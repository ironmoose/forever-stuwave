#!/usr/bin/env python3
"""Bake the Mage Gunsight module's two Ice Lance / Fire Blast marks: the ice spike and the fireball comet.

The source is the design mockup (Mage Gunsight Module, 2026-11-07): drawLance (the 36 px faceted ice spike, broken flat at the
back, spurs jutting forward, drawn pointing left) and drawFireBlastMark (a comet flying right: a big round head tapering like a
teardrop into rippling strands of flame). Every sprite px is baked as SCALE x SCALE texels of one flat colour. Full colour RGBA.

    mage_spike.tga         256 x 128  2 x 2 cells of 128 x 64 texels (64 x 32 sprite px), order SPIKE_CELLS: the spike ready,
                                      cooling (dark), and its white cast flash. Origin (SPIKE_OX, SPIKE_OY) of the cell is the
                                      spike's (0, 0): the sprite px the mockup puts at (L0, LY).
    mage_spike_mid.tga     128 x 64   the cooling spike's refilled colours, SPIKE_BOX stretched over the file, so a horizontal
                                      StatusBar filling from the right (the spike's broken back) draws the cooldown.
    mage_comet.tga         512 x 512  4 x 10 cells of 128 x 48 texels (64 x 24 sprite px), order COMET_CELLS: COMET_FRAMES frames
                                      of the ready comet (a COMET_LOOP s loop at COMET_FPS), then the cooling comet and its white
                                      flash. The cell's origin (COMET_OX, COMET_OY) is where the mockup's mirrored x = COMET_K - x
                                      puts the sprite, for a piece centred at MX = 46.
    mage_comet_mid.tga     256 x 64   the cooling comet's refilled colours, COMET_BOX stretched over the file: a horizontal
                                      StatusBar filling from the left (the strand tips) toward the head.

    python3 tools/assets/generate_mage_mark.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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
# the ice spike
# ---------------------------------------------------------------------------------------------------------------------
SP_TOP = [3, 5, 6, 6, 6, 5, 6, 6, 5, 5, 6, 5, 5, 4, 4, 5, 4, 4, 3, 3, 4, 3, 3, 2, 2, 3, 2, 2, 1, 2, 1, 1, 1, 0, 0, 0]
SP_BOT = [3, 4, 5, 5, 4, 5, 5, 4, 4, 4, 3, 4, 4, 3, 3, 3, 3, 2, 3, 2, 2, 2, 2, 2, 1, 2, 1, 1, 1, 1, 0, 1, 0, 0, 0, 0]
LEN = len(SP_TOP)                          # 36 px long
SPIKE_CELLS = ["ready", "off", "flash"]
SPIKE_CELL = (128, 64)                     # texels
SPIKE_OX, SPIKE_OY = 6, 12                 # the spike's (0, 0) (mockup L0, LY) inside its 64 x 32 sprite px cell
SPIKE_BOX = (-3, -10, 40, 20)              # StatusBar art box from the spike's (0, 0): x, y, w, h (stretched over mage_spike_mid)
LPAL_LIT = {"ridge": "#ffffff", "hi": "#d4fbff", "up": "#9ff0ff", "topE": "#e8ffff", "lo": "#5fd4e8", "deep": "#2fa8c8",
            "botE": "#17608a", "crack": "#ffffff", "back": "#c8f6ff", "spur": "#d4fbff", "spurL": "#3ab8d8"}
LPAL_MID = {"ridge": "#9ff0ff", "hi": "#7fe0f4", "up": "#4ab4d4", "topE": "#7fe0f4", "lo": "#2a8cb0", "deep": "#1e6a90",
            "botE": "#124a6a", "crack": "#5fd4e8", "back": "#7fe0f4", "spur": "#5fd4e8", "spurL": "#1e6a90"}
LPAL_OFF = {"ridge": "#2e4270", "hi": "#24345c", "up": "#1e2c50", "topE": "#2e4270", "lo": "#1a2644", "deep": "#16203a",
            "botE": "#101830", "crack": "#24345c", "back": "#2e4270", "spur": "#24345c", "spurL": "#16203a"}


def build_lance():
    m = []
    for x in range(LEN):
        tp, bt = SP_TOP[x], SP_BOT[x]
        for y in range(-tp, bt + 1):
            fu = math.floor((x + y * 0.9 + 40) / 6) % 2
            fl = math.floor((x - y * 0.9 + 40) / 6) % 2
            if y == 0:
                k = "hi" if (x % 7) >= 5 else "ridge"
            elif y == -tp:
                k = "topE"
            elif y == bt:
                k = "botE"
            elif y < 0:
                k = "hi" if fu else "up"
            else:
                k = "lo" if fl else "deep"
            if x == 0 or (x == 1 and abs(y) > 2):
                k = "back"
            m.append((x, y, k))
    for (x, y) in ((9, -6), (10, -7), (11, -8), (19, -5), (20, -6), (27, -3), (28, -4)):
        m.append((x, y, "spur"))
    for (x, y) in ((13, 5), (14, 6), (23, 3), (24, 4)):
        m.append((x, y, "spurL"))
    for (x, y) in ((36, 0), (37, 0)):
        m.append((x, y, "ridge"))
    return m


LANCE = build_lance()
LANCE_SET = {(p[0], p[1]) for p in LANCE}


def spike(pal, white=False):
    """The spike as the mockup draws it: a 1 px dark outline, then the body. Drawn mirrored: sprite x 0 (the back) is at
    screen x LEN - 1, the point at the left."""
    L = Layer()
    sx = lambda x: LEN - 1 - x
    for (x, y, _) in LANCE:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, y + dy) not in LANCE_SET:
                L.paint(sx(x + dx), y + dy, col("#0a2238"))
    for (x, y, k) in LANCE:
        L.paint(sx(x), y, col("#ffffff" if white else pal[k]))
    return L


def spike_atlas():
    a = Atlas(256, 128)
    for name, layer in (("ready", spike(LPAL_LIT)), ("off", spike(LPAL_OFF)), ("flash", spike(LPAL_LIT, True))):
        w = cell_rect(SPIKE_CELLS.index(name), 2, *SPIKE_CELL)
        a.blit(layer, w[0] + SPIKE_OX, w[1] + SPIKE_OY, w, name)
    return a


def spike_mid():
    return stretched(spike(LPAL_MID), SPIKE_BOX, 128, 64)


# ---------------------------------------------------------------------------------------------------------------------
# the Fire Blast comet
# ---------------------------------------------------------------------------------------------------------------------
FB_BODY = 40
FB_STRANDS = [  # start dx on the body, side (fraction of the body half width), length, fan at the tip, wave amp, start width, phase, speed
    [21, -0.45, 21, -2.2, 0.9, 1.9, 0.0, 1.00],
    [23, 0.45, 17, 2.0, 0.8, 1.7, 1.9, 1.20],
    [29, -0.10, 17, -0.6, 0.9, 1.3, 3.7, 1.10],
    [27, 0.20, 12, 1.0, 0.7, 1.1, 5.1, 1.35]]
LX, LY = 27, 64
HX, HY = LX + 6, LY
COMET_K = 102                              # the mockup's mirror, K = round(MX + (minX + maxX) / 2) for a piece centred at MX = 46
COMET_FRAMES, COMET_FPS = 24, 12           # a 2 s loop
COMET_LOOP_CYCLES = (2, 3, 2, 3)           # waves per loop of each strand (the mockup's speeds, rounded to whole cycles)
COMET_CELLS = [f"ready{i}" for i in range(COMET_FRAMES)] + ["off", "flash"]
COMET_CELL = (128, 48)                     # texels: 64 x 24 sprite px
COMET_OX, COMET_OY = -16, -52              # the cell's top left is screen (16, 52) at MX = 46
COMET_BOX = (23, 52, 53, 24)               # StatusBar art box in screen sprite px at MX = 46: x, y, w, h
COMET_MIRROR_PAD = 0


def nz(i):
    v = math.sin(i * 12.9898) * 43758.5453
    return v - math.floor(v)


def comet(mode, f=0, flash=False):
    """mode 'ready' (frame f of the loop), 'mid' (cooling colours, all lit) or 'off'. Painted at screen coordinates for MX = 46."""
    ready = mode == "ready"
    L = Layer()
    N = COMET_FRAMES
    ph_body = 2 * math.pi * 2 * f / N          # the body spine and the head pulse: two cycles per loop
    pulse = 0.5 + 0.5 * math.sin(ph_body) if ready else 0.0
    R = 5.6 + 0.5 * pulse

    def hw(dx):
        if dx <= 0:
            return math.sqrt(max(0.0, R * R - dx * dx))
        return R * math.pow(max(0.0, 1 - dx / FB_BODY), 1.25)

    mir = lambda x: COMET_K - x
    V: dict[tuple[int, int], float] = {}

    def put(x, y, v):
        k = (x, y)
        if k not in V or V[k] < v:
            V[k] = v

    for dx in range(-math.ceil(R), FB_BODY + 1):
        u = max(0, dx) / FB_BODY
        w = hw(dx) + 0.2
        cy = HY + (math.sin(u * 4 - ph_body) * u * 0.9 if ready else 0)
        for y in range(math.floor(cy - w), math.ceil(cy + w) + 1):
            py = abs(y - cy)
            if py > w:
                continue
            r = math.hypot(min(dx, 0) * 1.0 + max(dx, 0) * 0.35, py)
            put(HX + dx, y, (1 - py / (w + 0.6)) * 0.65 + (1 - u) * 0.55 + max(0, 1 - r / (R * 0.8)) * 0.45)
    tip_y, tip_x = [], []
    for k, (d0, side, ln, fan, amp, w0, ph, sp) in enumerate(FB_STRANDS):
        flick = 0.86 + 0.14 * nz(f * 3.1 + k * 7) if ready else 1
        y0 = HY + side * hw(d0)
        wave = 2 * math.pi * COMET_LOOP_CYCLES[k] * f / N if ready else 0.35 * 7 * sp
        yat = lambda u: (HY + (y0 - HY) * (1 - 0.7 * min(1, u * 1.6)) + fan * u * u
                         + amp * math.sin(u * 5.2 + ph - wave) * min(1, u * 2.2))
        tip_y.append(yat(1))
        tip_x.append(HX + d0 + ln)
        prev = jsround(y0)
        for i in range(ln + 1):
            u = i / ln
            cy = yat(u)
            w = max(0.35, w0 * math.pow(1 - u, 0.9) + 0.2)
            x = HX + d0 + i
            base = (0.5 + (1 - u) * 0.45) * flick * (1 - d0 / FB_BODY * 0.4)
            ry = jsround(cy)
            for y in range(min(prev, ry), max(prev, ry) + 1):
                put(x, y, base * 0.95)
            prev = ry
            for y in range(math.floor(cy - w), math.ceil(cy + w) + 1):
                py = abs(y - cy)
                if py < w:
                    put(x, y, base * ((1 - py / w) * 0.5 + 0.6))
    if ready:
        for (x, y) in list(V):
            for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + ax, y + ay) not in V:
                    head = x < HX + 4
                    L.paint(mir(x + ax), y + ay, col("#ff3b1e" if head else "#d0203a", (0.25 + 0.25 * pulse) if head else 0.22))
    for (x, y), v in V.items():
        if flash:
            c = "#ffffff"
        elif ready:
            c = ("#ffffff" if v > 1.3 else "#fff3d0" if v > 1.1 else "#ffe08a" if v > 0.92 else "#ffcf3a" if v > 0.74
                 else "#ff8a2a" if v > 0.56 else "#ff5a2a" if v > 0.42 else "#d0203a" if v > 0.3 else "#7a0c28")
        elif mode == "mid":
            c = "#ffb648" if v > 1.1 else "#e07a20" if v > 0.74 else "#c04a1a" if v > 0.45 else "#6a1a18"
        else:
            c = "#5a2430" if v > 1.1 else "#4a2028" if v > 0.74 else "#3a1a22" if v > 0.45 else "#2a1018"
        L.paint(mir(x), y, col(c))
    if ready and not flash:
        for k in range(len(FB_STRANDS)):
            ph = ((2 * f / N) + k * 0.27) % 1
            if ph > 0.85:
                continue
            L.paint(mir(jsround(tip_x[k] + 1 + ph * 5)), jsround(tip_y[k] + (1 if k % 2 else -1) * ph * 2.5),
                    col("#ffe08a" if ph < 0.35 else "#ff5a2a", 1 - ph))
    return L


def comet_atlas():
    a = Atlas(512, 512)
    for i, name in enumerate(COMET_CELLS):
        if name.startswith("ready"):
            layer = comet("ready", int(name[5:]))
        else:
            layer = comet("off") if name == "off" else comet("off", flash=True)
        w = cell_rect(i, 4, *COMET_CELL)
        a.blit(layer, w[0] + COMET_OX, w[1] + COMET_OY, w, name)
    return a


def comet_mid():
    return stretched(comet("mid"), COMET_BOX, 256, 64)


def main():
    here = out_dir()
    write_tga(os.path.join(here, "mage_spike.tga"), spike_atlas())
    write_tga(os.path.join(here, "mage_spike_mid.tga"), spike_mid())
    write_tga(os.path.join(here, "mage_comet.tga"), comet_atlas())
    write_tga(os.path.join(here, "mage_comet_mid.tga"), comet_mid())


if __name__ == "__main__":
    main()
