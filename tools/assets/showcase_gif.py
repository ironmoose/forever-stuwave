#!/usr/bin/env python3
"""Turn class-module frames into a showcase GIF with a small STU watermark in the bottom right corner.

Usage:
    showcase_gif.py --frames DIR_OR_STRIP OUT.gif [--fps 20] [--zoom 4] [--strip W,H,COLS,N]
    showcase_gif.py --rewatermark IN.gif OUT.gif

Frames are native size module renders (150 x 86); they are upscaled NEAREST by --zoom. The watermark is
the STU key icon the UI ships (icon_stu.tga) at 3x, 40% opacity.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
MARGIN = 10
OPACITY = 0.4


def stu_mark(scale: int = 3) -> Image.Image:
    """The STU key icon the UI ships (Media/Textures/icon_stu.tga, 32 px), upscaled NEAREST."""
    im = Image.open(HERE.parent.parent / "forever-stuwave/Media/Textures/icon_stu.tga").convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox())
    im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    im.putalpha(im.getchannel("A").point(lambda v: int(v * OPACITY)))
    return im


def stamp(frames: list[Image.Image], mark: Image.Image) -> list[Image.Image]:
    out = []
    for f in frames:
        f = f.convert("RGBA")
        f.alpha_composite(mark, (f.width - mark.width - MARGIN, f.height - mark.height - MARGIN))
        out.append(f.convert("RGB"))
    return out


def save_gif(frames: list[Image.Image], path: Path, durations) -> None:
    # one shared adaptive palette keeps the colours steady from frame to frame
    pal_src = Image.new("RGB", (frames[0].width, frames[0].height * min(len(frames), 12)))
    step = max(1, len(frames) // 12)
    for i, f in enumerate(frames[::step][:12]):
        pal_src.paste(f, (0, i * frames[0].height))
    pal = pal_src.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=False, disposal=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames")
    ap.add_argument("--strip")
    ap.add_argument("--rewatermark")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--zoom", type=int, default=4)
    ap.add_argument("out")
    a = ap.parse_args()
    mark = stu_mark()
    if a.rewatermark:
        src = Image.open(a.rewatermark)
        frames, durs = [], []
        for i in range(src.n_frames):
            src.seek(i)
            frames.append(src.convert("RGB"))
            durs.append(src.info.get("duration", 50))
        save_gif(stamp(frames, mark), Path(a.out), durs)
        return 0
    if a.strip:
        W, H, COLS, N = (int(v) for v in a.strip.split(","))
        im = Image.open(a.frames).convert("RGB")
        frames = [im.crop(((f % COLS) * W, (f // COLS) * H, (f % COLS) * W + W, (f // COLS) * H + H)) for f in range(N)]
    else:
        frames = [Image.open(p).convert("RGB") for p in sorted(Path(a.frames).glob("*.png"))]
    frames = [f.resize((f.width * a.zoom, f.height * a.zoom), Image.NEAREST) for f in frames]
    save_gif(stamp(frames, mark), Path(a.out), int(1000 / a.fps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
