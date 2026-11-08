#!/usr/bin/env python3
"""Generates icon_gear.tga: the gear on the minimap bezel's Settings key.

The shape is the design mockup's `gear` glyph (the Game Menu key in control-deck-v1, ICONS.menu), drawn as written on its
16 unit viewBox: a hub ring of radius 2 and a rim ring of radius 4.5, both 1.6 wide, and eight spokes every 45 degrees
from east, each a butt-capped bar 2.3 wide running from the rim (radius 4.5) out to radius 6.8. 16 units map onto the 32
texel canvas (2 texels a unit), so the whole gear stays 1.2 units inside the canvas edge and no tooth is ever clipped.

A line glyph like the HUD toggle keys' (generate_hud_key_glyphs.py), but its own file: the key draws it once, centred,
tinted by SetVertexColor (white RGB, shape in alpha), and Lua lays it on whole physical pixels.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_icon_gear.py
"""

import math
import os
import struct

SIZE = 32
UNITS = 16.0
SCALE = SIZE / UNITS            # 2 texels per design unit
SUPERSAMPLE = 6
CENTRE = UNITS / 2

RINGS = ((2.0, 1.6), (4.5, 1.6))   # (radius, stroke width)
SPOKES = 8
SPOKE_INNER, SPOKE_OUTER, SPOKE_WIDTH = 4.5, 6.8, 2.3


def _inside(px, py):
    """True when the design-unit point (px, py) is on the gear."""
    x, y = px - CENTRE, py - CENTRE
    r = math.hypot(x, y)
    for radius, width in RINGS:
        if abs(r - radius) <= width / 2:
            return True
    for k in range(SPOKES):
        a = k * 2 * math.pi / SPOKES
        along = x * math.cos(a) + y * math.sin(a)
        across = -x * math.sin(a) + y * math.cos(a)
        if SPOKE_INNER <= along <= SPOKE_OUTER and abs(across) <= SPOKE_WIDTH / 2:
            return True
    return False


def _coverage(tx, ty):
    hits = 0
    for sy in range(SUPERSAMPLE):
        py = (ty + (sy + 0.5) / SUPERSAMPLE) / SCALE
        for sx in range(SUPERSAMPLE):
            px = (tx + (sx + 0.5) / SUPERSAMPLE) / SCALE
            if _inside(px, py):
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(x, y) * 255))))
    return bytes(rows)


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "icon_gear.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
