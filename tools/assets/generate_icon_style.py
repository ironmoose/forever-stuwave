#!/usr/bin/env python3
"""Generates the art of the runtime icon style: nine colour ramps and one key cover.

Why: the micro keys and the class tab spell tiles draw the game's OWN icon textures, restyled live (Core/IconStyle.lua):
the icon is desaturated, an ADD copy of it lifts its brightness, one of these ramp textures is MULTIPLIED over it
(blend mode MOD) and a flat low ADD tints the shadows. No file here is derived from game art, so nothing of Blizzard's is
shipped: these are our own gradients and shapes.

iconramp_<family>.tga: 8x8, opaque, a diagonal gradient from the family's hot colour at the top left to its mid colour at the
bottom right. The families are the colour families of tools/assets/synthwave_icons.py FAMILIES (the colours are repeated
here, this script stays standalone like the others; the tests compare the two).

iconcover_key.tga: 128x128, the key's plate colour wherever the micro key's slanted shape is NOT, over key columns 1 to 33 of
34 and the full height (the bounding box of the key's inside, which is the rectangle the keys draw their icon in). A MaskTexture
does not clip on this client, so the icon is a plain rectangle and this cover, drawn over it and under the key's ring, hides
the two triangles that would stick out of the slanted key. Its shape is the key shape: the plate texture (cell_slant.tga)
minus the ring texture (deck_key_slant_outline.tga), stretched over the key's 34 x 26 design px and cut to those columns,
so the icon meets the ring's inner edge with no band of plate colour between them. The key leans / (top right to bottom left), so the solid wedges
are the top left and the bottom right. Those two textures are read from FS_ASSET_INPUT_DIR (default: the repository's Media/Textures), so they must already
exist.

Needs numpy.

    python generate_icon_style.py
"""

import os
import struct

import numpy as np

RAMP_SIZE = 8
COVER_SIZE = 128
KEY_W, KEY_H = 34, 26  # the micro key, design px (MicroBars.lua)
SCALE = 8              # samples per design px while the shape is built
GROW = 0               # the ring's line is grown by this many samples before it is cut out: 0, so the icon meets the ring's inner edge
# Key columns (design px of the 34 wide key) the cover and the icon span: the bounding box of the key's inside (the plate
# minus the ring's line, columns 1.6 to 32.4 of 34, rounded out to whole design px; the tests pin it). Media's cover and
# IconStyleData.covers follow.
COVER_RECTS = {"key": (1, 33)}
# Fraction of the way across the diagonal that is horizontal: the ramp runs mostly top to bottom.
RAMP_DIAGONAL = 0.35
COVER_COLOR = (0x0D, 0x06, 0x20)  # Theme COLOR_HUD_SCRIM's colour: the deck behind the keys

VIOLET, DEEP, PINK, CYAN = "a855f7", "4c1d95", "ff2e97", "22e0ff"
AMBER, GREEN, ICE, LAVENDER, WHITE, LIME = "ffb648", "7dff5a", "7ab8ff", "e2d4ff", "f3fbff", "d6ff7a"
# family -> (mid, hot): the middle and top of the colour ramp of synthwave_icons.FAMILIES
RAMPS = {
    "house_cyan": (PINK, CYAN),
    "house_violet": (VIOLET, PINK),
    "house_pink": (CYAN, PINK),
    "fire": (PINK, AMBER),
    "earth": (GREEN, LIME),
    "frost": (ICE, CYAN),
    "air": (CYAN, LAVENDER),
    "lightning": (CYAN, WHITE),
    "water": (ICE, CYAN),
}


def rgb(hexcolor):
    return tuple(int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))


def ramp_pixels(family):
    """RGB (0..255 ints) of the 8x8 ramp, row by row: hot at the top left, mid at the bottom right."""
    mid, hot = (np.array(rgb(c), dtype=float) for c in RAMPS[family])
    out = []
    for y in range(RAMP_SIZE):
        for x in range(RAMP_SIZE):
            u = RAMP_DIAGONAL * (x + 0.5) / RAMP_SIZE + (1 - RAMP_DIAGONAL) * (y + 0.5) / RAMP_SIZE
            out.append(tuple(int(round(c)) for c in hot * (1 - u) + mid * u))
    return out


def read_tga_alpha(path):
    """Alpha (0..1, rows top to bottom) of an uncompressed 32 bit TGA with a top-left origin."""
    data = open(path, "rb").read()
    width, height = struct.unpack_from("<HH", data, 12)
    assert data[2] == 2 and data[16] == 32 and data[17] & 0x20, f"{path}: not an uncompressed top-left 32 bit TGA"
    px = np.frombuffer(data, dtype=np.uint8, offset=18 + data[0], count=width * height * 4).reshape(height, width, 4)
    return px[..., 3].astype(float) / 255.0


def bilinear(a, out_w, out_h):
    """Resample `a` to out_w x out_h with plain bilinear taps at pixel centres (what the client does when it stretches)."""
    h, w = a.shape

    def taps(n_out, n_in):
        u = np.clip((np.arange(n_out) + 0.5) * n_in / n_out - 0.5, 0, n_in - 1)
        i0 = np.floor(u).astype(int)
        i1 = np.minimum(i0 + 1, n_in - 1)
        return i0, i1, u - i0

    y0, y1, fy = taps(out_h, h)
    x0, x1, fx = taps(out_w, w)
    rows = a[y0] * (1 - fy)[:, None] + a[y1] * fy[:, None]
    return rows[:, x0] * (1 - fx)[None, :] + rows[:, x1] * fx[None, :]


def area(a, out_w, out_h):
    """Resample `a` to out_w x out_h by area averaging (each output pixel is the mean of the samples it covers)."""
    def weights(n_out, n_in):
        m = np.zeros((n_out, n_in))
        step = n_in / n_out
        for i in range(n_out):
            lo, hi = i * step, (i + 1) * step
            for j in range(int(np.floor(lo)), min(int(np.ceil(hi)), n_in)):
                m[i, j] = max(0.0, min(hi, j + 1) - max(lo, j)) / step
        return m

    return weights(out_h, a.shape[0]) @ a @ weights(out_w, a.shape[1]).T


def key_inside(input_dir):
    """Alpha of the area inside the key's border over the key's own rectangle, SCALE samples per design px: the plate
    texture minus the ring texture's line (grown by GROW samples, none now)."""
    w, h = KEY_W * SCALE, KEY_H * SCALE
    plate = bilinear(read_tga_alpha(os.path.join(input_dir, "cell_slant.tga")), w, h)
    ring = bilinear(read_tga_alpha(os.path.join(input_dir, "deck_key_slant_outline.tga")), w, h)
    padded = np.pad(ring, GROW, mode="edge")
    grown = np.max([padded[GROW + dy:GROW + dy + h, GROW + dx:GROW + dx + w]
                    for dy in range(-GROW, GROW + 1) for dx in range(-GROW, GROW + 1)], axis=0)
    return np.clip(plate - grown, 0.0, 1.0)


def cover_alpha(inside, key):
    """COVER_SIZE square coverage (0..1) of everything outside the key shape, over the columns of the cover `key`."""
    x0, x1 = COVER_RECTS[key]
    cols = inside[:, x0 * SCALE:x1 * SCALE]
    return area(1.0 - cols, COVER_SIZE, COVER_SIZE)


def tga(width, height, bgra):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    return header + bytes(bgra)


def build(input_dir):
    """{file stem: bytes} for every texture this generator writes."""
    out = {}
    for family in RAMPS:
        px = bytearray()
        for r, g, b in ramp_pixels(family):
            px += bytes((b, g, r, 255))
        out[f"iconramp_{family}"] = tga(RAMP_SIZE, RAMP_SIZE, px)
    inside = key_inside(input_dir)
    for key in COVER_RECTS:
        px = bytearray()
        for a in cover_alpha(inside, key).reshape(-1):
            px += bytes((COVER_COLOR[2], COVER_COLOR[1], COVER_COLOR[0], int(round(float(a) * 255))))
        out[f"iconcover_{key}"] = tga(COVER_SIZE, COVER_SIZE, px)
    return out


def main():
    textures = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")
    out_dir = os.environ.get("FS_ASSET_OUTPUT_DIR", textures)
    input_dir = os.environ.get("FS_ASSET_INPUT_DIR", textures)
    for stem, data in build(input_dir).items():
        path = os.path.join(out_dir, stem + ".tga")
        with open(path, "wb") as fh:
            fh.write(data)
        print(f"wrote {path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
