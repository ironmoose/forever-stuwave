#!/usr/bin/env python3
"""Generates led_segments.tga, led_segment_glow.tga and led_glow.tga: the art of the five second rule tab's LED readout.

led_segments.tga is a 64x64 atlas of sixteen 16x16 slots (4 across, 4 down, slot n at column n % 4, row n // 4).
Slots 0..13 hold one of the fourteen segments of a 14 segment cell, in SEGMENT_ORDER; slots 14 and 15 are empty.
A cell is 10 x 12 texels. The segments are drawn on that whole pixel grid in pure white, alpha 255 or 0, no
anti-aliasing, and they are DISJOINT: no texel belongs to two segments (the four diagonals own the four corner
blocks), so a segment tinted with SetVertexColor at a partial alpha never double composites into a bright speck.
The tab draws one texture per segment, 1 texel per physical pixel (never scaled fractionally), lit or unlit
by SetVertexColor alone. The 10 x 12 art sits at the slot's top-left corner; the rest of the slot is clear.

led_segment_glow.tga is the same atlas blurred, the soft copy the page draws under the hard edged segments (a Gaussian of
sigma 1 texel, white, all the shape in the alpha channel, drawn at half strength by the tab). Each slot keeps the layout of
led_segments.tga shifted by a two texel margin: the 10 x 12 art sits at (2, 2) and the glow fills the slot's 14 x 16 top left
rect, so the tab seats the texture two texels up and left of the segment's cell. Slot 14 holds the blurred 2 x 2 block of the
tilde and the dot (art at (2, 2), glow in 6 x 6); slot 15 is empty. A blur keeps the mass, so a cell glows exactly where its
lit segments are and nowhere else.

led_glow.tga is a 64x32 soft box: the Gaussian blur of a solid 35 x 11 core (the page's gauge segments are 7 x 3 design
px and glow 3 px past each side, so the core is 7/13 by 3/9 of the canvas and the falloff sigma is 1.2 px). The tab stretches
it over a gauge segment's rect plus that margin. There is no flat top and no edge: the hump falls to zero at the border.

The segment rows below are [x, y, width] runs one texel tall; mockups/five-second-rule-compact-2026-10-14.html
(SEGS) draws the same table. Pure stdlib, matching the other generators here: 18-byte header, image type 2,
descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top to bottom.

    python generate_led_segments.py
"""

import math
import os
import struct

CELL_W, CELL_H = 10, 12
SLOT = 16
ATLAS = 64

SEGMENT_ORDER = ("a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m")


def _column(x, y0, y1, width=2):
    return [[x, y, width] for y in range(y0, y1 + 1)]


SEGMENTS = {
    "a": [[2, 0, 6], [2, 1, 6]],
    "d": [[2, 10, 6], [2, 11, 6]],
    "f": _column(0, 2, 5),
    "b": _column(8, 2, 5),
    "e": _column(0, 6, 9),
    "c": _column(8, 6, 9),
    "g1": [[2, 5, 3], [2, 6, 3]],
    "g2": [[5, 5, 3], [5, 6, 3]],
    "i": _column(4, 2, 4),
    "l": _column(4, 7, 9),
    "h": [[0, 0, 2], [0, 1, 2], [2, 2, 1], [2, 3, 2], [3, 4, 1]],
    "j": [[8, 0, 2], [8, 1, 2], [7, 2, 1], [6, 3, 2], [6, 4, 1]],
    "k": [[3, 7, 1], [2, 8, 2], [2, 9, 1], [0, 10, 2], [0, 11, 2]],
    "m": [[6, 7, 1], [6, 8, 2], [7, 9, 1], [8, 10, 2], [8, 11, 2]],
}

GLOW_W, GLOW_H = 64, 32
GLOW_INNER_W, GLOW_INNER_H = 35, 11      # the solid core, centred; the blur spills outside it
GLOW_SIGMA_X = (GLOW_W - GLOW_INNER_W) / 2 / 3 * 1.2   # 3 design px of margin a side is 1.2 sigma-px: 14.5 texels = 3 px
GLOW_SIGMA_Y = (GLOW_H - GLOW_INNER_H) / 2 / 3 * 1.2
SEGMENT_GLOW_SIGMA = 1.0                 # texels
SEGMENT_GLOW_MARGIN = 2                  # texels of glow past the cell on the left and top (and the right and bottom)
BLOCK_SLOT = 14                          # the blurred 2 x 2 block of the tilde and the dot


def build_atlas():
    """The atlas as a list of rows of (r, g, b, a) tuples."""
    rows = [[(255, 255, 255, 0)] * ATLAS for _ in range(ATLAS)]
    for n, name in enumerate(SEGMENT_ORDER):
        ox, oy = (n % 4) * SLOT, (n // 4) * SLOT
        for x, y, width in SEGMENTS[name]:
            for q in range(width):
                assert 0 <= x + q < CELL_W and 0 <= y < CELL_H, (name, x, y, width)
                assert rows[oy + y][ox + x + q][3] == 0, f"segment {name} overlaps another at {x + q},{y}"
                rows[oy + y][ox + x + q] = (255, 255, 255, 255)
    return rows


def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _box_blur_1d(x, lo, hi, sigma):
    """The blur of the interval [lo, hi) sampled over the texel [x, x + 1): its mean."""
    # the integral of the blurred indicator over the texel, by the antiderivative of Phi
    def big_phi(z):
        return z * _phi(z) + math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi)

    def prim(t):
        return sigma * big_phi((t - lo) / sigma) - sigma * big_phi((t - hi) / sigma)

    return (prim(x + 1.0) - prim(x)) / 1.0


def _blur_rows(mask, sigma, size_w, size_h):
    """The Gaussian blur of a 0/1 texel mask (a list of rows) as float rows, edge texels treated as clear."""
    radius = int(math.ceil(sigma * 3.5))
    kernel = [_phi((d + 0.5) / sigma) - _phi((d - 0.5) / sigma) for d in range(-radius, radius + 1)]
    horizontal = [[sum(kernel[k] * (mask[y][x + k - radius] if 0 <= x + k - radius < size_w else 0.0)
                       for k in range(len(kernel))) for x in range(size_w)] for y in range(size_h)]
    return [[sum(kernel[k] * (horizontal[y + k - radius][x] if 0 <= y + k - radius < size_h else 0.0)
                 for k in range(len(kernel))) for x in range(size_w)] for y in range(size_h)]


def build_segment_glow():
    """The blurred atlas as rows of (r, g, b, a): each slot's art shifted by the margin, then blurred inside the slot."""
    rows = [[(255, 255, 255, 0)] * ATLAS for _ in range(ATLAS)]
    shapes = [SEGMENTS[name] for name in SEGMENT_ORDER] + [[[0, 0, 2], [0, 1, 2]]]
    for n, runs in enumerate(shapes):
        ox, oy = (n % 4) * SLOT, (n // 4) * SLOT
        mask = [[0.0] * SLOT for _ in range(SLOT)]
        for x, y, width in runs:
            for q in range(width):
                mask[y + SEGMENT_GLOW_MARGIN][x + q + SEGMENT_GLOW_MARGIN] = 1.0
        blurred = _blur_rows(mask, SEGMENT_GLOW_SIGMA, SLOT, SLOT)
        for y in range(SLOT):
            for x in range(SLOT):
                # the glow rect is the cell plus the margin on every side: 14 x 16 for a segment, 6 x 6 for the block
                in_rect = x < (6 if n == BLOCK_SLOT else CELL_W + 2 * SEGMENT_GLOW_MARGIN) and \
                    y < (6 if n == BLOCK_SLOT else CELL_H + 2 * SEGMENT_GLOW_MARGIN)
                alpha = int(round(blurred[y][x] * 255)) if in_rect else 0
                rows[oy + y][ox + x] = (255, 255, 255, alpha)
    return rows


def build_glow():
    """The soft box: the blur of a solid core, tapered to exactly zero at the border."""
    left = (GLOW_W - GLOW_INNER_W) / 2
    top = (GLOW_H - GLOW_INNER_H) / 2
    ax = [_box_blur_1d(x, left, left + GLOW_INNER_W, GLOW_SIGMA_X) for x in range(GLOW_W)]
    ay = [_box_blur_1d(y, top, top + GLOW_INNER_H, GLOW_SIGMA_Y) for y in range(GLOW_H)]
    edge_x, edge_y = ax[0], ay[0]
    rows = []
    for y in range(GLOW_H):
        row = []
        for x in range(GLOW_W):
            wx = max(0.0, (ax[x] - edge_x) / (1.0 - edge_x))
            wy = max(0.0, (ay[y] - edge_y) / (1.0 - edge_y))
            row.append((255, 255, 255, int(round(wx * wy * 255))))
        rows.append(row)
    return rows


def write_tga(path, rows):
    height, width = len(rows), len(rows[0])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    payload = bytearray()
    for row in rows:
        for r, g, b, a in row:
            payload += bytes((b, g, r, a))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(payload)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def main():
    out = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write_tga(os.path.join(out, "led_segments.tga"), build_atlas())
    write_tga(os.path.join(out, "led_segment_glow.tga"), build_segment_glow())
    write_tga(os.path.join(out, "led_glow.tga"), build_glow())


if __name__ == "__main__":
    main()
