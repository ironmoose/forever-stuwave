-- Forever STUwave: data service for the player's own debuffs on the target (FS.TargetDebuffs).
-- Entries are { id, name, icon, expires, duration, count, order }: an aura snapshot out of combat, an own-cast
-- ledger in combat. IN COMBAT it is an estimate: a resisted cast still counts, refreshes that are not casts (poison
-- procs, Deep Wounds, talents) are invisible, and a cast is timed from the last snapshot of that spell id or name,
-- else the SPELL_SECONDS / HudSpells tables (an unknown one has no expiry); out of combat the snapshot is exact.

local _, FS = ...

local TD = {}
FS.TargetDebuffs = TD

local MAX_AURAS = 40
local SCAN_DELAY = 0.1       -- UNIT_AURA bursts coalesce into one scan this long after the first
local PENDING_TTL = 60       -- seconds a SENT cast is remembered without a verdict
local STALE_AFTER = 30       -- a ledger target whose debuffs all ended this long ago is dropped
local NO_EXPIRY_AGE = 120    -- an entry with no known expiry is believed this long after it was written

-- Names match classic and are unverified on Forever; a name seen in any snapshot is tracked whatever the class.
local CLASS_DEBUFFS = {
    WARRIOR = { "Rend", "Deep Wounds", "Thunder Clap", "Sunder Armor", "Demoralizing Shout" },
    ROGUE = { "Deadly Poison", "Crippling Poison", "Rupture", "Garrote", "Expose Armor" },
    DRUID = { "Rake", "Rip" },
}

-- Seconds a debuff lasts when the player casts it, so the FIRST cast in combat is timed before any snapshot has
-- taught the session. `apply` is the top rank (or the only length); `byRank` maps a cast rank id to its length for a
-- spell whose length follows the rank. Verified against Wowhead / ForeverDB (Forever): Rend 9/12/15/18/21 s,
-- Thunder Clap 10/14/18/22/26/30 s (rank ids 6343 and 11556 were read there, the rest are classic rank ids),
-- Sunder Armor 30 s, Hamstring 15 s, Demoralizing Shout 45 s (30 s in classic). Deep Wounds has no cast, so no entry.
-- Only Warrior is filled so far; every other class is timed from its first readable snapshot (learned below).
local SPELL_SECONDS = {
    ["Rend"] = { apply = 21, byRank = { [772] = 9, [6546] = 12, [6547] = 15, [6548] = 18, [11572] = 21, [11573] = 21, [11574] = 21 } },
    ["Thunder Clap"] = { apply = 30, byRank = { [6343] = 10, [8198] = 14, [8204] = 18, [8205] = 22, [11580] = 26, [11581] = 30 } },
    ["Sunder Armor"] = { apply = 30 },
    ["Hamstring"] = { apply = 15 },
    ["Demoralizing Shout"] = { apply = 45 },
}

local EMPTY = {}
local list = EMPTY                  -- the current entries, sorted; replaced (never edited) by Rebuild
local subs, subCount = {}, 0
local enabled, suppress, scanQueued, areaHooked, readableHooked, hudOn = false, false, false, false, false, false
local epoch = 0                     -- bumped on every target change
local lastTakes                    -- the last FS.TargetTakesDots answer
local ledger = {}                   -- target key -> { [name] = entry }
local pending = {}                  -- castGUID -> { key, at }
local hudEntries, hudNames          -- the Hud's DoT rows as entries, and every name those DoTs go by
local learnedDuration, maxStack, known, seenOrder, seenCount = {}, {}, {}, {}, 0
local learnedById = {}                  -- spell id -> seconds, from a readable snapshot (session only)
local hudSeconds                    -- name -> HudSpells def, built on first use
local classToken, classSet, classOrder
local plainFrame, targetFrame, playerFrame

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "targetdebuffs_" .. key, "|cffff4488Forever STUwave|r: target debuffs: " .. tostring(msg))
    end
end

local function Plain(v)
    local f = FS.IsSecret
    return not (f and f(v))
end

local function PlainOf(v, kind)
    if not Plain(v) then return nil end
    if type(v) ~= kind or v ~= v then return nil end
    return v
end

local function OnPlayer(unit) return PlainOf(unit, "string") == "player" end

-------------------------------------------------------------------------------
-- Lookups
-------------------------------------------------------------------------------

local function Class()
    if classToken then return classToken end
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    token = ok and PlainOf(token, "string") or nil
    if not token then return nil end
    classToken, classSet, classOrder = token, {}, {}
    for i, n in ipairs(CLASS_DEBUFFS[token] or EMPTY) do classSet[n], classOrder[n] = true, i end
    return classToken
end

local function OrderOf(name)
    Class()
    if classOrder and classOrder[name] then return classOrder[name] end
    if not seenOrder[name] then
        seenCount = seenCount + 1
        seenOrder[name] = seenCount
    end
    return 100 + seenOrder[name]
end

local function HudDef(name)
    if not hudSeconds then
        hudSeconds = {}
        for _, def in pairs(FS.HudSpells or EMPTY) do
            if def.apply and not def.self then
                for _, n in ipairs(def.names or EMPTY) do hudSeconds[n] = def end
            end
        end
    end
    return hudSeconds[name]
end

-- Seconds a cast of `spellID` lasts, best source first: what a snapshot measured for this exact id, the rank table
-- for this exact id, what a snapshot measured for the name (another rank, the player's talents), then the top rank.
local function DurationOf(name, spellID)
    if spellID and learnedById[spellID] then return learnedById[spellID] end
    local def, own = HudDef(name), SPELL_SECONDS[name]
    local byRank = spellID and (def and def.applyByRank and def.applyByRank[spellID] or own and own.byRank and own.byRank[spellID])
    if byRank then return byRank end
    if learnedDuration[name] then return learnedDuration[name] end
    return def and def.apply or own and own.apply or nil
end

local function Tracks(name)
    Class()
    return known[name] or (classSet and classSet[name]) or SPELL_SECONDS[name] ~= nil or HudDef(name) ~= nil
end

-- name, icon of a spell id; plain values only.
local function SpellInfo(id)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, id)
        if ok and Plain(info) and type(info) == "table" then
            return PlainOf(info.name, "string"), PlainOf(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, icon = pcall(GetSpellInfo, id)
        if ok then return PlainOf(name, "string"), PlainOf(icon, "number") end
    end
    return nil
end

-- The ledger key of the current target: its GUID, or the epoch when the GUID is secret; nil with no target.
local function TargetKey()
    if FS.HasTarget and not FS.HasTarget() then return nil end
    local ok, g = pcall(UnitGUID, "target")
    if not ok then return nil end
    if not Plain(g) then return "e" .. epoch end
    if type(g) == "string" then return g end
    return nil
end

local function TakesDots()
    if FS.TargetTakesDots then return FS.TargetTakesDots() end
    return true
end

local function IsJudgement(e)
    for _, def in pairs(FS.HudSpells or EMPTY) do
        if def.judgement then
            for _, id in ipairs(def.ids or EMPTY) do
                if id == e.id then return true end
            end
        end
    end
    return e.name:find("^Judg") ~= nil      -- English fallback: aura ids differ from the cast id
end

-- The Seal module carries Judgement while the Class Module area is in use.
local function Excluded(e)
    if Class() ~= "PALADIN" or not IsJudgement(e) then return false end
    local areas = FS.GunsightAreas
    return areas ~= nil and areas.AreaOf ~= nil and areas.AreaOf("class") ~= nil
end

-------------------------------------------------------------------------------
-- The list
-------------------------------------------------------------------------------

local function ByOrder(a, b)
    if a.order ~= b.order then return a.order < b.order end
    return a.name < b.name
end

local function Rebuild()
    if suppress then return end
    local out = {}
    lastTakes = TakesDots()
    if lastTakes then
        for _, e in ipairs(hudEntries or EMPTY) do out[#out + 1] = e end
        local key = TargetKey()
        for name, e in pairs(key and ledger[key] or EMPTY) do
            if not (hudNames and hudNames[name]) and not Excluded(e) then out[#out + 1] = e end
        end
        table.sort(out, ByOrder)
    end
    list = out
    for i = 1, #subs do
        local ok, err = pcall(subs[i], out, epoch)
        if not ok then LogOnce("subscriber", err) end
    end
end

-- Source 1: the player's harmful auras on the target, read only while auras are readable.
local function Report(label, err) LogOnce("read", tostring(label) .. ": " .. tostring(err)) end

local function ScanInto(bucket)
    local read = FS.FrameHelpers and FS.FrameHelpers.ReadAuraSlot
    if not read then error("FrameHelpers.ReadAuraSlot is missing") end
    for i = 1, MAX_AURAS do
        local a = read("target", i, "HARMFUL", Report)
        if not (a and Plain(a) and type(a) == "table") then break end
        local name = PlainOf(a.name, "string")
        if name and PlainOf(a.caster, "string") == "player" then
            local duration, expires = PlainOf(a.duration, "number"), PlainOf(a.expirationTime, "number")
            local count = math.floor(PlainOf(a.count, "number") or 0)
            if count < 1 then count = 1 end
            local entry = { id = PlainOf(a.spellId, "number"), name = name, icon = PlainOf(a.icon, "number") or PlainOf(a.icon, "string"),
                count = count, order = OrderOf(name), at = GetTime() }
            if duration and duration > 0 then
                entry.duration = duration
                learnedDuration[name] = duration
                if entry.id then learnedById[entry.id] = duration end
                if expires and expires > 0 then entry.expires = expires end
            end
            if count > (maxStack[name] or 0) then maxStack[name] = count end
            known[name] = true
            bucket[name] = entry
        end
    end
end

-- true when the ledger of the current target was replaced by a snapshot.
local function Scan()
    local key = TargetKey()
    if not key or not (FS.AurasReadable and FS.AurasReadable()) then return false end
    local bucket = {}
    local ok, err = pcall(ScanInto, bucket)
    if not ok then LogOnce("scan", err); return false end
    ledger[key] = bucket
    return true
end

local function ScanAndRebuild()
    Scan()
    Rebuild()
end

local function FlushScan()
    scanQueued = false
    if enabled then ScanAndRebuild() end
end

local function QueueScan()
    if scanQueued or not (FS.AurasReadable and FS.AurasReadable()) then return end
    if not (C_Timer and C_Timer.After) then ScanAndRebuild(); return end
    scanQueued = true
    C_Timer.After(SCAN_DELAY, FlushScan)
end

-- Drops targets that no longer matter; `keepKey` stays whatever its age.
local function Prune(keepKey)
    local now = GetTime()
    for key, bucket in pairs(ledger) do
        if key ~= keepKey then
            local live = false
            for _, e in pairs(bucket) do
                local believed = e.expires and e.expires > now - STALE_AFTER
                    or not e.expires and now - (e.at or 0) < math.max(NO_EXPIRY_AGE, e.duration or 0)
                if believed then live = true end
            end
            if not live then ledger[key] = nil end
        end
    end
    for id, p in pairs(pending) do
        if now - p.at > PENDING_TTL then pending[id] = nil end
    end
end

-------------------------------------------------------------------------------
-- Source 2: the own-cast ledger
-------------------------------------------------------------------------------

-- A cast aimed at a unit whose name differs from the target's ([@mouseover], [@focus]) is not attributed.
local function AimedElsewhere(targetName)
    local sent = PlainOf(targetName, "string")
    if not sent or sent == "" then return false end
    local ok, current = pcall(UnitName, "target")
    current = ok and PlainOf(current, "string") or nil
    return current ~= nil and current ~= "" and current ~= sent
end

local function OnSent(unit, targetName, castGUID)
    if not OnPlayer(unit) then return end
    local guid = PlainOf(castGUID, "string")
    if not guid then return end
    pending[guid] = { key = (not AimedElsewhere(targetName)) and TargetKey() or nil, at = GetTime() }
end

local function DropPending(unit, castGUID)
    local guid = PlainOf(castGUID, "string")
    if OnPlayer(unit) and guid then pending[guid] = nil end
end

local function OnSucceeded(unit, castGUID, spellID)
    if not OnPlayer(unit) then return end
    local id = PlainOf(spellID, "number")
    local guid = PlainOf(castGUID, "string")
    local p = guid and pending[guid]
    if guid then pending[guid] = nil end
    if not id then return end
    local key
    if p then key = p.key else key = TargetKey() end
    if not key then return end
    local name, icon = SpellInfo(id)
    if not (name and Tracks(name)) then return end
    local now = GetTime()
    local bucket = ledger[key]
    if not bucket then bucket = {}; ledger[key] = bucket end
    local prev = bucket[name]
    local count = 1
    if prev and prev.count and (not prev.expires or prev.expires > now) then
        count = math.min(prev.count + 1, maxStack[name] or prev.count)
    end
    local duration = DurationOf(name, id)
    bucket[name] = { id = id, name = name, icon = icon, count = count, order = OrderOf(name),
        duration = duration, expires = duration and now + duration or nil, at = now }
    if key == TargetKey() then
        Rebuild()
        QueueScan()                 -- readable: the snapshot corrects a resisted cast
    end
end

-------------------------------------------------------------------------------
-- The Hud's DoT ledger (Priest, Warlock): better than either source for a profile DoT
-------------------------------------------------------------------------------

local function HudDots()
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then return nil end
    local ok, profile = pcall(Hud.GetProfile)
    if not ok or type(profile) ~= "table" then return nil end
    local dots = profile.dots
    if type(dots) == "table" and next(dots) ~= nil then return dots end
    return nil
end

local function OnHud(state)
    local dots = HudDots()
    hudEntries, hudNames = nil, nil
    if dots and type(state) == "table" and state.active and type(state.row) == "table" then
        hudEntries, hudNames = {}, {}
        local now = GetTime()
        for key in pairs(dots) do
            for _, n in ipairs(FS.HudSpells and FS.HudSpells[key] and FS.HudSpells[key].names or EMPTY) do hudNames[n] = true end
        end
        for _, e in ipairs(state.row) do
            local key = type(e) == "table" and PlainOf(e.key, "string")
            local remaining = key and dots[key] and PlainOf(e.remaining, "number")
            if remaining then
                local expires = PlainOf(e.expiresAt, "number")
                if not expires and remaining > 0 then expires = now + remaining end
                local live = expires ~= nil and expires > now
                local def = FS.HudSpells and FS.HudSpells[key]
                hudEntries[#hudEntries + 1] = {
                    name = def and def.names and def.names[1] or key,
                    icon = PlainOf(e.icon, "number") or PlainOf(e.icon, "string"),
                    expires = live and expires or 0, duration = live and PlainOf(e.duration, "number") or nil,
                    count = 1, order = #hudEntries + 1,
                }
            end
        end
    end
    Rebuild()
end

local function SyncHud()
    local want = enabled and HudDots() ~= nil
    if want and not hudOn then
        hudOn = true
        FS.Hud.Subscribe(OnHud)
    elseif not want and hudOn then
        hudOn = false
        if FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnHud) end
        hudEntries, hudNames = nil, nil
    end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local handlers = {}

function handlers.PLAYER_TARGET_CHANGED()
    epoch = epoch + 1
    hudEntries = nil                -- the Hud has not pushed for this target yet
    Prune(TargetKey())
    ScanAndRebuild()
end

function handlers.PLAYER_ENTERING_WORLD()
    epoch = epoch + 1
    ledger, pending = {}, {}
    SyncHud()
    ScanAndRebuild()
end

function handlers.PLAYER_REGEN_ENABLED()
    if Scan() then Prune(TargetKey()) end
    Rebuild()
end

function handlers.UNIT_AURA(unit)
    if PlainOf(unit, "string") == "target" then QueueScan() end
end

local function OnTargetState(unit)
    if PlainOf(unit, "string") ~= "target" then return end
    if TakesDots() ~= lastTakes then Rebuild() end
end
handlers.UNIT_HEALTH, handlers.UNIT_FLAGS, handlers.UNIT_FACTION = OnTargetState, OnTargetState, OnTargetState

handlers.UNIT_SPELLCAST_SENT = OnSent
handlers.UNIT_SPELLCAST_SUCCEEDED = OnSucceeded
handlers.UNIT_SPELLCAST_FAILED = DropPending
handlers.UNIT_SPELLCAST_INTERRUPTED = DropPending

local function OnEvent(_, event, ...)
    local h = handlers[event]
    if not h then return end
    local ok, err = pcall(h, ...)
    if not ok then LogOnce("event_" .. event, err) end
end

local PLAIN_EVENTS = { "PLAYER_TARGET_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }
local TARGET_EVENTS = { "UNIT_AURA", "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }
local PLAYER_EVENTS = { "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }

local function Register(frame, events, unit)
    for _, e in ipairs(events) do
        if unit and frame.RegisterUnitEvent then
            pcall(frame.RegisterUnitEvent, frame, e, unit)
        else
            frame:RegisterEvent(e)
        end
    end
end

local function Unregister(frame, events)
    for _, e in ipairs(events) do frame:UnregisterEvent(e) end
end

local function Enable()
    enabled = true
    if not plainFrame then
        plainFrame, targetFrame, playerFrame = CreateFrame("Frame"), CreateFrame("Frame"), CreateFrame("Frame")
        for _, f in ipairs({ plainFrame, targetFrame, playerFrame }) do f:SetScript("OnEvent", OnEvent) end
    end
    Register(plainFrame, PLAIN_EVENTS)
    Register(targetFrame, TARGET_EVENTS, "target")
    Register(playerFrame, PLAYER_EVENTS, "player")
    if FS.OnAurasReadable and not readableHooked then
        readableHooked = true
        FS.OnAurasReadable(function() if enabled then ScanAndRebuild() end end)
    end
    local areas = FS.GunsightAreas
    if not areaHooked and areas and areas.OnAreaChanged then
        areaHooked = true
        areas.OnAreaChanged(function() if enabled then Rebuild() end end)
    end
    suppress = true
    SyncHud()
    Scan()
    suppress = false
    Rebuild()
end

local function Disable()
    enabled = false
    Unregister(plainFrame, PLAIN_EVENTS)
    Unregister(targetFrame, TARGET_EVENTS)
    Unregister(playerFrame, PLAYER_EVENTS)
    SyncHud()
    ledger, pending, list = {}, {}, EMPTY
end

-------------------------------------------------------------------------------
-- API
-------------------------------------------------------------------------------

-- fn(list, epoch) runs at once and after every change; the list is shared and read only.
function TD.Subscribe(fn)
    if type(fn) ~= "function" then return end
    subs[#subs + 1] = fn
    subCount = subCount + 1
    if subCount == 1 then
        Enable()
    else
        local ok, err = pcall(fn, list, epoch)
        if not ok then LogOnce("subscriber", err) end
    end
end

function TD.Unsubscribe(fn)
    for i = #subs, 1, -1 do
        if subs[i] == fn then
            table.remove(subs, i)
            subCount = subCount - 1
        end
    end
    if subCount == 0 and enabled then Disable() end
end

function TD.Get() return list end

function TD.Epoch() return epoch end
