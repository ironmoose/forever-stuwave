#!/usr/bin/env python3
"""Generates loc_tick.tga: one tick of the loss of control alert's ring.

Reference: the loss of control mockup, concept B "Gunsight jam" (2026-11-05): sixteen ticks on a ring around the
spell icon, each a bar 3 design units wide and 7 long, drawn through a soft glow (a gaussian blur, stdDeviation
1, merged under the crisp bar). The Lua side places sixteen copies of this one texture round the ring and turns
each with SetRotation, so the texture is the bar standing upright with its glow baked around it.

Canvas: the bar plus PAD = 3 design units of glow on every side, 9 x 13 units, at 4 texels a unit and rounded up
to a power of two: 64 x 64 texels with the shape centred (the unused rows are clear). HudText.lua draws it
9 x 13 units in a 16 x 16 unit square region so the texel aspect stays square. White RGB, shape in alpha
(crisp core over its own blur), so SetVertexColor tints it.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_loc_tick.py
"""

import math
import os
import struct

SIZE = 64
UNITS = 16.0                # the square region the texture is drawn into, design units
BAR_W, BAR_H = 3.0, 7.0
SIGMA = 1.0
SUPERSAMPLE = 8


def _core(x, y):
    """Coverage of the crisp bar in texel (x, y)."""
    scale = UNITS / SIZE
    hits = 0
    for sy in range(SUPERSAMPLE):
        py = (y + (sy + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
        for sx in range(SUPERSAMPLE):
            px = (x + (sx + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
            if abs(px) <= BAR_W / 2 and abs(py) <= BAR_H / 2:
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def _blur(img):
    sigma = SIGMA * SIZE / UNITS
    radius = int(math.ceil(sigma * 3))
    kernel = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]
    tmp = [[0.0] * SIZE for _ in range(SIZE)]
    for y in range(SIZE):
        for x in range(SIZE):
            tmp[y][x] = sum(kernel[i + radius] * img[y][min(SIZE - 1, max(0, x + i))] for i in range(-radius, radius + 1))
    out = [[0.0] * SIZE for _ in range(SIZE)]
    for y in range(SIZE):
        for x in range(SIZE):
            out[y][x] = sum(kernel[i + radius] * tmp[min(SIZE - 1, max(0, y + i))][x] for i in range(-radius, radius + 1))
    return out


def main():
    core = [[_core(x, y) for x in range(SIZE)] for y in range(SIZE)]
    glow = _blur(core)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            c = core[y][x]
            a = c + (1 - c) * min(1.0, glow[y][x] * 1.6) * 0.8
            rows += bytes((255, 255, 255, int(round(max(0.0, min(1.0, a)) * 255))))
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "loc_tick.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
