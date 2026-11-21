#!/usr/bin/env python3
"""Checks the Help page's one source, HelpModules.lua, and the atlas baked from it.

  * the committed help_pictures.tga and HelpPicturesArt.lua equal a fresh bake (tools/assets/help_pictures.py);
  * every picture a page names has a frame in tools/assets/help_frames/ and a rect in the manifest, and no frame is unused;
  * every class in ORDER has pages; a page with more than one has a label each;
  * every pin and extra points at a real line, no number twice, and only lines in UNSHOWN have neither;
  * pins sit in the margin box, targets inside the picture, and the laid out block fits the 550 px content width;
  * the arrows Layout() returns are axis aligned rectangles on whole pixels inside the block;
  * the words are neutral and have no em dash.

    python3 tools/helppage-harness.py

Exit 0 = every check passed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "assets"))
import help_pictures as HP  # noqa: E402

CONTENT_W = 550
UNSHOWN = {("SHAMAN", 1, 4)}          # FAR: no showcase frame has it; the line keeps a dashed number
BANNED = (r"\bbots?\b", r"automat", r"\bmacro", r"\bscript", "\u2014")


def main() -> int:
    problems: list[str] = []
    fresh = subprocess.run([sys.executable, str(HERE / "assets/help_pictures.py"), "--check"], capture_output=True, text=True)
    if fresh.returncode != 0:
        problems.append("atlas: " + (fresh.stdout + fresh.stderr).strip())
    data = HP.load_data()
    H = data["H"]
    manifest = HP.MANIFEST.read_text(encoding="utf-8")
    order = HP.py(H.ORDER)
    used: set[str] = set()
    sizes: dict[str, tuple[int, int]] = {}

    def size(name):
        if name not in sizes:
            im = Image.open(HP.FRAMES / f"{name}.png")
            sizes[name] = (im.width, im.height)
        return sizes[name]

    S, M, PIN = int(H.SCALE), int(H.MARGIN), int(H.PIN)
    for token in order:
        cls = HP.py(H.CLASSES[token])
        pages = cls.get("pages") or []
        if not pages:
            problems.append(f"{token}: no pages")
        for i, page in enumerate(pages, 1):
            where = f"{token} page {i}"
            if len(pages) > 1 and not page.get("label"):
                problems.append(f"{where}: needs a label")
            names = [page["picture"]] + [e["picture"] for e in page.get("extras", [])]
            for n in names:
                used.add(n)
                if not (HP.FRAMES / f"{n}.png").exists():
                    problems.append(f"{where}: no frame {n}.png")
                elif f"        {n} = {{" not in manifest:
                    problems.append(f"{where}: {n} is not in HelpPicturesArt.lua")
            lines = page["lines"]
            numbers = [p[0] for p in page.get("pins", [])] + [e["n"] for e in page.get("extras", [])]
            if len(numbers) != len(set(numbers)):
                problems.append(f"{where}: a number is used twice {numbers}")
            for n in numbers:
                if not 1 <= n <= len(lines):
                    problems.append(f"{where}: {n} has no line")
            for n in range(1, len(lines) + 1):
                if n not in numbers and (token, i, n) not in UNSHOWN:
                    problems.append(f"{where}: line {n} ({lines[n - 1][0]}) has no pin or picture")
            pw, ph = size(page["picture"])
            for n, tx, ty, px, py in page.get("pins", []):
                if not (0 <= tx <= pw and 0 <= ty <= ph):
                    problems.append(f"{where}: pin {n} target {tx},{ty} is off the picture")
                half = PIN / 2 / S
                if not (-M + half <= px <= pw + M - half and -M + half <= py <= ph + M - half):
                    problems.append(f"{where}: pin {n} at {px},{py} leaves the margin")
            text = " ".join(f"{a} {b}" for a, b in lines) + " " + (page.get("note") or "")
            for word in BANNED:
                if re.search(word, text.lower()):
                    problems.append(f"{where}: says {word!r}")
            L = HP.py(H.Layout(H.CLASSES[token]["pages"][i], CONTENT_W, size))
            if L["box"][2] > CONTENT_W:
                problems.append(f"{where}: picture block {L['box'][2]} px is wider than {CONTENT_W}")
            for e in L["extras"]:
                if e[2] + e[4] > CONTENT_W:
                    problems.append(f"{where}: extra {e[1]} runs past the content width")
            bx, by, bw, bh = L["box"]
            for x, y, w, h in L["arrows"]:
                if any(v != int(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
                    problems.append(f"{where}: arrow rect {x},{y},{w},{h} is not whole pixels")
                if x < bx or y < by or x + w > bx + bw or y + h > by + bh:
                    problems.append(f"{where}: arrow rect {x},{y},{w},{h} leaves the picture box")
    frames = {p.stem for p in HP.FRAMES.glob("*.png")}
    if frames - used:
        problems.append(f"unused frames: {sorted(frames - used)}")
    for p in problems:
        print(f"FAIL  {p}")
    print("help page data: " + ("ok" if not problems else f"{len(problems)} problems"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
