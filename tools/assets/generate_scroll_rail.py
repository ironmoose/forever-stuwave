#!/usr/bin/env python3
"""Generates scroll_rail.tga: the chat scrollbar's rail and thumb light.

ONE TEXTURE FOR BOTH, because they are the same light at two strengths -- a
dim groove and a bright slider running in it. The caller tints and sizes it.

The alpha varies ONLY ACROSS the texture, never along it. That is the whole
design constraint: a scrollbar thumb is stretched to an arbitrary height that
changes as the chat scrolls, so anything baked into the vertical axis would
squash and stretch with it. With a purely horizontal profile the texture is
correct at every height by construction, which is the same reason
generate_tab_slant.py bakes the middle run's glow the way it does.

The falloff curve is deliberately the SAME quadratic ease-out as the tab
chrome, so the scrollbar reads as part of the same instrument rather than a
borrowed widget. Sizing two different curves to look alike matches their
extent, not their shape, and they never quite agree -- that lesson cost a
round of "i think you have a different glow" on the tab caps.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_scroll_rail.py
"""

import os
import struct

SIZE = 32
CENTRE = SIZE / 2.0
# The core is a large fraction of the width on purpose. The texture stretches
# to whatever width the caller draws it at, so a narrow core stays narrow in
# PROPORTION -- widening the bar would then just spread the glow and leave the
# same hairline bright band, which reads as washed out rather than wider. At
# ~34% of the texture width the bright band scales with the bar the way a
# scrollbar is expected to.
CORE = 5.5          # texels either side of centre at full brightness
GLOW = 5.0          # texels the light reaches outward from the core
SUPERSAMPLE = 6


def _falloff(distance):
    """Eased brightness `distance` texels from the centre line.

    Quadratic ease-out, matching generate_tab_slant.py's _falloff so the rail
    and the tab strip are lit by the same curve.
    """
    if distance <= CORE:
        return 1.0
    t = (distance - CORE) / GLOW
    return 0.0 if t >= 1.0 else (1.0 - t) ** 2


def _value(px, _py):
    return _falloff(abs(px - CENTRE))


def _coverage(x, y):
    total = 0.0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            total += _value(px, py)
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    # Every row is identical by construction, so compute one and repeat it.
    # Not merely an optimisation: it guarantees the profile cannot drift down
    # the texture, which is the property the stretch depends on.
    row = bytearray()
    for x in range(SIZE):
        row += bytes((255, 255, 255, int(round(_coverage(x, 0) * 255))))
    return bytes(row) * SIZE


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "scroll_rail.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
