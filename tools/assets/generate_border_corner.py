#!/usr/bin/env python3
"""Generates border_corner.tga: a 64x64 uncompressed 32-bit TGA, solid white
RGB, whose ALPHA is a quarter-ring stroke -- the rounded corner of the panel
border. Baked in the TOP-LEFT orientation: the arc is centered at the
texture's bottom-right pixel (the point where the two inset straight border
edges would meet) with outer radius = the texture size, so the ring hugs the
rounded outer edge of the corner. The other three corners reuse this texture
with a simple SetTexCoord H/V flip (see AddGradientBorder in UnitFrames.lua).

Displayed in a RADIUS_PX x RADIUS_PX box at each panel corner. The stroke is
BORDER_W px wide on screen, converted to texture pixels here so the arc's
width matches the straight edges' thickness where they meet. Tinted the border
color at draw time (top corners at the faded top alpha, bottom corners solid),
so this texture carries only the ring shape.

Pure stdlib, no dependencies:

    python3 generate_border_corner.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), then BGRA rows top-to-bottom.
"""

import os
import struct

SIZE = 64
RADIUS_PX = 6   # on-screen corner box size (matches the locked radius)
BORDER_W = 2    # on-screen border thickness

OUTER = SIZE
STROKE = SIZE * (BORDER_W / RADIUS_PX)  # stroke width in texture pixels
INNER = OUTER - STROKE
CENTER = SIZE - 1  # arc center at the bottom-right pixel (top-left orientation)


def _ring_alpha(dist):
    """Anti-aliased radial ring: full alpha for INNER <= dist <= OUTER, with a
    1px linear feather at each edge, 0 outside the band."""
    # outer feather
    if dist >= OUTER + 0.5:
        return 0.0
    outer_cov = 1.0 if dist <= OUTER - 0.5 else (OUTER + 0.5) - dist
    # inner feather
    if dist <= INNER - 0.5:
        return 0.0
    inner_cov = 1.0 if dist >= INNER + 0.5 else dist - (INNER - 0.5)
    return max(0.0, min(1.0, min(outer_cov, inner_cov)))


def build_alpha_grid():
    grid = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            dx = CENTER - x
            dy = CENTER - y
            dist = (dx * dx + dy * dy) ** 0.5
            row.append(round(255 * _ring_alpha(dist)))
        grid.append(row)
    return grid


def write_tga(path, alpha_grid):
    header = bytes([
        0, 0, 2, 0, 0, 0, 0, 0,
    ]) + struct.pack("<HHHH", 0, 0, SIZE, SIZE) + bytes([32, 0x28])

    pixels = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            pixels += bytes([255, 255, 255, alpha_grid[y][x]])  # BGRA, white

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)


if __name__ == "__main__":
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "border_corner.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
