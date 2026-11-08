-- Forever STUwave: the Hunter's shot clock, range, ammo and traps, as plain state for the Gunsight Hunter module
--
-- FACTS (DEFS and TUNING below; every number the module guesses with sits in TUNING, because class tuning moves between builds).
-- Auto Shot fires once a ranged weapon cycle (UnitRangedDamage: 0.5 s of it is the cast, the rest the weapon's cooldown; haste
-- shrinks both) and keeps firing through Aimed, Multi and Sniper Shot casts, so no cast warning is kept. Moving in the last
-- half second delays the shot (the game retries every half second while you move). A melee swing resets the ranged timer on
-- Forever (the wiki lists it as current behaviour; TUNING.MELEE_RESET switches the reset off if it is fixed), and so does
-- Feign Death. Every trap shares ONE 30 s cooldown; one fire trap (Immolation or Explosive) and one frost trap (Freezing or
-- Frost) may lie on the ground at once, each for a minute. The player's own casts are matched by spell NAME, so any rank
-- counts, and every spell id below is UNPROBED on this client: a spell is found by id when one is known and by its name
-- otherwise.
--
-- WHAT THE CLIENT LETS US READ (12.0 engine, see the wow-addon-secret-values notes):
--   * The moment a shot fires is the player's own Auto Shot (spell 75) as a plain UNIT_SPELLCAST_SUCCEEDED, the way the wand's
--     Shoot arrived on the Priest probe (UNPROVEN on a Hunter). The cycle length is UnitRangedDamage's speed when it is a plain
--     number, else the measured gap between two shots, else TUNING.DEFAULT_CYCLE. Nothing here is a secret.
--   * Auto Shot on or off: START_AUTOREPEAT_SPELL / STOP_AUTOREPEAT_SPELL, corrected by IsAutoRepeatSpell when the client has it;
--     with neither, a shot inside TUNING.RECENT_CYCLES cycles stands for "on".
--   * Range is four states, never yards: Raptor Strike in range = melee, Auto Shot in range = ranged (C_Spell.IsSpellInRange,
--     plain on the Priest probe for a hostile target; Hunter spells UNPROBED); neither = dead zone or too far, told apart by
--     CheckInteractDistance (plain, coarse bands). UnitInRange is a secret boolean and is not used.
--   * Moving is GetUnitSpeed("player") > 0 (expected plain, UNPROBED).
--   * Ammo is GetItemCount of the item in the ammo slot (plain in combat on the Priest), shown only with a ranged weapon.
--   * Cooldown flags (isActive, isOnGCD) are plain; the seconds are secret, so the trap refill is the engine's own
--     (C_Spell.GetSpellCooldownDuration, handed out by CooldownDuration()).
--
-- WHAT IS A GUESS AND HOW IT IS CORRECTED
--   * A trap on the ground is a ledger of the own cast (60 s, shown with "~"): the client never says when a trap fires or when
--     the mob it caught is gone, and the combat log is restricted, so a slot keeps draining after its trap went off.
--   * A melee swing is only seen when it is an ability (Raptor Strike, Mongoose Bite, Wing Clip): a plain white swing sends the
--     addon no event. The reset is therefore a floor, not a full account.
--   * The first shot after Auto Shot turns on waits the cast time (TUNING.WINDUP) at least, which is how the clock starts.
--
-- The listeners run from Start() on and never stop: a cast while the module is hidden (no target) cannot be read back later.
--
-- API: Start(), Refresh(), Subscribe(fn), Unsubscribe(fn), Tick(now), Known(key) -> true / false / nil, Shot() (the live shot
-- table: last, cycle, source, firedAt, lateAmt, resetAt), Fill(now), Late(now), AutoOn(now), Range(now) -> "melee" | "dead" |
-- "ranged" | "far" | nil, Moving() -> true / false / nil, Ammo() -> count | nil, AmmoWarn(), TrapKey(), TrapCooling() -> true /
-- false / nil, TrapDuration(), TrapCastAt(), Traps() -> { fire, frost } (each up, expires, at, key), CastAt(key), DEFS, TUNING,
-- SETTINGS. A listener is called fn(reason, key) with reason "cast", "shot", "reset", "auto", "trap", "cooldown", "combat",
-- "ammo", "expire", "change", "learn".

local _, FS = ...

FS.HunterState = FS.HunterState or {}
local State = FS.HunterState

local IsSecret = FS.IsSecret or function() return false end

local TUNING = {
    DEFAULT_CYCLE = 2.8,                 -- s, the bow of the design mockup, until a weapon speed or a measured gap is known
    WINDUP = 0.5,                        -- s, the last stretch of a cycle that must be stood still in
    CYCLE_MIN = 0.8, CYCLE_MAX = 6,      -- a weapon speed outside this is not a ranged speed
    LATE_MIN = 0.05,                     -- s a shot may fire after it was due before it counts as late
    RECENT_CYCLES = 1.5,                 -- cycles after the last shot in which Auto Shot is taken as on, with no start or stop signal
    RANGE_EVERY = 0.1,                   -- s between range re-reads
    NEAR_INTERACT = 3,                   -- CheckInteractDistance index told apart from "too far": the duel distance, about 10 yd
    TRAP_COOLDOWN = 30, TRAP_LIFE = 60,
    MELEE_RESET = true,                  -- a melee ability resets the ranged timer (Forever, current behaviour; false when it is fixed)
    RESETTERS = { "raptor", "mongoose", "wingclip", "feign" },
    AMMO_SLOT = 0, RANGED_SLOT = 18,     -- the ammo and ranged weapon inventory slots
}
State.TUNING = TUNING

local SETTINGS = { ammoWarn = { key = "gunsight.hunter.ammowarn", default = 60 } }
State.SETTINGS = SETTINGS
if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(SETTINGS.ammoWarn.key, SETTINGS.ammoWarn.default) end

-- ids are the Classic ranks (UNPROBED here); a name is always tried too
local DEFS = {
    autoshot = { name = "Auto Shot", ids = { 75 } },
    raptor = { name = "Raptor Strike", ids = { 27014, 14266, 14265, 14264, 14263, 14262, 14261, 14260, 2973 } },
    mongoose = { name = "Mongoose Bite", ids = { 36916, 14271, 14270, 14269, 1495 } },
    wingclip = { name = "Wing Clip", ids = { 14268, 14267, 2974 } },
    feign = { name = "Feign Death", ids = { 5384 } },
    immolation = { name = "Immolation Trap", ids = { 27023, 14305, 14304, 14303, 14302, 13795 } },
    explosive = { name = "Explosive Trap", ids = { 27025, 14317, 14316, 13813 } },
    freezing = { name = "Freezing Trap", ids = { 14311, 14310, 1499 } },
    frost = { name = "Frost Trap", ids = { 13809 } },
}
State.DEFS = DEFS
local KEYS = { "autoshot", "raptor", "mongoose", "wingclip", "feign", "immolation", "explosive", "freezing", "frost" }
local TRAP_KEYS = { "immolation", "freezing", "explosive", "frost" }     -- the order a cooldown is read from when none was cast yet
local FAMILY = { immolation = "fire", explosive = "fire", freezing = "frost", frost = "frost" }

local known = {}                       -- key -> true / false (nil = never resolved)
local shot = { last = nil, cycle = TUNING.DEFAULT_CYCLE, source = "default", firedAt = nil, lateAmt = nil, resetAt = nil, measured = nil }
local auto = { on = nil }              -- nil = no signal yet
local traps = { fire = { up = false }, frost = { up = false } }
local castAt = {}
local trapKey, trapCastAt = nil, nil
local ammo = { count = nil }
local rangeCache = { at = -1, value = nil }
local resetInGap = false
local listeners = {}
local started = false
local frame, unitFrame

local function Now() return GetTime() end

local function Notify(reason, key)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], reason, key)
        if not ok and FS.LogDegradeOnce then
            pcall(FS.LogDegradeOnce, "hunterstate_listener", "|cffff4488Forever STUwave|r: hunter state listener: " .. tostring(err))
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

local function SpellRef(d) return d.id or d.localName or d.name end

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
    return changed
end

function State.Known(key) return known[key] end
function State.CastAt(key) return castAt[key] end
function State.Shot() return shot end
function State.Traps() return traps end
function State.TrapCastAt() return trapCastAt end

-------------------------------------------------------------------------------
-- The shot clock
-------------------------------------------------------------------------------

local function ReadCycle()
    local speed = Call(UnitRangedDamage, "player")
    speed = PlainOf(speed, "number")
    if speed and speed >= TUNING.CYCLE_MIN and speed <= TUNING.CYCLE_MAX then return speed end
    return nil
end

local function UpdateCycle()
    local c = ReadCycle()
    if c then
        shot.cycle, shot.source = c, "weapon"
    elseif shot.measured then
        shot.cycle, shot.source = shot.measured, "measured"
    else
        shot.cycle, shot.source = TUNING.DEFAULT_CYCLE, "default"
    end
end

-- 0 .. 1: how far the cycle has run since the last shot (0 with no shot yet)
function State.Fill(now)
    local last = shot.last
    if not last then return 0 end
    local f = ((now or Now()) - last) / shot.cycle
    if f < 0 then return 0 elseif f > 1 then return 1 end
    return f
end

-- seconds past the moment the shot was due (0 when it is not yet due, or there is no clock)
function State.Late(now)
    local last = shot.last
    if not last then return 0 end
    local late = (now or Now()) - last - shot.cycle
    if late < 0 then return 0 end
    return late
end

function State.AutoOn(now)
    if auto.on ~= nil then return auto.on end
    local last = shot.last
    if not last then return false end
    return (now or Now()) - last <= shot.cycle * TUNING.RECENT_CYCLES
end

local function ReadAuto()
    local d = DEFS.autoshot
    local fn = C_Spell and C_Spell.IsAutoRepeatSpell or IsAutoRepeatSpell
    if type(fn) ~= "function" then return end
    local ok, r = pcall(fn, SpellRef(d))
    if not ok or IsSecret(r) then return end
    if r == nil then return end
    local on = (r == true or r == 1) and true or false
    if auto.on ~= on then auto.on = on; Notify("auto") end
end

local function SetAuto(on)
    local was = auto.on
    auto.on = on
    if on then
        -- the first shot waits the cast time at least: the clock starts with the wind-up left
        local now = Now()
        local floorAt = now - (shot.cycle - TUNING.WINDUP)
        if not shot.last or shot.last < floorAt then
            shot.last = floorAt
            resetInGap = true        -- the gap to the first shot is a made up clock, not a cycle
        end
    end
    if was ~= on then Notify("auto") end
end

local function OnShot(now)
    local last = shot.last
    if last then
        local gap = now - last
        local due = last + shot.cycle
        local late = now - due
        shot.lateAmt = late > TUNING.LATE_MIN and late or nil
        -- a gap is the cycle only when nothing stretched or cut it: no reset inside it, not a late shot
        if not resetInGap and gap >= TUNING.CYCLE_MIN and gap <= TUNING.CYCLE_MAX and not shot.lateAmt then
            shot.measured = gap
        end
    else
        shot.lateAmt = nil
    end
    resetInGap = false
    shot.firedAt, shot.last = now, now
    UpdateCycle()
end

local function OnReset(now)
    shot.last, shot.resetAt = now, now
    resetInGap = true
    Notify("reset")
end

-------------------------------------------------------------------------------
-- Range, movement, ammo
-------------------------------------------------------------------------------

local function InRange(key)
    if known[key] ~= true then return nil end
    local d = DEFS[key]
    local fn = C_Spell and C_Spell.IsSpellInRange
    if type(fn) == "function" then
        local ok, r = pcall(fn, SpellRef(d), "target")
        if ok and not IsSecret(r) then
            if r == nil then return nil end
            return r and true or false
        end
        return nil
    end
    if type(IsSpellInRange) == "function" then
        local ok, r = pcall(IsSpellInRange, d.localName or d.name, "target")
        if ok and not IsSecret(r) then
            if r == nil then return nil end
            return (r == 1 or r == true) and true or false
        end
    end
    return nil
end

local function ReadRange()
    local attack = Call(UnitCanAttack, "player", "target")
    if IsSecret(attack) or not attack then return nil end
    local melee, ranged = InRange("raptor"), InRange("autoshot")
    if melee == true then return "melee" end
    if ranged == true then return "ranged" end
    if melee == nil and ranged == nil then return nil end
    local near = Call(CheckInteractDistance, "target", TUNING.NEAR_INTERACT)
    if IsSecret(near) or near == nil then return nil end
    return near and "dead" or "far"
end

-- "melee" | "dead" | "ranged" | "far" | nil (cannot tell, or no hostile target); re-read at most every RANGE_EVERY
function State.Range(now)
    now = now or Now()
    if now - rangeCache.at >= TUNING.RANGE_EVERY or now < rangeCache.at then
        rangeCache.at, rangeCache.value = now, ReadRange()
    end
    return rangeCache.value
end

function State.Moving()
    local speed = PlainOf(Call(GetUnitSpeed, "player"), "number")
    if speed == nil then return nil end
    return speed > 0
end

function State.AmmoWarn()
    local c = FS.Config
    local v = c and c.Get and c.Get(SETTINGS.ammoWarn.key)
    if type(v) ~= "number" or v < 0 then return SETTINGS.ammoWarn.default end
    return v
end

local function ReadAmmo()
    -- no ranged weapon, nothing to count
    if not Call(GetInventoryItemID, "player", TUNING.RANGED_SLOT) then return nil end
    local id = Call(GetInventoryItemID, "player", TUNING.AMMO_SLOT)
    if not id then return 0 end
    local n = PlainOf(Call(GetItemCount, id), "number")
    if n == nil then n = PlainOf(Call(GetInventoryItemCount, "player", TUNING.AMMO_SLOT), "number") end
    return n
end

-- the ammo count (a plain number), nil with no ranged weapon or an unreadable count
function State.Ammo() return ammo.count end

function State.RefreshAmmo()
    local n = ReadAmmo()
    if n ~= ammo.count then
        ammo.count = n
        Notify("ammo")
    end
end

-------------------------------------------------------------------------------
-- Traps
-------------------------------------------------------------------------------

local function ReadCooldown(d)
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if type(fn) ~= "function" then return nil end
    local ok, c = pcall(fn, SpellRef(d))
    if not ok or type(c) ~= "table" or IsSecret(c) then return nil end
    local active, gcd = PlainOf(c.isActive, "boolean"), PlainOf(c.isOnGCD, "boolean")
    if active == nil then return nil end
    return active and gcd ~= true
end

-- the trap whose cooldown stands for the shared one: the last one cast, else the first learned
function State.TrapKey()
    if trapKey and known[trapKey] == true then return trapKey end
    for i = 1, #TRAP_KEYS do
        if known[TRAP_KEYS[i]] == true then return TRAP_KEYS[i] end
    end
    return nil
end

-- true while the shared trap cooldown runs; false ready; nil nothing learned or unreadable
function State.TrapCooling()
    local key = State.TrapKey()
    if not key then return nil end
    return ReadCooldown(DEFS[key])
end

-- the engine's duration object of the shared trap cooldown (for StatusBar:SetTimerDuration), or nil
function State.TrapDuration()
    local key = State.TrapKey()
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    if not key or type(fn) ~= "function" then return nil end
    local ok, obj = pcall(fn, SpellRef(DEFS[key]))
    if not ok then return nil end
    return obj
end

-------------------------------------------------------------------------------
-- Refresh, tick
-------------------------------------------------------------------------------

-- Always ends with a "change": a refresh comes from an event that may move what the module shows (a new target, combat, a
-- learned spell) even when nothing else changed.
function State.Refresh()
    local learned = Learn()
    rangeCache.at = -1
    UpdateCycle()
    ReadAuto()
    State.RefreshAmmo()
    if learned then Notify("learn") end
    Notify("change")
end

-- Expiry of the trap ledgers. Called from the module's ticker.
function State.Tick(now)
    now = now or Now()
    local changed = false
    for _, fam in pairs(traps) do
        if fam.up and fam.expires <= now then fam.up, fam.expires = false, nil; changed = true end
    end
    if changed then Notify("expire") end
end

-------------------------------------------------------------------------------
-- The cast ledger
-------------------------------------------------------------------------------

local function IsResetter(key)
    for i = 1, #TUNING.RESETTERS do
        if TUNING.RESETTERS[i] == key then return true end
    end
    return false
end

local function OnCast(spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local spell = SpellNameOf(spellID)
    local key = KeyOfSpell(spell)
    if not key then return end
    local now = Now()
    castAt[key] = now
    if known[key] ~= true then known[key] = true end
    if key == "autoshot" then
        OnShot(now)
        if C_Timer and C_Timer.After then C_Timer.After(0.2, State.RefreshAmmo) else State.RefreshAmmo() end
        Notify("shot")
    elseif FAMILY[key] then
        local fam = traps[FAMILY[key]]
        fam.up, fam.expires, fam.at, fam.key = true, now + TUNING.TRAP_LIFE, now, key
        trapKey, trapCastAt = key, now
        Notify("trap", key)
    elseif IsResetter(key) and (TUNING.MELEE_RESET or key == "feign") then
        OnReset(now)
        Notify("cast", key)
    else
        Notify("cast", key)
    end
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_REGEN_ENABLED",
    "PLAYER_REGEN_DISABLED", "PLAYER_TARGET_CHANGED", "PLAYER_EQUIPMENT_CHANGED", "BAG_UPDATE_DELAYED" }

local function Guard(tag, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "hunterstate_" .. tag, "|cffff4488Forever STUwave|r: hunter state " .. tag .. ": " .. tostring(err))
    end
end

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

local function OnSpeed()
    UpdateCycle()
    Notify("change")
end

function State.Start()
    if started then return end
    started = true
    frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, a1, a2, a3)
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            Guard("cast", OnCast, a3)
        elseif event == "START_AUTOREPEAT_SPELL" then
            Guard("auto", SetAuto, true)
        elseif event == "STOP_AUTOREPEAT_SPELL" then
            Guard("auto", SetAuto, false)
        elseif event == "SPELL_UPDATE_COOLDOWN" then
            Notify("cooldown")
        elseif event == "PLAYER_REGEN_DISABLED" or event == "PLAYER_REGEN_ENABLED" then
            Notify("combat")
            if event == "PLAYER_REGEN_ENABLED" then Guard("refresh", State.Refresh) end
        elseif event == "UNIT_ATTACK_SPEED" or event == "UNIT_RANGEDDAMAGE" then
            Guard("speed", OnSpeed)
        else
            Guard("refresh", State.Refresh)
        end
    end)
    Register(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
    Register(frame, "START_AUTOREPEAT_SPELL")
    Register(frame, "STOP_AUTOREPEAT_SPELL")
    Register(frame, "SPELL_UPDATE_COOLDOWN")
    Register(frame, "UNIT_ATTACK_SPEED", "player")
    Register(frame, "UNIT_RANGEDDAMAGE", "player")
    for _, e in ipairs(EVENTS) do Register(frame, e) end
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
State._OnCast, State._SetAuto = OnCast, SetAuto
