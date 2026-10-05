#!/usr/bin/env python3
"""Generates cell_slant_glow.tga: the XP bar pip shape with a feathered edge.

Why: the first glow pass used a straight horizontal bleed plus a ROUND radial
at the leading edge. Against eighty leaning pips both read as foreign -- a
rectangular haze and a circular blob over a bar made entirely of slashes.
Parker's note was "the glow needs to be slanty too" and "the pips should get
some", which is the same fix twice: every glowing thing on this bar should be
the pip's own shape.

So this is cell_slant's parallelogram with alpha falling off outward over PAD
texels instead of stopping at a hard edge. Each pip gets one behind it, and the
leading pip gets a larger, brighter copy.

GEOMETRY CONTRACT: the shape occupies the middle (SIZE - 2*PAD) of the texture,
so a glow drawn at SIZE/(SIZE - 2*PAD) times the pip's size, centred on it,
puts the shape exactly on the pip with the falloff spilling outside. XPBar.lua
calls that ratio GLOW_SCALE -- change PAD here and that constant must follow.

The slant is a fraction of the SHAPE's width, matching cell_slant's definition,
so both lean at the same angle however the textures are stretched.

Pure stdlib, matching the other generators here. Output: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_cell_glow.py
"""

import math
import os
import struct

SIZE = 64
PAD = 10            # falloff distance, in texels, on every side
SLANT = 0.34        # fraction of the SHAPE width, same as cell_slant.py
SUPERSAMPLE = 3


def _distance_outside(px, py):
    """Distance from (px, py) to the parallelogram; 0 when inside."""
    inner_h = SIZE - 2 * PAD
    inner_w = SIZE - 2 * PAD
    slant = SLANT * inner_w

    # Vertical: how far outside the shape's band.
    dy = max(PAD - py, py - (SIZE - PAD), 0.0)

    # Horizontal span for this row, sliding left as it descends. Clamped so
    # rows above and below the shape use the nearest edge's span rather than
    # extrapolating the lean off to infinity.
    t = min(max((py - PAD) / inner_h, 0.0), 1.0)
    shift = slant * t
    x0 = PAD + slant - shift
    x1 = (SIZE - PAD) - shift
    dx = max(x0 - px, px - x1, 0.0)

    return math.hypot(dx, dy)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    px = x + (sx + 0.5) / SUPERSAMPLE
                    py = y + (sy + 0.5) / SUPERSAMPLE

                    distance = _distance_outside(px, py)
                    if distance <= 0.0:
                        total += 1.0
                    elif distance < PAD:
                        # Quadratic falloff: reads brighter against the pip
                        # edge than a linear ramp, which is what makes it look
                        # like emitted light rather than a blur.
                        fade = 1.0 - distance / PAD
                        total += fade * fade

            alpha = total / (SUPERSAMPLE * SUPERSAMPLE)
            # White; every pip tints its own glow with SetVertexColor, so the
            # shape has to live entirely in the alpha channel.
            rows += bytes((255, 255, 255, int(round(alpha * 255))))
    return bytes(rows)


def main():
    path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media")), "cell_slant_glow.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
    print(f"GLOW_SCALE for XPBar.lua = {SIZE / (SIZE - 2 * PAD):.4f}")


if __name__ == "__main__":
    main()
