"""The hand drawn line shapes the micro menu's Character and Legacy keys are baked from.

These two have no static Blizzard art (Blizzard draws a live portrait on Character, and Legacy is a crowned
shield), so tools/assets/synthwave_icons.py rasterises them here, in memory, and bakes them into the same
gradient art as the other keys (glyphart_character.tga, glyphart_legacy.tga). Nothing in this module is written
to the addon: the old per glyph glyph_<name>.tga files were line art tinted at run time and are gone.

    glyph_character   person bust
    glyph_legacy      three-point crown over a heater shield, right half solid

Clean line shapes: stroke 2.2px at 32px with round caps and joins, about 4px of padding, drawn upright.
`render(name)` returns the shape's coverage as a SIZE x SIZE list of rows of 0..1 floats.

Pure stdlib.
"""

import math

SIZE = 32
SUPERSAMPLE = 4
STROKE = 2.2
HALF = STROKE / 2.0


# ---------------------------------------------------------------------------
# Shape primitives. A glyph is a list of strokes (polylines drawn with round
# caps) and fills (polygons). Everything is in 32x32 pixel space, y down.
# ---------------------------------------------------------------------------

def stroke(points, closed=False, width=STROKE):
    pts = list(points)
    if closed:
        pts.append(pts[0])
    return ("stroke", pts, width / 2.0)


def fill(points):
    return ("fill", list(points), 0.0)


def dot(cx, cy, r):
    """A filled round dot: a zero-length stroke of diameter 2r."""
    return ("stroke", [(cx, cy), (cx, cy)], r)


def arc_points(cx, cy, r, a0, a1, rx=None, ry=None, steps=None):
    """Points along an elliptical arc, angles in degrees, y down."""
    rx = r if rx is None else rx
    ry = r if ry is None else ry
    steps = steps or max(8, int(abs(a1 - a0) / 6))
    out = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps)
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


def circle(cx, cy, r):
    return stroke(arc_points(cx, cy, r, 0, 360, steps=48))


def ellipse_fill(cx, cy, rx, ry, rot_deg=0.0):
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    pts = []
    for i in range(40):
        a = 2 * math.pi * i / 40
        x, y = rx * math.cos(a), ry * math.sin(a)
        pts.append((cx + x * c - y * s, cy + x * s + y * c))
    return fill(pts)


def bezier(p0, p1, p2, steps=24):
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def link(a, b, ra, rb, gap=1.3):
    """A line between two hollow circles, stopped short of each rim."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    s = ra + HALF + gap
    e = rb + HALF + gap
    return stroke([(a[0] + ux * s, a[1] + uy * s), (b[0] - ux * e, b[1] - uy * e)])


def rounded_rect(x0, y0, x1, y1, r):
    pts = []
    pts += arc_points(x1 - r, y0 + r, r, -90, 0, steps=6)
    pts += arc_points(x1 - r, y1 - r, r, 0, 90, steps=6)
    pts += arc_points(x0 + r, y1 - r, r, 90, 180, steps=6)
    pts += arc_points(x0 + r, y0 + r, r, 180, 270, steps=6)
    return stroke(pts, closed=True)


# ---------------------------------------------------------------------------
# The shapes
# ---------------------------------------------------------------------------


def glyph_character():
    return [
        circle(16, 10.5, 5.0),
        stroke(arc_points(16, 27.5, 0, 180, 360, rx=10.5, ry=9.5), closed=True),
    ]



def glyph_legacy():
    # Blizzard's Legacy icon: a crowned heater shield with a light/dark split
    # down the middle. Here the left half is outline and the right half solid,
    # and the crown is solid, so both survive 16px.
    top = 14.2
    left_side = bezier((7.5, top), (7.5, 24.0), (16.0, 28.2))
    right_side = bezier((24.5, top), (24.5, 24.0), (16.0, 28.2))
    outline = [(16.0, top), (7.5, top)] + left_side + right_side[::-1] + [(24.5, top)]
    solid = [(16.0, top), (24.5, top)] + right_side + [(16.0, 28.2)]
    # Crown is a plain fill (no stroke), so its points stay sharp at 16px.
    crown = [(9.6, 10.6), (9.6, 4.0), (13.0, 7.6), (16.0, 3.0),
             (19.0, 7.6), (22.4, 4.0), (22.4, 10.6)]
    return [
        stroke(outline, closed=True),
        fill(solid),
        stroke([(16.0, top), (16.0, 28.2)]),
        fill(crown),
    ]



# ---------------------------------------------------------------------------
# Rasteriser
# ---------------------------------------------------------------------------

def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


def _in_polygon(px, py, pts):
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _prepare(shapes):
    segs = []      # (ax, ay, bx, by, r2, minx, miny, maxx, maxy)
    polys = []
    for kind, pts, r in shapes:
        if kind == "stroke":
            for a, b in zip(pts, pts[1:]):
                segs.append((a[0], a[1], b[0], b[1], r * r,
                             min(a[0], b[0]) - r, min(a[1], b[1]) - r,
                             max(a[0], b[0]) + r, max(a[1], b[1]) + r))
        else:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            polys.append((pts, min(xs), min(ys), max(xs), max(ys)))
    return segs, polys


def _inside(px, py, segs, polys):
    for ax, ay, bx, by, r2, x0, y0, x1, y1 in segs:
        if x0 <= px <= x1 and y0 <= py <= y1 and _seg_dist2(px, py, ax, ay, bx, by) <= r2:
            return True
    for pts, x0, y0, x1, y1 in polys:
        if x0 <= px <= x1 and y0 <= py <= y1 and _in_polygon(px, py, pts):
            return True
    return False


def build(shapes):
    segs, polys = _prepare(shapes)
    rows = bytearray()
    n = SUPERSAMPLE * SUPERSAMPLE
    for y in range(SIZE):
        for x in range(SIZE):
            hits = 0
            for sy in range(SUPERSAMPLE):
                py = y + (sy + 0.5) / SUPERSAMPLE
                for sx in range(SUPERSAMPLE):
                    if _inside(x + (sx + 0.5) / SUPERSAMPLE, py, segs, polys):
                        hits += 1
            rows += bytes((255, 255, 255, int(round(hits / n * 255))))
    return bytes(rows)



SHAPES = {"character": glyph_character, "legacy": glyph_legacy}


def render(name):
    """Coverage (0..1) of the named shape, SIZE rows of SIZE floats, top row first."""
    flat = build(SHAPES[name]())
    return [[flat[(y * SIZE + x) * 4 + 3] / 255.0 for x in range(SIZE)] for y in range(SIZE)]
