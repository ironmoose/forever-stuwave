#!/usr/bin/env python3
"""Bake the Druid Gunsight module's 8-bit art: the beast eyes of every form, the glyphs between them, the Eclipse moons, the claw
gashes, the bar frames, the chips and the lane icons.

The design is the mockup "Druid Gunsight Module: Wildshape Eyes" (2026-11-16): a pair of eyes watches from a thicket and changes with
the form (Moonkin or caster owl eyes, Cat slit eyes, Bear angry eyes, Restoration leaf eyes). Under them one gauge per form
(Eclipse moons, five claw gashes with the energy bar, the rage bar with its ability ticks, two heal-over-time lanes). This file is the
single art source: the module reads the packing from DruidArt.lua and the mockup page is built from the same sprites by
tools/assets/druid_mockup_build.py, so the page the art was judged on and the shipped art cannot drift.

Every sprite px is baked as SCALE x SCALE texels of one flat colour, so the art stays blocky under the client's filter. Layers that
the module tints are grey (white) masks; everything the module never tints keeps its colours.

    druid_gunsight.tga     512 x 512 atlas of everything the module places by name (see DruidArt.lua)
    druid_slash_lit.tga    32 x 64   a lit claw gash, a StatusBar over the dark one: the engine shows it when the combo count reaches its slot
    druid_slash_flare.tga  32 x 64   the white halo of a gash, driven the same way by a bar that is full only at five points
    druid_energy_fill.tga  256 x 16  the energy fill (96 x 6 sprite px at the top left of a 128 x 8 box: the bar's maximum is scaled by FILL_BOX)
    druid_rage_fill.tga    256 x 32  the rage fill (96 x 10 in a 128 x 16 box)
    druid_chip_sp.tga      32 x 32   the Shifting Power chip, lit (a vertical StatusBar fills it from the bottom over the cooldown)
    druid_chip_pb.tga      32 x 32   the Primal Bite chip, lit
    druid_chip_sm.tga      32 x 32   the Swiftmend flower, lit

The packing is written out as forever-stuwave/Modules/CombatHud/DruidArt.lua (FS.DruidArt): every sprite's atlas rect and origin, and
the geometry (GEOM) both the module and the mockup page use. Do not edit it by hand; gunsightdruid-harness.py regenerates it and fails
when the committed copy differs.

    python3 tools/assets/generate_druid_gunsight.py      (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                           FS_ART_LUA_OUTPUT the manifest path)
"""

from __future__ import annotations

import math
import os
import struct

SCALE = 2                       # texels per sprite px
PAD = 1                         # empty sprite px round every packed sprite

# ---------------------------------------------------------------------------------------------------------------------
# Colours (Theme.lua's synthwave tokens; the module takes the live ones from Theme, these are for the baked colours)
# ---------------------------------------------------------------------------------------------------------------------
OUT, DARKV, MIDV, LINE = "#120822", "#170c2a", "#2a1846", "#3a2168"
VIOLET, CYAN, AMBER, GOLD, WARM, RED = "#a855f7", "#22e0ff", "#ffb648", "#ffd23f", "#ff3d1f", "#ff3b4e"
GREEN, PINK, WHITE, MUTED = "#39ff14", "#ff4dd8", "#f3fbff", "#9d93c4"
PUPIL = "#0a0416"


def jround(v: float) -> int:
    return math.floor(v + 0.5)


def hexrgb(h: str):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def tohex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, int(v))):02x}" for v in rgb)


def mix(a: str, b: str, k: float) -> str:
    A, B = hexrgb(a), hexrgb(b)
    return tohex(tuple(jround(x + (y - x) * k) for x, y in zip(A, B)))


def ramp(base: str) -> dict:
    return {"deep": mix(base, "#000000", .72), "lo": mix(base, "#000000", .45), "mid": base,
            "hi": mix(base, "#ffffff", .42), "top": mix(base, "#ffffff", .8)}


def grey(v: int) -> str:
    return tohex((v, v, v))


class Layer:
    """A sparse layer of sprite px: (x, y) -> (r, g, b, a 0..1), source over."""

    def __init__(self):
        self.p: dict[tuple[int, int], tuple[float, float, float, float]] = {}

    def px(self, x: int, y: int, h: str, a: float = 1.0) -> None:
        if a <= 0:
            return
        r, g, b = hexrgb(h)
        old = self.p.get((x, y))
        if old is None or a >= 1.0:
            self.p[(x, y)] = (r, g, b, min(a, 1.0))
            return
        orr, og, ob, oa = old
        na = a + oa * (1 - a)
        self.p[(x, y)] = ((r * a + orr * oa * (1 - a)) / na, (g * a + og * oa * (1 - a)) / na,
                          (b * a + ob * oa * (1 - a)) / na, na)

    def rect(self, x: int, y: int, w: int, h: int, c: str, a: float = 1.0) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c, a)

    def has(self, x: int, y: int) -> bool:
        return (x, y) in self.p

    def shifted(self, dx: int, dy: int) -> "Layer":
        o = Layer()
        o.p = {(x + dx, y + dy): v for (x, y), v in self.p.items()}
        return o


# ---------------------------------------------------------------------------------------------------------------------
# Geometry: the one copy, in sprite px on the 150 x 86 canvas (the module and the mockup read it from DruidArt.lua)
# ---------------------------------------------------------------------------------------------------------------------
GEOM = {
    "W": 150, "H": 86,
    "EYE_Y": 16, "EYE_L": 43, "EYE_R": 107,      # the eyes' centre px; the right eye is the left one mirrored
    "GLYPH_X": 75, "GLYPH_Y": 16,                # the form glyph between them
    "CUE_Y": 36,                                 # the cue word's centre row
    # moons (Eclipse): four sockets, the drain bar, the seconds
    "MOON_X": 29, "MOON_STEP": 24, "MOON_Y": 43, "MOON_N": 4,
    "DRAIN_X": 29, "DRAIN_Y": 69, "DRAIN_W": 91,  # the drain bar's frame box (inner is 2 less)
    "SECS_X": 124, "SECS_Y": 72,
    # claws (Cat): five gashes along one rake, the energy bar, its number, the Shifting Power chip
    "SLASH_X": 28, "SLASH_STEP": 21, "SLASH_Y": 42, "SLASH_DY": [3, 1, 0, 1, 3], "SLASH_N": 5,
    "ENERGY_X": 14, "ENERGY_Y": 73, "BAR_W": 98, "BAR_H": 8,    # the frame box; the fill sits 1 px inside it
    "FILL_W": 96, "FILL_BOX_W": 128,                              # the fill art's width and its file's width (sprite px)
    "NOTCH_ENERGY": 55,                                           # Shifting Power: energy under this is a good time to use it
    "NUM_X": 116, "NUM_Y": 77,
    "CHIP_X": 131, "CHIP_Y": 66, "CHIP_S": 16,
    # paws (Bear): the rage bar, the tick row, the Lacerate pips
    "RAGE_X": 14, "RAGE_Y": 46, "RAGE_H": 12,
    "TICK_Y": 59, "LETTER_Y": 63,
    "PIP_X": 15, "PIP_STEP": 10, "PIP_Y": 73,
    "RAGE_NUM_Y": 52, "RAGE_CHIP_Y": 46,
    # lanes (Restoration)
    "LANE_X": 28, "LANE_W": 72, "LANE_H": 9, "LANE_Y": [44, 58], "ICON_X": 14, "ICON_S": 11,
    "LANE_SECS_X": 103, "FLOWER_X": 128, "FLOWER_Y": 44,
}

# ---------------------------------------------------------------------------------------------------------------------
# Eyes. Every eye is drawn around its centre px (0, 0); the sprite origin is that px.
# ---------------------------------------------------------------------------------------------------------------------
FORMS = {"moon": CYAN, "cat": GOLD, "bear": WARM, "tree": GREEN}
FORM_ORDER = ["moon", "cat", "bear", "tree"]


def moon_eye(hot: bool = False) -> Layer:
    """The caster / Moonkin owl eye: a round cyan iris in a violet feather ring."""
    L = Layer()
    P = ramp(CYAN)
    V = ramp(VIOLET)
    if hot:
        P = {k: mix(v, "#ffffff", .3) for k, v in P.items()}
    for dy in range(-9, 10):
        for dx in range(-9, 10):
            d = math.hypot(dx, dy)
            if d > 7.6:
                continue
            if d > 6.6:
                c = OUT
            elif d > 5.5:
                c = V["hi"] if dy < -2 else (V["mid"] if dy < 2 else V["lo"])
            elif (dx / 1.9) ** 2 + (dy / 3.3) ** 2 <= 1.0:
                c = PUPIL
            else:
                band = dy + (dx % 2) * 0.0
                if d > 4.5:
                    c = P["lo"]
                elif band < -2.2:
                    c = P["hi"]
                elif band < 1.4:
                    c = P["mid"]
                else:
                    c = P["lo"] if (dx + dy) % 2 else P["mid"]
                if -2.8 < band < -1.6 and (dx + dy) % 2 == 0:
                    c = P["hi"]
            L.px(dx, dy, c)
    for p in ((-3, -3), (-2, -3), (-3, -2)):
        L.px(p[0], p[1], "#ffffff")
    L.px(2, 2, P["top"])
    # feather brow: an arc over the ring with a tuft at each end
    for deg in range(-72, 73, 6):
        a = math.radians(deg)
        x, y = jround(9.0 * math.sin(a)), jround(-9.0 * math.cos(a))
        L.px(x, y, V["lo"])
    for x, y in ((-9, -4), (-10, -3), (9, -4), (10, -3), (-8, -6), (8, -6)):
        L.px(x, y, V["mid"])
    return L


def cat_eye(hot: bool = False) -> Layer:
    """The Cat's almond eye with a slit pupil; the inner corner (right side of the left eye) sits low."""
    L = Layer()
    P = ramp(GOLD)
    if hot:
        P = {k: mix(v, "#ffffff", .18) for k, v in P.items()}
    for dx in range(-12, 13):
        t = abs(dx) / 12.0
        hh = 6.0 * (1 - t ** 1.7)
        sh = 0.27 * dx
        top, bot = -hh + sh, hh + sh
        for dy in range(math.floor(top) - 1, math.ceil(bot) + 2):
            if dy < top - 0.9 or dy > bot + 0.9:
                continue
            edge = dy < top + 0.9 or dy > bot - 0.9
            if edge:
                c = OUT
            elif dy < top + 2.0:
                c = P["deep"] if dx % 2 else P["lo"]
            else:
                y01 = (dy - top) / max(bot - top, 1)
                if y01 < .38:
                    c = P["hi"]
                elif y01 < .72:
                    c = P["mid"]
                else:
                    c = P["lo"] if (dx + dy) % 2 else P["mid"]
                if abs(dx) > 8:
                    c = P["lo"] if (dx + dy) % 2 == 0 else P["mid"]
            # the slit pupil
            if not edge and dy >= top + 1.6 and dy <= bot - 0.6:
                if abs(dx) <= 0 or (abs(dx) <= 1 and top + 3 <= dy <= bot - 2):
                    c = PUPIL
            L.px(dx, dy, c)
    for p in ((-5, -2), (-4, -2), (-5, -1)):
        L.px(p[0], p[1] + jround(0.27 * p[0]), "#ffffff")
    return L


def bear_eye(hot: bool = False) -> Layer:
    """The Bear's small angry eye under a heavy brow that slopes down toward the nose."""
    L = Layer()
    P = ramp(WARM)
    BR = ramp("#8a2a3c")
    if hot:
        P = {k: mix(v, "#ffffff", .2) for k, v in P.items()}
    P["hi"] = mix(P["hi"], AMBER, .5)
    RX, RY = 8.4, 4.7
    for dx in range(-9, 10):
        cut = -3.0 + 0.40 * dx
        for dy in range(-7, 8):
            e = (dx / RX) ** 2 + (dy / RY) ** 2
            if e <= 1.0 and dy >= cut:
                if e > 0.74 or dy <= cut + 0.9:
                    c = OUT
                elif e < 0.22:
                    c = P["top"] if hot else P["hi"]
                elif e < 0.5:
                    c = P["hi"] if dy < 1 else P["mid"]
                else:
                    c = P["mid"] if (dx + dy) % 2 else P["lo"]
                L.px(dx, dy, c)
    for p in ((1, -1), (2, -1), (1, 0), (2, 0), (1, 1), (2, 1)):
        L.px(p[0], p[1], PUPIL)
    L.px(-2, -1, "#ffffff")
    L.px(-3, -1, P["top"])
    for dx in range(-10, 11):
        cut = -3.0 + 0.40 * dx
        y = jround(cut) - 1
        L.px(dx, y, BR["hi"] if dx % 3 == 0 else BR["mid"])
        L.px(dx, y - 1, BR["mid"] if dx % 2 else BR["lo"])
        L.px(dx, y - 2, BR["lo"])
        if abs(dx) > 5:
            L.px(dx, y - 3, BR["deep"])
    return L


def tree_eye(hot: bool = False) -> Layer:
    """The Restoration eye: a soft leaf-shaped green eye with a bright mote for a pupil."""
    L = Layer()
    P = ramp(GREEN)
    if hot:
        P = {k: mix(v, "#ffffff", .28) for k, v in P.items()}
    for dx in range(-11, 12):
        t = abs(dx) / 11.0
        hh = 6.6 * (1 - t ** 2.1)
        for dy in range(-8, 9):
            if abs(dy) > hh + 0.9:
                continue
            edge = abs(dy) > hh - 0.9
            if edge:
                c = OUT
            else:
                y01 = (dy + hh) / max(2 * hh, 1)
                if y01 < .4:
                    c = P["hi"]
                elif y01 < .7:
                    c = P["mid"]
                else:
                    c = P["lo"] if (dx + dy) % 2 else P["mid"]
                if abs(dx) > 7:
                    c = P["lo"] if (dx + dy) % 2 == 0 else P["mid"]
            L.px(dx, dy, c)
    # the mote: a round bright pupil with a soft ring
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            d = math.hypot(dx, dy)
            if d <= 1.6:
                L.px(dx, dy, "#f2ffe6")
            elif d <= 2.7:
                L.px(dx, dy, P["lo"] if (dx + dy) % 2 else PUPIL)
    L.px(-1, -1, "#ffffff")
    # a leaf on the brow, outer upper corner
    for x, y, c in ((-9, -7, P["lo"]), (-10, -8, P["mid"]), (-11, -9, P["hi"]), (-8, -8, P["mid"]), (-9, -9, P["lo"])):
        L.px(x, y, c)
    return L


EYE_FN = {"moon": moon_eye, "cat": cat_eye, "bear": bear_eye, "tree": tree_eye}


def extents(L: Layer):
    xs = [p[0] for p in L.p]
    ys = [p[1] for p in L.p]
    return min(xs), max(xs), min(ys), max(ys)


def eye_half(L: Layer, form: str) -> Layer:
    """The lid half down: everything above the cut becomes lid, the cut a dark line."""
    x0, x1, y0, y1 = extents(L)
    cut = y0 + jround((y1 - y0) * 0.5)
    lid = mix(FORMS[form], "#000000", .78)
    O = Layer()
    for (x, y), v in L.p.items():
        if y > cut:
            O.p[(x, y)] = v
        elif y == cut:
            O.px(x, y, OUT)
        elif y >= cut - 2:
            O.px(x, y, lid)
        else:
            O.px(x, y, mix(lid, OUT, .5)) if y > y0 + 2 else None
    # keep it a clean lid: drop the tufts and brows well above the cut
    O.p = {k: v for k, v in O.p.items() if k[1] >= cut - 3}
    return O


def eye_closed(L: Layer, form: str) -> Layer:
    """A shut eye: one dark lash line that sags in the middle, lit underneath."""
    x0, x1, y0, y1 = extents(L)
    hw = max(abs(x0), abs(x1)) - 1
    base = jround((y0 + y1) / 2)
    O = Layer()
    for dx in range(-hw, hw + 1):
        sag = jround(1.8 * (1 - (dx / hw) ** 2))
        slant = jround(0.27 * dx) if form == "cat" else (jround(0.2 * dx) if form == "bear" else 0)
        y = base + sag + slant
        O.px(dx, y, OUT)
        O.px(dx, y + 1, mix(FORMS[form], "#000000", .5))
    return O


def eye_glow(L: Layer) -> Layer:
    """A soft halo mask round the open eye."""
    O = Layer()
    for (x, y) in L.p:
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if (x + dx, y + dy) in L.p:
                    continue
                d = max(abs(dx), abs(dy))
                a = {1: .55, 2: .3, 3: .12}.get(d, 0)
                key = (x + dx, y + dy)
                if key not in O.p or O.p[key][3] < a:
                    O.p[key] = (255, 255, 255, a)
    return O


# ---------------------------------------------------------------------------------------------------------------------
# Glyphs (grey masks 0..255 tinted by the module), 13 x 13 around the centre px
# ---------------------------------------------------------------------------------------------------------------------
def glyph_moon() -> Layer:
    L = Layer()
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            if math.hypot(dx + 1, dy) <= 5.6 and math.hypot(dx - 1.4, dy - 0.2) > 4.9:
                v = 255 if dx < -3 else 205
                L.px(dx, dy, grey(v))
    for x, y in ((5, -4), (4, -3), (6, -3), (5, -2), (5, -3)):
        L.px(x, y, grey(255 if (x, y) == (5, -3) else 190))
    return L


def glyph_paw(claws: bool) -> Layer:
    L = Layer()
    if not claws:
        for dy in range(-2, 7):
            for dx in range(-6, 7):
                if (dx / 4.6) ** 2 + ((dy - 2.5) / 3.3) ** 2 <= 1:
                    L.px(dx, dy, grey(255 if dy < 3 else 200))
        for cx, cy in ((-4.6, -2.2), (-1.6, -4.4), (1.6, -4.4), (4.6, -2.2)):
            for dy in range(-7, 1):
                for dx in range(-7, 8):
                    if math.hypot(dx - cx, dy - cy) <= 1.75:
                        L.px(dx, dy, grey(235))
    else:
        # three claws, each a pointed wedge, with a hot arch across their tops
        for cx, lean in ((-4, -1), (0, 0), (4, 1)):
            for k in range(0, 13):
                w = (3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1)[k]
                x0 = cx - w // 2 + jround(lean * k / 12.0)
                for i in range(w):
                    L.px(x0 + i, -6 + k, grey(255 if i == 0 else 205))
        for x in range(-6, 7):
            L.px(x, -7 + (1 if abs(x) > 4 else 0), grey(150))
    return L


def glyph_leaf() -> Layer:
    L = Layer()
    for i in range(0, 101):
        t = i / 100.0
        cx, cy = -5 + 10 * t, 5 - 10 * t
        hw = 3.4 * math.sin(math.pi * t)
        for k in range(-4, 5):
            if abs(k) <= hw:
                px = jround(cx + k * 0.7071)
                py = jround(cy + k * 0.7071)
                L.px(px, py, grey(255 if k <= 0 else 200))
    for i in range(0, 10):
        L.px(-5 + i, 5 - i, grey(120))
    L.px(-6, 6, grey(160))
    L.px(-7, 7, grey(160))
    return L


GLYPHS = {"moon": glyph_moon, "cat": lambda: glyph_paw(False), "bear": lambda: glyph_paw(True), "tree": glyph_leaf}

# ---------------------------------------------------------------------------------------------------------------------
# The thicket: vine corners
# ---------------------------------------------------------------------------------------------------------------------
STEM_A, STEM_B, LEAF_A, LEAF_B = "#1f3d3a", "#2f6659", "#2b5a45", "#3f8a64"


def ivy() -> tuple[Layer, Layer]:
    """A vine curling out of the top left corner: the vine itself (colour) and its buds (a white mask)."""
    body, buds = Layer(), Layer()
    pts = []
    for i in range(0, 41):
        t = i / 40.0
        x = 1 + 20 * t
        y = 9 * (1 - t) ** 1.6 + 1.5 * math.sin(t * 9) * (1 - t)
        pts.append((jround(x), jround(y)))
    for x, y in pts:
        body.px(x, y, STEM_B)
        body.px(x, y + 1, STEM_A)
    for (x, y), up in (((6, 6), False), ((11, 4), True), ((16, 3), False)):
        for k in range(1, 4):
            body.px(x + k, y + (k if not up else -k) // 2 + (1 if up else 2), LEAF_B if k < 3 else LEAF_A)
            body.px(x + k, y + (k if not up else -k) // 2 + (2 if up else 3), LEAF_A)
        body.px(x, y + (0 if up else 1), STEM_B)
    # a hanging tendril down the left edge with a bud
    for yy in range(3, 15):
        body.px(1 + (1 if yy % 5 < 2 else 0), yy, STEM_B)
        body.px(0 + (1 if yy % 5 < 2 else 0), yy, STEM_A)
    for x, y in ((21, 2), (22, 2), (22, 1), (1, 15), (2, 15), (1, 16)):
        buds.px(x, y, grey(255))
    return body, buds


# ---------------------------------------------------------------------------------------------------------------------
# Moons
# ---------------------------------------------------------------------------------------------------------------------
def moon_shape(r_out=8.4, off=(3.0, -1.0), r_in=7.0):
    pts = set()
    for y in range(0, 19):
        for x in range(0, 19):
            if math.hypot(x - 9, y - 9) <= r_out and math.hypot(x - 9 - off[0], y - 9 - off[1]) > r_in:
                pts.add((x, y))
    return pts


MOON_PTS = moon_shape()


def moon_lit() -> Layer:
    L = Layer()
    for (x, y) in MOON_PTS:
        edge = any((x + dx, y + dy) not in MOON_PTS for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        v = 255 if edge and x < 9 else (215 if edge else (235 if x < 5 else 180))
        if not edge and (x + y) % 2 == 0 and x >= 5:
            v = 160
        L.px(x, y, grey(v))
    return L


def moon_dark() -> Layer:
    L = Layer()
    disc = {(x, y) for y in range(0, 19) for x in range(0, 19) if math.hypot(x - 9, y - 9) <= 8.4}
    for (x, y) in disc:
        if (x, y) in MOON_PTS:
            edge = any((x + dx, y + dy) not in MOON_PTS for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            L.px(x, y, LINE if edge else MIDV)
        else:
            rim = any((x + dx, y + dy) not in disc for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if rim and (x + y) % 2 == 0:
                L.px(x, y, LINE)
    return L


def moon_dotted() -> Layer:
    L = Layer()
    for y in range(0, 19):
        for x in range(0, 19):
            d = math.hypot(x - 9, y - 9)
            if 7.4 <= d <= 8.4 and (x + y) % 3 == 0:
                L.px(x, y, MUTED, .8)
    return L


def halo() -> Layer:
    """A round soft light mask centred on (0, 0), radius 11: the glow behind a chip, a pip or a spark."""
    L = Layer()
    for y in range(-12, 13):
        for x in range(-12, 13):
            d = math.hypot(x, y)
            a = 0.0 if d > 11 else (0.5 if d < 5 else (0.3 if d < 7.5 else (0.16 if d < 9.5 else 0.07)))
            if a and not (d >= 5 and (x + y) % 2 and d > 9.5):
                L.px(x, y, "#ffffff", a)
    return L


def moon_glow() -> Layer:
    L = Layer()
    for y in range(-4, 23):
        for x in range(-4, 23):
            if (x, y) in MOON_PTS:
                continue
            d = min(math.hypot(x - px, y - py) for (px, py) in MOON_PTS if abs(px - x) < 5 and abs(py - y) < 5) \
                if any(abs(px - x) < 5 and abs(py - y) < 5 for (px, py) in MOON_PTS) else 9
            a = 0.5 if d < 1.5 else (0.28 if d < 2.5 else (0.12 if d < 3.5 else 0))
            if a:
                L.px(x, y, "#ffffff", a)
    return L


# ---------------------------------------------------------------------------------------------------------------------
# Claw gashes: the three files share one 16 x 32 sprite px box; the art sits at the same place in each
# ---------------------------------------------------------------------------------------------------------------------
SL_BOX = (16, 32)
SL_OX, SL_OY = 3, 4


def slash_pts():
    """The gash: tapered, leaning (top right to bottom left); (x, y) with the box origin."""
    cells: dict[tuple[int, int], float] = {}
    for y in range(0, 24):
        t = y / 23.0
        cx = 8.2 - 6.4 * t
        hw = 0.5 + 1.45 * math.sin(math.pi * min(max(t * 1.05, 0), 1))
        for x in range(0, 12):
            d = abs(x - cx)
            if d <= hw:
                cells[(x + SL_OX, y + SL_OY)] = d / max(hw, .01)
    return cells


SLASH = slash_pts()


def slash_dark() -> Layer:
    L = Layer()
    for (x, y), e in SLASH.items():
        L.px(x, y, LINE if e > .55 else MIDV)
    return L


def slash_lit() -> Layer:
    L = Layer()
    for (x, y), e in SLASH.items():
        if e > .7:
            c = "#ff7a2e"
        elif e > .35:
            c = AMBER
        else:
            c = "#fff4d6"
        L.px(x, y, c)
    return L


def slash_flare() -> Layer:
    L = Layer()
    pts = set(SLASH)
    for (x, y) in pts:
        L.px(x, y, "#ffffff", .9)
    for (x, y) in pts:
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                k = (x + dx, y + dy)
                if k in pts:
                    continue
                d = max(abs(dx), abs(dy))
                a = {1: .5, 2: .26, 3: .1}.get(d, 0)
                if a and (k not in L.p or L.p[k][3] < a):
                    L.p[k] = (255, 255, 255, a)
    return L


# ---------------------------------------------------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------------------------------------------------
def frame_box(w: int, h: int) -> Layer:
    """A bar's frame: a one px violet edge with a dark inside, corners cut."""
    L = Layer()
    for y in range(h):
        for x in range(w):
            if (x in (0, w - 1)) and (y in (0, h - 1)):
                continue
            edge = x in (0, w - 1) or y in (0, h - 1)
            L.px(x, y, LINE if edge else DARKV)
    return L


def fill_art(w: int, h: int, light: str, mid: str, dark: str) -> Layer:
    """A bar fill: a bright top row, a body, scanline stipple, a dark bottom row."""
    L = Layer()
    for y in range(h):
        for x in range(w):
            if y == 0:
                c = light
            elif y == h - 1:
                c = dark
            elif y < h * 0.45:
                c = mix(mid, light, .35)
            else:
                c = mid if (x + y) % 2 == 0 else mix(mid, dark, .3)
            L.px(x, y, c)
    return L


def pip(lit: bool) -> Layer:
    """A Lacerate stack pip: a small pointed drop, 7 x 9."""
    L = Layer()
    rows = [(3, 3), (2, 4), (2, 4), (1, 5), (1, 5), (1, 5), (2, 4), (2, 4), (3, 3)]
    for y, (a, b) in enumerate(rows):
        for x in range(a, b + 1):
            edge = x in (a, b) or y in (0, 8)
            if lit:
                L.px(x, y, grey(255 if (x < 3 and y < 5) else (215 if edge else 235)))
            else:
                L.px(x, y, LINE if edge else MIDV)
    return L


ICON_SRC = {
    "rejuv": ["....XX.....", "...XXXX....", "..XXXXXX...", "..XXXXXX...", ".XXXXXXXX..", ".XXXXXXXX..",
              ".XXXXXXXX..", ".XXXXXXXX..", "..XXXXXX...", "...XXXX....", "..........."],
    "regrow": ["..X.....X..", ".XXX...XXX.", ".XXXX.XXXX.", "..XXXXXXX..", "...XXXXX...", "..XXXXXXX..",
               ".XXXX.XXXX.", ".XXX...XXX.", "..X..X..X..", ".....X.....", ".....X....."],
}


def icon_mask(name: str) -> Layer:
    L = Layer()
    for y, row in enumerate(ICON_SRC[name]):
        for x, ch in enumerate(row):
            if ch == "X":
                L.px(x, y, grey(255 if y < 5 else 215))
    return L


LETTERS = {
    "L": ["X..", "X..", "X..", "X..", "XXX"],
    "B": ["XX.", "X.X", "XX.", "X.X", "XX."],
    "M": ["X.X", "XXX", "XXX", "X.X", "X.X"],
}


def letter(ch: str) -> Layer:
    L = Layer()
    for y, row in enumerate(LETTERS[ch]):
        for x, c in enumerate(row):
            if c == "X":
                L.px(x, y, grey(255))
    return L


# ---------------------------------------------------------------------------------------------------------------------
# Chips (16 x 16): a dark one in the atlas, the lit one in its own file (a vertical StatusBar fills it from the bottom)
# ---------------------------------------------------------------------------------------------------------------------
def chip_sp(lit: bool) -> Layer:
    """Shifting Power: a ring arrow (the shift) with a spark in the middle."""
    L = Layer()
    ring, arrow, core = (CYAN, "#b8f6ff", "#ffffff") if lit else (LINE, MIDV, MIDV)
    for y in range(16):
        for x in range(16):
            d = math.hypot(x - 7.5, y - 7.5)
            ang = math.degrees(math.atan2(y - 7.5, x - 7.5)) % 360
            if 4.6 <= d <= 7.2 and not (300 <= ang <= 345):
                L.px(x, y, ring if d < 6.3 else (arrow if lit else DARKV))
    for x, y in ((12, 1), (13, 2), (14, 3), (13, 3), (12, 3), (13, 4), (14, 4), (12, 2)):
        L.px(x, y, arrow)
    for x, y in ((7, 5), (8, 5), (6, 6), (7, 6), (8, 6), (9, 6), (7, 7), (8, 7), (6, 8), (7, 8), (8, 8), (9, 8), (7, 9), (8, 9),
                 (7, 10), (8, 10)):
        L.px(x, y, core)
    return L


def chip_pb(lit: bool) -> Layer:
    """Primal Bite: a pair of fangs under a jaw line."""
    L = Layer()
    jaw, fang, edge = (AMBER, "#fff4d6", WARM) if lit else (LINE, MIDV, DARKV)
    for x in range(1, 15):
        L.px(x, 3, jaw)
        L.px(x, 4, jaw if x % 2 else edge)
    for off in (3, 9):
        for y in range(5, 14):
            w = max(0, 3 - (y - 5) // 3)
            for x in range(off, off + w + 1):
                L.px(x, y, fang if x < off + w else edge)
    return L


def chip_sm(lit: bool) -> Layer:
    """Swiftmend: a flower of four petals round a core."""
    L = Layer()
    petal, core, edge = (PINK, "#fff4d6", "#b3208f") if lit else (LINE, MIDV, DARKV)
    for cx, cy in ((7.5, 3.2), (7.5, 11.8), (3.2, 7.5), (11.8, 7.5)):
        for y in range(16):
            for x in range(16):
                if math.hypot(x - cx, y - cy) <= 3.1:
                    L.px(x, y, petal if math.hypot(x - cx, y - cy) <= 2.2 else edge)
    for y in range(16):
        for x in range(16):
            if math.hypot(x - 7.5, y - 7.5) <= 2.4:
                L.px(x, y, core)
    for x, y in ((7, 14), (8, 14), (7, 15), (8, 15)):
        L.px(x, y, GREEN if lit else LINE)
    return L


def chip_ring() -> Layer:
    L = Layer()
    for y in range(20):
        for x in range(20):
            d = math.hypot(x - 9.5, y - 9.5)
            if d <= 9.6:
                L.px(x, y, LINE if d > 8.4 else DARKV)
    return L


# ---------------------------------------------------------------------------------------------------------------------
# Thorns: the Bramble Wreath (design mockup "Druid Thorns Concepts", 2026-11-17, concept A). A port of the page's drawWreath and
# its helpers (Buf, thorn, leaf, h2, ang, the 3 x 5 label font). Everything is baked in absolute canvas px (origin 0, 0), so the
# module places a piece at (0, 0); the moving pieces (the falling leaf, the sparkle) are baked round their own (0, 0).
#
# What the canvas draws per frame and how the bake splits it:
#   * the glow behind the living arc: per px alpha (1 - (e - 4) / 5) * .32, a white mask cut into TH_WEDGES angular wedges; the
#     module tints it (green, amber in the last minute) and multiplies the breath into the vertex alpha;
#   * the braided vine and its dark outline: TH_WEDGES wedges by each px's own angle, in bark and in dry colours; the module shows
#     a wedge dry when its centre angle is behind the dry line (exact when the time left is a multiple of 600 / TH_WEDGES s);
#   * 20 thorns (live at TH_POPS pop steps, dry, and live with the amber tip of the last minute's blink) and 10 leaves (TH_UNF
#     unfurl steps, wilted, and the last leaf's amber pulse in TH_AMBER steps). The canvas outlines the union of vine, thorns and
#     leaves once; here each piece keeps the outline px that no other piece covers when everything is grown, so a piece drawn
#     later never darkens one drawn before it (the outlines differ from the canvas only while the cast grows the wreath);
#   * a falling leaf in TH_SPIN rotations, the cast sparkle, the 3 x 5 label glyphs (white masks) and the dim amber rings of the
#     after combat reminder. The sap bead, the fireflies and the cast ring are flat px the module places itself (the page's own
#     maths, see GunsightDruid.lua).
# ---------------------------------------------------------------------------------------------------------------------
TH = {"CX": 75, "CY": 36, "R": 22, "A": 2.3, "N": 7, "T": 1.75, "LABEL_Y": 74, "LEN": 600}
TH_WEDGES, TH_POPS, TH_UNF, TH_AMBER, TH_SPIN = 60, 10, 10, 8, 32
TH_W, TH_H = 150, 86
TAU = math.pi * 2
TH_OUT = "#100608"
BARK = {"dk": "#3a1d0e", "md": "#643618", "lt": "#94592a", "hi": "#c48a48"}
DRY = {"dk": "#2a221e", "md": "#463a32", "lt": "#66584a", "hi": "#857664"}
LEAF = {"dk": "#145628", "md": "#2f9a3a", "lt": "#6fd04a", "hi": "#c4f57a"}
WILT = {"dk": "#4a2a10", "md": "#8a5a20", "lt": "#c08a3a", "hi": "#d8a85a"}
TH_TIP, TH_TIPHI, TH_DRYTIP, TH_AMBERD = "#f2e4b4", "#fff8dc", "#a8988a", "#7a4a10"
TH_FONT = {"0": ["XXX", "X.X", "X.X", "X.X", "XXX"], "1": [".X.", "XX.", ".X.", ".X.", "XXX"], "2": ["XXX", "..X", "XXX", "X..", "XXX"],
           "3": ["XXX", "..X", ".XX", "..X", "XXX"], "4": ["X.X", "X.X", "XXX", "..X", "..X"], "5": ["XXX", "X..", "XXX", "..X", "XXX"],
           "6": ["XXX", "X..", "XXX", "X.X", "XXX"], "7": ["XXX", "..X", ".X.", ".X.", ".X."], "8": ["XXX", "X.X", "XXX", "X.X", "XXX"],
           "9": ["XXX", "X.X", "XXX", "..X", "XXX"], "S": [".XX", "X..", ".X.", "..X", "XX."], "M": ["X.X", "XXX", "XXX", "X.X", "X.X"],
           "T": ["XXX", ".X.", ".X.", ".X.", ".X."], "H": ["X.X", "X.X", "XXX", "X.X", "X.X"], "O": ["XXX", "X.X", "X.X", "X.X", "XXX"],
           "R": ["XX.", "X.X", "XX.", "X.X", "X.X"], "N": ["XX.", "X.X", "X.X", "X.X", "X.X"],
           "~": ["...", "...", ".XX", "XX.", "..."]}   # the estimate mark (not on the page: a time from our own cast in combat)
TH_GLYPHS = "0123456789SMTHORN~"


def _i32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _imul(a: int, b: int) -> int:
    return _i32(_i32(a) * _i32(b))


def h2(x, y) -> float:
    """The page's integer hash (Math.imul and the unsigned shifts, bit for bit)."""
    n = _imul(int(x), 374761393) + _imul(int(y), 668265263)          # a plain sum: JS does not wrap it here
    n = _imul(_i32(n) ^ _i32((n & 0xFFFFFFFF) >> 13), 1274126177)
    return ((_i32(n) ^ ((n & 0xFFFFFFFF) >> 16)) & 0xFFFFFFFF) / 4294967295


def ang(x: float, y: float) -> float:
    return math.fmod(math.atan2(x, -y) + TAU, TAU)


def clampf(v, a, b):
    return max(a, min(b, v))


class Buf:
    """The page's Buf: px set in order (a later set wins, the first set keeps its place)."""

    def __init__(self):
        self.m: dict[tuple[int, int], str] = {}

    def set(self, x, y, c):
        x, y = jround(x), jround(y)
        if x < 0 or y < 0 or x >= TH_W or y >= TH_H:
            return
        self.m[(x, y)] = c

    def outline(self) -> set:
        out = set()
        for (x, y) in self.m:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if q not in self.m and 0 <= q[0] < TH_W and 0 <= q[1] < TH_H:
                    out.add(q)
        return out


def th_thorn(b: Buf, x, y, th, L, w, rmp, tip, shade):
    dx, dy = math.sin(th), -math.cos(th)
    nx, ny = -dy, dx
    s = 0.0
    while s <= L:
        k = s / L
        hw, bend = w * (1 - k), k * k * 1.2
        o = -hw
        while o <= hw + .01:
            X, Y = x + dx * s + nx * (o - bend), y + dy * s + ny * (o - bend)
            if k > .62:
                c = TH_TIPHI if k > .88 else tip
            else:
                c = rmp["dk"] if o * shade > 0 else (rmp["hi"] if k > .35 else rmp["lt"])
            b.set(X, Y, c)
            o += .34
        s += .34


def th_leaf(b: Buf, x, y, th, L, w, R):
    dx, dy = math.sin(th), -math.cos(th)
    nx, ny = -dy, dx
    if L <= 0:
        return            # the page's p / L is NaN at L = 0, so its half width is NaN and no px is set
    p = 0.0
    while p <= L:
        hw = w * math.pow(math.sin(math.pi * clampf(p / L, 0, 1)), .8)
        q = -hw
        while q <= hw:
            X, Y = x + dx * p + nx * q, y + dy * p + ny * q
            lit = (nx * q * -.6 + ny * q * -.8) / max(w, 1)
            if abs(q) < .45 and .8 < p < L - 1:
                c = R["dk"]
            else:
                c = R["hi"] if lit > .35 else R["lt"] if lit > -.1 else R["md"]
            b.set(X, Y, c)
            q += .3
        p += .3


def th_vine():
    """{(x, y): (f, ramp key)} of the braided vine (the page's double loop, in its order)."""
    R, A, N, T, cx, cy = TH["R"], TH["A"], TH["N"], TH["T"], TH["CX"], TH["CY"]
    out = {}
    for y in range(-R - 5, R + 6):
        for x in range(-R - 5, R + 6):
            d = math.hypot(x, y)
            if d < R - A - T - 1 or d > R + A + T + 1:
                continue
            a = ang(x, y)
            f = a / TAU
            sw = math.sin(N * a)
            r0, r1 = R + A * sw, R - A * sw
            in0, in1 = abs(d - r0) <= T, abs(d - r1) <= T
            if not in0 and not in1:
                continue
            m = jround(N * a / math.pi)
            front = m % 2
            k = front if (in0 and in1) else (0 if in0 else 1)
            rk = r1 if k else r0
            u = (d - rk) / T
            lit = (x / d * u) * -.6 + (y / d * u) * -.8
            c = "hi" if lit > .42 else "lt" if lit > .02 else "md" if lit > -.5 else "dk"
            other = r0 if k else r1
            if k != front and abs(d - other) <= T + 1.2:
                c = "dk"
            if c == "md" and h2(jround(a * 60), jround(d * 2)) > .8:
                c = "dk"
            if c == "lt" and h2(x * 3, y * 7) > .9:
                c = "hi"
            out[(cx + x, cy + y)] = (f, c)
    return out


def th_thorn_geom(j, pop, rmp, tip):
    R, A, N, T, cx, cy = TH["R"], TH["A"], TH["N"], TH["T"], TH["CX"], TH["CY"]
    a = (j + .35) / 20 * TAU
    sw = abs(math.sin(N * a))
    out = j % 2 == 0
    rr = R + A * sw + T - .4 if out else R - A * sw - T + .4
    L = (4.6 if out else 3.2) * pop
    th = a - .45 if out else a + math.pi + .45
    b = Buf()
    if L >= .6:
        th_thorn(b, cx + math.sin(a) * rr, cy - math.cos(a) * rr, th, L, 1.25, rmp, tip, 1 if out else -1)
    return b


def th_leaf_geom(i, unf, R2):
    R, A, N, cx, cy = TH["R"], TH["A"], TH["N"], TH["CX"], TH["CY"]
    a = (i + .5) / 10 * TAU
    sw = abs(math.sin(N * a))
    rr = R + A * sw + .8
    side = 1 if i % 2 else -1
    b = Buf()
    th_leaf(b, cx + math.sin(a) * rr, cy - math.cos(a) * rr, a + side * 1.05, 6.5 * unf, 2.1 * unf, R2)
    return b


def th_amber_leaf(k: float) -> dict:
    return {"dk": "#6a5010", "md": "#b89a2a", "lt": mix("#e8d060", AMBER, k), "hi": "#fff0a0"}


def th_piece(b: Buf, blocked: set) -> Layer:
    """A piece's px and the outline px that nothing grown covers (outline first, then the colours, as the page draws)."""
    L = Layer()
    for q in b.outline():
        if q not in blocked:
            L.px(q[0], q[1], TH_OUT)
    for (x, y), c in b.m.items():
        L.px(x, y, c)
    return L


def th_sprites() -> list:
    """(name, Layer) of every Thorns piece."""
    R, cx, cy = TH["R"], TH["CX"], TH["CY"]
    out = []
    vine = th_vine()
    vset = set(vine)
    full_thorns = [set(th_thorn_geom(j, 1.0, BARK, TH_TIP).m) for j in range(20)]
    full_leaves = [set(th_leaf_geom(i, 1.0, LEAF).m) for i in range(10)]
    vb = Buf()
    vb.m = {q: BARK[c] for q, (_, c) in vine.items()}
    voutline = vb.outline()
    # the vine wedges: every px (and outline px) by its own angle
    for k in range(TH_WEDGES):
        for key, rmp in (("live", BARK), ("dry", DRY)):
            L = Layer()
            for q in voutline:
                if int(ang(q[0] - cx, q[1] - cy) / TAU * TH_WEDGES) == k:
                    L.px(q[0], q[1], TH_OUT)
            for q, (f, c) in vine.items():
                if int(f * TH_WEDGES) == k:
                    L.px(q[0], q[1], rmp[c])
            out.append((f"th_vine_{k}_{key}", L))
        # the glow behind the living arc (white; the module tints it and multiplies the breath)
        G = Layer()
        for y in range(-R - 9, R + 10):
            for x in range(-R - 9, R + 10):
                d = math.hypot(x, y)
                f = ang(x, y) / TAU
                e = abs(d - R)
                if e < 4 or e > 9 or int(f * TH_WEDGES) != k:
                    continue
                X, Y = cx + x, cy + y
                if (X + Y) & 1 == 0:
                    G.px(X, Y, "#ffffff", (1 - (e - 4) / 5) * .32)
        out.append((f"th_glow_{k}", G))
    # thorns: blocked = the vine, the other grown thorns, the grown leaves
    for j in range(20):
        blocked = vset.union(*(full_thorns[n] for n in range(20) if n != j), *full_leaves)
        for p in range(1, TH_POPS + 1):
            b = th_thorn_geom(j, p / TH_POPS, BARK, TH_TIP)
            if b.m:
                out.append((f"th_thorn_{j}_{p}", th_piece(b, blocked)))
        out.append((f"th_thorn_{j}_dry", th_piece(th_thorn_geom(j, 1.0, DRY, TH_DRYTIP), blocked)))
        out.append((f"th_thorn_{j}_blink", th_piece(th_thorn_geom(j, 1.0, BARK, AMBER), blocked)))
    # leaves
    for i in range(10):
        blocked = vset.union(*full_thorns, *(full_leaves[n] for n in range(10) if n != i))
        for u in range(1, TH_UNF + 1):
            out.append((f"th_leaf_{i}_{u}", th_piece(th_leaf_geom(i, u / TH_UNF, LEAF), blocked)))
        out.append((f"th_leaf_{i}_wilt", th_piece(th_leaf_geom(i, 1.0, WILT), blocked)))
    for s in range(TH_AMBER + 1):
        blocked = vset.union(*full_thorns, *full_leaves[:9])
        out.append((f"th_leaf_9_amber_{s}", th_piece(th_leaf_geom(9, 1.0, th_amber_leaf(s / TH_AMBER)), blocked)))
    # the falling leaf round its own (0, 0), drawn at (40, 40) so no px is clipped, then shifted back
    for s in range(TH_SPIN):
        b = Buf()
        th_leaf(b, 40, 40, s / TH_SPIN * TAU, 6, 2, WILT)
        out.append((f"th_fall_{s}", th_piece(b, set()).shifted(-40, -40)))
    # the cast sparkle: white heart, arms at .7 (the module multiplies its fade), tinted nothing
    S = Layer()
    S.px(0, 0, "#ffffff")
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        S.px(dx, dy, "#c4f57a", .7)
    out.append(("th_sparkle", S))
    # the label glyphs (3 x 5 white masks, top left at 0, 0)
    for ch in TH_GLYPHS:
        L = Layer()
        for j, row in enumerate(TH_FONT[ch]):
            for q in range(3):
                if row[q] == "X":
                    L.px(q, j, "#ffffff")
        out.append((f"th_glyph_{'tilde' if ch == '~' else ch}", L))
    # the after combat reminder: two dim amber dashed rings and ten dots
    Gn = Layer()

    def dashed(r, c, a):
        n = jround(TAU * r)
        for i in range(n):
            if i % 4 == 3:
                continue
            t = i / n * TAU
            Gn.px(jround(cx + math.sin(t) * r), jround(cy - math.cos(t) * r), c, a)
    dashed(R + 2, TH_AMBERD, .8)
    dashed(R - 2, TH_AMBERD, .5)
    for i in range(10):
        t = (i + .5) / 10 * TAU
        Gn.px(jround(cx + math.sin(t) * (R + 5)), jround(cy - math.cos(t) * (R + 5)), AMBER, .35)
    out.append(("th_gone", Gn))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Packing and output
# ---------------------------------------------------------------------------------------------------------------------
class Sprite:
    def __init__(self, name: str, layer: Layer):
        self.name, self.layer = name, layer
        xs = [p[0] for p in layer.p] or [0]
        ys = [p[1] for p in layer.p] or [0]
        self.x0, self.y0 = min(xs), min(ys)
        self.w, self.h = max(xs) - self.x0 + 1, max(ys) - self.y0 + 1
        self.tx = self.ty = 0


def pack(sprites, size) -> bool:
    W, H = size
    x = y = shelf = 0
    for s in sorted(sprites, key=lambda s: (-s.h, -s.w, s.name)):
        w, h = (s.w + 2 * PAD) * SCALE, (s.h + 2 * PAD) * SCALE
        if x + w > W:
            x, y = 0, y + shelf
            shelf = 0
        if y + h > H or w > W:
            return False
        s.tx, s.ty = x + PAD * SCALE, y + PAD * SCALE
        x += w
        shelf = max(shelf, h)
    return True


def rgba_bytes(r, g, b, a) -> bytes:
    return bytes((int(round(b)), int(round(g)), int(round(r)), int(round(a * 255))))


def write_tga_raw(path: str, w: int, h: int, px: bytearray) -> None:
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(px)
    print(f"wrote {path} ({w}x{h}, {os.path.getsize(path)} bytes)")


def raster_atlas(size, sprites) -> bytearray:
    W, H = size
    px = bytearray(W * H * 4)
    for s in sprites:
        for (x, y), (r, g, b, a) in s.layer.p.items():
            bx, by = s.tx + (x - s.x0) * SCALE, s.ty + (y - s.y0) * SCALE
            for dy in range(SCALE):
                o = ((by + dy) * W + bx) * 4
                for dx in range(SCALE):
                    px[o + dx * 4:o + dx * 4 + 4] = rgba_bytes(r, g, b, a)
    return px


def raster_file(size, layer: Layer) -> bytearray:
    """A single file: the layer's (0, 0) is the file's top left; size in texels."""
    W, H = size
    px = bytearray(W * H * 4)
    for (x, y), (r, g, b, a) in layer.p.items():
        if not (0 <= x * SCALE < W and 0 <= y * SCALE < H):
            raise ValueError(f"px ({x}, {y}) is outside the {W}x{H} file")
        for dy in range(SCALE):
            for dx in range(SCALE):
                o = ((y * SCALE + dy) * W + x * SCALE + dx) * 4
                px[o:o + 4] = rgba_bytes(r, g, b, a)
    return px


ATLAS_SIZE = (512, 512)
FILES = {
    "druid_slash_lit": ((32, 64), slash_lit),
    "druid_slash_flare": ((32, 64), slash_flare),
    "druid_energy_fill": ((256, 16), lambda: fill_art(GEOM["FILL_W"], 6, "#fff0b0", AMBER, "#a8641e")),
    "druid_rage_fill": ((256, 32), lambda: fill_art(GEOM["FILL_W"], 10, "#ffd0a0", WARM, "#8a1608")),
    "druid_chip_sp": ((32, 32), lambda: chip_sp(True)),
    "druid_chip_pb": ((32, 32), lambda: chip_pb(True)),
    "druid_chip_sm": ((32, 32), lambda: chip_sm(True)),
}


def atlas_sprites() -> list[Sprite]:
    out: list[Sprite] = []

    def add(name: str, layer: Layer) -> None:
        out.append(Sprite(name, layer))

    for form in FORM_ORDER:
        fn = EYE_FN[form]
        open_l, hot_l = fn(False), fn(True)
        add(f"eye_{form}_open", open_l)
        add(f"eye_{form}_hot", hot_l)
        add(f"eye_{form}_half", eye_half(open_l, form))
        add(f"eye_{form}_shut", eye_closed(open_l, form))
        add(f"eye_{form}_glow", eye_glow(open_l))
        add(f"glyph_{form}", GLYPHS[form]())
    body, buds = ivy()
    add("ivy", body)
    add("ivy_buds", buds)
    add("moon_dark", moon_dark())
    add("moon_lit", moon_lit())
    add("moon_dotted", moon_dotted())
    add("moon_glow", moon_glow())
    add("halo", halo())
    add("slash_dark", slash_dark())
    g = GEOM
    add("track_energy", frame_box(g["BAR_W"], g["BAR_H"]))
    add("track_rage", frame_box(g["BAR_W"], g["RAGE_H"]))
    add("track_lane", frame_box(g["LANE_W"], g["LANE_H"]))
    add("track_drain", frame_box(g["DRAIN_W"], 7))
    add("pip_dark", pip(False))
    add("pip_lit", pip(True))
    add("icon_rejuv", icon_mask("rejuv"))
    add("icon_regrow", icon_mask("regrow"))
    for ch in LETTERS:
        add(f"letter_{ch}", letter(ch))
    add("chip_ring", chip_ring())
    add("chip_sp", chip_sp(False))
    add("chip_pb", chip_pb(False))
    add("chip_sm", chip_sm(False))
    return out


THORNS_SIZE = (512, 512)


def build():
    sprites = atlas_sprites()
    if not pack(sprites, ATLAS_SIZE):
        raise SystemExit("the sprites do not fit the atlas")
    return sprites


def build_thorns():
    sprites = [Sprite(name, layer) for name, layer in th_sprites() if layer.p]
    if not pack(sprites, THORNS_SIZE):
        raise SystemExit("the Thorns sprites do not fit their atlas")
    return sprites


def lua_manifest(sprites, thorns) -> str:
    g = GEOM
    keys = list(g)
    lines = [
        "-- Forever STUwave: the Druid Gunsight module's sprite manifest.",
        "-- GENERATED by tools/assets/generate_druid_gunsight.py; do not edit (gunsightdruid-harness.py checks it).",
        "-- sprite = { tx, ty, w, h, ox, oy }: texel rect in the atlas, size in sprite px, and the sprite's origin as an offset",
        "-- from its top left, in sprite px. GEOM is the geometry, in sprite px on the 150 x 86 canvas.",
        "",
        "local _, FS = ...",
        "",
        "FS.DruidArt = {",
        f"    SCALE = {SCALE},",
        f'    ATLAS = {{ file = "druid_gunsight", w = {ATLAS_SIZE[0]}, h = {ATLAS_SIZE[1]} }},',
        "    FILES = { " + ", ".join(f'{n} = {{ w = {FILES[n][0][0]}, h = {FILES[n][0][1]} }}' for n in sorted(FILES)) + " },",
        f"    SLASH_BOX = {{ {SL_BOX[0]}, {SL_BOX[1]} }}, SLASH_ART = {{ {SL_OX}, {SL_OY} }},",
        "    GEOM = {",
    ]
    for k in keys:
        v = g[k]
        if isinstance(v, list):
            lines.append(f"        {k} = {{ " + ", ".join(str(i) for i in v) + " },")
        else:
            lines.append(f"        {k} = {v},")
    lines += ["    },", "    sprites = {"]
    for s in sorted(sprites, key=lambda s: s.name):
        lines.append(f'        ["{s.name}"] = {{ {s.tx}, {s.ty}, {s.w}, {s.h}, {-s.x0}, {-s.y0} }},')
    lines += ["    },",
              "    -- the Thorns Bramble Wreath: its own atlas, the same sprite rows; pieces drawn in canvas px sit at (0, 0)",
              "    THORNS = {",
              f'        ATLAS = {{ file = "druid_thorns", w = {THORNS_SIZE[0]}, h = {THORNS_SIZE[1]} }},',
              "        " + ", ".join(f"{k} = {v}" for k, v in TH.items()) + ",",
              f"        WEDGES = {TH_WEDGES}, POPS = {TH_POPS}, UNF = {TH_UNF}, AMBER = {TH_AMBER}, SPIN = {TH_SPIN},",
              "        sprites = {"]
    for s in sorted(thorns, key=lambda s: s.name):
        lines.append(f'            ["{s.name}"] = {{ {s.tx}, {s.ty}, {s.w}, {s.h}, {-s.x0}, {-s.y0} }},')
    lines += ["        },", "    },", "}", ""]
    return "\n".join(lines)


def verify(sprites) -> None:
    names = {s.name for s in sprites}
    for f in FORM_ORDER:
        for st in ("open", "hot", "half", "shut", "glow"):
            assert f"eye_{f}_{st}" in names
    for n, (size, _) in FILES.items():
        assert size[0] & (size[0] - 1) == 0 and size[1] & (size[1] - 1) == 0, f"{n}: a file texture must be a power of two"
    assert GEOM["FILL_W"] * 4 // 3 == GEOM["FILL_BOX_W"], "the fill box is the fill's width times 4/3 (the module scales the maximum by it)"


def main() -> None:
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "DruidArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "DruidArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    sprites = build()
    verify(sprites)
    thorns = build_thorns()
    write_tga_raw(os.path.join(here, "druid_gunsight.tga"), ATLAS_SIZE[0], ATLAS_SIZE[1], raster_atlas(ATLAS_SIZE, sprites))
    write_tga_raw(os.path.join(here, "druid_thorns.tga"), THORNS_SIZE[0], THORNS_SIZE[1], raster_atlas(THORNS_SIZE, thorns))
    for name, (size, fn) in FILES.items():
        write_tga_raw(os.path.join(here, f"{name}.tga"), size[0], size[1], raster_file(size, fn()))
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(sprites, thorns))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
