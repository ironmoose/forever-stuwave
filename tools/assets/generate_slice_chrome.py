#!/usr/bin/env python3
"""Generates the NINE-SLICE chrome textures: slice_fill, slice_button,
slice_border.

Why this exists, and why the older corner pieces are being retired for it:

Every rounded thing in this addon was composited out of primitives -- a centre
quad, four 1px rails, and four corner quads cut from a 64x64 arc texture. At
panel size that reads fine. At action-button size (a 4px radius on a ~22px
button) it falls apart, and a pixel dump of Parker's close-up says exactly how:

    y=7:  111015 111015 22e0ff   <- two near-BLACK pixels in the elbow
    y=8:  111015 22e0ff 22e0ff
    y=9:  22e0ff 22e0ff 241640

The rail ends and the arc quad did not meet. Two pixels of the button's dark
ground showed through the join, and the three cyan pixels that did land formed
a hard staircase with no antialiasing, because a 64x64 arc squeezed into a 4x4
quad has nothing left to interpolate. That is the "corners popping out" Parker
kept seeing -- not a glow bug, a seam.

Nine-slicing removes the seam by construction: ONE texture, and the engine
draws the corners from it at native texel resolution while stretching only the
straight edges. `SetTextureSliceMargins` + `SetTextureSliceMode` were both
confirmed present on this client (interface 16001) by live probe, along with
`Enum.UITextureSliceMode.Stretched == 0`, so this is not a modern-retail-only
path we are guessing at.

It is also much cheaper: a skinned button drops from ~13 texture regions to 3,
which matters because Parker is running at 25 FPS with 72 action buttons on
screen.

SIZE/RADIUS/margin contract: the margin passed to SetTextureSliceMargins must
equal RADIUS, so the corner slice contains exactly the arc and the edge slices
contain only straight runs. Theme.lua reads RADIUS back as Theme.SLICE_MARGIN;
change it here and there together.

Pure stdlib, like the other generators here. Output: 18-byte header, image type
2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_slice_chrome.py
"""

import math
import os
import struct

SIZE = 32
RADIUS = 5.0        # texels; MUST match Theme.SLICE_MARGIN
THICKNESS = 1.0     # border ring, in texels
SUPERSAMPLE = 6

# Outer glow. The shape is the same rounded rect, inset by GLOW_PAD from the
# texture edge, with the alpha falling off outward over those GLOW_PAD texels.
# Drawn on a region that overhangs the button by GLOW_PAD on every side, the
# shape boundary then lands exactly on the button's own rounded edge.
#
# Its slice margin is GLOW_PAD + RADIUS, not RADIUS -- the corner slice has to
# contain the whole arc AND its halo.
GLOW_PAD = 4

# Action-button background, from the mockup: #241640 at the top fading to
# #160c2b at the bottom. Baked into RGB rather than applied with SetGradient
# because a gradient is a per-vertex effect and a nine-sliced texture is nine
# quads -- it would band at every slice boundary.
GRAD_TOP = (0x24, 0x16, 0x40)
GRAD_BOTTOM = (0x16, 0x0c, 0x2b)


def _rounded_coverage(x, y, x0, y0, x1, y1, radius):
    """Fraction of pixel (x,y) inside the rounded rect [x0,x1] x [y0,y1].

    Uses the standard rounded-rect test -- clamp the sample to the rect inset
    by `radius`, then ask whether it is within `radius` of that clamped point.
    An earlier version short-circuited on "this sample is level with a straight
    edge, so it is inside", which is only true for samples already within the
    rect: it reported full coverage for points ABOVE the top edge and so
    cancelled the whole ring away, leaving only four loose arcs.

    Supersampled rather than analytic: these textures exist to give a clean
    antialiased arc, and the corner is only ~5 texels across.
    """
    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            py = y + (sy + 0.5) / SUPERSAMPLE

            if px < x0 or px > x1 or py < y0 or py > y1:
                continue

            cx = min(max(px, x0 + radius), x1 - radius)
            cy = min(max(py, y0 + radius), y1 - radius)
            if math.hypot(px - cx, py - cy) <= radius:
                hits += 1

    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def _write(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def build_fill(colour_at=None):
    """Solid rounded rect. White unless `colour_at(y)` bakes a gradient."""
    rows = bytearray()
    for y in range(SIZE):
        r, g, b = colour_at(y) if colour_at else (255, 255, 255)
        for x in range(SIZE):
            alpha = int(round(_rounded_coverage(x, y, 0, 0, SIZE, SIZE, RADIUS) * 255))
            rows += bytes((b, g, r, alpha))   # TGA is BGRA
    return bytes(rows)


def build_border():
    """Rounded-rect outline: outer shape minus the same shape inset by
    THICKNESS. Subtracting coverages (not shapes) keeps the antialiasing on
    both edges of the ring."""
    inner_radius = max(RADIUS - THICKNESS, 0.0)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            outer = _rounded_coverage(x, y, 0, 0, SIZE, SIZE, RADIUS)

            # Inner shape: the same rounded rect pulled in by THICKNESS on all
            # sides. Expressed as different BOUNDS rather than a shifted sample
            # point, so the straight edges of the ring survive.
            inner = _rounded_coverage(
                x, y,
                THICKNESS, THICKNESS, SIZE - THICKNESS, SIZE - THICKNESS,
                inner_radius)

            alpha = int(round(max(outer - inner, 0.0) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def build_glow():
    """Rounded rect with a soft outward falloff, for the outer glow.

    Replaces the four edge strips plus four corner quads that Theme.SkinButton
    used to build. Those strips are flush to the button's SQUARE edge, so they
    never covered the area a rounded corner cuts away: every button had a hard
    dark notch between its corner arc and its halo, which is what Parker kept
    seeing as "the corners are still not correct". A single sliced texture
    whose shape is the rounded rect itself cannot leave that gap.

    Alpha is 1 inside the shape and falls to 0 over GLOW_PAD texels outside it.
    The inside is covered by the opaque button fill, so only the falloff shows.
    """
    x0, y0 = GLOW_PAD, GLOW_PAD
    x1, y1 = SIZE - GLOW_PAD, SIZE - GLOW_PAD

    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            # Distance outside the rounded rect, sampled at the pixel centre.
            px, py = x + 0.5, y + 0.5
            cx = min(max(px, x0 + RADIUS), x1 - RADIUS)
            cy = min(max(py, y0 + RADIUS), y1 - RADIUS)
            distance = math.hypot(px - cx, py - cy) - RADIUS

            if distance <= 0:
                # HOLLOW inside. The glow is ADD-blended on the OVERLAY layer,
                # above the icon, so a solid interior would wash cyan across
                # every spell icon on the bar. Alpha 0 here also costs nothing
                # visually: the button's own fill occupies that area anyway.
                alpha = 0.0
            elif distance >= GLOW_PAD:
                alpha = 0.0
            else:
                # Quadratic falloff: brighter against the edge than a linear
                # ramp, which is how the old glow_edge texture read.
                t = 1.0 - distance / GLOW_PAD
                alpha = t * t

            rows += bytes((255, 255, 255, int(round(alpha * 255))))
    return bytes(rows)


def gradient(y):
    t = y / (SIZE - 1)
    return tuple(
        int(round(GRAD_TOP[i] + (GRAD_BOTTOM[i] - GRAD_TOP[i]) * t))
        for i in range(3)
    )


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    _write(os.path.join(here, "slice_fill.tga"), build_fill())
    _write(os.path.join(here, "slice_button.tga"), build_fill(gradient))
    _write(os.path.join(here, "slice_border.tga"), build_border())
    _write(os.path.join(here, "slice_glow.tga"), build_glow())


if __name__ == "__main__":
    main()
