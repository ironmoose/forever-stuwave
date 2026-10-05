#!/usr/bin/env python3
"""Generates the CUT-CORNER (chamfered) chrome pieces that replace the rounded set.

Decision (Parker, 2026-10-02): chamfered cut corners are the default chrome
everywhere and rounded is retired. EVERY rectangle or square is two-corner (2C:
TOP-LEFT + BOTTOM-RIGHT cut, TOP-RIGHT + BOTTOM-LEFT square), panels, bars and
tooltips included; there is no four-corner chrome (the older four-corner
slice_cut_outline/fill stay on disk until the rounded retirement). Chamfer set
C = {2, 3, 4, 6} texels; each size is its own baked file because a nine-slice
corner is drawn at native texels and never rescales. Inventory and lane plan:
notes/cut-corners-inventory-2026-10-02.md.

Composed pieces (16x16 canvas, drawn at NATIVE texels in the top-left, so the
caller samples SetTexCoord(0, c/16, 0, c/16) and one texel stays one texel; a 64
texel triangle scaled down to 3-6 px aliases). The canvas keeps going as the plate
the piece is the TOP-LEFT corner of, so bilinear filtering at the region edge
reads the straight run, not a transparent border. Callers place a piece only at
the plate's TOP-LEFT and BOTTOM-RIGHT corners; the bottom-right one is the same
file with the texcoords flipped both ways (SetTexCoord(c/16, 0, c/16, 0)), so one
file per chamfer is enough.

    fill_cut_c{c}          solid triangle, opaque where x + y >= c (AddRoundedFill,
                           AddPillCaps)
    anti_cut_c{c}          erase triangle, opaque where x + y < c - 0.586, the
                           fractional leg baked by supersampling (AddCornerMask et
                           al: leg = c - inset * (2 - sqrt 2), inset 1)
    anti_cut_br_c{c}       the same triangle flipped into the BOTTOM-RIGHT of the canvas
                           (opaque where (16 - x) + (16 - y) < c - 0.586): a StatusBar
                           fill shows its file unflipped, so the nameplate's gated
                           mid-plate wedge (Theme.AddGatedCutCorner) needs it baked
    border_cut_c{c}_t{t}   diagonal stroke (AddGradientBorder), t=1 for every c,
                           t=2 only for c=6 (UnitFrames BORDER_THICK 2). The
                           stroke is t wide PERPENDICULAR to the cut, like the
                           straight runs, and the inner cut is clamped to the
                           chamfer square so it never leaks into the rail that
                           starts at x = c (no ghost line along the straight edge)
    glow_corner_cut        32x32 halo for the cut corner (AddOuterGlow), ONE baked
                           at chamfer:glow = 6:8 and stretched whole, the way
                           glow_corner_round is reused at other ratios today. The
                           texture is the 14 px box [-8, 6]^2 around the plate
                           corner: peak on the cut line, quadratic fade out to 8 px,
                           hollow inside, same profile as glow_edge strips

Nine-slice sets (32x32; SetTextureSliceMargins margin = the baked chamfer, glow
margin = GLOW_PAD + chamfer, same rule as slice_glow / slice_cut2_glow):

    slice_cut2_border_c{c}                             1.0 stroke, c in {2,3,4,6}: the
                                                       panel/tooltip/plate border
    slice_cut2_{outline,glow,button,fill}_c{c}         c in {2,3,4} only (c=6 is
                                                       generate_cut_corner_outline.py's
                                                       slice_cut2_*, which must stay
                                                       byte-identical; its outline is the
                                                       older unclamped stroke, so panels
                                                       use slice_cut2_border_c6)

slice_cut2_outline_c{c} and slice_cut2_border_c{c} are the same 1.0 stroke for
c in {2,3,4} (two names so callers can say which job they mean).

Fill erase for a nine-sliced stroke (32x32, margin c, white RGB, shape in alpha; tinted an
opaque colour at runtime; c in {4, 6}):

    slice_cut2_erase_c{c}   an opaque wedge in the TOP-LEFT and BOTTOM-RIGHT corner
                            slices and nothing else (edges and centre empty). c6 is the
                            nameplate's (stroke slice_cut2_border_c6), c4 the party pet
                            column's (stroke slice_cut2_outline_c4)

The plate stroke (slice_cut2_border_c6) is a nine-slice over the plate ROOT, so the engine
decides how many screen pixels one slice texel is, and that is NOT the plate's unit: erase
quads sized in plate units (anti_cut_c*) drifted off the stroke's diagonal at every scale
but one (live 2026-10-04, a dark triangle between the diagonal and the fill). This erase is
a nine-slice of the same margin laid over the same ROOT rect (Theme.AddCutFillErase), so the
engine draws its corner cells at the stroke's own scale: the wedge's cut line x + y =
erase_hypotenuse(c) sits the same fraction of a stroke width from the stroke's diagonal at every
plate scale, whatever the bar inset. (A first version laid it over the BAR rect, inset one
plate unit from the root; that is delta = unit_px / texel_px texels and only matched the
stroke for delta 1.0 .. 1.9, so a stacked plate-scale CVar brought the triangle back.)

Every nine-slice is checked by the tests for the contract that makes it
stretchable: the edge and centre slices are constant along their stretch
direction, so nothing of a corner smears across an edge.

Pure stdlib, same TGA format as every other generator here. Output: 18-byte
header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python3 generate_cut_pieces.py
"""

import math
import os
import struct

CHAMFERS = (2, 3, 4, 6)
CUT2_EXTRA_CHAMFERS = (2, 3, 4)     # c=6 lives in generate_cut_corner_outline.py

PIECE_SIZE = 16
SLICE_SIZE = 32
GLOW_CORNER_SIZE = 32

# Antialiasing subpixel grids (NxN samples per texel). Powers of two, so mirrored
# samples are exact in floating point and every file is symmetric where the shape is.
SS_PIECE = 16
SS_SLICE = 8

# Same stroke the action buttons use (generate_cut_corner_outline.THICKNESS_CUT2).
STROKE = 1.0
# A 45 degree stroke needs this much less inner chamfer per unit of thickness to stay
# the same width perpendicular to the cut as on the straight runs.
DIAG = 2.0 - math.sqrt(2.0)
# Pad of the nine-slice glow (Theme.SLICE_CUT2_GLOW_PAD): glow margin = pad + chamfer.
GLOW_PAD = 4

# glow_corner_cut: chamfer and halo reach it is baked for (ratio 6:8, like
# glow_corner_round's RADIUS_PX / GLOW_SIZE).
GLOW_CORNER_CHAMFER = 6
GLOW_CORNER_REACH = 8

CUT2_CORNERS = ("tl", "br")
TL_ONLY = ("tl",)

# Action-button background, kept in step by hand with generate_cut_corner_outline.py
# (the generators are standalone scripts and cannot import each other).
GRAD_TOP = (0x24, 0x16, 0x40)
GRAD_BOTTOM = (0x16, 0x0c, 0x2b)

# Erase wedge hypotenuse, in texels from the stroked rect's corner (cut line x + y = H). For a
# chamfer c the 1.0 thick stroke band from that corner is c (outer cut line) to c + sqrt 2 (inner
# edge); c = 6 is 6.0 to 7.414. The supported window for H is that band: at or past c nothing of
# the fill shows outside the violet line, at or before c + sqrt 2 the wedge never reaches past the
# stroke's inner edge, so no dark sliver shows between stroke and fill. H sits ERASE_INNER_MARGIN
# texel (0.164, about 0.13 px) inside the inner edge, so the stroke's own antialiased inner edge
# lies over the wedge, not over a gap. c6 lands on 7.25 and c4 on 5.25 (H = c + 1.25).
ERASE_INNER_MARGIN = 0.1642
ERASE_CHAMFERS = (4, 6)


def erase_hypotenuse(c):
    """c + 1.25: the 1.0 stroke's inner edge (c + sqrt 2) less ERASE_INNER_MARGIN, to the
    nearest hundredth so c = 6 stays the 7.25 the committed nameplate file was baked with."""
    return round(c + 2.0 ** 0.5 - ERASE_INNER_MARGIN, 2)


HUGE = 1.0e6   # "the plate keeps going": far enough that no other edge is in the canvas


def _inside(px, py, x0, y0, x1, y1, chamfer, corners, reach=None):
    """True if (px,py) is inside the chamfered rect [x0,x1] x [y0,y1].

    `reach` limits each cut to the chamfer square (local coords below reach), which is
    what keeps an INNER stroke edge from continuing past the baked chamfer."""
    if px < x0 or px > x1 or py < y0 or py > y1:
        return False
    for corner in corners:
        lu = (px - x0) if corner in ("tl", "bl") else (x1 - px)
        lv = (py - y0) if corner in ("tl", "tr") else (y1 - py)
        if lu + lv < chamfer and (reach is None or (lu < reach and lv < reach)):
            return False
    return True


# A sample lying exactly on a 45 degree edge (integer chamfer, symmetric sample grid:
# a texel-diagonal always has them) must count half, not whole, or every edge texel is
# biased towards one side. Each sample is tested nudged by +/- TIE_NUDGE along (1,1) and
# the two answers averaged: a tie splits 0.5 / 0.5, a clear inside or outside agrees.
TIE_NUDGE = 1.0e-7


def _coverage(x, y, ss, inside):
    hits = 0
    for sy in range(ss):
        for sx in range(ss):
            px = x + (sx + 0.5) / ss
            py = y + (sy + 0.5) / ss
            hits += inside(px + TIE_NUDGE, py + TIE_NUDGE) + inside(px - TIE_NUDGE, py - TIE_NUDGE)
    return hits / (2 * ss * ss)


def _write(path, pixels, size):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({size}x{size}, {os.path.getsize(path)} bytes)")


def _white(alpha):
    return bytes((255, 255, 255, int(round(alpha * 255))))


# ---------------------------------------------------------------------------
# Composed pieces (16x16, TOP-LEFT orientation)
# ---------------------------------------------------------------------------

def build_fill_piece(c):
    """Opaque where x + y >= c: the plate's top-left cut corner."""
    rows = bytearray()
    for y in range(PIECE_SIZE):
        for x in range(PIECE_SIZE):
            rows += _white(_coverage(
                x, y, SS_PIECE,
                lambda px, py: _inside(px, py, 0, 0, HUGE, HUGE, c, TL_ONLY)))
    return bytes(rows)


def build_anti_piece(c):
    """Opaque where x + y < c - 0.586: erases a fill's square corner, leaving the
    inset (inset 1) cut. The fractional leg is baked by supersampling."""
    leg = c - DIAG
    rows = bytearray()
    for y in range(PIECE_SIZE):
        for x in range(PIECE_SIZE):
            rows += _white(_coverage(x, y, SS_PIECE, lambda px, py: px + py < leg))
    return bytes(rows)


def _stroke_inside_fns(c, t, x1, y1, corners):
    inner_c = max(c - t * DIAG, 0.0)

    def outer(px, py):
        return _inside(px, py, 0, 0, x1, y1, c, corners)

    def inner(px, py):
        return _inside(px, py, t, t, x1 - t, y1 - t, inner_c, corners, reach=c - t)

    return outer, inner


def _stroke_alpha(x, y, ss, outer, inner):
    return max(_coverage(x, y, ss, outer) - _coverage(x, y, ss, inner), 0.0)


def build_border_piece(c, t):
    """Diagonal stroke of the top-left corner; the straight strokes carry on to the
    canvas edge along the top and the left."""
    outer, inner = _stroke_inside_fns(c, t, HUGE, HUGE, TL_ONLY)
    rows = bytearray()
    for y in range(PIECE_SIZE):
        for x in range(PIECE_SIZE):
            rows += _white(_stroke_alpha(x, y, SS_PIECE, outer, inner))
    return bytes(rows)


# ---------------------------------------------------------------------------
# Corner glow (32x32, TOP-LEFT orientation, 6:8)
# ---------------------------------------------------------------------------

def _polygon(x0, y0, x1, y1, chamfer, corners):
    """Vertices (clockwise from the top-left, y down) of the chamfered rect."""
    pts = []
    for corner, (cx, cy) in (
            ("tl", (x0, y0)), ("tr", (x1, y0)), ("br", (x1, y1)), ("bl", (x0, y1))):
        if corner not in corners:
            pts.append((cx, cy))
        elif corner == "tl":
            pts += [(cx, cy + chamfer), (cx + chamfer, cy)]
        elif corner == "tr":
            pts += [(cx - chamfer, cy), (cx, cy + chamfer)]
        elif corner == "br":
            pts += [(cx, cy - chamfer), (cx - chamfer, cy)]
        else:
            pts += [(cx + chamfer, cy), (cx, cy - chamfer)]
    return pts


def _distance_outside(px, py, pts):
    """Distance from (px,py) to a convex polygon; 0 when inside it."""
    n = len(pts)
    inside = True
    best = float("inf")
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        # Clockwise winding in a y-down raster: the interior is where the cross
        # product is >= 0 for every edge.
        if ex * (py - ay) - ey * (px - ax) < 0:
            inside = False
        t = ((px - ax) * ex + (py - ay) * ey) / (ex * ex + ey * ey)
        t = min(max(t, 0.0), 1.0)
        best = min(best, math.hypot(px - (ax + t * ex), py - (ay + t * ey)))
    return 0.0 if inside else best


def build_glow_corner():
    """Halo of a top-left cut corner. Panel coordinates have the panel corner at
    (0,0) and the plate to the lower right; the texture is the box
    [-reach, chamfer]^2 stretched onto GLOW_CORNER_SIZE texels. Alpha is the same
    quadratic fade the straight glow_edge strips use (1 on the border, 0 at `reach`
    px out), measured from the CUT, and 0 inside the plate."""
    c, g = GLOW_CORNER_CHAMFER, GLOW_CORNER_REACH
    scale = GLOW_CORNER_SIZE / (c + g)
    pts = [(0, c), (c, 0), (HUGE, 0), (HUGE, HUGE), (0, HUGE)]
    rows = bytearray()
    for y in range(GLOW_CORNER_SIZE):
        for x in range(GLOW_CORNER_SIZE):
            d = _distance_outside((x + 0.5) / scale - g, (y + 0.5) / scale - g, pts)
            alpha = 0.0 if d <= 0 or d >= g else (1.0 - d / g) ** 2
            rows += _white(alpha)
    return bytes(rows)


# ---------------------------------------------------------------------------
# Nine-slice sets (32x32)
# ---------------------------------------------------------------------------

def _gradient(y):
    t = y / (SLICE_SIZE - 1)
    return tuple(int(round(GRAD_TOP[i] + (GRAD_BOTTOM[i] - GRAD_TOP[i]) * t)) for i in range(3))


def build_slice_fill(c, corners, gradient=False):
    """Solid chamfered plate. White, or (gradient) the action-button gradient baked
    into RGB (see generate_slice_chrome.py on why a nine-slice gradient is baked)."""

    def inside(px, py):
        return _inside(px, py, 0, 0, SLICE_SIZE, SLICE_SIZE, c, corners)

    rows = bytearray()
    for y in range(SLICE_SIZE):
        r, g, b = _gradient(y) if gradient else (255, 255, 255)
        for x in range(SLICE_SIZE):
            rows += bytes((b, g, r, int(round(_coverage(x, y, SS_SLICE, inside) * 255))))
    return bytes(rows)


def build_anti_piece_br(c):
    """anti_cut_c{c} flipped both ways: opaque where (16 - x) + (16 - y) < c - 0.586."""
    leg = c - DIAG
    rows = bytearray()
    for y in range(PIECE_SIZE):
        for x in range(PIECE_SIZE):
            rows += _white(_coverage(
                x, y, SS_PIECE, lambda px, py: (PIECE_SIZE - px) + (PIECE_SIZE - py) < leg))
    return bytes(rows)


def build_slice_outline(c, corners, t=STROKE):
    outer, inner = _stroke_inside_fns(c, t, SLICE_SIZE, SLICE_SIZE, corners)
    rows = bytearray()
    for y in range(SLICE_SIZE):
        for x in range(SLICE_SIZE):
            rows += _white(_stroke_alpha(x, y, SS_SLICE, outer, inner))
    return bytes(rows)


def build_slice_glow(c, corners):
    """Outer glow of the chamfered plate, same idiom as slice_cut2_glow: the plate
    inset by GLOW_PAD from the texture edge, alpha falling off outward over GLOW_PAD
    texels (quadratic) and HOLLOW inside, because the glow is ADD-blended above the
    content."""
    pts = _polygon(GLOW_PAD, GLOW_PAD, SLICE_SIZE - GLOW_PAD, SLICE_SIZE - GLOW_PAD, c, corners)
    rows = bytearray()
    for y in range(SLICE_SIZE):
        for x in range(SLICE_SIZE):
            d = _distance_outside(x + 0.5, y + 0.5, pts)
            alpha = 0.0 if d <= 0 or d >= GLOW_PAD else (1.0 - d / GLOW_PAD) ** 2
            rows += _white(alpha)
    return bytes(rows)


def build_slice_erase(c=6):
    """Fill erase of a nine-sliced chamfer-c stroke: an opaque wedge (x + y < H) in the TOP-LEFT
    corner slice (margin c) and its mirror in the BOTTOM-RIGHT one; everything else clear."""
    h = erase_hypotenuse(c)

    def inside(px, py):
        return px + py < h or (SLICE_SIZE - px) + (SLICE_SIZE - py) < h

    rows = bytearray()
    for y in range(SLICE_SIZE):
        for x in range(SLICE_SIZE):
            in_corner = ((x < c and y < c)
                         or (x >= SLICE_SIZE - c and y >= SLICE_SIZE - c))
            rows += _white(_coverage(x, y, SS_SLICE, inside) if in_corner else 0.0)
    return bytes(rows)


def main():
    here = os.path.dirname(os.path.abspath(__file__))

    def out(name, pixels, size):
        _write(os.path.join(here, f"{name}.tga"), pixels, size)

    for c in CHAMFERS:
        out(f"fill_cut_c{c}", build_fill_piece(c), PIECE_SIZE)
        out(f"anti_cut_c{c}", build_anti_piece(c), PIECE_SIZE)
        out(f"anti_cut_br_c{c}", build_anti_piece_br(c), PIECE_SIZE)
        out(f"border_cut_c{c}_t1", build_border_piece(c, 1), PIECE_SIZE)
    out("border_cut_c6_t2", build_border_piece(6, 2), PIECE_SIZE)
    out("glow_corner_cut", build_glow_corner(), GLOW_CORNER_SIZE)

    for c in CHAMFERS:
        out(f"slice_cut2_border_c{c}", build_slice_outline(c, CUT2_CORNERS), SLICE_SIZE)

    for c in ERASE_CHAMFERS:
        out(f"slice_cut2_erase_c{c}", build_slice_erase(c), SLICE_SIZE)

    for c in CUT2_EXTRA_CHAMFERS:
        out(f"slice_cut2_outline_c{c}", build_slice_outline(c, CUT2_CORNERS), SLICE_SIZE)
        out(f"slice_cut2_glow_c{c}", build_slice_glow(c, CUT2_CORNERS), SLICE_SIZE)
        out(f"slice_cut2_button_c{c}", build_slice_fill(c, CUT2_CORNERS, gradient=True), SLICE_SIZE)
        out(f"slice_cut2_fill_c{c}", build_slice_fill(c, CUT2_CORNERS), SLICE_SIZE)


if __name__ == "__main__":
    main()
