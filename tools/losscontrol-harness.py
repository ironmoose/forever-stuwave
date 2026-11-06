#!/usr/bin/env python3
"""Runs the real LossOfControl.lua headless against a mock LossOfControlFrame.

The stun / fear / silence alert is drawn as the Gunsight "jam": brackets, an octagon well, sixteen ring ticks and a
plate for the word. These checks pin:

  * the effect type picks the colour (pink stun, violet fear, cyan silence, amber root), pink when unknown;
  * the ticks still lit follow the time left, and all stay lit when the time is unknown;
  * Blizzard's smoke and red rails go to alpha 0 and stay there;
  * the icon, word and seconds are re-seated into the jam's layout, again after the mixin sets up a display;
  * a secret duration is never used for the ring.

    python3 tools/losscontrol-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

SRC = (Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Skins/LossOfControl.lua").read_text(encoding="utf-8")

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind) return setmetatable({ kind = kind, alpha = 1 }, Obj) end
function Obj:SetPoint(p, rel, rp, x, y) self.point = { p, rel, rp, x or 0, y or 0 } end
function Obj:ClearAllPoints() self.point = nil end
function Obj:GetPoint() if self.point then return unpack(self.point) end end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Obj:SetTextColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Obj:CreateTexture() local t = New("Texture"); __textures[#__textures + 1] = t; return t end
function Obj:SetTexture(p) self.path = p end
function Obj:GetFrameStrata() return "HIGH" end
function Obj:GetFrameLevel() return 10 end
function Obj:HookScript(n, fn) self.hooks = self.hooks or {}; self.hooks[n] = fn end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:CreateAnimationGroup()
    local ag = New("AnimationGroup")
    function ag:CreateAnimation() return New("Animation") end
    function ag:Play() __played = (__played or 0) + 1 end
    return ag
end
__textures = {}
function CreateFrame() return New("Frame") end
function InCombatLockdown() return false end
__now = 10
function GetTime() return __now end
function hooksecurefunc(t, name, fn)
    local orig = t[name]
    t[name] = function(...) local r = orig(...); fn(...); return r end
end

LossOfControlFrame = New("Frame")
local F = LossOfControlFrame
F.blackBg, F.RedLineTop, F.RedLineBottom = New("Texture"), New("Texture"), New("Texture")
F.Icon = New("Texture"); F.Icon:SetPoint("CENTER", F, "CENTER", -60, 0)
F.AbilityName = New("FontString")
F.TimeLeft = New("Frame"); F.TimeLeft.NumberText = New("FontString"); F.TimeLeft.SecondsText = New("FontString")
function F:SetUpDisplay() self.Icon:ClearAllPoints(); self.Icon:SetPoint("CENTER", self, "CENTER", -60, 0) end

__data = nil
C_LossOfControl = { GetActiveLossOfControlData = function(i) return __data end }
SECRET = {}
FS = {
    IsSecret = function(v) return v == SECRET end,
    Config = { RegisterDefault = function() end, Get = function() return true end },
    Theme = {
        COLOR_HEALTH = { 1, 0.18, 0.59 }, COLOR_BORDER = { 0.66, 0.33, 0.97 }, COLOR_POWER = { 0.13, 0.88, 1 },
        COLOR_AMBER = { 1, 0.71, 0.28 }, COLOR_BAR_TRACK = { 0, 0, 0 }, COLOR_TEXT_WHITE = { 1, 1, 1 },
        SLICE_CUT_FILL_TEXTURE = "f", SLICE_CUT_MARGIN = 6, SLICE_CUT2_GLOW_TEXTURE = "g", SLICE_CUT2_GLOW_PAD = 4,
        SLICE_CUT2_FILL_TEXTURE = "f2", SLICE_CUT2_OUTLINE_TEXTURE = "o2", FONT_ORBITRON = "orb",
        AddSliceTexture = function(f) return f:CreateTexture() end,
        AddCut2Texture = function(f) return f:CreateTexture() end,
        AddCutCornerOutline = function(f) return f:CreateTexture() end,
        ApplyNineSlice = function() end, ApplyFontGeneric = function() end, ApplyMono = function() end,
    },
}
function Load() assert(loadstring(SRC, "@LossOfControl.lua"))("forever-stuwave", FS); return FS.LossOfControl end
function Ticks()
    local out = {}
    for _, t in ipairs(__textures) do if t.path and t.path:find("loc_tick") then out[#out + 1] = t end end
    return out
end
function Lit(col)
    local n = 0
    for _, t in ipairs(Ticks()) do if t.color and t.color[1] == col[1] and t.color[4] == 1 then n = n + 1 end end
    return n
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("effect_type_picks_the_colour", """
    local L = Load()
    local T = FS.Theme
    assert(L.TypeColor("STUN_MECHANIC") == T.COLOR_HEALTH)
    assert(L.TypeColor("FEAR") == T.COLOR_BORDER)
    assert(L.TypeColor("SILENCE") == T.COLOR_POWER and L.TypeColor("PACIFYSILENCE") == T.COLOR_POWER)
    assert(L.TypeColor("ROOT") == T.COLOR_AMBER)
    assert(L.TypeColor(nil) == T.COLOR_HEALTH and L.TypeColor(SECRET) == T.COLOR_HEALTH)
""")

case("lit_ticks_follow_the_time_left", """
    local L = Load()
    assert(L.LitTicks(3, 3) == 16)
    assert(L.LitTicks(1.5, 3) == 8)
    assert(L.LitTicks(0.6, 3) == 4)
    assert(L.LitTicks(0, 3) == 0)
    assert(L.LitTicks(nil, 3) == 16 and L.LitTicks(1, nil) == 16, "unknown time keeps the ring lit")
""")

case("stock_art_is_held_at_zero_and_the_layout_is_seated", """
    __data = { locType = "STUN", startTime = 9, duration = 3 }
    Load()
    local F = LossOfControlFrame
    assert(F.blackBg.alpha == 0 and F.RedLineTop.alpha == 0 and F.RedLineBottom.alpha == 0)
    F.RedLineTop:SetAlpha(1)
    assert(F.RedLineTop.alpha == 0, "a rail came back")
    local p = { F.Icon:GetPoint() }
    assert(p[1] == "CENTER" and p[2] == F and p[4] == 0 and p[5] == 24, "icon not in the well: " .. tostring(p[4]) .. "," .. tostring(p[5]))
    assert(#Ticks() == 16, "ticks: " .. #Ticks())
    assert(Lit(FS.Theme.COLOR_HEALTH) == 11, "2 of 3 s left lights 11, got " .. Lit(FS.Theme.COLOR_HEALTH))
    F:SetUpDisplay()
    p = { F.Icon:GetPoint() }
    assert(p[4] == 0 and p[5] == 24, "the mixin's own anchor survived SetUpDisplay")
    assert((__played or 0) >= 1, "no snap in on a new display")
""")

case("a_secret_duration_keeps_every_tick_lit", """
    __data = { locType = "SILENCE", startTime = SECRET, duration = SECRET }
    Load()
    assert(Lit(FS.Theme.COLOR_POWER) == 16, "lit: " .. Lit(FS.Theme.COLOR_POWER))
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().SRC = SRC
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
