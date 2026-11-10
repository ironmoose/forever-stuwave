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
--
-- SavedVariables reach disk only on /reload, logout or quit, so after a level up a small "Reload to save" button
-- can show (out of combat only); a click runs /reload through a secure macro button, a right click hides it. FS.Config key
-- "export.reloadButton" (default off) turns the button on.

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
Export.RELOAD_KEY = "export.reloadButton"
Export.RELOAD_SETTING = {
    label = "Reload button after level up",
    key = Export.RELOAD_KEY,
    tip = "Shows a Reload to save button after each level up, out of combat. The saved file is only written on a "
        .. "reload or logout; the button reloads so the new level reaches it now. Right click hides it. Off by default.",
}
if FS.Config and FS.Config.RegisterDefault then
    FS.Config.RegisterDefault(Export.CONFIG_KEY, true)
    FS.Config.RegisterDefault(Export.RELOAD_KEY, false)
end

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
local SECONDARY_BY_LINE = { [794] = "archaeology", [356] = "fishing", [185] = "cooking", [129] = "firstAid" }

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
                local line = Num(info[7])
                -- Secondaries are keyed by skill line, not position: Forever returns First Aid (129) in the
                -- slot retail gives archaeology (live 2026-11-10), so the position alone mislabels it.
                if i > 2 and line and SECONDARY_BY_LINE[line] then slot = SECONDARY_BY_LINE[line] end
                p[slot] = { name = Str(info[1]), skill = Num(info[3]), max = Num(info[4]), skillLine = line }
            end
        end
    end
    -- The classic skill list as a fallback: on some clients GetProfessions answers with no slots. Lines under the
    -- "Professions" and "Secondary Skills" headers (English client; a collapsed header hides its lines) fill the
    -- same slot names: the first two primaries, then fishing, cooking and first aid by name.
    if not (p.primary1 or p.fishing or p.cooking or p.firstAid) then
        local count = CallNum(Api(nil, "GetNumSkillLines"))
        local lineFn = Api(nil, "GetSkillLineInfo")
        local header
        local SECONDARY = { Fishing = "fishing", Cooking = "cooking", ["First Aid"] = "firstAid" }
        for i = 1, (lineFn and count or 0) do
            local info = Call(lineFn, i)
            local name = info and Str(info[1])
            if name and info[2] and not Secret(info[2]) then
                header = name
            elseif name and (header == "Professions" or header == "Secondary Skills") then
                local entry = { name = name, skill = Num(info[4]), max = Num(info[7]) }
                local slot = SECONDARY[name] or (not p.primary1 and "primary1") or (not p.primary2 and "primary2")
                if slot and not p[slot] then p[slot] = entry end
            end
        end
    end
    p.status = "ok"
end

-- True when a professions table holds no learned slot.
local function NoProfessions(p)
    if type(p) ~= "table" then return true end
    for _, slot in ipairs(PROFESSION_SLOTS) do
        if type(p[slot]) == "table" then return false end
    end
    return true
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

-- Bags and bank ------------------------------------------------------------------------------

local bankOpen = false

-- One container slot, from C_Container (a table) or the old global (positional returns), or nil when empty.
local function SlotInfo(bag, slot)
    local r = Call(Api("C_Container", "GetContainerItemInfo"), bag, slot)
    local t = r and Tbl(r[1])
    if t then return Num(t.itemID), Str(t.hyperlink), Num(t.stackCount), Num(t.quality) end
    r = Call(Api(nil, "GetContainerItemInfo"), bag, slot)
    if r and r[1] ~= nil then return Num(r[10]), Str(r[7]), Num(r[2]), Num(r[4]) end
end

-- Reads the given container ids into { slots, free, items = { {bag, slot, itemId, name, count, quality, itemLevel,
-- link} }, incomplete }.
local function ReadContainers(ids)
    local numFn = Api("C_Container", "GetContainerNumSlots") or Api(nil, "GetContainerNumSlots")
    local levelFn = Api("C_Item", "GetDetailedItemLevelInfo") or Api(nil, "GetDetailedItemLevelInfo")
    local infoFn = Api("C_Item", "GetItemInfo") or Api(nil, "GetItemInfo")
    local out = { slots = 0, free = 0, items = {} }
    local missing = 0
    for _, bag in ipairs(ids) do
        local n = CallNum(numFn, bag) or 0
        out.slots = out.slots + n
        for slot = 1, n do
            local itemId, link, count, quality = SlotInfo(bag, slot)
            if itemId or link then
                local item = { bag = bag, slot = slot, itemId = itemId, link = link, count = count or 1, quality = quality }
                item.itemLevel = CallNum(levelFn, link or itemId)
                local info = Call(infoFn, link or itemId)
                if info then
                    item.name = Str(info[1])
                    if not item.quality then item.quality = Num(info[3]) end
                    if not item.itemLevel then item.itemLevel = Num(info[4]) end
                end
                if not (item.link and item.name) then missing = missing + 1 end
                out.items[#out.items + 1] = item
            else
                out.free = out.free + 1
            end
        end
    end
    out.incomplete = missing > 0 and missing or nil
    return out
end

local function ReadBags(snap)
    local last = type(NUM_BAG_SLOTS) == "number" and NUM_BAG_SLOTS or 4
    local ids = {}
    for bag = 0, last do ids[#ids + 1] = bag end
    snap.bags = ReadContainers(ids)
    -- The bank reads only while its window is open; otherwise the write carries the last read (see Export.Write).
    if bankOpen then
        local bankIds = { type(BANK_CONTAINER) == "number" and BANK_CONTAINER or -1 }
        local extra = type(NUM_BANKBAGSLOTS) == "number" and NUM_BANKBAGSLOTS or 7
        for bag = last + 1, last + extra do bankIds[#bankIds + 1] = bag end
        snap.bank = ReadContainers(bankIds)
    end
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
    Guarded(ReadBags, snap, "bags")
    local now = CallNum(Api(nil, "GetServerTime")) or CallNum(Api(nil, "time"))
    snap.savedAt = now
    if now then
        local r = Call(Api(nil, "date"), "!%Y-%m-%dT%H:%M:%SZ", now)
        snap.savedAtText = r and Str(r[1]) or nil
    end
    return snap
end

local function On(key)
    if not (FS.Config and FS.Config.Get) then return true end
    local ok, v = pcall(FS.Config.Get, key)
    return not ok or v ~= false
end

local function Enabled() return On(Export.CONFIG_KEY) end

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

-- The same logout teardown (live 2026-11-10, reason "logout") read money, xp and xpMax as 0, the zone and gear empty,
-- talents unavailable and professions slotless. A section read that way keeps the last write's value, and `kept`
-- names each one. xpMax 0 is the tell for money and xp: below the level cap the xp bar is never 0, so a 0 there while
-- the last write had a real bar means a torn read.
local function GearEmpty(g)
    if type(g) ~= "table" then return true end
    for k, v in pairs(g) do
        if k ~= "incomplete" and type(v) == "table" then return false end
    end
    return true
end

local function KeepTorn(snap, last)
    local kept = {}
    local function keep(key) kept[#kept + 1] = key end
    if (snap.xpMax or 0) == 0 and type(last.xpMax) == "number" and last.xpMax > 0 then
        snap.money, snap.xp, snap.xpMax, snap.restedXp = last.money, last.xp, last.xpMax, last.restedXp
        keep("money"); keep("xp")
    end
    if GearEmpty(snap.gear) and not GearEmpty(last.gear) then snap.gear = last.gear; keep("gear") end
    if type(snap.zone) ~= "table" or not snap.zone.name then
        if type(last.zone) == "table" and last.zone.name then snap.zone = last.zone; keep("zone") end
    end
    local t, lt = snap.talents, last.talents
    if (type(t) ~= "table" or t.status == "unavailable") and type(lt) == "table" and lt.status ~= "unavailable" then
        snap.talents = lt; keep("talents")
    end
    local b, lb = snap.bags, last.bags
    if (type(b) ~= "table" or b.slots == 0) and type(lb) == "table" and (lb.slots or 0) > 0 then
        snap.bags = lb; keep("bags")
    end
    -- Not torn, just not open: the bank keeps its last read, with its own bankFrom stamp, and is not named in kept.
    if snap.bank == nil and type(last.bank) == "table" then
        snap.bank, snap.bankFrom = last.bank, last.bankFrom or last.savedAt
    end
    if NoProfessions(snap.professions) and not NoProfessions(last.professions) then
        snap.professions = last.professions; keep("professions")
    end
    snap.kept = #kept > 0 and kept or nil
    if snap.kept then snap.keptFrom = last.keptFrom or last.savedAt end
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
    if type(last) == "table" then KeepTorn(snap, last) end
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

-- Reload button ------------------------------------------------------------------------------

local RELOAD_W, RELOAD_H = 140, 24
local reloadButton, reloadWanted = nil, false

-- A secure macro button running /reload: ReloadUI and C_UI.Reload are protected on this client (a call from our
-- OnClick is ADDON_ACTION_BLOCKED, live 2026-11-04). Only the left click has a type, so a right click runs nothing
-- and just hides it. Secure buttons cannot be shown or hidden in combat, so nothing here touches it then.
local function BuildReloadButton()
    local b = CreateFrame("Button", "ForeverSTUwaveReloadButton", UIParent, "SecureActionButtonTemplate")
    b:SetFrameStrata("HIGH")
    b:SetSize(RELOAD_W, RELOAD_H)
    b:SetPoint("TOP", UIParent, "TOP", 0, -120)
    -- AnyUp+AnyDown: the click is acted on at whichever edge ActionButtonUseKeyDown picks.
    b:RegisterForClicks("AnyUp", "AnyDown")
    b:SetAttribute("type1", "macro")
    b:SetAttribute("macrotext1", "/reload")
    -- A Button needs a font object before it can hold text.
    b:SetNormalFontObject(_G.GameFontNormal)
    b:SetText("Reload to save")
    b:SetScript("OnEnter", function(self)
        if not GameTooltip then return end
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:SetText("Reloads the UI so the character snapshot is written to the saved file. "
            .. "Right click hides this.", 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    b:HookScript("OnClick", function(self, mouse)
        if mouse ~= "RightButton" or InCombat() then return end
        reloadWanted = false
        self:Hide()
    end)
    if FS.ButtonSkins and FS.ButtonSkins.SkinTextButton then FS.ButtonSkins.SkinTextButton(b, { accent = "cyan" }) end
    b:Hide()
    return b
end

-- Shows the button when one is wanted, the switch is on and the player is out of combat; hides it otherwise.
-- PLAYER_REGEN_DISABLED fires before the lockdown starts, so the hide on entering combat is still allowed.
local function UpdateReloadButton(enteringCombat)
    if InCombat() then return end
    local show = reloadWanted and not enteringCombat and Enabled() and On(Export.RELOAD_KEY)
    if show and not reloadButton then
        local ok, b = pcall(BuildReloadButton)
        if not ok then return end
        reloadButton = b
    end
    if not reloadButton then return end
    if show then reloadButton:Show() else reloadButton:Hide() end
end
Export.UpdateReloadButton = UpdateReloadButton
function Export.ReloadButton() return reloadButton end

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
    BAG_UPDATE_DELAYED = "bags",
    BANKFRAME_OPENED = "bank",
    PLAYERBANKSLOTS_CHANGED = "bank",
}

local frame = CreateFrame("Frame")
frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
local events = { "BANKFRAME_CLOSED" }
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
        UpdateReloadButton()
    elseif event == "PLAYER_REGEN_DISABLED" then
        UpdateReloadButton(true)
    elseif event == "BANKFRAME_CLOSED" then
        -- A visit shorter than the write delay would otherwise close before the bank is read.
        if pending then Export.Write("bank") end
        bankOpen = false
    elseif event == "PLAYER_ENTERING_WORLD" then
        Schedule("login", LOGIN_DELAY)
    else
        if event == "BANKFRAME_OPENED" then bankOpen = true end
        Schedule(REASONS[event])
        if event == "PLAYER_LEVEL_UP" then
            reloadWanted = true
            UpdateReloadButton()
        end
    end
end)
