#!/usr/bin/env python3
"""Generates the profession skill up chips (Services.lua, the recipe list of the profession window).

    skillup_chips.tga   64 x 32  three chips side by side, chip n (one, two or three chevrons) at x = 16 * (n - 1), y = 0

A chip is a white mask, tinted by the tier colour (orange three chevrons, yellow two, green one): a 1 px rim, a dark face (the ink
colour baked in, so the tint leaves it near black) and the chevrons. One chevron is 7 columns of 1 x 2 px steps, apex at the top
(5 px tall); chevrons stack 4 px apart, which leaves a 2 px gap. The chip is 11 px wide and 9, 13 or 17 px tall, so the tallest
fits the 19 px inside of a recipe card with a px to spare.

The whole chip is ONE texture drawn at one texel per physical px. It used to be a box of four edges and up to 27 one px
rectangles; on a row that sat half a pixel off the grid each of those snapped on its own, so 1 px steps came out 0 or 2 px wide
and the chevrons broke up into a checkerboard. One quad snaps as a unit and keeps its shape.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python3 tools/assets/generate_skillup_chips.py      (FS_ASSET_OUTPUT_DIR overrides the .tga directory)
"""

import os
import struct

ATLAS_W, ATLAS_H = 64, 32
SLOT = 16
CHIP_W = 11
STEP_W, STEP_H, PITCH = 7, 5, 4
EDGE, PAD = 1, 1
INK = (7, 3, 14)
WHITE = (255, 255, 255)


def chip_h(n):
    return 2 * (EDGE + PAD) + STEP_H + PITCH * (n - 1)


def chip(n):
    """{(x, y): (r, g, b)} for chip n, opaque everywhere inside its 11 x chip_h(n) box."""
    w, h = CHIP_W, chip_h(n)
    px = {}
    for y in range(h):
        for x in range(w):
            rim = x < EDGE or y < EDGE or x >= w - EDGE or y >= h - EDGE
            px[(x, y)] = WHITE if rim else INK
    x0 = (w - STEP_W) // 2
    y0 = EDGE + PAD
    apex = (STEP_W - 1) // 2
    for k in range(n):
        for c in range(STEP_W):
            top = y0 + PITCH * k + abs(c - apex)
            px[(x0 + c, top)] = WHITE
            px[(x0 + c, top + 1)] = WHITE
    return px


def atlas():
    rows = [[(0, 0, 0, 0)] * ATLAS_W for _ in range(ATLAS_H)]
    for n in (1, 2, 3):
        for (x, y), rgb in chip(n).items():
            rows[y][SLOT * (n - 1) + x] = (*rgb, 255)
    return rows


def write_tga(path, rows):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, ATLAS_W, ATLAS_H, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        for row in rows:
            for r, g, b, a in row:
                fh.write(bytes((b, g, r, a)))


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    out = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "skillup_chips.tga")
    write_tga(path, atlas())
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
