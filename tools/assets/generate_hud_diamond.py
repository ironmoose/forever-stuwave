#!/usr/bin/env python3
"""Generates hud_diamond.tga: the soul shard diamond of the combat HUD.

A white, anti-aliased rhombus filling a 32 x 32 texture edge to edge (points touch the
middle of each side). CombatHud.lua stretches it to 10 x 12 and tints it with
SetVertexColor; the mockup draws the same shape with a CSS clip-path polygon
(50% 0, 100% 50%, 50% 100%, 0 50%).

Pure stdlib, matching the other generators here. Output: 18-byte header, image type 2,
descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_hud_diamond.py
"""

import os
import struct

SIZE = 32
SUPERSAMPLE = 6


def _inside(px, py):
    """|x - c| + |y - c| <= c, the rhombus through the four side midpoints."""
    c = SIZE / 2.0
    return abs(px - c) + abs(py - c) <= c


def _coverage(x, y):
    total = 0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            if _inside(px, py):
                total += 1
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def main():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(x, y) * 255))))
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "hud_diamond.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
