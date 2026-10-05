#!/usr/bin/env python3
"""Generates tab_slant.tga and tab_slant_glow.tga: the leaning tab end cap.

WHY A CAP AND NOT A NINE-SLICE

The tab plate leans like the XP bar's cells (Parker: "for the shape lets try
the cool slanty rectangle like we have in the xp bar"), and a leaning shape
CANNOT be nine-sliced. Nine-slice stretches the middle band vertically and
leaves the corner slices at native size, so a straight diagonal comes out as
three segments at two different slopes -- a visible kink partway up each side.

So the plate is built the way a leaning shape has to be: a fixed-size slanted
cap at each end with a plain stretched rectangle between them. The caps never
scale, so the ANGLE is identical on every tab no matter how wide the label is.
That is also why the lean here is expressed in texels rather than as a fraction
of the width the way generate_cell_slant.py does it -- an XP cell is one fixed
size, a tab is not.

    tab_slant.tga       the solid wedge. Filled where x/W >= 1 - y/H, i.e. the
                        leading edge travels right as it rises, giving the "/"
                        lean. The TRAILING cap is this same texture flipped on
                        BOTH axes via SetTexCoord -- flipping only horizontally
                        gives a "\\" that tapers the wrong way, which is the
                        easy mistake here.

    tab_mid_raster.tga  scanlines across the straight run, and
    tab_slant_raster.tga the same lines clipped to the TRAILING wedge, baked
                        pre-flipped so it is drawn upright. Flipping a raster
                        vertically the way the shape is flipped mirrors the
                        line pattern and throws it out of phase; see the
                        function for why.

    tab_mid_glow.tga    the straight run's top and bottom edges as light, the
                        same curve at the same scale as the cap's straight
                        edge. Stretched horizontally across the middle and
                        drawn at the caps' height, it matches them row for row.

    tab_slant_glow.tga  the wedge's edges as light: brightest along the
                        hypotenuse AND along the straight edge, falling off
                        INWARD over GLOW texels, zero outside the shape.
                        Tinted and blended ADD, this is the "border ... glow
                        inward" without a second geometry pass -- a
                        rectangular glow strip cannot follow a diagonal, and
                        clamping one to the flat part leaves a visible
                        vertical seam where it stops.

Pure stdlib, matching the other generators here. Output: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_tab_slant.py
"""

import math
import os
import struct

SIZE = 32
GLOW = 10.0         # texels the edge light reaches inward from the diagonal
EDGE = 1.5          # texels of solid core on the diagonal itself
SUPERSAMPLE = 6


def _signed_distance(px, py):
    """Distance from the hypotenuse; positive INSIDE the wedge.

    The diagonal runs from the top-right corner (SIZE, 0) to the bottom-left
    (0, SIZE), so the line is x + y = SIZE and the inside is x + y >= SIZE.
    Dividing by sqrt(2) converts the algebraic value to true distance, which
    is what keeps the glow an even width along the slope instead of wider
    where the line is shallow.
    """
    return (px + py - SIZE) / math.sqrt(2.0)


def _coverage(x, y, value_at):
    """Supersample `value_at` over the texel's area; returns 0..1."""
    total = 0.0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            total += value_at(px, py)
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def _solid(px, py):
    return 1.0 if _signed_distance(px, py) >= 0.0 else 0.0


def _falloff(distance):
    """Eased brightness at `distance` texels in from an edge.

    Quadratic ease-out, the same shape generate_glow_edge.py uses, so the caps
    and the straight middle run read as one light rather than two.
    """
    if distance <= EDGE:
        return 1.0
    t = (distance - EDGE) / GLOW
    return 0.0 if t >= 1.0 else (1.0 - t) ** 2


def _edge_light(px, py):
    """Light off BOTH of this wedge's edges, brightest at each, 0 outside.

    The diagonal is the obvious one. The STRAIGHT edge matters just as much:
    the cap has a full-width bottom (and, once flipped for the trailing end, a
    full-width top), and the middle run's glow is a rectangle that has to stop
    where the straight part stops. Without the cap lighting its own straight
    edge, that stop is a hard vertical seam and the glow reads as a rectangle
    floating inside a leaning plate -- Parker: "lol now it looks silly."

    Baking both here means the cap's light follows the silhouette on the
    diagonal AND hands off seamlessly to the middle run on the flat.
    """
    if _signed_distance(px, py) < 0.0:
        return 0.0
    return max(_falloff(_signed_distance(px, py)), _falloff(SIZE - py))


def _write(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def build(value_at):
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = int(round(_coverage(x, y, value_at) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


# Raster period in TEXELS. The caps and the middle are both drawn at the pill's
# height, so a period baked here lands at RASTER_PERIOD * pillHeight / SIZE
# pixels on screen -- about 3px at the current 21px pill. Baking it rather than
# tiling a small texture is what lets the SLANTED cap carry the same lines: a
# tiled rectangle over a wedge overhangs the diagonal, exactly as a rectangular
# glow does.
RASTER_PERIOD = 4.5
RASTER_CORE = 0.55      # texels at full brightness
RASTER_FALLOFF = 1.5    # texels of glow either side of the core


def _raster(py):
    """Symmetric scanline with a soft edge, so the lines glow rather than tick."""
    phase = py % RASTER_PERIOD
    d = min(phase, RASTER_PERIOD - phase)      # distance to the nearest line
    if d <= RASTER_CORE:
        return 1.0
    t = (d - RASTER_CORE) / RASTER_FALLOFF
    return 0.0 if t >= 1.0 else (1.0 - t) ** 2


def _mid_raster(px, py):
    return _raster(py)


def _slant_raster(px, py):
    """The same lines, clipped to the TRAILING wedge and already flipped.

    Baked pre-flipped so the caller draws it upright, and that is the whole
    point. The solid cap and its glow are drawn with SetTexCoord(1, 0, 1, 0),
    a flip on BOTH axes -- which is correct for a shape and for a falloff
    measured off the diagonal, since both are symmetric about it. It is wrong
    for a raster: flipping vertically mirrors the line pattern, and a period
    that does not divide the texture height evenly (4.5 into 32 does not) comes
    back out of phase. The lines then sit a pixel or two off the straight run's
    at the seam.

    So this clips to the trailing silhouette directly -- filled where
    x + y <= SIZE, the mirror of the leading wedge -- and keeps the raster's
    own vertical phase, identical to tab_mid_raster's.
    """
    return _raster(py) if (px + py) <= SIZE else 0.0


def _mid_light(px, py):
    """Light off the straight top AND bottom edges, for the stretched middle.

    Deliberately the SAME _falloff, over the SAME SIZE texels, as the cap uses
    for its straight edge. That is the whole point of generating it here rather
    than reusing glow_edge.tga: that texture is a different curve (no solid
    core) spanning its own full height, so however carefully the two were sized
    they met at the cap seam as two different lights -- Parker: "the corners
    still don't line up... i think you have a different glow."

    Drawn at the same height as the caps, this is pixel-identical to them row
    for row, so the seam disappears by construction instead of by tuning.
    """
    return max(_falloff(py), _falloff(SIZE - py))


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    _write(os.path.join(here, "tab_slant.tga"), build(_solid))
    _write(os.path.join(here, "tab_slant_glow.tga"), build(_edge_light))
    _write(os.path.join(here, "tab_mid_glow.tga"), build(_mid_light))
    _write(os.path.join(here, "tab_mid_raster.tga"), build(_mid_raster))
    _write(os.path.join(here, "tab_slant_raster.tga"), build(_slant_raster))
