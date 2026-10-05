#!/usr/bin/env python3
"""Generates the control deck's chrome textures (divider, LED, key outline).

Files written (all next to this script):

    deck_divider.tga           32x32   neon double slash "//"
    deck_led.tga               32x8    soft rounded LED underline bar
    deck_key_slant_outline.tga 32x32   outline-only twin of cell_slant.tga

Every texture is white RGB with the shape or intensity in ALPHA, so the Lua
side tints it (SetVertexColor) or paints a gradient over it (SetGradient; the
`//` divider gets a vertical violet to pink ramp that way).

The deck chassis itself is no longer drawn from art made here: it is a plain
two-corner cut rectangle built from the shared slice_cut2 textures, so the old
sun, perspective grid and slanted shoulder textures are gone.

deck_key_slant_outline: the same parallelogram and slant as cell_slant.tga
(32x32, top edge leads the bottom by 0.34 of the width), but only a 1.5px
ring along its edge, for hover and active neon outlines on the micro keys.
The key fill reuses cell_slant.tga itself; do not regenerate that here.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28
(top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_deck_chrome.py
"""

import math
import os
import struct

SUPERSAMPLE = 6


def write_tga(path, width, height, alpha_rows):
    """alpha_rows: height lists of width floats in 0..1."""
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    pixels = bytearray()
    for row in alpha_rows:
        for a in row:
            pixels += bytes((255, 255, 255, int(round(min(max(a, 0.0), 1.0) * 255))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def supersample(width, height, inside):
    """Coverage grid for a boolean shape test inside(x, y)."""
    n = SUPERSAMPLE * SUPERSAMPLE
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            hits = 0
            for sy in range(SUPERSAMPLE):
                py = y + (sy + 0.5) / SUPERSAMPLE
                for sx in range(SUPERSAMPLE):
                    if inside(x + (sx + 0.5) / SUPERSAMPLE, py):
                        hits += 1
            row.append(hits / n)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# deck_divider
# ---------------------------------------------------------------------------

DIV_SIZE = 32
DIV_HALF = 1.1
DIV_SLASHES = (((8.0, 26.0), (14.5, 6.0)), ((17.5, 26.0), (24.0, 6.0)))


def _seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)
    t = min(max(t, 0.0), 1.0)
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def build_divider():
    return supersample(
        DIV_SIZE, DIV_SIZE,
        lambda x, y: any(_seg_dist(x, y, a, b) <= DIV_HALF for a, b in DIV_SLASHES),
    )


# ---------------------------------------------------------------------------
# deck_led
# ---------------------------------------------------------------------------

LED_W, LED_H = 32, 8
LED_CORE = 1.1          # half-thickness that stays fully bright
LED_REACH = 3.8         # distance where the soft edge hits zero


def build_led():
    a, b = (8.0, LED_H / 2.0), (24.0, LED_H / 2.0)
    rows = []
    for y in range(LED_H):
        row = []
        for x in range(LED_W):
            d = _seg_dist(x + 0.5, y + 0.5, a, b)
            if d <= LED_CORE:
                v = 1.0
            elif d >= LED_REACH:
                v = 0.0
            else:
                v = (1.0 - (d - LED_CORE) / (LED_REACH - LED_CORE)) ** 2
            row.append(v)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# deck_key_slant_outline
# ---------------------------------------------------------------------------

KEY_SIZE = 32
KEY_SLANT = 0.34                      # same fraction as generate_cell_slant.py
KEY_OUTLINE = 1.5


def _key_poly():
    s = KEY_SLANT * KEY_SIZE
    return [(s, 0.0), (KEY_SIZE, 0.0), (KEY_SIZE - s, KEY_SIZE), (0.0, KEY_SIZE)]


def _key_ring(x, y):
    poly = _key_poly()
    worst = None
    # Convex, clockwise in y-down space: inside means every edge has the point
    # on its right-hand side. Track the smallest perpendicular distance.
    for i in range(4):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % 4]
        ex, ey = bx - ax, by - ay
        length = math.hypot(ex, ey)
        d = (ex * (y - ay) - ey * (x - ax)) / length
        if d < 0.0:
            return False
        worst = d if worst is None else min(worst, d)
    return worst <= KEY_OUTLINE


def build_key_outline():
    return supersample(KEY_SIZE, KEY_SIZE, _key_ring)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = lambda name: os.path.join(here, name + ".tga")
    write_tga(out("deck_divider"), DIV_SIZE, DIV_SIZE, build_divider())
    write_tga(out("deck_led"), LED_W, LED_H, build_led())
    write_tga(out("deck_key_slant_outline"), KEY_SIZE, KEY_SIZE, build_key_outline())


if __name__ == "__main__":
    main()
