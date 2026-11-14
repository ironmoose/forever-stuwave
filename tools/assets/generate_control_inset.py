#!/usr/bin/env python3
"""Generates the shared controls kit's inset art: ctl_scanline (mockups/shared-controls-2026-11-12.html, inset()).

    ctl_scanline  4 x 4  the inset's CRT scanline tile: white RGB with the shape in alpha, one solid row in four. The mockup draws
                         a 1 px line every 4 px, the first at y + 3 (for i = y + 3; i < y + h; i += 4), so tiled from the top
                         left of the inset the line is row 3 of the tile. Tinted violet at 5 percent in Lua and tiled one texel
                         per screen pixel.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_control_inset.py
"""

import os
import struct

SIZE = 4
LINE_ROW = 3


def build():
    out = bytearray()
    for y in range(SIZE):
        alpha = 255 if y == LINE_ROW else 0
        for _ in range(SIZE):
            out += bytes((255, 255, 255, alpha))
    return bytes(out)


def write(directory, name):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write(here, "ctl_scanline")
