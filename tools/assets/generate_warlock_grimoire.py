#!/usr/bin/env python3
"""Bake the Warlock Gunsight module's art: the Grimoire, its soul crystals, its effects and the pixel font.

The design is the concept "The Grimoire" (2026-11-20, picked over the Soul Jar and the Crowned Skull): the demon's pact book
on a 150 x 86 sprite px canvas. The book is generated art (tools/assets/warlock_grimoire_art/book.png, 46 x 62 sprite px,
pixelized from source_generated_1024.png: ComfyUI, Juggernaut XL, an esports mascot prompt). Its cover lights from the bottom
with the demon's health; five soul crystals stand in a row beside it; the cue word is small, the book acts the cue out.
Every sprite px is SCALE x SCALE texels of one flat colour, so the art stays blocky under the client's filter.

    warlock_grimoire.tga      the atlas: the dark, grey, rim, white and gem looks of the book, the chain, the shadow, the
                              halo, the crystals, the bolts, the rune ring frames, the blood drop and the font
    warlock_grimoire_lit.tga  the LIT book alone in a 64 x 64 sprite px box (128 x 128 texels), the book at BOOK_IN_BOX. A
                              vertical StatusBar stretches it over the whole box, so the engine fills it from the bottom with
                              the secret pet health.

White masks are tinted by the module with SetVertexColor (rim, white, gem, halo, bolts, rune ring, font); the book looks, the
chain, the crystals and the drop are full colour.

The packing is written to forever-stuwave/Modules/CombatHud/WarlockArt.lua (FS.WarlockArt). Do not edit it by hand;
gunsightwarlock-harness.py regenerates it and fails on a diff.

    python3 tools/assets/generate_warlock_grimoire.py   (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                         FS_ART_LUA_OUTPUT the manifest path)
"""

from __future__ import annotations

import math
import os
import random
import struct
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ART_DIR = Path(os.environ.get("FS_WARLOCK_ART_DIR", Path(os.environ.get("FS_ASSETS_DIR", HERE)) / "warlock_grimoire_art"))

SCALE = 2                       # texels per sprite px
PAD = 1                         # empty sprite px round every packed sprite

BOOK_W, BOOK_H = 46, 62
BOX = 64                        # the lit book's StatusBar box, sprite px
BOOK_IN_BOX = (9, 1)            # the book's top left inside the box
GEM_C = (23, 23)                # the cover gem's centre, book px
EYES = ((17, 34), (29, 34))     # the cover face's eyes (2 x 1 px each), book px
HORNS = ((8, 2), (38, 2))       # the horn tips, book px (the bolts start here)
CRY_W, CRY_H = 9, 14
ZAPS = 6
RING_FRAMES = 6
RING_RX, RING_RY = 24, 4


def solid(h, a=1.0):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), int(round(a * 255)))


W1 = (255, 255, 255, 255)


def jround(v):
    return math.floor(v + 0.5)


# ---------------------------------------------------------------------------------------------------------------------
# The book and its looks. A layer is {(x, y): (r, g, b, a)} in sprite px relative to the sprite's origin.
# ---------------------------------------------------------------------------------------------------------------------


def book_layer():
    im = Image.open(ART_DIR / "book.png").convert("RGBA")
    if im.size != (BOOK_W, BOOK_H):
        raise SystemExit(f"book.png is {im.size}, expected {(BOOK_W, BOOK_H)}")
    px = im.load()
    return {(x, y): px[x, y] for y in range(BOOK_H) for x in range(BOOK_W) if px[x, y][3] > 0}


def lum(r, g, b):
    return 0.3 * r + 0.59 * g + 0.11 * b


def clamp(v):
    return max(0, min(255, jround(v)))


def dark_of(layer):
    """The unlit book: a deep violet shadow of itself (the concept page's look)."""
    out = {}
    for p, (r, g, b, a) in layer.items():
        l = lum(r, g, b) * 0.32
        out[p] = (clamp(l * 0.9 + 10), clamp(l * 0.7 + 6), clamp(l * 1.25 + 22), 255)
    return out


def grey_of(layer):
    """Unreadable: a flat grey book, dimmed."""
    out = {}
    for p, (r, g, b, a) in layer.items():
        l = lum(r, g, b) * 0.4
        out[p] = (clamp(l + 8), clamp(l + 6), clamp(l + 16), 255)
    return out


def edge_of(layer):
    return {p: W1 for p in layer if any((p[0] + dx, p[1] + dy) not in layer for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}


def mask_of(layer):
    return {p: W1 for p in layer}


def gem_mask(layer):
    """The green gem on the cover: its px, as a white mask the cue colour tints."""
    out = {}
    for (x, y), (r, g, b, a) in layer.items():
        if abs(x - GEM_C[0]) <= 5 and abs(y - GEM_C[1]) <= 8 and g > r + 30 and g > b + 30:
            out[(x, y)] = W1
    return out


def chain_layer():
    """A chain across the cover, the demon unbound: links every 3 px on a slight sag (book px)."""
    out = {}
    for i in range(0, BOOK_W, 3):
        y = 30 + jround(math.sin(i * 0.3) * 1.5)
        for dx in (0, 1):
            for dy in (0, 1):
                out[(i + dx, y + dy)] = solid("#8a7da8")
        out[(i + 1, y)] = solid("#30264a")
    return out


def shadow_layer():
    """The floor shadow under the book: one row, centre at x 0."""
    return {(i, 0): (0, 0, 0, int(round(0.35 * (1 - abs(i) / 19) * 255))) for i in range(-18, 19)}


def halo_layer():
    """A dithered glow round the book: an ellipse band, ordered 4 x 4 dither in two alpha steps; origin = its centre."""
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    rx, ry = 29, 35
    out = {}
    for y in range(-ry - 4, ry + 5):
        for x in range(-rx - 4, rx + 5):
            d = math.hypot(x / rx, y / ry)
            if d > 1.12:
                continue
            k = (1 - (d - 1) / 0.12) if d > 1 else max(0.0, (d - 0.72) / 0.28) ** 1.6 * 0.8
            if k > 0 and k * 16 > bayer[y & 3][x & 3] + 0.5:
                out[(x, y)] = (255, 255, 255, 87 if k > 0.55 else 51)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Crystals (9 x 14, origin = top left)
# ---------------------------------------------------------------------------------------------------------------------

CRY = ["....1....", "...121...", "..12221..", "..12231..", ".1222331.", ".1222331.", "122223331", "122223331",
       ".1222331.", ".1222331.", "..12231..", "..12231..", "...121...", "....1...."]
CRY_PAL = {
    "lit": ("#2a0b44", "#e6b3ff", "#b45cff", "#6a1fb8"), "amber": ("#3a1c04", "#fff0c0", "#ffb648", "#c06a10"),
    "white": ("#ffffff", "#ffffff", "#ffffff", "#ffffff"), "empty": ("#5a3d8a", "#1a0d2e", "#140a24", "#100820"),
    "q": ("#4a4066", "#1a1428", "#16111f", "#120e1a"),
}


def crystal_layer(kind):
    pal = CRY_PAL[kind]
    out = {(x, y): solid(pal[int(ch)]) for y, row in enumerate(CRY) for x, ch in enumerate(row) if ch != "."}
    if kind == "lit":
        out[(3, 4)] = out[(3, 5)] = solid("#ffffff")
    if kind == "q":
        for (x, y) in ((3, 4), (4, 4), (5, 5), (4, 6), (4, 8)):
            out[(x, y)] = solid("#7a6aa8")
    return out


DROP = [".X.", "XXX", "XYX", ".Z."]


def drop_layer():
    pal = {"X": solid("#d0103a"), "Y": solid("#ff7aa8"), "Z": solid("#8a0a26")}
    return {(x - 1, y): pal[ch] for y, row in enumerate(DROP) for x, ch in enumerate(row) if ch != "."}


# ---------------------------------------------------------------------------------------------------------------------
# Bolts (horns to gem, book px) and the rune ring (origin = its centre)
# ---------------------------------------------------------------------------------------------------------------------


def line(p0, p1):
    (x0, y0), (x1, y1) = p0, p1
    pts, dx, dy = set(), abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        pts.add((x0, y0))
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


def zap_layer(seed):
    rng = random.Random(seed)
    out = {}
    for (hx, hy) in HORNS:
        x0, y0, x1, y1 = hx, hy, GEM_C[0], GEM_C[1] - 3
        ln = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
        n = 6
        path = []
        for t in range(n + 1):
            j = 0 if t in (0, n) else rng.uniform(-4, 4)
            path.append((jround(x0 + (x1 - x0) * t / n + nx * j), jround(y0 + (y1 - y0) * t / n + ny * j)))
        for a, b in zip(path, path[1:]):
            for p in line(a, b):
                out[p] = W1
    return out


def ring_layer(frame):
    """The binding rune ring: a dotted ellipse with twelve dashes riding it, turned by frame / RING_FRAMES of a dash gap."""
    out = {}
    for i in range(40):
        t = i / 40 * 2 * math.pi
        out[(jround(math.cos(t) * (RING_RX + 3)), jround(math.sin(t) * (RING_RY + 1)))] = (255, 255, 255, 128)
    for i in range(12):
        t = (i + frame / RING_FRAMES) / 12 * 2 * math.pi
        x, y = jround(math.cos(t) * RING_RX), jround(math.sin(t) * RING_RY)
        a = 0.5 + 0.5 * math.sin(t)
        for dx in (0, 1):
            out[(x + dx, y)] = (255, 255, 255, int(round((0.35 + 0.65 * a) * 255)))
    return out


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
# Packing and output
# ---------------------------------------------------------------------------------------------------------------------


class Sprite:
    def __init__(self, name, layer, origin_box=False):
        self.name = name
        if origin_box:                  # keep (0, 0) as the top left even where it is empty (the book looks share one box)
            self.x0, self.y0 = 0, 0
            self.w, self.h = BOOK_W, BOOK_H
        else:
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


def lit_box_tga(book):
    s = Sprite("box", {(x + BOOK_IN_BOX[0], y + BOOK_IN_BOX[1]): c for (x, y), c in book.items()})
    s.x0 = s.y0 = s.tx = s.ty = 0
    size = (BOX * SCALE, BOX * SCALE)
    return tga_bytes(size, raster(size, [s]))


ATLAS_SIZES = [(256, 256), (512, 256), (512, 512), (1024, 512), (1024, 1024)]


def build():
    book = book_layer()
    sprites = []

    def add(name, layer, box=False):
        sprites.append(Sprite(name, layer, box))

    add("book_dark", dark_of(book), True)
    add("book_grey", grey_of(book), True)
    add("book_rim", edge_of(book), True)
    add("book_white", mask_of(book), True)
    add("book_gem", gem_mask(book))
    add("chain", chain_layer())
    add("shadow", shadow_layer())
    add("halo", halo_layer())
    for kind in CRY_PAL:
        add(f"crys_{kind}", crystal_layer(kind))
    add("drop", drop_layer())
    for k in range(ZAPS):
        add(f"zap{k}", zap_layer(k + 1))
    for k in range(RING_FRAMES):
        add(f"ring{k}", ring_layer(k))
    for ch in FONT:
        add(glyph_name(ch), font_layer(ch))
    for size in ATLAS_SIZES:
        if pack(sprites, size):
            return book, sprites, size
    raise SystemExit("the sprites do not fit a 1024 x 1024 atlas")


def lua_manifest(sprites, size):
    glyph_w = {ch: len(FONT[ch][0]) for ch in FONT}
    lines = [
        "-- Forever STUwave: the Warlock Gunsight module's sprite manifest.",
        "-- GENERATED by tools/assets/generate_warlock_grimoire.py; do not edit (gunsightwarlock-harness.py checks it).",
        "-- sprite = { tx, ty, w, h, ox, oy }: texel rect in the atlas, size in sprite px, and the sprite's origin",
        "-- (the point the module places) as an offset from the sprite's top left, in sprite px.",
        "",
        "local _, FS = ...",
        "",
        "FS.WarlockArt = {",
        f"    SCALE = {SCALE},",
        f"    BOOK_W = {BOOK_W}, BOOK_H = {BOOK_H}, BOX = {BOX}, BOX_X = {BOOK_IN_BOX[0]}, BOX_Y = {BOOK_IN_BOX[1]},",
        f"    GEM_X = {GEM_C[0]}, GEM_Y = {GEM_C[1]}, EYE1_X = {EYES[0][0]}, EYE2_X = {EYES[1][0]}, EYE_Y = {EYES[0][1]},",
        f"    CRY_W = {CRY_W}, CRY_H = {CRY_H}, ZAPS = {ZAPS}, RING_FRAMES = {RING_FRAMES},",
        f"    ATLAS = {{ file = \"warlock_grimoire\", w = {size[0]}, h = {size[1]} }},",
        "    LIT = \"warlock_grimoire_lit\",",
        "    GLYPH_W = { " + ", ".join(f'["{ch}"] = {w}' for ch, w in sorted(glyph_w.items())) + " },",
        "    sprites = {",
    ]
    for s in sorted(sprites, key=lambda s: s.name):
        lines.append(f'        ["{s.name}"] = {{ {s.tx}, {s.ty}, {s.w}, {s.h}, {-s.x0}, {-s.y0} }},')
    lines += ["    },", "}", ""]
    return "\n".join(lines)


def main():
    root = HERE.parent.parent
    out = Path(os.environ.get("FS_ASSET_OUTPUT_DIR", root / "forever-stuwave" / "Media" / "Textures"))
    default_lua = (out / "WarlockArt.lua" if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else root / "forever-stuwave" / "Modules" / "CombatHud" / "WarlockArt.lua")
    lua = Path(os.environ.get("FS_ART_LUA_OUTPUT", default_lua))
    book, sprites, size = build()
    out.mkdir(parents=True, exist_ok=True)
    (out / "warlock_grimoire.tga").write_bytes(tga_bytes(size, raster(size, sprites)))
    (out / "warlock_grimoire_lit.tga").write_bytes(lit_box_tga(book))
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(sprites, size))
    print(f"wrote {out}/warlock_grimoire.tga {size}, warlock_grimoire_lit.tga, {lua}")


if __name__ == "__main__":
    main()
