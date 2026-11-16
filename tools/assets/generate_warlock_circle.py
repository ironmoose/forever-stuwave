#!/usr/bin/env python3
"""Bake the Warlock Gunsight module's 8-bit art: the binding circle, its five shard sockets, the demon medallions.

The design is the mockup "Warlock Binding Circle" (2026-11-16): a summoning circle on a 150 x 86 sprite px canvas. A rune ring
(outer ring, inner ring, ten runes between them) holds a pentagram whose five points are SOUL SHARD sockets; a gem sits in a
socket for every shard held. In the middle is a round medallion of the current demon that fills from the bottom with the
demon's health. The right of the canvas is text, set in the 3 x 5 pixel font baked here. Every sprite px is SCALE x SCALE
texels of one flat colour, so the art stays blocky under the client's filter.

Most pieces are WHITE masks the module tints with SetVertexColor (the rings, runes, star, halo, bolts, the dashed rim and the
text), because their colour is the state's. The shard gems and the demon medallions are full colour.

    warlock_circle.tga        the atlas: masks, sockets, gems, the dim and ghost medallions, the font
    warlock_sigil_<demon>.tga 64 x 64 texels (32 x 32 sprite px) per demon, the LIT medallion alone. A vertical StatusBar
                              stretches it over the whole file, so the engine fills it from the bottom with the secret pet
                              health. The disc is 31 px across with its centre pixel at sprite px (15, 15).

The packing is written to forever-stuwave/Modules/CombatHud/WarlockArt.lua (FS.WarlockArt): every sprite's atlas, texel
rect, size and origin in sprite px. Do not edit it by hand; gunsightwarlock-harness.py regenerates it and fails on a diff.

    python3 tools/assets/generate_warlock_circle.py     (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                          FS_ART_LUA_OUTPUT the manifest path)
"""

from __future__ import annotations

import math
import os
import random
import struct

SCALE = 2                       # texels per sprite px
PAD = 1                         # empty sprite px round every packed sprite

# the module's geometry, sprite px on the 150 x 86 canvas (the module and the mockup share these)
CX, CY = 40, 43                 # the circle's centre pixel
R_OUT, R_IN = 39, 32            # the outer and the inner ring; the star's points sit on the inner ring
R_RUNE = 35.5                   # the runes sit between the rings
R_MED = 15                      # the medallion's disc (31 px across)
MED_BOX = 32                    # the medallion's box, sprite px (a StatusBar fills it)
R_STAR = 32
POINTS = [(-90 + 72 * k) for k in range(5)]                 # degrees; the shard sockets, clockwise from the top
RUNE_ANG = [(-72 + 36 * j) for j in range(10)]
GEM_W, GEM_H = 7, 10

DEMONS = ["imp", "voidwalker", "sayaad", "felhunter", "bound"]

# ---------------------------------------------------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------------------------------------------------


def jround(v):
    return math.floor(v + 0.5)


def hexrgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def mixc(a, b, k):
    A, B = hexrgb(a), hexrgb(b)
    return "#" + "".join(f"{jround(x + (y - x) * k):02x}" for x, y in zip(A, B))


def solid(h, a=1.0):
    r, g, b = hexrgb(h)
    return (r, g, b, int(round(a * 255)))


W1 = solid("#ffffff")
INK = "#120822"                  # the dark of the panel
OFF = "#2c2048"
VIOLET = "#a855f7"

# ---------------------------------------------------------------------------------------------------------------------
# Raster helpers. A layer is {(x, y): (r, g, b, a)} in sprite px, relative to the sprite's origin (the circle's centre pixel
# for the circle pieces, the box's top left for boxes).
# ---------------------------------------------------------------------------------------------------------------------


def ring(r, thick=1.0, col=W1, phase=None, dash=None):
    out = {}
    n = int(r) + 2
    for y in range(-n, n + 1):
        for x in range(-n, n + 1):
            d = math.hypot(x, y)
            if r - thick / 2 <= d < r + thick / 2:
                if dash:
                    a = math.atan2(y, x)
                    idx = int((a + math.pi) / (2 * math.pi) * dash[2])
                    if idx % (dash[0] + dash[1]) >= dash[0]:
                        continue
                out[(x, y)] = col
    return out


def disc(r, col):
    n = int(r) + 1
    return {(x, y): col for y in range(-n, n + 1) for x in range(-n, n + 1) if math.hypot(x, y) <= r + 0.001}


def line(p0, p1, col=W1):
    (x0, y0), (x1, y1) = p0, p1
    pts, dx, dy = {}, abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts[(x0, y0)] = col
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def at(deg, r):
    a = math.radians(deg)
    return (jround(math.cos(a) * r), jround(math.sin(a) * r))


def art(rows, pal, ox=0, oy=0):
    out = {}
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch != "." and ch in pal:
                out[(ox + i, oy + j)] = pal[ch]
    return out


def put(dst, src, dx=0, dy=0):
    for (x, y), c in src.items():
        dst[(x + dx, y + dy)] = c


def mask_of(layer):
    return {p: W1 for p, c in layer.items() if c[3] > 0}


def edge_of(layer):
    return {p: W1 for p in layer if any((p[0] + dx, p[1] + dy) not in layer for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}


# ---------------------------------------------------------------------------------------------------------------------
# The circle's pieces
# ---------------------------------------------------------------------------------------------------------------------

RUNES = [
    ["X....", "XX...", "X.X..", "X..X.", "X...X"],
    ["..X..", ".XX..", "X.X.X", "..XX.", "..X.."],
    ["X...X", ".X.X.", "..X..", "..X..", "..X.."],
    [".XXX.", "X...X", "X.X.X", "X...X", ".XXX."],
    ["..X..", ".XXX.", "X.X.X", "..X..", "..X.."],
    ["X.X.X", "X.X.X", ".XXX.", "..X..", "..X.."],
    ["X...X", "XX.XX", "X.X.X", "X...X", "X...X"],
    ["..X..", "..XX.", "..X.X", "..X..", "..X.."],
    ["XXX..", "..X..", ".X...", "X..X.", "..XXX"],
    ["X...X", "X...X", ".XXX.", "..X..", "..X.."],
]


def rune_layer(i):
    return {(x - 2, y - 2): W1 for y, row in enumerate(RUNES[i]) for x, ch in enumerate(row) if ch == "X"}


def star_layer():
    pts = [at(a, R_STAR) for a in POINTS]
    out = {}
    for k in range(5):
        out.update(line(pts[k], pts[(k + 2) % 5]))
    return out


def halo_layer():
    """A dithered glow: ordered 4 x 4 dither in three alpha steps, thickest just inside the outer ring."""
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    out = {}
    n = R_OUT + 3
    for y in range(-n, n + 1):
        for x in range(-n, n + 1):
            d = math.hypot(x, y)
            if d > R_OUT + 3.4:
                continue
            if d > R_OUT:
                k = 1 - (d - R_OUT) / 3.4
            else:
                k = max(0.0, (d - 29) / (R_OUT - 29)) ** 1.6 * 0.8
            if k <= 0:
                continue
            if k * 16 > bayer[y & 3][x & 3] + 0.5:
                out[(x, y)] = solid("#ffffff", 0.34 if k > 0.55 else 0.2)
    return out


def zap_layer(seed):
    """Lightning from the medallion's rim out to two of the five sockets: jagged one px lines, deterministic per seed."""
    rng = random.Random(seed)
    out = {}
    for ang in rng.sample(POINTS, 2):
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        path = []
        n = 7
        for t in range(n + 1):
            r = R_MED + 2 + (R_STAR - 6 - R_MED - 2) * t / n
            j = 0 if t in (0, n) else rng.uniform(-4, 4)
            path.append((jround(ux * r + nx * j), jround(uy * r + ny * j)))
        for s0, e0 in zip(path, path[1:]):
            out.update(line(s0, e0))
        mid = path[n // 2]
        off = rng.choice((-1, 1)) * 5
        out.update(line(mid, (mid[0] + jround(nx * off + ux * 4), mid[1] + jround(ny * off + uy * 4))))
    return out


GEM_ROWS = [
    "...O...",
    "..OLO..",
    ".OLLMO.",
    "OLHLMMO",
    "OLLMMDO",
    "OLMMMDO",
    "OLMMDDO",
    ".OMMDO.",
    "..ODO..",
    "...O...",
]
GEM_PAL = {
    "violet": {"O": solid("#2a1250"), "L": solid("#d9b3ff"), "M": solid("#a855f7"), "D": solid("#5b2d9e"), "H": solid("#ffffff")},
    "amber": {"O": solid("#4a2a06"), "L": solid("#ffe0a0"), "M": solid("#ffb648"), "D": solid("#b36a10"), "H": solid("#ffffff")},
    "white": {"O": solid("#6b4fa0"), "L": solid("#ffffff"), "M": solid("#f3fbff"), "D": solid("#cdbbf0"), "H": solid("#ffffff")},
}


def gem_layer(kind):
    return art(GEM_ROWS, GEM_PAL[kind], -3, -5)


def socket_layer(question=False):
    base = art(GEM_ROWS, {"O": solid("#4b2a86"), "L": solid("#1b0f33"), "M": solid("#150a28"), "D": solid("#150a28"),
                          "H": solid("#150a28")}, -3, -5)
    if question:
        q = art(["XX.", "..X", ".X.", "...", ".X."], {"X": solid("#7a6aa8")}, -1, -3)
        put(base, q)
    return base


DROP_ROWS = ["..X..", ".XXX.", "XXXXX", "XXXXX", ".XXX."]


def drop_layer():
    return art(DROP_ROWS, {"X": W1}, -2, -2)


# ---------------------------------------------------------------------------------------------------------------------
# The demon medallions: 21 x 21 art on a 31 px disc whose centre pixel is (15, 15) of a 32 px box
# ---------------------------------------------------------------------------------------------------------------------

IMP = (
    ["........y........",
     ".......yRy.......",
     "o.....yRRRy.....o",
     "oo...ooRRRoo...oo",
     "ror.orrrrrrro.ror",
     ".rrorrrrrrrrrorr.",
     "..orrrrrrrrrrro..",
     "..orykrrrrrkyro..",
     "..orrrrrrrrrrro..",
     "..orrrwrrrwrrro..",
     "...orrwwwwwrro...",
     "...orrrrrrrrro...",
     "....oorrrrroo....",
     "......ooooo......"],
    {"o": "#3a0f0a", "r": "#d63a1e", "R": "#ff7a3a", "y": "#ffd23f", "k": "#2a0a05", "w": "#fff3d8"},
    "#2a0a12", "#ff6a2e",
)

VOIDWALKER = (
    ["......ooooooo......",
     "....ooppppppoo.....",
     "...oppppppppppo....",
     "..oppppppppppppo...",
     "..oppkkkkkkkkppo...",
     "..opkkkkkkkkkkpo...",
     "..opkkcckkkcckpo...",
     "..opkkcCkkkcCkpo...",
     "..opkkkkkkkkkkpo...",
     "..oppkkkkkkkkppo...",
     "..opppkkkkkkpppo...",
     "..oppppkkkkppppo...",
     "..opp.opppppo.ppo..",
     "..op...opppo...po..",
     "..o.....ooo.....o.."],
    {"o": "#1a0a33", "p": "#5b2d9e", "k": "#0a0414", "c": "#22e0ff", "C": "#ffffff"},
    "#150a2a", "#a855f7",
)

SAYAAD = (
    ["o...............o",
     "oo.............oo",
     "orro...ooo...orro",
     "oRrro.orrro.orrRo",
     ".orrrooRrRoorrro.",
     "..orrrrrrrrrrro..",
     "..orrrrrrrrrrro..",
     "..orwwrrrrrwwro..",
     "..orwkrrrrrkwro..",
     "..orrrrrrrrrrro..",
     "...orrrhrhrrro...",
     "...orrrrhrrrro...",
     "....orrrrrrro....",
     ".....ooooooo....."],
    {"o": "#3a0a26", "r": "#e0368f", "R": "#ff7ac0", "w": "#ffe6f4", "k": "#3a0a26", "h": "#ff2e5a"},
    "#2a0a1e", "#ff2e97",
)

FELHUNTER = (
    ["o.o.............o.o",
     "oro.............oro",
     "orro...ooooo...orro",
     "orrrooorrrrroorrro.",
     ".orrrrrrrrrrrrrro..",
     "..orrrrrrrrrrrro...",
     "..orgGrrrrrrgGro...",
     "..orgGrrrrrrgGro...",
     "..orrrrrrrrrrrro...",
     "...orrrrkkkrrro....",
     "...orrrkkkkkrro....",
     "...orwrkkkkkrwo....",
     "....owrwkwkwrwo....",
     ".....owwoooowwo....."],
    {"o": "#0f2a0a", "r": "#2f8f2a", "g": "#39ff14", "G": "#e8ffd8", "k": "#0a1a06", "w": "#f0ffe8"},
    "#0a1a0a", "#39ff14",
)

BOUND = (
    ["........o........",
     ".......ovo.......",
     ".......ovo.......",
     "......ovvvo......",
     "oooooovvvvvoooooo",
     ".ovvvvvvvvvvvvvo.",
     "..oovvvvvvvvvoo..",
     "....ovvvvvvvo....",
     "....ovvvovvvo....",
     "...ovvvo.ovvvo...",
     "...ovvo...ovvo...",
     "..ovvo.....ovvo..",
     "..ovo.......ovo..",
     "..oo.........oo.."],
    {"o": "#2a1250", "v": "#a855f7"},
    "#150a2a", "#a855f7",
)

DEMON_ART = {"imp": IMP, "voidwalker": VOIDWALKER, "sayaad": SAYAAD, "felhunter": FELHUNTER, "bound": BOUND}


def norm(rows):
    """Every row centred on the widest, so a row typed a char short does not skew the art."""
    width = max(len(r) for r in rows)
    return [r if len(r) == width else r.strip(".").center(width, ".") for r in rows]


def creature_layer(name, dim=False):
    rows, pal, bg, rim = DEMON_ART[name]
    rows = norm(rows)
    width = len(rows[0])
    colours = {k: v for k, v in pal.items()}
    if dim:
        colours = {k: mixc(v, "#2c2048", 0.72) for k, v in colours.items()}
    layer = {}
    # the disc, its dark wash and 1 px rim in the demon's colour
    back = disc(R_MED, solid(bg))
    rimpx = ring(R_MED, 1.0, solid(mixc(rim, "#2c2048", 0.8) if dim else rim))
    put(layer, back, 15, 15)
    put(layer, rimpx, 15, 15)
    ox = 15 - width // 2
    oy = 15 - len(rows) // 2 - 1
    put(layer, art(rows, {k: solid(v) for k, v in colours.items()}, ox, oy))
    return layer


def creature_mask(name):
    rows, pal, _, _ = DEMON_ART[name]
    rows = norm(rows)
    width = len(rows[0])
    return art(rows, {k: W1 for k in pal}, 15 - width // 2, 15 - len(rows) // 2 - 1)


def ghost_layer(name):
    """A dotted outline of the demon, the 'summon me' look: every other edge px, in white."""
    edge = edge_of(creature_mask(name))
    return {p: W1 for i, p in enumerate(sorted(edge)) if (p[0] + p[1]) % 2 == 0}


# ---------------------------------------------------------------------------------------------------------------------
# The font: 3 x 5, a few wider letters
# ---------------------------------------------------------------------------------------------------------------------

FONT = {
    "A": [".X.", "X.X", "XXX", "X.X", "X.X"], "B": ["XX.", "X.X", "XX.", "X.X", "XX."],
    "C": [".XX", "X..", "X..", "X..", ".XX"], "D": ["XX.", "X.X", "X.X", "X.X", "XX."],
    "E": ["XXX", "X..", "XX.", "X..", "XXX"], "F": ["XXX", "X..", "XX.", "X..", "X.."],
    "G": [".XX", "X..", "X.X", "X.X", ".XX"], "H": ["X.X", "X.X", "XXX", "X.X", "X.X"],
    "I": ["XXX", ".X.", ".X.", ".X.", "XXX"], "J": ["..X", "..X", "..X", "X.X", ".X."],
    "K": ["X.X", "X.X", "XX.", "X.X", "X.X"], "L": ["X..", "X..", "X..", "X..", "XXX"],
    "M": ["X...X", "XX.XX", "X.X.X", "X...X", "X...X"], "N": ["X...X", "XX..X", "X.X.X", "X..XX", "X...X"],
    "O": [".X.", "X.X", "X.X", "X.X", ".X."], "P": ["XX.", "X.X", "XX.", "X..", "X.."],
    "R": ["XX.", "X.X", "XX.", "X.X", "X.X"], "S": [".XX", "X..", ".X.", "..X", "XX."],
    "T": ["XXX", ".X.", ".X.", ".X.", ".X."], "U": ["X.X", "X.X", "X.X", "X.X", "XXX"],
    "V": ["X.X", "X.X", "X.X", "X.X", ".X."], "W": ["X...X", "X...X", "X.X.X", "XX.XX", "X...X"],
    "X": ["X.X", "X.X", ".X.", "X.X", "X.X"], "Y": ["X.X", "X.X", ".X.", ".X.", ".X."],
    "Z": ["XXX", "..X", ".X.", "X..", "XXX"],
    "0": ["XXX", "X.X", "X.X", "X.X", "XXX"], "1": [".X.", "XX.", ".X.", ".X.", "XXX"], "2": ["XXX", "..X", "XXX", "X..", "XXX"],
    "3": ["XXX", "..X", ".XX", "..X", "XXX"], "4": ["X.X", "X.X", "XXX", "..X", "..X"], "5": ["XXX", "X..", "XXX", "..X", "XXX"],
    "6": ["XXX", "X..", "XXX", "X.X", "XXX"], "7": ["XXX", "..X", ".X.", ".X.", ".X."], "8": ["XXX", "X.X", "XXX", "X.X", "XXX"],
    "9": ["XXX", "X.X", "XXX", "..X", "XXX"],
    "?": ["XX.", "..X", ".X.", "...", ".X."], "-": ["...", "...", "XXX", "...", "..."], "+": ["...", ".X.", "XXX", ".X.", "..."],
    ".": ["...", "...", "...", "...", ".X."],
}
FONT_NAMES = {"?": "q", "-": "minus", "+": "plus", ".": "dot"}


def glyph_name(ch):
    return "f_" + FONT_NAMES.get(ch, ch)


def font_layer(ch):
    return {(x, y): W1 for y, row in enumerate(FONT[ch]) for x, c in enumerate(row) if c == "X"}


# ---------------------------------------------------------------------------------------------------------------------
# Packing and output (the Paladin pipeline)
# ---------------------------------------------------------------------------------------------------------------------


class Sprite:
    def __init__(self, name, layer):
        self.name = name
        xs = [p[0] for p in layer] or [0]
        ys = [p[1] for p in layer] or [0]
        self.x0, self.y0 = min(xs), min(ys)
        self.w, self.h = max(xs) - self.x0 + 1, max(ys) - self.y0 + 1
        self.layer = layer
        self.tx = self.ty = 0


def pack(sprites, size):
    W, H = size
    x = y = shelf = 0
    for s in sorted(sprites, key=lambda s: (-s.h, -s.w, s.name)):
        w, h = (s.w + 2 * PAD) * SCALE, (s.h + 2 * PAD) * SCALE
        if x + w > W:
            x, y = 0, y + shelf
            shelf = 0
        if y + h > H or w > W:
            return False
        s.tx, s.ty = x + PAD * SCALE, y + PAD * SCALE
        x += w
        shelf = max(shelf, h)
    return True


def raster(size, sprites):
    W, H = size
    px = bytearray(W * H * 4)
    for s in sprites:
        for (x, y), (r, g, b, a) in s.layer.items():
            bx, by = s.tx + (x - s.x0) * SCALE, s.ty + (y - s.y0) * SCALE
            for dy in range(SCALE):
                o = ((by + dy) * W + bx) * 4
                for dx in range(SCALE):
                    px[o + dx * 4:o + dx * 4 + 4] = bytes((b, g, r, a))
    return px


def tga_bytes(size, px):
    W, H = size
    return struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, W, H, 32, 0x28) + bytes(px)


def box_tga(layer):
    """A 32 x 32 sprite px box as a 64 x 64 texel file (the layer's coordinates are the box's)."""
    s = Sprite("box", layer)
    s.x0, s.y0, s.tx, s.ty = 0, 0, 0, 0
    return tga_bytes((MED_BOX * SCALE, MED_BOX * SCALE), raster((MED_BOX * SCALE, MED_BOX * SCALE), [s]))


ATLAS_SIZES = [(256, 256), (512, 256), (512, 512), (1024, 512), (1024, 1024)]


def build():
    sprites = []

    def add(name, layer):
        sprites.append(Sprite(name, layer))

    add("ring_out", ring(R_OUT))
    add("ring_in", ring(R_IN))
    add("halo", halo_layer())
    add("star", star_layer())
    for i in range(10):
        add(f"rune{i}", rune_layer(i))
    add("socket", socket_layer())
    add("socket_q", socket_layer(True))
    for kind in GEM_PAL:
        add(f"gem_{kind}", gem_layer(kind))
    add("drop", drop_layer())
    for k in range(6):
        add(f"zap{k}", zap_layer(k + 1))
    add("med_rim", {(x + 15, y + 15): c for (x, y), c in ring(R_MED).items()})
    add("med_dash", {(x + 15, y + 15): c for (x, y), c in ring(R_MED, 1.0, W1, dash=(3, 2, 48)).items()})
    for d in DEMONS:
        add(f"dim_{d}", creature_layer(d, dim=True))
        add(f"ghost_{d}", ghost_layer(d))
    for ch in FONT:
        add(glyph_name(ch), font_layer(ch))
    sizes = None
    for size in ATLAS_SIZES:
        if pack(sprites, size):
            sizes = size
            break
    if not sizes:
        raise SystemExit("the sprites do not fit a 1024 x 1024 atlas")
    return sprites, sizes


def lua_manifest(sprites, size):
    glyph_w = {ch: len(FONT[ch][0]) for ch in FONT}
    lines = [
        "-- Forever STUwave: the Warlock Gunsight module's sprite manifest.",
        "-- GENERATED by tools/assets/generate_warlock_circle.py; do not edit (gunsightwarlock-harness.py checks it).",
        "-- sprite = { tx, ty, w, h, ox, oy }: texel rect in the atlas, size in sprite px, and the sprite's origin",
        "-- (the point the module places) as an offset from the sprite's top left, in sprite px.",
        "",
        "local _, FS = ...",
        "",
        "FS.WarlockArt = {",
        f"    SCALE = {SCALE},",
        f"    CX = {CX}, CY = {CY}, R_OUT = {R_OUT}, R_IN = {R_IN}, R_RUNE = {R_RUNE}, R_MED = {R_MED}, MED_BOX = {MED_BOX},",
        f"    GEM_W = {GEM_W}, GEM_H = {GEM_H},",
        f"    ATLAS = {{ file = \"warlock_circle\", w = {size[0]}, h = {size[1]} }},",
        "    POINTS = { " + ", ".join(str(a) for a in POINTS) + " },",
        "    RUNE_ANG = { " + ", ".join(str(a) for a in RUNE_ANG) + " },",
        "    DEMONS = { " + ", ".join(f'"{d}"' for d in DEMONS) + " },",
        "    ZAPS = 6, RUNES = 10,",
        "    GLYPH_W = { " + ", ".join(f'["{ch}"] = {w}' for ch, w in sorted(glyph_w.items())) + " },",
        "    sprites = {",
    ]
    for s in sorted(sprites, key=lambda s: s.name):
        lines.append(f'        ["{s.name}"] = {{ {s.tx}, {s.ty}, {s.w}, {s.h}, {-s.x0}, {-s.y0} }},')
    lines += ["    },", "}", ""]
    return "\n".join(lines)


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "WarlockArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "WarlockArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    sprites, size = build()
    os.makedirs(here, exist_ok=True)
    with open(os.path.join(here, "warlock_circle.tga"), "wb") as fh:
        fh.write(tga_bytes(size, raster(size, sprites)))
    for d in DEMONS:
        with open(os.path.join(here, f"warlock_sigil_{d}.tga"), "wb") as fh:
            fh.write(box_tga(creature_layer(d)))
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(sprites, size))
    print(f"wrote {here}/warlock_circle.tga {size}, {len(DEMONS)} sigils, {lua}")


if __name__ == "__main__":
    main()
