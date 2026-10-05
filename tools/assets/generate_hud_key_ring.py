#!/usr/bin/env python3
"""Generates the sixteen ring arc textures of the Gunsight HUD toggle keys.

Reference: mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html,
buildRing(), perimAt() and perimPath(). Each toggle key wears a ring that follows
its outline, split into RING_N = 16 equal stretches of the perimeter; the ring
ignites, flickers and goes out arc by arc, so each arc is its own texture and the
Lua side tints and fades them one at a time. All sixteen are the same size and are
meant to be stacked on ONE anchor, so a stack of them is the whole ring.

Files: hud_key_ring_00.tga .. hud_key_ring_15.tga, 128x64, white RGB, shape in alpha.

Geometry (from buildRing; design units):

    key            34 x 26, TOP-LEFT and BOTTOM-RIGHT cut by C = 6
    ring polygon   the key outline inset by INS = 1.8, its cut legs shortened to
                   cp = C - 0.586 * INS so the diagonal stays a true parallel of the
                   key's own cut. Seven vertices from the top middle, clockwise:
                   (17, 1.8) (32.2, 1.8) (32.2, 19.25) (27.25, 24.2) (1.8, 24.2)
                   (1.8, 6.75) (6.75, 1.8)
    arc i          perimeter fraction i/16 to (i + 1)/16 + 0.004 (the 0.004 is a
                   hairline overlap so neighbours leave no gap), keeping the corners
                   it passes, stroked 1.4 wide with MITER joins and BUTT ends
    arc 0          starts at the top middle and runs clockwise (to the right)

Glow: the mockup draws the arcs through a filter that merges a gaussian blur
(stdDeviation 1.1) under the crisp stroke. That is baked here: alpha is the crisp
stroke coverage over its own blur, so the arc has a hard core and a soft edge.
The blur has to fit somewhere, so the canvas is the key box plus PAD = 4 design
units on every side (3 sigma is 3.3): the texture is (34 + 8) x (26 + 8) = 42 x 34
design units, centred on the key. Size it to that and anchor CENTER to CENTER, and
the arcs land exactly on the key's ring.

Pixels are not square in design units (128 texels over 42 units across, 64 over 34
down), so the shape is rasterised IN DESIGN UNITS (every texel is mapped to its
design position first) and the blur sigma is converted per axis. Stretched to the
42 x 34 box the stroke is therefore an even 1.4 on every edge and the diagonal
cuts are true 45 degree lines.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_hud_key_ring.py
"""

import math
import os
import struct

RING_N = 16
KEY_W, KEY_H = 34.0, 26.0
CUT = 6.0
INS = 1.8
STROKE = 1.4
OVERLAP = 0.004
PAD = 4.0
BLUR_SIGMA = 1.1          # design units, the mockup's feGaussianBlur stdDeviation

WIDTH, HEIGHT = 128, 64
SPAN_W = KEY_W + 2 * PAD  # design units the canvas covers
SPAN_H = KEY_H + 2 * PAD
SUPERSAMPLE = 4


def ring_points():
    """The seven vertices of the ring polygon, top middle first, clockwise."""
    cp = CUT - 0.586 * INS
    return [
        (KEY_W / 2, INS), (KEY_W - INS, INS), (KEY_W - INS, KEY_H - cp - INS),
        (KEY_W - cp - INS, KEY_H - INS), (INS, KEY_H - INS), (INS, cp + INS),
        (cp + INS, INS),
    ]


def perimeter(points):
    """Cumulative path length at every vertex of the closed polygon (len n + 1)."""
    cum = [0.0]
    n = len(points)
    for i in range(1, n + 1):
        a, b = points[i - 1], points[i % n]
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return cum


def point_at(points, cum, d):
    n = len(points)
    i = 1
    while i < n and cum[i] < d:
        i += 1
    a, b = points[i - 1], points[i % n]
    f = (d - cum[i - 1]) / ((cum[i] - cum[i - 1]) or 1.0)
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


def arc_path(points, cum, f0, f1):
    """perimPath: the stretch f0..f1 of the perimeter as an open polyline, keeping
    the vertices it passes."""
    total = cum[-1]
    d0, d1 = f0 * total, min(total, f1 * total)
    path = [point_at(points, cum, d0)]
    for i in range(1, len(points)):
        if d0 + 1e-6 < cum[i] < d1 - 1e-6:
            path.append(points[i])
    path.append(point_at(points, cum, d1))
    return path


def stroke_polygon(path, half):
    """Outline of a polyline stroked `half` each side with miter joins and butt ends."""
    normals = []
    for a, b in zip(path, path[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        normals.append((-dy / length, dx / length))
    left, right = [], []
    for i, p in enumerate(path):
        if i == 0:
            mx, my = normals[0]
        elif i == len(path) - 1:
            mx, my = normals[-1]
        else:
            n1, n2 = normals[i - 1], normals[i]
            k = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
            mx, my = (n1[0] + n2[0]) / k, (n1[1] + n2[1]) / k
        left.append((p[0] + mx * half, p[1] + my * half))
        right.append((p[0] - mx * half, p[1] - my * half))
    return left + right[::-1]


def inside(poly, px, py):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def coverage(poly):
    """Supersampled stroke coverage per texel, sampled at design coordinates."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    # texel range touched by the polygon (design x = tx * SPAN_W / WIDTH - PAD)
    tx0 = max(0, int(math.floor((min(xs) + PAD) * WIDTH / SPAN_W)) - 1)
    tx1 = min(WIDTH - 1, int(math.ceil((max(xs) + PAD) * WIDTH / SPAN_W)) + 1)
    ty0 = max(0, int(math.floor((min(ys) + PAD) * HEIGHT / SPAN_H)) - 1)
    ty1 = min(HEIGHT - 1, int(math.ceil((max(ys) + PAD) * HEIGHT / SPAN_H)) + 1)
    grid = [[0.0] * WIDTH for _ in range(HEIGHT)]
    n = SUPERSAMPLE * SUPERSAMPLE
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            hits = 0
            for sy in range(SUPERSAMPLE):
                dy = (ty + (sy + 0.5) / SUPERSAMPLE) * SPAN_H / HEIGHT - PAD
                for sx in range(SUPERSAMPLE):
                    dx = (tx + (sx + 0.5) / SUPERSAMPLE) * SPAN_W / WIDTH - PAD
                    if inside(poly, dx, dy):
                        hits += 1
            grid[ty][tx] = hits / n
    return grid


def _kernel(sigma):
    radius = int(math.ceil(sigma * 3))
    k = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(k)
    return radius, [v / total for v in k]


def blur(grid, sigma_x, sigma_y):
    """Separable gaussian blur with a different sigma per axis (texels). Scatter
    form, so the cost follows the (few) non-zero texels of a thin arc."""
    rx, kx = _kernel(sigma_x)
    ry, ky = _kernel(sigma_y)
    h, w = len(grid), len(grid[0])
    mid = [[0.0] * w for _ in range(h)]
    for y in range(h):
        row = grid[y]
        for x in range(w):
            v = row[x]
            if v:
                for i, k in enumerate(kx):
                    xx = x + i - rx
                    if 0 <= xx < w:
                        mid[y][xx] += v * k
    out = [[0.0] * w for _ in range(h)]
    for y in range(h):
        row = mid[y]
        for x in range(w):
            v = row[x]
            if v:
                for i, k in enumerate(ky):
                    yy = y + i - ry
                    if 0 <= yy < h:
                        out[yy][x] += v * k
    return out


def build_arc(points, cum, index):
    path = arc_path(points, cum, index / RING_N, (index + 1) / RING_N + OVERLAP)
    crisp = coverage(stroke_polygon(path, STROKE / 2.0))
    soft = blur(crisp, BLUR_SIGMA * WIDTH / SPAN_W, BLUR_SIGMA * HEIGHT / SPAN_H)
    # feMerge: the blur underneath, the crisp stroke over it.
    return [
        [min(1.0, c + b * (1.0 - c)) for c, b in zip(crow, brow)]
        for crow, brow in zip(crisp, soft)
    ]


def write_tga(path, grid):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, WIDTH, HEIGHT, 32, 0x28)
    rows = bytearray()
    for row in grid:
        for v in row:
            rows += bytes((255, 255, 255, int(round(v * 255))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({WIDTH}x{HEIGHT}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    points = ring_points()
    cum = perimeter(points)
    for i in range(RING_N):
        write_tga(os.path.join(here, f"hud_key_ring_{i:02d}.tga"), build_arc(points, cum, i))


if __name__ == "__main__":
    main()
