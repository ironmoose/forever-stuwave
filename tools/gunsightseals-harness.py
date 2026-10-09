#!/usr/bin/env python3
"""Runs the real GunsightSeals.lua (the Paladin's Seal module of the Gunsight HUD) headless against a mock WoW API.

GunsightSeals.lua is sealModule in mockups/gunsight-modules-concepts-v7-2026-10-08.html: a compact class module that fits ONE
half height area (upper or lower). It registers itself with GunsightAreas as the "class" module for PALADIN and draws from the
rect the area hands it. GunsightAreas is a FAKE here (the registry API only: RegisterModule, then build, seat, onShow, onHide);
Gunsight, Layout and Theme are small stand-ins, so this file does not depend on the files other lanes own. The checks pin:

  * constants: every number the file draws with is parsed back out of sealModule (the tile, the name and caption, the time, the
    drain bar with its RESEAL band, ticks and numbers, the Judgement row), plus the seal table (name, colour, Judgement
    debuff length) from the v2 mockup, the area rects from the v7 mockup and the font metrics, so a mockup edit fails here;
  * the registration: one "class" module for PALADIN only, nothing built at load, and no piece of its own (the area owns the gate);
  * the build and seat: a child of the host, every part at its mockup coordinates in the upper rect and in the lower rect, the
    same parts moving with the rect when the area changes, and the same image px at another screen scale;
  * the look follows FS.Hud's state.seal: each of the seven seals in its colour; false is NO SEAL; nil, a secret, garbage
    and an unmapped key are UNKNOWN; a repaint is written only when the look changes;
  * the drain bar fills remaining / 30 s from the left, the RESEAL band is exactly the 0 to 3 s end, and under 3 s the reseal
    warning goes amber and the band breathes (steady under reduced motion);
  * the Judgement row follows the target's debuff on a 0 to 40 s bar with its time, and empties on none, unknown, a retarget
    and a dead target;
  * the area gate: the module follows the Hud only while its area shows it (onShow subscribes, onHide unsubscribes, a stale
    push is inert);
  * ONE cheap OnUpdate that exists only while something animates, writes only the bar widths on a steady tick and allocates
    nothing (a runtime count and a static scan of the per frame functions); secret values are never compared.

The mock is strict (a widget method it does not define fails as a nil call). The mock client and its helpers are
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
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
SEALS = Path(os.environ.get("GUNSIGHTSEALS_LUA") or ADDON / "Modules/CombatHud/GunsightSeals.lua")
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = ROOT / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"
MOCKUP_V2 = ROOT / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import spelltip_support as tips  # noqa: E402

DOTS_H = _load("gunsightdots_harness", "gunsightdots-harness.py")
lua_value = DOTS_H.lua_value


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def font_metrics() -> dict:
    """What the text seating depends on, read out of the font file the addon wears (Mononoki Bold): how far the middle of a line
    box sits above its baseline when the engine builds the box from the hhea ascender and descender. Not measured in game."""
    d = (ADDON / "Media" / "Fonts" / "MononokiNerdFontMono-Bold.ttf").read_bytes()
    tables = {}
    for i in range(struct.unpack(">H", d[4:6])[0]):
        tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i:28 + 16 * i])
        tables[tag.decode()] = off
    upm = struct.unpack(">H", d[tables["head"] + 18:tables["head"] + 20])[0]
    asc, desc = struct.unpack(">hh", d[tables["hhea"] + 4:tables["hhea"] + 8])
    return dict(CAP=(asc + desc) / 2 / upm)


def gunsight_geometry() -> dict:
    """The canvas centre and the design px per image px that Gunsight.ui and Gunsight.Point use."""
    src = GUNSIGHT.read_text(encoding="utf-8")
    grid = float(_m(r"(?m)^local GRID = ([\d.]+)\s", src, "GRID").group(1))
    cx, cy = (int(v) for v in _m(r"(?m)^local W, H, CX, CY = \d+, \d+, (\d+), (\d+)", src, "CX / CY").groups())
    return dict(GRID=grid, CX=cx, CY=cy)


def mockup_module() -> dict:
    """Everything sealModule draws, the area rects it sits in, the colour tokens and the seal table."""
    src = MOCKUP.read_text(encoding="utf-8")
    body = _m(r"(?s)function sealModule\(y0\)\{(.*?)\n\}\n", src, "the sealModule body").group(1)

    def g(pattern: str, what: str) -> tuple:
        return _m(pattern, body, what).groups()

    def f(v: str) -> float:
        return float(v)

    x, w, jud = g(r"var o='',x=(\d+),w=(\d+),col=C\.gold,seal=\d+,jud=(\d+),i;", "the module x, w and the sample")
    tile_y, tile, tile_h, tile_cut = g(r"ch\(x,y0\+(\d+),(\d+),(\d+),(\d+)\)", "the seal tile")
    tile_mix = g(r"fill=\"'\+mix\(C\.bg,col,(\.\d+)\)\+'\"", "the tile fill")[0]
    tile_edge_w = g(r"stroke=\"'\+col\+'\" stroke-width=\"([\d.]+)\" filter=\"url\(#gls\)\"", "the tile edge")[0]
    ab_x, ab_y, ab_size = g(r"txt\(x\+(\d+),y0\+(\d+),'SV',(\d+),C\.white,\{a:'middle'\}\)", "the tile letters")
    name_x, name_y, name_size = g(r"txt\(x\+(\d+),y0\+(\d+),'VENGEANCE',(\d+),C\.white\)", "the seal name")
    cap_y, cap_size = g(r"txt\(x\+\d+,y0\+(\d+),'SEAL ACTIVE',(\d+),C\.muted\)", "the caption")
    time_y, time_size = g(r"txt\(x\+w,y0\+(\d+),seal\+'s',(\d+),col,\{a:'end'\}\)", "the time")
    by, bh, max_s = g(r"var by=y0\+(\d+),bh=(\d+),bw=w\*\((\d+)/\d+\),bx=x;", "the drain bar")
    track_c, track_a = g(r"rect\(bx,by,bw,bh,'(#[0-9a-f]{6})',(\.\d+)\)", "the track")
    band_s, band_of, band_a = g(r"rect\(bx,by,bw\*(\d+)/(\d+),bh,C\.amber,(\.\d+)\)", "the RESEAL band")
    fill_a = g(r"rect\(bx,by,bw\*seal/\d+,bh,col,(\.\d+)\)", "the fill")[0]
    tip_w, tip_pad, tip_w2, tip_h, tip_a = g(
        r"rect\(bx\+bw\*seal/\d+-(\d+),by-(\d+),(\d+),bh\+(\d+),'#ffffff',(\.\d+)\)", "the tip")
    out_a = g(r"fill=\"none\" stroke=\"'\+col\+'\" stroke-opacity=\"(\.\d+)\"/>", "the outline")[0]
    cut_pad, cut_pad2, cut_a, dash_on, dash_off = g(
        r"line\(bx\+bw\*3/30,by-(\d+),bx\+bw\*3/30,by\+bh\+(\d+),C\.amber,(\.\d+),1,'(\d+) (\d+)'\)", "the cut line")
    ticks, tick_long, tick_short, tick_a = g(
        r"for\(i=0;i<=(\d+);i\+\+\)\{var tx=bx\+bw\*i/\d+;o\+=line\(tx,by\+bh,tx,by\+bh\+\(i%2===0\?(\d+):(\d+)\),C\.violet,(\.\d+),1\);\}",
        "the ticks")
    labels, label_of, label_y, label_size, label_end, label_a = g(
        r"\[([\d,]+)\]\.forEach\(function\(v\)\{o\+=txt\(bx\+bw\*v/(\d+),by\+bh\+(\d+),String\(v\),(\d+),C\.fg,"
        r"\{a:v===0\?'start':v===(\d+)\?'end':'middle',op:(\.\d+)\}\)", "the numbers")
    reseal_dx, reseal_y, reseal_size, reseal_a = g(
        r"txt\(bx\+bw\*3/30\+(\d+),by\+bh\+(\d+),'RESEAL',(\d+),C\.amber,\{a:'middle',op:(\.\d+)\}\)", "RESEAL")
    j_y = g(r"var jy=y0\+(\d+);", "the Judgement row")[0]
    j_size, j_size2, j_cut = g(r"ch\(x,jy,(\d+),(\d+),(\d+)\)", "the J chip")
    j_plate, j_mix = g(r"mix\(C\.bg,'(#[0-9a-f]{6})',(\.\d+)\)", "the chip fill")
    j_edge_w, j_letter_x, j_letter_y, j_letter_size = g(
        r"stroke=\"'\+col\+'\" stroke-width=\"([\d.]+)\"/><text x=\"'\+\(x\+(\d+)\)\+'\" y=\"'\+\(jy\+(\d+)\)\+'\" font-size=\"(\d+)\"",
        "the J letter")
    jbar_x, jbar_dy, jbar_shrink, jbar_h, jbar_a, jmax = g(
        r"rect\(x\+(\d+),jy\+(\d+),w-(\d+),(\d+),col,(\.\d+)\)\+rect\(x\+\d+,jy\+\d+,\(w-\d+\)\*jud/(\d+),\d+,col\)",
        "the Judgement bar")
    jtime_y, jtime_size = g(r"txt\(x\+w,jy\+(\d+),jud\+'s',(\d+),C\.white,\{a:'end'\}\)", "the Judgement time")
    if (tile, tile_h) != (tile, tile) or j_size != j_size2 or tip_w != tip_w2 or cut_pad != cut_pad2 or band_of != max_s \
            or label_of != max_s:
        sys.exit("mockup: sealModule's repeated numbers disagree")

    area_x, area_w = (int(v) for v in _m(r"<rect x=\"(\d+)\" y=\"'\+y\+'\" width=\"(\d+)\" height=\"'\+h\+'\"", src, "the area rect").groups())
    upper = int(_m(r"S\.upper==='seals'\)o\+=sealModule\((\d+)\)", src, "the upper area y").group(1))
    lower = int(_m(r"S\.lower==='seals'\)o\+=sealModule\((\d+)\)", src, "the lower area y").group(1))
    area_h = int(_m(r"emptySlot\(%d,(\d+)," % upper, src, "the area height").group(1))

    css = {n: v.lower() for n, v in re.findall(
        r"--(bg|fg|muted|violet|amber|white):(#[0-9a-fA-F]{6})\s*;", src)}
    for need in ("bg", "fg", "muted", "violet", "amber", "white"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")
    v2 = MOCKUP_V2.read_text(encoding="utf-8")
    for n, v in re.findall(r"--(red|steel):(#[0-9a-fA-F]{6})\s*;", v2):
        css[n] = v.lower()
    for need in ("red", "steel"):
        if need not in css:
            sys.exit(f"mockup v2: colour token --{need} missing")
    block = _m(r"(?s)var SEALS=\{(.*?)\n\};", v2, "the SEALS table").group(1)
    seals = {sid: dict(n=n, c=c.lower(), deb=int(deb)) for sid, n, c, deb in re.findall(
        r"(\w+):\{n:'(\w+)',c:'(#[0-9a-fA-F]{6})',deb:(\d+)\}", block)}
    if len(seals) != 7:
        sys.exit(f"mockup: expected seven seals, found {len(seals)}")

    S = dict(
        X=int(x), W=int(w), JUD=int(jud),
        TILE=int(tile), TILE_Y=int(tile_y), TILE_CUT=int(tile_cut), TILE_MIX=f(tile_mix), TILE_EDGE_W=f(tile_edge_w),
        AB_X=int(ab_x), AB_Y=int(ab_y), AB_SIZE=int(ab_size),
        NAME_X=int(name_x), NAME_Y=int(name_y), NAME_SIZE=int(name_size), CAP_Y=int(cap_y), CAP_SIZE=int(cap_size),
        TIME_Y=int(time_y), TIME_SIZE=int(time_size),
        BAR_Y=int(by), BAR_H=int(bh), MAX_S=int(max_s), TRACK=track_c, TRACK_A=f(track_a), BAND_S=int(band_s), BAND_A=f(band_a),
        FILL_A=f(fill_a), TIP_W=int(tip_w), TIP_PAD=int(tip_pad), TIP_H=int(bh) + int(tip_h), TIP_A=f(tip_a), OUT_A=f(out_a),
        CUT_PAD=int(cut_pad), CUT_A=f(cut_a), CUT_DASH=[int(dash_on), int(dash_off)],
        TICKS=int(ticks), TICK_LONG=int(tick_long), TICK_SHORT=int(tick_short), TICK_A=f(tick_a),
        LABELS=[int(v) for v in labels.split(",")], LABEL_Y=int(label_y), LABEL_SIZE=int(label_size), LABEL_A=f(label_a),
        RESEAL_DX=int(reseal_dx), RESEAL_Y=int(reseal_y), RESEAL_SIZE=int(reseal_size), RESEAL_A=f(reseal_a),
        J_Y=int(j_y), J_SIZE=int(j_size), J_CUT=int(j_cut), J_PLATE=j_plate, J_MIX=f(j_mix), J_EDGE_W=f(j_edge_w),
        J_LETTER_X=int(j_letter_x), J_LETTER_Y=int(j_letter_y), J_LETTER_SIZE=int(j_letter_size),
        JBAR_X=int(jbar_x), JBAR_DY=int(jbar_dy), JBAR_SHRINK=int(jbar_shrink), JBAR_H=int(jbar_h), JBAR_TRACK_A=f(jbar_a),
        JMAX_S=int(jmax), JTIME_Y=int(jtime_y), JTIME_SIZE=int(jtime_size),
    )
    if S["TIP_H"] != S["BAR_H"] + 2 * S["TIP_PAD"]:
        sys.exit("mockup: the tip is no longer bh + 2 * its pad tall")
    areas = dict(x=area_x, w=area_w, h=area_h, upper=upper, lower=lower)
    return dict(S=S, AREAS=areas, CSS=css, SEALS=seals, FONT=font_metrics(), GEO=gunsight_geometry())


# ---------------------------------------------------------------------------------------
# Lua prelude: the dots harness's mock client, a fake GunsightAreas, and the Seal module helpers
# ---------------------------------------------------------------------------------------

PRELUDE = DOTS_H.MOCK + r"""
local S, GEO, AREAS, FONT = MU.S, MU.GEO, MU.AREAS, MU.FONT
local SK = GEO.GRID                                -- design px per image px
SCALE = 1
local LINE = 1.3

local function rgb(hex) return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 } end
local function mixC(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end
local WHITE = { 1, 1, 1 }
local CSS = {}
for k, v in pairs(MU.CSS) do CSS[k] = rgb(v) end
local KEY_ID = { sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command", sol = "light", sow = "wisdom", soj = "justice" }
local ORDER = { "sor", "sotc", "sofu", "soc", "sol", "sow", "soj" }
local ABBR = { righteousness = "RI", crusader = "CR", fury = "FU", command = "CO", light = "LI", wisdom = "WI", justice = "JU" }
local function sealColor(id) return rgb(MU.SEALS[id].c) end

-- A strict secret: every operation but type() throws, and FS.IsSecret recognises it.
SECRET = setmetatable({}, {
    __index = function() error("indexed a secret", 2) end, __newindex = function() error("wrote a secret", 2) end,
    __len = function() error("length of a secret", 2) end, __call = function() error("called a secret", 2) end,
    __lt = function() error("compared a secret", 2) end, __le = function() error("compared a secret", 2) end,
    __concat = function() error("concatenated a secret", 2) end, __unm = function() error("negated a secret", 2) end,
})
SECRET_FN = function(v) return rawequal(v, SECRET) end

function stubTheme2_()
    local Theme = {
        FONT_MONO = "mono.ttf",
        SLICE_CUT2_FILL_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_fill.tga",
        SLICE_GLOW_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_glow.tga",
        SLICE_GLOW_PAD = 4, SLICE_GLOW_MARGIN = 10, SLICE_CUT_MARGIN = 6,
        SLICE_CUT2_OUTLINE_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_outline.tga",
    }
    FS.Theme = Theme
    function Theme.ApplyMono(fs, size, color) fs.monoSize = size; fs.monoColor = color; fs.hasFont = true end  -- the real one calls SetFont
    function Theme.ApplyNineSlice(tex, margin) tex.margin = margin; return true end
    -- the real Theme.AddSliceTexture: two anchors, inset, a nine slice margin
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
end

-- A stand-in for FS.Hud: the ledger-backed state is pushed by the test.
function stubHud_()
    FS.Hud = {
        GetProfile = function() return PROFILE end,
        GetState = function() return STATE end,
        Subscribe = function(fn)
            SUBS[#SUBS + 1] = fn
            if STATE then fn(STATE) end
            return fn
        end,
        Unsubscribe = function(fn)
            for i = #SUBS, 1, -1 do if SUBS[i] == fn then table.remove(SUBS, i) end end
        end,
    }
end
function push(state)
    STATE = state
    for _, fn in ipairs({ unpack(SUBS) }) do fn(state) end
end

-- Gunsight.ui and Gunsight.Point as Gunsight.lua defines them (the canvas centre and the design px per image px come from it)
local function stubGunsight_()
    local root = CreateFrame("Frame", "ForeverSTUwaveGunsight", UIParent)
    root:SetSize(1, 1)
    root:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    function root:GetEffectiveScale() return 1 end
    local Gs = { G = { GRID = GEO.GRID, CX = GEO.CX, CY = GEO.CY }, root = root, IsActive = function() return true end }
    function Gs.ui(px) return px * GEO.GRID * FS.Layout.Scale() end
    function Gs.Point(frame, point, x, y)
        local k = GEO.GRID * FS.Layout.Scale()
        frame:ClearAllPoints()
        frame:SetPoint(point, root, "CENTER", (x - GEO.CX) * k, -(y - GEO.CY) * k)
    end
    FS.Gunsight = Gs
end

RECTS = {
    upper = { x = AREAS.x, y = AREAS.upper, w = AREAS.w, h = AREAS.h },
    lower = { x = AREAS.x, y = AREAS.lower, w = AREAS.w, h = AREAS.h },
}
ForeverSTUwaveDB = {}
JUDGE_ANSWER, DEAD, REGS, HOST, CUR = { remaining = 0 }, false, {}, nil, "upper"

-- opts: db, noAreas, noHud, noTheme, height
local function boot(opts)
    opts = opts or {}
    resetWorld()
    for i = #REGS, 1, -1 do REGS[i] = nil end
    IN_COMBAT, AFFECTING, DEAD, SCALE, HOST, CUR = false, nil, false, 1, nil, "upper"
    JUDGE_ANSWER = { remaining = 0 }
    SECRET_FN = function(v) return rawequal(v, SECRET) end
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db or ForeverSTUwaveDB
    FS.IsSecret = function(v) return SECRET_FN(v) end
    FS.Layout = { Scale = function() return SCALE end }
    UnitGUID = function() return "Creature-0-0-0-0-1-0000000001" end
    UnitIsDead = function() return DEAD end
    FS.HudSpells = { jd = { names = { "Judgement" }, ids = { 20271 } }, sor = { names = { "Seal of Righteousness" } } }
    stubGunsight_()
    loadSpellTips(HELPERS_SRC)
    if not opts.noTheme then stubTheme2_() end
    if not opts.noHud then
        stubHud_()
        FS.Hud.GetJudgement = function() return JUDGE_ANSWER end
    end
    if not opts.noAreas then
        FS.GunsightAreas = { RegisterModule = function(id, spec) REGS[#REGS + 1] = { id = id, spec = spec } end }
    end
    assert(loadstring(SEALS_SRC, "@GunsightSeals.lua"))("forever-stuwave", FS)
    return FS.GunsightSeals
end

-- What GunsightAreas does with a registered module: build into a host frame, seat in the area's rect, show.
local function mount(area, opts)
    opts = opts or {}
    if #REGS == 0 then local keep = STATE; boot(); STATE = keep end
    check(#REGS == 1, "expected one registered module, got " .. #REGS)
    local spec = REGS[1].spec
    HOST = CreateFrame("Frame", "FakeAreaHost", FS.Gunsight.root)
    local frame = spec.build(HOST)
    check(frame, "build returned no frame")
    CUR = area
    spec.seat(RECTS[area])
    if not opts.hidden then spec.onShow(area) end
    return FS.GunsightSeals, frame, spec
end
local function seatIn(area) CUR = area; REGS[1].spec.seat(RECTS[area]) end
local function org() local r = RECTS[CUR]; return r.x + (r.w - S.W) / 2, r.y end

local function near3(a, b, what) near(a, b, what, 1e-3) end
local function colorIs(c, want, what)
    for i = 1, 3 do near3(c[i], want[i], what .. " channel " .. i) end
end
local function colA(c, want, a, what)
    colorIs(c, want, what .. " colour")
    near3(c[4], a, what .. " alpha")
end
local function tint(t) return t.color or t.vertex end
-- a region's rect against module coordinates (x, y, w, h image px from the module origin)
local function rectIs(t, x, y, w, h, what)
    local ox, oy = org()
    local l, tp, rw, rh = imgRect(t)
    near3(l, ox + x, what .. " x"); near3(tp, oy + y, what .. " y"); near3(rw, w, what .. " width"); near3(rh, h, what .. " height")
end
-- a text part: shown, its text, its font size, its anchor x and its baseline (the line middle sits CAP * size above it)
local function textIs(fs, text, size, x, base, what)
    check(isVisible(fs) and fs.text == text, what .. ": text " .. tostring(fs.text) .. ", want " .. tostring(text))
    near3(fs.monoSize, size * SK * FS.Layout.Scale(), what .. " font")
    local ox, oy = org()
    local cx, cy = imgCenter(fs)
    near3(cx, ox + x, what .. " x"); near3(cy, oy + base - FONT.CAP * size, what .. " baseline")
end

-- Hud states
local function sealAt(key, rem, extra)
    local st = { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {}, inCombat = false,
        seal = { key = key, id = 21084, expiresAt = NOW + rem, duration = 30, castAt = NOW - (30 - rem) } }
    for k, v in pairs(extra or {}) do st[k] = v end
    return st
end
local function noneState(inCombat) return { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {}, seal = false, inCombat = inCombat } end
local function unknownState() return { active = true, class = "PALADIN", row = {}, buffsMissing = {}, procs = {} } end
local DEB = { sotc = 40, sol = 40, sow = 40, soj = 10 }
local function judgedState(key, rem, seal)
    local st = sealAt(seal or key, 1000)
    st.judged = { key = key, appliedAt = NOW - 5, expiresAt = NOW + rem, duration = DEB[key] }
    return st
end

-- the bar's fill against a time left: its rect, colour and the tip on its right edge
local function barIs(P, rem, col, what)
    local w = math.min(rem, S.MAX_S) / S.MAX_S * S.W
    check(isVisible(P.fill) and isVisible(P.tip), what .. ": the fill and tip are shown")
    rectIs(P.fill, 0, S.BAR_Y, w, S.BAR_H, what .. ": fill")
    colA(P.fill.color, col, S.FILL_A, what .. ": fill")
    rectIs(P.tip, w - S.TIP_W, S.BAR_Y - S.TIP_PAD, S.TIP_W, S.TIP_H, what .. ": tip")
end
-- the Judgement row lit for `rem` seconds in colour `col`
local function rowIs(P, rem, col, what)
    local w = math.min(rem, S.JMAX_S) / S.JMAX_S * (S.W - S.JBAR_SHRINK)
    check(isVisible(P.jFill), what .. ": the bar is shown")
    rectIs(P.jFill, S.JBAR_X, S.J_Y + S.JBAR_DY, w, S.JBAR_H, what .. ": bar")
    colorIs(P.jFill.color, col, what .. ": bar")
    colA(P.jTrack.color, col, S.JBAR_TRACK_A, what .. ": track")
    textIs(P.jTime, math.min(math.ceil(rem), S.JMAX_S) .. "s", S.JTIME_SIZE, S.W, S.J_Y + S.JTIME_Y, what .. ": time")
    near3(P.chip.alpha, 1, what .. ": chip alpha")
    colorIs(P.chip.edge.vertex, col, what .. ": chip edge")
    check(P.jEmpty.text == "", what .. ": no empty label")
end
-- the row with nothing on it, wearing `label`
local function rowEmpty(P, label, what)
    check(not isVisible(P.jFill), what .. ": the bar is hidden")
    check(not isVisible(P.jTime), what .. ": the time is hidden")
    near3(P.chip.alpha, 0.45, what .. ": chip dimmed")
    check(P.jEmpty.text == label, what .. ": label '" .. tostring(P.jEmpty.text) .. "', want '" .. label .. "'")
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
local Seals = boot()
local C = Seals.C
check(type(C) == "table", "FS.GunsightSeals.C (the constants table) is missing")
local function eq(a, b, what) near(a, b, what .. " (GunsightSeals has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")", 1e-9) end
eq(C.W, S.W, "module width"); eq(AREAS.x + (AREAS.w - C.W) / 2, S.X, "the module centred across the area starts at the mockup's x")
check(C.H <= AREAS.h, "the module fits one area: " .. C.H .. " of " .. AREAS.h)
eq(C.TILE, S.TILE, "tile"); eq(C.TILE_Y, S.TILE_Y, "tile y"); eq(C.TILE_CUT, S.TILE_CUT, "tile cut"); eq(C.TILE_MIX, S.TILE_MIX, "tile fill mix")
eq(C.TILE_EDGE_W, S.TILE_EDGE_W, "tile edge weight")
eq(C.AB_X, S.AB_X, "tile letters x"); eq(C.AB_Y, S.AB_Y, "tile letters y"); eq(C.AB_SIZE, S.AB_SIZE, "tile letters size")
eq(C.NAME_X, S.NAME_X, "name x"); eq(C.NAME_Y, S.NAME_Y, "name y"); eq(C.NAME_SIZE, S.NAME_SIZE, "name size")
eq(C.CAP_Y, S.CAP_Y, "caption y"); eq(C.CAP_SIZE, S.CAP_SIZE, "caption size")
eq(C.TIME_Y, S.TIME_Y, "time y"); eq(C.TIME_SIZE, S.TIME_SIZE, "time size")
eq(C.BAR_Y, S.BAR_Y, "bar y"); eq(C.BAR_H, S.BAR_H, "bar height"); eq(C.MAX_S, S.MAX_S, "bar seconds")
eq(C.TRACK_A, S.TRACK_A, "track alpha"); check(C.TRACK == S.TRACK, "track colour " .. tostring(C.TRACK))
eq(C.BAND_S, S.BAND_S, "RESEAL band seconds"); eq(C.BAND_A, S.BAND_A, "band alpha"); eq(C.FILL_A, S.FILL_A, "fill alpha")
eq(C.TIP_W, S.TIP_W, "tip width"); eq(C.TIP_PAD, S.TIP_PAD, "tip pad"); eq(C.TIP_A, S.TIP_A, "tip alpha"); eq(C.OUT_A, S.OUT_A, "outline alpha")
eq(C.CUT_PAD, S.CUT_PAD, "cut line pad"); eq(C.CUT_A, S.CUT_A, "cut line alpha"); eq(C.CUT_DASH[1], S.CUT_DASH[1], "dash on"); eq(C.CUT_DASH[2], S.CUT_DASH[2], "dash off")
eq(C.TICKS, S.TICKS, "tick count"); eq(C.TICK_LONG, S.TICK_LONG, "long tick"); eq(C.TICK_SHORT, S.TICK_SHORT, "short tick"); eq(C.TICK_A, S.TICK_A, "tick alpha")
check(#C.LABELS == #S.LABELS, "number labels"); for i = 1, #S.LABELS do eq(C.LABELS[i], S.LABELS[i], "label " .. i) end
eq(C.LABEL_Y, S.LABEL_Y, "number y"); eq(C.LABEL_SIZE, S.LABEL_SIZE, "number size"); eq(C.LABEL_A, S.LABEL_A, "number alpha")
eq(C.RESEAL_DX, S.RESEAL_DX, "RESEAL x"); eq(C.RESEAL_SIZE, S.RESEAL_SIZE, "RESEAL size"); eq(C.RESEAL_A, S.RESEAL_A, "RESEAL alpha")
eq(C.LABEL_Y, S.RESEAL_Y, "RESEAL shares the numbers' baseline")
eq(C.J_Y, S.J_Y, "Judgement row y"); eq(C.J_SIZE, S.J_SIZE, "chip"); eq(C.J_CUT, S.J_CUT, "chip cut"); eq(C.J_MIX, S.J_MIX, "chip fill mix")
colorIs(rgb(C.J_PLATE), rgb(S.J_PLATE), "chip plate colour"); eq(C.J_EDGE_W, S.J_EDGE_W, "chip edge weight")
eq(C.J_SIZE / 2, S.J_LETTER_X, "the J is centred on the chip"); eq(C.J_LETTER_Y, S.J_LETTER_Y, "J y"); eq(C.J_LETTER_SIZE, S.J_LETTER_SIZE, "J size")
eq(C.JBAR_X, S.JBAR_X, "Judgement bar x"); eq(C.JBAR_DY, S.JBAR_DY, "Judgement bar y"); eq(C.JBAR_SHRINK, S.JBAR_SHRINK, "Judgement bar shrink")
eq(C.JBAR_H, S.JBAR_H, "Judgement bar height"); eq(C.JBAR_TRACK_A, S.JBAR_TRACK_A, "Judgement track alpha"); eq(C.JMAX_S, S.JMAX_S, "Judgement seconds")
eq(C.JTIME_Y, S.JTIME_Y, "Judgement time y"); eq(C.JTIME_SIZE, S.JTIME_SIZE, "Judgement time size")
eq(C.CAP, FONT.CAP, "baseline to line middle (the font's hhea)")
for _, name in ipairs({ "bg", "fg", "violet", "amber", "red", "steel", "muted", "white" }) do colorIs(C.COLORS[name], CSS[name], "colour " .. name) end
local n = 0
for id, e in pairs(MU.SEALS) do
    n = n + 1
    local s = C.SEALS[id]
    check(s, "seal " .. id .. " missing")
    check(s.n == e.n, "seal " .. id .. " name " .. tostring(s.n) .. ", mockup " .. e.n)
    colorIs(s.c, rgb(e.c), "seal " .. id .. " colour")
    check(s.deb == e.deb, "seal " .. id .. " Judgement debuff " .. tostring(s.deb) .. ", mockup " .. e.deb)
    check(s.ab == ABBR[id], "seal " .. id .. " tile letters " .. tostring(s.ab))
end
check(n == 7, "seven seals")
""")

case("registers_one_class_module_for_paladin_only")(r"""
boot()
check(#REGS == 1, "exactly one RegisterModule call, got " .. #REGS)
local spec = REGS[1].spec
check(REGS[1].id == "class", "registered as the class module: " .. tostring(REGS[1].id))
check(type(spec.classes) == "table" and #spec.classes == 1 and spec.classes[1] == "PALADIN", "classes is {PALADIN} only")
for _, k in ipairs({ "build", "seat", "onShow", "onHide" }) do check(type(spec[k]) == "function", "spec." .. k .. " is a function") end
check(#FRAMES == 1 and FRAMES[1].name == "ForeverSTUwaveGunsight", "nothing is built at file load (only the Gunsight root exists)")
check(#SUBS == 0, "nothing subscribed at file load")
check(onUpdateFrames() == 0, "no ticker at file load")
""")

case("loads_silently_without_the_areas_registry")(r"""
boot({ noAreas = true })
check(#REGS == 0 and #FRAMES == 1, "nothing registered or built")
FS.GunsightAreas = {}
resetWorld(); FS.Gunsight = nil
local fn = assert(loadstring(SEALS_SRC, "@GunsightSeals.lua"))
fn("forever-stuwave", FS)
check(FS.GunsightSeals == nil, "no Gunsight: the file stands down")
""")

case("has_no_piece_of_its_own")(r"""
-- the dot piece belongs to GunsightAreas now: the module must not register or gate on any piece, and needs no GunsightDots
boot()
local Gs = FS.Gunsight
for _, k in ipairs({ "RegisterPiece", "IsPieceOn", "OnPieceChanged", "SetPiece", "OnReady", "IsEnabled" }) do
    check(Gs[k] == nil, "the stand-in Gunsight offers no " .. k .. ", so any call would have thrown at load or build")
end
check(FS.GunsightDots == nil, "no GunsightDots in this world")
local Seals, frame = mount("upper")
check(Seals.frame == frame and frame:GetParent() == HOST, "the module frame is a child of the host the area gave")
check(frame.name == "ForeverSTUwaveGunsightSeals", "the frame name")
""")

case("seats_in_the_upper_area")(r"""
STATE = sealAt("sor", 15)
local Seals, frame = mount("upper")
local P = Seals.parts
local ox, oy = org()
near3(ox, S.X, "module x is the mockup's"); near3(oy, AREAS.upper, "module y is the area top")
rectIs(frame, 0, 0, S.W, Seals.C.H, "module frame")
rectIs(P.tile, 0, S.TILE_Y, S.TILE, S.TILE, "tile")
rectIs(P.track, 0, S.BAR_Y, S.W, S.BAR_H, "track")
rectIs(P.band, 0, S.BAR_Y, S.W * S.BAND_S / S.MAX_S, S.BAR_H, "band")
rectIs(P.chip, 0, S.J_Y, S.J_SIZE, S.J_SIZE, "chip")
rectIs(P.jTrack, S.JBAR_X, S.J_Y + S.JBAR_DY, S.W - S.JBAR_SHRINK, S.JBAR_H, "Judgement track")
textIs(P.ab, "RI", S.AB_SIZE, S.AB_X, S.AB_Y, "tile letters")
textIs(P.name, "RIGHTEOUSNESS", S.NAME_SIZE, S.NAME_X, S.NAME_Y, "name")
textIs(P.cap, "SEAL ACTIVE", S.CAP_SIZE, S.NAME_X, S.CAP_Y, "caption")
textIs(P.time, "15s", S.TIME_SIZE, S.W, S.TIME_Y, "time")
for i, v in ipairs(S.LABELS) do textIs(P.labels[i], tostring(v), S.LABEL_SIZE, S.W * v / S.MAX_S, S.BAR_Y + S.BAR_H + S.LABEL_Y, "number " .. v) end
textIs(P.reseal, "RESEAL", S.RESEAL_SIZE, S.W * S.BAND_S / S.MAX_S + S.RESEAL_DX, S.BAR_Y + S.BAR_H + S.LABEL_Y, "RESEAL")
textIs(P.jLetter, "J", S.J_LETTER_SIZE, S.J_LETTER_X, S.J_Y + S.J_LETTER_Y, "J")
for i = 0, S.TICKS do
    local len = i % 2 == 0 and S.TICK_LONG or S.TICK_SHORT
    local l, tp, w, h = imgRect(P.ticks[i + 1])
    near3(l + w / 2, ox + S.W * i / S.TICKS, "tick " .. i .. " x"); near3(tp, oy + S.BAR_Y + S.BAR_H, "tick " .. i .. " top"); near3(h, len, "tick " .. i .. " length")
    colA(P.ticks[i + 1].color, CSS.violet, S.TICK_A, "tick " .. i)
end
local top, bot = oy + S.BAR_Y - S.CUT_PAD, oy + S.BAR_Y + S.BAR_H + S.CUT_PAD
local first, last = imgRect(P.cut[1]), { imgRect(P.cut[#P.cut]) }
local _, t1 = imgRect(P.cut[1]); near3(t1, top, "the cut line starts at by - 3")
near3(last[2] + last[4], bot, "the cut line ends at by + bh + 3")
local l, _, w = imgRect(P.cut[1]); near3(l + w / 2, ox + S.W * S.BAND_S / S.MAX_S, "the cut line sits on the 3 s mark")
-- the module stays inside the area rect
local r = RECTS.upper
check(ox >= r.x and ox + S.W <= r.x + r.w and oy + Seals.C.H <= r.y + r.h, "the module lies inside the upper area")
""")

case("seats_in_the_lower_area_and_follows_a_move")(r"""
STATE = sealAt("sow", 12, { judged = { key = "sow", appliedAt = NOW - 5, expiresAt = NOW + 20, duration = 40 } })
local Seals, frame = mount("lower")
local P = Seals.parts
local ox, oy = org()
near3(oy, AREAS.lower, "module y is the lower area top")
rectIs(frame, 0, 0, S.W, Seals.C.H, "module frame (lower)")
rectIs(P.tile, 0, S.TILE_Y, S.TILE, S.TILE, "tile (lower)")
barIs(P, 12, sealColor("wisdom"), "lower")
rowIs(P, 20, sealColor("wisdom"), "lower")
textIs(P.time, "12s", S.TIME_SIZE, S.W, S.TIME_Y, "time (lower)")
local r = RECTS.lower
check(oy + Seals.C.H <= r.y + r.h, "the module lies inside the lower area")
-- the player moves it to the upper area: seat is called again with the other rect and everything follows
seatIn("upper")
near3(select(2, org()), AREAS.upper, "now seated at the upper area top")
rectIs(P.tile, 0, S.TILE_Y, S.TILE, S.TILE, "tile (moved up)")
barIs(P, 12, sealColor("wisdom"), "moved up")
rowIs(P, 20, sealColor("wisdom"), "moved up")
textIs(P.name, "WISDOM", S.NAME_SIZE, S.NAME_X, S.NAME_Y, "name (moved up)")
seatIn("lower")
barIs(P, 12, sealColor("wisdom"), "and back down")
""")

case("a_rescale_keeps_the_image_px")(r"""
STATE = sealAt("sor", 15, { judged = { key = "sotc", appliedAt = NOW - 5, expiresAt = NOW + 10, duration = 40 } })
local Seals = mount("lower")
local P = Seals.parts
SCALE = 1.25
seatIn("lower")
rectIs(P.tile, 0, S.TILE_Y, S.TILE, S.TILE, "tile at scale 1.25")
rectIs(P.track, 0, S.BAR_Y, S.W, S.BAR_H, "track at scale 1.25")
barIs(P, 15, sealColor("righteousness"), "scale 1.25")
textIs(P.time, "15s", S.TIME_SIZE, S.W, S.TIME_Y, "time at scale 1.25")
SCALE = 0.8
seatIn("upper")
barIs(P, 15, sealColor("righteousness"), "scale 0.8, upper")
rectIs(P.chip, 0, S.J_Y, S.J_SIZE, S.J_SIZE, "chip at scale 0.8")
""")

case("seat_before_build_and_a_bad_rect_are_harmless")(r"""
boot()
local spec = REGS[1].spec
spec.seat(RECTS.lower)                                            -- before the frame exists
for _, bad in ipairs({ false, "x", {}, { x = "a", y = 1, w = 2 }, { x = SECRET, y = 1, w = 2 } }) do spec.seat(bad) end
HOST = CreateFrame("Frame", "FakeAreaHost", FS.Gunsight.root)
local frame = spec.build(HOST)
CUR = "lower"
rectIs(frame, 0, 0, S.W, FS.GunsightSeals.C.H, "built after a seat call, at the rect it was given first")
""")

case("each_seal_wears_its_colour_name_and_letters")(r"""
for _, key in ipairs(ORDER) do
    local id = KEY_ID[key]
    local col = sealColor(id)
    boot()
    STATE = sealAt(key, 20)
    local Seals = mount("upper")
    local P = Seals.parts
    check(Seals.Mode() == "seal", key .. ": seal look")
    textIs(P.name, MU.SEALS[id].n, S.NAME_SIZE, S.NAME_X, S.NAME_Y, key .. " name")
    colA(P.name.textColor, CSS.white, 1, key .. " name")
    textIs(P.ab, ABBR[id], S.AB_SIZE, S.AB_X, S.AB_Y, key .. " letters")
    textIs(P.cap, "SEAL ACTIVE", S.CAP_SIZE, S.NAME_X, S.CAP_Y, key .. " caption")
    colA(P.cap.textColor, CSS.muted, 1, key .. " caption")
    colA(P.time.textColor, col, 1, key .. " time")
    colA(P.tile.edge.vertex, col, 1, key .. " tile edge")
    colorIs(P.tile.plate.vertex, mixC(CSS.bg, col, S.TILE_MIX), key .. " tile fill")
    check(P.tile.glow.shown, key .. ": tile glow shown")
    barIs(P, 20, col, key)
    for i, t in ipairs(P.outline) do colA(t.color, col, S.OUT_A, key .. " outline " .. i) end
    colA(P.track.color, rgb(S.TRACK), S.TRACK_A, key .. " track")
    colA(P.band.color, CSS.amber, S.BAND_A, key .. " band")
    -- the Judgement row's empty label: a seal that carries a debuff says NOT JUDGED, one that does not says NO DEBUFF
    rowEmpty(P, MU.SEALS[id].deb > 0 and "NOT JUDGED" or "NO DEBUFF", key .. " empty row")
end
""")

case("drain_bar_fill_for_a_given_remaining_time")(r"""
STATE = sealAt("sotc", 15)
local Seals = mount("upper")
local P = Seals.parts
local col = sealColor("crusader")
barIs(P, 15, col, "15 s"); near3(P.fill.w / (SK * SCALE), S.W * 0.5, "half the bar at 15 s")
for _, rem in ipairs({ 30, 29.5, 22.4, 10, 5.5, 3.2, 1, 0.2 }) do
    push(sealAt("sotc", rem))
    barIs(P, rem, rem <= S.BAND_S and CSS.amber or col, rem .. " s")      -- under 3 s the reseal warning wears amber
end
-- the fill's right edge is the tip's right edge, and it tracks the clock
push(sealAt("sotc", 20)); tick(5)
barIs(P, 15, col, "five seconds on")
-- a duration above 30 (a reconcile can report one) pins at the full bar
push(sealAt("sotc", 45)); barIs(P, 30, col, "pinned at 30 s")
-- under .05 s the fill is hidden; an unreadable time hides it and the time
push(sealAt("sotc", 0.03)); check(not isVisible(P.fill) and not isVisible(P.tip), "no fill under .05 s")
push(sealAt("sotc", 20, { seal = { key = "sotc", id = 1, expiresAt = SECRET, duration = 30 } }))
check(not isVisible(P.fill) and not isVisible(P.tip) and not isVisible(P.time), "a secret expiry draws no bar and no time")
check(Seals.Mode() == "seal", "and keeps the seal look")
push(sealAt("sotc", 20, { seal = { key = "sotc", id = 1, expiresAt = "soon", duration = 30 } }))
check(not isVisible(P.fill) and not isVisible(P.time), "a non number expiry draws no bar and no time")
""")

case("quarter_pixel_snapping_of_the_widths")(r"""
PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1440 end }
STATE = sealAt("sotc", 7.3, { judged = { key = "sotc", appliedAt = NOW - 5, expiresAt = NOW + 13.7, duration = 40 } })
local Seals = mount("upper")
local P = Seals.parts
local q = 0.25 * (768 / 1440) / (SK * SCALE)
local function onGrid(w, step, what) check(math.abs(w / step - math.floor(w / step + 0.5)) < 1e-6, what .. " is on the grid: " .. w) end
local function wImg(t) return t.w / (SK * SCALE) end
local raw = S.W * 7.3 / S.MAX_S
onGrid(wImg(P.fill), q, "fill width"); check(math.abs(wImg(P.fill) - raw) <= q / 2 + 1e-9, "snapped within half a step of " .. raw)
local rawJ = (S.W - S.JBAR_SHRINK) * 13.7 / S.JMAX_S
onGrid(wImg(P.jFill), q, "Judgement width"); check(math.abs(wImg(P.jFill) - rawJ) <= q / 2 + 1e-9, "Judgement snapped within half a step of " .. rawJ)
""")


case("the_tile_wears_the_seal_spell_icon_and_the_letters_are_the_fallback")(r"""
C_Spell = { GetSpellTexture = function(id) return 135000 + id end }
STATE = sealAt("sor", 20)
local Seals = mount("upper")
local P = Seals.parts
local icon = P.tile.icon
check(icon and isVisible(icon), "the tile has a shown icon")
check(icon.path == 135000 + 21084, "the icon is the seal's spell texture: " .. tostring(icon.path))
check(not isVisible(P.ab), "the letters hide behind a readable icon")
check(#icon.points == 2, "the icon fills the cut frame by two anchors")
local inset = 3 * SK * SCALE
near3(icon.points[1][4], inset, "icon inset left"); near3(icon.points[1][5], -inset, "icon inset top")
near3(icon.points[2][4], -inset, "icon inset right"); near3(icon.points[2][5], inset, "icon inset bottom")
check(P.tile.plate and P.tile.edge and isVisible(P.tile.plate) and isVisible(P.tile.edge), "the cut frame stays around it")
-- a new seal reads its own spell id
local st = sealAt("sotc", 20); st.seal.id = 20375; push(st)
check(icon.path == 135000 + 20375 and isVisible(icon), "a new seal reads its own icon: " .. tostring(icon.path))
-- NO SEAL and unknown wear no icon
push(noneState(false)); check(not isVisible(icon), "NO SEAL: no icon"); check(isVisible(P.ab) and P.ab.text == "--", "NO SEAL keeps its dashes")
push(unknownState()); check(not isVisible(icon) and not isVisible(P.ab), "unknown: no icon, no letters")
""")

case("the_seal_tile_and_the_judgement_chip_show_their_spell_on_hover")(r"""
STATE = sealAt("sor", 20)
local Seals = mount("upper")
local P = Seals.parts
for _, f in ipairs({ P.tile, P.chip }) do
    check(hoverOnly(f) and f.mouse == false, "a plate is motion only and never click enabled")
end
hover(P.tile)
check(tip() and tip().spellID == 21084 and GameTooltip.setOwner == 1, "the tile shows the seal's spell once, got " .. tostring(tip() and tip().spellID))
unhover(P.tile)
check(tip() == nil, "leave takes it down")
hover(P.chip)
check(tip() and tip().spellID == 20271, "the chip shows Judgement")
unhover(P.chip)
-- a new seal under the cursor redraws it
hover(P.tile)
local st = sealAt("sotc", 20); st.seal.id = 20375; push(st)
check(tip() and tip().spellID == 20375, "the open tooltip follows the new seal")
-- NO SEAL has no spell to show
push(noneState(false))
check(tip() == nil, "NO SEAL: nothing to show")
""")

case("a_secret_seal_id_falls_back_to_the_seal_name_and_the_gate_holds")(r"""
STATE = sealAt("sor", 20); STATE.seal.id = SECRET
local Seals = mount("upper")
hover(Seals.parts.tile)
check(tip() and tip().spellID == nil and tip().text == "Seal of Righteousness", "a secret id shows the name, got " .. tostring(tip() and tip().text))
unhover(Seals.parts.tile)
FS.Gunsight.IsActive = function() return false end
hover(Seals.parts.chip)
check(tip() == nil, "an inactive Gunsight shows no Judgement tooltip")
""")


case("the_tile_falls_back_to_the_letters_for_every_unreadable_icon")(r"""
local answers = {
    { "nil", function() return nil end }, { "zero", function() return 0 end }, { "empty string", function() return "" end },
    { "negative", function() return -5 end }, { "NaN", function() return 0 / 0 end }, { "throws", function() error("boom") end },
    { "secret", function() return SECRET end },
}
for _, a in ipairs(answers) do
    boot()
    C_Spell = { GetSpellTexture = a[2] }
    GetSpellTexture = nil
    STATE = sealAt("sor", 20)
    local Seals = mount("upper")
    local P = Seals.parts
    check(not isVisible(P.tile.icon), a[1] .. ": no icon")
    check(isVisible(P.ab) and P.ab.text == "RI", a[1] .. ": the letters show: " .. tostring(P.ab.text))
end
-- the legacy global when C_Spell is absent
boot(); C_Spell = nil; GetSpellTexture = function(id) return 777 end
STATE = sealAt("sor", 20)
local Seals = mount("upper")
check(Seals.parts.tile.icon.path == 777 and not isVisible(Seals.parts.ab), "the legacy GetSpellTexture answers")
-- a secret or missing spell id asks for nothing
boot(); GetSpellTexture = nil; local asked = 0
C_Spell = { GetSpellTexture = function(id) if id ~= 20271 then asked = asked + 1 end return 5 end }
STATE = sealAt("sor", 20); STATE.seal.id = SECRET
Seals = mount("upper")
check(asked == 0 and isVisible(Seals.parts.ab), "a secret seal spell id is never passed on: asked " .. asked)
-- an icon that arrives late replaces the letters at the next push
boot(); GetSpellTexture = nil; local ready = false
C_Spell = { GetSpellTexture = function(id) if ready then return 4242 end return nil end }
STATE = sealAt("sor", 20)
Seals = mount("upper")
check(isVisible(Seals.parts.ab) and not isVisible(Seals.parts.tile.icon), "letters while the client has not answered")
ready = true; push(sealAt("sor", 19))
check(Seals.parts.tile.icon.path == 4242 and not isVisible(Seals.parts.ab), "the icon takes over once the client answers")
""")

case("the_judgement_chip_wears_the_judgement_icon_with_the_j_as_fallback")(r"""
C_Spell = { GetSpellTexture = function(id) return 135000 + id end }
STATE = judgedState("sotc", 20)
local Seals = mount("upper")
local P = Seals.parts
local icon = P.chip.icon
check(icon and isVisible(icon) and icon.path == 135000 + 20271, "the chip shows the Judgement spell texture: " .. tostring(icon and icon.path))
check(not isVisible(P.jLetter), "the J hides behind it")
check(#icon.points == 2, "two anchors inside the cut frame")
near3(icon.points[1][4], 2 * SK * SCALE, "chip icon inset"); check(isVisible(P.chip.plate) and isVisible(P.chip.edge), "the cut frame stays")
-- the empty row keeps the icon (the chip is only dimmed)
push(sealAt("sotc", 20)); check(isVisible(icon) and near3(P.chip.alpha, 0.45, "dimmed") == nil, "empty row: dimmed icon")
-- fallback: no readable icon, or no Judgement spell id
for _, why in ipairs({ "unreadable", "no spell", "no table" }) do
    boot()
    if why == "unreadable" then C_Spell = { GetSpellTexture = function() return nil end }
    elseif why == "no spell" then FS.HudSpells = {}
    else FS.HudSpells = nil end
    if why ~= "unreadable" then C_Spell = { GetSpellTexture = function(id) return 1 end } end
    STATE = judgedState("sotc", 20)
    local S2 = mount("upper")
    check(not isVisible(S2.parts.chip.icon) and isVisible(S2.parts.jLetter) and S2.parts.jLetter.text == "J", why .. ": the J shows")
end
-- a late answer
boot(); local ready = false
C_Spell = { GetSpellTexture = function(id) if ready then return 99 end return nil end }
STATE = judgedState("sotc", 20)
local S3 = mount("upper")
check(isVisible(S3.parts.jLetter), "J while unanswered")
ready = true; push(judgedState("sotc", 19))
check(S3.parts.chip.icon.path == 99 and not isVisible(S3.parts.jLetter), "the icon arrives at the next push")
""")

case("time_text_is_whole_seconds_above_five_and_tenths_below")(r"""
STATE = sealAt("sor", 21)
local Seals = mount("upper")
local P = Seals.parts
for _, row in ipairs({ { 21, "21s" }, { 20.2, "21s" }, { 29.9, "30s" }, { 45, "30s" }, { 6, "6s" }, { 5.01, "6s" }, { 5, "5.0s" }, { 4.25, "4.3s" },
    { 2.04, "2.0s" }, { 0.5, "0.5s" }, { 0.06, "0.1s" } }) do
    push(sealAt("sor", row[1]))
    textIs(P.time, row[2], S.TIME_SIZE, S.W, S.TIME_Y, row[1] .. " s")
end
check(Seals.TimeText(12.3) == "13s" and Seals.TimeText(3.14) == "3.1s", "TimeText is exported")
""")

case("reseal_band_is_the_zero_to_three_second_end")(r"""
STATE = sealAt("sotc", 20)
local Seals = mount("upper")
local P = Seals.parts
colA(P.band.color, CSS.amber, S.BAND_A, "the band at rest")
colA(P.reseal.textColor, CSS.amber, S.RESEAL_A, "RESEAL at rest")
-- the band's right edge is where the fill ends at exactly 3 s
local l, _, bw = imgRect(P.band)
local ox = org()
near3(l, ox, "the band starts at the 0 end"); near3(bw, S.W * S.BAND_S / S.MAX_S, "the band spans 0 to 3 s of 30")
push(sealAt("sotc", S.BAND_S))
near3(select(1, imgRect(P.fill)) + P.fill.w / (SK * SCALE), l + bw, "a fill of exactly 3 s ends at the band's edge")
push(sealAt("sotc", S.BAND_S - 1))
check(P.fill.w / (SK * SCALE) < bw, "under 3 s the fill lies inside the band")
-- the dashed cut line and the RESEAL label sit on the band
local cl = imgRect(P.cut[1])
near3(cl + select(3, imgRect(P.cut[1])) / 2, ox + bw, "the cut line is the band's right edge")
""")

case("reseal_warning_look_under_three_seconds")(r"""
STATE = sealAt("sotc", 10)
local Seals = mount("upper")
local P = Seals.parts
local col = sealColor("crusader")
barIs(P, 10, col, "10 s")
colA(P.time.textColor, col, 1, "time at 10 s"); check(P.cap.text == "SEAL ACTIVE", "caption at 10 s")
-- 3.5 s: not yet
push(sealAt("sotc", 3.5)); barIs(P, 3.5, col, "3.5 s"); check(P.cap.text == "SEAL ACTIVE", "no warning at 3.5 s")
colA(P.band.color, CSS.amber, S.BAND_A, "the band is steady at 3.5 s")
-- exactly 3.0 s is the warning too (the band is the 0 to 3 s end, inclusive)
push(sealAt("sotc", 3.0)); check(P.cap.text == "EXPIRING", "the warning starts at exactly 3.0 s"); barIs(P, 3.0, CSS.amber, "3.0 s")
-- exactly 0 left: the seal has run out, so the look is NO SEAL at once
push(sealAt("sotc", 0)); check(Seals.Mode() == "none" and P.name.text == "NO SEAL", "a seal with exactly 0 s left reads NO SEAL")
check(not isVisible(P.fill), "and draws no fill")
push(sealAt("sotc", 10))
-- 2.9 s: the warning. The fill, the time and the caption go amber; the tile and its name keep the seal's colour
push(sealAt("sotc", 2.9))
barIs(P, 2.9, CSS.amber, "2.9 s")
colA(P.time.textColor, CSS.amber, 1, "time in the warning")
check(P.cap.text == "EXPIRING", "caption in the warning: " .. tostring(P.cap.text)); colA(P.cap.textColor, CSS.amber, 1, "caption in the warning")
colA(P.tile.edge.vertex, col, 1, "the tile keeps the seal colour"); colA(P.name.textColor, CSS.white, 1, "the name stays white")
-- the band breathes with the clock; RESEAL breathes with the pulse
local seen = {}
for i = 1, 6 do
    tick(0.13)
    local rem = 2.9 - 0.13 * i
    local pl = 0.5 + 0.5 * math.sin(NOW * 9)
    near3(P.band.color[4], S.BAND_A + 0.2 * pl, "the band wash at " .. i)
    near3(P.reseal.textColor[4], 0.55 + 0.45 * (0.5 - 0.5 * math.cos(math.pi * NOW / 1.4)), "RESEAL at " .. i)
    seen[#seen + 1] = P.band.color[4]
end
check(math.abs(seen[1] - seen[4]) > 1e-3, "the band wash actually moves")
-- a recast leaves the warning: the colours, the caption and the band come back
push(sealAt("sotc", 25))
barIs(P, 25, col, "after a recast"); colA(P.time.textColor, col, 1, "time after a recast")
check(P.cap.text == "SEAL ACTIVE", "caption after a recast"); colA(P.cap.textColor, CSS.muted, 1, "caption colour after a recast")
colA(P.band.color, CSS.amber, S.BAND_A, "the band at rest again"); near3(P.reseal.textColor[4], S.RESEAL_A, "RESEAL at rest again")
""")

case("reseal_warning_is_steady_under_reduced_motion")(r"""
STATE = sealAt("sotc", 2.5)
local Seals = mount("upper")
ForeverSTUwaveDB.reducedMotion = true
push(sealAt("sotc", 2.5))
local P = Seals.parts
barIs(P, 2.5, CSS.amber, "reduced, 2.5 s"); check(P.cap.text == "EXPIRING", "still the warning")
local a, b = P.band.color[4], P.reseal.textColor[4]
near3(a, S.BAND_A, "the band rests at its base"); near3(b, 1, "RESEAL holds .55 + .45 * 1")
for i = 1, 5 do tick(0.1); near3(P.band.color[4], a, "band steady"); near3(P.reseal.textColor[4], b, "RESEAL steady") end
barIs(P, 2.0, CSS.amber, "and the drain still moves")
""")

case("no_seal_look")(r"""
STATE = noneState(false)
local Seals = mount("upper")
local P = Seals.parts
check(Seals.Mode() == "none", "none look")
local red = CSS.red
textIs(P.name, "NO SEAL", S.NAME_SIZE, S.NAME_X, S.NAME_Y, "name")
colorIs(P.name.textColor, red, "name colour"); near3(P.name.textColor[4], 0.5 + 0.5 * 0.5, "name alpha at rest")
textIs(P.cap, "CAST A SEAL", S.CAP_SIZE, S.NAME_X, S.CAP_Y, "caption"); colA(P.cap.textColor, CSS.muted, 1, "caption out of combat")
textIs(P.time, "--", S.TIME_SIZE, S.W, S.TIME_Y, "time"); colA(P.time.textColor, CSS.muted, 0.4, "time")
textIs(P.ab, "--", S.AB_SIZE, S.AB_X, S.AB_Y, "tile letters")
colorIs(P.tile.edge.vertex, red, "tile edge colour"); near3(P.tile.edge.vertex[4], 0.35 + 0.65 * 0.5, "tile edge alpha at rest")
colorIs(P.tile.plate.vertex, mixC(CSS.bg, red, S.TILE_MIX), "tile fill")
check(not isVisible(P.fill) and not isVisible(P.tip), "no fill and no tip")
for i, t in ipairs(P.outline) do colA(t.color, CSS.steel, S.OUT_A, "outline " .. i .. " steel") end
colA(P.track.color, rgb(S.TRACK), S.TRACK_A, "the track stays")
rowEmpty(P, "", "empty row")
check(onUpdateFrames() == 0, "no ticker out of combat")
-- in combat: the caption turns red and the tile and name pulse on one ticker
push(noneState(true))
colA(P.cap.textColor, red, 0.8, "caption in combat")
check(onUpdateFrames() == 1, "one ticker in combat")
for _, dt in ipairs({ 0.2, 0.3, 0.45 }) do
    tick(dt)
    local u = 0.5 - 0.5 * math.cos(math.pi * NOW / 1.4)
    near3(P.name.textColor[4], 0.5 + 0.5 * u, "name pulse"); near3(P.tile.edge.vertex[4], 0.35 + 0.65 * u, "edge pulse")
    near3(P.tile.glow.vertex[4], Seals.C.TILE_GLOW_A * (0.35 + 0.65 * u), "glow pulse")
end
push(noneState(false)); check(onUpdateFrames() == 0, "the ticker clears when the fight ends")
colA(P.cap.textColor, CSS.muted, 1, "caption after the fight")
""")

case("no_seal_is_steady_under_reduced_motion")(r"""
ForeverSTUwaveDB.reducedMotion = true
STATE = noneState(true)
local Seals = mount("upper")
local P = Seals.parts
check(onUpdateFrames() == 0, "no pulse, so no ticker")
near3(P.name.textColor[4], 1, "name steady at u = 1"); near3(P.tile.edge.vertex[4], 1, "edge steady at u = 1")
""")

case("unknown_looks_guess_nothing")(r"""
local Seals = mount("upper", { hidden = true })
local P = Seals.parts
local function check_unknown(st, what)
    push(st)
    check(Seals.Mode() == "unknown", what .. ": unknown look")
    check(P.name.text == "" and P.cap.text == "" and P.ab.text == "", what .. ": no text guessed")
    check(not isVisible(P.fill) and not isVisible(P.tip) and not isVisible(P.time), what .. ": no bar, no time")
    colorIs(P.tile.edge.vertex, CSS.violet, what .. ": violet tile")
    check(not P.tile.glow.shown, what .. ": no glow")
    check(onUpdateFrames() == 0, what .. ": no ticker")
end
REGS[1].spec.onShow("upper")
check_unknown(unknownState(), "nil seal")
check_unknown(sealAt("nope", 10), "an unmapped key")
local st = sealAt("sor", 10); st.seal = SECRET; check_unknown(st, "a secret seal")
st = sealAt("sor", 10); st.seal.key = SECRET; check_unknown(st, "a secret key")
st = sealAt("sor", 10); st.seal.key = 7; check_unknown(st, "a number key")
check_unknown("garbage", "a string state")
check_unknown(SECRET, "a secret state")
-- a secret combat flag is not combat
local n = noneState(SECRET); push(n); check(Seals.Mode() == "none" and onUpdateFrames() == 0, "a secret combat flag reads as out of combat")
""")

case("a_repaint_is_written_only_when_the_look_changes")(r"""
STATE = sealAt("sor", 20)
local Seals = mount("upper")
local P = Seals.parts
local function writes()
    local n = 0
    for _, t in ipairs(TEXTURES) do n = n + (t.writes or 0) end
    return n
end
local before = #P.tile.plate.vertex
local setText = 0
local orig = P.name.SetText
P.name.SetText = function(self, t) setText = setText + 1; return orig(self, t) end
push(sealAt("sor", 19)); push(sealAt("sor", 18))
check(setText == 0, "the name was not rewritten by pushes of the same seal: " .. setText)
push(sealAt("sotc", 18)); check(setText == 1 and P.name.text == "CRUSADER", "a new seal rewrites it once")
push(noneState(false)); push(noneState(false)); check(setText == 2 and P.name.text == "NO SEAL", "none rewrites it once")
push(noneState(true)); local after = setText
push(noneState(true)); check(setText == after, "the same combat look is not written again")
""")

case("judgement_row_follows_the_target_debuff")(r"""
STATE = judgedState("sotc", 14)
local Seals = mount("upper")
local P = Seals.parts
local col = sealColor("crusader")
rowIs(P, 14, col, "14 s"); near3(P.jFill.w / (SK * SCALE), (S.W - S.JBAR_SHRINK) * 14 / 40, "bar is 14 / 40 of its track")
colA(P.jLetter.textColor, CSS.white, 1, "J")
colorIs(P.chip.plate.vertex, mixC(CSS.bg, rgb(S.J_PLATE), S.J_MIX), "chip fill")
for _, rem in ipairs({ 40, 39.5, 25, 10, 2.2, 0.1 }) do
    push(judgedState("sotc", rem)); rowIs(P, rem, col, rem .. " s")
end
push(judgedState("sotc", 55)); rowIs(P, 40, col, "pinned at 40 s")
-- a 10 s Judgement (Justice) on its 0 to 40 s axis, the colour of the seal it was cast under
push(judgedState("soj", 10)); rowIs(P, 10, sealColor("justice"), "justice, 10 s")
-- the clock moves the bar and the time, and the debuff running out empties the row at once
push(judgedState("sotc", 12)); tick(4); rowIs(P, 8, col, "four seconds on")
tick(8.5); rowEmpty(P, "NOT JUDGED", "ran out"); check(onUpdateFrames() == 1, "the timed seal keeps the ticker")
""")

case("judgement_row_empty_looks")(r"""
local Seals = mount("upper", { hidden = true })
local P = Seals.parts
REGS[1].spec.onShow("upper")
local function st(key, judged) local s = sealAt(key, 1000); s.judged = judged; return s end
push(st("sotc", false)); rowEmpty(P, "NOT JUDGED", "crusader, none on the target")
push(st("sor", false)); rowEmpty(P, "NO DEBUFF", "righteousness carries none")
push(st("sotc", nil)); rowEmpty(P, "NOT JUDGED", "unknown judged")
push(noneState(false)); rowEmpty(P, "", "no seal")
push(unknownState()); rowEmpty(P, "", "unknown seal")
-- unreadable debuffs never light the row
push(st("sotc", SECRET)); rowEmpty(P, "NOT JUDGED", "a secret judged")
push(st("sotc", { key = SECRET, expiresAt = NOW + 5 })); rowEmpty(P, "NOT JUDGED", "a secret key")
push(st("sotc", { key = "sotc", expiresAt = SECRET })); rowEmpty(P, "NOT JUDGED", "a secret expiry")
push(st("sotc", { key = "sotc", expiresAt = "x" })); rowEmpty(P, "NOT JUDGED", "a string expiry")
push(st("sotc", { key = "sor", expiresAt = NOW + 5 })); rowEmpty(P, "NOT JUDGED", "a seal with no Judgement debuff")
push(st("sotc", { key = "zzz", expiresAt = NOW + 5 })); rowEmpty(P, "NOT JUDGED", "an unmapped key")
-- the row lights in the look's colour: red when the seal ran out, violet for unknown
local lit = { key = "sotc", expiresAt = NOW + 20, appliedAt = NOW - 1, duration = 40 }
local s = noneState(false); s.judged = lit; push(s); rowIs(P, 20, CSS.red, "no seal")
s = unknownState(); s.judged = lit; push(s); rowIs(P, 20, CSS.violet, "unknown seal")
""")

case("a_retarget_and_a_dead_target_switch_the_row")(r"""
STATE = judgedState("sotc", 30)
local Seals = mount("upper")
local P = Seals.parts
local col = sealColor("crusader")
rowIs(P, 30, col, "lit")
check(P.events.events.PLAYER_TARGET_CHANGED and P.events.events.UNIT_HEALTH, "the event frame listens while shown")
-- a retarget reads the Hud's own judgement for the new target at once
JUDGE_ANSWER = { key = "sotc", remaining = 12 }; fire("PLAYER_TARGET_CHANGED"); rowIs(P, 12, col, "a debuffed target")
JUDGE_ANSWER = { remaining = 0 }; fire("PLAYER_TARGET_CHANGED"); rowEmpty(P, "NOT JUDGED", "a clean target")
JUDGE_ANSWER = SECRET; fire("PLAYER_TARGET_CHANGED"); rowEmpty(P, "NOT JUDGED", "a secret answer")
JUDGE_ANSWER = { key = "sotc", remaining = SECRET }; fire("PLAYER_TARGET_CHANGED"); rowEmpty(P, "NOT JUDGED", "a secret remaining")
JUDGE_ANSWER = { key = "sotc", remaining = 9 }
UnitGUID = function() return SECRET end
fire("PLAYER_TARGET_CHANGED"); rowEmpty(P, "NOT JUDGED", "a secret target GUID waits for the push")
UnitGUID = function() return "Creature-0-0-0-0-1-0000000001" end
fire("PLAYER_TARGET_CHANGED"); rowIs(P, 9, col, "a plain GUID reads the answer")
-- a target that dies empties the row, and a resurrection relights it
DEAD = true; fire("UNIT_HEALTH", "target"); rowEmpty(P, "NOT JUDGED", "a dead target")
fire("UNIT_HEALTH", "target"); rowEmpty(P, "NOT JUDGED", "still dead")
DEAD = false; fire("UNIT_HEALTH", "target"); rowIs(P, 9, col, "resurrected")
push(judgedState("sotc", 30)); DEAD = true; push(judgedState("sotc", 30)); rowEmpty(P, "NOT JUDGED", "a push for a dead target")
""")

case("the_module_follows_the_hud_only_while_its_area_shows_it")(r"""
STATE = sealAt("sor", 20)
local Seals, frame, spec = mount("upper", { hidden = true })
local P = Seals.parts
check(#SUBS == 0, "built and seated but not shown: not subscribed")
check(not (P.events.events.PLAYER_TARGET_CHANGED or P.events.events.UNIT_HEALTH), "and not listening")
check(onUpdateFrames() == 0, "and no ticker")
check(P.name.text == "", "and nothing painted from the Hud")
spec.onShow("upper")
check(#SUBS == 1, "onShow subscribes"); check(P.name.text == "RIGHTEOUSNESS", "and paints the current state at once")
check(onUpdateFrames() == 1 and P.events.events.PLAYER_TARGET_CHANGED, "ticker and events on")
spec.onHide("upper")
check(#SUBS == 0, "onHide unsubscribes"); check(onUpdateFrames() == 0, "and clears the ticker")
check(not (P.events.events.PLAYER_TARGET_CHANGED or P.events.events.UNIT_HEALTH), "and stops listening")
-- the area hides the host with the module: no frame runs while hidden
STATE = sealAt("sotc", 10)
HOST:Hide(); tick(1); HOST:Show()
check(P.name.text == "RIGHTEOUSNESS", "nothing repaints while hidden")
-- shown again: subscribes again
spec.onShow("lower"); check(#SUBS == 1 and P.name.text == "CRUSADER", "onShow again resubscribes and repaints")
spec.onHide("lower"); spec.onHide("lower"); check(#SUBS == 0, "a double hide is harmless")
spec.onShow("upper"); spec.onShow("upper"); check(#SUBS == 1, "a double show subscribes once")
""")

case("a_stale_hud_push_after_the_hide_is_ignored")(r"""
STATE = sealAt("sor", 20)
local Seals, frame, spec = mount("upper")
local P = Seals.parts
local push_fn = SUBS[1]
check(type(push_fn) == "function", "the Hud callback")
spec.onHide("upper")
push_fn(sealAt("sotc", 10))
check(P.name.text == "RIGHTEOUSNESS", "a push that arrives after onHide changes nothing")
check(onUpdateFrames() == 0, "and starts no ticker")
""")

case("exactly_one_onupdate_exists_only_while_something_moves")(r"""
local Seals, frame, spec = mount("upper", { hidden = true })
local P = Seals.parts
spec.onShow("upper")
check(onUpdateFrames() == 0, "nothing pushed yet")
push(unknownState()); check(onUpdateFrames() == 0, "unknown: no ticker")
push(noneState(false)); check(onUpdateFrames() == 0, "none out of combat: no ticker")
push(sealAt("sor", 20)); check(onUpdateFrames() == 1 and frame.scripts.OnUpdate, "a timed seal: one ticker, on the module frame")
push(sealAt("sor", 20, { seal = { key = "sor", id = 1, expiresAt = SECRET, duration = 30 } })); check(onUpdateFrames() == 0, "a seal with no readable time: no ticker")
push(judgedState("sotc", 20, "sor")); check(onUpdateFrames() == 1, "a debuff on the target alone keeps one ticker")
push(judgedState("sotc", 20)); check(onUpdateFrames() == 1, "a seal and a debuff share the one ticker")
local n = 0
for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then n = n + 1 end end
check(n == 1, "still one OnUpdate in the whole tree")
-- the seal runs out: the module flips to NO SEAL by itself; the debuff still drains in red
push(sealAt("sor", 1.5)); tick(2)
check(Seals.Mode() == "none", "the expiry flipped the look by itself")
colA(P.name.textColor, CSS.red, P.name.textColor[4], "NO SEAL")
push(sealAt("sor", 1.5)); tick(2); push(noneState(false)); check(Seals.Mode() == "none", "the Hud's late push repaints nothing new")
check(onUpdateFrames() == 0, "nothing moves out of combat: the ticker is cleared")
""")

case("a_steady_tick_writes_only_the_bar_widths_and_the_text")(r"""
STATE = judgedState("sotc", 30)
STATE.seal.expiresAt = NOW + 25
local Seals, frame = mount("upper")
local P = Seals.parts
tick(0.01)
local function snapshot()
    local n, w = 0, 0
    for _, t in ipairs(TEXTURES) do n = n + t.setPointCalls; w = w + (t.writes or 0) end
    for _, s in ipairs(FONTSTRINGS) do n = n + s.setPointCalls; w = w + (s.writes or 0) end
    for _, f in ipairs(FRAMES) do n = n + f.setPointCalls; w = w + (f.writes or 0) end
    return n, w
end
local n0, w0 = snapshot()
local widthWrites = 0
for _, t in ipairs({ P.fill, P.jFill }) do
    local origW = t.SetWidth
    t.SetWidth = function(self, v) widthWrites = widthWrites + 1; return origW(self, v) end
end
for i = 1, 20 do tick(0.016) end
local n1, w1 = snapshot()
check(n1 == n0, "no SetPoint during steady ticks: " .. (n1 - n0))
check(w1 == w0, "no Show or Hide during steady ticks: " .. (w1 - w0))
check(widthWrites == 40, "the two bar widths are the things a tick writes: " .. widthWrites)
-- the time text only when it changes
local texts = 0
local origT = P.time.SetText
P.time.SetText = function(self, v) texts = texts + 1; return origT(self, v) end
for i = 1, 30 do tick(0.016) end
check(texts <= 1, "the time text is written when its string changes, not every frame: " .. texts)
""")

case("the_per_frame_path_allocates_nothing")(r"""
jit.off()
STATE = judgedState("sotc", 38, "sotc")
STATE.seal.expiresAt = NOW + 29
local Seals, frame = mount("upper")
-- the mock's colour setters build a table per call, which the client does not: reuse one per region so only the addon's own
-- allocation is counted
for _, t in ipairs(TEXTURES) do
    t.SetVertexColor = function(self, r, g, b, a) local v = self.vertex; v[1], v[2], v[3], v[4] = r, g, b, a == nil and 1 or a end
    t.SetColorTexture = function(self, r, g, b, a)
        local c = self.color or { 0, 0, 0, 0 }
        self.color = c; c[1], c[2], c[3], c[4] = r, g, b, a; self.path = nil
    end
end
for _, s in ipairs(FONTSTRINGS) do
    s.textColor = { 0, 0, 0, 0 }
    s.SetTextColor = function(self, r, g, b, a) local c = self.textColor; c[1], c[2], c[3], c[4] = r, g, b, a end
end
local OnUpdate = frame.scripts.OnUpdate
check(type(OnUpdate) == "function", "ticking")
for i = 1, 300 do NOW = NOW + 0.01; OnUpdate(frame, 0.01) end            -- warm every path once
collectgarbage(); collectgarbage("stop")
local before = collectgarbage("count")
for i = 1, 1500 do NOW = NOW + 0.01; OnUpdate(frame, 0.01) end            -- through whole seconds, tenths and the reseal band
local grown = (collectgarbage("count") - before) * 1024
collectgarbage("restart")
check(grown < 512, "1500 frames allocated " .. math.floor(grown) .. " bytes")
check(frame.scripts.OnUpdate, "still ticking (29 s of seal left at the start)")
-- the same through the reseal warning and a NO SEAL pulse
STATE = nil; push(sealAt("sotc", 3.2)); push(noneState(true))
OnUpdate = frame.scripts.OnUpdate
for i = 1, 100 do NOW = NOW + 0.01; OnUpdate(frame, 0.01) end
collectgarbage(); collectgarbage("stop")
before = collectgarbage("count")
for i = 1, 1500 do NOW = NOW + 0.01; OnUpdate(frame, 0.01) end
grown = (collectgarbage("count") - before) * 1024
collectgarbage("restart")
check(grown < 512, "1500 NO SEAL pulse frames allocated " .. math.floor(grown) .. " bytes")
""")

case("a_throwing_frame_stops_the_ticker_until_the_next_push")(r"""
STATE = sealAt("sor", 20)
local Seals, frame = mount("upper")
local P = Seals.parts
P.fill.SetWidth = function() error("boom") end
tick(0.1)
check(onUpdateFrames() == 0, "a throw clears the ticker")
check(DEGRADED["gunsightseals_tick"], "and logs it once")
P.fill.SetWidth = nil
push(sealAt("sor", 19)); check(onUpdateFrames() == 1, "the next push starts it again")
""")

case("reduced_motion_flag_is_read_at_each_push")(r"""
STATE = noneState(true)
local Seals = mount("upper")
check(onUpdateFrames() == 1, "pulsing")
ForeverSTUwaveDB.reducedMotion = true; push(noneState(true)); check(onUpdateFrames() == 0, "reduced motion stops the pulse at the next push")
ForeverSTUwaveDB.reducedMotion = nil; push(noneState(true)); check(onUpdateFrames() == 1, "and clearing the flag resumes it")
ForeverSTUwaveDB.reducedMotion = "yes"; push(noneState(true)); check(onUpdateFrames() == 1, "only an exact true counts")
""")

case("a_missing_hud_or_theme_degrades_instead_of_throwing")(r"""
boot({ noHud = true })
REGS[1].spec.build(CreateFrame("Frame", nil, UIParent)); REGS[1].spec.seat(RECTS.upper)
REGS[1].spec.onShow("upper")
check(DEGRADED["gunsightseals_nohud"], "no Hud: logged once")
check(#SUBS == 0 and onUpdateFrames() == 0, "and nothing runs")
boot({ noTheme = true })
FS.Theme = nil
local f = REGS[1].spec.build(CreateFrame("Frame", nil, UIParent))
check(f == nil and DEGRADED["gunsightseals_notheme"], "no Theme: build answers nil and logs")
REGS[1].spec.seat(RECTS.upper); REGS[1].spec.onShow("upper"); REGS[1].spec.onHide("upper")
-- a build that throws leaves nothing behind
boot()
FS.Theme.AddSliceTexture = function() error("boom") end
local g = REGS[1].spec.build(CreateFrame("Frame", nil, UIParent))
check(g == nil and DEGRADED["gunsightseals_build"], "a throwing build answers nil and logs: " .. tostring(g))
REGS[1].spec.seat(RECTS.upper); REGS[1].spec.onShow("upper")
check(#SUBS == 0, "and a later show subscribes nothing")
""")

case("no_aura_api_is_read")(r"""
STATE = judgedState("sotc", 20)
local Seals = mount("upper")
push(sealAt("sor", 3)); push(noneState(true)); tick(1)
check(#AURA_TOUCHED == 0, "an aura API was read: " .. tostring(AURA_TOUCHED[1]))
check(#PLAYING == 0 or next(PLAYING) == nil, "no animation group playing")
""")


# ---------------------------------------------------------------------------------------
# Static checks
# ---------------------------------------------------------------------------------------

HOT = ("Pulse", "TimeText", "BarWidth", "TextAlpha", "PaintText", "Tint", "SetWarn", "ApplyNoSeal", "ApplyBar",
       "ApplyJudgeBar", "LiveJudged", "LiveNone", "LiveSeal", "Live", "Animating", "Tick")


def hot_path_check(code: str) -> str | None:
    """Everything the ticker runs each frame: no table, closure, concatenation, formatted string or object creation."""
    banned = [r"\{", r"function\s*\(", r"\.\.", r"string\.format", r"\bformat\(", r"CreateColor", r"CreateFrame", r"CreateTexture",
              r"CreateFontString", r"\bselect\(", r"\bunpack\(", r"\bpcall\(", r"tostring\(", r"setmetatable", r"\bMix\("]
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
    """One OnUpdate script on the module frame, set only while something animates and cleared with nil, plus the one event frame's
    OnEvent (the target change and the target's health); nothing else is scripted."""
    calls = re.findall(r"SetScript\(([^)]*)\)", code)
    if sorted(c.replace(" ", "") for c in calls) != sorted(['"OnUpdate",Tick', '"OnUpdate",nil', '"OnEvent",OnTargetEvent']):
        return ("GunsightSeals.lua must call SetScript exactly three times, to install Tick, to clear it and for the event frame: "
                + repr(calls))
    return None


def secret_guard_order(code: str) -> str | None:
    """The mock cannot trap a compare, an index or arithmetic on a secret STRING (a plain string in the mock), so this reads the
    source: in each function below, nothing may mention the value before its FS.IsSecret guard except the line that declares it."""
    wanted = [("SealIdOf", "key"), ("CombatOf", "flag"), ("Resolve", "state"), ("Resolve", "seal"), ("Plain", "v"),
              ("JudgedOf", "state"), ("JudgedOf", "jd"), ("KeyHasDebuff", "key"), ("ReadJudgement", "j"), ("TargetDead", "v"),
              ("ReadTarget", "guid")]
    for fn, var in wanted:
        m = re.search(r"(?ms)^local function %s\(.*?^end$" % fn, code)
        if not m:
            return f"{fn} is missing from GunsightSeals.lua"
        body = m.group(0)
        g = body.find(f"IsSecret({var})")
        if g < 0:
            return f"{fn} never passes {var} through FS.IsSecret"
        for line in body[:g].splitlines():
            if re.search(r"\b%s\b" % var, line) and not re.search(r"(local\s+[\w,\s]*\b%s\b[\w,\s]*=|^local function)" % var, line):
                return f"{fn} touches {var} before its FS.IsSecret guard: {line.strip()}"
    return None


def texture_guard(code: str) -> str | None:
    """The texture answer is checked for a secret before any type test or comparison (the mock cannot trap it)."""
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
    """The debuff's expiresAt reaches arithmetic only through Plain (the FS.IsSecret guard first), and nothing in the row code
    does arithmetic on the raw fields of state.judged."""
    m = re.search(r"(?ms)^local function JudgedOf\(.*?^end$", code)
    if not m:
        return "JudgedOf is missing from GunsightSeals.lua"
    body = m.group(0)
    raw = re.findall(r"jd\.expiresAt", body)
    plain = re.findall(r"Plain\(jd\.expiresAt\)", body)
    if not plain or len(raw) != len(plain):
        return "JudgedOf must read expiresAt through Plain"
    for fn in ("LaneLook", "ApplyJudgeBar", "LiveJudged", "ExpireJudged"):
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
        s = toc.index("Modules/CombatHud/GunsightSeals.lua")
        a = toc.index("Modules/CombatHud/GunsightAreas.lua")
        g = toc.index("Modules/CombatHud/Gunsight.lua")
        hp = toc.index("Modules/CombatHud/HudProfiles.lua")
        th = toc.index("Core/Theme.lua")
        out.append(("toc_order", None if s > a > g else
                    f"GunsightSeals.lua must load after GunsightAreas.lua and Gunsight.lua (positions {s}, {a}, {g})"))
        out.append(("toc_after_hud_profiles_and_theme", None if s > hp and s > th else
                    "GunsightSeals.lua must load after HudProfiles.lua and Theme.lua"))
        out.append(("toc_lists_the_file_once", None if toc.count("Modules/CombatHud/GunsightSeals.lua") == 1 else
                    "GunsightSeals.lua must appear in the .toc exactly once"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "forever-stuwave.toc must stay CRLF"))
    if SEALS.exists():
        text = SEALS.read_text(encoding="utf-8")
        code = "\n".join(ln.split("--", 1)[0] for ln in text.splitlines())
        banned = [w for w in ("CreateAnimationGroup", "UnitAura", "UnitBuff", "UnitDebuff",
                              "C_UnitAuras", "GetAuraDataByIndex", "GetPlayerAuraBySpellID", "SetRotation", "CreateLine")
                  if w in code]
        out.append(("source_has_no_animation_group_and_no_aura_read", None if not banned else
                    "GunsightSeals.lua code mentions " + ", ".join(banned)))
        gone = [w for w in ("RegisterPiece", "IsPieceOn", "OnPieceChanged", "SetPiece", "GunsightDots", "OnReady", "DOT_AX",
                            "OnRescale", "seal_lens", "seal_arcs", "seal_ring", "seal_glyph", "glow_round", "SLICE_CUT2_GLOW_TEXTURE")
                if w in code]
        out.append(("the_old_chamber_and_its_dot_piece_gate_are_gone", None if not gone else
                    "GunsightSeals.lua still carries " + ", ".join(gone)))
        out.append(("exactly_one_onupdate_installed_and_cleared", ticker_check(code)))
        out.append(("the_per_frame_path_allocates_nothing_static", hot_path_check(code)))
        i_flag, i_cmp = code.find("IsSecret(flag)"), code.find("flag == true")
        out.append(("source_guards_the_combat_flag_before_comparing", None if 0 <= i_flag < i_cmp else
                    "GunsightSeals.lua must pass the combat flag through FS.IsSecret before it compares it"))
        i_guard, i_use = code.find("IsSecret(key)"), code.find("return KEY_ID[key]")
        out.append(("source_guards_the_key_before_indexing", None if 0 <= i_guard < i_use else
                    "GunsightSeals.lua must pass the seal key through FS.IsSecret before it indexes KEY_ID with it"))
        out.append(("secret_guards_come_before_the_first_use_of_each_value", secret_guard_order(code)))
        out.append(("source_guards_the_texture_answer_before_comparing_it", texture_guard(code)))
        out.append(("source_reads_the_judgement_time_only_through_plain", judged_times_plain(code)))
        out.append(("source_has_no_em_dash", None if "—" not in text else "GunsightSeals.lua contains an em dash"))
        out.append(("player_text_never_says_tape", None if not re.search(r"(?i)\btape\b", code) else
                    "GunsightSeals.lua code mentions the tape; player text says cast bar"))
        out.append(("every_registration_is_guarded", None if re.search(
            r"(?m)^if FS\.GunsightAreas and FS\.GunsightAreas\.RegisterModule then\s*\n\s*FS\.GunsightAreas\.RegisterModule\(\"class\"", text)
            and text.count("RegisterModule(") == 1 else
            "GunsightSeals.lua must register once, behind `if FS.GunsightAreas and FS.GunsightAreas.RegisterModule then`"))
        out.append(("source_builds_nothing_at_file_scope", None if not re.search(r"^\s*CreateFrame\(", text, re.M)
                    and not re.search(r"^[A-Za-z_.]+ = CreateFrame\(", text, re.M) else
                    "GunsightSeals.lua must build only inside build() (no file-scope CreateFrame)"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.globals().SEALS_SRC = SEALS.read_text(encoding="utf-8")
    lua.globals().HELPERS_SRC = tips.HELPERS.read_text(encoding="utf-8")
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_module()
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
