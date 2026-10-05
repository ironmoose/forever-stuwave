#!/usr/bin/env python3
"""Generates border_rail.tga: a 4x128 uncompressed 32-bit TGA, solid white
RGB, with a 1D LINEAR vertical alpha gradient -- alpha 0.31 at the top row
(y=0) rising to 1.0 at the bottom row (y=127), uniform across every column.

This is the left/right edge of the panel border (AddGradientBorder in
UnitFrames.lua). It replaces the old stack of 16 fixed-height ColorTexture
segments, which were sized to a hardcoded PANEL_HEIGHT and therefore
overhung the bottom by one bar whenever the panel shrank to hide the power
bar (any no-power target). A single texture anchored TOPLEFT+BOTTOMLEFT
stretches to the panel's CURRENT height, so the rail always matches the
frame no matter which height it is at. The border color is applied at draw
time via SetVertexColor; this texture only carries the vertical alpha ramp
(SetGradient does not render on the 2.5.6 client, which is why the ramp is
baked here).

Matches the old segment ramp: alphaTop = 0.31 at the top, full alpha at the
bottom (the border reads solid along the bottom edge, fading up).

Pure stdlib, no dependencies. Run directly to (re)write border_rail.tga next
to this script:

    python3 generate_border_rail.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import os
import struct

WIDTH = 4
HEIGHT = 128
ALPHA_TOP = 0.31  # matches AddGradientBorder's alphaTop = a * 0.31


def build_alpha_grid():
    """Alpha depends only on row: ALPHA_TOP at y=0 rising linearly to 1.0 at
    y=HEIGHT-1, identical across every column in that row."""
    grid = []
    for y in range(HEIGHT):
        f = y / (HEIGHT - 1)  # 0.0 at top, 1.0 at bottom
        a = ALPHA_TOP + (1.0 - ALPHA_TOP) * f
        grid.append([round(255 * a)] * WIDTH)
    return grid


def write_tga(path, alpha_grid):
    header = bytes([
        0,      # id length
        0,      # color map type
        2,      # image type: uncompressed truecolor
        0, 0, 0, 0, 0,  # color map spec (unused)
    ]) + struct.pack("<HHHH", 0, 0, WIDTH, HEIGHT) + bytes([
        32,     # bits per pixel
        0x28,   # image descriptor: top-left origin, 8 alpha bits
    ])

    pixels = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            alpha = alpha_grid[y][x]
            pixels += bytes([255, 255, 255, alpha])  # BGRA, solid white

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)


if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "border_rail.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
