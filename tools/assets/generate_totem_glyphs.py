#!/usr/bin/env python3
"""Generates the Shaman totem tab glyphs: the four element crowns, the set mark, the recall mark and the
dotted mold of a locked button.

Reference: mockups/gunsight-class-module-shaman-2026-10-08.html, Concept A "Totem Poles", the
`crown(el, cx, ty, c)` function. Each pole wears a 12 x 6 unit crown drawn from a handful of points:

    fire   a solid three peaked flame           (7 point polygon)
    earth  a solid stepped block, a castle top  (8 point polygon)
    water  a wave of four half waves, stroked   (quadratic curves, stroke 1.8)
    air    two up chevrons side by side, stroked (stroke 1.6)

The points below are the mockup's own, copied and scaled up to fill a 16 unit box (the tab shows the
crown as a small badge on the element button and the set button shows four of them), so the tab and
the approved tracker poles wear the same crowns.

Files written (in forever-stuwave/Media/Textures):

    totem_fire.tga     32x32  fire crown
    totem_earth.tga    32x32  earth crown
    totem_water.tga    32x32  water crown
    totem_air.tga      32x32  air crown
    totem_set.tga      32x32  the four crowns small, one per quadrant (the whole-set drop)
    totem_recall.tga   32x32  a loop arrow around a small totem dot (Totemic Recall)
    totem_mold.tga     64x64  a dotted outline with the button's two chamfers (top left and bottom
                              right, 10 texels), the mockup's dashed pole mold, for a locked button

White RGB, shape in alpha; Lua tints them with SetVertexColor. There is deliberately no baked glow.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha
bits), BGRA top-to-bottom.

    python3 generate_totem_glyphs.py
"""

import math
import os
import struct

SUPERSAMPLE = 4
GLYPH_SIZE = 32
VIEWBOX = 16.0
MOLD_SIZE = 64


# ---------------------------------------------------------------------------
# The mockup's crown points, as (dx, dy) from (cx, ty): x in [-6, 6], y in [0, 6]
# ---------------------------------------------------------------------------

FIRE = [(-5, 6), (-3, 3), (-1, 4.5), (0, 0), (1, 4.5), (3, 3), (5, 6)]
EARTH = [(-5, 6), (-5, 2), (-2, 2), (-2, 0), (2, 0), (2, 2), (5, 2), (5, 6)]
AIR_LEFT = [(-6, 5), (-3, 1), (0, 5)]
AIR_RIGHT = [(0, 5), (3, 1), (6, 5)]


def quad(p0, p1, p2, steps=14):
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def wave():
    """M-6,5 q1.5,-5 3,0 t3,0 t3,0 t3,0: four half waves, each reflecting the last control point."""
    pts = []
    cur = (-6.0, 5.0)
    ctrl_dx, ctrl_dy = 1.5, -5.0
    for k in range(4):
        end = (cur[0] + 3.0, cur[1])
        seg = quad(cur, (cur[0] + ctrl_dx, cur[1] + ctrl_dy), end)
        pts += seg if not pts else seg[1:]
        cur = end
        ctrl_dy = -ctrl_dy          # t: the next control point is the reflection of this one
    return pts


# A glyph is a list of items:  ("fill", polygon)  ("stroke", polyline, width)  ("dot", cx, cy, r)
# in the 16 unit box.

def place(points, cx, cy, k):
    """Mockup crown points (centred on x = 0, y in [0, 6]) to box units: scale k about (cx, cy)."""
    return [(cx + k * dx, cy + k * (dy - 3.0)) for dx, dy in points]


def crown(element, cx, cy, k, stroke):
    if element == "fire":
        return [("fill", place(FIRE, cx, cy, k))]
    if element == "earth":
        return [("fill", place(EARTH, cx, cy, k))]
    if element == "water":
        return [("stroke", place(wave(), cx, cy, k), stroke)]
    return [("stroke", place(AIR_LEFT, cx, cy, k), stroke), ("stroke", place(AIR_RIGHT, cx, cy, k), stroke)]


def glyph_crown(element):
    # Fill crowns want a bigger scale (a solid shape reads small); the stroked ones carry their width.
    k = 1.25 if element in ("fire", "earth") else 1.05
    return crown(element, 8.0, 8.0, k, 1.7)


def glyph_set():
    out = []
    for element, (cx, cy) in (("fire", (5.0, 4.6)), ("earth", (11.0, 4.6)),
                              ("water", (5.0, 11.6)), ("air", (11.0, 11.6))):
        out += crown(element, cx, cy, 0.6, 1.2)
    return out


def glyph_recall():
    # A loop arrow: three quarters of a ring, an arrowhead at its end, a solid dot in the middle.
    cx, cy, r = 8.0, 8.0, 5.2
    a0, a1 = math.radians(-50), math.radians(-50 + 290)
    arc = [(cx + r * math.cos(a0 + (a1 - a0) * i / 40), cy + r * math.sin(a0 + (a1 - a0) * i / 40))
           for i in range(41)]
    # tangent at the end (the arc runs clockwise on screen: angle grows, y down)
    tx, ty = -math.sin(a1), math.cos(a1)
    nx, ny = -ty, tx
    tip = (arc[-1][0] + tx * 2.6, arc[-1][1] + ty * 2.6)
    base = arc[-1]
    head = [tip, (base[0] + nx * 2.3, base[1] + ny * 2.3), (base[0] - nx * 2.3, base[1] - ny * 2.3)]
    return [("stroke", arc, 1.9), ("fill", head), ("dot", cx, cy, 1.5)]


GLYPHS = {
    "totem_fire": glyph_crown("fire"),
    "totem_earth": glyph_crown("earth"),
    "totem_water": glyph_crown("water"),
    "totem_air": glyph_crown("air"),
    "totem_set": glyph_set(),
    "totem_recall": glyph_recall(),
}


# ---------------------------------------------------------------------------
# Rasteriser
# ---------------------------------------------------------------------------

def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2


def _inside(px, py, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def rasterise(items, size, scale):
    """Alpha rows for a list of items; `scale` texels per unit. Round caps and joins on strokes."""
    segs, polys, dots = [], [], []
    for item in items:
        if item[0] == "fill":
            polys.append(item[1])
        elif item[0] == "stroke":
            half = item[2] / 2.0
            for a, b in zip(item[1], item[1][1:]):
                segs.append((a[0], a[1], b[0], b[1], half * half,
                             min(a[0], b[0]) - half, min(a[1], b[1]) - half,
                             max(a[0], b[0]) + half, max(a[1], b[1]) + half))
        else:
            dots.append((item[1], item[2], item[3] * item[3]))
    n = SUPERSAMPLE * SUPERSAMPLE
    rows = bytearray()
    for y in range(size):
        for x in range(size):
            hit = 0
            for sy in range(SUPERSAMPLE):
                py = (y + (sy + 0.5) / SUPERSAMPLE) / scale
                for sx in range(SUPERSAMPLE):
                    px = (x + (sx + 0.5) / SUPERSAMPLE) / scale
                    covered = False
                    for poly in polys:
                        if _inside(px, py, poly):
                            covered = True
                            break
                    if not covered:
                        for cx, cy, r2 in dots:
                            if (px - cx) ** 2 + (py - cy) ** 2 <= r2:
                                covered = True
                                break
                    if not covered:
                        for ax, ay, bx, by, h2, x0, y0, x1, y1 in segs:
                            if x0 <= px <= x1 and y0 <= py <= y1 and _seg_dist2(px, py, ax, ay, bx, by) <= h2:
                                covered = True
                                break
                    hit += covered
            rows += bytes((255, 255, 255, int(round(hit / n * 255))))
    return bytes(rows)


# ---------------------------------------------------------------------------
# The dotted mold: the button's outline (chamfers top left and bottom right) as round dots
# ---------------------------------------------------------------------------

MOLD_INSET = 3.0
MOLD_CUT = 10.0
MOLD_DOT_R = 1.4
MOLD_PITCH = 6.0


def mold_outline():
    lo, hi, c = MOLD_INSET, MOLD_SIZE - MOLD_INSET, MOLD_CUT
    return [(lo + c, lo), (hi, lo), (hi, hi - c), (hi - c, hi), (lo, hi), (lo, lo + c), (lo + c, lo)]


def mold_dots():
    """Evenly spaced dot centres along the closed outline, starting on the top edge."""
    pts = mold_outline()
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    total = sum(lengths)
    count = max(1, round(total / MOLD_PITCH))
    out = []
    for k in range(count):
        d = total * k / count
        for (a, b), length in zip(zip(pts, pts[1:]), lengths):
            if d <= length:
                t = d / length
                out.append(("dot", a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, MOLD_DOT_R))
                break
            d -= length
    return out


def write_tga(path, pixels, size):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    scale = GLYPH_SIZE / VIEWBOX
    for name, items in GLYPHS.items():
        path = os.path.join(here, f"{name}.tga")
        write_tga(path, rasterise(items, GLYPH_SIZE, scale), GLYPH_SIZE)
        print(f"wrote {path} ({GLYPH_SIZE}x{GLYPH_SIZE}, {os.path.getsize(path)} bytes)")
    path = os.path.join(here, "totem_mold.tga")
    write_tga(path, rasterise(mold_dots(), MOLD_SIZE, 1.0), MOLD_SIZE)
    print(f"wrote {path} ({MOLD_SIZE}x{MOLD_SIZE}, {os.path.getsize(path)} bytes)")
