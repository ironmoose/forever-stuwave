#!/usr/bin/env python3
"""Bake the damage meter's cell tile.

The source is the design mockup "Damage Meter" (2026-11-09), form D: drawD() and slantCell(). A row's gauge is the XP bar's
run of leaning cells. The engine draws the class gradient as one flat fill that it crops to the row's value (the value is
secret in combat, so no addon code can count lit cells), and this tile is laid OVER that fill and over the unlit track,
repeated across the gauge one texel per physical pixel. It cuts both into cells and shades each cell the way the mockup does.

    dm_cell_tile.tga   16 x 16  one pip and its gap: an 11 px pip leaning half a px per row (its top row sits right of its
                                bottom row) and a 5 px gap. Pip px are clear, so the fill shows through with its own shading
                                (the module paints the fill as one vertical gradient, so every pip is a single gradient, as
                                the XP bar's are); gap px are the track ink, nearly opaque, cutting fill and track into pips.
                                The module samples the BOTTOM rows it needs (the gauge is 6 to 10 px tall, by row height),
                                so the lean stays half a px per row at any gauge height. The tile wraps left to right.

    python3 tools/assets/generate_damage_meter_cells.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import os
import struct

TILE = 16         # px per tile, both ways (a power of two, like every texture the addon ships)
PIP = 11          # px of a pip's width; the gap is TILE - PIP
LEAN_PER_ROW = 0.5  # px each row up sits right of the row below
GAP_INK = (6, 3, 18)   # #060312, the XP bar's track
GAP_ALPHA = 0.92


def pip_offset(row: int) -> int:
    """x of a row's first pip px: 0 on the bottom row, LEAN_PER_ROW more for each row above it."""
    return int((TILE - 1 - row) * LEAN_PER_ROW + 0.5)


def tile() -> list[tuple[int, int, int, int]]:
    px = []
    for row in range(TILE):
        off = pip_offset(row)
        lit = {(off + k) % TILE for k in range(PIP)}
        for x in range(TILE):
            px.append((255, 255, 255, 0) if x in lit else (*GAP_INK, round(255 * GAP_ALPHA)))
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
