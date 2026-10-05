#!/usr/bin/env python3
"""Generates icon_chat.tga and icon_channel.tga: the two title-bar glyphs.

WHY WE DRAW THESE INSTEAD OF TINTING BLIZZARD'S

Parker: "We don't need the borders for these. just the icons will be fine."
Dropping our own border got the channel button there -- measured via
`/fschat parts`, its glyph is a separate OVERLAY region
(`chatframe-button-icon-voicechat`) sitting on a `chatframe-button-up` disc, so
hiding the disc leaves a clean speaker.

ChatFrameMenuButton is NOT built that way. Its three ARTWORK regions are plain
fileIDs (130947-9) with no atlas, and the rounded frame is painted INTO the
glyph -- there is no disc to hide. Probed for a bare atlas variant on 16001 and
there is none: `chatframe-button-icon-` + chat / emote / menu / speech all fail
to resolve. So the frame can only be cropped off with SetTexCoord, which means
magnifying a ~10px bubble to 16px and wearing the blur, or replaced.

Replaced, then -- and once one is drawn the other should be too, or the bar
carries one vector glyph beside one piece of Blizzard atlas art at slightly
different weights.

Both use the SAME hologram treatment as generate_icon_social.py (even scanlines,
a vertical falloff, and a rim exempt from the lines so the silhouette survives).
The constants are duplicated rather than imported because each generator here is
a standalone stdlib script, and because these two are a matched pair with the
social icon: if that one's look is ever retuned, these should be retuned WITH
it deliberately, not silently dragged along by a shared import.

Shape and intensity live in the alpha channel with white RGB, so Chat.lua tints
them to whatever the state calls for.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left
origin, 8 alpha bits), BGRA top-to-bottom.

    python generate_icon_chrome.py
"""

import math
import os
import struct

SIZE = 32
SUPERSAMPLE = 6

# Identical to generate_icon_social.py -- see the module docstring for why they
# are copied rather than imported.
SCAN_PERIOD = 3.0        # texels between scanline starts
SCAN_GAP = 1.0           # texels actually cut
SCAN_DIM = 0.28          # a cut is not fully empty; a hologram still glows there

RIM = 1.3                # texels of near-solid edge
RIM_ALPHA = 0.95
FALLOFF_TOP = 0.45       # alpha at the very top of the glyph
FALLOFF_BOTTOM = 1.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _rounded_rect(px, py, x0, y0, x1, y1, radius):
    """Inside an axis-aligned rounded rectangle.

    Standard inset-and-measure: clamp the point to the rectangle shrunk by
    `radius`, then ask whether it is within `radius` of that clamp. One
    expression covers the flat edges and all four corners.
    """
    cx = min(max(px, x0 + radius), x1 - radius)
    cy = min(max(py, y0 + radius), y1 - radius)
    return math.hypot(px - cx, py - cy) <= radius


def _triangle(px, py, a, b, c):
    """Inside a triangle, by consistent sign of the three edge cross products."""
    def side(p, q):
        return (q[0] - p[0]) * (py - p[1]) - (q[1] - p[1]) * (px - p[0])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def _arc(px, py, cx, cy, radius, thickness, half_angle):
    """Inside an annulus segment opening to the RIGHT of (cx, cy).

    `half_angle` is in degrees off the +x axis, so the sound waves fan
    symmetrically about the speaker's axis the way a real one is drawn.
    """
    dx, dy = px - cx, py - cy
    dist = math.hypot(dx, dy)
    if abs(dist - radius) > thickness / 2.0:
        return False
    if dx <= 0:
        return False
    return abs(math.degrees(math.atan2(dy, dx))) <= half_angle


# ---------------------------------------------------------------------------
# The two silhouettes
# ---------------------------------------------------------------------------

def _inside_chat(px, py):
    """A speech bubble: rounded body with a tail off the bottom left.

    Filled rather than outlined on purpose. An outline would be all rim, and
    the rim is exempt from the scanlines -- so an outlined bubble would come
    out solid and read as a different family from the other two icons.
    """
    if _rounded_rect(px, py, 4.0, 5.0, 28.0, 22.0, 5.0):
        return True
    return _triangle(px, py, (10.0, 20.0), (10.0, 29.0), (18.0, 21.0))


def _inside_channel(px, py):
    """A speaker: a small box, a cone opening right, and two waves."""
    if 6.0 <= px <= 12.5 and 12.0 <= py <= 20.0:
        return True
    # Cone. Two triangles rather than a trapezoid test, which keeps the edge
    # function the same shape as the tail's and so antialiases identically.
    cone = ((12.0, 13.0), (20.0, 5.0), (20.0, 27.0))
    if _triangle(px, py, *cone):
        return True
    if _triangle(px, py, (12.0, 13.0), (20.0, 27.0), (12.0, 19.0)):
        return True
    if _arc(px, py, 20.5, 16.0, 5.0, 1.9, 52.0):
        return True
    if _arc(px, py, 20.5, 16.0, 9.0, 1.9, 52.0):
        return True
    return False


# ---------------------------------------------------------------------------
# Hologram shading (shared by both glyphs)
# ---------------------------------------------------------------------------

def _near_edge(inside, px, py):
    """True if inside but within RIM texels of the outside."""
    if not inside(px, py):
        return False
    for dx, dy in ((RIM, 0), (-RIM, 0), (0, RIM), (0, -RIM),
                   (RIM * 0.7, RIM * 0.7), (-RIM * 0.7, RIM * 0.7),
                   (RIM * 0.7, -RIM * 0.7), (-RIM * 0.7, -RIM * 0.7)):
        if not inside(px + dx, py + dy):
            return True
    return False


def _intensity(inside, px, py):
    if not inside(px, py):
        return 0.0

    t = min(max(py / float(SIZE), 0.0), 1.0)
    value = FALLOFF_TOP + (FALLOFF_BOTTOM - FALLOFF_TOP) * t

    edge = _near_edge(inside, px, py)
    if not edge and (py % SCAN_PERIOD) < SCAN_GAP:
        value *= SCAN_DIM
    if edge:
        value = max(value, RIM_ALPHA)
    return value


def _coverage(inside, x, y):
    total = 0.0
    for sy in range(SUPERSAMPLE):
        py = y + (sy + 0.5) / SUPERSAMPLE
        for sx in range(SUPERSAMPLE):
            px = x + (sx + 0.5) / SUPERSAMPLE
            total += _intensity(inside, px, py)
    return total / (SUPERSAMPLE * SUPERSAMPLE)


def build(inside):
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            rows += bytes((255, 255, 255, int(round(_coverage(inside, x, y) * 255))))
    return bytes(rows)


def _write(path, pixels):
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(pixels)
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "addon", "ForeverSynthwave", "media"))
    _write(os.path.join(here, "icon_chat.tga"), build(_inside_chat))
    _write(os.path.join(here, "icon_channel.tga"), build(_inside_channel))
