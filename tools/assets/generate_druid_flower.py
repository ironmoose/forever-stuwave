#!/usr/bin/env python3
"""Bake the Druid CASTER form's HoT flower: a 46 x 46 sprite px pixel art flower drawn over the Thorns wreath. The rose in the
middle is Rejuvenation (12 s, four heals), the seven petals round it are Regrowth (21 s, seven heals), the base (leaves and stem)
is always drawn.

The art is made in ComfyUI, pixelised and cut into layers that share one 46 x 46 canvas, so they stack exactly. The layers are
committed beside this script in druid_flower_art/ (full.png is the reference, source_generated_1024.png the raw generation, kept
as provenance only):

    base.png  rose.png  petal1.png .. petal7.png     (petal1 first: lower left, over the top, to lower right)

Everything is baked at SCALE x SCALE texels per sprite px (crisp, no smoothing). The module (GunsightDruidFlower.lua) cannot
desaturate, brighten or rotate crisp art with a vertex colour alone, so each look that needs a colour change is its own sprite
here, and the module only picks one and sets its alpha and vertex colour. Files:

    druid_flower_art.tga   512 x 512  the atlas, one sprite each, tight crops (rects in the generated manifest):
        base, rose, petal1..7              the art as drawn
        base_g, rose_g, petal_g1..7        the same desaturated (a plain luminance grey); the module dims them with the vertex colour
                                           (about half for a HoT that is not up, 0.35 for a petal that has healed and wilted)
        rose_hot                           the rose tinted toward hot pink #ff3ea5 and brightened; the module fades it over the rose
                                           by the time left
        rose_m, petal_m1..7                white silhouettes of the same px; the module tints them (white for the cast flash and
                                           the heal pulse, amber #ffb020 for the last seconds) and sets their alpha over the art
        fall<i>_<s>                        the wilted petal (the grey one) i turned s of SPIN steps clockwise about its own centre, each
                                           on a square canvas wide enough to turn on; the copy that falls on each heal is one of
                                           these, moved and faded by the module and swapped for the next step as it turns (baked
                                           turns, so every sprite px stays crisp and no texture rotation is needed)
    druid_flower_glow.tga   64 x 64   a white radial falloff in alpha (code, no source art): the soft glows behind the rose and
                                           the flower, tinted and added by the module
    DruidFlowerArt.lua     the manifest FS.DruidFlowerArt (never hand edit it, regenerate)

    python3 tools/assets/generate_druid_flower.py     (FS_ASSET_OUTPUT_DIR overrides the .tga directory, FS_ART_LUA_OUTPUT the
                                                       manifest, FS_ASSETS_DIR or FS_DRUID_FLOWER_ART_DIR the layer PNGs,
                                                       FS_FLOWER_PREVIEW a directory of one px per sprite px preview PNGs)
Needs numpy and Pillow. Deterministic: the same layers write the same bytes.
"""

from __future__ import annotations

import math
import os
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SCALE = 2
W, H = 150, 86                         # the module canvas, sprite px
CX, CY = 75, 36                        # the Thorns wreath's centre
SIZE = 46                              # the flower's canvas, sprite px
FX, FY = CX - SIZE // 2, CY - SIZE // 2
ATLAS_W, ATLAS_H = 512, 512            # texels
GLOW_N = 64                            # texels square
PETALS = 7
SPIN = 16                              # baked turns of a falling petal over one full turn
TAU = math.tau
HOT = (255, 62, 165)                   # #ff3ea5
_HERE = Path(__file__).resolve().parent
ART_DIR = Path(os.environ.get("FS_DRUID_FLOWER_ART_DIR") or Path(os.environ.get("FS_ASSETS_DIR") or _HERE) / "druid_flower_art")


# ---------------------------------------------------------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------------------------------------------------------

def load(name: str) -> np.ndarray:
    """One layer as a SIZE x SIZE x 4 uint8 array (straight alpha); a pixel with alpha 0 has colour 0."""
    im = Image.open(ART_DIR / f"{name}.png").convert("RGBA")
    if im.size != (SIZE, SIZE):
        raise ValueError(f"{name}.png is {im.size}, every layer must be {SIZE} x {SIZE} so they stack")
    a = np.asarray(im).copy()
    a[a[..., 3] == 0] = 0
    return a


def luminance(a: np.ndarray) -> np.ndarray:
    return (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) / 255.0


def grey(a: np.ndarray) -> np.ndarray:
    """Desaturated: each px becomes its luminance."""
    out = a.copy()
    lum = np.rint(luminance(a) * 255).astype(np.uint8)
    for c in range(3):
        out[..., c] = lum
    out[a[..., 3] == 0] = 0
    return out


def hot(a: np.ndarray) -> np.ndarray:
    """Tinted toward hot pink #ff3ea5 and brightened: the px's luminance picks a point on a ramp from a dark rose through the pink
    to a near white highlight, and the result is mostly that ramp (the art's own shading stays), a little of the original colour."""
    out = a.copy()
    lum = np.clip(luminance(a) * 1.3 + 0.12, 0.0, 1.0)
    base = np.array(HOT, dtype=np.float64)
    dark = base * 0.35
    low = (lum < 0.62)[..., None]
    t_low = (lum / 0.62)[..., None]
    t_high = np.clip((lum - 0.62) / 0.38, 0.0, 1.0)[..., None]
    white = np.array([255.0, 214.0, 240.0])
    ramp = np.where(low, dark + (base - dark) * t_low, base + (white - base) * t_high)
    mix = ramp * 0.88 + a[..., :3].astype(np.float64) * 0.12
    out[..., :3] = np.clip(np.rint(mix), 0, 255).astype(np.uint8)
    out[a[..., 3] == 0] = 0
    return out


def mask(a: np.ndarray) -> np.ndarray:
    """A white silhouette of the same px."""
    out = np.zeros_like(a)
    solid = a[..., 3] > 0
    out[solid] = (255, 255, 255, 255)
    return out


def bbox(a: np.ndarray):
    ys, xs = np.nonzero(a[..., 3] > 0)
    if not len(xs):
        raise ValueError("an empty layer")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def crop(a: np.ndarray):
    x0, y0, x1, y1 = bbox(a)
    return a[y0:y1, x0:x1].copy(), x0, y0


def fall_canvas(petal_grey: np.ndarray):
    """The grey petal on a square wide enough to turn about its centre without clipping (its bbox diagonal plus a px of room)."""
    sub, x0, y0 = crop(petal_grey)
    h, w = sub.shape[:2]
    n = int(math.ceil(math.hypot(w, h))) + 2
    n += n % 2                                                  # even, so the centre is a texel edge
    canvas = np.zeros((n, n, 4), dtype=np.uint8)
    ox, oy = (n - w) // 2, (n - h) // 2
    canvas[oy:oy + h, ox:ox + w] = sub
    return canvas, (x0 + w / 2.0, y0 + h / 2.0)                 # the petal's centre on the flower canvas


def turned(canvas: np.ndarray, step: int) -> np.ndarray:
    """`canvas` turned step / SPIN of a full turn clockwise about its centre, nearest px (sprite px stay whole px)."""
    n = canvas.shape[0]
    if step % SPIN == 0:
        return canvas.copy()
    th = TAU * step / SPIN
    c, s = math.cos(th), math.sin(th)
    out = np.zeros_like(canvas)
    half = n / 2.0
    for dy in range(n):
        for dx in range(n):
            px, py = dx + 0.5 - half, dy + 0.5 - half
            # the source px that lands on (dx, dy): rotate back by th (y runs down, so a clockwise turn is the plain rotation)
            sx, sy = c * px + s * py, -s * px + c * py
            ix, iy = int(math.floor(sx + half)), int(math.floor(sy + half))
            if 0 <= ix < n and 0 <= iy < n:
                out[dy, dx] = canvas[iy, ix]
    return out


# ---------------------------------------------------------------------------------------------------------------------------
# The atlas
# ---------------------------------------------------------------------------------------------------------------------------

def build() -> dict:
    base, rose = load("base"), load("rose")
    petals = [load(f"petal{i}") for i in range(1, PETALS + 1)]
    sprites: list[tuple[str, np.ndarray, int, int]] = []     # name, tight crop, anchor x, anchor y (sprite px)

    def add_box(name: str, a: np.ndarray) -> None:
        sub, x0, y0 = crop(a)
        sprites.append((name, sub, -x0, -y0))                   # the anchor is the flower canvas's origin

    add_box("base", base)
    add_box("base_g", grey(base))
    add_box("rose", rose)
    add_box("rose_g", grey(rose))
    add_box("rose_hot", hot(rose))
    add_box("rose_m", mask(rose))
    for i, p in enumerate(petals, 1):
        add_box(f"petal{i}", p)
    for i, p in enumerate(petals, 1):
        add_box(f"petal_g{i}", grey(p))
    for i, p in enumerate(petals, 1):
        add_box(f"petal_m{i}", mask(p))
    centres = []
    for i, p in enumerate(petals, 1):
        canvas, centre = fall_canvas(grey(p))
        centres.append(centre)
        for step in range(SPIN):
            sprites.append((f"fall{i}_{step}", turned(canvas, step), canvas.shape[1] // 2, canvas.shape[0] // 2))   # anchored at its centre

    # a shelf packer: sprites in this order, a one sprite px gap, rows left to right
    aw, ah = ATLAS_W // SCALE, ATLAS_H // SCALE
    rects, x, y, row_h = [], 0, 0, 0
    for name, sub, ax, ay in sprites:
        h, w = sub.shape[:2]
        if x + w > aw:
            x, y, row_h = 0, y + row_h + 1, 0
        if y + h > ah:
            raise ValueError(f"the atlas is full at {name}")
        rects.append((name, x, y, w, h, ax, ay))
        x += w + 1
        row_h = max(row_h, h)

    tex = np.zeros((ATLAS_H, ATLAS_W, 4), dtype=np.uint8)
    for (name, sub, _, _), (_, px, py, w, h, _, _) in zip(sprites, rects):
        block = np.repeat(np.repeat(sub, SCALE, axis=0), SCALE, axis=1)
        tex[py * SCALE:(py + h) * SCALE, px * SCALE:(px + w) * SCALE] = block

    # the glow: a white falloff in alpha, quadratic like the other soft glows, zero at the rim so a clamped edge never shows
    c = (GLOW_N - 1) / 2.0
    yy, xx = np.mgrid[0:GLOW_N, 0:GLOW_N]
    d = np.hypot(xx - c, yy - c) / (GLOW_N / 2.0)
    fall = np.clip(1.0 - d, 0.0, 1.0) ** 2
    glow = np.zeros((GLOW_N, GLOW_N, 4), dtype=np.uint8)
    glow[..., :3] = 255
    glow[..., 3] = np.rint(fall * 255).astype(np.uint8)
    glow[glow[..., 3] == 0] = 0

    rb = bbox(rose)
    return {
        "atlas": tex, "glow": glow, "rects": rects,
        "rose": ((rb[0] + rb[2]) / 2.0, (rb[1] + rb[3]) / 2.0),
        "petal": centres,
        "sprites": sprites,
    }


def write_tga(path: Path, a: np.ndarray) -> None:
    h, w = a.shape[:2]
    bgra = a[..., [2, 1, 0, 3]]
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    path.write_bytes(header + bgra.tobytes())
    print(f"wrote {path} ({w}x{h})")


def fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


def lua_manifest(out: dict) -> str:
    L = ["-- Generated by tools/assets/generate_druid_flower.py. Never hand edit; regenerate.", "local _, FS = ...", "FS.DruidFlowerArt = {"]
    L.append(f"    SCALE = {SCALE}, W = {W}, H = {H}, CX = {CX}, CY = {CY}, SIZE = {SIZE}, FX = {FX}, FY = {FY}, PETALS = {PETALS}, SPIN = {SPIN},")
    L.append(f"    ATLAS = \"druid_flower_art\", ATLAS_W = {ATLAS_W}, ATLAS_H = {ATLAS_H},")
    L.append(f"    GLOW = \"druid_flower_glow\", GLOW_W = {GLOW_N}, GLOW_H = {GLOW_N},")
    L.append("    -- the rose's centre and each petal's centre on the flower's own canvas (sprite px from its top left)")
    L.append(f"    ROSE = {{ {fmt(out['rose'][0])}, {fmt(out['rose'][1])} }},")
    L.append("    PETAL = {")
    for cx, cy in out["petal"]:
        L.append(f"        {{ {fmt(cx)}, {fmt(cy)} }},")
    L.append("    },")
    L.append("    -- sprite name = { texel x, texel y, w, h (sprite px), anchor x, anchor y }: the anchor is where the sprite's own point sits")
    L.append("    -- measured from the sprite's top left (the flower canvas's origin for the art layers, the centre for the fall sprites)")
    L.append("    SPR = {")
    for name, x, y, w, h, ax, ay in out["rects"]:
        L.append(f"        {name} = {{ {x * SCALE}, {y * SCALE}, {w}, {h}, {ax}, {ay} }},")
    L.append("    },")
    L.append("}")
    return "\n".join(L) + "\n"


def preview(out: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, sub, _, _ in out["sprites"]:
        Image.fromarray(sub, "RGBA").save(directory / f"{name}.png")
    Image.fromarray(out["glow"], "RGBA").save(directory / "glow.png")


def main() -> int:
    here = _HERE.parent.parent
    out_dir = Path(os.environ.get("FS_ASSET_OUTPUT_DIR") or here / "forever-stuwave" / "Media" / "Textures")
    out_dir.mkdir(parents=True, exist_ok=True)
    default_lua = (out_dir / "DruidFlowerArt.lua") if os.environ.get("FS_ASSET_OUTPUT_DIR") else (here / "forever-stuwave" / "Modules" / "CombatHud" / "DruidFlowerArt.lua")
    lua = Path(os.environ.get("FS_ART_LUA_OUTPUT") or default_lua)
    result = build()
    write_tga(out_dir / "druid_flower_art.tga", result["atlas"])
    write_tga(out_dir / "druid_flower_glow.tga", result["glow"])
    lua.write_text(lua_manifest(result), encoding="utf-8")
    print(f"wrote {lua}")
    pv = os.environ.get("FS_FLOWER_PREVIEW")
    if pv:
        preview(result, Path(pv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
