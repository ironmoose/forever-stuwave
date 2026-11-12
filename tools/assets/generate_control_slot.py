"""Generates the shared controls kit's item slot art: ctl_hazard, ctl_glint and ctl_lock
(mockups/shared-controls-2026-11-12.html, slot()).

White RGB with the shape in alpha, tinted by SetVertexColor in Lua and drawn one texel per screen pixel:

    ctl_hazard   64 x 64  the locked slot's hazard tape: 3 px strokes at 45 degrees on the lines x + y = 20, 40 and 58 of the
                          mockup (its (-10, 30) -> (20, 0), (0, 40) -> (40, 0) and (14, 44) -> (44, 14), in icon coordinates)
                          and, so a larger icon is taped to its far corner too, x + y = 78, 98 and 118. The Lua shows the
                          top left w x h texels of it over the icon area, so a 32 x 30 icon sees exactly the mockup's three
                          strokes. Tinted amber at 0.4 in Lua.
    ctl_glint    64 x 64  the epic and legendary glint: the band (4, 30) -> (14, 0) -> (20, 0) -> (10, 30) of the mockup, a 6 px
                          wide slant, carried on at the same slope down the canvas for a taller icon. Shown through the icon
                          area and slid across it by moving the texture coordinates (the transparent canvas around the band
                          is what clamps a coordinate beyond 0 or 1). Tinted white at 0.35 in Lua.
    ctl_lock     16 x 16  the locked glyph: a shackle (M5 7 V5 a3 3 0 0 1 6 0 V7 at stroke 1.5) over a 10 x 7 body at (3, 7).

A stroke has butt ends. A sample shifted by an irrational amount never lands exactly on a 45 degree edge through whole pixel
corners, which would count every such sample in (or out) and bias the edge texels one way.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_control_slot.py
"""

import math
import os
import struct

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


def poly(points):
    return lambda px, py: point_in_polygon(px, py, points)


def rect(x0, y0, x1, y1):
    return lambda px, py: x0 <= px <= x1 and y0 <= py <= y1


def union(*shapes):
    return lambda px, py: any(s(px, py) for s in shapes)


def half_ring(cx, cy, radius, stroke):
    """The upper half (y <= cy) of a ring: the shackle's arc."""
    inner, outer = radius - stroke / 2, radius + stroke / 2
    return lambda px, py: py <= cy and inner <= math.hypot(px - cx, py - cy) <= outer


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


# x + y = c for each stroke; the segment runs from outside the canvas to outside it, so no butt end shows
HAZARD_SUMS = (20, 40, 58, 78, 98, 118)
HAZARD_LINES = tuple(((c - 80, 80), (c + 10, -10)) for c in HAZARD_SUMS)
GLINT_SLOPE = 10 / 30   # the band moves 10 px left for every 30 px down
GLINT_BOTTOM = 64

GLYPHS = {
    "ctl_hazard": (64, union(*(poly(segment_polygon(a, b, 1.5)) for a, b in HAZARD_LINES))),
    "ctl_glint": (64, poly([
        (14, 0), (20, 0), (20 - GLINT_SLOPE * GLINT_BOTTOM, GLINT_BOTTOM), (14 - GLINT_SLOPE * GLINT_BOTTOM, GLINT_BOTTOM),
    ])),
    "ctl_lock": (16, union(
        half_ring(8, 5, 3, 1.5),
        rect(4.25, 5, 5.75, 7),
        rect(10.25, 5, 11.75, 7),
        rect(3, 7, 13, 14),
    )),
}


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    for name, (size, shape) in GLYPHS.items():
        write(here, name, size, shape)
