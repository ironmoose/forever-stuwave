#!/usr/bin/env python3
"""Generates fill_corner.tga: a 64x64 uncompressed 32-bit TGA, solid white RGB,
whose ALPHA is a FILLED quarter disc -- the rounded corner of the panel's
background fill. Companion to border_corner.tga (which is the ring/stroke at
the same corner): this is the solid interior up to that same arc, so the fill
and border round on exactly the same circle.

Baked in the TOP-LEFT orientation: the arc center is the texture's bottom-right
pixel, radius = the texture size. Alpha is 255 for pixels within the radius
(the filled interior), anti-aliased at the arc, 0 outside (the transparent
corner cutout). Displayed in a RADIUS x RADIUS box pinned to the panel corner;
the other three corners reuse this texture with a SetTexCoord H/V flip (see
AddRoundedFill in UnitFrames.lua). Tinted to the bg color at draw time.

This exists because a single stretched rounded-rect fill texture cannot be used
here: stretching moves the baked corner's arc center off the fixed
border/glow arc center (the panel has two heights), so the fill pokes past the
border. Fixed-size corner pieces keep the fill aligned at any panel height.

Pure stdlib, no dependencies:

    python3 generate_fill_corner.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), then BGRA rows top-to-bottom.
"""

import os
import struct

SIZE = 64
RADIUS = SIZE  # arc radius = full box; disc centered at the bottom-right pixel
CENTER = SIZE - 1


def _alpha(dist):
    """Filled disc: full inside RADIUS, 1px anti-aliased feather at the arc,
    empty outside."""
    if dist <= RADIUS - 0.5:
        return 1.0
    if dist >= RADIUS + 0.5:
        return 0.0
    return (RADIUS + 0.5) - dist


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
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "fill_corner.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
