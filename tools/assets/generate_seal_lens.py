#!/usr/bin/env python3
"""Generates the two 128x128 textures of the Seal Chamber's lens (the Paladin module in the DoT slot).

Files written (in forever-stuwave/Media/Textures):

    seal_lens.tga   the static lens: an outer ring, 36 inward ticks and an inner ring
    seal_arcs.tga   the three bright arcs that turn round the outer ring, at their start angles

Source of truth: drawSealChamber in mockups/gunsight-hud-v2-2026-10-02/, the block under "the
lens". Its numbers, in mockup image px, with the lens centred on (SC_GX, SC_GY):

    outer ring    radius SC_GR = 50, line width LW, alpha .28 (x neon)
    ticks         36, one every 10 degrees from +x clockwise (the canvas has y down), from
                  SC_GR - 1 inward by 6.5 (every third one, i % 3 == 0) or 3.5, line width LW,
                  butt caps, alpha .5
    inner ring    radius SC_GR - 14, line width LW, alpha .18
    arcs          three, radius SC_GR, line width LW * 1.6, butt caps, each .62 rad long, the
                  first starting at p (here 0, the texture is turned by the Lua side) and the
                  others 2 pi / 3 further round, alpha .95 (x neon)

LW is 1.3 screen px at the mockup's default 1400 px wide preview of its 2000 px canvas, so
1.3 * 2000 / 1400 = 1.857 image px.

Scale: 1.2 texels per image px, so the 128 texel canvas is 128 / 1.2 = 106.67 image px square,
centred on the lens centre, and the outer ring is 60 texels from the centre (the widest thing on
the canvas, the arc, reaches 61.8, so there are 2.2 texels of room). A caller sizes both
textures to 128 / 1.2 = 106.67 image px square (times its image-px-to-UI factor) and centres
them on the lens; rotating seal_arcs about its centre turns the arcs about the lens centre.

The three ring layers have different alphas in the mockup and they live in ONE texture, so those
alphas are baked (the layers composite with "over", as the canvas does where they touch), the way
generate_hud_key_glyphs.py bakes a second line's stroke opacity. The Lua side multiplies the
whole texture by the mockup's neon value. The arcs are one layer, so seal_arcs is baked at full
alpha and the caller applies .95 x neon.

Same convention as generate_deck_glyphs.py: crisp line art, anti-aliased, NO baked glow (the
mockup's glow on the arcs is a shadow blur the Lua side stands in for), shape in the alpha
channel with white RGB, tinted with SetVertexColor.

Pure stdlib. Output per file: 18-byte header, image type 2, descriptor 0x28 (top-left origin,
8 alpha bits), BGRA top-to-bottom.

    python generate_seal_lens.py
"""

import math
import os
import struct

SIZE = 128
SUPERSAMPLE = 4
CENTRE = SIZE / 2.0
K = 1.2                         # texels per mockup image px

SC_GR = 50.0                    # mockup lens radius, image px
LW = 1.3 * 2000.0 / 1400.0      # mockup line width, image px

RING_R = SC_GR * K
INNER_R = (SC_GR - 14.0) * K
HALF = LW * K / 2.0
ARC_HALF = LW * 1.6 * K / 2.0

TICKS = 36
TICK_STEP = math.pi / 18.0
TICK_OUT = (SC_GR - 1.0) * K
TICK_LONG = (SC_GR - 6.5) * K   # i % 3 == 0 (the mockup's `i % 3 ? 3.5 : 6.5`)
TICK_SHORT = (SC_GR - 3.5) * K

ARCS = 3
ARC_SPAN = 0.62                 # radians
ARC_START = 0.0                 # p = t * .5 at t = 0

RING_ALPHA = 0.28
TICK_ALPHA = 0.5
INNER_ALPHA = 0.18

TAU = 2.0 * math.pi


def _tick_hit(dx, dy, r, theta):
    i = int(round(theta / TICK_STEP)) % TICKS
    f = i * TICK_STEP
    cf, sf = math.cos(f), math.sin(f)
    along = dx * cf + dy * sf
    perp = -dx * sf + dy * cf
    inner = TICK_LONG if i % 3 == 0 else TICK_SHORT
    return abs(perp) <= HALF and inner <= along <= TICK_OUT


def lens_alpha(dx, dy):
    r = math.hypot(dx, dy)
    if r > RING_R + HALF or r < INNER_R - HALF:
        return 0.0
    theta = math.atan2(dy, dx) % TAU
    keep = 1.0
    if abs(r - RING_R) <= HALF:
        keep *= 1.0 - RING_ALPHA
    if abs(r - INNER_R) <= HALF:
        keep *= 1.0 - INNER_ALPHA
    if TICK_LONG - HALF <= r <= TICK_OUT + HALF and _tick_hit(dx, dy, r, theta):
        keep *= 1.0 - TICK_ALPHA
    return 1.0 - keep


def arcs_alpha(dx, dy):
    r = math.hypot(dx, dy)
    if abs(r - RING_R) > ARC_HALF:
        return 0.0
    theta = math.atan2(dy, dx) % TAU
    for i in range(ARCS):
        if (theta - (ARC_START + i * TAU / ARCS)) % TAU <= ARC_SPAN:
            return 1.0
    return 0.0


def build(alpha_at):
    n = SUPERSAMPLE * SUPERSAMPLE
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                py = y + (sy + 0.5) / SUPERSAMPLE - CENTRE
                for sx in range(SUPERSAMPLE):
                    total += alpha_at(x + (sx + 0.5) / SUPERSAMPLE - CENTRE, py)
            rows += bytes((255, 255, 255, int(round(total / n * 255))))
    return bytes(rows)


def write_tga(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)


OUTPUTS = {
    "seal_lens": lens_alpha,
    "seal_arcs": arcs_alpha,
}


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    for name, alpha_at in OUTPUTS.items():
        path = os.path.join(here, name + ".tga")
        write_tga(path, build(alpha_at))
        print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
