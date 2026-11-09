#!/usr/bin/env python3
"""Bake the Shaman Gunsight Fire Nova flame disc.

The source is the design mockup "Shaman Nova Tracker" (2026-11-08), form A: drawSun() and the constants above it. It is the twin of
generate_shaman_disc.py's rune disc, smaller (NR = 12) and in fire: every image px of the mockup is baked as SCALE x SCALE texels
of one flat colour, full colour RGBA, no blur and no anti-aliasing; a glow is a stepped alpha ring. The disc's centre is the pixel
CORNER between px (-1, -1) and (0, 0): the mockup rasterises everything at pixel centres (x + .5, y + .5). In every 32 px cell
(64 texels) that corner is the cell's middle, so a Cooldown sweep over the cell turns about the disc's centre.

    nova_disc.tga             256 x 256  4 x 4 cells of 64 texels (32 px), order DISC_CELLS: the plate (the carved violet disc),
                                         its mask (white, tinted by the module for the ready tint and the flash), the dim rim
                                         (violet .45), the lit rim (white, tinted), the eight compass notches (ink), the empty
                                         flame, the unknown flame (muted), the ready flame, the three flicker overlays (amber px
                                         on the flame's upper rows, one per phase of the module's three step cycle), the white
                                         hot flame (the flash, and the row under the fill's edge) and the two halo rings
                                         (NR + 1 .. NR + 2 and NR + 2 .. NR + 3, white, tinted by the module and breathed in 20
                                         steps). The last two cells are spare. The flame's centre is the cell's middle.
    nova_disc_rim.tga         64 x 64    the lit rim in ember red to amber with a slight turn to hot white (the mockup's
                                         fireMix(.25 + f * .5) by each px's own angle f from 12 o'clock, alpha .95), for the
                                         engine's clockwise refill (a Cooldown swipe, reversed).
    nova_disc_rim_mirror.tga  64 x 64    the same art mirrored left to right: a swipe keeps the arc from where the elapsed time
                                         ends to 12 o'clock, so the whole 0.3 s drain after a cast plays as the mirror image of the
                                         mockup's, colours included.
    nova_flame_lit.tga        32 x 32    the charged flame (its rows coloured by height, the core px warm white) stretched over a
                                         16 x 16 px box centred on the flame's centre, for a vertical StatusBar: the engine crops it
                                         from the base up. The flame's 13 rows (y -7 to 5) sit on box rows 1 to 13: one px of
                                         padding above them, two below.

    python3 tools/assets/generate_nova_disc.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2                                  # texels per image px: every px is baked as SCALE x SCALE texels of one flat colour
NR = 12                                    # the disc's radius
CELL = 64                                  # texels of a disc cell (32 px)
CENTER = 16                                # px of the disc's centre corner inside a cell
DISC_CELLS = ["disc", "mask", "rimDim", "rimLit", "notches", "flameEmpty", "flameMuted", "flameReady", "flick0", "flick1",
              "flick2", "flameWhite", "halo1", "halo2"]
FLAME_BOX = (-8, -8, 16, 16)               # the StatusBar box of nova_flame_lit, from the flame's centre: x, y, w, h in px
FLAME_FILE = (32, 32)

INK, VIOLET, MUTED = "#0a0416", "#a855f7", "#9d93c4"
FIRE, AMBER, HOT = "#ff5a3c", "#ffb648", "#fff1d0"
NOTCH = [(0, -NR), (0, -NR + 1), (-1, NR - 1), (-1, NR - 2), (-NR, -1), (-NR + 1, -1), (NR - 1, 0), (NR - 2, 0)]
FLAME_ROWS = [
    "....#.......",
    "....##......",
    "...###...#..",
    "...####..#..",
    "..#####.##..",
    "..######.##.",
    ".###+####.#.",
    ".###++#####.",
    ".##+++####..",
    ".##++++###..",
    ".##++++###..",
    "..##+++##...",
    "...#####....",
]


def jsround(v: float) -> int:
    """JavaScript's Math.round (halves go up), which the mockup uses."""
    return math.floor(v + 0.5)


def rgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def mix(a, b, t: float):
    """The mockup's mix(): channels rounded half up, as a colour tuple."""
    p, q = rgb(a) if isinstance(a, str) else a, rgb(b) if isinstance(b, str) else b
    return tuple(jsround(p[i] + (q[i] - p[i]) * t) for i in range(3))


def col(c, a: float = 1.0):
    c = rgb(c) if isinstance(c, str) else c
    return (c[0], c[1], c[2], a)


def fire_mix(t: float):
    """The mockup's fireMix: ember red to amber to hot white."""
    return mix(FIRE, AMBER, t * 2) if t < 0.5 else mix(AMBER, HOT, (t - 0.5) * 2)


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
    """(x, y, d) of the plate: every px whose centre is within NR - 1.8 of the centre corner."""
    out = []
    for y in range(-NR, NR):
        for x in range(-NR, NR):
            d = math.hypot(x + 0.5, y + 0.5)
            if d <= NR - 1.8:
                out.append((x, y, d))
    return out


def ring_px(r0: float = NR - 1.8, r1: float = NR):
    """(x, y, f, d) of the band r0 (exclusive) to r1, f the px's share of a turn clockwise from 12 o'clock (the mockup's ringPx)."""
    out = []
    for y in range(-int(r1) - 1, int(r1) + 1):
        for x in range(-int(r1) - 1, int(r1) + 1):
            d = math.hypot(x + 0.5, y + 0.5)
            if r0 < d <= r1:
                ang = math.atan2(x + 0.5, -(y + 0.5))
                if ang < 0:
                    ang += math.pi * 2
                out.append((x, y, ang / (math.pi * 2), d))
    return out


def flame_px():
    """(x, y, core, row_f) of the flame: row_f is 0 on the base row and 1 on the top row (the mockup's FLAME)."""
    h = len(FLAME_ROWS)
    out = []
    for y, row in enumerate(FLAME_ROWS):
        for x, ch in enumerate(row):
            if ch != ".":
                out.append((x - 6, y - 7, ch == "+", (h - 1 - y) / (h - 1)))
    return out


FLAME_PX = flame_px()


def layer_disc():
    L = Layer()
    for x, y, d in disc_px():
        L.paint(x, y, col(mix(INK, VIOLET, 0.12 + (0.05 if d > NR - 4 else 0))))
    return L


def layer_mask():
    L = Layer()
    for x, y, _ in disc_px():
        L.paint(x, y, (255, 255, 255, 1.0))
    return L


def layer_rim_dim():
    L = Layer()
    for x, y, _, _ in ring_px():
        L.paint(x, y, col(VIOLET, 0.45))
    return L


def layer_rim_white():
    L = Layer()
    for x, y, _, _ in ring_px():
        L.paint(x, y, (255, 255, 255, 1.0))
    return L


def layer_rim_fire():
    L = Layer()
    for x, y, f, _ in ring_px():
        L.paint(x, y, col(fire_mix(0.25 + f * 0.5), 0.95))
    return L


def layer_notches():
    L = Layer()
    for x, y in NOTCH:
        L.paint(x, y, col(INK))
    return L


def layer_flame_empty():
    L = Layer()
    for x, y, core, _ in FLAME_PX:
        L.paint(x, y, col(mix(INK, VIOLET, 0.3) if core else mix(INK, VIOLET, 0.5)))
    return L


def layer_flame_muted():
    L = Layer()
    for x, y, core, _ in FLAME_PX:
        L.paint(x, y, col(mix(INK, MUTED, 0.4) if core else MUTED))
    return L


def layer_flame_ready():
    L = Layer()
    for x, y, core, row_f in FLAME_PX:
        L.paint(x, y, col(HOT if core else fire_mix(0.05 + row_f * 0.55)))
    return L


def layer_flame_flicker(phase: int):
    """The amber px of the ready flame's upper rows that the mockup swaps in for one phase of floor(t * 8) % 3."""
    L = Layer()
    for x, y, core, row_f in FLAME_PX:
        if not core and row_f > 0.7 and (x + y + phase) % 3 == 0:
            L.paint(x, y, col(AMBER))
    return L


def layer_flame_white():
    L = Layer()
    for x, y, _, _ in FLAME_PX:
        L.paint(x, y, col(HOT))
    return L


def layer_flame_charged():
    L = Layer()
    for x, y, core, row_f in FLAME_PX:
        L.paint(x, y, col(mix(AMBER, HOT, 0.5) if core else fire_mix(0.05 + row_f * 0.55)))
    return L


def layer_halo(r0: float, r1: float):
    L = Layer()
    for y in range(-int(r1) - 2, int(r1) + 2):
        for x in range(-int(r1) - 2, int(r1) + 2):
            if r0 < math.hypot(x + 0.5, y + 0.5) <= r1:
                L.paint(x, y, (255, 255, 255, 1.0))
    return L


def disc_atlas() -> Atlas:
    layers = {
        "disc": layer_disc(), "mask": layer_mask(), "rimDim": layer_rim_dim(), "rimLit": layer_rim_white(),
        "notches": layer_notches(), "flameEmpty": layer_flame_empty(), "flameMuted": layer_flame_muted(),
        "flameReady": layer_flame_ready(), "flick0": layer_flame_flicker(0), "flick1": layer_flame_flicker(1),
        "flick2": layer_flame_flicker(2), "flameWhite": layer_flame_white(), "halo1": layer_halo(NR + 1, NR + 2),
        "halo2": layer_halo(NR + 2, NR + 3),
    }
    atlas = Atlas(256, 256)
    for i, name in enumerate(DISC_CELLS):
        cx, cy, _, _ = cell_rect(i, 4, CELL)
        atlas.blit(layers[name], cx + CENTER, cy + CENTER, cell_rect(i, 4, CELL), name)
    return atlas


def single(layer: Layer, size: int = 64) -> Atlas:
    atlas = Atlas(size, size)
    atlas.blit(layer, CENTER, CENTER, (0, 0, size // SCALE, size // SCALE), "ring")
    return atlas


def main() -> None:
    here = out_dir()
    write_tga(os.path.join(here, "nova_disc.tga"), disc_atlas())
    write_tga(os.path.join(here, "nova_disc_rim.tga"), single(layer_rim_fire()))
    write_tga(os.path.join(here, "nova_disc_rim_mirror.tga"), single(layer_rim_fire().mirrored()))
    write_tga(os.path.join(here, "nova_flame_lit.tga"), stretched(layer_flame_charged(), FLAME_BOX, *FLAME_FILE))


if __name__ == "__main__":
    main()
