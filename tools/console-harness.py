#!/usr/bin/env python3
"""Runs the real ActionBars.lua + Console.lua headless against the actionbars-harness mock.

The Console is the Gunsight HUD's action bar chassis: ONE plate around the 72 buttons with
a stepped shoulder tab on top for the HUD keys (the locked design in
mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html, "Console panel style").
The checks pin the geometry the mockup states, resolved from the REAL button frames rather
than from a copy of the arithmetic:

  * chassis rect = the button field plus CN_PAD 8 / CN_MARG 7 (left) / CN_PT 15 / CN_PB 15,
    in design px (UI units = design * FS.Layout.Scale()), and again after a rescale;
  * the shoulder tab: foot CN_FOOT in from the TAB_DW box (computed from the key count, 349
    wide at 8 keys), height CN_TH, right edge = chassis right edge; ONE continuous outline
    path (no top line under the tab, no halo inside it);
  * the tab fits the SHOWN keys: Console.SetKeyCount(n) moves the tab's left edge and the whole
    slanted shoulder (wedge, foot rail, halo, outline) with an even key pitch (key + CN gap, no
    group gaps) and the same 15 padding at n = 8, 6 and 4; refused in combat;
  * the key gap rule: the HUD key bottom sits CN_VG = 49.2 - 36 design px above the first
    button top;
  * pips, spine at the stack centre, row dividers, tick ruler, silkscreen, screws;
  * pill chrome (fill, border, MAIN tag) hangs off a hideable child and is hidden while the
    Console is on, shown again by `/fsconsole off`; the 7.2 pill gap grows to CN_SPINE 20;
  * nothing protected is re-seated, shown or hidden in combat; the work waits for regen.

Every number the mockup owns (CN_*, DK, DECK_N, TAB_RP, so TAB_DW) is parsed back out of the mockup, so a mockup
edit fails here instead of drifting. The mock is NOT the real client: it does not render,
and resolves anchors with the small solver in CHECKS (single point anchors, nested scales).

    python3 tools/console-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "addon" / "ForeverSynthwave"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
TOC = ADDON / "ForeverSynthwave.toc"
CONSOLE = ADDON / "Console.lua"
LAYOUT = ADDON / "Layout.lua"

_spec = importlib.util.spec_from_file_location("actionbars_harness", HERE / "actionbars-harness.py")
abh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(abh)

SCALES = (1 / 1.2, 1.0)   # the live client's UI scale, and an identity scale


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_constants() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    pad, marg, pt, pb, cut, zx, zt, zy, spine, sr = _m(
        r"var CN_PAD=(\d+),CN_MARG=(\d+),CN_PT=(\d+),CN_PB=(\d+),CN_CUT=(\d+),CN_ZX=(\d+),CN_ZT=(\d+),"
        r"CN_ZY=([\d.]+),CN_SPINE=(\d+),CN_SR=(\d+)", src, "CN_ constants").groups()
    dk = dict(re.findall(r"(\w+):(\d+)", _m(r"var DK=\{([^}]*)\}", src, "DK").group(1)))
    dk = {k: int(v) for k, v in dk.items()}
    deck_n = int(_m(r"var DECK_N=(\d+);", src, "DECK_N").group(1))
    tab_rp = int(_m(r"TAB_RP=(\d+);", src, "TAB_RP").group(1))
    _m(r"var TAB_DW=DK\.SH\+DK\.PAD\+DECK_N\*DK\.W\+\(DECK_N-1\)\*DK\.GAP\+TAB_RP;", src, "TAB_DW formula")
    _m(r"function keyX\(i\)\{return DK\.SH\+DK\.PAD\+i\*\(DK\.W\+DK\.GAP\);\}", src, "even keyX")
    tab_dw = dk["SH"] + dk["PAD"] + deck_n * dk["W"] + (deck_n - 1) * dk["GAP"] + tab_rp
    ab_rp = float(_m(r"AB_RP=([\d.]+)\*AU", src, "AB_RP").group(1))
    ab_bs = int(_m(r"AB_BS=(\d+)\*AU", src, "AB_BS").group(1))

    def key_x(i: int) -> int:
        return dk["SH"] + dk["PAD"] + i * (dk["W"] + dk["GAP"])

    cn_vg = ab_rp - ab_bs
    cn_kb = int(pt) - cn_vg
    cn_tp = tab_dw - (key_x(deck_n - 1) + dk["W"])
    cn_th = dk["H"] - cn_kb + cn_tp
    # the 45 degree cut sits cn_tp (perpendicular) from the first key's top-left chamfer edge
    cn_foot = dk["SH"] + dk["PAD"] + cn_tp + dk["C"] - cn_th - cn_tp * math.sqrt(2)
    return dict(
        PAD=int(pad), MARG=int(marg), PT=int(pt), PB=int(pb), CUT=int(cut), ZX=int(zx), ZT=int(zt),
        ZY=float(zy), SPINE=int(spine), SR=int(sr), TAB_DW=tab_dw, KEY_W=dk["W"], KEY_H=dk["H"],
        KEY_C=dk["C"], KEY_GAP=dk["GAP"], DECK_N=deck_n, TAB_RP=tab_rp, KEY_PAD=dk["PAD"], KEY_SH=dk["SH"],
        KEY_X0=key_x(0), KEY_XL=key_x(deck_n - 1), RP=ab_rp, BS=ab_bs,
        VG=cn_vg, KB=cn_kb, TP=cn_tp, TH=cn_th, FOOT=cn_foot,
    )


def layout_constants() -> dict:
    """The chat clearances Layout.lua owns (the real numbers, parsed back out of it)."""
    src = LAYOUT.read_text(encoding="utf-8")
    out = {}
    for name in ("CHAT_CHROME_RIGHT", "CHAT_CLEARANCE", "CONSOLE_PET_GAP"):
        m = re.search(rf"^FS\.Layout\.{name} = (-?[\d.]+)", src, re.M)
        if not m:
            sys.exit(f"Layout.lua: FS.Layout.{name} not found")
        out[name] = float(m.group(1))
    return out


def chat_edge_implied_by_the_code(scale: float) -> float:
    """Right edge of the chat terminal in design px (centre-relative), derived from the code:
    the chat entry's right edge plus the backdrop outset (ChatCore PAD_X) and the SkinPanel
    glow (Theme SLICE_GLOW_PAD), both UI units, converted at `scale`. This is a sanity
    floor: the check asserts CHAT_CHROME_RIGHT is never left of this value, leaving about
    19px unexplained, so it only fires if the chat outset grows significantly. The real guard
    is re-measuring from a live screenshot when the chat chrome changes."""
    pad_x = int(_m(r"(?m)^local PAD_X = (\d+)", (ADDON / "ChatCore.lua").read_text(encoding="utf-8"), "ChatCore PAD_X").group(1))
    glow = int(_m(r"(?m)^Theme\.SLICE_GLOW_PAD = (\d+)", (ADDON / "Theme.lua").read_text(encoding="utf-8"), "SLICE_GLOW_PAD").group(1))
    lay = re.search(r"^\s+chat\s+= \{[^}]*x = (-?\d+),\s+y = -?\d+,\s+w = (\d+)", LAYOUT.read_text(encoding="utf-8"), re.M)
    if not lay:
        sys.exit("Layout.lua: chat entry not found")
    x, w = int(lay.group(1)), int(lay.group(2))
    return x + w / 2 + (pad_x + glow) / scale


PRELUDE = r"""
__scale = %(scale)r
__say = nil
print = function(...) __say = table.concat({ ... }, " ") end
UIParent._w, UIParent._h = 2560 * __scale, 1440 * __scale
UIParent._scale = 1

-- extra widget surface the Console uses (the actionbars mock does not model a texture's look)
function __Region:SetScale(s) self._scale = s end
function __Region:GetScale() return self._scale or 1 end
function __Region:SetGradient(o, a, b) self._gradient = { orientation = o, from = a, to = b } end
function __Region:SetColorTexture(r, g, b, a) self._color = { r, g, b, a }; self._texture = nil end
function __Region:SetTexCoord(...) self._tc = { ... } end
function __Region:SetRotation(r) self._rot = r end
function __Region:SetSnapToPixelGrid() end
function __Region:SetTextColor(r, g, b, a) self._textColor = { r, g, b, a } end
function __Region:SetShadowColor() end
function __Region:SetShadowOffset() end
function __Region:GetStringWidth() return 40 end
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a or 1 } end

-- the Theme chrome the pill builds from: record that it landed on the frame it was given
FS.Theme.AddRoundedFill = function(frame) frame:CreateTexture(nil, "BACKGROUND") end
FS.Theme.AddGradientBorder = function(frame) frame:CreateTexture(nil, "BORDER") end
FS.Theme.AddOuterGlow = function(frame) frame:CreateTexture(nil, "BACKGROUND") end
FS.Theme.ApplyMono = function(fs, size, color) fs:SetFont("mono.ttf", size, ""); fs._mono = { size = size, color = color } end  -- the real one calls SetFont

-- Layout that follows the scale, like the real one (design px -> UI units = * Scale())
FS.Layout.Scale = function() return __scale end
FS.Layout.action = { point = "CENTER", relPoint = "CENTER", x = -7, y = -540, w = 1089, h = 178 }
FS.Layout.CHAT_CHROME_RIGHT = %(chat_right)r
FS.Layout.CHAT_CLEARANCE = %(chat_clear)r
FS.Layout.Apply = function(frame, id)
    local L, s = FS.Layout[id], __scale
    frame:ClearAllPoints()
    if L.point then frame:SetPoint(L.point, UIParent, L.relPoint, L.x * s, L.y * s) end
    frame:SetSize(L.w * s, L.h * s)
    L.scaledW, L.scaledH = L.w * s, L.h * s
    return L
end
__rescaleCbs = {}
FS.Layout.OnRescale = function(fn) __rescaleCbs[#__rescaleCbs + 1] = fn end
function __fire_rescale() for _, fn in ipairs(__rescaleCbs) do fn() end end
function __rescale(s)
    __scale = s
    UIParent._w, UIParent._h = 2560 * s, 1440 * s
    FS.Layout.Apply(FSActionBarStack, "action")
    __fire_rescale()
end

-- A frame that parents secure buttons is protected implicitly: model it, and refuse the
-- anchor and size edits the engine refuses on a protected frame in combat.
for _, name in ipairs({ "SetPoint", "SetSize", "ClearAllPoints", "SetWidth", "SetHeight" }) do
    local orig = __Region[name]
    __Region[name] = function(self, ...)
        if self._protected and __combat then __blocked = __blocked + 1 end
        return orig(self, ...)
    end
end
function __protect_stack()
    FSActionBarStack._protected = true
    for i = 1, 6 do _G["FSActionBar" .. i]._protected = true end
end
%(db)s
"""


def make_prelude(scale: float, db: str = "") -> str:
    lay = layout_constants()
    return PRELUDE % dict(scale=scale, db=db, chat_right=lay["CHAT_CHROME_RIGHT"], chat_clear=lay["CHAT_CLEARANCE"])


CHECKS = r"""
local T = {}
local EPS = 1e-6
local M = __M

local function near(a, b, msg, eps)
    if a == nil or b == nil or math.abs(a - b) > (eps or EPS) then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function truthy(v, msg) if not v then error(msg or "expected truthy", 2) end end

-- ---- a small anchor solver: single point anchors, nested frame scales -------------------
local FRAC = {
    TOPLEFT = { 0, 0 }, TOP = { .5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, .5 }, CENTER = { .5, .5 },
    RIGHT = { 1, .5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { .5, 1 }, BOTTOMRIGHT = { 1, 1 },
}
local function isFrame(f) return f._kind ~= "Texture" and f._kind ~= "FontString" end
local function spaceScale(f)  -- scale of the coordinate space f's anchors and size are written in
    if f == UIParent then return 1 end
    if isFrame(f) then
        local parentScale = f._parent and spaceScale(f._parent) or 1
        return parentScale * (f._scale or 1)
    end
    return spaceScale(f._parent)
end
local function rect(f)
    if f == UIParent then return { l = 0, t = 0, w = UIParent._w, h = UIParent._h, r = UIParent._w, b = UIParent._h } end
    local p = f._points[1]
    if not p then error("no anchor on " .. tostring(f._name or f._kind), 2) end
    local R = rect(p.rel)
    local sc = spaceScale(f)
    local ax = R.l + FRAC[p.relPoint][1] * R.w + p.x * sc
    local ay = R.t + FRAC[p.relPoint][2] * R.h - p.y * sc
    local w, h = f._w * sc, f._h * sc
    local l = ax - FRAC[p.point][1] * w
    local t = ay - FRAC[p.point][2] * h
    return { l = l, t = t, w = w, h = h, r = l + w, b = t + h }
end

local function C() return FS.Console end
local function S() return __scale end
local function btn(bar, i) return __button(bar, i) end
local function chassis() return rect(C().root) end
-- a region's rect in DESIGN px, relative to the chassis top-left (y down, above the chassis negative)
local function D(f)
    local R, r, s = chassis(), rect(f), S()
    return { x = (r.l - R.l) / s, y = (r.t - R.t) / s, w = r.w / s, h = r.h / s,
             r = (r.r - R.l) / s, b = (r.b - R.t) / s }
end
local function chassisDesign()
    local R, s = chassis(), S()
    return R.w / s, R.h / s
end

-- ---- chassis ----------------------------------------------------------------------------
function T.chassis_wraps_the_button_field_with_the_mockup_paddings()
    local R, s = chassis(), S()
    near(R.l, rect(btn(1, 1)).l - (M.PAD + M.MARG) * s, "left = first button - (PAD + MARG)")
    near(R.t, rect(btn(1, 1)).t - M.PT * s, "top = first row - PT")
    near(R.r, rect(btn(2, 12)).r + M.PAD * s, "right = last button + PAD")
    near(R.b, rect(btn(6, 12)).b + M.PB * s, "bottom = last row + PB")
    eq(C().root:GetParent(), UIParent, "Console hangs off UIParent, not the protected stack")
    truthy(C().root:IsShown(), "Console shown")
    truthy(C().IsActive(), "Console active")
end

function T.chassis_follows_a_rescale()
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    T.chassis_wraps_the_button_field_with_the_mockup_paddings()
    local W, H = chassisDesign()
    near(C().layout.w, W, "layout width follows")
    near(C().layout.h, H, "layout height follows")
end

function T.chassis_geometry_is_the_computed_layout()
    local W, H = chassisDesign()
    local L = C().layout
    near(L.w, W, "w"); near(L.h, H, "h")
    near(L.cut, M.CUT, "cut")
    near(L.field.x, M.PAD + M.MARG, "field x"); near(L.field.y, M.PT, "field y")
    near(L.field.h, H - M.PT - M.PB, "field h")
    near(L.field.w, W - (M.PAD + M.MARG) - M.PAD, "field w")
end

function T.console_draws_behind_the_buttons_and_never_under_the_stack()
    local stack, root = FSActionBarStack, C().root
    truthy(root:GetFrameLevel() < stack:GetFrameLevel(), "root below the stack")
    truthy(C().tab:GetFrameLevel() > C().art:GetFrameLevel(), "tab above the chrome")
    local f = C().tab
    while f do
        if f == stack then error("a Console frame is parented under the protected stack") end
        f = f:GetParent()
    end
    eq(C().art:GetScale(), S(), "chrome host carries the design scale (1 unit = 1 design px)")
end

-- ---- tab --------------------------------------------------------------------------------
function T.tab_foot_height_and_right_edge()
    local R, s = chassis(), S()
    local tab = rect(C().tab)
    near(tab.r, R.r, "tab right edge = chassis right edge")
    near(tab.b, R.t, "tab bottom stands on the chassis top line")
    near(tab.h, M.TH * s, "tab height CN_TH")
    near(tab.l, R.r - (M.TAB_DW - M.FOOT) * s, "foot = right edge - (TAB_DW - CN_FOOT), TAB_DW computed from the key count")
    near(tab.w, (M.TAB_DW - M.FOOT) * s, "tab width")
    near(M.TH, 39.2, "CN_TH derivation (mockup)", 1e-9)
    near(M.FOOT, 34 + 15 + 6 - 39.2 - 15 * math.sqrt(2), "CN_FOOT derivation (mockup)", 1e-9)
end

-- the tab's left cut is x + y = TH in tab-local design px (45 degrees, foot at the bottom left);
-- the first key's top-left chamfer is x + y = key.x + TP + C. Parallel lines, so the
-- perpendicular gap is the difference over sqrt 2, and it must equal TP (the padding the keys
-- have to the tab's top and right edges).
function T.tab_cut_is_cn_tp_from_the_first_keys_chamfer_edge()
    local s = S()
    local tab, area = rect(C().tab), C().keyArea
    local cutC = tab.h / s
    local chamferC = (area.x + area.y) / s + M.KEY_C
    near((chamferC - cutC) / math.sqrt(2), M.TP, "perpendicular gap, cut to first key chamfer = CN_TP")
    near(M.TP, 15, "CN_TP", 1e-9)
end

function T.tab_is_one_continuous_outline_with_no_seam()
    local W, H = chassisDesign()
    local P = C().parts
    local tx, th = W - (M.TAB_DW - M.FOOT), M.TH
    -- the chassis top line stops where the foot stands: nothing runs under the tab
    local top = D(P.lineTop)
    near(top.x, M.CUT, "top line starts after the cut"); near(top.r, tx, "top line stops at the foot")
    near(top.h, 1, "1 texel line")
    -- the right edge is ONE line from the tab top down to the BR cut
    local right = D(P.lineRight)
    near(right.r, W, "right line on the right edge"); near(right.y, -th, "right line starts at the tab top")
    near(right.b, H - M.CUT, "right line ends at the BR cut")
    -- the tab top line meets the foot stub and the right line, the foot sits on the chassis top line
    local tt = D(P.lineTabTop)
    near(tt.y, -th, "tab top line at the tab top"); near(tt.r, W - 1, "tab top line ends at the right line")
    local foot = D(P.foot)
    near(foot.w, 59.2, "foot texture is 59.2 wide", 1e-9); near(foot.h, 49.2, "foot texture is 49.2 tall", 1e-9)
    near(foot.x, tx - 10, "foot left = foot x - 10")
    near(foot.b, 0.5, "foot bottom ends mid way down the chassis top line")
    near(tt.x, foot.x + 59.2, "top line carries on where the foot stub ends")
    -- the wedge fills the foot, the rect the rest of the tab, both above the chassis
    local wedge, rest = D(P.tabWedge), D(P.tabFill)
    near(wedge.x, tx, "wedge at the foot"); near(wedge.y, -th, "wedge top"); near(wedge.w, th, "wedge is 45 degrees: w = h")
    near(wedge.h, th, "wedge height"); near(rest.x, tx + th, "fill continues after the wedge")
    near(rest.r, W, "fill reaches the right edge"); near(rest.b, 0, "tab fill stops at the chassis top line")
    eq(P.tabWedge._texture, C().TEX.slant, "wedge texture")
    eq(P.foot._texture, C().TEX.foot, "foot texture")
end

function T.halo_stays_outside_and_never_lights_the_tab_interior()
    local W = chassisDesign()
    local P = C().parts
    local tx, th = W - (M.TAB_DW - M.FOOT), M.TH
    truthy(D(P.haloTop).r <= tx + 1e-6, "halo above the chassis top ends at the foot")
    truthy(D(P.haloTabTop).x >= tx + 49.2 - 1e-6, "tab top halo starts where the foot stub ends")
    near(D(P.haloTabTop).b, -th, "tab top halo sits above the tab top")
    near(D(P.haloRight).x, W, "right halo is outside the right edge")
    near(D(P.haloLeft).r, 0, "left halo is outside the left edge")
    near(D(P.haloBottom).y, chassisDesign() and select(2, chassisDesign()), "bottom halo is below the bottom edge")
    for _, k in ipairs({ "haloTL", "haloTR", "haloBR", "haloBL" }) do
        eq(P[k]._texture, C().TEX.glow, k .. " texture")
        eq(#P[k]._tc, 4, k .. " samples a corner block, not the stretched plate")
    end
end

-- ---- the tab fits the shown keys ---------------------------------------------------------
-- Pure arithmetic of the count n: keys start at the left inset, run at one even pitch (key + gap)
-- and keep the same right padding; the slanted shoulder rides the computed edge.
function T.tab_fits_the_shown_key_count_at_8_6_and_4_keys()
    local s = S()
    local P = C().parts
    for _, n in ipairs({ 8, 6, 4 }) do
        truthy(C().SetKeyCount(n), "SetKeyCount(" .. n .. ") was refused out of combat")
        eq(C().GetKeyCount(), n, "key count")
        local boxW = M.KEY_SH + M.KEY_PAD + n * M.KEY_W + (n - 1) * M.KEY_GAP + M.TP
        near(C().TabWidth(n), boxW, "TabWidth(" .. n .. ") is the left inset + n keys + (n - 1) gaps + the right padding")
        local R = chassis()
        local tab, area = rect(C().tab), C().keyArea
        near(tab.r, R.r, "n=" .. n .. " tab right edge = chassis right edge")
        near(tab.w, (boxW - M.FOOT) * s, "n=" .. n .. " tab width follows the count")
        near(tab.h, M.TH * s, "n=" .. n .. " tab height does not depend on the count")
        near(area.w, (n * M.KEY_W + (n - 1) * M.KEY_GAP) * s, "n=" .. n .. " key area width")
        near(tab.r - (tab.l + area.x + area.w), M.TP * s, "n=" .. n .. " right padding is 15")
        near(area.y, M.TP * s, "n=" .. n .. " top padding is 15")
        near(area.x, (M.KEY_SH + M.KEY_PAD - M.FOOT) * s, "n=" .. n .. " the first key keeps its place in the tab")
        for i = 1, n - 1 do
            local gap = C().KeyRect(i, s).x - (C().KeyRect(i - 1, s).x + M.KEY_W * s)
            near(gap, M.KEY_GAP * s, "n=" .. n .. " gap after key " .. i .. " is the even gap")
        end
        -- the 45 degree cut stays CN_TP (perpendicular) from the first key's chamfer, the same 15 as the right padding
        local cutC = tab.h / s
        local chamferC = (area.x + area.y) / s + M.KEY_C
        near((chamferC - cutC) / math.sqrt(2), M.TP, "n=" .. n .. " cut to the first key's chamfer is CN_TP")
        -- the chassis pieces ride the computed foot
        local W, H = chassisDesign()
        local tx, th = W - (boxW - M.FOOT), M.TH
        near(C().layout.tx, tx, "n=" .. n .. " layout.tx")
        near(D(P.lineTop).r, tx, "n=" .. n .. " top line stops at the foot")
        near(D(P.foot).x, tx - 10, "n=" .. n .. " foot rail")
        near(D(P.lineTabTop).x, D(P.foot).x + 59.2, "n=" .. n .. " tab top line carries on from the foot stub")
        near(D(P.tabWedge).x, tx, "n=" .. n .. " wedge at the foot"); near(D(P.tabWedge).w, th, "n=" .. n .. " wedge is 45 degrees")
        near(D(P.tabFill).x, tx + th, "n=" .. n .. " fill continues after the wedge"); near(D(P.tabFill).r, W, "n=" .. n .. " fill reaches the right edge")
        truthy(D(P.haloTop).r <= tx + 1e-6, "n=" .. n .. " halo above the chassis top ends at the foot")
        near(D(P.haloTabTop).x, tx - 10 + 59.2, "n=" .. n .. " tab top halo starts where the foot stub ends")
        near(D(P.lineRight).r, W, "n=" .. n .. " right line on the right edge")
        near(D(P.screws and P.screws[1].disc).x + 4, W - 7.5, "n=" .. n .. " screw stays in the shoulder's top right corner")
        near(tab.b, R.t, "n=" .. n .. " tab stands on the chassis top line")
    end
end

function T.key_count_is_clamped_and_refused_in_combat()
    truthy(C().SetKeyCount(5), "accepted out of combat")
    local w = rect(C().tab).w
    __combat = true
    eq(C().SetKeyCount(3), false, "refused in combat")
    eq(C().GetKeyCount(), 5, "count unchanged by the refused call")
    near(rect(C().tab).w, w, "tab not resized in combat")
    __combat = false
    truthy(C().SetKeyCount(99), "accepted")
    eq(C().GetKeyCount(), M.DECK_N, "clamped to the most keys the tab has")
    truthy(C().SetKeyCount(0), "accepted")
    eq(C().GetKeyCount(), 1, "clamped to one key")
end

function T.key_count_set_before_the_first_seat_is_used_by_it()
    -- the count is state, not a one-shot reseat: a rescale and a new geometry keep the shown keys' tab
    C().SetKeyCount(6)
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    local boxW = M.KEY_SH + M.KEY_PAD + 6 * M.KEY_W + 5 * M.KEY_GAP + M.TP
    near(rect(C().tab).w, (boxW - M.FOOT) * S(), "tab width survives a rescale")
end

-- ---- the pet dock gap -------------------------------------------------------------------
-- SetDockGap(x0, x1) opens the chassis top outline and its halo where the pet panel docks, the
-- way the key tab omits the line under itself: the top line and the top halo split in two around
-- the gap (one extra texture each), everything else (fill, corners, the tab) stays put.
local GP = 11   -- the halo's reach (Console.lua GP)
local KEEP = { "cornerTL", "cornerBR", "lineLeft", "lineBottom", "lineRight", "lineTabTop", "foot", "tabWedge",
               "tabFill", "haloTL", "haloTR", "haloBR", "haloBL", "haloLeft", "haloTabTop", "haloRight",
               "haloBottom", "fillTop", "fillMid", "fillBottom", "fillTL", "fillBR" }
local function snapParts()
    local out = {}
    for _, k in ipairs(KEEP) do out[k] = D(C().parts[k]) end
    return out
end
local function sameParts(a, b, label)
    for _, k in ipairs(KEEP) do
        for _, f in ipairs({ "x", "y", "w", "h" }) do
            near(b[k][f], a[k][f], label .. ": " .. k .. "." .. f, 1e-6)
        end
    end
end
-- the top line and halo pieces as { x, r } in design px, nil when hidden
local function piece(k)
    local t = C().parts[k]
    if not t:IsShown() then return nil end
    local d = D(t)
    return { x = d.x, r = d.r, y = d.y, h = d.h, w = d.w }
end
local function noGap(tx, label)
    local a, ah = piece("lineTop"), piece("haloTop")
    truthy(a, label .. ": top line drawn"); truthy(ah, label .. ": top halo drawn")
    near(a.x, M.CUT, label .. ": top line from the cut"); near(a.r, tx, label .. ": top line to the foot")
    near(ah.x, M.CUT, label .. ": halo from the cut"); near(ah.r, tx, label .. ": halo to the foot")
    eq(piece("lineTop2"), nil, label .. ": no second line piece")
    eq(piece("haloTop2"), nil, label .. ": no second halo piece")
    eq(C().layout.gap, nil, label .. ": no gap in the layout")
end

function T.dock_gap_opens_the_top_line_and_halo_at_scales_1_and_064()
    local s0 = __scale
    -- manual loop: 0.64 is a real UI scale but is not in SCALES
    for _, s in ipairs({ 1.0, 0.64 }) do
        __rescale(s)
        local tag = "scale " .. s .. ": "
        local before = snapParts()
        local tx = C().layout.tx
        truthy(tx > 300, tag .. "the test gap sits left of the foot")
        truthy(C().SetDockGap(100, 300), tag .. "accepted out of combat")
        local P = C().parts
        local line, line2 = piece("lineTop"), piece("lineTop2")
        truthy(line and line2, tag .. "both line pieces drawn")
        near(line.x, M.CUT, tag .. "left stub starts at the TL cut"); near(line.r, 100, tag .. "left stub ends at x0")
        near(line2.x, 300, tag .. "right piece starts at x1"); near(line2.r, tx, tag .. "right piece runs to the foot")
        near(line.y, 0, tag .. "left stub on the top edge"); near(line.h, 1, tag .. "1 texel")
        near(line2.y, 0, tag .. "right piece on the top edge"); near(line2.h, 1, tag .. "1 texel")
        near(line.w, 100 - M.CUT, tag .. "left stub width")
        -- nothing of the top line lies inside the gap
        truthy(line.r <= 100 + 1e-9 and line2.x >= 300 - 1e-9, tag .. "the gap is open")
        -- the halo pieces (their x extents are checked against the line in dock_gap_halo_matches_the_line_split)
        local h, h2 = piece("haloTop"), piece("haloTop2")
        truthy(h and h2, tag .. "both halo pieces drawn")
        near(h.y, -GP, tag .. "halo above the top edge"); near(h.h, GP, tag .. "halo reach")
        near(h2.y, -GP, tag .. "halo piece 2 above the top edge"); near(h2.h, GP, tag .. "halo piece 2 reach")
        eq(P.haloTop2._texture, C().TEX.glow, tag .. "halo piece 2 is the same glow strip")
        eq(#P.haloTop2._tc, 4, tag .. "halo piece 2 samples the straight middle")
        for i = 1, 4 do near(P.haloTop2._tc[i], P.haloTop._tc[i], tag .. "same strip texcoord " .. i) end
        -- the layout reports the effective gap
        near(C().layout.gap.x0, 100, tag .. "layout gap x0"); near(C().layout.gap.x1, 300, tag .. "layout gap x1")
        -- fill, corners and the key tab are untouched, and the fill stays continuous
        sameParts(before, snapParts(), tag .. "unchanged by the gap")
        local a, b, c = D(P.fillTop), D(P.fillMid), D(P.fillBottom)
        near(a.x, M.CUT, tag .. "fill top still spans to the right edge"); near(a.r, chassisDesign(), tag .. "fill top reaches the right edge")
        near(a.b, b.y, tag .. "fill still tiles"); near(b.b, c.y, tag .. "fill still tiles")
        C().SetDockGap(nil, nil)
    end
    __rescale(s0)
end

function T.dock_gap_leaves_the_right_key_tab_alone()
    local P = C().parts
    local tabBefore = rect(C().tab)
    local areaBefore = C().keyArea
    truthy(C().SetDockGap(120, 280))
    local tabAfter = rect(C().tab)
    for _, f in ipairs({ "l", "t", "w", "h" }) do near(tabAfter[f], tabBefore[f], "tab frame " .. f) end
    near(C().keyArea.x, areaBefore.x, "key area x"); near(C().keyArea.w, areaBefore.w, "key area w")
    -- the right piece stops where the foot stands, not under the tab
    near(piece("lineTop2").r, C().layout.tx, "right piece ends at the foot")
    near(piece("haloTop2").r, C().layout.tx, "right halo piece ends at the foot")
    near(D(P.lineTabTop).x, D(P.foot).x + 59.2, "tab top line still carries on from the foot stub")
end

function T.dock_gap_halo_matches_the_line_split()
    for _, gap in ipairs({ { 100, 300 }, { 14, 200 }, { 250, 1e6 }, { 60, 61 } }) do
        truthy(C().SetDockGap(gap[1], gap[2]))
        local g = C().layout.gap
        local l, l2, h, h2 = piece("lineTop"), piece("lineTop2"), piece("haloTop"), piece("haloTop2")
        eq((l ~= nil), (h ~= nil), "left line and halo shown together " .. gap[1])
        eq((l2 ~= nil), (h2 ~= nil), "right line and halo shown together " .. gap[1])
        if l then near(l.x, h.x, "left piece x"); near(l.r, h.r, "left piece right edge") end
        if l2 then near(l2.x, h2.x, "right piece x"); near(l2.r, h2.r, "right piece right edge") end
        near(g.x0, math.max(gap[1], M.CUT), "effective x0 is clamped to the cut")
        near(g.x1, math.min(gap[2], C().layout.tx), "effective x1 is clamped to the foot")
    end
end

function T.dock_gap_is_refused_in_combat()
    truthy(C().SetDockGap(100, 300), "accepted out of combat")
    local before = snapParts()
    local line, line2 = piece("lineTop"), piece("lineTop2")
    __combat = true
    eq(C().SetDockGap(40, 90), false, "a new gap is refused in combat")
    eq(C().SetDockGap(nil, nil), false, "a clear is refused in combat")
    __combat = false
    sameParts(before, snapParts(), "nothing moved")
    near(piece("lineTop").r, line.r, "left piece unchanged"); near(piece("lineTop2").x, line2.x, "right piece unchanged")
    near(C().layout.gap.x0, 100, "the refused call did not record a gap")
    -- a refused gap is not remembered: a clear that was refused stays refused, a set that was refused never lands
    C().SetDockGap(nil, nil)
    __combat = true
    eq(C().SetDockGap(40, 90), false, "refused again")
    __combat = false
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    eq(C().layout.gap, nil, "no gap came back with a rescale")
    noGap(C().layout.tx, "after the refused call")
end

-- ---- the gap patch ------------------------------------------------------------------------
-- A 1 texel line plus a halo strip over exactly the gap span, built with the top line's and top halo's own
-- recipe (so a patch at alpha 1 is an unbroken line), whose ALPHA the pet dock drives: SetAlpha is legal in
-- combat where Show, Hide and SetPoint on the anchored chassis are not.
local function same(a, b, label)
    eq(type(a), type(b), label)
    if type(a) == "table" then
        eq(#a, #b, label .. " length")
        for i = 1, #a do near(a[i], b[i], label .. "[" .. i .. "]") end
    else
        eq(a, b, label)
    end
end

function T.gap_patch_fills_the_gap_with_the_top_lines_own_recipe()
    local P = C().parts
    truthy(P.gapLine and P.gapHalo, "the patch textures exist once the chassis is built")
    eq(P.gapLine:IsShown(), false, "no gap, no patch line"); eq(P.gapHalo:IsShown(), false, "no gap, no patch halo")
    local before = snapParts()
    truthy(C().SetDockGap(100, 300))
    local l, h = piece("gapLine"), piece("gapHalo")
    truthy(l and h, "the patch is drawn over the gap")
    near(l.x, 100, "patch line from x0"); near(l.r, 300, "patch line to x1")
    near(l.y, 0, "patch line on the top edge"); near(l.h, 1, "patch line is 1 texel")
    near(h.x, 100, "patch halo from x0"); near(h.r, 300, "patch halo to x1")
    near(h.y, -GP, "patch halo above the top edge"); near(h.h, GP, "patch halo reach")
    -- the same recipe as the line and halo it stands in for
    same(P.gapLine._color, P.lineTop._color, "patch line colour and alpha")
    eq(P.gapLine._layer, P.lineTop._layer, "patch line layer"); eq(P.gapLine._sub, P.lineTop._sub, "patch line sublevel")
    eq(P.gapHalo._texture, P.haloTop._texture, "patch halo texture")
    same(P.gapHalo._tc, P.haloTop._tc, "patch halo texcoord")
    same(P.gapHalo._vertex, P.haloTop._vertex, "patch halo tint")
    eq(P.gapHalo._layer, P.haloTop._layer, "patch halo layer"); eq(P.gapHalo._sub, P.haloTop._sub, "patch halo sublevel")
    -- patch + stubs tile the whole top line: no overlap (it would double the alpha), no hole
    local a, b = piece("lineTop"), piece("lineTop2")
    near(a.r, l.x, "left stub meets the patch"); near(l.r, b.x, "the patch meets the right piece")
    local ha, hb = piece("haloTop"), piece("haloTop2")
    near(ha.r, h.x, "left halo meets the patch halo"); near(h.r, hb.x, "the patch halo meets the right halo")
    sameParts(before, snapParts(), "unchanged by the patch")
end

function T.gap_patch_follows_the_effective_gap_the_key_count_and_a_rescale()
    local P = C().parts
    truthy(C().SetDockGap(-50, 100))
    near(piece("gapLine").x, M.CUT, "a gap hanging past the cut: the patch is clamped like the line")
    near(piece("gapLine").r, 100, "patch to x1")
    truthy(C().SetDockGap(100, C().layout.tx + 500))
    near(piece("gapLine").r, C().layout.tx, "a gap running past the foot: the patch stops at the foot")
    near(piece("gapHalo").r, C().layout.tx, "...halo too")
    for _, gap in ipairs({ { 200, 200 }, { 300, 100 }, { 0, M.CUT } }) do
        truthy(C().SetDockGap(gap[1], gap[2]))
        eq(P.gapLine:IsShown(), false, "no patch for an empty gap " .. gap[1])
        eq(P.gapHalo:IsShown(), false, "no patch halo for an empty gap " .. gap[1])
    end
    truthy(C().SetDockGap(100, 300))
    C().SetKeyCount(4)
    near(piece("gapLine").x, 100, "patch keeps x0 across a key count change"); near(piece("gapLine").r, 300, "...and x1")
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    near(piece("gapLine").x, 100, "patch keeps x0 across a rescale"); near(piece("gapLine").r, 300, "...and x1")
    near(piece("gapHalo").x, 100, "patch halo keeps x0"); near(piece("gapHalo").r, 300, "...and x1")
    truthy(C().SetDockGap(nil, nil))
    eq(P.gapLine:IsShown(), false, "the patch goes with the gap"); eq(P.gapHalo:IsShown(), false, "...halo too")
end

function T.gap_patch_alpha_is_legal_in_combat_and_survives_a_reseat()
    local P = C().parts
    eq(C().GetGapPatchAlpha(), 0, "the gap starts visibly open")
    truthy(C().SetDockGap(100, 300))
    near(P.gapLine._alpha, 0, "patch line alpha 0"); near(P.gapHalo._alpha, 0, "patch halo alpha 0")
    __combat = true
    local forbidden = {}
    for _, k in ipairs({ "gapLine", "gapHalo" }) do
        for _, m in ipairs({ "Show", "Hide", "SetPoint", "ClearAllPoints", "SetSize", "SetShown" }) do
            P[k][m] = function() forbidden[#forbidden + 1] = k .. ":" .. m end
        end
    end
    truthy(C().SetGapPatchAlpha(1), "accepted in combat")
    eq(#forbidden, 0, "no Show, Hide or SetPoint in combat: " .. table.concat(forbidden, ","))
    near(P.gapLine._alpha, 1, "patch line alpha 1 at once"); near(P.gapHalo._alpha, 1, "patch halo alpha 1 at once")
    eq(C().GetGapPatchAlpha(), 1)
    truthy(C().SetGapPatchAlpha(0), "and back")
    near(P.gapLine._alpha, 0, "patch line alpha 0 again")
    eq(#forbidden, 0, "still no restricted call")
    -- a combat call is not refused and not recorded as a gap change
    eq(C().SetDockGap(40, 90), false, "the gap itself is still refused in combat")
    __combat = false
    for _, k in ipairs({ "gapLine", "gapHalo" }) do
        for _, m in ipairs({ "Show", "Hide", "SetPoint", "ClearAllPoints", "SetSize", "SetShown" }) do P[k][m] = nil end
    end
    -- garbage is refused and changes nothing; numbers are clamped
    eq(C().SetGapPatchAlpha("1"), false, "a string is refused"); eq(C().SetGapPatchAlpha(nil), false, "nil is refused")
    eq(C().SetGapPatchAlpha(0 / 0), false, "NaN is refused")
    eq(C().GetGapPatchAlpha(), 0, "refused calls changed nothing")
    truthy(C().SetGapPatchAlpha(7)); eq(C().GetGapPatchAlpha(), 1, "clamped to 1")
    truthy(C().SetGapPatchAlpha(-3)); eq(C().GetGapPatchAlpha(), 0, "clamped to 0")
    -- the alpha is state: a reseat, a gap change and a redraw keep it
    truthy(C().SetGapPatchAlpha(1))
    C().SetKeyCount(5)
    near(P.gapLine._alpha, 1, "alpha kept across a key count change")
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    near(P.gapLine._alpha, 1, "alpha kept across a rescale"); near(P.gapHalo._alpha, 1, "...halo too")
    truthy(C().SetDockGap(120, 280))
    near(P.gapLine._alpha, 1, "alpha kept across a new gap")
    SlashCmdList.FSCONSOLE("off"); SlashCmdList.FSCONSOLE("on")
    near(P.gapLine._alpha, 1, "alpha kept across a redraw")
end

function T.gap_patch_alpha_set_before_the_chassis_exists_lands_on_the_first_draw()
    eq(C().root, nil, "nothing built yet")
    truthy(C().SetGapPatchAlpha(1), "stored before anything is built")
    truthy(C().SetDockGap(100, 300))
    SlashCmdList.FSCONSOLE("on")
    near(C().parts.gapLine._alpha, 1, "the stored alpha was seated by the first draw")
    near(C().parts.gapHalo._alpha, 1, "...halo too")
end

function T.dock_gap_halo_span_can_be_wider_than_the_line_span()
    -- SetDockGap(x0, x1, hx0, hx1): the optional last pair is the HALO's gap (the pet dock keeps the
    -- Console's glow off its own side glow, while the line runs under its sides); omitted or not two
    -- numbers, the halo gap is the line's.
    local P = C().parts
    truthy(C().SetDockGap(100, 300, 90, 310))
    near(piece("lineTop").r, 100, "line stub to x0"); near(piece("lineTop2").x, 300, "line piece from x1")
    near(piece("gapLine").x, 100, "patch line from x0"); near(piece("gapLine").r, 300, "patch line to x1")
    near(piece("haloTop").r, 90, "halo stub to hx0"); near(piece("haloTop2").x, 310, "halo piece from hx1")
    near(piece("gapHalo").x, 90, "patch halo from hx0"); near(piece("gapHalo").r, 310, "patch halo to hx1")
    near(C().layout.gap.x0, 100, "layout line gap x0"); near(C().layout.gap.x1, 300, "layout line gap x1")
    near(C().layout.haloGap.x0, 90, "layout halo gap x0"); near(C().layout.haloGap.x1, 310, "layout halo gap x1")
    -- the patch halo and the halo stubs tile with no overlap and no hole
    near(piece("haloTop").r, piece("gapHalo").x, "halo stub meets the patch halo")
    near(piece("gapHalo").r, piece("haloTop2").x, "patch halo meets the right halo")
    -- a change of the halo pair alone re-seats
    truthy(C().SetDockGap(100, 300, 80, 320))
    near(piece("haloTop").r, 80, "halo gap follows a change of the halo pair alone")
    near(piece("lineTop").r, 100, "...and the line stays")
    -- omitted or garbage: the halo follows the line
    for _, args in ipairs({ { 100, 300 }, { 100, 300, "a", "b" }, { 100, 300, 90 }, { 100, 300, 0 / 0, 310 } }) do
        truthy(C().SetDockGap(args[1], args[2], args[3], args[4]))
        near(piece("haloTop").r, 100, "halo stub = line stub for " .. tostring(args[3]))
        near(piece("haloTop2").x, 300, "halo piece = line piece for " .. tostring(args[3]))
        near(piece("gapHalo").x, 100); near(piece("gapHalo").r, 300)
    end
    -- clamped like the line
    local tx = C().layout.tx
    truthy(C().SetDockGap(100, 300, -50, tx + 500))
    eq(piece("haloTop"), nil, "the halo gap runs to the cut: no stub"); eq(piece("haloTop2"), nil, "...and to the foot: no right piece")
    near(piece("gapHalo").x, M.CUT, "patch halo from the cut"); near(piece("gapHalo").r, tx, "patch halo to the foot")
    near(piece("lineTop").r, 100, "the line gap is unaffected")
    -- survives a key count change and a rescale
    truthy(C().SetDockGap(100, 300, 90, 310))
    C().SetKeyCount(4)
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    near(piece("haloTop").r, 90, "halo gap kept"); near(piece("gapHalo").r, 310, "...patch halo too")
    -- refused in combat like the line gap
    __combat = true
    eq(C().SetDockGap(100, 300, 50, 350), false, "refused in combat")
    __combat = false
    near(piece("haloTop").r, 90, "nothing changed")
    truthy(C().SetDockGap(nil, nil))
    eq(C().layout.haloGap, nil, "cleared"); eq(P.gapHalo:IsShown(), false)
end

function T.dock_gap_nil_clears_it()
    local tx = C().layout.tx
    truthy(C().SetDockGap(100, 300))
    truthy(piece("lineTop2"), "gap is open")
    truthy(C().SetDockGap(nil, nil), "clear accepted out of combat")
    noGap(tx, "after the clear")
    -- anything that is not a pair of numbers clears too
    truthy(C().SetDockGap(100, 300))
    truthy(C().SetDockGap(100, nil)); noGap(tx, "a lone x0")
    truthy(C().SetDockGap(100, 300))
    truthy(C().SetDockGap("a", "b")); noGap(tx, "strings")
    truthy(C().SetDockGap(100, 300))
    truthy(C().SetDockGap(0 / 0, 300)); noGap(tx, "NaN")
end

function T.dock_gap_that_is_degenerate_or_outside_the_span_draws_nothing()
    local tx = C().layout.tx
    for _, gap in ipairs({ { 200, 200 }, { 300, 100 }, { -50, 5 }, { 0, M.CUT }, { tx, tx + 50 }, { tx + 10, tx + 50 },
                           { -50, -10 }, { 1e6, 2e6 } }) do
        truthy(C().SetDockGap(gap[1], gap[2]), "stored " .. gap[1] .. "," .. gap[2])
        noGap(tx, "gap " .. gap[1] .. "," .. gap[2])
    end
    -- a gap hanging past either end is clamped to the drawable span
    truthy(C().SetDockGap(-50, 100))
    eq(piece("lineTop"), nil, "no left stub when the gap starts at the cut")
    near(piece("lineTop2").x, 100, "right piece from x1"); near(piece("lineTop2").r, tx, "to the foot")
    eq(piece("haloTop"), nil, "no left halo piece either")
    truthy(C().SetDockGap(300, tx + 500))
    near(piece("lineTop").r, 300, "left stub to x0"); eq(piece("lineTop2"), nil, "no right piece when the gap runs to the foot")
    eq(piece("haloTop2"), nil, "no right halo piece either")
    -- the whole span: nothing of the top line is drawn
    truthy(C().SetDockGap(-50, tx + 500))
    eq(piece("lineTop"), nil, "the whole top line is the gap"); eq(piece("lineTop2"), nil, "the whole top line is the gap")
    eq(piece("haloTop"), nil, "the whole top halo is the gap"); eq(piece("haloTop2"), nil, "the whole top halo is the gap")
    -- and a piece that was hidden comes back when the gap closes again
    C().SetDockGap(nil, nil)
    noGap(tx, "after reopening the whole span")
end

function T.dock_gap_follows_the_key_count_and_a_rescale()
    truthy(C().SetDockGap(100, 300))
    C().SetKeyCount(4)
    local tx4 = C().layout.tx
    truthy(tx4 > 300, "the 4 key foot is still right of the gap")
    near(piece("lineTop").r, 100, "left stub keeps x0"); near(piece("lineTop2").x, 300, "right piece keeps x1")
    near(piece("lineTop2").r, tx4, "right piece follows the foot")
    -- a foot that moves left of x1 clamps the gap to it
    C().SetKeyCount(8)
    truthy(C().SetDockGap(100, C().layout.tx + 40))
    eq(piece("lineTop2"), nil, "gap runs to the foot at 8 keys")
    C().SetKeyCount(4)
    near(piece("lineTop2") and piece("lineTop2").r or -1, C().layout.tx, "...and the piece reappears when the foot moves right", 1e-6)
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    near(C().layout.gap.x0, 100, "gap survives a rescale in design px")
    near(piece("lineTop").r, 100, "left stub after the rescale")
end

function T.is_drawn_follows_the_chassis()
    eq(C().IsDrawn(), true, "drawn after the first seat")
    SlashCmdList.FSCONSOLE("off")
    eq(C().IsDrawn(), false, "not drawn while the Console is off")
    -- a gap set while nothing is drawn is stored, and lands on the next draw
    truthy(C().SetDockGap(100, 300), "stored while not drawn")
    SlashCmdList.FSCONSOLE("on")
    eq(C().IsDrawn(), true, "drawn again after on")
    near(piece("lineTop").r, 100, "the stored gap was seated by the next draw")
    near(piece("lineTop2").x, 300, "the stored gap was seated by the next draw")
end

function T.is_drawn_is_false_before_the_first_seat_and_a_stored_gap_lands_on_the_first_draw()
    eq(C().IsDrawn(), false, "nothing drawn: saved off")
    eq(C().root, nil, "no chassis was built")
    truthy(C().SetDockGap(100, 300), "stored before anything is built")
    SlashCmdList.FSCONSOLE("on")
    eq(C().IsDrawn(), true, "drawn after the first on")
    near(piece("lineTop").r, 100, "left stub to x0"); near(piece("lineTop2").x, 300, "right piece from x1")
    near(piece("haloTop").r, 100, "halo left piece to x0"); near(piece("haloTop2").x, 300, "halo right piece from x1")
end

-- ---- key gap rule -----------------------------------------------------------------------
function T.hud_key_bottom_sits_cn_vg_above_the_first_button_top()
    local s = S()
    local tab, area = rect(C().tab), C().keyArea
    local keyBottom = tab.t + (area.y + area.h)
    near(rect(btn(1, 1)).t - keyBottom, M.VG * s, "first button top - HUD key bottom = CN_VG")
    near(M.VG, 13.2, "CN_VG = 49.2 - 36", 1e-9)
    near(area.h, M.KEY_H * s, "key height"); near(area.w, (M.KEY_XL + M.KEY_W - M.KEY_X0) * s, "8 keys wide")
    near(area.x, (M.KEY_X0 - M.FOOT) * s, "first key x in the tab")
    near(M.TP, 15, "the keys keep 15 design px of padding to the tab edges", 1e-9)
    near(area.y, M.TP * s, "keys centred in the tab's top padding")
    near(tab.r - (tab.l + area.x + area.w), M.TP * s, "same padding to the right edge")
end

-- ---- fill -------------------------------------------------------------------------------
function T.fill_is_one_vertical_gradient_across_the_whole_chassis()
    local P = C().parts
    local _, H = chassisDesign()
    local function col(t) return t.r, t.g, t.b, t.a end
    local top, mid, bot = P.fillTop._gradient, P.fillMid._gradient, P.fillBottom._gradient
    eq(top.orientation, "VERTICAL", "vertical")
    -- SetGradient("VERTICAL", min, max): min is the BOTTOM colour
    near(top.to.r, 45 / 255, "chassis top r"); near(top.to.g, 27 / 255, "chassis top g")
    near(top.to.b, 78 / 255, "chassis top b"); near(top.to.a, .8, "chassis top a")
    near(bot.from.r, 11 / 255, "chassis bottom r"); near(bot.from.g, 6 / 255, "chassis bottom g")
    near(bot.from.b, 20 / 255, "chassis bottom b"); near(bot.from.a, .88, "chassis bottom a")
    -- no band: each piece starts on the colour the one above it ends on
    near(top.from.a, mid.to.a, "top/mid alpha continuity"); near(top.from.r, mid.to.r, "top/mid r continuity")
    near(mid.from.a, bot.to.a, "mid/bottom alpha continuity"); near(mid.from.b, bot.to.b, "mid/bottom b continuity")
    -- tiles without overlap: pieces stack to exactly the chassis height
    local a, b, c = D(P.fillTop), D(P.fillMid), D(P.fillBottom)
    near(a.b, b.y, "top meets mid"); near(b.b, c.y, "mid meets bottom"); near(c.b, H, "bottom ends at the chassis bottom")
    -- the two cut corners are the c14 fill's own corner blocks, no nine-slice (a gradient bands on one)
    for _, k in ipairs({ "fillTL", "fillBR" }) do
        eq(P[k]._texture, C().TEX.fill, k)
        near(D(P[k]).w, M.CUT, k .. " w"); near(D(P[k]).h, M.CUT, k .. " h")
        eq(P[k]._slice, nil, k .. " is not nine-sliced")
    end
    near(D(P.fillTL).x, 0, "TL corner at the left"); near(D(P.fillTL).y, 0, "TL corner at the top")
    local W = chassisDesign()
    near(D(P.fillBR).r, W, "BR corner at the right"); near(D(P.fillBR).b, H, "BR corner at the bottom")
    near(P.tabFill._color[4], .8, "tab fill is the top colour"); near(P.tabWedge._vertex[4], .8, "wedge is the top colour")
end

-- ---- inside -----------------------------------------------------------------------------
function T.row_pips_centre_in_the_left_margin()
    local R, s = chassis(), S()
    local pips = C().parts.pips
    eq(#pips, 3, "one pip per row")
    local rows = { btn(1, 1), btn(3, 1), btn(5, 1) }
    for r = 1, 3 do
        local p = rect(pips[r])
        near(p.w, 3 * s, "pip width"); near(p.h, rect(rows[r]).h, "pip is a button tall")
        near(p.t, rect(rows[r]).t, "pip aligned with its row")
        near(p.l - R.l, (M.PAD + M.MARG - 3) / 2 * s, "pip centred in the margin")
        near(rect(rows[r]).l - p.r, p.l - R.l, "equal space each side of the pip")
    end
    near(pips[1]._color[1], 1, "MAIN pip pink r"); near(pips[1]._color[4], .7, "MAIN pip alpha")
    near(pips[2]._color[4], .35, "other pips violet .35"); near(pips[3]._color[4], .35)
end

function T.spine_sits_on_the_stack_centre_with_a_chevron_at_each_end()
    local s = S()
    local stack = rect(FSActionBarStack)
    local spine = rect(C().parts.spine)
    near(spine.l + spine.w / 2, stack.l + stack.w / 2, "spine x = stack centre")
    near((rect(btn(1, 12)).r + rect(btn(2, 1)).l) / 2, stack.l + stack.w / 2, "stack centre is mid way between the halves")
    near(spine.t, rect(btn(1, 1)).t, "spine from the first row"); near(spine.b, rect(btn(5, 1)).b, "spine to the last row")
    near(C().parts.spine._color[4], .35, "spine alpha")
    local ch = C().parts.chevrons
    eq(#ch, 4, "two arms per end")
    local cx = stack.l + stack.w / 2
    for i = 1, 4 do
        local r = rect(ch[i])
        near(math.abs((r.l + r.w / 2) - cx), 1.6 * s, "arm centre 1.6 off the spine")
        near(ch[i]._color[4], .5, "chevron alpha")
        near(math.abs(ch[i]._rot), math.atan2(3.2, 3.4), "arm angle", 1e-6)
    end
    truthy(ch[1]._rot * ch[2]._rot < 0, "arms of one chevron lean opposite ways")
    -- the top chevron points up (its apex at the field top), the bottom one down
    local top = rect(btn(1, 1)).t
    near(rect(ch[1]).t + rect(ch[1]).h / 2 - top, 1.7 * s, "top arm midpoint 1.7 below the apex")
end

function T.row_hairlines_and_the_tick_ruler()
    local s = S()
    local P = C().parts
    local R = chassis()
    eq(#P.dividers, 2, "a divider between each pair of rows")
    for r = 1, 2 do
        local lo = rect(btn(r * 2 - 1, 1)).b
        local hi = rect(btn(r * 2 + 1, 1)).t
        local d = rect(P.dividers[r])
        near(d.t + d.h / 2, (lo + hi) / 2, "divider mid way down the row gap")
        near(d.l, rect(btn(1, 1)).l - M.ZX * s, "divider starts ZX outside the field")
        near(d.r, rect(btn(2, 12)).r + M.ZX * s, "divider ends ZX outside the field")
        near(P.dividers[r]._color[4], .18, "divider alpha")
    end
    eq(#P.ticks, 72, "a tick at every button centre of every row")
    for _, tk in ipairs(P.ticks) do
        local b = btn(tk.row * 2 - 2 + tk.half, tk.idx)
        local br, t = rect(b), rect(tk.tex)
        near(t.l + t.w / 2, br.l + br.w / 2, "tick on the button centre")
        near(t.t - br.b, 1.2 * s, "tick 1.2 under the button")
        near(t.h, (tk.idx % 4 == 0 and 4 or 2) * s, "every 4th tick is long")
        near(tk.tex._color[4], .25, "tick alpha")
    end
    truthy(R.w > 0)
end

function T.silkscreen_and_screws()
    local W, H = chassisDesign()
    local P = C().parts
    eq(P.main:GetText(), "MAIN"); eq(P.serial:GetText(), "FS-CNSL 06")
    near(P.main._mono.size, 8, "silkscreen 8 design px"); near(P.main._mono.color[4], .6, "MAIN alpha .6")
    near(P.serial._mono.color[4], .22, "serial alpha .22")
    near(D(P.main).x, M.PAD + M.MARG, "MAIN sits over the first button column")
    near(D(P.serial).x, 14, "serial after the BL screw")
    truthy(D(P.main).b < M.PT - M.ZT + 3, "MAIN lives in the top strip")
    truthy(D(P.serial).y > H - M.PB, "serial lives in the bottom strip")
    eq(#P.screws, 2, "two screws")
    local top = D(P.screws[1].disc)
    near(top.x + top.w / 2, W - 7.5, "top right screw x"); near(top.y + top.h / 2, -M.TH + 7.5, "top right screw y")
    local bl = D(P.screws[2].disc)
    near(bl.x + bl.w / 2, 7.5, "bottom left screw x"); near(bl.y + bl.h / 2, H - 7.5, "bottom left screw y")
    near(P.screws[1].disc._vertex[4], .5, "screw disc alpha")
end

function T.outline_and_halo_are_violet_at_the_mockup_alphas()
    local P = C().parts
    for _, k in ipairs({ "lineTop", "lineLeft", "lineBottom", "lineRight", "lineTabTop", "cornerTL", "cornerBR" }) do
        local c = P[k]._color or P[k]._vertex
        near(c[4], .72, k .. " outline alpha .72")
        near(c[1], 0.659, k .. " violet r", 1e-3)
    end
    near(P.foot._vertex[4], 1, "foot carries its own baked halo, alpha 1")
    eq(P.cornerTL._texture, C().TEX.outline, "outline corner texture")
    for _, k in ipairs({ "haloTL", "haloTop", "haloTabTop", "haloTR", "haloRight", "haloBR", "haloBottom", "haloBL", "haloLeft" }) do
        near(P[k]._vertex[4], 1, k .. " halo alpha")
    end
end

-- ---- pill chrome + spine gap --------------------------------------------------------------
local function chromeOf(i) return _G["FSActionBar" .. i].fsChrome end

function T.pill_chrome_hangs_off_a_hideable_child_and_hides_under_the_console()
    for i = 1, 6 do
        local header, chrome = _G["FSActionBar" .. i], chromeOf(i)
        truthy(chrome, "header " .. i .. " has a chrome child")
        eq(chrome:IsShown(), false, "pill chrome hidden while the Console is on")
        local textures = 0
        for _, r in ipairs(chrome._regions) do if r._kind == "Texture" then textures = textures + 1 end end
        truthy(textures >= 2, "fill and border textures live on the chrome child")
        for _, r in ipairs(header._regions) do
            if r._kind == "Texture" or r._kind == "FontString" then error("loose chrome on header " .. i) end
        end
    end
    local tag
    for _, r in ipairs(chromeOf(1)._regions) do if r._kind == "FontString" and r._text == "MAIN" then tag = r end end
    truthy(tag, "the MAIN tag lives on bar 1's chrome")
    for _, r in ipairs(chromeOf(2)._regions) do eq(r._kind == "FontString" and r._text == "MAIN", false, "only bar 1 is MAIN") end
end

function T.console_off_brings_the_pill_chrome_and_the_old_gap_back()
    local h1, h2 = _G.FSActionBar1, _G.FSActionBar2
    local gapOn = rect(h2).l - rect(h1).r
    near(gapOn, FS.ActionBars.SPINE_DESIGN * S(), "gap = CN_SPINE design px while on")
    near(FS.ActionBars.SPINE_DESIGN, M.SPINE, "CN_SPINE matches the mockup")
    SlashCmdList.FSCONSOLE("off")
    eq(ForeverSynthwaveDB.consoleEnabled, false, "saved")
    eq(C().IsActive(), false)
    eq(C().root:IsShown(), false, "Console hidden")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), true, "pill chrome back on bar " .. i) end
    near(rect(h2).l - rect(h1).r, 6, "the 6 unit pill gap is back")
    local stack = rect(FSActionBarStack)
    near((rect(h1).l + rect(h2).r) / 2, stack.l + stack.w / 2, "pills still centred in the stack")
    SlashCmdList.FSCONSOLE("on")
    eq(ForeverSynthwaveDB.consoleEnabled, true, "saved on")
    eq(C().root:IsShown(), true, "Console back")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), false, "pill chrome hidden again") end
    near(rect(h2).l - rect(h1).r, FS.ActionBars.SPINE_DESIGN * S(), "wide gap back")
    T.chassis_wraps_the_button_field_with_the_mockup_paddings()
end

-- Every button, header and the stack: its size and every anchor, by value (the anchor target by
-- identity). `/fsconsole off` has to hand the old pill layout back EXACTLY, not approximately.
local function snapshot()
    local snap = {}
    local function take(key, f)
        local entry = { w = f._w, h = f._h, points = {} }
        for i, p in ipairs(f._points) do
            entry.points[i] = { point = p.point, rel = p.rel, relPoint = p.relPoint, x = p.x, y = p.y }
        end
        snap[key] = entry
    end
    take("stack", FSActionBarStack)
    for i = 1, 6 do
        take("header" .. i, _G["FSActionBar" .. i])
        for j = 1, 12 do take(("button%d_%d"):format(i, j), btn(i, j)) end
    end
    return snap
end
local function sameSnapshot(a, b, label)
    local n = 0
    for key, was in pairs(a) do
        n = n + 1
        local now = b[key]
        truthy(now, label .. ": " .. key .. " vanished")
        eq(now.w, was.w, label .. ": " .. key .. " width")
        eq(now.h, was.h, label .. ": " .. key .. " height")
        eq(#now.points, #was.points, label .. ": " .. key .. " anchor count")
        for i, p in ipairs(was.points) do
            local q = now.points[i]
            local what = label .. ": " .. key .. " anchor " .. i
            eq(q.point, p.point, what .. " point")
            eq(q.rel, p.rel, what .. " target")
            eq(q.relPoint, p.relPoint, what .. " relPoint")
            eq(q.x, p.x, what .. " x")
            eq(q.y, p.y, what .. " y")
        end
    end
    eq(n, 1 + 6 + 72, "snapshot covers the stack, 6 headers and 72 buttons")
end

-- Runs from a start with the Console saved OFF, so the snapshot is the layout before the
-- Console ever existed (the variant of this name).
function T.console_off_restores_the_pill_layout_exactly()
    eq(FS.Console.root, nil, "baseline is taken before the Console is ever built")
    local baseline = snapshot()
    SlashCmdList.FSCONSOLE("on")
    truthy(FS.Console.root, "Console built by the first on")
    SlashCmdList.FSCONSOLE("off")
    sameSnapshot(baseline, snapshot(), "after on then off")
    -- and again after a rescale while on, restored to the same scale
    SlashCmdList.FSCONSOLE("on")
    local s0 = __scale
    __rescale(s0 == 1 and 1 / 1.2 or 1)
    __rescale(s0)
    SlashCmdList.FSCONSOLE("off")
    sameSnapshot(baseline, snapshot(), "after on, rescale, off")
end

function T.toggling_and_rescaling_do_not_grow_frames_or_regions()
    local s0 = __scale
    local base = #__frames
    __rescale(s0 == 1 and 1 / 1.2 or 1)
    eq(#__frames, base, "a rescale creates no frame or region")
    __rescale(s0)
    for cycle = 1, 3 do
        SlashCmdList.FSCONSOLE("off")
        SlashCmdList.FSCONSOLE("on")
        __rescale(cycle % 2 == 0 and s0 or (s0 == 1 and 1 / 1.2 or 1))
    end
    eq(#__frames, base, "off/on cycles and rescales create no frame or region")
end

-- A Build that throws partway must not run again on the next geometry (each run made a new
-- FSConsole frame and a new set of textures), and must tell the player once.
function T.a_failed_build_is_not_retried_and_is_logged_once()
    eq(__consoleFrames, 1, "Build ran once at login")
    eq(__degradeCount, 1, "one chat line for the failed build")
    truthy(__degraded.console_build, "logged under the build key")
    local base = #__frames
    for _ = 1, 3 do __rescale(__scale == 1 and 1 / 1.2 or 1) end
    SlashCmdList.FSCONSOLE("off")
    SlashCmdList.FSCONSOLE("on")
    eq(__consoleFrames, 1, "no second FSConsole frame")
    eq(#__frames, base, "no new frame or region after the failure")
    eq(__degradeCount, 1, "still one chat line")
    eq(FS.Console.root and FS.Console.root:IsShown(), false, "the half built chassis stays hidden")
end

-- Console on but its Build threw: ActionBars hides every pill's chrome while the console is on,
-- so without a fallback the bars would have no chrome at all. The fallback is a RUNTIME one:
-- it drops ActionBars' applied look back to the pills, never the saved /fsconsole choice, and
-- it runs a frame later, never inside the geometry callback (that re-enters SeatAll).
function T.a_failed_build_falls_back_to_pill_chrome_without_reentering_or_unsaving()
    eq(__consoleFrames, 1, "Build ran once at login and threw")
    eq(__geoMax, 1, "login seat ran its callback once, not nested")
    truthy(__timersQueued() <= 1, "one queued fallback timer after the build failure")
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    truthy(__timersQueued() <= 1, "a second failing pass in the same frame does not stack timers: " .. __timersQueued())
    __flush()
    eq(__geoMax, 1, "the fallback never re-entered the geometry callback")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "pill chrome back on bar " .. i) end
    near(rect(_G.FSActionBar2).l - rect(_G.FSActionBar1).r, 6, "the pill gap, not the wide spine")
    eq(ForeverSynthwaveDB.consoleEnabled, true, "the saved choice is untouched")
    eq(C().IsActive(), true, "the player's choice still reads on")
    eq(C().root and C().root:IsShown(), false, "the half built chassis stays hidden")
    -- switching off and on again lands on the same fallback instead of chrome-less pills
    SlashCmdList.FSCONSOLE("off")
    __say = nil
    SlashCmdList.FSCONSOLE("on")
    truthy(__say and __say:find("failed to draw", 1, true), "the player is told it failed to draw: " .. tostring(__say))
    __flush()
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "chrome after off/on, bar " .. i) end
    eq(ForeverSynthwaveDB.consoleEnabled, true, "still saved on")
    eq(__geoMax, 1, "still never nested")
    eq(__consoleFrames, 1, "and still no rebuild")
end

-- No C_Timer.After at all: the fallback cannot run, and that is logged once rather than silent.
function T.a_missing_timer_logs_the_skipped_fallback_once()
    truthy(__degraded.console_fallback_timer, "logged under the fallback_timer key")
    eq(__degradeCount, 2, "the build failure and the skipped fallback, one line each")
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    SlashCmdList.FSCONSOLE("off")
    SlashCmdList.FSCONSOLE("on")
    eq(__degradeCount, 2, "no repeat lines")
end

-- Same fallback with combat starting in the frame between the failure and the deferred call:
-- nothing protected moves until regen.
function T.a_failed_build_fallback_waits_for_combat_to_end()
    __combat = true; __blocked = 0
    __flush()
    eq(__blocked, 0, "no protected frame touched in combat")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), false, "chrome waits, bar " .. i) end
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    __flush()
    eq(__blocked, 0, "regen work is not blocked")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "chrome on bar " .. i .. " after regen") end
    eq(ForeverSynthwaveDB.consoleEnabled, true, "saved choice untouched")
    eq(__geoMax, 1, "never nested")
end

-- Seat throws (OnGeometry's Degrade("seat") path) with the chassis never shown: same bare pill
-- gap as a failed build, so it takes the same fallback. The fallback is for this session only;
-- the saved choice stays on.
function T.a_failed_seat_falls_back_to_pill_chrome_like_a_failed_build()
    eq(__degradeCount, 1, "one chat line for the failed seat")
    truthy(__degraded.console_seat, "logged under the seat key")
    eq(C().root:IsShown(), false, "the chassis never showed")
    eq(__geoMax, 1, "login seat ran its callback once, not nested")
    truthy(__timersQueued() <= 1, "one queued fallback timer after the seat failure")
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    truthy(__timersQueued() <= 1, "a second failing seat in the same frame does not stack timers: " .. __timersQueued())
    __flush()
    eq(__geoMax, 1, "the fallback never re-entered the geometry callback")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "pill chrome back on bar " .. i) end
    eq(ForeverSynthwaveDB.consoleEnabled, true, "the saved choice is untouched")
    eq(C().IsActive(), true, "the player's choice still reads on")
    eq(__degradeCount, 1, "still one chat line")
    SlashCmdList.FSCONSOLE("off")
    __say = nil
    SlashCmdList.FSCONSOLE("on")
    truthy(__say and __say:find("failed to draw", 1, true), "the player is told it failed to draw: " .. tostring(__say))
end

-- Once the seat works again, switching the console on lands on the chassis cleanly: deferred
-- SetConsoleActive, one geometry pass at a time, saved choice unchanged.
function T.a_failed_seat_recovers_when_the_next_seat_works()
    __flush()
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "fallback first, bar " .. i) end
    __seatBroken = false
    SlashCmdList.FSCONSOLE("on")
    __flush()
    eq(C().root:IsShown(), true, "the chassis is up")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), false, "pill chrome off again, bar " .. i) end
    eq(ForeverSynthwaveDB.consoleEnabled, true, "saved choice untouched")
    eq(__geoMax, 1, "never nested")
end

-- A seat that throws while the chassis is drawn leaves it up where it was (the bars are not
-- bare); the same failure once it has been switched off falls back, since nothing is on screen.
function T.a_failed_seat_falls_back_only_when_no_chassis_is_drawn()
    -- setup only (the recovery itself is asserted above): fall back, then get the chassis drawn
    __flush()
    __seatBroken = false
    SlashCmdList.FSCONSOLE("on")
    __flush()
    __seatBroken = true
    __rescale(__scale == 1 and 1 / 1.2 or 1)
    __flush()
    eq(C().root:IsShown(), true, "a seat failure while drawn leaves the chassis alone")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), false, "no fallback while drawn, bar " .. i) end
    SlashCmdList.FSCONSOLE("off")
    SlashCmdList.FSCONSOLE("on")
    __flush()
    eq(C().root:IsShown(), false, "nothing drawn after off then a failing on")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "fallback, bar " .. i) end
    eq(ForeverSynthwaveDB.consoleEnabled, true, "saved choice untouched")
    eq(__geoMax, 1, "never nested")
end

-- The message has to name the real reason a switch did not land.
function T.the_switch_message_names_combat_only_when_it_is_combat()
    __say = nil
    __combat = true
    SlashCmdList.FSCONSOLE("off")
    __combat = false
    truthy(__say, "the player is told something in combat")
    truthy(__say:find("switches when combat ends", 1, true), "combat names the wait: " .. tostring(__say))
    __say = nil
    FS.Layout.action = nil
    SlashCmdList.FSCONSOLE("off")
    truthy(__say, "the player is told something")
    eq(__say:find("combat", 1, true), nil, "not a combat message out of combat: " .. tostring(__say))
    truthy(__say:find("saved", 1, true), "still says the choice is saved")
end

function T.spine_gap_widens_the_stack_but_keeps_it_centred()
    local s = S()
    local size = btn(1, 1)._w
    local g = FS.ActionBars.geometry
    near(g.btnSize, size, "geometry btnSize")
    near(g.gap, 20 * s, "geometry gap")
    near(g.spineX, g.stackW / 2, "spine x is the stack's centre")
    local stack = rect(FSActionBarStack)
    near(stack.l + stack.w / 2, UIParent._w / 2 + (-7 * s), "stack centred on the layout anchor")
    near(g.fieldLeft, g.halfX[1] + g.btnX0, "field left"); near(g.fieldRight, g.halfX[2] + g.barW - g.btnX0, "field right")
    near(g.rowPitch, g.barH + 5, "row pitch"); near(g.btnPitch, g.btnSize + 7, "button pitch")
end

-- ---- the chassis fits beside the chat terminal ------------------------------------------------
-- The outer edge of the drawn Console (halo included) in DESIGN px, x centre-relative and y up
-- (the screen centre is the origin), read off the real halo pieces: left/right of the chassis,
-- top of the chassis halo, and the shoulder tab's own halo (its left is the foot texture).
function __outer_extent()
    local R, s = chassis(), S()
    local P = C().parts
    local cx, cy = UIParent._w / 2, UIParent._h / 2
    local function X(d) return (R.l + d * s - cx) / s end
    local function Y(d) return (cy - (R.t + d * s)) / s end
    return {
        left = X(D(P.haloLeft).x), right = X(D(P.haloRight).r),
        top = Y(D(P.haloTop).y), bottom = Y(D(P.haloBottom).b),
        tabLeft = X(D(P.foot).x), tabTop = Y(D(P.haloTabTop).y),
    }
end

function T.console_halo_stays_in_the_action_footprint_and_clear_of_the_chat()
    local L, e = FS.Layout.action, __outer_extent()
    -- These action rect checks are implied by the chat check today; matter only if CHAT_CLEARANCE or the chat edge moves.
    truthy(e.left >= L.x - L.w / 2 - EPS, "halo left " .. e.left .. " inside the action rect left " .. (L.x - L.w / 2))
    truthy(e.right <= L.x + L.w / 2 + EPS, "halo right " .. e.right .. " inside the action rect right " .. (L.x + L.w / 2))
    local want = FS.Layout.CHAT_CHROME_RIGHT + FS.Layout.CHAT_CLEARANCE
    truthy(e.left >= want - EPS, "halo left " .. e.left .. " is " .. FS.Layout.CHAT_CLEARANCE .. " clear of the chat chrome edge " .. FS.Layout.CHAT_CHROME_RIGHT)
    -- the stack stays where it was: centred on the layout anchor, vertically too
    local stack = rect(FSActionBarStack)
    near(stack.t + stack.h / 2, UIParent._h / 2 - L.y * S(), "stack centre y unchanged", 1e-6)
end

-- The pre-change numbers, pinned: Console OFF is the pill layout exactly as it was, and the
-- Console-on buttons are the size that fits the window above (a floor, not a free-for-all).
local PINNED = {   -- keyed by round(scale * 1000): off = { btn, stackW, stackH }, on = btn
    [1000] = { off = { 37, 1070, 149 }, on = 34 },
    [833]  = { off = { 30, 902, 128 }, on = 27 },
}
function T.console_off_geometry_is_unchanged_and_on_buttons_are_the_fitted_size()
    local pin = PINNED[math.floor(S() * 1000 + 0.5)]
    truthy(pin, "no pinned numbers for scale " .. S())
    local onBtn = FS.ActionBars.geometry.btnSize
    SlashCmdList.FSCONSOLE("off")
    local g = FS.ActionBars.geometry
    eq(g.btnSize, pin.off[1], "console-off button size")
    eq(g.stackW, pin.off[2], "console-off stack width")
    eq(g.stackH, pin.off[3], "console-off stack height")
    eq(onBtn, pin.on, "console-on button size")
end

function T.console_hides_with_the_stack_under_fsbars_blizz()
    SlashCmdList.FSBARS("blizz")
    eq(C().root:IsShown(), false, "Console follows the Blizzard fallback")
    SlashCmdList.FSBARS("fs")
    eq(C().root:IsShown(), true, "and comes back")
end

-- ---- combat -----------------------------------------------------------------------------
function T.nothing_protected_is_re_seated_shown_or_hidden_in_combat()
    __protect_stack()
    local before = { h = _G.FSActionBar2._points[1].x, w = btn(1, 1)._w, root = C().root._w, level = C().root:GetFrameLevel() }
    __combat = true
    __blocked = 0
    __scale = 0.9
    UIParent._w, UIParent._h = 2560 * 0.9, 1440 * 0.9
    __fire_rescale()
    SlashCmdList.FSCONSOLE("off")
    eq(__blocked, 0, "no protected frame touched in combat")
    eq(_G.FSActionBar2._points[1].x, before.h, "pills did not move")
    eq(btn(1, 1)._w, before.w, "buttons did not resize")
    eq(C().root._w, before.root, "Console did not re-seat")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), false, "chrome untouched in combat") end
    eq(ForeverSynthwaveDB.consoleEnabled, false, "the choice itself is saved at once")
    truthy(__say and __say:find("combat"), "the player is told it waits for combat")
    -- regen: both the rescale and the off switch land
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__blocked, 0, "regen work is not blocked")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), true, "chrome back after combat") end
    eq(C().root:IsShown(), false, "Console hidden after combat")
    near(rect(_G.FSActionBar2).l - rect(_G.FSActionBar1).r, 6, "old gap after combat")
end

function T.console_back_on_in_combat_waits_then_lands()
    SlashCmdList.FSCONSOLE("off")
    __protect_stack()
    __combat = true; __blocked = 0
    SlashCmdList.FSCONSOLE("on")
    eq(__blocked, 0, "nothing blocked")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), true, "still the pill look mid fight") end
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    for i = 1, 6 do eq(chromeOf(i):IsShown(), false, "Console look after combat") end
    eq(C().root:IsShown(), true)
    T.chassis_wraps_the_button_field_with_the_mockup_paddings()
end

function T.console_starts_off_when_saved_off()
    eq(FS.Console.IsActive(), false, "saved off is respected")
    eq(FS.Console.root, nil, "no Console frame was ever built")
    for i = 1, 6 do eq(_G["FSActionBar" .. i].fsChrome:IsShown(), true, "pill chrome on bar " .. i) end
    eq(_G.FSActionBar2._points[1].x - (_G.FSActionBar1._points[1].x + _G.FSActionBar1._w), 6, "narrow gap")
end

function T.console_constants_match_the_mockup()
    local c = FS.Console.C
    for _, k in ipairs({ "PAD", "MARG", "PT", "PB", "CUT", "ZX", "ZT", "ZY", "SR", "VG", "KB", "TP", "TH", "FOOT" }) do
        near(c[k], M[k], "Console.C." .. k .. " vs the mockup", 1e-9)
    end
    near(FS.ActionBars.SPINE_DESIGN, M.SPINE, "CN_SPINE", 1e-9)
    local key = FS.Console.KEY
    near(key.W, M.KEY_W); near(key.H, M.KEY_H); near(key.GAP, M.KEY_GAP); eq(key.GG, nil, "no group gap: the key pitch is even")
    near(FS.Console.TabWidth(M.DECK_N), M.TAB_DW, "TabWidth at the mockup's key count is its TAB_DW", 1e-9)
    near(key.PAD, M.KEY_PAD); near(key.SH, M.KEY_SH)
    near(FS.Console.KeyRect(0, 1).x, M.KEY_X0 - M.FOOT, "first key x in the tab (scale 1)")
    near(FS.Console.KeyRect(7, 1).x, M.KEY_XL - M.FOOT, "eighth key x in the tab (scale 1)")
    near(FS.Console.KEY.COUNT, M.DECK_N, "the console carries the mockup's key count at most")
end

__checks = T
"""


# A Console whose Build throws (the tab frame), a manual C_Timer (nothing runs until __flush), and a
# depth counter on every OnGeometry subscriber so a nested SeatAll shows up as __geoMax > 1.
FALLBACK_TIMERS_AND_DEPTH = """
    local timers = {}
    C_Timer = { After = function(_, fn) timers[#timers + 1] = fn end }
    function __timersQueued() return #timers end
    function __flush()
        for _ = 1, 10 do
            local run = timers
            timers = {}
            if #run == 0 then return end
            for _, fn in ipairs(run) do fn() end
        end
    end
    __geoDepth, __geoMax = 0, 0
    setmetatable(FS, { __newindex = function(t, k, v)
        rawset(t, k, v)
        if k ~= "ActionBars" then return end
        setmetatable(v, { __newindex = function(ab, name, fn)
            if name == "OnGeometry" then
                local orig = fn
                fn = function(cb)
                    return orig(function(g)
                        __geoDepth = __geoDepth + 1
                        if __geoDepth > __geoMax then __geoMax = __geoDepth end
                        local ok, err = pcall(cb, g)
                        __geoDepth = __geoDepth - 1
                        if not ok then error(err, 0) end
                    end)
                end
            end
            rawset(ab, name, fn)
        end })
    end })
"""

FAILED_BUILD_FALLBACK = """
    ForeverSynthwaveDB = { consoleEnabled = true }
    local realCreateFrame = CreateFrame
    __consoleFrames = 0
    CreateFrame = function(kind, name, ...)
        if name == "FSConsole" then __consoleFrames = __consoleFrames + 1 end
        if name == "FSConsoleTab" then error("boom") end
        return realCreateFrame(kind, name, ...)
    end
""" + FALLBACK_TIMERS_AND_DEPTH

# Build works but Seat throws while __seatBroken (the root's SetPoint is what Seat calls first).
FAILED_SEAT_FALLBACK = """
    ForeverSynthwaveDB = { consoleEnabled = true }
    __seatBroken = true
    local realCreateFrame = CreateFrame
    CreateFrame = function(kind, name, ...)
        local f = realCreateFrame(kind, name, ...)
        if name == "FSConsole" then
            f.SetPoint = function(self, ...)
                if __seatBroken then error("seat boom") end
                return __Region.SetPoint(self, ...)
            end
        end
        return f
    end
""" + FALLBACK_TIMERS_AND_DEPTH

# Checks that need a different start: name -> Lua run before the addon loads. They run ONLY on
# that start; every other check runs on the default one (Console on, nothing saved).
VARIANTS = {
    "console_starts_off_when_saved_off": "ForeverSynthwaveDB = { consoleEnabled = false }",
    "is_drawn_is_false_before_the_first_seat_and_a_stored_gap_lands_on_the_first_draw": "ForeverSynthwaveDB = { consoleEnabled = false }",
    "gap_patch_alpha_set_before_the_chassis_exists_lands_on_the_first_draw": "ForeverSynthwaveDB = { consoleEnabled = false }",
    "console_off_restores_the_pill_layout_exactly": "ForeverSynthwaveDB = { consoleEnabled = false }",
    "a_failed_build_falls_back_to_pill_chrome_without_reentering_or_unsaving": FAILED_BUILD_FALLBACK,
    "a_failed_build_fallback_waits_for_combat_to_end": FAILED_BUILD_FALLBACK,
    "a_missing_timer_logs_the_skipped_fallback_once": """
        C_Timer = nil
        local realCreateFrame = CreateFrame
        CreateFrame = function(kind, name, ...)
            if name == "FSConsoleTab" then error("boom") end
            return realCreateFrame(kind, name, ...)
        end
    """,
    "a_failed_seat_falls_back_to_pill_chrome_like_a_failed_build": FAILED_SEAT_FALLBACK,
    "a_failed_seat_recovers_when_the_next_seat_works": FAILED_SEAT_FALLBACK,
    "a_failed_seat_falls_back_only_when_no_chassis_is_drawn": FAILED_SEAT_FALLBACK,
    "a_failed_build_is_not_retried_and_is_logged_once": """
        local realCreateFrame = CreateFrame
        __consoleFrames = 0
        CreateFrame = function(kind, name, ...)
            if name == "FSConsole" then __consoleFrames = __consoleFrames + 1 end
            if name == "FSConsoleTab" then error("boom") end
            return realCreateFrame(kind, name, ...)
        end
    """ + FALLBACK_TIMERS_AND_DEPTH,  # a timer exists, so only the build failure is logged
}

# Checks that do not run per scale (static, file based).
def static_checks(mu: dict) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        out.append(("toc_places_console_right_after_actionbars",
                    None if toc.index("Console.lua") == toc.index("ActionBars.lua") + 1
                    else "Console.lua must load right after ActionBars.lua"))
    except ValueError as e:
        out.append(("toc_places_console_right_after_actionbars", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_keeps_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "toc has bare LF lines"))
    missing = [n for n in ("console_fill_c14.tga", "console_outline_c14.tga", "console_glow_c14.tga",
                           "console_tab_foot.tga", "tab_slant.tga", "glow_round.tga")
               if not (ADDON / "media" / n).exists()]
    out.append(("console_media_exists", None if not missing else f"missing {missing}"))
    out.append(("console_lua_exists", None if CONSOLE.exists() else "Console.lua does not exist"))
    lay = layout_constants()
    for sc in SCALES:
        implied = chat_edge_implied_by_the_code(sc)
        # Sanity floor check: asserts CHAT_CHROME_RIGHT is never left of the code-implied edge (~-568),
        # leaving 19px unexplained, so only fires if the chat outset grows significantly. The real guard
        # is re-measuring from a live screenshot when the chat chrome changes.
        out.append((f"chat_chrome_edge_is_not_left_of_what_the_chat_code_implies @scale={sc:.4f}",
                    None if lay["CHAT_CHROME_RIGHT"] >= implied
                    else f"CHAT_CHROME_RIGHT {lay['CHAT_CHROME_RIGHT']} is left of the {implied:.1f} the code implies"))
    ok_slash = "SLASH_FSCONSOLE1" in (Path(__file__).resolve().parent.parent / ".luacheckrc").read_text(encoding="utf-8")
    out.append(("luacheckrc_declares_the_slash_global", None if ok_slash else "SLASH_FSCONSOLE1 missing from .luacheckrc"))
    return out


def outer_extent(scale: float) -> dict:
    """The Console's outer edge, halo included, at `scale` (design px, x centre-relative, y up):
    left, right, top, bottom, tabLeft, tabTop. petframe-harness.py seats the pet panel from it."""
    mu = mockup_constants()
    lua = abh.boot(make_prelude(scale, ""), extra=("Console.lua",))
    lua.globals().__M = lua.table_from(mu)
    lua.execute(CHECKS)
    e = lua.eval("__outer_extent")()
    return {k: e[k] for k in ("left", "right", "top", "bottom", "tabLeft", "tabTop")}


def run_check(name: str, scale: float, mu: dict) -> str | None:
    db = VARIANTS.get(name, "")
    prelude = make_prelude(scale, db)
    # boot() runs the prelude BEFORE the addon files and __login() last
    lua = abh.boot(prelude, extra=("Console.lua",))
    lua.globals().__M = lua.table_from(mu)
    lua.execute(CHECKS)
    try:
        lua.eval("__checks")[name]()
    except LuaError as err:
        return str(err)
    return None


def main() -> int:
    mu = mockup_constants()
    failed = 0

    def report(label: str, err: str | None) -> None:
        nonlocal failed
        if err is None:
            print(f"ok    {label}")
        else:
            failed += 1
            print(f"FAIL  {label}\n      " + err.replace("\n", "\n      "))

    total = 0
    statics = static_checks(mu)
    for name, err in statics:
        total += 1
        report(name, err)

    if not CONSOLE.exists():
        print(f"\n{failed} failed (Console.lua is missing)")
        return 1

    # the check names are read from a scratch boot, so a missing module fails per check
    probe = abh.boot(make_prelude(SCALES[0], ""), extra=("Console.lua",))
    probe.globals().__M = probe.table_from(mu)
    probe.execute(CHECKS)
    names = sorted(k for k in probe.eval("__checks").keys())
    for name in names:
        for scale in SCALES:
            total += 1
            label = f"{name} @scale={scale:.4f}"
            try:
                report(label, run_check(name, scale, mu))
            except LuaError as err:  # a boot failure is a harness or module error, not a pass
                report(label, f"boot error: {err}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
