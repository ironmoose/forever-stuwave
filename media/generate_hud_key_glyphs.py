#!/usr/bin/env python3
"""Generates the eight 32x32 glyphs for the Gunsight HUD toggle keys.

Reference: mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html, the
GLY table (one SVG fragment per glyph, 16 x 16 viewBox) and DECK_DEFS (which key
uses which glyph). The glyph SVG is rasterised as written: the path strings below
are copied from GLY and parsed here, so the two cannot drift by hand-tracing.

Files written (all next to this script), and the key that wears each one:

    glyph_hud_chev.tga      your    Your Cast       two stacked up-chevrons
    glyph_hud_play.tga      next    Next Cast       play triangle with a bar
    glyph_hud_diamond.tga   shard   Soul Shards     diamond with a mid line
    glyph_hud_shield.tga    buff    Buff Reminder   shield with a check
    glyph_hud_cross.tga     target  Target Cast     reticle: ring, four ticks, dot
    glyph_hud_clock.tga     dots    DoT Timers      clock face
    glyph_hud_bolt.tga      procs   Procs           lightning bolt
    glyph_hud_group.tga     party   Party Frame     three heads and shoulders

Style, from the mockup's CSS: `.kgl` is stroke-width 1.6 in the 16 unit box, round
caps and joins, fill none; the elements marked `fill="currentColor" stroke="none"`
are solid dots. 16 units map onto the 32 texel canvas (scale 2, stroke 3.2 texels),
and the key draws the glyph at scale .8 of its 16 box (12.8 design units), so a
texel is about 0.4 design units. The two sub-paths drawn with `stroke-opacity`
(.55 on the chev's second chevron, .5 on the diamond's mid line) are baked at that
alpha; where a faint stroke touches a full one the full one wins.

There is deliberately no baked glow: the key draws the glyph twice (once a little
larger and dim, ADD blend, the mockup's `.kgg`), exactly like the micro menu
glyphs from generate_deck_glyphs.py. White RGB, shape in alpha; Lua tints it with
SetVertexColor.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28
(top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_hud_key_glyphs.py
"""

import math
import os
import re
import struct

SIZE = 32
VIEWBOX = 16.0
SCALE = SIZE / VIEWBOX          # 2 texels per SVG unit
SUPERSAMPLE = 4
STROKE_SVG = 1.6                # .kgl stroke-width, SVG units
CURVE_STEPS = 16

# GLY, verbatim: (path d, stroke opacity) per path, then filled circles (cx, cy, r) and
# stroked circles. Order inside a glyph does not matter (coverage is the max).
GLYPHS = {
    "chev": {
        "paths": [("M3 9.8L8 5l5 4.8", 1.0), ("M3 14L8 9.2l5 4.8", 0.55)],
    },
    "play": {
        "paths": [("M4 3.2v9.6L11 8z", 1.0), ("M13 3.2v9.6", 1.0)],
    },
    "diamond": {
        "paths": [("M8 1.8l4.4 6.2L8 14.2 3.6 8z", 1.0), ("M3.6 8h8.8", 0.5)],
    },
    "shield": {
        "paths": [
            ("M8 1.8l5 1.8v4.2c0 3-2.2 5-5 6.4C5.2 12.8 3 10.8 3 7.8V3.6z", 1.0),
            ("M5.8 7.6l1.6 1.6 2.9-3", 1.0),
        ],
    },
    "cross": {
        "circles": [(8.0, 8.0, 4.2)],
        "paths": [("M8 1.2v3.2M8 11.6v3.2M1.2 8h3.2M11.6 8h3.2", 1.0)],
        "dots": [(8.0, 8.0, 0.9)],
    },
    "clock": {
        "circles": [(8.0, 8.0, 5.8)],
        "paths": [("M8 4.6V8l2.3 1.5", 1.0)],
    },
    "bolt": {
        "paths": [("M9.4 1.4L3.6 9.2h4l-1 5.4 6-8H8.6z", 1.0)],
    },
    "group": {
        "circles": [(8.0, 5.0, 2.1), (3.2, 6.6, 1.5), (12.8, 6.6, 1.5)],
        "paths": [
            ("M4.6 13c0-2.5 1.5-3.9 3.4-3.9s3.4 1.4 3.4 3.9", 1.0),
            ("M1 12.6c0-1.8.9-2.9 2.3-2.9", 1.0),
            ("M15 12.6c0-1.8-.9-2.9-2.3-2.9", 1.0),
        ],
    },
}

_TOKEN = re.compile(r"[MmLlHhVvCcSsZz]|-?(?:\d+\.?\d*|\.\d+)")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Z": 0}


def _cubic(p0, p1, p2, p3):
    out = []
    for i in range(1, CURVE_STEPS + 1):
        t = i / CURVE_STEPS
        u = 1.0 - t
        out.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        ))
    return out


def parse_path(d):
    """SVG path data to a list of (points, closed) subpaths, in SVG units.

    Handles M L H V C S Z and their relative forms, which is every command the GLY
    table uses (no arcs, no quadratics). Curves are flattened to CURVE_STEPS lines."""
    tokens = _TOKEN.findall(d)
    subpaths = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    pts = []
    prev_ctrl = None
    cmd = None
    i = 0

    def finish(closed):
        nonlocal pts
        if len(pts) > 1:
            subpaths.append((pts, closed))
        pts = []

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                if pts:
                    pts.append(start)
                finish(True)
                cur = start
                prev_ctrl = None
                continue
        upper = cmd.upper()
        rel = cmd.islower()
        n = _ARGS[upper]
        a = [float(t) for t in tokens[i:i + n]]
        i += n
        ox, oy = cur if rel else (0.0, 0.0)
        if upper == "M":
            finish(False)
            cur = start = (a[0] + ox, a[1] + oy)
            pts = [cur]
            cmd = "l" if rel else "L"    # extra pairs after a moveto are linetos
            prev_ctrl = None
        elif upper == "L":
            cur = (a[0] + ox, a[1] + oy)
            pts.append(cur)
            prev_ctrl = None
        elif upper == "H":
            cur = (a[0] + ox, cur[1])
            pts.append(cur)
            prev_ctrl = None
        elif upper == "V":
            cur = (cur[0], a[0] + oy)
            pts.append(cur)
            prev_ctrl = None
        elif upper == "C":
            c1 = (a[0] + ox, a[1] + oy)
            c2 = (a[2] + ox, a[3] + oy)
            end = (a[4] + ox, a[5] + oy)
            pts += _cubic(cur, c1, c2, end)
            cur, prev_ctrl = end, c2
        else:  # S: first control point is the reflection of the previous second one
            c1 = cur if prev_ctrl is None else (2 * cur[0] - prev_ctrl[0], 2 * cur[1] - prev_ctrl[1])
            c2 = (a[0] + ox, a[1] + oy)
            end = (a[2] + ox, a[3] + oy)
            pts += _cubic(cur, c1, c2, end)
            cur, prev_ctrl = end, c2
    finish(False)
    return subpaths


def circle_points(cx, cy, r, steps=48):
    return [(cx + r * math.cos(2 * math.pi * k / steps), cy + r * math.sin(2 * math.pi * k / steps))
            for k in range(steps + 1)]


def glyph_strokes(spec):
    """(points, stroke opacity) polylines, in SVG units."""
    out = []
    for cx, cy, r in spec.get("circles", []):
        out.append((circle_points(cx, cy, r), 1.0))
    for d, opacity in spec.get("paths", []):
        for pts, _closed in parse_path(d):
            out.append((pts, opacity))
    return out


def glyph_dots(spec):
    return spec.get("dots", [])


def _seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return (px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2


def build(spec):
    """Alpha rows for one glyph: round-capped, round-joined strokes of STROKE_SVG
    units, solid dots, each stroke at its own opacity, combined by max."""
    half = STROKE_SVG / 2.0
    half2 = half * half
    segs = []   # (ax, ay, bx, by, opacity, minx, miny, maxx, maxy) in SVG units
    for pts, opacity in glyph_strokes(spec):
        for a, b in zip(pts, pts[1:]):
            segs.append((a[0], a[1], b[0], b[1], opacity,
                         min(a[0], b[0]) - half, min(a[1], b[1]) - half,
                         max(a[0], b[0]) + half, max(a[1], b[1]) + half))
    dots = [(cx, cy, r * r) for cx, cy, r in glyph_dots(spec)]
    n = SUPERSAMPLE * SUPERSAMPLE
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                py = (y + (sy + 0.5) / SUPERSAMPLE) / SCALE
                for sx in range(SUPERSAMPLE):
                    px = (x + (sx + 0.5) / SUPERSAMPLE) / SCALE
                    best = 0.0
                    for cx, cy, r2 in dots:
                        if (px - cx) ** 2 + (py - cy) ** 2 <= r2:
                            best = 1.0
                            break
                    if best < 1.0:
                        for ax, ay, bx, by, op, x0, y0, x1, y1 in segs:
                            if op > best and x0 <= px <= x1 and y0 <= py <= y1 \
                                    and _seg_dist2(px, py, ax, ay, bx, by) <= half2:
                                best = op
                                if best >= 1.0:
                                    break
                    total += best
            rows += bytes((255, 255, 255, int(round(total / n * 255))))
    return bytes(rows)


def write_tga(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for name, spec in GLYPHS.items():
        path = os.path.join(here, f"glyph_hud_{name}.tga")
        write_tga(path, build(spec))
        print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
