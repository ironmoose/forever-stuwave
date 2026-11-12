#!/usr/bin/env python3
"""Generates icon_stu.tga: the STU key's icon on the minimap's key row ("icon A").

Icon A is the STU lettering set over a tilted triangle, picked on 2026-10-07 (design mockup
stuwave-icon, symbol `ic-a`, a 64 unit viewBox) and chosen again for the minimap cleanup of 2026-11-12, where it
replaces the stock gear as the key that opens the config window. This file bakes that symbol, layer for layer, at
the size the key draws it so the strokes land on whole pixels instead of being resampled from a big file:

    canvas 32 x 32 texels, the 64 unit art box mapped onto 22 x 22 of them with 5 clear texels on every side
    (the key lays the canvas at 32 px, so the art is 22 px, the mockup's 44 design px at 2x: the triangle's ink is
    20 px wide, inside the 20 to 24 px band the lettering has to stay readable in).

The layers, in the symbol's own order:

    1  the triangle: a near black fill (#05020a), a violet (#a855f7) 2.6 unit miter stroke
    2  two inner outlines of that triangle, violet (.9 wide, .9 opacity) and cyan (.9 wide, .95 opacity)
    3  five small spikes (tabs on the edges), a dark violet (#4b2a86) 1.8 unit outline round a black fill
    4  the lettering, set in the symbol's own space (translate 32 34, rotate -6, scale .3277): a dark violet
       18.92 unit outline, a black 12.21 unit outline inside it, then the letters filled with three hard
       bands by height (cyan to 42%, violet to 54%, pink below), three thin horizontal gaps cut through them

The triangle and spike strokes are exact miter offsets of their (convex) polygons; the lettering's strokes are
distance fields with round joins, because its outline is a smooth curve where the join style cannot show.
Everything is supersampled, composited in straight alpha, and the colour of fully clear texels is bled from the
nearest inked one so bilinear sampling never pulls a black fringe in.

Pure stdlib. Output: 18-byte header, image type 2, descriptor 0x28 (top-left origin, 8 alpha bits), BGRA
top-to-bottom.

    python generate_icon_stu.py
"""

import math
import os
import re
import struct

SIZE = 32
ART = 22                      # texels the 64 unit art box covers (the mockup's 44 design px / 2)
PAD = (SIZE - ART) // 2       # clear texels round the art box
UNITS = 64.0
SUPERSAMPLE = 6
N = SIZE * SUPERSAMPLE        # subsamples per side
MITER_LIMIT = 4.0             # the SVG default, used by the spikes (the triangle's own limit is 6; none reaches either)

VIOLET = (0xA8, 0x55, 0xF7)
CYAN = (0x22, 0xE0, 0xFF)
PINK = (0xFF, 0x2E, 0x97)
DEEP = (0x4B, 0x2A, 0x86)
INK = (0x05, 0x02, 0x0A)
BLACK = (0, 0, 0)

TRIANGLE = [(29, 3.5), (61.5, 53), (3.5, 47.5)]
INNER_VIOLET = [(29.23, 6.62), (58.48, 51.17), (6.28, 46.22)]
INNER_CYAN = [(29.42, 9.11), (56.07, 49.70), (8.51, 45.19)]
SPIKES = [
    [(2, 33), (11, 28), (12, 37)],
    [(61, 24), (52, 28), (54, 20)],
    [(48, 52), (54, 60), (40, 49)],
    [(10, 50), (8, 58), (18, 47)],
    [(36, 12), (33, 3), (40, 14)],
]

# The lettering: one path of three subpaths (S, T, U) in the symbol's own space, y up.
LETTERS_D = (
    "M16.6 5.8Q11.5 6 7.25 4.55Q3 3.1 0.35 0.6Q-2.3 -1.9 -3 -5.25Q-3.7 -8.6 -1.8 -12.1Q0.8 -16.3 8.6 -14.6"
    "Q14.5 -13.4 16.75 -13.3Q19 -13.2 20.6 -13.9Q27.9 -16.3 28.8 -19.1Q29.4 -21.2 26.2 -24Q24.9 -25.2 23.3 -26.4"
    "Q21.7 -27.6 20.6 -28.8Q15.6 -32.5 12.75 -37.35Q9.9 -42.2 10.4 -47.9Q10.9 -53.6 12.3 -57.35"
    "Q13.7 -61.1 15.8 -64Q19.5 -69.1 25.4 -72.3Q32.2 -75.8 36.3 -76.8Q44.4 -78.6 52.7 -77.1Q55.5 -76.6 57.5 -75.2"
    "Q59.5 -73.8 61.5 -72.3Q65 -68.8 63.2 -65.2Q62.5 -63.6 61 -62.6Q59.5 -61.6 57.8 -61.5Q58 -58.8 56.8 -57.5"
    "Q54.5 -55.2 48.8 -54.5Q40.6 -55.1 37.7 -53.6Q34.3 -51.8 35.2 -45.8Q35.4 -44.5 36.85 -43.1"
    "Q38.3 -41.7 40.25 -40.1Q42.2 -38.5 44.35 -36.5Q46.5 -34.5 48.1 -31.9Q53.7 -22.7 47.2 -10.4"
    "Q42.4 -1.2 30.8 3.4Q24.8 5.8 16.6 5.8Z "
    "M66.4 7.6Q58 6.3 61.2 -4.5Q63.3 -13.1 64.6 -18.55Q65.9 -24 66.75 -27.55Q67.6 -31.1 68.2 -33.45"
    "Q68.8 -35.8 69.5 -38.1Q70.2 -40.4 71.25 -43.3Q72.3 -46.2 74 -51Q70.2 -50.5 67.2 -51.8Q62.8 -53.7 63.6 -60"
    "Q64 -62.9 66.7 -65.4Q68.1 -66.7 70 -68.2Q73.9 -71.3 85.5 -74.8Q97.5 -78.4 106.1 -78.2"
    "Q108.4 -78.6 110.85 -77.65Q113.3 -76.7 114.8 -75.1Q116.3 -73.5 116.35 -71.6Q116.4 -69.7 113.9 -68.2"
    "Q112.7 -67.4 112.2 -65.55Q111.7 -63.7 111.1 -61.65Q110.5 -59.6 109.35 -57.9Q108.2 -56.2 105.7 -55.9"
    "Q104.4 -55.2 102.05 -54.9Q99.7 -54.6 98.95 -54.45Q98.2 -54.3 98.1 -53.9Q96.3 -48.6 93.8 -41.05"
    "Q91.3 -33.5 88.55 -25.65Q85.8 -17.8 83 -10.6Q80.2 -3.4 78.35 0.35Q76.5 4.1 75.1 5.5Q73.7 6.9 72.25 7.4"
    "Q70.8 7.9 69.35 7.8Q67.9 7.7 66.4 7.6ZM75 -52.1Q74.8 -52.1 74.8 -52.05Q74.8 -52 75 -52Z "
    "M136.7 -72.4V-72.2Q136.7 -72.1 136.75 -72.1Q136.8 -72.1 136.8 -72V-71.8H136.9L137.5 -70.2"
    "Q138.5 -67.3 132.3 -52.2Q125.7 -36.1 126.2 -27.1Q127.3 -20.7 136.9 -37.4Q144.5 -50.4 151.6 -65.9"
    "Q152.5 -68 153.5 -70.25Q154.5 -72.5 156 -74Q159.3 -77.6 164 -75.9Q165.6 -77.8 167.75 -78.5"
    "Q169.9 -79.2 171.85 -78.8Q173.8 -78.4 175.2 -76.95Q176.6 -75.5 176.7 -73.1Q177 -71.1 174.65 -63.6"
    "Q172.3 -56.1 170.3 -49.9Q168.3 -43.7 166.2 -36.4Q161.1 -19.1 158.1 -3.8Q158 -0.6 155.35 1.5"
    "Q152.7 3.6 149.45 4.25Q146.2 4.9 143.3 4Q139.8 3 139.6 -1Q139.6 -2.1 139.5 -3.2Q139.7 0.2 134.6 2.6"
    "Q133.2 3.3 132 3.9Q125 6 117.3 3Q113.7 1.5 110.85 -1.05Q108 -3.6 106.9 -7.1Q103.4 -18.3 108.2 -36.5"
    "Q110.2 -44.3 113.1 -51.7Q116 -59.1 117.35 -62.4Q118.7 -65.7 119.3 -66.95Q119.9 -68.2 120.6 -69.4"
    "Q122.3 -72.8 123.5 -74L124.7 -75.1Q124.9 -75.3 125.1 -75.35Q125.3 -75.4 125.6 -75.6Q126.4 -76.1 127.3 -76.3"
    "L128.7 -76.6H129.3Q132.2 -77 134.3 -75.4Q134.3 -75.3 134.5 -75.3L135.3 -74.6L135.6 -74.3L135.9 -73.9"
    "Q135.9 -73.8 135.95 -73.8Q136 -73.8 136 -73.7L136.1 -73.6V-73.4Q136.2 -73.4 136.2 -73.3V-73.2"
    "Q136.3 -73.1 136.4 -73.1V-73Q136.4 -72.9 136.45 -72.9Q136.5 -72.9 136.5 -72.85Q136.5 -72.8 136.6 -72.7"
    "V-72.6Q136.6 -72.5 136.7 -72.4ZM139.4 -5.8V-6.1Q139.3 -6 139.3 -5.3Q139.3 -5.6 139.4 -5.7Z"
)
# Gaps cut through the coloured letters (x, y, width, height in the lettering's space).
GAPS = [(106.0, -52.9, 68.4, 3.04), (8.5, -21.7, 51.3, 3.04), (85.5, -9.5, 85.5, 3.04)]
OUTLINE_WIDTH, INNER_WIDTH = 18.92, 12.21
BAND_STOPS = (0.42, 0.54)     # cyan above the first, violet to the second, pink below (of the path's height)
LETTER_SCALE, LETTER_ROTATE = 0.3277, -6.0
LETTER_SHIFT, LETTER_ORIGIN = (32.0, 34.0), (-85.45, 35.56)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def parse_path(d):
    """The path's subpaths as lists of points (quadratics flattened). Handles M L H V Q Z, absolute."""
    tokens = re.findall(r"[MLHVQZ]|-?\d*\.?\d+", d)
    subpaths, current, pos, i = [], [], (0.0, 0.0), 0
    cmd = None
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                if current:
                    subpaths.append(current)
                current = []
            continue
        if cmd == "M":
            if current:
                subpaths.append(current)
            pos = (float(tokens[i]), float(tokens[i + 1]))
            current = [pos]
            i += 2
            cmd = "L"          # further pairs after a move are lines
        elif cmd == "L":
            pos = (float(tokens[i]), float(tokens[i + 1]))
            current.append(pos)
            i += 2
        elif cmd == "H":
            pos = (float(tokens[i]), pos[1])
            current.append(pos)
            i += 1
        elif cmd == "V":
            pos = (pos[0], float(tokens[i]))
            current.append(pos)
            i += 1
        elif cmd == "Q":
            c = (float(tokens[i]), float(tokens[i + 1]))
            e = (float(tokens[i + 2]), float(tokens[i + 3]))
            for s in range(1, 9):
                t = s / 8.0
                u = 1 - t
                current.append((u * u * pos[0] + 2 * u * t * c[0] + t * t * e[0],
                                u * u * pos[1] + 2 * u * t * c[1] + t * t * e[1]))
            pos = e
            i += 4
        else:
            raise ValueError("unsupported path command " + str(cmd))
    if current:
        subpaths.append(current)
    return subpaths


def letter_transform(point):
    """A point of the lettering's space in the 64 unit art box."""
    x = (point[0] + LETTER_ORIGIN[0]) * LETTER_SCALE
    y = (point[1] + LETTER_ORIGIN[1]) * LETTER_SCALE
    a = math.radians(LETTER_ROTATE)
    return (LETTER_SHIFT[0] + x * math.cos(a) - y * math.sin(a),
            LETTER_SHIFT[1] + x * math.sin(a) + y * math.cos(a))


def to_canvas(point):
    """A point of the 64 unit art box in canvas texels."""
    k = ART / UNITS
    return (PAD + point[0] * k, PAD + point[1] * k)


def signed_area(poly):
    return sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly))) / 2


def offset_polygon(poly, d):
    """A convex polygon moved outward by d (inward when negative) with miter joins; a join past the miter
    limit is clamped to the limit's length (a bevel's reach)."""
    n = len(poly)
    sign = 1.0 if signed_area(poly) > 0 else -1.0
    normals = []
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        length = math.hypot(bx - ax, by - ay)
        normals.append((sign * (by - ay) / length, -sign * (bx - ax) / length))
    out = []
    for i in range(n):
        n1, n2 = normals[i - 1], normals[i]
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        scale = d / (1 + dot)
        mx, my = (n1[0] + n2[0]) * scale, (n1[1] + n2[1]) * scale
        reach = math.hypot(mx, my)
        if abs(d) > 0 and reach > MITER_LIMIT * abs(d):
            mx, my = mx * MITER_LIMIT * abs(d) / reach, my * MITER_LIMIT * abs(d) / reach
        out.append((poly[i][0] + mx, poly[i][1] + my))
    return out


# ---------------------------------------------------------------------------
# Coverage masks: N x N subsample grids of 0 / 1, rows top to bottom
# ---------------------------------------------------------------------------

def blank():
    return [bytearray(N) for _ in range(N)]


def fill_mask(polys, nonzero=True):
    """Subsamples inside the polygons (canvas texels), by winding number or by crossings."""
    mask = blank()
    edges = []
    for poly in polys:
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            if a[1] != b[1]:
                edges.append((a, b))
    for row in range(N):
        y = (row + 0.5) / SUPERSAMPLE
        crossings = []
        for a, b in edges:
            lo, hi = (a, b) if a[1] < b[1] else (b, a)
            if lo[1] <= y < hi[1]:
                x = lo[0] + (y - lo[1]) * (hi[0] - lo[0]) / (hi[1] - lo[1])
                crossings.append((x, 1 if b[1] > a[1] else -1))
        crossings.sort()
        winding, line = 0, mask[row]
        for k, (x, direction) in enumerate(crossings[:-1]):
            winding += direction
            inside = winding != 0 if nonzero else (k % 2 == 0)
            if inside:
                x0 = max(0, int(math.ceil(x * SUPERSAMPLE - 0.5)))
                x1 = min(N, int(math.ceil(crossings[k + 1][0] * SUPERSAMPLE - 0.5)))
                for col in range(x0, x1):
                    line[col] = 1
    return mask


def stroke_mask(polys, half):
    """Subsamples within `half` texels of any polygon edge (round joins, round caps)."""
    mask = blank()
    segments = []
    for poly in polys:
        for i in range(len(poly)):
            segments.append((poly[i], poly[(i + 1) % len(poly)]))
    for row in range(N):
        y = (row + 0.5) / SUPERSAMPLE
        diff = [0] * (N + 1)
        for a, b in segments:
            if y < min(a[1], b[1]) - half or y > max(a[1], b[1]) + half:
                continue
            lo, hi = None, None
            for end in (a, b):                                   # the two round caps
                dy = y - end[1]
                if abs(dy) <= half:
                    w = math.sqrt(half * half - dy * dy)
                    lo = end[0] - w if lo is None else min(lo, end[0] - w)
                    hi = end[0] + w if hi is None else max(hi, end[0] + w)
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length > 0:                                       # the body: the segment pushed sideways by half
                nx, ny = -dy / length * half, dx / length * half
                pts = [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]
                xs = []
                for i in range(4):
                    p, q = pts[i], pts[(i + 1) % 4]
                    if (p[1] <= y < q[1]) or (q[1] <= y < p[1]):
                        xs.append(p[0] + (y - p[1]) * (q[0] - p[0]) / (q[1] - p[1]))
                if len(xs) >= 2:
                    lo = min(xs) if lo is None else min(lo, min(xs))
                    hi = max(xs) if hi is None else max(hi, max(xs))
            if lo is None:
                continue
            x0 = max(0, int(math.ceil(lo * SUPERSAMPLE - 0.5)))
            x1 = min(N, int(math.ceil(hi * SUPERSAMPLE - 0.5)))
            if x1 > x0:
                diff[x0] += 1
                diff[x1] -= 1
        line, run = mask[row], 0
        for col in range(N):
            run += diff[col]
            if run > 0:
                line[col] = 1
    return mask


def intersect(a, b):
    return [bytearray(x & y for x, y in zip(ra, rb)) for ra, rb in zip(a, b)]


def subtract(a, b):
    return [bytearray(x & (1 - y) for x, y in zip(ra, rb)) for ra, rb in zip(a, b)]


# ---------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------

class Canvas:
    """Premultiplied accumulation per subsample, composited layer over layer."""

    def __init__(self):
        self.r = [[0.0] * N for _ in range(N)]
        self.g = [[0.0] * N for _ in range(N)]
        self.b = [[0.0] * N for _ in range(N)]
        self.a = [[0.0] * N for _ in range(N)]

    def paint(self, mask, color, alpha=1.0, colour_at=None):
        for row in range(N):
            line = mask[row]
            for col in range(N):
                if not line[col]:
                    continue
                c = colour_at(col, row) if colour_at else color
                keep = 1 - alpha
                self.r[row][col] = c[0] * alpha + self.r[row][col] * keep
                self.g[row][col] = c[1] * alpha + self.g[row][col] * keep
                self.b[row][col] = c[2] * alpha + self.b[row][col] * keep
                self.a[row][col] = alpha + self.a[row][col] * keep

    def resolve(self):
        """SIZE x SIZE straight RGBA texels."""
        out = []
        count = SUPERSAMPLE * SUPERSAMPLE
        for ty in range(SIZE):
            row = []
            for tx in range(SIZE):
                r = g = b = a = 0.0
                for sy in range(SUPERSAMPLE):
                    for sx in range(SUPERSAMPLE):
                        yy, xx = ty * SUPERSAMPLE + sy, tx * SUPERSAMPLE + sx
                        r += self.r[yy][xx]
                        g += self.g[yy][xx]
                        b += self.b[yy][xx]
                        a += self.a[yy][xx]
                if a > 0:
                    row.append((r / a, g / a, b / a, a / count))
                else:
                    row.append((0.0, 0.0, 0.0, 0.0))
            out.append(row)
        return out


def draw(canvas):
    def poly(points):
        return [to_canvas(p) for p in points]

    k = ART / UNITS
    # 1 triangle
    tri = poly(TRIANGLE)
    canvas.paint(fill_mask([tri]), INK)
    ring = fill_mask([offset_polygon(tri, 2.6 / 2 * k)])
    canvas.paint(subtract(ring, fill_mask([offset_polygon(tri, -2.6 / 2 * k)])), VIOLET)
    # 2 inner outlines
    for pts, color, width, opacity in ((INNER_VIOLET, VIOLET, 0.9, 0.9), (INNER_CYAN, CYAN, 0.9, 0.95)):
        p = poly(pts)
        ring = fill_mask([offset_polygon(p, width / 2 * k)])
        canvas.paint(subtract(ring, fill_mask([offset_polygon(p, -width / 2 * k)])), color, opacity)
    # 3 spikes: dark violet fill and 1.8 stroke, then black over the fill
    for spike in SPIKES:
        p = poly(spike)
        canvas.paint(fill_mask([offset_polygon(p, 1.8 / 2 * k)]), DEEP)
    for spike in SPIKES:
        canvas.paint(fill_mask([poly(spike)]), BLACK)

    # 4 lettering
    local = parse_path(LETTERS_D)
    letters = [[to_canvas(letter_transform(p)) for p in sub] for sub in local]
    scale = LETTER_SCALE * k
    canvas.paint(fill_mask(letters), DEEP)
    canvas.paint(stroke_mask(letters, OUTLINE_WIDTH / 2 * scale), DEEP)
    canvas.paint(fill_mask(letters), BLACK)
    canvas.paint(stroke_mask(letters, INNER_WIDTH / 2 * scale), BLACK)

    ys = [p[1] for sub in local for p in sub]
    top, bottom = min(ys), max(ys)
    cut = [[to_canvas(letter_transform(p)) for p in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
           for x, y, w, h in GAPS]
    inked = subtract(fill_mask(letters), fill_mask(cut))

    # Height of a subsample in the lettering's space: the transform is a rotation and a uniform scale.
    a = math.radians(LETTER_ROTATE)

    def local_y(col, row):
        cx, cy = (col + 0.5) / SUPERSAMPLE, (row + 0.5) / SUPERSAMPLE
        ux, uy = (cx - PAD) / k - LETTER_SHIFT[0], (cy - PAD) / k - LETTER_SHIFT[1]
        ly = (-ux * math.sin(a) + uy * math.cos(a)) / LETTER_SCALE     # rotate back by -a, unscale
        return ly - LETTER_ORIGIN[1]

    def band(col, row):
        t = (local_y(col, row) - top) / (bottom - top)
        if t < BAND_STOPS[0]:
            return CYAN
        if t < BAND_STOPS[1]:
            return VIOLET
        return PINK

    canvas.paint(inked, None, 1.0, band)


def bleed(texels):
    """Give every fully clear texel the colour of its nearest inked neighbour, a few passes out."""
    colours = [[(t[0], t[1], t[2]) if t[3] > 0 else None for t in row] for row in texels]
    for _ in range(3):
        grown = [row[:] for row in colours]
        for y in range(SIZE):
            for x in range(SIZE):
                if colours[y][x] is not None:
                    continue
                near = [colours[yy][xx] for yy in range(max(0, y - 1), min(SIZE, y + 2))
                        for xx in range(max(0, x - 1), min(SIZE, x + 2)) if colours[yy][xx] is not None]
                if near:
                    grown[y][x] = tuple(sum(c[i] for c in near) / len(near) for i in range(3))
        colours = grown
    return colours


def build():
    canvas = Canvas()
    draw(canvas)
    texels = canvas.resolve()
    colours = bleed(texels)
    rows = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            t = texels[y][x]
            c = colours[y][x] or (0, 0, 0)
            rows += bytes((int(round(c[2])), int(round(c[1])), int(round(c[0])), int(round(t[3] * 255))))
    return bytes(rows)


if __name__ == "__main__":
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures"))
    path = os.path.join(here, "icon_stu.tga")
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, SIZE, SIZE, 32, 0x28)
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(build())
    print(f"wrote {path} ({SIZE}x{SIZE}, {os.path.getsize(path)} bytes)")
