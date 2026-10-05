#!/usr/bin/env python3
"""Generates icon_social.tga: the friends/person glyph, rendered as a hologram.

Parker: "Still have the person icon but instead of it just being solid have it
look all holographic with the lines and stuff."

So the silhouette stays the familiar head-and-shoulders -- it has to read as
"social" at 14 pixels, and nothing else does -- but it is projected rather than
printed. Three things do that, and all three are needed; any one alone just
looks like a damaged icon:

  1. SCANLINES. Evenly spaced horizontal cuts, unlike the widening slots of a
     synthwave sun. Even spacing is what reads as a raster; a progression reads
     as a sunset.
  2. A VERTICAL FALLOFF. The projection is brightest where it emits and thins
     toward the top, so the glyph fades out rather than ending in a hard edge.
  3. A BRIGHT RIM. Holograms are edge-lit: the outline stays near-solid even
     where the scanlines have eaten the fill, which is what keeps the shape
     legible once the interior is half cut away.

Shape and intensity live in the alpha channel with white RGB, so the caller
tints it to whatever the state calls for -- matching every other generator here.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_icon_social.py
"""

import math
import os
import struct

SIZE = 32
SUPERSAMPLE = 6

HEAD_CX, HEAD_CY, HEAD_R = 16.0, 10.0, 5.6
# Shoulders: an ellipse clipped to its top half, so it reads as a torso rather
# than a blob. Centre sits below the canvas on purpose.
BODY_CX, BODY_CY = 16.0, 31.0
BODY_RX, BODY_RY = 10.5, 13.0
BODY_TOP = 17.0

SCAN_PERIOD = 3.0        # texels between scanline starts
SCAN_GAP = 1.0           # texels actually cut
SCAN_DIM = 0.28          # a cut is not fully empty; a hologram still glows there

RIM = 1.3                # texels of near-solid edge
RIM_ALPHA = 0.95
FALLOFF_TOP = 0.45       # alpha at the very top of the glyph
FALLOFF_BOTTOM = 1.0


def _inside(px, py):
    if math.hypot(px - HEAD_CX, py - HEAD_CY) <= HEAD_R:
        return True
    if py >= BODY_TOP:
        nx = (px - BODY_CX) / BODY_RX
        ny = (py - BODY_CY) / BODY_RY
        if nx * nx + ny * ny <= 1.0:
            return True
    return False


def _near_edge(px, py):
    """True if inside but within RIM texels of the outside."""
    if not _inside(px, py):
        return False
    for dx, dy in ((RIM, 0), (-RIM, 0), (0, RIM), (0, -RIM),
                   (RIM * 0.7, RIM * 0.7), (-RIM * 0.7, RIM * 0.7),
                   (RIM * 0.7, -RIM * 0.7), (-RIM * 0.7, -RIM * 0.7)):
        if not _inside(px + dx, py + dy):
            return True
    return False


def _intensity(px, py):
    if not _inside(px, py):
        return 0.0

    # Projection falloff, dimmest at the top of the glyph.
    t = min(max(py / float(SIZE), 0.0), 1.0)
    value = FALLOFF_TOP + (FALLOFF_BOTTOM - FALLOFF_TOP) * t

    # Raster. The rim is exempt: edge-lighting survives the scanlines, and
    # without that exemption the silhouette breaks up into disconnected slabs.
    if not _near_edge(px, py) and (py % SCAN_PERIOD) < SCAN_GAP:
        value *= SCAN_DIM

    if _near_edge(px, py):
        value = max(value, RIM_ALPHA)

    return value


def _coverage(x, y):
    total = 0.0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            total += _intensity(px, py)
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(x, y) * 255))))
    return bytes(rows)


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "icon_social.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
