#!/usr/bin/env python3
"""Generates bar_led_tile.tga and bar_slant_tile.tga: the seamless fill tiles of the LED segments and Slant cells bar looks.

A bar look draws the fill of a health or power bar from one of these tiles: the StatusBar's fill texture repeats the tile
horizontally (SetHorizTile), so the engine crops the pattern at the value and no cell is ever counted in Lua (health and
power are secret numbers). The shape lives in the alpha channel, white, tinted by the bar's colour.

  bar_led_tile.tga    8 x 16: a 6 wide lit segment and a 2 wide gap, the gap the cut between two segments
  bar_slant_tile.tga  16 x 16: a parallelogram leaning `/` (4 over the full height), 12 wide on each row, a 4 wide gap;
                      the span wraps around the tile edge, so the tile repeats without a seam

Pure stdlib, like the other generators here. Output: 18 byte header, image type 2, descriptor 0x28 (top left origin,
8 alpha bits), BGRA top to bottom.

    python generate_bar_look_tiles.py
"""

import os
import struct

SUPERSAMPLE = 6


def led(px, py, width=8, height=16):
    return 1.0 if px < 6 else 0.0


def slant(px, py, width=16, height=16):
    """Coverage of pixel (px, py): the span [4 - shift, 16 - shift] wrapped to the tile, shift growing 0 to 4 downward."""
    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            x = px + (sx + 0.5) / SUPERSAMPLE
            y = py + (sy + 0.5) / SUPERSAMPLE
            shift = 4.0 * (y / height)
            left = 4.0 - shift
            if (x - left) % width < 12.0:
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


TILES = {"bar_led_tile": (8, 16, led), "bar_slant_tile": (16, 16, slant)}


def build(width, height, shape):
    rows = bytearray()
    for y in range(height):
        for x in range(width):
            alpha = int(round(shape(x, y) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def main():
    out = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    for name, (width, height, shape) in TILES.items():
        path = os.path.join(out, name + ".tga")
        header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
        with open(path, "wb") as fh:
            fh.write(header)
            fh.write(build(width, height, shape))
        print(f"wrote {path} ({width}x{height}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
