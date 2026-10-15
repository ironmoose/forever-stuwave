#!/usr/bin/env python3
"""Generates reticle_ring.tga: the ring of the target of target plate's reticle.

Reference: the design mockup, concept A (reticle()): a 9 x 9 glyph made of a ring (circle
centre (4.5, 4.5), radius 2.5, stroke 1), four 2 px ticks and a 1 x 1 centre dot. The ticks and the dot are plain
solid textures in Lua; only the ring needs a texture.

The stroke is centred on radius 2.5, so the ring spans radius 2 to 3 and its bounding square is 6 x 6 glyph units.
The canvas is exactly that square: 16 x 16 texels (a power of two, which the client needs), about 2.7 texels a
unit, outer radius 8 texels, inner radius 5.3. It is drawn about 6.4 screen px square, so the texture is nearly 1:1
on screen (a larger canvas is minified without mipmaps and the ring comes out uneven). GunsightTags.lua draws it
6 image px square centred on the glyph centre. White RGB, the shape in alpha, so the Lua side tints it with SetVertexColor (the tag tone: steel, pink, red).

Pure stdlib, matching the other generators here. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_reticle_ring.py
"""

import math
import os
import struct

SIZE = 16
UNITS = 6.0                 # glyph units the canvas covers
SUPERSAMPLE = 16
R_OUTER, R_INNER = 3.0, 2.0  # glyph units: radius 2.5 +- half the 1 unit stroke


def _coverage(x, y):
    scale = UNITS / SIZE
    total = 0
    for sy in range(SUPERSAMPLE):
        py = (y + (sy + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
        for sx in range(SUPERSAMPLE):
            px = (x + (sx + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
            if R_INNER <= math.hypot(px, py) <= R_OUTER:
                total += 1
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def main():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(x, y) * 255))))
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "reticle_ring.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
