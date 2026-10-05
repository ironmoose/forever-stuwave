#!/usr/bin/env python3
"""Generates scanline_rgb.tga: a 4x4 uncompressed 32-bit TGA approximating the
layout-planner mockup's `.mmscan` RGB subpixel-stripe overlay -- a CSS
90-degree repeating gradient of 1px red / 1px green / 1px blue (period 3px)
that WoW cannot render directly (a Texture has no gradient support), so real
per-column RGB is baked into a tiling texture instead of relying on a single
SetVertexColor tint (three different hues can't come from one tint call).

Layout (matches scanline.tga's own 4x4 tiling convention -- see that
generator): columns vary by X, giving a vertical RGB-stripe pattern (an LCD
subpixel grid look) with a 4px period rather than the mockup's 3px, to stay
power-of-two-clean per this repo's TGA convention (see
test_tga_generators.py's EXPECTED_DIMS on why
every generated texture here is power-of-two). Rows are identical, since the
pattern has no vertical variation.

    x=0: red   rgba(255,60,90, ~0.10)
    x=1: green rgba(60,255,140,~0.08)
    x=2: blue  rgba(80,140,255,~0.10)
    x=3: a dimmer repeat of the red column -- the 4th, power-of-two-filler
         column, softening the seam where the mockup's 3px period wraps into
         this texture's 4px tile

Alphas are baked ABOVE the mockup's own .06/.05/.06 (CSS opacity values,
tuned for a large screen-filling overlay): at typical WoW UI scale the map
face is small and the mockup's own values read as imperceptible there, so
they are bumped roughly 1.6x here for legibility -- a design call, not a
defect. Unlike scanline.tga (whose baked alpha is further scaled by
Minimap.lua's own SCANLINE_ALPHA), these are the FINAL alpha values; the
addon applies no extra multiplier on top (see Minimap.lua's SUBPIXEL_ALPHA).

Pure stdlib, matching the other generators in this folder. Output: 18-byte
header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom, no footer.

    python3 generate_scanline_rgb.py
"""

import os
import struct

WIDTH = 4
HEIGHT = 4

# (R, G, B, alpha 0-255) per column, x=0..3.
COLUMNS = [
    (255, 60, 90, round(255 * 0.10)),    # red
    (60, 255, 140, round(255 * 0.08)),   # green
    (80, 140, 255, round(255 * 0.10)),   # blue
    (255, 60, 90, round(255 * 0.05)),    # dim repeat of red, power-of-two filler
]


def write_tga(path):
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
    for _y in range(HEIGHT):
        for x in range(WIDTH):
            r, g, b, a = COLUMNS[x]
            pixels += bytes([b, g, r, a])  # BGRA

    with open(path, "wb") as f:
        f.write(header)
        f.write(pixels)


if __name__ == "__main__":
    out_path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "scanline_rgb.tga")
    write_tga(out_path)
    print(f"wrote {out_path}")
