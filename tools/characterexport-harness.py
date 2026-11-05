#!/usr/bin/env python3
"""Runs the real Modules/Diagnostics/CharacterExport.lua headless against a mocked client.

The checks pin: a write lands in ForeverSTUwaveExport.characters keyed by the full GetUnitName("player", true) name
with every documented field filled (identity, XP, zone, money, base and effective stats, attack and spell power, crit,
hit, armor, health and mana, talents by name and id, professions with Cooking / First Aid / Fishing, gear per slot with
item id, link, enchant, gems and item level, savedAt and the addon version); a secret answer is left out and never
touched; nothing is written in combat and the deferred write happens after PLAYER_REGEN_ENABLED; a logout in combat keeps
the last snapshot; the config switch stops writes; events in one burst coalesce into one write; nothing prints.

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
FRAMES = {}
function CreateFrame()
    local f = setmetatable({ events = {}, scripts = {} }, FrameMT)
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
function GetServerTime() return 1793750400 end
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
    end,
}

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
