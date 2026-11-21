"""The addon list icon (`## IconTexture` in forever-stuwave.toc): the pixel STU logo, 64 x 64.

Source: addon_icon_art/addon_icon.png, our own pixel STU logo (the same mark as the CurseForge project logo) with its
backdrop cleared to transparent. This writes it as an uncompressed 32 bit TGA, top-left origin.

    python generate_addon_icon.py
"""
import os
import struct

from PIL import Image

SIZE = 64


def main():
    art = os.path.join(os.environ.get("FS_ASSETS_DIR", os.path.dirname(os.path.abspath(__file__))), "addon_icon_art")
    im = Image.open(os.path.join(art, "addon_icon.png")).convert("RGBA")
    assert im.size == (SIZE, SIZE), im.size
    rows = bytearray()
    for r, g, b, a in im.get_flattened_data():
        rows += bytes((b, g, r, a))
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "addon_icon.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
