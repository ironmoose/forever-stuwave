#!/usr/bin/env python3
"""Generates tab_plate.tga and tab_edge.tga: the terminal tab strip's chrome.

WHY THESE EXIST

The active tab started as a flat SetColorTexture rectangle, became a rounded
nine-sliced plate with an ADD bloom, and Parker rejected both: "the tab bg is
just a box right now and should be cool synthwave looking", then "rounding
corners are nice for the tab but it feels out of place" and "the gradient bar
running across the tab looks weird", and finally "the tabs are better but look
boring af".

Rounded is wrong here and so is flat. This UI's shape language is ANGULAR --
the minimap is squared off, the XP bar is built from leaning parallelogram
cells, the panels are hard neon rails. A console channel selector belongs in
that family: a plate with its corners CUT rather than rounded, so the silhouette
reads as machined.

tab_plate.tga  the plate body. Top-left and top-right corners are chamfered at
               45 degrees; the bottom corners are square, because the plate
               sits ON the strip's rule and a cut there would float it.
tab_edge.tga   the same silhouette as a 1px outline, drawn only along the top
               and the two chamfers. Stopping the outline before the bottom is
               deliberate: a closed outline turns the plate back into a button,
               which is the shape being avoided. Open at the bottom, it reads
               as a tab socketed into the strip.

NINE-SLICE CONTRACT: the margin passed to SetTextureSliceMargins must equal
CHAMFER, so a corner slice holds exactly the diagonal and the edge slices hold
only straight runs. Chat.lua reads it back as TAB_SLICE_MARGIN; change the two
together or the cut stretches into a wedge.

Pure stdlib, matching the other generators here. Output: 18-byte header, image
type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_tab_plate.py
"""

import os
import struct

SIZE = 32
CHAMFER = 8.0       # texels cut off each TOP corner; MUST match TAB_SLICE_MARGIN
THICKNESS = 1.0     # outline width for tab_edge.tga
SUPERSAMPLE = 6


def _inside(px, py):
    """True if the point is within the chamfered silhouette.

    The cut is a half-plane test per top corner: x + y >= CHAMFER keeps the
    top-left, and (SIZE - x) + y >= CHAMFER keeps the top-right. Everything
    below the chamfer passes both trivially.
    """
    if px < 0 or py < 0 or px > SIZE or py > SIZE:
        return False
    if px + py < CHAMFER:
        return False
    if (SIZE - px) + py < CHAMFER:
        return False
    return True


def _coverage(x, y, test):
    """Antialias by supersampling `test` over the texel's area."""
    hits = 0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            if test(px, py):
                hits += 1
    return hits / (SUPERSAMPLE * SUPERSAMPLE)


def _inset(px, py):
    """The silhouette pulled in by THICKNESS on every side except the bottom.

    The bottom is left open on purpose -- see tab_edge.tga in the docstring.
    """
    if py > SIZE - THICKNESS:
        return _inside(px, py)
    return _inside(px, py + THICKNESS) and _inside(
        px + THICKNESS, py) and _inside(px - THICKNESS, py)


def _write(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


def build_plate():
    """Solid chamfered plate, white, shape in the alpha channel for tinting."""
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            alpha = int(round(_coverage(x, y, _inside) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


def build_edge():
    """The silhouette as an outline: inside minus the inset copy."""
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            outer = _coverage(x, y, _inside)
            inner = _coverage(x, y, _inset)
            alpha = int(round(max(outer - inner, 0.0) * 255))
            rows += bytes((255, 255, 255, alpha))
    return bytes(rows)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    _write(os.path.join(here, "tab_plate.tga"), build_plate())
    _write(os.path.join(here, "tab_edge.tga"), build_edge())
