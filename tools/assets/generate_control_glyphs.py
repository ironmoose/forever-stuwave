#!/usr/bin/env python3
"""Generates the shared controls kit's field and dropdown glyphs: ctl_prompt, ctl_lens, ctl_cross, ctl_radar,
ctl_radar_arm and ctl_chev (mockups/shared-controls-2026-11-12.html, glyph() and the radar lens of field()).

Each is a 16 x 16 white-RGB, alpha-shape texture tinted by SetVertexColor in Lua and drawn one texel per screen pixel (the
mockup's glyph canvas is 16 x 16 and its origin sits at (4, 6) inside a field and (x + w - 24, 6) in a dropdown), so an
edge is one crisp pixel and only the diagonals carry coverage:

    ctl_prompt     (5, 4) -> (10, 8) -> (5, 12), stroke 2          the edit box's prompt chevron
    ctl_lens       ring about (7, 7) of radius 4.5, stroke 2, and the handle (10.5, 10.5) -> (14, 14), stroke 2
    ctl_cross      (4, 4) -> (12, 12) and (12, 4) -> (4, 12), stroke 2     the search box's clear key
    ctl_radar      ring about (8, 8) of radius 7 at stroke 1 and, at half alpha, the ring of radius 3 (the radar lens)
    ctl_radar_arm  (8, 8) -> (15, 8), stroke 2: the sweep arm, turned about the canvas centre in Lua
    ctl_chev       (3, 6) -> (8, 11) -> (13, 6), stroke 2: the dropdown's chevron; flipped upright for an open list

A stroke has butt ends and a mitre at a bend. A sample that lands exactly on a 45 degree edge through whole pixel corners
would count in (or out) every such sample and bias the edge texels one way, so each sample is taken twice, nudged one way
and the other by an irrational amount, and a tie counts half.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_control_glyphs.py
"""

import math
import os
import struct

SIZE = 16
SUPERSAMPLE = 8
SHIFT_X, SHIFT_Y = 1.3e-7, 0.7e-7


def point_in_polygon(px, py, poly):
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def segment_polygon(a, b, half):
    """A butt ended stroke of one segment as a rectangle."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * half, dx / length * half
    return [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]


def bend_polygon(a, b, c, half):
    """A butt ended stroke of a -> b -> c with a mitred bend at b, as one polygon."""
    def unit(p, q):
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        return (q[0] - p[0]) / length, (q[1] - p[1]) / length

    d1, d2 = unit(a, b), unit(b, c)
    n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])

    def meet(p, d, q, e):
        det = d[0] * e[1] - d[1] * e[0]
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / det
        return (p[0] + d[0] * t, p[1] + d[1] * t)

    def side(s):
        start = (a[0] + n1[0] * s * half, a[1] + n1[1] * s * half)
        mid_a = (b[0] + n1[0] * s * half, b[1] + n1[1] * s * half)
        mid_c = (b[0] + n2[0] * s * half, b[1] + n2[1] * s * half)
        end = (c[0] + n2[0] * s * half, c[1] + n2[1] * s * half)
        return start, meet(mid_a, d1, mid_c, d2), end

    left, right = side(1), side(-1)
    return [left[0], left[1], left[2], right[2], right[1], right[0]]


def ring(cx, cy, radius, stroke):
    inner, outer = radius - stroke / 2, radius + stroke / 2
    return lambda px, py: inner <= math.hypot(px - cx, py - cy) <= outer


def poly(points):
    return lambda px, py: point_in_polygon(px, py, points)


def union(*shapes):
    return lambda px, py: any(s(px, py) for s in shapes)


def build(shapes):
    """`shapes` is a list of (inside, alpha): where they overlap the larger alpha wins."""
    out = bytearray()
    for ty in range(SIZE):
        for tx in range(SIZE):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    # the sample taken once nudged one way and once the other, so a tie counts half
                    for sign in (1, -1):
                        px = tx + (sx + 0.5) / SUPERSAMPLE + sign * SHIFT_X
                        py = ty + (sy + 0.5) / SUPERSAMPLE + sign * SHIFT_Y
                        total += 0.5 * max((alpha for inside, alpha in shapes if inside(px, py)), default=0.0)
            out += bytes((255, 255, 255, int(round(total / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
    return bytes(out)


def write(directory, name, shapes):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build(shapes))
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


GLYPHS = {
    "ctl_prompt": [(poly(bend_polygon((5, 4), (10, 8), (5, 12), 1.0)), 1.0)],
    "ctl_lens": [
        (ring(7, 7, 4.5, 2.0), 1.0),
        (poly(segment_polygon((10.5, 10.5), (14, 14), 1.0)), 1.0),
    ],
    "ctl_cross": [
        (union(poly(segment_polygon((4, 4), (12, 12), 1.0)), poly(segment_polygon((12, 4), (4, 12), 1.0))), 1.0),
    ],
    "ctl_radar": [(ring(8, 8, 7, 1.0), 1.0), (ring(8, 8, 3, 1.0), 0.5)],
    "ctl_radar_arm": [(poly(segment_polygon((8, 8), (15, 8), 1.0)), 1.0)],
    "ctl_chev": [(poly(bend_polygon((3, 6), (8, 11), (13, 6), 1.0)), 1.0)],
}


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    for name, shapes in GLYPHS.items():
        write(here, name, shapes)
