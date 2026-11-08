#!/usr/bin/env python3
"""Generates the Shaman Gunsight Fire Nova ring and footer pip textures.

The shock tracker (the rune disc and its bolt) is baked by generate_shaman_disc.py; this file keeps the Fire Nova pieces, which
are unchanged from the first Shaman build.

Reference: the design mockup, Concept A "Totem Poles", poleMod():

    Nova ring     circle(r 14, dashed '3 3', stroke 1.4, glow) and circle(r 18, stroke 1, alpha .35) around the Fire head
    Nova pip      circle(r 4, dashed '2 2', stroke 1.2) beside the NOVA word in the footer

Every canvas is a power of two (the client refuses anything else) and covers a known number of mockup image px, so the Lua
side sizes the frame in image px and the art lands at the mockup's scale:

    nova_ring.tga           64 x 64   44 x 44 px, centred; the dashed r 14 ring (alpha 1) and the solid r 18 ring (alpha .37,
                                      so the .95 tint the Lua side applies lands on the mockup's .35)
    nova_ring_glow.tga      64 x 64   same canvas; the dashed ring blurred 1.2
    nova_pip.tga            16 x 16   10 x 10 px, centred; six dashes on r 4

White RGB, the shape in alpha; Lua tints them with SetVertexColor.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_shaman_shocks.py
"""

import math
import os
import struct

SUPERSAMPLE = 4

# ---------------------------------------------------------------------------
# The mockup's shapes (image px)
# ---------------------------------------------------------------------------

NOVA_R_IN, NOVA_R_OUT, NOVA_STROKE_IN, NOVA_STROKE_OUT = 14.0, 18.0, 1.4, 1.0
NOVA_DASHES, NOVA_OUT_ALPHA, NOVA_BLUR = 15, 0.35 / 0.95, 1.2
PIP_R, PIP_STROKE, PIP_DASHES = 4.0, 1.2, 6


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

class Canvas:
    """w x h texels covering (w * scale) x (h * scale) image px whose top left is (x0, y0) in image px."""

    def __init__(self, w, h, x0, y0, scale):
        self.w, self.h, self.x0, self.y0, self.scale = w, h, x0, y0, scale

    def coverage(self, shape):
        """Supersampled coverage 0..1 of shape(px, py) -> bool, row-major."""
        ss = SUPERSAMPLE
        out = []
        for ty in range(self.h):
            for tx in range(self.w):
                hits = 0
                for sy in range(ss):
                    py = self.y0 + (ty + (sy + 0.5) / ss) * self.scale
                    for sx in range(ss):
                        px = self.x0 + (tx + (sx + 0.5) / ss) * self.scale
                        if shape(px, py):
                            hits += 1
                out.append(hits / (ss * ss))
        return out


def blur(alpha, w, h, sigma_texels):
    """Separable gaussian blur of a row-major alpha list."""
    radius = max(1, int(math.ceil(sigma_texels * 3)))
    kernel = [math.exp(-(i * i) / (2 * sigma_texels * sigma_texels)) for i in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [k / total for k in kernel]
    tmp = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            acc = 0.0
            for i, k in enumerate(kernel):
                xx = x + i - radius
                if 0 <= xx < w:
                    acc += alpha[y * w + xx] * k
            tmp[y * w + x] = acc
    out = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            acc = 0.0
            for i, k in enumerate(kernel):
                yy = y + i - radius
                if 0 <= yy < h:
                    acc += tmp[yy * w + x] * k
            out[y * w + x] = acc
    return out


def merge(*layers):
    """Alpha of several layers drawn over each other (the same colour, so 'over' on alpha)."""
    out = [0.0] * len(layers[0])
    for layer in layers:
        out = [a + b * (1 - a) for a, b in zip(out, layer)]
    return out


def write_tga(path, w, h, alpha):
    rows = bytearray()
    for a in alpha:
        rows += bytes((255, 255, 255, int(round(max(0.0, min(1.0, a)) * 255))))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({w}x{h}, {os.path.getsize(path)} bytes)")


def dashed_ring(px, py, cx, cy, r, stroke, dashes):
    """True on a ring of `dashes` equal dashes with equal gaps, stroke wide, centred on (cx, cy)."""
    dx, dy = px - cx, py - cy
    if abs(math.hypot(dx, dy) - r) > stroke / 2:
        return False
    turn = (math.atan2(dy, dx) % (2 * math.pi)) / (2 * math.pi)
    return (turn * dashes) % 1.0 < 0.5


def solid_ring(px, py, cx, cy, r, stroke):
    return abs(math.hypot(px - cx, py - cy) - r) <= stroke / 2


# ---------------------------------------------------------------------------
# The files
# ---------------------------------------------------------------------------

def nova_files():
    scale = 44.0 / 64
    canvas = Canvas(64, 64, -22.0, -22.0, scale)
    inner = canvas.coverage(lambda x, y: dashed_ring(x, y, 0, 0, NOVA_R_IN, NOVA_STROKE_IN, NOVA_DASHES))
    outer = canvas.coverage(lambda x, y: solid_ring(x, y, 0, 0, NOVA_R_OUT, NOVA_STROKE_OUT))
    ring = merge(inner, [a * NOVA_OUT_ALPHA for a in outer])
    glow = blur(inner, 64, 64, NOVA_BLUR / scale)
    pip_canvas = Canvas(16, 16, -5.0, -5.0, 10.0 / 16)
    pip = pip_canvas.coverage(lambda x, y: dashed_ring(x, y, 0, 0, PIP_R, PIP_STROKE, PIP_DASHES))
    return {"nova_ring": (64, 64, ring), "nova_ring_glow": (64, 64, glow), "nova_pip": (16, 16, pip)}


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    files = {}
    files.update(nova_files())
    for name, (w, h, alpha) in files.items():
        write_tga(os.path.join(here, name + ".tga"), w, h, alpha)


if __name__ == "__main__":
    main()
