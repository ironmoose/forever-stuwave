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
never committed (the mockup used debug/icon-sources-2026-10-14/):

    spells/<iconname>.jpg    https://wow.zamimg.com/images/wow/icons/large/<iconname>.jpg  (56 px)
    micro/<name>.blp         classic micro button art, fetched by file id from wago.tools
                             (32x64 BLP: the button frame with the glyph inside)
    subs/<iconname>.jpg      zamimg icons standing in where the micro button art is a
                             runtime portrait or does not exist

Usage (read untrusted downloads with -I so nothing in their directory is imported):

    uv run python -I tools/assets/synthwave_icons.py --sources debug/icon-sources-2026-10-14 \\
        --html debug/synthwave-icons-2026-10-14.html

The preview page embeds the derived art as base64, so it defaults to debug/ (gitignored) and
must never be committed to the public repository.

Derived art is made from Blizzard's icons: fine for personal use. A public release should
prefer style D, which ships no copies of Blizzard art.

Needs Pillow and numpy only.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
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
    64: dict(line=1.7, esig=1.1, lo=0.20, hi=0.55, glow=3.2, gain=0.85, scan=0.20, dlift=0.5, dglow=0.14),
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
    out = np.zeros((side, side, 3)) + rgb[0:2].reshape(-1, 3).mean(axis=0)
    y0, x0 = (side - h) // 2, (side - w) // 2
    out[y0:y0 + h, x0:x0 + w] = rgb
    return out


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
    and one extra ADD texture (glow_round). Lift is by (1 - gray) so highlights keep their detail,
    and the glow is low so base plus glow stays under 1 (headroom 1 - DHEAD).
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

# (glyph file stem, label, source, accent) in the deck's order. A "~" source is a stand-in
# from subs/ because the classic micro button art is a runtime portrait or does not exist.
MICRO = [
    ("character", "Character", "~subs/achievement_character_human_male.jpg"),
    ("spellbook", "Spellbook", "micro/spellbook.blp"),
    ("talents", "Talents", "micro/talents.blp"),
    ("professions", "Professions", "~subs/trade_blacksmithing.jpg"),
    ("achievement", "Achievements", "micro/achievement.blp"),
    ("questlog", "Quest Log", "micro/quest.blp"),
    ("guild", "Guild", "~subs/inv_shirt_guildtabard_01.jpg"),
    ("socials", "Social", "micro/socials.blp"),
    ("lfd", "Group Finder", "micro/lfg.blp"),
    ("pvp", "PvP", "~subs/achievement_pvp_a_01.jpg"),
    ("collections", "Collections", "micro/mounts.blp"),
    ("ej", "Adventure Guide", "micro/ej.blp"),
    ("worldmap", "World Map", "micro/world.blp"),
    ("store", "Shop", "micro/store.blp"),
    ("help", "Help", "micro/help.blp"),
    ("mainmenu", "Main Menu", "micro/mainmenu.blp"),
]
MICRO_FAMILIES = ["house_cyan", "house_violet", "house_pink"]  # the deck's accent cycle


def load_any(root: Path, rel: str) -> np.ndarray:
    path = root / rel.lstrip("~")
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".blp":
        return load_micro(path)
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
    """The hand-drawn glyph_*.tga files tinted the way MicroBars draws them, for comparison."""
    out = {}
    tex = REPO / "forever-stuwave" / "Media" / "Textures"
    tint = hexrgb("#cfc4ef")
    for stem, *_ in MICRO:
        p = tex / f"glyph_{stem}.tga"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGBA")
        a = np.asarray(im, dtype=np.float64)[..., 3] / 255.0
        rgb = a[..., None] * tint + (1 - a[..., None]) * PLATE
        out[stem] = to_png(np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize((16, 16), Image.LANCZOS)) / 255.0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sources", type=Path, required=True, help="directory holding spells/, micro/, subs/")
    ap.add_argument("--html", type=Path, default=REPO / "debug" / "synthwave-icons-2026-10-14.html",
                    help="standalone preview page (default is under debug/, which is untracked: it embeds Blizzard art, never commit it)")
    ap.add_argument("--png-dir", type=Path, help="also write every rendered PNG here")
    args = ap.parse_args()

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
