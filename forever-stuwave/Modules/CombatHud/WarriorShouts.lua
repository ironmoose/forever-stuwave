-- Forever STUwave: the Warrior's shouts, as plain state for the Gunsight Warrior module
--
-- Two shouts: Battle Shout (a buff on the player, 3 min on Forever) and Demoralizing Shout (a debuff on the enemies around the
-- player, learned at 14). For each one this file knows: whether the player knows it, whether it is up, when it runs out and
-- where that number came from.
--
-- WHERE THE NUMBERS COME FROM.
--   * Battle Shout out of combat (FS.AurasReadable): the player's own aura, by every known rank id, then by name. A plain
--     expirationTime and duration are the truth (source "aura"); a readable answer with no aura means it is down.
--   * In combat aura reads are refused, so the player's own cast is the clock: UNIT_SPELLCAST_SUCCEEDED of the player, matched
--     by NAME so any rank counts, stamps now + the duration (the last plain aura duration seen, else DEFS). Source "cast": the
--     module shows the time with a "~". A shout from another warrior in combat is not seen until the next plain read.
--   * Demoralizing Shout is on the target, which addons cannot read in combat, so it is always the cast ledger. Its duration is
--     DEFS (the Classic value, UNMEASURED on Forever).
-- A spellID that is secret or missing is ignored (never compared). The ledger listens from Start() on and never stops: a
-- cast while the module is hidden (no target) cannot be read back later.
--
-- API: Start(), Get(key) -> record, Remaining(key, now), Lit(key, now) -> 0..8, Refresh(), Subscribe(fn), Unsubscribe(fn),
-- Tick(now). key is "battle" or "demo". A listener is called fn(key, reason) with reason "cast" (the player just shouted: the
-- module plays its animation), "change" or "learn". Record fields: known (true / false), up, expires (GetTime based or nil),
-- duration, source ("aura" | "cast" | nil), castAt.

local _, FS = ...

FS.WarriorShouts = FS.WarriorShouts or {}
local Shouts = FS.WarriorShouts

local IsSecret = FS.IsSecret or function() return false end
local ceil = math.ceil

local DEFS = {
    battle = { name = "Battle Shout", ids = { 25289, 11551, 11550, 11549, 6192, 5242, 6673 }, duration = 180, aura = true },
    -- 30 s is the Classic Era duration; not measured on Forever
    demo = { name = "Demoralizing Shout", ids = { 11556, 11555, 11554, 6190, 1160 }, duration = 30, aura = false },
}
Shouts.DEFS = DEFS
Shouts.BLOCKS = 8

local state = {
    battle = { key = "battle", known = false, up = false },
    demo = { key = "demo", known = false, up = false },
}

local listeners = {}
local started = false
local frame

local function Notify(key, reason)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], key, reason)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "warriorshouts_listener", "|cffff4488Forever STUwave|r: warrior shouts listener: " .. tostring(err))
        end
    end
end

-------------------------------------------------------------------------------
-- Secret safe reads
-------------------------------------------------------------------------------

local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

local nameCache = {}
local function SpellNameOf(id)
    local hit = nameCache[id]
    if hit then return hit end
    local name
    if C_Spell and C_Spell.GetSpellName then
        local ok, n = pcall(C_Spell.GetSpellName, id)
        if ok then name = PlainOf(n, "string") end
    end
    if not name and GetSpellInfo then
        local ok, n = pcall(GetSpellInfo, id)
        if ok then name = PlainOf(n, "string") end
    end
    if name then nameCache[id] = name end
    return name
end

-- true / false / nil (cannot tell) for "does the player know this spell id"
local function IsKnownId(id)
    local sawFalse, unreadable = false, false
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    for i = 1, 3 do
        local fn = fns[i]
        if fn then
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) then
                if r then return true end
                sawFalse = true
            else
                unreadable = true
            end
        end
    end
    if unreadable then return nil end
    if sawFalse then return false end
    return nil
end

local function Resolve(key)
    local d, s = DEFS[key], state[key]
    local known, unknown = false, false
    s.localName = s.localName or SpellNameOf(d.ids[#d.ids])
    for _, id in ipairs(d.ids) do
        local k = IsKnownId(id)
        if k == true then known = true; s.id = id; break end
        if k == nil then unknown = true end
    end
    -- An unreadable book keeps what we knew: never forget a shout on a refused read.
    if known or not unknown then
        if s.known ~= known then
            s.known = known
            return true
        end
    end
    return false
end

-- expires, duration of the player's own Battle Shout when an aura read is allowed; false when readably absent; nil unknown
local function ReadBattleAura()
    if not (FS.AurasReadable and FS.AurasReadable()) then return nil end
    local A = C_UnitAuras
    local byId = (A and A.GetPlayerAuraBySpellID) or _G.GetPlayerAuraBySpellID
    local sawAnswer = false
    if byId then
        for _, id in ipairs(DEFS.battle.ids) do
            local ok, aura = pcall(byId, id)
            if ok and not IsSecret(aura) then
                sawAnswer = true
                if type(aura) == "table" then
                    local exp, dur = PlainOf(aura.expirationTime, "number"), PlainOf(aura.duration, "number")
                    if exp and dur then return exp, dur end
                end
            end
        end
    end
    local byName = A and A.GetAuraDataBySpellName
    local name = state.battle.localName or DEFS.battle.name
    if byName then
        local ok, aura = pcall(byName, "player", name, "HELPFUL")
        if ok and not IsSecret(aura) then
            sawAnswer = true
            if type(aura) == "table" then
                local exp, dur = PlainOf(aura.expirationTime, "number"), PlainOf(aura.duration, "number")
                if exp and dur then return exp, dur end
            end
        end
    end
    if sawAnswer then return false end
    return nil
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local function Now() return GetTime() end

local function SetUp(s, expires, duration, source)
    local changed = s.up ~= true or s.expires ~= expires or s.duration ~= duration or s.source ~= source
    s.up, s.expires, s.duration, s.source = true, expires, duration, source
    return changed
end

local function SetDown(s)
    if not s.up and s.expires == nil then return false end
    s.up, s.expires, s.source = false, nil, nil
    return true
end

function Shouts.Get(key) return state[key] end

function Shouts.Remaining(key, now)
    local s = state[key]
    if not (s and s.up and s.expires) then return nil end
    local r = s.expires - (now or Now())
    if r < 0 then r = 0 end
    return r
end

function Shouts.Lit(key, now)
    local s = state[key]
    if not (s and s.up and s.expires and s.duration and s.duration > 0) then return 0 end
    local r = s.expires - (now or Now())
    if r <= 0 then return 0 end
    local n = ceil(r / s.duration * Shouts.BLOCKS)
    if n < 1 then n = 1 elseif n > Shouts.BLOCKS then n = Shouts.BLOCKS end
    return n
end

local function RefreshBattle()
    local s = state.battle
    local exp, dur = ReadBattleAura()
    if exp then
        s.lastDuration = dur > 0 and dur or s.lastDuration
        if dur <= 0 then return SetDown(s) end      -- an aura with no duration (should not happen) cannot be drawn as a clock
        return SetUp(s, exp, dur, "aura")
    elseif exp == false then
        return SetDown(s)
    end
    return false                                    -- unreadable: keep the ledger's numbers
end

function Shouts.Refresh()
    local learned = false
    for key in pairs(DEFS) do
        if Resolve(key) then learned = true end
    end
    local changed = RefreshBattle()
    if learned then Notify("battle", "learn"); Notify("demo", "learn") end
    if changed then Notify("battle", "change") end
end

-- Expiry: a shout whose clock ran out is down. Called from the module's ticker and from Refresh paths.
function Shouts.Tick(now)
    now = now or Now()
    for key, s in pairs(state) do
        if s.up and s.expires and s.expires <= now then
            SetDown(s)
            Notify(key, "change")
        end
    end
end

local function OnCast(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local name = SpellNameOf(spellID)
    if not name then return end
    for key, d in pairs(DEFS) do
        local s = state[key]
        if name == d.name or (s.localName and name == s.localName) then
            local now = Now()
            local dur = (key == "battle" and s.lastDuration) or d.duration
            s.castAt = now
            if not s.known then s.known = true end
            SetUp(s, now + dur, dur, "cast")
            Notify(key, "cast")
            -- out of combat the aura is readable a moment later; read it so the "~" goes
            if key == "battle" and C_Timer and C_Timer.After then
                C_Timer.After(0.2, function() if RefreshBattle() then Notify("battle", "change") end end)
            end
        end
    end
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP",
    "PLAYER_REGEN_ENABLED" }

function Shouts.Start()
    if started then return end
    started = true
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2, a3)
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            local ok, err = pcall(OnCast, a3)
            if not ok and FS.LogDegradeOnce then
                pcall(FS.LogDegradeOnce, "warriorshouts_cast", "|cffff4488Forever STUwave|r: warrior shouts cast: " .. tostring(err))
            end
        elseif event == "UNIT_AURA" then
            if RefreshBattle() then Notify("battle", "change") end
        else
            pcall(Shouts.Refresh)
        end
    end)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then
        FH.RegisterEvent(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        FH.RegisterEvent(frame, "UNIT_AURA", "player")
        if FH.RegisterEvents then FH.RegisterEvents(frame, EVENTS) end
    else
        pcall(frame.RegisterUnitEvent, frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        pcall(frame.RegisterUnitEvent, frame, "UNIT_AURA", "player")
        for _, e in ipairs(EVENTS) do pcall(frame.RegisterEvent, frame, e) end
    end
    if FS.OnAurasReadable then
        FS.OnAurasReadable(function() if RefreshBattle() then Notify("battle", "change") end end)
    end
    pcall(Shouts.Refresh)
end

function Shouts.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function Shouts.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
Shouts._state = state
Shouts._OnCast = OnCast
