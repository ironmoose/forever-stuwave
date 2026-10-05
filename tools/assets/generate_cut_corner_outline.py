#!/usr/bin/env python3
"""Generates the CUT-CORNER (chamfered) outline chrome texture: slice_cut_outline.

Companion to generate_slice_chrome.py's nine-slice ring (slice_border.tga), but
the corner shape is a straight 45-degree cut instead of an arc. This is the
"outline / cut corners" chrome primitive from the locked pet-container design:
a thin cyan stroke, hollow interior, no fill, no corner brackets, no
drag-handle dashes. slice_cut_fill is its solid companion (same outer shape).

Corner sets. The four-corner pair above (slice_cut_outline / slice_cut_fill) cuts
every corner and is the BagBar keycap shape. The action, pet and stance bar
buttons use the locked pet-slot design instead: only the TOP-LEFT and
BOTTOM-RIGHT corners are chamfered, TOP-RIGHT and BOTTOM-LEFT stay square. That
set ("cut2") is generated here too, from the same CHAMFER, as:

    slice_cut2_outline   thin stroke, hollow (THICKNESS_CUT2 wide)
    slice_cut2_fill      solid white, for tinted washes (ADD-blend hover wash)
    slice_cut2_button    the same shape with the action-button #241640 ->
                         #160c2b gradient baked into RGB (see slice_chrome note
                         on why a gradient must be baked into a nine-slice)
    slice_cut2_glow      outer glow, hollow inside, same GLOW_PAD / margin idiom
                         as slice_glow (Theme.SLICE_CUT2_GLOW_*)
    mask_cut2_square     64x64 alpha mask for icons and the cooldown swipe
                         (solid white RGB, shape in alpha, like mask_minimap.tga)
                         (unused while MaskTexture does not clip on the client)

The four-corner outputs are byte-identical to what they were before cut2 existed.

Same nine-slice idiom, same TGA format as generate_slice_chrome.py -- see that
file's module docstring for the full rationale on why nine-slicing exists at
all (rail/arc seam at small sizes) and why the coverage test is supersampled
rather than analytic (a straight diagonal edge through a low-res raster still
aliases without it, exactly like the rounded arc does).

SIZE/CHAMFER/margin contract: the margin passed to SetTextureSliceMargins must
equal CHAMFER, so the corner slice contains exactly the cut and the edge
slices contain only straight runs. Theme.lua reads CHAMFER back as
Theme.SLICE_CUT_MARGIN; change it here and there together.

Pure stdlib, like every other generator in this directory. Output: 18-byte
header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_cut_corner_outline.py
"""

import math
import os
import struct

SIZE = 32
# Chamfer (45-degree corner cut) size, in texels. MUST match
# Theme.SLICE_CUT_MARGIN -- change the two together. Starting guess pending
# Parker's eyeball against the Pet Frame Designer artifact.
CHAMFER = 6.0
# Outline stroke width, in texels. Starting guess pending Parker's eyeball
# against the Pet Frame Designer artifact.
THICKNESS = 1.5
# Antialiasing subpixel grid (NxN samples per texel). Starting guess pending
# Parker's eyeball against the Pet Frame Designer artifact.
SUPERSAMPLE = 6

# Corner sets: which corners of the plate get the 45-degree cut.
ALL_CORNERS = ("tl", "tr", "bl", "br")
CUT2_CORNERS = ("tl", "br")

# cut2 stroke width, in texels. The action buttons' rounded border is 1 texel
# (generate_slice_chrome.py THICKNESS), so cut2 matches that rather than the
# 1.5 texel stroke the four-corner BagBar outline uses.
THICKNESS_CUT2 = 1.0

# Slice margin of the cut2 glow is GLOW_PAD + CHAMFER (the corner slice has to
# hold the chamfer AND its halo), same rule as slice_glow. MUST match
# Theme.SLICE_CUT2_GLOW_PAD and Theme.SLICE_CUT2_GLOW_MARGIN.
GLOW_PAD = 4

# mask_cut2_square: a mask stretches with whatever it clips, so its chamfer is a
# FRACTION of the texture, not a texel count. 0.15 of a ~35px action icon is
# ~5 texels, i.e. the inside edge of the button's 6 texel chamfer minus the 1
# texel icon inset and border. Retune if the button size or CHAMFER changes.
MASK_SIZE = 64
MASK_CHAMFER_FRACTION = 0.15

# Action-button background, same gradient as generate_slice_chrome.py (kept in
# step by hand: the generators are standalone scripts and cannot import each
# other).
GRAD_TOP = (0x24, 0x16, 0x40)
GRAD_BOTTOM = (0x16, 0x0c, 0x2b)


def _chamfer_coverage(x, y, x0, y0, x1, y1, chamfer, corners=ALL_CORNERS):
    """Fraction of pixel (x,y) inside the chamfered rect [x0,x1] x [y0,y1].

    A supersampled point is inside the chamfered rect iff it's inside the
    plain rect AND clears every diagonal cut named in `corners`. Supersampled rather than
    analytic for the same reason generate_slice_chrome.py's
    _rounded_coverage is: a 45-degree line through a low-res raster still
    aliases without it, straight edge or not.
    """
    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            py = y + (sy + 0.5) / SUPERSAMPLE

            if px < x0 or px > x1 or py < y0 or py > y1:
                continue

            if "tl" in corners and (px - x0) + (py - y0) < chamfer:
                continue
            if "tr" in corners and (x1 - px) + (py - y0) < chamfer:
                continue
            if "bl" in corners and (px - x0) + (y1 - py) < chamfer:
                continue
            if "br" in corners and (x1 - px) + (y1 - py) < chamfer:
                continue

            hits += 1

    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def _write(path, pixels, size=SIZE):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({size}x{size}, {os.path.getsize(path)} bytes)")


def build_outline(corners=ALL_CORNERS, thickness=THICKNESS, inner_chamfer=None):
    """Chamfered-rect outline: outer chamfered coverage minus the same shape
    inset by `thickness`. Subtracting coverages (not shapes) keeps the
    antialiasing on both edges of the ring, same technique as
    generate_slice_chrome.py's build_border().

    `inner_chamfer` defaults to CHAMFER - thickness (the original four-corner
    formula, kept so those outputs do not change). A 45-degree edge needs
    CHAMFER - thickness * (2 - sqrt(2)) to keep the stroke the same width on the
    diagonal as on the straight runs; build_cut2 passes that."""
    if inner_chamfer is None:
        inner_chamfer = max(CHAMFER - thickness, 0.0)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            outer = _chamfer_coverage(x, y, 0, 0, SIZE, SIZE, CHAMFER, corners)

            inner = _chamfer_coverage(
                x, y,
                thickness, thickness, SIZE - thickness, SIZE - thickness,
                inner_chamfer, corners)

            alpha = int(round(max(outer - inner, 0.0) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def build_fill(corners=ALL_CORNERS, colour_at=None):
    """Solid chamfered rect: full coverage inside the same outer shape the
    outline uses, antialiased on the edge the same way. Flush under the
    outline's outer edge, so a tinted fill leaves no gap inside the stroke.
    White unless `colour_at(y)` bakes a vertical gradient into RGB."""
    rows = bytearray()
    for y in range(SIZE):
        r, g, b = colour_at(y) if colour_at else (255, 255, 255)
        for x in range(SIZE):
            outer = _chamfer_coverage(x, y, 0, 0, SIZE, SIZE, CHAMFER, corners)
            rows += bytes((b, g, r, int(round(outer * 255))))
    return bytes(rows)


def _gradient(y):
    t = y / (SIZE - 1)
    return tuple(
        int(round(GRAD_TOP[i] + (GRAD_BOTTOM[i] - GRAD_TOP[i]) * t))
        for i in range(3))


def _polygon(x0, y0, x1, y1, chamfer, corners):
    """Vertices (clockwise from the top-left) of the chamfered rect."""
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


def build_glow(corners=CUT2_CORNERS):
    """Outer glow of the chamfered plate, same idiom as slice_glow.tga: the
    shape is the plate inset by GLOW_PAD from the texture edge, alpha falls off
    outward over GLOW_PAD texels (quadratic, brighter against the edge) and is
    HOLLOW inside, because the glow is ADD-blended above the icon and a solid
    interior would wash across every spell icon. A cut corner leaves a lit
    diagonal gap where a square corner would have been, which is the point:
    the halo follows the chamfer."""
    pts = _polygon(GLOW_PAD, GLOW_PAD, SIZE - GLOW_PAD, SIZE - GLOW_PAD, CHAMFER, corners)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            distance = _distance_outside(x + 0.5, y + 0.5, pts)
            if distance <= 0 or distance >= GLOW_PAD:
                alpha = 0.0
            else:
                t = 1.0 - distance / GLOW_PAD
                alpha = t * t
            rows += bytes((255, 255, 255, int(round(alpha * 255))))
    return bytes(rows)


def build_mask(corners=CUT2_CORNERS):
    """MASK_SIZE square alpha mask: solid white RGB, shape in alpha, chamfer a
    fraction of the texture (see MASK_CHAMFER_FRACTION). Same format as
    mask_minimap.tga."""
    chamfer = MASK_CHAMFER_FRACTION * MASK_SIZE
    rows = bytearray()
    for y in range(MASK_SIZE):
        for x in range(MASK_SIZE):
            cov = _chamfer_coverage(x, y, 0, 0, MASK_SIZE, MASK_SIZE, chamfer, corners)
            rows += bytes((255, 255, 255, int(round(cov * 255))))
    return bytes(rows)


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    _write(os.path.join(here, "slice_cut_outline.tga"), build_outline())
    _write(os.path.join(here, "slice_cut_fill.tga"), build_fill())

    inner = CHAMFER - THICKNESS_CUT2 * (2.0 - math.sqrt(2.0))
    _write(os.path.join(here, "slice_cut2_outline.tga"),
           build_outline(CUT2_CORNERS, THICKNESS_CUT2, inner))
    _write(os.path.join(here, "slice_cut2_fill.tga"), build_fill(CUT2_CORNERS))
    _write(os.path.join(here, "slice_cut2_button.tga"), build_fill(CUT2_CORNERS, _gradient))
    _write(os.path.join(here, "slice_cut2_glow.tga"), build_glow())
    _write(os.path.join(here, "mask_cut2_square.tga"), build_mask(), MASK_SIZE)


if __name__ == "__main__":
    main()
