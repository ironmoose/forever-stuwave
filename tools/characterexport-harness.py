#!/usr/bin/env python3
"""Runs the real Modules/Diagnostics/CharacterExport.lua headless against a mocked client.

The checks pin: a write lands in ForeverSTUwaveExport.characters keyed by the full GetUnitName("player", true) name
with every documented field filled (identity, XP, zone, money, base and effective stats, attack and spell power, crit,
hit, armor, health and mana, talents by name and id, professions with Cooking / First Aid / Fishing, gear per slot with
item id, link, enchant, gems and item level, savedAt and the addon version); a secret answer is left out and never
touched; nothing is written in combat and the deferred write happens after PLAYER_REGEN_ENABLED; a logout in combat keeps
the last snapshot; the config switch stops writes; events in one burst coalesce into one write; nothing prints. A trade
skill window read (C_TradeSkillUI, as the client documents it) puts each profession's known recipes (difficulty word,
craftable count, reagents with name, item id, count needed and owned) in `professions.<slot>.recipes` with its own
capturedAt; the list survives writes made with no window open, a logout teardown and a new session, is dropped when the
slot's profession changes, and is not recorded for a linked, guild or NPC window, an unmatched profession, in combat or
with the switch off.

The mock is strict. It is NOT the real client.

    python3 tools/characterexport-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "forever-stuwave/Modules/Diagnostics/CharacterExport.lua"

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end

PRINTS = {}
function print(...) PRINTS[#PRINTS + 1] = table.concat({ ... }, " ") end
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) PRINTS[#PRINTS + 1] = m end }

SECRET = setmetatable({}, {
    __index = function() error("SECRET_OP: index", 2) end, __newindex = function() error("SECRET_OP: write", 2) end,
    __eq = function() error("SECRET_OP: compare", 2) end, __lt = function() error("SECRET_OP: compare", 2) end,
    __le = function() error("SECRET_OP: compare", 2) end, __add = function() error("SECRET_OP: arith", 2) end,
    __concat = function() error("SECRET_OP: concat", 2) end,
})

SETTINGS = {}
FS = {
    IsSecret = function(v) return rawequal(v, SECRET) end,
    Config = {
        RegisterDefault = function(k, v) if SETTINGS[k] == nil then SETTINGS[k] = v end end,
        Get = function(k) return SETTINGS[k] end,
    },
}

-- frames and timers
local FrameMT = {}
FrameMT.__index = FrameMT
function FrameMT:RegisterEvent(e) self.events[e] = true end
function FrameMT:SetScript(n, fn) self.scripts[n] = fn end
function FrameMT:Show() self.shown = true end
function FrameMT:Hide() self.shown = false end
function FrameMT:SetText(t) self.text = t end
function FrameMT:SetAttribute(k, v) self.attrs = self.attrs or {}; self.attrs[k] = v end
function FrameMT:HookScript(n, fn)
    local prev = self.scripts[n]
    self.scripts[n] = function(...) if prev then prev(...) end fn(...) end
end
for _, m in ipairs({ "SetFrameStrata", "SetSize", "SetPoint", "RegisterForClicks", "SetNormalFontObject" }) do
    FrameMT[m] = function() end
end
UIParent = {}
-- ReloadUI is protected on the release client: a call from addon code is blocked
function ReloadUI() error("ADDON_ACTION_BLOCKED: Reload()") end
FRAMES = {}
function CreateFrame(kind, name, parent, template)
    local f = setmetatable({ events = {}, scripts = {}, template = template }, FrameMT)
    FRAMES[#FRAMES + 1] = f
    return f
end
function fire(event, ...)
    for _, f in ipairs(FRAMES) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
    end
end
TIMERS = {}
C_Timer = { After = function(d, fn) TIMERS[#TIMERS + 1] = { d = d, fn = fn } end }
function runTimers()
    local list = TIMERS
    TIMERS = {}
    for _, t in ipairs(list) do t.fn() end
    return #list
end

-- client state
COMBAT = false
function InCombatLockdown() return COMBAT end
NAME = "Viktor Oldlight"
function GetUnitName(unit, full) return NAME end
function UnitName() return "Viktor" end
function GetRealmName() return "Forever" end
function UnitRace() return "Tauren", "Tauren" end
function UnitClass() return "Shaman", "SHAMAN" end
function UnitSex() return 2 end
function UnitGUID() return "Player-1-0001" end
LEVEL = 24
function UnitLevel() return LEVEL end
function UnitXP() return 1200 end
function UnitXPMax() return 9000 end
function GetXPExhaustion() return 4500 end
function GetMoney() return 123456 end
function GetRealZoneText() return "The Barrens" end
function GetSubZoneText() return "Crossroads" end
C_Map = { GetBestMapForUnit = function() return 1413 end }
C_SpecializationInfo = {
    GetSpecialization = function() return 1 end,
    GetSpecializationInfo = function() return 262, "Shaman", "", 0, "DAMAGER", 4, 0 end,
}
C_AddOns = { GetAddOnMetadata = function(_, field) if field == "Version" then return "0.1.0-test" end end }
NOW = 1793750400
function GetServerTime() return NOW end
date, time = os.date, os.time

STATS = { { 40, 52 }, { 30, 41 }, { 45, 60 }, { 35, 38 }, { 50, 55 } }
function UnitStat(_, i) local s = STATS[i]; return s[1], s[2], s[2] - s[1], 0 end
function UnitAttackPower() return 120, 20, -5 end
function UnitRangedAttackPower() return 30, 0, 0 end
function GetSpellBonusDamage(school) return school == 4 and 25 or 10 end
function GetSpellBonusHealing() return 18 end
function GetCritChance() return 6.5 end
function GetRangedCritChance() return 4.25 end
function GetSpellCritChance(school) return school == 4 and 5.5 or 3 end
CR_HIT_MELEE, CR_HIT_RANGED, CR_HIT_SPELL = 6, 7, 8
function GetCombatRating(id) return id * 2 end
function GetCombatRatingBonus(id) return id / 4 end
function GetHitModifier() return 1 end
function GetSpellHitModifier() return 3 end
function UnitArmor() return 900, 1100 end
function GetDodgeChance() return 5 end
function GetParryChance() return 0 end
function GetBlockChance() return 0 end
function GetShieldBlock() return 0 end
function GetExpertise() return 0 end
function GetHaste() return 0 end
function UnitAttackSpeed() return 3.4, nil end
function GetManaRegen() return 2, 0.5 end
function UnitHealthMax() return 850 end
function UnitPowerMax(_, p) return p == 0 and 700 or 100 end
function UnitPowerType() return 0, "MANA" end

-- talents: one tree, three nodes; node 2 has no rank
C_ClassTalents = { GetActiveConfigID = function() return 77 end }
NODES = {
    [101] = { activeRank = 5, maxRanks = 5, posX = 1, posY = 2, activeEntry = { entryID = 1001 } },
    [102] = { activeRank = 0, maxRanks = 3, activeEntry = { entryID = 1002 } },
    [103] = { activeRank = 2, maxRanks = 2, entryIDs = { 1003 } },
}
C_Traits = {
    GetConfigInfo = function() return { treeIDs = { 9 } } end,
    GetTreeNodes = function() return { 101, 102, 103 } end,
    GetNodeInfo = function(_, id) return NODES[id] end,
    GetEntryInfo = function(_, id) return { definitionID = id + 1000 } end,
    GetDefinitionInfo = function(id)
        if id == 2001 then return { spellID = 16259 } end
        return { spellID = 17485, overrideName = "Improved Lightning Shield" }
    end,
}
C_Spell = { GetSpellName = function(id) if id == 16259 then return "Thundering Strikes" end end }

-- professions: Skinning, Leatherworking, no archaeology, Fishing, Cooking, First Aid
PROFS = {
    [1] = { "Skinning", 0, 110, 150, 0, 0, 393 },
    [2] = { "Leatherworking", 0, 95, 150, 0, 0, 165 },
    [4] = { "Fishing", 0, 20, 75, 0, 0, 356 },
    [5] = { "Cooking", 0, 40, 75, 0, 0, 185 },
    [6] = { "First Aid", 0, 60, 75, 0, 0, 129 },
}
function GetProfessions() return 1, 2, nil, 4, 5, 6 end
function GetProfessionInfo(i) return unpack(PROFS[i]) end

-- gear: head enchanted, mainhand with a gem, chest uncached
GEAR = {
    [1] = { 1111, "|cff1eff00|Hitem:1111:15:0:0:0:0:0:0:24|h[Hat]|h|r", 20 },
    [5] = { 5555, nil, nil },
    [16] = { 1616, "|cff0070dd|Hitem:1616:0:3001:0:0:0:-12:0:24|h[Axe]|h|r", 25 },
}
function GetInventoryItemID(_, slot) return GEAR[slot] and GEAR[slot][1] end
function GetInventoryItemLink(_, slot) return GEAR[slot] and GEAR[slot][2] end
C_Item = {
    GetDetailedItemLevelInfo = function(x)
        for _, g in pairs(GEAR) do if g[2] == x then return g[3] end end
    end,
    GetItemInfo = function(x)
        for _, g in pairs(GEAR) do if g[2] and g[2] == x then return x:match("%[(.-)%]"), x, 2, g[3] end end
        if type(x) == "string" and x:match("|Hitem:(%d+)") then
            local id = tonumber(x:match("|Hitem:(%d+)"))
            if ITEMLEVEL and ITEMLEVEL[id] then return x:match("%[(.-)%]"), x, 1, ITEMLEVEL[id] end
        end
    end,
}

-- bags: backpack with a stack of fish and a cached ring; bag 1 empty 6 slots; bank: one item in the bank slots
BAGS = {
    [0] = { [1] = { itemID = 6303, stackCount = 7, quality = 1, hyperlink = "|cffffffff|Hitem:6303::::::::12|h[Raw Slitherskin Mackerel]|h|r" },
            [3] = { itemID = 2222, stackCount = 1, quality = 2, hyperlink = "|cff1eff00|Hitem:2222::::::::12|h[Ring]|h|r" } },
    [1] = {},
    [-1] = { [2] = { itemID = 4444, stackCount = 3, quality = 1, hyperlink = "|cffffffff|Hitem:4444::::::::12|h[Cloth]|h|r" } },
}
BAGSIZE = { [0] = 4, [1] = 6, [-1] = 28 }
C_Container = {
    GetContainerNumSlots = function(bag) return BAGSIZE[bag] or 0 end,
    GetContainerItemInfo = function(bag, slot) return BAGS[bag] and BAGS[bag][slot] end,
}
ITEMLEVEL = { [6303] = 5, [2222] = 18, [4444] = 10 }

-- quest log: a zone header, one quest in progress, one complete; three quests turned in
QLOG = {
    { title = "Mulgore", isHeader = true },
    { title = "The Hunt Continues", questID = 747, level = 3, isHeader = false },
    { title = "Rite of Strength", questID = 757, level = 4, isHeader = false },
}
QOBJ = {
    [747] = { { text = "Plainstrider Meat: 3/7", type = "item", finished = false, numFulfilled = 3, numRequired = 7 } },
    [757] = { { text = "Bristleback Interloper slain: 12/12", type = "monster", finished = true, numFulfilled = 12, numRequired = 12 } },
}
C_QuestLog = {
    GetNumQuestLogEntries = function() return #QLOG end,
    GetInfo = function(i) return QLOG[i] end,
    IsComplete = function(id) return id == 757 end,
    GetQuestObjectives = function(id) return QOBJ[id] end,
    GetAllCompletedQuestIDs = function() return { 750, 744, 3376 } end,
}

-- currencies: one header, Merchant's Favor (id only in the link), Honor (id in the table)
CURR = {
    { name = "Forever", isHeader = true },
    { name = "Merchant's Favor", isHeader = false, quantity = 37, maxQuantity = 0 },
    { name = "Honor Points", isHeader = false, quantity = 120, currencyID = 1901 },
}
C_CurrencyInfo = {
    GetCurrencyListSize = function() return #CURR end,
    GetCurrencyListInfo = function(i) return CURR[i] end,
    GetCurrencyListLink = function(i) if i == 2 then return "|cffffffff|Hcurrency:3456:0|h[Merchant's Favor]|h|r" end end,
}
-- reputations: a header, Thunder Bluff (Honored 3000/12000), Durotar Supply and Logistics (Friendly 250/6000)
FACTIONS = {
    { name = "Horde", factionID = 67, isHeader = true, isHeaderWithRep = false },
    { name = "Thunder Bluff", factionID = 81, reaction = 6, currentStanding = 12000, currentReactionThreshold = 9000,
      nextReactionThreshold = 21000, isHeader = false },
    { name = "Durotar Supply and Logistics", factionID = 2700, reaction = 5, currentStanding = 3250,
      currentReactionThreshold = 3000, nextReactionThreshold = 9000, isHeader = false },
}
C_Reputation = {
    GetNumFactions = function() return #FACTIONS end,
    GetFactionDataByIndex = function(i) return FACTIONS[i] end,
}
FACTION_STANDING_LABEL5, FACTION_STANDING_LABEL6 = "Friendly", "Honored"

-- item stats by link: the hat (random suffix) and the ring in the backpack; everything else has none
C_Item.GetItemStats = function(link)
    if type(link) ~= "string" then return nil end
    if link:find("Hitem:1111") then return { ITEM_MOD_STAMINA_SHORT = 2, ITEM_MOD_INTELLECT_SHORT = 2, RESISTANCE0_NAME = 45 } end
    if link:find("Hitem:2222") then return { ITEM_MOD_AGILITY_SHORT = 3 } end
    return {}
end

-- items by id: names (4291 is not cached yet), how many the bags hold, and the load requests made
ITEMNAMES = { [2318] = "Light Leather", [2320] = "Coarse Thread", [2325] = "Black Dye", [5001] = "Tuft of Fur",
    [5002] = "Thick Tuft of Fur", [5003] = "Dense Tuft of Fur", [769] = "Chunk of Boar Meat", [6889] = "Small Egg",
    [2678] = "Mild Spices", [2589] = "Linen Cloth" }
ITEMCOUNT = { [2318] = 14, [2320] = 3, [4291] = 2, [5001] = 1, [5002] = 2, [5003] = 4, [769] = 5, [2589] = 9 }
LOADREQ = {}
C_Item.GetItemNameByID = function(id) return ITEMNAMES[id] end
C_Item.GetItemCount = function(id) return ITEMCOUNT[id] or 0 end
C_Item.RequestLoadItemDataByID = function(id) LOADREQ[#LOADREQ + 1] = id end

-- trade skill window (the modern C_TradeSkillUI): closed until a case opens one. Names and ids are test data.
Enum = {
    TradeskillRelativeDifficulty = { Optimal = 0, Medium = 1, Easy = 2, Trivial = 3 },
    CraftingReagentType = { Modifying = 0, Basic = 1, Finishing = 2, Automatic = 3 },
}
local function slot(kind, qty, ...)
    local reagents = {}
    for _, id in ipairs({ ... }) do reagents[#reagents + 1] = { itemID = id } end
    return { reagentType = kind, quantityRequired = qty, reagents = reagents, required = kind == 1 }
end
RECIPES = {
    [2152] = { name = "Light Armor Kit", recipeID = 2152, skillLineAbilityID = 9152, learned = true, relativeDifficulty = 0 },
    [2149] = { name = "Handstitched Leather Boots", recipeID = 2149, skillLineAbilityID = 9149, learned = true, relativeDifficulty = 3 },
    [3753] = { name = "Fine Leather Belt", recipeID = 3753, skillLineAbilityID = 9753, learned = true, relativeDifficulty = 1 },
    [3756] = { name = "Embossed Leather Gloves", recipeID = 3756, skillLineAbilityID = 9756, learned = true, relativeDifficulty = 2 },
    [4001] = { name = "Mystery Recipe", recipeID = 4001, learned = true },
    [9999] = { name = "Cured Heavy Hide", recipeID = 9999, learned = false, relativeDifficulty = 0 },
    [2538] = { name = "Roasted Boar Meat", recipeID = 2538, skillLineAbilityID = 9538, learned = true, relativeDifficulty = 0 },
    [8604] = { name = "Herb Baked Egg", recipeID = 8604, skillLineAbilityID = 9604, learned = true, relativeDifficulty = 2 },
    [3275] = { name = "Linen Bandage", recipeID = 3275, skillLineAbilityID = 9275, learned = true, relativeDifficulty = 1 },
}
SCHEMATICS = {
    [2152] = { outputItemID = 2304, reagentSlotSchematics = { slot(1, 1, 2318) } },
    [2149] = { outputItemID = 2307, reagentSlotSchematics = { slot(1, 2, 2318), slot(1, 1, 2320), slot(2, 1, 2325) } },
    [3753] = { outputItemID = 3779, reagentSlotSchematics = { slot(1, 6, 2318), slot(1, 2, 4291) } },
    [3756] = { outputItemID = 4237, reagentSlotSchematics = { slot(1, 3, 5001, 5002, 5003), slot(1, 1, 2320) } },
    [2538] = { outputItemID = 2681, reagentSlotSchematics = { slot(1, 1, 769) } },
    [8604] = { outputItemID = 6888, reagentSlotSchematics = { slot(1, 1, 6889), slot(1, 1, 2678) } },
    [3275] = { outputItemID = 1251, reagentSlotSchematics = { slot(1, 1, 2589) } },
}
CRAFTABLE = { [2152] = 14, [2149] = 3, [3756] = 1, [2538] = 5, [8604] = 0, [3275] = 9 }
WINDOWS = {
    leatherworking = {
        base = { professionID = 165, professionName = "Leatherworking", skillLevel = 95, maxSkillLevel = 150 },
        child = { professionID = 2800, professionName = "Classic Leatherworking", parentProfessionID = 165,
            parentProfessionName = "Leatherworking" },
        ids = { 2152, 2149, 3753, 3756, 4001, 9999 },
    },
    cooking = {
        base = { professionID = 185, professionName = "Cooking", skillLevel = 40, maxSkillLevel = 75 },
        child = { professionID = 0 },   -- an NPC style window answers with no child line
        ids = { 2538, 8604 },
    },
    firstaid = {
        base = { professionID = 129, professionName = "First Aid", skillLevel = 60, maxSkillLevel = 75 },
        child = { professionID = 0 },
        ids = { 3275 },
    },
    alchemy = {
        base = { professionID = 171, professionName = "Alchemy", skillLevel = 10, maxSkillLevel = 75 },
        child = { professionID = 0 },
        ids = { 2538 },
    },
}
TS = { ready = false, changing = false, linked = false, guild = false, guildMember = false, npc = false, ids = {} }
TSCALLS, WROTE = 0, nil
local function mutator(name) return function() WROTE = name end end
C_TradeSkillUI = {
    IsTradeSkillReady = function() return TS.ready end,
    IsDataSourceChanging = function() return TS.changing end,
    IsTradeSkillLinked = function() return TS.linked, TS.linked and "Mira" or nil end,
    IsTradeSkillGuild = function() return TS.guild end,
    IsTradeSkillGuildMember = function() return TS.guildMember end,
    IsNPCCrafting = function() return TS.npc end,
    GetBaseProfessionInfo = function() return TS.base end,
    GetChildProfessionInfo = function() return TS.child end,
    GetAllRecipeIDs = function() TSCALLS = TSCALLS + 1; return TS.ids end,
    GetRecipeInfo = function(id) return RECIPES[id] end,
    GetRecipeSchematic = function(id, isRecraft) return SCHEMATICS[id] end,
    GetCraftableCount = function(id) return CRAFTABLE[id] or 0 end,
}
for _, name in ipairs({ "SetShowLearned", "SetShowUnlearned", "SetRecipeItemNameFilter", "SetOnlyShowMakeableRecipes",
    "OpenTradeSkill", "CloseTradeSkill", "SetProfessionChildSkillLineID", "CraftRecipe", "SetRecipeFavorite" }) do
    C_TradeSkillUI[name] = mutator(name)
end
function openWindow(name)
    local w = WINDOWS[name]
    TS.base, TS.child, TS.ids = w.base, w.child, w.ids
    TS.ready, TS.changing, TS.linked, TS.guild, TS.guildMember, TS.npc = true, false, false, false, false, false
    fire("TRADE_SKILL_SHOW")
    fire("TRADE_SKILL_DATA_SOURCE_CHANGED")
    fire("TRADE_SKILL_LIST_UPDATE")
end
function closeWindow()
    TS.ready = false
    fire("TRADE_SKILL_CLOSE")
end
-- Runs timers until none are left (the read, the write it schedules, a retry); bounded so a loop fails instead of hanging.
function settle()
    for i = 1, 10 do
        if runTimers() == 0 then return i - 1 end
    end
    error("timers kept rescheduling", 2)
end
-- The note on a read that recorded nothing lands with the next write; a logout write is the quickest.
function flush() fire("PLAYER_LOGOUT") end
-- A new session: the addon starts again with the saved table the client loaded.
function reload()
    local keep = ForeverSTUwaveExport
    FRAMES, TIMERS = {}, {}
    local fn = assert(loadstring(SOURCE_TEXT, "@CharacterExport.lua"))
    fn("forever-stuwave", FS)
    ForeverSTUwaveExport = keep
    fire("ADDON_LOADED", "forever-stuwave")
    return FS.CharacterExport
end

function load()
    ForeverSTUwaveExport = nil
    local fn = assert(loadstring(SOURCE_TEXT, "@CharacterExport.lua"))
    fn("forever-stuwave", FS)
    fire("ADDON_LOADED", "forever-stuwave")
    return FS.CharacterExport
end
function login()
    fire("PLAYER_ENTERING_WORLD", true, false)
    return runTimers()
end
function saved() return ForeverSTUwaveExport and ForeverSTUwaveExport.characters[NAME] end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("login_writes_every_field_keyed_by_full_name")(r"""
load()
check(login() == 1, "one timer for the login write")
local c = saved()
check(c, "written under the full name")
check(ForeverSTUwaveExport.schema == 1 and c.schema == 1, "schema")
check(c.name == "Viktor Oldlight" and c.realm == "Forever" and c.race == "Tauren" and c.class == "Shaman", "identity")
check(c.classToken == "SHAMAN" and c.level == 24 and c.xp == 1200 and c.xpMax == 9000 and c.restedXp == 4500, "xp")
check(c.money == 123456 and c.zone.name == "The Barrens" and c.zone.subzone == "Crossroads" and c.zone.mapId == 1413, "zone")
check(c.spec == "Shaman" and c.specId == 262, "spec as the client names it")
local s = c.stats
check(s.base.str == 40 and s.effective.str == 52 and s.effective.spi == 55 and s.base.int == 35, "stats")
check(s.attackPower == 135 and s.attackPowerBase == 120 and s.rangedAttackPower == 30, "attack power")
check(s.spellPower == 25 and s.spellPowerBySchool.nature == 25 and s.healingPower == 18, "spell power")
check(s.crit.melee == 6.5 and s.crit.spell == 5.5 and s.crit.ranged == 4.25, "crit")
check(s.hit.melee == 2.5 and s.hit.spell == 5 and s.hit.meleeRating == 12, "hit = rating percent + modifier")
check(s.armor == 1100 and s.armorBase == 900 and s.healthMax == 850 and s.manaMax == 700, "armor, health, mana")
check(s.mp5 == 10 and s.attackSpeed.mainhand == 3.4, "regen and speed")
local t = c.talents
check(t.status == "ok" and t.configId == 77 and t.treeIds[1] == 9 and t.pointsSpent == 7, "talent header")
check(#t.list == 2, "only ranked nodes listed")
check(t.list[1].name == "Thundering Strikes" and t.list[1].spellId == 16259 and t.list[1].rank == 5
    and t.list[1].maxRank == 5 and t.list[1].nodeId == 101 and t.list[1].entryId == 1001
    and t.list[1].definitionId == 2001 and t.list[1].posX == 1, "talent by name and id")
check(t.list[2].name == "Improved Lightning Shield" and t.list[2].entryId == 1003, "entryIDs fallback, override name")
local p = c.professions
check(p.status == "ok" and p.primary1.name == "Skinning" and p.primary1.skill == 110 and p.primary1.max == 150
    and p.primary1.skillLine == 393, "primary profession")
check(p.primary2.name == "Leatherworking" and p.archaeology == nil, "second profession, no archaeology")
check(p.cooking.skill == 40 and p.firstAid.max == 75 and p.fishing.name == "Fishing", "secondary skills")
local g = c.gear
check(g.head.itemId == 1111 and g.head.slot == 1 and g.head.enchantId == 15 and g.head.itemLevel == 20
    and g.head.name == "Hat" and g.head.link:find("item:1111", 1, true), "head")
check(g.mainhand.enchantId == nil and g.mainhand.gems[1] == 3001 and g.mainhand.suffixId == -12
    and g.mainhand.itemLevel == 25, "mainhand gem and suffix")
check(g.chest.itemId == 5555 and g.chest.link == nil and g.incomplete == 1, "uncached item is counted")
check(g.legs == nil, "an empty slot is absent")
check(c.savedAt == 1793750400 and c.savedAtText == "2026-11-04T00:00:00Z" and c.addonVersion == "0.1.0-test", "stamp")
check(c.reason == "login" and c.errors == nil, "reason and no errors")
check(#PRINTS == 0, "silent: " .. tostring(PRINTS[1]))
""")

case("a_secret_answer_is_left_out_and_never_touched")(r"""
function UnitStat(_, i) if i == 1 then return SECRET, SECRET end return 10, 12 end
function GetMoney() return SECRET end
function GetCritChance() return SECRET end
C_ClassTalents.GetActiveConfigID = function() return SECRET end
function GetInventoryItemLink(_, slot) if slot == 1 then return SECRET end return GEAR[slot] and GEAR[slot][2] end
load()
login()
local c = saved()
check(c and c.errors == nil, "no reader threw: " .. tostring(c and c.errors and c.errors[1]))
check(c.stats.base.str == nil and c.stats.effective.str == nil and c.stats.effective.agi == 12, "secret stat absent")
check(c.money == nil and c.stats.crit.melee == nil, "secret money and crit absent")
check(c.talents.status == "unavailable" and #c.talents.list == 0, "secret config id: talents unavailable")
check(c.gear.head.itemId == 1111 and c.gear.head.link == nil, "secret link absent, id kept")
""")

case("nothing_is_written_in_combat_and_the_write_follows_combat_end")(r"""
load()
COMBAT = true
login()
check(saved() == nil, "no write in combat")
fire("PLAYER_REGEN_ENABLED")
COMBAT = false
check(runTimers() == 1, "combat end schedules the write")
check(saved() and saved().reason == "combat end", "written after combat")
COMBAT = false
""")

case("logout_in_combat_keeps_the_last_snapshot")(r"""
load()
login()
local first = saved()
COMBAT = true
LEVEL = 25
fire("PLAYER_LOGOUT")
check(saved() == first and first.level == 24, "kept")
COMBAT = false
fire("PLAYER_LOGOUT")
check(saved().level == 25 and saved().reason == "logout", "logout out of combat writes at once")
""")

case("a_logout_that_reads_every_stat_as_zero_keeps_the_last_stats")(r"""
-- live 2026-11-04: a snapshot written at logout had all five stats at 0 (the client tears the unit down first)
load()
login()
check(saved().stats.base.str == 40, "login stats")
local stamp = saved().savedAt
STATS = { { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 } }
LEVEL = 25
fire("PLAYER_LOGOUT")
local c = saved()
check(c.level == 25 and c.reason == "logout", "the rest of the logout snapshot is written")
check(c.stats.base.str == 40 and c.stats.effective.spi == 55 and c.stats.attackPower == 135, "the last stats are kept")
check(c.statsFrom == stamp, "the kept stats say when they were read")
-- a later write that reads real stats replaces them and drops the mark
STATS = { { 41, 53 }, { 30, 41 }, { 45, 60 }, { 35, 38 }, { 50, 55 } }
fire("PLAYER_LOGOUT")
check(saved().stats.base.str == 41 and saved().statsFrom == nil, "real stats replace the kept ones")
-- with nothing kept before, zero stats are written as read
ForeverSTUwaveExport = nil
STATS = { { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 }, { 0, 0 } }
fire("PLAYER_LOGOUT")
check(saved().stats.base.str == 0 and saved().statsFrom == nil, "no earlier stats: written as read")
STATS = { { 40, 52 }, { 30, 41 }, { 45, 60 }, { 35, 38 }, { 50, 55 } }
""")

case("a_logout_teardown_keeps_money_xp_gear_zone_talents_and_professions")(r"""
-- live 2026-11-10 (reason "logout"): money, xp and xpMax read 0, zone and gear empty, talents unavailable,
-- professions with no slot. Each such section keeps the last real value and is named in kept.
load()
login()
local stamp = saved().savedAt
local real = { UnitXPMax, GetMoney, UnitXP, GetRealZoneText, GetInventoryItemID, GetProfessions, C_ClassTalents.GetActiveConfigID }
UnitXPMax = function() return 0 end
GetMoney = function() return 0 end
UnitXP = function() return 0 end
GetRealZoneText = function() return nil end
GetInventoryItemID = function() return nil end
GetProfessions = function() end
C_ClassTalents.GetActiveConfigID = function() return nil end
fire("PLAYER_LOGOUT")
local c = saved()
check(c.reason == "logout", "the logout write still lands")
check(c.money == 123456 and c.xp == 1200 and c.xpMax == 9000, "money and xp kept")
check(c.gear.head and c.gear.head.itemId == 1111, "gear kept")
check(c.zone.name == "The Barrens", "zone kept")
check(c.talents.status == "ok" and #c.talents.list == 2, "talents kept")
check(c.professions.cooking and c.professions.cooking.skill == 40, "professions kept")
check(type(c.kept) == "table" and #c.kept == 6 and c.keptFrom == stamp, "kept names each section and when it was read")
UnitXPMax, GetMoney, UnitXP, GetRealZoneText, GetInventoryItemID, GetProfessions, C_ClassTalents.GetActiveConfigID =
    real[1], real[2], real[3], real[4], real[5], real[6], real[7]
fire("PLAYER_LOGOUT")
check(saved().kept == nil and saved().keptFrom == nil, "a real read drops the mark")
""")

case("action_bars_bindings_and_macros_are_exported")(r"""
local slots = { [1] = { "spell", 6343 }, [73] = { "spell", 78 }, [86] = { "macro", 2 }, [120] = { "item", 118 } }
GetActionInfo = function(slot) local s = slots[slot]; if s then return s[1], s[2], slot == 120 and "x" or nil end end
GetActionText = function() return nil end
GetBonusBarOffset = function() return 2 end
C_Spell = C_Spell or {}
C_Spell.GetSpellName = function(id) return ({ [6343] = "Thunder Clap", [78] = "Heroic Strike" })[id] end
C_Item = C_Item or {}
C_Item.GetItemNameByID = function(id) return id == 118 and "Minor Healing Potion" or nil end
GetCurrentBindingSet = function() return 2 end
GetBindingKey = function(cmd)
    if cmd == "ACTIONBUTTON1" then return "F", "SHIFT-1" end
    if cmd == "MULTIACTIONBAR1BUTTON3" then return "CTRL-E" end
end
GetNumBindings = function() return 3 end
GetBinding = function(i)
    if i == 1 then return "ACTIONBUTTON1", "ACTIONBAR", "F" end
    if i == 2 then return "TARGETLASTTARGET", "TARGETING", "CTRL-SHIFT-H" end
    return "TOGGLEMUSIC", "MISC"
end
GetNumMacros = function() return 1, 1 end
GetMacroInfo = function(i)
    if i == 1 then return "Pull", 132355, "/cast Thunder Clap" end
    if i == 2 then return "Charge", "INV_MISC_QUESTIONMARK", "/cast Charge" end
    if i == 121 then return "Mine", 136243, "/say hi" end
end
load()
login()
local c = saved()
local a = c.actionBars
check(a.status == "ok" and a.bonusBarOffset == 2 and #a.list == 4, "four filled slots and the stance page")
check(a.list[1].slot == 1 and a.list[1].type == "spell" and a.list[1].id == 6343 and a.list[1].name == "Thunder Clap", "spell slot")
check(a.list[2].slot == 73 and a.list[2].name == "Heroic Strike", "battle stance page slot")
check(a.list[3].slot == 86 and a.list[3].type == "macro" and a.list[3].name == "Charge", "macro slot named by its macro")
check(a.list[4].slot == 120 and a.list[4].name == "Minor Healing Potion" and a.list[4].subType == "x", "item slot")
local b = c.bindings
check(b.status == "ok" and b.set == 2 and b.setName == "character", "binding set")
check(#b.actionBar == 2 and b.actionBar[1].command == "ACTIONBUTTON1" and b.actionBar[1].keys[1] == "F"
    and b.actionBar[1].keys[2] == "SHIFT-1" and b.actionBar[2].command == "MULTIACTIONBAR1BUTTON3", "bar binds")
check(#b.other == 1 and b.other[1].command == "TARGETLASTTARGET" and b.other[1].keys[1] == "CTRL-SHIFT-H"
    and b.other[1].category == "TARGETING", "other binds: bar commands and unbound left out")
local m = c.macros
check(m.status == "ok" and #m.list == 2, "a general and a character macro")
check(m.list[1].index == 1 and m.list[1].scope == "general" and m.list[1].body == "/cast Thunder Clap" and m.list[1].icon == 132355, "general macro")
check(m.list[2].index == 121 and m.list[2].scope == "character" and m.list[2].name == "Mine", "character macro")
check(c.errors == nil, "no reader threw")
""")

case("professions_fall_back_to_the_skill_lines_when_the_slots_are_empty")(r"""
local realP = GetProfessions
GetProfessions = function() end
LINES = {
    { "Professions", true }, { "Skinning", false, false, 110, 0, 0, 150 }, { "Herbalism", false, false, 30, 0, 0, 75 },
    { "Secondary Skills", true }, { "Cooking", false, false, 39, 0, 0, 75 }, { "Fishing", false, false, 12, 0, 0, 75 },
    { "Weapon Skills", true }, { "Maces", false, false, 95, 0, 0, 100 },
}
GetNumSkillLines = function() return #LINES end
GetSkillLineInfo = function(i) return unpack(LINES[i]) end
load()
login()
local p = saved().professions
check(p.status == "ok", "status")
check(p.primary1.name == "Skinning" and p.primary1.skill == 110 and p.primary1.max == 150, "first primary")
check(p.primary2.name == "Herbalism", "second primary")
check(p.cooking.skill == 39 and p.cooking.max == 75 and p.fishing.skill == 12, "secondaries by name")
check(p.firstAid == nil, "an unlearned slot stays absent")
GetProfessions, GetNumSkillLines, GetSkillLineInfo = realP, nil, nil
""")

case("first_aid_in_the_archaeology_slot_keys_by_skill_line")(r"""
load()
local realP = GetProfessions
-- Forever (live 2026-11-10) returns First Aid in the third slot, where retail puts archaeology.
GetProfessions = function() return 1, 2, 6, 4, 5, nil end
login()
local p = saved().professions
check(p.firstAid and p.firstAid.name == "First Aid" and p.firstAid.skill == 60, "first aid keyed by skill line")
check(p.archaeology == nil, "no archaeology entry")
check(p.primary1.name == "Skinning" and p.cooking.skill == 40, "the rest unchanged")
GetProfessions = realP
""")

case("bags_list_every_item_and_logout_keeps_them")(r"""
load()
login()
local b = saved().bags
check(b.slots == 10 and b.free == 8 and #b.items == 2, "slot counts")
local fish = b.items[1]
check(fish.bag == 0 and fish.slot == 1 and fish.itemId == 6303 and fish.count == 7 and fish.quality == 1
    and fish.name == "Raw Slitherskin Mackerel" and fish.itemLevel == 5 and fish.link:find("Hitem:6303"), "item fields")
check(saved().bank == nil, "no bank before it is opened")
local realN = C_Container.GetContainerNumSlots
C_Container.GetContainerNumSlots = function() return 0 end
fire("PLAYER_LOGOUT")
check(saved().bags.slots == 10 and #saved().bags.items == 2, "logout teardown keeps the bags")
local kept = false
for _, k in ipairs(saved().kept or {}) do if k == "bags" then kept = true end end
check(kept, "bags named in kept")
C_Container.GetContainerNumSlots = realN
""")

case("quests_list_objectives_and_completed_ids_and_logout_keeps_them")(r"""
load()
login()
local q = saved().quests
check(q.status == "ok" and #q.list == 2, "two quests, header skipped")
local hunt, rite = q.list[1], q.list[2]
check(hunt.questId == 747 and hunt.title == "The Hunt Continues" and hunt.level == 3 and hunt.header == "Mulgore"
    and hunt.isComplete == nil, "quest fields")
check(hunt.objectives[1].numFulfilled == 3 and hunt.objectives[1].numRequired == 7
    and hunt.objectives[1].text == "Plainstrider Meat: 3/7", "objective progress")
check(rite.isComplete == true and rite.objectives[1].finished == true, "a complete quest")
local done = saved().completedQuests
check(#done == 3 and done[1] == 744 and done[3] == 3376, "completed ids, sorted")
local realLog, realDone = C_QuestLog.GetNumQuestLogEntries, C_QuestLog.GetAllCompletedQuestIDs
C_QuestLog.GetNumQuestLogEntries = function() return 0 end
C_QuestLog.GetAllCompletedQuestIDs = function() return {} end
fire("QUEST_LOG_UPDATE")
runTimers()
check(#saved().quests.list == 0, "an emptied log outside logout is written as read")
fire("PLAYER_LOGOUT")
check(#saved().quests.list == 0, "nothing real to keep from an empty write")
C_QuestLog.GetNumQuestLogEntries, C_QuestLog.GetAllCompletedQuestIDs = realLog, realDone
fire("QUEST_LOG_UPDATE")
runTimers()
C_QuestLog.GetNumQuestLogEntries = function() return 0 end
C_QuestLog.GetAllCompletedQuestIDs = function() return {} end
fire("PLAYER_LOGOUT")
check(#saved().quests.list == 2 and #saved().completedQuests == 3, "logout teardown keeps quests and completed ids")
C_QuestLog.GetNumQuestLogEntries, C_QuestLog.GetAllCompletedQuestIDs = realLog, realDone
""")

case("quests_fall_back_to_the_old_quest_log_calls")(r"""
local realQ = C_QuestLog
C_QuestLog = nil
GetNumQuestLogEntries = function() return 2 end
GetQuestLogTitle = function(i)
    if i == 1 then return "Mulgore", 0, 0, true end
    return "Swoop Hunting", 7, 0, false, false, 1, 0, 761
end
GetNumQuestLeaderBoards = function() return 1 end
GetQuestLogLeaderBoard = function() return "Trophy Swoop Quill: 8/8", "item", true end
GetQuestsCompleted = function() return { [747] = true, [750] = true } end
load()
login()
local q = saved().quests.list[1]
check(q.questId == 761 and q.title == "Swoop Hunting" and q.level == 7 and q.header == "Mulgore" and q.isComplete == true,
    "row from GetQuestLogTitle")
check(q.objectives[1].numFulfilled == 8 and q.objectives[1].numRequired == 8 and q.objectives[1].finished, "leaderboard")
check(#saved().completedQuests == 2 and saved().completedQuests[1] == 747, "GetQuestsCompleted map")
C_QuestLog = realQ
GetNumQuestLogEntries, GetQuestLogTitle, GetNumQuestLeaderBoards, GetQuestLogLeaderBoard, GetQuestsCompleted =
    nil, nil, nil, nil, nil
""")

case("currencies_and_reputations_and_logout_keeps_them")(r"""
load()
login()
local c = saved().currencies
check(c.status == "ok" and #c.list == 2, "two currencies, header skipped")
check(c.list[1].name == "Merchant's Favor" and c.list[1].id == 3456 and c.list[1].quantity == 37
    and c.list[1].header == "Forever", "currency id from the link")
check(c.list[2].id == 1901 and c.list[2].quantity == 120, "currency id from the table")
local r = saved().reputations
check(r.status == "ok" and #r.list == 2, "two factions, header skipped")
local tb, dsl = r.list[1], r.list[2]
check(tb.name == "Thunder Bluff" and tb.id == 81 and tb.standing == "Honored" and tb.value == 3000 and tb.max == 12000
    and tb.total == 12000 and tb.header == "Horde", "faction fields")
check(dsl.name == "Durotar Supply and Logistics" and dsl.standing == "Friendly" and dsl.value == 250
    and dsl.max == 6000, "DSL standing")
local realC, realR = C_CurrencyInfo.GetCurrencyListSize, C_Reputation.GetNumFactions
C_CurrencyInfo.GetCurrencyListSize = function() return 0 end
C_Reputation.GetNumFactions = function() return 0 end
fire("PLAYER_LOGOUT")
check(#saved().currencies.list == 2 and #saved().reputations.list == 2, "logout teardown keeps both")
C_CurrencyInfo.GetCurrencyListSize, C_Reputation.GetNumFactions = realC, realR
""")

case("reputations_fall_back_to_GetFactionInfo")(r"""
local realR = C_Reputation
C_Reputation = nil
GetNumFactions = function() return 2 end
GetFactionInfo = function(i)
    if i == 1 then return "Horde", "", 0, 0, 0, 0, false, false, true, false, false, false, false, 67 end
    return "Orgrimmar", "", 6, 9000, 21000, 10500, false, false, false, false, true, false, true, 76
end
load()
login()
local o = saved().reputations.list[1]
check(#saved().reputations.list == 1 and o.name == "Orgrimmar" and o.id == 76 and o.standing == "Honored"
    and o.value == 1500 and o.max == 12000 and o.header == "Horde", "row from GetFactionInfo")
C_Reputation, GetNumFactions, GetFactionInfo = realR, nil, nil
""")

case("gear_and_bag_items_carry_their_stats_from_the_link")(r"""
load()
login()
local head = saved().gear.head
check(head.stats and head.stats.ITEM_MOD_STAMINA_SHORT == 2 and head.stats.ITEM_MOD_INTELLECT_SHORT == 2
    and head.stats.armor == 45 and head.stats.RESISTANCE0_NAME == 45, "gear stats with armor")
check(saved().gear.mainhand.stats == nil, "no stats, no field")
local items = saved().bags.items
check(items[2].itemId == 2222 and items[2].stats.ITEM_MOD_AGILITY_SHORT == 3 and items[2].stats.armor == nil, "bag item stats")
check(items[1].stats == nil, "a fish has no stats")
""")

case("the_bank_reads_while_open_and_carries_after")(r"""
load()
login()
local stamp = saved().savedAt
fire("BANKFRAME_OPENED")
fire("BANKFRAME_CLOSED")
local bank = saved().bank
check(bank and bank.slots == 28 and #bank.items == 1 and bank.items[1].itemId == 4444 and bank.items[1].count == 3,
    "a short bank visit is read before it closes")
check(saved().reason == "bank" and saved().bankFrom == nil, "read live, no carry stamp")
local readAt = saved().savedAt
fire("BAG_UPDATE_DELAYED")
runTimers()
check(saved().bank and saved().bank.items[1].itemId == 4444 and saved().bankFrom == readAt, "closed bank carried with its stamp")
""")

case("a_burst_of_events_is_one_write")(r"""
load()
login()
fire("PLAYER_EQUIPMENT_CHANGED", 1, false)
fire("PLAYER_EQUIPMENT_CHANGED", 5, false)
fire("TRAIT_CONFIG_UPDATED", 77)
fire("PLAYER_LEVEL_UP", 25)
check(#TIMERS == 1, "one pending timer, got " .. #TIMERS)
runTimers()
check(saved().reason == "gear", "first reason of the burst")
""")

case("the_switch_stops_writes")(r"""
load()
check(SETTINGS["export.enabled"] == true, "default on")
SETTINGS["export.enabled"] = false
login()
fire("PLAYER_LOGOUT")
check(ForeverSTUwaveExport == nil, "nothing written when off")
SETTINGS["export.enabled"] = true
""")

case("nothing_is_written_before_the_saved_table_loads")(r"""
ForeverSTUwaveExport = nil
local fn = assert(loadstring(SOURCE_TEXT, "@CharacterExport.lua"))
FRAMES = {}
fn("forever-stuwave", FS)
check(FS.CharacterExport.Write("early") == false and ForeverSTUwaveExport == nil, "refused before ADDON_LOADED")
""")

case("other_characters_are_kept")(r"""
load()
ForeverSTUwaveExport = { schema = 1, characters = { ["Mira Ashgrove"] = { level = 18 } } }
login()
check(ForeverSTUwaveExport.characters["Mira Ashgrove"].level == 18, "another character stays")
check(saved().level == 24, "this one added")
""")


case("a_level_up_shows_a_secure_reload_macro_button")(r"""
load()
SETTINGS["export.reloadButton"] = true
check(FS.CharacterExport.ReloadButton() == nil, "no button before a level up")
fire("PLAYER_LEVEL_UP", 25)
local b = FS.CharacterExport.ReloadButton()
check(b and b.shown, "button shown after the level up")
check(b.text == "Reload to save", "label: " .. tostring(b.text))
check(b.template == "SecureActionButtonTemplate", "not a secure button")
check(b.attrs.type1 == "macro" and b.attrs.macrotext1 == "/reload", "left click is not the /reload macro")
check(b.attrs.type == nil and b.attrs.type2 == nil, "a right click would run something")
if b.scripts.OnClick then b.scripts.OnClick(b, "LeftButton") end  -- addon code never calls the protected reload
""")

case("the_reload_button_waits_out_combat_and_right_click_dismisses")(r"""
load()
SETTINGS["export.reloadButton"] = true
COMBAT = true
fire("PLAYER_LEVEL_UP", 25)
check(FS.CharacterExport.ReloadButton() == nil, "not built in combat")
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
local b = FS.CharacterExport.ReloadButton()
check(b and b.shown, "shown once combat ends")
fire("PLAYER_REGEN_DISABLED")  -- fires before the lockdown starts
check(not b.shown, "hidden when combat starts")
COMBAT = true
fire("PLAYER_LEVEL_UP", 26)
check(not b.shown, "a secure button is not touched in lockdown")
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(b.shown, "back after combat")
b.scripts.OnClick(b, "RightButton")
check(not b.shown, "right click hides it")
fire("PLAYER_REGEN_ENABLED")
check(not b.shown, "a dismissed button stays hidden")
""")

case("the_reload_button_switch_keeps_it_hidden")(r"""
load()
check(SETTINGS["export.reloadButton"] == false, "default off")
fire("PLAYER_LEVEL_UP", 25)
check(FS.CharacterExport.ReloadButton() == nil, "no button when switched off")
""")


# Profession recipes ----------------------------------------------------------------------------

case("the_trade_skill_events_are_registered_and_the_read_is_side_effect_free")(r"""
load()
for _, event in ipairs({ "TRADE_SKILL_SHOW", "TRADE_SKILL_LIST_UPDATE", "TRADE_SKILL_DATA_SOURCE_CHANGED", "TRADE_SKILL_CLOSE" }) do
    local found = false
    for _, f in ipairs(FRAMES) do if f.events[event] then found = true end end
    check(found, event .. " is not registered")
end
login()
openWindow("leatherworking")
settle()
check(saved().professions.primary2.recipes, "a read happened")
check(WROTE == nil, "the read called a setter: " .. tostring(WROTE))
check(#PRINTS == 0, "silent: " .. tostring(PRINTS[1]))
""")

case("a_trade_window_open_records_the_known_recipes_with_difficulty_count_and_reagents")(r"""
load()
login()
check(saved().professions.primary2.recipes == nil and saved().recipeCapture == nil, "no recipes before a window opens")
openWindow("leatherworking")
check(#TIMERS == 1, "show, source change and list update are one read, got " .. #TIMERS)
check(saved().professions.primary2.recipes == nil, "the read waits for the window to settle")
settle()
local c = saved()
check(c.reason == "recipes" and c.errors == nil, "the read triggers a write: " .. tostring(c.reason))
local lw = c.professions.primary2
check(lw.name == "Leatherworking" and lw.skill == 95 and lw.max == 150 and lw.skillLine == 165, "the profession line is as before")
check(lw.capturedAt == 1793750400 and lw.capturedAtText == "2026-11-04T00:00:00Z" and lw.capturedSkill == 95, "stamp and skill")
check(lw.recipesIncomplete == 1, "one reagent has no cached name: " .. tostring(lw.recipesIncomplete))
local r = lw.recipes
check(#r == 5, "five learned recipes, the unlearned one left out, got " .. #r)
check(r[1].name == "Embossed Leather Gloves" and r[2].name == "Fine Leather Belt" and r[3].name == "Handstitched Leather Boots"
    and r[4].name == "Light Armor Kit" and r[5].name == "Mystery Recipe", "sorted by name")
local kit = r[4]
check(kit.recipeId == 2152 and kit.skillLineAbilityId == 9152 and kit.outputItemId == 2304, "ids")
check(kit.difficulty == "orange" and kit.difficultyId == 0 and kit.numCraftable == 14, "difficulty and number craftable")
check(#kit.reagents == 1 and kit.reagents[1].name == "Light Leather" and kit.reagents[1].itemId == 2318
    and kit.reagents[1].count == 1 and kit.reagents[1].owned == 14, "reagent: name, item id, needed, owned")
check(r[1].difficulty == "green" and r[2].difficulty == "yellow" and r[3].difficulty == "grey", "difficulty words")
check(r[3].numCraftable == 3 and r[2].numCraftable == 0, "craftable counts")
local boots = r[3]
check(#boots.reagents == 2 and boots.reagents[1].count == 2 and boots.reagents[2].name == "Coarse Thread"
    and boots.reagents[2].count == 1 and boots.reagents[2].owned == 3, "the finishing slot is not a needed reagent")
local belt = r[2]
check(belt.reagents[2].itemId == 4291 and belt.reagents[2].name == nil and belt.reagents[2].count == 2
    and belt.reagents[2].owned == 2, "an uncached item keeps its id and count, no name")
local gloves = r[1]
check(gloves.reagents[1].itemId == 5001 and gloves.reagents[1].count == 3 and gloves.reagents[1].owned == 7
    and #gloves.reagents[1].itemIds == 3 and gloves.reagents[1].itemIds[3] == 5003, "alternates: first id, all ids, owned summed")
check(kit.reagents[1].itemIds == nil, "a single item has no alternates list")
local odd = r[5]
check(odd.recipeId == 4001 and odd.difficulty == nil and odd.difficultyId == nil and odd.reagents == nil
    and odd.outputItemId == nil and odd.numCraftable == 0, "a recipe with no difficulty or schematic keeps what it has")
local rc = c.recipeCapture
check(rc.status == "ok" and rc.slot == "primary2" and rc.name == "Leatherworking" and rc.skillLine == 165 and rc.count == 5
    and rc.at == 1793750400 and rc.failed == 1, "capture note, one recipe without a schematic counted")
check(LOADREQ[1] == 4291 and #LOADREQ == 1, "only the uncached item is requested")
""")

case("cooking_and_first_aid_windows_land_in_their_own_slots")(r"""
load()
login()
openWindow("cooking")
settle()
openWindow("firstaid")
settle()
local p = saved().professions
check(p.cooking.recipes and #p.cooking.recipes == 2 and p.cooking.recipes[1].name == "Herb Baked Egg", "cooking")
check(p.cooking.recipes[2].name == "Roasted Boar Meat" and p.cooking.recipes[2].difficulty == "orange"
    and p.cooking.recipes[2].reagents[1].name == "Chunk of Boar Meat" and p.cooking.recipes[2].numCraftable == 5,
    "a window with no child line is read from the base line")
check(p.firstAid.recipes and #p.firstAid.recipes == 1 and p.firstAid.recipes[1].name == "Linen Bandage"
    and p.firstAid.capturedSkill == 60, "first aid")
check(p.cooking.capturedSkill == 40 and p.primary2.recipes == nil and p.fishing.recipes == nil, "others untouched")
check(saved().recipeCapture.slot == "firstAid", "the capture note is the latest read")
""")

case("recipes_survive_writes_with_no_window_a_logout_teardown_and_a_new_session")(r"""
load()
login()
openWindow("leatherworking")
settle()
local at = saved().professions.primary2.capturedAt
closeWindow()
NOW = NOW + 600
fire("BAG_UPDATE_DELAYED")
check(#TIMERS == 1, "a closed window schedules only the bag write")
settle()
local lw = saved().professions.primary2
check(saved().reason == "bags" and #lw.recipes == 5 and lw.capturedAt == at, "kept with its own stamp, got " .. tostring(lw.capturedAt))
check(saved().kept == nil, "not torn, so not named in kept")
-- a logout teardown reads no profession slot: the whole section comes from the last write, recipes with it
local realP = GetProfessions
GetProfessions = function() end
fire("PLAYER_LOGOUT")
check(saved().professions.primary2.recipes and #saved().professions.primary2.recipes == 5, "logout teardown keeps the recipes")
GetProfessions = realP
-- a new session starts with an empty session table and carries the stored list
reload()
PROFS[2][3] = 96
login()
local again = saved().professions.primary2
check(again.skill == 96 and #again.recipes == 5 and again.capturedAt == at and again.capturedSkill == 95,
    "a new session keeps the stored recipes and their capture skill")
check(again.recipes[4].reagents[1].name == "Light Leather", "the stored list is whole")
""")

case("a_recapture_replaces_the_list_and_an_empty_read_keeps_the_last")(r"""
load()
login()
openWindow("cooking")
settle()
local first = saved().professions.cooking
check(first.recipes[2].numCraftable == 5, "first read")
NOW = NOW + 60
CRAFTABLE[2538] = 2
fire("TRADE_SKILL_LIST_UPDATE")
settle()
local second = saved().professions.cooking
check(second.recipes[2].numCraftable == 2 and second.capturedAt == NOW, "a list update re-reads the counts")
-- the client answers with no learned recipe (not loaded yet): the last real list stays
NOW = NOW + 60
for _, id in ipairs({ 2538, 8604 }) do RECIPES[id].learned = false end
fire("TRADE_SKILL_LIST_UPDATE")
settle()
flush()
local third = saved().professions.cooking
check(#third.recipes == 2 and third.capturedAt == second.capturedAt, "an empty read does not replace the list")
check(saved().recipeCapture.status == "empty" and saved().recipeCapture.count == 0, "and says so: " .. tostring(saved().recipeCapture.status))
-- a newly learned recipe shows up on the next read
RECIPES[2538].learned = true
fire("TRADE_SKILL_LIST_UPDATE")
settle()
check(#saved().professions.cooking.recipes == 1 and saved().professions.cooking.recipes[1].name == "Roasted Boar Meat",
    "the new read is the list")
""")

case("a_bag_change_refreshes_the_counts_only_while_a_window_is_open")(r"""
load()
login()
openWindow("cooking")
settle()
CRAFTABLE[2538] = 4
fire("BAG_UPDATE_DELAYED")
check(#TIMERS == 2, "the bag write and a recipe read, got " .. #TIMERS)
settle()
check(saved().professions.cooking.recipes[2].numCraftable == 4, "the count follows the bags")
closeWindow()
fire("BAG_UPDATE_DELAYED")
check(#TIMERS == 1, "no read once the window is closed")
local calls = TSCALLS
settle()
check(TSCALLS == calls, "and none happened")
""")

case("a_linked_guild_or_npc_window_is_not_recorded")(r"""
load()
login()
for _, flag in ipairs({ "linked", "guild", "guildMember", "npc" }) do
    openWindow("leatherworking")
    TS[flag] = true
    settle()
    flush()
    check(saved().professions.primary2.recipes == nil, flag .. " window recorded")
    check(saved().recipeCapture and saved().recipeCapture.status == (flag == "guildMember" and "guild" or flag),
        flag .. " status: " .. tostring(saved().recipeCapture and saved().recipeCapture.status))
    closeWindow()
end
-- no way to tell a linked window from our own: not recorded either
C_TradeSkillUI.IsTradeSkillLinked = nil
openWindow("leatherworking")
settle()
flush()
check(saved().professions.primary2.recipes == nil and saved().recipeCapture.status == "unverified", "unverifiable")
closeWindow()
C_TradeSkillUI.IsTradeSkillLinked = function() return SECRET end
openWindow("leatherworking")
settle()
flush()
check(saved().professions.primary2.recipes == nil and saved().recipeCapture.status == "unverified", "a secret answer is unverifiable")
-- our own window again records
C_TradeSkillUI.IsTradeSkillLinked = function() return false end
openWindow("leatherworking")
settle()
check(saved().professions.primary2.recipes and #saved().professions.primary2.recipes == 5, "own window records")
""")

case("a_window_that_is_not_ours_or_not_ready_is_not_recorded")(r"""
load()
login()
openWindow("alchemy")
settle()
flush()
local p = saved().professions
check(p.primary1.recipes == nil and p.primary2.recipes == nil and p.cooking.recipes == nil, "no slot holds Alchemy")
check(saved().recipeCapture.status == "unmatched" and saved().recipeCapture.name == "Alchemy" and saved().recipeCapture.skillLine == 171,
    "unmatched, with what was open")
-- data source still changing: wait for the next event, record nothing
openWindow("cooking")
TS.changing = true
local calls = TSCALLS
settle()
check(TSCALLS == calls and saved().professions.cooking.recipes == nil, "not read while the data source changes")
TS.changing = false
fire("TRADE_SKILL_DATA_SOURCE_CHANGED")
settle()
check(saved().professions.cooking.recipes, "read once it settled")
-- not ready
closeWindow()
TS.base = WINDOWS.leatherworking.base
fire("TRADE_SKILL_LIST_UPDATE")
calls = TSCALLS
settle()
check(TSCALLS == calls and saved().professions.primary2.recipes == nil, "a closed window is not read")
""")

case("a_window_matches_its_slot_by_name_when_the_slot_has_no_skill_line")(r"""
GetProfessions = function() end
LINES = {
    { "Professions", true }, { "Leatherworking", false, false, 95, 0, 0, 150 },
    { "Secondary Skills", true }, { "Cooking", false, false, 40, 0, 0, 75 },
}
GetNumSkillLines = function() return #LINES end
GetSkillLineInfo = function(i) return unpack(LINES[i]) end
load()
login()
check(saved().professions.primary1.skillLine == nil, "the fallback path has no skill line")
openWindow("leatherworking")
settle()
check(saved().professions.primary1.recipes and #saved().professions.primary1.recipes == 5, "matched by profession name")
""")

case("a_dropped_profession_does_not_keep_the_old_recipes")(r"""
load()
login()
openWindow("leatherworking")
settle()
check(saved().professions.primary2.recipes, "captured")
PROFS[2] = { "Tailoring", 0, 10, 75, 0, 0, 197 }
fire("SKILL_LINES_CHANGED")
settle()
check(saved().professions.primary2.name == "Tailoring" and saved().professions.primary2.recipes == nil
    and saved().professions.primary2.capturedAt == nil, "the new profession in the slot starts empty")
reload()
login()
check(saved().professions.primary2.recipes == nil, "and a new session does not bring them back")
""")

case("a_trade_window_read_waits_out_combat")(r"""
load()
login()
COMBAT = true
openWindow("cooking")
settle()
check(TSCALLS == 0, "no recipe read in combat")
check(saved().professions.cooking.recipes == nil and saved().recipeCapture == nil, "nothing recorded in combat")
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
settle()
check(TSCALLS >= 1 and saved().professions.cooking.recipes and #saved().professions.cooking.recipes == 2, "read after combat")
-- a window closed during the fight is not read afterwards
COMBAT = true
openWindow("firstaid")
settle()
closeWindow()
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
local calls = TSCALLS
settle()
check(TSCALLS == calls and saved().professions.firstAid.recipes == nil, "closed in combat: not read")
""")

case("the_switch_stops_recipe_reads")(r"""
load()
login()
SETTINGS["export.enabled"] = false
openWindow("cooking")
settle()
check(TSCALLS == 0 and saved().professions.cooking.recipes == nil, "nothing read when off")
SETTINGS["export.enabled"] = true
""")

case("secret_recipe_data_is_left_out_and_never_touched")(r"""
RECIPES[2152] = { name = SECRET, recipeID = 2152, learned = true, relativeDifficulty = SECRET }
RECIPES[3753].learned = SECRET
CRAFTABLE[2149] = SECRET
SCHEMATICS[3756].reagentSlotSchematics[1].reagents[1].itemID = SECRET
C_Item.GetItemCount = function(id) if id == 2318 then return SECRET end return ITEMCOUNT[id] or 0 end
load()
login()
openWindow("leatherworking")
settle()
local c = saved()
check(c.errors == nil and c.recipeCapture.status == "ok", "nothing threw: " .. tostring(c.recipeCapture.status))
check(c.recipeCapture.failed == 1, "only the recipe with no schematic failed, so no secret was operated on: " .. tostring(c.recipeCapture.failed))
local r = c.professions.primary2.recipes
check(#r == 4, "the recipe with a secret learned flag is skipped, got " .. #r)
local kit, boots, gloves
for _, x in ipairs(r) do
    if x.recipeId == 2152 then kit = x elseif x.recipeId == 2149 then boots = x elseif x.recipeId == 3756 then gloves = x end
end
check(kit.name == nil and kit.difficulty == nil and kit.difficultyId == nil and kit.reagents[1].name == "Light Leather"
    and kit.reagents[1].owned == nil, "a secret name, difficulty and owned count are absent")
check(boots.numCraftable == nil, "a secret craftable count is absent")
check(gloves.reagents[1].itemId == 5002 and #gloves.reagents[1].itemIds == 2, "a secret item id is dropped from the alternates")
-- a secret answer to the readiness or the window guards
C_TradeSkillUI.IsTradeSkillGuild = function() return SECRET end
openWindow("cooking")
settle()
flush()
check(saved().professions.cooking.recipes == nil and saved().recipeCapture.status == "unverified",
    "a secret guild answer is not ours to record")
""")

case("a_client_without_the_recipe_api_records_nothing_and_throws_nothing")(r"""
local whole = C_TradeSkillUI
load()
login()
-- the namespace without the list calls
C_TradeSkillUI = { IsTradeSkillReady = function() return true end, IsTradeSkillLinked = function() return false end }
fire("TRADE_SKILL_SHOW")
settle()
flush()
check(saved().professions.cooking.recipes == nil and saved().recipeCapture.status == "unavailable", "unavailable, not an error")
check(saved().errors == nil, "no reader threw")
-- no namespace at all
C_TradeSkillUI = nil
fire("TRADE_SKILL_LIST_UPDATE")
settle()
flush()
check(saved().errors == nil, "no namespace: no throw")
-- a schematic call that throws costs that recipe's reagents, not the list
C_TradeSkillUI = whole
openWindow("cooking")
local realSchematic = C_TradeSkillUI.GetRecipeSchematic
C_TradeSkillUI.GetRecipeSchematic = function(id) if id == 2538 then error("boom") end return SCHEMATICS[id] end
settle()
flush()
local cooking = saved().professions.cooking
check(cooking.recipes and #cooking.recipes == 2 and cooking.recipes[2].name == "Roasted Boar Meat"
    and cooking.recipes[2].reagents == nil and cooking.recipes[1].reagents[1].name == "Small Egg", "the recipe stays, without reagents")
check(saved().recipeCapture.failed == 1, "and is counted")
-- a recipe whose own fields throw while it is read is skipped, not the whole list
C_TradeSkillUI.GetRecipeSchematic = realSchematic
SCHEMATICS[2538].reagentSlotSchematics = { setmetatable({}, { __index = function() error("boom") end }) }
fire("TRADE_SKILL_LIST_UPDATE")
settle()
flush()
cooking = saved().professions.cooking
check(#cooking.recipes == 1 and cooking.recipes[1].name == "Herb Baked Egg" and saved().recipeCapture.failed == 1,
    "the throwing recipe is skipped and counted")
""")

case("a_read_that_throws_is_noted_and_the_next_one_works")(r"""
local good = WINDOWS.cooking.base
WINDOWS.cooking.base = setmetatable({}, { __index = function() error("boom") end })
load()
login()
openWindow("cooking")
settle()
flush()
local rc = saved().recipeCapture
check(rc.status == "error" and rc.detail:find("boom", 1, true), "the throw is noted: " .. tostring(rc.status))
check(saved().errors == nil and saved().professions.cooking.recipes == nil, "and costs nothing else")
WINDOWS.cooking.base = good
openWindow("cooking")
settle()
check(saved().professions.cooking.recipes and #saved().professions.cooking.recipes == 2, "the next read works")
""")

case("the_difficulty_words_need_no_enum_table")(r"""
Enum = nil
load()
login()
openWindow("leatherworking")
settle()
local r = saved().professions.primary2.recipes
check(r[4].difficulty == "orange" and r[2].difficulty == "yellow" and r[1].difficulty == "green" and r[3].difficulty == "grey",
    "the documented values 0 to 3")
check(#r[3].reagents == 2, "the documented Basic value still leaves the finishing slot out")
""")

case("uncached_reagent_names_are_retried_a_bounded_number_of_times")(r"""
load()
login()
openWindow("leatherworking")
runTimers()
check(#TIMERS == 2, "the write and one retry, got " .. #TIMERS)
ITEMNAMES[4291] = "Silken Thread"
settle()
local belt = saved().professions.primary2.recipes[2]
check(belt.reagents[2].name == "Silken Thread" and saved().professions.primary2.recipesIncomplete == nil, "the retry filled the name in")
-- a name that never arrives: one read plus two retries, then it stops
local before = TSCALLS
ITEMNAMES[4291] = nil
fire("TRADE_SKILL_DATA_SOURCE_CHANGED")
settle()
check(TSCALLS - before == 3, "read and two retries, got " .. (TSCALLS - before))
check(saved().professions.primary2.recipesIncomplete == 1, "still flagged")
""")


def run(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().SOURCE_TEXT = SOURCE.read_text(encoding="utf-8")
    try:
        lua.execute(MOCK)
        lua.execute(body)
    except LuaError as error:
        return str(error)
    return None


def main() -> int:
    failed = 0
    for name, body in CASES:
        error = run(name, body)
        if error:
            failed += 1
            print(f"FAIL  {name}: {error}")
        else:
            print(f"ok    {name}")
    print(f"{len(CASES) - failed}/{len(CASES)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

