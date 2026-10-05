#!/usr/bin/env python3
"""Generates shoulder_glow.tga: the three pieces of the Paladin shoulder's halo that the Console's own
glow texture cannot draw.

The Gunsight mockup's default Console style bakes the Paladin shoulder (a 306.8 x 91.8 block standing on
the chassis top edge) into the chassis outline, so the shoulder is haloed by the SAME stepped profile as
the chassis: `halo(true)` strokes the outline four times, each wider by 2 w and drawn at alpha
a x CN_GK x A(.7), (w, a) = (1.5, .26) (3.2, .17) (5, .10) (7, .055) in image px, and outside the path the
layers composite source-over. generate_console_chrome.py documents the arithmetic and bakes it into
console_glow_c14.tga; this file uses the very same profile (HALO below is a copy: every generator here is
a stand-alone script that is run from a copy in a temp dir, so it cannot import a sibling). The straight
runs of the shoulder (top, left and right sides) and its square top right corner are drawn with
console_glow_c14.tga itself, UV for UV like the Console draws its own, so they are identical by
construction. That texture has a 14 cut at the top left and bottom right and no foot, so three places are
baked here, each a piece of the halo of the SAME outline:

    TL     the halo around the top left cut 6 (LS_C): the block x, y in [-11, 6]
    FLARE  the halo of the right side's last stretch, the vertex and the 45 degree foot (LS_F = 10), out
           to where the foot stops mattering and the Console's top halo resumes: x in [0, 15] of the right
           edge (the foot ends 10.2071 out and its diagonal still outshines the chassis line above it for
           0.4142 x the profile's 9.536 reach more, 14.16), y from ABOVE = 12 above the vertex down to the
           chassis top line
    BL     the concave corner where the left side meets the chassis top line: x, y in [-11, 0]. The
           nearest outline is the left side or the top line, so a Console strip and a shoulder strip
           laid over each other would composite twice there; one baked piece says min(distance)

White RGB, shape in alpha, tinted by the caller (violet at vertex alpha 1; the .7 of A(.7) is baked in,
like console_glow_c14). One texel is one design px. Each piece is baked with MARGIN = 2 texels of the real
halo field around it, so the bilinear filter at the edge of its UV window reads the continuing halo and not
the next piece or empty canvas. The pieces sit in a 64 x 64 canvas:

    piece   atlas rect (x, y, w, h) of the PIECE, margin excluded
    TL      (2, 2, 17, 17)     GLOW_PAD + CUT wide and tall
    FLARE   (26, 2, 15, 22)    FLARE_W wide, ABOVE + FLARE tall
    BL      (48, 2, 11, 11)    GLOW_PAD square

PetDock.lua carries the same rects (PetDock.C.SHOULDER_GLOW) and classshoulder-harness.py reads them out of
this file, rasterizes the real textures and compares every texel with the mockup's halo around the outline.

GEOMETRY (piece-local design px, y down). The outline's OUTER edge is what the halo is measured from. The
sides are the columns x = 0 and x = W; the 45 degree foot is a 1 px stroke whose centreline runs
(W - .5, H - f) to (W - .5 + f, H), so its outer edge lies .5 / sqrt 2 * 2 = .7071 off the centreline, which
puts it at x = W where it meets the vertical, .2071 above the centreline vertex, and
W + f + .2071 where it meets the chassis top line (the same numbers as generate_pet_dock_flare.py).

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top to bottom.

    python3 generate_shoulder_glow.py
"""

import math
import os
import struct

CANVAS = 64
MARGIN = 2                   # texels of the real halo field kept around every piece
GLOW_PAD = 11                # the Console's GP: texels from the glow canvas edge to the outline
CUT = 6                      # the shoulder's top left cut, LS_C
FLARE = 10                   # the foot's flare, LS_F
FLARE_W = 15                 # the FLARE piece's width: ceil(10.2071 + (sqrt 2 - 1) x 9.536), see the header
ABOVE = 12                   # how far above the foot's vertex the FLARE piece starts
SUPERSAMPLE = 4              # per axis, like generate_console_chrome.py
STROKE_OFF = 0.5 * math.sqrt(2.0) - 0.5   # see GEOMETRY
FAR = 60.0                   # "infinitely" far, for the outline's long runs

# Atlas rects (x, y, w, h) of the pieces, margin excluded. PetDock.C.SHOULDER_GLOW mirrors them.
TL = (2, 2, GLOW_PAD + CUT, GLOW_PAD + CUT)
FLARE_PIECE = (26, 2, FLARE_W, ABOVE + FLARE)
BL = (48, 2, GLOW_PAD, GLOW_PAD)

# cnBake's halo (see generate_console_chrome.py): [stroke half width extra, alpha] in image px.
HALO = [(1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055)]
CORE_HALF_IMAGE = 0.45
IMAGE_TO_DESIGN = 1.28
GLOW_GAIN = 1.7              # CN_GK
OVERALL_ALPHA = 0.7          # A(.7) in front of halo(true)
REACHES = [((w + CORE_HALF_IMAGE) * IMAGE_TO_DESIGN, min(1.0, a * GLOW_GAIN * OVERALL_ALPHA))
           for w, a in HALO]


def halo_alpha(dist):
    keep = 1.0
    for reach, alpha in REACHES:
        if dist <= reach:
            keep *= 1.0 - alpha
    return 1.0 - keep


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def inside(px, py, poly):
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def outline_field(path, closing):
    """The halo of an open outline: 0 inside the shape (the path closed by `closing`), else the stepped
    profile of the distance to the path."""
    shape = path + closing

    def fn(x, y):
        if inside(x, y, shape):
            return 0.0
        return halo_alpha(min(seg_dist(x, y, path[i], path[i + 1]) for i in range(len(path) - 1)))

    return fn


def piece_fields():
    """name -> (rect, field function of piece-local design px)."""
    g, c = float(GLOW_PAD), float(CUT)
    # TL: local origin = the block's top left, art (-11, -11); the chassis corner (0, 0) is at (g, g).
    tl = [(g, g + FAR), (g, g + c), (g + c, g), (g + FAR, g)]
    tl_field = outline_field(tl, [(g + FAR, g + FAR)])
    # FLARE: local origin = the piece's top left, the right edge x = 0, the foot's vertex ABOVE down.
    drop = float(ABOVE)
    flare = [(0.0, -FAR), (0.0, drop - STROKE_OFF), (FLARE + STROKE_OFF, drop + FLARE), (FAR, drop + FLARE)]
    flare_field = outline_field(flare, [(FAR, FAR), (-FAR, FAR), (-FAR, -FAR)])
    # BL: local origin = the block's top left, art (-11, H - 11); the concave corner (0, H) is at (g, g).
    bl = [(-FAR, g), (g, g), (g, -FAR)]
    bl_field = outline_field(bl, [(FAR, -FAR), (FAR, FAR), (-FAR, FAR)])
    return {"TL": (TL, tl_field), "FLARE": (FLARE_PIECE, flare_field), "BL": (BL, bl_field)}


def build_canvas():
    grid = [[0.0] * CANVAS for _ in range(CANVAS)]
    n = SUPERSAMPLE * SUPERSAMPLE
    for rect, fn in piece_fields().values():
        ax, ay, w, h = rect
        for cy in range(ay - MARGIN, ay + h + MARGIN):
            for cx in range(ax - MARGIN, ax + w + MARGIN):
                total = 0.0
                for sy in range(SUPERSAMPLE):
                    for sx in range(SUPERSAMPLE):
                        total += fn(cx - ax + (sx + 0.5) / SUPERSAMPLE, cy - ay + (sy + 0.5) / SUPERSAMPLE)
                grid[cy][cx] = total / n
    return grid


def write_tga(path, grid):
    height, width = len(grid), len(grid[0])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    rows = bytearray()
    for row in grid:
        for v in row:
            rows += bytes((255, 255, 255, int(round(v * 255))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    write_tga(os.path.join(here, "shoulder_glow.tga"), build_canvas())


if __name__ == "__main__":
    main()
