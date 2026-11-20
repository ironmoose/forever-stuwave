#!/usr/bin/env python3
"""Bake the Druid BEAR form look: the Demoralizing Roar tracker (a roaring bear head with an animated jaw inside a floating
storm aura, five sound arcs a side as the 30 s timer) and the small Thorns corner.

The design is the mockup "Druid Roar Bear Animated" (2026-11-17: candidate 1, the approved mouth frames, eyes that flare on the
roar, a storm aura with an ordered dither ragged edge and no box, lightning on the roar) and, for the corner, "Druid Gunsight
Module: One Layout Per Form" (2026-11-16). The mockup page draws a 150 x 86 canvas pixel by pixel at 30 Hz; the module
(GunsightDruidBear.lua) paints the same scene from the pieces baked here, so everything that is cheap stays live in Lua (the
arcs' state, the label, every eye pixel, the head's frame and bob, the shake) and everything that is a big pixel field is a
sprite of ONE atlas, one texel per sprite px (druid_bear_1.tga, white masks where the module tints):

    aura_<f>        the storm cloud, AURA_FRAMES frames of one loop: the page's two value noise layers, its ordered dither ragged
                    edge and its four tones, opaque to 0.9 like the page
    light<bx>_<f>   the flash that lights the bright parts of the cloud round a bolt (bx 35 = the cast, 121 = the idle flicker),
                    the page's mix toward #b8d0ff drawn as an overlay (colour #b8d0ff, alpha = the page's mix weight x 0.9)
    bolt<bx>        the forked lightning of that bolt, in its own two colours
    halo            the dithered ring behind the head, a white mask whose alpha is the page's falloff (tinted pink or amber)
    arc_<p>_<a|b|c> the ten sound arcs (p = 0 is the first to go) in three layers: a = the dither beside the arc, b = the arc, both
                    white masks tinted ROAR / amber (b also lighter on the wave), c = the dark inner edge (baked colour)
    ring_<i>        the three shock rings of the roar, RING_STEPS steps of the ellipse, a white mask (tinted white or ROAR)
    head_<frame>    the approved head frames (open, mid, rest, k11, k12, k13) and the rest frame greyed twice (dim_combat for
                    the roar down in combat, dim_ooc for out of combat: the page's grayscale / brightness filters)
    th_seg_<i>_<s>  the Thorns corner: segment i (0 at 12 o'clock, clockwise) of the ring with its thorn, live (green), amber, dry
    th_ghost        the dashed amber ring of the gone look

DEVIATIONS from the page. (1) The page's cloud drifts for ever (its noise layers move 2.4 and 2 px per second); a baked loop cannot,
so the two layers sway back and forth in one AURA_LOOP s loop (the same peak speeds, a smaller sweep); frame 0 is the page's t = 0,
which is also the still cloud of the roar down in combat. (2) The flash that lights the cloud and the bolt are overlays whose alpha
the module sets (the page mixes the colour); the overlay's weight is the page's, with the cloud's 0.9 opacity folded in. (3)
Repeated draws of one pixel (the arcs, the rings, the bolt) are blended in the bake at full strength; the module only scales the
whole sprite's alpha (the page scales each draw), so a flickering arc differs by the overlap of a few of its pixels. (4) The
shock ring is baked in RING_STEPS radii (one per 1 / 30 s tick of its 0.6 s) with the ring's own alpha at that step.

    python3 tools/assets/generate_druid_bear.py      (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                       FS_ART_LUA_OUTPUT the manifest path, FS_DRUID_BEAR_ART_DIR the head frames)
Needs numpy and Pillow. Deterministic: the same source writes the same bytes. The head frames in druid_bear_art/ are the approved
candidate 1 frames (64 px tall, 28 colours, the jaw built from the art's own pixels).
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("FS_ASSETS_DIR") or _HERE)
import generate_warrior_powerups as W  # noqa: E402  (the shared atlas packer and TGA writer)

GW, GH = 150, 86                 # the sprite canvas
CX, CY = 75, 36
HCY = CY - 2                     # the head's centre row on the page (cy = CY - 2)
ART_DIR = os.environ.get("FS_DRUID_BEAR_ART_DIR") or os.path.join(os.environ.get("FS_ASSETS_DIR") or _HERE, "druid_bear_art")
TAU = math.pi * 2
jround = W.jround

# the page's colours
OUT_A = 0.9                      # the cloud's pixel alpha
ROAR, ROARH, ROARD = "#ff6a2a", "#ffc890", "#8a2410"
AMBER = "#ffb648"
BOLT, BOLTC = "#e8f4ff", "#7ab0ff"
LIGHT = "#b8d0ff"
TONES = ("#0a0a1e", "#121638", "#1c2450", "#2c3874")
BAY = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)

AURA_FRAMES = 24                 # frames of the cloud's loop
AURA_LOOP = 8.0                  # seconds the loop takes (3 frames per second)
SWAY_A, SWAY_B = 1.5, 1.3        # input px each noise layer sways (the page's layers move 1.2 x 2 and 2 px per second)
BOLTS = (35, 121)                # the cast's bolt (CX - 40) and the idle flicker's (CX + 46)
RING_STEPS = 18                  # steps of a shock ring over its 0.6 s
HEADS = ("open", "mid", "rest", "k11", "k12", "k13")
DIM_COMBAT, DIM_OOC = (0.75, 0.55), (0.85, 0.40)     # grayscale(a) brightness(b) of the roar down in / out of combat

TH_CX, TH_CY, TH_R = 12, 12, 8   # the Thorns corner ring (sprite px)
TH_STATES = {"live": "#5fd35a", "amber": "#ffb648", "dry": "#3a2168"}
TH_WHITE = "#f3fbff"


def rgb(c):
    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))


# ------------------------------------------------------------------------------------------------------------------------
# JavaScript's hash and value noise, the page's, in numpy
# ------------------------------------------------------------------------------------------------------------------------
M32 = 0xFFFFFFFF


def h2a(x, y):
    """The page's h2 on integer arrays: imul hash to 0..1."""
    a = (x * 374761393) & M32
    b = (y * 668265263) & M32
    s = (a + b) & M32
    t = (s ^ (s >> 13)) & M32
    n = (t * 1274126177) & M32
    return ((n ^ (n >> 16)) & M32) / 4294967295.0


def h2(x, y):
    """h2 on two numbers (the page truncates with |0)."""
    return float(h2a(np.int64(int(x)), np.int64(int(y))))


def vn(xf, yi, s, seed):
    """The page's value noise: xf is a float array, yi an integer array, s the cell size."""
    xs = xf / s
    X = np.floor(xs).astype(np.int64)
    fx = xs - X
    ys = yi / s
    Y = np.floor(ys).astype(np.int64)
    fy = ys - Y
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = h2a(X + seed, Y), h2a(X + 1 + seed, Y)
    c, d = h2a(X + seed, Y + 1), h2a(X + 1 + seed, Y + 1)
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


# ------------------------------------------------------------------------------------------------------------------------
# A float RGBA canvas: premultiplied, source over, like the page's 2D context
# ------------------------------------------------------------------------------------------------------------------------
class Layer:
    def __init__(self, w=GW, h=GH):
        self.w, self.h = w, h
        self.buf = np.zeros((h, w, 4), np.float64)      # premultiplied rgb 0..255, alpha 0..1

    def px(self, x, y, c, a):
        x, y = jround(x), jround(y)
        if not (0 <= x < self.w and 0 <= y < self.h) or a <= 0:
            return
        a = min(1.0, a)
        r, g, b = c
        p = self.buf[y, x]
        p[:3] = np.array((r, g, b)) * a + p[:3] * (1 - a)
        p[3] = a + p[3] * (1 - a)

    def dither(self, x, y, c, a):
        if (jround(x) + jround(y)) & 1 == 0:
            self.px(x, y, c, a)

    def straight(self):
        """The layer as straight (r, g, b, a) uint8, rounded."""
        a = self.buf[..., 3:4]
        c = np.where(a > 0, self.buf[..., :3] / np.maximum(a, 1e-12), 0.0)
        out = np.zeros(self.buf.shape, np.uint8)
        out[..., :3] = np.clip(np.floor(c + 0.5), 0, 255)
        out[..., 3] = np.clip(np.floor(a[..., 0] * 255 + 0.5), 0, 255)
        out[out[..., 3] == 0, :3] = 0
        return out


def crop(rgba, box=None):
    """(sprite array, x0, y0) of the nonzero alpha's bounding box, or of `box` = (x0, y0, x1, y1)."""
    if box is None:
        ys, xs = np.where(rgba[..., 3] > 0)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    x0, y0, x1, y1 = box
    return rgba[y0:y1, x0:x1].copy(), x0, y0


# ------------------------------------------------------------------------------------------------------------------------
# The storm cloud and its flash
# ------------------------------------------------------------------------------------------------------------------------
YS, XS = np.mgrid[0:GH, 0:GW]
BAYM = np.array(BAY, np.float64).reshape(4, 4)[YS & 3, XS & 3] / 16.0
TONE_RGB = np.array([rgb(t) for t in TONES], np.uint8)


def aura_field(f):
    """The cloud of loop frame f: (drawn mask, tone index, n), the page's aura() with its noise inputs swayed."""
    ph = math.sin(TAU * f / AURA_FRAMES)
    n = vn(XS * 0.5 + SWAY_A * ph, YS, 7, 3) * 0.65 + vn(XS + SWAY_B * ph, YS, 4, 9) * 0.35
    d = ((XS - CX) / 58.0) ** 2 + ((YS - CY + 1) / 38.0) ** 2 + (n - 0.5) * 0.45
    edge = np.clip((1 - d) / 0.22, 0, 1)
    drawn = (d <= 1) & ((edge >= 1) | (BAYM < edge))
    tone = np.zeros((GH, GW), np.int64)
    tone[n > 0.48] = 1
    tone[n > 0.58] = 2
    tone[n > 0.70] = 3
    return drawn, tone, n


def bolt_pixels(bx):
    """The page's bolt through the cloud as draws (x, y, colour, alpha, dithered) in order."""
    out = []
    x, y = float(bx), 6.0
    while y < 54:
        nx = x + (h2(y, bx) - 0.5) * 5
        ny = y + 2 + h2(y, 7) * 3
        s = 0.0
        while s <= 1:
            X, Y = x + (nx - x) * s, y + (ny - y) * s
            out.append((X, Y, BOLT, 1.0, False))
            out.append((X + 1, Y, BOLTC, 0.6, False))
            out.append((X - 1, Y, BOLTC, 0.5, True))
            s += 0.2
        if h2(y, 3) > 0.78:
            bx_, by_ = nx, ny
            for k in range(6):
                bx_ += 1.4 if h2(k, y) > 0.5 else -1.4
                by_ += 1.6
                out.append((bx_, by_, BOLTC, 0.7, False))
        x, y = nx, ny
    return out


def bake_aura():
    """({name: (rgba, ox, oy)}) for the cloud frames, their light overlays and the two bolts. Every frame of a kind shares one
    box, so the module never resizes them."""
    fields = [aura_field(f) for f in range(AURA_FRAMES)]
    box = None
    for drawn, _, _ in fields:
        ys, xs = np.where(drawn)
        b = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    out = {}
    for f, (drawn, tone, _) in enumerate(fields):
        img = np.zeros((GH, GW, 4), np.uint8)
        img[..., :3] = TONE_RGB[tone]
        img[..., 3] = np.where(drawn, jround(OUT_A * 255), 0)
        img[~drawn, :3] = 0
        out[f"aura_{f}"] = crop(img, box)
    lbox = {}
    lights = {}
    for bx in BOLTS:
        dd = np.hypot(XS - bx, YS - 24)
        for f, (drawn, _, n) in enumerate(fields):
            m = drawn & (n > 0.45) & (dd < 55)
            wgt = (1 - dd / 55) * 0.85 * OUT_A
            img = np.zeros((GH, GW, 4), np.uint8)
            img[m, 0], img[m, 1], img[m, 2] = rgb(LIGHT)
            img[m, 3] = np.clip(np.floor(wgt[m] * 255 + 0.5), 0, 255)
            lights[(bx, f)] = img
            ys, xs = np.where(m)
            b = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            lbox[bx] = b if bx not in lbox else (min(lbox[bx][0], b[0]), min(lbox[bx][1], b[1]), max(lbox[bx][2], b[2]), max(lbox[bx][3], b[3]))
        for f in range(AURA_FRAMES):
            out[f"light{bx}_{f}"] = crop(lights[(bx, f)], lbox[bx])
        lay = Layer()
        for x, y, c, a, dith in bolt_pixels(bx):
            (lay.dither if dith else lay.px)(x, y, rgb(c), a)
        out[f"bolt{bx}"] = crop(lay.straight())
    return out


# ------------------------------------------------------------------------------------------------------------------------
# Halo, arcs, rings
# ------------------------------------------------------------------------------------------------------------------------
def bake_halo():
    """The dithered ring behind the head (r 18 to 40 round (CX, HCY)) as a white mask whose alpha is the page's falloff."""
    lay = Layer()
    r0, r1 = 18, 40
    for y in range(-r1, r1 + 1):
        for x in range(-r1, r1 + 1):
            d = math.hypot(x, y)
            if d < r0 or d > r1:
                continue
            lay.dither(CX + x, HCY + y, (255, 255, 255), 1 - (d - r0) / (r1 - r0))
    return crop(lay.straight())


def arc_geometry(p):
    j = 9 - p
    ring, side = j >> 1, 1 if (j & 1) else -1
    return ring, side, 35 + ring * 4.2


def bake_arc(p):
    """Layers a, b, c of piece p: the page's loop over t, each layer's repeated draws blended at alpha 1 x the page's weights."""
    ring, side, r = arc_geometry(p)
    la, lb, lc = Layer(), Layer(), Layer()
    t = -0.55
    while t <= 0.55:
        x, y = CX + side * math.cos(t) * r, HCY + 2 + math.sin(t) * r * 0.95
        e = 1 - abs(t) / 0.55
        la.dither(x + side, y, (255, 255, 255), 0.35 * e)
        lb.px(x, y, (255, 255, 255), 0.45 + 0.55 * e)
        lc.px(x - side, y, rgb(ROARD), 0.7 * e)
        t += 0.6 / r
    return [crop(layer.straight()) for layer in (la, lb, lc)]


def bake_ring(i):
    """Shock ring step i: the page's 180 samples of the ellipse at the step's radius, a white mask with the ring's alpha."""
    kk = (i + 0.5) / RING_STEPS
    r = 20 + kk * 70
    a = (1 - kk) * 0.8
    lay = Layer()
    for t in range(180):
        a2 = t / 180 * TAU
        lay.dither(CX + math.cos(a2) * r, HCY + 2 + math.sin(a2) * r * 0.75, (255, 255, 255), a)
    return crop(lay.straight())


# ------------------------------------------------------------------------------------------------------------------------
# The head frames
# ------------------------------------------------------------------------------------------------------------------------
def head_image(name):
    from PIL import Image
    return np.asarray(Image.open(os.path.join(ART_DIR, f"bear1_{name}.png")).convert("RGBA")).copy()


def grey(img, filt):
    """The page's CSS filter grayscale(g) brightness(b) on the head."""
    g, b = filt
    c = img[..., :3].astype(np.float64)
    lum = c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722
    out = (c * (1 - g) + lum[..., None] * g) * b
    res = img.copy()
    res[..., :3] = np.clip(np.floor(out + 0.5), 0, 255)
    return res


def bake_heads():
    out = {}
    for name in HEADS:
        out[f"head_{name}"] = (head_image(name), 0, 0)
    rest = head_image("rest")
    out["head_dim_combat"] = (grey(rest, DIM_COMBAT), 0, 0)
    out["head_dim_ooc"] = (grey(rest, DIM_OOC), 0, 0)
    return out


# ------------------------------------------------------------------------------------------------------------------------
# The Thorns corner
# ------------------------------------------------------------------------------------------------------------------------
def mixc(a, b, k):
    return tuple(jround(a[i] + (b[i] - a[i]) * k) for i in range(3))


def bake_thorns():
    out = {}
    for i in range(10):
        pts = []
        for a in range(0, 360, 3):
            if a // 36 != i:
                continue
            rad = (a - 90) * math.pi / 180
            pts.append((jround(TH_CX + math.cos(rad) * TH_R), jround(TH_CY + math.sin(rad) * TH_R), 0))
        rad = ((i + 0.5) * 36 - 90) * math.pi / 180
        for k in (1, 2):
            pts.append((jround(TH_CX + math.cos(rad) * (TH_R + k)), jround(TH_CY + math.sin(rad) * (TH_R + k)), k))
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        for state, hexc in TH_STATES.items():
            col = rgb(hexc)
            img = np.zeros((GH, GW, 4), np.uint8)
            for x, y, k in pts:
                c = col if state == "dry" or k < 2 else mixc(col, rgb(TH_WHITE), 0.4)
                img[y, x] = (*c, 255)
            out[f"th_seg_{i}_{state}"] = crop(img, box)
    img = np.zeros((GH, GW, 4), np.uint8)
    for a in range(0, 360, 4):
        if (a // 16) % 2:
            continue
        rad = (a - 90) * math.pi / 180
        img[jround(TH_CY + math.sin(rad) * TH_R), jround(TH_CX + math.cos(rad) * TH_R)] = (*rgb(AMBER), 255)
    out["th_ghost"] = crop(img)
    return out


# ------------------------------------------------------------------------------------------------------------------------
# Bake, pack, write
# ------------------------------------------------------------------------------------------------------------------------
def bake():
    """An ordered list of (name, rgba, ox, oy): `ox, oy` is the sprite's top left on the 150 x 86 canvas (the head's own origin
    for the head frames)."""
    sprites = []

    def add(items):
        for name, (img, ox, oy) in items:
            sprites.append((name, img, ox, oy))

    heads = bake_heads()
    add([(f"head_{n}", heads[f"head_{n}"]) for n in HEADS]
        + [("head_dim_combat", heads["head_dim_combat"]), ("head_dim_ooc", heads["head_dim_ooc"])])
    aura = bake_aura()
    add([(f"aura_{f}", aura[f"aura_{f}"]) for f in range(AURA_FRAMES)])
    for bx in BOLTS:
        add([(f"light{bx}_{f}", aura[f"light{bx}_{f}"]) for f in range(AURA_FRAMES)])
        add([(f"bolt{bx}", aura[f"bolt{bx}"])])
    add([("halo", bake_halo())])
    for p in range(10):
        add([(f"arc_{p}_{k}", layer) for k, layer in zip("abc", bake_arc(p))])
    add([(f"ring_{i}", bake_ring(i)) for i in range(RING_STEPS)])
    th = bake_thorns()
    for i in range(10):
        add([(f"th_seg_{i}_{s}", th[f"th_seg_{i}_{s}"]) for s in TH_STATES])
    add([("th_ghost", th["th_ghost"])])
    return sprites


def lua_manifest(sprites, atlas, where):
    w, h, _ = atlas
    L = [
        "-- Forever STUwave: the Druid Bear look's sprite manifest (the Demoralizing Roar tracker and the Thorns corner).",
        "-- GENERATED by tools/assets/generate_druid_bear.py; do not edit (gunsightdruidbear-harness.py checks it).",
        "-- sprites[name] = { tx, ty, w, h, ox, oy }: a texel rect of the atlas (one texel is one sprite px) and the sprite's top",
        "-- left on the 150 x 86 canvas (the head frames: on the head's own 64 x 64 box).",
        "",
        "local _, FS = ...",
        "",
        "FS.DruidBearArt = {",
        f'    FILE = "druid_bear_1", AW = {w}, AH = {h}, GW = {GW}, GH = {GH}, CX = {CX}, CY = {CY},',
        f"    AURA_FRAMES = {AURA_FRAMES}, AURA_LOOP = {AURA_LOOP}, RING_STEPS = {RING_STEPS},",
        f"    TH_CX = {TH_CX}, TH_CY = {TH_CY}, TH_R = {TH_R},",
        "    sprites = {",
    ]
    for sid, (name, img, ox, oy) in enumerate(sprites, 1):
        tx, ty = where[sid]
        L.append(f'        ["{name}"] = {{ {tx}, {ty}, {img.shape[1]}, {img.shape[0]}, {ox}, {oy} }},')
    L += ["    },", "}", ""]
    return "\n".join(L)


def main():
    root = os.path.join(_HERE, "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "DruidBearArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "DruidBearArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    sprites = bake()
    packed = [(img.shape[1], img.shape[0], img.tobytes()) for _, img, _, _ in sprites]
    atlases = W.pack(packed)
    assert len(atlases) == 1, f"the bear atlas must be one file, it needs {len(atlases)}"
    atlas = atlases[0]
    where = {sid: (tx, ty) for sid, tx, ty in atlas[2]}
    total = sum(w * h for w, h, _ in packed)
    print(f"{len(sprites)} sprites, {total} texels, atlas {atlas[0]}x{atlas[1]}")
    if "--stats" in sys.argv:
        return
    os.makedirs(here, exist_ok=True)
    W.write_tga(os.path.join(here, "druid_bear_1.tga"), atlas, packed)
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(sprites, atlas, where))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
