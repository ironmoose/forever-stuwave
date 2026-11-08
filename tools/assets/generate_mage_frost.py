#!/usr/bin/env python3
"""Bake the Mage Gunsight module's Frost art: the snowflake with its Hagalaz core, the ice crust, the Fingers of Frost crystals.

The source is the design mockup (Mage Gunsight Module, 2026-11-07): drawFrost, the FLAKE / ice core / CRUST / CRYST tables and
the rune. Every sprite px is baked as SCALE x SCALE texels of one flat colour (no smoothing). Full colour RGBA unless noted:
the palettes are part of the art. The snowflake's centre is sprite px (CENTER, CENTER) of each BOX x BOX sprite px cell.

    mage_frost.tga          512 x 512  4 x 4 cells of 128 texels (a 64 sprite px box), order FROST_CELLS below: the snowflake
                                       ready (bright, core included), cooling (dark, core included), the white hit flash, the
                                       cold glow behind a ready flake (colour baked, alpha is pulsed in game), the Frozen haze,
                                       the dim and the idle crust, and six frames of the Nova ring bursting outward.
    mage_frost_glint.tga    512 x 256  GLINT_FRAMES frames of a white band sweeping down the flake's arms, same cells.
    mage_flake_mid.tga      128 x 128  the cooling flake's refilled colours, FLAKE_BOX stretched over the whole file so a
                                       vertical StatusBar fills it from the bottom: the engine draws the Nova cooldown.
    mage_crust_swipe.tga    128 x 128  the lit ice crust ring and its spikes, MIRRORED left to right: a Cooldown swipe keeps the
                                       arc from where the elapsed time ends back to 12 o'clock, the mockup keeps it from 12
                                       o'clock on, so the mirror draws the mockup's arc.
    mage_fingers.tga         64 x 64   2 x 2 cells of 32 texels (16 sprite px): a Fingers of Frost crystal lit, dark, and the
                                       cold outline round a lit one (colour baked, alpha pulsed in game).

    python3 tools/assets/generate_mage_frost.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
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


BOX, CENTER, CELL = 64, 32, 128            # the flake cells: 64 sprite px, the flake centre at sprite px 32
FROST_CELLS = ["flakeReady", "flakeOff", "flakeFlash", "flakeGlow", "haze", "crustDim", "crustIdle",
               "nova1", "nova2", "nova3", "nova4", "nova5", "nova6"]
NOVA_RADII = (12, 15, 18, 20, 23, 26)
GLINT_FRAMES = 8
FLAKE_BOX = (-16, -16, 33, 33)             # x, y, w, h from the flake centre: the StatusBar's art box (stretched over mage_flake_mid)
FING_CELL, FING_ORIGIN = 32, (2, 2)        # a crystal's 11 x 11 sprite px sit at (2, 2) of its 16 sprite px cell
FING_CELLS = ["on", "off", "glow"]


def hex_in(x, y, w, h):
    ax = abs(x)
    return ax <= w and abs(y) <= h + (w - ax) // 2


def ring(R, th):
    out = []
    for y in range(-R - 1, R + 2):
        for x in range(-R - 1, R + 2):
            if not in_disc(x, y, R) or in_disc(x, y, R - th):
                continue
            a = math.atan2(x + 0.01, -y)
            if a < 0:
                a += 2 * math.pi
            outer = (not in_disc(x + 1, y, R)) or (not in_disc(x - 1, y, R)) or (not in_disc(x, y + 1, R)) or (not in_disc(x, y - 1, R))
            out.append((x, y, a / (2 * math.pi), outer))
    return sorted(out, key=lambda p: p[2])


def build_flake():
    m: dict[tuple[int, int], int] = {}
    D = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]

    def add(x, y, k):
        if (x, y) not in m or k > m[(x, y)]:
            m[(x, y)] = k

    for i, d in enumerate(D):
        diag = i % 2 == 1
        L = 11 if diag else 16
        for r in range(1, L + 1):
            add(d[0] * r, d[1] * r, 2 if r == L else 1)
        nl, nr = D[(i + 7) % 8], D[(i + 1) % 8]
        for b, n in ([(9, 1)] if diag else [(11, 2), (14, 1)]):
            for k in range(1, n + 1):
                add(d[0] * b + nl[0] * k, d[1] * b + nl[1] * k, 0)
                add(d[0] * b + nr[0] * k, d[1] * b + nr[1] * k, 0)
    return [(x, y, k) for (x, y), k in m.items()]


FLAKE = build_flake()
FLAKE_NEW = [p for p in FLAKE if not hex_in(p[0], p[1], 5, 3)]
TIPS = [p for p in FLAKE if p[2] == 2]
RUNE_HAGL = [(0, y) for y in range(-3, 4)] + [q for k in (1, 2) for q in ((k, k), (-k, k), (k, -k), (-k, -k))]
FLAKE_COLOURS = {
    "ready": ["#5fd4e8", "#b4f4ff", "#f4ffff"],
    "mid": ["#2a8cb0", "#4ab4d4", "#7fe0f4"],
    "off": ["#1a2644", "#24345c", "#2e4270"],
}


def draw_core(state):
    """The 9 x 9 ice hexagon holding Hagalaz (mockup drawIceCore): dark edge, cold fill lit top left, a 4 neighbour dark line
    round the rune. state: ready (bright), mid (the refilled colours), off (dark), flash (white)."""
    L = Layer()
    ready, flash = state == "ready", state == "flash"
    on = state in ("ready", "mid", "flash")
    for y in range(-5, 6):
        for x in range(-5, 6):
            if not hex_in(x, y, 4, 2):
                continue
            edge = (not hex_in(x + 1, y, 4, 2)) or (not hex_in(x - 1, y, 4, 2)) or (not hex_in(x, y + 1, 4, 2)) or (not hex_in(x, y - 1, 4, 2))
            if edge:
                c = ("#9ff0ff" if (x <= 0 and y <= 0) else "#5fd4e8") if ready else ("#2a8cb0" if on else "#24345c")
            else:
                c = ("#2a78a8" if x + y < -2 else "#1e5a88") if ready else ("#164a6c" if on else "#0c1630")
            if flash:
                c = "#ffffff" if edge else "#7fe0f4"
            L.paint(x, y, col(c))
    rune_col = "#ffffff" if (flash or ready) else "#3a5a88"
    line = "#061a2c" if (ready or flash) else "#080e1c"
    rset = set(RUNE_HAGL)
    done = set()
    for (x, y) in RUNE_HAGL:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            k = (x + dx, y + dy)
            if k not in rset and k not in done:
                done.add(k)
                L.paint(k[0], k[1], col(line))
    for (x, y) in RUNE_HAGL:
        L.paint(x, y, col(rune_col))
    return L


def draw_flake(state):
    L = Layer()
    for (x, y, k) in FLAKE_NEW:
        c = "#ffffff" if state == "flash" else FLAKE_COLOURS["ready" if state == "ready" else state][k]
        L.paint(x, y, col(c))
    L.over(draw_core(state))
    return L


def flake_glow():
    """The cold glow behind a ready flake: every 4 neighbour of an arm px (k >= 1), alpha stacking where they overlap."""
    L = Layer()
    for (x, y, k) in FLAKE_NEW:
        if k >= 1:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                L.paint(x + dx, y + dy, col("#40d0f0", 0.18))
    return L


def haze():
    L = Layer()
    for y in range(-17, 18):
        for x in range(-17, 18):
            if in_disc(x, y, 17) and (x * 7 + y * 13 + 400) % 17 == 0:
                L.paint(x, y, col("#9ff0ff", 0.30))
    return L


CRUST = ring(20, 2)


def build_spikes():
    out = []
    for i, p in enumerate([q for q in CRUST if q[3]]):
        if i % 5 == 0:
            a = math.atan2(p[1], p[0])
            dx, dy = jsround(math.cos(a)), jsround(math.sin(a))
            out.append((p[0] + dx, p[1] + dy))
            if i % 10 == 0:
                out.append((p[0] + 2 * dx, p[1] + 2 * dy))
    return out


SPIKES = build_spikes()


def crust_lit():
    L = Layer()
    for (x, y, f, outer) in CRUST:
        L.paint(x, y, col("#d4fbff" if outer else "#7fe0f4"))
    for (x, y) in SPIKES:
        L.paint(x, y, col("#f4ffff"))
    return L


def crust_dim():
    L = Layer()
    for (x, y, f, outer) in CRUST:
        L.paint(x, y, col("#16304a" if outer else "#102438"))
    return L


def crust_idle():
    L = Layer()
    for i, (x, y, f, outer) in enumerate(CRUST):
        if outer and i % 3 == 0:
            L.paint(x, y, col("#18213e"))
    return L


def nova_ring(r):
    L = Layer()
    for i, (x, y, f, outer) in enumerate(ring(r, 1)):
        if i % 2 == 0:
            L.paint(x, y, col("#9ff0ff"))
    return L


def glint_frame(k):
    """A white band four rows tall, centred on the sweep row (the mockup's two rows, widened so eight frames cover the arms)."""
    L = Layer()
    gp = (k + 0.5) / GLINT_FRAMES
    gy = jsround(-17 + gp * 34)
    for (x, y, _) in FLAKE_NEW:
        if gy - 1 <= y <= gy + 2:
            L.paint(x, y, col("#ffffff"))
    return L


CRYST = ["....W......", "...WLM.....", "...WLM.....", "...WLM..W..", "W..WLM.WLM.", "WM.WLM.WLM.", "WLMWLM.WLM.", "WLMWLMMWLM.",
         "WLMWLLMWLMM", "WLMWLLMWLMM", ".DDDDDDDDD."]
CRYST_LIT = {"W": "#ffffff", "L": "#9ff0ff", "M": "#2fa8c8", "D": "#1e78a0"}
CRYST_OFF = {"W": "#2e4270", "L": "#24345c", "M": "#1a2644", "D": "#141c36"}


def crystal(pal):
    L = Layer()
    for j, row in enumerate(CRYST):
        for q, ch in enumerate(row):
            if ch != ".":
                L.paint(q, j, col(pal[ch]))
    return L


def crystal_glow():
    L = Layer()
    for j, row in enumerate(CRYST):
        for q, ch in enumerate(row):
            if ch == ".":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, -1)):
                rr = CRYST[j + dy] if 0 <= j + dy < len(CRYST) else None
                c2 = rr[q + dx] if rr is not None and 0 <= q + dx < len(rr) else "."
                if c2 == ".":
                    L.paint(q + dx, j + dy, col("#40d0f0", 0.48))
    return L


def frost_atlas():
    a = Atlas(512, 512)
    layers = {
        "flakeReady": draw_flake("ready"), "flakeOff": draw_flake("off"), "flakeFlash": draw_flake("flash"),
        "flakeGlow": flake_glow(), "haze": haze(), "crustDim": crust_dim(), "crustIdle": crust_idle(),
    }
    for i, r in enumerate(NOVA_RADII):
        layers[f"nova{i + 1}"] = nova_ring(r)
    for name, layer in layers.items():
        i = FROST_CELLS.index(name)
        w = cell_window(i, 4, CELL)
        a.blit(layer, w[0] + CENTER, w[1] + CENTER, w, name)
    return a


def glint_atlas():
    a = Atlas(512, 256)
    for k in range(GLINT_FRAMES):
        w = cell_window(k, 4, CELL)
        a.blit(glint_frame(k), w[0] + CENTER, w[1] + CENTER, w, f"glint{k}")
    return a


def flake_mid():
    x0, y0, bw, bh = FLAKE_BOX
    return stretched(draw_flake("mid"), (x0, y0, bw, bh), 128, 128)


def crust_swipe():
    a = Atlas(128, 128)
    w = (0, 0, 64, 64)
    a.blit(crust_lit().mirrored(), CENTER, CENTER, w, "crust")
    return a


def fingers_atlas():
    a = Atlas(64, 64)
    for name, layer in (("on", crystal(CRYST_LIT)), ("off", crystal(CRYST_OFF)), ("glow", crystal_glow())):
        w = cell_window(FING_CELLS.index(name), 2, FING_CELL)
        a.blit(layer, w[0] + FING_ORIGIN[0], w[1] + FING_ORIGIN[1], w, name)
    return a


def main():
    here = out_dir()
    write_tga(os.path.join(here, "mage_frost.tga"), frost_atlas())
    write_tga(os.path.join(here, "mage_frost_glint.tga"), glint_atlas())
    write_tga(os.path.join(here, "mage_flake_mid.tga"), flake_mid())
    write_tga(os.path.join(here, "mage_crust_swipe.tga"), crust_swipe())
    write_tga(os.path.join(here, "mage_fingers.tga"), fingers_atlas())


if __name__ == "__main__":
    main()
