#!/usr/bin/env python3
"""Bake the Druid Clearcasting alert: a seer's orb in an antler root cradle with one omen per form (the roaring bear, FREE MAUL;
the roaring lion, FREE SHRED; the waxing moon with a star, FREE SPELL), the CLEARCASTING title and a drain bar.

The source is the design mockup "Druid Clearcasting alert" (2026-11-17), drawn on a 150 x 96 sprite grid with a canvas API (rects,
Bresenham lines, discs, pixel rings, a 5 x 7 bitmap title font, the generated head frames in druid_cc_art/) and a last 1 px
scanline pass. This file is a port of the mockup's drawCC and its helpers, played into DISPLAY LISTS with the same machinery as the
Warrior power-up alerts (generate_warrior_powerups.py: Painter, the cut and dedupe of sprites, the shelf packer, the TGA writer);
read that file's docstring for the method. The module (DruidClearcasting.lua) only replays the lists.

Each form has five SEQUENCES (frame counts at 30 Hz; the first frame of every sequence is a snapshot, the rest are deltas):

    enter   the entrance, 1.6 s: the cradle grows, the orb opens, the omen forms out of the mist, the title condenses, the
            first roar
    held    the idle loop, 6.8 s (two roars 3.4 s apart, the mist, the orbiting leaves, the glints, the title glint)
    amber   the same loop in amber, for the last 3 s of the 15 s window
    cast    the exit when the free spell is spent (0.6 s): the beast bursts out of the glass, the orb shatters, a green ring
    exp     the exit when the window runs out unused (0.7 s): the omen sinks into the mist, everything greys and drops

The drain bar's fill is three 1 texel sprites (FILL_KEYS) that the module stretches to the real remaining time.

RETUNE. The held loop must be seamless, so every periodic term repeats in 6.8 s (the bake checks frame f + loop against frame f);
TUNE below holds each number next to the mockup's:
    * the mist's spiral turned 1.6 rad/s: now 4 pi / 6.8 (1.848, two turns per loop); its cross wave 0.9 rad/s: now 2 pi / 6.8.
    * the orbiting leaves turned 1.4 rad/s: now 5/3 turns per loop (1.540; three leaves 120 degrees apart, so the set repeats);
      the leaves behind the orb and in front of it are one object each, so a leaf that took another's place is the same picture.
    * the title glint swept every 2.4 s: now 6.8 / 3 (2.267). The glass rim glints every 0.9 s: now 6.8 / 8 (0.85), and the
      glint's place hashes the glint's number modulo 8.
    * the eye and star beat (every 2 s): now 6.8 / 3. The breath sin(e * 2.2): now 2 pi / 3.4 (1.848), one breath per roar.
    * the roar every 3.4 s from 1.6 s already divides the loop.
Every periodic term reads the loop's phase time (`p`: the frame number folded into the loop), every one shot term the real
time (`e`), so a loop repeats exactly and not just to rounding.

DEVIATIONS from the canvas. A CSS filter (grayscale(1) brightness(.5) on the beast's head as it greys out) is computed in float
and rounded once. The mist and the dissolve hash use numpy's sin, which can differ from the browser's in the last bit and so flip a
pixel that sits exactly on a tone threshold.

    python3 tools/assets/generate_druid_clearcasting.py   (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                           FS_ART_LUA_OUTPUT the manifest path, FS_DRUID_CC_ART_DIR the art folder)
Needs numpy and Pillow. Deterministic: the same source writes the same bytes.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("FS_ASSETS_DIR") or _HERE)
import generate_warrior_powerups as W  # noqa: E402  (the shared bake machinery)

GW, GH, MX = W.GW, W.GH, W.MX
SPX = 2.5
DT = 30
EPS = W.EPS
AMBER = 3.0
WIN = 15.0
CAST_AT = 4.0
TAU = math.pi * 2
ART_DIR = os.environ.get("FS_DRUID_CC_ART_DIR") or os.path.join(_HERE, "druid_cc_art")
jround, clamp, q4, ease_out, col = W.jround, W.clamp, W.q4, W.ease_out, W.col

K = {"cy": "#22e0ff", "pk": "#ff4dd8", "am": "#ffb648", "ink": "#07030e", "vi": "#a855f7", "wh": "#f3fbff", "gr": "#39ff14",
     "lf": "#7dff5a"}

LOOP_S = 6.8
LOOP_F = 204                     # frames in the held loop
HELD0 = 48                       # the loop starts at 1.6 s (the first roar after the entrance)
TUNE = dict(
    MIST_A=4 * math.pi / LOOP_S,     # mockup 1.6
    MIST_B=2 * math.pi / LOOP_S,     # mockup 0.9
    ORBIT=5 / 3 * TAU / LOOP_S,      # mockup 1.4
    BEAT=LOOP_S / 3,                 # mockup 2
    GLINT=LOOP_S / 8, GLINTS=8,      # mockup 0.9, no modulo
    SWEEP=LOOP_S / 3,                # mockup 2.4
    BREATH=2 * math.pi / 3.4,        # mockup 2.2
)

OX, OY, R = MX, 29, 23           # the orb (LAY: r 23, oy 29 for every form)
WY, LY, DY = 62, 78, 89          # title, label, drain bar rows
ROAR_EVERY, ROAR_LEN = 3.4, 0.62


def jhash(a, b):
    s = math.sin(a * 127.1 + b * 311.7) * 43758.5453
    return s - math.floor(s)


def jmod(a, b):
    """JS %: the sign of the dividend."""
    return math.fmod(a, b)


# ------------------------------------------------------------------------------------------------------------------------
# Head art
# ------------------------------------------------------------------------------------------------------------------------
HEADF = {"bear": ("open", "mid", "k1", "k2", "k3", "rest"), "cat": ("open", "mid", "k1", "k2", "rest")}
HEAD_FILE = {"bear": "bear38", "cat": "lion42"}
EYES = {"bear": ((13, 7), (23, 7)), "cat": ((15, 13), (24, 13))}
_IMG = {}


def head(kind, fr):
    key = (kind, fr)
    if key not in _IMG:
        from PIL import Image
        _IMG[key] = np.asarray(Image.open(os.path.join(ART_DIR, f"{HEAD_FILE[kind]}_{fr}.png")).convert("RGBA")).copy()
    return _IMG[key]


# ------------------------------------------------------------------------------------------------------------------------
# Painter helpers on top of the Warrior Painter
# ------------------------------------------------------------------------------------------------------------------------
def glow(p, a, fn):
    """The mockup's glow(): nothing at a <= 0, else globalAlpha *= a."""
    if a <= 0:
        return
    old = p.alpha
    p.mul(a)
    fn()
    p.alpha = old


def obj(p, key, fn, sig=None, pieces=None):
    if p.begin(key, sig, pieces):
        fn()
    p.end()


def blit(p, rgb, a, dx, dy):
    """Source over of a float straight image (rgb 0..1, alpha 0..1) at an integer offset, under globalAlpha."""
    h, w = a.shape
    x0, y0, x1, y1 = max(dx, 0), max(dy, 0), min(dx + w, GW), min(dy + h, GH)
    if x1 <= x0 or y1 <= y0:
        return
    sa = a[y0 - dy:y1 - dy, x0 - dx:x1 - dx, None] * p.alpha
    src = rgb[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    reg = p.cur[y0:y1, x0:x1]
    reg[..., :3] = src * sa + reg[..., :3] * (1 - sa)
    reg[..., 3:4] = sa + reg[..., 3:4] * (1 - sa)


def rgbf(c):
    r, g, b, _ = col(c)
    return np.array([r, g, b], np.float64) / 255


def disc_mask(size, cx, cy, r):
    m = np.zeros((size, size), bool)
    for dy in range(-r, r + 1):
        w = int(math.floor(math.sqrt(r * r - dy * dy)))
        y = jround(cy) + dy
        if 0 <= y < size:
            m[y, max(0, jround(cx) - w):max(0, jround(cx) + w + 1)] = True
    return m


def ring_px(p, cx, cy, r, c, th):
    """The Druid page's ringPx: the vertical radius is 0.8 of the horizontal one."""
    cc = col(c)
    n = max(24, jround(r * 8))
    seen = set()
    for i in range(n):
        a = i / n * TAU
        x, y = jround(cx + math.cos(a) * r), jround(cy + math.sin(a) * r * 0.8)
        if (x, y) in seen:
            continue
        seen.add((x, y))
        p.rect(x, y, th, th, cc)


# ------------------------------------------------------------------------------------------------------------------------
# Font
# ------------------------------------------------------------------------------------------------------------------------
FONT = {
    "C": ["..XXX", ".X...", "X....", "X....", "X....", ".X...", "..XXX"], "L": ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"], "A": ["..X..", ".X.X.", "X...X", "X...X", "XXXXX", "X...X", "X...X"],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"], "S": ["..XXX", ".X...", "X....", ".XXX.", "....X", "...X.", "XXX.."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."], "I": ["XXX", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"],
    "N": ["X...X", "XX..X", "XX..X", "X.X.X", "X..XX", "X..XX", "X...X"], "G": ["..XXX", ".X...", "X....", "X..XX", "X...X", ".X..X", "..XXX"],
    "F": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."], "M": ["X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."], "H": ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "D": ["XXX..", "X..X.", "X...X", "X...X", "X...X", "X..X.", "XXX.."], "P": ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
}
SC, GAP = 2, 2


def fw(ch):
    return 3 if ch == " " else len(FONT[ch][0])


def layout(txt):
    x, out = 0, []
    for ch in txt:
        out.append((ch, x, fw(ch) * SC))
        x += fw(ch) * SC + GAP
    return out, x - GAP


PAL = {
    "clear": (("#f3fbff", "#7fe8ff", "#2a8ab0"), "#0c2a3a"), "amber": (("#fff0c8", "#ffb648", "#9a5a10"), "#4a3008"),
    "dim": (("#8a7ab8", "#6c5a9a", "#3a2c5c"), "#1a1030"),
}


def letter(p, i, ch, x, y, pal, cell=None):
    rows = FONT[ch]
    cells = []
    for j, r in enumerate(rows):
        for ci in range(len(r)):
            if r[ci] != "X":
                continue
            dx = dy = 0
            c = None
            if cell:
                t = cell(ci, j)
                if t is None:
                    continue
                dx, dy, c = t
            cells.append((x + ci * SC + dx, y + j * SC + dy, j, c))
    sig = ("L", tuple(cells), pal)
    if p.begin(f"L{i}", sig):
        tone, sh = pal
        for cx, cy, _, _ in cells:
            p.P(cx - 1, cy - 1, SC + 2, SC + 2, K["ink"])
            p.P(cx, cy + 1, SC + 2, SC + 2, K["ink"])
        for cx, cy, _, _ in cells:
            p.P(cx + 1, cy + 2, SC, SC, sh)
        for cx, cy, j, c in cells:
            p.P(cx, cy, SC, SC, c or (tone[0] if j < 2 else tone[1] if j < 5 else tone[2]))
            if not c:
                p.P(cx + SC - 1, cy + SC - 1, 1, 1, tone[2])
    p.end()


def word(p, txt, y, fn):
    lay, w = layout(txt)
    x0 = jround(MX - w / 2)
    for i, (ch, lx, lw) in enumerate(lay):
        s = fn(i, ch, x0 + lx, y, lw)
        if s and ch != " ":
            letter(p, i, ch, x0 + lx, s["y"], s["pal"], s.get("cell"))


def tiny_w(txt):
    return sum(4 if ch == " " else len(FONT[ch][0]) + 1 for ch in txt) - 1


def tiny(p, txt, x, y, c, n):
    ox = x
    for k, ch in enumerate(txt):
        if k >= n:
            break
        if ch == " ":
            ox += 4
            continue
        r = FONT[ch]
        for j, row in enumerate(r):
            for i in range(len(row)):
                if row[i] == "X":
                    p.P(ox + i - 1, y + j - 1, 3, 3, K["ink"])
        for j, row in enumerate(r):
            for i in range(len(row)):
                if row[i] == "X":
                    p.P(ox + i, y + j, 1, 1, c)
        ox += len(r[0]) + 1


# ------------------------------------------------------------------------------------------------------------------------
# Drain bar (FILL_KEYS are stretched by the module)
# ------------------------------------------------------------------------------------------------------------------------
BAR_W = 100
FILL_KEYS = W.FILL_KEYS


def drain(p, open_, am, exp):
    ww = jround(BAR_W * open_)
    if ww < 3:
        return
    xx = jround(MX - ww / 2)
    edge = K["am"] if am else K["vi"]
    if p.begin("bar.f", ("bar.f", ww, am)):
        p.P(xx, DY, ww, 5, "#150c26")
        p.P(xx, DY, ww, 1, edge)
        p.P(xx, DY + 4, ww, 1, edge)
        p.P(xx, DY, 1, 5, edge)
        p.P(xx + ww - 1, DY, 1, 5, edge)
    p.end()
    if open_ < 1:
        return
    x0 = jround(MX - BAR_W / 2)
    if not exp:
        hi, body = ("#ffe9a8", K["am"]) if am else ("#b8f6ff", K["cy"])
        for key, y, c in zip(FILL_KEYS, (DY + 1, DY + 2, DY + 3), (hi, body, body)):
            key = key[:-2]
            if p.begin(key, (key, am)):
                p.P(x0 + 1, y, p.fill_w or 1, 1, c)
            p.end()
    if p.begin("bar.mark", ("bar.mark",)):
        p.P(x0 + 1 + jround(AMBER / WIN * (BAR_W - 2)), DY - 1, 1, 7, K["am"])
    p.end()


# ------------------------------------------------------------------------------------------------------------------------
# The orb, the cradle, the leaves
# ------------------------------------------------------------------------------------------------------------------------
def leaf(p, x, y, c, dk):
    x, y = jround(x), jround(y)
    p.P(x - 2, y - 1, 5, 3, K["ink"])
    p.P(x - 1, y - 2, 3, 5, K["ink"])
    p.P(x - 1, y, 3, 1, c)
    p.P(x, y - 1, 1, 3, c)
    p.P(x + 1, y - 1, 1, 1, dk)
    p.P(x - 1, y + 1, 1, 1, dk)
    p.P(x, y, 1, 1, "#e8ffd8")


def root_pts():
    pts = []
    for i in range(15):
        a = (98 + i * 7.4) * math.pi / 180
        r = R + 4 + math.sin(i / 14 * math.pi) * 1.5
        pts.append((math.cos(a) * r, math.sin(a) * r * 0.95))
    return pts


ROOT = root_pts()
TINES = ((4, -8, -4), (8, -9, -1), (12, -7, -7))


def cradle(p, prog, dim, am):
    cy = OY
    wood = "#4a3a5c" if dim else "#7a4a24"
    lite = "#6c5a9a" if dim else "#c08a48"
    bud = "#6c5a9a" if dim else K["am"] if am else K["lf"]
    budd = "#3a2c5c" if dim else "#9a5a10" if am else "#1c7a2a"
    n = jround(prog * 14)
    for sd in (-1, 1):
        P2 = [(OX - sd * x, cy + y) for x, y in ROOT]
        for i in range(n):
            p.line(P2[i][0] - 1, P2[i][1] - 1, P2[i + 1][0] - 1, P2[i + 1][1] - 1, K["ink"], 4)
        for ti, tx, ty in TINES:
            if ti > n:
                continue
            bx, by = P2[ti]
            ex, ey = bx + sd * tx, by + ty
            p.line(bx - 1, by - 1, ex - 1, ey - 1, K["ink"], 3)
            p.line(ex - 1, ey - 1, ex + sd * 3 - 1, ey - 4, K["ink"], 3)
            p.line(ex - 1, ey - 1, ex + sd * 4 - 1, ey + 1, K["ink"], 3)
        for i in range(n):
            p.line(P2[i][0], P2[i][1], P2[i + 1][0], P2[i + 1][1], wood, 2)
            p.line(P2[i][0], P2[i][1], P2[i + 1][0], P2[i + 1][1], lite, 1)
        for ti, tx, ty in TINES:
            if ti > n:
                continue
            bx, by = P2[ti]
            ex, ey = bx + sd * tx, by + ty
            p.line(bx, by, ex, ey, lite, 1)
            p.line(ex, ey, ex + sd * 3, ey - 3, wood, 1)
            p.line(ex, ey, ex + sd * 4, ey + 2, wood, 1)
            p.P(ex + sd * 3, ey - 3, 1, 1, lite)
        leaf(p, P2[14][0] + sd * 2, P2[14][1] - 3, bud, budd)
    if prog > 0:
        p.disc(OX, cy + R + 3, 3, K["ink"])
        p.disc(OX, cy + R + 3, 2, wood)
        p.P(OX - 1, cy + R + 2, 2, 1, lite)


MIST = {"dim": ("#1a1030", "#24183c", "#2e2050", "#3a2c5c"), "amber": ("#1d1033", "#3a2448", "#6a3a30", "#a8662a"),
        "live": ("#1a0c3a", "#3a1f78", "#3a5ab0", "#4ab8e0")}
_MISTC = {k: np.array([rgbf(c) for c in v]) for k, v in MIST.items()}


def orb_mist(p, r, t, mode, cx, cy):
    p.disc(cx, cy, r + 1, K["ink"])
    ys, xs = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float64)
    d = np.hypot(xs, ys)
    a = np.arctan2(ys, xs)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = 17 / r if r else np.inf
        v = (np.sin(a * 2 + d * 0.42 * k - t * TUNE["MIST_A"]) + 0.6 * np.sin(xs * 0.5 * k - ys * 0.3 * k + t * TUNE["MIST_B"])
             - (d / r if r else d / 0.0) * 0.9)
    ti = np.where(v > 0.75, 3, np.where(v > 0.05, 2, np.where(v > -0.7, 1, 0)))
    inside = d <= r + 0.4
    blit(p, _MISTC[mode][ti], inside.astype(np.float64), jround(cx) - r, jround(cy) - r)


def orb_glass(p, r, mode, cx, cy):
    rim = "#6c5a9a" if mode == "dim" else K["am"] if mode == "amber" else K["cy"]
    back = "#3a2c5c" if mode == "dim" else "#9a5a10" if mode == "amber" else "#2a8ab0"
    for i in range(r * 8):
        a = i / (r * 8) * TAU
        p.P(cx + jround(math.cos(a) * r), cy + jround(math.sin(a) * r), 1, 1, rim if 3.4 < a < 5.6 else back)
    if r >= 8 and mode != "dim":
        n = jround(r / 2)
        for i in range(n):
            a = (200 + i * 72 / n) * math.pi / 180
            p.P(cx + jround(math.cos(a) * (r - 3)), cy + jround(math.sin(a) * (r - 3)), 1, 1, K["wh"])
        p.P(cx - jround(r * 0.7) + 2, cy - jround(r * 0.62) + 2, 2, 2, K["wh"])
        p.P(cx + r - 5, cy + r - 6, 1, 1, "#b8f6ff")


def head_pose(kind, e, ph, out, ot):
    roar = -1.0
    if out == "cast":
        roar = ot
    elif not out:
        if 0.5 <= e < 0.5 + ROAR_LEN:
            roar = e - 0.5
        elif e > 1.6:
            c = jmod(ph - 1.6, ROAR_EVERY)
            if c < ROAR_LEN:
                roar = c
    lunge = 0
    if roar >= 0 and out != "exp":
        fr = "mid" if roar < 0.06 else "open" if (roar < ROAR_LEN - 0.08 or out == "cast") else "mid"
        lunge = 1 if roar < 0.06 else 2 if roar < 0.2 else 1 if roar < 0.4 else 0
    elif out == "exp":
        fr = "rest"
    else:
        b = math.sin(ph * TUNE["BREATH"])
        seq = ("k1", "k2", "k3", "rest") if kind == "bear" else ("k1", "k2", "rest", "rest")
        fr = seq[0] if b > 0.75 else seq[1] if b > 0.25 else seq[2] if b > -0.25 else seq[3]
    breath = 0 if roar >= 0 else (0 if math.sin(ph * TUNE["BREATH"]) > 0.2 else 1)
    return fr, lunge, roar, breath


_HMASK = {}


def head_in_orb(p, kind, pose, r, cx, cy, reveal, gray, eye):
    fr, lunge, _, breath = pose
    im = head(kind, fr)
    h, w = im.shape[:2]
    rgb = np.zeros((64, 64, 3))
    a = np.zeros((64, 64))
    hx, hy = 32 - w // 2, 32 - h // 2 + 2 - lunge + breath
    src = im.astype(np.float64)
    srgb = W.css_filter(src[..., :3], ("gray", 0.5) if gray else None) / 255
    rgb[hy:hy + h, hx:hx + w] = srgb
    a[hy:hy + h, hx:hx + w] = src[..., 3] / 255
    if eye:
        ec = rgbf(eye)
        for ex, ey in EYES[kind]:
            rgb[hy + ey, hx + ex:hx + ex + 2] = ec
            a[hy + ey, hx + ex:hx + ex + 2] = 1
    mk = (r, reveal, hy, h)
    m = _HMASK.get(mk)
    if m is None:
        ys, xs = np.mgrid[0:64, 0:64]
        m = np.hypot(xs - 32, ys - 32) <= r - 0.6
        if reveal < 1:
            hs = np.array([[jhash(x, y) for x in range(64)] for y in range(64)]) * 0.75 + (1 - (ys - hy) / h) * 0.25
            m &= ~(hs > reveal)
        _HMASK[mk] = m
    blit(p, rgb, a * m, cx - 32, cy - 32)


def roar_rings(p, age, r, cx, cy, c):
    for k in range(3):
        a = age - k * 0.12
        if a < 0 or a > 0.45:
            continue
        rr = jround(5 + a * 50)
        if rr > r - 2:
            continue

        def ring(rr=rr):
            for i in range(rr * 6):
                an = i / (rr * 6) * TAU
                if math.sin(an) < -0.2:
                    continue
                x, y = jround(cx + math.cos(an) * rr), jround(cy + 8 + math.sin(an) * rr * 0.6)
                if math.hypot(x - cx, y - cy) < r - 1:
                    p.P(x, y, 1, 1, c)
        glow(p, q4(1 - a / 0.45), ring)


def moon_glyph(p, gp, pulse, colr, core, cx, cy):
    if gp <= 0:
        return
    rr = 11
    off = jround(11 - 7 * gp)
    rgb = np.zeros((40, 40, 3))
    a = np.zeros((40, 40))
    for m, c in ((disc_mask(40, 20, 20, rr + 1), K["ink"]), (disc_mask(40, 20, 20, rr), colr), (disc_mask(40, 23, 19, rr - 3), core)):
        rgb[m] = rgbf(c)
        a[m] = 1
    a[disc_mask(40, 20 + off, 16, rr - 1)] = 0
    blit(p, rgb, a, cx - 20 - 3, cy - 20 + 1)
    if gp > 0.6:
        s = 3 if pulse else 2
        sx, sy = cx + 8, cy - 8
        p.P(sx - s - 1, sy - 1, 2 * s + 3, 3, K["ink"])
        p.P(sx - 1, sy - s - 1, 3, 2 * s + 3, K["ink"])
        p.P(sx - s, sy, 2 * s + 1, 1, K["wh"])
        p.P(sx, sy - s, 1, 2 * s + 1, K["wh"])
    if gp > 0.8:
        p.P(cx + 11, cy + 2, 1, 1, "#b8f6ff")
        p.P(cx + 4, cy - 14, 1, 1, "#b8f6ff")


def scaled(p, im, s, dx, dy):
    """drawImage(im, dx, dy, w, h) with smoothing off: nearest neighbour, each destination pixel's centre sampled."""
    h, w = im.shape[:2]
    W2, H2 = jround(w * s), jround(h * s)
    # the source texel under each destination pixel's centre; a centre that lands exactly on a texel edge takes the texel
    # before it (what the browser does: checked against the mockup in headless Chrome)
    xs = np.minimum(np.ceil((np.arange(W2) + 0.5) * w / W2).astype(int) - 1, w - 1)
    ys = np.minimum(np.ceil((np.arange(H2) + 0.5) * h / H2).astype(int) - 1, h - 1)
    big = im[ys][:, xs].astype(np.float64)
    blit(p, big[..., :3] / 255, big[..., 3] / 255, dx, dy)
    return W2, H2


# ------------------------------------------------------------------------------------------------------------------------
# drawCC
# ------------------------------------------------------------------------------------------------------------------------
LABEL = {"bear": "FREE MAUL", "cat": "FREE SHRED", "moon": "FREE SPELL"}
SHAKE_X = (1, -1, 1, 0, -1, 0, 1, 0, 0)
SHAKE_Y = (0, 1, -1, 1, 0, -1, 0, 0, 0)


def draw_cc(p, st, kind):
    e, ph, out, ot, am = st["e"], st["p"], st["out"], st["ot"], st["am"]
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.mul(fade)
    beast = kind != "moon"
    dim = out == "exp" and ot > 0.08
    mode = "dim" if dim else "amber" if am else "live"
    T = ph
    pose = head_pose(kind, e, ph, out, ot) if beast else None
    sx = sy = 0
    if beast and 0 <= pose[2] < 0.3 and out != "cast":
        s = int(math.floor(pose[2] * 30))
        sx, sy = SHAKE_X[s] if s < 9 else 0, SHAKE_Y[s] if s < 9 else 0
    cx, cy = OX + sx, OY + sy
    r = 0 if e < 0.12 else jround(R * 0.35) if e < 0.17 else jround(R * 0.68) if e < 0.22 else R
    orb_a = (1 if ot < 0.1 else 0) if out == "cast" else 1
    lc = "#6c5a9a" if dim else K["am"] if am else K["lf"]
    ld = "#3a2c5c" if dim else "#9a5a10" if am else "#1c7a2a"

    if not out and e < 0.3:
        def spiral():
            pp = clamp(e / 0.28)
            for i in range(8):
                a = i * math.pi / 4 + pp * 3
                rr = (1 - ease_out(pp)) * 58 + R + 3
                leaf(p, OX + math.cos(a) * rr, OY + math.sin(a) * rr * 0.7, lc, ld)
        obj(p, "spiral", spiral)
    orbit = []
    if e >= 0.3 and not (out == "cast" and ot > 0.1):
        for i in range(3):
            a = T * TUNE["ORBIT"] + i * TAU / 3
            orbit.append((OX + math.cos(a) * (R + 11), OY + math.sin(a) * 7 + 2, math.sin(a)))
    back = [(x, y) for x, y, z in orbit if z < 0]
    front = [(x, y) for x, y, z in orbit if z >= 0]

    def leaves(pts):
        def fn():
            for x, y in pts:
                leaf(p, x, y, lc, ld)
        return fn
    if back:
        obj(p, "leaves.b", leaves(back), sig=(tuple((jround(x), jround(y)) for x, y in back), lc))
    prog = 1.0 if out == "cast" else clamp(e / 0.2)
    obj(p, "cradle", lambda: cradle(p, prog, dim, am), sig=(jround(prog * 14), dim, am))
    if not out and 0.17 <= e < 0.27:
        obj(p, "flash", lambda: p.disc(OX, OY, R + 4 + jround((e - 0.17) * 60), "rgba(243,251,255,.55)"))
    beat = 1 if jmod(T, TUNE["BEAT"]) < 0.15 else 0
    if orb_a > 0:
        if not beast:
            if r > 0:
                obj(p, "mist", lambda: orb_mist(p, r, T, mode, cx, cy))
                obj(p, "glass", lambda: orb_glass(p, r, mode, cx, cy), sig=(r, mode, cx, cy))
            gcol = "#6c5a9a" if dim else K["am"] if am else "#cfe8ff"
            gcore = "#3a2c5c" if dim else "#fff0c8" if am else "#f3fbff"
            if r == R:
                gp = clamp((e - 0.25) / 0.18)
                ga = q4(1 - clamp((ot - 0.1) / 0.25)) if out == "exp" else 1
                pulse = 0 if out else beat
                obj(p, "glyph", lambda: glow(p, ga, lambda: moon_glyph(p, gp, pulse, gcol, gcore, cx, cy)),
                    sig=(gp, pulse, gcol, ga, cx, cy))
        else:
            obj(p, "mist", lambda: orb_mist(p, r, T, mode, cx, cy))
            if r == R:
                rev = clamp((e - 0.22) / 0.3)
                if out == "exp":
                    rev = 1 - clamp((ot - 0.05) / 0.4)
                eye = None if dim else K["wh"] if pose[2] >= 0 else K["am"] if am else "#ffd0f4" if beat else None
                obj(p, "head", lambda: head_in_orb(p, kind, pose, r, cx, cy, rev, dim, eye),
                    sig=(pose[0], pose[1], pose[3], r, cx, cy, rev, dim, eye))
                if pose[2] >= 0 and out != "exp":
                    obj(p, "rings", lambda: roar_rings(p, pose[2], r, cx, cy, K["am"] if am else K["cy"]))
            obj(p, "glass", lambda: orb_glass(p, r, mode, cx, cy), sig=(r, mode, cx, cy))
            if r == R and 0 <= pose[2] < 0.08 and out != "cast":
                obj(p, "gflash", lambda: p.disc(cx, cy, r, "rgba(243,251,255,.18)"), sig=(cx, cy))
    if front:
        obj(p, "leaves.f", leaves(front), sig=(tuple((jround(x), jround(y)) for x, y in front), lc))
    if not out and e > 0.5:
        gi = int(math.floor(T / TUNE["GLINT"]))
        ga = jmod(T, TUNE["GLINT"])
        if ga < 0.2:
            a = -0.6 - jhash(gi % TUNE["GLINTS"], 3) * 2.2
            gx, gy = cx + math.cos(a) * R, cy + math.sin(a) * R
            s = 2 if ga < 0.1 else 1

            def glint():
                p.P(gx - s, gy, 2 * s + 1, 1, K["wh"])
                p.P(gx, gy - s, 1, 2 * s + 1, K["wh"])
            obj(p, "glint", glint)
    if out == "cast":
        if ot < 0.08:
            obj(p, "cflash", lambda: p.disc(OX, OY, R + 8, "rgba(243,251,255,.6)"))
        if beast and 0.04 <= ot < 0.42:
            im = head(kind, "open")
            s = (1.25, 1.5, 1.75, 2)[min(3, int(math.floor((ot - 0.04) / 0.05)))]
            w, h = jround(im.shape[1] * s), jround(im.shape[0] * s)
            obj(p, "burst", lambda: glow(p, q4(1 - clamp((ot - 0.16) / 0.26)),
                                         lambda: scaled(p, im, s, jround(OX - w / 2), jround(OY - h / 2 - ot * 16))))
        if ot < 0.3:
            def slash():
                s = 1 + ot * 7
                if not beast:
                    p.disc(OX, OY, jround(R * s * 0.7), "rgba(243,251,255,.35)")
                elif ot >= 0.06:
                    n, sp = (3, 7) if kind == "bear" else (4, 5)
                    for i in range(n):
                        ox = (i - (n - 1) / 2) * sp * s * 0.7
                        p.line(OX + ox + 9 * s - 1, OY - 13 * s - 1, OX + ox - 9 * s - 1, OY + 13 * s - 1, K["ink"], 5 if kind == "bear" else 3)
                        p.line(OX + ox + 9 * s, OY - 13 * s, OX + ox - 9 * s, OY + 13 * s, K["pk"], 3 if kind == "bear" else 1)
            obj(p, "slash", lambda: glow(p, q4(1 - ot / 0.3), slash), pieces=W.PIECES_DISC)

        def cring():
            rr = jround(R + ot * 90)
            ring_px(p, OX, OY, rr, K["gr"], 2)
            ring_px(p, OX, OY, rr - 4, K["lf"], 1)
        obj(p, "cring", lambda: glow(p, q4(1 - ot / 0.45), cring), pieces=W.PIECES_RING)

        def sparks():
            for i in range(16):
                a = i * TAU / 16 + jhash(i, 1) * 0.3
                d = R * 0.7 + ot * (70 + jhash(i, 2) * 60)

                def one(i=i, a=a, d=d):
                    x, y = OX + math.cos(a) * d, OY + math.sin(a) * d * 0.8 + ot * ot * 40
                    p.P(x - 1, y - 1, 4, 4, K["ink"])
                    p.P(x, y, 2, 2, "#7fe8ff" if i % 3 else K["wh"])
                glow(p, q4(1 - ot / 0.5), one)
        obj(p, "sparks", sparks, pieces=W.PIECES_RING)

    base = PAL["dim"] if out == "exp" else PAL["amber"] if am else PAL["clear"]
    sweep = jmod(T - 1, TUNE["SWEEP"]) * 90 - 10

    def fn(i, ch, x, y, lw):
        dl = 0.3 + 0.03 * i
        if not out:
            if e < dl:
                return None
            pp = clamp((e - dl) / 0.25)
            if pp < 1:
                k = (1 - ease_out(pp)) * 14
                return dict(pal=base, y=y, cell=lambda ci, j: (jround((jhash(i * 7 + ci, j) - 0.5) * k * 2), jround((jhash(j, i * 5 + ci) - 0.5) * k), None))

            def cell(ci, j):
                cx2 = x + ci * SC - 6
                return (0, 0, K["wh"]) if (sweep < cx2 < sweep + 6 and e > 1) else (0, 0, None)
            return dict(pal=base, y=y, cell=cell)
        if out == "cast":
            k = max(0, ot - abs(i - 5.5) * 0.012)
            py = jround(y + (-1 if i % 2 else 1) * k * k * 260)
            al = q4(1 - clamp((ot - 0.12) / 0.3))
            if al <= 0:
                return None
            return dict(pal=base, y=py, cell=lambda ci, j: (0, 0, None) if jhash(i * 7 + ci, j) < al else None)
        return dict(pal=base, y=y + int(math.floor(ot / 0.15)))
    word(p, "CLEARCASTING", WY, fn)

    lab = LABEL[kind]
    lx = jround(MX - tiny_w(lab) / 2)
    if e >= 0.65:
        n = 99 if out else int(math.floor((e - 0.65) / 0.035)) + 1
        ly, la = LY, 1.0
        if out == "cast":
            la = q4(1 - ot / 0.25)
        if out == "exp":
            ly += int(math.floor(ot / 0.15))
        c = "#6c5a9a" if dim else K["am"] if am else ("#cfe8ff" if kind == "moon" else K["pk"])
        n = min(n, len(lab))
        obj(p, "label", lambda: glow(p, la, lambda: tiny(p, lab, lx, ly, c, n)), sig=(n, ly, la, c))
    if e >= 0.4:
        open_ = clamp(1 - ot / 0.1) if out == "cast" else clamp((e - 0.4) / 0.15)
        drain(p, open_, am or out == "exp", out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# States and the bake
# ------------------------------------------------------------------------------------------------------------------------
KINDS = {
    "bear": dict(enter=HELD0, held=(HELD0, LOOP_F), amber=(HELD0, LOOP_F)),
    "cat": dict(enter=HELD0, held=(HELD0, LOOP_F), amber=(HELD0, LOOP_F)),
    "moon": dict(enter=HELD0, held=(HELD0, LOOP_F), amber=(HELD0, LOOP_F)),
}
ORDER = ("bear", "cat", "moon")
CAST_FRAMES, EXP_FRAMES = 19, 22
SEQS = W.SEQS


def phase(f):
    """The loop's phase time of frame f: frames past the entrance fold into the held loop."""
    if f >= HELD0:
        f = HELD0 + (f - HELD0) % LOOP_F
    return f / DT + EPS


def live_state(f, am):
    e = f / DT + EPS
    return {"e": e, "p": phase(f), "out": None, "ot": 0.0, "rem": WIN - e, "am": am}


def leave_state(kind, j):
    ot = j / DT + EPS
    at = CAST_AT if kind == "cast" else WIN
    f = jround(at * DT) + j
    return {"e": at + ot, "p": phase(f), "out": kind, "ot": ot, "rem": WIN - CAST_AT if kind == "cast" else 0.0, "am": False}


def states(sp):
    h0, hn = sp["held"]
    a0, an = sp["amber"]
    return {
        "enter": [live_state(f, False) for f in range(sp["enter"])],
        "held": [live_state(f, False) for f in range(h0, h0 + hn)],
        "amber": [live_state(f, True) for f in range(a0, a0 + an)],
        "cast": [leave_state("cast", j) for j in range(CAST_FRAMES)],
        "exp": [leave_state("exp", j) for j in range(EXP_FRAMES)],
    }


def draw_frame(p, kind, st):
    p.reset()
    draw_cc(p, st, kind)
    return list(p.items)


def bake():
    p = W.Painter()
    data = {}
    for kind in ORDER:
        sp = KINDS[kind]
        seqs = states(sp)
        p.memo = {}             # a sig names art within one form only (the label, the head frames); sprites still dedupe by bytes
        built = {s: [draw_frame(p, kind, st) for st in seqs[s]] for s in SEQS}
        # the loop seam: the frame after the loop's last is the loop's first again
        for s in ("held", "amber"):
            start, n = sp[s]
            nxt = draw_frame(p, kind, live_state(start + n, s == "amber"))
            assert nxt == built[s][0], f"{kind} {s} does not loop"
        order = W.slot_order([fr for s in SEQS for fr in built[s]])
        slot = {k: i + 1 for i, k in enumerate(order)}
        fill = [slot.get(k) for k in FILL_KEYS]
        deltas = {}
        for s in SEQS:
            prev, out = {}, []
            for n, fr in enumerate(built[s]):
                cur = {slot[k]: (sid, x, y) for k, sid, x, y in fr}
                flat = []
                if n == 0:
                    for sl in sorted(cur):
                        flat += [sl, *cur[sl]]
                else:
                    for sl in sorted(set(prev) | set(cur)):
                        if prev.get(sl) != cur.get(sl):
                            flat += [sl, *cur.get(sl, (0, 0, 0))]
                out.append(flat)
                prev = cur
            deltas[s] = out
        data[kind] = dict(slots=len(order), fill=fill, seqs=deltas, order=order, built=built)
    return p, data


def lua_manifest(p, atlases, data):
    L = [
        "-- Forever STUwave: the Druid Clearcasting alert's sprite manifest and frame lists.",
        "-- GENERATED by tools/assets/generate_druid_clearcasting.py; do not edit (druidclearcasting-harness.py checks it).",
        "-- ATLAS[n] = { file, w, h }. SPRITE[id] = { atlas, tx, ty, w, h }: a texel rect in its atlas; one texel is one sprite px.",
        "-- KIND.seqs[name][frame] = flat list of { slot, sprite, x, y } (x, y = sprite px on the 150 x 96 canvas; sprite 0 hides",
        "-- the slot). The first frame of each sequence is a snapshot, the rest are deltas against the frame before. Slots are",
        "-- in back to front order. FILL slots are the drain bar's fill: their sprite is one texel and the module stretches it.",
        "",
        "local _, FS = ...",
        "",
        "FS.DruidClearcastingArt = {",
        f"    SPX = {SPX}, GW = {GW}, GH = {GH}, MX = {MX},",
        f"    AMBER = {int(AMBER)}, WIN = {int(WIN)}, BAR_FILL = {BAR_W - 2},",
        "    ATLAS = {",
    ]
    for n, (w, h, _) in enumerate(atlases, 1):
        L.append(f'        {{ file = "druid_clearcasting_{n}", w = {w}, h = {h} }},')
    L += ["    },", "    SPRITE = {"]
    where = {}
    for n, (w, h, placed) in enumerate(atlases, 1):
        for sid, tx, ty in placed:
            where[sid] = (n, tx, ty)
    for sid in range(1, len(p.sprites) + 1):
        n, tx, ty = where[sid]
        sw, sh, _ = p.sprites[sid - 1]
        L.append(f"        {{ {n}, {tx}, {ty}, {sw}, {sh} }},")
    L += ["    },", "    KIND = {"]
    for kind in ORDER:
        d = data[kind]
        sp = KINDS[kind]
        L += [f"        {kind} = {{",
              f"            slots = {d['slots']}, fill = {W.lua_list(d['fill'])},",
              f"            enterFrames = {sp['enter']}, heldStart = {sp['held'][0]}, amberStart = {sp['amber'][0]},",
              "            seqs = {"]
        for s in SEQS:
            L.append(f"                {s} = {{")
            for flat in d["seqs"][s]:
                L.append("                    " + W.lua_list(flat) + ",")
            L.append("                },")
        L += ["            },", "        },"]
    L += ["    },", "}", ""]
    return "\n".join(L)


def verify(p, atlases, data):
    for w, h, _ in p.sprites:
        assert 1 <= w <= GW and 1 <= h <= GH
    for kind in ORDER:
        d = data[kind]
        for s in SEQS:
            for fr in d["built"][s]:
                for key, sid, x, y in fr:
                    w, h, _ = p.sprites[sid - 1]
                    assert 0 <= x and 0 <= y and x + w <= GW and y + h <= GH, (kind, s, key)
        assert all(d["fill"]), f"{kind}: the fill slots must all be used"
        assert d["fill"] == sorted(d["fill"]) and d["fill"][-1] - d["fill"][0] == 2, "fill slots must be adjacent and in order"
    for w, h, _ in atlases:
        assert w <= W.ATLAS_MAX and h <= W.ATLAS_MAX


def main():
    root = os.path.join(_HERE, "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "DruidClearcastingArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "DruidClearcastingArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    p, data = bake()
    atlases = W.pack(p.sprites)
    verify(p, atlases, data)
    total = sum(w * h for w, h, _ in p.sprites)
    print(f"{len(p.sprites)} sprites, {total} px, {len(atlases)} atlas(es): " + ", ".join(f"{w}x{h}" for w, h, _ in atlases))
    for kind in ORDER:
        d = data[kind]
        print(f"  {kind}: {d['slots']} slots, " + ", ".join(f"{s} {len(d['seqs'][s])}f/{sum(len(f) for f in d['seqs'][s]) // 4} deltas" for s in SEQS))
    if "--stats" in sys.argv:
        return
    os.makedirs(here, exist_ok=True)
    for n, atlas in enumerate(atlases, 1):
        W.write_tga(os.path.join(here, f"druid_clearcasting_{n}.tga"), atlas, p.sprites)
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(p, atlases, data))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
