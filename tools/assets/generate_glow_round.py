#!/usr/bin/env python3
"""Generates glow_round.tga: a 128x128 uncompressed 32-bit TGA, solid white
RGB, with a RADIAL soft glow alpha profile -- full brightness at the center,
raised-cosine falloff out to exactly 0 at the unit circle (r>=1), and exactly
0 at every corner (r=sqrt(2) > 1 there). Companion to generate_glow_edge.py:
this one is for small ROUND elements (class icon, level badge) where a
rectangular glow (see generate_glow.py) puts an ugly hard-edged box around a
circular icon -- AddSoftGlow (UnitFrames.lua) stretches this texture with ADD
blend and a negative inset so a round element gets a round halo instead.

Pure stdlib, no dependencies. Run directly to (re)write glow_round.tga next
to this script:

    python3 generate_glow_round.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import math
import os
import struct

SIZE = 128
CORE_RADIUS = 0.15  # r <= this stays at full brightness (1.0)


def _radius(x, y):
    # Map pixel index to [-1, 1] per axis, endpoint-inclusive (x=0 -> -1.0,
    # x=SIZE-1 -> +1.0), same convention as generate_glow.py's edge distance.
    # A corner pixel then has nx=ny=+-1 so r = sqrt(2) > 1, which the falloff
    # below already maps to exactly 0 -- no special-casing needed.
    nx = x / (SIZE - 1) * 2 - 1
    ny = y / (SIZE - 1) * 2 - 1
    return math.sqrt(nx * nx + ny * ny)


def build_alpha_grid():
    """Raised-cosine radial falloff: alpha=1 for r<=CORE_RADIUS, a smooth
    half-cosine ramp down to alpha=0 at r=1, and alpha=0 for every r>=1
    (which includes all four corners, since a square texture's corners sit
    outside the unit circle inscribed in it)."""
    grid = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            r = _radius(x, y)
            if r <= CORE_RADIUS:
                a = 1.0
            elif r < 1.0:
                a = 0.5 * (1.0 + math.cos(math.pi * (r - CORE_RADIUS) / (1.0 - CORE_RADIUS)))
            else:
                a = 0.0
            row.append(round(255 * a))
        grid.append(row)
    return grid


def write_tga(path, alpha_grid):
    header = bytes([
        0,      # id length
        0,      # color map type
        2,      # image type: uncompressed truecolor
        0, 0, 0, 0, 0,  # color map spec (unused)
    ]) + struct.pack("<HHHH", 0, 0, SIZE, SIZE) + bytes([
        32,     # bits per pixel
        0x28,   # image descriptor: top-left origin, 8 alpha bits
    ])

    pixels = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = alpha_grid[y][x]
            pixels += bytes([255, 255, 255, alpha])  # BGRA, solid white

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)


if __name__ == "__main__":
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media")), "glow_round.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
