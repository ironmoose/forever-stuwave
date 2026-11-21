#!/usr/bin/env python3
"""Cuts the Help page pictures out of the class module showcase GIFs into tools/assets/help_frames/*.png.

The showcase GIFs (local, under debug/showcase-gifs-<date>/) are the shipped module art rendered frame by frame and
upscaled NEAREST by a whole factor, with a small STU watermark in the bottom right corner. Each Help picture is one
frozen frame of one of them, brought back to the module's own pixels (one texel per art pixel) and with the
watermark painted over by each row's own background colour. The committed PNGs are the source the Help atlas
(help_pictures.py) is baked from, so the atlas can be rebuilt without the GIFs.

    python3 tools/assets/help_frames.py [GIF_DIR]

FRAMES: picture name -> (gif stem, frame index, upscale factor of that GIF, crop box in module pixels or None).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "help_frames"
DEFAULT_GIFS = HERE.parent.parent / "debug" / "showcase-gifs-2026-11-20"
WATERMARK = 90          # GIF pixels from the bottom right corner the watermark may cover

FRAMES: dict[str, tuple[str, int, int, tuple[int, int, int, int] | None]] = {
    "warrior": ("warrior", 87, 3, (0, 0, 135, 100)),
    "warrior_down": ("warrior", 290, 3, (0, 0, 135, 72)),
    "warrior_alert": ("warrior", 87, 3, (154, 0, 300, 96)),
    "paladin": ("paladin", 120, 3, None),
    "paladin_crack": ("paladin", 235, 3, (5, 12, 58, 82)),
    "paladin_slam": ("paladin", 30, 3, None),
    "priest": ("priest", 68, 3, None),
    "priest_empty": ("priest", 0, 3, (0, 0, 70, 70)),
    "priest_tap": ("priest", 177, 3, (70, 0, 150, 40)),
    "shaman": ("shaman", 183, 4, (0, 0, 202, 124)),
    "rogue": ("rogue", 123, 4, None),
    "rogue_finish": ("rogue", 92, 4, (0, 0, 154, 82)),
    "rogue_opener": ("rogue", 23, 4, (0, 0, 154, 82)),
    "hunter": ("hunter", 32, 4, None),
    "hunter_plant": ("hunter", 49, 4, (0, 0, 75, 86)),
    "hunter_late": ("hunter", 106, 4, (0, 0, 75, 86)),
    "druid_caster": ("druid-caster", 66, 4, None),
    "druid_bear": ("druid-bear", 35, 4, None),
    "druid_cat": ("druid-cat", 62, 4, None),
    "druid_cat_finish": ("druid-cat", 81, 4, None),
    "druid_cat_swipe": ("druid-cat", 131, 4, None),
    "mage_frost": ("mage-frost", 170, 4, None),
    "mage_arcane": ("mage-arcane", 116, 4, None),
    "mage_fire": ("mage-fire", 64, 4, None),
    "warlock": ("warlock", 29, 4, None),
    "warlock_summon": ("warlock", 108, 4, None),
    "warlock_fire": ("warlock", 69, 4, None),
    "warlock_tap": ("warlock", 187, 4, None),
    "warlock_reaping": ("warlock", 217, 4, None),
}


def module_pixels(frame: Image.Image, k: int) -> Image.Image:
    """One texel per art pixel: the centre pixel of every k x k block, the watermark painted out row by row."""
    frame = frame.convert("RGB")
    w, h = frame.width // k, frame.height // k
    px = frame.load()
    out = Image.new("RGB", (w, h))
    op = out.load()
    for y in range(h):
        row = [px[x * k + k // 2, y * k + k // 2] for x in range(w)]
        background = Counter(row).most_common(1)[0][0]
        for x in range(w):
            covered = x >= w - WATERMARK // k and y >= h - WATERMARK // k
            op[x, y] = background if covered else row[x]
    return out


def main() -> int:
    gifs = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GIFS
    OUT.mkdir(exist_ok=True)
    for name, (stem, index, k, crop) in FRAMES.items():
        src = Image.open(gifs / f"{stem}.gif")
        src.seek(index)
        im = module_pixels(src, k)
        if crop:
            im = im.crop(crop)
        im.save(OUT / f"{name}.png")
        print(f"{name}: {im.width}x{im.height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
