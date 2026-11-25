#!/usr/bin/env python3
"""The player role (ticket C3): Core/Role.lua, its per character store and the Roles page of /fsconfig.

Runs the real Core/Role.lua headless on a small mock client and pins:

  * Auto resolves in order: the assigned group role (UnitGroupRolesAssigned) when it is set and not NONE, else the
    talent tree with the most points (FS.CharBackdrop.TreePoints, ties to the leftmost tree) through the per class tree
    table, else Melee or Ranged by class; a secret group role is never read; with no FS.CharBackdrop (skins off) or no
    readable points Auto falls back to the class default and says so;
  * the tree table matches the talent art sheets of the client (FS.TalentBgArt.sheets): the same trees, left to right;
  * a hand pick overrides Auto and is stored per character: ForeverSTUwaveCharDB.role and an account wide copy by GUID
    (this client does not restore per character saved variables); a bad stored value reads as Auto; a read only profile
    keeps the pick in memory and writes only the character table;
  * a manual pick, a talent change and a group role change each fire OnChange at once (and only when the role or its
    source moved), a failing listener is isolated;
  * the role settings register their defaults, read back clean values (a bad stored value reads as the default), and
    act only when their role is the one in use (Role.Active / Role.Value / Role.Disabled);
  * the events are registered through the client's safe path and an unknown event name does not stop the rest;
  * the Roles page: every row, section, label, key, default, range, option and tip of the prototype's four tabs, the
    pinned "Your role" bar on every tab, the YOUR ROLE / "<ROLE> ONLY" section tags, the arrow on your role's tab,
    rows of other roles kept but marked, a role change repaints the page, no dashes, neutral wording.

The mock is NOT the real client.

    python3 tools/role-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
ROLE = ADDON / "Core/Role.lua"
THREAT = ADDON / "Modules/Nameplates/PlateThreat.lua"
PAGE = ADDON / "Modules/Config/ConfigPageRoles.lua"
PARTY = ADDON / "Modules/UnitFrames/PartyFrames.lua"
TALENT_ART = ADDON / "Modules/Skins/TalentBgArt.lua"
TOC = ADDON / "forever-stuwave.toc"
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))
PROTO = MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- the mock client for the core ---------------------------------------------------------------------------------

CORE_PRE = r"""
local realType = type
SECRET = setmetatable({}, { __metatable = false,
    __index = function() error("indexed a secret", 2) end, __newindex = function() error("wrote to a secret", 2) end,
    __lt = function() error("compared a secret", 2) end, __le = function() error("compared a secret", 2) end,
    __add = function() error("did math on a secret", 2) end, __sub = function() error("did math on a secret", 2) end,
    __mul = function() error("did math on a secret", 2) end, __div = function() error("did math on a secret", 2) end,
    __concat = function() error("joined a secret", 2) end, __call = function() error("called a secret", 2) end,
    __len = function() error("measured a secret", 2) end,
})
-- a secret answers type() as what it holds; a check says which with __secretKind
__secretKind = "string"
function type(v) if rawequal(v, SECRET) then return __secretKind end return realType(v) end
function check(c, msg) if not c then error(msg or "check failed", 2) end end

__frames = {}
local KNOWN = {}
for e in ([[PLAYER_LOGIN PLAYER_ENTERING_WORLD GROUP_ROSTER_UPDATE PLAYER_ROLES_ASSIGNED PLAYER_TALENT_UPDATE
    CHARACTER_POINTS_CHANGED TRAIT_CONFIG_UPDATED ACTIVE_TALENT_GROUP_CHANGED]]):gmatch("%S+") do KNOWN[e] = true end
function CreateFrame(kind)
    local f = { kind = kind, events = {}, scripts = {} }
    function f:RegisterEvent(e)
        if not KNOWN[e] then error("Frame:RegisterEvent(): Attempt to register unknown event \"" .. tostring(e) .. "\"", 2) end
        self.events[e] = true
    end
    function f:UnregisterEvent(e) self.events[e] = nil end
    function f:SetScript(k, fn) self.scripts[k] = fn end
    function f:GetScript(k) return self.scripts[k] end
    __frames[#__frames + 1] = f
    return f
end
function fire(event, ...)
    for _, f in ipairs(__frames) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end
    end
end

__class, __guid, __groupRole, __points, __inGroup = "SHAMAN", "Player-1-AAAA", "NONE", { 0, 0, 0 }, false
function UnitClass() return "Shaman", __class end
function UnitGUID() return __guid end
function IsInGroup() return __inGroup end
function UnitGroupRolesAssigned(unit) check(unit == "player", "asked for " .. tostring(unit)); return __groupRole end

-- a config like Core/Config.lua: a value equal to the default is stored as nothing, callbacks fire on a change
function mkConfig(initial)
    local store, defaults, cbs = initial or {}, {}, {}
    local C = { store = store, defaults = defaults, readOnly = false }
    function C.RegisterDefault(k, v) defaults[k] = v end
    function C.Get(k) local v = store[k]; if v == nil then return defaults[k] end return v end
    function C.IsStored(k) return store[k] ~= nil end
    function C.IsReadOnly() return C.readOnly end
    function C.OnChange(k, f) cbs[k] = cbs[k] or {}; table.insert(cbs[k], f) end
    function C.Set(k, v)
        if C.readOnly then return false end
        local old = C.Get(k)
        if v == defaults[k] then v = nil end
        store[k] = v
        local new = C.Get(k)
        if old ~= new then for _, f in ipairs(cbs[k] or {}) do f(new, old, k) end end
        return true
    end
    return C
end

-- The real talent art table: the tree names of the client, left to right.
function loadTalentArt()
    local chunk = assert(load(__TALENT_ART, "@TalentBgArt.lua"))
    chunk("forever-stuwave", FS)
end

-- Loads Core/Role.lua the way the .toc does (after Config.lua), then logs in.
function enter(o)
    o = o or {}
    for k in pairs(_G) do if k:match("^ForeverSTUwave") then _G[k] = nil end end
    __frames = {}
    FS = { IsSecret = function(v) return rawequal(v, SECRET) end }
    FS.Config = mkConfig(o.config)
    FS.FrameHelpers = { RegisterEvents = function(frame, list) for _, e in ipairs(list) do pcall(frame.RegisterEvent, frame, e) end end }
    if o.noHelpers then FS.FrameHelpers = nil end
    if o.charbackdrop ~= false then FS.CharBackdrop = { TreePoints = function() return __points end } end
    if o.char ~= nil then ForeverSTUwaveCharDB = o.char end
    if o.db ~= nil then ForeverSTUwaveDB = o.db end
    loadTalentArt()
    assert(load(__ROLE_SRC, "@Role.lua"))("forever-stuwave", FS)
    if o.login ~= false then fire("PLAYER_LOGIN") end
    return FS.Role
end
"""

CORE_CASES: list[tuple[str, str]] = [
    ("the module loads and exports the role names, picks and texts", r"""
local R = enter({ login = false })
check(table.concat(R.NAMES, ",") == "tank,healer,melee,ranged", "role names")
check(table.concat(R.PICKS, ",") == "auto,tank,healer,melee,ranged", "pick names")
for _, n in ipairs(R.NAMES) do check(type(R.TEXT[n]) == "string", "no text for " .. n) end
check(type(R.Current) == "function" and type(R.Pick) == "function" and type(R.SetPick) == "function"
    and type(R.OnChange) == "function" and type(R.Summary) == "function" and type(R.Why) == "function", "api")
"""),

    ("the tree table is the client's talent art trees, left to right, for all nine classes", r"""
local R = enter({ login = false })
local classes = 0
for token, sheets in pairs(FS.TalentBgArt.sheets) do
    classes = classes + 1
    local trees = R.TREES[token]
    check(trees and #trees == 3, "no three trees for " .. token)
    for i = 1, 3 do
        local want = sheets[i]:match("^talentbg_" .. token:lower() .. "_(%a+)$")
        check(trees[i].name == want, token .. " tree " .. i .. " is " .. tostring(trees[i].name) .. ", the client's art says " .. tostring(want))
        local okRole = trees[i].role == "tank" or trees[i].role == "healer" or trees[i].role == "melee" or trees[i].role == "ranged"
        check(okRole, token .. " tree " .. i .. " has the role " .. tostring(trees[i].role))
    end
    local def = R.CLASS_ROLE[token]
    check(def == "melee" or def == "ranged", token .. " class default is " .. tostring(def))
end
check(classes == 9, "nine classes in the art, saw " .. classes)
"""),

    ("tree roles: the tanks, healers and damage trees", r"""
local R = enter({ login = false })
local function role(token, i) return R.TREES[token][i].role end
check(role("WARRIOR", 3) == "tank" and role("WARRIOR", 1) == "melee" and role("WARRIOR", 2) == "melee", "warrior")
check(role("PALADIN", 1) == "healer" and role("PALADIN", 2) == "tank" and role("PALADIN", 3) == "melee", "paladin")
check(role("PRIEST", 1) == "healer" and role("PRIEST", 2) == "healer" and role("PRIEST", 3) == "ranged", "priest")
check(role("SHAMAN", 1) == "ranged" and role("SHAMAN", 2) == "melee" and role("SHAMAN", 3) == "healer", "shaman")
check(role("DRUID", 1) == "ranged" and role("DRUID", 2) == "melee" and role("DRUID", 3) == "healer", "druid")
check(role("ROGUE", 1) == "melee" and role("ROGUE", 3) == "melee", "rogue")
for i = 1, 3 do check(role("MAGE", i) == "ranged" and role("WARLOCK", i) == "ranged" and role("HUNTER", i) == "ranged", "casters") end
"""),

    ("Auto: most points in Enhancement makes a Shaman Melee, from talents", r"""
__class, __points = "SHAMAN", { 3, 31, 0 }
local R = enter()
local role, source = R.Current()
check(role == "melee" and source == "talents", "got " .. tostring(role) .. " " .. tostring(source))
check(R.Pick() == "auto", "pick")
check(R.Summary() == "MELEE, FROM TALENTS", "summary was " .. tostring(R.Summary()))
check(R.Why():find("Enhancement"), "the why names the tree: " .. R.Why())
"""),

    ("Auto: Restoration points make a Shaman a Healer, Elemental a Ranged", r"""
__class, __points = "SHAMAN", { 0, 5, 31 }
local R = enter()
check(R.Current() == "healer", "resto")
__points = { 31, 0, 0 }
fire("PLAYER_TALENT_UPDATE")
check(R.Current() == "ranged", "elemental")
"""),

    ("Auto: ties go to the leftmost tree, no points fall to the class default", r"""
__class, __points = "PALADIN", { 10, 10, 10 }
local R = enter()
check(R.Current() == "healer", "a three way tie is the left tree (holy)")
__points = { 0, 0, 0 }
fire("CHARACTER_POINTS_CHANGED")
local role, source = R.Current()
check(role == "melee" and source == "class", "no points: " .. tostring(role) .. " " .. tostring(source))
check(R.Summary() == "MELEE, FROM CLASS", "summary " .. R.Summary())
check(R.Why():find("class"), "the why says the class decided: " .. R.Why())
"""),

    ("Auto: unreadable points (nil, a throw, a malformed answer) fall to the class default", r"""
for _, bad in ipairs({ "nil", "throw", "short", "words", "negative" }) do
    __class = "MAGE"
    local R = enter({ login = false })
    FS.CharBackdrop.TreePoints = function()
        if bad == "nil" then return nil elseif bad == "throw" then error("trait system down")
        elseif bad == "short" then return { 5 } elseif bad == "words" then return { "a", "b", "c" } else return { -3, -1, -2 } end
    end
    fire("PLAYER_LOGIN")
    local role, source = R.Current()
    check(role == "ranged" and source == "class", bad .. ": " .. tostring(role) .. " " .. tostring(source))
end
"""),

    ("Auto: with FS.CharBackdrop missing (skins off) the class default decides", r"""
__class = "ROGUE"
local R = enter({ charbackdrop = false })
local role, source = R.Current()
check(role == "melee" and source == "class", tostring(role) .. " " .. tostring(source))
__class = "HUNTER"
local R2 = enter({ charbackdrop = false })
check(R2.Current() == "ranged", "hunter")
"""),

    ("Auto: every class default", r"""
local want = { WARRIOR = "melee", PALADIN = "melee", HUNTER = "ranged", ROGUE = "melee", PRIEST = "ranged",
    SHAMAN = "melee", MAGE = "ranged", WARLOCK = "ranged", DRUID = "ranged" }
for token, role in pairs(want) do
    __class = token
    local R = enter({ charbackdrop = false })
    check(R.Current() == role, token .. " defaulted to " .. tostring(R.Current()))
end
__class = "DEATHKNIGHT"
local R = enter({ charbackdrop = false })
check(R.Current() == "melee", "an unknown class still answers a role: " .. tostring(R.Current()))
"""),

    ("Auto: an assigned group role wins over talents", r"""
__class, __points, __groupRole, __inGroup = "SHAMAN", { 0, 31, 0 }, "HEALER", true
local R = enter()
local role, source = R.Current()
check(role == "healer" and source == "group", tostring(role) .. " " .. tostring(source))
check(R.Summary() == "HEALER, FROM GROUP", R.Summary())
__groupRole = "TANK"; fire("PLAYER_ROLES_ASSIGNED")
check(R.Current() == "tank", "tank")
__groupRole = "NONE"; fire("GROUP_ROSTER_UPDATE")
local r2, s2 = R.Current()
check(r2 == "melee" and s2 == "talents", "back to talents: " .. tostring(r2) .. " " .. tostring(s2))
"""),

    ("Auto: a damage assignment picks melee or ranged from the tree, then the class", r"""
__class, __points, __groupRole = "SHAMAN", { 0, 31, 0 }, "DAMAGER"
local R = enter()
local role, source = R.Current()
check(role == "melee" and source == "group", "enhancement damage: " .. tostring(role) .. " " .. tostring(source))
__points = { 31, 0, 0 }; fire("PLAYER_TALENT_UPDATE")
check(R.Current() == "ranged", "elemental damage")
__points = { 0, 0, 31 }; fire("PLAYER_TALENT_UPDATE")
check(R.Current() == "melee", "a restoration shaman assigned damage falls to the class default (melee)")
__class, __points = "WARRIOR", { 0, 0, 31 }
local R2 = enter()
check(R2.Current() == "melee", "a protection warrior assigned damage is melee")
"""),

    ("Auto: a secret or odd group role is never read", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
__groupRole = SECRET
local R = enter()
local role, source = R.Current()
check(role == "melee" and source == "talents", "secret group role: " .. tostring(role) .. " " .. tostring(source))
for _, odd in ipairs({ 5, true, "LEADER", "", "tank" }) do
    __groupRole = odd
    fire("PLAYER_ROLES_ASSIGNED")
    check(select(2, R.Current()) == "talents", "an odd group role " .. tostring(odd) .. " was believed")
end
UnitGroupRolesAssigned = nil
fire("PLAYER_ROLES_ASSIGNED")
check(select(2, R.Current()) == "talents", "no API")
UnitGroupRolesAssigned = function() error("boom") end
fire("PLAYER_ROLES_ASSIGNED")
check(select(2, R.Current()) == "talents", "a throwing API")
"""),

    ("a secret class token never breaks the class default", r"""
__class = SECRET
local R = enter({ charbackdrop = false })
check(R.Current() == "melee", "got " .. tostring(R.Current()))
"""),

    ("a hand pick overrides Auto, says so, and Auto comes back", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
local R = enter()
check(R.SetPick("healer") == true, "SetPick refused")
local role, source = R.Current()
check(role == "healer" and source == "pick" and R.Pick() == "healer", tostring(role) .. " " .. tostring(source))
check(R.Summary() == nil, "a hand pick has no Auto summary")
__groupRole, __inGroup = "TANK", true; fire("PLAYER_ROLES_ASSIGNED")
check(R.Current() == "healer", "a group role does not beat a hand pick")
__points = { 31, 0, 0 }; fire("PLAYER_TALENT_UPDATE")
check(R.Current() == "healer", "talents do not beat a hand pick")
R.SetPick("auto")
local r2, s2 = R.Current()
check(r2 == "tank" and s2 == "group", "auto again: " .. tostring(r2) .. " " .. tostring(s2))
check(R.SetPick("bard") == false and R.Pick() == "auto", "an unknown pick is refused")
check(R.SetPick(nil) == false and R.SetPick(SECRET) == false, "nil and a secret are refused")
"""),

    ("the pick is stored per character and mirrored account wide by GUID", r"""
local R = enter()
R.SetPick("tank")
check(ForeverSTUwaveCharDB and ForeverSTUwaveCharDB.role == "tank", "char store")
check(ForeverSTUwaveDB == nil, "the account table is never created")
R.SetPick("auto")
check(ForeverSTUwaveCharDB.role == nil, "auto is stored as nothing")

local db = { profiles = {} }
local R2 = enter({ db = db })
R2.SetPick("ranged")
check(db.roleByChar and db.roleByChar["Player-1-AAAA"] == "ranged", "account copy by GUID")
check(db.profiles and next(db.profiles) == nil, "the profiles table is untouched")
R2.SetPick("auto")
check(db.roleByChar["Player-1-AAAA"] == nil, "auto clears the copy")
"""),

    ("the pick comes back at login from the character table, else from the account copy", r"""
local R = enter({ char = { role = "healer" } })
check(R.Pick() == "healer" and R.Current() == "healer", "char table")
local R2 = enter({ db = { roleByChar = { ["Player-1-AAAA"] = "tank", ["Player-9-ZZZZ"] = "healer" } } })
check(R2.Pick() == "tank", "account copy of this character, not the other one: " .. R2.Pick())
local R3 = enter({ char = { role = "melee" }, db = { roleByChar = { ["Player-1-AAAA"] = "tank" } } })
check(R3.Pick() == "melee", "the character table wins")
local R4 = enter({ char = { role = "bard" }, db = { roleByChar = { ["Player-1-AAAA"] = 7 } } })
check(R4.Pick() == "auto", "bad stored values read as Auto")
local R5 = enter({ char = "junk", db = "junk" })
check(R5.Pick() == "auto", "stores that are not tables")
R5.SetPick("tank")
check(R5.Pick() == "tank" and type(ForeverSTUwaveDB) == "string", "a junk account table is never replaced")
"""),

    ("a read only profile keeps the pick in memory and writes only the character table", r"""
local db = {}
local R = enter({ db = db })
FS.Config.readOnly = true
check(R.SetPick("tank") == true and R.Pick() == "tank", "in memory")
check(ForeverSTUwaveCharDB.role == "tank", "char table written")
check(db.roleByChar == nil or db.roleByChar["Player-1-AAAA"] == nil, "account copy not written while read only")
"""),

    ("no GUID yet: the pick is held in memory and written once the GUID is known", r"""
__guid = nil
local db = {}
local R = enter({ db = db })
R.SetPick("healer")
check(R.Pick() == "healer", "in memory")
check(db.roleByChar == nil, "no made up key")
__guid = "Player-1-AAAA"
fire("PLAYER_ENTERING_WORLD")
check(db.roleByChar and db.roleByChar["Player-1-AAAA"] == "healer", "copied once the GUID reads")
"""),

    ("OnChange: a pick, a talent change and a group change each fire once, and only when the role or source moved", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
local R = enter()
local seen = {}
R.OnChange(function(role, source, was) seen[#seen + 1] = role .. ":" .. source .. ":" .. tostring(was) end)
R.SetPick("healer")
check(#seen == 1 and seen[1] == "healer:pick:melee", "pick: " .. table.concat(seen, ","))
R.SetPick("healer")
check(#seen == 1, "the same pick again fires nothing")
R.SetPick("auto")
check(#seen == 2 and seen[2] == "melee:talents:healer", "auto: " .. table.concat(seen, ","))
__points = { 0, 0, 31 }; fire("PLAYER_TALENT_UPDATE")
check(#seen == 3 and seen[3] == "healer:talents:melee", "talents: " .. table.concat(seen, ","))
fire("PLAYER_TALENT_UPDATE")
check(#seen == 3, "an event that changes nothing fires nothing")
__groupRole, __inGroup = "TANK", true; fire("GROUP_ROSTER_UPDATE")
check(#seen == 4 and seen[4] == "tank:group:healer", "group: " .. table.concat(seen, ","))
__groupRole = "HEALER"; fire("PLAYER_ROLES_ASSIGNED")
check(#seen == 5, "tank to healer by group")
__groupRole = "NONE"; fire("GROUP_ROSTER_UPDATE")
check(#seen == 6 and seen[6] == "healer:talents:healer", "same role, new source still fires: " .. tostring(seen[6]))
"""),

    ("OnChange: a failing listener does not stop the others or the role", r"""
local R = enter()
local got = 0
R.OnChange(function() error("boom") end)
R.OnChange(function() got = got + 1 end)
check(R.SetPick("tank") == true, "pick")
check(got == 1 and R.Current() == "tank", "the second listener ran")
check(R.OnChange(nil) == false and R.OnChange("x") == false, "a non function is refused")
"""),

    ("talent points are read on talent events, not on every group event", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
local reads = 0
local R = enter({ login = false })
FS.CharBackdrop.TreePoints = function() reads = reads + 1; return __points end
fire("PLAYER_LOGIN")
local atLogin = reads
check(atLogin >= 1, "read at login")
for i = 1, 10 do fire("GROUP_ROSTER_UPDATE") end
check(reads == atLogin, "ten roster events read the talents " .. (reads - atLogin) .. " more times")
fire("PLAYER_TALENT_UPDATE")
check(reads == atLogin + 1, "one talent event, one read")
R.Current(); R.Current(); R.Current()
check(reads == atLogin + 1, "Current is a cached answer")
"""),

    ("the events register through the safe path, an unknown name is skipped, a missing helper still works", r"""
local R = enter()
local seen = {}
for _, f in ipairs(__frames) do for e in pairs(f.events) do seen[e] = true end end
for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "GROUP_ROSTER_UPDATE", "PLAYER_ROLES_ASSIGNED", "PLAYER_TALENT_UPDATE",
    "CHARACTER_POINTS_CHANGED", "TRAIT_CONFIG_UPDATED", "ACTIVE_TALENT_GROUP_CHANGED" }) do
    check(seen[e], "not listening to " .. e)
end
local R2 = enter({ noHelpers = true })
local seen2 = 0
for _, f in ipairs(__frames) do for e in pairs(f.events) do seen2 = seen2 + 1 end end
check(seen2 >= 5, "without the helper the events still register: " .. seen2)
"""),

    ("settings: defaults, kinds, ranges and options", r"""
local R = enter({ login = false })
local want = {
    ["tank.aggro"] = { "tank", true }, ["tank.threat"] = { "tank", "off" }, ["tank.lost"] = { "tank", true },
    ["tank.lost.snd"] = { "tank", true },
    ["heal.incoming"] = { "healer", true }, ["heal.range"] = { "healer", true }, ["heal.dispel"] = { "healer", true },
    ["heal.hp"] = { "healer", "missing" }, ["heal.aggro"] = { "healer", true }, ["heal.aggro.snd"] = { "healer", true },
    ["melee.warn"] = { "melee", true }, ["melee.pct"] = { "melee", 90 }, ["melee.aggro"] = { "melee", true },
    ["melee.range"] = { "melee", true },
    ["ranged.warn"] = { "ranged", true }, ["ranged.pct"] = { "ranged", 90 }, ["ranged.aggro"] = { "ranged", true },
    ["ranged.range"] = { "ranged", true },
}
local n = 0
for key, w in pairs(want) do
    n = n + 1
    local s = R.SETTINGS[key]
    check(s, "no setting " .. key)
    check(s.role == w[1] and s.default == w[2], key .. " is " .. tostring(s.role) .. " " .. tostring(s.default))
    check(FS.Config.defaults[key] == w[2], "default not registered for " .. key)
end
check(#R.KEYS == n, "the key list has " .. #R.KEYS .. " keys, want " .. n)
check(R.SETTINGS["tank.threat"].kind == "choice" and #R.SETTINGS["tank.threat"].options == 3, "threat choice")
local o = R.SETTINGS["tank.threat"].options
check(o[1].value == "off" and o[2].value == "pct" and o[3].value == "lead", "threat options")
local h = R.SETTINGS["heal.hp"].options
check(h[1].value == "none" and h[2].value == "percent" and h[3].value == "missing", "health text options")
local p = R.SETTINGS["melee.pct"]
check(p.kind == "slider" and p.min == 70 and p.max == 100 and p.step == 5, "the warn slider is 70 to 100 step 5")
check(R.SETTINGS["ranged.pct"].min == 70 and R.SETTINGS["ranged.pct"].max == 100, "ranged slider")
"""),

    ("settings: a bad stored value reads as the default, a slider is held to its range and step", r"""
local R = enter({ config = { ["tank.aggro"] = "yes", ["tank.threat"] = "loud", ["melee.pct"] = "lots", ["ranged.pct"] = 51,
    ["heal.hp"] = 4 } })
check(R.Get("tank.aggro") == true, "a word for a switch")
check(R.Get("tank.threat") == "off", "an unknown choice")
check(R.Get("melee.pct") == 90, "a word for a number")
check(R.Get("ranged.pct") == 70, "a number past the range is held to it, got " .. tostring(R.Get("ranged.pct")))
check(R.Get("heal.hp") == "missing", "a number for a choice")
FS.Config.Set("melee.pct", 83)
check(R.Get("melee.pct") == 85, "a value off the step snaps: " .. tostring(R.Get("melee.pct")))
FS.Config.Set("melee.pct", 500)
check(R.Get("melee.pct") == 100, "past the top")
check(R.Get("no.such.key") == nil, "an unknown key")
"""),

    ("settings of other roles keep their values and do nothing", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
local R = enter()
FS.Config.Set("tank.aggro", false)
FS.Config.Set("heal.incoming", false)
FS.Config.Set("melee.warn", false)
check(R.Current() == "melee", "melee")
check(R.Active("melee.warn") == true and R.Active("tank.aggro") == false and R.Active("heal.incoming") == false, "active")
check(R.Disabled("melee.warn") == true, "your own switch off is disabled")
check(R.Disabled("tank.aggro") == false and R.Disabled("heal.incoming") == false, "another role's switch off does nothing")
check(R.Value("melee.pct") == 90 and R.Value("tank.threat") == nil, "Value is nil for another role")
check(FS.Config.Get("tank.aggro") == false and FS.Config.Get("heal.incoming") == false, "their values are kept")
R.SetPick("healer")
check(R.Disabled("heal.incoming") == true and R.Disabled("melee.warn") == false, "now the healer ones act")
check(R.Disabled("tank.threat") == false, "a choice is never disabled")
check(R.Disabled("no.such.key") == false and R.Active("no.such.key") == false, "unknown keys act on nothing")
"""),

    ("settings: no Config means defaults, no crash", r"""
FS = { IsSecret = function() return false end }
__frames = {}
assert(load(__ROLE_SRC, "@Role.lua"))("forever-stuwave", FS)
local R = FS.Role
check(R.Get("tank.aggro") == true and R.Get("heal.hp") == "missing", "defaults without a config")
"""),

    ("the party rows repaint at once on a role change and on a healer switch, and only then", r"""
__class, __points = "SHAMAN", { 0, 31, 0 }
local R = enter({ login = false })
local runs = {}
FS.PartyFrames = { rows = {
    { events = { GetScript = function() return function(_, event) runs[#runs + 1] = event end end } },
    { events = { GetScript = function() return function() error("a row failed") end end } },
    { events = { GetScript = function() return nil end } },
    "junk",
} }
fire("PLAYER_LOGIN")
local base = #runs
R.SetPick("healer")
check(#runs == base + 1 and runs[#runs] == "PLAYER_REGEN_ENABLED", "a pick repaints the rows (a failing or missing row is skipped)")
FS.Config.Set("heal.dispel", false)
check(#runs == base + 2, "a healer switch repaints")
FS.Config.Set("heal.incoming", false)
FS.Config.Set("heal.range", false)
check(#runs == base + 4, "each healer switch repaints")
FS.Config.Set("heal.hp", "percent")
FS.Config.Set("tank.aggro", false)
check(#runs == base + 4, "other keys do not")
FS.PartyFrames = nil
FS.Config.Set("heal.dispel", true)
"""),

    ("Role.Describe names each role and source in words", r"""
local R = enter()
check(R.TEXT.melee == "Melee" and R.TEXT.healer == "Healer", "texts")
check(R.SOURCE_TEXT.talents == "from talents" and R.SOURCE_TEXT.group == "from group" and R.SOURCE_TEXT.class == "from class",
    "source texts")
"""),
]


# ---- the page tests: the real Role.lua and PlateThreat.lua under the config window mock ------------------------------

def proto_roles() -> dict:
    """The role page of proto-pages.js: {tab: {"label": .., "sections": [{title, role, hidden, tip, rows}]}}."""
    src = PROTO.read_text(encoding="utf-8")
    start = src.index(" {key:'role',label:'Roles',tabs:[")
    end = src.index("\n {key:'party'", start)
    block = src[start:end]

    def text(field: str, chunk: str):
        m = re.search(rf"(?:^|,){field}:'((?:[^'\\]|\\.)*)'", chunk)
        return m.group(1).replace("\\'", "'") if m else None

    tabs = {}
    for tab in re.split(r"\n  \{key:'", block)[1:]:
        key = tab.split("'", 1)[0]
        label = re.search(r"label:'([^']*)'", tab).group(1)
        sections = []
        for sec in re.split(r"\{t:'", tab)[1:]:
            title = sec.split("'", 1)[0]
            head, _, body = sec.partition("rows:[")
            section = {"title": title, "role": text("role", head), "hidden": "hidden:1" in head, "tip": text("tip", head), "rows": []}
            for m in re.finditer(r"\{ty:'(\w+)',([^{}]*)\}", body):
                ty, rest = m.groups()
                row = {"ty": ty}
                for field in ("k", "l", "tip", "needs", "nl", "u"):
                    value = text(field, rest)
                    if value is not None:
                        row[field] = value
                d = re.search(r"(?:^|,)d:('[^']*'|[0-9.]+|true|false)", rest)
                if d:
                    raw = d.group(1)
                    row["d"] = raw.strip("'") if raw.startswith("'") else (raw == "true" if raw in ("true", "false") else float(raw))
                for field in ("min", "max", "st"):
                    f = re.search(rf"(?:^|,){field}:(\d+)", rest)
                    if f:
                        row[field] = int(f.group(1))
                row["sub"] = bool(re.search(r"(?:^|,)sub:1", rest))
                row["nodot"] = bool(re.search(r"(?:^|,)nodot:1", rest))
                o = re.search(r"(?:^|,)o:(\[[^\]]*\])", rest)
                if o:
                    row["o"] = re.findall(r"'([^']*)'", o.group(1))
                c = re.search(r"(?:^|,)c:\[(\[.*\])\]", rest)
                if c:
                    row["c"] = [list(pair) for pair in re.findall(r"\['(#[0-9a-f]{6})','([^']*)'\]", c.group(1))]
                section["rows"].append(row)
            sections.append(section)
        tabs[key] = {"label": label, "sections": sections}
    return tabs


# Stored values of the prototype's option text.
STORED = {"Auto": "auto", "Off": "off", "Aggro %": "pct", "Lead": "lead", "None": "none", "Percent": "percent",
          "Missing": "missing"}

PAGE_CHECKS = r"""
local function roles(opts)
    opts = opts or {}
    return function()
        FS.IsSecret = function() return false end
        UnitClass = function() return "Shaman", opts.class or "SHAMAN" end
        UnitGroupRolesAssigned = function() return opts.group or "NONE" end
        if not opts.noRole then assert(load(__ROLE, "@Core/Role.lua"))("forever-stuwave", FS) end
        if not opts.noThreat then assert(load(__THREAT, "@Modules/Nameplates/PlateThreat.lua"))("forever-stuwave", FS) end
    end
end
local TABS = { "tank", "healer", "melee", "ranged" }
local function openAll(W) for _, tab in ipairs(TABS) do W.Open("role", tab) end end
local function bandOf()
    for _, o in ipairs(ALL) do if o.fsBand and o:IsShown() then return o end end
end
local function sections()
    local out = {}
    for _, o in ipairs(ALL) do
        local sec = o.fsSection
        if sec and o:IsVisible() then out[#out + 1] = { title = sec.title, meta = sec.meta:GetText(), color = sec.meta.themeColor } end
    end
    return out
end
local function hex(c)
    return string.format("#%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5))
end
local function arrows()
    local strip = FS.ConfigWindow.I.ui.strips.role
    local out = {}
    for _, b in ipairs(strip.fsButtons) do
        if b.fsMark and b.fsMark:IsShown() then out[#out + 1] = b.fsTabKey end
    end
    return table.concat(out, ",")
end
local function entries(tab)
    local out = {}
    for _, e in ipairs(FS.ConfigWindow.Rows()) do if e.page == "role" and (tab == nil or e.tab == tab) then out[#out + 1] = e end end
    return out
end

function T.the_roles_page_has_every_prototype_row_with_its_label_key_range_default_and_tip()
    local W = boot({ preWindow = roles() })
    local seen, swatches = 0, 0
    for _, tab in ipairs(__PROTO) do
        W.Open("role", tab.key)
        local at = 0
        for _, sec in ipairs(tab.sections) do
            if not sec.hidden then
                for _, want in ipairs(sec.rows) do
                    if want.ty == "swatch" then
                        swatches = swatches + 1
                        local found
                        for _, e in ipairs(entries(tab.key)) do
                            if e.kind == "swatch" and e.section == sec.title then found = e end
                        end
                        if not found then error("no swatch row in " .. tab.key .. " / " .. sec.title) end
                        eq(found.label, want.l, "swatch label")
                        eq(found.sub, true, "swatch sub")
                        eq(found.needs, want.needs, "swatch needs")
                        local have = FS.PlateThreat.SWATCHES[tab.key]
                        eq(#have, #want.c, tab.key .. " swatch chips")
                        for i, pair in ipairs(want.c) do
                            eq(hex(have[i][1]), pair[1], tab.key .. " chip " .. i .. " colour")
                            eq(have[i][2], pair[2], tab.key .. " chip " .. i .. " word")
                            yes(findText(pair[2], found.row), tab.key .. " shows no chip " .. pair[2])
                        end
                    else
                        seen = seen + 1
                        local e = W.RowByKey(want.k, "role")
                        if not e then error("no row " .. want.k .. " (" .. want.l .. ")") end
                        eq(e.label, want.l, want.k .. " label")
                        eq(e.tab, tab.key, want.k .. " tab")
                        eq(e.section, sec.title, want.k .. " section")
                        eq(e.sub, want.sub, want.k .. " sub")
                        eq(e.needs, want.needs, want.k .. " needs")
                        if want.ty == "sl" then
                            eq(e.min, want.min, want.k .. " min"); eq(e.max, want.max, want.k .. " max")
                            eq(FS.Config.Get(want.k), want.d, want.k .. " default")
                            eq(e.row.fsUnit:GetText(), want.u, want.k .. " unit")
                            eq(FS.Role.SETTINGS[want.k].step, want.st, want.k .. " step")
                        elseif want.ty == "sw" then
                            eq(FS.Config.Get(want.k), want.d, want.k .. " default")
                            eq(e.kind, "switch", want.k .. " kind")
                        else
                            eq(FS.Config.Get(want.k), want.stored, want.k .. " default")
                            local have = texts(e.row)
                            for _, option in ipairs(want.o) do
                                local found = false
                                for _, t in ipairs(have) do if t == option then found = true end end
                                yes(found, want.k .. " has no option " .. option)
                            end
                        end
                        if want.tip then eq(e.tip, want.tip, want.k .. " tip") end
                    end
                end
            end
        end
    end
    yes(seen >= 16, "only " .. seen .. " prototype rows were checked")
    eq(swatches, 3, "three swatch rows")
end

function T.the_sections_of_each_tab_are_the_prototype_sections_in_order()
    local W = boot({ preWindow = roles() })
    for _, tab in ipairs(__PROTO) do
        W.Open("role", tab.key)
        local want, have = {}, {}
        for _, sec in ipairs(tab.sections) do if not sec.hidden then want[#want + 1] = sec.title end end
        for _, s in ipairs(sections()) do have[#have + 1] = s.title end
        eq(table.concat(have, ","), table.concat(want, ","), tab.key .. " sections")
        for _, sec in ipairs(tab.sections) do
            if sec.tip then
                local found
                for _, o in ipairs(ALL) do
                    local s = o.fsSection
                    if s and o:IsVisible() and s.title == sec.title then found = s.tip end
                end
                eq(found, sec.tip, sec.title .. " section tip")
            end
        end
    end
end

function T.every_tab_carries_the_pinned_role_bar_with_the_five_picks_and_one_registry_row()
    local W = boot({ preWindow = roles() })
    for _, tab in ipairs(TABS) do
        W.Open("role", tab)
        local band = bandOf()
        yes(band, "no band on " .. tab)
        yes(findText("YOUR ROLE", band), tab .. " bar has no YOUR ROLE label")
        local have = {}
        for _, t in ipairs(texts(band)) do have[#have + 1] = t end
        local joined = table.concat(have, "|")
        for _, option in ipairs({ "Auto", "Tank", "Healer", "Melee", "Ranged" }) do
            yes(joined:find(option, 1, true), tab .. " bar has no " .. option)
        end
        local tip
        for _, o in ipairs(ALL) do if o.fsTip and under(band, o) then tip = o.fsTip end end
        yes(tip and tip:find("Auto uses your group role", 1, true), tab .. " bar is not explained by the prototype tip")
        yes(tip:find("Saved per character.", 1, true), "the prototype's last sentence")
    end
    local mine = 0
    for _, e in ipairs(W.Rows()) do if e.page == "role" and e.key == "role" then mine = mine + 1 end end
    eq(mine, 1, "Your role is one row for search")
    local e = W.RowByKey("role", "role")
    eq(e.label, "Your role"); eq(e.nodot, true, "the pick is not a changed setting")
end

function T.the_role_bar_is_not_a_row_of_the_scrolling_page()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    local band = bandOf()
    local e = W.RowByKey("role", "role")
    yes(under(band, e.row), "the bar row lives in the band")
    local rec = FS.ConfigWindow.I.ui.tabRec
    for _, item in ipairs(rec.page.fsHolder.fsFlow) do
        yes(item.frame ~= e.row, "the bar row is still in the flow")
    end
end

function T.the_bar_shows_what_auto_chose_and_a_pick_replaces_it()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    local band = bandOf()
    yes(findText("MELEE, FROM CLASS", band), "Auto with no other reading says what chose it")
    yes(click("Healer", band), "the Healer pick did not click")
    eq(FS.Role.Pick(), "healer"); eq((FS.Role.Current()), "healer")
    no(findText("MELEE, FROM CLASS", band), "the summary stays after a hand pick")
    no(hasText(band, "FROM"), "no summary on a pick")
    yes(click("Auto", band))
    eq(FS.Role.Pick(), "auto")
    yes(findText("MELEE, FROM CLASS", band), "the summary is back on Auto")
end

function T.the_bar_tip_says_why_auto_chose_what_it_chose()
    local W = boot({ preWindow = roles() })
    W.Open("role", "melee")
    local band = bandOf()
    local tip
    for _, o in ipairs(ALL) do if o.fsTip and under(band, o) then tip = o.fsTip end end
    yes(tip:find(FS.Role.Why(), 1, true), "the tip does not carry Role.Why()")
    FS.Role.SetPick("tank")
    for _, o in ipairs(ALL) do if o.fsTip and under(band, o) then tip = o.fsTip end end
    yes(tip:find("You picked Tank by hand.", 1, true), "the tip did not follow the pick")
end

function T.a_section_is_tagged_your_role_or_the_role_it_is_for()
    local W = boot({ preWindow = roles() })
    local C = FS.ConfigWindow.C
    W.Open("role", "tank")
    for _, s in ipairs(sections()) do
        eq(s.meta, "TANK ONLY", s.title); eq(s.color, C.amber, s.title .. " colour")
    end
    W.Open("role", "healer")
    for _, s in ipairs(sections()) do eq(s.meta, "HEALER ONLY", s.title) end
    W.Open("role", "melee")
    for _, s in ipairs(sections()) do
        eq(s.meta, "YOUR ROLE", s.title); eq(s.color, C.cyan, s.title .. " colour")
    end
    W.Open("role", "ranged")
    for _, s in ipairs(sections()) do eq(s.meta, "RANGED ONLY", s.title) end
end

function T.a_role_change_retags_the_sections_and_moves_the_arrow_at_once()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    eq(arrows(), "melee", "the arrow starts on the Melee tab (a Shaman by class)")
    FS.Role.SetPick("tank")
    for _, s in ipairs(sections()) do eq(s.meta, "YOUR ROLE", s.title) end
    eq(arrows(), "tank")
    FS.Role.SetPick("healer")
    for _, s in ipairs(sections()) do eq(s.meta, "TANK ONLY", s.title) end
    eq(arrows(), "healer")
    W.Open("role", "healer")
    for _, s in ipairs(sections()) do eq(s.meta, "YOUR ROLE", s.title) end
    FS.Role.SetPick("auto")
    eq(arrows(), "melee", "back on Auto")
end

function T.the_tab_arrow_is_a_small_cyan_pixel_triangle_in_the_tab_and_only_one_shows()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    local strip = FS.ConfigWindow.I.ui.strips.role
    local shown = 0
    for _, b in ipairs(strip.fsButtons) do
        if b.fsMark and b.fsMark:IsShown() then
            shown = shown + 1
            eq(b.fsMark.fsGlyph.direction, "left", "it points left, as the prototype's does")
            eq(#b.fsMark.fsGlyph.textures, 4, "drawn from rects, not typed")
            for _, t in ipairs(b.fsMark.fsGlyph.textures) do
                for i = 1, 3 do yes(math.abs(t.color[i] - FS.ConfigWindow.C.cyan[i]) < 0.002, "cyan") end
            end
        end
        no(b.fsRoleArrow, "the page no longer reaches into the strip's buttons")
    end
    eq(shown, 1)
end

function T.the_rows_of_another_role_stay_editable()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    eq(FS.Config.Get("tank.aggro"), true)
    yes(press("Aggro colours"), "the tank's switch did not press while the role is melee")
    eq(FS.Config.Get("tank.aggro"), false)
    yes(press("Lost aggro"))
    eq(FS.Config.Get("tank.lost"), false)
end

function T.dependent_rows_follow_their_switch()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    local sound, colours = W.RowByKey("tank.lost.snd", "role"), nil
    for _, e in ipairs(entries("tank")) do if e.kind == "swatch" then colours = e end end
    no(sound.disabled, "the sound row starts on")
    no(colours.disabled, "the colours row starts on")
    FS.Config.Set("tank.lost", false)
    yes(W.RowByKey("tank.lost.snd", "role").disabled, "Sound follows Lost aggro")
    FS.Config.Set("tank.aggro", false)
    yes(colours.disabled, "Colours follows Aggro colours")
    yes(colours.why and colours.why:find("Aggro colours", 1, true), "the reason names the switch")
    W.Open("role", "melee")
    FS.Config.Set("melee.warn", false)
    yes(W.RowByKey("melee.pct", "role").disabled, "Warn at follows Warn near the tank")
    FS.Config.Set("melee.aggro", false)
    local swatch
    for _, e in ipairs(entries("melee")) do if e.kind == "swatch" then swatch = e end end
    yes(swatch.disabled, "the melee colours follow their switch")
end

function T.the_colour_and_warn_rows_say_what_happens_when_the_game_hides_threat()
    local W = boot({ preWindow = roles() })
    openAll(W)
    for _, key in ipairs({ "tank.aggro", "melee.aggro", "ranged.aggro" }) do
        local e = W.RowByKey(key, "role")
        yes(e.tip and e.tip:find("hides your threat", 1, true), key .. " tip does not say what a hidden threat does")
    end
    for _, key in ipairs({ "melee.pct", "ranged.pct" }) do
        local e = W.RowByKey(key, "role")
        yes(e.tip and e.tip:find("hides the percent", 1, true), key .. " tip does not name the fallback")
    end
end

function T.the_health_text_row_says_it_is_not_applied_yet()
    local W = boot({ preWindow = roles() })
    W.Open("role", "healer")
    local e = W.RowByKey("heal.hp", "role")
    yes(e.disabled, "the row does nothing yet and is greyed")
    yes(e.why and e.why:find("Not applied yet", 1, true), "the reason says so")
    eq(FS.Config.Get("heal.hp"), "missing")
end

function T.the_threat_text_and_warn_rows_write_their_keys()
    local W = boot({ preWindow = roles() })
    W.Open("role", "tank")
    yes(click("Aggro %"), "Aggro % did not click")
    eq(FS.Config.Get("tank.threat"), "pct")
    yes(click("Lead"))
    eq(FS.Config.Get("tank.threat"), "lead")
    yes(click("Off"))
    eq(FS.Config.Get("tank.threat"), "off")
    W.Open("role", "ranged")
    FS.Config.Set("ranged.pct", 100)
    eq(W.RowByKey("ranged.pct", "role").row.fsEdit:GetText(), "100")
end

function T.the_page_leaves_out_what_the_modules_do_not_offer()
    local W = boot({ preWindow = roles({ noThreat = true }) })
    openAll(W)
    for _, e in ipairs(entries()) do no(e.kind == "swatch", "a swatch row without the plate threat module") end
    yes(W.RowByKey("tank.aggro", "role"), "the switch stays")
    W = boot({ preWindow = roles({ noRole = true, noThreat = true }) })
    openAll(W)
    eq(#entries(), 0, "no role module, no rows")
    no(bandOf(), "no role module, no bar")
    eq(arrows(), "", "no arrow without a role")
end

function T.search_finds_the_role_rows_and_the_bar_jump_does_not_fail()
    local W = boot({ preWindow = roles() })
    openAll(W)
    local e = W.RowByKey("role", "role")
    yes(e, "the bar row is in the registry")
    W.Open("role", "melee", "role")
    eq(#__errors, 0, "a jump to the bar row forwarded an error")
    local seen = {}
    for _, row in ipairs(entries()) do seen[row.label] = (seen[row.label] or 0) + 1 end
    eq(seen["Dim target out of melee range"], 1); eq(seen["Dim target out of spell range"], 1)
    eq(seen["Your role"], 1)
end

function T.the_page_text_has_no_dash_characters()
    local W = boot({ preWindow = roles() })
    openAll(W)
    local bad = string.char(0xE2, 0x80, 0x94)
    local bad2 = string.char(0xE2, 0x80, 0x93)
    for _, o in ipairs(ALL) do
        local t = o.kind == "FontString" and o:GetText() or o.fsTip
        if type(t) == "string" then
            yes(not t:find(bad, 1, true) and not t:find(bad2, 1, true), "a dash in: " .. t)
        end
    end
end
"""

# ---- python level checks -------------------------------------------------------------------------------------------

DASHES = (chr(0x2014), chr(0x2013))


def run_core(name: str, body: str, role_src: str, talent_src: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.globals().__ROLE_SRC = role_src
    lua.globals().__TALENT_ART = talent_src
    try:
        lua.execute(CORE_PRE)
        lua.execute(body)
    except LuaError as err:
        return " ".join(str(err).splitlines()[:4])[:900]
    return None


def check_no_dashes() -> list[str]:
    problems = []
    for path in (ROLE, THREAT, PAGE, Path(__file__)):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for mark in DASHES:
            if mark in text:
                problems.append(f"{path.name} has a dash character ({mark!r})")
    return problems


def check_files_in_toc_order() -> list[str]:
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("##")]
    problems = []
    for want in ("Core/Config.lua", "Core/Role.lua", "Modules/Nameplates/PlateThreat.lua", "Modules/Config/ConfigPageRoles.lua"):
        if want not in toc:
            problems.append(f"{want} is not in the .toc")
    if not problems:
        if not toc.index("Core/Config.lua") < toc.index("Core/Role.lua") < toc.index("Modules/UnitFrames/PartyFrames.lua"):
            problems.append("Role.lua must load after Config.lua and before PartyFrames.lua")
        if not toc.index("Modules/Nameplates/PlateThreat.lua") > toc.index("Core/Role.lua"):
            problems.append("PlateThreat.lua must load after Role.lua")
        if not toc.index("Modules/Config/ConfigPageRoles.lua") > toc.index("Modules/Nameplates/PlateThreat.lua"):
            problems.append("ConfigPageRoles.lua must load after PlateThreat.lua")
    if "## SavedVariablesPerCharacter: ForeverSTUwaveCharDB" not in TOC.read_text(encoding="utf-8"):
        problems.append("the per character saved variable is not declared in the .toc")
    return problems


def check_party_frames_gates() -> list[str]:
    """PartyFrames reads the healer switches through three of its existing parts and gets no new file scope local."""
    src = PARTY.read_text(encoding="utf-8")
    problems = []
    for key in ("heal.incoming", "heal.range", "heal.dispel"):
        if f'FS.Role.Disabled("{key}")' not in src:
            problems.append(f"PartyFrames.lua does not read {key}")
    parse = load("parse_gate", "parse-gate.py")
    count = parse.count_file_scope_locals(src)
    limit = 200
    if count >= limit:
        problems.append(f"PartyFrames.lua has {count} file scope locals (the limit is {limit})")
    return problems


def check_party_frames_local_count_did_not_grow() -> list[str]:
    parse = load("parse_gate", "parse-gate.py")
    count = parse.count_file_scope_locals(PARTY.read_text(encoding="utf-8"))
    print(f"      PartyFrames.lua file scope locals: {count}")
    return []


BASE = load("configwindow_harness", "configwindow-harness.py")


def run_page_checks(role_source: str, threat_source: str, rows: dict) -> int:
    tabs = []
    for key, tab in rows.items():
        sections = []
        for sec in tab["sections"]:
            wanted = []
            for item in sec["rows"]:
                item = dict(item)
                if item["ty"] == "seg" and "d" in item:
                    item["stored"] = STORED[item["d"]]
                wanted.append(item)
            sections.append({"title": sec["title"], "hidden": sec["hidden"], "tip": sec["tip"], "rows": wanted})
        tabs.append({"key": key, "label": tab["label"], "sections": sections})
    names = sorted(re.findall(r"^function T\.([a-z0-9_]+)\(", PAGE_CHECKS, re.M))
    original = BASE.CHECKS
    BASE.CHECKS = original.replace("__checks = T", PAGE_CHECKS + "\n__checks = T")
    failed = 0
    try:
        for name in names:
            try:
                lua = BASE.boot()
                lua.globals().__ROLE = role_source
                lua.globals().__THREAT = threat_source
                lua.globals().__PROTO = BASE.to_lua(lua, tabs)
                lua.eval("__checks")[name]()
                leaked = list(lua.eval("__errors").values())
                if leaked:
                    raise LuaError(f"errors were forwarded to the error handler: {leaked}")
                print(f"ok    {name}")
            except LuaError as err:
                failed += 1
                print(f"FAIL  {name}\n      {' '.join(str(err).splitlines()[:3])[:700]}")
    finally:
        BASE.CHECKS = original
    return failed


def check_arrow_goes_through_the_window_hook() -> list[str]:
    """The tab arrow is set with CW.TabMark; the page does not walk the window's strips or tab buttons."""
    code = "\n".join(line.split("--", 1)[0] for line in PAGE.read_text(encoding="utf-8").splitlines())
    problems = []
    if "CW.TabMark" not in code:
        problems.append("ConfigPageRoles.lua does not use CW.TabMark")
    for needle in ("I.ui", "fsButtons", "fsRoleArrow"):
        if needle in code:
            problems.append(f"ConfigPageRoles.lua reaches into the window with {needle}")
    return problems


def check_page_text_stays_neutral() -> list[str]:
    """Client visible text keeps to the neutral wording."""
    problems = []
    terms = re.compile(r"(?<![a-z])bots?(?![a-z])|harness|pixel|bridge|beacon|python|automat|probe|recon", re.I)
    for number, line in enumerate(PAGE.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("--"):
            continue
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', line):
            if terms.search(literal):
                problems.append(f"{PAGE.name}:{number}: {literal[:60]}")
    return problems


def main() -> int:
    role_source = role_src = ROLE.read_text(encoding="utf-8")
    threat_source = THREAT.read_text(encoding="utf-8")
    talent_src = TALENT_ART.read_text(encoding="utf-8")
    failures = 0
    total = 0
    for name, body in CORE_CASES:
        total += 1
        error = run_core(name, body, role_src, talent_src)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    for label, problems in (
        ("role_files_load_in_toc_order", check_files_in_toc_order()),
        ("no_dash_characters_in_the_role_files", check_no_dashes()),
        ("party_frames_reads_the_healer_switches", check_party_frames_gates()),
        ("party_frames_local_count", check_party_frames_local_count_did_not_grow()),
        ("roles_page_text_uses_neutral_words", check_page_text_stays_neutral()),
        ("roles_page_arrow_goes_through_the_window_hook", check_arrow_goes_through_the_window_hook()),
    ):
        total += 1
        if problems:
            failures += 1
            print(f"FAIL  {label}\n      " + "\n      ".join(problems))
        else:
            print(f"ok    {label}")
    rows = proto_roles()
    if sorted(rows) != ["healer", "melee", "ranged", "tank"]:
        print(f"FAIL  the prototype's role page has tabs {sorted(rows)}")
        return 1
    page_names = len(re.findall(r"^function T\.", PAGE_CHECKS, re.M))
    total += page_names
    failures += run_page_checks(role_source, threat_source, rows)
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
