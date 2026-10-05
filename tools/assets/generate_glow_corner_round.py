#!/usr/bin/env python3
"""Generates glow_corner_round.tga: a 128x128 uncompressed 32-bit TGA, solid
white RGB, whose ALPHA is a quarter-annulus glow -- the outward halo around a
ROUNDED panel corner (radius PANEL_RADIUS). It is the corner piece of the
panel's box-shadow when the panel has rounded corners: the halo peaks on the
rounded border arc and fades outward, and is zero inside the arc (no interior
fill), exactly like the straight edge strips (glow_edge.tga) peak at the
border and fade out.

Baked in the TOP-LEFT orientation: the arc CENTER is the texture's bottom-right
pixel. The border arc sits at radius RADIUS_PX (in display px) from that
center; the halo peaks there (alpha 1) and fades with the same quadratic
profile as the edge strips out to RADIUS_PX + GLOW_SIZE, and is 0 for any
radius below RADIUS_PX (inside the panel). Displayed in a
(RADIUS_PX + GLOW_SIZE) square box whose bottom-right (the arc center) is
pinned RADIUS_PX inside the panel corner; the other three corners reuse this
texture with a SetTexCoord H/V flip (see AddOuterGlow in UnitFrames.lua).

Distinct from glow_corner.tga (the SQUARE-corner box-shadow, a radial blob
centered ON the corner point): that one is correct only when the panel corner
is a right angle. A rounded panel needs this annulus so the halo follows the
arc instead of poking a square nub past it.

Pure stdlib, no dependencies:

    python3 generate_glow_corner_round.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), then BGRA rows top-to-bottom.
"""

import os
import struct

SIZE = 128
RADIUS_PX = 6    # panel corner radius (display px)
GLOW_SIZE = 8    # halo reach past the border (display px), matches AddOuterGlow size

BOX = RADIUS_PX + GLOW_SIZE          # display box side
INNER = SIZE * (RADIUS_PX / BOX)      # arc radius in texture px (halo peak)
OUTER = SIZE                          # halo reaches 0 at the box edge
CENTER = SIZE - 1                     # arc center at the bottom-right pixel


def _alpha(dist):
    """0 inside the arc (dist < INNER); quadratic ease-out from the peak at
    dist == INNER to 0 at dist == OUTER; 0 beyond."""
    if dist < INNER or dist >= OUTER:
        return 0.0
    f = (OUTER - dist) / (OUTER - INNER)
    return f * f


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
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media")), "glow_corner_round.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
