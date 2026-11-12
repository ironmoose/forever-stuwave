#!/usr/bin/env python3
"""Generates the shared controls kit's marching chevron strips: ctl_chevron_h8, ctl_chevron_h4 and ctl_chevron_h3
(mockups/shared-controls-2026-11-12.html, chevs()).

The mockup's cast bar idiom: right pointing chevrons on a pitch of 8 px, a 2 px stroke, clipped to a strip and slid sideways
by 8 px every 0.6 s. One tile is one period, drawn at the pixel size the strip shows it (one texel a screen pixel), white RGB
with the shape in alpha, tinted by SetVertexColor in Lua and tiled horizontally (the texture repeats, so the chevrons march
by moving the texture's left coordinate):

    ctl_chevron_h8   8 x 8   the slider's cell strip: (0, 0) -> (4, 4) -> (0, 8)
    ctl_chevron_h4   8 x 4   the selected tab's top strip: (0, 0) -> (4, 2) -> (0, 4)
    ctl_chevron_h3   8 x 4   the switch slug's underline: (0, 0) -> (4, 1.5) -> (0, 3), the art in the top 3 rows of the
                             power of two canvas (sample the top 3/4)

The stroke has butt ends and a mitre at the tip, and is clipped to the strip's rows, as the SVG clip path does. The chevron
repeats every 8 px, so a stroke that leaves one tile enters its neighbour (the tile is periodic).

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_control_chevrons.py
"""

import math
import os
import struct

SUPERSAMPLE = 8
PITCH = 8.0
HALF = 1.0          # half the 2 px stroke
TIP_X = 4.0
# A sample shifted by an irrational amount never lands exactly on a 45 degree edge through whole pixel corners, which would
# count every such sample in (or out) and bias the edge texels one way.
SHIFT_X, SHIFT_Y = 1.3e-7, 0.7e-7


def stroke_polygon(height):
    """Outline of the chevron (0, 0) -> (TIP_X, height / 2) -> (0, height) as a polygon: butt ends, mitred tip."""
    ax, ay, bx, by, cx, cy = 0.0, 0.0, TIP_X, height / 2, 0.0, height
    l1 = math.hypot(bx - ax, by - ay)
    d1x, d1y = (bx - ax) / l1, (by - ay) / l1
    d2x, d2y = (cx - bx) / l1, (cy - by) / l1           # the two arms are the same length
    n1 = (-d1y, d1x)                                     # left of the first arm (towards the lower left)
    n2 = (-d2y, d2x)
    # outer side (the side the tip points out of): the right of the first arm, the right of the second
    # mitre at the tip: intersection of the two offset lines
    def offset(point, d, n, s):
        return (point[0] + n[0] * s, point[1] + n[1] * s, d[0], d[1])

    def meet(p, q):
        px, py, pdx, pdy = p
        qx, qy, qdx, qdy = q
        det = pdx * qdy - pdy * qdx
        t = ((qx - px) * qdy - (qy - py) * qdx) / det
        return (px + pdx * t, py + pdy * t)

    outer_tip = meet(offset((ax, ay), (d1x, d1y), n1, -HALF), offset((bx, by), (d2x, d2y), n2, -HALF))
    inner_tip = meet(offset((ax, ay), (d1x, d1y), n1, HALF), offset((bx, by), (d2x, d2y), n2, HALF))
    return [
        (ax - n1[0] * HALF, ay - n1[1] * HALF), outer_tip, (cx - n2[0] * HALF, cy - n2[1] * HALF),
        (cx + n2[0] * HALF, cy + n2[1] * HALF), inner_tip, (ax + n1[0] * HALF, ay + n1[1] * HALF),
    ]


def point_in_polygon(px, py, poly):
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def inside_for(height):
    poly = stroke_polygon(height)

    def inside(px, py):
        if py < 0 or py > height:        # the strip's clip rectangle
            return False
        for k in (-1, 0, 1):             # the neighbouring chevrons of the periodic tile
            if point_in_polygon(px - k * PITCH, py, poly):
                return True
        return False

    return inside


def build(width, rows, inside):
    out = bytearray()
    for ty in range(rows):
        for tx in range(width):
            hits = 0
            for sy in range(SUPERSAMPLE):
                py = ty + (sy + 0.5) / SUPERSAMPLE + SHIFT_Y
                for sx in range(SUPERSAMPLE):
                    if inside(tx + (sx + 0.5) / SUPERSAMPLE + SHIFT_X, py):
                        hits += 1
            out += bytes((255, 255, 255, int(round(hits / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
    return bytes(out)


def write(directory, name, width, rows, inside):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, rows, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build(width, rows, inside))
    print(f"wrote {path} ({width}x{rows}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write(here, "ctl_chevron_h8", 8, 8, inside_for(8.0))
    write(here, "ctl_chevron_h4", 8, 4, inside_for(4.0))
    write(here, "ctl_chevron_h3", 8, 4, inside_for(3.0))
