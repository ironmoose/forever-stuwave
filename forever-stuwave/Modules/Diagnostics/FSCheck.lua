-- Forever STUwave: /fscheck -- opt-in, read-only secret-value check
--
-- Parker types /fscheck ONCE before a play session. It records into
-- ForeverSTUwaveDB.fscheck what this client lets an addon READ, in and out of
-- combat, so the 12.1 secret-value rules are measured instead of guessed:
--
--   ooc            snapshot taken the moment the command runs (normally out of combat)
--   combat         snapshot ~4s after the next PLAYER_REGEN_DISABLED, if still locked down
--   casts          the player's next 10 UNIT_SPELLCAST_SUCCEEDED
--   channel        UNIT_SPELLCAST_CHANNEL_START/UPDATE/STOP seen in the same window
--   auracontainer  can a CustomAuraContainerTemplate AuraContainer draw target auras?
--   unitAura       the first UNIT_AURA payloads for player/target (5 out of combat, 10 in
--                  combat): secrecy of the unit arg, the updateInfo table and its four
--                  fields (counts only when plain)
--   procGlow       the first 20 SPELL_ACTIVATION_OVERLAY_GLOW_SHOW/HIDE events
--   shoot          wand Shoot (5019) SUCCEEDED and channel events, kept out of casts/channel
--   whitelist, gcd, pet   extra snapshot sections (spell secrecy enums, GCD cooldown
--                  fields, UnitExists("pet")); casts[i].gcd and gcdStart[i].gcd are a GCD
--                  sample taken right after each SUCCEEDED / at each START (see GcdCheck)
--
--   gunsight       `/fscheck gunsight`: a SEPARATE one-shot feature check for the gunsight HUD
--                  (8-arg SetTexCoord, SetVertexColorFromBoolean, a vertical StatusBar fed a
--                  duration object, CreateLine, C_UnitAuras instance ids and aura durations in
--                  combat, an engine-drawn AuraContainer, SetAlphaFromBoolean). Stored in
--                  ForeverSTUwaveDB.fscheck.gunsight; it never touches the main run's armed
--                  state and survives a re-arm; re-running it replaces the result.
--
--   hot            `/fscheck hot` (out of combat) / `/fscheck hot off`: does an engine AuraContainer
--                  per party token (player, party1..4) draw the player's own Renew, and do its
--                  buttons stay up and tick in combat? Plain widget queries only. Also builds the
--                  HoT TIMER BAR shape (a StatusBar the engine drives, a bare-number countdown that
--                  turns amber at 3, a pandemic overlay). Stored in ForeverSTUwaveDB.fscheck.hot;
--                  survives a re-arm like gunsight (see HP below).
--
--   priest         `/fscheck priest` (any time) / `/fscheck priest off`: what a priest's pain points can
--                  read on this client. An ooc and a combat snapshot (mana and regen, absorbs and heal
--                  prediction, auras by spell id, cooldowns, range, threat, loss of control, secrecy of
--                  every spell involved), each record tagged inCombat true/false, plus bounded ring
--                  buffers of power ticks, casts with their mana cost, auras, kills, absorbs and loss of
--                  control events. The main run adds the snapshot part to its own ooc and combat
--                  snapshots when the class is PRIEST. Stored in ForeverSTUwaveDB.fscheck.priest;
--                  survives a re-arm like gunsight (see PP below).
--
--   shaman         `/fscheck shaman` (any time) / `/fscheck shaman off`: what a Shaman totem bar can read and do
--                  on 16001, built for a fresh low level character (spells not known yet are skipped and
--                  NAMED). Same shape as priest: ooc and combat snapshots, bounded logs. Plus three explicit
--                  subcommands that are never run automatically: `buttons` (a temporary strip of secure test
--                  buttons, out of combat only), `setslot` (SetMultiCastSpell, to be run in combat) and
--                  `destroy` (DestroyTotem from addon code). Stored in ForeverSTUwaveDB.fscheck.shaman;
--                  survives a re-arm like gunsight (see the SH block below).
--
-- Read it after /reload or logout: WTF/Account/<id>/SavedVariables/forever-stuwave.lua
-- (ForeverSTUwaveDB.fscheck).
--
-- Rules this file keeps, because it runs in the middle of a play session:
--   * Nothing runs at load. The only side effect of loading is the slash command.
--     The event frame, the events and the timers all start inside /fscheck.
--   * Every API call, handler and timer is pcall'd. An error becomes a string in
--     the results; nothing is ever thrown into the session.
--   * Read-only. No protected call, no SetAttribute, no secure template. The one
--     visible thing is an AuraContainer built from the same template Plater uses.
--     The one exception is the opt-in `/fscheck shaman` subcommands (see the SH block): the totem button row
--     of secure buttons and the two calls that may be protected, each typed by Parker, never automatic.
--   * A secret value is never compared, concatenated, truth-tested, indexed or
--     tostring'd, and never stored. Only its type and the boolean "isSecret" are
--     recorded. A plain value is stored only where a field is marked `keep`, and
--     only when issecretvalue() answered "no". If issecretvalue() itself cannot be
--     called, the answer fails closed ("secret") and no value is stored.
--   * Every event is unregistered as its part finishes, and nothing uses OnUpdate.

local KEY = "fscheck"
local COMBAT_DELAY = 4
local CAST_TARGET = 10
local CHANNEL_CAP = 30
local AURA_SHOW_SECONDS = 30
local MAX_ERR = 200
local MAX_STR = 60
local MAX_EXTRA_KEYS = 24
local MAX_RETURNS = 10
local MAX_REGISTER_ERR = 800

local TEMPLATE = "CustomAuraContainerTemplate"
local HARMFUL_MINE = "HARMFUL|PLAYER"
local HELPFUL = "HELPFUL"

local SOUL_SHARD = 6265
local SHADOW_BOLT = 686
local SHADOW_TRANCE = 17941
local SHOOT = 5019
local AURA_OOC_CAP = 5
local AURA_COMBAT_CAP = 10
local PROC_CAP = 20
local GCD_START_CAP = 10
local SHOOT_CAP = 12

-- W1: C_Secrets enum per spell. 0 NeverSecret, 1 AlwaysSecret, 2 ContextuallySecret.
local WHITELIST_IDS = {
    21562, 1459, 6673, 1126, 2823, 8679, 3408, 5761,
    17941, 15473, 706, 1243, 589, 594, 980, 172, 348, 18265, 687, 5019,
}

-- GCD: spells whose cooldown table is read in each snapshot. GCD_CHECK_SPELLS are the
-- candidates read for isActive in a cast sample: only spells with NO cooldown of their own
-- (Mind Blast has an 8s one, so it would read active with no GCD running), and never the
-- spell that was just cast. 61304 is the global cooldown marker, read as the control.
local GCD_MARKER = 61304
local GCD_SECTION_SPELLS = { GCD_MARKER, 686, 585 }
local GCD_CHECK_SPELLS = { 585, 686, 172 }
local GCD_KEEP = { startTime = true, duration = true, isActive = true, isOnGCD = true }
local GCD_CONTROL_KEYS = { "startTime", "duration", "isActive" }

-- aura = "debuff" (read on the target), "buff" (read on the player), nil = neither.
local SPELLS = {
    { 589, "debuff" },   -- Shadow Word: Pain r1
    { 15473, "buff" },   -- Shadowform
    { 588, "buff" },     -- Inner Fire
    { 1243, "buff" },    -- Power Word: Fortitude
    { 8092, nil },       -- Mind Blast
    { 15407, "debuff" }, -- Mind Flay
    { 2944, "debuff" },  -- Devouring Plague
    { 585, nil },        -- Smite (extra: what a low level priest actually has)
    { 17, "buff" },      -- Power Word: Shield (extra)
    { 172, "debuff" },   -- Corruption
    { 980, "debuff" },   -- Curse of Agony / Bane of Agony
    { 348, "debuff" },   -- Immolate
    { 17941, "buff" },   -- Shadow Trance
    { SHADOW_BOLT, nil },
    { 687, "buff" },     -- Demon Skin
    { 706, "buff" },     -- Demon Armor
}

-- Cooldown reads: Smite, Mind Blast, Shadow Bolt, Fade (off the GCD), and the GCD
-- itself (61304 is the global cooldown marker spell).
local COOLDOWN_SPELLS = { 585, 8092, SHADOW_BOLT, 586, 61304 }

local AURA_FIELDS = {
    "spellId", "name", "icon", "duration", "expirationTime", "applications",
    "sourceUnit", "isFromPlayerOrPlayerPet", "auraInstanceID",
}
local COOLDOWN_FIELDS = { "startTime", "duration", "isEnabled", "isActive", "modRate" }
local GCD_FIELDS = { "startTime", "duration", "isEnabled", "isActive", "modRate", "isOnGCD" }
local SPELLINFO_FIELDS = { "name", "spellID", "castTime", "minRange", "maxRange" }

-- Every function the 16001 API dump lists under C_Secrets. Names missing at
-- runtime are recorded as "absent".
local SECRETS_DUMP = {
    "CanCompareUnitTokens", "GetPowerTypeSecrecy", "GetSpellAuraSecrecy",
    "GetSpellCastSecrecy", "GetSpellCooldownSecrecy", "HasSecretRestrictions",
    "ShouldActionCooldownBeSecret", "ShouldAurasBeSecret", "ShouldCooldownsBeSecret",
    "ShouldSpellAuraBeSecret", "ShouldSpellBookItemCooldownBeSecret",
    "ShouldSpellCooldownBeSecret", "ShouldTotemSlotBeSecret", "ShouldTotemSpellBeSecret",
    "ShouldUnitAuraIndexBeSecret", "ShouldUnitAuraInstanceBeSecret",
    "ShouldUnitAuraSlotBeSecret", "ShouldUnitComparisonBeSecret",
    "ShouldUnitHealthMaxBeSecret", "ShouldUnitIdentityBeSecret", "ShouldUnitPowerBeSecret",
    "ShouldUnitPowerMaxBeSecret", "ShouldUnitSpellCastBeSecret",
    "ShouldUnitSpellCastingBeSecret", "ShouldUnitStatsBeSecret",
    "ShouldUnitThreatStateBeSecret", "ShouldUnitThreatValuesBeSecret",
}

-- C_Secrets calls whose signature is documented (SecretPredicateAPIDocumentation).
-- The spell-id ones run per spell below; the spellbook-slot and aura-instance ones
-- need an argument that does not exist yet, so they are only listed by name.
local SECRETS_CALLS = {
    { "HasSecretRestrictions" },
    { "ShouldAurasBeSecret" },
    { "ShouldCooldownsBeSecret" },
    { "ShouldUnitStatsBeSecret" },
    { "GetPowerTypeSecrecy", 0 },
    { "CanCompareUnitTokens", "player", "target" },
    { "ShouldUnitComparisonBeSecret", "player", "target" },
    { "ShouldUnitHealthMaxBeSecret", "player" },
    { "ShouldUnitHealthMaxBeSecret", "target" },
    { "ShouldUnitIdentityBeSecret", "target" },
    { "ShouldUnitPowerBeSecret", "player" },
    { "ShouldUnitPowerMaxBeSecret", "player" },
    { "ShouldUnitSpellCastingBeSecret", "player" },
    { "ShouldUnitSpellCastBeSecret", "player", SHADOW_BOLT },
    { "ShouldUnitAuraIndexBeSecret", "target", 1, HARMFUL_MINE },
    { "ShouldUnitThreatStateBeSecret", "player" },
    { "ShouldUnitThreatValuesBeSecret", "player", "target" },
    { "ShouldActionCooldownBeSecret", 1 },
    { "ShouldTotemSlotBeSecret", 1 },
}

-- Cast ends that are not a success: each one drops the remembered START.
local CAST_END_EVENTS = {
    "UNIT_SPELLCAST_STOP",
    "UNIT_SPELLCAST_FAILED",
    "UNIT_SPELLCAST_INTERRUPTED",
}
-- Longest START -> SUCCEEDED gap (seconds) still taken as a cast time.
local MAX_CAST_ELAPSED = 10

local CHANNEL_EVENTS = {
    "UNIT_SPELLCAST_CHANNEL_START",
    "UNIT_SPELLCAST_CHANNEL_UPDATE",
    "UNIT_SPELLCAST_CHANNEL_STOP",
}

local AURA_EVENT = "UNIT_AURA"
local AURA_UPDATE_FIELDS = {
    "isFullUpdate", "addedAuras", "updatedAuraInstanceIDs", "removedAuraInstanceIDs",
}
local PROC_EVENTS = {
    "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",
    "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE",
}

local USAGE = {
    "fscheck: /fscheck (out of combat) = snapshot now, then record your next pull, 10 casts, and a 30s aura row above screen centre",
    "fscheck: /fscheck again = status | /fscheck reset = clear and stop | after \"done\", /reload to save",
    "fscheck: /fscheck gunsight = gunsight HUD feature checks (works any time; the cast and combat parts wait for your next cast and pull)",
    "fscheck: /fscheck priest = priest check: snapshot now, the other (ooc/combat) one on the next pull or fight end, plus 20 min of bounded power/cast/aura/kill logs | /fscheck priest off = stop",
    "fscheck: /fscheck shaman = shaman totem check: snapshot now, the other (ooc/combat) one on the next pull or fight end, plus 30 min of bounded totem/cast/click logs, and a list of the checks that could not run (spell not known yet) | /fscheck shaman off = stop",
    "fscheck: /fscheck shaman buttons = temporary totem button row (dismiss slots 1-4, castsequence, Totemic Recall; out of combat) | /fscheck shaman buttons off = hide it | /fscheck shaman setslot = SetMultiCastSpell from addon code, run it IN COMBAT yourself | /fscheck shaman destroy [slot] = DestroyTotem from addon code",
    "fscheck: /fscheck hot = party row HoT check: an engine aura container per party token (icon, short buffs, HoT timer bar) for 120s (out of combat to start) | /fscheck hot off = remove it",
}

-------------------------------------------------------------------------------
-- State (all of it dormant until /fscheck runs)
-------------------------------------------------------------------------------

local state = {
    runId = 0,
    armed = false,
    frame = nil,
    extra = nil,
    auraOoc = 0,
    auraCombat = 0,
    procCount = 0,
    shootCount = 0,
    startCount = 0,
    startAt = nil,
    startSpell = nil,
    gcdKnown = nil,
    canTest = false,
    combatDone = false,
    combatPending = false,
    combatSkips = 0,
    castsDone = false,
    castCount = 0,
    channelCount = 0,
    acDone = false,
    acBuilt = false,
    rowLive = false,
    container = nil,
    label = nil,
    groupAdded = false,
    gsRun = 0,
    gsFrame = nil,
    gsHost = nil,
    gsCastArmed = false,
    gsCombatArmed = false,
    gsCombatPending = false,
    gsObjs = {},
    gsAc = nil,
}

-- The priest check (/fscheck priest). Declared here so the snapshot section list can name it;
-- the code is in the PP block further down.
local PP = {}

-------------------------------------------------------------------------------
-- Secret-safe primitives
-------------------------------------------------------------------------------

-- True when v is secret OR when that could not be determined. Failing closed means
-- a broken issecretvalue can only ever cost us data, never leak a value.
local function IsSecret(v)
    local fn = _G.issecretvalue
    if type(fn) ~= "function" then return true end
    local ok, result = pcall(fn, v)
    if not ok then return true end
    return result ~= false
end

local function ErrText(err)
    if IsSecret(err) then return "error value was secret or unreadable" end
    local ok, text = pcall(function()
        if type(err) == "string" then return string.sub(err, 1, MAX_ERR) end
        return "(" .. type(err) .. " error)"
    end)
    if ok and type(text) == "string" then return text end
    return "unprintable error"
end

-- One value, described. `keep` stores the value too, but only a plain
-- boolean/number/short string that issecretvalue() cleared.
local function Desc(v, keep)
    local d = { type = type(v), isSecret = IsSecret(v) }
    if keep and state.canTest and d.isSecret == false then
        local t = d.type
        if t == "boolean" then
            d.value = v
        elseif t == "number" then
            if v ~= v or v == math.huge or v == -math.huge then
                d.value = "nonfinite"
            else
                d.value = v
            end
        elseif t == "string" then
            d.value = string.sub(v, 1, MAX_STR)
        end
    end
    return d
end

local function Pack(...)
    return select("#", ...), { ... }
end

-- Looks up ns[name] (or the global `ns` when name is nil) without throwing.
local function Api(ns, name)
    local owner = _G[ns]
    if name == nil then
        if type(owner) == "function" then return owner end
        return nil
    end
    if type(owner) ~= "table" then return nil end
    local ok, fn = pcall(function() return owner[name] end)
    if ok and type(fn) == "function" then return fn end
    return nil
end

-- Calls fn(...) under pcall and describes every return. Returns the record and the
-- FIRST raw return, which the caller may only pass to IsSecret/type/Desc.
local function Invoke(keep, fn, ...)
    if type(fn) ~= "function" then return { exists = false } end
    local n, t = Pack(pcall(fn, ...))
    local rec = { exists = true, ok = t[1] == true }
    if not rec.ok then
        rec.err = ErrText(t[2])
        return rec
    end
    local returns = n - 1
    rec.n = returns
    if returns < 1 then
        rec.r1 = Desc(nil)
        return rec, nil
    end
    for i = 1, math.min(returns, MAX_RETURNS) do
        rec["r" .. i] = Desc(t[i + 1], keep)
    end
    return rec, t[2]
end

-- A plain number field of a plain table, or nil.
local function PlainNumberField(tbl, key)
    local ok, v = pcall(function() return tbl[key] end)
    if ok and type(v) == "number" and not IsSecret(v) then return v end
    return nil
end

-- Describes `wanted` fields of a non-secret table, plus any other string keys it
-- carries (capped), so a field this client added shows up without a code change.
local function ReadFields(rec, tbl, wanted, keep)
    local fields = {}
    local seen = {}
    for _, key in ipairs(wanted) do
        seen[key] = true
        local ok, v = pcall(function() return tbl[key] end)
        if ok then
            fields[key] = Desc(v, keep and keep[key])
        else
            fields[key] = { err = ErrText(v) }
        end
    end
    pcall(function()
        local extra = 0
        for k in pairs(tbl) do
            if type(k) == "string" and not IsSecret(k) and not seen[k] then
                extra = extra + 1
                if extra > MAX_EXTRA_KEYS then break end
                seen[k] = true
                local ok, v = pcall(function() return tbl[k] end)
                if ok then fields[k] = Desc(v) end
            end
        end
    end)
    rec.fields = fields
end

-- True when issecrettable calls the table secret. One rule for every table check here: a
-- MISSING issecrettable function means the API does not exist on this client, so no table
-- can be secret by it (false); a function that THROWS or returns anything but false means
-- the check could not be made, so the table counts as secret (true, fail closed).
local function SecretTable(v)
    local fn = _G.issecrettable
    if type(fn) ~= "function" then return false end
    local ok, r = pcall(fn, v)
    return not (ok and r == false)
end

-- Records issecrettable's verdict on rec. Nothing is recorded when the API is missing.
local function NoteTable(rec, v)
    if type(v) ~= "table" then return end
    if type(_G.issecrettable) == "function" then
        rec.issecrettable = SecretTable(v)
    end
end

-- Invoke, then describe the fields of the table it returned. A table is indexed only
-- when issecretvalue AND issecrettable both cleared it. `keep` (a set of field names)
-- also stores those fields' plain values.
local function InvokeTableKeep(wanted, keep, fn, ...)
    local rec, v = Invoke(false, fn, ...)
    if rec.ok and type(v) == "table" then
        NoteTable(rec, v)
        if rec.r1 and rec.r1.isSecret == false and rec.issecrettable ~= true then
            ReadFields(rec, v, wanted, keep)
        end
    end
    return rec, v
end

local function InvokeTable(wanted, fn, ...)
    return InvokeTableKeep(wanted, nil, fn, ...)
end

-- An aura read. Also returns the auraInstanceID when it is a plain number.
local function AuraCall(fn, ...)
    local rec, v = InvokeTable(AURA_FIELDS, fn, ...)
    local instanceID
    if rec.ok and type(v) == "table" and rec.r1 and rec.r1.isSecret == false and rec.issecrettable ~= true then
        instanceID = PlainNumberField(v, "auraInstanceID")
    end
    return rec, instanceID
end

-- GetUnitAuras: an array of aura tables.
local function AuraListCall(fn, ...)
    local rec, v = Invoke(false, fn, ...)
    if rec.ok and type(v) == "table" and rec.r1 and rec.r1.isSecret == false then
        NoteTable(rec, v)
        if rec.issecrettable == true then return rec end
        local okc, count = pcall(function() return #v end)
        if okc and type(count) == "number" then rec.count = count end
        local okf, first = pcall(function() return v[1] end)
        if okf and type(first) == "table" and not IsSecret(first) then
            ReadFields(rec, first, AURA_FIELDS)
        end
    end
    return rec
end

local function Section(snap, name, fn)
    local sec = {}
    snap[name] = sec
    local ok, err = pcall(fn, sec)
    if not ok then sec.sectionError = ErrText(err) end
end

local function SafeDate()
    local ok, text = pcall(function() return _G.date("%Y-%m-%d %H:%M:%S") end)
    if ok and type(text) == "string" then return text end
    return "unknown"
end

-- A plain boolean from a record made with keep=true, or nil.
local function KeptBool(rec)
    local d = rec and rec.r1
    if d and d.type == "boolean" and d.isSecret == false then return d.value end
    return nil
end

local function SpellName(id)
    local nameFn = Api("C_Spell", "GetSpellName")
    local rec, v = Invoke(true, nameFn, id)
    if rec.ok and type(v) == "string" and not IsSecret(v) then return v end
    local infoFn = Api("C_Spell", "GetSpellInfo")
    local irec, info = Invoke(false, infoFn, id)
    if irec.ok and type(info) == "table" and not IsSecret(info) then
        local ok, name = pcall(function() return info.name end)
        if ok and type(name) == "string" and not IsSecret(name) then return name end
    end
    return nil
end

-- The spell id the player actually knows for a name (the client resolves a name to
-- the highest known rank), or nil.
local function KnownRankID(name)
    local infoFn = Api("C_Spell", "GetSpellInfo")
    local rec, info = Invoke(false, infoFn, name)
    if rec.ok and type(info) == "table" and not IsSecret(info) then
        return PlainNumberField(info, "spellID")
    end
    return nil
end

-------------------------------------------------------------------------------
-- Snapshot sections
-------------------------------------------------------------------------------

local function SectionEnv(sec)
    sec.canTestSecret = state.canTest
    sec.inCombatLockdown = Invoke(true, Api("InCombatLockdown"))
    sec.aurasShouldBeSecret = Invoke(true, Api("C_Secrets", "ShouldAurasBeSecret"))
    sec.unitClass = Invoke(true, Api("UnitClass"), "player")
    sec.unitLevel = Invoke(true, Api("UnitLevel"), "player")
    sec.buildInfo = Invoke(true, Api("GetBuildInfo"))
    sec.gameTime = Invoke(true, Api("GetTime"))
end

local function SectionSecrets(sec)
    local owner = _G.C_Secrets
    if type(owner) ~= "table" then
        sec.namespace = "absent"
        return
    end
    sec.namespace = "present"

    local present, absent = {}, {}
    pcall(function()
        for k, v in pairs(owner) do
            if type(k) == "string" and type(v) == "function" then present[#present + 1] = k end
        end
    end)
    table.sort(present)
    sec.names = table.concat(present, ",")

    local have = {}
    for _, k in ipairs(present) do have[k] = true end
    for _, k in ipairs(SECRETS_DUMP) do
        if not have[k] then absent[#absent + 1] = k end
    end
    sec.absent = table.concat(absent, ",")

    sec.calls = {}
    for _, call in ipairs(SECRETS_CALLS) do
        local label = call[1]
        local args = {}
        for i = 2, #call do args[#args + 1] = tostring(call[i]) end
        if #args > 0 then label = label .. "(" .. table.concat(args, ",") .. ")" end
        sec.calls[label] = Invoke(true, Api("C_Secrets", call[1]), unpack(call, 2))
    end
end

local function SectionSpells(sec)
    local isPlayerSpell = Api("IsPlayerSpell")
    local isKnown = Api("C_SpellBook", "IsSpellKnown")
    local auraSecrecy = Api("C_Secrets", "GetSpellAuraSecrecy")
    local auraSecret = Api("C_Secrets", "ShouldSpellAuraBeSecret")
    local cdSecret = Api("C_Secrets", "ShouldSpellCooldownBeSecret")
    local castSecrecy = Api("C_Secrets", "GetSpellCastSecrecy")
    local cdSecrecy = Api("C_Secrets", "GetSpellCooldownSecrecy")
    for _, spell in ipairs(SPELLS) do
        local id = spell[1]
        local entry = {}
        sec["s" .. id] = entry
        local ok, err = pcall(function()
            entry.name = SpellName(id) or "unresolved"
            entry.isPlayerSpell = Invoke(true, isPlayerSpell, id)
            entry.isSpellKnown = Invoke(true, isKnown, id)
            entry.auraSecrecy = Invoke(true, auraSecrecy, id)
            entry.shouldAuraBeSecret = Invoke(true, auraSecret, id)
            entry.shouldCooldownBeSecret = Invoke(true, cdSecret, id)
            entry.castSecrecy = Invoke(true, castSecrecy, id)
            entry.cooldownSecrecy = Invoke(true, cdSecrecy, id)
        end)
        if not ok then entry.entryError = ErrText(err) end
    end
end

local function SectionTargetAuras(sec)
    local exists = Invoke(true, Api("UnitExists"), "target")
    sec.unitExists = exists
    if KeptBool(exists) ~= true then
        sec.skipped = "no target"
        return
    end

    local bySpellID = Api("C_UnitAuras", "GetUnitAuraBySpellID")
    local bySpellName = Api("C_UnitAuras", "GetAuraDataBySpellName")
    local byIndex = Api("C_UnitAuras", "GetAuraDataByIndex")
    local getAuras = Api("C_UnitAuras", "GetUnitAuras")
    local getDuration = Api("C_UnitAuras", "GetAuraDuration")

    local function WithDuration(rec, instanceID)
        if instanceID then
            rec.durationObject = Invoke(false, getDuration, "target", instanceID)
        end
        return rec
    end

    sec.byIndex1 = WithDuration(AuraCall(byIndex, "target", 1, HARMFUL_MINE))
    sec.getUnitAuras = AuraListCall(getAuras, "target", HARMFUL_MINE)

    for _, spell in ipairs(SPELLS) do
        if spell[2] == "debuff" then
            local id = spell[1]
            local entry = {}
            sec["s" .. id] = entry
            local ok, err = pcall(function()
                local name = SpellName(id)
                entry.name = name or "unresolved"
                local rec, instance = AuraCall(bySpellID, "target", id)
                entry.byRank1ID = WithDuration(rec, instance)
                if name then
                    local nrec, ninstance = AuraCall(bySpellName, "target", name, HARMFUL_MINE)
                    entry.byName = WithDuration(nrec, ninstance)
                    local known = KnownRankID(name)
                    if known then
                        entry.knownRankID = known
                        if known ~= id then
                            local krec, kinstance = AuraCall(bySpellID, "target", known)
                            entry.byKnownRankID = WithDuration(krec, kinstance)
                        end
                    end
                end
            end)
            if not ok then entry.entryError = ErrText(err) end
        end
    end
end

local function SectionPlayerAuras(sec)
    local byPlayerID = Api("C_UnitAuras", "GetPlayerAuraBySpellID")
    local bySpellName = Api("C_UnitAuras", "GetAuraDataBySpellName")
    sec.shapeshiftForm = Invoke(false, Api("GetShapeshiftForm"))
    for _, spell in ipairs(SPELLS) do
        if spell[2] == "buff" then
            local id = spell[1]
            local entry = {}
            sec["s" .. id] = entry
            local ok, err = pcall(function()
                local name = SpellName(id)
                entry.name = name or "unresolved"
                entry.byID = AuraCall(byPlayerID, id)
                if name then
                    entry.byName = AuraCall(bySpellName, "player", name, HELPFUL)
                end
            end)
            if not ok then entry.entryError = ErrText(err) end
        end
    end
end

local function SectionVitals(sec)
    local calls = {
        { "playerPower", "UnitPower", "player" },
        { "playerPowerMax", "UnitPowerMax", "player" },
        { "playerPowerPercent", "UnitPowerPercent", "player" },
        { "playerHealth", "UnitHealth", "player" },
        { "playerHealthMax", "UnitHealthMax", "player" },
        { "playerHealthPercent", "UnitHealthPercent", "player" },
        { "targetHealth", "UnitHealth", "target" },
        { "targetHealthMax", "UnitHealthMax", "target" },
        { "targetHealthPercent", "UnitHealthPercent", "target" },
    }
    for _, c in ipairs(calls) do
        sec[c[1]] = Invoke(false, Api(c[2]), c[3])
    end
end

local function SectionCooldowns(sec)
    local isPlayerSpell = Api("IsPlayerSpell")
    local getCooldown = Api("C_Spell", "GetSpellCooldown")
    local getDuration = Api("C_Spell", "GetSpellCooldownDuration")
    local isUsable = Api("C_Spell", "IsSpellUsable")
    local inRange = Api("C_Spell", "IsSpellInRange")
    for _, id in ipairs(COOLDOWN_SPELLS) do
        local entry = {}
        sec["s" .. id] = entry
        local ok, err = pcall(function()
            entry.name = SpellName(id) or "unresolved"
            entry.isPlayerSpell = Invoke(true, isPlayerSpell, id)
            entry.cooldown = InvokeTable(COOLDOWN_FIELDS, getCooldown, id)
            entry.cooldownDuration = Invoke(false, getDuration, id)
            entry.usable = Invoke(false, isUsable, id)
            entry.inRangeOfTarget = Invoke(false, inRange, id, "target")
        end)
        if not ok then entry.entryError = ErrText(err) end
    end
    sec.shadowBoltInfo = InvokeTable(SPELLINFO_FIELDS, Api("C_Spell", "GetSpellInfo"), SHADOW_BOLT)
end

local function SectionTargetIdentity(sec)
    sec.guid = Invoke(false, Api("UnitGUID"), "target")
    sec.exists = Invoke(true, Api("UnitExists"), "target")
    sec.isDead = Invoke(true, Api("UnitIsDead"), "target")
    sec.canAttack = Invoke(true, Api("UnitCanAttack"), "player", "target")
end

local function SectionAssistedCombat(sec)
    sec.namespace = type(_G.C_AssistedCombat) == "table" and "present" or "absent"
    sec.isAvailable = Invoke(true, Api("C_AssistedCombat", "IsAvailable"))
    sec.nextCastSpell = Invoke(false, Api("C_AssistedCombat", "GetNextCastSpell"))
end

local function SectionOverlay(sec)
    sec.namespace = type(_G.C_SpellActivationOverlay) == "table" and "present" or "absent"
    local overlayed = Api("C_SpellActivationOverlay", "IsSpellOverlayed")
    sec.shadowBoltOverlayed = Invoke(true, overlayed, SHADOW_BOLT)
    sec.shadowTranceOverlayed = Invoke(true, overlayed, SHADOW_TRANCE)
end

local function SectionItems(sec)
    sec.soulShardCount = Invoke(true, Api("C_Item", "GetItemCount"), SOUL_SHARD)
end

-- W1: the three C_Secrets enums per spell, whichever of them exist on this client.
local function SectionWhitelist(sec)
    sec.enum = "0 NeverSecret, 1 AlwaysSecret, 2 ContextuallySecret"
    local aura = Api("C_Secrets", "GetSpellAuraSecrecy")
    local cast = Api("C_Secrets", "GetSpellCastSecrecy")
    local cooldown = Api("C_Secrets", "GetSpellCooldownSecrecy")
    for _, id in ipairs(WHITELIST_IDS) do
        local entry = {}
        sec["s" .. id] = entry
        local ok, err = pcall(function()
            entry.aura = Invoke(true, aura, id)
            entry.cast = Invoke(true, cast, id)
            entry.cooldown = Invoke(true, cooldown, id)
        end)
        if not ok then entry.entryError = ErrText(err) end
    end
end

-- GCD: the global cooldown marker and two real spells; GCD_FIELDS carries isOnGCD, so
-- hasIsOnGCD says whether this client has the field at all. The plain values of
-- startTime, duration, isActive and isOnGCD are kept (GCD_KEEP).
local function SectionGcd(sec)
    local getCooldown = Api("C_Spell", "GetSpellCooldown")
    for _, id in ipairs(GCD_SECTION_SPELLS) do
        local entry = {}
        sec["s" .. id] = entry
        local ok, err = pcall(function()
            entry.cooldown = InvokeTableKeep(GCD_FIELDS, GCD_KEEP, getCooldown, id)
            local fields = entry.cooldown.fields
            if fields and fields.isOnGCD then entry.hasIsOnGCD = fields.isOnGCD.type ~= "nil" end
        end)
        if not ok then entry.entryError = ErrText(err) end
    end
end

local function SectionPet(sec)
    sec.unitExists = Invoke(true, Api("UnitExists"), "pet")
end

-- Only a PRIEST gets the priest snapshot in the main run; /fscheck priest runs it for any class.
local function SectionPriest(sec)
    local token = PP.ClassToken()
    sec.classToken = token or "unknown"
    if token ~= "PRIEST" then
        sec.skipped = "not a priest"
        return
    end
    PP.Snapshot(sec)
end

local SECTIONS = {
    { "env", SectionEnv },
    { "secrets", SectionSecrets },
    { "spells", SectionSpells },
    { "targetAuras", SectionTargetAuras },
    { "playerAuras", SectionPlayerAuras },
    { "vitals", SectionVitals },
    { "cooldowns", SectionCooldowns },
    { "targetIdentity", SectionTargetIdentity },
    { "assistedCombat", SectionAssistedCombat },
    { "spellOverlay", SectionOverlay },
    { "items", SectionItems },
    { "whitelist", SectionWhitelist },
    { "gcd", SectionGcd },
    { "pet", SectionPet },
    { "priest", SectionPriest },
}

local function TakeSnapshot(kind)
    local snap = { kind = kind, when = SafeDate() }
    for _, s in ipairs(SECTIONS) do
        Section(snap, s[1], s[2])
    end
    return snap
end

-------------------------------------------------------------------------------
-- Storage
-------------------------------------------------------------------------------

-- Account-wide ForeverSTUwaveDB is the one SavedVariable that restores on this
-- client (see the .toc). Looked up at call time because the saved globals land
-- after the addon's files run.
local function DB()
    if type(_G.ForeverSTUwaveDB) ~= "table" then _G.ForeverSTUwaveDB = {} end
    local root = _G.ForeverSTUwaveDB
    if type(root[KEY]) ~= "table" then root[KEY] = {} end
    return root[KEY]
end

local function Meta()
    local db = DB()
    if type(db.meta) ~= "table" then db.meta = {} end
    return db.meta
end

local function Say(text)
    print("fscheck: " .. text)
end

local function PartLine(done, label)
    return label .. (done and " done" or " waiting")
end

local function StatusLine()
    return string.format("armed. ooc snapshot done; %s; casts %d/%d%s; %s",
        state.combatDone and "combat snapshot done" or "combat snapshot waiting",
        state.castCount, CAST_TARGET, state.castsDone and " done" or "",
        PartLine(state.acDone, "aura test"))
end

-------------------------------------------------------------------------------
-- Event plumbing
-------------------------------------------------------------------------------

local function CallOn(frame, method, ...)
    if not frame then return end
    pcall(function(...)
        local fn = frame[method]
        if type(fn) == "function" then fn(frame, ...) end
    end, ...)
end

local function FrameCall(method, ...)
    CallOn(state.frame, method, ...)
end

local function UnregisterAll()
    CallOn(state.extra, "UnregisterAllEvents")
    FrameCall("UnregisterEvent", "PLAYER_REGEN_DISABLED")
    FrameCall("UnregisterEvent", "UNIT_SPELLCAST_SUCCEEDED")
    FrameCall("UnregisterEvent", "UNIT_SPELLCAST_START")
    FrameCall("UnregisterEvent", "PLAYER_TARGET_CHANGED")
    for _, event in ipairs(CAST_END_EVENTS) do FrameCall("UnregisterEvent", event) end
    for _, event in ipairs(CHANNEL_EVENTS) do FrameCall("UnregisterEvent", event) end
    FrameCall("UnregisterAllEvents")
end

local function Finish()
    if not (state.combatDone and state.castsDone and state.acDone) then return end
    if not state.armed then return end
    state.armed = false
    UnregisterAll()
    pcall(function() Meta().status = "done" end)
    Say("done, /reload or log out to save")
end

-------------------------------------------------------------------------------
-- AuraContainer visual test
-------------------------------------------------------------------------------

local function AcRecord()
    local db = DB()
    if type(db.auracontainer) ~= "table" then db.auracontainer = { steps = {} } end
    if type(db.auracontainer.steps) ~= "table" then db.auracontainer.steps = {} end
    return db.auracontainer
end

local function Step(name, fn, ...)
    local ac = AcRecord()
    local ok, err = pcall(fn, ...)
    ac.steps[name] = ok and "ok" or ErrText(err)
    return ok
end

-- Calls obj:method(...) if the method exists; records "absent" otherwise.
local function StepMethod(name, obj, method, ...)
    local ac = AcRecord()
    local okGet, fn = pcall(function() return obj[method] end)
    if not okGet or type(fn) ~= "function" then
        ac.steps[name] = "absent"
        return false
    end
    return Step(name, fn, obj, ...)
end

-- Calls obj:method(...) if it exists, swallowing any error. Used for the "turn it off"
-- calls where a failure costs nothing and must not stop the next one. Returns false only
-- when the method existed and threw; a missing method is not a failure.
local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

-- The minimum Plater's initAuraFrame does: an icon texture, a cooldown frame and a
-- duration fontstring, each handed to the button's own binder.
local function InitButton(button)
    -- First thing, before the button turns forbidden: the tiles must not take clicks
    -- or show tooltips while Parker is fighting (Plater_Auras.lua does the same).
    Quiet(button, "SetMouseMotionEnabled", false)
    Quiet(button, "SetMouseClickEnabled", false)
    Quiet(button, "SetHideTooltipInCombat", true)
    local ac = { steps = {} }
    local okAc, rec = pcall(AcRecord)
    if okAc and type(rec) == "table" then ac = rec end
    pcall(function() ac.initCalls = (ac.initCalls or 0) + 1 end)
    local function S(name, fn)
        local ok, err = pcall(fn)
        if not ok and not ac.initError then ac.initError = name .. ": " .. ErrText(err) end
    end
    local cooldown
    S("icon", function()
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetAllPoints(button)
        button:SetIcon(icon)
    end)
    S("cooldown", function()
        cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        Quiet(cooldown, "EnableMouse", false)
        Quiet(cooldown, "EnableMouseMotion", false)
        cooldown:SetAllPoints(button)
        if type(cooldown.SetHideCountdownNumbers) == "function" then
            cooldown:SetHideCountdownNumbers(true)
        end
        button:SetDurationCooldown(cooldown)
    end)
    S("durationText", function()
        local fs = (cooldown or button):CreateFontString(nil, "OVERLAY", "NumberFontNormal")
        fs:SetPoint("CENTER")
        local ok, err = pcall(button.SetDurationText, button, fs)
        if not ok then
            -- Plater always passes an options table; retry once so the record says
            -- whether the bare call was the problem.
            ac.durationTextBareError = ErrText(err)
            button:SetDurationText(fs, {})
        end
    end)
end

local function BuildContainer()
    local ac = AcRecord()
    ac.status = "building"

    local getTemplate = Api("C_XMLUtil", "GetTemplateInfo")
    if not getTemplate then
        ac.status = "absent: C_XMLUtil.GetTemplateInfo"
        return false
    end
    local rec = Invoke(true, getTemplate, TEMPLATE)
    ac.templateInfo = rec
    if not rec.ok then
        ac.status = "template check errored"
        return false
    end
    local d = rec.r1
    if d.type == "nil" or (d.type == "boolean" and d.value == false) then
        ac.status = "absent: " .. TEMPLATE
        return false
    end

    local frame = _G.FSCheckAuraContainer
    if frame == nil then
        local ok, result = pcall(CreateFrame, "AuraContainer", "FSCheckAuraContainer", UIParent, TEMPLATE)
        ac.steps.createFrame = ok and "ok" or ErrText(result)
        if not ok then
            ac.status = "create failed"
            return false
        end
        frame = result
    else
        ac.steps.createFrame = "reused"
    end
    state.container = frame
    -- Hidden until the combat snapshot starts the 30s test row.
    StepMethod("hide", frame, "Hide")

    StepMethod("setSize", frame, "SetSize", 1, 1)
    -- TOPLEFT so the row grows right and down from here; the label sits above it.
    StepMethod("setPoint", frame, "SetPoint", "TOPLEFT", UIParent, "CENTER", -100, 200)

    local sortMethod = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local sortDirection = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    local layout = {
        elementSpacing = 2,
        lineSpacing = 2,
        groupLineSpacing = 2,
        elementWidth = 24,
        elementHeight = 24,
    }
    local options = {
        maxFrameCount = 8,
        sortMethod = sortMethod,
        sortDirection = sortDirection,
        initializeFrame = InitButton,
        layout = layout,
    }
    if not state.groupAdded then
        if StepMethod("addAuraGroup", frame, "AddAuraGroup", "mine", HARMFUL_MINE, options) then
            state.groupAdded = true
        end
    else
        ac.steps.addAuraGroup = "reused"
    end
    StepMethod("setAuraGroupLayout", frame, "SetAuraGroupLayout", "mine", layout)

    local flow = type(_G.AnchorUtil) == "table" and _G.AnchorUtil.FlowDirection or nil
    if type(flow) == "table" and flow.Right ~= nil and flow.Down ~= nil then
        StepMethod("setFlowLayoutAnchorPoint", frame, "SetFlowLayoutAnchorPoint", "TOPLEFT")
        StepMethod("setFlowLayoutGrowthDirection", frame, "SetFlowLayoutGrowthDirection", flow.Right, flow.Down)
    else
        ac.steps.setFlowLayoutGrowthDirection = "absent: AnchorUtil.FlowDirection"
    end

    Step("label", function()
        local holder = _G.FSCheckAuraLabel
        if holder == nil then
            holder = CreateFrame("Frame", "FSCheckAuraLabel", UIParent)
            holder:SetSize(120, 12)
            holder:SetPoint("BOTTOMLEFT", UIParent, "CENTER", -100, 206)
            local text = holder:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            text:SetPoint("LEFT")
            text:SetText("aura preview")
        end
        holder:Hide()
        state.label = holder
    end)

    ac.status = "built"
    state.acBuilt = true
    return true
end

local function HideContainer(runId)
    if runId ~= state.runId then return end
    state.rowLive = false
    FrameCall("UnregisterEvent", "PLAYER_TARGET_CHANGED")
    if state.container then
        StepMethod("hide", state.container, "Hide")
        StepMethod("setEnabledFalse", state.container, "SetEnabled", false)
    end
    if state.label then StepMethod("hideLabel", state.label, "Hide") end
    local ac = AcRecord()
    ac.hidden = true
    state.acDone = true
    Say("aura test finished (" .. tostring(ac.initCalls or 0) .. " buttons built)")
    Finish()
end

local function ShowContainer()
    local ac = AcRecord()
    if not state.acBuilt or not state.container then
        state.acDone = true
        return
    end
    local frame = state.container
    StepMethod("setUnit", frame, "SetUnit", "target")
    StepMethod("setEnabledTrue", frame, "SetEnabled", true)
    StepMethod("show", frame, "Show")
    if state.label then StepMethod("showLabel", state.label, "Show") end
    ac.shown = true
    -- A retarget inside the 30s window must re-point the row, or it keeps the old
    -- target's auras.
    state.rowLive = true
    FrameCall("RegisterEvent", "PLAYER_TARGET_CHANGED")

    local runId = state.runId
    local after = Api("C_Timer", "After")
    local ok = after and pcall(after, AURA_SHOW_SECONDS, function()
        local okh, err = pcall(HideContainer, runId)
        if not okh then pcall(function() AcRecord().hideError = ErrText(err) end) end
    end)
    if not ok then
        ac.timerError = "C_Timer.After unavailable; hidden immediately"
        HideContainer(runId)
    end
end

-------------------------------------------------------------------------------
-- Combat snapshot
-------------------------------------------------------------------------------

-- onError is what to answer when the check itself fails (default true: see below).
local function LockedDown(onError)
    local ok, locked = pcall(function()
        local fn = _G.InCombatLockdown
        if type(fn) ~= "function" then return false end
        return fn() and true or false
    end)
    -- If the check itself failed, do not skip: a snapshot with its own errors in it
    -- is worth more than waiting for a second pull.
    if not ok then return onError ~= false end
    return locked
end

local function TakeCombatSnapshot()
    local snap = TakeSnapshot("combat")
    snap.combatSkips = state.combatSkips
    DB().combat = snap
    pcall(function() Meta().combatDone = true end)
    state.combatDone = true
    FrameCall("UnregisterEvent", "PLAYER_REGEN_DISABLED")
    Say("combat snapshot saved")
    ShowContainer()
    Finish()
end

local function OnCombatTimer(runId)
    if runId ~= state.runId or state.combatDone then return end
    state.combatPending = false
    if not LockedDown() then
        -- Combat ended inside the delay: nothing worth recording. Stay armed.
        state.combatSkips = state.combatSkips + 1
        return
    end
    TakeCombatSnapshot()
end

local function ScheduleCombatSnapshot()
    if state.combatDone or state.combatPending then return end
    state.combatPending = true
    local runId = state.runId
    local after = Api("C_Timer", "After")
    local ok = after and pcall(after, COMBAT_DELAY, function()
        local okc, err = pcall(OnCombatTimer, runId)
        if not okc then pcall(function() Meta().timerError = ErrText(err) end) end
    end)
    if not ok then
        -- No timer: take the snapshot now rather than never.
        state.combatPending = false
        pcall(function() Meta().combatDelay = "none (C_Timer.After unavailable)" end)
        TakeCombatSnapshot()
    end
end

-------------------------------------------------------------------------------
-- Cast recorder
-------------------------------------------------------------------------------

local function DescribeArgs(rec, ...)
    local n = select("#", ...)
    rec.argCount = n
    for i = 1, math.min(n, 6) do
        -- Only the spellID (third arg) may keep its value, and only when plain.
        rec["arg" .. i] = Desc((select(i, ...)), i == 3)
    end
end

local function RecordCast(event, ...)
    local rec = { event = event }
    DescribeArgs(rec, ...)
    rec.targetGUID = Invoke(false, Api("UnitGUID"), "target")
    rec.inCombatLockdown = Invoke(true, Api("InCombatLockdown"))
    rec.time = Invoke(true, Api("GetTime"))
    return rec
end

-- The plain spellID (third arg) of a cast event, or nil when it is missing or secret.
local function PlainSpellID(...)
    if select("#", ...) < 3 then return nil end
    local id = select(3, ...)
    if IsSecret(id) or type(id) ~= "number" then return nil end
    return id
end

-- True for a table that is safe to index: issecretvalue AND issecrettable both cleared it.
-- A throwing issecrettable counts as secret; a missing one means the API does not exist,
-- so the table is plain (the same rule as SecretTable and NoteTable).
local function IsPlainTable(v)
    if type(v) ~= "table" or IsSecret(v) then return false end
    return not SecretTable(v)
end

-- A plain GetTime(), or nil.
local function PlainTime()
    local rec, now = Invoke(false, Api("GetTime"))
    if rec.ok and type(now) == "number" and not IsSecret(now) then return now end
    return nil
end

-- The known spells of GCD_CHECK_SPELLS, in order (a non-empty result is cached per run).
local function GcdKnown()
    if state.gcdKnown then return state.gcdKnown end
    local isPlayerSpell = Api("IsPlayerSpell")
    local isKnown = Api("C_SpellBook", "IsSpellKnown")
    local known = {}
    for _, id in ipairs(GCD_CHECK_SPELLS) do
        if KeptBool(Invoke(true, isPlayerSpell, id)) == true or KeptBool(Invoke(true, isKnown, id)) == true then
            known[#known + 1] = id
        end
    end
    -- An empty list is not cached: the spellbook may simply not be loaded yet.
    if #known > 0 then state.gcdKnown = known end
    return known
end

-- The first known check spell whose NAME differs from the just-cast spell's (a plain
-- compare, after SpellName's IsSecret checks), or nil. A check id equal to the plain
-- castID is always skipped, so a cast spell whose name cannot be read is still excluded.
local function GcdSpell(castID, castName)
    for _, id in ipairs(GcdKnown()) do
        if id ~= castID then
            local name = castName and SpellName(id) or nil
            if not (castName and name and name == castName) then return id end
        end
    end
    return nil
end

-- Describes `keys` of a plain cooldown table into `out`, values kept when plain. A secret
-- table (either predicate) is never indexed.
local function ReadCooldownKeys(out, rec, v, keys)
    if not (rec.ok and rec.r1 and rec.r1.isSecret == false and IsPlainTable(v)) then return end
    for _, key in ipairs(keys) do
        local okf, f = pcall(function() return v[key] end)
        if okf then out[key] = Desc(f, true) else out[key] = { err = ErrText(f) } end
    end
end

-- The cast time of the spell just cast: C_Spell.GetSpellInfo(id).castTime (ms) while it is
-- plain, else the START -> SUCCEEDED elapsed seconds, else nothing.
local function CastTime(castID, elapsed)
    if castID then
        local rec, info = Invoke(false, Api("C_Spell", "GetSpellInfo"), castID)
        if rec.ok and IsPlainTable(info) then
            local ms = PlainNumberField(info, "castTime")
            if ms then return { source = "spellinfo", value = ms } end
        end
    end
    if elapsed then return { source = "elapsed", value = elapsed } end
    return { source = "none" }
end

-- One GCD sample, taken right after a SUCCEEDED or at a START. Reads the cooldown table of
-- a spell that has no cooldown of its own (isActive / isOnGCD) and of the GCD marker 61304
-- as the control, plus GetTime, plus the cast spell's castTime. A cast-time spell reads its
-- GCD as already over after SUCCEEDED, so the START sample is the one where the GCD is
-- certainly running. A secret table is never indexed.
local function GcdCheck(castID, elapsed)
    local out = {}
    local ok, err = pcall(function()
        local getCooldown = Api("C_Spell", "GetSpellCooldown")
        local crec, cv = Invoke(false, getCooldown, GCD_MARKER)
        out.control = { call = crec }
        ReadCooldownKeys(out.control, crec, cv, GCD_CONTROL_KEYS)
        out.control.time = Invoke(true, Api("GetTime"))
        out.castTime = CastTime(castID, elapsed)

        local known = GcdKnown()
        if #known == 0 then
            out.skipped = "no known spell"
            return
        end
        local id = GcdSpell(castID, castID and SpellName(castID) or nil)
        if not id then
            out.skipped = "no usable spell"
            return
        end
        out.spellId = id
        local rec, v = Invoke(false, getCooldown, id)
        out.call = rec
        ReadCooldownKeys(out, rec, v, { "isActive", "isOnGCD" })
    end)
    if not ok then out.error = ErrText(err) end
    return out
end

-- START of a (non-Shoot) player cast: remember when, for the elapsed-time castTime.
local function NoteCastStart(castID)
    state.startAt, state.startSpell = nil, nil
    local now = PlainTime()
    if now and castID then
        state.startAt, state.startSpell = now, castID
    end
end

-- The remembered START is dropped when the cast ends without succeeding.
local function ClearCastStart()
    state.startAt, state.startSpell = nil, nil
end

-- Seconds since the START of the same spell, or nil. Consumes the remembered START. An
-- elapsed time of MAX_CAST_ELAPSED seconds or more is a stale START, not a cast time.
local function TakeCastElapsed(castID)
    local at, spell = state.startAt, state.startSpell
    ClearCastStart()
    if not at or not castID or spell ~= castID then return nil end
    local now = PlainTime()
    if not now then return nil end
    local elapsed = now - at
    if elapsed < 0 or elapsed >= MAX_CAST_ELAPSED then return nil end
    return elapsed
end

local function RecordSucceeded(event, ...)
    local rec = RecordCast(event, ...)
    local castID = PlainSpellID(...)
    rec.gcd = GcdCheck(castID, TakeCastElapsed(castID))
    return rec
end

local function RecordStart(event, ...)
    local rec = RecordCast(event, ...)
    rec.gcd = GcdCheck(PlainSpellID(...))
    return rec
end

local function RecordChannel(event, ...)
    local rec = RecordCast(event, ...)
    local info = Invoke(false, Api("UnitChannelInfo"), "player")
    -- Return order per the 12.1 UnitChannelInfo documentation.
    rec.channelInfo = {
        ok = info.ok, err = info.err, exists = info.exists, n = info.n,
        name = info.r1, startTimeMs = info.r4, endTimeMs = info.r5,
        notInterruptible = info.r7, spellID = info.r8,
    }
    return rec
end

local function AppendTo(name, rec)
    local db = DB()
    if type(db[name]) ~= "table" then db[name] = {} end
    db[name][#db[name] + 1] = rec
end

local function FinishCasts()
    state.castsDone = true
    FrameCall("UnregisterEvent", "UNIT_SPELLCAST_SUCCEEDED")
    FrameCall("UnregisterEvent", "UNIT_SPELLCAST_START")
    for _, event in ipairs(CAST_END_EVENTS) do FrameCall("UnregisterEvent", event) end
    for _, event in ipairs(CHANNEL_EVENTS) do FrameCall("UnregisterEvent", event) end
    pcall(function() Meta().castsDone = true end)
    Say("cast recorder saved (" .. state.castCount .. " casts, " .. state.channelCount .. " channel events)")
    Finish()
end

-- The unit filter is a RegisterUnitEvent job. If that fell back to a plain
-- RegisterEvent, drop foreign units here; a secret unit is kept and described.
local function WrongUnit(unit)
    if IsSecret(unit) then return false end
    return unit ~= "player"
end

-- UNIT_AURA is registered for two units, so a plain RegisterEvent fallback has to drop
-- the rest here; a secret unit is kept and described.
local function WrongAuraUnit(unit)
    if IsSecret(unit) then return false end
    return unit ~= "player" and unit ~= "target"
end

-- True for a plain spellID (third arg) of the wand Shoot. A secret or missing one is not.
local function IsShoot(...)
    return PlainSpellID(...) == SHOOT
end

local function RecordAura(event, unit, info)
    local rec = { event = event, unit = Desc(unit, true), info = Desc(info) }
    rec.inCombatLockdown = Invoke(true, Api("InCombatLockdown"))
    rec.time = Invoke(true, Api("GetTime"))
    -- Only a plain table is ever indexed: IsSecret fails closed, and a table that
    -- issecrettable calls secret is skipped even when issecretvalue cleared it.
    NoteTable(rec.info, info)
    if type(info) == "table" and rec.info.isSecret == false and rec.info.issecrettable ~= true then
        local fields = {}
        rec.fields = fields
        for _, key in ipairs(AURA_UPDATE_FIELDS) do
            local ok, v = pcall(function() return info[key] end)
            if ok then
                local d = Desc(v, key == "isFullUpdate")
                -- Only a table both issecretvalue and issecrettable cleared is measured.
                if d.type == "table" and IsPlainTable(v) then
                    local okc, n = pcall(function() return #v end)
                    if okc and type(n) == "number" and not IsSecret(n) then d.count = n end
                end
                fields[key] = d
            else
                fields[key] = { err = ErrText(v) }
            end
        end
    end
    return rec
end

local function RecordProc(event, spellID)
    local rec = { event = event, spellID = Desc(spellID, true) }
    rec.inCombatLockdown = Invoke(true, Api("InCombatLockdown"))
    rec.time = Invoke(true, Api("GetTime"))
    return rec
end

local function Handle(event, ...)
    if event == AURA_EVENT then
        -- Two budgets, so out-of-combat churn (buff upkeep, target swaps) cannot spend the
        -- in-combat samples this check exists for. A failed lockdown check counts as out.
        local inCombat = LockedDown(false)
        if WrongAuraUnit((...)) then return end
        if inCombat then
            if state.auraCombat >= AURA_COMBAT_CAP then return end
            state.auraCombat = state.auraCombat + 1
        else
            if state.auraOoc >= AURA_OOC_CAP then return end
            state.auraOoc = state.auraOoc + 1
        end
        AppendTo("unitAura", RecordAura(event, ...))
        if state.auraOoc >= AURA_OOC_CAP and state.auraCombat >= AURA_COMBAT_CAP then
            CallOn(state.extra, "UnregisterEvent", AURA_EVENT)
        end
        return
    end
    for _, name in ipairs(PROC_EVENTS) do
        if event == name then
            if state.procCount >= PROC_CAP then return end
            state.procCount = state.procCount + 1
            AppendTo("procGlow", RecordProc(event, ...))
            if state.procCount >= PROC_CAP then
                for _, e in ipairs(PROC_EVENTS) do CallOn(state.extra, "UnregisterEvent", e) end
            end
            return
        end
    end
    if event == "PLAYER_REGEN_DISABLED" then
        ScheduleCombatSnapshot()
        return
    end
    if event == "PLAYER_TARGET_CHANGED" then
        if state.rowLive and state.container then
            -- SetUnit returns early when the token is unchanged ("target" stays "target"),
            -- so on its own it does nothing on a retarget. Blizzard's TargetFrame and
            -- ElvUI call UpdateAllAuras() for the refresh; both calls stay, the second
            -- feature-detected.
            local okSet = pcall(function() state.container:SetUnit("target") end)
            local okRefresh = Quiet(state.container, "UpdateAllAuras")
            pcall(function()
                local ac = AcRecord()
                ac.retargets = (ac.retargets or 0) + 1
                if not (okSet and okRefresh) then ac.retargetErrors = (ac.retargetErrors or 0) + 1 end
            end)
        end
        return
    end
    if state.castsDone then return end
    if event == "UNIT_SPELLCAST_START" then
        if WrongUnit((...)) or IsShoot(...) then return end
        NoteCastStart(PlainSpellID(...))
        if state.startCount < GCD_START_CAP then
            state.startCount = state.startCount + 1
            AppendTo("gcdStart", RecordStart(event, ...))
        end
        return
    end
    for _, name in ipairs(CAST_END_EVENTS) do
        if event == name then
            if not WrongUnit((...)) then ClearCastStart() end
            return
        end
    end
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        if WrongUnit((...)) then return end
        if IsShoot(...) then
            -- The wand has its own timing, so no GCD sample for it.
            if state.shootCount < SHOOT_CAP then
                state.shootCount = state.shootCount + 1
                AppendTo("shoot", RecordCast(event, ...))
            end
            return
        end
        state.castCount = state.castCount + 1
        AppendTo("casts", RecordSucceeded(event, ...))
        if state.castCount >= CAST_TARGET then FinishCasts() end
        return
    end
    for _, name in ipairs(CHANNEL_EVENTS) do
        if event == name then
            if WrongUnit((...)) then return end
            if IsShoot(...) then
                if state.shootCount < SHOOT_CAP then
                    state.shootCount = state.shootCount + 1
                    AppendTo("shoot", RecordChannel(event, ...))
                end
                return
            end
            if state.channelCount >= CHANNEL_CAP then return end
            state.channelCount = state.channelCount + 1
            AppendTo("channel", RecordChannel(event, ...))
            return
        end
    end
end

local function OnEvent(_, event, ...)
    local ok, err = pcall(Handle, event, ...)
    if not ok then
        pcall(function() Meta().lastError = ErrText(err) end)
    end
end

local function EnsureFrame()
    if state.frame then return true end
    local ok, frame = pcall(CreateFrame, "Frame")
    if not ok or not frame then
        pcall(function() Meta().frameError = ErrText(frame) end)
        return false
    end
    state.frame = frame
    local okScript = pcall(frame.SetScript, frame, "OnEvent", OnEvent)
    return okScript
end

local function EnsureExtraFrame()
    if state.extra then return true end
    local ok, frame = pcall(CreateFrame, "Frame")
    if not ok or not frame then
        pcall(function() Meta().extraFrameError = ErrText(frame) end)
        return false
    end
    state.extra = frame
    return (pcall(frame.SetScript, frame, "OnEvent", OnEvent))
end

-- Every failed registration is kept (appended, capped), not just the last one.
local function NoteRegisterError(err)
    pcall(function()
        local meta = Meta()
        local text = ErrText(err)
        if type(meta.registerError) == "string" and meta.registerError ~= "" then
            text = meta.registerError .. " | " .. text
        end
        meta.registerError = string.sub(text, 1, MAX_REGISTER_ERR)
    end)
end

-- UNIT_AURA (player and target) and the proc glow events live on their own frame:
-- RegisterUnitEvent's unit whitelist is frame-wide, so sharing the cast frame would
-- narrow one of the two.
local function RegisterExtras()
    if not EnsureExtraFrame() then return end
    local frame = state.extra
    local ok = pcall(frame.RegisterUnitEvent, frame, AURA_EVENT, "player", "target")
    if not ok then
        local ok2, err = pcall(frame.RegisterEvent, frame, AURA_EVENT)
        if not ok2 then NoteRegisterError(err) end
    end
    for _, event in ipairs(PROC_EVENTS) do
        local ok3, err = pcall(frame.RegisterEvent, frame, event)
        if not ok3 then NoteRegisterError(err) end
    end
end

local function RegisterUnit(event)
    local frame = state.frame
    local ok = pcall(frame.RegisterUnitEvent, frame, event, "player")
    if not ok then
        local ok2, err = pcall(frame.RegisterEvent, frame, event)
        if not ok2 then NoteRegisterError(err) end
    end
end

-------------------------------------------------------------------------------
-- /fscheck gunsight: feature checks for the gunsight HUD
-------------------------------------------------------------------------------
-- One slash call runs the immediate checks and arms the two that need a live event: the
-- vertical bar fed a real cast duration (next UNIT_SPELLCAST_START for "player") and the
-- C_UnitAuras reads on a target in combat (next PLAYER_REGEN_DISABLED). Everything is stored
-- in ForeverSTUwaveDB.fscheck.gunsight[<check>]. Only booleans, plain numbers and short
-- plain strings are stored; a secret becomes the string "secret", an error its (capped) text.
-- Every helper hangs off the one table GS: this file is near Lua 5.1's limit of 200 locals
-- per chunk, and the gunsight code is the part that keeps growing.

local GS = {}

GS.COMBAT_DELAY = 2
GS.COMBAT_MAX_ATTEMPTS = 10
GS.SAMPLE_DELAY = 0.5
GS.TEX = "Interface\\Buttons\\WHITE8X8"
GS.FILTER_MINE = "HARMFUL|PLAYER"
GS.FILTER_HELPFUL = "HELPFUL"
-- UL, LL, UR, LR as (x, y) pairs: the full texture turned 90 degrees (a rotation, not a mirror).
GS.ROT90 = { 0, 1, 1, 1, 0, 0, 1, 0 }
GS.NAME_NEEDLES = { "Duration", "InstanceID" }
GS.MAX_NAMES = 40

-- A plain boolean/number/short string, or "secret", "nil", "nonfinite" or "(type)".
function GS.Plain(v)
    if IsSecret(v) then return "secret" end
    local t = type(v)
    if t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "nonfinite" end
        return v
    end
    if t == "boolean" then return v end
    if t == "string" then return string.sub(v, 1, MAX_STR) end
    if t == "nil" then return "nil" end
    return "(" .. t .. ")"
end

function GS.Record()
    local db = DB()
    if type(db.gunsight) ~= "table" then db.gunsight = {} end
    return db.gunsight
end

function GS.Section(key)
    local gs = GS.Record()
    if type(gs[key]) ~= "table" then gs[key] = {} end
    return gs[key]
end

-- Stores the one-line summary beside the check and prints it.
function GS.Report(key, text)
    pcall(function() GS.Section(key).summary = text end)
    Say("gunsight " .. key .. ": " .. text)
end

function GS.Method(obj, name)
    local okGet, fn = pcall(function() return obj[name] end)
    if okGet and type(fn) == "function" then return fn end
    return nil
end

-- obj:name(...) under pcall. Returns exists, ok, then the packed returns and their count
-- (or the error text when it threw). The returns may be secret: only GS.Plain/IsSecret them.
function GS.Call(obj, name, ...)
    local fn = GS.Method(obj, name)
    if not fn then return false end
    local n, t = Pack(pcall(fn, obj, ...))
    if t[1] ~= true then return true, false, ErrText(t[2]) end
    return true, true, t, n - 1
end

-- "ok", "absent" or the error text of one method call.
function GS.Step(obj, name, ...)
    local exists, ok, res = GS.Call(obj, name, ...)
    if not exists then return "absent" end
    if not ok then return res end
    return "ok"
end

-- The first return of obj:name(...) as a GS.Plain value, "absent" or "error: ...".
function GS.Read(obj, name, ...)
    local exists, ok, res = GS.Call(obj, name, ...)
    if not exists then return "absent" end
    if not ok then return "error: " .. res end
    return GS.Plain(res[2])
end

-- All returns of obj:name() as one comma list of GS.Plain values, plus how many there were.
function GS.ReadList(obj, name)
    local exists, ok, res, n = GS.Call(obj, name)
    if not exists then return "absent", 0 end
    if not ok then return "error: " .. res, 0 end
    local out = {}
    for i = 1, math.min(n, MAX_RETURNS) do out[i] = tostring(GS.Plain(res[i + 1])) end
    return table.concat(out, ","), n
end

function GS.Host()
    if state.gsHost then return state.gsHost end
    local host = CreateFrame("Frame", nil, UIParent)
    host:SetSize(64, 64)
    host:SetPoint("CENTER")
    -- Shown (an animated bar does not tick while hidden) but invisible and click-through.
    host:SetAlpha(0)
    host:EnableMouse(false)
    state.gsHost = host
    return host
end

function GS.Timer(delay, fn)
    local after = Api("C_Timer", "After")
    if not after then return false end
    return (pcall(after, delay, fn))
end

-- The check's test objects are built once and cached on `state`, so re-running the check
-- never grows the frame count (a frame or texture cannot be destroyed). Each check hides its
-- object when it is done, and GS.HideObjects (every Disarm) hides whatever is left.
function GS.Obj(key, make)
    local obj = state.gsObjs[key]
    if obj == nil then
        obj = make(GS.Host())
        state.gsObjs[key] = obj
    end
    return obj
end

function GS.Hide(obj)
    if obj then pcall(function() obj:Hide() end) end
end

function GS.HideObjects()
    for _, obj in pairs(state.gsObjs) do GS.Hide(obj) end
    GS.AcHide()
end

function GS.Tex(key)
    local tex = GS.Obj(key, function(host)
        local t = host:CreateTexture(nil, "ARTWORK")
        t:SetTexture(GS.TEX)
        return t
    end)
    tex:Show()
    return tex
end

-- A vertical StatusBar at value 0, shown. Callers hide it when their trial is over.
function GS.Bar(key)
    local bar = GS.Obj(key, function(host)
        local b = CreateFrame("StatusBar", nil, host)
        b:SetSize(8, 48)
        b:SetPoint("CENTER")
        b:SetStatusBarTexture(GS.TEX)
        b:SetMinMaxValues(0, 1)
        return b
    end)
    bar:SetValue(0)
    bar:Show()
    return bar
end

function GS.Num(v, expected)
    return type(v) == "number" and not IsSecret(v) and math.abs(v - expected) < 0.0001
end

-- 1. 8-argument SetTexCoord ------------------------------------------------------------------

function GS.CheckTexCoord(rec, _host)
    local tex = GS.Tex("texcoord")
    local exists, ok, res = GS.Call(tex, "SetTexCoord", unpack(GS.ROT90))
    rec.exists = exists
    rec.accepted = exists and ok or false
    if exists and not ok then rec.err = res end
    local list, n = GS.ReadList(tex, "GetTexCoord")
    rec.readback = list
    rec.readbackCount = n
    local match = n == 8
    if match then
        local _, _, t = GS.Call(tex, "GetTexCoord")
        for i = 1, 8 do
            if not GS.Num(t[i + 1], GS.ROT90[i]) then match = false end
        end
    end
    rec.readbackMatches = match
    -- Baseline: the classic 4-argument form, to see how many values GetTexCoord gives back.
    rec.fourArgStep = GS.Step(tex, "SetTexCoord", 0, 1, 0, 1)
    local list4, n4 = GS.ReadList(tex, "GetTexCoord")
    rec.fourArgReadback = list4
    rec.fourArgReadbackCount = n4
    local verdict
    if not exists then
        verdict = "SetTexCoord absent"
    elseif not ok then
        verdict = "8 args REJECTED: " .. tostring(res)
    elseif match then
        verdict = "8 args accepted, readback matches the rotation"
    else
        verdict = "8 args accepted, readback differs (" .. tostring(list) .. ")"
    end
    rec.verdict = verdict
    GS.Hide(tex)
    GS.Report("texcoord8", verdict)
end

-- 2. SetVertexColorFromBoolean ---------------------------------------------------------------

function GS.ColorTrial(tex, makeA, makeB)
    local out = {}
    local okMake, a, b = pcall(function() return makeA(), makeB() end)
    if not okMake then
        out.build = ErrText(a)
        return out
    end
    out.trueStep = GS.Step(tex, "SetVertexColorFromBoolean", true, a, b)
    out.trueReadback = GS.ReadList(tex, "GetVertexColor")
    out.falseStep = GS.Step(tex, "SetVertexColorFromBoolean", false, a, b)
    out.falseReadback = GS.ReadList(tex, "GetVertexColor")
    return out
end

function GS.CheckVertexColor(rec, _host)
    local tex = GS.Tex("vertexColor")
    rec.exists = GS.Method(tex, "SetVertexColorFromBoolean") ~= nil
    if not rec.exists then
        GS.Hide(tex)
        rec.verdict = "SetVertexColorFromBoolean absent on Texture"
        GS.Report("vertexColorFromBoolean", rec.verdict)
        return
    end
    local mk = _G.CreateColor
    if type(mk) == "function" then
        rec.colorObjects = GS.ColorTrial(tex, function() return mk(1, 0, 0, 1) end, function() return mk(0, 1, 0, 1) end)
    else
        rec.colorObjects = { build = "CreateColor absent" }
    end
    rec.plainTables = GS.ColorTrial(tex,
        function() return { r = 1, g = 0, b = 0, a = 1 } end,
        function() return { r = 0, g = 1, b = 0, a = 1 } end)
    local c = rec.colorObjects
    local works = c.trueStep == "ok" and c.falseStep == "ok"
    rec.worksWithColorObjects = works
    if works then
        rec.verdict = "exists; plain boolean + CreateColor objects work (true " .. tostring(c.trueReadback)
            .. " | false " .. tostring(c.falseReadback) .. ")"
    else
        rec.verdict = "exists; plain boolean call FAILED with color objects: "
            .. tostring(c.build or c.trueStep) .. " | tables: " .. tostring(rec.plainTables.trueStep)
    end
    GS.Hide(tex)
    GS.Report("vertexColorFromBoolean", rec.verdict)
end

-- 3. Vertical StatusBar + SetTimerDuration ---------------------------------------------------

-- Feeds `duration` to the bar and records orientation, the call result and GetValue now and
-- GS.SAMPLE_DELAY seconds later. onDone runs after the second sample (or at once without a timer).
function GS.BarTrial(rec, bar, duration, run, onDone)
    rec.setOrientation = GS.Step(bar, "SetOrientation", "VERTICAL")
    rec.orientation = GS.Read(bar, "GetOrientation")
    rec.durationType = type(duration)
    rec.durationSecret = IsSecret(duration)
    rec.setTimerDuration = GS.Step(bar, "SetTimerDuration", duration)
    rec.valueAt0 = GS.Read(bar, "GetValue")
    local function finish()
        local a, b = rec.valueAt0, rec.valueAt05
        if type(a) == "number" and type(b) == "number" then
            rec.moved = a ~= b
        else
            rec.moved = "unreadable"
        end
        if onDone then pcall(onDone) end
    end
    local timed = GS.Timer(GS.SAMPLE_DELAY, function()
        if run ~= state.gsRun then return end
        local ok, err = pcall(function() rec.valueAt05 = GS.Read(bar, "GetValue") end)
        if not ok then rec.sampleError = ErrText(err) end
        finish()
    end)
    if not timed then
        rec.sampleNote = "C_Timer.After unavailable, no second sample"
        finish()
    end
end

function GS.BarSummary(label, rec)
    return label .. ": orientation " .. tostring(rec.orientation) .. ", SetOrientation " .. tostring(rec.setOrientation)
        .. ", SetTimerDuration " .. tostring(rec.setTimerDuration) .. ", GetValue "
        .. tostring(rec.valueAt0) .. " -> " .. tostring(rec.valueAt05) .. " (moved " .. tostring(rec.moved) .. ")"
end

function GS.CheckBarManual(rec, _host, run)
    local bar = GS.Bar("manualBar")
    rec.hasSetOrientation = GS.Method(bar, "SetOrientation") ~= nil
    rec.hasSetTimerDuration = GS.Method(bar, "SetTimerDuration") ~= nil
    local util = _G.C_DurationUtil
    local create = type(util) == "table" and util.CreateDuration or nil
    rec.hasCreateDuration = type(create) == "function"
    rec.castPart = "waits for the next UNIT_SPELLCAST_START for player"
    local manual = {}
    rec.manual = manual
    if not rec.hasCreateDuration then
        manual.skipped = "C_DurationUtil.CreateDuration absent"
        manual.setOrientation = GS.Step(bar, "SetOrientation", "VERTICAL")
        manual.orientation = GS.Read(bar, "GetOrientation")
        GS.Hide(bar)
        GS.Report("verticalBarTimer", "no C_DurationUtil.CreateDuration, orientation "
            .. tostring(manual.orientation) .. "; waiting for a real cast")
        return
    end
    local okMake, duration = pcall(create)
    if not okMake then
        manual.skipped = "CreateDuration threw: " .. ErrText(duration)
        GS.Hide(bar)
        GS.Report("verticalBarTimer", manual.skipped)
        return
    end
    local now = Api("GetTime") and select(2, pcall(_G.GetTime)) or 0
    if type(now) ~= "number" or IsSecret(now) then now = 0 end
    manual.setTimeFromStart = GS.Step(duration, "SetTimeFromStart", now, 3)
    GS.BarTrial(manual, bar, duration, run, function()
        GS.Hide(bar)
        GS.Report("verticalBarTimer", GS.BarSummary("manual 3s duration", manual) .. "; cast part waits for your next cast")
    end)
end

function GS.CheckBarCast(run)
    local rec = GS.Section("verticalBarTimer")
    local cast = {}
    rec.cast = cast
    local fn = Api("UnitCastingDuration")
    if not fn then
        cast.skipped = "UnitCastingDuration absent"
        GS.Report("verticalBarTimer", "cast: " .. cast.skipped)
        return
    end
    local ok, duration = pcall(fn, "player")
    if not ok then
        cast.skipped = "UnitCastingDuration threw: " .. ErrText(duration)
        GS.Report("verticalBarTimer", "cast: " .. cast.skipped)
        return
    end
    local bar = GS.Bar("castBar")
    GS.BarTrial(cast, bar, duration, run, function()
        GS.Hide(bar)
        GS.Report("verticalBarTimer", GS.BarSummary("real cast", cast))
    end)
end

-- 4. CreateLine ------------------------------------------------------------------------------

function GS.CheckLine(rec, host)
    rec.exists = GS.Method(host, "CreateLine") ~= nil
    if not rec.exists then
        rec.verdict = "Frame:CreateLine absent"
        GS.Report("line", rec.verdict)
        return
    end
    local ok, line = pcall(GS.Obj, "line", function(h) return h:CreateLine(nil, "OVERLAY") end)
    rec.created = ok
    if not ok then
        rec.err = ErrText(line)
        rec.verdict = "CreateLine threw: " .. rec.err
        GS.Report("line", rec.verdict)
        return
    end
    local steps = {}
    rec.steps = steps
    steps.setStartPoint = GS.Step(line, "SetStartPoint", "BOTTOMLEFT", host, 0, 0)
    steps.setEndPoint = GS.Step(line, "SetEndPoint", "TOPRIGHT", host, 0, 0)
    steps.setThickness = GS.Step(line, "SetThickness", 2)
    steps.setColorTexture = GS.Step(line, "SetColorTexture", 1, 1, 1, 1)
    steps.show = GS.Step(line, "Show")
    rec.thicknessReadback = GS.Read(line, "GetThickness")
    rec.startPointReadback = GS.ReadList(line, "GetStartPoint")
    rec.endPointReadback = GS.ReadList(line, "GetEndPoint")
    GS.Hide(line)
    local allOk = steps.setStartPoint == "ok" and steps.setEndPoint == "ok" and steps.setThickness == "ok"
    rec.drawable = allOk
    if allOk then
        rec.verdict = "line drawable (thickness readback " .. tostring(rec.thicknessReadback) .. ")"
    else
        rec.verdict = "line steps failed: start " .. tostring(steps.setStartPoint) .. ", end "
            .. tostring(steps.setEndPoint) .. ", thickness " .. tostring(steps.setThickness)
    end
    GS.Report("line", rec.verdict)
end

-- 5. C_UnitAuras instance ids and aura durations ---------------------------------------------

-- C_UnitAuras functions whose name mentions Duration or InstanceID, sorted, capped.
function GS.AuraNames()
    local owner = _G.C_UnitAuras
    if type(owner) ~= "table" then return "namespace absent" end
    local names = {}
    pcall(function()
        for k, v in pairs(owner) do
            if type(k) == "string" and type(v) == "function" then
                for _, needle in ipairs(GS.NAME_NEEDLES) do
                    if string.find(k, needle, 1, true) then
                        names[#names + 1] = k
                        break
                    end
                end
            end
        end
    end)
    table.sort(names)
    while #names > GS.MAX_NAMES do names[#names] = nil end
    return table.concat(names, ",")
end

-- C_UnitAuras.GetUnitAuraInstanceIDs(unit, filter), described. Returns the record, the raw
-- first id (only to be passed on, never compared) and the plain count or nil.
function GS.ReadAuraIds(unit, filter)
    local rec = { unit = unit, filter = filter }
    local fn = Api("C_UnitAuras", "GetUnitAuraInstanceIDs")
    if not fn then
        rec.exists = false
        return rec
    end
    rec.exists = true
    local n, t = Pack(pcall(fn, unit, filter))
    if t[1] ~= true then
        rec.ok = false
        rec.err = ErrText(t[2])
        return rec
    end
    rec.ok = true
    rec.returns = n - 1
    local v = t[2]
    rec.resultType = type(v)
    rec.resultSecret = IsSecret(v)
    if type(v) ~= "table" or rec.resultSecret then return rec end
    rec.tableSecret = SecretTable(v)
    if rec.tableSecret then return rec end
    local okc, count = pcall(function() return #v end)
    if okc then rec.count = GS.Plain(count) else rec.count = "error" end
    local plainCount = (okc and type(count) == "number" and not IsSecret(count)) and count or nil
    local okf, first = pcall(function() return v[1] end)
    -- `first` may be secret: type() and IsSecret() are the only things allowed to touch it
    -- before it is described (a comparison with nil is itself a forbidden operation).
    if okf and type(first) ~= "nil" then
        rec.firstIdSecret = IsSecret(first)
        rec.firstIdType = type(first)
        rec.firstId = GS.Plain(first)
        return rec, first, plainCount
    end
    return rec, nil, plainCount
end

-- C_UnitAuras.GetAuraDuration(unit, id) and what the returned object will tell us.
function GS.ReadAuraDuration(rec, unit, id)
    local fn = Api("C_UnitAuras", "GetAuraDuration")
    if not fn then
        rec.durationApi = false
        return
    end
    rec.durationApi = true
    local _, t = Pack(pcall(fn, unit, id))
    if t[1] ~= true then
        rec.durationOk = false
        rec.durationErr = ErrText(t[2])
        return
    end
    rec.durationOk = true
    local d = t[2]
    rec.durationType = type(d)
    rec.durationSecret = IsSecret(d)
    if rec.durationSecret or (type(d) ~= "table" and type(d) ~= "userdata") then return end
    rec.remaining = GS.Read(d, "GetRemainingDuration")
    rec.total = GS.Read(d, "GetTotalDuration")
    rec.endTime = GS.Read(d, "GetEndTime")
    rec.hasSecretValues = GS.Read(d, "HasSecretValues")
end

function GS.AuraSummary(label, rec)
    local ids = rec.ids or {}
    return label .. ": ids " .. (ids.exists == false and "API absent"
        or (ids.ok == false and ("error: " .. tostring(ids.err))
        or ("table secret=" .. tostring(ids.tableSecret) .. " count=" .. tostring(ids.count)
            .. " firstId=" .. tostring(ids.firstId))))
        .. "; duration " .. (rec.durationApi == false and "API absent"
        or (rec.durationOk == false and ("error: " .. tostring(rec.durationErr))
        or (rec.durationOk and ("remaining=" .. tostring(rec.remaining) .. " total=" .. tostring(rec.total))
            or "not called")))
end

function GS.CheckAuraApi(rec)
    local ns = _G.C_UnitAuras
    rec.namespace = type(ns) == "table"
    rec.getUnitAuraInstanceIDs = Api("C_UnitAuras", "GetUnitAuraInstanceIDs") ~= nil
    rec.getAuraDuration = Api("C_UnitAuras", "GetAuraDuration") ~= nil
    rec.durationAndInstanceNames = GS.AuraNames()
    rec.combatPart = "waits for the next PLAYER_REGEN_DISABLED with a HARMFUL|PLAYER aura on the target"
    local ooc = { inCombatLockdown = LockedDown(false) }
    rec.ooc = ooc
    local idsRec, first = GS.ReadAuraIds("player", GS.FILTER_HELPFUL)
    ooc.ids = idsRec
    if type(first) ~= "nil" then GS.ReadAuraDuration(ooc, "player", first) end
    GS.Report("auraApi", "exists ids=" .. tostring(rec.getUnitAuraInstanceIDs) .. " duration="
        .. tostring(rec.getAuraDuration) .. "; names " .. rec.durationAndInstanceNames .. "; "
        .. GS.AuraSummary("ooc player HELPFUL", ooc))
end

-- One capture of the target's own harmful auras. Returns the record and whether it is final:
-- anything but "readable and empty" (or no target) is a result worth keeping.
function GS.CaptureCombatAuras(attempt)
    local rec = { attempt = attempt, inCombatLockdown = LockedDown(false) }
    local okT, exists = pcall(function() return _G.UnitExists("target") end)
    if okT then
        rec.targetExists = GS.Plain(exists)
    else
        rec.targetExists = "error"
    end
    if rec.targetExists ~= true then return rec, false end
    local idsRec, first, count = GS.ReadAuraIds("target", GS.FILTER_MINE)
    rec.ids = idsRec
    if type(first) ~= "nil" then GS.ReadAuraDuration(rec, "target", first) end
    if idsRec.exists and idsRec.ok and count == 0 then return rec, false end
    return rec, true
end

function GS.FinishCombat(run, rec, final)
    state.gsCombatArmed = false
    state.gsCombatPending = false
    rec.captured = final
    rec.gaveUp = not final
    GS.Section("auraApi").combat = rec
    GS.Report("auraApi", GS.AuraSummary(final and "combat target HARMFUL|PLAYER" or
        "combat target (gave up: no aura on target)", rec) .. " [attempt " .. tostring(rec.attempt) .. "]")
    GS.AcFinish(run)
    if run == state.gsRun and state.gsFrame then
        CallOn(state.gsFrame, "UnregisterEvent", "PLAYER_REGEN_DISABLED")
    end
end

function GS.CombatStep(run, attempt)
    if run ~= state.gsRun or not state.gsCombatArmed then return end
    state.gsCombatPending = false
    if not LockedDown(false) then
        -- Combat ended before a usable capture. Stay armed for the next pull.
        pcall(function() GS.Section("auraApi").combatInterrupted = attempt end)
        GS.AcHide()
        return
    end
    pcall(GS.AcShow)
    local rec, final = GS.CaptureCombatAuras(attempt)
    if final or attempt >= GS.COMBAT_MAX_ATTEMPTS then
        GS.FinishCombat(run, rec, final)
        return
    end
    state.gsCombatPending = true
    local scheduled = GS.Timer(GS.COMBAT_DELAY, function()
        local ok, err = pcall(GS.CombatStep, run, attempt + 1)
        if not ok then pcall(function() GS.Section("auraApi").combatError = ErrText(err) end) end
    end)
    if not scheduled then GS.FinishCombat(run, rec, false) end
end

function GS.ScheduleCombat(run)
    if not state.gsCombatArmed or state.gsCombatPending then return end
    state.gsCombatPending = true
    local scheduled = GS.Timer(GS.COMBAT_DELAY, function()
        local ok, err = pcall(GS.CombatStep, run, 1)
        if not ok then pcall(function() GS.Section("auraApi").combatError = ErrText(err) end) end
    end)
    if not scheduled then
        -- No timer: capture once, now.
        state.gsCombatPending = false
        local ok, err = pcall(GS.CombatStep, run, GS.COMBAT_MAX_ATTEMPTS)
        if not ok then pcall(function() GS.Section("auraApi").combatError = ErrText(err) end) end
    end
end

-- 6. SetAlphaFromBoolean ---------------------------------------------------------------------

function GS.AlphaTrial(obj)
    local out = { exists = GS.Method(obj, "SetAlphaFromBoolean") ~= nil }
    if not out.exists then return out end
    out.trueStep = GS.Step(obj, "SetAlphaFromBoolean", true, 1, 0)
    out.trueAlpha = GS.Read(obj, "GetAlpha")
    out.falseStep = GS.Step(obj, "SetAlphaFromBoolean", false, 1, 0)
    out.falseAlpha = GS.Read(obj, "GetAlpha")
    return out
end

function GS.CheckAlpha(rec, _host)
    local tex = GS.Tex("alphaTex")
    rec.texture = GS.AlphaTrial(tex)
    local frame = GS.Obj("alphaFrame", function(h) return CreateFrame("Frame", nil, h) end)
    rec.frame = GS.AlphaTrial(frame)
    GS.Hide(tex)
    GS.Hide(frame)
    local t = rec.texture
    if not t.exists then
        rec.verdict = "SetAlphaFromBoolean absent on Texture"
    elseif t.trueStep == "ok" and t.falseStep == "ok" then
        rec.verdict = "Texture:SetAlphaFromBoolean works (true -> " .. tostring(t.trueAlpha)
            .. ", false -> " .. tostring(t.falseAlpha) .. "); on Frame: " .. tostring(rec.frame.exists)
    else
        rec.verdict = "Texture:SetAlphaFromBoolean exists but failed: " .. tostring(t.trueStep)
    end
    GS.Report("alphaFromBoolean", rec.verdict)
end

-- 7. AuraContainer: engine-drawn aura buttons ------------------------------------------------
-- Why: Plater and ElvUI show target debuffs in combat through an AuraContainer, never reading
-- the aura data. Question: can that engine timer also move a vertical DoT chip?
-- Source for every call below (nothing guessed): Blizzard_AuraContainer in the retail 12.1.0
-- FrameXML (Blizzard_CustomAuraContainer.lua: AddAuraGroup / SetUnit; Blizzard_CustomAuraButton.lua:
-- SetIcon / SetDurationCooldown / SetDurationText / SetDurationBar / SetApplicationCount;
-- AuraContainerUtilDocumentation.lua: the option structures), ElvUI's Auras/Containers.lua (the
-- same calls in a shipping addon, including button:SetDurationBar(statusbar)) and the 16001
-- dump (C_XMLUtil template check, C_AuraContainerUtil). No Plater source was available.
-- What those files say about the duration: the engine never hands it to addon code. The
-- initializeFrame callback gets the button only; the duration object is applied by the engine
-- as cooldown:SetCooldownFromDurationObject(duration, false), a text binding and
-- statusBar:SetTimerDuration(duration, interpolation, direction) on the objects we registered.
-- So "the argument the engine passed" is observed here with hooksecurefunc on OUR Cooldown and
-- StatusBar objects (type and secrecy only, never the value), and the key question is tested
-- three ways on cached vertical bars: the engine's own SetDurationBar bar (fill height), a
-- bar fed the duration the engine passed to our bar hook, and a bar fed
-- button:GetAuraDuration() (a private-mixin method, so it may well refuse).

GS.AC_NAME = "FSCheckGsAuraContainer"
GS.AC_GROUP = "mine"
GS.AC_MAX_BUTTONS = 8
GS.AC_MAX_BARS = 12
GS.AC_BAR_W = 6
GS.AC_BAR_H = 20

function GS.AcState()
    local ac = state.gsAc
    if not ac then
        ac = { bars = {}, steps = {}, inits = 0, cooldownHits = 0, barHits = 0, armed = false }
        state.gsAc = ac
    end
    return ac
end

-- "type:plain" or "type:secret" for each argument (at most 4) plus the argument count.
function GS.ArgTypes(...)
    local out = {}
    local n = select("#", ...)
    for i = 1, math.min(n, 4) do
        local v = select(i, ...)
        out[i] = type(v) .. ":" .. (IsSecret(v) and "secret" or "plain")
    end
    return table.concat(out, ","), n
end

-- Feeds `duration` (possibly secret, only ever passed on) to the cached vertical bar `key`.
function GS.AcFeed(key, duration)
    local ac = GS.AcState()
    local bar = GS.Bar("acFwd" .. key)
    pcall(bar.SetOrientation, bar, "VERTICAL")
    if not ac.fed then ac.fed = {} end
    ac.fed[key] = true
    return GS.Step(bar, "SetTimerDuration", duration)
end

function GS.AcNoteCooldown(...)
    local ac = state.gsAc
    if not ac or not ac.armed then return end
    ac.cooldownHits = ac.cooldownHits + 1
    if not ac.cooldownArgs then ac.cooldownArgs = (GS.ArgTypes(...)) end
end

-- Post-hook on SetTimerDuration of the bar registered with SetDurationBar: its first
-- argument is the engine's duration object, forwarded once to a bar of ours.
function GS.AcNoteBar(...)
    local ac = state.gsAc
    if not ac or not ac.armed then return end
    ac.barHits = ac.barHits + 1
    if ac.barArgs then return end
    ac.barArgs = (GS.ArgTypes(...))
    local duration = ...
    ac.hookForward = GS.AcFeed("hook", duration)
end

-- A post-hook gets the method's own arguments, self first; drop self.
function GS.AcHookCooldown(_, ...) pcall(GS.AcNoteCooldown, ...) end
function GS.AcHookBar(_, ...) pcall(GS.AcNoteBar, ...) end

-- The group's initializeFrame: runs once per button the engine builds, before the button
-- turns restricted. Every step is its own pcall; the first result per step is recorded.
function GS.AcInitButton(button)
    Quiet(button, "SetMouseMotionEnabled", false)
    Quiet(button, "SetMouseClickEnabled", false)
    Quiet(button, "SetHideTooltipInCombat", true)
    local ac = GS.AcState()
    ac.inits = ac.inits + 1
    local steps = ac.steps
    local function S(name, fn)
        local ok, err = pcall(fn)
        if steps[name] == nil then steps[name] = ok and "ok" or ErrText(err) end
    end
    local cooldown, bar
    S("icon", function()
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetAllPoints(button)
        button:SetIcon(icon)
    end)
    S("cooldown", function()
        cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        Quiet(cooldown, "EnableMouse", false)
        Quiet(cooldown, "EnableMouseMotion", false)
        cooldown:SetAllPoints(button)
        Quiet(cooldown, "SetHideCountdownNumbers", true)
        button:SetDurationCooldown(cooldown)
    end)
    S("cooldownHook", function() hooksecurefunc(cooldown, "SetCooldownFromDurationObject", GS.AcHookCooldown) end)
    S("durationText", function()
        local fs = (cooldown or button):CreateFontString(nil, "OVERLAY", "NumberFontNormal")
        fs:SetPoint("CENTER")
        button:SetDurationText(fs, {})
    end)
    S("applicationCount", function()
        local fs = button:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmall")
        fs:SetPoint("BOTTOMRIGHT")
        button:SetApplicationCount(fs)
    end)
    S("durationBar", function()
        bar = CreateFrame("StatusBar", nil, button)
        bar:SetSize(GS.AC_BAR_W, GS.AC_BAR_H)
        bar:SetPoint("CENTER")
        bar:SetStatusBarTexture(GS.TEX)
        bar:SetOrientation("VERTICAL")
        bar:SetMinMaxValues(0, 1)
        Quiet(bar, "EnableMouse", false)
        button:SetDurationBar(bar)
        if #ac.bars < GS.AC_MAX_BARS then ac.bars[#ac.bars + 1] = bar end
    end)
    S("barHook", function() hooksecurefunc(bar, "SetTimerDuration", GS.AcHookBar) end)
end

-- Out of combat, run by /fscheck gunsight: build the container once (cached on `state`),
-- add the group once, point it at the target, leave it hidden and disabled.
function GS.CheckAuraContainer(rec, _host)
    local ac = GS.AcState()
    rec.combatPart = "waits for the next PLAYER_REGEN_DISABLED with a HARMFUL|PLAYER aura on the target"
    local getTemplate = Api("C_XMLUtil", "GetTemplateInfo")
    if not getTemplate then
        rec.status = "absent: C_XMLUtil.GetTemplateInfo"
        GS.Report("auraContainer", rec.status)
        return
    end
    local okT, tmpl = pcall(getTemplate, TEMPLATE)
    if not okT then
        rec.status = "template check errored: " .. ErrText(tmpl)
        GS.Report("auraContainer", rec.status)
        return
    end
    if not IsSecret(tmpl) and (type(tmpl) == "nil" or tmpl == false) then
        rec.status = "template absent: " .. TEMPLATE
        GS.Report("auraContainer", rec.status)
        return
    end
    rec.templateAccepted = true

    local container = ac.container
    if container == nil then
        local ok, result = pcall(CreateFrame, "AuraContainer", GS.AC_NAME, UIParent, TEMPLATE)
        rec.frameType = ok and "ok" or ErrText(result)
        if not ok then
            rec.status = "AuraContainer frame type refused: " .. rec.frameType
            GS.Report("auraContainer", rec.status)
            return
        end
        container = result
        ac.container = container
    else
        rec.frameType = "reused"
    end
    -- The two bars that take a forwarded duration exist before any combat, so no frame is
    -- built inside the engine's own call.
    for _, key in ipairs({ "hook", "get" }) do
        local okB, errB = pcall(function() GS.Hide(GS.Bar("acFwd" .. key)) end)
        if not okB then rec.fwdBarError = ErrText(errB) end
    end
    -- Invisible on purpose (alpha 0 keeps it animating): only the counts and heights matter.
    rec.setSize = GS.Step(container, "SetSize", 1, 1)
    rec.setPoint = GS.Step(container, "SetPoint", "CENTER", UIParent, "CENTER", 0, 150)
    rec.setAlpha = GS.Step(container, "SetAlpha", 0)

    local sortMethod = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local sortDirection = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    local layout = {
        elementSpacing = 2,
        lineSpacing = 2,
        groupLineSpacing = 2,
        elementWidth = 24,
        elementHeight = 24,
    }
    local options = {
        maxFrameCount = GS.AC_MAX_BUTTONS,
        sortMethod = sortMethod,
        sortDirection = sortDirection,
        initializeFrame = GS.AcInitButton,
        layout = layout,
    }
    if ac.groupAdded then
        rec.addAuraGroup = "reused"
    else
        rec.addAuraGroup = GS.Step(container, "AddAuraGroup", GS.AC_GROUP, GS.FILTER_MINE, options)
        if rec.addAuraGroup == "ok" then ac.groupAdded = true end
    end
    rec.setUnit = GS.Step(container, "SetUnit", "target")
    rec.setEnabledFalse = GS.Step(container, "SetEnabled", false)
    rec.hide = GS.Step(container, "Hide")
    rec.initCalls = ac.inits
    rec.initSteps = ac.steps
    rec.verdict = "frame " .. tostring(rec.frameType) .. ", template accepted, AddAuraGroup " .. tostring(rec.addAuraGroup)
        .. ", SetUnit " .. tostring(rec.setUnit) .. ", " .. tostring(ac.inits) .. " init callbacks"
    GS.Report("auraContainer", rec.verdict .. "; combat part waits for a pull with a DoT on the target")
end

-- In combat: point the container at the target, enable it and show it (the three calls the
-- main run's container already survives in combat), and zero the counters this window reads.
function GS.AcShow()
    local ac = state.gsAc
    if not ac or not ac.container or not ac.groupAdded or ac.armed then return end
    local container = ac.container
    local c = {}
    GS.Section("auraContainer").combat = c
    ac.armed = true
    ac.cooldownHits, ac.barHits = 0, 0
    ac.cooldownArgs, ac.barArgs, ac.hookForward, ac.fed = nil, nil, nil, nil
    c.setUnit = GS.Step(container, "SetUnit", "target")
    c.setEnabled = GS.Step(container, "SetEnabled", true)
    c.show = GS.Step(container, "Show")
end

function GS.AcHide()
    local ac = state.gsAc
    if not ac then return end
    ac.armed = false
    if ac.container then
        GS.Hide(ac.container)
        Quiet(ac.container, "SetEnabled", false)
    end
    for key in pairs(ac.fed or {}) do GS.Hide(state.gsObjs["acFwd" .. key]) end
end

-- Children of the container: how many, how many plainly shown, and the first shown one.
function GS.AcCountButtons(container)
    local out = { children = 0, shown = 0, unknown = 0 }
    local exists, ok, res, n = GS.Call(container, "GetChildren")
    if not exists then
        out.note = "GetChildren absent"
        return out
    end
    if not ok then
        out.note = "error: " .. res
        return out
    end
    local firstShown
    for i = 1, n do
        local child = res[i + 1]
        out.children = out.children + 1
        local okS, shown = pcall(function() return child:IsShown() end)
        if okS and not IsSecret(shown) then
            if shown == true then
                out.shown = out.shown + 1
                if firstShown == nil then firstShown = child end
            end
        else
            out.unknown = out.unknown + 1
        end
    end
    return out, firstShown
end

-- Height of a StatusBar's fill texture: a plain number, "secret", "nil", "absent" or "error: ...".
function GS.FillHeight(bar)
    local exists, ok, res = GS.Call(bar, "GetStatusBarTexture")
    if not exists then return "absent" end
    if not ok then return "error: " .. res end
    local tex = res[2]
    if IsSecret(tex) then return "secret" end
    if type(tex) == "nil" then return "nil" end
    return GS.Read(tex, "GetHeight")
end

-- Heights of the engine-driven bars (the ones given to SetDurationBar) whose button is visible.
function GS.AcReadEngineBars(ac)
    local out = { stored = #ac.bars, visible = 0, unknown = 0, filled = 0, secret = 0 }
    for _, bar in ipairs(ac.bars) do
        local okV, vis = pcall(function() return bar:IsVisible() end)
        if okV and not IsSecret(vis) then
            if vis == true then
                out.visible = out.visible + 1
                local h = GS.FillHeight(bar)
                if h == "secret" then
                    out.secret = out.secret + 1
                elseif type(h) == "number" then
                    if h > 0 then out.filled = out.filled + 1 end
                    if out.maxHeight == nil or h > out.maxHeight then out.maxHeight = h end
                elseif out.note == nil then
                    out.note = h
                end
            end
        else
            out.unknown = out.unknown + 1
        end
    end
    return out
end

function GS.AcFedSummary(ac)
    local out = {}
    for key in pairs(ac.fed or {}) do
        local bar = state.gsObjs["acFwd" .. key]
        out[key] = { height = GS.FillHeight(bar), value = GS.Read(bar, "GetValue") }
    end
    return out
end

function GS.AcCombatLine(c)
    local function fed(key)
        local f = c.fed and c.fed[key]
        return f and tostring(f.height) or "not fed"
    end
    local b = c.buttons or {}
    local e = c.engineBars or {}
    return "combat: " .. tostring(b.shown) .. " of " .. tostring(b.children) .. " children shown, "
        .. tostring(c.initCalls) .. " init callbacks; cooldown hook " .. tostring(c.cooldownHook.calls) .. " ["
        .. tostring(c.cooldownHook.args) .. "]; bar hook " .. tostring(c.barHook.calls) .. " ["
        .. tostring(c.barHook.args) .. "] forward " .. tostring(c.barHook.forwardStep)
        .. "; engine bars visible " .. tostring(e.visible) .. " filled " .. tostring(e.filled)
        .. " max " .. tostring(e.maxHeight) .. " secret " .. tostring(e.secret)
        .. "; button:GetAuraDuration " .. tostring(c.buttonDuration and c.buttonDuration.call)
        .. "; fill height hook-fed " .. fed("hook") .. ", get-fed " .. fed("get")
end

-- Second half of the sample, GS.SAMPLE_DELAY after the first: heights, then hide.
function GS.AcSampleHeights(run, c)
    local ac = state.gsAc
    if run ~= state.gsRun or not ac or not ac.armed then return end
    local ok, err = pcall(function()
        c.engineBars = GS.AcReadEngineBars(ac)
        c.fed = GS.AcFedSummary(ac)
    end)
    if not ok then c.sampleError = ErrText(err) end
    GS.AcHide()
    local okL, line = pcall(GS.AcCombatLine, c)
    GS.Report("auraContainer", okL and line or ("combat sample error: " .. ErrText(line)))
end

-- First half of the sample: counts, hook results, and the button's own duration object.
function GS.AcSample(run)
    local ac = state.gsAc
    if run ~= state.gsRun or not ac or not ac.armed then return end
    local c = GS.Section("auraContainer").combat
    if type(c) ~= "table" then
        c = {}
        GS.Section("auraContainer").combat = c
    end
    local ok, err = pcall(function()
        c.inCombatLockdown = LockedDown(false)
        c.initCalls = ac.inits
        c.cooldownHook = { calls = ac.cooldownHits, args = ac.cooldownArgs or "none" }
        c.barHook = { calls = ac.barHits, args = ac.barArgs or "none", forwardStep = ac.hookForward or "not forwarded" }
        c.allocated = GS.Read(ac.container, "GetAuraGroupFrameCount", GS.AC_GROUP)
        local counts, firstShown = GS.AcCountButtons(ac.container)
        c.buttons = counts
        if firstShown ~= nil then
            local d = {}
            c.buttonDuration = d
            local exists, okCall, res = GS.Call(firstShown, "GetAuraDuration")
            if not exists then
                d.call = "absent"
            elseif not okCall then
                d.call = "error: " .. res
            else
                d.call = "ok"
                local dur = res[2]
                d.type = type(dur)
                d.secret = IsSecret(dur)
                d.forwardStep = GS.AcFeed("get", dur)
            end
        else
            c.buttonDuration = { call = "no shown button" }
        end
    end)
    if not ok then c.sampleError = ErrText(err) end
    local second = function()
        local okS, errS = pcall(GS.AcSampleHeights, run, c)
        if not okS then
            pcall(function() c.heightError = ErrText(errS) end)
            GS.AcHide()
        end
    end
    if not GS.Timer(GS.SAMPLE_DELAY, second) then second() end
end

-- Called when the combat aura capture is over: the engine has had the capture's own time to
-- populate the buttons, so sample a moment later and then hide.
function GS.AcFinish(run)
    local ac = state.gsAc
    if not ac or not ac.armed then return end
    local first = function()
        local ok, err = pcall(GS.AcSample, run)
        if not ok then
            pcall(function() GS.Section("auraContainer").combatError = ErrText(err) end)
            GS.AcHide()
        end
    end
    if not GS.Timer(GS.SAMPLE_DELAY, first) then first() end
end

-- Arming and events --------------------------------------------------------------------------

function GS.Disarm()
    GS.HideObjects()
    state.gsRun = state.gsRun + 1
    state.gsCastArmed = false
    state.gsCombatArmed = false
    state.gsCombatPending = false
    CallOn(state.gsFrame, "UnregisterAllEvents")
end

function GS.Handle(event, ...)
    if event == "PLAYER_REGEN_DISABLED" then
        GS.ScheduleCombat(state.gsRun)
        return
    end
    if event == "UNIT_SPELLCAST_START" then
        if not state.gsCastArmed or WrongUnit((...)) then return end
        state.gsCastArmed = false
        CallOn(state.gsFrame, "UnregisterEvent", "UNIT_SPELLCAST_START")
        GS.CheckBarCast(state.gsRun)
    end
end

function GS.OnEvent(_, event, ...)
    local ok, err = pcall(GS.Handle, event, ...)
    if not ok then
        pcall(function() GS.Section("meta").lastError = ErrText(err) end)
    end
end

function GS.EnsureFrame()
    if state.gsFrame then return true end
    local ok, frame = pcall(CreateFrame, "Frame")
    if not ok or not frame then return false end
    state.gsFrame = frame
    return (pcall(frame.SetScript, frame, "OnEvent", GS.OnEvent))
end

-- Runs one check under pcall so a failure is recorded and the next check still runs.
function GS.Run(key, fn, ...)
    local rec = GS.Section(key)
    local ok, err = pcall(fn, rec, ...)
    if not ok then
        rec.checkError = ErrText(err)
        GS.Report(key, "check error: " .. rec.checkError)
    end
end

function GS.Start()
    GS.Disarm()
    local run = state.gsRun
    local db = DB()
    db.gunsight = {}
    local meta = GS.Section("meta")
    meta.started = SafeDate()
    meta.run = run
    meta.issecretvalueAvailable = type(_G.issecretvalue) == "function"
    meta.inCombatLockdown = LockedDown(false)
    -- Plain values only: the version string and the build number (GetBuildInfo's first two returns).
    local okB, version, build = pcall(function() return _G.GetBuildInfo() end)
    if okB then
        meta.buildVersion = GS.Plain(version)
        meta.buildNumber = GS.Plain(build)
    else
        meta.buildVersion = "error: " .. ErrText(version)
    end

    local okHost, host = pcall(GS.Host)
    if not okHost then
        meta.hostError = ErrText(host)
        Say("gunsight: could not create the test frame (" .. meta.hostError .. "), nothing run")
        return
    end

    GS.Run("texcoord8", GS.CheckTexCoord, host)
    GS.Run("vertexColorFromBoolean", GS.CheckVertexColor, host)
    GS.Run("verticalBarTimer", GS.CheckBarManual, host, run)
    GS.Run("line", GS.CheckLine, host)
    GS.Run("auraApi", GS.CheckAuraApi)
    GS.Run("auraContainer", GS.CheckAuraContainer)
    GS.Run("alphaFromBoolean", GS.CheckAlpha, host)

    if GS.EnsureFrame() then
        state.gsCastArmed = true
        state.gsCombatArmed = true
        local frame = state.gsFrame
        local ok = pcall(frame.RegisterUnitEvent, frame, "UNIT_SPELLCAST_START", "player")
        if not ok then
            local ok2, err = pcall(frame.RegisterEvent, frame, "UNIT_SPELLCAST_START")
            if not ok2 then meta.registerError = ErrText(err) end
        end
        local okR, errR = pcall(frame.RegisterEvent, frame, "PLAYER_REGEN_DISABLED")
        if not okR then meta.registerError = ErrText(errR) end
        if meta.inCombatLockdown then GS.ScheduleCombat(run) end
        Say("gunsight armed: cast one spell with a cast time (bar test) and pull a mob with a DoT on it (aura test)")
    else
        meta.frameError = "event frame could not be created, cast and combat parts skipped"
        Say("gunsight: " .. meta.frameError)
    end
    Say("gunsight results: ForeverSTUwaveDB.fscheck.gunsight, /reload or log out to save to "
        .. "WTF/Account/<id>/SavedVariables/forever-stuwave.lua (late results print as they finish)")
end

-------------------------------------------------------------------------------
-- Class checks: the machinery /fscheck priest and /fscheck shaman share
-------------------------------------------------------------------------------
-- CP.Install(P, cfg) turns an empty table into a class check: a saved record
-- ForeverSTUwaveDB.fscheck.<cfg.key> with `meta`, an `ooc` and a `combat` snapshot and bounded `logs`;
-- the snapshot timing (one now, the other state on the next pull, 4 s in, or at the fight's end);
-- the event frame and its registration; start, stop and the timeout. The class supplies:
--   P.PARTS      the snapshot parts, { name, fn(sec) } (each pcall'd by Section, each record tagged inCombat)
--   P.SPELLS     { key, english name, { ids }, reads auras } for the generic spells / cooldowns parts
--   P.PREDICATES C_Secrets calls with their arguments for the generic secrets part
--   P.EVENTS     { event, unit filters... } registered at start
--   P.HANDLERS   event -> function(event, ...)
--   optional hooks: P.ResetState(), P.MetaFields(meta), P.Clock(entry, now), P.OnStop(status),
--                   P.Finish(snap, sec) (an extra `checks` part), P.AfterSnapshot(snap, kind),
--                   P.CarryOver(old, fresh) (a start that replaces the saved record moves what must survive into
--                   the new one; a class without it replaces everything, as before)
--   P.Start(resume): resume = true re-arms the logging over an existing saved record WITHOUT replacing it or
--                   taking a snapshot (a class's side commands use it); with no saved record it starts normally.
-- cfg: key, label (chat prefix and command word), logCap, logCaps, logSeconds, combatDelay, oocDelay,
--      sweepKey (the cached cooldown frame of the duration object trial), logsText, todo (chat text).

local CP = {}

CP.CD_FIELDS = { "startTime", "duration", "isEnabled", "isActive", "modRate", "isOnGCD" }
CP.CHARGE_FIELDS = { "currentCharges", "maxCharges", "cooldownStartTime", "cooldownDuration", "chargeModRate", "isActive" }
CP.CD_KEEP = { duration = true, isEnabled = true, isActive = true, isOnGCD = true }
CP.CHARGE_KEEP = { currentCharges = true, maxCharges = true, isActive = true }

function CP.Round(x)
    return math.floor(x * 1000 + 0.5) / 1000
end

-- The plain class token of the player, or nil (a secret or failing read fails closed).
function CP.ClassToken()
    local ok, _, token = pcall(Api("UnitClass"), "player")
    if ok and type(token) == "string" and not IsSecret(token) then return string.sub(token, 1, MAX_STR) end
    return nil
end

-- One description of a returned value: "type/plain=value" or "type/secret".
function CP.DescText(d)
    if type(d) ~= "table" then return "?" end
    local text = tostring(d.type) .. (d.isSecret and "/secret" or "/plain")
    if d.value ~= nil then text = text .. "=" .. tostring(d.value) end
    return text
end

-- An Invoke record as one string.
function CP.Brief(rec)
    if rec.exists == false then return "absent" end
    if rec.ok ~= true then return "error: " .. tostring(rec.err) end
    if (rec.n or 0) < 1 then return "no returns" end
    local parts = {}
    for i = 1, math.min(rec.n, MAX_RETURNS) do parts[i] = CP.DescText(rec["r" .. i]) end
    return table.concat(parts, ",")
end

-- Invoke(keep) then Brief, for the per-spell cells.
function CP.B(fn, ...)
    return CP.Brief((Invoke(true, fn, ...)))
end

-- Brief plus the described fields of a returned table, sorted.
function CP.FieldsBrief(rec)
    local text = CP.Brief(rec)
    if rec.issecrettable ~= nil then text = text .. " issecrettable=" .. tostring(rec.issecrettable) end
    if type(rec.fields) == "table" then
        local keys = {}
        for k in pairs(rec.fields) do keys[#keys + 1] = k end
        table.sort(keys)
        local parts = {}
        for i, k in ipairs(keys) do
            local d = rec.fields[k]
            parts[i] = k .. "=" .. ((type(d) == "table" and d.err) and "error" or CP.DescText(d))
        end
        text = text .. " {" .. table.concat(parts, ",") .. "}"
    end
    return text
end

-- A method call on an object that came back from the API, never on a secret one.
function CP.Method(obj, name)
    if type(obj) == "nil" or IsSecret(obj) then return nil end
    return GS.Method(obj, name)
end

-- True for a plain unit token outside the set: a plain RegisterEvent fallback delivers every unit.
-- A secret unit is kept and described.
function CP.ForeignUnit(unit, set)
    if IsSecret(unit) then return false end
    return not set[unit]
end

function CP.Install(P, cfg)
    for _, name in ipairs({ "Round", "ClassToken", "DescText", "Brief", "B", "FieldsBrief", "Method", "ForeignUnit" }) do
        P[name] = CP[name]
    end
    P.cfg = cfg
    P.run = 0
    P.live = nil         -- the running check: { run, pending = { ooc, combat } }
    P.frame = nil        -- the event frame (frames are never destroyed, so it is reused)
    P.combat = false     -- InCombatLockdown at the start of the snapshot being taken
    P.resolved = nil     -- the spell list with ids resolved, for the snapshot being taken
    P.last = {}          -- log name -> GetTime of its previous entry
    P.sample = {}        -- sampled log name -> { key, t, skipped } of its previous kept entry
    P.names = nil        -- spell id -> resolved name, for the snapshot being taken

    -- Snapshot helpers ---------------------------------------------------------------------------

    function P.Stamp(rec)
        rec.inCombat = P.combat
        return rec
    end

    -- Invoke, tagged. Drops the raw first return: callers that need it call Invoke themselves.
    function P.Call(keep, fn, ...)
        return P.Stamp((Invoke(keep, fn, ...)))
    end

    -- The name the client resolves a spell id to ("unresolved" when it cannot be read as plain). Cached
    -- for the snapshot being taken.
    function P.IdName(id)
        local cache = P.names
        if cache and cache[id] then return cache[id] end
        local ok, name = pcall(SpellName, id)
        local text = (ok and type(name) == "string") and string.sub(name, 1, MAX_STR) or "unresolved"
        if cache then cache[id] = text end
        return text
    end

    -- The spell list with its ids: the listed ones plus the rank the client resolves the name to.
    function P.Resolve()
        local out = {}
        for _, s in ipairs(P.SPELLS) do
            local ids, seen = {}, {}
            local function add(id)
                if type(id) == "number" and not seen[id] then
                    seen[id] = true
                    ids[#ids + 1] = id
                end
            end
            for _, id in ipairs(s[3]) do add(id) end
            local known = KnownRankID(s[2])
            add(known)
            out[#out + 1] = { key = s[1], name = s[2], ids = ids, known = known, aura = s[4] }
        end
        return out
    end

    -- Ids of a resolved spell the player has not been refused: only an answer of exactly false drops one.
    function P.KnownIds(s, isPlayerSpell)
        local out = {}
        for _, id in ipairs(s.ids) do
            if KeptBool((Invoke(true, isPlayerSpell, id))) ~= false then out[#out + 1] = id end
        end
        return out
    end

    -- Generic snapshot parts ---------------------------------------------------------------------

    function P.PartSecrets(sec)
        sec.calls = {}
        for _, call in ipairs(P.PREDICATES) do
            local args = {}
            for i = 2, #call do args[#args + 1] = tostring(call[i]) end
            local label = call[1]
            if #args > 0 then label = label .. "(" .. table.concat(args, ",") .. ")" end
            sec.calls[label] = P.Call(true, Api("C_Secrets", call[1]), unpack(call, 2))
        end
    end

    function P.PartSpells(sec)
        local isPlayerSpell = Api("IsPlayerSpell")
        local auraSecrecy = Api("C_Secrets", "GetSpellAuraSecrecy")
        local cdSecrecy = Api("C_Secrets", "GetSpellCooldownSecrecy")
        local castSecrecy = Api("C_Secrets", "GetSpellCastSecrecy")
        local auraSecret = Api("C_Secrets", "ShouldSpellAuraBeSecret")
        local cdSecret = Api("C_Secrets", "ShouldSpellCooldownBeSecret")
        for _, s in ipairs(P.resolved) do
            local entry = { name = s.name, knownRankID = s.known, inCombat = P.combat }
            sec[s.key] = entry
            local ok, err = pcall(function()
                for _, id in ipairs(s.ids) do
                    entry["s" .. id] = {
                        spellName = P.IdName(id),
                        isPlayerSpell = P.B(isPlayerSpell, id),
                        aura = P.B(auraSecrecy, id),
                        cooldown = P.B(cdSecrecy, id),
                        cast = P.B(castSecrecy, id),
                        shouldAuraBeSecret = P.B(auraSecret, id),
                        shouldCooldownBeSecret = P.B(cdSecret, id),
                    }
                end
            end)
            if not ok then entry.entryError = ErrText(err) end
        end
    end

    -- A duration object handed to a hidden Cooldown frame (the call is a protected function on a protected
    -- frame; this one is a plain throwaway). Returns "ok", "absent" or the error text.
    function P.Sweep(dur)
        local ok, cd = pcall(GS.Obj, cfg.sweepKey, function(host)
            local c = CreateFrame("Cooldown", nil, host, "CooldownFrameTemplate")
            c:Hide()
            return c
        end)
        if not ok or type(cd) == "nil" then return "no frame: " .. ErrText(cd) end
        local result = GS.Step(cd, "SetCooldownFromDurationObject", dur, true)
        GS.Hide(cd)
        return result
    end

    function P.PartCooldowns(sec)
        local isPlayerSpell = Api("IsPlayerSpell")
        local getCooldown = Api("C_Spell", "GetSpellCooldown")
        local getDuration = Api("C_Spell", "GetSpellCooldownDuration")
        local getCharges = Api("C_Spell", "GetSpellCharges")
        for _, s in ipairs(P.resolved) do
            local entry = { name = s.name, inCombat = P.combat }
            sec[s.key] = entry
            local ok, err = pcall(function()
                if #s.ids == 0 then
                    entry.skipped = "no id"
                    return
                end
                local ids = P.KnownIds(s, isPlayerSpell)
                if #ids == 0 then
                    entry.skipped = "not known"
                    return
                end
                for _, id in ipairs(ids) do
                    local cell = { spellName = P.IdName(id) }
                    entry["s" .. id] = cell
                    cell.cooldown = P.FieldsBrief((InvokeTableKeep(CP.CD_FIELDS, CP.CD_KEEP, getCooldown, id)))
                    local drec, dur = Invoke(false, getDuration, id)
                    cell.durationObject = P.Brief(drec)
                    if drec.ok and type(dur) ~= "nil" and not IsSecret(dur) then
                        cell.durationIsZero = P.B(P.Method(dur, "IsZero"), dur)
                        cell.durationRemaining = P.B(P.Method(dur, "GetRemainingDuration"), dur)
                        cell.sweep = P.Sweep(dur)
                    end
                    cell.charges = P.FieldsBrief((InvokeTableKeep(CP.CHARGE_FIELDS, CP.CHARGE_KEEP, getCharges, id)))
                end
            end)
            if not ok then entry.entryError = ErrText(err) end
        end
    end

    -- Fills `snap` (a main-run section or a <key>.ooc/combat table).
    function P.Snapshot(snap)
        P.combat = LockedDown(false)
        snap.inCombat = P.combat
        local ok, resolved = pcall(P.Resolve)
        P.resolved = ok and resolved or {}
        P.names = {}
        snap.time = P.Call(true, Api("GetTime"))
        for _, part in ipairs(P.PARTS) do
            Section(snap, part[1], function(sec)
                sec.inCombat = P.combat
                part[2](sec)
            end)
        end
        if P.Finish then
            Section(snap, "checks", function(sec)
                sec.inCombat = P.combat
                P.Finish(snap, sec)
            end)
        end
        P.resolved = nil
        P.names = nil
    end

    -- Storage, logs ------------------------------------------------------------------------------

    function P.Rec()
        local db = DB()
        if type(db[cfg.key]) ~= "table" then db[cfg.key] = {} end
        return db[cfg.key]
    end

    function P.Meta()
        local rec = P.Rec()
        if type(rec.meta) ~= "table" then rec.meta = {} end
        return rec.meta
    end

    -- The saved record without creating it (a stop after a reset must not bring it back).
    function P.Saved()
        local root = _G.ForeverSTUwaveDB
        local db = type(root) == "table" and root[KEY] or nil
        if type(db) == "table" and type(db[cfg.key]) == "table" then return db[cfg.key] end
        return nil
    end

    function P.Log(name)
        local rec = P.Rec()
        if type(rec.logs) ~= "table" then rec.logs = {} end
        local log = rec.logs[name]
        if type(log) ~= "table" then
            log = { cap = cfg.logCaps[name] or cfg.logCap, total = 0, dropped = 0, entries = {} }
            rec.logs[name] = log
        end
        return log
    end

    -- Appends to a ring buffer: the oldest entries go once there are log.cap (cfg.logCap, or cfg.logCaps for the long logs).
    function P.Push(name, entry)
        local log = P.Log(name)
        log.entries[#log.entries + 1] = entry
        log.total = log.total + 1
        while #log.entries > log.cap do
            table.remove(log.entries, 1)
            log.dropped = log.dropped + 1
        end
        if type(entry.t) == "number" then P.last[name] = entry.t end
    end

    -- Tags an entry: in combat or not, GetTime, the gap to the log's previous entry and, with `clock`,
    -- whatever the class keeps (P.Clock). Plain numbers only: a secret GetTime is not used (noTime).
    function P.Mark(e, name, clock)
        e.inCombat = LockedDown(false)
        local now = PlainTime()
        if now == nil then
            e.noTime = true
            return e
        end
        e.t = now
        local last = P.last[name]
        if last then e.gap = P.Round(now - last) end
        if clock and P.Clock then P.Clock(e, now) end
        return e
    end

    -- Snapshot timing and events -----------------------------------------------------------------

    -- kind "ooc" / "combat". Assigned before it is filled, so a failure part-way still saves what ran.
    function P.TakeSnapshot(kind)
        local snap = { kind = kind, when = SafeDate(), classToken = P.ClassToken() or "unknown" }
        P.Rec()[kind] = snap
        local ok, err = pcall(P.Snapshot, snap)
        if not ok then snap.snapshotError = ErrText(err) end
        Say(cfg.label .. ": " .. kind .. " snapshot saved")
        if P.AfterSnapshot then
            local okAfter, errAfter = pcall(P.AfterSnapshot, snap, kind)
            if not okAfter then snap.afterError = ErrText(errAfter) end
        end
        return snap
    end

    -- The event that asked for `kind` is dropped once that snapshot exists.
    function P.Satisfied(kind)
        CallOn(P.frame, "UnregisterEvent", kind == "combat" and "PLAYER_REGEN_DISABLED" or "PLAYER_REGEN_ENABLED")
    end

    function P.Due(run, kind)
        local live = P.live
        if not live or live.run ~= run then return end
        live.pending[kind] = nil
        -- A pull that ended inside the delay (or a fight that restarted) is not worth recording: stay armed.
        if LockedDown(kind == "combat") ~= (kind == "combat") then return end
        local ok, err = pcall(P.TakeSnapshot, kind)
        if not ok then pcall(function() P.Meta().snapshotError = ErrText(err) end) end
        P.Satisfied(kind)
    end

    function P.Schedule(kind, delay)
        local live = P.live
        if not live or live.pending[kind] then return end
        live.pending[kind] = true
        local run = live.run
        if not GS.Timer(delay, function()
            local ok, err = pcall(P.Due, run, kind)
            if not ok then pcall(function() P.Meta().timerError = ErrText(err) end) end
        end) then
            -- No timer: take the snapshot now rather than never.
            live.pending[kind] = nil
            pcall(function() P.Meta().delay = "none (C_Timer.After unavailable)" end)
            P.Due(run, kind)
        end
    end

    P.CORE_HANDLERS = {
        PLAYER_REGEN_DISABLED = function()
            if P.Rec().combat == nil then P.Schedule("combat", cfg.combatDelay) end
        end,
        PLAYER_REGEN_ENABLED = function()
            if P.Rec().ooc == nil then P.Schedule("ooc", cfg.oocDelay) end
        end,
    }

    function P.OnEvent(_, event, ...)
        if not P.live then return end
        local fn = P.HANDLERS[event] or P.CORE_HANDLERS[event]
        if not fn then return end
        local ok, err = pcall(fn, event, ...)
        if not ok then
            pcall(function() P.Meta().lastError = ErrText(err) end)
        end
    end

    function P.EnsureFrame()
        if P.frame then return true end
        local ok, frame = pcall(CreateFrame, "Frame")
        if not ok or type(frame) == "nil" then
            pcall(function() P.Meta().frameError = ErrText(frame) end)
            return false
        end
        P.frame = frame
        return (pcall(frame.SetScript, frame, "OnEvent", P.OnEvent))
    end

    -- Every failed registration is kept (appended, capped).
    function P.NoteRegisterError(event, err)
        pcall(function()
            local meta = P.Meta()
            local text = event .. ": " .. ErrText(err)
            if type(meta.registerError) == "string" and meta.registerError ~= "" then
                text = meta.registerError .. " | " .. text
            end
            meta.registerError = string.sub(text, 1, MAX_REGISTER_ERR)
        end)
    end

    function P.Register(event, ...)
        local frame = P.frame
        if select("#", ...) > 0 and pcall(frame.RegisterUnitEvent, frame, event, ...) then return end
        local ok, err = pcall(frame.RegisterEvent, frame, event)
        if not ok then P.NoteRegisterError(event, err) end
    end

    -- status: what meta.status says afterwards. quiet: the explicit reset path, which prints its own line.
    function P.Stop(status, quiet)
        local live = P.live
        P.live = nil
        P.run = P.run + 1   -- every pending timer of the old run is now stale
        CallOn(P.frame, "UnregisterAllEvents")
        GS.Hide(state.gsObjs[cfg.sweepKey])
        if P.OnStop then pcall(P.OnStop, status) end
        if live then
            local rec = P.Saved()
            if rec and type(rec.meta) == "table" then rec.meta.status = status end
        end
        if quiet then return end
        if live then
            Say(cfg.label .. ": logging stopped (" .. status .. "), /reload or log out to save")
        else
            Say(cfg.label .. ": not running")
        end
    end

    function P.Start(resume)
        state.canTest = Invoke(false, Api("issecretvalue"), 0).ok == true
        local kind = LockedDown(false) and "combat" or "ooc"
        if P.live then
            if resume then return end
            P.TakeSnapshot(kind)
            Say(cfg.label .. ": logs keep running; /fscheck " .. cfg.label .. " off stops them")
            return
        end
        P.run = P.run + 1
        P.last, P.sample = {}, {}
        if P.ResetState then P.ResetState() end
        local run = P.run
        local meta = {
            started = SafeDate(), run = run, status = "logging", logCap = cfg.logCap, logCaps = cfg.logCaps, logSeconds = cfg.logSeconds,
            issecretvalueAvailable = type(_G.issecretvalue) == "function",
        }
        if P.MetaFields then P.MetaFields(meta) end
        local old = P.Saved()
        local kept = resume and old ~= nil and (old.ooc ~= nil or old.combat ~= nil)
        if kept then
            -- Re-arm over what is saved: snapshots, logs and runs stay; only the meta is renewed.
            local before = type(old.meta) == "table" and old.meta or {}
            meta.resumed = (type(before.resumed) == "number" and before.resumed or 0) + 1
            meta.firstStarted = before.firstStarted or before.started
            old.meta = meta
            if type(old.logs) ~= "table" then old.logs = {} end
        else
            if old then Say(cfg.label .. ": replacing the saved " .. cfg.label .. " record") end
            local fresh = { meta = meta, logs = {} }
            if old and P.CarryOver then pcall(P.CarryOver, old, fresh) end
            DB()[cfg.key] = fresh
            P.TakeSnapshot(kind)
        end
        if not P.EnsureFrame() then
            meta.status = "no frame"
            if kept then
                Say(cfg.label .. ": the event frame could not be created; nothing armed (the saved record is kept)")
            else
                Say(cfg.label .. ": " .. kind .. " snapshot saved but the event frame could not be created; nothing armed")
            end
            return
        end
        -- Live only once the snapshot is in and the frame exists: a failed start leaves nothing half armed.
        P.live = { run = run, pending = {} }
        for _, entry in ipairs(P.EVENTS) do P.Register(unpack(entry)) end
        -- The snapshot of the other state follows the next change: a pull (4 s in) or the end of the fight.
        -- A kept record asks only for the one it lacks.
        if kept then
            local rec = P.Rec()
            if rec.combat == nil then P.Register("PLAYER_REGEN_DISABLED") end
            if rec.ooc == nil then P.Register("PLAYER_REGEN_ENABLED") end
        elseif kind == "ooc" then
            P.Register("PLAYER_REGEN_DISABLED")
        else
            P.Register("PLAYER_REGEN_ENABLED")
        end
        if not GS.Timer(cfg.logSeconds, function()
            if not (P.live and P.live.run == run) then return end
            local ok, err = pcall(P.Stop, "timeout")
            if not ok then pcall(function() P.Meta().timerError = ErrText(err) end) end
        end) then
            meta.timerError = "C_Timer.After unavailable; logging runs until /fscheck " .. cfg.label .. " off"
        end
        if kept then
            Say(cfg.label .. ": logging re-armed over the saved record (nothing replaced, no new snapshot). Logging " .. cfg.logSeconds
                .. "s: " .. cfg.logsText .. ". Run /fscheck " .. cfg.label .. " to take a new snapshot (it replaces the saved snapshot and keeps the logs), "
                .. "/fscheck " .. cfg.label .. " off to stop, /reload to save")
            return
        end
        Say(cfg.label .. ": " .. kind .. " snapshot saved. Logging " .. cfg.logSeconds .. "s: " .. cfg.logsText .. ". "
            .. (kind == "ooc" and "Pull a mob: the combat snapshot follows " .. cfg.combatDelay .. "s in. "
                or "Leave combat: the ooc snapshot follows. ")
            .. cfg.todo .. " Run /fscheck " .. cfg.label .. " again to re-snapshot, "
            .. "/fscheck " .. cfg.label .. " off to stop, /reload to save")
    end
end

-------------------------------------------------------------------------------
-- /fscheck priest: what each priest pain point can read on this client
-------------------------------------------------------------------------------
-- `/fscheck priest` (any time, any class; the main run adds the same section only for a PRIEST)
-- answers, per API a priest UI would lean on: does it exist, is its return secret, and what is the
-- plain value when it is not. Every record is tagged inCombat true/false, so the out-of-combat and
-- in-combat runs sit side by side:
--   priest.ooc / priest.combat   the snapshots (taken now; the other one follows the next pull or
--                                the end of the fight), parts: env, secrets, spells, mana, shield,
--                                auras, cooldowns, triage, lossOfControl, misc, apis;
--   priest.logs.<name>           bounded ring buffers (50 entries, 300 for the power logs; oldest dropped; `total`
--                                and `dropped` count what went by): power (UNIT_POWER_UPDATE, the
--                                mana tick clock; each entry also reads UnitPower for its power
--                                type, plain or secret), powerFrequent (UNIT_POWER_FREQUENT, sampled:
--                                `total` is the raw count, an entry is kept when the unit or power
--                                type shape changes or after `minGap` seconds, `sampledOut` is what
--                                was skipped, `skippedBefore` on an entry says how many it stands
--                                for), powerOther (any non-mana power event, same sampling, so a
--                                5 s series on another power type shows up), cast (with the mana cost, so the
--                                five second rule can be read off sinceManaCast on a power entry;
--                                a spell with no cost table at all is free, cost 0),
--                                aura (player and target UNIT_AURA payload secrecy), shield (absorb
--                                and heal prediction events on player and party), kill (PARTY_KILL,
--                                PLAYER_TARGET_DIED), died (UNIT_DIED), loc (loss of control).
-- Logging stops after 1200 s, on `/fscheck priest off`, or on `/fscheck reset`.
-- The per-spell tables (spells, auras, cooldowns) hold ONE compact string per read:
-- "type/plain=value", "type/secret", "absent", "error: ...", "nil/plain" (nothing there).
-- A secret is described, never compared, concatenated, indexed or stored; a GUID is compared
-- only when both sides are plain. Spell ids not taken from this repo are Classic Era ids and
-- unverified on Forever; every spell is also resolved by NAME (english), and the rank the client
-- reports for the name is checked too. API names and signatures: Gethe/wow-ui-source, branch
-- `forever` (the generated API documentation), 1.60.1.
-- Every checked spell id also records the name the client resolves it to (spellName), so an id taken
-- from Classic Era can be checked. The `target` part records how durable the target is
-- (classification, level, effective level, plus-mob flag, creature type), plain or secret.
-- Results: ForeverSTUwaveDB.fscheck.priest.

PP.FREQUENT_COUNT = 10        -- with no plain clock, keep 1 in this many sampled events
PP.COST_ASSUMPTION = "nil or empty = free"   -- a spell power cost call that returns nothing is read as a free spell
PP.MANA = 0                   -- Enum.PowerType.Mana
PP.INSANITY = 13              -- Enum.PowerType.Insanity
-- Friendly spells tried in order for the range read (by name: no id guess); the first one that
-- answers for the player is used and recorded.
PP.RANGE_NAMES = { "Lesser Heal", "Heal", "Flash Heal", "Renew", "Power Word: Shield" }
PP.AURA_UNITS = { "player", "party1", "target" }
PP.COST_IDS = { 585, 2050, 5019 }
PP.FREQUENT_GAP = 1           -- seconds between kept UNIT_POWER_FREQUENT entries of an unchanged shape
PP.ITEMS = { "Holy Candle", "Sacred Candle", "Devout Candle", "Refreshing Spring Water" }
PP.PLAYER_SET = { player = true }
PP.AURA_SET = { player = true, target = true }
PP.SHIELD_SET = { player = true, party1 = true }

-- { key, english name, { ids }, read auras }. Ids from this repo: 17, 1243, 588, 589, 585,
-- 5019, 15473, 8092, 586, 401977. The rest are Classic Era ids [UNVERIFIED on Forever]; each
-- snapshot records the name the client resolves every id to (spellName), and the names carry the
-- load (the client resolves a name to the rank the player knows). Retail Fortitude 21562 is not a
-- Forever spell (the buff is the rank id, 1244).
PP.SPELLS = {
    { "pw_shield", "Power Word: Shield", { 17 }, true },
    { "weakened_soul", "Weakened Soul", { 6788 }, true },
    { "renew", "Renew", { 139 }, true },
    { "pom", "Prayer of Mending", {}, true },
    { "inner_fire", "Inner Fire", { 588 }, true },
    { "fort", "Power Word: Fortitude", { 1243, 1244 }, true },
    { "divine_spirit", "Divine Spirit", { 14752 }, true },
    { "shadow_prot", "Shadow Protection", { 976 }, true },
    { "fear_ward", "Fear Ward", { 6346 }, true },
    { "inner_focus", "Inner Focus", { 14751 }, true },
    { "psychic_scream", "Psychic Scream", { 8122 }, false },
    { "fade", "Fade", { 586 }, false },
    { "penance", "Penance", {}, false },
    { "divine_grace", "Divine Grace", {}, false },
    { "binding_heal", "Binding Heal", {}, false },
    { "shadowform", "Shadowform", { 15473 }, true },
    { "sw_pain", "Shadow Word: Pain", { 589 }, true },
    { "dplague", "Devouring Plague", {}, true },
    { "ve", "Vampiric Embrace", { 15286 }, true },
    { "spirit_tap", "Spirit Tap", { 15338 }, true },
    { "shadow_weaving", "Shadow Weaving", {}, true },
    { "shadowfiend", "Shadowfiend", { 401977 }, false },
    { "mind_blast", "Mind Blast", { 8092 }, false },
    { "shoot", "Shoot", { 5019 }, false },
    { "dispel_magic", "Dispel Magic", { 527 }, false },
    { "abolish_disease", "Abolish Disease", { 552 }, false },
    { "lesser_heal", "Lesser Heal", { 2050 }, false },
    { "smite", "Smite", { 585 }, false },
}

-- C_Secrets calls with their documented arguments (SecretPredicateAPIDocumentation).
PP.PREDICATES = {
    { "HasSecretRestrictions" },
    { "ShouldAurasBeSecret" },
    { "ShouldCooldownsBeSecret" },
    { "ShouldUnitStatsBeSecret" },
    { "GetPowerTypeSecrecy", 0 },
    { "GetPowerTypeSecrecy", 13 },
    { "ShouldUnitPowerBeSecret", "player", 0 },
    { "ShouldUnitPowerBeSecret", "party1", 0 },
    { "ShouldUnitPowerBeSecret", "target", 0 },
    { "ShouldUnitPowerMaxBeSecret", "player", 0 },
    { "ShouldUnitPowerMaxBeSecret", "party1", 0 },
    { "ShouldUnitHealthMaxBeSecret", "party1" },
    { "ShouldUnitSpellCastingBeSecret", "player" },
    { "ShouldUnitThreatStateBeSecret", "player", "target" },
    { "ShouldUnitThreatStateBeSecret", "party1", "target" },
    { "ShouldUnitThreatValuesBeSecret", "player", "target" },
    { "ShouldUnitThreatValuesBeSecret", "party1", "target" },
    { "ShouldUnitIdentityBeSecret", "party1" },
    { "CanCompareUnitTokens", "player", "party1" },
}

PP.COST_FIELDS = { "type", "name", "cost", "minCost", "costPercent", "costPerSec" }
PP.COST_KEEP = { type = true, name = true, cost = true, minCost = true, costPercent = true, costPerSec = true }
PP.LOC_FIELDS = { "locType", "spellID", "displayText", "startTime", "timeRemaining", "duration", "lockoutSchool", "priority", "displayType" }
PP.LOC_KEEP = { locType = true, spellID = true, displayText = true, priority = true, displayType = true, duration = true }

-- Presence only: { namespace-or-global, name }.
PP.API_LIST = {
    { "UnitPowerPercent" }, { "UnitGetTotalAbsorbs" }, { "UnitGetIncomingHeals" },
    { "CreateUnitHealPredictionCalculator" }, { "UnitGetDetailedHealPrediction" },
    { "GetPowerRegen" }, { "GetPowerRegenForPowerType" }, { "UnitCastingInfo" }, { "UnitChannelInfo" },
    { "UnitInRange" }, { "UnitThreatSituation" }, { "UnitDetailedThreatSituation" },
    { "C_StringUtil", "TruncateWhenZero" }, { "C_CurveUtil", "CreateCurve" }, { "C_CurveUtil", "CreateColorCurve" },
    { "C_Spell", "GetSpellCooldownDuration" }, { "C_Spell", "GetSpellCharges" }, { "C_Spell", "GetSpellPowerCost" },
    { "C_UnitAuras", "GetAuraDuration" }, { "C_UnitAuras", "GetAuraApplicationDisplayCount" },
    { "C_UnitAuras", "GetAuraDispelTypeColor" }, { "C_UnitAuras", "IsAuraFilteredOutByInstanceID" },
    { "C_UnitAuras", "GetUnitAuraInstanceIDs" },
    { "C_LossOfControl", "GetActiveLossOfControlData" }, { "C_LossOfControl", "GetActiveLossOfControlDataCount" },
    { "C_CombatLog", "IsCombatLogRestricted" }, { "C_Item", "GetItemCount" },
    { "UnitLevel" }, { "UnitExists" }, { "UnitClassification" }, { "UnitEffectiveLevel" }, { "UnitIsPlusMob" }, { "UnitCreatureType" },
}

-- { event, unit filter for RegisterUnitEvent (none = the event has no unit) }. RegisterUnitEvent
-- takes at most two units, so absorb and prediction cover player + party1; the handler drops any
-- other unit a plain RegisterEvent fallback would deliver.
PP.EVENTS = {
    { "UNIT_POWER_UPDATE", "player" }, { "UNIT_POWER_FREQUENT", "player" },
    { "UNIT_SPELLCAST_SUCCEEDED", "player" }, { "UNIT_SPELLCAST_START", "player" },
    { "UNIT_SPELLCAST_CHANNEL_START", "player" }, { "UNIT_SPELLCAST_CHANNEL_STOP", "player" },
    { "UNIT_AURA", "player", "target" },
    { "UNIT_ABSORB_AMOUNT_CHANGED", "player", "party1" }, { "UNIT_HEAL_PREDICTION", "player", "party1" },
    { "PARTY_KILL" }, { "UNIT_DIED" }, { "PLAYER_TARGET_DIED" },
    { "LOSS_OF_CONTROL_ADDED" }, { "LOSS_OF_CONTROL_UPDATE" },
    { "PLAYER_CONTROL_LOST" }, { "PLAYER_CONTROL_GAINED" },
}

PP.lastCast = nil     -- GetTime of the last player cast that finished
PP.lastManaCast = nil -- ... of the last one that cost mana (the five second rule clock)
PP.manaClockUnknown = false -- a cast whose cost could not be read has gone by since lastManaCast

CP.Install(PP, {
    key = "priest", label = "priest",
    logCap = 50,
    -- The power logs hold more: sampled to about one entry a second, 50 would cover under a minute and
    -- push the idle window after a mana cast out. Still bounded.
    logCaps = { power = 300, powerFrequent = 300, powerOther = 300 },
    logSeconds = 1200, combatDelay = 4, oocDelay = 2, sweepKey = "ppCooldown",
    logsText = "power ticks, casts, auras, kills, absorbs",
    todo = "Cast, wand, drink, shield yourself and a party member.",
})

function PP.ResetState()
    PP.lastCast, PP.lastManaCast, PP.manaClockUnknown = nil, nil, false
end

function PP.MetaFields(meta)
    meta.costAssumption = PP.COST_ASSUMPTION
end

-- The five second rule clock of a power or cast entry. An unreadable cost since lastManaCast makes it
-- stale: say so instead of a number.
function PP.Clock(e, now)
    if PP.manaClockUnknown then
        e.sinceManaCastUnknown = true
    elseif PP.lastManaCast then
        e.sinceManaCast = PP.Round(now - PP.lastManaCast)
    end
    if PP.lastCast then e.sinceCast = PP.Round(now - PP.lastCast) end
end

-- Snapshot helpers ---------------------------------------------------------------------------

function PP.Curve()
    local ok, curve = pcall(function() return _G.CurveConstants.ScaleTo100 end)
    if ok and type(curve) ~= "nil" then return curve end
    return nil
end

function PP.EnumValue(enumName, field)
    local ok, v = pcall(function() return _G.Enum[enumName][field] end)
    if ok and type(v) == "number" and not IsSecret(v) then return v end
    return nil
end

-- Snapshot parts (each gets its own table, tagged, and is pcall'd by Section) ------------------

-- The mana cost of a spell id: the record, with the first cost entry described.
function PP.CostRec(id)
    local rec, v = Invoke(false, Api("C_Spell", "GetSpellPowerCost"), id)
    PP.Stamp(rec)
    rec.spellName = PP.IdName(id)
    if rec.ok and IsPlainTable(v) then
        local okc, n = pcall(function() return #v end)
        if okc and type(n) == "number" and not IsSecret(n) then rec.count = n end
        local okf, first = pcall(function() return v[1] end)
        if okf and IsPlainTable(first) then
            local holder = {}
            ReadFields(holder, first, PP.COST_FIELDS, PP.COST_KEEP)
            rec.first = holder.fields
        end
    end
    return rec
end

function PP.PartMana(sec)
    local curve = PP.Curve()
    for _, unit in ipairs({ "player", "party1" }) do
        sec[unit .. "Power"] = PP.Call(true, Api("UnitPower"), unit, PP.MANA)
        sec[unit .. "PowerMax"] = PP.Call(true, Api("UnitPowerMax"), unit, PP.MANA)
        sec[unit .. "PowerPercent"] = PP.Call(true, Api("UnitPowerPercent"), unit, PP.MANA, false)
        if type(curve) ~= "nil" then
            sec[unit .. "PowerPercentCurve"] = PP.Call(true, Api("UnitPowerPercent"), unit, PP.MANA, false, curve)
        else
            sec[unit .. "PowerPercentCurve"] = { skipped = "CurveConstants.ScaleTo100 absent", inCombat = PP.combat }
        end
    end
    sec.regen = PP.Call(true, Api("GetPowerRegen"))
    sec.regenForMana = PP.Call(true, Api("GetPowerRegenForPowerType"), PP.MANA)
    sec.casting = PP.Call(true, Api("UnitCastingInfo"), "player")
    sec.channeling = PP.Call(true, Api("UnitChannelInfo"), "player")
    sec.costAssumption = PP.COST_ASSUMPTION
    sec.cost = { inCombat = PP.combat }
    for _, id in ipairs(PP.COST_IDS) do sec.cost["s" .. id] = PP.CostRec(id) end
end

function PP.ShieldFor(unit)
    local out = { inCombat = PP.combat }
    out.exists = PP.Call(true, Api("UnitExists"), unit)
    local arec, absorbs = Invoke(true, Api("UnitGetTotalAbsorbs"), unit)
    out.totalAbsorbs = PP.Stamp(arec)
    out.incomingHeals = PP.Call(true, Api("UnitGetIncomingHeals"), unit)
    -- A secret number handed to TruncateWhenZero is the sanctioned way to turn "is there any shield"
    -- into text; only the call's secrecy is read here, Parker judges what it draws.
    if arec.ok and (arec.n or 0) >= 1 then
        out.truncateWhenZero = PP.Call(true, Api("C_StringUtil", "TruncateWhenZero"), absorbs)
    else
        out.truncateWhenZero = { skipped = "no absorb value to pass", inCombat = PP.combat }
    end
    local crec, calc = Invoke(false, Api("CreateUnitHealPredictionCalculator"))
    out.calculator = PP.Stamp(crec)
    if crec.ok and type(calc) ~= "nil" and not IsSecret(calc) then
        out.fill = PP.Call(true, Api("UnitGetDetailedHealPrediction"), unit, "player", calc)
        for _, name in ipairs({ "GetDamageAbsorbs", "GetIncomingHeals", "GetHealAbsorbs" }) do
            out[name] = PP.Call(true, PP.Method(calc, name), calc)
        end
    end
    return out
end

function PP.PartShield(sec)
    for _, unit in ipairs({ "player", "party1" }) do sec[unit] = PP.ShieldFor(unit) end
end

function PP.PartAuras(sec)
    local byPlayer = Api("C_UnitAuras", "GetPlayerAuraBySpellID")
    local byUnit = Api("C_UnitAuras", "GetUnitAuraBySpellID")
    local byName = Api("C_UnitAuras", "GetAuraDataBySpellName")
    for _, s in ipairs(PP.resolved) do
        if s.aura then
            local entry = { name = s.name, inCombat = PP.combat }
            sec[s.key] = entry
            local ok, err = pcall(function()
                entry.byName = PP.FieldsBrief((AuraCall(byName, "player", s.name, HELPFUL)))
                for _, id in ipairs(s.ids) do
                    local cell = { spellName = PP.IdName(id), playerByID = PP.FieldsBrief((AuraCall(byPlayer, id))) }
                    entry["s" .. id] = cell
                    for _, unit in ipairs(PP.AURA_UNITS) do
                        cell[unit] = PP.FieldsBrief((AuraCall(byUnit, unit, id)))
                    end
                end
            end)
            if not ok then entry.entryError = ErrText(err) end
        end
    end
end

function PP.PartTriage(sec)
    local inRange = Api("C_Spell", "IsSpellInRange")
    -- The first friendly spell that answers for the player (a spell the player lacks answers nil).
    local used
    local tried = {}
    for _, name in ipairs(PP.RANGE_NAMES) do
        tried[#tried + 1] = name
        local rec = Invoke(false, inRange, name, "player")
        if rec.ok and rec.r1 and rec.r1.type ~= "nil" then
            used = name
            break
        end
    end
    sec.rangeTried = table.concat(tried, ",")
    sec.rangeSpell = used or "none answered"
    local rangeName = used or PP.RANGE_NAMES[1]
    sec.party1InRangeOfHeal = PP.Call(true, inRange, rangeName, "party1")
    sec.targetInRangeOfHeal = PP.Call(true, inRange, rangeName, "target")
    sec.unitInRangeParty1 = PP.Call(true, Api("UnitInRange"), "party1")
    sec.party1Exists = PP.Call(true, Api("UnitExists"), "party1")
    sec.party1IsDeadOrGhost = PP.Call(true, Api("UnitIsDeadOrGhost"), "party1")
    sec.party1IsConnected = PP.Call(true, Api("UnitIsConnected"), "party1")
    sec.threatPlayer = PP.Call(true, Api("UnitThreatSituation"), "player", "target")
    sec.threatParty1 = PP.Call(true, Api("UnitThreatSituation"), "party1", "target")
    sec.detailedThreatPlayer = PP.Call(true, Api("UnitDetailedThreatSituation"), "player", "target")
end

-- How durable the target is: the reads a fight-length estimate would lean on. Each is plain or
-- secret per read; an API this client lacks is recorded absent.
function PP.PartTarget(sec)
    sec.exists = PP.Call(true, Api("UnitExists"), "target")
    sec.classification = PP.Call(true, Api("UnitClassification"), "target")
    sec.level = PP.Call(true, Api("UnitLevel"), "target")
    sec.effectiveLevel = PP.Call(true, Api("UnitEffectiveLevel"), "target")
    sec.isPlusMob = PP.Call(true, Api("UnitIsPlusMob"), "target")
    sec.creatureType = PP.Call(true, Api("UnitCreatureType"), "target")
end

function PP.PartLossOfControl(sec)
    sec.count = PP.Call(true, Api("C_LossOfControl", "GetActiveLossOfControlDataCount"))
    sec.first = PP.Stamp((InvokeTableKeep(PP.LOC_FIELDS, PP.LOC_KEEP, Api("C_LossOfControl", "GetActiveLossOfControlData"), 1)))
end

-- Never register COMBAT_LOG_EVENT_UNFILTERED: it is protected on Forever, and the refusal
-- (ADDON_ACTION_FORBIDDEN) goes through the global error handler, which pcall cannot catch.
PP.CLEU_REGISTER = "forbidden (ADDON_ACTION_FORBIDDEN, measured on 16001 2026-10-09)"

-- A readable player aura instance id, or nil (in combat the read may be refused: that is data).
function PP.AuraInstance()
    local rec, v = Invoke(false, Api("C_UnitAuras", "GetUnitAuraInstanceIDs"), "player", "HELPFUL", 1)
    if rec.ok and IsPlainTable(v) then
        local ok, id = pcall(function() return v[1] end)
        if ok and type(id) == "number" and not IsSecret(id) then return id end
    end
    return nil
end

-- Can a duration object be asked "less than 3 s left?" with a step curve, and is the answer plain?
function PP.DurationTrial(sec)
    local id = PP.AuraInstance()
    sec.instance = id and "found" or "none"
    if not id then return end
    local rec, dur = Invoke(false, Api("C_UnitAuras", "GetAuraDuration"), "player", id)
    sec.object = PP.Stamp(rec)
    if not (rec.ok and type(dur) ~= "nil" and not IsSecret(dur)) then return end
    for _, name in ipairs({ "GetRemainingDuration", "IsZero", "HasExpired", "IsActive" }) do
        sec[name] = PP.Call(true, PP.Method(dur, name), dur)
    end
    local crec, curve = Invoke(false, Api("C_CurveUtil", "CreateCurve"))
    sec.curve = PP.Stamp(crec)
    if crec.ok and type(curve) ~= "nil" and not IsSecret(curve) then
        sec.setType = GS.Step(curve, "SetType", PP.EnumValue("LuaCurveType", "Step") or 1)
        sec.addPoint = GS.Step(curve, "AddPoint", 0, 1)
        sec.addPoint2 = GS.Step(curve, "AddPoint", 3.001, 0)
        sec.evaluateRemaining = PP.Call(true, PP.Method(dur, "EvaluateRemainingDuration"), dur, curve)
    end
end

function PP.PartMisc(sec)
    sec.combatLogRestricted = PP.Call(true, Api("C_CombatLog", "IsCombatLogRestricted"))
    sec.cleuRegister = PP.CLEU_REGISTER
    sec.items = { inCombat = PP.combat }
    for _, name in ipairs(PP.ITEMS) do
        sec.items[name] = PP.Call(true, Api("C_Item", "GetItemCount"), name)
    end
    sec.durationObject = { inCombat = PP.combat }
    local ok, err = pcall(PP.DurationTrial, sec.durationObject)
    if not ok then sec.durationObject.trialError = ErrText(err) end
end

function PP.PartApis(sec)
    for _, entry in ipairs(PP.API_LIST) do
        local label = entry[2] and (entry[1] .. "." .. entry[2]) or entry[1]
        sec[label] = Api(entry[1], entry[2]) and "present" or "absent"
    end
    sec["CurveConstants.ScaleTo100"] = PP.Curve() and "present" or "absent"
end

PP.PARTS = {
    { "env", SectionEnv },
    { "secrets", PP.PartSecrets },
    { "spells", PP.PartSpells },
    { "mana", PP.PartMana },
    { "shield", PP.PartShield },
    { "auras", PP.PartAuras },
    { "cooldowns", PP.PartCooldowns },
    { "triage", PP.PartTriage },
    { "target", PP.PartTarget },
    { "lossOfControl", PP.PartLossOfControl },
    { "misc", PP.PartMisc },
    { "apis", PP.PartApis },
}

-- Storage, logs -------------------------------------------------------------------------------

-- Total mana cost of a spell id from C_Spell.GetSpellPowerCost, or nil when unreadable. A call that
-- succeeds and returns nothing (Shoot) or an empty plain table is a FREE spell: cost 0. An entry
-- whose type or cost is secret (or missing) makes the whole answer nil: skipping it would read as a
-- free cast. So does a throwing call or a secret return.
function PP.ManaCost(id)
    local ok, v = pcall(Api("C_Spell", "GetSpellPowerCost"), id)
    if not ok then return nil end
    if type(v) == "nil" then return 0 end
    if not IsPlainTable(v) then return nil end
    local okc, n = pcall(function() return #v end)
    if not okc or type(n) ~= "number" or IsSecret(n) then return nil end
    local total = 0
    for i = 1, n do
        local okf, entry = pcall(function() return v[i] end)
        if not okf or not IsPlainTable(entry) then return nil end
        local costType = PlainNumberField(entry, "type")
        local cost = PlainNumberField(entry, "cost")
        if costType == nil or cost == nil then return nil end
        if costType == PP.MANA then total = total + cost end
    end
    return total
end

-- true/false when both GUIDs are plain, nil otherwise (a secret GUID is never compared).
function PP.SameGuid(guid, unit)
    if IsSecret(guid) or type(guid) ~= "string" then return nil end
    local rec, mine = Invoke(false, Api("UnitGUID"), unit)
    if not rec.ok or IsSecret(mine) or type(mine) ~= "string" then return nil end
    return guid == mine
end

-- One Desc as a short shape word: "secret" or "<type>:<value>". The shape of an event is what the
-- sampler compares, never a raw argument.
function PP.Shape(desc)
    if desc.isSecret ~= false then return "secret" end
    return tostring(desc.type) .. ":" .. tostring(desc.value)
end

-- Enum.PowerType by event token ("MANA" -> 0, "RUNIC_POWER" -> 6), built once from the client's own enum.
function PP.PowerEnum(token)
    if type(PP.powerTokens) ~= "table" then
        local map = {}
        pcall(function()
            for key, num in pairs(_G.Enum.PowerType) do
                if type(key) == "string" and type(num) == "number" and not IsSecret(num) then
                    map[string.upper((string.gsub(key, "(%l)(%u)", "%1_%2")))] = num
                end
            end
        end)
        PP.powerTokens = map
    end
    return PP.powerTokens[token]
end

-- UnitPower("player", <the event's power type>) as a plain/secret word, or nil when the unit or the
-- power type of the event is not a plain value (a secret argument is never passed on).
function PP.PowerReadout(udesc, pdesc)
    if udesc.isSecret ~= false or udesc.value ~= "player" then return nil end
    if pdesc.isSecret ~= false or pdesc.type ~= "string" or pdesc.value == nil then return nil end
    return PP.B(Api("UnitPower"), "player", PP.PowerEnum(pdesc.value) or pdesc.value)
end

-- The sampler for a high-rate stream. An event is kept when its shape (event, unit, power type; plain
-- or secret) differs from the previous event of the stream, or PP.FREQUENT_GAP seconds have passed
-- since the last kept one. A skipped event still counts in the log's total and sampledOut, so the raw
-- rate stays visible. Returns keep, and how many events the kept entry stands for.
function PP.Sample(stream, logName, e)
    local key = tostring(e.event) .. "|" .. PP.Shape(e.unit) .. "|" .. PP.Shape(e.powerType)
    local now = PlainTime()
    local st = PP.sample[stream]
    if type(st) ~= "table" then
        st = { skipped = 0 }
        PP.sample[stream] = st
    end
    local same = st.key == key
    st.key = key
    local log = PP.Log(logName)
    log.minGap = PP.FREQUENT_GAP
    local skip = false
    if same and now ~= nil and st.t ~= nil then
        skip = now - st.t < PP.FREQUENT_GAP
    elseif same and now == nil then
        -- No plain clock: sample by count instead, and say so.
        st.count = (st.count or 0) + 1
        skip = st.count < PP.FREQUENT_COUNT
        log.countSampling = PP.FREQUENT_COUNT
    end
    if skip then
        st.skipped = st.skipped + 1
        log.total = log.total + 1
        log.sampledOut = (log.sampledOut or 0) + 1
        return false, 0
    end
    local skipped = same and st.skipped or 0
    st.skipped, st.t, st.count = 0, now, 0
    return true, skipped
end

function PP.LogPower(name, event, unit, powerType)
    if PP.ForeignUnit(unit, PP.PLAYER_SET) then return end
    local e = { event = event, unit = Desc(unit, true), powerType = Desc(powerType, true) }
    local pt = e.powerType
    -- Mana is the log's subject; a plain power type that is not mana goes to powerOther (so a periodic
    -- tick on another power type shows up); a secret one is kept and described.
    local other = pt.isSecret == false and pt.type == "string" and pt.value ~= nil and pt.value ~= "MANA"
    local log = other and "powerOther" or name
    local stream = (name == "powerFrequent" and (other and "frequentOther" or "frequent")) or (other and "updateOther") or nil
    if stream then
        local keep, skipped = PP.Sample(stream, log, e)
        if not keep then return end
        if skipped > 0 then e.skippedBefore = skipped end
    end
    e.unitPower = PP.PowerReadout(e.unit, pt)
    PP.Push(log, PP.Mark(e, log, true))
end

function PP.LogCast(event, unit, castGUID, spellID)
    if PP.ForeignUnit(unit, PP.PLAYER_SET) then return end
    local e = { event = event, unit = Desc(unit, true), castGUID = Desc(castGUID), spellID = Desc(spellID, true) }
    PP.Mark(e, "cast")
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        PP.lastCast = e.t
        local id = PlainSpellID(unit, castGUID, spellID)
        local cost = id and PP.ManaCost(id) or nil
        if id then e.manaCost = cost end
        if cost == nil then
            -- A secret spell id or an unreadable cost: this cast may have restarted the five second rule.
            PP.manaClockUnknown = true
        elseif cost > 0 then
            PP.lastManaCast = e.t
            PP.manaClockUnknown = e.t == nil
        end
    end
    PP.Push("cast", e)
end

function PP.LogAura(event, unit, info)
    if PP.ForeignUnit(unit, PP.AURA_SET) then return end
    PP.Push("aura", PP.Mark(RecordAura(event, unit, info), "aura"))
end

function PP.LogShield(event, unit)
    if PP.ForeignUnit(unit, PP.SHIELD_SET) then return end
    PP.Push("shield", PP.Mark({ event = event, unit = Desc(unit, true) }, "shield"))
end

function PP.LogKill(event, attacker, target)
    local e = { event = event, arg1 = Desc(attacker), arg2 = Desc(target) }
    if event == "PARTY_KILL" then
        e.attackerIsPlayer = PP.SameGuid(attacker, "player")
        e.targetIsTarget = PP.SameGuid(target, "target")
    end
    PP.Push("kill", PP.Mark(e, "kill"))
end

function PP.LogDied(event, guid)
    local e = { event = event, arg1 = Desc(guid) }
    e.isTarget = PP.SameGuid(guid, "target")
    e.isPlayer = PP.SameGuid(guid, "player")
    PP.Push("died", PP.Mark(e, "died"))
end

function PP.LogLoc(event, ...)
    local e = { event = event, argCount = select("#", ...) }
    for i = 1, math.min(e.argCount, 3) do e["arg" .. i] = Desc((select(i, ...)), true) end
    PP.Push("loc", PP.Mark(e, "loc"))
end

-- Snapshot timing and events ------------------------------------------------------------------

PP.HANDLERS = {
    UNIT_POWER_UPDATE = function(event, ...) PP.LogPower("power", event, ...) end,
    UNIT_POWER_FREQUENT = function(event, ...) PP.LogPower("powerFrequent", event, ...) end,
    UNIT_SPELLCAST_SUCCEEDED = function(event, ...) PP.LogCast(event, ...) end,
    UNIT_SPELLCAST_START = function(event, ...) PP.LogCast(event, ...) end,
    UNIT_SPELLCAST_CHANNEL_START = function(event, ...) PP.LogCast(event, ...) end,
    UNIT_SPELLCAST_CHANNEL_STOP = function(event, ...) PP.LogCast(event, ...) end,
    UNIT_AURA = function(event, ...) PP.LogAura(event, ...) end,
    UNIT_ABSORB_AMOUNT_CHANGED = function(event, ...) PP.LogShield(event, ...) end,
    UNIT_HEAL_PREDICTION = function(event, ...) PP.LogShield(event, ...) end,
    PARTY_KILL = function(event, ...) PP.LogKill(event, ...) end,
    PLAYER_TARGET_DIED = function(event, ...) PP.LogKill(event, ...) end,
    UNIT_DIED = function(event, ...) PP.LogDied(event, ...) end,
    LOSS_OF_CONTROL_ADDED = function(event, ...) PP.LogLoc(event, ...) end,
    LOSS_OF_CONTROL_UPDATE = function(event, ...) PP.LogLoc(event, ...) end,
    PLAYER_CONTROL_LOST = function(event, ...) PP.LogLoc(event, ...) end,
    PLAYER_CONTROL_GAINED = function(event, ...) PP.LogLoc(event, ...) end,
}

-------------------------------------------------------------------------------
-- /fscheck shaman: what a totem bar can read and do on this client
-------------------------------------------------------------------------------
-- Built for a fresh low level Shaman on WoW Forever (16001): the first Earth totem comes at level 4, the
-- other elements and the Call of the Elements / Totemic Recall spells later, so every check that needs a
-- spell the player does not know yet is SKIPPED and NAMED (checks.notRun, and a chat line), never failed.
-- Same machinery as `/fscheck priest` (CP above): `/fscheck shaman` (any time, any class) takes an ooc and
-- a combat snapshot (the other one follows the next pull, 4 s in, or the end of the fight) and logs for
-- 30 minutes. Results: ForeverSTUwaveDB.fscheck.shaman.
--   shaman.ooc / shaman.combat   parts, each record tagged inCombat true/false:
--     player     class, level, GetNumTotemSlots, the slot constants (FIRE_TOTEM_SLOT ...) and
--                SHAMAN_TOTEM_PRIORITIES;
--     secrets    C_Secrets predicates, ShouldTotemSlotBeSecret(1..4), ShouldTotemSpellBeSecret per known spell;
--     totems     per slot s1..s4: GetTotemInfo with ALL returns (plain value or secret, per field; `brief` is
--                the same as one string; `looksBlank` flags the known 1.60.1 report of a live totem that
--                answers with no name), GetTotemTimeLeft, GetTotemCannotDismiss, C_TooltipInfo.GetTotem and
--                the NEWER duration API: GetTotemDuration(slot) returns a duration object (that is what
--                ElvUI's "new API blizzard provided" is: it stays readable when the numbers are secret);
--                its methods are read plain or secret, handed to a hidden Cooldown frame
--                (SetCooldownFromDurationObject) and to a hidden StatusBar (SetTimerDuration);
--     multicast  the native bar's data: C_ActionBar.GetMultiCastBarIndex, HasMultiCastActionBar / Page,
--                GetMultiCastTotemSpells per action id 1..12 (spell ids with names), and for 3 sets x 4 slots
--                the action id (barIndex - 1) * 12 + (set - 1) * 4 + slot with HasAction / GetActionInfo /
--                GetActionTexture on it, plus Blizzard's own MultiCastActionButtonN ids when they exist;
--     frames     MultiCastActionBarFrame, MultiCastSlotButton1-4, MultiCastSummonSpellButton,
--                MultiCastRecallSpellButton, MultiCastFlyoutFrame, MultiCastActionButton1, TotemFrame: exists,
--                shown, alpha, scale, rect, size, anchors; and whether the native bar's rect overlaps our
--                action bar group (FSActionBarStack, FSConsole). READ ONLY: these frames are never changed;
--     spells / cooldowns   Call of the Elements 66842, Call of the Ancestors 66843, Totemic Recall 36936 and
--                every totem by name (the client resolves a name to the rank the player knows): ids,
--                names, IsPlayerSpell, secrecy, cooldown plain/secret, duration object;
--     misc / apis   totem items, constants, presence of every API used;
--     checks     notRun (what could not run and why), notRunCount, spellsKnown, spellsNotKnown.
--   shaman.logs.<name>  bounded ring buffers: totem (PLAYER_TOTEM_UPDATE: slot argument plain or secret and a
--                GetTotemInfo readout for it per event), cast (the player's start / succeeded / failed /
--                interrupted), multicast (UPDATE_MULTI_CAST_ACTIONBAR with HasMultiCastActionBar), click (the
--                totem button row: each click with the totem state before and after, and the events that followed
--                it within 3 s).
-- Nothing protected runs by itself. These run ONLY when Parker types them:
--   /fscheck shaman buttons        a small labelled TEMPORARY strip of 3 SecureActionButtonTemplate buttons:
--                                  dismiss (left slot 1, right slot 2, shift-left 3, shift-right 4 through
--                                  the secure `destroytotem` action), a `/castsequence` through two known
--                                  totems and Totemic Recall (each only when known). Built and shown out of
--                                  combat only; in combat the command refuses. When the check is not logging it
--                                  re-arms the logging over the saved record and never replaces it.
--   /fscheck shaman buttons off    hides it (out of combat). In combat (also `shaman off`, the 30 minute timeout
--                                  and `reset` in combat) it only sets alpha 0: the buttons stay clickable,
--                                  invisible, until combat ends, then a PLAYER_REGEN_ENABLED wait finishes
--                                  the hide (Hide, EnableMouse false) out of combat.
--   /fscheck shaman setslot        P1: SetMultiCastSpell on the earth (or first) slot from addon code, run it
--                                  IN COMBAT yourself. The chat line comes first because a blocked call
--                                  prints ADDON_ACTION_BLOCKED, which pcall cannot catch. The action id is the
--                                  native MultiCastActionButtonN:CalculateAction() when it exists, else
--                                  (bar - 1) * 12 + slot (run.actionSource says which). It puts the old pick
--                                  back only when the slot held a plain spell; otherwise the chat line says
--                                  the slot stays changed and to set it back by hand.
--   /fscheck shaman destroy [n]    DestroyTotem(n) from addon code (default: the first live totem).
-- Rules this section keeps: never register the combat log event (protected on Forever); a secret is described,
-- never compared, branched on or stored; Blizzard's totem frames and buttons are only read.

local SH = {}

SH.SLOT_COUNT = 4
SH.PAGES = 3
SH.PAGE_SIZE = 4
SH.BAR_SIZE = 12              -- NUM_ACTIONBAR_BUTTONS: action ids per bar
SH.BAR_FALLBACK = 12          -- the bar index assumed when the call cannot be read
SH.SLOT_PICK_ORDER = { 2, 1, 3, 4 }   -- SHAMAN_TOTEM_PRIORITIES: earth first, the first totem a shaman gets
SH.FOLLOW_SECONDS = 3
SH.FOLLOW_CAP = 8
SH.NOTRUN_CAP = 40
SH.RUN_CAP = 6
SH.STRIP_NAME = "FSCheckShamanStrip"
SH.STRIP_Y = -190             -- centre y from the screen centre: the strip must stay above Layout.lua's tcast (top -286)
SH.BUTTON_PREFIX = "FSCheckShamanBtn"
SH.PLAYER_SET = { player = true }
SH.CONSTANTS = { "FIRE_TOTEM_SLOT", "EARTH_TOTEM_SLOT", "WATER_TOTEM_SLOT", "AIR_TOTEM_SLOT", "MAX_TOTEMS" }
SH.DURATION_METHODS = {
    "GetRemainingDuration", "GetElapsedDuration", "GetTotalDuration", "IsZero", "HasExpired", "HasStarted",
    "IsActive", "HasSecretValues",
}

-- { element, english name, level of the first rank } up to the level 30 cap and a little above (research
-- 2026-10-10: foreverdb / talentsforever tooltips). A name the client does not resolve is simply not known yet.
SH.TOTEMS = {
    { "earth", "Stoneskin Totem", 4 }, { "earth", "Earthbind Totem", 6 }, { "earth", "Stoneclaw Totem", 8 },
    { "earth", "Strength of Earth Totem", 10 }, { "earth", "Tremor Totem", 18 },
    { "fire", "Searing Totem", 10 }, { "fire", "Frost Resistance Totem", 24 }, { "fire", "Magma Totem", 26 },
    { "fire", "Flametongue Totem", 28 },
    { "water", "Healing Stream Totem", 20 }, { "water", "Poison Cleansing Totem", 22 },
    { "water", "Disease Cleansing Totem", 22 }, { "water", "Mana Spring Totem", 26 },
    { "water", "Fire Resistance Totem", 28 }, { "water", "Mana Tide Totem", 25 },
    { "air", "Grounding Totem", 30 }, { "air", "Nature Resistance Totem", 30 }, { "air", "Windfury Totem", 32 },
    { "air", "Sentry Totem", 34 }, { "air", "Windwall Totem", 36 }, { "air", "Grace of Air Totem", 42 },
}

-- { key, english name, { ids }, reads auras, level }. Ids: 66842, 66843, 66844 and 36936 are the client's own
-- TOTEM_MULTI_CAST_SUMMON_SPELLS / RECALL_SPELLS; Fire Nova is a spell on Forever (research 2026-10-10).
-- Totems have no id here: the name resolves to the rank the player knows.
SH.SPELLS = {
    { "coe", "Call of the Elements", { 66842 }, false, 20 },
    { "coa", "Call of the Ancestors", { 66843 }, false, 30 },
    { "cos", "Call of the Spirits", { 66844 }, false, 40 },
    { "recall", "Totemic Recall", { 36936 }, false, 20 },
    { "projection", "Totemic Projection", {}, false, 22 },
    { "fire_nova", "Fire Nova", { 408341 }, false, 12 },
}
for _, t in ipairs(SH.TOTEMS) do
    local key = string.lower((string.gsub((string.gsub(t[2], " Totem$", "")), "%s+", "_")))
    SH.SPELLS[#SH.SPELLS + 1] = { key, t[2], {}, false, t[3] }
end

-- The totem items a cast needs in the bags (Classic Era ids, UNVERIFIED on Forever).
SH.ITEMS = { { "earth", 5175 }, { "fire", 5176 }, { "water", 5177 }, { "air", 5178 } }

SH.PREDICATES = {
    { "HasSecretRestrictions" }, { "ShouldCooldownsBeSecret" }, { "ShouldAurasBeSecret" },
    { "ShouldTotemSlotBeSecret", 1 }, { "ShouldTotemSlotBeSecret", 2 },
    { "ShouldTotemSlotBeSecret", 3 }, { "ShouldTotemSlotBeSecret", 4 },
    { "ShouldUnitSpellCastingBeSecret", "player" },
}

-- Blizzard's totem frames (read only) and our own action bar group (the overlap target).
SH.FRAMES = {
    "MultiCastActionBarFrame", "MultiCastSlotButton1", "MultiCastSlotButton2", "MultiCastSlotButton3",
    "MultiCastSlotButton4", "MultiCastSummonSpellButton", "MultiCastRecallSpellButton", "MultiCastFlyoutFrame",
    "MultiCastActionButton1", "TotemFrame",
}
SH.OURS = { "FSActionBarStack", "FSConsole" }

-- Presence only: { namespace-or-global, name }.
SH.API_LIST = {
    { "GetTotemInfo" }, { "GetTotemTimeLeft" }, { "GetTotemDuration" }, { "GetNumTotemSlots" },
    { "GetTotemCannotDismiss" }, { "DestroyTotem" }, { "SetMultiCastSpell" }, { "GetMultiCastTotemSpells" },
    { "HasMultiCastActionBar" }, { "HasMultiCastActionPage" }, { "ChangeMultiCastActionPage" },
    { "GetMultiCastBarIndex" }, { "C_ActionBar", "GetMultiCastBarIndex" },
    { "C_Secrets", "ShouldTotemSlotBeSecret" }, { "C_Secrets", "ShouldTotemSpellBeSecret" },
    { "C_TooltipInfo", "GetTotem" }, { "C_Spell", "GetSpellCooldownDuration" },
    { "HasAction" }, { "GetActionInfo" }, { "GetActionTexture" }, { "C_Item", "GetItemCount" }, { "UnitLevel" },
}

-- { event, unit filter }: the combat log event is never among them.
SH.EVENTS = {
    { "PLAYER_TOTEM_UPDATE" }, { "UPDATE_MULTI_CAST_ACTIONBAR" },
    { "UNIT_SPELLCAST_START", "player" }, { "UNIT_SPELLCAST_SUCCEEDED", "player" },
    { "UNIT_SPELLCAST_FAILED", "player" }, { "UNIT_SPELLCAST_INTERRUPTED", "player" },
}

SH.lastClick = nil    -- the click entry still collecting the events that follow it
SH.strip = nil        -- { host, buttons }: the totem button row frames (frames are never destroyed, so they are reused)
SH.stripShown = false -- the strip is up (shown, or only faded in combat) and not yet really hidden
SH.hidePending = false -- a real hide waits for PLAYER_REGEN_ENABLED
SH.regenFrame = nil   -- the plain frame that waits for it (apart from the check's event frame, which stop unregisters)

CP.Install(SH, {
    key = "shaman", label = "shaman",
    logCap = 50, logCaps = { totem = 100 },
    logSeconds = 1800, combatDelay = 4, oocDelay = 2, sweepKey = "shCooldown",
    logsText = "PLAYER_TOTEM_UPDATE readouts, casts, native bar updates, totem button clicks",
    todo = "Drop a totem, dismiss it, cast a few spells. /fscheck shaman buttons (out of combat) shows the totem buttons; "
        .. "/fscheck shaman setslot is the combat test, run it yourself in a fight.",
})

SH.PartGenericSecrets = SH.PartSecrets   -- the installed one; SH.PartSecrets below adds the totem spell predicates

function SH.ResetState()
    SH.lastClick = nil
end

-- A start that replaces the saved record keeps the manual runs (setslot, destroy) and the strip record: they are
-- written without starting the check, and a fresh snapshot of the totems says nothing about them. Merged (old
-- runs first, then any the fresh record already holds) and capped.
function SH.CarryOver(old, fresh)
    for _, name in ipairs({ "setslot", "destroy" }) do
        local was, now = old[name], fresh[name]
        local runs = {}
        for _, list in ipairs({ type(was) == "table" and was.runs or {}, type(now) == "table" and now.runs or {} }) do
            if type(list) == "table" then
                for _, run in ipairs(list) do runs[#runs + 1] = run end
            end
        end
        if #runs > 0 then
            while #runs > SH.RUN_CAP do table.remove(runs, 1) end
            fresh[name] = { runs = runs }
        end
    end
    if type(old.strip) == "table" and fresh.strip == nil then fresh.strip = old.strip end
end

function SH.MetaFields(meta)
    meta.slotNote = "slot numbers are the GetTotemInfo / DestroyTotem indices; the constants in player.constants say which element each is"
    meta.followSeconds = SH.FOLLOW_SECONDS
end

function SH.OnStop(_)
    SH.lastClick = nil
    SH.HideStrip(true)
end

-- Helpers --------------------------------------------------------------------------------------

-- The plain value of return i of an Invoke record made with keep, or nil (secret, absent or not kept).
function SH.Kept(rec, i)
    local d = rec and rec["r" .. i]
    if type(d) == "table" and d.isSecret == false then return d.value end
    return nil
end

-- The first return of widget:method(), when it is a plain number.
function SH.Number(widget, method)
    local exists, ok, res = GS.Call(widget, method)
    if not (exists and ok) then return nil end
    local got = res[2]
    if type(got) == "number" and not IsSecret(got) then return got end
    return nil
end

-- A related widget by method (GetParent): its name, "nil" for an anonymous one, or a plain description.
function SH.Related(widget, method)
    local exists, ok, res = GS.Call(widget, method)
    if not exists then return "absent" end
    if not ok then return "error: " .. res end
    local got = res[2]
    if type(got) == "table" and not IsSecret(got) then return GS.Read(got, "GetName") end
    return GS.Plain(got)
end

-- The screen rect of a widget in effective-scale units, or nil when any edge is not a plain number.
function SH.Rect(widget)
    local left, bottom = SH.Number(widget, "GetLeft"), SH.Number(widget, "GetBottom")
    local right, top = SH.Number(widget, "GetRight"), SH.Number(widget, "GetTop")
    if not (left and bottom and right and top) then return nil end
    local scale = SH.Number(widget, "GetEffectiveScale") or 1
    return { l = left * scale, b = bottom * scale, r = right * scale, t = top * scale }
end

-- One frame by global name: what a UI author needs to place a bar next to it.
function SH.FrameRec(name)
    local widget = _G[name]
    if type(widget) ~= "table" or IsSecret(widget) then return { exists = false } end
    local rec = { exists = true }
    rec.shown = GS.Read(widget, "IsShown")
    rec.visible = GS.Read(widget, "IsVisible")
    rec.alpha = GS.Read(widget, "GetAlpha")
    rec.effectiveAlpha = GS.Read(widget, "GetEffectiveAlpha")
    rec.scale = GS.Read(widget, "GetScale")
    rec.effectiveScale = GS.Read(widget, "GetEffectiveScale")
    rec.rect = (GS.ReadList(widget, "GetRect"))
    rec.size = (GS.ReadList(widget, "GetSize"))
    rec.strata = GS.Read(widget, "GetFrameStrata")
    rec.parent = SH.Related(widget, "GetParent")
    rec.protected = (GS.ReadList(widget, "IsProtected"))
    rec.children = GS.Read(widget, "GetNumChildren")
    local count = GS.Read(widget, "GetNumPoints")
    rec.numPoints = count
    rec.points = {}
    if type(count) == "number" then
        for i = 1, math.min(count, 4) do
            local exists, ok, res = GS.Call(widget, "GetPoint", i)
            if exists and ok then
                local relative = res[3]
                local relName = "nil"
                if type(relative) == "table" and not IsSecret(relative) then relName = GS.Read(relative, "GetName") end
                rec.points["p" .. i] = {
                    point = GS.Plain(res[2]), relativeTo = relName, relativePoint = GS.Plain(res[4]),
                    x = GS.Plain(res[5]), y = GS.Plain(res[6]),
                }
            end
        end
    end
    return rec
end

-- "overlaps" / "clear" for two rects (hidden native frames say so), or why it is unknown.
function SH.Overlap(nativeName, ourName)
    local lhs, rhs = _G[nativeName], _G[ourName]
    if type(lhs) ~= "table" or IsSecret(lhs) then return "unknown: " .. nativeName .. " absent" end
    if type(rhs) ~= "table" or IsSecret(rhs) then return "unknown: " .. ourName .. " absent" end
    local a, b = SH.Rect(lhs), SH.Rect(rhs)
    if not (a and b) then return "unknown: rect unreadable or secret" end
    local hit = a.l < b.r and b.l < a.r and a.b < b.t and b.b < a.t
    local text = hit and "overlaps" or "clear"
    if GS.Read(lhs, "IsShown") ~= true then text = text .. " (native frame not shown)" end
    return text
end

-- Every GetTotemInfo slot as one string each (the state around a click or an event).
function SH.Slots()
    local out = {}
    for slot = 1, SH.SLOT_COUNT do out["s" .. slot] = SH.B(Api("GetTotemInfo"), slot) end
    return out
end

-- Snapshot parts ---------------------------------------------------------------------------------

function SH.PartPlayer(sec)
    sec.classToken = SH.ClassToken() or "unknown"
    if sec.classToken ~= "SHAMAN" then sec.notShaman = true end
    sec.level = SH.Call(true, Api("UnitLevel"), "player")
    sec.numTotemSlots = SH.Call(true, Api("GetNumTotemSlots"))
    sec.constants = {}
    for _, name in ipairs(SH.CONSTANTS) do sec.constants[name] = GS.Plain(_G[name]) end
    local ok, text = pcall(function()
        local list = _G.SHAMAN_TOTEM_PRIORITIES
        if type(list) ~= "table" then return "absent" end
        local parts = {}
        for i = 1, 8 do
            if list[i] == nil then break end
            parts[#parts + 1] = tostring(GS.Plain(list[i]))
        end
        return table.concat(parts, ",")
    end)
    sec.priorities = ok and text or ("error: " .. ErrText(text))
end

function SH.PartSecrets(sec)
    SH.PartGenericSecrets(sec)
    sec.totemSpells = {}
    local secret = Api("C_Secrets", "ShouldTotemSpellBeSecret")
    local isPlayerSpell = Api("IsPlayerSpell")
    for _, s in ipairs(SH.resolved) do
        local ids = SH.KnownIds(s, isPlayerSpell)
        for n, id in ipairs(ids) do
            sec.totemSpells[n == 1 and s.name or (s.name .. " " .. id)] = SH.B(secret, id)
        end
    end
end

-- A duration object on a hidden StatusBar: does SetTimerDuration take it, and what does the bar read?
function SH.BarTrial(dur)
    local out = {}
    local ok, bar = pcall(GS.Bar, "shBar")
    if not ok or type(bar) == "nil" then
        out.error = "no bar: " .. ErrText(bar)
        return out
    end
    out.setTimerDuration = GS.Step(bar, "SetTimerDuration", dur)
    out.value = GS.Read(bar, "GetValue")
    GS.Hide(bar)
    return out
end

-- Everything one slot can say, into `cell`.
function SH.ReadSlot(cell, slot)
    local rec = Invoke(true, Api("GetTotemInfo"), slot)
    cell.info = SH.Stamp(rec)
    cell.brief = SH.Brief(rec)
    local have, name = SH.Kept(rec, 1), SH.Kept(rec, 2)
    cell.live = have == true
    -- live / empty / unknown: a secret answer is NOT an empty slot.
    if type(have) ~= "boolean" then
        cell.state = "unknown"
    elseif have then
        cell.state = "live"
    else
        cell.state = "empty"
    end
    if type(have) ~= "boolean" then
        cell.looksBlank = "unknown"
    elseif have == false then
        cell.looksBlank = false
    elseif type(name) == "string" then
        cell.looksBlank = name == ""
    else
        cell.looksBlank = "unknown"
    end
    cell.timeLeft = SH.Call(true, Api("GetTotemTimeLeft"), slot)
    cell.cannotDismiss = SH.Call(true, Api("GetTotemCannotDismiss"), slot)
    cell.tooltip = SH.FieldsBrief((InvokeTableKeep({ "type", "id" }, { type = true, id = true }, Api("C_TooltipInfo", "GetTotem"), slot)))
    local drec, dur = Invoke(false, Api("GetTotemDuration"), slot)
    local d = { object = SH.Brief(drec) }
    cell.duration = SH.Stamp(d)
    if drec.ok and type(dur) ~= "nil" and not IsSecret(dur) then
        for _, method in ipairs(SH.DURATION_METHODS) do d[method] = SH.Call(true, SH.Method(dur, method), dur) end
        d.sweep = SH.Sweep(dur)
        d.statusBar = SH.BarTrial(dur)
    end
end

function SH.PartTotems(sec)
    sec.slots = {}
    sec.active, sec.empty, sec.unreadable = 0, 0, 0
    for slot = 1, SH.SLOT_COUNT do
        local cell = { slot = slot }
        sec.slots["s" .. slot] = cell
        local ok, err = pcall(SH.ReadSlot, cell, slot)
        if not ok then cell.slotError = ErrText(err) end
        if cell.state == "live" then
            sec.active = sec.active + 1
        elseif cell.state == "empty" then
            sec.empty = sec.empty + 1
        else
            sec.unreadable = sec.unreadable + 1
        end
    end
end

-- GetMultiCastTotemSpells(id): the count and every return as "type/plain=id Name".
function SH.SpellsOf(id)
    local out = { count = 0, entries = {} }
    local fn = Api("GetMultiCastTotemSpells")
    if not fn then
        out.absent = true
        return out
    end
    local n, t = Pack(pcall(fn, id))
    if t[1] ~= true then
        out.err = ErrText(t[2])
        return out
    end
    out.count = n - 1
    for i = 1, math.min(out.count, MAX_RETURNS + 2) do
        local d = Desc(t[i + 1], true)
        local text = SH.DescText(d)
        if d.type == "number" and d.isSecret == false and type(d.value) == "number" then
            text = text .. " " .. SH.IdName(d.value)
        end
        out.entries[i] = text
    end
    return out
end

-- The plain spell ids GetMultiCastTotemSpells(id) answers (secret ones are dropped).
function SH.PlainSpellIds(id)
    local out = {}
    local fn = Api("GetMultiCastTotemSpells")
    if not fn then return out end
    local n, t = Pack(pcall(fn, id))
    if t[1] ~= true then return out end
    for i = 2, n do
        local got = t[i]
        if type(got) == "number" and not IsSecret(got) then out[#out + 1] = got end
    end
    return out
end

function SH.ActionState(id)
    return {
        hasAction = SH.B(Api("HasAction"), id),
        info = SH.B(Api("GetActionInfo"), id),
        texture = SH.B(Api("GetActionTexture"), id),
    }
end

function SH.PartMulticast(sec)
    sec.barIndex = SH.Call(true, Api("C_ActionBar", "GetMultiCastBarIndex"))
    sec.barIndexLegacy = SH.B(Api("GetMultiCastBarIndex"))
    sec.hasBar = SH.Call(true, Api("HasMultiCastActionBar"))
    sec.pages = {}
    for page = 1, SH.PAGES do sec.pages["p" .. page] = SH.B(Api("HasMultiCastActionPage"), page) end
    sec.spellsByAction = {}
    for id = 1, SH.PAGES * SH.PAGE_SIZE do sec.spellsByAction["a" .. id] = SH.SpellsOf(id) end
    local bar = SH.Kept(sec.barIndex, 1)
    if type(bar) ~= "number" then
        sec.barIndexNote = "unreadable: the action ids below assume bar " .. SH.BAR_FALLBACK
        bar = SH.BAR_FALLBACK
    end
    sec.actionBar = bar
    sec.actions = {}
    for set = 1, SH.PAGES do
        for slot = 1, SH.PAGE_SIZE do
            local id = (bar - 1) * SH.BAR_SIZE + (set - 1) * SH.PAGE_SIZE + slot
            local cell = SH.ActionState(id)
            cell.id = id
            sec.actions["set" .. set .. "slot" .. slot] = cell
        end
    end
    sec.nativeButtons = {}
    for i = 1, SH.PAGES * SH.PAGE_SIZE do
        local widget = _G["MultiCastActionButton" .. i]
        if type(widget) == "table" and not IsSecret(widget) then
            sec.nativeButtons["b" .. i] = { id = GS.Read(widget, "GetID"), calculateAction = GS.Read(widget, "CalculateAction") }
        end
    end
end

function SH.PartFrames(sec)
    sec.list = {}
    for _, name in ipairs(SH.FRAMES) do sec.list[name] = SH.FrameRec(name) end
    -- P5: are the tracker's buttons addressable by a global name (the forum macro `/click TotemFrameTotem1` failed)?
    sec.trackerButtons = {}
    for i = 1, SH.SLOT_COUNT do sec.trackerButtons["TotemFrameTotem" .. i] = type(_G["TotemFrameTotem" .. i]) end
    sec.ours = {}
    for _, name in ipairs(SH.OURS) do sec.ours[name] = SH.FrameRec(name) end
    sec.overlap = {}
    for _, name in ipairs(SH.OURS) do
        sec.overlap["MultiCastActionBarFrame/" .. name] = SH.Overlap("MultiCastActionBarFrame", name)
    end
end

function SH.PartMisc(sec)
    sec.combatLogRestricted = SH.Call(true, Api("C_CombatLog", "IsCombatLogRestricted"))
    sec.errSpellFailedTotems = GS.Plain(_G.ERR_SPELL_FAILED_TOTEMS)
    sec.items = { inCombat = SH.combat, note = "Classic Era item ids, unverified on Forever" }
    for _, item in ipairs(SH.ITEMS) do
        sec.items[item[1]] = { id = item[2], count = SH.Call(true, Api("C_Item", "GetItemCount"), item[2]) }
    end
end

function SH.PartApis(sec)
    for _, entry in ipairs(SH.API_LIST) do
        local label = entry[2] and (entry[1] .. "." .. entry[2]) or entry[1]
        sec[label] = Api(entry[1], entry[2]) and "present" or "absent"
    end
end

SH.PARTS = {
    { "player", SH.PartPlayer },
    { "secrets", SH.PartSecrets },
    { "totems", SH.PartTotems },
    { "multicast", SH.PartMulticast },
    { "frames", SH.PartFrames },
    { "spells", SH.PartSpells },
    { "cooldowns", SH.PartCooldowns },
    { "misc", SH.PartMisc },
    { "apis", SH.PartApis },
}

-- What could not run. Built from the parts already in `snap`.
function SH.Finish(snap, sec)
    local notRun = {}
    local function note(text)
        if #notRun < SH.NOTRUN_CAP then notRun[#notRun + 1] = text end
    end
    local totems = type(snap.totems) == "table" and snap.totems or {}
    sec.activeTotems = totems.active
    local unreadable = type(totems.unreadable) == "number" and totems.unreadable or 0
    if unreadable > 0 then
        note(unreadable .. " of " .. SH.SLOT_COUNT .. " totem slots unreadable (secret): GetTotemInfo gave no readable value there, "
            .. "so whether a totem was down in them is unknown (" .. tostring(totems.active) .. " live, " .. tostring(totems.empty)
            .. " plain empty); the duration object and the other reads on those slots are described, not judged")
    elseif totems.active == 0 then
        note("no totem was down: GetTotemInfo, GetTotemTimeLeft and GetTotemDuration were read on empty slots only; "
            .. "drop one and run /fscheck shaman again (also in combat) to read a live totem")
    end
    local known, unknown = {}, {}
    local cooldowns = type(snap.cooldowns) == "table" and snap.cooldowns or {}
    for _, s in ipairs(SH.SPELLS) do
        local entry = cooldowns[s[1]]
        if type(entry) == "table" and entry.skipped == nil then
            local ids = {}
            for k in pairs(entry) do
                local id = type(k) == "string" and string.match(k, "^s(%d+)$") or nil
                if id then ids[#ids + 1] = tonumber(id) end
            end
            table.sort(ids)
            known[#known + 1] = s[2] .. (#ids > 0 and (" (" .. table.concat(ids, ",") .. ")") or "")
        else
            unknown[#unknown + 1] = s[2]
            local level = s[5] and (" (first rank at level " .. s[5] .. ")") or ""
            if #unknown <= 12 then
                note(s[2] .. ": spell not known" .. level .. ", its cooldown, secrecy and duration reads were skipped")
            end
        end
    end
    if #unknown > 12 then note((#unknown - 12) .. " more spells not known, see spellsNotKnown") end
    sec.spellsKnown = table.concat(known, ", ")
    sec.spellsNotKnown = table.concat(unknown, ", ")
    local frames = type(snap.frames) == "table" and snap.frames.list or {}
    local bar = frames.MultiCastActionBarFrame
    if type(bar) == "table" and bar.exists == false then
        note("MultiCastActionBarFrame is absent on this client: its position and overlap with our bars were not read")
    elseif type(bar) == "table" and bar.shown ~= true then
        note("the native totem bar (MultiCastActionBarFrame) is not shown yet: its overlap with our action bars means nothing until it shows")
    end
    local multicast = type(snap.multicast) == "table" and snap.multicast or {}
    local anySpells, anyAction = false, false
    for _, cell in pairs(multicast.spellsByAction or {}) do
        if type(cell) == "table" and (cell.count or 0) > 0 then anySpells = true end
    end
    for _, cell in pairs(multicast.actions or {}) do
        if type(cell) == "table" and cell.hasAction == "boolean/plain=true" then anyAction = true end
    end
    if not anySpells then
        note("GetMultiCastTotemSpells answered no spells for any slot: no totem is learned yet, or the multicast bar is not set up")
    end
    if not anyAction then
        note("no multicast action id holds a spell yet (HasAction false on all 12), so the action based element buttons could not be checked")
    end
    for label, state in pairs(type(snap.apis) == "table" and snap.apis or {}) do
        if state == "absent" then note("api absent on this client: " .. label) end
    end
    note("manual only: /fscheck shaman setslot (SetMultiCastSpell in combat), /fscheck shaman destroy [slot] "
        .. "(DestroyTotem from addon code), /fscheck shaman buttons (secure dismiss, castsequence and Totemic Recall clicks)")
    sec.notRun = notRun
    sec.notRunCount = #notRun
end

function SH.AfterSnapshot(snap, kind)
    local checks = snap.checks
    if type(checks) ~= "table" or type(checks.notRun) ~= "table" then return end
    Say("shaman: " .. kind .. ": spells known: " .. (checks.spellsKnown ~= "" and checks.spellsKnown or "none"))
    Say("shaman: " .. kind .. ": " .. checks.notRunCount .. " checks could not run (shaman." .. kind
        .. ".checks.notRun lists them). First: " .. tostring(checks.notRun[1]))
    if checks.notRun[2] then Say("shaman: also: " .. checks.notRun[2]) end
end

-- Logs -----------------------------------------------------------------------------------------------

-- The slot argument of PLAYER_TOTEM_UPDATE when it is a plain number.
function SH.PlainSlot(...)
    if select("#", ...) < 1 then return nil end
    local got = select(1, ...)
    if type(got) == "number" and not IsSecret(got) then return got end
    return nil
end

-- A log entry that lands within SH.FOLLOW_SECONDS of the last click is copied into that click.
function SH.Follow(e, what)
    local click = SH.lastClick
    if type(click) ~= "table" or type(click.t) ~= "number" or type(e.t) ~= "number" then return end
    local dt = e.t - click.t
    if dt < 0 or dt > SH.FOLLOW_SECONDS then return end
    if #click.follow >= SH.FOLLOW_CAP then return end
    click.follow[#click.follow + 1] = { event = e.event, dt = SH.Round(dt), what = what }
end

function SH.LogTotem(event, ...)
    local e = { event = event, argCount = select("#", ...), slot = Desc((select(1, ...)), true) }
    local at = SH.PlainSlot(...)
    if at then
        e.info = SH.B(Api("GetTotemInfo"), at)
        e.timeLeft = SH.B(Api("GetTotemTimeLeft"), at)
        e.cannotDismiss = SH.B(Api("GetTotemCannotDismiss"), at)
    else
        e.all = SH.Slots()
    end
    SH.Mark(e, "totem")
    SH.Follow(e, e.info or "slot not readable")
    SH.Push("totem", e)
end

function SH.LogCast(event, unit, castGUID, spellID)
    if SH.ForeignUnit(unit, SH.PLAYER_SET) then return end
    local e = { event = event, unit = Desc(unit, true), castGUID = Desc(castGUID), spellID = Desc(spellID, true) }
    local id = PlainSpellID(unit, castGUID, spellID)
    if id then e.spellName = SH.IdName(id) end
    SH.Mark(e, "cast")
    SH.Follow(e, e.spellName or "spell not readable")
    SH.Push("cast", e)
end

function SH.LogMulticast(event)
    local e = { event = event, hasBar = SH.B(Api("HasMultiCastActionBar")) }
    local bar = _G.MultiCastActionBarFrame
    if type(bar) == "table" and not IsSecret(bar) then
        e.barShown = GS.Read(bar, "IsShown")
    else
        e.barShown = "absent"
    end
    SH.Push("multicast", SH.Mark(e, "multicast"))
end

SH.HANDLERS = {
    PLAYER_TOTEM_UPDATE = function(event, ...) SH.LogTotem(event, ...) end,
    UPDATE_MULTI_CAST_ACTIONBAR = function(event) SH.LogMulticast(event) end,
    UNIT_SPELLCAST_START = function(event, ...) SH.LogCast(event, ...) end,
    UNIT_SPELLCAST_SUCCEEDED = function(event, ...) SH.LogCast(event, ...) end,
    UNIT_SPELLCAST_FAILED = function(event, ...) SH.LogCast(event, ...) end,
    UNIT_SPELLCAST_INTERRUPTED = function(event, ...) SH.LogCast(event, ...) end,
}

-- The explicit protected-risk calls (typed by Parker, never automatic) ---------------------------------

-- Appends one run to shaman.<name>.runs (bounded) and returns it.
function SH.NewRun(name)
    local rec = SH.Rec()
    if type(rec[name]) ~= "table" then rec[name] = { runs = {} } end
    local runs = rec[name].runs
    local run = { inCombat = LockedDown(false), when = SafeDate() }
    runs[#runs + 1] = run
    while #runs > SH.RUN_CAP do table.remove(runs, 1) end
    SH.combat = run.inCombat
    return run
end

-- The action id Blizzard's own multicast button for `slot` reports (MultiCastActionBarFrame passes
-- actionButton:CalculateAction() to SetMultiCastSpell), or nil when the button or the answer is not usable.
function SH.NativeActionId(slot)
    local widget = _G["MultiCastActionButton" .. slot]
    if type(widget) ~= "table" or IsSecret(widget) then return nil end
    local got = SH.Number(widget, "CalculateAction")
    if type(got) == "number" and got >= 1 and got == math.floor(got) then return got end
    return nil
end

-- P1. SetMultiCastSpell from addon code. The chat line is printed BEFORE the call: if the client blocks
-- it, ADDON_ACTION_BLOCKED goes through the global error handler, which pcall cannot catch.
function SH.SetSlot()
    state.canTest = Invoke(false, Api("issecretvalue"), 0).ok == true
    local run = SH.NewRun("setslot")
    local fn = Api("SetMultiCastSpell")
    if not fn then
        run.skipped = "SetMultiCastSpell is absent on this client"
        Say("shaman setslot: " .. run.skipped)
        return
    end
    local bar = SH.Kept(Invoke(true, Api("C_ActionBar", "GetMultiCastBarIndex")), 1)
    if type(bar) ~= "number" then
        run.barIndexFallback = SH.BAR_FALLBACK
        bar = SH.BAR_FALLBACK
    end
    local slot, ids
    for _, candidate in ipairs(SH.SLOT_PICK_ORDER) do
        local list = SH.PlainSpellIds(candidate)
        if #list > 0 then
            slot, ids = candidate, list
            break
        end
    end
    if not slot then
        run.skipped = "no totem spells: GetMultiCastTotemSpells answered nothing readable for any slot (no totem learned yet, or the bar is not set up)"
        Say("shaman setslot: " .. run.skipped)
        return
    end
    local computed = (bar - 1) * SH.BAR_SIZE + slot
    local native = SH.NativeActionId(slot)
    local actionId = native or computed
    run.slot, run.actionId = slot, actionId
    if native then
        run.actionSource = "native CalculateAction"
        run.computedActionId = computed
    else
        run.actionSource = "computed (bar-1)*12+slot"
    end
    run.before = SH.ActionState(actionId)
    -- The previous pick is only trusted when the slot holds a plain spell: an empty slot, a macro or a secret
    -- answer leaves nothing to put back.
    local infoRec = Invoke(true, Api("GetActionInfo"), actionId)
    local previousType, previous = SH.Kept(infoRec, 1), SH.Kept(infoRec, 2)
    if type(previousType) == "string" then run.previousType = previousType end
    if not (previousType == "spell" and type(previous) == "number") then previous = nil end
    local pick = ids[1]
    for _, id in ipairs(ids) do
        if id ~= previous then
            pick = id
            break
        end
    end
    run.spellId, run.previousSpellId = pick, previous
    if previous ~= nil and pick == previous then run.noop = true end
    local pickName = SH.IdName(pick)
    Say("shaman setslot: calling SetMultiCastSpell(" .. actionId .. ", " .. pick .. ") now, in combat: "
        .. tostring(run.inCombat) .. " (action id from " .. run.actionSource .. "). "
        .. "If the client prints ADDON_ACTION_BLOCKED, that is the answer. /reload to save.")
    if run.noop then
        Say("shaman setslot: the pick (" .. pickName .. ") is the slot's current pick (only one totem is known for it), "
            .. "so this call is a no-op for the bar: it only shows whether the call is blocked")
    end
    run.call = (Invoke(true, fn, actionId, pick))
    run.after = SH.ActionState(actionId)
    local afterRec = Invoke(true, Api("GetActionInfo"), actionId)
    local nowType, now = SH.Kept(afterRec, 1), SH.Kept(afterRec, 2)
    local nowPlain = nowType == "spell" and type(now) == "number"
    if nowPlain and previous then
        run.changed = now ~= previous
    else
        run.changed = "unknown"
    end
    local note
    if run.changed == true then
        run.restore = { call = (Invoke(true, fn, actionId, previous)) }
        run.restore.after = SH.ActionState(actionId)
    elseif run.noop then
        run.restore = { skipped = "no-op: the pick was the slot's current pick, nothing to restore" }
    elseif previous == nil then
        -- There is no plain previous spell to put back.
        if nowPlain and now == pick then
            run.restore = { skipped = "the slot held no plain spell before (empty, another type or unreadable), so there is nothing to restore",
                leftChanged = true }
            note = "slot left changed to " .. pickName .. " (it held no plain spell before); set it back by hand"
        else
            run.restore = { skipped = "the slot held no plain spell before, and its state after the call could not be read" }
            note = "the slot's state after the call is unreadable and it held no plain spell before; check the bar and set it back by hand if it changed"
        end
    elseif run.changed == "unknown" then
        run.restore = { skipped = "the slot could not be read after the call, so a restore was not attempted" }
        note = "the slot is unreadable after the call; if it changed, set it back to " .. SH.IdName(previous) .. " by hand"
    else
        run.restore = { skipped = "the pick did not visibly change (the call was probably blocked), nothing to restore" }
    end
    Say("shaman setslot: call " .. (run.call.ok and "returned" or ("failed: " .. tostring(run.call.err)))
        .. "; slot changed: " .. tostring(run.changed) .. ". Record: shaman.setslot.runs[" .. #SH.Rec().setslot.runs .. "]")
    if note then Say("shaman setslot: " .. note) end
end

-- The first slot GetTotemInfo says holds a live totem, or nil.
function SH.LiveSlot()
    for slot = 1, SH.SLOT_COUNT do
        if KeptBool((Invoke(true, Api("GetTotemInfo"), slot))) == true then return slot end
    end
    return nil
end

-- P11. DestroyTotem from addon code (the secure route is the totem button row).
function SH.Destroy(arg)
    state.canTest = Invoke(false, Api("issecretvalue"), 0).ok == true
    local slot = tonumber(arg)
    if arg ~= nil and not (slot and slot >= 1 and slot <= SH.SLOT_COUNT and slot == math.floor(slot)) then
        Say("shaman destroy: the slot must be 1 to " .. SH.SLOT_COUNT)
        return
    end
    local run = SH.NewRun("destroy")
    local fn = Api("DestroyTotem")
    if not fn then
        run.skipped = "DestroyTotem is absent on this client"
        Say("shaman destroy: " .. run.skipped)
        return
    end
    if not slot then
        slot = SH.LiveSlot()
        if not slot then
            slot = 2
            run.slotNote = "no live totem seen: slot 2 (earth per the constants)"
        end
    end
    run.slot = slot
    run.before = SH.B(Api("GetTotemInfo"), slot)
    Say("shaman destroy: calling DestroyTotem(" .. slot .. ") from addon code now, in combat: " .. tostring(run.inCombat)
        .. ". If the client prints ADDON_ACTION_BLOCKED, that is the answer. /reload to save.")
    run.call = (Invoke(true, fn, slot))
    run.after = SH.B(Api("GetTotemInfo"), slot)
    Say("shaman destroy: call " .. (run.call.ok and "returned" or ("failed: " .. tostring(run.call.err)))
        .. ". Record: shaman.destroy.runs[" .. #SH.Rec().destroy.runs .. "]")
end

-- The temporary totem button row: secure buttons, out of combat only ------------------------------------------

-- True when the player knows the spell: the name resolves to an id and nothing refuses it.
function SH.IsKnown(name)
    local id = KnownRankID(name)
    return id ~= nil and KeptBool((Invoke(true, Api("IsPlayerSpell"), id))) ~= false
end

function SH.KnownTotems()
    local out = {}
    for _, t in ipairs(SH.TOTEMS) do
        if SH.IsKnown(t[2]) then out[#out + 1] = t[2] end
    end
    return out
end

-- Click 1: dismiss. Left = slot 1, right = slot 2, shift-left = slot 3, shift-right = slot 4, through the
-- secure `destroytotem` action (the slot is read from the modified attribute `totem-slot`).
function SH.SyncDismiss(button, entry)
    for _, spec in ipairs({ { "", "1", 1 }, { "", "2", 2 }, { "shift-", "1", 3 }, { "shift-", "2", 4 } }) do
        button:SetAttribute(spec[1] .. "type" .. spec[2], "destroytotem")
        button:SetAttribute(spec[1] .. "totem-slot" .. spec[2], spec[3])
    end
    entry.label = "dismiss: L1 R2 shift-L3 shift-R4"
    entry.attributes = "type1/type2/shift-type1/shift-type2 = destroytotem, totem-slot = 1/2/3/4"
end

-- Click 2: castsequence through two known totems (the same one twice when only one is known).
function SH.SyncCastSequence(button, entry)
    local names = SH.KnownTotems()
    if #names == 0 then
        button:SetAttribute("type", nil)
        button:SetAttribute("macrotext", nil)
        entry.skipped = "no totem known (the first Earth totem comes at level 4)"
        entry.label = "castsequence: (no totem known)"
        return
    end
    local macro = "/castsequence reset=combat/15 " .. names[1] .. ", " .. (names[2] or names[1])
    button:SetAttribute("type", "macro")
    button:SetAttribute("macrotext", macro)
    entry.macrotext = macro
    entry.label = "castsequence: " .. names[1] .. " > " .. (names[2] or names[1])
end

-- Click 3: Totemic Recall.
function SH.SyncRecall(button, entry)
    if not SH.IsKnown("Totemic Recall") then
        button:SetAttribute("type", nil)
        button:SetAttribute("spell", nil)
        entry.skipped = "Totemic Recall not known (level 20)"
        entry.label = "recall: (not known)"
        return
    end
    button:SetAttribute("type", "spell")
    button:SetAttribute("spell", "Totemic Recall")
    entry.spell = "Totemic Recall"
    entry.label = "recall: Totemic Recall"
end

SH.BUTTONS = {
    { key = "dismiss", sync = SH.SyncDismiss },
    { key = "castsequence", sync = SH.SyncCastSequence },
    { key = "recall", sync = SH.SyncRecall },
}

function SH.PreClick(index, mouse, down)
    if not SH.live then return end
    local e = { event = "PreClick", button = SH.BUTTONS[index].key, mouse = Desc(mouse, true), down = Desc(down, true),
        follow = {}, totemsBefore = SH.Slots() }
    SH.lastClick = SH.Mark(e, "click")
    SH.Push("click", e)
end

function SH.PostClick(index)
    if not SH.live then return end
    local click = SH.lastClick
    if type(click) == "table" then
        click.post = SH.Mark({ event = "PostClick", totems = SH.Slots() }, "clickPost")
    end
end

-- Builds the host and the buttons once (a named secure frame cannot be destroyed). Out of combat only.
function SH.BuildStrip()
    if SH.strip then return SH.strip end
    -- A frame an earlier, half finished build already made is reused (a named frame cannot be destroyed).
    local host = _G[SH.STRIP_NAME]
    if type(host) ~= "table" then
        host = CreateFrame("Frame", SH.STRIP_NAME, UIParent)
        host:SetSize(224, 22 + #SH.BUTTONS * 30)
        -- Centre y -190: the strip spans -134 to -246, clear of our target cast bar (Layout.lua tcast, -286 to -308).
        host:SetPoint("CENTER", UIParent, "CENTER", 0, SH.STRIP_Y)
        host:SetFrameStrata("DIALOG")
        local ground = host:CreateTexture(nil, "BACKGROUND")
        ground:SetAllPoints(host)
        ground:SetColorTexture(0.1, 0.02, 0.18, 0.85)
        local title = host:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        title:SetPoint("TOP", host, "TOP", 0, -5)
        title:SetText("SHAMAN TOTEM BUTTONS (temporary)")
    end
    local strip = { host = host, buttons = {} }
    for i = 1, #SH.BUTTONS do
        local name = SH.BUTTON_PREFIX .. i
        local button = _G[name]
        if type(button) ~= "table" then
            button = CreateFrame("Button", name, host, "SecureActionButtonTemplate")
            button:SetSize(208, 24)
            button:SetPoint("TOP", host, "TOP", 0, -20 - (i - 1) * 30)
            local face = button:CreateTexture(nil, "BACKGROUND")
            face:SetAllPoints(button)
            face:SetColorTexture(0.35, 0.1, 0.5, 0.9)
            button.fsText = button:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            button.fsText:SetPoint("CENTER", button, "CENTER", 0, 0)
            button:RegisterForClicks("AnyUp")
            button:HookScript("PreClick", function(_, mouse, down) pcall(SH.PreClick, i, mouse, down) end)
            button:HookScript("PostClick", function() pcall(SH.PostClick, i) end)
        end
        strip.buttons[i] = button
    end
    SH.strip = strip
    return strip
end

-- Writes the protected attributes and shows the strip. Called from SH.ButtonsOn, which has refused combat.
function SH.SyncStrip()
    local strip = SH.BuildStrip()
    local rec = { shown = true, buttons = {} }
    for i, def in ipairs(SH.BUTTONS) do
        local entry = {}
        rec.buttons[def.key] = entry
        local ok, err = pcall(def.sync, strip.buttons[i], entry)
        if not ok then entry.error = ErrText(err) end
        pcall(function() strip.buttons[i].fsText:SetText(entry.label or def.key) end)
    end
    SH.CancelPendingHide()
    for i = 1, #SH.BUTTONS do pcall(strip.buttons[i].EnableMouse, strip.buttons[i], true) end
    strip.host:SetAlpha(1)
    strip.host:Show()
    SH.stripShown = true
    SH.Rec().strip = rec
end

function SH.ButtonsOn()
    if LockedDown(true) then
        Say("shaman buttons: leave combat first (the strip is secure buttons: not built, changed or shown in combat)")
        return
    end
    -- Never replaces a saved record: after `off` or the timeout the logging is re-armed over what is saved.
    if not SH.live then SH.Start(true) end
    local ok, err = pcall(SH.SyncStrip)
    if not ok then
        pcall(function() SH.Rec().strip = { error = ErrText(err) } end)
        Say("shaman buttons: could not build the strip: " .. ErrText(err))
        return
    end
    Say("shaman: TOTEM BUTTONS (temporary) are below screen centre: dismiss (left slot 1, right slot 2, shift-left 3, shift-right 4), "
        .. "castsequence, recall. Click each out of combat and in combat. Clicks are logged in shaman.logs.click. "
        .. "/fscheck shaman buttons off hides it (out of combat)")
end

-- The real hide: host hidden and the secure buttons' mouse off. Out of combat only (both are protected in combat);
-- fails closed, so a combat check that cannot be read counts as combat. Returns true when the strip is hidden.
function SH.RealHide()
    if LockedDown(true) then return false end
    local strip = SH.strip
    if strip then
        pcall(strip.host.Hide, strip.host)
        for i = 1, #strip.buttons do pcall(strip.buttons[i].EnableMouse, strip.buttons[i], false) end
    end
    SH.stripShown = false
    SH.CancelPendingHide()
    local saved = SH.Saved()
    local rec = saved and type(saved.strip) == "table" and saved.strip or nil
    if rec then
        rec.shown = false
        rec.faded = nil
        rec.hidePending = nil
    end
    return true
end

-- PLAYER_REGEN_ENABLED while a hide is queued: finish it (still in combat by the check: keep waiting).
function SH.OnRegen()
    if not SH.hidePending then
        CallOn(SH.regenFrame, "UnregisterEvent", "PLAYER_REGEN_ENABLED")
        return
    end
    SH.RealHide()
end

function SH.CancelPendingHide()
    SH.hidePending = false
    CallOn(SH.regenFrame, "UnregisterEvent", "PLAYER_REGEN_ENABLED")
end

-- Queues the real hide for the end of combat. Own plain frame: the check's event frame is unregistered by stop.
-- Returns false when the wait could not be set up.
function SH.QueueHide()
    if not SH.regenFrame then
        local made, frame = pcall(CreateFrame, "Frame")
        if not made or type(frame) == "nil" then return false end
        -- pcall'd: nothing is ever thrown into the session from a script handler.
        if not pcall(frame.SetScript, frame, "OnEvent", function() pcall(SH.OnRegen) end) then return false end
        SH.regenFrame = frame
    end
    SH.hidePending = true
    if pcall(SH.regenFrame.RegisterEvent, SH.regenFrame, "PLAYER_REGEN_ENABLED") then return true end
    SH.hidePending = false
    return false
end

-- Hides the strip out of combat. In combat nothing secure may change, so it is only faded (alpha 0): the buttons
-- stay clickable, invisible, until combat ends, and the real hide is queued for PLAYER_REGEN_ENABLED.
-- Said even when `quiet` (stop, timeout, reset): invisible clickable buttons must never be a surprise.
function SH.HideStrip(quiet)
    local strip = SH.strip
    if not strip then return end
    if LockedDown(true) then
        if not SH.stripShown then return end
        pcall(strip.host.SetAlpha, strip.host, 0)
        local queued = SH.QueueHide()
        local saved = SH.Saved()
        local rec = saved and type(saved.strip) == "table" and saved.strip or nil
        if rec then
            rec.faded = true
            rec.hidePending = queued or nil
        end
        Say("shaman buttons off: in combat the strip is only faded (alpha 0). The buttons stay clickable, invisible, until combat ends; "
            .. (queued and "then they hide by themselves."
                or "then run /fscheck shaman buttons off to hide them (the automatic hide could not be set up)."))
        return
    end
    SH.RealHide()
    if not quiet then Say("shaman buttons off: strip hidden") end
end

function SH.ButtonsOff()
    if not SH.strip then
        Say("shaman buttons off: there is no strip")
        return
    end
    if not SH.stripShown then
        Say("shaman buttons off: the strip is already hidden")
        return
    end
    SH.HideStrip(false)
end

-------------------------------------------------------------------------------
-- /fscheck hot: can an engine AuraContainer per party row show the player's own Renew?
-------------------------------------------------------------------------------
-- `/fscheck hot` (out of combat only) builds one CustomAuraContainerTemplate per token that
-- exists (player, party1..party4) and lays them out as a labelled debug strip above screen
-- centre. Each container has the three shapes a party-row HoT timer could use:
--   slot   AddAuraSlot "HELPFUL|PLAYER", candidateFilters.includeSpellIDs = the Renew rank ids
--          (the shape CombatHud uses for target DoTs): one button, the box on the left;
--   group  AddAuraGroup "HELPFUL|PLAYER", candidateFilters.maxDuration = 60 (ID free fallback;
--          also shows Power Word: Shield and any other of your short buffs): up to 4 buttons;
--   bar    a second slot "renewbar" (same filter and ids) under the boxes, labelled "bar": the
--          shape Parker chose for party rows, a HoT TIMER BAR. Its button gets, each step in its
--          own pcall and each result recorded in tokens.<t>.barSteps: a 160 x 4 StatusBar on a dark
--          track, fill reversed, handed to SetDurationBar (direction RemainingTime, interpolation
--          Immediate); a FontString handed to SetDurationText with a bare-number format (a numeric
--          rule formatter: one breakpoint, step 1, round up, "%d", format string "{}") and a Step
--          colour curve on RemainingDuration (amber from 0, green from 3.001; if the custom options
--          error, SetDurationText is retried with defaults and barSteps says which one worked); and
--          an amber texture riding the bar's fill, hidden, handed to AddPandemicRegion. barSteps.api
--          also records which of those methods, enums and factories exist on this client.
-- The first two shapes draw the engine's cooldown sweep and duration text. The bar shape proves
-- the engine can drive a StatusBar timer, a custom number and a pandemic overlay on a party row.
-- A button that is up while Renew is on that unit shows a ticking number: that part Parker judges
-- by eye, never read in code. For the bar he judges four things: (1) the bar drains from the left
-- toward the number, (2) the number counts whole seconds with no "s", (3) the number turns amber
-- at 3 seconds, (4) whether an amber overlay appears on the bar near the end (pandemic). The
-- samples also count how often the bar slot and the pandemic texture read shown (secret = unk).
-- Then it samples every container once a second for 120s, in and out of combat, with plain
-- widget queries only (GetNumChildren, GetChildren + IsShown, the slot's IsShown, the group's
-- GetAuraGroupFrameCount, InCombatLockdown). It never reads an aura, a duration or a text.
-- IN COMBAT IsShown IS EXPECTED TO BE SECRET: the engine's buttons are shown through
-- SetShown(secretwrap(...)) (Blizzard_CustomAuraButton.lua:577), so every in-combat read comes
-- back secret and counts as `unknown` (the `unk=` field, `unknown` in the stats, `unk` in the
-- summary), never as hidden. An unknown sample feeds none of withShown, transitions,
-- lostInCombat or gainedInCombat, and the last KNOWN shown count is kept across it, so a known,
-- unknown, known run is not a transition. So the in-combat samples only prove whether
-- visibility is READABLE at all; whether the countdown renders and ticks in combat is judged by
-- eye from the on-screen strip. Out of combat the counts are real.
-- `ch=` (GetNumChildren) and `grp=` (GetAuraGroupFrameCount) count OWNED frames, not visible
-- ones: FrameCreationBatchSize = 10 pre-creates 10 group buttons at once (so initCalls.group is
-- 10 in game, not 4). Only `shown` and `unk` are signal.
-- Nothing is built, enabled, shown or hidden in combat (those calls are protected there);
-- `/fscheck hot off` in combat only sets alpha 0 on the containers and hides the plain holder
-- (the unprotected frame), then says to repeat it later.
-- Source for the option names: Blizzard_CustomAuraContainer.lua (ValidateCandidateFilters:
-- includeSpellIDs is a set and "only permitted for helpful buffs on assistable units";
-- maxDuration is derived from the aura's MAX duration and hides permanent auras).
-- Results: ForeverSTUwaveDB.fscheck.hot (see HP.NewRow for the shape).

local HP = {}

HP.TOKENS = { "player", "party1", "party2", "party3", "party4" }
HP.NAME = "Renew"
-- Renew rank ids (an aura reports the rank id that was cast), the same list as ElvUI's TBC and
-- Wrath Renew filters (Game/TBC/Filters/Filters.lua:795, Game/Wrath/Filters/Filters.lua:992).
-- The id the NAME resolves to today is added at run time, as CombatHud.IdSet does, which
-- covers SoD and Forever ids that list does not.
HP.RANKS = { 139, 6074, 6075, 6076, 6077, 6078, 10927, 10928, 10929, 25315, 25221, 25222 }
HP.FILTER = "HELPFUL|PLAYER"
HP.SLOT_KEY = "renew"
HP.BAR_KEY = "renewbar"
HP.GROUP_KEY = "short"
HP.MAX_DURATION = 60
HP.GROUP_FRAMES = 4
HP.PERIOD = 1
HP.SECONDS = 120
HP.BOX = 30
HP.GAP = 6
HP.COL_W = 170
HP.TOP = 300
HP.BG = { 0.18, 0.05, 0.3, 0.6 }
-- The timer bar shape. The bar sits in a strip box under the two boxes; the number rides its right end.
HP.BAR_W = 160
HP.BAR_H = 4
HP.BAR_LABEL_H = 12
HP.BAR_BOX_H = 20
HP.BAR_GREEN = { 0.22, 1, 0.08 }          -- the HUD green (Theme.COLOR_HEAL)
HP.BAR_AMBER = { 1, 0.714, 0.282 }        -- the HUD amber
HP.BAR_TRACK = { 0.04, 0.02, 0.1, 1 }
HP.BAR_PANDEMIC = { 1, 0.714, 0.282, 0.6 }
HP.AMBER_UNTIL = 3.001                    -- seconds: amber below this, green from it
HP.NS = select(2, ...)                    -- the addon table, for FS.Theme (nil in a bare load)

HP.run = 0
HP.cache = {}   -- token -> { holder, slotBox, groupBox, barBox, barLabel, container, slot, barSlot, panTex, barRec } (frames are never destroyed)
HP.live = nil   -- the current run: { run, rec, rows, tick, sampling }

function HP.Fmt(v) return tostring(GS.Plain(v)) end

-- The shape of one token's result.
function HP.NewRow(exists)
    return {
        exists = exists,
        steps = {},
        initCalls = { slot = 0, group = 0, bar = 0 },
        initSteps = {},
        samples = {},
        stats = {
            ooc = { samples = 0, withShown = 0, maxShown = 0, slotShown = 0, slotSecret = 0, unknown = 0,
                barShown = 0, barSecret = 0, panShown = 0, panSecret = 0 },
            combat = { samples = 0, withShown = 0, maxShown = 0, slotShown = 0, slotSecret = 0, unknown = 0,
                barShown = 0, barSecret = 0, panShown = 0, panSecret = 0 },
            transitions = 0, lostInCombat = 0, gainedInCombat = 0,
        },
    }
end

function HP.TokenExists(token)
    local fn = _G.UnitExists
    if type(fn) ~= "function" then return false end
    local ok, v = pcall(fn, token)
    return ok and not IsSecret(v) and v == true
end

-- The Renew id set: the rank list plus the id the name resolves to today.
function HP.IdSet(meta)
    local set, list = {}, {}
    local function add(id)
        if type(id) == "number" and not IsSecret(id) and not set[id] then
            set[id] = true
            list[#list + 1] = id
        end
    end
    for _, id in ipairs(HP.RANKS) do add(id) end
    local known = KnownRankID(HP.NAME)
    meta.runtimeRank = known or "none"
    add(known)
    meta.idCount = #list
    meta.ids = table.concat(list, ",")
    meta.idsSource = "ElvUI TBC/Wrath Renew filter lists plus the runtime name"
    return set
end

-- First thing in every initializeFrame, before the button turns restricted: the tiles take no
-- clicks and show no tooltips while Parker is fighting.
function HP.Preamble(button)
    Quiet(button, "SetMouseMotionEnabled", false)
    Quiet(button, "SetMouseClickEnabled", false)
    Quiet(button, "SetHideTooltipInCombat", true)
end

-- initializeFrame for all three shapes (slot, group, bar): the same pieces Plater's button has,
-- each under its own pcall, the first result per step recorded. Looks the row up at call time, so
-- a re-run reuses the container (and these closures) without a stale record.
function HP.Init(token, kind)
    return function(button)
        HP.Preamble(button)
        local live = HP.live
        local row = live and live.rows[token]
        if row then row.initCalls[kind] = row.initCalls[kind] + 1 end
        local function S(name, fn)
            local ok, err = pcall(fn)
            local key = kind .. "." .. name
            if row and row.initSteps[key] == nil then row.initSteps[key] = ok and "ok" or ErrText(err) end
        end
        local cache = HP.cache[token]
        if kind == "slot" and cache then S("seat", function() button:SetAllPoints(cache.slotBox) end) end
        S("icon", function()
            local icon = button:CreateTexture(nil, "ARTWORK")
            icon:SetAllPoints(button)
            button:SetIcon(icon)
        end)
        local cooldown
        S("cooldown", function()
            cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
            Quiet(cooldown, "EnableMouse", false)
            Quiet(cooldown, "EnableMouseMotion", false)
            cooldown:SetAllPoints(button)
            Quiet(cooldown, "SetHideCountdownNumbers", true)
            button:SetDurationCooldown(cooldown)
        end)
        S("durationText", function()
            local fs = (cooldown or button):CreateFontString(nil, "OVERLAY", "NumberFontNormal")
            fs:SetPoint("CENTER")
            button:SetDurationText(fs, {})
        end)
    end
end

-- A plain number from Enum[enumName][field], nil when the enum or the field is absent.
function HP.EnumValue(enumName, field)
    local E = _G.Enum
    if type(E) ~= "table" then return nil end
    local okT, t = pcall(function() return E[enumName] end)
    if not okT or type(t) ~= "table" then return nil end
    local okV, v = pcall(function() return t[field] end)
    if okV and type(v) == "number" and not IsSecret(v) then return v end
    return nil
end

-- What this client has: method types on the button, the enums (with the one value used) and the
-- two factories. Plain type names and numbers only.
function HP.RecordApi(button, rec)
    local api = {}
    rec.api = api
    for _, name in ipairs({ "SetDurationBar", "AddPandemicRegion", "SetDurationText" }) do
        local ok, t = pcall(function() return type(button[name]) end)
        api[name] = ok and t or "error"
    end
    local E = _G.Enum
    for _, e in ipairs({ { "StatusBarTimerDirection", "RemainingTime" }, { "StatusBarInterpolation", "Immediate" },
                         { "DurationTextBindingProperty", "RemainingDuration" }, { "NumericRuleFormatRounding", "Up" },
                         { "LuaCurveType", "Step" } }) do
        local okT, t = pcall(function() return type(E) == "table" and E[e[1]] or nil end)
        api["Enum." .. e[1]] = okT and type(t) or "error"
        api["Enum." .. e[1] .. "." .. e[2]] = GS.Plain(HP.EnumValue(e[1], e[2]))
    end
    api["C_StringUtil.CreateNumericRuleFormatter"] = type(Api("C_StringUtil", "CreateNumericRuleFormatter"))
    api["C_CurveUtil.CreateColorCurve"] = type(Api("C_CurveUtil", "CreateColorCurve"))
    api.CreateColor = type(_G.CreateColor)
end

local function Need(value, what)
    if value == nil then error("absent: " .. what, 0) end
    return value
end

-- The custom duration text options: a bare number (one numeric rule breakpoint, whole seconds
-- rounded up, "%d") coloured by a Step curve on the remaining duration, amber until 3.001 s
-- and green after. Builds only; raises on the first piece this client lacks.
function HP.TextOptions()
    local property = Need(HP.EnumValue("DurationTextBindingProperty", "RemainingDuration"), "Enum.DurationTextBindingProperty.RemainingDuration")
    local roundUp = Need(HP.EnumValue("NumericRuleFormatRounding", "Up"), "Enum.NumericRuleFormatRounding.Up")
    local step = Need(HP.EnumValue("LuaCurveType", "Step"), "Enum.LuaCurveType.Step")
    local makeFormatter = Need(Api("C_StringUtil", "CreateNumericRuleFormatter"), "C_StringUtil.CreateNumericRuleFormatter")
    local makeCurve = Need(Api("C_CurveUtil", "CreateColorCurve"), "C_CurveUtil.CreateColorCurve")
    local color = Need(Api("CreateColor"), "CreateColor")
    local formatter = makeFormatter()
    formatter:AddBreakpoint({ threshold = 0, step = 1, rounding = roundUp, format = "%d" })
    local curve = makeCurve()
    curve:SetType(step)
    curve:AddPoint(0, color(HP.BAR_AMBER[1], HP.BAR_AMBER[2], HP.BAR_AMBER[3], 1))
    curve:AddPoint(HP.AMBER_UNTIL, color(HP.BAR_GREEN[1], HP.BAR_GREEN[2], HP.BAR_GREEN[3], 1))
    return {
        textFormat = { formatString = "{}", components = { { property = property, formatter = formatter } } },
        textColor = { curve = curve, property = property },
    }
end

-- initializeFrame for the bar slot: the timer bar shape, every step under its own pcall with the
-- first result recorded in the token's barSteps (kept on the cache so a re-run, which reuses the
-- container and never calls this again, still has it). Nothing here reads a value back.
function HP.InitBar(token)
    return function(button)
        HP.Preamble(button)
        local c = HP.cache[token]
        if c == nil then c = {}; HP.cache[token] = c end
        local rec = c.barRec
        if rec == nil then rec = {}; c.barRec = rec end
        local live = HP.live
        local row = live and live.rows[token]
        if row then
            row.initCalls.bar = row.initCalls.bar + 1
            row.barSteps = rec
        end
        local function Put(name, text) if rec[name] == nil then rec[name] = text end end
        local function S(name, fn)
            local ok, err = pcall(fn)
            Put(name, ok and "ok" or ErrText(err))
            return ok
        end

        if rec.api == nil then
            local ok, err = pcall(HP.RecordApi, button, rec)
            if not ok then rec.api = { recordError = ErrText(err) } end
        end

        if c.barBox then
            S("seat", function()
                button:SetAllPoints(c.barBox)
                -- Above the strip box's tinted texture, whatever level the engine gave the button.
                local lvl = c.barBox:GetFrameLevel()
                if type(lvl) == "number" and not IsSecret(lvl) then button:SetFrameLevel(lvl + 3) end
            end)
        end

        -- 2. the bar: flat green fill, reversed, on a dark track, the engine drives it.
        local bar
        S("bar", function()
            bar = CreateFrame("StatusBar", nil, button)
            bar:SetSize(HP.BAR_W, HP.BAR_H)
            bar:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 1, 2)
            Quiet(bar, "EnableMouse", false)
        end)
        if bar then
            local theme = type(HP.NS) == "table" and HP.NS.Theme or nil
            local flat = type(theme) == "table" and theme.FLAT_TEXTURE or "Interface\\Buttons\\WHITE8X8"
            S("barTexture", function() bar:SetStatusBarTexture(flat) end)
            S("barColor", function() bar:SetStatusBarColor(HP.BAR_GREEN[1], HP.BAR_GREEN[2], HP.BAR_GREEN[3], 1) end)
            Put("barReverse", GS.Step(bar, "SetReverseFill", true))
            S("barTrack", function()
                local track = bar:CreateTexture(nil, "BACKGROUND")
                track:SetAllPoints(bar)
                track:SetColorTexture(HP.BAR_TRACK[1], HP.BAR_TRACK[2], HP.BAR_TRACK[3], HP.BAR_TRACK[4])
            end)
            local options = {}
            local direction = HP.EnumValue("StatusBarTimerDirection", "RemainingTime")
            local interpolation = HP.EnumValue("StatusBarInterpolation", "Immediate")
            if direction ~= nil then options.direction = direction end
            if interpolation ~= nil then options.interpolation = interpolation end
            Put("durationBarOptions", (direction ~= nil and interpolation ~= nil) and "RemainingTime+Immediate" or "defaults (enum absent)")
            Put("setDurationBar", GS.Step(button, "SetDurationBar", bar, options))
        else
            for _, name in ipairs({ "barTexture", "barColor", "barReverse", "barTrack", "setDurationBar" }) do
                Put(name, "skipped: no bar")
            end
        end

        -- 3. the number: at the bar's right end, bare whole seconds, amber at 3.
        local fs
        S("text", function()
            fs = button:CreateFontString(nil, "OVERLAY", "NumberFontNormal")
            if bar then
                fs:SetPoint("BOTTOMRIGHT", bar, "TOPRIGHT", 0, 1)
            else
                fs:SetPoint("RIGHT", button, "RIGHT", -2, 0)
            end
        end)
        if fs then
            local theme = type(HP.NS) == "table" and HP.NS.Theme or nil
            local applyMono = type(theme) == "table" and theme.ApplyMono or nil
            if type(applyMono) == "function" then
                S("textFont", function() applyMono(fs, 12) end)
            else
                Put("textFont", "template font (FS.Theme.ApplyMono absent)")
            end
            local okOpts, opts = pcall(HP.TextOptions)
            local custom
            if okOpts then
                custom = GS.Step(button, "SetDurationText", fs, opts)
            else
                custom = ErrText(opts)
            end
            Put("textCustom", custom)
            if custom == "ok" then
                Put("textMode", "custom")
            else
                -- The custom options errored: retry with the engine defaults and say which worked.
                local fallback = GS.Step(button, "SetDurationText", fs, {})
                Put("textDefault", fallback)
                Put("textMode", fallback == "ok" and "default" or "none")
            end
        else
            Put("textCustom", "skipped: no font string")
            Put("textMode", "none")
        end

        -- 4. pandemic: an amber overlay on the bar's fill, hidden until the engine shows it.
        local pan
        if bar then
            S("pandemicTexture", function()
                pan = bar:CreateTexture(nil, "OVERLAY")
                pan:SetColorTexture(HP.BAR_PANDEMIC[1], HP.BAR_PANDEMIC[2], HP.BAR_PANDEMIC[3], HP.BAR_PANDEMIC[4])
                local fill = bar:GetStatusBarTexture()
                pan:SetPoint("TOPLEFT", fill, "TOPLEFT", 0, 0)
                pan:SetPoint("BOTTOMRIGHT", fill, "BOTTOMRIGHT", 0, 0)
                pan:Hide()
            end)
        else
            Put("pandemicTexture", "skipped: no bar")
        end
        if pan then
            c.panTex = pan
            Put("addPandemicRegion", GS.Step(button, "AddPandemicRegion", pan))
        else
            Put("addPandemicRegion", "skipped: no pandemic texture")
        end
    end
end

-- The plain (unprotected) pieces of one column: holder, label, two tinted boxes and the bar box. Built once.
function HP.EnsureFrames(token, index, row)
    local c = HP.cache[token]
    if c and c.holder then return c end
    c = c or {}
    HP.cache[token] = c
    local x = -(#HP.TOKENS * HP.COL_W) / 2 + (index - 1) * HP.COL_W
    local holder = CreateFrame("Frame", nil, UIParent)
    holder:SetSize(HP.COL_W - 8, HP.BOX + 16 + 2 + HP.BAR_LABEL_H + HP.BAR_BOX_H)
    holder:SetPoint("TOPLEFT", UIParent, "CENTER", x, HP.TOP)
    c.holder = holder
    local label = holder:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, 0)
    label:SetText("hot " .. token)
    c.label = label
    local function box(w, anchor, dx)
        local f = CreateFrame("Frame", nil, holder)
        f:SetSize(w, HP.BOX)
        f:SetPoint("TOPLEFT", anchor, anchor == holder and "TOPLEFT" or "TOPRIGHT", dx, anchor == holder and -16 or 0)
        local bg = f:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(f)
        bg:SetColorTexture(HP.BG[1], HP.BG[2], HP.BG[3], HP.BG[4])
        return f
    end
    c.slotBox = box(HP.BOX, holder, 0)
    c.groupBox = box(HP.GROUP_FRAMES * (HP.BOX + 2) - 2, c.slotBox, HP.GAP)
    -- The bar slot's strip box, under the two boxes, labelled "bar".
    local barLabel = holder:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    barLabel:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, -(16 + HP.BOX + 2))
    barLabel:SetText("bar")
    c.barLabel = barLabel
    local barBox = CreateFrame("Frame", nil, holder)
    barBox:SetSize(HP.COL_W - 8, HP.BAR_BOX_H)
    barBox:SetPoint("TOPLEFT", holder, "TOPLEFT", 0, -(16 + HP.BOX + 2 + HP.BAR_LABEL_H))
    local barBg = barBox:CreateTexture(nil, "BACKGROUND")
    barBg:SetAllPoints(barBox)
    barBg:SetColorTexture(HP.BG[1], HP.BG[2], HP.BG[3], HP.BG[4])
    c.barBox = barBox
    row.steps.frames = "ok"
    return c
end

function HP.BuildToken(token, index, ids, row)
    local okF, errF = pcall(HP.EnsureFrames, token, index, row)
    if not okF then
        row.steps.frames = ErrText(errF)
        row.status = "layout frames failed"
        return
    end
    local c = HP.cache[token]
    GS.Step(c.holder, "Show")
    local container = c.container
    if container == nil then
        local ok, result = pcall(CreateFrame, "AuraContainer", "FSCheckHot_" .. token, UIParent, TEMPLATE)
        row.steps.createFrame = ok and "ok" or ErrText(result)
        if not ok then
            row.status = "create failed"
            return
        end
        container = result
        c.container = container
    else
        row.steps.createFrame = "reused"
    end
    row.steps.setSize = GS.Step(container, "SetSize", 1, 1)
    row.steps.setPoint = GS.Step(container, "SetPoint", "TOPLEFT", c.groupBox, "TOPLEFT", 0, 0)
    row.steps.setAlpha = GS.Step(container, "SetAlpha", 1)
    if c.built then
        row.steps.addAuraSlot = "reused"
        row.steps.addBarSlot = "reused"
        row.steps.addAuraGroup = "reused"
        row.barSteps = c.barRec
    else
        local sortMethod = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
        local sortDirection = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
        local exists, ok, res = GS.Call(container, "AddAuraSlot", HP.SLOT_KEY, HP.FILTER, {
            initializeFrame = HP.Init(token, "slot"),
            candidateFilters = { includeSpellIDs = ids },
            sortMethod = sortMethod,
            sortDirection = sortDirection,
        })
        if not exists then
            row.steps.addAuraSlot = "absent"
        elseif not ok then
            row.steps.addAuraSlot = res
        else
            row.steps.addAuraSlot = "ok"
            c.slot = res[2]
        end
        local barExists, barOk, barRes = GS.Call(container, "AddAuraSlot", HP.BAR_KEY, HP.FILTER, {
            initializeFrame = HP.InitBar(token),
            candidateFilters = { includeSpellIDs = ids },
            sortMethod = sortMethod,
            sortDirection = sortDirection,
        })
        if not barExists then
            row.steps.addBarSlot = "absent"
        elseif not barOk then
            row.steps.addBarSlot = barRes
        else
            row.steps.addBarSlot = "ok"
            c.barSlot = barRes[2]
        end
        row.steps.addAuraGroup = GS.Step(container, "AddAuraGroup", HP.GROUP_KEY, HP.FILTER, {
            maxFrameCount = HP.GROUP_FRAMES,
            sortMethod = sortMethod,
            sortDirection = sortDirection,
            initializeFrame = HP.Init(token, "group"),
            candidateFilters = { maxDuration = HP.MAX_DURATION },
            layout = { elementSpacing = 2, lineSpacing = 2, groupLineSpacing = 2,
                elementWidth = HP.BOX, elementHeight = HP.BOX },
        })
        c.built = row.steps.addAuraSlot == "ok" or row.steps.addAuraGroup == "ok"
        local flow = type(_G.AnchorUtil) == "table" and _G.AnchorUtil.FlowDirection or nil
        if type(flow) == "table" and flow.Right ~= nil and flow.Down ~= nil then
            row.steps.flowAnchor = GS.Step(container, "SetFlowLayoutAnchorPoint", "TOPLEFT")
            row.steps.flowGrowth = GS.Step(container, "SetFlowLayoutGrowthDirection", flow.Right, flow.Down)
        else
            row.steps.flowGrowth = "absent: AnchorUtil.FlowDirection"
        end
    end
    row.steps.setUnit = GS.Step(container, "SetUnit", token)
    row.steps.setEnabled = GS.Step(container, "SetEnabled", true)
    row.steps.show = GS.Step(container, "Show")
    row.built = c.built == true
    row.status = row.built and "built" or "no slot or group accepted"
end

-- One plain-query sample of one column; also updates its running counts.
function HP.SampleRow(row, c, n, combat)
    local ch, shown, unknown = nil, 0, 0
    local exists, ok, res = GS.Call(c.container, "GetNumChildren")
    if exists and ok and not IsSecret(res[2]) and type(res[2]) == "number" then ch = res[2] end
    local okC, okCall, kids, count = GS.Call(c.container, "GetChildren")
    if okC and okCall then
        for i = 1, count do
            local child = kids[i + 1]
            local okS, s = pcall(function() return child:IsShown() end)
            if okS and not IsSecret(s) then
                if s == true then shown = shown + 1 end
            else
                unknown = unknown + 1
            end
        end
    end
    local slotShown = "none"
    if c.slot ~= nil then slotShown = HP.Fmt(GS.Read(c.slot, "IsShown")) end
    local barShown, panShown = "none", "none"
    if c.barSlot ~= nil then barShown = HP.Fmt(GS.Read(c.barSlot, "IsShown")) end
    if c.panTex ~= nil then panShown = HP.Fmt(GS.Read(c.panTex, "IsShown")) end
    local grp = HP.Fmt(GS.Read(c.container, "GetAuraGroupFrameCount", HP.GROUP_KEY))
    local cont = HP.Fmt(GS.Read(c.container, "IsShown"))
    row.samples[#row.samples + 1] = string.format("%d %s ch=%s shown=%d unk=%d slot=%s bar=%s pan=%s grp=%s cont=%s",
        n, combat and "COMBAT" or "ooc", HP.Fmt(ch), shown, unknown, slotShown, barShown, panShown, grp, cont)

    local st = row.stats
    local bucket = combat and st.combat or st.ooc
    bucket.samples = bucket.samples + 1
    if slotShown == "true" then
        bucket.slotShown = bucket.slotShown + 1
    elseif slotShown == "secret" then
        bucket.slotSecret = bucket.slotSecret + 1
    end
    -- The bar slot button and the pandemic texture: shown, or secret (unknown), never "hidden".
    if barShown == "true" then
        bucket.barShown = bucket.barShown + 1
    elseif barShown == "secret" then
        bucket.barSecret = bucket.barSecret + 1
    end
    if panShown == "true" then
        bucket.panShown = bucket.panShown + 1
    elseif panShown == "secret" then
        bucket.panSecret = bucket.panSecret + 1
    end
    if shown > bucket.maxShown then bucket.maxShown = shown end   -- a lower bound, still true
    if unknown > 0 then
        -- Some button answered with a secret (in combat, all of them): the true shown count is
        -- not known, so this sample says nothing about withShown or a transition, and
        -- row.lastShown keeps the last KNOWN count for the next readable sample.
        bucket.unknown = bucket.unknown + 1
        return
    end
    if shown > 0 then bucket.withShown = bucket.withShown + 1 end
    local last = row.lastShown
    if last ~= nil and last ~= shown then
        st.transitions = st.transitions + 1
        if combat and shown == 0 then st.lostInCombat = st.lostInCombat + 1 end
        if combat and last == 0 then st.gainedInCombat = st.gainedInCombat + 1 end
    end
    row.lastShown = shown
end

function HP.Sample(live)
    live.n = live.n + 1
    local combat = LockedDown(false)
    live.rec.meta.lockdownSamples = (live.rec.meta.lockdownSamples or 0) + (combat and 1 or 0)
    for _, token in ipairs(HP.TOKENS) do
        local row, c = live.rows[token], HP.cache[token]
        if row and row.built and c and c.container then
            local ok, err = pcall(HP.SampleRow, row, c, live.n, combat)
            if not ok then
                row.sampleErrors = (row.sampleErrors or 0) + 1
                if row.firstSampleError == nil then row.firstSampleError = ErrText(err) end
            end
        end
    end
end

function HP.Summary(live)
    local parts = {}
    for _, token in ipairs(HP.TOKENS) do
        local row = live.rows[token]
        if row and row.built then
            local o, k = row.stats.ooc, row.stats.combat
            parts[#parts + 1] = string.format(
                "%s ooc %d/%d cbt %d/%d unk %d slotsecret %d lost %d init %d+%d barshown %d barunk %d pandemic %d pandemicunk %d",
                token, o.withShown, o.samples, k.withShown, k.samples, k.unknown, k.slotSecret,
                row.stats.lostInCombat, row.initCalls.slot, row.initCalls.group,
                o.barShown + k.barShown, o.barSecret + k.barSecret, o.panShown + k.panShown, o.panSecret + k.panSecret)
        elseif row and row.exists then
            parts[#parts + 1] = token .. " " .. tostring(row.status or "not built")
        end
    end
    return "samples with a button shown / samples (unk = in-combat samples with a secret IsShown; barshown and pandemic = samples the bar slot / pandemic overlay read shown, barunk and pandemicunk = secret): "
        .. table.concat(parts, " | ")
end

function HP.Finish(live, reason)
    if not live.sampling then return end
    live.sampling = false
    live.rec.meta.ended = reason
    live.rec.meta.samples = live.n
    live.rec.summary = HP.Summary(live)
    Say("hot " .. reason .. " (" .. live.n .. " samples): " .. live.rec.summary
        .. ". /reload to save; /fscheck hot off removes the strip")
end

function HP.Tick(run)
    local live = HP.live
    if not live or live.run ~= run or not live.sampling then return end
    local ok, err = pcall(HP.Sample, live)
    if not ok then live.rec.meta.sampleError = ErrText(err) end
    if live.n >= HP.SECONDS / HP.PERIOD + 1 then
        HP.Finish(live, "done")
        return
    end
    if not GS.Timer(HP.PERIOD, function() HP.Tick(run) end) then
        live.rec.meta.timerError = "C_Timer.After unavailable; sampling stopped"
        HP.Finish(live, "stopped")
    end
end

function HP.Start()
    if LockedDown(true) then
        Say("hot: leave combat first (the containers are built and enabled out of combat only)")
        return
    end
    local old = HP.live
    if old and old.sampling then
        Say("hot: already sampling (" .. old.n .. " of " .. (HP.SECONDS / HP.PERIOD + 1) .. "); /fscheck hot off stops it")
        return
    end
    HP.run = HP.run + 1
    local meta = {
        started = SafeDate(), run = HP.run, filter = HP.FILTER, maxDuration = HP.MAX_DURATION,
        issecretvalueAvailable = type(_G.issecretvalue) == "function",
    }
    local rec = { meta = meta, tokens = {} }
    DB().hot = rec
    local live = { run = HP.run, rec = rec, rows = {}, n = 0, sampling = false }
    HP.live = live

    local getTemplate = Api("C_XMLUtil", "GetTemplateInfo")
    if not getTemplate then
        meta.status = "absent: C_XMLUtil.GetTemplateInfo"
        Say("hot: " .. meta.status)
        return
    end
    local okT, tmpl = pcall(getTemplate, TEMPLATE)
    if not okT then
        meta.status = "template check errored: " .. ErrText(tmpl)
        Say("hot: " .. meta.status)
        return
    end
    if not IsSecret(tmpl) and (type(tmpl) == "nil" or tmpl == false) then
        meta.status = "template absent: " .. TEMPLATE
        Say("hot: " .. meta.status)
        return
    end

    local ids = HP.IdSet(meta)
    local built = 0
    for index, token in ipairs(HP.TOKENS) do
        local row = HP.NewRow(HP.TokenExists(token))
        rec.tokens[token] = row
        live.rows[token] = row
        if row.exists then
            local ok, err = pcall(HP.BuildToken, token, index, ids, row)
            if not ok then
                row.buildError = ErrText(err)
                row.status = "build error"
            end
            if row.built then built = built + 1 end
        else
            row.status = "no such unit"
        end
    end
    meta.status = "built " .. built
    if built == 0 then
        Say("hot: no container built, see ForeverSTUwaveDB.fscheck.hot (/reload to save)")
        return
    end
    live.sampling = true
    Say("hot: " .. built .. " container(s) up above screen centre (renew slot box, then up to "
        .. HP.GROUP_FRAMES .. " short-buff buttons, then a row labelled bar). Renew ids from ElvUI's list (" .. meta.idCount .. " incl. runtime rank "
        .. tostring(meta.runtimeRank) .. "). Cast Renew on yourself and a party member, pull a mob, wait "
        .. HP.SECONDS .. "s")
    Say("hot: watch the bar row: (1) does the bar drain from the left toward the number, (2) does the number count "
        .. "whole seconds with no s, (3) does the number turn amber at 3, (4) does an amber overlay (pandemic) show on the bar near the end")
    HP.Tick(HP.run)
end

-- quiet: the explicit /fscheck reset path, which prints its own line.
function HP.Off(quiet)
    local live = HP.live
    if live and live.sampling then HP.Finish(live, "stopped") end
    HP.run = HP.run + 1
    local combat = LockedDown(true)
    for _, c in pairs(HP.cache) do
        if c.container then
            GS.Step(c.container, "SetAlpha", 0)
            if not combat then
                Quiet(c.container, "SetEnabled", false)
                Quiet(c.container, "Hide")
            end
        end
        GS.Hide(c.holder)
    end
    if quiet then return end
    if combat then
        Say("hot off: alpha 0 on the containers, plain holder hidden; the containers stay enabled until you run /fscheck hot off out of combat")
    else
        Say("hot off: strip removed")
    end
end

-------------------------------------------------------------------------------
-- /fscheck
-------------------------------------------------------------------------------

-- keepGunsight: the main run re-arming must not wipe a saved `/fscheck gunsight`, `/fscheck hot`,
-- `/fscheck priest` or `/fscheck shaman` result or disarm their pending parts; only an explicit `/fscheck reset` clears those.
local function Reset(keepGunsight)
    state.runId = state.runId + 1
    state.armed = false
    state.combatDone = false
    state.combatPending = false
    state.combatSkips = 0
    state.castsDone = false
    state.castCount = 0
    state.channelCount = 0
    state.auraOoc = 0
    state.auraCombat = 0
    state.procCount = 0
    state.shootCount = 0
    state.startCount = 0
    state.startAt = nil
    state.startSpell = nil
    state.gcdKnown = nil
    state.acDone = false
    state.acBuilt = false
    state.rowLive = false
    UnregisterAll()
    if state.container then
        pcall(function() state.container:Hide() end)
        pcall(function() state.container:SetEnabled(false) end)
    end
    if state.label then pcall(function() state.label:Hide() end) end
    local root = _G.ForeverSTUwaveDB
    if type(root) == "table" then
        local kept, keptHot, keptPriest, keptShaman = nil, nil, nil, nil
        if keepGunsight and type(root[KEY]) == "table" then
            kept = root[KEY].gunsight
            keptHot = root[KEY].hot
            keptPriest = root[KEY].priest
            keptShaman = root[KEY].shaman
        end
        root[KEY] = nil
        if type(kept) == "table" or type(keptHot) == "table" or type(keptPriest) == "table" or type(keptShaman) == "table" then
            root[KEY] = { gunsight = kept, hot = keptHot, priest = keptPriest, shaman = keptShaman }
        end
    end
    if not keepGunsight then
        -- First, and on its own: a failure in the gunsight or hot teardown must not leave the priest
        -- check's events registered.
        PP.Stop("reset", true)
        SH.Stop("reset", true)
        GS.Disarm()
        HP.Off(true)
    end
end

-- True when a finished run, or any combat/cast/channel results, are already saved. Reads
-- the SavedVariable without creating it.
local function SavedResults()
    local root = _G.ForeverSTUwaveDB
    local db = type(root) == "table" and root[KEY] or nil
    if type(db) ~= "table" then return false end
    local status = type(db.meta) == "table" and db.meta.status or nil
    return status == "done" or db.combat ~= nil or db.casts ~= nil or db.channel ~= nil
end

local function Arm()
    Reset(true)
    state.canTest = Invoke(false, Api("issecretvalue"), 0).ok == true
    local meta = Meta()
    meta.started = SafeDate()
    meta.run = state.runId
    meta.status = "armed"
    meta.canTestSecret = state.canTest

    DB().ooc = TakeSnapshot("ooc")
    state.armed = true

    -- The container is built now, hidden, so the only thing left for the combat
    -- moment is SetUnit/Show. A missing template completes that part immediately.
    local ok, err = pcall(BuildContainer)
    if not ok then AcRecord().status = "build error: " .. ErrText(err) end
    if not state.acBuilt then state.acDone = true end

    if not EnsureFrame() then
        Say("snapshot saved (ooc) but the event frame could not be created; nothing armed")
        state.armed = false
        return
    end
    FrameCall("RegisterEvent", "PLAYER_REGEN_DISABLED")
    RegisterUnit("UNIT_SPELLCAST_SUCCEEDED")
    RegisterUnit("UNIT_SPELLCAST_START")
    for _, event in ipairs(CAST_END_EVENTS) do RegisterUnit(event) end
    for _, event in ipairs(CHANNEL_EVENTS) do RegisterUnit(event) end
    RegisterExtras()

    Say("snapshot saved (ooc). Armed: pull a mob (combat snapshot ~" .. COMBAT_DELAY
        .. "s in), cast " .. CAST_TARGET .. " spells, aura test shows " .. AURA_SHOW_SECONDS .. "s after the combat snapshot")
end

local function Command(msg)
    local arg = ""
    if type(msg) == "string" then arg = string.lower((string.gsub(msg, "^%s*(.-)%s*$", "%1"))) end
    arg = string.gsub(arg, "%s+", " ")
    if arg == "reset" then
        Reset()
        Say("results cleared, nothing armed")
    elseif arg == "gunsight" then
        GS.Start()
    elseif arg == "priest" then
        PP.Start()
    elseif arg == "priest off" then
        PP.Stop("stopped")
    elseif arg == "shaman" then
        SH.Start()
    elseif arg == "shaman off" then
        SH.Stop("stopped")
    elseif arg == "shaman buttons" then
        SH.ButtonsOn()
    elseif arg == "shaman buttons off" then
        SH.ButtonsOff()
    elseif arg == "shaman setslot" then
        SH.SetSlot()
    elseif arg == "shaman destroy" then
        SH.Destroy(nil)
    elseif string.match(arg, "^shaman destroy %S+$") then
        SH.Destroy(string.match(arg, "^shaman destroy (%S+)$"))
    elseif arg == "hot" then
        HP.Start()
    elseif arg == "hot off" then
        HP.Off()
    elseif arg == "help" or arg == "?" then
        for _, line in ipairs(USAGE) do print(line) end
    elseif arg ~= "" then
        for _, line in ipairs(USAGE) do print(line) end
    elseif state.armed then
        Say(StatusLine())
    elseif SavedResults() then
        Say("results exist, /reload to save or /fscheck reset first")
    elseif LockedDown(false) then
        -- The ooc snapshot would be taken in combat and mislabelled. If the check
        -- itself fails, arm anyway: the errors are data.
        Say("leave combat first")
    else
        Arm()
    end
end

SLASH_FSCHECK1 = "/fscheck"
SlashCmdList["FSCHECK"] = function(msg)
    local ok, err = pcall(Command, msg)
    if not ok then
        pcall(print, "fscheck: error (not fatal): " .. ErrText(err))
    end
end
