#!/usr/bin/env python3
"""Nameplate settings (ticket C2): the plate layout, text and parts, and the Nameplates page of /fsconfig.

Runs the real Modules/Nameplates/Nameplates.lua headless on the mock client of tools/nameplate-auras-harness.py and pins:

  * defaults leave the plate exactly as it was (sizes, anchors, fonts of every part, compared with a recording taken
    from the file before the settings existed);
  * every key reaches the plate layout, live: width, health, power and cast heights (0 hides the bar and the plate
    shrinks), name size, level, health text (none, percent, number, both: a secret value is never compared, text goes
    through SetFormattedText / SetText only, percent through UnitHealthPercent with CurveConstants.ScaleTo100), the quest,
    aura and raid marker parts, and the friendly plates (same, smaller, off);
  * a plate that is in the pool when a setting changes is laid out for it when it is taken again;
  * the colour and text providers (FS.Nameplates.SetColorProvider / SetTextProvider): called, a nil answer keeps the
    default, re-applied on a threat event, a failing provider is swallowed and logged once;
  * Nameplates.lua keeps no more file level locals than before (the parse gate limit is near);
  * every row of the four prototype tabs (mockups proto-pages.js) is on the page with its label, key, range, default and
    unit, the preview band sits on every tab, follows the settings and peeks and pulses the hovered part.

The mock is NOT the real client.

    python3 tools/nameplates-harness.py

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
SOURCE = ADDON / "Modules/Nameplates/Nameplates.lua"
PAGE = ADDON / "Modules/Config/ConfigPagePlates.lua"
COMBO = ADDON / "Modules/Nameplates/NameplateCombo.lua"
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))
PROTO = MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AURAS = load("nameplate_auras_harness", "nameplate-auras-harness.py")
PARSE_GATE = load("parse_gate", "parse-gate.py")
COMBO_HARNESS = load("nameplatecombo_harness", "nameplatecombo-harness.py")

# The file level locals Nameplates.lua had when the settings were added (parse gate limit 190, fails at 190).
LOCALS_BEFORE = 189

# Prototype keys, defaults and ranges. The page tests parse the same rows out of proto-pages.js and compare.
NUMBERS = {
    "w": ("plates.w", 130, 80, 240, 2),
    "hpH": ("plates.hpH", 14, 6, 30, 1),
    "mpH": ("plates.mpH", 5, 0, 12, 1),
    "castH": ("plates.castH", 6, 0, 16, 1),
    "nameSize": ("plates.nameSize", 10, 8, 16, 1),
}
BOOLS = {"level": "plates.level", "quest": "plates.quest", "auras": "plates.auras", "raidMark": "plates.raidMark"}
CHOICES = {
    "hpText": ("plates.hpText", "none", ["none", "percent", "number", "both"]),
    "friendly": ("plates.friendly", "same", ["same", "smaller", "off"]),
}


def lua_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua_literal(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ",".join(f"[{lua_literal(k)}]={lua_literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(value)


# ---- the mock client: the aura harness' mock plus unit data, a config store and a recording of every part ------------

PRE = r"""
local realType = type
SECRET = setmetatable({}, {
    __index = function() error("indexed a secret", 2) end,
    __newindex = function() error("wrote to a secret", 2) end,
    __lt = function() error("compared a secret", 2) end, __le = function() error("compared a secret", 2) end,
    __add = function() error("did math on a secret", 2) end, __sub = function() error("did math on a secret", 2) end,
    __mul = function() error("did math on a secret", 2) end, __div = function() error("did math on a secret", 2) end,
    __unm = function() error("did math on a secret", 2) end, __concat = function() error("joined a secret", 2) end,
    __call = function() error("called a secret", 2) end,
})
-- a secret number answers type() "number", exactly as it does on the client
function type(v) if rawequal(v, SECRET) then return "number" end return realType(v) end

U = {}
__target = nil
local function d(unit) return U[unit] or {} end
function GetUnitName(unit) return d(unit).name end
function UnitName(unit) return d(unit).name end
function UnitLevel(unit) if unit == "player" then return 20 end return d(unit).level end
function UnitClassification(unit) return d(unit).class end
function UnitIsPlayer(unit) return d(unit).player == true end
function UnitCanAttack(_, unit) return d(unit).hostile ~= false end
function UnitIsFriend(_, unit) return d(unit).friend == true end
function UnitReaction(unit) return d(unit).reaction or 2 end
function UnitIsDead() return false end
function UnitIsTapDenied(unit) return d(unit).tapped == true end
function UnitExists(unit) return U[unit] ~= nil or (unit == "target" and __target ~= nil) end
function UnitIsUnit(a, b) return b == "target" and __target == a end
function UnitHealth(unit) local x = d(unit) if x.secret then return SECRET end return x.health or 100 end
function UnitHealthMax(unit) local x = d(unit) if x.secret then return SECRET end return x.max or 100 end
function UnitPower() return 50 end
function UnitPowerMax() return 100 end
function UnitCastingInfo(unit) local c = d(unit).cast if c then return c, nil, "tex", 0, 1000, nil, nil, false end end
function UnitChannelInfo() end
function GetRaidTargetIndex(unit) return d(unit).mark end
function SetRaidTargetIconTexture() end
CurveConstants = { ScaleTo100 = { name = "ScaleTo100" } }
__pctCalls = {}
function UnitHealthPercent(unit, predicted, curve)
    __pctCalls[#__pctCalls + 1] = { unit, predicted, curve }
    if d(unit).pctThrows then error("boom: UnitHealthPercent") end
    if d(unit).secret then return SECRET end
    return d(unit).pct
end
function AbbreviateNumbers(v) if rawequal(v, SECRET) then return "A(secret)" end return "A(" .. tostring(v) .. ")" end

-- A config store like Core/Config.lua: a value equal to the default is stored as nothing, callbacks fire on a change.
function mkConfig(initial)
    local store, defaults, cbs = initial or {}, {}, {}
    local C = { store = store, defaults = defaults, listening = {} }
    function C.RegisterDefault(k, v) defaults[k] = v end
    function C.Get(k) local v = store[k]; if v == nil then return defaults[k] end return v end
    function C.IsStored(k) return store[k] ~= nil end
    function C.OnChange(k, f) cbs[k] = cbs[k] or {}; table.insert(cbs[k], f); C.listening[k] = true end
    function C.Set(k, v)
        local old = C.Get(k)
        if v == defaults[k] then v = nil end
        store[k] = v
        local new = C.Get(k)
        if old ~= new then for _, f in ipairs(cbs[k] or {}) do f(new, old, k) end end
        return true
    end
    return C
end

-- Loads the file before Theme.lua (the .toc order), then the config, then logs in.
function enter(initial)
    boot()
    FS.IsSecret = function(v) return rawequal(v, SECRET) end
    FS.Config = mkConfig(initial)
    fire("PLAYER_ENTERING_WORLD"); drain()
end
function plate(unit, data)
    U[unit] = data or { name = "Mob " .. unit, level = 22, health = 1984, max = 3100, pct = 64 }
    addPlate(unit)
    return FS.framesByUnit[unit], __plates and __plates[unit]
end
function set(key, value) check(FS.Config.Set(key, value), "the config refused " .. key) end
function sizeOf(f) local a = f._args.SetSize return a and a[1], a and a[2] end
function widthOf(f) local a = f._args.SetWidth return a and a[1] end
function heightOf(f) local a = f._args.SetHeight return a and a[1] end
function pointOf(f, point)
    for _, p in ipairs(f._points) do if p[1] == point then return p end end
end
function fontSizeOf(fs) local a = fs._args.SetFont return a and a[2] end

-- Everything a plate puts on screen that the settings can move, as sorted "part.field=value" lines.
function facts(root, plate)
    local names = {
        [root] = "root", [root.healthBar] = "healthBar", [root.powerBar] = "powerBar", [root.fsSizer] = "sizer",
        [root.castBar] = "castBar", [root.nameText] = "nameText", [root.raidMarker] = "raidMarker",
        [root.questIcon] = "questIcon", [root.castBar.nameText] = "castName", [root.targetMark[1]] = "mark1",
        [root.targetMark[2]] = "mark2", [root.targetMark[3]] = "mark3", [root.fsSizerAnchor] = "sizerFill",
    }
    names[plate] = "plate"
    local out = {}
    for obj, name in pairs(names) do
        for _, k in ipairs({ "SetSize", "SetWidth", "SetHeight", "SetFont" }) do
            local a = obj._args[k]
            if a then
                local t = {}
                for i = 1, #a do t[i] = tostring(a[i]) end
                out[#out + 1] = name .. "." .. k .. "=" .. table.concat(t, ",")
            end
        end
        for i, p in ipairs(obj._points) do
            out[#out + 1] = name .. ".pt" .. i .. "=" .. tostring(p[1]) .. ">" .. tostring(names[p[2]] or "?") .. "."
                .. tostring(p[3]) .. "@" .. tostring(p[4]) .. "," .. tostring(p[5])
        end
    end
    table.sort(out)
    return table.concat(out, "\n")
end

-- The module's data as Lua source, for the page tests (functions are left out).
function dump(t, seen)
    local kind = type(t)
    if kind == "string" then return string.format("%q", t) end
    if kind == "number" or kind == "boolean" then return tostring(t) end
    if kind ~= "table" then return "nil" end
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local parts = {}
    for _, k in ipairs(keys) do
        local v = t[k]
        if type(v) ~= "function" and not (type(v) == "table" and getmetatable(v)) then
            parts[#parts + 1] = "[" .. dump(k) .. "]=" .. dump(v)
        end
    end
    return "{" .. table.concat(parts, ",") .. "}"
end
function dumpModule()
    local N = FS.Nameplates
    return dump({ KEY = N.KEY, SETTING = N.SETTING, TARGET_MARK_SETTING = N.TARGET_MARK_SETTING,
        SETTINGS = N.SETTINGS, GEOMETRY = N.GEOMETRY, PALETTE = N.PALETTE })
end
"""

# What the plate looked like before the settings (taken with `facts` from the file at the merge of lane A).
GOLDEN = r"""
castBar.SetHeight=6
castBar.pt1=TOPLEFT>root.BOTTOMLEFT@1,-2
castBar.pt2=TOPRIGHT>root.BOTTOMRIGHT@-1,-2
castName.SetFont=MONO,9,OUTLINE
castName.pt1=LEFT>castBar.LEFT@2,0
castName.pt2=RIGHT>castBar.RIGHT@-2,0
healthBar.SetSize=132,16
healthBar.pt1=TOPLEFT>root.TOPLEFT@1,-1
mark1.SetSize=6,4
mark1.pt1=BOTTOMRIGHT>mark2.BOTTOMLEFT@0,0
mark2.SetSize=6,4
mark2.pt1=BOTTOM>healthBar.TOP@0,46
mark3.SetSize=6,4
mark3.pt1=BOTTOMLEFT>mark2.BOTTOMRIGHT@0,0
nameText.SetFont=MONO,10,OUTLINE
nameText.pt1=BOTTOMLEFT>healthBar.TOPLEFT@0,2
powerBar.SetSize=132,5
powerBar.pt1=TOPLEFT>healthBar.BOTTOMLEFT@0,-1
questIcon.SetFont=MONO,14,OUTLINE
questIcon.pt1=RIGHT>nameText.LEFT@-3,0
raidMarker.SetSize=25,25
raidMarker.pt1=BOTTOM>nameText.TOP@0,3
root.SetWidth=134
root.pt1=TOP>plate.CENTER@0,9
root.pt2=BOTTOM>sizerFill.BOTTOM@nil,nil
sizer.SetSize=1,6
sizer.pt1=TOP>plate.CENTER@0,-9
""".strip()

NUMBER_ROWS = lua_literal({f: list(v) for f, v in NUMBERS.items()})
BOOL_ROWS = lua_literal(BOOLS)
CHOICE_ROWS = lua_literal({f: [v[0], v[1], v[2]] for f, v in CHOICES.items()})

CASES: list[tuple[str, str, str]] = [
    ("defaults leave every part of the plate where it was", "true", r"""
enter()
local root, p = plate("nameplate1")
local got = facts(root, p)
if got ~= GOLDEN then
    local want, have = {}, {}
    for line in GOLDEN:gmatch("[^\n]+") do want[line] = true end
    local diff = {}
    for line in got:gmatch("[^\n]+") do have[line] = true; if not want[line] then diff[#diff + 1] = "new: " .. line end end
    for line in GOLDEN:gmatch("[^\n]+") do if not have[line] then diff[#diff + 1] = "lost: " .. line end end
    error("the default plate changed:\n" .. table.concat(diff, "\n"), 0)
end
"""),

    ("the settings table has the prototype keys, defaults and ranges", "true", r"""
boot()
local N = FS.Nameplates
check(type(N.SETTINGS) == "table", "no FS.Nameplates.SETTINGS")
for field, row in pairs(NUMBERS) do
    local s = N.SETTINGS[field]
    check(s, "no setting " .. field)
    check(s.key == row[1] and s.default == row[2] and s.min == row[3] and s.max == row[4] and s.step == row[5],
        field .. " is not " .. row[1] .. " " .. row[2] .. " " .. row[3] .. "-" .. row[4] .. " step " .. row[5])
end
for field, key in pairs(BOOLS) do
    local s = N.SETTINGS[field]
    check(s and s.key == key and s.default == true, "bad switch " .. field)
end
for field, row in pairs(CHOICES) do
    local s = N.SETTINGS[field]
    check(s and s.key == row[1] and s.default == row[2], "bad choice " .. field)
    check(#s.options == #row[3], field .. " option count")
    for i, v in ipairs(row[3]) do check(s.options[i].value == v and type(s.options[i].text) == "string", field .. " option " .. v) end
end
check(N.TARGET_MARK_SETTING and N.TARGET_MARK_SETTING.key == "nameplates.targetMark" and N.TARGET_MARK_SETTING.default == false,
    "the target mark switch must keep its key and its default off")
check(N.SETTING.key == "nameplates.enabled", "the module switch key changed")
local g = N.GEOMETRY
check(g and g.PAD == 2 and g.POWER_GAP == 1 and g.CAST_GAP == 2 and g.CAST_NAME_SIZE == 9 and g.RAID_SIZE == 25
    and g.RAID_GAP == 3 and g.QUEST_SIZE == 14 and g.QUEST_GAP == 3 and g.AURA_SIZE == 18 and g.AURA_GAP == 2
    and g.AURA_Y == 2 and g.SMALL_SCALE == 0.8 and g.MARK_W == 6 and g.MARK_H == 4, "the preview constants are not exported")
check(g.MARK_Y and g.MARK_Y[10] == 46 and N.TargetMarkY(10) == 46, "the target mark height at the default name size")
check(N.PALETTE and N.PALETTE.text and N.PALETTE.nameHostile and N.PALETTE.fillNeutral and N.PALETTE.fillFriend, "no palette")
"""),

    ("the settings register their defaults and listen at login, a saved bad value reads as the default", "true", r"""
enter({ ["plates.w"] = "wide", ["plates.hpH"] = 9999, ["plates.hpText"] = "loud", ["plates.level"] = "yes",
        ["plates.mpH"] = -4, ["plates.friendly"] = 3 })
local N, C = FS.Nameplates, FS.Config
for field, row in pairs(NUMBERS) do
    check(C.defaults[row[1]] == row[2], "no default for " .. row[1])
    check(C.listening[row[1]], "no listener for " .. row[1])
end
for _, key in pairs(BOOLS) do check(C.defaults[key] == true and C.listening[key], "switch " .. key) end
for _, row in pairs(CHOICES) do check(C.defaults[row[1]] == row[2] and C.listening[row[1]], "choice " .. row[1]) end
check(N.S.w == 130, "a word for the width gave " .. tostring(N.S.w))
check(N.S.hpH == 30, "a height past the range was not clamped: " .. tostring(N.S.hpH))
check(N.S.mpH == 0, "a negative power height was not clamped: " .. tostring(N.S.mpH))
check(N.S.hpText == "none", "an unknown health text gave " .. tostring(N.S.hpText))
check(N.S.level == true, "a word for a switch gave " .. tostring(N.S.level))
check(N.S.friendly == "same", "a number for the friendly choice gave " .. tostring(N.S.friendly))
"""),

    ("a config that answers true for every key leaves the defaults", "true", r"""
boot()
FS.IsSecret = function(v) return rawequal(v, SECRET) end
FS.Config = { RegisterDefault = function() end, Get = function() return true end, OnChange = function() end,
              Set = function() return true end, IsStored = function() return false end }
fire("PLAYER_ENTERING_WORLD"); drain()
local S = FS.Nameplates.S
check(S.w == 130 and S.hpH == 14 and S.mpH == 5 and S.castH == 6 and S.nameSize == 10, "numbers read true as a value")
check(S.hpText == "none" and S.friendly == "same", "choices read true as a value")
local root = plate("nameplate1")
check(widthOf(root) == 134, "the plate was laid out from a bad read")
"""),

    ("plate width reaches the root, both bars and a pooled plate", "true", r"""
enter()
local root = plate("nameplate1")
check(widthOf(root) == 134 and sizeOf(root.healthBar) == 132 and sizeOf(root.powerBar) == 132, "default widths")
set("plates.w", 160)
check(widthOf(root) == 164, "root width " .. tostring(widthOf(root)))
check(sizeOf(root.healthBar) == 162 and sizeOf(root.powerBar) == 162, "bar widths " .. tostring(sizeOf(root.healthBar)))
check(root.baseHeight == 18, "the width moved the height")
-- a plate in the pool when the setting changes is laid out for it when it is taken again
removePlate("nameplate1")
set("plates.w", 100)
local again = plate("nameplate1")
check(again == root, "the pooled plate was not reused")
check(widthOf(again) == 104 and sizeOf(again.healthBar) == 102, "the pooled plate kept the old width")
set("plates.w", 130)
check(widthOf(again) == 134, "back to the default")
"""),

    ("a plate built after a change is built for it", "true", r"""
enter()
set("plates.w", 200); set("plates.hpH", 20); set("plates.mpH", 8); set("plates.castH", 10)
local root = plate("nameplate1")
check(widthOf(root) == 204, "width " .. tostring(widthOf(root)))
local _, hh = sizeOf(root.healthBar)
check(hh == 22, "health fill height " .. tostring(hh))
local _, ph = sizeOf(root.powerBar)
check(ph == 8, "power height " .. tostring(ph))
check(heightOf(root.castBar) == 10, "cast height " .. tostring(heightOf(root.castBar)))
"""),

    ("health bar height moves the plate anchors with it", "true", r"""
enter()
local root, p = plate("nameplate1")
local top, sizerTop = pointOf(root, "TOP"), pointOf(root.fsSizer, "TOP")
check(top[2] == p and top[5] == 9 and sizerTop[5] == -9, "default anchors " .. tostring(top[5]) .. " " .. tostring(sizerTop[5]))
set("plates.hpH", 20)
check(root.baseHeight == 24, "base height " .. tostring(root.baseHeight))
local _, hh = sizeOf(root.healthBar)
check(hh == 22, "fill height " .. tostring(hh))
top, sizerTop = pointOf(root, "TOP"), pointOf(root.fsSizer, "TOP")
check(top[5] == 12 and sizerTop[5] == -12, "anchors did not follow: " .. tostring(top[5]) .. " " .. tostring(sizerTop[5]))
check(#root._points == 2, "the root has " .. #root._points .. " anchors")
"""),

    ("power bar height 0 hides the bar and the plate shrinks, back above 0 it grows again", "true", r"""
enter()
local root, p = plate("nameplate1")
check(root.powerBar:IsShown(), "no power bar at the default")
local bottom = pointOf(root, "BOTTOM")
check(bottom[2] == root.fsSizerAnchor, "the plate is not sized by the power strip at the default")
set("plates.mpH", 0)
check(not root.powerBar:IsShown(), "the bar is still shown at 0")
bottom = pointOf(root, "BOTTOM")
check(bottom[2] == p and bottom[5] == -9, "the plate bottom is not fixed under the health bar: " .. tostring(bottom[2] == p) .. " " .. tostring(bottom[5]))
fire("UNIT_MAXPOWER", "nameplate1"); fire("UNIT_DISPLAYPOWER", "nameplate1")
check(not root.powerBar:IsShown(), "a power event brought the bar back")
check(root.fsSizer._args.SetValue[1] == 0, "the sizer was left open")
check(root.fsMidWedge == nil or root.fsMidWedge._args.SetValue[1] == 0, "the mid wedge was left open")
-- a plate added at 0
local other = plate("nameplate2")
check(not other.powerBar:IsShown(), "a new plate has a power bar at 0")
set("plates.mpH", 8)
check(root.powerBar:IsShown() and other.powerBar:IsShown(), "the bar did not come back")
local _, ph = sizeOf(root.powerBar)
check(ph == 8, "power height " .. tostring(ph))
check(select(2, sizeOf(root.fsSizer)) == 9, "the sizer is not the strip plus its gap tall")
check(pointOf(root, "BOTTOM")[2] == root.fsSizerAnchor, "the plate is not sized by the strip again")
"""),

    ("cast bar height sets the bar, 0 never shows it", "true", r"""
enter()
local root = plate("nameplate1", { name = "Caster", level = 22, health = 100, max = 100, pct = 100, cast = "Howl" })
fire("UNIT_SPELLCAST_START", "nameplate1")
check(root.castBar:IsShown() and root.castActive, "no cast at the default")
check(heightOf(root.castBar) == 6, "default cast height")
set("plates.castH", 12)
check(heightOf(root.castBar) == 12, "cast height " .. tostring(heightOf(root.castBar)))
check(root.castBar:IsShown(), "a resize hid the cast")
set("plates.castH", 0)
check(not root.castBar:IsShown() and not root.castActive, "the cast stayed up at 0")
fire("UNIT_SPELLCAST_START", "nameplate1"); fire("UNIT_SPELLCAST_DELAYED", "nameplate1")
check(not root.castBar:IsShown(), "a cast event showed the bar at 0")
local other = plate("nameplate2", { name = "Caster", level = 22, health = 100, max = 100, pct = 100, cast = "Howl" })
check(not other.castBar:IsShown(), "a plate added mid cast showed the bar at 0")
set("plates.castH", 6)
check(root.castBar:IsShown() and other.castBar:IsShown(), "the cast did not come back when the bar did")
"""),

    ("name size sets the font and lifts the target mark with it", "true", r"""
enter()
local root = plate("nameplate1")
check(__routedThroughSetFontChecked(root.nameText, "MONO", 10), "the name did not start at 10")
local function markY() return pointOf(root.targetMark[2], "BOTTOM")[5] end
check(markY() == 46, "default mark height " .. tostring(markY()))
set("plates.nameSize", 16)
check(__routedThroughSetFontChecked(root.nameText, "MONO", 16) and fontSizeOf(root.nameText) == 16, "name size 16")
check(markY() == 52, "mark height at 16: " .. tostring(markY()))
set("plates.nameSize", 12)
check(fontSizeOf(root.nameText) == 12 and markY() == 48, "name size 12 " .. tostring(markY()))
check(#root.targetMark[2]._points == 1, "the mark was anchored twice")
removePlate("nameplate1")
set("plates.nameSize", 8)
local again = plate("nameplate1")
check(fontSizeOf(again.nameText) == 8, "a pooled plate kept the old name size")
check(fontSizeOf(again.castBar.nameText) == 9, "the cast name size is not a setting")
"""),

    ("level shows in the name until the switch turns it off", "true", r"""
enter()
local root = plate("nameplate1", { name = "Kolkar Packhound", level = 22, class = "elite", health = 100, max = 100, pct = 100 })
local text = root.nameText._args.SetText[1]
check(text:find("22+", 1, true) and text:find("Kolkar Packhound", 1, true), "level missing: " .. text)
set("plates.level", false)
check(root.nameText._args.SetText[1] == "Kolkar Packhound", "the level stayed: " .. root.nameText._args.SetText[1])
local other = plate("nameplate2", { name = "Wolf", level = 5, health = 100, max = 100, pct = 100 })
check(other.nameText._args.SetText[1] == "Wolf", "a plate added with the level off showed it")
set("plates.level", true)
check(root.nameText._args.SetText[1]:find("22+", 1, true), "the level did not come back")
check(other.nameText._args.SetText[1]:find("5", 1, true) and other.nameText._args.SetText[1]:find("Wolf", 1, true), "the level did not come back on the other plate")
"""),

    ("health text: none by default, percent, number and both, live", "true", r"""
enter()
local root = plate("nameplate1", { name = "Wolf", level = 5, health = 1984, max = 3100, pct = 64 })
check(root.hpText and not root.hpText:IsShown(), "health text is on by default")
check(#__pctCalls == 0, "the percent was read with the text off")
set("plates.hpText", "percent")
check(root.hpText:IsShown(), "percent is not shown")
local a = root.hpText._args.SetFormattedText
check(a and a[1] == "%.0f%%" and a[2] == 64, "percent text")
local c = __pctCalls[#__pctCalls]
check(c[1] == "nameplate1" and c[2] == false and c[3] == CurveConstants.ScaleTo100, "percent is not read with ScaleTo100")
set("plates.hpText", "number")
a = root.hpText._args.SetFormattedText
check(a[1] == "%s / %s" and a[2] == "A(1984)" and a[3] == "A(3100)", "number text: " .. tostring(a[1]) .. " " .. tostring(a[2]) .. " " .. tostring(a[3]))
set("plates.hpText", "both")
a = root.hpText._args.SetFormattedText
check(a[1] == "%s  %.0f%%" and a[2] == "A(1984)" and a[3] == 64, "both text: " .. tostring(a[1]))
U.nameplate1.health, U.nameplate1.pct = 1000, 32
fire("UNIT_HEALTH", "nameplate1")
a = root.hpText._args.SetFormattedText
check(a[2] == "A(1000)" and a[3] == 32, "a health event did not update the text")
set("plates.hpText", "none")
check(not root.hpText:IsShown(), "none left the text up")
-- a plate added with the text on, and one taken from the pool
set("plates.hpText", "percent")
local other = plate("nameplate2", { name = "Boar", level = 5, health = 10, max = 100, pct = 10 })
check(other.hpText:IsShown() and other.hpText._args.SetFormattedText[2] == 10, "a new plate has no health text")
removePlate("nameplate2")
check(not other.hpText:IsShown(), "a released plate keeps its text up")
"""),

    ("health text of a secret value goes to SetFormattedText untouched and is never compared", "true", r"""
enter()
set("plates.hpText", "percent")
local root = plate("nameplate1", { name = "Boss", level = -1, secret = true })
local a = root.hpText._args.SetFormattedText
check(root.hpText:IsShown() and a and a[1] == "%.0f%%" and rawequal(a[2], SECRET), "secret percent")
set("plates.hpText", "number")
a = root.hpText._args.SetFormattedText
check(a[1] == "%s / %s" and a[2] == "A(secret)" and a[3] == "A(secret)", "secret number")
set("plates.hpText", "both")
a = root.hpText._args.SetFormattedText
check(a[1] == "%s  %.0f%%" and a[2] == "A(secret)" and rawequal(a[3], SECRET), "secret both")
fire("UNIT_HEALTH", "nameplate1"); fire("UNIT_MAXHEALTH", "nameplate1")
-- a refused read leaves a blank, never an error
U.nameplate1.pctThrows = true
fire("UNIT_HEALTH", "nameplate1")
check(root.hpText._args.SetText and root.hpText._args.SetText[1] == "", "a failing percent read did not blank the text")
"""),

    ("health text without ScaleTo100 divides plain values only", "true", r"""
CurveConstants = nil
enter()
set("plates.hpText", "percent")
local root = plate("nameplate1", { name = "Wolf", level = 5, health = 1984, max = 3100, pct = 64 })
local a = root.hpText._args.SetFormattedText
check(a and a[1] == "%.0f%%" and math.abs(a[2] - 64) < 0.01, "plain percent without the curve")
check(#__pctCalls == 0, "UnitHealthPercent was called without the curve")
local boss = plate("nameplate2", { name = "Boss", level = -1, secret = true })
check(boss.hpText._args.SetText and boss.hpText._args.SetText[1] == "", "a secret value without the curve must blank, not divide")
"""),

    ("quest marker, raid marker and auras row switch off and on live", "true", r"""
local log = { { questID = 11 } }
C_QuestLog = {
    GetNumQuestLogEntries = function() return #log end,
    GetInfo = function(i) return { questID = log[i].questID } end,
    IsUnitOnQuest = function() return true end,
}
enter()
local root = plate("nameplate1", { name = "Quest mob", level = 5, health = 100, max = 100, pct = 100, mark = 8 })
check(root.questIcon:IsShown(), "no quest marker at the default")
check(root.raidMarker:IsShown(), "no raid marker at the default")
check(root.auraContainer and root.auraContainer._enabled == true, "no aura row at the default")
set("plates.quest", false)
check(not root.questIcon:IsShown(), "the quest marker stayed")
fire("QUEST_LOG_UPDATE"); drain()
check(not root.questIcon:IsShown(), "a quest refresh brought it back")
set("plates.raidMark", false)
check(not root.raidMarker:IsShown(), "the raid marker stayed")
fire("RAID_TARGET_UPDATE")
check(not root.raidMarker:IsShown(), "a marker event brought it back")
local c = root.auraContainer
set("plates.auras", false)
check(root.auraContainer == nil and c._enabled == false and not c._shown, "the aura row stayed on the plate")
local other = plate("nameplate2", { name = "Quest mob", level = 5, health = 100, max = 100, pct = 100, mark = 8 })
check(not other.questIcon:IsShown() and not other.raidMarker:IsShown() and other.auraContainer == nil, "a plate added with the parts off shows them")
set("plates.quest", true); set("plates.raidMark", true); set("plates.auras", true)
check(root.questIcon:IsShown() and other.questIcon:IsShown(), "the quest marker did not come back")
check(root.raidMarker:IsShown() and other.raidMarker:IsShown(), "the raid marker did not come back")
check(root.auraContainer and root.auraContainer._unit == "nameplate1" and root.auraContainer._enabled == true, "the aura row did not come back")
check(other.auraContainer and other.auraContainer._unit == "nameplate2", "the aura row did not come back on the other plate")
"""),

    ("the fallback aura row hides with the switch", "false", r"""
enter()
local root = plate("nameplate1")
check(root.auraIcons and #root.auraIcons == 5, "no fallback row")
set("plates.auras", false)
for _, icon in ipairs(root.auraIcons) do check(not icon:IsShown(), "a fallback icon stayed") end
__slotReads = 0
fire("UNIT_AURA", "nameplate1")
check(__slotReads == 0, "the fallback row scanned auras while off")
"""),

    ("friendly plates: same as enemy, smaller, off", "true", r"""
enter()
local enemy = plate("nameplate1", { name = "Wolf", level = 5, health = 100, max = 100, pct = 100 })
local friend, fplate = plate("nameplate2", { name = "Moolah", level = 5, health = 100, max = 100, pct = 100, hostile = false, friend = true, reaction = 5 })
check((enemy._args.SetScale and enemy._args.SetScale[1] or 1) == 1 and (friend._args.SetScale and friend._args.SetScale[1] or 1) == 1, "scaled at the default")
set("plates.friendly", "smaller")
check(friend._args.SetScale[1] == 0.8, "friendly plate not 80 percent: " .. tostring(friend._args.SetScale and friend._args.SetScale[1]))
check((enemy._args.SetScale and enemy._args.SetScale[1] or 1) == 1, "an enemy plate was scaled")
local late = plate("nameplate3", { name = "Guard", level = 5, health = 100, max = 100, pct = 100, hostile = false, friend = true, reaction = 5 })
check(late._args.SetScale[1] == 0.8, "a friendly plate added later is not smaller")
set("plates.friendly", "off")
check(FS.framesByUnit.nameplate2 == nil and FS.framesByUnit.nameplate3 == nil, "friendly plates are still built")
check(FS.framesByUnit.nameplate1 == enemy and enemy:IsShown(), "the enemy plate went with them")
check(fplate.UnitFrame._shown == false, "the game's own plate came back for a friendly unit")
local newer = plate("nameplate4", { name = "Guard", level = 5, health = 100, max = 100, pct = 100, hostile = false, friend = true, reaction = 5 })
check(newer == nil, "a friendly plate was built while off")
set("plates.friendly", "same")
check(FS.framesByUnit.nameplate2 and FS.framesByUnit.nameplate3 and FS.framesByUnit.nameplate4, "friendly plates did not come back")
check((FS.framesByUnit.nameplate2._args.SetScale and FS.framesByUnit.nameplate2._args.SetScale[1] or 1) == 1, "still small")
-- a unit that turns hostile (a duel, a flag change) gets a plate even while friendly plates are off
set("plates.friendly", "off")
check(FS.framesByUnit.nameplate2 == nil, "setup")
U.nameplate2.hostile, U.nameplate2.friend, U.nameplate2.reaction = true, false, 2
fire("UNIT_FACTION", "nameplate2")
check(FS.framesByUnit.nameplate2, "a unit that turned hostile has no plate")
U.nameplate2.hostile, U.nameplate2.friend, U.nameplate2.reaction = false, true, 5
fire("UNIT_FLAGS", "nameplate2")
check(FS.framesByUnit.nameplate2 == nil, "a unit that turned friendly kept its plate")
-- with the plates switched off nothing here builds anything
set("nameplates.enabled", false)
set("plates.friendly", "same")
check(next(FS.framesByUnit) == nil, "a friendly change built plates while the module is off")
"""),

    ("a friendly plate with a secret answer is treated as an enemy plate", "true", r"""
enter()
set("plates.friendly", "off")
UnitCanAttack = function() return SECRET end
local root = plate("nameplate1", { name = "Unknown", level = 5, health = 100, max = 100, pct = 100, hostile = false, friend = true })
check(root, "a plate whose attackable answer is secret was dropped")
"""),

    ("color provider: called, nil keeps the default, re-applied on threat events, a failing one is swallowed", "true", r"""
enter()
local HOT, COOL = { 1, 0, 0, 1 }, { 0, 1, 1, 1 }
local root = plate("nameplate1")
local default = root.fillColor
check(default == FS.Theme.COLOR_HEALTH, "the default fill is not the reaction colour")
check(type(FS.Nameplates.SetColorProvider) == "function" and type(FS.Nameplates.SetTextProvider) == "function", "no provider setters")
local calls, answer = 0, HOT
FS.Nameplates.SetColorProvider(function(unit) calls = calls + 1; check(unit == "nameplate1" or unit == "nameplate2", "wrong unit " .. tostring(unit)); return answer end)
check(root.fillColor == HOT, "the provider colour was not applied on the call")
answer = nil
fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
check(root.fillColor == default, "a nil answer did not keep the default")
answer = COOL
fire("UNIT_THREAT_LIST_UPDATE", "nameplate1")
check(root.fillColor == COOL, "a threat list event did not re-apply the provider")
local before = calls
fire("UNIT_HEALTH", "nameplate1")
check(calls >= before, "health events may ask again")
-- a plate added later asks too
answer = HOT
local other = plate("nameplate2")
check(other.fillColor == HOT, "a new plate did not take the provider colour")
-- tapped units keep the grey of "no credit for you"
U.nameplate2.tapped = true
fire("UNIT_FLAGS", "nameplate2")
check(other.fillColor ~= HOT and other.fillColor[1] == 0.42, "a tapped unit took the provider colour")
-- garbage answers keep the default: a string, a secret, a short table, a table of words
for _, bad in ipairs({ "red", SECRET, { 1, 2 }, { "a", "b", "c" }, false }) do
    answer = bad
    fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
    check(root.fillColor == default, "a bad answer was used: " .. tostring(bad))
end
-- an error is swallowed, logged once, and the default stays
FS.Nameplates.SetColorProvider(function() error("boom") end)
check(root.fillColor == default, "a failing provider changed the colour")
fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1"); fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
check(degraded("plate_color_provider") == 1, "the failing provider was logged " .. degraded("plate_color_provider") .. " times")
-- no provider: the default again
FS.Nameplates.SetColorProvider(nil)
check(root.fillColor == default and other.fillColor[1] == 0.42, "removing the provider did not restore the default")
"""),

    ("text provider: shown in the threat text field, nil hides, re-applied on threat events, a failing one is swallowed", "true", r"""
enter()
local root = plate("nameplate1")
check(root.threatText and not root.threatText:IsShown(), "the threat text shows with no provider")
local text, shade = "tank 142%", { 1, 0.2, 0.2, 1 }
local calls = 0
FS.Nameplates.SetTextProvider(function(unit) calls = calls + 1; return text, shade end)
check(root.threatText:IsShown() and root.threatText._args.SetText[1] == "tank 142%", "the text was not applied on the call")
local c = root.threatText._args.SetTextColor
check(c and c[1] == 1 and c[2] == 0.2, "the colour of the text was not applied")
text = "lost 80%"
fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
check(root.threatText._args.SetText[1] == "lost 80%", "a threat event did not refresh the text")
text = nil
fire("UNIT_THREAT_LIST_UPDATE", "nameplate1")
check(not root.threatText:IsShown(), "a nil answer left the text up")
text = "back"
local other = plate("nameplate2")
check(other.threatText:IsShown() and other.threatText._args.SetText[1] == "back", "a new plate has no threat text")
removePlate("nameplate2")
check(not other.threatText:IsShown(), "a released plate keeps its threat text")
FS.Nameplates.SetTextProvider(function() error("boom") end)
check(not root.threatText:IsShown(), "a failing provider left text up")
fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1"); fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
check(degraded("plate_text_provider") == 1, "the failing provider was logged " .. degraded("plate_text_provider") .. " times")
FS.Nameplates.SetTextProvider(function() return 12 end)
check(not root.threatText:IsShown(), "a number is not text")
FS.Nameplates.SetTextProvider(function() return SECRET end)
check(not root.threatText:IsShown(), "a secret number is not text")
FS.Nameplates.SetTextProvider(nil)
check(not root.threatText:IsShown(), "removing the provider left the text up")
"""),

    ("the threat events still refresh the fill and the name with no provider set", "true", r"""
enter()
local root = plate("nameplate1")
local before = root.fillColor
UnitThreatSituation = function() return 3 end
fire("UNIT_THREAT_SITUATION_UPDATE", "nameplate1")
check(root.fillColor ~= before, "the engagement colour did not follow the threat event")
"""),
]


def run_case(name: str, template: str, body: str, source: str, golden: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(AURAS.MOCK)
    lua.globals().__SRC = source
    lua.execute(f"__template = {template}")
    lua.globals().GOLDEN = golden
    lua.execute(f"NUMBERS = {NUMBER_ROWS}; BOOLS = {BOOL_ROWS}; CHOICES = {CHOICE_ROWS}")
    try:
        lua.execute(PRE)
        lua.execute(body)
    except LuaError as err:
        return str(err)
    return None


def export_module(source: str) -> str:
    """The real file's settings, geometry and palette as Lua source, for the page tests."""
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(AURAS.MOCK)
    lua.globals().__SRC = source
    lua.execute("__template = true")
    lua.execute(PRE)
    return lua.execute("boot() return dumpModule()")


# ---- python level checks ---------------------------------------------------------------------------------------------

def check_file_scope_locals_do_not_grow() -> list[str]:
    count = PARSE_GATE.count_file_scope_locals(SOURCE.read_text(encoding="utf-8"))
    print(f"      Nameplates.lua file scope locals: {count} (limit 190, before the settings {LOCALS_BEFORE})")
    if count > LOCALS_BEFORE:
        return [f"Nameplates.lua has {count} file scope locals, it had {LOCALS_BEFORE}: fold new state into the Plates table"]
    return []


def check_combo_pips_follow_the_cast_bar_height() -> list[str]:
    """The pips sit below the slot the cast bar keeps, so a taller or hidden cast bar moves them with it, live."""
    body = r"""
local a = Plate("nameplate1")
W.target = "nameplate1"
Fire("PLAYER_TARGET_CHANGED")
local host
for _, f in ipairs(FRAMES()) do if f.parent == a and f.kind == "Frame" and f.strata == "HIGH" then host = f end end
check(host ~= nil and host.shown, "the pips show")
local function drop() local pt = host.points[1] return pt and pt[5] end
check(drop() == -11, "the default slot is the old one, got " .. tostring(drop()))
FS.Config.Set("plates.castH", 16)
check(drop() == -21, "a 16 high cast bar pushes the pips down, got " .. tostring(drop()))
FS.Config.Set("plates.castH", 0)
check(drop() == -5, "a hidden cast bar leaves only the gaps, got " .. tostring(drop()))
FS.Config.Set("plates.castH", 6)
check(drop() == -11, "back to the default slot, got " .. tostring(drop()))
FS.Config.Set("plates.castH", 99)
check(drop() == -21, "a value out of range is held to the limit, got " .. tostring(drop()))
FS.Config.Set("plates.castH", "tall")
check(drop() == -11, "a word reads as the default, got " .. tostring(drop()))
"""
    return COMBO_HARNESS.run("ROGUE", "FS.Config.RegisterDefault('plates.castH', 6)\n" + body)


def check_no_dashes() -> list[str]:
    problems = []
    for path in (SOURCE, PAGE, COMBO, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        for mark, label in ((chr(0x2014), "em dash"), (chr(0x2013), "en dash")):
            if mark in text:
                problems.append(f"{path.name} has an {label}")
    return problems


def check_provider_names_stay_neutral() -> list[str]:
    """Client visible text (labels, tips, log lines) keeps to the neutral wording of stage_runtime.py."""
    problems = []
    terms = re.compile(r"(?<![a-z])bots?(?![a-z])|harness|pixel|bridge|beacon|python|automat|probe|recon", re.I)
    for path in (PAGE,):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', line):
                if terms.search(literal):
                    problems.append(f"{path.name}:{number}: {literal[:60]}")
    return problems


# ---- the page tests: the real Nameplates.lua data under the config window mock ------------------------------------

def proto_rows() -> dict:
    """The plates page of proto-pages.js: {tab: {"label": .., "sections": [(title, [row, ..])]}}."""
    src = PROTO.read_text(encoding="utf-8")
    start = src.index(" {key:'plates',label:'Nameplates',tabs:[")
    end = src.index("\n {key:'gunsight'", start)
    block = src[start:end]
    tabs = {}
    for tab in re.split(r"\n  \{key:'", block)[1:]:
        key = tab.split("'", 1)[0]
        label = re.search(r"label:'([^']*)'", tab).group(1)
        sections = []
        for sec in re.split(r"\{t:'", tab)[1:]:
            title = sec.split("'", 1)[0]
            rows = []
            for m in re.finditer(r"\{ty:'(sl|sw|seg)',k:'([^']+)',l:'([^']+)',d:('[^']*'|[0-9.]+|true|false)([^}]*)\}", sec):
                ty, k, l, d, rest = m.groups()
                row = {"ty": ty, "k": k, "l": l, "d": d.strip("'") if d.startswith("'") else (d == "true" if d in ("true", "false") else float(d))}
                for field in ("min", "max", "st"):
                    f = re.search(rf"{field}:(\d+)", rest)
                    if f:
                        row[field] = int(f.group(1))
                u = re.search(r"u:'(\w+)'", rest)
                if u:
                    row["u"] = u.group(1)
                t = re.search(r"tip:'((?:[^'\\]|\\.)*)'", rest)
                if t:
                    row["tip"] = t.group(1)
                o = re.search(r"o:(\[[^\]]*\]|FMT)", rest)
                if o:
                    row["o"] = ["None", "Percent", "Number", "Num + %"] if o.group(1) == "FMT" else re.findall(r"'([^']*)'", o.group(1))
                rows.append(row)
            sections.append((title, rows, "preview:1" in sec.split("rows:", 1)[0]))
        tabs[key] = {"label": label, "sections": sections}
    return tabs


# A stored value of the prototype's option text.
STORED = {"None": "none", "Percent": "percent", "Number": "number", "Num + %": "both",
          "Same as enemy": "same", "Smaller": "smaller", "Off": "off"}

PAGE_CHECKS = r"""
local function np()
    FS.Nameplates = assert(load("return " .. __NP))()
    for _, def in pairs(FS.Nameplates.SETTINGS) do FS.Config.RegisterDefault(def.key, def.default) end
    FS.Config.RegisterDefault(FS.Nameplates.KEY, true)
    FS.Config.RegisterDefault(FS.Nameplates.TARGET_MARK_SETTING.key, FS.Nameplates.TARGET_MARK_SETTING.default)
end
local function withCombo()
    FS.NameplateCombo = { SETTING = { key = "nameplates.comboPips", default = true, label = "Combo points on the target", tip = "Combo tip." } }
    FS.Config.RegisterDefault("nameplates.comboPips", true)
end
local function plates() np(); withCombo() end
local TABS = { "size", "text", "parts", "friendly" }
local function openAll(W)
    for _, tab in ipairs(TABS) do W.Open("plates", tab) end
end
local function bandOf(tab)
    for _, o in ipairs(ALL) do if o.fsBand and o.fsPlatesTab == tab then return o end end
end
local function inside(root, o)
    while o do
        if o == root then return true end
        o = o.parent
    end
    return false
end
-- every region of one tab's band tagged with a part name, optionally of one plate
local function parts(tab, name, plate)
    local band, out = assert(bandOf(tab), "no preview band on the " .. tab .. " tab"), {}
    for _, o in ipairs(ALL) do
        if o.fsPart == name and inside(band, o) and (plate == nil or o.fsPlate == plate) then out[#out + 1] = o end
    end
    return out
end
local function one(tab, name, plate)
    local list = parts(tab, name, plate)
    if #list ~= 1 then error("expected one '" .. name .. "' part on plate " .. tostring(plate) .. ", found " .. #list, 2) end
    return list[1]
end
local function entry(key) return assert(FS.ConfigWindow.RowByKey(key, "plates"), "no row " .. key) end

function T.the_plates_page_has_every_prototype_row_with_its_label_key_range_and_default()
    local W = boot({ preWindow = plates })
    openAll(W)
    local seen = 0
    for _, tab in ipairs(__PROTO) do
        for _, sec in ipairs(tab.sections) do
            for _, want in ipairs(sec.rows) do
                seen = seen + 1
                W.Open("plates", tab.key)
                local e = W.RowByKey(want.k, "plates")
                if not e then error("no row " .. want.k .. " (" .. want.l .. ")") end
                eq(e.label, want.l, want.k .. " label")
                eq(e.tab, tab.key, want.k .. " tab")
                eq(e.section, sec.title, want.k .. " section")
                if want.ty == "sl" then
                    eq(e.min, want.min, want.k .. " min"); eq(e.max, want.max, want.k .. " max")
                    eq(FS.Config.Get(want.k), want.d, want.k .. " default")
                    eq(e.row.fsUnit:GetText(), want.u, want.k .. " unit")
                    local step = nil
                    for _, def in pairs(FS.Nameplates.SETTINGS) do if def.key == want.k then step = def.step end end
                    eq(step, want.st, want.k .. " step")
                elseif want.ty == "sw" then
                    eq(FS.Config.Get(want.k), want.d, want.k .. " default")
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
    yes(seen >= 12, "only " .. seen .. " prototype rows were checked")
end

function T.the_plates_page_keeps_the_module_switch_and_the_target_mark_switch_on_the_parts_tab()
    local W = boot({ preWindow = plates })
    W.Open("plates", "parts")
    local m, t = entry("nameplates.enabled"), entry("nameplates.targetMark")
    eq(m.label, "STUwave nameplates"); eq(m.section, "What shows"); eq(m.tab, "parts")
    eq(t.label, "Show target mark"); eq(t.tab, "parts"); eq(t.section, "What shows")
    yes(t.tip and t.tip:find("target", 1, true), "the target mark switch is explained by a tip")
    eq(FS.Config.Get("nameplates.targetMark"), false, "off by default")
    yes(entry("nameplates.comboPips"), "the combo points switch is still there")
    press("Show target mark")
    eq(FS.Config.Get("nameplates.targetMark"), true)
end

function T.the_plates_page_leaves_out_what_the_modules_do_not_offer()
    local W = boot({ preWindow = function() np(); end })
    W.Open("plates", "parts")
    no(W.RowByKey("nameplates.comboPips", "plates"), "no combo module, no combo row")
    yes(W.RowByKey("plates.quest", "plates"), "the plate rows stay")
    W = boot({ preWindow = function() FS.Nameplates = {} end })
    openAll(W)
    eq(#(W.Rows()) > 0 and (function() local n = 0 for _, e in ipairs(W.Rows()) do if e.page == "plates" then n = n + 1 end end return n end)() or 0, 0, "a module with nothing to offer has no rows")
    for _, tab in ipairs(TABS) do no(bandOf(tab), "no preview without the module") end
end

function T.every_tab_of_the_plates_page_has_a_preview_band_with_four_plates()
    local W = boot({ preWindow = plates })
    openAll(W)
    for _, tab in ipairs(TABS) do
        local band = bandOf(tab)
        yes(band, "no band on " .. tab)
        eq(#parts(tab, "plate"), 4, tab .. " plates")
        local title
        for _, o in ipairs(ALL) do if o.kind == "FontString" and inside(band, o) and o:GetText() == "PREVIEW" then title = o end end
        yes(title, tab .. " has no PREVIEW title")
        local tip
        for _, o in ipairs(ALL) do if o.fsTip and inside(band, o) then tip = o.fsTip end end
        yes(tip and tip:find("settings", 1, true), tab .. " preview is not explained by a tip")
    end
    yes(bandOf("size"):IsShown() or true)
end

function T.the_preview_is_drawn_from_the_plate_module_constants()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    local g = FS.Nameplates.GEOMETRY
    for plate = 1, 3 do
        local bar = one("size", "bar", plate)
        eq(bar.w, 130); eq(bar.h, 14)
        eq(one("size", "box", plate).w, 130 + 2 * g.PAD, "the chrome is the bar plus the padding")
    end
    eq(one("size", "power", 2).h, 5, "the target plate's power bar")
    eq(one("size", "cast", 2).h, 6, "the target plate's cast bar")
    eq(one("size", "name", 2):GetText():find("Kolkar Packhound", 1, true) ~= nil, true)
    eq(one("size", "quest", 1):GetText(), "!", "the quest marker is the module's own glyph")
    yes(one("size", "quest", 1):IsShown(), "the neutral plate carries the quest marker")
    yes(one("size", "mark", 3):IsShown(), "the third plate carries the raid marker")
    eq(#parts("size", "aura", 2), 3, "three aura icons on the target plate")
    eq(parts("size", "aura", 2)[1].w, g.AURA_SIZE)
    no(one("size", "tmark", 2):IsShown(), "the target mark is off by default")
    yes(one("size", "combo", 2):IsShown(), "the combo pips show for a class that has them")
    yes(one("size", "plate", 4):IsShown(), "the friendly plate shows")
    eq(one("size", "plate", 4).fsScale, 1)
end

function T.the_preview_follows_the_size_settings()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    FS.Config.Set("plates.w", 200)
    for plate = 1, 4 do eq(one("size", "bar", plate).w, 200, "width of plate " .. plate) end
    FS.Config.Set("plates.hpH", 24)
    for plate = 1, 4 do eq(one("size", "bar", plate).h, 24, "health height of plate " .. plate) end
    FS.Config.Set("plates.mpH", 9)
    eq(one("size", "power", 2).h, 9)
    FS.Config.Set("plates.mpH", 0)
    no(one("size", "power", 2):IsShown(), "power bar 0 hides it")
    FS.Config.Set("plates.castH", 11)
    eq(one("size", "cast", 2).h, 11)
    FS.Config.Set("plates.castH", 0)
    no(one("size", "cast", 2):IsShown(), "cast bar 0 hides it")
    local band = bandOf("size")
    for plate = 1, 4 do
        local pf = one("size", "plate", plate)
        yes(pf.fsScale > 0 and pf.fsScale <= 1, "plate " .. plate .. " scale " .. tostring(pf.fsScale))
    end
end

function T.the_preview_shrinks_to_fit_the_stage_at_the_largest_sizes()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    local one1 = one("size", "plate", 1).fsScale
    eq(one1, 1, "the default settings fit without scaling")
    FS.Config.Set("plates.w", 240); FS.Config.Set("plates.hpH", 30); FS.Config.Set("plates.mpH", 12)
    FS.Config.Set("plates.castH", 16); FS.Config.Set("plates.nameSize", 16)
    local s = one("size", "plate", 1).fsScale
    yes(s < 1 and s > 0.3, "the largest plates scale to " .. tostring(s))
    for plate = 2, 4 do eq(one("size", "plate", plate).fsScale, s * (plate == 4 and 1 or 1), "one scale for the row, plate " .. plate) end
end

function T.the_preview_follows_the_text_settings()
    local W = boot({ preWindow = plates })
    W.Open("plates", "text")
    no(one("text", "hptext", 2):IsShown(), "no health text by default")
    FS.Config.Set("plates.hpText", "percent")
    eq(one("text", "hptext", 2):GetText(), "64%"); yes(one("text", "hptext", 2):IsShown())
    FS.Config.Set("plates.hpText", "number")
    eq(one("text", "hptext", 2):GetText(), "1984 / 3100")
    FS.Config.Set("plates.hpText", "both")
    eq(one("text", "hptext", 2):GetText(), "1984  64%")
    FS.Config.Set("plates.nameSize", 15)
    eq(one("text", "name", 2).fontSize, 15, "name size")
    yes(one("text", "name", 2):GetText():find("22", 1, true), "the level is in the name")
    FS.Config.Set("plates.level", false)
    no(one("text", "name", 2):GetText():find("22", 1, true), "the level is gone")
    no(one("text", "name", 2):GetText():find("|c", 1, true), "no colour code is left behind")
end

function T.the_preview_follows_the_parts_settings()
    local W = boot({ preWindow = plates })
    W.Open("plates", "parts")
    yes(one("parts", "quest", 1):IsShown() and one("parts", "mark", 3):IsShown() and #parts("parts", "aura") > 0)
    FS.Config.Set("plates.quest", false)
    no(one("parts", "quest", 1):IsShown(), "quest marker off")
    FS.Config.Set("plates.raidMark", false)
    no(one("parts", "mark", 3):IsShown(), "raid marker off")
    FS.Config.Set("plates.auras", false)
    for _, a in ipairs(parts("parts", "aura")) do no(a:IsShown(), "an aura icon stayed") end
    FS.Config.Set("nameplates.comboPips", false)
    no(one("parts", "combo", 2):IsShown(), "combo pips off")
    FS.Config.Set("nameplates.targetMark", true)
    yes(one("parts", "tmark", 2):IsShown(), "the target mark shows when it is on")
    FS.Config.Set("nameplates.targetMark", false)
    no(one("parts", "tmark", 2):IsShown())
end

function T.the_preview_follows_the_friendly_setting()
    local W = boot({ preWindow = plates })
    W.Open("plates", "friendly")
    eq(one("friendly", "plate", 4).fsScale, 1); yes(one("friendly", "plate", 4):IsShown())
    FS.Config.Set("plates.friendly", "smaller")
    eq(one("friendly", "plate", 4).fsScale, 0.8, "smaller is 80 percent")
    eq(one("friendly", "bar", 4).w, 130, "the part sizes stay, the plate scales")
    yes(one("friendly", "plate", 4):IsShown())
    FS.Config.Set("plates.friendly", "off")
    no(one("friendly", "plate", 4):IsShown(), "off hides the friendly plate")
    yes(one("friendly", "plate", 2):IsShown(), "the enemy plates stay")
end

function T.a_hidden_tab_catches_up_when_it_is_shown()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    W.Open("plates", "parts")
    FS.Config.Set("plates.w", 180)
    W.Open("plates", "size")
    eq(one("size", "bar", 2).w, 180, "the size tab did not catch up")
    eq(one("parts", "bar", 2).w, 180)
end

function T.hovering_a_row_shows_the_part_and_pulses_it_then_puts_everything_back()
    local W = boot({ preWindow = plates })
    W.Open("plates", "parts")
    FS.Config.Set("plates.quest", false)
    FS.Config.Set("plates.auras", false)
    no(one("parts", "quest", 1):IsShown())
    W.SetHover(entry("plates.quest"))
    yes(one("parts", "quest", 1):IsShown(), "the hovered part shows even while it is off")
    yes(one("parts", "quest", 1).fsPulse, "the hovered part pulses")
    eq(bandOf("parts").fsPeek, "plates.quest")
    no(parts("parts", "aura", 2)[1]:IsShown(), "the others stay as they are")
    eq(FS.Config.Get("plates.quest"), false, "hovering never writes a setting")
    W.SetHover(entry("plates.auras"))
    no(one("parts", "quest", 1):IsShown(), "the previous part went back")
    yes(#parts("parts", "aura") > 0 and parts("parts", "aura")[1]:IsShown() and parts("parts", "aura")[1].fsPulse, "the aura row shows and pulses")
    W.SetHover(nil)
    for _, a in ipairs(parts("parts", "aura")) do no(a:IsShown(), "an aura icon stayed after the hover") end
    no(bandOf("parts").fsPeek, "the peek ended")
    -- the pulse moves the alpha only while it runs
    W.SetHover(entry("plates.raidMark"))
    local band = bandOf("parts")
    yes(band.scripts.OnUpdate, "the pulse runs while a part is hovered")
    W.SetHover(nil)
    no(band.scripts.OnUpdate, "the pulse stops with the hover")
end

function T.hovering_the_size_rows_pulses_the_part_they_change()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    W.SetHover(entry("plates.castH"))
    yes(one("size", "cast", 2).fsPulse, "the cast bar pulses for its row")
    W.SetHover(entry("plates.mpH"))
    yes(one("size", "power", 2).fsPulse and not one("size", "cast", 2).fsPulse, "the power bar pulses for its row")
    W.SetHover(entry("plates.w"))
    no(one("size", "power", 2).fsPulse, "the width has nothing to pulse")
    W.SetHover(nil)
    W.Open("plates", "text")
    W.SetHover(entry("plates.hpText"))
    yes(one("text", "name", 2) ~= nil)
    W.SetHover(entry("plates.nameSize"))
    yes(one("text", "name", 2).fsPulse, "the name pulses for its size row")
    W.SetHover(nil)
    W.Open("plates", "friendly")
    W.SetHover(entry("plates.friendly"))
    yes(one("friendly", "plate", 4).fsPulse, "the friendly plate pulses")
    W.SetHover(nil)
end

function T.hovering_the_health_text_row_shows_a_sample_while_the_text_is_none()
    local W = boot({ preWindow = plates })
    W.Open("plates", "text")
    no(one("text", "hptext", 2):IsShown())
    W.SetHover(entry("plates.hpText"))
    yes(one("text", "hptext", 2):IsShown() and one("text", "hptext", 2).fsPulse, "the health text shows a sample for its row")
    W.SetHover(nil)
    no(one("text", "hptext", 2):IsShown())
end

function T.the_page_uses_the_modules_ranges_and_changing_a_slider_writes_the_setting()
    local W = boot({ preWindow = plates })
    W.Open("plates", "size")
    local e = entry("plates.w")
    local r = e.row
    yes(r.control, "a slider control")
    eq(r.fsReadout:GetText(), "130 px")
    FS.Config.Set("plates.w", 150)
    W.RefreshAll()
    eq(r.fsReadout:GetText(), "150 px")
    W.Open("plates", "friendly")
    click("Smaller", FS.ConfigWindow and _G.ForeverSTUwaveConfig)
    eq(FS.Config.Get("plates.friendly"), "smaller")
    click("Off", _G.ForeverSTUwaveConfig)
    eq(FS.Config.Get("plates.friendly"), "off")
end
"""


def run_page_checks(np_source: str, rows: dict) -> int:
    base = AURAS_BASE
    tabs = []
    for key, tab in rows.items():
        sections = []
        for title, items, _preview in tab["sections"]:
            wanted = []
            for item in items:
                item = dict(item)
                if item["ty"] == "seg":
                    item["stored"] = STORED[item["d"]]
                wanted.append(item)
            sections.append({"title": title, "rows": wanted})
        tabs.append({"key": key, "label": tab["label"], "sections": sections})
    names = sorted(re.findall(r"^function T\.([a-z0-9_]+)\(", PAGE_CHECKS, re.M))
    original = base.CHECKS
    base.CHECKS = original.replace("__checks = T", PAGE_CHECKS + "\n__checks = T")
    failed = 0
    try:
        for name in names:
            try:
                lua = base.boot()
                lua.globals().__NP = np_source
                lua.globals().__PROTO = base.to_lua(lua, tabs)
                lua.eval("__checks")[name]()
                leaked = list(lua.eval("__errors").values())
                if leaked:
                    raise LuaError(f"errors were forwarded to the error handler: {leaked}")
                print(f"ok    {name}")
            except LuaError as err:
                failed += 1
                print(f"FAIL  {name}\n      {' '.join(str(err).splitlines()[:3])[:600]}")
    finally:
        base.CHECKS = original
    return failed


AURAS_BASE = load("configwindow_harness", "configwindow-harness.py")


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    golden = GOLDEN
    failures = 0
    total = 0
    for name, template, body in CASES:
        total += 1
        error = run_case(name, template, body, source, golden)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    for label, problems in (
        ("nameplates_file_scope_locals_do_not_grow", check_file_scope_locals_do_not_grow()),
        ("no_em_or_en_dash_in_the_plate_files", check_no_dashes()),
        ("page_labels_and_tips_use_neutral_words", check_provider_names_stay_neutral()),
        ("combo_pips_follow_the_cast_bar_height", check_combo_pips_follow_the_cast_bar_height()),
    ):
        total += 1
        if problems:
            failures += 1
            print(f"FAIL  {label}\n      " + "\n      ".join(problems))
        else:
            print(f"ok    {label}")
    rows = proto_rows()
    if sorted(rows) != ["friendly", "parts", "size", "text"]:
        print(f"FAIL  the prototype's plates page has tabs {sorted(rows)}")
        return 1
    try:
        np_source = export_module(source)
    except LuaError as err:
        print(f"FAIL  the module data could not be exported for the page tests\n      {err}")
        return 1
    page_names = len(re.findall(r"^function T\.", PAGE_CHECKS, re.M))
    total += page_names
    failures += run_page_checks(np_source, rows)
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
