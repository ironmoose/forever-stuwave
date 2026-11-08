-- Forever STUwave: the Mage's freeze, stacks and ward, as plain state for the Gunsight Mage module
--
-- FACTS (DEFS and TUNING below; every number the module guesses with sits in TUNING, because class tuning moves between builds).
-- Frost Nova freezes for up to 8 s (damage can end it early). Fingers of Frost: a Frost hit may make the next two spells hit a
-- frozen target (15 s). Arcane Blast stacks 4 times, 18 s from the FIRST Blast, never refreshed. Scorch builds Fire Vulnerability
-- (5 stacks, 30 s, each Scorch refreshes it). Ice Lance and Fire Blast share one cooldown. Ice Barrier (30 s cooldown) and Mana
-- Shield are the personal absorbs; an Ice Barrier cast also starts a 1 minute damage buff. The player's own casts are matched by
-- spell NAME, so any rank counts, and every spell id below is UNPROBED on this client: a spell is found by id when one is known
-- and by its name otherwise.
--
-- WHAT THE CLIENT LETS US READ (12.0 engine, see the wow-addon-secret-values notes):
--   * UnitGetTotalAbsorbs is SECRET, always. This file never compares it, does arithmetic on it or formats it: it only hands it
--     out (Absorb()) and keeps one as the "full" mark, the absorb caught right after the player's own Ice Barrier or Mana Shield
--     (Mark()). The module gives both to a StatusBar (SetMinMaxValues / SetValue take secrets), to SetAlpha (a gate) and to
--     AbbreviateNumbers -> SetFormattedText.
--   * Auras are plain out of combat and REFUSED under InCombatLockdown: every aura read is gated on FS.AurasReadable() and redone
--     at PLAYER_REGEN_ENABLED (and FS.OnAurasReadable). Out of combat the auras are the truth (source "aura"); in combat the
--     player's own casts are the clock (source "cast", the module shows "~").
--   * Cooldown flags (isActive, isOnGCD) are plain; the seconds are secret, so every refill is the engine's own
--     (C_Spell.GetSpellCooldownDuration, handed out by CooldownDuration()).
--   * GetSpellPowerCost is a plain read of the next Arcane Blast's cost (UNPROVEN in combat).
--
-- WHAT IS A GUESS AND HOW IT IS CORRECTED
--   * Frozen window: from the own Frost Nova cast, 8 s, a guess ("~"); a plain read out of combat of the target is not made (the
--     freeze is a target state the client does not show), so only the clock ends it.
--   * Fingers of Frost (the least certain piece, UNPROVEN LIVE): two signals, whichever the client gives. (1) a spell activation
--     glow on Ice Lance (SPELL_ACTIVATION_OVERLAY_GLOW_SHOW / _HIDE) when the client raises one; (2) a UNIT_AURA on the player
--     within FOTF_WINDOW after an own Frostbolt, which stands for "the proc landed". Charges count down by the own casts that
--     spend one (TUNING.FOTF_SPENDERS), time out after 15 s, and are corrected from a real aura read whenever auras are readable.
--     A guess made in combat is flagged est.
--   * Arcane Blast stacks: counted from the own Blast casts, corrected out of combat from the player's aura.
--   * Clearcasting: in combat only a plain Blast cost that reads 0 (UNPROVEN LIVE; no aura ping, an Arcane Blast changes the
--     player's auras every cast); out of combat the aura. Cleared by the next own cast, set again by the next cost read.
--   * Fire Vulnerability: counted from the own Scorch casts (a Scorch that missed or another mage's is only caught out of
--     combat), corrected out of combat from the target's debuff.
--   * Ward: the up guess (a cast within its minute, or the aura out of combat) only chooses the label and the nudge; whether
--     there is light in it is the engine's, through the absorb. The damage buff ring is a pure ledger of the Ice Barrier cast.
--
-- The listeners run from Start() on and never stop: a cast while the module is hidden (no target) cannot be read back later.
--
-- API: Start(), Refresh(), Subscribe(fn), Unsubscribe(fn), Tick(now), Spec() -> "FROST" | "ARCANE" | "FIRE", Talented(),
-- Known(key) -> true / false / nil, Cooling(key) -> true / false / nil, CooldownDuration(key), MarkKind() -> "lance" | "comet" |
-- nil, WardKind() -> "barrier" | "mana" | nil, Ward(), Buff(), Frozen(), Fingers(), Arcane(), Clearcasting(), Fire(),
-- BlastCost(), RefreshCost(), CastAt(key), Absorb(), Mark(), DEFS, TUNING. A listener is called fn(reason, key) with reason
-- "cast", "hit" (an absorb ping), "absorb" (our own shield landing), "break" (a plain read saw the ward vanish early),
-- "stacks", "fingers", "frozen", "expire", "cooldown", "combat", "change", "learn".

local _, FS = ...

FS.MageState = FS.MageState or {}
local State = FS.MageState

local IsSecret = FS.IsSecret or function() return false end

local TUNING = {
    FROZEN = 8,                          -- s a Frost Nova freeze is shown for
    FOTF_CHARGES = 2,                    -- spells one Fingers of Frost proc covers
    FOTF_DURATION = 15,
    FOTF_WINDOW_MIN = 0.1, FOTF_WINDOW_MAX = 2.0,   -- s after an own Frostbolt in which a player aura change is the proc
    FOTF_SPENDERS = { "frostbolt", "lance", "fireblast" },
    ARCANE_STACKS = 4, ARCANE_DURATION = 18,
    CC_DURATION = 15,
    FIRE_STACKS = 5, FIRE_DURATION = 30,
    WARD_DURATION = 60, BUFF_DURATION = 60,
    MARK_WINDOW = 0.6,                   -- s after the own ward cast in which an absorb ping is the shield landing
    BREAK_SLACK = 0.5,                   -- a plain read that loses the ward this long before its expiry calls it broken
    COST_SOON = 780,                     -- the Blast cost from which the number turns hot (the module colours it)
}
State.TUNING = TUNING

-- ids are the Classic ranks (UNPROBED here); a name is always tried too
local DEFS = {
    nova = { name = "Frost Nova", ids = { 27088, 10230, 6131, 865, 122 } },
    lance = { name = "Ice Lance", ids = {} },
    fireblast = { name = "Fire Blast", ids = { 27079, 27078, 10199, 10197, 8413, 8412, 2138, 2137, 2136 } },
    frostbolt = { name = "Frostbolt", ids = { 27072, 27071, 25304, 10181, 10180, 10179, 8408, 8407, 8406, 7322, 837, 205, 116 } },
    arcaneblast = { name = "Arcane Blast", ids = { 30451 } },
    scorch = { name = "Scorch", ids = { 27074, 27073, 10207, 10206, 10205, 8446, 8445, 8444, 2948 } },
    icebarrier = { name = "Ice Barrier", ids = { 33405, 27134, 13033, 13032, 13031, 11426 } },
    manashield = { name = "Mana Shield", ids = { 27131, 10193, 10192, 10191, 8495, 8494, 1463 } },
}
-- auras read out of combat (names only: the aura ids are unprobed too)
local AURAS = {
    fingers = { name = "Fingers of Frost" }, clearcasting = { name = "Clearcasting" }, blast = { name = "Arcane Blast" },
    vulnerability = { name = "Fire Vulnerability" },
}
State.DEFS, State.AURAS = DEFS, AURAS
local KEYS = { "nova", "lance", "fireblast", "frostbolt", "arcaneblast", "scorch", "icebarrier", "manashield" }
local LEVEL_FOR_TALENTS = 10

local TAB_ORDER = { "ARCANE", "FIRE", "FROST" }   -- the Mage talent tabs, in order
local TAB_WORDS = { ARCANE = "arcane", FIRE = "fire", FROST = "frost" }

local known = {}                       -- key -> true / false (nil = never resolved)
local spec, talented = "FROST", false
local frozen = { up = false }
local fingers = { n = 0 }
local arcane = { stacks = 0 }
local cc = { up = false }
local fire = { stacks = 0 }
local ward = { up = false }
local buff = { expires = nil }
local castAt = {}
local marks, markOpen = nil, nil       -- the secret absorb caught after the own cast, and when the window opened
local boltAt = nil
local cost = nil
local listeners = {}
local started = false
local frame, unitFrame

local function Now() return GetTime() end

local function Notify(reason, key)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason, key)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "magestate_listener", "|cffff4488Forever STUwave|r: mage state listener: " .. tostring(err))
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

-- known (true / false / nil unreadable), the known id, the client's own name. A name is tried after the ids: the client hands
-- out a spell's id for the name of a spell in the player's book.
local function ResolveSpell(d)
    local unknown = false
    for _, id in ipairs(d.ids) do
        local k = IsKnownId(id)
        if k == true then return true, id, SpellNameOf(id) end
        if k == nil then unknown = true end
    end
    local info = Call(C_Spell and C_Spell.GetSpellInfo, d.name)
    local id = type(info) == "table" and not IsSecret(info) and PlainOf(info.spellID, "number") or nil
    if id then
        local k = IsKnownId(id)
        if k == true then return true, id, PlainOf(info.name, "string") or d.name end
        if k == nil then unknown = true end
    end
    if unknown then return nil end
    return false
end

local function NameIs(name, d)
    return name == d.name or (d.localName ~= nil and name == d.localName)
end

local function KeyOfSpell(name)
    if not name then return nil end
    for i = 1, #KEYS do
        if NameIs(name, DEFS[KEYS[i]]) then return KEYS[i] end
    end
    return nil
end

local function Same(a, b)
    local v = Call(UnitIsUnit, a, b)
    if IsSecret(v) then return false end
    return v and true or false
end

local function Level()
    return PlainOf(Call(UnitLevel, "player"), "number")
end

-------------------------------------------------------------------------------
-- Aura reads (gated on FS.AurasReadable)
-------------------------------------------------------------------------------

local function Readable() return FS.AurasReadable and FS.AurasReadable() or false end

-- the aura table (plain) or false when readably absent; nil unreadable
local function ReadAura(unit, name, filter)
    if not Readable() then return nil end
    local byName = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(byName) ~= "function" then return nil end
    local ok, aura = pcall(byName, unit, name, filter)
    if not ok or IsSecret(aura) then return nil end
    if type(aura) ~= "table" then return false end
    return aura
end

local function ExpiryOf(aura)
    local exp = PlainOf(aura.expirationTime, "number")
    return (exp and exp > 0) and exp or nil
end

-------------------------------------------------------------------------------
-- Spec, spells
-------------------------------------------------------------------------------

-- the points spent in each Mage tab, {ARCANE, FIRE, FROST} order; nil when the client shows none
local function TabPoints()
    local pts, names = {}, {}
    local specFn = C_SpecializationInfo and C_SpecializationInfo.GetSpecializationInfo
    local tabFn = GetTalentTabInfo
    for i = 1, 3 do
        local name, points
        if type(specFn) == "function" then
            local ok, _, n, _, _, _, _, p = pcall(specFn, i)
            if ok then name, points = PlainOf(n, "string"), PlainOf(p, "number") end
        end
        if points == nil and type(tabFn) == "function" then
            local ok, a, b, c, d, e = pcall(tabFn, i)
            if ok then
                -- Classic layout: name, icon, points. Retail layout: id, name, description, icon, points.
                if type(a) == "number" and type(b) == "string" then name, points = b, PlainOf(e, "number")
                else name, points = PlainOf(a, "string"), PlainOf(c, "number") end
            end
        end
        if points == nil then return nil end
        pts[i], names[i] = points, name
    end
    return pts, names
end

local function PickSpec()
    local pts, names = TabPoints()
    if not pts then return nil end
    local best, bestPts, total = nil, 0, 0
    for i = 1, 3 do
        total = total + pts[i]
        if pts[i] > bestPts then best, bestPts = i, pts[i] end
    end
    if not best then return "FROST", 0 end
    local key = TAB_ORDER[best]
    local nm = names[best]
    if nm then
        local lower = nm:lower()
        for k, word in pairs(TAB_WORDS) do
            if lower:find(word, 1, true) then key = k break end
        end
    end
    return key, total
end

local function Learn()
    local changed = false
    for _, key in ipairs(KEYS) do
        local d = DEFS[key]
        local k, id, name = ResolveSpell(d)
        if k ~= nil then
            if k then d.id, d.localName = id, name or d.localName end
            if known[key] ~= k then known[key] = k; changed = true end
        end
    end
    local level = Level()
    local s, total = PickSpec()
    if s then
        local t = total > 0
        if spec ~= s or talented ~= t then spec, talented, changed = s, t, true end
    end
    if level and level < LEVEL_FOR_TALENTS and talented then talented, changed = false, true end
    return changed
end

function State.Spec() return spec end
function State.Talented() return talented end
function State.Known(key) return known[key] end

function State.MarkKind()
    if spec == "ARCANE" then return nil end
    if spec == "FROST" and known.lance == true then return "lance" end
    if known.fireblast == true then return "comet" end
    return nil
end

function State.WardKind()
    if known.icebarrier == true then return "barrier" end
    if known.manashield == true then return "mana" end
    return nil
end

local function ReadCooldown(d)
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if type(fn) ~= "function" then return nil end
    local ok, c = pcall(fn, d.id or d.localName or d.name)
    if not ok or type(c) ~= "table" or IsSecret(c) then return nil end
    local active, gcd = PlainOf(c.isActive, "boolean"), PlainOf(c.isOnGCD, "boolean")
    if active == nil then return nil end
    return active and gcd ~= true
end

-- true while the spell's own cooldown runs (not the global cooldown); false ready; nil unreadable
function State.Cooling(key)
    if known[key] ~= true then return false end
    return ReadCooldown(DEFS[key])
end

-- the engine's duration object of a spell's cooldown (for StatusBar:SetTimerDuration), or nil
function State.CooldownDuration(key)
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    if type(fn) ~= "function" or known[key] ~= true then return nil end
    local d = DEFS[key]
    local ok, obj = pcall(fn, d.id or d.localName or d.name)
    if not ok then return nil end
    return obj
end

function State.CastAt(key) return castAt[key] end
function State.Frozen() return frozen end
function State.Fingers() return fingers end
function State.Arcane() return arcane end
function State.Clearcasting() return cc end
function State.Fire() return fire end
function State.Ward() return ward end
function State.Buff() return buff end

-- The next Arcane Blast's mana cost, a plain read cached by RefreshCost (the engine hands the cost back in a fresh table).
function State.BlastCost() return cost end

-- Clearcasting from the cost: a Blast that costs nothing means the next one is free. Only in combat, where it is the one
-- signal (an estimate); out of combat the aura read is the truth (ReadClearcasting). UNPROVEN LIVE: that GetSpellPowerCost
-- drops to 0 under Clearcasting. Returns whether the Clearcasting state changed.
local function CostSignal(now)
    if spec ~= "ARCANE" or cost == nil or Readable() then return false end
    if cost == 0 then
        if cc.up then return false end
        cc.up, cc.expires, cc.est, cc.at = true, now + TUNING.CC_DURATION, true, now
        return true
    end
    if cc.up and cc.est then
        cc.up, cc.expires, cc.est = false, nil, false
        return true
    end
    return false
end

local function ReadCost()
    local d = DEFS.arcaneblast
    local fn = C_Spell and C_Spell.GetSpellPowerCost
    if type(fn) ~= "function" or known.arcaneblast ~= true then cost = nil return end
    local ok, costs = pcall(fn, d.id or d.localName or d.name)
    if not ok or IsSecret(costs) or type(costs) ~= "table" then cost = nil return end
    local mana = _G.Enum and _G.Enum.PowerType and _G.Enum.PowerType.Mana or 0
    local first
    for i = 1, #costs do
        local c = costs[i]
        if type(c) == "table" and not IsSecret(c) then
            local v = PlainOf(c.cost, "number")
            if v ~= nil then
                if c.type == mana then cost = v return end
                first = first or v
            end
        end
    end
    cost = first
end

function State.RefreshCost()
    ReadCost()
    if CostSignal(Now()) then Notify("change") end
end

-- The secret absorb of the player (or nil), and the one caught right after the own ward cast. Only for setters.
function State.Absorb()
    if type(UnitGetTotalAbsorbs) ~= "function" then return nil end
    local ok, v = pcall(UnitGetTotalAbsorbs, "player")
    if not ok then return nil end
    return v
end

function State.Mark() return marks end

-------------------------------------------------------------------------------
-- Out of combat: the auras are the truth
-------------------------------------------------------------------------------

local function ReadBlast()
    local aura = ReadAura("player", AURAS.blast.name, "HARMFUL")
    if aura == false then aura = ReadAura("player", AURAS.blast.name, "HELPFUL") end
    if aura == nil then return false end
    local n = aura and (PlainOf(aura.applications, "number") or 1) or 0
    local exp = aura and ExpiryOf(aura) or nil
    if n > TUNING.ARCANE_STACKS then n = TUNING.ARCANE_STACKS end
    local a = arcane
    local changed = a.stacks ~= n or a.est or (n > 0 and a.expires ~= exp)
    a.stacks, a.expires, a.est = n, n > 0 and exp or nil, false
    return changed
end

local function ReadFire()
    local aura = ReadAura("target", AURAS.vulnerability.name, "HARMFUL")
    if aura == nil then return false end
    local n = aura and (PlainOf(aura.applications, "number") or 1) or 0
    local exp = aura and ExpiryOf(aura) or nil
    if n > TUNING.FIRE_STACKS then n = TUNING.FIRE_STACKS end
    local f = fire
    local changed = f.stacks ~= n or f.est or (n > 0 and f.expires ~= exp)
    f.stacks, f.expires, f.est = n, n > 0 and exp or nil, false
    return changed
end

local function ReadFingers()
    local aura = ReadAura("player", AURAS.fingers.name, "HELPFUL")
    if aura == nil then return false end
    local n = aura and (PlainOf(aura.applications, "number") or TUNING.FOTF_CHARGES) or 0
    if n > TUNING.FOTF_CHARGES then n = TUNING.FOTF_CHARGES end
    local exp = aura and ExpiryOf(aura) or nil
    local changed = fingers.n ~= n or fingers.est
    fingers.n, fingers.expires, fingers.est = n, n > 0 and exp or nil, false
    return changed
end

local function ReadClearcasting()
    local aura = ReadAura("player", AURAS.clearcasting.name, "HELPFUL")
    if aura == nil then return false end
    local up = aura and true or false
    local changed = cc.up ~= up or cc.est
    cc.up, cc.expires, cc.est = up, up and ExpiryOf(aura) or nil, false
    return changed
end

-- the ward's aura: the first of the two shields that is up. Returns changed, broke.
local function ReadWard()
    local aura, kind = ReadAura("player", DEFS.icebarrier.localName or DEFS.icebarrier.name, "HELPFUL"), "barrier"
    if aura == false then aura, kind = ReadAura("player", DEFS.manashield.localName or DEFS.manashield.name, "HELPFUL"), "mana" end
    if aura == nil then return false, false end
    local w, now = ward, Now()
    local changed, broke = false, false
    if aura then
        local exp = ExpiryOf(aura)
        if not w.up or w.expires ~= exp or w.est or w.kind ~= kind then changed = true end
        w.up, w.kind, w.expires, w.est = true, kind, exp, false
    elseif w.up then
        changed = true
        if not w.est and w.expires and now < w.expires - TUNING.BREAK_SLACK then broke = true end
        w.up, w.expires, w.est = false, nil, false
    end
    return changed, broke
end

local function ReadAll()
    local changed = false
    local a, b = ReadBlast(), ReadFire()
    local c, d = ReadFingers(), ReadClearcasting()
    local w, broke = ReadWard()
    if a or b or c or d or w then changed = true end
    return changed, broke
end

-- Always ends with a "change": a refresh comes from an event that may move what the module shows (a new target, combat, a spec
-- change) even when no aura changed.
function State.Refresh()
    local learned = Learn()
    local _, broke = ReadAll()
    State.RefreshCost()
    if learned then Notify("learn") end
    if broke then Notify("break") end
    Notify("change")
end

-- Expiry of the clocks the ledger or a read set. Called from the module's ticker.
function State.Tick(now)
    now = now or Now()
    local changed = false
    if frozen.up and frozen.expires <= now then frozen.up, frozen.expires = false, nil; changed = true end
    if fingers.n > 0 and fingers.expires and fingers.expires <= now then fingers.n, fingers.expires = 0, nil; changed = true end
    if cc.up and cc.expires and cc.expires <= now then cc.up, cc.expires = false, nil; changed = true end
    if arcane.stacks > 0 and arcane.expires and arcane.expires <= now then
        arcane.stacks, arcane.expires, arcane.est = 0, nil, false
        arcane.shatterAt = now
        changed = true
        Notify("expire", "arcane")
    end
    if fire.stacks > 0 and fire.expires and fire.expires <= now then fire.stacks, fire.expires, fire.est = 0, nil, false; changed = true end
    if ward.up and ward.expires and ward.expires <= now then ward.up, ward.expires, ward.est = false, nil, false; changed = true end
    if buff.expires and buff.expires <= now then buff.expires = nil; changed = true end
    if boltAt and now - boltAt > TUNING.FOTF_WINDOW_MAX then boltAt = nil end
    if changed then Notify("change") end
end

-------------------------------------------------------------------------------
-- The cast ledger
-------------------------------------------------------------------------------

local function CatchMark()
    local open = markOpen
    if not open or Now() - open > TUNING.MARK_WINDOW then return false end
    local v = State.Absorb()
    if v ~= nil then marks = v end
    return true
end

local function GiveFingers(now, why)
    fingers.n, fingers.expires, fingers.est, fingers.at = TUNING.FOTF_CHARGES, now + TUNING.FOTF_DURATION, not Readable(), now
    Notify("fingers", why)
end

local function SpendFingers(key)
    if fingers.n <= 0 then return end
    for i = 1, #TUNING.FOTF_SPENDERS do
        if TUNING.FOTF_SPENDERS[i] == key then
            fingers.n = fingers.n - 1
            if fingers.n <= 0 then fingers.n, fingers.expires = 0, nil end
            Notify("fingers", "spend")
            return
        end
    end
end

local function OnCast(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local spell = SpellNameOf(spellID)
    local key = KeyOfSpell(spell)
    if not key then return end
    local now = Now()
    castAt[key] = now
    if known[key] ~= true then known[key] = true end
    if cc.up then cc.up, cc.expires, cc.est = false, nil, false end    -- the next cast spends a Clearcasting
    if key == "nova" then
        frozen.up, frozen.expires, frozen.est = true, now + TUNING.FROZEN, true
        Notify("frozen")
    elseif key == "lance" or key == "fireblast" then
        castAt.mark = now
        SpendFingers(key)
        Notify("cast", key)
    elseif key == "frostbolt" then
        SpendFingers(key)
        boltAt = now
        Notify("cast", key)
    elseif key == "arcaneblast" then
        local a = arcane
        if a.stacks == 0 then a.expires = now + TUNING.ARCANE_DURATION end
        a.stacks = a.stacks + 1
        if a.stacks > TUNING.ARCANE_STACKS then a.stacks = TUNING.ARCANE_STACKS end
        a.est, a.popAt, a.shatterAt = true, now, nil
        boltAt = now
        if C_Timer and C_Timer.After then C_Timer.After(0.15, State.RefreshCost) else State.RefreshCost() end
        Notify("stacks", key)
    elseif key == "scorch" then
        local f = fire
        f.stacks = f.stacks + 1
        if f.stacks > TUNING.FIRE_STACKS then f.stacks = TUNING.FIRE_STACKS end
        f.expires, f.est, f.popAt = now + TUNING.FIRE_DURATION, true, now
        Notify("stacks", key)
    elseif key == "icebarrier" or key == "manashield" then
        local w = ward
        w.up, w.kind, w.expires, w.est = true, key == "icebarrier" and "barrier" or "mana", now + TUNING.WARD_DURATION, true
        if key == "icebarrier" then buff.expires = now + TUNING.BUFF_DURATION end
        markOpen = now
        CatchMark()
        Notify("cast", key)
        if C_Timer and C_Timer.After then
            C_Timer.After(0.15, function()
                CatchMark()
                -- out of combat the aura reads a moment later: the "~" goes
                local c = ReadWard()
                Notify(c and "change" or "absorb", key)
            end)
        end
    else
        Notify("cast", key)
    end
end

-- a plain window signal: an aura changed on the player soon after an own Frostbolt, which stands for "Fingers of Frost
-- landed" (an Arcane Blast changes the player's auras every cast, so it cannot be a Clearcasting signal)
local function OnPlayerAura(info)
    local now = Now()
    if not boltAt then return end
    local dt = now - boltAt
    if dt < TUNING.FOTF_WINDOW_MIN or dt > TUNING.FOTF_WINDOW_MAX then return end
    if type(info) == "table" and not IsSecret(info) then
        local added = info.addedAuras
        local updated = info.updatedAuraInstanceIDs
        local has = (type(added) == "table" and #added > 0) or (type(updated) == "table" and #updated > 0)
        if not has then return end
    end
    boltAt = nil
    if spec == "FROST" and talented then GiveFingers(now, "aura") end
end

local function OnAura(unit, info)
    if unit ~= "player" then return end
    if Readable() then
        local c, broke = ReadAll()
        State.RefreshCost()
        if broke then Notify("break") end
        if c then Notify("change") end
        return
    end
    OnPlayerAura(info)
end

local function OnGlow(spellID, shown)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local key = KeyOfSpell(SpellNameOf(spellID))
    if key ~= "lance" then return end
    if shown then
        GiveFingers(Now(), "glow")
    elseif fingers.n > 0 then
        fingers.n, fingers.expires = 0, nil
        Notify("fingers", "glow")
    end
end

local function OnAbsorb(unit)
    if unit ~= "player" and not Same(unit, "player") then return end
    local landing = CatchMark()
    if not marks and not landing then
        -- a shield the player never cast (or one from before a reload): the first absorb seen is its full mark
        local v = State.Absorb()
        if v ~= nil then marks = v end
    end
    Notify(landing and "absorb" or "hit")
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_REGEN_ENABLED",
    "PLAYER_REGEN_DISABLED", "PLAYER_TARGET_CHANGED", "SPELL_UPDATE_COOLDOWN", "PLAYER_TALENT_UPDATE", "CHARACTER_POINTS_CHANGED",
    "ACTIVE_TALENT_GROUP_CHANGED", "TRAIT_CONFIG_UPDATED" }

local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "magestate_" .. tag, "|cffff4488Forever STUwave|r: mage state " .. tag .. ": " .. tostring(err))
    end
end

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

function State.Start()
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
        elseif event == "SPELL_UPDATE_COOLDOWN" then
            Notify("cooldown")
        elseif event == "PLAYER_REGEN_DISABLED" then
            Notify("combat")                         -- the empty looks start to nudge; nothing to read
        elseif event == "PLAYER_TARGET_CHANGED" then
            Guard("refresh", State.Refresh)
        else
            Guard("refresh", State.Refresh)
        end
    end)
    Register(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
    Register(frame, "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW")
    Register(frame, "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
    unitFrame = CreateFrame("Frame")
    unitFrame:SetScript("OnEvent", function(_, event, unit, info)
        if event == "UNIT_ABSORB_AMOUNT_CHANGED" then Guard("absorb", OnAbsorb, unit)
        else Guard("aura", OnAura, unit, info) end
    end)
    Register(unitFrame, "UNIT_AURA", "player")
    Register(unitFrame, "UNIT_ABSORB_AMOUNT_CHANGED", "player")
    if FS.OnAurasReadable then
        FS.OnAurasReadable(function() Guard("refresh", State.Refresh) end)
    end
    Guard("refresh", State.Refresh)
end

function State.Subscribe(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #listeners do if listeners[i] == fn then return end end
    listeners[#listeners + 1] = fn
end

function State.Unsubscribe(fn)
    for i = #listeners, 1, -1 do
        if listeners[i] == fn then table.remove(listeners, i) end
    end
end

-- for the harness
State._OnCast, State._OnAura, State._OnGlow, State._OnAbsorb = OnCast, OnAura, OnGlow, OnAbsorb
