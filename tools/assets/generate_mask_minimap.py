"""Generates mask_minimap.tga: a barely-chamfered alpha mask for the minimap
face, replacing the hard-square Interface\\BUTTONS\\WHITE8X8 mask.

Shape: every rectangle in the UI cuts its TOP-LEFT and BOTTOM-RIGHT corners
only; top-right and bottom-left stay square. The cut is a straight 45 degree
chamfer whose size is 6/250 = 0.024 of the side (about 6 px on the minimap's
250 px base width).

Because Minimap:SetMaskTexture stretches to whatever Minimap's current size
is, a FRACTIONAL chamfer baked into the mask stays correct automatically at
any UI scale -- no per-scale recompute needed.

Construction: supersampled coverage along the diagonal edge, solid white RGB,
shape purely in alpha; pure stdlib, 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom,
no footer.

    python3 generate_mask_minimap.py
"""

import os
import struct

SIZE = 64
# 6px chamfer at the mockup's base map width of 250 -> 6/250 = 0.024.
CORNER_FRACTION = 6 / 250
SUPERSAMPLE = 4


def coverage(px, py):
    """Fraction of this pixel inside the shape, by supersampling.

    The shape is the full square minus a triangle at the top-left and one at
    the bottom-right; top-right and bottom-left are untouched.
    """
    cut = CORNER_FRACTION * SIZE
    hits = 0

    for sy in range(SUPERSAMPLE):
        for sx in range(SUPERSAMPLE):
            x = px + (sx + 0.5) / SUPERSAMPLE
            y = py + (sy + 0.5) / SUPERSAMPLE

            if x + y < cut:
                continue                       # top-left chamfer
            if (SIZE - x) + (SIZE - y) < cut:
                continue                       # bottom-right chamfer
            hits += 1

    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def build():
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = int(round(coverage(x, y) * 255))
            # Solid white; the shape lives entirely in alpha, which is what
            # SetMaskTexture reads.
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def main():
    path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "mask_minimap.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
