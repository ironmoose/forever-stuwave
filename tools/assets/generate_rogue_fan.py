#!/usr/bin/env python3
"""Bake the Rogue Gunsight module's art: the fan of five throwing daggers, the Slice and Dice blade star, the FINISH plaque and the
small gems, from the design mockup "Rogue dagger fan" (2026-11-16).

Every sprite px is baked as SCALE x SCALE texels of one flat colour (the Paladin and Hunter pipeline). The fan is five daggers
fanned from one pivot (the cuff), drawn by rasterising each dagger's own geometry at its angle (no anti-aliasing, a one px dark
outline), and composited back to front the way a hand of cards is held. Each dagger is baked in a DEAD look (all five composited into
one file) and in a LIT look (one file per dagger, holding only the px of that dagger the later daggers do not cover, so a lit dagger
drops exactly onto the dead fan). A StatusBar over a lit file is filled by the ENGINE when the combo count reaches that dagger, so
no addon code ever compares the count (it is a secret value in combat).

    rogue_dead.tga      256 x 128   the fan, dead look, plus the cuff on top (FAN_W x FAN_H = 128 x 64 sprite px)
    rogue_lit_1..5.tga  256 x 128   one dagger each, lit look, the same box
    rogue_ready.tga     256 x 128   the gold overlay of the whole fan (outline, rim, glow), shown by an engine gate at 5 points
    rogue_flash.tga     256 x 128   the whole fan as a white silhouette (the spend flash)
    rogue_finish.tga    128 x 32    the word FINISH (white mask, tinted), FINISH_W x FINISH_H = 64 x 16 sprite px
    rogue_gem.tga       16 x 16     the lit cost gem (white mask, tinted), 8 x 8 sprite px
    rogue_atlas.tga     256 x 128   cells of 24 x 24 sprite px, 5 across: the blade star in four turns and dead, the gem (dim),
                                    the energy cap spark; ATLAS_CELLS gives the order. Rects are in the generated RogueArt.lua.
    RogueArt.lua        the manifest FS.RogueArt (never hand edit it, regenerate)

    python3 tools/assets/generate_rogue_fan.py           (FS_ASSET_OUTPUT_DIR overrides the .tga directory; FS_ROGUE_LUA the manifest;
                                                          FS_ROGUE_PREVIEW writes one px per sprite px PNGs of every file for the mockup)
"""

from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

SCALE = 2
FAN_W, FAN_H = 128, 64               # the fan box, sprite px (a StatusBar box equals its file)
PIVOT = (40, 56)                     # the cuff centre in the box
ANGLES = (-48, -24, 0, 24, 48)       # degrees from straight up, left to right
FINISH_W, FINISH_H = 64, 16
GEM = 8
CELL = 24                            # atlas cell, sprite px
ATLAS_COLS = 5
ATLAS_CELLS = ["star0", "star1", "star2", "star3", "starDead", "gemDim", "spark", "ring", "cuffBig", "pad"]
STAR_R = 10                          # the blade star's radius


def col(h: str, a: float = 1.0):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)


def mix(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(3)) + (1.0,)


OUTLINE = col("#120822")
DEAD = {"hi": col("#6a5aa0"), "lt": col("#4a3b73"), "dk": col("#2f2350"), "fuller": col("#241a3f"),
        "gold": col("#6b5a25"), "goldDk": col("#3d3014"), "grip": col("#2b1f48"), "gripB": col("#221838"), "gem": col("#4a1d48")}
LIT = {"hi": col("#ffffff"), "lt": col("#dfe9ff"), "dk": col("#9fb2e6"), "fuller": col("#6f83bd"),
       "gold": col("#ffd23f"), "goldDk": col("#b9811a"), "grip": col("#a855f7"), "gripB": col("#6a1fd1"), "gem": col("#ff2e97")}
GOLD_EDGE, GOLD_PALE = col("#ffd36a"), col("#fff1b8")


def write_tga(path: Path, w: int, h: int, px: bytearray) -> None:
    rows = bytearray()
    for i in range(0, len(px), 4):
        r, g, b, a = px[i:i + 4]
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    path.write_bytes(header + bytes(rows))
    print(f"wrote {path} ({w}x{h})")


def write_png(path: Path, w: int, h: int, grid) -> None:
    """One px per sprite px, for the mockup."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for (x, y), (r, g, b, a) in grid.items():
        if 0 <= x < w and 0 <= y < h:
            im.putpixel((x, y), (int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
    im.save(path)


class Layer:
    def __init__(self):
        self.p: dict[tuple[int, int], tuple[float, float, float, float]] = {}

    def paint(self, x, y, c):
        if c[3] <= 0:
            return
        old = self.p.get((x, y))
        if old is None or c[3] >= 1.0:
            self.p[(x, y)] = c
            return
        r, g, b, a = c
        orr, og, ob, oa = old
        na = a + oa * (1 - a)
        self.p[(x, y)] = ((r * a + orr * oa * (1 - a)) / na, (g * a + og * oa * (1 - a)) / na, (b * a + ob * oa * (1 - a)) / na, na)

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.paint(xx, yy, c)


def to_texels(layer: Layer, w: int, h: int) -> bytearray:
    out = bytearray(w * SCALE * h * SCALE * 4)
    tw = w * SCALE
    for (x, y), (r, g, b, a) in layer.p.items():
        if not (0 <= x < w and 0 <= y < h):
            raise ValueError(f"px ({x}, {y}) outside {w} x {h}")
        rgba = bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
        for dy in range(SCALE):
            for dx in range(SCALE):
                i = ((y * SCALE + dy) * tw + x * SCALE + dx) * 4
                out[i:i + 4] = rgba
    return out


# ---------------------------------------------------------------------------------------------------------------------
# one dagger, in its own frame: u runs from the pivot along the blade, v across it (negative = the left, lit side)
# ---------------------------------------------------------------------------------------------------------------------
U_POMMEL, U_GRIP, U_GUARD, U_BLADE, U_TIP = 3.0, 5.0, 15.0, 17.5, 49.0
U_TAPER = 39.0
HW_BLADE, HW_GRIP, HW_GUARD, HW_POMMEL = 3.6, 1.7, 5.4, 2.3


def shape_at(u: float, v: float):
    """The part of the dagger at (u, v), or None. Returns (part, edge) where edge is the distance in px to the nearest side."""
    av = abs(v)
    if U_POMMEL <= u < U_GRIP:
        return ("pommel", HW_POMMEL - av) if av <= HW_POMMEL else None
    if U_GRIP <= u < U_GUARD:
        return ("grip", HW_GRIP - av) if av <= HW_GRIP else None
    if U_GUARD <= u < U_BLADE:
        # the cross guard curls down at its ends
        lim = HW_GUARD - (0.9 if av > HW_GUARD - 1.3 else 0)
        return ("guard", lim - av) if av <= HW_GUARD else None
    if U_BLADE <= u <= U_TIP:
        hw = HW_BLADE if u <= U_TAPER else HW_BLADE * (U_TIP - u) / (U_TIP - U_TAPER)
        return ("blade", hw - av) if av <= hw else None
    return None


def dagger_mask(angle_deg: float):
    """{(x, y): (part, edge, u, v)} for the box, the pivot at PIVOT; samples px centres."""
    a = math.radians(angle_deg)
    sa, ca = math.sin(a), math.cos(a)
    out = {}
    for y in range(FAN_H):
        for x in range(FAN_W):
            dx, dy = x + 0.5 - PIVOT[0], PIVOT[1] - (y + 0.5)       # up is +dy
            u = dx * sa + dy * ca
            v = dx * ca - dy * sa
            hit = shape_at(u, v)
            if hit:
                out[(x, y)] = (hit[0], hit[1], u, v)
    return out


def grip_band(u: float) -> bool:
    return int(u) % 2 == 0


def body_color(pal, part, edge, u, v):
    if part == "pommel":
        return pal["gold"] if v < 0 else pal["goldDk"]
    if part == "grip":
        return pal["gripB"] if grip_band(u) else pal["grip"]
    if part == "guard":
        return pal["gold"] if v < 0.8 and edge > 0.6 else pal["goldDk"]
    # blade
    if abs(v) < 0.65 and 20.0 <= u <= 37.5:
        return pal["fuller"]
    if edge < 1.0:
        return pal["hi"] if v < 0 else pal["dk"]
    return pal["lt"] if v < 0 else pal["dk"]


def lit_dagger(i: int, solid: dict):
    """The full-shape lit colours of dagger i: {(x, y): colour} plus the shape set (without outline)."""
    mask = solid[i]
    cols = {}
    for (x, y), (part, edge, u, v) in mask.items():
        c = body_color(LIT, part, edge, u, v)
        if part == "guard" and abs(v) < 1.2 and u < 16.6:
            c = LIT["gem"]
        cols[(x, y)] = c
    # tip glint: the last blade px
    tip = [(p, m[2]) for p, m in mask.items() if m[0] == "blade"]
    if tip:
        (p, _u) = max(tip, key=lambda t: t[1])
        cols[p] = LIT["hi"]
    return cols


def dead_dagger(i: int, solid: dict):
    mask = solid[i]
    cols = {}
    for (x, y), (part, edge, u, v) in mask.items():
        c = body_color(DEAD, part, edge, u, v)
        if part == "guard" and abs(v) < 1.2 and u < 16.6:
            c = DEAD["gem"]
        cols[(x, y)] = c
    return cols


NB = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def outline_of(cells: set):
    out = set()
    for (x, y) in cells:
        for dx, dy in NB:
            q = (x + dx, y + dy)
            if q not in cells:
                out.add(q)
    return out


def build_fan():
    solid = [dagger_mask(a) for a in ANGLES]
    shapes = [set(m) for m in solid]
    outlines = [outline_of(s) for s in shapes]
    # the footprint of dagger i with its outline; later daggers cover earlier ones
    foot = [shapes[i] | outlines[i] for i in range(5)]
    visible_shape, visible_outline = [], []
    for i in range(5):
        later = set()
        for j in range(i + 1, 5):
            later |= foot[j]
        visible_shape.append(shapes[i] - later)
        visible_outline.append((outlines[i] - shapes[i]) - later)
    return solid, shapes, outlines, foot, visible_shape, visible_outline


def cuff_layer(lit: bool = False) -> Layer:
    """The leather cuff the five grips come out of, with the pivot at its centre."""
    L = Layer()
    cx, cy = PIVOT
    R = 7
    rim, face, hi, dk = col("#ffd23f"), col("#2a1d48"), col("#a855f7"), col("#120822")
    ring = col("#b9811a")
    pts = {}
    for y in range(-R - 1, R + 2):
        for x in range(-R - 1, R + 2):
            d = math.hypot(x + 0.5 - 0.0, y + 0.5 - 0.0)
            pts[(x, y)] = d
    for (x, y), d in pts.items():
        if d <= R - 0.5 + 0.5:
            if d > R - 1.6:
                L.paint(cx + x, cy + y, rim if (x + y) < 1 else ring)
            else:
                L.paint(cx + x, cy + y, face)
        elif d <= R + 1.5:
            L.paint(cx + x, cy + y, dk)
    for (x, y), d in pts.items():           # a soft violet highlight top left inside the face
        if 2.6 < d < 4.0 and x < 0 and y < 0 and x + y < -2:
            L.paint(cx + x, cy + y, mix(face, hi, 0.4))
    return L


def fan_layers():
    solid, shapes, outlines, foot, vs, vo = build_fan()
    dead = Layer()
    lits = [Layer() for _ in range(5)]
    for i in range(5):
        cols_d = dead_dagger(i, solid)
        cols_l = lit_dagger(i, solid)
        for p in vo[i]:
            dead.paint(p[0], p[1], OUTLINE)
            lits[i].paint(p[0], p[1], OUTLINE)
        for p in vs[i]:
            dead.paint(p[0], p[1], cols_d[p])
            lits[i].paint(p[0], p[1], cols_l[p])
    # ready overlay: gold outline, pale rim on the blade edges, a one px glow beyond the outline
    ready = Layer()
    all_foot = set().union(*foot)
    glow = outline_of(all_foot) - all_foot
    for p in glow:
        ready.paint(p[0], p[1], (GOLD_EDGE[0], GOLD_EDGE[1], GOLD_EDGE[2], 0.42))
    for i in range(5):
        for p in vo[i]:
            ready.paint(p[0], p[1], GOLD_EDGE)
        for p in vs[i]:
            part, edge, u, v = solid[i][p]
            if part == "blade" and edge < 1.0:
                ready.paint(p[0], p[1], GOLD_PALE if v < 0 else GOLD_EDGE)
    flash = Layer()
    for p in all_foot:
        flash.paint(p[0], p[1], col("#ffffff"))
    cuff = cuff_layer()
    for p, c in cuff.p.items():
        dead.paint(p[0], p[1], c)
    # the cuff stays on top of the lit daggers too: it is part of the dead file, and lit files carry no px inside its disc
    inside = set(cuff.p)
    for i in range(5):
        for p in list(lits[i].p):
            if p in inside:
                del lits[i].p[p]
        pass
    for p in list(ready.p):
        if p in inside:
            del ready.p[p]
    for p in list(flash.p):
        if p in inside:
            del flash.p[p]
    return dead, lits, ready, flash, cuff


# ---------------------------------------------------------------------------------------------------------------------
# the 3 x 5 pixel font for FINISH, drawn twice as big
# ---------------------------------------------------------------------------------------------------------------------
FONT = {
    "F": ["XXX", "X..", "XX.", "X..", "X.."], "I": ["XXX", ".X.", ".X.", ".X.", "XXX"],
    "N": ["XX.", "X.X", "X.X", "X.X", "X.X"], "S": [".XX", "X..", ".X.", "..X", "XX."],
    "H": ["X.X", "X.X", "XXX", "X.X", "X.X"],
}


def finish_layer() -> Layer:
    L = Layer()
    word = "FINISH"
    letter_w, gap, sc = 3 * 2, 2, 2
    total = len(word) * letter_w + (len(word) - 1) * gap
    x0 = (FINISH_W - total) // 2
    y0 = (FINISH_H - 5 * sc) // 2
    w = col("#ffffff")
    for k, ch in enumerate(word):
        for j, row in enumerate(FONT[ch]):
            for q, c in enumerate(row):
                if c == "X":
                    L.rect(x0 + k * (letter_w + gap) + q * sc, y0 + j * sc, sc, sc, w)
    return L


def gem_layer() -> Layer:
    """An 8 x 8 diamond with a light top left facet (a white mask: tinted in Lua)."""
    L = Layer()
    for y in range(GEM):
        for x in range(GEM):
            d = abs(x - 3.5) + abs(y - 3.5)
            if d <= 3.5:
                c = col("#ffffff") if (x + y) < 7 else col("#c8c8d8")
                if d > 2.6:
                    c = col("#ffffff") if (x + y) < 7 else col("#9a9ab0")
                L.paint(x, y, c)
    return L


def gem_dim() -> Layer:
    L = Layer()
    for y in range(GEM):
        for x in range(GEM):
            d = abs(x - 3.5) + abs(y - 3.5)
            if 2.6 < d <= 3.5:
                L.paint(x, y, col("#4b2a86"))
            elif d <= 2.6:
                L.paint(x, y, col("#1c1030"))
    return L


def star_layer(turn: float, dead: bool = False) -> Layer:
    """The Slice and Dice blade star: four swept blades round a hub (a pinwheel), on a 24 x 24 cell. White masks for lit (tinted in
    Lua); `turn` is the rotation in radians (the four frames cover a quarter turn at 1/4 steps of the 90 degree symmetry)."""
    L = Layer()
    c = CELL / 2
    R = STAR_R + 0.6
    body, edge = col("#ffffff"), col("#b9b9d4")
    if dead:
        body, edge = col("#2c2048"), col("#3a2a66")
    cells = {}
    for y in range(CELL):
        for x in range(CELL):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            d = math.hypot(dx, dy)
            if d < 1.6:
                continue
            th = math.atan2(dy, dx) - turn - 0.55 * (d / R)
            lobe = max(0.0, math.cos(4 * th)) ** 0.85
            r = R * (0.36 + 0.64 * lobe)
            if d <= r:
                cells[(x, y)] = edge if d > r - 1.1 else body
    for p, colr in cells.items():
        L.paint(p[0], p[1], colr)
    for p in outline_of(set(cells)):
        L.paint(p[0], p[1], col("#120822"))
    hub = col("#120822")
    for dy in range(-1, 1):
        for dx in range(-1, 1):
            L.paint(int(c) + dx, int(c) + dy, hub)
    return L


def spark_layer() -> Layer:
    L = Layer()
    w = col("#ffffff")
    for k in range(-5, 6):
        L.paint(12 + k, 12, (w[0], w[1], w[2], 1.0 if abs(k) < 3 else 0.6))
        L.paint(12, 12 + k, (w[0], w[1], w[2], 1.0 if abs(k) < 3 else 0.6))
    for k in (-1, 1):
        L.paint(12 + k, 12 + k, (w[0], w[1], w[2], 0.8))
        L.paint(12 + k, 12 - k, (w[0], w[1], w[2], 0.8))
    return L


def ring_layer() -> Layer:
    """A dashed ring (white mask) for the empty Slice and Dice look, radius 11."""
    L = Layer()
    cx = cy = CELL // 2
    n = 40
    for i in range(n):
        if i % 4 == 3:
            continue
        a = i / n * math.tau
        L.paint(cx + int(round(math.cos(a) * 10.5 - 0.5)), cy + int(round(math.sin(a) * 10.5 - 0.5)), col("#ffffff"))
    return L


def atlas_layer() -> Layer:
    A = Layer()

    def put(index, layer):
        ox, oy = (index % ATLAS_COLS) * CELL, (index // ATLAS_COLS) * CELL
        for (x, y), c in layer.p.items():
            A.paint(x + ox, y + oy, c)

    for k in range(4):
        put(k, star_layer(k * math.pi / 8))
    put(4, star_layer(0.0, dead=True))
    put(5, gem_dim())
    put(6, spark_layer())
    put(7, ring_layer())
    return A


def lua_manifest() -> str:
    cells = {name: ((i % ATLAS_COLS) * CELL, (i // ATLAS_COLS) * CELL) for i, name in enumerate(ATLAS_CELLS)}
    lines = ["-- Generated by tools/assets/generate_rogue_fan.py. Never hand edit; regenerate.", "local _, FS = ...", "FS.RogueArt = {"]
    lines.append(f"    SCALE = {SCALE}, FAN_W = {FAN_W}, FAN_H = {FAN_H}, PIVOT_X = {PIVOT[0]}, PIVOT_Y = {PIVOT[1]},")
    lines.append(f"    FINISH_W = {FINISH_W}, FINISH_H = {FINISH_H}, GEM = {GEM}, CELL = {CELL}, STAR_R = {STAR_R},")
    lines.append(f"    ATLAS_W = 128, ATLAS_H = 64, ATLAS_COLS = {ATLAS_COLS},")
    lines.append("    ANGLES = { " + ", ".join(str(a) for a in ANGLES) + " },")
    lines.append("    ATLAS = {")
    for name, (x, y) in cells.items():
        lines.append(f"        {name} = {{ {x}, {y}, {CELL}, {CELL} }},")
    lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    out = Path(os.environ.get("FS_ASSET_OUTPUT_DIR") or Path(__file__).resolve().parent.parent.parent / "forever-stuwave" / "Media" / "Textures")
    out.mkdir(parents=True, exist_ok=True)
    preview = os.environ.get("FS_ROGUE_PREVIEW")
    prev = Path(preview) if preview else None
    if prev:
        prev.mkdir(parents=True, exist_ok=True)
    dead, lits, ready, flash, cuff = fan_layers()
    files = {"rogue_dead": (dead, FAN_W, FAN_H), "rogue_ready": (ready, FAN_W, FAN_H), "rogue_flash": (flash, FAN_W, FAN_H),
             "rogue_finish": (finish_layer(), FINISH_W, FINISH_H), "rogue_gem": (gem_layer(), GEM, GEM)}
    for i, L in enumerate(lits):
        files[f"rogue_lit_{i + 1}"] = (L, FAN_W, FAN_H)
    atl = atlas_layer()
    # the atlas file is 256 x 128 texels (128 x 64 sprite px)? the cells need 5 x 24 across and two rows: 120 x 48 sprite px
    files["rogue_atlas"] = (atl, 128, 64)
    for name, (layer, w, h) in files.items():
        write_tga(out / f"{name}.tga", w * SCALE, h * SCALE, to_texels(layer, w, h))
        if prev:
            write_png(prev / f"{name}.png", w, h, layer.p)
    lua = os.environ.get("FS_ROGUE_LUA")
    if not lua:
        if os.environ.get("FS_ASSET_OUTPUT_DIR"):
            lua = str(out / "RogueArt.lua")
        else:
            lua = str(Path(__file__).resolve().parent.parent.parent / "forever-stuwave" / "Modules" / "CombatHud" / "RogueArt.lua")
    Path(lua).write_text(lua_manifest(), encoding="utf-8")
    print(f"wrote {lua}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
