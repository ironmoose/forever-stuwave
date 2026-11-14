#!/usr/bin/env python3
"""Generates the NPC dialog's row glyphs, one 64 x 32 atlas (gossip_glyphs.tga): eight white-RGB, alpha-shape glyphs tinted by
SetVertexColor in Lua (mockups/quest-npc-craft-2026-11-12.html, section B4: bubble, bag, book, house, plane, the gold ! and ?,
coin).

The atlas is 4 columns x 2 rows of 16 x 16 cells, in this order, left to right and top to bottom:

    0 bubble   1 bag    2 book   3 house
    4 plane    5 bang   6 qmark  7 coin

Each glyph is a 12 x 12 pixel drawing at (2, 2) inside its cell, the two outer texels of the cell left clear so a texture
coordinate that lands a hair off its cell never picks up a neighbour. A row of the dialog is 16 UI units (about 19 physical pixels)
tall, so the mockup's 20 px glyphs do not fit; these are drawn for 12 px, one texel per screen pixel, so an edge is one crisp pixel
and only the diagonals carry coverage. A stroke is one pixel wide with its centreline on a half pixel, except the two quest marks,
which are solid and bold. Cell (cx, cy) is read in Lua as texcoord (cx * 16 + 2) / 64 .. (cx * 16 + 14) / 64 across and
(cy * 16 + 2) / 32 .. (cy * 16 + 14) / 32 down.

A sample that lands exactly on a 45 degree edge through whole pixel corners would count in (or out) every such sample and bias the
edge texels one way, so each sample is taken twice, nudged one way and the other by an irrational amount, and a tie counts half.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_gossip_glyphs.py
"""

import math
import os
import struct

CELL = 16
COLS, ROWS = 4, 2
WIDTH, HEIGHT = COLS * CELL, ROWS * CELL
SUPERSAMPLE = 8
SHIFT_X, SHIFT_Y = 1.3e-7, 0.7e-7

ORDER = ("bubble", "bag", "book", "house", "plane", "bang", "qmark", "coin")


def point_in_polygon(px, py, pts):
    inside = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def rect(x0, y0, x1, y1):
    return lambda px, py: x0 <= px < x1 and y0 <= py < y1


def outline_rect(x0, y0, x1, y1, t=1.0):
    return lambda px, py: (x0 <= px < x1 and y0 <= py < y1) and not (x0 + t <= px < x1 - t and y0 + t <= py < y1 - t)


def poly(pts):
    return lambda px, py: point_in_polygon(px, py, pts)


def seg(a, b, w=1.0):
    """A butt ended stroke of one segment, `w` wide."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * w / 2, dx / n * w / 2
    return poly([(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])


def ring(cx, cy, r, w=1.0):
    lo, hi = r - w / 2, r + w / 2
    return lambda px, py: lo <= math.hypot(px - cx, py - cy) <= hi


def arc(cx, cy, r, w, start_deg, sweep_deg):
    """A ring sector: angles in degrees clockwise on screen from 'east' (y runs down), `sweep` long."""
    lo, hi = r - w / 2, r + w / 2

    def inside(px, py):
        d = math.hypot(px - cx, py - cy)
        if not lo <= d <= hi:
            return False
        a = (math.degrees(math.atan2(py - cy, px - cx)) - start_deg) % 360
        return a <= sweep_deg

    return inside


def union(*shapes):
    return lambda px, py: any(s(px, py) for s in shapes)


# Each glyph is a list of (inside, alpha); where two overlap the larger alpha wins. Coordinates are texels of the 16 x 16 cell;
# the drawing sits in (2, 2) .. (14, 14).
GLYPHS = {
    # a speech bubble with a tail at the lower left and three dots of speech
    "bubble": [
        (outline_rect(2, 3, 14, 10), 1.0),
        (poly([(4, 10), (8, 10), (4, 14)]), 1.0),
        (union(rect(5, 6, 6, 7), rect(8, 6, 9, 7), rect(11, 6, 12, 7)), 1.0),
    ],
    # a purse: a round handle over a body that widens to the foot, with a belt line across it
    "bag": [
        (arc(8, 6.5, 3.0, 1.0, 180, 180), 1.0),
        (rect(4, 7, 12, 8), 1.0),
        (seg((4.5, 7.5), (3.3, 13.5), 1.2), 1.0),
        (seg((11.5, 7.5), (12.7, 13.5), 1.2), 1.0),
        (rect(3, 13, 13, 14), 1.0),
        (rect(3, 10, 13, 11), 1.0),
    ],
    # an open book, a spine down the middle and two lines of text on each page
    "book": [
        (union(rect(3, 3, 7, 4), rect(9, 3, 13, 4)), 1.0),
        (outline_rect(2, 4, 8, 13), 1.0),
        (outline_rect(8, 4, 14, 13), 1.0),
        (union(rect(4, 6, 6, 7), rect(4, 9, 6, 10), rect(10, 6, 12, 7), rect(10, 9, 12, 10)), 1.0),
    ],
    # a house: a pitched roof, two walls, a floor line and a door
    "house": [
        (seg((2.8, 8.3), (8, 3.1), 1.4), 1.0),
        (seg((8, 3.1), (13.2, 8.3), 1.4), 1.0),
        (rect(4, 8, 5, 14), 1.0),
        (rect(11, 8, 12, 14), 1.0),
        (rect(4, 13, 12, 14), 1.0),
        (rect(7, 10, 9, 14), 1.0),
    ],
    # a paper plane: the outline of the wing and a fold line from the notch to the nose
    "plane": [
        (seg((2.7, 9), (13.2, 3.6), 1.4), 1.0),
        (seg((13.2, 3.6), (10, 13.2), 1.4), 1.0),
        (seg((10, 13.2), (7.2, 10.4), 1.4), 1.0),
        (seg((7.2, 10.4), (2.7, 9), 1.4), 1.0),
        (seg((7.2, 10.4), (13.2, 3.6), 1.4), 1.0),
    ],
    # the gold !: a bold stem that narrows to the foot, and a square dot
    "bang": [
        (poly([(6, 2), (10, 2), (9, 10), (7, 10)]), 1.0),
        (rect(7, 12, 9, 14), 1.0),
    ],
    # the gold ?: a hooked arc over a short stem, and a square dot
    "qmark": [
        (arc(8, 6.3, 3.2, 2.0, 180, 215), 1.0),
        (seg((10.6, 8.1), (8, 9.7), 2.0), 1.0),
        (rect(7, 9, 9, 10.5), 1.0),
        (rect(7, 12, 9, 14), 1.0),
    ],
    # a coin: a ring with a vertical bar and a short bar across it
    "coin": [
        (ring(8, 8, 5.5, 1.0), 1.0),
        (rect(7, 5, 9, 11), 1.0),
        (rect(6, 6, 10, 7), 1.0),
    ],
}


def sample(shapes, tx, ty):
    total = 0.0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            # the sample taken once nudged one way and once the other, so a tie counts half
            for sign in (1, -1):
                px = tx + (sx + 0.5) / SUPERSAMPLE + sign * SHIFT_X
                py = ty + (sy + 0.5) / SUPERSAMPLE + sign * SHIFT_Y
                total += 0.5 * max((alpha for inside, alpha in shapes if inside(px, py)), default=0.0)
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    out = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            cx, cy = x // CELL, y // CELL
            name = ORDER[cy * COLS + cx]
            alpha = sample(GLYPHS[name], x - cx * CELL, y - cy * CELL)
            out += bytes((255, 255, 255, int(round(alpha * 255))))
    return bytes(out)


def write(directory, name="gossip_glyphs"):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, WIDTH, HEIGHT, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({WIDTH}x{HEIGHT}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write(here)
