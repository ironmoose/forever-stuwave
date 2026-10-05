#!/usr/bin/env python3
"""Generates hatch.tga: a 16x16 uncompressed 32-bit TGA, solid white RGB,
designed to TILE. Alpha depends only on `(x + y) % PERIOD`, which gives a
45-degree diagonal stripe pattern that is periodic in x+y -- it tiles
perfectly on ANY power-of-two size, no matter how the diagonal happens to
land at the tile boundary, unlike a stripe defined from a fixed start point
would. UnitFrames.lua's absorb/shield overlay tiles this (SetHorizTile +
SetVertTile on the StatusBar's fill texture, Theme.lua's HATCH_TEXTURE) to
get Parker's mockup-review ask: "HATCHED DIAGONAL STRIPES (light gray/white
stripes on transparent, roughly 45 degrees, about 3-4px period)" in place of
the old flat translucent-white shield tint.

Pure stdlib, no dependencies. Run directly to (re)write hatch.tga next to
this script:

    python3 generate_hatch.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import os
import struct

WIDTH = 16
HEIGHT = 16
PERIOD = 4        # stripe repeat period in pixels (Parker's ask: ~3-4px)
STRIPE_WIDTH = 2   # of PERIOD pixels, how many are opaque "stripe" pixels
STRIPE_ALPHA = 0.85  # light gray/white, not fully opaque


def build_alpha_grid():
    """Alpha depends only on (x + y) % PERIOD: STRIPE_ALPHA for the first
    STRIPE_WIDTH pixels of each period, 0 for the rest (the transparent gap).
    Periodic in x+y, so this is a clean 45-degree diagonal hatch that tiles
    seamlessly on any size -- no need to solve for a period that "fits" the
    tile dimensions."""
    grid = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            stripe = (x + y) % PERIOD < STRIPE_WIDTH
            row.append(round(255 * STRIPE_ALPHA) if stripe else 0)
        grid.append(row)
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
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hatch.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
