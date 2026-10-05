#!/usr/bin/env python3
"""Generates the cast bar chevron textures (solid neon chevrons, pointing RIGHT).

Reference: addons/ForeverSTUwave/mockups/castbar-v2-chevrons-locked-2026-10-01.html,
card H ("Solid chevrons"), function segsChev() and the "outline" caret in
placeShapedCaret(). Parker locked that look; the shared cast bar Lua engine
draws these textures (mirrored with SetTexCoord for channels, tinted with
SetVertexColor, nothing is baked in colour).

Outputs (all white RGB, shape in alpha, so Lua tints per use):

    cast_chevron_fill.tga      64x64    one solid chevron segment.
    cast_chevron_outline.tga   64x64    the hollow outline of the same chevron, a
                                        white stroke inside the same 64x64 box.
                                        The leading caret core.
    cast_chevron_glow.tga      128x128  soft halo of that outline (ADD blend, tint
                                        cyan, drawn behind the outline). The
                                        chevron box sits centred, so the pad is
                                        GLOW_PAD = 32 texels on every side:
                                        draw it (1 + 2 * 32/64) = 2x the chevron's
                                        on-screen size, centred on the chevron.
    cast_chevron_burst.tga     128x128  solid chevron plus a soft glow edge, for the
                                        lock-in burst glyph. Same centred box and
                                        same 32 texel pad as the glow.
    cast_chevron_strip.tga     32x16    horizontally tileable strip of 2 chevrons
                                        (16 texel pitch) for the secret-timing
                                        fallback. StatusBar fill texture with
                                        SetHorizTile; tiles seamlessly.

GEOMETRY (from segsChev; h is the bar run height, the chevron is h tall):

    polygon  (0,0) (d,0) (d+ah,h/2) (d,h) (0,h) (ah,h/2)
    ah = h/2   45 degree arms: depth equals the half height, so the tip and the
               notch are both h/2 deep
    d          arm depth. The prototype uses d = h/2 (9 of 18 player, 5 of 10 pet),
               so one chevron is d + ah = h wide: ASPECT 1:1
    pitch      d + gap, the next chevron's tip sits in this one's notch. The
               prototype gap is 3 of an 18 high player run (1/6 of h) and 2 of a
               10 high pet run (1/5); GAP_FRACTION below is the player value.

The fill, outline, glow and burst use the prototype ratios exactly (d = h/2).
The STRIP cannot: SetHorizTile repeats the file at its native pixel width, WoW
needs power-of-two sizes, and 2 prototype chevrons span 4/3 of h (not a power
of two for any power-of-two h). So the strip uses a 32x16 tile with a 16 texel
pitch, keeps the 45 degree arms, and gives up a thicker arm (d = 13) and a gap
of 3 for the period. It is a fallback look, not pixel-matched to the segments.

Antialiasing: supersampled coverage, same technique as
generate_pet_cast_triangle.py. Glow: separable gaussian blur of the shape
coverage, pure stdlib.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_cast_chevron.py
"""

import math
import os
import struct

SUPERSAMPLE = 6

# --- fill / outline / glow / burst: the prototype ratios, h = BOX ------------
BOX = 64                 # chevron box, texels (width == height, aspect 1:1)
ARM = BOX // 2           # d: arm depth (h/2)
TIP = BOX // 2           # ah: tip and notch depth (h/2)
# Outline stroke, texels, drawn INSIDE the box (the polygon's own bounds).
# Prototype strokes are 2 of 18 (player) and 1 of 10 (pet), about 0.1 of h.
STROKE = 7.0
# Glow canvas: the box centred with GLOW_PAD texels of room on every side.
# MUST match Theme.CAST_CHEVRON_GLOW_PAD / CAST_CHEVRON_GLOW_PAD_FRACTION.
GLOW_PAD = 32
GLOW_SIZE = BOX + 2 * GLOW_PAD
# Gaussian sigma in texels (prototype blur is about 0.12 of h) and the alpha
# gain on the blurred outline so the halo reads on a dark bar.
GLOW_SIGMA = 8.0
GLOW_GAIN = 1.8
BURST_GAIN = 1.2

# --- strip -------------------------------------------------------------------
STRIP_W = 32
STRIP_H = 16
STRIP_PITCH = STRIP_W // 2       # 2 chevrons per tile
STRIP_TIP = STRIP_H // 2         # 45 degree arms
STRIP_ARM = STRIP_PITCH - 3      # d = 13: pitch minus a 3 texel gap


def chevron_polygon(h, arm, tip, ox=0.0, oy=0.0):
    return [
        (ox, oy), (ox + arm, oy), (ox + arm + tip, oy + h / 2.0),
        (ox + arm, oy + h), (ox, oy + h), (ox + tip, oy + h / 2.0),
    ]


def _inside(poly, px, py):
    """Even-odd point-in-polygon (ray to +x)."""
    n = len(poly)
    c = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            if px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
                c = not c
    return c


def _dist_to_edges(poly, px, py):
    best = 1e9
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))
    return best


def _coverage_grid(width, height, hit):
    """Supersampled coverage in [0, 1] for hit(px, py) over a width x height grid."""
    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            n = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    if hit(x + (sx + 0.5) / SUPERSAMPLE, y + (sy + 0.5) / SUPERSAMPLE):
                        n += 1
            row.append(n / (SUPERSAMPLE * SUPERSAMPLE))
        grid.append(row)
    return grid


def _blur(grid, sigma):
    radius = int(math.ceil(sigma * 3))
    kernel = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]
    h, w = len(grid), len(grid[0])

    def conv_rows(g):
        out = []
        for row in g:
            new = []
            for x in range(w):
                s = 0.0
                for i, k in enumerate(kernel):
                    xx = x + i - radius
                    if 0 <= xx < w:
                        s += row[xx] * k
                new.append(s)
            out.append(new)
        return out

    horiz = conv_rows(grid)
    cols = [list(c) for c in zip(*horiz)]
    cols = conv_rows(cols)
    return [list(r) for r in zip(*cols)]


def _pad(grid, pad, size):
    out = [[0.0] * size for _ in range(size)]
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            out[y + pad][x + pad] = v
    return out


def build_fill():
    poly = chevron_polygon(BOX, ARM, TIP)
    return _coverage_grid(BOX, BOX, lambda px, py: _inside(poly, px, py))


def build_outline():
    poly = chevron_polygon(BOX, ARM, TIP)
    return _coverage_grid(
        BOX, BOX,
        lambda px, py: _inside(poly, px, py) and _dist_to_edges(poly, px, py) <= STROKE,
    )


def build_glow():
    blurred = _blur(_pad(build_outline(), GLOW_PAD, GLOW_SIZE), GLOW_SIGMA)
    return [[min(1.0, v * GLOW_GAIN) for v in row] for row in blurred]


def build_burst():
    solid = _pad(build_fill(), GLOW_PAD, GLOW_SIZE)
    blurred = _blur(solid, GLOW_SIGMA)
    return [
        [max(s, min(1.0, b * BURST_GAIN)) for s, b in zip(srow, brow)]
        for srow, brow in zip(solid, blurred)
    ]


def build_strip():
    """2 chevrons per tile. The pattern repeats every STRIP_PITCH columns, so
    each column is rendered from its position within one pitch (x % pitch) and
    the copy that leaves the pitch window wraps in via the -pitch chevron. That
    makes column x and column x + pitch identical by construction, which is what
    makes the tile seamless."""
    polys = [chevron_polygon(STRIP_H, STRIP_ARM, STRIP_TIP, ox) for ox in (0, -STRIP_PITCH)]
    grid = []
    for y in range(STRIP_H):
        row = []
        for x in range(STRIP_W):
            xm = x % STRIP_PITCH
            n = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    px = xm + (sx + 0.5) / SUPERSAMPLE
                    py = y + (sy + 0.5) / SUPERSAMPLE
                    if any(_inside(p, px, py) for p in polys):
                        n += 1
            row.append(n / (SUPERSAMPLE * SUPERSAMPLE))
        grid.append(row)
    return grid


def write_tga(path, grid):
    height, width = len(grid), len(grid[0])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    rows = bytearray()
    for row in grid:
        for v in row:
            rows += bytes((255, 255, 255, int(round(v * 255))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    write_tga(os.path.join(here, "cast_chevron_fill.tga"), build_fill())
    write_tga(os.path.join(here, "cast_chevron_outline.tga"), build_outline())
    write_tga(os.path.join(here, "cast_chevron_glow.tga"), build_glow())
    write_tga(os.path.join(here, "cast_chevron_burst.tga"), build_burst())
    write_tga(os.path.join(here, "cast_chevron_strip.tga"), build_strip())


if __name__ == "__main__":
    main()
