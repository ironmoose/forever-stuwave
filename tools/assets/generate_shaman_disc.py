#!/usr/bin/env python3
"""Bake the Shaman Gunsight shock tracker's rune disc and Sowilo bolt.

The source is the design mockup "Shaman Shock Tracker Polish" (2026-11-07): drawShock(). Every image px of the mockup is baked as
SCALE x SCALE texels of one flat colour, full colour RGBA, no blur and no anti-aliasing; a glow is a stepped alpha ring, never a
gaussian. The disc is SR = 14 px in radius and its centre is the pixel CORNER between px (-1, -1) and (0, 0): the mockup
rasterises everything at pixel centres (x + .5, y + .5). In every 32 px cell (64 texels) that corner is the cell's middle, so a
Cooldown sweep over the cell turns about the disc's centre.

    shaman_disc.tga           256 x 256  4 x 4 cells of 64 texels (32 px), order DISC_CELLS: the disc fill (the carved violet
                                         plate), its mask (white, tinted by the module for the ready tint and the flash), the dim
                                         inner dotted ring (violet .3), the dim rim (violet .45), the lit rim (white, tinted),
                                         the eight compass notches (ink), the bolt's outline (ink .95), the empty bolt, the ready
                                         bolt, the unknown bolt (muted), a white bolt (flash, shimmer rows) and the same with
                                         the edge px left out (the row under the shimmer). The bolt's centre is the cell's middle.
    shaman_disc_halo.tga      256 x 128  two cells of 128 texels (64 px): the inner halo ring (SR + 1 .. SR + 2) and the outer
                                         one (SR + 2 .. SR + 3), white, tinted cyan by the module and breathed in 20 steps.
    shaman_disc_rim.tga       64 x 64    the lit rim, cyan .95, for the engine's clockwise refill (a Cooldown swipe, reversed).
    shaman_disc_rim_mirror.tga 64 x 64   the same ring mirrored left to right: a swipe keeps the arc from where the elapsed time
                                         ends to 12 o'clock, so the mirrored art drains from 12 o'clock clockwise (the cast).
    shaman_bolt_lit.tga       32 x 64    the charged bolt (cyan, a bright top left edge, a darker bottom right edge) stretched over
                                         a 16 x 32 px box centred on the bolt's centre, for a vertical StatusBar: the engine
                                         crops it from the tip up. The bolt's 23 rows (y -12 to 10) sit on box rows 4 to 26.

    python3 tools/assets/generate_shaman_disc.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2                                  # texels per image px: every px is baked as SCALE x SCALE texels of one flat colour
SR = 14                                    # the disc's radius
CELL = 64                                  # texels of a disc cell (32 px)
CENTER = 16                                # px of the disc's centre corner inside a cell
DISC_CELLS = ["disc", "mask", "dots", "rimDim", "rimLit", "notches", "boltOutline", "boltEmpty", "boltReady", "boltMuted",
              "boltWhite", "boltInner"]
HALO_CELL = 128                            # texels (64 px)
HALO_CENTER = 32
BOLT_BOX = (-8, -16, 16, 32)               # the StatusBar box of shaman_bolt_lit, from the bolt's centre: x, y, w, h in px
BOLT_FILE = (32, 64)

INK, VIOLET, CYAN, WHITE, MUTED = "#0a0416", "#a855f7", "#22e0ff", "#f3fbff", "#9d93c4"
BOLT_PTS = [(2, -12), (-6, 2), (-1, 2), (-3, 12), (6, -3), (1, -3), (5, -12)]
NOTCH = [(0, -SR + 1), (0, -SR), (-1, SR - 1), (-1, SR - 2), (-SR + 1, -1), (-SR, -1), (SR - 1, 0), (SR - 2, 0)]


def jsround(v: float) -> int:
    """JavaScript's Math.round (halves go up), which the mockup uses."""
    return math.floor(v + 0.5)


def rgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def mix(a: str, b: str, t: float):
    """The mockup's mix(): channels rounded half up, as a colour tuple."""
    p, q = rgb(a) if isinstance(a, str) else a, rgb(b) if isinstance(b, str) else b
    return tuple(jsround(p[i] + (q[i] - p[i]) * t) for i in range(3))


def col(c, a: float = 1.0):
    c = rgb(c) if isinstance(c, str) else c
    return (c[0], c[1], c[2], a)


class Layer:
    """A sparse layer of px, composited the way the mockup's canvas fillRect does (source over)."""

    def __init__(self):
        self.p: dict[tuple[int, int], tuple[float, float, float, float]] = {}

    def paint(self, x: int, y: int, c) -> None:
        r, g, b, a = c
        if a <= 0:
            return
        old = self.p.get((x, y))
        if old is None or a >= 1.0:
            self.p[(x, y)] = (r, g, b, min(a, 1.0))
            return
        orr, og, ob, oa = old
        na = a + oa * (1 - a)
        self.p[(x, y)] = ((r * a + orr * oa * (1 - a)) / na, (g * a + og * oa * (1 - a)) / na,
                          (b * a + ob * oa * (1 - a)) / na, na)

    def mirrored(self) -> "Layer":
        """Left to right about the centre corner: px x -> -1 - x."""
        out = Layer()
        for (x, y), c in self.p.items():
            out.p[(-1 - x, y)] = c
        return out

    def recolour(self, c) -> "Layer":
        out = Layer()
        for k, (_, _, _, a) in self.p.items():
            out.p[k] = (c[0], c[1], c[2], a * c[3])
        return out


class Atlas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)

    def blit(self, layer: Layer, ox: int, oy: int, window=None, name="layer") -> None:
        for (x, y), (r, g, b, a) in layer.p.items():
            sx, sy = x + ox, y + oy
            if window is not None:
                x0, y0, x1, y1 = window
                if not (x0 <= sx < x1 and y0 <= sy < y1):
                    raise ValueError(f"{name}: px ({x}, {y}) lands at ({sx}, {sy}) outside its cell {window}")
            if not (0 <= sx * SCALE < self.w and 0 <= sy * SCALE < self.h):
                raise ValueError(f"{name}: px ({x}, {y}) is outside the file")
            rgba = bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
            for dy in range(SCALE):
                for dx in range(SCALE):
                    i = ((sy * SCALE + dy) * self.w + sx * SCALE + dx) * 4
                    self.px[i:i + 4] = rgba


def cell_rect(index: int, cols: int, cell: int):
    """The px window (x0, y0, x1, y1) of cell `index` of a file whose cells are `cell` texels square, `cols` across."""
    s = cell // SCALE
    return ((index % cols) * s, (index // cols) * s, (index % cols) * s + s, (index // cols) * s + s)


def stretched(layer: Layer, box, w: int, h: int) -> Atlas:
    """The px inside box (x0, y0, bw, bh) stretched, nearest, over the whole w x h file, so a StatusBar's crop of the texture
    matches the art. Texel (tx, ty) shows px (x0 + tx * bw // w, y0 + ty * bh // h)."""
    x0, y0, bw, bh = box
    atlas = Atlas(w, h)
    for ty in range(h):
        for tx in range(w):
            c = layer.p.get((x0 + tx * bw // w, y0 + ty * bh // h))
            if c:
                r, g, b, a = c
                atlas.px[(ty * w + tx) * 4:(ty * w + tx) * 4 + 4] = bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
    return atlas


def write_tga(path: str, atlas: Atlas) -> None:
    rows = bytearray()
    for i in range(0, len(atlas.px), 4):
        r, g, b, a = atlas.px[i:i + 4]
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, atlas.w, atlas.h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({atlas.w}x{atlas.h}, {os.path.getsize(path)} bytes)")


def out_dir() -> str:
    return os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))


# ---------------------------------------------------------------------------------------------------------------------
# the mockup's shapes
# ---------------------------------------------------------------------------------------------------------------------

def disc_px():
    """(x, y, d) of the plate: every px whose centre is within SR - 1.8 of the centre corner."""
    out = []
    for y in range(-SR, SR):
        for x in range(-SR, SR):
            d = math.hypot(x + 0.5, y + 0.5)
            if d <= SR - 1.8:
                out.append((x, y, d))
    return out


def ring_px():
    """(x, y, d) of the rim, the band from SR - 1.8 (exclusive) to SR."""
    out = []
    for y in range(-SR, SR):
        for x in range(-SR, SR):
            d = math.hypot(x + 0.5, y + 0.5)
            if SR - 1.8 < d <= SR:
                out.append((x, y, d))
    return out


def halo_px(r0: float, r1: float):
    out = []
    for y in range(-int(r1) - 2, int(r1) + 2):
        for x in range(-int(r1) - 2, int(r1) + 2):
            d = math.hypot(x + 0.5, y + 0.5)
            if r0 < d <= r1:
                out.append((x, y))
    return out


def in_poly(poly, x: float, y: float) -> bool:
    c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[i], poly[j]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            c = not c
        j = i
    return c


def bolt_shape():
    """(px set, list of (x, y, edge, hi, lo), outline px) of the Sowilo bolt, rasterised at pixel centres."""
    m = {(x, y) for y in range(-13, 14) for x in range(-8, 9) if in_poly(BOLT_PTS, x + 0.5, y + 0.5)}
    px = []
    for (x, y) in sorted(m, key=lambda q: (q[1], q[0])):
        edge = ((x + 1, y) not in m) or ((x - 1, y) not in m) or ((x, y + 1) not in m) or ((x, y - 1) not in m)
        px.append((x, y, edge, (x - 1, y - 1) not in m, (x + 1, y + 1) not in m))
    out = set()
    for (x, y) in m:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, y + dy) not in m:
                out.add((x + dx, y + dy))
    return m, px, sorted(out)


BOLT_MASK, BOLT_PX, BOLT_OUT = bolt_shape()


def charged(edge: bool, hi: bool, lo: bool):
    if hi:
        return mix(CYAN, WHITE, 0.75)
    if lo:
        return mix(CYAN, VIOLET, 0.5)
    if edge:
        return mix(CYAN, WHITE, 0.25)
    return rgb(CYAN)


def layer_disc():
    L = Layer()
    for x, y, d in disc_px():
        L.paint(x, y, col(mix(INK, VIOLET, 0.12 + (0.05 if d > SR - 4 else 0))))
    return L


def layer_mask():
    L = Layer()
    for x, y, _ in disc_px():
        L.paint(x, y, (255, 255, 255, 1.0))
    return L


def layer_dots():
    L = Layer()
    for i in range(16):
        a = i / 16 * math.pi * 2
        L.paint(jsround(math.cos(a) * (SR - 4) - 0.5), jsround(math.sin(a) * (SR - 4) - 0.5), col(VIOLET, 0.3))
    return L


def layer_rim_dim():
    L = Layer()
    for x, y, _ in ring_px():
        L.paint(x, y, col(VIOLET, 0.45))
    return L


def layer_rim_white():
    L = Layer()
    for x, y, _ in ring_px():
        L.paint(x, y, (255, 255, 255, 1.0))
    return L


def layer_rim_cyan():
    L = Layer()
    for x, y, _ in ring_px():
        L.paint(x, y, col(CYAN, 0.95))
    return L


def layer_notches():
    L = Layer()
    for x, y in NOTCH:
        L.paint(x, y, col(INK))
    return L


def layer_bolt_outline():
    L = Layer()
    for x, y in BOLT_OUT:
        L.paint(x, y, col(INK, 0.95))
    return L


def layer_bolt_empty():
    L = Layer()
    for x, y, edge, _, _ in BOLT_PX:
        L.paint(x, y, col(mix(VIOLET, INK, 0.15) if edge else mix(INK, VIOLET, 0.22)))
    return L


def layer_bolt_charged():
    L = Layer()
    for x, y, edge, hi, lo in BOLT_PX:
        L.paint(x, y, col(charged(edge, hi, lo)))
    return L


def layer_bolt_ready():
    L = Layer()
    for x, y, edge, hi, lo in BOLT_PX:
        c = charged(edge, hi, lo)
        if not edge and not lo:
            c = mix(c, WHITE, 0.45)
        L.paint(x, y, col(c))
    return L


def layer_bolt_muted():
    L = Layer()
    for x, y, edge, _, _ in BOLT_PX:
        L.paint(x, y, col(MUTED if edge else mix(INK, MUTED, 0.15)))
    return L


def layer_bolt_white(inner_only: bool = False):
    L = Layer()
    for x, y, edge, _, _ in BOLT_PX:
        if inner_only and edge:
            continue
        L.paint(x, y, (255, 255, 255, 1.0))
    return L


def disc_atlas() -> Atlas:
    layers = {
        "disc": layer_disc(), "mask": layer_mask(), "dots": layer_dots(), "rimDim": layer_rim_dim(), "rimLit": layer_rim_white(),
        "notches": layer_notches(), "boltOutline": layer_bolt_outline(), "boltEmpty": layer_bolt_empty(),
        "boltReady": layer_bolt_ready(), "boltMuted": layer_bolt_muted(), "boltWhite": layer_bolt_white(),
        "boltInner": layer_bolt_white(True),
    }
    atlas = Atlas(256, 256)
    for i, name in enumerate(DISC_CELLS):
        cx, cy, _, _ = cell_rect(i, 4, CELL)
        atlas.blit(layers[name], cx + CENTER, cy + CENTER, cell_rect(i, 4, CELL), name)
    return atlas


def halo_atlas() -> Atlas:
    atlas = Atlas(256, 128)
    for i, (r0, r1) in enumerate(((SR + 1, SR + 2), (SR + 2, SR + 3))):
        L = Layer()
        for x, y in halo_px(r0, r1):
            L.paint(x, y, (255, 255, 255, 1.0))
        cx, cy, _, _ = cell_rect(i, 2, HALO_CELL)
        atlas.blit(L, cx + HALO_CENTER, cy + HALO_CENTER, cell_rect(i, 2, HALO_CELL), f"halo{i}")
    return atlas


def single(layer: Layer, size: int = 64) -> Atlas:
    atlas = Atlas(size, size)
    atlas.blit(layer, CENTER, CENTER, (0, 0, size // SCALE, size // SCALE), "ring")
    return atlas


def main() -> None:
    here = out_dir()
    write_tga(os.path.join(here, "shaman_disc.tga"), disc_atlas())
    write_tga(os.path.join(here, "shaman_disc_halo.tga"), halo_atlas())
    write_tga(os.path.join(here, "shaman_disc_rim.tga"), single(layer_rim_cyan()))
    write_tga(os.path.join(here, "shaman_disc_rim_mirror.tga"), single(layer_rim_cyan().mirrored()))
    write_tga(os.path.join(here, "shaman_bolt_lit.tga"), stretched(layer_bolt_charged(), BOLT_BOX, *BOLT_FILE))


if __name__ == "__main__":
    main()
