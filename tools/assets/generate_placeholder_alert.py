#!/usr/bin/env python3
"""Bake the STAY RAD sample alert: the Warrior Overpower pop up (generate_warrior_powerups.py) with a neutral synthwave sun in
place of the axe and STAY RAD for the title.

It is a placeholder for the classes that have no pop up alert yet, shown only as the config window's preview of the Alert scale
row (PlaceholderAlert.lua); it never plays in a fight. Everything but the emblem and the words is the Overpower alert's own code:
the Painter, the cut and dedupe of sprites, the title font and letter, the rune circle, the drain bar, the shelf packer and the TGA
writer all come from generate_warrior_powerups.py (read its docstring for the method), and draw_stayrad below is a port of that
file's draw_over, so the frame, the entrance (the circle draws itself, the runes light, the emblem slams down in ghost frames and
bites, a white ring snaps round the circle, a pink ring and sparks fly out), the held look (the circle turning a step at a time, the
pulse, the embers, a glint walking the emblem's rim, the word shaking now and then) and the amber and expiry looks are the same.

The differences from draw_over, all of them:
  * the emblem is a pixel sun drawn here (a disc in gold, amber, orange red, pink and violet bands with a dithered seam at each
    band, a highlight on its upper left and the classic stripes cut out of its lower half), in the 54 x 54 box the axe takes, so
    every position and the ghosts, the bounce and the dimming are the axe's;
  * the glint walks the sun's rim (draw_over walks the axe blade's edge); in amber the rim is outlined in amber, where draw_over
    outlines the blade;
  * the title is STAY RAD (the Warrior font gained a D for it) and its slash is skipped for the space;
  * no cast exit: the sample is never cast, so it has the sequences enter, held, amber and exp (frame counts at 30 Hz; the first
    frame of every sequence is a snapshot, the rest are deltas):

        enter   0.5 s     held   3.0 s (frames 15 to 104 of the window, not a loop: the module stays on its last frame)
        amber   1.5 s (the last 1.5 s of the 5 s window)     exp   the exit when the window runs out, 0.7 s

    The drain bar's fill is three 1 texel sprites (FILL_KEYS) that the module stretches to the real remaining time.

    python3 tools/assets/generate_placeholder_alert.py   (FS_ASSET_OUTPUT_DIR overrides the texture directory,
                                                          FS_ART_LUA_OUTPUT the manifest path, FS_ASSETS_DIR the folder that holds
                                                          generate_warrior_powerups.py)
Needs numpy and Pillow. Deterministic: the same source writes the same bytes.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("FS_ASSETS_DIR") or _HERE)
import generate_warrior_powerups as W  # noqa: E402  (the shared bake machinery)

GW, GH, MX, SPX, DT, EPS, AMBER = W.GW, W.GH, W.MX, W.SPX, W.DT, W.EPS, W.AMBER
K, IMP, AX, RC, WY = W.K, W.IMP, W.AX, W.RC, W.WY
jround, clamp, q4, obj = W.jround, W.clamp, W.q4, W.obj
TAU = math.pi * 2

TITLE = "STAY RAD"
SEQS = ("enter", "held", "amber", "exp")
# win, enter frames, held (first frame of the window, frames), amber (first frame, frames): Overpower's, to the frame
SPELL = dict(win=5.0, cast_at=3.0, enter=15, held=(15, 90), amber=(105, 45))
EXP_FRAMES = W.EXP_FRAMES

# ------------------------------------------------------------------------------------------------------------------------
# The emblem: a synthwave sun. Colours are Theme.lua's: COLOR_GOLD, COLOR_AMBER, COLOR_WARM, COLOR_HEALTH (the pink) and
# COLOR_BORDER (the violet), and the generator's pale amber for the highlight.
# ------------------------------------------------------------------------------------------------------------------------
SUN_R = 17
SUN_C = (27, 28)                        # the sun's centre in the axe's 54 x 54 box: (27, 28) + the box origin is the rune circle's centre
BANDS = ((-17, "#ffd23f"), (-10, "#ffb648"), (-3, "#ff3d1f"), (4, "#ff2e97"), (11, "#a855f7"))
SEAMS = (-10, -3, 4)                    # the first row of a band is dithered with the band above it
GAPS = ((3, 1), (7, 1), (10, 2), (13, 2), (16, 2))      # (first row, rows) cut out below the centre, thicker toward the bottom
LIGHT = "#fff0c8"
GLINT_ROWS = 2                          # the glint walks the rim down to this row below the centre (the first stripe is at 3)


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def sun_pixels():
    """(solid, rim): the pixels of the sun {(x, y): (r, g, b)} and the pixels of its round outline (before the stripes are cut)."""
    cx, cy = SUN_C
    disc = {(x, y) for y in range(cy - SUN_R - 1, cy + SUN_R + 2) for x in range(cx - SUN_R - 1, cx + SUN_R + 2)
            if (x - cx) ** 2 + (y - cy) ** 2 <= SUN_R * SUN_R + SUN_R}
    rim = {(x, y) for x, y in disc if any((x + dx, y + dy) not in disc for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}
    gap_rows = {r for first, n in GAPS for r in range(first, first + n)}
    solid = {}
    for x, y in sorted(disc):
        dy = y - cy
        if dy in gap_rows:
            continue
        band = max(i for i, (start, _) in enumerate(BANDS) if start <= dy)
        if dy in SEAMS and (x + y) % 2 == 0:
            band -= 1                   # a checker of the band above on the seam row: the 8 bit way to blend two flat colours
        c = BANDS[band][1]
        d = math.hypot(x - cx, y - cy)
        ang = math.degrees(math.atan2(x - cx, -(dy)))       # 0 = straight up, negative = the left
        if SUN_R - 2.2 < d <= SUN_R + 0.4 and -74 <= ang <= -40 and dy < 0:
            c = LIGHT                   # the highlight on the upper left rim
        solid[(x, y)] = _rgb(c)
    return solid, rim


def sun_image():
    """The emblem as an 8 bit RGBA array in the axe's 54 x 54 box."""
    solid, _ = sun_pixels()
    im = np.zeros((AX["H"], AX["W"], 4), np.uint8)
    for (x, y), (r, g, b) in solid.items():
        im[y, x] = (r, g, b, 255)
    return im


def rim_walks():
    """The rim pixels the glint walks and the rim the amber outline draws.

    Two lists, one for each side of the sun, from the top down to GLINT_ROWS below the centre, each ordered by its angle from the
    top so a glint travels along the arc (draw_over's AX_SIDES are the blade's edge sorted by row)."""
    solid, rim = sun_pixels()
    cx, cy = SUN_C
    on = sorted((p for p in rim if p in solid), key=lambda p: (p[1], p[0]))
    sides = []
    for sign in (1, -1):
        pts = [p for p in on if (p[0] - cx) * sign >= 0 and p[1] - cy <= GLINT_ROWS]
        pts.sort(key=lambda p: (math.atan2((p[0] - cx) * sign, -(p[1] - cy)), p))
        sides.append(pts)
    return on, sides


EMB = sun_image()
EDGE, SIDES = rim_walks()


# ------------------------------------------------------------------------------------------------------------------------
# The alert: draw_over with the sun and the words
# ------------------------------------------------------------------------------------------------------------------------
def draw_stayrad(p, st):
    e, out, ot = st["e"], st["out"], st["ot"]
    win = 5
    am = st["am"] and not out
    fade = 1.0
    if out == "exp":
        fade = q4(1 - ot / 0.6)
    if fade <= 0:
        return
    p.alpha = fade
    if not out and IMP <= e < IMP + 0.15:
        k = int(math.floor((e - IMP) / 0.025))
        p.tx = [3, -3, 2, -2, 1, -1][k] if k < 6 else 0
        p.ty = [-2, 2, -1, 1, 0, 0][k] if k < 6 else 0
    hot = K["am"] if am else K["rg"]
    CX, CY = RC[0], RC[1] + 2
    colr = K["am"] if am else K["cy"]
    dk = "#5a3a10" if am else "#16505e"
    # the rune circle draws itself, the runes light one by one, then it turns a step at a time and a pulse runs round it
    trace = 1.0 if out else clamp(e / 0.16)
    lit = max(0, 16 - int(math.floor(ot / 0.03))) if out == "exp" else 16 if out else int(math.floor(clamp((e - 0.12) / 0.3) * 16))
    rot = int(math.floor(max(0, e - 0.6) / 0.35))
    pulse = (e * 2.6) % TAU if (not out and e > 0.6) else None
    p.glow(1, lambda: W.rune_circle(p, trace, lit, rot, pulse, colr, dk, out == "exp" and ot > 0.08, 0))
    # the bite lights the circle: a flash, a white ring snaps round it once, a pink ring and sparks fly out, embers rise
    if not out and e >= IMP:
        k = e - IMP
        if k < 0.12:
            obj(p, "sr.flash", lambda: p.disc(CX, CY, jround(22 * (1 - k / 0.12)), f"rgba(255,240,235,{q4(1 - k / 0.12)})"), None, W.PIECES_DISC)
        if k < 0.2:
            def snap():
                p.ring_px(RC[0], RC[1], RC[2] + 1, K["wh"], 2)
                p.ring_px(RC[0], RC[1], RC[2] - 9, K["wh"], 1)
            obj(p, "sr.snap", lambda: p.glow(q4(1 - k / 0.2), snap), None, W.PIECES_RING)
        if k < 0.5:
            obj(p, "sr.ring", lambda: p.glow(q4(1 - k / 0.5), lambda: p.ring_px(CX, CY, jround(k / 0.5 * 60 / 2) * 2, K["pk"], 2)), None, W.PIECES_RING)
            for i in range(16):
                a = i * 2.4
                v = 34 + (i * 7) % 26
                x = CX + math.cos(a) * v * k * 2
                y = CY + math.sin(a) * v * k * 2 + 110 * k * k
                c = K["wh"] if i % 3 == 0 else K["am"] if i % 3 == 1 else K["rg"]
                obj(p, f"sr.spark{i}", lambda x=x, y=y, c=c: p.glow(q4(1 - k / 0.5), lambda: p.P(x, y, 2, 2, c)))
        if e > 0.5:
            for i in range(7):
                ph = (e * 0.8 + i * 0.14) % 1
                x = CX - 24 + (i * 13) % 48 + jround(math.sin(e * 4 + i) * 2)
                obj(p, f"sr.ember{i}", lambda i=i, ph=ph, x=x: p.glow(q4(1 - ph), lambda: p.P(x, CY + 18 - ph * 40, 1 + (i % 2), 1 + (i % 2), K["am"] if i % 2 else hot)))
    # the sun: slams straight down from above in ghost frames, bites, then holds; a glint walks each side of its rim
    w, h = AX["W"], AX["H"]
    if not out and e < IMP:
        pp = clamp(e / IMP)
        dy = jround(-70 * (1 - pp * pp))
        if pp > 0.35:
            for i in range(6):
                obj(p, f"sr.line{i}", lambda i=i: p.glow(0.6, lambda: p.line(AX["X"] + 12 + i * 6, AX["Y"] + dy - 30 + i * 3, AX["X"] + 12 + i * 6, AX["Y"] + dy + 4,
                                                                             K["cy"] if i % 2 else K["wh"], 1)))
        for n, (lag, al) in enumerate(((-18, .18), (-11, .3), (-5, .5))):
            obj(p, f"sr.ghost{n}", lambda lag=lag, al=al: p.glow(al, lambda: p.sprite_ink(EMB, 0, 0, w, h, AX["X"], AX["Y"] + dy + lag)))
        obj(p, "sr.sunIn", lambda: p.sprite_ink(EMB, 0, 0, w, h, AX["X"], AX["Y"] + dy))
    else:
        filt = ("gray", 0.6) if (out == "exp" and ot > 0.08) else None
        bounce = 1 if (not out and IMP <= e < IMP + 0.06) else 0

        def held():
            obj(p, "sr.sun", lambda: p.sprite_ink(EMB, 0, 0, w, h, AX["X"], AX["Y"] + bounce, filt), ("sun", bounce, filt, p.alpha, p.tx, p.ty))
            if not filt:
                if am:
                    obj(p, "sr.edge", lambda: [p.P(AX["X"] + x, AX["Y"] + bounce + y, 1, 1, K["am"]) for x, y in EDGE], ("edge", bounce, p.alpha, p.tx, p.ty))
                if not out and e > 0.5:
                    k = int(math.floor((e % 1.4) / 0.05))
                    for n, lst in enumerate(SIDES):
                        if k < len(lst):
                            x, y = lst[k]

                            def glint(x=x, y=y):
                                p.P(AX["X"] + x - 1, AX["Y"] + y, 3, 1, K["wh"])
                                p.P(AX["X"] + x, AX["Y"] + y - 1, 1, 3, K["wh"])
                            obj(p, f"sr.glint{n}", glint, ("glint", x, y, p.alpha, p.tx, p.ty))
        p.glow(1, held)
    # the word: slashed in diagonally, shakes, glints, splits on cast (the split is only the entrance here)
    base = W.PAL["dim"] if out == "exp" else (W.PAL["rageAflash"] if int(math.floor(e * 4)) % 2 else W.PAL["rageA"]) if am else W.PAL["rage"]

    def fn(i, ch, x, y, lw):
        d = 0.24 + 0.03 * i
        pr = clamp((e - d) / 0.12)
        if not out and e < d:
            return None
        pp = math.floor(pr * 3) / 3

        def split(ci, j):
            return 0 if (ci * 1.0 + j * 1.2) < 5.4 else 1
        jx = jy = 0
        if not out:
            if pr >= 1 and e - d - 0.12 < 0.18:
                jx = 2 if int(math.floor(e * 40)) % 2 else -2
                jy = int(math.floor(e * 40)) % 3 - 1
            elif e > 0.5 and (e % 1.2) < 0.1:
                jx = 1 if int(math.floor(e * 40)) % 2 else -1
        gp = ((e % 1.8) / 0.6) * 130 - 14

        def cell(ci, j):
            hh = split(ci, j)
            dx = dy2 = 0
            if pr < 1:
                dx = (1 - pp) * 16 if hh else -(1 - pp) * 16
                dy2 = (1 - pp) * 8 if hh else -(1 - pp) * 8
            gl = (not out) and e > 0.6 and abs((x + ci * 2 + j * 1.5) - gp) < 4
            return (jround(dx), jround(dy2), K["wh"] if gl else None)
        return {"x": x + jx, "y": y + jy + (int(math.floor(ot / 0.15)) if out == "exp" else 0), "pal": base, "cell": cell}
    x0, wd = W.word(p, "sr", TITLE, WY, fn)
    if not out:
        lay, lw_ = W.layout(TITLE)
        for i, (ch, lx, lw) in enumerate(lay):
            if ch == " ":
                continue
            d = 0.24 + 0.03 * i
            pr = (e - d) / 0.12
            if 0.55 < pr < 1.1:
                xl = jround(MX - lw_ / 2) + lx
                obj(p, f"sr.slash{i}", lambda xl=xl, lw=lw: p.line(xl - 2, WY + 15, xl + lw + 2, WY - 2, K["wh"], 1))
    if e >= 0.4 and (not out or out == "exp"):
        W.rune(p, "sr.runeL", x0 - 11, WY + 4, W.RUNE_T, K["am"] if am else K["cy"])
        W.rune(p, "sr.runeR", x0 + wd + 7, WY + 4, W.RUNE_T, K["am"] if am else K["cy"])
    if e >= 0.4:
        W.drain(p, win, clamp((e - 0.4) / 0.15), out == "exp" or st["am"], out == "exp")


# ------------------------------------------------------------------------------------------------------------------------
# States and the bake
# ------------------------------------------------------------------------------------------------------------------------
def states():
    h0, hn = SPELL["held"]
    a0, an = SPELL["amber"]
    return {
        "enter": [W.live_state(SPELL, f, False) for f in range(SPELL["enter"])],
        "held": [W.live_state(SPELL, f, False) for f in range(h0, h0 + hn)],
        "amber": [W.live_state(SPELL, f, True) for f in range(a0, a0 + an)],
        "exp": [W.leave_state(SPELL, "exp", j) for j in range(EXP_FRAMES)],
    }


def bake():
    p = W.Painter()
    seqs = states()
    built = {}
    for s in SEQS:
        frames = []
        for st in seqs[s]:
            p.reset()
            draw_stayrad(p, st)
            frames.append(list(p.items))
        built[s] = frames
    order = W.slot_order([fr for s in SEQS for fr in built[s]])
    slot = {k: i + 1 for i, k in enumerate(order)}
    fill = [slot.get(k) for k in W.FILL_KEYS]
    deltas = {}
    for s in SEQS:
        prev, out = {}, []
        for n, fr in enumerate(built[s]):
            cur = {slot[k]: (sid, x, y) for k, sid, x, y in fr}
            flat = []
            if n == 0:
                for sl in sorted(cur):
                    flat += [sl, *cur[sl]]
            else:
                for sl in sorted(set(prev) | set(cur)):
                    if prev.get(sl) != cur.get(sl):
                        flat += [sl, *cur.get(sl, (0, 0, 0))]
            out.append(flat)
            prev = cur
        deltas[s] = out
    return p, dict(slots=len(order), fill=fill, seqs=deltas, order=order, built=built, win=SPELL["win"])


def lua_manifest(p, atlases, d):
    L = [
        "-- Forever STUwave: the STAY RAD sample alert's sprite manifest and frame lists.",
        "-- GENERATED by tools/assets/generate_placeholder_alert.py; do not edit (placeholderalert-harness.py checks it).",
        "-- ATLAS[n] = { file, w, h }. SPRITE[id] = { atlas, tx, ty, w, h }: a texel rect in its atlas; one texel is one sprite px.",
        "-- SPELL.stayrad.seqs[name][frame] = flat list of { slot, sprite, x, y } (x, y = sprite px on the 150 x 96 canvas; sprite 0 hides",
        "-- the slot). The first frame of each sequence is a snapshot, the rest are deltas against the frame before. Slots are",
        "-- in back to front order. FILL slots are the drain bar's fill: their sprite is one texel and the module stretches it.",
        "",
        "local _, FS = ...",
        "",
        "FS.PlaceholderAlertArt = {",
        f"    SPX = {SPX}, GW = {GW}, GH = {GH}, MX = {MX},",
        f"    AMBER = {AMBER}, BAR_FILL = {W.BAR_W - 2},",
        "    ATLAS = {",
    ]
    for n, (w, h, _) in enumerate(atlases, 1):
        L.append(f'        {{ file = "placeholder_alert_{n}", w = {w}, h = {h} }},')
    L += ["    },", "    SPRITE = {"]
    where = {}
    for n, (w, h, placed) in enumerate(atlases, 1):
        for sid, tx, ty in placed:
            where[sid] = (n, tx, ty)
    for sid in range(1, len(p.sprites) + 1):
        n, tx, ty = where[sid]
        sw, sh, _ = p.sprites[sid - 1]
        L.append(f"        {{ {n}, {tx}, {ty}, {sw}, {sh} }},")
    L += ["    },", "    SPELL = {", "        stayrad = {",
          f"            win = {int(SPELL['win'])}, slots = {d['slots']}, fill = {W.lua_list(d['fill'])},",
          f"            enterFrames = {SPELL['enter']}, heldStart = {SPELL['held'][0]}, amberStart = {SPELL['amber'][0]},",
          "            seqs = {"]
    for s in SEQS:
        L.append(f"                {s} = {{")
        for flat in d["seqs"][s]:
            L.append("                    " + W.lua_list(flat) + ",")
        L.append("                },")
    L += ["            },", "        },", "    },", "}", ""]
    return "\n".join(L)


def verify(p, atlases, d):
    for w, h, _ in p.sprites:
        assert 1 <= w <= GW and 1 <= h <= GH
    for s in SEQS:
        for fr in d["built"][s]:
            for key, sid, x, y in fr:
                w, h, _ = p.sprites[sid - 1]
                assert 0 <= x and 0 <= y and x + w <= GW and y + h <= GH, (s, key)
    assert all(d["fill"]), "the fill slots must all be used"
    assert d["fill"] == sorted(d["fill"]) and d["fill"][-1] - d["fill"][0] == 2, "fill slots must be adjacent and in order"
    for w, h, _ in atlases:
        assert w <= W.ATLAS_MAX and h <= W.ATLAS_MAX
    # the sun sits on the rune circle's centre: the axe's box origin plus the sun's centre
    assert (AX["X"] + SUN_C[0], AX["Y"] + SUN_C[1]) == (RC[0], RC[1]), "the sun is off the rune circle's centre"


def main():
    root = os.path.join(_HERE, "..", "..")
    here = os.environ.get("FS_ASSET_OUTPUT_DIR", os.path.join(root, "forever-stuwave", "Media", "Textures"))
    default_lua = (os.path.join(here, "PlaceholderAlertArt.lua") if "FS_ASSET_OUTPUT_DIR" in os.environ
                   else os.path.join(root, "forever-stuwave", "Modules", "CombatHud", "PlaceholderAlertArt.lua"))
    lua = os.environ.get("FS_ART_LUA_OUTPUT", default_lua)
    p, d = bake()
    atlases = W.pack(p.sprites)
    verify(p, atlases, d)
    total = sum(w * h for w, h, _ in p.sprites)
    print(f"{len(p.sprites)} sprites, {total} px, {len(atlases)} atlas(es): " + ", ".join(f"{w}x{h}" for w, h, _ in atlases))
    print(f"  stayrad: {d['slots']} slots, " + ", ".join(f"{s} {len(d['seqs'][s])}f/{sum(len(f) for f in d['seqs'][s]) // 4} deltas" for s in SEQS))
    if "--stats" in sys.argv:
        return
    os.makedirs(here, exist_ok=True)
    for n, atlas in enumerate(atlases, 1):
        W.write_tga(os.path.join(here, f"placeholder_alert_{n}.tga"), atlas, p.sprites)
    with open(lua, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(lua_manifest(p, atlases, d))
    print(f"wrote {lua}")


if __name__ == "__main__":
    main()
