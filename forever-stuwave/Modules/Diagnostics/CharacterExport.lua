-- Forever STUwave: character export
-- A silent snapshot of the logged-in character in ForeverSTUwaveExport (account-wide SavedVariables), keyed by
-- the full name GetUnitName("player", true) ("Viktor Oldlight"; UnitName gives only the first name here). Written on
-- login, level up, talent, gear and profession skill changes, and at logout, so a page or a sim reading the saved file
-- gets the level, stats, talents, professions and gear. The shape is documented in docs/EXPORT.md; keep the two in
-- step and bump SCHEMA when a field changes meaning.
--
-- Rules: every API is feature-detected and pcalled, and every answer goes through FS.IsSecret before anything else
-- touches it; a secret, missing or odd value is left out (nil), never guessed. A section that could not be read says so
-- in its `status`. Nothing is written in combat (stats and talents are not trusted there): the write waits for
-- PLAYER_REGEN_ENABLED, and a logout in combat keeps the last snapshot. Events are coalesced into one write after a
-- short delay. No chat output. FS.Config key "export.enabled" (default on) turns it off.

local addonName, FS = ...

local Export = {}
FS.CharacterExport = Export

Export.SCHEMA = 1
Export.CONFIG_KEY = "export.enabled"
Export.SETTING = {
    label = "Character snapshot",
    key = Export.CONFIG_KEY,
    tip = "Keeps a copy of this character's level, stats, talents, professions and gear in the addon's saved file, "
        .. "updated on login, level up, talent, gear and skill changes and logout. Nothing shows in game.",
}
if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(Export.CONFIG_KEY, true) end

local DELAY = 2           -- seconds between the first event of a burst and the write
local LOGIN_DELAY = 4     -- stats and item data settle a few seconds after the loading screen
local MAX_TREES, MAX_NODES = 4, 400

local STAT_NAMES = { "str", "agi", "sta", "int", "spi" }
local SCHOOLS = { "holy", "fire", "nature", "frost", "shadow", "arcane" } -- spell schools 2 to 7
local SLOTS = {
    { 1, "head" }, { 2, "neck" }, { 3, "shoulder" }, { 4, "shirt" }, { 5, "chest" }, { 6, "waist" },
    { 7, "legs" }, { 8, "feet" }, { 9, "wrist" }, { 10, "hands" }, { 11, "finger1" }, { 12, "finger2" },
    { 13, "trinket1" }, { 14, "trinket2" }, { 15, "back" }, { 16, "mainhand" }, { 17, "offhand" },
    { 18, "ranged" }, { 19, "tabard" },
}

-- Plain readers -------------------------------------------------------------------------------

local function Secret(v)
    return FS.IsSecret and FS.IsSecret(v) and true or false
end

-- A plain finite number, or nil.
local function Num(v)
    if Secret(v) or type(v) ~= "number" then return nil end
    if v ~= v or v == math.huge or v == -math.huge then return nil end
    return v
end

local function Str(v)
    if Secret(v) or type(v) ~= "string" or v == "" then return nil end
    return v
end

local function Tbl(v)
    if Secret(v) or type(v) ~= "table" then return nil end
    return v
end

-- The function at _G[ns][name] (or _G[name] with no ns), or nil.
local function Api(ns, name)
    local holder = ns and _G[ns] or _G
    if type(holder) ~= "table" then return nil end
    local fn = holder[name]
    return type(fn) == "function" and fn or nil
end

-- Every return of fn(...) packed by position (a nil in the middle keeps its place), or nil when fn is missing or throws.
local function Pack(ok, ...)
    if not ok then return nil end
    local r = {}
    for i = 1, select("#", ...) do r[i] = (select(i, ...)) end
    return r
end

local function Call(fn, ...)
    if not fn then return nil end
    return Pack(pcall(fn, ...))
end

local function CallNum(fn, ...)
    local r = Call(fn, ...)
    return r and Num(r[1]) or nil
end

local function CallTable(fn, ...)
    local r = Call(fn, ...)
    return r and Tbl(r[1]) or nil
end

local function Sum(...)
    local total, any = 0, false
    for i = 1, select("#", ...) do
        local v = select(i, ...)
        if v then total, any = total + v, true end
    end
    return any and total or nil
end

local function AddonVersion()
    local get = Api("C_AddOns", "GetAddOnMetadata") or Api(nil, "GetAddOnMetadata")
    local r = Call(get, addonName, "Version")
    return r and Str(r[1]) or nil
end

-- Sections ------------------------------------------------------------------------------------

local function ReadIdentity(snap)
    local r = Call(Api(nil, "GetUnitName"), "player", true)
    snap.name = r and Str(r[1]) or nil
    if not snap.name then
        r = Call(Api(nil, "UnitName"), "player")
        snap.name = r and Str(r[1]) or nil
    end
    r = Call(Api(nil, "GetRealmName"))
    snap.realm = r and Str(r[1]) or nil
    r = Call(Api(nil, "UnitRace"), "player")
    if r then snap.race, snap.raceToken = Str(r[1]), Str(r[2]) end
    r = Call(Api(nil, "UnitClass"), "player")
    if r then snap.class, snap.classToken = Str(r[1]), Str(r[2]) end
    r = Call(Api(nil, "UnitSex"), "player")
    snap.sex = r and Num(r[1]) or nil
    r = Call(Api(nil, "UnitGUID"), "player")
    snap.guid = r and Str(r[1]) or nil
    snap.level = CallNum(Api(nil, "UnitLevel"), "player")
    snap.xp = CallNum(Api(nil, "UnitXP"), "player")
    snap.xpMax = CallNum(Api(nil, "UnitXPMax"), "player")
    snap.restedXp = CallNum(Api(nil, "GetXPExhaustion"))
    snap.money = CallNum(Api(nil, "GetMoney"))
    local zone = {}
    r = Call(Api(nil, "GetRealZoneText"))
    zone.name = r and Str(r[1]) or nil
    r = Call(Api(nil, "GetSubZoneText"))
    zone.subzone = r and Str(r[1]) or nil
    zone.mapId = CallNum(Api("C_Map", "GetBestMapForUnit"), "player")
    snap.zone = zone
end

-- Specialization as the client names it. On Forever this answers with the class name (one tree per class), so the
-- talents are the real source of a build; the value is kept as the client reports it.
local function ReadSpec(snap)
    local idx = CallNum(Api("C_SpecializationInfo", "GetSpecialization")) or CallNum(Api(nil, "GetSpecialization"))
    snap.specIndex = idx
    if not idx or idx <= 0 then return end
    local info = Api("C_SpecializationInfo", "GetSpecializationInfo") or Api(nil, "GetSpecializationInfo")
    local r = Call(info, idx)
    if r then
        snap.specId = Num(r[1])
        snap.spec = Str(r[2])
    end
end

local function ReadStats(snap)
    local s = { base = {}, effective = {} }
    local unitStat = Api(nil, "UnitStat")
    for i, key in ipairs(STAT_NAMES) do
        local r = Call(unitStat, "player", i)
        if r then
            s.base[key] = Num(r[1])
            s.effective[key] = Num(r[2])
        end
    end

    local r = Call(Api(nil, "UnitAttackPower"), "player")
    if r then
        local base, pos, neg = Num(r[1]), Num(r[2]), Num(r[3])
        s.attackPower = Sum(base, pos, neg)
        s.attackPowerBase = base
    end
    r = Call(Api(nil, "UnitRangedAttackPower"), "player")
    if r then s.rangedAttackPower = Sum(Num(r[1]), Num(r[2]), Num(r[3])) end

    local bySchool, best = {}, nil
    local bonus = Api(nil, "GetSpellBonusDamage")
    for i, school in ipairs(SCHOOLS) do
        local v = CallNum(bonus, i + 1)
        bySchool[school] = v
        if v and (not best or v > best) then best = v end
    end
    s.spellPower = best
    s.spellPowerBySchool = bySchool
    s.healingPower = CallNum(Api(nil, "GetSpellBonusHealing"))

    local crit = {}
    crit.melee = CallNum(Api(nil, "GetCritChance"))
    crit.ranged = CallNum(Api(nil, "GetRangedCritChance"))
    local spellCrit = Api(nil, "GetSpellCritChance")
    local critBySchool, bestCrit = {}, nil
    for i, school in ipairs(SCHOOLS) do
        local v = CallNum(spellCrit, i + 1)
        critBySchool[school] = v
        if v and (not bestCrit or v > bestCrit) then bestCrit = v end
    end
    crit.spell = bestCrit
    crit.spellBySchool = critBySchool
    s.crit = crit

    -- Hit: the rating's percent plus the talent and gear modifier, each kept as read as well.
    local hit = {}
    local ratingBonus, rating = Api(nil, "GetCombatRatingBonus"), Api(nil, "GetCombatRating")
    local function RatingPair(id)
        id = Num(id)
        if not id then return nil, nil end
        return CallNum(rating, id), CallNum(ratingBonus, id)
    end
    local meleeRating, meleeRatingPct = RatingPair(_G.CR_HIT_MELEE)
    local rangedRating, rangedRatingPct = RatingPair(_G.CR_HIT_RANGED)
    local spellRating, spellRatingPct = RatingPair(_G.CR_HIT_SPELL)
    hit.meleeModifier = CallNum(Api(nil, "GetHitModifier"))
    hit.spellModifier = CallNum(Api(nil, "GetSpellHitModifier"))
    hit.meleeRating, hit.rangedRating, hit.spellRating = meleeRating, rangedRating, spellRating
    hit.melee = Sum(meleeRatingPct, hit.meleeModifier)
    hit.ranged = Sum(rangedRatingPct, hit.meleeModifier)
    hit.spell = Sum(spellRatingPct, hit.spellModifier)
    s.hit = hit

    r = Call(Api(nil, "UnitArmor"), "player")
    if r then
        s.armorBase = Num(r[1])
        s.armor = Num(r[2])
    end
    s.dodge = CallNum(Api(nil, "GetDodgeChance"))
    s.parry = CallNum(Api(nil, "GetParryChance"))
    s.block = CallNum(Api(nil, "GetBlockChance"))
    s.blockValue = CallNum(Api(nil, "GetShieldBlock"))
    s.expertise = CallNum(Api(nil, "GetExpertise"))
    s.haste = CallNum(Api(nil, "GetHaste"))
    r = Call(Api(nil, "UnitAttackSpeed"), "player")
    if r then s.attackSpeed = { mainhand = Num(r[1]), offhand = Num(r[2]) } end
    r = Call(Api(nil, "GetManaRegen"))
    if r then
        local base, casting = Num(r[1]), Num(r[2])
        s.mp5 = base and base * 5 or nil
        s.mp5Casting = casting and casting * 5 or nil
    end

    s.healthMax = CallNum(Api(nil, "UnitHealthMax"), "player")
    local powerMax = Api(nil, "UnitPowerMax")
    s.manaMax = CallNum(powerMax, "player", 0)
    r = Call(Api(nil, "UnitPowerType"), "player")
    if r then
        s.powerType = Num(r[1])
        s.powerToken = Str(r[2])
        if s.powerType then s.powerMax = CallNum(powerMax, "player", s.powerType) end
    end
    snap.stats = s
end

local function TraitName(def)
    local name = Str(def.overrideName)
    if name then return name end
    local id = Num(def.spellID)
    if not id then return nil end
    local r = Call(Api("C_Spell", "GetSpellName"), id)
    if r then return Str(r[1]) end
    r = Call(Api(nil, "GetSpellInfo"), id)
    return r and Str(r[1]) or nil
end

-- Talents from the trait system (what Forever's own talent frame reads): C_ClassTalents.GetActiveConfigID ->
-- C_Traits.GetConfigInfo (treeIDs) -> GetTreeNodes -> GetNodeInfo (activeRank, maxRanks, activeEntry) ->
-- GetEntryInfo (definitionID) -> GetDefinitionInfo (spellID, overrideName). Only nodes with a rank above 0 are listed.
local function ReadTalents(snap)
    local t = { list = {}, status = "unavailable" }
    snap.talents = t
    local T = _G.C_Traits
    local cfg = CallNum(Api("C_ClassTalents", "GetActiveConfigID"))
    if not (cfg and Tbl(T)) then return end
    t.configId = cfg
    local info = CallTable(Api("C_Traits", "GetConfigInfo"), cfg)
    local trees = info and Tbl(info.treeIDs)
    if not trees then return end
    local nodeFn, entryFn, defFn = Api("C_Traits", "GetNodeInfo"), Api("C_Traits", "GetEntryInfo"),
        Api("C_Traits", "GetDefinitionInfo")
    local treesFn = Api("C_Traits", "GetTreeNodes")
    t.treeIds = {}
    local seen, missed, spent = 0, 0, 0
    for ti = 1, math.min(#trees, MAX_TREES) do
        local treeId = Num(trees[ti])
        local nodes = treeId and CallTable(treesFn, treeId)
        if treeId then t.treeIds[#t.treeIds + 1] = treeId end
        if not nodes then
            missed = missed + 1
        else
            if #nodes > MAX_NODES then missed = missed + 1 end
            for ni = 1, math.min(#nodes, MAX_NODES) do
                local nodeId = Num(nodes[ni])
                local node = nodeId and CallTable(nodeFn, cfg, nodeId)
                local rank = node and (Num(node.activeRank) or Num(node.currentRank) or Num(node.ranksPurchased))
                if not rank then
                    missed = missed + 1
                else
                    seen = seen + 1
                    if rank > 0 then
                        local e = { nodeId = nodeId, treeId = treeId, rank = rank, maxRank = Num(node.maxRanks),
                            posX = Num(node.posX), posY = Num(node.posY) }
                        local active = Tbl(node.activeEntry)
                        local entryId = active and Num(active.entryID)
                        local ids = Tbl(node.entryIDs)
                        if not entryId and ids then entryId = Num(ids[1]) end
                        e.entryId = entryId
                        local entry = entryId and CallTable(entryFn, cfg, entryId)
                        local defId = entry and Num(entry.definitionID)
                        e.definitionId = defId
                        local def = defId and CallTable(defFn, defId)
                        if def then
                            e.spellId = Num(def.spellID)
                            e.name = TraitName(def)
                        end
                        if not e.name then missed = missed + 1 end
                        spent = spent + rank
                        t.list[#t.list + 1] = e
                    end
                end
            end
        end
    end
    t.pointsSpent = spent
    if seen == 0 then return end
    t.status = missed > 0 and "partial" or "ok"
    t.unread = missed > 0 and missed or nil
end

-- GetProfessions gives prof1, prof2, archaeology, fishing, cooking, firstAid as indices for GetProfessionInfo
-- (name, icon, skillLevel, maxSkillLevel, numAbilities, spellOffset, skillLine).
local PROFESSION_SLOTS = { "primary1", "primary2", "archaeology", "fishing", "cooking", "firstAid" }

local function ReadProfessions(snap)
    local p = { status = "unavailable" }
    snap.professions = p
    local r = Call(Api(nil, "GetProfessions"))
    if not r then return end
    local infoFn = Api(nil, "GetProfessionInfo")
    for i, slot in ipairs(PROFESSION_SLOTS) do
        local idx = Num(r[i])
        if idx then
            local info = Call(infoFn, idx)
            if info then
                p[slot] = { name = Str(info[1]), skill = Num(info[3]), max = Num(info[4]), skillLine = Num(info[7]) }
            end
        end
    end
    p.status = "ok"
end

-- item:itemID:enchantID:gem1:gem2:gem3:gem4:suffixID:uniqueID:... ; empty fields read as nil.
local function ParseLink(link)
    local body = link:match("|Hitem:([^|]+)|h") or link:match("^item:([^|]+)")
    if not body then return nil end
    local f, i = {}, 0
    for part in (body .. ":"):gmatch("([^:]*):") do
        i = i + 1
        f[i] = tonumber(part)
        if i >= 7 then break end
    end
    return f
end

local function ReadGear(snap)
    local g = {}
    snap.gear = g
    local idFn, linkFn = Api(nil, "GetInventoryItemID"), Api(nil, "GetInventoryItemLink")
    local levelFn = Api("C_Item", "GetDetailedItemLevelInfo") or Api(nil, "GetDetailedItemLevelInfo")
    local infoFn = Api("C_Item", "GetItemInfo") or Api(nil, "GetItemInfo")
    local missing = 0
    for _, s in ipairs(SLOTS) do
        local slot, key = s[1], s[2]
        local itemId = CallNum(idFn, "player", slot)
        if itemId then
            local item = { slot = slot, itemId = itemId }
            local r = Call(linkFn, "player", slot)
            local link = r and Str(r[1])
            item.link = link
            local f = link and ParseLink(link)
            if f then
                item.enchantId = f[2] ~= 0 and f[2] or nil
                local gems = {}
                for gi = 3, 6 do
                    if f[gi] and f[gi] ~= 0 then gems[#gems + 1] = f[gi] end
                end
                item.gems = #gems > 0 and gems or nil
                item.suffixId = f[7] ~= 0 and f[7] or nil
            end
            item.itemLevel = CallNum(levelFn, link or itemId)
            local info = Call(infoFn, link or itemId)
            if info then
                item.name = Str(info[1])
                item.quality = Num(info[3])
                if not item.itemLevel then item.itemLevel = Num(info[4]) end
            end
            if not (item.link and item.itemLevel and item.name) then missing = missing + 1 end
            g[key] = item
        end
    end
    -- Item data the client has not cached yet comes back empty; a later write fills it in.
    g.incomplete = missing > 0 and missing or nil
end

-- Snapshot and write --------------------------------------------------------------------------

-- A reader that throws leaves what it had filled and is named in snap.errors.
local function Guarded(fn, snap, key)
    if pcall(fn, snap) then return end
    snap.errors = snap.errors or {}
    snap.errors[#snap.errors + 1] = key
end

function Export.Snapshot()
    local snap = { schema = Export.SCHEMA, addonVersion = AddonVersion() }
    Guarded(ReadIdentity, snap, "identity")
    Guarded(ReadSpec, snap, "spec")
    Guarded(ReadStats, snap, "stats")
    Guarded(ReadTalents, snap, "talents")
    Guarded(ReadProfessions, snap, "professions")
    Guarded(ReadGear, snap, "gear")
    local now = CallNum(Api(nil, "GetServerTime")) or CallNum(Api(nil, "time"))
    snap.savedAt = now
    if now then
        local r = Call(Api(nil, "date"), "!%Y-%m-%dT%H:%M:%SZ", now)
        snap.savedAtText = r and Str(r[1]) or nil
    end
    return snap
end

local function Enabled()
    if not (FS.Config and FS.Config.Get) then return true end
    local ok, v = pcall(FS.Config.Get, Export.CONFIG_KEY)
    return not ok or v ~= false
end

local function InCombat()
    local r = Call(Api(nil, "InCombatLockdown"))
    if not r then return false end
    local v = r[1]
    if Secret(v) then return true end
    return v and true or false
end

local loaded, pending, scheduled = false, false, false

-- True when no base stat reads above 0: nothing real was read.
local function NoStats(stats)
    local base = type(stats) == "table" and stats.base
    if type(base) ~= "table" then return true end
    for _, key in ipairs(STAT_NAMES) do
        local v = base[key]
        if type(v) == "number" and v > 0 then return false end
    end
    return true
end

-- Returns true when a snapshot was written.
function Export.Write(reason)
    if not (loaded and Enabled()) then return false end
    if InCombat() then
        pending = true
        return false
    end
    pending = false
    local snap = Export.Snapshot()
    if not snap.name then return false end
    snap.reason = reason
    if type(ForeverSTUwaveExport) ~= "table" then ForeverSTUwaveExport = {} end
    local store = ForeverSTUwaveExport
    store.schema = Export.SCHEMA
    if type(store.characters) ~= "table" then store.characters = {} end
    -- At logout (a /reload too) the client can read every stat as 0 (live 2026-11-04): keep the last real stats,
    -- marked with when they were read.
    local last = store.characters[snap.name]
    if NoStats(snap.stats) and type(last) == "table" and type(last.stats) == "table" and not NoStats(last.stats) then
        snap.stats = last.stats
        snap.statsFrom = last.statsFrom or last.savedAt
    end
    store.characters[snap.name] = snap
    return true
end

local function Schedule(reason, delay)
    pending = true
    if scheduled then return end
    local after = Api("C_Timer", "After")
    if not after then
        Export.Write(reason)
        return
    end
    scheduled = true
    local ok = pcall(after, delay or DELAY, function()
        scheduled = false
        if pending then Export.Write(reason) end
    end)
    if not ok then
        scheduled = false
        Export.Write(reason)
    end
end
Export.Schedule = Schedule

local REASONS = {
    PLAYER_ENTERING_WORLD = "login",
    PLAYER_LEVEL_UP = "level",
    TRAIT_CONFIG_UPDATED = "talents",
    PLAYER_TALENT_UPDATE = "talents",
    CHARACTER_POINTS_CHANGED = "talents",
    ACTIVE_TALENT_GROUP_CHANGED = "talents",
    PLAYER_EQUIPMENT_CHANGED = "gear",
    SKILL_LINES_CHANGED = "skills",
    CHAT_MSG_SKILL = "skills",
}

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
local events = {}
for event in pairs(REASONS) do events[#events + 1] = event end
table.sort(events)
if FS.FrameHelpers and FS.FrameHelpers.RegisterEvents then
    FS.FrameHelpers.RegisterEvents(frame, events)
else
    for _, event in ipairs(events) do pcall(frame.RegisterEvent, frame, event) end
end

frame:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" then
        if arg1 == addonName then loaded = true end
    elseif event == "PLAYER_LOGOUT" then
        pcall(Export.Write, "logout")
    elseif event == "PLAYER_REGEN_ENABLED" then
        if pending then Schedule("combat end") end
    elseif event == "PLAYER_ENTERING_WORLD" then
        Schedule("login", LOGIN_DELAY)
    else
        Schedule(REASONS[event])
    end
end)
