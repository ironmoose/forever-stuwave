#!/usr/bin/env python3
"""Bake the Hunter Gunsight module's trap piece: the bear trap with its jaws open and its soft glow, the sprung jaws (dark, white flash, and
the lit art a StatusBar fills from the bottom while the shared trap cooldown refills) and the two trap slot bars' frames.

The source is the design mockup "Hunter Gunsight Module: Lock-On Scope + Traps" (2026-11-07): drawTrapOpen, drawTrapShut and drawSlot.
Every sprite px is baked as SCALE x SCALE texels of one flat colour.

    hunter_trap.tga       512 x 256  4 x 4 cells of 128 x 64 texels (64 x 32 sprite px), order TRAP_CELLS. open and glow have the jaws'
                                     centre (the mockup's TC) at cell px (OPEN_OX, OPEN_OY); shutDark and shutWhite are the shut jaws'
                                     box (SHUT_W x SHUT_H sprite px) at the cell's top left; slotBorder (a white mask, tinted) and slotInner
                                     (the dark inside) are the slot bar's frame (42 x 8) at the cell's top left.
    hunter_trap_lit.tga   64 x 32    the shut jaws' arcs and meshed teeth in their lit colours, LIT_W x LIT_H sprite px over the whole file, so a
                                     vertical StatusBar the size of the box crops it bottom up. The mockup lights the arcs from the base row
                                     up, one row more than twelve times the refill; the box is LIT_BOX: three spare rows on top, the twelve rows
                                     of the arcs (LIT_ARC_TOP .. LIT_ARC_BOTTOM), then LIT_PAD row under them, so a bar at v shows 16 v rows
                                     from the bottom and runs within one row of the mockup all the way (the base plate is in the dark art only).

    python3 tools/assets/generate_hunter_traps.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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


class Sheet:
    """A w x h texel file of cw x ch texel cells, `cols` across. put() lays a layer into cell `index`: (ox, oy) is where the layer's (0, 0)
    sits in the cell, in sprite px; every px must land inside the cell."""

    def __init__(self, w: int, h: int, cw: int, ch: int, cols: int):
        self.w, self.h, self.cw, self.ch, self.cols = w, h, cw, ch, cols
        self.px = bytearray(w * h * 4)

    def put(self, index: int, layer: Layer, ox: int, oy: int, name: str = "layer") -> None:
        spw, sph = self.cw // SCALE, self.ch // SCALE
        cx0, cy0 = (index % self.cols) * spw, (index // self.cols) * sph
        for (x, y), (r, g, b, a) in layer.p.items():
            sx, sy = x + ox, y + oy
            if not (0 <= sx < spw and 0 <= sy < sph):
                raise ValueError(f"{name}: px ({x}, {y}) lands at cell px ({sx}, {sy}), outside the {spw} x {sph} px cell")
            rgba = bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
            for dy in range(SCALE):
                for dx in range(SCALE):
                    i = (((cy0 + sy) * SCALE + dy) * self.w + (cx0 + sx) * SCALE + dx) * 4
                    self.px[i:i + 4] = rgba


def write_tga(path: str, sheet: Sheet) -> None:
    rows = bytearray()
    for i in range(0, len(sheet.px), 4):
        r, g, b, a = sheet.px[i:i + 4]
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, sheet.w, sheet.h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({sheet.w}x{sheet.h}, {os.path.getsize(path)} bytes)")


def out_dir() -> str:
    return os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))


# ---------------------------------------------------------------------------------------------------------------------
# the mockup's numbers
# ---------------------------------------------------------------------------------------------------------------------
TC_X, TC_Y = 113, 22                               # the trap's centre (const TC)
MET = {"lo": "#4a4670", "mid": "#9a96c8", "hi": "#e8e6ff", "dk": "#241c3c"}
FREE, FREE_HI = "#22e0ff", "#b8f6ff"
PLANT, PLANT_HI = "#ffd36a", "#fff1b8"
OPEN_RX, OPEN_RY = 13, 6                           # the open jaws' ellipse
SHUT_R = 10                                        # the sprung jaws' radius
SHUT_BASE = TC_Y + 7                               # drawTrapShut's base row
SLOT_BW, SLOT_BH = 40, 6                           # a slot bar's inside
TRAP_CELLS = ["open", "glow", "shutDark", "shutWhite", "slotBorder", "slotInner"]
TRAP_CELL = (128, 64)                              # texels
OPEN_OX, OPEN_OY = 32, 16                          # the open jaws' centre in its 64 x 32 sprite px cell
SHUT_BOX = (TC_X - 16, TC_Y - 5)                   # the shut jaws' box's top left on the mockup's canvas
SHUT_W, SHUT_H = 32, 16                            # the box, sprite px
LIT_BOX = (TC_X - 16, TC_Y - 7)                    # the lit art's box's top left on the mockup's canvas
LIT_W, LIT_H = 32, 16
LIT_ARC_TOP, LIT_ARC_BOTTOM = 3, 14                # the arcs' rows in it
LIT_PAD = LIT_H - 1 - LIT_ARC_BOTTOM               # rows from the arcs' last row to the bottom of the box (1)
LIT_FILE = (64, 32)                                # hunter_trap_lit.tga, texels


def open_jaws() -> Layer:
    """drawTrapOpen(g, glow = false), relative to the trap's centre."""
    L = Layer()
    rx, ry = OPEN_RX, OPEN_RY
    for y in range(-ry - 1, ry + 2):
        for x in range(-rx - 1, rx + 2):
            e = math.sqrt((x * x) / (rx * rx) + (y * y) / (ry * ry))
            if 0.80 <= e <= 1.08:
                if y < 0:
                    L.paint(x, y, col(MET["hi"] if e > 0.95 else MET["mid"]))
                else:
                    L.paint(x, y, col(MET["mid"] if e > 0.95 else MET["lo"]))
    for i in range(-5, 6):
        x = i * 2
        edge = ry * math.sqrt(max(0, 1 - (i * 2) * (i * 2) / (rx * rx)))
        yb = -jsround(edge) + 1
        L.paint(x, yb, col(MET["hi"]))
        L.paint(x, yb + 1, col(MET["hi"]))
        yf = jsround(edge) - 1
        L.paint(x, yf, col(MET["mid"]))
    L.rect(-rx - 4, 0, 4, 1, col(MET["mid"]))
    L.rect(rx + 1, 0, 4, 1, col(MET["mid"]))
    L.rect(-rx - 5, -1, 1, 3, col(MET["hi"]))
    L.rect(rx + 5, -1, 1, 3, col(MET["hi"]))
    L.rect(-3, -1, 7, 3, col("#8a6a20"))
    L.rect(-2, -1, 5, 2, col(PLANT))
    L.rect(-1, -1, 2, 1, col(PLANT_HI))
    for k in range(4):
        L.rect(rx + 5, 2 + k * 2, 1, 2, col(MET["lo"] if k % 2 else MET["mid"]))
    return L


def open_glow() -> Layer:
    """drawTrapOpen's glow ring, a white mask (the mockup's mint at .10 + .08 * beat is the tint)."""
    L = Layer()
    rx, ry = OPEN_RX, OPEN_RY
    for y in range(-ry - 3, ry + 4):
        for x in range(-rx - 3, rx + 4):
            e = (x * x) / ((rx + 2.5) * (rx + 2.5)) + (y * y) / ((ry + 2.5) * (ry + 2.5))
            if 0.55 < e <= 1:
                L.paint(x, y, (255, 255, 255, 1.0))
    return L


def shut_jaws(mode: str) -> Layer:
    """drawTrapShut as a layer in a box's own px (the mockup's canvas minus the box's top left). mode: "dark" (nothing lit, in SHUT_BOX), "white"
    (the snap's flash, in SHUT_BOX) or "lit" (the arcs and teeth all lit, no base plate, in LIT_BOX)."""
    L = Layer()
    R, base = SHUT_R, SHUT_BASE
    flash, lit = mode == "white", mode == "lit"
    ox, oy = LIT_BOX if lit else SHUT_BOX
    for y in range(base - R - 1, base + 1):
        for x in range(-R - 1, R + 2):
            d = math.sqrt(x * x + (y - base) * (y - base))
            if R - 1.6 <= d <= R + 0.5:
                if flash:
                    c = col("#ffffff")
                elif lit:
                    c = col(FREE_HI if d > R - 0.5 else FREE)
                else:
                    c = col("#3a3460" if d > R - 0.5 else MET["dk"])
                L.paint(TC_X + x - ox, y - oy, c)
    for y in range(base - R + 2, base):
        o = -1 if y % 2 else 1
        c = col("#ffffff") if flash else col(FREE_HI) if lit else col("#3a3460")
        L.paint(TC_X + o - ox, y - oy, c)
        L.paint(TC_X - ox, y - oy, c)
    if not lit:
        L.rect(TC_X - R - 2 - ox, base + 1 - oy, 2 * R + 5, 2, col("#ffffff") if flash else col(MET["lo"]))
        L.rect(TC_X - R - 2 - ox, base + 3 - oy, 2 * R + 5, 1, col(MET["dk"]))
    return L


def slot_frame() -> tuple[Layer, Layer]:
    """drawSlot's bar: the 1 px border (a white mask) and the dark inside, relative to the border's top left."""
    border, inner = Layer(), Layer()
    bw, bh = SLOT_BW, SLOT_BH
    border.rect(0, 0, bw + 2, 1, (255, 255, 255, 1.0))
    border.rect(0, bh + 1, bw + 2, 1, (255, 255, 255, 1.0))
    border.rect(0, 0, 1, bh + 2, (255, 255, 255, 1.0))
    border.rect(bw + 1, 0, 1, bh + 2, (255, 255, 255, 1.0))
    inner.rect(1, 1, bw, bh, col("#120a22"))
    return border, inner


def trap_sheet() -> Sheet:
    sheet = Sheet(512, 256, TRAP_CELL[0], TRAP_CELL[1], 4)
    border, inner = slot_frame()
    layers = {"open": (open_jaws(), OPEN_OX, OPEN_OY), "glow": (open_glow(), OPEN_OX, OPEN_OY),
              "shutDark": (shut_jaws("dark"), 0, 0), "shutWhite": (shut_jaws("white"), 0, 0),
              "slotBorder": (border, 0, 0), "slotInner": (inner, 0, 0)}
    for i, name in enumerate(TRAP_CELLS):
        layer, ox, oy = layers[name]
        sheet.put(i, layer, ox, oy, name)
    return sheet


def lit_sheet() -> Sheet:
    """The lit arcs, LIT_W x LIT_H sprite px over the whole file (SCALE texels a sprite px each way)."""
    sheet = Sheet(LIT_FILE[0], LIT_FILE[1], LIT_FILE[0], LIT_FILE[1], 1)
    sheet.put(0, shut_jaws("lit"), 0, 0, "lit")
    return sheet


def main() -> None:
    here = out_dir()
    os.makedirs(here, exist_ok=True)
    write_tga(os.path.join(here, "hunter_trap.tga"), trap_sheet())
    write_tga(os.path.join(here, "hunter_trap_lit.tga"), lit_sheet())


if __name__ == "__main__":
    main()
