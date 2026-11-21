-- Forever STUwave: the Warrior's strike windows, as plain state for the Gunsight Warrior module's lane
--
-- A strike window is the stretch of time a reactive Warrior spell can be used: Overpower after the target dodges, Revenge after the
-- player blocks, dodges or parries, Victory Rush after a kill that gives experience. This file knows, for each one: whether the
-- player knows the spell, whether its window is open, when it started, when it runs out and which source said so. The lane in
-- GunsightWarrior.lua only paints it. A new window is one more entry in DEFS (and ORDER); nothing else here is per spell.
--
-- EVERY NUMBER HERE IS UNMEASURED ON FOREVER. The window lengths are the Classic values (the in-game tooltips give no length), the
-- spell ids are Classic ranks from memory, and the names are the truth: ids are tried first, then the name the client resolves.
--
-- HOW A WINDOW OPENS. The first of two sources to fire; its moment is the start and the window runs LENGTH seconds from it.
--   * SPELL_ACTIVATION_OVERLAY_GLOW_SHOW for the spell (matched by id, else by NAME; a secret or missing id is ignored, never
--     compared). A second SHOW while the window is open restarts the clock. This source is unverified on this client.
--   * IsSpellUsable going from plain false to plain true (C_Spell.IsSpellUsable, else the old IsUsableSpell), read on
--     SPELL_UPDATE_USABLE and every POLL seconds from Tick (which runs only while the lane's module is shown). In combat the
--     answer may be a SECRET boolean: that read is simply unavailable and never tested, so the glow is then the only source. Out
--     of the stance a spell needs it likely reads plain false with the window open; that is accepted (no window, no lane).
--     Only a false-to-true change opens a window: a first read of true says nothing about when it began.
-- HOW IT CLOSES. Earlier than the length on GLOW_HIDE, or when usable goes plain true to plain false (a quiet close: reason
-- "close"); on the player's own cast of the spell (UNIT_SPELLCAST_SUCCEEDED for "player", matched by NAME so any rank counts:
-- reason "cast"); or when the length runs out in Tick (reason "expire"). A cast that arrives up to CAST_GRACE s after a quiet
-- close still counts as the cast (the engine may drop the glow a beat before the cast event reaches us).
-- COMBAT_LOG_EVENT_UNFILTERED is protected on this client and is never registered here.
--
-- A window is not shown while the spell is on its OWN cooldown (Revenge after a block it already used): the reactive
-- trigger fires on every block, dodge or parry regardless. It shows once the cooldown ends, if the window is still open.
-- C_Spell.GetSpellCooldown's isActive and isOnGCD are never secret, so this works in combat. The global cooldown does not
-- count: with isOnGCD true, or (where the client leaves it nil) while the GCD spell itself is cooling, it cannot be told
-- apart, so the window stays shown rather than flicker after every cast.
--
-- A spell the player does not know never opens a window. Victory Rush carries a health gate: while the player's health is
-- plainly above hideAboveHealth percent the window is open but not "shown" (the heal is not worth a cue). UnitHealth and
-- UnitHealthMax may be secret in combat: both plain gives the percent, else UnitHealthPercent if its answer is plain, else the
-- gate does not apply and the window is shown. Nothing secret is ever compared.
--
-- The ledger listens from Start() on and never stops: a dodge while the module is hidden (no target) cannot be read back later.
--
-- API: Start(), Refresh(), Subscribe(fn), Unsubscribe(fn), Tick(now), Get(key) -> record, Remaining(key, now),
-- Shown(key, now), Urgent(now) -> key or nil (the shown window with the least time left, ORDER breaks a tie).
-- A listener is called fn(key, reason): "open", "change" (the clock restarted), "ready" (its own cooldown ended while open),
-- "close" (ended early), "cast", "expire", "learn".
-- Record fields: cooling (on its own cooldown: not shown), key, known, id (the rank id we use), localName, open, openAt, expires, length, source ("glow" | "usable" | nil),
-- usable (the last plain read), hidden (the health gate), closedAt, closedWhy ("cast" | "expire" | "glow" | "usable"),
-- shownAtClose (was it shown the moment it closed, so the lane knows whether to play the cast flash or the expiry outline).

local _, FS = ...

FS.WarriorWindows = FS.WarriorWindows or {}
local Windows = FS.WarriorWindows

local IsSecret = FS.IsSecret or function() return false end

local DEFS = {
    -- ids: Classic ranks, highest first. length: Classic value in seconds, unmeasured on Forever.
    overpower = { name = "Overpower", label = "OVERPOWER", ids = { 11585, 11584, 7887, 7384 }, length = 5 },
    revenge = { name = "Revenge", label = "REVENGE", ids = { 30357, 25269, 25288, 11601, 11600, 7379, 6574, 6572 }, length = 5 },
    -- 402927 is the id on Forever (read off a Warrior's action bar, 2026-11-20). 20 s is the Classic value; shown only while health is at or below hideAboveHealth percent (the player's decision)
    victoryrush = { name = "Victory Rush", label = "VICTORY RUSH", ids = { 402927, 34428 }, length = 20, hideAboveHealth = 90 },
}
local ORDER = { "overpower", "revenge", "victoryrush" }
Windows.DEFS, Windows.ORDER = DEFS, ORDER
Windows.POLL = 0.2                 -- seconds between usable and health reads from Tick
Windows.CAST_GRACE = 0.6           -- a cast this soon after a quiet close still counts as the cast

local ID_KEY = {}
local state = {}
for i = 1, #ORDER do
    local key = ORDER[i]
    for _, id in ipairs(DEFS[key].ids) do ID_KEY[id] = key end
    state[key] = { key = key, known = false, open = false, length = DEFS[key].length, hidden = false }
end

local listeners = {}
local started = false
local frame
local lastPoll = -1e9

local function Now() return GetTime() end

local function Notify(key, reason)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], key, reason)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "warriorwindows_listener", "|cffff4488Forever STUwave|r: warrior windows listener: " .. tostring(err))
        end
    end
end

-- pcall that logs once per tag; no closure per call (the event paths run it).
local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "warriorwindows_" .. tag, "|cffff4488Forever STUwave|r: warrior windows " .. tag .. ": " .. tostring(err))
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

-- true when the spellbook says the player knows this spell id (FrameHelpers asks every spellbook API the client has)
local function IsKnownId(id)
    local FH = FS.FrameHelpers
    if FH and FH.IsKnownSpellId then return FH.IsKnownSpellId(id, false) end
    for _, fn in ipairs({ IsPlayerSpell or false, IsSpellKnown or false }) do
        if fn then
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) and r then return true end
        end
    end
    return false
end

-- The window key a spell id belongs to: by id, else by name. A secret or unknown id answers nil.
local function KeyOf(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return nil end
    local hit = ID_KEY[spellID]
    if hit then return hit end
    local name = SpellNameOf(spellID)
    if not name then return nil end
    for i = 1, #ORDER do
        local key = ORDER[i]
        if name == DEFS[key].name or name == state[key].localName then return key end
    end
    return nil
end

-- The player's health as a percent, or nil when it cannot be read as a plain number (never a secret compared).
local function HealthPercent()
    if type(UnitHealth) == "function" and type(UnitHealthMax) == "function" then
        local okH, h = pcall(UnitHealth, "player")
        local okM, m = pcall(UnitHealthMax, "player")
        if okH and okM and not IsSecret(h) and not IsSecret(m) and type(h) == "number" and type(m) == "number" and m > 0 then
            return h / m * 100
        end
    end
    if type(UnitHealthPercent) == "function" then
        local curves = _G.CurveConstants
        local ok, p
        if curves and curves.ScaleTo100 then
            ok, p = pcall(UnitHealthPercent, "player", false, curves.ScaleTo100)
        else
            ok, p = pcall(UnitHealthPercent, "player")
        end
        if ok and not IsSecret(p) and type(p) == "number" then return p end
    end
    return nil
end

-- true / false / nil (cannot tell) for "is the spell usable now"
local function ReadUsable(s)
    local fn = (C_Spell and C_Spell.IsSpellUsable) or IsUsableSpell
    if type(fn) ~= "function" then return nil end
    local ok, usable = pcall(fn, s.id or s.localName or DEFS[s.key].name)
    if not ok or IsSecret(usable) then return nil end
    if type(usable) == "boolean" then return usable end
    if type(usable) == "number" then return usable ~= 0 end
    return nil
end

local GCD_SPELL = 61304            -- the client's global cooldown spell

local function CooldownActive(spell)
    local get = C_Spell and C_Spell.GetSpellCooldown
    if type(get) ~= "function" or spell == nil then return nil, nil end
    local ok, info = pcall(get, spell)
    if not ok or type(info) ~= "table" or IsSecret(info) then return nil, nil end
    local active, gcd = info.isActive, info.isOnGCD
    if IsSecret(active) or type(active) ~= "boolean" then active = nil end
    if IsSecret(gcd) or type(gcd) ~= "boolean" then gcd = nil end
    return active, gcd
end

-- true only when the spell is plainly on its own cooldown; nil and false both mean "may be shown"
local function ReadCooling(s)
    local active, onGCD = CooldownActive(s.id or s.localName or DEFS[s.key].name)
    if not active then return false end
    if onGCD == true then return false end
    if onGCD == nil and CooldownActive(GCD_SPELL) then return false end
    return true
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

function Windows.Get(key) return state[key] end

function Windows.Remaining(key, now)
    local s = state[key]
    if not (s and s.open and s.expires) then return nil end
    local r = s.expires - (now or Now())
    if r < 0 then r = 0 end
    return r
end

-- Is this window one the lane should draw right now: known, open, not run out, not held back by the health gate
-- or the spell's own cooldown.
function Windows.Shown(key, now)
    local s = state[key]
    if not (s and s.known and s.open and s.expires and not s.hidden and not s.cooling) then return false end
    return s.expires > (now or Now())
end

-- The shown window with the least time left (ORDER breaks a tie), or nil. No table is built.
function Windows.Urgent(now)
    now = now or Now()
    local best, bestLeft
    for i = 1, #ORDER do
        local key = ORDER[i]
        if Windows.Shown(key, now) then
            local left = state[key].expires - now
            if not bestLeft or left < bestLeft then best, bestLeft = key, left end
        end
    end
    return best
end

local function GateOf(s)
    local limit = DEFS[s.key].hideAboveHealth
    if not limit then return false end
    local pct = HealthPercent()
    return pct ~= nil and pct > limit
end

local function Open(s, source, now)
    if not s.known then return false end
    local len = DEFS[s.key].length
    s.open, s.openAt, s.expires, s.length, s.source = true, now, now + len, len, source
    s.hidden = GateOf(s)
    s.cooling = ReadCooling(s)
    Notify(s.key, "open")
    return true
end

local function Close(s, why, now)
    s.shownAtClose = s.open and not s.hidden and not s.cooling
    s.open, s.expires, s.source, s.hidden, s.cooling = false, nil, nil, false, false
    s.closedAt, s.closedWhy = now, why
end

local function PollKey(s, now)
    if not s.known then return end
    local r = ReadUsable(s)
    if r ~= nil then
        local last = s.usable
        s.usable = r
        if r then
            if last == false and not s.open then Open(s, "usable", now) end
        elseif last == true and s.open then
            Close(s, "usable", now)
            Notify(s.key, "close")
        end
    end
    if s.open and DEFS[s.key].hideAboveHealth then s.hidden = GateOf(s) end
    if s.open then
        local was = s.cooling
        s.cooling = ReadCooling(s)
        if was and not s.cooling then Notify(s.key, "ready") end
    end
end

local function PollAll(now)
    for i = 1, #ORDER do PollKey(state[ORDER[i]], now) end
end

-- Expiry, then the throttled usable and health reads. The lane's module calls it from its ticker while it is shown.
function Windows.Tick(now)
    now = now or Now()
    for i = 1, #ORDER do
        local s = state[ORDER[i]]
        if s.open and s.expires and s.expires <= now then
            Close(s, "expire", now)
            Notify(s.key, "expire")
        end
    end
    if now - lastPoll >= Windows.POLL then
        lastPoll = now
        PollAll(now)
    end
end

-- Resolve what the player knows (ranks by id, then by name). Known is sticky: a refused read never forgets a spell.
local function Resolve(key)
    local d, s = DEFS[key], state[key]
    local known, id = false, nil
    for i = 1, #d.ids do
        if IsKnownId(d.ids[i]) then known, id = true, d.ids[i]; break end
    end
    local FH = FS.FrameHelpers
    if not known and FH and FH.ResolveSpell then
        local ok, rid = pcall(FH.ResolveSpell, d.name)
        if ok and not IsSecret(rid) and type(rid) == "number" and IsKnownId(rid) then known, id = true, rid end
    end
    s.localName = s.localName or SpellNameOf(id or d.ids[#d.ids])
    if known then
        s.id = id
        if not s.known then
            s.known = true
            return true
        end
    end
    return false
end

function Windows.Refresh()
    local learned = false
    for i = 1, #ORDER do
        if Resolve(ORDER[i]) then learned = true end
    end
    if learned then
        for i = 1, #ORDER do Notify(ORDER[i], "learn") end
    end
    PollAll(Now())
end

local function OnGlow(spellID, shown)
    local key = KeyOf(spellID)
    if not key then return end
    local s, now = state[key], Now()
    if shown then
        if s.open then
            s.expires = now + DEFS[key].length
            Notify(key, "change")
        else
            Open(s, "glow", now)
        end
    elseif s.open then
        Close(s, "glow", now)
        Notify(key, "close")
    end
end

local function OnCast(spellID)
    local key = KeyOf(spellID)
    if not key then return end
    local s, now = state[key], Now()
    if s.open then
        Close(s, "cast", now)
    else
        local recent = s.closedAt and s.closedWhy ~= "cast" and now - s.closedAt <= Windows.CAST_GRACE
        if not recent then return end
        s.closedWhy = "cast"
    end
    Notify(key, "cast")
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP" }

function Windows.Start()
    if started then return end
    started = true
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2, a3)
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            Guard("cast", OnCast, a3)
        elseif event == "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW" then
            Guard("glow", OnGlow, a1, true)
        elseif event == "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE" then
            Guard("glow", OnGlow, a1, false)
        elseif event == "SPELL_UPDATE_USABLE" or event == "SPELL_UPDATE_COOLDOWN" then
            Guard("usable", PollAll, Now())
        else
            Guard("refresh", Windows.Refresh)
        end
    end)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then
        FH.RegisterEvent(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        FH.RegisterEvent(frame, "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW")
        FH.RegisterEvent(frame, "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE")
        FH.RegisterEvent(frame, "SPELL_UPDATE_USABLE")
        FH.RegisterEvent(frame, "SPELL_UPDATE_COOLDOWN")
        if FH.RegisterEvents then FH.RegisterEvents(frame, EVENTS) end
    else
        pcall(frame.RegisterUnitEvent, frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        pcall(frame.RegisterEvent, frame, "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW")
        pcall(frame.RegisterEvent, frame, "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE")
        pcall(frame.RegisterEvent, frame, "SPELL_UPDATE_USABLE")
        pcall(frame.RegisterEvent, frame, "SPELL_UPDATE_COOLDOWN")
        for _, e in ipairs(EVENTS) do pcall(frame.RegisterEvent, frame, e) end
    end
    Guard("refresh", Windows.Refresh)
end

function Windows.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function Windows.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
Windows._state = state
Windows._OnCast = OnCast
Windows._OnGlow = OnGlow
Windows._PollAll = PollAll
