#!/usr/bin/env python3
"""Bake the Mage Gunsight module's Fire look: the living flame tongue with the Kaun rune cut out of its base, the stack embers
and the 30 s ring.

The source is the design mockup (Mage Gunsight Module, 2026-11-07): drawFire. Every sprite px is baked as SCALE x SCALE texels of
one flat colour. Full colour RGBA, except the rune and its molten rim, which are white masks the game tints.

The flame sways on a 12 frame loop (the mockup runs it at 12 frames a second): the body sway is one cycle and two cycles of the
mockup's sine terms, where the mockup's own phase steps are about 5 percent and 20 percent off a whole cycle. The flame is baked
standing still (no bob; the game lifts the whole picture by the bob row) and with no Scorch swell.

    mage_fire_flame.tga      1024 x 512  16 x 5 cells of 64 x 80 texels (32 x 40 sprite px): the flame for 0 to 5 stacks, 12
                                         frames each, cell index stacks * FLAME_FRAMES + frame. The flame's base line is
                                         sprite px (FLAME_OX, FLAME_OY) + (0, FLAME_BASE) of the cell, the piece centre is
                                         (FLAME_OX, FLAME_OY).
    mage_fire.tga             512 x 256  4 x 2 cells of 128 x 128 texels (64 sprite px), order FIRE_CELLS: the dark ring, the
                                         Kaun rune (white mask), its thin molten rim (white mask), a lit stack ember (its centre
                                         px left to the game) and an empty ember socket. The piece centre is sprite px
                                         (CENTER, CENTER) of the cell.
    mage_fire_ring.tga        128 x 128  the lit ring, baked mirrored (a Cooldown swipe shows the arc still to come).
    mage_fire_ring_low.tga    128 x 128  the same arc in one amber colour for the last seconds.

    python3 tools/assets/generate_mage_fire.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2                          # texels per sprite px: every sprite px is baked as SCALE x SCALE texels of one flat colour


def jsround(v: float) -> int:
    """JavaScript's Math.round (halves go up), which the mockup uses."""
    return math.floor(v + 0.5)


def col(h: str, a: float = 1.0):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)


def in_disc(x, y, r):
    return x * x + y * y <= r * r + r * 0.8


class Layer:
    """A sparse layer of sprite px, composited the way the mockup's canvas fillRect does (source over)."""

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

    def rect(self, x, y, w, h, c) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.paint(xx, yy, c)

    def over(self, other: "Layer", dx: int = 0, dy: int = 0) -> None:
        for (x, y), c in other.p.items():
            self.paint(x + dx, y + dy, c)

    def mirrored(self) -> "Layer":
        out = Layer()
        for (x, y), c in self.p.items():
            out.p[(-x, y)] = c
        return out

    def recolour(self, c) -> "Layer":
        """The same coverage in one flat colour (alpha scaled by this layer's), for a mask that is tinted in game."""
        out = Layer()
        for k, (_, _, _, a) in self.p.items():
            out.p[k] = (c[0], c[1], c[2], a * c[3])
        return out

    def bounds(self):
        xs = [k[0] for k in self.p]
        ys = [k[1] for k in self.p]
        return min(xs), min(ys), max(xs), max(ys)


class Atlas:
    """A w x h texel file. blit() lays a layer into a cell: (ox, oy) is the sprite px of the layer's (0, 0) in the file, and the
    cell window (cx, cy, cw, ch) in file sprite px must contain every px (a px outside it is a bug, not a clip)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)

    def blit(self, layer: Layer, ox: int, oy: int, window=None, name="layer") -> None:
        for (x, y), (r, g, b, a) in layer.p.items():
            sx, sy = x + ox, y + oy
            if window is not None:
                x0, y0, x1, y1 = window
                if not (x0 <= sx < x1 and y0 <= sy < y1):
                    raise ValueError(f"{name}: sprite px ({x}, {y}) lands at ({sx}, {sy}) outside its cell {window}")
            if not (0 <= sx * SCALE < self.w and 0 <= sy * SCALE < self.h):
                raise ValueError(f"{name}: sprite px ({x}, {y}) is outside the file")
            rgba = (int(round(r)), int(round(g)), int(round(b)), int(round(a * 255)))
            for dy in range(SCALE):
                for dx in range(SCALE):
                    i = ((sy * SCALE + dy) * self.w + sx * SCALE + dx) * 4
                    self.px[i:i + 4] = bytes(rgba)


def cell_rect(index: int, cols: int, cw: int, ch: int):
    """The sprite px window (x0, y0, x1, y1) of cell `index` of a file whose cells are cw x ch texels, `cols` across."""
    sw, sh = cw // SCALE, ch // SCALE
    return ((index % cols) * sw, (index // cols) * sh, (index % cols) * sw + sw, (index // cols) * sh + sh)


def cell_window(index: int, cols: int, cell: int):
    return cell_rect(index, cols, cell, cell)


def stretched(layer: Layer, box, w: int, h: int) -> Atlas:
    """The sprites inside box (x0, y0, bw, bh) stretched, nearest, over the whole w x h file, so a StatusBar's crop of the
    texture matches the art. Texel (tx, ty) shows sprite px (x0 + tx * bw // w, y0 + ty * bh // h)."""
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
# layout
# ---------------------------------------------------------------------------------------------------------------------
CENTER = 32
FLAME_FRAMES, FLAME_STACKS = 12, 6
FLAME_CELL = (64, 80)                      # texels
FLAME_COLS = 16
FLAME_OX, FLAME_OY = 16, 24                # the piece centre (MX, MY) inside a flame cell; the base line is 13 px below it
FLAME_BASE = 13
FIRE_CELL = 128
FIRE_CELLS = ["ringDark", "rune", "rim", "emberOn", "emberOff"]
EMBER_ANGLES = (124, 152, 180, 208, 236)
RUNE = [(-1, -3), (-1, -2), (-1, -1), (-1, 0), (-1, 1), (-1, 2), (-1, 3), (0, 0), (1, -1), (2, -2), (2, -3)]   # Younger Futhark kaun
RUNE_DY = 2 - max(y for _, y in RUNE)      # the glyph sits on the same baseline as every rune the mockup offers


def ring(R, th):
    out = []
    for y in range(-R - 1, R + 2):
        for x in range(-R - 1, R + 2):
            if not in_disc(x, y, R) or in_disc(x, y, R - th):
                continue
            outer = (not in_disc(x + 1, y, R)) or (not in_disc(x - 1, y, R)) or (not in_disc(x, y + 1, R)) or (not in_disc(x, y - 1, R))
            out.append((x, y, outer))
    return out


RING = ring(22, 2)


def ring_dark():
    L = Layer()
    for (x, y, outer) in RING:
        L.paint(x, y, col("#2a1420" if outer else "#22101a"))
    return L


def ring_lit(flat=None):
    """Mirrored about the ring's centre px for a Cooldown swipe."""
    L = Layer()
    for (x, y, outer) in RING:
        L.paint(-x, y, col(flat or ("#ff5a2a" if outer else "#ffb648")))
    return L


def ember_pos(i):
    a = EMBER_ANGLES[i] * math.pi / 180
    return jsround(math.sin(a) * 17), jsround(-math.cos(a) * 17)


# ---------------------------------------------------------------------------------------------------------------------
# the flame
# ---------------------------------------------------------------------------------------------------------------------
def flame(n, f):
    """Stacks n (0 to 5), frame f of the loop, no bob, no Scorch swell. Painted relative to the piece centre."""
    L = Layer()
    N = FLAME_FRAMES
    p_a = 2 * math.pi * f / N                          # the mockup's fr * 0.55 (one cycle a loop)
    p_b = 2 * math.pi * 2 * f / N                      # fr * 1.3 (two cycles a loop)
    arm = (2 * math.pi * f / N, 2 * math.pi * f / N + 2)
    H = 9 if n == 0 else 16 + n * 2.6
    Rb = 3.5 if n == 0 else 5.5 + n * 0.55
    bottom = FLAME_BASE
    heat = 0.5 if n == 0 else 0.8 + n * 0.06
    V: dict[tuple[int, int], list] = {}

    def put(x, y, v, u):
        o = V.get((x, y))
        if o is None:
            V[(x, y)] = [v, u]
        elif v > o[0]:
            o[0], o[1] = v, u

    for y in range(bottom, math.floor(bottom - H - 2) - 1, -1):
        u = (bottom - y) / H
        if u > 1.02:
            continue
        sway = math.sin(p_a + u * 3.6) * u * u * 3.4 + math.sin(p_b + u * 9) * u * 0.8
        if u < 0.28:
            hw = Rb * math.sqrt(max(0.0, 1 - math.pow((0.28 - u) / 0.28, 2)))
        else:
            hw = Rb * math.pow(max(0.0, 1 - u) / 0.72, 0.9)
        for x in range(-13, 14):
            dx = abs(x - sway)
            if dx <= hw + 0.3:
                put(x, y, ((1 - dx / (hw + 0.6)) * 0.7 + (1 - u) * 0.6) * heat, u)
        if n > 0:
            for (side, a, b, ph) in ((-1, 0.38, 0.66, arm[0]), (1, 0.46, 0.78, arm[1])):
                if u < a or u > b:
                    continue
                k = (u - a) / (b - a)
                c = side * (Rb * (0.55 + 0.15 * math.sin(ph)) + k * 3.5) + sway * 0.7
                w2 = 1.8 * (1 - k) + 0.3
                for x in range(-13, 14):
                    if abs(x - c) <= w2:
                        put(x, y, (0.42 + (1 - k) * 0.25) * heat, 0.7 + k * 0.3)
    for (x, y), (v, u) in V.items():
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + ax, y + ay) not in V:
                L.paint(x + ax, y + ay, col("#c04cff" if u > 0.75 else "#ff3b1e", 0.12 if n == 0 else 0.28))
    for (x, y), (v, u) in V.items():
        c = ("#ffffff" if v > 1.0 else "#fff3d0" if v > 0.85 else "#ffe08a" if v > 0.7 else "#ffcf3a" if v > 0.56
             else "#ff8a2a" if v > 0.42 else "#ff5a2a" if v > 0.3 else "#d0203a" if v > 0.18 else "#7a0c28")
        if u > 0.8 and v < 0.45:
            c = "#c04cff" if u > 0.92 else "#ff2e97"           # a hint of magic at the tips
        if n == 0:
            c = "#ff8a2a" if v > 0.6 else "#c0401e" if v > 0.4 else "#5a1a1a"
        L.paint(x, y, col(c))
    return L


def rune_rows():
    return [(x, y + RUNE_DY) for (x, y) in RUNE]


def rune_mask():
    L = Layer()
    for (x, y) in rune_rows():
        L.paint(x, y, col("#ffffff"))
    return L


def rim_mask():
    """The thin molten rim: the four neighbours of each rune px that are not rune px."""
    L = Layer()
    R = rune_rows()
    have = set(R)
    for (x, y) in R:
        for (ax, ay) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + ax, y + ay) not in have:
                L.paint(x + ax, y + ay, col("#ffffff"))
    return L


def ember_on():
    L = Layer()
    for (dx, dy) in ((0, -2), (-2, 0), (2, 0), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        L.paint(dx, dy, col("#1a0610"))
    L.paint(0, -1, col("#ffb648"))
    L.paint(0, 1, col("#e0401e"))
    L.paint(-1, 0, col("#ff8a2a"))
    L.paint(1, 0, col("#ff8a2a"))
    return L


def ember_off():
    L = Layer()
    L.paint(0, 0, col("#3a1a2a"))
    return L


def flame_atlas():
    a = Atlas(1024, 512)
    for n in range(FLAME_STACKS):
        for f in range(FLAME_FRAMES):
            w = cell_rect(n * FLAME_FRAMES + f, FLAME_COLS, *FLAME_CELL)
            a.blit(flame(n, f), w[0] + FLAME_OX, w[1] + FLAME_OY, w, f"flame{n}.{f}")
    return a


def fire_atlas():
    a = Atlas(512, 256)
    layers = {"ringDark": ring_dark(), "rune": rune_mask(), "rim": rim_mask(), "emberOn": ember_on(), "emberOff": ember_off()}
    for i, name in enumerate(FIRE_CELLS):
        w = cell_rect(i, 4, FIRE_CELL, FIRE_CELL)
        a.blit(layers[name], w[0] + CENTER, w[1] + CENTER, w, name)
    return a


def ring_swipe(flat=None):
    a = Atlas(128, 128)
    a.blit(ring_lit(flat), CENTER, CENTER, (0, 0, 64, 64), "ring")
    return a


def main():
    here = out_dir()
    write_tga(os.path.join(here, "mage_fire_flame.tga"), flame_atlas())
    write_tga(os.path.join(here, "mage_fire.tga"), fire_atlas())
    write_tga(os.path.join(here, "mage_fire_ring.tga"), ring_swipe())
    write_tga(os.path.join(here, "mage_fire_ring_low.tga"), ring_swipe("#ffb648"))


if __name__ == "__main__":
    main()
