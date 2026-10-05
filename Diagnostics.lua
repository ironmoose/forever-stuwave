-- Forever Synthwave: Diagnostics
-- /fsfont: does each bundled font actually LOAD, and is the live UI wearing it?
-- Extracted out of Theme.lua; reads FS.Theme.* only, since a diagnostic
-- command has no reason to live in the chrome/tokens file. Loads last (see
-- .toc) since it samples FS.player/FS.target, which UnitFrames.lua builds.

local _, FS = ...
local Theme = FS.Theme
local MINIMAP_BOUNDS_DEPTH = 6
local MINIMAP_BOUNDS_NODES = 250
local MINIMAP_PARENT_LIMIT = 32
local MINIMAP_BOUNDS_PALETTE = {
    { 0, 1, 1 }, { 0, 1, 0 }, { 1, 1, 0 }, { 1, 0, 1 }, { 0.6, 0.3, 1 },
}

-------------------------------------------------------------------------------
-- /fsfont -- does each bundled font actually LOAD?
-------------------------------------------------------------------------------

-- ApplyFontGeneric already reads the font path back rather than trusting
-- SetFont's return value, but when the readback fails it only says so in the
-- chat frame. That warning scrolls away, it is rate-limited to once per path
-- per session, and it never reaches ForeverSynthwaveErrorLog -- so an empty
-- error log says nothing at all about whether our fonts loaded. That is how
-- Orbitron-VF.ttf went weeks as a silent FRIZQT fallback.
--
-- This writes the same readback into ForeverSynthwaveDB, where it survives the
-- unload and fsdev.py can read it, instead of into a chat line nobody is
-- looking at. Probe lives in the addon rather than in a long /run for the same
-- reason /fsreload does: the chat box truncates at 255 characters.
SLASH_FSFONT1 = "/fsfont"
SlashCmdList["FSFONT"] = function()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}

    local probe = UIParent:CreateFontString(nil, "ARTWORK")
    local report = { when = date("%Y-%m-%d %H:%M:%S") }

    for label, path in pairs({
        mono = Theme.FONT_MONO,
        orbitron = Theme.FONT_ORBITRON,
    }) do
        probe:SetFont(path, 12, "")
        local got = probe:GetFont()
        -- GetFont echoes the path we asked for on success. Anything else is
        -- the engine's fallback, which is the failure we are hunting.
        report[label] = {
            want = path,
            got = tostring(got),
            ok = tostring(Theme.SameFontPath(got, path)),
        }
        print(("|cff22e0ff%-9s|r %s"):format(
            label, Theme.SameFontPath(got, path) and "LOADS" or "FAILED -> " .. tostring(got)))
    end

    -- A constant loading in isolation is not the same as the live UI wearing
    -- it: a component can be applying a different path, or nothing at all.
    -- Sample the real widgets the Orbitron change was supposed to fix. These
    -- fontstrings are anonymous, so there is no _G name to look up -- the only
    -- handles are the ones UnitFrames hangs off FS.player / FS.target.
    for label, fs in pairs({
        playerName = FS.player and FS.player.name,
        playerLevel = FS.player and FS.player.levelText,
        targetName = FS.target and FS.target.name,
        targetLevel = FS.target and FS.target.levelText,
    }) do
        if fs and fs.GetFont then
            local got = fs:GetFont()
            report[label] = {
                got = tostring(got),
                ok = tostring(Theme.SameFontPath(got, Theme.FONT_ORBITRON)),
            }
            print(("|cff22e0ff%-9s|r %s"):format(
                label, Theme.SameFontPath(got, Theme.FONT_ORBITRON) and "orbitron" or tostring(got)))
        else
            report[label] = { got = "NO SUCH WIDGET" }
        end
    end

    ForeverSynthwaveDB.fontProbe = report
    print("|cff22e0ffsynthwave://font|r  written to ForeverSynthwaveDB; /fsreload to flush it")
end

-------------------------------------------------------------------------------
-- /fsrecon threat -- threat/role/reaction secret-value probe
-------------------------------------------------------------------------------

-- The player has no group and no reliable in-combat access to threat tables,
-- so this answers by MEASUREMENT whether UnitThreatSituation and friends hand
-- back secrets while tainted, rather than guessing from the
-- 12.0 docs. Dispatched from PanelSkins.lua's `/fsrecon` (that file loads
-- before this one, so it reaches these through `FS.Diagnostics.*` at call
-- time, never a captured local -- same rule as the Chat terminal's split).
FS.Diagnostics = FS.Diagnostics or {}
local Diagnostics = FS.Diagnostics

-------------------------------------------------------------------------------
-- /fsrecon probe -- bounded target aura event capture during combat
-------------------------------------------------------------------------------

local PROBE_MAX_UPDATES = 8
local PROBE_MAX_AURAS = 3
local PROBE_AURA_FIELDS = { "sourceUnit", "spellId", "auraInstanceID" }
local probeFrame
local probeRun

local function ProbeError(err)
    if type(err) ~= "string" then return "other error" end
    local ok, refused = pcall(function()
        local message = err:lower()
        return message:find("secret", 1, true) ~= nil
            or message:find("taint", 1, true) ~= nil
            or message:find("forbidden", 1, true) ~= nil
            or message:find("access denied", 1, true) ~= nil
    end)
    if ok and refused then return "secret/taint refusal" end
    return "other error"
end

local function ProbeValue(value)
    local row = { type = type(value) }
    local ok, secret = pcall(FS.IsSecret, value)
    if not ok then row.err = ProbeError(secret); return row end
    row.secret = secret and true or false
    if secret then return row end
    if type(canaccessvalue) == "function" then
        local accessOk, accessible = pcall(canaccessvalue, value)
        if not accessOk then row.err = ProbeError(accessible); return row end
        row.access = accessible and true or false
        if not accessible then return row end
    end
    if type(value) == "number" or type(value) == "boolean" then
        row.value = value
    elseif type(value) == "string" then
        -- Only the known unit token is useful here; aura names never enter the run.
        row.present = true
    end
    return row
end

local function ProbeTable(value)
    local row = ProbeValue(value)
    if row.type ~= "table" or row.err or row.secret or row.access == false then return row, false end
    if type(issecrettable) ~= "function" or type(canaccesstable) ~= "function" then
        row.err = "table inspectors unavailable"
        return row, false
    end
    local secretOk, secret = pcall(issecrettable, value)
    if not secretOk then row.err = ProbeError(secret); return row, false end
    row.secretTable = secret and true or false
    if secret then return row, false end
    local accessOk, access = pcall(canaccesstable, value)
    if not accessOk then row.err = ProbeError(access); return row, false end
    row.accessTable = access and true or false
    if not access then return row, false end
    return row, true
end

local function ProbeField(parent, key)
    local ok, value = pcall(function() return parent[key] end)
    if not ok then return { err = ProbeError(value) }, nil, false end
    return ProbeValue(value), value, true
end

local function ProbeList(value)
    local row, accessible = ProbeTable(value)
    if not accessible then return row, false end
    local ok, count = pcall(function() return #value end)
    if not ok then row.err = ProbeError(count); return row, false end
    local countRow = ProbeValue(count)
    if countRow.err or countRow.secret or countRow.access == false or type(count) ~= "number" then
        row.countResult = countRow
        return row, false
    end
    row.count = count
    return row, true
end

local function ProbeAuraRecord(value)
    local row, accessible = ProbeTable(value)
    if not accessible then return row end
    row.fields = {}
    for _, field in ipairs(PROBE_AURA_FIELDS) do
        local fieldRow, fieldValue = ProbeField(value, field)
        if field == "sourceUnit" and not fieldRow.err and not fieldRow.secret
            and fieldRow.access ~= false and type(fieldValue) == "string" then
            fieldRow.value = fieldValue == "player" and "player" or "other unit token"
        end
        row.fields[field] = fieldRow
    end
    return row
end

local function ProbeAuraList(value, inspect)
    local row, accessible = ProbeList(value)
    if not accessible then return row end
    if inspect then
        row.items = {}
        for i = 1, math.min(row.count, PROBE_MAX_AURAS) do
            local ok, item = pcall(function() return value[i] end)
            row.items[i] = ok and ProbeAuraRecord(item) or { err = ProbeError(item) }
        end
    end
    return row
end

local function ProbeAuraAPI(name, ...)
    local api = C_UnitAuras
    local fn = type(api) == "table" and api[name]
    if type(fn) ~= "function" then return { ok = false, err = "unavailable" } end
    local ok, value = pcall(fn, ...)
    if not ok then return { ok = false, err = ProbeError(value) } end
    return { ok = true, result = ProbeAuraList(value, name ~= "GetUnitAuraInstanceIDs") }
end

local function SaveProbe(reason)
    if not probeRun then return end
    probeRun.stop = reason
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.probe = probeRun
    probeRun = nil
    if probeFrame then probeFrame:UnregisterEvent("UNIT_AURA") end
    print("|cff22e0ffForeverSynthwave|r: /fsrecon probe -- saved; /fsreload to flush")
end

local function CaptureProbeUpdate(updateInfo)
    local row = { inCombat = true }
    local infoRow, infoAccessible = ProbeTable(updateInfo)
    row.updateInfo = infoRow
    local addedID
    if infoAccessible then
        row.fields = {}
        for _, field in ipairs({ "addedAuras", "updatedAuraInstanceIDs", "removedAuraInstanceIDs" }) do
            local fieldRow, value, readable = ProbeField(updateInfo, field)
            if readable then
                local listRow, listReadable = ProbeList(value)
                fieldRow = listRow
                if listReadable and field == "addedAuras" then
                    fieldRow.items = {}
                    for i = 1, math.min(listRow.count, PROBE_MAX_AURAS) do
                        local ok, aura = pcall(function() return value[i] end)
                        if ok then
                            fieldRow.items[i] = ProbeAuraRecord(aura)
                            if not addedID then
                                local _, auraReadable = ProbeTable(aura)
                                if auraReadable then
                                    local idRow, id = ProbeField(aura, "auraInstanceID")
                                    if not idRow.err and not idRow.secret and idRow.access ~= false
                                        and type(id) == "number" then addedID = id end
                                end
                            end
                        else
                            fieldRow.items[i] = { err = ProbeError(aura) }
                        end
                    end
                end
            end
            row.fields[field] = fieldRow
        end
    end
    row.getUnitAuras = ProbeAuraAPI("GetUnitAuras", "target", "HARMFUL", PROBE_MAX_AURAS)
    row.getInstanceIDs = ProbeAuraAPI("GetUnitAuraInstanceIDs", "target", "HARMFUL")
    local api = C_UnitAuras
    local byID = type(api) == "table" and api.GetAuraDataByAuraInstanceID
    if type(byID) ~= "function" then
        row.byAddedID = { ok = false, err = "unavailable" }
    elseif not addedID then
        row.byAddedID = { ok = false, err = "no accessible added ID" }
    else
        local ok, value = pcall(byID, "target", addedID)
        row.byAddedID = ok and { ok = true, result = ProbeAuraRecord(value) }
            or { ok = false, err = ProbeError(value) }
    end
    local byIndex = type(api) == "table" and api.GetAuraDataByIndex
    if type(byIndex) ~= "function" then
        row.byIndex = { ok = false, err = "unavailable" }
    else
        local ok, value = pcall(byIndex, "target", 1, "HARMFUL")
        row.byIndex = ok and { ok = true, result = ProbeAuraRecord(value) }
            or { ok = false, err = ProbeError(value) }
    end
    return row
end

function Diagnostics.ArmAuraProbe()
    if probeRun then SaveProbe("rearmed") end
    probeRun = { t = time(), updates = {} }
    if not probeFrame then
        probeFrame = CreateFrame("Frame")
        probeFrame:SetScript("OnEvent", function(_, _, unit, updateInfo)
            if not probeRun or unit ~= "target" then return end
            local combatOk, inCombat = pcall(InCombatLockdown)
            if not combatOk or not inCombat then return end
            local ok, row = pcall(CaptureProbeUpdate, updateInfo)
            probeRun.updates[#probeRun.updates + 1] = ok and row or { err = ProbeError(row) }
            if #probeRun.updates >= PROBE_MAX_UPDATES then SaveProbe("cap") end
        end)
    end
    probeFrame:RegisterEvent("UNIT_AURA")
    print("|cff22e0ffForeverSynthwave|r: /fsrecon probe -- armed for eight target aura updates in combat")
end

function Diagnostics.StopAuraProbe()
    if probeRun then SaveProbe("manual")
    else print("|cff22e0ffForeverSynthwave|r: /fsrecon probe -- no active run") end
end

local HAS_CANACCESSVALUE = type(canaccessvalue) == "function"
local HAS_C_TIMER = type(C_Timer) == "table" and type(C_Timer.After) == "function"
local MAX_THREAT_RUNS = 10

-- Only `type()` and the two secrecy inspectors ever touch `v` directly; the
-- value itself is stored in a table (a legal operation on a secret) ONLY when
-- it is not secret, per this probe's own stricter rule for UnitName/UnitGUID.
local function RecordValue(v, noStoreValue)
    local secret = FS.IsSecret(v)
    local row = {
        type = type(v),
        secret = tostring(secret),
        access = HAS_CANACCESSVALUE and tostring(canaccessvalue(v)) or "n/a",
    }
    if not secret and not noStoreValue then
        row.value = v
    end
    return row
end

-- select('#', ...) over pcall's own return list, so a nil in the middle of a
-- multi-return (UnitDetailedThreatSituation) is counted instead of truncating
-- the table constructor early.
local function Pack(...)
    return select("#", ...), { ... }
end

local function BuildCallResult(n, packed, noStoreValue)
    if not packed[1] then
        return { ok = false, err = tostring(packed[2]) }
    end

    local results = {}
    for i = 2, n do
        results[#results + 1] = RecordValue(packed[i], noStoreValue)
    end
    return { ok = true, n = n - 1, results = results }
end

local function ProbeCall(fn, ...)
    if type(fn) ~= "function" then
        return { ok = false, err = "unavailable" }
    end
    return BuildCallResult(Pack(pcall(fn, ...)))
end

local function ProbeCallNoStore(fn, ...)
    if type(fn) ~= "function" then
        return { ok = false, err = "unavailable" }
    end
    local n, packed = Pack(pcall(fn, ...))
    return BuildCallResult(n, packed, true)
end

local HAS_GET_AURA_DATA_BY_INDEX = type(C_UnitAuras) == "table" and type(C_UnitAuras.GetAuraDataByIndex) == "function"
local HAS_ISSECRETTABLE = type(issecrettable) == "function"
local HAS_CANACCESSTABLE = type(canaccesstable) == "function"

local AURA_PROBE_FIELDS = {
    "name", "icon", "applications", "duration", "expirationTime",
    "sourceUnit", "spellId", "auraInstanceID", "isHarmful",
}

-- GetAuraDataByIndex returns a whole TABLE (or nil), not scalars, so
-- ProbeCall's select('#', ...) scalar path doesn't fit -- this is the
-- dedicated recorder that shape needs. A plain (non-secret-VALUE) table can
-- still be a secret TABLE, where indexing throws even though issecretvalue
-- says false -- issecrettable/canaccesstable gate the field loop for that
-- case, and each field read is its own pcall in case a stale client
-- disagrees with what those two flags claimed.
local function ProbeAuraCall(unit, filter)
    if not HAS_GET_AURA_DATA_BY_INDEX then
        return { ok = false, err = "unavailable" }
    end

    local ok, ret = pcall(C_UnitAuras.GetAuraDataByIndex, unit, 1, filter)
    if not ok then
        return { ok = false, err = type(ret) == "string" and ret or "non-string error" }
    end

    local row = { ok = true, retType = type(ret) }
    if type(ret) ~= "table" then
        return row
    end

    row.secret = tostring(FS.IsSecret(ret))
    if FS.IsSecret(ret) then
        return row
    end

    -- Explicit `if`, not `X and f(v) or default`: that idiom silently
    -- flips a legitimate `false` from f(v) to `default` whenever `default`
    -- is truthy, which is exactly backwards for an accessible-table flag.
    local secretTable = false
    if HAS_ISSECRETTABLE then
        secretTable = issecrettable(ret)
    end
    local accessTable = true
    if HAS_CANACCESSTABLE then
        accessTable = canaccesstable(ret)
    end
    row.secretTable = HAS_ISSECRETTABLE and tostring(secretTable) or "n/a"
    row.accessTable = HAS_CANACCESSTABLE and tostring(accessTable) or "n/a"
    if secretTable or not accessTable then
        return row
    end

    row.fields = {}
    for _, field in ipairs(AURA_PROBE_FIELDS) do
        local readOk, v = pcall(function() return ret[field] end)
        if not readOk then
            row.fields[field] = { err = type(v) == "string" and v or "non-string error" }
        else
            local secretField = FS.IsSecret(v)
            local fieldRow = {
                type = type(v),
                secret = tostring(secretField),
                access = HAS_CANACCESSVALUE and tostring(canaccessvalue(v)) or "n/a",
            }
            if not secretField and (type(v) == "number" or type(v) == "boolean") then
                fieldRow.value = v
            end
            row.fields[field] = fieldRow
        end
    end
    return row
end

local function ProbeUnit(unit)
    return {
        { api = "UnitThreatSituation('player', unit)", result = ProbeCall(UnitThreatSituation, "player", unit) },
        { api = "UnitThreatSituation('pet', unit)", result = ProbeCall(UnitThreatSituation, "pet", unit) },
        { api = "UnitDetailedThreatSituation('player', unit)",
          result = ProbeCall(UnitDetailedThreatSituation, "player", unit) },
        { api = "UnitDetailedThreatSituation('pet', unit)",
          result = ProbeCall(UnitDetailedThreatSituation, "pet", unit) },
        { api = "UnitThreatPercentageOfLead('player', unit)",
          result = ProbeCall(UnitThreatPercentageOfLead, "player", unit) },
        { api = "UnitReaction('player', unit)", result = ProbeCall(UnitReaction, "player", unit) },
        { api = "UnitReaction(unit, 'player')", result = ProbeCall(UnitReaction, unit, "player") },
        { api = "UnitCanAttack('player', unit)", result = ProbeCall(UnitCanAttack, "player", unit) },
        { api = "UnitIsTapDenied(unit)", result = ProbeCall(UnitIsTapDenied, unit) },
        { api = "UnitPowerType(unit)", result = ProbeCall(UnitPowerType, unit) },
        -- Confirms the cast bar's notInterruptible return position (documented
        -- as #8/#7 but UNVERIFIED on 16001 -- see ForeverSynthwave.lua).
        -- ProbeCall already records type/secret flags per index and only
        -- stores a value when it isn't secret, so this needs no special case.
        { api = "UnitCastingInfo(unit)", result = ProbeCall(UnitCastingInfo, unit) },
        { api = "UnitChannelInfo(unit)", result = ProbeCall(UnitChannelInfo, unit) },
        { api = "UnitName(unit)", result = ProbeCallNoStore(UnitName, unit) },
        { api = "UnitGUID(unit)", result = ProbeCallNoStore(UnitGUID, unit) },
        -- Deliberately NOT gated on FS.AurasReadable: the point of this pair
        -- is to measure whether enemy aura reads survive combat lockdown on
        -- 16001, and that's acceptable here (unlike Buffs.lua's ticker) since
        -- this only runs on demand or 2s into an armed pull, never a ticker.
        { api = "C_UnitAuras.GetAuraDataByIndex(unit, 1, 'HARMFUL|PLAYER')",
          result = ProbeAuraCall(unit, "HARMFUL|PLAYER") },
        { api = "C_UnitAuras.GetAuraDataByIndex(unit, 1, 'HARMFUL')",
          result = ProbeAuraCall(unit, "HARMFUL") },
    }
end

local function ProbeUnitFree()
    return {
        { api = "UnitGroupRolesAssigned('player')", result = ProbeCall(UnitGroupRolesAssigned, "player") },
        { api = "GetShapeshiftFormID()", result = ProbeCall(GetShapeshiftFormID) },
        { api = "IsInGroup()", result = ProbeCall(IsInGroup) },
        { api = "InCombatLockdown()", result = ProbeCall(InCombatLockdown) },
        { api = "UnitExists('pet')", result = ProbeCall(UnitExists, "pet") },
    }
end

-- Feature-detects BOTH the modern plate.namePlateUnitToken field and the
-- CompactUnitFrame-carried plate.UnitFrame.unit fallback, since which one a
-- given client populates is exactly the kind of thing this probe exists to
-- stop guessing about.
local function CollectNameplateUnits()
    local units = {}
    if not (C_NamePlate and C_NamePlate.GetNamePlates) then return units end

    local ok, plates = pcall(C_NamePlate.GetNamePlates)
    if not ok or type(plates) ~= "table" then return units end

    for _, plate in ipairs(plates) do
        local token = plate.namePlateUnitToken
        if not token and plate.UnitFrame then
            token = plate.UnitFrame.unit
        end
        if token then
            units[#units + 1] = token
        end
    end
    return units
end

local FIXED_THREAT_UNITS = { "target", "focus", "mouseover", "pet", "boss1" }

local function BuildThreatUnitList()
    local units = {}
    for _, u in ipairs(FIXED_THREAT_UNITS) do
        units[#units + 1] = u
    end
    for _, u in ipairs(CollectNameplateUnits()) do
        units[#units + 1] = u
    end
    return units
end

local function RunThreatProbeInner()
    local run = {
        t = time(),
        inCombat = InCombatLockdown() and true or false,
        rows = { { unit = "_global", calls = ProbeUnitFree() } },
    }

    for _, unit in ipairs(BuildThreatUnitList()) do
        local existsOk, exists = pcall(UnitExists, unit)
        if existsOk and exists then
            run.rows[#run.rows + 1] = { unit = unit, calls = ProbeUnit(unit) }
        end
    end

    return run
end

local function StoreThreatRun(run)
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.threat = ForeverSynthwaveDB.recon.threat or {}

    local runs = ForeverSynthwaveDB.recon.threat
    runs[#runs + 1] = run
    while #runs > MAX_THREAT_RUNS do
        table.remove(runs, 1)
    end
end

local function CountSecretReturns(run)
    local count = 0
    for _, unitRow in ipairs(run.rows) do
        for _, call in ipairs(unitRow.calls) do
            if call.result.results then
                for _, r in ipairs(call.result.results) do
                    if r.secret == "true" then
                        count = count + 1
                    end
                end
            end
        end
    end
    return count
end

local function DoThreatProbeRun()
    local run = RunThreatProbeInner()
    StoreThreatRun(run)

    print(("|cff22e0ffForeverSynthwave|r: /fsrecon threat -- %d run(s) stored, %d secret return(s) this run, %s")
        :format(#ForeverSynthwaveDB.recon.threat, CountSecretReturns(run),
            run.inCombat and "IN COMBAT" or "out of combat"))
end

-- The whole run is pcall'd, per this addon's isolation rule: a probe firing
-- off a live PLAYER_REGEN_DISABLED event must never take the rest of the
-- addon down with it.
function Diagnostics.RunThreatProbe()
    local ok, err = pcall(DoThreatProbeRun)
    if not ok then
        FS.LogDegradeOnce("fsrecon_threat_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon threat -- probe failed: %s"):format(tostring(err)))
    end
end

function Diagnostics.ClearThreatRuns()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.threat = {}
    print("|cff22e0ffForeverSynthwave|r: /fsrecon threat -- stored runs cleared.")
end

local threatAutoFrame
local threatAutoRemaining = 0

local function DisarmThreatAuto()
    if threatAutoFrame then
        threatAutoFrame:UnregisterEvent("PLAYER_REGEN_DISABLED")
    end
    threatAutoRemaining = 0
end

-- Event-driven only, no OnUpdate: a 2s C_Timer.After delay after combat
-- starts, so threat has actually had a moment to establish before capture.
local function OnThreatAutoCombatStart()
    if threatAutoRemaining <= 0 then return end

    if HAS_C_TIMER then
        C_Timer.After(2, Diagnostics.RunThreatProbe)
    else
        FS.LogDegradeOnce("fsrecon_threat_noctimer",
            "|cffff4488ForeverSynthwave|r: /fsrecon threat auto -- C_Timer unavailable, capturing immediately "
                .. "instead of the usual 2s in-combat delay.")
        Diagnostics.RunThreatProbe()
    end

    threatAutoRemaining = threatAutoRemaining - 1
    if threatAutoRemaining <= 0 then
        DisarmThreatAuto()
    end
end

function Diagnostics.ArmThreatAuto(n)
    n = (type(n) == "number" and n >= 1) and math.floor(n) or 3
    threatAutoRemaining = n

    if not threatAutoFrame then
        threatAutoFrame = CreateFrame("Frame")
        threatAutoFrame:SetScript("OnEvent", function()
            pcall(OnThreatAutoCombatStart)
        end)
    end
    threatAutoFrame:RegisterEvent("PLAYER_REGEN_DISABLED")

    print(("|cff22e0ffForeverSynthwave|r: /fsrecon threat auto -- armed for the next %d combat(s)."):format(n))
end

-------------------------------------------------------------------------------
-- /fsrecon pet -- pet-addon Phase-0 secret-value + availability probe
-------------------------------------------------------------------------------

-- Same measurement-over-guessing rationale as /fsrecon threat above: the pet
-- action bar/cast bar rebuild (Phase 1) hinges on seven open questions about
-- what this client's pet APIs actually hand back -- particularly whether a
-- pet's cast/channel timing is secret, which decides whether the pairing's
-- triangle cast bar can ever read a numeric progress fraction. Reuses every
-- probe primitive the threat probe above already built (RecordValue/Pack/
-- ProbeCall/ProbeCallNoStore) rather than duplicating them.

local MAX_PET_RUNS = 10

local HAS_XMLUTIL_TEMPLATE_INFO = type(C_XMLUtil) == "table" and type(C_XMLUtil.GetTemplateInfo) == "function"
local HAS_GET_VEHICLE_BAR_INDEX = type(C_ActionBar) == "table" and type(C_ActionBar.GetVehicleBarIndex) == "function"
local HAS_HAS_OVERRIDE_ACTION_BAR = type(HasOverrideActionBar) == "function"
local HAS_CAST_DURATION = type(UnitCastingDuration) == "function"
local HAS_CHANNEL_DURATION = type(UnitChannelDuration) == "function"

-- Q1: NUM_PET_ACTION_SLOTS is a plain global constant, not an API call, but
-- pcall'd anyway for defensive parity with every other probe in this file,
-- even though a plain global index is very unlikely to throw.
local function ProbePetActionSlotCount()
    local ok, v = pcall(function() return NUM_PET_ACTION_SLOTS end)
    if not ok then
        return { ok = false, err = tostring(v) }
    end
    local row = RecordValue(v)
    row.ok = true
    return row
end

-- Q2: the dead-pet gate. All three are read live in combat, where they are
-- the ones actually at risk of turning secret -- ProbeCall's RecordValue
-- already flags secrecy per this file's established pattern.
local function ProbeDeadPetGate()
    return {
        { api = "UnitExists('pet')", result = ProbeCall(UnitExists, "pet") },
        { api = "UnitIsDead('pet')", result = ProbeCall(UnitIsDead, "pet") },
        { api = "UnitIsFeignDeath('pet')", result = ProbeCall(UnitIsFeignDeath, "pet") },
    }
end

-- Q3: autocast overlay availability -- existence only, never attached to a
-- live frame (attaching would create/parent a real widget just to probe it,
-- which this diagnostic has no business doing). AutoCastOverlayMixin is a
-- plain Lua table global; AutoCastShineTemplate is an XML template, which
-- typically has no Lua global of its own -- checked anyway since a global
-- miss is itself informative and this stays cheap and non-attaching.
-- C_XMLUtil.GetTemplateInfo is a belt-and-suspenders second check when this
-- client has it (UNVERIFIED on 16001, hence the feature-detect).
local function ProbeAutocastOverlay()
    local row = {}

    local mixinOk, mixinType = pcall(function() return type(AutoCastOverlayMixin) end)
    row.mixin = mixinOk and mixinType or "error"

    local templateGlobalOk, templateGlobalType = pcall(function() return type(_G["AutoCastShineTemplate"]) end)
    row.templateGlobal = templateGlobalOk and templateGlobalType or "error"

    row.templateInfoApiAvailable = HAS_XMLUTIL_TEMPLATE_INFO
    if HAS_XMLUTIL_TEMPLATE_INFO then
        local ok, info = pcall(C_XMLUtil.GetTemplateInfo, "AutoCastShineTemplate")
        row.templateFound = ok and (info ~= nil)
        if not ok then
            row.templateFoundErr = tostring(info)
        end
    end

    return row
end

-- Q4 (THE gating probe): pet cast/channel timing secrecy. UnitCastingInfo/
-- UnitChannelInfo go through the exact same ProbeCall path the threat probe
-- uses for 'unit' above, unit fixed to "pet". UnitCastingDuration/
-- UnitChannelDuration are feature-detected separately and their return is a
-- DURATION OBJECT, not a scalar -- unlike everything else in this file it is
-- never stored (an object is not serializable into ForeverSynthwaveDB even
-- when not secret), only its type and secrecy flag.
local function ProbeDurationFn(fn, unit)
    if type(fn) ~= "function" then
        return { ok = false, err = "unavailable" }
    end
    local ok, obj = pcall(fn, unit)
    if not ok then
        return { ok = false, err = type(obj) == "string" and obj or "non-string error" }
    end
    return { ok = true, type = type(obj), secret = tostring(FS.IsSecret(obj)) }
end

local function ProbePetCastTiming()
    return {
        { api = "UnitCastingInfo('pet')", result = ProbeCall(UnitCastingInfo, "pet") },
        { api = "UnitChannelInfo('pet')", result = ProbeCall(UnitChannelInfo, "pet") },
        { api = "UnitCastingDuration('pet')", available = HAS_CAST_DURATION,
          result = ProbeDurationFn(UnitCastingDuration, "pet") },
        { api = "UnitChannelDuration('pet')", available = HAS_CHANNEL_DURATION,
          result = ProbeDurationFn(UnitChannelDuration, "pet") },
    }
end

-- Q5: pet action cooldown secrecy, same multi-return shape as everything
-- else ProbeCall already handles.
local function ProbePetCooldown()
    return { api = "GetPetActionCooldown(1)", result = ProbeCall(GetPetActionCooldown, 1) }
end

-- Q6: possess/vehicle bar. Feature-detect the two presence checks; capture
-- whatever GetPetActionInfo(1) hands back at run time (it answers for
-- whichever bar -- pet or vehicle override -- is actually active right now,
-- there is no way to force one or the other from outside combat).
local function ProbeVehicleState()
    return {
        hasVehicleBarIndexApi = HAS_GET_VEHICLE_BAR_INDEX,
        hasOverrideActionBarApi = HAS_HAS_OVERRIDE_ACTION_BAR,
        petActionInfo = ProbeCall(GetPetActionInfo, 1),
    }
end

-- Q7: whether the native PetActionButton HotKey regions are still reachable
-- (and at what alpha) -- confirms whether a SetAlpha(0) on the pet bar
-- itself actually reaches them, or whether they need their own suppression.
-- Read-only: no alpha is ever set here.
local function ProbeHotkeySuppression()
    local rows = {}
    for i = 1, 10 do
        local btn = _G["PetActionButton" .. i]
        local row = { index = i, buttonExists = btn ~= nil }
        if btn then
            if type(btn.GetAlpha) == "function" then
                local ok, alpha = pcall(btn.GetAlpha, btn)
                if ok then row.buttonAlpha = alpha end
            end
            local hotkey = btn.HotKey
            row.hotkeyExists = hotkey ~= nil
            if hotkey and type(hotkey.GetAlpha) == "function" then
                local ok, alpha = pcall(hotkey.GetAlpha, hotkey)
                if ok then row.hotkeyAlpha = alpha end
            end
        end
        rows[#rows + 1] = row
    end
    return rows
end

local function RunPetProbeInner()
    return {
        t = time(),
        inCombat = InCombatLockdown() and true or false,
        numPetActionSlots = ProbePetActionSlotCount(),
        deadPetGate = ProbeDeadPetGate(),
        autocastOverlay = ProbeAutocastOverlay(),
        castTiming = ProbePetCastTiming(),
        cooldown = ProbePetCooldown(),
        vehicle = ProbeVehicleState(),
        hotkeySuppression = ProbeHotkeySuppression(),
    }
end

local function StorePetRun(run)
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.pet = ForeverSynthwaveDB.recon.pet or {}

    local runs = ForeverSynthwaveDB.recon.pet
    runs[#runs + 1] = run
    while #runs > MAX_PET_RUNS do
        table.remove(runs, 1)
    end
end

-- The pet run's shape (named fields, not threat's per-unit rows list) does
-- not fit CountSecretReturns' row-walk above, so this counts secret flags by
-- walking the run generically instead of re-deriving a shape-specific walk.
local function CountPetSecretFlags(node, count)
    count = count or 0
    if type(node) ~= "table" then
        return count
    end
    if node.secret == "true" then
        count = count + 1
    end
    for _, v in pairs(node) do
        if type(v) == "table" then
            count = CountPetSecretFlags(v, count)
        end
    end
    return count
end

local function DoPetProbeRun()
    local run = RunPetProbeInner()
    StorePetRun(run)

    print(("|cff22e0ffForeverSynthwave|r: /fsrecon pet -- %d run(s) stored, %d secret return(s) this run, %s")
        :format(#ForeverSynthwaveDB.recon.pet, CountPetSecretFlags(run),
            run.inCombat and "IN COMBAT" or "out of combat"))
end

-- Same whole-run pcall isolation rule as RunThreatProbe: a probe firing off
-- a live PLAYER_REGEN_DISABLED event must never take the rest of the addon
-- down with it.
function Diagnostics.RunPetProbe()
    local ok, err = pcall(DoPetProbeRun)
    if not ok then
        FS.LogDegradeOnce("fsrecon_pet_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon pet -- probe failed: %s"):format(tostring(err)))
    end
end

function Diagnostics.ClearPetRuns()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.pet = {}
    print("|cff22e0ffForeverSynthwave|r: /fsrecon pet -- stored runs cleared.")
end

local petAutoFrame
local petAutoRemaining = 0

local function DisarmPetAuto()
    if petAutoFrame then
        petAutoFrame:UnregisterEvent("PLAYER_REGEN_DISABLED")
    end
    petAutoRemaining = 0
end

-- Event-driven only, no OnUpdate, same 2s-into-combat delay as
-- OnThreatAutoCombatStart -- captures probes 2, 4 and 5 (the combat-
-- sensitive ones) after pet/cast state has had a moment to establish.
local function OnPetAutoCombatStart()
    if petAutoRemaining <= 0 then return end

    if HAS_C_TIMER then
        C_Timer.After(2, Diagnostics.RunPetProbe)
    else
        FS.LogDegradeOnce("fsrecon_pet_noctimer",
            "|cffff4488ForeverSynthwave|r: /fsrecon pet auto -- C_Timer unavailable, capturing immediately "
                .. "instead of the usual 2s in-combat delay.")
        Diagnostics.RunPetProbe()
    end

    petAutoRemaining = petAutoRemaining - 1
    if petAutoRemaining <= 0 then
        DisarmPetAuto()
    end
end

function Diagnostics.ArmPetAuto(n)
    n = (type(n) == "number" and n >= 1) and math.floor(n) or 3
    petAutoRemaining = n

    if not petAutoFrame then
        petAutoFrame = CreateFrame("Frame")
        petAutoFrame:SetScript("OnEvent", function()
            pcall(OnPetAutoCombatStart)
        end)
    end
    petAutoFrame:RegisterEvent("PLAYER_REGEN_DISABLED")

    print(("|cff22e0ffForeverSynthwave|r: /fsrecon pet auto -- armed for the next %d combat(s)."):format(n))
end

-- Shared by /fsrecon surname and /fsrecon minimap below: wraps a single
-- captured value as `{ok, secret, value}`, where `value` is always a
-- tostring() (itself pcall'd -- a secret value's tostring() behavior is
-- unverified and must never throw out of a probe), never the raw value.
-- IsSecret is reported but never trusted for control flow here -- the only
-- operation performed on `v` itself is that pcall'd tostring() (same "don't
-- touch a possibly secret value directly" discipline as RecordValue above).
local function WrapReconValue(v)
    local secret = FS.IsSecret(v)
    local strOk, str = pcall(tostring, v)
    return { ok = true, secret = tostring(secret), value = strOk and str or "<tostring failed>" }
end

-- Shared call-and-wrap helper: pcalls a single-return getter and wraps the
-- result via WrapReconValue, or "<no API>" when the getter itself is absent.
local function ProbeReconField(fn, ...)
    if type(fn) ~= "function" then
        return { ok = true, secret = "false", value = "<no API>" }
    end
    local ok, ret = pcall(fn, ...)
    if not ok then
        return { ok = false, err = type(ret) == "string" and ret or "non-string error" }
    end
    return WrapReconValue(ret)
end

-- /fsrecon surname -- one-shot probe over the name-API family (UnitName's two
-- returns, GetUnitName's two boolean modes, UnitNameUnmodified if present,
-- UnitGUID) for "player" and "target", dispatched from PanelSkins.lua's
-- /fsrecon like threat/pet above. Unlike those, this has no auto/clear and no
-- run history -- it's a single lookup, so each run OVERWRITES
-- ForeverSynthwaveDB.recon.surname rather than appending.
local function ProbeSurnameUnit(unit)
    local row = { unit = unit, exists = UnitExists(unit) and true or false }
    if not row.exists then
        return row
    end

    -- UnitName returns two values (name, realm), so it needs its own pcall
    -- rather than ProbeReconField's single-return shape.
    local nameOk, name1, name2 = pcall(UnitName, unit)
    if nameOk then
        row.unitName_1 = WrapReconValue(name1)
        row.unitName_2 = WrapReconValue(name2)
    else
        local err = { ok = false, err = type(name1) == "string" and name1 or "non-string error" }
        row.unitName_1, row.unitName_2 = err, err
    end

    row.getUnitName_true = ProbeReconField(GetUnitName, unit, true)
    row.getUnitName_false = ProbeReconField(GetUnitName, unit, false)
    row.unitNameUnmodified = ProbeReconField(UnitNameUnmodified, unit)
    row.guid = ProbeReconField(UnitGUID, unit)

    return row
end

local SURNAME_UNITS = { "player", "target" }

local function DoSurnameProbeRun()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}

    local captured = {}
    for _, unit in ipairs(SURNAME_UNITS) do
        captured[unit] = ProbeSurnameUnit(unit)
    end
    ForeverSynthwaveDB.recon.surname = captured
end

-- Same whole-run pcall isolation rule as RunThreatProbe/RunPetProbe: a probe
-- fired from a slash command must never take the rest of the addon down. The
-- confirmation print lives here rather than in DoSurnameProbeRun itself so
-- /fsrecon all (below) can run the capture without it, for one combined line.
function Diagnostics.RunSurnameProbe()
    local ok, err = pcall(DoSurnameProbeRun)
    if not ok then
        FS.LogDegradeOnce("fsrecon_surname_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon surname -- probe failed: %s"):format(tostring(err)))
        return
    end
    print("|cff22e0ffForeverSynthwave|r: /fsrecon surname -- captured, /fsreload to flush")
end

-- /fsrecon minimap -- one-shot probe over Minimap/MinimapCluster geometry
-- (size, anchor point, scale, shape shim, fsPlaced marker), since a container
-- can reserve space its hidden children don't give back -- see the
-- frame-recon note on MinimapCluster's header strip. Same one-shot-overwrite
-- shape as /fsrecon surname above: no auto/clear, no run history.
local function ProbeMinimapSize(frame, wKey, hKey, row)
    if type(frame) ~= "table" or type(frame.GetSize) ~= "function" then
        row[wKey] = { ok = true, secret = "false", value = "<no API>" }
        row[hKey] = { ok = true, secret = "false", value = "<no API>" }
        return
    end
    local ok, w, h = pcall(frame.GetSize, frame)
    if not ok then
        local err = { ok = false, err = type(w) == "string" and w or "non-string error" }
        row[wKey], row[hKey] = err, err
        return
    end
    row[wKey] = WrapReconValue(w)
    row[hKey] = WrapReconValue(h)
end

-- GetPoint(1) hands back 5 values at once (point/relTo/relPoint/x/y), so it
-- gets its own composite row rather than fitting ProbeReconField's
-- single-return shape. relTo is a FRAME reference, not a scalar -- resolved
-- to its name (or a placeholder) before it ever reaches WrapReconValue, since
-- tostring() on a frame object is a useless pointer string, not the name
-- read back off disk.
local function ProbeMinimapPoint(frame)
    if type(frame) ~= "table" or type(frame.GetPoint) ~= "function" then
        return { ok = true, secret = "false", value = "<no API>" }
    end

    local ok, point, relTo, relPoint, x, y = pcall(frame.GetPoint, frame, 1)
    if not ok then
        return { ok = false, err = type(point) == "string" and point or "non-string error" }
    end

    local relToName = "<nil>"
    if type(relTo) == "table" then
        local nameOk, name = pcall(function() return relTo.GetName and relTo:GetName() end)
        -- Explicit `if`, not `nameOk and name or "<unnamed>"`: GetName can
        -- legitimately return nil for an anonymous frame, and that idiom
        -- would silently replace a genuine nil with the placeholder even
        -- when nameOk is true -- moot today (name is nil, not false, so the
        -- `or` still fires correctly), but kept explicit per this file's
        -- established and/or-with-a-real-default rule (see ProbeAuraCall).
        if nameOk and name then
            relToName = name
        else
            relToName = "<unnamed>"
        end
    end

    return {
        ok = true,
        point = WrapReconValue(point),
        relTo = WrapReconValue(relToName),
        relPoint = WrapReconValue(relPoint),
        x = WrapReconValue(x),
        y = WrapReconValue(y),
    }
end

local function DoMinimapProbeRun()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}

    local row = {}
    ProbeMinimapSize(Minimap, "mw", "mh", row)
    ProbeMinimapSize(MinimapCluster, "cw", "ch", row)
    row.minimapPoint = ProbeMinimapPoint(Minimap)
    row.clusterPoint = ProbeMinimapPoint(MinimapCluster)

    local fsPlaced = nil
    if type(Minimap) == "table" then
        fsPlaced = Minimap.fsPlaced
    end
    row.fsPlaced = WrapReconValue(fsPlaced)

    row.minimapScale = ProbeReconField(function() return Minimap:GetEffectiveScale() end)
    row.clusterScale = ProbeReconField(function() return MinimapCluster:GetEffectiveScale() end)
    row.minimapShape = ProbeReconField(function()
        if type(GetMinimapShape) ~= "function" then
            return "<no shim>"
        end
        return GetMinimapShape() or "<no shim>"
    end)
    row.parent = ProbeReconField(function()
        local parent = Minimap:GetParent()
        if parent and type(parent.GetName) == "function" then
            return parent:GetName() or "<unnamed>"
        end
        return "<unnamed>"
    end)

    ForeverSynthwaveDB.recon.minimap = row
end

-- Same whole-run pcall isolation rule as the other /fsrecon probes. The
-- confirmation print lives here rather than in DoMinimapProbeRun itself so
-- /fsrecon all (below) can run the capture without it, for one combined line.
function Diagnostics.RunMinimapProbe()
    local ok, err = pcall(DoMinimapProbeRun)
    if not ok then
        FS.LogDegradeOnce("fsrecon_minimap_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon minimap -- probe failed: %s"):format(tostring(err)))
        return
    end
    print("|cff22e0ffForeverSynthwave|r: /fsrecon minimap -- captured, /fsreload to flush")
end

-------------------------------------------------------------------------------
-- /fsrecon minimap paint|spill|clear -- read-only bounds and reserved space
-------------------------------------------------------------------------------

local minimapBoundsOverlay
local minimapBoundsMarks = {}

local function MinimapPlain(value, kind)
    local info = ProbeValue(value)
    return not info.err and not info.secret and info.access ~= false and type(value) == kind
end

local function MinimapNumber(value)
    return MinimapPlain(value, "number") and value == value and math.abs(value) < math.huge
end

local function MinimapBoundsCall(object, key, ...)
    local ok, method = pcall(function() return object[key] end)
    if not ok then return false, "method lookup refused" end
    if type(method) ~= "function" then return false, "method unavailable" end
    local n, values = Pack(pcall(method, object, ...))
    if not values[1] then return false, "method refused" end
    return unpack(values, 1, n)
end

local function MinimapReadable(object)
    if not (MinimapPlain(object, "table") or MinimapPlain(object, "userdata")) then return false end
    local ok, forbidden = MinimapBoundsCall(object, "IsForbidden")
    if not ok then return forbidden == "method unavailable" end
    return MinimapPlain(forbidden, "boolean") and not forbidden
end

local function MinimapBoundsName(object)
    if not MinimapReadable(object) then return "<unavailable>" end
    local ok, name = MinimapBoundsCall(object, "GetName")
    if ok and MinimapPlain(name, "string") then return name:sub(1, 160) end
    return "<anonymous>"
end

local function MinimapBoundsParent(object)
    local ok, parent = MinimapBoundsCall(object, "GetParent")
    if not ok then return nil, false end
    if MinimapPlain(parent, "nil") then return nil, true end
    if not MinimapReadable(parent) then return nil, false end
    return parent, true
end

local function MinimapBoundsScale(object)
    local seen = {}
    for _ = 1, MINIMAP_PARENT_LIMIT do
        if not MinimapReadable(object) or seen[object] then return nil, "unavailable scale" end
        seen[object] = true
        local ok, scale = MinimapBoundsCall(object, "GetEffectiveScale")
        if ok then
            if MinimapNumber(scale) and scale > 0 then return scale end
            return nil, "secret or invalid scale"
        end
        if scale ~= "method unavailable" then return nil, scale end
        local parent, readable = MinimapBoundsParent(object)
        if not readable or not parent then return nil, "unavailable scale" end
        object = parent
    end
    return nil, "scale parent limit"
end

local function MinimapBoundsRect(object, uiScale)
    if not MinimapReadable(object) then return nil, "forbidden or inaccessible" end
    local ok, left, bottom, width, height = MinimapBoundsCall(object, "GetRect")
    if not ok then
        if left ~= "method unavailable" then return nil, left end
        local leftOk, edgeLeft = MinimapBoundsCall(object, "GetLeft")
        local rightOk, edgeRight = MinimapBoundsCall(object, "GetRight")
        local topOk, edgeTop = MinimapBoundsCall(object, "GetTop")
        local bottomOk, edgeBottom = MinimapBoundsCall(object, "GetBottom")
        if not (leftOk and rightOk and topOk and bottomOk) then return nil, "edge getters unavailable" end
        if not (MinimapNumber(edgeLeft) and MinimapNumber(edgeRight)
            and MinimapNumber(edgeTop) and MinimapNumber(edgeBottom)) then return nil, "secret or unresolved edges" end
        left, bottom = edgeLeft, edgeBottom
        width, height = edgeRight - edgeLeft, edgeTop - edgeBottom
    end
    if not (MinimapNumber(left) and MinimapNumber(bottom) and MinimapNumber(width) and MinimapNumber(height)) then
        return nil, "secret or unresolved rect"
    end
    if width <= 0 or height <= 0 then return nil, "nonpositive rect" end
    local scale, err = MinimapBoundsScale(object)
    if not scale then return nil, err end
    local ratio = scale / uiScale
    local rect = { left = left * ratio, bottom = bottom * ratio, width = width * ratio, height = height * ratio }
    rect.right = rect.left + rect.width
    rect.top = rect.bottom + rect.height
    for _, value in pairs(rect) do
        if not MinimapNumber(value) then return nil, "nonfinite normalized rect" end
    end
    return rect, nil, scale
end

-- Texture effective alpha is unreliable here; inspect guarded ancestor alpha.
local function MinimapBoundsAlpha(object)
    local alpha, seen = 1, {}
    for _ = 1, MINIMAP_PARENT_LIMIT do
        if not MinimapReadable(object) or seen[object] then return nil, "inaccessible or cyclic ancestry" end
        seen[object] = true
        local shownOk, shown = MinimapBoundsCall(object, "IsShown")
        if not shownOk or not MinimapPlain(shown, "boolean") then return nil, "unknown ancestor visibility" end
        if not shown then return 0 end
        local ok, ownAlpha = MinimapBoundsCall(object, "GetAlpha")
        if not ok or not MinimapNumber(ownAlpha) or ownAlpha < 0 or ownAlpha > 1 then
            return nil, "unknown ancestor alpha"
        end
        alpha = alpha * ownAlpha
        if alpha == 0 then return 0 end
        local parent, readable = MinimapBoundsParent(object)
        if not readable then return nil, "unknown parent" end
        if not parent then return alpha end
        object = parent
    end
    return nil, "alpha parent limit"
end

local function MinimapBoundsPoint(object)
    local ok, point, relative, relativePoint, x, y = MinimapBoundsCall(object, "GetPoint", 1)
    if not ok or not MinimapPlain(point, "string") or not MinimapPlain(relativePoint, "string")
        or not MinimapNumber(x) or not MinimapNumber(y) then return nil end
    return { point = point, relative = MinimapBoundsName(relative), relativePoint = relativePoint,
        x = x, y = y, coordinates = "native anchor offsets" }
end

local function ClearMinimapBoundsMarks()
    for _, mark in ipairs(minimapBoundsMarks) do mark:Hide() end
end

local function PaintMinimapBounds(run, mode)
    if not minimapBoundsOverlay then
        minimapBoundsOverlay = CreateFrame("Frame", nil, UIParent)
        minimapBoundsOverlay:SetAllPoints(UIParent)
        minimapBoundsOverlay:SetFrameStrata("TOOLTIP")
        minimapBoundsOverlay:EnableMouse(false)
    end
    local used = 0
    local function Edge(left, bottom, right, top, color)
        used = used + 1
        local mark = minimapBoundsMarks[used]
        if not mark then
            mark = minimapBoundsOverlay:CreateTexture(nil, "OVERLAY")
            minimapBoundsMarks[used] = mark
        end
        mark:ClearAllPoints()
        mark:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", left, bottom)
        mark:SetPoint("TOPRIGHT", UIParent, "BOTTOMLEFT", right, top)
        mark:SetColorTexture(color[1], color[2], color[3], 0.9)
        mark:Show()
    end
    for i, row in ipairs(run.rows) do
        local rect = row.rect
        if rect and (mode == "paint" or row.spill) then
            local color = MINIMAP_BOUNDS_PALETTE[((i - 1) % #MINIMAP_BOUNDS_PALETTE) + 1]
            if row.spill then color = { 1, 0, 0 } end
            if row.alphaState ~= "known" then color = { 1, 0.65, 0 } end
            if row.shown == false or row.effectiveAlpha == 0 then color = { 0.5, 0.5, 0.5 } end
            local thickness = math.min(2, rect.width / 2, rect.height / 2)
            Edge(rect.left, rect.bottom, rect.right, rect.bottom + thickness, color)
            Edge(rect.left, rect.top - thickness, rect.right, rect.top, color)
            Edge(rect.left, rect.bottom, rect.left + thickness, rect.top, color)
            Edge(rect.right - thickness, rect.bottom, rect.right, rect.top, color)
        end
    end
    run.painted = used / 4
end

local function CaptureMinimapBounds(mode)
    local uiScale = MinimapBoundsScale(UIParent)
    if not uiScale then return nil, "UIParent scale unavailable" end
    local uiRect, uiErr = MinimapBoundsRect(UIParent, uiScale)
    if not uiRect then return nil, uiErr end
    local mapRect, mapErr = MinimapBoundsRect(Minimap, uiScale)
    local cluster = _G["MinimapCluster"]
    local clusterRect, clusterErr = MinimapBoundsRect(cluster, uiScale)
    local run = {
        version = 1, mode = mode, coordinates = "UIParent units", uiScale = uiScale,
        uiParent = uiRect, map = mapRect, mapError = mapErr, cluster = clusterRect, clusterError = clusterErr,
        rows = {}, skips = {}, visited = 0, attempted = 0, spills = 0,
        limits = { depth = MINIMAP_BOUNDS_DEPTH, nodes = MINIMAP_BOUNDS_NODES, parentDepth = MINIMAP_PARENT_LIMIT },
    }
    if mapRect then
        local margin = uiRect.top - mapRect.top
        if MinimapNumber(margin) then run.topMargin = margin end
    end
    if clusterRect and mapRect then
        local header, left = clusterRect.top - mapRect.top, mapRect.left - clusterRect.left
        if MinimapNumber(header) then run.headerInset = header end
        if MinimapNumber(left) then run.leftInset = left end
    end

    local furniture = {}
    if MinimapReadable(Minimap) then
        for _, key in ipairs({ "fsBezel", "fsTray" }) do
            local ok, object = pcall(function() return Minimap[key] end)
            if ok and MinimapReadable(object) then furniture[object] = key end
        end
    end
    local visited, expanded = {}, {}
    local function Skip(path, reason)
        if #run.skips < MINIMAP_BOUNDS_NODES then
            run.skips[#run.skips + 1] = { path = path, reason = reason }
        else
            run.skipLimit = true
        end
    end
    local function Sample(object, path, category)
        if run.attempted >= MINIMAP_BOUNDS_NODES then run.nodeLimit = true; return false end
        run.attempted = run.attempted + 1
        if not MinimapReadable(object) then Skip(path, "forbidden or inaccessible"); return false end
        category = furniture[object] or category
        if visited[object] then return true end
        visited[object] = true
        run.visited = run.visited + 1
        local row = { name = MinimapBoundsName(object), path = path, category = category }
        local typeOk, objectType = MinimapBoundsCall(object, "GetObjectType")
        if typeOk and MinimapPlain(objectType, "string") then row.type = objectType end
        local parent, readable = MinimapBoundsParent(object)
        row.parent = MinimapBoundsName(parent)
        if not readable then row.parentError = "unavailable parent" end
        local shownOk, shown = MinimapBoundsCall(object, "IsShown")
        if shownOk and MinimapPlain(shown, "boolean") then row.shown = shown end
        local alpha, alphaError = MinimapBoundsAlpha(object)
        row.effectiveAlpha = alpha
        row.alphaState = alphaError or "known"
        row.rect, row.rectError, row.scale = MinimapBoundsRect(object, uiScale)
        row.point = MinimapBoundsPoint(object)
        if row.rectError then Skip(path, row.rectError) end
        if row.rect and mapRect then
            local rect = row.rect
            local overhang = math.max(mapRect.left - rect.left, rect.right - mapRect.right,
                rect.top - mapRect.top, mapRect.bottom - rect.bottom, 0)
            if MinimapNumber(overhang) then
                row.overhang = overhang
                row.spill = overhang > 0.5
            else
                Skip(path, "nonfinite overhang")
            end
            if row.spill then
                run.spills = run.spills + 1
                row.spillKind = "outside map bounds"
                if category == "fsBezel" or category == "fsTray" then row.spillKind = "custom furniture" end
            end
        end
        run.rows[#run.rows + 1] = row
        return true
    end
    local function Walk(object, depth, path, category)
        if depth > MINIMAP_BOUNDS_DEPTH then run.depthLimit = true; return end
        if not Sample(object, path, category) or expanded[object] then return end
        category = furniture[object] or category
        expanded[object] = true
        if object == UIParent or object == minimapBoundsOverlay then return end
        if depth == MINIMAP_BOUNDS_DEPTH then run.depthLimit = true; return end
        for _, getter in ipairs({ "GetRegions", "GetChildren" }) do
            local n, values = Pack(MinimapBoundsCall(object, getter))
            if values[1] then
                for i = 2, n do
                    if run.attempted >= MINIMAP_BOUNDS_NODES then run.nodeLimit = true; return end
                    Walk(values[i], depth + 1, path .. "/" .. getter .. "[" .. (i - 1) .. "]", category)
                end
            elseif values[2] ~= "method unavailable" then
                Skip(path .. "/" .. getter, values[2])
            end
        end
    end

    Walk(cluster, 0, "MinimapCluster", "native cluster")
    Walk(Minimap, 0, "Minimap", "map")
    for object, category in pairs(furniture) do Walk(object, 0, "Minimap." .. category, category) end
    for _, root in ipairs({ Minimap, cluster }) do
        local object, seen = root, {}
        for depth = 1, MINIMAP_PARENT_LIMIT do
            if not MinimapReadable(object) or seen[object] then break end
            seen[object] = true
            local parent, readable = MinimapBoundsParent(object)
            if not readable or not parent then break end
            if not Sample(parent, "parent[" .. depth .. "] of " .. MinimapBoundsName(root), "ancestor") then break end
            if parent == UIParent then break end
            object = parent
            if depth == MINIMAP_PARENT_LIMIT then run.parentLimit = true end
        end
    end
    return run
end

function Diagnostics.RunMinimapBounds(mode)
    ClearMinimapBoundsMarks()
    if mode == "clear" or mode == "paintoff" then
        print("|cff22e0ffForeverSynthwave|r: minimap bounds outlines cleared; capture retained")
        return
    end
    if mode ~= "paint" and mode ~= "spill" then return end
    local ok, run, err = pcall(CaptureMinimapBounds, mode)
    if not ok or not run then
        print("|cffff4488ForeverSynthwave|r: minimap bounds capture unavailable: " .. (ok and err or "capture refused"))
        return
    end
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.minimapBounds = run
    local painted = pcall(PaintMinimapBounds, run, mode)
    if not painted then ClearMinimapBoundsMarks(); run.paintError = "overlay unavailable" end
    print(("|cff22e0ffForeverSynthwave|r: minimap bounds -- %d nodes, %d outside map, %d skips; " ..
        "grey hidden, amber unknown alpha, red visible spill (custom furniture identified in capture)")
        :format(run.visited, run.spills, #run.skips))
    print("|cff22e0ffForeverSynthwave|r: stored recon.minimapBounds; /fsreload to flush, minimap clear removes outlines")
end

-------------------------------------------------------------------------------
-- /fsrecon plateauras -- are Blizzard's own nameplate aura icons populated
-- while our code hides the stock plate?
-------------------------------------------------------------------------------

-- Background: addon-tainted aura reads are refused in combat, but Blizzard's
-- own (secure) NamePlateUnitFrame still runs its AurasFrame (build 1.60.1.70009
-- source: Blizzard_NamePlates.xml parentKey chain UnitFrame.AurasFrame with
-- DebuffListFrame / BuffListFrame / CrowdControlListFrame / LossOfControlFrame,
-- items acquired from AurasFrame.auraItemFramePool, each with .Icon /
-- .CountFrame.Count / .Cooldown). ForeverSynthwave.lua Hide()s that UnitFrame,
-- so this answers whether the child icons are still populated underneath.
--
-- STRICTLY READ-ONLY: every method call is a getter, pcall'd, and every
-- returned value is FS.IsSecret-checked before it is stored or compared (a
-- secret is stored as the string "<secret>"). Nothing is shown, hidden,
-- reparented or modified, and no protected function is called, so it is safe
-- to run mid-fight. Results: ForeverSynthwaveDB.recon.plateauras.runs
-- (newest last, capped at PLATEAURAS_MAX_RUNS).

local PLATEAURAS_MAX_RUNS = 4
local PLATEAURAS_MAX_DEPTH = 6
local PLATEAURAS_MAX_NODES = 300 -- total budget per snapshot, split across plates
local PLATEAURAS_MAX_PLATES = 3
local PLATEAURAS_MAX_REGIONS = 16 -- regions described per frame
local PLATEAURAS_MAX_KEYS = 24
local PLATEAURAS_MAX_CHILDREN = 64 -- children queued per frame
local PLATEAURAS_MAX_STR = 48
local PLATEAURAS_MAX_NAME = 120
local PLATEAURAS_CVARS = {
    "nameplateShowDebuffs", "nameplateShowBuffs",
    "nameplateShowOnlyNameForFriendlyPlayerUnits", "nameplateMotion",
}
-- Non-widget tables on AurasFrame worth a size readback (priority tables and
-- the frame pool); counted by pairs(), never indexed into.
local PLATEAURAS_TABLE_KEYS = { "buffList", "debuffList", "crowdControlList", "auraItemFramePool" }
local PLATEAURAS_AURA_WORDS = { "buff", "aura" } -- "debuff" contains "buff"

-- One plain scalar for storage: secret -> "<secret>", string -> truncated,
-- number/boolean/nil kept, anything else -> its type name.
local function PlateAurasScalar(v, keepTail)
    local ok, secret = pcall(FS.IsSecret, v)
    if not ok or secret then return "<secret>" end
    local t = type(v)
    if t == "string" then
        -- Debug names keep their TAIL (the leaf key is the informative part).
        if keepTail and #v > PLATEAURAS_MAX_NAME then return "..." .. v:sub(-PLATEAURAS_MAX_NAME) end
        if not keepTail and #v > PLATEAURAS_MAX_STR then return v:sub(1, PLATEAURAS_MAX_STR) .. "..." end
        return v
    end
    if t == "number" or t == "boolean" or t == "nil" then return v end
    return "<" .. t .. ">"
end

-- Calls obj:method(...) under pcall and returns (ok, packedCount, packedTable).
-- Missing method -> ok=false. All returns go through Pack so a nil in the
-- middle (GetChildren) can't truncate the list.
local function PlateAurasCall(obj, method, ...)
    local fOk, fn = pcall(function() return obj[method] end)
    if not fOk or type(fn) ~= "function" then return false, 0, {} end
    local n, packed = Pack(pcall(fn, obj, ...))
    if not packed[1] then return false, 0, {} end
    local vals = {}
    for i = 2, n do vals[i - 1] = packed[i] end
    return true, n - 1, vals
end

local function PlateAurasGet(obj, method, keepTail)
    local ok, n, vals = PlateAurasCall(obj, method)
    if not ok or n < 1 then return nil end
    return PlateAurasScalar(vals[1], keepTail)
end

local function PlateAurasName(obj)
    local name = PlateAurasGet(obj, "GetDebugName", true)
    if name == nil then name = PlateAurasGet(obj, "GetName", true) end
    if name == nil then return "<anonymous>" end
    return name
end

local function PlateAurasIsWidget(v)
    if type(v) ~= "table" then return false end
    local ok, fn = pcall(function() return v.GetObjectType end)
    return ok and type(fn) == "function"
end

local function PlateAurasAuraName(name)
    if type(name) ~= "string" then return false end
    local low = name:lower()
    for _, word in ipairs(PLATEAURAS_AURA_WORDS) do
        if low:find(word, 1, true) then return true end
    end
    return false
end

-- Widget-valued keys on a frame (BuffFrame, AurasFrame, DebuffListFrame ...)
-- plus size readbacks for the known non-widget aura tables. Every widget key
-- is collected first, then sorted (aura/buff/debuff-named first, then
-- alphabetical), and only then truncated, so pairs() order can never drop
-- AurasFrame. Stored names are truncated to PLATEAURAS_MAX_STR.
local function PlateAurasKeys(obj)
    local keys, known = {}, nil
    pcall(function()
        local all = {}
        for k, v in pairs(obj) do
            if type(k) == "string" and PlateAurasIsWidget(v) then
                local sOk, secret = pcall(FS.IsSecret, k)
                if sOk and not secret then all[#all + 1] = k end
            end
        end
        table.sort(all, function(a, b)
            local aa, ba = PlateAurasAuraName(a), PlateAurasAuraName(b)
            if aa ~= ba then return aa end
            return a < b
        end)
        for i = 1, math.min(#all, PLATEAURAS_MAX_KEYS) do
            keys[i] = PlateAurasScalar(all[i])
        end
        for _, k in ipairs(PLATEAURAS_TABLE_KEYS) do
            local v = rawget(obj, k)
            if type(v) == "table" and not PlateAurasIsWidget(v) then
                known = known or {}
                local row = {}
                local cOk, count = pcall(function()
                    local c = 0
                    for _ in pairs(v) do c = c + 1 end
                    return c
                end)
                row.keyCount = cOk and count or "<error>"
                local aOk, active = pcall(function() return v.GetNumActive and v:GetNumActive() end)
                if aOk then
                    local activeScalar = PlateAurasScalar(active)
                    if activeScalar ~= nil then row.numActive = activeScalar end
                end
                known[k] = row
            end
        end
    end)
    if #keys == 0 then keys = nil end
    return keys, known
end

-- Describes one node. `kind` is "frame" or "region".
local function PlateAurasDescribe(obj, kind)
    local node = { name = PlateAurasName(obj), kind = kind }
    node.objType = PlateAurasGet(obj, "GetObjectType")
    node.shown = PlateAurasGet(obj, "IsShown")
    node.visible = PlateAurasGet(obj, "IsVisible")
    node.alpha = PlateAurasGet(obj, "GetAlpha")

    local pOk, pn, pv = PlateAurasCall(obj, "GetParent")
    if pOk and pn >= 1 and type(pv[1]) == "table" then node.parent = PlateAurasName(pv[1]) end

    if kind == "frame" then
        node.keys, node.known = PlateAurasKeys(obj)
    end

    if node.objType == "Texture" or node.objType == "MaskTexture" then
        local tOk, tn, tv = PlateAurasCall(obj, "GetTexture")
        if tOk and tn >= 1 then
            node.texType = type(tv[1])
            node.texture = PlateAurasScalar(tv[1])
        end
        local fOk, fn, fv = PlateAurasCall(obj, "GetTextureFileID")
        if fOk and fn >= 1 then node.fileID = PlateAurasScalar(fv[1]) end
        node.atlas = PlateAurasGet(obj, "GetAtlas")
    elseif node.objType == "FontString" then
        node.text = PlateAurasGet(obj, "GetText")
    end
    return node
end

-- Breadth-first over FRAMES under a node budget, so the budget spreads over
-- the tree instead of draining into the first branch. Frames whose debug name
-- looks aura-related are visited before the rest (see the two queues below).
-- A frame's regions are leaves described when the frame is visited (at most
-- PLATEAURAS_MAX_REGIONS each; the full count is still recorded) so a
-- texture-heavy frame can't starve the deeper frames. Work is bounded: at most
-- PLATEAURAS_MAX_CHILDREN children are queued per frame (aura-named first),
-- and never more than the remaining budget can visit. Every child's debug name
-- is read once to sort it, so the sort cost is the frame's child count.
-- `seen` is shared per snapshot so the plate's own one-level pass and the
-- UnitFrame pass never double-count.
local function PlateAurasWalk(root, maxDepth, budget, seen, out)
    -- Two queues: frames whose debug name looks aura-related (the whole
    -- AurasFrame subtree, since a debug name carries its full path) are
    -- visited first, so the budget can't be eaten by unrelated siblings.
    local prio, normal = {}, { { root, 0 } }
    local prioHead, normalHead = 1, 1
    local pending = 1 -- queued entries not yet visited
    local used = 0
    local dropped = false
    while used < budget do
        local entry
        if prioHead <= #prio then
            entry = prio[prioHead]
            prioHead = prioHead + 1
        elseif normalHead <= #normal then
            entry = normal[normalHead]
            normalHead = normalHead + 1
        else
            break
        end
        pending = pending - 1
        local obj, depth = entry[1], entry[2]
        if not seen[obj] then
            seen[obj] = true
            used = used + 1
            local node = PlateAurasDescribe(obj, "frame")
            node.depth = depth

            local nChildren, nRegions = 0, 0
            local children, regions = {}, {}
            local cOk, cn, cv = PlateAurasCall(obj, "GetChildren")
            if cOk then nChildren, children = cn, cv end
            local rOk, rn, rv = PlateAurasCall(obj, "GetRegions")
            if rOk then nRegions, regions = rn, rv end
            node.numChildren, node.numRegions = nChildren, nRegions
            out[#out + 1] = node

            if depth < maxDepth then
                for i = 1, math.min(nRegions, PLATEAURAS_MAX_REGIONS) do
                    local region = regions[i]
                    if used >= budget then break end
                    if type(region) == "table" and not seen[region] then
                        seen[region] = true
                        used = used + 1
                        local rnode = PlateAurasDescribe(region, "region")
                        rnode.depth = depth + 1
                        out[#out + 1] = rnode
                    end
                end
                if nChildren > PLATEAURAS_MAX_CHILDREN then dropped = true end
                -- Partition ALL of this frame's children first (aura-named
                -- before the rest), then enqueue in that order under the budget
                -- and the per-frame cap, so a late aura-named child is never
                -- starved by earlier normal siblings, even past the cap.
                local newPrio, newNormal = {}, {}
                for i = 1, nChildren do
                    local child = children[i]
                    if type(child) == "table" then
                        local target = PlateAurasAuraName(PlateAurasName(child)) and newPrio or newNormal
                        target[#target + 1] = child
                    end
                end
                local queuedHere = 0
                for _, group in ipairs({ newPrio, newNormal }) do
                    local queue = (group == newPrio) and prio or normal
                    for _, child in ipairs(group) do
                        -- A queued entry past the remaining budget could never
                        -- be visited, so stop queueing once it is full.
                        if used + pending >= budget or queuedHere >= PLATEAURAS_MAX_CHILDREN then
                            dropped = true
                            break
                        end
                        queue[#queue + 1] = { child, depth + 1 }
                        pending = pending + 1
                        queuedHere = queuedHere + 1
                    end
                end
            end
        end
    end
    out.truncated = out.truncated or dropped or (prioHead <= #prio) or (normalHead <= #normal)
    return used
end

local function PlateAurasSummary(plates)
    local s = {
        auraFramesShown = 0, auraTexturesShown = 0, auraTexturesVisible = 0,
        auraTexturesWithTexture = 0, auraIconsShown = 0, auraTextures = 0,
    }
    for _, plate in ipairs(plates) do
        for _, node in ipairs(plate.nodes) do
            local isAura = PlateAurasAuraName(node.name)
            if isAura and node.kind == "frame" and node.shown == true then
                s.auraFramesShown = s.auraFramesShown + 1
            end
            if isAura and (node.objType == "Texture") then
                s.auraTextures = s.auraTextures + 1
                if node.shown == true then s.auraTexturesShown = s.auraTexturesShown + 1 end
                if node.visible == true then s.auraTexturesVisible = s.auraTexturesVisible + 1 end
                if node.shown == true and node.texture ~= nil then
                    s.auraTexturesWithTexture = s.auraTexturesWithTexture + 1
                    if type(node.name) == "string" and node.name:match("%.Icon$") then
                        s.auraIconsShown = s.auraIconsShown + 1
                    end
                end
            end
        end
    end
    return s
end

local function PlateAurasContext()
    local ctx = { time = time() }
    local okC, combat = pcall(UnitAffectingCombat, "player")
    ctx.unitAffectingCombat = okC and PlateAurasScalar(combat) or "<error>"
    local okL, lockdown = pcall(InCombatLockdown)
    ctx.inCombatLockdown = okL and PlateAurasScalar(lockdown) or "<error>"
    ctx.cvars = {}
    for _, name in ipairs(PLATEAURAS_CVARS) do
        local ok, value = pcall(GetCVar, name)
        ctx.cvars[name] = ok and PlateAurasScalar(value) or "<error>"
    end
    return ctx
end

local function PlateAurasPickPlates()
    local picked, mode = {}, "none"
    if not (C_NamePlate and C_NamePlate.GetNamePlateForUnit) then return picked, "no C_NamePlate" end
    local ok, plate = pcall(C_NamePlate.GetNamePlateForUnit, "target")
    if ok and plate then
        picked[1] = plate
        return picked, "target"
    end
    local lOk, list = pcall(C_NamePlate.GetNamePlates)
    if lOk and type(list) == "table" then
        mode = "first plates"
        for i = 1, math.min(#list, PLATEAURAS_MAX_PLATES) do picked[#picked + 1] = list[i] end
    end
    return picked, mode
end

local function CapturePlateAuras(reason)
    local run = { when = date("%Y-%m-%d %H:%M:%S"), reason = reason or "manual" }
    run.context = PlateAurasContext()
    local picked, mode = PlateAurasPickPlates()
    run.mode = mode
    run.plates = {}

    local perPlate = math.max(1, math.floor(PLATEAURAS_MAX_NODES / math.max(1, #picked)))
    for _, plate in ipairs(picked) do
        local entry = { name = PlateAurasName(plate), nodes = {} }
        local seen = {}
        -- UnitFrame first, full depth; then the plate itself one level deep.
        local uf
        local ufOk, ufv = pcall(function() return plate.UnitFrame end)
        if ufOk and type(ufv) == "table" then uf = ufv end
        entry.hasUnitFrame = uf ~= nil
        local used = 0
        if uf then
            used = PlateAurasWalk(uf, PLATEAURAS_MAX_DEPTH, perPlate, seen, entry.nodes)
        end
        if used < perPlate then
            PlateAurasWalk(plate, 1, perPlate - used, seen, entry.nodes)
        end
        entry.nodeCount = #entry.nodes
        entry.truncated = entry.nodes.truncated and true or false
        entry.nodes.truncated = nil
        run.plates[#run.plates + 1] = entry
    end

    run.summary = PlateAurasSummary(run.plates)

    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    local store = ForeverSynthwaveDB.recon.plateauras
    if type(store) ~= "table" or type(store.runs) ~= "table" then
        store = { runs = {} }
        ForeverSynthwaveDB.recon.plateauras = store
    end
    store.runs[#store.runs + 1] = run
    while #store.runs > PLATEAURAS_MAX_RUNS do table.remove(store.runs, 1) end
    return run
end

local function DoPlateAurasRun(reason)
    local ok, run = pcall(CapturePlateAuras, reason)
    if not ok then
        FS.LogDegradeOnce("fsrecon_plateauras_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon plateauras -- probe failed: %s"):format(tostring(run)))
        return
    end
    local s = run.summary
    print(("|cff22e0ffForeverSynthwave|r: /fsrecon plateauras -- %s, %d plate(s), aura textures shown %d / with texture %d / visible %d, %s; saved to recon.plateauras, /fsreload to flush")
        :format(run.mode, #run.plates, s.auraTexturesShown, s.auraTexturesWithTexture, s.auraTexturesVisible,
            tostring(run.context.inCombatLockdown) == "true" and "IN COMBAT" or "out of combat"))
end

function Diagnostics.RunPlateAurasProbe()
    DoPlateAurasRun("manual")
end

local plateAurasArmFrame
-- Bumped on every arm, trigger and disarm. A pending capture timer carries the
-- value it was created under and does nothing if it no longer matches, so
-- re-arming or disarming while a timer is pending can't double-capture.
local plateAurasArmGen = 0
-- True while armed or while a triggered capture timer is still pending, so
-- "off" can tell whether it cancelled anything.
local plateAurasActive = false

local function DisarmPlateAuras()
    plateAurasArmGen = plateAurasArmGen + 1
    plateAurasActive = false
    if plateAurasArmFrame then plateAurasArmFrame:UnregisterEvent("UNIT_AURA") end
end

local function OnPlateAurasArmEvent()
    local ok, combat = pcall(UnitAffectingCombat, "player")
    if not ok or FS.IsSecret(combat) or not combat then return end
    DisarmPlateAuras()
    if HAS_C_TIMER then
        local gen = plateAurasArmGen
        plateAurasActive = true -- capture timer pending
        C_Timer.After(1.5, function()
            if gen == plateAurasArmGen then
                plateAurasActive = false
                DoPlateAurasRun("armed")
            end
        end)
    else
        DoPlateAurasRun("armed")
    end
end

function Diagnostics.DisarmPlateAuras()
    local wasActive = plateAurasActive
    DisarmPlateAuras()
    if wasActive then
        print("|cff22e0ffForeverSynthwave|r: /fsrecon plateauras off -- disarmed; any pending capture is cancelled")
    else
        print("|cff22e0ffForeverSynthwave|r: /fsrecon plateauras off -- nothing armed")
    end
end

function Diagnostics.ArmPlateAuras()
    DisarmPlateAuras() -- supersede any earlier arm and its pending timer
    if not plateAurasArmFrame then
        plateAurasArmFrame = CreateFrame("Frame")
        plateAurasArmFrame:SetScript("OnEvent", function()
            pcall(OnPlateAurasArmEvent)
        end)
    end
    local ok, err = pcall(plateAurasArmFrame.RegisterUnitEvent, plateAurasArmFrame, "UNIT_AURA", "target")
    if not ok then
        print(("|cffff4488ForeverSynthwave|r: /fsrecon plateauras arm -- could not register UNIT_AURA: %s"):format(tostring(err)))
        return
    end
    plateAurasActive = true
    print("|cff22e0ffForeverSynthwave|r: /fsrecon plateauras arm -- armed; will capture once, 1.5s after the first target aura change in combat")
end

-- /fsrecon all -- runs every one-shot recon probe in a single command.
-- Each capture is pcall-isolated exactly like its own /fsrecon <name>
-- command (DoSurnameProbeRun/DoMinimapProbeRun, not the public
-- RunSurnameProbe/RunMinimapProbe wrappers, since those print their own
-- per-probe confirmation line and this command prints one combined line
-- instead), so one probe throwing can't block the other or skip its
-- ForeverSynthwaveDB write.
function Diagnostics.RunAllRecon()
    local surnameOk, surnameErr = pcall(DoSurnameProbeRun)
    if not surnameOk then
        FS.LogDegradeOnce("fsrecon_surname_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon surname -- probe failed: %s"):format(tostring(surnameErr)))
    end

    local minimapOk, minimapErr = pcall(DoMinimapProbeRun)
    if not minimapOk then
        FS.LogDegradeOnce("fsrecon_minimap_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon minimap -- probe failed: %s"):format(tostring(minimapErr)))
    end

    print(("|cff22e0ffForeverSynthwave|r: /fsrecon all -- surname %s, minimap %s, /fsreload to flush")
        :format(surnameOk and "captured" or "FAILED", minimapOk and "captured" or "FAILED"))
end

-- /fsrecon microbags -- inventory of Blizzard-selected controls.
local function MicroBagFrameName(frame, fallback)
    local ok, name = pcall(function() return frame:GetName() end)
    if ok and type(name) == "string" and name ~= "" then return name end
    return fallback or "<anonymous>"
end

local function MicroBagParentName(frame)
    local ok, parent = pcall(function() return frame:GetParent() end)
    if not ok then return "unavailable" end
    if not parent then return "<none>" end
    return MicroBagFrameName(parent)
end

local function MicroBagShown(frame)
    local ok, shown = pcall(function() return frame:IsShown() end)
    if not ok then return "unavailable" end
    local secretOk, secret = pcall(FS.IsSecret, shown)
    if not secretOk or secret then return "secret" end
    return shown and true or false
end

local function MicroBagLayoutIndex(frame)
    local ok, index = pcall(function()
        local value = frame.layoutIndex
        if FS.IsSecret(value) then return nil end
        if type(value) == "number" then return value end
    end)
    if ok then return index end
end

local function CaptureMicroBags()
    local report = { when = date("%Y-%m-%d %H:%M:%S"), micro = {}, bags = {} }
    local seen = {}
    local function addMicro(button, fallback)
        local index = MicroBagLayoutIndex(button)
        if not index then return end
        local name = MicroBagFrameName(button, fallback)
        if seen[name] then return end
        seen[name] = true
        report.micro[#report.micro + 1] = { name = name, index = index }
    end

    local menu = _G.MicroMenu
    local candidateOk, infos = pcall(function()
        if menu and type(menu.GenerateButtonInfos) == "function" then
            return menu:GenerateButtonInfos()
        end
    end)
    if candidateOk and type(infos) == "table" then
        pcall(function()
            for _, info in ipairs(infos) do addMicro(info.button) end
        end)
    end
    for name, frame in pairs(_G) do
        if type(name) == "string" and name:match("MicroButton$") then
            addMicro(frame, name)
        end
    end
    table.sort(report.micro, function(a, b)
        if a.index == b.index then return a.name < b.name end
        return a.index < b.index
    end)

    local manager = _G.MainMenuBarBagManager
    if manager and type(manager.EnumerateBagButtons) == "function" then
        local bagsOk, bagsErr = pcall(function()
            for registrationIndex, button in manager:EnumerateBagButtons() do
                report.bags[#report.bags + 1] = {
                    registrationIndex = registrationIndex,
                    name = MicroBagFrameName(button),
                    parent = MicroBagParentName(button),
                    shown = MicroBagShown(button),
                }
            end
        end)
        if not bagsOk then report.bagError = ProbeError(bagsErr) end
    else
        report.bagError = manager and "enumerator unavailable" or "manager unavailable"
    end

    if type(C_ActionBar) == "table" and type(C_ActionBar.ShouldShowKeyring) == "function" then
        local keyringOk, keyring = pcall(function()
            local value = C_ActionBar.ShouldShowKeyring()
            if FS.IsSecret(value) then return "secret" end
            return value and true or false
        end)
        if keyringOk then
            report.shouldShowKeyring = keyring
        else
            report.shouldShowKeyring = ProbeError(keyring)
        end
    else
        report.shouldShowKeyring = "unavailable"
    end

    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
    ForeverSynthwaveDB.recon.microBags = report
    return report
end

function Diagnostics.RunMicroBagsProbe(silent)
    local ok, report = pcall(CaptureMicroBags)
    if not ok then
        FS.LogDegradeOnce("fsrecon_microbags_probe_error",
            ("|cffff4488ForeverSynthwave|r: /fsrecon microbags -- capture failed: %s"):format(ProbeError(report)))
        return
    end
    if not silent then
        print(("|cff22e0ffForeverSynthwave|r: /fsrecon microbags -- %d micro, %d bags; saved to recon.microBags, /fsreload to flush")
            :format(#report.micro, #report.bags))
    end
end

local microBagLogin = CreateFrame("Frame")
microBagLogin:RegisterEvent("PLAYER_LOGIN")
microBagLogin:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    if C_Timer and type(C_Timer.After) == "function" then
        C_Timer.After(0.25, function() Diagnostics.RunMicroBagsProbe(true) end)
    else
        Diagnostics.RunMicroBagsProbe(true)
    end
end)

-------------------------------------------------------------------------------
-- /fsmo -- mouseover probe for testing mouseover casting
-------------------------------------------------------------------------------

-- `/fsmo` toggles a watch on UPDATE_MOUSEOVER_UNIT. Each CHANGE of unit or frame prints one chat
-- line: UnitExists, UnitName, UnitIsFriend and the name of the frame under the mouse. It exists to
-- answer "does mouseover casting see the unit I am hovering, and which frame is it over" while
-- Parker plays, so it prints and stores nothing else. Every API is pcall'd and every value goes
-- through FS.IsSecret BEFORE anything else touches it: a secret prints the word "secret" and is
-- never compared, concatenated or tostring'd. The throttle key is built only from the printed
-- strings (plus a plain GUID when readable), so a held hover on one unit stays silent. The watch
-- turns itself off after MO_TIMEOUT seconds; a generation counter makes a stale timer from an
-- earlier session a no-op.
local MO_TIMEOUT = 120
local MO_PREFIX = "|cff22e0ffsynthwave://mouseover|r  "
local moFrame
local moOn = false
local moGen = 0
local moLastKey

-- A plain string for a value that may be secret, nil, or the result of a failed call.
local function MoText(ok, value)
    if not ok then return "error" end
    local secOk, secret = pcall(FS.IsSecret, value)
    if not secOk then return "error" end
    if secret then return "secret" end
    if value == nil then return "nil" end
    local textOk, text = pcall(tostring, value)
    if not textOk then return "error" end
    return text
end

-- pcall that reports an absent API as the plain text "n/a" instead of an error.
local function MoCall(fn, ...)
    if type(fn) ~= "function" then return true, "n/a" end
    return pcall(fn, ...)
end

local function MoFrameName()
    local ok, found, name = pcall(function()
        local frame
        if type(GetMouseFoci) == "function" then
            local foci = GetMouseFoci()
            frame = foci and foci[1]
        elseif type(GetMouseFocus) == "function" then
            -- Fallback only: GetMouseFocus is absent on the 16001 dump, GetMouseFoci is the live API.
            frame = GetMouseFocus()
        else
            return "n/a"
        end
        if not frame then return "none" end
        return "frame", frame:GetName()
    end)
    if not ok then return "error" end
    if found ~= "frame" then return found end
    if name == nil then return "anon" end
    return MoText(true, name)
end

-- GUID is only part of the throttle key, never printed, so two same-named units on one frame
-- still print separately. Secret, missing or throwing reads contribute nothing, so with a secret
-- name AND an unreadable GUID, moving between units on one frame prints once (same key).
local function MoGuidKey()
    local ok, guid = MoCall(UnitGUID, "mouseover")
    if not ok then return "" end
    local secOk, secret = pcall(FS.IsSecret, guid)
    if not secOk or secret or type(guid) ~= "string" then return "" end
    return guid
end

local function MoOnEvent()
    local exists = MoText(MoCall(UnitExists, "mouseover"))
    local name = MoText(MoCall(UnitName, "mouseover"))
    local friend = MoText(MoCall(UnitIsFriend, "player", "mouseover"))
    local frameName = MoFrameName()
    local key = exists .. "|" .. name .. "|" .. friend .. "|" .. frameName .. "|" .. MoGuidKey()
    if key == moLastKey then return end
    moLastKey = key
    print(("%sexists=%s name=%s friend=%s frame=%s"):format(MO_PREFIX, exists, name, friend, frameName))
end

local function MoStop(reason)
    moOn = false
    moGen = moGen + 1
    moLastKey = nil
    if moFrame then moFrame:UnregisterEvent("UPDATE_MOUSEOVER_UNIT") end
    print(MO_PREFIX .. "off" .. (reason and ("  (" .. reason .. ")") or ""))
end

local function MoStart()
    if not moFrame then
        moFrame = CreateFrame("Frame")
        moFrame:SetScript("OnEvent", function() MoOnEvent() end)
    end
    moOn = true
    moGen = moGen + 1
    moLastKey = nil
    moFrame:RegisterEvent("UPDATE_MOUSEOVER_UNIT")
    local cvar = MoText(MoCall(GetCVar, "enableMouseoverCast"))
    local click = MoText(MoCall(GetModifiedClick, "MOUSEOVERCAST"))
    local hasTimer = C_Timer and type(C_Timer.After) == "function"
    print(("%son  enableMouseoverCast=%s  MOUSEOVERCAST=%s  %s"):format(
        MO_PREFIX, cvar, click, hasTimer and ("(auto-off " .. MO_TIMEOUT .. "s)") or "(no auto-off timer)"))
    if hasTimer then
        local gen = moGen
        C_Timer.After(MO_TIMEOUT, function()
            if moOn and gen == moGen then MoStop(MO_TIMEOUT .. "s timeout") end
        end)
    end
end

SLASH_FSMO1 = "/fsmo"
SlashCmdList["FSMO"] = function()
    if moOn then MoStop() else MoStart() end
end

-------------------------------------------------------------------------------
-- /fsrecon class -- class spell, form and aura recon
-------------------------------------------------------------------------------

-- `/fsrecon class` records what a class really looks like on this client before class features
-- are built for it: the talent API that exists with the points per tab and the ranked talents
-- (CR.Ranks), the shapeshift forms, the resolved id of every candidate spell name with IsPlayerSpell
-- and the aura secrecy enum, the class's own HudProfile spell keys, the player's buffs, the player's
-- debuffs on the target, and the player's buffs on party1 to party4. The tester runs it once (a seal
-- and an aura up, a judged mob, a blessing on a party member), then `/fsbug`: the result is also kept
-- in ForeverSynthwaveDB.recon.class, stamped with the wall clock (`taken`). BugReport.lua copies the last run into the FIRST report after a
-- run (Diagnostics.GetClassRecon, then MarkClassReconReported); later reports get a small stub.
--
-- Every API read is pcall'd and every value goes through FS.IsSecret BEFORE anything compares,
-- concatenates, indexes or tostring's it: a secret is stored as the word "secret", a throw as
-- "error", an absent API as "unavailable". A table is read only after IsSecret and issecrettable
-- cleared it, and only with rawget (CR.Field, CR.Sub, CR.At; the # operator on a cleared list is
-- the one other touch). Aura reads (the three aura sections) run out of
-- combat only: in combat, or when the combat state cannot be read, or when
-- C_Secrets.ShouldAurasBeSecret is not a plain false, they are skipped and the section says why.
-- Every list is capped (CR.LIMITS). The class candidate table is CR.CANDIDATES (PALADIN full, the
-- other two small); a class without one still gets the generic sections and its HudProfile keys.
--
-- The chat output is built from the stored data, so chat and the /fsbug JSON say the same thing
-- (the stored data also carries a decoded name beside each secrecy number).
do
    local CR = {}
    CR.PREFIX = "|cff22e0ffsynthwave://class|r  "
    CR.LIMITS = { str = 60, forms = 10, tabs = 5, spells = 60, hud = 40, buffs = 40, debuffs = 16, party = 20,
        talents = 60, talentScan = 40, trees = 3, nodes = 400 }
    -- Enum.SecrecyLevel, as GetSpellAuraSecrecy returns it (SecretWrapperConstantsDocumentation.lua).
    CR.SECRECY = { [0] = "NeverSecret", [1] = "AlwaysSecret", [2] = "ContextuallySecret" }
    CR.PARTY_UNITS = { "party1", "party2", "party3", "party4" }
    CR.MARKERS = { secret = true, error = true, unavailable = true, nan = true }
    CR.last = nil

    -- Candidate spell NAMES per class token, in the groups the chat output prints. A name that does
    -- not resolve on this client is itself the answer ("none"), so spellings that may not exist
    -- (Seal of Fury, the Greater versions of every blessing) are listed on purpose.
    CR.CANDIDATES = {
        PALADIN = {
            { group = "seals", "Seal of Righteousness", "Seal of the Crusader", "Seal of Fury",
              "Seal of Command", "Seal of Justice", "Seal of Light", "Seal of Wisdom" },
            { group = "judgement", "Judgement", "Judgment" },
            { group = "strike", "Holy Strike" },
            { group = "auras", "Devotion Aura", "Retribution Aura", "Concentration Aura",
              "Shadow Resistance Aura", "Frost Resistance Aura", "Fire Resistance Aura" },
            { group = "blessings", "Blessing of Might", "Blessing of Wisdom", "Blessing of Kings",
              "Blessing of Protection", "Blessing of Salvation", "Blessing of Light", "Blessing of Sanctuary",
              "Greater Blessing of Might", "Greater Blessing of Wisdom", "Greater Blessing of Kings",
              "Greater Blessing of Protection", "Greater Blessing of Salvation", "Greater Blessing of Light",
              "Greater Blessing of Sanctuary" },
            { group = "other", "Purify", "Cleanse", "Consecration", "Hammer of Justice", "Lay on Hands",
              "Divine Protection", "Holy Light", "Flash of Light" },
        },
        WARLOCK = {
            { group = "core", "Corruption", "Immolate", "Shadow Bolt", "Life Tap", "Curse of Agony",
              "Drain Soul", "Fear", "Demon Armor" },
        },
        PRIEST = {
            { group = "core", "Shadow Word: Pain", "Mind Blast", "Mind Flay", "Smite",
              "Power Word: Fortitude", "Inner Fire", "Power Word: Shield" },
        },
    }

    -- nil when v is plain, else "secret" (or "error" when the check itself failed).
    function CR.SecretState(v)
        local ok, sec = pcall(FS.IsSecret, v)
        if not ok then return "error" end
        if sec ~= false then return "secret" end
        return nil
    end

    -- A plain value, capped, or a marker word. Tables and functions are never recorded as values.
    function CR.Value(v)
        local state = CR.SecretState(v)
        if state then return state end
        local t = type(v)
        if t == "string" then
            if #v > CR.LIMITS.str then return v:sub(1, CR.LIMITS.str) end
            return v
        elseif t == "number" then
            if v ~= v or v == math.huge or v == -math.huge then return "nan" end
            return v
        elseif t == "boolean" then
            return v
        end
        return nil
    end

    -- The table when it is plain and readable; otherwise nil plus a marker word, or nil alone when
    -- v is plainly not a table.
    function CR.Readable(t)
        local state = CR.SecretState(t)
        if state then return nil, state end
        if type(t) ~= "table" then return nil, nil end
        local fn = _G.issecrettable
        if type(fn) == "function" then
            local ok, r = pcall(fn, t)
            if not ok or r ~= false then return nil, "secret" end
        end
        return t, nil
    end

    function CR.Field(t, key)
        local ok, v = pcall(rawget, t, key)
        if not ok then return "error" end
        return CR.Value(v)
    end

    -- A function from _G (ns nil) or from a namespace table, or nil when it is not there.
    function CR.Api(ns, name)
        local ok, fn = pcall(function()
            if ns == nil then return _G[name] end
            local t = _G[ns]
            if type(t) ~= "table" then return nil end
            return t[name]
        end)
        if ok and type(fn) == "function" then return fn end
        return nil
    end

    local function pack(ok, ...)
        if not ok then return { status = "error", n = 0 } end
        return { status = "ok", n = select("#", ...), ... }
    end

    -- { status = "ok" | "error" | "unavailable", n = count, [i] = RAW result }. Raw values must go
    -- through CR.Get, CR.Value or CR.Readable before anything else touches them.
    function CR.Call(fn, ...)
        if type(fn) ~= "function" then return { status = "unavailable", n = 0 } end
        return pack(pcall(fn, ...))
    end

    function CR.Get(r, i)
        if r.status ~= "ok" then return r.status end
        return CR.Value(r[i])
    end

    -- A readable table result of fn(...): the table, or nil plus a marker word ("secret", "error",
    -- "unavailable") or nil alone when the call plainly returned no table.
    function CR.CallTable(fn, ...)
        local r = CR.Call(fn, ...)
        if r.status ~= "ok" then return nil, r.status end
        return CR.Readable(r[1])
    end

    -- t[key] of a readable table by rawget (never an index), or nil when the read throws. The value
    -- is RAW: pass it through CR.Value or CR.Readable before anything else touches it.
    function CR.At(t, key)
        local ok, v = pcall(rawget, t, key)
        if ok then return v end
        return nil
    end

    -- A readable sub-table of a readable table (rawget, never an index), or nil.
    function CR.Sub(t, key)
        return (CR.Readable(CR.At(t, key)))
    end

    function CR.Guard(fn, ...)
        local ok, r = pcall(fn, ...)
        if ok then return r end
        return "error"
    end

    function CR.Round1(v) return math.floor(v * 10 + 0.5) / 10 end

    -- Spell lookup ----------------------------------------------------------

    -- The resolved id of a spell NAME: a number, "none" (the client resolved nothing), or a marker.
    function CR.Resolve(fn, legacy, name)
        local r = CR.Call(fn, name)
        if r.status ~= "ok" then return r.status end
        if legacy then
            local id = CR.Get(r, 7)
            if id == nil then return "none" end
            return id
        end
        local info, state = CR.Readable(r[1])
        if state then return state end
        if info == nil then return "none" end
        local id = CR.Field(info, "spellID")
        if id == nil then return "none" end
        return id
    end

    function CR.Spell(ctx, name)
        local e = { name = name }
        e.id = CR.Resolve(ctx.infoFn, ctx.legacy, name)
        if type(e.id) == "number" then
            e.known = CR.Get(CR.Call(ctx.knownFn, e.id), 1)
            if ctx.secrecyFn then
                e.secrecy = CR.Get(CR.Call(ctx.secrecyFn, e.id), 1)
                if type(e.secrecy) == "number" then e.secrecyName = CR.SECRECY[e.secrecy] end
            end
        end
        return e
    end

    function CR.SpellContext()
        local ctx = { spellApi = {} }
        ctx.infoFn = CR.Api("C_Spell", "GetSpellInfo")
        if ctx.infoFn then
            ctx.spellApi.info = "C_Spell.GetSpellInfo"
        else
            ctx.infoFn = CR.Api(nil, "GetSpellInfo")
            ctx.legacy = true
            ctx.spellApi.info = ctx.infoFn and "GetSpellInfo" or "unavailable"
        end
        ctx.knownFn = CR.Api(nil, "IsPlayerSpell")
        ctx.secrecyFn = CR.Api("C_Spell", "GetSpellAuraSecrecy")
        if ctx.secrecyFn then
            ctx.spellApi.secrecy = "C_Spell.GetSpellAuraSecrecy"
        else
            ctx.secrecyFn = CR.Api("C_Secrets", "GetSpellAuraSecrecy")
            ctx.spellApi.secrecy = ctx.secrecyFn and "C_Secrets.GetSpellAuraSecrecy" or "unavailable"
        end
        return ctx
    end

    function CR.Candidates(ctx, token)
        local groups = type(token) == "string" and CR.CANDIDATES[token] or nil
        local out = {}
        if not groups then return out end
        for _, g in ipairs(groups) do
            for _, name in ipairs(g) do
                if #out >= CR.LIMITS.spells then return out end
                local e = CR.Spell(ctx, name)
                e.group = g.group
                out[#out + 1] = e
            end
        end
        return out
    end

    -- The class's own HudProfile spell keys (row, cooldowns, dots, channels, self buffs), deduped.
    function CR.HudKeys(profile)
        local keys, seen = {}, {}
        local function add(k)
            if type(k) == "string" and not seen[k] and #keys < CR.LIMITS.hud then
                seen[k] = true
                keys[#keys + 1] = k
            end
        end
        local function addSorted(t)
            if type(t) ~= "table" then return end
            local list = {}
            for k in pairs(t) do
                if type(k) == "string" then list[#list + 1] = k end
            end
            table.sort(list)
            for _, k in ipairs(list) do add(k) end
        end
        if type(profile.row) == "table" then for _, k in ipairs(profile.row) do add(k) end end
        if type(profile.cooldowns) == "table" then for _, k in ipairs(profile.cooldowns) do add(k) end end
        addSorted(profile.dots)
        addSorted(profile.channels)
        if type(profile.selfBuffs) == "table" then
            for _, b in ipairs(profile.selfBuffs) do
                if type(b) == "table" then add(b.spell) end
            end
        end
        return keys
    end

    function CR.Hud(ctx, token)
        local profile = type(token) == "string" and type(FS.HudProfiles) == "table" and FS.HudProfiles[token] or nil
        if type(profile) ~= "table" then return { profile = false } end
        local out = { profile = true, keys = {} }
        local dictionary = type(FS.HudSpells) == "table" and FS.HudSpells or {}
        for _, key in ipairs(CR.HudKeys(profile)) do
            local def = dictionary[key]
            local name = type(def) == "table" and type(def.names) == "table" and def.names[1] or nil
            local e
            if type(name) == "string" then
                e = CR.Spell(ctx, name)
            else
                e = { id = "no entry" }
            end
            e.key = key
            if type(def) == "table" and type(def.ids) == "table" then e.dictId = CR.Value(def.ids[1]) end
            out.keys[#out.keys + 1] = e
        end
        return out
    end

    -- Talents, forms -----------------------------------------------------------

    -- A tab count the client gave, capped. A count that is not a number, or is below 1, is as good as
    -- no answer (a client can report 0 before the talents load): the first three tabs get probed.
    function CR.Tabs(n)
        if type(n) ~= "number" or n < 1 then n = 3 end
        return math.min(n, CR.LIMITS.tabs)
    end

    -- How many talent trees to walk: GetNumSpecializations, or three when the client has none.
    function CR.TabCount()
        return CR.Tabs(CR.Get(CR.Call(CR.Api(nil, "GetNumSpecializations")), 1))
    end

    -- Talents with a rank, from C_SpecializationInfo.GetTalentInfo. Verified against the 16001 API dump
    -- (C_SpecializationInfo.GetTalentInfo is a function), Blizzard_APIDocumentationGenerated/
    -- SpecializationInfoDocumentation.lua (one TalentInfoQuery table in, a TalentInfoResult table or
    -- nothing out) and Deprecated_Specialization_TBC.lua (talentIndex is a position inside tab
    -- specializationIndex; there is no talent-count API, so each tab is read until nothing comes back).
    -- Returns "ok" (something was read), "empty" (the API answered nothing), "unavailable", "secret" or
    -- "error" (the API stopped the scan before anything ranked was read), or "partial" (it stopped it
    -- after: the list keeps what was read). A stop also returns where, e.g. "error at tab 2 idx 5".
    function CR.RanksFromSpecInfo(list)
        local fn = CR.Api("C_SpecializationInfo", "GetTalentInfo")
        if not fn then return "unavailable" end
        local seen = 0
        for tab = 1, CR.TabCount() do
            for index = 1, CR.LIMITS.talentScan do
                local t, state = CR.CallTable(fn, { specializationIndex = tab, talentIndex = index, isInspect = false, isPet = false })
                if not t then
                    if state then
                        local where = ("%s at tab %d idx %d"):format(state, tab, index)
                        if #list > 0 then return "partial", nil, where end
                        return state, nil, where
                    end
                    break
                end
                seen = seen + 1
                local rank = CR.Field(t, "rank")
                if rank ~= nil and (type(rank) ~= "number" or rank > 0) then
                    if #list >= CR.LIMITS.talents then return "ok", true end
                    list[#list + 1] = { tab = tab, id = CR.Field(t, "talentID"), name = CR.Field(t, "name"),
                        rank = rank, maxRank = CR.Field(t, "maxRank") }
                end
            end
        end
        return seen > 0 and "ok" or "empty"
    end

    -- The same, from the trait system for a client whose talents are trait nodes. Verified in the dump
    -- and SharedTraitsDocumentation.lua / ClassTalentsDocumentation.lua: C_ClassTalents.GetActiveConfigID()
    -- gives the config id; C_Traits.GetConfigInfo(configID).treeIDs; C_Traits.GetTreeNodes(treeID);
    -- C_Traits.GetNodeInfo(configID, nodeID) has activeRank, maxRanks and activeEntry.entryID;
    -- C_Traits.GetEntryInfo(configID, entryID).definitionID; C_Traits.GetDefinitionInfo(definitionID).spellID.
    -- An id is handed to the next call only when it is a plain number. A tree list, tree or node that could
    -- not be read (its id or its table secret, or the call failing) is counted in tally.skipped, so the result says
    -- how much it could not see; when nothing at all was read, that reason is the status.
    function CR.RanksFromTraits(list, tally)
        local cfgR = CR.Call(CR.Api("C_ClassTalents", "GetActiveConfigID"))
        local cfg = CR.Get(cfgR, 1)
        if type(cfg) ~= "number" then
            if cfgR.status ~= "ok" then return cfgR.status end
            -- CR.Value turns a plain string like "secret" into the same word as a real marker, so the
            -- raw result decides: only a value the secret check flags (or fails on) is "secret"/"error".
            local state = CR.SecretState(cfgR[1])
            if state then return state end
            -- plainly nothing: empty; plainly something the walk cannot use (a string, a table, NaN): unavailable
            if cfgR[1] == nil then return "empty" end
            return "unavailable"
        end
        local info, state = CR.CallTable(CR.Api("C_Traits", "GetConfigInfo"), cfg)
        if not info then return state or "empty" end
        local trees, treesState = CR.Readable(CR.At(info, "treeIDs"))
        if not trees then
            -- A secret (or unreadable) id list is not an empty one: count it and say why.
            if treesState and CR.MARKERS[treesState] then
                if tally then tally.skipped = (tally.skipped or 0) + 1 end
                return treesState
            end
            return "empty"
        end
        local nodeFn, entryFn, defFn = CR.Api("C_Traits", "GetNodeInfo"), CR.Api("C_Traits", "GetEntryInfo"),
            CR.Api("C_Traits", "GetDefinitionInfo")
        local seen, unreadable = 0, nil
        -- Counts something that could not be read. Only a marker word (CR.MARKERS) is a state; any other
        -- value, a plain string included, is no state and never becomes the status text.
        local function note(state)
            if type(state) ~= "string" or not CR.MARKERS[state] then return end
            if tally then tally.skipped = (tally.skipped or 0) + 1 end
            unreadable = unreadable or state
        end
        for ti = 1, math.min(#trees, CR.LIMITS.trees) do
            local treeId = CR.Value(CR.At(trees, ti))
            local nodes, treeState
            if type(treeId) == "number" then
                nodes, treeState = CR.CallTable(CR.Api("C_Traits", "GetTreeNodes"), treeId)
            else
                treeState = treeId
            end
            note(treeState)
            for ni = 1, nodes and math.min(#nodes, CR.LIMITS.nodes) or 0 do
                local nodeId = CR.Value(CR.At(nodes, ni))
                local node, nodeState
                if type(nodeId) == "number" then
                    node, nodeState = CR.CallTable(nodeFn, cfg, nodeId)
                else
                    nodeState = nodeId
                end
                note(nodeState)
                if node then
                    seen = seen + 1
                    local rank = CR.Field(node, "activeRank")
                    if rank ~= nil and (type(rank) ~= "number" or rank > 0) then
                        if #list >= CR.LIMITS.talents then return "ok", true end
                        local e = { node = nodeId, rank = rank, maxRank = CR.Field(node, "maxRanks") }
                        local active = CR.Sub(node, "activeEntry")
                        local entryId = active and CR.Field(active, "entryID")
                        local entry = type(entryId) == "number" and CR.CallTable(entryFn, cfg, entryId) or nil
                        local defId = entry and CR.Field(entry, "definitionID")
                        local def = type(defId) == "number" and CR.CallTable(defFn, defId) or nil
                        if def then e.spellId = CR.Field(def, "spellID") end
                        list[#list + 1] = e
                    end
                end
            end
        end
        if seen == 0 and unreadable then return unreadable end
        return seen > 0 and "ok" or "empty"
    end

    -- { status, source, list, capped, reason, stoppedAt, skipped }: the talents with a rank, from whichever
    -- verified API answers. A scan the API cut short keeps what it read and says where, as status
    -- "partial (error at tab 2 idx 5)"; with nothing read, the trait route still gets its turn.
    function CR.Ranks()
        local ranks = { list = {} }
        local spec, capped, stoppedAt = CR.RanksFromSpecInfo(ranks.list)
        local traits = "skipped"
        local tally = {}
        ranks.source = "C_SpecializationInfo.GetTalentInfo"
        ranks.stoppedAt = stoppedAt
        if spec ~= "ok" and #ranks.list == 0 then
            traits, capped = CR.RanksFromTraits(ranks.list, tally)
            ranks.source = "C_Traits (C_ClassTalents.GetActiveConfigID)"
            if traits ~= "ok" then ranks.source = nil end
        end
        ranks.capped = capped or nil
        ranks.skipped = tally.skipped
        if spec == "ok" or traits == "ok" then
            ranks.status = "ok"
        elseif spec == "partial" then
            ranks.status = "partial (" .. stoppedAt .. ")"
            ranks.partial = true
        else
            ranks.status = (spec == "secret" or spec == "error") and spec or "unavailable"
            ranks.reason = ("GetTalentInfo=%s traits=%s"):format(spec, traits)
        end
        return ranks
    end

    function CR.Talents()
        local out = { api = {}, tabs = {}, specIndex = {} }
        local tabFn = CR.Api(nil, "GetTalentTabInfo")
        out.api.GetTalentTabInfo = tabFn and "ok" or "unavailable"
        out.tabSource = "GetTalentTabInfo"
        if tabFn then
            -- A client without GetNumTalentTabs still gets its first three tabs probed.
            local n = CR.Tabs(CR.Get(CR.Call(CR.Api(nil, "GetNumTalentTabs")), 1))
            for i = 1, n do
                local r = CR.Call(tabFn, i)
                if r.status == "error" then
                    out.api.GetTalentTabInfo = "error"
                    break
                end
                -- Classic layout: name, icon, points. Retail layout: id, name, description, icon, points.
                local a, b = CR.Get(r, 1), CR.Get(r, 2)
                local name, points
                if type(a) == "number" and type(b) == "string" then
                    name, points = b, CR.Get(r, 5)
                else
                    name, points = a, CR.Get(r, 3)
                end
                if name == nil then break end
                out.tabs[#out.tabs + 1] = { name = name, points = points }
            end
        else
            -- This client ships no GetTalentTabInfo (Blizzard's deprecated shim loads only behind a CVar):
            -- names and points come from C_SpecializationInfo.GetSpecializationInfo, which returns specId,
            -- name, description, icon, role, primaryStat, pointsSpent.
            local specFn = CR.Api("C_SpecializationInfo", "GetSpecializationInfo")
            if specFn then out.tabSource = "C_SpecializationInfo.GetSpecializationInfo" end
            for i = 1, specFn and CR.TabCount() or 0 do
                local r = CR.Call(specFn, i)
                local name = CR.Get(r, 2)
                if r.status ~= "ok" or name == nil then break end
                out.tabs[#out.tabs + 1] = { name = name, points = CR.Get(r, 7) }
            end
        end
        out.ranks = CR.Guard(CR.Ranks)
        local function spec(label, idxFn, infoFn)
            local r = CR.Call(idxFn)
            out.api[label] = r.status
            local idx = CR.Get(r, 1)
            if type(idx) ~= "number" then return end
            out.specIndex[label] = idx
            if idx > 0 and not out.spec then
                local info = CR.Call(infoFn, idx)
                if info.status == "ok" then
                    local name = CR.Get(info, 2)
                    if type(name) == "string" then out.spec = name end
                end
            end
        end
        spec("C_SpecializationInfo", CR.Api("C_SpecializationInfo", "GetSpecialization"),
            CR.Api("C_SpecializationInfo", "GetSpecializationInfo"))
        spec("GetSpecialization", CR.Api(nil, "GetSpecialization"), CR.Api(nil, "GetSpecializationInfo"))
        return out
    end

    function CR.Forms()
        local out = { list = {} }
        local n = CR.Get(CR.Call(CR.Api(nil, "GetNumShapeshiftForms")), 1)
        out.count = n
        if type(n) ~= "number" then return out end
        local infoFn = CR.Api(nil, "GetShapeshiftFormInfo")
        for i = 1, math.min(n, CR.LIMITS.forms) do
            local r = CR.Call(infoFn, i)
            if r.status ~= "ok" then
                out.list[#out.list + 1] = { index = i, status = r.status }
                break
            end
            -- Retail: icon, active, castable, spellID. Classic: icon, name, active, castable, spellID.
            local e = { index = i, icon = CR.Get(r, 1) }
            if type(r[2]) == "string" then
                e.name, e.active, e.castable, e.spellId = CR.Get(r, 2), CR.Get(r, 3), CR.Get(r, 4), CR.Get(r, 5)
            else
                e.active, e.castable, e.spellId = CR.Get(r, 2), CR.Get(r, 3), CR.Get(r, 4)
            end
            out.list[#out.list + 1] = e
        end
        return out
    end

    -- Auras -----------------------------------------------------------------------

    -- Returns the combat flag (true, false or "unknown") and, when auras must not be read, the
    -- reason. A plain false from both checks is the only thing that lets a read through.
    function CR.AuraGate()
        local v = CR.Get(CR.Call(CR.Api(nil, "InCombatLockdown")), 1)
        if v == true then return true, "skipped (in combat)" end
        if v ~= false then return "unknown", "skipped (combat state unknown)" end
        -- A client without C_Secrets.ShouldAurasBeSecret passes: the reads below are still pcall'd and
        -- every table goes through CR.Readable, so a secret there reads "secret" instead of throwing.
        local secretFn = CR.Api("C_Secrets", "ShouldAurasBeSecret")
        if secretFn and CR.Get(CR.Call(secretFn), 1) ~= false then
            return false, "skipped (auras secret)"
        end
        return false, nil
    end

    function CR.AuraEntry(data, kind, now)
        local e = { name = CR.Field(data, "name"), spellId = CR.Field(data, "spellId") }
        if kind == "party" then return e end
        e.duration = CR.Field(data, "duration")
        if kind ~= "player" then return e end
        local exp = CR.Field(data, "expirationTime")
        if type(exp) == "number" and type(now) == "number" then
            if exp == 0 then e.left = "none" else e.left = CR.Round1(exp - now) end
        elseif CR.MARKERS[exp] then
            e.left = exp
        end
        e.sourceUnit = CR.Field(data, "sourceUnit")
        e.dispelName = CR.Field(data, "dispelName")
        return e
    end

    function CR.Scan(unit, filter, cap, kind, now)
        local fn = CR.Api("C_UnitAuras", "GetAuraDataByIndex")
        if not fn then return { status = "unavailable" } end
        local out = { status = "ok", list = {} }
        for i = 1, cap do
            local r = CR.Call(fn, unit, i, filter)
            if r.status ~= "ok" then
                if i == 1 then return { status = r.status } end
                out.status = "partial (" .. r.status .. ")"
                break
            end
            -- Zero return values at index 1 is an unreadable scan, never an empty list.
            if r.n == 0 then
                if i == 1 then return { status = "unreadable (no values)" } end
                break
            end
            local data, state = CR.Readable(r[1])
            if state then
                out.list[#out.list + 1] = state
            elseif data == nil then
                break
            else
                out.list[#out.list + 1] = CR.AuraEntry(data, kind, now)
            end
        end
        out.count = #out.list
        if out.count >= cap then out.capped = true end
        return out
    end

    -- true / false for a unit that plainly does / does not exist, nil when that cannot be read.
    function CR.Exists(unit)
        local v = CR.Get(CR.Call(CR.Api(nil, "UnitExists"), unit), 1)
        if v == true or v == false then return v end
        return nil
    end

    function CR.Auras(data)
        local combat, reason = CR.AuraGate()
        data.inCombat = combat
        if reason then
            data.buffs, data.debuffs, data.party = { status = reason }, { status = reason }, { status = reason }
            return
        end
        local now = CR.Get(CR.Call(CR.Api(nil, "GetTime")), 1)
        data.time = type(now) == "number" and now or nil
        data.buffs = CR.Guard(CR.Scan, "player", "HELPFUL", CR.LIMITS.buffs, "player", now)
        local exists = CR.Exists("target")
        if exists == true then
            data.debuffs = CR.Guard(CR.Scan, "target", "HARMFUL|PLAYER", CR.LIMITS.debuffs, "target", now)
        elseif exists == false then
            data.debuffs = { status = "no target" }
        else
            data.debuffs = { status = "unknown target" }
        end
        data.party = {}
        for _, unit in ipairs(CR.PARTY_UNITS) do
            local present = CR.Exists(unit)
            if present == true then
                data.party[unit] = CR.Guard(CR.Scan, unit, "HELPFUL|PLAYER", CR.LIMITS.party, "party", now)
            elseif present == false then
                data.party[unit] = { status = "absent" }
            else
                data.party[unit] = { status = "unknown" }
            end
        end
    end

    -- Capture -------------------------------------------------------------------------

    function CR.Capture()
        local data = { schema = 1 }
        local cls = CR.Call(CR.Api(nil, "UnitClass"), "player")
        data.class, data.token = CR.Get(cls, 1), CR.Get(cls, 2)
        -- Wall clock, so a report can say which run it carries. date is plain text, never secret.
        local okDate, stamp = pcall(date, "%Y-%m-%d %H:%M:%S")
        data.taken = okDate and type(stamp) == "string" and stamp or "unavailable"
        data.level = CR.Get(CR.Call(CR.Api(nil, "UnitLevel"), "player"), 1)
        local combat = CR.AuraGate()
        data.inCombat = combat

        data.talents = CR.Guard(CR.Talents)
        if type(data.talents) == "table" then data.spec = data.talents.spec end
        data.forms = CR.Guard(CR.Forms)

        local ctx = CR.Guard(CR.SpellContext)
        if type(ctx) ~= "table" then ctx = { spellApi = { info = "error", secrecy = "error" } } end
        data.spellApi = ctx.spellApi
        data.spells = CR.Guard(CR.Candidates, ctx, data.token)
        data.hud = CR.Guard(CR.Hud, ctx, data.token)
        if type(data.hud) == "table" then data.hud.token = data.token end

        CR.Guard(CR.Auras, data)
        if data.buffs == nil then data.buffs, data.debuffs, data.party = "error", "error", "error" end
        return data
    end

    -- Chat output ----------------------------------------------------------------------------

    local function T(v)
        if v == nil then return "nil" end
        return tostring(v)
    end

    local function tbl(v)
        if type(v) == "table" then return v end
        return {}
    end

    function CR.SpellText(e, label)
        local text = ("%s=%s"):format(label or T(e.name), T(e.id))
        if type(e.id) == "number" then
            if e.known == true then text = text .. " known"
            elseif e.known == false then text = text .. " unknown"
            else text = text .. " known=" .. T(e.known) end
            if e.secrecy ~= nil then text = text .. " s=" .. T(e.secrecy) end
        end
        return text
    end

    function CR.AuraText(e, kind)
        if type(e) ~= "table" then return T(e) end
        local text = ("%s id=%s"):format(T(e.name), T(e.spellId))
        if kind == "party" then return text end
        text = text .. " dur=" .. T(e.duration)
        if kind ~= "player" then return text end
        return text .. (" left=%s src=%s dispel=%s"):format(T(e.left), T(e.sourceUnit), T(e.dispelName))
    end

    function CR.AuraSection(label, section, kind)
        if type(section) ~= "table" then return label .. "  " .. T(section) end
        if section.status ~= "ok" then return label .. "  " .. T(section.status) end
        local parts = {}
        for _, e in ipairs(tbl(section.list)) do parts[#parts + 1] = CR.AuraText(e, kind) end
        local text = ("%s  %d"):format(label, #parts)
        if #parts > 0 then text = text .. "  " .. table.concat(parts, "; ") end
        if section.capped then text = text .. "  (capped)" end
        return text
    end

    function CR.PartyText(party)
        local label = "party buffs (mine)"
        if type(party) ~= "table" then return label .. "  " .. T(party) end
        if party.status then return label .. "  " .. T(party.status) end
        local parts = {}
        for _, unit in ipairs(CR.PARTY_UNITS) do
            local p = party[unit]
            local text
            if type(p) ~= "table" then
                text = T(p)
            elseif p.status ~= "ok" then
                text = T(p.status)
            elseif #tbl(p.list) == 0 then
                text = "none"
            else
                local auras = {}
                for _, e in ipairs(p.list) do auras[#auras + 1] = CR.AuraText(e, "party") end
                text = table.concat(auras, ", ")
            end
            parts[#parts + 1] = unit .. ": " .. text
        end
        return label .. "  " .. table.concat(parts, "; ")
    end

    function CR.Lines(data)
        local lines = {}
        local function add(text) lines[#lines + 1] = text end
        add(("class=%s level=%s spec=%s combat=%s"):format(T(data.token), T(data.level), T(data.spec or "n/a"),
            T(data.inCombat)))

        local talents = tbl(data.talents)
        local api = tbl(talents.api)
        local tabs = {}
        for _, tab in ipairs(tbl(talents.tabs)) do tabs[#tabs + 1] = ("%s=%s"):format(T(tab.name), T(tab.points)) end
        add(("talents  GetTalentTabInfo=%s C_SpecializationInfo=%s GetSpecialization=%s  %s"):format(
            T(api.GetTalentTabInfo), T(api.C_SpecializationInfo), T(api.GetSpecialization),
            #tabs > 0 and table.concat(tabs, " ") or "tabs=none"))
        local ranks = tbl(talents.ranks)
        if ranks.status == "ok" or ranks.partial then
            local parts = {}
            for _, e in ipairs(tbl(ranks.list)) do
                parts[#parts + 1] = ("%s=%s/%s"):format(T(e.name or e.spellId or e.node), T(e.rank), T(e.maxRank))
            end
            local skipped = ranks.skipped and (" (%s unreadable)"):format(T(ranks.skipped)) or ""
            add(("ranks  %s via %s  %d%s%s  %s"):format(T(ranks.status), T(ranks.source), #parts,
                ranks.capped and " (capped)" or "", skipped, #parts > 0 and table.concat(parts, "; ") or "none"))
        else
            add(("ranks  %s  %s"):format(T(ranks.status), T(ranks.reason)))
        end

        local forms = tbl(data.forms)
        add("forms=" .. T(forms.count))
        for _, f in ipairs(tbl(forms.list)) do
            local text = ("form %s  id=%s active=%s castable=%s icon=%s"):format(
                T(f.index), T(f.spellId), T(f.active), T(f.castable), T(f.icon))
            if f.name ~= nil then text = text .. " name=" .. T(f.name) end
            if f.status ~= nil then text = text .. " status=" .. T(f.status) end
            add(text)
        end

        local spells = tbl(data.spells)
        local resolved, known = 0, 0
        local order, byGroup = {}, {}
        for _, e in ipairs(spells) do
            if type(e.id) == "number" then resolved = resolved + 1 end
            if e.known == true then known = known + 1 end
            local g = T(e.group)
            if not byGroup[g] then byGroup[g] = {}; order[#order + 1] = g end
            byGroup[g][#byGroup[g] + 1] = CR.SpellText(e)
        end
        local spellApi = tbl(data.spellApi)
        add(("spells  %d candidates, %d resolved, %d known  info=%s secrecy=%s"):format(
            #spells, resolved, known, T(spellApi.info), T(spellApi.secrecy)))
        for _, g in ipairs(order) do add(g .. "  " .. table.concat(byGroup[g], "; ")) end

        local hud = tbl(data.hud)
        if hud.profile == true then
            local parts = {}
            for _, e in ipairs(tbl(hud.keys)) do parts[#parts + 1] = CR.SpellText(e, T(e.key)) end
            add(("hud  %s profile keys=%d  %s"):format(T(hud.token), #parts, table.concat(parts, "; ")))
        else
            add("hud  no profile for " .. T(hud.token or data.token))
        end

        add(CR.AuraSection("buffs", data.buffs, "player"))
        add(CR.AuraSection("target debuffs (mine)", data.debuffs, "target"))
        add(CR.PartyText(data.party))
        return lines
    end

    function Diagnostics.RunClassRecon()
        local ok, data = pcall(CR.Capture)
        if not ok then
            FS.LogDegradeOnce("fsrecon_class_probe_error",
                "|cffff4488ForeverSynthwave|r: /fsrecon class -- capture failed")
            return
        end
        CR.last = data
        ForeverSynthwaveDB = ForeverSynthwaveDB or {}
        ForeverSynthwaveDB.recon = ForeverSynthwaveDB.recon or {}
        ForeverSynthwaveDB.recon.class = data

        local built, lines = pcall(CR.Lines, data)
        if not built then lines = { "output failed, the data is saved" } end
        for _, line in ipairs(lines) do pcall(print, CR.PREFIX .. line) end
        pcall(print, CR.PREFIX .. "saved to recon.class, /fsbug includes it")
    end

    -- BugReport.lua calls this once /fsbug has attached the full run to a report AND shown it to the
    -- tester, so later reports carry only a stub. The flag lives on the saved run, so the next /fsrecon class (a new table) clears it.
    function Diagnostics.MarkClassReconReported()
        local data = Diagnostics.GetClassRecon()
        if type(data) == "table" then data.reported = true end
    end

    -- The last run, for BugReport.lua. A run from an earlier session (the SavedVariables copy) counts
    -- until this session runs one.
    function Diagnostics.GetClassRecon()
        if CR.last ~= nil then return CR.last end
        local db = _G.ForeverSynthwaveDB
        if type(db) == "table" and type(db.recon) == "table" then return db.recon.class end
        return nil
    end
end
