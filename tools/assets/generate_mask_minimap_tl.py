"""Generates mask_minimap_tl.tga: the minimap face's alpha mask with only the TOP-LEFT corner cut.

The minimap is no longer a box of its own. Since the 2026-11-12 cleanup the map, the key row and the coords are one
chamfered body whose TOP-LEFT and BOTTOM-RIGHT are cut (the Theme.CHROME_CORNERS "cut" vocabulary); the BOTTOM-RIGHT
cut now belongs to the body's last row, and the map above it ends in a straight bottom edge that meets the key row.
mask_minimap.tga (generate_mask_minimap.py), which also cut the map's bottom-right, is no longer what the map wears.

Shape: the full square minus a straight 45 degree triangle at the top-left, 6/250 = 0.024 of the side (about 6 px
on the minimap's 250 px base width). The other three corners stay square.

Because Minimap:SetMaskTexture stretches to whatever the map's current size is, a FRACTIONAL chamfer baked into the
mask stays correct at any UI scale.

Construction: supersampled coverage along the diagonal edge, solid white RGB, shape purely in alpha; pure stdlib,
18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom, no footer.

    python3 generate_mask_minimap_tl.py
"""

import os
import struct

SIZE = 64
CORNER_FRACTION = 6 / 250
SUPERSAMPLE = 4


def coverage(px, py):
    """Fraction of this pixel inside the shape, by supersampling: the full square minus the top-left triangle."""
    cut = CORNER_FRACTION * SIZE
    hits = 0
    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            x = px + (sx + 0.5) / SUPERSAMPLE
            y = py + (sy + 0.5) / SUPERSAMPLE
            if x + y < cut:
                continue
            hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = int(round(coverage(x, y) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def main():
    path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "mask_minimap_tl.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
