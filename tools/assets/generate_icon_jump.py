#!/usr/bin/env python3
"""Generates icon_jump.tga: the chat "jump to the latest line" glyph.

A down chevron over a short bar -- the standard "go to the end" mark rather
than a plain arrow, because a plain arrow reads as "scroll down by one" and
this button skips the whole way. The bar is what makes it terminal.

Blizzard's own art here is part of the `minimal-scrollbar` atlas family and is
stripped with the rest of it, so the button needs a glyph of its own or it sits
there correctly positioned and invisible -- which is exactly how it shipped for
one build.

Deliberately NOT given the holographic scanline treatment that icon_social and
icon_chrome use. Those are 14-16px glyphs that sit still; this one appears and
disappears as the chat scrolls, and a rastered glyph flickering in and out
reads as a rendering fault. It is a plain shape with an antialiased edge.

Shape lives in the alpha channel with white RGB, so the caller tints it.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_icon_jump.py
"""

import math
import os
import struct

SIZE = 32
SUPERSAMPLE = 6

# Chevron: two strokes meeting at the point. Drawn as segments with a round
# join so the vertex does not come out notched the way two overlapping
# rectangles would.
CHEVRON_LEFT = (6.5, 7.0)
CHEVRON_TIP = (16.0, 17.5)
CHEVRON_RIGHT = (25.5, 7.0)
STROKE = 3.4                 # full width of the chevron stroke

BAR_TOP, BAR_BOTTOM = 22.0, 25.6
BAR_LEFT, BAR_RIGHT = 7.0, 25.0


def _segment_distance(px, py, a, b):
    """Distance from (px, py) to the line SEGMENT a-b."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = min(max(t, 0.0), 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _inside(px, py):
    half = STROKE / 2.0
    if _segment_distance(px, py, CHEVRON_LEFT, CHEVRON_TIP) <= half:
        return True
    if _segment_distance(px, py, CHEVRON_TIP, CHEVRON_RIGHT) <= half:
        return True
    if BAR_LEFT <= px <= BAR_RIGHT and BAR_TOP <= py <= BAR_BOTTOM:
        return True
    return False


def _coverage(x, y):
    hits = 0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
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
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    path = os.path.join(here, "icon_jump.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
