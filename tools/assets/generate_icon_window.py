#!/usr/bin/env python3
"""Generates icon_minimize.tga and icon_maximize.tga: the title-bar lamps.

The two dots at the left of the term bar were decorative -- a pink and a green
glow, the mock's status lights. They become controls here, so they need to say
which control they are.

Drawn as plain glyphs, tinted by the caller -- minimise pink, maximise green,
carrying the colours the old status lamps had. An earlier pass punched them out
of a round glowing lamp, traffic-light style; Parker's call was to drop the
disc ("i don't think the icons need the round bg") and match the flat glyphs in
the title bar's right-hand group instead, which is also one less thing between
the shape and the reader at this size.

Shapes, deliberately a matched pair with media/generate_icon_jump.py so the
three window controls share one vocabulary:

    minimize   one bar. The window collapses TO that line.
    maximize   a bar with a chevron rising into it: the window grows UP to the
               top of the screen. It is generate_icon_jump.py's glyph inverted,
               because it is the inverse action.

A plain arrow was rejected for maximize for the same reason it was on the jump
button: an arrow reads as "nudge one step in this direction", and a bar is what
turns it into "all the way to the end".

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_icon_window.py
"""

import math
import os
import struct

SIZE = 32
SUPERSAMPLE = 6

# Proportioned to match generate_icon_chrome.py's glyphs, which sit beside
# these in the same bar at the same 16px. Bold enough to survive the downscale:
# a stroke that looks right on the 32px canvas is half of what it seems once
# drawn at 16.
BAR_LEFT, BAR_RIGHT = 5.0, 27.0
BAR_THICK = 4.6

# Chevron for maximize, pointing UP into the bar above it.
CHEVRON_LEFT = (5.5, 25.5)
CHEVRON_TIP = (16.0, 13.5)
CHEVRON_RIGHT = (26.5, 25.5)
STROKE = 4.4

MAX_BAR_TOP = 4.0
MIN_BAR_TOP = 13.7          # minimize: a single bar on the centre line


def _segment_distance(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = min(max(t, 0.0), 1.0)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _bar(px, py, top):
    return BAR_LEFT <= px <= BAR_RIGHT and top <= py <= top + BAR_THICK


def _inside_minimize(px, py):
    return _bar(px, py, MIN_BAR_TOP)


def _inside_maximize(px, py):
    if _bar(px, py, MAX_BAR_TOP):
        return True
    half = STROKE / 2.0
    if _segment_distance(px, py, CHEVRON_LEFT, CHEVRON_TIP) <= half:
        return True
    if _segment_distance(px, py, CHEVRON_TIP, CHEVRON_RIGHT) <= half:
        return True
    return False


def _coverage(inside, x, y):
    hits = 0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            if inside(px, py):
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build(inside):
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(inside, x, y) * 255))))
    return bytes(rows)


def _write(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    _write(os.path.join(here, "icon_minimize.tga"), build(_inside_minimize))
    _write(os.path.join(here, "icon_maximize.tga"), build(_inside_maximize))
