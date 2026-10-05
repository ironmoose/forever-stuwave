#!/usr/bin/env python3
"""Generates glow_edge.tga: a 128x128 uncompressed 32-bit TGA, solid white
RGB, with a 1D QUADRATIC EASE-OUT gradient alpha -- full brightness (255) at
the top row (y=0), falling off toward the bottom row (y=127) where it hits
exactly 0, with the falloff shape concentrating brightness near the bright
edge and softening toward the far edge (an eased curve, not a straight
ramp), uniform across every column. This is the panel's OUTWARD border-following halo: four
copies of this strip are anchored one per edge (see AddOuterGlow in
UnitFrames.lua) with the bright end touching the frame's border and the
faded end pointing away from it, using SetTexCoord to rotate/flip the
gradient per edge instead of baking four separate textures.

Pure stdlib, no dependencies. Run directly to (re)write glow_edge.tga next
to this script:

    python3 generate_glow_edge.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import os
import struct

SIZE = 128


def build_alpha_grid():
    """Alpha depends only on row: 255 at y=0, quadratic ease-out down to 0
    at y=SIZE-1, identical across every column in that row. The fraction
    f = 1.0 - (y / (SIZE-1)) (1.0 at the bright row, 0.0 at the far row)
    is squared (a = f*f) before scaling to 255, so brightness stays
    concentrated near the bright edge (y=0) and softly fades out toward
    the far edge instead of dropping off in an even ramp."""
    grid = []
    for y in range(SIZE):
        f = 1.0 - (y / (SIZE - 1))
        a = f * f
        row_alpha = round(255 * a)
        grid.append([row_alpha] * SIZE)
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
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media")), "glow_edge.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
