#!/usr/bin/env python3
"""Generates the four 32x32 level tag icons of the Gunsight target box.

Reference: mockups/gunsight-level-tag-2026-10-08.html, concept B ("crown and glint"). The
crown and skull outlines are the mockup's SVG paths (CROWN_BODY, CROWN_BASE, SKULL), scaled
to the 32 texel canvas. The user then replaced B's four-point glint with a clear five-point
STAR, so the rare icon and the rare elite shoulder mark are stars, not sparkles.

Files written (in forever-stuwave/Media/Textures), and the classification that wears each:

    level_crown.tga        elite       three-spike crown on a base bar        tint gold
    level_star.tga         rare        five-point star                        tint silver
    level_crown_star.tga   rareelite   crown with a small star on its shoulder  BAKED, do not tint
    level_skull.tga        worldboss   skull, eyes and nose cut out           tint red

Colour. The first, second and fourth are white with the shape in alpha, tinted in Lua with
SetVertexColor like every other HUD texture. The rare elite icon needs two colours at once
(gold crown, silver star) and a texture has only one vertex colour, so that one file has the
colours baked into RGB: draw it with SetVertexColor(1, 1, 1) (or leave the default). Tint
values, from the mockup's palette:

    gold   #ffd23f  (1.000, 0.824, 0.247)
    silver #ccced7  (0.800, 0.808, 0.843)   shipped steel #8d93a6 mixed 55% to white
    red    #ff3b4e  (1.000, 0.231, 0.306)

Every glyph fills the full 32 texel width of the canvas and is centred vertically, so each
file is a square texture holding a glyph that is wider than it is tall. Draw each at the
square size listed below (addon units, on the 15 tall tag plate) and the shape comes out
undistorted at its natural aspect:

    level_crown       11 x 11   (crown 11 wide, 9 tall)
    level_star        10 x 10
    level_crown_star  14 x 14   (crown plus star badge, 14 wide, 10.7 tall)
    level_skull       11 x 11

Shapes are chunky on purpose (the star's inner radius is 0.48 of the outer, chunkier than a
regular pentagram) because they are shown at 10 to 14 px.

The star badge on the crown knocks a 0.8 unit gap out of the crown around itself, the texture
version of the mockup's plate coloured halo, so it needs no knowledge of the plate colour.

Pure stdlib, matching the other generators here. Output per file: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_level_icons.py
"""

import math
import os
import struct

SIZE = 32
SUPERSAMPLE = 6

GOLD = (255, 210, 63)
SILVER = (204, 206, 215)

# ---- geometry helpers (all in texel coordinates, 0..32) -----------------------------


def _poly_contains(poly, px, py):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _seg_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _near_poly(poly, px, py, dist):
    """True when the point is inside the polygon or within `dist` of its outline."""
    if _poly_contains(poly, px, py):
        return True
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if _seg_dist(ax, ay, bx, by, px, py) <= dist:
            return True
    return False


def _bezier(p0, p1, p2, p3, steps=12):
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return out


class Box:
    """Maps a glyph drawn in `w` x `h` design units onto the 32 texel canvas.

    The unit scale is SIZE / w (the glyph fills the canvas width) and the glyph is centred
    vertically.
    """

    def __init__(self, w, h):
        self.s = SIZE / w
        self.ox = 0.0
        self.oy = (SIZE - h * self.s) / 2.0

    def pt(self, x, y):
        return (self.ox + x * self.s, self.oy + y * self.s)

    def poly(self, pts):
        return [self.pt(x, y) for x, y in pts]


# ---- shapes ---------------------------------------------------------------------------


def star_points(cx, cy, outer, ratio=0.48):
    """Five-point star, one point straight up; `ratio` is inner radius over outer."""
    pts = []
    for i in range(10):
        ang = math.radians(-90 + 36 * i)
        r = outer if i % 2 == 0 else outer * ratio
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


# Mockup CROWN_BODY (spikes), in the mockup's 11 x 9 box. The mockup leaves a 1.2 unit gap
# between the body and a separate base bar; at 11 px that gap lands between pixel rows and
# smears into a half dark band, so here the crown is one solid shape: the same spike outline
# running down to the base bar's bottom edge.
CROWN = [(0.9, 9.0), (0.0, 1.4), (3.2, 4.4), (5.5, 0.0), (7.8, 4.4), (11.0, 1.4), (10.1, 9.0)]


def _skull_outline():
    """Mockup SKULL outer path in its 10 x 10 box (cranium curve, jaw with teeth notches)."""
    pts = [(5.0, 0.2)]
    pts += _bezier((5.0, 0.2), (7.9, 0.2), (9.8, 2.1), (9.8, 4.5))
    pts += _bezier((9.8, 4.5), (9.8, 6.1), (9.0, 7.0), (8.2, 7.5))
    pts += [(8.2, 9.8), (6.8, 9.8), (6.8, 8.6), (5.6, 8.6), (5.6, 9.8), (4.4, 9.8), (4.4, 8.6),
            (3.2, 8.6), (3.2, 9.8), (1.8, 9.8), (1.8, 7.5)]
    pts += _bezier((1.8, 7.5), (1.0, 7.0), (0.2, 6.1), (0.2, 4.5))
    pts += _bezier((0.2, 4.5), (0.2, 2.1), (2.1, 0.2), (5.0, 0.2))
    return pts


def _circle(cx, cy, r, n=24):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


# ---- icon definitions ------------------------------------------------------------------
# Each icon is a function (px, py) -> (crown, star) membership, or a single "mono" test.


def make_crown():
    box = Box(11.0, 9.0)
    crown = box.poly(CROWN)
    return lambda px, py: _poly_contains(crown, px, py)


def make_star():
    box = Box(10.0, 9.5)
    # outer radius 5.26: the star is 1.902 R wide (10 units) and 1.809 R tall (9.5 units).
    star = box.poly(star_points(5.0, 5.26, 5.26))
    return lambda px, py: _poly_contains(star, px, py)


def make_skull():
    box = Box(10.0, 10.0)
    outline = box.poly(_skull_outline())
    holes = [
        box.poly(_circle(3.45, 4.6, 1.5)),
        box.poly(_circle(6.55, 4.6, 1.5)),
        box.poly([(5.0, 5.9), (4.35, 7.2), (5.65, 7.2)]),
    ]

    def inside(px, py):
        if not _poly_contains(outline, px, py):
            return False
        return not any(_poly_contains(h, px, py) for h in holes)

    return inside


def make_crown_star():
    """Returns (crown test, star test) in a 14 x 10.7 box: the full 11 x 9 crown top left, the
    star as a badge over its lower right end, hanging a little below the base and clear of all
    three spike tips."""
    box = Box(14.0, 10.7)
    crown_poly = box.poly(CROWN)
    star = box.poly(star_points(10.55, 7.55, 3.5))
    gap = 0.8 * box.s

    def crown(px, py):
        if _near_poly(star, px, py, gap):
            return False
        return _poly_contains(crown_poly, px, py)

    def star_test(px, py):
        return _poly_contains(star, px, py)

    return crown, star_test


# ---- rasteriser -------------------------------------------------------------------------


def _coverage(test, x, y):
    total = 0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            if test(px, py):
                total += 1
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def _mono_rows(test):
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(test, x, y) * 255))))
    return rows


def _crown_star_rows():
    crown, star = make_crown_star()
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            c = _coverage(crown, x, y)
            s = _coverage(star, x, y)
            alpha = s + c * (1.0 - s)
            if alpha <= 0:
                rows += bytes((255, 255, 255, 0))
                continue
            rgb = [(s * SILVER[i] + c * (1.0 - s) * GOLD[i]) / alpha for i in range(3)]
            rows += bytes((int(round(rgb[0])), int(round(rgb[1])), int(round(rgb[2])),
                           int(round(alpha * 255))))
    return rows


def _write(out_dir, name, rows):
    path = os.path.join(out_dir, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def _bgra_from_rgba_rows(rows):
    """Texture rows are written B, G, R, A; the mono rows are symmetric, crown/star is not."""
    out = bytearray(rows)
    for i in range(0, len(out), 4):
        out[i], out[i + 2] = out[i + 2], out[i]
    return out


def main():
    out_dir = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    _write(out_dir, "level_crown", _mono_rows(make_crown()))
    _write(out_dir, "level_star", _mono_rows(make_star()))
    _write(out_dir, "level_crown_star", _bgra_from_rgba_rows(_crown_star_rows()))
    _write(out_dir, "level_skull", _mono_rows(make_skull()))


if __name__ == "__main__":
    main()
