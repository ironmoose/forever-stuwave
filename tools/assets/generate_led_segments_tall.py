#!/usr/bin/env python3
"""Generates led_segments_tall.tga and led_segment_glow_tall.tga: the ammo tab's tall LED readout.

The same fourteen segment cell as the mana regen module's led_segments.tga (generate_led_segments.py), redrawn twice as
tall: a cell is 11 x 22 texels. led_segments_tall.tga is a 128x128 atlas of sixteen 32x32 slots (4 across, 4 down, slot n
at column n % 4, row n // 4); slots 0..13 hold one segment each in SEGMENT_ORDER, at the slot's top left; slots 14 and 15
are empty. Pure white, alpha 255 or 0, no anti-aliasing, and the segments are DISJOINT (no texel belongs to two), so a
segment tinted at a partial alpha never double composites. The tab draws one texture per segment, n physical pixels a
texel, lit or unlit by SetVertexColor alone.

led_segment_glow_tall.tga is the same atlas blurred (a Gaussian of sigma 1 texel, white, the shape in the alpha), with a
two texel margin: each segment's art sits at (2, 2) of its slot and the glow fills the slot's 15 x 26 top left rect, so the
tab seats it two texels up and left of the cell. A blur keeps the mass, so a cell glows only where its lit segments are.

The segments are the mockup's (ammo-tab-glyph-right-2026-11-20, look B): two texel strokes for the bars, one texel steps
for the four diagonals and the two centre verticals. Pure stdlib, like the other generators here: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top to bottom.

    python generate_led_segments_tall.py
"""

import math
import os
import struct

CELL_W, CELL_H = 11, 22
SLOT = 32
ATLAS = 128
GLOW_MARGIN = 2
GLOW_W, GLOW_H = CELL_W + 2 * GLOW_MARGIN, CELL_H + 2 * GLOW_MARGIN
GLOW_SIGMA = 1.0

SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m")


def _box(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def _diagonal(x0, x1, y0, y1):
    """One texel per row from (x0, y0) to (x1, y1), rounded half up."""
    return {(int(math.floor(x0 + (x1 - x0) * (y - y0) / (y1 - y0) + 0.5)), y) for y in range(y0, y1 + 1)}


SEGMENTS = {
    "a": _box(2, 0, 8, 1),
    "d": _box(2, 20, 8, 21),
    "f": _box(0, 2, 1, 9),
    "e": _box(0, 12, 1, 19),
    "b": _box(9, 2, 10, 9),
    "c": _box(9, 12, 10, 19),
    "g1": _box(2, 10, 4, 11),
    "g2": _box(6, 10, 8, 11),
    "i": _box(5, 3, 5, 8),
    "l": _box(5, 13, 5, 18),
    "h": _diagonal(2, 4, 2, 9),
    "j": _diagonal(8, 6, 2, 9),
    "k": _diagonal(4, 2, 12, 19),
    "m": _diagonal(6, 8, 12, 19),
}


def build_atlas():
    rows = [[(255, 255, 255, 0)] * ATLAS for _ in range(ATLAS)]
    for n, name in enumerate(SEGMENT_ORDER):
        ox, oy = (n % 4) * SLOT, (n // 4) * SLOT
        for x, y in SEGMENTS[name]:
            assert 0 <= x < CELL_W and 0 <= y < CELL_H, (name, x, y)
            rows[oy + y][ox + x] = (255, 255, 255, 255)
    seen = set()
    for name in SEGMENT_ORDER:
        assert not (seen & SEGMENTS[name]), f"segment {name} overlaps another"
        seen |= SEGMENTS[name]
    return rows


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _blur(mask, sigma, size):
    radius = int(math.ceil(sigma * 3.5))
    kernel = [_phi((d + 0.5) / sigma) - _phi((d - 0.5) / sigma) for d in range(-radius, radius + 1)]
    horizontal = [[sum(kernel[k] * (mask[y][x + k - radius] if 0 <= x + k - radius < size else 0.0)
                       for k in range(len(kernel))) for x in range(size)] for y in range(size)]
    return [[sum(kernel[k] * (horizontal[y + k - radius][x] if 0 <= y + k - radius < size else 0.0)
                 for k in range(len(kernel))) for x in range(size)] for y in range(size)]


def build_glow():
    rows = [[(255, 255, 255, 0)] * ATLAS for _ in range(ATLAS)]
    for n, name in enumerate(SEGMENT_ORDER):
        ox, oy = (n % 4) * SLOT, (n // 4) * SLOT
        mask = [[0.0] * SLOT for _ in range(SLOT)]
        for x, y in SEGMENTS[name]:
            mask[y + GLOW_MARGIN][x + GLOW_MARGIN] = 1.0
        blurred = _blur(mask, GLOW_SIGMA, SLOT)
        for y in range(GLOW_H):
            for x in range(GLOW_W):
                rows[oy + y][ox + x] = (255, 255, 255, int(round(blurred[y][x] * 255)))
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
    write_tga(os.path.join(out, "led_segments_tall.tga"), build_atlas())
    write_tga(os.path.join(out, "led_segment_glow_tall.tga"), build_glow())


if __name__ == "__main__":
    main()
