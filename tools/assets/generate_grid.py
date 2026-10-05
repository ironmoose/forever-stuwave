#!/usr/bin/env python3
"""Bakes grid.tga: the synthwave perspective floor that sits behind the action
bars, matching mockups/full-ui-layout.html rather than approximating it.

WoW cannot do CSS 3D transforms, so the mockup's construction is reproduced by
inverse-mapping every texture pixel back through the same transform the browser
applies and asking "is this pixel on a grid line". The mockup builds the grid
from THREE stacked layers (full CSS in mockups/SPEC-grid.txt):

  .gridgrad    violet radial wash + vertical gradient, below the horizon
  .gridlines   cyan VERTICAL + pink HORIZONTAL lines, rotateX(76deg) under
               perspective:520px with perspective-origin 50% 0%
  .gridhorizon a 2px WHITE bar with a heavy cyan bloom -- the horizon itself

The previous grid.tga had none of the perspective convergence, no pink
horizontals and no glowing horizon, which is what "missing the coolest parts"
referred to.

CSS transform chain, reproduced exactly
---------------------------------------
Working in .gridwrap coordinates (W x H = the whole texture):

  .gridlines spans x in [-0.60W, 1.60W], y in [0.35H, 1.60H]
  transform-origin: top center      -> (0.5W, 0.35H)
  perspective-origin: 50% 0%        -> (0.5W, 0)
  transform: rotateX(76deg)

For a plane point (u, v), with dv = v - 0.35H and theta = 76deg, CSS rotateX
gives y' = dv*cos(theta), z' = dv*sin(theta) (+z is toward the viewer, so the
bottom of the floor swings toward the camera and is magnified -- a receding
floor). The perspective divide about the perspective-origin is then:

  scale = d / (d - z')
  sx    = 0.5W + (u - 0.5W) * scale
  sy    = (0.35H + dv*cos(theta)) * scale

Rasterising needs the inverse. Solving the sy equation for dv:

  sy*(d - dv*s) = (a + dv*c)*d        where a = 0.35H, c = cos, s = sin
  dv = d*(sy - a) / (c*d + sy*s)

then scale follows and u = 0.5W + (sx - 0.5W)/scale. Pixels above the horizon
(dv <= 0) or past the vanishing point are simply not on the floor.

On the one resolution-dependent constant
----------------------------------------
The mockup hardcodes `perspective: 520px` in CSS pixels while the grid element
itself is sized as a percentage of the planner canvas, so the rendered look
genuinely changes with browser window size -- there is no single pixel-exact
answer to match. PERSPECTIVE_OVER_HEIGHT below pins the ratio that actually
governs the shape, derived for a typical planner canvas (screen element approx
1600px wide for the 2560px virtual screen, making the 183px-tall grid section
render about 114px tall, so 520/114 ~= 4.5). Line DENSITY has the same
dependency, hence CSS_CANVAS_W. Both are named and isolated here: if Parker
says the convergence or the line spacing reads wrong against the mockup, these
two numbers are the tuning surface and nothing else needs to move.

Pure stdlib except numpy, which the repo already depends on; numpy keeps the
inverse map and the 3x supersample readable and fast. Output matches the other
generators: 18-byte header, image type 2, descriptor 0x28 (top-left origin,
8 alpha bits), BGRA top-to-bottom, no footer.

    python generate_grid.py
"""

import os
import struct

import numpy as np

# --- output -----------------------------------------------------------------
# WoW silently refuses to render a file texture whose dimensions are not powers
# of two. The first version of this was 2048x146 -- chosen to match the frame's
# 2560x183 aspect -- and drew absolutely nothing in game, with no error. Every
# other texture in media/ is power-of-two (128x128, 4x128, 64x64); this one has
# to be too.
#
# So the texture is 2048x256, but the perspective is still solved for the shape
# the frame ACTUALLY displays (FS.Layout.grid, 2560x183). DISPLAY_H is that
# aspect expressed at our texture width; the raster samples display space and
# writes it stretched across 256 rows, which WoW then squashes back to 183 when
# it fills the frame. Net result: correct geometry on screen, legal dimensions
# on disk.
OUT_W = 2048
OUT_H = 256
SUPERSAMPLE = 3

GRID_FRAME_W = 2560.0   # FS.Layout.grid.w
GRID_FRAME_H = 183.0    # FS.Layout.grid.h
DISPLAY_H = OUT_W * (GRID_FRAME_H / GRID_FRAME_W)

# --- transform (from the CSS above) -----------------------------------------
ROTATE_X_DEG = 76.0
HORIZON_FRAC = 0.35          # .gridlines top / .gridhorizon top
PLANE_LEFT = -0.60           # .gridlines left:-60%
PLANE_RIGHT = 1.60           # .gridlines right:-60%  -> extends to 160%
PLANE_BOTTOM = 1.60          # .gridlines bottom:-60%
PERSPECTIVE_OVER_HEIGHT = 4.5

# --- line density (CSS px, converted via CSS_CANVAS_W) ----------------------
CSS_CANVAS_W = 1600.0        # rendered width of the 2560px virtual screen
VERT_PERIOD_CSS = 46.0       # repeating-linear-gradient(90deg, ... 2px 46px)
VERT_WIDTH_CSS = 2.0
HORIZ_PERIOD_CSS = 40.0      # repeating-linear-gradient(0deg, ... 2px 40px)
HORIZ_WIDTH_CSS = 2.0

# --- palette (exact values from the mockup CSS) -----------------------------
CYAN = (34, 224, 255)        # rgba(34,224,255,.95) verticals
PINK = (255, 46, 151)        # rgba(255,46,151,.9) horizontals
VERT_ALPHA = 0.95
HORIZ_ALPHA = 0.90
GRAD_TOP = (12, 6, 32)       # #0c0620
GRAD_MID = (27, 11, 48)      # #1b0b30
GRAD_BOT = (37, 15, 66)      # #250f42
GRAD_OPACITY = 0.60          # .gridgrad opacity:.6
VIOLET = (124, 58, 237)      # radial-gradient(... rgba(124,58,237,.35) ...)
VIOLET_ALPHA = 0.35
HORIZON_GLOW_CYAN = (34, 224, 255)


def _plane_coords(sx, sy, w, h):
    """Inverse of the CSS transform: screen pixel -> (u, v) on the floor plane.

    Returns (u, dv, on_plane) where dv is depth below the horizon in plane
    space. on_plane is False above the horizon and beyond the vanishing point.
    """
    theta = np.radians(ROTATE_X_DEG)
    c, s = np.cos(theta), np.sin(theta)
    a = HORIZON_FRAC * h
    d = PERSPECTIVE_OVER_HEIGHT * h

    denom = c * d + sy * s
    # denom == 0 is the vanishing point; guard so the divide is quiet.
    safe = np.where(np.abs(denom) < 1e-9, 1e-9, denom)
    dv = d * (sy - a) / safe

    z = dv * s
    scale_denom = d - z
    ok = (dv > 0) & (scale_denom > 1e-6) & (dv <= PLANE_BOTTOM * h)
    scale = d / np.where(scale_denom > 1e-6, scale_denom, 1e-6)

    u = 0.5 * w + (sx - 0.5 * w) / scale
    on_plane = ok & (u >= PLANE_LEFT * w) & (u <= PLANE_RIGHT * w)
    return u, dv, on_plane


def _line_mask(coord, period, width):
    """Coverage in [0,1] for a repeating line pattern, with 1px soft edges so
    the supersampled result does not alias into dashes at the horizon."""
    phase = np.mod(coord, period)
    dist = np.minimum(phase, period - phase)
    return np.clip((width * 0.5 + 0.5 - dist), 0.0, 1.0)


def build_rgba():
    w, rows = OUT_W * SUPERSAMPLE, OUT_H * SUPERSAMPLE
    ys, xs = np.mgrid[0:rows, 0:w]
    sx = (xs + 0.5).astype(np.float64)

    # Every geometric term below works in DISPLAY space (the 2560x183 shape the
    # frame is drawn at), not texture space, so the perspective is right on
    # screen rather than right on disk.
    h = DISPLAY_H * SUPERSAMPLE
    sy = (ys + 0.5).astype(np.float64) * (h / rows)

    px_per_css = (OUT_W * SUPERSAMPLE) / CSS_CANVAS_W
    vert_period = VERT_PERIOD_CSS * px_per_css
    vert_width = VERT_WIDTH_CSS * px_per_css
    horiz_period = HORIZ_PERIOD_CSS * px_per_css
    horiz_width = HORIZ_WIDTH_CSS * px_per_css

    rgb = np.zeros((rows, w, 3), dtype=np.float64)
    alpha = np.zeros((rows, w), dtype=np.float64)

    horizon_y = HORIZON_FRAC * h

    # --- .gridgrad: vertical gradient + violet radial, below the horizon ----
    below = sy >= horizon_y
    t = np.clip((sy - horizon_y) / max(h - horizon_y, 1.0), 0.0, 1.0)
    # linear-gradient(180deg, #0c0620 0%, #1b0b30 60%, #250f42 100%)
    grad = np.zeros((rows, w, 3))
    lo = t < 0.60
    for ch in range(3):
        first = GRAD_TOP[ch] + (GRAD_MID[ch] - GRAD_TOP[ch]) * (t / 0.60)
        second = GRAD_MID[ch] + (GRAD_BOT[ch] - GRAD_MID[ch]) * ((t - 0.60) / 0.40)
        grad[:, :, ch] = np.where(lo, first, second)

    # radial-gradient(120% 140% at 50% 0%, rgba(124,58,237,.35), transparent 60%)
    rx = (sx - 0.5 * w) / (1.20 * w * 0.5)
    ry = (sy - 0.0) / (1.40 * h)
    rr = np.sqrt(rx * rx + ry * ry)
    violet_a = np.clip(1.0 - rr / 0.60, 0.0, 1.0) * VIOLET_ALPHA
    for ch in range(3):
        grad[:, :, ch] = grad[:, :, ch] * (1 - violet_a) + VIOLET[ch] * violet_a

    grad_a = np.where(below, GRAD_OPACITY, 0.0)
    rgb = grad * grad_a[:, :, None]
    alpha = grad_a.copy()

    # --- .gridlines: cyan verticals + pink horizontals on the tilted plane --
    u, dv, on_plane = _plane_coords(sx, sy, w, h)
    vert = _line_mask(u, vert_period, vert_width) * VERT_ALPHA
    horiz = _line_mask(dv, horiz_period, horiz_width) * HORIZ_ALPHA
    vert = np.where(on_plane, vert, 0.0)
    horiz = np.where(on_plane, horiz, 0.0)

    for cov, color in ((horiz, PINK), (vert, CYAN)):
        for ch in range(3):
            rgb[:, :, ch] = rgb[:, :, ch] * (1 - cov) + color[ch] * cov
        alpha = alpha * (1 - cov) + cov

    # --- .gridhorizon: white 2px bar + 0 0 12px 3px and 0 0 28px 8px bloom --
    dist = np.abs(sy - horizon_y)
    core_half = 1.0 * px_per_css
    core = np.clip(core_half + 0.5 - dist, 0.0, 1.0)
    inner = np.exp(-((dist / (12.0 * px_per_css)) ** 2)) * 0.85
    outer = np.exp(-((dist / (28.0 * px_per_css)) ** 2)) * 0.50

    for bloom in (outer, inner):
        for ch in range(3):
            rgb[:, :, ch] = rgb[:, :, ch] * (1 - bloom) + HORIZON_GLOW_CYAN[ch] * bloom
        alpha = np.maximum(alpha, bloom)
    for ch in range(3):
        rgb[:, :, ch] = rgb[:, :, ch] * (1 - core) + 255.0 * core
    alpha = np.maximum(alpha, core)

    # --- downsample the supersample --------------------------------------
    rgb = rgb.reshape(OUT_H, SUPERSAMPLE, OUT_W, SUPERSAMPLE, 3).mean(axis=(1, 3))
    alpha = alpha.reshape(OUT_H, SUPERSAMPLE, OUT_W, SUPERSAMPLE).mean(axis=(1, 3))

    out = np.zeros((OUT_H, OUT_W, 4), dtype=np.uint8)
    out[:, :, 0] = np.clip(rgb[:, :, 2], 0, 255)  # B
    out[:, :, 1] = np.clip(rgb[:, :, 1], 0, 255)  # G
    out[:, :, 2] = np.clip(rgb[:, :, 0], 0, 255)  # R
    out[:, :, 3] = np.clip(alpha * 255.0, 0, 255)
    return out


def write_tga(path, bgra):
    header = struct.pack(
        "<BBBHHBHHHHBB",
        0, 0, 2, 0, 0, 0, 0, 0, OUT_W, OUT_H, 32, 0x28,
    )
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(bgra.tobytes())


def main():
    path = os.path.join(os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "forever-stuwave", "Media", "Textures")), "grid.tga")
    write_tga(path, build_rgba())
    print(f"wrote {path} ({OUT_W}x{OUT_H}, {os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
