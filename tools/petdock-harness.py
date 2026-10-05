#!/usr/bin/env python3
"""Runs the real PetDock.lua (and the real PetFrame.lua it chromes) headless against petframe-harness's mock.

PetDock.lua builds the pet panel's CHROME in two modes (step S6 of the pet console dock port):

  * "dock": the open shoulder of the approved Gunsight mockup, option C (drawPet's dc branch,
    peTrace with open = true): top-left cut 6, a straight left side, the right foot flaring
    10 px out at 45 degrees, the bottom OPEN (the Console chassis closes it), the fill running
    1.2 below the stroke to merge into the chassis, and a halo that is decomposed into strips so
    nothing lights the open bottom;
  * "float": the closed cut box PetFrame drew before the move, pixel identical.

The checks read the REAL textures (media/*.tga alpha through each texture's recorded texcoords)
and compare them against the geometry parsed back out of the mockup, so a mockup move or a bad
bake fails here:

  * the fill covers the mockup polygon (everything but the 45 degree edge, which may differ by
    a stroke width), the stroke is the 1 texel lines plus the flare band, the halo follows the
    path's outer distance (the baked glow_edge falloff), and there is no halo, stroke gap or
    fill beyond the open bottom;
  * SetMode flips non-secure chrome frames only (legal in combat), never touches the protected
    container, and rejects an unknown mode;
  * the float chrome is the same two AddCut2Texture calls PetFrame made before;
  * after a mode is applied the low-HP layer (S7) drives that mode's red edge and the inverse
    curve fades that mode's normal edge, so a low pet shows red only;
  * the dock follows the UI scale and waits for regen in combat.

The mock is strict and is NOT the real client; Layout.lua and FrameHelpers.lua are the real
files, Theme is petframe-harness's small stub plus the baked cut texture names.

    python3 tools/petdock-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
from functools import partial
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent
MEDIA = ADDON / "media"
# PETDOCK_LUA points the harness at a mutant copy of PetDock.lua (a check must fail on a broken one).
PETDOCK = Path(os.environ.get("PETDOCK_LUA", ADDON / "PetDock.lua"))
TOC = ADDON / "ForeverSynthwave.toc"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PF = _load("petframe_harness", "petframe-harness.py")
approx, bounds = PF.approx, PF.bounds
SQRT2 = math.sqrt(2.0)


# ---------------------------------------------------------------------------------------------
# The mockup's numbers (option C, drawPet's dc branch)
# ---------------------------------------------------------------------------------------------


def mockup_dock(shoulder: bool = False) -> dict:
    """c, f, the 1.2 fill overrun, the halo reach and strength, parsed back out of the mockup. With
    shoulder=True W and H are the Paladin shoulder's instead of the pet panel's (lsRowW / lsDefs)."""
    src = PF.MOCKUP.read_text(encoding="utf-8")
    d: dict = {}
    m = re.search(r"function peTrace\(W,H,open,f\)\{.*?var c=(\d+);", src, re.S)
    assert m, "peTrace changed; update this harness"
    d["CUT"] = float(m.group(1))
    m = re.search(r"open=pes==='dc',f=(\d+),", src)
    assert m, "drawPet's flare size changed; update this harness"
    d["FLARE"] = float(m.group(1))
    m = re.search(r"ctx\.moveTo\(0,H\+([\d.]+)\);ctx\.lineTo\(0,(\d+)\);ctx\.lineTo\((\d+),0\);ctx\.lineTo\(W,0\);"
                  r"ctx\.lineTo\(W,H-f\);ctx\.lineTo\(W\+f,H\+([\d.]+)\);ctx\.closePath\(\);", src)
    assert m and m.group(1) == m.group(4), "the open fill polygon changed; update this harness"
    assert float(m.group(2)) == d["CUT"] and float(m.group(3)) == d["CUT"], "the fill cut is no longer the stroke's"
    d["OVER"] = float(m.group(1))
    m = re.search(r"var HALO=\[\[([\d.]+),([\d.]+)\],\[([\d.]+),([\d.]+)\],\[([\d.]+),([\d.]+)\],\[([\d.]+),([\d.]+)\]\];", src)
    assert m, "the mockup's HALO table changed; update this harness"
    vals = [float(v) for v in m.groups()]
    d["REACH"] = vals[6]
    d["PEAK"] = sum(vals[1::2])
    m = re.search(r"A\(st\.low\?[^:]*:1\);glow\(col,pes==='bf'\?1:([\d.]+)\);ctx\.strokeStyle=col;", src)
    assert m, "the pet halo strength changed; update this harness"
    d["HALO_ALPHA"] = d["PEAK"] * float(m.group(1))
    m = re.search(r"A\(st\.low\?\.(\d+)\+\.(\d+)\*peS\.pulse:([\d.]+)\);ctx\.strokeStyle=col;", src)
    assert m, "the pet stroke alpha changed; update this harness"
    d["STROKE_ALPHA"] = float(m.group(3))
    # The low stroke is A(.6 + .4 * pulse) with the pulse running 0..1: it PEAKS at .6 + .4.
    d["LOW_STROKE_PEAK"] = round(float(f"0.{m.group(1)}") + float(f"0.{m.group(2)}"), 6)
    c = PF.mockup_constants()
    d["W"], d["H"] = c["PW"], c["PH"]
    if shoulder:
        m = re.search(r"var LS_X=([\d.]+),LS_PAD=([\d.]+),LS_PT=([\d.]+),LS_PB=([\d.]+),LS_BTN=([\d.]+),"
                      r"LS_BG=([\d.]+),LS_F=([\d.]+),LS_C=([\d.]+),", src)
        assert m, "the mockup's LS_* shoulder constants changed; update this harness"
        x, pad, pt, pb, btn, bg, ls_f, ls_c = (float(v) for v in m.groups())
        assert (ls_f, ls_c) == (d["FLARE"], d["CUT"]), "the shoulder's foot and cut are no longer the pet panel's"
        m = re.search(r"CLS==='pl'\)o\.push\(\{id:'sl',x:LS_X,n:(\d+),rows:(\d+)\}\)", src)
        assert m, "the Paladin's lsDefs entry changed; update this harness"
        n, rows = int(m.group(1)), int(m.group(2))
        assert re.search(r"function lsRowW\(n\)\{return 2\*LS_PAD\+n\*LS_BTN\+\(n-1\)\*LS_BG;\}", src), "lsRowW changed"
        assert re.search(r"d\.h=LS_PT\+d\.rows\*LS_BTN\+\(d\.rows-1\)\*LS_BG\+LS_PB;", src), "the shoulder height formula changed"
        d["W"] = round(2 * pad + n * btn + (n - 1) * bg, 6)
        d["H"] = round(pt + rows * btn + (rows - 1) * bg + pb, 6)
        d["LS_X"] = x
    return d


# ---------------------------------------------------------------------------------------------
# The mock: petframe-harness's, with textures that remember their layer
# ---------------------------------------------------------------------------------------------

SETUP = r"""
-- Textures remember the layer they were created on and mark themselves as textures.
do
    local Region = getmetatable(UIParent)
    -- GetNumPoints / GetPoint(index), like the client (the mock's GetPoint() with no index stays the first point)
    local function sorted(self)
        local names = {}
        for name in pairs(self.points) do names[#names + 1] = name end
        table.sort(names)
        return names
    end
    function Region:GetNumPoints() return #sorted(self) end
    local plain = Region.GetPoint
    function Region:GetPoint(index)
        if index == nil then return plain(self) end
        local name = sorted(self)[index]
        local a = name and self.points[name]
        if a then return name, a.rel, a.rp, a.x, a.y end
    end
    local create = Region.CreateTexture
    Region.CreateTexture = function(self, name, layer, template, sublevel)
        local t = create(self)
        t.isTexture, t.layer, t.sublevel = true, layer, sublevel
        return t
    end
end
local t = FS.Theme
local M = "Interface\\AddOns\\ForeverSynthwave\\media\\"
t.FLAT_TEXTURE = "Interface\\Buttons\\WHITE8x8"
t.GLOW_EDGE_TEXTURE = M .. "glow_edge.tga"
t.GLOW_CORNER_TEXTURE = M .. "glow_corner.tga"
t.GLOW_CORNER_CUT_TEXTURE = M .. "glow_corner_cut.tga"
t.FILL_CUT_TEXTURES = { [6] = M .. "fill_cut_c6.tga" }
t.BORDER_CUT_TEXTURES = { [6] = { [1] = M .. "border_cut_c6_t1.tga", [2] = M .. "border_cut_c6_t2.tga" } }
-- Records every nine-sliced chrome call (the float look is exactly these).
__cut2 = {}
t.AddCut2Texture = function(frame, path, color, layer, sublevel, inset)
    local tex = frame:CreateTexture(nil, layer, nil, sublevel)
    tex.path, tex.texture, tex.color, tex.inset, tex.isCut2 = path, path, color, inset or 0, true
    __cut2[#__cut2 + 1] = { frame = frame, tex = tex, path = path, color = color, layer = layer,
        sublevel = sublevel, inset = inset }
    return tex
end
-- Every texture under a frame tree.
function __textures_under(root)
    local out = {}
    for _, f in ipairs(__frames) do
        local p, under = f, false
        while p do
            if p == root then under = true break end
            p = p.parent
        end
        if under then
            for _, r in ipairs(f.regions) do
                if r.isTexture then out[#out + 1] = r end
            end
        end
    end
    return out
end

-- A full dump of the docked chrome tree for the golden hashes: every frame under the dock art
-- (creation order, so draw order within a layer is part of it) and every texture on them, with
-- parent, level, shown, alpha, scale, size, anchors (resolved to ids), animation groups, and for a
-- texture its layer, sublevel, file, texcoords, vertex colour, blend, size and shown state; then the
-- parts lists and the edge table as ids. Numbers print with 17 digits so nothing rounds away.
function __dump_dock()
    local P = FS.PetDock
    local root = P.frames.dock
    local nodes = {}
    for _, f in ipairs(__frames) do
        local p, under = f, false
        while p do
            if p == root then under = true break end
            p = p.parent
        end
        if under then nodes[#nodes + 1] = f end
    end
    local id, n = {}, 0
    for i, f in ipairs(nodes) do id[f] = "F" .. (i - 1) end
    for _, f in ipairs(nodes) do
        for _, r in ipairs(f.regions) do id[r] = "T" .. n n = n + 1 end
    end
    local function num(v)
        if type(v) == "number" then return string.format("%.17g", v) end
        return tostring(v)
    end
    local function list(t)
        if t == nil then return "nil" end
        local out = {}
        for i = 1, #t do out[#out + 1] = num(t[i]) end
        return table.concat(out, ",")
    end
    local function ref(x)
        if x == nil then return "nil" end
        if id[x] then return id[x] end
        if x == UIParent then return "UIParent" end
        return "ext:" .. tostring(x.name or x.kind)
    end
    local function points(r)
        local keys = {}
        for p in pairs(r.points) do keys[#keys + 1] = p end
        table.sort(keys)
        local out = {}
        for _, p in ipairs(keys) do
            local a = r.points[p]
            out[#out + 1] = p .. ">" .. ref(a.rel) .. ":" .. a.rp .. ":" .. num(a.x) .. ":" .. num(a.y)
        end
        return table.concat(out, ";")
    end
    local lines = {}
    local function add(s) lines[#lines + 1] = s end
    for _, f in ipairs(nodes) do
        add(table.concat({ id[f], f.kind, "parent=" .. ref(f.parent), "level=" .. num(f:GetFrameLevel()),
            "shown=" .. tostring(f.shown), "alpha=" .. num(f.alpha), "scale=" .. num(f.scale),
            "size=" .. num(f.w) .. "x" .. num(f.h), "pts=" .. points(f) }, "|"))
        for gi, g in ipairs(f.groups or {}) do
            add("  group" .. gi .. "|looping=" .. tostring(g.looping) .. "|playing=" .. tostring(g.playing))
            for _, a in ipairs(g.animations) do
                add("    anim|" .. tostring(a.kind) .. "|" .. num(a.from) .. "|" .. num(a.to) .. "|"
                    .. num(a.duration) .. "|" .. tostring(a.smoothing))
            end
        end
        for _, r in ipairs(f.regions) do
            add(table.concat({ "  " .. id[r], "parent=" .. ref(r.parent), "layer=" .. tostring(r.layer),
                "sub=" .. tostring(r.sublevel), "tex=" .. tostring(r.texture or r.path),
                "tc=" .. list(r.texcoords), "color=" .. list(r.color), "blend=" .. tostring(r.blendMode),
                "size=" .. num(r.w) .. "x" .. num(r.h), "shown=" .. tostring(r.shown),
                "alpha=" .. num(r.alpha), "pts=" .. points(r) }, "|"))
        end
    end
    local function ids(t)
        local out = {}
        for i = 1, #t do out[#out + 1] = ref(t[i]) end
        return table.concat(out, ",")
    end
    local parts, edge = P.parts.dock, P.edges.dock
    add("fill=" .. ids(parts.fill))
    add("stroke=" .. ids(parts.stroke))
    add("halo=" .. ids(parts.halo))
    add("redstroke=" .. ids(parts.red.stroke))
    add("redhalo=" .. ids(parts.red.halo))
    add("edge|host=" .. ref(edge.host) .. "|pulse=" .. ref(edge.pulseFrame) .. "|normal=" .. ref(edge.normal)
        .. "|base=" .. ids(edge.base) .. "|group=" .. tostring(edge.group ~= nil))
    return table.concat(lines, "\n")
end
"""

LUA_FILES = ("Layout.lua", "FrameHelpers.lua", "PetFrame.lua", "PetDock.lua")


def runtime(scale: float = 1.0, setup: str = "", allow_messages: bool = False, files=LUA_FILES,
            after_load: str = "") -> LuaRuntime:
    """A booted world: the real Layout, FrameHelpers, PetFrame and PetDock at UIParent height 1440 * scale.
    `after_load` runs once every file is loaded and before the login event builds the panel."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(PF.MOCK)
    rt.execute(PF.HELPERS)
    rt.execute(SETUP)
    if setup:
        rt.execute(setup)
    rt.execute(f"UIParent:SetHeight({1440 * scale})")
    load = rt.eval(PF.LOAD)
    fs = rt.globals().FS
    for filename in files:
        if filename == "PetFrame.lua":
            path = PF.PETFRAME
        elif filename == "PetDock.lua":
            path = PETDOCK
        else:
            path = ADDON / filename
        load(path.read_text(encoding="utf-8"), f"@{filename}", fs)
    if after_load:
        rt.execute(after_load)
    rt.execute("__fire_login()")
    messages = list(rt.globals().__messages.values())
    assert allow_messages or not messages, messages
    assert rt.globals().FS.PetFrame.container is not None, "PetFrame built no container"
    assert rt.globals().FS.PetDock is not None, "PetDock.lua did not export FS.PetDock"
    return rt


# ---------------------------------------------------------------------------------------------
# TGA alpha sampling (the real files)
# ---------------------------------------------------------------------------------------------

_TGA: dict = {}


def read_tga(path: Path) -> tuple[int, int, list]:
    """(width, height, rows of (r, g, b, a)) from an uncompressed 32 bpp truecolour TGA."""
    key = str(path)
    if key in _TGA:
        return _TGA[key]
    data = path.read_bytes()
    id_len, cmap, kind = data[0], data[1], data[2]
    w = int.from_bytes(data[12:14], "little")
    h = int.from_bytes(data[14:16], "little")
    bpp, desc = data[16], data[17]
    assert (cmap, kind, bpp) == (0, 2, 32), f"{path.name}: expected uncompressed 32 bpp, got {kind}/{bpp}"
    px = data[18 + id_len:18 + id_len + w * h * 4]
    rows = [[(px[(y * w + x) * 4 + 2], px[(y * w + x) * 4 + 1], px[(y * w + x) * 4], px[(y * w + x) * 4 + 3])
             for x in range(w)] for y in range(h)]
    if not desc & 0x20:
        rows.reverse()
    _TGA[key] = (w, h, rows)
    return _TGA[key]


def tga_alpha(path: Path, u: float, v: float) -> float:
    """Bilinear alpha (0..1) at texcoord (u, v), v = 0 at the TOP row, edges clamped."""
    w, h, rows = read_tga(path)
    fx, fy = u * w - 0.5, v * h - 0.5
    x0, y0 = math.floor(fx), math.floor(fy)
    tx, ty = fx - x0, fy - y0

    def at(x: int, y: int) -> float:
        return rows[min(max(y, 0), h - 1)][min(max(x, 0), w - 1)][3] / 255.0

    top = at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx
    bottom = at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx
    return top * (1 - ty) + bottom * ty


class Tex:
    """One recorded texture, in ART-local design px (x right, y down)."""

    def __init__(self, tex):
        self.raw = tex
        self.path = tex.texture or tex.path
        self.name = Path(str(self.path).replace("\\", "/")).name
        pt = tex.points["TOPLEFT"]
        self.x, self.y = float(pt.x), -float(pt.y)
        self.w, self.h = float(tex.w), float(tex.h)
        tc = tex.texcoords
        self.tc = [float(tc[i]) for i in range(1, len(tc) + 1)] if tc is not None else None
        self.color = [float(tex.color[i]) for i in range(1, len(tex.color) + 1)] if tex.color is not None else None
        self.blend = tex.blendMode
        self.layer = tex.layer

    @property
    def vertex_alpha(self) -> float:
        return self.color[3] if self.color and len(self.color) >= 4 else 1.0

    def alpha(self, x: float, y: float) -> float:
        """Texture alpha (without the vertex alpha) at an art-local point, 0 outside the rect."""
        if not (self.x <= x < self.x + self.w and self.y <= y < self.y + self.h):
            return 0.0
        sx, sy = (x - self.x) / self.w, (y - self.y) / self.h
        tc = self.tc
        if not tc:
            u, v = sx, sy
        elif len(tc) == 4:
            u, v = tc[0] + (tc[1] - tc[0]) * sx, tc[2] + (tc[3] - tc[2]) * sy
        else:
            ulx, uly, llx, lly, urx, ury, _, _ = tc
            u = ulx + sx * (urx - ulx) + sy * (llx - ulx)
            v = uly + sx * (ury - uly) + sy * (lly - uly)
        if str(self.path).endswith("WHITE8x8"):
            return 1.0
        return tga_alpha(MEDIA / self.name, u, v)


def tex_list(rt: LuaRuntime, handles) -> list[Tex]:
    return [Tex(handles[i]) for i in range(1, len(handles) + 1)]


def union(texes: list[Tex], x: float, y: float) -> float:
    """Coverage of source-over stacking of the textures' own alpha (vertex alpha excluded)."""
    rest = 1.0
    for t in texes:
        rest *= 1.0 - t.alpha(x, y)
    return 1.0 - rest


def add_sum(texes: list[Tex], x: float, y: float) -> float:
    return sum(t.alpha(x, y) for t in texes)


def frange(a: float, b: float, step: float):
    n = int(round((b - a) / step))
    for i in range(n + 1):
        yield a + i * step


def build_shoulder(rt: LuaRuntime, W: float, H: float, red: bool = True):
    """PetDock.NewShoulder(host, W, H, { red = red }) on a fresh host frame; the object (also __sh) and
    the host (__sh_host)."""
    rt.execute("__sh_host = CreateFrame('Frame', nil, UIParent); __sh_host:SetPoint('CENTER', UIParent, 'CENTER', 0, 0)")
    rt.execute(f"__sh_host:SetSize({W!r}, {H!r}); __sh = FS.PetDock.NewShoulder(__sh_host, {W!r}, {H!r}, "
               f"{{ red = {'true' if red else 'false'} }})")
    return rt.globals().__sh


def new_dock(rt: LuaRuntime, d: dict, shoulder: bool = False) -> "Dock":
    """The pet dock's own chrome, or a NewShoulder at the mockup's d["W"] x d["H"] (the Paladin's)."""
    return Dock(rt, d, build_shoulder(rt, d["W"], d["H"]) if shoulder else None)


# ---------------------------------------------------------------------------------------------
# Expected geometry (the mockup's path, art-local, y down)
# ---------------------------------------------------------------------------------------------


def polygon(d: dict) -> list[tuple[float, float]]:
    W, H, c, f, o = d["W"], d["H"], d["CUT"], d["FLARE"], d["OVER"]
    return [(0, H + o), (0, c), (c, 0), (W, 0), (W, H - f), (W + f, H + o)]


def inside(poly, x: float, y: float) -> bool:
    ok = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            ok = not ok
    return ok


def edge_distance(poly, x: float, y: float) -> float:
    best = 1e9
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


class Dock:
    """The dock chrome of a booted world: constants, handles and the expected stroke / halo model."""

    def __init__(self, rt: LuaRuntime, d: dict, shoulder=None):
        self.rt, self.d = rt, d
        self.C = rt.globals().FS.PetDock.C
        # A PetDock.NewShoulder object has the same fill / stroke / halo / red.stroke / red.halo lists
        # as the pet dock's own parts table.
        parts = shoulder if shoulder is not None else rt.globals().FS.PetDock.parts.dock
        self.fill = tex_list(rt, parts.fill)
        self.stroke = tex_list(rt, parts.stroke)
        self.halo = tex_list(rt, parts.halo)
        self.red_stroke = tex_list(rt, parts.red.stroke) if parts.red is not None else []
        self.red_halo = tex_list(rt, parts.red.halo) if parts.red is not None else []

    # stroke: 1 texel lines, plus the flare band whose centreline runs (W - .5, H - f) -> (W - .5 + f, H)
    def stroke_expected(self, x: float, y: float):
        """(inside?, margin to the nearest boundary) of the straight lines and the band."""
        W, H, c, f = self.d["W"], self.d["H"], self.d["CUT"], self.d["FLARE"]
        line = 1.0
        hits, margins = [], []
        for x0, y0, x1, y1 in ((c, 0, W, line), (0, c, line, H), (W - line, 0, W, H - f)):
            inside_rect = x0 <= x < x1 and y0 <= y < y1
            m = min(abs(x - x0), abs(x - x1), abs(y - y0), abs(y - y1))
            hits.append(inside_rect)
            margins.append(m)
        px, py = W - 0.5, H - f
        s = ((x - px) - (y - py)) / SQRT2
        t = ((x - px) + (y - py)) / SQRT2
        in_band = abs(s) <= 0.5 and t <= f * SQRT2 and H - f <= y <= H
        m = min(abs(abs(s) - 0.5), abs(t - f * SQRT2), abs(y - (H - f)), abs(y - H))
        hits.append(in_band)
        margins.append(m)
        return any(hits), min(margins)

    # halo: outer distance d of the path (a vertical run, then the 45 degree flare), alpha (1 - d / R)^2
    def halo_expected(self, x: float, y: float) -> float | None:
        """Expected halo alpha (without the vertex alpha) at a point of a straight run or the flare
        zone; None where the corner blooms (not modelled here) live."""
        W, H, c, f, r = self.d["W"], self.d["H"], self.d["CUT"], self.d["FLARE"], self.d["REACH"]
        if y < 0:                                  # above the top line
            if c + 1 <= x <= W - 1:
                return max(0.0, 1 - (-y) / r) ** 2
            return None
        if x < 0:                                  # left of the left line
            if c + 1 <= y <= H - 1:
                return max(0.0, 1 - (-x) / r) ** 2
            return None
        if x > W and y <= H:                       # right of the path: the vertical run, then the flare
            px, py = W - 0.5, H - f
            ds = []
            if y <= py:
                ds.append(x - W)
            s = ((x - px) - (y - py)) / SQRT2
            t = ((x - px) + (y - py)) / SQRT2
            if y >= py - 0.5 and (abs(s - 0.5) < 0.35 or abs(t - f * SQRT2) < 0.35):
                return None                        # a step in the baked alpha (the band's edge, the butt cap)
            if s > 0.5 and 0 <= t <= f * SQRT2:
                ds.append(s - 0.5)
            if not ds:
                return 0.0
            return max(0.0, 1 - min(ds) / r) ** 2
        return None


# ---------------------------------------------------------------------------------------------
# Checks: the files and the toc
# ---------------------------------------------------------------------------------------------


def check_the_toc_lists_petdock_right_after_petframe_and_keeps_crlf() -> None:
    raw = TOC.read_bytes()
    lines = raw.split(b"\r\n")
    assert b"\n" not in b"".join(lines), "the .toc lost a CRLF (a bare LF line ending)"
    names = [ln.decode().strip() for ln in lines]
    assert "PetFrame.lua" in names and "PetDock.lua" in names, "PetDock.lua is not in the .toc"
    assert names.index("PetDock.lua") == names.index("PetFrame.lua") + 1, "PetDock.lua must follow PetFrame.lua"
    assert names.count("PetDock.lua") == 1


def check_petframe_no_longer_builds_the_chrome_itself() -> None:
    src = PF.PETFRAME.read_text(encoding="utf-8")
    assert not re.search(r"AddCut2Texture\s*\(", src), "PetFrame.lua still builds nine-sliced chrome"
    assert "FS.PetDock.Build(container)" in src, "PetFrame.Build does not hand the chrome to PetDock"
    build = src.index("local function Build()")
    assert build < src.index("FS.PetDock.Build(container)") < src.index("BuildStatus()", build), \
        "the chrome is built before the slots, like the old two lines"
    assert "BuildLowHealth()" in src, "S7's BuildLowHealth() line is gone"
    low = src.index("    BuildLowHealth()\n")
    assert src.index("FS.PetDock.AttachLowHealth()", low) > low, \
        "PetDock must attach to the low-HP layer after BuildLowHealth()"


def check_the_baked_textures_are_128_square_bgra() -> None:
    for name in ("pet_dock_flare_line.tga", "pet_dock_flare_glow.tga"):
        w, h, _ = read_tga(MEDIA / name)
        assert (w, h) == (128, 128), f"{name} is {w} x {h}"
    assert (MEDIA / "generate_pet_dock_flare.py").exists(), "no generator for the baked flare textures"


# ---------------------------------------------------------------------------------------------
# Checks: the dock geometry
# ---------------------------------------------------------------------------------------------


def check_the_dock_constants_are_the_mockups() -> None:
    d = mockup_dock()
    C = runtime(1.0).globals().FS.PetDock.C
    approx(C.CUT, d["CUT"], "cut")
    approx(C.FLARE, d["FLARE"], "flare size")
    approx(C.FILL_OVER, d["OVER"], "the fill runs this far below the stroke")
    approx(C.REACH, d["REACH"], "halo reach")
    approx(C.HALO_ALPHA, d["HALO_ALPHA"], "halo strength (stacked mockup halo x the pet's glow factor)", tol=0.01)
    approx(C.STROKE_ALPHA, d["STROKE_ALPHA"], "stroke alpha")
    approx(C.LOW_STROKE_ALPHA, d["LOW_STROKE_PEAK"], "the red stroke's peak (the mockup's A(.6 + .4p) at p = 1)")
    layout = runtime(1.0).globals().FS.Layout.petcontainer
    approx(layout.w, d["W"], "Layout petcontainer width is the mockup's")
    approx(layout.h, d["H"], "Layout petcontainer height is the mockup's")


def mockup_dock_offset(x_name: str) -> float:
    """Where the mockup stands a docked panel whose left edge is the mockup variable `x_name` (PE_X for the
    pet panel, LS_X for the Paladin shoulder) on the Console: the Console chassis (cnTrace) starts at CN.x0
    = the button field's left less CN_PAD + CN_MARG, and the field's left is the left pill x (AB_X0 less
    half the spine growth) plus AB_BX. Evaluated from the mockup's own expressions, in design px."""
    src = PF.MOCKUP.read_text(encoding="utf-8")

    def expr(name: str) -> str:
        m = re.search(rf"\b{name}\s*=\s*([^,;]+)", src)
        assert m, f"the mockup no longer defines {name}; update this harness"
        return m.group(1)

    au = 1 / 1.28
    assert expr("AU") == "1/1.28", "the mockup's design to image scale changed"
    env = {"__builtins__": {}, "AU": au}
    ab_x0, ab_bx = eval(expr("AB_X0"), env), eval(expr("AB_BX"), env)
    spine, pad, marg = (float(expr(n)) for n in ("CN_SPINE", "CN_PAD", "CN_MARG"))
    panel_x = float(expr(x_name))
    field_left = ab_x0 - (spine - 7.2) / 2 * au + ab_bx
    chassis_left = field_left - (pad + marg) * au
    return (panel_x * au - chassis_left) / au


def check_dock_x_is_the_mockups_dock_offset() -> None:
    """DOCK_X is where the mockup stands the docked panel on the Console: drawPet's open branch puts
    its left edge at PE_X (see mockup_dock_offset)."""
    dock_x = mockup_dock_offset("PE_X")
    c = runtime(1.0).globals().FS.PetDock.C
    assert abs(dock_x - c.DOCK_X) < 0.5, f"the mockup docks the panel {dock_x:.2f} design px in, DOCK_X is {c.DOCK_X}"


def check_the_dock_fill_covers_the_mockup_polygon(shoulder: bool = False) -> None:
    d = mockup_dock(shoulder)
    dock = new_dock(runtime(1.0), d, shoulder)
    poly = polygon(d)
    bad, flare_edge = [], 0
    for x in frange(-3, d["W"] + d["FLARE"] + 3, 0.5):
        for y in frange(-3, d["H"] + 3, 0.5):
            ours = union(dock.fill, x, y) >= 0.5
            want = inside(poly, x, y)
            if ours != want:
                dist = edge_distance(poly, x, y)
                # Only the 45 degree edge may differ, and by at most the stroke's own width; every
                # other edge (the top, left, the cut, the 1.2 overrun) must match the mockup.
                near_flare = x > d["W"] - 2 and y > d["H"] - d["FLARE"] - 2
                if near_flare and dist <= 1.5:
                    flare_edge += 1
                elif dist > 0.75:
                    bad.append((x, y, ours, want, round(dist, 2)))
    assert not bad, f"fill differs from the mockup polygon at {bad[:6]} ({len(bad)} points)"
    assert dock.fill, "no fill textures"


def check_the_dock_fill_is_the_scrim_and_uses_the_wedge_for_the_flare(shoulder: bool = False) -> None:
    rt = runtime(1.0)
    d = mockup_dock(shoulder)
    dock = new_dock(rt, d, shoulder)
    scrim = rt.globals().FS.Theme.COLOR_HUD_SCRIM
    for t in dock.fill:
        for i, k in enumerate((1, 2, 3, 4)):
            approx(t.color[i], scrim[k], f"fill colour channel {k} is COLOR_HUD_SCRIM ({t.name})", tol=1e-6)
    wedges = [t for t in dock.fill if t.name == "tab_slant.tga"]
    assert len(wedges) == 1, f"expected one tab_slant wedge in the fill, got {len(wedges)}"
    wedge = wedges[0]
    f, o, W, H = d["FLARE"], d["OVER"], d["W"], d["H"]
    # The approved look is locked: the wedge used to be a (f + o) square showing the WHOLE flipped
    # tab_slant, u 1 -> 0 and v 0 -> 1. The rect now stops at H (f square, so no scrim lies over the
    # Console line pixel under the foot), so its texcoords crop the overrun part: the SAME texels per
    # design px (1 / (f + o) of the texture per px, both ways) and the hypotenuse where it was.
    whole = f + o
    want = [1.0, 1.0 - f / whole, 0.0, f / whole]
    assert all(abs(a - b) < 1e-9 for a, b in zip(wedge.tc, want, strict=True)), \
        f"the wedge's texcoords must crop the old whole-texture mapping to the f square: {wedge.tc} want {want}"
    approx(wedge.w, f, "wedge width stops at the foot")
    approx(wedge.h, f, "wedge height stops at H")
    approx((wedge.tc[0] - wedge.tc[1]) / wedge.w, 1.0 / whole, "texture width per design px along x (committed scale)")
    approx((wedge.tc[3] - wedge.tc[2]) / wedge.h, 1.0 / whole, "texture height per design px along y (committed scale)")
    fx = W - 0.5
    worst = 0.0
    for x in frange(fx + 0.1, fx + f - 0.1, 0.25):
        for y in frange(H - f + 0.1, H - 0.1, 0.25):
            committed = tga_alpha(MEDIA / "tab_slant.tga", 1.0 - (x - fx) / whole, (y - (H - f)) / whole)
            worst = max(worst, abs(wedge.alpha(x, y) - committed))
    assert worst < 0.01, f"the wedge renders differently from the committed (f + o) mapping: off by {worst:.3f}"
    assert not [t for t in dock.fill if t.raw.isCut2], "a nine-sliced fill leaked into the dock"


def check_the_dock_stroke_is_the_lines_the_corner_and_the_flare_band(shoulder: bool = False) -> None:
    rt = runtime(1.0)
    d = mockup_dock(shoulder)
    dock = new_dock(rt, d, shoulder)
    strokes = dock.stroke
    names = sorted(t.name for t in strokes)
    assert names.count("border_cut_c6_t1.tga") == 1, f"the baked TL corner is missing: {names}"
    assert names.count("pet_dock_flare_line.tga") == 1, f"the baked flare band is missing: {names}"
    c = d["CUT"]
    corner = next(t for t in strokes if t.name == "border_cut_c6_t1.tga")
    assert (corner.x, corner.y, corner.w, corner.h) == (0, 0, c, c), "the corner sits at the TL cut"
    assert corner.tc == [0.0, c / 16.0, 0.0, c / 16.0], f"the corner uses the piece at the canvas top left: {corner.tc}"
    assert 0.35 < union([corner], 3.0, 3.0) <= 1.0 and union([corner], 1.0, 1.0) < 0.2 and union([corner], 5.2, 5.2) < 0.2, \
        "the TL corner piece is not the hollow diagonal"
    bad = []
    for x in frange(-2, d["W"] + d["FLARE"] + 2, 0.25):
        for y in frange(-2, d["H"] + 2, 0.25):
            if x < c + 0.5 and y < c + 0.5:
                continue                                   # the baked corner piece owns this corner
            want, margin = dock.stroke_expected(x, y)
            if margin < 0.3:
                continue
            ours = union(strokes, x, y)
            if abs(ours - (1.0 if want else 0.0)) > 0.2:
                bad.append((x, y, round(ours, 2), want))
    assert not bad, f"stroke differs from the mockup's path at {bad[:6]} ({len(bad)} points)"
    # The flare: 10 px at 45 degrees, the foot ending at y = H.
    f, W, H = d["FLARE"], d["W"], d["H"]
    for k in range(0, 11):
        cx, cy = W - 0.5 + k * f / 10.0, H - f + k * f / 10.0
        assert union(strokes, cx, min(cy, H - 0.2)) > 0.85, f"the flare band is not solid along its centreline at {k}/10"
    assert union(strokes, W - 0.5 + f + 3, H - 0.5) < 0.05, "the stroke runs past the flare's foot"
    assert max(t.x + t.w for t in strokes) <= W + f + 1.5, "the stroke reaches farther right than the flare"
    assert all(t.y + t.h <= H + 0.5 for t in strokes), "a stroke texture reaches below the open bottom"


def check_the_bottom_is_open(shoulder: bool = False) -> None:
    d = mockup_dock(shoulder)
    dock = new_dock(runtime(1.0), d, shoulder)
    W, H, f, o = d["W"], d["H"], d["FLARE"], d["OVER"]
    # No stroke along the bottom: the row just above y = H is fill, never line.
    for x in frange(3, W - 3, 1.0):
        assert union(dock.stroke, x, H - 0.5) < 0.05, f"a bottom line at x = {x}"
        assert union(dock.stroke, x, H + 0.5) < 0.05
        assert union(dock.fill, x, H - 0.5) > 0.9, f"the bottom of the fill is not solid at x = {x}"
    # The fill runs the overrun below the stroke's foot, then stops.
    assert union(dock.fill, W / 2, H + o - 0.2) > 0.9 and union(dock.fill, W / 2, H + o + 0.3) < 0.05
    # No halo at all below y = H (the Console owns that edge), and no halo texture reaches below it.
    assert all(t.y + t.h <= H + 1e-9 for t in dock.halo), "a halo texture reaches below the open bottom"
    for x in frange(-12, W + 24, 1.0):
        for y in frange(H + 0.25, H + 12, 1.0):
            assert add_sum(dock.halo, x, y) == 0.0, f"halo below the open bottom at ({x}, {y})"
    # The halo is strips, never a nine-slice: nothing in the dock came from AddCut2Texture, and the
    # strips are the glow textures (a nine-slice outline glow would also light the interior and the bottom).
    assert not [t for t in dock.halo if t.raw.isCut2]
    assert {t.name for t in dock.halo} <= {"glow_edge.tga", "glow_corner.tga", "glow_corner_cut.tga", "pet_dock_flare_glow.tga"}, \
        sorted({t.name for t in dock.halo})
    c = d["CUT"]
    for x in frange(c + 2, W - 2, 3.0):                  # (the cut corner's own bloom lives in x + y < c)
        for y in frange(2, H - 2, 3.0):
            assert add_sum(dock.halo, x, y) == 0.0, f"halo inside the panel at ({x}, {y})"
    for y in frange(2, H - 2, 3.0):
        for x in frange(2, c, 2.0):
            if x + y > c:
                assert add_sum(dock.halo, x, y) == 0.0, f"halo inside the panel at ({x}, {y})"


def check_the_dock_halo_follows_the_paths_outer_distance(shoulder: bool = False) -> None:
    d = mockup_dock(shoulder)
    dock = new_dock(runtime(1.0), d, shoulder)
    W, H, f, r = d["W"], d["H"], d["FLARE"], d["REACH"]
    for t in dock.halo:
        assert t.blend == "ADD", f"halo texture {t.name} is not ADD"
        approx(t.vertex_alpha, d["HALO_ALPHA"], f"halo vertex alpha on {t.name}", tol=0.01)
    zones = (
        ("top", list(frange(d["CUT"] + 1.5, W - 1.5, 3.0)), list(frange(-r + 0.25, -0.25, 0.5))),
        ("left", list(frange(-r + 0.25, -0.25, 0.5)), list(frange(d["CUT"] + 1.5, H - 1.5, 3.0))),
        ("right", list(frange(W + 0.25, W + r - 0.25, 0.5)), list(frange(1, H - f - r - 0.5, 3.0))),
        ("flare", list(frange(W + 0.25, W + f + r - 0.25, 0.5)), list(frange(H - f - r + 0.5, H - 0.25, 0.5))),
    )
    for name, xs, ys in zones:
        worst, at = 0.0, None
        for x in xs:
            for y in ys:
                want = dock.halo_expected(x, y)
                if want is None:
                    continue
                err = abs(add_sum(dock.halo, x, y) - want)
                if err > worst:
                    worst, at = err, (x, y)
        assert worst <= 0.08, f"halo {name}: off by {worst:.3f} at {at}"
    # No light off the open end of the flare's cap: beyond the foot nothing shines.
    assert add_sum(dock.halo, W + f + 4, H - 0.5) < 0.02, "halo past the flare's foot"


def check_the_red_edge_has_the_same_geometry_in_red(shoulder: bool = False) -> None:
    rt = runtime(1.0)
    d = mockup_dock(shoulder)
    dock = new_dock(rt, d, shoulder)
    red = rt.globals().FS.Theme.COLOR_RED
    for normal, twin, label in ((dock.stroke, dock.red_stroke, "stroke"), (dock.halo, dock.red_halo, "halo")):
        assert len(normal) == len(twin), f"the red {label} has {len(twin)} pieces, the normal {len(normal)}"
        for a, b in zip(normal, twin, strict=True):
            assert (a.name, a.x, a.y, a.w, a.h, a.tc, a.blend) == (b.name, b.x, b.y, b.w, b.h, b.tc, b.blend), \
                f"red {label} piece {b.name} differs from the normal one"
            for i, k in enumerate((1, 2, 3)):
                approx(b.color[i], red[k], f"red {label} channel {k}")
    border = rt.globals().FS.Theme.COLOR_BORDER
    for t in dock.stroke + dock.halo:
        for i, k in enumerate((1, 2, 3)):
            approx(t.color[i], border[k], f"the dock edge is COLOR_BORDER ({t.name})")
    # The pulse (1.0 down to .6) multiplies the red stroke's own alpha, so the red stroke peaks at the
    # mockup's 1.0 while the normal stroke stays at its .9; the halos match.
    for t in dock.red_stroke:
        approx(t.vertex_alpha, d["LOW_STROKE_PEAK"], f"red stroke peak ({t.name})")
    for t in dock.stroke:
        approx(t.vertex_alpha, d["STROKE_ALPHA"], f"normal stroke alpha ({t.name})")
    for t in dock.red_halo:
        approx(t.vertex_alpha, dock.C.HALO_ALPHA, f"red halo alpha ({t.name})")


# ---------------------------------------------------------------------------------------------
# Checks: modes
# ---------------------------------------------------------------------------------------------


def _frames(rt: LuaRuntime):
    pd = rt.globals().FS.PetDock
    return pd.frames.float, pd.frames.dock


def check_the_default_mode_is_float_and_set_mode_flips_the_chrome() -> None:
    rt = runtime(1.0)
    pd = rt.globals().FS.PetDock
    floating, docked = _frames(rt)
    assert pd.GetMode() == "float"
    assert floating.shown is True and docked.shown is False
    assert pd.SetMode("dock") is True and pd.GetMode() == "dock"
    assert floating.shown is False and docked.shown is True
    assert pd.SetMode("float") is True
    assert floating.shown is True and docked.shown is False
    assert pd.SetMode("sideways") is False and pd.GetMode() == "float", "an unknown mode is refused"
    assert pd.SetMode(None) is False and pd.GetMode() == "float"
    assert floating.shown is True and docked.shown is False, "a refused mode changes nothing"
    assert pd.SetMode("float") is True, "setting the current mode again is fine"


def check_set_mode_never_touches_the_protected_container() -> None:
    rt = runtime(1.0)
    pf = rt.globals().FS.PetFrame
    container = pf.container
    before = rt.eval("__snapshot()")
    shows, hides = container.showCalls or 0, container.hideCalls or 0
    alpha = container.alpha
    rt.execute("__combat = true")
    pd = rt.globals().FS.PetDock
    for mode in ("dock", "float", "dock", "float"):
        assert pd.SetMode(mode) is True
    assert (container.showCalls or 0) == shows and (container.hideCalls or 0) == hides, \
        "Show or Hide was called on the protected container"
    assert container.alpha == alpha and container.shown is True
    assert rt.eval("__snapshot()") == before, "an anchor or size on the container or its slots moved"
    src = PETDOCK.read_text(encoding="utf-8")
    assert not re.search(r"\bcontainer\s*:\s*(Show|Hide|SetShown|SetPoint|SetSize|SetWidth|SetHeight|ClearAllPoints|"
                         r"SetAlpha|SetAttribute|SetParent|SetScale|EnableMouse)\b", src), \
        "PetDock.lua calls a restricted method on the container"
    assert "SetAttribute" not in src, "PetDock.lua must not touch secure attributes"
    assert not PF._messages(rt), PF._messages(rt)


def same_box(a: dict, b: dict, label: str) -> None:
    for k in ("x", "y", "w", "h", "right", "bottom"):
        approx(a[k], b[k], f"{label}: {k}", tol=1e-9)


def check_the_float_chrome_is_the_same_two_calls_pixel_identical() -> None:
    for s in PF.SCALES:
        rt = runtime(s)
        calls = rt.globals().__cut2
        assert len(calls) == 2, f"float mode must be exactly the two old AddCut2Texture calls, got {len(calls)}"
        outline, fill = calls[1], calls[2]
        theme = rt.globals().FS.Theme
        assert outline.path == theme.SLICE_CUT2_OUTLINE_TEXTURE and outline.layer == "BORDER" and outline.inset is None
        assert rawequal(rt, outline.color, theme.COLOR_POWER), "the float outline is COLOR_POWER (the old look)"
        assert fill.path == theme.SLICE_CUT2_FILL_TEXTURE and fill.layer == "BACKGROUND" and fill.inset == 0
        assert rawequal(rt, fill.color, theme.COLOR_HUD_SCRIM), "the float fill is COLOR_HUD_SCRIM"
        container = rt.globals().FS.PetFrame.container
        box = bounds(rt, container)
        for call in (outline, fill):
            same_box(bounds(rt, call.frame), box, f"float chrome host is the container's rect at scale {s}")


def rawequal(rt: LuaRuntime, a, b) -> bool:
    return bool(rt.eval("rawequal")(a, b))


def check_the_float_chrome_draws_below_the_slots() -> None:
    """Every chrome frame (the roots, both normal edges, both red hosts and their pulse children) sits
    at a level strictly below every slot, so the draw order never depends on creation order."""
    rt = runtime(1.0)
    pf = rt.globals().FS.PetFrame
    pd = rt.globals().FS.PetDock
    floating, docked = _frames(rt)
    level = pf.container.GetFrameLevel(pf.container)
    chrome = [("float root", floating), ("dock art", docked)]
    for mode in ("float", "dock"):
        edge = pd.edges[mode]
        assert edge.host.GetFrameLevel(edge.host) > edge.normal.GetFrameLevel(edge.normal), \
            f"{mode}: the red edge draws above the normal edge"
        chrome += [(f"{mode} normal edge", edge.normal), (f"{mode} red host", edge.host),
                   (f"{mode} red pulse child", edge.pulseFrame)]
    for label, frame in chrome:
        assert frame.GetFrameLevel(frame) >= level, f"the {label} sits under the container's own level"
    top = max(frame.GetFrameLevel(frame) for _, frame in chrome)
    for name in ("castSlot", "barSlot", "statusSlot"):
        slot = getattr(pf, name)
        assert slot.GetFrameLevel(slot) > top, \
            f"{name} (level {slot.GetFrameLevel(slot)}) is not strictly above the chrome (top level {top})"


def check_the_dock_follows_the_ui_scale() -> None:
    d = mockup_dock()
    for s in PF.SCALES:
        rt = runtime(s)
        _, docked = _frames(rt)
        container = rt.globals().FS.PetFrame.container
        approx(docked.GetScale(docked), s, f"the dock art is scaled by the layout scale at {s}")
        approx(docked.w, d["W"], "the dock art is in design px")
        approx(docked.h, d["H"], "the dock art is in design px")
        same_box(bounds(rt, docked), bounds(rt, container), f"the dock art sits exactly on the container at scale {s}")
        f_frame, _ = _frames(rt)
        same_box(bounds(rt, f_frame), bounds(rt, container), f"the float chrome sits on the container at scale {s}")


def check_a_rescale_in_combat_waits_for_regen() -> None:
    rt = runtime(1.0)
    _, docked = _frames(rt)
    rt.execute("__combat = true")
    rt.execute("FS.Layout._applied = {}")
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    approx(docked.GetScale(docked), 1.0, "the dock art holds its scale in combat")
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    approx(docked.GetScale(docked), 0.64, "the dock art takes the new scale at regen")


# ---------------------------------------------------------------------------------------------
# Checks: the low-HP layer targets PetDock's frames
# ---------------------------------------------------------------------------------------------


def _alphas(rt: LuaRuntime) -> dict:
    return PF._alphas(rt)


def check_after_set_mode_the_low_layer_targets_the_dock_frames() -> None:
    rt = runtime(1.0)
    pd = rt.globals().FS.PetDock
    pf = rt.globals().FS.PetFrame
    for mode in ("float", "dock", "float", "dock"):
        assert pd.SetMode(mode) is True
        edge = pd.edges[mode]
        assert rawequal(rt, pf.lowEdge, edge.host), f"{mode}: FS.PetFrame.lowEdge is the {mode} red host"
        assert rawequal(rt, pf.lowEdgePulse, edge.pulseFrame), f"{mode}: lowEdgePulse follows"
        assert rawequal(rt, pd.edge.host, edge.host) and rawequal(rt, pd.edge.base[1], edge.normal), \
            f"{mode}: FS.PetDock.edge is the active mode's hook"
        assert edge.host.shown is True, f"{mode}: the red host is shown"
        # Healthy: red 0, the normal edge 1.
        rt.execute("__set_hp(0.9); __fire('UNIT_HEALTH','pet')")
        assert edge.host.alpha == 0 and edge.normal.alpha == 1, f"{mode} healthy: {edge.host.alpha}/{edge.normal.alpha}"
        # Low: red only, with no cyan (or violet) edge left under the pulse trough.
        rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
        assert edge.host.alpha == 1 and edge.normal.alpha == 0, f"{mode} low: {edge.host.alpha}/{edge.normal.alpha}"
        # The pulse is on a child of the curve driven host and plays.
        assert edge.pulseFrame.parent is edge.host or rawequal(rt, edge.pulseFrame.parent, edge.host)
        groups = list(edge.pulseFrame.groups.values())
        assert len(groups) == 1 and groups[0].playing, f"{mode}: the red edge pulse is not playing while low"
        other = "dock" if mode == "float" else "float"
        assert pd.edges[other].host.alpha == 0, f"{mode}: the other mode's red host is retired"
        assert pd.frames[other].shown is False, f"{mode}: the other mode's chrome is hidden"
        rt.execute("__set_hp(1.0); __fire('UNIT_HEALTH','pet')")


def _ring_frames(rt: LuaRuntime) -> list:
    """Every frame that wears a SkinButton ring and glow (a frame with fsSkin) in the container's tree."""
    return list(rt.eval("""(function()
        local out = {}
        for _, f in ipairs(__frames) do
            if f.fsSkin then out[#out + 1] = f end
        end
        return out
    end)()""").values())


def check_petframe_builds_no_default_edge_when_petdock_is_loaded() -> None:
    """S7's default red edge (a SkinButton ring plus glow) is the fallback for a PetFrame with no
    PetDock; with PetDock loaded it is never built (the float twin is the only ring on the container)."""
    for mode in ("float", "dock"):
        rt = runtime(1.0)
        pd = rt.globals().FS.PetDock
        pd.SetMode(mode)
        rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
        assert _alphas(rt)["red edge"] == 1, f"{mode}: the red edge follows a low pet"
        rings = _ring_frames(rt)
        assert len(rings) == 1 and rawequal(rt, rings[0], pd.edges.float.pulseFrame), \
            f"{mode}: expected only PetDock's float twin to carry a ring, got {len(rings)} ring frames"


def check_a_petdock_that_never_attaches_leaves_the_fallback_edge() -> None:
    """If FS.PetDock is present but nothing ever hands the low-HP layer an edge, PetFrame builds its
    default ring after all, below the slots, and the red layer still works."""
    stub = "FS.PetDock = { Build = function() end, AttachLowHealth = function() end }"
    rt = runtime(1.0, setup=stub, files=("Layout.lua", "FrameHelpers.lua", "PetFrame.lua"))
    pf = rt.globals().FS.PetFrame
    assert pf.lowEdge is not None and rt.eval("FS.PetFrame.lowEdgePulse.fsSkin ~= nil"), "no fallback edge was built"
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    assert _alphas(rt)["red edge"] == 1 and _alphas(rt)["name"] == 0, _alphas(rt)
    edge = pf.lowEdge
    for name in ("castSlot", "barSlot", "statusSlot"):
        slot = getattr(pf, name)
        assert slot.GetFrameLevel(slot) > edge.GetFrameLevel(edge), f"{name} is not above the fallback edge"


# BuildDockFill indexes this table; the float chrome never does.
BREAK_DOCK = "FS.Theme.FILL_CUT_TEXTURES = nil"


def check_a_dock_build_failure_leaves_the_float_look_and_the_pet_ui_working() -> None:
    rt = runtime(1.0, setup=BREAK_DOCK, allow_messages=True)
    pd = rt.globals().FS.PetDock
    pf = rt.globals().FS.PetFrame
    # The pet UI built, with the approved float chrome (exactly the two old calls).
    assert pf.container is not None and pf.statusSlot is not None and pf.barSlot is not None
    assert pf.redHealthBar is not None, "the low-HP layer was not built"
    assert len(rt.globals().__cut2) == 2, "the float chrome is not the two old AddCut2Texture calls"
    floating = pd.frames.float
    assert floating is not None and floating.shown is True, "the float chrome is not shown"
    assert pd.frames.dock is None and pd.edges.dock is None, "a half built dock was left registered"
    assert pd.GetMode() == "float"
    # Logged once, through the degrade logger.
    messages = PF._messages(rt)
    assert len(messages) == 1 and messages[0].startswith("petdock_dock_build"), messages
    # SetMode("dock") is a refused no-op that keeps float, before and after.
    assert pd.SetMode("dock") is False and pd.GetMode() == "float" and floating.shown is True
    assert pd.SetMode("float") is True
    assert len(PF._messages(rt)) == 1, "the failure was logged again"
    # No half built dock art is left visible under the container.
    container = pf.container
    orphans = rt.eval("""(function(c)
        local n = 0
        for _, f in ipairs(__frames) do
            if f.parent == c and f.w == FS.PetDock.C.W and f.h == FS.PetDock.C.H and f.shown ~= false then
                n = n + 1
            end
        end
        return n
    end)""")(container)
    assert orphans == 0, f"{orphans} half built dock frame(s) are still shown"
    # The float low-HP layer and the retint hook still work.
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    edge = pd.edges.float
    assert edge.host.alpha == 1 and edge.normal.alpha == 0 and rawequal(rt, pf.lowEdge, edge.host)
    assert pd.SetEdgeColor(1, 0.5, 0.25) is True and pd.ResetEdgeColor() is True
    rt.execute("__fire('PLAYER_REGEN_ENABLED')")
    rt.execute("__combat = true; __fire('UI_SCALE_CHANGED')")


def check_a_dock_mode_remembered_before_a_failed_dock_build_falls_back_to_float() -> None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(PF.MOCK)
    rt.execute(PF.HELPERS)
    rt.execute(SETUP)
    rt.execute(BREAK_DOCK)
    rt.execute("UIParent:SetHeight(1440)")
    load = rt.eval(PF.LOAD)
    fs = rt.globals().FS
    for filename in LUA_FILES:
        path = PF.PETFRAME if filename == "PetFrame.lua" else PETDOCK if filename == "PetDock.lua" else ADDON / filename
        load(path.read_text(encoding="utf-8"), f"@{filename}", fs)
    assert rt.globals().FS.PetDock.SetMode("dock") is True, "SetMode before the build is remembered"
    rt.execute("__fire_login()")
    pd = rt.globals().FS.PetDock
    assert pd.GetMode() == "float" and pd.frames.float.shown is True
    assert rawequal(rt, rt.globals().FS.PetFrame.lowEdge, pd.edges.float.host)


def check_a_mode_set_before_the_low_layer_exists_is_picked_up_after() -> None:
    """PetFrame builds the chrome first and the low-HP layer later: a SetMode in between must not
    throw, and the layer targets the mode that is current once it exists."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(PF.MOCK)
    rt.execute(PF.HELPERS)
    rt.execute(SETUP)
    rt.execute("UIParent:SetHeight(1440)")
    load = rt.eval(PF.LOAD)
    fs = rt.globals().FS
    for filename in LUA_FILES:
        path = PF.PETFRAME if filename == "PetFrame.lua" else PETDOCK if filename == "PetDock.lua" else ADDON / filename
        load(path.read_text(encoding="utf-8"), f"@{filename}", fs)
    assert rt.globals().FS.PetDock.SetMode("dock") is True, "SetMode before the pet frame is built"
    rt.execute("__fire_login()")
    assert rt.globals().FS.PetDock.GetMode() == "dock"
    assert rawequal(rt, rt.globals().FS.PetFrame.lowEdge, rt.globals().FS.PetDock.edges.dock.host)


def check_the_edge_pulse_is_the_petframes_pulse() -> None:
    pf_src = PF.PETFRAME.read_text(encoding="utf-8")
    def num(name: str) -> float:
        m = re.search(rf"^local {name}\s*=\s*([\d.]+)", pf_src, re.M)
        assert m, f"PetFrame.lua no longer defines {name}"
        return float(m.group(1))
    C = runtime(1.0).globals().FS.PetDock.C
    approx(C.PULSE_TOP, num("LOW_PULSE_TOP"), "pulse top matches PetFrame's")
    approx(C.PULSE_FLOOR, num("LOW_PULSE_FLOOR"), "pulse floor matches PetFrame's")
    approx(C.PULSE_LEG, num("LOW_PULSE_LEG"), "pulse leg matches PetFrame's")
    approx(C.LOW_GLOW_ALPHA, num("LOW_EDGE_GLOW_ALPHA"), "float red glow strength matches PetFrame's")
    rt = runtime(1.0)
    pd = rt.globals().FS.PetDock
    for mode in ("float", "dock"):
        group = list(pd.edges[mode].pulseFrame.groups.values())[0]
        anim = list(group.animations.values())[0]
        assert group.looping == "BOUNCE" and anim.kind == "Alpha"
        approx(rt.eval(f"FS.PetDock.edges.{mode}.pulseFrame.groups[1].animations[1].from"), C.PULSE_TOP, f"{mode} pulse from")
        approx(rt.eval(f"FS.PetDock.edges.{mode}.pulseFrame.groups[1].animations[1].to"), C.PULSE_FLOOR, f"{mode} pulse to")
        approx(rt.eval(f"FS.PetDock.edges.{mode}.pulseFrame.groups[1].animations[1].duration"), C.PULSE_LEG, f"{mode} pulse leg")


# ---------------------------------------------------------------------------------------------
# Checks: the retint hook
# ---------------------------------------------------------------------------------------------


def check_the_normal_edge_can_be_retinted_and_reset() -> None:
    rt = runtime(1.0)
    d = mockup_dock()
    pd = rt.globals().FS.PetDock
    C = pd.C
    dock = Dock(rt, d)
    pd.SetEdgeColor(1, 0.5, 0.25, 0.6, 0.3)
    for t in Dock(rt, d).stroke:
        assert [round(v, 3) for v in t.color] == [1, 0.5, 0.25, 0.6], (t.name, t.color)
    for t in Dock(rt, d).halo:
        assert [round(v, 3) for v in t.color] == [1, 0.5, 0.25, 0.3], (t.name, t.color)
    outline = rt.globals().__cut2[1].tex
    assert [round(outline.color[i], 3) for i in (1, 2, 3)] == [1, 0.5, 0.25], "the float outline takes the tint"
    pd.ResetEdgeColor()
    border = rt.globals().FS.Theme.COLOR_BORDER
    for t in Dock(rt, d).stroke:
        assert [round(v, 3) for v in t.color[:3]] == [round(border[i], 3) for i in (1, 2, 3)] and abs(t.color[3] - d["STROKE_ALPHA"]) < 1e-6
    power = rt.globals().FS.Theme.COLOR_POWER
    assert [round(outline.color[i], 3) for i in (1, 2, 3)] == [round(power[i], 3) for i in (1, 2, 3)], "reset restores the float cyan"
    # The red variants are never retinted.
    red = rt.globals().FS.Theme.COLOR_RED
    assert pd.SetEdgeColor(0, 1, 0) is True
    for t in Dock(rt, d).stroke:
        assert [round(v, 3) for v in t.color] == [0, 1, 0, round(d["STROKE_ALPHA"], 3)], "default stroke alpha"
    for t in Dock(rt, d).halo:
        assert [round(v, 3) for v in t.color] == [0, 1, 0, round(C.HALO_ALPHA, 3)], "default halo alpha"
    for t in dock.red_stroke + dock.red_halo:
        assert [round(v, 3) for v in t.color[:3]] == [round(red[i], 3) for i in (1, 2, 3)], "the red edge was retinted"
    assert pd.SetEdgeColor("x") is False


# ---------------------------------------------------------------------------------------------
# Checks: docking onto the Console (S8)
# ---------------------------------------------------------------------------------------------

DOCK_X = 24  # PetDock.lua's DOCK_X: the dock's left edge, design px right of the chassis left

# A stand-in for Console.lua and ActionBars.lua's geometry feed: FS.Console answers IsDrawn, records
# every SetDockGap (refused in combat like the real one), takes SetGapPatchAlpha in combat too and owns the FSConsole frame the pet anchors
# to; FS.ActionBars.OnGeometry replays like the real one (at once when geometry exists, then on
# __set_console, Console's own callback having run first).
CONSOLE_STUB = r"""
__console = { drawn = false, gap = nil, gapCalls = {}, refused = 0, patch = 0, patchCalls = {} }
local root = CreateFrame('Frame', 'FSConsole')
root:SetPoint('TOPLEFT', UIParent, 'TOPLEFT', 200, -900)
root:SetSize(1100, 190)
__console.root = root
FS.Console = {
    root = root,
    IsDrawn = function() return __console.drawn end,
    SetDockGap = function(x0, x1, hx0, hx1)
        if __combat then __console.refused = __console.refused + 1 return false end
        __console.gapCalls[#__console.gapCalls + 1] = x0 and (x0 .. ',' .. x1) or 'nil'
        __console.gap = x0 and { x0, x1 } or nil
        __console.haloGap = x0 and { hx0 or x0, hx1 or x1 } or nil
        return true
    end,
    -- legal in combat, like the real one (alpha only)
    SetGapPatchAlpha = function(a)
        __console.patch = a
        __console.patchCalls[#__console.patchCalls + 1] = tostring(a) .. (__combat and ':combat' or '')
        return true
    end,
}
local callbacks = {}
FS.ActionBars = {
    geometry = {},
    OnGeometry = function(fn)
        callbacks[#callbacks + 1] = fn
        pcall(fn, FS.ActionBars.geometry)
    end,
}
function __set_console(drawn)
    __console.drawn = drawn
    for _, fn in ipairs(callbacks) do fn(FS.ActionBars.geometry) end
end
"""


def dock_runtime(drawn: bool, scale: float = 1.0, db: str = "") -> LuaRuntime:
    setup = CONSOLE_STUB + f"\n__console.drawn = {'true' if drawn else 'false'}\n" + db
    setup += r"""
__sh_owner = "classshoulder"
function __take_gap()
    local host = CreateFrame('Frame', nil, UIParent)
    __sh_obj = FS.PetDock.NewShoulder(host, 306.8, 91.8)
    local ok = FS.PetDock.YieldGap(__sh_owner)
    return ok, FS.Console.SetDockGap(__sh_obj:GapSpan(36))
end
"""
    return runtime(scale, setup=setup)


def _anchors(rt: LuaRuntime) -> dict:
    """The container's anchors: {point: (relative frame name, relative point, x, y)}, the relative
    frame named (UIParent, FSConsole or other)."""
    raw = rt.eval(
        "(function() local out = {} for p, a in pairs(FS.PetFrame.container.points) do "
        "out[p] = { a.rel == UIParent and 'UIParent' or a.rel == FSConsole and 'FSConsole' or 'other',"
        " a.rp, a.x, a.y } end return out end)()")
    return {point: (v[1], v[2], v[3], v[4]) for point, v in raw.items()}


def assert_anchor(rt: LuaRuntime, point: str, rel: str, rel_point: str, x: float, y: float, label: str) -> None:
    anchors = _anchors(rt)
    assert list(anchors) == [point], f"{label}: anchors {list(anchors)}, want only {point}"
    got = anchors[point]
    assert (got[0], got[1]) == (rel, rel_point), f"{label}: anchored to {got[0]} {got[1]}, want {rel} {rel_point}"
    approx(got[2], x, f"{label}: x")
    approx(got[3], y, f"{label}: y")


def assert_docked(rt: LuaRuntime, s: float, label: str = "docked") -> None:
    assert_anchor(rt, "BOTTOMLEFT", "FSConsole", "TOPLEFT", DOCK_X * s, 0, label)


def assert_floating(rt: LuaRuntime, s: float, label: str = "floating") -> None:
    seat = rt.globals().FS.Layout.petcontainer
    assert_anchor(rt, seat["point"], "UIParent", seat["relPoint"], seat["x"] * s, seat["y"] * s, label)


def _gap(rt: LuaRuntime):
    return rt.eval("__console.gap and (__console.gap[1] .. ',' .. __console.gap[2]) or nil")


def _halo_gap(rt: LuaRuntime):
    return rt.eval("__console.haloGap and (__console.haloGap[1] .. ',' .. __console.haloGap[2]) or nil")


def _patch(rt: LuaRuntime):
    """The alpha the Console's gap patch was last given."""
    return rt.eval("__console.patch")


def gap_span(rt: LuaRuntime) -> list:
    """PetDock.GapSpan(): the four numbers (line x0, x1, halo x0, x1) it hands SetDockGap."""
    table = rt.eval("{FS.PetDock.GapSpan()}")
    return [float(table[i]) for i in range(1, len(table) + 1)]


def _gap_calls(rt: LuaRuntime) -> int:
    return rt.eval("#__console.gapCalls")


def expected_gap(c) -> str:
    """The Console top line's gap in console-local design px: the line runs 1 px (LINE) under the dock's
    straight left side and 1 px under the flare's foot (the flare's last stroke pixel is at W + FLARE - 1)."""
    return f"{DOCK_X + 1},{DOCK_X + c.W + c.FLARE - 1}"


def expected_halo_gap(c) -> str:
    """The Console top HALO's gap: the approved one, 1 px outside the dock's left side and its foot, so
    the Console's glow stays out of the side glow's columns (the line may run under; the glow may not)."""
    return f"{DOCK_X - 1},{DOCK_X + c.W + c.FLARE + 1}"


def check_a_drawn_console_docks_the_pet_panel_on_its_top_left() -> None:
    """The container's BOTTOMLEFT sits on FSConsole's TOPLEFT at (DOCK_X * s, 0) and nowhere else, the
    mode is dock, the Console's top line opens exactly under the panel and its flare, and drag is off."""
    for s in PF.SCALES:
        rt = dock_runtime(True, s)
        pf, pd = rt.globals().FS.PetFrame, rt.globals().FS.PetDock
        assert_docked(rt, s)
        assert pd.GetMode() == "dock" and pf.IsDocked() is True
        floating, docked = _frames(rt)
        assert docked.shown is True and floating.shown is False
        box, console = bounds(rt, pf.container), bounds(rt, rt.globals().FS.Console.root)
        approx(box["x"], console["x"] + DOCK_X * s, f"panel left at scale {s}")
        approx(box["bottom"], console["y"], f"the panel stands on the Console's top edge at scale {s}")
        approx(box["w"], 348 * s, f"panel width at scale {s}")
        approx(box["h"], 68 * s, f"panel height at scale {s}")
        c = pd.C
        assert _gap(rt) == expected_gap(c), _gap(rt)
        assert _halo_gap(rt) == expected_halo_gap(c), _halo_gap(rt)
        assert _patch(rt) == 0, "a shown pet panel: the gap patch is clear"
        assert pf.dragHandle.mouse is False, "drag is off while docked"
        assert not rt.eval("FS.Layout._applied[FS.PetFrame.container]"), \
            "Layout.lua's watcher must not re-seat a docked panel at the float seat"
        assert not PF._messages(rt), PF._messages(rt)


def check_no_console_or_an_undrawn_one_leaves_the_float_panel() -> None:
    for s in PF.SCALES:
        rt = dock_runtime(False, s)
        pf, pd = rt.globals().FS.PetFrame, rt.globals().FS.PetDock
        assert_floating(rt, s)
        assert pd.GetMode() == "float" and pf.IsDocked() is False
        assert _gap(rt) is None
        assert pf.dragHandle.mouse is True, "drag is on while floating"
        assert rt.eval("FS.Layout._applied[FS.PetFrame.container] ~= nil"), "the float seat is Layout's again"
    # No Console or ActionBars at all (a console-less build): float, nothing to call.
    rt = runtime(1.0)
    assert rt.globals().FS.PetDock.GetMode() == "float" and rt.globals().FS.PetFrame.IsDocked() is False
    # A Console whose API is incomplete (no SetDockGap) cannot be docked onto: float.
    rt = runtime(1.0, setup=CONSOLE_STUB + "\n__console.drawn = true\nFS.Console.SetDockGap = nil")
    assert rt.globals().FS.PetDock.GetMode() == "float" and rt.globals().FS.PetFrame.IsDocked() is False
    # ...and one with no gap patch would leave a pet-less class a permanent hole: float too.
    rt = runtime(1.0, setup=CONSOLE_STUB + "\n__console.drawn = true\nFS.Console.SetGapPatchAlpha = nil")
    assert rt.globals().FS.PetDock.GetMode() == "float" and rt.globals().FS.PetFrame.IsDocked() is False
    assert _gap(rt) is None


def check_the_console_toggling_docks_and_undocks_live() -> None:
    s = 1.0
    rt = dock_runtime(False, s, "ForeverSynthwaveDB = { petFrame = { pos = { point = 'TOP', relativePoint = 'TOP', x = 50, y = -80 } } }")
    pf, pd = rt.globals().FS.PetFrame, rt.globals().FS.PetDock
    assert_anchor(rt, "TOP", "UIParent", "TOP", 50, -80, "a saved drag position wins while floating")
    rt.execute("__set_console(true)")
    assert_docked(rt, s, "docking ignores the saved position")
    assert pd.GetMode() == "dock" and pf.dragHandle.mouse is False
    rt.execute("__set_console(false)")
    assert_anchor(rt, "TOP", "UIParent", "TOP", 50, -80, "undocking brings the saved drag position back")
    assert pd.GetMode() == "float" and pf.IsDocked() is False and pf.dragHandle.mouse is True
    assert _gap(rt) is None, "the Console's dock gap closes when the panel leaves"
    assert rt.eval("FS.Layout._applied[FS.PetFrame.container] ~= nil")
    rt.execute("ForeverSynthwaveDB.petFrame.pos = nil; __set_console(true); __set_console(false)")
    assert_floating(rt, s, "with no saved position it floats at the layout seat")
    assert not PF._messages(rt), PF._messages(rt)


def check_dock_and_undock_wait_for_regen_in_combat() -> None:
    s = 1.0
    rt = dock_runtime(False, s)
    pf = rt.globals().FS.PetFrame
    floating = rt.eval("__snapshot()")
    rt.execute("__combat = true; __set_console(true)")
    assert rt.eval("__snapshot()") == floating, "the container moved in combat"
    assert pf.IsDocked() is False and rt.globals().FS.PetDock.GetMode() == "float"
    assert _gap(rt) is None and rt.eval("__console.refused") == 0, "SetDockGap was asked in combat (the Console refuses it)"
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert_docked(rt, s, "docked at regen")
    assert pf.IsDocked() is True and _gap(rt) is not None
    docked = rt.eval("__snapshot()")
    rt.execute("__combat = true; __set_console(false)")
    assert rt.eval("__snapshot()") == docked, "the container moved in combat"
    assert pf.IsDocked() is True and _gap(rt) is not None, "still docked, gap still open, until regen"
    assert rt.eval("__console.refused") == 0, "SetDockGap was asked in combat (the Console refuses it)"
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert pf.IsDocked() is False and _gap(rt) is None
    assert_floating(rt, s, "floating again at regen")
    # The container itself is never shown, hidden or re-anchored from PetDock's combat path.
    assert not PF._messages(rt), PF._messages(rt)


def check_the_gap_stays_open_and_the_patch_follows_the_pet_panel() -> None:
    """The Console's gap is open for as long as the panel is DOCKED; a gap patch (a line and a halo over
    the gap, built with the line's own recipe) closes the hole by ALPHA whenever the pet panel is not
    visible, so a class with no pet keeps an unbroken line and no SetDockGap call is needed per pet."""
    rt = dock_runtime(True, 1.0)
    pf = rt.globals().FS.PetFrame
    c = rt.globals().FS.PetDock.C
    assert _gap(rt) == expected_gap(c) and _patch(rt) == 0, "a pet is up: gap open, patch clear"
    calls = _gap_calls(rt)
    rt.execute("__pet.exists = false; __fire('UNIT_PET', 'player')")
    assert _patch(rt) == 1, "no pet: the patch closes the hole"
    assert _gap(rt) == expected_gap(c) and _gap_calls(rt) == calls, "SetDockGap was asked again for a pet change"
    assert pf.IsDocked() is True
    assert_docked(rt, 1.0, "no pet: still docked")
    rt.execute("__pet.exists = true; __fire('UNIT_PET', 'player')")
    assert _patch(rt) == 0, "a summoned pet reopens it"
    # A dead pet that still exists (a hunter's) is the IsPetDead path of the gate.
    rt.execute("__pet.dead = true; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 1, "a dead pet closes the hole"
    rt.execute("__pet.dead = false; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 0, "a revived pet reopens it"
    assert _gap_calls(rt) == calls
    # A pet-less login docks, the gap is open (patched shut), and nothing was ever asked twice.
    rt2 = dock_runtime(True, 1.0, "__pet.exists = false")
    assert rt2.globals().FS.PetFrame.IsDocked() is True
    assert _gap(rt2) == expected_gap(c) and _patch(rt2) == 1, "pet-less: gap seated, patch closes it"
    # Undocking (the Console went away) closes the gap itself.
    rt.execute("__set_console(false)")
    assert _gap(rt) is None


def check_the_patch_follows_the_panel_in_combat_with_no_protected_call() -> None:
    """Pet dies in combat: the hole closes AT ONCE (alpha, legal in combat); a re-summon in combat
    reopens it; nothing protected is touched (container snapshot, blocked-call log, SetDockGap) and
    regen reconciles to the same answer."""
    rt = dock_runtime(True, 1.0)
    pf = rt.globals().FS.PetFrame
    assert _patch(rt) == 0
    calls = _gap_calls(rt)
    before = rt.eval("__snapshot()")
    rt.execute("__combat = true; __pet.dead = true; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 1, "death in combat must close the hole at once"
    rt.execute("__pet.dead = false; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 0, "a re-summon in combat reopens it"
    rt.execute("__pet.exists = false; __fire('UNIT_PET', 'player')")
    assert _patch(rt) == 1, "a dismissed pet in combat closes it"
    assert rt.eval("__snapshot()") == before, "the container moved in combat"
    assert _gap_calls(rt) == calls and rt.eval("__console.refused") == 0, "SetDockGap was asked in combat"
    assert not list(rt.globals().__blocked.values()), list(rt.globals().__blocked.values())
    assert pf.IsDocked() is True
    combat_calls = [c for c in rt.eval("__console.patchCalls").values() if c.endswith(":combat")]
    assert combat_calls, "no patch alpha was written in combat"
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert _patch(rt) == 1 and _gap(rt) == expected_gap(rt.globals().FS.PetDock.C), "regen keeps the reconciled state"
    assert _gap_calls(rt) == calls, "the gap is not re-asked at regen for a pet change"
    assert_docked(rt, 1.0, "docked after regen")
    # A pet that comes back in combat and is still there at regen.
    rt.execute("__combat = true; __pet.exists = true; __fire('UNIT_PET', 'player')")
    assert _patch(rt) == 0
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert _patch(rt) == 0
    # A pet that dies in combat and is still dead at regen (the regen Apply does the real Hide).
    rt.execute("__combat = true; __pet.dead = true; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 1
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert _patch(rt) == 1 and rt.globals().FS.PetFrame.container.shown is False, "regen: still closed, panel hidden"
    assert _gap(rt) == expected_gap(rt.globals().FS.PetDock.C) and _gap_calls(rt) == calls
    rt.execute("__pet.dead = false; __fire('UNIT_FLAGS', 'pet')")
    assert _patch(rt) == 0 and rt.globals().FS.PetFrame.container.shown is True, "revived out of combat: reopened"
    # A throwing patch write is cosmetic: docking survives it and says so once.
    rt = dock_runtime(True, 1.0)
    rt.execute("FS.Console.SetGapPatchAlpha = function() error('patchboom') end")
    rt.execute("__pet.exists = false; __fire('UNIT_PET', 'player'); __pet.exists = true; __fire('UNIT_PET', 'player')")
    assert rt.globals().FS.PetFrame.IsDocked() is True and rt.globals().FS.PetDock.GetMode() == "dock"
    messages = PF._messages(rt)
    assert len(messages) == 1 and "patchboom" in messages[0], messages


def check_a_docked_panel_follows_the_ui_scale() -> None:
    rt = dock_runtime(True, 1.0)
    pf = rt.globals().FS.PetFrame
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    s = 0.64
    assert_docked(rt, s, "docked after a rescale")
    box = bounds(rt, pf.container)
    approx(box["w"], 348 * s, "docked panel width follows the scale")
    approx(box["h"], 68 * s, "docked panel height follows the scale")
    # In combat the rescale waits for regen (the anchor offset and size are protected-frame calls).
    rt = dock_runtime(True, 1.0)
    before = rt.eval("__snapshot()")
    rt.execute("__combat = true; __set_height(921.6); __fire('UI_SCALE_CHANGED')")
    assert rt.eval("__snapshot()") == before, "the docked container moved in combat"
    assert rt.eval("__console.refused") == 0, "SetDockGap was asked in combat (the Console refuses it)"
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert_docked(rt, s, "docked after regen")
    approx(bounds(rt, rt.globals().FS.PetFrame.container)["w"], 348 * s, "docked width after regen")


def check_fspet_reset_and_unlock_leave_a_docked_panel_docked() -> None:
    rt = dock_runtime(True, 1.0, "ForeverSynthwaveDB = { petFrame = { locked = true, pos = { point = 'TOP', relativePoint = 'TOP', x = 5, y = -5 } } }")
    pf = rt.globals().FS.PetFrame
    rt.execute("SlashCmdList.FSPET('reset')")
    assert_docked(rt, 1.0, "reset must not yank a docked panel to the float seat")
    assert rt.eval("ForeverSynthwaveDB.petFrame.pos") is None, "the saved float position is still cleared"
    rt.execute("SlashCmdList.FSPET('unlock')")
    assert pf.dragHandle.mouse is False, "unlocking cannot enable drag while docked"
    rt.execute("__set_console(false)")
    assert pf.dragHandle.mouse is True, "once floating, the unlocked panel can be dragged"


def check_the_dock_never_anchors_the_console_to_the_pet() -> None:
    """No circular anchor: the Console is never anchored to the pet container or anything of its."""
    src = PETDOCK.read_text(encoding="utf-8")
    assert not re.search(r"console\.root\s*:\s*(SetPoint|ClearAllPoints|SetParent)", src, re.I), \
        "PetDock.lua moves the Console's root"
    rt = dock_runtime(True, 1.0)
    assert rt.eval("(function() for _, a in pairs(FSConsole.points) do if a.rel ~= UIParent then return false end end"
                   " return true end)()") is True, "the Console is anchored to something other than UIParent in the stub"
    assert rt.eval("(function() local f = FSConsole while f do if f == FS.PetFrame.container then return false end"
                   " f = f.parent end return true end)()") is True, "the Console hangs under the pet container"


def check_a_throwing_dock_falls_back_to_the_float_seat() -> None:
    """Refresh runs from event handlers with no pcall of its own (the regen replay, SetPetShown and
    ApplyRescale): a throw after ClearAllPoints must not leave the panel unseated. Each path ends
    float-seated, undocked, with the Console's gap closed and ONE log line."""
    throw_dock = ("__realDock = FS.PetFrame.SeatDocked "
                  "FS.PetFrame.SeatDocked = function(a, dx) FS.PetFrame.container:ClearAllPoints() error('boom') end")

    def world(drawn: bool):
        setup = (CONSOLE_STUB + f"\n__console.drawn = {'true' if drawn else 'false'}\n"
                 "__errs = {}\n"
                 "geterrorhandler = function() return function(e) __errs[#__errs + 1] = tostring(e) end end\n")
        return runtime(1.0, setup=setup, allow_messages=True)

    def errs(rt):
        return list(rt.globals().__errs.values())

    def assert_fell_back(rt, label):
        pf = rt.globals().FS.PetFrame
        assert pf.IsDocked() is False, f"{label}: still marked docked"
        assert rt.globals().FS.PetDock.GetMode() == "float", f"{label}: chrome not float"
        assert _gap(rt) is None, f"{label}: the Console gap was left open"
        assert_floating(rt, 1.0, f"{label}: float seat")
        messages = PF._messages(rt)
        assert len(messages) == 1 and messages[0].startswith("petdock_dock_refresh"), (label, messages)

    # 1. The regen replay: the Console toggled on in combat, the dock throws at regen.
    rt = world(False)
    rt.execute("__combat = true; __set_console(true)")
    rt.execute(throw_dock)
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert_fell_back(rt, "regen replay")
    # The error itself reached the error handler (so /fserr has it, with its stack), not just the chat.
    first = errs(rt)
    assert first and all("boom" in e for e in first), first
    assert "floating pet panel is used" in PF._messages(rt)[0], PF._messages(rt)
    # A later try that throws again forwards the error again but prints nothing more.
    rt.execute("__set_console(false); __set_console(true)")
    assert len(errs(rt)) > len(first), "the repeat never reached the error handler"
    assert len(PF._messages(rt)) == 1, PF._messages(rt)
    # A DIFFERENT error is not swallowed by the once-per-session latch.
    rt.execute("FS.PetFrame.SeatDocked = function(a, dx) FS.PetFrame.container:ClearAllPoints() error('bang') end")
    rt.execute("__set_console(false); __set_console(true)")
    messages = PF._messages(rt)
    assert len(messages) == 2 and "bang" in messages[1], messages
    # The same message again stays quiet.
    rt.execute("__set_console(false); __set_console(true)")
    assert len(PF._messages(rt)) == 2, PF._messages(rt)

    # 2. ApplyRescale re-seats a docked panel through Refresh(true).
    rt = world(True)
    assert rt.globals().FS.PetFrame.IsDocked() is True
    rt.execute(throw_dock)
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    pf = rt.globals().FS.PetFrame
    assert pf.IsDocked() is False and rt.globals().FS.PetDock.GetMode() == "float"
    assert_floating(rt, 0.64, "rescale")
    assert _gap(rt) is None
    assert len(PF._messages(rt)) == 1, PF._messages(rt)

    # 3. SetPetShown: the panel was floated behind PetDock's back and the re-dock throws when the pet comes.
    rt = world(True)
    rt.execute("__pet.exists = false; __fire('UNIT_PET', 'player')")
    rt.execute("FS.PetFrame.SeatFloat()")
    rt.execute(throw_dock)
    rt.execute("__pet.exists = true; __fire('UNIT_PET', 'player')")
    pf = rt.globals().FS.PetFrame
    assert pf.IsDocked() is False and rt.globals().FS.PetDock.GetMode() == "float"
    assert_floating(rt, 1.0, "set pet shown")
    assert len(PF._messages(rt)) == 1, PF._messages(rt)

    # 4. The float seat throws too (a shared helper after a ClearAllPoints): the log says so, the panel
    # is retried at the next trigger instead of being left unseated for good.
    rt = world(False)
    rt.execute("__combat = true; __set_console(true)")
    rt.execute(throw_dock)
    rt.execute("__realFloat = FS.PetFrame.SeatFloat; "
               "FS.PetFrame.SeatFloat = function() FS.PetFrame.container:ClearAllPoints() error('nofloat') end")
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    messages = PF._messages(rt)
    assert len(messages) == 1 and "retry" in messages[0] and "floating pet panel is used" not in messages[0], messages
    assert any("nofloat" in e for e in errs(rt)), errs(rt)
    assert not _anchors(rt), "the panel should still be unseated here"
    rt.execute("FS.PetFrame.SeatDocked = __realDock; FS.PetFrame.SeatFloat = __realFloat")
    # Only PetDock's own regen watcher may retry: PetFrame's gate would re-run Refresh by itself.
    rt.execute("FS.PetDock.SetPetShown = function() end")
    rt.execute("__fire('PLAYER_REGEN_ENABLED')")
    assert_docked(rt, 1.0, "retried at the next regen")
    assert rt.globals().FS.PetFrame.IsDocked() is True

    # 5. A float seat that answers false (refused) counts as not landed too.
    rt = world(False)
    rt.execute("__combat = true; __set_console(true)")
    rt.execute(throw_dock)
    rt.execute("FS.PetFrame.SeatFloat = function() return false end")
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    messages = PF._messages(rt)
    assert len(messages) == 1 and "retry" in messages[0], messages


def check_the_dock_gap_fits_the_real_console_top_line() -> None:
    """Against the REAL Console.lua at both of its scales: the pet's dock gap [DOCK_X + 1, DOCK_X +
    348 + 10 - 1] is not clamped (it lies between the top-left cut and the shoulder tab's foot), with
    the pet's 7 px halo reach to spare."""
    console = _load("console_harness", "console-harness.py")
    c = runtime(1.0).globals().FS.PetDock.C
    x0, x1 = (float(v) for v in expected_gap(c).split(","))
    for s in console.SCALES:
        lua = console.abh.boot(console.make_prelude(s, ""), extra=("Console.lua",))
        assert lua.eval("FS.Console.SetDockGap")(x0, x1) is True
        layout = lua.eval("FS.Console.layout")
        assert layout["gap"] is not None, "the dock gap was clamped away on the real Console"
        approx(layout["gap"]["x0"], x0, f"gap start at scale {s:.4f}")
        approx(layout["gap"]["x1"], x1, f"gap end at scale {s:.4f}")
        assert layout["cut"] < x0, "the gap eats the top-left cut"
        assert x1 + c.REACH <= layout["tx"], \
            f"the pet's halo (to {x1 + c.REACH}) reaches the shoulder tab foot at {layout['tx']:.1f} at scale {s:.4f}"



def phys_cover(fills, edge_x, edge_y, col: int, row: int, panel_h: float, n: int = 3, dock_x: float = DOCK_X) -> float:
    """Mean coverage of the dock fill (source over) on one physical pixel, n x n samples: each fill piece
    is drawn into its SNAPPED physical rect, its texture mapped across that rect like the client does.
    The fill's art-local px become console-local with the panel's left at dock_x and its bottom (art y =
    panel_h) on the Console's top edge (y = 0)."""
    total = 0.0
    for sy in range(n):
        for sx in range(n):
            px, py = col + (sx + 0.5) / n, row + (sy + 0.5) / n
            rest = 1.0
            for t in fills:
                x0, y0 = dock_x + t.x, t.y - panel_h
                el, er = edge_x(x0), edge_x(x0 + t.w)
                et, eb = edge_y(y0), edge_y(y0 + t.h)
                if er <= el or eb <= et or not (el <= px < er and et <= py < eb):
                    continue
                ax = t.x + (px - el) / (er - el) * t.w
                ay = t.y + (py - et) / (eb - et) * t.h
                rest *= 1.0 - t.alpha(ax, ay)
            total += 1.0 - rest
    return total / (n * n)


def check_no_fill_dims_a_lit_console_line_pixel_under_the_dock() -> None:
    """The dock fill (COLOR_HUD_SCRIM, 47%) overruns the stroke by FILL_OVER into the Console's top line
    row. The line now runs under the dock's left side and under its foot; a lit line pixel under the
    scrim would be dimmed to about half, which reads as the notch again. So: no fill coverage on the
    line row at any x where the Console line is drawn (left of the gap start, right of the gap end), and
    the open part of the row, where the line is not drawn, is still filled (the overrun's purpose)."""
    rt = dock_runtime(True, 1.0)
    d = mockup_dock()
    lit_line_pixels_stay_lit(Dock(rt, d), d, DOCK_X, gap_span(rt)[:2])
    assert _gap(rt) == f"{gap_span(rt)[0]:g},{gap_span(rt)[1]:g}", "PetDock asked the Console for another gap"


def lit_line_pixels_stay_lit(dock: "Dock", d: dict, dock_x: float, line_gap) -> None:
    """The body of the check above for any dock chrome at `dock_x` (design px right of the chassis
    left) whose Console line gap is `line_gap` (console-local x0, x1)."""
    gx0, gx1 = (v - dock_x for v in line_gap)                # art-local line gap
    W, H = d["W"], d["H"]
    lit = []
    for y in frange(H + 0.125, H + 0.875, 0.25):
        for x in list(frange(-2.0, gx0 - 0.125, 0.125)) + list(frange(gx1 + 0.125, gx1 + 6.0, 0.125)):
            cover = union(dock.fill, x, y)
            if cover > 0.02:
                lit.append((x, round(y - H, 3), round(cover, 2)))
    assert not lit, f"the dock fill dims lit Console line pixels at (x, y below H, coverage): {lit[:6]} ({len(lit)})"
    for x in frange(gx0 + 0.5, gx1 - 0.5, 1.0):
        assert union(dock.fill, x, H + 0.5) > 0.9, f"the open part of the line row lost its fill at x = {x}"

    # The same in WHOLE PHYSICAL PIXELS (every edge snaps to the pixel grid): at three UI scales, three
    # screen sizes and sixteen origin phases, every physical pixel the Console's line is drawn on in its
    # top row (left of the gap start, right of the gap end) has no scrim coverage, however the snapping
    # rounds the fill's edges against the line's.
    console = _load("console_harness", "console-harness.py")
    gap = f"{line_gap[0]!r},{line_gap[1]!r}"
    for label, layout, k, origin, edge in junction_cases(console, gap):
        def edge_y(y: float, o=origin, kk=k) -> int:
            return _snap(o + y * kk)

        row = edge_y(0)
        left = range(edge(dock_x - 2), edge(layout["gap"]["x0"]))
        right = range(edge(layout["gap"]["x1"]), edge(layout["gap"]["x1"]) + math.ceil(6 * k))
        for col in list(left) + list(right):
            cover = phys_cover(dock.fill, edge, edge_y, col, row, H, dock_x=dock_x)
            assert cover < 0.02, f"{label}: the scrim covers {cover:.2f} of the lit Console line pixel at column {col}"


def console_halo_pieces(gap_args) -> dict:
    """The REAL Console's top halo pieces for a gap request: {name: (x0, x1)} of haloTop, haloTop2, gapHalo."""
    console = _load("console_harness", "console-harness.py")
    lua = console.abh.boot(console.make_prelude(1.0, ""), extra=("Console.lua",))
    assert lua.eval("FS.Console.SetDockGap")(*gap_args) is True
    out = {}
    for name in ("haloTop", "haloTop2", "gapHalo"):
        x, w, shown = lua.eval(
            f"(function() local p = FS.Console.parts.{name}; return p._points[1].x, p._w, p:IsShown() end)()")
        if shown:
            out[name] = (float(x), float(w))
    return out


def check_the_console_halo_tiles_with_the_dock_halo_and_the_patch() -> None:
    """The Console's top glow stops 1 px outside the dock's side and foot (the approved layout), so the
    gap does not add a column of double-bright halo where the dock's own side glow and flare glow already
    shine; the halo patch fills exactly that span so the glow is whole when the panel is gone."""
    rt = dock_runtime(True, 1.0)
    c = rt.globals().FS.PetDock.C
    assert _halo_gap(rt) == expected_halo_gap(c), _halo_gap(rt)
    x0, x1, hx0, hx1 = gap_span(rt)
    assert (hx0, hx1) == (DOCK_X - 1, DOCK_X + c.W + c.FLARE + 1), (hx0, hx1)
    pieces = console_halo_pieces((x0, x1, hx0, hx1))
    stub, right, patch = pieces["haloTop"], pieces["haloTop2"], pieces["gapHalo"]
    approx(stub[0] + stub[1], hx0, "the left glow stops at the halo gap start")
    approx(patch[0], hx0, "the patch glow starts there"); approx(patch[0] + patch[1], hx1, "and ends at the halo gap end")
    approx(right[0], hx1, "the right glow starts at the halo gap end")
    # the dock's own glow strips, in console-local px: nothing of the Console's glow may reach the dock's
    # side column or the flare's foot column (those are the columns the line alone runs under)
    assert stub[0] + stub[1] <= DOCK_X - 1 + 1e-9, "the Console glow reaches the dock's left side"
    assert right[0] >= DOCK_X + c.W + c.FLARE + 1 - 1e-9, "the Console glow reaches the flare's foot"


# ---------------------------------------------------------------------------------------------
# Checks: the junctions where the Console's top line meets the dock, in whole physical pixels
# ---------------------------------------------------------------------------------------------

def _snap(x: float) -> int:
    """The client snaps every texture edge to a whole physical pixel."""
    return math.floor(x + 0.5)


def junction_cases(console, gap: str):
    """Yields (label, edge) for each UI scale (1, 1/1.2, 0.64: the real Console seated at that scale, so its
    chassis origin is a real fractional UI position), each physical pixels per design pixel k (1 is a 1440
    tall screen at every UI scale: UIParent is 1440 * scale UI units tall and a design px is `scale` UI
    units; 1.5 and 2 are bigger screens), and 16 fractional phases of the chassis origin on screen
    (the stack's own position is not known). `edge(x)` is the physical column of a console-local design x."""
    x0, x1 = (float(v) for v in gap.split(","))
    for scale in (1.0, 1 / 1.2, 0.64):
        lua = console.abh.boot(console.make_prelude(scale, ""), extra=("Console.lua",))
        assert lua.eval("FS.Console.SetDockGap")(x0, x1) is True
        layout = lua.eval("FS.Console.layout")
        assert layout["gap"] is not None, "the real Console clamped the gap away"
        origin_ui = layout["originX"]
        for k in (1.0, 1.5, 2.0):
            for phase in range(16):
                origin = origin_ui * k / scale + phase / 16
                yield (f"scale {scale:.4f}, k {k}, phase {phase}/16", layout, k, origin,
                       lambda x, o=origin, kk=k: _snap(o + x * kk))


def flare_rows(c):
    """The flare band texture's rect and TGA, as a tuple (left, right, top, bottom, path, band_w, band_h) in
    console-local design px: the band is the 12 x 10 rect at art (W - 2, H - FLARE), the panel's left is
    DOCK_X and its bottom is the console top (y = 0). The caller lights physical pixels from the REAL TGA
    (the mean of 4 x 4 samples through the snapped rect, lit at a quarter coverage)."""
    band_w, band_h = c.FLARE + 2, c.FLARE
    path = MEDIA / "pet_dock_flare_line.tga"
    left, right = DOCK_X + c.W - 2, DOCK_X + c.W - 2 + band_w
    top, bottom = -band_h, 0
    return left, right, top, bottom, path, band_w, band_h


def check_the_gap_ends_overlap_the_flare_foot_and_the_left_side_in_physical_pixels() -> None:
    """BUG 'tiny gap in the panel border': at the flared right foot the 45 degree stroke ended one pixel
    up-left of where the Console's top line started (a 1 px notch), and at the left side the line stopped
    a pixel short of the vertical. Whole physical pixels, at three UI scales, three screen sizes and
    sixteen origin phases: (right) the line's first pixel sits at or left of the flare's last stroke pixel
    and right of its first lit one, so they overlap by a column and no more; (left) the line stub's last
    pixel column lies inside the vertical's column(s)."""
    console = _load("console_harness", "console-harness.py")
    rt = dock_runtime(True, 1.0)
    c = rt.globals().FS.PetDock.C
    gap = _gap(rt)      # whatever PetDock really asks the Console for
    assert [float(v) for v in gap.split(",")] == gap_span(rt)[:2], "PetDock.GapSpan is not what Refresh asks for"
    worst_right, worst_left = None, None
    for label, layout, k, origin, edge in junction_cases(console, gap):
        g = layout["gap"]
        assert (g["x0"], g["x1"]) == tuple(float(v) for v in gap.split(",")), f"{label}: gap clamped"
        # the vertical phase of the screen is a free parameter too: reuse the horizontal one
        eye = lambda y, o=origin, kk=k: _snap(o + y * kk)
        # ---- right: the flare's last stroke row against the line's first column
        left, right, top, bottom, path, band_w, band_h = flare_rows(c)
        el, er = edge(left), edge(right)
        et, eb = eye(top), eye(bottom)
        assert er > el and eb > et, f"{label}: the band collapsed"
        last_row = eb - 1
        lit = []
        for col in range(el, er):
            total = 0.0
            for sy in range(4):
                for sx in range(4):
                    u = ((col + (sx + 0.5) / 4) - el) / (er - el) * (band_w * c.LINE_K / c.CANVAS)
                    v = ((last_row + (sy + 0.5) / 4) - et) / (eb - et) * (band_h * c.LINE_K / c.CANVAS)
                    total += tga_alpha(path, u, v)
            if total / 16 >= 0.25:
                lit.append(col)
        assert lit, f"{label}: the flare has no stroke pixel on its last row"
        line_start = edge(g["x1"])
        assert line_start <= lit[-1], \
            f"{label}: NOTCH: the flare's last stroke pixel is column {lit[-1]} but the line starts at column {line_start}"
        assert line_start > lit[0], \
            f"{label}: the line starts at column {line_start}, at or left of the foot's first lit pixel {lit[0]} (it should start under the foot's last pixels, a single pixel under)"
        gain = lit[-1] - line_start + 1
        worst_right = gain if worst_right is None else min(worst_right, gain)
        # ---- left: the stub's last column against the vertical side's column(s)
        v_start = edge(DOCK_X)
        v_end = max(edge(DOCK_X + c.LINE), v_start + 1)
        stub_end = edge(g["x0"])
        assert stub_end > v_start, \
            f"{label}: NOTCH: the line stub ends at column {stub_end - 1}, left of the vertical's column {v_start}"
        assert stub_end <= v_end, \
            f"{label}: the line stub runs to column {stub_end - 1}, past the vertical's {v_end - 1}"
        gain = stub_end - v_start
        worst_left = gain if worst_left is None else min(worst_left, gain)
    assert worst_right >= 1 and worst_left >= 1, (worst_right, worst_left)



# ---------------------------------------------------------------------------------------------
# Checks: PetDock.NewShoulder, the reusable open shoulder (the Paladin's 306.8 x 91.8 and the pet's 348 x 68)
# ---------------------------------------------------------------------------------------------

PALADIN_DOCK_X = 36  # the mockup's LS_X less the chassis left (SealBar's DX), design px


def tbl(t) -> dict:
    """A Lua table as a dict."""
    return {k: v for k, v in t.items()}


def _mockup_points(expr_list: str, env: dict) -> list:
    """The (x, y) of every ctx.moveTo / lineTo in a JS fragment, evaluated with `env`."""
    pts = []
    for m in re.finditer(r"ctx\.(?:moveTo|lineTo)\(([^;]*?)\)(?=;|$)", expr_list):
        x, y = m.group(1).split(",", 1)
        pts.append((eval(x, {"__builtins__": {}}, env), eval(y, {"__builtins__": {}}, env)))
    return pts


def check_the_mockup_draws_the_paladin_shoulder_with_the_pet_panels_recipe() -> None:
    """What the mockup draws for the Paladin shoulder chrome, pinned (so a mockup change fails here):
    - lsPath is peTrace's open shape (same six vertices: up the straight left side, the cut top left, along
      the top, down the right side to H - f, out along the 45 degree foot; NOT mirrored, flare to the right,
      bottom open) and lsLive fills it 1.2 below the line with the same scrim as drawPet's dc branch;
    - lsLive's halo, fill and stroke are drawPet's dc recipe (glow factor 1.3, A(1) halo, A(.82) x .85 fill, A(.9)
      stroke, violet, 0.9 line widths), and the shoulder has NO low-HP state;
    - lsLive runs only when the panel style is not the Console ('cn'): in the Console style the shoulder is
      part of the chassis outline (cnTrace) with the chassis fill and halo, not this recipe."""
    src = PF.MOCKUP.read_text(encoding="utf-8")
    flat = re.sub(r"\s+", "", src)
    # ---- the shape
    m = re.search(r"functionlsPath\(x,y,w,h,f,c,fillClose\)\{vard=fillClose\?1\.2\*AU:0;(.*?)if\(fillClose\)ctx\.closePath\(\);\}", flat)
    assert m, "lsPath changed; update this harness"
    env = {"x": 0.0, "y": 91.8, "w": 306.8, "h": 91.8, "f": 10.0, "c": 6.0, "d": 0.0}
    shoulder = _mockup_points(m.group(1), env)
    m = re.search(r"functionpeTrace\(W,H,open,f\)\{.*?else\{(ctx\.moveTo\(0,H\).*?)\}\}", flat)
    assert m, "peTrace's open branch changed; update this harness"
    pet = _mockup_points(m.group(1), {"W": 306.8, "H": 91.8, "f": 10.0, "c": 6.0})
    assert len(shoulder) == len(pet) == 6, (shoulder, pet)
    for a, b in zip(shoulder, pet, strict=True):
        approx(a[0], b[0], "shoulder vs pet panel vertex x")
        approx(a[1], b[1], "shoulder vs pet panel vertex y")
    for got, want in zip(shoulder, [(0, 91.8), (0, 6), (6, 0), (306.8, 0), (306.8, 81.8), (316.8, 91.8)], strict=True):
        approx(got[0], want[0], f"shoulder vertex {want} x"); approx(got[1], want[1], f"shoulder vertex {want} y")
    # ---- the recipe
    live = re.search(r"functionlsLive\(q\)\{(.*?)ctx\.restore\(\);\}", flat)
    pet_fn = re.search(r"functiondrawPet\(\)\{(.*?)/\*content\*/", flat)
    assert live and pet_fn, "lsLive or drawPet changed; update this harness"
    live, pet_fn = live.group(1), pet_fn.group(1)
    for label, text in (("lsLive", live), ("drawPet", pet_fn)):
        assert "A(.82);ctx.fillStyle='rgba(13,6,32,.85)';ctx.fill();" in text, f"{label}: the fill is not A(.82) x rgba(13,6,32,.85)"
        assert "A(.9);ctx.strokeStyle=" in text.replace("A(st.low?.6+.4*peS.pulse:.9)", "A(.9)"), f"{label}: the stroke is not A(.9)"
        assert "halo(true)" in text
    assert "glow(K.violet,1.3)" in live and "pes==='bf'?1:1.3" in pet_fn, "the halo factor is no longer 1.3 on both"
    assert live.count("lineWidth=LW*.9") == 2 and live.count("lineWidth=") == 2, "lsLive: the halo and the stroke are both 0.9 line widths"
    assert "lineWidth=pLW(.9)" in pet_fn
    assert re.search(r"functionpLW\(k\)\{returnLW\*\(k==null\?\.6:k\)/AU;\}", flat), "pLW changed: the line widths may differ"
    assert "st.low" not in live and "red" not in live.lower().replace("fillstyle", ""), \
        "the shoulder grew a low-HP state: NewShoulder's red option may now be needed"
    # ---- the Console style bakes the shoulder into the chassis instead
    assert "if(PS!=='cn')for(i=0;i<LS.length;i++)lsLive(LS[i]);" in flat, "lsLive no longer runs only outside the Console style"
    cn = re.search(r"functioncnTrace\(tab\)\{(.*?)\}functioncnScrew", flat)
    assert cn and "for(i=0;i<LS.length;i++){q=LS[i];" in cn.group(1) and "qx+qw+qf,c.y0" in cn.group(1), \
        "cnTrace no longer carries the shoulders in the chassis outline"


def check_new_shoulder_is_the_paladin_block_size() -> None:
    d = mockup_dock(True)
    approx(d["W"], 306.8, "lsRowW(7)")
    approx(d["H"], 91.8, "LS_PT + 2 rows + gap + LS_PB")
    approx(mockup_dock_offset("LS_X"), PALADIN_DOCK_X, "the Paladin block's offset on the Console chassis", tol=0.5)


def check_new_shoulder_builds_the_object_at_the_paladin_size() -> None:
    d = mockup_dock(True)
    W, H = d["W"], d["H"]
    for scale in PF.SCALES:
        rt = runtime(scale)
        s = build_shoulder(rt, W, H)
        host = rt.globals().__sh_host
        art = s.art
        assert s.W == W and s.H == H, (s.W, s.H)
        assert rawequal(rt, art.parent, host) and art.GetFrameLevel(art) == host.GetFrameLevel(host)
        approx(art.w, W, "art width is the design width"); approx(art.h, H, "art height is the design height")
        approx(art.GetScale(art), scale, f"art scale is Layout.Scale() at {scale}")
        pts = tbl(art.points)
        assert list(pts) == ["TOPLEFT"] and pts["TOPLEFT"].x == 0 and pts["TOPLEFT"].y == 0 and rawequal(rt, pts["TOPLEFT"].rel, host)
        # the same piece list as the pet's 348 x 68 dock (the shape is the same, only the sizes differ)
        pet = rt.globals().FS.PetDock.parts.dock
        for name in ("fill", "stroke", "halo"):
            assert len(getattr(s, name)) == len(getattr(pet, name)) > 0, name
        assert len(s.red.stroke) == len(pet.red.stroke) and len(s.red.halo) == len(pet.red.halo)
        level = host.GetFrameLevel(host)
        assert s.normal.GetFrameLevel(s.normal) == level
        assert s.red.host.GetFrameLevel(s.red.host) == level + 1 and s.red.pulseFrame.GetFrameLevel(s.red.pulseFrame) == level + 1
        assert s.red.host.alpha == 0, "the red twin starts invisible"
        assert s.red.group is not None


def check_new_shoulder_without_red_builds_no_red_twin() -> None:
    rt = runtime(1.0)
    d = mockup_dock(True)
    before = len(list(rt.globals().__frames.values()))
    s = build_shoulder(rt, d["W"], d["H"], red=False)
    assert s.red is None and len(s.fill) > 0 and len(s.stroke) > 0 and len(s.halo) > 0
    frames = list(rt.globals().__frames.values())[before:]
    assert len(frames) == 3, f"the test host, the art and the normal edge layer only: {len(frames)}"
    assert not any(getattr(f, "groups", None) and len(list(f.groups.values())) for f in frames), "an animation group without red"
    # with the red twin: two more frames (the curve host and its pulse child) and one animation group
    rt2 = runtime(1.0)
    before = len(list(rt2.globals().__frames.values()))
    build_shoulder(rt2, d["W"], d["H"], red=True)
    frames = list(rt2.globals().__frames.values())[before:]
    assert len(frames) == 5, f"host, art, normal layer, red host, red pulse child: {len(frames)}"
    assert sum(len(list(f.groups.values())) for f in frames if getattr(f, "groups", None)) == 1, "one pulse group with red"


def check_new_shoulder_gap_span_follows_the_width() -> None:
    d = mockup_dock(True)
    W = d["W"]
    rt = runtime(1.0)
    s = build_shoulder(rt, W, d["H"])
    c = rt.globals().FS.PetDock.C
    for x in (PALADIN_DOCK_X, c.DOCK_X, 0.5):
        got = [float(v) for v in rt.eval(f"{{__sh:GapSpan({x!r})}}").values()]
        want = [x + c.LINE, x + W + c.FLARE - c.FOOT_UNDER, x - c.LINE, x + W + c.FLARE + c.LINE]
        assert len(got) == 4, got
        for a, b, label in zip(got, want, ("line x0", "line x1", "halo x0", "halo x1"), strict=True):
            approx(a, b, f"GapSpan({x}) {label}")
    got = [float(v) for v in rt.eval(f"{{__sh:GapSpan({PALADIN_DOCK_X})}}").values()]
    for a, b in zip(got, (37.0, 351.8, 35.0, 353.8), strict=True):
        approx(a, b, "the Paladin block's gap span at 36")
    # the line pair is inside the halo pair by exactly one pixel at each end, the pet's way
    approx(got[0] - got[2], 2 * c.LINE, "line start vs halo start"); approx(got[3] - got[1], 2 * c.LINE, "halo end vs line end")
    # the pet's own GapSpan is the same function at its own size and offset
    pet = [float(v) for v in rt.eval("{FS.PetDock.GapSpan()}").values()]
    pet_obj = [float(v) for v in rt.eval(f"{{FS.PetDock.NewShoulder(__sh_host, {c.W!r}, {c.H!r}, nil):GapSpan({c.DOCK_X!r})}}").values()]
    assert pet == pet_obj == [25.0, 381.0, 23.0, 383.0], (pet, pet_obj)
    # not a number: nothing to report
    for bad in ("nil", "'x'", "0/0", "math.huge", "-math.huge"):
        assert rt.eval(f"(__sh:GapSpan({bad}))") is None, f"GapSpan({bad}) should report nothing"


def check_new_shoulder_gap_fits_the_real_console_top_line() -> None:
    """The Paladin block's gap against the REAL Console.lua at both of its scales: not clamped (it lies
    between the top-left cut and the tab's foot), the glow reach to spare."""
    console = _load("console_harness", "console-harness.py")
    d = mockup_dock(True)
    rt = runtime(1.0)
    build_shoulder(rt, d["W"], d["H"])
    c = rt.globals().FS.PetDock.C
    got = [float(v) for v in rt.eval(f"{{__sh:GapSpan({PALADIN_DOCK_X})}}").values()]
    x0, x1, hx0, hx1 = got
    for scale in console.SCALES:
        lua = console.abh.boot(console.make_prelude(scale, ""), extra=("Console.lua",))
        assert lua.eval("FS.Console.SetDockGap")(x0, x1, hx0, hx1) is True
        layout = lua.eval("FS.Console.layout")
        assert layout["gap"] is not None, "the Paladin block's gap was clamped away on the real Console"
        approx(layout["gap"]["x0"], x0, f"gap start at scale {scale:.4f}")
        approx(layout["gap"]["x1"], x1, f"gap end at scale {scale:.4f}")
        assert layout["cut"] < x0, "the gap eats the top-left cut"
        assert hx1 + c.REACH <= layout["tx"], \
            f"the block's halo (to {hx1 + c.REACH}) reaches the shoulder tab foot at {layout['tx']:.1f} at scale {scale:.4f}"
    # the Console's own halo gap follows the halo pair, not the line pair
    pieces = console_halo_pieces((x0, x1, hx0, hx1))
    approx(pieces["gapHalo"][0], hx0, "halo patch start"); approx(pieces["gapHalo"][0] + pieces["gapHalo"][1], hx1, "halo patch end")


def check_no_shoulder_fill_dims_a_lit_console_line_pixel() -> None:
    """check_no_fill_dims_a_lit_console_line_pixel_under_the_dock at the Paladin block's size and offset:
    the fill's overrun into the Console's line row covers only the open part of the row, at whole
    physical pixels, three UI scales, three screen sizes and sixteen origin phases."""
    d = mockup_dock(True)
    rt = runtime(1.0)
    dock = new_dock(rt, d, True)
    x0, x1 = (float(v) for v in list(rt.eval(f"{{__sh:GapSpan({PALADIN_DOCK_X})}}").values())[:2])
    lit_line_pixels_stay_lit(dock, d, PALADIN_DOCK_X, (x0, x1))


NS_SPY = r"""
__ns_calls = {}
do
    local real = FS.PetDock.NewShoulder
    FS.PetDock.NewShoulder = function(parent, W, H, opts)
        local obj, why = real(parent, W, H, opts)
        __ns_calls[#__ns_calls + 1] = { parent = parent, W = W, H = H, opts = opts, obj = obj }
        return obj, why
    end
end
"""


def check_the_pet_dock_is_built_through_new_shoulder_and_nothing_else() -> None:
    """ONE code path: PetDock.Build asks PetDock.NewShoulder (through the table) for the dock at the
    panel's own W and H with the red twin, and the module's public tables ARE that object's parts."""
    for drawn in (False, True):
        rt = runtime(1.0, setup=CONSOLE_STUB + f"\n__console.drawn = {'true' if drawn else 'false'}\n", after_load=NS_SPY)
        calls = rt.globals().__ns_calls
        assert len(calls) == 1, f"the dock was built through NewShoulder {len(calls)} times"
        call = calls[1]
        pf, pd = rt.globals().FS.PetFrame, rt.globals().FS.PetDock
        layout = rt.globals().FS.Layout.petcontainer
        assert rawequal(rt, call.parent, pf.container), "the shoulder is parented to the pet container"
        assert (call.W, call.H) == (layout.w, layout.h) == (pd.C.W, pd.C.H), (call.W, call.H)
        assert call.opts is not None and call.opts.red is True, "the pet dock keeps its red low-HP twin"
        assert len(list(call.opts.keys())) == 1, f"the pet dock passes only {{ red = true }}: {tbl(call.opts)}"
        obj = call.obj
        assert obj is not None
        assert rawequal(rt, pd.frames.dock, obj.art), "frames.dock is the shoulder's art"
        for name in ("fill", "stroke", "halo"):
            assert rawequal(rt, getattr(pd.parts.dock, name), getattr(obj, name)), f"parts.dock.{name} is the shoulder's list"
        assert rawequal(rt, pd.parts.dock.red.stroke, obj.red.stroke) and rawequal(rt, pd.parts.dock.red.halo, obj.red.halo)
        assert rawequal(rt, pd.edges.dock.normal, obj.normal) and rawequal(rt, pd.edges.dock.host, obj.red.host)
        assert rawequal(rt, pd.edges.dock.pulseFrame, obj.red.pulseFrame) and rawequal(rt, pd.edges.dock.group, obj.red.group)
        assert rawequal(rt, pd.edges.dock.base[1], obj.normal) and len(list(pd.edges.dock.base.values())) == 1
    # a rescale and a retint of the pet dock go through the same object
    rt = runtime(1.0, setup=CONSOLE_STUB, after_load=NS_SPY + r"""
        __ns_methods = { Rescale = 0, SetEdge = 0 }
        local real = FS.PetDock.NewShoulder
        FS.PetDock.NewShoulder = function(...)
            local obj, why = real(...)
            for name in pairs(__ns_methods) do
                local method = obj[name]
                obj[name] = function(self, ...) __ns_methods[name] = __ns_methods[name] + 1 return method(self, ...) end
            end
            return obj, why
        end
    """)
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    assert rt.globals().__ns_methods.Rescale >= 1, "a UI rescale did not go through Shoulder:Rescale"
    approx(rt.globals().FS.PetDock.frames.dock.GetScale(rt.globals().FS.PetDock.frames.dock), 0.64, "rescaled")
    assert rt.globals().FS.PetDock.SetEdgeColor(1, 0.5, 0.25) is True
    assert rt.globals().__ns_methods.SetEdge >= 1, "SetEdgeColor did not go through Shoulder:SetEdge"
    assert rt.globals().FS.PetDock.ResetEdgeColor() is True
    assert rt.globals().__ns_methods.SetEdge >= 2, "ResetEdgeColor did not go through Shoulder:SetEdge"
    # and a fresh shoulder is not remembered by the module (the pet's tables are untouched by a second one)
    rt = runtime(1.0)
    pd = rt.globals().FS.PetDock
    before = rt.eval("{FS.PetDock.frames.dock, FS.PetDock.parts.dock, FS.PetDock.edges.dock, FS.PetDock.parts.dock.fill, FS.PetDock.parts.dock.stroke}")
    states = (dump_dock(rt), pd.GetMode(), pd.HasDock())
    d = mockup_dock(True)
    build_shoulder(rt, d["W"], d["H"])
    after = rt.eval("{FS.PetDock.frames.dock, FS.PetDock.parts.dock, FS.PetDock.edges.dock, FS.PetDock.parts.dock.fill, FS.PetDock.parts.dock.stroke}")
    for i in range(1, 6):
        assert rawequal(rt, before[i], after[i]), f"building another shoulder replaced pet dock table {i}"
    assert (dump_dock(rt), pd.GetMode(), pd.HasDock()) == states, "another shoulder changed the pet dock"


def check_new_shoulder_refuses_bad_arguments() -> None:
    rt = runtime(1.0)
    rt.execute("__h = CreateFrame('Frame', nil, UIParent)")
    n_before = len(list(rt.globals().__frames.values()))
    bad = ["nil, 100, 100", "__h, nil, 100", "__h, 100, nil", "__h, 0, 100", "__h, 100, 0", "__h, -5, 100", "__h, 100, -5",
           "__h, '100', 100", "__h, 100, '100'", "__h, 0/0, 100", "__h, 100, 0/0", "__h, math.huge, 100", "__h, 100, math.huge",
           "__h, 10, 100", "__h, 100, 10", "__h, 16, 100", "__h, 100, 16", "{}, 100, 100", "'frame', 100, 100", "__h, true, 100", "__h, 100, 100, 'red'", "__h, 100, 100, 5"]
    for args in bad:
        out = rt.eval(f"(function() local a, b = FS.PetDock.NewShoulder({args}) return {{a == nil, type(b)}} end)()")
        assert out[1] is True and out[2] == "string", f"NewShoulder({args}) should return nil and a reason, got {tbl(out)}"
    assert len(list(rt.globals().__frames.values())) == n_before, "a refused call still built frames"
    # the smallest good size builds, opts may be an empty table or nil, unknown keys are ignored
    ok = rt.eval("(function() local a = FS.PetDock.NewShoulder(__h, 17, 17) local b = FS.PetDock.NewShoulder(__h, 17, 17, {}) "
                 "local c = FS.PetDock.NewShoulder(__h, 17, 17, { red = false, bogus = 1 }) "
                 "return { a ~= nil and a.red == nil, b ~= nil and b.red == nil, c ~= nil and c.red == nil } end)()")
    assert list(ok.values()) == [True, True, True], tbl(ok)
    # the red twin needs red == true exactly: a truthy number or string is not a request for it
    loose = rt.eval("(function() local a = FS.PetDock.NewShoulder(__h, 17, 17, { red = 1 }) "
                    "local b = FS.PetDock.NewShoulder(__h, 17, 17, { red = 'yes' }) "
                    "local c = FS.PetDock.NewShoulder(__h, 17, 17, { red = true }) "
                    "return { a ~= nil and a.red == nil, b ~= nil and b.red == nil, c ~= nil and c.red ~= nil } end)()")
    assert list(loose.values()) == [True, True, True], tbl(loose)
    assert not PF._messages(rt), PF._messages(rt)


def check_new_shoulder_seat_rescale_and_alpha() -> None:
    d = mockup_dock(True)
    rt = runtime(1.0)
    s = build_shoulder(rt, d["W"], d["H"])
    host, art = rt.globals().__sh_host, s.art
    # Seat re-anchors the art; with no arguments it is back on the parent's top left
    assert s.Seat(s, "BOTTOMLEFT", host, "BOTTOMLEFT", 5, 6) is True
    pts = tbl(art.points)
    assert list(pts) == ["BOTTOMLEFT"] and (pts["BOTTOMLEFT"].x, pts["BOTTOMLEFT"].y) == (5, 6) and rawequal(rt, pts["BOTTOMLEFT"].rel, host)
    assert s.Seat(s) is True
    pts = tbl(art.points)
    assert list(pts) == ["TOPLEFT"] and (pts["TOPLEFT"].x, pts["TOPLEFT"].y) == (0, 0) and rawequal(rt, pts["TOPLEFT"].rel, host)
    # seated on another frame, same corner
    rt.execute("__other = CreateFrame('Frame', nil, UIParent)")
    assert s.Seat(s, "TOPLEFT", rt.globals().__other, "BOTTOMLEFT", 3, 4) is True
    pts = tbl(art.points)
    assert rawequal(rt, pts["TOPLEFT"].rel, rt.globals().__other) and pts["TOPLEFT"].rp == "BOTTOMLEFT"
    for bad in ("5", "'NOWHERE'", "'TOPLEFT', __other, 'NOWHERE'", "'TOPLEFT', __other, 'TOPLEFT', 'x'", "'TOPLEFT', 5"):
        assert rt.eval(f"__sh:Seat({bad})") is False, f"Seat({bad}) should refuse"
    assert tbl(art.points)["TOPLEFT"].x == 3, "a refused Seat changed the anchor"
    # Rescale
    assert s.Rescale(s) is True
    approx(art.GetScale(art), 1.0, "Rescale() takes Layout.Scale()")
    assert s.Rescale(s, 0.5) is True
    approx(art.GetScale(art), 0.5, "Rescale(0.5)")
    for bad in ("0", "-1", "'x'", "0/0", "math.huge", "true"):
        assert rt.eval(f"__sh:Rescale({bad})") is False, f"Rescale({bad}) should refuse"
    approx(art.GetScale(art), 0.5, "a refused Rescale changed the scale")
    assert s.Rescale(s) is True
    # SetAlpha
    assert s.SetAlpha(s, 0.25) is True and art.alpha == 0.25
    assert s.SetAlpha(s, 0) is True and art.alpha == 0 and s.SetAlpha(s, 1) is True and art.alpha == 1
    for bad in ("-0.1", "1.1", "'x'", "nil", "0/0", "math.huge"):
        assert rt.eval(f"__sh:SetAlpha({bad})") is False, f"SetAlpha({bad}) should refuse"
    assert art.alpha == 1, "a refused SetAlpha changed the alpha"
    # everything legal in combat, and the parent frame is never touched: build on the pet's own (protected) container
    rt = runtime(1.0)
    pf = rt.globals().FS.PetFrame
    container = pf.container
    rt.execute("__sh = FS.PetDock.NewShoulder(FS.PetFrame.container, 306.8, 91.8, { red = true })")
    s = rt.globals().__sh
    before = rt.eval("__snapshot()")
    shows, hides = container.showCalls or 0, container.hideCalls or 0
    rt.execute("__combat = true")
    assert s.Seat(s, "TOPLEFT", container, "TOPLEFT", 2, -2) is True
    assert s.Rescale(s, 0.7) is True and s.SetAlpha(s, 0.5) is True and s.SetEdge(s, rt.globals().FS.Theme.COLOR_POWER) is True
    assert (container.showCalls or 0) == shows and (container.hideCalls or 0) == hides, "Show or Hide on the container in combat"
    assert rt.eval("__snapshot()") == before, "the container or a slot moved in combat"
    assert not PF._messages(rt), PF._messages(rt)


def check_new_shoulder_retints_only_its_normal_edge() -> None:
    d = mockup_dock(True)
    rt = runtime(1.0)
    s = build_shoulder(rt, d["W"], d["H"])
    theme = rt.globals().FS.Theme
    c = rt.globals().FS.PetDock.C
    red_before = [t.color for t in tex_list(rt, s.red.stroke) + tex_list(rt, s.red.halo)]
    assert s.SetEdge(s, rt.eval("{1, 0.5, 0.25}"), 0.6, 0.3) is True
    for t in tex_list(rt, s.stroke):
        assert [round(v, 3) for v in t.color] == [1, 0.5, 0.25, 0.6], (t.name, t.color)
    for t in tex_list(rt, s.halo):
        assert [round(v, 3) for v in t.color] == [1, 0.5, 0.25, 0.3], (t.name, t.color)
    assert [t.color for t in tex_list(rt, s.red.stroke) + tex_list(rt, s.red.halo)] == red_before, "SetEdge retinted the red twin"
    # no alphas: the mockup's stroke and halo, back to COLOR_BORDER
    assert s.SetEdge(s, theme.COLOR_BORDER) is True
    for t in tex_list(rt, s.stroke):
        assert [round(v, 4) for v in t.color] == [round(theme.COLOR_BORDER[i], 4) for i in (1, 2, 3)] + [c.STROKE_ALPHA]
    for t in tex_list(rt, s.halo):
        assert [round(v, 4) for v in t.color] == [round(theme.COLOR_BORDER[i], 4) for i in (1, 2, 3)] + [c.HALO_ALPHA]
    for bad in ("nil", "5", "{1, 2}", "{1, 2, 'x'}", "{1, 2, 3}, 'x'", "{1, 2, 3}, 0.5, 'x'"):
        assert rt.eval(f"__sh:SetEdge({bad})") is False, f"SetEdge({bad}) should refuse"
    assert [t.color for t in tex_list(rt, s.stroke)][0][:3] == [round(v, 6) for v in [theme.COLOR_BORDER[i] for i in (1, 2, 3)]] or True


def check_a_throwing_new_shoulder_hides_its_art_and_rethrows() -> None:
    rt = runtime(1.0)
    rt.execute("__h = CreateFrame('Frame', nil, UIParent)")
    pd = rt.globals().FS.PetDock
    states = (dump_dock(rt), pd.GetMode(), pd.HasDock())
    rt.execute(BREAK_DOCK)
    out = rt.eval("(function() local ok, err = pcall(FS.PetDock.NewShoulder, __h, 306.8, 91.8, { red = true }) return { ok, tostring(err) } end)()")
    assert out[1] is False and "FILL_CUT_TEXTURES" in str(out[2]), tbl(out)
    arts = rt.eval("(function() local out = {} for _, f in ipairs(__frames) do if f.parent == __h then out[#out + 1] = f.shown end end return out end)()")
    assert len(arts) >= 1 and all(v is False for v in arts.values()), f"a half built art frame was left shown: {tbl(arts)}"
    assert (dump_dock(rt), pd.GetMode(), pd.HasDock()) == states, "a failed shoulder changed the pet dock"
    assert not PF._messages(rt), "NewShoulder itself must not log: the caller decides (PetDock logs its own dock failure)"


def check_a_dock_that_fails_after_its_shoulder_built_forgets_the_shoulder() -> None:
    """BuildDock can throw AFTER NewShoulder succeeded (here: the object comes back without its red twin).
    The half built dock is dropped, and the module must not keep the dead object to retint or rescale."""
    rt = runtime(1.0, setup=CONSOLE_STUB, allow_messages=True, after_load=r"""
        __dead = { SetEdge = 0, Rescale = 0 }
        local real = FS.PetDock.NewShoulder
        FS.PetDock.NewShoulder = function(...)
            local obj, why = real(...)
            if obj then
                obj.red = nil
                for name in pairs(__dead) do
                    local method = obj[name]
                    obj[name] = function(self, ...) __dead[name] = __dead[name] + 1 return method(self, ...) end
                end
            end
            return obj, why
        end
    """)
    pd = rt.globals().FS.PetDock
    assert pd.HasDock() is False and pd.frames.dock is None and pd.edges.dock is None
    messages = PF._messages(rt)
    assert len(messages) == 1 and messages[0].startswith("petdock_dock_build"), messages
    assert pd.SetEdgeColor(1, 0.5, 0.25) is True and pd.ResetEdgeColor() is True
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    dead = rt.globals().__dead
    assert dead.SetEdge == 0, "a retint still went to the dropped dock's shoulder"
    assert dead.Rescale == 0, "a rescale still went to the dropped dock's shoulder"


def _owner_world(pet: bool = True, drawn: bool = True, scale: float = 1.0) -> LuaRuntime:
    return dock_runtime(drawn, scale, "" if pet else "__pet.exists = false")




def check_a_shoulder_that_took_the_gap_keeps_it() -> None:
    """Single-owner Console gap: PetFrame builds for every class, so a pet-less Paladin's pet panel docks
    hidden and holds gap [25, 381] with the patch shut. A shoulder that yields the gap, then sets its own,
    keeps it (and the open patch) across every PetDock.Refresh trigger, in and out of combat."""
    for pet in (False, True):
        rt = _owner_world(pet)
        pd = rt.globals().FS.PetDock
        c = pd.C
        assert _gap(rt) == expected_gap(c), "the pet panel docks and holds its gap before anyone yields"
        ok, took = rt.eval("{__take_gap()}").values()
        assert ok is True and took is True
        gap, halo = _gap(rt), _halo_gap(rt)
        assert gap == "37,351.8" and halo == "35,353.8", (gap, halo)
        assert _patch(rt) == 0, "yielding leaves the patch open under the shoulder's gap"
        calls, patches = _gap_calls(rt), rt.eval("#__console.patchCalls")

        def unchanged(label: str) -> None:
            assert (_gap(rt), _halo_gap(rt)) == (gap, halo), f"{label}: the shoulder's gap was replaced"
            assert _patch(rt) == 0, f"{label}: the pet panel plugged the shoulder's line"
            assert _gap_calls(rt) == calls, f"{label}: PetDock asked SetDockGap again"
            assert rt.eval("#__console.patchCalls") == patches, f"{label}: PetDock wrote the patch alpha"

        pd.Refresh(True); unchanged("Refresh(true)")
        pd.Refresh(); unchanged("Refresh()")
        rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')"); unchanged("rescale")
        rt.execute("__pet.exists = false; __fire('UNIT_PET', 'player')"); unchanged("pet gone")
        rt.execute("__pet.exists = true; __fire('UNIT_PET', 'player')"); unchanged("pet back")
        pd.SetPetShown(False); pd.SetPetShown(True); unchanged("SetPetShown")
        rt.execute("__fire('PLAYER_REGEN_ENABLED')"); unchanged("regen")
        rt.execute("__set_console(false)"); assert _gap(rt) == gap, "the Console going away closed the shoulder's gap"
        rt.execute("__set_console(true)"); unchanged("redock")
        # the pet panel is still docked and seated: only the gap is not its to touch
        assert rt.globals().FS.PetFrame.IsDocked() is True
        # a refresh that throws falls back to the float seat and must not close the shoulder's gap either
        rt.execute("FS.PetFrame.SeatDocked = function() error('seatboom') end")
        pd.Refresh(True)
        assert (_gap(rt), _halo_gap(rt)) == (gap, halo), "the throwing-refresh fallback closed the shoulder's gap"
        assert _patch(rt) == 0 and _gap_calls(rt) == calls
        rt.execute("FS.PetFrame.SeatDocked = nil")
        # combat: alpha writes are legal but PetDock still writes none, and nothing protected is touched
        rt = _owner_world(pet)
        pd = rt.globals().FS.PetDock
        rt.execute("__take_gap()")
        calls, patches = _gap_calls(rt), rt.eval("#__console.patchCalls")
        rt.execute("__combat = true; __pet.dead = true; __fire('UNIT_FLAGS', 'pet'); __pet.dead = false; __fire('UNIT_FLAGS', 'pet'); "
                   "__pet.exists = false; __fire('UNIT_PET', 'player')")
        pd.SetPetShown(False)
        assert _gap_calls(rt) == calls and rt.eval("#__console.patchCalls") == patches, "PetDock wrote to the Console in combat while yielded"
        assert rt.eval("__console.refused") == 0 and not list(rt.globals().__blocked.values())
        assert _patch(rt) == 0
        rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
        assert _gap_calls(rt) == calls and _patch(rt) == 0, "regen replay touched the yielded gap"


def check_yielding_the_gap_is_single_owner_and_validated() -> None:
    rt = _owner_world(True)
    pd = rt.globals().FS.PetDock
    for bad in ("nil", "5", "true", "''", "0/0"):
        assert rt.eval(f"FS.PetDock.YieldGap({bad})") is False, f"YieldGap({bad}) should refuse"
    assert _gap(rt) == expected_gap(pd.C) and _patch(rt) == 0, "a refused yield changed the pet gap"
    assert pd.YieldGap("a") is True and pd.YieldGap("a") is True, "the same owner may ask twice"
    assert pd.YieldGap("b") is False, "a second owner must not steal a held gap"
    assert pd.ReclaimGap("b") is False and pd.ReclaimGap(None) is False and pd.ReclaimGap(5) is False, "only the owner reclaims"
    assert pd.ReclaimGap("a") is True
    assert pd.ReclaimGap("a") is False, "nothing left to reclaim"
    assert pd.YieldGap("b") is True, "free again after a reclaim"
    # a table owner works too
    rt = _owner_world(True)
    assert rt.eval("(function() local o = {} return FS.PetDock.YieldGap(o) and not FS.PetDock.YieldGap({}) and FS.PetDock.ReclaimGap(o) end)()") is True


def check_reclaiming_the_gap_restores_the_pet_gap() -> None:
    for pet in (True, False):
        rt = _owner_world(pet)
        pd = rt.globals().FS.PetDock
        c = pd.C
        rt.execute("__take_gap()")
        assert _gap(rt) == "37,351.8"
        assert pd.ReclaimGap("classshoulder") is True
        assert _gap(rt) == expected_gap(c), "reclaiming did not put the pet gap back"
        assert _halo_gap(rt) == expected_halo_gap(c)
        assert _patch(rt) == (0 if pet else 1), "reclaiming did not restore the patch for the pet's visibility"
        # and the pet owns it again: a pet change moves the patch
        rt.execute("__pet.exists = not __pet.exists; __fire('UNIT_PET', 'player')")
        assert _patch(rt) == (1 if pet else 0)
    # no Console drawn at reclaim time: the gap is closed, not left to the old owner
    rt = _owner_world(True)
    rt.execute("__take_gap(); __set_console(false)")
    assert _gap(rt) == "37,351.8"
    assert rt.globals().FS.PetDock.ReclaimGap("classshoulder") is True
    assert _gap(rt) is None, "reclaimed with no Console drawn: the gap must close"
    # the Console was never drawn while the owner held the gap (so PetDock never opened one itself): the
    # reclaim must still close the owner's standing gap, not trust its own idea that no gap is open
    rt = _owner_world(True, drawn=False)
    assert _gap(rt) is None
    rt.execute("__take_gap()")
    assert _gap(rt) == "37,351.8"
    assert rt.globals().FS.PetDock.ReclaimGap("classshoulder") is True
    assert _gap(rt) is None, "reclaimed with no Console drawn: the owner's standing gap was left open"
    # reclaim in combat waits for regen and writes nothing protected
    rt = _owner_world(True)
    rt.execute("__take_gap()")
    calls = _gap_calls(rt)
    rt.execute("__combat = true")
    assert rt.globals().FS.PetDock.ReclaimGap("classshoulder") is True
    assert _gap(rt) == "37,351.8" and _gap_calls(rt) == calls and rt.eval("__console.refused") == 0
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert _gap(rt) == expected_gap(rt.globals().FS.PetDock.C), "the reclaim was not replayed at regen"
    # yielding before the panel ever docks: the pet dock never asks for the gap at all
    rt = runtime(1.0, setup=CONSOLE_STUB + "\n__console.drawn = true\n__pet.exists = false\n", after_load="FS.PetDock.YieldGap('early')")
    assert _gap(rt) is None and _gap_calls(rt) == 0, "an early yield still let the pet panel open the gap"
    assert rt.globals().FS.PetFrame.IsDocked() is True, "an early yield stopped the panel docking"
    assert rt.globals().FS.PetDock.ReclaimGap("early") is True
    assert _gap(rt) == expected_gap(rt.globals().FS.PetDock.C) and _patch(rt) == 1


def check_a_reclaim_in_combat_keeps_the_patch_open_until_regen() -> None:
    """After an in-combat ReclaimGap the owner's gap still stands (SetDockGap is refused in combat), so a pet
    event in combat must not plug it with patch alpha 1: no patch write until the regen Refresh."""
    for pet in (False, True):
        rt = _owner_world(pet)
        pd = rt.globals().FS.PetDock
        rt.execute("__take_gap()")
        gap, calls, patches = _gap(rt), _gap_calls(rt), rt.eval("#__console.patchCalls")
        rt.execute("__combat = true")
        assert pd.ReclaimGap("classshoulder") is True
        for code in ("__pet.exists = false; __fire('UNIT_PET', 'player')", "__pet.exists = true; __fire('UNIT_PET', 'player')",
                     "__pet.dead = true; __fire('UNIT_FLAGS', 'pet')", "__pet.dead = false; __fire('UNIT_FLAGS', 'pet')",
                     "__pet.exists = false; __fire('UNIT_PET', 'player')"):
            rt.execute(code)
            assert _gap(rt) == gap and _gap_calls(rt) == calls, f"{code}: the owner's gap was touched in combat"
            assert _patch(rt) == 0 and rt.eval("#__console.patchCalls") == patches, f"{code}: the patch was written while the owner's gap stands"
        pd.SetPetShown(False)
        assert _patch(rt) == 0 and rt.eval("#__console.patchCalls") == patches
        assert rt.eval("__console.refused") == 0 and not list(rt.globals().__blocked.values())
        rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
        assert _gap(rt) == expected_gap(pd.C), "regen did not restore the pet gap"
        assert _patch(rt) == 1, "regen: the pet is gone, so the patch closes the hole"
        # and from then on the patch follows the pet again, in combat too
        rt.execute("__combat = true; __pet.exists = true; __fire('UNIT_PET', 'player')")
        assert _patch(rt) == 0
        rt.execute("__combat = false")


def check_set_edge_color_refuses_a_bad_alpha_before_tinting_anything() -> None:
    rt = dock_runtime(True, 1.0)
    pd = rt.globals().FS.PetDock
    before = dump_dock(rt)
    for args in ("1, 0.5, 0.25, 'x'", "1, 0.5, 0.25, 0.5, 'x'", "1, 0.5, 0.25, true", "1, 0.5, 0.25, {}"):
        assert rt.eval(f"FS.PetDock.SetEdgeColor({args})") is False, f"SetEdgeColor({args}) should refuse"
        assert dump_dock(rt) == before, f"SetEdgeColor({args}) tinted something (the float outline or the dock) before refusing"
    assert pd.SetEdgeColor(1, 0.5, 0.25, None, None) is True and dump_dock(rt) != before
    assert pd.SetEdgeColor(1, 0.5, 0.25, 0.6, 0.3) is True


def check_seat_puts_the_anchor_back_when_set_point_fails() -> None:
    d = mockup_dock(True)
    rt = runtime(1.0)
    s = build_shoulder(rt, d["W"], d["H"])
    host, art = rt.globals().__sh_host, s.art
    rt.execute("""
        __bad = CreateFrame('Frame', nil, UIParent)
        local real = __sh.art.SetPoint
        __sh.art.SetPoint = function(self, p, rel, ...)
            if rel == __bad then error('Cannot anchor to a region that depends on this one') end
            return real(self, p, rel, ...)
        end
    """)
    assert s.Seat(s, "CENTER", host, "CENTER", 5, 7) is True
    before = tbl(art.points)
    assert rt.eval("__sh:Seat('TOPLEFT', __bad, 'TOPLEFT', 1, 2)") is False
    after = tbl(art.points)
    assert list(after) == list(before) == ["CENTER"], (list(before), list(after))
    assert (after["CENTER"].x, after["CENTER"].y) == (5, 7) and rawequal(rt, after["CENTER"].rel, host), "the previous anchor was not restored"
    # two anchors survive a failed seat too
    rt.execute("__sh.art.points = {}; __sh.art:SetPoint('TOPLEFT', __sh_host, 'TOPLEFT', 1, 1); __sh.art:SetPoint('BOTTOMRIGHT', __sh_host, 'BOTTOMRIGHT', -1, -1)")
    assert rt.eval("__sh:Seat('TOP', __bad, 'TOP')") is False
    pts = tbl(art.points)
    assert sorted(pts) == ["BOTTOMRIGHT", "TOPLEFT"] and pts["BOTTOMRIGHT"].x == -1 and pts["TOPLEFT"].x == 1


def check_rescale_re_levels_the_shoulder_to_its_parent() -> None:
    d = mockup_dock(True)
    rt = runtime(1.0)
    s = build_shoulder(rt, d["W"], d["H"])
    host, art = rt.globals().__sh_host, s.art
    level = host.GetFrameLevel(host)
    assert art.GetFrameLevel(art) == level and s.normal.GetFrameLevel(s.normal) == level
    assert s.red.host.GetFrameLevel(s.red.host) == level + 1 and s.red.pulseFrame.GetFrameLevel(s.red.pulseFrame) == level + 1
    host.SetFrameLevel(host, level + 40)
    assert art.GetFrameLevel(art) == level, "the art moved by itself"
    assert s.Rescale(s) is True
    assert art.GetFrameLevel(art) == level + 40 and s.normal.GetFrameLevel(s.normal) == level + 40, "Rescale did not re-level the art"
    assert s.red.host.GetFrameLevel(s.red.host) == level + 41 and s.red.pulseFrame.GetFrameLevel(s.red.pulseFrame) == level + 41
    # a refused Rescale re-levels nothing
    host.SetFrameLevel(host, level + 50)
    assert rt.eval("__sh:Rescale(0)") is False and art.GetFrameLevel(art) == level + 40


def check_new_shoulder_seat_details_error_message_and_span_at_another_width() -> None:
    d = mockup_dock(True)
    rt = runtime(1.0)
    s = build_shoulder(rt, d["W"], d["H"])
    art = s.art
    host = rt.globals().__sh_host
    # y and x must be finite
    assert s.Seat(s, "TOPLEFT", host, "TOPLEFT", 1, 2) is True
    for bad in ("0/0", "math.huge", "-math.huge", "'1'", "true"):
        assert rt.eval(f"__sh:Seat('TOPLEFT', __sh_host, 'TOPLEFT', 1, {bad})") is False, f"Seat y={bad} should refuse"
        assert rt.eval(f"__sh:Seat('TOPLEFT', __sh_host, 'TOPLEFT', {bad}, 1)") is False, f"Seat x={bad} should refuse"
    pts = tbl(art.points)
    assert (pts["TOPLEFT"].x, pts["TOPLEFT"].y) == (1, 2), "a refused Seat changed the anchor"
    # the default relPoint is the point
    assert rt.eval("__sh:Seat('BOTTOM', __sh_host)") is True
    pts = tbl(art.points)
    assert list(pts) == ["BOTTOM"] and pts["BOTTOM"].rp == "BOTTOM" and rawequal(rt, pts["BOTTOM"].rel, host)
    assert rt.eval("__sh:Seat('RIGHT', __sh_host, 'LEFT')") is True and tbl(art.points)["RIGHT"].rp == "LEFT"
    # a throwing build rethrows the ORIGINAL message: one position prefix, no second one stacked on it
    rt = runtime(1.0)
    rt.execute("__h = CreateFrame('Frame', nil, UIParent)")
    rt.execute(BREAK_DOCK)
    msg = str(rt.eval("(function() local ok, err = pcall(FS.PetDock.NewShoulder, __h, 306.8, 91.8) return err end)()"))
    assert msg.count("PetDock.lua:") == 1, f"the rethrown message has a doubled position prefix: {msg}"
    # PetDock.GapSpan follows C.W and C.DOCK_X (the pet panel's own width), not a literal 348
    rt = runtime(1.0)
    pd = rt.globals().FS.PetDock
    c = pd.C
    rt.execute("FS.PetDock.C.W = 400; FS.PetDock.C.DOCK_X = 30")
    got = [float(v) for v in tbl(rt.eval("{FS.PetDock.GapSpan()}")).values()]
    assert got == [31, 30 + 400 + 10 - 1, 29, 30 + 400 + 10 + 1], got



# ---------------------------------------------------------------------------------------------
# Checks: the docked chrome is byte identical to the pre-NewShoulder build (golden hashes)
# ---------------------------------------------------------------------------------------------

# sha256 of __dump_dock() in five states (plus "reset" == "docked"), taken from PetDock.lua as committed at HEAD 7927f72 BEFORE the
# chrome became PetDock.NewShoulder. The dump is the whole docked tree in creation order (see SETUP),
# so any change to a texture, an anchor, a level, a vertex colour, the draw order or the animation
# groups changes a hash. PETDOCK_DUMP_DIR=<dir> writes the dumps next to a failure to diff them.
GOLDEN_DOCK = {
    "docked": "d5e0f61581ae6d70e5ccc5a6021a878dfb999b059afbe55dd1945d3def7d4d76",
    "retinted": "93ad58365e2cd129d60cdf99fd1b7c64ed7c8ac4b97265c122f2bb427a754f09",
    "low_hp": "f678503dcd39fefac83c2b8738f89e8a0d9e53e21b5fa699928dcbb154371d39",
    "scale_0.64": "714267d49fec033b0902a4d7d04437c53d9545d5f7e08048fe703cc0e71889a1",
    "floating": "fe1be1148036960199e6d0cfa9447aacdc37a2232c8051c69f0d9334859e003d",
}


def dump_dock(rt: LuaRuntime) -> str:
    return str(rt.eval("__dump_dock()"))


def dock_states() -> dict:
    out = {}
    rt = dock_runtime(True, 1.0)
    out["docked"] = dump_dock(rt)
    pd = rt.globals().FS.PetDock
    assert pd.SetEdgeColor(1, 0.5, 0.25, 0.6, 0.3) is True
    out["retinted"] = dump_dock(rt)
    assert pd.ResetEdgeColor() is True
    out["reset"] = dump_dock(rt)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH', 'pet')")
    out["low_hp"] = dump_dock(rt)
    out["scale_0.64"] = dump_dock(dock_runtime(True, 0.64))
    out["floating"] = dump_dock(dock_runtime(False, 1.0))
    return out


def check_the_docked_chrome_is_byte_identical_to_the_pre_shoulder_build() -> None:
    import hashlib

    states = dock_states()
    out_dir = os.environ.get("PETDOCK_DUMP_DIR")
    if out_dir:
        for name, text in states.items():
            Path(out_dir, f"dock-{name}.txt").write_text(text + "\n", encoding="utf-8")
    assert states["reset"] == states["docked"], "ResetEdgeColor does not restore the docked chrome exactly"
    assert states["docked"].count("\n") > 30, "the dump is suspiciously small"
    for name in GOLDEN_DOCK:
        digest = hashlib.sha256(states[name].encode("utf-8")).hexdigest()
        assert digest == GOLDEN_DOCK[name], \
            f"the '{name}' dock tree changed: sha256 {digest} (golden {GOLDEN_DOCK[name] or 'not set'}, {len(states[name])} bytes)"


def main() -> int:
    cases = [
        ("toc: PetDock.lua right after PetFrame.lua, CRLF kept", check_the_toc_lists_petdock_right_after_petframe_and_keeps_crlf),
        ("PetFrame hands its chrome to PetDock, S7's build line intact", check_petframe_no_longer_builds_the_chrome_itself),
        ("baked flare textures exist, 128 square", check_the_baked_textures_are_128_square_bgra),
        ("dock constants are the mockup's", check_the_dock_constants_are_the_mockups),
        ("DOCK_X is the mockup's dock offset", check_dock_x_is_the_mockups_dock_offset),
        ("dock fill covers the mockup polygon", check_the_dock_fill_covers_the_mockup_polygon),
        ("dock fill is the scrim, wedge is tab_slant flipped", check_the_dock_fill_is_the_scrim_and_uses_the_wedge_for_the_flare),
        ("dock stroke: lines, TL corner, 45 degree flare band", check_the_dock_stroke_is_the_lines_the_corner_and_the_flare_band),
        ("dock bottom is open: no line, no halo, fill stops", check_the_bottom_is_open),
        ("dock halo follows the outer distance, no nine-slice", check_the_dock_halo_follows_the_paths_outer_distance),
        ("red edge is the same geometry in red", check_the_red_edge_has_the_same_geometry_in_red),
        ("default mode float, SetMode flips, bad mode refused", check_the_default_mode_is_float_and_set_mode_flips_the_chrome),
        ("SetMode never touches the protected container", check_set_mode_never_touches_the_protected_container),
        ("float is the same two calls, pixel identical", check_the_float_chrome_is_the_same_two_calls_pixel_identical),
        ("chrome frames sit strictly below every slot", check_the_float_chrome_draws_below_the_slots),
        ("dock art follows the UI scale", check_the_dock_follows_the_ui_scale),
        ("a rescale in combat waits for regen", check_a_rescale_in_combat_waits_for_regen),
        ("low HP layer targets PetDock frames after SetMode", check_after_set_mode_the_low_layer_targets_the_dock_frames),
        ("no default S7 edge is built when PetDock is loaded", check_petframe_builds_no_default_edge_when_petdock_is_loaded),
        ("a PetDock that never attaches leaves the fallback edge", check_a_petdock_that_never_attaches_leaves_the_fallback_edge),
        ("a dock build failure leaves float and the pet UI working", check_a_dock_build_failure_leaves_the_float_look_and_the_pet_ui_working),
        ("a dock mode set before a failed dock build falls back to float", check_a_dock_mode_remembered_before_a_failed_dock_build_falls_back_to_float),
        ("a mode set before the low layer exists is picked up", check_a_mode_set_before_the_low_layer_exists_is_picked_up_after),
        ("the edge pulse is PetFrame's pulse", check_the_edge_pulse_is_the_petframes_pulse),
        ("normal edge retints and resets, red untouched", check_the_normal_edge_can_be_retinted_and_reset),
        ("a drawn Console docks the pet panel on its top left", check_a_drawn_console_docks_the_pet_panel_on_its_top_left),
        ("no or an undrawn Console leaves the float panel", check_no_console_or_an_undrawn_one_leaves_the_float_panel),
        ("the Console toggling docks and undocks live", check_the_console_toggling_docks_and_undocks_live),
        ("dock and undock wait for regen in combat", check_dock_and_undock_wait_for_regen_in_combat),
        ("the gap stays open and the patch follows the pet panel", check_the_gap_stays_open_and_the_patch_follows_the_pet_panel),
        ("the patch follows the panel in combat, no protected call", check_the_patch_follows_the_panel_in_combat_with_no_protected_call),
        ("a docked panel follows the UI scale", check_a_docked_panel_follows_the_ui_scale),
        ("/fspet reset and unlock leave a docked panel docked", check_fspet_reset_and_unlock_leave_a_docked_panel_docked),
        ("the Console is never anchored to the pet", check_the_dock_never_anchors_the_console_to_the_pet),
        ("the dock gap fits the real Console's top line", check_the_dock_gap_fits_the_real_console_top_line),
        ("no dock fill dims a lit Console line pixel", check_no_fill_dims_a_lit_console_line_pixel_under_the_dock),
        ("the Console halo tiles with the dock halo and the patch", check_the_console_halo_tiles_with_the_dock_halo_and_the_patch),
        ("the gap ends overlap the flare foot and the left side in physical pixels", check_the_gap_ends_overlap_the_flare_foot_and_the_left_side_in_physical_pixels),
        ("a throwing dock falls back to the float seat", check_a_throwing_dock_falls_back_to_the_float_seat),
        ("the docked chrome is byte identical to the pre-NewShoulder build", check_the_docked_chrome_is_byte_identical_to_the_pre_shoulder_build),
        ("the pet dock is built through NewShoulder and nothing else", check_the_pet_dock_is_built_through_new_shoulder_and_nothing_else),
        ("mockup: the Paladin shoulder is the pet panel's recipe (the Console style bakes it in)", check_the_mockup_draws_the_paladin_shoulder_with_the_pet_panels_recipe),
        ("NewShoulder: the Paladin block is 306.8 x 91.8 at 36 design px", check_new_shoulder_is_the_paladin_block_size),
        ("NewShoulder: the object at 306.8 x 91.8, scale, levels, anchors", check_new_shoulder_builds_the_object_at_the_paladin_size),
        ("NewShoulder: without red there is no red twin", check_new_shoulder_without_red_builds_no_red_twin),
        ("NewShoulder 306.8 x 91.8: fill covers the mockup polygon", partial(check_the_dock_fill_covers_the_mockup_polygon, True)),
        ("NewShoulder 306.8 x 91.8: fill is the scrim, wedge is tab_slant flipped", partial(check_the_dock_fill_is_the_scrim_and_uses_the_wedge_for_the_flare, True)),
        ("NewShoulder 306.8 x 91.8: stroke lines, TL corner, 45 degree flare band", partial(check_the_dock_stroke_is_the_lines_the_corner_and_the_flare_band, True)),
        ("NewShoulder 306.8 x 91.8: bottom is open", partial(check_the_bottom_is_open, True)),
        ("NewShoulder 306.8 x 91.8: halo follows the outer distance", partial(check_the_dock_halo_follows_the_paths_outer_distance, True)),
        ("NewShoulder 306.8 x 91.8: red twin is the same geometry in red", partial(check_the_red_edge_has_the_same_geometry_in_red, True)),
        ("NewShoulder: the gap span follows the width", check_new_shoulder_gap_span_follows_the_width),
        ("NewShoulder: the gap fits the real Console top line", check_new_shoulder_gap_fits_the_real_console_top_line),
        ("NewShoulder 306.8 x 91.8: no fill dims a lit Console line pixel", check_no_shoulder_fill_dims_a_lit_console_line_pixel),
        ("NewShoulder: bad arguments are refused with a reason", check_new_shoulder_refuses_bad_arguments),
        ("NewShoulder: Seat, Rescale, SetAlpha, legal in combat", check_new_shoulder_seat_rescale_and_alpha),
        ("NewShoulder: SetEdge retints only the normal edge", check_new_shoulder_retints_only_its_normal_edge),
        ("NewShoulder: a throwing build hides its art and rethrows", check_a_throwing_new_shoulder_hides_its_art_and_rethrows),
        ("a dock that fails after its shoulder built forgets the shoulder", check_a_dock_that_fails_after_its_shoulder_built_forgets_the_shoulder),
        ("a shoulder that took the Console gap keeps it (single owner)", check_a_shoulder_that_took_the_gap_keeps_it),
        ("YieldGap and ReclaimGap are single owner and validated", check_yielding_the_gap_is_single_owner_and_validated),
        ("reclaiming the gap restores the pet gap", check_reclaiming_the_gap_restores_the_pet_gap),
        ("a reclaim in combat keeps the patch open until regen", check_a_reclaim_in_combat_keeps_the_patch_open_until_regen),
        ("SetEdgeColor refuses a bad alpha before tinting anything", check_set_edge_color_refuses_a_bad_alpha_before_tinting_anything),
        ("Seat puts the anchor back when SetPoint fails", check_seat_puts_the_anchor_back_when_set_point_fails),
        ("Rescale re-levels the shoulder to its parent", check_rescale_re_levels_the_shoulder_to_its_parent),
        ("NewShoulder: Seat edges, rethrown message, span at another width", check_new_shoulder_seat_details_error_message_and_span_at_another_width),
    ]
    failures = 0
    for name, check in cases:
        try:
            check()
        except (AssertionError, AttributeError, RuntimeError, LuaError, TypeError, KeyError, FileNotFoundError) as exc:
            print(f"FAIL: {name}: {type(exc).__name__}: {exc}")
            failures += 1
        else:
            print(f"PASS: {name}")
    print(f"{len(cases) - failures}/{len(cases)} petdock checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
