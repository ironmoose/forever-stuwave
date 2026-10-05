#!/usr/bin/env python3
"""Generates the sixteen ring arc textures of the pet action bar's autocast ring.

Reference: mockups/castbar-v2-chevrons-locked-2026-10-01.html, buildRing() in the "Pet slot rings"
section. Each pet slot is a 30 design unit button wearing a CIRCLE of radius 11.5 (stroke 1.5)
centred on it, split into RING_N = 16 equal arcs (arc i runs from -90 degrees + i/16 of a turn,
clockwise, to the next arc plus 0.02 radian of hairline overlap). The ring ignites, flickers and goes
out arc by arc, so each arc is its own texture and PetActionBar.lua tints and fades them one at a
time. All sixteen are the same size and are meant to be stacked on ONE anchor (centred on the
button), so a stack of them is the whole ring.

(media/hud_key_ring_NN.tga is the HUD key's cut-corner outline in a 42 x 34 box: it does not fit a
square 30 unit button, hence this separate set.)

Files: pet_slot_ring_00.tga .. pet_slot_ring_15.tga, 128x128, white RGB, shape in alpha.

Glow: the mockup draws the arcs through a filter that merges a gaussian blur (stdDeviation 1.1)
under the crisp stroke. That is baked here: alpha is the crisp stroke coverage over its own blur.
The blur has to fit somewhere, so the canvas is the button box plus PAD = 4 design units on every
side: 38 x 38 design units, centred on the button. Size the texture to 38 / 30 of the button and
anchor CENTER to CENTER, and the arcs land on the button's ring.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha
bits), BGRA top-to-bottom.

    python3 generate_pet_slot_ring.py
"""

import math
import os
import struct

RING_N = 16
BUTTON = 30.0
RADIUS = 11.5
STROKE = 1.5
OVERLAP = 0.02            # radians
PAD = 4.0
BLUR_SIGMA = 1.1          # design units, the mockup's feGaussianBlur stdDeviation
SIZE = 128                # texels per side (a power of two)
SPAN = BUTTON + 2 * PAD   # design units the canvas covers
SUPERSAMPLE = 4
TAU = 2 * math.pi


def coverage(index):
    """Supersampled stroke coverage per texel of arc `index`."""
    a0 = -math.pi / 2 + (index / RING_N) * TAU
    width = TAU / RING_N + OVERLAP
    mid = SPAN / 2
    grid = [[0.0] * SIZE for _ in range(SIZE)]
    lo, hi = RADIUS - STROKE / 2, RADIUS + STROKE / 2
    reach = int(math.ceil((hi + 1) * SIZE / SPAN))
    centre = SIZE // 2
    for ty in range(max(0, centre - reach), min(SIZE, centre + reach + 1)):
        for tx in range(max(0, centre - reach), min(SIZE, centre + reach + 1)):
            hits = 0
            for sy in range(SUPERSAMPLE):
                dy = (ty + (sy + 0.5) / SUPERSAMPLE) * SPAN / SIZE - mid
                for sx in range(SUPERSAMPLE):
                    dx = (tx + (sx + 0.5) / SUPERSAMPLE) * SPAN / SIZE - mid
                    d = math.hypot(dx, dy)
                    if d < lo or d > hi:
                        continue
                    rel = (math.atan2(dy, dx) - a0) % TAU
                    if rel <= width:
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


def build_arc(index):
    crisp = coverage(index)
    soft = blur(crisp, BLUR_SIGMA * SIZE / SPAN)
    # feMerge: the blur underneath, the crisp stroke over it.
    return [
        [min(1.0, c + b * (1.0 - c)) for c, b in zip(crow, brow)]
        for crow, brow in zip(crisp, soft)
    ]


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
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    for i in range(RING_N):
        write_tga(os.path.join(here, f"pet_slot_ring_{i:02d}.tga"), build_arc(i))


if __name__ == "__main__":
    main()
