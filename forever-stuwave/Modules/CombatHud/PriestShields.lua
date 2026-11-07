-- Forever STUwave: the Priest's Power Word: Shield and Prayer of Mending, as plain state for the Gunsight Priest module
--
-- FACTS (DEFS below). Power Word: Shield: learned at 6, a 4 s cooldown, 30 s on the unit, and it leaves Weakened Soul (6788,
-- 15 s) on that unit. Prayer of Mending: the Holy talent at 40 (401859 on this client per research), 5 heals, 30 s on each
-- holder, a 10 s cooldown, one per caster. The player's own casts are matched by spell NAME so any rank counts. The 30 s
-- shield, the 30 s jump timer and the 15 s Weakened Soul are the Classic values: UNMEASURED on Forever.
--
-- WHAT THE CLIENT LETS US READ (12.0 engine, see the wow-addon-secret-values notes):
--   * UnitGetTotalAbsorbs is SECRET, always. This file never compares it, does arithmetic on it or formats it: it only hands it
--     out (Absorb(unit)) and keeps one per unit as the "full" mark, the absorb caught right after the player's own Power Word:
--     Shield on that unit (Mark(unit)). The module gives both to a StatusBar (SetMinMaxValues / SetValue accept secrets), to
--     SetAlpha (a gate: 0 is invisible, any absorb is fully shown) and to AbbreviateNumbers -> SetFormattedText.
--   * Auras are plain out of combat and REFUSED under InCombatLockdown: every aura read is gated on FS.AurasReadable() and
--     redone at PLAYER_REGEN_ENABLED (and FS.OnAurasReadable). Out of combat the shield (any priest's), its expiry, Weakened
--     Soul (any priest's) and whose they are (sourceUnit == "player") are the truth (source "aura").
--   * In combat the player's own casts are the clock (source "cast", the module shows "~"): a Power Word: Shield stamps the
--     unit's shield (30 s) and Weakened Soul (15 s); a Prayer of Mending stamps its holder (the cast target), 5 heals and 30 s.
--     A shield or Weakened Soul from another priest in combat is not seen until the next plain read, and no Mending jump is
--     claimed in combat (the holder and heals stay what the cast said).
--   * UNIT_ABSORB_AMOUNT_CHANGED is a plain ping with no amount: it is a "hit" (the module flashes) and, within MARK_WINDOW s of
--     the player's own cast on that unit, the moment the full mark is caught.
--   * The cooldowns' isActive / isOnGCD are never secret (plain flags); the seconds are, so the heart's cooldown shade is the
--     engine's (C_Spell.GetSpellCooldownDuration, handed out by CooldownDuration()).
--
-- WHO A CAST WENT ON (TO PROVE LIVE). UNIT_SPELLCAST_SENT carries the cast's target NAME (conditionally secret): a plain name is
-- matched against the seats (player, party1-4) and the target by UnitName. A secret, missing or unmatched name falls back to
-- what the client would have cast on: the target when the player can assist it, else the player. UNIT_SPELLCAST_SUCCEEDED then
-- stamps the ledger. Units are keyed by plain UnitGUID, else by their seat token.
--
-- The listeners run from Start() on and never stop: a cast while the module is hidden (no target) cannot be read back later.
--
-- API: Start(), Refresh(), Subscribe(fn), Unsubscribe(fn), Tick(now), Watched() -> unit token ("target" or "player"),
-- Shield(unit) -> record or nil, Absorb(unit), Mark(unit), ShieldKnown(), ShieldCooling(), Mending() -> record,
-- MendingCooling(), MendingCooldownDuration(), SeatUnit(i), SEATS. A listener is called fn(reason, unit) with reason "cast" (the
-- player shielded unit), "hit" (an absorb ping on unit), "absorb" (the ping of our own shield landing, or a re-read after a
-- cast), "break" (a plain read saw a shield vanish before its time), "jump" (a plain read saw the Mending holder move),
-- "mending" (the player cast Prayer of Mending), "cooldown", "combat" (combat began), "change", "learn".
-- Shield record: up, expires, est, mine, ws (Weakened Soul up), wsExpires, wsDuration, wsEst, wsMine.
-- Mending record: known, out, holder (seat 1..5 or nil), charges, expires, est, cooling, from, jumpAt.

local _, FS = ...

FS.PriestShields = FS.PriestShields or {}
local Shields = FS.PriestShields

local IsSecret = FS.IsSecret or function() return false end

local DEFS = {
    shield = { name = "Power Word: Shield", ids = { 25218, 25217, 10901, 10900, 10899, 10898, 6066, 6065, 3747, 600, 592, 17 },
        duration = 30, cooldown = 4, level = 6 },
    soul = { name = "Weakened Soul", id = 6788, duration = 15 },
    mending = { name = "Prayer of Mending", ids = { 401859, 48113, 48112, 33076 }, duration = 30, charges = 5, cooldown = 10,
        level = 40 },
}
Shields.DEFS = DEFS
Shields.SEATS = { "player", "party1", "party2", "party3", "party4" }
local SEATS = Shields.SEATS
local MARK_WINDOW = 0.6            -- s after the player's own cast in which an absorb ping is the shield landing
local SENT_WINDOW = 3              -- s a SENT target is held for its SUCCEEDED
local BREAK_SLACK = 0.5            -- a plain read that loses a shield this long before its expiry calls it broken

local records = {}                 -- key (GUID or seat token) -> shield record
local marks = {}                   -- key -> the secret absorb caught after the player's cast
local markOpen = {}                -- key -> GetTime() of the player's cast (the mark window)
local mending = { known = false, out = false, charges = 0 }
local shieldKnown = false
local listeners = {}
local started = false
local frame, unitFrames
local sent = { at = nil, key = nil, unit = nil }

local function Now() return GetTime() end

local function Notify(reason, unit)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason, unit)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "priestshields_listener", "|cffff4488Forever STUwave|r: priest shields listener: " .. tostring(err))
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

local function Call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a, b = pcall(fn, ...)
    if not ok then return nil end
    return a, b
end

local nameCache = {}
local function SpellNameOf(id)
    local hit = nameCache[id]
    if hit then return hit end
    local name = PlainOf(Call(C_Spell and C_Spell.GetSpellName, id), "string")
    if not name then name = PlainOf(Call(GetSpellInfo, id), "string") end
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

-- known (true / false / nil unreadable), the known id, the client's own name
local function ResolveSpell(d)
    local unknown = false
    for _, id in ipairs(d.ids) do
        local k = IsKnownId(id)
        if k == true then return true, id, SpellNameOf(id) end
        if k == nil then unknown = true end
    end
    if unknown then return nil end
    return false
end

local function NameIs(name, d)
    return name == d.name or (d.localName ~= nil and name == d.localName)
end

local function PlainGUID(unit)
    return PlainOf(Call(UnitGUID, unit), "string")
end

local function Exists(unit)
    if unit == "player" then return true end
    local e = Call(UnitExists, unit)
    if IsSecret(e) then return false end
    return e and true or false
end

local function CanAssist(unit)
    local v = Call(UnitCanAssist, "player", unit)
    if IsSecret(v) then return false end
    return v and true or false
end

local function Same(a, b)
    local v = Call(UnitIsUnit, a, b)
    if IsSecret(v) then return false end
    return v and true or false
end

-- The ledger key of a unit: its plain GUID, else the seat it sits in, else nil.
local function KeyOf(unit)
    if not Exists(unit) then return nil end
    local g = PlainGUID(unit)
    if g then return g end
    for i = 1, #SEATS do
        if unit == SEATS[i] or Same(unit, SEATS[i]) then return SEATS[i] end
    end
    return nil
end
Shields.KeyOf = KeyOf

local function SeatOfKey(key)
    if not key then return nil end
    for i = 1, #SEATS do
        if KeyOf(SEATS[i]) == key then return i end
    end
    return nil
end

-------------------------------------------------------------------------------
-- Aura reads (gated on FS.AurasReadable)
-------------------------------------------------------------------------------

local function Readable() return FS.AurasReadable and FS.AurasReadable() or false end

-- the aura table (plain) or false when readably absent; nil unreadable
local function ReadAura(unit, d, filter)
    if not Readable() then return nil end
    local byName = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(byName) ~= "function" then return nil end
    local ok, aura = pcall(byName, unit, d.localName or d.name, filter)
    if not ok or IsSecret(aura) then return nil end
    if type(aura) ~= "table" then return false end
    return aura
end

local function Mine(aura)
    local src = aura.sourceUnit
    if IsSecret(src) or type(src) ~= "string" then return false end
    return src == "player" or Same(src, "player")
end

local function Record(key)
    local r = records[key]
    if not r then
        r = { up = false, ws = false }
        records[key] = r
    end
    return r
end

-- Out of combat: the unit's shield and Weakened Soul from its auras. Returns changed, broke.
local function ReadUnit(unit)
    local key = KeyOf(unit)
    if not key then return false, false end
    local sh = ReadAura(unit, DEFS.shield, "HELPFUL")
    local ws = ReadAura(unit, DEFS.soul, "HARMFUL")
    if sh == nil and ws == nil then return false, false end
    local r, now = Record(key), Now()
    local changed, broke = false, false
    if sh ~= nil then
        local exp = sh and PlainOf(sh.expirationTime, "number")
        if sh then
            local mine = Mine(sh)
            if not r.up or r.expires ~= exp or r.est or r.mine ~= mine then changed = true end
            r.up, r.expires, r.est, r.mine = true, (exp and exp > 0) and exp or nil, false, mine
        else
            if r.up then
                changed = true
                if not r.est and r.expires and now < r.expires - BREAK_SLACK then broke = true end
            end
            r.up, r.expires, r.est, r.mine = false, nil, false, false
        end
    end
    if ws ~= nil then
        if ws then
            local exp, dur = PlainOf(ws.expirationTime, "number"), PlainOf(ws.duration, "number")
            local mine = Mine(ws)
            if not r.ws or r.wsExpires ~= exp or r.wsEst or r.wsMine ~= mine then changed = true end
            r.ws, r.wsExpires, r.wsDuration, r.wsEst, r.wsMine = true, exp, (dur and dur > 0) and dur or DEFS.soul.duration, false, mine
        elseif r.ws then
            changed = true
            r.ws, r.wsExpires, r.wsEst, r.wsMine = false, nil, false, false
        end
    end
    return changed, broke
end

-- Out of combat: who carries the player's Prayer of Mending.
local function ReadMending()
    if not mending.known or not Readable() then return false end
    local holder, charges, exp
    for i = 1, #SEATS do
        local unit = SEATS[i]
        if Exists(unit) then
            local aura = ReadAura(unit, DEFS.mending, "HELPFUL")
            if aura == nil then return false end
            if aura and Mine(aura) then
                holder = i
                charges = PlainOf(aura.applications, "number")
                if not charges or charges < 1 then charges = 1 end
                exp = PlainOf(aura.expirationTime, "number")
                break
            end
        end
    end
    local m = mending
    local was = m.out and m.holder
    if holder then
        local changed = not m.out or m.holder ~= holder or m.charges ~= charges or m.expires ~= exp or m.est
        if was and was ~= holder then m.from, m.jumpAt = was, Now() end
        m.out, m.holder, m.charges, m.expires, m.est = true, holder, charges, (exp and exp > 0) and exp or nil, false
        return changed, was and was ~= holder
    end
    if m.out then
        m.out, m.holder, m.charges, m.expires, m.est = false, nil, 0, nil, false
        return true, false
    end
    return false, false
end

local function ReadCooldown(d)
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if type(fn) ~= "function" then return nil end
    local ok, cd = pcall(fn, d.id or d.localName or d.name)
    if not ok or type(cd) ~= "table" or IsSecret(cd) then return nil end
    local active, gcd = PlainOf(cd.isActive, "boolean"), PlainOf(cd.isOnGCD, "boolean")
    if active == nil then return nil end
    return active and gcd ~= true
end

-------------------------------------------------------------------------------
-- Public reads
-------------------------------------------------------------------------------

-- The unit the big shield watches: a target the player can assist, else the player (an enemy never carries our shield).
function Shields.Watched()
    if Exists("target") and CanAssist("target") then return "target" end
    return "player"
end

function Shields.SeatUnit(i) return SEATS[i] end

function Shields.Shield(unit)
    local key = KeyOf(unit)
    return key and records[key] or nil
end

-- The secret absorb total (or nil). Only for setters.
function Shields.Absorb(unit)
    if type(UnitGetTotalAbsorbs) ~= "function" then return nil end
    local ok, v = pcall(UnitGetTotalAbsorbs, unit)
    if not ok then return nil end
    return v
end

function Shields.Mark(unit)
    local key = KeyOf(unit)
    return key and marks[key] or nil
end

function Shields.ShieldKnown() return shieldKnown end

-- true while the Power Word: Shield cooldown runs (not the global cooldown); false ready; nil unreadable
function Shields.ShieldCooling()
    if not shieldKnown then return false end
    return ReadCooldown(DEFS.shield)
end

function Shields.Mending() return mending end

-- true while the Prayer of Mending cooldown runs (not the global cooldown); false ready; nil unreadable
function Shields.MendingCooling()
    if not mending.known then return false end
    return ReadCooldown(DEFS.mending)
end

-- The engine's duration object of Prayer of Mending's cooldown (for StatusBar:SetTimerDuration), or nil.
function Shields.MendingCooldownDuration()
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    if type(fn) ~= "function" or not mending.known then return nil end
    local ok, obj = pcall(fn, DEFS.mending.id or DEFS.mending.name)
    if not ok then return nil end
    return obj
end

-------------------------------------------------------------------------------
-- Refresh and expiry
-------------------------------------------------------------------------------

local function Learn()
    local changed = false
    local level = PlainOf(Call(UnitLevel, "player"), "number")
    for key, d in pairs({ shield = DEFS.shield, mending = DEFS.mending }) do
        local known, id, name = ResolveSpell(d)
        if known ~= nil then
            if known then d.id, d.localName = id, name or d.localName end
            local was
            if key == "shield" then was = shieldKnown else was = mending.known end
            if was ~= known then
                changed = true
                if key == "shield" then shieldKnown = known else mending.known = known end
            end
        end
    end
    -- a level below the spell's can never know it; never forget a spell on an unreadable book
    if level and level < DEFS.shield.level and shieldKnown then shieldKnown, changed = false, true end
    DEFS.soul.localName = DEFS.soul.localName or SpellNameOf(DEFS.soul.id)
    return changed
end

local function ReadAll()
    local changed, breaks = false, nil
    local seen = {}
    local units = { "target", SEATS[1], SEATS[2], SEATS[3], SEATS[4], SEATS[5] }
    for i = 1, #units do
        local u = units[i]
        local key = KeyOf(u)
        if key and not seen[key] then
            seen[key] = true
            local c, b = ReadUnit(u)
            if c then changed = true end
            if b then breaks = breaks or u end
        end
    end
    local mc, jumped = ReadMending()
    return changed or mc, breaks, jumped
end

-- Always ends with a "change": a refresh comes from an event that may move what the module shows (a new target, the group,
-- combat) even when no aura changed.
function Shields.Refresh()
    local learned = Learn()
    local _, broke, jumped = ReadAll()
    if learned then Notify("learn") end
    if broke then Notify("break", broke) end
    if jumped then Notify("jump") end
    Notify("change")
end

-- Expiry of the clocks the ledger or a read set. Called from the module's ticker.
function Shields.Tick(now)
    now = now or Now()
    local changed = false
    for _, r in pairs(records) do
        if r.up and r.expires and r.expires <= now then r.up, r.expires, r.est = false, nil, false; changed = true end
        if r.ws and r.wsExpires and r.wsExpires <= now then r.ws, r.wsExpires, r.wsEst = false, nil, false; changed = true end
    end
    local m = mending
    if m.out and m.expires and m.expires <= now then
        m.out, m.holder, m.charges, m.expires, m.est = false, nil, 0, nil, false
        changed = true
    end
    if changed then Notify("change") end
end

-------------------------------------------------------------------------------
-- The cast ledger
-------------------------------------------------------------------------------

-- the unit a helpful cast went on, by the SENT target name; else what the client casts a helpful spell on
local function UnitOfName(name)
    if type(name) ~= "string" or IsSecret(name) or name == "" then return nil end
    local units = { "target", SEATS[1], SEATS[2], SEATS[3], SEATS[4], SEATS[5] }
    for i = 1, #units do
        local u = units[i]
        if Exists(u) then
            local n = PlainOf(Call(UnitName, u), "string")
            if n and (n == name or name:sub(1, #n + 1) == n .. "-" or name:sub(1, #n + 1) == n .. " ") then return u end
        end
    end
    return nil
end

local function DefaultUnit()
    return Shields.Watched()
end

local function OnSent(name, spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local spell = SpellNameOf(spellID)
    if not spell or not (NameIs(spell, DEFS.shield) or NameIs(spell, DEFS.mending)) then return end
    local unit = UnitOfName(name) or DefaultUnit()
    sent.at, sent.unit, sent.key = Now(), unit, KeyOf(unit)
end

local function CastUnit(now)
    if sent.at and now - sent.at <= SENT_WINDOW and sent.key then
        local unit, key = sent.unit, sent.key
        sent.at, sent.unit, sent.key = nil, nil, nil
        return unit, key
    end
    local unit = DefaultUnit()
    return unit, KeyOf(unit)
end

local function CatchMark(key, unit)
    local open = markOpen[key]
    if not open or Now() - open > MARK_WINDOW then return false end
    local v = Shields.Absorb(unit)
    if v ~= nil then marks[key] = v end
    return true
end

local function OnCast(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local spell = SpellNameOf(spellID)
    if not spell then return end
    local now = Now()
    if NameIs(spell, DEFS.shield) then
        local unit, key = CastUnit(now)
        shieldKnown = true
        if not key then return end
        local r = Record(key)
        r.up, r.expires, r.est, r.mine = true, now + DEFS.shield.duration, true, true
        r.ws, r.wsExpires, r.wsDuration, r.wsEst, r.wsMine = true, now + DEFS.soul.duration, DEFS.soul.duration, true, true
        markOpen[key] = now
        CatchMark(key, unit)
        Notify("cast", unit)
        if C_Timer and C_Timer.After then
            C_Timer.After(0.15, function()
                CatchMark(key, unit)
                -- out of combat the auras read a moment later: the "~" goes
                local c = ReadUnit(unit)
                Notify(c and "change" or "absorb", unit)
            end)
        end
    elseif NameIs(spell, DEFS.mending) then
        local _, key = CastUnit(now)
        mending.known = true
        local m = mending
        m.out, m.holder, m.charges, m.expires, m.est = true, SeatOfKey(key), DEFS.mending.charges, now + DEFS.mending.duration, true
        m.from, m.jumpAt = nil, nil
        Notify("mending")
        if C_Timer and C_Timer.After then
            C_Timer.After(0.2, function() if ReadMending() then Notify("change") end end)
        end
    end
end

local function OnAbsorb(unit)
    local key = KeyOf(unit)
    if not key then return end
    local landing = CatchMark(key, unit)
    if not marks[key] and not landing then
        -- a shield the player never cast (or one from before a reload): the first absorb seen is its full mark
        local v = Shields.Absorb(unit)
        if v ~= nil then marks[key] = v end
    end
    Notify(landing and "absorb" or "hit", unit)
end

local function OnAura(unit)
    if not Readable() then return end
    local c, broke = ReadUnit(unit)
    local mc, jumped = ReadMending()
    if broke then Notify("break", unit) end
    if jumped then Notify("jump") end
    if c or mc then Notify("change") end
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP",
    "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED", "PLAYER_TARGET_CHANGED", "GROUP_ROSTER_UPDATE", "SPELL_UPDATE_COOLDOWN" }
-- unit events, two units per frame (RegisterUnitEvent takes at most two on older clients)
local UNIT_PAIRS = { { "player", "target" }, { "party1", "party2" }, { "party3", "party4" } }

local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "priestshields_" .. tag, "|cffff4488Forever STUwave|r: priest shields " .. tag .. ": " .. tostring(err))
    end
end

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

function Shields.Start()
    if started then return end
    started = true
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2, a3, a4)
        if event == "UNIT_SPELLCAST_SENT" then
            Guard("sent", OnSent, a2, a4)
        elseif event == "UNIT_SPELLCAST_SUCCEEDED" then
            Guard("cast", OnCast, a3)
        elseif event == "SPELL_UPDATE_COOLDOWN" then
            Notify("cooldown")
        elseif event == "PLAYER_REGEN_DISABLED" then
            Notify("combat")                        -- the empty looks start to nudge; nothing to read
        else
            Guard("refresh", Shields.Refresh)
        end
    end)
    Register(frame, "UNIT_SPELLCAST_SENT", "player")
    Register(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
    unitFrames = {}
    for i, pair in ipairs(UNIT_PAIRS) do
        local f = CreateFrame("Frame")
        f:SetScript("OnEvent", function(_, event, unit)
            if event == "UNIT_ABSORB_AMOUNT_CHANGED" then Guard("absorb", OnAbsorb, unit)
            else Guard("aura", OnAura, unit) end
        end)
        Register(f, "UNIT_AURA", pair[1], pair[2])
        Register(f, "UNIT_ABSORB_AMOUNT_CHANGED", pair[1], pair[2])
        unitFrames[i] = f
    end
    if FS.OnAurasReadable then
        FS.OnAurasReadable(function() Guard("refresh", Shields.Refresh) end)
    end
    Guard("refresh", Shields.Refresh)
end

function Shields.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function Shields.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
Shields._records, Shields._marks, Shields._mending = records, marks, mending
Shields._OnCast, Shields._OnSent, Shields._OnAbsorb, Shields._OnAura = OnCast, OnSent, OnAbsorb, OnAura
