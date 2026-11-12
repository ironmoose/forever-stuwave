#!/usr/bin/env python3
"""Generates the shared controls kit's slanted tab caps: ctl_tab_fill, ctl_tab_edge and ctl_tab_diag
(mockups/shared-controls-2026-11-12.html, slant()).

A leaning tab cannot be nine-sliced (the straight diagonal would kink where the stretched middle meets the corners), so a tab is
built the way tab_slant.tga builds the chat tabs: a fixed size cap at each end and a plain rectangle between them, so the angle is
the same on every tab whatever its width. The mockup's tab is 28 tall with a slant of 8: the top edge runs from x + 8 to x + w, the
bottom edge from x to x + w - 8. Each cap is 8 wide by 28 tall, drawn in the top left of a 32 x 32 canvas and shown through its
texture coordinates (0, 8 / 32, 0, 28 / 32); the trailing cap is the same texture turned half way round (both axes flipped), which
maps the leading cap's diagonal onto the trailing one.

White RGB with the shape in alpha, tinted by SetVertexColor in Lua and drawn one texel per screen pixel:

    ctl_tab_fill   32 x 32  the leading cap's face: the part of the 8 x 28 box on the inside of the diagonal (8, 0) -> (0, 28)
    ctl_tab_edge   32 x 32  its 1 px edge: the diagonal (8.5, 0.5) -> (0.5, 27.5) (1 px across, butt ends) and the 1 px run along the
                            bottom, y 27 to 28 (the trailing cap's turn puts the run along the top)
    ctl_tab_diag   32 x 32  the selected tab's pink diagonal alone: (7.5, 1) -> (0, 28), 1 px across

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_control_tab.py
"""

import math
import os
import struct

SUPERSAMPLE = 8
SHIFT_X, SHIFT_Y = 1.3e-7, 0.7e-7
CAP_W, CAP_H = 8, 28


def segment_polygon(a, b, half):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * half, dx / length * half
    return [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]


def point_in_polygon(px, py, poly):
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def in_box(px, py):
    return 0 <= px <= CAP_W and 0 <= py <= CAP_H


def fill(px, py):
    # right of the diagonal through (8, 0) and (0, 28): 28 x + 8 y >= 8 * 28
    return in_box(px, py) and CAP_H * px + CAP_W * py >= CAP_W * CAP_H


EDGE_DIAGONAL = segment_polygon((8.5, 0.5), (0.5, 27.5), 0.5)


def edge(px, py):
    if not in_box(px, py):
        return False
    return (27 <= py <= 28) or point_in_polygon(px, py, EDGE_DIAGONAL)


DIAG_DIAGONAL = segment_polygon((7.5, 1), (0, 28), 0.5)


def diag(px, py):
    return in_box(px, py) and point_in_polygon(px, py, DIAG_DIAGONAL)


def build(size, shape):
    out = bytearray()
    for ty in range(size):
        for tx in range(size):
            total = 0
            for sy in range(SUPERSAMPLE):
                py = ty + (sy + 0.5) / SUPERSAMPLE + SHIFT_Y
                for sx in range(SUPERSAMPLE):
                    px = tx + (sx + 0.5) / SUPERSAMPLE + SHIFT_X
                    if shape(px, py):
                        total += 1
            out += bytes((255, 255, 255, int(round(total / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
    return bytes(out)


def write(directory, name, size, shape):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build(size, shape))
    print(f"wrote {path} ({size}x{size}, {os.path.getsize(path)} bytes)")


GLYPHS = {"ctl_tab_fill": (32, fill), "ctl_tab_edge": (32, edge), "ctl_tab_diag": (32, diag)}


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    for name, (size, shape) in GLYPHS.items():
        write(here, name, size, shape)
