#!/usr/bin/env python3
"""Generates anti_corner.tga: a 64x64 uncompressed 32-bit TGA, solid white RGB,
whose ALPHA is the INVERSE of fill_corner.tga's filled quarter disc -- opaque
outside the rounding arc, transparent inside it. Companion to fill_corner.tga,
same top-left baked orientation (arc center at the texture's bottom-right
pixel, radius = the texture size), so the existing 4-corner
placement/texcoord-flip table (Theme.lua's AddRoundedFill) applies unchanged.

Used to overpaint a StatusBar fill's square corners with the track color:
pinned to the fill's own corners at a per-bar concentric radius (the fill
radius, fill height / 2, computed in CreatePillBar), the opaque outer
region hides the fill's square corner while the transparent inner region
lets the fill's rounded silhouette show through (see Theme.AddCornerMask).
MaskTexture does not clip on this client (see fill_corner.tga's own
docstring), which is why this is a second corner texture instead of a mask.

Pure stdlib, no dependencies:

    python3 generate_anti_corner.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), then BGRA rows top-to-bottom.
"""

import os
import struct

SIZE = 64
RADIUS = SIZE  # arc radius = full box; disc centered at the bottom-right pixel
CENTER = SIZE - 1


def _alpha(dist):
    """Inverted disc: transparent inside RADIUS, 1px anti-aliased feather at
    the arc, opaque outside."""
    if dist <= RADIUS - 0.5:
        return 0.0
    if dist >= RADIUS + 0.5:
        return 1.0
    return dist - (RADIUS - 0.5)


def build_alpha_grid():
    grid = []
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            dx = CENTER - x
            dy = CENTER - y
            dist = (dx * dx + dy * dy) ** 0.5
            row.append(round(255 * _alpha(dist)))
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
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anti_corner.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
