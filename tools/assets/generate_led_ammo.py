#!/usr/bin/env python3
"""Generates led_ammo.tga and led_ammo_glow.tga: the art of the ammo tab's LED counter (AmmoTab.lua).

The design mockup ammo-tab-led-arrow-2026-11-20 (look B, LED COUNTER, with the BROADHEAD arrow) draws a tall seven segment
readout of four digits and a fifth cell holding a pixel arrow or bullet. This is that art on whole texels.

led_ammo.tga is a 128x64 atlas of sixteen 16x32 slots (8 across, 2 down, slot n at column n % 8, row n // 8). A cell is
9 x 18 texels at the slot's top-left corner. Slots 0..6 hold the seven segments a, b, c, d, e, f, g of a digit, in
SEGMENT_ORDER; slot 7 is the broadhead arrow and slot 8 the bullet (each a whole glyph, lit as one texture); slots 9..15
are empty. Everything is pure white, alpha 255 or 0, no anti-aliasing, and the seven segments are DISJOINT (the corners
belong to no segment), so a segment tinted at a partial alpha never double composites. The tab draws one texture per
segment or glyph, one texel to n physical pixels (never scaled fractionally), lit or ghosted by SetVertexColor alone.

led_ammo_glow.tga is the same atlas blurred (a Gaussian of sigma 1 texel, white, all of it in the alpha), each slot's art
shifted by a two texel margin: the 9 x 18 art sits at (2, 2) and the glow fills the slot's 13 x 22 top left rect, so the tab
seats it two texels up and left of the cell, the way led_segment_glow.tga sits under the mana regen readout.

The bitmaps below are the mockup's (GL.bh and GL.bullet, "#" lit). Pure stdlib, the same TGA writer as the other
generators: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top to bottom.

    python generate_led_ammo.py
"""

import math
import os
import struct

CELL_W, CELL_H = 9, 18
SLOT_W, SLOT_H = 16, 32
ATLAS_W, ATLAS_H = 128, 64
GLOW_MARGIN = 2
GLOW_SIGMA = 1.0

SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g")
ARROW_SLOT, BULLET_SLOT = 7, 8


def _rect(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


# a seven segment digit on a 9 x 18 cell, strokes two texels thick, the corners left dark
SEGMENTS = {
    "a": _rect(2, 0, 6, 1),
    "b": _rect(7, 2, 8, 7),
    "c": _rect(7, 10, 8, 15),
    "d": _rect(2, 16, 6, 17),
    "e": _rect(0, 10, 1, 15),
    "f": _rect(0, 2, 1, 7),
    "g": _rect(2, 8, 6, 9),
}

ARROW = (
    "....#....",
    "...###...",
    "..#####..",
    ".#######.",
    "#########",
    "....#....",
    "....#....",
    "....#....",
    "....#....",
    "....#....",
    "....#....",
    "....#....",
    "...###...",
    "..#.#.#..",
    ".#..#..#.",
    "...###...",
    "..#.#.#..",
    ".#..#..#.",
)

BULLET = (
    "....#....",
    "...###...",
    "...###...",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    "..#####..",
    ".#######.",
    ".#.....#.",
    ".#######.",
    ".........",
)


def _bitmap(rows):
    assert len(rows) == CELL_H and all(len(r) == CELL_W for r in rows)
    return {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "#"}


def shapes():
    """Slot -> set of (x, y) texels of the 9 x 18 cell."""
    out = {n: SEGMENTS[name] for n, name in enumerate(SEGMENT_ORDER)}
    out[ARROW_SLOT] = _bitmap(ARROW)
    out[BULLET_SLOT] = _bitmap(BULLET)
    return out


def _origin(slot):
    return (slot % 8) * SLOT_W, (slot // 8) * SLOT_H


def build_atlas():
    rows = [[(255, 255, 255, 0)] * ATLAS_W for _ in range(ATLAS_H)]
    seen = set()
    for slot, texels in shapes().items():
        ox, oy = _origin(slot)
        for x, y in texels:
            assert 0 <= x < CELL_W and 0 <= y < CELL_H, (slot, x, y)
            if slot < len(SEGMENT_ORDER):
                assert (x, y) not in seen, f"segment {SEGMENT_ORDER[slot]} overlaps another at {x},{y}"
                seen.add((x, y))
            rows[oy + y][ox + x] = (255, 255, 255, 255)
    return rows


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _blur(mask, sigma, w, h):
    radius = int(math.ceil(sigma * 3.5))
    kernel = [_phi((d + 0.5) / sigma) - _phi((d - 0.5) / sigma) for d in range(-radius, radius + 1)]
    horizontal = [[sum(kernel[k] * (mask[y][x + k - radius] if 0 <= x + k - radius < w else 0.0)
                       for k in range(len(kernel))) for x in range(w)] for y in range(h)]
    return [[sum(kernel[k] * (horizontal[y + k - radius][x] if 0 <= y + k - radius < h else 0.0)
                 for k in range(len(kernel))) for x in range(w)] for y in range(h)]


def build_glow():
    rows = [[(255, 255, 255, 0)] * ATLAS_W for _ in range(ATLAS_H)]
    gw, gh = CELL_W + 2 * GLOW_MARGIN, CELL_H + 2 * GLOW_MARGIN
    for slot, texels in shapes().items():
        ox, oy = _origin(slot)
        mask = [[0.0] * SLOT_W for _ in range(SLOT_H)]
        for x, y in texels:
            mask[y + GLOW_MARGIN][x + GLOW_MARGIN] = 1.0
        blurred = _blur(mask, GLOW_SIGMA, SLOT_W, SLOT_H)
        for y in range(SLOT_H):
            for x in range(SLOT_W):
                alpha = int(round(blurred[y][x] * 255)) if (x < gw and y < gh) else 0
                rows[oy + y][ox + x] = (255, 255, 255, alpha)
    return rows


def write_tga(path, rows):
    height, width = len(rows), len(rows[0])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    payload = bytearray()
    for row in rows:
        for r, g, b, a in row:
            payload += bytes((b, g, r, a))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(payload)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def main():
    out = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write_tga(os.path.join(out, "led_ammo.tga"), build_atlas())
    write_tga(os.path.join(out, "led_ammo_glow.tga"), build_glow())


if __name__ == "__main__":
    main()
