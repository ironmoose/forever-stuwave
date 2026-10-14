#!/usr/bin/env python3
"""Synthwave restyles of Blizzard's own icons: the pipeline behind the icon style mockup.

Turns a Blizzard icon into neon variants so the buff tab and micro menu do not need
hand-drawn art. Four styles are produced for every icon:

    A  wireframe   edge detect into thin neon lines on a near black violet ground, soft glow
    B  gradient    luminance mapped onto the STUwave ramp (violet, pink, accent), faint scanline
    C  hybrid      B dimmed underneath with A's neon edges on top
    D  runtime     no baked art: the real icon desaturated, vertex tinted and glowed the way the
                   game can do live (SetDesaturated, SetVertexColor, an ADD glow overlay)

A, B and C are baked per icon and size (each size is re-rendered, not downscaled, so line
width and edge threshold stay tuned for it). D is simulated here only so it can be compared;
in game it needs no art at all and works for any spell.

Sources are NOT part of the repository. Download them yourself into a directory that is
never committed (the mockup used debug/icon-sources-2026-10-14/). All are fetched by file id
from wago.tools (https://wago.tools/api/casc/<fileid>?download), ids from the community listfile:

    spells/<iconname>.jpg    https://wow.zamimg.com/images/wow/icons/large/<iconname>.jpg  (56 px)
    micro/<name>.blp         classic micro button art (32x64 BLP: the button frame with the glyph
                             inside), interface/buttons/ui-microbutton-<name>-up
    micro/pvp_<faction>.blp  interface/targetingframe/ui-pvp-alliance, -horde, -ffa (64x64)
    micro/uimicromenu2x.blp  interface/hud/uimicromenu2x, file id 4708813: the modern micro menu
                             atlas (uncompressed BLP2). Cells come from UiTextureAtlasMember
                             (wago.tools/db2/UiTextureAtlasMember/csv, atlas 2136).
    classicons/<class>.blp   interface/icons/classicon_<class> (64x64), ids 625999 to 626008 (626002 is the monk)
    spellfiles/<icon>.blp    the 64 px spell icon files, interface/icons/<name>, ids in SPELL_ICONS

Usage (read untrusted downloads with -I so nothing in their directory is imported):

    uv run python -I tools/assets/synthwave_icons.py --sources debug/icon-sources-2026-10-14 \\
        --html debug/synthwave-icons-2026-10-14.html

The preview page embeds the derived art as base64, so it defaults to debug/ (gitignored) and
must never be committed to the public repository.

Shipping: NOTHING derived from the game's art is shipped. The micro keys and the class tab spell tiles draw the
game's own textures and restyle them live in the client (Core/IconStyle.lua: SetDesaturated, an ADD copy, a MOD ramp,
an ADD lift; the ramps and the key covers are our own art, tools/assets/generate_icon_style.py). This tool still
renders styles A to D from the downloaded sources for the preview page, and writes:

    --gen-runtime   forever-stuwave/Core/IconStyleData.lua: per icon the texture (a file id or a path), the upright
                    texcoord window that fills the icon rectangle, the colour family and a boost (how much brighter than the plain
                    desaturated icon it must be drawn). Numbers only; the sources are read, nothing of them is copied.
    --bake-own      glyphart_character.tga and glyphart_legacy.tga: the Character fallback (the person glyph, used when
                    the class is unknown) and the Legacy key, baked from our OWN hand drawn shapes
                    (tools/assets/deck_glyph_sources.py) on a violet vignette through the same gradient map, with the
                    key's slanted shape baked into the alpha (a MaskTexture does not clip on this client). No game art.

tools/assets/test_tga_generators.py fails if a shipped texture has neither a generator nor is one of those two.

Needs Pillow and numpy only.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Palette (Theme.lua / the mockup CSS). Everything is float RGB in 0..1.
# ---------------------------------------------------------------------------


def hexrgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


BG = hexrgb("#0d0620")
PLATE = hexrgb("#140a24")
VIOLET = hexrgb("#a855f7")
DEEP = hexrgb("#4c1d95")
PINK = hexrgb("#ff2e97")
CYAN = hexrgb("#22e0ff")
AMBER = hexrgb("#ffb648")
GREEN = hexrgb("#7dff5a")
ICE = hexrgb("#7ab8ff")
LAVENDER = hexrgb("#e2d4ff")
WHITE = hexrgb("#f3fbff")

# A family is (weak edge, mid edge, hot edge). The gradient ramp for B runs
# BG, deep violet, weak, mid, hot, white. One house shape, per element accents.
FAMILIES = {
    "house_cyan": (VIOLET, PINK, CYAN),
    "house_violet": (DEEP, VIOLET, PINK),
    "house_pink": (VIOLET, CYAN, PINK),
    "fire": (VIOLET, PINK, AMBER),
    "earth": (VIOLET, GREEN, hexrgb("#d6ff7a")),
    "frost": (VIOLET, ICE, CYAN),
    "air": (VIOLET, CYAN, LAVENDER),
    "lightning": (VIOLET, CYAN, WHITE),
    "water": (VIOLET, ICE, CYAN),
}

# Per output size: (line width in output px, edge blur in SOURCE px, threshold low, high,
# glow sigma in output px, glow gain, scanline strength).
TUNING = {
    64: dict(line=1.7, esig=1.1, lo=0.20, hi=0.55, glow=3.2, gain=0.85, scan=0.20, dlift=0.5, dglow=0.12),
    32: dict(line=1.35, esig=1.2, lo=0.27, hi=0.62, glow=2.0, gain=0.80, scan=0.13, dlift=0.6, dglow=0.12),
    16: dict(line=1.05, esig=1.3, lo=0.32, hi=0.68, glow=0.9, gain=0.40, scan=0.0, dlift=0.7, dglow=0.10),
}
# Vertex colour style D multiplies the desaturated icon by, per family.
D_TINT = {
    "house_cyan": CYAN, "house_violet": VIOLET, "house_pink": PINK,
    "fire": hexrgb("#ff6a3c"), "earth": hexrgb("#a6ff4a"), "frost": hexrgb("#4ad2ff"),
    "air": hexrgb("#9a8cff"), "lightning": CYAN, "water": hexrgb("#3b8bff"),
}
DHEAD = 0.88  # style D keeps this much of full white so the ADD glow cannot clip it
SS = 8  # supersample factor for the work canvas


# ---------------------------------------------------------------------------
# numpy image helpers
# ---------------------------------------------------------------------------


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Separable gaussian over the first two axes, edge padded."""
    if sigma < 0.05:
        return a
    r = max(1, int(3 * sigma + 0.5))
    x = np.arange(-r, r + 1)
    k = np.exp(-x * x / (2.0 * sigma * sigma))
    k /= k.sum()
    out = a
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        acc = np.zeros_like(out, dtype=np.float64)
        for i, w in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + n)
            acc += w * p[tuple(sl)]
        out = acc
    return out


def smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114])


def resize(rgb: np.ndarray, size: int, resample=Image.LANCZOS) -> np.ndarray:
    im = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8))
    return np.asarray(im.resize((size, size), resample), dtype=np.float64) / 255.0


def to_png(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def ramp(t: np.ndarray, stops: list[np.ndarray]) -> np.ndarray:
    """Piecewise linear colour ramp; t in 0..1 (any shape) gives shape + (3,)."""
    n = len(stops) - 1
    x = np.clip(t, 0, 1) * n
    i = np.minimum(x.astype(int), n - 1)
    f = (x - i)[..., None]
    arr = np.stack(stops)
    return arr[i] * (1 - f) + arr[i + 1] * f


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def load_spell(path: Path) -> np.ndarray:
    """A zamimg 56 px icon with its baked 3 px frame trimmed off."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    im = im.crop((3, 3, w - 3, h - 3))
    return np.asarray(im, dtype=np.float64) / 255.0


def load_micro(path: Path) -> np.ndarray:
    """The glyph window of a classic 32x64 micro button, padded to a square."""
    im = Image.open(path).convert("RGBA")
    inner = im.crop((5, 29, 27, 58))  # inside the button frame
    a = np.asarray(inner, dtype=np.float64) / 255.0
    rgb = a[..., :3] * a[..., 3:4]
    h, w = rgb.shape[:2]
    side = max(h, w)
    out = np.zeros((side, side, 3)) + np.percentile(rgb.reshape(-1, 3), 10, axis=0)
    y0, x0 = (side - h) // 2, (side - w) // 2
    out[y0:y0 + h, x0:x0 + w] = rgb
    return out


def read_blp2_bgra(path: Path) -> Image.Image:
    """An uncompressed (colour encoding 3, BGRA) BLP2, which Pillow does not read: the modern
    micro menu atlas is one."""
    d = path.read_bytes()
    magic, _typ, enc, _ad, _ae, _mips, w, h = struct.unpack("<4sIBBBBII", d[:20])
    if magic != b"BLP2" or enc != 3:
        raise ValueError(f"{path}: not an uncompressed BLP2 (encoding {enc})")
    off = struct.unpack("<I", d[20:24])[0]
    px = np.frombuffer(d[off:off + w * h * 4], dtype=np.uint8).reshape(h, w, 4)
    return Image.fromarray(px[..., [2, 1, 0, 3]], "RGBA")


def trim_square(rgba: Image.Image) -> np.ndarray:
    """Composite on the key plate colour, crop to the visible art, pad to a square."""
    a = np.asarray(rgba.convert("RGBA"), dtype=np.float64) / 255.0
    alpha = a[..., 3]
    ys, xs = np.where(alpha > 0.08)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb = a[..., :3] * alpha[..., None] + PLATE * (1 - alpha[..., None])
    crop = rgb[y0:y1, x0:x1]
    h, w = crop.shape[:2]
    side = max(h, w) + max(2, round(max(h, w) * 0.12))
    out = np.zeros((side, side, 3)) + PLATE
    oy, ox = (side - h) // 2, (side - w) // 2
    out[oy:oy + h, ox:ox + w] = crop
    return out


def load_atlas(path: Path, left: int, top: int, w: int, h: int) -> np.ndarray:
    return trim_square(read_blp2_bgra(path).crop((left, top, left + w, top + h)))


def load_emblem(path: Path) -> np.ndarray:
    """A plain RGBA BLP such as the PvP faction emblem."""
    return trim_square(Image.open(path))


# ---------------------------------------------------------------------------
# The four styles
# ---------------------------------------------------------------------------


def ground(n: int) -> np.ndarray:
    """Near black violet ground with a faint centre lift so a glow has something to sit in."""
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot(xx - (n - 1) / 2, yy - (n - 1) / 2) / (n / 2)
    lift = (1.0 - np.clip(d, 0, 1))[..., None] * 1.4
    return np.clip(BG * 0.9 + (PLATE - BG) * lift, 0, 1)


def edge_layers(src: np.ndarray, out: int, fam: tuple, tune: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (line alpha, line colour, strength) on the work canvas (out*SS square)."""
    work = out * SS
    big = resize(src, work, Image.BICUBIC)
    # a small source (the micro glyphs are ~30 px) has finer features per source pixel
    sig = tune["esig"] * min(1.0, src.shape[0] / 56.0) * work / src.shape[0]
    sm = blur(big, sig)
    gx = np.zeros_like(sm)
    gy = np.zeros_like(sm)
    gx[:, 1:-1] = sm[:, 2:] - sm[:, :-2]
    gy[1:-1] = sm[2:] - sm[:-2]
    g = np.sqrt((gx ** 2 + gy ** 2).sum(axis=2) / 3.0)
    # the square edge of the icon itself is not a feature
    m = int(work * 0.035)
    g[:m] = g[-m:] = 0
    g[:, :m] = g[:, -m:] = 0
    g /= max(np.percentile(g, 99.0), 1e-6)
    g = np.clip(g, 0, 1.4)
    # thin the ridge: keep a pixel only if it is a local maximum across the edge direction
    lx, ly = gx.sum(axis=2), gy.sum(axis=2)
    ang = np.arctan2(ly, lx)
    dx, dy = np.round(np.cos(ang)).astype(int), np.round(np.sin(ang)).astype(int)
    yy, xx = np.mgrid[0:work, 0:work]
    n1 = g[np.clip(yy + dy, 0, work - 1), np.clip(xx + dx, 0, work - 1)]
    n2 = g[np.clip(yy - dy, 0, work - 1), np.clip(xx - dx, 0, work - 1)]
    ridge = np.where((g >= n1) & (g >= n2), g, 0.0)
    e = smoothstep(tune["lo"], tune["hi"], ridge)
    # widen to the target line width; a lone line peaks at 1 and clips to a flat core
    sw = tune["line"] * SS * 0.35
    wide = blur(e, sw) * sw * 2.5066
    alpha = np.clip(wide, 0, 1)
    # colour by edge strength, lifted by the local source brightness
    lum = blur(luma(big), sig * 1.5)
    t = np.clip(0.75 * smoothstep(0.25, 1.2, blur(g, sig)) + 0.25 * smoothstep(0.15, 0.85, lum), 0, 1)
    weak, mid, hot = fam
    col = ramp(blur(t, tune["line"] * SS * 0.5), [weak, mid, hot, WHITE * 0.85 + hot * 0.15])
    core = smoothstep(0.55, 1.0, alpha)[..., None]
    col = col * (1 - 0.30 * core) + WHITE * 0.30 * core
    return alpha, col, g


def style_a(src: np.ndarray, out: int, fam: tuple) -> np.ndarray:
    tune = TUNING[out]
    alpha, col, _ = edge_layers(src, out, fam, tune)
    work = out * SS
    base = ground(work)
    glow_c = blur(alpha[..., None] * col, tune["glow"] * SS)
    rgb = base * (1 - alpha[..., None]) + col * alpha[..., None]
    rgb = rgb + glow_c * tune["gain"] * 0.9
    return finish(rgb, out, tune)


def gradient_map(src: np.ndarray, out: int, fam: tuple) -> np.ndarray:
    """B's colour on the work canvas, before scanlines."""
    work = out * SS
    big = resize(src, work, Image.BICUBIC)
    lum = luma(big)
    # local contrast first so shapes survive the loss of hue
    lum = np.clip(lum + 0.55 * (lum - blur(lum, work / 12.0)), 0, 1)
    lo, hi = np.percentile(lum, 3), np.percentile(lum, 98)
    t = np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.9
    weak, mid, hot = fam
    return ramp(t, [BG, DEEP * 0.8, weak * 0.9, mid, hot, WHITE * 0.8 + hot * 0.2])


def style_b(src: np.ndarray, out: int, fam: tuple) -> np.ndarray:
    return finish(gradient_map(src, out, fam), out, TUNING[out], scan=True)


def style_c(src: np.ndarray, out: int, fam: tuple) -> np.ndarray:
    tune = TUNING[out]
    alpha, col, _ = edge_layers(src, out, fam, tune)
    base = gradient_map(src, out, fam) * 0.42 + BG * 0.10
    glow_c = blur(alpha[..., None] * col, tune["glow"] * SS)
    rgb = base * (1 - alpha[..., None]) + col * alpha[..., None] + glow_c * tune["gain"] * 0.8
    return finish(rgb, out, tune, scan=True)


def bilinear(src: np.ndarray, out: int) -> np.ndarray:
    """Sample src at out x out pixel centres with plain 2x2 bilinear taps and no prefilter.

    That is what the client does when it minifies a texture, so style D aliases a little at 32 and
    16 px where a Lanczos or box downscale would not. Approximate: the real filter and mip chain
    depend on the client's texture settings.
    """
    n = src.shape[0]
    u = (np.arange(out) + 0.5) * n / out - 0.5
    i0 = np.clip(np.floor(u).astype(int), 0, n - 1)
    i1 = np.clip(i0 + 1, 0, n - 1)
    f = np.clip(u - np.floor(u), 0, 1)
    rows = src[i0] * (1 - f)[:, None, None] + src[i1] * f[:, None, None]
    return rows[:, i0] * (1 - f)[None, :, None] + rows[:, i1] * f[None, :, None]


def style_d(src: np.ndarray, out: int, fam: tuple) -> np.ndarray:
    """What the client can do live, and nothing more: SetDesaturated, SetVertexColor (a multiply)
    and one extra low-alpha ADD texture (glow_round).

    The lift `gray * (1 + k * (1 - gray))` is a compressive curve: it raises shadows more than
    highlights so detail survives. The client cannot apply a curve, so in game it is approximated
    by SetVertexColor at about 0.85 to 0.9 times the tint (DHEAD) plus, at most, a low-alpha second
    ADD draw of the icon. Headroom 1 - DHEAD keeps base plus glow under 1 at the centre.
    """
    tune = TUNING[out]
    gray = luma(bilinear(src, out))
    gray = gray * (1.0 + tune["dlift"] * (1.0 - gray)) * DHEAD
    tint = D_TINT[next(k for k, v in FAMILIES.items() if v is fam)]
    rgb = gray[..., None] * tint
    yy, xx = np.mgrid[0:out, 0:out]
    d = np.hypot(xx - (out - 1) / 2, yy - (out - 1) / 2) / (out / 2)
    glow = (np.clip(1 - d, 0, 1) ** 1.6)[..., None] * tint * tune["dglow"]  # glow_round, ADD blend
    return np.clip(rgb + glow, 0, 1)


def finish(rgb: np.ndarray, out: int, tune: dict, scan: bool = False) -> np.ndarray:
    rgb = np.clip(rgb, 0, 1)
    px = resize(rgb, out, Image.BOX)
    if scan and tune["scan"] > 0:
        px[1::2] *= 1.0 - tune["scan"]
    return np.clip(px, 0, 1)


STYLES = {"A": style_a, "B": style_b, "C": style_c, "D": style_d}
SIZES = (64, 32, 16)


def original(src: np.ndarray, out: int) -> np.ndarray:
    return resize(src, out, Image.LANCZOS)


# ---------------------------------------------------------------------------
# Icon lists
# ---------------------------------------------------------------------------

SHAMAN = [
    ("Rockbiter Weapon", "spells/spell_nature_rockbiter.jpg", "earth"),
    ("Flametongue Weapon", "spells/spell_fire_flametounge.jpg", "fire"),
    ("Frostbrand Weapon", "spells/spell_frost_frostbrand.jpg", "frost"),
    ("Windfury Weapon", "spells/spell_nature_windfury.jpg", "air"),
    ("Lightning Shield", "spells/spell_nature_lightningshield.jpg", "lightning"),
    ("Water Shield", "spells/ability_shaman_watershield.jpg", "water"),
]

# (glyph file stem, label, source, family) in the deck's order. Sources, all of them real client
# art (see the module docstring): "micro/<name>.blp" is a classic 32x64 micro button, "atlas:" is a
# cell of the modern micro menu atlas (left,top,width,height), and the PvP emblem is the faction
# crest the classic PvP button draws. Character has no static art (the button draws your portrait
# at runtime) and Legacy has none at all, so both keep their hand drawn glyph_ file and are not here.
# The family is the deck's accent cycle position the glyph had in the approved preview.
ATLAS = "atlas:micro/uimicromenu2x.blp@"
MICRO = [
    ("spellbook", "Spellbook", "micro/spellbook.blp", "house_violet"),
    ("talents", "Talents", "micro/talents.blp", "house_pink"),
    ("professions", "Professions", ATLAS + "397,337,64,82", "house_cyan"),
    ("achievement", "Achievements", "micro/achievement.blp", "house_violet"),
    ("questlog", "Quest Log", "micro/quest.blp", "house_pink"),
    ("guild", "Guild", ATLAS + "265,421,64,82", "house_cyan"),
    ("socials", "Social", "micro/socials.blp", "house_violet"),
    ("lfd", "Group Finder", "micro/lfg.blp", "house_pink"),
    ("pvp", "PvP", "micro/pvp_horde.blp", "house_cyan"),
    ("collections", "Collections", "micro/mounts.blp", "house_violet"),
    ("ej", "Adventure Guide", "micro/ej.blp", "house_pink"),
    ("worldmap", "World Map", "micro/world.blp", "house_cyan"),
    ("store", "Shop", "micro/store.blp", "house_violet"),
    ("help", "Help", "micro/help.blp", "house_pink"),
    ("mainmenu", "Main Menu", "micro/mainmenu.blp", "house_cyan"),
    ("housing", "Housing", ATLAS + "331,337,64,82", "house_violet"),
]
# PvP is baked once per faction (MicroBars.lua picks by UnitFactionGroup), never as plain "pvp".
PVP_VARIANTS = [
    ("pvp_alliance", "micro/pvp_alliance.blp"),
    ("pvp_horde", "micro/pvp_horde.blp"),
    ("pvp_ffa", "micro/pvp_ffa.blp"),
]
# Character and Legacy have no static art: baked from the hand drawn shapes (load_glyph_field).
MICRO_SHAPES = [
    ("character", "glyph:character", "house_cyan"),
    ("legacy", "glyph:legacy", "house_pink"),
]
MICRO_FAMILIES = ["house_cyan", "house_violet", "house_pink"]  # the deck's accent cycle


def load_glyph_field(name: str) -> np.ndarray:
    """A hand drawn line shape (deck_glyph_sources) on a synthetic backdrop: a soft bright core fading to a dark
    edge, so the gradient map gives it a filled, lit field like the Blizzard art, with the strokes the hottest
    thing on it. The shape's 32 px coverage is upscaled first so its edges are smooth at the bake size."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import deck_glyph_sources  # noqa: PLC0415  (same directory)

    n = 64
    cov = Image.fromarray((np.asarray(deck_glyph_sources.render(name)) * 255).astype(np.uint8)).resize((n, n), Image.LANCZOS)
    cov = np.asarray(cov, dtype=np.float64) / 255.0
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot((xx + 0.5) / n - 0.5, (yy + 0.5) / n - 0.5) / 0.5
    field = 0.20 + 0.30 * np.exp(-((r / 0.75) ** 2))
    field = field + 0.14 * blur(cov, 2.0)  # a soft halo round the strokes
    field = field * (1 - cov) + cov
    return np.dstack([field] * 3)


def load_any(root: Path, rel: str) -> np.ndarray:
    if rel.startswith("glyph:"):
        return load_glyph_field(rel[len("glyph:"):])
    if rel.startswith("atlas:"):
        name, rect = rel[len("atlas:"):].split("@")
        return load_atlas(root / name, *[int(v) for v in rect.split(",")])
    path = root / rel.lstrip("~")
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".blp":
        return load_micro(path) if Image.open(path).size == (32, 64) else load_emblem(path)
    return load_spell(path)


def render_set(root: Path, entries, families) -> list[dict]:
    rows = []
    for i, ent in enumerate(entries):
        name, label, rel = ent[0], ent[1], ent[2]
        fam_name = ent[3] if len(ent) > 3 else families[i % len(families)]
        try:
            src = load_any(root, rel)
        except FileNotFoundError as e:
            print(f"missing source {e}", file=sys.stderr)
            continue
        fam = FAMILIES[fam_name]
        row = {"key": name, "label": label, "family": fam_name, "stand_in": rel.startswith("~"), "img": {}}
        for size in SIZES:
            row["img"][f"O{size}"] = to_png(original(src, size))
            for k, fn in STYLES.items():
                row["img"][f"{k}{size}"] = to_png(fn(src, size, fam))
        rows.append(row)
        print("rendered", label, file=sys.stderr)
    return rows


def current_glyphs() -> dict[str, bytes]:
    """The two hand drawn line shapes tinted the way the old micro keys drew them, for the preview's CURRENT column."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import deck_glyph_sources  # noqa: PLC0415  (same directory)

    out = {}
    tint = hexrgb("#cfc4ef")
    for stem, *_ in MICRO_SHAPES:
        a = np.asarray(deck_glyph_sources.render(stem))
        rgb = a[..., None] * tint + (1 - a[..., None]) * PLATE
        out[stem] = to_png(np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize((16, 16), Image.LANCZOS)) / 255.0)
    return out


# ---------------------------------------------------------------------------
# Shipping: the micro menu's style B textures
# ---------------------------------------------------------------------------

BAKE_SIZE = 64  # power of two: a square the key covers; MicroBars.lua crops it to the key's band of rows
BAKE_FILL = 1.15  # the art is padded to this much of its size with its own backdrop: just enough that the key's slanted corners do not cut the glyph, little enough that the art still fills the key
# The micro key's design size (MicroBars.lua KEY_W, KEY_H): the baked art is the key's rect, drawn at the key's width, the
# texture's central band of rows (KEY_H / KEY_W of its height) is the key; the area inside the key's border is opaque and
# everything else is transparent (a MaskTexture does not clip on this client).
KEY_W, KEY_H = 34.0, 26.0


def pad_backdrop(src: np.ndarray, scale: float) -> np.ndarray:
    """Surround the art with its own backdrop colour (a low percentile per channel, so it lands on the
    same dark the gradient map gives the art's own background) so the glyph sits inside a larger field."""
    n = src.shape[0]
    border = np.percentile(src.reshape(-1, 3), 10, axis=0)
    side = int(round(n * scale))
    out = np.zeros((side, side, 3)) + border
    o = (side - n) // 2
    out[o:o + n, o:o + n] = src
    return out


def key_shape_alpha(n: int) -> np.ndarray:
    """Alpha of the area INSIDE the key's border, in the central band of an n x n square: the plate texture's shape
    (cell_slant.tga) minus the ring's line (deck_key_slant_outline.tga, grown by a texel), both drawn stretched over the key's rect, so the art
    stops at the ring's inner edge. The ring is only 35% opaque at idle, so art under it would show through as art running
    over the border; and the drawn shapes, not a constant lean, are what the art has to fit."""
    ss = 8
    band_h = n * KEY_H / KEY_W
    y0 = (n - band_h) / 2
    tex = REPO / "forever-stuwave" / "Media" / "Textures"

    def stretched(name: str) -> np.ndarray:
        alpha = Image.open(tex / name).convert("RGBA").getchannel("A")
        top, bottom = round(y0 * ss), round((y0 + band_h) * ss)
        canvas = Image.new("L", (n * ss, n * ss), 0)
        canvas.paste(alpha.resize((n * ss, bottom - top), Image.BILINEAR), (0, top))
        return np.asarray(canvas, dtype=np.float64).reshape(n, ss, n, ss).mean(axis=(1, 3)) / 255.0

    ring = stretched("deck_key_slant_outline.tga")
    padded = np.pad(ring, 1, mode="edge")
    # one texel of margin: the art ends just inside the ring's line, so the ring's soft inner edge never carries any
    ring = np.max([padded[1 + dy:1 + dy + n, 1 + dx:1 + dx + n] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)
    return np.clip(stretched("cell_slant.tga") - ring, 0.0, 1.0)


def bake_glyph(src: np.ndarray, fam: tuple) -> np.ndarray:
    """Style B at BAKE_SIZE as RGBA uint8: art edge to edge, alpha the area inside the key's border. No scanline: it
    would alias when the client rescales. Outside the shape the colour is the plate's, not the art's: the client filters
    straight (not premultiplied) alpha, so bright art colour in transparent texels would fringe into the border and the gap."""
    rgb = finish(gradient_map(pad_backdrop(src, BAKE_FILL), BAKE_SIZE, fam), BAKE_SIZE, TUNING[BAKE_SIZE], scan=False)
    alpha = key_shape_alpha(BAKE_SIZE)
    rgb = rgb * alpha[..., None] + PLATE * (1.0 - alpha[..., None])
    return (np.dstack([rgb, alpha]) * 255 + 0.5).astype(np.uint8)


def tga_bytes(rgba: np.ndarray) -> bytes:
    """Uncompressed 32 bit TGA, top-left origin, BGRA: the format the other generators write."""
    h, w = rgba.shape[:2]
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    return header + rgba[..., [2, 1, 0, 3]].tobytes()


def bake_own(out_dir: Path) -> list[Path]:
    """Write glyphart_character.tga and glyphart_legacy.tga, the two keys drawn from our OWN hand drawn shapes
    (deck_glyph_sources.py): no game art is involved. Every other key draws the game's own texture at runtime."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for stem, rel, fam in MICRO_SHAPES:
        path = out_dir / f"glyphart_{stem}.tga"
        path.write_bytes(tga_bytes(bake_glyph(load_any(Path("."), rel), FAMILIES[fam])))
        written.append(path)
        print("baked", path.name, file=sys.stderr)
    return written


# ---------------------------------------------------------------------------
# Shipping: the class tab spell icons in style B
# ---------------------------------------------------------------------------

SPELL_BAKE_SIZE = 64  # power of two; the tiles show it at about 32 px
# (icon file name, icon file data id, family, [(spell id, spell name)]). The ids and icon names are the TBC
# data (wowhead's tooltip data, dataEnv 5), the file ids come from the community listfile. The client reports a
# spell's icon as its file id, so that is the key MicroBars-style lookups use (FS.SpellArt); a spell that is not
# listed here simply keeps its stock icon. Sources: spellfiles/<icon name>.blp, interface/icons/<icon name>.
SPELL_ICONS = [
    ("spell_nature_rockbiter", 136086, "earth", [(8017, 'Rockbiter Weapon')]),
    ("spell_fire_flametounge", 135814, "fire", [(8024, 'Flametongue Weapon')]),
    ("spell_frost_frostbrand", 135847, "frost", [(8033, 'Frostbrand Weapon')]),
    ("spell_nature_cyclone", 136018, "air", [(8232, 'Windfury Weapon')]),
    ("spell_nature_lightningshield", 136051, "lightning", [(324, 'Lightning Shield')]),
    ("ability_shaman_watershield", 132315, "water", [(24398, 'Water Shield')]),
    ("spell_fire_searingtotem", 135825, "fire", [(3599, 'Searing Totem')]),
    ("spell_frostresistancetotem_01", 135866, "frost", [(8181, 'Frost Resistance Totem')]),
    ("spell_fire_selfdestruct", 135826, "fire", [(8190, 'Magma Totem')]),
    ("spell_nature_guardianward", 136040, "fire", [(8227, 'Flametongue Totem')]),
    ("spell_nature_stoneskintotem", 136098, "earth", [(8071, 'Stoneskin Totem')]),
    ("spell_nature_strengthofearthtotem02", 136102, "earth", [(2484, 'Earthbind Totem')]),
    ("spell_nature_stoneclawtotem", 136097, "earth", [(5730, 'Stoneclaw Totem')]),
    ("spell_nature_earthbindtotem", 136023, "earth", [(8075, 'Strength of Earth Totem')]),
    ("spell_nature_tremortotem", 136108, "earth", [(8143, 'Tremor Totem')]),
    ("inv_spear_04", 135127, "water", [(5394, 'Healing Stream Totem')]),
    ("spell_nature_poisoncleansingtotem", 136070, "water", [(8166, 'Poison Cleansing Totem')]),
    ("spell_nature_manaregentotem", 136053, "water", [(5675, 'Mana Spring Totem')]),
    ("spell_fireresistancetotem_01", 135832, "fire", [(8184, 'Fire Resistance Totem')]),
    ("spell_nature_groundingtotem", 136039, "air", [(8177, 'Grounding Totem')]),
    ("spell_nature_natureresistancetotem", 136061, "air", [(10595, 'Nature Resistance Totem')]),
    ("ability_thunderbolt", 132325, "house_pink", [(21084, 'Seal of Righteousness')]),
    ("spell_holy_holysmite", 135924, "house_pink", [(21082, 'Seal of the Crusader')]),
    ("ability_warrior_innerrage", 132347, "house_pink", [(20375, 'Seal of Command')]),
    ("spell_holy_healingaura", 135917, "house_pink", [(20165, 'Seal of Light')]),
    ("spell_holy_righteousnessaura", 135960, "house_pink", [(20166, 'Seal of Wisdom')]),
    ("spell_holy_sealofwrath", 135971, "house_pink", [(20164, 'Seal of Justice')]),
    ("spell_holy_devotionaura", 135893, "house_cyan", [(465, 'Devotion Aura')]),
    ("spell_holy_auraoflight", 135873, "house_cyan", [(7294, 'Retribution Aura')]),
    ("spell_holy_mindsooth", 135933, "house_cyan", [(19746, 'Concentration Aura')]),
    ("spell_shadow_sealofkings", 136192, "house_cyan", [(19876, 'Shadow Resistance Aura')]),
    ("spell_frost_wizardmark", 135865, "house_cyan", [(19888, 'Frost Resistance Aura')]),
    ("spell_fire_sealoffire", 135824, "house_cyan", [(19891, 'Fire Resistance Aura')]),
    ("spell_holy_mindvision", 135934, "house_cyan", [(20218, 'Sanctity Aura')]),
    ("ability_warrior_offensivestance", 132349, "house_violet", [(2457, 'Battle Stance')]),
    ("ability_warrior_defensivestance", 132341, "house_violet", [(71, 'Defensive Stance')]),
    ("ability_racial_avatar", 132275, "house_violet", [(2458, 'Berserker Stance')]),
]


# ---------------------------------------------------------------------------
# Shipping: the runtime icon style's data (numbers only: file ids, texture windows, gains)
# ---------------------------------------------------------------------------
#
# The micro keys and the class tab tiles draw the game's OWN textures and restyle them live (Core/IconStyle.lua), so
# no art derived from the game is shipped. What the addon needs per icon is a handful of numbers: which texture, which
# window of it to show, how bright it needs to be, which colour family. They are computed here from the downloaded
# sources (never committed) and written to forever-stuwave/Core/IconStyleData.lua.

# Game textures by file id (community listfile). The classic micro button textures are 32x64: a button frame with the glyph
# window at (5,29)-(27,58).
CLASSIC_MICRO_IDS = {
    "spellbook": (130810, "spellbook"), "talents": (130813, "talents"), "achievement": (235422, "achievement"),
    "questlog": (130804, "quest"), "socials": (130807, "socials"), "lfd": (130798, "lfg"), "mainmenu": (130801, "mainmenu"),
    "help": (130794, "help"), "worldmap": (130816, "world"), "ej": (525019, "ej"), "collections": (615164, "mounts"),
    "store": (902317, "store"),
}
CLASSIC_WINDOW = (5, 29, 27, 58)
ATLAS_ID = 4708813  # interface/hud/uimicromenu2x
ATLAS_CELLS = {"professions": (397, 337, 64, 82), "guild": (265, 421, 64, 82), "housing": (331, 337, 64, 82)}
PVP_IDS = {"Alliance": (136998, "pvp_alliance"), "Horde": (137000, "pvp_horde"), "other": (136999, "pvp_ffa")}
# The class keys draw Interface\Icons\ClassIcon_<Class> (64x64, a bevel at the edge: the 0.07 crop the tiles use skips it).
CLASS_TOKENS = {"WARRIOR": "Warrior", "PALADIN": "Paladin", "HUNTER": "Hunter", "ROGUE": "Rogue", "PRIEST": "Priest",
                "SHAMAN": "Shaman", "MAGE": "Mage", "WARLOCK": "Warlock", "DRUID": "Druid"}
CLASS_CROP = (0.07, 0.93)
CLASS_FAMILY = "house_cyan"
# The micro key's icon rectangle is the key's inside bounding box: key columns 1 to 33 of the 34 wide key, full height
# (generate_icon_style.py COVER_RECTS["key"], also the cover's span), so no plate wedge is left without art on the `/` leaning
# key; the cover then trims the two outside triangles along the slant. Every glyph is drawn UPRIGHT (four texcoords, no lean)
# zoomed to fill that rectangle: the texcoord window has the rectangle's aspect, so the picture is cropped at the texture's
# edge when its own part of the texture is too narrow or too short, and never stretched.
RECT_COLS = (1.0, 33.0)
COVER_FILE = "iconcover_key.tga"
FIT_PAD = 1.06  # the window is this much larger than the glyph, so it does not touch the key's edge
BOOST_TARGET = 0.85  # the 90th percentile of the icon's brightness is lifted to about this
LIFT_STRENGTH = 0.15  # the flat ADD under the ramp: the family's weak colour times this tints the shadows


def read_rgba(root: Path, rel: str) -> Image.Image:
    path = root / rel
    if path.suffix == ".blp" and Image.open(path).size == (32, 64):
        return Image.open(path).convert("RGBA")
    try:
        return Image.open(path).convert("RGBA")
    except Exception:  # noqa: BLE001  (the modern atlas is an uncompressed BLP2 Pillow does not read)
        return read_blp2_bgra(path)


def alpha_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(im.convert("RGBA"), dtype=np.float64)[..., 3] / 255.0
    ys, xs = np.where(a > 0.08)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def fit_window(box: tuple[float, float, float, float], limit: tuple[float, float, float, float], rect_w: float,
               rect_h: float, pad: float = FIT_PAD) -> tuple[float, float, float, float]:
    """The texel window to show in a rect_w x rect_h rectangle so the glyph in `box` (l, t, r, b texels) fills it: grown
    by `pad`, widened or heightened to the rect's aspect (a transparent margin), and kept inside `limit` (the part of the
    texture that is the glyph's own: a button frame or a neighbouring atlas cell must never show), cropping the other axis
    when the limit ends first."""
    l, t, r, b = box
    ll, lt, lr, lb = limit
    cx, cy = (l + r) / 2, (t + b) / 2
    w, h = (r - l) * pad, (b - t) * pad
    aspect = rect_w / rect_h
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    if w > lr - ll:
        w, h = lr - ll, (lr - ll) / aspect
    if h > lb - lt:
        h, w = lb - lt, (lb - lt) * aspect
    cx = min(max(cx, ll + w / 2), lr - w / 2)
    cy = min(max(cy, lt + h / 2), lb - h / 2)
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def boost_for(im: Image.Image, window: tuple[float, float, float, float]) -> float:
    """How much brighter than the plain desaturated icon the style must draw it, 0 (as is) to 1 (twice)."""
    a = np.asarray(im.convert("RGBA"), dtype=np.float64) / 255.0
    l, t, r, b = (int(round(v)) for v in window)
    a = a[t:b, l:r]
    lum = luma(a[..., :3])
    solid = lum[a[..., 3] > 0.5]
    p90 = float(np.percentile(solid, 90)) if solid.size else 0.5
    gain = float(np.clip(BOOST_TARGET / max(p90, 0.05), 1.0, 2.0))
    return round(gain - 1.0, 2)


def runtime_entry(im: Image.Image, window: tuple[float, float, float, float], file_id, fam: str,
                  limit: tuple[float, float, float, float] | None = None) -> dict:
    """One icon's data: the file, the upright texcoord window (l, r, t, b as fractions), the texture's size in texels, the
    family and the boost. The window is the glyph grown a little, given the icon rectangle's aspect (a transparent margin is
    added, or the other axis cropped, centred) and kept inside the `limit` (the glyph's own part of the texture: a button
    frame or a neighbouring atlas cell must never show), so the picture fills the rectangle without being stretched."""
    w, h = im.size
    limit = limit or (0, 0, w, h)
    x0, x1 = RECT_COLS
    box = fit_window(window, limit, x1 - x0, KEY_H)
    frac = (box[0] / w, box[2] / w, box[1] / h, box[3] / h)
    lim = (limit[0] / w, limit[2] / w, limit[1] / h, limit[3] / h)
    return {"file": file_id, "fam": fam, "coords": frac, "size": (w, h), "limit": lim, "boost": boost_for(im, box)}


def micro_runtime_data(root: Path) -> tuple[dict, dict, dict]:
    """(micro, pvp, class) data tables. micro: stem -> entry; pvp: faction -> entry; class: token -> entry."""
    fam_of = {stem: fam for stem, _l, _r, fam in MICRO}
    micro, pvp, klass = {}, {}, {}
    for stem, (fid, local) in CLASSIC_MICRO_IDS.items():
        im = read_rgba(root, f"micro/{local}.blp")
        micro[stem] = runtime_entry(im, CLASSIC_WINDOW, fid, fam_of[stem], limit=CLASSIC_WINDOW)
    sheet = read_blp2_bgra(root / "micro/uimicromenu2x.blp")
    for stem, (left, top, w, h) in ATLAS_CELLS.items():
        cell = sheet.crop((left, top, left + w, top + h))
        x0, y0, x1, y1 = alpha_bbox(cell)
        win = (left + x0, top + y0, left + x1, top + y1)
        micro[stem] = runtime_entry(sheet, win, ATLAS_ID, fam_of[stem], limit=(left, top, left + w, top + h))
    for faction, (fid, local) in PVP_IDS.items():
        im = read_rgba(root, f"micro/{local}.blp")
        pvp[faction] = runtime_entry(im, alpha_bbox(im), fid, fam_of["pvp"])
    for token, name in CLASS_TOKENS.items():
        im = read_rgba(root, f"classicons/{name.lower()}.blp")
        w, h = im.size
        # the 0.07 crop is the whole glyph, a square; the key's inside is wider than tall, so its full width is shown and the
        # rows are cropped to the rectangle's aspect, centred (the art is full bleed: it fills the key, the cover trims it)
        x0, x1 = RECT_COLS
        span = (CLASS_CROP[1] - CLASS_CROP[0]) * (KEY_H / (x1 - x0))
        top, bottom = 0.5 - span / 2, 0.5 + span / 2
        win = (CLASS_CROP[0] * w, top * h, CLASS_CROP[1] * w, bottom * h)
        klass[token] = {"file": "Interface\\Icons\\ClassIcon_" + name, "coords": (CLASS_CROP[0], CLASS_CROP[1], round(top, 5), round(bottom, 5)),
                        "size": (w, h), "limit": (CLASS_CROP[0], CLASS_CROP[1], CLASS_CROP[0], CLASS_CROP[1]), "fam": CLASS_FAMILY, "boost": boost_for(im, win)}
    return micro, pvp, klass


def lua_num(v) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def lua_entry(ent: dict) -> str:
    fid = ent["file"]
    file = fid if isinstance(fid, int) else '"' + fid.replace("\\", "\\\\") + '"'
    l, r, t, b = (lua_num(round(v, 5)) for v in ent["coords"])
    ll, lr, lt, lb = (lua_num(round(v, 5)) for v in ent["limit"])
    return (f'{{ file = {file}, coords = {{ {l}, {r}, {t}, {b} }}, size = {{ {ent["size"][0]}, {ent["size"][1]} }}, '
            f'limit = {{ {ll}, {lr}, {lt}, {lb} }}, '
            f'fam = "{ent["fam"]}", boost = {lua_num(ent["boost"])} }}')


def spell_look(root: Path, icon: str, fam: str) -> dict:
    """The boost for a spell tile: the tiles draw the 0.07 crop of the 64 px icon file."""
    im = Image.open(root / "spellfiles" / f"{icon}.blp").convert("RGBA")
    w, h = im.size
    return {"fam": fam, "boost": boost_for(im, (0.07 * w, 0.07 * h, 0.93 * w, 0.93 * h))}


def lua_runtime_data(root: Path) -> str:
    micro, pvp, klass = micro_runtime_data(root)
    ramps = "".join(
        f'    {fam} = {{ file = "iconramp_{fam}.tga", lift = {{ {", ".join(lua_num(round(float(c) * LIFT_STRENGTH, 4)) for c in FAMILIES[fam][0])} }} }},\n'
        for fam in FAMILIES)
    cx0, cx1 = RECT_COLS
    cover = f'  cover = {{ file = "{COVER_FILE}", x0 = {lua_num(round(cx0 / KEY_W, 5))}, x1 = {lua_num(round(cx1 / KEY_W, 5))} }},\n'
    micro_s = "".join(f"    {k} = {lua_entry(v)},\n" for k, v in micro.items())
    pvp_s = "".join(f"    {k} = {lua_entry(v)},\n" for k, v in pvp.items())
    class_s = "".join(f"    {k} = {lua_entry(v)},\n" for k, v in klass.items())
    looks = {icon: spell_look(root, icon, fam) for icon, _fd, fam, _ids in SPELL_ICONS}
    by_file = "".join(f'    [{fdid}] = "{icon}",\n' for icon, fdid, _f, _ids in SPELL_ICONS)
    by_name = "".join(f'    {icon} = "{icon}",\n' for icon, _fd, _f, _ids in SPELL_ICONS)
    by_spell = "".join(f'    [{sid}] = "{icon}",  -- {name}\n' for icon, _fd, _f, ids in SPELL_ICONS for sid, name in ids)
    look_s = "".join(f'    {icon} = {{ fam = "{v["fam"]}", boost = {lua_num(v["boost"])} }},\n' for icon, v in looks.items())
    return (
        "-- Generated by tools/assets/synthwave_icons.py --gen-runtime. Do not edit by hand.\n"
        "-- The runtime icon style's data (Core/IconStyle.lua): numbers only, nothing derived from game art.\n"
        "--   ramps:  colour families, the ramp texture and the flat ADD that tints the shadows\n"
        "--   cover:  the cover texture of a micro key and the key columns it spans (fractions of the key width): also the\n"
        "--           rectangle every glyph is drawn in\n"
        "--   micro, pvp, class: the game texture a micro key draws (file id or path), the upright texcoord window (l, r, t, b)\n"
        "--           zoomed to the rectangle's aspect, the texture's size in texels (w, h), the glyph's own part of the texture\n"
        "--           (limit: l, r, t, b; the window is refitted inside it when the keys shrink) and the family and the boost\n"
        "--           (0 plain, 1 twice as bright)\n"
        "--   spells: byFile (the icon file id the client reports for a spell) and byName (the lower case icon file name)\n"
        "--           to an icon name; look: that name to its family and boost; bySpell: the spell ids that wear each icon,\n"
        "--           kept for the harness (every spell the class tabs show must be here)\n"
        "local _, FS = ...\n"
        "FS.IconStyleData = {\n"
        "  ramps = {\n" + ramps + "  },\n"
        + cover +
        "  micro = {\n" + micro_s + "  },\n"
        "  pvp = {\n" + pvp_s + "  },\n"
        "  class = {\n" + class_s + "  },\n"
        "  spells = {\n"
        "  byFile = {\n" + by_file + "  },\n  byName = {\n" + by_name + "  },\n  look = {\n" + look_s + "  },\n  bySpell = {\n"
        + by_spell + "  },\n  },\n}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sources", type=Path, default=Path("."), help="directory holding spells/, micro/, classicons/, spellfiles/ (not needed by --bake-own)")
    ap.add_argument("--html", type=Path, default=REPO / "debug" / "synthwave-icons-2026-10-14.html",
                    help="standalone preview page (default is under debug/, which is untracked: it embeds Blizzard art, never commit it)")
    ap.add_argument("--png-dir", type=Path, help="also write every rendered PNG here")
    ap.add_argument("--bake-own", action="store_true",
                    help="write glyphart_character.tga and glyphart_legacy.tga (our own hand drawn shapes) into "
                         "forever-stuwave/Media/Textures (or FS_ASSET_OUTPUT_DIR), then stop")
    ap.add_argument("--gen-runtime", action="store_true",
                    help="write Core/IconStyleData.lua (file ids, texture windows, boosts; numbers only), then stop")
    args = ap.parse_args()

    if args.gen_runtime:
        lua = Path(os.environ.get("FS_ICONSTYLE_DATA") or REPO / "forever-stuwave" / "Core" / "IconStyleData.lua")
        lua.write_text(lua_runtime_data(args.sources), encoding="utf-8", newline="\n")
        print("wrote", lua, file=sys.stderr)
        return 0
    if args.bake_own:
        out = Path(os.environ.get("FS_ASSET_OUTPUT_DIR") or REPO / "forever-stuwave" / "Media" / "Textures")
        bake_own(out)
        return 0

    shaman = render_set(args.sources, [(n, n, r, f) for n, r, f in SHAMAN], list(FAMILIES))
    micro = render_set(args.sources, MICRO, MICRO_FAMILIES)
    cur = current_glyphs()

    if args.png_dir:
        args.png_dir.mkdir(parents=True, exist_ok=True)
        for grp, rows in (("shaman", shaman), ("micro", micro)):
            for r in rows:
                for k, b in r["img"].items():
                    safe = r["key"].lower().replace(" ", "_")
                    (args.png_dir / f"{grp}_{safe}_{k}.png").write_bytes(b)

    if args.html:
        from synthwave_icons_page import build_page  # noqa: PLC0415  (same directory)

        enc = lambda b: base64.b64encode(b).decode("ascii")
        data = {
            "shaman": [dict(r, img={k: enc(v) for k, v in r["img"].items()}) for r in shaman],
            "micro": [dict(r, img={k: enc(v) for k, v in r["img"].items()}) for r in micro],
            "current": {k: enc(v) for k, v in cur.items()},
        }
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(build_page(json.dumps(data)), encoding="utf-8")
        print("wrote", args.html, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
