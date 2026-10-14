#!/usr/bin/env python3
"""Generates the arc textures of the totem preset dial and the GNARLY cell.

Reference: mockups/totem-presets-2026-10-14.html, concept C, ringBtn(). A cell is a 38 design unit square button
wearing a ring of radius 11.5 centred 2 units above the button centre (cx 19, cy 17 in the box), split into one arc per
totem of the preset: n arcs of 360 / n degrees each, 14 degrees of gap between neighbours (no gap for a single arc),
the first arc starting at the top and running clockwise.

Every texture covers the WHOLE button box (38 x 38 design units, 64 x 64 texels) so a stack of them is anchored to the
button with SetAllPoints. White RGB, the shape in alpha; the addon tints them.

Per arc (n = 1..4 arcs, i = 1..n) five kinds:
    t  the quiet stroke, 3.6 units wide
    g  the same stroke with the mockup's glow (blur under the crisp stroke) baked in: the arcs that are done
    k  the thick stroke, 5 units wide: the arc that is next
    c  the thin core, 1.2 units wide, one unit short at both ends: the white line inside the next arc
    d  the locked arc: 3.6 units wide, dashed 2 on, 2.6 off along the arc
and one `empty`: the dashed full circle (3 units wide, 2 on, 3.2 off) of a preset with no totem.

Files: totem_dial_n{n}_{i}_{kind}.tga and totem_dial_empty.tga.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_totem_dial.py
"""

import math
import os
import struct

BOX = 38.0                # design units the canvas covers (the button)
SIZE = 64                 # texels per side
CX, CY = 19.0, 17.0       # ring centre in the box, design units (y down)
RADIUS = 11.5
GAP_DEG = 14.0
SUPERSAMPLE = 4
BLUR_SIGMA = 1.2          # design units, the mockup's feGaussianBlur stdDeviation for a done arc
STROKES = {"t": 3.6, "g": 3.6, "k": 5.0, "c": 1.2, "d": 3.6}
CORE_TRIM_DEG = 1.0 / RADIUS * 180.0 / math.pi   # the core runs one unit short of each end
DASH_ON, DASH_OFF = 2.0, 2.6
EMPTY_STROKE, EMPTY_ON, EMPTY_OFF = 3.0, 2.0, 3.2


def arc_span(n, i):
    """(start, end) degrees clockwise from the top of arc i (0 based) of n."""
    seg = 360.0 / n
    gap = 0.0 if n == 1 else GAP_DEG
    return i * seg + gap / 2, (i + 1) * seg - gap / 2


def coverage(span, width, dash=None, trim=0.0):
    """Supersampled coverage of a stroke of `width` around the ring over `span` degrees."""
    a0, a1 = span[0] + trim, span[1] - trim
    lo, hi = RADIUS - width / 2, RADIUS + width / 2
    grid = [[0.0] * SIZE for _ in range(SIZE)]
    unit = BOX / SIZE
    for ty in range(SIZE):
        for tx in range(SIZE):
            hits = 0
            for sy in range(SUPERSAMPLE):
                dy = (ty + (sy + 0.5) / SUPERSAMPLE) * unit - CY
                for sx in range(SUPERSAMPLE):
                    dx = (tx + (sx + 0.5) / SUPERSAMPLE) * unit - CX
                    d = math.hypot(dx, dy)
                    if d < lo or d > hi:
                        continue
                    theta = math.degrees(math.atan2(dx, -dy)) % 360.0
                    if theta < a0 or theta > a1:
                        continue
                    if dash is not None:
                        run = (theta - span[0]) * math.pi / 180.0 * RADIUS
                        if run % (dash[0] + dash[1]) > dash[0]:
                            continue
                    hits += 1
            grid[ty][tx] = hits / (SUPERSAMPLE * SUPERSAMPLE)
    return grid


def _kernel(sigma):
    radius = int(math.ceil(sigma * 3))
    k = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(k)
    return radius, [v / total for v in k]


def blur(grid, sigma):
    """Separable gaussian blur (scatter form: the cost follows the few non-zero texels)."""
    r, k = _kernel(sigma)
    h, w = len(grid), len(grid[0])
    mid = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            v = grid[y][x]
            if v:
                for i, kv in enumerate(k):
                    xx = x + i - r
                    if 0 <= xx < w:
                        mid[y][xx] += v * kv
    out = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            v = mid[y][x]
            if v:
                for i, kv in enumerate(k):
                    yy = y + i - r
                    if 0 <= yy < h:
                        out[yy][x] += v * kv
    return out


def build(kind, n, i):
    span = arc_span(n, i)
    if kind == "t":
        return coverage(span, STROKES["t"])
    if kind == "k":
        return coverage(span, STROKES["k"])
    if kind == "c":
        return coverage(span, STROKES["c"], trim=CORE_TRIM_DEG)
    if kind == "d":
        return coverage(span, STROKES["d"], dash=(DASH_ON, DASH_OFF))
    crisp = coverage(span, STROKES["g"])
    soft = blur(crisp, BLUR_SIGMA * SIZE / BOX)
    # feMerge: the blur underneath, the crisp stroke over it
    return [[min(1.0, c + b * (1.0 - c)) for c, b in zip(crow, brow)] for crow, brow in zip(crisp, soft)]


def build_empty():
    return coverage((0.0, 360.0), EMPTY_STROKE, dash=(EMPTY_ON, EMPTY_OFF))


def write_tga(path, grid):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    rows = bytearray()
    for row in grid:
        for v in row:
            rows += bytes((255, 255, 255, int(round(v * 255))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    for n in range(1, 5):
        for i in range(n):
            for kind in ("t", "g", "k", "c", "d"):
                write_tga(os.path.join(here, f"totem_dial_n{n}_{i + 1}_{kind}.tga"), build(kind, n, i))
    write_tga(os.path.join(here, "totem_dial_empty.tga"), build_empty())


if __name__ == "__main__":
    main()
