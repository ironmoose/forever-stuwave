#!/usr/bin/env python3
"""Generates the Console panel chrome of the Gunsight HUD: a cut-14 chassis nine-slice
set and the 45 degree foot of the stepped shoulder tab.

Reference: mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html,
"Console panel style": cnTrace(tab) draws the chassis outline (cut CN_CUT = 14 at
the TOP-LEFT and BOTTOM-RIGHT corners, TOP-RIGHT and BOTTOM-LEFT square) plus the
stepped shoulder; cnBake() fills it, throws the halo OUTSIDE the outline only and
strokes a rail on it. Design px (the mockup's image px x 1.28).

Nothing else in media/ fits, so these are new:

    console_fill_c14.tga     64x64   solid chamfered plate, cut 14, white. Nine-slice,
                                     slice margin 14. The chassis gradient (the
                                     Deck fill, rgba(45,27,78,.8) down to
                                     rgba(11,6,20,.88)) is a vertical gradient over
                                     the whole chassis, which a nine-slice would
                                     stretch, so it is NOT baked: set it in Lua with
                                     SetGradient on this texture.
    console_outline_c14.tga  64x64   the 1 texel rail on the same shape (hollow).
                                     Nine-slice, margin 14, the same canvas as the
                                     fill so the two stack. The mockup rail is 1.15
                                     design px; it is a whole texel here, like
                                     slice_cut2_outline, so it stays crisp at scale 1.
    console_glow_c14.tga     64x64   the halo OUTSIDE the outline, hollow inside.
                                     Nine-slice, margin = GLOW_PAD + 14 = 25. The
                                     outline polygon sits GLOW_PAD = 11 texels in from
                                     the canvas edge, so the frame is the chassis
                                     outset by 11 on every side, and the halo follows
                                     the 14 cut on the TOP-LEFT and BOTTOM-RIGHT.
    console_tab_foot.tga     128x128 the slanted left foot of the stepped shoulder tab,
                                     the rail line and its outside halo on the 45
                                     degree diagonal. See below.

Existing pieces that DO NOT fit and why: slice_cut2_{outline,fill,glow} are chamfer
6, and generate_cut_pieces.py only bakes chamfers 2, 3, 4 and 6; a nine-slice margin
is the baked chamfer, so a 6 set cannot draw a 14 cut. deck_shoulder.tga is 32x64 for
the deck's 18 x 38 shoulder (63 degrees), not 45. tab_slant.tga IS reused for the
tab foot's FILL (it is a 32x32 wedge, "/" lean, solid lower right, which stretched
onto a square is exactly 45 degrees), so no fill wedge is generated here.

HALO. cnBake calls glow(violet, CN_GK = 1.7) then halo(true): four strokes of the
outline, each lineWidth 0.9 + 2 w wide with alpha a x 1.7 x .7 (the .7 is the
A(.7) set just before), (w, a) = (1.5, .26) (3.2, .17) (5, .10) (7, .055) in image
px, clipped to the OUTSIDE of the outline. Outside the path the layers composite
over each other, so the alpha at distance d from the outline is
1 - prod(1 - alpha_i) over the layers whose reach (w + 0.45) x 1.28 design px is at
least d: reaches 2.5, 4.67, 6.98, 9.54, a stepped halo (that is the approved look,
not an approximation). The .7 is baked in, so an alpha of 1 in Lua reproduces the
mockup; tint it violet. The glow reaches 9.54 texels, so GLOW_PAD 11 leaves a clear
texel or more before the canvas edge and a nine-slice shows no cutoff.

TAB FOOT. The tab is CN_TH = 39.2 design px tall (DK.H - CN_KB + CN_TP, see the
mockup), its left foot standing on the chassis top line and rising 45 degrees to
the tab's top edge, which then runs right to the chassis right edge. The foot
texture covers 59.2 x 50.2 design units: the 39.2 square of the foot, 10 of halo
room to the left, FOOT_TOP = 11 above (the glow strip's 10.5 reach past a stroke's
outer edge), and a 10 unit stub of the top edge to the right so the halo wraps the
corner and carries on along the top. Its polygon is (10, 50.2) (49.2, 11) (59.2, 11)
(59.2, 50.2): the diagonal, the stub, and the tab interior below them. The texture
holds the rail line (white alpha 1; the diagonal 1.15 wide, the stub 1.0 like
lineTabTop) and the halo outside it. NOTHING inside the tab. The straight runs (the
chassis top line, running off the left edge, and the stub) carry console_glow_c14's
own per-texel strip profile from their outer edge, so the strips that end at this
texture's left edge and start at its right edge join with no step; the top strip must
END where this texture begins, or the two composite into a brighter lobe at the
concave corner.
In Lua: size it 59.2 x 50.2 design units and seat its TOPLEFT at (foot x - 10, chassis
top - 50.2 + 0.5), so the texture's (10, 50.2) corner is the foot standing on the chassis
top line.
The canvas is stretched, not square, so it is rasterised in
design units (as generate_hud_key_ring.py does): a texel is 0.46 x 0.39 units and
the stroke and the 45 degree line come out true after the stretch. For the halo
along the straight top and right edges, sample a one dimensional strip from the
middle of console_glow_c14 with SetTexCoord (it does not vary along its edge).

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python3 generate_console_chrome.py
"""

import math
import os
import struct

SIZE = 64
CHAMFER = 14.0
STROKE = 1.0                 # outline thickness, texels
GLOW_PAD = 11                # texels between the canvas edge and the outline polygon
SUPERSAMPLE = 4

# cnBake's halo, converted to design px. HALO is [stroke half width extra, alpha] in image px.
HALO = [(1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055)]
CORE_HALF_IMAGE = 0.45       # half of the 0.9 core stroke, image px
IMAGE_TO_DESIGN = 1.28
GLOW_GAIN = 1.7              # CN_GK
OVERALL_ALPHA = 0.7          # A(.7) in front of halo(true)
REACHES = [((w + CORE_HALF_IMAGE) * IMAGE_TO_DESIGN, min(1.0, a * GLOW_GAIN * OVERALL_ALPHA))
           for w, a in HALO]

# Tab foot, design units (CN_TH = 39.2, 10 of halo room left and 11 above, 10 stub right).
FOOT_SIZE = 128
FOOT_TH = 39.2
FOOT_PAD = 10.0
FOOT_TOP = 11.0              # room above the stub's centreline: the strip's 10.5 reach past the stroke's edge
FOOT_W = FOOT_PAD + FOOT_TH + FOOT_PAD
FOOT_H = FOOT_TOP + FOOT_TH
CORE_HALF = CORE_HALF_IMAGE * IMAGE_TO_DESIGN   # 0.576
FOOT_SEAM = 0.5              # the texture ends half way down the 1 texel chassis top line (Console.lua SEAM)


def halo_alpha(dist):
    """Alpha of the stepped, composited halo at `dist` outside the outline."""
    keep = 1.0
    for reach, alpha in REACHES:
        if dist <= reach:
            keep *= 1.0 - alpha
    return 1.0 - keep


def chamfer_polygon(x0, y0, x1, y1, c):
    """Clockwise from the TOP-LEFT cut; TOP-LEFT and BOTTOM-RIGHT cut."""
    return [(x0, y0 + c), (x0 + c, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0, y1)]


def convex_inside(poly, px, py):
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        if (bx - ax) * (py - ay) - (by - ay) * (px - ax) < 0:
            return False
    return True


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def poly_dist(px, py, pts, closed=True):
    n = len(pts) if closed else len(pts) - 1
    return min(seg_dist(px, py, pts[i], pts[(i + 1) % len(pts)]) for i in range(n))


def poly_inside(px, py, pts):
    c = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def supersample(width, height, fn, to_design):
    """Mean of fn(design x, design y) over SUPERSAMPLE^2 points per texel."""
    n = SUPERSAMPLE * SUPERSAMPLE
    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    total += fn(*to_design(x + (sx + 0.5) / SUPERSAMPLE,
                                           y + (sy + 0.5) / SUPERSAMPLE))
            row.append(total / n)
        grid.append(row)
    return grid


def _identity(x, y):
    return x, y


def build_fill():
    poly = chamfer_polygon(0.0, 0.0, float(SIZE), float(SIZE), CHAMFER)
    return supersample(SIZE, SIZE, lambda x, y: 1.0 if convex_inside(poly, x, y) else 0.0,
                       _identity)


def build_outline():
    outer = chamfer_polygon(0.0, 0.0, float(SIZE), float(SIZE), CHAMFER)
    # The inset shape keeps the stroke as thick on the diagonal as on the straight runs.
    inner = chamfer_polygon(STROKE, STROKE, SIZE - STROKE, SIZE - STROKE,
                            CHAMFER - STROKE * (2.0 - math.sqrt(2.0)))

    def fn(x, y):
        return 1.0 if convex_inside(outer, x, y) and not convex_inside(inner, x, y) else 0.0

    return supersample(SIZE, SIZE, fn, _identity)


def build_glow():
    lo, hi = float(GLOW_PAD), float(SIZE - GLOW_PAD)
    poly = chamfer_polygon(lo, lo, hi, hi, CHAMFER)

    def fn(x, y):
        if convex_inside(poly, x, y):
            return 0.0
        return halo_alpha(poly_dist(x, y, poly))

    return supersample(SIZE, SIZE, fn, _identity)


def glow_strip_profile():
    """Per-texel alpha of console_glow_c14's straight top strip, as 8 bit values, outermost row first."""
    grid = build_glow()
    return [round(grid[row][SIZE // 2] * 255) / 255 for row in range(GLOW_PAD)]


def strip_alpha(profile, dist):
    """The strip as the engine draws it at 1:1: linear between texel centres, `dist` outside the outer edge."""
    pos = GLOW_PAD - 0.5 - dist          # texel-centre coordinate: texel r is centred on r
    if pos <= 0.0:
        return profile[0]
    if pos >= GLOW_PAD - 1:
        return profile[-1]
    lo = int(pos)
    return profile[lo] + (profile[lo + 1] - profile[lo]) * (pos - lo)


def build_tab_foot():
    line = [(FOOT_PAD, FOOT_H), (FOOT_PAD + FOOT_TH, FOOT_TOP), (FOOT_W, FOOT_TOP)]
    tab = line + [(FOOT_W, FOOT_H)]
    # The straight runs (the chassis top line, running off the left edge, and the stub) carry the
    # Console glow strip's own per-texel profile, measured from their outer edge, so the strip pieces
    # that end at the foot's left edge and start at its right edge join with no step.
    profile = glow_strip_profile()
    edge_y = FOOT_H - FOOT_SEAM
    stub_y = FOOT_TOP - 0.5 * STROKE
    top = [(-FOOT_PAD * 10.0, edge_y), (FOOT_PAD, edge_y)]
    stub = [(FOOT_PAD + FOOT_TH, stub_y), (FOOT_W, stub_y)]

    def to_design(x, y):
        return x * FOOT_W / FOOT_SIZE, y * FOOT_H / FOOT_SIZE

    def fn(x, y):
        dist = poly_dist(x, y, line[:2], closed=False)
        # the stub's core is lineTabTop's own 1 unit stroke; the diagonal keeps the mockup's core
        if dist <= CORE_HALF or seg_dist(x, y, line[1], line[2]) <= 0.5 * STROKE:
            return 1.0
        if poly_inside(x, y, tab):
            return 0.0
        return max(halo_alpha(dist),
                   strip_alpha(profile, poly_dist(x, y, top, closed=False)),
                   strip_alpha(profile, poly_dist(x, y, stub, closed=False)))

    return supersample(FOOT_SIZE, FOOT_SIZE, fn, to_design)


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
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    write_tga(os.path.join(here, "console_fill_c14.tga"), build_fill())
    write_tga(os.path.join(here, "console_outline_c14.tga"), build_outline())
    write_tga(os.path.join(here, "console_glow_c14.tga"), build_glow())
    write_tga(os.path.join(here, "console_tab_foot.tga"), build_tab_foot())


if __name__ == "__main__":
    main()
