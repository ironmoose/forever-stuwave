#!/usr/bin/env python3
"""Bake the Warrior power-up alerts: Overpower (the bearded axe), Revenge (the laughing skull), Victory Rush (the war cry bust).

The source is the design mockup "Warrior power-up alerts" (2026-11-13), drawn on a 150 x 96 sprite grid with a canvas API:
rects, Bresenham lines, scanline polygons, discs, pixel rings, a 5 x 7 bitmap title font and a last 1 px scanline pass. This file is
a line for line port of that drawing code. It plays every frame the alert can show at 30 Hz (the mockup's own clock) into a
DISPLAY LIST: the ordered objects of the frame (each letter, the axe, the crack, a spark, the skull's jaw, ...) as sprites. An
object is cut to its own bounding box, the scanline pass is baked into it for the absolute rows it lands on, and identical
sprites are shared between frames. The module (WarriorPowerUps.lua) only replays the lists: no art is drawn at runtime.

Each spell has five SEQUENCES (frame counts at 30 Hz; the first frame of every sequence is a snapshot, the rest are deltas):

    enter   the entrance, played once from the open of the window
    held    the idle loop while the window is open (Overpower: the whole 3.5 s before the amber part, no loop needed;
            Revenge: its 1.8 s cackle cycle; Victory Rush: a 4 s loop, see RETUNE)
    amber   the same loop in amber, for the last 1.5 s (Overpower: the real last 1.5 s of its 5 s window)
    cast    the exit when the player casts the spell (0.6 s)
    exp     the exit when the window runs out unused (0.7 s)

The drain bar is NOT baked whole: its frame and tick mark are display list objects, but its fill is three 1 texel sprites
(FILL_SLOTS) that the module stretches to the width the real remaining time gives.

RETUNE. Revenge's HA bits were cyan on every third beat; the cackle has four beats, so the cycle only repeated every 5.4 s. They are
cyan on the first beat of each cackle now. Victory Rush's idle animation is built from toggles with periods 0.4, 0.5, 0.667, 1.0, 2.0, 2.2 s and two sines, which only
repeat after 22 s. The loop is 4 s, so the 2.2 s war cry cycle became 2.0 s and the two sines got whole periods (3.14 and 4.71
rad/s for 3 and 5). Everything else is the mockup's number. Overpower is exact.

    python3 tools/assets/generate_warrior_powerups.py     (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                           FS_ART_LUA_OUTPUT the manifest path)
Needs numpy. Deterministic: the same source writes the same bytes.
"""

from __future__ import annotations

import math
import os
import re
import struct
import sys

import numpy as np

GW, GH, MX = 150, 96, 75
SPX = 2.5                    # image px per sprite px (375 x 240 for the 150 x 96 grid)
DT = 30                      # the mockup's clock: whole 1 / 30 s steps
EPS = 1e-9                   # a frame's time sits a hair above its tick so floor() edges land the same way every loop
AMBER = 1.5
PAD = 1
ATLAS_MAX = 2048
INK = (7, 3, 14)

K = {"cy": "#22e0ff", "pk": "#ff2e97", "am": "#ffb648", "rg": "#ff3b5c", "ink": "#07030e", "vi": "#a855f7", "wh": "#f3fbff", "gr": "#46e08a"}


def jround(v):
    """Math.round: halves go up."""
    return int(math.floor(v + 0.5))


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def q4(a):
    return jround(a * 4) / 4


def ease_out(p):
    return 1 - (1 - p) * (1 - p)


def col(c):
    if c[0] == "#":
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 1.0)
    m = re.match(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", c)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4)))


# ------------------------------------------------------------------------------------------------------------------------
# The canvas. One object at a time is painted into a transparent 150 x 96 float buffer (premultiplied), then cut to its box.
# ------------------------------------------------------------------------------------------------------------------------
GAP_MIN, SAVE_MIN, PIECES_MAX = 3, 160, 8


def _tight(mask, x0, y0, x1, y1):
    sub = mask[y0:y1, x0:x1]
    ys = np.where(sub.any(axis=1))[0]
    xs = np.where(sub.any(axis=0))[0]
    return x0 + int(xs[0]), y0 + int(ys[0]), x0 + int(xs[-1]) + 1, y0 + int(ys[-1]) + 1


def _widest_gap(empty):
    """(start, length) of the longest run of True in a 1-D bool array, interior only (the ends are already trimmed)."""
    best, run, start = (0, 0), 0, 0
    for i, v in enumerate(empty):
        if v:
            if run == 0:
                start = i
            run += 1
            if run > best[1]:
                best = (start, run)
        else:
            run = 0
    return best


def split_boxes(mask):
    """Guillotine cuts along the widest empty row or column band while that saves area; tight boxes, in a fixed order."""
    boxes = [_tight(mask, 0, 0, GW, GH)]
    n = 0
    while n < len(boxes) and len(boxes) < PIECES_MAX:
        x0, y0, x1, y1 = boxes[n]
        sub = mask[y0:y1, x0:x1]
        ry, rl = _widest_gap(~sub.any(axis=1))
        cx, cl = _widest_gap(~sub.any(axis=0))
        if max(rl, cl) < GAP_MIN:
            n += 1
            continue
        if rl >= cl:
            parts = [(x0, y0, x1, y0 + ry), (x0, y0 + ry + rl, x1, y1)]
        else:
            parts = [(x0, y0, x0 + cx, y1), (x0 + cx + cl, y0, x1, y1)]
        parts = [_tight(mask, *q) for q in parts]
        saved = (x1 - x0) * (y1 - y0) - sum((q[2] - q[0]) * (q[3] - q[1]) for q in parts)
        if saved < SAVE_MIN:
            n += 1
            continue
        boxes[n:n + 1] = parts
    return boxes


class Painter:
    def __init__(self):
        self.sprites = []            # id - 1 -> (w, h, rgba bytes)
        self.by_bytes = {}
        self.memo = {}
        self.items = []
        self.alpha = 1.0
        self.tx = self.ty = 0
        self.cur = None
        self.key = None
        self.sig = None
        self.hit = None

    def reset(self):
        self.items = []
        self.alpha = 1.0
        self.tx = self.ty = 0

    # --- object framing -----------------------------------------------------------------------------------------------
    def begin(self, key, sig=None):
        """Start an object. Returns False when `sig` was baked before (nothing to paint)."""
        self.key, self.sig = key, sig
        if sig is not None and sig in self.memo:
            self.hit = self.memo[sig]
            self.cur = None
            return False
        self.hit = None
        self.cur = np.zeros((GH, GW, 4), np.float32)
        return True

    def end(self):
        if self.hit is None:
            self.hit = self._cut()
            if self.sig is not None:
                self.memo[self.sig] = self.hit
        for n, (sid, x0, y0) in enumerate(self.hit):
            self.items.append((f"{self.key}~{n}", sid, x0, y0))
        self.cur = self.hit = self.sig = None

    def _sprite(self, rgba):
        h, w = rgba.shape[:2]
        data = rgba.tobytes()
        k = (w, h, data)
        sid = self.by_bytes.get(k)
        if sid is None:
            self.sprites.append(k)
            sid = len(self.sprites)
            self.by_bytes[k] = sid
        return sid

    def _cut(self):
        """The object as 8 bit straight RGBA with the scanline baked in, cut into the boxes that hold its pixels:
        a sparse object (a letter whose halves flew apart, a crack spreading) becomes several small sprites."""
        a8 = np.rint(self.cur[..., 3] * 255).astype(np.int32)
        mask = a8 > 0
        if not mask.any():
            return ()
        a = self.cur[..., 3:4]
        rgb = np.where(a > 1e-9, self.cur[..., :3] / np.maximum(a, 1e-9), 0.0)
        odd = (np.arange(GH) % 2) == 1
        rgb[odd] = rgb[odd] * 0.8 + np.array(INK, np.float32) / 255 * 0.2
        full = np.zeros((GH, GW, 4), np.uint8)
        full[..., :3] = np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8)
        full[..., 3] = np.clip(a8, 0, 255).astype(np.uint8)
        full[~mask] = 0
        out = []
        for x0, y0, x1, y1 in split_boxes(mask):
            out.append((self._sprite(full[y0:y1, x0:x1]), x0, y0))
        return tuple(out)

    # --- primitives (the mockup's names) --------------------------------------------------------------------------------
    def rect(self, x, y, w, h, c):
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        x += self.tx
        y += self.ty
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, GW), min(y + h, GH)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b, ca = c
        a = ca * self.alpha
        if a <= 0:
            return
        reg = self.cur[y0:y1, x0:x1]
        if a >= 1:
            reg[...] = (r / 255, g / 255, b / 255, 1.0)
            return
        reg *= 1 - a
        reg[..., 0] += r / 255 * a
        reg[..., 1] += g / 255 * a
        reg[..., 2] += b / 255 * a
        reg[..., 3] += a

    def P(self, x, y, w, h, c):
        self.rect(jround(x), jround(y), jround(w), jround(h), col(c) if isinstance(c, str) else c)

    def line(self, x0, y0, x1, y1, c, th=1):
        x0, y0, x1, y1 = jround(x0), jround(y0), jround(x1), jround(y1)
        th = th or 1
        cc = col(c)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        for _ in range(400):
            self.rect(x0, y0, th, th, cc)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def poly(self, pts, c):
        cc = col(c)
        ys = [p[1] for p in pts]
        y0, y1, n = int(math.floor(min(ys))), int(math.ceil(max(ys))), len(pts)
        for y in range(y0, y1):
            yy = y + 0.5
            xs = []
            for i in range(n):
                a, b = pts[i], pts[(i + 1) % n]
                if (a[1] <= yy < b[1]) or (b[1] <= yy < a[1]):
                    xs.append(a[0] + (yy - a[1]) / (b[1] - a[1]) * (b[0] - a[0]))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa, xb = jround(xs[k]), jround(xs[k + 1])
                if xb > xa:
                    self.rect(xa, y, xb - xa, 1, cc)

    def disc(self, cx, cy, r, c):
        cc = col(c)
        for dy in range(-r, r + 1):
            w = int(math.floor(math.sqrt(r * r - dy * dy)))
            self.rect(jround(cx) - w, jround(cy) + dy, w * 2 + 1, 1, cc)

    def arc(self, cx, cy, r, c):
        cc = col(c)
        step = max(2, int(math.floor(360 / (r * 3)))) if r else 1e9
        a = -172
        while a <= -8:
            an = a * math.pi / 180
            self.rect(jround(cx + math.cos(an) * r), jround(cy + math.sin(an) * r * 0.9), 2, 2, cc)
            a += step

    def mul(self, a):
        """globalAlpha *= a. A canvas ignores an alpha outside 0..1, so a faded out q4() (negative) leaves the alpha as it was."""
        v = self.alpha * a
        if 0 <= v <= 1:
            self.alpha = v

    def glow(self, a, fn):
        old = self.alpha
        self.mul(a)
        fn()
        self.alpha = old


# ------------------------------------------------------------------------------------------------------------------------
# Title font
# ------------------------------------------------------------------------------------------------------------------------
FONT = {
    "O": ["..X..", ".X.X.", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
    "V": ["X...X", "X...X", "X...X", "X...X", ".X.X.", ".X.X.", "..X.."],
    "E": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "P": ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
    "W": ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
    "N": ["X...X", "XX..X", "XX..X", "X.X.X", "X..XX", "X..XX", "X...X"],
    "G": ["..XXX", ".X...", "X....", "X..XX", "X...X", ".X..X", "..XXX"],
    "I": ["XXX", ".X.", ".X.", ".X.", ".X.", ".X.", "XXX"],
    "C": ["..XXX", ".X...", "X....", "X....", "X....", ".X...", "..XXX"],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "U": ["X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
    "S": ["..XXX", ".X...", "X....", ".XXX.", "....X", "...X.", "XXX.."],
    "H": ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
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
    "rage": (("#fff3e6", "#ff3b5c", "#a3203f"), "#4a0f22"), "rageA": (("#fff0c8", "#ffb648", "#9a5a10"), "#4a3008"),
    "rageAflash": (("#ffffff", "#fff0c8", "#c9a060"), "#4a3008"),
    "vio": (("#f3d0ff", "#c04cff", "#6a2aa0"), "#8a1a5a"), "vioA": (("#fff0c8", "#ffb648", "#9a5a10"), "#4a3008"),
    "hel": (("#d8ffe8", "#46e08a", "#1c7a4a"), "#0c3a24"), "helA": (("#fff0c8", "#ffb648", "#9a5a10"), "#4a3008"),
    "dim": (("#8a7ab8", "#6c5a9a", "#3a2c5c"), "#1a1030"),
}
WY = 62


def letter(p, tag, i, ch, x, y, pal, cols=None, cell=None):
    """The mockup's letter(): `cell(ci, j)` -> None (skip the cell) or (dx, dy, colour-or-None)."""
    if ch == " ":
        return
    rows = FONT[ch]
    cols = cols if cols is not None else list(range(len(rows[0])))
    cells = []
    for j, r in enumerate(rows):
        for ci, sc in enumerate(cols):
            if r[sc] != "X":
                continue
            dx = dy = 0
            c = None
            if cell:
                t = cell(ci, j)
                if t is None:
                    continue
                dx, dy, c = t
            cells.append((x + ci * SC + dx, y + j * SC + dy, j, c))
    sig = ("L", tuple(cells), pal, p.alpha, p.tx, p.ty)
    if p.begin(f"{tag}.L{i}", sig):
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


def word(p, tag, txt, y, fn):
    lay, w = layout(txt)
    x0 = jround(MX - w / 2)
    for i, (ch, lx, lw) in enumerate(lay):
        s = fn(i, ch, x0 + lx, y, lw)
        if s:
            letter(p, tag, i, ch, s["x"], s["y"], s["pal"], s.get("cols"), s.get("cell"))
    return x0, w


RUNE_T = ["..X..", ".XXX.", "X.X.X", "..X..", "..X..", "..X..", "..X.."]
RUNE_A = ["X.X.X", ".XXX.", "..X..", "..X..", "..X..", "..X..", "..X.."]


def rune(p, key, x, y, rows, c):
    p.begin(key)
    for j, r in enumerate(rows):
        for i in range(5):
            if r[i] == "X":
                p.P(x + i - 1, y + j - 1, 3, 3, K["ink"])
    for j, r in enumerate(rows):
        for i in range(5):
            if r[i] == "X":
                p.P(x + i, y + j, 1, 1, c)
    p.end()


# ------------------------------------------------------------------------------------------------------------------------
# The drain bar: its frame and tick are objects, its fill is three stretched 1 texel slots (FILL_SLOTS).
# ------------------------------------------------------------------------------------------------------------------------
BAR_W, BAR_Y = 100, 85
FILL_KEYS = ("bar.fill1~0", "bar.fill2~0", "bar.fill3~0")


def drain(p, win, open_, am, exp):
    ww = jround(BAR_W * open_)
    if ww < 3:
        return
    xx = jround(MX - ww / 2)
    edge = K["am"] if am else K["vi"]
    if p.begin("bar.f", ("bar.f", ww, am, p.alpha)):
        p.P(xx, BAR_Y, ww, 5, "#150c26")
        p.P(xx, BAR_Y, ww, 1, edge)
        p.P(xx, BAR_Y + 4, ww, 1, edge)
        p.P(xx, BAR_Y, 1, 5, edge)
        p.P(xx + ww - 1, BAR_Y, 1, 5, edge)
    p.end()
    if open_ < 1:
        return
    x0 = jround(MX - BAR_W / 2)
    if not exp:
        hi, body = ("#ffe9a8", K["am"]) if am else ("#b8f6ff", K["cy"])
        for key, y, c in zip(FILL_KEYS, (BAR_Y + 1, BAR_Y + 2, BAR_Y + 3), (hi, body, body)):
            key = key[:-2]
            if p.begin(key, (key, am, p.alpha)):
                p.P(x0 + 1, y, 1, 1, c)
            p.end()
    if p.begin("bar.mark", ("bar.mark", win, p.alpha)):
        p.P(x0 + 1 + jround(AMBER / win * (BAR_W - 2)), BAR_Y - 1, 1, 7, K["am"])
    p.end()


# ------------------------------------------------------------------------------------------------------------------------
# OVERPOWER: bearded axe
# ------------------------------------------------------------------------------------------------------------------------
SWP = {"l": "#f3fbff", "m": "#7fc8e8", "d": "#2a6a8a"}
SWA = {"l": "#fff3d0", "m": "#ffb648", "d": "#8a5410"}
SWD = {"l": "#9d93c4", "m": "#6c5a9a", "d": "#3a2c5c"}
OFF8 = [(-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (-1, 1), (1, -1)]


def axe(p, hx, hy, pal, alpha):
    def T(t, s):
        return [hx - t + s, hy + t + s]

    def M(a):
        return [T(t, s) for t, s in a]

    haft = M([[-3, -2], [-3, 2], [28, 2], [28, -2]])
    head = M([[10, 2], [12, 8], [14, 14], [18, 18], [24, 19], [30, 16], [27, 9], [27, 2]])
    shade = M([[11, 2], [13, 6], [17, 9], [26, 9], [27, 2]])
    edge = M([[12, 8], [14, 14], [18, 18], [24, 19], [30, 16]])
    lite = M([[-3, -0.7], [-3, 0.7], [28, 0.7], [28, -0.7]])
    old = p.alpha
    p.mul(alpha)
    for ox, oy in OFF8:
        p.poly([[x + ox, y + oy] for x, y in haft], K["ink"])
        p.poly([[x + ox, y + oy] for x, y in head], K["ink"])
    p.poly(haft, "#6e1430")
    p.poly(lite, "#a3203f")
    for t in (5, 6, 17, 18):
        p.poly(M([[t, -2], [t, 2], [t + 1, 2], [t + 1, -2]]), "#6c5a9a" if pal["m"] == SWD["m"] else K["am"])
    p.disc(hx + 4, hy - 4, 2, K["ink"])
    p.disc(hx + 4, hy - 4, 1, K["am"])
    p.poly(head, pal["m"])
    p.poly(shade, pal["d"])
    for i in range(len(edge) - 1):
        p.line(edge[i][0], edge[i][1], edge[i + 1][0], edge[i + 1][1], pal["l"], 1)
    for i in range(4):
        p.P(head[4][0] + 2 - i, head[4][1] - 6 + i * 0, 1, 1, pal["l"])
    p.line(edge[1][0] - 6, edge[1][1] - 3, edge[2][0] - 9, edge[2][1] - 2, pal["l"], 1)
    p.alpha = old


def _crack_rays():
    rays = []
    for r in range(9):
        pts = [[0.0, 0.0]]
        a, x, y = r * math.pi * 2 / 9 + 0.3, 0.0, 0.0
        for k in range(5):
            a += (((r * 7 + k * 3) % 5) - 2) * 0.2
            ln = 6 + ((r + k) % 3) * 2.5
            x += math.cos(a) * ln
            y += math.sin(a) * ln * 0.85
            pts.append([x, y])
        rays.append(pts)
    return rays


CRACK = _crack_rays()


def crack(p, cx, cy, prog, spread, c1, c2):
    n = int(math.floor(prog * 5 + 0.001))
    for pts in CRACK:
        for k in range(n):
            a, b = pts[k], pts[k + 1]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            d = math.hypot(mx, my) or 1
            ox, oy = mx / d * spread, my / d * spread
            p.glow(0.5, lambda: p.line(cx + a[0] + ox, cy + a[1] + oy + 1, cx + b[0] + ox, cy + b[1] + oy + 1, c2, 3))
            p.line(cx + a[0] + ox, cy + a[1] + oy, cx + b[0] + ox, cy + b[1] + oy, c1, 1)


def obj(p, key, fn, sig=None):
    """Paint one object with `fn` (the common case: paint, then end)."""
    if p.begin(key, sig):
        fn()
    p.end()


def draw_over(p, st):
    e, out, ot, rem = st["e"], st["out"], st["ot"], st["rem"]
    win = 5
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    if not out and 0.12 <= e < 0.27:
        k = int(math.floor((e - 0.12) / 0.03))
        p.tx = [3, -3, 2, -2, 1, -1][k] if k < 6 else 0
        p.ty = [-2, 2, -1, 1, 0, 0][k] if k < 6 else 0
    CX, CY, HX, HY = MX - 9, 40, MX + 14, 8
    later = None
    hot = K["am"] if am else K["rg"]
    pal = SWD if out == "exp" else SWA if am else SWP
    if not out and e < 0.14:
        pp = clamp(e / 0.12)
        a = 60 * (1 - pp * pp)
        for i in range(5):
            o = (i - 2) * 9
            u = -a

            def streak():
                p.alpha = fade * 0.6
                p.line(CX + o + u + 18, CY + o - u - 18, CX + o + u, CY + o - u, K["cy"] if i % 2 else K["wh"], 1)
                p.alpha = fade
            obj(p, f"op.streak{i}", streak)
        for n, (lag, al) in enumerate([(16, .18), (10, .3), (5, .5)]):
            obj(p, f"op.ghost{n}", lambda lag=lag, al=al: axe(p, HX + a + lag, HY - a - lag, pal, al))
        obj(p, "op.swordIn", lambda: axe(p, HX + a, HY - a, pal, 1))
    else:
        off, al = 0, 1
        if out == "cast":
            off = -jround(ot * ot * 400)
            al = q4(1 - clamp(ot / 0.25))

        def later():
            if al > 0:
                obj(p, "op.sword", lambda: axe(p, HX + off, HY - off, pal, al))
            if not out and e > 0.5:
                k = int(math.floor((e % 1.4) / 0.2))
                if k < 5:
                    T = [[12, 8], [14, 14], [18, 18], [24, 19], [30, 16]][k]
                    x, y = HX - T[0] + T[1], HY + T[0] + T[1]

                    def glint():
                        p.P(x - 2, y, 5, 1, K["wh"])
                        p.P(x, y - 2, 1, 5, K["wh"])
                    obj(p, "op.glint", glint)
    if not out and e >= 0.12:
        k = e - 0.12
        if k < 0.12:
            obj(p, "op.flash", lambda: p.disc(CX, CY, jround(20 * (1 - k / 0.12)), f"rgba(255,240,235,{q4(1 - k / 0.12)})"))
        if k < 0.2:
            def xmark():
                p.glow(q4(1 - k / 0.2), lambda: (p.line(CX - 16, CY - 16, CX + 16, CY + 16, K["wh"], 1),
                                                 p.line(CX + 16, CY - 16, CX - 16, CY + 16, K["cy"], 1)))
            obj(p, "op.xmark", xmark)
        pulse = (0.5 if int(math.floor(e * 3)) % 2 else 1) if e > 0.4 else 1
        obj(p, "op.crack", lambda: p.glow(pulse, lambda: crack(p, CX, CY, clamp(k / 0.18), 0, K["wh"], hot)))
        if k < 0.5:
            for i in range(14):
                a = i * 2.4
                v = 34 + (i * 7) % 26
                x = CX + math.cos(a) * v * k * 2
                y = CY + math.sin(a) * v * k * 2 + 110 * k * k
                c = K["wh"] if i % 3 == 0 else K["am"] if i % 3 == 1 else K["rg"]
                obj(p, f"op.spark{i}", lambda x=x, y=y, c=c: p.glow(q4(1 - k / 0.5), lambda: p.P(x, y, 2, 2, c)))
        if e > 0.5:
            for i in range(7):
                ph = (e * 0.8 + i * 0.14) % 1
                x = CX - 22 + (i * 13) % 44 + jround(math.sin(e * 4 + i) * 2)
                obj(p, f"op.ember{i}", lambda i=i, ph=ph, x=x: p.glow(q4(1 - ph), lambda: p.P(x, CY + 10 - ph * 34, 1 + (i % 2), 1 + (i % 2), K["am"] if i % 2 else hot)))
    if later:
        later()
    if out == "cast":
        if ot < 0.08:
            obj(p, "op.cflash", lambda: p.disc(CX, CY, 34, "rgba(255,46,151,.35)"))
        obj(p, "op.cx", lambda: p.glow(q4(1 - ot / 0.3), lambda: (p.line(CX - 20, CY - 20, CX + 20, CY + 20, K["pk"], 3),
                                                              p.line(CX + 20, CY - 20, CX - 20, CY + 20, K["wh"], 1))))
        obj(p, "op.ccrack", lambda: p.glow(q4(1 - ot / 0.5), lambda: crack(p, CX, CY, 1, jround(ot * 110), K["pk"], K["vi"])))
    if out == "exp":
        obj(p, "op.xcrack", lambda: crack(p, CX, CY, 1, 0, "#8a7ab8", "#4a3e72"))
    base = PAL["dim"] if out == "exp" else (PAL["rageAflash"] if int(math.floor(e * 4)) % 2 else PAL["rageA"]) if am else PAL["rage"]

    def fn(i, ch, x, y, lw):
        d = 0.2 + 0.03 * i
        pr = clamp((e - d) / 0.12)
        if not out and e < d:
            return None
        pp = math.floor(pr * 3) / 3

        def split(ci, j):
            return 0 if (ci * 1.0 + j * 1.2) < 5.4 else 1
        jx = jy = 0
        if not out:
            if pr >= 1 and e - d - 0.12 < 0.18:
                jx = 2 if int(math.floor(e * 40)) % 2 else -2
                jy = int(math.floor(e * 40)) % 3 - 1
            elif e > 0.5 and (e % 1.2) < 0.1:
                jx = 1 if int(math.floor(e * 40)) % 2 else -1
        gp = ((e % 1.8) / 0.6) * 130 - 14

        def cell(ci, j):
            h = split(ci, j)
            dx = dy = 0
            if out == "cast":
                f = math.pow(clamp((ot - i * 0.01) / 0.5), 1.3) * 70
                dx = f if h else -f
                dy = f * 0.5 if h else -f * 0.5
            elif pr < 1:
                dx = (1 - pp) * 16 if h else -(1 - pp) * 16
                dy = (1 - pp) * 8 if h else -(1 - pp) * 8
            gl = (not out) and e > 0.6 and abs((x + ci * 2 + j * 1.5) - gp) < 4
            return (jround(dx), jround(dy), K["wh"] if gl else None)
        return {"x": x + jx, "y": y + jy + (int(math.floor(ot / 0.15)) if out == "exp" else 0), "pal": base, "cell": cell}
    x0, w = word(p, "op", "OVERPOWER", WY, fn)
    if not out:
        lay, lw_ = layout("OVERPOWER")
        for i, (ch, lx, lw) in enumerate(lay):
            d = 0.2 + 0.03 * i
            pr = (e - d) / 0.12
            if 0.55 < pr < 1.1:
                xl = jround(MX - lw_ / 2) + lx
                obj(p, f"op.slash{i}", lambda xl=xl, lw=lw: p.line(xl - 2, WY + 15, xl + lw + 2, WY - 2, K["wh"], 1))
    if e >= 0.4 and (not out or out == "exp"):
        rune(p, "op.runeL", x0 - 11, WY + 4, RUNE_T, K["am"] if am else K["cy"])
        rune(p, "op.runeR", x0 + w + 7, WY + 4, RUNE_T, K["am"] if am else K["cy"])
    if e >= 0.4:
        drain(p, win, clamp(1 - ot / 0.1) if out == "cast" else clamp((e - 0.4) / 0.15), out == "exp" or st["am"], out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# REVENGE: laughing horned skull
# ------------------------------------------------------------------------------------------------------------------------
CRAN = ["....XXXXXXXX....", "..XXXXXXXXXXXX..", ".XXXXXXXXXXXXXX.", ".XXXXXXXXXXXXXX.", "XXXXXXXXXXXXXXXX", "XXKKKKXXXXKKKKXX",
        "XKKEEKKXXKKEEKKX", "XKKEEKKXXKKEEKKX", "XXKKKKXXXXKKKKXX", "XXXXXXKKKKXXXXXX", ".XXXXXXKKXXXXXX.", "..XSXSXSXSXSXS.."]
JAWR = ["..XSXSXSXSXSXS..", "..XXXXXXXXXXXX..", "...XXXXXXXXXX...", "....XXXXXXXX...."]


def bone_part(p, key, rows, x, y, eye, dark, flat_from):
    def at(i, j):
        return rows[j][i] if 0 <= j < len(rows) and 0 <= i < len(rows[j]) else "."

    def paint():
        for j in range(len(rows)):
            for i in range(16):
                if at(i, j) != ".":
                    p.P(x + i * 2 - 1, y + j * 2 - 1, 4, 4, K["ink"])
        for j in range(len(rows)):
            for i in range(16):
                c = at(i, j)
                if c == ".":
                    continue
                if j >= flat_from:
                    cc = "#9b8964" if c == "S" else "#eadfc4"
                elif c == "K":
                    cc = "#12030a"
                elif c == "E":
                    cc = "#12030a" if dark else eye
                else:
                    cc = "#fff6e0" if at(i, j - 1) == "." else "#9b8964" if (at(i + 1, j) == "." or at(i, j + 1) == ".") else "#eadfc4"
                p.P(x + i * 2, y + j * 2, 2, 2, cc)
    obj(p, key, paint, (key, x, y, eye, dark, p.alpha, p.tx, p.ty))


def horn_helm(p, key, x, y, dim):
    def paint():
        cap = [[x - 1, y + 9], [x, y + 2], [x + 7, y - 2], [x + 25, y - 2], [x + 32, y + 2], [x + 33, y + 9]]
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            p.poly([[a + dx, b + dy] for a, b in cap], K["ink"])
        p.poly(cap, "#3a2c5c" if dim else "#6c5a9a")
        p.P(x + 4, y - 1, 22, 1, "#6c5a9a" if dim else "#a898d0")
        p.P(x - 1, y + 6, 34, 3, K["ink"])
        p.P(x, y + 7, 32, 1, "#4a3e72" if dim else "#8a7ab8")
        for rx in (4, 15, 26):
            p.P(x + rx, y + 7, 2, 1, K["am"])
        p.P(x + 15, y + 9, 2, 5, "#4a3e72" if dim else "#8a7ab8")
        for d in (-1, 1):
            bx = x if d < 0 else x + 32
            pts = [[bx, y + 5], [bx + d * 5, y], [bx + d * 7, y - 6], [bx + d * 5, y - 12]]
            for i in range(3):
                p.line(pts[i][0] - 2, pts[i][1] - 2, pts[i + 1][0] - 2, pts[i + 1][1] - 2, K["ink"], 5)
            for i in range(3):
                p.line(pts[i][0] - 1, pts[i][1] - 1, pts[i + 1][0] - 1, pts[i + 1][1] - 1,
                       (("#9b8964" if dim else K["am"]) if i == 2 else "#eadfc4"), 3)
    obj(p, key, paint, (key, x, y, dim, p.alpha, p.tx, p.ty))


def laugh_skull(p, x, sy, eye, d, t, dark, alpha):
    old = p.alpha
    p.mul(alpha)
    cy = sy - t
    jy = cy + 24 + d
    if d > 0:
        def mouth():
            p.P(x + 5, cy + 23, 22, d + 3, "#12030a")
            if d >= 4:
                p.P(x + 11, jy - 2, 10, 2, K["pk"])
        obj(p, "rv.sk.mouth", mouth)

    def fangbg():
        for bx in (x + 10, x + 22):
            for j in range(8):
                p.P(bx - 2, jy + 8 + j, 5, 1, K["ink"])
    obj(p, "rv.sk.fangbg", fangbg, ("fangbg", x, jy, p.alpha, p.tx, p.ty))
    bone_part(p, "rv.sk.jaw", JAWR, x, jy, eye, dark, 1)

    def fangs():
        for bx in (x + 10, x + 22):
            for j in range(8):
                p.P(bx - 1 + (((j >> 1) + (1 if d > 0 else 0)) % 2), jy + 8 + j, 3, 1, "#ff6a2a" if j % 2 else "#9e3412")
            p.P(bx - 1, jy + 16, 3, 1, K["am"])
    obj(p, "rv.sk.fangs", fangs, ("fangs", x, jy, d > 0, p.alpha, p.tx, p.ty))
    bone_part(p, "rv.sk.cran", CRAN, x, cy, eye, dark, 11)
    horn_helm(p, "rv.sk.helm", x, cy, dark)
    p.alpha = old


def tiny(p, txt, x, y, c):
    ox = x
    for ch in txt:
        r = FONT[ch]
        for j, row in enumerate(r):
            for i in range(5):
                if row[i] == "X":
                    p.P(ox + i - 1, y + j - 1, 3, 3, K["ink"])
        for j, row in enumerate(r):
            for i in range(5):
                if row[i] == "X":
                    p.P(ox + i, y + j, 1, 1, c)
        ox += 6


def draw_rev(p, st):
    e, out, ot, rem = st["e"], st["out"], st["ot"], st["rem"]
    win = 5
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    CX = MX
    beats = [0.1, 0.27, 0.44]
    for k in range(14):
        for m in range(4):
            beats.append(0.8 + 1.8 * k + 0.17 * m)
    bi = -1
    for i, b in enumerate(beats):
        if b <= e:
            bi = i
    age = e - beats[bi] if bi >= 0 else 9
    laugh = (not out) and age < 0.17
    d = t = 0
    if laugh:
        d = 6 if age < 0.05 else 3 if age < 0.11 else 0
        t = 3 if d == 6 else 1 if d == 3 else 0
    elif out == "cast":
        d = 6 if ot < 0.18 else 3 if ot < 0.26 else 0
        t = 3 if d == 6 else 1 if d == 3 else 0
    elif out == "exp":
        d = 3 if ot < 0.1 else 2 if ot < 0.2 else 0
    dark = out == "exp" and ot > 0.1
    eye = K["ink"] if dark else K["wh"] if (out == "cast" and ot < 0.1) else K["am"] if am else (K["pk"] if bi % 2 else K["cy"])
    sy = 14
    if not out and e < 0.1:
        sy = 14 + jround((1 - ease_out(clamp(e / 0.1))) * 16)
        obj(p, "rv.sdisc", lambda: p.disc(CX, 32, jround(26 * (1 - e / 0.1)), "rgba(255,46,151,.35)"))
    if d >= 3:
        for n, sd in enumerate((-1, 1)):
            c = K["cy"] if bi % 2 else K["pk"]

            def lines(sd=sd, c=c):
                p.line(CX + sd * 23, sy + 7, CX + sd * 28, sy + 4, c, 1)
                p.line(CX + sd * 25, sy + 15, CX + sd * 31, sy + 15, c, 1)
                p.line(CX + sd * 23, sy + 23, CX + sd * 28, sy + 26, c, 1)
            obj(p, f"rv.laugh{n}", lines)
    if not out:
        rank = 0
        for i, tb in enumerate(beats):
            a = e - tb
            if a < 0 or a >= 0.4:
                continue
            sd = 1 if i % 2 else -1
            c = K["cy"] if ((i == 0) if i < 3 else (i - 3) % 4 == 0) else K["pk"]            # RETUNE: i % 3 == 0 in the mockup
            obj(p, f"rv.ha{rank}", lambda a=a, sd=sd, c=c: p.glow(q4(1 - a / 0.4), lambda: tiny(p, "HA", jround(CX + sd * (22 + a * 60) - 5), jround(36 - a * 45), c)))
            rank += 1
    if out == "cast":
        if ot < 0.08:
            obj(p, "rv.cdisc", lambda: p.disc(CX, 32, 34, "rgba(255,240,250,.4)"))
        for i in range(8):
            a = i * math.pi / 4
            r = 14 + jround(ot * 140)
            obj(p, f"rv.cha{i}", lambda i=i, a=a, r=r: p.glow(q4(1 - ot / 0.45), lambda: tiny(p, "HA", jround(CX + math.cos(a) * r - 5), jround(34 + math.sin(a) * r * 0.8 - 3), K["cy"] if i % 2 else K["pk"])))
    sa = 1
    if out == "cast":
        sa = q4(1 - clamp((ot - 0.2) / 0.25))
    if sa > 0:
        laugh_skull(p, CX - 16, sy, eye, d, t, dark, sa)
    base = PAL["dim"] if out == "exp" else PAL["vioA"] if am else PAL["vio"]
    COLS = {5: [0, 1, 2, 3, 4], 3: [0, 2, 4], 1: [2]}

    def fn(i, ch, x, y, lw):
        dl = 0.22 + 0.05 * i
        wd, px, py, al = 5, x, y, 1
        if not out:
            if e < dl:
                return None
            pr = clamp((e - dl) / 0.32)
            if pr < 1:
                sx = CX - 5
                px = jround(sx + (x - sx) * ease_out(pr))
                py = jround(44 + (y - 44) * pr - abs(math.sin(pr * math.pi * 2.5)) * (1 - pr) * 16)
                wd = [5, 3, 1, 3][int(math.floor(pr * 12)) % 4]
            elif laugh:
                py = y - ((bi + i) % 2)
        elif out == "cast":
            k = max(0, ot - i * 0.02)
            px = jround(x + k * k * 700)
            py = jround(y - abs(math.sin(k * 16)) * 8 * (1 - clamp(k / 0.5)))
            wd = [5, 3, 1, 3][int(math.floor(k * 30)) % 4]
            al = q4(1 - clamp((ot - 0.15) / 0.35))
        else:
            wd = 1 if ot > 0.35 else 3 if ot > 0.15 else 5
            py = y + int(math.floor(ot / 0.15))
        if al <= 0:
            return None
        sh = (5 - wd) * SC / 2
        return {"x": px + jround(sh), "y": py, "pal": base, "cols": COLS[wd]}
    x0, w = word(p, "rv", "REVENGE", WY, fn)
    if e >= 0.4 and (not out or out == "exp"):
        rune(p, "rv.runeL", x0 - 11, WY + 4, RUNE_A, K["am"] if am else K["cy"])
        rune(p, "rv.runeR", x0 + w + 7, WY + 4, RUNE_A, K["am"] if am else K["cy"])
    if e >= 0.4:
        drain(p, win, clamp(1 - ot / 0.1) if out == "cast" else clamp((e - 0.4) / 0.15), out == "exp" or st["am"], out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# VICTORY RUSH: war cry bust
# ------------------------------------------------------------------------------------------------------------------------
def outlined(p, pts, c):
    for ox, oy in OFF8:
        p.poly([[x + ox, y + oy] for x, y in pts], K["ink"])
    p.poly(pts, c)


def big_line(p, x0, y0, x1, y1, c, th, ink):
    h = th // 2
    if ink:
        p.line(x0 - h - 1, y0 - h - 1, x1 - h - 1, y1 - h - 1, K["ink"], th + 2)
    p.line(x0 - h, y0 - h, x1 - h, y1 - h, c, th)


def plus(p, x, y, c):
    p.P(x - 1, y - 2, 3, 5, K["ink"])
    p.P(x - 2, y - 1, 5, 3, K["ink"])
    p.P(x, y - 1, 1, 3, c)
    p.P(x - 1, y, 3, 1, c)
    p.P(x, y, 1, 1, K["wh"])


def bust(p, CX, oy, mh, puff, eye, lower, dim, sway):
    def Y(v):
        return jround(v + oy)

    def B(pts):
        return [[x, Y(y)] for x, y in pts]
    fy = 30 + lower * 18
    el = [CX + 25, 44 + lower * 8]
    top = fy - 24

    def arm():
        big_line(p, CX + 20, Y(52), el[0], Y(el[1]), "#a3203f", 6, True)
        big_line(p, el[0], Y(el[1]), CX + 28, Y(fy), "#e8a87c", 5, True)
        p.P(CX + 25, Y(fy + 4), 6, 2, K["am"])
        p.P(CX + 26, Y(top) - 1, 4, 34, K["ink"])
        p.P(CX + 27, Y(top), 2, 32, "#6e1430")
        outlined(p, B([[CX + 28, top], [CX + 37, top - 3], [CX + 39, top + 5], [CX + 35, top + 12], [CX + 28, top + 10]]), "#6c5a9a" if dim else "#7fc8e8")
        p.poly(B([[CX + 29, top + 1], [CX + 34, top], [CX + 30, top + 6]]), "#f3fbff")
        p.P(CX + 28, Y(top - 5), 1, 5, K["ink"])
        p.P(CX + 28, Y(top - 4), 1, 4, "#a898d0")
        p.disc(CX + 28, Y(fy), 4, K["ink"])
        p.disc(CX + 28, Y(fy), 3, "#e8a87c")
        p.P(CX + 27, Y(fy - 2), 2, 1, "#ffd0a0")
    obj(p, "vc.arm", arm, ("arm", CX, oy, round(lower, 6), dim, p.alpha, p.tx, p.ty))

    def torso():
        outlined(p, B([[CX - 28, 59], [CX - 24, 50], [CX - 13, 46], [CX + 13, 46], [CX + 24, 50], [CX + 28, 59]]), "#a3203f")
        p.P(CX - 13, Y(46), 26, 2, "#ff3b5c")
        for i in range(-12, 12, 3):
            p.P(CX + i, Y(45), 3, 3, "#9b8964" if ((i + 12) // 3) % 2 else "#eadfc4")
    obj(p, "vc.torso", torso, ("torso", CX, oy, p.alpha, p.tx, p.ty))
    sw, bp = int(sway), puff

    def beard():
        outlined(p, B([[CX - 13 - bp, 38], [CX - 16 - bp, 46], [CX - 10 - bp + sw, 56], [CX + sw, 59], [CX + 10 + bp + sw, 56], [CX + 16 + bp, 46], [CX + 13 + bp, 38]]), "#ff6a2a")
        for bx in (-7, 0, 7):
            for j in range(12):
                p.P(CX + bx + sw - 1 + (1 if ((j >> 1) % 2) else 0), Y(45 + j), 2, 1, "#ffb04a" if j % 2 else "#9e3412")
        p.poly(B([[CX - 16 - bp, 46], [CX - 13 - bp, 38], [CX - 12, 44], [CX - 11, 54]]), "#9e3412")
        p.P(CX + sw - 1, Y(58), 3, 1, K["am"])
    obj(p, "vc.beard", beard, ("beard", CX, oy, bp, sw, p.alpha, p.tx, p.ty))

    def face1():
        outlined(p, B([[CX - 12, 27], [CX - 12, 36], [CX - 9, 42], [CX + 9, 42], [CX + 12, 36], [CX + 12, 27]]), "#e8a87c")
        p.poly(B([[CX + 7, 28], [CX + 12, 28], [CX + 12, 36], [CX + 9, 42], [CX + 6, 42]]), "#b8704a")
        p.P(CX - 11, Y(28), 4, 2, "#ffd0a0")
        p.P(CX - 9, Y(31), 5, 2, "#fff6e0")
        p.P(CX + 4, Y(31), 5, 2, "#fff6e0")
    obj(p, "vc.face1", face1, ("face1", CX, oy, p.alpha, p.tx, p.ty))

    def pupils():
        p.P(CX - 7, Y(31), 2, 2, eye)
        p.P(CX + 5, Y(31), 2, 2, eye)
    obj(p, "vc.pupils", pupils, ("pupils", CX, oy, eye, p.alpha, p.tx, p.ty))

    def face2():
        p.line(CX - 10, Y(28), CX - 3, Y(30), K["ink"], 2)
        p.line(CX + 10, Y(28), CX + 3, Y(30), K["ink"], 2)
        p.P(CX - 1, Y(33), 2, 3, "#b8704a")
    obj(p, "vc.face2", face2, ("face2", CX, oy, p.alpha, p.tx, p.ty))

    def mouth():
        p.P(CX - 7, Y(36), 14, mh + 2, K["ink"])
        p.P(CX - 6, Y(37), 12, mh, "#12030a")
        p.P(CX - 5, Y(37), 10, 2, "#fff6e0")
        if mh >= 8:
            p.P(CX - 4, Y(37 + mh - 2), 8, 2, "#fff6e0")
        if mh >= 6:
            p.P(CX - 3, Y(37 + mh - 4), 6, 2, "#ff3b5c")
    obj(p, "vc.mouth", mouth, ("mouth", CX, oy, mh, p.alpha, p.tx, p.ty))

    def helm():
        outlined(p, B([[CX - 13, 27], [CX - 14, 19], [CX - 9, 13], [CX + 9, 13], [CX + 14, 19], [CX + 13, 27]]), "#3a2c5c" if dim else "#6c5a9a")
        p.P(CX - 8, Y(14), 16, 1, "#6c5a9a" if dim else "#a898d0")
        p.P(CX - 13, Y(24), 26, 3, K["ink"])
        p.P(CX - 12, Y(25), 24, 1, "#4a3e72" if dim else "#8a7ab8")
        for rx in (-9, -1, 7):
            p.P(CX + rx, Y(25), 2, 1, K["am"])
        p.P(CX - 1, Y(27), 2, 8, "#8a7ab8")
        for sd in (-1, 1):
            bx = CX + sd * 13
            pts = [[bx, Y(20)], [bx + sd * 5, Y(15)], [bx + sd * 7, Y(9)], [bx + sd * 5, Y(4)]]
            for i in range(3):
                p.line(pts[i][0] - 2, pts[i][1] - 2, pts[i + 1][0] - 2, pts[i + 1][1] - 2, K["ink"], 5)
            for i in range(3):
                p.line(pts[i][0] - 1, pts[i][1] - 1, pts[i + 1][0] - 1, pts[i + 1][1] - 1, K["am"] if i == 2 else "#eadfc4", 3)
    obj(p, "vc.helm", helm, ("helm", CX, oy, dim, p.alpha, p.tx, p.ty))


def draw_vic(p, st):
    e, out, ot, rem = st["e"], st["out"], st["ot"], st["rem"]
    win = 20
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    CX = MX - 8
    heal = K["am"] if am else K["gr"]
    yt = -1
    if not out:
        if 0.15 <= e < 0.6:
            yt = e - 0.15
        elif e >= 0.9:
            w = (e - 0.9) % 2.0                                  # RETUNE: 2.2 in the mockup
            if w < 0.7:
                yt = w
    yelling = yt >= 0 or (out == "cast" and ot < 0.25)
    mh = (11 if (out == "cast" or (0.1 < yt < 0.5)) else 8) if yelling else (3 if int(math.floor(e * 4)) % 2 else 4)
    if out == "exp":
        mh = 5 if ot < 0.15 else 3 if ot < 0.3 else 2
    lower = 0.0
    if not out and e < 0.3:
        lower = clamp(1 - (e - 0.12) / 0.18)
    if out == "exp":
        lower = clamp(ot / 0.4)
    if out == "cast":
        lower = -0.25
    oy = 0
    if not out and e < 0.14:
        oy = jround((1 - ease_out(clamp(e / 0.14))) * 40)
    elif not out and e > 0.4:
        oy = 1 if int(math.floor(e * 2)) % 2 else 0
    if yelling and not out:
        oy -= 1
    if out == "exp":
        oy += min(2, int(math.floor(ot / 0.15)))
    puff = 2 if yelling else 0
    sway = (1 if int(math.floor(e * 30)) % 2 else -1) if yelling else 0
    eye = K["ink"] if (out == "exp" and ot > 0.1) else K["am"] if am else (K["gr"] if int(math.floor(e * 3)) % 2 else "#d8ffe8")
    if e >= 0.08 and not (out == "cast" and ot > 0.3):
        k = 1 if out else clamp((e - 0.08) / 0.2)
        alt = math.pi / 12 if int(math.floor(e * 5)) % 2 else 0
        ro = 16 + jround(36 * k)

        def rays():
            for r in range(12):
                a = r * math.pi / 6 + alt
                ri = 16
                p.glow(0.1 if out == "exp" else 0.2, lambda a=a: p.poly([[CX + math.cos(a) * ro, 32 + math.sin(a) * ro],
                                                                       [CX + math.cos(a - 0.12) * ri, 32 + math.sin(a - 0.12) * ri],
                                                                       [CX + math.cos(a + 0.12) * ri, 32 + math.sin(a + 0.12) * ri]], K["am"]))
        obj(p, "vc.rays", rays)
        pu = 0.7 if int(math.floor(e * 3)) % 2 else 1

        def beams():
            for w, a in ((44, .07), (30, .1), (14, .14)):
                p.glow(a * pu * 4, lambda w=w: p.P(CX - w / 2, 4, w, 56, heal))
        obj(p, "vc.beams", beams)
    if yt >= 0:
        for n, dly in enumerate((0, 0.18)):
            s = yt - dly
            if 0 <= s < 0.45:
                r = jround((10 + s * 105) / 2) * 2
                obj(p, f"vc.arc{n}", lambda s=s, r=r: p.glow(q4(1 - s / 0.45), lambda: (p.arc(CX, 40, r, heal), p.arc(CX, 40, r - 3, "#d8ffe8"))))
    if out == "cast":
        if ot < 0.1:
            obj(p, "vc.cdisc", lambda: p.disc(CX, 34, 34, "rgba(216,255,232,.4)"))
        for i in range(12):
            a = i * math.pi / 6
            dd = jround(ot * 130)
            obj(p, f"vc.cplus{i}", lambda i=i, a=a, dd=dd: p.glow(q4(1 - ot / 0.5), lambda: plus(p, CX + math.cos(a) * (14 + dd), 36 + math.sin(a) * (14 + dd) * 0.8, K["gr"] if i % 2 else "#d8ffe8")))
    ba = 1
    if out == "cast":
        ba = q4(1 - clamp((ot - 0.25) / 0.3))
    if ba > 0:
        old = p.alpha
        p.mul(ba)
        bust(p, CX, oy, mh, puff, eye, lower, out == "exp" and ot > 0.1, sway)
        p.alpha = old
    if 0 <= yt < 0.5:
        for i in range(9):
            a = (-170 + i * 20) * math.pi / 180
            r0 = 26 + yt * 40 + ((i * 7) % 5)
            r1 = r0 + 7
            if abs(a + math.pi * 0.17) < 0.3:
                continue
            obj(p, f"vc.shl{i}", lambda i=i, a=a, r0=r0, r1=r1: p.glow(q4(1 - yt / 0.5), lambda: p.line(CX + math.cos(a) * r0, 36 + math.sin(a) * r0 * 0.9, CX + math.cos(a) * r1, 36 + math.sin(a) * r1 * 0.9, K["wh"] if i % 2 else heal, 1)))
    if not out and e >= 0.2:
        for i in range(10):
            ph = (e * 0.5 + i * 0.1) % 1
            px = CX - 44 + (i * 17) % 88 + jround(math.sin(e * math.pi + i) * 2)        # RETUNE: sin(e * 3 + i)
            if abs(px - CX) < 16:
                continue
            obj(p, f"vc.plus{i}", lambda i=i, ph=ph, px=px: p.glow(q4(1 - ph * ph), lambda: plus(p, px, 58 - ph * 46, "#d8ffe8" if i % 3 == 0 else heal)))
    base = PAL["dim"] if out == "exp" else PAL["helA"] if am else PAL["hel"]
    W = layout("VICTORY RUSH")[1]
    if not out and e > 0.45:
        obj(p, "vc.tglow", lambda: p.glow(0.1 if int(math.floor(e * 3)) % 2 else 0.16, lambda: p.P(MX - W / 2 - 6, WY - 4, W + 12, 22, heal)))

    def fn(i, ch, x, y, lw):
        d = 0.2 + 0.035 * i
        py, px, al, flash = y, x, 1, False
        if not out:
            if e < d:
                return None
            pr = clamp((e - d) / 0.16)
            py = y + jround((1 - ease_out(pr)) * 22)
            if pr >= 1:
                k = e - d - 0.16
                if k < 0.1:
                    py = y - [3, 2, 1, 0][int(math.floor(k / 0.025))]
                    flash = True
                elif e > 0.5 and math.sin(e * (math.pi * 1.5) - i * 0.6) > 0.55:        # RETUNE: sin(e * 5 - i * 0.6)
                    py = y - 1
                if yt >= 0 and e > 0.5:
                    kk = yt - i * 0.015
                    if 0 <= kk < 0.2:
                        py = y - [2, 3, 2, 1][int(math.floor(kk / 0.05))]
        elif out == "cast":
            k = max(0, ot - i * 0.02)
            px = jround(x + k * k * 900)
            al = q4(1 - clamp((ot - 0.15) / 0.4))
            if k > 0 and al > 0 and px < MX + 90:
                obj(p, f"vc.trail{i}", lambda: p.glow(0.5 * al, lambda: p.line(x, y + 7, px - 2, y + 7, K["gr"], 1)))
        else:
            py = y + int(math.floor(ot / 0.12))
        if al <= 0:
            return None
        if flash:
            obj(p, f"vc.flash{i}", lambda: p.glow(0.5, lambda: p.P(px - 2, py - 2, lw + 4, 18, K["am"])))
        return {"x": px, "y": py, "pal": base}
    word(p, "vc", "VICTORY RUSH", WY, fn)
    if e >= 0.4:
        drain(p, win, clamp(1 - ot / 0.1) if out == "cast" else clamp((e - 0.4) / 0.15), out == "exp" or st["am"], out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# Sequences
# ------------------------------------------------------------------------------------------------------------------------
# (win, castAt, drawer, enter frames, held (start, frames), amber (start, frames))
SPELLS = {
    "overpower": dict(tag="op", win=5.0, cast_at=3.0, draw=draw_over, enter=15, held=(15, 90), amber=(105, 45)),
    "revenge": dict(tag="rv", win=5.0, cast_at=3.0, draw=draw_rev, enter=26, held=(26, 54), amber=(26, 54)),
    "victoryrush": dict(tag="vc", win=20.0, cast_at=8.0, draw=draw_vic, enter=27, held=(27, 120), amber=(27, 120)),
}
ORDER = ("overpower", "revenge", "victoryrush")
CAST_FRAMES, EXP_FRAMES = 19, 22        # the exits: 0.6 s and 0.7 s at 30 Hz, both ends included


def states(sp):
    win = sp["win"]

    def live(f, am):
        e = f / DT + EPS
        return {"e": e, "out": None, "ot": 0.0, "rem": win - e, "am": am}

    def leave(kind, j):
        ot = j / DT + EPS
        at = sp["cast_at"] if kind == "cast" else win
        return {"e": at + ot, "out": kind, "ot": ot, "rem": win - sp["cast_at"] if kind == "cast" else 0.0, "am": False}
    h0, hn = sp["held"]
    a0, an = sp["amber"]
    return {
        "enter": [live(f, False) for f in range(sp["enter"])],
        "held": [live(f, False) for f in range(h0, h0 + hn)],
        "amber": [live(f, True) for f in range(a0, a0 + an)],
        "cast": [leave("cast", j) for j in range(CAST_FRAMES)],
        "exp": [leave("exp", j) for j in range(EXP_FRAMES)],
    }


SEQS = ("enter", "held", "amber", "cast", "exp")


def slot_order(frames):
    """One fixed back to front order of every object key the spell uses; raises if two frames disagree."""
    first, after = {}, {}
    for fr in frames:
        keys = [it[0] for it in fr]
        assert len(set(keys)) == len(keys), f"duplicate keys in a frame: {keys}"
        for k in keys:
            first.setdefault(k, len(first))
        for a, b in zip(keys, keys[1:]):
            after.setdefault(a, set()).add(b)
    indeg = {k: 0 for k in first}
    for a, bs in after.items():
        for b in bs:
            indeg[b] += 1
    out, ready = [], sorted((k for k in first if indeg[k] == 0), key=first.get)
    while ready:
        k = ready.pop(0)
        out.append(k)
        for b in sorted(after.get(k, ()), key=first.get):
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
        ready.sort(key=first.get)
    assert len(out) == len(first), "object order cycle: " + ", ".join(k for k in first if k not in out)
    return out


def bake():
    p = Painter()
    data = {}
    for name in ORDER:
        sp = SPELLS[name]
        seqs = states(sp)
        built = {}
        for s in SEQS:
            fl = []
            for st in seqs[s]:
                p.reset()
                sp["draw"](p, st)
                fl.append(list(p.items))
            built[s] = fl
        order = slot_order([fr for s in SEQS for fr in built[s]])
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
        data[name] = dict(slots=len(order), fill=fill, seqs=deltas, order=order, built=built, win=sp["win"])
    return p, data


# ------------------------------------------------------------------------------------------------------------------------
# Atlases, TGA, manifest
# ------------------------------------------------------------------------------------------------------------------------
def pow2(n):
    v = 1
    while v < n:
        v *= 2
    return v


def pack(sprites):
    """Shelf packing, tallest first, into atlases at most ATLAS_MAX wide and tall. Returns [(w, h, [(sid, tx, ty)])]."""
    order = sorted(range(len(sprites)), key=lambda i: (-sprites[i][1], -sprites[i][0], i))
    atlases, cur, x, y, shelf = [], [], 0, 0, 0
    for i in order:
        w, h = sprites[i][0] + 2 * PAD, sprites[i][1] + 2 * PAD
        assert w <= ATLAS_MAX and h <= ATLAS_MAX
        if x + w > ATLAS_MAX:
            x, y, shelf = 0, y + shelf, 0
        if y + h > ATLAS_MAX:
            atlases.append((cur, y + shelf))
            cur, x, y, shelf = [], 0, 0, 0
        cur.append((i + 1, x + PAD, y + PAD))
        x += w
        shelf = max(shelf, h)
    atlases.append((cur, y + shelf))
    out = []
    for placed, used in atlases:
        h = max(64, pow2(used))
        w = max(64, pow2(max(tx + sprites[sid - 1][0] + PAD for sid, tx, _ in placed)))
        out.append((w, h, placed))
    return out


def write_tga(path, atlas, sprites):
    w, h, placed = atlas
    px = np.zeros((h, w, 4), np.uint8)
    for sid, tx, ty in placed:
        sw, sh, data = sprites[sid - 1]
        a = np.frombuffer(data, np.uint8).reshape(sh, sw, 4)
        px[ty:ty + sh, tx:tx + sw, 0] = a[..., 2]
        px[ty:ty + sh, tx:tx + sw, 1] = a[..., 1]
        px[ty:ty + sh, tx:tx + sw, 2] = a[..., 0]
        px[ty:ty + sh, tx:tx + sw, 3] = a[..., 3]
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(px.tobytes())
    print(f"wrote {path} ({w}x{h}, {os.path.getsize(path)} bytes)")


def lua_list(vals):
    return "{ " + ", ".join(str(v) for v in vals) + " }"


def lua_manifest(p, atlases, data):
    L = [
        "-- Forever STUwave: the Warrior power-up alerts' sprite manifest and frame lists.",
        "-- GENERATED by tools/assets/generate_warrior_powerups.py; do not edit (warriorpowerups-harness.py checks it).",
        "-- ATLAS[n] = { file, w, h }. SPRITE[id] = { atlas, tx, ty, w, h }: a texel rect in its atlas; one texel is one sprite px.",
        "-- SPELL.seqs[name][frame] = flat list of { slot, sprite, x, y } (x, y = sprite px on the 150 x 96 canvas; sprite 0 hides",
        "-- the slot). The first frame of each sequence is a snapshot, the rest are deltas against the frame before. Slots are",
        "-- in back to front order. FILL slots are the drain bar's fill: their sprite is one texel and the module stretches it.",
        "",
        "local _, FS = ...",
        "",
        "FS.WarriorPowerUpArt = {",
        f"    SPX = {SPX}, GW = {GW}, GH = {GH}, MX = {MX},",
        f"    AMBER = {AMBER}, BAR_FILL = {BAR_W - 2},",
        "    ATLAS = {",
    ]
    for n, (w, h, _) in enumerate(atlases, 1):
        L.append(f'        {{ file = "warrior_powerups_{n}", w = {w}, h = {h} }},')
    L += ["    },", "    SPRITE = {"]
    where = {}
    for n, (w, h, placed) in enumerate(atlases, 1):
        for sid, tx, ty in placed:
            where[sid] = (n, tx, ty)
    for sid in range(1, len(p.sprites) + 1):
        n, tx, ty = where[sid]
        sw, sh, _ = p.sprites[sid - 1]
        L.append(f"        {{ {n}, {tx}, {ty}, {sw}, {sh} }},")
    L += ["    },", "    SPELL = {"]
    for name in ORDER:
        d = data[name]
        sp = SPELLS[name]
        L += [f"        {name} = {{",
              f"            win = {int(sp['win'])}, castAt = {int(sp['cast_at'])}, slots = {d['slots']}, fill = {lua_list(d['fill'])},",
              f"            enterFrames = {sp['enter']}, heldStart = {sp['held'][0]}, amberStart = {sp['amber'][0]},",
              "            seqs = {"]
        for s in SEQS:
            L.append(f"                {s} = {{")
            for flat in d["seqs"][s]:
                L.append("                    " + lua_list(flat) + ",")
            L.append("                },")
        L += ["            },", "        },"]
    L += ["    },", "}", ""]
    return "\n".join(L)


def verify(p, atlases, data):
    for sid, (w, h, _) in enumerate(p.sprites, 1):
        assert 1 <= w <= GW and 1 <= h <= GH
    for name in ORDER:
        d = data[name]
        for s in SEQS:
            for fr in d["built"][s]:
                for key, sid, x, y in fr:
                    w, h, _ = p.sprites[sid - 1]
                    assert 0 <= x and 0 <= y and x + w <= GW and y + h <= GH, (name, s, key)
        assert all(d["fill"]), f"{name}: the fill slots must all be used"
        assert d["fill"] == sorted(d["fill"]) and d["fill"][-1] - d["fill"][0] == 2, "fill slots must be adjacent and in order"
    for w, h, placed in atlases:
        assert w <= ATLAS_MAX and h <= ATLAS_MAX


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "WarriorPowerUpArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "WarriorPowerUpArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    p, data = bake()
    atlases = pack(p.sprites)
    verify(p, atlases, data)
    total = sum(w * h for w, h, _ in p.sprites)
    print(f"{len(p.sprites)} sprites, {total} px, {len(atlases)} atlas(es)")
    for name in ORDER:
        d = data[name]
        print(f"  {name}: {d['slots']} slots, " + ", ".join(f"{s} {len(d['seqs'][s])}f/{sum(len(f) for f in d['seqs'][s]) // 4} deltas" for s in SEQS))
    if "--stats" in sys.argv:
        return
    os.makedirs(here, exist_ok=True)
    for n, atlas in enumerate(atlases, 1):
        write_tga(os.path.join(here, f"warrior_powerups_{n}.tga"), atlas, p.sprites)
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(p, atlases, data))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
