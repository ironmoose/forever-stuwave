#!/usr/bin/env python3
"""Generates cell_slant.tga: a parallelogram leaning `/`, for the XP bar's cells.

Why: the first segmented XP bar drew each cell with SetColorTexture, which can
only make a rectangle. Eighty upright rectangles in a row reads as a progress
bar, which is exactly what Parker called boring. Leaning them turns the same
data into an arcade power meter -- the shape does the work, not the colour.

The lean is expressed as a fraction of the WIDTH, so it scales with the cell
rather than staying a fixed pixel count, and the gaps between cells inherit the
same angle for free.

Shape, per row y from top to bottom: the span slides left as it descends, so
the top edge is pushed right by SLANT and the bottom edge is pulled back.

Pure stdlib, matching the other generators here. Output: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_cell_slant.py
"""

import os
import struct

SIZE = 32
SLANT = 0.34        # fraction of the width the top edge leads the bottom by
SUPERSAMPLE = 6


def coverage(px, py):
    """Fraction of pixel (px, py) inside the leaning parallelogram."""
    slant = SLANT * SIZE
    hits = 0

    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            x = px + (sx + 0.5) / SUPERSAMPLE
            y = py + (sy + 0.5) / SUPERSAMPLE

            # How far this row's span has slid left, 0 at the top row.
            shift = slant * (y / SIZE)
            if (slant - shift) <= x <= (SIZE - shift):
                hits += 1

    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = int(round(coverage(x, y) * 255))
            # White; every cell is tinted with SetVertexColor, so the shape has
            # to live entirely in the alpha channel.
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def main():
    path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "cell_slant.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
