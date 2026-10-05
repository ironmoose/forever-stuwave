#!/usr/bin/env python3
"""Generates the seven 64x64 Paladin seal sigils for the Seal Chamber lens.

Files written (all next to this script):

    seal_glyph_righteousness.tga   scales
    seal_glyph_crusader.tga        crossed swords
    seal_glyph_fury.tga            a flame inside a flame
    seal_glyph_command.tga         crown
    seal_glyph_light.tga           sun
    seal_glyph_wisdom.tga          eye
    seal_glyph_justice.tga         gavel on its block

Source of truth: the GLYPH table in mockups/gunsight-hud-v2-2026-10-02/ (line art in a unit box,
x and y from -1 to 1 around the centre, scaled by r) and drawSealChamber, which strokes the
active seal's glyph at the lens centre with r = SC_GR * .56 = 28 image px and a line width of
LW * 1.6, round joins and round caps. The paths below are a literal port of those calls
(m / l / q / b / c / z); media/test_tga_generators.py parses the mockup's own GLYPH source and
checks the baked alpha against it, so a typo here or a swapped glyph fails there.

Scale: 28 texels per unit, so 1 texel is exactly 1 mockup image px and the 64 texel canvas is a
64 image px square centred on the glyph origin (the lens centre). A caller that draws the glyph
at radius r image px sizes the texture to 64/28 * r image px square and centres it where the
mockup centres the glyph. The line width is the mockup's: LW is 1.3 screen px at the mockup's
default 1400 px wide preview of its 2000 px canvas, 1.3 * 2000 / 1400 = 1.857 image px, so the
glyph stroke is 1.6 * 1.857 = 2.971 texels. The widest extent (the scales and the eye reach
1.02 units) plus half the stroke is 30.1 texels, so every stroke ends inside the 32 texel
half canvas.

Same convention as generate_deck_glyphs.py: crisp line art, anti-aliased, NO baked glow (the
mockup's glow is a shadow blur that the Lua side stands in for with a second, larger, dim ADD
copy), shape in the alpha channel with white RGB, tinted with SetVertexColor.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28 (top-left origin,
8 alpha bits), BGRA top-to-bottom.

    python generate_seal_glyphs.py
"""

import math
import os
import struct

SIZE = 64
SUPERSAMPLE = 4
CENTRE = SIZE / 2.0

SC_GR = 50.0                    # the lens radius, image px
GLYPH_R = SC_GR * 0.56          # the glyph's unit radius in image px (28)
TEXELS_PER_IMAGE_PX = SIZE / 64.0
UNIT = GLYPH_R * TEXELS_PER_IMAGE_PX   # texels per glyph unit
LW = 1.3 * 2000.0 / 1400.0      # the mockup's line width in image px at its default 1400 px preview
STROKE = 1.6 * LW * TEXELS_PER_IMAGE_PX
HALF = STROKE / 2.0

CURVE_STEPS = 32
CIRCLE_STEPS = 96


class Path:
    """Records what the mockup's G(cx, cy, r) records, as polylines in texel space."""

    def __init__(self):
        self.lines = []       # list of point lists
        self.cur = None       # the polyline being built
        self.start = None     # subpath start, for z
        self.pt = None

    def _p(self, x, y):
        return (CENTRE + x * UNIT, CENTRE + y * UNIT)

    def m(self, x, y):
        self.start = self._p(x, y)
        self.pt = self.start
        self.cur = [self.start]
        self.lines.append(self.cur)

    def l(self, x, y):
        self.pt = self._p(x, y)
        self.cur.append(self.pt)

    def q(self, a, b, c, d):
        p0, p1, p2 = self.pt, self._p(a, b), self._p(c, d)
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            u = 1.0 - t
            self.cur.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                             u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
        self.pt = p2

    def b(self, a, b, c, d, e, f):
        p0, p1, p2, p3 = self.pt, self._p(a, b), self._p(c, d), self._p(e, f)
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS
            u = 1.0 - t
            self.cur.append((
                u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
        self.pt = p3

    def c(self, x, y, rr):
        """The mockup's circle: moveTo(x + rr, y) then a full arc."""
        cx, cy = self._p(x, y)
        r = rr * UNIT
        ring = [(cx + r * math.cos(2 * math.pi * i / CIRCLE_STEPS),
                 cy + r * math.sin(2 * math.pi * i / CIRCLE_STEPS)) for i in range(CIRCLE_STEPS + 1)]
        self.start = ring[0]
        self.pt = ring[-1]
        self.cur = ring
        self.lines.append(ring)

    def z(self):
        if self.start is not None and self.cur is not None:
            self.cur.append(self.start)
            self.pt = self.start


# ---------------------------------------------------------------------------
# The glyphs: literal ports of GLYPH.<id> in the mockup.
# ---------------------------------------------------------------------------

def righteousness(g):
    g.m(0, -.78); g.l(0, .8); g.m(-.42, .8); g.l(.42, .8); g.m(-.82, -.5); g.l(.82, -.5)
    g.c(0, -.84, .07)
    g.m(-.82, -.5); g.l(-1, .12); g.m(-.82, -.5); g.l(-.46, .12)
    g.m(-1.02, .12); g.q(-.74, .46, -.44, .12); g.z()
    g.m(.82, -.5); g.l(1, .12); g.m(.82, -.5); g.l(.46, .12)
    g.m(1.02, .12); g.q(.74, .46, .44, .12); g.z()


def crusader(g):
    g.m(.84, -.84); g.l(-.36, .52); g.l(-.52, .36); g.z()
    g.m(-.44, .44); g.l(-.74, .74); g.m(-.66, .14); g.l(-.14, .66); g.c(-.8, .8, .07)
    g.m(-.84, -.84); g.l(.36, .52); g.l(.52, .36); g.z()
    g.m(.44, .44); g.l(.74, .74); g.m(.66, .14); g.l(.14, .66); g.c(.8, .8, .07)


def fury(g):
    g.m(0, -.95)
    g.b(.1, -.6, .62, -.3, .6, .25)
    g.b(.58, .7, .25, .95, 0, .95)
    g.b(-.3, .95, -.62, .7, -.6, .25)
    g.b(-.58, -.1, -.3, -.2, -.25, -.55)
    g.b(-.12, -.45, -.05, -.7, 0, -.95)
    g.m(0, .1)
    g.b(.25, .35, .28, .6, 0, .78)
    g.b(-.28, .6, -.25, .35, 0, .1)


def command(g):
    g.m(-.8, .55); g.l(-.8, -.35); g.l(-.4, .05); g.l(0, -.55); g.l(.4, .05); g.l(.8, -.35)
    g.l(.8, .55); g.z()
    g.m(-.8, .3); g.l(.8, .3)
    g.c(-.8, -.5, .07); g.c(0, -.68, .07); g.c(.8, -.5, .07)


def light(g):
    g.c(0, 0, .36)
    for k in range(8):
        a = k * math.pi / 4
        ro = .74 if k % 2 else .98
        g.m(math.cos(a) * .55, math.sin(a) * .55)
        g.l(math.cos(a) * ro, math.sin(a) * ro)


def wisdom(g):
    g.m(-.98, 0); g.q(0, -.88, .98, 0); g.q(0, .88, -.98, 0); g.z()
    g.c(0, 0, .3); g.c(0, 0, .1)
    g.m(-.55, -.52); g.l(-.7, -.8); g.m(0, -.64); g.l(0, -.95); g.m(.55, -.52); g.l(.7, -.8)


def justice(g):
    hx, hy, ux, uy, vx, vy, a, b = -.3, -.3, .819, -.574, .574, .819, .55, .22
    g.m(hx - a * ux - b * vx, hy - a * uy - b * vy)
    g.l(hx + a * ux - b * vx, hy + a * uy - b * vy)
    g.l(hx + a * ux + b * vx, hy + a * uy + b * vy)
    g.l(hx - a * ux + b * vx, hy - a * uy + b * vy)
    g.z()
    g.m(hx + b * vx, hy + b * vy); g.l(hx + 1.25 * vx, hy + 1.25 * vy)
    g.m(-.2, .95); g.l(.95, .95); g.m(0, .78); g.l(.78, .78)


GLYPHS = {
    "seal_glyph_righteousness": righteousness,
    "seal_glyph_crusader": crusader,
    "seal_glyph_fury": fury,
    "seal_glyph_command": command,
    "seal_glyph_light": light,
    "seal_glyph_wisdom": wisdom,
    "seal_glyph_justice": justice,
}


# ---------------------------------------------------------------------------
# Rasteriser: a stroke is the union of round-capped segments, which is also a round join.
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


def _segments(lines):
    segs = []
    for pts in lines:
        for a, b in zip(pts, pts[1:]):
            segs.append((a[0], a[1], b[0], b[1],
                         min(a[0], b[0]) - HALF, min(a[1], b[1]) - HALF,
                         max(a[0], b[0]) + HALF, max(a[1], b[1]) + HALF))
    return segs


def build(make):
    path = Path()
    make(path)
    segs = _segments(path.lines)
    r2 = HALF * HALF
    n = SUPERSAMPLE * SUPERSAMPLE
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            near = [s for s in segs if s[4] <= x + 1 and s[6] >= x and s[5] <= y + 1 and s[7] >= y]
            hits = 0
            if near:
                for sy in range(SUPERSAMPLE):
                    py = y + (sy + 0.5) / SUPERSAMPLE
                    for sx in range(SUPERSAMPLE):
                        px = x + (sx + 0.5) / SUPERSAMPLE
                        for ax, ay, bx, by, x0, y0, x1, y1 in near:
                            if x0 <= px <= x1 and y0 <= py <= y1 and \
                                    _seg_dist2(px, py, ax, ay, bx, by) <= r2:
                                hits += 1
                                break
            rows += bytes((255, 255, 255, int(round(hits / n * 255))))
    return bytes(rows)


def write_tga(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, make in GLYPHS.items():
        path = os.path.join(here, name + ".tga")
        write_tga(path, build(make))
        print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
