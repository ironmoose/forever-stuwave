#!/usr/bin/env python3
"""Generates the line art soul shard textures of the Gunsight combat HUD.

Reference: addons/ForeverSynthwave/mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html,
SH_GLYPH and drawShards(). The brief was a line art version of the actual soulshard icon:
an elongated faceted crystal leaning right with a sharp point at the bottom. CombatHud.lua stacks
four textures per held shard and tints each one, nothing is baked in colour (white RGB, shape in
alpha, like generate_hud_diamond.py):

    hud_shard_glow.tga    64x64    soft violet halo of the outline (drawn first, behind everything)
    hud_shard_line.tga    64x128   the outline stroke (violet in Lua)
    hud_shard_fill.tga    64x128   the lit top facet as a solid polygon (violet at alpha .3 in Lua)
    hud_shard_facet.tga   64x128   the three interior facet lines (violet mixed 45% to white in Lua)

GEOMETRY. The glyph lives in a 0..1 box (x right, y down) that is SH_W x SH_H = 10 x 18 addon
units; the points below are the mockup's SH_GLYPH, unchanged. Texture canvases are larger than the
box because the stroke is centred on the path (half of it lies outside) and the halo reaches
further:

    line, fill, facet   LINE_CANVAS = 16 x 32 units at 4 texels per unit (64 x 128),
                        the box centred. Lua draws them 16 x 32 design px times the UI scale,
                        centred on the shard's 10 x 18 cell.
    glow                GLOW_CANVAS = 40 x 40 units at 1.6 texels per unit (64 x 64), box centred.

Every dimension is a power of two (WoW refuses other file textures).

STROKES. The mockup draws strokes in canvas px at LW = 1.3 * 2000 / 1400 (its W is 2000 and the
stroke is 1.3 screen px at a 1400 wide view), outline LW * 1.1, facets LW * 0.8, with round line
caps and miter joins. One addon unit is U = 1 / 1.28 canvas px, so in addon units the outline is
2.6 wide and the facets 1.9. The halo is the mockup's HALO table: four nested round-join strokes
of width outline + 2 * reach, reach 1.5, 3.2, 5 and 7 canvas px, alpha .26, .17, .10, .055, times
the glow strength .5 the mockup passes for the shards. They are composited here into one alpha
and blurred a little, the soft falloff a texture can hold.

Pure stdlib, supersampled coverage like the other generators. Output: 18-byte header, image type
2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_hud_shard.py
"""

import math
import os
import struct

SUPERSAMPLE = 6

# --- the mockup's glyph, 0..1 box coordinates -------------------------------------------------
OUTLINE = [(.42, 0), (1, .17), (.86, .64), (.30, 1), (0, .55), (.08, .21)]
FACETS = [((.08, .21), (.56, .25)), ((.56, .25), (1, .17)), ((.56, .25), (.30, 1))]
LIT = [(.42, 0), (1, .17), (.56, .25), (.08, .21)]

# --- sizes, addon units ------------------------------------------------------------------------
SH_W, SH_H = 10.0, 18.0
GRID = 1.28                                    # addon units per canvas px, the mockup's 1 / U
LW = 1.3 * 2000 / 1400                         # the mockup's base line width, canvas px
OUTLINE_W = LW * 1.1 * GRID                    # 2.61 units
FACET_W = LW * 0.8 * GRID                      # 1.90 units
HALO = [(1.5, .26), (3.2, .17), (5.0, .10), (7.0, .055)]   # reach canvas px, alpha
HALO_STRENGTH = 0.5                            # glow(K.violet, .5)
GLOW_BLUR_SIGMA = 1.0                          # addon units

# Texture canvases: (texels wide, texels high, units wide, units high)
LINE_TEX = (64, 128, 16.0, 32.0)
GLOW_TEX = (64, 64, 40.0, 40.0)

FILES = {
    "hud_shard_glow": GLOW_TEX,
    "hud_shard_line": LINE_TEX,
    "hud_shard_fill": LINE_TEX,
    "hud_shard_facet": LINE_TEX,
}


# --- geometry helpers --------------------------------------------------------------------------
def _box_points(pts):
    return [(x * SH_W, y * SH_H) for x, y in pts]


def _inside(poly, px, py):
    """Even odd point in polygon."""
    hit = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _offset(poly, d):
    """The closed polygon moved outward by d (inward when d < 0) with miter joins."""
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    sign = 1.0 if area > 0 else -1.0     # outward normal of a CCW (y up) loop is (dy, -dx)
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        normals = []
        for a, b in ((p0, p1), (p1, p2)):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            normals.append((sign * dy / length, -sign * dx / length))
        (n1x, n1y), (n2x, n2y) = normals
        k = d / (1 + n1x * n2x + n1y * n2y)
        out.append((p1[0] + (n1x + n2x) * k, p1[1] + (n1y + n2y) * k))
    return out


def _seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _ring_dist(poly, px, py):
    n = len(poly)
    return min(_seg_dist(px, py, poly[i], poly[(i + 1) % n]) for i in range(n))


def _canvas(tex):
    """(tw, th, uw, uh) -> texels per unit and the box origin in units, the box centred."""
    tw, th, uw, uh = tex
    return tw / uw, th / uh, (uw - SH_W) / 2.0, (uh - SH_H) / 2.0


def _raster(tex, inside):
    """Supersampled coverage of inside(ux, uy) (box units) over the canvas, a th x tw grid of 0..1."""
    tw, th, _, _ = tex
    tpu_x, tpu_y, ox, oy = _canvas(tex)
    grid = []
    for y in range(th):
        row = []
        for x in range(tw):
            total = 0
            for sy in range(SUPERSAMPLE):
                uy = (y + (sy + 0.5) / SUPERSAMPLE) / tpu_y - oy
                for sx in range(SUPERSAMPLE):
                    ux = (x + (sx + 0.5) / SUPERSAMPLE) / tpu_x - ox
                    if inside(ux, uy):
                        total += 1
            row.append(total / (SUPERSAMPLE * SUPERSAMPLE))
        grid.append(row)
    return grid


# --- the four shapes ---------------------------------------------------------------------------
def build_line():
    poly = _box_points(OUTLINE)
    outer = _offset(poly, OUTLINE_W / 2)
    inner = _offset(poly, -OUTLINE_W / 2)
    return _raster(LINE_TEX, lambda x, y: _inside(outer, x, y) and not _inside(inner, x, y))


def build_fill():
    poly = _box_points(LIT)
    return _raster(LINE_TEX, lambda x, y: _inside(poly, x, y))


def build_facet():
    segs = [(_box_points([a])[0], _box_points([b])[0]) for a, b in FACETS]
    r = FACET_W / 2
    return _raster(LINE_TEX, lambda x, y: any(_seg_dist(x, y, a, b) <= r for a, b in segs))


def _blur(grid, sigma):
    radius = int(math.ceil(sigma * 3))
    k = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(k)
    k = [v / total for v in k]
    h, w = len(grid), len(grid[0])
    mid = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            mid[y][x] = sum(k[i + radius] * grid[y][min(w - 1, max(0, x + i))] for i in range(-radius, radius + 1))
    out = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            out[y][x] = sum(k[i + radius] * mid[min(h - 1, max(0, y + i))][x] for i in range(-radius, radius + 1))
    return out


def build_glow():
    poly = _box_points(OUTLINE)
    tw, th, _, _ = GLOW_TEX
    tpu_x, tpu_y, ox, oy = _canvas(GLOW_TEX)
    layers = [(reach * GRID + OUTLINE_W / 2, a * HALO_STRENGTH) for reach, a in HALO]
    grid = []
    for y in range(th):
        row = []
        for x in range(tw):
            d = _ring_dist(poly, (x + 0.5) / tpu_x - ox, (y + 0.5) / tpu_y - oy)
            rest = 1.0
            for limit, a in layers:
                if d <= limit:
                    rest *= 1 - a
            row.append(1 - rest)
        grid.append(row)
    return _blur(grid, GLOW_BLUR_SIGMA * tpu_x)


BUILDERS = {
    "hud_shard_glow": build_glow,
    "hud_shard_line": build_line,
    "hud_shard_fill": build_fill,
    "hud_shard_facet": build_facet,
}


def write_tga(path, grid):
    h, w = len(grid), len(grid[0])
    rows = bytearray()
    for row in grid:
        for cov in row:
            rows += bytes((255, 255, 255, int(round(max(0.0, min(1.0, cov)) * 255))))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({w}x{h}, {os.path.getsize(path)} bytes)")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    for name, build in BUILDERS.items():
        write_tga(os.path.join(here, name + ".tga"), build())


if __name__ == "__main__":
    main()
