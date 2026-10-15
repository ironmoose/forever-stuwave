#!/usr/bin/env python3
"""Generates the Shaman Gunsight shock trace, shock bolt and Fire Nova textures.

Reference: the design mockup, Concept A "Totem Poles", poleMod():

    shock trace   a zigzag stroke along the ground: points every 8 image px from x = 0 to 160 (the last moved to 162),
                  y alternating -2.5 and +2.5 about the centre line, stroke 1.4 to 2 px
    shock bolt    bolt(x, y, .95): the polygon (3,0) (-6,14) (-1,14) (-4,27) (7,9) (1,9) (6,0), stroke 1.3, a soft glow
    Nova ring     circle(r 14, dashed '3 3', stroke 1.4, glow) and circle(r 18, stroke 1, alpha .35) around the Fire head
    Nova pip      circle(r 4, dashed '2 2', stroke 1.2) beside the NOVA word in the footer

Every canvas is a power of two (the client refuses anything else) and covers a known number of mockup image px, so the Lua
side sizes the frame in image px and the art lands at the mockup's scale:

    shock_trace_line.tga   256 x 32   162 x 20.25 px; x = 0 is the trace start, the zigzag centre line is texel row 16
    shock_trace_glow.tga   256 x 32   178 x 22.25 px; 8 px of margin each side of the trace, same centre line, blur 2.1
    shock_bolt_fill.tga     64 x 64   32 x 32 px, the bolt origin (0, 0) at canvas (16, 2); the polygon interior
    shock_bolt_line.tga     64 x 64   same canvas; the stroke band, 1.3 px, centred on the polygon edge
    shock_bolt_glow.tga     64 x 64   same canvas; the fill and stroke blurred 1.2
    nova_ring.tga           64 x 64   44 x 44 px, centred; the dashed r 14 ring (alpha 1) and the solid r 18 ring (alpha .37,
                                      so the .95 tint the Lua side applies lands on the mockup's .35)
    nova_ring_glow.tga      64 x 64   same canvas; the dashed ring blurred 1.2
    nova_pip.tga            16 x 16   10 x 10 px, centred; six dashes on r 4

The shock trace is a StatusBar texture in Lua: the engine crops it left to right as the cooldown runs, so the line texture
spans exactly the trace and nothing else. White RGB, the shape in alpha; Lua tints them with SetVertexColor.

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

TRACE_W, TRACE_STEP, TRACE_AMP, TRACE_STROKE = 162.0, 8.0, 2.5, 1.7
TRACE_GLOW_BLUR = 2.1
BOLT = [(3, 0), (-6, 14), (-1, 14), (-4, 27), (7, 9), (1, 9), (6, 0)]
BOLT_STROKE, BOLT_BLUR = 1.3, 1.2
BOLT_ORIGIN = (16.0, 2.0)
NOVA_R_IN, NOVA_R_OUT, NOVA_STROKE_IN, NOVA_STROKE_OUT = 14.0, 18.0, 1.4, 1.0
NOVA_DASHES, NOVA_OUT_ALPHA, NOVA_BLUR = 15, 0.35 / 0.95, 1.2
PIP_R, PIP_STROKE, PIP_DASHES = 4.0, 1.2, 6


def trace_points():
    """The mockup's polyline: x every 8 px from 0 while <= 162, y alternating -2.5 / +2.5, the last x moved to 162."""
    pts, x, k = [], 0.0, 0
    while x <= TRACE_W + 1e-9:
        pts.append([x, -TRACE_AMP if k % 2 == 0 else TRACE_AMP])
        x += TRACE_STEP
        k += 1
    pts[-1][0] = TRACE_W
    return [tuple(p) for p in pts]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polyline_dist(px, py, pts, closed=False):
    best = 1e9
    n = len(pts)
    for i in range(n if closed else n - 1):
        a, b = pts[i], pts[(i + 1) % n]
        best = min(best, seg_dist(px, py, a[0], a[1], b[0], b[1]))
    return best


def inside(px, py, poly):
    hit = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > py) != (y1 > py) and px < (x1 - x0) * (py - y0) / (y1 - y0) + x0:
            hit = not hit
    return hit


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

def trace_files():
    pts = trace_points()
    scale = TRACE_W / 256
    line_canvas = Canvas(256, 32, 0.0, -16 * scale, scale)
    line = line_canvas.coverage(lambda x, y: polyline_dist(x, y, pts) <= TRACE_STROKE / 2)
    glow_scale = (TRACE_W + 16) / 256
    glow_canvas = Canvas(256, 32, -8.0, -16 * glow_scale, glow_scale)
    shape = glow_canvas.coverage(lambda x, y: polyline_dist(x, y, pts) <= TRACE_STROKE / 2)
    glow = blur(shape, 256, 32, TRACE_GLOW_BLUR / glow_scale)
    return {"shock_trace_line": (256, 32, line), "shock_trace_glow": (256, 32, glow)}


def bolt_files():
    ox, oy = BOLT_ORIGIN
    poly = [(ox + x, oy + y) for x, y in BOLT]
    canvas = Canvas(64, 64, 0.0, 0.0, 0.5)
    fill = canvas.coverage(lambda x, y: inside(x, y, poly))
    line = canvas.coverage(lambda x, y: polyline_dist(x, y, poly, closed=True) <= BOLT_STROKE / 2)
    both = merge(fill, line)
    glow = blur(both, 64, 64, BOLT_BLUR / 0.5)
    return {"shock_bolt_fill": (64, 64, fill), "shock_bolt_line": (64, 64, line), "shock_bolt_glow": (64, 64, glow)}


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
    files.update(trace_files())
    files.update(bolt_files())
    files.update(nova_files())
    for name, (w, h, alpha) in files.items():
        write_tga(os.path.join(here, name + ".tga"), w, h, alpha)


if __name__ == "__main__":
    main()
