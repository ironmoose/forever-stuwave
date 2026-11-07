#!/usr/bin/env python3
"""Bake the Warrior Gunsight module's 8-bit art: the roaring helm frames and the rune tiles.

The source is the design mockup (Warrior Roaring Helm, rune ring, 2026-11-07): the helm is a 32 x 32 sprite (the 26 px helm at
x 3, its bushy beard flaring past it), the runes are 3 x 5
glyphs on 7 x 9 (Battle Shout) or 5 x 7 (Demoralizing Shout) tiles. Every sprite px is baked as SCALE x SCALE texels of one flat
colour (no smoothing), so the art stays blocky under the client's filter. Unlike the other generators these are full colour RGBA:
the palettes are part of the art, nothing is tinted in game.

    warrior_helm.tga         256 x 256   16 frames in 64 x 64 texel cells, 4 per row; each cell is the whole 32 x 32 sprite. Frame order is HELM_FRAMES below (GunsightWarrior.lua's FRAME).
    warrior_runes_big.tga    256 x 256   Battle Shout tiles: 8 glyphs across, one row per kind (BIG_KINDS), 24 x 28 texel
                                         cells; a 7 x 9 tile with a 2 px glow margin (11 x 13 sprite px = 22 x 26 texels).
    warrior_runes_small.tga  256 x 256   Demoralizing Shout tiles: same cells, a 5 x 7 tile with the 2 px margin (9 x 11 sprite px
                                         = 18 x 22 texels), one row per kind (SMALL_KINDS).

    python3 tools/assets/generate_warrior_helm.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2          # texels per sprite px
CANVAS = 256

TOP = [
    "..B....................B..",
    ".BB....................BB.",
    ".Bb.......OOOOOO.......bB.",
    ".Bb.....OOMMLLMMOO.....bB.",
    ".bBb...OMMMLHHLMMMO...bBb.",
    "..bBb.OMMMMLHHLMMMMO.bBb..",
    "...bBBOMMMMLLLLMMMMOBBb...",
    "....bbOMMMMMLLMMMMMObb....",
    ".....OOOOOOOOOOOOOOOO.....",
    ".....OLHLLHLLLLHLLHLO.....",
    ".....OOOOOOOOOOOOOOOO.....",
    ".....OKKKKKKOOKKKKKKO.....",
]
EYES = {
    "blaze": "OKYEEYKOOKYEEYKO", "hot": "OKHEEHKOOKHEEHKO", "red": "OKLHHLKOOKLHHLKO",
    "dim": "OKMLLMKOOKMLLMKO", "dark": "OKKKKKKOOKKKKKKO", "flick": "OKKYYKKOOKKYYKKO", "slit": "OKYYYYKOOKYYYYKO",
}
MOUTH = {
    "roar": ["OMOEKEEKKEEKEOMO", "OMOKKKKKKKKKKOMO", "OMOKKKrrrrKKKOMO", "OMOKEKEEEEKEKOMO"],
    "open": ["OMMOEKEKKEKEOMMO", "OMMOKKKKKKKKOMMO", "OMMOEKEKKEKEOMMO", "OMMMMMMMMMMMMMMO"],
    "shut": ["OMMMMMMMMMMMMMMO", "OMMOOOOOOOOOOMMO", "OMMMMMMMMMMMMMMO", "OMMMMMMMMMMMMMMO"],
    "snarl": ["OMOKKKKKKKKKKOMO", "OMOEKEKEEKEKEOMO", "OMOEKEKEEKEKEOMO", "OMOKKKKKKKKKKOMO"],
}
# The bushy beard both helms wear (approved 2026-11-07, after the pixel viking reference): one solid rounded mass in three tones
# with light strands and dark grooves drawn into it, a mustache over the mouth corners, side tips that flare out and down, and
# three points hanging off the bottom. It holds still between shouts; on a cast (the Battle roar, the Demo growl) it puffs out,
# whips side to side and the tips stretch and flutter. Those four poses are baked from the mockup's drawBeard at fixed times.
MUSTACHE = ["....lRRR......RRRl....", "..lRRRRRr....rRRRRRl..", ".lRRRrr.......rrRRRl."]
MASS = [(0, 22), (0, 22), (0, 22), (1, 21), (1, 21), (1, 21), (2, 20), (2, 20), (3, 19), (4, 18), (5, 17), (7, 15), (9, 13)]
STRANDS = [(4, -0.25), (8, -0.10), (11, 0.0), (14, 0.10), (18, 0.25)]          # (x at the root, drift per row)
FLARE = [[0, 0, 0, 0, 0, 1, 1, 1, 0], [0, 0, 0, 0, 1, 1, 2, 2, 1], [0, 0, 0, 1, 1, 2, 3, 3, 2]]
DROPS = [(6, 10, [[2], [3, 1], [3, 2, 1]], 0.7), (10.5, 12, [[2], [4, 2], [4, 2, 2]], 2.2),
         (15, 10, [[2], [3, 1], [3, 2, 1]], 3.8)]
ROAR_POSES = [0.0, 0.07, 0.14, 0.21]   # mockup times: the whip runs centre, right, centre, left

PAL = {
    "rage": {"O": "#ff3b5c", "M": "#6e1430", "L": "#a3203f", "H": "#ff8098", "K": "#12030a", "E": "#fff3e6", "Y": "#ffcf3a",
             "B": "#eadfc4", "b": "#9b8964", "R": "#ff6a2a", "r": "#9e3412", "l": "#ffb04a"},
    "grim": {"O": "#c04cff", "M": "#33124f", "L": "#4f1f78", "H": "#e09cff", "K": "#0c0316", "E": "#fbeaff", "Y": "#ff5ad0",
             "B": "#cbbfe2", "b": "#776b96", "R": "#8a3ad0", "r": "#4e1f80", "l": "#b46cf0"},
    "cold": {"O": "#6c5a9a", "M": "#221b3a", "L": "#30284e", "H": "#8a7ab8", "K": "#0b0814", "E": "#30284e", "Y": "#ffb648",
             "B": "#6e6688", "b": "#423b5c", "R": "#4a3e72", "r": "#2e2650", "l": "#5e5288"},
}
# (eyes, mouth, palette, beard pose), in atlas order. A pose is "still" or a roar pose 0-3. GunsightWarrior.lua's FRAME must match.
HELM_FRAMES = [
    ("blaze", "roar", "rage", 0),         # 0-3 Battle Shout cast: the roar, the beard whipping
    ("blaze", "roar", "rage", 1),         # 1
    ("blaze", "roar", "rage", 2),         # 2
    ("blaze", "roar", "rage", 3),         # 3
    ("hot", "shut", "rage", "still"),     # 4 between shouts: mouth shut
    ("red", "shut", "rage", "still"),     # 5
    ("dim", "shut", "rage", "still"),     # 6
    ("hot", "shut", "grim", "still"),     # 7 Demoralizing Shout
    ("red", "shut", "grim", "still"),     # 8
    ("dim", "shut", "grim", "still"),     # 9
    ("slit", "snarl", "grim", 0),         # 10-13 Demoralizing Shout cast: the growl
    ("slit", "snarl", "grim", 1),         # 11
    ("slit", "snarl", "grim", 2),         # 12
    ("slit", "snarl", "grim", 3),         # 13
    ("dark", "shut", "cold", "still"),    # 14 gone
    ("flick", "shut", "cold", "still"),   # 15 gone, the amber flick
]
# The sprite is HELM_W x HELM_H with the 26 px wide helm's own x = 0 at HELM_OX (the flared, puffed beard reaches past it).
HELM_W, HELM_H, HELM_OX, HELM_CELL = 32, 32, 3, 64

RUNES = [
    ["X.X", "XX.", "X.X", "XX.", "X.."], ["XXX", "X.X", "X.X", "X.X", "X.X"], ["X..", "XX.", "X.X", "XX.", "X.."],
    ["XX.", "X.X", "XX.", "X.X", "X.."], ["XX.", "X.X", "XX.", "X.X", "X.X"], ["..X", ".X.", "X..", ".X.", "..X"],
    [".X.", "X.X", ".X.", ".X.", ".X."], ["X.X", "X.X", ".X.", ".X.", ".X."],
]
# kind: (rim, fill, glyph, glow rgba or None, glow level, style). Style "solid" | "dashed" | "dotted".
TILE = {
    "rage1": ("#ff3b5c", "#5a1028", "#ffd0d8", (255, 59, 92, 0.28), 1, "solid"),
    "rage2": ("#ff3b5c", "#5a1028", "#ffd0d8", (255, 59, 92, 0.28), 2, "solid"),
    "grim1": ("#c04cff", "#2a0f44", "#f0d0ff", (192, 76, 255, 0.28), 1, "solid"),
    "grim2": ("#c04cff", "#2a0f44", "#f0d0ff", (192, 76, 255, 0.28), 2, "solid"),
    "amber": ("#ffb648", "#4a3008", "#ffe9a8", (255, 182, 72, 0.32), 1, "solid"),
    "off": ("#3a2c5c", "#150c26", "#3a2c5c", None, 0, "solid"),
    "gone": ((255, 182, 72, 0.5), None, None, None, 0, "dashed"),
    "locked": ((157, 147, 196, 0.4), None, None, None, 0, "dashed"),
}
BIG_KINDS = ["rage1", "rage2", "amber", "off", "gone"]
SMALL_KINDS = ["grim1", "grim2", "amber", "off", "gone", "locked"]
MARGIN = 2
CELL_W, CELL_H = 24, 28


def rgba(c):
    if isinstance(c, tuple):
        r, g, b, a = c
        return (r, g, b, int(round(a * 255)))
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 255)


def jround(v):
    """JavaScript Math.round (halves go up), so the bake matches the mockup pixel for pixel."""
    return math.floor(v + 0.5)


def helm_rows(eyes, mouth):
    """The helm's own rows 0 to 18: dome, band, eye slits, cheek guards and the face plate's mouth."""
    rows = list(TOP)                                       # rows 0 to 11, the last one the top of the eye slits
    rows.append("....." + EYES[eyes] + ".....")              # 12, the eyes
    rows.append(".....OKKKKKKOOKKKKKKO.....")                # 13, the bottom of the slits
    rows.append(".....OMMMMMMOOMMMMMMO.....")                # 14, the cheek guards
    rows += ["....." + m + "....." for m in MOUTH[mouth]]
    for i, r in enumerate(rows):
        assert len(r) == 26, (i, len(r))
    return rows


def angry(rows):
    """Angry eyes: the brow cuts down over the inner corner of both slits."""
    rows[11] = ".....OKKKKOOOOOOKKKKO....."
    e = rows[12]
    rows[12] = e[:10] + "KO" + e[12:14] + "OK" + e[16:]


def paint_beard(put, pose):
    """The mockup's drawBeard; put(x, y, ch) in helm coordinates. pose "still" or a roar pose index."""
    roar = pose != "still"
    t = ROAR_POSES[pose] if roar else 0.0
    ox, oy, n = 2, 14, len(MASS)
    swing, puff = (math.sin(t * 22) * 1.6, 1) if roar else (0.0, 0)

    def row_dx(j):
        return jround(swing * max(0.0, (j - 4) / (n - 5)))

    def lvl(side):
        return 2 - (1 if math.sin(t * 22 + side * math.pi) > 0.6 else 0) if roar else 1

    fl, fr = FLARE[lvl(0)], FLARE[lvl(1)]

    def span(j):
        a, b = MASS[j]
        if puff and 2 <= j < n - 2:
            a, b = a - 1, b + 1
        return a - (fl[j] if j < len(fl) else 0), b + (fr[j] if j < len(fr) else 0)

    for j in range(n):
        a, b = span(j)
        d = row_dx(j)
        for i in range(a, b):
            put(ox + i + d, oy + j, "r" if (i == a or i == b - 1 or j == n - 1) else "R")
    for sx, dr in STRANDS:
        for j in range(2, n):
            a, b = span(j)
            cx, d = jround(sx + dr * j), row_dx(j)
            if cx <= a or cx >= b - 1:
                continue
            put(ox + cx + d, oy + j, "l")
            if cx + 1 < b - 1:
                put(ox + cx + 1 + d, oy + j, "r")
    for c, js, widths, ph in DROPS:
        level = 2 - (1 if math.sin(t * 22 + ph) > 0.6 else 0) if roar else 1
        ws, d = widths[level], row_dx(n - 1)
        for k, w in enumerate(ws):
            x0, last = jround(c - (w - 1) / 2 - 0.01), k == len(ws) - 1
            for i in range(w):
                edge = last or i == 0 or i == w - 1
                put(ox + x0 + i + d, oy + js + 1 + k, "r" if (edge and w > 1) or last else "R")
    for j, row in enumerate(MUSTACHE):
        for i, ch in enumerate(row):
            if ch != ".":
                put(ox + i, oy + 1 + j, ch)


def helm_pixels(eyes, mouth, pal, pose):
    """{(x, y): ch} in helm coordinates, painted in the mockup's drawHelm order."""
    out = {}

    def put(x, y, ch):
        out[(x, y)] = ch

    paint_beard(put, pose)
    rows = helm_rows(eyes, mouth)
    angry(rows)                                             # the same angry eyes on every frame (the growl glows pink)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "." or (j >= 15 and (i < 5 or i > 20)):
                continue
            put(i, j, ch)
    for j, row in enumerate(MUSTACHE):
        for i, ch in enumerate(row):
            if ch != ".":
                put(2 + i, 15 + j, ch)
    return out


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = [(0, 0, 0, 0)] * (w * h)

    def sprite_px(self, x, y, color):
        """One sprite px at sprite coordinate (x, y), already in canvas sprite units."""
        for dy in range(SCALE):
            for dx in range(SCALE):
                tx, ty = x * SCALE + dx, y * SCALE + dy
                if 0 <= tx < self.w and 0 <= ty < self.h:
                    self.px[ty * self.w + tx] = color

    def blend_px(self, x, y, color):
        """Paint over what is there, alpha over."""
        r, g, b, a = color
        for dy in range(SCALE):
            for dx in range(SCALE):
                tx, ty = x * SCALE + dx, y * SCALE + dy
                if not (0 <= tx < self.w and 0 <= ty < self.h):
                    continue
                i = ty * self.w + tx
                br, bg, bb, ba = self.px[i]
                fa = a / 255
                oa = fa + ba / 255 * (1 - fa)
                if oa <= 0:
                    continue
                mix = lambda s, d: int(round((s * fa + d * (ba / 255) * (1 - fa)) / oa))
                self.px[i] = (mix(r, br), mix(g, bg), mix(b, bb), int(round(oa * 255)))


def helm_atlas():
    c = Canvas(CANVAS, CANVAS)
    for f, (eyes, mouth, pal, pose) in enumerate(HELM_FRAMES):
        ox, oy = (f % 4) * HELM_CELL // SCALE, (f // 4) * HELM_CELL // SCALE
        P = PAL[pal]
        for (x, y), ch in helm_pixels(eyes, mouth, pal, pose).items():
            sx = x + HELM_OX
            assert 0 <= sx < HELM_W and 0 <= y < HELM_H, (f, x, y)
            c.sprite_px(ox + sx, oy + y, rgba(P[ch]))
    return c


def tile(c, ox, oy, w, h, glyph, kind):
    rim, fill, ink, glow, level, style = TILE[kind]
    x0, y0 = ox + MARGIN, oy + MARGIN
    if style != "solid":
        col = rgba(rim)
        for i in range(0, w, 2):
            c.sprite_px(x0 + i, y0, col)
            c.sprite_px(x0 + i, y0 + h - 1, col)
        for j in range(0, h, 2):
            c.sprite_px(x0, y0 + j, col)
            c.sprite_px(x0 + w - 1, y0 + j, col)
        return
    if glow is not None and level > 0:
        g = rgba(glow)
        for y in range(y0 - 1, y0 + h + 1):
            for x in range(x0 - 1, x0 + w + 1):
                c.blend_px(x, y, g)
        if level > 1:
            for y in range(y0 + 1, y0 + h - 1):
                c.blend_px(x0 - 2, y, g)
                c.blend_px(x0 + w + 1, y, g)
            for x in range(x0 + 1, x0 + w - 1):
                c.blend_px(x, y0 - 2, g)
                c.blend_px(x, y0 + h + 1, g)
    f, r, k = rgba(fill), rgba(rim), rgba(ink)
    for y in range(h):
        for x in range(w):
            edge = y == 0 or y == h - 1 or x == 0 or x == w - 1
            c.sprite_px(x0 + x, y0 + y, r if edge else f)
    gx, gy = x0 + (w - 3) // 2, y0 + (h - 5) // 2
    for j, row in enumerate(RUNES[glyph]):
        for q, ch in enumerate(row):
            if ch == "X":
                c.sprite_px(gx + q, gy + j, k)


def rune_atlas(kinds, w, h):
    c = Canvas(CANVAS, CANVAS)
    for r, kind in enumerate(kinds):
        for g in range(8):
            tile(c, g * CELL_W // SCALE, r * CELL_H // SCALE, w, h, g, kind)
    return c


def write_tga(path, canvas):
    rows = bytearray()
    for (r, g, b, a) in canvas.px:
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, canvas.w, canvas.h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({canvas.w}x{canvas.h}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))
    write_tga(os.path.join(here, "warrior_helm.tga"), helm_atlas())
    write_tga(os.path.join(here, "warrior_runes_big.tga"), rune_atlas(BIG_KINDS, 7, 9))
    write_tga(os.path.join(here, "warrior_runes_small.tga"), rune_atlas(SMALL_KINDS, 5, 7))


if __name__ == "__main__":
    main()
