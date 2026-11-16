#!/usr/bin/env python3
"""Generates the nameplate combo pip art (NameplateCombo.lua).

    combo_pip_rest.tga   16 x 16  the unlit pip: a hard edged diamond, violet rim on a dark well (drawn as is, never tinted)
    combo_pip_lit.tga    16 x 16  the lit pip as a white mask (tinted pink, or gold at five): a full bright rim, a shaded face
                                  lighter to the top left, and a two px glint
    combo_pip_glow.tga   32 x 32  a soft diamond glow (white, drawn ADD under a lit pip at twice its size)

The pips are drawn at one texel per physical px, so every edge is a whole pixel; only the glow is soft.
Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python3 tools/assets/generate_combo_pips.py      (FS_ASSET_OUTPUT_DIR overrides the .tga directory)
"""

import os
import struct

PIP = 16
GLOW = 32


def hexrgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def inside(x, y):
    """The diamond: row y spans min(y, 15 - y) + 1 px either side of the centre line."""
    if not (0 <= x < PIP and 0 <= y < PIP):
        return False
    w = min(y, PIP - 1 - y) + 1
    return PIP // 2 - w <= x < PIP // 2 + w


def ring(x, y):
    """How far in from the edge: 0 = the rim, 1 = just inside it, 2 = the face."""
    if not inside(x, y):
        return None
    for d in (0, 1):
        r = d + 1
        if any(not inside(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if abs(dx) + abs(dy) <= r):
            return d
    return 2


def rest():
    rim, inner, well = hexrgb("#8a5cf0"), hexrgb("#3b2468"), hexrgb("#1a1025")
    px = []
    for y in range(PIP):
        for x in range(PIP):
            d = ring(x, y)
            if d is None:
                px.append((0, 0, 0, 0))
            elif d == 0:
                px.append((*rim, 255))
            elif d == 1:
                px.append((*inner, 240))
            else:
                px.append((*well, 225))
    return px


GLINT = {(6, 3), (5, 4), (6, 4), (4, 5)}


def lit():
    px = []
    for y in range(PIP):
        for x in range(PIP):
            d = ring(x, y)
            if d is None:
                px.append((0, 0, 0, 0))
                continue
            if d == 0 or (x, y) in GLINT:
                v = 255
            elif d == 1:
                v = 225
            else:
                # lighter to the top left: x + y runs about 4 to 26 across the face
                v = int(round(205 - (x + y - 4) * 55 / 22))
            px.append((v, v, v, 255))
    return px


def glow():
    c = GLOW / 2.0
    px = []
    for y in range(GLOW):
        for x in range(GLOW):
            d = (abs(x + 0.5 - c) + abs(y + 0.5 - c)) / c
            a = max(0.0, 1.0 - d) ** 1.7
            px.append((255, 255, 255, int(round(a * 230))))
    return px


def write(name, size, px, out):
    path = os.path.join(out, name)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(bytes(b for r, g, bl, a in px for b in (bl, g, r, a)))
    print(f"wrote {path} ({size}x{size})")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(here, "..", "..", "forever-stuwave", "Media", "Textures"))
    write("combo_pip_rest.tga", PIP, rest(), out)
    write("combo_pip_lit.tga", PIP, lit(), out)
    write("combo_pip_glow.tga", GLOW, glow(), out)


if __name__ == "__main__":
    main()
