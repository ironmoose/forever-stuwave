#!/usr/bin/env python3
"""Generates hud_tile.tga: the tile fill of the combat HUD.

The mockup paints `.hud-ic .tile, .hud-next, .hud-buff` with
`linear-gradient(135deg, var(--surface), var(--bg))`: two stops, from --surface #2d1b4e at the
top left to --bg #1a1025 at the bottom right. WoW has no diagonal gradient call, so it is baked
here as an opaque 64 x 64 texture that CombatHud.lua stretches over every spell tile, the next
tile and the buff tiles (the tiles are all square, and a CSS 135 degree gradient over a square is
t = (x + y) / (2 * size), the same for every size).

Two-corner twin, hud_tile_cut2.tga (Parker, 2026-10-02: every rectangle gets TOP-LEFT and
BOTTOM-RIGHT cut corners, tiles included): the same gradient, byte for byte in RGB, with the
top-left and bottom-right corners chamfered in alpha (antialiased by supersampling) and the
other two square. hud_tile.tga itself is NOT changed. The tile is STRETCHED over 24 to 56 px
tiles, so the chamfer is a fraction of the texture, not a texel count: 6 px on the 36 px spell
tile is 1/6 of it (CUT_FRACTION), about 10.7 of the 64 texels, which lands at 4 px on the 24 px
buff tile and 9 px on the 56 px next tile. A caller that wants a fixed 6 px cut on every size
cannot get it from one stretched texture.

The colours are RGB in the file, not a vertex tint, so the gradient survives (a tint would
multiply it). Pure stdlib, matching the other generators here. Output: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_hud_tile.py
"""

import os
import struct

SIZE = 64
CUT_FRACTION = 6.0 / 36.0       # chamfer as a fraction of the tile: 6 px on the 36 px spell tile
CUT_SUPERSAMPLE = 8             # NxN samples per texel for the antialiased chamfer edge
SURFACE = (0x2D, 0x1B, 0x4E)    # --surface in mockups/combat-hud-stack-a-2026-10-02.html
BG = (0x1A, 0x10, 0x25)         # --bg


def _pixel(x, y):
    t = ((x + 0.5) + (y + 0.5)) / (2.0 * SIZE)
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(SURFACE, BG))


def _cut2_coverage(x, y):
    """Fraction of texel (x,y) inside the tile with TOP-LEFT and BOTTOM-RIGHT chamfered."""
    chamfer = CUT_FRACTION * SIZE
    ss = CUT_SUPERSAMPLE
    hits = 0
    for sy in range(ss):
        for sx in range(ss):
            px = x + (sx + 0.5) / ss
            py = y + (sy + 0.5) / ss
            # Ties (a sample exactly on the cut, possible when chamfer is a whole number)
            # split half and half so the edge is not biased to one side.
            for nudge in (1.0e-7, -1.0e-7):
                u, v = px + nudge, py + nudge
                if u + v >= chamfer and (SIZE - u) + (SIZE - v) >= chamfer:
                    hits += 1
    return hits / (2 * ss * ss)


def _write(path, rows):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    rows = bytearray()
    cut_rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b = _pixel(x, y)
            rows += bytes((b, g, r, 255))
            cut_rows += bytes((b, g, r, int(round(_cut2_coverage(x, y) * 255))))
    _write(os.path.join(here, "hud_tile.tga"), rows)
    _write(os.path.join(here, "hud_tile_cut2.tga"), cut_rows)


if __name__ == "__main__":
    main()
