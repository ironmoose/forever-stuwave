#!/usr/bin/env python3
"""Bake the Hunter Gunsight module's range scope: the four zone bands (unlit and lit), their ring lines, the cross hairs, the two
whole rim flashes, the dotted divider, and the small sprites (the skull and its halo, the dead zone strike and melee claws, the burst
rings, the lock-on brackets, the quiver and the two trap slot icons).

The source is the design mockup "Hunter Gunsight Module: Lock-On Scope + Traps" (2026-11-07), drawRadar (the scope the shot timer is
told on) and drawLock / drawSkull / drawBurst / drawLabel / drawSlot. Every sprite px is baked as SCALE x SCALE texels of one flat
colour. Full colour RGBA where the mockup's colour is fixed, white masks (tinted in game) where the colour follows a state.

    hunter_zones.tga     512 x 512  4 x 4 cells of 128 x 128 texels (64 x 64 sprite px), order ZONE_CELLS. The scope's centre (C_X, C_Y)
                                    of the mockup canvas sits at cell px (32, 32): cell px = canvas px - (ZONE_OX, ZONE_OY). The
                                    unlit and lit bands hold only their band's px (a band shows one or the other); the ring lines are
                                    white masks (tinted: the mockup's per state colours); the cross hairs are fixed colour.
    hunter_rings.tga     512 x 512  3 x 3 cells of 160 x 160 texels (80 x 80 sprite px), order RING_CELLS. The scope's centre sits at
                                    cell px (40, 40) (RING_OX, RING_OY); the divider's px are at their canvas x and y.
    hunter_sprites.tga   256 x 512  4 x 8 cells of 64 x 64 texels (32 x 32 sprite px), order SPRITE_CELLS. Every cell's art origin (the
                                    px a sprite is placed by: the skull's centre, a bracket's corner, a pattern's top left) is at cell
                                    px (16, 16).

    python3 tools/assets/generate_hunter_scope.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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
    """A w x h texel file of cells. put() lays a layer into cell `index`: (ox, oy) is where the layer's (0, 0) sits in the cell, in sprite
    px, and every px must land inside the cell (a px outside it is a bug, not a clip)."""

    def __init__(self, w: int, h: int, cell: int, cols: int):
        self.w, self.h, self.cell, self.cols = w, h, cell, cols
        self.px = bytearray(w * h * 4)

    def put(self, index: int, layer: Layer, ox: int, oy: int, name: str = "layer") -> None:
        sp = self.cell // SCALE
        cx0, cy0 = (index % self.cols) * sp, (index // self.cols) * sp
        for (x, y), (r, g, b, a) in layer.p.items():
            sx, sy = x + ox, y + oy
            if not (0 <= sx < sp and 0 <= sy < sp):
                raise ValueError(f"{name}: px ({x}, {y}) lands at cell px ({sx}, {sy}), outside the {sp} px cell")
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
W, H = 150, 86
C_X, C_Y = 38, 37                                  # the scope's centre (const C)
BANDS = [("melee", 0, 7.5), ("dead", 7.5, 12.5), ("ranged", 12.5, 25.5), ("far", 25.5, 30.5)]
RIM0, RIM1 = 31.5, 34.2                            # the rim's inner and outer radius
LINE_RADII = [7.5, 12.5, 25.5, 30.5]
K = {"free": "#22e0ff", "pink": "#ff2e97", "melee": "#ff6a2a", "muted": "#9d93c4", "dark": "#120a22"}
# hex of the dark 'K.dark' in the mockup is '#120a22'; the skull's dark px and the slot bar's inside use it

ZONE_CELLS = ["unlitMelee", "unlitDead", "unlitRanged", "unlitFar", "litMelee", "litDead", "litRanged", "litFar",
              "line75", "line125", "line255", "line305", "cross"]
ZONE_CELL = 128                                    # texels
ZONE_OX, ZONE_OY = 6, 5                            # cell px = canvas px - (6, 5): the centre (38, 37) is cell (32, 32)
RING_CELLS = ["flashRing", "resetRing", "divider"]
RING_CELL = 160
RING_OX, RING_OY = -2, -3                          # cell px = canvas px - (-2, -3): the centre is cell (40, 40)
SPRITE_CELLS = ["skullBody", "skullDark", "skullHalo", "strikeDead", "clawsMelee", "ring5", "ring7",
                "bracketTL", "bracketTR", "bracketBL", "bracketBR", "quiver",
                "flameX", "flameO", "flameOff", "flakeX", "flakeO", "flakeOff"]
SPRITE_CELL = 64
SPRITE_O = 16                                      # every sprite cell's art origin

MOB = [".XXXXX.", "XXXXXXX", "XoOXOoX", "XoOXOoX", "XXXoXXX", ".XXXXX.", ".X.X.X."]
QUIV = ["X.X.X", "X.X.X", "XXXXX", "X...X", "X...X", "XXXXX"]
FLAME = ["...X...", "..XX...", "..XXX..", ".XXXX.X", ".XXOXX.", "XXOOOXX", "XXOOOXX", ".XXOXX."]
FLAKE = ["...X...", ".X.X.X.", "..XXX..", "XXXOXXX", "..XXX..", ".X.X.X.", "...X..."]
WHITE = (255, 255, 255, 1.0)


def band_of(d: float):
    for name, _, hi in BANDS:
        if d < hi:
            return name
    return None


def canvas_px():
    """The mockup's PX: every canvas px within 35.5 of the scope's centre, with its distance (measured from the px's corner)."""
    out = []
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - C_X) ** 2 + (y - C_Y) ** 2)
            if d <= 35.5:
                out.append((x, y, d))
    return out


def zone_colour(band: str, lit: bool, x: int, y: int):
    """drawRadar's fill of one px of a band (on = lit)."""
    if band == "dead":
        if lit:
            return col(K["pink"], 0.55 if (x + y) % 3 == 0 else 0.22)
        return col("#2e1236") if (x + y) % 3 == 0 else col("#160a22")
    if band == "far":
        if lit:
            return col(K["muted"], 0.3) if (x + y) % 2 else col("#120a20")
        return col("#1c1430") if (x + y) % 2 else col("#0c0618")
    if lit:
        return col(K["melee"] if band == "melee" else K["free"], 0.28)
    return col("#1a0c10") if band == "melee" else col("#0c1624")


def zones_sheet() -> Sheet:
    sheet = Sheet(512, 512, ZONE_CELL, 4)
    px = canvas_px()
    for i, name in enumerate(ZONE_CELLS):
        layer = Layer()
        if name.startswith("unlit") or name.startswith("lit"):
            lit = name.startswith("lit")
            want = name[3:].lower() if lit else name[5:].lower()
            for x, y, d in px:
                if d > 30.5 or band_of(d) != want:
                    continue
                layer.paint(x, y, zone_colour(want, lit, x, y))
        elif name.startswith("line"):
            r = LINE_RADII[["line75", "line125", "line255", "line305"].index(name)]
            for x, y, d in px:
                if abs(d - r) < 0.5:
                    layer.paint(x, y, WHITE)
        else:                                      # cross hairs, faint, in the mockup's fixed colour
            c = (157, 147, 196, 0.18)
            for k in range(-30, 31):
                if abs(k) > 3:
                    layer.paint(C_X + k, C_Y, c)
                    layer.paint(C_X, C_Y + k, c)
        sheet.put(i, layer, -ZONE_OX, -ZONE_OY, name)
    return sheet


def rings_sheet() -> Sheet:
    sheet = Sheet(512, 512, RING_CELL, 3)
    px = canvas_px()
    flash, reset, divider = Layer(), Layer(), Layer()
    for x, y, d in px:
        if RIM0 - 1 <= d <= RIM1 + 1:
            flash.paint(x, y, WHITE)
        if RIM0 <= d <= RIM1:
            reset.paint(x, y, WHITE)
    for y in range(6, 72, 2):
        divider.paint(77, y, col("#1c1430"))
    for i, layer in enumerate((flash, reset, divider)):
        sheet.put(i, layer, -RING_OX, -RING_OY, RING_CELLS[i])
    return sheet


def pattern(rows, keep) -> Layer:
    layer = Layer()
    for j, row in enumerate(rows):
        for q, ch in enumerate(row):
            if ch != "." and keep(ch, q, j):
                layer.paint(q, j, WHITE)
    return layer


def ring_points(r: int) -> Layer:
    layer = Layer()
    for y in range(-r - 1, r + 2):
        for x in range(-r - 1, r + 2):
            if abs(math.sqrt(x * x + y * y) - r) < 0.5:
                layer.paint(x, y, WHITE)
    return layer


def sprites_sheet() -> Sheet:
    sheet = Sheet(256, 512, SPRITE_CELL, 4)
    cells: dict[str, Layer] = {}
    body, dark, halo = Layer(), Layer(), Layer()
    for j, row in enumerate(MOB):
        for q, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "X":
                body.paint(q - 3, j - 3, WHITE)
            elif ch == "O":
                body.paint(q - 3, j - 3, (255, 255, 255, 0.35))
            else:
                dark.paint(q - 3, j - 3, col(K["dark"]))
    for j, row in enumerate(MOB):                  # drawSkull's dark halo, a 3 x 1 and a 1 x 3 round every body px
        for q, ch in enumerate(row):
            if ch != ".":
                halo.rect(-4 + q, -3 + j, 3, 1, (10, 4, 22, 0.85))
                halo.rect(-3 + q, -4 + j, 1, 3, (10, 4, 22, 0.85))
    strike = Layer()
    for k in range(-5, 6):
        strike.paint(k, -k, WHITE)
    claws = Layer()
    for x, y in ((-5, -2), (-5, 0), (-5, 2), (5, -2), (5, 0), (5, 2)):
        claws.paint(x, y, WHITE)
    # the lock-on brackets: the corner px at the cell origin, two arms of three px running in toward the skull
    brackets = {}
    for name, sx, sy in (("bracketTL", -1, -1), ("bracketTR", 1, -1), ("bracketBL", -1, 1), ("bracketBR", 1, 1)):
        layer = Layer()
        for i in range(3):
            layer.paint(-sx * i, 0, WHITE)
            layer.paint(0, -sy * i, WHITE)
        brackets[name] = layer
    cells.update({"skullBody": body, "skullDark": dark, "skullHalo": halo, "strikeDead": strike, "clawsMelee": claws,
                  "ring5": ring_points(5), "ring7": ring_points(7), "quiver": pattern(QUIV, lambda ch, q, j: ch == "X"),
                  "flameX": pattern(FLAME, lambda ch, q, j: ch == "X"), "flameO": pattern(FLAME, lambda ch, q, j: ch == "O"),
                  "flameOff": pattern(FLAME, lambda ch, q, j: (q + j) % 2 == 0),
                  "flakeX": pattern(FLAKE, lambda ch, q, j: ch == "X"), "flakeO": pattern(FLAKE, lambda ch, q, j: ch == "O"),
                  "flakeOff": pattern(FLAKE, lambda ch, q, j: (q + j) % 2 == 0)})
    cells.update(brackets)
    for i, name in enumerate(SPRITE_CELLS):
        sheet.put(i, cells[name], SPRITE_O, SPRITE_O, name)
    return sheet


def main() -> None:
    here = out_dir()
    os.makedirs(here, exist_ok=True)
    write_tga(os.path.join(here, "hunter_zones.tga"), zones_sheet())
    write_tga(os.path.join(here, "hunter_rings.tga"), rings_sheet())
    write_tga(os.path.join(here, "hunter_sprites.tga"), sprites_sheet())


if __name__ == "__main__":
    main()
