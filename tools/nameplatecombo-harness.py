#!/usr/bin/env python3
"""Runs the real Modules/Nameplates/NameplateCombo.lua headless against a mock WoW API.

Pins the combo pips on the target's nameplate:

  * a Rogue gets five pips beside the target's STUwave plate, each a StatusBar from i - 1 to i plus a gold one from 4 to 5,
    fed the raw UnitPower value (a secret goes straight to SetValue, Lua never compares it);
  * they follow the target to its plate, hide with no target, a friendly target, no plate, or the setting off;
  * a Druid sees them only while its power is energy (Cat Form);
  * any other class loads nothing.

The mock is NOT the real client.

    python3 tools/nameplatecombo-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "forever-stuwave" / "Modules" / "Nameplates" / "NameplateCombo.lua"

MOCK = r"""
Enum = { PowerType = { ComboPoints = 4, Energy = 3, Mana = 0 } }
C_NamePlate = {}
PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }
SECRET = setmetatable({}, { __index = function() error("indexed a secret") end,
    __lt = function() error("compared a secret") end, __le = function() error("compared a secret") end,
    __eq = function() error("compared a secret") end })
W = { class = "ROGUE", ptype = 3, power = 0, target = nil, hostile = true, dead = false, timers = {} }
function UnitClass() return "Rogue", W.class end
function UnitPowerType() return W.ptype end
function UnitPower(u, t) assert(u == "player" and t == 4) return W.power end
function UnitExists(u) return u == "target" and W.target ~= nil end
function UnitCanAttack() return W.hostile end
function UnitIsDead() return W.dead end
function UnitIsUnit(a, b) return b == "target" and W.target == a end
C_Timer = { After = function(_, fn) W.timers[#W.timers + 1] = fn end }
function Flush() local t = W.timers W.timers = {} for _, fn in ipairs(t) do fn() end end

local function Region()
    local r = { shown = true, points = {} }
    function r:SetAllPoints() end
    function r:SetColorTexture() end
    function r:SetPoint(...) self.points[#self.points + 1] = { ... } end
    function r:ClearAllPoints() self.points = {} end
    return r
end
local frames = {}
function CreateFrame(kind, _, parent)
    local f = Region()
    f.kind, f.parent, f.level, f.scripts, f.events = kind, parent, 1, {}, {}
    function f:SetFrameLevel(l) self.level = l end
    function f:GetFrameLevel() return self.level end
    function f:SetFrameStrata(s) self.strata = s end
    function f:SetIgnoreParentAlpha() end
    function f:Hide() self.shown = false end
    function f:Show() self.shown = true end
    function f:IsShown() return self.shown end
    function f:SetParent(p) self.parent = p end
    function f:SetSize(w, h) self.w, self.h = w, h end
    function f:GetEffectiveScale() return 1 end
    function f:SetScript(k, fn) self.scripts[k] = fn end
    function f:GetScript(k) return self.scripts[k] end
    function f:RegisterEvent(e) self.events[e] = true end
    function f:RegisterUnitEvent(e) self.events[e] = true end
    function f:CreateTexture() return Region() end
    function f:SetStatusBarTexture() end
    function f:SetStatusBarColor(r, g, b) self.color = { r, g, b } end
    function f:SetMinMaxValues(lo, hi) self.lo, self.hi = lo, hi end
    function f:SetValue(v) self.value = v end
    frames[#frames + 1] = f
    return f
end
UIParent = CreateFrame("Frame")

local store, subs = {}, {}
FS = {
    framesByUnit = {},
    IsSecret = function(v) return v == SECRET end,
    Config = {
        RegisterDefault = function(k, v) if store[k] == nil then store[k] = v end end,
        Get = function(k) return store[k] end,
        Set = function(k, v) store[k] = v for _, fn in ipairs(subs[k] or {}) do fn() end end,
        OnChange = function(k, fn) subs[k] = subs[k] or {} table.insert(subs[k], fn) end,
    },
}
function Fire(event, unit)
    for _, f in ipairs(frames) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, unit) end
    end
end
function Plate(unit)
    local root = CreateFrame("Frame", nil, UIParent)
    FS.framesByUnit[unit] = root
    return root
end
"""

CASES = r"""
local M = FS.NameplateCombo
check(M ~= nil, "a Rogue loads the module")

-- no target: nothing built or shown
Fire("PLAYER_ENTERING_WORLD")
check(true, "no target, no error")

local a = Plate("nameplate1")
local b = Plate("nameplate2")
W.target = "nameplate1"
Fire("PLAYER_TARGET_CHANGED")
local host
for _, f in ipairs(FRAMES()) do if f.parent == a and f.kind == "Frame" and f.strata == "HIGH" then host = f end end
check(host ~= nil and host.shown, "pips hang from the target's plate and show")

local fills, golds = {}, {}
for _, f in ipairs(FRAMES()) do
    if f.kind == "StatusBar" then
        if f.lo == 4 and f.hi == 5 and f.color[1] > 0.99 and f.color[2] > 0.8 then golds[#golds + 1] = f
        else fills[#fills + 1] = f end
    end
end
check(#fills == 5 and #golds == 5, "five pink and five gold bars: " .. #fills .. " " .. #golds)
for i, f in ipairs(fills) do check(f.lo == i - 1 and f.hi == i, "pip " .. i .. " runs " .. (i - 1) .. " to " .. i) end

W.power = 3
Fire("UNIT_POWER_UPDATE", "player")
check(fills[1].value == 3 and golds[5].value == 3, "a plain count goes to every bar")

W.power = SECRET
Fire("UNIT_POWER_FREQUENT", "player")
check(fills[2].value == SECRET and golds[1].value == SECRET, "a secret count goes to the bars untouched")
W.power = 2

W.target = "nameplate2"
Fire("PLAYER_TARGET_CHANGED")
check(host.parent == b and host.shown, "the pips follow the target to its plate")

W.hostile = false
Fire("PLAYER_TARGET_CHANGED")
check(not host.shown, "a friendly target hides them")
W.hostile = SECRET
Fire("PLAYER_TARGET_CHANGED")
check(not host.shown, "a secret attackable reads as not hostile")
W.hostile = true

FS.framesByUnit.nameplate2 = nil
Fire("NAME_PLATE_UNIT_REMOVED", "nameplate2")
Flush()
check(not host.shown, "the target's plate gone hides them")
FS.framesByUnit.nameplate2 = b
Fire("NAME_PLATE_UNIT_ADDED", "nameplate2")
check(not host.shown, "a new plate waits a frame for Nameplates.lua")
Flush()
check(host.shown and host.parent == b, "and then seats on it")

FS.Config.Set("nameplates.comboPips", false)
check(not host.shown, "the setting off hides them")
FS.Config.Set("nameplates.comboPips", true)
check(host.shown, "and on shows them again")

W.target = nil
Fire("PLAYER_TARGET_CHANGED")
check(not host.shown, "no target hides them")

"""

DRUID_CASE = r"""
local M = FS.NameplateCombo
check(M ~= nil, "a Druid loads the module")
local a = Plate("nameplate1")
W.target = "nameplate1"
W.ptype = 0
Fire("PLAYER_TARGET_CHANGED")
local host
for _, f in ipairs(FRAMES()) do if f.strata == "HIGH" then host = f end end
check(host == nil or not host.shown, "caster form shows nothing")
W.ptype = 3
Fire("UPDATE_SHAPESHIFT_FORM")
for _, f in ipairs(FRAMES()) do if f.strata == "HIGH" then host = f end end
check(host ~= nil and host.shown and host.parent == a, "cat form shows the pips")
W.ptype = 1
Fire("UNIT_DISPLAYPOWER", "player")
check(not host.shown, "bear form hides them")
"""

OTHER_CASE = r"""
check(FS.NameplateCombo == nil, "a Shaman loads nothing")
"""


def run(cls: str, body: str) -> list[str]:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK)
    lua.execute(f'W.class = "{cls}"')
    failures: list[str] = []
    lua.globals().check = lambda ok, msg: None if ok else failures.append(f"[{cls}] {msg}")
    lua.execute(MOCK_FRAMES)
    chunk = lua.eval("function(...) return loadstring(...) end")(SRC.read_text(encoding="utf-8"), "@NameplateCombo.lua")
    if chunk is None:
        return [f"[{cls}] the file does not parse"]
    lua.globals().CHUNK = chunk
    lua.execute('CHUNK("forever-stuwave", FS)')
    lua.execute(body)
    return failures


MOCK_FRAMES = r"""
local orig = CreateFrame
local all = {}
function CreateFrame(...) local f = orig(...) all[#all + 1] = f return f end
function FRAMES() return all end
function Fire(event, unit)
    for _, f in ipairs(all) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event, unit) end
    end
end
"""


def main() -> int:
    failures = run("ROGUE", CASES) + run("DRUID", DRUID_CASE) + run("SHAMAN", OTHER_CASE)
    for f in failures:
        print("FAIL", f)
    if failures:
        return 1
    print("nameplatecombo-harness: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
