#!/usr/bin/env python3
"""Generates the Shaman totem tab's hover PIECE and its tab BUMP.

Reference: the design mockup, concept V1 "As drawn" (pieceRel, pieceSvg, neonArrow,
bumpPts). On hover an element button grows a square cap piece above it; the tab outline grows a bump around the
piece. WoW cannot draw the slanted edge, the chevron gradient or the haze at run time, so they are baked here.

Every texture is white RGB with the shape in alpha. TotemPiece.lua tints them: the element colour, the hot
magenta of the gradient, the Console's violet. Nothing is baked in colour, so one set serves all four elements.

THE PIECE (design px, relative to the element button's top left corner, y down). The button's top left chamfer
is 5, so its cut runs x + y = 5. The piece is square on three sides: left edge x = 0, top y = -13, right edge
x = 38, the bar 11 thick with an even 2 px seam above the button top. Its one slanted edge is the lower left,
parallel to the cut with a 2 px seam (the cut continues as a seam), ending in a small tip over the empty cut
corner. Vertices: (0, 2.17) (0, -13) (38, -13) (38, -2) (4.17, -2).

  PIECE canvas (PIECE_CANVAS_W x PIECE_CANVAS_H texels, PIECE_K texels per design px, origin PIECE_ORIGIN):
    totem_piece_fill       the polygon, solid
    totem_piece_scan       the faint scanlines, clipped to the polygon (the mockup's 0.5 px lines, every 1.5 px)
    totem_piece_glow       the lit state's outer glow: a 1 px stroke along the edge, blurred and merged
    totem_piece_edge       the 2 px stroke clipped to the polygon, which is the 1 px that shows inside it
  CHEVRON canvas (the same size, origin CHEV_ORIGIN, centred on the chevron so a vertical flip about the
  texture's own centre turns the up chevron into the down one):
    totem_chev_body        the bold chevron, 30 wide: apex (19, -11.6), arms 5.2 down, 3.4 thick
    totem_chev_pink        the same shape with the gradient's magenta share baked as alpha (0 at the arm feet,
                           .6 at the middle, 1 at the apex): layered over the element tinted body it makes the
                           mockup's element to magenta gradient
    totem_chev_haze        the soft glow of the chevron: the shape plus a 3.6 px stroke, blurred
    totem_chev_haze_pink   the haze with the same magenta share
    totem_chev_core        the thin near white core line through the middle of the arms

THE BUMP. While the piece is up the tab outline grows a bump around it: same Console stroke, fill and halo as the
tab, vertical walls, square top corners. The left wall stands BUMP_LEFT px left of the button (4, or 6 on the
leftmost button, where it meets the tab's own left wall), the right wall 4 px right of it, and the right wall
returns to the rail through a 45 degree foot of BUMP_FOOT px, like the tab's own right flare. The bump top is
BUMP_RISE above the rail. Design px relative to the button's top left; the rail's outer edge is y = RAIL.
The fill is plain rectangles and a cut wedge in Lua; what is baked here:

  totem_bump_stroke   the 1 px outline of the bump (inside its outer edge, like the tab's own strokes), both
                      variants in one 256 canvas at BUMP_K texels per px. Normal variant at the top, the
                      leftmost (Fire) one under it. White; Lua tints the Console's violet at its stroke alpha.
  totem_bump_halo     the Console's halo of the same outline, stepped profile and all (it is the profile of
                      generate_shoulder_glow.py, which is the Console's), one texel per px, both variants in a
                      128 x 64 canvas. The halo of the rail resumes either side of it, so each piece carries
                      the concave corners (the nearest outline wins: one composite, never two).

THE FLYOUT. While the icon picker is open the bump's top is open between the button's two edges and a chimney rises
out of it (Lua: TotemPiece.SetFlyout; the mockup's open state). Its walls, top line, fill and the straight runs of
its halo are plain rectangles and the Console's own halo strips; its top left cut uses the shared cut pieces. What
the Console's pieces cannot draw is where the chimney's walls meet the bump's top (the concave corners, where the
nearest outline wins), so those two junctions are baked here, for the open shape instead of the closed bump:

  totem_flyout_halo   the halo left of the chimney's left wall (normal and leftmost variants) and right of its right
                      wall, from 11 px over the bump top down to the rail, one texel per px, three pieces in a
                      64 square canvas.

Pure stdlib, like every generator here. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin,
8 alpha bits), BGRA top to bottom.

    python3 generate_totem_piece.py
"""

import math
import os
import struct

SS = 4                       # supersamples per texel and axis
SQRT2 = math.sqrt(2.0)

# ---- the piece ----
BTN_W = 38.0
CUT = 5.0                    # the button's top left chamfer
SEAM = 2.0
BAR = 11.0
TOP = -(SEAM + BAR)          # -13
PIECE_K = 4
PIECE_CANVAS_W, PIECE_CANVAS_H = 256, 128
PIECE_ORIGIN = (-13.0, -21.0)
CHEV_ORIGIN = (-13.0, -23.3)
_D = SEAM * SQRT2
PIECE = [(0.0, CUT - _D), (0.0, TOP), (BTN_W, TOP), (BTN_W, -SEAM), (CUT - _D + SEAM, -SEAM)]
SCAN_PITCH, SCAN_WIDTH = 1.5, 0.5
GLOW_SIGMA = 1.2
EDGE_WIDTH = 1.0             # the visible inner stroke

# the chevron (mockup neonArrow, V1 hover): relative to the button, apex first
CHEV_CX, CHEV_APEX = 19.0, -11.6
CHEV_HALF, CHEV_ARM, CHEV_THICK = 15.0, 5.2, 3.4
CHEV = [
    (CHEV_CX, CHEV_APEX), (CHEV_CX + CHEV_HALF, CHEV_APEX + CHEV_ARM),
    (CHEV_CX + CHEV_HALF, CHEV_APEX + CHEV_ARM + CHEV_THICK), (CHEV_CX, CHEV_APEX + CHEV_THICK),
    (CHEV_CX - CHEV_HALF, CHEV_APEX + CHEV_ARM + CHEV_THICK), (CHEV_CX - CHEV_HALF, CHEV_APEX + CHEV_ARM),
]
CORE = [
    (CHEV_CX - CHEV_HALF, CHEV_APEX + CHEV_ARM + CHEV_THICK / 2.0), (CHEV_CX, CHEV_APEX + CHEV_THICK / 2.0),
    (CHEV_CX + CHEV_HALF, CHEV_APEX + CHEV_ARM + CHEV_THICK / 2.0),
]
CORE_WIDTH = 0.6
HAZE_STROKE = 3.6
HAZE_SIGMA = 1.6

# ---- the bump ----
BUMP_K = 4
BUMP_CANVAS = 256
HALO_CANVAS_W, HALO_CANVAS_H = 128, 64
BTN_TOP_ART = 6.0            # the button's top, design px under the tab's top line
RAIL = -6.0                  # the tab's rail outer edge, relative to the button top
BUMP_RISE = 11.0             # bump top above the rail
BUMP_TOP = RAIL - BUMP_RISE  # -17
BUMP_RIGHT = BTN_W + 4.0     # outer edge of the right wall: 42
BUMP_FOOT = 6.0
VERTEX = RAIL - BUMP_FOOT    # the foot's vertex y
STROKE_OFF = 0.5 * SQRT2 - 0.5
GLOW_PAD = 11.0
FAR = 400.0
VARIANTS = {"normal": -4.0, "fire": -6.0}        # left wall outer edge x

# atlas rects (texels): the region of the canvas each variant occupies, margin included
# stroke region in design px: x from left wall - 1 to the foot's end + 1, y from the top - 1 to RAIL + 2 (normal)
# or to the end of the leftmost wall at the button top (fire)
BUMP_STROKE_REGION = {
    "normal": (-5.0, BUMP_TOP - 1.0, BUMP_RIGHT + BUMP_FOOT + 1.0, RAIL + 2.0),
    "fire": (-7.0, BUMP_TOP - 1.0, BUMP_RIGHT + BUMP_FOOT + 1.0, 1.0),
}
BUMP_STROKE_AT = {"normal": (2, 2), "fire": (2, 64)}
# halo region in design px (x0, y0, x1, y1): GLOW_PAD around the wall, reaching the rail's halo either side
BUMP_HALO_REGION = {
    "normal": (-4.0 - GLOW_PAD, BUMP_TOP - GLOW_PAD, BUMP_RIGHT + GLOW_PAD, RAIL),
    "fire": (-6.0 - GLOW_PAD, BUMP_TOP - GLOW_PAD, BUMP_RIGHT + GLOW_PAD, 0.0),
}
BUMP_HALO_AT = {"normal": (2, 2), "fire": (2, 32)}
HALO_BLEED = 2                # texels of the real halo field kept around each piece, for the bilinear filter

# ---- the flyout (the chimney's two junctions with the bump top) ----
FLY_LEFT, FLY_RIGHT = 0.0, BTN_W        # the chimney's walls: the button's own edges
FLY_HALO_CANVAS = 64
FLY_HALO_REGION = {
    "left": (-4.0 - GLOW_PAD, BUMP_TOP - GLOW_PAD, FLY_LEFT, RAIL),
    "left_fire": (-6.0 - GLOW_PAD, BUMP_TOP - GLOW_PAD, FLY_LEFT, 0.0),
    "right": (FLY_RIGHT, BUMP_TOP - GLOW_PAD, BUMP_RIGHT + GLOW_PAD, RAIL),
}
FLY_HALO_AT = {"left": (2, 2), "left_fire": (22, 2), "right": (44, 2)}

# the Console's halo profile (generate_shoulder_glow.py)
HALO = [(1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055)]
CORE_HALF_IMAGE = 0.45
IMAGE_TO_DESIGN = 1.28
GLOW_GAIN = 1.7
OVERALL_ALPHA = 0.7
REACHES = [((w + CORE_HALF_IMAGE) * IMAGE_TO_DESIGN, min(1.0, a * GLOW_GAIN * OVERALL_ALPHA)) for w, a in HALO]


# ---------------------------------------------------------------- geometry helpers

def inside(px, py, poly):
    c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def edge_dist(px, py, poly):
    n = len(poly)
    return min(seg_dist(px, py, poly[i], poly[(i + 1) % n]) for i in range(n))


def line_dist(px, py, pts):
    return min(seg_dist(px, py, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def halo_alpha(dist):
    keep = 1.0
    for reach, alpha in REACHES:
        if dist <= reach:
            keep *= 1.0 - alpha
    return 1.0 - keep


def bake(width, height, k, origin, value_at):
    """A height x width grid: texel (tx, ty) averages value_at over SS x SS samples, in design px relative to the
    button (origin is the canvas top left)."""
    grid = []
    for ty in range(height):
        row = []
        for tx in range(width):
            total = 0.0
            for sy in range(SS):
                y = origin[1] + (ty + (sy + 0.5) / SS) / k
                for sx in range(SS):
                    total += value_at(origin[0] + (tx + (sx + 0.5) / SS) / k, y)
            row.append(total / (SS * SS))
        grid.append(row)
    return grid


def blur(grid, sigma_px, k):
    sigma = sigma_px * k
    radius = int(math.ceil(sigma * 3))
    kernel = [math.exp(-(i * i) / (2 * sigma * sigma)) for i in range(-radius, radius + 1)]
    total = sum(kernel)
    kernel = [v / total for v in kernel]

    def conv(g):
        width = len(g[0])
        out = []
        for row in g:
            new = []
            for x in range(width):
                s = 0.0
                for i, kv in enumerate(kernel):
                    xx = x + i - radius
                    if 0 <= xx < width:
                        s += row[xx] * kv
                new.append(s)
            out.append(new)
        return out

    horiz = conv(grid)
    cols = conv([list(c) for c in zip(*horiz)])
    return [list(r) for r in zip(*cols)]


def mul(a, b):
    return [[x * y for x, y in zip(ra, rb)] for ra, rb in zip(a, b)]


def merge(src, under):
    """src over under, alpha only."""
    return [[s + u * (1.0 - s) for s, u in zip(rs, ru)] for rs, ru in zip(src, under)]


# ---------------------------------------------------------------- the piece layers

def piece_fill():
    return bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, PIECE_ORIGIN, lambda x, y: 1.0 if inside(x, y, PIECE) else 0.0)


def piece_edge():
    return bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, PIECE_ORIGIN,
                lambda x, y: 1.0 if inside(x, y, PIECE) and edge_dist(x, y, PIECE) <= EDGE_WIDTH else 0.0)


def piece_scan():
    ys = [y for _, y in PIECE]
    first = math.ceil(min(ys)) + 0.75
    centres = []
    yy = first
    while yy < max(ys):
        centres.append(yy)
        yy += SCAN_PITCH

    def value(x, y):
        if not inside(x, y, PIECE):
            return 0.0
        return 1.0 if any(abs(y - c) <= SCAN_WIDTH / 2.0 for c in centres) else 0.0

    return bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, PIECE_ORIGIN, value)


def piece_glow():
    ring = bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, PIECE_ORIGIN,
                lambda x, y: 1.0 if edge_dist(x, y, PIECE) <= 0.5 else 0.0)
    return merge(ring, blur(ring, GLOW_SIGMA, PIECE_K))


# ---------------------------------------------------------------- the chevron layers

def pink_share(y):
    """The magenta share of the gradient at design y: element at the arm feet (t = 0), magenta at the apex (t = 1),
    the stops 0 / .5 -> .6 / 1 of neonArrow."""
    foot = CHEV_APEX + CHEV_ARM + CHEV_THICK
    t = max(0.0, min(1.0, (foot - y) / (foot - CHEV_APEX)))
    return 1.2 * t if t <= 0.5 else 0.6 + 0.8 * (t - 0.5)


def chev_shape():
    return bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, CHEV_ORIGIN, lambda x, y: 1.0 if inside(x, y, CHEV) else 0.0)


def ramp(grid):
    out = []
    for ty, row in enumerate(grid):
        y = CHEV_ORIGIN[1] + (ty + 0.5) / PIECE_K
        share = pink_share(y)
        out.append([v * share for v in row])
    return out


def chev_haze():
    # the polygon plus its HAZE_STROKE wide stroke (HAZE_STROKE / 2 outside), then the haze blur
    solid = bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, CHEV_ORIGIN,
                 lambda x, y: 1.0 if inside(x, y, CHEV) or edge_dist(x, y, CHEV) <= HAZE_STROKE / 2.0 else 0.0)
    return blur(solid, HAZE_SIGMA, PIECE_K)


def chev_core():
    return bake(PIECE_CANVAS_W, PIECE_CANVAS_H, PIECE_K, CHEV_ORIGIN,
                lambda x, y: 1.0 if line_dist(x, y, CORE) <= CORE_WIDTH / 2.0 else 0.0)


# ---------------------------------------------------------------- the bump

def bump_stroke_value(variant):
    lx = VARIANTS[variant]
    wall_end = 0.0 if variant == "fire" else RAIL + 1.0       # fire: down to the button top, where the tab's own wall takes over

    def value(x, y):
        # left wall
        if lx <= x <= lx + 1.0 and BUMP_TOP <= y <= wall_end:
            return 1.0
        # top
        if lx <= x <= BUMP_RIGHT and BUMP_TOP <= y <= BUMP_TOP + 1.0:
            return 1.0
        # right wall, down to the foot's vertex
        if BUMP_RIGHT - 1.0 <= x <= BUMP_RIGHT and BUMP_TOP <= y <= VERTEX:
            return 1.0
        # the 45 degree foot: a 1 px band along (W - .5, vertex) -> (W - .5 + f, rail), butt end at the far end, cut
        # square at the vertex row (the right wall already covers the join) and clipped at the rail
        dx, dy = x - (BUMP_RIGHT - 0.5), y - VERTEX
        s, t = (dx - dy) / SQRT2, (dx + dy) / SQRT2
        if abs(s) <= 0.5 and t <= BUMP_FOOT * SQRT2 and VERTEX <= y <= RAIL:
            return 1.0
        return 0.0

    return value


def bump_halo_value(variant):
    lx = VARIANTS[variant]
    foot = [(BUMP_RIGHT, VERTEX - STROKE_OFF), (BUMP_RIGHT + BUMP_FOOT + STROKE_OFF, RAIL), (FAR, RAIL)]
    if variant == "normal":
        path = [(-FAR, RAIL), (lx, RAIL), (lx, BUMP_TOP), (BUMP_RIGHT, BUMP_TOP)] + foot
        closing = [(FAR, FAR), (-FAR, FAR)]
    else:
        path = [(lx, FAR), (lx, BUMP_TOP), (BUMP_RIGHT, BUMP_TOP)] + foot
        closing = [(FAR, FAR)]
    shape = path + closing

    def value(x, y):
        if inside(x, y, shape):
            return 0.0
        return halo_alpha(line_dist(x, y, path))

    return value


def flyout_halo_value(side):
    """The halo of the open outline: the chimney's wall rises from the bump top, so above the shoulder the nearest
    outline is the wall, and at the concave corner the wall and the shoulder's top share one composite."""
    if side == "right":
        foot = [(BUMP_RIGHT, VERTEX - STROKE_OFF), (BUMP_RIGHT + BUMP_FOOT + STROKE_OFF, RAIL), (FAR, RAIL)]
        path = [(FLY_RIGHT, -FAR), (FLY_RIGHT, BUMP_TOP), (BUMP_RIGHT, BUMP_TOP)] + foot
        closing = [(FAR, FAR), (-FAR, FAR), (-FAR, -FAR)]
    else:
        lx = VARIANTS["fire" if side == "left_fire" else "normal"]
        if side == "left":
            path = [(-FAR, RAIL), (lx, RAIL), (lx, BUMP_TOP), (FLY_LEFT, BUMP_TOP), (FLY_LEFT, -FAR)]
            closing = [(FAR, -FAR), (FAR, FAR), (-FAR, FAR)]
        else:
            path = [(lx, FAR), (lx, BUMP_TOP), (FLY_LEFT, BUMP_TOP), (FLY_LEFT, -FAR)]
            closing = [(FAR, -FAR), (FAR, FAR)]
    shape = path + closing

    def value(x, y):
        if inside(x, y, shape):
            return 0.0
        return halo_alpha(line_dist(x, y, path))

    return value


def canvas_with(width, height, pieces):
    """pieces: (atlas position of the piece itself, its grid, bleed texels around it already in the grid)."""
    grid = [[0.0] * width for _ in range(height)]
    for at, grid_piece, bleed in pieces:
        for y, row in enumerate(grid_piece):
            for x, v in enumerate(row):
                grid[at[1] - bleed + y][at[0] - bleed + x] = v
    return grid


def region_texels(region, k):
    x0, y0, x1, y1 = region
    return int(round((x1 - x0) * k)), int(round((y1 - y0) * k))


def build_bump_stroke():
    pieces = []
    for variant in VARIANTS:
        region = BUMP_STROKE_REGION[variant]
        w, h = region_texels(region, BUMP_K)
        pieces.append((BUMP_STROKE_AT[variant], bake(w, h, BUMP_K, (region[0], region[1]), bump_stroke_value(variant)), 0))
    return canvas_with(BUMP_CANVAS, BUMP_CANVAS, pieces)


def build_bump_halo():
    pieces = []
    for variant in VARIANTS:
        region = BUMP_HALO_REGION[variant]
        w, h = region_texels(region, 1)
        m = HALO_BLEED
        pieces.append((BUMP_HALO_AT[variant],
                       bake(w + 2 * m, h + 2 * m, 1, (region[0] - m, region[1] - m), bump_halo_value(variant)), m))
    return canvas_with(HALO_CANVAS_W, HALO_CANVAS_H, pieces)


def build_flyout_halo():
    pieces = []
    for side in FLY_HALO_REGION:
        region = FLY_HALO_REGION[side]
        w, h = region_texels(region, 1)
        m = HALO_BLEED
        pieces.append((FLY_HALO_AT[side],
                       bake(w + 2 * m, h + 2 * m, 1, (region[0] - m, region[1] - m), flyout_halo_value(side)), m))
    return canvas_with(FLY_HALO_CANVAS, FLY_HALO_CANVAS, pieces)


# ---------------------------------------------------------------- output

def write_tga(path, grid):
    height, width = len(grid), len(grid[0])
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    rows = bytearray()
    for row in grid:
        for v in row:
            rows += bytes((255, 255, 255, max(0, min(255, int(round(v * 255))))))
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    shape = chev_shape()
    haze = chev_haze()
    outputs = [
        ("totem_piece_fill", piece_fill),
        ("totem_piece_scan", piece_scan),
        ("totem_piece_glow", piece_glow),
        ("totem_piece_edge", piece_edge),
        ("totem_chev_body", lambda: shape),
        ("totem_chev_pink", lambda: ramp(shape)),
        ("totem_chev_haze", lambda: haze),
        ("totem_chev_haze_pink", lambda: ramp(haze)),
        ("totem_chev_core", chev_core),
        ("totem_bump_stroke", build_bump_stroke),
        ("totem_bump_halo", build_bump_halo),
        ("totem_flyout_halo", build_flyout_halo),
    ]
    for name, make in outputs:
        write_tga(os.path.join(here, name + ".tga"), make())


if __name__ == "__main__":
    main()
