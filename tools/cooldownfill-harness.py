#!/usr/bin/env python3
"""Runs the real FrameHelpers.lua, ActionBars.lua, StanceBar.lua and PetActionBar.lua headless
against the action bar mock (actionbars-harness.py) and pins the violet cooldown fill.

The approved look (look S3 of the cooldown fill mockup, GCD pick C): a real cooldown is a violet fill
over the key, the whole face when it starts, its bottom edge rising until it is gone at ready, with a
bright edge line and a soft glow on that edge; the global cooldown keeps the dark clock swipe.

What is pinned here:

  * the fill: a vertical StatusBar filling from the top, on the icon, one level over the swipe, the
    edge host one level over the fill, the keybind text over both; built once, never again on a re-seat;
  * the colour: Theme.COLOR_BORDER at 0.55 over a 0.60 black scrim composed into one flat colour
    (alpha 0.82), the edge violet mixed 0.55 toward white, two physical pixels;
  * the engine path: SetCooldownFill hands the duration object to StatusBar:SetTimerDuration in the
    REMAINING time direction, never reading a number; the action bar asks for the fill's object with
    the GCD left out (ignoreGCD) and gives the swipe the GCD marker's object alone;
  * the fallbacks: no SetTimerDuration, no direction enum or a throwing call keeps the old swipe of
    everything; a client with no usable StatusBar never builds (and never retries) a fill;
  * the plain path (stance and pet bars, legacy clients): a GCD-length cooldown is the swipe, a longer
    one the fill run down by its own OnUpdate, a secret value hides both and is never compared.

It is NOT a rendering test and NOT the real client: whether 16001 honours SetTimerDuration's remaining
time direction, SetReverseFill on a vertical bar, SetClipsChildren on the edge and the ignoreGCD
argument is an in-game check (docs/TESTING.md).

    python3 tools/cooldownfill-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


abh = _load("actionbars_harness", "actionbars-harness.py")


def _theme_border() -> str:
    src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    m = re.search(r"^Theme\.COLOR_BORDER\s*=\s*(\{[^}]*\})", src, re.M)
    if not m:
        sys.exit("Theme.COLOR_BORDER not found in Theme.lua")
    return m.group(1)


# A client with everything the fill needs: the StatusBar widget, the timer enums, the GCD marker's
# duration object and an action duration API that records the ignoreGCD argument.
FILL_CLIENT = r"""
__BORDER = """ + _theme_border() + r"""
__now = 100
function GetTime() return __now end
Enum = Enum or {}
Enum.StatusBarTimerDirection = { ElapsedTime = 0, RemainingTime = 1 }
Enum.StatusBarInterpolation = { Immediate = 0, ExponentialEaseOut = 1 }
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a } end
__timerCalls, __timerThrows = 0, false
local SB = {}
function SB:SetStatusBarTexture(t)
    if not self._sbTex then self._sbTex = self:CreateTexture(nil, "ARTWORK") end
    self._sbTex._path = t
end
function SB:GetStatusBarTexture() return self._sbTex end
function SB:SetStatusBarColor(r, g, b, a) self._sbColor = { r, g, b, a } end
function SB:SetOrientation(o) self._orient = o end
function SB:SetReverseFill(v) self._reverse = v end
function SB:SetMinMaxValues(a, b) self._min, self._max = a, b end
function SB:SetValue(v) self._value = v end
function SB:SetTimerDuration(obj, interp, dir)
    __timerCalls = __timerCalls + 1
    if __timerThrows then error("SetTimerDuration refused it") end
    self._timer = { obj = obj, interp = interp, dir = dir }
end
function __Region:SetClipsChildren(v) self._clips = v end
function __Region:SetGradient(orient, a, b) self._gradient = { orient, a, b } end
do
    local create = CreateFrame
    function CreateFrame(kind, ...)
        local f = create(kind, ...)
        if kind == "StatusBar" then for k, fn in pairs(SB) do f[k] = fn end end
        return f
    end
end
__gcdAsks = 0
C_Spell = C_Spell or {}
C_Spell.GetSpellCooldownDuration = function(id)
    if id == 61304 then __gcdAsks = __gcdAsks + 1; return { gcd = true } end
    return { spell = id }
end
C_ActionBar.GetActionCooldownDuration = function(slot, ignoreGCD)
    return { slot = slot, ignoreGCD = ignoreGCD }
end
"""

# Variants of FILL_CLIENT, by check name.
VARIANTS = {
    "a_client_without_the_timer_direction_keeps_the_swipe_of_everything":
        "Enum.StatusBarTimerDirection = nil",
    "a_client_without_set_timer_duration_keeps_the_swipe_of_everything":
        "local c = CreateFrame; function CreateFrame(k, ...) local f = c(k, ...); "
        "if k == 'StatusBar' then f.SetTimerDuration = nil end; return f end",
    "a_client_without_clipping_gets_the_fill_and_no_edge": "__Region.SetClipsChildren = nil",
    "a_client_without_set_reverse_fill_grows_from_the_bottom_with_the_edge_on_top":
        "local c = CreateFrame; function CreateFrame(k, ...) local f = c(k, ...); "
        "if k == 'StatusBar' then f.SetReverseFill = nil end; return f end",
}

# A client with no StatusBar at all: the plain action bar mock, no FILL_CLIENT.
BARE = ("a_client_with_no_status_bar_builds_no_fill_and_never_retries",)

CHECKS = r"""
local T = {}

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, msg)
    if type(a) ~= "number" or math.abs(a - b) > 1e-6 then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end

local function actionButton(bar, i) return _G[("FSActionButton%d_%d"):format(bar, i)] end
local function stanceButton(i) return _G["FSStanceButton" .. i] end
local function petButton(i) return _G["FSPetActionButton" .. i] end
local function anchorOf(region, point)
    for _, p in ipairs(region._points) do if p.point == point then return p end end
end

function T.every_bar_button_gets_one_fill_on_its_icon_above_the_swipe()
    for _, b in ipairs({ actionButton(1, 1), actionButton(6, 12), stanceButton(1), petButton(2) }) do
        local fill = b.fsCdFill
        eq(type(fill), "table", "a fill on " .. tostring(b._name))
        eq(fill._parent, b, "the fill is a child of the button")
        eq(fill._points[1].rel, b.icon, "the fill covers the icon")
        eq(fill:GetFrameLevel(), b.cooldown:GetFrameLevel() + 1, "the fill sits one over the swipe")
        eq(fill.fsEdgeHost:GetFrameLevel(), fill:GetFrameLevel() + 1, "the edge host one over the fill")
        eq(b.HotKey._parent:GetFrameLevel() > fill.fsEdgeHost:GetFrameLevel(), true, "the keybind over the fill")
        eq(fill._mouse, false, "click-through")
    end
end

function T.the_fill_is_a_vertical_bar_filling_from_the_top_in_the_approved_colour()
    local fill = actionButton(1, 1).fsCdFill
    eq(fill._orient, "VERTICAL", "vertical")
    eq(fill._reverse, true, "fills from the top, so its bottom edge rises")
    eq(fill._min == 0 and fill._max == 1, true, "0..1")
    local c, a = fill._sbColor, 1 - (1 - 0.55) * (1 - 0.60)
    near(a, 0.82, "0.55 violet over a 0.60 scrim")
    near(c[4], a, "alpha")
    for i = 1, 3 do near(c[i], __BORDER[i] * 0.55 / a, "COLOR_BORDER channel " .. i) end
    local edge = fill.fsEdge
    for i = 1, 3 do near(edge._color[i], __BORDER[i] + (1 - __BORDER[i]) * 0.55, "edge channel " .. i) end
    eq(edge._color[4], 1, "edge opaque")
    eq(anchorOf(edge, "BOTTOMLEFT").rel, fill:GetStatusBarTexture(), "the edge rides the fill's bottom")
    eq(anchorOf(edge, "BOTTOMRIGHT").rel, fill:GetStatusBarTexture(), "on both corners")
    eq(fill._clips, true, "the bar clips the edge host, so an empty bar shows no line")
    eq(fill.fsEdgeHost._parent, fill, "the edge lives in a child frame the clip applies to")
    local glow = fill.fsGlow
    eq(anchorOf(glow, "BOTTOMLEFT").rel, edge, "the glow sits on the edge")
    eq(glow._gradient[1], "VERTICAL", "the glow fades")
    near(glow._gradient[2].a, 0.45, "strong at the edge")
    eq(glow._gradient[3].a, 0, "clear away from it")
end

function T.a_new_fill_is_hidden_until_a_cooldown_runs()
    local b = CreateFrame("Button", "FSFillProbe", UIParent)
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.cooldown = CreateFrame("Cooldown", nil, b)
    FS.FrameHelpers.SeatButtonCooldown(b)
    eq(b.fsCdFill:IsShown(), false, "hidden")
    eq(b.fsCdFill._value, 0, "empty")
end

function T.a_rescale_reseats_the_fill_without_building_another()
    local b = actionButton(1, 1)
    local fill, n = b.fsCdFill, #__frames
    FS.FrameHelpers.SeatButtonCooldown(b)
    FS.FrameHelpers.SeatButtonCooldown(b)
    eq(b.fsCdFill, fill, "the same fill")
    eq(#__frames, n, "no frame or region made by a re-seat")
end

function T.a_cooldown_runs_the_fill_from_the_gcd_less_object_and_the_swipe_shows_the_gcd()
    local b = actionButton(1, 1)
    __gcdAsks = 0
    __now = __now + 1   -- a frame after the login refresh
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    local t = b.fsCdFill._timer
    eq(t ~= nil, true, "the fill was handed a duration object")
    eq(t.obj.slot, b.action, "the button's own slot")
    eq(t.obj.ignoreGCD, true, "asked with the GCD left out")
    eq(t.dir, Enum.StatusBarTimerDirection.RemainingTime, "runs down: remaining time")
    eq(t.interp, Enum.StatusBarInterpolation.Immediate, "no easing")
    eq(b.fsCdFill:IsShown(), true, "shown")
    eq(b.cooldown._cdObj.gcd, true, "the swipe is the global cooldown alone")
    eq(__gcdAsks, 1, "the GCD marker is asked once per frame time, not once per button")
    __now = __now + 1
    __fire_event("SPELL_UPDATE_COOLDOWN")
    eq(__gcdAsks, 2, "and again on a later frame")
end

function T.an_empty_slot_hides_its_fill()
    local b = actionButton(1, 1)
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), true, "running")
    local slot = b.action
    HasAction = function(s) return s ~= slot end
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), false, "an empty slot shows no fill")
end

function T.a_throwing_set_timer_duration_keeps_the_swipe_of_everything()
    local b = actionButton(1, 1)
    __timerThrows = true
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), false, "no fill")
    eq(b.cooldown._cdObj.slot, b.action, "the swipe has the slot's cooldown")
    eq(b.cooldown._cdObj.ignoreGCD, nil, "GCD included, as before")
end

function T.a_client_without_the_timer_direction_keeps_the_swipe_of_everything()
    local b = actionButton(1, 1)
    __timerCalls = 0
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(__timerCalls, 0, "a bar that would fill up is never started")
    eq(b.fsCdFill:IsShown(), false, "no fill")
    eq(b.cooldown._cdObj.ignoreGCD, nil, "the swipe has the whole cooldown")
end

function T.a_client_without_set_timer_duration_keeps_the_swipe_of_everything()
    local b = actionButton(1, 1)
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), false, "no fill")
    eq(b.cooldown._cdObj.slot, b.action, "the swipe has the slot's cooldown")
end

function T.a_client_without_clipping_gets_the_fill_and_no_edge()
    local b = actionButton(1, 1)
    eq(b.fsCdFill.fsEdge, nil, "no edge that could hang at the top of an empty bar")
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), true, "the fill still runs")
end

function T.a_client_without_set_reverse_fill_grows_from_the_bottom_with_the_edge_on_top()
    local fill = actionButton(1, 1).fsCdFill
    eq(fill.fsFromTop, false, "fills from the bottom here")
    eq(anchorOf(fill.fsEdge, "TOPLEFT").rel, fill:GetStatusBarTexture(), "the edge rides the moving top")
end

function T.a_client_with_no_status_bar_builds_no_fill_and_never_retries()
    local b = actionButton(1, 1)
    eq(b.fsCdFill, false, "marked unsupported")
    local n = #__frames
    FS.FrameHelpers.SeatButtonCooldown(b)
    eq(#__frames, n, "no frame made on a re-seat")
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.cooldown._cdObj ~= nil, true, "the swipe still runs")
end

function T.pet_plain_cooldown_fills_runs_down_and_hides_at_ready()
    local b = petButton(2)
    GetPetActionCooldown = function() return 100, 8, 1 end
    __now = 102
    __fire_event("PET_BAR_UPDATE")
    local fill = b.fsCdFill
    eq(fill:IsShown(), true, "a long cooldown is the fill")
    near(fill._value, 0.75, "6 of 8 s left")
    eq(b.cooldown._cd, nil, "the swipe is not handed the cooldown")
    eq(b.cooldown:IsShown(), false, "and is hidden")
    __now = 106
    fill._scripts.OnUpdate(fill, 4)
    near(fill._value, 0.25, "2 of 8 s left")
    __now = 108.5
    fill._scripts.OnUpdate(fill, 2.5)
    eq(fill:IsShown(), false, "gone at ready")
    eq(fill._scripts.OnUpdate, nil, "and its OnUpdate stopped")
end

function T.pet_plain_gcd_is_the_swipe_and_a_secret_hides_both_uncompared()
    local b = petButton(2)
    GetPetActionCooldown = function() return 100, 1.5, 1 end
    __fire_event("PET_BAR_UPDATE")
    eq(b.fsCdFill:IsShown(), false, "no fill for the GCD")
    eq(b.cooldown._cd[2], 1.5, "the GCD is the swipe")
    GetPetActionCooldown = function() return 100, 8, 1 end
    __fire_event("PET_BAR_UPDATE")
    eq(b.fsCdFill:IsShown(), true, "a real cooldown fills")
    GetPetActionCooldown = function() return __SECRET, __SECRET, 1 end
    b.cooldown._cd = nil
    __fire_event("PET_BAR_UPDATE")
    eq(b.fsCdFill:IsShown(), false, "a secret cooldown hides the fill")
    eq(b.cooldown:IsShown(), false, "and the swipe")
    eq(b.cooldown._cd, nil, "SetCooldown never saw a secret")
end

function T.plain_disabled_and_secret_enable_flags()
    local b = petButton(2)
    GetPetActionCooldown = function() return 100, 8, 0 end
    __fire_event("PET_BAR_UPDATE")
    eq(b.fsCdFill:IsShown(), false, "a disabled cooldown shows nothing")
    GetPetActionCooldown = function() return 100, 8, __SECRET end
    __fire_event("PET_BAR_UPDATE")
    eq(b.fsCdFill:IsShown(), true, "an unreadable enable flag counts as enabled")
end

function T.stance_plain_cooldown_is_the_fill()
    local b = stanceButton(1)
    GetShapeshiftFormCooldown = function() return 100, 10, 1 end
    __now = 105
    __fire_event("UPDATE_SHAPESHIFT_COOLDOWN")
    eq(b.fsCdFill:IsShown(), true, "a stance cooldown fills")
    near(b.fsCdFill._value, 0.5, "half left")
end

function T.the_fill_is_legal_in_combat()
    local b = actionButton(1, 1)
    __combat = true
    __blocked, __protectedTouch = 0, 0
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.fsCdFill:IsShown(), true, "runs in combat")
    eq(__blocked, 0, "no protected operation refused")
    eq(__protectedTouch, 0, "nothing built, anchored or re-levelled under the secure button in combat")
    __combat = false
end

return T
"""


def boot(name: str):
    if name in BARE:
        return abh.boot()
    return abh.boot(FILL_CLIENT + VARIANTS.get(name, "") + abh.PET_RING_PRELUDE.replace(
        "__now = 100\nfunction GetTime() return __now end\n", ""), ("Core/ChevronCastBar.lua",))


def main() -> int:
    names = sorted(boot("").execute(CHECKS).keys())
    failed = 0
    for name in names:
        lua = boot(name)
        try:
            lua.execute(CHECKS)[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
