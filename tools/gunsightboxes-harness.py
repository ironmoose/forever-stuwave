#!/usr/bin/env python3
"""Runs the real GunsightBoxes.lua (the two cast info boxes of the Gunsight HUD) headless against a mock WoW API.

GunsightBoxes.lua is the info boxes of mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html
(infoBox and castIcon, drawn by drawYour on BOXL and drawTarget on BOXR). It builds the box chrome and the
members the CAST STATE MACHINE writes to (icon, name, timer, tick counter), and GunsightTape.lua hands them to
CastBars.lua inside the two tape bar tables, so the boxes are driven by the existing paths and nothing here
reads a cast. This harness reuses the gunsighttape-harness world (REAL CastBars.lua, ChevronCastBar.lua,
Layout.lua, Gunsight.lua and GunsightTape.lua; Theme's constants are read from Theme.lua and its helpers are
the castbars-harness stubs) and adds the real GunsightBoxes.lua. It pins:

  * constants: box chamfer, fill, padding, the two text lines, divider, header, icon tile, crop and idle alpha
    are parsed back out of the mockup, so a mockup edit fails here;
  * seats: both boxes fill boxL / boxR, the icon tile sits on the inner side, text and header sit at the
    mockup offsets, at two UI heights, and a rescale re-seats in place and builds nothing;
  * pieces: the boxes are children of the tape piece frames, so `you` / `tgt` off hides them;
  * the player box: spell name in capitals on line 1, the "0.9 / 2.5" timer on line 2 as CastBars formats it,
    the icon, the channel tick counter and CUT in the header row, the idle look (blank: no spell name, no timer);
  * the target box: unit name on line 1, the spell on line 2 (pink or steel with the interruptible flag, never
    a timer), the icon tile only while a cast is live, the same flag colouring the box edge;
  * secrets: a secret spell name, unit name and flag reach only SetText / SetAlphaFromBoolean sinks: no secret
    is compared, measured, upper-cased or concatenated, and no pcall swallowed one;
  * fonts: the mock throws "Font not set" for a write to a FontString without a font, so a box that builds wrote
    nothing early; the unit-name listener is second to last and the rescale registration last; a rescale re-fits
    a long name; the idle tile is gray;
  * INTERRUPTED: CastBars' onVerdict hook shows the red tone, "INTERRUPTED" and a flicker group, the next
    write or cast clears them, Stack A bars never have a hook;
  * target bar settings (FS.Config keys under gunsight.targetBars.*, defaults and ranges read from
    mockups/config-window-2026-10-07.html): the defaults draw exactly the option B rails, a change applies
    live to the heights, width and numbers and survives a rescale and a profile switch, a protected
    frame defers the change to PLAYER_REGEN_ENABLED, and the numbers (current, current / max, percent) go only
    to SetFormattedText with a secret health or power value, percent through the engine's UnitHealthPercent /
    UnitPowerPercent and never through arithmetic on a secret;
  * degrade: a failed build falls back to the alpha 0 text sinks of the tape and never stops the tape; a tape
    that fails after its box built retires the box (no listener, no layout or name write afterwards).

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the real client.

    python3 tools/gunsightboxes-harness.py

Exit 0 = every check passed. GUNSIGHTBOXES_LUA=<path> runs another file in place of GunsightBoxes.lua.
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
ADDON = HERE.parent / "forever-stuwave"
BOXES = Path(os.environ.get("GUNSIGHTBOXES_LUA") or ADDON / "Modules/CombatHud/GunsightBoxes.lua")
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
CONFIG_MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "config-window-2026-10-07.html"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TH = _load("gunsighttape_harness", "gunsighttape-harness.py")
CB, CHEV = TH.CB, TH.CHEV


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_config() -> dict:
    """The target bar controls of the config window mockup: readout defaults, track positions, format options."""
    src = CONFIG_MOCKUP.read_text(encoding="utf-8")

    def slider(label: str) -> tuple[int, int]:
        m = _m(r'<div class="lab">' + re.escape(label) + r'(?:<span class="q"[^>]*>\?</span>)?</div>'
               r'<div class="sl" style="--p:(\d+)%"><i></i><b></b></div><span class="rd">(\d+)', src, label + " slider")
        return int(m.group(2)), int(m.group(1))

    health, resource, width = slider("Health bar height"), slider("Resource bar height"), slider("Bar width")
    seg = _m(r'<div class="lab">Number format</div>\s*<div class="seg">(.*?)</div></div>', src, "Number format").group(1)
    options = re.findall(r'<span class="btn( on)?"><b>([^<]*)</b></span>', seg)
    return dict(
        HEALTH=health[0], HEALTH_P=health[1], RESOURCE=resource[0], RESOURCE_P=resource[1], WIDTH=width[0], WIDTH_P=width[1],
        FORMAT_OPTIONS=[o[1] for o in options], FORMAT_SELECTED=[o[1] for o in options if o[0]][0],
    )


def mockup_boxes() -> dict:
    """Everything infoBox, castIcon and the header of drawYour / drawTarget own, read out of the mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    chamfer, fill_a = _m(r"chamfer\(b\.x,b\.y,b\.w,b\.h,(\d+)\);\s*A\((\.\d+)\);ctx\.fillStyle=", src, "box chamfer and fill alpha").groups()
    fill = _m(r"A\(\.82\);ctx\.fillStyle='rgba\((\d+),(\d+),(\d+),(\.\d+)\)'", src, "box fill colour").groups()
    l1_size, wmax_pad = _m(r"var fs=o\.fs1\|\|(\d+),wmax=b\.w-(\d+);", src, "line 1 size and width").groups()
    l1_x, l1_y = _m(r"text\(l1,b\.x\+(\d+),b\.y\+(\d+),fs,o\.c1\|\|K\.white,a,'left'\)", src, "line 1 seat").groups()
    div_y, div_a = _m(r"hline\(b\.y\+(\d+),b\.x\+7,b\.x\+b\.w-7,o\.stroke\|\|col,(\.\d+)\*a\)", src, "divider").groups()
    l2_size = _m(r"var f2=o\.fs2\|\|(\d+);", src, "line 2 size (yours; the target passes fs2)").group(1)
    tgt_fs1, tgt_fs2 = _m(r"infoBox\(BR,col,'KURAK',spell,\{[^}]*?fs1:(\d+),fs2:(\d+),", src, "target infoBox call").groups()
    grow_y, grow_h = _m(r"if\(TBS==='b'\)return \{x:BOXR\.x,y:BOXR\.y-(\d+),w:BOXR\.w,h:BOXR\.h\+(\d+)\};", src, "option B box rect").groups()
    tb_min, tb_x, tb_y, tb_hp_h, tb_pw_dy, tb_pw_h = _m(
        r"w=Math\.max\((\d+),nameW\);x=BR\.x\+(\d+);y=BR\.y\+(\d+);\s*tbBarH\(x,y,w,(\d+),s\.hp,hc\);\s*"
        r"if\(pc\)tbBarH\(x,y\+(\d+),w,(\d+),s\.pw,pc\);", src, "option B bar rects").groups()
    tb_track = _m(r"A\(1\);ctx\.fillStyle=rgba\(col,(\.\d+)\);ctx\.fillRect\(x,y,w,h\);", src, "bar track alpha").group(1)
    tb_tail, tb_tip_end = _m(r"createLinearGradient\(x,0,x\+fw,0\);g\.addColorStop\(0,rgba\(col,(\.\d+)\)\);g\.addColorStop\(1,rgba\(col,(\d+)\)\);",
                             src, "bar fill gradient").groups()
    tb_tip_a, tb_tip_mix, tb_tip_w = _m(r"A\((\.\d+)\);ctx\.fillStyle=mix\(col,'#ffffff',(\.\d+)\);ctx\.fillRect\(x\+fw-([\d.]+),y,[\d.]+,h\);",
                                   src, "bar tip").groups()
    tb_low, tb_hp = _m(r"var TB_LOW=(\.\d+),TB_HP='(#[0-9a-fA-F]{6})';", src, "TB_LOW and TB_HP").groups()
    tb_mana, tb_rage, tb_focus = _m(r"var TB_PC=\{mana:'(#[0-9a-fA-F]{6})',rage:'(#[0-9a-fA-F]{6})',energy:K\.gold,focus:'(#[0-9a-fA-F]{6})'\};",
                                    src, "TB_PC").groups()
    party = (ADDON / "Modules/UnitFrames/PartyFrames.lua").read_text(encoding="utf-8")
    low_eps = _m(r"LOW_HP_EPSILON\s*=\s*([\d.]+)", party, "PartyFrames LOW_HP_EPSILON").group(1)
    l2_x, l2_y = _m(r"text\(l2,b\.x\+(\d+),b\.y\+(\d+),f2,o\.c2\|\|col,a,'left'\)", src, "line 2 seat").groups()
    head_size = _m(r"text\(s,x,y,(\d+),col,a,align\|\|'left'\);", src, "header size").group(1)
    head_dy, head_a = _m(r"header\('YOU',BOXL\.x,BOXL\.y-(\d+),K\.cyan,(\.\d+)\);", src, "header seat").groups()
    ci, cic, cig = _m(r"var CI=(\d+),CIC=(\d+),CIG=(\d+),", src, "icon tile").groups()
    ci_fill = _m(r"A\(\.85\*a\);ctx\.fillStyle='rgba\(13,6,32,(\.\d+)\)'", src, "icon plate fill").group(1)
    ci_stroke = _m(r"A\((\.\d+)\*a\);ctx\.strokeStyle=k\?col:K\.muted", src, "icon stroke alpha").group(1)
    ci_back = _m(r"A\((\.\d+)\*a\);ctx\.fillStyle='rgba\(13,6,32,\.9\)'", src, "icon plate alpha").group(1)
    crop = _m(r"ICON_CROP=(\.\d+)", src, "icon crop").group(1)
    idle_a = _m(r"castIcon\(BOXL\.x\+BOXL\.w\+CIG,BOXL\.y\+\(BOXL\.h-CI\)/2,CST_K\[CLS\],bc,\((idle\?)(\.\d+):1\)\*flick", src, "idle icon alpha").group(2)
    _m(r"castIcon\(BOXR\.x-CIG-CI,BOXR\.y\+\(BOXR\.h-CI\)/2,", src, "target icon seat")
    flick = _m(r"flick=\[([\d.,]+)\]\[Math\.min\(6,Math\.floor\(\(st\.tau-\.2\)/\.35\*7\)\)\]", src, "outage flicker steps").group(1)
    css = {k: v.lower() for k, v in re.findall(r"^\s*--(white|muted|cyan|pink|steel|red|gold):(#[0-9a-fA-F]{6});", src, re.M)}
    for need in ("white", "muted", "cyan", "pink", "steel", "red", "gold"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")
    return dict(
        CFG=mockup_config(),
        base=TH.GS.mockup_constants(), CHAMFER=int(chamfer), FILL=[int(fill[0]), int(fill[1]), int(fill[2]), float(fill[3])],
        FILL_A=float(fill_a), L1_SIZE=int(l1_size), PAD=int(l1_x), WMAX_PAD=int(wmax_pad), L1_Y=int(l1_y),
        DIV_Y=int(div_y), DIV_A=float(div_a), L2_SIZE=int(l2_size), L2_X=int(l2_x), L2_Y=int(l2_y),
        HEAD_SIZE=int(head_size), HEAD_DY=int(head_dy), HEAD_A=float(head_a),
        CI=int(ci), CIC=int(cic), CIG=int(cig), CI_FILL=float(ci_fill) * float(ci_back), CI_STROKE=float(ci_stroke),
        ICON_CROP=float(crop), IDLE_ICON_A=float(idle_a), CSS=css,
        FLICK=[float(x) for x in flick.split(",")],
        TGT_L1_SIZE=int(tgt_fs1), TGT_L2_SIZE=int(tgt_fs2), TB_GROW=int(grow_y), TB_GROW_H=int(grow_h),
        TB_MIN_W=int(tb_min), TB_X=int(tb_x), TB_HP_Y=int(tb_y), TB_HP_H=int(tb_hp_h), TB_PW_Y=int(tb_y) + int(tb_pw_dy), TB_PW_H=int(tb_pw_h),
        TB_TRACK_A=float(tb_track), TB_TAIL_A=float(tb_tail), TB_TIP_END=int(tb_tip_end), TB_TIP_A=float(tb_tip_a),
        TB_TIP_MIX=float(tb_tip_mix), TB_TIP_W=float(tb_tip_w), TB_LOW=float(tb_low), TB_HP_HEX=tb_hp.lower(),
        TB_PC={"mana": tb_mana.lower(), "rage": tb_rage.lower(), "focus": tb_focus.lower()}, LOW_EPS=float(low_eps),
    )


EXTRA_MOCK = r"""
-- Every failed pcall is recorded: a secret operation swallowed by a pcall must not go unnoticed.
local realPcall = pcall
local function pack(...) return { n = select("#", ...), ... } end
__pcallFails = {}
function pcall(f, ...)
    local r = pack(realPcall(f, ...))
    if not r[1] then __pcallFails[#__pcallFails + 1] = tostring(r[2]) end
    return unpack(r, 1, r.n)
end
local Region = getmetatable(UIParent)
-- Text width scales with the font size, like the client's: 6 units a character at size 11.
function Region:GetStringWidth()
    if rawequal(self._text, __SECRET_NAME) then error("measured a secret string") end
    if __charW == "throw" then error("cannot measure") end
    return #tostring(self._text) * (__charW or 6) * ((self._fontSize or 11) / 11)
end
function Region:SetJustifyV(j) self._justifyV = j end
function Region:SetMaxLines(n) self._maxLines = n end
function Region:SetNonSpaceWrap(v) self._nonSpaceWrap = v end
function Region:SetDesaturated(v) self._desat = v end
function Region:SetSnapToPixelGrid(v) self._snap = v end
function Region:SetTexelSnappingBias(v) self._bias = v end
function UnitName(u) return __units[u].name end
-- Target bars: plain unit stats by default, a hidden health fraction the Step curve is evaluated at (the
-- engine's UnitHealthPercent), and the gradient / colour API of a Texture. __curveRefuses makes the curve throw.
__units.target.hp, __units.target.hpMax, __units.target.pw, __units.target.pwMax = 62, 100, 70, 100
__units.target.ptype, __units.target.pct = 0, 0.62
function UnitHealth(u) return __units[u].hp end
function UnitHealthMax(u) return __units[u].hpMax end
function UnitPower(u) return __units[u].pw end
function UnitPowerMax(u) return __units[u].pwMax end
function UnitPowerType(u) return __units[u].ptype, "TOKEN" end
__curves = {}
-- FrameHelpers.UpdatePowerHostEmpty is the real helper's contract: alpha 0 at an empty power bar, 1 above
-- (the real one evaluates a Step curve engine-side; here the plain power stands in for the hidden fraction).
-- __emptyCalls records the hosts it was handed; __noEmptyHelper removes it.
__emptyCalls = {}
FS.FrameHelpers.UpdatePowerHostEmpty = function(host, unit)
    __emptyCalls[#__emptyCalls + 1] = { host = host, unit = unit }
    host:SetAlpha(__units[unit].pw == 0 and 0 or 1)
end
C_CurveUtil = { CreateCurve = function()
    local c = { pts = {} }
    function c:SetType(t) self.type = t end
    function c:AddPoint(x, y) self.pts[#self.pts + 1] = { x, y } end
    __curves[#__curves + 1] = c
    return c
end }
Enum = Enum or {}
Enum.LuaCurveType = { Step = 1, Linear = 0 }
-- The engine evaluates a curve at the hidden fraction: Step holds the last point at or below it, Linear
-- interpolates between the points around it.
local function evalCurve(curve, x)
    local y
    if curve.type == Enum.LuaCurveType.Linear then
        local lo, hi
        for _, p in ipairs(curve.pts) do
            if p[1] <= x then lo = p end
            if p[1] >= x and not hi then hi = p end
        end
        if lo and hi and hi[1] ~= lo[1] then return lo[2] + (hi[2] - lo[2]) * (x - lo[1]) / (hi[1] - lo[1]) end
        return (lo or hi)[2]
    end
    for _, p in ipairs(curve.pts) do if p[1] <= x then y = p[2] end end
    return y
end
__units.target.pwPct = 0.70
function UnitHealthPercent(u, predicted, curve)
    if __curveRefuses then error("curve refused") end
    __curveCalls = (__curveCalls or 0) + 1
    local y = evalCurve(curve, __units[u].pct)
    if __curveSecret then return __SECRET end
    return y
end
-- UnitPowerPercent(unit, powerType, usePredicted, curve), as FrameHelpers calls it.
function UnitPowerPercent(u, powerType, predicted, curve)
    if __powerCurveRefuses then error("power curve refused") end
    __powerCurveCalls = (__powerCurveCalls or 0) + 1
    local y = evalCurve(curve, __units[u].pwPct)
    if __curveSecret then return __SECRET end
    return y
end
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a } end
function Region:SetGradient(orientation, c1, c2)
    if __noGradientCall then error("SetGradient refused") end
    self._gradient = { orientation, c1, c2 }
end
-- Fires a unit event at every frame that registered it with RegisterUnitEvent (or plain RegisterEvent).
function __fireUnit(event, unit)
    local frames = {}
    for _, f in ipairs(__all) do
        if (f._unitEvents and f._unitEvents[event]) or (f._events and f._events[event]) then frames[#frames + 1] = f end
    end
    for _, f in ipairs(frames) do
        local fn = f._scripts.OnEvent
        if fn then fn(f, event, unit) end
    end
end
"""

CHECKS_BODY = r"""
local function rgb(c) return string.format("%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)) end
local function colourOf(fs)
    local c = fs._textColor or fs._monoColor
    return c and rgb(c) or nil
end
local function K() return 1.28 * FS.Layout.Scale() end
local function fontFor(imgPx) return math.max(6, math.floor(imgPx * K() + 0.5)) end
local function noFails(msg)
    if #__pcallFails > 0 then error((msg or "a pcall failed") .. ": " .. __pcallFails[1], 2) end
end
local function target(name) __units.target.name = name; __fireEvent("PLAYER_TARGET_CHANGED") end
local function channel(unit, name, t0, secs)
    __now = t0
    __units[unit].chan = { name = name, tex = "icon", startMS = t0 * 1000, endMS = (t0 + secs) * 1000, notInt = false }
    __units[unit].cast = nil
end
local function secretUnit() __units.target.name = __SECRET_NAME end

-- ---- constants --------------------------------------------------------------------

-- The target box draws no TARGET label: no FontString anywhere under its frame (the tone copies, the red one,
-- the bars) ever holds the word.
local function noTargetLabel(W, msg)
    local n = 0
    for _, o in ipairs(__all) do
        if o._kind == "FontString" then
            local p = o._parent
            while p and p ~= W.tgt.box.frame do p = p._parent end
            if p then
                n = n + 1
                ok(o._text ~= "TARGET", msg .. ": a target box FontString holds TARGET")
            end
        end
    end
    ok(n >= 4, msg .. ": target box FontStrings were scanned (" .. n .. ")")
    eq(next(W.tgt.box.head), nil, msg .. ": the target box has no header FontString")
end

function T.constants_match_the_mockup()
    local W = world()
    local C = FS.GunsightBoxes.C
    eq(C.CHAMFER, MB.CHAMFER, "box chamfer")
    for i = 1, 3 do near(C.FILL[i], MB.FILL[i] / 255, 1e-9, "fill colour " .. i) end
    near(C.FILL[4], MB.FILL[4] * MB.FILL_A, 1e-9, "fill alpha is the fill alpha times A(.82)")
    eq(C.PAD, MB.PAD); eq(C.PAD, MB.L2_X, "both lines start at the same x"); eq(2 * C.PAD, MB.WMAX_PAD, "wmax = w - 2 pad")
    eq(C.L1_SIZE, MB.L1_SIZE); eq(C.L1_Y, MB.L1_Y); eq(C.L2_SIZE, MB.L2_SIZE, "your timer line stays 18"); eq(C.L2_Y, MB.L2_Y)
    eq(C.TGT_L2_SIZE, MB.TGT_L2_SIZE, "the target's spell line runs at fs2 14"); eq(MB.TGT_L1_SIZE, C.L1_SIZE, "its unit name line stays 14")
    eq(C.TGT_GROW, MB.TB_GROW, "option B grows the box up"); eq(MB.TB_GROW, MB.TB_GROW_H, "by exactly its added height")
    eq(C.TB_X, MB.TB_X); eq(C.TB_HP_Y, MB.TB_HP_Y); eq(C.TB_HP_H, MB.TB_HP_H); eq(C.TB_PW_Y, MB.TB_PW_Y); eq(C.TB_PW_H, MB.TB_PW_H)
    eq(C.TB_MIN_W, MB.TB_MIN_W)
    near(C.TB_TRACK_A, MB.TB_TRACK_A, 1e-9); near(C.TB_TAIL_A, MB.TB_TAIL_A, 1e-9); eq(MB.TB_TIP_END, 1, "the fill ends at full alpha")
    near(C.TB_TIP_A, MB.TB_TIP_A, 1e-9); near(C.TB_TIP_MIX, MB.TB_TIP_MIX, 1e-9); near(C.TB_TIP_W, MB.TB_TIP_W, 1e-9)
    near(C.TB_LOW, MB.TB_LOW, 1e-9); near(C.LOW_EPSILON, MB.LOW_EPS, 1e-9, "the PartyFrames epsilon")
    eq(C.DIV_Y, MB.DIV_Y); near(C.DIV_A, MB.DIV_A, 1e-9)
    eq(C.HEAD_SIZE, MB.HEAD_SIZE); eq(C.HEAD_DY, MB.HEAD_DY); near(C.HEAD_A, MB.HEAD_A, 1e-9)
    eq(C.CI, MB.CI); eq(C.CIC, MB.CIC); eq(C.CIG, MB.CIG)
    near(C.CI_FILL_A, MB.CI_FILL, 1e-9); near(C.CI_STROKE_A, MB.CI_STROKE, 1e-9)
    near(C.ICON_CROP, MB.ICON_CROP, 1e-9); near(C.IDLE_ICON_A, MB.IDLE_ICON_A, 1e-9)
    eq(#C.FLICK, #MB.FLICK, "the flicker has the mockup's steps")
    for i, v in ipairs(MB.FLICK) do near(C.FLICK[i], v, 1e-9, "flicker step " .. i) end
    near(C.FLICK_DELAY, 0.2, 1e-9, "the flicker starts at tau .2"); near(C.FLICK_STEP, 0.35 / 7, 1e-9, "seven steps over .35 s")
end

function T.colours_are_the_mockups()
    local W = world()
    local c = FS.GunsightBoxes.colors
    eq(rgb(c.white), MB.CSS.white:sub(2)); eq(rgb(c.muted), MB.CSS.muted:sub(2))
    eq(rgb(c.cyan), MB.CSS.cyan:sub(2)); eq(rgb(c.pink), MB.CSS.pink:sub(2)); eq(rgb(c.steel), MB.CSS.steel:sub(2))
    eq(rgb(c.red), MB.CSS.red:sub(2), "the INTERRUPTED red")
    eq(rgb(c.green), MB.TB_HP_HEX:sub(2), "the HP rail green")
    eq(rgb(c.rage), MB.TB_PC.rage:sub(2)); eq(rgb(c.focus), MB.TB_PC.focus:sub(2))
    eq(rgb(c.cyan), MB.TB_PC.mana:sub(2), "mana is the cyan"); eq(rgb(c.gold), MB.CSS.gold:sub(2), "energy is K.gold")
end

-- ---- seats --------------------------------------------------------------------------

function T.each_box_fills_its_anchor_with_the_tile_and_text_at_the_mockup_offsets()
    local W = world()
    local C = FS.GunsightBoxes.C
    local B = MB.base
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        local k = K()
        for _, t in ipairs({ W.you, W.tgt }) do
            local box = t.box
            ok(box, t.key .. ": a box was built")
            local anchor = t.key == "you" and W.Gun.anchors.boxL or W.Gun.anchors.boxR
            local g = t.key == "you" and B.BOXL or B.BOXR
            eq(box.anchor, anchor)
            eq(box.frame._points.TOPLEFT.rel, anchor); eq(box.frame._points.TOPLEFT.relPoint, "TOPLEFT")
            eq(box.frame._points.BOTTOMRIGHT.rel, anchor); eq(box.frame._points.BOTTOMRIGHT.relPoint, "BOTTOMRIGHT")
            near(anchor._w, g.w * k, 1e-6, t.key .. ": the anchor is 114 image px wide at " .. h)
            near(anchor._h, g.h * k, 1e-6, t.key .. ": and 56 high")
            eq(box.frame:GetParent(), t.piece, t.key .. ": a child of the tape piece")
            -- line 1 and line 2: baseline y, left x
            local p1 = box.l1._points.BOTTOMLEFT
            eq(p1.rel, box.frame); eq(p1.relPoint, "TOPLEFT")
            near(p1.x, C.PAD * k, 1e-6, "line 1 x"); near(p1.y, -(C.L1_Y + C.L1_SIZE * C.DESCENT) * k, 1e-6, "line 1 baseline")
            near(box.l1._w, (g.w - 2 * C.PAD) * k, 1e-6, "line 1 is as wide as wmax")
            local grow = t.key == "tgt" and C.TGT_GROW or 0
            local l2Size = t.key == "tgt" and C.TGT_L2_SIZE or C.L2_SIZE
            -- the target's frame grows UP by TGT_GROW above its anchor; nothing else of the anchor moves
            near(box.frame._points.TOPLEFT.y, grow * k, 1e-6, t.key .. ": the box top is grown by the option B rise")
            near(box.frame._points.TOPLEFT.x, 0, 1e-6); near(box.frame._points.BOTTOMRIGHT.y, 0, 1e-6)
            for tone, fs in pairs(box.l2) do
                local p2 = fs._points.BOTTOMLEFT
                eq(p2.rel, box.frame); near(p2.x, C.PAD * k, 1e-6)
                near(p2.y, -(C.L2_Y + grow + l2Size * C.DESCENT) * k, 1e-6, "line 2 baseline")
                near(box.frame._points.TOPLEFT.y + p2.y, -(C.L2_Y + l2Size * C.DESCENT) * k, 1e-6, "line 2 keeps its old screen seat")
                eq(fs._fontSize, fontFor(l2Size), "line 2 font")
                eq(fs:GetParent(), box.tones[tone], "line 2 lives in its colour's frame")
            end
            -- the icon tile: 28, on the box's inner side (right of yours, left of the target's), 6 off the box
            near(box.tile._w, C.CI * k, 1e-6); near(box.tile._h, C.CI * k, 1e-6)
            if t.key == "you" then
                local p = box.tile._points.TOPLEFT
                eq(p.rel, box.frame); eq(p.relPoint, "TOPRIGHT"); near(p.x, C.CIG * k, 1e-6)
                near(p.y, -((g.h - C.CI) / 2) * k, 1e-6, "centred on the box height")
            else
                local p = box.tile._points.TOPRIGHT
                eq(p.rel, box.frame); eq(p.relPoint, "TOPLEFT"); near(p.x, -C.CIG * k, 1e-6)
                near(p.y, -((g.h - C.CI) / 2 + grow) * k, 1e-6, "centred on the old box height, below the grown top")
                near(box.frame._points.TOPLEFT.y + p.y, -((g.h - C.CI) / 2) * k, 1e-6, "the tile keeps its old screen seat")
            end
            -- the header sits HEAD_DY above yours, at its left end; the target box has none
            for tone, fs in pairs(box.head) do
                eq(t.key, "you", "only your box has a header")
                local pt = fs._points.BOTTOMLEFT
                eq(pt.rel, box.frame); eq(pt.relPoint, "TOPLEFT")
                near(pt.x, 0, 1e-6); near(pt.y, (C.HEAD_DY - C.HEAD_SIZE * C.DESCENT) * k, 1e-6, "header baseline")
                eq(fs._text, "YOU")
            end
            eq(box.l1._fontSize, fontFor(C.L1_SIZE), "line 1 font")
        end
        -- the target's divider
        for _, d in pairs(W.tgt.box.divider) do
            ok(d._h > 0, "a visible thickness")
            near(d._w, (MB.base.BOXR.w - 2 * C.PAD) * k, 1e-6, "the divider spans the padded width")
            near(d._points.TOPLEFT.y, -(C.DIV_Y + C.TGT_GROW) * k, 1e-6, "at b.y + 29 below the grown top")
            near(W.tgt.box.frame._points.TOPLEFT.y + d._points.TOPLEFT.y, -C.DIV_Y * k, 1e-6, "which is its old screen seat")
        end
        eq(next(W.you.box.divider), nil, "yours has no divider")
    end
end

function T.the_boxes_hang_off_the_tape_pieces_so_the_piece_toggles_fade_them()
    local W = world()
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(W.you.S, "UNIT_SPELLCAST_START")   -- your box exists only while casting
    eq(W.you.box.frame:IsVisible(), true); eq(W.tgt.box.frame:IsVisible(), true)
    W.Gun.SetPiece("you", false, true)
    eq(W.you.box.frame:IsVisible(), false, "piece `you` off hides the left box")
    eq(W.tgt.box.frame:IsVisible(), true, "and only the left box")
    W.Gun.SetPiece("tgt", false, true)
    eq(W.tgt.box.frame:IsVisible(), false, "piece `tgt` off hides the right box")
    W.Gun.SetPiece("you", true, true); W.Gun.SetPiece("tgt", true, true)
    eq(W.you.box.frame:IsVisible(), true); eq(W.tgt.box.frame:IsVisible(), true)
    -- the box is not registered as a piece of its own (one frame per key, and the keys are the tapes')
    eq(W.Gun.IsPieceOn("you"), true)
end

function T.the_members_castbars_drives_are_the_boxes()
    local W = world()
    for _, t in ipairs({ W.you, W.tgt }) do
        local m, S = t.box.members, t.S
        eq(S.icon, m.icon, t.key .. ": icon"); eq(S.tabName, m.tabName, "name"); eq(S.timer, m.timer, "timer")
        eq(S.tabTicks, m.tabTicks, "ticks")
        eq(S.tabTicks, t.box.ticks, "the tick counter is the real FontString")
        for _, name in ipairs({ "SetTexture" }) do eq(type(m.icon[name]), "function") end
        for _, name in ipairs({ "SetText", "GetStringWidth" }) do eq(type(m.tabName[name]), "function") end
        for _, name in ipairs({ "SetText", "SetFormattedText" }) do eq(type(m.timer[name]), "function") end
    end
    ok(W.you.name == W.you.box.l1, "yours: the name lands on line 1")
    ok(W.tgt.name == W.tgt.box.l2.pink, "the target's: on line 2 (pink copy)")
end

-- ---- the player box -----------------------------------------------------------------

function T.a_player_cast_writes_name_and_timer_in_the_mockups_format()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.at(S, 100.9)
    W.clean(); noFails()
    eq(b.l1._text, "SHADOW BOLT", "line 1: the spell, in capitals")
    eq(colourOf(b.l1), MB.CSS.white:sub(2), "white while casting")
    eq(b.l2.base._text, "0.9|cff9a8fbd / 2.5|r", "line 2: elapsed over the real length, CastBars' own format")
    eq(colourOf(b.l2.base), MB.CSS.cyan:sub(2), "cyan")
    eq(b.icon._texture, "icon", "the spell icon")
    eq(b.tile._alpha, 1, "full strength while casting")
    eq(b.tile:IsShown(), true)
    W.at(S, 102.4)
    eq(b.l2.base._text, "2.4|cff9a8fbd / 2.5|r")
    W.clean(); noFails()
end

function T.the_player_box_at_rest_is_blank_with_no_stale_last_spell_and_no_timer()
    local W = world()
    local b, S = W.you.box, W.you.S
    eq(b.l1._text, "", "nothing cast yet: no name"); eq(b.l2.base._text, "")
    near(b.tile._alpha, MB.IDLE_ICON_A, 1e-9, "the icon tile is dimmed at rest")
    eq(b.frame:IsVisible(), false, "your box is hidden at rest: no cast, no box")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 102.5)
    W.fire(S, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(S, 102.5, 104.5)
    eq(S.mode, nil, "back to idle")
    eq(b.l1._text, "", "the finished cast's name is gone from line 1")
    for _, fs in pairs(b.l2) do eq(fs._text, "", "and line 2 (every colour copy) has no timer text") end
    eq(b.head.base._text, "YOU", "the header stays")
    near(b.tile._alpha, MB.IDLE_ICON_A, 1e-9); eq(b.icon._texture, nil, "the icon is cleared"); eq(b.icon._desat, true)
    eq(colourOf(b.l1), MB.CSS.muted:sub(2), "line 1 is muted at rest")
    -- the next cast brings the colours back
    W.cast("player", "Fear", "C2", 110, 1.5)
    W.fire(S, "UNIT_SPELLCAST_START"); W.at(S, 110.3)
    eq(b.l1._text, "FEAR")
    eq(colourOf(b.l1), MB.CSS.white:sub(2)); eq(colourOf(b.l2.base), MB.CSS.cyan:sub(2)); eq(b.tile._alpha, 1)
    W.clean(); noFails()
end

function T.the_channel_counter_sits_in_the_header_row_with_cut_in_pink()
    local W = world()
    local b, S = W.you.box, W.you.S
    local C = FS.GunsightBoxes.C
    local k = K()
    eq(b.ticks:IsShown(), false, "no counter at rest")
    local p = b.ticks._points.BOTTOMRIGHT
    eq(p.rel, b.frame); eq(p.relPoint, "TOPRIGHT"); near(p.x, 0, 1e-6)
    near(p.y, (C.HEAD_DY - C.HEAD_SIZE * C.DESCENT) * k, 1e-6, "the header row's baseline, at the box's right end")
    channel("player", "Mind Flay", 100, 3)
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START")
    eq(b.ticks:IsShown(), true); eq(b.ticks._text, "0/3")
    W.at(S, 101.1); eq(b.ticks._text, "1/3")
    W.at(S, 102.1); eq(b.ticks._text, "CUT", "2 of 3 landed")
    eq(colourOf(b.ticks), rgb(FS.Theme.COLOR_HEALTH), "pink")
    eq(b.l1._text, "MIND FLAY")
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_CHANNEL_STOP"); W.stepTo(S, 102.1, 104)
    eq(b.ticks:IsShown(), false, "the counter goes with the cast")
    eq(b.l1._text, "", "line 1 is empty at idle after channel")
    for _, fs in pairs(b.l2) do eq(fs._text, "", "line 2 is empty for all colours at idle") end
    W.clean(); noFails()
end

-- ---- the target box -----------------------------------------------------------------

function T.the_target_box_shows_the_unit_name_and_the_spell_as_two_fields_and_no_timer()
    local W = world()
    local b, S = W.tgt.box, W.tgt.S
    target("Kurak")
    eq(b.l1._text, "KURAK", "line 1: the unit name in capitals")
    eq(colourOf(b.l1), MB.CSS.muted:sub(2), "muted while it is not casting")
    for _, fs in pairs(b.l2) do eq(fs._text, "", "no spell between casts") end
    eq(b.tile:IsShown(), false, "no icon tile between casts (the mockup draws none)")
    W.cast("target", "Fear", "T1", 100, 1.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean(); noFails()
    eq(b.l2.pink._text, "FEAR"); eq(b.l2.steel._text, "FEAR", "both colour copies carry it")
    eq(colourOf(b.l1), MB.CSS.white:sub(2), "white once it casts")
    eq(b.tile:IsShown(), true); eq(b.icon._texture, "icon")
    eq(colourOf(b.l2.pink), MB.CSS.pink:sub(2)); eq(colourOf(b.l2.steel), MB.CSS.steel:sub(2))
    noTargetLabel(W, "while it casts")
    -- no timer: whatever CastBars writes goes nowhere
    eq(type(S.timer.SetFormattedText), "function"); S.timer:SetFormattedText("%.1f / %.1f", 1, 2); S.timer:SetText("x")
    eq(W.tgt.box.regions.timer, nil, "there is no timer region on the target box")
    W.endCast("target"); W.fire(S, "UNIT_SPELLCAST_STOP", "T1")
    for _, fs in pairs(b.l2) do eq(fs._text, "") end
    eq(colourOf(b.l1), MB.CSS.muted:sub(2), "muted again"); eq(b.tile:IsShown(), false)
    eq(b.l1._text, "KURAK", "the unit stays named")
    target(nil)
    eq(b.l1._text, "", "no target: no name")
    W.clean(); noFails()
end

function T.the_interruptible_flag_colours_every_target_box_part_through_alpha_from_boolean()
    local W = world()
    local b, S = W.tgt.box, W.tgt.S
    W.cast("target", "Fear", "T1", 100, 1.5, true)      -- notInterruptible
    W.fire(S, "UNIT_SPELLCAST_START")
    for _, r in ipairs(b.fb.steel) do eq(r._alpha, 1, "steel up") end
    for _, r in ipairs(b.fb.pink) do eq(r._alpha, 0, "pink down") end
    W.cast("target", "Mending", "T2", 100, 2, false)
    W.fire(S, "UNIT_SPELLCAST_START")
    for _, r in ipairs(b.fb.steel) do eq(r._alpha, 0) end
    for _, r in ipairs(b.fb.pink) do eq(r._alpha, 1) end
    -- between casts the neutral steel look
    W.endCast("target"); W.fire(S, "UNIT_SPELLCAST_STOP", "T2")
    for _, r in ipairs(b.fb.steel) do eq(r._alpha, 1) end
    for _, r in ipairs(b.fb.pink) do eq(r._alpha, 0) end
    -- the box edge, the header, line 2, the divider and the tile edge are the flagged parts
    local function has(list, v) for _, r in ipairs(list) do if r == v then return true end end return false end
    for _, tone in ipairs({ "pink", "steel" }) do
        ok(has(b.fb[tone], b.tones[tone]), tone .. ": the tone frame (edge, header, line 2, divider) is flagged")
        ok(has(b.fb[tone], b.tileTones[tone]), tone .. ": so is the tile edge")
        eq(b.stroke[tone]:GetParent(), b.tones[tone]); eq(b.divider[tone]:GetParent(), b.tones[tone])
    end
    -- and every flagged region is a frame, which is where the tape already relies on SetAlphaFromBoolean
    for _, list in pairs(b.fb) do for _, r in ipairs(list) do eq(r._kind, "Frame") end end
    -- the whole tape still reads the flag as it did: the tape's own regions share the lists
    ok(#W.tgt.fb.pink >= 5 and #W.tgt.fb.steel >= 5, "the tape's lists carry the box's frames too")
    W.clean(); noFails()
end

function T.without_alpha_from_boolean_the_target_box_stays_neutral_steel()
    local W = world({ beforeLoad = function() getmetatable(UIParent).SetAlphaFromBoolean = nil end })
    local b, S = W.tgt.box, W.tgt.S
    W.cast("target", "Fear", "T1", 100, 1.5, false)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean(); noFails()
    for _, r in ipairs(b.fb.steel) do eq(r._alpha, 1) end
    for _, r in ipairs(b.fb.pink) do eq(r._alpha, 0) end
end

-- ---- secrets --------------------------------------------------------------------------

function T.a_secret_target_cast_reaches_only_sinks()
    local W = world()
    local b, S = W.tgt.box, W.tgt.S
    secretUnit(); __fireEvent("PLAYER_TARGET_CHANGED")
    ok(rawequal(b.l1._text, __SECRET_NAME), "a secret unit name reaches SetText untouched (not upper-cased)")
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    W.at(S, __now + 0.3)
    W.clean(); noFails("a secret operation was swallowed by a pcall")
    ok(rawequal(b.l2.pink._text, __SECRET_NAME) and rawequal(b.l2.steel._text, __SECRET_NAME), "the spell name: SetText only")
    eq(b.l2.pink._fontSize, fontFor(FS.GunsightBoxes.C.SECRET_L2_SIZE), "a secret is never measured: the fixed size")
    eq(b.l2.pink._w, (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * K(), "and a fixed width, so it clips instead")
    eq(b.l2.pink._wordWrap, false)
    eq(b.icon._texture, "icon"); eq(b.tile:IsShown(), true)
    for _, r in ipairs(b.fb.steel) do ok(rawequal(r._fromBool, __SECRET_BOOL), "steel: the flag, untouched"); eq(r._fromT, 1) end
    for _, r in ipairs(b.fb.pink) do ok(rawequal(r._fromBool, __SECRET_BOOL), "pink: the same flag"); eq(r._fromF, 1) end
    -- every event of the state machine, with secrets in every slot
    for _, event in ipairs({ "UNIT_SPELLCAST_DELAYED", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED",
        "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_CHANNEL_STOP" }) do
        W.secretCast("target")
        W.fire(S, "UNIT_SPELLCAST_START")
        W.fire(S, event, __SECRET_ID, __SECRET)
        W.at(S, __now + 0.3)
    end
    W.endCast("target"); W.fire(S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.clean(); noFails("a secret operation was swallowed by a pcall")
    ok(rawequal(b.l2.pink._text, ""), "idle again")
end

function T.a_secret_channel_name_on_the_target_is_a_sink_write_too()
    local W = world()
    local b, S = W.tgt.box, W.tgt.S
    __units.target.cast = nil
    __units.target.chan = { name = __SECRET_NAME, tex = "icon", startMS = __SECRET, endMS = __SECRET,
        notInt = __SECRET_BOOL, spellID = __SECRET, secret = true }
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START")
    W.at(S, __now + 0.3)
    W.clean(); noFails()
    ok(rawequal(b.l2.steel._text, __SECRET_NAME))
    eq(b.ticks:IsShown(), false, "no tick counter on the target (its name is secret)")
end

-- ---- fitting ----------------------------------------------------------------------------

function T.a_long_plain_name_shrinks_to_fit_and_a_short_one_keeps_the_mockups_size()
    local W = world()
    local b, S = W.you.box, W.you.S
    local base = fontFor(FS.GunsightBoxes.C.L1_SIZE)
    W.cast("player", "Fear", "C1", 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START")
    eq(b.l1._fontSize, base, "a short name keeps 14 image px")
    W.cast("player", "Summon Felhunter", "C2", 100, 6); W.fire(S, "UNIT_SPELLCAST_START")
    ok(b.l1._fontSize < base and b.l1._fontSize >= 6, "a long name shrinks: " .. tostring(b.l1._fontSize))
    local wmax = (MB.base.BOXL.w - 2 * FS.GunsightBoxes.C.PAD) * K()
    ok(b.l1:GetStringWidth() <= wmax + 1e-6, "and now fits the box: " .. b.l1:GetStringWidth() .. " <= " .. wmax)
    W.cast("player", "Fear", "C3", 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START")
    eq(b.l1._fontSize, base, "the next short name is back at full size")
    W.clean(); noFails()
end

-- ---- lifecycle ----------------------------------------------------------------------------

function T.a_rescale_reseats_in_place_and_builds_nothing()
    local W = world()
    local S = W.tgt.S
    W.cast("target", "Fear", "T1", 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START")
    target("Kurak")
    local before = countFrames()
    local fontBefore, tileBefore = W.tgt.box.l1._fontSize, W.tgt.box.tile._w
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
    W.clean(); noFails()
    eq(countFrames(), before, "a rescale creates no frame, texture or font string")
    ok(W.tgt.box.l1._fontSize < fontBefore, "the type shrank with the scale")
    ok(W.tgt.box.tile._w < tileBefore, "so did the tile")
    near(W.tgt.box.tile._w, FS.GunsightBoxes.C.CI * K(), 1e-6)
    eq(W.tgt.box.l1._text, "KURAK", "the text survives")
    eq(W.tgt.box.l2.pink._text, "FEAR", "a cast in progress keeps its name")
    for _, h in ipairs({ 1440, 720, 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
    end
    eq(countFrames(), before, "and still nothing built")
    -- target and cast events build nothing either
    for i = 1, 5 do target("Kurak" .. i); W.cast("target", "Fear", "T" .. i, 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START") end
    for _, e in ipairs({ "UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER", "UNIT_DISPLAYPOWER" }) do __fireUnit(e, "target") end
    eq(countFrames(), before, "events (the bar events too) build nothing")
    W.clean(); noFails()
end

function T.no_onupdate_at_rest_with_the_boxes_built()
    local W = world()
    eq(__countOnUpdates(), 0)
    target("Kurak")
    eq(__countOnUpdates(), 0, "a target change installs none")
end

function T.the_gunsight_off_builds_no_box()
    local W = world({ db = { gunsight = { enabled = false } } })
    W.clean()
    eq(W.you, nil)
    eq(find(function(o) return o._name and o._name:find("GunsightBox", 1, true) end), nil, "no box frame exists")
end

function T.a_failed_box_build_falls_back_to_the_text_sinks_and_the_tape_keeps_working()
    local W = world({ beforeLoad = function()
        local build = FS.Theme.AddCut2Texture
        FS.Theme.AddCut2Texture = function(frame, ...)
            if frame._parent and frame._parent._name == "ForeverSTUwaveGunsightBox_you" then error("box build failed") end
            return build(frame, ...)
        end
    end })
    W.clean()
    eq(W.you.box, nil, "no box on the left"); ok(W.tgt.box, "the right box is independent")
    ok(degraded("gunsighttape_box_you"), "logged once")
    local broken = find(function(o) return o._name == "ForeverSTUwaveGunsightBox_you" end)
    ok(broken, "the half built frame exists"); eq(broken._shown, false, "and is hidden")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.you.S, "UNIT_SPELLCAST_START")
    eq(W.you.S.mode, "run"); eq(W.you.name._text, "SHADOW BOLT", "the alpha 0 sink still takes the name")
    W.clean()
end


-- ---- fonts before text ----------------------------------------------------------------------

function T.every_font_string_has_its_font_before_the_first_settext()
    -- The mock throws "Font not set" for a write to a FontString without one (the client does, and the
    -- throw lands in pcall(BuildBox)), so a box that built at all wrote nothing before its font.
    local W = world()
    W.clean()
    for _, t in ipairs({ W.you, W.tgt }) do
        ok(t.box, t.key .. ": the box built (no `Font not set` swallowed by the build pcall)")
        local n = 0
        for _, o in ipairs(__all) do
            if o._kind == "FontString" and o._parent and (o._parent == t.box.frame or o._parent._parent == t.box.frame) then
                n = n + 1
                ok(o._fontSize ~= nil, t.key .. ": a FontString without a font")
            end
        end
        ok(n >= 4, t.key .. ": FontStrings were checked (" .. n .. ")")
    end
    -- and the mock is really strict
    local fs = W.you.box.frame:CreateFontString(nil, "OVERLAY")
    local okSet, err = pcall(fs.SetText, fs, "x")
    eq(okSet, false); ok(tostring(err):find("Font not set", 1, true), "the mock throws like the client")
    __pcallFails = {}
end

-- ---- the listener is second to last, the rescale registration last, a dropped box is retired ----

local function targetListeners()
    local n = 0
    for _, o in ipairs(__all) do
        if o._events and o._events.PLAYER_TARGET_CHANGED and o._scripts and o._scripts.OnEvent
            and o._parent and o._parent._name == "ForeverSTUwaveGunsightBox_tgt" then n = n + 1 end
    end
    return n
end

function T.a_build_that_fails_late_leaves_no_live_name_listener()
    local W = world({ noLogin = true })
    local on = FS.Layout.OnRescale
    FS.Layout.OnRescale = function(fn)
        if debug.getinfo(fn, "S").short_src:find("GunsightBoxes", 1, true) then error("late build step failed") end
        return on(fn)
    end
    __fireEvent("ADDON_LOADED", "forever-stuwave")
    __fireEvent("PLAYER_LOGIN")
    W.you, W.tgt = FS.GunsightTape.you, FS.GunsightTape.tgt
    W.clean()
    eq(W.tgt.box, nil, "the box did not build")
    ok(degraded("gunsighttape_box_tgt"), "and said so")
    eq(targetListeners(), 0, "no PLAYER_TARGET_CHANGED listener survives on the dead box")
    __units.target.name = "Kurak"
    __fireEvent("PLAYER_TARGET_CHANGED")                   -- nothing calls into the dead box
    __fireEvent("UNIT_NAME_UPDATE", "target")
end

function T.a_failing_listener_step_unregisters_what_it_registered()
    local W = world({ beforeLoad = function()
        local Region = getmetatable(UIParent)
        local setScript = Region.SetScript
        function Region:SetScript(k, fn)
            if k == "OnEvent" and self._parent and self._parent._name == "ForeverSTUwaveGunsightBox_tgt" then error("SetScript failed") end
            return setScript(self, k, fn)
        end
    end })
    W.clean()
    eq(W.tgt.box, nil, "the box did not build")
    for _, o in ipairs(__all) do
        if o._parent and o._parent._name == "ForeverSTUwaveGunsightBox_tgt" and o._events then
            eq(next(o._events), nil, "nothing stays registered on the half built listener")
            eq(next(o._unitEvents or {}), nil, "no unit event either")
        end
    end
end

-- A tape that fails AFTER its box built (here the target tape's KICK label, the step after BuildMembers)
-- retires every box it already built: no layout write on a rescale, no name write on a target change, no
-- listener left registered, even if a stale reference still calls into the box.
function T.a_tape_that_fails_after_its_box_built_retires_the_box()
    local W = world({ noLogin = true })
    local boxes, armed, stale, staleYou = {}, false, nil, nil
    local build = FS.GunsightBoxes.Build
    FS.GunsightBoxes.Build = function(spec)
        local box, err = build(spec)
        if box then
            boxes[#boxes + 1] = box
            if spec.isTarget then armed = true; stale = box.events._scripts.OnEvent
            else staleYou = box.events._scripts.OnEvent end
        end
        return box, err
    end
    local Region = getmetatable(UIParent)
    local createFont = Region.CreateFontString
    function Region:CreateFontString(...)
        if armed then armed = false; error("kick label failed") end
        return createFont(self, ...)
    end
    __fireEvent("ADDON_LOADED", "forever-stuwave")
    __fireEvent("PLAYER_LOGIN")
    Region.CreateFontString = createFont
    W.clean()
    eq(FS.GunsightTape.tgt, nil, "the tape build failed")
    ok(degraded("gunsighttape_build"), "and said so")
    eq(#boxes, 2, "both boxes had been built")
    ok(stale, "the target box had its listener (kept as a stale reference the retire cannot clear)")
    ok(staleYou, "and so had yours (its PLAYER_LOGIN / PLAYER_ENTERING_WORLD name refresh)")
    local writes = {}
    for i, b in ipairs(boxes) do
        writes[i] = 0
        local objs = { b.l1, b.tile, b.ticks }
        for _, f in pairs(b.l2) do objs[#objs + 1] = f end       -- line two and the timer text
        for _, f in pairs(b.head) do objs[#objs + 1] = f end
        for _, o in ipairs(objs) do
            for _, m in ipairs({ "SetText", "SetWidth", "SetSize", "SetPoint", "ClearAllPoints" }) do
                local orig = o[m]
                if orig then o[m] = function(...) writes[i] = writes[i] + 1; return orig(...) end end
            end
        end
    end
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")                           -- Layout.OnRescale runs the callbacks
    __units.target.name = "Kurak"
    __fireEvent("PLAYER_TARGET_CHANGED")
    __fireEvent("UNIT_NAME_UPDATE", "target")
    stale()                                                   -- and a stale caller of the listener
    __units.player.name = "Rowan"                             -- a late name refresh on yours: a no-op too
    __fireEvent("PLAYER_ENTERING_WORLD"); __fireEvent("PLAYER_LOGIN")
    staleYou()
    for i = 1, #boxes do eq(writes[i], 0, "box " .. i .. ": a retired box did no layout, name, line two or timer write") end
    eq(boxes[1].head.base._text, "YOU", "yours kept its header: the late name write did nothing")
    for _, b in ipairs(boxes) do eq(b.frame._shown, false, "the retired box is hidden") end
    eq(targetListeners(), 0, "no PLAYER_TARGET_CHANGED listener survives")
    for _, o in ipairs(__all) do
        local pn = o._parent and o._parent._name
        if o._events and (pn == "ForeverSTUwaveGunsightBox_tgt" or pn == "ForeverSTUwaveGunsightBox_you") then
            eq(next(o._events), nil, "no event stays registered (" .. pn .. ")")
            eq(next(o._unitEvents or {}), nil, "no unit event either")
        end
    end
    W.clean()
end

function T.a_retired_box_ignores_a_late_verdict()
    local W = world()
    local b, S = W.you.box, W.you.S
    FS.GunsightBoxes.Retire(b)
    S.onVerdict(S, "interrupt")                               -- a stale bar table still calls the hook
    W.clean(); noFails()
    ok(not b.verdict, "no verdict state")
    eq(b.flicker.playing, false, "no flicker on a retired box")
    eq(b.tones.red._shown, false, "no red tone"); eq(b.tileTones.red._shown, false, "nor a red tile edge")
    ok(b.l1._text ~= "INTERRUPTED", "line one was not written")
end

function T.a_retired_box_ignores_late_name_timer_and_icon_writes()
    local W = world()
    local b, S = W.you.box, W.you.S
    FS.GunsightBoxes.Retire(b)
    local writes = 0
    local objs = { b.l1, b.icon, b.tile, b.ticks }
    for _, f in pairs(b.l2) do objs[#objs + 1] = f end
    for _, o in ipairs(objs) do
        for _, m in ipairs({ "SetText", "SetFormattedText", "SetTexture", "SetAlpha", "SetShown", "SetDesaturated", "SetTextColor" }) do
            local orig = o[m]
            if orig then o[m] = function(...) writes = writes + 1; return orig(...) end end
        end
    end
    S.tabName:SetText("SHADOW BOLT")                          -- a stale bar table still writes the sinks
    S.timer:SetText("0.9")
    S.timer:SetFormattedText("%.1f|cff9a8fbd / %.1f|r", 0.9, 2.5)
    S.icon:SetTexture(136197)
    W.clean(); noFails()
    eq(writes, 0, "a retired box took no name, timer or icon write")
    ok(b.l1._text ~= "SHADOW BOLT", "line one was not written")
end

function T.a_failed_tape_build_survives_the_boxes_module_vanishing()
    local W = world({ noLogin = true })
    local armed = false
    local gb, build = FS.GunsightBoxes, FS.GunsightBoxes.Build
    gb.Build = function(spec)
        local box, err = build(spec)
        if box and spec.isTarget then armed = true end
        return box, err
    end
    local Region = getmetatable(UIParent)
    local createFont = Region.CreateFontString
    function Region:CreateFontString(...)
        if armed then armed = false; FS.GunsightBoxes = nil; error("kick label failed") end
        return createFont(self, ...)
    end
    __fireEvent("ADDON_LOADED", "forever-stuwave")
    __fireEvent("PLAYER_LOGIN")
    Region.CreateFontString = createFont
    FS.GunsightBoxes = gb
    W.clean()
    eq(FS.GunsightTape.tgt, nil, "the tape build still failed cleanly")
    ok(degraded("gunsighttape_build"), "and said so even though the retire lookup threw")
    W.clean()
end

-- ---- a rescale re-fits ---------------------------------------------------------------------------

function T.a_rescale_refits_a_long_plain_name_at_once()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Summon Felhunter", "C1", 100, 6); W.fire(S, "UNIT_SPELLCAST_START")
    local base1440 = fontFor(FS.GunsightBoxes.C.L1_SIZE)
    ok(b.l1._fontSize < base1440, "shrunk at 1440")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local wmax = (MB.base.BOXL.w - 2 * FS.GunsightBoxes.C.PAD) * K()
    local base = fontFor(FS.GunsightBoxes.C.L1_SIZE)
    ok(b.l1._fontSize < base, "still shrunk after the rescale (base " .. base .. ", got " .. tostring(b.l1._fontSize) .. ")")
    ok(b.l1:GetStringWidth() <= wmax + 1e-6, "and it fits the new box width: " .. b.l1:GetStringWidth() .. " <= " .. wmax)
    UIParent._h = 1440; UIParent._w = 1440 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    ok(b.l1:GetStringWidth() <= (MB.base.BOXL.w - 2 * FS.GunsightBoxes.C.PAD) * K() + 1e-6, "and back up")
    W.clean(); noFails()
end

-- ---- the idle tile is gray -----------------------------------------------------------------------

function T.the_idle_player_tile_is_desaturated_and_live_is_not()
    local W = world()
    local b, S = W.you.box, W.you.S
    eq(b.icon._desat, true, "at rest the tile icon is a gray flag as well as dimmed")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START")
    eq(b.icon._desat, false, "live: in colour")
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_STOP", "C1"); W.stepTo(S, 100, 104.5)
    eq(b.icon._desat, true, "and gray again at idle")
    -- a client without SetDesaturated just keeps the dim
    local W2 = world({ beforeLoad = function() getmetatable(UIParent).SetDesaturated = nil end })
    near(W2.you.box.tile._alpha, MB.IDLE_ICON_A, 1e-9, "still dimmed"); W2.clean(); noFails()
end

-- ---- visibility: your box only while casting, the target's only with a target -----------------------------

function T.your_box_is_hidden_at_idle_and_shown_while_a_cast_is_live()
    local W = world()
    local b, S = W.you.box, W.you.S
    eq(b.frame._shown, false, "built hidden: nothing is cast")
    for _, part in ipairs({ b.tile, b.head.base, b.l1, b.l2.base, b.ticks }) do eq(part:IsVisible(), false, "no part of it shows") end
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START")
    eq(b.frame._shown, true, "a cast shows it"); eq(b.frame:IsVisible(), true); eq(b.tile:IsVisible(), true)
    W.at(S, 100.9)
    eq(b.frame._shown, true, "and keeps it up while it runs")
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_STOP", "C1"); W.stepTo(S, 100.9, 104.5)
    eq(S.mode, nil, "back to idle")
    eq(b.frame._shown, false, "the idle write hides the whole box")
    -- a channel is live too
    __now = 110
    __units.player.chan = { name = "Mind Flay", tex = "icon", startMS = 110000, endMS = 113000, notInt = false }; __units.player.cast = nil
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START")
    eq(b.frame._shown, true, "a channel shows it")
    W.clean(); noFails()
    eq(__countOnUpdates() <= 2, true, "no OnUpdate was added by the box")
end

function T.a_secret_player_cast_shows_the_box_without_reading_the_secret()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.secretCast("player"); W.fire(S, "UNIT_SPELLCAST_START", __SECRET_ID)
    eq(b.frame._shown, true, "a secret write is live: the box shows")
    ok(rawequal(b.l1._text, __SECRET_NAME), "the secret went to SetText untouched")
    W.clean(); noFails("nothing read the secret")
end

function T.the_interrupted_look_keeps_the_box_up_until_it_clears()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 101.5)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(b.verdict, true); eq(b.frame._shown, true, "the verdict look shows the box")
    W.at(S, 102.0)
    eq(b.frame._shown, true, "still up during the outage")
    W.stepTo(S, 102.0, 103.4)
    eq(b.verdict, false, "the look cleared"); eq(b.frame._shown, false, "and the box went away with it")
    -- a verdict that arrives while the box is hidden brings it up
    S.onVerdict(S, "interrupt")
    eq(b.frame._shown, true, "a verdict shows a hidden box")
    W.clean(); noFails()
end

function T.a_retired_box_stays_hidden_through_late_writes()
    local W = world()
    local b = W.you.box
    FS.GunsightBoxes.Retire(b)
    b.members.tabName:SetText("FEAR")
    eq(b.frame._shown, false, "Retire hides it and a late name write does not bring it back")
end

function T.the_header_is_the_players_name_in_capitals_and_falls_back_to_you()
    local W = world({ beforeLoad = function() __units.player.name = "Kaelith" end })
    local b = W.you.box
    eq(b.head.base._text, "KAELITH", "the character name, upper-cased"); eq(b.head.red._text, "KAELITH", "on the red copy too")
    noTargetLabel(W, "the player's name does not touch the target box")
    -- not ready at build: nil, then "Unknown", then a secret, each falls back to YOU until the name is real
    for _, early in ipairs({ "nil", "Unknown", "secret", "" }) do
        local W2 = world({ beforeLoad = function()
            if early == "nil" then __units.player.name = nil
            elseif early == "secret" then __units.player.name = __SECRET_NAME
            else __units.player.name = early end
        end })
        local b2 = W2.you.box
        eq(b2.head.base._text, "YOU", early .. ": falls back to YOU")
        __units.player.name = "Rowan"
        __fireEvent("PLAYER_ENTERING_WORLD")
        eq(b2.head.base._text, "ROWAN", early .. ": PLAYER_ENTERING_WORLD refreshes it")
        __units.player.name = "Mira"
        __fireEvent("PLAYER_LOGIN")
        eq(b2.head.base._text, "MIRA", early .. ": PLAYER_LOGIN refreshes it")
        __units.player.name = __SECRET_NAME
        __fireEvent("PLAYER_ENTERING_WORLD")
        eq(b2.head.base._text, "YOU", early .. ": a secret name goes back to YOU, never measured")
        W2.clean(); noFails()
    end
    __units.player.name = nil
end

function T.the_header_is_the_full_name_with_the_surname_and_fits_the_box()
    -- UnitName drops the surname on this server; FS.GetFullUnitName (UnitFrames.lua) keeps it.
    local W = world({ beforeLoad = function()
        __units.player.name = "Hammered"
        FS.GetFullUnitName = function(u) return u == "player" and "Hammered Stu" or nil end
    end })
    local b = W.you.box
    eq(b.head.base._text, "HAMMERED STU", "first name and surname, upper-cased"); eq(b.head.red._text, "HAMMERED STU")
    local line = b.headLine
    ok(line.wmax > 0 and b.head.base:GetStringWidth() <= line.wmax + 1e-6, "and it fits the header width")
    -- a secret full name falls back to YOU without being measured; a long one shrinks instead of overflowing
    FS.GetFullUnitName = function() return __SECRET_NAME end
    __fireEvent("PLAYER_ENTERING_WORLD")
    eq(b.head.base._text, "YOU", "a secret full name reads YOU")
    FS.GetFullUnitName = function() return "Alexandria Thegreat" end
    __fireEvent("PLAYER_ENTERING_WORLD")
    ok(b.head.base._fontSize < fontFor(FS.GunsightBoxes.C.HEAD_SIZE), "a long full name shrinks")
    ok(b.head.base:GetStringWidth() <= b.headLine.wmax + 1e-6, "to the box minus the tick counter's reserve")
    W.clean(); noFails("a secret name was measured")
end

function T.a_long_character_name_shrinks_to_the_box_and_a_short_one_keeps_the_header_size()
    local W = world({ beforeLoad = function() __units.player.name = "Alexandriathegreat" end })
    local b = W.you.box
    local C = FS.GunsightBoxes.C
    local avail = (MB.base.BOXL.w - C.HEAD_RESERVE) * K()
    ok(b.head.base:GetStringWidth() <= avail + 1e-6, "the long name fits the header width")
    ok(b.head.base._fontSize < fontFor(C.HEAD_SIZE), "so it shrank")
    ok(b.head.base._fontSize >= C.MIN_FONT, "never under the minimum size")
    eq(b.head.red._fontSize, b.head.base._fontSize, "the red copy fits the same")
    __units.player.name = "Rowan"; __fireEvent("PLAYER_ENTERING_WORLD")
    eq(b.head.base._fontSize, fontFor(C.HEAD_SIZE), "a short name is back at the header size")
    -- a rescale re-fits the held name
    __units.player.name = "Alexandriathegreat"; __fireEvent("PLAYER_ENTERING_WORLD")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9; __fireEvent("UI_SCALE_CHANGED")
    ok(b.head.base:GetStringWidth() <= (MB.base.BOXL.w - C.HEAD_RESERVE) * K() + 1e-6, "still fits after a rescale")
    __units.player.name = nil
end

function T.the_target_box_is_hidden_with_no_target_and_shown_with_one()
    local W = world({ beforeLoad = function() __units.target.exists = false end })
    local b = W.tgt.box
    eq(b.frame._shown, false, "no target at build: hidden"); eq(b.frame:IsVisible(), false)
    __units.target.exists = true; __units.target.name = "Murloc"; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame._shown, true, "a target shows it"); eq(b.l1._text, "MURLOC", "with its name")
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame._shown, false, "target dropped: hidden again")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame._shown, true)
    -- PLAYER_ENTERING_WORLD re-reads it too (the tape, the dots and the horizon do)
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame._shown, false, "setup: hidden")
    __units.target.exists = true; __fireEvent("PLAYER_ENTERING_WORLD")
    eq(b.frame._shown, true, "PLAYER_ENTERING_WORLD shows it for a target")
    __units.target.exists = false; __fireEvent("PLAYER_ENTERING_WORLD")
    eq(b.frame._shown, false, "and hides it for none")
    -- The rule itself (IsSecret asked before any truth test, missing UnitExists) is pinned once in
    -- theme-harness.py; this proves the box goes through it. The mock calls the plain false UnitExists
    -- returns "secret": a truth test would keep the box hidden.
    local plain = FS.IsSecret
    FS.IsSecret = function(v) return v == false or plain(v) end
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame._shown, true, "a value IsSecret flags keeps the box shown")
    W.clean(); noFails()
end

function T.the_target_box_follows_the_target_not_the_cast_and_the_player_box_ignores_the_target()
    local W = world({ beforeLoad = function() __units.target.exists = false end })
    local you, tgt = W.you.box, W.tgt.box
    eq(you.frame._shown, false, "your box does not depend on a target")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(you.frame._shown, false, "gaining a target does not show your idle box")
    eq(tgt.frame._shown, true, "an idle target with no cast still shows its box")
end

function T.a_rescale_does_not_re_show_a_hidden_box()
    local W = world({ beforeLoad = function() __units.target.exists = false end })
    for _, h in ipairs({ 1080, 1440 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
        eq(W.you.box.frame._shown, false, "your idle box stays hidden at " .. h)
        eq(W.tgt.box.frame._shown, false, "the no-target box stays hidden at " .. h)
    end
    W.clean(); noFails()
end

-- ---- the INTERRUPTED look ---------------------------------------------------------------------------

local function has(list, v) for _, r in ipairs(list) do if r == v then return true end end return false end

function T.an_interrupt_shows_the_red_box_with_interrupted_and_a_flicker()
    local W = world()
    local b, S = W.you.box, W.you.S
    eq(b.tones.red._shown, false, "no red at rest"); eq(b.tones.base._shown, true)
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 101.5)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    W.clean(); noFails()
    eq(b.l1._text, "INTERRUPTED", "plain text on line one")
    eq(colourOf(b.l1), MB.CSS.red:sub(2), "in red")
    eq(b.tones.red._shown, true, "the red tone frame is up"); eq(b.tones.base._shown, false, "the cyan one is down")
    eq(b.tileTones.red._shown, true, "the tile edge is red too"); eq(b.tileTones.base._shown, false)
    eq(b.l2.red._text, b.l2.base._text, "the timer text is on the red copy as well")
    eq(colourOf(b.l2.red), MB.CSS.red:sub(2), "red")
    eq(colourOf(b.head.red), MB.CSS.red:sub(2))
    ok(not has(b.fb.pink, b.tones.red) and not has(b.fb.steel, b.tones.red), "the red tone is not in the flag lists")
    ok(not has(b.fb.pink, b.tileTones.red) and not has(b.fb.steel, b.tileTones.red), "nor is its tile edge")
    ok(b.flicker, "one flicker group"); eq(b.flicker.playing, true, "flickering")
    local groups = 0
    for _, g in ipairs(b.frame._groups) do groups = groups + 1 end
    eq(groups, 1, "one AnimationGroup on the box frame")
    eq(#b.flicker._anims, 1 + #FS.GunsightBoxes.C.FLICK, "the delay plus the mockup's steps")
    for i, a in ipairs(b.flicker._anims) do
        eq(a._kind, "Alpha"); eq(a._args.SetOrder[1], i, "in order")
    end
    near(b.flicker._anims[2]._args.SetFromAlpha[1], MB.FLICK[1], 1e-9, "the first step is the mockup's .5")
    near(b.tile._alpha, MB.IDLE_ICON_A, 1e-9, "the icon is dimmed like an interrupted cast's"); eq(b.icon._desat, true)
    -- the outage plays out, GoIdle writes through the sinks: back to the rest look, flicker stopped
    W.stepTo(S, 101.5, 103.2)
    eq(b.l1._text, "", "the cast name is gone at rest, not kept muted")
    eq(b.tones.red._shown, false, "red is gone"); eq(b.tones.base._shown, true)
    eq(b.tileTones.red._shown, false); eq(b.tileTones.base._shown, true)
    eq(b.flicker.playing, false, "flicker stopped")
    for _, fs in pairs(b.l2) do eq(fs._text, "", "no timer text at rest") end
    W.clean(); noFails()
    eq(__countOnUpdates(), 0, "the box added no OnUpdate")
end

function T.the_next_cast_clears_the_interrupted_look()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 101)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(b.l1._text, "INTERRUPTED")
    W.cast("player", "Fear", "C2", 101.2, 1.5); W.fire(S, "UNIT_SPELLCAST_START"); W.at(S, 101.5)
    eq(b.l1._text, "FEAR", "the new spell replaces INTERRUPTED"); eq(colourOf(b.l1), MB.CSS.white:sub(2))
    eq(b.tones.red._shown, false, "no red"); eq(b.tones.base._shown, true)
    eq(b.flicker.playing, false, "no flicker")
    eq(colourOf(b.l2.base), MB.CSS.cyan:sub(2)); eq(b.tile._alpha, 1); eq(b.icon._desat, false)
    W.clean(); noFails()
end

function T.a_failed_cast_and_a_kicked_channel_are_interrupts_too()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 100.5)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_FAILED", "C1")
    eq(b.l1._text, "INTERRUPTED", "FAILED routes to the interrupt")
    W.stepTo(S, 100.5, 103)
    eq(b.tones.red._shown, false)
    channel("player", "Mind Flay", 110, 3); W.fire(S, "UNIT_SPELLCAST_CHANNEL_START"); W.stepTo(S, 110, 111)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_CHANNEL_STOP", "C1", "Kurak")
    eq(b.l1._text, "INTERRUPTED", "a kicked channel too")
    W.clean(); noFails()
end

function T.the_bar_tables_carry_the_boxs_hook_and_a_failed_box_leaves_none()
    local W = world()
    for _, t in ipairs({ W.you, W.tgt }) do
        eq(type(t.box.members.onVerdict), "function", t.key .. ": the box has a hook")
        eq(t.S.onVerdict, t.box.members.onVerdict, t.key .. ": the bar table CastBars drives carries it")
    end
    local W2 = world({ beforeLoad = function()
        local build = FS.Theme.AddCut2Texture
        FS.Theme.AddCut2Texture = function(frame, ...)
            if frame._parent and frame._parent._name == "ForeverSTUwaveGunsightBox_you" then error("box build failed") end
            return build(frame, ...)
        end
    end })
    eq(W2.you.box, nil); eq(W2.you.S.onVerdict, nil, "the alpha 0 sinks have no hook")
    ok(W2.tgt.S.onVerdict, "the other tape keeps its box's")
    W2.cast("player", "Shadow Bolt", "C1", 100, 2.5); W2.fire(W2.you.S, "UNIT_SPELLCAST_START"); W2.stepTo(W2.you.S, 100, 101)
    W2.fire(W2.you.S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W2.you.run:GetPhase(), "intr", "an interrupt without a hook still plays")
    W2.clean()
end

function T.a_success_has_no_red_look()
    local W = world()
    local b, S = W.you.box, W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 102.5)
    W.fire(S, "UNIT_SPELLCAST_STOP", "C1")
    eq(b.tones.red._shown, false); ok(not b.flicker.playing, "no flicker")
    eq(b.l1._text, "SHADOW BOLT")
    W.clean(); noFails()
end

function T.stack_a_never_reaches_a_verdict_hook()
    local W = world({ stripView = true })              -- no view: Stack A draws
    W.clean()
    eq(W.P.onVerdict, nil, "the Stack A player bar has no hook"); eq(W.G.onVerdict, nil, "nor the target's")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(W.P, "UNIT_SPELLCAST_START"); W.stepTo(W.P, 100, 101)
    W.fire(W.P, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    W.clean(); noFails()
    eq(W.you.box.l1._text, "", "the (idle) box was not told"); eq(W.you.box.tones.red._shown, false)
    ok(not W.you.box.flicker.playing, "and no flicker")
end

function T.an_interrupted_target_box_restores_its_unit_name()
    -- A target cast on the plain run path (no strips) can be interrupted too.
    local W = world({ beforeLoad = function() end })
    local b, S = W.tgt.box, W.tgt.S
    target("Kurak")
    S.stripOnly = nil                                  -- take the run path for a plain cast
    W.cast("target", "Fear", "T1", 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 100.5)
    W.endCast("target"); W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "T1")
    W.clean(); noFails()
    eq(b.l1._text, "INTERRUPTED"); eq(colourOf(b.l1), MB.CSS.red:sub(2))
    eq(b.tones.red._shown, true); eq(b.tones.pink._shown, false); eq(b.tones.steel._shown, false)
    noTargetLabel(W, "INTERRUPTED")
    ok(not has(b.fb.pink, b.tones.red) and not has(b.fb.steel, b.tones.red))
    target("Kurak")                                    -- a unit name event while it shows does not overwrite it
    __fireEvent("UNIT_NAME_UPDATE", "target")
    W.stepTo(S, 100.5, 103)
    eq(b.l1._text, "KURAK", "the unit name is back"); eq(colourOf(b.l1), MB.CSS.muted:sub(2))
    eq(b.tones.red._shown, false); eq(b.tones.pink._shown, true); eq(b.tones.steel._shown, true)
    noTargetLabel(W, "after the interrupt cleared")
    W.clean(); noFails()
end

function T.target_name_events_leave_interrupted_on_line_one_until_the_clear()
    -- RefreshTargetName must not overwrite the INTERRUPTED look (box.verdict), only the clear brings the name back.
    local W = world()
    local b, S = W.tgt.box, W.tgt.S
    target("Kurak")
    S.stripOnly = nil                                  -- the run path, so a plain cast can be interrupted
    W.cast("target", "Fear", "T1", 100, 1.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 100.5)
    W.endCast("target"); W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "T1")
    eq(b.l1._text, "INTERRUPTED"); eq(b.tones.red._shown, true)
    -- PLAYER_TARGET_CHANGED through the box's own listener (a full fire would also reach CastBars, whose
    -- target bar drops the old cast on a target change and so ends the look by itself)
    __units.target.name = "Murak"
    b.events._scripts.OnEvent(b.events, "PLAYER_TARGET_CHANGED")
    eq(b.l1._text, "INTERRUPTED", "a target change leaves line one alone")
    eq(colourOf(b.l1), MB.CSS.red:sub(2), "still red")
    __units.target.name = "Zorak"; __fireEvent("UNIT_NAME_UPDATE", "target")
    eq(b.l1._text, "INTERRUPTED", "so does a unit name update")
    eq(b.tones.red._shown, true, "the red look is still up")
    -- the target's timer is a null sink: a write to it neither clears the look nor shows anything
    S.timer:SetText(""); S.timer:SetFormattedText("%.1f / %.1f", 1, 2)
    eq(b.l1._text, "INTERRUPTED", "a timer write does not clear it")
    W.stepTo(S, 100.5, 103)
    eq(b.l1._text, "ZORAK", "after the clear line one is the CURRENT target name")
    eq(colourOf(b.l1), MB.CSS.muted:sub(2)); eq(b.tones.red._shown, false)
    W.clean(); noFails()
end

local function countRescaleRegistrations()
    local box = { n = 0 }
    local on = FS.Layout.OnRescale
    FS.Layout.OnRescale = function(fn)
        if debug.getinfo(fn, "S").short_src:find("GunsightBoxes", 1, true) then box.n = box.n + 1 end
        return on(fn)
    end
    return box
end

function T.a_late_build_failure_registers_no_rescale_callback()
    -- The target box's listener step throws: that box is dropped and must not keep a Layout callback
    -- (the callback cannot be removed). Yours, which builds fine, registers exactly one.
    local W = world({ noLogin = true, beforeLoad = function()
        local Region = getmetatable(UIParent)
        local setScript = Region.SetScript
        function Region:SetScript(k, fn)
            if k == "OnEvent" and self._parent and self._parent._name == "ForeverSTUwaveGunsightBox_tgt" then error("SetScript failed") end
            return setScript(self, k, fn)
        end
    end })
    local reg = countRescaleRegistrations()
    __fireEvent("ADDON_LOADED", "forever-stuwave")
    __fireEvent("PLAYER_LOGIN")
    W.you, W.tgt = FS.GunsightTape.you, FS.GunsightTape.tgt
    W.clean()
    eq(W.tgt.box, nil, "the target box did not build")
    ok(W.you.box, "yours did")
    eq(reg.n, 1, "only the box that built registered a rescale callback")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")                    -- nothing calls into the dropped box
    W.clean()
end

function T.a_rescale_to_a_larger_scale_grows_a_shrunk_name_back_to_the_new_base()
    local W = world()
    local b, S = W.you.box, W.you.S
    local C = FS.GunsightBoxes.C
    W.cast("player", "Searing Pains", "C1", 100, 3); W.fire(S, "UNIT_SPELLCAST_START")
    eq(b.l1._fontSize, fontFor(C.L1_SIZE), "13 characters fit the box at 1440")
    UIParent._h = 765; UIParent._w = 765 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local small = fontFor(C.L1_SIZE)
    ok(b.l1._fontSize < small, "the same name no longer fits at 765 and shrinks below its base " .. small .. ": " .. tostring(b.l1._fontSize))
    UIParent._h = 1440; UIParent._w = 1440 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    eq(b.l1._fontSize, fontFor(C.L1_SIZE), "a larger scale: the shrunk name is back at the new base size")
    eq(b.l1._text, "SEARING PAINS")
    ok(b.l1:GetStringWidth() <= (MB.base.BOXL.w - 2 * C.PAD) * K() + 1e-6, "and it fits")
    W.clean(); noFails()
end

-- ---- the target's HP and power rules (mockup option B, "Underline") ---------------------------------

local function bars(W) return W.tgt.box.bars end
local function fireBar(...) for _, e in ipairs({ ... }) do __fireUnit(e, "target") end end
local function allBarEvents() fireBar("UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER", "UNIT_DISPLAYPOWER") end
local function hexOf(c) return rgb({ c.r or c[1], c.g or c[2], c.b or c[3] }) end
local function mixHex(hex, t)
    local out = {}
    for i = 1, 3 do
        local v = tonumber(hex:sub(2 * i, 2 * i + 1), 16) / 255
        out[i] = v + (1 - v) * t
    end
    return rgb(out)
end
local function countKey(key) local n = 0; for _, k in ipairs(__degrades) do if k == key then n = n + 1 end end; return n end

function T.the_target_bars_sit_under_line_one_at_the_option_b_offsets_at_two_heights()
    local W = world()
    local C = FS.GunsightBoxes.C
    for _, h in ipairs({ 1440, 1080 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        target("Kurak")
        local k = K()
        local box, b = W.tgt.box, bars(W)
        ok(b, "the target box carries its bars")
        local want = math.max(MB.TB_MIN_W * k, box.l1:GetStringWidth())
        for _, r in ipairs({ b.hp.green, b.hp.red }) do
            local p = r.host._points.TOPLEFT
            eq(p.rel, box.frame); eq(p.relPoint, "TOPLEFT")
            near(p.x, MB.TB_X * k, 1e-6, "x = box.x + 7"); near(p.y, -MB.TB_HP_Y * k, 1e-6, "y = box.y + 26")
            near(r.host._w, want, 1e-6, "as wide as the name at " .. h); near(r.host._h, MB.TB_HP_H * k, 1e-6, "3 high")
        end
        local p = b.power.host._points.TOPLEFT
        eq(p.rel, box.frame); near(p.x, MB.TB_X * k, 1e-6); near(p.y, -MB.TB_PW_Y * k, 1e-6, "y = box.y + 30")
        near(b.power.host._w, want, 1e-6); near(b.power.host._h, MB.TB_PW_H * k, 1e-6, "2 high")
        local gap = (-p.y) - (-b.hp.green.host._points.TOPLEFT.y) - b.hp.green.host._h
        near(gap, k, 1e-6, "one image px between the rules")
        ok(-b.hp.green.host._points.TOPLEFT.y > C.L1_Y * k, "the rules sit under line one's baseline")
        eq(b.frame:GetParent(), box.frame, "bars are a child of the box frame")
    end
end

function T.a_rail_has_the_mockups_track_gradient_and_tip_and_the_hp_colours()
    local W = world()
    local C = FS.GunsightBoxes.C
    target("Kurak")
    local k, b = K(), bars(W)
    for name, r in pairs({ green = b.hp.green, red = b.hp.red, power = b.power }) do
        local hex = ({ green = MB.TB_HP_HEX, red = MB.CSS.red, power = MB.TB_PC.mana })[name]
        eq(rgb(r.track._colorTexture), hex:sub(2), name .. ": the track is the bar colour")
        near(r.track._colorTexture[4], MB.TB_TRACK_A, 1e-9, name .. ": at alpha .2")
        eq(r.fill, r.sb:GetStatusBarTexture(), name .. ": the gradient lives on the StatusBar fill")
        local g = r.fill._gradient
        ok(g, name .. ": a gradient"); eq(g[1], "HORIZONTAL")
        eq(hexOf(g[2]), hex:sub(2)); eq(hexOf(g[3]), hex:sub(2))
        near(g[2].a, MB.TB_TAIL_A, 1e-9, "tail alpha .35"); near(g[3].a, 1, 1e-9, "tip alpha 1")
        eq(r.tip._points.TOPRIGHT.rel, r.fill); eq(r.tip._points.TOPRIGHT.relPoint, "TOPRIGHT")
        eq(r.tip._points.BOTTOMRIGHT.rel, r.fill); eq(r.tip._points.BOTTOMRIGHT.relPoint, "BOTTOMRIGHT")
        near(r.tip._w, MB.TB_TIP_W * k, 1e-6, name .. ": a 1.5 image px tip riding the fill's right edge")
        eq(rgb(r.tip._colorTexture), mixHex(hex, MB.TB_TIP_MIX), name .. ": mix(col, white, .55)")
        near(r.tip._colorTexture[4], MB.TB_TIP_A, 1e-9, name .. ": at alpha .9")
    end
    eq(b.hp.red.host._alpha, 0, "the red twin starts invisible"); eq(b.hp.green.host._alpha, 1)
    W.clean(); noFails()
end

function T.a_missing_or_refused_gradient_falls_back_to_a_flat_colour_and_logs_once()
    local setGradient = getmetatable(UIParent).SetGradient
    local missing = world({ beforeLoad = function() getmetatable(UIParent).SetGradient = nil end })
    target("Kurak")
    local r = missing.tgt.box.bars.hp.green
    eq(r.fill._gradient, nil, "no gradient to apply")
    eq(rgb(r.fill._vc), MB.TB_HP_HEX:sub(2), "the flat colour on the fill")
    local W = world({ beforeLoad = function() getmetatable(UIParent).SetGradient = setGradient; __noGradientCall = true end })
    target("Kurak")
    local b = bars(W)
    eq(rgb(b.hp.green.fill._vc), MB.TB_HP_HEX:sub(2), "a refusing SetGradient takes the flat fallback")
    eq(rgb(b.hp.red.fill._vc), MB.CSS.red:sub(2))
    eq(countKey("gunsightboxes_target_gradient"), 1, "and logs once")
end

function T.secret_health_and_power_reach_only_the_setters()
    local W = world()
    local b = bars(W)
    local u = __units.target
    u.hp, u.hpMax, u.pw, u.pwMax = __SECRET, __SECRET, __SECRET, __SECRET
    allBarEvents()
    fireBar("PLAYER_TARGET_CHANGED")
    for _, sb in ipairs({ b.hp.green.sb, b.hp.red.sb, b.power.sb }) do
        ok(rawequal(sb._value, __SECRET), "the value went to SetValue untouched")
        ok(rawequal(sb._max, __SECRET), "and the max to SetMinMaxValues"); eq(sb._min, 0)
    end
    eq(b.power.host:IsShown(), true, "a secret power max keeps the rule shown")
    W.clean(); noFails("a secret operation was swallowed by a pcall")
end

function T.the_step_curve_drives_the_red_and_green_rails_including_exactly_35_percent()
    local W = world()
    local b = bars(W)
    eq(#__curves, 3, "three Step curves are built: low, its inverse and the empty-tip one")
    local low, base = __curves[1], __curves[2]
    eq(low.type, Enum.LuaCurveType.Step); eq(base.type, Enum.LuaCurveType.Step)
    eq(#low.pts, 2); eq(low.pts[1][1], 0); eq(low.pts[1][2], 1); near(low.pts[2][1], MB.TB_LOW + MB.LOW_EPS, 1e-12); eq(low.pts[2][2], 0)
    eq(base.pts[1][2], 0); eq(base.pts[2][2], 1, "the inverse curve goes on the green rail")
    local function at(pct, red, green, msg)
        __units.target.pct = pct
        fireBar("UNIT_HEALTH")
        eq(b.hp.red.host._alpha, red, msg .. ": red"); eq(b.hp.green.host._alpha, green, msg .. ": green")
    end
    at(0.62, 0, 1, "62%")
    at(0.36, 0, 1, "36%")
    at(MB.TB_LOW, 1, 0, "exactly 35%")
    at(0.20, 1, 0, "20%")
    at(0, 1, 0, "dead")
    -- the engine may hand back a secret alpha: it goes to SetAlpha as it is
    __curveSecret = true
    fireBar("UNIT_HEALTH")
    ok(rawequal(b.hp.red.host._alpha, __SECRET) and rawequal(b.hp.green.host._alpha, __SECRET), "a secret curve result reaches SetAlpha untouched")
    W.clean(); noFails()
end

function T.the_tip_hides_at_an_empty_bar_through_a_step_curve()
    local W = world()
    local b, u = bars(W), __units.target
    local empty = __curves[3]
    eq(#empty.pts, 2); eq(empty.pts[1][1], 0); eq(empty.pts[1][2], 0)
    near(empty.pts[2][1], MB.LOW_EPS, 1e-12, "EPSILON 0.0005"); eq(empty.pts[2][2], 1)
    local function tips(hp, msg)
        u.pct = hp; fireBar("UNIT_HEALTH")
        eq(b.hp.green.tip._alpha, hp == 0 and 0 or 1, msg .. ": green tip"); eq(b.hp.red.tip._alpha, hp == 0 and 0 or 1, msg .. ": red tip")
    end
    tips(0.62, "62%"); tips(0.0005, "just above empty"); tips(0, "empty"); tips(0.62, "refilled")
    eq(rgb(b.hp.green.tip._colorTexture), mixHex(MB.TB_HP_HEX, MB.TB_TIP_MIX), "the colour is not touched")
    -- power: the shared FrameHelpers helper drives the power tip
    eq(__emptyCalls[#__emptyCalls].host, b.power.tip); eq(__emptyCalls[#__emptyCalls].unit, "target")
    u.pw = 0; fireBar("UNIT_POWER_UPDATE"); eq(b.power.tip._alpha, 0, "empty power hides the power tip")
    u.pw = 70; fireBar("UNIT_POWER_UPDATE"); eq(b.power.tip._alpha, 1)
    W.clean(); noFails()
end

function T.a_refused_tip_curve_leaves_the_tips_visible_logs_once_and_latches()
    local W2 = world()
    local b2, u2 = bars(W2), __units.target
    __curveRefuses = true; u2.pct = 0
    fireBar("UNIT_HEALTH", "UNIT_MAXHEALTH")
    eq(b2.hp.green.tip._alpha, 1, "visible after a refusal"); eq(b2.hp.red.tip._alpha, 1)
    eq(countKey("gunsightboxes_target_tip"), 1, "logged once")
    __curveRefuses = false; __curveCalls = 0
    fireBar("UNIT_HEALTH")
    eq(__curveCalls, 0, "the failure latched")
    eq(countKey("gunsightboxes_target_tip"), 1)
end

function T.without_the_curve_api_or_the_helper_the_tips_stay_visible_silently()
    local W3 = world({ beforeLoad = function() C_CurveUtil = nil; FS.FrameHelpers.UpdatePowerHostEmpty = nil end })
    __units.target.pct, __units.target.pw = 0, 0
    fireBar("UNIT_HEALTH", "UNIT_POWER_UPDATE")
    eq(bars(W3).hp.green.tip._alpha, 1, "no curve API: the tip stays visible"); eq(bars(W3).power.tip._alpha, 1, "no helper: so does the power tip")
    eq(countKey("gunsightboxes_target_tip"), 0)
end

function T.a_refused_curve_latches_logs_once_and_falls_back_to_a_plain_compare()
    local W = world()
    local b, u = bars(W), __units.target
    __curveRefuses = true
    u.hp, u.hpMax = 35, 100
    fireBar("UNIT_HEALTH")
    eq(b.hp.red.host._alpha, 1, "35/100 is low on the plain path"); eq(b.hp.green.host._alpha, 0)
    eq(countKey("gunsightboxes_target_lowhp"), 1, "logged")
    local fails = #__pcallFails
    __curveRefuses = false; __curveCalls = 0
    u.hp = 36
    fireBar("UNIT_HEALTH", "UNIT_MAXHEALTH")
    eq(b.hp.red.host._alpha, 0, "36/100 is not"); eq(b.hp.green.host._alpha, 1)
    eq(__curveCalls, 0, "the failure latched: the curve is not asked again")
    eq(countKey("gunsightboxes_target_lowhp"), 1, "and logged once")
    eq(#__pcallFails, fails, "no further failure")
    u.hp, u.hpMax = __SECRET, __SECRET
    fireBar("UNIT_HEALTH")
    eq(b.hp.red.host._alpha, 0, "secret health: red stays down"); eq(b.hp.green.host._alpha, 1, "and green stays up")
    -- a client with no curve API at all takes the same compare, without a log
    local logged = countKey("gunsightboxes_target_lowhp")
    local W2 = world({ beforeLoad = function() C_CurveUtil = nil end })
    __units.target.hp, __units.target.hpMax = 20, 100
    fireBar("UNIT_HEALTH")
    eq(bars(W2).hp.red.host._alpha, 1, "no curve API: the plain compare")
    eq(countKey("gunsightboxes_target_lowhp"), logged, "and nothing more to complain about")
end

function T.the_power_rule_hides_for_no_power_and_stays_for_a_secret_max()
    local W = world()
    local b, u = bars(W), __units.target
    eq(b.power.host:IsShown(), true, "a mana bar shows")
    u.pwMax = 0; fireBar("UNIT_MAXPOWER")
    eq(b.power.host:IsShown(), false, "a plain max of 0 hides the rule")
    eq(b.hp.green.host:IsShown(), true, "the HP rule stays")
    u.pwMax = __SECRET; fireBar("UNIT_MAXPOWER")
    eq(b.power.host:IsShown(), true, "a secret max keeps it shown")
    u.pwMax = 100; u.ptype = -1; fireBar("UNIT_DISPLAYPOWER")
    eq(b.power.host:IsShown(), false, "no power type hides it")
    u.ptype = 0; fireBar("UNIT_DISPLAYPOWER")
    eq(b.power.host:IsShown(), true)
    W.clean(); noFails()
end

function T.the_power_rail_wears_the_power_type_colour()
    local W = world()
    local b, u = bars(W), __units.target
    local want = { [0] = MB.TB_PC.mana, [1] = MB.TB_PC.rage, [2] = MB.TB_PC.focus, [3] = MB.CSS.gold, [99] = MB.TB_PC.mana }
    for _, ptype in ipairs({ 1, 2, 3, 0, 99 }) do
        u.ptype = ptype
        fireBar("UNIT_DISPLAYPOWER")
        local hex = want[ptype]:sub(2)
        eq(rgb(b.power.track._colorTexture), hex, "type " .. ptype .. ": the track")
        eq(hexOf(b.power.fill._gradient[3]), hex, "type " .. ptype .. ": the fill")
        eq(rgb(b.power.tip._colorTexture), mixHex(want[ptype], MB.TB_TIP_MIX), "type " .. ptype .. ": the tip")
    end
    W.clean(); noFails()
end

function T.a_throwing_bar_update_never_drops_the_box_and_logs_once()
    -- UnitHealth throws on this "client": the build, the name refresh and the events all go on.
    local W = world({ beforeLoad = function() function UnitHealth() error("boom") end end })
    local box = W.tgt.box
    ok(box, "the box still built")
    eq(box.grow, FS.GunsightBoxes.C.TGT_GROW, "and carries its grow for the KICK tag"); eq(W.you.box.grow, 0, "yours grows nothing")
    target("Kurak")
    eq(box.l1._text, "KURAK", "the name refresh still runs")
    fireBar("UNIT_HEALTH", "UNIT_MAXHEALTH")
    eq(countKey("gunsightboxes_target_bars"), 1, "logged once")
    eq(box.events._scripts.OnEvent ~= nil and box.barEvents._scripts.OnEvent ~= nil, true, "listeners stay up")
end

function T.the_unfiltered_bar_event_fallback_ignores_other_units()
    local W = world({ beforeLoad = function() getmetatable(UIParent).RegisterUnitEvent = function() error("no unit events") end end })
    local b, u = bars(W), __units.target
    eq(next(W.tgt.box.barEvents._unitEvents or {}), nil, "the unit whitelist was refused")
    u.hp = 11
    __fireUnit("UNIT_HEALTH", "party1")
    ok(b.hp.green.sb._value ~= 11, "another unit's event leaves the bars alone")
    __fireUnit("UNIT_HEALTH", __SECRET_NAME)
    eq(b.hp.green.sb._value, 11, "a secret unit is not inspected and reads on")
    u.hp = 12
    __fireUnit("UNIT_HEALTH", "target")
    eq(b.hp.green.sb._value, 12, "the target's does")
end

function T.the_bar_width_is_the_name_width_and_the_full_text_width_for_a_secret_name()
    local W = world()
    local b, box = bars(W), W.tgt.box
    local k = K()
    local wmax = (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * k
    target("Kurak")
    near(b.hp.green.host._w, box.l1:GetStringWidth(), 1e-6, "a plain name: its measured width")
    near(b.power.host._w, box.l1:GetStringWidth(), 1e-6, "for both rules")
    target("Al")
    near(b.hp.green.host._w, MB.TB_MIN_W * k, 1e-6, "a short name: the 24 image px floor")
    target("Archmage Antonidas the Great")
    ok(b.hp.green.host._w <= wmax + 1e-6, "a long name is fitted, and so is the bar")
    near(b.hp.green.host._w, box.l1:GetStringWidth(), 1e-6)
    target("Kurak")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    near(b.hp.green.host._w, box.l1:GetStringWidth(), 1e-6, "a rescale measures it again")
    ok(b.hp.green.host._w < 49, "at the smaller type")
    secretUnit(); __fireEvent("PLAYER_TARGET_CHANGED")
    near(b.hp.green.host._w, (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * K(), 1e-6, "a secret name: the full text width")
    __fireEvent("UNIT_NAME_UPDATE", "target")
    UIParent._h = 1440; UIParent._w = 1440 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    near(b.power.host._w, (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * K(), 1e-6, "also after a rescale")
    W.clean(); noFails("a secret name was measured")
end

function T.target_events_refresh_the_bars_and_only_for_the_target_unit()
    local W = world()
    local b, box, u = bars(W), W.tgt.box, __units.target
    local be = box.barEvents
    ok(be, "a listener frame for the bar events")
    for _, e in ipairs({ "UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER", "UNIT_DISPLAYPOWER" }) do
        eq(be._unitEvents[e], "target", e .. " is registered for the target unit")
    end
    u.hp = 40; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.hp.green.sb._value, 40, "a target change reads the bars"); eq(b.hp.green.sb._max, 100)
    u.hp = 41; fireBar("UNIT_HEALTH"); eq(b.hp.red.sb._value, 41, "UNIT_HEALTH feeds the red twin too")
    u.hpMax = 120; fireBar("UNIT_MAXHEALTH"); eq(b.hp.green.sb._max, 120)
    u.pw = 55; fireBar("UNIT_POWER_UPDATE"); eq(b.power.sb._value, 55)
    u.pwMax = 80; fireBar("UNIT_MAXPOWER"); eq(b.power.sb._max, 80)
    u.hp = 7; __fireEvent("PLAYER_ENTERING_WORLD"); eq(b.hp.green.sb._value, 7, "so does entering the world")
    eq(b.frame:IsVisible(), true, "the bars show with the box")
    u.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.frame:IsVisible(), false, "and hide with it when the target goes")
    u.hp = 99; fireBar("UNIT_HEALTH")
    eq(b.hp.green.sb._value, 7, "no target: nothing is read")
    eq(__countOnUpdates(), 0, "no OnUpdate")
    W.clean(); noFails()
end

function T.a_failing_bar_listener_unregisters_and_a_retired_box_ignores_bar_events()
    local W = world({ beforeLoad = function()
        local Region = getmetatable(UIParent)
        local setScript, n = Region.SetScript, 0
        function Region:SetScript(k, fn)
            if k == "OnEvent" and self._parent and self._parent._name == "ForeverSTUwaveGunsightBox_tgt" then
                n = n + 1
                if n == 2 then error("bar listener SetScript failed") end
            end
            return setScript(self, k, fn)
        end
    end })
    eq(W.tgt.box, nil, "the box did not build")
    for _, o in ipairs(__all) do
        if o._parent and o._parent._name == "ForeverSTUwaveGunsightBox_tgt" and o._events then
            eq(next(o._events), nil, "nothing stays registered on either listener")
            eq(next(o._unitEvents or {}), nil, "no unit event either")
        end
    end
    local W2 = world()
    local box = W2.tgt.box
    local stale = box.barEvents._scripts.OnEvent
    FS.GunsightBoxes.Retire(box)
    eq(next(box.barEvents._unitEvents), nil, "Retire takes the bar listener down")
    __units.target.hp = 11
    stale(box.barEvents, "UNIT_HEALTH", "target")
    eq(box.bars.hp.green.sb._value, 62, "a stale call writes nothing")
end

function T.the_player_box_has_no_bars_and_keeps_its_timer_line_at_18()
    local W = world()
    local b = W.you.box
    eq(b.bars, nil); eq(b.barEvents, nil)
    near(b.frame._points.TOPLEFT.y, 0, 1e-9, "its frame is not grown")
    for _, fs in pairs(b.l2) do eq(fs._fontSize, fontFor(MB.L2_SIZE), "the timer stays 18") end
    eq(b.lineTwo.baseImg, MB.L2_SIZE)
    eq(W.tgt.box.lineTwo.baseImg, MB.TGT_L2_SIZE, "the target's spell line fits from 14")
end

-- ---- the target bar settings (FS.Config gunsight.targetBars.*, the config window's controls) ------------

local function S() return FS.GunsightBoxes.SETTINGS end
local function flush() FS.GunsightBoxes.Flush() end    -- the one-shot OnUpdate a setting change schedules
local function setting(name, value) FS.Config.Set(S()[name].key, value); flush() end
local function hpPx(v) return v * FS.GunsightBoxes.C.BAR_PX end
local function textOf(fs) return fs._text end
local function numbersOn(format)
    setting("numbers", true)
    if format then setting("numberFormat", format) end
end
local function pctWidth(W, pct)       -- the rule width a width setting should give, from the name width
    local k = K()
    local wmax = (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * k
    return math.min(wmax, W.tgt.box.l1:GetStringWidth() * pct / 100)
end

function T.the_settings_default_to_the_mockups_values_and_draw_todays_rails()
    local W = world()
    local C, s = FS.GunsightBoxes.C, S()
    eq(s.hpHeight.default, MB.CFG.HEALTH, "the config mockup's health default"); eq(s.powerHeight.default, MB.CFG.RESOURCE)
    eq(s.width.default, MB.CFG.WIDTH)
    -- a slider px is half a mockup image px, so the config mockup's defaults are the option B rails (3 and 2)
    near(hpPx(s.hpHeight.default), MB.TB_HP_H, 1e-9, "6 px renders as the 3 image px rail")
    near(hpPx(s.powerHeight.default), MB.TB_PW_H, 1e-9, "4 px renders as the 2 image px rail")
    eq(C.TB_GAP, MB.TB_PW_Y - MB.TB_HP_Y - MB.TB_HP_H, "the gap between the rules is the mockup's")
    for name, def in pairs(s) do
        if type(def) == "table" and def.key then
            eq(FS.Config.Get(def.key), def.default, name .. " reads its default")
            ok(not FS.Config.IsStored(def.key), name .. " pins nothing")
        end
    end
    -- the config mockup's track positions are where the defaults sit in the ranges
    for _, pair in ipairs({ { s.hpHeight, MB.CFG.HEALTH_P }, { s.powerHeight, MB.CFG.RESOURCE_P }, { s.width, MB.CFG.WIDTH_P } }) do
        near((pair[1].default - pair[1].min) / (pair[1].max - pair[1].min) * 100, pair[2], 1e-9, pair[1].key .. " range")
    end
    eq(s.hpHeight.step, 1); eq(s.powerHeight.step, 1); ok(s.width.step >= 1)
    eq(s.numbers.default, false, "no numbers until asked: approved visuals do not change")
    eq(s.numberFormat.default, "both")
    local fmts = FS.GunsightBoxes.NUMBER_FORMATS
    eq(#fmts, #MB.CFG.FORMAT_OPTIONS)
    for i, text in ipairs(MB.CFG.FORMAT_OPTIONS) do eq(fmts[i].text, text, "format label " .. i) end
    eq(fmts[2].text, MB.CFG.FORMAT_SELECTED); eq(fmts[2].value, s.numberFormat.default, "the mockup's selected format is the default")
    eq(C.NUM_SIZE > 0, true)
    W.clean(); noFails()
end

function T.with_the_defaults_no_number_text_is_shown_or_written()
    local calls = 0
    local W = world({ beforeLoad = function()
        local Region = getmetatable(UIParent)
        local real = Region.SetFormattedText
        function Region:SetFormattedText(...) calls = calls + 1; return real(self, ...) end
    end })
    target("Kurak")
    allBarEvents()
    local b = bars(W)
    eq(b.hpText:IsShown(), false); eq(b.powerText:IsShown(), false)
    eq(textOf(b.hpText), ""); eq(textOf(b.powerText), "")
    eq(calls, 0, "numbers off: no SetFormattedText at all")
    W.clean(); noFails()
end

function T.bar_heights_apply_live_and_the_power_rule_rides_under_the_health_rule()
    local W = world()
    local C = FS.GunsightBoxes.C
    target("Kurak")
    local k, b = K(), bars(W)
    setting("hpHeight", 10)
    for _, r in ipairs({ b.hp.green, b.hp.red }) do
        near(r.host._h, hpPx(10) * k, 1e-6, "health rule 5 image px"); near(r.host._points.TOPLEFT.y, -C.TB_HP_Y * k, 1e-6)
    end
    near(b.power.host._points.TOPLEFT.y, -(C.TB_HP_Y + hpPx(10) + C.TB_GAP) * k, 1e-6, "the power rule keeps its one px gap")
    near(b.power.host._h, MB.TB_PW_H * k, 1e-6, "its own height is untouched")
    setting("powerHeight", 12)
    near(b.power.host._h, hpPx(12) * k, 1e-6, "power rule 6 image px")
    near(b.hp.green.host._h, hpPx(10) * k, 1e-6, "health untouched by the power slider")
    setting("hpHeight", nil); setting("powerHeight", nil)
    for _, r in ipairs({ b.hp.green, b.hp.red }) do near(r.host._h, MB.TB_HP_H * k, 1e-6, "back to 3") end
    near(b.power.host._points.TOPLEFT.y, -MB.TB_PW_Y * k, 1e-6, "back to y = 30")
    near(b.power.host._h, MB.TB_PW_H * k, 1e-6, "back to 2")
    W.clean(); noFails()
end

function T.bar_size_settings_survive_a_rescale()
    local W = world()
    target("Kurak")
    setting("hpHeight", 8); setting("powerHeight", 6); setting("width", 60)
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    local k, b = K(), bars(W)
    near(b.hp.green.host._h, hpPx(8) * k, 1e-6); near(b.power.host._h, hpPx(6) * k, 1e-6)
    near(b.hp.green.host._w, pctWidth(W, 60), 1e-6, "width follows the setting after a rescale")
    W.clean(); noFails()
end

function T.bar_width_is_a_percent_of_the_name_width_clamped_to_the_text_width()
    local W = world()
    target("Kurak")
    local b = bars(W)
    setting("width", 50)
    near(b.hp.green.host._w, pctWidth(W, 50), 1e-6, "half the name width"); near(b.power.host._w, pctWidth(W, 50), 1e-6, "both rules")
    near(b.hp.red.host._w, pctWidth(W, 50), 1e-6, "and the red twin")
    setting("width", 150)
    near(b.hp.green.host._w, pctWidth(W, 150), 1e-6)
    target("Archmage Antonidas the Great")
    local wmax = (MB.base.BOXR.w - 2 * FS.GunsightBoxes.C.PAD) * K()
    near(b.hp.green.host._w, wmax, 1e-6, "never wider than the box text")
    secretUnit(); __fireEvent("PLAYER_TARGET_CHANGED")
    setting("width", 50)
    near(b.hp.green.host._w, wmax * 0.5, 1e-6, "a secret name has the full text width, so half of it")
    setting("width", 100)
    near(b.hp.green.host._w, wmax, 1e-6)
    W.clean(); noFails("a secret name was measured")
end

function T.junk_and_out_of_range_settings_read_as_the_default_or_the_nearest_end()
    local W = world()
    target("Kurak")
    local k, b, s = K(), bars(W), S()
    setting("hpHeight", "tall")
    near(b.hp.green.host._h, MB.TB_HP_H * k, 1e-6, "a string reads as the default")
    setting("hpHeight", 99)
    near(b.hp.green.host._h, hpPx(s.hpHeight.max) * k, 1e-6, "clamped to the maximum")
    setting("hpHeight", -4)
    near(b.hp.green.host._h, hpPx(s.hpHeight.min) * k, 1e-6, "clamped to the minimum")
    setting("width", 0 / 0)
    near(b.hp.green.host._w, pctWidth(W, s.width.default), 1e-6, "NaN reads as the default")
    setting("numbers", "yes")
    eq(b.hpText:IsShown(), false, "only a real true turns numbers on")
    setting("numbers", true); setting("numberFormat", "bogus")
    eq(textOf(b.hpText), "62 / 100", "an unknown format reads as the default")
    W.clean(); noFails()
end

function T.numbers_sit_outside_the_box_at_its_outer_end_one_line_under_the_other()
    local W = world()
    local C = FS.GunsightBoxes.C
    target("Kurak")
    numbersOn()
    local k, b, box = K(), bars(W), W.tgt.box
    eq(b.hpText:GetParent(), b.frame, "numbers belong to the bars frame (they go with the target)")
    local hp, pw = b.hpText._points.BOTTOMLEFT, b.powerText._points.BOTTOMLEFT
    eq(hp.rel, box.frame); eq(hp.relPoint, "TOPRIGHT"); near(hp.x, C.NUM_GAP * k, 1e-6, "past the outer edge")
    eq(pw.rel, box.frame); eq(pw.relPoint, "TOPRIGHT"); near(pw.x, C.NUM_GAP * k, 1e-6)
    local hpBase = C.TB_HP_Y + hpPx(S().hpHeight.default)
    near(hp.y, -(hpBase + C.NUM_SIZE * C.DESCENT) * k, 1e-6, "health number on the health rule's bottom edge")
    near(pw.y, -(hpBase + C.NUM_SIZE + C.NUM_LINE + C.NUM_SIZE * C.DESCENT) * k, 1e-6, "power number one line below")
    eq(b.hpText._fontSize, fontFor(C.NUM_SIZE)); eq(b.powerText._fontSize, fontFor(C.NUM_SIZE))
    eq(b.hpText._justifyH, "LEFT")
    setting("hpHeight", 12)
    local hp2 = b.hpText._points.BOTTOMLEFT
    near(hp2.y, -(C.TB_HP_Y + hpPx(12) + C.NUM_SIZE * C.DESCENT) * k, 1e-6, "the numbers follow a taller health rule")
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    eq(b.hpText._fontSize, fontFor(C.NUM_SIZE), "and a rescale resizes the type")
    near(b.hpText._points.BOTTOMLEFT.x, C.NUM_GAP * K(), 1e-6)
    W.clean(); noFails()
end

function T.the_three_formats_write_current_current_over_max_and_percent()
    local W = world()
    target("Kurak")
    local b = bars(W)
    numbersOn()
    eq(b.hpText:IsShown(), true); eq(b.powerText:IsShown(), true)
    eq(textOf(b.hpText), "62 / 100", "current / max is the default"); eq(textOf(b.powerText), "70 / 100")
    setting("numberFormat", "current")
    eq(textOf(b.hpText), "62"); eq(textOf(b.powerText), "70")
    setting("numberFormat", "percent")
    eq(textOf(b.hpText), "62%", "percent comes from the engine's UnitHealthPercent")
    eq(textOf(b.powerText), "70%", "and UnitPowerPercent")
    setting("numberFormat", "both")
    eq(textOf(b.hpText), "62 / 100")
    W.clean(); noFails()
end

function T.numbers_follow_health_and_power_events_and_each_format()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    numbersOn("both")
    u.hp = 41; fireBar("UNIT_HEALTH"); eq(textOf(b.hpText), "41 / 100")
    u.hpMax = 120; fireBar("UNIT_MAXHEALTH"); eq(textOf(b.hpText), "41 / 120")
    u.pw = 55; fireBar("UNIT_POWER_UPDATE"); eq(textOf(b.powerText), "55 / 100")
    u.pwMax = 80; fireBar("UNIT_MAXPOWER"); eq(textOf(b.powerText), "55 / 80")
    setting("numberFormat", "percent")
    u.pct = 0.41; u.pwPct = 0.55
    fireBar("UNIT_HEALTH", "UNIT_POWER_UPDATE")
    eq(textOf(b.hpText), "41%"); eq(textOf(b.powerText), "55%")
    W.clean(); noFails()
end

function T.numbers_hide_with_the_target_and_the_power_number_hides_with_the_power_rule()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    numbersOn()
    eq(b.powerText:IsShown(), true)
    u.pwMax = 0; fireBar("UNIT_MAXPOWER")
    eq(b.powerText:IsShown(), false, "no power, no power number"); eq(b.hpText:IsShown(), true)
    u.pwMax = 100; fireBar("UNIT_MAXPOWER")
    eq(b.powerText:IsShown(), true)
    u.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(b.hpText:IsVisible(), false, "the numbers go with the bars when the target goes")
    W.clean(); noFails()
end

function T.turning_numbers_off_clears_and_stops_the_writes()
    local calls = 0
    local W = world({ beforeLoad = function()
        local Region = getmetatable(UIParent)
        local real = Region.SetFormattedText
        function Region:SetFormattedText(...) calls = calls + 1; return real(self, ...) end
    end })
    target("Kurak")
    local b = bars(W)
    numbersOn()
    ok(calls > 0, "numbers on writes")
    setting("numbers", false)
    eq(b.hpText:IsShown(), false); eq(b.powerText:IsShown(), false)
    eq(textOf(b.hpText), ""); eq(textOf(b.powerText), "")
    calls = 0
    allBarEvents()
    eq(calls, 0, "numbers off again: nothing written")
    W.clean(); noFails()
end

function T.secret_health_and_power_numbers_reach_only_formatted_text_sinks()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    u.hp, u.hpMax, u.pw, u.pwMax = __SECRET, __SECRET, __SECRET, __SECRET
    numbersOn("both")
    for _, format in ipairs({ "both", "current" }) do
        setting("numberFormat", format)
        allBarEvents()
        fireBar("PLAYER_TARGET_CHANGED")
        eq(b.hpText._secretText, true, format .. ": the secret health went to SetFormattedText untouched")
        eq(b.powerText._secretText, true, format .. ": and the secret power")
    end
    -- percent with a plain percent from the engine: the secret values are never touched at all
    setting("numberFormat", "percent")
    allBarEvents()
    eq(textOf(b.hpText), "62%", "the percent is the engine's, not computed from the secret health")
    eq(textOf(b.powerText), "70%")
    -- percent: the engine hands back a secret percent, which also only reaches the setter
    __curveSecret = true
    allBarEvents()
    eq(b.hpText._secretText, true, "a secret percent goes straight to SetFormattedText")
    eq(b.powerText._secretText, true)
    __curveSecret = false
    eq(countKey("gunsightboxes_target_numbers"), 0, "nothing was refused")
    W.clean(); noFails("a secret operation was swallowed by a pcall")
end

function T.percent_never_divides_a_secret_and_falls_back_to_a_blank_when_the_engine_refuses()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    u.hp, u.hpMax, u.pw, u.pwMax = __SECRET, __SECRET, __SECRET, __SECRET
    numbersOn("percent")
    local healthCalls = 0
    local real = UnitHealthPercent
    UnitHealthPercent = function(...) healthCalls = healthCalls + 1; return real(...) end
    __curveRefuses, __powerCurveRefuses = true, true
    allBarEvents()
    eq(textOf(b.hpText), "", "no percent from a secret without the engine: blank, not arithmetic")
    eq(textOf(b.powerText), "")
    eq(countKey("gunsightboxes_target_health_percent"), 1, "the health refusal is logged once")
    eq(countKey("gunsightboxes_target_power_percent"), 1, "and the power one")
    local after = healthCalls
    allBarEvents()
    eq(healthCalls, after, "every refused path is latched: no retry")
    eq(countKey("gunsightboxes_target_health_percent"), 1, "and not logged again")
    __pcallFails = {}
    -- with plain values the same refusal falls back to a plain compare
    u.hp, u.hpMax, u.pw, u.pwMax = 30, 120, 25, 50
    allBarEvents()
    eq(textOf(b.hpText), "25%", "30 / 120"); eq(textOf(b.powerText), "50%", "25 / 50")
    UnitHealthPercent = real
    W.clean()
end

function T.percent_without_the_percent_apis_uses_a_plain_compare_or_stays_blank()
    local W = world({ beforeLoad = function() UnitHealthPercent, UnitPowerPercent = nil, nil end })
    target("Kurak")
    local b, u = bars(W), __units.target
    numbersOn("percent")
    eq(textOf(b.hpText), "62%", "62 / 100 in plain numbers"); eq(textOf(b.powerText), "70%")
    u.hp, u.pw = __SECRET, __SECRET
    allBarEvents()
    eq(textOf(b.hpText), "", "a secret cannot be divided: blank"); eq(textOf(b.powerText), "")
    W.clean(); noFails()
end

function T.percent_uses_the_clients_scale_to_100_curve_when_it_has_one()
    local W = world({ beforeLoad = function() CurveConstants = { ScaleTo100 = { pts = { { 0, 0 }, { 1, 100 } }, type = Enum.LuaCurveType.Linear } } end })
    local before = #__curves
    target("Kurak")
    numbersOn("percent")
    eq(textOf(bars(W).hpText), "62%")
    eq(#__curves, before, "no curve of ours was built")
    CurveConstants = nil
end

function T.the_percent_curve_is_built_only_when_percent_is_used_and_only_once()
    local W = world()
    target("Kurak")
    eq(#__curves, 3, "the three Step curves of the rails and nothing else")
    numbersOn("both")
    eq(#__curves, 3, "current / max builds nothing")
    setting("numberFormat", "percent")
    eq(#__curves, 4, "percent builds one Linear curve")
    eq(__curves[4].type, Enum.LuaCurveType.Linear)
    allBarEvents(); setting("numberFormat", "current"); setting("numberFormat", "percent")
    eq(#__curves, 4, "and reuses it")
    W.clean(); noFails()
end

function T.a_refused_number_write_latches_the_numbers_off_and_logs_once()
    local W = world()
    target("Kurak")
    local b = bars(W)
    local calls = 0
    local Region = getmetatable(UIParent)
    local real = Region.SetFormattedText
    function Region:SetFormattedText(...) calls = calls + 1; error("secret refused") end
    numbersOn("both")
    eq(countKey("gunsightboxes_target_numbers"), 1, "logged once")
    eq(textOf(b.hpText), "", "cleared")
    local after = calls
    allBarEvents(); setting("numberFormat", "current")
    eq(calls, after, "not retried after the latch")
    eq(countKey("gunsightboxes_target_numbers"), 1)
    Region.SetFormattedText = real
    eq(W.tgt.box.retired, nil, "the box is alive")
    eq(b.frame:IsVisible(), true)
    __pcallFails = {}
    W.clean()
end

function T.non_number_values_blank_the_text_instead_of_throwing()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    numbersOn("both")
    u.hp, u.hpMax = nil, nil
    fireBar("UNIT_HEALTH")
    eq(textOf(b.hpText), "", "nil health: blank")
    eq(countKey("gunsightboxes_target_numbers"), 0, "and nothing latched")
    u.hp, u.hpMax = 62, 100
    fireBar("UNIT_HEALTH")
    eq(textOf(b.hpText), "62 / 100")
    W.clean(); noFails()
end

function T.a_nil_percent_blanks_one_tick_without_latching_and_the_next_valid_one_renders()
    local W = world()
    target("Kurak")
    local b, u = bars(W), __units.target
    numbersOn("percent")
    eq(textOf(b.hpText), "62%"); eq(textOf(b.powerText), "70%")
    local real, realPower = UnitHealthPercent, UnitPowerPercent
    local returnNil = true
    UnitHealthPercent = function(unit, predicted, curve)
        if returnNil and curve.type == Enum.LuaCurveType.Linear then return nil end
        return real(unit, predicted, curve)
    end
    UnitPowerPercent = function(unit, ptype, predicted, curve)
        if returnNil and curve.type == Enum.LuaCurveType.Linear then return nil end
        return realPower(unit, ptype, predicted, curve)
    end
    allBarEvents()
    eq(textOf(b.hpText), "", "no percent this tick: blank"); eq(textOf(b.powerText), "")
    returnNil = false
    u.pct, u.pwPct = 0.5, 0.25
    allBarEvents()
    eq(textOf(b.hpText), "50%", "the next valid percent renders: nothing was latched")
    eq(textOf(b.powerText), "25%")
    eq(countKey("gunsightboxes_target_health_percent"), 0, "nothing logged"); eq(countKey("gunsightboxes_target_power_percent"), 0)
    UnitHealthPercent, UnitPowerPercent = real, realPower
    W.clean(); noFails()
end

function T.a_profile_switch_applies_the_settings_live()
    local W = world({ beforeLoad = function() UnitGUID = function() return "Player-1-AAAA" end end })
    target("Kurak")
    local k, b = K(), bars(W)
    FS.Config.NewProfile("Raid")
    ok(FS.Config.SetActiveProfile("Raid"), "the character is known")
    flush()
    setting("hpHeight", 10); setting("numbers", true)
    near(b.hp.green.host._h, hpPx(10) * k, 1e-6); eq(b.hpText:IsShown(), true)
    FS.Config.SetActiveProfile("Default")
    flush()
    near(b.hp.green.host._h, MB.TB_HP_H * k, 1e-6, "Default still has the rails as designed")
    eq(b.hpText:IsShown(), false)
    FS.Config.SetActiveProfile("Raid")
    flush()
    near(b.hp.green.host._h, hpPx(10) * k, 1e-6); eq(textOf(b.hpText), "62 / 100")
    W.clean(); noFails()
end

function T.one_profile_switch_costs_one_seat_and_one_refresh_per_box()
    local W = world({ beforeLoad = function() UnitGUID = function() return "Player-1-AAAA" end end })
    target("Kurak")
    local k, b = K(), bars(W)
    FS.Config.NewProfile("Raid")
    ok(FS.Config.SetActiveProfile("Raid"), "the character is known")
    flush()
    for _, name in ipairs({ "hpHeight", "powerHeight", "width", "numbers", "numberFormat" }) do
        FS.Config.Set(S()[name].key, ({ hpHeight = 10, powerHeight = 8, width = 70, numbers = true, numberFormat = "percent" })[name])
    end
    flush()
    FS.Config.SetActiveProfile("Default")
    flush()
    local seats, reads = 0, 0
    local realHealth = UnitHealth
    local host = b.hp.green.host
    local realClear = host.ClearAllPoints
    host.ClearAllPoints = function(self, ...) seats = seats + 1; return realClear(self, ...) end
    UnitHealth = function(...) reads = reads + 1; return realHealth(...) end
    FS.Config.SetActiveProfile("Raid")
    local before, readsBefore = seats, reads
    eq(before, 1, "inside the callbacks only Layout's own rescale seat ran: the five keys applied nothing")
    eq(readsBefore, 0, "and read nothing")
    flush()
    eq(seats - before, 1, "five keys changed: one Seat for the box")
    eq(reads - readsBefore, 1, "and one Refresh (one health read)")
    near(host._h, hpPx(10) * k, 1e-6); eq(textOf(b.hpText), "62%")
    flush()
    eq(seats - before, 1, "a second flush has nothing left to apply")
    UnitHealth = realHealth
    W.clean(); noFails()
end

function T.plain_frames_take_a_change_in_combat_at_once()
    local W = world()
    target("Kurak")
    InCombatLockdown = function() return true end
    setting("hpHeight", 10)
    near(bars(W).hp.green.host._h, hpPx(10) * K(), 1e-6, "nothing here is protected")
    InCombatLockdown = function() return false end
end

function T.a_protected_bar_frame_defers_the_change_to_the_end_of_combat()
    local W = world()
    target("Kurak")
    local k, b = K(), bars(W)
    getmetatable(UIParent).IsProtected = function(self) return self._prot == true end
    b.frame._prot = true
    local inCombat = true
    InCombatLockdown = function() return inCombat end
    local sizes = 0
    local Region = getmetatable(UIParent)
    local realSize = Region.SetSize
    function Region:SetSize(w, h) sizes = sizes + 1; return realSize(self, w, h) end
    setting("hpHeight", 10); setting("width", 60); setting("numbers", true)
    eq(sizes, 0, "no geometry call while locked down")
    near(b.hp.green.host._h, MB.TB_HP_H * k, 1e-6, "the rails wait")
    eq(b.hpText:IsShown(), false, "and so do the numbers")
    setting("hpHeight", 8)
    inCombat = false
    __fireEvent("PLAYER_REGEN_ENABLED")
    near(b.hp.green.host._h, hpPx(8) * k, 1e-6, "applied once, with the latest value")
    eq(b.hpText:IsShown(), true)
    near(b.hp.green.host._w, pctWidth(W, 60), 1e-6)
    local after = sizes
    __fireEvent("PLAYER_REGEN_ENABLED")
    eq(sizes, after, "not replayed twice")
    Region.SetSize = realSize
    InCombatLockdown = function() return false end
    W.clean(); noFails()
end

function T.a_retired_box_ignores_setting_changes_and_the_player_box_has_nothing_to_change()
    local W = world()
    target("Kurak")
    local k, box = K(), W.tgt.box
    FS.GunsightBoxes.Retire(box)
    setting("hpHeight", 10); setting("numbers", true)
    near(box.bars.hp.green.host._h, MB.TB_HP_H * k, 1e-6, "a retired box is left alone")
    eq(box.bars.hpText:IsShown(), false)
    eq(W.you.box.bars, nil, "the player box has no bars to size")
    W.clean(); noFails()
end

function T.the_settings_code_adds_no_per_event_allocation_path_for_defaults()
    -- The hot path for a default profile: no Config read per UNIT_HEALTH, no text. Settings are cached by
    -- the change callbacks, so only Seat (name events, rescale) reads them.
    local W = world()
    target("Kurak")
    local gets = 0
    local real = FS.Config.Get
    FS.Config.Get = function(...) gets = gets + 1; return real(...) end
    allBarEvents()
    eq(gets, 0, "UNIT_* events read no setting")
    FS.Config.Get = real
    W.clean(); noFails()
end

__checks = T
"""


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "forever-stuwave.toc must stay CRLF"))
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, b, t, c = (toc.index(n) for n in ("Modules/CombatHud/Gunsight.lua", "Modules/CombatHud/GunsightBoxes.lua", "Modules/CombatHud/GunsightTape.lua", "Modules/CombatHud/CombatHud.lua"))
        out.append(("toc_order", None if g < b < t < c else
                    f"GunsightBoxes.lua must load after Gunsight.lua and before GunsightTape.lua and CombatHud.lua (positions {g}, {b}, {t}, {c})"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = BOXES.read_text(encoding="utf-8") if BOXES.exists() else ""
    code = "\n".join(ln.split("--", 1)[0] for ln in src.splitlines())      # comments may name them
    reads = [n for n in ("UnitCastingInfo", "UnitChannelInfo", "UnitCastingDuration", "UnitChannelDuration") if n in code]
    out.append(("boxes_never_read_cast_data", None if not reads else f"GunsightBoxes.lua must leave cast data to CastBars.lua, it mentions {reads}"))
    out.append(("boxes_install_no_onupdate_but_the_one_shot_flusher",
                None if len(re.findall(r"OnUpdate", code)) <= 2 else
                "GunsightBoxes.lua may only set and clear the one-shot setting flusher's OnUpdate"))
    out.append(("boxes_measure_text_in_three_places_only",
                None if len(re.findall(r"GetStringWidth", code)) <= 4 else
                "GetStringWidth appears outside FitLine (plain text only), the name sink's forward for CastBars and the bar width measure"))
    return out


def run_case(name: str, mu: dict, mb: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHEV.MOCK)
    lua.execute(CB.MOCK)
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in
              TH.THEME_CONSTANTS + ("COLOR_CARET_HEALTH", "COLOR_HEAL", "COLOR_GOLD", "FLAT_TEXTURE")]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.execute(CB.WIRE)
    lua.execute(TH.MOCK)
    lua.execute(TH.GS.theme_has_target_lua())   # the real shared rule (FS.HasTarget), Theme being stubbed here
    lua.execute(EXTRA_MOCK)
    lua.eval("__loadChevron")("Core/ChevronCastBar.lua", (ADDON / "Core/ChevronCastBar.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.__castSrc = TH.CASTBARS.read_text(encoding="utf-8")
    g.__layoutSrc = TH.LAYOUT.read_text(encoding="utf-8")
    g.__configSrc = TH.CONFIG.read_text(encoding="utf-8")
    g.__gunsightSrc = TH.GUNSIGHT.read_text(encoding="utf-8")
    g.__tapeSrc = TH.TAPE.read_text(encoding="utf-8")
    g.__boxSrc = BOXES.read_text(encoding="utf-8") if BOXES.exists() else "error('GunsightBoxes.lua is missing')"
    lua.execute("MU = " + TH.lua_value(mu))
    lua.execute("MB = " + TH.lua_value(mb))
    try:
        lua.execute(checks_source())
        lua.eval("__checks")[name]()
    except LuaError as e:
        return str(e)
    return None


def checks_source() -> str:
    """The tape harness's helpers and world() (everything before its first check), with the boxes loaded
    ahead of the tape, then this file's checks."""
    prefix = TH.CHECKS.split("-- ---- constants", 1)[0]
    needle = '__load("Modules/CombatHud/GunsightTape.lua", __tapeSrc)'
    if needle not in prefix:
        sys.exit("gunsighttape-harness.py changed shape: its world() no longer loads GunsightTape.lua the way this harness patches")
    patched = prefix.replace(needle, '__load("Modules/CombatHud/GunsightBoxes.lua", __boxSrc)\n    ' + needle)
    return patched + CHECKS_BODY


def main() -> int:
    mu = TH.mockup_tape()
    mb = mockup_boxes()
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(checks_source().replace("__checks = T", "__names = T"))
    names = sorted(k for k in lua.eval("__names").keys())
    failed = 0
    total = 0
    for name, problem in static_checks():
        total += 1
        if problem:
            failed += 1
            print(f"FAIL  {name}: {problem}")
        else:
            print(f"ok    {name}")
    for name in names:
        total += 1
        err = run_case(name, mu, mb)
        if err:
            failed += 1
            print(f"FAIL  {name}: {err}")
        else:
            print(f"ok    {name}")
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
