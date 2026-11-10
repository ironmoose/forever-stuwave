#!/usr/bin/env python3
"""Bake the Priest Gunsight module's 8-bit art: the round shield and the Prayer of Mending pieces.

The source is the design mockup (Priest shield and mending, 2026-11-07, palette BIFROST FROST, rune C): a round Viking
shield of radius R = 27 sprite px with a 2 px rim, an iron band with 8 rivets, planks painted in quarters, a midnight blue
boss and the protection rune (Algiz, 45 degree arms) with its dark 1 px outline. Every sprite px is baked as SCALE x SCALE
texels of one flat colour (no smoothing). The shield pieces share one sprite box, BOX x BOX sprite px with the shield centre
(x 0, y 0 of the mockup's drawShield) at sprite px (CENTER, CENTER), so the module lays every cell on the same spot.

    priest_shield.tga        512 x 512  4 x 4 cells of 128 texels (a 64 sprite px box), order SHIELD_CELLS below:
                                        the dark shield, the clear rim, the cooldown rim, the dark Weakened Soul rim, the dashed
                                        rim (white, tinted in game), the rune and its outline (white, tinted), the hit flash
                                        disc (white), the frost aura and the amber nudge halo (full colour, alpha baked), then
                                        the GHOST, the calm empty look (design mockup "Priest shield, off state", 2026-11-10,
                                        option C): a faint wash with the band and boss as thin rings and the rivets as dots, and
                                        its solid 2 px rim (both full colour, alpha baked; the rune is the shared rune cell).
    priest_shield_glint.tga  512 x 256  GLINT_FRAMES frames of the diagonal glint, same cells.
    priest_shield_rays.tga   256 x 256  the 8 rays round a shield with light in it, an 80 sprite px box (centre RAYS_CENTER).
    priest_shield_ws.tga     128 x 128  the violet Weakened Soul rim alone, the swipe texture of a Cooldown frame.
    priest_shield_lit.tga    128 x 128  the lit shield's interior (x -27..27, y -26..26) STRETCHED over the whole file, so a
                                        vertical StatusBar fills it from the bottom: the engine draws the secret absorb level.
    priest_mending.tga       256 x 256  4 x 4 cells of 64 texels (32 sprite px), order MENDING_CELLS: beads (lit, off,
                                        dashed), the small holder heart, the 2x heart (lit, off, amber, locked dots) and its
                                        glow (white, tinted).
    priest_heart_cd.tga       32 x 32   the heart's cooldown shade, stretched like the lit shield (a top down StatusBar).

    python3 tools/assets/generate_priest_shield.py      (FS_ASSET_OUTPUT_DIR overrides the output directory)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2
R, BOSS = 27, 11
BOX, CENTER = 64, 32               # the shield cell: 64 sprite px, the shield centre at sprite px 32
RAYS_BOX, RAYS_CENTER = 80, 40
CELL = BOX * SCALE                 # 128 texels
GLINT_FRAMES = 8
LIT_X0, LIT_Y0, LIT_W, LIT_H = -27, -26, 55, 53

SHIELD_CELLS = ["dark", "rimClear", "rimCd", "rimWsDark", "rimDash", "rune", "runeLine", "flash", "aura", "halo", "ghost",
                "ghostRim"]
MENDING_CELLS = ["beadLit", "beadOff", "beadDash", "heartSmall", "heartLit", "heartOff", "heartAmber", "heartLocked",
                 "heartGlow"]
MCELL = 32                         # sprite px per mending cell

# PALETTES.AGENT ("BIFROST FROST") of the mockup
LIT = {"top": "#f4ffff", "hi": "#d4fbff", "body": "#9ff0ff", "body2": "#5fd4e8", "deep": "#2fa8c8", "seam": "#3a9ab8",
       "band": "#4a6a8c", "bossOuter": "#061a2c", "bossRing": "#e8ffff", "boss": "#0e3a5c", "bossHi": "#2a78a0",
       "rivet": "#ffffff", "rivetShadow": (10, 60, 90, 0.6)}
DARK = {"plank": "#0e1a34", "plank2": "#0b1530", "seam": "#050a18", "band": "#1e2a4a", "bossOuter": "#3a5a88",
        "boss": "#101c3a", "bossHi": "#1c3058", "rivet": "#a8d8f0", "rivetShadow": (4, 10, 24, 0.9)}
AURA, AURA_OUTER, RAY, RAY_CORE = "#a0f4ff", "#40d0f0", "#c8faff", "#ffffff"
RIM_CLEAR, RIM_CLEAR_HI, RIM_CLEAR_IN = "#5fd4e8", "#d4fbff", "#2a8cb0"
CD_OUTER, CD_IN = "#2a5a6a", "#1e4250"
WS_OUTER, WS_IN, WS_DARK_OUTER, WS_DARK_IN = "#c04cff", "#e08cff", "#2a1a44", "#3a2560"
AMBER = "#ffb648"
# the ghost (option C of the off state mockup): the ground shows through, so every colour is a translucent one
GHOST_FACE = (6, 14, 30, 0.45)
GHOST_BAND, GHOST_BAND_A = "#4a6a8c", 0.55
GHOST_BOSS, GHOST_BOSS_A = "#5fd4e8", 0.45
GHOST_RIVET, GHOST_RIVET_A = "#a8d8f0", 0.7
GHOST_RIM_OUTER_A, GHOST_RIM_INNER_A = 0.75, 0.3

SEAMS = (-19, -10, 10, 19)
# RUNES.C of the mockup: 45 degree arms, 2 px strokes
RUNE_X, RUNE_Y = -5, -6
RUNE = ["XX..XX..XX", ".XX.XX.XX.", "..XXXXXX..", "...XXXX...", "....XX....", "....XX....", "....XX....", "....XX....",
        "....XX....", "....XX....", "....XX....", "....XX....", "....XX...."]
HEART = [".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..."]


def jsround(v: float) -> int:
    """JavaScript's Math.round (halves go up), which the mockup uses."""
    return math.floor(v + 0.5)


def in_disc(x, y, r):
    return x * x + y * y <= r * r + r * 0.8


def boss_disc(x, y, r):
    a, b = x + 0.5, y + 0.5
    return a * a + b * b <= r * r + r * 0.8


def rim_points():
    out = []
    for y in range(-R, R + 1):
        for x in range(-R, R + 1):
            if not in_disc(x, y, R) or in_disc(x, y, R - 2):
                continue
            a = math.atan2(x + 0.01, -y)
            if a < 0:
                a += 2 * math.pi
            outer = not in_disc(x + 1, y, R) or not in_disc(x - 1, y, R) or not in_disc(x, y + 1, R) or not in_disc(x, y - 1, R)
            out.append((x, y, a / (2 * math.pi), outer))
    return out


RIM = rim_points()
RIMSET = {(x, y) for (x, y, _, _) in RIM}


def inside(x, y):
    return in_disc(x, y, R) and (x, y) not in RIMSET


def on_band(x, y):
    return inside(x, y) and not in_disc(x, y, R - 3)


def in_boss(x, y):
    return boss_disc(x, y, BOSS)


RIVETS = []
for i in range(8):
    a = i * math.pi / 4 + math.pi / 8
    RIVETS.append((jsround(math.sin(a) * (R - 2)), jsround(-math.cos(a) * (R - 2))))


def rune_on(j, q):
    return 0 <= j < len(RUNE) and 0 <= q < len(RUNE[0]) and RUNE[j][q] == "X"


def rgba(c):
    if isinstance(c, tuple):
        r, g, b, a = c
        return (r, g, b, int(round(a * 255)))
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 255)


def with_alpha(c, a):
    r, g, b, _ = rgba(c)
    return (r, g, b, int(round(a * 255)))


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = [(0, 0, 0, 0)] * (w * h)

    def put(self, tx, ty, c):
        if 0 <= tx < self.w and 0 <= ty < self.h:
            self.px[ty * self.w + tx] = c

    def blend(self, tx, ty, c):
        if not (0 <= tx < self.w and 0 <= ty < self.h):
            return
        r, g, b, a = c
        i = ty * self.w + tx
        br, bg, bb, ba = self.px[i]
        fa = a / 255
        oa = fa + ba / 255 * (1 - fa)
        if oa <= 0:
            return
        mix = lambda s, d: int(round((s * fa + d * (ba / 255) * (1 - fa)) / oa))
        self.px[i] = (mix(r, br), mix(g, bg), mix(b, bb), int(round(oa * 255)))

    def sprite(self, sx, sy, c, blend=False):
        for dy in range(SCALE):
            for dx in range(SCALE):
                (self.blend if blend else self.put)(sx * SCALE + dx, sy * SCALE + dy, c)


class Cell:
    """One shield cell: sprite px relative to the shield centre."""

    def __init__(self, canvas, index, cols, center=CENTER, cell=BOX):
        self.c = canvas
        self.ox = (index % cols) * cell + center
        self.oy = (index // cols) * cell + center
        self.lo, self.hi = -center, cell - center

    def px(self, x, y, c, blend=False):
        if self.lo <= x < self.hi and self.lo <= y < self.hi:
            self.c.sprite(self.ox + x, self.oy + y, rgba(c) if isinstance(c, str) else c, blend)


def lit_colour(x, y, fill_top=-(R - 1)):
    """The mockup's lit planks, band and boss at full light (fillTop = -(R - 1))."""
    L = LIT
    d = y - fill_top
    if on_band(x, y):
        return L["band"]
    if in_boss(x, y):
        edge = not boss_disc(x, y, BOSS - 1)
        ring = not edge and not boss_disc(x, y, BOSS - 2)
        hi = (x + y < -6) and not edge and not ring
        return L["bossOuter"] if edge else L["bossRing"] if ring else L["bossHi"] if hi else L["boss"]
    pl = 1 if (x >= 0) != (y >= 0) else 0
    c = L["top"] if d == 0 else L["hi"] if d < 3 else L["deep"] if y > R - 8 else (L["body"] if pl else L["body2"])
    if x in SEAMS:
        c = L["hi"] if d == 0 else L["seam"]
    return c


def dark_colour(x, y):
    D = DARK
    if on_band(x, y):
        return D["band"]
    if in_boss(x, y):
        edge = not boss_disc(x, y, BOSS - 1)
        ring = not edge and not boss_disc(x, y, BOSS - 2)
        hi = (x + y < -6) and not edge and not ring
        return D["bossOuter"] if edge else D["bossHi"] if hi else D["boss"]
    pl = 1 if (x >= 0) != (y >= 0) else 0
    c = D["plank"] if pl else D["plank2"]
    if x in SEAMS:
        c = D["seam"]
    return c


def paint_body(cell, colour_of, pal):
    for y in range(-R, R + 1):
        for x in range(-R, R + 1):
            if inside(x, y):
                cell.px(x, y, colour_of(x, y))
    for (x, y) in RIVETS:
        cell.px(x, y, pal["rivet"])
        cell.px(x + 1, y + 1, rgba(pal["rivetShadow"]), blend=True)


def paint_ghost(cell):
    """Option C of the off state mockup: the interior is one faint wash (no planks, no seams); only the band's outermost row
    and the boss's own edge are drawn, as thin rings, and each rivet is one px laid over the band ring (no shadow). Every px is
    one colour, so a rivet blends over the band's as the canvas does."""
    face = rgba(GHOST_FACE)
    for y in range(-R, R + 1):
        for x in range(-R, R + 1):
            if not inside(x, y):
                continue
            c = face
            if on_band(x, y) and not in_disc(x, y, R - 2.5):
                c = with_alpha(GHOST_BAND, GHOST_BAND_A)
            if in_boss(x, y) and not boss_disc(x, y, BOSS - 1):
                c = with_alpha(GHOST_BOSS, GHOST_BOSS_A)
            cell.px(x, y, c)
    for (x, y) in RIVETS:
        cell.px(x, y, with_alpha(GHOST_RIVET, GHOST_RIVET_A), blend=True)


def ring_around(cell, near, far):
    """The mockup's glow ring round the rim: for every outer rim px, one px out (near) and two px out (far), blended as the
    canvas does; never over the shield itself."""
    for (x, y, _, outer) in RIM:
        if not outer:
            continue
        a = math.atan2(y, x)
        dx, dy = jsround(math.cos(a)), jsround(math.sin(a))
        for k, c in ((1, near), (2, far)):
            qx, qy = x + k * dx, y + k * dy
            if not in_disc(qx, qy, R):
                cell.px(qx, qy, c, blend=True)


def shield_atlas():
    canvas = Canvas(512, 512)
    cells = {name: Cell(canvas, i, 4) for i, name in enumerate(SHIELD_CELLS)}
    paint_body(cells["dark"], dark_colour, DARK)
    paint_ghost(cells["ghost"])
    for (x, y, f, outer) in RIM:
        top_left = y < -R + 5 or (x < 0 and y < 0)
        cells["rimClear"].px(x, y, (RIM_CLEAR_HI if top_left else RIM_CLEAR) if outer else RIM_CLEAR_IN)
        cells["rimCd"].px(x, y, CD_OUTER if outer else CD_IN)
        cells["rimWsDark"].px(x, y, WS_DARK_OUTER if outer else WS_DARK_IN)
        if math.floor(f * 40) % 2 == 0:
            cells["rimDash"].px(x, y, "#ffffff")
        cells["ghostRim"].px(x, y, with_alpha(RIM_CLEAR, GHOST_RIM_OUTER_A if outer else GHOST_RIM_INNER_A))
    for j in range(-1, len(RUNE) + 1):
        for q in range(-1, len(RUNE[0]) + 1):
            if rune_on(j, q):
                cells["rune"].px(RUNE_X + q, RUNE_Y + j, "#ffffff")
            elif rune_on(j - 1, q) or rune_on(j + 1, q) or rune_on(j, q - 1) or rune_on(j, q + 1):
                cells["runeLine"].px(RUNE_X + q, RUNE_Y + j, "#ffffff")
    for y in range(-R, R + 1):
        for x in range(-R, R + 1):
            if inside(x, y):
                cells["flash"].px(x, y, "#ffffff")
    ring_around(cells["aura"], with_alpha(AURA, 0.55), with_alpha(AURA_OUTER, 0.22))
    ring_around(cells["halo"], with_alpha(AMBER, 0.45), with_alpha(AMBER, 0.18))
    return canvas


def glint_atlas():
    canvas = Canvas(512, 256)
    for k in range(GLINT_FRAMES):
        cell = Cell(canvas, k, 4)
        gp = (k + 0.5) / GLINT_FRAMES
        gx = jsround(-34 + gp * 68)
        for y in range(-R, R):
            x = gx - (y >> 1)
            if inside(x, y):
                cell.px(x, y, with_alpha("#ffffff", 0.85))
                if inside(x + 1, y):
                    cell.px(x + 1, y, with_alpha("#ffffff", 0.4))
    return canvas


def rays():
    canvas = Canvas(256, 256)
    cell = Cell(canvas, 0, 1, RAYS_CENTER, RAYS_BOX)
    for i in range(8):
        a = i * math.pi / 4
        ln = 5 if i % 2 == 0 else 3
        for r in range(R + 1, R + 3 + ln):
            k = (r - R - 1) / (ln + 1)
            x, y = jsround(math.sin(a) * r), jsround(-math.cos(a) * r)
            if not in_disc(x, y, R):
                cell.px(x, y, with_alpha(RAY_CORE if k < 0.4 else RAY, 1 - k), blend=True)
    return canvas


def ws_rim():
    canvas = Canvas(128, 128)
    cell = Cell(canvas, 0, 1)
    for (x, y, _, outer) in RIM:
        cell.px(x, y, WS_OUTER if outer else WS_IN)
    return canvas


def stretched(w, h, src_w, src_h, colour_at):
    """A sprite of src_w x src_h px stretched over a w x h texel file, nearest: texel (tx, ty) shows sprite px
    (floor(tx * src_w / w), floor(ty * src_h / h)). A StatusBar crops its texture by the fill, so the art must span the file."""
    canvas = Canvas(w, h)
    for ty in range(h):
        for tx in range(w):
            c = colour_at(tx * src_w // w, ty * src_h // h)
            if c is not None:
                canvas.put(tx, ty, c)
    return canvas


def lit_shield():
    body = {}
    for y in range(-R, R + 1):
        for x in range(-R, R + 1):
            if inside(x, y):
                body[(x, y)] = rgba(lit_colour(x, y))
    for (x, y) in RIVETS:
        body[(x, y)] = rgba(LIT["rivet"])
        base = body.get((x + 1, y + 1))
        if base:
            sr, sg, sb, sa = rgba(LIT["rivetShadow"])
            fa = sa / 255
            body[(x + 1, y + 1)] = tuple(int(round(s * fa + d * (1 - fa))) for s, d in zip((sr, sg, sb), base[:3])) + (255,)
    return stretched(128, 128, LIT_W, LIT_H, lambda sx, sy: body.get((sx + LIT_X0, sy + LIT_Y0)))


def heart_cd():
    shade = (10, 4, 22, int(round(0.7 * 255)))
    return stretched(32, 32, 14, 12, lambda sx, sy: shade if HEART[sy // 2][sx // 2] == "X" else None)


class MCell:
    def __init__(self, canvas, index):
        self.c = canvas
        self.ox, self.oy = (index % 4) * MCELL, (index // 4) * MCELL

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.c.sprite(self.ox + xx, self.oy + yy, rgba(c))

    def heart(self, x, y, c, k=1):
        for j, row in enumerate(HEART):
            for q, ch in enumerate(row):
                if ch == "X":
                    self.rect(x + q * k, y + j * k, k, k, c)


BEADS = {"beadLit": ("#ffd36a", "#fff1b8", "#8a5a14"), "beadOff": ("#3a2c5c", "#5a4a88", "#150c26")}


def mending_atlas():
    canvas = Canvas(256, 256)
    cells = {name: MCell(canvas, i) for i, name in enumerate(MENDING_CELLS)}
    for name, (c0, c1, c2) in BEADS.items():
        m, x, y = cells[name], 3, 3                 # the bead's centre sits at (3, 3) of its cell
        m.rect(x - 2, y - 3, 5, 7, c2); m.rect(x - 3, y - 2, 7, 5, c2)
        m.rect(x - 2, y - 2, 5, 5, c0); m.rect(x - 1, y - 3, 3, 1, c0); m.rect(x - 3, y - 1, 1, 3, c0)
        m.rect(x + 3, y - 1, 1, 3, c0); m.rect(x - 1, y + 3, 3, 1, c0)
        m.rect(x - 1, y - 2, 2, 1, c1); m.rect(x - 2, y - 1, 1, 1, c1)
    for (a, b) in ((-1, -3), (1, -3), (-3, -1), (3, -1), (-3, 1), (3, 1), (-1, 3), (1, 3)):
        cells["beadDash"].rect(3 + a, 3 + b, 1, 1, AMBER)
    cells["heartSmall"].heart(0, 0, "#ff5d8f")
    for name, (hc, hl) in {"heartLit": ("#ff5d8f", "#ffc2d6"), "heartOff": ("#3a2c5c", "#5a4a88"),
                           "heartAmber": (AMBER, "#ffe9a8")}.items():
        cells[name].heart(0, 0, hc, 2)
        cells[name].rect(2, 2, 2, 2, hl)
    for j, row in enumerate(HEART):
        for q, ch in enumerate(row):
            if ch == "X" and (q + j) % 2 == 0:
                cells["heartLocked"].rect(q * 2, j * 2, 1, 1, (157, 147, 196, 0.4))
    # the heart's glow, from (HX - 2, HY - 1) of the mockup
    for (x, y, w, h) in ((0, 0, 18, 9), (2, 9, 14, 4), (6, 13, 6, 2)):
        cells["heartGlow"].rect(x, y, w, h, "#ffffff")
    return canvas


def write_tga(path, canvas):
    rows = bytearray()
    for (r, g, b, a) in canvas.px:
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, canvas.w, canvas.h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rows)
    print(f"wrote {path} ({canvas.w}x{canvas.h}, {os.path.getsize(path)} bytes)")


def main():
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                              "forever-stuwave", "Media", "Textures"))
    write_tga(os.path.join(here, "priest_shield.tga"), shield_atlas())
    write_tga(os.path.join(here, "priest_shield_glint.tga"), glint_atlas())
    write_tga(os.path.join(here, "priest_shield_rays.tga"), rays())
    write_tga(os.path.join(here, "priest_shield_ws.tga"), ws_rim())
    write_tga(os.path.join(here, "priest_shield_lit.tga"), lit_shield())
    write_tga(os.path.join(here, "priest_mending.tga"), mending_atlas())
    write_tga(os.path.join(here, "priest_heart_cd.tga"), heart_cd())


if __name__ == "__main__":
    main()
