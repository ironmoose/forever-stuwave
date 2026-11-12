#!/usr/bin/env python3
"""Generates the shared controls kit's checkbox and radio art: ctl_diamond_fill, ctl_diamond_ring1, ctl_diamond_ring2,
ctl_diamond_node and ctl_tick (mockups/shared-controls-2026-11-12.html, check() and radio()).

Each file is white RGB with the shape in alpha, tinted by SetVertexColor in Lua, and drawn at the pixel size the control
shows it (one texel a screen pixel, the Mail build's "one mock px = one physical px"), so an edge is one crisp pixel and
only the 45 degree runs carry coverage:

    ctl_diamond_fill   16 x 16   the radio's rhombus through the four side midpoints (|x - 8| + |y - 8| <= 8)
    ctl_diamond_ring1  16 x 16   the same rhombus as a 1 px stroke (the idle and hover edge)
    ctl_diamond_ring2  16 x 16   the same rhombus as a 2 px stroke (the selected edge)
    ctl_diamond_node   8 x 8     the 6 px selection node (points at 5 and 11 on the 16 box), art at the top left
    ctl_tick           16 x 16   the checkbox tick: (3, 8) -> (6, 11) -> (11, 6) at stroke 2, butt ends

A stroke of width w along a 45 degree edge measures w * sqrt(2) along the axes, so the rings are bands of the rhombus's
L1 radius, 8 down to 8 - w * sqrt(2). A 45 degree edge through whole pixel corners lands exactly on the supersample
lattice, so a sample that falls on an edge counts half (counting it in or out biases every edge texel the same way).

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_control_checks.py
"""

import math
import os
import struct

SUPERSAMPLE = 8

DIAMOND_SIZE = 16
DIAMOND_RADIUS = 8.0
NODE_SIZE = 8
NODE_RADIUS = 3.0
TICK_SIZE = 16
TICK_STROKE = 2.0
TICK_POINTS = ((3.0, 8.0), (6.0, 11.0), (11.0, 6.0))


EPS = 1e-9


def below(value, limit):
    """1 when value < limit, 0.5 on the limit itself, 0 above it."""
    if abs(value - limit) <= EPS:
        return 0.5
    return 1.0 if value < limit else 0.0


def diamond_inside(radius, inner=0.0):
    """Inside the rhombus of L1 `radius` about its canvas centre, outside the one of L1 `inner` (a ring)."""
    cx = cy = DIAMOND_SIZE / 2

    def inside(px, py):
        d = abs(px - cx) + abs(py - cy)
        return below(d, radius) * (1.0 - below(d, inner) if inner else 1.0)

    return inside


def node_inside(px, py):
    return below(abs(px - NODE_RADIUS) + abs(py - NODE_RADIUS), NODE_RADIUS)


def tick_inside(px, py):
    """Both segments with butt ends, plus a round join at the vertex so the corner has no notch."""
    (ax, ay), (bx, by), (cx, cy) = TICK_POINTS
    half = TICK_STROKE / 2
    best = 0.0
    for (x0, y0), (x1, y1) in (((ax, ay), (bx, by)), ((bx, by), (cx, cy))):
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        along = (px - x0) * ux + (py - y0) * uy
        across = abs(-(px - x0) * uy + (py - y0) * ux)
        start = 1.0 - below(along, 0.0) if along > -EPS else 0.0
        best = max(best, start * below(along, length) * below(across, half))
    return max(best, below(math.hypot(px - bx, py - by), half))


def build(size, inside):
    rows = bytearray()
    for ty in range(size):
        for tx in range(size):
            hits = 0.0
            for sy in range(SUPERSAMPLE):
                py = ty + (sy + 0.5) / SUPERSAMPLE
                for sx in range(SUPERSAMPLE):
                    hits += inside(tx + (sx + 0.5) / SUPERSAMPLE, py)
            rows += bytes((255, 255, 255, int(round(hits / (SUPERSAMPLE * SUPERSAMPLE) * 255))))
    return bytes(rows)


def write(directory, name, size, inside):
    path = os.path.join(directory, name + ".tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build(size, inside))
    print(f"wrote {path} ({size}x{size}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get(
        "FS_ASSET_OUTPUT_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"),
    )
    write(here, "ctl_diamond_fill", DIAMOND_SIZE, diamond_inside(DIAMOND_RADIUS))
    write(here, "ctl_diamond_ring1", DIAMOND_SIZE, diamond_inside(DIAMOND_RADIUS, DIAMOND_RADIUS - 1.0 * math.sqrt(2)))
    write(here, "ctl_diamond_ring2", DIAMOND_SIZE, diamond_inside(DIAMOND_RADIUS, DIAMOND_RADIUS - 2.0 * math.sqrt(2)))
    write(here, "ctl_diamond_node", NODE_SIZE, node_inside)
    write(here, "ctl_tick", TICK_SIZE, tick_inside)
