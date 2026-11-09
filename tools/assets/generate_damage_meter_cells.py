#!/usr/bin/env python3
"""Bake the damage meter's cell tile.

The source is the design mockup "Damage Meter" (2026-11-09), form D: drawD() and slantCell(). A row's gauge is the XP bar's
run of leaning cells. The engine draws the class gradient as one flat fill that it crops to the row's value (the value is
secret in combat, so no addon code can count lit cells), and this tile is laid OVER that fill and over the unlit track,
repeated across the gauge one texel per physical pixel. It cuts both into cells and shades each cell the way the mockup does.

    dm_cell_tile.tga   16 x 16  one cell and its gap, in the XP bar's proportions (a wide leaning cell, a 3 px gap). The cell
                                is CELL px wide and leans LEAN px over the ROWS px the gauge shows (its top row sits LEAN px
                                right of its bottom row); rows past ROWS repeat the last one, padding the file to a power of
                                two, and the module samples only the first ROWS (SetTexCoord v = ROWS / 16). Cell px are
                                shading only: white at TOP_LIFT alpha on the top row easing to clear at the middle, then to
                                black at FOOT_SHADE alpha on the bottom row (the mockup's mix toward white .25 at the top and
                                black .3 at the foot). Gap px are the track ink, nearly opaque, so the fill underneath is cut
                                into cells. The tile wraps left to right.

    python3 tools/assets/generate_damage_meter_cells.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import os
import struct

TILE = 16         # px per tile, both ways (a power of two, like every texture the addon ships)
ROWS = 10         # px of the gauge's height: the rows the module samples
CELL = 13         # px of a cell's width; the gap is TILE - CELL (3, the XP bar's CELL_GAP)
LEAN = 5          # px the top row sits right of the bottom row
TOP_LIFT = 0.25   # white alpha on the top row
FOOT_SHADE = 0.30 # black alpha on the bottom row
GAP_INK = (6, 3, 18)   # #060312, the XP bar's track
GAP_ALPHA = 0.92


def cell_offset(row: int) -> int:
    """x of a row's first cell px: LEAN on the top row, 0 on the bottom row (the mockup's Math.round((1 - t) * lean))."""
    t = min(row, ROWS - 1) / (ROWS - 1)
    return int((1 - t) * LEAN + 0.5)


def shade(row: int) -> tuple[int, int, int, int]:
    t = min(row, ROWS - 1) / (ROWS - 1)
    if t <= 0.5:
        return (255, 255, 255, round(255 * TOP_LIFT * (1 - t / 0.5)))
    return (0, 0, 0, round(255 * FOOT_SHADE * ((t - 0.5) / 0.5)))


def tile() -> list[tuple[int, int, int, int]]:
    px = []
    for row in range(TILE):
        off = cell_offset(row)
        lit = {(off + k) % TILE for k in range(CELL)}
        for x in range(TILE):
            px.append(shade(row) if x in lit else (*GAP_INK, round(255 * GAP_ALPHA)))
    return px


def tga_bytes(px: list[tuple[int, int, int, int]], w: int, h: int) -> bytes:
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    body = bytearray()
    for r, g, b, a in px:
        body += bytes((b, g, r, a))
    return header + bytes(body)


def out_dir() -> str:
    return os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))


def main() -> None:
    path = os.path.join(out_dir(), "dm_cell_tile.tga")
    with open(path, "wb") as fh:
        fh.write(tga_bytes(tile(), TILE, TILE))
    print(f"wrote {path} ({TILE}x{TILE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
