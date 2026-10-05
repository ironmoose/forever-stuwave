#!/usr/bin/env python3
"""Generates pet_dock_flare_line.tga and pet_dock_flare_glow.tga: the stroke and the halo of the
pet panel's docked FLARE (PetDock.lua; mockup option C, drawPet's dc branch).

The docked panel is an open shoulder: top-left cut, a straight left side, and a right foot that
flares 10 px outward at 45 degrees. Every straight run is a plain texture (1 texel lines, the
glow_edge strips) but the 45 degree foot cannot be one: a nine-slice or a stretched strip bends
it, and tab_slant.tga (the wedge CastBars.lua pairs under its fill) is a SOLID triangle. The pet
fill is the translucent HUD scrim, so a solid stroke wedge under it would show through the whole
triangle. So the stroke and the halo of the flare are baked as their own pieces:

    pet_dock_flare_line.tga   the 1 px stroke band, 12 x 10 design px at 10 texels per px
    pet_dock_flare_glow.tga   the halo of the vertical run's last 7 px plus the flare, 17 x 17
                              design px at 7 texels per px

Both are 128 x 128 canvases with the piece at the top-left (the cut pieces' convention), so a
piece of w x h design px is sampled with SetTexCoord(0, w * k / 128, 0, h * k / 128). White RGB,
shape in alpha, tinted by the caller.

GEOMETRY (art-local design px, y down, W = panel width, H = panel height, f = 10 the flare):
the centreline runs (W - .5, H - f) -> (W - .5 + f, H); the right line is the 1 px column
[W - 1, W], so the band continues it half a px inside, and a 1 px band is +-.5 perpendicular.

  LINE piece: origin (W - 2, H - f), 12 x 10 px, k = 10. Coverage is the band
  |(x - 1.5) - y| <= .5 * sqrt 2, solid from the piece's top (the vertical line already covers
  the join) to a butt cap through the foot, clipped at y = H (the bottom is open).

  GLOW piece: origin (W, H - f - R), 17 x 17 px, k = 7, R = 7 the halo's reach. Alpha is
  (1 - d / R)^2, the glow_edge.tga profile, where d is the OUTER distance from the path: the
  vertical run (d = x, valid up to the vertex) and the 45 degree foot (valid between its butt
  caps), whichever is nearer. Nothing inside the panel, nothing under the stroke band, nothing
  below y = H (the Console chassis owns that edge): "none along the open bottom".

PetDock.lua carries the same numbers and petdock-harness.py rasterizes the real files against the
mockup's path, so a drift in either place fails there.

Pure stdlib, matching the other generators here. Output: 18-byte header, image type 2,
descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top to bottom.

    python generate_pet_dock_flare.py
"""

import math
import os
import struct

CANVAS = 128
FLARE = 10.0            # f: the foot's horizontal and vertical extent
REACH = 7.0             # R: the halo's reach (the mockup's HALO table tops out at 7)
HALF = 0.5              # half the 1 px stroke
SUPERSAMPLE = 8
SQRT2 = math.sqrt(2.0)

LINE_K = 10             # texels per design px
LINE_W, LINE_H = 12, 10
GLOW_K = 7
GLOW_W = GLOW_H = 17    # FLARE + REACH


def line_value(x, y):
    """Stroke band coverage at a point of the LINE piece (design px, origin top-left)."""
    # The centreline enters the piece at (1.5, 0) and runs (1, 1) down to (11.5, 10).
    s = ((x - 1.5) - y) / SQRT2
    t = ((x - 1.5) + y) / SQRT2
    return 1.0 if abs(s) <= HALF and t <= FLARE * SQRT2 else 0.0


def glow_value(x, y):
    """Halo alpha at a point of the GLOW piece (design px, origin top-left of the 17 x 17)."""
    px, py = -0.5, REACH                     # the vertex (W - .5, H - f) in piece coordinates
    distances = []
    if x > 0 and y <= py:                    # the vertical run's outer edge is x = 0
        distances.append(x)
    s = ((x - px) - (y - py)) / SQRT2
    t = ((x - px) + (y - py)) / SQRT2
    if s > HALF and 0.0 <= t <= FLARE * SQRT2:
        distances.append(s - HALF)
    if not distances:
        return 0.0
    f = 1.0 - min(distances) / REACH
    return f * f if f > 0.0 else 0.0


def bake(width, height, k, value_at):
    """A CANVAS x CANVAS alpha grid: the piece at the top-left, coverage supersampled per texel."""
    grid = [[0] * CANVAS for _ in range(CANVAS)]
    for ty in range(min(CANVAS, height * k)):
        for tx in range(min(CANVAS, width * k)):
            total = 0.0
            for sy in range(SUPERSAMPLE):
                y = (ty + (sy + 0.5) / SUPERSAMPLE) / k
                for sx in range(SUPERSAMPLE):
                    total += value_at((tx + (sx + 0.5) / SUPERSAMPLE) / k, y)
            grid[ty][tx] = round(255 * total / (SUPERSAMPLE * SUPERSAMPLE))
    return grid


def write_tga(path, grid):
    header = bytes([0, 0, 2, 0, 0, 0, 0, 0]) + struct.pack("<HHHH", 0, 0, CANVAS, CANVAS) + bytes([32, 0x28])
    pixels = bytearray()
    for row in grid:
        for alpha in row:
            pixels += bytes([255, 255, 255, alpha])  # BGRA: white, shape in alpha
    with open(path, "wb") as out:
        out.write(header + bytes(pixels))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    write_tga(os.path.join(here, "pet_dock_flare_line.tga"), bake(LINE_W, LINE_H, LINE_K, line_value))
    write_tga(os.path.join(here, "pet_dock_flare_glow.tga"), bake(GLOW_W, GLOW_H, GLOW_K, glow_value))


if __name__ == "__main__":
    main()
