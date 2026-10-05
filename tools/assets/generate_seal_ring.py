#!/usr/bin/env python3
"""Generates the Seal Chamber's Judgement ring, a 256x256 texture (the Paladin module in the DoT slot).

File written (next to this script):

    seal_ring.tga   one full circle at the lens radius, with the mockup's glow(col, 1) halo baked round it

Source of truth: drawSealChamber in mockups/gunsight-hud-v2-2026-10-02/, the block under "JUDGEMENT cast":

    if(f<.9){p=ease(f/.9);A(.85*(1-p));glow(col,1);ctx.strokeStyle=col;ctx.lineWidth=LW*1.6;
             ctx.beginPath();ctx.arc(SC_GX,SC_GY,SC_GR+p*26,0,Math.PI*2);ctx.stroke();noglow();}

Its numbers, in mockup image px, with the ring centred on (SC_GX, SC_GY):

    ring          radius SC_GR = 50 (at rest, the Lua side scales the texture to grow it), stroke LW * 1.6
    halo          glow(col, 1): the mockup's HALO table, [[1.5, .26], [3.2, .17], [5, .10], [7, .055]]. Each
                  entry is one more stroke of the same circle, width LW * 1.6 + 2 * reach at alpha a, drawn
                  BEFORE the core stroke, so the core sits on top and the strokes composite with "over"

LW is 1.3 screen px at the mockup's default 1400 px wide preview of its 2000 px canvas, so
1.3 * 2000 / 1400 = 1.857 image px.

Scale: 1.2 texels per image px, the same as seal_lens.tga and seal_arcs.tga, so the ring's stroke is
as sharp as the lens it leaves. The halo reaches 1.857 * 1.6 / 2 + 7 = 8.5 image px past the ring's
centre line, which puts the outermost halo edge 60 + 10.2 = 70.2 texels from the centre; that does
not fit the lens' 128 canvas (64 texels), so this is a 256 canvas (213.33 image px square). A caller
sizes the texture to 256 / 1.2 image px at rest and centres it on the lens.

The layers have different alphas in the mockup and live in ONE texture, so those alphas are baked
(composited with "over" the way the canvas does where the strokes overlap); the core is baked at full
alpha and the Lua side multiplies the whole texture by the mockup's A(.85 * (1 - p)). One difference
that cannot be baked: the mockup keeps the stroke and halo widths as the ring grows and the Lua side
scales the texture, so a growing ring thickens a little (it is also fading out by then).

Same convention as generate_seal_lens.py: anti-aliased, white RGB, shape in the alpha channel, tinted
with SetVertexColor. Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_seal_ring.py
"""

import math
import os
import struct

SIZE = 256
SUPERSAMPLE = 4
CENTRE = SIZE / 2.0
K = 1.2                         # texels per mockup image px (the lens' scale)

SC_GR = 50.0                    # mockup lens radius, image px
LW = 1.3 * 2000.0 / 1400.0      # mockup line width, image px

RING_R = SC_GR * K
CORE_HALF = LW * 1.6 * K / 2.0
# the mockup's HALO: (reach, alpha); each stroke is the core's width plus twice the reach
HALO = ((1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055))


def ring_alpha(dx, dy):
    d = abs(math.hypot(dx, dy) - RING_R)
    if d <= CORE_HALF:
        return 1.0
    keep = 1.0
    for reach, a in HALO:
        if d <= CORE_HALF + reach * K:
            keep *= 1.0 - a
    return 1.0 - keep


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
    "seal_ring": ring_alpha,
}


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    for name, alpha_at in OUTPUTS.items():
        path = os.path.join(here, name + ".tga")
        write_tga(path, build(alpha_at))
        print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
