-- /fsperf [seconds]: samples every frame for a while (60 s by default) and saves what the slow frames had in them, so a
-- hitch can be pinned on an addon (or on none) instead of guessed at. Needs the scriptProfile CVar on, which only takes at
-- a /reload: with it off, the command turns it on and asks for a /reload and the command again; a sample that ends turns
-- it back off (from the next /reload) when this command was what turned it on, since profiling costs a little itself.
-- /fsbug carries the last sample (BugReport.lua `hitch`), so a tester sends it with the usual report.
--
-- Per frame: UpdateAddOnCPUUsage, each loaded addon's CPU since the last frame (GetAddOnCPUUsage is cumulative), the
-- frame's own time and the Lua heap (a heap that shrank means a garbage collection step ran in that frame). A frame
-- over SLOW_MS is kept with its top addons. Saved to ForeverSTUwaveDB.hitch (on disk after /reload or logout) and
-- summed up in one chat line. The sampler's own UpdateAddOnCPUUsage call is charged to this addon, so read our share
-- against the other addons' with that in mind. Nothing runs until the command is typed, and the OnUpdate is removed
-- when the sample ends.
local _, FS = ...
if type(FS) ~= "table" then return end

FS.Hitch = FS.Hitch or {}
local H = FS.Hitch

H.SLOW_MS = 25          -- a frame this long is a felt stutter at 60 fps (16.7 ms a frame) and above
H.SPIKE_MS = 2          -- one addon using this much CPU in one frame is kept as a spike, whatever the frame time
H.KEEP = 80             -- slow frames kept
H.TOP = 4               -- addons named per slow frame
H.DEFAULT_S = 60
H.FRAMES_KEPT = 25     -- frames named in the per-frame CPU list
H.EVENT_CAP = 200       -- events remembered per frame (a burst past it is counted, not listed)

-- While sampling, one frame takes every event (RegisterAllEvents) and notes its name for the current frame, so a spike or
-- a slow frame is kept with what fired in it. No events means a timer or an OnUpdate did the work.
local evBuf, evCount = {}, 0
local function NoteEvent(_, event)
    evCount = evCount + 1
    if evCount <= H.EVENT_CAP then evBuf[evCount] = event end
end
local function EventsLine()
    if evCount == 0 then return "no events" end
    local seen, order = {}, {}
    for i = 1, math.min(evCount, H.EVENT_CAP) do
        local e = evBuf[i]
        if not seen[e] then seen[e] = 0; order[#order + 1] = e end
        seen[e] = seen[e] + 1
    end
    for i = 1, #order do order[i] = order[i] .. (seen[order[i]] > 1 and (" x" .. seen[order[i]]) or "") end
    local line = table.concat(order, ", ")
    if evCount > H.EVENT_CAP then line = line .. (", +%d more"):format(evCount - H.EVENT_CAP) end
    return line
end

local AddOns = C_AddOns or {}
local NumAddOns = AddOns.GetNumAddOns or GetNumAddOns
local AddOnInfo = AddOns.GetAddOnInfo or GetAddOnInfo
local IsLoaded = AddOns.IsAddOnLoaded or IsAddOnLoaded

local function Say(msg)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("|cffff4488Forever STUwave|r: " .. msg) end
end

local function LoadedNames()
    local out = {}
    local n = type(NumAddOns) == "function" and NumAddOns() or 0
    for i = 1, n do
        local name = AddOnInfo(i)
        if type(name) == "string" and IsLoaded(name) then out[#out + 1] = name end
    end
    return out
end

-- Every frame's own script CPU (GetFrameCPUUsage, children not included), keyed by frame: taken once when a sample
-- starts and once when it ends, so the difference names the handlers that did the work (a C_Timer callback has no frame
-- and shows only in the addon totals). Two walks of every frame: a one-off cost outside the sampled frames.
local function FrameCPU()
    local out = {}
    if type(EnumerateFrames) ~= "function" or type(GetFrameCPUUsage) ~= "function" then return out end
    local f = EnumerateFrames()
    while f do
        local ok, v = pcall(GetFrameCPUUsage, f, false)
        if ok and type(v) == "number" and v > 0 then out[f] = v end
        f = EnumerateFrames(f)
    end
    return out
end

-- Events an unnamed frame may listen to, to tell one handler from another.
H.NAMED_EVENTS = { "QUEST_LOG_UPDATE", "QUEST_WATCH_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED", "QUEST_TURNED_IN",
    "UNIT_QUEST_LOG_CHANGED", "ITEM_DATA_LOAD_RESULT", "GET_ITEM_INFO_RECEIVED", "BAG_UPDATE", "BAG_UPDATE_DELAYED",
    "UNIT_AURA", "UNIT_HEALTH", "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "PLAYER_TARGET_CHANGED", "NAME_PLATE_UNIT_ADDED",
    "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_COOLDOWN", "ACTIONBAR_SLOT_CHANGED", "UNIT_FLAGS",
    "PLAYER_REGEN_ENABLED", "LOOT_OPENED", "CHAT_MSG_LOOT", "ZONE_CHANGED", "UPDATE_FACTION", "SKILL_LINES_CHANGED",
    "PLAYER_MONEY", "UNIT_SPELLCAST_SUCCEEDED", "GROUP_ROSTER_UPDATE", "UPDATE_MOUSEOVER_UNIT", "CURSOR_CHANGED" }

local function FrameName(f)
    local ok, name = pcall(f.GetDebugName, f)
    if not (ok and type(name) == "string" and name ~= "") then
        ok, name = pcall(f.GetName, f)
        name = ok and type(name) == "string" and name or tostring(f)
    end
    if not (type(f.GetName) == "function" and f:GetName()) and type(f.IsEventRegistered) == "function" then
        local hit = {}
        for _, e in ipairs(H.NAMED_EVENTS) do
            local okE, on = pcall(f.IsEventRegistered, f, e)
            if okE and on then hit[#hit + 1] = e end
        end
        if #hit > 0 then name = name .. " [" .. table.concat(hit, " ") .. "]" end
    end
    return name
end

-- A named piece of work timed by its owner while a sample runs (the data bar's segments): total and worst ms.
function H.Time(key, ms)
    local s = H.run
    if not s then return end
    local t = s.timed[key]
    if not t then t = { n = 0, total = 0, worst = 0 }; s.timed[key] = t end
    t.n, t.total = t.n + 1, t.total + ms
    if ms > t.worst then t.worst = ms end
end

local function TopFrames(before)
    local after, list = FrameCPU(), {}
    for f, v in pairs(after) do
        local d = v - (before[f] or 0)
        if d > 0.05 then list[#list + 1] = { f = f, ms = d } end
    end
    table.sort(list, function(a, b) return a.ms > b.ms end)
    local out = {}
    for i = 1, math.min(#list, H.FRAMES_KEPT) do
        local f = list[i].f
        local ev = f.GetScript and f:GetScript("OnEvent") and "OnEvent" or ""
        local up = f.GetScript and f:GetScript("OnUpdate") and "OnUpdate" or ""
        out[i] = ("%.1f ms %s %s %s"):format(list[i].ms, FrameName(f), ev, up)
    end
    return out
end

local function Finish()
    local s = H.run
    H.run = nil
    H.frame:SetScript("OnUpdate", nil)
    if H.events then H.events:UnregisterAllEvents(); H.events:SetScript("OnEvent", nil) end
    evCount = 0
    local list = {}
    for i, name in ipairs(s.names) do
        list[#list + 1] = { name = name, totalMs = s.total[i], maxMs = s.max[i], slowMs = s.inSlow[i] }
    end
    table.sort(list, function(a, b) return a.slowMs > b.slowMs end)
    local seconds = GetTime() - s.startAt
    ForeverSTUwaveDB = ForeverSTUwaveDB or {}
    ForeverSTUwaveDB.hitch = {
        at = date and date("%Y-%m-%d %H:%M:%S") or nil, seconds = seconds, frames = s.frames, slowCount = s.slowCount,
        worstMs = s.worstMs, gcSteps = s.gcSteps, slowWithGc = s.slowWithGc, addons = list, slow = s.slow,
        moving = s.moving, spikes = s.spikes, frameCpu = TopFrames(s.frameCpu or {}), timed = s.timed,
    }
    local top = list[1]
    Say(("sample saved: %d frames, %d slow (worst %.0f ms, %d with a heap drop); most CPU in slow frames: %s. Type /fsbug to send it.")
        :format(s.frames, s.slowCount, s.worstMs, s.slowWithGc, top and top.name or "none"))
    if ForeverSTUwaveDB.hitchProfileOn and type(SetCVar) == "function" then
        ForeverSTUwaveDB.hitchProfileOn = nil
        pcall(SetCVar, "scriptProfile", "0")       -- off again from the next /reload
    end
end

local function Step(_, elapsed)
    local s = H.run
    if not s then return end
    UpdateAddOnCPUUsage()
    local ms = (elapsed or 0) * 1000
    local heap = collectgarbage("count")
    local dropped = s.heap and heap < s.heap
    if dropped then s.gcSteps = s.gcSteps + 1 end
    s.heap = heap
    local deltas, names = s.deltas, s.names
    for i = 1, #names do
        local cur = GetAddOnCPUUsage(names[i]) or 0
        local d = cur - (s.last[i] or cur)
        s.last[i] = cur
        deltas[i] = d
        s.total[i] = s.total[i] + d
        if d > s.max[i] then s.max[i] = d end
    end
    s.frames = s.frames + 1
    if s.frames > 2 and #s.spikes < H.KEEP then
        for i = 1, #names do
            if deltas[i] >= H.SPIKE_MS then
                s.spikes[#s.spikes + 1] = ("%.2f s %s %.2f ms (frame %.0f ms): %s"):format(GetTime() - s.startAt, names[i], deltas[i],
                    ms, EventsLine())
            end
        end
    end
    -- the speed can be a secret on this client: count a frame as moving only from a plain read
    local speed = type(GetUnitSpeed) == "function" and GetUnitSpeed("player") or nil
    local moving = type(speed) == "number" and not (FS.IsSecret and FS.IsSecret(speed)) and speed > 0
    if moving then s.moving = s.moving + 1 end
    if s.frames > 2 and ms >= H.SLOW_MS then
        s.slowCount = s.slowCount + 1
        if ms > s.worstMs then s.worstMs = ms end
        if dropped then s.slowWithGc = s.slowWithGc + 1 end
        for i = 1, #names do s.inSlow[i] = s.inSlow[i] + deltas[i] end
        if #s.slow < H.KEEP then
            -- the top addons of this frame, by a few passes over the deltas (no sort table per frame)
            local row = { t = GetTime() - s.startAt, ms = ms, gc = dropped or nil, moving = moving or nil, heapKb = heap,
                events = EventsLine() }
            local used = {}
            for k = 1, H.TOP do
                local best, bi = -1, nil
                for i = 1, #names do
                    if not used[i] and deltas[i] > best then best, bi = deltas[i], i end
                end
                if not bi or best <= 0 then break end
                used[bi] = true
                row[#row + 1] = ("%s %.2f"):format(names[bi], best)
            end
            s.slow[#s.slow + 1] = row
        end
    end
    evCount = 0
    if GetTime() >= s.stopAt then Finish() end
end

function H.Start(seconds)
    if H.run then Say("a sample is already running.") return end
    if type(GetCVar) == "function" and GetCVar("scriptProfile") ~= "1" then
        if type(SetCVar) == "function" and pcall(SetCVar, "scriptProfile", "1") then
            ForeverSTUwaveDB = ForeverSTUwaveDB or {}
            ForeverSTUwaveDB.hitchProfileOn = true
            Say("CPU profiling is now on. Type /reload, then /fsperf again.")
        else
            Say("CPU profiling is off and could not be turned on.")
        end
        return
    end
    if type(UpdateAddOnCPUUsage) ~= "function" or type(GetAddOnCPUUsage) ~= "function" then
        Say("this client has no addon CPU readout.")
        return
    end
    local names = LoadedNames()
    local s = { names = names, last = {}, total = {}, max = {}, inSlow = {}, deltas = {}, slow = {}, spikes = {}, timed = {}, frames = 0,
        slowCount = 0, worstMs = 0, gcSteps = 0, slowWithGc = 0, moving = 0 }
    for i = 1, #names do s.total[i], s.max[i], s.inSlow[i], s.deltas[i] = 0, 0, 0, 0 end
    s.frameCpu = FrameCPU()
    s.startAt = GetTime()
    s.stopAt = s.startAt + seconds
    H.run = s
    H.frame = H.frame or CreateFrame("Frame")
    H.frame:SetScript("OnUpdate", Step)
    H.events = H.events or CreateFrame("Frame")
    evCount = 0
    if H.events.RegisterAllEvents then
        H.events:SetScript("OnEvent", NoteEvent)
        H.events:RegisterAllEvents()
    end
    Say(("sampling %d addons for %d s. Play as usual."):format(#names, seconds))
end

SLASH_FSPERF1 = "/fsperf"
SlashCmdList["FSPERF"] = function(msg)
    local n = tonumber(msg and msg:match("%d+"))
    H.Start((n and n >= 5 and n <= 600) and n or H.DEFAULT_S)
end
