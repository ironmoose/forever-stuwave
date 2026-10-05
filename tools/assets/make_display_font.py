#!/usr/bin/env python3
"""Build the addon's display font from Google's Orbitron variable font.

WHY THIS EXISTS

WoW's font renderer will not load a VARIABLE font. We shipped
``Orbitron-VF.ttf`` (Google's ``Orbitron[wght].ttf``, 38KB) for weeks and every
``SetFont`` on it silently failed -- Theme.ApplyFontGeneric reads the path back
and logged "SetFont failed ... using fallback" the whole time, so every Orbitron
heading in the UI was really FRIZQT. Pinning the weight axis produces an
ordinary static TTF, which loads.

WHY THE FAMILY IS RENAMED

Orbitron is OFL with the Reserved Font Name "Orbitron". Pinning an axis makes
this a Modified Version, and OFL clause 3 forbids a Modified Version from using
the reserved name as the primary name presented to users. So the instance ships
as "FS Display". The OFL text lives beside it in OFL-Orbitron.txt, as clause 2
requires. Crediting Orbitron in the description field (name ID 10) is expressly
allowed.

WHY 700 AND NOT THE OLD STATICS

theleagueof/orbitron ships genuine static Bold files, but they are the
pre-2018 design. The layout mockup loads ``Orbitron:wght@500;700;800`` from
Google Fonts, i.e. the current design, so instancing our VF at 700 is what
actually matches what the mock was judged against.

Usage (needs fonttools, which is NOT a runtime dependency of the addon):

    python -m venv .venv && .venv/Scripts/python -m pip install fonttools
    .venv/Scripts/python tools/assets/make_display_font.py
"""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parents[2] / "addon" / "ForeverSynthwave" / "fonts"
SOURCE = HERE / "Orbitron-VF.ttf"
TARGET = HERE / "FSDisplay-Bold.ttf"

WEIGHT = 700
FAMILY = "FS Display"
SUBFAMILY = "Bold"
FULL_NAME = f"{FAMILY} {SUBFAMILY}"
POSTSCRIPT_NAME = "FSDisplay-Bold"
DESCRIPTION = (
    "Forever Synthwave display face. A static instance (wght=700) of Orbitron "
    "by The League of Moveable Type, as distributed by Google Fonts. Renamed "
    'per OFL 1.1 clause 3; "Orbitron" is a Reserved Font Name.'
)


def build() -> Path:
    font = TTFont(SOURCE)
    static = instancer.instantiateVariableFont(
        font, {"wght": WEIGHT}, updateFontNames=True, inplace=False
    )

    # DSIG signs the variable outlines and is meaningless once they are pinned.
    if "DSIG" in static:
        del static["DSIG"]

    name = static["name"]
    # 16/17 are the typographic family/subfamily. They only exist to describe a
    # family with more members than the 4-style RIBBI model can hold; a lone
    # static Bold has none, and leaving them behind would still say "Orbitron".
    for name_id in (16, 17):
        name.removeNames(nameID=name_id)
    for name_id, value in (
        (1, FAMILY),
        (2, SUBFAMILY),
        (3, f"{POSTSCRIPT_NAME}: Forever Synthwave"),
        (4, FULL_NAME),
        (6, POSTSCRIPT_NAME),
        (10, DESCRIPTION),
    ):
        name.setName(value, name_id, 3, 1, 0x409)  # Windows, Unicode BMP, en-US
        name.setName(value, name_id, 1, 0, 0)  # Macintosh, Roman, English

    static.save(TARGET)
    return TARGET


def verify(path: Path) -> None:
    """Assert the things that would make this font fail in game, or fail OFL."""
    font = TTFont(path)

    leftover = [t for t in ("fvar", "gvar", "avar", "HVAR", "MVAR") if t in font]
    assert not leftover, f"still a variable font: {leftover}"

    name = font["name"]
    for name_id in (1, 3, 4, 6, 16, 17):
        value = name.getDebugName(name_id)
        assert "Orbitron" not in (value or ""), f"name[{name_id}] uses the reserved name: {value}"
    assert name.getDebugName(1) == FAMILY, name.getDebugName(1)
    assert font["OS/2"].usWeightClass == WEIGHT, font["OS/2"].usWeightClass

    print(f"{path.name}: {path.stat().st_size} bytes, {font['maxp'].numGlyphs} glyphs")
    print(f"  family={name.getDebugName(1)!r} subfamily={name.getDebugName(2)!r}")
    print(f"  usWeightClass={font['OS/2'].usWeightClass} macStyle={font['head'].macStyle}")
    print("  no variation tables, no reserved name in any name field")


if __name__ == "__main__":
    verify(build())
