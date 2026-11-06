#!/usr/bin/env python3
"""Generates queue_eye_lid.tga and queue_eye_pupil.tga: Forever STUwave's own group finder eye.

Blizzard's queue eye is a flipbook with its round bezel baked into every frame, so it cannot sit on a STUwave key
plate without that bezel (player, 2026-11-05: "we need our own icon or remove the border"). This draws the eye
from two shapes, each white with its shape in alpha (crisp core over its own gaussian glow) so SetVertexColor
tints it: the LID, an almond (the lens where two circles overlap) as an outline plus the iris ring, and the PUPIL,
a filled dot. MicroBars.lua tints the lid cyan and the pupil pink.

Canvas: 64 x 64 texels for a 16 x 16 design unit square (4 texels a unit). Pure stdlib. Output: 18-byte header,
image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_queue_eye.py
"""

import math
import os
import struct

SIZE = 64
UNITS = 16.0
SUPERSAMPLE = 6
SIGMA = 0.7          # glow, design units
LID_W, LID_H = 13.0, 7.4   # the almond's width and height
STROKE = 1.1
IRIS_R = 2.6
PUPIL_R = 1.25


def _lens_radius():
    # Two circles of radius r whose centres sit d apart vertically meet LID_W apart and overlap LID_H tall.
    half_w, half_h = LID_W / 2, LID_H / 2
    r = (half_w ** 2 + half_h ** 2) / (2 * half_h)
    return r, r - half_h


R, OFF = _lens_radius()


def _in_lens(px, py, grow=0.0):
    return (math.hypot(px, py - OFF) <= R + grow) and (math.hypot(px, py + OFF) <= R + grow)


def _lid(px, py):
    outline = _in_lens(px, py, STROKE / 2) and not _in_lens(px, py, -STROKE / 2)
    d = math.hypot(px, py)
    ring = abs(d - IRIS_R) <= STROKE / 2
    return outline or ring


def _pupil(px, py):
    return math.hypot(px, py) <= PUPIL_R


def _coverage(shape):
    scale = UNITS / SIZE
    img = [[0.0] * SIZE for _ in range(SIZE)]
    for y in range(SIZE):
        for x in range(SIZE):
            hits = 0
            for sy in range(SUPERSAMPLE):
                py = (y + (sy + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
                for sx in range(SUPERSAMPLE):
                    px = (x + (sx + 0.5) / SUPERSAMPLE) * scale - UNITS / 2
                    if shape(px, py):
                        hits += 1
            img[y][x] = hits / (SUPERSAMPLE * SUPERSAMPLE)
    return img


def _blur(img):
    sigma = SIGMA * SIZE / UNITS
    radius = int(math.ceil(sigma * 3))
    kernel = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]
    tmp = [[sum(kernel[i + radius] * img[y][min(SIZE - 1, max(0, x + i))] for i in range(-radius, radius + 1))
            for x in range(SIZE)] for y in range(SIZE)]
    return [[sum(kernel[i + radius] * tmp[min(SIZE - 1, max(0, y + i))][x] for i in range(-radius, radius + 1))
             for x in range(SIZE)] for y in range(SIZE)]


def _write(name, shape):
    core = _coverage(shape)
    glow = _blur(core)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            c = core[y][x]
            a = c + (1 - c) * min(1.0, glow[y][x] * 1.8) * 0.55
            rows += bytes((255, 255, 255, int(round(max(0.0, min(1.0, a)) * 255))))
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, name)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def main():
    _write("queue_eye_lid.tga", _lid)
    _write("queue_eye_pupil.tga", _pupil)


if __name__ == "__main__":
    main()
