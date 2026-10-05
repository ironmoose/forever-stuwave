#!/usr/bin/env python3
"""Generates scanline.tga: a 4x4 uncompressed 32-bit TGA, solid black RGB,
designed to TILE. Row 0 (y=0) carries a moderate alpha (~0.30) dark line;
rows 1-3 are fully transparent. Tiled vertically (REPEAT wrap) this gives the
1px-on / 3px-off horizontal scanline pattern from the mockup's `.mmscan` /
`.term .scan` CRT overlay (`repeating-linear-gradient(0deg, rgba(0,0,0,.30)
0 1px, transparent 1px 3px)`), reused as-is for both the minimap and chat
overlays (Minimap.lua, Chat.lua) rather than baked as two separate textures.

Pure stdlib, no dependencies. Run directly to (re)write scanline.tga next to
this script:

    python3 generate_scanline.py

TGA layout: 18-byte header (image type 2, uncompressed truecolor; image
descriptor 0x28 = top-left origin, 8 alpha bits), followed by BGRA pixel
data in top-to-bottom row order (matching the top-left descriptor), no
footer.
"""

import os
import struct

WIDTH = 4
HEIGHT = 4
LINE_ALPHA = 0.30  # matches the mockup's rgba(0,0,0,.30) scanline row


def build_alpha_grid():
    """Alpha depends only on row: LINE_ALPHA at y=0 (the scanline row), 0.0
    for y=1..HEIGHT-1 (the gap), identical across every column in that row."""
    grid = []
    for y in range(HEIGHT):
        row_alpha = round(255 * LINE_ALPHA) if y == 0 else 0
        grid.append([row_alpha] * WIDTH)
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
            pixels += bytes([0, 0, 0, alpha])  # BGRA, solid black

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)


if __name__ == "__main__":
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "scanline.tga")
    write_tga(out_path, build_alpha_grid())
    print(f"wrote {out_path}")
