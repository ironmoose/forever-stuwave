-- Forever STUwave: the Druid's data for the Gunsight Class Module (GunsightDruid.lua): the form, the Eclipse ledger, the Lacerate
-- ledger, the heal over time ledger, the cooldown flags.
--
-- WHAT IS READ AND WHAT IS A LEDGER. In combat this client hands an addon SECRET values for current power, auras and cooldown
-- seconds. So nothing here compares a secret. What is plain: the player's own UNIT_SPELLCAST_SUCCEEDED spell id (and its name),
-- the cooldown flags isActive / isOnGCD, the form (UnitPowerType token, GetShapeshiftFormID), UnitLevel, target names, and
-- C_Spell.GetSpellCooldownDuration (an object handed to the engine, never read). Everything with a number of seconds below is
-- therefore a LEDGER: a guess built from our own casts, shown with a "~" by the module.
--   * Eclipse: Wrath banks 2 charges, Starfire spends 1, cap 4, all gone 15 s after the last grant (research doc "Druid stock-UI
--     pain points", wowfdb Balance rotation). A miss banks nothing but SUCCEEDED fires on the cast, so the ledger can over count.
--   * Lacerate: +1 stack per cast on the target, cap 5, 15 s refreshed per cast (Forever tuning, Nov 3 patch notes).
--   * Rejuvenation 12 s, Regrowth 21 s, per target NAME (a GUID can be secret in an instance, a name is not).
--   * Shifting Power 8 s, Primal Bite 6 s, Swiftmend 15 s: the module shows the engine's cooldown object; these are the
--     fallback seconds when no object is available.
--   * Thorns (the caster's Bramble Wreath): out of combat, while FS.AurasReadable(), the player's own aura by NAME is the truth
--     (its plain expirationTime; a readably absent aura is "gone"). In combat the time is a ledger: our own Thorns cast lands on
--     the player (UNIT_SPELLCAST_SENT names the target: an empty, secret or own name, or a target that is not a friend we can
--     help, is the player; the client casts Thorns on you then) and lasts THORNS_SECONDS (600: "Lasts 10 min", Forever's rank 1
--     tooltip); shown with "~". A reload in combat with no cast seen leaves it "unknown" (nothing drawn) until a read or a cast.
-- Every number is in TUNING / DEFS below and UNVERIFIED on the live client (the Forever tuning moves with class patches).
--
-- The ledger listens from Start() on and never stops: a cast while the module is hidden (no target) cannot be read back later.
-- API: Start(), Subscribe(fn(reason)), Unsubscribe(fn), Refresh(), Kind() -> "moon" | "cat" | "bear" | "tree" | "travel",
-- Eclipse(now) -> mode, charges, left, Lacerate(now) -> stacks, left, Hot(key, now) -> left or nil, Stamp(key), Known(key),
-- Cooldown(key) -> "ready" | "cool" | "none" | nil, Duration(key), Tick(now), Friendly(),
-- Thorns(now) -> mode ("up" | "gone" | "unknown"), seconds left (up only), est (a ledger time), castAt (our own cast's GetTime()).

local _, FS = ...

local State = {}
FS.DruidState = State

local IsSecret = FS.IsSecret or function() return false end

-- one place for every tunable number (sources in the header)
local TUNING = {
    ECLIPSE_SECONDS = 15, ECLIPSE_MAX = 4, WRATH_GRANTS = 2, STARFIRE_SPENDS = 1, ECLIPSE_LEVEL = 30,
    UNKNOWN_SECONDS = 15,                          -- after a reload in combat the banked charges are unknown for this long
    LACERATE_SECONDS = 15, LACERATE_MAX = 5,
    REJUV_SECONDS = 12, REGROWTH_SECONDS = 21,
    SHIFT_CD = 8, BITE_CD = 6, SWIFTMEND_CD = 15,  -- fallback only
    ENERGY_NOTCH = 55,                             -- Shifting Power: use it under this much energy (Method, wowfdb)
    RAGE_LACERATE = 15, RAGE_BITE = 20, RAGE_MAUL = 35,   -- the ability ticks under the rage bar (Method, SixtySim)
    BLOOM_WINDOW = 1.5,                            -- a HoT that runs out by itself blooms
    THORNS_SECONDS = 600,                          -- Thorns rank 1 tooltip on Forever: "Lasts 10 min"
    THORNS_REREAD = 0.2,                           -- s after an own cast out of combat before the aura is read back
}
State.TUNING = TUNING

-- spell NAME (any rank) to the ledger key; names are the truth on Forever, ids are not probed
local DEFS = {
    ["wrath"] = "wrath", ["starfire"] = "starfire",
    ["rejuvenation"] = "rejuv", ["regrowth"] = "regrow", ["swiftmend"] = "swift",
    ["lacerate"] = "lacerate", ["primal bite"] = "bite",
    ["rip"] = "finisher", ["ferocious bite"] = "finisher",
    ["shifting power"] = "shift",
    ["thorns"] = "thorns",
}
local SPELLS = { shift = "Shifting Power", bite = "Primal Bite", swift = "Swiftmend", rejuv = "Rejuvenation", regrow = "Regrowth",
    lacerate = "Lacerate", maul = "Maul", thorns = "Thorns" }
State.DEFS, State.SPELLS = DEFS, SPELLS

local TRAVEL = { [3] = true, [4] = true, [27] = true, [29] = true }     -- travel, aquatic, flight forms

local started = false
local frame
local listeners = {}
local eclipse = { charges = 0, at = nil, seen = false }
local lace = { stacks = 0, at = nil, name = nil }
local hots = {}                                     -- target name -> { rejuv = expires, regrow = expires, swift = nil }
local stamp = { grantAt = nil, spendAt = nil, finisherAt = nil, biteAt = nil, lacAt = nil, shiftAt = nil, bloomAt = nil, shiftCastAt = nil, swiftAt = nil }
local form = "caster"
local level = nil                                  -- the player's level, re-read at refresh (a plain number or nil)
local unknownUntil = nil
local known = {}
local cdCache = {}
-- Thorns on the player: expires (GetTime()) or nil; read = a plain read or our own cast has said something since login
local thorns = { expires = nil, est = false, castAt = nil, read = false, up = false }
local sentSelf = true                               -- where the last UNIT_SPELLCAST_SENT pointed (true = the player)

local function Now() return GetTime() end

local function Notify(reason)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "druidstate_listener", "|cffff4488Forever STUwave|r: druid state listener: " .. tostring(err))
        end
    end
end

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
    if type(id) ~= "number" or IsSecret(id) then return nil end
    local hit = nameCache[id]
    if hit then return hit end
    local name = PlainOf(Call(C_Spell and C_Spell.GetSpellName, id), "string")
    if not name then name = PlainOf(Call(GetSpellInfo, id), "string") end
    if name then nameCache[id] = name end
    return name
end

local function TargetName()
    local n = PlainOf(Call(UnitName, "target"), "string")
    return n
end

-------------------------------------------------------------------------------
-- Form and target
-------------------------------------------------------------------------------

local function ReadForm()
    local fn = UnitPowerType
    if type(fn) == "function" then
        local ok, powerType, token = pcall(fn, "player")
        if ok and not IsSecret(powerType) and not IsSecret(token) then
            if token == "ENERGY" or powerType == 3 then return "cat" end
            if token == "RAGE" or powerType == 1 then return "bear" end
        end
    end
    local id = PlainOf(Call(GetShapeshiftFormID), "number")
    if id and TRAVEL[id] then return "travel" end
    return "caster"
end

-- true when the target is a friend we could help and not attack (a plain read of each; unreadable is not a friend)
function State.Friendly()
    if type(UnitExists) ~= "function" then return false end
    local ex = Call(UnitExists, "target")
    if IsSecret(ex) or not ex then return false end
    local canAttack = Call(UnitCanAttack, "player", "target")
    local canAssist = Call(UnitCanAssist, "player", "target")
    if IsSecret(canAttack) or IsSecret(canAssist) then return false end
    return (canAssist and not canAttack) and true or false
end

-- the look: the eyes and the gauge follow it
function State.Kind()
    if form == "cat" then return "cat" end
    if form == "bear" then return "bear" end
    if form == "travel" then return "travel" end
    return State.Friendly() and "tree" or "moon"
end

function State.Form() return form end

-------------------------------------------------------------------------------
-- Ledgers
-------------------------------------------------------------------------------

function State.Stamp(key) return stamp[key] end

-- "locked" below the Eclipse level, "unknown" right after a reload in combat until a cast tells the truth, else "ok"
function State.Eclipse(now)
    if level and level < TUNING.ECLIPSE_LEVEL then return "locked", 0, 0 end
    if unknownUntil and now < unknownUntil and not eclipse.seen then return "unknown", 0, 0 end
    if eclipse.at == nil or eclipse.charges <= 0 then return "ok", 0, 0 end
    local left = eclipse.at + TUNING.ECLIPSE_SECONDS - now
    if left <= 0 then return "ok", 0, 0 end
    return "ok", eclipse.charges, left
end

function State.Lacerate(now)
    if lace.at == nil or lace.stacks <= 0 then return 0, 0 end
    local here = TargetName()
    if here and lace.name and here ~= lace.name then return 0, 0 end
    local left = lace.at + TUNING.LACERATE_SECONDS - now
    if left <= 0 then return 0, 0 end
    return lace.stacks, left
end

-- seconds left on our own HoT on the current target, or nil
function State.Hot(key, now)
    local name = TargetName()
    local rec = name and hots[name]
    local exp = rec and rec[key]
    if not exp then return nil end
    local left = exp - now
    if left <= 0 then return nil end
    return left
end

local function Readable() return FS.AurasReadable and FS.AurasReadable() or false end

-- The player's Thorns aura, out of combat only. Returns whether anything changed.
local function ReadThorns()
    if not Readable() then return false end
    local byName = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(byName) ~= "function" then return false end
    local ok, aura = pcall(byName, "player", SPELLS.thorns, "HELPFUL")
    if not ok or IsSecret(aura) then return false end
    local th = thorns
    local exp, up = nil, false
    if type(aura) == "table" then
        local e = PlainOf(aura.expirationTime, "number")
        up = true
        if e and e > 0 then exp = e end
    end
    local changed = th.up ~= up or th.expires ~= exp or th.est or not th.read
    th.up, th.expires, th.est, th.read = up, exp, false, true
    return changed
end

-- read the aura again (out of combat) and tell the listeners when it changed
function State.RereadThorns()
    if ReadThorns() then Notify("thorns") end
end

function State.Thorns(now)
    local th = thorns
    if not th.read then return "unknown", nil, false, th.castAt end
    if not th.up then return "gone", nil, false, th.castAt end
    if th.expires == nil then return "up", TUNING.THORNS_SECONDS, th.est, th.castAt end   -- an aura with no end time
    local left = th.expires - now
    if left <= 0 then return "gone", nil, false, th.castAt end
    if left > TUNING.THORNS_SECONDS then left = TUNING.THORNS_SECONDS end
    return "up", left, th.est, th.castAt
end

-- UNIT_SPELLCAST_SENT: (unit, target name, castGUID, spellID). Only a plain other name on a friend we can help is not the player.
local function OnSent(target)
    local own = PlainOf(Call(UnitName, "player"), "string")
    local name = PlainOf(target, "string")
    if name == nil or name == "" or name == own then sentSelf = true return end
    local here = TargetName()
    sentSelf = not (here == name and State.Friendly())
end

local function OnCast(spellID)
    local name = SpellNameOf(spellID)
    local key = name and DEFS[string.lower(name)]
    if not key then return end
    local now = Now()
    if key == "thorns" then
        if sentSelf then
            local th = thorns
            th.up, th.expires, th.est, th.read, th.castAt = true, now + TUNING.THORNS_SECONDS, true, true, now
            if Readable() and C_Timer and C_Timer.After then
                C_Timer.After(TUNING.THORNS_REREAD, State.RereadThorns)
            end
        end
        sentSelf = true
        Notify("cast")
        return
    end
    if key == "wrath" then
        eclipse.charges = math.min(TUNING.ECLIPSE_MAX, ((eclipse.at and now < eclipse.at + TUNING.ECLIPSE_SECONDS) and eclipse.charges or 0) + TUNING.WRATH_GRANTS)
        eclipse.at, eclipse.seen = now, true
        stamp.grantAt = now
    elseif key == "starfire" then
        if eclipse.at and now < eclipse.at + TUNING.ECLIPSE_SECONDS and eclipse.charges > 0 then
            eclipse.charges = eclipse.charges - TUNING.STARFIRE_SPENDS
            stamp.spendAt = now
        end
        eclipse.seen = true
    elseif key == "lacerate" then
        local here = TargetName()
        local same = lace.at and now < lace.at + TUNING.LACERATE_SECONDS and (here == nil or lace.name == nil or lace.name == here)
        lace.stacks = math.min(TUNING.LACERATE_MAX, (same and lace.stacks or 0) + 1)
        lace.at, lace.name = now, here
        stamp.lacAt = now
    elseif key == "bite" then
        stamp.biteAt = now
    elseif key == "swift" then
        stamp.swiftAt = now
    elseif key == "finisher" then
        stamp.finisherAt = now
    elseif key == "shift" then
        stamp.shiftCastAt = now
    elseif key == "rejuv" or key == "regrow" then
        local who = TargetName()
        if who then
            local rec = hots[who]
            if not rec then rec = {}; hots[who] = rec end
            rec[key] = now + (key == "rejuv" and TUNING.REJUV_SECONDS or TUNING.REGROWTH_SECONDS)
        end
    end
    Notify("cast")
end

local HOT_KEYS = { "rejuv", "regrow" }

-- A HoT that ran its full time blooms: stamp it once and forget it. Called from the module's ticker (no allocation).
function State.Tick(now)
    local name = TargetName()
    local rec = name and hots[name]
    if rec then
        for i = 1, #HOT_KEYS do
            local key = HOT_KEYS[i]
            local exp = rec[key]
            if exp and exp <= now then
                rec[key] = nil
                if now - exp < TUNING.BLOOM_WINDOW then stamp.bloomAt = now end
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Spells and cooldowns
-------------------------------------------------------------------------------

-- true / false for "the player knows this spell" (by name), nil when unreadable
function State.Known(key)
    local name = SPELLS[key]
    if not name then return nil end
    local FH = FS.FrameHelpers
    if not (FH and FH.ResolveSpell and FH.IsKnownSpellId) then return nil end
    local id = FH.ResolveSpell(name)
    if not id then return false end
    return FH.IsKnownSpellId(id, false) and true or false
end

-- "ready" or "cool" from the plain flags of the spell's cooldown, "none" when it is not learned, nil when it cannot be read
function State.Cooldown(key)
    local k = State.Known(key)
    if k == false then return "none" end
    if k == nil then return nil end
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if type(fn) ~= "function" then return nil end
    local ok, c = pcall(fn, SPELLS[key])
    if not ok or type(c) ~= "table" or IsSecret(c) then return nil end
    local active, gcd = PlainOf(c.isActive, "boolean"), PlainOf(c.isOnGCD, "boolean")
    if active == nil then return nil end
    if active and gcd == nil then return nil end   -- an unreadable GCD flag: it may be the GCD alone, so say nothing
    return (active and gcd ~= true) and "cool" or "ready"
end

-- the engine's duration object of the cooldown (for StatusBar:SetTimerDuration), or nil
function State.Duration(key)
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    if type(fn) ~= "function" or not SPELLS[key] then return nil end
    local ok, obj = pcall(fn, SPELLS[key])
    if not ok then return nil end
    return obj
end

-------------------------------------------------------------------------------
-- Start
-------------------------------------------------------------------------------

function State.Refresh()
    ReadThorns()
    level = PlainOf(Call(UnitLevel, "player"), "number")
    local f = ReadForm()
    local changed = f ~= form
    form = f
    if changed then stamp.shiftAt = Now() end
    Notify(changed and "form" or "refresh")
end

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORM", "SPELLS_CHANGED", "PLAYER_LEVEL_UP", "PLAYER_TARGET_CHANGED",
    "SPELL_UPDATE_COOLDOWN", "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED" }

function State.Start()
    if started then return end
    started = true
    local now = Now()
    if type(InCombatLockdown) == "function" and InCombatLockdown() then unknownUntil = now + TUNING.UNKNOWN_SECONDS end
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, unit, a2, spellID)
        local ok, err
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            ok, err = pcall(OnCast, spellID)
        elseif event == "UNIT_SPELLCAST_SENT" then
            ok, err = pcall(OnSent, a2)
        elseif event == "UNIT_AURA" then
            ok, err = pcall(State.RereadThorns)
        elseif event == "SPELL_UPDATE_COOLDOWN" then
            Notify("cooldown"); ok = true
        elseif event == "UNIT_DISPLAYPOWER" then
            ok, err = pcall(State.Refresh)
        else
            ok, err = pcall(State.Refresh)
        end
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "druidstate_event", "|cffff4488Forever STUwave|r: druid state " .. tostring(event) .. ": " .. tostring(err))
        end
    end)
    Register(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
    Register(frame, "UNIT_SPELLCAST_SENT", "player")
    Register(frame, "UNIT_AURA", "player")
    Register(frame, "UNIT_DISPLAYPOWER", "player")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
    -- the aura gate can still be shut for a moment after PLAYER_REGEN_ENABLED: read Thorns again once it opens
    if FS.OnAurasReadable then pcall(FS.OnAurasReadable, State.RereadThorns) end
    pcall(State.Refresh)
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
