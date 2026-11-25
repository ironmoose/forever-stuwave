#!/usr/bin/env python3
"""Bake the Warrior power-up alerts (v2): Overpower (the bearded double axe chopping into a rotating 16 rune Elder Futhark circle),
Revenge (the cackling Viking skull on a round shield, little round shields flanking the title), Victory Rush (crossed flaming
bearded axes on a red sunburst, a clang, a green heal).

The source is the design mockup "Gunsight Warrior: proc alerts v2" (2026-11-17, kept beside the art as
warrior_powerups_art/mockup-v2-2026-11-17.html), drawn on a 150 x 96 sprite grid with a canvas API: rects, Bresenham lines, discs,
pixel rings, a 5 x 7 bitmap title font, the generated pixel art (skull_px, axe_clean54, vr_circle, vr_axeL, vr_axeR,
the vr_flame pixel list; all in warrior_powerups_art/) drawn with an 8 way ink outline and a CSS filter, and a last 1 px scanline
pass. This file is a port of the mockup's LAST definitions of drawOver, drawRev, drawVic and their helpers. It plays every frame the
alert can show at 30 Hz (the mockup's own clock) into a DISPLAY LIST: the ordered objects of the frame (each letter, the axe, a ring,
a spark, the skull's jaw, ...) as sprites. An object is cut to its own bounding boxes, the scanline pass is baked into it for the
absolute rows it lands on, and identical sprites are shared between frames. The module (WarriorPowerUps.lua) only replays the lists:
no art is drawn at runtime.

Each spell has five SEQUENCES (frame counts at 30 Hz; the first frame of every sequence is a snapshot, the rest are deltas):

    enter   the entrance, played once from the open of the window
    held    the idle loop while the window is open (Overpower: the whole 3.5 s before the amber part, no loop needed;
            Revenge: its 1.8 s cackle cycle; Victory Rush: its 2.4 s clang cycle, see RETUNE)
    amber   the same loop in amber, for the last 1.5 s (Overpower: the real last 1.5 s of its 5 s window)
    cast    the exit when the player casts the spell (0.6 s)
    exp     the exit when the window runs out unused (0.7 s)

The drain bar is NOT baked whole: its frame and tick mark are display list objects, but its fill is three 1 texel sprites
(FILL_KEYS) that the module stretches to the width the real remaining time gives.

The art that moves independently of the rest is cut into its own object (every letter, every rune of the circle, the pulse that runs
round a ring, the light wedge on the sunburst, each axe's flames, every spark), and an object that repeats is painted once (`sig`).
A sparse object (a ring, a disc of glow) is cut into up to PIECES_RING tight boxes so its empty middle costs no atlas.

RETUNE. The module needs seamless loops, so every periodic term of Revenge's and Victory Rush's idle animation repeats exactly in
its loop (the bake checks this: frame f + loop must draw the same list as frame f). Where the mockup's period does not divide the
loop it was moved to the nearest whole number of periods; TUNE below holds each number next to the mockup's. Overpower is not
looped (its 5 s window plays straight through) and is exact.

  Revenge (1.8 s loop):
    * the HA bits were cyan on every third beat; a cackle has four beats, so they are cyan on the first beat of each cackle.
    * the shield cracks pulse with sin(e * 5): now sin(e * 3.49), one period per loop.
  Victory Rush (2.4 s loop):
    * the heal plus signs drift 0.45 cycles/s (2.22 s): now 1 / 2.4. Their sideways wobble sin(e * 3 + i): now 2.62 rad/s.
    * the sunburst's light wedge turned 1.6 rad/s: now 2.62 rad/s, one turn per clang.
    * the title glow toggled every 1/3 s (3.6 toggles per loop): now every 0.3 s.
    * the clang's spark angles carried the clang's index (a = i * 2.4 + ci, so each clang turned the fan): the repeating clangs
      use ci = 1; the first (big) clang keeps its own fan.
    * the flames are a 1.2 s loop inside the 2.4 s loop (two passes, half the atlas): the tip flicker hashes 13 steps/s -> 13.33
      (amber 20 -> 20), the flame tip licks 9.1 -> 9.17 steps/s (amber 14 -> 14.17), the colour wave sin(e * 11.7) -> sin(e * 10.47)
      (amber 18 -> 15.71), and the hash input is the step number modulo the steps in a pass.
    * the glow disc toggle (every 0.4 s) and the clang and heal pulse period (2.4 s) already divide the loop.

DEVIATIONS from the canvas. The sunburst's light wedge is a canvas path fill (antialiased); the bake covers it with a 16 x 16
supersample of the same polygon, so a few edge pixels differ by up to 6 of 255 levels (7 of the 585 baked frames). A CSS filter
(brightness(0) for the outline, grayscale(1) brightness(b) for the dimmed frames) is computed in float and rounded once, not by the
browser's own pipeline, so a dimmed pixel can differ by a level. The wedge is its own object, a translucent overlay on the plain
sunburst (a source-atop fill is a plain over blend on the sunburst's opaque pixels, so the pixels are the same), and Overpower's
white ring pulse is an overlay of only the ring pixels that differ from the plain ring. The v1 page passed ringPx its arguments in the
wrong order so its rings never drew; the v2 calls are fixed and the rings now draw. A canvas ignores a negative globalAlpha, so a
faded out glow() stays at full strength until the exit ends; Painter.mul keeps that. The port was checked against the mockup's own
drawers run in headless Chrome for every baked frame (colour within 4 levels, the wedge pixels above).

    python3 tools/assets/generate_warrior_powerups.py     (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                           FS_ART_LUA_OUTPUT the manifest path, FS_WARRIOR_ART_DIR the art folder)
Needs numpy and Pillow. Deterministic: the same source writes the same bytes.
"""

from __future__ import annotations

import json
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
ART_DIR = os.environ.get("FS_WARRIOR_ART_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "warrior_powerups_art")
TAU = math.pi * 2

K = {"cy": "#22e0ff", "pk": "#ff2e97", "am": "#ffb648", "rg": "#ff3b5c", "ink": "#07030e", "vi": "#a855f7", "wh": "#f3fbff", "gr": "#46e08a"}

# The retuned periodic terms (see RETUNE). MOCKUP_TUNE holds the mockup's own numbers; a replay of the approved mockup in a browser
# sets them to compare the port pixel for pixel. flame: steps (or rad) per second for the tip hash, the lick hash and the colour
# wave, and the steps in one pass (None = the mockup's unbounded hash input).
FLAME_PASS = 1.2
TUNE = dict(
    rv_crack=TAU / 1.8,
    rv_ha_beat=True,
    vc_shine=TAU / 2.4,
    vc_plus_drift=1 / 2.4,
    vc_plus_wobble=TAU / 2.4,
    vc_spark_ci=True,
    flame_hot=dict(tip=16 / FLAME_PASS, lick=11 / FLAME_PASS, wave=2 * TAU / FLAME_PASS, mod=(16, 11)),
    flame_amber=dict(tip=24 / FLAME_PASS, lick=17 / FLAME_PASS, wave=3 * TAU / FLAME_PASS, mod=(24, 17)),
)
MOCKUP_TUNE = dict(
    rv_crack=5.0,
    rv_ha_beat=False,
    vc_shine=1.6,
    vc_plus_drift=0.45,
    vc_plus_wobble=3.0,
    vc_spark_ci=False,
    flame_hot=dict(tip=13.0, lick=13 * 0.7, wave=13 * 0.9, mod=None),
    flame_amber=dict(tip=20.0, lick=20 * 0.7, wave=20 * 0.9, mod=None),
)


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


_IMG = {}


def art(name):
    """A committed art PNG as an 8 bit RGBA array (rows, columns, 4)."""
    if name not in _IMG:
        from PIL import Image
        _IMG[name] = np.asarray(Image.open(os.path.join(ART_DIR, name + ".png")).convert("RGBA")).copy()
    return _IMG[name]


def flame_pixels():
    with open(os.path.join(ART_DIR, "vr_flame.json"), encoding="utf-8") as fh:
        return json.load(fh)


def css_filter(rgb, filt):
    """The CSS filters the mockup uses on a float RGB array (0..255): 'ink' = brightness(0), ('gray', b) = grayscale(1) brightness(b)."""
    rgb = np.asarray(rgb, np.float32)
    if filt is None:
        return rgb
    if filt == "ink":
        return np.zeros_like(rgb)
    gray = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    return np.repeat(np.minimum(255.0, gray * filt[1])[..., None], 3, axis=-1)


# ------------------------------------------------------------------------------------------------------------------------
# The canvas. One object at a time is painted into a transparent 150 x 96 float buffer (premultiplied), then cut to its boxes.
# ------------------------------------------------------------------------------------------------------------------------
GAP_MIN, SAVE_MIN, PIECES_MAX = 3, 160, 8
PIECES_RING, PIECES_DISC, ANY_SAVE = 16, 8, 40


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


def best_cut(sub):
    """(area of the two tight boxes, axis, position) of the straight cut through a tight box that leaves the least area; None for a line."""
    best = None
    for axis in (0, 1):
        m = sub if axis == 0 else sub.T
        h, w = m.shape
        if h < 2:
            continue
        rows = m.any(axis=1)
        first = np.where(rows, m.argmax(axis=1), w)
        last = np.where(rows, w - 1 - m[:, ::-1].argmax(axis=1), -1)
        idx = np.arange(h)
        top_end = np.maximum.accumulate(np.where(rows, idx, -1))
        bot_start = np.minimum.accumulate(np.where(rows, idx, h)[::-1])[::-1]
        pmin, pmax = np.minimum.accumulate(first), np.maximum.accumulate(last)
        smin, smax = np.minimum.accumulate(first[::-1])[::-1], np.maximum.accumulate(last[::-1])[::-1]
        r = np.arange(1, h)
        cost = (top_end[r - 1] + 1) * (pmax[r - 1] - pmin[r - 1] + 1) + (h - bot_start[r]) * (smax[r] - smin[r] + 1)
        j = int(cost.argmin())
        if best is None or cost[j] < best[0]:
            best = (int(cost[j]), axis, int(r[j]))
    return best


def split_any(mask, limit):
    """Cuts a sparse object (a ring) into up to `limit` tight boxes by the straight cut that saves the most area, through its pixels."""
    boxes = [_tight(mask, 0, 0, GW, GH)]
    while len(boxes) < limit:
        gain, at, cut = 0, None, None
        for n, (x0, y0, x1, y1) in enumerate(boxes):
            c = best_cut(mask[y0:y1, x0:x1])
            if c is not None and (x1 - x0) * (y1 - y0) - c[0] > gain:
                gain, at, cut = (x1 - x0) * (y1 - y0) - c[0], n, c
        if at is None or gain < ANY_SAVE:
            break
        x0, y0, x1, y1 = boxes[at]
        _, axis, pos = cut
        parts = [(x0, y0, x1, y0 + pos), (x0, y0 + pos, x1, y1)] if axis == 0 else [(x0, y0, x0 + pos, y1), (x0 + pos, y0, x1, y1)]
        boxes[at:at + 1] = [_tight(mask, *q) for q in parts]
    return boxes


class Painter:
    def __init__(self):
        self.sprites = []            # id - 1 -> (w, h, rgba bytes)
        self.by_bytes = {}
        self.memo = {}
        self.items = []
        self.alpha = 1.0
        self.tx = self.ty = 0
        self.clip = None             # (x0, y0, x1, y1): a canvas clip() rect
        self.filt = None             # the canvas filter that fillRect gets
        self.cur = None
        self.key = None
        self.sig = None
        self.hit = None
        self.pieces = None
        self.flat = None             # a replay of the mockup: every object composited, not cut (the browser comparison)
        self.fill_w = None           # ... with the drain fill at its real width
        self.memo_on = True

    def reset(self):
        self.items = []
        self.alpha = 1.0
        self.tx = self.ty = 0
        self.clip = None
        self.filt = None

    # --- object framing -----------------------------------------------------------------------------------------------
    def begin(self, key, sig=None, pieces=None):
        """Start an object. Returns False when `sig` was baked before (nothing to paint)."""
        self.key, self.pieces = key, pieces
        # a painted object depends on its key (the same sig can mean different art for another key), the state it is drawn under
        # (alpha, translate, clip, filter) and what its sig names; the sprite boxes it cuts hold absolute positions
        self.sig = None if sig is None else (key, sig, self.alpha, self.tx, self.ty, self.clip, self.filt)
        if self.sig is not None and self.memo_on and self.sig in self.memo:
            self.hit = self.memo[self.sig]
            self.cur = None
            return False
        self.hit = None
        self.cur = np.zeros((GH, GW, 4), np.float32)
        return True

    def end(self):
        if self.hit is None:
            if self.flat is not None:
                self.flat[...] = self.cur + self.flat * (1 - self.cur[..., 3:4])
            self.hit = self._cut()
            if self.sig is not None and self.memo_on:
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

    def straight(self, cur=None):
        """The buffer as 8 bit straight RGBA (premultiplied float in), before the scanline pass."""
        cur = self.cur if cur is None else cur
        a8 = np.rint(cur[..., 3] * 255).astype(np.int32)
        a = cur[..., 3:4]
        rgb = np.where(a > 1e-9, cur[..., :3] / np.maximum(a, 1e-9), 0.0)
        return rgb, a8

    def _cut(self):
        """The object as 8 bit straight RGBA with the scanline baked in, cut into the boxes that hold its pixels:
        a sparse object (a letter whose halves flew apart, a ring) becomes several small sprites."""
        rgb, a8 = self.straight()
        mask = a8 > 0
        if not mask.any():
            return ()
        odd = (np.arange(GH) % 2) == 1
        rgb[odd] = rgb[odd] * 0.8 + np.array(INK, np.float32) / 255 * 0.2
        full = np.zeros((GH, GW, 4), np.uint8)
        full[..., :3] = np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8)
        full[..., 3] = np.clip(a8, 0, 255).astype(np.uint8)
        full[~mask] = 0
        out = []
        boxes = split_boxes(mask) if self.pieces is None else split_any(mask, self.pieces)
        for x0, y0, x1, y1 in boxes:
            out.append((self._sprite(full[y0:y1, x0:x1]), x0, y0))
        return tuple(out)

    # --- primitives (the mockup's names) --------------------------------------------------------------------------------
    def _box(self, x0, y0, x1, y1):
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, GW), min(y1, GH)
        if self.clip is not None:
            cx0, cy0, cx1, cy1 = self.clip
            x0, y0, x1, y1 = max(x0, cx0), max(y0, cy0), min(x1, cx1), min(y1, cy1)
        return x0, y0, x1, y1

    def rect(self, x, y, w, h, c):
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        x += self.tx
        y += self.ty
        x0, y0, x1, y1 = self._box(x, y, x + w, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b, ca = c
        a = ca * self.alpha
        if a <= 0:
            return
        if self.filt is not None:
            r, g, b = (float(v) for v in css_filter(np.array([r, g, b]), self.filt))
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

    def disc(self, cx, cy, r, c):
        cc = col(c)
        for dy in range(-r, r + 1):
            w = int(math.floor(math.sqrt(r * r - dy * dy)))
            self.rect(jround(cx) - w, jround(cy) + dy, w * 2 + 1, 1, cc)

    def ring_px(self, cx, cy, r, c, th):
        """ringPx: n points round the circle, each pixel once (the mockup's `seen` set). The v1 page passed (th, c) in the wrong order so
        its rings never drew; the v2 calls are fixed and the rings draw."""
        cc = col(c)
        n = max(24, jround(r * 8))
        seen = set()
        for i in range(n):
            a = i / n * TAU
            x, y = jround(cx + math.cos(a) * r), jround(cy + math.sin(a) * r)
            if (x, y) in seen:
                continue
            seen.add((x, y))
            self.rect(x, y, th, th, cc)

    def sprite(self, im, sx, sy, sw, sh, dx, dy, filt=None):
        """drawImage(im, sx, sy, sw, sh, dx, dy, sw, sh) at an integer offset: nearest, source over, globalAlpha, the canvas filter."""
        dx += self.tx
        dy += self.ty
        x0, y0, x1, y1 = self._box(dx, dy, dx + sw, dy + sh)
        if x1 <= x0 or y1 <= y0:
            return
        src = im[sy:sy + sh, sx:sx + sw][y0 - dy:y1 - dy, x0 - dx:x1 - dx].astype(np.float32)
        a = src[..., 3:4] / 255 * self.alpha
        rgb = css_filter(src[..., :3], filt) / 255
        reg = self.cur[y0:y1, x0:x1]
        reg[..., :3] = rgb * a + reg[..., :3] * (1 - a)
        reg[..., 3:4] = a + reg[..., 3:4] * (1 - a)

    def sprite_ink(self, im, sx, sy, sw, sh, dx, dy, filt=None):
        """spriteInk: the image's 8 way black outline, then the image (with the canvas filter)."""
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            self.sprite(im, sx, sy, sw, sh, dx + ox, dy + oy, "ink")
        self.sprite(im, sx, sy, sw, sh, dx, dy, filt)

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


def obj(p, key, fn, sig=None, pieces=None):
    """Paint one object with `fn` (the common case: paint, then end)."""
    if p.begin(key, sig, pieces):
        fn()
    p.end()


def obj_diff(p, key, paint, paint_base, sig=None, pieces=None):
    """An object that holds only the pixels `paint` changes from `paint_base`: drawn over the plain object it gives `paint` exactly
    (opaque pixels only, so the over blend is a replace)."""
    if p.begin(key, sig, pieces):
        assert p.alpha == 1.0, "a diff overlay needs opaque pixels"
        paint()
        truth = p.cur
        p.cur = np.zeros_like(truth)
        paint_base()
        base = p.cur
        diff = (np.abs(truth - base) > 1e-6).any(axis=2)
        assert (truth[..., 3][diff] == 1.0).all(), "a diff overlay needs opaque pixels"
        p.cur = np.where(diff[..., None], truth, 0).astype(np.float32)
    p.end()


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
    "D": ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],      # for generate_placeholder_alert.py; no Warrior title has a D
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


def rune(p, key, x, y, rows, c):
    p.begin(key, (key, x, y, c, p.alpha, p.tx, p.ty))
    if p.cur is not None:
        for j, r in enumerate(rows):
            for i in range(5):
                if r[i] == "X":
                    p.P(x + i - 1, y + j - 1, 3, 3, K["ink"])
        for j, r in enumerate(rows):
            for i in range(5):
                if r[i] == "X":
                    p.P(x + i, y + j, 1, 1, c)
    p.end()


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


def plus(p, x, y, c):
    p.P(x - 1, y - 2, 3, 5, K["ink"])
    p.P(x - 2, y - 1, 5, 3, K["ink"])
    p.P(x, y - 1, 1, 3, c)
    p.P(x - 1, y, 3, 1, c)
    p.P(x, y, 1, 1, K["wh"])


# ------------------------------------------------------------------------------------------------------------------------
# The drain bar: its frame and tick are objects, its fill is three stretched 1 texel slots (FILL_KEYS).
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
                p.P(x0 + 1, y, p.fill_w or 1, 1, c)          # fill_w only in a replay of the mockup (the real width is the module's)
            p.end()
    if p.begin("bar.mark", ("bar.mark", win, p.alpha)):
        p.P(x0 + 1 + jround(AMBER / win * (BAR_W - 2)), BAR_Y - 1, 1, 7, K["am"])
    p.end()


# ------------------------------------------------------------------------------------------------------------------------
# OVERPOWER: the double axe in front of a rune circle
# ------------------------------------------------------------------------------------------------------------------------
IMP = 0.16                           # the axe bites at this time
AX = dict(W=54, H=54, X=MX - 27, Y=2)
AX_EDGE = [[37, 3], [38, 3], [38, 4], [39, 4], [38, 5], [39, 5], [39, 6], [40, 6], [39, 7], [40, 7], [39, 8], [40, 8], [40, 9], [41, 9],
           [40, 10], [41, 10], [40, 11], [41, 11], [40, 12], [41, 12], [39, 13], [40, 13], [41, 13], [39, 14], [40, 14], [39, 15], [40, 15],
           [39, 16], [40, 16], [38, 17], [39, 17], [36, 18], [37, 18], [38, 18], [39, 18], [36, 19], [37, 19], [38, 19], [36, 20], [37, 20],
           [13, 11], [13, 12], [13, 13], [13, 14], [14, 14], [14, 15], [14, 16], [15, 16], [15, 17], [16, 17], [16, 18], [17, 18], [17, 19]]
AX_SIDES = [sorted((q for q in AX_EDGE if q[0] > 27), key=lambda q: q[1]), sorted((q for q in AX_EDGE if q[0] < 27), key=lambda q: q[1])]
RC = (MX, 30, 29)
# Elder Futhark, 5 x 5: fehu, uruz, thurisaz, ansuz, raidho, kenaz, gebo, wunjo, hagalaz, naudiz, isa, jera, tiwaz, sowilo, algiz, othala
FUTH = [["X.X..", "XX.X.", "X.X..", "X....", "X...."], ["XXX..", "X..X.", "X..X.", "X..X.", "X..X."], ["X....", "XX...", "X.X..", "XX...", "X...."],
        ["X.X..", "XX.X.", "X.X..", "X....", "X...."], ["XX...", "X.X..", "XX...", "X.X..", "X..X."], ["..X..", ".X...", "X....", ".X...", "..X.."],
        ["X...X", ".X.X.", "..X..", ".X.X.", "X...X"], ["XX...", "X.X..", "XX...", "X....", "X...."], ["X..X.", "X..X.", "XXXX.", "X..X.", "X..X."],
        [".X...", "XXX..", ".X...", ".X...", ".X..."], [".X...", ".X...", ".X...", ".X...", ".X..."], ["..X..", ".X.X.", "X...X", ".X.X.", "..X.."],
        ["..X..", ".XXX.", "X.X.X", "..X..", "..X.."], [".X...", "X....", ".X...", "..X..", ".X..."], ["X.X.X", ".XXX.", "..X..", "..X..", "..X.."],
        [".XXX.", "X...X", ".XXX.", "X...X", "X...X"]]


def near_pulse(a, pulse, width):
    return pulse is not None and abs(((a - pulse) % TAU + math.pi * 3) % TAU - math.pi) < width


def ring_points(rr, trace):
    """The points of one ring of the rune circle, traced round from the top: (x, y, angle)."""
    cx, cy, _ = RC
    n = jround(rr * 7)
    pts = []
    for i in range(n):
        a = i / n * TAU
        if a > trace * TAU:
            break
        pts.append((cx + jround(math.sin(a) * rr), cy - jround(math.cos(a) * rr), a))
    return pts


def rune_circle(p, trace, lit, rot, pulse, colr, dkr, dim, burst):
    """runeCircle: two rings traced round from the top (the pulse is a white overlay on the plain ring), spokes and a star behind
    the axe, 16 runes between the rings (each one object, so a step round the circle only moves it)."""
    cx, cy, r = RC
    if dim:
        colr, dkr = "#4a3e72", "#241a36"
    for rr, th, key in ((r, 2, "op.ringO"), (r - 9, 1, "op.ringI")):
        pts = ring_points(rr, trace)
        near = [near_pulse(a, pulse, 0.35) for _, _, a in pts]

        def paint(use, pts=pts, near=near, th=th):
            for (x, y, _), nr in zip(pts, near):
                p.P(x - 1, y - 1, th + 2, th + 2, K["ink"])
                p.P(x, y, th, th, K["wh"] if (use and nr) else colr)
        obj(p, key, lambda paint=paint: paint(False), (key, len(pts), colr, p.alpha, p.tx, p.ty), PIECES_RING)
        if any(near):
            obj_diff(p, key + "p", lambda paint=paint: paint(True), lambda paint=paint: paint(False),
                     (key, "p", tuple(near), len(pts), colr, p.tx, p.ty), PIECES_RING)
    if trace >= 1:
        def spokes():
            for i in range(8):
                a = i * math.pi / 4 + math.pi / 8
                p.line(cx + math.sin(a) * 6, cy - math.cos(a) * 6, cx + math.sin(a) * (r - 11), cy - math.cos(a) * (r - 11), dkr, 1)
            for i in range(4):
                a = i * math.pi / 2
                p.line(cx + math.sin(a) * 8, cy - math.cos(a) * 8, cx + math.sin(a + math.pi / 2) * 8, cy - math.cos(a + math.pi / 2) * 8, dkr, 1)
        obj(p, "op.spokes", spokes, ("spokes", dkr, p.alpha, p.tx, p.ty))
    for i in range(16):
        slot = (i + rot) % 16
        a = slot / 16 * TAU
        rr = r - 4.5 + burst * (1 + (i % 3) * 0.4)
        x, y = jround(cx + math.sin(a) * rr - 2), jround(cy - math.cos(a) * rr - 2)
        c = dkr if i >= lit else K["wh"] if near_pulse(a, pulse, 0.4) else colr

        def paint(i=i, x=x, y=y, c=c):
            for j, row in enumerate(FUTH[i]):
                for k in range(5):
                    if row[k] == "X":
                        p.P(x + k, y + j, 1, 1, c)
        obj(p, f"op.f{i}", paint, (f"op.f{i}", x, y, c, p.alpha, p.tx, p.ty))


def draw_over(p, st):
    e, out, ot = st["e"], st["out"], st["ot"]
    win = 5
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    if not out and IMP <= e < IMP + 0.15:
        k = int(math.floor((e - IMP) / 0.025))
        p.tx = [3, -3, 2, -2, 1, -1][k] if k < 6 else 0
        p.ty = [-2, 2, -1, 1, 0, 0][k] if k < 6 else 0
    hot = K["am"] if am else K["rg"]
    CX, CY = RC[0], RC[1] + 2
    colr = K["am"] if am else K["cy"]
    dk = "#5a3a10" if am else "#16505e"
    # the rune circle draws itself, the runes light one by one, then it turns a step at a time and a pulse runs round it
    trace = 1.0 if out else clamp(e / 0.16)
    lit = max(0, 16 - int(math.floor(ot / 0.03))) if out == "exp" else 16 if out else int(math.floor(clamp((e - 0.12) / 0.3) * 16))
    rot = int(math.floor(max(0, e - 0.6) / 0.35))
    pulse = (e * 2.6) % TAU if (not out and e > 0.6) else None
    burst = jround(ot * 80) if out == "cast" else 0
    rc_a = q4(1 - clamp(ot / 0.4)) if out == "cast" else 1
    p.glow(rc_a, lambda: rune_circle(p, trace, lit, rot, pulse, colr, dk, out == "exp" and ot > 0.08, burst))
    # the bite lights the circle: a flash, a white ring snaps round it once, a pink ring and sparks fly out, embers rise
    if not out and e >= IMP:
        k = e - IMP
        if k < 0.12:
            obj(p, "op.flash", lambda: p.disc(CX, CY, jround(22 * (1 - k / 0.12)), f"rgba(255,240,235,{q4(1 - k / 0.12)})"), None, PIECES_DISC)
        if k < 0.2:
            def snap():
                p.ring_px(RC[0], RC[1], RC[2] + 1, K["wh"], 2)
                p.ring_px(RC[0], RC[1], RC[2] - 9, K["wh"], 1)
            obj(p, "op.snap", lambda: p.glow(q4(1 - k / 0.2), snap), None, PIECES_RING)
        if k < 0.5:
            obj(p, "op.ring", lambda: p.glow(q4(1 - k / 0.5), lambda: p.ring_px(CX, CY, jround(k / 0.5 * 60 / 2) * 2, K["pk"], 2)), None, PIECES_RING)
            for i in range(16):
                a = i * 2.4
                v = 34 + (i * 7) % 26
                x = CX + math.cos(a) * v * k * 2
                y = CY + math.sin(a) * v * k * 2 + 110 * k * k
                c = K["wh"] if i % 3 == 0 else K["am"] if i % 3 == 1 else K["rg"]
                obj(p, f"op.spark{i}", lambda x=x, y=y, c=c: p.glow(q4(1 - k / 0.5), lambda: p.P(x, y, 2, 2, c)))
        if e > 0.5:
            for i in range(7):
                ph = (e * 0.8 + i * 0.14) % 1
                x = CX - 24 + (i * 13) % 48 + jround(math.sin(e * 4 + i) * 2)
                obj(p, f"op.ember{i}", lambda i=i, ph=ph, x=x: p.glow(q4(1 - ph), lambda: p.P(x, CY + 18 - ph * 40, 1 + (i % 2), 1 + (i % 2), K["am"] if i % 2 else hot)))
    # the axe: chops straight down from above in ghost frames, bites, then holds; a glint walks each blade edge
    im = art("axe_clean54")
    W, H = AX["W"], AX["H"]
    if not out and e < IMP:
        pp = clamp(e / IMP)
        dy = jround(-70 * (1 - pp * pp))
        if pp > 0.35:
            for i in range(6):
                obj(p, f"op.line{i}", lambda i=i: p.glow(0.6, lambda: p.line(AX["X"] + 12 + i * 6, AX["Y"] + dy - 30 + i * 3, AX["X"] + 12 + i * 6, AX["Y"] + dy + 4,
                                                                                 K["cy"] if i % 2 else K["wh"], 1)))
        for n, (lag, al) in enumerate(((-18, .18), (-11, .3), (-5, .5))):
            obj(p, f"op.ghost{n}", lambda lag=lag, al=al: p.glow(al, lambda: p.sprite_ink(im, 0, 0, W, H, AX["X"], AX["Y"] + dy + lag)))
        obj(p, "op.axeIn", lambda: p.sprite_ink(im, 0, 0, W, H, AX["X"], AX["Y"] + dy))
    else:
        off, al, filt = 0, 1, None
        if out == "cast":
            off = -jround(ot * ot * 420)
            al = q4(1 - clamp(ot / 0.25))
        if out == "exp" and ot > 0.08:
            filt = ("gray", 0.6)
        bounce = 1 if (not out and IMP <= e < IMP + 0.06) else 0
        if al > 0:
            def held():
                obj(p, "op.axe", lambda: p.sprite_ink(im, 0, 0, W, H, AX["X"], AX["Y"] + off + bounce, filt),
                    ("axe", off + bounce, filt, p.alpha, p.tx, p.ty))
                if not filt:
                    if am:
                        obj(p, "op.edge", lambda: [p.P(AX["X"] + x, AX["Y"] + off + bounce + y, 1, 1, K["am"]) for x, y in AX_EDGE],
                            ("edge", off + bounce, p.alpha, p.tx, p.ty))
                    if not out and e > 0.5:
                        k = int(math.floor((e % 1.4) / 0.05))
                        for n, lst in enumerate(AX_SIDES):
                            if k < len(lst):
                                x, y = lst[k]

                                def glint(x=x, y=y):
                                    p.P(AX["X"] + x - 1, AX["Y"] + y, 3, 1, K["wh"])
                                    p.P(AX["X"] + x, AX["Y"] + y - 1, 1, 3, K["wh"])
                                obj(p, f"op.glint{n}", glint, ("glint", x, y, p.alpha, p.tx, p.ty))
            p.glow(al, held)
    if out == "cast":
        if ot < 0.08:
            obj(p, "op.cflash", lambda: p.disc(CX, CY, 36, "rgba(255,46,151,.35)"), ("cflash", p.alpha), PIECES_DISC)
        # the circle flares: a white and cyan shock ring rolls out with the flying runes; the axe leaves a streak as it rips up
        def shock():
            r = RC[2] + jround(ot * 90)
            p.ring_px(RC[0], RC[1], r, K["wh"], 2)
            p.ring_px(RC[0], RC[1], max(4, r - 6), K["cy"], 1)
        obj(p, "op.shock", lambda: p.glow(q4(1 - ot / 0.4), shock), None, PIECES_RING)
        if ot < 0.25:
            ay = AX["Y"] - jround(ot * ot * 400)
            for i in range(5):
                obj(p, f"op.streak{i}", lambda i=i: p.glow(q4(0.8 * (1 - ot / 0.25)), lambda: p.line(AX["X"] + 15 + i * 6, ay + 50, AX["X"] + 15 + i * 6,
                                                                                                    ay + 64 + jround(ot * 160) + (i % 2) * 6, K["cy"] if i % 2 else K["wh"], 1)))
    # the word: slashed in diagonally, shakes, glints, splits on cast
    base = PAL["dim"] if out == "exp" else (PAL["rageAflash"] if int(math.floor(e * 4)) % 2 else PAL["rageA"]) if am else PAL["rage"]

    def fn(i, ch, x, y, lw):
        d = 0.24 + 0.03 * i
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
            d = 0.24 + 0.03 * i
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
# REVENGE: the cackling Viking skull on a round shield
# ------------------------------------------------------------------------------------------------------------------------
SK = dict(W=56, H=56, X=MX - 28, Y=2, CUT=39, JX0=19, JX1=37, MX0=23, MX1=33)       # jaw block columns and mouth columns
SK_EYES = [[20, 23], [22, 23], [23, 23], [24, 23], [21, 24], [24, 24], [25, 24], [23, 25], [26, 25], [31, 23], [32, 23], [33, 23], [34, 23],
           [35, 23], [31, 24], [33, 24], [34, 24], [32, 25]]
SHC = dict(x=MX, y=31, r=29)
PLANK = ["#3a2148", "#2c1838", "#43264f", "#2c1838", "#3a2148", "#2c1838", "#43264f", "#2c1838", "#3a2148", "#2c1838", "#43264f", "#2c1838", "#3a2148"]
CRACKS = [[[-26, -6], [-20, -3], [-17, -9], [-12, -8]], [[25, -11], [20, -6], [22, -1], [17, 3]], [[-23, 13], [-18, 10], [-15, 16]],
          [[22, 15], [17, 11], [14, 17], [10, 15]]]
MINI_SH = ["..XXX..", ".XOOOX.", "XOOWOOX", "XOWBWOX", "XOOWOOX", ".XOOOX.", "..XXX.."]


def shield_half(p, half, cx, cy, r, s, rim, dim):
    """One half of the round shield (the mockup's shield() paints the left half, then the right): planks, a pink and cyan painted
    split, an iron rim with a highlight and rivets."""
    hx = cx + half * s
    for y in range(-r, r + 1):
        w = int(math.floor(math.sqrt(r * r - y * y)))
        for x in (range(-w, 1) if half < 0 else range(1, w + 1)):
            d = math.hypot(x, y)
            if d > r - 1.2:
                c = K["ink"]
            elif d > r - 3.2:
                c = "#4a3e72" if dim else rim
            elif d > r - 4.2:
                c = "#2a2040" if dim else "#4a4e60"
            else:
                c = "#241a36" if dim else PLANK[int(math.floor((x + r) / 4)) % len(PLANK)]
                if not dim and int(math.floor((x + r) / 4)) != int(math.floor((x + r + 1) / 4)):
                    c = "#1a0e24"
                a = math.atan2(y, x)
                if not dim and r - 9 < d < r - 6 and math.sin(a * 2) > 0.3:
                    c = "#7a1f52" if math.cos(a) > 0 else "#1f5a6a"
            p.P(hx + x, cy + y, 1, 1, c)
    if not dim:
        for i in range(10):
            a = (200 + i * 6) * math.pi / 180
            if (half < 0) == (math.cos(a) <= 0):
                p.P(hx + jround(math.cos(a) * (r - 2)), cy + jround(math.sin(a) * (r - 2)), 1, 1, "#e8f0ff")
    for i in range(12):
        a = i * math.pi / 6 + 0.26
        if (math.cos(a) < 0) != (half < 0):
            continue
        p.P(hx + jround(math.cos(a) * (r - 2)), cy + jround(math.sin(a) * (r - 2)), 1, 1, "#6c5a9a" if dim else "#f3fbff")


def shield(p, cx, cy, r, split, rim, crack_a, crack_c, dim):
    for half, key in ((-1, "rv.shL"), (1, "rv.shR")):
        obj(p, key, lambda half=half: shield_half(p, half, cx, cy, r, split, rim, dim), (key, cx, cy, split, rim, dim, p.alpha, p.tx, p.ty), PIECES_DISC)
    if crack_a > 0 and not dim:
        def cracks():
            for c in CRACKS:
                for i in range(len(c) - 1):
                    p.line(cx + c[i][0], cy + c[i][1], cx + c[i + 1][0], cy + c[i + 1][1], crack_c, 1)
        obj(p, "rv.crack", lambda: p.glow(crack_a, cracks), ("crack", cx, cy, crack_a, crack_c, p.alpha, p.tx, p.ty))


def skull_v2(p, d, t, eye, filt, sa, clip):
    """skullV2 inside glow(sa): the outline once for the whole shape (jaw at its dropped place), the mouth behind the jaw, the cranium,
    the braids, the jaw and beard, then the eyes in the beat's colour."""
    im = art("skull_px")
    x, y = SK["X"], SK["Y"] - t
    W, H, CUT, JX0, JX1, MX0, MX1 = SK["W"], SK["H"], SK["CUT"], SK["JX0"], SK["JX1"], SK["MX0"], SK["MX1"]
    old, old_clip = p.alpha, p.clip
    p.mul(sa)
    if clip:
        p.clip = (0, 0, GW, SHC["y"] + SHC["r"] - 2)

    def body():
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            p.sprite(im, 0, 0, W, CUT, x + ox, y + oy, "ink")
            p.sprite(im, 0, CUT, JX0, H - CUT, x + ox, y + CUT + oy, "ink")
            p.sprite(im, JX1, CUT, W - JX1, H - CUT, x + JX1 + ox, y + CUT + oy, "ink")
            p.sprite(im, JX0, CUT, JX1 - JX0, H - CUT, x + JX0 + ox, y + CUT + d + oy, "ink")
        p.filt = filt
        if d > 0:
            p.P(x + MX0, y + CUT - 1, MX1 - MX0, d + 2, "#12030a")
            if d >= 3:
                p.P(x + MX0 + 3, y + CUT + d - 1, MX1 - MX0 - 6, 1, K["pk"])
        p.sprite(im, 0, 0, W, CUT, x, y, filt)
        p.sprite(im, 0, CUT, JX0, H - CUT, x, y + CUT, filt)
        p.sprite(im, JX1, CUT, W - JX1, H - CUT, x + JX1, y + CUT, filt)
        if d > 0:
            p.P(x + MX0, y + CUT, MX1 - MX0, d, "#12030a")
        p.sprite(im, JX0, CUT, JX1 - JX0, H - CUT, x + JX0, y + CUT + d, filt)
        p.filt = None
    obj(p, "rv.sk", body, ("sk", d, t, filt, p.alpha, bool(clip), p.tx, p.ty), PIECES_DISC)

    def eyes():
        for ex, ey in SK_EYES:
            p.P(x + ex, y + ey, 1, 1, eye)
    if eye:
        obj(p, "rv.eyes", eyes, ("eyes", t, eye, bool(clip), p.alpha, p.tx, p.ty))
    p.alpha, p.clip = old, old_clip


def mini_shield(p, key, x, y, c, dim):
    def paint():
        for j, r in enumerate(MINI_SH):
            for i in range(7):
                if r[i] != ".":
                    p.P(x + i - 1, y + j - 1, 3, 3, K["ink"])
        for j, r in enumerate(MINI_SH):
            for i in range(7):
                ch = r[i]
                if ch == ".":
                    continue
                p.P(x + i, y + j, 1, 1, ("#4a3e72" if dim else "#c6cede") if ch == "X" else ("#4a3e72" if dim else K["wh"]) if ch == "B"
                    else ("#2a2040" if dim else "#8a93a8") if ch == "W" else c)
    obj(p, key, paint, (key, x, y, c, dim, p.alpha, p.tx, p.ty))


def draw_rev(p, st):
    e, out, ot = st["e"], st["out"], st["ot"]
    win = 5
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    CX = MX
    # cackle beats: three on the entrance, then a burst of four every 1.8 s
    beats = [0.3, 0.47, 0.64]
    for k in range(14):
        for m in range(4):
            beats.append(1.0 + 1.8 * k + 0.17 * m)
    bi = -1
    for i, b in enumerate(beats):
        if b <= e:
            bi = i
    age = e - beats[bi] if bi >= 0 else 9
    laugh = (not out) and age < 0.17
    d = t = 0
    if laugh:
        d = 4 if age < 0.05 else 2 if age < 0.11 else 0
        t = 2 if d == 4 else 1 if d == 2 else 0
    elif out == "cast":
        d = 5 if ot < 0.18 else 2 if ot < 0.26 else 0
        t = 3 if d == 5 else 1 if d == 2 else 0
    elif out == "exp":
        d = 1 if ot < 0.1 else 0
    dark = out == "exp" and ot > 0.1
    odd_beat = bi >= 0 and bi % 2 == 1
    eye = K["ink"] if dark else K["wh"] if (out == "cast" and ot < 0.1) else K["am"] if am else (K["pk"] if odd_beat else K["cy"])
    # entrance: the shield slams in from the left in three steps and rings, then the skull rises from behind it
    shx = 0
    if not out and e < 0.12:
        k = int(math.floor(e / 0.03))
        shx = [-44, -24, -9, -3][k] if k < 4 else 0
    sky = 0
    if not out and e < 0.12:
        sky = 99
    elif not out and e < 0.24:
        sky = jround((1 - ease_out(clamp((e - 0.12) / 0.12))) * 18)
    split = jround((ot - 0.08) * 90) if (out == "cast" and ot > 0.08) else 0
    sh_a = q4(1 - clamp((ot - 0.1) / 0.35)) if out == "cast" else 1
    rim = K["am"] if am else ("#f3fbff" if (laugh and age < 0.06) else "#8a93a8")
    crack_a = (1 if laugh else 0.5 + 0.25 * math.sin(e * TUNE["rv_crack"])) if e > 0.24 else 0
    p.glow(sh_a, lambda: shield(p, SHC["x"] + shx, SHC["y"], SHC["r"], split, rim, q4(crack_a), K["am"] if am else K["pk"], dark))
    if not out and 0.09 <= e < 0.2:
        k = e - 0.09
        ra = q4(1 - k / 0.11)
        obj(p, "rv.snap", lambda: p.glow(ra, lambda: p.ring_px(SHC["x"], SHC["y"], SHC["r"] + 2 + jround(k * 60), K["wh"], 1)), None, PIECES_RING)
        for i in range(10):
            a = math.pi * (0.7 + i * 0.06)
            r = SHC["r"] + k * 90
            obj(p, f"rv.spk{i}", lambda i=i, a=a, r=r: p.glow(ra, lambda: p.P(SHC["x"] + math.cos(a) * r, SHC["y"] + math.sin(a) * r, 2, 2, K["am"] if i % 2 else K["wh"])))
    # laugh lines and HA bits
    MY = SK["Y"] + SK["CUT"]
    if d >= 2 and not dark:
        for n, sd in enumerate((-1, 1)):
            c = K["cy"] if bi % 2 else K["pk"]

            def lines(sd=sd, c=c):
                p.line(CX + sd * 28, MY - 14, CX + sd * 34, MY - 18, c, 1)
                p.line(CX + sd * 30, MY - 6, CX + sd * 37, MY - 6, c, 1)
                p.line(CX + sd * 28, MY + 2, CX + sd * 34, MY + 6, c, 1)
            obj(p, f"rv.laugh{n}", lines)
    if not out:
        rank = 0
        for i, tb in enumerate(beats):
            a = e - tb
            if a < 0 or a >= 0.4:
                continue
            sd = 1 if i % 2 else -1
            cyan = ((i == 0) if i < 3 else (i - 3) % 4 == 0) if TUNE["rv_ha_beat"] else i % 3 == 0       # RETUNE: i % 3 == 0 in the mockup
            c = K["cy"] if cyan else K["pk"]
            obj(p, f"rv.ha{rank}", lambda a=a, sd=sd, c=c: p.glow(q4(1 - a / 0.4), lambda: tiny(p, "HA", jround(CX + sd * (26 + a * 60) - 5), jround(MY - 4 - a * 45), c)))
            rank += 1
    if out == "cast":
        if ot < 0.08:
            obj(p, "rv.cdisc", lambda: p.disc(CX, SHC["y"], 36, "rgba(255,240,250,.4)"), ("cdisc", p.alpha), PIECES_DISC)

        def rings():
            r = jround(ot / 0.4 * 64 / 2) * 2
            p.ring_px(CX, SHC["y"], r, K["pk"], 3)
            p.ring_px(CX, SHC["y"], r - 4, K["cy"], 1)
        obj(p, "rv.cring", lambda: p.glow(q4(1 - ot / 0.4), rings), None, PIECES_RING)
        for i in range(8):
            a = i * math.pi / 4
            r = 18 + jround(ot * 140)
            obj(p, f"rv.cha{i}", lambda i=i, a=a, r=r: p.glow(q4(1 - ot / 0.45), lambda: tiny(p, "HA", jround(CX + math.cos(a) * r - 5), jround(SHC["y"] + math.sin(a) * r * 0.8 - 3), K["cy"] if i % 2 else K["pk"])))
    sa = 1
    if out == "cast":
        sa = q4(1 - clamp((ot - 0.2) / 0.25))
    if sky < 99 and sa > 0:
        skull_v2(p, d, t - sky, eye, ("gray", 0.55) if dark else None, sa, sky > 0)
    if not out and 0.12 <= e < 0.16:
        obj(p, "rv.sdisc", lambda: p.disc(CX, SHC["y"], jround(30 * (1 - (e - 0.12) / 0.04)), "rgba(255,46,151,.35)"), None, PIECES_DISC)
    # title: bounces in from the mouth, then hops in time with each cackle
    base = PAL["dim"] if out == "exp" else PAL["vioA"] if am else PAL["vio"]
    COLS = {5: [0, 1, 2, 3, 4], 3: [0, 2, 4], 1: [2]}

    def fn(i, ch, x, y, lw):
        dl = 0.42 + 0.05 * i
        wd, px, py, al = 5, x, y, 1
        if not out:
            if e < dl:
                return None
            pr = clamp((e - dl) / 0.32)
            if pr < 1:
                sx = CX - 5
                px = jround(sx + (x - sx) * ease_out(pr))
                py = jround(MY + (y - MY) * pr - abs(math.sin(pr * math.pi * 2.5)) * (1 - pr) * 16)
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
    # little round shields flank the word (its own mark), hopping with each cackle
    if e >= 0.6 and (not out or out == "exp"):
        hop = 1 if (laugh and age < 0.08) else 0
        fc = "#4a3e72" if dark else K["am"] if am else (K["pk"] if bi % 2 else K["cy"])
        mini_shield(p, "rv.msL", x0 - 12, WY + 3 - hop, fc, dark)
        mini_shield(p, "rv.msR", x0 + w + 5, WY + 3 - (hop if (bi + 1) % 2 else 0), fc, dark)
    if e >= 0.6:
        drain(p, win, clamp(1 - ot / 0.1) if out == "cast" else clamp((e - 0.6) / 0.15), out == "exp" or st["am"], out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# VICTORY RUSH: crossed bearded axes on the red sunburst
# ------------------------------------------------------------------------------------------------------------------------
VR = dict(S=60, X=MX - 30, Y=0, CX=MX, CY=34)
FLAME_HOT = ["#fff6c8", "#ffe066", "#ffb02e", "#ff7a1f", "#f0381a", "#a8141a"]
FLAME_AM = ["#ffffff", "#fff0c8", "#ffd27a", "#ffb648", "#e08a2a", "#8a5010"]
_FLAMES = {}


def vhash(a, b):
    h = math.sin(a * 12.9898 + b * 78.233) * 43758.5453
    return h - math.floor(h)


def flame_data():
    if not _FLAMES:
        fl = flame_pixels()
        top = {}
        for s in ("L", "R"):
            for x, y, *_ in fl[s]:
                top[s + str(x)] = min(top.get(s + str(x), 99), y)
        _FLAMES.update(px=fl, top=top)
    return _FLAMES


def vr_flames(p, key, s, dx, dy, e, lvl, am, die):
    """vrFlames: lvl 0..1 = how much of the flame has lit (from the bottom); die 0..1 = burnt out from the top. One object per axe."""
    fd = flame_data()
    pts = fd["px"][s]
    ymin, ymax = min(q[1] for q in pts), max(q[1] for q in pts)
    cut = ymax - (ymax - ymin + 1) * lvl
    cut_d = ymin + (ymax - ymin + 1) * die
    pal = FLAME_AM if am else FLAME_HOT
    rt = TUNE["flame_amber" if am else "flame_hot"]
    n_tip = int(math.floor(e * rt["tip"]))
    n_lick = int(math.floor(e * rt["lick"]))
    if rt["mod"]:
        n_tip, n_lick = n_tip % rt["mod"][0], n_lick % rt["mod"][1]
    vis = []
    for x, y, r, g, b in pts:
        if y < cut or y < cut_d:
            continue
        if y == fd["top"][s + str(x)] and vhash(x, n_tip) < 0.35:
            continue
        lum = (r * 0.3 + g * 0.59 + b * 0.11) / 255
        base = 1 if lum > 0.8 else 2 if lum > 0.62 else 3 if lum > 0.45 else 4
        w = math.sin(e * rt["wave"] + y * 0.9 + x * 1.7)
        vis.append((x, y, pal[max(0, min(5, base + (-1 if w > 0.55 else 1 if w < -0.6 else 0)))]))
    if not die:
        for k, y0 in fd["top"].items():
            if k[0] != s:
                continue
            x = int(k[1:])
            if y0 < cut:
                continue
            h = vhash(x, n_lick)
            if h > 0.8:
                vis.append((x, y0 - 1, pal[1]))
            if h > 0.93:
                vis.append((x, y0 - 2, pal[0]))

    def paint():
        for x, y, _ in vis:
            p.P(dx + x - 1, dy + y - 1, 3, 3, K["ink"])
        for x, y, c in vis:
            p.P(dx + x, dy + y, 1, 1, c)
    obj(p, key, paint, (key, tuple(vis), dx, dy, p.alpha, p.tx, p.ty))


def wedge_cover(shine):
    """Coverage (60 x 60, 0..1) of the sweeping wedge: moveTo(30, 30), lineTo(30 + cos a * 44, 30 + sin a * 44) for a = shine - 0.28 + k * 0.07."""
    pts = [(30.0, 30.0)] + [(30 + math.cos(shine - 0.28 + k * 0.07) * 44, 30 + math.sin(shine - 0.28 + k * 0.07) * 44) for k in range(9)]
    ss = 16
    cov = np.zeros((60, 60), np.float32)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    x0, x1 = max(0, int(math.floor(min(xs)))), min(60, int(math.ceil(max(xs))))
    y0, y1 = max(0, int(math.floor(min(ys)))), min(60, int(math.ceil(max(ys))))
    if x1 <= x0 or y1 <= y0:
        return cov
    gx = x0 + (np.arange((x1 - x0) * ss) + 0.5) / ss
    gy = y0 + (np.arange((y1 - y0) * ss) + 0.5) / ss
    X, Y = np.meshgrid(gx, gy)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    inside = np.ones(X.shape, bool)
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        cross = (b[0] - a[0]) * (Y - a[1]) - (b[1] - a[1]) * (X - a[0])
        inside &= (cross >= 0) if area > 0 else (cross <= 0)
    cov[y0:y1, x0:x1] = inside.reshape(y1 - y0, ss, x1 - x0, ss).mean(axis=(1, 3))
    return cov


def vr_circle_canvas(iris, dim):
    """The offscreen 60 x 60 canvas of vrCircle without the wedge: the circle, dimmed, then the iris mask (destination-in)."""
    out = art("vr_circle").astype(np.float32)
    if dim:
        on = (out[..., 3:4] > 0)
        out[..., :3] = np.where(on, out[..., :3] * 0.25 + np.array([40, 30, 60], np.float32) * 0.75, out[..., :3])
    if iris is not None:
        mask = np.zeros((60, 60), np.float32)
        r = max(0, iris)
        for dy in range(-r, r + 1):
            w = int(math.floor(math.sqrt(r * r - dy * dy)))
            if 0 <= 31 + dy < 60:
                mask[31 + dy, max(0, 30 - w):min(60, 30 + w + 1)] = 1
        out[..., 3] *= mask
    return np.rint(out).astype(np.uint8)


def vr_shine_image(shine, am):
    """The wedge as a translucent overlay on the circle's opaque pixels (a source-atop fill = an over blend there)."""
    cov = wedge_cover(shine)
    r, g, b, aa = (255, 200, 120, .38) if am else (255, 170, 150, .32)
    img = np.zeros((60, 60, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = r, g, b
    on = art("vr_circle")[..., 3] > 0
    img[..., 3] = np.where(on, np.rint(cov * aa * 255), 0).astype(np.uint8)
    return img


def draw_vic(p, st):
    e, out, ot = st["e"], st["out"], st["ot"]
    win = 20
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - clamp((ot - 0.25) / 0.45))
    if fade <= 0:
        return
    p.alpha = fade
    CX, CY = VR["CX"], VR["CY"]
    heal = K["am"] if am else K["gr"]
    HIT = 0.16                                      # the axes clang together here
    # clangs: the axes kick apart a step and slam back every 2.4 s while the window is open
    clangs = [HIT] + [1.2 + 2.4 * k for k in range(9)]
    ci = -1
    for i, c in enumerate(clangs):
        if c <= e:
            ci = i
    cage = e - clangs[ci] if ci >= 0 else 9
    # shake on each clang (big on the first)
    if not out and cage < 0.12:
        k = int(math.floor(cage / 0.025))
        big = ci == 0
        sx_, sy_ = ([3, -3, 2, -2, 1], [-2, 2, -1, 1, 0]) if big else ([1, -1, 1, 0, 0], [0, 1, 0, 0, 0])
        p.tx = sx_[k] if k < 5 else 0
        p.ty = sy_[k] if k < 5 else 0
    # no backdrop: the mockup's green heal disc behind the sunburst and box behind the title were dropped (2026-11-20) so
    # Victory Rush sits on the world like Overpower and Revenge
    # the sunburst: irises open, then a light wedge sweeps round it
    iris = None if out else (jround(ease_out(e / 0.12) * 34) if e < 0.12 else None)
    c_a = q4(1 - clamp(ot / 0.35)) if out == "cast" else 1
    dim = out == "exp" and ot > 0.1

    def circle():
        obj(p, "vc.circle", lambda: p.sprite_ink(vr_circle_canvas(iris, dim), 0, 0, 60, 60, VR["X"], VR["Y"], ("gray", 0.7) if dim else None),
            ("circle", iris, dim, p.alpha, p.tx, p.ty))
        if not out and e > 0.5:
            shine = (e * TUNE["vc_shine"]) % TAU
            obj(p, "vc.shine", lambda: p.sprite(vr_shine_image(shine, am), 0, 0, 60, 60, VR["X"], VR["Y"]), ("shine", jround(shine * 1e9), am, p.alpha, p.tx, p.ty), PIECES_DISC)
    p.glow(c_a, circle)
    if not out and e < 0.12:
        obj(p, "vc.iris", lambda: p.glow(0.9, lambda: p.ring_px(VR["X"] + 30, VR["Y"] + 31, jround(ease_out(e / 0.12) * 34), K["wh"], 1)), None, PIECES_RING)
    # the axes: slide in from the sides in steps with ghost frames, clang into the X
    sx = 0
    if not out and e < HIT:
        k = int(math.floor(e / HIT * 6))
        sx = [-60, -44, -30, -18, -9, -3][k] if k < 6 else 0
    if not out and e >= HIT and cage < 0.1 and ci > 0:
        sx = -2 if cage < 0.04 else -1 if cage < 0.07 else 0
    lx, rx, ly, ry, al, filt = sx, -sx, 0, 0, 1, None
    if out == "cast":
        k = ot * ot * 500
        lx, rx = -jround(k), jround(k)
        ly = ry = -jround(k * 0.75)
        al = q4(1 - clamp(ot / 0.3))
    if out == "exp":
        gy = min(3, int(math.floor(ot / 0.1)))
        ly = ry = gy
        if ot > 0.1:
            filt = ("gray", 0.6)
    lit = 1 if out == "exp" else clamp((e - HIT) / 0.22)
    die = clamp(ot / 0.3) if out == "exp" else 0
    imL, imR = art("vr_axeL"), art("vr_axeR")
    if not out and e < HIT and e > 0.03:
        for n, (lag, ga) in enumerate(((14, .2), (8, .35))):
            def ghost(lag=lag):
                p.sprite_ink(imL, 0, 0, 60, 60, VR["X"] + lx - lag, VR["Y"])
                p.sprite_ink(imR, 0, 0, 60, 60, VR["X"] + rx + lag, VR["Y"])
            obj(p, f"vc.ghost{n}", lambda ghost=ghost, ga=ga: p.glow(ga, ghost))
    if out == "cast" and ot < 0.3:
        for i in range(4):
            o = i * 5 - 8

            def streak(o=o, i=i):
                p.line(CX - 6 + o + lx * 0.5, CY - 14 + ly * 0.5, CX - 20 + o + lx, CY - 28 + ly, K["wh"] if i % 2 else heal, 1)
                p.line(CX + 6 - o + rx * 0.5, CY - 14 + ry * 0.5, CX + 20 - o + rx, CY - 28 + ry, K["wh"] if i % 2 else heal, 1)
            obj(p, f"vc.streak{i}", lambda streak=streak: p.glow(q4(0.6 * (1 - ot / 0.3)), streak))
    if al > 0:
        def axes():
            # right axe first: the left one lies over it where the hafts cross
            obj(p, "vc.axeR", lambda: p.sprite_ink(imR, 0, 0, 60, 60, VR["X"] + rx, VR["Y"] + ry, filt), ("axeR", rx, ry, filt, p.alpha, p.tx, p.ty))
            obj(p, "vc.axeL", lambda: p.sprite_ink(imL, 0, 0, 60, 60, VR["X"] + lx, VR["Y"] + ly, filt), ("axeL", lx, ly, filt, p.alpha, p.tx, p.ty))
            if lit > 0 and die < 1:
                vr_flames(p, "vc.flameR", "R", VR["X"] + rx, VR["Y"] + ry, e + ot, lit, am, die)
                vr_flames(p, "vc.flameL", "L", VR["X"] + lx, VR["Y"] + ly, e + ot + 0.37, lit, am, die)
        p.glow(al, axes)
    # smoke when the flames die
    if out == "exp" and ot < 0.6:
        for i in range(10):
            s = -1 if i < 5 else 1
            ph = clamp(ot / 0.6)
            x = CX + s * (20 + (i % 5) * 3) + jround(math.sin(ot * 8 + i) * 2)
            y = VR["Y"] + 14 - (i % 5) - ph * 22
            obj(p, f"vc.smoke{i}", lambda i=i, x=x, y=y, ph=ph: p.glow(q4(0.6 * (1 - ph)), lambda: p.P(x, y, 2, 2, "#6a6280" if i % 2 else "#8a83a0")))
    # the clang: white flash, sparks and a ring where the hafts meet
    if not out and ci >= 0 and cage < 0.4:
        big = ci == 0
        k = cage
        if k < 0.08:
            obj(p, "vc.cflash", lambda: p.disc(CX, CY, jround((14 if big else 7) * (1 - k / 0.08)), "rgba(255,250,235," + str(q4(1 - k / 0.08)) + ")"), None, PIECES_DISC)
        if big and k < 0.4:
            obj(p, "vc.cring", lambda: p.glow(q4(1 - k / 0.4), lambda: p.ring_px(CX, CY, jround(k / 0.4 * 56 / 2) * 2, K["pk"], 2)), None, PIECES_RING)
        for i in range(14 if big else 7):
            a = i * 2.4 + (ci if (big or not TUNE["vc_spark_ci"]) else 1)                      # RETUNE: + ci in the mockup
            v = (40 if big else 26) + (i * 7) % 18
            x = CX + math.cos(a) * v * k * 1.6
            y = CY + math.sin(a) * v * k * 1.6 + 90 * k * k
            if k < 0.35:
                c = K["wh"] if i % 3 == 0 else K["am"] if i % 3 == 1 else "#ffd060"
                obj(p, f"vc.spark{i}", lambda x=x, y=y, c=c: p.glow(q4(1 - k / 0.35), lambda: p.P(x, y, 2, 2, c)))
    # heal: plus signs drift up around the circle; a green pulse rolls out every 2.4 s
    if not out and e >= 0.3:
        for i in range(9):
            ph = (e * TUNE["vc_plus_drift"] + i * 0.111) % 1
            px = CX - 42 + (i * 19) % 84 + jround(math.sin(e * TUNE["vc_plus_wobble"] + i) * 2)
            if abs(px - CX) < 20:
                continue
            obj(p, f"vc.plus{i}", lambda i=i, ph=ph, px=px: p.glow(q4(1 - ph * ph), lambda: plus(p, px, 60 - ph * 50, "#d8ffe8" if i % 3 == 0 else heal)))
    if not out and e >= 1.2:
        k = (e - 1.2) % 2.4
        if k < 0.5:
            obj(p, "vc.pulse", lambda: p.glow(q4(0.8 * (1 - k / 0.5)), lambda: p.ring_px(CX, CY - 3, 30 + jround(k * 36), heal, 1)), None, PIECES_RING)
    if out == "cast":
        if ot < 0.1:
            obj(p, "vc.cdisc", lambda: p.disc(CX, CY - 2, 34, "rgba(216,255,232,.4)"), ("cdisc", p.alpha), PIECES_DISC)

        def rings():
            r = jround(ot / 0.45 * 70 / 2) * 2
            p.ring_px(CX, CY - 2, r, K["gr"], 3)
            p.ring_px(CX, CY - 2, max(2, r - 4), K["wh"], 1)
        obj(p, "vc.cring2", lambda: p.glow(q4(1 - ot / 0.45), rings), None, PIECES_RING)
        for i in range(12):
            a = i * math.pi / 6
            dd = jround(ot * 130)
            obj(p, f"vc.cplus{i}", lambda i=i, a=a, dd=dd: p.glow(q4(1 - ot / 0.5), lambda: plus(p, CX + math.cos(a) * (14 + dd), CY - 2 + math.sin(a) * (14 + dd) * 0.8, K["gr"] if i % 2 else "#d8ffe8")))
    # title: rises in (the approved v1 title), hops on each clang
    base = PAL["dim"] if out == "exp" else PAL["helA"] if am else PAL["hel"]
    W = layout("VICTORY RUSH")[1]

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
                elif ci > 0 and cage < 0.12:
                    kk = cage - i * 0.008
                    if kk >= 0:
                        n = int(math.floor(kk / 0.03))
                        py = y - [2, 1, 1, 0][n] if n < 4 else y
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
# (win, castAt, drawer, enter frames, held (start, frames), amber (start, frames), loops)
SPELLS = {
    "overpower": dict(tag="op", win=5.0, cast_at=3.0, draw=draw_over, enter=15, held=(15, 90), amber=(105, 45), loop=False),
    "revenge": dict(tag="rv", win=5.0, cast_at=3.0, draw=draw_rev, enter=33, held=(33, 54), amber=(33, 54), loop=True),
    "victoryrush": dict(tag="vc", win=20.0, cast_at=8.0, draw=draw_vic, enter=27, held=(27, 72), amber=(27, 72), loop=True),
}
ORDER = ("overpower", "revenge", "victoryrush")
CAST_FRAMES, EXP_FRAMES = 19, 22        # the exits: 0.6 s and 0.7 s at 30 Hz, both ends included


def live_state(sp, f, am):
    e = f / DT + EPS
    return {"e": e, "out": None, "ot": 0.0, "rem": sp["win"] - e, "am": am}


def leave_state(sp, kind, j):
    ot = j / DT + EPS
    at = sp["cast_at"] if kind == "cast" else sp["win"]
    return {"e": at + ot, "out": kind, "ot": ot, "rem": sp["win"] - sp["cast_at"] if kind == "cast" else 0.0, "am": False}


def states(sp):
    h0, hn = sp["held"]
    a0, an = sp["amber"]
    return {
        "enter": [live_state(sp, f, False) for f in range(sp["enter"])],
        "held": [live_state(sp, f, False) for f in range(h0, h0 + hn)],
        "amber": [live_state(sp, f, True) for f in range(a0, a0 + an)],
        "cast": [leave_state(sp, "cast", j) for j in range(CAST_FRAMES)],
        "exp": [leave_state(sp, "exp", j) for j in range(EXP_FRAMES)],
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


def draw_frame(p, sp, st):
    p.reset()
    sp["draw"](p, st)
    return list(p.items)


def check_loops(p, sp, name, built):
    """A loop is seamless when frame f + loop draws the same list as frame f (every periodic term repeats exactly)."""
    for seq in ("held", "amber"):
        start, n = sp[seq]
        for k in range(n):
            nxt = draw_frame(p, sp, live_state(sp, start + k + n, seq == "amber"))
            assert nxt == built[seq][k], f"{name} {seq} does not loop: frame {start + k} differs from frame {start + k + n}"


def bake(check=True):
    p = Painter()
    data = {}
    for name in ORDER:
        sp = SPELLS[name]
        seqs = states(sp)
        built = {s: [draw_frame(p, sp, st) for st in seqs[s]] for s in SEQS}
        if sp["loop"] and check:
            check_loops(p, sp, name, built)
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
    print(f"{len(p.sprites)} sprites, {total} px, {len(atlases)} atlas(es): " + ", ".join(f"{w}x{h}" for w, h, _ in atlases))
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
