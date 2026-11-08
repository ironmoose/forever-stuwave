#!/usr/bin/env python3
"""Bake the Mage Gunsight module's Arcane look: the 18 s ring, the Eye of the Kirin Tor and the four stack gems.

The source is the design mockup (Mage Gunsight Module, 2026-11-07): drawArcane. Every sprite px is baked as SCALE x SCALE texels
of one flat colour. Full colour RGBA. The piece's centre (the mockup's MX, MY) is the corner between sprite px (CENTER - 1) and
CENTER of a 64 x 64 sprite px cell, so the ring (centred on that corner) is centred on the cell and a Cooldown sweep over it
turns about the right point.

    mage_arcane.tga           512 x 256  4 x 2 cells of 128 x 128 texels (64 sprite px), order ARC_CELLS: the dark ring, the
                                         Eye shut (no stacks), open (1-3) and blazing (4 stacks), the pink glow round the open
                                         and the blazing lids, the Clearcasting spark arms and diagonals. The piece's centre
                                         is sprite px (CENTER, CENTER) of the cell; the spark's centre is its origin (CENTER, CENTER).
    mage_arcane_gems.tga      256 x 256  4 x 4 cells of 64 x 64 texels (32 sprite px), order GEM_CELLS: a dark gem, a lit gem,
                                         its white twinkle and white fresh overlays, then the pop rings at radius 5 to 10.
                                         The gem's centre is the corner of sprite px (GEM_ORIGIN, GEM_ORIGIN).
    mage_arcane_ring.tga      128 x 128  the lit ring, baked mirrored (a Cooldown swipe shows the arc still to come, the ring
                                         empties from its far end back toward the top).
    mage_arcane_ring_low.tga  128 x 128  the same arc in one amber colour for the last seconds.

    python3 tools/assets/generate_mage_arcane.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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
CENTER = 32                                # sprite px of the piece's centre corner inside a 64 x 64 cell
ARC_CELL = 128                             # texels
ARC_CELLS = ["ringDark", "eyeShut", "eyeOpen", "eyeFull", "glowOpen", "glowFull", "ccArms", "ccDiag"]
GEM_CELL = 64
GEM_ORIGIN = 16
GEM_CELLS = ["off", "on", "twinkle", "fresh", "pop5", "pop6", "pop7", "pop8", "pop9", "pop10"]
POP_MIN, POP_MAX = 5, 10
GLOW_FULL_ALPHA = 0.45                     # the blazing glow peaks here; the game scales it down to the pulse low
RING_R, RING_TH = 22, 2


def ring_px():
    """The 18 s ring, centred on the pixel corner (0, 0): (x, y, outer)."""
    def IN(x, y, r):
        a, b = x + 0.5, y + 0.5
        return a * a + b * b <= r * r + r * 0.8
    out = []
    for y in range(-RING_R - 2, RING_R + 2):
        for x in range(-RING_R - 2, RING_R + 2):
            if not IN(x, y, RING_R) or IN(x, y, RING_R - RING_TH):
                continue
            outer = (not IN(x + 1, y, RING_R) or not IN(x - 1, y, RING_R)
                     or not IN(x, y + 1, RING_R) or not IN(x, y - 1, RING_R))
            out.append((x, y, outer))
    return out


RING = ring_px()


def ring_dark():
    L = Layer()
    for (x, y, outer) in RING:
        L.paint(x, y, col("#22163a" if outer else "#1a1030"))
    return L


def ring_lit(flat=None):
    """The lit ring mirrored about its centre corner (x -> -1 - x) for a Cooldown swipe."""
    L = Layer()
    for (x, y, outer) in RING:
        L.paint(-1 - x, y, col(flat or ("#c04cff" if outer else "#e08cff")))
    return L


# ---------------------------------------------------------------------------------------------------------------------
# the Eye of the Kirin Tor (2 x 2 blocks)
# ---------------------------------------------------------------------------------------------------------------------
LID = ["....XXXXX....", "..XX.....XX..", ".X.........X.", "X...........X", ".X.........X.", "..XX.....XX..", "....XXXXX...."]
HALF = [5, 4, 2]
IRIS = [(-1, -1), (0, -1), (1, -1), (-2, 0), (-1, 0), (1, 0), (2, 0), (-1, 1), (0, 1), (1, 1)]
RAYS = [(0, 4), (0, 5), (0, 6), (-2, 4), (-3, 5), (2, 4), (3, 5), (-5, 4), (5, 4)]


def ep(L, x, y, c):
    L.rect(2 * x - 1, 2 * y - 3, 2, 2, c)


def inside_eye(x, y):
    return abs(y) <= 2 and abs(x) <= HALF[abs(y)]


def eye(state):
    """state: shut (no stacks), open (1-3), full (4). The white pulse pixels of the blazing eye (the pupil and the ray tip) are
    left out: the game draws them as flat white blocks it pulses."""
    L = Layer()
    n0, full = state == "shut", state == "full"
    gold = "#4a3a6a" if n0 else ("#ffe08a" if full else "#ffd36a")
    gold2 = "#3a2c58" if n0 else "#c89a3a"
    for x in range(-3, 4):
        ep(L, x, -5, col(gold2))
    ep(L, -4, -4, col(gold2))
    ep(L, 4, -4, col(gold2))
    if n0:
        for x in range(-6, 7):
            ep(L, x, 0, col(gold))
        for (x, y) in ((-4, 1), (-2, 2), (0, 2), (2, 2), (4, 1)):
            ep(L, x, y, col(gold2))
    else:
        for j in range(7):
            for q in range(13):
                x, y = q - 6, j - 3
                if LID[j][q] == "X":
                    ep(L, x, y, col(gold))
                elif inside_eye(x, y):
                    ep(L, x, y, col("#2a1040"))
        ir = "#ff8ad8" if full else "#ff5ad0"
        ir2 = "#ff5ad0" if full else "#c0308a"
        for (x, y) in IRIS:
            ep(L, x, y, col(ir2 if x + y > 0 else ir))
        if not full:
            ep(L, 0, 0, col("#ffd0f0"))
        for (x, y) in ((-3, -5), (-2, -5), (-3, -4)):                       # glint
            L.paint(x, y, col("#ffffff"))
        for x in range(-7, 7):                                              # upper lid highlight, 1 px
            L.paint(x, -9, col("#fff6c8" if full else "#ffe9a8"))
    ray = "#2e2248" if n0 else ("#ffd36a" if full else "#a855f7")
    for (x, y) in RAYS:
        ep(L, x, y, col(ray))
    if not n0 and not full:
        ep(L, 0, 7, col("#e09cff"))
    return L


def eye_glow(state):
    """The soft glow round the open lids, painted once per lid px edge exactly as the mockup does (so it builds up where edges meet)."""
    L = Layer()
    full = state == "full"
    c = col("#ff5ad0", GLOW_FULL_ALPHA) if full else col("#a855f7", 0.12)
    for j in range(7):
        for q in range(13):
            if LID[j][q] != "X":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jj, qq = j + dy, q + dx
                if 0 <= jj < 7 and 0 <= qq < 13 and LID[jj][qq] == "X":
                    continue
                x, y = q - 6 + dx, j - 3 + dy
                if not inside_eye(x, y):
                    ep(L, x, y, c)
    return L


def cc_arms():
    L = Layer()
    c = col("#d4fbff")
    for d in range(-3, 4):
        L.paint(d, 0, c)
        L.paint(0, d, c)
    return L


def cc_diag():
    L = Layer()
    for (x, y) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        L.paint(x, y, col("#9ff0ff"))
    return L


def arcane_atlas():
    a = Atlas(512, 256)
    layers = {"ringDark": (ring_dark(), CENTER), "eyeShut": (eye("shut"), CENTER), "eyeOpen": (eye("open"), CENTER),
              "eyeFull": (eye("full"), CENTER), "glowOpen": (eye_glow("open"), CENTER), "glowFull": (eye_glow("full"), CENTER),
              "ccArms": (cc_arms(), CENTER), "ccDiag": (cc_diag(), CENTER)}
    for i, name in enumerate(ARC_CELLS):
        layer, o = layers[name]
        w = cell_rect(i, 4, ARC_CELL, ARC_CELL)
        a.blit(layer, w[0] + o, w[1] + o, w, name)
    return a


def ring_swipe(flat=None):
    a = Atlas(128, 128)
    a.blit(ring_lit(flat), CENTER, CENTER, (0, 0, 64, 64), "ring")
    return a


# ---------------------------------------------------------------------------------------------------------------------
# the stack gems (a diamond on the half pixel)
# ---------------------------------------------------------------------------------------------------------------------
def gem(kind):
    """kind: off, on, twinkle (the four centre px white), fresh (the whole diamond white)."""
    L = Layer()
    for y in range(-6, 6):
        for x in range(-6, 6):
            ax, ay = x + 0.5, y + 0.5
            d = abs(ax) + abs(ay)
            if kind in ("off", "on") and d == 6:
                L.paint(x, y, col("#0a0416"))
            if d > 5:
                continue
            if kind == "off":
                c = "#3a2560" if d == 5 else "#120a20"
            elif kind == "on":
                if d == 5:
                    c = "#8a1a6a"
                elif ax + ay <= -1 and d <= 3:
                    c = "#ffd0f0"
                elif ax + ay >= 2:
                    c = "#c0308a"
                else:
                    c = "#ff5ad0"
                if d == 1:
                    c = "#ffb0e8"
            elif kind == "twinkle":
                if d != 1:
                    continue
                c = "#ffffff"
            else:
                c = "#ffffff"
            L.paint(x, y, col(c))
    return L


def pop(r):
    L = Layer()
    for y in range(-r, r + 1):
        for x in range(-r, r + 1):
            if abs(x) + abs(y) == r and (x + y) % 2 == 0:
                L.paint(x, y, col("#ff8ad8"))
    return L


def gems_atlas():
    a = Atlas(256, 256)
    for i, name in enumerate(GEM_CELLS):
        layer = pop(int(name[3:])) if name.startswith("pop") else gem(name)
        w = cell_rect(i, 4, GEM_CELL, GEM_CELL)
        a.blit(layer, w[0] + GEM_ORIGIN, w[1] + GEM_ORIGIN, w, name)
    return a


def main():
    here = out_dir()
    write_tga(os.path.join(here, "mage_arcane.tga"), arcane_atlas())
    write_tga(os.path.join(here, "mage_arcane_gems.tga"), gems_atlas())
    write_tga(os.path.join(here, "mage_arcane_ring.tga"), ring_swipe())
    write_tga(os.path.join(here, "mage_arcane_ring_low.tga"), ring_swipe("#ffb648"))


if __name__ == "__main__":
    main()
