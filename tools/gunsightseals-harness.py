#!/usr/bin/env python3
"""Runs the real GunsightSeals.lua (the Paladin's Seal Chamber CHROME of the Gunsight HUD) headless against a mock WoW API.

GunsightSeals.lua is the static layout of drawSealChamber in
mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html (the Paladin's seat of the "dot" piece,
mockup line 2361: CLS==='pl' ? drawSealChamber). It hangs off the piece frame GunsightDots.lua registers
and draws nothing for it on a class-slot profile. The checks pin:

  * constants: every number the file draws with is parsed back out of drawSealChamber (the chamber frame,
    the 0 to 30 s ruler, the lens, the glyph, the band, the tube, the NO SEAL labels and the Judgement lane),
    plus the seal table (name, colour, Judgement debuff length) and the media sizes read from the baked
    TGA headers and their generators, so a mockup edit or a re-bake fails here instead of drifting;
  * the gate: nothing at file load, nothing when the gunsight is disabled, and NOTHING for a Warlock, a
    Priest, a class with no profile or a dots-plus-seals profile (the whole drawn tree of the DoT piece is
    identical with and without this file);
  * the Paladin build: a child of the "dot" piece frame (so the console's dot key shows and hides it) and
    not of the target gate (the chamber is drawn with no target), every part seated at its mockup image
    coordinates at two screen heights;
  * the look follows FS.Hud's state.seal: each of the seven keys gets its glyph file, tint, name, colour
    and caption; false is the NO SEAL look; nil, a secret, garbage and an unmapped key are an UNKNOWN
    chamber that draws no seal and no NO SEAL cry; a repaint is written only when the look changes;
  * the piece: subscribed to FS.Hud only while the "dot" piece is on, unsubscribed on hide, a stale
    push after the hide is inert, a saved-off piece is never subscribed;
  * the v1 drops are absent: no animation group, no turning arcs (the Judgement ring is a second arcs file,
    hidden at rest), no judge-chip glyph, no scan sweep or scanlines, no aura API read;
  * the LIVE layer (lane 8), driven from Hud state with the mock clock: the drain fill, tip bar and tip dot
    follow the seal's remaining time (out of 30 s, hidden at 0.05 s and for an unreadable time), the countdown
    and its S, the RESEAL band at 3 s, the strike flicker after a cast (and a recast), the expiring dropouts
    in the last 5 s, the NO SEAL pulse (in combat only), the Judgement ring, the expiry flip to NO SEAL by the
    chamber itself, golden values from the mockup's own sealNeon / pulse / fill functions run under node, a
    secret time never read, and ONE cheap OnUpdate that exists only while something animates, writes only
    the fill height on a steady tick and allocates nothing;
  * the Judgement lane, live (lane 9), from state.judged with the mock clock: the bar and chip against the 0 to 40 s axis
    at several remaining times for 40 s and 10 s debuffs, the colour per seal key (the seal it was cast under), the empty,
    unknown, unreadable and expired lanes, a target change switching the lane, the landing flash, the chip's spell icon
    (C_Spell.GetSpellTexture, the legacy global, every unusable answer), the flat tint on a client without gradients, the
    ticker idle rules, reduced motion, the quarter pixel writes, a rescale, and the static secret guards on the new reads.

The mock is strict (a widget method it does not define fails as a nil call). Theme and the FrameHelpers
aura tile are STUBS here (their own harnesses cover the real ones); the real Layout.lua, Gunsight.lua,
HudProfiles.lua and GunsightDots.lua are loaded, and the mock, the Hud stub and the Lua prelude are
gunsightdots-harness.py's own.

    python3 tools/gunsightseals-harness.py

Exit 0 = every check passed. GUNSIGHTSEALS_LUA=<path> runs another file in place of GunsightSeals.lua.
"""

from __future__ import annotations

import importlib.util
import os
import re
import struct
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent
MEDIA = ADDON / "media"
SEALS = Path(os.environ.get("GUNSIGHTSEALS_LUA") or ADDON / "GunsightSeals.lua")
TOC = ADDON / "ForeverSynthwave.toc"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DOTS_H = _load("gunsightdots_harness", "gunsightdots-harness.py")
_m = DOTS_H._m
lua_value = DOTS_H.lua_value
MOCKUP = DOTS_H.MOCKUP


def tga_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:18]
    return struct.unpack("<HH", head[12:16])


def glow_half_radius(path: Path) -> float:
    """glow_round.tga is a radial glow: the radius, as a fraction of the half size, at which the alpha along the middle row
    falls to half of its centre value (the tip dot is sized so that radius is the mockup's 3 px disc)."""
    d = path.read_bytes()
    w, h = struct.unpack("<HH", d[12:16])
    bpp, desc = d[16], d[17]
    if d[2] != 2 or bpp != 32:
        sys.exit("glow_round.tga: expected an uncompressed 32 bit TGA")
    off = 18 + d[0]
    row = h // 2 if desc & 0x20 else h - 1 - h // 2
    alpha = [d[off + (row * w + x) * 4 + 3] for x in range(w)]
    mid = w // 2
    half = alpha[mid] / 2
    for x in range(mid, w - 1):
        if alpha[x] >= half > alpha[x + 1]:
            frac = (alpha[x] - half) / (alpha[x] - alpha[x + 1])
            return (x - mid + frac) / (w / 2)
    sys.exit("glow_round.tga: the alpha never falls to half")


def font_metrics() -> dict:
    """What the chamber's text seating depends on, read out of the font file the addon wears (Mononoki Bold, the face
    Theme.FONT_MONO names): the monospace advance as a fraction of the size, and how far the middle of a line box sits above
    its baseline when the engine builds the box from the hhea ascender and descender ((ascender + descender) / 2, descender
    negative). Not measured in game."""
    d = (MEDIA.parent / "fonts" / "MononokiNerdFontMono-Bold.ttf").read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", d[4:6])[0]):
        tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i:28 + 16 * i])
        tables[tag.decode()] = off
    upm = struct.unpack(">H", d[tables["head"] + 18:tables["head"] + 20])[0]
    asc, desc = struct.unpack(">hh", d[tables["hhea"] + 4:tables["hhea"] + 8])
    adv = struct.unpack(">H", d[tables["hmtx"]:tables["hmtx"] + 2])[0]
    return dict(CAP=(asc + desc) / 2 / upm, MONO_ADV=adv / upm)


def mockup_seals() -> dict:
    """Everything drawSealChamber owns, read out of the mockup (and the media generators)."""
    src = MOCKUP.read_text(encoding="utf-8")
    base = DOTS_H._load_gunsight_harness().mockup_constants()
    body = _m(r"(?s)function drawSealChamber\(vv,t\)\{(.*?)\n\}\n\n/\* Paladin rungs", src,
              "the drawSealChamber body").group(1)

    def g(pattern: str, what: str, text: str = body) -> tuple:
        return _m(pattern, text, what).groups()

    def fl(x: str) -> float:
        return float(x)

    sc_w, sc_c, tx_dx, tw, gx, gy, gr = (int(v) for v in g(
        r"var SC=\{x:DOT_AX,y:FR_T,w:(\d+),h:FR_B-FR_T,c:(\d+)\},SC_TX=DOT_AX\+(\d+),SC_TW=(\d+),SC_GX=(\d+),SC_GY=(\d+),SC_GR=(\d+);",
        "the SC / SC_TX / SC_GX constants", src))
    jl_x, jl_ax = (int(v) for v in g(r"var JL_X=(\d+),JL_AX=(\d+);", "JL_X / JL_AX", src))
    jl_max = int(g(r"function jY\(s\)\{return BOT-s/(\d+)\*\(BOT-TOP\);\}", "jY scale", src)[0])

    hdr_y, hdr_a = g(r"header\('SEAL',DOT_AX,(\d+),no\?K\.red:col,(\.\d+)\)", "the SEAL header")
    judged_dx, judged_y, judged_a = g(
        r"header\('JUDGED',JL_X-(\d+),(\d+),st\.jrem>0\?col:K\.muted,st\.jrem>0\?\.9:(\.\d+)\)", "the JUDGED header")
    plate_no, plate_a, pr, pg, pb, plate_fill = g(
        r"chamfer\(SC\.x,SC\.y,SC\.w,SC\.h,SC\.c\);A\(no\?(\.\d+):(\.\d+)\);ctx\.fillStyle='rgba\((\d+),(\d+),(\d+),(\.\d+)\)'",
        "the chamber plate")
    rad_r0, rad_pad, rad_a = g(
        r"createRadialGradient\(SC_GX,SC_GY,(\d+),SC_GX,SC_GY,SC_GR\+(\d+)\);g\.addColorStop\(0,rgba\(col,(\.\d+)\)\)",
        "the radial wash")
    edge_a0, edge_a1, glow_k0, glow_k1a, glow_k1b = g(
        r"A\((\.\d+)\+(\.\d+)\*neon\);glow\(col,(\.\d+)\+(\.\d+)\*neon\*(\.\d+)\)", "the seal edge")
    no_edge_a0, no_edge_a1 = g(r"A\((\.\d+)\+(\.\d+)\*u\);glow\(K\.red,u\)", "the NO SEAL edge")
    maj, maj_len, min_len, tick_a = g(
        r"tick\(DOT_AX,y,s%(\d+)===0\?(\d+):(\d+),-1,K\.violet,(\.\d+)\);", "the ruler ticks")
    max_s = int(g(r"for\(s=0;s<=(\d+);s\+\+\)\{\s*y=secY\(s\);", "the ruler span")[0])
    label_dx, label_dy, label_size, label_no, label_a = g(
        r"text\(String\(s\),DOT_AX\+(\d+),y\+(\d+),(\d+),K\.fg,no\?(\.\d+):(\.\d+),'left'\)", "the ruler labels")
    band_s = int(g(r"yb=secY\((\d+)\);", "the band seconds")[0])
    band_fill, band_pl = g(r"A\((\.\d+)\+(\.\d+)\*pl\);ctx\.fillStyle=K\.amber;ctx\.fillRect\(SC\.x,yb,SC\.w,BOT-yb\)", "the band fill")
    dash_on, dash_off, band_pad, band_top_a = g(
        r"setLineDash\(\[(\d+),(\d+)\]\);hline\(yb,SC\.x\+(\d+),SC\.x\+SC\.w-\d+,K\.amber,(\.\d+)\)", "the band top")
    band_bot_a, band_bot_w = g(
        r"hline\(BOT,SC\.x\+\d+,SC\.x\+SC\.w-\d+,K\.amber,(\.\d+),LW\*([\d.]+)\)", "the band foot")
    reseal_dy, reseal_size, reseal_in0, reseal_in1, reseal_a = g(
        r"text\('RESEAL',SC_GX,\(yb\+BOT\)/2\+([\d.]+),(\d+),K\.amber,inBand\?(\.\d+)\+(\.\d+)\*\(reduce\?1:u\):(\.\d+),'center'\)", "RESEAL")
    tube_no_a, tube_a = g(r"ctx\.fillStyle=no\?rgba\(K\.steel,(\.\d+)\):rgba\(tcol,(\.\d+)\)", "the tube track")
    rung_from, rung_to, rung_step, rung_a = g(
        r"for\(s=(\d+);s<(\d+);s\+=(\d+)\)hline\(secY\(s\),SC_TX-SC_TW/2,SC_TX\+SC_TW/2,K\.bg,(\.\d+),LW\)", "the rungs")
    out_no_a, out_a, out_w = g(
        r"A\(no\?(\.\d+):(\.\d+)\);ctx\.strokeStyle=no\?K\.steel:tcol;ctx\.lineWidth=LW\*(\.\d+);ctx\.strokeRect",
        "the tube outline")
    arcs_a = g(r"A\((\.\d+)\*neon\);glow\(col,\.8\);ctx\.strokeStyle=col;ctx\.lineWidth=LW\*1\.6;", "the arcs")[0]
    glyph_r, glyph_tint = g(
        r"strokeGlyph\(st\.id,SC_GX,SC_GY,SC_GR\*(\.\d+),mix\(col,'#ffffff',(\.\d+)\),neon", "the glyph")
    name_y, name_long, name_size_long, name_size, name_tint, name_a = g(
        r"pSpaced\(sl\.n,SC_GX,(\d+),sl\.n\.length>(\d+)\?([\d.]+):(\d+),mix\(col,'#ffffff',(\.\d+)\),(\.\d+)\*neon",
        "the seal name")
    cap_y, cap_size, cap_a = g(
        r"pSpaced\(ex\?'EXPIRING':'SEAL ACTIVE',SC_GX,(\d+),([\d.]+),ex\?K\.amber:col,(\.\d+)\*", "the caption")
    no_y, no_size = g(r"text\('NO SEAL',SC_GX,SC_GY\+(\d+),(\d+),K\.red", "NO SEAL")
    no_sub_y, no_sub_size, no_sub_a = g(
        r"pSpaced\('IN COMBAT',SC_GX,SC_GY\+(\d+),([\d.]+),K\.red,(\.\d+)", "IN COMBAT")
    no_time_dx, no_time_y, no_time_size, no_time_a = g(
        r"text\('--',SC_GX-(\d+),(\d+),(\d+),K\.muted,(\.\d+)", "the NO SEAL time")
    no_hint_y, no_hint_size, no_hint_a = g(
        r"pSpaced\('CAST A SEAL',SC_GX,(\d+),([\d.]+),K\.muted,(\.\d+)", "CAST A SEAL")
    ax_up, ax_dn, ax_a = g(r"vline\(JL_AX,TOP-(\d+),BOT\+(\d+),K\.violet,st\.jrem>0\?\.85:(\.\d+)\)", "the Judgement axis")
    jl_maj, jl_maj_len, jl_mid, jl_mid_len, jl_min_len, jl_tick_a = g(
        r"tick\(JL_AX,y,s%(\d+)===0\?(\d+):\(s%(\d+)===0\?(\d+):(\d+)\),-1,K\.violet,st\.jrem>0\?\.7:(\.\d+)\)",
        "the Judgement ticks")
    jl_label_a = g(r"if\(s%\d+===0\)text\(String\(s\),JL_AX\+\d+,y\+\d+,\d+,K\.fg,st\.jrem>0\?\.9:(\.\d+),'left'\)",
                   "the Judgement labels")[0]
    jl_guide_on, jl_guide_off, jl_guide_a = g(
        r"setLineDash\(\[(\d+),(\d+)\]\);vline\(JL_X,TOP,BOT,K\.violet,(\.\d+)\)", "the Judgement guide")
    jl_text_dx = g(r"ctx\.translate\(JL_X\+(\d+),\(TOP\+BOT\)/2\)", "the empty lane label")[0]
    jl_text_size, jl_text_a, jl_text_sp = g(
        r"pSpaced\(no\?'':sl\.deb\?'NOT JUDGED':'NO DEBUFF',0,0,([\d.]+),K\.muted,(\.\d+),'center',([\d.]+)\)",
        "the empty lane text")

    # the Judgement lane's live terms (lane 9): the on alphas of the static parts, the bar, the chip and the landing flash
    judged_a_on = g(r"header\('JUDGED',JL_X-\d+,\d+,st\.jrem>0\?col:K\.muted,st\.jrem>0\?(\.\d+):\.\d+\)", "the JUDGED header (debuff up)")[0]
    jl_ax_a_on = g(r"vline\(JL_AX,TOP-\d+,BOT\+\d+,K\.violet,st\.jrem>0\?(\.\d+):\.\d+\)", "the Judgement axis (debuff up)")[0]
    jl_tick_a_on = g(r"tick\(JL_AX,y,s%\d+===0\?\d+:\(s%\d+===0\?\d+:\d+\),-1,K\.violet,st\.jrem>0\?(\.\d+):\.\d+\)",
                     "the Judgement ticks (debuff up)")[0]
    jl_label_a_on = g(r"if\(s%\d+===0\)text\(String\(s\),JL_AX\+\d+,y\+\d+,\d+,K\.fg,st\.jrem>0\?(\.\d+):\.\d+,'left'\)",
                      "the Judgement labels (debuff up)")[0]
    chs = int(g(r"var CHS=(\d+),CHP=CHS/2;", "the chip size", src)[0])
    bar_a0, bar_glow_a, bar_glow_w, bar_core_a, bar_core_w = g(
        r"y=jY\(st\.jrem\);\s*g=ctx\.createLinearGradient\(0,BOT,0,Math\.min\(BOT,y\+CHP\)\);"
        r"g\.addColorStop\(0,rgba\(col,(\.\d+)\)\);g\.addColorStop\(1,rgba\(col,1\)\);\s*"
        r"A\((\.\d+)\);ctx\.strokeStyle=g;ctx\.lineWidth=(\d+);ctx\.beginPath\(\);ctx\.moveTo\(JL_X,BOT\);"
        r"ctx\.lineTo\(JL_X,Math\.min\(BOT,y\+CHP\)\);ctx\.stroke\(\);\s*"
        r"A\((\d+)\);ctx\.strokeStyle=g;ctx\.lineWidth=([\d.]+);ctx\.beginPath\(\);ctx\.moveTo\(JL_X,BOT\);"
        r"ctx\.lineTo\(JL_X,Math\.min\(BOT,y\+CHP\)\);ctx\.stroke\(\);", "the Judgement bar")
    chip_cut, chip_plate_a, chip_plate_mix = g(
        r"chamfer\(JL_X-CHP,y-CHP,CHS,CHS,(\d+)\);A\((\.\d+)\);ctx\.fillStyle=mix\(K\.bg,col,(\.\d+)\);ctx\.fill\(\);",
        "the Judgement chip plate")
    chip_glow_k = g(r"chamfer\(JL_X-CHP,y-CHP,CHS,CHS,\d+\);A\(1\);glow\(col,(\.\d+)\);ctx\.strokeStyle=col;ctx\.lineWidth=LW;",
                    "the Judgement chip edge")[0]
    pop_s, pop_s2, pop_a = g(
        r"if\(st\.jage<(\.\d+)\)\{chamfer\(JL_X-CHP,y-CHP,CHS,CHS,\d+\);A\(\(1-st\.jage/(\.\d+)\)\*(\.\d+)\);"
        r"ctx\.fillStyle=K\.white;ctx\.fill\(\);\}", "the landing flash")
    if pop_s != pop_s2:
        sys.exit("mockup: the landing flash window and its fade disagree")

    # the live terms: sealNeon and sealSt (outside the function body), then the live statements of drawSealChamber
    strike_win, strike_list, strike_cap, strike_win2, strike_n = g(
        r"if\(st\.strike<(\.\d+)\)m=\[([\d.,]+)\]\[Math\.min\((\d+),Math\.floor\(st\.strike/(\.\d+)\*(\d+)\)\)\];", "the strike flicker", src)
    strike = [float(v) for v in strike_list.split(",")]
    if strike_win != strike_win2 or int(strike_cap) != int(strike_n) - 1 or len(strike) != int(strike_n):
        sys.exit("mockup: the strike flicker table and its index no longer agree")
    (flick_rate, drop_p0, drop_p1, expire_s, seed1, mul1, drop_lo, drop_span, seed2, mul2, steady_base, steady_amp,
     steady_freq) = g(
        r"if\(st\.mode==='expiring'&&st\.rem>0\)\{\s*n=Math\.floor\(t\*(\d+)\);p=(\.\d+)\+(\.\d+)\*\(1-st\.rem/(\d+)\);\s*"
        r"m=fract\(Math\.sin\(n\*([\d.]+)\)\*([\d.]+)\)<p\?(\.\d+)\+(\.\d+)\*fract\(Math\.sin\(n\*([\d.]+)\)\*([\d.]+)\):"
        r"(\.\d+)\+(\.\d+)\*Math\.sin\(t\*(\d+)\);\s*\}", "the expiring dropouts", src)
    if mul1 != mul2:
        sys.exit("mockup: the two dropout hashes use different multipliers")
    cycle_expire = g(r"st\.mode=st\.rem<=(\d+)\?'expiring':'active'", "the expiring threshold", src)[0]
    if cycle_expire != expire_s:
        sys.exit("mockup: the expiring threshold and the dropout ramp disagree")
    reduced_expiring = g(r"if\(reduce\)return st\.mode==='expiring'\?(\.\d+):1;", "the reduced motion neon", src)[0]
    pulse_s = g(r"u=reduce\?1:\.5-\.5\*Math\.cos\(Math\.PI\*clock/([\d.]+)\)", "the pulse")[0]
    pl_freq = g(r"pl=inBand&&!reduce\?\.5\+\.5\*Math\.sin\(clock\*(\d+)\):0", "the band pulse")[0]
    in_band_s = g(r"inBand=!no&&st\.rem<=(\d+)", "the reseal threshold")[0]
    fill_min = g(r"if\(!no&&st\.rem>(\.\d+)\)\{\s*tipY=secY\(st\.rem\);", "the fill threshold")[0]
    fill_a0 = g(r"g\.addColorStop\(0,rgba\(tcol,(\.\d+)\)\);g\.addColorStop\(1,rgba\(tcol,1\)\);\s*A\(neon\);ctx\.fillStyle=g;"
                r"ctx\.fillRect\(SC_TX-SC_TW/2,tipY,SC_TW,BOT-tipY\);", "the fill gradient")[0]
    tip_a, tip_mix, tip_h = g(
        r"A\((\.\d+)\*neon\);ctx\.fillStyle=mix\(tcol,'#ffffff',(\.\d+)\);ctx\.fillRect\(SC_TX-SC_TW/2,tipY,SC_TW,([\d.]+)\);", "the tip bar")
    dot_mix, dot_r = g(
        r"A\(neon\);glow\(tcol,1\);ctx\.fillStyle=mix\(tcol,'#ffffff',(\.\d+)\);ctx\.beginPath\(\);ctx\.arc\(SC_TX,tipY,(\d+),0,Math\.PI\*2\)", "the tip dot")
    count_from = g(r"s=st\.rem>(\d+)\?String\(Math\.ceil\(st\.rem\)\):st\.rem\.toFixed\(1\);", "the countdown text")[0]
    count_dx, count_y, count_size, s_gap, s_size, s_a = g(
        r"text\(s,SC_GX-(\d+),(\d+),(\d+),tcol,neon,'center'\);text\('S',SC_GX-\d+\+p/2\+(\d+),\d+,(\d+),K\.muted,(\.\d+)\*neon,'left'\);",
        "the countdown and its S")
    ring_win, ring_win2, ring_a, ring_grow = g(
        r"if\(f<(\.\d+)\)\{p=ease\(f/(\.\d+)\);A\((\.\d+)\*\(1-p\)\);glow\(col,1\);ctx\.strokeStyle=col;ctx\.lineWidth=LW\*1\.6;"
        r"ctx\.beginPath\(\);ctx\.arc\(SC_GX,SC_GY,SC_GR\+p\*(\d+),0,Math\.PI\*2\)", "the Judgement ring")
    if ring_win != ring_win2:
        sys.exit("mockup: the Judgement ring window and its ease disagree")
    if not _m(r"function ease\(v\)\{return 1-Math\.pow\(1-v,3\);\}", src, "the ease function"):
        sys.exit("mockup: ease is gone")

    halo = [[float(a), float(b)] for a, b in re.findall(
        r"\[([\d.]+),([\d.]+)\]", _m(r"var HALO=\[(.*?)\];", src, "the HALO table").group(1))]
    if len(halo) != 4:
        sys.exit(f"mockup: expected four HALO strokes, found {len(halo)}")
    band_glow_k = g(r"glow\(K\.amber,(\.\d+)\);hline\(BOT,", "the band foot glow")[0]
    glyph_glow_k = g(r"strokeGlyph\(st\.id,SC_GX,SC_GY,SC_GR\*\.\d+,mix\(col,'#ffffff',\.\d+\),neon,(\.\d+),LW\*[\d.]+\)",
                     "the glyph glow")[0]
    mock_lw = float(_m(r"LWb=Math\.max\(1,([\d.]+)\*sw/1400\)", src, "the line weight").group(1)) * 2000 / 1400

    css = {n: v.lower() for n, v in re.findall(
        r"^\s*--(bg|fg|muted|violet|amber|red|steel|white):(#[0-9a-fA-F]{6});", src, re.M)}
    for need in ("bg", "fg", "muted", "violet", "amber", "red", "steel", "white"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")

    block = _m(r"(?s)var SEALS=\{(.*?)\n\};", src, "the SEALS table").group(1)
    seals = {sid: dict(n=n, c=c.lower(), deb=int(deb)) for sid, n, c, deb in re.findall(
        r"(\w+):\{n:'(\w+)',c:'(#[0-9a-fA-F]{6})',deb:(\d+)\}", block)}
    if len(seals) != 7:
        sys.exit(f"mockup: expected seven seals, found {len(seals)}")

    # media: texel counts from the baked headers, the scale from the generators
    lens_gen = (MEDIA / "generate_seal_lens.py").read_text(encoding="utf-8")
    ring_gen = (MEDIA / "generate_seal_ring.py").read_text(encoding="utf-8")
    glyph_gen = (MEDIA / "generate_seal_glyphs.py").read_text(encoding="utf-8")
    lens_k = float(_m(r"(?m)^K = ([\d.]+)\s", lens_gen, "the lens texels per image px (K)").group(1))
    texels_per_unit = int(_m(r"Scale: (\d+) texels per unit", glyph_gen, "the glyph texels per unit").group(1))
    ring_k = float(_m(r"(?m)^K = ([\d.]+)\s", ring_gen, "the ring texels per image px (K)").group(1))
    ring_gr = float(_m(r"(?m)^SC_GR = ([\d.]+)\s", ring_gen, "the ring's lens radius (SC_GR)").group(1))
    tex = dict(
        GLOW_HALF=glow_half_radius(MEDIA / "glow_round.tga"),
        lens=tga_size(MEDIA / "seal_lens.tga")[0], arcs=tga_size(MEDIA / "seal_arcs.tga")[0],
        ring=tga_size(MEDIA / "seal_ring.tga")[0], RING_K=ring_k, RING_GR=ring_gr,
        glyph={sid: tga_size(MEDIA / f"seal_glyph_{sid}.tga")[0] for sid in seals},
        LENS_K=lens_k, GLYPH_TEXELS_PER_PX=texels_per_unit / (gr * fl(glyph_r)),
    )

    S = dict(
        SC_W=sc_w, SC_C=int(sc_c), TX_DX=tx_dx, TW=tw, GX=gx, GY=gy, GR=gr, JL_X=jl_x, JL_AX=jl_ax, JL_MAX_S=jl_max,
        HDR_Y=int(hdr_y), HDR_A=fl(hdr_a), JUDGED_DX=int(judged_dx), JUDGED_Y=int(judged_y), JUDGED_A=fl(judged_a),
        PLATE_A_NO=fl(plate_no), PLATE_A=fl(plate_a),
        PLATE_RGB=[int(pr) / 255, int(pg) / 255, int(pb) / 255], PLATE_FILL=fl(plate_fill),
        RADIAL_R0=int(rad_r0), RADIAL_PAD=int(rad_pad), RADIAL_A=fl(rad_a),
        EDGE_A0=fl(edge_a0), EDGE_A1=fl(edge_a1), GLOW_K0=fl(glow_k0), GLOW_K1=fl(glow_k1a) * fl(glow_k1b),
        NO_EDGE_A0=fl(no_edge_a0), NO_EDGE_A1=fl(no_edge_a1),
        MAJ=int(maj), MAJ_LEN=int(maj_len), MIN_LEN=int(min_len), TICK_A=fl(tick_a), MAX_S=max_s,
        LABEL_DX=int(label_dx), LABEL_DY=int(label_dy), LABEL_SIZE=int(label_size),
        LABEL_A_NO=fl(label_no), LABEL_A=fl(label_a),
        BAND_S=band_s, BAND_FILL=fl(band_fill), BAND_DASH=[int(dash_on), int(dash_off)], BAND_PAD=int(band_pad),
        BAND_TOP_A=fl(band_top_a), BAND_BOT_A=fl(band_bot_a), BAND_BOT_W=fl(band_bot_w),
        RESEAL_DY=fl(reseal_dy), RESEAL_SIZE=int(reseal_size), RESEAL_A=fl(reseal_a),
        TUBE_NO_A=fl(tube_no_a), TUBE_A=fl(tube_a),
        RUNG_FROM=int(rung_from), RUNG_TO=int(rung_to), RUNG_STEP=int(rung_step), RUNG_A=fl(rung_a),
        OUT_NO_A=fl(out_no_a), OUT_A=fl(out_a), OUT_W=fl(out_w), ARCS_A=fl(arcs_a),
        GLYPH_R=fl(glyph_r), GLYPH_TINT=fl(glyph_tint),
        NAME_Y=int(name_y), NAME_LONG=int(name_long), NAME_SIZE_LONG=fl(name_size_long), NAME_SIZE=int(name_size),
        NAME_TINT=fl(name_tint), NAME_A=fl(name_a),
        CAP_Y=int(cap_y), CAP_SIZE=fl(cap_size), CAP_A=fl(cap_a),
        NO_Y=int(no_y), NO_SIZE=int(no_size), NO_SUB_Y=int(no_sub_y), NO_SUB_SIZE=fl(no_sub_size), NO_SUB_A=fl(no_sub_a),
        NO_TIME_DX=int(no_time_dx), NO_TIME_Y=int(no_time_y), NO_TIME_SIZE=int(no_time_size), NO_TIME_A=fl(no_time_a),
        NO_HINT_Y=int(no_hint_y), NO_HINT_SIZE=fl(no_hint_size), NO_HINT_A=fl(no_hint_a),
        JL_AX_UP=int(ax_up), JL_AX_DN=int(ax_dn), JL_AX_A=fl(ax_a),
        JL_MAJ=int(jl_maj), JL_MAJ_LEN=int(jl_maj_len), JL_MID=int(jl_mid), JL_MID_LEN=int(jl_mid_len),
        JL_MIN_LEN=int(jl_min_len), JL_TICK_A=fl(jl_tick_a), JL_LABEL_A=fl(jl_label_a),
        JL_GUIDE_DASH=[int(jl_guide_on), int(jl_guide_off)], JL_GUIDE_A=fl(jl_guide_a),
        JL_TEXT_DX=int(jl_text_dx), JL_TEXT_SIZE=fl(jl_text_size), JL_TEXT_A=fl(jl_text_a), JL_TEXT_SP=fl(jl_text_sp),
    )
    # The draw sequence: where each part's drawing statement sits in the function body. A later statement paints over an
    # earlier one, so wherever two parts overlap the later one must draw above the earlier one. (Ties are one statement
    # that draws a halo and then its core, so the list order breaks them.)
    landmarks = [
        ("plate", "rgba(13,6,32,.8)"), ("radial", "createRadialGradient(SC_GX,SC_GY,"), ("glow", "glow(col,.6+"),
        ("edge", "ctx.strokeStyle=col;ctx.lineWidth=LW;ctx.stroke();noglow();"), ("ticks", "tick(DOT_AX,y,"),
        ("band", "ctx.fillStyle=K.amber;ctx.fillRect(SC.x,yb"), ("bandTop", "hline(yb,SC.x+2"),
        ("bandGlow", "glow(K.amber,.8);hline(BOT"), ("bandBottom", "hline(BOT,SC.x+2"),
        ("tube", "ctx.fillRect(SC_TX-SC_TW/2,TOP,SC_TW,BOT-TOP)"), ("fill", "ctx.fillRect(SC_TX-SC_TW/2,tipY,SC_TW,BOT-tipY)"),
        ("tipBar", "ctx.fillRect(SC_TX-SC_TW/2,tipY,SC_TW,1.5)"), ("tipDot", "ctx.arc(SC_TX,tipY,3,0,Math.PI*2)"),
        ("rungs", "hline(secY(s),SC_TX-SC_TW/2"),
        ("outline", "ctx.strokeRect(SC_TX-SC_TW/2,TOP"), ("lens", "ctx.arc(SC_GX,SC_GY,SC_GR,0,Math.PI*2);ctx.stroke()"),
        ("arcs", "glow(col,.8);ctx.strokeStyle=col"), ("glyphHalo", "strokeGlyph(st.id"), ("glyph", "strokeGlyph(st.id"),
        ("judgeRing", "ctx.arc(SC_GX,SC_GY,SC_GR+p*26,0,Math.PI*2)"),
    ]
    at = []
    for k, (name, mark) in enumerate(landmarks):
        i = body.find(mark)
        if i < 0:
            sys.exit(f"mockup: the draw landmark for {name} ({mark!r}) is gone from drawSealChamber")
        at.append((i, k, name))
    order = [name for _, _, name in sorted(at)]
    S.update(BAND_GLOW_K=fl(band_glow_k), GLYPH_GLOW_K=fl(glyph_glow_k), MOCK_LW=mock_lw)
    S.update(
        STRIKE_S=fl(strike_win), STRIKE=strike, EXPIRE_S=int(expire_s), FLICK_RATE=int(flick_rate), FLICK_SEED=fl(seed1),
        FLICK_SEED2=fl(seed2), FLICK_MUL=fl(mul1), DROP_P0=fl(drop_p0), DROP_P1=fl(drop_p1), DROP_LO=fl(drop_lo),
        DROP_SPAN=fl(drop_span), STEADY_BASE=fl(steady_base), STEADY_AMP=fl(steady_amp), STEADY_FREQ=int(steady_freq),
        PULSE_S=fl(pulse_s), BAND_PL_FREQ=int(pl_freq), BAND_PL=fl(band_pl), IN_BAND_S=int(in_band_s),
        RESEAL_IN0=fl(reseal_in0), RESEAL_IN1=fl(reseal_in1),
        FILL_MIN=fl(fill_min), FILL_A0=fl(fill_a0), TIP_A=fl(tip_a), TIP_MIX=fl(tip_mix), TIP_H=fl(tip_h),
        DOT_MIX=fl(dot_mix), DOT_R=int(dot_r),
        COUNT_FROM=int(count_from), COUNT_DX=int(count_dx), COUNT_Y=int(count_y), COUNT_SIZE=int(count_size),
        S_GAP=int(s_gap), S_SIZE=int(s_size), S_A=fl(s_a),
        RING_S=fl(ring_win), RING_A=fl(ring_a), RING_GROW=int(ring_grow), REDUCED_EXPIRING=fl(reduced_expiring),
    )
    S.update(
        JUDGED_A_ON=fl(judged_a_on), JL_AX_A_ON=fl(jl_ax_a_on), JL_TICK_A_ON=fl(jl_tick_a_on), JL_LABEL_A_ON=fl(jl_label_a_on),
        CHS=chs, JL_BAR_A0=fl(bar_a0), JL_BAR_GLOW_A=fl(bar_glow_a), JL_BAR_GLOW_W=int(bar_glow_w),
        JL_BAR_CORE_A=int(bar_core_a), JL_BAR_CORE_W=fl(bar_core_w), CHIP_CUT=int(chip_cut), CHIP_PLATE_A=fl(chip_plate_a),
        CHIP_PLATE_MIX=fl(chip_plate_mix), CHIP_GLOW_K=fl(chip_glow_k), POP_S=fl(pop_s), POP_A=fl(pop_a),
    )
    return dict(base=base, S=S, CSS=css, SEALS=seals, TEX=tex, HALO=halo, FONT=font_metrics(), ORDER=order)


# ---------------------------------------------------------------------------------------
# Lua prelude: the dots harness's own, plus a Paladin-aware boot and the Seal Chamber helpers
# ---------------------------------------------------------------------------------------

PRELUDE = DOTS_H.PRELUDE + r"""
local B, S = MU.base, MU.S
local FONT, HALO = MU.FONT, MU.HALO
-- the mockup's glow(col, k) is HALO's four nested strokes, each at alpha k * a: the coverage over the stroke's edge, from stroke `from` out
local function coverage(k, from)
    local keep = 1
    for i = from or 1, #HALO do keep = keep * (1 - k * HALO[i][2]) end
    return 1 - keep
end
-- one scaled ADD copy of a glyph standing in for that halo: its mean alpha over the reach, and how far it grows (mean reach, alpha weighted)
local function haloStandIn(k, size)
    local sum, prev, wr, wa = 0, 0, 0, 0
    for j = 1, #HALO do
        sum = sum + (HALO[j][1] - prev) * coverage(k, j)
        prev = HALO[j][1]
        wr, wa = wr + HALO[j][1] * HALO[j][2], wa + HALO[j][2]
    end
    return 1 + (wr / wa) / (size / 2), sum / HALO[#HALO][1]
end
local SK = 1.28                                  -- design px per image px, at a 1440 high screen
local function secY(s) return B.BOT - s / S.MAX_S * (B.BOT - B.TOP) end
local function jY(s) return B.BOT - s / S.JL_MAX_S * (B.BOT - B.TOP) end
local function rgb(hex) return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 } end
local WHITE = { 1, 1, 1 }
local LINE = 1.3

-- the profile's seal keys (HudProfiles.lua seals.order) and the mockup ids they stand for
local KEY_ID = { sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command", sol = "light", sow = "wisdom", soj = "justice" }
local ORDER = { "sor", "sotc", "sofu", "soc", "sol", "sow", "soj" }

-- A strict-ish secret: every operation but type() throws, and FS.IsSecret recognises it.
SECRET = setmetatable({}, {
    __index = function() error("indexed a secret", 2) end, __newindex = function() error("wrote a secret", 2) end,
    __len = function() error("length of a secret", 2) end, __call = function() error("called a secret", 2) end,
    __lt = function() error("compared a secret", 2) end, __le = function() error("compared a secret", 2) end,
    __concat = function() error("concatenated a secret", 2) end, __unm = function() error("negated a secret", 2) end,
})
SECRET_FN = function(v) return rawequal(v, SECRET) end

function stubTheme2_()
    stubTheme_()
    local Theme = FS.Theme
    Theme.SLICE_GLOW_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_glow.tga"
    Theme.SLICE_GLOW_PAD = 4
    Theme.SLICE_GLOW_MARGIN = 10
    Theme.SLICE_CUT_MARGIN = 6
    Theme.SLICE_CUT2_OUTLINE_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\slice_cut2_outline.tga"
    -- the real Theme.AddSliceTexture / AddCut2Texture: two anchors, inset, margin
    function Theme.AddSliceTexture(frame, path, color, layer, sublevel, inset)
        local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
        t:SetTexture(path)
        Theme.ApplyNineSlice(t)
        inset = inset or 0
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
        t:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
        if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
        t.slicePath, t.inset = path, inset
        return t
    end
    function Theme.AddCut2Texture(frame, path, color, layer, sublevel, inset)
        local t = Theme.AddSliceTexture(frame, path, color, layer, sublevel, inset)
        Theme.ApplyNineSlice(t, Theme.SLICE_CUT_MARGIN)
        return t
    end
end

-- Animation groups created on any region of the chamber tree are a v1 drop: record every owner.
ANIM_OWNERS = {}
do
    local mt = getmetatable(UIParent)
    local orig = mt.CreateAnimationGroup
    mt.CreateAnimationGroup = function(self, ...)
        ANIM_OWNERS[#ANIM_OWNERS + 1] = self
        return orig(self, ...)
    end
end

-- opts: class, db, state, noSeals, noDots, noHud, noEvents, height, mkProfile(profiles), themeFix(), beforeSeals()
local function boot(opts)
    opts = opts or {}
    resetWorld()
    for i = #ANIM_OWNERS, 1, -1 do ANIM_OWNERS[i] = nil end
    IN_COMBAT, AFFECTING = false, nil
    SECRET_FN = function(v) return rawequal(v, SECRET) end
    SetScreen(opts.height or 1440)
    ForeverSynthwaveDB = opts.db or {}
    FS.IsSecret = function(v) return SECRET_FN(v) end
    UnitGUID = function() return "Creature-0-0-0-0-1-0000000001" end
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    stubTheme2_()
    if not opts.noHud then stubHud_() end
    loadAddonFile(LAYOUT_SRC, "Layout.lua")
    loadAddonFile(GUNSIGHT_SRC, "Gunsight.lua")
    loadAddonFile(PROFILES_SRC, "HudProfiles.lua")
    loadAddonFile(HUDSPELLS_SRC, "HudSpells.lua")
    local cls = opts.class or "PALADIN"
    PROFILE = FS.HudProfiles[cls]
    if opts.mkProfile then PROFILE = opts.mkProfile(FS.HudProfiles) end
    UnitClass = function() return "Class", cls end
    STATE = opts.state
    if opts.themeFix then opts.themeFix() end
    if not opts.noDots then loadAddonFile(DOTS_SRC, "GunsightDots.lua") end
    if opts.beforeSeals then opts.beforeSeals() end
    if not opts.noSeals then loadAddonFile(SEALS_SRC, "GunsightSeals.lua") end
    if not opts.noEvents then
        fire("ADDON_LOADED", "ForeverSynthwave")
        fire("PLAYER_LOGIN")
    end
    return FS.GunsightSeals, FS.GunsightDots
end

-- Hud states: a known seal, none (false), unknown (nil)
local function sealState(key)
    return { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {}, inCombat = false,
        seal = { key = key, id = 21084, expiresAt = NOW + 20, duration = 30, castAt = NOW - 10 } }
end
-- a Hud seal state `rem` seconds from expiry, cast `age` seconds ago (both against the mock clock), plus extra top level fields
local function sealAt(key, rem, age, extra)
    local st = sealState(key)
    st.seal.expiresAt = NOW + rem
    st.seal.castAt = NOW - (age or 10)
    for k, v in pairs(extra or {}) do st[k] = v end
    return st
end
local function effA(t) return (t.alpha or 1) * ((t.color and t.color[4]) or (t.vertex and t.vertex[4]) or 1) end
local function mixW(c, k) return { c[1] + (1 - c[1]) * k, c[2] + (1 - c[2]) * k, c[3] + (1 - c[3]) * k } end
local function pulseAt(t) return 0.5 - 0.5 * math.cos(math.pi * t / S.PULSE_S) end
local function easeOut(v) return 1 - (1 - v) ^ 3 end
local function noneState(inCombat) return { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {}, seal = false, inCombat = inCombat } end
local function unknownState() return { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {} } end

local function chamberFrames()
    local out = {}
    for _, f in ipairs(FRAMES) do if (f.name or ""):find("GunsightSeals") then out[#out + 1] = f end end
    return out
end
local function sealColor(id) return rgb(MU.SEALS[id].c) end
local function vis(f) return isVisible(f) end
local function texOf(t) return (t.path or ""):match("([^\\]+)$") end
local function lineRect(t)                       -- a solid line texture's centre line and extent
    local l, tp, w, h = imgRect(t)
    return l, tp, w, h
end
local function visibleTexts()
    local out = {}
    for _, fs in ipairs(FONTSTRINGS) do
        if fs.text and fs.text ~= "" and isVisible(fs) then out[#out + 1] = fs.text end
    end
    return out
end
local function textSet()
    local set = {}
    for _, t in ipairs(visibleTexts()) do set[t] = (set[t] or 0) + 1 end
    return set
end
local function colA(c, want, a, what)            -- a {r,g,b,a} table against a colour and an alpha
    colorIs(c, want, what .. " colour")
    near3(c[4], a, what .. " alpha")
end
local function tint(t)                           -- what a texture will draw as: its colour texture or its vertex colour
    return t.color or t.vertex
end
-- every neon driven part at neon level e: the alphas the mockup's A(.. * neon) lays down
local function checkNeon(Seals, e, what)
    local P, C = Seals.parts, Seals.C
    near3(P.glyph.vertex[4], e, what .. ": glyph")
    near3(P.lens.vertex[4], e, what .. ": lens")
    near3(P.arcs.vertex[4], S.ARCS_A * e, what .. ": arcs")
    near3(P.glyphHalo.vertex[4], C.HALO_A * e, what .. ": glyph halo")
    near3(P.radial.vertex[4], S.RADIAL_A * e, what .. ": radial wash")
    near3(tint(P.edge)[4], S.EDGE_A0 + S.EDGE_A1 * e, what .. ": edge")
    near3(tint(P.glow)[4], (S.EDGE_A0 + S.EDGE_A1 * e) * coverage(S.GLOW_K0 + S.GLOW_K1 * e), what .. ": edge halo")
    near3(P.name.textColor[4], S.NAME_A * e, what .. ": name")
    near3(P.count.textColor[4], e, what .. ": countdown")
    near3(P.countS.textColor[4], S.S_A * e, what .. ": S")
    near3(P.name.cur[4], S.NAME_A * e, what .. ": name (stored colour)")
    near3(P.count.cur[4], e, what .. ": countdown (stored colour)")
    near3(P.countS.cur[4], S.S_A * e, what .. ": S (stored colour)")
    near3(P.fill.alpha, e, what .. ": fill")
    near3(effA(P.tipBar), S.TIP_A * e, what .. ": tip bar")
    near3(effA(P.tipDot), e, what .. ": tip dot")
end
-- a text part: shown, its text, its font size, its centre x and its baseline (the middle of the line box sits CAP * size above it)
local function checkText(fs, text, size, x, base, what)
    check(vis(fs) and fs.text == text, what .. ": text " .. tostring(fs.text) .. ", want " .. tostring(text))
    check(math.abs(fs.monoSize - size * SK * FS.Layout.Scale()) < 1e-6, what .. ": font " .. tostring(fs.monoSize))
    local cx, cy = imgCenter(fs)
    near3(cx, x, what .. " x"); near3(cy, base - FONT.CAP * size, what .. " baseline")
end

-- The Judgement lane (lane 9). A Hud state whose TARGET carries our Judgement debuff: `key` is the seal it was cast under (the
-- ledger's key), `rem` the seconds left, `age` the seconds since it landed; the active seal is that same seal unless told. The lane
-- wears the CHAMBER's colour (the current seal's, red under NO SEAL, violet unknown), as the mockup does (2111, 2188 to 2194).
C_Spell = { GetSpellTexture = function() return 135959 end }       -- the default client answers; icon cases swap it
local DEB = { sotc = 40, sol = 40, sow = 40, soj = 10 }
local function laneColor(name)
    if name == "red" then return rgb(MU.CSS.red) elseif name == "violet" then return rgb(MU.CSS.violet) end
    return sealColor(KEY_ID[name])
end
local function judgedState(key, rem, age, seal)
    local st = sealAt(seal or key, 1000, 10)
    st.judgeAt = NOW - (age or 10)
    st.judged = { key = key, appliedAt = NOW - (age or 10), expiresAt = NOW + rem, duration = DEB[key] }
    return st
end
-- judged false (none on the target) or nil (unknown)
local function noJudgeState(seal, judged)
    local st = sealAt(seal or "sotc", 1000, 10)
    st.judged = judged
    return st
end
local function stackCount(P)
    local n = 0
    for _, fs in ipairs(P.stack) do if vis(fs) and fs.text and fs.text ~= "" then n = n + 1 end end
    return n
end
local function stackWord(P)
    local out = {}
    for _, fs in ipairs(P.stack) do if vis(fs) and fs.text then out[#out + 1] = fs.text end end
    return table.concat(out)
end
-- the static lane parts at their debuff-up (on) or empty (off) alphas
local function laneStatic(P, on, col, what)
    local violet, fg = rgb(MU.CSS.violet), rgb(MU.CSS.fg)
    colA(P.jAxis.color, violet, on and S.JL_AX_A_ON or S.JL_AX_A, what .. ": axis")
    for i, t in ipairs(P.jTicks) do colA(t.color, violet, on and S.JL_TICK_A_ON or S.JL_TICK_A, what .. ": Judgement tick " .. (i - 1)) end
    for s2, fs in pairs(P.jLabels) do colA(fs.textColor, fg, on and S.JL_LABEL_A_ON or S.JL_LABEL_A, what .. ": Judgement label " .. s2) end
    if on then colA(P.judged.textColor, col, S.JUDGED_A_ON, what .. ": JUDGED header")
    else colA(P.judged.textColor, rgb(MU.CSS.muted), S.JUDGED_A, what .. ": JUDGED header") end
end
-- the lane with a debuff of `rem` seconds on it, in the colour named by `key` (a seal key, or "red" / "violet")
local function laneIs(P, rem, key, what)
    local col = laneColor(key)
    local hj = math.min(rem, S.JL_MAX_S) / S.JL_MAX_S * (B.BOT - B.TOP)       -- BOT - jY(rem)
    local hb = hj - S.CHS / 2                                                   -- the bar runs BOT to min(BOT, y + CHP)
    for _, spec in ipairs({ { P.jBarGlow, S.JL_BAR_GLOW_W, S.JL_BAR_GLOW_A, "bar glow" }, { P.jBarCore, S.JL_BAR_CORE_W, S.JL_BAR_CORE_A, "bar core" } }) do
        local t, w, a, nm = spec[1], spec[2], spec[3], what .. ": " .. spec[4]
        if hb > 1e-6 then
            check(vis(t), nm .. " is shown")
            local l, tp, tw, th = imgRect(t)
            near3(l + tw / 2, S.JL_X, nm .. " x"); near3(tw, w, nm .. " width"); near3(tp + th, B.BOT, nm .. " foot is BOT")
            near3(th, hb, nm .. " height (rem " .. rem .. ")"); near3(tp, jY(math.min(rem, S.JL_MAX_S)) + S.CHS / 2, nm .. " top is the chip's lower edge")
            near3(t.alpha, a, nm .. " alpha")
            local g = t.gradient
            check(g and g.orientation == "VERTICAL", nm .. ": a vertical gradient")
            near3(g.min.a, S.JL_BAR_A0, nm .. " tail alpha"); near3(g.max.a, 1, nm .. " tip alpha")
            colorIs({ g.min.r, g.min.g, g.min.b }, col, nm .. " tail colour"); colorIs({ g.max.r, g.max.g, g.max.b }, col, nm .. " tip colour")
        else
            check(not vis(t), nm .. " is hidden when the chip already covers it (rem " .. rem .. ")")
        end
    end
    local chip = P.jChip
    check(vis(chip), what .. ": the chip is shown")
    local l, tp, w, h = imgRect(chip)
    near3(l + w / 2, S.JL_X, what .. ": chip x"); near3(tp + h / 2, jY(math.min(rem, S.JL_MAX_S)), what .. ": chip y is jY(rem)")
    near3(w, S.CHS, what .. ": chip width"); near3(h, S.CHS, what .. ": chip height")
    colA(chip.fsSkin.border.ring.vertex, col, 1, what .. ": chip ring")
    colorIs(chip.fsSkin.glow.vertex, col, what .. ": chip glow colour")
    near3(chip.fsSkin.glow.vertex[4], coverage(S.CHIP_GLOW_K), what .. ": chip glow alpha (glow(col, .6))")
    near3(chip.fsAuraPlate.alpha, S.CHIP_PLATE_A, what .. ": chip plate alpha")
    laneStatic(P, true, col, what)
    check(stackCount(P) == 0, what .. ": no empty lane label")
end
-- the lane with nothing on it: the label the seal look gives it (NOT JUDGED, NO DEBUFF or none)
local function laneEmpty(P, label, what)
    for _, nm in ipairs({ "jBarGlow", "jBarCore", "jChip", "jPop" }) do check(not vis(P[nm]), what .. ": " .. nm .. " is hidden") end
    laneStatic(P, false, nil, what)
    check(stackWord(P) == label, what .. ": lane label '" .. stackWord(P) .. "', want '" .. label .. "'")
end
"""


# ---------------------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------------------

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("constants_match_the_mockup")(r"""
local Seals = boot({ noEvents = true })
check(type(Seals) == "table" and type(Seals.C) == "table", "FS.GunsightSeals.C (the constants table) is missing")
local C = Seals.C
local function eq(a, b, what) near(a, b, what .. " (GunsightSeals has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")") end
eq(C.SC.x, B.DOT_AX, "chamber x (the DoT scale's seat)"); eq(C.SC.y, B.FR_T, "chamber y")
eq(C.SC.w, S.SC_W, "chamber width"); eq(C.SC.h, B.FR_B - B.FR_T, "chamber height"); eq(C.SC.c, S.SC_C, "chamber chamfer (baked 6, mockup 8)", 2)
eq(C.TX_DX, S.TX_DX, "tube x"); eq(C.TW, S.TW, "tube width"); eq(C.GX, S.GX, "lens x"); eq(C.GY, S.GY, "lens y"); eq(C.GR, S.GR, "lens radius")
eq(C.JL_X, S.JL_X, "Judgement guide x"); eq(C.JL_AX, S.JL_AX, "Judgement axis x"); eq(C.JL_MAX_S, S.JL_MAX_S, "Judgement seconds")
eq(C.HDR_Y, S.HDR_Y, "header y"); eq(C.HDR_A, S.HDR_A, "header alpha"); eq(C.JUDGED_DX, S.JUDGED_DX, "JUDGED x offset"); eq(C.JUDGED_A, S.JUDGED_A, "JUDGED alpha")
eq(S.JUDGED_Y, S.HDR_Y, "the two headers share a baseline")
eq(C.PLATE_A, S.PLATE_A, "plate alpha"); eq(C.PLATE_A_NO, S.PLATE_A_NO, "plate alpha with no seal"); eq(C.PLATE_FILL, S.PLATE_FILL, "plate fill alpha")
for i = 1, 3 do eq(C.PLATE_RGB[i], S.PLATE_RGB[i], "plate rgb " .. i) end
eq(C.RADIAL_A, S.RADIAL_A, "radial alpha"); eq(C.RADIAL_R0, S.RADIAL_R0, "radial inner radius"); eq(C.RADIAL_PAD, S.RADIAL_PAD, "radial outer pad")
eq(C.EDGE_A0, S.EDGE_A0, "edge alpha base"); eq(C.EDGE_A1, S.EDGE_A1, "edge alpha neon"); eq(C.NO_EDGE_A0, S.NO_EDGE_A0, "NO SEAL edge base"); eq(C.NO_EDGE_A1, S.NO_EDGE_A1, "NO SEAL edge pulse")
eq(C.GLOW_K0, S.GLOW_K0, "glow base"); eq(C.GLOW_K1, S.GLOW_K1, "glow neon")
eq(C.MAJ, S.MAJ, "major tick step"); eq(C.MAJ_LEN, S.MAJ_LEN, "major tick length"); eq(C.MIN_LEN, S.MIN_LEN, "minor tick length")
eq(C.TICK_A, S.TICK_A, "tick alpha"); eq(C.MAX_S, S.MAX_S, "ruler seconds")
eq(C.LABEL_DX, S.LABEL_DX, "label x"); eq(C.LABEL_DY, S.LABEL_DY, "label y"); eq(C.LABEL_SIZE, S.LABEL_SIZE, "label size")
eq(C.LABEL_A, S.LABEL_A, "label alpha"); eq(C.LABEL_A_NO, S.LABEL_A_NO, "label alpha with no seal")
eq(C.BAND_S, S.BAND_S, "band seconds"); eq(C.BAND_FILL, S.BAND_FILL, "band fill"); eq(C.BAND_PAD, S.BAND_PAD, "band side pad")
eq(C.BAND_DASH[1], S.BAND_DASH[1], "band dash on"); eq(C.BAND_DASH[2], S.BAND_DASH[2], "band dash off")
eq(C.BAND_TOP_A, S.BAND_TOP_A, "band top alpha"); eq(C.BAND_BOT_A, S.BAND_BOT_A, "band foot alpha"); eq(C.BAND_BOT_W, S.BAND_BOT_W, "band foot weight")
eq(C.RESEAL_DY, S.RESEAL_DY, "RESEAL y"); eq(C.RESEAL_SIZE, S.RESEAL_SIZE, "RESEAL size"); eq(C.RESEAL_A, S.RESEAL_A, "RESEAL alpha")
eq(C.TUBE_A, S.TUBE_A, "tube track alpha"); eq(C.TUBE_NO_A, S.TUBE_NO_A, "tube track alpha with no seal")
eq(C.RUNG_STEP, S.RUNG_STEP, "rung step"); eq(C.RUNG_A, S.RUNG_A, "rung alpha")
eq(C.OUT_W, S.OUT_W, "tube outline weight"); eq(C.OUT_A, S.OUT_A, "tube outline alpha"); eq(C.OUT_NO_A, S.OUT_NO_A, "tube outline alpha with no seal")
eq(C.ARCS_A, S.ARCS_A, "arcs alpha"); eq(C.GLYPH_R, S.GLYPH_R, "glyph radius fraction"); eq(C.GLYPH_TINT, S.GLYPH_TINT, "glyph tint")
eq(C.NAME_Y, S.NAME_Y, "name y"); eq(C.NAME_SIZE, S.NAME_SIZE, "name size"); eq(C.NAME_SIZE_LONG, S.NAME_SIZE_LONG, "long name size"); eq(C.NAME_LONG, S.NAME_LONG, "long name length")
eq(C.NAME_TINT, S.NAME_TINT, "name tint"); eq(C.NAME_A, S.NAME_A, "name alpha")
eq(C.CAP_Y, S.CAP_Y, "caption y"); eq(C.CAP_SIZE, S.CAP_SIZE, "caption size"); eq(C.CAP_A, S.CAP_A, "caption alpha")
eq(C.NO_Y, S.NO_Y, "NO SEAL y"); eq(C.NO_SIZE, S.NO_SIZE, "NO SEAL size")
eq(C.NO_SUB_Y, S.NO_SUB_Y, "IN COMBAT y"); eq(C.NO_SUB_SIZE, S.NO_SUB_SIZE, "IN COMBAT size"); eq(C.NO_SUB_A, S.NO_SUB_A, "IN COMBAT alpha")
eq(C.NO_TIME_DX, S.NO_TIME_DX, "-- x"); eq(C.NO_TIME_Y, S.NO_TIME_Y, "-- y"); eq(C.NO_TIME_SIZE, S.NO_TIME_SIZE, "-- size"); eq(C.NO_TIME_A, S.NO_TIME_A, "-- alpha")
eq(C.NO_HINT_SIZE, S.NO_HINT_SIZE, "CAST A SEAL size"); eq(C.NO_HINT_A, S.NO_HINT_A, "CAST A SEAL alpha")
eq(C.CAP_Y, S.NO_HINT_Y, "CAST A SEAL shares the caption baseline")
eq(C.JL_AX_UP, S.JL_AX_UP, "Judgement axis overshoot up"); eq(C.JL_AX_DN, S.JL_AX_DN, "Judgement axis overshoot down"); eq(C.JL_AX_A, S.JL_AX_A, "Judgement axis alpha")
eq(C.JL_MAJ, S.JL_MAJ, "Judgement major step"); eq(C.JL_MID, S.JL_MID, "Judgement mid step")
eq(C.JL_MAJ_LEN, S.JL_MAJ_LEN, "Judgement major length"); eq(C.JL_MID_LEN, S.JL_MID_LEN, "Judgement mid length"); eq(C.JL_MIN_LEN, S.JL_MIN_LEN, "Judgement minor length")
eq(C.JL_TICK_A, S.JL_TICK_A, "Judgement tick alpha"); eq(C.JL_LABEL_A, S.JL_LABEL_A, "Judgement label alpha")
eq(C.JL_GUIDE_DASH[1], S.JL_GUIDE_DASH[1], "guide dash on"); eq(C.JL_GUIDE_DASH[2], S.JL_GUIDE_DASH[2], "guide dash off"); eq(C.JL_GUIDE_A, S.JL_GUIDE_A, "guide alpha")
eq(C.JL_TEXT_DX, S.JL_TEXT_DX, "empty lane label x"); eq(C.JL_TEXT_SIZE, S.JL_TEXT_SIZE, "empty lane label size")
eq(C.JL_TEXT_SP, S.JL_TEXT_SP, "empty lane label spacing"); eq(C.JL_TEXT_A, S.JL_TEXT_A, "empty lane label alpha")
eq(C.CAP, FONT.CAP, "baseline to line middle (the font's hhea)"); eq(C.MONO_ADV, FONT.MONO_ADV, "monospace advance (the font's hmtx)")
check(#C.HALO == #HALO, "the HALO table has four strokes")
for i = 1, #HALO do eq(C.HALO[i][1], HALO[i][1], "HALO reach " .. i); eq(C.HALO[i][2], HALO[i][2], "HALO alpha " .. i) end
do
    local k, a = haloStandIn(S.GLYPH_GLOW_K, MU.TEX.glyph.fury / MU.TEX.GLYPH_TEXELS_PER_PX)
    eq(C.HALO_K, k, "glyph halo growth (derived from HALO and glow(col, .9))"); eq(C.HALO_A, a, "glyph halo alpha (derived from HALO and glow(col, .9))")
end
eq(C.BAND_GLOW_K, S.BAND_GLOW_K, "band foot glow strength"); eq(C.GLYPH_GLOW_K, S.GLYPH_GLOW_K, "glyph glow strength")
eq(C.LENS_K, MU.TEX.LENS_K, "lens texels per image px (generator)")
eq(C.LENS_SIZE, MU.TEX.lens, "lens texture size (TGA header)"); eq(C.LENS_SIZE, MU.TEX.arcs, "arcs texture size (TGA header)")
for id, px in pairs(MU.TEX.glyph) do eq(C.GLYPH_SIZE, px / MU.TEX.GLYPH_TEXELS_PER_PX, "glyph size in image px (" .. id .. ")") end
for _, name in ipairs({ "bg", "fg", "violet", "amber", "red", "steel", "muted" }) do colorIs(C.COLORS[name], rgb(MU.CSS[name]), "colour " .. name) end
local n = 0
for id, e in pairs(MU.SEALS) do
    n = n + 1
    local s = C.SEALS[id]
    check(s, "seal " .. id .. " missing")
    check(s.n == e.n, "seal " .. id .. " name " .. tostring(s.n) .. ", mockup " .. e.n)
    colorIs(s.c, rgb(e.c), "seal " .. id .. " colour")
    check(s.deb == e.deb, "seal " .. id .. " Judgement debuff " .. tostring(s.deb) .. ", mockup " .. e.deb)
end
check(n == 7, "seven seals")
""")

case("live_constants_match_the_mockup")(r"""
local Seals = boot({ noEvents = true })
local C = Seals.C
local function eq(a, b, what, eps) near(a, b, what .. " (GunsightSeals has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")", eps or 1e-6) end
check(#C.STRIKE == #S.STRIKE, "strike flicker steps: " .. tostring(#C.STRIKE))
for i = 1, #S.STRIKE do eq(C.STRIKE[i], S.STRIKE[i], "strike step " .. i) end
eq(C.STRIKE_S, S.STRIKE_S, "strike window")
for _, k in ipairs({ "EXPIRE_S", "FLICK_RATE", "FLICK_SEED", "FLICK_SEED2", "FLICK_MUL", "DROP_P0", "DROP_P1", "DROP_LO", "DROP_SPAN",
    "STEADY_BASE", "STEADY_AMP", "STEADY_FREQ", "PULSE_S", "BAND_PL_FREQ", "BAND_PL", "RESEAL_IN0", "RESEAL_IN1",
    "FILL_MIN", "FILL_A0", "TIP_A", "TIP_MIX", "TIP_H", "DOT_MIX", "DOT_R", "COUNT_FROM", "COUNT_DX", "COUNT_Y", "COUNT_SIZE",
    "S_GAP", "S_SIZE", "S_A", "RING_S", "RING_A", "RING_GROW", "REDUCED_EXPIRING" }) do
    check(C[k] ~= nil, "constant " .. k .. " is missing")
    eq(C[k], S[k], k)
end
eq(C.BAND_S, S.IN_BAND_S, "the reseal threshold is the band's 3 s")
eq(C.GLOW_HALF, MU.TEX.GLOW_HALF, "glow_round's half alpha radius (read from the TGA)", 2e-3)
eq(C.RING_SIZE, MU.TEX.ring, "ring texture size (TGA header)"); eq(C.RING_K, MU.TEX.RING_K, "ring texels per image px (generator)")
eq(C.GR, MU.TEX.RING_GR, "the ring texture's circle is the lens radius (generator SC_GR)")
""")

case("neon_and_pulse_match_the_mockups_functions")(r"""
local Seals = boot({ noEvents = true })
local neon, pulse = Seals.Neon, Seals.Pulse
check(type(neon) == "function" and type(pulse) == "function", "FS.GunsightSeals.Neon and .Pulse are exported")
-- golden values: the mockup's own sealNeon and clock pulse, run in node
for _, e in ipairs({ { 0, .2 }, { .05, .2 }, { .1, .9 }, { .15, .9 }, { .2, .1 }, { .3, .7 }, { .35, .7 }, { .45, .3 }, { .5, 1 },
    { .6, .6 }, { .69, .6 }, { .7, 1 }, { 1, 1 }, { 30, 1 } }) do
    near(neon(e[1], false, 20, 5000), e[2], "strike " .. e[1], 1e-12)
end
for _, e in ipairs({ { 4.9, 5000, 0.5910093213105505 }, { 4.9, 5000.077, 0.9284757643198537 }, { 4.9, 5000.154, 0.6846598036199792 },
    { 4.9, 5000.231, 0.26445424428522524 }, { 3, 5001, 0.15437775275742752 }, { 2, 5001.3, 0.3412925747150166 },
    { 1, 5002.05, 0.19082953433127842 }, { .5, 5002.9, 0.5602921190966179 }, { .2, 5003.1, 0.40376015138783256 },
    { 4.5, 5123.456, 0.14766314421771767 }, { 1, 5123.5, 0.1750773243459844 }, { 2.5, 5124, 0.617142527758218 } }) do
    near(neon(99, true, e[1], e[2]), e[3], "expiring rem " .. e[1] .. " at " .. e[2], 1e-9)
end
near(neon(.1, true, 4, 5000.5), 0.16076564962015255, "expiring wins over the strike", 1e-9)
near(neon(.1, true, 4, 5000.5), neon(99, true, 4, 5000.5), "the strike is ignored while expiring", 1e-12)
near(neon(.1, false, 20, 5000, true), 1, "reduced motion: a fresh cast is not struck", 1e-12)
near(neon(0, false, 20, 5000, true), 1, "reduced motion: not expiring is steady", 1e-12)
for _, e in ipairs({ { 4.9, 5000 }, { 3, 5001 }, { 1, 5002.05 }, { .5, 5002.9 }, { 4.5, 5123.456 } }) do
    near(neon(99, true, e[1], e[2], true), S.REDUCED_EXPIRING, "reduced motion: expiring holds the dim level at rem " .. e[1], 1e-12)
end
near(neon(99, true, 4, 5000.5, false), neon(99, true, 4, 5000.5), "an explicit false is the animated neon", 1e-12)
near(neon(99, true, 0, 5000), 1, "an expired seal (rem 0) is steady", 1e-12)
near(neon(99, true, -1, 5000), 1, "an expired seal (rem below 0) is steady", 1e-12)
near(neon(99, false, 4, 5000), 1, "not expiring is steady", 1e-12)
for _, e in ipairs({ { 0, 0 }, { .35, 0.1464466094067262 }, { .7, .5 }, { 1.05, 0.8535533905932737 }, { 1.4, 1 },
    { 5000, 0.6112604669776084 }, { 5000.3, 0.28305813044062333 } }) do
    near(pulse(e[1]), e[2], "pulse at " .. e[1], 1e-12)
end
-- the number the countdown prints: whole seconds above 5 (rounded up), one decimal from 5 down (toFixed(1), half up)
local text = Seals.CountText
check(type(text) == "function", "FS.GunsightSeals.CountText is exported")
for _, e in ipairs({ { 30, "30" }, { 20, "20" }, { 20.01, "21" }, { 6, "6" }, { 5.5, "6" }, { 5.0001, "6" }, { 5, "5.0" }, { 4.96, "5.0" },
    { 4.949, "4.9" }, { 4.95, "5.0" }, { .25, "0.3" }, { .05, "0.1" }, { .06, "0.1" }, { .049, "0.0" }, { 1, "1.0" } }) do
    check(text(e[1]) == e[2], "countdown text at " .. e[1] .. ": " .. tostring(text(e[1])) .. ", want " .. e[2])
end
""")

case("nothing_is_built_at_file_load_and_nothing_when_disabled")(r"""
local Seals = boot({ noEvents = true })
check(Seals.frame == nil, "the chamber was built at file load (UIParent is not real yet)")
check(#chamberFrames() == 0, "a chamber frame exists at file load")
local S2 = boot({ db = { gunsight = { enabled = false } } })
check(S2.frame == nil and #chamberFrames() == 0, "a disabled gunsight must build nothing")
check(next(DEGRADED) == nil, "a disabled gunsight is silent: " .. tostring(next(DEGRADED)))
""")

case("a_class_that_does_not_own_the_seal_seat_builds_nothing_and_changes_nothing")(r"""
-- WARLOCK and PRIEST have dots, ROGUE has no profile at all; the whole drawn tree of the DoT piece and the
-- frame, texture and font string counts are the same with and without this file.
for _, cls in ipairs({ "WARLOCK", "PRIEST", "ROGUE" }) do
    local Seals, Dots = boot({ class = cls })
    check(Seals.frame == nil and Seals.parts == nil, cls .. ": a chamber was built")
    check(#chamberFrames() == 0, cls .. ": a chamber frame exists")
    local h1, n1 = renderHash(Dots)
    local nf, nt, ns = #FRAMES, #TEXTURES, #FONTSTRINGS
    check(#SUBS <= 1, cls .. ": more than the scale's own subscription")
    local _, Dots2 = boot({ class = cls, noSeals = true })
    local h2, n2 = renderHash(Dots2)
    check(nf == #FRAMES and nt == #TEXTURES and ns == #FONTSTRINGS,
        string.format("%s: counts differ with the file loaded: frames %d/%d textures %d/%d fonts %d/%d", cls, nf, #FRAMES, nt, #TEXTURES, ns, #FONTSTRINGS))
    check(h1 == h2 and n1 == n2, cls .. ": the drawn tree differs with the file loaded")
    check(next(DEGRADED) == nil, cls .. ": a degrade was logged: " .. tostring(next(DEGRADED)))
end
-- dots plus seals stays on the scale (ClassSlot says "dots"), so no chamber either
local Seals = boot({ class = "WARLOCK", mkProfile = function(P)
    local p = {}
    for k, v in pairs(P.WARLOCK) do p[k] = v end
    p.seals = { order = { "sor" }, duration = 30, judge = {} }
    return p
end })
check(Seals.frame == nil and #chamberFrames() == 0, "dots plus seals must not build the chamber")
-- a non table seals value is not a seal profile either
local Seals2 = boot({ class = "ROGUE", mkProfile = function() return { row = {}, seals = "x" } end })
check(Seals2.frame == nil, "a non table seals value built a chamber")
""")

case("the_class_slot_comes_from_the_shared_helper_and_a_bad_helper_builds_nothing")(r"""
local Seals = boot({ class = "WARLOCK", themeFix = function() FS.HudProfiles.ClassSlot = function() return "seals" end end })
check(Seals.frame ~= nil, "the helper answering seals must give the chamber for a Warlock profile (the rule is the helper's, not a copy)")
local S2 = boot({ themeFix = function() FS.HudProfiles.ClassSlot = function() return "dots" end end })
check(S2.frame == nil, "the helper answering dots must give a Paladin no chamber")
local S3 = boot({ themeFix = function() FS.HudProfiles.ClassSlot = nil end })
check(S3.frame == nil, "a missing helper builds nothing and does not throw")
local S4 = boot({ themeFix = function() FS.HudProfiles.ClassSlot = function() error("boom") end end })
check(S4.frame == nil, "a throwing helper builds nothing and does not throw")
local S5 = boot({ noHud = true })
check(S5.frame == nil, "no FS.Hud: nothing built")
""")

case("the_paladin_chamber_hangs_off_the_dot_piece_frame")(r"""
local Seals, Dots = boot({})
local ch = Seals.frame
check(ch and ch.name == "ForeverSynthwaveGunsightSeals", "the chamber frame is missing or misnamed")
check(ch:GetParent() == Dots.frame, "the chamber is a child of the dot piece frame (so the dot key toggles it)")
check(Dots.frame:GetParent() == FS.Gunsight.root, "the piece frame is the gunsight root's child")
check(ch:GetParent() ~= Dots.gate and ch:GetParent() ~= Dots.content, "not hung off the target gate or the scale content")
check(next(Dots.parts) == nil and #Dots.chips == 0, "the DoT file draws nothing for the Paladin")
check(#chamberFrames() == 1, "exactly one frame built")
check(ch:IsShown() and isVisible(ch), "visible by default")
check(type(Seals.parts) == "table" and Seals.parts.glyph and Seals.parts.lens, "Seals.parts exposes the parts")
for k, p in pairs(Seals.parts) do
    -- the Judgement chip is a frame on the chamber and its white pop is the chip's own texture
    if type(p) == "table" and p.kind then check(p.parent == (k == "jPop" and Seals.parts.jChip or ch), "part " .. k .. " is not a child of the chamber") end
end
check(#AURA_TOUCHED == 0, "no aura API was read")
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("the_chamber_does_not_depend_on_a_target")(r"""
local Seals, Dots = boot({})
UnitExists = function() return false end
fire("PLAYER_TARGET_CHANGED")
check(not Dots.gate:IsShown(), "setup: with no target the DoT gate is hidden")
check(isVisible(Seals.frame), "the chamber is drawn with no target (only the horizon segment depends on one)")
""")

case("chamber_frame_geometry_matches_the_mockup")(r"""
local Seals, Dots = boot({})
local ch, P = Seals.frame, Seals.parts
local l, t, w, h = imgRect(ch)
near3(l, B.DOT_AX, "chamber left"); near3(t, B.FR_T, "chamber top")
near3(w, S.SC_W, "chamber width"); near3(h, B.FR_B - B.FR_T, "chamber height")
-- plate, edge, halo: the nine-slice textures hug the chamber (the halo outset by the baked pad)
local function corners(tex)
    local tl, br
    for _, p in ipairs(tex.points) do
        check(p[2] == ch, "a frame texture anchors to the chamber")
        if p[1] == "TOPLEFT" then tl = p elseif p[1] == "BOTTOMRIGHT" then br = p end
    end
    check(tl and br and #tex.points == 2, "two anchors")
    return tl[4], tl[5], br[4], br[5]
end
local a, b, c, d = corners(P.plate)
check(a == 0 and b == 0 and c == 0 and d == 0, "the plate fills the chamber exactly")
a, b, c, d = corners(P.edge)
check(a == 0 and b == 0 and c == 0 and d == 0, "the edge ring sits on the chamber's own rect")
a, b, c, d = corners(P.glow)
check(a == -4 and b == 4 and c == 4 and d == -4, "the halo is outset by the glow pad (4), got " .. a .. "," .. b .. "," .. c .. "," .. d)
check(P.glow.blend == "ADD", "the halo adds")
check(texOf(P.plate) == "slice_cut2_fill.tga" and P.plate.margin == 6, "plate: the cut2 fill at the chamfer margin")
check(texOf(P.edge) == "slice_cut2_outline.tga" and P.edge.margin == 6, "edge: the cut2 outline at the chamfer margin")
check(texOf(P.glow) == "slice_cut2_glow.tga" and P.glow.margin == 10, "halo: the cut2 glow at the glow margin")
-- the soft radial wash: the round glow cropped at the frame's right edge
local R = S.GR + S.RADIAL_PAD
local rl, rt, rw, rh = imgRect(P.radial)
near3(rl, S.GX - R, "radial left"); near3(rt, S.GY - R, "radial top"); near3(rh, 2 * R, "radial height")
near3(rw, (B.DOT_AX + S.SC_W) - (S.GX - R), "radial width is cropped at the frame's right edge")
check(texOf(P.radial) == "glow_round.tga", "radial texture")
check(P.radial.texcoord and math.abs(P.radial.texcoord[2] - rw / (2 * R)) < 1e-6 and P.radial.texcoord[1] == 0
    and P.radial.texcoord[3] == 0 and P.radial.texcoord[4] == 1, "radial texcoords crop the glow at the same edge")
""")

case("ruler_matches_the_mockup")(r"""
local Seals = boot({})
local P = Seals.parts
check(#P.ticks == S.MAX_S + 1, "31 ticks, got " .. #P.ticks)
for s = 0, S.MAX_S do
    local maj = s % S.MAJ == 0
    local tl, tt, tw, th = imgRect(P.ticks[s + 1])
    near3(tt + th / 2, secY(s), "tick " .. s .. " y")
    near3(tl + tw, B.DOT_AX, "tick " .. s .. " right edge on the frame's left edge")
    near3(tw, maj and S.MAJ_LEN or S.MIN_LEN, "tick " .. s .. " length")
    near3(th, LINE, "tick " .. s .. " weight")
    colA(P.ticks[s + 1].color, rgb(MU.CSS.violet), S.TICK_A, "tick " .. s)
    check(vis(P.ticks[s + 1]), "tick " .. s .. " visible")
end
local found = {}
for _, fs in ipairs(FONTSTRINGS) do
    if fs.text and tostring(fs.text):match("^%d+$") then found[fs.text] = (found[fs.text] or 0) + 1 end
end
for s = 0, S.MAX_S, S.MAJ do
    local fs = P.labels[s]
    check(fs and fs.text == tostring(s), "label " .. s)
    check(found[tostring(s)] >= 1, "label " .. s .. " drawn")
    check(math.abs(fs.monoSize - S.LABEL_SIZE * SK) < 1e-6, "label font is Mononoki 12 image px, got " .. tostring(fs.monoSize))
    local cx, cy = imgCenter(fs)
    near3(cx, B.DOT_AX + S.LABEL_DX, "label " .. s .. " left edge")
    near3(cy, secY(s) + S.LABEL_DY - FONT.CAP * S.LABEL_SIZE, "label " .. s .. " on the mockup baseline (y + 4)")
    check(fs.justifyH == "LEFT", "label justify")
end
for s = 0, S.MAX_S do if s % S.MAJ ~= 0 then check(P.labels[s] == nil, "minor tick " .. s .. " must not be labelled") end end
local hdr = P.header
check(hdr.text == "SEAL", "header text")
check(math.abs(hdr.monoSize - 11 * SK) < 1e-6, "header font 11 image px")
local hl, ht, hw, hh = imgRect(hdr)
near3(hl, B.DOT_AX, "header left")
near3(ht + hh, S.HDR_Y + 2.5, "header bottom: the DoT scale's own seat (BOTTOMLEFT, 2.5 image px under the 488 baseline)")
""")

case("band_and_reseal_match_the_mockup")(r"""
local Seals = boot({ state = sealState("sor") })
local P = Seals.parts
local yb = secY(S.BAND_S)
local l, t, w, h = imgRect(P.band)
near3(l, B.DOT_AX, "band left"); near3(l + w, B.DOT_AX + S.SC_W, "band right is the frame's right edge")
near3(t, yb, "band top is 3 s"); near3(t + h, B.BOT, "band bottom is 0")
colA(P.band.color, rgb(MU.CSS.amber), S.BAND_FILL, "band fill")
check(#P.bandTop >= 8, "band top is dashed, got " .. #P.bandTop)
local prevRight
for i, d in ipairs(P.bandTop) do
    local dl, dt, dw, dh = imgRect(d)
    near3(dt + dh / 2, yb, "dash y")
    if i < #P.bandTop then near3(dw, S.BAND_DASH[1], "dash length") else check(dw <= S.BAND_DASH[1] + 1e-3, "last dash is clipped") end
    check(dl >= B.DOT_AX + S.BAND_PAD - 1e-3 and dl + dw <= B.DOT_AX + S.SC_W - S.BAND_PAD + 1e-3, "dash inside the pad")
    if i == 1 then near3(dl, B.DOT_AX + S.BAND_PAD, "first dash starts at the pad") end
    if prevRight then near3(dl - prevRight, S.BAND_DASH[2], "dash gap") end
    prevRight = dl + dw
    colA(d.color, rgb(MU.CSS.amber), S.BAND_TOP_A, "dash")
end
do  -- the canvas dash pattern runs from the pad to the far pad: n whole periods, then a clipped dash and a gap
    local run = S.SC_W - 2 * S.BAND_PAD
    local period = S.BAND_DASH[1] + S.BAND_DASH[2]
    local whole = math.floor(run / period)
    local rest = run - whole * period
    near3(prevRight, B.DOT_AX + S.BAND_PAD + whole * period + math.min(rest, S.BAND_DASH[1]), "the last dash ends where the canvas pattern ends")
    near3(#P.bandTop, whole + (rest > 0 and 1 or 0), "dash count")
end
local el, et, ew, eh = imgRect(P.bandBottom)
near3(et + eh / 2, B.BOT, "foot y"); near3(el, B.DOT_AX + S.BAND_PAD, "foot left"); near3(el + ew, B.DOT_AX + S.SC_W - S.BAND_PAD, "foot right")
near3(eh, LINE * S.BAND_BOT_W, "foot weight"); colA(P.bandBottom.color, rgb(MU.CSS.amber), S.BAND_BOT_A, "foot")
-- the foot's glow(K.amber, .8) is HALO's four nested strokes, wider and fainter outward, drawn UNDER the core line (plain blend, as the canvas)
check(#P.bandGlow == #HALO, "four glow strokes under the band foot, got " .. #P.bandGlow)
for i, gl in ipairs(P.bandGlow) do
    local gl_, gt_, gw_, gh_ = imgRect(gl)
    near3(gt_ + gh_ / 2, B.BOT, "glow stroke " .. i .. " y"); near3(gl_, B.DOT_AX + S.BAND_PAD, "glow stroke " .. i .. " left"); near3(gw_, S.SC_W - 2 * S.BAND_PAD, "glow stroke " .. i .. " width")
    near3(gh_, LINE * S.BAND_BOT_W + 2 * HALO[i][1], "glow stroke " .. i .. " thickness (core + 2 x reach)")
    colA(gl.color, rgb(MU.CSS.amber), S.BAND_BOT_A * S.BAND_GLOW_K * HALO[i][2], "glow stroke " .. i)
    check(gl.blend ~= "ADD", "glow stroke " .. i .. " blends plainly like the canvas")
end
-- RESEAL
local fs = P.reseal
check(fs.text == "RESEAL" and fs.justifyH == "CENTER", "RESEAL text")
check(math.abs(fs.monoSize - S.RESEAL_SIZE * SK) < 1e-6, "RESEAL font")
local cx, cy = imgCenter(fs)
near3(cx, S.GX, "RESEAL x"); near3(cy, (yb + B.BOT) / 2 + S.RESEAL_DY - FONT.CAP * S.RESEAL_SIZE, "RESEAL on the (yb + BOT) / 2 + 3.5 baseline")
colA(fs.textColor, rgb(MU.CSS.amber), S.RESEAL_A, "RESEAL")
""")

case("tube_matches_the_mockup")(r"""
local Seals = boot({ state = sealState("sor") })
local P = Seals.parts
local cx = B.DOT_AX + S.TX_DX
local l, t, w, h = imgRect(P.tube)
near3(l, cx - S.TW / 2, "tube left"); near3(w, S.TW, "tube width"); near3(t, B.TOP, "tube top"); near3(t + h, B.BOT, "tube bottom")
colA(P.tube.color, sealColor("righteousness"), S.TUBE_A, "tube track")
check(#P.rungs == 5, "five rungs (5 to 25 s), got " .. #P.rungs)
local k = 0
for s = S.RUNG_FROM, S.RUNG_TO - 1, S.RUNG_STEP do
    k = k + 1
    local rl, rt, rw, rh = imgRect(P.rungs[k])
    near3(rt + rh / 2, secY(s), "rung " .. s .. " y"); near3(rl, cx - S.TW / 2, "rung left"); near3(rw, S.TW, "rung width")
    colA(P.rungs[k].color, rgb(MU.CSS.bg), S.RUNG_A, "rung " .. s)
end
check(k == #P.rungs, "rung count")
check(#P.outline == 4, "four outline lines")
local th = LINE * S.OUT_W
local want = { { cx, B.TOP, S.TW, th }, { cx, B.BOT, S.TW, th }, { cx - S.TW / 2, (B.TOP + B.BOT) / 2, th, B.BOT - B.TOP }, { cx + S.TW / 2, (B.TOP + B.BOT) / 2, th, B.BOT - B.TOP } }
for i, wnt in ipairs(want) do
    local ol, ot, ow, oh = imgRect(P.outline[i])
    near3(ol + ow / 2, wnt[1], "outline " .. i .. " centre x"); near3(ot + oh / 2, wnt[2], "outline " .. i .. " centre y")
    near3(ow, wnt[3], "outline " .. i .. " width"); near3(oh, wnt[4], "outline " .. i .. " height")
    colA(P.outline[i].color, sealColor("righteousness"), S.OUT_A, "outline " .. i)
end
""")

case("lens_arcs_and_glyph_are_seated_on_the_lens_centre")(r"""
local Seals = boot({ state = sealState("sofu") })
local P = Seals.parts
local lens = MU.TEX.lens / MU.TEX.LENS_K
for _, name in ipairs({ "lens", "arcs" }) do
    local l, t, w, h = imgRect(P[name])
    near3(l + w / 2, S.GX, name .. " centre x"); near3(t + h / 2, S.GY, name .. " centre y")
    near3(w, lens, name .. " width (texels / 1.2)"); near3(h, lens, name .. " height")
end
check(texOf(P.lens) == "seal_lens.tga", "lens texture"); check(texOf(P.arcs) == "seal_arcs.tga", "arcs texture")
local gpx = MU.TEX.glyph.fury / MU.TEX.GLYPH_TEXELS_PER_PX
local gl, gt, gw, gh = imgRect(P.glyph)
near3(gl + gw / 2, S.GX, "glyph centre x"); near3(gt + gh / 2, S.GY, "glyph centre y"); near3(gw, gpx, "glyph width"); near3(gh, gpx, "glyph height")
local hl, ht, hw, hh = imgRect(P.glyphHalo)
near3(hl + hw / 2, S.GX, "halo centre x"); near3(ht + hh / 2, S.GY, "halo centre y"); local haloK, haloA = haloStandIn(S.GLYPH_GLOW_K, gpx)
near3(hw, gpx * haloK, "halo width: the glyph grown by the halo's mean reach")
check(P.glyphHalo.blend == "ADD", "the halo copy adds")
-- the seal name above and the caption below
local fs = P.name
local cx, cy = imgCenter(fs)
near3(cx, S.GX, "name x"); near3(cy, S.NAME_Y - FONT.CAP * fs.size, "name on the 541 baseline")
fs = P.caption
cx, cy = imgCenter(fs)
check(fs.text == "SEAL ACTIVE", "caption text")
near3(cx, S.GX, "caption x"); near3(cy, S.CAP_Y - FONT.CAP * S.CAP_SIZE, "caption on the 716 baseline")
check(math.abs(fs.monoSize - S.CAP_SIZE * SK) < 1e-6, "caption font")
""")

case("each_seal_gets_its_glyph_tint_name_and_colour")(r"""
local Seals = boot({ state = sealState("sor") })
local P = Seals.parts
check(Seals.Mode() == "seal", "the seed state painted")
for _, key in ipairs(ORDER) do
    local id = KEY_ID[key]
    local e = MU.SEALS[id]
    local col = rgb(e.c)
    push(sealState(key))
    local mode, sid = Seals.Mode()
    check(mode == "seal" and sid == id, key .. ": mode " .. tostring(mode) .. " id " .. tostring(sid))
    check(texOf(P.glyph) == "seal_glyph_" .. id .. ".tga", key .. ": glyph file " .. tostring(texOf(P.glyph)))
    check(texOf(P.glyphHalo) == "seal_glyph_" .. id .. ".tga", key .. ": halo file " .. tostring(texOf(P.glyphHalo)))
    colA(P.glyph.vertex, mix(col, WHITE, S.GLYPH_TINT), 1, key .. " glyph tint (col mixed .3 toward white)")
    colorIs(P.glyphHalo.vertex, col, key .. " halo colour")
    colA(P.lens.vertex, col, 1, key .. " lens"); colA(P.arcs.vertex, col, S.ARCS_A, key .. " arcs")
    colA(P.radial.vertex, col, S.RADIAL_A, key .. " radial wash")
    check(P.name.text == e.n, key .. ": name " .. tostring(P.name.text))
    colA(P.name.textColor, mix(col, WHITE, S.NAME_TINT), S.NAME_A, key .. " name")
    local wantSize = (#e.n > S.NAME_LONG) and S.NAME_SIZE_LONG or S.NAME_SIZE
    check(math.abs(P.name.monoSize - wantSize * SK) < 1e-6, key .. ": name font " .. tostring(P.name.monoSize / SK) .. ", want " .. wantSize)
    colA(P.caption.textColor, col, S.CAP_A, key .. " caption")
    colA(P.header.textColor, col, S.HDR_A, key .. " header")
    colA(tint(P.edge), col, S.EDGE_A0 + S.EDGE_A1, key .. " edge")
    colA(tint(P.glow), col, (S.EDGE_A0 + S.EDGE_A1) * coverage(S.GLOW_K0 + S.GLOW_K1), key .. " edge halo (the edge's alpha x the nested strokes' coverage at glow(col, .6 + .25))")
    check(vis(P.glow), key .. ": the edge halo is on")
    do
        local _, ha = haloStandIn(S.GLYPH_GLOW_K, 64)
        near3(P.glyphHalo.vertex[4], ha, key .. " glyph halo alpha")
    end
    colA(P.tube.color, col, S.TUBE_A, key .. " tube track")
    for i, o in ipairs(P.outline) do colA(o.color, col, S.OUT_A, key .. " outline " .. i) end
    local pa = S.PLATE_A * S.PLATE_FILL
    colA(P.plate.vertex, S.PLATE_RGB, pa, key .. " plate")
    for _, nm in ipairs({ "radial", "lens", "arcs", "glyphHalo", "glyph", "name", "caption", "reseal" }) do
        check(vis(P[nm]), key .. ": " .. nm .. " is shown")
    end
    for _, nm in ipairs({ "noSeal", "noSub", "noTime", "noHint" }) do check(not vis(P[nm]), key .. ": " .. nm .. " is hidden") end
    for s = 0, S.MAX_S, S.MAJ do colA(P.labels[s].textColor, rgb(MU.CSS.fg), S.LABEL_A, key .. " label " .. s) end
end
-- all seven keys of the profile are covered
local order = FS.HudProfiles.PALADIN.seals.order
check(#order == 7, "the profile lists seven seals")
for i, key in ipairs(order) do check(key == ORDER[i] and KEY_ID[key], "profile key " .. key .. " is mapped by the harness") end
""")

case("no_seal_is_the_red_chamber_with_the_seal_parts_gone")(r"""
local Seals = boot({ state = noneState(true) })
local P = Seals.parts
check(Seals.Mode() == "none", "mode none")
local red = rgb(MU.CSS.red)
local u = pulseAt(NOW)                           -- in combat the NO SEAL look pulses with the clock
colA(P.header.textColor, red, S.HDR_A, "header is red")
colA(tint(P.edge), red, S.NO_EDGE_A0 + S.NO_EDGE_A1 * u, "edge pulses red")
colA(tint(P.glow), red, (S.NO_EDGE_A0 + S.NO_EDGE_A1 * u) * coverage(u), "the red halo (edge alpha x coverage at glow(K.red, u))"); check(vis(P.glow), "the red halo is on")
colA(P.plate.vertex, S.PLATE_RGB, S.PLATE_A_NO * S.PLATE_FILL, "plate is denser with no seal")
for s = 0, S.MAX_S, S.MAJ do colA(P.labels[s].textColor, rgb(MU.CSS.fg), S.LABEL_A_NO, "dim label " .. s) end
colA(P.tube.color, rgb(MU.CSS.steel), S.TUBE_NO_A, "tube track is steel")
for i, o in ipairs(P.outline) do colA(o.color, rgb(MU.CSS.steel), S.OUT_NO_A, "outline " .. i .. " is steel") end
for _, nm in ipairs({ "radial", "lens", "arcs", "glyphHalo", "glyph", "name", "caption", "reseal" }) do check(not vis(P[nm]), nm .. " is hidden with no seal") end
local function check_text(fs, text, size, x, base, col, a, what)
    check(vis(fs) and fs.text == text, what .. ": text " .. tostring(fs.text))
    check(math.abs(fs.monoSize - size * SK) < 1e-6, what .. ": font")
    local cx, cy = imgCenter(fs)
    near3(cx, x, what .. " x"); near3(cy, base - FONT.CAP * size, what .. " baseline")
    colA(fs.textColor, col, a, what)
end
check_text(P.noSeal, "NO SEAL", S.NO_SIZE, S.GX, S.GY + S.NO_Y, red, 0.5 + 0.5 * u, "NO SEAL")
check_text(P.noSub, "IN COMBAT", S.NO_SUB_SIZE, S.GX, S.GY + S.NO_SUB_Y, red, S.NO_SUB_A, "IN COMBAT")
check_text(P.noTime, "--", S.NO_TIME_SIZE, S.GX - S.NO_TIME_DX, S.NO_TIME_Y, rgb(MU.CSS.muted), S.NO_TIME_A, "--")
check_text(P.noHint, "CAST A SEAL", S.NO_HINT_SIZE, S.GX, S.NO_HINT_Y, rgb(MU.CSS.muted), S.NO_HINT_A, "CAST A SEAL")
-- the band, the ruler and the Judgement lane stay
check(vis(P.band) and vis(P.bandBottom) and vis(P.tube) and vis(P.jAxis) and vis(P.ticks[1]), "frame furniture stays")
local set = textSet()
check(set["RESEAL"] == nil and set["SEAL ACTIVE"] == nil, "no RESEAL or SEAL ACTIVE with no seal")
check(set["NOT JUDGED"] == nil and set["NO DEBUFF"] == nil, "no empty lane label with no seal (the mockup draws '')")
""")

case("an_unknown_seal_draws_no_seal_and_no_cry")(r"""
local function expectUnknown(Seals, what)
    local P = Seals.parts
    check(Seals.Mode() == "unknown", what .. ": mode " .. tostring(Seals.Mode()))
    for _, nm in ipairs({ "radial", "lens", "arcs", "glyphHalo", "glyph", "name", "caption", "reseal", "noSeal", "noSub", "noTime", "noHint" }) do
        check(not vis(P[nm]), what .. ": " .. nm .. " is shown on an unknown seal")
    end
    local v = rgb(MU.CSS.violet)
    colA(P.header.textColor, v, S.HDR_A, what .. " header is violet")
    colA(tint(P.edge), v, S.EDGE_A0, what .. " edge")
    check(not vis(P.glow), what .. ": no halo")
    colA(P.tube.color, rgb(MU.CSS.steel), S.TUBE_NO_A, what .. " tube")
    check(vis(P.band) and vis(P.ticks[1]) and vis(P.jAxis), what .. ": furniture")
end
-- the default before any push
expectUnknown(boot({}), "no push yet")
-- nil seal in a pushed state
local Seals = boot({})
push(sealState("sor")); check(Seals.Mode() == "seal", "setup")
push(unknownState()); expectUnknown(Seals, "nil seal")
-- the other ways to be unknown
for what, state in pairs({
    ["a string state"] = "x", ["a number seal"] = (function() local s = unknownState(); s.seal = 5; return s end)(),
    ["a number key"] = (function() local s = sealState("sor"); s.seal.key = 7; return s end)(),
    ["an unmapped key"] = (function() local s = sealState("sor"); s.seal.key = "nope"; return s end)(),
    ["no key"] = (function() local s = sealState("sor"); s.seal.key = nil; return s end)(),
    ["a secret seal"] = (function() local s = unknownState(); s.seal = SECRET; return s end)(),
    ["a secret key"] = (function() local s = sealState("sor"); s.seal.key = SECRET; return s end)(),
    ["a secret state"] = SECRET,
}) do
    local S2 = boot({})
    push(sealState("sow")); check(S2.Mode() == "seal", "setup for " .. what)
    local ok, err = pcall(push, state)
    check(ok, what .. " threw out of the subscriber: " .. tostring(err))
    expectUnknown(S2, what)
    check(DEGRADED.gunsightseals_state == nil, what .. ": a plain unusable value is not a failure: " .. tostring(DEGRADED.gunsightseals_state))
end
-- a pushed state AFTER the unknown one recovers
local S3 = boot({})
push(unknownState()); expectUnknown(S3, "recover setup")
push(sealState("soj")); check(S3.Mode() == "seal" and select(2, S3.Mode()) == "justice", "recovers")
""")

case("transitions_repaint_only_when_the_look_changes")(r"""
local Seals = boot({})
local P = Seals.parts
local n = 0
local orig = P.glyph.SetTexture
P.glyph.SetTexture = function(self, p) n = n + 1; return orig(self, p) end
push(sealState("sor")); check(n == 1, "first seal writes the glyph once, got " .. n)
push(sealState("sor")); push(sealState("sor"))
check(n == 1, "the same seal again writes nothing, got " .. n)
local ns = 0
P.glyphHalo.SetTexture = function(self, p) ns = ns + 1 end
local st = sealState("sor"); st.seal.expiresAt = NOW + 5; st.seal.castAt = NOW - 25
push(st); check(n == 1 and ns == 0, "a ticking seal (same key) is not a new look")
push(sealState("sotc")); check(n == 2 and texOf(P.glyph) == "seal_glyph_crusader.tga", "a new seal rewrites the glyph")
push(noneState()); check(Seals.Mode() == "none" and not vis(P.glyph), "to none hides the glyph")
push(noneState()); check(n == 2, "none again writes nothing")
push(sealState("sotc")); check(Seals.Mode() == "seal" and vis(P.glyph) and n == 3, "back from none shows the seal again")
check(not vis(P.noSeal), "the none cry is gone again")
push(unknownState()); push(sealState("soc")); check(texOf(P.glyph) == "seal_glyph_command.tga", "unknown to seal")
""")

case("the_name_is_reseated_once_per_seat_not_once_per_repaint")(r"""
local Seals = boot({})
local P = Seals.parts
local n = 0
local orig = FS.Theme.ApplyMono
FS.Theme.ApplyMono = function(fs, ...) if fs == P.name then n = n + 1 end return orig(fs, ...) end
for _, key in ipairs({ "sor", "sofu", "sor", "sotc", "sofu", "sor" }) do push(sealState(key)) end
n = 0
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(n == 1, "a rescale seats the name once, not once per earlier repaint: " .. n)
check(math.abs(P.name.monoSize - S.NAME_SIZE_LONG * FS.Layout.Scale() * SK) < 1e-6, "the long name keeps its size after the rescale: " .. P.name.monoSize)
push(sealState("sotc"))
check(math.abs(P.name.monoSize - S.NAME_SIZE * FS.Layout.Scale() * SK) < 1e-6, "a short name takes the short size after the rescale: " .. P.name.monoSize)
""")

case("the_hud_is_followed_only_while_the_dot_piece_is_on")(r"""
local Seals = boot({ state = sealState("sow") })
local P = Seals.parts
check(#SUBS == 1, "subscribed while the piece is on, got " .. #SUBS)
check(select(2, Seals.Mode()) == "wisdom" and texOf(P.glyph) == "seal_glyph_wisdom.tga", "the Hud's current state is painted at once")
local stale = SUBS[1]
FS.Gunsight.SetPiece("dot", false, true)
check(#SUBS == 0, "unsubscribed when the piece goes off, got " .. #SUBS)
check(not isVisible(Seals.frame), "hidden with the piece")
push(sealState("sofu"))
check(select(2, Seals.Mode()) == "wisdom", "a push while off changes nothing")
stale(sealState("soj"))
check(select(2, Seals.Mode()) == "wisdom", "a stale subscriber called after the hide is inert")
FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 1, "back on: subscribed again, got " .. #SUBS)
check(select(2, Seals.Mode()) == "fury", "back on: the newest state is painted at once (pushed while off), got " .. tostring(select(2, Seals.Mode())))
FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 1, "a repeated on does not subscribe twice")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", false, true)
check(#SUBS == 0, "a repeated off")
check(#AURA_TOUCHED == 0, "no aura API was read")
""")

case("a_piece_saved_off_is_never_subscribed")(r"""
local Seals = boot({ db = { gunsight = { pieces = { dot = false } } }, state = sealState("sor") })
check(#SUBS == 0, "no subscription while saved off")
check(not isVisible(Seals.frame), "hidden while saved off")
check(Seals.Mode() == "unknown", "and nothing was painted from the Hud")
FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 1 and Seals.Mode() == "seal", "turning it on subscribes and paints")
""")

case("the_dot_key_toggles_the_whole_chamber")(r"""
local Seals, Dots = boot({ state = sealState("soc") })
local P = Seals.parts
local function everything(on)
    for k, p in pairs(P) do
        if type(p) == "table" and p.kind then
            if p.shown ~= false then check(isVisible(p) == on, "part " .. k .. " visibility " .. tostring(isVisible(p)) .. ", want " .. tostring(on)) end
        end
    end
end
check(isVisible(Seals.frame), "on"); everything(true)
FS.Gunsight.SetPiece("dot", false, true)
check(not isVisible(Seals.frame) and not Dots.frame:IsShown(), "the dot key hides the chamber"); everything(false)
FS.Gunsight.SetPiece("dot", true, true)
check(isVisible(Seals.frame), "and shows it"); everything(true)
check(Seals.frame:IsShown(), "the chamber's own shown flag was never touched by the key")
""")

case("a_rescale_keeps_every_rect_and_colour")(r"""
for _, height in ipairs({ 1200, 1080 }) do
    local Seals = boot({ state = sealState("sol") })
    local P = Seals.parts
    local nf, nt, ns = #FRAMES, #TEXTURES, #FONTSTRINGS
    local before = {}
    for k, p in pairs(P) do if type(p) == "table" and p.kind == "Texture" and #p.points == 1 then before[k] = { imgRect(p) } end end
    local c1 = { P.glyph.vertex[1], P.glyph.vertex[2], P.glyph.vertex[3], P.glyph.vertex[4] }
    local lc = { P.labels[10].textColor[1], P.labels[10].textColor[2], P.labels[10].textColor[3], P.labels[10].textColor[4] }
    SetScreen(height); fire("UI_SCALE_CHANGED"); fire("DISPLAY_SIZE_CHANGED")
    for k, r in pairs(before) do
        local now = { imgRect(P[k]) }
        for i = 1, 4 do near3(now[i], r[i], "part " .. k .. " rect " .. i .. " at height " .. height) end
    end
    local l, t, w, h = imgRect(Seals.frame)
    near3(l, B.DOT_AX, "chamber left"); near3(w, S.SC_W, "chamber width"); near3(t, B.FR_T, "chamber top")
    near3(P.labels[10].monoSize, S.LABEL_SIZE * FS.Layout.Scale() * SK, "label font follows the scale")
    colA(P.glyph.vertex, c1, c1[4], "glyph tint after the rescale")
    colA(P.labels[10].textColor, lc, lc[4], "label colour after the rescale")
    colorIs(P.labels[10].monoColor, lc, "the colour handed to the font reapply is the painted one")
    check(texOf(P.glyph) == "seal_glyph_light.tga", "the glyph after the rescale")
    check(nf == #FRAMES and nt == #TEXTURES and ns == #FONTSTRINGS, "a rescale builds nothing")
end
""")

case("the_judgement_lane_geometry_matches_the_mockup")(r"""
local Seals = boot({ state = sealState("sotc") })
local P = Seals.parts
local al, at, aw, ah = imgRect(P.jAxis)
near3(al + aw / 2, S.JL_AX, "axis x"); near3(at, B.TOP - S.JL_AX_UP, "axis top"); near3(at + ah, B.BOT + S.JL_AX_DN, "axis bottom")
colA(P.jAxis.color, rgb(MU.CSS.violet), S.JL_AX_A, "axis")
check(#P.jTicks == S.JL_MAX_S + 1, "41 ticks")
for s = 0, S.JL_MAX_S do
    local len = s % S.JL_MAJ == 0 and S.JL_MAJ_LEN or (s % S.JL_MID == 0 and S.JL_MID_LEN or S.JL_MIN_LEN)
    local tl, tt, tw, th = imgRect(P.jTicks[s + 1])
    near3(tt + th / 2, jY(s), "Judgement tick " .. s .. " y"); near3(tl + tw, S.JL_AX, "tick right edge on the axis"); near3(tw, len, "tick " .. s .. " length")
    colA(P.jTicks[s + 1].color, rgb(MU.CSS.violet), S.JL_TICK_A, "Judgement tick " .. s)
end
for s = 0, S.JL_MAX_S do
    local fs = P.jLabels[s]
    if s % S.JL_MAJ == 0 then
        check(fs and fs.text == tostring(s), "Judgement label " .. s)
        local cx, cy = imgCenter(fs)
        near3(cx, S.JL_AX + S.LABEL_DX, "Judgement label x"); near3(cy, jY(s) + S.LABEL_DY - FONT.CAP * S.LABEL_SIZE, "Judgement label baseline")
        colA(fs.textColor, rgb(MU.CSS.fg), S.JL_LABEL_A, "Judgement label " .. s)
    else
        check(fs == nil, "no Judgement label at " .. s)
    end
end
check(#P.jGuide >= 20, "the guide is dashed, got " .. #P.jGuide)
local prevBottom
for i, d in ipairs(P.jGuide) do
    local dl, dt, dw, dh = imgRect(d)
    near3(dl + dw / 2, S.JL_X, "guide x")
    if i < #P.jGuide then near3(dh, S.JL_GUIDE_DASH[1], "guide dash") else check(dh <= S.JL_GUIDE_DASH[1] + 1e-3, "last guide dash is clipped") end
    if i == 1 then near3(dt, B.TOP, "first guide dash starts at the top") end
    if prevBottom then near3(dt - prevBottom, S.JL_GUIDE_DASH[2], "guide gap") end
    prevBottom = dt + dh
    check(dt >= B.TOP - 1e-3 and dt + dh <= B.BOT + 1e-3, "guide inside the lane")
    colA(d.color, rgb(MU.CSS.violet), S.JL_GUIDE_A, "guide dash")
end
local jd = P.judged
check(jd.text == "JUDGED" and math.abs(jd.monoSize - 11 * SK) < 1e-6, "JUDGED header")
local jl, jt, jw, jh = imgRect(jd)
near3(jl, S.JL_X - S.JUDGED_DX, "JUDGED left"); near3(jt + jh, S.HDR_Y + 2.5, "JUDGED bottom on the same header seat")
colA(jd.textColor, rgb(MU.CSS.muted), S.JUDGED_A, "JUDGED (no debuff)")
-- the empty lane label: stacked upright letters centred on the guide, top to bottom
local function stackText()
    local out = {}
    for _, fs in ipairs(P.stack) do if vis(fs) then out[#out + 1] = fs end end
    local letters = {}
    for _, fs in ipairs(out) do letters[#letters + 1] = fs.text end
    return out, table.concat(letters)
end
local function checkStack(want, what)
    local list, text = stackText()
    check(text == want, what .. ": '" .. text .. "', want '" .. want .. "'")
    local pitch = FONT.MONO_ADV * S.JL_TEXT_SIZE + S.JL_TEXT_SP
    local cy = (B.TOP + B.BOT) / 2
    for i, fs in ipairs(list) do
        local cx, y = imgCenter(fs)
        near3(cx, S.JL_X + S.JL_TEXT_DX - FONT.CAP * S.JL_TEXT_SIZE, what .. " letter " .. i .. " x")
        near3(y, cy + (i - (#list + 1) / 2) * pitch, what .. " letter " .. i .. " y")
        check(math.abs(fs.monoSize - S.JL_TEXT_SIZE * SK) < 1e-6, what .. " letter font")
        colA(fs.textColor or fs.monoColor, rgb(MU.CSS.muted), S.JL_TEXT_A, what .. " letter " .. i)
    end
end
checkStack("NOT JUDGED", "Crusader (debuff 40 s)")
push(sealState("sor")); checkStack("NO DEBUFF", "Righteousness (no debuff)")
push(sealState("soj")); checkStack("NOT JUDGED", "Justice (debuff 10 s)")
push(noneState()); checkStack("", "no seal")
push(unknownState()); checkStack("", "unknown")
""")

case("v1_drops_are_absent")(r"""
local Seals = boot({ state = sealAt("sor", 100, 10) })
local P = Seals.parts
local ch = Seals.frame
local function inChamber(r)
    while r do if r == ch then return true end r = r.parent end
    return false
end
for _, f in ipairs(FRAMES) do
    if inChamber(f) then
        for name in pairs(f.scripts) do
            check((name == "OnUpdate" and f == ch) or (name == "OnEvent" and f == P.events),
                "a script other than the chamber's OnUpdate and the one event frame's OnEvent: " .. name)
        end
    end
end
for _, owner in ipairs(ANIM_OWNERS) do check(not inChamber(owner), "an animation group was created in the chamber") end
tick(2); tick(30)
local arcs, rings = 0, 0
for _, t in ipairs(TEXTURES) do
    if inChamber(t) then
        if texOf(t) == "seal_arcs.tga" then arcs = arcs + 1 end
        if texOf(t) == "seal_ring.tga" then rings = rings + 1 end
        check(t.gradient == nil or t == P.fill or t == P.jBarGlow or t == P.jBarCore, "a gradient texture (the scan sweep) in the chamber")
        check(t.rotation == nil and t.SetRotation == getmetatable(t).SetRotation, "a rotated texture")
        local p = (t.path or ""):lower()
        check(not p:find("scan") and not p:find("comet") and not p:find("judge") and not p:find("chip"), "a dropped texture: " .. p)
    end
end
check(arcs == 1, "one arcs file: the static arcs, not the turning arcs and not the Judgement ring, got " .. arcs)
local arcsShown = 0
for _, t in ipairs(TEXTURES) do if inChamber(t) and texOf(t) == "seal_arcs.tga" and isVisible(t) then arcsShown = arcsShown + 1 end end
check(arcsShown == 1, "the arcs texture shows at rest, got " .. arcsShown)
check(rings == 1, "one ring texture: the Judgement ring (seal_ring.tga), got " .. rings)
for _, t in ipairs(TEXTURES) do if inChamber(t) and texOf(t) == "seal_ring.tga" then check(not isVisible(t), "the Judgement ring is hidden at rest") end end
local glyphs = 0
for _, t in ipairs(TEXTURES) do if inChamber(t) and (t.path or ""):find("seal_glyph_") then glyphs = glyphs + 1 end end
check(glyphs == 2, "the glyph and its halo copy only, no judge chip glyph: " .. glyphs)
-- with a debuff on the lane: the chip wears the spell icon, still no glyph file, comet or target box flash
C_Spell = { GetSpellTexture = function() return 135959 end }
local S2 = boot({ state = judgedState("sotc", 30, 0) })
tick(.1)
local glyphs2, icons = 0, 0
for _, t in ipairs(TEXTURES) do
    if t.parent and (t.parent == S2.frame or t.parent.parent == S2.frame) then
        local p = (t.path ~= nil and tostring(t.path) or ""):lower()
        if p:find("seal_glyph_") then glyphs2 = glyphs2 + 1 end
        if t == S2.parts.jChip.icon and t.path == 135959 then icons = icons + 1 end
        check(not p:find("comet") and not p:find("scan") and not p:find("judge") and not p:find("chip"), "a dropped texture with a debuff up: " .. p)
    end
end
check(glyphs2 == 2, "a debuff does not add a glyph: " .. glyphs2)
check(icons == 1, "the chip's icon is the spell texture")
C_Spell = nil
boot({ state = sealAt("sor", 100, 10) })
-- no scanlines: no repeated 1 px red rows under the NO SEAL look
push(noneState())
local redRows = 0
for _, t in ipairs(TEXTURES) do
    if inChamber(t) and t.color and isVisible(t) and math.abs(t.color[1] - 1) < 1e-3 and math.abs(t.color[2] - 59 / 255) < 1e-3 then redRows = redRows + 1 end
end
check(redRows == 0, "red solid rows (scanlines) drawn: " .. redRows)
-- no countdown, no EXPIRING, no lsLive text
push(sealState("sor"))
local set = textSet()
for text in pairs(set) do
    check(text ~= "EXPIRING" and not text:match("^%d+%.%d$"), "text of a short seal drawn for a long one: " .. text)
end
-- only the ruler numbers and the known words are ever drawn
local allowed = { SEAL = true, JUDGED = true, RESEAL = true, ["SEAL ACTIVE"] = true, RIGHTEOUSNESS = true }
for text in pairs(set) do
    check(allowed[text] or text:match("^%d+$") or #text == 1, "unexpected text in the chamber: " .. text)
end
check(#AURA_TOUCHED == 0, "no aura API was read")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_failing_build_leaves_nothing_visible_and_never_throws")(r"""
-- the Theme helper throws mid build
local Seals = boot({ themeFix = function() FS.Theme.AddCut2Texture = function() error("boom") end end })
check(Seals.frame == nil and Seals.parts == nil, "a failed build exports nothing")
check(DEGRADED.gunsightseals_build ~= nil, "the failure is logged")
for _, f in ipairs(chamberFrames()) do check(not f:IsShown(), "the half built frame is hidden") end
check(#SUBS == 0, "and nothing subscribed")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 0, "a piece toggle after a failed build does not subscribe")
-- Theme missing a helper the file needs
local S2 = boot({ themeFix = function() FS.Theme.AddCut2Texture = nil end })
check(S2.frame == nil and DEGRADED.gunsightseals_notheme ~= nil, "a missing Theme helper is logged and builds nothing")
-- no piece frame to hang off
local S3 = boot({ noDots = true })
check(S3.frame == nil and DEGRADED.gunsightseals_nodots ~= nil, "no DoT piece frame is logged and builds nothing")
""")

case("a_failing_repaint_is_contained_and_retried")(r"""
local stateLogs = 0
local Seals = boot({ beforeSeals = function()
    local orig = FS.LogDegradeOnce
    FS.LogDegradeOnce = function(key, msg) if key == "gunsightseals_state" then stateLogs = stateLogs + 1 end return orig(key, msg) end
end })
local P = Seals.parts
local orig = P.glyph.SetTexture
P.glyph.SetTexture = function() error("boom") end
local ok = pcall(push, sealState("sor"))
check(ok, "the throw escaped the subscriber")
check(DEGRADED.gunsightseals_state ~= nil, "logged")
push(sealState("sor")); push(sealState("sor"))
check(stateLogs == 1, "the same failure is logged once (LogDegradeOnce does not dedupe), got " .. stateLogs)
P.glyph.SetTexture = orig
push(sealState("sor"))
check(Seals.Mode() == "seal" and texOf(P.glyph) == "seal_glyph_righteousness.tga", "the same state is applied on the next push (the failed paint did not latch)")
""")

case("a_missing_hud_subscribe_is_logged_and_leaves_the_chamber_standing")(r"""
local Seals = boot({ beforeSeals = function() FS.Hud.Subscribe = nil end })
check(Seals.frame ~= nil and isVisible(Seals.frame), "the chamber still stands")
check(DEGRADED.gunsightseals_nohud ~= nil, "logged")
check(Seals.Mode() == "unknown", "and shows the unknown look")
""")

case("no_aura_api_is_ever_read")(r"""
local Seals = boot({ state = sealState("sor") })
for _, key in ipairs(ORDER) do push(sealState(key)) end
push(noneState()); push(unknownState())
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
SetScreen(1080); fire("UI_SCALE_CHANGED")
IN_COMBAT = true; fire("PLAYER_REGEN_DISABLED"); tick(1); fire("PLAYER_REGEN_ENABLED")
check(#AURA_TOUCHED == 0, "an aura API was read: " .. tostring(AURA_TOUCHED[1]))
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")


case("the_in_combat_label_shows_only_in_combat")(r"""
local Seals = boot({ state = noneState(false) })
local P = Seals.parts
local function labels(sub, what)
    check(Seals.Mode() == "none", what .. ": the NO SEAL look")
    check(vis(P.noSeal) and vis(P.noTime) and vis(P.noHint), what .. ": NO SEAL, -- and CAST A SEAL stay")
    check(vis(P.noSub) == sub, what .. ": IN COMBAT " .. (sub and "shown" or "hidden") .. ", got " .. tostring(vis(P.noSub)))
end
labels(false, "no seal out of combat")
push(noneState(true)); labels(true, "no seal in combat")
push(noneState(false)); labels(false, "back out of combat")
push(noneState(nil)); labels(false, "no combat flag at all")
push(noneState("yes")); labels(false, "a non boolean flag is not combat")
-- the repaint is written only when the combat flag changes, and a seal never repaints on it
local writes = 0
local orig = P.noSub.SetShown
P.noSub.SetShown = function(self, v) writes = writes + 1; return orig(self, v) end
push(noneState(false)); push(noneState(false))
check(writes == 0, "the same combat state again writes nothing, got " .. writes)
push(noneState(true)); check(writes == 1, "a combat change repaints once, got " .. writes)
push(noneState(true)); check(writes == 1, "and not again, got " .. writes)
push(sealState("sor"))
local n = 0
local o2 = P.glyph.SetTexture
P.glyph.SetTexture = function(self, path) n = n + 1; return o2(self, path) end
local st = sealState("sor"); st.inCombat = true
push(st); check(n == 0, "a seal does not repaint when combat starts, got " .. n)
check(not vis(P.noSub), "IN COMBAT is a NO SEAL label only")
-- a secret flag is never read as true (the guard comes first: a plain true flagged as secret must not show the label)
local S2 = boot({})
SECRET_FN = function(v) return v == true end
push(noneState(true))
check(S2.Mode() == "none" and not vis(S2.parts.noSub), "a secret combat flag shows no IN COMBAT")
SECRET_FN = function(v) return rawequal(v, SECRET) end
push(noneState(true)); check(vis(S2.parts.noSub), "and the plain flag shows it again")
push(noneState(SECRET)); check(S2.Mode() == "none" and not vis(S2.parts.noSub), "a secret table flag shows nothing and throws nothing")
check(DEGRADED.gunsightseals_state == nil, "no failure was logged: " .. tostring(DEGRADED.gunsightseals_state))
""")

case("every_part_draws_in_the_mockups_order")(r"""
local Seals = boot({ state = sealState("sor") })
local P, ch = Seals.parts, Seals.frame
local LAYER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4 }
local function z(t)
    check(LAYER[t.layer], "an unknown draw layer " .. tostring(t.layer))
    return LAYER[t.layer] * 100 + (t.sublevel or 0)
end
local function members(name)
    check(P[name] ~= nil, "part " .. name .. " is missing")
    if P[name].kind then return { P[name] } end
    return P[name]
end
local function rect(t, name)
    if name == "plate" or name == "edge" then return imgRect(ch) end
    if name == "glow" then local l, tp, w, h = imgRect(ch); return l - 4, tp - 4, w + 8, h + 8 end
    return imgRect(t)
end
local function overlap(a, b)
    local al, at, aw, ah = unpack(a)
    local bl, bt, bw, bh = unpack(b)
    return al < bl + bw - 1e-6 and bl < al + aw - 1e-6 and at < bt + bh - 1e-6 and bt < at + ah - 1e-6
end
local order = MU.ORDER
check(#order == 20, "twenty drawn parts in the mockup's sequence, got " .. #order)
local pairsChecked = 0
for i = 1, #order - 1 do
    for j = i + 1, #order do
        for _, a in ipairs(members(order[i])) do
            for _, b in ipairs(members(order[j])) do
                if overlap({ rect(a, order[i]) }, { rect(b, order[j]) }) then
                    pairsChecked = pairsChecked + 1
                    check(z(a) < z(b), string.format("%s (%s %s) must draw under %s (%s %s): the mockup draws it first",
                        order[i], a.layer, tostring(a.sublevel), order[j], b.layer, tostring(b.sublevel)))
                end
            end
        end
    end
end
check(pairsChecked >= 40, "the order check saw too few overlapping pairs: " .. pairsChecked)
-- every label sits above every texture of the chamber (the plate is under the labels)
local top = LAYER.OVERLAY * 100
local texts = 0
for _, f in ipairs(FONTSTRINGS) do
    if f.layer ~= nil and f.parent == ch then
        texts = texts + 1
        check(f.layer == "OVERLAY", "a label on " .. tostring(f.layer) .. ", want OVERLAY (" .. tostring(f.text) .. ")")
    end
end
check(texts >= 30, "fewer labels than expected: " .. texts)
for _, t in ipairs(TEXTURES) do
    if t.parent == ch then check(z(t) < top, "a texture draws at or above the labels: " .. tostring(t.layer) .. " " .. tostring(t.sublevel)) end
end
-- the sublevels stay inside the engine's -8..7 range
for _, t in ipairs(TEXTURES) do
    if t.parent == ch then check((t.sublevel or 0) >= -8 and (t.sublevel or 0) <= 7, "sublevel out of range: " .. tostring(t.sublevel)) end
end
""")

case("a_late_profile_builds_the_chamber_when_it_arrives")(r"""
-- the Hud has no profile yet when the pieces build (HudLogic has no change hook): the answer comes later
local Seals, Dots = boot({ class = "PALADIN", mkProfile = function() return nil end, state = sealState("sow") })
check(Seals.frame == nil, "no profile, no chamber yet")
check(Dots.frame ~= nil, "setup: the DoT file built its piece frame")
check(#chamberFrames() == 0, "no chamber frame yet")
PROFILE = FS.HudProfiles.PALADIN
check(Seals.frame == nil, "the profile arriving alone builds nothing (no event frame listens)")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
Seals = FS.GunsightSeals
check(Seals.frame ~= nil and #chamberFrames() == 1, "a piece change asks again and builds the chamber")
check(Seals.frame:GetParent() == Dots.frame, "late chamber is a child of the dot piece frame")
check(select(2, Seals.Mode()) == "wisdom", "and it paints the Hud's current state, got " .. tostring(select(2, Seals.Mode())))
local n = 0
for _, fn in ipairs(SUBS) do if fn ~= nil then n = n + 1 end end
check(n >= 1, "the late chamber follows the Hud")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
check(#chamberFrames() == 1, "asking again builds nothing more")
-- a rescale asks too
local S2, D2 = boot({ class = "PALADIN", mkProfile = function() return nil end, state = sealState("sor") })
check(S2.frame == nil, "setup: nothing yet")
PROFILE = FS.HudProfiles.PALADIN
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(FS.GunsightSeals.frame ~= nil, "a rescale asks again and builds the chamber")
-- the late answer "dots" is final: a Warlock never gets a chamber later
local S3 = boot({ class = "WARLOCK", state = nil })
check(S3.frame == nil, "setup: a Warlock has no chamber")
PROFILE = FS.HudProfiles.PALADIN
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
SetScreen(1080); fire("UI_SCALE_CHANGED")
check(FS.GunsightSeals.frame == nil and #chamberFrames() == 0, "a decided class never builds later")
-- a profile that is still missing at every retry builds nothing and logs nothing
local S4 = boot({ class = "ROGUE" })
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(S4.frame == nil and next(DEGRADED) == nil or (DEGRADED.gunsightseals_nopiece == nil and DEGRADED.gunsightseals_build == nil),
    "a class with no profile stays silent")
""")

case("a_dot_piece_that_never_registered_leaves_the_chamber_unbuilt")(r"""
local logs = 0
local Seals, Dots = boot({
    themeFix = function() FS.TargetTakesDots = function() error("boom") end end,
    beforeSeals = function()
        local orig = FS.LogDegradeOnce
        FS.LogDegradeOnce = function(key, msg) if key == "gunsightseals_nopiece" then logs = logs + 1 end return orig(key, msg) end
    end,
})
check(Dots.frame ~= nil, "setup: the DoT file's frame exists although its build threw")
check(not Dots.registered, "setup: the DoT piece never registered")
check(Seals.frame == nil and #chamberFrames() == 0, "no chamber hangs off an unregistered piece frame")
check(logs == 1, "the missing piece is logged once, got " .. logs)
check(#SUBS == 0, "and nothing subscribed to the Hud")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(#chamberFrames() == 0 and logs == 1, "later asks neither build nor log again, got " .. logs)
-- a registered piece is the normal case
local S2, D2 = boot({})
check(D2.registered == true and S2.frame ~= nil, "a registered piece gets its chamber")
""")

case("a_secret_string_seal_key_is_never_compared_or_indexed")(r"""
local Seals = boot({})
SECRET_FN = function(v) return v == "sor" end           -- "sor" is a secret string in this case
push(sealState("sofu")); check(select(2, Seals.Mode()) == "fury", "setup: an unflagged key paints")
local ok, err = pcall(push, sealState("sor"))
check(ok, "a secret string key threw out of the subscriber: " .. tostring(err))
check(Seals.Mode() == "unknown", "a secret string key is an unknown look, got " .. tostring(Seals.Mode()))
check(not vis(Seals.parts.glyph) and not vis(Seals.parts.noSeal), "no seal and no NO SEAL cry")
check(DEGRADED.gunsightseals_state == nil, "a plain secret is not a failure: " .. tostring(DEGRADED.gunsightseals_state))
SECRET_FN = function(v) return rawequal(v, SECRET) end
push(sealState("sor")); check(select(2, Seals.Mode()) == "righteousness", "and the same key unflagged paints again")
-- the secret seal TABLE holding a plain key is unknown too, without reading the key
SECRET_FN = function(v) return rawequal(v, SECRET) end
local st = sealState("sor"); st.seal = SECRET
push(st); check(Seals.Mode() == "unknown", "a secret seal table is unknown")
""")


case("drain_fill_and_tip_follow_the_seal_time")(r"""
local Seals = boot({ state = sealAt("sor", 20, 10) })
local P, C = Seals.parts, Seals.C
local cx = B.DOT_AX + S.TX_DX
local col, amber = sealColor("righteousness"), rgb(MU.CSS.amber)
local function drain(rem, tcol, what)
    for _, nm in ipairs({ "fill", "tipBar", "tipDot" }) do check(vis(P[nm]), what .. ": " .. nm .. " is shown") end
    local l, t, w, h = imgRect(P.fill)
    near3(l, cx - S.TW / 2, what .. ": fill left"); near3(w, S.TW, what .. ": fill width")
    near3(t, secY(rem), what .. ": fill top is secY(rem)"); near3(t + h, B.BOT, what .. ": fill foot is the tube foot")
    local g = P.fill.gradient
    check(g and g.orientation == "VERTICAL", what .. ": a vertical gradient")
    near3(g.min.a, S.FILL_A0, what .. ": tail alpha"); near3(g.max.a, 1, what .. ": tip alpha")
    colorIs({ g.min.r, g.min.g, g.min.b }, tcol, what .. ": tail colour"); colorIs({ g.max.r, g.max.g, g.max.b }, tcol, what .. ": tip colour")
    local bl, bt, bw, bh = imgRect(P.tipBar)
    near3(bl, cx - S.TW / 2, what .. ": tip bar left"); near3(bw, S.TW, what .. ": tip bar width")
    near3(bt, secY(rem), what .. ": tip bar top"); near3(bh, S.TIP_H, what .. ": tip bar height")
    colorIs(P.tipBar.color, mix(tcol, WHITE, S.TIP_MIX), what .. ": tip bar colour")
    near3(P.tipBar.color[4], S.TIP_A, what .. ": tip bar alpha")
    local dl, dt, dw, dh = imgRect(P.tipDot)
    near3(dl + dw / 2, cx, what .. ": dot x"); near3(dt + dh / 2, secY(rem), what .. ": dot y")
    near3(dw, 2 * S.DOT_R / C.GLOW_HALF, what .. ": dot size (a soft disc of radius DOT_R at half alpha)"); near3(dh, dw, what .. ": dot square")
    check(texOf(P.tipDot) == "glow_round.tga", what .. ": the dot is the round glow")
    colorIs(P.tipDot.vertex, mix(tcol, WHITE, S.DOT_MIX), what .. ": dot colour")
end
drain(20, col, "rem 20")
tick(5); drain(15, col, "rem 15")
tick(7.5); drain(7.5, col, "rem 7.5")
tick(2.5); drain(5, col, "rem 5")
tick(1.75); drain(3.25, col, "rem 3.25")
-- the tube holds 30 s: a longer seal clamps at the top
local S2 = boot({ state = sealAt("sor", 35, 10) })
local l, t, w, h = imgRect(S2.parts.fill)
near3(t, B.TOP, "35 s of seal fills the whole tube, not past it"); near3(t + h, B.BOT, "to the foot")
-- the fill rests at 0.05 s: just above it shows, at or under it hides with the tip
local S3 = boot({ state = sealAt("sor", 0.0625, 10) })
check(vis(S3.parts.fill) and vis(S3.parts.tipBar) and vis(S3.parts.tipDot), "0.0625 s is above FILL_MIN: the drain shows")
local S4 = boot({ state = sealAt("sor", 0.03125, 10) })
for _, nm in ipairs({ "fill", "tipBar", "tipDot" }) do check(not vis(S4.parts[nm]), nm .. " hides at 0.03125 s (under FILL_MIN)") end
for _, nm in ipairs({ "count", "countS" }) do check(vis(S4.parts[nm]), nm .. " stays at 0.03125 s: the mockup gates only the tube on rem > .05") end
check(S4.parts.count.text == "0.0", "the countdown reads 0.0 under FILL_MIN, got " .. tostring(S4.parts.count.text))
-- the count walks 0.2, 0.1, 0.0 into the expiry, then goes with the seal
local S6 = boot({ state = sealAt("sor", 0.25, 10) })
check(S6.parts.count.text == "0.3", "0.25 s reads 0.3, got " .. tostring(S6.parts.count.text))
tick(.125); check(vis(S6.parts.count) and S6.parts.count.text == "0.1", "0.125 s reads 0.1, got " .. tostring(S6.parts.count.text))
tick(.0625); check(vis(S6.parts.count) and S6.parts.count.text == "0.1", "0.0625 s reads 0.1")
tick(.03125); check(vis(S6.parts.count) and S6.parts.count.text == "0.0" and not vis(S6.parts.fill), "0.03125 s reads 0.0 with the tube gone")
tick(.1); check(not vis(S6.parts.count) and S6.Mode() == "none", "the count goes with the seal at the expiry")
check(vis(S4.parts.glyph), "the seal look itself stays")
-- an unknown or unreadable time draws no drain, no countdown and claims nothing
for what, mk in pairs({
    ["no expiry"] = function(s) s.seal.expiresAt = nil end,
    ["a secret expiry"] = function(s) s.seal.expiresAt = SECRET end,
    ["a string expiry"] = function(s) s.seal.expiresAt = "soon" end,
    ["a NaN expiry"] = function(s) s.seal.expiresAt = 0 / 0 end,
    ["an infinite expiry"] = function(s) s.seal.expiresAt = math.huge end,
    ["a negative infinite expiry"] = function(s) s.seal.expiresAt = -math.huge end,
}) do
    local st = sealAt("sor", 20, 10); mk(st)
    local S5 = boot({ state = st })
    for _, nm in ipairs({ "fill", "tipBar", "tipDot", "count", "countS" }) do check(not vis(S5.parts[nm]), what .. ": " .. nm .. " is hidden") end
    check(S5.Mode() == "seal" and vis(S5.parts.glyph), what .. ": the seal look stays")
    check(onUpdateFrames() == 0, what .. ": nothing to animate, no ticker")
    check((S5.parts.count.text or "") == "", what .. ": the countdown holds no text")
    tick(1)
    check(next(DEGRADED) == nil, what .. ": no degrade: " .. tostring(next(DEGRADED)))
end
""")

case("the_countdown_and_its_s_follow_the_seal_time")(r"""
local Seals = boot({ state = sealAt("sor", 20, 10) })
local P = Seals.parts
local col, amber = sealColor("righteousness"), rgb(MU.CSS.amber)
local sets = 0
local origSet = P.count.SetText
P.count.SetText = function(self, t) sets = sets + 1; return origSet(self, t) end
local function counting(text, tcol, what)
    checkText(P.count, text, S.COUNT_SIZE, S.GX - S.COUNT_DX, S.COUNT_Y, what)
    check(P.count.justifyH == "CENTER", what .. ": centred")
    colorIs(P.count.textColor, tcol, what .. ": colour")
    checkText(P.countS, "S", S.S_SIZE, S.GX - S.COUNT_DX + #text * FONT.MONO_ADV * S.COUNT_SIZE / 2 + S.S_GAP, S.COUNT_Y, what .. " S")
    check(P.countS.justifyH == "LEFT", what .. ": the S is left aligned")
    colorIs(P.countS.textColor, rgb(MU.CSS.muted), what .. ": the S is muted")
end
counting("20", col, "rem 20")
local pointsBefore, countPoints = P.countS.setPointCalls, P.count.setPointCalls
for _, e in ipairs({ { .5, "20" }, { .5, "19" }, { 9, "10" }, { 4.5, "6" }, { .5, "5.0" }, { .75, "4.3" }, { 3.25, "1.0" }, { .75, "0.3" } }) do
    tick(e[1]); counting(e[2], e[2] == "0.3" and amber or (e[2] == "1.0" and amber or (e[2] == "4.3" and col or col)), "text " .. e[2])
end
check(sets == 7, "the text is written only when it changes: 7 changes, got " .. sets)
check(P.countS.setPointCalls - pointsBefore == 2, "the S is re-seated only when the text length changes (twice), got " .. (P.countS.setPointCalls - pointsBefore))
check(P.count.setPointCalls == countPoints, "the number itself is never re-seated by a tick")
-- tenths round half up, and the drain is still up at 0.0625 s
tick(.1875); checkText(P.count, "0.1", S.COUNT_SIZE, S.GX - S.COUNT_DX, S.COUNT_Y, "rem 0.0625")
""")

case("the_reseal_band_lights_at_three_seconds")(r"""
local Seals = boot({ state = sealAt("sor", 3.5, 10) })
local P, C = Seals.parts, Seals.C
local col, amber = sealColor("righteousness"), rgb(MU.CSS.amber)
local made = 0
local oc = CreateColor
CreateColor = function(...) made = made + 1; return oc(...) end
local function look(inBand, what)
    local tcol = inBand and amber or col
    local pl = inBand and (0.5 + 0.5 * math.sin(NOW * S.BAND_PL_FREQ)) or 0
    colA(P.band.color, amber, S.BAND_FILL + S.BAND_PL * pl, what .. ": band wash")
    colA(P.reseal.textColor, amber, inBand and (S.RESEAL_IN0 + S.RESEAL_IN1 * pulseAt(NOW)) or S.RESEAL_A, what .. ": RESEAL")
    colA(P.tube.color, tcol, S.TUBE_A, what .. ": tube track")
    for i, o in ipairs(P.outline) do colA(o.color, tcol, S.OUT_A, what .. ": outline " .. i) end
    local g = P.fill.gradient
    colorIs({ g.min.r, g.min.g, g.min.b }, tcol, what .. ": fill tail"); colorIs({ g.max.r, g.max.g, g.max.b }, tcol, what .. ": fill tip")
    near3(g.min.a, S.FILL_A0, what .. ": fill tail alpha"); near3(g.max.a, 1, what .. ": fill tip alpha")
    colorIs(P.tipBar.color, mix(tcol, WHITE, S.TIP_MIX), what .. ": tip bar")
    colorIs(P.tipDot.vertex, mix(tcol, WHITE, S.DOT_MIX), what .. ": tip dot")
    colorIs(P.count.textColor, tcol, what .. ": countdown")
    colorIs(P.lens.vertex, col, what .. ": the lens keeps the seal colour")
    colorIs(P.arcs.vertex, col, what .. ": the arcs keep the seal colour")
    colorIs(P.header.textColor, col, what .. ": the header keeps the seal colour")
    colorIs(P.name.textColor, mix(col, WHITE, S.NAME_TINT), what .. ": the name keeps the seal colour")
end
look(false, "rem 3.5")
tick(.25); look(false, "rem 3.25")
tick(.25); look(true, "rem 3.0 (the threshold is inclusive)")
tick(.5); look(true, "rem 2.5")
tick(.375); look(true, "rem 2.125 (the band wash pulses with the clock)")
check(made == 0, "flipping into the band builds no colour object, made " .. made)
-- a recast with plenty of time drops out of the band at once
push(sealAt("sor", 20, 0)); look(false, "recast")
-- the band cue is a seal look: no band cue without a seal, and the wash rests at its static alpha
push(noneState(true))
colA(P.band.color, amber, S.BAND_FILL, "no seal: the band wash rests")
colA(P.reseal.textColor, amber, S.RESEAL_A, "no seal: RESEAL rests")
CreateColor = oc
""")

case("the_strike_flicker_runs_after_a_cast_and_a_recast_restarts_it")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 0.05) })
local P = Seals.parts
checkNeon(Seals, S.STRIKE[1], "age 0.05")
for i, want in ipairs({ { .15, .9 }, { .25, .1 }, { .35, .7 }, { .45, .3 }, { .55, 1 }, { .65, .6 }, { .75, 1 } }) do
    tick(.1); checkNeon(Seals, want[2], "age " .. want[1])
    near3(P.caption.textColor[4], S.CAP_A, "age " .. want[1] .. ": the SEAL ACTIVE caption keeps its alpha through a strike")
end
tick(5); checkNeon(Seals, 1, "age 5.75: steady")
-- a recast of the SAME seal (a new castAt) restarts it at once
push(sealAt("sor", 30, 0.05)); checkNeon(Seals, .2, "recast: the first step")
tick(.2); checkNeon(Seals, .1, "recast: age 0.25")
-- the same state pushed again is not a recast
push(sealAt("sor", 30, 0.25)); checkNeon(Seals, .1, "the same cast pushed again does not restart it")
-- a new seal is a new strike
push(sealAt("sotc", 30, 0.05)); checkNeon(Seals, .2, "a new seal strikes up")
-- the strike is over after the window and a very old cast never strikes
local S2 = boot({ state = sealAt("sor", 20, 100) })
checkNeon(S2, 1, "an old cast is steady")
local S3 = boot({ state = (function() local s = sealAt("sor", 20, 10); s.seal.castAt = nil; return s end)() })
checkNeon(S3, 1, "no castAt: steady, no strike")
local S4 = boot({ state = (function() local s = sealAt("sor", 20, 10); s.seal.castAt = NOW + 100; return s end)() })
checkNeon(S4, 1, "a castAt in the future: steady")
""")

case("the_tube_dies_out_in_the_last_five_seconds")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 6, 10) })
local P = Seals.parts
local amber = rgb(MU.CSS.amber)
local function caption(ex, what)
    check(P.caption.text == (ex and "EXPIRING" or "SEAL ACTIVE"), what .. ": caption " .. tostring(P.caption.text))
    colorIs(P.caption.textColor, ex and amber or sealColor("righteousness"), what .. ": caption colour")
end
checkNeon(Seals, 1, "rem 6"); caption(false, "rem 6")
tick(.5); checkNeon(Seals, 1, "rem 5.5: not yet"); caption(false, "rem 5.5")
tick(.5)                                     -- rem 5 exactly: the mockup's rem <= 5
caption(true, "rem 5")
local low, dropouts, steady = 1, 0, 0
for i = 1, 160 do
    local rem = NOW + (6 - 1) - NOW + 0   -- placeholder to keep the arithmetic below honest
    rem = (5000 + 6) - NOW
    local e = Seals.Neon(10, true, rem, NOW)
    checkNeon(Seals, e, string.format("rem %.4f at %.4f", rem, NOW))
    near3(P.caption.textColor[4], S.CAP_A * e, "the EXPIRING caption follows the neon")
    if e < 0.5 then dropouts = dropouts + 1 else steady = steady + 1 end
    if e < low then low = e end
    check(e >= S.DROP_LO - 1e-9 and e <= 1 + 1e-9, "neon stays in its range: " .. e)
    tick(1 / 32)
end
check(dropouts >= 5 and steady >= 5, "the last 5 s mix dropouts and steady glow: " .. dropouts .. " dark, " .. steady .. " lit")
check(low < S.DROP_LO + S.DROP_SPAN + 1e-9, "a dropout reaches the dark band: " .. low)
-- expiring wins over a fresh strike
local S2 = boot({ state = sealAt("sor", 4.5, 0.05) })
checkNeon(S2, S2.Neon(0.05, true, 4.5, NOW), "expiring wins over the strike")
check(S2.parts.caption.text == "EXPIRING", "a fresh cast of a short seal still says EXPIRING")
-- a longer seal after a recast goes back to steady and SEAL ACTIVE
push(sealAt("sor", 20, 10)); checkNeon(S2, 1, "recast with time: steady"); check(S2.parts.caption.text == "SEAL ACTIVE", "SEAL ACTIVE again")
colA(S2.parts.caption.textColor, sealColor("righteousness"), S.CAP_A, "SEAL ACTIVE again wears the seal colour")
-- a different seal repaints the caption too, even from EXPIRING
push(sealAt("sor", 4.5, 10)); check(S2.parts.caption.text == "EXPIRING", "expiring again")
push(sealAt("sotc", 20, 10)); check(S2.parts.caption.text == "SEAL ACTIVE", "a new seal after EXPIRING says SEAL ACTIVE")
colA(S2.parts.caption.textColor, sealColor("crusader"), S.CAP_A, "in the new seal's colour")
""")

case("no_seal_pulses_only_in_combat_with_a_known_empty_seal")(r"""
NOW = 5000
local Seals = boot({ state = noneState(true) })
local P = Seals.parts
local red = rgb(MU.CSS.red)
local function pulse(u, what)
    colA(tint(P.edge), red, S.NO_EDGE_A0 + S.NO_EDGE_A1 * u, what .. ": edge")
    colA(tint(P.glow), red, (S.NO_EDGE_A0 + S.NO_EDGE_A1 * u) * coverage(u), what .. ": halo")
    colorIs(P.noSeal.textColor, red, what .. ": NO SEAL colour"); near3(P.noSeal.textColor[4], 0.5 + 0.5 * u, what .. ": NO SEAL alpha")
    check(vis(P.glow), what .. ": the halo stays on")
end
pulse(pulseAt(NOW), "boot")
check(onUpdateFrames() == 1, "one OnUpdate while NO SEAL pulses, got " .. onUpdateFrames())
for i = 1, 12 do tick(.35); pulse(pulseAt(NOW), "t=" .. NOW) end
local lo, hi = 1, 0
for i = 1, 40 do tick(.07); local u = pulseAt(NOW); lo, hi = math.min(lo, u), math.max(hi, u) end
check(lo < .1 and hi > .9, "the pulse sweeps most of its range: " .. lo .. " to " .. hi)
-- leaving combat: the pulse stops at the resting mean
push(noneState(false)); pulse(Seals.C.NO_U, "out of combat")
check(onUpdateFrames() == 0, "no ticker for NO SEAL out of combat")
tick(1); tick(.3); pulse(Seals.C.NO_U, "out of combat, later")
push(noneState(true)); pulse(pulseAt(NOW), "back in combat"); check(onUpdateFrames() == 1, "pulsing again")
-- a seal does not pulse the red look, the unknown look never does
push(sealState("sor")); check(not vis(P.noSeal), "a seal draws no NO SEAL")
push(unknownState()); check(onUpdateFrames() == 0 and not vis(P.noSeal), "unknown in combat: no ticker, no cry")
local st = unknownState(); st.inCombat = true
push(st); check(onUpdateFrames() == 0, "an unknown seal in combat still does not animate")
""")

case("the_judgement_ring_leaves_the_sigil")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10, { judgeAt = NOW - 0.25 }) })
local P = Seals.parts
local rest = MU.TEX.ring / MU.TEX.RING_K          -- the ring texture at rest: its circle is the lens' own radius, SC_GR
local col = sealColor("righteousness")
local function ring(P, f, what)
    local p = easeOut(f / S.RING_S)
    check(vis(P.judgeRing), what .. ": the ring is shown")
    local l, t, w, h = imgRect(P.judgeRing)
    near3(l + w / 2, S.GX, what .. ": ring x"); near3(t + h / 2, S.GY, what .. ": ring y")
    near3(w, rest * (S.GR + p * S.RING_GROW) / S.GR, what .. ": ring size (radius GR + p * 26)"); near3(h, w, what .. ": square")
    check(texOf(P.judgeRing) == "seal_ring.tga", what .. ": the full circle texture, not the scaled arcs")
    colorIs(P.judgeRing.vertex, col, what .. ": ring colour"); near3(effA(P.judgeRing), S.RING_A * (1 - p), what .. ": ring alpha (.85 * (1 - p))")
end
ring(P, .25, "f .25")
tick(.125); ring(P, .375, "f .375")
tick(.25); ring(P, .625, "f .625")
tick(.25); ring(P, .875, "f .875")
tick(.0625); check(not vis(P.judgeRing), "at .9375 the ring is gone (the window is f < .9)")
tick(5); check(not vis(P.judgeRing), "and stays gone")
-- a fresh Judgement starts a ring at once, at the sigil's own size
push(sealAt("sor", 20, 10, { judgeAt = NOW })); ring(P, 0, "f 0")
near3(effA(P.judgeRing), S.RING_A, "the ring starts at .85")
-- no judgeAt, a stale one, one in the future, a secret one and a string one draw no ring and throw nothing
for what, v in pairs({ ["nil"] = false, stale = NOW - 100, future = NOW + 100, secret = SECRET, string = "now", nan = 0 / 0 }) do
    local st = sealAt("sor", 20, 10); if v ~= false then st.judgeAt = v end
    local S2 = boot({ state = st })
    check(not vis(S2.parts.judgeRing), what .. ": no ring")
    tick(1); check(next(DEGRADED) == nil, what .. ": no degrade: " .. tostring(next(DEGRADED)))
end
-- the ring needs a seal: none and unknown draw no ring
local S3 = boot({ state = noneState(true) })
local st = noneState(true); st.judgeAt = NOW
push(st); check(not vis(S3.parts.judgeRing), "no seal: no ring")
local st2 = unknownState(); st2.judgeAt = NOW
push(st2); check(not vis(S3.parts.judgeRing), "unknown: no ring")
-- it works with an unknown seal time too
local st3 = sealAt("sor", 20, 10, { judgeAt = NOW - .25 }); st3.seal.expiresAt = nil
local S4 = boot({ state = st3 })
ring(S4.parts, .25, "unknown time")
""")

case("the_ticker_runs_only_while_something_animates")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10) })
check(onUpdateFrames() == 1 and Seals.frame:GetScript("OnUpdate") ~= nil, "a timed seal: one OnUpdate, on the chamber")
local stale = SUBS[1]
FS.Gunsight.SetPiece("dot", false, true)
check(onUpdateFrames() == 0, "the piece off: no OnUpdate")
stale(sealAt("sor", 20, 10)); check(onUpdateFrames() == 0, "a stale push after the hide does not start it")
push(sealAt("sor", 20, 10)); check(onUpdateFrames() == 0, "nor does a push while off")
FS.Gunsight.SetPiece("dot", true, true); check(onUpdateFrames() == 1, "the piece back on: running again")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", false, true); check(onUpdateFrames() == 0, "a repeated off")
-- an unknown time and a stale cast and Judgement: nothing moves
local function untimed(extra) local s = sealAt("sor", 20, 100, extra); s.seal.expiresAt = nil; return s end
local S2 = boot({ state = untimed() })
check(onUpdateFrames() == 0, "an untimed old seal: no OnUpdate")
SetScreen(1200); fire("UI_SCALE_CHANGED"); check(onUpdateFrames() == 0, "a rescale of a resting chamber starts nothing")
-- an untimed seal just cast: the strike window only
push(untimed()); push((function() local s = sealAt("sor", 20, 0.05); s.seal.expiresAt = nil; return s end)())
check(onUpdateFrames() == 1, "an untimed fresh cast: the strike runs")
tick(.5); check(onUpdateFrames() == 1, "still inside the window")
tick(.25); check(onUpdateFrames() == 0, "the window is over: the ticker stopped itself")
checkNeon(S2, 1, "and it left the steady look")
-- an untimed seal just judged: the ring window only
push((function() local s = untimed({ judgeAt = NOW }); return s end)())
check(onUpdateFrames() == 1, "an untimed Judgement: the ring runs")
tick(.5); check(onUpdateFrames() == 1, "still inside the ring window")
tick(.5); check(onUpdateFrames() == 0 and not vis(S2.parts.judgeRing), "the ring is over: the ticker stopped itself and the ring is gone")
-- none: only in combat; unknown: never
push(noneState(false)); check(onUpdateFrames() == 0, "NO SEAL out of combat: no OnUpdate")
push(noneState(true)); check(onUpdateFrames() == 1, "NO SEAL in combat: the pulse")
push(unknownState()); check(onUpdateFrames() == 0, "unknown: none")
push(noneState(true)); push(sealAt("sor", 20, 10)); check(onUpdateFrames() == 1, "a timed seal replaces the pulse with the countdown")
push(noneState(true)); push(noneState(false)); check(onUpdateFrames() == 0, "leaving combat stops the pulse")
-- a class that does not own the seat, and a piece saved off, never start one
local W = boot({ class = "WARLOCK" }); check(W.frame == nil and onUpdateFrames() == 0, "a Warlock: no chamber, no OnUpdate")
local Off = boot({ db = { gunsight = { pieces = { dot = false } } }, state = sealAt("sor", 20, 10) })
check(onUpdateFrames() == 0, "a piece saved off: no OnUpdate")
FS.Gunsight.SetPiece("dot", true, true); check(onUpdateFrames() == 1, "turned on: running")
check(#AURA_TOUCHED == 0, "no aura API was read")
""")

case("an_expired_seal_flips_to_no_seal_by_itself")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 1, 10) })
local P = Seals.parts
tick(.5); check(Seals.Mode() == "seal" and vis(P.glyph), "0.5 s left: still a seal")
tick(.5)
check(Seals.Mode() == "none", "at rem 0 the chamber is NO SEAL, got " .. tostring(Seals.Mode()))
for _, nm in ipairs({ "glyph", "lens", "arcs", "name", "caption", "reseal", "fill", "tipBar", "tipDot", "count", "countS", "judgeRing" }) do check(not vis(P[nm]), nm .. " is gone after the expiry") end
check(vis(P.noSeal) and vis(P.noTime) and vis(P.noHint), "NO SEAL, -- and CAST A SEAL are up")
check(not vis(P.noSub), "out of combat: no IN COMBAT label")
check(onUpdateFrames() == 0, "out of combat the ticker stopped with the seal")
-- the Hud's own push for the expiry (Signature turns the seal term into knone) lands within one 0.2 s tick, and a push of false
-- with the same combat flag changes nothing: the chamber flipped itself for immediacy and the late push repaints nothing
local n = 0
local o1, o2 = P.edge.SetVertexColor, P.edge.SetColorTexture
P.edge.SetVertexColor = function(self, ...) n = n + 1; return o1(self, ...) end
P.edge.SetColorTexture = function(self, ...) n = n + 1; return o2(self, ...) end
push(noneState(false)); tick(1); push(noneState(false))
check(n == 0 and Seals.Mode() == "none", "the Hud's later false repaints nothing, got " .. n)
-- a stale push of the same dead seal is NO SEAL too, not a flash of the old look
push(sealAt("sor", -2, 40)); check(Seals.Mode() == "none" and not vis(P.glyph), "a pushed seal that already ran out is NO SEAL")
push(sealAt("sor", 0, 40)); check(Seals.Mode() == "none", "a seal expiring exactly now is NO SEAL")
check(n == 0, "a dead seal pushed onto NO SEAL repaints nothing, got " .. n)
-- a recast brings the seal back, striking
P.edge.SetVertexColor, P.edge.SetColorTexture = o1, o2
push(sealAt("sor", 30, 0.05)); check(Seals.Mode() == "seal" and vis(P.glyph) and vis(P.fill), "a recast repaints the seal")
checkNeon(Seals, .2, "and strikes"); check(onUpdateFrames() == 1, "and the ticker is back")
-- in combat the expiry keeps the pulse
local S2 = boot({ state = sealAt("sor", 1, 10, { inCombat = true }) })
tick(1)
check(S2.Mode() == "none" and vis(S2.parts.noSub), "expired in combat: NO SEAL with IN COMBAT")
near3(S2.parts.noSeal.textColor[4], 0.5 + 0.5 * pulseAt(NOW), "the pulse is already running on the frame it flips")
check(onUpdateFrames() == 1, "and the pulse keeps the ticker alive")
tick(.35); near3(S2.parts.noSeal.textColor[4], 0.5 + 0.5 * pulseAt(NOW), "pulsing")
""")

case("a_secret_time_is_never_read")(r"""
NOW = 5000
for _, field in ipairs({ "castAt", "expiresAt", "duration" }) do
    local Seals = boot({})
    local st = sealAt("sor", 20, 10); st.seal[field] = SECRET
    local ok, err = pcall(push, st)
    check(ok, field .. ": a secret threw out of the subscriber: " .. tostring(err))
    for i = 1, 4 do local ok2, e2 = pcall(tick, .25); check(ok2, field .. ": a secret threw in the ticker: " .. tostring(e2)) end
    check(Seals.Mode() == "seal", field .. ": the seal look stays")
    check(DEGRADED.gunsightseals_state == nil and DEGRADED.gunsightseals_tick == nil, field .. ": no degrade logged: " .. tostring(next(DEGRADED)))
end
do  -- a secret judgeAt and combat flag
    local Seals = boot({})
    local st = sealAt("sor", 20, 10, { judgeAt = SECRET, inCombat = SECRET })
    check(pcall(push, st) and pcall(tick, .25), "a secret judgeAt and flag throw nothing")
    check(DEGRADED.gunsightseals_state == nil and DEGRADED.gunsightseals_tick == nil, "and log nothing")
end
do  -- plain numbers the client flags as secret are never compared either: they read as unknown
    local Seals = boot({})
    local st = sealAt("sor", 20, 10, { judgeAt = NOW - 0.25 })
    local flagged = { [st.seal.expiresAt] = true, [st.seal.castAt] = true, [st.judgeAt] = true }
    SECRET_FN = function(v) return flagged[v] == true end
    push(st); tick(.25)
    for _, nm in ipairs({ "fill", "tipBar", "tipDot", "count", "countS", "judgeRing" }) do check(not vis(Seals.parts[nm]), nm .. " hidden for flagged numbers") end
    checkNeon(Seals, 1, "a flagged castAt strikes nothing")
    SECRET_FN = function(v) return rawequal(v, SECRET) end
    check(DEGRADED.gunsightseals_state == nil and DEGRADED.gunsightseals_tick == nil, "no degrade: " .. tostring(next(DEGRADED)))
end
""")

case("a_steady_tick_writes_only_the_fill_height")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10) })
local P, ch = Seals.parts, Seals.frame
local W = {}
local function spy(obj, name, label)
    local orig = obj[name]
    obj[name] = function(self, ...) local key = label or name; W[key] = (W[key] or 0) + 1; return orig(self, ...) end
end
local Fm = getmetatable(P.fill).__index
for _, n in ipairs({ "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight", "SetAlpha", "Show", "Hide", "SetShown" }) do spy(Fm, n) end
for _, t in ipairs(TEXTURES) do
    if t.parent == ch then
        for _, n in ipairs({ "SetVertexColor", "SetColorTexture", "SetTexture", "SetGradient", "SetBlendMode", "SetTexCoord", "SetDesaturated" }) do spy(t, n) end
    end
end
for _, f in ipairs(FONTSTRINGS) do
    if f.parent == ch then for _, n in ipairs({ "SetText", "SetTextColor", "SetFont" }) do spy(f, n) end end
end
spy(FS.Theme, "ApplyMono")
local oc = CreateColor
CreateColor = function(...) W.CreateColor = (W.CreateColor or 0) + 1; return oc(...) end
for i = 1, 4 do tick(.125) end
CreateColor = oc
for k, v in pairs(W) do
    if k ~= "SetHeight" then error("a steady tick called " .. k .. " " .. v .. " times") end
end
check(W.SetHeight == 4, "the fill height follows the time, once a tick, got " .. tostring(W.SetHeight))
-- and the fill really moved
local l, t, w, h = imgRect(P.fill)
near3(t, secY(19.5), "the fill top after four ticks")
""")

case("a_rescale_keeps_the_live_parts")(r"""
NOW = 5000
for _, height in ipairs({ 1200, 1080 }) do
    local Seals = boot({ state = sealAt("sor", 12.5, 10, { judgeAt = NOW - .25 }) })
    local P = Seals.parts
    tick(.5)
    local before = {}
    for _, nm in ipairs({ "fill", "tipBar", "tipDot", "judgeRing", "count", "countS" }) do before[nm] = { imgRect(P[nm]) } end
    local texts = { P.count.text, P.countS.text }
    local nf, nt, ns = #FRAMES, #TEXTURES, #FONTSTRINGS
    SetScreen(height); fire("UI_SCALE_CHANGED"); fire("DISPLAY_SIZE_CHANGED")
    for nm, r in pairs(before) do
        local now = { imgRect(P[nm]) }
        for i = 1, 4 do near3(now[i], r[i], nm .. " rect " .. i .. " at height " .. height) end
    end
    check(P.count.text == texts[1] and P.countS.text == texts[2], "the text survives the rescale")
    near3(P.count.monoSize, S.COUNT_SIZE * FS.Layout.Scale() * SK, "the countdown font follows the scale")
    near3(P.countS.monoSize, S.S_SIZE * FS.Layout.Scale() * SK, "the S font follows the scale")
    check(nf == #FRAMES and nt == #TEXTURES and ns == #FONTSTRINGS, "a rescale builds nothing")
    check(onUpdateFrames() == 1, "the ticker is still one")
    tick(.25); local l, t = imgRect(P.fill); near3(t, secY(11.75), "and the fill keeps draining after the rescale")
    checkNeon(Seals, 1, "neon after the rescale")
end
""")


case("reduced_motion_holds_the_neon_steady")(r"""
NOW = 5000
-- ForeverSynthwaveDB.reducedMotion == true: sealNeon is .8 while expiring and 1 otherwise, never struck, never dropping out
local S1 = boot({ db = { reducedMotion = true }, state = sealAt("sor", 20, 0.1) })
checkNeon(S1, 1, "a fresh cast is not struck")
for i = 1, 6 do tick(.1); checkNeon(S1, 1, "no strike flicker, step " .. i) end
local S2 = boot({ db = { reducedMotion = true }, state = sealAt("sor", 4.9, 10) })
for i = 1, 14 do checkNeon(S2, S.REDUCED_EXPIRING, "expiring holds the dim level, step " .. i); tick(.0777) end
-- a strike inside the last five seconds: the dim level, not the dropouts and not the strike table
local S3 = boot({ db = { reducedMotion = true }, state = sealAt("sor", 4, 0.1) })
for i = 1, 5 do checkNeon(S3, S.REDUCED_EXPIRING, "a strike while expiring, step " .. i); tick(.05) end
-- the animated look is the control: the same states do move without the flag
local C1 = boot({ state = sealAt("sor", 4.9, 10) })
local seen = {}
for i = 1, 14 do seen[string.format("%.4f", C1.parts.fill.alpha)] = true; tick(.0777) end
local distinct = 0
for _ in pairs(seen) do distinct = distinct + 1 end
check(distinct > 3, "without the flag the expiring tube moves, " .. distinct .. " distinct levels")
-- only an exact true is the flag
for _, v in ipairs({ "yes", 1, "true", false }) do
    local S4 = boot({ db = { reducedMotion = v }, state = sealAt("sor", 20, 0.1) })
    checkNeon(S4, S4.Neon(0.1, false, 20, NOW), "reducedMotion = " .. tostring(v) .. " is not the flag")
    -- and the NO SEAL pulse still runs: a truthy non boolean must not half reduce the chamber
    local N = boot({ db = { reducedMotion = v }, state = noneState(true) })
    check(onUpdateFrames() == 1, "reducedMotion = " .. tostring(v) .. ": the NO SEAL pulse ticker still runs")
    local e0 = tint(N.parts.edge)[4]; tick(.35)
    check(math.abs(tint(N.parts.edge)[4] - e0) > 0.01, "reducedMotion = " .. tostring(v) .. ": the NO SEAL edge still pulses")
end
-- the flag is read through ForeverSynthwaveDB at the push; a missing table is just off
local S5 = boot({ state = sealAt("sor", 20, 10) })
ForeverSynthwaveDB = nil
local ok, err = pcall(push, sealAt("sor", 20, 0.1))
check(ok, "no ForeverSynthwaveDB threw: " .. tostring(err))
checkNeon(S5, S5.Neon(0.1, false, 20, NOW), "no table: the animated look")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("reduced_motion_holds_the_reseal_band_steady")(r"""
NOW = 5000
local function steady(Seals, what)
    local P = Seals.parts
    near3(P.band.color[4], S.BAND_FILL, what .. ": the wash stays at its base (pl = 0)")
    near3(P.reseal.textColor[4], S.RESEAL_IN0 + S.RESEAL_IN1, what .. ": RESEAL at .55 + .45 * 1")
end
local Seals = boot({ db = { reducedMotion = true }, state = sealAt("sor", 3, 10) })
local P = Seals.parts
steady(Seals, "entering the band")
check(Seals.parts.band.color[4] ~= nil, "the band has a colour")
local nb, nr = 0, 0
local ob, orr = P.band.SetColorTexture, P.reseal.SetTextColor
P.band.SetColorTexture = function(self, ...) nb = nb + 1; return ob(self, ...) end
P.reseal.SetTextColor = function(self, ...) nr = nr + 1; return orr(self, ...) end
for i = 1, 8 do tick(.1); steady(Seals, "step " .. i) end
check(nb == 0 and nr == 0, "a steady band writes nothing per frame: wash " .. nb .. ", RESEAL " .. nr)
-- leaving the band (a longer seal pushed) puts both back to rest
push(sealAt("sor", 10, 10))
near3(P.band.color[4], S.BAND_FILL, "out of the band the wash rests"); near3(P.reseal.textColor[4], S.RESEAL_A, "and RESEAL rests at .6")
-- the control: without the flag the wash breathes
local C1 = boot({ state = sealAt("sor", 3, 10) })
local lo, hi = 9, -9
for i = 1, 20 do local a = C1.parts.band.color[4]; lo, hi = math.min(lo, a), math.max(hi, a); tick(.07) end
check(hi - lo > 0.05, "without the flag the wash breathes, range " .. (hi - lo))
""")

case("reduced_motion_holds_the_no_seal_look_steady")(r"""
NOW = 5000
for _, combat in ipairs({ true, false }) do
    local Seals = boot({ db = { reducedMotion = true }, state = noneState(combat) })
    local P = Seals.parts
    local function steady(what)
        near3(tint(P.edge)[4], S.NO_EDGE_A0 + S.NO_EDGE_A1, what .. ": the edge at u = 1")
        near3(tint(P.glow)[4], (S.NO_EDGE_A0 + S.NO_EDGE_A1) * coverage(1), what .. ": the halo at u = 1")
        near3(P.noSeal.textColor[4], 1, what .. ": the label at u = 1")
        check(vis(P.glow), what .. ": the halo shows")
    end
    steady("combat " .. tostring(combat) .. " at rest")
    check(onUpdateFrames() == 0, "combat " .. tostring(combat) .. ": no pulse ticker under reduced motion")
    check(vis(P.noSub) == combat, "the IN COMBAT sub-label still follows the flag")
    for i = 1, 5 do tick(.35); steady("combat " .. tostring(combat) .. " tick " .. i) end
end
-- an expiry into NO SEAL under reduced motion lands on the steady look too
local S2 = boot({ db = { reducedMotion = true }, state = sealAt("sor", 1, 10, { inCombat = true }) })
tick(1.1)
check(S2.Mode() == "none", "expired")
near3(tint(S2.parts.edge)[4], S.NO_EDGE_A0 + S.NO_EDGE_A1, "the expiry flip wears u = 1")
near3(S2.parts.noSeal.textColor[4], 1, "and the label at 1"); check(onUpdateFrames() == 0, "and nothing keeps the ticker alive")
""")

case("reduced_motion_runs_the_ticker_only_for_what_still_moves")(r"""
NOW = 5000
local RED = function() return { reducedMotion = true } end
local function untimed(extra) local s = sealAt("sor", 20, 100, extra); s.seal.expiresAt = nil; return s end
-- a timed seal: the drain and the countdown still move
local S1 = boot({ db = RED(), state = sealAt("sor", 20, 10) })
check(onUpdateFrames() == 1, "a timed seal: the drain and the countdown")
tick(1); local l, t = imgRect(S1.parts.fill); near3(t, secY(19), "the drain still moves"); check(S1.parts.count.text == "19", "and so does the number")
-- an untimed seal just cast: the strike is dropped, so nothing moves
local S2 = boot({ db = RED(), state = (function() local s = sealAt("sor", 20, 0.05); s.seal.expiresAt = nil; return s end)() })
check(onUpdateFrames() == 0, "an untimed fresh cast: no strike, no ticker")
-- the Judgement ring is not gated by reduce in the mockup: it still animates, then the ticker stops
push(untimed({ judgeAt = NOW - .25 }))
check(onUpdateFrames() == 1, "an untimed Judgement: the ring runs")
tick(.25)
local p = easeOut(.5 / S.RING_S)
near3(effA(S2.parts.judgeRing), S.RING_A * (1 - p), "the ring fades as ever under reduced motion")
tick(1)
check(onUpdateFrames() == 0 and not vis(S2.parts.judgeRing), "the ring is over: the ticker stopped")
-- NO SEAL in combat: the pulse is held, so no ticker
local S3 = boot({ db = RED(), state = noneState(true) })
check(onUpdateFrames() == 0, "NO SEAL in combat: held, no ticker")
""")

case("a_change_of_the_reduced_motion_flag_repaints_at_the_next_push")(r"""
NOW = 5000
-- NO SEAL in combat: pulsing, then held, then pulsing again
local Seals = boot({ state = noneState(true) })
local P = Seals.parts
check(onUpdateFrames() == 1, "pulsing")
tick(.35); near3(P.noSeal.textColor[4], 0.5 + 0.5 * pulseAt(NOW), "the pulse runs")
ForeverSynthwaveDB.reducedMotion = true
push(noneState(true))
check(onUpdateFrames() == 0, "the flag on: the ticker stops at the next push")
near3(tint(P.edge)[4], S.NO_EDGE_A0 + S.NO_EDGE_A1, "and the edge is held at u = 1"); near3(P.noSeal.textColor[4], 1, "and the label")
ForeverSynthwaveDB.reducedMotion = false
push(noneState(true))
check(onUpdateFrames() == 1, "the flag off again: the pulse resumes")
tick(.35); near3(P.noSeal.textColor[4], 0.5 + 0.5 * pulseAt(NOW), "pulsing again")
-- an expiring seal: dropouts, then the dim level, then dropouts
local S2 = boot({ state = sealAt("sor", 4, 10) })
local st = sealAt("sor", 4, 10)
ForeverSynthwaveDB.reducedMotion = true
push(st); checkNeon(S2, S.REDUCED_EXPIRING, "reduced")
ForeverSynthwaveDB.reducedMotion = false
push(st); checkNeon(S2, S2.Neon(NOW - st.seal.castAt, true, st.seal.expiresAt - NOW, NOW), "animated again")
""")

case("a_client_without_gradients_still_draws_the_drain_in_a_flat_tint")(r"""
NOW = 5000
local mt = getmetatable(UIParent)
local origCreateTexture, realCreateColor = mt.CreateTexture, CreateColor
-- each variant starts from the full client and takes away ONE thing, whatever ran before it
local function fullClient()
    mt.CreateTexture = origCreateTexture
    CreateColor = realCreateColor
end
local function noSetGradient()
    fullClient()
    mt.CreateTexture = function(self, ...)
        local t = origCreateTexture(self, ...)
        t.SetGradient = nil
        return t
    end
end
local function noCreateColor()
    fullClient()
    CreateColor = nil
end
-- with both present the drain is the gradient and never the flat tint (the control, before the variants strip the client)
local G = boot({ state = sealAt("sor", 20, 10) })
check(G.parts.fill.gradient ~= nil, "with SetGradient and CreateColor the drain is a gradient")
local variants = { { "no Texture:SetGradient", noSetGradient }, { "no CreateColor", noCreateColor } }
for _, variant in ipairs(variants) do
    local what, before = variant[1], variant[2]
    local Seals = boot({ beforeSeals = before, state = sealAt("sor", 20, 10) })
    local P = Seals.parts
    local col, amber = sealColor("righteousness"), rgb(MU.CSS.amber)
    check(Seals.Mode() == "seal", what .. ": the chamber still builds the seal look")
    check(vis(P.fill) and vis(P.tipBar) and vis(P.tipDot), what .. ": the drain shows")
    check(P.fill.gradient == nil, what .. ": no gradient was set")
    colA(tint(P.fill), col, 1, what .. ": the flat seal tint")
    local l, t = imgRect(P.fill); near3(t, secY(20), what .. ": the fill still follows the time")
    push(sealAt("sor", 3, 10)); colA(tint(P.fill), amber, 1, what .. ": the band wears amber")
    push(sealAt("sor", 12, 10)); colA(tint(P.fill), col, 1, what .. ": and back to the seal tint")
    tick(1); check(next(DEGRADED) == nil, what .. ": no degrade: " .. tostring(next(DEGRADED)))
    local S2 = boot({ beforeSeals = before, state = sealAt("sor", 3, 10) })
    colA(tint(S2.parts.fill), amber, 1, what .. ": built in the band")
end
""")

case("the_fill_height_is_quantised_to_a_quarter_screen_pixel")(r"""
NOW = 5000
-- a client that reports the pixel: PixelUtil's factor (UI units per physical pixel at scale 1) and the root's effective scale
local function install(factor, scale)
    return function()
        PixelUtil = { GetPixelToUIUnitFactor = function() return factor end }
        getmetatable(UIParent).GetEffectiveScale = function() return scale or 1 end
    end
end
local function drain(opts, frames)
    local Seals = boot(opts)
    local P = Seals.parts
    local Fm = getmetatable(P.fill).__index
    local heights, orig = {}, Fm.SetHeight
    Fm.SetHeight = function(self, h) heights[#heights + 1] = h; return orig(self, h) end
    for i = 1, frames do tick(1 / frames) end
    Fm.SetHeight = orig
    return Seals, heights
end
-- the worst distance of a written height from a whole multiple of `step`
local function offGrid(heights, step)
    local worst = 0
    for _, h in ipairs(heights) do worst = math.max(worst, math.abs(h / step - math.floor(h / step + 0.5))) end
    return worst
end
-- the smallest distance between two different written heights (the step actually in use)
local function minStep(heights)
    local best = math.huge
    for i = 2, #heights do
        local d = math.abs(heights[i] - heights[i - 1])
        if d > 1e-9 and d < best then best = d end
    end
    return best
end
local function allFinite(heights)
    for _, v in ipairs(heights) do if v ~= v or v == math.huge or v == -math.huge then return false end end
    return #heights > 0
end
-- 1 s at 144 frames a second without a pixel API: every frame writes the height
local S0, h0 = drain({ state = sealAt("sor", 20, 10) }, 144)
check(#h0 == 144, "without a pixel API every frame writes the height, got " .. #h0)
-- with one: the writes land on quarter pixel steps and are a fraction of the frames
local exp1 = NOW + 20                -- sealAt below is built at the clock as it is now
local S1, h1 = drain({ beforeSeals = install(1), state = sealAt("sor", 20, 10) }, 144)
local step = 0.25
check(offGrid(h1, step) < 1e-6, "every written height is a whole quarter pixel, worst remainder " .. offGrid(h1, step))
check(#h1 > 20 and #h1 < 60, "the writes follow the drain on quarter pixel steps (a drain of about 10 px in a second), got " .. #h1 .. " of 144 frames")
local l, t, w, h = imgRect(S1.parts.fill)
local exact = (20 - 1) * (B.BOT - B.TOP) / S.MAX_S
local ui1 = SK * FS.Layout.Scale()
check(math.abs(h * ui1 - exact * ui1) <= step / 2 + 1e-6, "the quantised height is within half a step of the true one, off by " .. math.abs(h - exact) * ui1)
-- the number is exact, not quantised
check(S1.parts.count.text == S1.CountText(exp1 - NOW), "the countdown is not quantised: " .. tostring(S1.parts.count.text))
-- the step is a quarter of a screen pixel: a pixel of 0.5333 UI units at effective scale 1, and a factor of 1 at effective scale 2
for what, args in pairs({ ["0.5333 per pixel"] = { 0.5333, 1 }, ["scale 2"] = { 1, 2 } }) do
    local _, hh = drain({ beforeSeals = install(args[1], args[2]), state = sealAt("sor", 20, 10) }, 144)
    local want = 0.25 * args[1] / args[2]
    check(offGrid(hh, want) < 1e-6 and #hh > 5 and #hh < 144, what .. ": quarter pixel steps of " .. want .. ", worst remainder " .. offGrid(hh, want) .. ", " .. #hh .. " writes")
    check(math.abs(minStep(hh) - want) < 1e-6, what .. ": the step in use is " .. want .. " (the pixel over the root's scale), not " .. minStep(hh))
end
check(math.abs(minStep(h1) - step) < 1e-6, "the step in use is a quarter pixel, got " .. minStep(h1))
-- rounds to the NEAREST quarter pixel, on every frame of the drain, not down
do
    local Sq = boot({ beforeSeals = install(1), state = sealAt("sor", 20, 10) })
    local expq = NOW + 20
    local worst = 0
    for i = 1, 144 do
        tick(1 / 144)
        local _, _, _, hq = imgRect(Sq.parts.fill)
        worst = math.max(worst, math.abs(hq - (expq - NOW) * (B.BOT - B.TOP) / S.MAX_S) * ui1)
    end
    check(worst <= step / 2 + 1e-6, "every frame's height is within half a step of the true one, worst " .. worst)
end
-- the tube is never overgrown: at 30 s and above (a reconcile can report more) the fill stops at the full tube on every grid
for _, f in ipairs({ 0.5333, 0.61, 0.7, 0.83, 0.9, 1.1, 1.3, 1.7 }) do
    for _, rem in ipairs({ 30, 35 }) do
        local Sf = boot({ beforeSeals = install(f), state = sealAt("sor", rem, 40) })
        local _, _, _, hf = imgRect(Sf.parts.fill)
        check(hf * ui1 <= (B.BOT - B.TOP) * ui1 + 1e-9, "pixel " .. f .. ", " .. rem .. " s: the fill " .. hf * ui1 .. " stays inside the tube " .. (B.BOT - B.TOP) * ui1)
    end
end
-- without PixelUtil the physical screen size gives the factor (768 / height)
local _, hp = drain({ beforeSeals = function()
    PixelUtil = nil
    GetPhysicalScreenSize = function() return 2560, 1440 end
    getmetatable(UIParent).GetEffectiveScale = function() return 1 end
end, state = sealAt("sor", 20, 10) }, 144)
check(offGrid(hp, 0.25 * 768 / 1440) < 1e-6 and #hp < 144, "GetPhysicalScreenSize: quarter pixel steps of 768 / height, " .. #hp .. " writes")
-- a rescale re-derives the step (the client is back to one UI unit per pixel at scale 1)
install(1)()
SetScreen(1080); fire("UI_SCALE_CHANGED"); fire("DISPLAY_SIZE_CHANGED")
local n = 0
local Fm = getmetatable(S1.parts.fill).__index
local orig, after = Fm.SetHeight, {}
Fm.SetHeight = function(self, v) n = n + 1; after[#after + 1] = v; return orig(self, v) end
for i = 1, 144 do tick(1 / 144) end
Fm.SetHeight = orig
check(n > 0 and n < 144, "still quantised after a rescale, got " .. n .. " writes")
check(offGrid(after, step) < 1e-6, "and on the new scale's quarter pixels, worst remainder " .. offGrid(after, step))
-- a secret or unusable factor or scale leaves the exact height (no step), without a throw
local unusable = {
    secret = function() return SECRET end, zero = function() return 0 end, text = function() return "x" end,
    nan = function() return 0 / 0 end, throws = function() error("no") end,
}
for what, fn in pairs(unusable) do
    local S2, h2 = drain({ beforeSeals = function()
        PixelUtil = { GetPixelToUIUnitFactor = fn }
        getmetatable(UIParent).GetEffectiveScale = function() return 1 end
    end, state = sealAt("sor", 20, 10) }, 60)
    check(#h2 == 60, what .. ": no step, every frame writes, got " .. #h2)
    check(allFinite(h2), what .. ": every written height is a finite number")
    check(math.abs(minStep(h2) - (B.BOT - B.TOP) / S.MAX_S * ui1 / 60) < 0.05, what .. ": the exact height, a step of " .. minStep(h2))
    check(next(DEGRADED) == nil, what .. ": no degrade: " .. tostring(next(DEGRADED)))
end
for what, v in pairs({ negative = -1, huge = math.huge }) do
    local _, h2 = drain({ beforeSeals = function()
        PixelUtil = { GetPixelToUIUnitFactor = function() return v end }
        getmetatable(UIParent).GetEffectiveScale = function() return 1 end
    end, state = sealAt("sor", 20, 10) }, 60)
    check(allFinite(h2) and #h2 == 60, what .. " factor: no step, finite heights, every frame writes, got " .. #h2)
end
-- an infinite effective scale or layout scale is no scale either
do
    local _, hi1 = drain({ beforeSeals = function()
        PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }
        getmetatable(UIParent).GetEffectiveScale = function() return math.huge end
    end, state = sealAt("sor", 20, 10) }, 60)
    check(allFinite(hi1), "an infinite effective scale counts as 1: finite heights")
    local _, hi2 = drain({ beforeSeals = function()
        install(1)()
        FS.Layout.Scale = function() return math.huge end
    end, state = sealAt("sor", 20, 10) }, 30)
    local nan = false
    for _, v in ipairs(hi2) do if v ~= v then nan = true end end
    check(#hi2 > 0 and not nan, "an infinite layout scale: no NaN height (the step is dropped, the heights are just huge)")
end
-- a pixel API that goes away on a rescale takes the step with it
do
    local Sg = boot({ beforeSeals = install(1), state = sealAt("sor", 20, 10) })
    PixelUtil = { GetPixelToUIUnitFactor = function() return 0 end }
    fire("UI_SCALE_CHANGED")
    local Fm2 = getmetatable(Sg.parts.fill).__index
    local o2, hg = Fm2.SetHeight, {}
    Fm2.SetHeight = function(self, v) hg[#hg + 1] = v; return o2(self, v) end
    for i = 1, 60 do tick(1 / 60) end
    Fm2.SetHeight = o2
    check(#hg == 60 and allFinite(hg), "a factor that turns unusable on a rescale drops the step: every frame writes, got " .. #hg)
end
-- an unusable layout scale (one image px is no length) leaves the exact height too
do
    local _, hs = drain({ beforeSeals = function()
        install(1)()
        FS.Layout.Scale = function() return 0 end
    end, state = sealAt("sor", 20, 10) }, 30)
    check(allFinite(hs), "a layout scale of 0: finite heights, got " .. tostring(hs[1]))
end
-- a secret NUMBER (the guard has to ask, type() says number): 7 is the secret here, as the client's would be
local S3, h3 = drain({ beforeSeals = function()
    SECRET_FN = function(v) return v == 7 end
    PixelUtil = { GetPixelToUIUnitFactor = function() return 7 end }
    getmetatable(UIParent).GetEffectiveScale = function() return 1 end
end, state = sealAt("sor", 20, 10) }, 60)
check(#h3 == 60, "a secret factor: no step, every frame writes, got " .. #h3)
local S4, h4 = drain({ beforeSeals = function()
    SECRET_FN = function(v) return v == 7 end
    PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }
    getmetatable(UIParent).GetEffectiveScale = function() return 7 end
end, state = sealAt("sor", 20, 10) }, 144)
check(offGrid(h4, 0.25) < 1e-6 and #h4 < 144, "a secret effective scale counts as 1: quarter pixel steps, " .. #h4 .. " writes")
check(math.abs(minStep(h4) - 0.25) < 1e-6, "a secret effective scale counts as 1: the step is a quarter, got " .. minStep(h4))
local S5, h5 = drain({ beforeSeals = function()
    SECRET_FN = function(v) return v == 7 end
    PixelUtil = nil
    GetPhysicalScreenSize = function() return 2560, 7 end
    getmetatable(UIParent).GetEffectiveScale = function() return 1 end
end, state = sealAt("sor", 20, 10) }, 60)
check(#h5 == 60, "a secret screen height: no step, every frame writes, got " .. #h5)
""")

case("the_neon_follows_the_mockups_sealneon_over_a_grid")(r"""
local Seals = boot({ state = sealAt("sor", 20, 10) })
-- sealNeon (mockup 2036 to 2041) with its numbers written out, nothing read from the addon
local function fr(v) return v - math.floor(v) end
local function model(strike, expiring, rem, t)
    local m = 1
    if strike < .7 and strike >= 0 then m = ({ .2, .9, .1, .7, .3, 1, .6 })[math.min(6, math.floor(strike / .7 * 7)) + 1] end
    if expiring and rem > 0 then
        local n = math.floor(t * 13)
        local p = .28 + .4 * (1 - rem / 5)
        if fr(math.sin(n * 91.7) * 43758.5453) < p then m = .12 + .3 * fr(math.sin(n * 12.9898) * 43758.5453)
        else m = .78 + .22 * math.sin(t * 37) end
    end
    return m
end
local strikes = { -1, 0, .05, .0999, .1, .2, .2999, .3, .45, .5, .6, .6999999, .7, .71, 5 }
local worst, bad = 0, nil
for _, strike in ipairs(strikes) do
    for _, expiring in ipairs({ false, true }) do
        for ri = 0, 24 do
            local rem = ri == 0 and 0 or (ri * 0.2083)
            for ti = 0, 40 do
                local t = 1000 + ti * 0.0777
                local got, want = Seals.Neon(strike, expiring, rem, t), model(strike, expiring, rem, t)
                local d = math.abs(got - want)
                if d > worst then worst, bad = d, string.format("strike %g expiring %s rem %g t %g: got %g want %g", strike, tostring(expiring), rem, t, got, want) end
            end
        end
    end
end
check(worst < 1e-9, "Neon differs from the mockup's sealNeon: " .. tostring(bad))
-- the dropout odds really do rise as the time runs out: more dark frames at 0.5 s than at 4.9 s
local function darkShare(rem)
    local dark = 0
    for i = 0, 399 do if Seals.Neon(-1, true, rem, 2000 + i * 0.0731) < .5 then dark = dark + 1 end end
    return dark / 400
end
check(darkShare(.5) > darkShare(4.9) + .1, "dropouts get likelier as the time runs out: " .. darkShare(.5) .. " vs " .. darkShare(4.9))
""")

case("the_countdown_text_clamps_and_rounds_like_the_mockup")(r"""
local Seals = boot({ state = sealAt("sor", 20, 10) })
local CT = Seals.CountText
for _, e in ipairs({ { 100, "30" }, { 30, "30" }, { 29.2, "30" }, { 29, "29" }, { 20.4, "21" }, { 5.01, "6" }, { 5, "5.0" }, { 4.96, "5.0" },
        { 4.95, "5.0" }, { 4.94, "4.9" }, { 1, "1.0" }, { .26, "0.3" }, { .24, "0.2" }, { .04, "0.0" }, { 0, "0.0" }, { -1, "0.0" } }) do
    check(CT(e[1]) == e[2], "CountText(" .. e[1] .. ") is " .. tostring(CT(e[1])) .. ", want " .. e[2])
end
""")

case("a_clamped_tube_writes_nothing_on_a_tick")(r"""
NOW = 5000
-- a reconcile can report a duration above 30 (a long buff on the seal's aura): the tube pins full and the number at 30
local Seals = boot({ state = sealAt("sor", 36, 10) })
local P = Seals.parts
check(P.count.text == "30", "36 s reads 30 (pinned), got " .. tostring(P.count.text))
local Fm = getmetatable(P.fill).__index
local n, orig = 0, Fm.SetHeight
Fm.SetHeight = function(self, ...) n = n + 1; return orig(self, ...) end
for i = 1, 4 do tick(.25) end
Fm.SetHeight = orig
check(n == 0, "35 s and more fill the whole tube: the height is not rewritten, got " .. n .. " writes")
local l, t, w, h = imgRect(P.fill); near3(t, B.TOP, "still the whole tube")
tick(6.5)    -- now 29.5 s: under the top
l, t = imgRect(P.fill); near3(t, secY(29.5 - 1), "and it drains once under 30 s")
""")

case("the_drain_comes_back_after_an_unreadable_time")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10) })
local P = Seals.parts
local five = { "fill", "tipBar", "tipDot", "count", "countS" }
local function allShown(on, what) for _, nm in ipairs(five) do check(vis(P[nm]) == on, what .. ": " .. nm .. (on and " shown" or " hidden")) end end
allShown(true, "timed")
local st = sealAt("sor", 20, 10); st.seal.expiresAt = nil
push(st); allShown(false, "time lost")
push(sealAt("sor", 20, 10)); allShown(true, "time back")
check(P.count.text == "20", "the countdown reads again: " .. tostring(P.count.text))
local l, t = imgRect(P.fill); near3(t, secY(20), "the fill is at 20 s again")
push(sealAt("sor", 0.03125, 10))
for _, nm in ipairs({ "fill", "tipBar", "tipDot" }) do check(not vis(P[nm]), "under FILL_MIN: " .. nm .. " hidden") end
for _, nm in ipairs({ "count", "countS" }) do check(vis(P[nm]), "under FILL_MIN: " .. nm .. " stays (the mockup gates only the tube)") end
check(P.count.text == "0.0", "under FILL_MIN the countdown reads 0.0, got " .. tostring(P.count.text))
push(sealAt("sor", 12, 10)); allShown(true, "12 s")
check(P.count.text == "12", "twelve: " .. tostring(P.count.text))
l, t = imgRect(P.fill); near3(t, secY(12), "and the fill follows")
""")

case("the_ring_is_shown_once_and_hidden_once")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10, { judgeAt = NOW - 0.25 }) })
local P = Seals.parts
local w0 = P.judgeRing.writes or 0
tick(.125); tick(.125); tick(.125)
check((P.judgeRing.writes or 0) == w0, "a ring in flight is not shown again each frame, got " .. ((P.judgeRing.writes or 0) - w0) .. " writes")
tick(.5)
check(not vis(P.judgeRing), "the window is over")
local w1 = P.judgeRing.writes or 0
tick(1); tick(1)
check((P.judgeRing.writes or 0) == w1, "and a gone ring is not hidden again each frame")
-- a hidden ring at build is the lens size
local S2 = boot({ state = unknownState() })
local l, t, w, h = imgRect(S2.parts.judgeRing)
near3(w, MU.TEX.ring / MU.TEX.RING_K, "the ring rests at its own texture's size (texels / 1.2)"); near3(h, w, "square")
""")

case("a_swap_of_seal_repaints_every_live_cache")(r"""
NOW = 5000
local amber = rgb(MU.CSS.amber)
-- mid ring window: the ring is up for the new seal, in its colour
local Seals = boot({ state = sealAt("sor", 20, 10, { judgeAt = NOW - 0.25 }) })
local P = Seals.parts
push(sealAt("sotc", 30, 10, { judgeAt = NOW - 0.25 }))
check(vis(P.judgeRing), "the ring survives a swap of seal")
check(vis(P.count) and vis(P.countS) and vis(P.fill), "the number, its S and the drain are up again after a swap of seal")
colorIs(P.judgeRing.vertex, sealColor("crusader"), "in the new seal's colour")
-- mid band: the new seal's parts are amber at once
local B2 = boot({ state = sealAt("sor", 2, 10) })
push(sealAt("sotc", 2.5, 10))
colA(B2.parts.tube.color, amber, S.TUBE_A, "band: tube")
colorIs(B2.parts.count.textColor, amber, "band: the number is amber after the swap")
local g = B2.parts.fill.gradient
colorIs({ g.min.r, g.min.g, g.min.b }, amber, "band: the fill tail is amber after the swap")
colorIs(B2.parts.tipBar.color, mix(amber, WHITE, S.TIP_MIX), "band: the tip is amber after the swap")
-- mid strike: the new seal starts at the first step
local S3 = boot({ state = sealAt("sor", 20, 0.05) })
push(sealAt("sotc", 20, 0.05))
checkNeon(S3, .2, "strike: the swap lands on the first step")
-- from the band onto NO SEAL: the wash and RESEAL rest
local B3 = boot({ state = sealAt("sor", 2, 10) })
tick(.1)
push(noneState(false))
colA(B3.parts.band.color, amber, S.BAND_FILL, "the band wash rests on NO SEAL")
colA(B3.parts.reseal.textColor, amber, S.RESEAL_A, "RESEAL rests on NO SEAL")
""")

case("a_throwing_tick_stops_itself_and_logs_once")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10) })
local P = Seals.parts
P.fill.SetHeight = function() error("boom") end
local ok, err = pcall(tick, .25)
check(ok, "a throw in the live layer does not escape the OnUpdate: " .. tostring(err))
check(DEGRADED.gunsightseals_tick ~= nil, "it is logged")
check(onUpdateFrames() == 0, "and the ticker is cleared")
check(pcall(tick, 1), "later frames run nothing"); check(onUpdateFrames() == 0, "still stopped")
-- the next push brings it back
P.fill.SetHeight = nil
DEGRADED.gunsightseals_tick = nil
push(sealAt("sor", 20, 10)); check(onUpdateFrames() == 1, "a new push re-arms the ticker")
tick(.25); local l, t = imgRect(P.fill); near3(t, secY(19.75 - 0), "and it drains again")
""")

case("the_ticker_is_installed_once_and_only_while_something_moves")(r"""
NOW = 5000
local Seals = boot({ state = sealAt("sor", 20, 10) })
local ch = Seals.frame
local n, orig = 0, getmetatable(ch).__index.SetScript
ch.SetScript = function(self, ...) n = n + 1; return orig(self, ...) end
for i = 1, 4 do push(sealAt("sor", 20 - i, 10)) end
for i = 1, 4 do tick(.25) end
check(n == 0, "a running ticker is not installed again by a push or a tick, got " .. n)
push(unknownState()); check(n == 1, "it is cleared once when nothing moves, got " .. n)
push(unknownState()); push(noneState(false)); check(n == 1, "and not again, got " .. n)
push(sealAt("sor", 20, 10)); check(n == 2, "and installed once more, got " .. n)
-- an untimed seal with a castAt or judgeAt still in the future waits: no ticker
local function untimed(extra) local s = sealAt("sor", 20, 10, extra); s.seal.expiresAt = nil; return s end
push(unknownState()); local m = n
local s1 = untimed(); s1.seal.castAt = NOW + .3; push(s1)
check(onUpdateFrames() == 0, "a cast in the future does not start the ticker")
push(untimed({ judgeAt = NOW + .3 }))
check(onUpdateFrames() == 0, "a Judgement in the future does not start the ticker")
-- a NaN time never animates
local s2 = sealAt("sor", 20, 10); s2.seal.expiresAt = 0 / 0; push(s2)
check(onUpdateFrames() == 0, "a NaN expiry does not start the ticker")
""")


# ---------------------------------------------------------------------------------------
# Lane 9: the Judgement debuff lane, live
# ---------------------------------------------------------------------------------------

case("judgement_lane_constants_match_the_mockup")(r"""
local Seals = boot({ noEvents = true })
local C = Seals.C
local function eq(a, b, what) near(a, b, what .. " (GunsightSeals has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")") end
eq(C.JUDGED_A_ON, S.JUDGED_A_ON, "JUDGED alpha with a debuff"); eq(C.JL_AX_A_ON, S.JL_AX_A_ON, "axis alpha with a debuff")
eq(C.JL_TICK_A_ON, S.JL_TICK_A_ON, "tick alpha with a debuff"); eq(C.JL_LABEL_A_ON, S.JL_LABEL_A_ON, "label alpha with a debuff")
eq(C.CHS, S.CHS, "chip size"); eq(C.JL_BAR_A0, S.JL_BAR_A0, "bar tail alpha")
eq(C.JL_BAR_GLOW_W, S.JL_BAR_GLOW_W, "bar glow width"); eq(C.JL_BAR_GLOW_A, S.JL_BAR_GLOW_A, "bar glow alpha")
eq(C.JL_BAR_CORE_W, S.JL_BAR_CORE_W, "bar core width"); eq(C.JL_BAR_CORE_A, S.JL_BAR_CORE_A, "bar core alpha")
eq(C.CHIP_PLATE_A, S.CHIP_PLATE_A, "chip plate alpha"); eq(C.CHIP_GLOW_K, S.CHIP_GLOW_K, "chip glow strength")
eq(C.POP_S, S.POP_S, "landing flash window"); eq(C.POP_A, S.POP_A, "landing flash alpha")
colorIs(C.COLORS.white, rgb(MU.CSS.white), "the flash white")
-- the debuff lengths the lane trusts are the mockup's (the HUD profile's own table is the ledger's, checked in hud-harness)
for id, sl in pairs(MU.SEALS) do eq(C.SEALS[id].deb, sl.deb, id .. " debuff seconds") end
eq(S.CHIP_CUT, 5, "the mockup chip cut (the baked chip is the shared 6, an approximation)")
near(S.CHIP_PLATE_MIX, 0.18, "the mockup tints the chip plate .18 toward the seal (NOT MAPPED: the baked plate is untinted)")
""")

case("the_judgement_bar_and_chip_follow_the_debuff_time")(r"""
NOW = 5000
local walks = {
    sotc = { 40, 30, 20, 10, 5, 2.5, 1.5, 0.5 }, sol = { 40, 25, 12, 6, 3 }, sow = { 39, 20, 8, 2.25, 1 },
    soj = { 10, 7.5, 5, 2.5, 1.9, 0.5 },
}
for _, key in ipairs({ "sotc", "sol", "sow", "soj" }) do
    local w = walks[key]
    local Seals = boot({ state = judgedState(key, w[1]) })
    local P = Seals.parts
    laneIs(P, w[1], key, key .. " rem " .. w[1])
    for i = 2, #w do
        tick(w[i - 1] - w[i])
        laneIs(P, w[i], key, key .. " rem " .. w[i])
    end
    check(next(DEGRADED) == nil, key .. ": no degrade: " .. tostring(next(DEGRADED)))
end
-- the axis is 0 to 40 s whatever the debuff: 10 s of Justice reaches a quarter of the way up
local Seals = boot({ state = judgedState("soj", 10) })
local l, t, w, h = imgRect(Seals.parts.jChip)
near3(t + h / 2, B.BOT - 10 / 40 * (B.BOT - B.TOP), "10 s of Justice sits at a quarter of the 40 s axis")
-- a debuff longer than the axis (a reconcile can report more) pins at the top like the seal's tube
local S2 = boot({ state = judgedState("sotc", 55) })
laneIs(S2.parts, 55, "sotc", "55 s pins at 40")
local l2, t2, w2, h2 = imgRect(S2.parts.jChip)
near3(t2 + h2 / 2, B.TOP, "the chip stops at the top of the axis")
-- built mid debuff and then left alone: the ticker moves the bar without another push
local S3 = boot({ state = judgedState("sow", 20) })
local _, top0 = imgRect(S3.parts.jBarCore)
tick(10)
local _, top1 = imgRect(S3.parts.jBarCore)
check(top1 > top0 + 1, "ten seconds later the bar top is lower, " .. top0 .. " to " .. top1)
laneIs(S3.parts, 10, "sow", "ten seconds later")
""")

case("the_lane_wears_the_chambers_colour_like_the_mockup")(r"""
NOW = 5000
-- mockup 2111 and 2188 to 2194: the header, the bar and the chip are all `col`, the CURRENT seal's colour (red under NO SEAL)
local Seals = boot({ state = judgedState("sol", 30, 10, "sow") })
local P = Seals.parts
laneIs(P, 30, "sow", "a Light debuff under a Wisdom seal is Wisdom's colour")
colorIs(P.edge.vertex, sealColor("wisdom"), "the seal edge is Wisdom's too")
-- swapping seal mid debuff recolours the whole lane at once
push(judgedState("sol", 30, 10, "sotc")); laneIs(P, 30, "sotc", "swapped to Crusader")
push(judgedState("sol", 25, 10, "soj")); laneIs(P, 25, "soj", "swapped to Justice")
push(judgedState("sol", 25, 10, "sor")); laneIs(P, 25, "sor", "swapped to Righteousness (gold)")
-- no seal: the chamber is red, so is the lane
local st = judgedState("soj", 6); st.seal = false; st.inCombat = false; push(st)
check(Seals.Mode() == "none", "no seal")
laneIs(P, 6, "red", "no seal plus a debuff is red")
colorIs(P.header.textColor, rgb(MU.CSS.red), "the SEAL header is red there as well")
-- and back to a seal
push(judgedState("soj", 6)); laneIs(P, 6, "soj", "a seal again")
-- an unknown seal: the look's own colour (violet, what the SEAL header wears)
local st2 = judgedState("sotc", 6); st2.seal = nil; push(st2)
check(Seals.Mode() == "unknown", "unknown seal")
laneIs(P, 6, "violet", "an unknown seal wears the unknown look's violet")
colorIs(P.header.textColor, rgb(MU.CSS.violet), "as does the SEAL header")
-- the seal running out recolours the lane by itself, before the Hud's push
local st3 = judgedState("sotc", 30); st3.seal.expiresAt = NOW + 2; push(st3)
tick(2.5); check(Seals.Mode() == "none", "the seal ran out")
laneIs(P, 27.5, "red", "and the lane went red with the chamber")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_target_without_the_debuff_shows_the_empty_lane")(r"""
NOW = 5000
local Seals = boot({ state = noJudgeState("sotc", false) })
local P = Seals.parts
laneEmpty(P, "NOT JUDGED", "none on the target, Crusader seal")
push(noJudgeState("sor", false)); laneEmpty(P, "NO DEBUFF", "Righteousness has no Judgement debuff")
push(noJudgeState("soj", false)); laneEmpty(P, "NOT JUDGED", "Justice")
push(noneState(false)); laneEmpty(P, "", "no seal draws no lane label")
push(unknownState()); laneEmpty(P, "", "an unknown seal draws no lane label")
-- UNKNOWN debuff (nil, e.g. after a loading screen): the mockup has no unknown look for the lane, so it wears the empty look
push(noJudgeState("sotc", nil)); laneEmpty(P, "NOT JUDGED", "unknown debuff (nil) wears the empty look")
push(noJudgeState("sor", nil)); laneEmpty(P, "NO DEBUFF", "unknown debuff, Righteousness")
-- a state with no judged field at all (a profile that never writes it)
local st = sealAt("sotc", 1000, 10); push(st); laneEmpty(P, "NOT JUDGED", "no judged field")
check(onUpdateFrames() == 1, "only the timed seal moves")
""")

case("an_unreadable_or_expired_debuff_draws_the_empty_lane_and_throws_nothing")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 20) })
local P = Seals.parts
laneIs(P, 20, "sotc", "control")
local bad = {
    ["a secret judged"] = function(st) st.judged = SECRET end,
    ["a string judged"] = function(st) st.judged = "up" end,
    ["a number judged"] = function(st) st.judged = 5 end,
    ["true judged"] = function(st) st.judged = true end,
    ["a secret key"] = function(st) st.judged.key = SECRET end,
    ["a number key"] = function(st) st.judged.key = 3 end,
    ["no key"] = function(st) st.judged.key = nil end,
    ["an unmapped key"] = function(st) st.judged.key = "nope" end,
    ["Righteousness (no debuff length)"] = function(st) st.judged.key = "sor" end,
    ["Fury (no debuff length)"] = function(st) st.judged.key = "sofu" end,
    ["a secret expiry"] = function(st) st.judged.expiresAt = SECRET end,
    ["a string expiry"] = function(st) st.judged.expiresAt = "soon" end,
    ["a NaN expiry"] = function(st) st.judged.expiresAt = 0 / 0 end,
    ["an infinite expiry"] = function(st) st.judged.expiresAt = math.huge end,
    ["no expiry"] = function(st) st.judged.expiresAt = nil end,
    ["an expiry that has passed"] = function(st) st.judged.expiresAt = NOW - 1 end,
    ["an expiry right now"] = function(st) st.judged.expiresAt = NOW end,
}
for what, mk in pairs(bad) do
    push(judgedState("sotc", 20)); laneIs(P, 20, "sotc", what .. " (before)")
    local st = judgedState("sotc", 20); mk(st)
    local ok, err = pcall(push, st)
    check(ok, what .. ": threw out of the subscriber: " .. tostring(err))
    laneEmpty(P, "NOT JUDGED", what)
    for i = 1, 3 do check(pcall(tick, .25), what .. ": threw in the ticker") end
    laneEmpty(P, "NOT JUDGED", what .. " after ticks")
    check(DEGRADED.gunsightseals_state == nil and DEGRADED.gunsightseals_tick == nil, what .. ": a degrade was logged: " .. tostring(next(DEGRADED)))
end
-- a whole secret state
push(judgedState("sotc", 20)); push(SECRET); laneEmpty(P, "", "a secret state")
-- a secret appliedAt only loses the flash: the bar is still drawn
local st = judgedState("sotc", 20, 0); st.judged.appliedAt = SECRET; push(st)
laneIs(P, 20, "sotc", "a secret appliedAt"); check(not vis(P.jPop), "and no flash")
tick(.1); check(DEGRADED.gunsightseals_tick == nil, "no tick degrade")
-- numbers the client flags as secret read as unknown and are never compared
local st2 = judgedState("sotc", 20, 5)
local flagged = { [st2.judged.expiresAt] = true }
SECRET_FN = function(v) return flagged[v] == true end
push(st2); laneEmpty(P, "NOT JUDGED", "a flagged expiry")
SECRET_FN = function(v) return rawequal(v, SECRET) end
""")

case("a_target_change_switches_the_lane")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P = Seals.parts
laneIs(P, 30, "sotc", "target A: Crusader 30 s")
push(noJudgeState("sotc", false)); laneEmpty(P, "NOT JUDGED", "target B: nothing on it")
push(judgedState("soj", 8)); laneIs(P, 8, "soj", "target C: Justice 8 s")
push(judgedState("sow", 35)); laneIs(P, 35, "sow", "target D: Wisdom 35 s (colour and height both switch)")
push(judgedState("sol", 12)); laneIs(P, 12, "sol", "target E: Light 12 s")
push(noJudgeState("sotc", nil)); laneEmpty(P, "NOT JUDGED", "target F: unknown")
push(judgedState("sotc", 3)); laneIs(P, 3, "sotc", "target A again")
-- the same target re-judged (a fresh appliedAt, a longer time): the bar jumps up and the chip follows
push(judgedState("sotc", 40, 0)); laneIs(P, 40, "sotc", "re-judged")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_debuff_that_runs_out_clears_the_lane_by_itself_and_stops_the_ticker")(r"""
NOW = 5000
-- an untimed old seal, so the lane is the only thing that moves
local function lane(rem)
    local st = judgedState("sotc", rem); st.seal.expiresAt = nil; st.seal.castAt = NOW - 100
    return st
end
local Seals = boot({ state = lane(3) })
local P = Seals.parts
check(onUpdateFrames() == 1 and Seals.frame:GetScript("OnUpdate") ~= nil, "a timed debuff on an untimed seal: one OnUpdate")
tick(1); laneIs(P, 2, "sotc", "2 s left")
tick(1.5); laneIs(P, 0.5, "sotc", "half a second left")
tick(0.25); laneIs(P, 0.25, "sotc", "a quarter left (the chip rests on the foot)")
check(onUpdateFrames() == 1, "still running")
tick(0.25)
laneEmpty(P, "NOT JUDGED", "the debuff ran out; no push has come")
check(onUpdateFrames() == 0, "and the ticker stopped itself")
tick(5); laneEmpty(P, "NOT JUDGED", "and it stays empty")
-- the Hud's own push for the expiry (judged false) repaints nothing new
push(noJudgeState("sotc", false)); laneEmpty(P, "NOT JUDGED", "the late push")
-- the lane clears even when a seal timer keeps the ticker alive
local S2 = boot({ state = judgedState("soj", 1) })
tick(.5); laneIs(S2.parts, .5, "soj", "Justice half a second")
tick(.6); laneEmpty(S2.parts, "NOT JUDGED", "Justice ran out under a running seal")
check(onUpdateFrames() == 1, "the seal timer still runs")
""")

case("the_landing_flash_fades_over_the_chip")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 40, 0) })
local P = Seals.parts
local white = rgb(MU.CSS.white)
local function flash(age, what)
    check(vis(P.jPop), what .. ": the flash is shown")
    colorIs(P.jPop.vertex, white, what .. ": white")
    near3(P.jPop.vertex[4], (1 - age / S.POP_S) * S.POP_A, what .. ": alpha (1 - age / .35) * .8")
    check(P.jPop.parent == P.jChip, what .. ": the flash is the chip's own, cut like it")
end
flash(0, "age 0")
tick(0.125); flash(0.125, "age .125")
tick(0.125); flash(0.25, "age .25")
tick(0.0625); flash(0.3125, "age .3125")
tick(0.0625); check(not vis(P.jPop), "past .35 the flash is gone (the window is age < .35)")
tick(1); check(not vis(P.jPop), "and stays gone")
-- a debuff that landed long ago (a target switch onto a judged mob) does not flash
push(judgedState("sol", 25, 12)); check(not vis(P.jPop), "an old debuff: no flash")
-- an appliedAt in the future does not flash either
local st = judgedState("sol", 25, -3); push(st); check(not vis(P.jPop), "a future appliedAt: no flash")
-- a fresh Judgement starts one, and a switch away mid flash hides it
push(judgedState("sow", 40, 0)); check(vis(P.jPop), "a fresh debuff flashes")
tick(.1); push(noJudgeState("sotc", false)); check(not vis(P.jPop), "the lane clears, so does the flash")
push(judgedState("sow", 40, 0)); tick(.1); push(judgedState("soj", 10, 9)); check(not vis(P.jPop), "an old debuff replacing a fresh one hides the flash")
push(noJudgeState("sotc", false)); push(judgedState("sol", 40, 0)); check(vis(P.jPop), "a fresh debuff after a cleared lane flashes again")
tick(.1); push(noJudgeState("sotc", false)); push(judgedState("sol", 40, 0)); check(vis(P.jPop), "and again after a flash cut short")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("the_landing_flash_ends_exactly_at_its_window")(r"""
-- a clock where 0.35 s is exact: the window is age < .35, so at exactly .35 the flash is gone
NOW = 0
local Seals = boot({ state = judgedState("sotc", 40, 0) })
check(vis(Seals.parts.jPop), "age 0: shown")
tick(0.34375); check(vis(Seals.parts.jPop), "age .34375: shown")
tick(0.00625); check(NOW == 0.35 and not vis(Seals.parts.jPop), "age .35 exactly: gone, got NOW " .. NOW)
""")

case("the_chip_wears_the_judgement_spell_icon")(r"""
NOW = 5000
local asked = {}
local function modern(tex) return function(id) asked[#asked + 1] = id; return tex end end
-- C_Spell.GetSpellTexture first, asked with the Judgement spell id the Hud already knows (HudSpells jd)
C_Spell = { GetSpellTexture = modern(135959) }
local Seals = boot({ state = judgedState("sotc", 30) })
local P = Seals.parts
local icon = P.jChip.icon
check(vis(icon) and icon.path == 135959, "the chip wears the spell's texture, got " .. tostring(icon.path))
check(asked[1] == FS.HudSpells.jd.ids[1] and asked[1] == 20271, "asked with Judgement's id 20271, got " .. tostring(asked[1]))
check(P.jChip.seatedBy == "SeatAuraTile", "the icon is seated inside the cut like every other chip")
local l, t, w, h = imgRect(P.jChip)
near3(w, S.CHS, "the icon chip is the mockup's 24 square")
local n = #asked
tick(1); tick(1); push(judgedState("sol", 20)); check(#asked == n, "the texture is read once, not per frame or push: " .. #asked .. " reads")
check(vis(icon) and icon.path == 135959, "and the icon stays through a change of seal")
push(noJudgeState("sotc", false)); push(judgedState("soj", 6)); check(vis(icon) and icon.path == 135959 and #asked == n, "and through an empty lane and back")
-- an unreadable answer leaves no icon and no error, and a later push retries
C_Spell = nil; GetSpellTexture = nil
local S2 = boot({ state = judgedState("sotc", 30) })
check(not vis(S2.parts.jChip.icon), "no texture API: no icon")
check(vis(S2.parts.jChip) and vis(S2.parts.jChip.fsAuraPlate), "but the chip itself (plate and ring) still draws")
check(next(DEGRADED) == nil, "the first unanswered ask logs nothing (the spell data may not be loaded yet): " .. tostring(next(DEGRADED)))
local function askAgain()        -- two more asks, 3 s apart: the third ask, 6 s after the first
    NOW = NOW + 3; push(judgedState("sotc", 30)); NOW = NOW + 3; push(judgedState("sotc", 30))
end
askAgain()
check(DEGRADED.gunsightseals_noicon ~= nil and next(DEGRADED, "gunsightseals_noicon") == nil and #(function() local n = {} for k in pairs(DEGRADED) do n[#n + 1] = k end return n end)() == 1,
    "still unanswered after three asks over 6 s: logged once as noicon and nothing else: " .. tostring(next(DEGRADED)))
C_Spell = { GetSpellTexture = modern(136012) }
push(judgedState("sotc", 30)); check(vis(S2.parts.jChip.icon) and S2.parts.jChip.icon.path == 136012, "an API that arrives later is picked up at the next push")
-- the legacy global when there is no C_Spell
C_Spell = nil; GetSpellTexture = modern("Interface\\Icons\\Spell_Holy_RighteousFury")
local S3 = boot({ state = judgedState("sotc", 30) })
check(S3.parts.jChip.icon.path == "Interface\\Icons\\Spell_Holy_RighteousFury", "the legacy GetSpellTexture is the fallback")
-- C_Spell wins over the legacy global
C_Spell = { GetSpellTexture = modern(1) }; GetSpellTexture = modern(2)
check(boot({ state = judgedState("sotc", 30) }).parts.jChip.icon.path == 1, "C_Spell.GetSpellTexture is preferred")
-- unusable answers: nil, false, a secret, zero, a NaN, an empty string, a throw
for what, v in pairs({ ["nil"] = false, ["false"] = "false", secret = SECRET, zero = 0, negative = -5, nan = 0 / 0, huge = math.huge, empty = "", table = {} }) do
    local val = v
    if v == false then val = nil elseif v == "false" then val = false end
    C_Spell = { GetSpellTexture = function() return val end }; GetSpellTexture = nil
    local S4 = boot({ state = judgedState("sotc", 30) })
    check(not vis(S4.parts.jChip.icon), what .. ": no icon")
    check(vis(S4.parts.jChip), what .. ": chip stays")
    tick(.5); check(DEGRADED.gunsightseals_noicon == nil, what .. ": the first ask logs nothing")
    askAgain(); check(DEGRADED.gunsightseals_noicon ~= nil and DEGRADED.gunsightseals_tick == nil and DEGRADED.gunsightseals_state == nil, what .. ": only noicon: " .. tostring(next(DEGRADED)))
end
C_Spell = { GetSpellTexture = function() error("boom") end }
local S5 = boot({ state = judgedState("sotc", 30) })
check(not vis(S5.parts.jChip.icon) and vis(S5.parts.jChip), "a throwing texture API leaves the chip without an icon")
tick(.5); check(DEGRADED.gunsightseals_noicon == nil, "and logs nothing at the first ask")
askAgain(); check(DEGRADED.gunsightseals_noicon ~= nil and DEGRADED.gunsightseals_tick == nil, "and logs only noicon once it stays unanswered: " .. tostring(next(DEGRADED)))
-- the re-ask happens only while a debuff is on the lane: an empty lane never asks, a debuff does
asked = {}
C_Spell = { GetSpellTexture = function(id) asked[#asked + 1] = id; return nil end }
local S7 = boot({ state = noJudgeState("sotc", false) })
push(noJudgeState("sol", false)); push(noJudgeState("sotc", nil)); tick(1)
check(#asked == 0, "no debuff on the lane: the icon is never asked for, got " .. #asked)
push(judgedState("sotc", 30)); check(#asked == 1, "a debuff asks once, got " .. #asked)
push(judgedState("sotc", 25)); check(#asked == 2, "and again at the next push while unanswered, got " .. #asked)
tick(1); tick(1); check(#asked == 2, "never per frame")
push(noJudgeState("sotc", false)); push(noJudgeState("sol", false)); check(#asked == 2, "and not once the lane empties, got " .. #asked)
-- a Hud without a Judgement spell (no HudSpells) draws no icon and asks nothing
C_Spell = { GetSpellTexture = modern(7) }; asked = {}
local S6 = boot({ beforeSeals = function() FS.HudSpells = nil end, state = judgedState("sotc", 30) })
check(not vis(S6.parts.jChip.icon) and #asked == 0, "no HudSpells: no icon, no read")
""")

case("the_chip_degrades_to_the_bar_when_the_chip_helpers_fail")(r"""
NOW = 5000
-- the DoT file builds its own chips through the same helpers, so only the chamber's chip is made to fail
local function failing(name)
    return function()
        local orig = FS.FrameHelpers[name] and FS.FrameHelpers or FS.Theme
        local fn = orig[name]
        orig[name] = function(button, ...)
            if button.parent and button.parent.name == "ForeverSynthwaveGunsightSeals" then error("boom " .. name) end
            return fn(button, ...)
        end
    end
end
for _, name in ipairs({ "SeatAuraTile", "SkinButton" }) do
    local Seals = boot({ beforeSeals = failing(name), state = judgedState("sotc", 30) })
    local P = Seals.parts
    check(P ~= nil and Seals.frame ~= nil, name .. ": the chamber still stands")
    check(P.jChip == nil and P.jPop == nil, name .. ": no chip")
    check(DEGRADED.gunsightseals_nochip ~= nil, name .. ": logged once as nochip")
    check(vis(P.jBarCore) and vis(P.jBarGlow), name .. ": the bar still draws")
    local _, tp = imgRect(P.jBarCore)
    tick(5); local _, tp2 = imgRect(P.jBarCore)
    check(tp2 > tp + 1, name .. ": and still follows the time")
    push(judgedState("soj", 6)); push(judgedState("sol", 20, 0)); tick(.1)
    push(noJudgeState("sotc", false)); check(not vis(P.jBarCore), name .. ": and clears")
    check(DEGRADED.gunsightseals_tick == nil and DEGRADED.gunsightseals_state == nil, name .. ": no tick or state degrade")
end
""")

case("the_ticker_runs_for_the_lane_only_while_a_debuff_is_up")(r"""
NOW = 5000
local function untimed(st) st.seal.expiresAt = nil; st.seal.castAt = NOW - 100; return st end
-- nothing judged on an old untimed seal: no ticker at all
local Seals = boot({ state = untimed(noJudgeState("sotc", false)) })
check(onUpdateFrames() == 0, "nothing judged: no OnUpdate")
push(untimed(noJudgeState("sotc", nil))); check(onUpdateFrames() == 0, "an unknown debuff: no OnUpdate")
push(untimed(judgedState("sotc", 20))); check(onUpdateFrames() == 1 and Seals.frame:GetScript("OnUpdate") ~= nil, "a debuff on the target: one OnUpdate, on the chamber")
push(untimed(judgedState("sol", 20))); push(untimed(judgedState("sow", 20))); check(onUpdateFrames() == 1, "still one")
push(untimed(noJudgeState("sotc", false))); check(onUpdateFrames() == 0, "the target without it: the ticker is cleared")
-- an old debuff that already ran out never starts it
local gone = untimed(judgedState("sotc", 20)); gone.judged.expiresAt = NOW - 5; push(gone)
check(onUpdateFrames() == 0, "an expired debuff: no OnUpdate")
-- it does not need a seal: none and unknown seals still draw the lane and tick for it
push(judgedState("soj", 9)); local st = judgedState("soj", 9); st.seal = false; st.inCombat = false; push(st)
check(onUpdateFrames() == 1, "no seal, debuff up: one OnUpdate"); tick(1); laneIs(Seals.parts, 8, "red", "no seal, a second later")
local u = unknownState(); u.judged = { key = "sotc", appliedAt = NOW - 5, expiresAt = NOW + 9, duration = 40 }; push(u)
check(onUpdateFrames() == 1, "unknown seal, debuff up: one OnUpdate")
-- the piece off stops it, a stale push does not restart it, on again resumes it
local stale = SUBS[1]
FS.Gunsight.SetPiece("dot", false, true); check(onUpdateFrames() == 0, "the piece off: no OnUpdate")
stale(judgedState("sotc", 20)); check(onUpdateFrames() == 0, "a stale push after the hide does not start it")
FS.Gunsight.SetPiece("dot", true, true); check(onUpdateFrames() == 1, "the piece back on: running again")
-- SetScript is called only on a real change
local calls = 0
local ch = Seals.frame
local orig = ch.SetScript
ch.SetScript = function(self, ...) calls = calls + 1; return orig(self, ...) end
for i = 1, 5 do push(untimed(judgedState("sotc", 20))) end
check(calls == 0, "five pushes of a ticking lane do not touch SetScript, got " .. calls)
check(#AURA_TOUCHED == 0, "no aura API was read")
""")

case("reduced_motion_still_drains_the_lane_and_flashes_like_the_mockup")(r"""
NOW = 5000
-- the mockup's reduce flag gates the neon, the pulse and the band wash, never the lane (the ring and the drain are not gated either)
local Seals = boot({ db = { reducedMotion = true }, state = judgedState("sotc", 30, 0) })
local P = Seals.parts
laneIs(P, 30, "sotc", "reduced motion")
check(vis(P.jPop), "the landing flash still shows (the mockup does not gate it)")
tick(.2); near3(P.jPop.vertex[4], (1 - .2 / S.POP_S) * S.POP_A, "and fades on its clock")
tick(.2); check(not vis(P.jPop), "and ends")
tick(10); laneIs(P, 19.6, "sotc", "and the bar still drains")
check(onUpdateFrames() == 1, "the ticker runs for the lane")
-- reduced motion with nothing judged and a steady seal: nothing runs
local S2 = boot({ db = { reducedMotion = true }, state = (function() local s = noJudgeState("sotc", false); s.seal.expiresAt = nil; s.seal.castAt = NOW - 100; return s end)() })
check(onUpdateFrames() == 0, "reduced motion, nothing judged, untimed seal: no OnUpdate")
-- a non true flag is not reduced motion
for what, v in pairs({ ["1"] = 1, ["string"] = "true" }) do
    local S3 = boot({ db = { reducedMotion = v }, state = judgedState("sotc", 30, 0) })
    check(vis(S3.parts.jPop), what .. ": still flashes")
end
""")

case("a_steady_lane_tick_writes_only_when_a_pixel_quarter_changes")(r"""
NOW = 5000
PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }
getmetatable(UIParent).GetEffectiveScale = function() return 1 end
local Seals = boot({ state = judgedState("sotc", 30) })
local P, ch = Seals.parts, Seals.frame
local W = {}
local function spy(obj, name, label)
    local orig = obj[name]
    obj[name] = function(self, ...) W[label or name] = (W[label or name] or 0) + 1; return orig(self, ...) end
end
local Fm = getmetatable(P.jBarCore).__index
local sizeWrites, pointWrites = 0, 0
for _, nm in ipairs({ "jBarCore", "jBarGlow" }) do
    local t = P[nm]
    local o = t.SetHeight; t.SetHeight = function(self, h) sizeWrites = sizeWrites + 1; return o(self, h) end
end
local op = P.jChip.SetPoint; P.jChip.SetPoint = function(self, ...) pointWrites = pointWrites + 1; return op(self, ...) end
for _, t in ipairs(TEXTURES) do
    if t.parent == ch or t.parent == P.jChip then
        for _, n in ipairs({ "SetVertexColor", "SetColorTexture", "SetTexture", "SetGradient", "SetBlendMode", "SetTexCoord", "SetDesaturated" }) do spy(t, n, "tex." .. n) end
    end
end
for _, f in ipairs(FONTSTRINGS) do
    if f.parent == ch then for _, n in ipairs({ "SetText", "SetTextColor", "SetFont" }) do spy(f, n, "fs." .. n) end end
end
spy(FS.Theme, "ApplyMono")
local oc = CreateColor
CreateColor = function(...) W.CreateColor = (W.CreateColor or 0) + 1; return oc(...) end
-- 1 ms ticks: a quarter screen pixel is far longer than that, so most ticks write nothing
local chipWrites, barWrites = P.jChip.writes or 0, (P.jBarCore.writes or 0) + (P.jBarGlow.writes or 0)
for i = 1, 200 do tick(.001) end
CreateColor = oc
check((P.jChip.writes or 0) == chipWrites, "the chip is not shown again on every move")
check((P.jBarCore.writes or 0) + (P.jBarGlow.writes or 0) == barWrites, "nor the bar")
check(W.CreateColor == nil, "a steady lane tick created a colour")
for _, k in ipairs({ "tex.SetColorTexture", "tex.SetTexture", "tex.SetGradient", "tex.SetBlendMode", "tex.SetTexCoord", "fs.SetText", "fs.SetTextColor", "fs.SetFont", "ApplyMono" }) do
    check(W[k] == nil, "a steady lane tick wrote " .. k .. " " .. tostring(W[k]) .. " times")
end
check(sizeWrites > 0 and sizeWrites < 2 * 200, "the bar height is written on a pixel quarter change only, got " .. sizeWrites .. " writes in 200 ticks")
check(pointWrites > 0 and pointWrites < 200, "the chip is re-seated on a pixel quarter change only, got " .. pointWrites .. " in 200 ticks")
-- the heights it did write are whole quarter pixels (image px for a quarter of a 1/1440 screen pixel at this scale)
for _, nm in ipairs({ "jBarGlow", "jBarCore" }) do
    local _, tp, tw, th = imgRect(P[nm])
    check(math.abs(th - (29.8 / 40 * (B.BOT - B.TOP) - S.CHS / 2)) < 0.3, nm .. " is within a quarter screen pixel of the true height, got " .. th)
end
local _, ct, _, chh = imgRect(P.jChip)
check(math.abs(ct + chh / 2 - jY(29.8)) < 0.3, "and so is the chip")
""")

case("a_client_without_gradients_still_draws_the_lane_bar_in_a_flat_tint")(r"""
NOW = 5000
local mt = getmetatable(UIParent)
local origCreateTexture, realCreateColor = mt.CreateTexture, CreateColor
local function noSetGradient()
    mt.CreateTexture = function(self, ...)
        local t = origCreateTexture(self, ...)
        t.SetGradient = nil
        return t
    end
end
local function noCreateColor() CreateColor = nil end
for _, variant in ipairs({ { "no Texture:SetGradient", noSetGradient }, { "no CreateColor", noCreateColor } }) do
    local what = variant[1]
    mt.CreateTexture = origCreateTexture; CreateColor = realCreateColor
    local Seals = boot({ beforeSeals = variant[2], state = judgedState("sow", 20) })
    local P = Seals.parts
    for _, nm in ipairs({ "jBarGlow", "jBarCore" }) do
        check(vis(P[nm]) and P[nm].gradient == nil, what .. ": " .. nm .. " shows with no gradient")
        colA(P[nm].color, sealColor("wisdom"), 1, what .. ": " .. nm .. " flat seal tint")
    end
    local _, tp, _, th = imgRect(P.jBarCore)
    near3(tp, jY(20) + S.CHS / 2, what .. ": the bar still follows the time")
    push(judgedState("soj", 8)); colA(P.jBarCore.color, sealColor("justice"), 1, what .. ": and the next seal's tint")
    colA(P.jBarGlow.color, sealColor("justice"), 1, what .. ": glow too")
    tick(1); check(next(DEGRADED) == nil, what .. ": no degrade: " .. tostring(next(DEGRADED)))
end
mt.CreateTexture = origCreateTexture; CreateColor = realCreateColor
""")

case("the_lane_repaints_only_when_the_debuffs_seal_changes")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P, ch = Seals.parts, Seals.frame
local W = {}
local function spy(obj, name, label)
    local orig = obj[name]
    obj[name] = function(self, ...) W[label] = (W[label] or 0) + 1; return orig(self, ...) end
end
local lane = { P.jAxis, P.jBarGlow, P.jBarCore }
for _, t in ipairs(P.jTicks) do lane[#lane + 1] = t end
for _, t in ipairs(lane) do
    for _, n in ipairs({ "SetColorTexture", "SetGradient", "SetVertexColor" }) do spy(t, n, "tex." .. n) end
end
for _, fs in pairs(P.jLabels) do spy(fs, "SetTextColor", "fs.SetTextColor") end
spy(P.judged, "SetTextColor", "fs.SetTextColor")
for _, fs in ipairs(P.stack) do spy(fs, "SetText", "fs.SetText") end
spy(P.jChip.fsSkin.border.ring, "SetVertexColor", "ring")
local oc = CreateColor
CreateColor = function(...) W.CreateColor = (W.CreateColor or 0) + 1; return oc(...) end
-- the same debuff re-pushed, a new time on the same seal, a re-judge: no colour or label write
push(judgedState("sotc", 30)); push(judgedState("sotc", 12)); push(judgedState("sotc", 40, 0)); tick(1)
check(next(W) == nil, "a lane of the same seal rewrote " .. tostring(next(W)))
-- another seal recolours the lane: each bar texture is written once (the seal look makes its own colours too, so CreateColor is not counted)
W["tex.SetGradient"] = nil
push(judgedState("sow", 20))
check(W["tex.SetGradient"] == 2, "a new colour sets the two bar gradients once, got " .. tostring(W["tex.SetGradient"]))
push(judgedState("sow", 19)); check(W["tex.SetGradient"] == 2, "and the same colour again writes nothing more")
-- the gradient colours are made once per lane colour: to empty and back under one seal asks CreateColor for nothing new
push(noJudgeState("sow", false)); W.CreateColor = nil
push(judgedState("sow", 18)); check(W.CreateColor == nil, "the lane colour's gradient is kept: no CreateColor on the way back, got " .. tostring(W.CreateColor))
CreateColor = oc
""")

case("the_bar_goes_when_the_chip_exactly_covers_it")(r"""
NOW = 5000
-- a quarter pixel of exactly 3/16 image px: 12 (the chip's half) is a whole 64 steps, so the bar length lands on exactly 0
boot({ noEvents = true })
local k = FS.Gunsight.ui(1)
PixelUtil = { GetPixelToUIUnitFactor = function() return 0.1875 * k / 0.25 end }
getmetatable(UIParent).GetEffectiveScale = function() return 1 end
local Seals = boot({ state = judgedState("sotc", S.CHS / 2 * S.JL_MAX_S / (B.BOT - B.TOP)) })
local P = Seals.parts
local _, t, _, h = imgRect(P.jChip)
near3(t + h / 2, B.BOT - S.CHS / 2, "the chip rests half its size above the foot")
check(not vis(P.jBarCore) and not vis(P.jBarGlow), "a bar of zero length is hidden, not drawn at height 0")
push(judgedState("sotc", 5)); check(vis(P.jBarCore), "a longer one shows")
""")

case("a_retarget_repaints_the_lane_at_once_from_the_huds_own_read")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P = Seals.parts
local answer
FS.Hud.GetJudgement = function() return answer end
local function retarget(a, what, ...)
    answer = a
    local ok, err = pcall(fire, "PLAYER_TARGET_CHANGED")
    check(ok, what .. ": threw: " .. tostring(err))
end
-- target B carries Light with 12 s left: the lane shows it before any Hud push
retarget({ judgeAt = NOW - 5, remaining = 12, key = "sol" }, "B")
laneIs(P, 12, "sotc", "target B at once (the chamber's colour, B's time)")
check(not vis(P.jPop), "no flash for a debuff read off a target switch")
tick(2); laneIs(P, 10, "sotc", "and it keeps draining")
-- target C has none
retarget({ judgeAt = NOW - 5, remaining = 0 }, "C"); laneEmpty(P, "NOT JUDGED", "target C: none")
check(onUpdateFrames() == 1, "the seal timer still runs")
retarget({ remaining = 20, key = "soj" }, "D"); laneIs(P, 20, "sotc", "target D")
-- unknown (remaining nil), no answer table, an unmapped key and a Righteousness key all empty the lane
for what, a in pairs({ unknown = { key = "sol" }, ["no remaining"] = {}, nokey = { remaining = 5 }, unmapped = { remaining = 5, key = "zz" },
    righteousness = { remaining = 5, key = "sor" }, ["not a table"] = 7, ["nil"] = false, secret = SECRET,
    ["secret remaining"] = { remaining = SECRET, key = "sol" }, ["secret key"] = { remaining = 5, key = SECRET },
    ["string remaining"] = { remaining = "5", key = "sol" }, nan = { remaining = 0 / 0, key = "sol" },
    inf = { remaining = math.huge, key = "sol" }, negative = { remaining = -3, key = "sol" } }) do
    retarget({ remaining = 20, key = "sol" }, what .. " (before)"); laneIs(P, 20, "sotc", what .. " before")
    retarget(a == false and nil or a, what); laneEmpty(P, "NOT JUDGED", what)
end
-- GetJudgement missing or throwing: the old target's bar must not stay
retarget({ remaining = 20, key = "sol" }, "again"); laneIs(P, 20, "sotc", "before a failing read")
FS.Hud.GetJudgement = function() error("boom") end
fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "a throwing GetJudgement")
FS.Hud.GetJudgement = function() return { remaining = 20, key = "sol" } end; fire("PLAYER_TARGET_CHANGED"); laneIs(P, 20, "sotc", "and back")
FS.Hud.GetJudgement = nil
fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "no GetJudgement at all")
check(DEGRADED.gunsightseals_tick == nil and DEGRADED.gunsightseals_state == nil, "no tick or state degrade: " .. tostring(next(DEGRADED)))
-- the Hud's push that follows carries the full ledger entry and takes over
FS.Hud.GetJudgement = function() return { remaining = 20, key = "sol" } end; fire("PLAYER_TARGET_CHANGED")
push(judgedState("sol", 19.5, 10, "sotc")); laneIs(P, 19.5, "sotc", "the push after")
-- a flash on the old target does not follow the retarget
push(judgedState("sol", 30, 0, "sotc")); check(vis(P.jPop), "a fresh debuff flashes")
FS.Hud.GetJudgement = function() return { remaining = 20, key = "sol" } end
tick(.1); fire("PLAYER_TARGET_CHANGED"); check(not vis(P.jPop), "the new target's lane carries no flash")
laneIs(P, 20, "sotc", "and shows its debuff")
-- a throw while painting is contained and logged by the event, and the lane is retried at the next event
local ring = P.jChip.fsSkin.border.ring
local origRing = ring.SetVertexColor
FS.Hud.GetJudgement = function() return { remaining = 5, key = "soj" } end
fire("PLAYER_TARGET_CHANGED"); laneIs(P, 5, "sotc", "a good event")
FS.Hud.GetJudgement = function() return { remaining = 0, key = "soj" } end
fire("PLAYER_TARGET_CHANGED")
ring.SetVertexColor = function() error("boom") end
FS.Hud.GetJudgement = function() return { remaining = 7, key = "soj" } end
check(pcall(fire, "PLAYER_TARGET_CHANGED"), "the event contained the throw")
check(DEGRADED.gunsightseals_target ~= nil, "and logged it as target")
ring.SetVertexColor = origRing
fire("PLAYER_TARGET_CHANGED"); laneIs(P, 7, "sotc", "the next event repaints the whole lane")
DEGRADED.gunsightseals_target = nil
-- a stopped ticker (a tick threw) comes back with a retarget
local bar = P.jBarCore
local origH = bar.SetHeight
bar.SetHeight = function() error("tick boom") end
tick(.5)
check(DEGRADED.gunsightseals_tick ~= nil, "the tick threw and stopped")
bar.SetHeight = origH
DEGRADED.gunsightseals_tick = nil
fire("PLAYER_TARGET_CHANGED")
tick(.25); laneIs(P, 6.75, "sotc", "a retarget restarted the lane's ticker")
-- an empty lane never asks for the icon on a target change
local asked2 = 0
C_Spell = { GetSpellTexture = function() asked2 = asked2 + 1; return nil end }
local S9 = boot({ state = noJudgeState("sotc", false) })
FS.Hud.GetJudgement = function() return { remaining = 0 } end
fire("PLAYER_TARGET_CHANGED"); fire("PLAYER_TARGET_CHANGED")
check(asked2 == 0, "a retarget onto an empty lane asks for no icon, got " .. asked2)
FS.Hud.GetJudgement = function() return { remaining = 9, key = "sol" } end
fire("PLAYER_TARGET_CHANGED"); check(asked2 == 1, "onto a judged one it asks, got " .. asked2)
-- a hidden piece ignores the event: nothing is read
Seals = boot({ state = judgedState("sotc", 30) })
local reads = 0
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 5, key = "sol" } end
FS.Gunsight.SetPiece("dot", false, true); fire("PLAYER_TARGET_CHANGED")
check(reads == 0, "the piece off: the event reads nothing, got " .. reads)
FS.Gunsight.SetPiece("dot", true, true); fire("PLAYER_TARGET_CHANGED"); check(reads == 1, "back on: it reads, got " .. reads)
-- the event is cheap: one frame, one script, registered once
local evFrames = 0
for _, f in ipairs(FRAMES) do if f.scripts.OnEvent and f.parent == Seals.frame then evFrames = evFrames + 1 end end
check(evFrames == 1, "one event frame on the chamber, got " .. evFrames)
""")

case("a_dead_target_hides_the_lane")(r"""
NOW = 5000
local dead = false
UnitIsDead = function(unit) check(unit == "target", "asked about " .. tostring(unit)); return dead end
local function untimed(st) st.seal.expiresAt = nil; st.seal.castAt = NOW - 100; return st end
local Seals = boot({ state = untimed(judgedState("sotc", 30)) })
local P = Seals.parts
laneIs(P, 30, "sotc", "a live target")
-- a push for a dead target
dead = true; push(untimed(judgedState("sotc", 30))); laneEmpty(P, "NOT JUDGED", "a dead target, by push")
check(onUpdateFrames() == 0, "and nothing ticks")
dead = false; push(untimed(judgedState("sotc", 30))); laneIs(P, 30, "sotc", "alive again")
-- it dies while the lane is up: UNIT_HEALTH for the target
dead = true; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "died under the lane")
check(onUpdateFrames() == 0, "the ticker stopped")
-- a live target's health events change nothing and ask nothing more than once each
dead = false; push(untimed(judgedState("sotc", 30)))
local asks = 0
UnitIsDead = function() asks = asks + 1; return false end
fire("UNIT_HEALTH", "target"); fire("UNIT_HEALTH", "target"); laneIs(P, 30, "sotc", "health events on a live target")
check(asks == 2, "one UnitIsDead per health event, got " .. asks)
asks = 0; fire("UNIT_HEALTH", "player"); fire("UNIT_HEALTH", "party1"); check(asks == 0, "another unit's health is not heard")
-- a push with no debuff never asks about death
asks = 0; push(untimed(noJudgeState("sotc", false))); check(asks == 0, "no debuff in the push: UnitIsDead is not asked, got " .. asks)
push(untimed(judgedState("sotc", 30)))
-- a live target's health event does no lane work: the clock moves, the bar must not until a frame runs
UnitIsDead = function() return false end
local _, top0 = imgRect(P.jBarCore)
NOW = NOW + 0.5; fire("UNIT_HEALTH", "target")
local _, top1 = imgRect(P.jBarCore)
near3(top1, top0, "a live target's health event leaves the bar for the next frame")
UnitIsDead = function() asks = asks + 1; return false end
-- no debuff on the lane: a health event reads nothing
push(untimed(noJudgeState("sotc", false))); asks = 0; fire("UNIT_HEALTH", "target"); check(asks == 0, "an empty lane skips the dead check, got " .. asks)
-- a target switch onto a dead target with a debuff in the ledger
UnitIsDead = function() return true end
FS.Hud.GetJudgement = function() return { remaining = 12, key = "sol" } end
push(untimed(judgedState("sotc", 30))); laneEmpty(P, "NOT JUDGED", "dead on arrival (push)")
fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "dead on arrival (event)")
UnitIsDead = function() return false end
fire("PLAYER_TARGET_CHANGED"); laneIs(P, 12, "sotc", "a live one")
-- unreadable answers count as alive: secret, nil, a throw, a missing API, a string
for what, fn in pairs({ secret = function() return SECRET end, ["nil"] = function() return nil end, throws = function() error("x") end,
    string = function() return "dead" end, table = function() return {} end, ["false"] = function() return false end, zero = function() return 0 end }) do
    UnitIsDead = fn
    push(untimed(judgedState("sotc", 30))); laneIs(P, 30, "sotc", what .. ": counts as alive")
    check(pcall(fire, "UNIT_HEALTH", "target"), what .. ": threw out of the event"); laneIs(P, 30, "sotc", what .. ": still alive after a health event")
end
UnitIsDead = function() return 1 end
push(untimed(judgedState("sotc", 30))); laneEmpty(P, "NOT JUDGED", "the legacy 1 reads as dead")
UnitIsDead = nil
push(untimed(judgedState("sotc", 30))); laneIs(P, 30, "sotc", "no UnitIsDead at all: alive")
check(DEGRADED.gunsightseals_tick == nil and DEGRADED.gunsightseals_state == nil, "no tick or state degrade: " .. tostring(next(DEGRADED)))
""")

case("noicon_is_logged_only_when_the_icon_stays_unanswered")(r"""
NOW = 5000
local resolved = false
local function counting()
    local n = { count = 0 }
    local base = FS.LogDegradeOnce
    FS.LogDegradeOnce = function(k, m) if k == "gunsightseals_noicon" then n.count = n.count + 1 end base(k, m) end
    return n
end
-- spell data that arrives late: many asks inside a few seconds, then it answers, and nothing is ever logged
C_Spell = { GetSpellTexture = function() if resolved then return 136012 end return nil end }; GetSpellTexture = nil
local S = boot({ state = judgedState("sotc", 30) })
local n = counting()
check(DEGRADED.gunsightseals_noicon == nil, "the first nil logs nothing")
for _ = 1, 4 do NOW = NOW + 1; push(judgedState("sotc", 29)) end
check(DEGRADED.gunsightseals_noicon == nil, "five asks inside 4 s log nothing: " .. tostring(DEGRADED.gunsightseals_noicon))
resolved = true; NOW = NOW + 1; push(judgedState("sotc", 25))
check(vis(S.parts.jChip.icon) and S.parts.jChip.icon.path == 136012, "the late answer is picked up")
NOW = NOW + 60; push(judgedState("sotc", 25)); tick(1)
check(DEGRADED.gunsightseals_noicon == nil and n.count == 0, "and noicon is never logged")
-- never resolves: three asks are not enough before 5 s, the ask at 5 s logs, once
resolved = false
S = boot({ state = judgedState("sotc", 30) })
n = counting()
NOW = NOW + 2; push(judgedState("sotc", 28)); NOW = NOW + 2; push(judgedState("sotc", 26))
check(n.count == 0, "three asks over 4 s: nothing yet")
NOW = NOW + 0.5; push(judgedState("sotc", 25.5)); check(n.count == 0, "four asks over 4.5 s: nothing yet")
NOW = NOW + 0.5; push(judgedState("sotc", 25)); check(n.count == 1, "the ask 5 s after the first logs, got " .. n.count)
NOW = NOW + 1; push(judgedState("sotc", 24)); NOW = NOW + 10; push(judgedState("sotc", 14)); tick(.5)
check(n.count == 1, "and only once, got " .. n.count)
-- time alone is not enough: two asks 10 s apart log nothing, the third does
S = boot({ state = judgedState("sotc", 30) })
n = counting()
NOW = NOW + 10; push(judgedState("sotc", 30)); check(n.count == 0, "two asks 10 s apart: nothing yet")
NOW = NOW + 0.25; push(judgedState("sotc", 30)); check(n.count == 1, "the third logs, got " .. n.count)
-- a retarget onto a judged target is an ask too
S = boot({ state = judgedState("sotc", 30) })
n = counting()
FS.Hud.GetJudgement = function() return { remaining = 9, key = "sol" } end
NOW = NOW + 3; fire("PLAYER_TARGET_CHANGED"); NOW = NOW + 3; fire("PLAYER_TARGET_CHANGED")
check(n.count == 1, "asks from target changes count, got " .. n.count)
""")

case("the_event_frame_listens_only_while_the_piece_is_subscribed")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local ev = Seals.parts.events
check(ev.events.PLAYER_TARGET_CHANGED and ev.events.UNIT_HEALTH, "registered while subscribed")
check(type(ev.unitOnly) == "table" and #ev.unitOnly.UNIT_HEALTH == 1 and ev.unitOnly.UNIT_HEALTH[1] == "target", "UNIT_HEALTH for the target only")
FS.Gunsight.SetPiece("dot", false, true)
check(not ev.events.PLAYER_TARGET_CHANGED and not ev.events.UNIT_HEALTH, "unregistered when the piece goes off")
FS.Gunsight.SetPiece("dot", true, true)
check(ev.events.PLAYER_TARGET_CHANGED and ev.events.UNIT_HEALTH and ev.unitOnly.UNIT_HEALTH[1] == "target", "and again when it comes back")
FS.Gunsight.SetPiece("dot", true, true)
check(ev.events.PLAYER_TARGET_CHANGED and ev.events.UNIT_HEALTH, "a repeat changes nothing")
-- a piece saved off never registers
local Off = boot({ db = { gunsight = { pieces = { dot = false } } }, state = judgedState("sotc", 30) })
check(not Off.parts.events.events.PLAYER_TARGET_CHANGED and not Off.parts.events.events.UNIT_HEALTH, "a piece saved off registers nothing")
FS.Gunsight.SetPiece("dot", true, true)
check(Off.parts.events.events.PLAYER_TARGET_CHANGED and Off.parts.events.events.UNIT_HEALTH, "and registers when it is switched on")
-- a Hud that has gone missing never subscribes, so it never registers
local Gone = boot({ state = judgedState("sotc", 30) })
FS.Gunsight.SetPiece("dot", false, true); FS.Hud = nil; FS.Gunsight.SetPiece("dot", true, true)
check(not Gone.parts.events.events.PLAYER_TARGET_CHANGED and not Gone.parts.events.events.UNIT_HEALTH, "no Hud at subscribe time: nothing is registered")
-- a RegisterEvent that throws on the event frame must not cost the Hud subscription
do
    local mt2 = getmetatable(UIParent)
    local origRE = mt2.RegisterEvent
    mt2.RegisterEvent = function(self, e)
        if self.parent and self.parent.name == "ForeverSynthwaveGunsightSeals" then error("boom") end
        return origRE(self, e)
    end
    local ok, err = pcall(function()
        local S = boot({ state = judgedState("sotc", 30) })
        laneIs(S.parts, 30, "sotc", "the Hud push still reached the lane")
        check(#SUBS == 1 or #SUBS == 2, "the chamber is subscribed to the Hud, got " .. #SUBS)
        check(DEGRADED.gunsightseals_listen ~= nil, "and the failure is logged as listen: " .. tostring(next(DEGRADED)))
        push(judgedState("sol", 20, 10, "sotc")); laneIs(S.parts, 20, "sotc", "later pushes still land")
        FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
        push(judgedState("sol", 18, 10, "sotc")); laneIs(S.parts, 18, "sotc", "and after a toggle")
    end)
    mt2.RegisterEvent = origRE
    check(ok, tostring(err))
end
-- a client without RegisterUnitEvent, or one that throws, still gets the target change and a working chamber
local mt = getmetatable(UIParent)
local orig = mt.RegisterUnitEvent
for what, fn in pairs({ missing = false, throwing = function() error("boom") end }) do
    mt.RegisterUnitEvent = fn or nil
    local ok, err = pcall(function()
        local S = boot({ state = judgedState("sotc", 30) })
        check(S.parts.events.events.PLAYER_TARGET_CHANGED, what .. ": the target change is registered")
        check(not S.parts.events.events.UNIT_HEALTH, what .. ": no health event without the unit filter")
        FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
        check(S.parts.events.events.PLAYER_TARGET_CHANGED, what .. ": and after a toggle")
        check(next(DEGRADED) == nil, what .. ": nothing is logged: " .. tostring(next(DEGRADED)))
    end)
    mt.RegisterUnitEvent = orig
    check(ok, what .. ": " .. tostring(err))
end
""")

case("a_secret_target_guid_empties_the_lane_until_the_next_push")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P = Seals.parts
local reads = 0
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 12, key = "sol" } end
-- a plain GUID keeps the direct read
UnitGUID = function(unit) check(unit == "target", "asked about " .. tostring(unit)); return "Creature-0-0-0-0-1-0000000002" end
fire("PLAYER_TARGET_CHANGED"); laneIs(P, 12, "sotc", "a plain GUID"); check(reads == 1, "the plain GUID reads, got " .. reads)
-- no target: nil is plain, the Hud answers none
UnitGUID = function() return nil end
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 0 } end
fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "no target"); check(reads == 2, "a nil GUID is plain: it reads, got " .. reads)
-- a secret GUID: the Hud may still hold the old target, so the lane is emptied and the Hud is not even asked
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 12, key = "sol" } end
UnitGUID = function() return "Creature-0-0-0-0-1-0000000002" end
fire("PLAYER_TARGET_CHANGED"); laneIs(P, 12, "sotc", "setup"); local before = reads
UnitGUID = function() return SECRET end
fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "a secret GUID")
check(reads == before, "a secret GUID reads nothing from the Hud, got " .. (reads - before))
-- the next push carries the entry and takes over
push(judgedState("sol", 11.5, 10, "sotc")); laneIs(P, 11.5, "sotc", "the push after")
-- a throwing or missing UnitGUID cannot be vouched for either
for what, fn in pairs({ throwing = function() error("boom") end, missing = false }) do
    UnitGUID = fn or nil
    local r0 = reads
    check(pcall(fire, "PLAYER_TARGET_CHANGED"), what .. ": the event threw")
    laneEmpty(P, "NOT JUDGED", what .. " UnitGUID"); check(reads == r0, what .. ": nothing read")
    push(judgedState("sol", 11.5, 10, "sotc")); laneIs(P, 11.5, "sotc", what .. ": the push repaints")
end
-- health events never read the GUID
UnitGUID = function() error("health events must not ask for the GUID") end
UnitIsDead = function() return false end
check(pcall(fire, "UNIT_HEALTH", "target"), "a health event does not ask for the GUID")
check(DEGRADED.gunsightseals_target == nil and DEGRADED.gunsightseals_state == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_resurrected_target_relights_the_lane")(r"""
NOW = 5000
local dead, reads = false, 0
UnitIsDead = function(unit) return dead end
local function untimed(st) st.seal.expiresAt = nil; st.seal.castAt = NOW - 100; return st end
local Seals = boot({ state = untimed(judgedState("sotc", 30)) })
local P = Seals.parts
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 12, key = "sol" } end
-- hidden by a push for a dead target, relit by the health event once it is alive: from the Hud's own read, no flash
dead = true; push(untimed(judgedState("sotc", 30))); laneEmpty(P, "NOT JUDGED", "dead (push)")
reads = 0; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "still dead after a health event")
check(reads == 0, "a still dead target is not read, got " .. reads)
dead = false
local deadAsks = 0
UnitIsDead = function() deadAsks = deadAsks + 1; return dead end
fire("UNIT_HEALTH", "target")
laneIs(P, 12, "sotc", "resurrected: relit at once"); check(reads == 1, "one Hud read, got " .. reads)
check(deadAsks == 1, "and one UnitIsDead, got " .. deadAsks)
check(not vis(P.jPop), "the relit lane carries no flash")
check(onUpdateFrames() == 1, "and the ticker runs for it")
-- a live target's further health events do nothing again
reads = 0; fire("UNIT_HEALTH", "target"); check(reads == 0, "a live lane's health event reads nothing, got " .. reads)
-- it dies under the lane (event), then comes back (event)
dead = true; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "died under the lane")
dead = false; fire("UNIT_HEALTH", "target"); laneIs(P, 12, "sotc", "and back")
-- dead on arrival (retarget), then resurrected
dead = true; fire("PLAYER_TARGET_CHANGED"); laneEmpty(P, "NOT JUDGED", "dead on arrival")
dead = false; fire("UNIT_HEALTH", "target"); laneIs(P, 12, "sotc", "relit")
-- the Hud now says none: the lane stays empty
dead = true; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "dead again")
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 0 } end
dead = false; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "alive with no debuff")
FS.Hud.GetJudgement = function() reads = reads + 1; return { remaining = 12, key = "sol" } end
reads = 0; fire("UNIT_HEALTH", "target"); check(reads == 0, "an empty lane that was not hidden by death reads nothing, got " .. reads)
local asks = 0
UnitIsDead = function() asks = asks + 1; return false end
fire("UNIT_HEALTH", "target"); check(asks == 0, "and does not ask whether it is dead, got " .. asks)
-- a lane with no debuff in the push is not marked dead, so a health event later does nothing
UnitIsDead = function() return true end
push(untimed(noJudgeState("sotc", false))); reads = 0; fire("UNIT_HEALTH", "target"); check(reads == 0, "no debuff, dead target: nothing read")
UnitIsDead = function() return false end
fire("UNIT_HEALTH", "target"); check(reads == 0, "no debuff, resurrected: nothing read, got " .. reads)
-- the secret GUID rule: alive again but the Hud may be behind, so the lane waits for the push
dead = true; UnitIsDead = function() return dead end
push(untimed(judgedState("sotc", 30))); laneEmpty(P, "NOT JUDGED", "dead (push) again")
UnitGUID = function() return SECRET end
dead = false; reads = 0; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "alive but a secret GUID")
check(reads == 0, "a secret GUID is not read, got " .. reads)
push(untimed(judgedState("sotc", 30))); laneIs(P, 30, "sotc", "the push relights it")
-- a second health event after the push does not read either (no longer hidden by death)
reads = 0; fire("UNIT_HEALTH", "target"); check(reads == 0, "relit by the push: no read, got " .. reads)
-- an unreadable death answer counts as alive
UnitGUID = function() return "Creature-0-0-0-0-1-0000000003" end
dead = true; fire("UNIT_HEALTH", "target"); laneEmpty(P, "NOT JUDGED", "dead")
UnitIsDead = function() return SECRET end
fire("UNIT_HEALTH", "target"); laneIs(P, 12, "sotc", "a secret answer reads as alive and relights")
check(DEGRADED.gunsightseals_target == nil and DEGRADED.gunsightseals_state == nil and DEGRADED.gunsightseals_tick == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_throwing_lane_paint_is_retried_not_latched")(r"""
NOW = 5000
local Seals = boot({ state = noJudgeState("sotc", false) })
local P = Seals.parts
local ring = P.jChip.fsSkin.border.ring
local orig = ring.SetVertexColor
ring.SetVertexColor = function() error("boom") end
push(judgedState("sotc", 30))
check(DEGRADED.gunsightseals_state ~= nil, "the throw was contained and logged")
ring.SetVertexColor = orig
push(judgedState("sotc", 29)); laneIs(P, 29, "sotc", "the next push repaints the whole lane")
-- the same for a throw while painting the bar
local Seals2 = boot({ state = noJudgeState("sotc", false) })
local P2 = Seals2.parts
local og = P2.jBarCore.SetGradient
P2.jBarCore.SetGradient = function() error("boom") end
push(judgedState("sow", 30))
P2.jBarCore.SetGradient = og
push(judgedState("sow", 29)); laneIs(P2, 29, "sow", "a failed bar paint is retried too")
-- and a throw on the way back to the empty lane
local og2 = P2.judged.SetTextColor
P2.judged.SetTextColor = function() error("boom") end
push(noJudgeState("sow", false))
P2.judged.SetTextColor = og2
push(noJudgeState("sow", false)); laneEmpty(P2, "NOT JUDGED", "a failed empty paint is retried")
""")

case("the_bar_rounds_to_the_nearest_quarter_pixel_not_down")(r"""
NOW = 5000
boot({ noEvents = true })
local k = FS.Gunsight.ui(1)
PixelUtil = { GetPixelToUIUnitFactor = function() return 0.1875 * k / 0.25 end }       -- a quarter pixel of exactly 3/16 image px
getmetatable(UIParent).GetEffectiveScale = function() return 1 end
local q = 0.1875
local function heightAt(steps)                                  -- a remaining time whose true height is `steps` quarter pixels
    local Seals = boot({ state = judgedState("sotc", steps * q * S.JL_MAX_S / (B.BOT - B.TOP)) })
    local _, t, _, h = imgRect(Seals.parts.jChip)
    return B.BOT - (t + h / 2)
end
near3(heightAt(200.4), 200 * q, "200.4 steps rounds down to 200")
near3(heightAt(200.6), 201 * q, "200.6 steps rounds up to 201, not down to 200")
near3(heightAt(200.5001), 201 * q, "just over half rounds up")
""")

case("a_rescale_keeps_the_lane")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sow", 22.5, 0) })
local P = Seals.parts
local function rects()
    local out = {}
    for _, nm in ipairs({ "jBarGlow", "jBarCore", "jChip" }) do
        local l, t, w, h = imgRect(P[nm]); out[nm] = { l, t, w, h }
    end
    return out
end
local before = rects()
SetScreen(1080); fire("UI_SCALE_CHANGED")
local after = rects()
for nm, r in pairs(before) do for i = 1, 4 do near3(after[nm][i], r[i], nm .. " rect " .. i .. " after a rescale") end end
laneIs(P, 22.5, "sow", "after a rescale")
SetScreen(2160); fire("UI_SCALE_CHANGED"); laneIs(P, 22.5, "sow", "after a second rescale")
tick(2.5); laneIs(P, 20, "sow", "and it keeps moving")
""")

case("the_lane_bar_draws_above_the_guide_and_the_chip_above_the_chamber")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P, ch = Seals.parts, Seals.frame
local rank = { BACKGROUND = 0, BORDER = 1, ARTWORK = 2, OVERLAY = 3, HIGHLIGHT = 4 }
local function order(t) return rank[t.layer] * 100 + (t.sublevel or 0) end
for i, d in ipairs(P.jGuide) do
    check(order(P.jBarGlow) > order(d) and order(P.jBarCore) > order(P.jBarGlow), "the bar (glow, then core) draws over the guide dash " .. i)
end
check(P.jChip.parent == ch and P.jChip.level > ch.level, "the chip is a frame above the chamber's own textures")
check(P.jChip.mouse == false, "the chip takes no mouse")
check(next(P.jChip.scripts) == nil, "the chip has no scripts")
check(P.jPop.layer == "OVERLAY" and P.jPop.parent == P.jChip, "the flash sits on the chip")
""")

case("the_seal_look_repainting_keeps_the_lane_bar_and_time")(r"""
NOW = 5000
local Seals = boot({ state = judgedState("sotc", 30) })
local P = Seals.parts
for _, key in ipairs(ORDER) do
    push(judgedState("sotc", 30, 10, key)); laneIs(P, 30, key, "seal " .. key)
end
push(noneState(true)); push(judgedState("sotc", 30)); laneIs(P, 30, "sotc", "back from NO SEAL")
-- a repaint that does not change the colour (the combat flag under NO SEAL, the reduced motion flag) leaves the lane's label empty
local function noSealJudged(inCombat) local s2 = judgedState("sotc", 30); s2.seal = false; s2.inCombat = inCombat; return s2 end
push(noSealJudged(false)); laneIs(P, 30, "red", "NO SEAL out of combat")
push(noSealJudged(true)); laneIs(P, 30, "red", "NO SEAL in combat (a repaint, same colour)")
push(noSealJudged(false)); laneIs(P, 30, "red", "and out again")
ForeverSynthwaveDB.reducedMotion = true; push(noSealJudged(false)); laneIs(P, 30, "red", "reduced motion flag flipped (a repaint, same colour)")
ForeverSynthwaveDB.reducedMotion = nil; push(judgedState("sotc", 30)); laneIs(P, 30, "sotc", "back to the Crusader seal")
ForeverSynthwaveDB.reducedMotion = true; push(judgedState("sotc", 30)); laneIs(P, 30, "sotc", "a seal repainted by the reduced motion flag keeps the empty label away")
ForeverSynthwaveDB.reducedMotion = nil; push(judgedState("sotc", 30))
-- the seal running out flips the chamber by itself; the lane keeps its bar and time and follows the chamber's colour
local st = judgedState("sotc", 30); st.seal.expiresAt = NOW + 2; push(st)
tick(2.5); check(Seals.Mode() == "none", "the seal ran out")
laneIs(P, 27.5, "red", "and the debuff lane carries on in red")
""")



HOT = ("Fract", "NeonAt", "Pulse", "CountText", "TextAlpha", "ApplyNeon", "SetBand", "SetExpiring", "ApplyNoSeal",
       "ApplyFill", "ApplyRing", "ApplyCount", "LiveSeal", "LiveNone", "Live", "Animating", "Tick",
       "Coverage", "Tint", "PaintFill", "LiveJudged", "ApplyLaneBar")


def hot_path_check(code: str) -> str | None:
    """Everything the ticker runs each frame: no table, closure, concatenation, formatted string or object creation."""
    banned = [r"\{", r"function\s*\(", r"\.\.", r"string\.format", r"\bformat\(", r"CreateColor", r"CreateFrame", r"CreateTexture",
              r"CreateFontString", r"\bselect\(", r"\bunpack\(", r"\bpcall\(", r"tostring\(", r"setmetatable"]
    for fn in HOT:
        m = re.search(r"(?ms)^local function %s\(.*?^end$" % fn, code)
        if not m:
            return f"{fn} is missing from GunsightSeals.lua"
        for pat in banned:
            hit = re.search(pat, m.group(0))
            if hit and not (fn == "Tick" and pat == r"\bpcall\("):
                return f"{fn} (run every frame) allocates or builds: {hit.group(0)!r}"
    return None


def ticker_check(code: str) -> str | None:
    """One OnUpdate script on the chamber, set only while something animates and cleared with nil, plus the one event frame's OnEvent
    (the target change and the target's health); nothing else is scripted."""
    calls = re.findall(r"SetScript\(([^)]*)\)", code)
    if sorted(c.replace(" ", "") for c in calls) != sorted(['"OnUpdate",Tick', '"OnUpdate",nil', '"OnEvent",OnTargetEvent']):
        return ("GunsightSeals.lua must call SetScript exactly three times, to install Tick, to clear it and for the event frame: "
                + repr(calls))
    return None


def secret_guard_order(code: str) -> str | None:
    """The mock cannot trap a compare, an index or arithmetic on a secret STRING (a plain string in the mock), so this reads the
    source: in each function below, nothing may mention the value before its FS.IsSecret guard except the line that declares it."""
    wanted = [("SealIdOf", "key"), ("CombatOf", "flag"), ("Resolve", "state"), ("Resolve", "seal"), ("Plain", "v"),
              ("JudgedOf", "state"), ("JudgedOf", "jd"), ("KeyHasDebuff", "key"), ("ReadJudgement", "j"), ("TargetDead", "v"), ("ReadTarget", "guid")]
    for fn, var in wanted:
        m = re.search(r"(?ms)^local function %s\(.*?^end$" % fn, code)
        if not m:
            return f"{fn} is missing from GunsightSeals.lua"
        body = m.group(0)
        g = body.find(f"IsSecret({var})")
        if g < 0:
            return f"{fn} never passes {var} through FS.IsSecret"
        before = body[:g]
        for line in before.splitlines():
            if re.search(r"\b%s\b" % var, line) and not re.search(r"(local\s+[\w,\s]*\b%s\b[\w,\s]*=|^local function)" % var, line):
                return f"{fn} touches {var} before its FS.IsSecret guard: {line.strip()}"
    return None

def judge_texture_guard(code: str) -> str | None:
    """The spell texture answer is checked for a secret before any type test or comparison (the mock cannot trap it)."""
    m = re.search(r"(?ms)^local function ReadTexture\(.*?^end$", code)
    if not m:
        return "ReadTexture is missing from GunsightSeals.lua"
    body = m.group(0)
    g = body.find("IsSecret(tex)")
    first = min((i for i in (body.find("type(tex)"), body.find("tex =="), body.find("tex >"), body.find("tex ~=")) if i >= 0), default=-1)
    if g < 0 or first < 0 or g > first:
        return "ReadTexture must pass the texture answer through FS.IsSecret before it types or compares it"
    return None


def judged_times_plain(code: str) -> str | None:
    """The debuff's expiresAt and appliedAt reach arithmetic only through Plain (the FS.IsSecret guard first), and nothing in the
    lane code does arithmetic on the raw fields of state.judged."""
    m = re.search(r"(?ms)^local function JudgedOf\(.*?^end$", code)
    if not m:
        return "JudgedOf is missing from GunsightSeals.lua"
    body = m.group(0)
    if "Plain(jd.expiresAt)" not in body or "Plain(jd.appliedAt)" not in body:
        return "JudgedOf must read expiresAt and appliedAt through Plain"
    raw = re.findall(r"jd\.(expiresAt|appliedAt)", body)
    plain = re.findall(r"Plain\(jd\.(?:expiresAt|appliedAt)\)", body)
    if len(raw) != len(plain):
        return "JudgedOf reads a debuff time without Plain"
    for fn in ("LaneLook", "ApplyLaneBar", "LiveJudged", "ExpireJudged"):
        f = re.search(r"(?ms)^local function %s\(.*?^end$" % fn, code)
        if not f:
            return f"{fn} is missing from GunsightSeals.lua"
        if re.search(r"state\.judged|\.expiresAt|\.appliedAt", f.group(0)):
            return f"{fn} reads a raw debuff field"
    return None


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        s = toc.index("GunsightSeals.lua")
        d = toc.index("GunsightDots.lua")
        g = toc.index("Gunsight.lua")
        hp = toc.index("HudProfiles.lua")
        th = toc.index("Theme.lua")
        out.append(("toc_order", None if s > d > g else
                    f"GunsightSeals.lua must load after GunsightDots.lua and Gunsight.lua (positions {s}, {d}, {g})"))
        out.append(("toc_after_hud_profiles_and_theme", None if s > hp and s > th else
                    "GunsightSeals.lua must load after HudProfiles.lua and Theme.lua"))
        out.append(("toc_lists_the_file_once", None if toc.count("GunsightSeals.lua") == 1 else
                    "GunsightSeals.lua must appear in the .toc exactly once"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "ForeverSynthwave.toc must stay CRLF"))
    if SEALS.exists():
        text = SEALS.read_text(encoding="utf-8")
        code = "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())
        banned = [w for w in ("CreateAnimationGroup", "UnitAura", "UnitBuff", "UnitDebuff",
                              "C_UnitAuras", "GetAuraDataByIndex", "GetPlayerAuraBySpellID", "SetRotation", "CreateLine")
                  if w in code]
        out.append(("source_has_no_animation_group_and_no_aura_read", None if not banned else
                    "GunsightSeals.lua code mentions " + ", ".join(banned)))
        out.append(("exactly_one_ticker_installed_and_cleared", ticker_check(code)))
        out.append(("the_per_frame_path_allocates_nothing", hot_path_check(code)))
        i_flag, i_cmp = code.find("IsSecret(flag)"), code.find("flag == true")
        out.append(("source_guards_the_combat_flag_before_comparing", None if 0 <= i_flag < i_cmp else
                    "GunsightSeals.lua must pass the combat flag through FS.IsSecret before it compares it"))
        dots_src = (ADDON / "GunsightDots.lua").read_text(encoding="utf-8")
        mine = re.search(r"(?m)^local LINE = G\.LINE or ([\d.]+)", text)
        theirs = re.search(r"(?m)^local LINE = G\.LINE or ([\d.]+)", dots_src)
        why = text[text.find("-- Hairline weight"):text.find("local LINE")] if "local LINE" in text else ""
        out.append(("line_weight_matches_the_dot_scale_and_the_comment_gives_the_reason",
                    None if (mine and theirs and mine.group(1) == theirs.group(1) == "1.3"
                             and abs(mockup_seals()["S"]["MOCK_LW"] - 1.857) < 1e-3
                             and "1.857" in why and "baked" in why and "UNVERIFIED" in why) else
                    "GunsightSeals.lua LINE must be the DoT scale's (1.3 image px) with the reason (the mockup's 1.857) in a comment"))
        i_guard, i_use = code.find("IsSecret(key)"), code.find("return KEY_ID[key]")
        out.append(("source_guards_the_key_before_indexing", None if 0 <= i_guard < i_use else
                    "GunsightSeals.lua must pass the seal key through FS.IsSecret before it indexes KEY_ID with it"))
        out.append(("secret_guards_come_before_the_first_use_of_each_value", secret_guard_order(code)))
        dots = (ADDON / "GunsightDots.lua").read_text(encoding="utf-8")
        out.append(("header_seat_is_the_dot_scales", None if '"BOTTOMLEFT", DOT_AX, D.HDR_Y + 2.5)' in dots
                    and 'C.HDR_Y + 2.5)' in text else
                    "the header seat (BOTTOMLEFT, 2.5 below the baseline) must match GunsightDots.lua's"))
        out.append(("source_guards_the_texture_answer_before_comparing_it", judge_texture_guard(code)))
        out.append(("source_reads_the_judgement_times_only_through_plain", judged_times_plain(code)))
        out.append(("source_has_no_em_dash", None if "—" not in text else "GunsightSeals.lua contains an em dash"))
        out.append(("source_builds_nothing_at_file_scope", None if re.search(r"^Gunsight\.OnReady\(Build\)\s*$", text, re.M)
                    and not re.search(r"^\s*CreateFrame\(", text, re.M) else
                    "GunsightSeals.lua must build only inside Gunsight.OnReady (no file-scope CreateFrame)"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(DOTS_H.MOCK)
    lua.globals().LAYOUT_SRC = DOTS_H.LAYOUT.read_text(encoding="utf-8")
    lua.globals().GUNSIGHT_SRC = DOTS_H.GUNSIGHT.read_text(encoding="utf-8")
    lua.globals().PROFILES_SRC = DOTS_H.PROFILES.read_text(encoding="utf-8")
    lua.globals().DOTS_SRC = (ADDON / "GunsightDots.lua").read_text(encoding="utf-8")
    lua.globals().HUDSPELLS_SRC = (ADDON / "HudSpells.lua").read_text(encoding="utf-8")
    lua.globals().SEALS_SRC = SEALS.read_text(encoding="utf-8")
    lua.globals().HAS_TARGET_SRC = DOTS_H._load_gunsight_harness().theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_seals()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not SEALS.exists():
        for name, _ in CASES:
            report(name, f"{SEALS.name} is missing")
        for name, err in static_checks():
            report(name, err)
        print(f"\n{failures} failed")
        return 1

    for name, body in CASES:
        try:
            err = run_case(name, body, mu)
        except LuaError as e:  # a harness bug, not a pass
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)

    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
