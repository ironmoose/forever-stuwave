#!/usr/bin/env python3
"""Bake the Paladin Gunsight module's 8-bit art: the wax seals, the Judgement hammer and the slam's light.

The source is the approved design mockup (Paladin seal and hammer, 2026-11-10, idea 1 "SLAM", hammer A, the seal set locked
the same day): a lumpy wax seal whose colour drains from the top as the 30 s seal runs down, and a stone, gold and blue
warhammer that fills with the seal's colour from the pommel up over the 10 s Judgement cooldown, then swings face first into
the ground. Every function below ports the mockup's canvas drawing pixel for pixel (Math.round is jround); every sprite px is
baked as SCALE x SCALE texels of one flat colour, so the art stays blocky under the client's filter.

Most art is full colour. A few layers are WHITE masks the module tints with SetVertexColor, because their colour is the
seal's: the hammer's tint mask (the mockup's filled colour is mix(mix(base, seal, .2), white, .05); the bake's "filled" body
is that colour without the seal, so the mask laid over it in the seal colour at alpha TINT_A gives the same pixel), the edge
line, the outline, the emblems, the light, the rune, the cracks, the pillar, the rays and the shockwaves.

    paladin_seal.tga     the wax seals (full, drained and level line per seal), the crack overlay, the 3 x 5 digits,
                         the halo, the ground rune emblems and the ground cracks
    paladin_hammer.tga   the hammer at every baked angle (cold, filled, tint mask, outline; the rise frames carry their
                         own fill), the emblems for the core at every angle, the glint bands
    paladin_fx.tga       the light column and its pool, the pillar rows, the rays and the shockwave rings

The packing is written out as forever-stuwave/Modules/CombatHud/PaladinArt.lua (FS.PaladinArt): every sprite's atlas,
texel rect, size and origin in sprite px, plus the angle tables the module picks frames from. Do not edit it by hand;
gunsightseals-harness.py regenerates it and fails when the committed copy differs.

    python3 tools/assets/generate_paladin_seal.py      (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                         FS_ART_LUA_OUTPUT the manifest path)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2                       # texels per sprite px
PAD = 1                         # empty sprite px round every packed sprite (no bleed under a linear filter)

# ---------------------------------------------------------------------------------------------------------------------
# The mockup's data
# ---------------------------------------------------------------------------------------------------------------------

SEALS = {
    "righteousness": "#c9d3e6", "crusader": "#ff9a2e", "fury": "#ff6a1a", "command": "#b565ff",
    "justice": "#ffd23f", "light": "#fff0c0", "wisdom": "#4da3ff",
}
ORDER = ["righteousness", "crusader", "fury", "command", "justice", "light", "wisdom"]
AMBER, WHITE, OUT = "#ffb648", "#f3fbff", "#120822"

EMBW = {
    "righteousness": ["...............", "..XXXXXXXXXXX..", ".XXXXXXXXXXXXX.", ".XXXXXXXXXXXXX.", ".XXXXXXXXXXXXX.",
                      ".XXXXXXXXXXXXX.", ".XXXXXXXXXXXXX.", "..XXXXXXXXXXX..", "......XXX......", "......XXX......",
                      "......XXX......", "......XXX......", ".....XXXXX.....", "......XXX......", "..............."],
    "justice": [".......X.......", "......XXX......", "XXXXXXXXXXXXXXX", "..X....X....X..", ".X.X...X...X.X.",
                ".X.X...X...X.X.", "X...X..X..X...X", "XXXXX..X..XXXXX", ".XXX...X...XXX.", ".......X.......",
                ".......X.......", ".....XXXXX.....", "....XXXXXXX....", "...............", "..............."],
    "light": ["......XX.......", "...XX.XX.XX....", "...XX.XX.XX.XX.", "...XX.XX.XX.XX.", "...XX.XX.XX.XX.",
              "...XX.XX.XX.XX.", "...XXXXXXXXXXX.", "X..XXXXXXXXXXX.", "XX.XXXXXXXXXXX.", ".XXXXXXXXXXXXX.",
              "..XXXXXXXXXXX..", "...XXXXXXXXX...", "....XXXXXXX....", "....XXXXXXX....", "..............."],
}
SWORD = [".....X.....", "....XXX....", "....XXX..X.", "..X.XXX...X", ".X..XXX...X", "X...XXX..X.", "X...XXX.X..",
         ".X.XXXXX...", "..X..X.....", "....XXX....", ".....X....."]
EMB = {
    "righteousness": ["...........", ".XXXXXXXXX.", ".XXXXXXXXX.", ".XXXXXXXXX.", ".XX.....XX.", ".....X.....",
                      ".....X.....", ".....X.....", ".....X.....", "....XXX....", "....XXX...."],
    "crusader": ["...XXXXX...", "....XXX....", "X...XXX...X", "XX..XXX..XX", "XXXXXXXXXXX", "XXXXXXXXXXX", "XXXXXXXXXXX",
                 "XX..XXX..XX", "X...XXX...X", "....XXX....", "...XXXXX..."],
    "command": ["...........", "X....X....X", "XX..XXX..XX", "XXX.XXX.XXX", "XXXXXXXXXXX", "XXXXXXXXXXX", ".XXXXXXXXX.",
                ".X.X.X.X.X.", ".XXXXXXXXX.", ".XXXXXXXXX.", "..........."],
    "justice": [".....X.....", "XXXXXXXXXXX", "X....X....X", "X....X....X", ".X...X...X.", "XXX..X..XXX", "XXX..X..XXX",
                ".....X.....", ".....X.....", "...XXXXX...", "..XXXXXXX.."],
    "light": ["...X...X...", ".X...X...X.", "...........", "..X.X.X.X..", "..X.X.X.X..", "..XXXXXXX.X", "..XXXXXXXX.",
              "..XXXXXXX..", "...XXXXX...", "...XXXXX...", "....XXX...."],
    "wisdom": SWORD,
    "fury": SWORD,
}
# One emblem shape per entry; Wisdom and Fury share the sword in a swirl (told apart by colour, as in the game).
SHAPES = ["righteousness", "crusader", "command", "justice", "light", "sword"]
SHAPE_OF = {k: ("sword" if k in ("wisdom", "fury") else k) for k in ORDER}
EMB_SHAPE = {s: EMB["wisdom" if s == "sword" else s] for s in SHAPES}

DIGITS = {
    "0": ["XXX", "X.X", "X.X", "X.X", "XXX"], "1": [".X.", "XX.", ".X.", ".X.", "XXX"], "2": ["XXX", "..X", "XXX", "X..", "XXX"],
    "3": ["XXX", "..X", ".XX", "..X", "XXX"], "4": ["X.X", "X.X", "XXX", "..X", "..X"], "5": ["XXX", "X..", "XXX", "..X", "XXX"],
    "6": ["XXX", "X..", "XXX", "X.X", "XXX"], "7": ["XXX", "..X", ".X.", ".X.", ".X."], "8": ["XXX", "X.X", "XXX", "X.X", "XXX"],
    "9": ["XXX", "X.X", "XXX", "..X", "XXX"], "S": [".XX", "X..", ".X.", "..X", "XX."],
}

# the module's geometry (sprite px on the 150 x 86 canvas), as drawSlam
WAX_R = 15
HX, GROUND = 108, 66
GX, GY = HX - 12, GROUND - 19        # where the hammer's grip lands
HY = GY - 25                         # the raised head's centre
IX = GX + 25                         # where the face lands

# the slam's clock, in mockup "s" units (game seconds / SLOW)
SLOW, WIND, HIT, STOP, RISE0, RISE1 = 1.8, 0.15, 0.23, 0.31, 1.1, 1.5
COOLDOWN = 10.0
R90 = math.pi / 2

# ---------------------------------------------------------------------------------------------------------------------
# Colour helpers (the mockup's hex / mix, rounding as JavaScript does)
# ---------------------------------------------------------------------------------------------------------------------


def jround(v):
    """JavaScript Math.round (halves go up), so the bake matches the mockup pixel for pixel."""
    return math.floor(v + 0.5)


def hexrgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def tohex(rgb):
    return "#" + "".join(f"{v:02x}" for v in rgb)


def mix(a, b, k):
    A, B = hexrgb(a), hexrgb(b)
    return tohex(tuple(jround(x + (y - x) * k) for x, y in zip(A, B)))


def over(dst, src, a):
    """Canvas source-over of one colour at alpha a onto an opaque colour (both hex)."""
    D, S = hexrgb(dst), hexrgb(src)
    return tohex(tuple(jround(d + (s - d) * a) for d, s in zip(D, S)))


def wax_tones(c):
    return {"hi": mix(c, "#ffffff", .45), "mid": c, "lo": mix(c, "#000000", .38), "deep": mix(c, "#000000", .62),
            "edge": mix(c, "#000000", .75)}


# A layer is a dict {(x, y): (r, g, b, a)} in sprite px, relative to the sprite's origin.
def solid(h, a=1.0):
    r, g, b = hexrgb(h)
    return (r, g, b, int(round(a * 255)))


W1 = solid("#ffffff")

# ---------------------------------------------------------------------------------------------------------------------
# The wax seal (drawWax, sealSide: centre (LX, 36), r 15, seed 1.3)
# ---------------------------------------------------------------------------------------------------------------------


def wax_radius(a, r, seed):
    return r + (1 if math.sin(a * 5 + seed) > .55 else 0) + (1 if math.sin(a * 3 + seed * 2) > .8 else 0)


def wax_layer(key, mode):
    """mode: "full" (the undrained seal), "drain" (every row above the level line), "line" (the level line row).
    The module shows rows above the line from "drain", the line row from "line" and rows below from "full"."""
    c = SEALS[key]
    T = wax_tones(c)
    r, seed = WAX_R, 1.3
    R = r + 2
    out = {}
    for y in range(-R - 3, R + 6):
        for x in range(-R - 1, R + 2):
            yy = y
            a = math.atan2(yy, x)
            d = math.hypot(x, yy)
            rr = wax_radius(a, r, seed)
            drip = (x == -r + 4 and 0 < y <= rr + 2) or (x == r - 6 and 0 < y <= rr + 3) or (x == -r + 5 and 0 < y <= rr + 1)
            if d > rr + 1 and not drip:
                continue
            if d > rr and not drip:
                col = T["edge"]
            elif drip and d > rr:
                col = T["lo"] if y >= rr + 1 else T["mid"]
            else:
                lit = (-x - yy) / (r * 1.4)
                if d > r - 2:
                    col = T["hi"] if lit > .25 else (T["lo"] if lit < -.35 else T["mid"])
                elif d > r - 3.2:
                    col = T["lo"] if lit > 0 else T["hi"]
                else:
                    col = mix(T["mid"], "#ffffff", .18) if lit > .55 else (mix(T["mid"], "#000000", .15) if lit < -.6 else T["mid"])
            if mode == "drain":
                col = mix(col, "#140a24", .72)
            elif mode == "line":
                col = mix(c, "#ffffff", .8)
            out[(x, y)] = col
    # the pressed emblem: dark fill, a light edge on its lower right
    E = EMBW.get(key) or EMB[key]
    EN, EM = len(E), len(E[0])
    ex, ey = -(EM // 2), -(EN // 2)
    drained = mode == "drain"
    for j, row in enumerate(E):
        for i in range(EM):
            if row[i] != "X":
                continue
            out[(ex + i, ey + j)] = "#0e0718" if drained else T["deep"]
            below = j < EN - 1 and E[j + 1][i] == "X"
            right = i < EM - 1 and row[i + 1] == "X"
            if not below:
                out[(ex + i, ey + j + 1)] = "#2a1d40" if drained else T["hi"]
            if not right:
                p = (ex + i + 1, ey + j)
                under = out.get(p)
                top = "#2a1d40" if drained else T["hi"]
                out[p] = over(under, top, .7) if isinstance(under, str) else solid(top, .7)
    return {p: (solid(v) if isinstance(v, str) else v) for p, v in out.items()}


def wax_crack():
    """The amber crack across the seal under 3 s left (the module sets its alpha .6 + .4 sin(t 14))."""
    r = WAX_R
    pts = [(-r + 3, -2), (-4, -1), (-2, 2), (2, 1), (5, 4), (r - 3, 5)]
    out = {}
    for k in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        n = max(abs(x1 - x0), abs(y1 - y0))
        for q in range(n + 1):
            out[(jround(x0 + (x1 - x0) * q / n), jround(y0 + (y1 - y0) * q / n))] = solid(AMBER)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# The hammer (HAMMER_A, hammerSprite, drawHammerAt)
# ---------------------------------------------------------------------------------------------------------------------

HW, HH = 42, 57
HPIV = (21, 37)
TOP_ROW, BOTTOM_ROW = 1, HH - 3      # the fill runs from the pommel (row 54) to the top (row 1)
TINT_A = 0.19                         # the seal colour's share of a filled pixel (see the module header)
HBASE = {
    "S": "#8e9298", "L": "#c3c7cc", "D": "#5a5e66", "k": "#6e7279",
    "G": "#e8b53a", "h": "#ffe08a", "g": "#9a6a14", "v": "#5a3a0a",
    "M": "#aab4c4", "N": "#e6eef8", "m": "#5c6678",
    "B": "#2f5fd0", "b": "#1c3a8a", "c": "#6f9cff",
    "K": "#120a1c", "P": "#e8e2d4", "Q": "#fffaf0", "p": "#a8a090", "n": "#b0702a",
}


def hammer_a():
    G = [["."] * HW for _ in range(HH)]

    def f(x, y, w, h, c):
        for j in range(y, y + h):
            for i in range(x, x + w):
                G[j][i] = c

    def put(x, y, c):
        G[y][x] = c

    for x0, x1 in ((1, 13), (28, 40)):
        f(x0, 1, x1 - x0 + 1, 22, "S"); f(x0, 1, x1 - x0 + 1, 1, "L"); f(x0, 1, 1, 22, "L"); f(x0, 22, x1 - x0 + 1, 1, "D"); f(x1, 1, 1, 22, "D")
        put(x0, 1, "."); put(x1, 1, "."); put(x0, 22, "."); put(x1, 22, ".")
        for j in range(3, 21):
            for i in range(x0 + 1, x1):
                if (i * 7 + j * 13) % 11 == 0:
                    put(i, j, "k")
                elif (i * 5 + j * 3) % 17 == 0:
                    put(i, j, "L")
    for x in (9, 30):
        f(x, 1, 3, 22, "G"); f(x, 1, 1, 22, "h"); f(x + 2, 1, 1, 22, "g"); f(x, 1, 3, 1, "h"); f(x, 22, 3, 1, "g")
        for j in (5, 11, 17):
            put(x + 1, j, "v"); put(x + 1, j - 1, "h")
    for x, d in ((1, 1), (40, -1)):
        for k in range(3):
            put(x, 4 + k * 7, "G"); put(x + d, 4 + k * 7, "g")
    f(14, 2, 1, 20, "M"); f(27, 2, 1, 20, "M"); f(14, 2, 1, 1, "N"); f(27, 2, 1, 1, "N"); f(14, 21, 1, 1, "m"); f(27, 21, 1, 1, "m")
    f(15, 3, 12, 18, "B")
    for j in range(3, 21):
        for i in range(15, 27):
            if (i + j * 2) % 5 == 0:
                put(i, j, "b")
    f(15, 3, 12, 1, "c"); f(15, 20, 12, 1, "b")
    f(17, 23, 8, 3, "G"); f(17, 23, 8, 1, "h"); f(17, 25, 8, 1, "g"); f(20, 24, 2, 1, "K")
    for j in range(26, 47):
        seam = (j - 26) % 4 == 3
        f(19, j, 4, 1, "b" if seam else "B")
        if not seam:
            put(20, j, "c")
        put(22, j, "b")
    f(18, 47, 6, 2, "G"); f(18, 47, 6, 1, "h"); f(18, 48, 6, 1, "g")
    f(18, 49, 6, 3, "P"); f(18, 49, 2, 3, "Q"); f(23, 49, 1, 3, "p")
    f(19, 52, 4, 2, "n"); f(19, 52, 1, 2, "N"); f(20, 54, 2, 1, "n")
    O = [r[:] for r in G]
    for j in range(HH):
        for i in range(HW):
            if G[j][i] == ".":
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    x, y = i + dx, j + dy
                    if 0 <= x < HW and 0 <= y < HH and G[y][x] != ".":
                        O[j][i] = "O"
                        break
    return ["".join(r) for r in O]


HAMMER = hammer_a()


def grey(h):
    r, g, b = hexrgb(h)
    v = jround(r * .3 + g * .55 + b * .15)
    return tohex((v, v, v))


COLD = {k: mix(mix(v, grey(v), .6), "#160c28", .5) for k, v in HBASE.items()}


def filled_neutral(h):
    """The filled colour without the seal: (0.76 base + 0.05 white) / 0.81, so mask x seal at TINT_A over it is the
    mockup's mix(mix(base, seal, .2), white, .05)."""
    return tohex(tuple(min(255, jround((0.76 * v + 0.05 * 255) / (1 - TINT_A))) for v in hexrgb(h)))


FILLED = {k: filled_neutral(v) for k, v in HBASE.items()}


def hammer_src(kind, fill_row=None):
    """A layer in the hammer's own px (0..41, 0..56). kind:
       cold     every material cold (rows at or above fill_row when fill_row is given)
       filled   every material filled, neutral (rows below fill_row when given)
       mask     white silhouette, no outline (rows below fill_row when given)
       edge     white silhouette of row fill_row only
       outline  white outline
       coldout  cold rows above fill_row plus the outline in OUT (the rise frames)
       coldrest cold rows at and below fill_row (a rise frame with no seal: coldout + coldrest is all cold)"""
    out = {}
    for j, row in enumerate(HAMMER):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "O":
                if kind == "outline":
                    out[(i, j)] = W1
                elif kind == "coldout":
                    out[(i, j)] = solid(OUT)
                continue
            if kind == "outline":
                continue
            if kind in ("cold", "coldout"):
                if fill_row is None or j < fill_row:
                    out[(i, j)] = solid(COLD[ch])
            elif kind == "coldrest":
                if j >= fill_row:
                    out[(i, j)] = solid(COLD[ch])
            elif kind == "filled":
                if fill_row is None or j > fill_row:
                    out[(i, j)] = solid(FILLED[ch])
            elif kind == "mask":
                if fill_row is None or j > fill_row:
                    out[(i, j)] = W1
            elif kind == "edge":
                if j == fill_row:
                    out[(i, j)] = W1
    return out


def emblem_src(shape):
    """The emblem on the blue core: EMB at (15 + i, 6 + j) in hammer px, white (the module tints it)."""
    return {(15 + i, 6 + j): W1 for j, row in enumerate(EMB_SHAPE[shape]) for i, ch in enumerate(row) if ch == "X"}


def rotate(src, ang):
    """drawHammerAt: translate to the grip, rotate(ang), drawImage(-21, -37) with no smoothing. Each destination pixel's
    centre is mapped back into the sprite and sampled nearest. The result is relative to the grip."""
    if not src:
        return {}
    ca, sa = math.cos(ang), math.sin(ang)
    out = {}
    for dy in range(-45, 46):
        for dx in range(-45, 46):
            px, py = dx + .5, dy + .5
            sx = px * ca + py * sa + HPIV[0]
            sy = -px * sa + py * ca + HPIV[1]
            p = (math.floor(sx), math.floor(sy))
            v = src.get(p)
            if v is not None:
                out[(dx, dy)] = v
    return out


def glint_src(band):
    """The ready glint: head rows 1..22, 0 <= i + j * .6 - band < 2.5, white at .6 (mix(filled, white, .6))."""
    out = {}
    for j in range(1, 23):
        for i, ch in enumerate(HAMMER[j]):
            if ch in ".O":
                continue
            d = i + j * .6 - band
            if 0 <= d < 2.5:
                out[(i - HPIV[0], j - HPIV[1])] = solid("#ffffff", .6)
    return out


# The baked angles. STAND: full layers (the ready hammer, the wind-up and the swing, the planted hammer). The module picks the
# nearest. RISE: the hammer rising back up after the blow, with the fill it has at that moment baked in.
STAND = [0.0, -0.07, -0.14, -0.21, -0.28, -0.35, 0.15, 0.55, 0.95, 1.3, R90]
RISE_N = 16


def rise_frames():
    """(k, angle, fill_row) per rise frame: k is the rise's progress (s from RISE0 to RISE1), the fill is the mockup's at
    that moment (cd = COOLDOWN - since, charge = 1 - cd / COOLDOWN)."""
    out = []
    for i in range(RISE_N):
        k = (i + .5) / RISE_N
        ang = R90 * (1 - k * k * (3 - 2 * k))
        since = (RISE0 + k * (RISE1 - RISE0)) * SLOW
        charge = 1 - (COOLDOWN - since) / COOLDOWN
        fill_row = jround(BOTTOM_ROW + 1 - (BOTTOM_ROW - TOP_ROW + 1) * charge)
        out.append((k, ang, fill_row))
    return out


GLINT_BANDS = list(range(-10, 53))

# ---------------------------------------------------------------------------------------------------------------------
# Light and impact (drawSlam)
# ---------------------------------------------------------------------------------------------------------------------


def half0(y):
    return 15 + jround(y * 0.14)


def column():
    """The light column from the top of the module down to the ground, centred on the hammer: a dither, its alpha
    edge * (1 - .55 y / GROUND); white (tinted, alpha a in the module). Origin: (HX - 12, 0)."""
    out = {}
    for y in range(GROUND):
        h = half0(y)
        for x in range(-h, h + 1):
            if (x + y) % 2:
                continue
            edge = min(1, (1 - abs(x) / h) * 2.2)
            out[(x, y)] = solid("#ffffff", edge * (1 - 0.55 * y / GROUND))
    return out


def column_pool():
    """The pool where the column meets the ground: every other px, alpha (1 - |x| / h) (the module multiplies a * 1.4)."""
    h = half0(GROUND)
    return {(x, 0): solid("#ffffff", 1 - abs(x) / h) for x in range(-h, h + 1) if x % 2 == 0}


def halo():
    """The halo round the raised head: 36 dots on r 18 (every other of 72), white. Origin: the head's centre."""
    out = {}
    for i in range(0, 72, 2):
        an = i / 72 * math.pi * 2
        out[(jround(math.cos(an) * 18), jround(math.sin(an) * 18))] = W1
    return out


def rune_emblem(shape):
    """The emblem burnt into the ground, squashed: rows 0, 3, 6, 9 at y -2..1. Origin: the impact point."""
    out = {}
    for j, row in enumerate(EMB_SHAPE[shape]):
        if j % 3:
            continue
        for i, ch in enumerate(row):
            if ch == "X":
                out[(i - 5, jround(-2 + j / 3))] = W1
    return out


CRACKS = [[(0, 0), (-5, 1), (-9, 0), (-13, 2), (-18, 1)], [(0, 0), (4, 1), (8, 0), (11, 2), (15, 1), (19, 2)],
          [(0, 0), (-2, 2), (-6, 3)], [(0, 0), (3, 2), (7, 3)]]


def cracks(odd):
    """The glowing ground cracks: odd steps in the seal colour, even steps in its light (two white layers)."""
    out = {}
    for pts in CRACKS:
        for q in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[q], pts[q + 1]
            n = max(abs(x1 - x0), 1)
            for m in range(n + 1):
                p = (jround(x0 + (x1 - x0) * m / n), jround(y0 + (y1 - y0) * m / n))
                if (m % 2 == 1) == odd:
                    out[p] = W1
                else:
                    out.pop(p, None)
    return out


PILLAR_W = list(range(2, 10))


def pillar_row(w, core):
    """One row of the pillar of light at half width w (the module stretches it from the top to the ground). core: the
    white middle (|x| < 2, alpha e), else the seal coloured sides (alpha .7 e)."""
    out = {}
    for x in range(-w, w + 1):
        e = 1 - abs(x) / (w + 1)
        if (abs(x) < 2) == core:
            out[(x, 0)] = solid("#ffffff", e if core else e * .7)
    return out


RAY_K = [i * 0.035 for i in range(10)]


def rays(k, white):
    """The rays bursting out of the impact at moment k (0..0.35): white = the odd rays, else the seal coloured ones."""
    out = {}
    L = 10 + k * 70
    for r in range(10):
        if (r % 2 == 1) != white:
            continue
        an = math.pi * (1.05 + 0.9 * r / 9)
        d = 6
        while d < L:
            if d % 3:
                p = (jround(math.cos(an) * d), jround(math.sin(an) * d * 0.75))
                out[p] = solid("#ffffff", 1 - d / (L + 1))
            d += 1
    return out


SHOCK_R = list(range(8, 51))


def shock(R):
    """A flattened shockwave ring of radius R: the ring at alpha 1, one px inside at .5 (white, tinted per ring)."""
    out = {}
    for i in range(120):
        an = i / 120 * math.pi * 2
        out.setdefault((jround(math.cos(an) * (R - 1)), jround(math.sin(an) * (R - 1) * 0.22)), solid("#ffffff", .5))
    for i in range(120):
        an = i / 120 * math.pi * 2
        out[(jround(math.cos(an) * R), jround(math.sin(an) * R * 0.22))] = W1
    return out


def digit(ch):
    return {(i, j): W1 for j, row in enumerate(DIGITS[ch]) for i, c in enumerate(row) if c == "X"}


# ---------------------------------------------------------------------------------------------------------------------
# Packing and output
# ---------------------------------------------------------------------------------------------------------------------


class Sprite:
    def __init__(self, name, layer):
        self.name = name
        xs = [p[0] for p in layer] or [0]
        ys = [p[1] for p in layer] or [0]
        self.x0, self.y0 = min(xs), min(ys)
        self.w, self.h = max(xs) - self.x0 + 1, max(ys) - self.y0 + 1
        self.layer = layer
        self.atlas = None
        self.tx = self.ty = 0


def pack(sprites, size):
    """Shelf packing, tallest first. Returns False when they do not fit in a size = (w, h) texel atlas."""
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


def write_tga(path, size, sprites):
    W, H = size
    px = bytearray(W * H * 4)
    for s in sprites:
        for (x, y), (r, g, b, a) in s.layer.items():
            bx, by = s.tx + (x - s.x0) * SCALE, s.ty + (y - s.y0) * SCALE
            for dy in range(SCALE):
                o = ((by + dy) * W + bx) * 4
                for dx in range(SCALE):
                    px[o + dx * 4:o + dx * 4 + 4] = bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, W, H, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(px)
    print(f"wrote {path} ({W}x{H}, {os.path.getsize(path)} bytes)")


ATLAS_SIZES = [(256, 256), (512, 256), (512, 512), (1024, 512), (1024, 1024)]


def build():
    atlases = {"seal": [], "hammer": [], "fx": []}

    def add(atlas, name, layer):
        atlases[atlas].append(Sprite(name, layer))

    for key in ORDER:
        for mode in ("full", "drain", "line"):
            add("seal", f"wax_{mode}_{key}", wax_layer(key, mode))
    add("seal", "wax_crack", wax_crack())
    for ch in DIGITS:
        add("seal", f"digit_{ch}", digit(ch))
    add("seal", "halo", halo())
    for shape in SHAPES:
        add("seal", f"rune_{shape}", rune_emblem(shape))
    add("seal", "cracks_odd", cracks(True))
    add("seal", "cracks_even", cracks(False))

    for a, ang in enumerate(STAND):
        for kind in ("cold", "filled", "mask", "outline"):
            add("hammer", f"stand{a}_{kind}", rotate(hammer_src(kind), ang))
        for shape in SHAPES:
            add("hammer", f"stand{a}_emb_{shape}", rotate(emblem_src(shape), ang))
    for r, (_, ang, fill_row) in enumerate(rise_frames()):
        add("hammer", f"rise{r}_coldout", rotate(hammer_src("coldout", fill_row), ang))
        add("hammer", f"rise{r}_coldrest", rotate(hammer_src("coldrest", fill_row), ang))
        add("hammer", f"rise{r}_filled", rotate(hammer_src("filled", fill_row), ang))
        add("hammer", f"rise{r}_mask", rotate(hammer_src("mask", fill_row), ang))
        add("hammer", f"rise{r}_edge", rotate(hammer_src("edge", fill_row), ang))
        for shape in SHAPES:
            add("hammer", f"rise{r}_emb_{shape}", rotate(emblem_src(shape), ang))
    for b in GLINT_BANDS:
        g = glint_src(b)
        if g:
            add("hammer", f"glint_{b}", g)

    add("fx", "column", column())
    add("fx", "column_pool", column_pool())
    for w in PILLAR_W:
        add("fx", f"pillar{w}_core", pillar_row(w, True))
        add("fx", f"pillar{w}_side", pillar_row(w, False))
    for i, k in enumerate(RAY_K):
        add("fx", f"rays{i}_white", rays(k, True))
        add("fx", f"rays{i}_seal", rays(k, False))
    for R in SHOCK_R:
        add("fx", f"shock{R}", shock(R))

    sizes = {}
    for name, sprites in atlases.items():
        for size in ATLAS_SIZES:
            if pack(sprites, size):
                sizes[name] = size
                break
        else:
            raise SystemExit(f"{name}: the sprites do not fit a {ATLAS_SIZES[-1]} atlas")
        for s in sprites:
            s.atlas = name
    return atlases, sizes


def verify(atlases):
    """Checks the module's assumptions about the bake: the 90 degree frame maps hammer row j to column COL90 - j, the
    upright frame row j to row j - 37 (both relative to the grip), so the module can crop the fill at a row."""
    for kind in ("mask",):
        src = hammer_src(kind)
        up, side = rotate(src, 0.0), rotate(src, R90)
        assert len(up) == len(src) and len(side) == len(src), "a right angle turn keeps every px"
        for (i, j) in src:
            assert (i - HPIV[0], j - HPIV[1]) in up
            assert (COL90 - j, i - HPIV[0]) in side, (i, j)
    names = {s.name for sprites in atlases.values() for s in sprites}
    for a in range(len(STAND)):
        assert f"stand{a}_cold" in names


COL90 = HPIV[1] - 1       # the 90 degree frame: hammer row j lands at column COL90 - j from the grip


def lua_manifest(atlases, sizes):
    lines = [
        "-- Forever STUwave: the Paladin Gunsight module's sprite manifest.",
        "-- GENERATED by tools/assets/generate_paladin_seal.py; do not edit (gunsightseals-harness.py checks it).",
        "-- sprite = { atlas, tx, ty, w, h, ox, oy }: texel rect in its atlas, size in sprite px, and the sprite's origin",
        "-- (the point the module places) as an offset from the sprite's top left, in sprite px.",
        "",
        "local _, FS = ...",
        "",
        "FS.PaladinArt = {",
        f"    SCALE = {SCALE},",
        f"    TINT_A = {TINT_A},",
        f"    HW = {HW}, HH = {HH}, PIVX = {HPIV[0]}, PIVY = {HPIV[1]}, TOP_ROW = {TOP_ROW}, BOTTOM_ROW = {BOTTOM_ROW},",
        f"    COL90 = {COL90},",
        "    ATLAS = { " + ", ".join(f'{n} = {{ file = "paladin_{n}", w = {sizes[n][0]}, h = {sizes[n][1]} }}' for n in atlases) + " },",
        "    STAND = { " + ", ".join(f"{a:.6f}" for a in STAND) + " },",
        "    RISE = {",
    ]
    for k, ang, fill_row in rise_frames():
        lines.append(f"        {{ k = {k:.6f}, angle = {ang:.6f}, fill = {fill_row} }},")
    lines += [
        "    },",
        "    GLINT = { " + ", ".join(str(b) for b in GLINT_BANDS if glint_src(b)) + " },",
        "    PILLAR = { " + ", ".join(str(w) for w in PILLAR_W) + " },",
        "    RAY_K = { " + ", ".join(f"{k:.3f}" for k in RAY_K) + " },",
        f"    SHOCK_MIN = {SHOCK_R[0]}, SHOCK_MAX = {SHOCK_R[-1]},",
        "    SHAPE = { " + ", ".join(f'{k} = "{SHAPE_OF[k]}"' for k in ORDER) + " },",
        "    sprites = {",
    ]
    for name in atlases:
        for s in sorted(atlases[name], key=lambda s: s.name):
            lines.append(f'        ["{s.name}"] = {{ "{name}", {s.tx}, {s.ty}, {s.w}, {s.h}, {-s.x0}, {-s.y0} }},')
    lines += ["    },", "}", ""]
    return "\n".join(lines)


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    # an isolated texture output (the generator tests) gets the manifest beside it, never over the committed one
    default_lua = (os.path.join(here, "PaladinArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "PaladinArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    atlases, sizes = build()
    verify(atlases)
    for name, sprites in atlases.items():
        write_tga(os.path.join(here, f"paladin_{name}.tga"), sizes[name], sprites)
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(atlases, sizes))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
