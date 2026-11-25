-- /fshitch [seconds]: samples every frame for a while (60 s by default) and saves what the slow frames had in them, so a
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

H.SLOW_MS = 40          -- a frame this long is a hitch at a 118 frame cap (about 8.5 ms a frame)
H.KEEP = 80             -- slow frames kept
H.TOP = 4               -- addons named per slow frame
H.DEFAULT_S = 60

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

local function Finish()
    local s = H.run
    H.run = nil
    H.frame:SetScript("OnUpdate", nil)
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
        moving = s.moving,
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
            local row = { t = GetTime() - s.startAt, ms = ms, gc = dropped or nil, moving = moving or nil, heapKb = heap }
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
    if GetTime() >= s.stopAt then Finish() end
end

function H.Start(seconds)
    if H.run then Say("a sample is already running.") return end
    if type(GetCVar) == "function" and GetCVar("scriptProfile") ~= "1" then
        if type(SetCVar) == "function" and pcall(SetCVar, "scriptProfile", "1") then
            ForeverSTUwaveDB = ForeverSTUwaveDB or {}
            ForeverSTUwaveDB.hitchProfileOn = true
            Say("CPU profiling is now on. Type /reload, then /fshitch again.")
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
    local s = { names = names, last = {}, total = {}, max = {}, inSlow = {}, deltas = {}, slow = {}, frames = 0,
        slowCount = 0, worstMs = 0, gcSteps = 0, slowWithGc = 0, moving = 0 }
    for i = 1, #names do s.total[i], s.max[i], s.inSlow[i], s.deltas[i] = 0, 0, 0, 0 end
    s.startAt = GetTime()
    s.stopAt = s.startAt + seconds
    H.run = s
    H.frame = H.frame or CreateFrame("Frame")
    H.frame:SetScript("OnUpdate", Step)
    Say(("sampling %d addons for %d s. Play as usual."):format(#names, seconds))
end

SLASH_FSHITCH1 = "/fshitch"
SlashCmdList["FSHITCH"] = function(msg)
    local n = tonumber(msg and msg:match("%d+"))
    H.Start((n and n >= 5 and n <= 600) and n or H.DEFAULT_S)
end
