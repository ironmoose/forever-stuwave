#!/usr/bin/env python3
"""Runs the real ClassShoulder.lua (the Paladin shoulder CHROME) headless, next to the real
FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua, PetActionBar.lua, PetDock.lua and
SealBar.lua (sealbar-harness's world, which this file imports).

The Paladin's seal and aura buttons stand on a shoulder block of the approved Gunsight mockup
(`LS_*`, `lsPath`, `lsBtn`: 306.8 x 91.8 design px, the seal row over the aura row). In the mockup's
DEFAULT Console style (`PS === 'cn'`) that block is not the pet recipe (`lsLive` runs only for
`PS !== 'cn'`): `cnTrace` draws it as part of the CHASSIS outline, so it wears the chassis look in
`cnBake` (the vertical gradient fill, whose top stop is all a shoulder above the chassis ever
shows, the halo `A(.7)` x `CN_GK` through the `HALO` strokes, and the stroke `A(.72)`). The checks read those
numbers back out of the HTML, so a mockup move fails here:

  * the shoulder builds ONLY for a Paladin (SealBar owns the forms), only while the Console is
    drawn, only out of combat, once;
  * it is 306.8 x 91.8 design px, seated BOTTOMLEFT on the Console root's TOPLEFT at 36 design px,
    scaled by the layout scale, and follows a rescale and the Console geometry callback;
  * it owns the Console's top gap: PetDock.YieldGap("classshoulder") first, then SetDockGap with the
    shoulder's span (line [37, 351.8], halo [25, 357.8]), and gives it back (ReclaimGap) when the
    Console goes off;
  * SealBar's seat functions answer from the shoulder while it exists, and the seal and aura
    buttons land exactly where they stood before (a delta of zero), inside the block by
    LS_PAD / LS_PT / LS_PB / LS_BTN / LS_BG;
  * the look is the chassis' (fill tint, stroke alpha, halo alpha and blend, no red twin, no
    overrun into the Console's line row);
  * nothing protected is touched in combat; the re-seat waits for PLAYER_REGEN_ENABLED; no secure
    frame is ever anchored to the art;
  * a Warrior (StanceBar owns the shoulder) gets the same chrome as a 3 x 1 block, 135.6 x 49 design px
    (mockup `{id:'st',n:3,rows:1}`), cached apart from the Paladin's, on the same baked halo atlas;
    Druid, Rogue, Priest and Mage get none.

The mock is strict and is NOT the real client. CLASSSHOULDER_LUA, SEALBAR_LUA, PETDOCK_LUA and TOC_FILE
point the harness at mutant copies (a check must fail on a broken one).

    python3 tools/classshoulder-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
CLASSSHOULDER = Path(os.environ.get("CLASSSHOULDER_LUA", ADDON / "Modules/ActionBars/ClassShoulder.lua"))
PETDOCK = Path(os.environ.get("PETDOCK_LUA", ADDON / "Modules/Pet/PetDock.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = _load("sealbar_harness", "sealbar-harness.py")
MU = sb.MU
TOC = sb.TOC
SCALES = (1 / 1.2, 1.0)
approx = sb.approx
g = sb.g
fire = sb.fire
set_combat = sb.set_combat
blocked = sb.blocked


# ---------------------------------------------------------------------------------------------
# The mockup's numbers (the geometry from sealbar-harness, the chassis look read here)
# ---------------------------------------------------------------------------------------------


def look() -> dict:
    """What the mockup's default (cn) style draws the shoulder with, read out of `cnBake`."""
    src = sb.MOCKUP.read_text(encoding="utf-8")
    bake = sb._m(r"function cnBake\(s\)\{(.*?)\nfunction drawConsole", src, "cnBake").group(1)
    stops = {}
    for at, r, gr, b, a in re.findall(r"addColorStop\((\d),'rgba\((\d+),(\d+),(\d+),([\d.]+)\)'\)", bake):
        stops[int(at)] = (int(r) / 255, int(gr) / 255, int(b) / 255, float(a))
    assert set(stops) == {0, 1}, f"the chassis gradient stops changed: {stops}"
    # the fill, the halo and the stroke all run over cnTrace, which carries the shoulders
    sb._m(r"function cnTrace\(tab\)\{.*?for\(i=0;i<LS\.length;i\+\+\)\{", src, "the shoulders in cnTrace")
    sb._m(r"gr=ctx\.createLinearGradient\(0,c\.y0,0,c\.y1\);", src, "gradient from the chassis top to bottom")
    halo_a = float(sb._m(r"cnTrace\(tab\);A\(([\d.]+)\);glow\(K\.violet,CN_GK\);", bake, "chassis halo alpha").group(1))
    gk = float(sb._m(r"CN_GK=([\d.]+)", src, "CN_GK").group(1))
    stroke_a = float(sb._m(
        r"cnTrace\(tab\);A\(([\d.]+)\);ctx\.strokeStyle=K\.violet;ctx\.lineWidth=LW\*\.9;ctx\.stroke\(\);", bake,
        "chassis stroke alpha").group(1))
    halo_table = sb._m(r"var HALO=\[(\[.*?\])\];", src, "HALO").group(1)
    halo_sum = sum(float(a) for _, a in re.findall(r"\[([\d.]+),([\d.]+)\]", halo_table))
    # the pet recipe (lsLive) only runs outside the Console style
    sb._m(r"if\(PS!=='cn'\)for\(i=0;i<LS\.length;i\+\+\)lsLive\(LS\[i\]\);", src, "lsLive gated off the Console style")
    return dict(
        FILL_TOP=stops[0], FILL_BOT=stops[1], STROKE_A=stroke_a,
        HALO_PEAK=halo_a, GK=gk, HALO_SUM=halo_sum,
    )


LOOK = look()


def warrior_block() -> dict:
    """The Warrior's stance shoulder as the mockup builds it: 3 wide, 1 row (lsRowW(3) by LS_PT + LS_BTN + LS_PB)."""
    src = sb.MOCKUP.read_text(encoding="utf-8")
    sb._m(r"if\(CLS==='wr'\)o\.push\(\{id:'st',x:LS_X,n:3,rows:1\}\);", src, "the Warrior stance shoulder (3 wide, 1 row)")
    stances = sb._m(r"var STANCES=\[(.*?)\];", src, "STANCES").group(1)
    order = re.findall(r"id:'(\w+)'", stances)
    return dict(W=2 * MU["PAD"] + 3 * MU["BTN"] + 2 * MU["BG"], H=MU["PT"] + MU["BTN"] + MU["PB"], ORDER=order)


WR = warrior_block()
WARRIOR_FORMS = ("Battle Stance", "Defensive Stance", "Berserker Stance")

# The mockup's stepped halo, worked out here from its HALO table and nothing under test. `halo(true)` strokes
# the outline four times, each wider by 2 w and drawn at alpha a x CN_GK x A(.7); outside the path the layers
# composite source-over, so the alpha at distance d is 1 - prod(1 - alpha_i) over the layers that reach d. The
# reach is (w + half the core stroke) in image px times 1.28 design px per image px (2560 / 2000), the Console's
# own approved conversion (media/generate_console_chrome.py documents it: 2.5, 4.67, 6.98 and 9.54).
IMAGE_TO_DESIGN = 1.28
CORE_HALF_IMAGE = 0.45


def _halo_steps() -> list:
    src = sb.MOCKUP.read_text(encoding="utf-8")
    table = sb._m(r"var HALO=\[(\[.*?\])\];", src, "HALO").group(1)
    rows = [(float(w), float(a)) for w, a in re.findall(r"\[([\d.]+),([\d.]+)\]", table)]
    return [((w + CORE_HALF_IMAGE) * IMAGE_TO_DESIGN, min(1.0, a * LOOK["GK"] * LOOK["HALO_PEAK"])) for w, a in rows]


STEPS = _halo_steps()


def profile(dist: float) -> float:
    keep = 1.0
    for reach, alpha in STEPS:
        if dist <= reach:
            keep *= 1.0 - alpha
    return 1.0 - keep


W =2 * MU["PAD"] + 7 * MU["BTN"] + 6 * MU["BG"]
H = MU["PT"] + 2 * MU["BTN"] + MU["BG"] + MU["PB"]
PITCH = MU["BTN"] + MU["BG"]
DX = 36   # ClassShoulder.C.DX; the mockup's own figure is checked against it to 0.5 design px


# ---------------------------------------------------------------------------------------------
# The world: sealbar-harness's, with the real PetDock and ClassShoulder in it
# ---------------------------------------------------------------------------------------------

PATCH = r"""
-- the Region bits NewShoulder reads, which the actionbars mock leaves out
do
    local R = __Region
    function R:GetNumPoints() return #self._points end
    function R:GetPoint(i)
        local p = self._points[i or 1]
        if p then return p.point, p.rel, p.relPoint, p.x, p.y end
    end
    function R:SetTexCoord(...) self._tc = { ... } end
    function R:CreateAnimationGroup()
        local anim = setmetatable({}, { __index = function() return function() end end })
        local group = setmetatable({}, { __index = function() return function() end end })
        group.CreateAnimation = function() return anim end
        group.IsPlaying = function() return false end
        return group
    end
end
local t = FS.Theme
local M = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
t.FLAT_TEXTURE = "Interface\\Buttons\\WHITE8x8"
t.GLOW_EDGE_TEXTURE = M .. "glow_edge.tga"
t.GLOW_CORNER_TEXTURE = M .. "glow_corner.tga"
t.GLOW_CORNER_CUT_TEXTURE = M .. "glow_corner_cut.tga"
t.FILL_CUT_TEXTURES = { [6] = M .. "fill_cut_c6.tga" }
t.BORDER_CUT_TEXTURES = { [6] = { [1] = M .. "border_cut_c6_t1.tga", [2] = M .. "border_cut_c6_t2.tga" } }
t.COLOR_HUD_SCRIM = t.COLOR_HUD_SCRIM or { 13 / 255, 6 / 255, 32 / 255, 0.55 * 0.85 }
t.COLOR_BORDER = t.COLOR_BORDER or { 0.659, 0.333, 0.969, 1 }
t.COLOR_RED = t.COLOR_RED or { 1, 0.2314, 0.3059, 1 }
-- A world where the shoulder hears nothing but its own PLAYER_REGEN_ENABLED: its registrations for the
-- Console geometry notice and the rescale callback are dropped (boot(drop=...)), so what runs at regen
-- is the shoulder's own replay and nothing else.
do
    local geo, resc = FS.ActionBars.OnGeometry, FS.Layout.OnRescale
    function FS.ActionBars.OnGeometry(fn)
        if __drop and __drop.geo and FS.ClassShoulder and fn == FS.ClassShoulder.Refresh then return end
        return geo(fn)
    end
    function FS.Layout.OnRescale(fn)
        if __drop and __drop.rescale and FS.ClassShoulder and fn == FS.ClassShoulder.Refresh then return end
        return resc(fn)
    end
end
-- The SealBar host parents secure buttons and the Console root is its anchor target, so both are
-- restricted in combat on the real client (the actionbars mock only knows the buttons).
do
    local create = CreateFrame
    function CreateFrame(kind, name, ...)
        local f = create(kind, name, ...)
        if name == "FSSealBar" or name == "FSConsole" then f._protected = true end
        return f
    end
end
-- a small anchor solver (single point anchors, nested scales), after console-harness's
local FRAC = {
    TOPLEFT = { 0, 0 }, TOP = { .5, 0 }, TOPRIGHT = { 1, 0 }, LEFT = { 0, .5 }, CENTER = { .5, .5 },
    RIGHT = { 1, .5 }, BOTTOMLEFT = { 0, 1 }, BOTTOM = { .5, 1 }, BOTTOMRIGHT = { 1, 1 },
}
local function isFrame(f) return f._kind ~= "Texture" and f._kind ~= "FontString" end
local function spaceScale(f)
    if f == UIParent then return 1 end
    if isFrame(f) then return (f._parent and spaceScale(f._parent) or 1) * (f._scale or 1) end
    return spaceScale(f._parent)
end
local function rect(f)
    if f == UIParent then return { l = 0, t = 0, w = UIParent._w, h = UIParent._h } end
    local p = f._points[1]
    if not p then error("no anchor on " .. tostring(f._name or f._kind), 2) end
    local R = rect(p.rel)
    local sc = spaceScale(f)
    local ax = R.l + FRAC[p.relPoint][1] * R.w + p.x * sc
    local ay = R.t + FRAC[p.relPoint][2] * R.h - p.y * sc
    local w, h = f._w * sc, f._h * sc
    return { l = ax - FRAC[p.point][1] * w, t = ay - FRAC[p.point][2] * h, w = w, h = h }
end
-- a frame's rect in DESIGN px from the chassis top left, y DOWN (above the chassis is negative)
function __D(f)
    local R, r, s = rect(FSConsole), rect(f), FS.Layout.Scale()
    return { x = (r.l - R.l) / s, y = (r.t - R.t) / s, w = r.w / s, h = r.h / s }
end
"""

SPIES = r"""
__calls = {}
local function spy(tbl, name, label)
    if not tbl then return end
    local orig = tbl[name]
    tbl[name] = function(...)
        local rec = { label }
        for i = 1, select("#", ...) do rec[#rec + 1] = tostring((select(i, ...))) end
        __calls[#__calls + 1] = table.concat(rec, ":")
        return orig(...)
    end
end
spy(FS.PetDock, "YieldGap", "yield")
spy(FS.PetDock, "ReclaimGap", "reclaim")
spy(FS.Console, "SetDockGap", "gap")
"""


def boot(scale: float = 1.0, *, spies: bool = True, pre_login: str = "", drop: tuple = (), **kw):
    """`drop` names the shoulder's registrations to leave out ("geo", "rescale")."""
    flags = "__drop = { " + ", ".join(f"{d} = true" for d in drop) + " }\n"
    return sb.boot(scale, extra_lua=flags + PATCH, extra_files=(PETDOCK, CLASSSHOULDER),
                   pre_login=(SPIES if spies else "") + pre_login, **kw)


def cs(lua):
    return g(lua).FS.ClassShoulder


def console(lua):
    return g(lua).FS.Console


def shoulder(lua):
    return cs(lua).shoulder


def calls(lua) -> list:
    t = g(lua).__calls
    return [t[i] for i in range(1, len(t) + 1)]


def clear_calls(lua):
    lua.execute("__calls = {}")


def D(lua, frame) -> dict:
    r = lua.eval("__D")(frame)
    return dict(x=r.x, y=r.y, w=r.w, h=r.h)


def seq(table) -> list:
    return [table[i] for i in range(1, len(table) + 1)]


def regions(frame) -> list:
    out = []
    for r in seq(frame._regions):
        out.append(r)
    return out


def textures_under(frame) -> list:
    """Every texture region under a frame, depth first."""
    out = []
    for r in seq(frame._regions):
        if r._kind == "Texture":
            out.append(r)
        elif r._kind not in ("FontString", "MaskTexture"):
            out.extend(textures_under(r))
    return out


def frames_under(frame) -> list:
    out = []
    for r in seq(frame._regions):
        if r._kind not in ("Texture", "FontString", "MaskTexture"):
            out.append(r)
            out.extend(frames_under(r))
    return out


def gap_of(lua):
    layout = console(lua).layout
    return layout["gap"], layout["haloGap"]


def buttons(lua):
    return sb.all_buttons(lua)


def seat_snapshot(lua) -> dict:
    """The host's and every button's anchor and size, for the zero delta comparison."""
    host = g(lua).FSSealBar
    snap = {"host": (host._points[1].point, host._points[1].rel._name, host._points[1].relPoint,
                     host._points[1].x, host._points[1].y, host._w, host._h, host._level)}
    for name, btn in zip([f"seal{i}" for i in range(1, 8)] + [f"aura{i}" for i in range(1, 8)], buttons(lua)):
        p = btn._points[1]
        snap[name] = (p.point, p.rel._name, p.relPoint, p.x, p.y, btn._w, btn._h, bool(btn._shown))
    return snap


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------


def check_the_chassis_look_is_read_from_the_mockup():
    assert LOOK["FILL_TOP"] == (45 / 255, 27 / 255, 78 / 255, 0.8), LOOK["FILL_TOP"]
    approx(LOOK["STROKE_A"], 0.72, "mockup stroke alpha")
    approx(LOOK["HALO_SUM"], 0.585, "HALO table sum")
    # the stepped halo the four nested strokes composite to, as the lead worked it out by hand
    approx(STEPS[0][1], 0.3094, "innermost stroke alpha (.26 x CN_GK x A(.7))", 1e-4)
    for (reach, _), want in zip(STEPS, (2.496, 4.672, 6.976, 9.536)):
        approx(reach, want, "stroke reach, design px", 1e-3)
    for d, want in ((0.5, 0.546), (3.0, 0.343), (5.0, 0.177), (7.0, 0.065), (9.0, 0.065), (10.0, 0.0)):
        approx(profile(d), want, f"composited halo at {d} px", 1e-3)
    approx(W, 306.8, "shoulder width"), approx(H, 91.8, "shoulder height")
    approx(MU["DX"], DX, "mockup dock offset against the code's 36", 0.5)


def check_toc_lists_classshoulder_between_petdock_and_sealbar():
    raw = TOC.read_bytes()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "the .toc lost its CRLF endings"
    lines = [ln.strip() for ln in raw.decode("utf-8").splitlines()]
    assert lines.count("Modules/ActionBars/ClassShoulder.lua") == 1, "ClassShoulder.lua must be listed exactly once"
    at = lines.index("Modules/ActionBars/ClassShoulder.lua")
    for dep in ("Core/Theme.lua", "Core/Layout.lua", "Modules/ActionBars/ActionBars.lua", "Modules/ActionBars/Console.lua", "Modules/ActionBars/StanceBar.lua", "Modules/Pet/PetFrame.lua",
                "Modules/Pet/PetDock.lua", "Modules/ActionBars/ConsoleKeys.lua"):
        assert lines.index(dep) < at, f"ClassShoulder.lua loads before {dep}"
    assert at < lines.index("Modules/ActionBars/SealBar.lua"), "ClassShoulder.lua must load before SealBar.lua"


def check_a_paladin_with_the_console_drawn_builds_one_shoulder():
    lua = boot()
    assert console(lua).IsDrawn(), "setup: the Console should be drawn"
    s = shoulder(lua)
    assert s is not None, "no shoulder was built"
    assert cs(lua).IsShown(), "the shoulder is not shown"
    art = s.art
    assert art._parent._name == "FSConsole", f"art parent {art._parent._name}"
    assert art._shown
    approx(art._w, W, "art width"), approx(art._h, H, "art height")
    approx(art._scale, 1.0, "art scale")
    assert len(art._points) == 1, f"art has {len(art._points)} points"
    p = art._points[1]
    assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT"), (
        f"art anchor {p.point} {p.rel._name} {p.relPoint}")
    approx(p.x, DX, "art x (art units)", 0.5), approx(p.y, 0, "art y")


def check_the_shoulder_is_built_once_and_survives_every_refresh_event():
    lua = boot()
    first = shoulder(lua)
    n = len(frames_under(g(lua).FSConsole))
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS", "PLAYER_REGEN_ENABLED"):
        fire(lua, event)
    lua.eval("__rescale")(1.0)
    cs(lua).Refresh()
    assert sb.same(lua, shoulder(lua), first), "the shoulder was rebuilt"
    assert len(frames_under(g(lua).FSConsole)) == n, "a refresh grew the frame tree"
    c = calls(lua)
    assert c.count("yield:classshoulder") == 1, f"the gap was yielded again on a refresh: {c}"
    assert len([x for x in c if x.startswith("gap:")]) == 1, f"the gap was set again on a refresh: {c}"


def check_geometry_is_the_mockups(scale):
    lua = boot(scale)
    art = shoulder(lua).art
    d = D(lua, art)
    approx(d["w"], W, "width in design px", 0.01), approx(d["h"], H, "height in design px", 0.01)
    approx(d["x"], DX, "left in design px from the chassis", 0.5)
    approx(d["y"] + d["h"], 0, "bottom stands on the chassis top edge", 0.01)
    approx(art._scale, scale, "art scale follows the layout scale")


def check_the_seal_and_aura_buttons_sit_inside_the_block_by_the_mockups_padding(scale):
    lua = boot(scale)
    block = D(lua, shoulder(lua).art)
    for row, getter in ((0, sb.seal), (1, sb.aura)):
        for col in range(7):
            b = D(lua, getter(lua, col + 1))
            approx(b["w"], MU["BTN"], f"row {row} col {col} width", 0.01)
            approx(b["x"], block["x"] + MU["PAD"] + col * PITCH, f"row {row} col {col} x", 0.01)
            approx(b["y"], block["y"] + MU["PT"] + row * PITCH, f"row {row} col {col} y", 0.01)
            assert block["x"] <= b["x"] and b["x"] + b["w"] <= block["x"] + block["w"] + 1e-6, "button outside left or right"
            assert block["y"] <= b["y"] and b["y"] + b["h"] <= block["y"] + block["h"] + 1e-6, "button outside top or bottom"
    last = D(lua, sb.seal(lua, 7))
    approx(block["x"] + block["w"] - (last["x"] + last["w"]), MU["PAD"], "right padding", 0.01)
    low = D(lua, sb.aura(lua, 1))
    approx(block["y"] + block["h"] - (low["y"] + low["h"]), MU["PB"], "bottom padding", 0.01)
    host = D(lua, g(lua).FSSealBar)
    for k in ("x", "y", "w", "h"):
        approx(host[k], block[k], f"host {k} equals the block's", 0.01)


def check_no_button_or_host_position_moves_with_the_shoulder(scale):
    with_s = boot(scale)
    without = sb.boot(scale)
    a, b = seat_snapshot(with_s), seat_snapshot(without)
    assert a.keys() == b.keys()
    for key in a:
        for x, y in zip(a[key], b[key]):
            if isinstance(x, float) or isinstance(y, float):
                approx(x, y, f"{key} moved")
            else:
                assert x == y, f"{key} moved: {a[key]} vs {b[key]}"
    assert without.eval("FS.ClassShoulder") is None


def check_a_non_paladin_builds_nothing_and_asks_for_nothing():
    for klass in ("WARLOCK", "PRIEST", "MAGE", "DRUID", "ROGUE"):
        lua = boot(klass=klass)
        assert cs(lua).shoulder is None, f"{klass}: a shoulder was built"
        assert not cs(lua).IsShown()
        assert calls(lua) == [], f"{klass}: touched the gap or PetDock: {calls(lua)}"
        gap, halo = gap_of(lua)
        assert gap is None and halo is None, f"{klass}: the Console gap was set"
        assert not any(r._name == "FSConsole" and False for r in [g(lua).FSConsole])
        art_frames = [f for f in frames_under(g(lua).FSConsole)]
        assert all(f._w == 0 or f._w != W for f in art_frames), f"{klass}: a shoulder sized frame exists"
        assert cs(lua).HostPoint() is None and cs(lua).SlotPoint(g(lua).UIParent, 1, 1) is None


def check_without_the_console_there_is_no_shoulder_and_the_buttons_keep_the_stance_seat():
    lua = boot(console=False)
    assert shoulder(lua) is None and not cs(lua).IsShown()
    assert calls(lua) == []
    p = g(lua).FSSealBar._points[1]
    assert p.rel._name == "FSStanceBar" and p.relPoint == "TOPLEFT", f"fallback anchor {p.rel._name}"
    assert all(sb.shown(b) for b in buttons(lua))


def check_the_console_going_off_hides_the_shoulder_and_gives_the_gap_back():
    lua = boot()
    assert cs(lua).IsShown()
    clear_calls(lua)
    console(lua).SetActive(False)
    assert not console(lua).IsDrawn()
    assert not cs(lua).IsShown(), "the shoulder stayed shown with the Console off"
    assert not shoulder(lua).art._shown, "the art stayed shown"
    c = calls(lua)
    assert c.count("reclaim:classshoulder") == 1, f"ReclaimGap calls: {c}"
    assert any(x.startswith("gap:nil") or x == "gap:nil:nil" for x in c), f"the owner did not close its own gap: {c}"
    assert c.index([x for x in c if x.startswith("gap:nil")][0]) < c.index("reclaim:classshoulder"), (
        "the gap must be closed before it is handed back")
    p = g(lua).FSSealBar._points[1]
    assert p.rel._name == "FSStanceBar", f"host anchor {p.rel._name}: the buttons did not fall back to the stance seat"
    assert sb.all_buttons(lua)[0]._shown
    assert cs(lua).HostPoint() is None
    assert cs(lua).SlotPoint(g(lua).FSSealBar, 1, 1) is None, "SlotPoint answered with no shoulder standing"


def check_the_console_coming_back_brings_the_shoulder_and_the_gap_back():
    lua = boot()
    first = shoulder(lua)
    console(lua).SetActive(False)
    clear_calls(lua)
    console(lua).SetActive(True)
    assert console(lua).IsDrawn() and cs(lua).IsShown()
    assert sb.same(lua, shoulder(lua), first), "the shoulder was rebuilt for a Console toggle"
    assert first.art._shown
    c = calls(lua)
    assert c[0] == "yield:classshoulder" and c[1].startswith("gap:"), f"order: {c}"
    gap, halo = gap_of(lua)
    approx(gap["x0"], DX + 1, "line start"), approx(gap["x1"], DX + W + 10 - 1, "line end")
    approx(halo["x0"], DX - GP, "halo start"), approx(halo["x1"], DX + W + 15, "halo end")
    p = g(lua).FSSealBar._points[1]
    assert p.rel._name == "FSConsole", "the buttons did not come back to the Console"


def check_the_shoulder_takes_the_gap_in_the_right_order_with_the_right_span(scale):
    lua = boot(scale)
    c = calls(lua)
    assert "yield:classshoulder" in c, f"never yielded: {c}"
    gaps = [x for x in c if x.startswith("gap:") and x != "gap:nil:nil"]
    assert gaps, f"never set a gap: {c}"
    assert c.index("yield:classshoulder") < c.index(gaps[0]), f"SetDockGap before YieldGap: {c}"
    nums = [float(v) for v in gaps[-1].split(":")[1:]]
    for got, want, what in zip(nums, (37.0, 351.8, 25.0, 357.8), ("line x0", "line x1", "halo x0", "halo x1")):
        approx(got, want, what, 1e-6)
    gap, halo = gap_of(lua)
    approx(gap["x0"], 37, "Console line x0"), approx(gap["x1"], 351.8, "Console line x1")
    approx(halo["x0"], 25, "Console halo x0"), approx(halo["x1"], 357.8, "Console halo x1")
    approx(console(lua).GetGapPatchAlpha(), 0, "the patch stays open under the shoulder")
    assert [x for x in c if x.startswith("reclaim")] == [], "reclaimed with the Console still drawn"


def check_the_shoulder_span_is_the_pet_docks_own_function_of_its_width():
    lua = boot()
    s = shoulder(lua)
    span = s.GapSpan(s, 36)
    for got, want in zip(span, (37.0, 351.8, 25.0, 357.8)):
        approx(got, want, "GapSpan", 1e-6)


def check_the_gap_stays_the_shoulders_across_pet_dock_refreshes():
    lua = boot()
    clear_calls(lua)
    g(lua).FS.PetDock.Refresh(True)
    g(lua).FS.PetDock.SetPetShown(False)
    g(lua).FS.PetDock.SetPetShown(True)
    gap, _ = gap_of(lua)
    approx(gap["x0"], 37, "line x0 after pet refreshes")
    approx(console(lua).GetGapPatchAlpha(), 0, "patch alpha after pet refreshes")


def check_a_refused_gap_owner_is_logged_once_and_the_shoulder_does_not_overwrite_it():
    lua = boot(spies=True, pre_login="assert(FS.PetDock.YieldGap('someone else'))\n__calls = {}")
    assert cs(lua).IsShown(), "the art should still draw"
    c = calls(lua)
    assert [x for x in c if x.startswith("gap:")] == [], f"SetDockGap called without the gap: {c}"
    assert g(lua).__degraded["classshoulder_gap"] is not None or g(lua).__degradeCount >= 1, "no log"
    n = g(lua).__degradeCount
    fire(lua, "PLAYER_ENTERING_WORLD")
    console(lua).SetActive(False)
    console(lua).SetActive(True)
    assert g(lua).__degradeCount == n, "the refusal was logged again"


def check_combat_touches_nothing_protected_and_the_reseat_waits_for_regen():
    lua = boot(1.0)
    base_gap = gap_of(lua)[0]["x0"]
    art = shoulder(lua).art
    set_combat(lua, True)
    clear_calls(lua)
    before = (art._scale, art._points[1].x, art._points[1].y, art._level, art._shown)
    lua.eval("__rescale")(0.64)
    for event in ("PLAYER_ENTERING_WORLD", "SPELLS_CHANGED"):
        fire(lua, event)
    cs(lua).Refresh()
    assert blocked(lua) == 0, "a protected operation was refused in combat"
    assert g(lua).__protectedTouch == 0, "something was created or anchored under a protected frame in combat"
    assert calls(lua) == [], f"gap or owner calls in combat: {calls(lua)}"
    assert (art._scale, art._points[1].x, art._points[1].y, art._level, art._shown) == before, "the art moved in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    approx(art._scale, 0.64, "art scale after regen")
    approx(D(lua, art)["w"], W, "width after regen in design px", 0.01)
    approx(gap_of(lua)[0]["x0"], base_gap, "gap after regen")
    assert blocked(lua) == 0


def check_the_shoulders_own_regen_event_replays_a_deferred_refresh():
    # nothing else calls it: its geometry and rescale registrations are left out of this world
    lua = boot(1.0, drop=("geo", "rescale"))
    art = shoulder(lua).art
    set_combat(lua, True)
    lua.eval("__rescale")(0.64)
    cs(lua).Refresh()
    approx(art._scale, 1.0, "art scale while in combat")
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    approx(art._scale, 0.64, "art scale after the shoulder's own regen replay")
    fire(lua, "PLAYER_REGEN_ENABLED")      # nothing pending now: no churn
    assert blocked(lua) == 0


def check_a_gap_the_console_refused_is_set_at_regen():
    lua = boot(1.0, drop=("geo", "rescale"), pre_login="""
        local real = FS.Console.SetDockGap
        __refuse = 1
        FS.Console.SetDockGap = function(...)
            if __refuse > 0 then __refuse = __refuse - 1; return false end
            return real(...)
        end
    """)
    assert gap_of(lua)[0] is None, "the gap was recorded though the Console refused it"
    fire(lua, "PLAYER_REGEN_ENABLED")
    approx(gap_of(lua)[0]["x0"], 37, "line start after the retry"), approx(gap_of(lua)[1]["x1"], 357.8, "halo end after the retry")


def check_a_console_without_the_chassis_look_builds_no_shoulder():
    lua = boot(pre_login="FS.Console.FILL_TOP = nil")
    assert shoulder(lua) is None and not cs(lua).IsShown()
    assert g(lua).__degraded["classshoulder_notokens"], "the missing look was not logged"
    assert calls(lua) == [], f"gap calls without a shoulder: {calls(lua)}"
    assert g(lua).FSSealBar._points[1].rel._name == "FSConsole" and all(sb.shown(b) for b in buttons(lua))


def check_a_throwing_refresh_cannot_stop_sealbar():
    lua = boot(pre_login="FS.ClassShoulder.Refresh = function() error('boom') end")
    assert g(lua).__degraded["sealbar_shoulder"], "the failure was not logged"
    assert g(lua).FS.SealBar.OwnsForms(), "SealBar stopped before it took the forms"
    assert g(lua).FSSealBar._points[1].rel._name == "FSConsole" and all(sb.shown(b) for b in buttons(lua))


def check_a_login_in_combat_builds_the_shoulder_at_regen():
    lua = boot(combat=True)
    assert shoulder(lua) is None, "built in combat"
    assert calls(lua) == []
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert shoulder(lua) is not None and cs(lua).IsShown(), "not built at regen"
    assert any(x.startswith("gap:37") for x in calls(lua))
    assert blocked(lua) == 0


def check_a_console_toggle_in_combat_never_touches_the_shoulder():
    lua = boot()
    art = shoulder(lua).art
    set_combat(lua, True)
    clear_calls(lua)
    console(lua).SetActive(False)         # ActionBars defers the real switch to regen
    assert blocked(lua) == 0 and g(lua).__protectedTouch == 0
    assert art._shown and calls(lua) == [], f"touched in combat: {calls(lua)}"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not art._shown and not cs(lua).IsShown(), "the shoulder did not hide after combat"
    assert "reclaim:classshoulder" in calls(lua)


def check_a_rescale_reseats_and_keeps_the_design_px_gap(scale=None):
    lua = boot(1.0)
    lua.eval("__rescale")(0.64)
    s = 0.64
    art = shoulder(lua).art
    approx(art._scale, s, "scale after rescale")
    approx(art._points[1].x, DX, "x stays in design px (art units)", 0.5)
    gap, halo = gap_of(lua)
    approx(gap["x0"], 37, "line x0 in design px"), approx(halo["x1"], 357.8, "halo x1 in design px")
    p = g(lua).FSSealBar._points[1]
    approx(p.x, DX * s, "host x", 0.5 * s)


def check_a_rescale_reaches_the_shoulder_without_a_geometry_notice():
    lua = boot(1.0, drop=("geo",))
    lua.eval("__rescale")(0.64)
    approx(shoulder(lua).art._scale, 0.64, "art scale after a rescale with no geometry notice")


def check_levels_the_art_under_the_buttons_and_over_nothing_secure():
    lua = boot()
    s = shoulder(lua)
    root = g(lua).FSConsole
    host = g(lua).FSSealBar
    assert s.art._level == root._level, f"art level {s.art._level} vs root {root._level}"
    assert s.normal._level >= s.art._level
    top = max(f._level for f in frames_under(s.art))
    assert host._level > top, f"the host ({host._level}) must draw above the whole art ({top})"
    for b in buttons(lua):
        assert b._level > top, "a button draws under the art"
    # the root is re-levelled: the next refresh follows it, and the host stays above
    root._level = root._level + 7
    cs(lua).Refresh()
    assert s.art._level == root._level, "the art did not follow its parent's level"
    fire(lua, "SPELLS_CHANGED")
    assert host._level > max(f._level for f in frames_under(s.art))


def check_no_secure_frame_is_anchored_to_the_art():
    lua = boot()
    art_frames = [shoulder(lua).art] + frames_under(shoulder(lua).art)
    ids = {id(f) for f in art_frames}
    # every frame the harness world created: nothing secure may point at, or live under, the art
    for f in seq(lua.eval("__frames")):
        if f._secure or f._protected:
            for p in seq(f._points):
                assert p.rel is None or all(not sb.same(lua, p.rel, a) for a in art_frames), (
                    f"{f._name} is anchored to the shoulder art")
            parent = f._parent
            while parent is not None:
                assert all(not sb.same(lua, parent, a) for a in art_frames), f"{f._name} is parented under the art"
                parent = parent._parent
    host_point = g(lua).FSSealBar._points[1]
    assert host_point.rel._name == "FSConsole"


def check_the_look_is_the_chassis_look_not_the_pet_recipe():
    lua = boot()
    s = shoulder(lua)
    assert s.red is None, "the shoulder has a low-HP twin"
    fills = seq(s.fill)
    assert fills, "no fill pieces"
    top = LOOK["FILL_TOP"]
    for tex in fills:
        v = tex._vertex
        assert v is not None, "an untinted fill piece"
        for i in range(4):
            approx(v[i + 1] if hasattr(v, "keys") else v[i + 1], top[i], f"fill tint channel {i}")
        assert tex._layer == "BACKGROUND"
    # the chassis fill is the Console's own gradient top
    c_top = console(lua).FILL_TOP
    for i in range(4):
        approx(c_top[i + 1], top[i], f"Console.FILL_TOP channel {i} against the mockup")
    # nothing runs below the art bottom: the overrun into the line row would double the alpha there
    art_h = H
    for tex in fills:
        assert tex._h > 0 and tex._w > 0, "an empty fill piece"
        p = tex._points[1]
        assert -p.y + tex._h <= art_h + 1e-6, f"a fill piece reaches {-p.y + tex._h} past the shoulder bottom {art_h}"
    # stroke and halo
    strokes, halos = seq(s.stroke), seq(s.halo)
    assert strokes and halos
    border = g(lua).FS.Theme.COLOR_BORDER
    for tex in strokes:
        v = tex._vertex
        approx(v[4], LOOK["STROKE_A"], "stroke alpha", 1e-6)
        for i in range(3):
            approx(v[i + 1], border[i + 1], f"stroke colour {i}")
    # the halo is the Console's own: its texture and tint, drawn as the Console draws it (source-over, the
    # stepped profile baked into the alpha, vertex alpha 1), not a formula of ours
    console_halo_part = console(lua).parts.haloLeft
    for tex in halos:
        v = tex._vertex
        approx(v[4], console_halo_part._vertex[4], "halo vertex alpha against the Console's", 1e-6)
        approx(v[4], 1.0, "halo vertex alpha: the profile is baked", 1e-6)
        assert tex._blend in (None, "BLEND"), f"halo blend {tex._blend}"
        for i in range(3):
            approx(v[i + 1], border[i + 1], f"halo colour {i}")
            approx(v[i + 1], console_halo_part._vertex[i + 1], f"halo colour {i} against the Console's")
    # the same stroke alpha and colour as the Console's own top line
    line = console(lua).parts.lineTop._color
    for i in range(3):
        approx(line[i + 1], strokes[1]._vertex[i + 1], f"Console line colour {i}")
    approx(line[4], strokes[1]._vertex[4], "Console line alpha")
    approx(console(lua).OUTLINE_ALPHA, LOOK["STROKE_A"], "Console.OUTLINE_ALPHA against the mockup")


# ---------------------------------------------------------------------------------------------
# The halo, rasterised: the real textures, UVs, placements and vertex colours
# ---------------------------------------------------------------------------------------------

pd = _load("petdock_harness", "petdock-harness.py")
MEDIA = ADDON / "Media" / "Textures"
GP = 11            # texels between the glow canvas edge and the outline polygon (Console.lua GP)
FLARE = 10.0       # the foot's flare, drawPet's f
CUT = 6.0          # the shoulder's top left cut, LS_C
SQRT2 = math.sqrt(2.0)
STROKE_OFF = 0.5 * SQRT2 - 0.5   # where the 1 px stroke's OUTER edge meets the vertical, above the centreline vertex
CONSOLE_HALO_PARTS = ("haloTL", "haloTop", "haloTop2", "haloTabTop", "haloTR", "haloRight", "haloBR",
                      "haloBottom", "haloBL", "haloLeft")


class HaloTex:
    """One halo texture as the engine would draw it: its rect in the art's design px (y down), its UV
    window, the file and the vertex alpha. Sampled bilinearly from the real TGA."""

    def __init__(self, tex):
        p = tex._points[1]
        self.x, self.y = float(p.x), -float(p.y)
        self.w, self.h = float(tex._w), float(tex._h)
        self.file = Path(str(tex._texture).replace("\\", "/")).name
        tc = tex._tc
        self.tc = [float(tc[i]) for i in range(1, len(tc) + 1)] if tc else [0.0, 1.0, 0.0, 1.0]
        assert len(self.tc) == 4, f"{self.file}: a halo piece with {len(self.tc)} texcoords"
        v = tex._vertex
        self.vertex = float(v[4]) if v else 1.0
        self.blend = tex._blend
        self.visible = tex._shown is not False and float(tex._alpha) > 0 and self.w > 0 and self.h > 0

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def alpha(self, x: float, y: float) -> float:
        """Texture alpha times vertex alpha at an art point; 0 outside the rect."""
        if not self.visible or not self.contains(x, y):
            return 0.0
        sx, sy = (x - self.x) / self.w, (y - self.y) / self.h
        u0, u1, v0, v1 = self.tc
        return pd.tga_alpha(MEDIA / self.file, u0 + (u1 - u0) * sx, v0 + (v1 - v0) * sy) * self.vertex


def field(pieces: list, x: float, y: float) -> float:
    """Source-over of the pieces' alpha (these halos are BLEND; an ADD piece fails the look check)."""
    rest = 1.0
    for t in pieces:
        rest *= 1.0 - t.alpha(x, y)
    return 1.0 - rest


def shoulder_halo(lua) -> list:
    return [HaloTex(t) for t in seq(shoulder(lua).halo)]


def console_halo(lua) -> list:
    parts = console(lua).parts
    out = []
    for name in CONSOLE_HALO_PARTS:
        t = parts[name]
        if t is not None and t._points[1] is not None:
            out.append(HaloTex(t))
    return out


def outline_path(wd: float, hd: float) -> list:
    """The outline the halo is thrown around, art design px: the chassis top line either side, the left
    side up, the top left cut, the top, the right side down to the foot, the 45 degree foot. Its outer
    edges, as drawPet's stroke leaves them: x = 0 and x = W, the foot's centreline lying half a pixel in."""
    return [(-60.0, hd), (0.0, hd), (0.0, CUT), (CUT, 0.0), (wd, 0.0), (wd, hd - FLARE - STROKE_OFF),
            (wd + FLARE + STROKE_OFF, hd), (wd + 60.0, hd)]


def _seg_dist(px, py, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _inside(px, py, poly) -> bool:
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def mockup_halo(px: float, py: float, path: list) -> float:
    """The mockup's halo at a point: nothing inside the shoulder and chassis, else the stepped profile of the
    distance to the outline."""
    poly = path + [(path[-1][0], path[-1][1] + 60.0), (path[0][0], path[0][1] + 60.0)]
    if _inside(px, py, poly):
        return 0.0
    return profile(min(_seg_dist(px, py, path[i], path[i + 1]) for i in range(len(path) - 1)))


def texel_mean(x0: float, y0: float, path: list, n: int = 4) -> float:
    """The mockup's halo averaged over the 1 x 1 texel at (x0, y0), n x n samples (the generators' own)."""
    total = 0.0
    for sy in range(n):
        for sx in range(n):
            total += mockup_halo(x0 + (sx + 0.5) / n, y0 + (sy + 0.5) / n, path)
    return total / (n * n)


def check_the_shoulder_halo_is_the_consoles_own_halo_profile():
    """Peak, steps and reach of the shoulder's halo against the Console's own, composited from the real
    textures: left of the chassis for the Console, over the top, left and right runs of the shoulder."""
    lua = boot()
    cons, sh = console_halo(lua), shoulder_halo(lua)
    left = console(lua).parts.haloLeft
    y_mid = -float(left._points[1].y) + float(left._h) / 2
    depths = [d + 0.5 for d in range(11)]
    console_profile = [field(cons, -d, y_mid) for d in depths]
    runs = {
        "top": [field(sh, W / 2, -d) for d in depths],
        "left": [field(sh, -d, H / 2) for d in depths],
        "right": [field(sh, W + d, 40.0) for d in depths],
    }
    for name, got in runs.items():
        for d, a, b in zip(depths, got, console_profile):
            assert abs(a - b) <= 1e-6, f"the shoulder's {name} halo at {d} px is {a:.4f}, the Console's {b:.4f}"
    # the Console's own is the mockup's stepped halo (the texel at a step edge is half and half)
    for d, got in zip(depths, console_profile):
        want = sum(profile(d - 0.5 + (i + 0.5) / 4) for i in range(4)) / 4
        assert abs(got - want) <= 1.5 / 255, f"Console halo at {d} px is {got:.4f}, the mockup's {want:.4f}"
    approx(console_profile[0], 0.546, "peak alpha at the edge", 1e-3)
    assert console_profile[9] > 0.03 and console_profile[10] == 0.0, f"reach: {console_profile[8:]}"
    assert all(a >= b - 1e-9 for a, b in zip(console_profile, console_profile[1:])), "the profile rises outward"


def check_every_halo_piece_is_the_mockups_halo_around_the_shoulders_path():
    """Texel by texel, every piece of the shoulder's halo against the mockup's stepped halo around the shoulder's
    outline: the straight runs, the top left cut 6, the square top right, the vertex and the foot, and the
    concave corner where the left side meets the chassis top."""
    lua = boot()
    path = outline_path(W, H)
    pieces = shoulder_halo(lua)
    assert len(pieces) >= 7, f"only {len(pieces)} halo pieces"
    worst = 0.0
    for t in pieces:
        for j in range(int(t.h)):
            for i in range(int(t.w)):
                x0, y0 = t.x + i, t.y + j
                got = t.alpha(x0 + 0.5, y0 + 0.5)
                want = texel_mean(x0, y0, path)
                worst = max(worst, abs(got - want))
                assert abs(got - want) <= 1.5 / 255, (
                    f"{t.file} piece at ({t.x:.1f}, {t.y:.1f}): texel ({x0:.1f}, {y0:.1f}) is {got:.4f}, "
                    f"the mockup's halo there is {want:.4f}")


def check_the_halo_pieces_tile_without_overlap_and_meet_the_consoles_halo_edge_to_edge():
    """Source-over of two pieces over one spot lights it twice: no two halo pieces may overlap, the shoulder's
    nor the Console's, and the Console's top halo must end where the shoulder's corner piece begins and resume
    where the foot's piece ends, with the same alpha on both sides of the seam."""
    lua = boot()
    sh, cons = shoulder_halo(lua), console_halo(lua)
    off_x, off_y = float(DX), float(H)    # shoulder art -> Console art: x + 36, y - H
    shifted = []
    for t in cons:
        if t.visible:
            shifted.append((t.x - off_x, t.y + off_y, t.w, t.h, t.file))
    rects = [(t.x, t.y, t.w, t.h, "shoulder " + t.file) for t in sh] + [(*r[:4], "console " + r[4]) for r in shifted]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if not (a[4].startswith("shoulder") or b[4].startswith("shoulder")):
                continue
            ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
            oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            assert not (ox > 1e-6 and oy > 1e-6), f"halo pieces overlap: {a} and {b}"
    # Coverage and accuracy where the two halos meet, in Console art px (y 0 is the chassis top line, up is
    # negative; art = Console x - DX, y + H). Each point must be drawn by exactly one piece and carry the
    # mockup's halo of the texel that piece draws, and any point no piece covers must be dark in the mockup
    # too. (The field itself steps across a seam where the outline turns, the foot's diagonal for one, so the
    # two sides are compared with the mockup, not with each other.)
    gap = console(lua).layout["haloGap"]
    both = cons + [HaloTex(t) for t in seq(shoulder(lua).halo)]
    for t in both[len(cons):]:     # the shoulder's pieces, moved into Console coordinates
        t.x, t.y = t.x + off_x, t.y - off_y
    path = outline_path(W, H)

    def judged(x, y, what):
        cover = [t for t in both if t.visible and t.contains(x, y)]
        assert len(cover) <= 1, f"{what}: {len(cover)} halo pieces draw ({x}, {y})"
        if not cover:
            assert mockup_halo(x - off_x, y + off_y, path) < 1 / 255 + 1e-9, (
                f"{what}: nothing draws ({x}, {y}) where the mockup has {mockup_halo(x - off_x, y + off_y, path):.4f}")
            return
        t = cover[0]
        tx, ty = t.x + math.floor(x - t.x), t.y + math.floor(y - t.y)
        want = texel_mean(tx - off_x, ty + off_y, path)
        got = t.alpha(tx + 0.5, ty + 0.5)
        assert abs(got - want) <= 1.5 / 255, f"{what}: ({x}, {y}) is {got:.4f}, the mockup's texel there {want:.4f}"

    for d in [k + 0.5 for k in range(11)]:
        for edge in (gap["x0"], gap["x1"]):
            for off in (-0.5, 0.5):
                judged(edge + off, -d, f"seam at x = {edge}, {d} px above the chassis")
    x = gap["x0"] - 5.0
    while x < gap["x1"] + 5.0:
        for d in [k + 0.5 for k in range(11)]:
            judged(x, -d, "above the chassis")
        x += 0.5
    # And the sides: every point around the shoulder, from the top of its halo down to the chassis top line, is
    # drawn by at most one piece and, where no piece draws it, is dark in the mockup too (a hole between two
    # strips, or between a strip and a baked piece, shows here and nowhere in the piece by piece check).
    y = -H - 12.0 + 0.25
    while y < 1.0:
        x = gap["x0"] - 8.0 + 0.25
        while x < gap["x1"] + 8.0:
            judged(x, y, "around the shoulder")
            x += 1.0
        y += 1.0


def check_the_open_bottom_has_no_stroke_and_no_halo_below_the_block():
    lua = boot()
    s = shoulder(lua)
    for tex in seq(s.stroke) + seq(s.halo):
        p = tex._points[1]
        assert -p.y <= H - 1e-6 or tex._h == 0, f"a stroke or halo piece starts below the block: {-p.y}"


def check_seat_functions_come_from_the_shoulder_when_it_exists(scale):
    lua = boot(scale)
    sb_api = g(lua).FS.SealBar
    point, rel, rel_point, x, y = cs(lua).HostPoint()
    assert (point, rel._name, rel_point) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT")
    approx(x, DX * scale, "shoulder host x", 0.5 * scale), approx(y, 0, "shoulder host y")
    host = g(lua).FSSealBar
    pitch = PITCH
    for row, getter in ((1, sb.seal), (2, sb.aura)):
        for col in range(1, 8):
            point, rel, rel_point, x, y = cs(lua).SlotPoint(host, row, col)
            assert point == "BOTTOMLEFT" and sb.same(lua, rel, host) and rel_point == "BOTTOMLEFT"
            approx(x, (MU["PAD"] + (col - 1) * pitch) * scale, f"SlotPoint({row},{col}) x")
            approx(y, (MU["PB"] + (2 - row) * pitch) * scale, f"SlotPoint({row},{col}) y")
            got = sb_api.SlotPoint(row, col)
            assert got == (point, rel, rel_point, x, y) or (
                got[0] == point and got[2] == rel_point and abs(got[3] - x) < 1e-9 and abs(got[4] - y) < 1e-9), (
                f"SealBar.SlotPoint({row},{col}) differs from the shoulder's")


def check_sealbar_takes_its_seat_from_the_shoulder_while_it_exists():
    lua = boot()
    lua.execute("""
        local real = FS.ClassShoulder.HostPoint
        FS.ClassShoulder.HostPoint = function()
            return "BOTTOMLEFT", FSConsole, "TOPLEFT", 123, 4
        end
        local realSlot = FS.ClassShoulder.SlotPoint
        FS.ClassShoulder.SlotPoint = function(host, row, col)
            return "BOTTOMLEFT", host, "BOTTOMLEFT", col * 100, row * 10
        end
    """)
    fire(lua, "SPELLS_CHANGED")
    hp = g(lua).FSSealBar._points[1]
    assert hp.x == 123 and hp.y == 4, f"the host ignored the shoulder's HostPoint: {hp.x} {hp.y}"
    p = sb.seal(lua, 3)._points[1]
    assert p.x == 300 and p.y == 10, f"the button ignored the shoulder's SlotPoint: {p.x} {p.y}"
    lua.execute("FS.ClassShoulder.HostPoint = function() return nil end; "
                "FS.ClassShoulder.SlotPoint = function() return nil end")
    fire(lua, "SPELLS_CHANGED")
    hp = g(lua).FSSealBar._points[1]
    assert hp.rel._name == "FSConsole" and abs(hp.x - DX) < 0.5, "no shoulder answer must fall back to SealBar's own seat"
    b3 = sb.seal(lua, 3)._points[1]
    assert b3.rel._name == "FSSealBar" and abs(b3.x - (MU["PAD"] + 2 * PITCH)) < 1e-6, (
        f"no shoulder answer must fall back to SealBar's own slot seat: {b3.rel._name} {b3.x}")


def check_the_shoulder_is_shown_before_sealbar_seats_on_every_geometry_notice():
    lua = boot(pre_login="""
        __order = {}
        local real = FS.ClassShoulder.HostPoint
        FS.ClassShoulder.HostPoint = function(...)
            local a, b, c, d, e = real(...)
            __order[#__order + 1] = a and "shoulder" or "none"
            return a, b, c, d, e
        end
    """)
    lua.execute("__order = {}")
    console(lua).SetActive(False)
    assert g(lua).FSSealBar._points[1].rel._name == "FSStanceBar", "the host stayed on a hidden Console"
    lua.execute("__order = {}")
    console(lua).SetActive(True)
    order = seq(g(lua).__order)
    assert order and order[-1] == "shoulder", f"SealBar seated before the shoulder was up: {order}"
    assert g(lua).FSSealBar._points[1].rel._name == "FSConsole"


def check_a_throwing_build_logs_once_and_leaves_the_bare_seat():
    lua = boot(spies=True, pre_login="""
        __tries = 0
        FS.PetDock.NewShoulder = function() __tries = __tries + 1; error("boom") end
    """)
    assert shoulder(lua) is None and not cs(lua).IsShown()
    assert [x for x in calls(lua) if x.startswith("yield") or x.startswith("gap:3")] == [], calls(lua)
    p = g(lua).FSSealBar._points[1]
    assert p.rel._name == "FSConsole" and abs(p.x - DX) < 0.5, "the buttons lost their seat"
    assert all(sb.shown(b) for b in buttons(lua))
    n = g(lua).__degradeCount
    assert n >= 1, "the failure was not logged"
    n_frames = len(seq(lua.eval("__frames")))
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD"):
        fire(lua, event)
    cs(lua).Refresh()
    assert g(lua).__degradeCount == n, "the failure was logged again"
    assert len(seq(lua.eval("__frames"))) == n_frames, "a failed build was retried"
    assert g(lua).__tries == 1, f"the failed build was attempted {g(lua).__tries} times"


def check_a_missing_petdock_builds_no_shoulder_and_leaves_the_bare_seat():
    lua = sb.boot(1.0, extra_lua=PATCH, extra_files=(CLASSSHOULDER,))
    # PetDock.lua was never loaded: NewShoulder does not exist, so there is no shoulder, nothing throws, one log
    assert shoulder(lua) is None and not cs(lua).IsShown()
    assert g(lua).__degraded["classshoulder_nodock"], "the missing PetDock was not logged"
    assert g(lua).FSSealBar._points[1].rel._name == "FSConsole", "the buttons lost their seat"
    assert all(sb.shown(b) for b in buttons(lua))


def check_the_golden_shoulder_default_is_unchanged_without_chassis_opts():
    lua = boot()
    host = lua.eval("CreateFrame('Frame', nil, UIParent)")
    plain = lua.eval("FS.PetDock.NewShoulder")(host, W, H, lua.eval("{ red = true }"))
    assert plain.red is not None
    for tex in seq(plain.stroke):
        approx(tex._vertex[4], 0.9, "default stroke alpha")
    for tex in seq(plain.halo):
        approx(tex._vertex[4], 0.76, "default halo alpha")
    scrim = g(lua).FS.Theme.COLOR_HUD_SCRIM
    for tex in seq(plain.fill):
        approx(tex._vertex[4], scrim[4], "default fill alpha")


def check_bad_chassis_opts_build_nothing():
    lua = boot()
    host = lua.eval("CreateFrame('Frame', nil, UIParent)")
    new = lua.eval("FS.PetDock.NewShoulder")
    n = len(seq(lua.eval("__frames")))
    good = dict(fill={1: 0.1, 2: 0.2, 3: 0.3, 4: 0.8}, strokeAlpha=0.7, haloAlpha=0.6)
    head = "fill = {1, 1, 1, 1}, strokeAlpha = .7, haloAlpha = .6"
    glow = "FS.Console.GLOW"
    bad = [
        "5", "{}", "{ fill = {1, 1, 1}, strokeAlpha = .7, haloAlpha = .6, halo = " + glow + " }",
        "{ fill = {1, 1, 1, 2}, strokeAlpha = .7, haloAlpha = .6, halo = " + glow + " }",
        "{ fill = {1, 1, 1, 1}, strokeAlpha = 'x', haloAlpha = .6, halo = " + glow + " }",
        "{ fill = {1, 1, 1, 1}, strokeAlpha = .7, halo = " + glow + " }",
        "{ fill = {1, 1, 1, 1}, strokeAlpha = .7, haloAlpha = 1 / 0, halo = " + glow + " }",
        "{ fill = {1, 1, 1, 1}, strokeAlpha = -1, haloAlpha = .6, halo = " + glow + " }",
        # the Console's glow descriptor is part of the chassis look: without it, or with a broken one, there is
        # no halo to draw and nothing is built
        "{ " + head + " }",
        "{ " + head + ", halo = 5 }",
        "{ " + head + ", halo = {} }",
        "{ " + head + ", halo = { texture = 5, size = 64, pad = 11, margin = 25, mid0 = 28, mid1 = 36 } }",
        "{ " + head + ", halo = { texture = '', size = 64, pad = 11, margin = 25, mid0 = 28, mid1 = 36 } }",
        "{ " + head + ", halo = { texture = 'x', size = 0, pad = 11, margin = 25, mid0 = 28, mid1 = 36 } }",
        "{ " + head + ", halo = { texture = 'x', size = 64, pad = 0, margin = 25, mid0 = 28, mid1 = 36 } }",
        "{ " + head + ", halo = { texture = 'x', size = 64, pad = 11, margin = 5, mid0 = 28, mid1 = 36 } }",
        "{ " + head + ", halo = { texture = 'x', size = 64, pad = 11, margin = 25, mid0 = 36, mid1 = 28 } }",
        "{ " + head + ", halo = { texture = 'x', size = 64, pad = 11, margin = 25, mid0 = 28, mid1 = 99 } }",
        "{ " + head + ", halo = { texture = 'x', size = 64, pad = 11, margin = 25, mid0 = 28, mid1 = 0 / 0 } }",
    ]
    for chunk in bad:
        res = new(host, W, H, lua.eval("{ chassis = " + chunk + " }"))
        got, why = res if isinstance(res, tuple) else (res, None)
        assert got is None and why, f"opts.chassis = {chunk} was accepted"
    assert len(seq(lua.eval("__frames"))) == n, "a refused chassis built frames"
    ok = new(host, W, H, lua.eval("{ chassis = { fill = {.1, .2, .3, .8}, strokeAlpha = .7, haloAlpha = .6, halo = " + glow + " } }"))
    assert ok is not None
    # the Console's strips and the baked corner pieces tile only on a block big enough to hold them all:
    # wider than the cut plus the corner block (6 + 14) and taller than the foot, the flare piece's run above the
    # vertex and the corner block (10 + 12 + 14)
    mine = "{ chassis = { fill = {.1, .2, .3, .8}, strokeAlpha = .7, haloAlpha = .6, halo = " + glow + " } }"
    for w, h in ((20, 40), (40, 36)):
        res = new(host, w, h, lua.eval(mine))
        got, why = res if isinstance(res, tuple) else (res, None)
        assert got is None and why, f"a {w} x {h} block was given the Console's halo pieces"
    assert new(host, 21, 37, lua.eval(mine)) is not None, "the smallest block that holds the halo pieces was refused"
    for tex in seq(ok.stroke):
        approx(tex._vertex[4], 0.7, "chassis stroke alpha")
    for tex in seq(ok.halo):
        approx(tex._vertex[4], 0.6, "chassis halo alpha")
    # SetEdge with no alphas falls back to the build defaults of THIS shoulder, not the pet panel's
    ok.SetEdge(ok, lua.eval("{ 1, 0, 0, 1 }"))
    for tex in seq(ok.stroke):
        approx(tex._vertex[4], 0.7, "SetEdge default stroke alpha")
    for tex in seq(ok.halo):
        approx(tex._vertex[4], 0.6, "SetEdge default halo alpha")


# ---------------------------------------------------------------------------------------------
# The Warrior's shoulder: the same chrome as a 3 x 1 block
# ---------------------------------------------------------------------------------------------


def warrior(scale: float = 1.0, **kw):
    kw.setdefault("forms", list(WARRIOR_FORMS))
    return boot(scale, klass="WARRIOR", **kw)


def check_the_mockups_warrior_block_is_three_by_one():
    assert WR["ORDER"] == ["ba", "de", "be"], f"the mockup's stance order changed: {WR['ORDER']}"
    approx(WR["W"], 135.6, "Warrior block width"), approx(WR["H"], 49, "Warrior block height")
    approx(W, 306.8, "the Paladin block stays 306.8 wide"), approx(H, 91.8, "and 91.8 tall")


def check_a_warrior_with_the_console_drawn_builds_one_3x1_shoulder():
    lua = warrior()
    assert console(lua).IsDrawn(), "setup: the Console should be drawn"
    assert g(lua).FS.StanceBar.OwnsShoulder() and not g(lua).FS.SealBar.OwnsForms()
    s = shoulder(lua)
    assert s is not None and cs(lua).IsShown(), "no Warrior shoulder stands"
    art = s.art
    assert art._parent._name == "FSConsole" and art._shown
    approx(art._w, WR["W"], "art width"), approx(art._h, WR["H"], "art height")
    assert len(art._points) == 1
    p = art._points[1]
    assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT"), (
        f"art anchor {p.point} {p.rel._name} {p.relPoint}")
    approx(p.x, DX, "art x (art units)", 0.5), approx(p.y, 0, "art y")
    # the art is the one NewShoulder size for this owner and nothing else
    approx(s.W, WR["W"], "shoulder W"), approx(s.H, WR["H"], "shoulder H")


def check_the_warrior_shoulder_is_the_mockups_block_at_both_scales(scale):
    lua = warrior(scale)
    d = D(lua, shoulder(lua).art)
    approx(d["w"], WR["W"], "width in design px", 0.01), approx(d["h"], WR["H"], "height in design px", 0.01)
    approx(d["x"], DX, "left in design px from the chassis", 0.5)
    approx(d["y"] + d["h"], 0, "bottom stands on the chassis top edge", 0.01)
    approx(shoulder(lua).art._scale, scale, "art scale follows the layout scale")
    point, rel, rel_point, x, y = cs(lua).HostPoint()
    assert (point, rel._name, rel_point) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT")
    approx(x, DX * scale, "host x", 0.5 * scale), approx(y, 0, "host y")
    host = g(lua).FSStanceBar
    for col in range(1, 4):
        point, rel, rel_point, x, y = cs(lua).SlotPoint(host, 1, col)
        assert point == "BOTTOMLEFT" and rel_point == "BOTTOMLEFT" and sb.same(lua, rel, host)
        approx(x, (MU["PAD"] + (col - 1) * PITCH) * scale, f"slot {col} x")
        approx(y, MU["PB"] * scale, f"slot {col} y: one row sits PB above the bottom")
    bw, bh, edge = cs(lua).BlockSize()
    approx(bw, WR["W"] * scale, "BlockSize width"), approx(bh, WR["H"] * scale, "BlockSize height")
    approx(edge, MU["BTN"] * scale, "BlockSize button edge")


def check_the_warrior_shoulder_takes_the_gap_in_order_and_gives_it_back():
    lua = warrior()
    c = calls(lua)
    gaps = [x for x in c if x.startswith("gap:") and x != "gap:nil:nil"]
    assert "yield:classshoulder" in c and gaps, f"never took the gap: {c}"
    assert c.index("yield:classshoulder") < c.index(gaps[0]), f"SetDockGap before YieldGap: {c}"
    nums = [float(v) for v in gaps[-1].split(":")[1:]]
    # line [dx + 1, dx + W + 10 - 1], halo [dx - 11, dx + W + 15], from the shoulder's own width
    want = (DX + 1, DX + WR["W"] + 9, DX - GP, DX + WR["W"] + 15)
    for got, w, what in zip(nums, want, ("line x0", "line x1", "halo x0", "halo x1")):
        approx(got, w, what, 1e-6)
    clear_calls(lua)
    console(lua).SetActive(False)
    assert not cs(lua).IsShown() and not shoulder(lua).art._shown
    c = calls(lua)
    assert c.count("reclaim:classshoulder") == 1, f"ReclaimGap calls: {c}"
    assert c.index([x for x in c if x.startswith("gap:nil")][0]) < c.index("reclaim:classshoulder")
    assert cs(lua).HostPoint() is None and cs(lua).SlotPoint(g(lua).FSStanceBar, 1, 1) is None
    assert cs(lua).BlockSize() is None
    first = shoulder(lua)
    console(lua).SetActive(True)
    assert cs(lua).IsShown() and sb.same(lua, shoulder(lua), first), "the Console coming back rebuilt the shoulder"


def check_a_warrior_without_the_console_or_without_forms_has_no_shoulder():
    lua = warrior(console=False)
    assert shoulder(lua) is None and not cs(lua).IsShown() and calls(lua) == []
    lua = warrior(forms=[])
    assert not g(lua).FS.StanceBar.OwnsShoulder(), "a Warrior with no forms owns a shoulder"
    assert shoulder(lua) is None and not cs(lua).IsShown() and calls(lua) == [], calls(lua)
    gap, halo = gap_of(lua)
    assert gap is None and halo is None, "the Console gap was set for no shoulder"


def check_a_warrior_shoulder_is_built_once_and_kept_per_owner():
    lua = warrior()
    first = shoulder(lua)
    n = len(frames_under(g(lua).FSConsole))
    for event in ("PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS", "PLAYER_REGEN_ENABLED"):
        fire(lua, event)
    lua.eval("__rescale")(1.0)
    cs(lua).Refresh()
    assert sb.same(lua, shoulder(lua), first), "the Warrior shoulder was rebuilt"
    assert len(frames_under(g(lua).FSConsole)) == n, "a refresh grew the frame tree"
    c = calls(lua)
    assert c.count("yield:classshoulder") == 1, f"the gap was yielded again: {c}"
    assert len([x for x in c if x.startswith("gap:")]) == 1, f"the gap was set again: {c}"
    # the Paladin's own is another object entirely, at its own size
    pal = boot()
    approx(shoulder(pal).art._w, W, "Paladin art width"), approx(shoulder(pal).art._h, H, "Paladin art height")


def check_the_warrior_halo_is_the_mockups_halo_around_a_3x1_path():
    """Every piece of the Warrior's halo, texel by texel, against the mockup's stepped halo around ITS outline.
    The baked corner pieces are fixed texel rects, so this is also the proof media/shoulder_glow.tga needs no
    re-bake for another width or height."""
    lua = warrior()
    ww, hh = WR["W"], WR["H"]
    path = outline_path(ww, hh)
    pieces = shoulder_halo(lua)
    assert len(pieces) >= 7, f"only {len(pieces)} halo pieces"
    for t in pieces:
        assert t.w > 0 and t.h > 0, f"an empty halo piece at ({t.x}, {t.y})"
        for j in range(int(t.h)):
            for i in range(int(t.w)):
                x0, y0 = t.x + i, t.y + j
                got = t.alpha(x0 + 0.5, y0 + 0.5)
                want = texel_mean(x0, y0, path)
                assert abs(got - want) <= 1.5 / 255, (
                    f"{t.file} piece at ({t.x:.1f}, {t.y:.1f}): texel ({x0:.1f}, {y0:.1f}) is {got:.4f}, "
                    f"the mockup's halo there is {want:.4f}")
    # the baked pieces are the same texel windows at the same size as on the Paladin's block
    pal = shoulder_halo(boot())
    def baked(ps):
        return sorted((t.file, tuple(round(v, 6) for v in t.tc), t.w, t.h) for t in ps if t.file == "shoulder_glow.tga")
    assert baked(pieces) == baked(pal) and len(baked(pieces)) == 3, "the baked corner pieces changed with the block"


def check_the_warrior_halo_tiles_without_overlap_or_holes():
    lua = warrior()
    ww, hh = WR["W"], WR["H"]
    pieces = shoulder_halo(lua)
    for i, a in enumerate(pieces):
        for b in pieces[i + 1:]:
            ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
            oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
            assert not (ox > 1e-6 and oy > 1e-6), f"halo pieces overlap: ({a.x}, {a.y}) and ({b.x}, {b.y})"
    path = outline_path(ww, hh)
    y = -GP + 0.25
    while y < hh - 1.0:
        x = -GP + 0.25
        while x < ww + 15.0:
            cover = [t for t in pieces if t.visible and t.contains(x, y)]
            assert len(cover) <= 1, f"{len(cover)} halo pieces draw ({x}, {y})"
            if not cover:
                assert mockup_halo(x, y, path) < 1 / 255 + 1e-9, (
                    f"nothing draws ({x}, {y}) where the mockup has {mockup_halo(x, y, path):.4f}")
            x += 1.0
        y += 1.0
    for tex in seq(shoulder(lua).stroke) + seq(shoulder(lua).halo):
        p = tex._points[1]
        assert -p.y <= hh - 1e-6 or tex._h == 0, f"a stroke or halo piece starts below the block: {-p.y}"


def check_a_warrior_login_in_combat_builds_the_shoulder_at_regen():
    lua = warrior(combat=True)
    assert shoulder(lua) is None and calls(lua) == []
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert shoulder(lua) is not None and cs(lua).IsShown(), "not built at regen"
    assert any(x.startswith("gap:37") for x in calls(lua))
    assert blocked(lua) == 0 and g(lua).__protectedTouch == 0


def check_the_warrior_shoulder_touches_nothing_protected_in_combat():
    lua = warrior(1.0)
    art = shoulder(lua).art
    set_combat(lua, True)
    clear_calls(lua)
    before = (art._scale, art._points[1].x, art._points[1].y, art._level, art._shown)
    lua.eval("__rescale")(0.64)
    cs(lua).Refresh()
    console(lua).SetActive(False)
    assert blocked(lua) == 0 and g(lua).__protectedTouch == 0, "a protected operation ran in combat"
    assert calls(lua) == [], f"gap or owner calls in combat: {calls(lua)}"
    assert (art._scale, art._points[1].x, art._points[1].y, art._level, art._shown) == before
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert blocked(lua) == 0


def check_the_warrior_shoulder_hangs_no_secure_frame_off_the_art():
    lua = warrior()
    art_frames = [shoulder(lua).art] + frames_under(shoulder(lua).art)
    for f in seq(lua.eval("__frames")):
        if f._secure or f._protected:
            for p in seq(f._points):
                assert p.rel is None or all(not sb.same(lua, p.rel, a) for a in art_frames), (
                    f"{f._name} is anchored to the shoulder art")
            parent = f._parent
            while parent is not None:
                assert all(not sb.same(lua, parent, a) for a in art_frames), f"{f._name} is parented under the art"
                parent = parent._parent
    host_point = g(lua).FSStanceBar._points[1]
    assert host_point.rel._name == "FSConsole", f"the stance host is anchored to {host_point.rel._name}"


def check_no_em_dashes_in_the_new_files():
    for path in (CLASSSHOULDER, Path(__file__)):
        assert path.exists(), f"{path} is missing"
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), f"{path.name} has an em dash"


def check_few_file_scope_locals():
    text = CLASSSHOULDER.read_text(encoding="utf-8")
    n = len(re.findall(r"^local (?:function )?\w+", text, re.M))
    assert n < 60, f"{n} file scope locals in ClassShoulder.lua"


def check_the_file_never_calls_a_protected_method_on_a_secure_frame():
    text = CLASSSHOULDER.read_text(encoding="utf-8")
    for needle in ("FSSealBar", "FSSealButton", "FSAuraButton", "SetAttribute", "RegisterStateDriver"):
        assert needle not in text, f"ClassShoulder.lua mentions {needle}"


CHECKS = [
    check_the_chassis_look_is_read_from_the_mockup,
    check_toc_lists_classshoulder_between_petdock_and_sealbar,
    check_a_paladin_with_the_console_drawn_builds_one_shoulder,
    check_the_mockups_warrior_block_is_three_by_one,
    check_a_warrior_with_the_console_drawn_builds_one_3x1_shoulder,
    check_the_warrior_shoulder_takes_the_gap_in_order_and_gives_it_back,
    check_a_warrior_without_the_console_or_without_forms_has_no_shoulder,
    check_a_warrior_shoulder_is_built_once_and_kept_per_owner,
    check_the_warrior_halo_is_the_mockups_halo_around_a_3x1_path,
    check_the_warrior_halo_tiles_without_overlap_or_holes,
    check_a_warrior_login_in_combat_builds_the_shoulder_at_regen,
    check_the_warrior_shoulder_touches_nothing_protected_in_combat,
    check_the_warrior_shoulder_hangs_no_secure_frame_off_the_art,
    check_the_shoulder_is_built_once_and_survives_every_refresh_event,
    check_a_non_paladin_builds_nothing_and_asks_for_nothing,
    check_without_the_console_there_is_no_shoulder_and_the_buttons_keep_the_stance_seat,
    check_the_console_going_off_hides_the_shoulder_and_gives_the_gap_back,
    check_the_console_coming_back_brings_the_shoulder_and_the_gap_back,
    check_the_shoulder_span_is_the_pet_docks_own_function_of_its_width,
    check_the_gap_stays_the_shoulders_across_pet_dock_refreshes,
    check_a_refused_gap_owner_is_logged_once_and_the_shoulder_does_not_overwrite_it,
    check_combat_touches_nothing_protected_and_the_reseat_waits_for_regen,
    check_the_shoulders_own_regen_event_replays_a_deferred_refresh,
    check_a_gap_the_console_refused_is_set_at_regen,
    check_a_console_without_the_chassis_look_builds_no_shoulder,
    check_a_throwing_refresh_cannot_stop_sealbar,
    check_a_login_in_combat_builds_the_shoulder_at_regen,
    check_a_console_toggle_in_combat_never_touches_the_shoulder,
    check_a_rescale_reseats_and_keeps_the_design_px_gap,
    check_a_rescale_reaches_the_shoulder_without_a_geometry_notice,
    check_levels_the_art_under_the_buttons_and_over_nothing_secure,
    check_no_secure_frame_is_anchored_to_the_art,
    check_the_look_is_the_chassis_look_not_the_pet_recipe,
    check_the_shoulder_halo_is_the_consoles_own_halo_profile,
    check_every_halo_piece_is_the_mockups_halo_around_the_shoulders_path,
    check_the_halo_pieces_tile_without_overlap_and_meet_the_consoles_halo_edge_to_edge,
    check_the_open_bottom_has_no_stroke_and_no_halo_below_the_block,
    check_sealbar_takes_its_seat_from_the_shoulder_while_it_exists,
    check_the_shoulder_is_shown_before_sealbar_seats_on_every_geometry_notice,
    check_a_throwing_build_logs_once_and_leaves_the_bare_seat,
    check_a_missing_petdock_builds_no_shoulder_and_leaves_the_bare_seat,
    check_the_golden_shoulder_default_is_unchanged_without_chassis_opts,
    check_bad_chassis_opts_build_nothing,
    check_no_em_dashes_in_the_new_files,
    check_few_file_scope_locals,
    check_the_file_never_calls_a_protected_method_on_a_secure_frame,
]
SCALED_CHECKS = [
    check_geometry_is_the_mockups,
    check_the_warrior_shoulder_is_the_mockups_block_at_both_scales,
    check_the_seal_and_aura_buttons_sit_inside_the_block_by_the_mockups_padding,
    check_no_button_or_host_position_moves_with_the_shoulder,
    check_the_shoulder_takes_the_gap_in_the_right_order_with_the_right_span,
    check_seat_functions_come_from_the_shoulder_when_it_exists,
]


def main() -> int:
    failed = total = 0

    def run(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
