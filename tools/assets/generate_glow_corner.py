#!/usr/bin/env python3
"""Generates glow_corner.tga: a 128x128 uncompressed 32-bit TGA, solid white
RGB, with a RADIAL QUADRATIC falloff alpha -- full brightness (1.0) at the
center, alpha = (1 - r)**2 out to exactly 0 at the unit circle (r >= 1), and
0 at every corner (r = sqrt(2) > 1 there).

This is the corner piece of the panel's outward border halo (AddOuterGlow in
UnitFrames.lua). It exists as a SEPARATE texture from glow_round.tga on
purpose: the four edge strips (glow_edge.tga) fade with a pure quadratic
profile a = f*f, so the corner quads must use the SAME quadratic radial
profile for the halo field to stay continuous across every edge/corner seam.
glow_round.tga uses a raised-cosine falloff with a flat bright core
(CORE_RADIUS), which mismatches the edges and makes each corner read as a
bright radial blob with a darker diagonal valley between the two lit edges
(an "X" artifact). glow_round stays in use for genuinely round elements
(the class icon), where its softer core looks better and there is no edge
strip to match.

Along any axis through the center, r equals the normalized perpendicular
distance from the border, so alpha here equals the edge strip's alpha at the
same distance -- the seam where a corner meets a strip is C0-continuous. Along
the 45-degree diagonal the alpha falls off faster (reaching 0 at r=1, i.e.
distance size/sqrt(2)), which is exactly how a CSS box-shadow rounds a corner.

Pure stdlib, no dependencies. Run directly to (re)write glow_corner.tga next
to this script:

    python3 generate_glow_corner.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import math
import os
import struct

SIZE = 128


def _radius(x, y):
    # Map pixel index to [-1, 1] per axis, endpoint-inclusive (x=0 -> -1.0,
    # x=SIZE-1 -> +1.0). A corner pixel then has nx=ny=+-1 so r = sqrt(2) > 1,
    # which the falloff below maps to exactly 0 -- no special-casing needed.
    nx = x / (SIZE - 1) * 2 - 1
    ny = y / (SIZE - 1) * 2 - 1
    return math.sqrt(nx * nx + ny * ny)


def build_alpha_grid():
    """Quadratic radial falloff: alpha = (1 - r)**2 for r < 1, else 0. Same
    quadratic shape as generate_glow_edge.py's 1D strip falloff, so the corner
    matches the edges along every axis and the halo field is seam-continuous."""
    grid = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            r = _radius(x, y)
            if r < 1.0:
                f = 1.0 - r
                a = f * f
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
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "glow_corner.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
