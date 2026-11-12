#!/usr/bin/env python3
"""Generates icon_key_search.tga, icon_key_calendar.tga and icon_key_chevron.tga: the minimap key row's glyphs.

The key row's keys lost their boxes in the 2026-11-12 cleanup: each is a bare glyph over a coloured LED underline.
The tracking key (cyan) and the calendar key (violet) used to wear Blizzard's stock art, whose colours and chrome
the addon does not control; these are the design mockup's own line glyphs instead, drawn once here and tinted by
SetVertexColor in Lua (white RGB, shape in alpha, like icon_gear.tga). The addon tray's toggle key gets its chevron
here too.

Each file is drawn at the pixel size the key shows it (one texel a screen pixel at the 1440 p design size), on
whole pixels where it can be, so a line is one crisp pixel and only the diagonals and the lens carry coverage:

    icon_key_search    16 x 16   a lens (ring 1.3 wide) and a square capped handle on the diagonal
    icon_key_calendar  16 x 16   a 1 px frame, the header rule, two binder pegs, five date dashes
    icon_key_chevron    8 x 4    a down chevron; the up chevron is the same file flipped (SetTexCoord)

The shapes are the mockup's `gTrack` and `gCal` on its 30 unit key box, scaled 16/30 (the lens and the handle), and
snapped to the pixel grid (the calendar).

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_minimap_keys.py
"""

import math
import os
import struct

SUPERSAMPLE = 8

# icon_key_search: the mockup's lens (centre 12, 12, radius 8, stroke 2.4) and handle (18, 18 to 27, 27) on 30 units, x 16/30.
SEARCH_SIZE = 16
SEARCH_SCALE = 16 / 30
LENS = (12 * SEARCH_SCALE, 12 * SEARCH_SCALE, 8 * SEARCH_SCALE, 2.4 * SEARCH_SCALE)
HANDLE = (18 * SEARCH_SCALE, 18 * SEARCH_SCALE, 27 * SEARCH_SCALE, 27 * SEARCH_SCALE, 2.4 * SEARCH_SCALE)

# icon_key_calendar: filled texels, (x0, y0, x1, y1) half open, on a 16 texel canvas.
CALENDAR_SIZE = 16
CALENDAR_RECTS = [
    (1, 3, 15, 4), (1, 14, 15, 15), (1, 3, 2, 15), (14, 3, 15, 15),    # the frame
    (1, 6, 15, 7),                                                       # the header rule
    (4, 1, 5, 5), (11, 1, 12, 5),                                        # the binder pegs
    (4, 9, 6, 10), (7, 9, 9, 10), (10, 9, 12, 10),                       # first row of dates
    (4, 11, 6, 12), (7, 11, 9, 12),                                      # second row of dates
]

# icon_key_chevron: a down chevron on an 8 x 4 canvas.
CHEVRON_W, CHEVRON_H = 8, 4
CHEVRON = ((0.55, 0.65), (4.0, 3.2), (7.45, 0.65))
CHEVRON_STROKE = 1.25


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def square_capped(px, py, ax, ay, bx, by, width):
    """Inside a stroke of the given width along a to b with butt ends extended by half the width (a square cap)."""
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    along = (px - ax) * ux + (py - ay) * uy
    across = abs(-(px - ax) * uy + (py - ay) * ux)
    return -width / 2 <= along <= length + width / 2 and across <= width / 2


def search_inside(px, py):
    cx, cy, radius, width = LENS
    if abs(math.hypot(px - cx, py - cy) - radius) <= width / 2:
        return True
    return square_capped(px, py, *HANDLE)


def calendar_inside(px, py):
    return any(x0 <= px < x1 and y0 <= py < y1 for x0, y0, x1, y1 in CALENDAR_RECTS)


def chevron_inside(px, py):
    return any(seg_dist(px, py, *CHEVRON[i], *CHEVRON[i + 1]) <= CHEVRON_STROKE / 2 for i in range(2))


def build(width, height, inside):
    rows = bytearray()
    for ty in range(height):
        for tx in range(width):
            hits = 0
            for sy in range(SUPERSAMPLE):
                py = ty + (sy + 0.5) / SUPERSAMPLE
                for sx in range(SUPERSAMPLE):
                    if inside(tx + (sx + 0.5) / SUPERSAMPLE, py):
                        hits += 1
            rows += bytes((255, 255, 255, int(round(hits / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
    return bytes(rows)


def write(directory, name, width, height, inside):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build(width, height, inside))
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    write(here, "icon_key_search", SEARCH_SIZE, SEARCH_SIZE, search_inside)
    write(here, "icon_key_calendar", CALENDAR_SIZE, CALENDAR_SIZE, calendar_inside)
    write(here, "icon_key_chevron", CHEVRON_W, CHEVRON_H, chevron_inside)
