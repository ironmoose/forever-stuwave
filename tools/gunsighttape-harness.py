#!/usr/bin/env python3
"""Runs the real GunsightTape.lua (the two cast tapes of the Gunsight HUD) headless against a mock WoW API.

GunsightTape.lua is pieces "you" and "tgt" of mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html
(drawTape, plus the KICK tag and padlock of drawTarget): your cast on a 30 wide vertical tape left of the
character, the target's on an identical one right of it, both built on the shared chevron engine (vertical runs)
and driven by the EXISTING CastBars.lua state machine through its view seam (FS.CastBars.SetView). The checks
use the REAL CastBars.lua, ChevronCastBar.lua, Layout.lua and Gunsight.lua; Theme's constants are read from
Theme.lua and its helper functions are the castbars-harness stubs. They pin:

  * constants: chevron count, half widths, depth, thickness, tick count and lengths, the dim alpha, the KICK
    tag and padlock boxes are parsed back out of the mockup, so a mockup edit fails here;
  * build: both pieces registered, frames filling the tape anchors, the run seated from the anchor, 20
    whole-pixel chevrons at several screen heights, 11 outer-edge ticks each side, dim chevrons at rest;
  * the player tape: a plain cast fills the run, a verdict plays the engine's lock-in or outage;
  * the target tape: ALWAYS engine timed (SetTimerDuration on two stacked vertical strips, pink and steel),
    nothing secret is ever compared, the interruptible flag only reaches SetAlphaFromBoolean (pink
    interruptible, steel not), KICK and padlock show only while a cast is live and follow the same flag;
  * the target's chevron reveal: the strip is an invisible (alpha 0) but live clock, a clipped frame rides its
    fill's TOP, the run's own lit chevrons sit at the run's segment rects (two scales and heights), a caret on
    top of the edge, the tones reach the reveal, no secret is touched, a rescale builds nothing, and a client without
    SetClipsChildren keeps the visible strip tile (logged once);
  * degrade: no SetAlphaFromBoolean, no vertical strip support, no seam in CastBars: never an error;
  * lifecycle: no OnUpdate at rest (the readout ticker installs one only while a cast is live), a rescale
    resizes in place and builds nothing, Stack A is retired by the seam and left completely alone with the
    Gunsight off.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the real client.

    python3 tools/gunsighttape-harness.py

Exit 0 = every check passed. GUNSIGHTTAPE_LUA=<path> runs another file in place of GunsightTape.lua.
GUNSIGHTTAPE_CASTBARS_LUA=<path> runs another file in place of CastBars.lua: the MANUAL mutation hook for the
onVerdict pcall test (a CastBars copy with the pcall around bar.onVerdict removed fails
`a_throwing_hook_never_stops_the_verdict`). Nothing automates that mutation.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent
TAPE = Path(os.environ.get("GUNSIGHTTAPE_LUA") or ADDON / "GunsightTape.lua")
CASTBARS = Path(os.environ.get("GUNSIGHTTAPE_CASTBARS_LUA") or ADDON / "CastBars.lua")
GUNSIGHT = ADDON / "Gunsight.lua"
LAYOUT = ADDON / "Layout.lua"
TOC = ADDON / "ForeverSynthwave.toc"
MOCKUP = ADDON / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CB = _load("castbars_harness", "castbars-harness.py")
CHEV = CB.CHEV
GS = _load("gunsight_harness", "gunsight-harness.py")


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_tape() -> dict:
    """Everything drawTape, drawTarget's KICK tag and padlock own, read out of the mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    base = GS.mockup_constants()
    n = int(_m(r"FR_B=\d+,N=(\d+),PITCH=\(BOT-TOP\)/N", src, "N").group(1))
    d, tk = _m(r"var hw=o\.hw\|\|\d+,d=(\d+),tk=([\d.]+);", src, "d/tk").groups()
    hw_you = int(_m(r"drawTape\(\{x0:TL\.x0,x1:TL\.x1,col:K\.cyan,st:st,side:-1,pulse:0,hw:(\d+)\}", src, "player hw").group(1))
    tick_top, tick_div, tick_mid, tick_mid_len, tick_len, tick_a = _m(
        r"for\(var k=0;k<=(\d+);k\+\+\)\{var ty=BOT-k\*\(BOT-TOP\)/(\d+);tick\(ex,ty,k===(\d+)\?(\d+):(\d+),out,col,(\.\d+)\);\}",
        src, "ticks").groups()
    frame_chamfer = int(_m(r"chamfer\(x0,FR_T,x1-x0,FR_B-FR_T,(\d+)\);\s*base=vv;A\(\.3\)", src, "frame chamfer").group(1))
    frame_fill = _m(r"A\(\.3\);ctx\.fillStyle='rgba\((\d+),(\d+),(\d+),(\.\d+)\)'", src, "frame fill").groups()
    edge = _m(r"var edge=clamp\((\.\d+)\+(\.\d+)\*o\.pulse,0,1\);", src, "edge alpha").groups()
    dim = _m(r"if\(o\.engine\)\{A\((\.\d+)\);ctx\.fillStyle=col;chevPath", src, "engine dim alpha").group(1)
    pulse_hz = int(_m(r"var pulse=st\.kick&&st\.mode==='cast'\?\.5\+\.5\*Math\.sin\(clock\*(\d+)\):0;", src, "pulse rate").group(1))
    kw, kh = _m(r"function kickTag\(x,y,col,a\)\{\s*var w=(\d+),h=(\d+);", src, "kick tag size").groups()
    kchamfer = int(_m(r"chamfer\(x,y,w,h,(\d+)\);A\(a\);ctx\.fillStyle='rgba\(13,6,32,\.95\)'", src, "kick chamfer").group(1))
    ktext = int(_m(r"text\('KICK',x\+w/2,y\+(\d+),(\d+),col,a,'center'\)", src, "kick text").group(1))
    ktext_size = int(_m(r"text\('KICK',x\+w/2,y\+\d+,(\d+),col,a,'center'\)", src, "kick text size").group(1))
    kdx, kdy = _m(r"var kx=BOXR\.x\+BOXR\.w-(\d+),ky=BOXR\.y-(\d+);", src, "kick position").groups()
    _m(r"kx\+=BR\.x\+BR\.w-BOXR\.x-BOXR\.w;ky\+=BR\.y-BOXR\.y;", src, "kick rides the grown box")
    grow = int(_m(r"if\(TBS==='b'\)return \{x:BOXR\.x,y:BOXR\.y-(\d+),w:BOXR\.w,h:BOXR\.h\+\d+\};", src, "option B box rect").group(1))
    ldx, ldy = _m(r"padlock\(kx\+(\d+),ky-([\d.]+),K\.steel", src, "padlock offset").groups()
    pl = _m(r"function padlock\(x,y,col,a\)\{ /\* x,y = top-left, (\d+)x(\d+) \*/", src, "padlock box").groups()
    body = [float(v) for v in _m(r"ctx\.fillRect\(x\+(\d+),y\+(\d+),(\d+),(\d+)\);\s*A\(a\);ctx\.fillStyle=K\.bg", src, "padlock body").groups()]
    hole = [float(v) for v in _m(r"A\(a\);ctx\.fillStyle=K\.bg;ctx\.fillRect\(x\+(\d+),y\+(\d+),([\d.]+),([\d.]+)\)", src, "padlock keyhole").groups()]
    shackle = [float(v) for v in _m(
        r"ctx\.moveTo\(x\+([\d.]+),y\+(\d+)\);ctx\.lineTo\(x\+[\d.]+,y\+(\d+)\);ctx\.arc\(x\+(\d+),y\+(\d+),([\d.]+),Math\.PI,0\)",
        src, "padlock shackle").groups()]
    css = {k: v.lower() for k, v in re.findall(r"^\s*--(pink|steel|cyan|bg):(#[0-9a-fA-F]{6});", src, re.M)}
    for need in ("pink", "steel", "cyan", "bg"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")
    return dict(
        base=base, N=n, HW_YOU=hw_you, CHEV_D=int(d), CHEV_T=float(tk),
        TICKS=int(tick_top), TICK_DIV=int(tick_div), TICK_MID=int(tick_mid), TICK_MID_LEN=int(tick_mid_len),
        TICK_LEN=int(tick_len), TICK_A=float(tick_a),
        FRAME_CHAMFER=frame_chamfer, FRAME_FILL=[int(frame_fill[0]), int(frame_fill[1]), int(frame_fill[2]), float(frame_fill[3])],
        FRAME_ALPHA=0.3, EDGE_A0=float(edge[0]), EDGE_A1=float(edge[1]), DIM=float(dim), PULSE_RATE=pulse_hz,
        KICK_W=int(kw), KICK_H=int(kh), KICK_CHAMFER=kchamfer, KICK_TEXT_Y=ktext, KICK_TEXT_SIZE=ktext_size,
        KICK_DX=int(kdx), KICK_DY=int(kdy), KICK_GROW=grow, LOCK_DX=int(ldx), LOCK_DY=float(ldy),
        LOCK_W=int(pl[0]), LOCK_H=int(pl[1]), LOCK_BODY=body, LOCK_HOLE=hole, LOCK_SHACKLE=shackle, CSS=css,
    )


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"[{k!r}]={lua_value(x)}".replace("'", '"') for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v + '"'
    return repr(v)


# ---------------------------------------------------------------------------------------
# The mock client: the castbars-harness one (which sits on the chevron engine's) plus what the
# Gunsight core, Layout and the tape need on top.
# ---------------------------------------------------------------------------------------

THEME_CONSTANTS = CB.THEME_CONSTANTS + ("COLOR_STEEL", "COLOR_BORDER", "COLOR_RED")

MOCK = r"""
local Region = getmetatable(UIParent)
SlashCmdList = {}
function InCombatLockdown() return false end
function Region:IsVisible()
    local f = self
    while f do
        if f._shown == false then return false end
        f = f._parent
    end
    return true
end
function Region:SetFrameStrata(s) self._strata = s end
-- The client throws "Font not set" for SetText / SetFormattedText on a FontString that has no font yet
-- (ApplyMono is what sets one here, and records the size). Stricter than the castbars mock on purpose:
-- a write before the font silently kills a pcall'd build on the real client.
do
    local plainSetText, plainSetFormatted = Region.SetText, Region.SetFormattedText
    function Region:SetText(s)
        if self._kind == "FontString" and self._fontSize == nil then error("Font not set", 2) end
        return plainSetText(self, s)
    end
    function Region:SetFormattedText(fmt, ...)
        if self._kind == "FontString" and self._fontSize == nil then error("Font not set", 2) end
        return plainSetFormatted(self, fmt, ...)
    end
end
function Region:SetVertTile(v) self._vertTile = v end
function Region:UnregisterAllEvents() self._events, self._unitEvents = {}, {} end
-- Records the call, and resolves a PLAIN boolean the way the client would. A secret is stored raw.
function Region:SetAlphaFromBoolean(b, t, f)
    self._fromBool, self._fromT, self._fromF = b, t, f
    self._fromCalls = (self._fromCalls or 0) + 1
    if type(b) == "boolean" then self._alpha = b and t or f end
end
-- Looping animations: the pulse. Group is the chevron mock's local class, reached through an instance.
do
    local g = UIParent:CreateAnimationGroup()
    local class = getmetatable(g).__index
    function class:SetLooping(mode) self.looping = mode end
end
-- OnUpdates that would actually be called: a script on a hidden frame (or under a hidden ancestor) is
-- never run by the client, so Stack A's permanently installed, hidden tickers do not count.
function __countOnUpdates()
    local n = 0
    for _, f in ipairs(__all) do
        if f._scripts and f._scripts.OnUpdate and f:IsVisible() then n = n + 1 end
    end
    return n
end
"""

CHECKS = r"""
local T = {}

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, tol, msg)
    if a == nil or math.abs(a - b) > (tol or 1e-6) then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function ok(v, msg) if not v then error(msg or "expected true", 2) end end

local function find(pred)
    for _, o in ipairs(__all) do if pred(o) then return o end end
end
local function countFrames() return #__all end

-- Boots the addon at screen height `h` (UI scale 1 in screen terms; Layout.Scale = h / 1440).
local function world(opts)
    opts = opts or {}
    __now = 100
    __ui(1)
    __physH = opts.physH or 768
    UIParent._h = opts.height or 1440
    UIParent._w = UIParent._h * 16 / 9
    ForeverSynthwaveDB = opts.db
    PlayerCastingBarFrame, TargetFrameSpellBar = CreateFrame("Frame"), CreateFrame("Frame")
    if opts.beforeLoad then opts.beforeLoad() end
    __load("Layout.lua", __layoutSrc)
    __load("CastBars.lua", __castSrc)
    if opts.stripView then FS.CastBars.SetView = nil end
    __load("Gunsight.lua", __gunsightSrc)
    __load("GunsightTape.lua", __tapeSrc)
    local W = { Tape = FS.GunsightTape, Gun = FS.Gunsight }
    if not opts.noLogin then
        __fireEvent("ADDON_LOADED", "ForeverSynthwave")
        __fireEvent("PLAYER_LOGIN")
    end
    W.you, W.tgt = FS.GunsightTape and FS.GunsightTape.you, FS.GunsightTape and FS.GunsightTape.tgt
    W.P, W.G = FS.playerCastBar, FS.targetCastBar            -- Stack A bars
    function W.fire(S, event, castID, interruptedBy)
        local f = S.events
        f._scripts.OnEvent(f, event, S.unit, castID, 1, interruptedBy)
    end
    function W.cast(unit, name, id, t0, secs, notInt)
        __now = t0 or 100
        __units[unit].cast = { name = name, tex = "icon", startMS = __now * 1000,
            endMS = (__now + secs) * 1000, castID = id or "C1", notInt = notInt or false }
        __units[unit].chan = nil
    end
    function W.secretCast(unit)
        __units[unit].cast = { name = __SECRET_NAME, tex = "icon", startMS = __SECRET, endMS = __SECRET,
            castID = __SECRET_ID, notInt = __SECRET_BOOL, secret = true }
        __units[unit].chan = nil
    end
    function W.endCast(unit) __units[unit].cast, __units[unit].chan = nil, nil end
    -- Runs the engine's OnUpdate and the readout ticker at clock t.
    function W.at(S, t)
        __now = t
        local fn = S.run.frame:GetScript("OnUpdate")
        if fn then fn(S.run.frame, 0) end
        local tf = S.ticker.frame or S.ticker
        local tick = tf._scripts.OnUpdate
        if tf._shown and tick then tick(tf, 0.2) end
    end
    function W.stepTo(S, from, to)
        local t = from
        while t < to do t = math.min(to, t + 1 / 30); W.at(S, t) end
    end
    function W.clean() eq(#__printed, 0, "no printed errors: " .. tostring(__printed[1])) end
    return W
end

local function litCount(run)
    local n = 0
    for i = 1, run.count do if run.segs[i].lit._shown then n = n + 1 end end
    return n
end
local function degraded(key)
    for _, k in ipairs(__degrades) do if k == key then return true end end
    return false
end
local function mockupK() return 1.28 * FS.Layout.Scale() end

-- ---- constants ------------------------------------------------------------------

function T.constants_match_the_mockup()
    world()
    local C = FS.GunsightTape.C
    eq(C.N, MU.N, "chevron count")
    -- ONE half width for both tapes: yours (the mockup's hw:10 on the player tape). The mockup's target
    -- default (hw 14) is deliberately NOT followed: it drew the target's chevrons to the plate edge, and
    -- Parker wants the two tapes alike (see the_target_track_is_inset_like_your_track).
    eq(C.HW, MU.HW_YOU, "half width is the player tape's")
    eq(C.CHEV_D, MU.CHEV_D); near(C.CHEV_T, MU.CHEV_T, 1e-9)
    eq(C.TICKS, MU.TICKS); eq(C.TICK_DIV, MU.TICK_DIV); eq(C.TICK_MID, MU.TICK_MID)
    eq(C.TICK_MID_LEN, MU.TICK_MID_LEN); eq(C.TICK_LEN, MU.TICK_LEN); near(C.TICK_A, MU.TICK_A, 1e-9)
    eq(C.FRAME_CHAMFER, MU.FRAME_CHAMFER)
    for i = 1, 3 do near(C.FRAME_FILL[i], MU.FRAME_FILL[i] / 255, 1e-9, "plate colour " .. i) end
    near(C.FRAME_FILL[4], MU.FRAME_FILL[4] * MU.FRAME_ALPHA, 1e-9, "plate alpha is the fill alpha times A(.3)")
    near(C.EDGE_A0, MU.EDGE_A0, 1e-9); near(C.EDGE_A1, MU.EDGE_A1, 1e-9)
    near(C.DIM, MU.DIM, 1e-9)
    near(C.PULSE_HZ, MU.PULSE_RATE / (2 * math.pi), 1e-9, "sin(clock * 7) is a 7 / 2pi Hz pulse")
    eq(C.KICK_W, MU.KICK_W); eq(C.KICK_H, MU.KICK_H); eq(C.KICK_CHAMFER, MU.KICK_CHAMFER)
    eq(C.KICK_TEXT_Y, MU.KICK_TEXT_Y); eq(C.KICK_TEXT_SIZE, MU.KICK_TEXT_SIZE)
    eq(C.KICK_DX, MU.KICK_DX); eq(C.KICK_DY, MU.KICK_DY)
    eq(C.LOCK_DX, MU.LOCK_DX); near(C.LOCK_DY, MU.LOCK_DY, 1e-9)
    eq(C.LOCK_W, MU.LOCK_W); eq(C.LOCK_H, MU.LOCK_H)
    for i = 1, 4 do near(C.LOCK_BODY[i], MU.LOCK_BODY[i], 1e-9, "padlock body " .. i) end
    for i = 1, 4 do near(C.LOCK_HOLE[i], MU.LOCK_HOLE[i], 1e-9, "padlock keyhole " .. i) end
    near(C.LOCK_SHACKLE.x0, MU.LOCK_SHACKLE[1], 1e-9); near(C.LOCK_SHACKLE.y1, MU.LOCK_SHACKLE[2], 1e-9)
    near(C.LOCK_SHACKLE.y0, MU.LOCK_SHACKLE[5] - MU.LOCK_SHACKLE[6], 1e-9, "the arc's top")
    near(C.LOCK_SHACKLE.x1, 2 * MU.LOCK_SHACKLE[4] - MU.LOCK_SHACKLE[1], 1e-9, "the arc mirrors about its centre")
end

function T.colours_are_the_mockups()
    world()
    local Th = FS.Theme
    local function hex(c) return string.format("%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)) end
    local tape = FS.GunsightTape
    eq(hex(tape.colors.cyan), MU.CSS.cyan:sub(2)); eq(hex(tape.colors.pink), MU.CSS.pink:sub(2))
    eq(hex(tape.colors.steel), MU.CSS.steel:sub(2)); eq(hex(tape.colors.bg), MU.CSS.bg:sub(2))
end

-- ---- build ----------------------------------------------------------------------

function T.builds_on_the_tape_anchors_and_registers_both_pieces()
    local W = world()
    W.clean()
    ok(W.you and W.tgt, "both tapes are exported")
    eq(W.you.key, "you"); eq(W.tgt.key, "tgt")
    local A = W.Gun.anchors
    for _, t in ipairs({ W.you, W.tgt }) do
        local anchor = t.key == "you" and A.tapeL or A.tapeR
        eq(t.anchor, anchor, t.key .. ": built on its anchor")
        eq(t.piece._points.TOPLEFT.rel, anchor); eq(t.piece._points.BOTTOMRIGHT.rel, anchor)
        eq(t.piece._points.TOPLEFT.relPoint, "TOPLEFT"); eq(t.piece._points.BOTTOMRIGHT.relPoint, "BOTTOMRIGHT")
        eq(t.piece:GetParent(), W.Gun.root, t.key .. ": a child of the gunsight root")
        eq(t.piece._shown, true, t.key .. ": shown (the piece is on)")
    end
    -- The registry owns the piece frames: switching a piece off hides exactly that tape.
    W.Gun.SetPiece("you", false, true)
    eq(W.you.piece._shown, false); eq(W.tgt.piece._shown, true)
    W.Gun.SetPiece("tgt", false, true)
    eq(W.tgt.piece._shown, false)
end

function T.the_run_is_a_vertical_engine_run_seated_from_the_anchor()
    local W = world()
    local G = W.Gun.G
    local k = mockupK()
    for _, t in ipairs({ W.you, W.tgt }) do
        local run = t.run
        eq(run.vertical, true, t.key .. ": vertical")
        eq(run.textures.fill, FS.ChevronCastBar.TEXTURES_UP.fill, "the up art")
        local hw = MU.HW_YOU        -- both tapes carry the player tape's chevron
        near(run.segW, 2 * hw * k, 1.2, t.key .. ": chevron box is 2 * hw image px across (to a pixel)")
        near(run.segLen, (MU.CHEV_D + MU.CHEV_T) * k, 1.2, t.key .. ": and d + tk deep")
        -- The pitch is the mockup's (BOT - TOP) / N, snapped to whole pixels the way the engine does it
        -- (layoutVertical): a +0.3 change in the design pitch must not slip through a tolerance.
        local want = math.max(1, math.floor((MU.base.BOT - MU.base.TOP) / MU.N * k / run.px + 0.5 + 1e-6)) * run.px
        near(run.pitch, want, 1e-9, t.key .. ": nested at the mockup pitch, whole pixels")
        near(FS.GunsightTape.C.PITCH, (MU.base.BOT - MU.base.TOP) / MU.N, 1e-9, "design pitch is the mockup's")
        eq(run.count, MU.N, t.key .. ": 20 chevrons")
        local p = run.frame._points.TOP
        eq(p.rel, t.anchor, "seated from the anchor"); eq(p.relPoint, "TOP")
        near(p.x, 0, 1e-9, "centred on the anchor"); near(p.y, -(MU.base.TOP - MU.base.FR_T) * k, 1e-6, "top chevron at TOP")
        eq(run.frame:GetParent(), t.host, "the run lives in the cast host")
    end
    -- The same art at the same size: the target's chevrons are as wide as yours.
    near(W.tgt.run.segW, W.you.run.segW, 1e-9, "20 wide on both tapes")
end

-- Parker, in game: "on my cast bar the chevrons don't extend to the edge and the target ones do. They
-- should look the same." Your tape is the approved look, so the target's track must sit in its tape
-- exactly as yours does: the same chevron size and pitch, the same inset from the side edges and the same
-- padding at both ends. The insets are measured off the built frames (anchor rect against the engine's own
-- chevron rects), not read back from a constant, so any way of drifting apart fails here.
function T.the_target_track_is_inset_like_your_track()
    local W = world()
    local function track(t)
        local run = t.run
        local p = run.frame._points.TOP
        local topOff = -p.y                                  -- anchor top to the run frame top
        local aw, ah = t.anchor:GetWidth(), t.anchor:GetHeight()
        local left = (aw - run.W) / 2 + run.xOff             -- anchor left to the chevron's left edge
        return {
            left = left, right = aw - left - run.segW,
            top = topOff + run.H - (run.origin + run.span),  -- anchor top to the top chevron's end
            bottom = ah - topOff - run.H + run.origin,       -- bottom chevron's start to the anchor bottom
        }
    end
    for _, case in ipairs({ { 1080, 1080 }, { 1440, 1440 }, { 720, 1080 }, { 2160, 2160 } }) do
        UIParent._h = case[1]; UIParent._w = case[1] * 16 / 9
        __physH = case[2]
        __fireEvent("UI_SCALE_CHANGED")
        local y, g = track(W.you), track(W.tgt)
        local what = " at " .. case[1] .. "/" .. case[2]
        local px = W.you.run.px
        -- Inset from each side edge: the same, to the one pixel the origin snap may move a column.
        near(g.left, y.left, px + 1e-6, "target left inset is yours" .. what)
        near(g.right, y.right, px + 1e-6, "target right inset is yours" .. what)
        near(g.top, y.top, px + 1e-6, "target end padding at the top is yours" .. what)
        near(g.bottom, y.bottom, px + 1e-6, "target end padding at the bottom is yours" .. what)
        -- And it is a real inset, not the edge to edge look the report was about (design px: your 5).
        local k = mockupK()
        ok(g.left >= 4 * k and g.right >= 4 * k, "target chevrons stop short of the tape edges" .. what .. ": "
            .. g.left .. " / " .. g.right .. " against " .. 4 * k)
    end
end

function T.twenty_chevrons_at_every_screen_height()
    local W = world()
    for _, h in ipairs({ 720, 1080, 1200, 1440, 2160 }) do
        for _, phys in ipairs({ 720, 1080, 1440, 2160 }) do
            UIParent._h = h; UIParent._w = h * 16 / 9
            __physH = phys
            __fireEvent("UI_SCALE_CHANGED")
            eq(W.you.run.count, MU.N, "you at " .. h .. " / " .. phys)
            eq(W.tgt.run.count, MU.N, "tgt at " .. h .. " / " .. phys)
            local kk = mockupK()
            for _, t in ipairs({ W.you, W.tgt }) do
                local want = math.max(1, math.floor((MU.base.BOT - MU.base.TOP) / MU.N * kk / t.run.px + 0.5 + 1e-6)) * t.run.px
                near(t.run.pitch, want, 1e-9, t.key .. " pitch at " .. h .. " / " .. phys)
            end
        end
    end
end

function T.ticks_stand_on_the_outer_edge()
    local W = world()
    local k = mockupK()
    local B = MU.base
    for _, t in ipairs({ W.you, W.tgt }) do
        local side = t.key == "you" and -1 or 1
        for layerKey, ticks in pairs(t.ticks) do
            eq(#ticks, MU.TICKS + 1, t.key .. "/" .. layerKey .. ": eleven ticks")
            for i, tex in ipairs(ticks) do
                local kk = i - 1
                local len = kk == MU.TICK_MID and MU.TICK_MID_LEN or MU.TICK_LEN
                near(tex._w, len * k, 1e-6, "tick " .. kk .. " length")
                local layer = t.layers[layerKey]
                local ty = B.BOT - kk * (B.BOT - B.TOP) / MU.TICK_DIV
                if side < 0 then
                    local p = tex._points.RIGHT
                    eq(p.rel, layer); eq(p.relPoint, "TOPLEFT", "left tape: ticks grow outward (left) from its left edge")
                    near(p.y, -(ty - B.FR_T) * k, 1e-6, "tick " .. kk .. " y")
                else
                    local p = tex._points.LEFT
                    eq(p.rel, layer); eq(p.relPoint, "TOPRIGHT", "right tape: ticks grow outward (right)")
                    near(p.y, -(ty - B.FR_T) * k, 1e-6, "tick " .. kk .. " y")
                end
                eq(tex._h >= 1, true, "a tick is at least a pixel thick")
            end
        end
    end
end

function T.rest_state_shows_the_dim_chevrons()
    local W = world()
    for _, t in ipairs({ W.you, W.tgt }) do
        eq(t.run:GetPhase(), "idle")
        eq(t.host._shown, true, t.key .. ": the host is always shown (the tape is never blank)")
        eq(t.run.frame._shown, true, t.key .. ": the idle row of chevrons")
        near(t.run.segs[1].dim._vc[4], MU.DIM, 1e-9, "dim chevrons at the mockup's .2")
        eq(t.castFrame._shown, false, t.key .. ": nothing cast-only at rest")
        for _, s in ipairs(t.strips) do eq(s._shown, false, "strips hidden at rest") end
    end
    -- Stack A is retired: its frames are hidden and its events are not read any more.
    eq(W.P.frame._shown, false); eq(W.G.frame._shown, false)
    eq(W.P.events._scripts.OnEvent, nil, "Stack A player events retired")
    eq(W.G.events._scripts.OnEvent, nil, "Stack A target events retired")
end

-- ---- player tape ----------------------------------------------------------------

function T.a_player_cast_fills_the_run_and_locks_in()
    local W = world()
    local S = W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "run", "plain times: the engine run")
    eq(W.you.run:GetPhase(), "cast")
    eq(litCount(W.you.run), 0, "nothing lit at t = 0")
    W.stepTo(S, 100, 101.25)
    near(W.you.run:GetProgress(), 0.5, 0.02, "half way")
    local half = litCount(W.you.run)
    ok(half > 3 and half < W.you.run.count, "some chevrons lit at half: " .. half)
    W.stepTo(S, 101.25, 102.5)
    ok(litCount(W.you.run) >= W.you.run.count - 1, "all lit at the end")
    W.fire(S, "UNIT_SPELLCAST_STOP", "C1")
    eq(W.you.run:GetPhase(), "hold", "castID matched: the lock-in")
    W.stepTo(S, 102.5, 104.2)
    eq(W.you.run:GetPhase(), "idle", "back to the dim row")
    eq(S.mode, nil)
    eq(W.you.host._shown, true)
    W.clean()
end

function T.a_player_interrupt_plays_the_engines_outage()
    local W = world()
    local S = W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 101)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W.you.run:GetPhase(), "intr", "the power outage")
    ok(W.you.run.flareTarget ~= nil, "the frame outline flares with it")
    W.stepTo(S, 101, 102.4)
    eq(W.you.run:GetPhase(), "idle", "and ends in the idle row")
    W.clean()
end

-- ---- the verdict hook (the info box's INTERRUPTED look) --------------------------------------

-- Replaces a view bar's hook with a recorder; returns the list of kinds it was called with.
local function recordVerdicts(S)
    local calls = {}
    S.onVerdict = function(self, kind) calls[#calls + 1] = { self = self, kind = kind } end
    return calls
end

function T.the_alpha_0_sinks_have_no_verdict_hook_and_an_interrupt_still_plays()
    -- This harness loads no GunsightBoxes.lua: the tapes fall back to hidden sinks, which carry no hook
    -- (gunsightboxes-harness.py checks the real box's hook reaches the bar table).
    local W = world()
    eq(W.you.S.onVerdict, nil); eq(W.tgt.S.onVerdict, nil)
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(W.you.S, "UNIT_SPELLCAST_START"); W.stepTo(W.you.S, 100, 101)
    W.fire(W.you.S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W.you.run:GetPhase(), "intr", "an interrupt without a hook still plays")
    W.clean()
end

function T.an_interrupt_calls_the_hook_once_after_the_readout_froze_and_before_the_outage()
    local W = world()
    local S = W.you.S
    local calls = {}
    S.onVerdict = function(self, kind)
        calls[#calls + 1] = { self = self, kind = kind, phase = W.you.run:GetPhase(), ticker = S.ticker.frame._shown }
    end
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 101)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(#calls, 1, "called once"); eq(calls[1].kind, "interrupt"); eq(calls[1].self, S, "with the bar table first")
    eq(calls[1].phase, "cast", "before the engine's outage starts")
    ok(not calls[1].ticker, "after the readout froze (the ticker is off)")
    eq(W.you.run:GetPhase(), "intr")
    W.stepTo(S, 101, 102.4)
    eq(#calls, 1, "and nothing more during the outage")
    W.clean()
end

function T.every_interrupt_route_calls_the_hook_and_nothing_else_does()
    local W = world()
    local S = W.you.S
    local calls = recordVerdicts(S)
    -- FAILED with a matching castID
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 100.5)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_FAILED", "C1"); W.stepTo(S, 100.5, 103)
    eq(#calls, 1, "FAILED routes to the interrupt"); eq(calls[1].kind, "interrupt")
    -- a kicked channel (interruptedBy present)
    __now = 110
    __units.player.chan = { name = "Mind Flay", tex = "icon", startMS = 110000, endMS = 113000, notInt = false }; __units.player.cast = nil
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START"); W.stepTo(S, 110, 111)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_CHANNEL_STOP", "C1", "Kurak"); W.stepTo(S, 111, 114)
    eq(#calls, 2, "a kicked channel"); eq(calls[2].kind, "interrupt")
    -- a completed cast: no verdict call (the mockup's box has no success look)
    W.cast("player", "Fear", "C3", 120, 1.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 120, 121.5)
    W.fire(S, "UNIT_SPELLCAST_STOP", "C3"); W.stepTo(S, 121.5, 124)
    eq(#calls, 2, "a success sends nothing")
    -- a channel that ran out, and a cast that quietly ends: nothing either
    __now = 130
    __units.player.chan = { name = "Mind Flay", tex = "icon", startMS = 130000, endMS = 133000, notInt = false }; __units.player.cast = nil
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START"); W.stepTo(S, 130, 133)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_CHANNEL_STOP", "C1"); W.stepTo(S, 133, 136)
    eq(#calls, 2, "a natural channel end sends nothing")
    W.clean()
end

function T.a_throwing_hook_never_stops_the_verdict()
    -- CastBars' pcall around onVerdict: without it the throw escapes InterruptCast before the engine's
    -- Interrupt() runs, so the outage never plays (and the event handler prints the error).
    local W = world()
    local S = W.you.S
    local called = 0
    S.onVerdict = function() called = called + 1; error("hook blew up") end
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(S, "UNIT_SPELLCAST_START"); W.stepTo(S, 100, 101)
    W.fire(S, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(called, 1, "the hook really ran and threw")
    eq(W.you.run:GetPhase(), "intr", "the outage plays anyway")
    W.stepTo(S, 101, 102.4)
    eq(W.you.run:GetPhase(), "idle")
    W.clean()             -- and no error escaped to the event handler's report
    -- a kicked channel takes the same route
    __now = 110
    __units.player.chan = { name = "Mind Flay", tex = "icon", startMS = 110000, endMS = 113000, notInt = false }; __units.player.cast = nil
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START"); W.stepTo(S, 110, 111)
    W.endCast("player"); W.fire(S, "UNIT_SPELLCAST_CHANNEL_STOP", "C1", "Kurak")
    eq(called, 2, "the kicked channel called it too")
    eq(W.you.run:GetPhase(), "intr", "and its outage plays")
    W.clean()
end

function T.stack_a_bars_have_no_verdict_hook_and_an_interrupt_runs_as_before()
    local W = world({ stripView = true })
    eq(W.P.onVerdict, nil); eq(W.G.onVerdict, nil)
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5); W.fire(W.P, "UNIT_SPELLCAST_START"); W.stepTo(W.P, 100, 101)
    W.fire(W.P, "UNIT_SPELLCAST_INTERRUPTED", "C1")
    eq(W.P.run:GetPhase(), "intr", "Stack A plays its outage")
    W.stepTo(W.P, 101, 102.4)
    W.clean()
end

function T.the_player_tape_has_one_colour_and_no_interruptible_layers()
    local W = world()
    ok(W.you.layers.base and not W.you.layers.pink and not W.you.layers.steel, "a single cyan layer")
    eq(W.you.S.shield.SetAlphaFromBoolean, nil, "no alpha-from-boolean on the player's shield stand-in")
    -- A plain false flag on your own cast is harmless.
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5, false)
    W.fire(W.you.S, "UNIT_SPELLCAST_START")
    W.clean()
end

-- ---- target tape ----------------------------------------------------------------

function T.a_secret_target_cast_is_engine_timed_on_two_stacked_vertical_strips()
    local W = world()
    local S = W.tgt.S
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "strip", "the strip path")
    eq(#W.tgt.strips, 2, "two stacked fills")
    for _, s in ipairs(W.tgt.strips) do
        eq(s._shown, true, "shown")
        ok(s._timer ~= nil, "SetTimerDuration was handed the duration object")
        eq(s._orientation, "VERTICAL", "a vertical bar")
        eq(s._fill._vertTile, true, "the fill tiles along the run")
    end
    eq(W.tgt.strips[1]._timer, W.tgt.strips[2]._timer, "both fills run on the same duration object")
    eq(W.tgt.run:GetPhase(), "idle", "the engine run is not driving a secret cast")
    -- pink first, steel second: the colours the mockup draws.
    local pink, steel = FS.GunsightTape.colors.pink, FS.GunsightTape.colors.steel
    near(W.tgt.strips[1]._fill._vc[1], pink[1], 1e-9); near(W.tgt.strips[2]._fill._vc[1], steel[1], 1e-9)
    -- The name goes to a FontString untouched; the timer text takes the duration object's numbers.
    eq(W.tgt.name._text, __SECRET_NAME, "a secret name reaches SetText untouched")
    -- End of cast: the verdict goes idle and hides the fills.
    W.endCast("target")
    W.fire(S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.clean()
    eq(S.mode, nil)
    for _, s in ipairs(W.tgt.strips) do eq(s._shown, false) end
end

function T.a_plain_target_cast_is_engine_timed_too()
    local W = world()
    local S = W.tgt.S
    W.cast("target", "Fear", "C1", 100, 1.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "strip", "the mockup draws the target tape engine timed always")
    ok(W.tgt.strips[1]._timer ~= nil, "SetTimerDuration")
    eq(W.tgt.run:GetPhase(), "idle", "no engine run on the target tape")
end

function T.the_interruptible_flag_only_reaches_alpha_from_boolean()
    local W = world()
    local S = W.tgt.S
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    local fb = W.tgt.fb
    eq(#fb.pink >= 3 and #fb.steel >= 3, true, "edge layer, strip and tag on each side")
    for _, r in ipairs(fb.steel) do
        eq(r._fromBool, __SECRET_BOOL, "steel: the secret flag, untouched"); eq(r._fromT, 1); eq(r._fromF, 0)
    end
    for _, r in ipairs(fb.pink) do
        eq(r._fromBool, __SECRET_BOOL, "pink: the same flag"); eq(r._fromT, 0); eq(r._fromF, 1)
    end
    -- the two pieces of text-free chrome that mark the cast: KICK is pink, the padlock steel
    ok(find(function(o) return o == W.tgt.kick end), "a KICK tag"); ok(W.tgt.padlock, "a padlock")
    local function has(list, v) for _, r in ipairs(list) do if r == v then return true end end return false end
    ok(has(fb.pink, W.tgt.kick) and not has(fb.steel, W.tgt.kick), "KICK follows the interruptible side")
    ok(has(fb.steel, W.tgt.padlock) and not has(fb.pink, W.tgt.padlock), "the padlock follows the other side")
end

function T.a_plain_flag_flips_the_stacked_fills()
    local W = world()
    local S = W.tgt.S
    W.cast("target", "Fear", "C1", 100, 1.5, true)      -- notInterruptible
    W.fire(S, "UNIT_SPELLCAST_START")
    for _, r in ipairs(W.tgt.fb.steel) do eq(r._alpha, 1, "steel up") end
    for _, r in ipairs(W.tgt.fb.pink) do eq(r._alpha, 0, "pink down") end
    W.cast("target", "Mending", "C2", 100, 2, false)
    W.fire(S, "UNIT_SPELLCAST_START")
    for _, r in ipairs(W.tgt.fb.steel) do eq(r._alpha, 0, "steel down") end
    for _, r in ipairs(W.tgt.fb.pink) do eq(r._alpha, 1, "pink up") end
    -- Between casts the tape is the neutral (steel) look, never a kickable pink one.
    W.endCast("target")
    W.fire(S, "UNIT_SPELLCAST_STOP", "C2")
    for _, r in ipairs(W.tgt.fb.steel) do eq(r._alpha, 1, "idle: steel") end
    for _, r in ipairs(W.tgt.fb.pink) do eq(r._alpha, 0, "idle: no pink") end
    W.clean()
end

function T.kick_and_padlock_exist_only_while_a_cast_is_live()
    local W = world()
    local S = W.tgt.S
    eq(W.tgt.castFrame._shown, false, "hidden at rest")
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(W.tgt.castFrame._shown, true, "shown with the cast")
    ok(W.tgt.kick:GetParent() == W.tgt.castFrame and W.tgt.padlock:GetParent() == W.tgt.castFrame, "inside the cast-only frame")
    W.endCast("target")
    W.fire(S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    eq(W.tgt.castFrame._shown, false, "gone with it")
    -- a target change drops the cast
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(W.tgt.castFrame._shown, true)
    W.endCast("target")
    W.fire(S, "PLAYER_TARGET_CHANGED")
    eq(W.tgt.castFrame._shown, false)
    W.clean()
end

function T.kick_and_padlock_sit_where_the_mockup_puts_them()
    local W = world()
    local k = mockupK()
    local kp = W.tgt.kick._points.TOPLEFT
    eq(kp.rel, W.Gun.anchors.boxR); eq(kp.relPoint, "TOPRIGHT")
    near(kp.x, -MU.KICK_DX * k, 1e-6, "kx = BOXR.x + BOXR.w - 40"); near(kp.y, MU.KICK_DY * k, 1e-6, "ky = BOXR.y - 8")
    near(W.tgt.kick._w, MU.KICK_W * k, 1e-6); near(W.tgt.kick._h, MU.KICK_H * k, 1e-6)
    local lp = W.tgt.padlock._points.TOPLEFT
    eq(lp.rel, W.tgt.kick); eq(lp.relPoint, "TOPLEFT")
    near(lp.x, MU.LOCK_DX * k, 1e-6); near(lp.y, MU.LOCK_DY * k, 1e-6, "the padlock sits half a unit above ky")
    near(W.tgt.padlock._w, MU.LOCK_W * k, 1e-6); near(W.tgt.padlock._h, MU.LOCK_H * k, 1e-6)
    eq(W.tgt.kick.label._text, "KICK")
    ok(W.tgt.kick.label._fontSize >= 6, "a readable size")
end

function T.kick_and_padlock_ride_the_grown_box_top_by_the_built_boxs_grow()
    -- ky = BOXR.y - 8, then ky += BR.y - BOXR.y (option B: the box grows up by KICK_GROW). The rise is the BUILT
    -- box's own `grow`; this harness builds no GunsightBoxes.lua, so a stand-in box carries it (the real
    -- file's constant is pinned against the mockup in the static checks, and in gunsightboxes-harness).
    local W = world()
    local k = mockupK()
    near(W.tgt.kick._points.TOPLEFT.y, MU.KICK_DY * k, 1e-6, "no built box (the sink fallback): the tag stays at the anchor")
    W.tgt.box = { grow = MU.KICK_GROW }
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    k = mockupK()
    local kp = W.tgt.kick._points.TOPLEFT
    near(kp.x, -MU.KICK_DX * k, 1e-6, "the x is untouched")
    near(kp.y, (MU.KICK_DY + MU.KICK_GROW) * k, 1e-6, "ky = BOXR.y - 16 in option B")
    local lp = W.tgt.padlock._points.TOPLEFT
    eq(lp.rel, W.tgt.kick); near(lp.y, MU.LOCK_DY * k, 1e-6, "the padlock rides the tag")
    W.clean()
end

function T.the_pulse_runs_only_with_the_cast()
    local W = world()
    local S = W.tgt.S
    local pulse = W.tgt.pulse
    ok(pulse, "a looping alpha animation, no OnUpdate")
    ok(not pulse.playing, "not playing at rest")
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(pulse.playing, true, "pulses while the cast shows")
    W.endCast("target")
    W.fire(S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    eq(pulse.playing, false, "stops at idle")
end

-- ---- the target tape follows the target ------------------------------------------------

local function noTarget() __units.target.exists = false end

function T.the_target_tape_is_hidden_with_no_target_and_shown_with_one()
    local W = world({ beforeLoad = noTarget })
    local t = W.tgt
    ok(t.gate, "the target tape has a visibility layer (t.gate)")
    eq(t.gate:GetFrameLevel(), t.piece:GetFrameLevel(), "the layer adds no stacking level over the piece frame")
    eq(t.gate._shown, false, "no target at build: the layer is down")
    for _, part in ipairs({ t.host, t.castFrame, t.layers.pink, t.layers.steel, t.strips[1], t.reveals[1].frame, t.run.frame }) do
        eq(part:IsVisible(), false, "nothing of the tape shows")
    end
    eq(t.piece._shown, true, "the piece frame itself is left to the piece toggle")
    eq(W.you.host:IsVisible(), true, "your tape is not gated")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(t.gate._shown, true, "a target shows it")
    eq(t.host:IsVisible(), true); eq(t.layers.pink:IsVisible(), true); eq(t.layers.steel:IsVisible(), true)
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(t.host:IsVisible(), false, "the target dropped: hidden again")
    __units.target.exists = true; __fireEvent("PLAYER_ENTERING_WORLD")
    eq(t.host:IsVisible(), true, "PLAYER_ENTERING_WORLD re-reads the target")
    W.clean()
    eq(__countOnUpdates(), 0, "the layer adds no OnUpdate")
end

function T.a_secret_target_answer_keeps_the_target_tape_shown()
    -- The rule itself (IsSecret asked before any truth test, missing UnitExists) is pinned once in
    -- theme-harness.py; this proves the tape goes through it. The mock calls the plain false UnitExists
    -- returns "secret": a truth test would keep the tape hidden.
    local W = world({ beforeLoad = noTarget })
    eq(W.tgt.host:IsVisible(), false, "setup: no target, hidden")
    local plain = FS.IsSecret
    FS.IsSecret = function(v) return v == false or plain(v) end
    __fireEvent("PLAYER_TARGET_CHANGED")
    eq(W.tgt.host:IsVisible(), true, "a value IsSecret flags keeps it shown")
    W.clean()
end

function T.the_target_layer_composes_with_the_tgt_piece_toggle()
    local W = world({ beforeLoad = noTarget })
    W.Gun.SetPiece("tgt", false, true)
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(W.tgt.piece._shown, false, "a target never turns the user's off piece on")
    eq(W.tgt.host:IsVisible(), false, "so the tape stays hidden")
    W.Gun.SetPiece("tgt", true, true)
    eq(W.tgt.host:IsVisible(), true, "piece on and a target: visible")
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(W.tgt.host:IsVisible(), false, "piece on and no target: hidden")
    eq(W.tgt.piece._shown, true, "the piece itself is untouched")
end

function T.a_target_cast_arriving_after_the_re_show_works_and_a_new_target_keeps_the_cast_machine_intact()
    local W = world({ beforeLoad = noTarget })
    local t, S = W.tgt, W.tgt.S
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    W.clean()
    W.cast("target", "Fear", "C1", 100, 1.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "strip", "a cast arriving after the re-show works")
    eq(t.strips[1]:IsVisible(), true, "the strip is on screen"); ok(t.strips[1]._timer ~= nil, "with its timer")
    eq(t.castFrame:IsVisible(), true, "and the cast tag frame shows")
    -- the target drops mid cast: hidden, and the machine ends the cast through its own PLAYER_TARGET_CHANGED path
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    W.clean()
    eq(t.host:IsVisible(), false, "no target: hidden")
    -- a target again, a new cast
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    W.cast("target", "Shadow Bolt", "C2", 110, 2.5, false)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "strip", "the next cast starts normally"); eq(t.castFrame:IsVisible(), true)
end

function T.a_rescale_does_not_re_show_a_hidden_target_tape()
    local W = world({ beforeLoad = noTarget })
    for _, h in ipairs({ 1080, 1440, 720 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
        eq(W.tgt.gate._shown, false, "still hidden at " .. h)
        eq(W.tgt.host:IsVisible(), false)
    end
    W.clean()
end

-- The client has no rect for a frame under a hidden ancestor (GetLeft / GetBottom answer nil), so the
-- chevron origin snap cannot run while the target tape is hidden. A rescale then leaves the unsnapped
-- seat, and the layer must lay the tape out again when it shows.
function T.a_rescale_while_the_target_tape_is_hidden_is_laid_out_again_when_it_shows()
    local Region = getmetatable(UIParent)
    local rectL, rectB = Region.GetLeft, Region.GetBottom
    function Region:GetLeft() if not self:IsVisible() then return nil end return rectL(self) or 0.37 end
    function Region:GetBottom() if not self:IsVisible() then return nil end return rectB(self) or 0.37 end
    local function rescale()
        UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
        __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
    end
    -- the reference: a tape that was on screen for the same rescale
    local Wref = world()
    rescale()
    local refOrigin, refX = Wref.tgt.run.origin, Wref.tgt.run.xOff
    -- the case: hidden for the rescale, then a target
    local W = world({ beforeLoad = noTarget })
    local t = W.tgt
    rescale()
    local hiddenOrigin, hiddenX = t.run.origin, t.run.xOff
    ok(hiddenOrigin ~= refOrigin or hiddenX ~= refX, "the mock rect makes the hidden-frame snap loss observable")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    near(t.run.origin, refOrigin, 1e-9, "the chevron origin is snapped again once the tape shows")
    near(t.run.xOff, refX, 1e-9, "and so is the column")
    -- a second show without a rescale in between lays out nothing again
    local layouts = 0
    local layout = t.run.Layout
    t.run.Layout = function(...) layouts = layouts + 1; return layout(...) end
    __units.target.exists = false; __fireEvent("PLAYER_TARGET_CHANGED")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(layouts, 0, "the re-layout is owed only after a rescale that happened while hidden")
    W.clean()
end

-- The dirty mark follows real visibility (IsVisible, the gate and every ancestor), not the gate's own flag:
-- a rescale under a hidden or fading tgt piece frame has no rects either. Only a re-layout that ran while the
-- tape was visible clears it, and the piece showing again is one of the moments that re-lays it out.
local function hiddenSnapMock()
    local Region = getmetatable(UIParent)
    local rectL, rectB = Region.GetLeft, Region.GetBottom
    function Region:GetLeft() if not self:IsVisible() then return nil end return rectL(self) or 0.37 end
    function Region:GetBottom() if not self:IsVisible() then return nil end return rectB(self) or 0.37 end
end
local function rescale1080()
    UIParent._h = 1080; UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED"); __fireEvent("DISPLAY_SIZE_CHANGED")
end

function T.a_rescale_while_the_tgt_piece_is_off_is_laid_out_again_when_the_piece_shows()
    hiddenSnapMock()
    local Wref = world()
    rescale1080()
    local refOrigin, refX = Wref.tgt.run.origin, Wref.tgt.run.xOff
    local W = world()                                   -- a target, the gate is shown
    local t = W.tgt
    W.Gun.SetPiece("tgt", false, true)
    eq(t.gate._shown, true, "setup: the gate itself is up, the piece frame above it is down")
    rescale1080()
    ok(t.dirty, "a rescale under the hidden piece marks the tape dirty")
    ok(t.run.origin ~= refOrigin or t.run.xOff ~= refX, "the mock rect makes the lost snap observable")
    W.Gun.SetPiece("tgt", true, true)
    near(t.run.origin, refOrigin, 1e-9, "the piece showing lays the tape out again: origin snapped")
    near(t.run.xOff, refX, 1e-9, "and the column")
    eq(t.dirty, nil, "the visible re-layout cleared the mark")
    W.clean()
end

function T.the_gate_showing_under_a_hidden_piece_does_not_clear_the_dirty_mark()
    hiddenSnapMock()
    local Wref = world()
    rescale1080()
    local refOrigin, refX = Wref.tgt.run.origin, Wref.tgt.run.xOff
    local W = world({ beforeLoad = noTarget })
    local t = W.tgt
    W.Gun.SetPiece("tgt", false, true)
    rescale1080()
    ok(t.dirty, "setup: dirty (gate and piece both down)")
    __units.target.exists = true; __fireEvent("PLAYER_TARGET_CHANGED")
    eq(t.gate._shown, true, "the gate is up")
    eq(t.gate:IsVisible(), false, "but not visible: the piece frame is down")
    ok(t.dirty, "so the owed re-layout is still owed")
    W.Gun.SetPiece("tgt", true, true)
    near(t.run.origin, refOrigin, 1e-9, "the piece showing runs it: origin snapped")
    near(t.run.xOff, refX, 1e-9, "and the column")
    eq(t.dirty, nil, "and only now is the mark cleared")
    W.clean()
end

function T.a_failed_build_takes_the_target_layer_listener_down()
    local W = world({ noLogin = true })
    local Region = getmetatable(UIParent)
    local setScript, listener = Region.SetScript, nil
    function Region:SetScript(k, fn)
        if k == "OnEvent" and self._events and self._events.PLAYER_TARGET_CHANGED
            and self._parent and self._parent._name == "ForeverSynthwaveGunsightTape_tgt" then
            listener = self
            error("SetScript failed")                        -- the step right after the two registrations
        end
        return setScript(self, k, fn)
    end
    __fireEvent("ADDON_LOADED", "ForeverSynthwave")
    __fireEvent("PLAYER_LOGIN")
    Region.SetScript = setScript
    W.clean()
    ok(listener, "the target layer's listener was built and registered before the failure")
    eq(next(listener._events), nil, "HideBuilt unregistered what the failed build had registered")
    eq(FS.GunsightTape.tgt, nil, "the build failed as a whole")
    ok(degraded("gunsighttape_build"), "and said so")
end

-- ---- the target's chevron reveal ------------------------------------------------

-- The timer-driven strip stays as the clock but draws nothing; a clipped column of the run's own lit
-- chevrons is revealed up to the strip fill's top edge (pure anchor geometry, nothing secret is read).
local function startTargetCast(W, secret)
    if secret then W.secretCast("target") else W.cast("target", "Fear", "C1", 100, 1.5, false) end
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
end
local function revealFor(W, color)
    for _, rv in ipairs(W.tgt.reveals or {}) do
        if rv.color == color then return rv end
    end
end

function T.the_target_strip_is_an_invisible_clock_and_the_bar_stays_up()
    local W = world()
    eq(#W.tgt.reveals, 2, "one reveal per strip (pink and steel)")
    for _, secret in ipairs({ true, false }) do
        startTargetCast(W, secret)
        W.clean()
        for _, s in ipairs(W.tgt.strips) do
            eq(s._shown, true, "the bar is still shown, so the engine keeps updating it")
            ok(s._timer ~= nil, "and still timer driven")
            eq(s._fill._alpha, 0, "but its own fill draws nothing")
        end
        W.endCast("target")
        W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", secret and __SECRET_ID or "C1")
    end
    -- the player tape keeps its plain strip untouched: no reveal there
    eq(W.you.reveals, nil, "the player tape has no reveal")
end

function T.the_reveal_is_a_clipped_frame_riding_the_strip_fill_top()
    local W = world()
    for _, rv in ipairs(W.tgt.reveals) do
        eq(rv.clip._clips, true, "SetClipsChildren on the reveal frame")
        local p = rv.clip._points
        eq(p.TOP.rel, rv.strip._fill, "TOP rides the strip's fill texture"); eq(p.TOP.relPoint, "TOP")
        eq(p.BOTTOMLEFT.rel, rv.strip, "bottom on the run column's bottom (where the fill starts)")
        eq(p.BOTTOMLEFT.relPoint, "BOTTOMLEFT"); eq(p.BOTTOMRIGHT.relPoint, "BOTTOMRIGHT")
        eq(p.BOTTOMRIGHT.rel, rv.strip)
        near(p.BOTTOMLEFT.x, -W.tgt.run.capW, 1e-6, "widened across by the caret width, like the engine's clip")
        near(p.BOTTOMRIGHT.x, W.tgt.run.capW, 1e-6)
        eq(rv.host:GetParent(), rv.clip, "the chevrons live on a child frame of the clipping frame")
    end
end

function T.the_strip_spans_exactly_the_chevron_run_so_the_top_chevron_lights_at_the_end()
    local W = world()
    local run = W.tgt.run
    for _, s in ipairs(W.tgt.strips) do
        local bl, tr = s._points.BOTTOMLEFT, s._points.TOPRIGHT
        eq(bl.rel, run.frame); eq(bl.relPoint, "BOTTOMLEFT"); near(bl.y, run.origin, 1e-9, "from the first chevron's bottom")
        eq(tr.rel, run.frame); eq(tr.relPoint, "BOTTOMRIGHT"); near(tr.y, run.origin + run.span, 1e-9, "to the last chevron's top")
        ok(s._scale == nil or s._scale == 1, "no tile scale: the tile is not drawn")
    end
end

function T.reveal_chevrons_sit_on_the_runs_seg_rects_at_two_scales_and_heights()
    local W = world()
    local art = FS.ChevronCastBar.TEXTURES_UP
    for _, case in ipairs({ { 1440, 1440 }, { 1080, 2160 }, { 720, 1080 } }) do
        UIParent._h = case[1]; UIParent._w = case[1] * 16 / 9
        __physH = case[2]
        __fireEvent("UI_SCALE_CHANGED")
        local run = W.tgt.run
        for _, rv in ipairs(W.tgt.reveals) do
            eq(#rv.lit, MU.N, "one lit chevron per segment"); eq(#rv.dim, MU.N)
            for i = 1, run.count do
                local seg = run.segs[i]
                for _, kind in ipairs({ "lit", "dim" }) do
                    local tex = rv[kind][i]
                    local p = tex._points.BOTTOMLEFT
                    eq(p.rel, rv.frame, "seated off the reveal's own frame")
                    eq(p.relPoint, "BOTTOMLEFT")
                    near(p.x, run.xOff, 1e-9, kind .. " " .. i .. " x at " .. case[1] .. "/" .. case[2])
                    near(p.y, seg.x0, 1e-9, kind .. " " .. i .. " y: the run's whole pixel pitch and origin")
                    near(tex._w, run.segW, 1e-9, kind .. " width"); near(tex._h, run.segLen, 1e-9, kind .. " depth")
                    near(p.x, seg.lit._points.BOTTOMLEFT.x, 1e-9, "the very seat the run's own chevron has")
                    near(p.y, seg.lit._points.BOTTOMLEFT.y, 1e-9)
                    eq(tex._texture, art.fill, kind .. ": the engine's up chevron art")
                    eq(tex._shown, true)
                end
            end
            near(rv.dim[1]._vc[4], MU.DIM, 1e-9, "the dim row stays at the mockup's .2")
            eq(rv.lit[1]._vc[4], 1, "lit chevrons are fully opaque")
        end
    end
end

-- Every route that ends a secret target cast must take the reveal down with the strip. Each case starts
-- from a fresh secret cast; the event is what ends it.
function T.the_reveal_is_shown_and_hidden_with_the_strip()
    local W = world()
    local S = W.tgt.S
    for _, rv in ipairs(W.tgt.reveals) do eq(rv.frame._shown, false, "nothing at rest (the run's idle row shows)") end
    for _, event in ipairs({ "UNIT_SPELLCAST_STOP", "PLAYER_TARGET_CHANGED", "PLAYER_ENTERING_WORLD",
        "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_FAILED" }) do
        startTargetCast(W, true)
        for _, rv in ipairs(W.tgt.reveals) do eq(rv.frame._shown, true, "up during the cast, before " .. event) end
        W.endCast("target")
        W.fire(S, event, __SECRET_ID)
        for _, rv in ipairs(W.tgt.reveals) do eq(rv.frame._shown, false, "gone after " .. event) end
    end
    W.clean()
end

function T.the_caret_caps_the_reveal_top_edge_inside_the_run()
    local W = world()
    local art = FS.ChevronCastBar.TEXTURES_UP
    local run = W.tgt.run
    for _, rv in ipairs(W.tgt.reveals) do
        local c = rv.caret
        local p = c._points.BOTTOMLEFT
        eq(c._points.TOPLEFT, nil, "it hangs from no top anchor: its bottom is the edge")
        eq(p.rel, rv.clip, "anchored to the fill's clip frame"); eq(p.relPoint, "TOPLEFT")
        near(p.y, 0, 1e-9, "its bottom edge sits on the fill's top edge, not under it")
        near(p.x, run.capX, 1e-9, "centred on the column, like the engine's caret")
        near(c._w, run.capW, 1e-9); near(c._h, run.capH, 1e-9)
        -- rv.clip's left edge is the run's left edge widened by m = capW, and capX includes that m, so in
        -- run.frame coordinates the caret's centre must be the chevron column's centre.
        near((p.x - run.capW) + run.capW / 2, run.xOff + run.segW / 2, 1e-6,
            "the caret is centred on the chevron column in run coordinates (the +m is kept)")
        eq(c._texture, art.outline, "the run's outline caret art")
        eq(c._vc[1], rv.color[1], "tinted like its fill")
        -- not under the fill's clip (the clip would cut the raised caret away), but on its own clip ...
        local up = c:GetParent()
        eq(up, rv.caretHost, "on its own host frame")
        local cc = up:GetParent()
        eq(cc, rv.caretClip, "under its own clipping frame")
        -- the caret clip is a child of the reveal frame (hides with it, takes its tone alpha)
        eq(cc:GetParent(), rv.frame, "the caret clip is a child of the reveal frame")
        eq(cc._clips, true, "it clips its children")
        -- spanning the run vertically, widened across by the caret width like the engine's own clip
        local q = cc._points
        eq(q.TOPLEFT.rel, run.frame); eq(q.TOPLEFT.relPoint, "TOPLEFT")
        near(q.TOPLEFT.x, -run.capW, 1e-6); near(q.TOPLEFT.y, 0, 1e-9)
        eq(q.BOTTOMRIGHT.rel, run.frame); eq(q.BOTTOMRIGHT.relPoint, "BOTTOMRIGHT")
        near(q.BOTTOMRIGHT.x, run.capW, 1e-6); near(q.BOTTOMRIGHT.y, 0, 1e-9)
        -- the host fills the caret clip so the caret's anchor math is unchanged
        eq(up._points.TOPLEFT.rel, cc); eq(up._points.BOTTOMRIGHT.rel, cc)
    end
end

function T.the_interruptible_flag_reaches_the_reveal_chevrons()
    local W = world()
    local pink, steel = FS.GunsightTape.colors.pink, FS.GunsightTape.colors.steel
    local rp, rs = revealFor(W, pink), revealFor(W, steel)
    ok(rp and rs and rp ~= rs, "a pink and a steel reveal")
    near(rp.lit[1]._vc[1], pink[1], 1e-9); near(rp.lit[1]._vc[3], pink[3], 1e-9)
    near(rs.lit[1]._vc[1], steel[1], 1e-9); near(rs.dim[1]._vc[1], steel[1], 1e-9)
    local function has(list, v) for _, r in ipairs(list) do if r == v then return true end end return false end
    ok(has(W.tgt.fb.pink, rp.frame) and not has(W.tgt.fb.steel, rp.frame), "pink reveal is in fb.pink")
    ok(has(W.tgt.fb.steel, rs.frame) and not has(W.tgt.fb.pink, rs.frame), "steel reveal is in fb.steel")
    startTargetCast(W, true)
    eq(rp.frame._fromBool, __SECRET_BOOL, "the secret flag reaches the pink reveal untouched")
    eq(rp.frame._fromT, 0); eq(rp.frame._fromF, 1)
    eq(rs.frame._fromBool, __SECRET_BOOL); eq(rs.frame._fromT, 1); eq(rs.frame._fromF, 0)
    W.cast("target", "Fear", "C1", 100, 1.5, true)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(rs.frame._alpha, 1, "not interruptible: steel reveal up"); eq(rp.frame._alpha, 0, "pink reveal down")
    W.cast("target", "Mending", "C2", 100, 2, false)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(rp.frame._alpha, 1, "interruptible: pink reveal up"); eq(rs.frame._alpha, 0)
    W.clean()
end

function T.a_rescale_reseats_the_reveal_and_builds_no_texture()
    local W = world()
    local before = countFrames()
    for _, h in ipairs({ 1080, 1440, 720, 1440 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
        __fireEvent("DISPLAY_SIZE_CHANGED")
        eq(countFrames(), before, "nothing built at " .. h)
        local run = W.tgt.run
        for _, rv in ipairs(W.tgt.reveals) do
            near(rv.lit[run.count]._points.BOTTOMLEFT.y, run.segs[run.count].x0, 1e-9, "re-seated at " .. h)
            near(rv.caret._w, run.capW, 1e-9)
        end
    end
    W.clean()
end

function T.without_set_clips_children_the_target_keeps_the_visible_strip_fill()
    local W = world({ beforeLoad = function()
        local create = FS.ChevronCastBar.Create
        FS.ChevronCastBar.Create = function(host, opts)
            local run = create(host, opts)            -- the engine's own clip frame is already built
            getmetatable(UIParent).SetClipsChildren = nil
            return run
        end
    end })
    W.clean()
    ok(W.tgt, "the tape still builds")
    eq(W.tgt.reveals, nil, "no reveal")
    ok(degraded("gunsighttape_noclip"), "logged once")
    local n = 0
    for _, k in ipairs(__degrades) do if k == "gunsighttape_noclip" then n = n + 1 end end
    eq(n, 1, "exactly once, even with two strips")
    startTargetCast(W, true)
    W.clean()
    eq(W.tgt.S.mode, "strip")
    eq(W.tgt.S.stripOnly, true, "still engine timed")
    for _, s in ipairs(W.tgt.strips) do
        eq(s._shown, true); ok(s._timer ~= nil)
        ok(s._fill._alpha ~= 0, "today's visible strip fill")
        near(s._scale, W.tgt.run.pitch / 16, 1e-9, "its tile scaled to one chevron per engine pitch")
        local tl, br = s._points.TOPLEFT, s._points.BOTTOMRIGHT
        ok(tl and br, "anchored by its two full-run corners")
        eq(tl.rel, W.tgt.run.frame); eq(tl.relPoint, "TOPLEFT")
        eq(br.rel, W.tgt.run.frame); eq(br.relPoint, "BOTTOMRIGHT")
        eq(s._points.BOTTOMLEFT, nil, "not the reveal's clock seating")
    end
end

-- A strip that has no fill texture to ride cannot carry the reveal: the tape degrades exactly like a
-- missing SetClipsChildren (one log, no reveal, no throw), and no strip is left invisible.
function T.a_strip_without_a_fill_texture_degrades_to_the_plain_strip_without_throwing()
    local W = world({ beforeLoad = function()
        local create = FS.ChevronCastBar.Create
        FS.ChevronCastBar.Create = function(host, opts)
            local run = create(host, opts)
            if run and opts.vertical and opts.colors.base == FS.GunsightTape.colors.steel then
                local strip = run.CreateStrip
                function run.CreateStrip(self, parent)
                    local sb, why = strip(self, parent)
                    if sb then sb.GetStatusBarTexture = function() return nil end end
                    return sb, why
                end
            end
            return run
        end
    end })
    W.clean()
    ok(W.tgt and W.you, "the tapes still build")
    eq(W.tgt.reveals, nil, "no reveal")
    ok(degraded("gunsighttape_noclip"), "logged under the noclip key")
    local n = 0
    for _, k in ipairs(__degrades) do if k == "gunsighttape_noclip" then n = n + 1 end end
    eq(n, 1, "exactly once")
    eq(#W.tgt.strips, 2, "both strips are kept")
    for _, s in ipairs(W.tgt.strips) do
        if s._fill then ok(s._fill._alpha ~= 0, "the strip that has a fill keeps it visible (the pair was never half hidden)") end
    end
    startTargetCast(W, true)
    W.clean()
    eq(W.tgt.S.mode, "strip"); eq(W.tgt.S.stripOnly, true, "still engine timed")
    W.endCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.clean()
    __fireEvent("UI_SCALE_CHANGED")
    W.clean()
end

-- ---- secrets --------------------------------------------------------------------

function T.no_secret_is_ever_compared()
    local W = world()
    local S = W.tgt.S
    for _, event in ipairs({ "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_DELAYED", "UNIT_SPELLCAST_STOP",
        "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED", "UNIT_SPELLCAST_CHANNEL_START",
        "UNIT_SPELLCAST_CHANNEL_STOP" }) do
        W.secretCast("target")
        W.fire(S, "UNIT_SPELLCAST_START")
        W.fire(S, event, __SECRET_ID, __SECRET)
        W.at(S, __now + 0.3)
    end
    W.clean()
    -- and the same with a secret CHANNEL
    __units.target.cast = nil
    __units.target.chan = { name = __SECRET_NAME, tex = "icon", startMS = __SECRET, endMS = __SECRET,
        notInt = __SECRET_BOOL, spellID = __SECRET, secret = true }
    W.fire(S, "UNIT_SPELLCAST_CHANNEL_START")
    W.at(S, __now + 0.3)
    W.clean()
end

-- ---- degrade --------------------------------------------------------------------

-- Which strip is which: the strip filled with the pink colour is the interruptible one, the steel one the
-- other. Swapping the two lists in fb would still flip alphas, so this pins the colours to the alphas.
function T.the_pink_strip_shows_for_interruptible_and_the_steel_strip_for_not()
    local W = world()
    local S = W.tgt.S
    local pink, steel = FS.GunsightTape.colors.pink, FS.GunsightTape.colors.steel
    local function strips()
        local p, s
        for _, strip in ipairs(W.tgt.strips) do
            local c = strip._fill._vc
            if c[1] == pink[1] and c[2] == pink[2] and c[3] == pink[3] then p = strip end
            if c[1] == steel[1] and c[2] == steel[2] and c[3] == steel[3] then s = strip end
        end
        return p, s
    end
    local p, s = strips()
    ok(p and s and p ~= s, "one pink strip and one steel strip")
    local function has(list, v) for _, r in ipairs(list) do if r == v then return true end end return false end
    ok(has(W.tgt.fb.pink, p) and not has(W.tgt.fb.steel, p), "the pink strip is in fb.pink")
    ok(has(W.tgt.fb.steel, s) and not has(W.tgt.fb.pink, s), "the steel strip is in fb.steel")
    W.cast("target", "Fear", "C1", 100, 1.5, true)       -- not interruptible
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(s._alpha, 1, "not interruptible: steel strip visible"); eq(p._alpha, 0, "not interruptible: pink strip hidden")
    W.cast("target", "Mending", "C2", 100, 2, false)     -- interruptible
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(p._alpha, 1, "interruptible: pink strip visible"); eq(s._alpha, 0, "interruptible: steel strip hidden")
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    eq(p._fromBool, __SECRET_BOOL, "pink strip follows the secret flag"); eq(p._fromT, 0); eq(p._fromF, 1)
    eq(s._fromBool, __SECRET_BOOL, "steel strip follows the secret flag"); eq(s._fromT, 1); eq(s._fromF, 0)
    W.clean()
end

-- Only one of the two target strips builds: the strip path needs both (a lone strip is never
-- alpha-managed, it would stay pink whatever the flag says), so it is the no-strips fallback.
function T.a_lone_target_strip_is_treated_as_unsupported()
    local W = world({ beforeLoad = function()
        local create = FS.ChevronCastBar.Create
        FS.ChevronCastBar.Create = function(host, opts)
            local run = create(host, opts)
            if run and opts.vertical and opts.colors.base == FS.GunsightTape.colors.steel then
                local made, strip = 0, run.CreateStrip
                function run.CreateStrip(self, parent)
                    made = made + 1
                    if made >= 2 then return nil, "no second strip" end
                    return strip(self, parent)
                end
            end
            return run
        end
    end })
    W.clean()
    ok(W.tgt, "the tape still builds")
    eq(#W.tgt.strips, 0, "no lone strip is kept")
    eq(W.tgt.S.stripOnly, nil, "the run path stays for plain casts")
    ok(degraded("gunsighttape_nostrip"), "logged once")
    for _, o in ipairs(__all) do
        if o._kind == "StatusBar" and o._timer ~= nil then error("a strip was handed a duration") end
    end
    W.secretCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    W.clean()
    W.endCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    W.cast("target", "Fear", "C1", 100, 1.5)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(W.tgt.S.mode, "run"); eq(W.tgt.run:GetPhase(), "cast")
    W.clean()
end

function T.without_alpha_from_boolean_the_tape_stays_neutral_and_never_errors()
    local W = world({ beforeLoad = function() getmetatable(UIParent).SetAlphaFromBoolean = nil end })
    local S = W.tgt.S
    eq(S.shield.SetAlphaFromBoolean, nil, "the shield stand-in falls back to CastBars' own branch")
    W.secretCast("target")
    W.fire(S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(S.mode, "strip")
    for _, r in ipairs(W.tgt.fb.steel) do eq(r._alpha, 1, "steel stays up") end
    for _, r in ipairs(W.tgt.fb.pink) do eq(r._alpha, 0, "pink stays down") end
end

function T.without_vertical_strip_support_the_tape_degrades_quietly()
    local W = world({ beforeLoad = function() __sbMissing.SetOrientation = true end })
    W.clean()
    ok(W.tgt and W.you, "the tapes still build")
    eq(#W.tgt.strips, 0, "no strips"); ok(degraded("gunsighttape_nostrip"), "logged once")
    -- a secret cast neither throws nor leaves a half drawn fill
    W.secretCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    W.clean()
    eq(W.tgt.S.mode, "strip", "CastBars still tracks the cast (name, tag, padlock)")
    eq(W.tgt.S.stripOnly, nil, "no engine-timed fill to rely on: the run path stays for plain casts")
    W.endCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    -- a plain cast still lights the engine run
    W.cast("target", "Fear", "C1", 100, 1.5)
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(W.tgt.S.mode, "run"); eq(W.tgt.run:GetPhase(), "cast")
    W.clean()
    -- the player tape works exactly as before
    W.cast("player", "Shadow Bolt", "P1", 100, 2.5)
    W.fire(W.you.S, "UNIT_SPELLCAST_START")
    eq(W.you.S.mode, "run")
    W.clean()
end

function T.a_castbars_without_the_view_seam_logs_and_leaves_stack_a()
    local W = world({ stripView = true })
    W.clean()
    ok(degraded("gunsighttape_noview"), "logged")
    ok(W.P.events._scripts.OnEvent ~= nil, "Stack A keeps its events")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(W.P.frame._shown, true, "Stack A still draws the cast")
    eq(W.you.run:GetPhase(), "idle", "and the tape stays idle")
end

-- ---- lifecycle ------------------------------------------------------------------

function T.no_onupdate_at_rest_and_one_chain_only_while_a_cast_is_live()
    local W = world()
    eq(__countOnUpdates(), 0, "nothing runs after the build")
    local S = W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    ok(__countOnUpdates() >= 1, "the engine and the readout ticker run while a cast is live")
    ok(S.ticker.frame._scripts.OnUpdate ~= nil, "the ticker installs its script on Show")
    W.stepTo(S, 100, 102.5)
    W.fire(S, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(S, 102.5, 104.5)
    eq(__countOnUpdates(), 0, "everything is cleared again once the lock-in has played")
    eq(S.ticker.frame._scripts.OnUpdate, nil, "the ticker's script is cleared, not just hidden")
    -- the same for the target's engine-timed cast
    W.secretCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_START")
    eq(__countOnUpdates(), 1, "only the readout ticker: the fill is engine timed")
    W.endCast("target")
    W.fire(W.tgt.S, "UNIT_SPELLCAST_STOP", __SECRET_ID)
    eq(__countOnUpdates(), 0)
    W.clean()
end

function T.a_rescale_resizes_in_place_and_builds_nothing()
    local W = world()
    local before = countFrames()
    local regionsBefore = #__all
    local segsBefore = #W.you.run.segs
    local segW1, tickW1 = W.you.run.segW, W.you.ticks.base[1]._w
    UIParent._h = 1080
    UIParent._w = 1080 * 16 / 9
    __fireEvent("UI_SCALE_CHANGED")
    __fireEvent("DISPLAY_SIZE_CHANGED")
    W.clean()
    eq(countFrames(), before, "no frame or texture created by a rescale")
    eq(#W.you.run.segs, segsBefore)
    ok(W.you.run.segW < segW1, "the chevrons shrank with the scale: " .. W.you.run.segW .. " < " .. segW1)
    ok(W.you.ticks.base[1]._w < tickW1, "so did the ticks")
    local k = mockupK()
    near(W.you.run.segW, 2 * MU.HW_YOU * k, 1.2, "the run follows the new scale")
    near(W.tgt.run.segW, 2 * MU.HW_YOU * k, 1.2)
    eq(W.you.run.count, MU.N); eq(W.tgt.run.count, MU.N)
    near(W.tgt.kick._w, MU.KICK_W * k, 1e-6, "the KICK tag resizes")
    near(W.you.run.frame._points.TOP.y, -(MU.base.TOP - MU.base.FR_T) * k, 1e-6, "and the seat")
    -- again, and back: still nothing built
    for _, h in ipairs({ 1080, 1440, 720, 1440 }) do
        UIParent._h = h; UIParent._w = h * 16 / 9
        __fireEvent("UI_SCALE_CHANGED")
    end
    eq(countFrames(), before)
    W.clean()
end

function T.a_rescale_mid_cast_keeps_the_cast_running()
    local W = world()
    local S = W.you.S
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(S, "UNIT_SPELLCAST_START")
    W.stepTo(S, 100, 101)
    UIParent._h = 1080
    __fireEvent("UI_SCALE_CHANGED")
    W.stepTo(S, 101, 101.5)
    eq(W.you.run:GetPhase(), "cast")
    ok(litCount(W.you.run) > 0)
    W.clean()
end

function T.the_gunsight_off_builds_nothing_and_leaves_stack_a_untouched()
    local W = world({ db = { gunsight = { enabled = false } } })
    W.clean()
    eq(W.Gun.IsEnabled(), false)
    eq(W.you, nil, "no player tape"); eq(W.tgt, nil, "no target tape")
    eq(find(function(o) return o._name == "ForeverSynthwaveGunsightTape_you" end), nil)
    -- Stack A: events still wired, and a cast still draws on its bar
    ok(W.P.events._scripts.OnEvent ~= nil and W.G.events._scripts.OnEvent ~= nil, "Stack A events intact")
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.P, "UNIT_SPELLCAST_START")
    eq(W.P.frame._shown, true, "the Stack A bar shows the cast")
    eq(W.P.mode, "run")
    W.fire(W.P, "UNIT_SPELLCAST_STOP", "C1")
    W.stepTo(W.P, 100, 104.5)
    eq(W.P.frame._shown, false, "and hides again")
    W.secretCast("target")
    W.fire(W.G, "UNIT_SPELLCAST_START")
    eq(W.G.mode, "strip", "the Stack A strip path is unchanged")
    -- no view was handed over and no Stack A bar was flagged
    eq(W.P.alwaysIdle, nil); eq(W.P.stripOnly, nil); eq(W.P.retired, nil)
    -- the idle row API still drives Stack A
    FS.CastBars.SetIdleVisible(true)
    eq(W.P.frame._shown, true, "idle row on")
    W.clean()
end

function T.the_view_seam_rejects_an_incomplete_view_and_a_second_view()
    local W = world({ noLogin = true })
    eq(FS.CastBars.SetView(nil), false); eq(FS.CastBars.SetView({}), false)
    eq(FS.CastBars.SetView({ player = {}, target = {} }), false, "a view needs every field")
    ok(W.P.events._scripts.OnEvent ~= nil, "a rejected view leaves Stack A live")
end

function T.the_idle_row_api_does_not_revive_a_retired_stack_a()
    local W = world()
    FS.CastBars.SetIdleVisible(true)
    eq(W.P.frame._shown, false); eq(W.G.frame._shown, false)
    eq(FS.CastBars.SetIdleHint("player", "x"), true, "the call is accepted, nothing shows")
    eq(W.P.frame._shown, false)
    eq(FS.CastBars.SetRestAlpha(0.5), true)
    eq(W.P.frame._alpha ~= 0.5, true)
    W.clean()
end

function T.a_cast_in_progress_when_the_view_takes_over_is_picked_up()
    local W = world({ noLogin = true })
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    __now = 101
    __fireEvent("ADDON_LOADED", "ForeverSynthwave")
    __fireEvent("PLAYER_LOGIN")
    W.you, W.tgt = FS.GunsightTape.you, FS.GunsightTape.tgt
    eq(W.you.S.mode, "run", "the live cast is read when the seam is wired")
    eq(W.P.frame._shown, false, "and Stack A is out of the picture")
    W.clean()
end

-- The idle paint at build must not kill a cast the seam just picked up (the state machine would stay in
-- "run" with the engine run idle, and ignore the verdict that follows).
function T.a_cast_live_at_build_is_still_running_after_the_build()
    local W = world({ noLogin = true })
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.cast("target", "Fear", "C2", 100, 1.5)
    __now = 101
    __fireEvent("ADDON_LOADED", "ForeverSynthwave")
    __fireEvent("PLAYER_LOGIN")
    W.you, W.tgt = FS.GunsightTape.you, FS.GunsightTape.tgt
    eq(W.you.S.mode, "run"); eq(W.you.run:GetPhase(), "cast", "the player's run is still casting")
    eq(W.tgt.S.mode, "strip"); eq(W.tgt.strips[1]._shown, true, "the target's fill is still up")
    -- and the verdict is still heard
    W.endCast("player")
    W.fire(W.you.S, "UNIT_SPELLCAST_STOP", "C1")
    eq(W.you.run:GetPhase(), "hold", "the state machine took the verdict: the lock-in plays")
    W.stepTo(W.you.S, 101, 103)
    eq(W.you.run:GetPhase(), "idle"); eq(W.you.S.mode, nil)
    W.clean()
end

function T.a_retired_stack_a_holds_no_event_registrations()
    local W = world()
    for _, S in ipairs({ W.P, W.G }) do
        eq(next(S.events._events), nil, S.unit .. ": no plain events left on the retired frame")
        eq(next(S.events._unitEvents), nil, S.unit .. ": no unit events left on the retired frame")
        eq(S.events._scripts.OnEvent, nil, S.unit .. ": and no handler")
    end
    -- the view's own bars do listen
    for _, t in ipairs({ W.you, W.tgt }) do
        eq(t.S.events._events.PLAYER_ENTERING_WORLD, true, t.key .. ": the view bar is wired")
    end
    -- without the seam Stack A is untouched
    local W2 = world({ stripView = true })
    ok(W2.P.events._scripts.OnEvent ~= nil, "no view: Stack A keeps its handler")
    eq(W2.P.events._events.PLAYER_ENTERING_WORLD, true, "no view: and its events")
    ok(next(W2.P.events._unitEvents) ~= nil, "no view: and its unit events")
end

function T.piece_frames_hold_no_tape_state_the_core_would_clobber()
    -- The core fades and hides the PIECE frame; the cast host is a child, so a hidden piece does not
    -- stop the state machine from tracking the cast, and showing it again finds it consistent.
    local W = world()
    W.Gun.SetPiece("you", false, true)
    W.cast("player", "Shadow Bolt", "C1", 100, 2.5)
    W.fire(W.you.S, "UNIT_SPELLCAST_START")
    eq(W.you.host._shown, true, "the host itself is never hidden by the registry")
    W.Gun.SetPiece("you", true, true)
    eq(W.you.piece._shown, true)
    W.clean()
end

__checks = T
"""


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "ForeverSynthwave.toc must stay CRLF"))
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, f, t, c = (toc.index(n) for n in ("Gunsight.lua", "GunsightFrame.lua", "GunsightTape.lua", "CombatHud.lua"))
        out.append(("toc_order", None if g < f < t < c else
                    f"GunsightTape.lua must load after GunsightFrame.lua and before CombatHud.lua (positions {g}, {f}, {t}, {c})"))
        cb = toc.index("CastBars.lua")
        out.append(("toc_after_castbars", None if cb < t else "GunsightTape.lua must load after CastBars.lua (it registers a view on it)"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = TAPE.read_text(encoding="utf-8") if TAPE.exists() else ""
    src = "\n".join(ln.split("--", 1)[0] for ln in src.splitlines())      # comments may name them
    reads = [n for n in ("UnitCastingInfo", "UnitChannelInfo", "UnitCastingDuration", "UnitChannelDuration")
             if n in src]
    out.append(("tape_never_reads_cast_data_itself", None if not reads else
                f"GunsightTape.lua must leave cast data to CastBars.lua, it mentions {reads}"))
    out.append(("tape_has_no_unconditional_onupdate", None if 'SetScript("OnUpdate"' not in src else
                "GunsightTape.lua installs an OnUpdate; the readout ticker in CastBars.lua is the only one"))
    boxes = ADDON / "GunsightBoxes.lua"
    m = re.search(r"\bTGT_GROW\s*=\s*(\d+)", boxes.read_text(encoding="utf-8")) if boxes.exists() else None
    want = int(re.search(r"if\(TBS==='b'\)return \{x:BOXR\.x,y:BOXR\.y-(\d+),", MOCKUP.read_text(encoding="utf-8")).group(1))
    out.append(("kick_rise_is_the_real_boxes_tgt_grow", None if m and int(m.group(1)) == want else
                f"GunsightBoxes.lua C.TGT_GROW is {m and m.group(1)}, the mockup's option B box grows up by {want}"))
    return out


def run_case(name: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHEV.MOCK)
    lua.execute(CB.MOCK)
    theme_src = (ADDON / "Theme.lua").read_text(encoding="utf-8")
    consts = [CHEV._extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    lua.execute(CB.WIRE)
    lua.execute(MOCK)
    lua.execute(GS.theme_has_target_lua())      # the real shared rule (FS.HasTarget), Theme being stubbed here
    lua.eval("__loadChevron")("ChevronCastBar.lua", (ADDON / "ChevronCastBar.lua").read_text(encoding="utf-8"))
    g = lua.globals()
    g.__castSrc = CASTBARS.read_text(encoding="utf-8")
    g.__layoutSrc = LAYOUT.read_text(encoding="utf-8")
    g.__gunsightSrc = GUNSIGHT.read_text(encoding="utf-8")
    g.__tapeSrc = TAPE.read_text(encoding="utf-8") if TAPE.exists() else "error('GunsightTape.lua is missing')"
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(CHECKS)
        lua.eval("__checks")[name]()
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_tape()
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(CHECKS.replace("__checks = T", "__names = T"))
    names = sorted(k for k in lua.eval("__names").keys())
    failed = 0
    total = 0
    for name, problem in static_checks():
        total += 1
        if problem:
            failed += 1
            print(f"FAIL  {name}: {problem}")
        else:
            print(f"ok    {name}")
    for name in names:
        total += 1
        err = run_case(name, mu)
        if err:
            failed += 1
            print(f"FAIL  {name}: {err}")
        else:
            print(f"ok    {name}")
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
