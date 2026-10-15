#!/usr/bin/env python3
"""Generates the art of the Shaman Gunsight totem poles that a plain solid texture cannot draw.

Reference: the design mockup, Concept A "Totem Poles", the functions
`pole(k, s, gy, st, an)` and `head(el, cx, ty, w, c, mode)`. Three kinds of piece, each at two widths (the wide Fire pole
and the three narrow ones), all white RGB with the shape in alpha so Lua tints them with SetVertexColor:

    pole_block_<w>   one block of the pole: `rect(x + ins, by, w - 2 * ins, 5, col, op)` plus the dark line
                     `rect(x + ins + 3, by + 2, w - 2 * ins - 6, 1, '#0a0416', .45)` drawn over it. The line is baked into the block
                     (a 45% blend of the near black over white, in RGB) so a tint carries it; w is the block width, 40 or 26.
    pole_mold_<w>    the mold, the dashed stroke of `rect(x + ins, gy - 48, w - 2 * ins, 47, fill .05, stroke violet, dash '2 3')`:
                     a 1 px stroke dashed 2 on, 3 off, clockwise from the top left corner. Only the stroke is baked; the faint fill is
                     a solid texture. w is the mold width, 40 or 26, the height is 47.
    pole_dash_<w>    the dashed stroke of the DROP / FAR head, `head(.., mode 'down' | 'far')`: the chamfered head polygon
                     `ch(hx, hy, w, 9, 2)` (top left and bottom right cut by 2), stroke 1.3, dash '3 2'. w is the head width, 48 or 30.

Each piece is drawn at 4 texels per image px. The mold and the dash get a 1 image px margin on every side so the outer half of
the stroke is not clipped; Lua places them 1 px up and left of the shape. WoW refuses a non power of two file texture, so the
art sits in the top left of the next power of two canvas and Lua crops it with SetTexCoord. Pure stdlib. Output per file: 18 byte
header, image type 2, descriptor 0x28 (top left origin, 8 alpha bits), BGRA top to bottom.

    python3 generate_totem_pole.py
"""

import math
import os
import struct

SCALE = 4                       # texels per image px
PAD = 1                         # image px margin around a stroked piece
SUPER = 3                       # sub samples per texel side
BLOCK_H = 5                     # BH in the mockup
MOLD_H = 47                     # NB * BP - 1
HEAD_H, HEAD_CUT = 9, 2
BLOCK_LINE = (3, 2, 1)          # inset x, y offset, height in image px
LINE_RGB = (0.572, 0.557, 0.592)   # white 55% + #0a0416 45%
MOLD_STROKE, MOLD_DASH = 1.0, (2.0, 3.0)
HEAD_STROKE, HEAD_DASH = 1.3, (3.0, 2.0)

# name -> (kind, w image px, h image px); the module keeps the same list (GunsightShaman.lua, TEX)
PIECES = {
    "pole_block_40": ("block", 40, BLOCK_H),
    "pole_block_26": ("block", 26, BLOCK_H),
    "pole_mold_40": ("mold", 40, MOLD_H),
    "pole_mold_26": ("mold", 26, MOLD_H),
    "pole_dash_48": ("dash", 48, HEAD_H),
    "pole_dash_30": ("dash", 30, HEAD_H),
}


def pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


def art_size(kind, w, h):
    """Art size in texels."""
    extra = 0 if kind == "block" else 2 * PAD
    return (w + extra) * SCALE, (h + extra) * SCALE


def outline(kind, w, h):
    """The closed polyline of a stroked piece in image px, margin included."""
    if kind == "mold":
        pts = [(0, 0), (w, 0), (w, h), (0, h), (0, 0)]
    else:
        c = HEAD_CUT
        pts = [(c, 0), (w, 0), (w, h - c), (w - c, h), (0, h), (0, c), (c, 0)]
    return [(x + PAD, y + PAD) for x, y in pts]


def stroke_coverage(poly, stroke, dash, px, py):
    """1 when (px, py) lies on a dash of the stroked polyline, else 0."""
    best, best_pos, run = None, 0.0, 0.0
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (length * length)))
        d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if best is None or d < best:
            best, best_pos = d, run + t * length
        run += length
    if best is None or best > stroke / 2:
        return 0
    return 1 if best_pos % (dash[0] + dash[1]) < dash[0] else 0


def raster(kind, w, h):
    """Rows of (r, g, b, a) bytes for the art area, as a list of bytearrays."""
    aw, ah = art_size(kind, w, h)
    rows = []
    poly = outline(kind, w, h) if kind != "block" else None
    stroke, dash = (MOLD_STROKE, MOLD_DASH) if kind == "mold" else (HEAD_STROKE, HEAD_DASH)
    n = SUPER * SUPER
    for y in range(ah):
        row = bytearray()
        for x in range(aw):
            if kind == "block":
                ix, iy = x / SCALE, y / SCALE
                on_line = (BLOCK_LINE[0] <= ix < w - BLOCK_LINE[0]
                           and BLOCK_LINE[1] <= iy < BLOCK_LINE[1] + BLOCK_LINE[2])
                if on_line:
                    row += bytes(round(c * 255) for c in LINE_RGB) + b"\xff"
                else:
                    row += b"\xff\xff\xff\xff"
                continue
            hit = 0
            for sy in range(SUPER):
                py = (y + (sy + 0.5) / SUPER) / SCALE
                for sx in range(SUPER):
                    px = (x + (sx + 0.5) / SUPER) / SCALE
                    hit += stroke_coverage(poly, stroke, dash, px, py)
            row += b"\xff\xff\xff" + bytes((round(hit / n * 255),))
        rows.append(row)
    return rows


def write_tga(path, rows, art_w, art_h):
    cw, ch = pow2(art_w), pow2(art_h)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, cw, ch, 32, 0x28)
    blank = b"\xff\xff\xff\x00"           # BGRA, white and clear
    with open(path, "wb") as fh:
        fh.write(header)
        for y in range(ch):
            if y < art_h:
                body = bytes(rows[y])
                # the file is BGRA
                bgra = bytearray()
                for i in range(0, len(body), 4):
                    bgra += bytes((body[i + 2], body[i + 1], body[i], body[i + 3]))
                fh.write(bytes(bgra) + blank * (cw - art_w))
            else:
                fh.write(blank * cw)
    return cw, ch


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    for name, (kind, w, h) in PIECES.items():
        aw, ah = art_size(kind, w, h)
        path = os.path.join(here, f"{name}.tga")
        cw, ch = write_tga(path, raster(kind, w, h), aw, ah)
        print(f"wrote {path} (art {aw}x{ah} in {cw}x{ch}, {os.path.getsize(path)} bytes)")
