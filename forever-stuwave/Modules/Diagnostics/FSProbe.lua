-- Forever STUwave: /fsprobe -- opt-in, read-only secret-value probe
--
-- Parker types /fsprobe ONCE before a play session. It records into
-- ForeverSTUwaveDB.fsprobe what this client lets an addon READ, in and out of
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
--                  sample taken right after each SUCCEEDED / at each START (see GcdProbe)
--
--   gunsight       `/fsprobe gunsight`: a SEPARATE one-shot feature probe for the gunsight HUD
--                  (8-arg SetTexCoord, SetVertexColorFromBoolean, a vertical StatusBar fed a
--                  duration object, CreateLine, C_UnitAuras instance ids and aura durations in
--                  combat, an engine-drawn AuraContainer, SetAlphaFromBoolean). Stored in
--                  ForeverSTUwaveDB.fsprobe.gunsight; it never touches the main run's armed
--                  state and survives a re-arm; re-running it replaces the result.
--
--   hot            `/fsprobe hot` (out of combat) / `/fsprobe hot off`: does an engine AuraContainer
--                  per party token (player, party1..4) draw the player's own Renew, and do its
--                  buttons stay up and tick in combat? Plain widget queries only. Also builds the
--                  HoT TIMER BAR shape (a StatusBar the engine drives, a bare-number countdown that
--                  turns amber at 3, a pandemic overlay). Stored in ForeverSTUwaveDB.fsprobe.hot;
--                  survives a re-arm like gunsight (see HP below).
--
-- Read it after /reload or logout: WTF/Account/<id>/SavedVariables/forever-stuwave.lua
-- (ForeverSTUwaveDB.fsprobe).
--
-- Rules this file keeps, because it runs in the middle of a play session:
--   * Nothing runs at load. The only side effect of loading is the slash command.
--     The event frame, the events and the timers all start inside /fsprobe.
--   * Every API call, handler and timer is pcall'd. An error becomes a string in
--     the results; nothing is ever thrown into the session.
--   * Read-only. No protected call, no SetAttribute, no secure template. The one
--     visible thing is an AuraContainer built from the same template Plater uses.
--   * A secret value is never compared, concatenated, truth-tested, indexed or
--     tostring'd, and never stored. Only its type and the boolean "isSecret" are
--     recorded. A plain value is stored only where a field is marked `keep`, and
--     only when issecretvalue() answered "no". If issecretvalue() itself cannot be
--     called, the answer fails closed ("secret") and no value is stored.
--   * Every event is unregistered as its part finishes, and nothing uses OnUpdate.

local KEY = "fsprobe"
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

-- GCD: spells whose cooldown table is read in each snapshot. GCD_PROBE_SPELLS are the
-- candidates read for isActive in a cast sample: only spells with NO cooldown of their own
-- (Mind Blast has an 8s one, so it would read active with no GCD running), and never the
-- spell that was just cast. 61304 is the global cooldown marker, read as the control.
local GCD_MARKER = 61304
local GCD_SECTION_SPELLS = { GCD_MARKER, 686, 585 }
local GCD_PROBE_SPELLS = { 585, 686, 172 }
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
    "fsprobe: /fsprobe (out of combat) = snapshot now, then record your next pull, 10 casts, and a 30s aura row above screen centre",
    "fsprobe: /fsprobe again = status | /fsprobe reset = clear and stop | after \"done\", /reload to save",
    "fsprobe: /fsprobe gunsight = gunsight HUD feature probes (works any time; the cast and combat parts wait for your next cast and pull)",
    "fsprobe: /fsprobe hot = party row HoT probe: an engine aura container per party token (icon, short buffs, HoT timer bar) for 120s (out of combat to start) | /fsprobe hot off = remove it",
}

-------------------------------------------------------------------------------
-- State (all of it dormant until /fsprobe runs)
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
    print("fsprobe: " .. text)
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

    local frame = _G.FSProbeAuraContainer
    if frame == nil then
        local ok, result = pcall(CreateFrame, "AuraContainer", "FSProbeAuraContainer", UIParent, TEMPLATE)
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
        local holder = _G.FSProbeAuraLabel
        if holder == nil then
            holder = CreateFrame("Frame", "FSProbeAuraLabel", UIParent)
            holder:SetSize(120, 12)
            holder:SetPoint("BOTTOMLEFT", UIParent, "CENTER", -100, 206)
            local text = holder:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
            text:SetPoint("LEFT")
            text:SetText("fsprobe auras")
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

-- The known spells of GCD_PROBE_SPELLS, in order (a non-empty result is cached per run).
local function GcdKnown()
    if state.gcdKnown then return state.gcdKnown end
    local isPlayerSpell = Api("IsPlayerSpell")
    local isKnown = Api("C_SpellBook", "IsSpellKnown")
    local known = {}
    for _, id in ipairs(GCD_PROBE_SPELLS) do
        if KeptBool(Invoke(true, isPlayerSpell, id)) == true or KeptBool(Invoke(true, isKnown, id)) == true then
            known[#known + 1] = id
        end
    end
    -- An empty list is not cached: the spellbook may simply not be loaded yet.
    if #known > 0 then state.gcdKnown = known end
    return known
end

-- The first known probe spell whose NAME differs from the just-cast spell's (a plain
-- compare, after SpellName's IsSecret checks), or nil. A probe id equal to the plain
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
local function GcdProbe(castID, elapsed)
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
    rec.gcd = GcdProbe(castID, TakeCastElapsed(castID))
    return rec
end

local function RecordStart(event, ...)
    local rec = RecordCast(event, ...)
    rec.gcd = GcdProbe(PlainSpellID(...))
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
        -- in-combat samples this probe exists for. A failed lockdown check counts as out.
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
-- /fsprobe gunsight: feature probes for the gunsight HUD
-------------------------------------------------------------------------------
-- One slash call runs the immediate probes and arms the two that need a live event: the
-- vertical bar fed a real cast duration (next UNIT_SPELLCAST_START for "player") and the
-- C_UnitAuras reads on a target in combat (next PLAYER_REGEN_DISABLED). Everything is stored
-- in ForeverSTUwaveDB.fsprobe.gunsight[<probe>]. Only booleans, plain numbers and short
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

-- Stores the one-line summary beside the probe and prints it.
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

-- The probe's test objects are built once and cached on `state`, so re-running the probe
-- never grows the frame count (a frame or texture cannot be destroyed). Each probe hides its
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

function GS.ProbeTexCoord(rec, _host)
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

function GS.ProbeVertexColor(rec, _host)
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

function GS.ProbeBarManual(rec, _host, run)
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

function GS.ProbeBarCast(run)
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

function GS.ProbeLine(rec, host)
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

function GS.ProbeAuraApi(rec)
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

function GS.ProbeAlpha(rec, _host)
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

GS.AC_NAME = "FSProbeGsAuraContainer"
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

-- Out of combat, run by /fsprobe gunsight: build the container once (cached on `state`),
-- add the group once, point it at the target, leave it hidden and disabled.
function GS.ProbeAuraContainer(rec, _host)
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
        GS.ProbeBarCast(state.gsRun)
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

-- Runs one probe under pcall so a failure is recorded and the next probe still runs.
function GS.Run(key, fn, ...)
    local rec = GS.Section(key)
    local ok, err = pcall(fn, rec, ...)
    if not ok then
        rec.probeError = ErrText(err)
        GS.Report(key, "probe error: " .. rec.probeError)
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

    GS.Run("texcoord8", GS.ProbeTexCoord, host)
    GS.Run("vertexColorFromBoolean", GS.ProbeVertexColor, host)
    GS.Run("verticalBarTimer", GS.ProbeBarManual, host, run)
    GS.Run("line", GS.ProbeLine, host)
    GS.Run("auraApi", GS.ProbeAuraApi)
    GS.Run("auraContainer", GS.ProbeAuraContainer)
    GS.Run("alphaFromBoolean", GS.ProbeAlpha, host)

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
    Say("gunsight results: ForeverSTUwaveDB.fsprobe.gunsight, /reload or log out to save to "
        .. "WTF/Account/<id>/SavedVariables/forever-stuwave.lua (late results print as they finish)")
end

-------------------------------------------------------------------------------
-- /fsprobe hot: can an engine AuraContainer per party row show the player's own Renew?
-------------------------------------------------------------------------------
-- `/fsprobe hot` (out of combat only) builds one CustomAuraContainerTemplate per token that
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
-- `/fsprobe hot off` in combat only sets alpha 0 on the containers and hides the plain holder
-- (the unprotected frame), then says to repeat it later.
-- Source for the option names: Blizzard_CustomAuraContainer.lua (ValidateCandidateFilters:
-- includeSpellIDs is a set and "only permitted for helpful buffs on assistable units";
-- maxDuration is derived from the aura's MAX duration and hides permanent auras).
-- Results: ForeverSTUwaveDB.fsprobe.hot (see HP.NewRow for the shape).

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
        local ok, result = pcall(CreateFrame, "AuraContainer", "FSProbeHot_" .. token, UIParent, TEMPLATE)
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
        .. ". /reload to save; /fsprobe hot off removes the strip")
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
        Say("hot: already sampling (" .. old.n .. " of " .. (HP.SECONDS / HP.PERIOD + 1) .. "); /fsprobe hot off stops it")
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
        Say("hot: no container built, see ForeverSTUwaveDB.fsprobe.hot (/reload to save)")
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

-- quiet: the explicit /fsprobe reset path, which prints its own line.
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
        Say("hot off: alpha 0 on the containers, plain holder hidden; the containers stay enabled until you run /fsprobe hot off out of combat")
    else
        Say("hot off: strip removed")
    end
end

-------------------------------------------------------------------------------
-- /fsprobe
-------------------------------------------------------------------------------

-- keepGunsight: the main run re-arming must not wipe a saved `/fsprobe gunsight` or `/fsprobe hot`
-- result or disarm their pending parts; only an explicit `/fsprobe reset` clears those.
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
        local kept, keptHot = nil, nil
        if keepGunsight and type(root[KEY]) == "table" then
            kept = root[KEY].gunsight
            keptHot = root[KEY].hot
        end
        root[KEY] = nil
        if type(kept) == "table" or type(keptHot) == "table" then
            root[KEY] = { gunsight = kept, hot = keptHot }
        end
    end
    if not keepGunsight then
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
        Say("results exist, /reload to save or /fsprobe reset first")
    elseif LockedDown(false) then
        -- The ooc snapshot would be taken in combat and mislabelled. If the check
        -- itself fails, arm anyway: the errors are data.
        Say("leave combat first")
    else
        Arm()
    end
end

SLASH_FSPROBE1 = "/fsprobe"
SlashCmdList["FSPROBE"] = function(msg)
    local ok, err = pcall(Command, msg)
    if not ok then
        pcall(print, "fsprobe: error (not fatal): " .. ErrText(err))
    end
end
