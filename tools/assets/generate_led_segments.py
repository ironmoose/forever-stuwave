#!/usr/bin/env python3
"""Generates led_segments.tga and led_glow.tga: the art of the five second rule tab's LED readout.

led_segments.tga is a 64x64 atlas of sixteen 16x16 slots (4 across, 4 down, slot n at column n % 4, row n // 4).
Slots 0..13 hold one of the fourteen segments of a 14 segment cell, in SEGMENT_ORDER; slots 14 and 15 are empty.
A cell is 10 x 12 texels. The segments are drawn on that whole pixel grid in pure white, alpha 255 or 0, no
anti-aliasing, and they are DISJOINT: no texel belongs to two segments (the four diagonals own the four corner
blocks), so a segment tinted with SetVertexColor at a partial alpha never double composites into a bright speck.
The tab draws one texture per segment, 1 texel per physical pixel (never scaled fractionally), lit or unlit
by SetVertexColor alone. The 10 x 12 art sits at the slot's top-left corner; the rest of the slot is clear.

led_glow.tga is a 64x32 soft glow, white with all the shape in the alpha channel: a filled bar with a quadratic
falloff to every side. It sits behind the readout as its own texture (blend ADD) and is stretched to the glow
rect; the hard edged segments never carry a blur themselves.

The segment rows below are [x, y, width] runs one texel tall; mockups/five-second-rule-compact-2026-10-14.html
(SEGS) draws the same table. Pure stdlib, matching the other generators here: 18-byte header, image type 2,
descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top to bottom.

    python generate_led_segments.py
"""

import math
import os
import struct

CELL_W, CELL_H = 10, 12
SLOT = 16
ATLAS = 64

SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m")


def _column(x, y0, y1, width=2):
    return [[x, y, width] for y in range(y0, y1 + 1)]


SEGMENTS = {
    "a": [[2, 0, 6], [2, 1, 6]],
    "d": [[2, 10, 6], [2, 11, 6]],
    "f": _column(0, 2, 5),
    "b": _column(8, 2, 5),
    "e": _column(0, 6, 9),
    "c": _column(8, 6, 9),
    "g1": [[2, 5, 3], [2, 6, 3]],
    "g2": [[5, 5, 3], [5, 6, 3]],
    "i": _column(4, 2, 4),
    "l": _column(4, 7, 9),
    "h": [[0, 0, 2], [0, 1, 2], [2, 2, 1], [2, 3, 2], [3, 4, 1]],
    "j": [[8, 0, 2], [8, 1, 2], [7, 2, 1], [6, 3, 2], [6, 4, 1]],
    "k": [[3, 7, 1], [2, 8, 2], [2, 9, 1], [0, 10, 2], [0, 11, 2]],
    "m": [[6, 7, 1], [6, 8, 2], [7, 9, 1], [8, 10, 2], [8, 11, 2]],
}

GLOW_W, GLOW_H = 64, 32
GLOW_INNER_W, GLOW_INNER_H = 36, 8      # the solid core, centred; the falloff spills outside it
GLOW_FALL_X, GLOW_FALL_Y = 12.0, 10.0   # falloff distance in texels, horizontal and vertical
SUPERSAMPLE = 3


def build_atlas():
    """The atlas as a list of rows of (r, g, b, a) tuples."""
    rows = [[(255, 255, 255, 0)] * ATLAS for _ in range(ATLAS)]
    for n, name in enumerate(SEGMENT_ORDER):
        ox, oy = (n % 4) * SLOT, (n // 4) * SLOT
        for x, y, width in SEGMENTS[name]:
            for q in range(width):
                assert 0 <= x + q < CELL_W and 0 <= y < CELL_H, (name, x, y, width)
                assert rows[oy + y][ox + x + q][3] == 0, f"segment {name} overlaps another at {x + q},{y}"
                rows[oy + y][ox + x + q] = (255, 255, 255, 255)
    return rows


def _glow_alpha(px, py):
    left = (GLOW_W - GLOW_INNER_W) / 2
    top = (GLOW_H - GLOW_INNER_H) / 2
    dx = max(left - px, px - (left + GLOW_INNER_W), 0.0) / GLOW_FALL_X
    dy = max(top - py, py - (top + GLOW_INNER_H), 0.0) / GLOW_FALL_Y
    d = math.hypot(dx, dy)
    if d >= 1.0:
        return 0.0
    return (1.0 - d) ** 2


def build_glow():
    rows = []
    for y in range(GLOW_H):
        row = []
        for x in range(GLOW_W):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    total += _glow_alpha(x + (sx + 0.5) / SUPERSAMPLE, y + (sy + 0.5) / SUPERSAMPLE)
            row.append((255, 255, 255, int(round(total / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
        rows.append(row)
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
    write_tga(os.path.join(out, "led_segments.tga"), build_atlas())
    write_tga(os.path.join(out, "led_glow.tga"), build_glow())


if __name__ == "__main__":
    main()
