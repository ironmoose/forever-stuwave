#!/usr/bin/env python3
"""Generates the VERTICAL cast tape chevron textures (shallow chevrons pointing UP).

Reference: mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html,
drawTape() and chevPath(cx, ay, hw, d, t). The Gunsight HUD's two cast tapes are
columns of 20 up-pointing chevrons that light from the bottom. Sibling of
generate_cast_chevron.py (the horizontal bar chevrons, pointing RIGHT); same
variant set, same file idiom, same Lua use: white RGB, shape in alpha, tinted per
use with SetVertexColor, nothing baked in colour.

Outputs:

    cast_chevron_up_fill.tga     64x32    one solid tape chevron.
    cast_chevron_up_outline.tga  64x32    the hollow caret chevron (stroke inside its
                                          own polygon). The caret in drawTape is a
                                          bigger, thicker chevron than the tape
                                          ones, so it has its own polygon.
    cast_chevron_up_glow.tga     128x64   soft halo of the outline (ADD blend, tint).
                                          The box sits centred, pad GLOW_PAD_X = 32
                                          and GLOW_PAD_Y = 16 texels: draw it 2x the
                                          chevron's on-screen size, centred on it.
    cast_chevron_up_burst.tga    128x64   solid tape chevron plus a soft glow edge for
                                          the lock-in burst at the end cap. Same
                                          centred box and pad as the glow.
    cast_chevron_up_strip.tga    32x16    vertical tile, ONE chevron per 16 texel
                                          pitch, for the engine-timed StatusBar fill
                                          (SetVertTile). Tiles seamlessly.

ONE TEXTURE SERVES BOTH TAPES (the simpler choice). The player tape uses half
width hw 10 and the target tape hw 14 (image px, design = image x 1.28). The
chevron depth d (8) and thickness t (5.5) are the same for both, so the two shapes
are the same polygon stretched horizontally: a horizontal stretch scales every
vertex x and leaves every y alone, which is exactly the change from hw 14 to hw 10
(arm slope d / hw goes from 8/14 to 8/10). So there is one texture per variant,
drawn for the wide (hw 14) chevron and sized in Lua to the tape's own width; two
sets would only duplicate pixels. The fill and burst are exact at both widths.
The outline is exact too up to its stroke, which thins a little on the slanted
arms at the narrow width (a stretched stroke, not a re-stroked one).

GEOMETRY, all fractions of the box (so Lua sizes the box and the shape follows):

    chevPath, tape chevron   tip (cx, ay), arm ends (cx +- hw, ay + d), arm feet
                             (cx +- hw, ay + d + t), notch (cx, ay + t)
                             box 2 hw wide, d + t = 13.5 high; d / box = 8 / 13.5
    chevPath, caret          drawn with (hw + 3, d + 1, t = 7): box 2 (hw + 3) wide,
                             16 high; d / box = 9 / 16

Sizing in Lua (design units, image x 1.28): tape chevron box = (2 hw x 1.28) wide by
17.28 high; caret box = (2 (hw + 3) x 1.28) wide by 20.48 high. Mockup pitch is
12.2 image px = 15.6 design.

STRIP: SetVertTile repeats the file at its native pixel height, and WoW needs power
of two sizes. The mockup pitch is 12.2 image px, so the tile is 16 texels per
chevron with d and t scaled by 16 / 12.2 (d 10.49, t 7.21, a chevron 17.7 tall that
nests into the next one) and the chevron spans the full 32 texel width, which
Lua stretches to the tape width. To land the pitch exactly on the mockup's 15.6
design units, scale the strip bar by 15.616 / 16 = 0.976 the way PetCastBar does
for its horizontal strip.

Antialiasing: supersampled coverage (same technique as generate_cast_chevron.py).
Glow: separable gaussian blur of the shape coverage, pure stdlib.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_cast_chevron_up.py
"""

import math
import os
import struct

SUPERSAMPLE = 6

BOX_W = 64
BOX_H = 32
# Depth of the arms as a fraction of the box height (the notch is the remainder).
FILL_DEPTH = 8.0 / 13.5      # tape chevron: d 8, t 5.5
CARET_DEPTH = 9.0 / 16.0     # caret: d 9, t 7
# Caret stroke, texels, drawn INSIDE the polygon (about 0.11 of the box height).
STROKE = 3.5

GLOW_PAD_X = 32
GLOW_PAD_Y = 16
GLOW_W = BOX_W + 2 * GLOW_PAD_X
GLOW_H = BOX_H + 2 * GLOW_PAD_Y
GLOW_SIGMA = 4.0
GLOW_GAIN = 1.8
BURST_GAIN = 1.2

STRIP_W = 32
STRIP_H = 16
STRIP_PITCH = STRIP_H
MOCK_PITCH = 12.2            # (BOT - TOP) / N in the mockup, image px
STRIP_ARM = STRIP_PITCH * 8.0 / MOCK_PITCH       # d
STRIP_THICK = STRIP_PITCH * 5.5 / MOCK_PITCH     # t


def up_polygon(w, h, depth, ox=0.0, oy=0.0):
    """Up-pointing chevron in a w x h box: tip top-centre, arm ends `depth * h` below it,
    notch (h - depth * h) below the tip (the arm thickness)."""
    d = depth * h
    return [
        (ox + w / 2.0, oy), (ox + w, oy + d), (ox + w, oy + h),
        (ox + w / 2.0, oy + (h - d)), (ox, oy + h), (ox, oy + d),
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

    def conv_rows(g):
        w = len(g[0])
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
    cols = conv_rows([list(c) for c in zip(*horiz)])
    return [list(r) for r in zip(*cols)]


def _pad(grid, pad_x, pad_y, width, height):
    out = [[0.0] * width for _ in range(height)]
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            out[y + pad_y][x + pad_x] = v
    return out


def build_fill():
    poly = up_polygon(BOX_W, BOX_H, FILL_DEPTH)
    return _coverage_grid(BOX_W, BOX_H, lambda px, py: _inside(poly, px, py))


def build_outline():
    poly = up_polygon(BOX_W, BOX_H, CARET_DEPTH)
    return _coverage_grid(
        BOX_W, BOX_H,
        lambda px, py: _inside(poly, px, py) and _dist_to_edges(poly, px, py) <= STROKE,
    )


def build_glow():
    blurred = _blur(_pad(build_outline(), GLOW_PAD_X, GLOW_PAD_Y, GLOW_W, GLOW_H), GLOW_SIGMA)
    return [[min(1.0, v * GLOW_GAIN) for v in row] for row in blurred]


def build_burst():
    solid = _pad(build_fill(), GLOW_PAD_X, GLOW_PAD_Y, GLOW_W, GLOW_H)
    blurred = _blur(solid, GLOW_SIGMA)
    return [
        [max(s, min(1.0, b * BURST_GAIN)) for s, b in zip(srow, brow)]
        for srow, brow in zip(solid, blurred)
    ]


def build_strip():
    """One chevron per tile. The pattern repeats every STRIP_PITCH rows and each
    chevron is taller than the pitch, so a row is covered by the chevron that
    starts in this tile (oy 0) or by the one that starts a pitch above and wraps
    in (oy -pitch). Rows y and y + pitch are identical by construction, which is
    what makes the tile seamless."""
    polys = [
        [
            (STRIP_W / 2.0, oy), (STRIP_W, oy + STRIP_ARM),
            (STRIP_W, oy + STRIP_ARM + STRIP_THICK), (STRIP_W / 2.0, oy + STRIP_THICK),
            (0.0, oy + STRIP_ARM + STRIP_THICK), (0.0, oy + STRIP_ARM),
        ]
        for oy in (0.0, -float(STRIP_PITCH))
    ]
    return _coverage_grid(
        STRIP_W, STRIP_H, lambda px, py: any(_inside(p, px, py) for p in polys))


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
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    write_tga(os.path.join(here, "cast_chevron_up_fill.tga"), build_fill())
    write_tga(os.path.join(here, "cast_chevron_up_outline.tga"), build_outline())
    write_tga(os.path.join(here, "cast_chevron_up_glow.tga"), build_glow())
    write_tga(os.path.join(here, "cast_chevron_up_burst.tga"), build_burst())
    write_tga(os.path.join(here, "cast_chevron_up_strip.tga"), build_strip())


if __name__ == "__main__":
    main()
