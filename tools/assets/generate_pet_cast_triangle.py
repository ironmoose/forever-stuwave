#!/usr/bin/env python3
"""Generates pet_cast_triangle.tga: a single equilateral triangle, apex up,
for the pet cast bar's zigzag reveal strip (Phase 6, addons/ForeverSynthwave/
PetCastBar.lua).

Same supersampled-coverage antialiasing technique as
generate_cut_corner_outline.py's _chamfer_coverage / generate_cell_slant.py's
coverage: a straight diagonal edge through a low-res raster still aliases
without it. White RGB, coverage fraction in the alpha channel only, so the
Lua side tints it per-triangle via SetVertexColor at runtime (exactly like
cell_slant.tga's own docstring says) -- no color is baked into this texture.

POWER-OF-TWO DEVIATION FROM THE NAIVE EQUILATERAL CANVAS (read this before
changing WIDTH/HEIGHT): the equilateral relation triangle-width ==
triangle-height * (2/sqrt(3)) computes to 37 at HEIGHT=32, and a canvas sized
to exactly that (37x32) would seem like the obvious "bake the proportions
into the canvas" reading of the design brief. It is also exactly the trap
generate_grid.py's own docstring already documents and this directory's
test_tga_generators.py now enforces as a hard invariant on EVERY generator
here (test_generator_writes_valid_tga's _is_power_of_two assert): WoW
silently refuses to render a file texture whose dimensions are not a power
of two. Shipping a 37x32 texture would not error -- it would just never draw
in game, discovered only by an in-game look, and would fail this directory's
own regression test along the way (a SECOND pytest failure beyond the
pre-existing, unrelated cut_corner_outline gap).

So the canvas is CANVAS_WIDTH x HEIGHT = 64 x 32 (both powers of two), and
the true equilateral-proportioned shape is drawn inset within only the LEFT
TRIANGLE_WIDTH (37) texels of that wider canvas; every texel from
TRIANGLE_WIDTH to CANVAS_WIDTH is fully transparent padding, never sampled
for content. The Lua side crops that padding away at render time via
Texture:SetTexCoord's 4-arg (minX, maxX, minY, maxY) form, minX=0,
maxX=TEXCOORD_U_MAX (TRIANGLE_WIDTH / CANVAS_WIDTH, printed by main() below)
-- so the triangle's own pixels are never stretched or resampled, only the
invisible padding is cropped out of the sample rect. This is the "no runtime
stretch distortion" requirement from a different angle than a same-sized
canvas would give it, not an abandonment of it.

Pure stdlib, like every other generator in this directory. Output: 18-byte
header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom -- same struct.pack header line and file-writing shape as
generate_cut_corner_outline.py / generate_cell_slant.py.

    python3 generate_pet_cast_triangle.py
"""

import math
import os
import struct

HEIGHT = 32  # already a power of two; the triangle's full pixel height.

# The equilateral relation itself: triangle width = triangle height *
# (2/sqrt(3)). This is geometric fact, not a tunable guess -- kept as a
# computed expression (not a bare literal) so that relationship stays
# visible in the source. Matches TRIANGLE_WIDTH_RATIO on the Lua side
# (PetCastBar.lua) within reasonable rounding.
TRIANGLE_WIDTH = round(HEIGHT * (2 / math.sqrt(3)))  # == 37

# Smallest power of two that fits TRIANGLE_WIDTH -- see the POWER-OF-TWO
# DEVIATION note above for why this canvas is wider than the shape itself.
CANVAS_WIDTH = 1
while CANVAS_WIDTH < TRIANGLE_WIDTH:
    CANVAS_WIDTH *= 2

# Padding between the triangle's own edges and TRIANGLE_WIDTH/HEIGHT's own
# bounds, texels, for antialiasing headroom -- same "1-2px inset" idea as
# generate_cut_corner_outline.py's CHAMFER/THICKNESS margin. Starting guess
# pending Parker's eyeball against the Pet Frame Designer artifact.
PADDING = 1.5

# Antialiasing subpixel grid (NxN samples per texel), same technique and
# same value as generate_cut_corner_outline.py's SUPERSAMPLE.
SUPERSAMPLE = 6

# Triangle vertices within the content region [0, TRIANGLE_WIDTH) x
# [0, HEIGHT): apex at top-center, base along the bottom edge, per the
# locked design ("pointing UP, apex at top-center, base along the bottom
# edge"). Inset by PADDING on every side.
_APEX = (TRIANGLE_WIDTH / 2.0, PADDING)
_BASE_LEFT = (PADDING, HEIGHT - PADDING)
_BASE_RIGHT = (TRIANGLE_WIDTH - PADDING, HEIGHT - PADDING)


def _edge(ax, ay, bx, by, px, py):
    """Signed area of the edge A->B against point P (a half-plane test)."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def _point_in_triangle(px, py):
    """True if (px, py) is on the same side of all three edges A->B->C->A.

    Half-plane test against the triangle's three edges, same style as
    generate_cut_corner_outline.py's _chamfer_coverage per-edge cutoff
    tests: a point is inside iff every edge function has the same sign
    (the triangle here is always wound consistently, so no separate
    clockwise/counterclockwise branch is needed).
    """
    ax, ay = _APEX
    bx, by = _BASE_LEFT
    cx, cy = _BASE_RIGHT

    d1 = _edge(ax, ay, bx, by, px, py)
    d2 = _edge(bx, by, cx, cy, px, py)
    d3 = _edge(cx, cy, ax, ay, px, py)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def coverage(x, y):
    """Fraction of texel (x, y) inside the triangle, via supersampling."""
    if x >= TRIANGLE_WIDTH:
        # Padding region: never any content here, skip the supersample loop.
        return 0.0

    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            py = y + (sy + 0.5) / SUPERSAMPLE
            if _point_in_triangle(px, py):
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(HEIGHT):
        for x in range(CANVAS_WIDTH):
            alpha = int(round(coverage(x, y) * 255))
            # White RGB; coverage lives entirely in the alpha channel so the
            # Lua side can tint it via SetVertexColor at runtime.
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    path = os.path.join(here, "pet_cast_triangle.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, CANVAS_WIDTH, HEIGHT, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    texcoord_u_max = TRIANGLE_WIDTH / CANVAS_WIDTH
    print(f"wrote {path} ({CANVAS_WIDTH}x{HEIGHT}, {os.path.getsize(path)} bytes)")
    print(f"triangle content width = {TRIANGLE_WIDTH} texels; "
          f"Lua-side SetTexCoord U crop = 0..{texcoord_u_max:.6f}")


if __name__ == "__main__":
    main()
