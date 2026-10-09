#!/usr/bin/env python3
"""Generates the nineteen 32x32 deck glyphs (the micro-menu glyphs and the bag bar backpack).

Files written (in forever-stuwave/Media/Textures):

    glyph_character.tga    person bust
    glyph_professions.tga  hammer
    glyph_spellbook.tga    open book
    glyph_talents.tga      three nodes linked (a small tree)
    glyph_legacy.tga       three-point crown over a heater shield, right half solid
    glyph_questlog.tga     scroll with an exclamation mark
    glyph_guild.tga        banner
    glyph_lfd.tga          eye
    glyph_collections.tga  paw print
    glyph_help.tga         question mark in a circle
    glyph_store.tga        coin with a diamond emblem
    glyph_mainmenu.tga     gear
    glyph_achievement.tga  trophy cup with handles on a base
    glyph_ej.tga           compass: ring with a half-filled diagonal needle
    glyph_pvp.tga          crossed swords
    glyph_socials.tga      speech bubble with a tail and three dots
    glyph_worldmap.tga     folded map, three zig-zag panels
    glyph_housing.tga      house: roof, walls and a solid door
    glyph_backpack.tga     backpack: top handle, domed body, flap line and a solid buckle

Style: clean neon LINE icons. Stroke 2.2px at 32px with round caps and joins,
about 4px of padding, drawn upright. They have to stay readable at 16 to 20px
on screen, so there is no fine interior detail; where an outline would go
muddy at that size (paw toes, pupil, dots) the element is filled instead.

There is deliberately no baked glow. The Lua side draws the glyph twice (once
slightly larger and dim with ADD blend), so the strokes here stay crisp.

Shape lives in the alpha channel with white RGB; the caller tints it with
SetVertexColor.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28
(top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_deck_glyphs.py
"""

import math
import os
import struct

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
# The glyphs
# ---------------------------------------------------------------------------

def glyph_character():
    return [
        circle(16, 10.5, 5.0),
        stroke(arc_points(16, 27.5, 0, 180, 360, rx=10.5, ry=9.5), closed=True),
    ]


def glyph_professions():
    # Hammer leaning up and to the right. The head is solid: an outlined head
    # collapses to a smudge at 16px, a filled one still reads as a hammer.
    head = [(27.0, 15.8), (22.3, 20.5), (11.0, 9.2), (15.7, 4.5)]
    return [
        fill(head),
        stroke(head, closed=True),
        stroke([(5.5, 26.5), (17.0, 15.0)]),
    ]


def glyph_spellbook():
    return [
        stroke([(5, 7.5), (16, 10.5), (27, 7.5), (27, 24.5), (16, 27.5), (5, 24.5)],
               closed=True),
        stroke([(16, 10.5), (16, 27.5)]),
    ]


def glyph_talents():
    top, bl, br = (16, 8), (7.5, 23.5), (24.5, 23.5)
    r = 3.6
    return [
        circle(*top, r), circle(*bl, r), circle(*br, r),
        link(top, bl, r, r), link(top, br, r, r), link(bl, br, r, r),
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


def glyph_questlog():
    # Offset rolls (top leans left, bottom leans right) so it reads as a
    # scroll rather than a pillar.
    return [
        rounded_rect(4.5, 4.5, 23.5, 8.5, 2.0),
        rounded_rect(8.5, 23.5, 27.5, 27.5, 2.0),
        stroke([(8.0, 8.5), (8.0, 23.5)]),
        stroke([(24.0, 8.5), (24.0, 23.5)]),
        stroke([(16, 11.8), (16, 17.0)], width=2.6),
        dot(16, 20.4, 1.5),
    ]


def glyph_guild():
    return [
        stroke([(5.5, 5.5), (26.5, 5.5)]),
        stroke([(8.5, 5.5), (8.5, 19.5), (16, 26.5), (23.5, 19.5), (23.5, 5.5)]),
        fill([(16, 10.0), (19.2, 14.0), (16, 18.0), (12.8, 14.0)]),
    ]


def glyph_lfd():
    upper = bezier((3.5, 16), (16, 0.5), (28.5, 16))
    lower = bezier((3.5, 16), (16, 31.5), (28.5, 16))
    return [stroke(upper), stroke(lower), dot(16, 16, 3.9)]


def glyph_collections():
    return [
        ellipse_fill(16, 21.5, 7.6, 6.2),
        ellipse_fill(6.6, 15.0, 2.7, 3.5, -18),
        ellipse_fill(12.0, 8.8, 2.8, 3.7, -6),
        ellipse_fill(20.0, 8.8, 2.8, 3.7, 6),
        ellipse_fill(25.4, 15.0, 2.7, 3.5, 18),
    ]


def glyph_help():
    hook = arc_points(16, 12.4, 3.7, 180, 400)
    hook += [(16, 17.2)]
    return [
        circle(16, 16, 11.4),
        stroke(hook),
        dot(16, 21.6, 1.35),
    ]


def glyph_store():
    return [
        circle(16, 16, 11.4),
        stroke([(16, 8.6), (22.2, 16), (16, 23.4), (9.8, 16)], closed=True),
    ]


def glyph_mainmenu():
    pts = []
    teeth = 8
    pitch = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * pitch - math.pi / 2
        for dr, da in ((8.4, -0.30), (11.6, -0.17), (11.6, 0.17), (8.4, 0.30)):
            pts.append((16 + dr * math.cos(a + da), 16 + dr * math.sin(a + da)))
    return [stroke(pts, closed=True), circle(16, 16, 3.6)]


def glyph_achievement():
    # Cup with two handles, a stem and a flat base. The bowl is one closed
    # outline (the rim is its top edge); handles are open arcs off the walls.
    bowl = [(8.5, 5.5), (8.5, 11.0)]
    bowl += arc_points(16, 11.0, 7.5, 180, 0)
    bowl += [(23.5, 5.5)]
    return [
        stroke(bowl, closed=True),
        stroke(arc_points(8.5, 9.0, 4.2, 90, 270, rx=4.6)),
        stroke(arc_points(23.5, 9.0, 4.2, 90, -90, rx=4.6)),
        stroke([(16, 18.5), (16, 24.5)]),
        stroke([(10.5, 26.5), (21.5, 26.5)]),
    ]


def glyph_ej():
    # Compass: ring plus a needle on the NE-SW diagonal. The north half is
    # solid and the south half an outline so it reads as a needle, not as the
    # store glyph's upright diamond.
    tip = (21.8, 10.2)
    tail = (10.2, 21.8)
    s1, s2 = (18.3, 18.3), (13.7, 13.7)
    return [
        circle(16, 16, 11.4),
        fill([tip, s1, s2]),
        stroke([tip, s1, s2], closed=True),
        stroke([tail, s1, s2], closed=True),
    ]


def glyph_pvp():
    # Two swords crossing, tips at the top corners, hilts at the bottom.
    def sword(sx):
        def x(v):
            return v if sx > 0 else 32 - v
        return [
            stroke([(x(6.0), 6.0), (x(21.0), 21.0)]),
            stroke([(x(23.3), 18.7), (x(18.7), 23.3)]),
            stroke([(x(21.0), 21.0), (x(25.5), 25.5)]),
        ]
    return sword(1) + sword(-1)


def glyph_socials():
    x0, y0, x1, y1, r = 4.5, 5.5, 27.5, 21.5, 4.0
    pts = []
    pts += arc_points(x1 - r, y0 + r, r, -90, 0, steps=6)
    pts += arc_points(x1 - r, y1 - r, r, 0, 90, steps=6)
    pts += [(17.5, y1), (9.5, 27.0), (11.0, y1)]
    pts += arc_points(x0 + r, y1 - r, r, 90, 180, steps=6)
    pts += arc_points(x0 + r, y0 + r, r, 180, 270, steps=6)
    return [
        stroke(pts, closed=True),
        dot(10.5, 13.5, 1.4),
        dot(16.0, 13.5, 1.4),
        dot(21.5, 13.5, 1.4),
    ]


def glyph_worldmap():
    outline = [(4.5, 8.0), (11.5, 5.5), (20.5, 8.5), (27.5, 6.0),
               (27.5, 24.0), (20.5, 26.5), (11.5, 23.5), (4.5, 26.0)]
    return [
        stroke(outline, closed=True),
        stroke([(11.5, 5.5), (11.5, 23.5)]),
        stroke([(20.5, 8.5), (20.5, 26.5)]),
    ]


def glyph_housing():
    # Solid door, like the hammer head: an outlined one muddies at 16px.
    return [
        stroke([(4.5, 15.5), (16, 5.5), (27.5, 15.5)]),
        stroke([(7.5, 13.5), (7.5, 26.5), (24.5, 26.5), (24.5, 13.5)]),
        fill([(13.0, 19.5), (19.0, 19.5), (19.0, 26.5), (13.0, 26.5)]),
    ]


def glyph_backpack():
    # Bag bar backpack slot (19px on screen). A domed rucksack body, a top carry
    # handle, a flap line and a solid buckle on it; the buckle is filled because
    # an outlined one muddies at that size. The flap and buckle sit high so the
    # free-slot count, drawn bottom-right over the icon, lands on the empty
    # pocket area instead of on the buckle.
    body = [(6.5, 24.0), (6.5, 13.0)]
    body += arc_points(16.0, 13.0, 9.5, 180, 360, ry=5.8)
    body += [(25.5, 24.0)]
    body += arc_points(22.5, 24.0, 3.0, 0, 90, steps=4)
    body += arc_points(9.5, 24.0, 3.0, 90, 180, steps=4)
    handle = arc_points(16.0, 6.8, 3.8, 180, 360, ry=3.4)
    return [
        stroke(body, closed=True),
        stroke(handle),
        stroke([(6.5, 15.0), (16.0, 17.8), (25.5, 15.0)]),
        fill([(13.0, 14.0), (19.0, 14.0), (19.0, 19.4), (13.0, 19.4)]),
    ]


GLYPHS = {
    "glyph_character": glyph_character,
    "glyph_professions": glyph_professions,
    "glyph_spellbook": glyph_spellbook,
    "glyph_talents": glyph_talents,
    "glyph_legacy": glyph_legacy,
    "glyph_questlog": glyph_questlog,
    "glyph_guild": glyph_guild,
    "glyph_lfd": glyph_lfd,
    "glyph_collections": glyph_collections,
    "glyph_help": glyph_help,
    "glyph_store": glyph_store,
    "glyph_mainmenu": glyph_mainmenu,
    "glyph_achievement": glyph_achievement,
    "glyph_ej": glyph_ej,
    "glyph_pvp": glyph_pvp,
    "glyph_socials": glyph_socials,
    "glyph_worldmap": glyph_worldmap,
    "glyph_housing": glyph_housing,
    "glyph_backpack": glyph_backpack,
}


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


def write_tga(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    for name, make in GLYPHS.items():
        path = os.path.join(here, name + ".tga")
        write_tga(path, build(make()))
        print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
