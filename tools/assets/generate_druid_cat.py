#!/usr/bin/env python3
"""Bake the Druid Cat form's art: the stretched hide with its five gash slots, the raked in gashes, the lion paw, the FINISH plaque
and the finisher's effects, from the design mockup "Druid Hide Rake" (mockups/gunsight-druid-combo-hide-2026-11-17.html, 2026-11-17,
the lion paw of mockups/druid-paw-still-2026-11-17.html). The page is the source of truth: every drawing function below is a port of
its canvas code (the same maths, the same hash, the same colours); a sprite is that code run once on a fixed spot.

Every sprite px is baked as SCALE x SCALE texels of one flat colour (the Rogue / Paladin / Hunter pipeline). Files:

    druid_cat_art.tga       1024 x 512  the atlas: the hide (outline, lacing, five healed scars baked in), the lion paw in six looks
                                        (rake and clean, rake and bloody, rake afterimage, finisher and clean, finisher and bloody,
                                        finisher afterimage tinted red) and the white mask of the clean finisher paw (the windup's red
                                        tint is that mask at a low alpha), the red halos of the windup, the white halo of a fresh gash,
                                        four stages of a gash being torn open, the four claw streaks of the swipe and the four glowing
                                        rake scars of the impact. Rects are in the generated manifest.
    druid_cat_gash_1..5.tga 64 x 128    one lit gash each (the cut, its lip, spatter, beads and drips; every px of it is the page's
                                        `gash` and static part of `blood`), the box of a StatusBar from i - 1 to i: the ENGINE lights
                                        it when the combo count reaches that point, so no addon code ever compares the count (a secret
                                        value in combat).
    druid_cat_cool_1..5.tga 64 x 128    one cooled gash each (the page's `gash` at heat 0 with the lip half curled back: a dark cut with a
                                        cream lip), the same boxes as a StatusBar from i - 1 to i; the cooling after a finisher fades a
                                        lit gash into it
    druid_cat_gold.tga      256 x 128   the five gashes burning gold with the same blood on top, the box of one StatusBar from 4 to 5
    druid_cat_finish.tga    128 x 32    the FINISH plaque (a dark backing, the word in gold with a dark outline), a StatusBar from 4 to 5
    DruidCatArt.lua         the manifest FS.DruidCatArt (never hand edit it, regenerate)

The paw, the leather bits, the blood burst, the shockwave and the falling drops are moved by the module with plain maths from the
tables here (the page's hash values, computed once). The moving parts the page draws per frame with sub pixel positions are baked
once at one fractional offset and move by whole sprite px.

    python3 tools/assets/generate_druid_cat.py     (FS_ASSET_OUTPUT_DIR overrides the .tga directory, FS_ART_LUA_OUTPUT the manifest,
                                                    FS_CAT_PREVIEW a directory of one px per sprite px PNGs for the mockup)
"""

from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

SCALE = 2
W, H = 150, 86                         # the module canvas, sprite px
CX, CY = 75, 36
HX, HY = CX, CY + 1                    # the hide's centre
TAU = math.tau
ATLAS_W, ATLAS_H = 1024, 512
LABEL_Y = 74


# ---------------------------------------------------------------------------------------------------------------------------
# JS semantics the page relies on
# ---------------------------------------------------------------------------------------------------------------------------

def i32(v: int) -> int:
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v & 0x80000000 else v


def imul(a: int, b: int) -> int:
    return i32(a * b)


def h2(x, y) -> float:
    """The page's two argument hash (a unit float); `x | 0` truncates toward zero like JS."""
    n = i32(imul(int(x), 374761393) + imul(int(y), 668265263))
    n = imul(n ^ ((n & 0xFFFFFFFF) >> 13), 1274126177)
    return ((n ^ ((n & 0xFFFFFFFF) >> 16)) & 0xFFFFFFFF) / 4294967295


def jsround(v: float) -> int:
    """Math.round: halves go up."""
    return math.floor(v + 0.5)


def clamp(v, a, b):
    return max(a, min(b, v))


def hexc(h: str):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mixc(a, b, k):
    """The page's mix() on hex strings or rgb tuples: each channel rounded the JS way."""
    A = hexc(a) if isinstance(a, str) else a
    B = hexc(b) if isinstance(b, str) else b
    return tuple(jsround(A[i] + (B[i] - A[i]) * k) for i in range(3))


def ramp(d):
    return {k: hexc(v) for k, v in d.items()}


LION = ramp({"dk": "#5a300e", "md": "#a86a22", "lt": "#d89838", "hi": "#ffd48a"})
MANE = ramp({"dk": "#2a1408", "md": "#5a3014", "lt": "#7e4a20", "hi": "#a46830"})
LIT = ramp({"dk": "#5a0a1a", "md": "#a8142e", "lt": "#ff3a4a", "hi": "#ffa070"})
BLOOD = ramp({"dk": "#5a0610", "md": "#a01020", "lt": "#d8202e", "hi": "#ff8a8a"})
GOLD = ramp({"dk": "#8a5a10", "md": "#e0a020", "lt": "#ffd23f", "hi": "#fffbe0"})
WHITE = (255, 255, 255)
PAW_OUT = hexc("#140804")
HIDE_OUT = hexc("#08040c")
LABEL_OUT = hexc("#0a0414")
GOLDG = hexc("#ffd23f")


# ---------------------------------------------------------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------------------------------------------------------

class Layer:
    """Sparse straight alpha pixels; `paint` composites over what is there (a canvas fillRect with a globalAlpha)."""

    def __init__(self, bounds=None):
        self.p: dict[tuple[int, int], tuple[float, float, float, float]] = {}
        self.bounds = bounds

    def paint(self, x: int, y: int, c, a: float = 1.0) -> None:
        if a <= 0:
            return
        if self.bounds and not (0 <= x < self.bounds[0] and 0 <= y < self.bounds[1]):
            return
        r, g, b = c[0], c[1], c[2]
        old = self.p.get((x, y))
        if old is None or a >= 1.0:
            self.p[(x, y)] = (r, g, b, 1.0 if a >= 1.0 else a)
            return
        orr, og, ob, oa = old
        na = a + oa * (1 - a)
        self.p[(x, y)] = ((r * a + orr * oa * (1 - a)) / na, (g * a + og * oa * (1 - a)) / na, (b * a + ob * oa * (1 - a)) / na, na)

    def px(self, x, y, c, a: float = 1.0) -> None:
        """The page's px(): one pixel at the rounded position."""
        self.paint(jsround(x), jsround(y), c, a)

    def rect(self, x, y, w, h, c, a: float = 1.0) -> None:
        x, y = jsround(x), jsround(y)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.paint(xx, yy, c, a)

    def merge(self, other: "Layer") -> None:
        for (x, y), (r, g, b, a) in other.p.items():
            self.paint(x, y, (r, g, b), a)

    def bbox(self):
        if not self.p:
            return None
        xs = [k[0] for k in self.p]
        ys = [k[1] for k in self.p]
        return min(xs), min(ys), max(xs), max(ys)


class Buf:
    """The page's sprite buffer: last write wins, one dark outline px round it (4 neighbours) before it is drawn."""

    def __init__(self, bounds=None):
        self.m: dict[tuple[int, int], tuple] = {}
        self.bounds = bounds

    def set(self, x, y, c) -> None:
        x, y = jsround(x), jsround(y)
        if self.bounds and (x < 0 or y < 0 or x >= self.bounds[0] or y >= self.bounds[1]):
            return
        self.m[(x, y)] = c

    def has(self, x, y) -> bool:
        return (x, y) in self.m

    def draw(self, layer: Layer, out, a: float = 1.0) -> None:
        for (x, y) in self.m:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if (x + dx, y + dy) not in self.m:
                    layer.paint(x + dx, y + dy, out, a)
        for (x, y), c in self.m.items():
            layer.paint(x, y, c, a)


def dither(layer: Layer, x, y, c, a) -> None:
    if (jsround(x) + jsround(y)) & 1 == 0:
        layer.px(x, y, c, a)


def halo(layer: Layer, cx, cy, r0, r1, c, a) -> None:
    for y in range(-r1, r1 + 1):
        for x in range(-r1, r1 + 1):
            d = math.hypot(x, y)
            if d < r0 or d > r1:
                continue
            dither(layer, cx + x, cy + y, c, (1 - (d - r0) / (r1 - r0)) * a)


# ---------------------------------------------------------------------------------------------------------------------------
# The hide
# ---------------------------------------------------------------------------------------------------------------------------

def hide_v(x, y):
    """< 1 inside the pelt; four leg stubs at the corners."""
    v = math.pow(abs(x) / 33, 2.6) + math.pow(abs(y) / 23, 2.6)
    for lx, ly in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        ax, ay = lx * 22, ly * 15
        bx, by = lx * 41, ly * 30 + (2 if ly < 0 else -1)
        dx, dy = bx - ax, by - ay
        t = clamp(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
        d = math.hypot(x - ax - dx * t, y - ay - dy * t)
        r = 6.5 * (1 - t) + 0.8
        v = min(v, d / r)
    return v + (h2(jsround(math.atan2(y, x) * 14), 1) - 0.5) * 0.08


def slot(k):
    """Five gash slots, a little slanted, each inside its own 12 px column."""
    x = HX - 24 + k * 12
    return {"x": x, "x0": x + 3, "y0": HY - 17 + (k % 2), "x1": x - 3, "y1": HY + 17 - ((k + 1) % 2)}


def gash_w(t, k):
    return 2.3 * math.pow(math.sin(math.pi * clamp(t, 0, 1)), 0.7) + (h2(jsround(t * 16), k * 7) - 0.5) * 0.7


def scar(layer: Layer, k, a):
    S = slot(k)
    t = 0.12
    while t <= 0.88:
        layer.px(S["x0"] + (S["x1"] - S["x0"]) * t, S["y0"] + (S["y1"] - S["y0"]) * t, hexc("#6a4024"), a)
        t += 0.02


def hide_layer() -> Layer:
    b = Buf((W, H))
    for y in range(-34, 35):
        for x in range(-46, 47):
            v = hide_v(x, y)
            if v > 1:
                if v < 1.12 and h2(x * 5, y * 3) > 0.45:                                   # the fur fringe
                    b.set(HX + x, HY + y, hexc("#5a3a22") if h2(x, y * 7) > 0.5 else hexc("#7a5230"))
                continue
            lt = (-x / 33 - y / 23) * 0.5
            m = h2(x >> 1, y >> 1) * 0.5 + h2(x, y) * 0.5
            c = hexc("#9a5e34") if lt > 0.25 else hexc("#83502a") if lt > -0.05 else hexc("#6e4222") if lt > -0.35 else hexc("#5a341a")
            if m > 0.82:
                c = mixc(c, "#3a2010", 0.35)
            elif m < 0.12:
                c = mixc(c, "#b8804a", 0.3)
            if v > 0.82:
                c = mixc(c, "#4a2814", (v - 0.82) * 3)                                    # burnished edge
            if h2(x * 13, y * 17) > 0.985:
                c = hexc("#5a361e")                                                        # pores
            b.set(HX + x, HY + y, c)
    # lacing: holes near the edge with a cord running out to a peg
    for i in range(14):
        a = i / 14 * TAU + 0.2
        r = 1.0
        while hide_v(math.cos(a) * r * 33, math.sin(a) * r * 23) < 0.86:
            r += 0.01
        x = HX + math.cos(a) * r * 33
        y = HY + math.sin(a) * r * 23
        b.set(x, y, hexc("#1a0a06"))
        if i % 2:
            continue
        for s in range(1, 4):
            b.set(x + math.cos(a) * s * 1.4, y + math.sin(a) * s * 1.4, hexc("#c8a070") if s % 2 else hexc("#8a6a44"))
        b.set(x + math.cos(a) * 5.6, y + math.sin(a) * 5.6, hexc("#6a6a7a"))
    layer = Layer((W, H))
    b.draw(layer, HIDE_OUT)
    for k in range(5):                                                                     # five old healed scars
        scar(layer, k, 0.7)
    return layer


# ---------------------------------------------------------------------------------------------------------------------------
# Gashes and blood
# ---------------------------------------------------------------------------------------------------------------------------

def gash(layer: Layer, k, p, heat, lip, R) -> None:
    """One gash, torn p of its length open, lit to `heat`, its cut edges curled back by `lip` (the page's gash() with no flicker)."""
    S = slot(k)
    n = math.hypot(S["x1"] - S["x0"], S["y1"] - S["y0"])
    ax, ay = (S["y1"] - S["y0"]) / n, -(S["x1"] - S["x0"]) / n
    i = 0
    while i <= n * 3 * p:
        t = i / (n * 3)
        w = max(0, gash_w(t, k)) * (0.6 if (t > p - 0.08 and p < 1) else 1)
        x = S["x0"] + (S["x1"] - S["x0"]) * t
        y = S["y0"] + (S["y1"] - S["y0"]) * t
        o = -w - 1.4 * lip
        while o <= w + 1.4 * lip:
            X, Y = x + ax * o, y + ay * o
            ao = abs(o)
            if ao > w:
                c = (hexc("#c84a3a") if (heat > 0 and ao < w + 0.7) else hexc("#ecd0a4")) if o < 0 else hexc("#3a1a10")
            else:
                core = ao / max(w, 0.01)
                base = R["hi"] if core < 0.45 else R["lt"] if core < 0.8 else R["md"]
                c = mixc("#2a0c0c", base, heat) if heat > 0 else (hexc("#2a0c0c") if core < 0.6 else hexc("#4a1a10"))
            layer.px(X, Y, c)
            o += 0.34
        i += 1


def drip_len(k, j):
    sz = 1 if j == 0 else 0.6
    return jsround((4 + h2(k, j * 9) * 6) * sz)


def blood_static(layer: Layer, k) -> None:
    """The part of the page's blood() that stands still once a gash has settled (a > 1.2, fade 1): spatter, beads on the lip and the
    two drips at their full length. The drop that lets go of the first drip is the module's."""
    S = slot(k)
    n = math.hypot(S["x1"] - S["x0"], S["y1"] - S["y0"])
    ax, ay = (S["y1"] - S["y0"]) / n, -(S["x1"] - S["x0"]) / n
    for j in range(9):                                                                      # spatter flung as the claw passed
        s, s2 = h2(j * 3, k * 11), h2(j * 7, k * 5)
        t = 0.15 + s * 0.7
        sgn = 1 if j % 3 else -1
        x = S["x0"] + (S["x1"] - S["x0"]) * t + ax * (3 + s2 * 7) * sgn
        y = S["y0"] + (S["y1"] - S["y0"]) * t + ay * (3 + s2 * 7) * sgn - s2 * 2
        layer.px(x, y, BLOOD["md"] if s > 0.5 else BLOOD["dk"], 1)
        if s2 > 0.6:
            layer.px(x + 1, y, BLOOD["dk"], 0.8)
    for j in range(5):                                                                      # beads on the lip
        t = 0.2 + j * 0.15 + h2(j, k) * 0.06
        w = max(0, gash_w(t, k))
        x = S["x0"] + (S["x1"] - S["x0"]) * t - ax * (w + 0.6)
        y = S["y0"] + (S["y1"] - S["y0"]) * t - ay * (w + 0.6)
        layer.px(x, y, BLOOD["lt"], 1)
        layer.px(x, y + 1, BLOOD["md"], 1)
    drips = [(S["x1"] + 0.5, S["y1"] - 1, 1.0),
             (S["x0"] + (S["x1"] - S["x0"]) * 0.55 + ax * 1.8, S["y0"] + (S["y1"] - S["y0"]) * 0.55 + ay * 1.8, 0.6)]
    for j, (x, y, sz) in enumerate(drips):
        L = drip_len(k, j)
        for i in range(L + 1):
            layer.px(x, y + i, BLOOD["md"] if i < L - 1 else BLOOD["lt"], 1)
        layer.rect(x, y + L, 2 if sz > 0.8 else 1, 2, BLOOD["md"], 1)
        layer.px(x, y + L, BLOOD["hi"], 0.9)


def lit_gash_layer(k, R=LIT) -> Layer:
    L = Layer((W, H))
    gash(L, k, 1, 1, 1, R)
    blood_static(L, k)
    return L


COOL_LIP = 0.4                           # the page's cooling draws `gash(k, 1, heat 0, lip = 1 - c)`: heat is gone by c = 0.62


def cool_gash_layer(k) -> Layer:
    L = Layer((W, H))
    gash(L, k, 1, 0, COOL_LIP, LIT)
    return L


def gold_layer() -> Layer:
    L = Layer((W, H))
    for k in range(5):
        gash(L, k, 1, 1, 1, GOLD)
    for k in range(5):
        blood_static(L, k)
    return L


def tear_layer(p) -> Layer:
    L = Layer((W, H))
    gash(L, 0, p, 1, 0, LIT)
    return L


# ---------------------------------------------------------------------------------------------------------------------------
# The lion paw
# ---------------------------------------------------------------------------------------------------------------------------

TOE = [(-9.6, 1.2), (-3.5, -3.6), (3.5, -3.6), (9.6, 1.2)]
CLAW_TIP = (5.2, -6.2)
LEG = [(0.6, 9, 3.5), (1.4, 15, 4.4), (2.4, 21, 5.2), (3.4, 28, 5.9), (4.4, 35, 6.4), (5.4, 43, 6.8), (6.4, 52, 7)]


def field(balls):
    def f(x, y):
        s = 0.0
        for bx, by, r in balls:
            d2 = (x - bx) ** 2 + (y - by) ** 2
            s += r * r / max(d2, 0.01)
        return s
    return f


def soft(b: Buf, balls, R, mask: set) -> None:
    """A soft shape with light from the top left: five tones, a bright rim on the lit edge, a dark core shadow on the far edge."""
    f = field(balls)
    x0 = min(x - r - 1 for x, y, r in balls)
    y0 = min(y - r - 1 for x, y, r in balls)
    x1 = max(x + r + 1 for x, y, r in balls)
    y1 = max(y + r + 1 for x, y, r in balls)
    y = math.floor(y0)
    while y <= y1:
        x = math.floor(x0)
        while x <= x1:
            v = f(x, y)
            if v >= 1:
                gx, gy = f(x + 0.5, y) - f(x - 0.5, y), f(x, y + 0.5) - f(x, y - 0.5)
                gl = math.hypot(gx, gy) or 1
                edge = clamp(1.5 / v, 0, 1)
                l = (-gx / gl * -0.62 + -gy / gl * -0.78) * edge
                c = R["hi"] if l > 0.62 else R["lt"] if l > 0.22 else R["md"] if l > -0.3 else R["dk"]
                b.set(x, y, c)
                mask.add((jsround(y), jsround(x)))
            x += 1
        y += 1


def paw_sprite(x, y, k, bloody, tint=None, ghost=False):
    """The page's paw(), run once with its claw tip at (x, y). Returns (layer with the shadow, the outline and the colours, the set of
    coloured px without the outline)."""
    b = Buf()
    m: set = set()
    shadow = Layer()
    tx, ty = TOE[1][0] + CLAW_TIP[0], TOE[1][1] + CLAW_TIP[1]
    x0, y0 = x - tx * k, y - ty * k

    def P(u, v, r=0):
        return (x0 + u * k, y0 + v * k, r * k)

    def T(Rm):
        return {n: mixc(c, tint[0], tint[1]) for n, c in Rm.items()} if tint else Rm

    Lr, Mr = T(LION), T(MANE)
    if not ghost:                                                                           # the shadow on what is under it
        for v in range(-8, 61):
            for u in range(-14, 17):
                half = 12 if v < 6 else max(5, 4 + v * 0.12)
                cu = u - ((v - 8) * 0.12 if v > 8 else 0) - 1
                if abs(cu) > half or (v < -2 and math.hypot(u, v + 2) > 13):
                    continue
                dither(shadow, x0 + (u + 3) * k, y0 + (v + 3) * k, (0, 0, 0), 0.3)
    soft(b, [P(*q) for q in (LEG[:2] if ghost else LEG)], Lr, m)                           # foreleg: a wrist pinch, then it thickens
    if not ghost:                                                                           # the ragged dark fringe down the back edge
        for i in range(22):
            v = 12 + i * 2.3
            _, ry, _ = P(0, v)
            row = jsround(ry)
            ex = -1e9
            for (my, mx) in m:
                if my == row:
                    ex = max(ex, mx)
            if ex < -1e8:
                continue
            ln = (6 + h2(i, 4) * 6) * k
            lean = 0.7 + h2(i, 8) * 0.5
            s2 = 0.0
            while s2 < ln:
                kk = s2 / ln
                w = (1 - kk) * 1.6 * k
                fx, fy = ex - 1 + s2 * lean, row + s2 * 0.85
                o = 0.0
                while o <= w:
                    b.set(fx, fy - o, Mr["hi"] if kk > 0.7 else Mr["lt"] if kk > 0.35 else Mr["md"])
                    o += 0.5
                s2 += 0.4
    soft(b, [P(-5, 2.4, 5), P(5, 2.4, 5), P(0, 5, 4.8), P(0, 0.6, 5.4)], Lr, m)             # the back of the paw, wider than tall
    soft(b, [P(-9.2, 7.4, 2)], Lr, m)                                                       # dewclaw
    for u, v in TOE:                                                                        # a dark ring under each toe
        cx, cy, r = P(u, v, 4)
        yy = math.floor(cy - r - 2)
        while yy <= cy + r + 2:
            xx = math.floor(cx - r - 2)
            while xx <= cx + r + 2:
                d = math.hypot(xx - cx, yy - cy)
                if d <= r + 0.8 and d > r - 0.1 and yy > cy:
                    b.set(xx, yy, Lr["dk"])
                xx += 1
            yy += 1
    for u, v in TOE:
        soft(b, [P(u, v, 3.95)], Lr, m)
    for i in range(3):                                                                      # deep gaps running back between the toes
        u0, v0 = TOE[i]
        u1, v1 = TOE[i + 1]
        mu, mv = (u0 + u1) / 2, max(v0, v1)
        t = 0.0
        while t <= 3.2:
            gx, gy, _ = P(mu, mv + t)
            b.set(gx, gy, hexc("#2a1406") if t < 2.2 else Lr["dk"])
            t += 0.35
    for i in range(46):                                                                     # fur as strands
        u = -12 + h2(i, 3) * 24
        v = 2 + h2(i, 7) * 52
        sd = h2(i, 11)
        sx, sy, _ = P(u, v)
        if (jsround(sy), jsround(sx)) not in m:
            continue
        lit = u < 1.5 + v * 0.1
        c = (Lr["lt"] if lit else Lr["md"]) if sd > 0.35 else mixc(Lr["md"], Lr["dk"], 0.6)
        for q in range(5):
            fx, fy, _ = P(u + q * 0.22, v + q * 0.95)
            if (jsround(fy), jsround(fx)) in m:
                b.set(fx, fy, c)

    def claw(u, v, sc):
        p0 = (u - 0.6, v - 3.2)
        p1 = (u + 2.6 * sc, v - 14 * sc)
        p2 = (u + CLAW_TIP[0] * sc, v + CLAW_TIP[1] * sc)
        t = 0.0
        while t <= 1:
            cx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            cy = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
            dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
            dl = math.hypot(dx, dy) or 1
            nx, ny = -dy / dl, dx / dl
            hw = 1.45 * sc * math.pow(1 - t, 1.1) + 0.15
            o = -hw
            while o <= hw + 0.01:
                e = o / max(hw, 0.01)
                c = WHITE if t > 0.86 else hexc("#7a6a50") if t < 0.06 else hexc("#fff6e2") if e < -0.35 else hexc("#8a7a60") if e > 0.45 else hexc("#ddcca8")
                if bloody and t > 0.55:
                    c = BLOOD["hi"] if t > 0.88 else BLOOD["lt"] if e < 0 else BLOOD["md"]
                if tint:
                    c = mixc(c, tint[0], tint[1] * 0.6)
                b.set(x0 + (cx + nx * o) * k, y0 + (cy + ny * o) * k, c)
                o += 0.25
            t += 0.02

    for u, v in TOE:
        claw(u, v, 1)
    claw(-9.2, 7.4 + 1.4, 0.45)
    out = Layer()
    out.merge(shadow)
    b.draw(out, PAW_OUT)
    return out, set(b.m.keys())


# ---------------------------------------------------------------------------------------------------------------------------
# The finisher's lines
# ---------------------------------------------------------------------------------------------------------------------------

def line_ends(i):
    return HX + 40 - i * 3, HY - 34 + i * 7, HX - 44 - i * 3, HY + 18 + i * 7


STREAK_TAIL = 0.4545                   # a streak is the last 45 percent behind its head: the page fades it out at 2.2 per unit of length


def streak_layer() -> Layer:
    """The four claw streaks of the swipe as a comet: the page's streak() with its head at the origin of line 0, white with a red px
    beside it, fading to nothing 45 percent of the line behind the head. The module slides it along the swipe (a whole sprite px at a
    time), so it is baked once at one phase."""
    L = Layer()
    x0, y0, x1, y1 = line_ends(0)
    n = math.ceil(math.hypot(x1 - x0, y1 - y0))
    for i in range(4):
        hx, hy = -3 * i, 7 * i
        for s in range(int(n * STREAK_TAIL), -1, -1):                                       # the tail first, the head last
            u = s / n
            a = clamp(1 - u * 2.2, 0, 1)
            X, Y = hx + (x0 - x1) * u, hy + (y0 - y1) * u
            L.px(X, Y, WHITE, a)
            L.px(X + 1, Y, hexc("#ff2040"), a * 0.7)
    return L


def scar_layers():
    """The four rake scars glowing across the hide (inside the pelt only): the white core (tinted red by the module as it cools) and the
    dark red edge beside it, drawn where the core is not."""
    core = Layer((W, H))
    edge = Layer((W, H))
    for i in range(4):
        x0, y0, x1, y1 = line_ends(i)
        n = math.hypot(x1 - x0, y1 - y0)
        t = 0
        while t <= n:
            X, Y = x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n
            t += 1
            if hide_v(X - HX, Y - HY) > 1:
                continue
            core.px(X, Y, WHITE, 1)
            edge.px(X + 1, Y, hexc("#a00a20"), 0.8)
    only = Layer((W, H))
    for pos, v in edge.p.items():
        if pos not in core.p:
            only.p[pos] = v
    return core, only


# ---------------------------------------------------------------------------------------------------------------------------
# The Thorns corner (the design page "Druid Gunsight Module: One Layout Per Form", 2026-11-16: a ring of ten segments, r 8, at 12, 12)
# ---------------------------------------------------------------------------------------------------------------------------

TH_CX, TH_CY, TH_R = 12, 12, 8


def thorns_masks():
    """White masks, one px each: the ring dots and the first thorn px of each of the ten segments, the second thorn px of each, and the
    dashed ring of a Thorns that ran out. A dot written by a later angle wins, like the page's draw order."""
    ring: dict[tuple[int, int], int] = {}
    for a in range(0, 360, 3):
        rad = (a - 90) * math.pi / 180
        ring[(jsround(TH_CX + math.cos(rad) * TH_R), jsround(TH_CY + math.sin(rad) * TH_R))] = a // 36
    segs = [Layer() for _ in range(10)]
    tips = [Layer() for _ in range(10)]
    for (x, y), seg in ring.items():
        segs[seg].paint(x, y, WHITE, 1)
    for i in range(10):
        rad = ((i + 0.5) * 36 - 90) * math.pi / 180
        for k, layer in ((1, segs[i]), (2, tips[i])):
            layer.paint(jsround(TH_CX + math.cos(rad) * (TH_R + k)), jsround(TH_CY + math.sin(rad) * (TH_R + k)), WHITE, 1)
    gone = Layer()
    for a in range(0, 360, 4):
        if (a // 16) % 2:
            continue
        rad = (a - 90) * math.pi / 180
        gone.paint(jsround(TH_CX + math.cos(rad) * TH_R), jsround(TH_CY + math.sin(rad) * TH_R), WHITE, 1)
    return segs, tips, gone


# ---------------------------------------------------------------------------------------------------------------------------
# The FINISH plaque
# ---------------------------------------------------------------------------------------------------------------------------

FONT = {"F": ["XXX", "X..", "XX.", "X..", "X.."], "I": ["XXX", ".X.", ".X.", ".X.", "XXX"], "N": ["XX.", "X.X", "X.X", "X.X", "X.X"],
        "S": [".XX", "X..", ".X.", "..X", "XX."], "H": ["X.X", "X.X", "XXX", "X.X", "X.X"]}
FINISH_SC = 2                          # a glyph px is 2 x 2 sprite px (the page's 3 x 5 type is too small at 1.25 image px per sprite px)
FINISH_W, FINISH_H = 64, 16            # the file's box, sprite px
BADGE_W, BADGE_H = 52, 14
LABEL_CY = 78                          # the digit and the plaque are centred on this row


def finish_layer() -> Layer:
    L = Layer((FINISH_W, FINISH_H))
    bx, by = (FINISH_W - BADGE_W) // 2, 1
    for y in range(BADGE_H):
        for x in range(BADGE_W):
            if (x in (0, BADGE_W - 1)) and (y in (0, BADGE_H - 1)):
                continue                                                                    # one px cut off each corner
            L.paint(bx + x, by + y, hexc("#0a0416"), 0.97)
    word = "FINISH"
    gw = 3 * FINISH_SC
    adv = gw + FINISH_SC
    tw = len(word) * adv - FINISH_SC
    x0 = bx + (BADGE_W - tw) // 2
    y0 = by + (BADGE_H - 5 * FINISH_SC) // 2
    ink = Layer((FINISH_W, FINISH_H))
    for n, ch in enumerate(word):
        for j, row in enumerate(FONT[ch]):
            for q, c in enumerate(row):
                if c == "X":
                    ink.rect(x0 + n * adv + q * FINISH_SC, y0 + j * FINISH_SC, FINISH_SC, FINISH_SC, GOLDG, 1)
    for (x, y) in list(ink.p):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            if (x + dx, y + dy) not in ink.p:
                L.paint(x + dx, y + dy, LABEL_OUT, 1)
    for (x, y), (r, g, b, a) in ink.p.items():
        L.paint(x, y, (r, g, b), 1)
    return L


# ---------------------------------------------------------------------------------------------------------------------------
# Atlas, files, manifest
# ---------------------------------------------------------------------------------------------------------------------------

def write_tga(path: Path, w: int, h: int, px: bytearray) -> None:
    rows = bytearray()
    for i in range(0, len(px), 4):
        r, g, b, a = px[i:i + 4]
        rows += bytes((b, g, r, a))
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    path.write_bytes(header + bytes(rows))
    print(f"wrote {path} ({w}x{h})")


def blit(buf: bytearray, tw: int, th: int, layer: Layer, ox: int, oy: int) -> None:
    """Draw `layer` (sprite px, origin at its own 0,0) into a texel buffer at sprite offset (ox, oy)."""
    for (x, y), (r, g, b, a) in layer.p.items():
        rgba = bytes((int(jsround(r)), int(jsround(g)), int(jsround(b)), int(jsround(a * 255))))
        for dy in range(SCALE):
            for dx in range(SCALE):
                tx, ty = (x + ox) * SCALE + dx, (y + oy) * SCALE + dy
                if not (0 <= tx < tw and 0 <= ty < th):
                    raise ValueError(f"px ({x}, {y}) lands outside the {tw} x {th} texel file")
                i = (ty * tw + tx) * 4
                buf[i:i + 4] = rgba


def png(path: Path, layer: Layer, ox: int, oy: int, w: int, h: int) -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for (x, y), (r, g, b, a) in layer.p.items():
        if 0 <= x + ox < w and 0 <= y + oy < h:
            im.putpixel((x + ox, y + oy), (int(jsround(r)), int(jsround(g)), int(jsround(b)), int(jsround(a * 255))))
    im.save(path)


def normalise(layer: Layer):
    """Shift a layer so its bounding box starts at 0,0. Returns (layer, minx, miny, w, h) with w, h in sprite px."""
    x0, y0, x1, y1 = layer.bbox()
    out = Layer()
    for (x, y), v in layer.p.items():
        out.p[(x - x0, y - y0)] = v
    return out, x0, y0, x1 - x0 + 1, y1 - y0 + 1


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


class Atlas:
    """A shelf packer: sprites in a fixed order, a one sprite px gap, rows left to right."""

    def __init__(self):
        self.items = []

    def add(self, name, layer: Layer, anchor=None):
        """anchor: the canvas point (sprite px) the sprite is placed by (a paw's claw tip); None = the canvas origin."""
        norm, mx, my, w, h = normalise(layer)
        ax, ay = anchor if anchor else (0, 0)
        self.items.append({"name": name, "layer": norm, "w": w, "h": h, "ox": ax - mx, "oy": ay - my})

    def pack(self):
        pad = 1
        x = y = row_h = 0
        aw, ah = ATLAS_W // SCALE, ATLAS_H // SCALE
        for it in self.items:
            if x + it["w"] > aw:
                x, y, row_h = 0, y + row_h + pad, 0
            it["x"], it["y"] = x, y
            x += it["w"] + pad
            row_h = max(row_h, it["h"])
            if y + it["h"] > ah:
                raise ValueError(f"the atlas is full at {it['name']}")


def build():
    atlas = Atlas()
    out = {"files": {}, "layers": {}}

    # the hide: placed by its canvas position, so its anchor is the canvas origin
    hide = hide_layer()
    atlas.add("hide", hide)

    # the paw, in the looks the page draws; every paw is baked with its claw tip at the same spot
    TIP = (60, 80)
    paws = {}
    for name, k, bloody, tint, ghost in (
            ("paw105", 1.05, False, None, False), ("paw105b", 1.05, True, None, False), ("paw105g", 1.05, False, None, True),
            ("paw13", 1.3, False, None, False), ("paw13b", 1.3, True, None, False),
            ("paw13gr", 1.3, True, ("#ff2040", 0.5), True)):
        layer, colours = paw_sprite(TIP[0], TIP[1], k, bloody, tint, ghost)
        paws[name] = (layer, colours)
        atlas.add(name, layer, TIP)
    # the clean finisher paw as a white mask of its coloured px (the windup tints it red by alpha)
    mask = Layer()
    for (x, y) in paws["paw13"][1]:
        mask.paint(x, y, WHITE, 1)
    atlas.add("paw13m", mask, TIP)

    # halos: dithered discs whose alpha falls to the rim (the windup's red light, the white burst on a fresh gash)
    for r in (14, 17, 20):
        L = Layer()
        halo(L, 0, 0, 0, r, WHITE, 1.0)
        atlas.add(f"halo{r}", L, (0, 0))
    L = Layer()
    halo(L, 0, 0, 0, 8, WHITE, 1.0)
    atlas.add("flare", L, (0, 0))

    # a gash being torn open (slot 0's shape, placed by the slot's origin)
    S0 = slot(0)
    origin = (S0["x"], S0["y0"] - 0)
    TEAR = (0.25, 0.5, 0.75, 0.95)
    for n, p in enumerate(TEAR):
        atlas.add(f"tear{n + 1}", tear_layer(p), origin)

    atlas.add("streak", streak_layer(), (0, 0))
    core, edge = scar_layers()
    atlas.add("scarc", core)
    atlas.add("scare", edge)
    segs, tips, gone = thorns_masks()
    for i in range(10):
        atlas.add(f"thr{i}", segs[i])
        atlas.add(f"tht{i}", tips[i])
    atlas.add("thgone", gone)
    atlas.pack()

    buf = bytearray(ATLAS_W * ATLAS_H * 4)
    for it in atlas.items:
        blit(buf, ATLAS_W, ATLAS_H, it["layer"], it["x"], it["y"])
    out["files"]["druid_cat_art"] = (ATLAS_W, ATLAS_H, buf)
    out["atlas"] = atlas

    # one lit gash per slot: the box of a StatusBar from i - 1 to i
    gashes = []
    for k in range(5):
        L = lit_gash_layer(k)
        norm, mx, my, w, h = normalise(L)
        tw, th = next_pow2(w * SCALE), next_pow2(h * SCALE)
        b = bytearray(tw * th * 4)
        blit(b, tw, th, norm, 0, 0)
        name = f"druid_cat_gash_{k + 1}"
        out["files"][name] = (tw, th, b)
        S = slot(k)
        drip = drip_len(k, 0)
        gashes.append({"file": name, "x": mx, "y": my, "w": tw // SCALE, "h": th // SCALE,
                       "drop_x": jsround(S["x1"] + 0.5), "drop_y": jsround(S["y1"] - 1), "drip": drip,
                       "per": 2.2 + h2(k, 0) * 1.5, "ph": k * 0.7})
    out["gashes"] = gashes

    # the cooled gash of each slot (the finisher's cooling fades the lit one into it)
    cools = []
    for k in range(5):
        L = cool_gash_layer(k)
        norm, mx, my, w, h = normalise(L)
        tw, th = next_pow2(w * SCALE), next_pow2(h * SCALE)
        b = bytearray(tw * th * 4)
        blit(b, tw, th, norm, 0, 0)
        name = f"druid_cat_cool_{k + 1}"
        out["files"][name] = (tw, th, b)
        cools.append({"file": name, "x": mx, "y": my, "w": tw // SCALE, "h": th // SCALE})
    out["cools"] = cools

    # the gold gashes, one file for all five
    G = gold_layer()
    norm, mx, my, w, h = normalise(G)
    tw, th = next_pow2(w * SCALE), next_pow2(h * SCALE)
    b = bytearray(tw * th * 4)
    blit(b, tw, th, norm, 0, 0)
    out["files"]["druid_cat_gold"] = (tw, th, b)
    out["gold"] = {"file": "druid_cat_gold", "x": mx, "y": my, "w": tw // SCALE, "h": th // SCALE}

    # the FINISH plaque
    F = finish_layer()
    tw, th = FINISH_W * SCALE, FINISH_H * SCALE
    b = bytearray(tw * th * 4)
    blit(b, tw, th, F, 0, 0)
    out["files"]["druid_cat_finish"] = (tw, th, b)
    out["finish"] = {"file": "druid_cat_finish", "w": FINISH_W, "h": FINISH_H, "x": (W - FINISH_W) // 2, "y": LABEL_CY - FINISH_H // 2 + 1}
    out["layers"] = {"hide": hide, "gold": G, "finish": F}
    return out


def tables():
    """The page's hash values the module needs, computed once (the client has no 32 bit multiply)."""
    burst = []
    for j in range(34):                                                                     # the blood burst's 34 drops
        s1, s2 = h2(j, 91), h2(j, 37)
        a2 = s1 * TAU
        burst.append((round(math.cos(a2), 5), round(math.sin(a2), 5), round(26 + s2 * 50, 4), 1 if j % 3 else 0, 1 if j % 4 == 0 else 0))
    bits = []                                                                               # leather bits torn up by the claw, per slot
    drift = []                                                                              # bits of fur and leather drifting down
    for k in range(5):
        bits.append([round(h2(j, k * 3), 5) for j in range(6)])
        drift.append([round(h2(j * 5, k), 5) for j in range(5)])
    return burst, bits, drift


def lua_manifest(out) -> str:
    atlas = out["atlas"]
    burst, bits, drift = tables()
    L = ["-- Generated by tools/assets/generate_druid_cat.py. Never hand edit; regenerate.", "local _, FS = ...", "FS.DruidCatArt = {"]
    L.append(f"    SCALE = {SCALE}, W = {W}, H = {H}, HX = {HX}, HY = {HY}, ATLAS_W = {ATLAS_W}, ATLAS_H = {ATLAS_H},")
    L.append('    ATLAS = "druid_cat_art",')
    L.append("    -- sprite name = { texel x, texel y, w, h (sprite px), anchor x, anchor y }: the anchor is where the sprite's own point sits")
    L.append("    -- (a paw's claw tip, a slot's origin) measured from the sprite's top left; canvas sprites put the canvas origin there")
    L.append("    SPR = {")
    for it in atlas.items:
        L.append(f"        {it['name']} = {{ {it['x'] * SCALE}, {it['y'] * SCALE}, {it['w']}, {it['h']}, {it['ox']}, {it['oy']} }},")
    L.append("    },")
    L.append("    GASH = {")
    for g in out["gashes"]:
        L.append(f"        {{ file = \"{g['file']}\", x = {g['x']}, y = {g['y']}, w = {g['w']}, h = {g['h']}, dropX = {g['drop_x']}, "
                 f"dropY = {g['drop_y']}, drip = {g['drip']}, per = {g['per']:.6f}, ph = {g['ph']:.1f} }},")
    L.append("    },")
    L.append("    COOL = {")
    for g in out["cools"]:
        L.append(f"        {{ file = \"{g['file']}\", x = {g['x']}, y = {g['y']}, w = {g['w']}, h = {g['h']} }},")
    L.append("    },")
    g = out["gold"]
    L.append(f"    GOLD = {{ file = \"{g['file']}\", x = {g['x']}, y = {g['y']}, w = {g['w']}, h = {g['h']} }},")
    f = out["finish"]
    L.append(f"    FINISH = {{ file = \"{f['file']}\", x = {f['x']}, y = {f['y']}, w = {f['w']}, h = {f['h']} }},")
    L.append(f"    LABEL_CY = {LABEL_CY},")
    L.append("    -- slot k (0 to 4): x = HX - 24 + 12 k, the cut runs from (x + 3, y0) to (x - 3, y0 + 33), y0 = HY - 17 + k % 2")
    L.append(f"    SLOT_X0 = {HX - 24}, SLOT_DX = 12, SLOT_Y0 = {HY - 17}, SLOT_LEN = 33,")
    L.append("    LINES = {")
    for i in range(4):
        x0, y0, x1, y1 = line_ends(i)
        L.append(f"        {{ {x0}, {y0}, {x1}, {y1} }},")
    L.append("    },")
    L.append("    -- the blood burst: cos, sin, distance scale, 1 = mid red 0 = light red, 1 = a dark px beside it")
    L.append("    BURST = {")
    for b in burst:
        L.append(f"        {{ {b[0]}, {b[1]}, {b[2]}, {b[3]}, {b[4]} }},")
    L.append("    },")
    L.append("    -- the leather bits the claw throws up and the bits that drift down, per slot")
    L.append("    BITS = {")
    for row in bits:
        L.append("        { " + ", ".join(str(v) for v in row) + " },")
    L.append("    },")
    L.append("    DRIFT = {")
    for row in drift:
        L.append("        { " + ", ".join(str(v) for v in row) + " },")
    L.append("    },")
    L.append("}")
    return "\n".join(L) + "\n"


def main() -> int:
    here = Path(__file__).resolve().parent.parent.parent
    out_dir = Path(os.environ.get("FS_ASSET_OUTPUT_DIR") or here / "forever-stuwave" / "Media" / "Textures")
    out_dir.mkdir(parents=True, exist_ok=True)
    default_lua = (out_dir / "DruidCatArt.lua") if os.environ.get("FS_ASSET_OUTPUT_DIR") else (here / "forever-stuwave" / "Modules" / "CombatHud" / "DruidCatArt.lua")
    lua = Path(os.environ.get("FS_ART_LUA_OUTPUT") or default_lua)
    result = build()
    for name, (w, h, buf) in result["files"].items():
        write_tga(out_dir / f"{name}.tga", w, h, buf)
    lua.write_text(lua_manifest(result), encoding="utf-8")
    print(f"wrote {lua}")
    preview = os.environ.get("FS_CAT_PREVIEW")
    if preview:
        pdir = Path(preview)
        pdir.mkdir(parents=True, exist_ok=True)
        for it in result["atlas"].items:
            png(pdir / f"{it['name']}.png", it["layer"], 0, 0, it["w"], it["h"])
        png(pdir / "hide_canvas.png", result["layers"]["hide"], 0, 0, W, H)
        png(pdir / "gold_canvas.png", result["layers"]["gold"], 0, 0, W, H)
        png(pdir / "finish.png", result["layers"]["finish"], 0, 0, FINISH_W, FINISH_H)
    return 0


if __name__ == "__main__":
    sys.exit(main())
