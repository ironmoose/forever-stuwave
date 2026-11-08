#!/usr/bin/env python3
"""Bake the Mage Gunsight module's ward: the Ice Barrier (a clear-ice oval shell) and the Mana Shield (a gaseous oval of arcane mist).

The source is the design mockup (Mage Gunsight Module, 2026-11-07): drawWard. Every sprite px is baked as SCALE x SCALE texels of
one flat colour. Full colour RGBA, except the masks named below, which the game tints. The ward's centre (the mockup's SX, SY) is
sprite px (CENTER, CENTER) of a 64 x 64 cell.

What the game cannot do and the art leaves out: the bright row riding the light's edge (the fill level is secret), the mist's
slow swirl (a StatusBar cannot flip its picture; the mist is still art with a flipbook only for the vapour round its rim), the
ripple a hit sends through the mist, and the mist blowing apart at a break (the game draws shards for a break it can see).

    mage_ward.tga          512 x 512  4 x 4 cells of 128 x 128 texels (64 sprite px), order WARD_CELLS.
    mage_ward_mist.tga     512 x 512  4 x 4 cells of 128 x 128 texels: the thin mist body, the vapour flipbook (VAPOUR_FRAMES),
                                      the white flash mask of the mist, order MIST_CELLS.
    mage_ward_glyph.tga     32 x 32   2 x 2 cells of 16 x 16 texels (8 sprite px): the four 3 x 3 orbiting glyphs as white masks;
                                      each glyph's centre px is sprite px (GLYPH_ORIGIN, GLYPH_ORIGIN) of its cell.
    mage_ward_buff.tga     128 x 128  the pink buff ring, lit, baked mirrored (a Cooldown swipe shows the arc still to come).
    mage_ice_lit.tga        64 x 128  the lit interior of the shell, ICE_LIT_BOX stretched over the file (a StatusBar fills it).
    mage_ice_cd.tga        128 x 128  the cooling look of shell, edge and spikes, ICE_CD_BOX stretched over the file.
    mage_mist_dense.tga    128 x 128  the dense mist body and its bright ring, MIST_BOX stretched over the file.

    python3 tools/assets/generate_mage_ward.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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
WARD_CELL = 128
WARD_CELLS = ["buffDark", "buffDash", "iceDark", "edgeCd", "edgeEven", "edgeOdd", "spikeDark", "spikeMask", "upChrome",
              "iceFlash", "manaRingDim", "manaRingOff", "manaLocked", "manaCore", "iceCover", "manaRingMask"]
VAPOUR_FRAMES = 4
MIST_CELLS = ["body", "vapour0", "vapour1", "vapour2", "vapour3", "mistFlash"]
GLYPH_CELL, GLYPH_ORIGIN = 16, 4
OA, OB = 12, 17                            # the Ice Barrier oval
MA, MB = OA + 1, OB + 1                    # the Mana Shield oval
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
MIST = [None, "#2a1d5e", "#4a3aa8", "#7f6ff2", "#c8bcff"]
T_MIST = 1.3                               # the instant of the mockup's mist the art is taken at (its tile instant)
ICE_LIT_BOX = (-13, -17, 27, 35)
ICE_CD_BOX = (-17, -17, 34, 35)
MIST_BOX = (-15, -18, 30, 36)


def in_ell(x, y, a, b):
    return (x * x) / (a * a) + (y * y) / (b * b) <= 1.04


def ell_ring(a, b, a2, b2):
    out = []
    for y in range(-b - 1, b + 2):
        for x in range(-a - 1, a + 2):
            if not in_ell(x, y, a, b) or in_ell(x, y, a2, b2):
                continue
            an = math.atan2(x + 0.01, -y)
            if an < 0:
                an += 2 * math.pi
            outer = (not in_ell(x + 1, y, a, b)) or (not in_ell(x - 1, y, a, b)) or (not in_ell(x, y + 1, a, b)) or (not in_ell(x, y - 1, a, b))
            out.append((x, y, an / (2 * math.pi), outer))
    return sorted(out, key=lambda p: p[2])


BUFF = ell_ring(19, 24, 17, 22)
ICE_CRACKS = [[(-10, -7), (-5, -5), (-2, -6), (2, -2), (9, 0)], [(-3, -17), (-2, -12), (1, -9), (2, -6)],
              [(-9, 7), (-4, 8), (-1, 12), (1, 17)], [(4, 5), (7, 8), (10, 9)]]


def crack_set():
    o = set()
    for line in ICE_CRACKS:
        for i in range(len(line) - 1):
            (x0, y0), (x1, y1) = line[i], line[i + 1]
            n = max(abs(x1 - x0), abs(y1 - y0))
            for k in range(n + 1):
                o.add((jsround(x0 + (x1 - x0) * k / n), jsround(y0 + (y1 - y0) * k / n)))
    return o


CRACKS = crack_set()


def build_shell():
    out = []
    for y in range(-OB - 1, OB + 2):
        for x in range(-OA - 1, OA + 2):
            if not in_ell(x, y, OA, OB):
                continue
            edge = (not in_ell(x + 1, y, OA, OB)) or (not in_ell(x - 1, y, OA, OB)) or (not in_ell(x, y + 1, OA, OB)) or (not in_ell(x, y - 1, OA, OB))
            q = math.sqrt((x * x) / (OA * OA) + (y * y) / (OB * OB))
            crack = (not edge) and (x, y) in CRACKS
            sk = x - jsround(y * 0.5)
            streak = (not edge) and (((sk == -5 or sk == -4) and -13 <= y <= -3) or (sk == 5 and 1 <= y <= 9))
            rime = (not edge) and q > 0.8 and (BAYER[(y + 64) % 4][(x + 64) % 4] / 16) < (q - 0.8) * 4.2
            out.append((x, y, edge, q, crack, streak, rime))
    return out


SHELL = build_shell()


def build_spikes():
    o = []
    A = [0, 22, 47, 70, 95, 118, 142, 165, 190, 214, 238, 262, 288, 312, 337]
    L = [4, 2, 3, 2, 4, 2, 3, 3, 2, 4, 2, 3, 2, 4, 3]
    for i, deg in enumerate(A):
        a = deg * math.pi / 180
        bx, by = OA * math.sin(a), -OB * math.cos(a)
        nx, ny = bx / (OA * OA), by / (OB * OB)
        nl = math.hypot(nx, ny)
        nx, ny = nx / nl, ny / nl
        for k in range(L[i] + 1):
            o.append((jsround(bx + nx * k), jsround(by + ny * k), k == L[i]))
            if k < L[i] - 1:
                o.append((jsround(bx + nx * k - ny), jsround(by + ny * k + nx), False))
    return o


SPK = build_spikes()


# ---------------------------------------------------------------------------------------------------------------------
# the pink buff ring (60 s)
# ---------------------------------------------------------------------------------------------------------------------
def buff_dark():
    L = Layer()
    for (x, y, f, outer) in BUFF:
        L.paint(x, y, col("#2a1430" if outer else "#22102a"))
    return L


def buff_dash():
    L = Layer()
    for i, (x, y, f, outer) in enumerate(BUFF):
        if outer and i % 3 == 0:
            L.paint(x, y, col("#1c1230"))
    return L


def buff_lit():
    L = Layer()
    for (x, y, f, outer) in BUFF:
        L.paint(-x, y, col("#ff2e97" if outer else "#ff8ad8"))
    return L


# ---------------------------------------------------------------------------------------------------------------------
# the Ice Barrier
# ---------------------------------------------------------------------------------------------------------------------
def ice_dark():
    """The interior in its empty look (the edge is a separate layer)."""
    L = Layer()
    for (x, y, edge, q, crack, streak, rime) in SHELL:
        if edge:
            continue
        c = "#24345c" if rime else "#2e4270" if crack else "#16264a" if streak else "#0a1022" if q < 0.5 else "#0e1830" if q < 0.8 else "#16264a"
        L.paint(x, y, col(c))
    return L


def ice_lit():
    L = Layer()
    for (x, y, edge, q, crack, streak, rime) in SHELL:
        if edge:
            continue
        c = ("#f4ffff" if rime else "#e8ffff" if crack else "#c8f6ff" if streak
             else "#1e78a8" if q < 0.42 else "#2f98c8" if q < 0.62 else "#5fc8e4" if q < 0.8 else "#9fe8f8")
        L.paint(x, y, col(c))
    return L


def ice_cd_body():
    """The interior as the cooldown refill lights it, plus the lit edge and spikes of the same refill."""
    L = Layer()
    for (x, y, edge, q, crack, streak, rime) in SHELL:
        if edge:
            continue
        c = ("#4a8ca8" if rime else "#0c1c34" if crack else "#3a7e9c" if streak
             else "#1f5672" if q < 0.5 else "#24607c" if q < 0.8 else "#2c6c88")
        L.paint(x, y, col(c))
    return L


def ice_spikes(fn):
    """Spikes painted before the shell, as the mockup does (the shell's edge wins where they meet)."""
    L = Layer()
    for (x, y, tip) in SPK:
        L.paint(x, y, col(fn(x, y, tip)))
    return L


def ice_edge(fn):
    L = Layer()
    for (x, y, edge, q, crack, streak, rime) in SHELL:
        if edge:
            c = fn(x, y)
            if c:
                L.paint(x, y, col(c))
    return L


def ice_up_chrome():
    L = Layer()
    L.over(ice_spikes(lambda x, y, tip: "#ffffff" if tip else ("#d4fbff" if y < 0 else "#7fe0f4")))
    L.over(ice_edge(lambda x, y: "#f4ffff" if (y < 0 or x < 0) else "#9ff0ff"))
    return L


def ice_cover():
    """The interior in its empty look as one opaque cover (the unfilled top of the light sits on it)."""
    return ice_dark()


def ice_mask(layer):
    out = Layer()
    for k, (_, _, _, a) in layer.p.items():
        out.p[k] = (255, 255, 255, a)
    return out


def ice_flash():
    L = Layer()
    L.over(ice_spikes(lambda x, y, tip: "#ffffff"))
    L.over(ice_edge(lambda x, y: "#ffffff"))
    for (x, y, edge, *_r) in SHELL:
        if not edge:
            L.paint(x, y, col("#ffffff"))
    return L


def ice_lit_file():
    return stretched(ice_lit(), ICE_LIT_BOX, 64, 128)


def ice_cd_file():
    L = Layer()
    L.over(ice_spikes(lambda x, y, tip: "#5aa8c4" if tip else "#3a7898"))
    L.over(ice_edge(lambda x, y: "#5aa8c4"))
    L.over(ice_cd_body())
    return stretched(L, ICE_CD_BOX, 128, 128)


# ---------------------------------------------------------------------------------------------------------------------
# the Mana Shield
# ---------------------------------------------------------------------------------------------------------------------
def mist_edge(a, t=T_MIST):
    return 1 + 0.02 * math.sin(t * 1.6) + 0.05 * math.sin(a * 3 + t * 1.3) + 0.035 * math.sin(a * 5 - t * 2.1)


def mist_cell(x, y, d):
    lv = min(4, math.floor(d * 4 + BAYER[(y + 64) % 4][(x + 64) % 4] / 16))
    return MIST[lv] if lv > 0 else None


def mist_body(dense):
    """The body of the oval (inside its wobbling edge): the thin veil, or the dense band the StatusBar fills."""
    L = Layer()
    RX, RY = math.ceil(MA + 6), math.ceil(MB + 6)
    for y in range(-RY, RY + 1):
        for x in range(-RX, RX + 1):
            e = math.hypot(x / MA, y / MB)
            a = math.atan2(y / MB, x / MA)
            if e > mist_edge(a):
                continue
            sw = 0.5 + 0.5 * math.sin(a * 2 - e * 7 + T_MIST * 1.7)
            d = (0.5 + 0.22 * max(0, e - 0.55) + 0.08 * sw) if dense else (0.2 + 0.08 * sw)
            c = mist_cell(x, y, d)
            if c:
                L.paint(x, y, col(c))
    return L


def mist_vapour(t):
    """The vapour curling off the rim, thinning outward; its curl is taken at instant t, the rim at T_MIST."""
    L = Layer()
    RX, RY = math.ceil(MA + 6), math.ceil(MB + 6)
    for y in range(-RY, RY + 1):
        for x in range(-RX, RX + 1):
            e = math.hypot(x / MA, y / MB)
            a = math.atan2(y / MB, x / MA)
            edge = mist_edge(a)
            if not (edge < e < edge + 0.28):
                continue
            k = (e - edge) / 0.28
            curl = 0.5 + 0.5 * math.sin(a * 6 + e * 14 - t * 2.4)
            d = 0.42 * (1 - k) * (0.35 + 0.75 * curl)
            c = mist_cell(x, y, d)
            if c:
                L.paint(x, y, col(c))
    return L


def mana_ring_px():
    out = []
    for y in range(-MB - 1, MB + 2):
        for x in range(-MA - 1, MA + 2):
            if in_ell(x, y, MA, MB) and not in_ell(x, y, MA - 1, MB - 1):
                out.append((x, y))
    return out


MANA_RING = mana_ring_px()


def mana_ring(c):
    L = Layer()
    for (x, y) in MANA_RING:
        L.paint(x, y, col(c))
    return L


def mana_ring_off():
    L = Layer()
    for (x, y) in MANA_RING:
        if (x + y) & 1:
            L.paint(x, y, col("#3a2c6a"))
    return L


def mana_locked():
    L = Layer()
    for i in range(40):
        a = i / 40 * 2 * math.pi
        if i % 2 == 0:
            L.paint(jsround(math.sin(a) * 14), jsround(-math.cos(a) * 16), col("#9d93c4", 0.4))
    return L


def mana_core():
    """The soft violet glow at the core, at its brightest beat (the game scales its alpha down to the dim beat)."""
    L = Layer()
    for y in range(-4, 5):
        for x in range(-3, 4):
            r = math.hypot(x, y * 0.8)
            if r > 3.6:
                continue
            L.paint(x, y, col("#e8d8ff" if r < 1.2 else "#b4a8ff", (1 - r / 3.8) * 0.6))
    return L


def mist_dense_file():
    L = Layer()
    L.over(mist_body(True))
    L.over(mana_ring("#c8bcff"))
    return stretched(L, MIST_BOX, 128, 128)


GLYPHS = [[(0, -1), (0, 0), (0, 1), (-1, 0), (1, 0)], [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
          [(0, -1), (-1, 0), (1, 0), (0, 1)], [(-1, -1), (0, -1), (1, -1), (0, 0), (0, 1)]]


def glyph_atlas():
    a = Atlas(32, 32)
    for i, g in enumerate(GLYPHS):
        L = Layer()
        for (x, y) in g:
            L.paint(x, y, col("#ffffff"))
        w = cell_rect(i, 2, GLYPH_CELL, GLYPH_CELL)
        a.blit(L, w[0] + GLYPH_ORIGIN, w[1] + GLYPH_ORIGIN, w, f"glyph{i}")
    return a


def ward_atlas():
    a = Atlas(512, 512)
    chrome = ice_up_chrome()
    layers = {
        "buffDark": buff_dark(), "buffDash": buff_dash(), "iceDark": ice_dark(),
        "edgeCd": ice_edge(lambda x, y: "#2e4270"),
        "edgeEven": ice_edge(lambda x, y: "#0e0a1c" if not ((x + y) & 1) else None),
        "edgeOdd": ice_edge(lambda x, y: "#ffffff" if ((x + y) & 1) else None),
        "spikeDark": ice_spikes(lambda x, y, tip: "#2e4270" if tip else "#24345c"),
        "spikeMask": ice_spikes(lambda x, y, tip: "#ffffff"),
        "upChrome": chrome, "iceFlash": ice_flash(),
        "manaRingDim": mana_ring("#7f6ff2"), "manaRingOff": mana_ring_off(), "manaLocked": mana_locked(), "manaCore": mana_core(),
        "iceCover": ice_cover(), "manaRingMask": mana_ring("#ffffff"),
    }
    for i, name in enumerate(WARD_CELLS):
        w = cell_rect(i, 4, WARD_CELL, WARD_CELL)
        a.blit(layers[name], w[0] + CENTER, w[1] + CENTER, w, name)
    return a


def mist_atlas():
    a = Atlas(512, 512)
    flash = Layer()
    for (k, c) in mist_body(False).p.items():
        flash.p[k] = (255, 255, 255, 1.0)
    for (x, y) in MANA_RING:
        flash.paint(x, y, col("#ffffff"))
    layers = {"body": mist_body(False), "mistFlash": flash}
    for i in range(VAPOUR_FRAMES):
        layers[f"vapour{i}"] = mist_vapour(T_MIST + i * 2 * math.pi / 2.4 / VAPOUR_FRAMES)
    for i, name in enumerate(MIST_CELLS):
        w = cell_rect(i, 4, WARD_CELL, WARD_CELL)
        a.blit(layers[name], w[0] + CENTER, w[1] + CENTER, w, name)
    return a


def buff_swipe():
    a = Atlas(128, 128)
    a.blit(buff_lit(), CENTER, CENTER, (0, 0, 64, 64), "buff")
    return a


def main():
    here = out_dir()
    write_tga(os.path.join(here, "mage_ward.tga"), ward_atlas())
    write_tga(os.path.join(here, "mage_ward_mist.tga"), mist_atlas())
    write_tga(os.path.join(here, "mage_ward_glyph.tga"), glyph_atlas())
    write_tga(os.path.join(here, "mage_ward_buff.tga"), buff_swipe())
    write_tga(os.path.join(here, "mage_ice_lit.tga"), ice_lit_file())
    write_tga(os.path.join(here, "mage_ice_cd.tga"), ice_cd_file())
    write_tga(os.path.join(here, "mage_mist_dense.tga"), mist_dense_file())


if __name__ == "__main__":
    main()
