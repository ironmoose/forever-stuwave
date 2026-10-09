#!/usr/bin/env python3
"""Runs the real Gunsight.lua (the L1 core of the Gunsight HUD) headless against a mock WoW API.

Gunsight.lua is the geometry root, the anchor frames and the piece registry every later Gunsight
lane builds on (mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html is the
locked design). The checks pin:

  * constants: every geometry number in Gunsight.lua is parsed back out of the mockup's JS and
    compared, so a mockup edit that moves a seat fails here instead of drifting silently;
  * geo: the mockup canvas is 2000x1125 image px and the design space is 2560x1440, so
    design = image * 1.28 and UI units = design * FS.Layout.Scale(); the character centre
    (CX, CY) is the root origin, (-6.4, -86.4) design px from UIParent CENTER, Y up;
  * seating: nothing is positioned at file load, everything lands at PLAYER_LOGIN from the
    UIParent height of that moment, and again on the Layout rescale hook; every anchor frame's
    resolved rect is compared with the mockup's own arithmetic (from the canvas centre, not
    through the root) at scale 1.0 and at 1200/1440;
  * the piece registry: default all on, SetPiece persists to ForeverSTUwaveDB.gunsight, a
    non-instant change fades through an AnimationGroup (never OnUpdate) from the frame's current
    alpha, a frame under a hidden ancestor snaps instead of fading, a piece registered after
    state was saved gets that state, a protected frame in combat gets alpha changes only (no
    Show/Hide/EnableMouse) and is reconciled on PLAYER_REGEN_ENABLED;
  * persistence shape, the /fsgun slash command, the debug outlines, the .toc order and the
    Theme colour tokens.

The mock is strict (a widget method it does not define fails as a nil call), Show/Hide/EnableMouse
on a protected frame in combat raise AND are recorded (a case fails if any was attempted, even
inside a pcall), IsVisible includes ancestor visibility, an animation group on a non visible frame
never plays, and it is NOT the real client. The real Layout.lua is loaded.

    python3 tools/gunsight-harness.py

Exit 0 = every check passed. GUNSIGHT_LUA=<path> runs another file in place of Gunsight.lua.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
GUNSIGHT = Path(os.environ.get("GUNSIGHT_LUA") or ADDON / "Modules/CombatHud/Gunsight.lua")
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
THEME = Path(os.environ.get("THEME_LUA") or ADDON / "Core/Theme.lua")
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
MOCKUP_V7 = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"


# ---------------------------------------------------------------------------------------
# Numbers the mockup owns. Read, never retyped, so a drift fails here.
# ---------------------------------------------------------------------------------------

def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def v7_constants() -> dict:
    """The target side areas and the My buffs plate, from the v7 concept mockup (emptySlot and buffs)."""
    src = MOCKUP_V7.read_text(encoding="utf-8")
    ax, aw = (int(v) for v in _m(r"""<rect x="(\d+)" y="'\+y\+'" width="(\d+)" height="'\+h\+'\"""", src, "emptySlot x and width").groups())
    uy, ah = (int(v) for v in _m(r"emptySlot\((\d+),(\d+),'UPPER AREA", src, "upper emptySlot y and height").groups())
    ly, lh = (int(v) for v in _m(r"emptySlot\((\d+),(\d+),'LOWER AREA", src, "lower emptySlot y and height").groups())
    if ah != lh:
        sys.exit("mockup v7: the two areas differ in height")
    bx, bw = (int(v) for v in _m(r"x0=(\d+),w=(\d+);", src, "buffs plate x and width").groups())
    by, bh = (int(v) for v in _m(r"ch\(x0,(\d+),w,(\d+),6\)", src, "buffs plate y and height").groups())
    return dict(AREA_X=ax, AREA_W=aw, AREA_H=ah, AREA_UY=uy, AREA_LY=ly, MYB_X=bx, MYB_Y=by, MYB_W=bw, MYB_H=bh)


def mockup_constants() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    W, H, CX, CY = (int(v) for v in _m(r"var W=(\d+),H=(\d+),CX=(\d+),CY=(\d+)", src, "W/H/CX/CY").groups())
    TOP, BOT, FR_T, FR_B = (int(v) for v in _m(r"var TOP=(\d+),BOT=(\d+),FR_T=(\d+),FR_B=(\d+)", src, "TOP/BOT/FR_T/FR_B").groups())
    tl0, tl1, tr0, tr1 = (int(v) for v in _m(r"var TL=\{x0:(\d+),x1:(\d+)\},TR=\{x0:(\d+),x1:(\d+)\}", src, "TL/TR").groups())
    b = [int(v) for v in _m(
        r"var BOXL=\{x:(\d+),y:(\d+),w:(\d+),h:(\d+)\},BOXR=\{x:(\d+),y:(\d+),w:(\d+),h:(\d+)\}", src, "BOXL/BOXR").groups()]
    lbrk = int(_m(r"var LBRK=(\d+),RBRK=2\*CX-LBRK", src, "LBRK/RBRK").group(1))
    dot_ax, dot_end, lanes = _m(r"var DOT_AX=(\d+),DOT_END=(\d+),LANE=\[([\d,]+)\]", src, "DOT_AX/DOT_END/LANE").groups()
    _m(r"var U=1/1\.28;", src, "U = 1/1.28")
    nxt_s = int(_m(r"var NXT=\{s:(\d+)\*U\}", src, "NXT size").group(1))
    nxt_pad = int(_m(r"NXT\.x=BOXL\.x-(\d+)\*U-NXT\.s", src, "NXT x gap").group(1))
    sh_sc, sh_w, sh_h, sh_g, sh_y = (int(v) for v in _m(
        r"var SH_SC=(\d+),SH_W=(\d+)\*U,SH_H=(\d+)\*U,SH_G=(\d+)\*U,SH_X=TL\.x1,SH_Y=FR_B\+(\d+)\*U", src, "shard row").groups())
    bs, buff_gap = (int(v) for v in _m(r"var bs=(\d+)\*U,u=reduce.*?by=SH_Y\+SH_H\+(\d+)\*U", src, "buff tile").groups())
    hz_l = int(_m(r"hline\(630,TL\.x1\+(\d+),LBRK", src, "horizon left end").group(1))
    hz_r = int(_m(r"hline\(630,TR\.x1\+\d+,DOT_AX-(\d+)", src, "horizon right end").group(1))
    proc_base, proc_grow = (int(v) for v in _m(r"half=(\d+)\+q\*(\d+);", src, "proc post half").groups())
    proc_tick = int(_m(r"lineTo\(bx\+out\*(\d+),630-half\)", src, "proc post tick").group(1))
    css = {n: v.lower() for n, v in re.findall(r"^\s*--(gold|steel|amber|warm|red):(#[0-9a-fA-F]{6});", src, re.M)}
    for need in ("gold", "steel", "amber", "warm", "red"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")
    return dict(
        W=W, H=H, CX=CX, CY=CY, TOP=TOP, BOT=BOT, FR_T=FR_T, FR_B=FR_B,
        TL=dict(x0=tl0, x1=tl1), TR=dict(x0=tr0, x1=tr1),
        BOXL=dict(x=b[0], y=b[1], w=b[2], h=b[3]), BOXR=dict(x=b[4], y=b[5], w=b[6], h=b[7]),
        LBRK=lbrk, RBRK=2 * CX - lbrk,
        DOT_AX=int(dot_ax), DOT_END=int(dot_end), LANE=[int(v) for v in lanes.split(",")],
        NXT_S=nxt_s, NXT_PAD=nxt_pad,
        SH_SC=sh_sc, SH_W=sh_w, SH_H=sh_h, SH_G=sh_g, SH_DROP=sh_y,
        BUFF_S=bs, BUFF_GAP=buff_gap,
        HZ_PAD_L=hz_l, HZ_PAD_R=hz_r,
        PROC_BASE=proc_base, PROC_GROW=proc_grow, PROC_TICK=proc_tick,
        CSS=css,
    )


def design_constants() -> tuple[int, int]:
    src = LAYOUT.read_text(encoding="utf-8")
    return (int(_m(r"FS\.Layout\.DESIGN_W\s*=\s*(\d+)", src, "DESIGN_W").group(1)),
            int(_m(r"FS\.Layout\.DESIGN_H\s*=\s*(\d+)", src, "DESIGN_H").group(1)))


def expected_rects(mu: dict) -> dict:
    """Image-px rects (x, y, w, h), top-left origin, straight from the mockup's own formulas."""
    mu = {**mu, **v7_constants()}
    U = 1 / 1.28
    tl, tr, bl, br = mu["TL"], mu["TR"], mu["BOXL"], mu["BOXR"]
    nxt_s = mu["NXT_S"] * U
    sh_y = mu["FR_B"] + mu["SH_DROP"] * U
    sh_w = mu["SH_SC"] * mu["SH_W"] * U + (mu["SH_SC"] - 1) * mu["SH_G"] * U
    buff_s = mu["BUFF_S"] * U
    proc_h = 2 * (mu["PROC_BASE"] + mu["PROC_GROW"])
    proc_w = 2 * mu["PROC_TICK"]
    return {
        "tapeL": (tl["x0"], mu["FR_T"], tl["x1"] - tl["x0"], mu["FR_B"] - mu["FR_T"]),
        "tapeR": (tr["x0"], mu["FR_T"], tr["x1"] - tr["x0"], mu["FR_B"] - mu["FR_T"]),
        "boxL": (bl["x"], bl["y"], bl["w"], bl["h"]),
        "boxR": (br["x"], br["y"], br["w"], br["h"]),
        "dotAxis": (mu["DOT_AX"], mu["TOP"], mu["DOT_END"] - mu["DOT_AX"], mu["BOT"] - mu["TOP"]),
        "next": (bl["x"] - mu["NXT_PAD"] * U - nxt_s, bl["y"] + (bl["h"] - nxt_s) / 2, nxt_s, nxt_s),
        "shards": (tl["x1"] - sh_w, sh_y, sh_w, mu["SH_H"] * U),
        "buff": ((tl["x0"] + tl["x1"]) / 2 - buff_s / 2, sh_y + mu["SH_H"] * U + mu["BUFF_GAP"] * U, buff_s, buff_s),
        "procL": (mu["LBRK"] - proc_w / 2, mu["CY"] - proc_h / 2, proc_w, proc_h),
        "procR": (mu["RBRK"] - proc_w / 2, mu["CY"] - proc_h / 2, proc_w, proc_h),
        "horizon": (tl["x1"] + mu["HZ_PAD_L"], mu["CY"], (mu["DOT_AX"] - mu["HZ_PAD_R"]) - (tl["x1"] + mu["HZ_PAD_L"]), 0),
        "areaU": (mu["AREA_X"], mu["AREA_UY"], mu["AREA_W"], mu["AREA_H"]),
        "areaL": (mu["AREA_X"], mu["AREA_LY"], mu["AREA_W"], mu["AREA_H"]),
        # The My buffs plate is sized from one tunable (MYBUFFS.tile), not from the mockup's 164 x 56; the anchor test
        # reads the rect off G.MYBUFFS and pin_mybuffs_plate_stays_inside_the_mockups checks it against the mockup.
        "mybuffs": (mu["MYB_X"], mu["MYB_Y"], mu["MYB_W"], mu["MYB_H"]),
    }


def theme_has_target_lua() -> str:
    """The REAL `function FS.HasTarget() ... end` out of Theme.lua, for harnesses that stub Theme but need
    the shared target rule the Gunsight pieces call. It reads FS, UnitExists and FS.IsSecret at call time.
    The closing `end` may carry a trailing comment. The extraction fails loudly if it swallowed a second
    top-level definition (the closing line moved or was indented)."""
    src = THEME.read_text(encoding="utf-8")
    m = re.search(r"^function FS\.HasTarget\(\)\n.*?^end[ \t]*(?:--[^\n]*)?$", src, re.M | re.S)
    if not m:
        sys.exit("Theme.lua: `function FS.HasTarget()` not found; the shared target rule moved")
    text = m.group(0)
    body = text.split("\n", 1)[1]
    if re.search(r"^(?:local )?function ", body, re.M):
        sys.exit("Theme.lua: the `function FS.HasTarget()` extraction swallowed a second top-level definition; "
                 "its closing `end` is not at column 0 on its own line (a trailing comment is allowed, "
                 "anything else is not)")
    return text + "\n"


def theme_target_rule_lua() -> str:
    """The shared target rules out of Theme.lua: FS.HasTarget plus the file-local PlainFlag helper and
    FS.TargetTakesDots (the DoT scale and the horizon's dot segment share it). They load as one chunk so the
    local resolves. Both extractions fail loudly if a closing `end` moved off column 0."""
    src = THEME.read_text(encoding="utf-8")
    parts = [theme_has_target_lua()]
    for head in (r"local function PlainFlag\(", r"function FS\.TargetTakesDots\(\)"):
        m = re.search(r"^" + head + r".*?^end[ \t]*(?:--[^\n]*)?$", src, re.M | re.S)
        if not m:
            sys.exit(f"Theme.lua: `{head}` not found; the shared target rule moved")
        body = m.group(0).split("\n", 1)[1]
        if re.search(r"^(?:local )?function ", body, re.M):
            sys.exit(f"Theme.lua: the `{head}` extraction swallowed a second top-level definition")
        parts.append(m.group(0) + "\n")
    return "".join(parts)


def lua_value(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"[{k!r}]={lua_value(x)}".replace("'", '"') for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_value(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v + '"'
    return repr(v)


# ---------------------------------------------------------------------------------------
# The mock client
# ---------------------------------------------------------------------------------------

MOCK = r"""
local realPcall = pcall
FRAMES = {}
PRINTED = {}
IN_COMBAT = false
BLOCKED = {}   -- every protected-frame action attempted in combat (even inside a pcall), see blockedAction
DEGRADED = {}
SlashCmdList = {}

function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    PRINTED[#PRINTED + 1] = table.concat(t, " ")
end
function InCombatLockdown() return IN_COMBAT end
function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < 1e-6,
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end

local ANCHOR = {
    TOPLEFT = { -0.5, 0.5 }, TOP = { 0, 0.5 }, TOPRIGHT = { 0.5, 0.5 },
    LEFT = { -0.5, 0 }, CENTER = { 0, 0 }, RIGHT = { 0.5, 0 },
    BOTTOMLEFT = { -0.5, -0.5 }, BOTTOM = { 0, -0.5 }, BOTTOMRIGHT = { 0.5, -0.5 },
}

local Frame = {}
Frame.__index = Frame

local function newRegion(kind, parent)
    local f = setmetatable({
        kind = kind, parent = parent, points = {}, w = 0, h = 0, alpha = 1, shown = true,
        strata = "MEDIUM", level = 1, events = {}, scripts = {}, mouse = true, calls = {}, children = {},
    }, Frame)
    return f
end

local function count(self, name) self.calls[name] = (self.calls[name] or 0) + 1 end

-- The client raises ADDON_ACTION_BLOCKED for Show/Hide/EnableMouse on a protected frame in combat
-- lockdown, and the event fires even when the caller wrapped the call in pcall. So record it
-- BEFORE raising: the runner fails any case that logged one, whoever swallowed the error.
local function blockedAction(self, what)
    if self.protected and IN_COMBAT then
        BLOCKED[#BLOCKED + 1] = what
        error("ADDON_ACTION_BLOCKED " .. what .. " on protected frame", 3)
    end
end

function Frame:SetPoint(point, rel, relPoint, x, y)
    count(self, "SetPoint")
    check(ANCHOR[point], "bad anchor point " .. tostring(point))
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    if rel == nil then rel = self.parent end
    check(rel ~= nil, "SetPoint with no relative frame")
    self.points[#self.points + 1] = { point, rel, relPoint or point, x or 0, y or 0 }
end
function Frame:ClearAllPoints() count(self, "ClearAllPoints"); self.points = {} end
function Frame:GetNumPoints() return #self.points end
function Frame:GetPoint(i)
    local p = self.points[i or 1]
    if not p then return nil end
    return p[1], p[2], p[3], p[4], p[5]
end
function Frame:SetSize(w, h) count(self, "SetSize"); self.w, self.h = w, h end
function Frame:SetWidth(w) self.w = w end
function Frame:SetHeight(h) self.h = h end
function Frame:GetWidth() return self.w end
function Frame:GetHeight() return self.h end
-- The client rule (measured live 2026-10-03): a frame whose own width or height is 0 has no rect,
-- and neither does any frame anchored through one. GetLeft/GetCenter are nil there, so nothing
-- anchored to it renders. Only presence is modelled here; rect() below does the geometry.
local function hasRect(f)
    if f == UIParent then return true end
    if not ((f.w or 0) > 0 and (f.h or 0) > 0) then return false end
    local p = f.points[1]
    return p ~= nil and hasRect(p[2])
end
function Frame:GetLeft() if hasRect(self) then return 0 end end
function Frame:GetCenter() if hasRect(self) then return 0, 0 end end
function Frame:SetAlpha(a) count(self, "SetAlpha"); self.alpha = a end
function Frame:GetAlpha() return self.alpha end
function Frame:Show()
    count(self, "Show")
    blockedAction(self, "Show")
    self.shown = true
end
function Frame:Hide()
    count(self, "Hide")
    blockedAction(self, "Hide")
    self.shown = false
end
function Frame:IsShown() return self.shown end
-- IsVisible is IsShown AND every ancestor shown, like the client; IsShown is the frame's own flag.
function Frame:IsVisible()
    return self.shown and (self.parent == nil or self.parent:IsVisible())
end
function Frame:SetFrameStrata(s) self.strata = s end
function Frame:GetFrameStrata() return self.strata end
function Frame:SetFrameLevel(l) self.level = l end
function Frame:GetFrameLevel() return self.level end
function Frame:GetParent() return self.parent end
function Frame:IsProtected() return self.protected == true, self.protected == true end
function Frame:EnableMouse(on)
    count(self, "EnableMouse")
    blockedAction(self, "EnableMouse")
    self.mouse = on and true or false
end
function Frame:IsMouseEnabled() return self.mouse end
function Frame:RegisterEvent(e) self.events[e] = true end
function Frame:UnregisterEvent(e) self.events[e] = nil end
function Frame:SetScript(name, fn) self.scripts[name] = fn end
function Frame:GetScript(name) return self.scripts[name] end
function Frame:HookScript() error("HookScript is not mocked") end

function Frame:CreateTexture(name, layer)
    local t = newRegion("Texture", self)
    t.layer = layer
    function t:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
    function t:SetTexture() end
    function t:SetAllPoints() self.allPoints = true end
    self.children[#self.children + 1] = t
    return t
end
-- The client throws "Font not set" for SetText / SetFormattedText on a FontString that has no font: one
-- made with an inherits template carries that template's font, otherwise SetFont / SetFontObject (or
-- Theme.ApplyMono, which calls SetFont) must come first. A write before that kills a pcall'd build.
function Frame:CreateFontString(name, layer, template)
    local s = newRegion("FontString", self)
    if type(template) == "string" then s.hasFont = true end
    function s:SetText(t)
        if not self.hasFont then error("Font not set", 2) end
        self.text = t
    end
    function s:SetFormattedText(fmt, ...)
        if not self.hasFont then error("Font not set", 2) end
        self.text = string.format(fmt, ...)
    end
    function s:SetTextColor() end
    function s:SetFontObject() self.hasFont = true end
    function s:SetFont(path, size, flags) self.hasFont = true; self.fontSize = size; return true end
    function s:SetJustifyH() end
    self.children[#self.children + 1] = s
    return s
end

PLAYING = {}
function Frame:CreateAnimationGroup()
    local g = { anims = {}, scripts = {}, playing = false, owner = self }
    function g:CreateAnimation(kind)
        check(kind == "Alpha", "only Alpha animations are mocked, got " .. tostring(kind))
        local a = { kind = kind }
        function a:SetFromAlpha(v) self.from = v end
        function a:SetToAlpha(v) self.to = v end
        function a:SetDuration(v) self.duration = v end
        function a:SetSmoothing(v) self.smoothing = v end
        function a:SetOrder(v) self.order = v end
        g.anims[#g.anims + 1] = a
        return a
    end
    function g:SetScript(n, fn) self.scripts[n] = fn end
    function g:SetToFinalAlpha(v) self.finalAlpha = v end
    -- Like the client, a group on a frame that is not visible (own flag or any ancestor hidden)
    -- never advances, so it never finishes and OnFinished never fires.
    function g:Play()
        self.plays = (self.plays or 0) + 1
        if not self.owner:IsVisible() then return end
        self.playing = true
        PLAYING[self] = true
    end
    function g:Stop() self.playing = false; PLAYING[self] = nil end
    function g:Finish() self.playing = false; PLAYING[self] = nil end
    function g:IsPlaying() return self.playing end
    self.groups = self.groups or {}
    self.groups[#self.groups + 1] = g
    return g
end

-- Lets every playing animation group run to its end, like the client would after its duration.
function finishAnims()
    local list = {}
    for g in pairs(PLAYING) do list[#list + 1] = g end
    for _, g in ipairs(list) do
        g.playing = false
        PLAYING[g] = nil
        if g.scripts.OnFinished then g.scripts.OnFinished(g, false) end
    end
end

function CreateFrame(kind, name, parent, template)
    check(kind == "Frame", "mock only builds plain Frames, got " .. tostring(kind))
    local f = newRegion("Frame", parent)
    f.name, f.template = name, template
    FRAMES[#FRAMES + 1] = f
    if parent then parent.children[#parent.children + 1] = f end
    return f
end

UIParent = newRegion("Frame", nil)
UIParent.name = "UIParent"
UIParent.calls = {}
function SetScreen(h)
    UIParent.h = h
    UIParent.w = h * 16 / 9
end

function fire(event, ...)
    local list = {}
    for _, f in ipairs(FRAMES) do
        if f.events[event] and f.scripts.OnEvent then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f.scripts.OnEvent(f, event, ...) end
end

-- Resolves a frame's rect against UIParent CENTER (y up): left, bottom, w, h.
local function position(f, point)
    if f == UIParent then
        local a = ANCHOR[point]
        return a[1] * f.w, a[2] * f.h
    end
    local p = f.points[1]
    check(p, "frame has no points (name " .. tostring(f.name) .. ")")
    local rx, ry = position(p[2], p[3])
    local ax, ay = rx + p[4], ry + p[5]
    local mine = ANCHOR[p[1]]
    local cx, cy = ax - mine[1] * f.w, ay - mine[2] * f.h
    local want = ANCHOR[point]
    return cx + want[1] * f.w, cy + want[2] * f.h
end
function rect(f)
    local l, t = position(f, "TOPLEFT")
    return l, t - f.h, f.w, f.h
end
function topleft(f) return position(f, "TOPLEFT") end
function centerOf(f) return position(f, "CENTER") end

FS = {}
function FS.LogDegradeOnce(key, msg) DEGRADED[key] = msg end

function loadAddonFile(src, name)
    local fn, err = loadstring(src, "@" .. name)
    if not fn then error(err) end
    return fn("forever-stuwave", FS)
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


# Boot helpers shared by the cases: a fresh world at a screen height, files loaded, login fired.
PRELUDE = r"""
local function boot(opts)
    opts = opts or {}
    SetScreen(opts.fileLoadHeight or opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    if opts.height then SetScreen(opts.height) end
    if not opts.noEvents then
        if ForeverSTUwaveDB ~= nil or opts.fireAddonLoaded then fire("ADDON_LOADED", "forever-stuwave") end
        fire("PLAYER_LOGIN")
    end
    return FS.Gunsight
end
"""

case("constants_match_the_mockup")(r"""
local G = boot({ noEvents = true }).G
check(type(G) == "table", "FS.Gunsight.G (the constants table) is missing")
local function eq(a, b, what) near(a, b, what .. " (Gunsight has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")") end
eq(G.W, MU.W, "W"); eq(G.H, MU.H, "H"); eq(G.CX, MU.CX, "CX"); eq(G.CY, MU.CY, "CY")
eq(G.TOP, MU.TOP, "TOP"); eq(G.BOT, MU.BOT, "BOT"); eq(G.FR_T, MU.FR_T, "FR_T"); eq(G.FR_B, MU.FR_B, "FR_B")
eq(G.TL.x0, MU.TL.x0, "TL.x0"); eq(G.TL.x1, MU.TL.x1, "TL.x1"); eq(G.TR.x0, MU.TR.x0, "TR.x0"); eq(G.TR.x1, MU.TR.x1, "TR.x1")
for _, k in ipairs({ "x", "y", "w", "h" }) do
    eq(G.BOXL[k], MU.BOXL[k], "BOXL." .. k); eq(G.BOXR[k], MU.BOXR[k], "BOXR." .. k)
end
check(G.BRK == nil, "the bracket box constants are gone with the HUD Frame piece")
eq(G.LBRK, MU.LBRK, "LBRK"); eq(G.RBRK, MU.RBRK, "RBRK")
eq(G.DOT_AX, MU.DOT_AX, "DOT_AX"); eq(G.DOT_END, MU.DOT_END, "DOT_END")
check(#G.LANE == #MU.LANE, "LANE count")
for i, v in ipairs(MU.LANE) do eq(G.LANE[i], v, "LANE " .. i) end
eq(G.U, 1 / 1.28, "U"); eq(G.GRID, 1.28, "image px to design px")
eq(G.NXT_S, MU.NXT_S, "NXT size (addon units)"); eq(G.NXT_PAD, MU.NXT_PAD, "NXT gap (addon units)")
eq(G.SH_SC, MU.SH_SC, "SH_SC"); eq(G.SH_W, MU.SH_W, "SH_W (addon units)"); eq(G.SH_H, MU.SH_H, "SH_H (addon units)")
eq(G.SH_G, MU.SH_G, "SH_G (addon units)"); eq(G.SH_DROP, MU.SH_DROP, "shard drop under the tape (addon units)")
eq(G.BUFF_S, MU.BUFF_S, "buff tile (addon units)"); eq(G.BUFF_GAP, MU.BUFF_GAP, "buff gap (addon units)")
eq(G.HZ_PAD_L, MU.HZ_PAD_L, "horizon left pad"); eq(G.HZ_PAD_R, MU.HZ_PAD_R, "horizon right pad")
eq(G.PROC_BASE, MU.PROC_BASE, "proc half base"); eq(G.PROC_GROW, MU.PROC_GROW, "proc half growth"); eq(G.PROC_TICK, MU.PROC_TICK, "proc tick")
eq(G.AREA.x, MU.AREA_X, "area x"); eq(G.AREA.w, MU.AREA_W, "area width"); eq(G.AREA.h, MU.AREA_H, "area height")
eq(G.AREA.upperY, MU.AREA_UY, "upper area y"); eq(G.AREA.lowerY, MU.AREA_LY, "lower area y")
-- My buffs: the plate is smaller than the mockup's (playtest 2026-10-08), sized from MYBUFFS.tile; it keeps the
-- mockup's right edge (the gap short of the next cast tile) and its vertical centre (the info boxes' band).
local MB = G.MYBUFFS
check(MB.w < MU.MYB_W and MB.h < MU.MYB_H, "My buffs plate is smaller than the mockup's " .. MU.MYB_W .. " x " .. MU.MYB_H)
near(MB.x + MB.w, MU.MYB_X + MU.MYB_W, "My buffs plate right edge")
near(MB.y + MB.h / 2, MU.MYB_Y + MU.MYB_H / 2, "My buffs plate vertical centre")
check(MB.tile > 0 and MB.tile < MB.pitch, "My buffs tile and pitch")
eq(MU.W * G.GRID, FS.Layout.DESIGN_W, "image width * 1.28 is the design width")
eq(MU.H * G.GRID, FS.Layout.DESIGN_H, "image height * 1.28 is the design height")
""")

case("geo_math_at_scale_one")(r"""
local Gs = boot({ height = 1440 })
near(FS.Layout.Scale(), 1, "scale")
near(Gs.ui(100), 128, "ui(100)"); near(Gs.ui(0), 0, "ui(0)"); near(Gs.ui(-50), -64, "ui(-50)")
local root = Gs.root
check(root:GetParent() == UIParent, "root is not parented to UIParent")
local point, rel, relPoint, x, y = root:GetPoint(1)
check(point == "CENTER" and rel == UIParent and relPoint == "CENTER", "root anchor is " .. tostring(point) .. "/" .. tostring(relPoint))
near(x, -6.4, "root x from UIParent CENTER"); near(y, -86.4, "root y from UIParent CENTER (Y up)")
near(root:GetWidth(), 1, "root width"); near(root:GetHeight(), 1, "root height")
-- Point seats a frame by image coordinates relative to the root origin.
local f = CreateFrame("Frame", nil, root)
Gs.Point(f, "TOPLEFT", 995, 630)
local p, r, rp, px, py = f:GetPoint(1)
check(p == "TOPLEFT" and r == root and rp == "CENTER", "Point anchors TOPLEFT to the root CENTER, got " .. tostring(p) .. " " .. tostring(rp))
near(px, 0, "character centre x is the root origin"); near(py, 0, "character centre y is the root origin")
Gs.Point(f, "CENTER", 1095, 530)   -- 100 right, 100 up (image y runs down)
local _, _, _, qx, qy = f:GetPoint(1)
near(qx, 128, "100 image px right is 128 UI units"); near(qy, 128, "100 image px up is 128 UI units, Y up")
check(f:GetNumPoints() == 1, "Point must clear the previous anchor")
""")

case("geo_math_at_1200")(r"""
local Gs = boot({ height = 1200 })
local s = 1200 / 1440
near(FS.Layout.Scale(), s, "scale")
near(Gs.ui(100), 128 * s, "ui(100) at 1200")
local _, _, _, x, y = Gs.root:GetPoint(1)
near(x, -6.4 * s, "root x at 1200"); near(y, -86.4 * s, "root y at 1200")
local f = CreateFrame("Frame", nil, Gs.root)
Gs.Point(f, "TOPLEFT", 1095, 530)
local _, _, _, px, py = f:GetPoint(1)
near(px, 128 * s, "Point x at 1200"); near(py, 128 * s, "Point y at 1200")
""")

case("nothing_is_positioned_at_file_load")(r"""
local Gs = boot({ noEvents = true, height = 1440 })
check(Gs.root:GetNumPoints() == 0, "root was seated at file load (UIParent is only 768 tall then)")
for name, a in pairs(Gs.anchors) do check(a:GetNumPoints() == 0, "anchor " .. name .. " was seated at file load") end
-- a rescale event before PLAYER_LOGIN must not seat either (UIParent is still settling)
fire("UI_SCALE_CHANGED")
check(Gs.root:GetNumPoints() == 0, "a rescale before login seated the root")
""")

case("seats_from_the_uiparent_height_at_login")(r"""
local Gs = boot({ fileLoadHeight = 768, height = 1200 })
near(select(4, Gs.root:GetPoint(1)), -6.4 * 1200 / 1440, "root x uses the height at login, not file load")
local l, b, w, h = rect(Gs.anchors.boxL)
near(w, 114 * 1.28 * 1200 / 1440, "boxL width uses the height at login")
""")

case("reseats_on_the_layout_rescale_hook")(r"""
local Gs = boot({ height = 1200 })
SetScreen(1440)
fire("UI_SCALE_CHANGED")
near(select(4, Gs.root:GetPoint(1)), -6.4, "root x after the rescale")
near(select(5, Gs.root:GetPoint(1)), -86.4, "root y after the rescale")
local _, _, w = rect(Gs.anchors.boxL)
near(w, 114 * 1.28, "boxL width after the rescale")
SetScreen(1080)
fire("DISPLAY_SIZE_CHANGED")
local _, _, w2 = rect(Gs.anchors.boxL)
near(w2, 114 * 1.28 * 1080 / 1440, "boxL width after a display size change")
""")

case("a_rescale_and_a_seat_move_in_combat_wait_for_the_end_of_combat")(r"""
local Gs = boot({ height = 1200, db = {} })
local x0, y0 = select(4, Gs.root:GetPoint(1)), select(5, Gs.root:GetPoint(1))
local _, _, w0 = rect(Gs.anchors.boxL)
IN_COMBAT = true
Gs.root.calls, Gs.anchors.boxR.calls = {}, {}
SetScreen(1440)
fire("UI_SCALE_CHANGED")
check(Gs.SetSeat(10, 20) ~= false, "SetSeat refused")
check(Gs.root.calls.SetPoint == nil and Gs.root.calls.ClearAllPoints == nil, "the root was moved in combat")
check(Gs.anchors.boxR.calls.SetPoint == nil and Gs.anchors.boxR.calls.SetSize == nil, "an anchor was moved or sized in combat")
near(select(4, Gs.root:GetPoint(1)), x0, "root x waits"); near(select(5, Gs.root:GetPoint(1)), y0, "root y waits")
local _, _, w1 = rect(Gs.anchors.boxL)
near(w1, w0, "boxL keeps its size in combat")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
near(select(4, Gs.root:GetPoint(1)), -6.4 + 10, "root x applied once combat ends")
near(select(5, Gs.root:GetPoint(1)), -86.4 + 20, "root y applied with the latest seat")
local _, _, w2 = rect(Gs.anchors.boxL)
near(w2, 114 * 1.28, "boxL resized at the new scale")
local n = Gs.root.calls.SetPoint
fire("PLAYER_REGEN_ENABLED")
check(Gs.root.calls.SetPoint == n, "the deferred reseat is not replayed")
""")

case("a_login_in_combat_still_seats_the_first_time_and_defers_only_later_moves")(r"""
IN_COMBAT = true
local Gs = boot({ height = 1200, db = {} })
IN_COMBAT = false
check(Gs.root:GetNumPoints() > 0 and Gs.anchors.boxL:GetWidth() > 0, "a reload in combat left the HUD unseated until the fight ended")
IN_COMBAT = true
Gs.root.calls = {}
fire("UI_SCALE_CHANGED")
check(Gs.root.calls.SetPoint == nil, "a later reseat in combat moved the root")
IN_COMBAT = false
""")

case("root_has_a_rect_so_children_resolve")(r"""
local Gs = boot({ height = 1200 })
local root = Gs.root
check(root:GetWidth() > 0 and root:GetHeight() > 0,
    "root is " .. tostring(root:GetWidth()) .. " x " .. tostring(root:GetHeight()) .. ": a 0 size frame has no rect on the client")
check(root:GetCenter() ~= nil, "root has no centre, so nothing anchored to it renders")
check(Gs.anchors.tapeL:GetLeft() ~= nil, "tapeL has no rect after login, so the tape would not draw")
check(Gs.anchors.boxL:GetCenter() ~= nil, "boxL has no rect after login")
""")

case("root_is_plain_and_anchors_hang_off_it")(r"""
local Gs = boot({ height = 1440 })
local root = Gs.root
check(root.kind == "Frame", "root kind")
check(root.template == nil, "root must not use a secure template: " .. tostring(root.template))
check(root:IsProtected() == false, "root must be non-secure")
check(root:GetFrameStrata() == "MEDIUM", "root strata is " .. tostring(root:GetFrameStrata()))
local want = { "tapeL", "tapeR", "boxL", "boxR", "dotAxis", "next", "shards", "buff", "procL", "procR", "horizon", "areaU", "areaL", "mybuffs" }
for _, name in ipairs(want) do
    local a = Gs.anchors[name]
    check(a, "anchor " .. name .. " is missing")
    check(a:GetParent() == root, "anchor " .. name .. " is not a child of the root")
    check(a.template == nil and a:IsProtected() == false, "anchor " .. name .. " must be a plain non-secure frame")
end
local n = 0
for _ in pairs(Gs.anchors) do n = n + 1 end
check(n == #want, "unexpected anchor count " .. n)
""")

local_anchor_body = r"""
local Gs = boot({ height = HEIGHT })
local s = HEIGHT / 1440
local gridUi = 1.28 * s
local bad = {}
for name, e in pairs(EXPECT) do
    local a = Gs.anchors[name]
    check(a, "anchor " .. name .. " is missing")
    if name == "mybuffs" then local M = Gs.G.MYBUFFS; e = { M.x, M.y, M.w, M.h } end
    -- Straight from the mockup arithmetic: image px from the canvas centre, no root involved.
    local el = (e[1] - MU.W / 2) * gridUi
    local et = -(e[2] - MU.H / 2) * gridUi
    local l, b, w, h = rect(a)
    local top = b + h
    local function off(got, want) return math.abs(got - want) > 1e-6 end
    if off(l, el) or off(top, et) or off(w, e[3] * gridUi) or off(h, e[4] * gridUi) then
        bad[#bad + 1] = string.format("%s: left %.4f top %.4f w %.4f h %.4f, mockup says %.4f %.4f %.4f %.4f",
            name, l, top, w, h, el, et, e[3] * gridUi, e[4] * gridUi)
    end
end
check(#bad == 0, "anchors off the mockup:\n  " .. table.concat(bad, "\n  "))
"""
case("anchors_land_where_the_mockup_says_at_scale_one")(local_anchor_body.replace("HEIGHT", "1440"))
case("anchors_land_where_the_mockup_says_at_1200")(local_anchor_body.replace("HEIGHT", "1200"))

case("seat_nudge_moves_the_root_and_every_anchor")(r"""
local Gs = boot({ height = 1440, db = {} })
local l0, b0 = rect(Gs.anchors.boxL)
local ok = Gs.SetSeat(10, -5)
check(ok ~= false, "SetSeat refused")
near(select(4, Gs.root:GetPoint(1)), -6.4 + 10, "root x with the nudge")
near(select(5, Gs.root:GetPoint(1)), -86.4 - 5, "root y with the nudge (Y up)")
local l1, b1 = rect(Gs.anchors.boxL)
near(l1 - l0, 10, "anchors follow the nudge in x"); near(b1 - b0, -5, "anchors follow the nudge in y")
check(ForeverSTUwaveDB.gunsight.seat.dx == 10 and ForeverSTUwaveDB.gunsight.seat.dy == -5, "nudge not saved")
-- a saved nudge scales with the screen: design px, not UI units
SetScreen(1200)
fire("UI_SCALE_CHANGED")
near(select(4, Gs.root:GetPoint(1)), (-6.4 + 10) * 1200 / 1440, "saved nudge is design px, scaled at 1200")
""")

case("saved_seat_applies_at_login")(r"""
local Gs = boot({ height = 1440, db = { gunsight = { seat = { dx = 4, dy = 8 } } } })
near(select(4, Gs.root:GetPoint(1)), -6.4 + 4, "root x with the saved nudge")
near(select(5, Gs.root:GetPoint(1)), -86.4 + 8, "root y with the saved nudge")
""")

case("db_defaults_and_repair")(r"""
local Gs = boot({ height = 1440, db = {} })
local g = ForeverSTUwaveDB.gunsight
check(type(g) == "table", "ForeverSTUwaveDB.gunsight not created")
check(g.enabled == nil and g.pieces == nil, "enabled and pieces live in FS.Config now, not in ForeverSTUwaveDB.gunsight")
check(FS.Config.Get("gunsight.enabled") == true, "enabled defaults to true")
check(g.seat and g.seat.dx == 0 and g.seat.dy == 0, "seat defaults to 0,0")
for _, k in ipairs({ "you", "next", "shard", "buff", "tgt", "dot", "prc", "party", "mybuffs" }) do
    check(FS.Config.Get("gunsight.pieces." .. k) == true, "piece " .. k .. " defaults to on")
    check(Gs.IsPieceOn(k) == true, "IsPieceOn(" .. k .. ") defaults to true")
end
check(Gs.IsEnabled() == true, "IsEnabled default")
""")

case("db_garbage_is_repaired_and_saved_values_kept")(r"""
local Gs = boot({ height = 1440, db = { gunsight = { enabled = false, pieces = { buff = false, you = "yes", bogus = true, frame = false }, seat = { dx = "x" } } } })
local g = ForeverSTUwaveDB.gunsight
check(FS.Config.Get("gunsight.enabled") == false and Gs.IsEnabled() == false, "enabled=false must survive the migration")
check(FS.Config.Get("gunsight.pieces.buff") == false and Gs.IsPieceOn("buff") == false, "a saved off piece stays off")
check(FS.Config.Get("gunsight.pieces.you") == true, "a non boolean piece value falls back to on")
-- a saved value for the retired `frame` piece (the removed HUD Frame) is ignored, not an error
check(Gs.IsPieceOn("frame") == false and Gs.SetPiece("frame", true) == false, "the retired frame piece is not a known piece")
check(#Gs.PIECES == 9, "nine pieces, got " .. #Gs.PIECES)
check(g.seat.dx == 0 and g.seat.dy == 0, "a bad seat falls back to 0,0")
""")


case("area_defaults_and_invalid_values_read_the_default")(r"""
local Gs = boot({ height = 1440, db = {} })
check(Gs.GetArea("upper") == "debuffsH", "upper defaults to debuffsH, got " .. tostring(Gs.GetArea("upper")))
check(Gs.GetArea("lower") == "class", "lower defaults to class, got " .. tostring(Gs.GetArea("lower")))
check(FS.Config.Get("gunsight.target.upper") == "debuffsH" and FS.Config.Get("gunsight.target.lower") == "class", "the config defaults")
FS.Config.Set("gunsight.target.upper", "bogus"); FS.Config.Set("gunsight.target.lower", 7)
check(Gs.GetArea("upper") == "debuffsH", "an unknown upper value reads as the default")
check(Gs.GetArea("lower") == "class", "a non string lower value reads as the default")
check(Gs.GetArea("middle") == nil, "an unknown area reads nil")
local ids = table.concat(Gs.AREA_IDS, ",")
check(ids == "debuffsH,debuffsV,class,empty", "the module ids in menu order: " .. ids)
""")

case("set_area_swaps_with_the_other_area")(r"""
local Gs = boot({ height = 1440, db = {} })
-- upper debuffsH, lower class: picking class for upper hands the lower area the old upper value
check(Gs.SetArea("upper", "class") == true, "SetArea refused")
check(Gs.GetArea("upper") == "class" and Gs.GetArea("lower") == "debuffsH", "swap upper: " .. Gs.GetArea("upper") .. "/" .. Gs.GetArea("lower"))
-- and the other direction
check(Gs.SetArea("lower", "class") == true, "SetArea lower refused")
check(Gs.GetArea("lower") == "class" and Gs.GetArea("upper") == "debuffsH", "swap lower: " .. Gs.GetArea("upper") .. "/" .. Gs.GetArea("lower"))
-- debuffsH and debuffsV are one family: picking V for the lower area (debuffsH sits upper) swaps
check(Gs.SetArea("lower", "debuffsV") == true, "SetArea debuffsV refused")
check(Gs.GetArea("lower") == "debuffsV" and Gs.GetArea("upper") == "class", "family swap: " .. Gs.GetArea("upper") .. "/" .. Gs.GetArea("lower"))
-- a pick the other area does not hold changes only this area
Gs.SetArea("lower", "empty")
check(Gs.GetArea("lower") == "empty" and Gs.GetArea("upper") == "class", "plain pick: " .. Gs.GetArea("upper") .. "/" .. Gs.GetArea("lower"))
-- Empty may sit in both areas: no swap
Gs.SetArea("upper", "empty")
check(Gs.GetArea("upper") == "empty" and Gs.GetArea("lower") == "empty", "both empty")
-- switching the same family inside one area is not a conflict with the other
Gs.SetArea("upper", "debuffsH"); Gs.SetArea("upper", "debuffsV")
check(Gs.GetArea("upper") == "debuffsV" and Gs.GetArea("lower") == "empty", "H to V in place")
check(Gs.SetArea("upper", "debuffsV") == true, "re-picking the current value is fine")
check(Gs.SetArea("upper", "bogus") == false and Gs.SetArea("nowhere", "class") == false, "bad arguments are refused")
check(Gs.GetArea("upper") == "debuffsV", "a refused pick changes nothing")
""")

case("on_area_changed_fires_on_set_and_on_a_profile_switch")(r"""
function UnitGUID() return "Player-1-0001" end
local Gs = boot({ height = 1440, db = {} })
local calls = 0
Gs.OnAreaChanged(function() calls = calls + 1 end)
Gs.SetArea("upper", "debuffsV")
check(calls == 1, "one notification for a plain pick, got " .. calls)
Gs.SetArea("upper", "class")
check(calls == 2, "one notification for a swap (two keys change), got " .. calls)
Gs.SetArea("upper", "class")
check(calls == 2, "re-picking the same value must not notify")
check(FS.Config.NewProfile("Other") == true, "NewProfile")
check(FS.Config.SetActiveProfile("Other") == true, "SetActiveProfile")
check(calls >= 3, "a profile switch to different areas must notify, got " .. calls)
local before = calls
FS.Config.Set("gunsight.target.lower", "empty")
check(calls == before + 1, "a direct config write notifies, got " .. (calls - before))
Gs.OnAreaChanged(function() error("boom") end)
FS.Config.Set("gunsight.target.lower", "class")
check(calls == before + 2, "a throwing callback must not stop the others")
""")

case("set_area_under_a_read_only_config_returns_false_and_changes_nothing")(r"""
local Gs = boot({ height = 1440, db = { profilesVersion = 999 } })
check(FS.Config.IsReadOnly(), "setup: Config is read-only (saved profiles newer than the addon)")
local calls = 0
Gs.OnAreaChanged(function() calls = calls + 1 end)
check(Gs.SetArea("upper", "class") == false, "a pick on a read-only Config is refused")
check(Gs.SetArea("lower", "debuffsV") == false, "so is a pick that would swap")
check(Gs.GetArea("upper") == "debuffsH" and Gs.GetArea("lower") == "class", "both areas keep their values")
check(calls == 0, "no notification for a refused pick, got " .. calls)
""")

case("piece_registry_defaults_all_on")(r"""
local Gs = boot({ height = 1440 })
local f = CreateFrame("Frame", nil, Gs.root)
local shows, hides = 0, 0
local piece = Gs.RegisterPiece("you", { frame = f, onShow = function() shows = shows + 1 end, onHide = function() hides = hides + 1 end })
check(Gs.IsPieceOn("you") == true, "default on")
check(f:IsShown(), "default-on piece is shown")
near(f:GetAlpha(), 1, "alpha")
check(shows == 1 and hides == 0, "onShow runs once at registration, got " .. shows .. "/" .. hides)
check(Gs.IsPieceOn("nope") == false, "unknown key is not on")
""")

case("set_piece_instant_persists_and_runs_hooks")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
local log = {}
Gs.RegisterPiece("buff", { frame = f, onShow = function() log[#log + 1] = "show" end, onHide = function() log[#log + 1] = "hide" end })
log = {}
Gs.SetPiece("buff", false, true)
check(not f:IsShown(), "instant off hides at once")
check(Gs.IsPieceOn("buff") == false, "IsPieceOn after off")
check(FS.Config.Get("gunsight.pieces.buff") == false, "off is not persisted")
check(table.concat(log, ",") == "hide", "hooks after off: " .. table.concat(log, ","))
Gs.SetPiece("buff", true, true)
check(f:IsShown() and f:GetAlpha() == 1, "instant on shows at full alpha")
check(FS.Config.Get("gunsight.pieces.buff") == true, "on is not persisted")
check(table.concat(log, ",") == "hide,show", "hooks after on: " .. table.concat(log, ","))
-- same state again is a no-op for the hooks
Gs.SetPiece("buff", true, true)
check(#log == 2, "repeating the same state must not rerun hooks")
check(Gs.SetPiece("nope", true) == false, "unknown key returns false")
""")

case("set_piece_fades_through_an_animation_group")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("tgt", { frame = f })
local before = f.scripts.OnUpdate
Gs.SetPiece("tgt", false)
check(f:IsShown(), "fade out keeps the frame shown until the fade ends")
local g
for _, grp in ipairs(f.groups or {}) do if grp.playing then g = grp end end
check(g, "no animation group is playing for the fade out")
check(#g.anims == 1 and g.anims[1].kind == "Alpha", "fade is one Alpha animation")
near(g.anims[1].duration, 0.25, "fade duration")
near(g.anims[1].from, 1, "fade out from"); near(g.anims[1].to, 0, "fade out to")
finishAnims()
check(not f:IsShown(), "frame hidden after the fade out")
Gs.SetPiece("tgt", true)
check(f:IsShown(), "fade in shows the frame first")
near(g.anims[1].from, 0, "fade in from"); near(g.anims[1].to, 1, "fade in to")
check(g.playing, "fade in animation is not playing")
finishAnims()
near(f:GetAlpha(), 1, "full alpha after the fade in")
check(f.scripts.OnUpdate == before and f.scripts.OnUpdate == nil, "the fade must not use OnUpdate")
for _, fr in ipairs(FRAMES) do check(fr.scripts.OnUpdate == nil, "some frame has an OnUpdate") end
""")

case("an_interrupted_fade_ends_in_the_latest_state")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("dot", { frame = f })
Gs.SetPiece("dot", false)
Gs.SetPiece("dot", true)    -- flip back mid fade
finishAnims()
check(f:IsShown() and f:GetAlpha() == 1, "flipped back on mid fade, frame should be on")
Gs.SetPiece("dot", false)
Gs.SetPiece("dot", true)
Gs.SetPiece("dot", false)
finishAnims()
check(not f:IsShown(), "ended off")
""")

case("protected_frame_in_combat_gets_alpha_only")(r"""
-- Every flip of a protected piece in combat: alpha only. Show/Hide/EnableMouse are all deferred
-- to the PLAYER_REGEN_ENABLED reconcile (the mock records any attempt, even one inside a pcall).
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
f.protected = true
Gs.RegisterPiece("party", { frame = f })
Gs.SetPiece("party", false, true)           -- hidden out of combat
IN_COMBAT = true
f.calls = {}
Gs.SetPiece("party", true)                  -- on in combat
Gs.SetPiece("party", false, true)           -- off in combat, instant
Gs.SetPiece("party", true, true)            -- on in combat, instant
near(f:GetAlpha(), 1, "alpha follows the state in combat")
check(f.calls.Show == nil and f.calls.Hide == nil and f.calls.EnableMouse == nil,
    "Show/Hide/EnableMouse are deferred in combat")
check(#BLOCKED == 0, "attempted: " .. table.concat(BLOCKED, ", "))
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(f:IsShown() and f:IsMouseEnabled(), "reconcile shows the piece and leaves the mouse on")
near(f:GetAlpha(), 1, "alpha after reconcile")
""")

case("fade_under_a_hidden_ancestor_snaps_to_the_final_state")(r"""
-- An animation group never plays on a frame that is not visible, so OnFinished never fires:
-- fading would strand the frame at alpha 0 (in) or shown (out). It must snap instead.
local Gs = boot({ height = 1440, db = {} })
local parent = CreateFrame("Frame", nil, Gs.root)
local f = CreateFrame("Frame", nil, parent)
Gs.RegisterPiece("tgt", { frame = f })
parent:Hide()
check(not f:IsVisible() and f:IsShown(), "setup: shown frame under a hidden ancestor")
Gs.SetPiece("tgt", false)
check(not f:IsShown(), "off under a hidden ancestor hides at once")
near(f:GetAlpha(), 0, "off alpha")
Gs.SetPiece("tgt", true)
check(f:IsShown(), "on under a hidden ancestor shows at once")
near(f:GetAlpha(), 1, "on alpha is not stranded at 0")
for _, grp in ipairs(f.groups or {}) do check(not grp.playing, "no fade is left playing") end
parent:Show()
check(f:IsVisible() and f:GetAlpha() == 1, "visible at full alpha once the ancestor shows")
""")

case("a_flip_mid_fade_starts_from_the_current_alpha")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("dot", { frame = f })
Gs.SetPiece("dot", false)                   -- fade out starts
f:SetAlpha(0.4)                             -- the fade is 40% up when the user flips back
Gs.SetPiece("dot", true)
local g
for _, grp in ipairs(f.groups or {}) do if grp.playing then g = grp end end
check(g, "fade in is not playing")
near(g.anims[1].from, 0.4, "fade in starts from the current alpha")
near(g.anims[1].to, 1, "fade in to")
near(f:GetAlpha(), 0.4, "the flip must not snap alpha before the fade")
Gs.SetPiece("dot", false)                   -- and again out, from 0.4
near(g.anims[1].from, 0.4, "fade out starts from the current alpha")
near(g.anims[1].to, 0, "fade out to")
finishAnims()
check(not f:IsShown(), "ended off")
""")

case("set_seat_before_init_is_kept")(r"""
local Gs = boot({ noEvents = true, height = 1440 })
check(Gs.SetSeat(10, -5) ~= false, "SetSeat refused before init")
ForeverSTUwaveDB = { gunsight = { seat = { dx = 1, dy = 2 } } }
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")
near(select(4, Gs.root:GetPoint(1)), -6.4 + 10, "root x uses the pre init seat, not the saved one")
near(select(5, Gs.root:GetPoint(1)), -86.4 - 5, "root y uses the pre init seat")
check(ForeverSTUwaveDB.gunsight.seat.dx == 10 and ForeverSTUwaveDB.gunsight.seat.dy == -5, "pre init seat not persisted")
""")

case("on_piece_changed_callbacks_fire")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("prc", { frame = f })
local seen = {}
Gs.OnPieceChanged(function(key, on) seen[#seen + 1] = key .. "=" .. tostring(on) end)
Gs.OnPieceChanged(function(key, on) seen[#seen + 1] = "second" end)
Gs.SetPiece("prc", false, true)
Gs.SetPiece("prc", false, true)
Gs.SetPiece("prc", true, true)
check(table.concat(seen, ",") == "prc=false,second,prc=true,second", "callbacks: " .. table.concat(seen, ","))
-- a throwing callback must not stop the others or the state change
Gs.OnPieceChanged(function() error("boom") end)
Gs.OnPieceChanged(function(key, on) seen[#seen + 1] = "after" end)
Gs.SetPiece("prc", false, true)
check(seen[#seen] == "after" and Gs.IsPieceOn("prc") == false, "a throwing callback broke the chain")
""")

case("late_registration_applies_the_saved_state")(r"""
local Gs = boot({ height = 1440, db = { gunsight = { pieces = { buff = false } } } })
local f = CreateFrame("Frame", nil, Gs.root)
local hid = 0
Gs.RegisterPiece("buff", { frame = f, onHide = function() hid = hid + 1 end })
check(not f:IsShown(), "a piece saved off must be hidden when it registers late")
check(hid == 1, "onHide must run for the saved off state")
near(f:GetAlpha(), 0, "late off piece alpha")
local g = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("shard", { frame = g })
check(g:IsShown(), "a piece with no saved off state registers on")
for _, grp in ipairs(f.groups or {}) do check(not grp.playing, "registration must not fade") end
""")

case("early_registration_waits_for_the_saved_state")(r"""
-- Files that load before ADDON_LOADED register before SavedVariables exist: the state lands at init.
SetScreen(1440)
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
loadAddonFile(CONFIG_SRC, "Core/Config.lua")
loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
local Gs = FS.Gunsight
local f = CreateFrame("Frame", nil, Gs.root)
local hid = 0
Gs.RegisterPiece("next", { frame = f, onHide = function() hid = hid + 1 end })
ForeverSTUwaveDB = { gunsight = { pieces = { next = false } } }   -- the client loads SavedVariables now
fire("ADDON_LOADED", "forever-stuwave")
check(not f:IsShown() and hid == 1, "the saved off state is applied once SavedVariables exist")
fire("PLAYER_LOGIN")
check(hid == 1, "login must not rerun the hook")
check(Gs.IsPieceOn("next") == false, "state")
""")

case("other_addons_loading_do_not_init")(r"""
local Gs = boot({ noEvents = true, height = 1440 })
ForeverSTUwaveDB = nil
fire("ADDON_LOADED", "SomeOtherAddon")
check(ForeverSTUwaveDB == nil, "another addon's ADDON_LOADED must not touch the DB")
""")

case("protected_frame_uses_alpha_in_combat_and_reconciles")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
f.protected = true
local log = {}
Gs.RegisterPiece("party", { frame = f, onShow = function() log[#log + 1] = "show" end, onHide = function() log[#log + 1] = "hide" end })
log = {}
f.calls = {}
IN_COMBAT = true
Gs.SetPiece("party", false)                -- non instant, in combat
check(f.calls.Hide == nil and f.calls.Show == nil, "Show/Hide called on a protected frame in combat")
near(f:GetAlpha(), 0, "alpha 0 while off in combat")
check(f.calls.EnableMouse == nil, "EnableMouse called on a protected frame in combat (blocked even in pcall)")
check(f:IsShown(), "frame is still technically shown")
check(Gs.IsPieceOn("party") == false, "state is off")
for _, grp in ipairs(f.groups or {}) do check(not grp.playing, "no fade on a protected frame in combat") end
Gs.SetPiece("party", true)
check(f.calls.Hide == nil, "still no Hide")
near(f:GetAlpha(), 1, "alpha back to 1")
check(f.calls.EnableMouse == nil, "still no EnableMouse in combat")
Gs.SetPiece("party", false)
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not f:IsShown(), "after combat the off piece is really hidden")
near(f:GetAlpha(), 0, "alpha after reconcile")
check(table.concat(log, ",") == "hide,show,hide", "hooks in order: " .. table.concat(log, ","))
-- reconcile for an on piece: hidden out of combat, shown by alpha only in combat, shown for real after
Gs.SetPiece("party", true, true)
check(f:IsShown() and f:GetAlpha() == 1, "on again out of combat")
""")

case("protected_frame_off_in_combat_then_shown_after_reconcile")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
f.protected = true
Gs.RegisterPiece("party", { frame = f })
Gs.SetPiece("party", false, true)           -- hidden out of combat
check(not f:IsShown(), "hidden out of combat")
IN_COMBAT = true
Gs.SetPiece("party", true)                  -- cannot Show now
check(f.calls.Show == 1, "only the earlier registration Show, none in combat: " .. tostring(f.calls.Show))
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(f:IsShown(), "reconcile shows the piece once combat ends")
near(f:GetAlpha(), 1, "alpha after reconcile")
check(f:IsMouseEnabled(), "mouse after reconcile")
check(#BLOCKED == 0, "a protected frame action was attempted in combat")
""")

case("unprotected_frames_still_show_hide_in_combat")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("you", { frame = f })
IN_COMBAT = true
Gs.SetPiece("you", false, true)
check(not f:IsShown(), "an unprotected frame hides normally in combat")
""")

case("master_switch_applies_live_to_the_root_and_tells_listeners")(r"""
local Gs = boot({ height = 1440, db = {} })
check(Gs.IsActive() == true, "a Gunsight enabled at load is active")
check(Gs.IsEnabled() == true and Gs.NeedsReload() == nil, "nothing to reload at load")
local seen = {}
Gs.OnActiveChanged(function(active) seen[#seen + 1] = tostring(active) end)
FS.Config.Set("gunsight.enabled", false)
check(not Gs.root:IsShown(), "master off hides the whole HUD (the root)")
check(Gs.IsActive() == false, "and it is no longer active")
check(Gs.IsEnabled() == true, "IsEnabled stays what was BUILT at load")
check(type(Gs.NeedsReload()) == "string" and Gs.NeedsReload():lower():find("reload", 1, true), "the classic combat HUD was never built: a reload prompt")
FS.Config.Set("gunsight.enabled", true)
check(Gs.root:IsShown(), "master on shows it again")
near(Gs.root:GetAlpha(), 1, "alpha")
check(Gs.IsActive() == true and Gs.NeedsReload() == nil, "active again, no prompt")
FS.Config.Set("gunsight.enabled", true)
check(table.concat(seen, ",") == "false,true", "each flip is announced once, a repeat not at all: " .. table.concat(seen, ","))
""")

case("showing_the_root_again_redraws_the_pieces_that_are_on")(r"""
local Gs = boot({ height = 1440, db = {} })
local log = {}
local function piece(key)
    local f = CreateFrame("Frame", nil, Gs.root)
    Gs.RegisterPiece(key, { frame = f, onShow = function() log[#log + 1] = key end })
end
piece("buff"); piece("shard")
Gs.SetPiece("shard", false, true)
log = {}
FS.Config.Set("gunsight.enabled", false)
check(#log == 0, "hiding the root runs no hook")
FS.Config.Set("gunsight.enabled", true)
check(table.concat(log, ",") == "buff", "only the piece that is on redraws (its pulse may have stopped): " .. table.concat(log, ","))
""")

case("master_off_in_combat_fades_now_and_hides_after_combat")(r"""
local Gs = boot({ height = 1440, db = {} })
Gs.root.protected = true          -- a parent of the protected target of target button
local seen = {}
Gs.OnActiveChanged(function(active) seen[#seen + 1] = tostring(active) end)
Gs.root.calls = {}
IN_COMBAT = true
FS.Config.Set("gunsight.enabled", false)
check(Gs.root.calls.Hide == nil and Gs.root.calls.Show == nil, "no Show or Hide on a protected root in combat")
near(Gs.root:GetAlpha(), 0, "the HUD disappears by alpha")
check(Gs.IsActive() == false and table.concat(seen, ",") == "false", "inactive at once: " .. table.concat(seen, ","))
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not Gs.root:IsShown(), "hidden for real once combat ends")
check(table.concat(seen, ",") == "false", "no second announcement")
check(#BLOCKED == 0, "nothing protected was attempted in combat")
""")

case("master_on_in_combat_waits_for_the_end_of_combat_when_the_root_is_hidden")(r"""
local Gs = boot({ height = 1440, db = {} })
Gs.root.protected = true
FS.Config.Set("gunsight.enabled", false)
check(not Gs.root:IsShown(), "hidden out of combat")
local seen = {}
Gs.OnActiveChanged(function(active) seen[#seen + 1] = tostring(active) end)
IN_COMBAT = true
FS.Config.Set("gunsight.enabled", true)
check(not Gs.root:IsShown() and Gs.IsActive() == false, "cannot show a protected root in combat: not active yet")
check(#seen == 0, "no announcement until it really shows")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(Gs.root:IsShown() and Gs.IsActive() == true and table.concat(seen, ",") == "true", "shown and announced after combat")
check(#BLOCKED == 0, "nothing protected was attempted in combat")
""")

case("master_toggled_back_on_in_combat_cancels_the_pending_hide")(r"""
local Gs = boot({ height = 1440, db = {} })
Gs.root.protected = true
IN_COMBAT = true
FS.Config.Set("gunsight.enabled", false)
Gs.root.calls = {}
FS.Config.Set("gunsight.enabled", true)
near(Gs.root:GetAlpha(), 1, "visible again by alpha")
check(Gs.IsActive() == true, "active at once: the root never left the screen")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(Gs.root:IsShown(), "and the deferred hide was cancelled")
check(Gs.root.calls.Hide == nil, "Hide was never called")
""")

case("master_off_on_off_in_combat_ends_hidden_after_combat_with_no_blocked_action")(r"""
local Gs = boot({ height = 1440, db = {} })
Gs.root.protected = true
local seen = {}
Gs.OnActiveChanged(function(active) seen[#seen + 1] = tostring(active) end)
Gs.root.calls = {}
IN_COMBAT = true
FS.Config.Set("gunsight.enabled", false)
near(Gs.root:GetAlpha(), 0, "off: invisible by alpha")
FS.Config.Set("gunsight.enabled", true)
near(Gs.root:GetAlpha(), 1, "on: visible again by alpha")
check(Gs.IsActive() == true, "on: active, the root never left the screen")
FS.Config.Set("gunsight.enabled", false)
near(Gs.root:GetAlpha(), 0, "off again: invisible")
check(Gs.IsActive() == false, "off again: inactive")
check(Gs.root:IsShown(), "still shown for real until combat ends")
check(Gs.root.calls.Hide == nil and Gs.root.calls.Show == nil, "no Show or Hide in combat")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not Gs.root:IsShown(), "hidden for real once combat ends")
near(Gs.root:GetAlpha(), 1, "alpha reset for the next Show")
check(Gs.IsActive() == false, "and stays inactive")
check(table.concat(seen, ",") == "false,true,false", "announced per flip: " .. table.concat(seen, ","))
check(#BLOCKED == 0, "nothing protected was attempted in combat")
""")

case("a_released_piece_is_shown_and_left_alone_until_it_is_resumed")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
local log = {}
Gs.RegisterPiece("party", { frame = f, onShow = function() log[#log + 1] = "show" end, onHide = function() log[#log + 1] = "hide" end })
Gs.SetPiece("party", false, true)
check(not f:IsShown(), "off: hidden")
log = {}
check(Gs.ReleasePiece("party") == true, "release answers true")
check(f:IsShown() and f:GetAlpha() == 1, "released: shown whatever its saved state")
Gs.SetPiece("party", true, true)
Gs.SetPiece("party", false)
check(f:IsShown() and f:GetAlpha() == 1, "a state change while released does not touch the frame")
check(Gs.IsPieceOn("party") == false, "but the state is still kept")
check(#log == 0, "and runs no hook: " .. table.concat(log, ","))
check(Gs.ResumePiece("party") == true, "resume answers true")
check(not f:IsShown(), "resumed: the frame follows the saved state again (off)")
check(table.concat(log, ",") == "hide", "the state's hook runs on resume: " .. table.concat(log, ","))
check(Gs.ReleasePiece("nope") == false and Gs.ResumePiece("nope") == false, "an unregistered piece is refused")
""")

case("releasing_a_protected_piece_in_combat_is_alpha_only_then_shown_after_combat")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
f.protected = true
Gs.RegisterPiece("party", { frame = f })
Gs.SetPiece("party", false, true)
check(not f:IsShown(), "off out of combat")
IN_COMBAT = true
Gs.ReleasePiece("party")
near(f:GetAlpha(), 1, "visible by alpha in combat")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(f:IsShown() and f:GetAlpha() == 1, "shown for real after combat, not hidden by the saved state")
IN_COMBAT = true
Gs.ResumePiece("party")
near(f:GetAlpha(), 0, "resumed in combat: off by alpha")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not f:IsShown(), "hidden for real after combat")
check(#BLOCKED == 0, "nothing protected was attempted in combat")
""")

case("a_gunsight_off_at_load_cannot_be_switched_on_live")(r"""
local Gs = boot({ height = 1440, db = { gunsight = { enabled = false } } })
check(Gs.IsEnabled() == false and Gs.IsActive() == false, "nothing built, nothing active")
local seen = {}
Gs.OnActiveChanged(function(active) seen[#seen + 1] = tostring(active) end)
FS.Config.Set("gunsight.enabled", true)
check(Gs.IsActive() == false and #seen == 0, "the pieces were never built: still inactive, no announcement")
check(type(Gs.NeedsReload()) == "string" and Gs.NeedsReload():lower():find("reload", 1, true), "a reload prompt")
FS.Config.Set("gunsight.enabled", false)
check(Gs.NeedsReload() == nil, "back to the loaded state: no prompt")
""")

case("register_piece_rejects_bad_input")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
check(Gs.RegisterPiece("bogus", { frame = f }) == false, "unknown key registers nothing")
check(Gs.RegisterPiece("you", {}) == false, "a spec with no frame registers nothing")
check(next(DEGRADED) ~= nil, "a rejected registration must be logged, not silent")
""")

case("hook_errors_are_contained_and_logged")(r"""
local Gs = boot({ height = 1440, db = {} })
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("you", { frame = f, onShow = function() error("hook boom") end })
Gs.SetPiece("you", false, true)
Gs.SetPiece("you", true, true)
check(Gs.IsPieceOn("you") == true and f:IsShown(), "a throwing hook must not stop the state change")
check(next(DEGRADED) ~= nil, "a throwing hook must be logged")
""")

case("slash_status_on_off_seat_piece")(r"""
local Gs = boot({ height = 1440, db = {} })
check(SlashCmdList["FSGUN"] and SLASH_FSGUN1 == "/fsgun", "/fsgun is not registered")
local slash = SlashCmdList["FSGUN"]
PRINTED = {}
slash("")
check(#PRINTED > 0, "no-arg prints the status")
local status = table.concat(PRINTED, "\n")
for _, k in ipairs({ "you", "next", "shard", "buff", "tgt", "dot", "prc", "party" }) do
    check(status:find(k, 1, true), "status does not mention piece " .. k)
end
PRINTED = {}
slash("off")
check(FS.Config.Get("gunsight.enabled") == false, "off did not save")
check(table.concat(PRINTED, "\n"):lower():find("reload", 1, true), "off must say a reload is needed")
PRINTED = {}
slash("on")
check(FS.Config.Get("gunsight.enabled") == true, "on did not save")
check(not table.concat(PRINTED, "\n"):lower():find("reload", 1, true), "on again matches what was built: applied live, no reload")
check(table.concat(PRINTED, "\n"):find("enabled", 1, true), "on says it is enabled")
slash("seat 12 -7")
check(ForeverSTUwaveDB.gunsight.seat.dx == 12 and ForeverSTUwaveDB.gunsight.seat.dy == -7, "seat not saved")
near(select(4, Gs.root:GetPoint(1)), -6.4 + 12, "seat re-seats live")
PRINTED = {}
slash("seat nope")
check(ForeverSTUwaveDB.gunsight.seat.dx == 12, "a bad seat must not change the saved nudge")
check(#PRINTED > 0, "a bad seat prints usage")
local f = CreateFrame("Frame", nil, Gs.root)
Gs.RegisterPiece("shard", { frame = f })
slash("piece shard off")
check(Gs.IsPieceOn("shard") == false, "piece off via slash")
check(FS.Config.Get("gunsight.pieces.shard") == false, "piece off via slash not saved")
slash("piece shard on")
check(Gs.IsPieceOn("shard") == true, "piece on via slash")
PRINTED = {}
slash("piece bogus on")
check(#PRINTED > 0, "an unknown piece prints a message")
PRINTED = {}
slash("garbage")
check(#PRINTED > 0, "unknown subcommands print usage")
""")

case("slash_debug_toggles_outlines_on_every_anchor")(r"""
local Gs = boot({ height = 1440, db = {} })
local slash = SlashCmdList["FSGUN"]
local function visibleEdges(a)
    local n = 0
    for _, c in ipairs(a.children) do
        if c.kind == "Texture" and c.shown and c.color then n = n + 1 end
    end
    return n
end
for name, a in pairs(Gs.anchors) do check(visibleEdges(a) == 0, "anchor " .. name .. " has a visible outline before debug") end
slash("debug")
for name, a in pairs(Gs.anchors) do check(visibleEdges(a) >= 4, "anchor " .. name .. " has no outline after debug on") end
slash("debug")
for name, a in pairs(Gs.anchors) do check(visibleEdges(a) == 0, "anchor " .. name .. " keeps its outline after debug off") end
check(not ForeverSTUwaveDB.gunsight.debug, "debug is a session toggle and must not be saved")
""")

case("debug_outlines_survive_a_rescale")(r"""
local Gs = boot({ height = 1440, db = {} })
SlashCmdList["FSGUN"]("debug")
SetScreen(1200)
fire("UI_SCALE_CHANGED")
local _, _, w = rect(Gs.anchors.boxL)
near(w, 114 * 1.28 * 1200 / 1440, "boxL resized with the debug outline up")
""")

case("on_ready_runs_after_init")(r"""
local Gs = boot({ noEvents = true, height = 1440 })
local ran = 0
Gs.OnReady(function() ran = ran + 1 end)
check(ran == 0, "OnReady must wait for init")
ForeverSTUwaveDB = {}
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")
check(ran == 1, "OnReady must run exactly once, ran " .. ran)
Gs.OnReady(function() ran = ran + 10 end)
check(ran == 11, "OnReady after init runs at once")
""")


def run_case(name: str, body: str, mu: dict, expect: dict, gunsight_src: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(f"MU = {lua_value(mu)}; EXPECT = {lua_value(expect)}")
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = gunsight_src
    runner = lua.eval("function(src) local f, e = loadstring(src, '=case'); if not f then return false, e end; local ok, err = pcall(f); if ok then if #BLOCKED > 0 then return false, 'ADDON_ACTION_BLOCKED: ' .. table.concat(BLOCKED, ', ') end; return true, '' end; return false, tostring(err) end")
    ok, err = runner(PRELUDE + "\n" + body)
    return None if ok else str(err)


def static_checks(mu: dict) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []

    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        i, h, c = toc.index("Modules/CombatHud/Gunsight.lua"), toc.index("Modules/CombatHud/HudLogic.lua"), toc.index("Modules/CombatHud/CombatHud.lua")
        later = [n for n, ln in enumerate(toc) if ln.startswith("Gunsight") and ln != "Modules/CombatHud/Gunsight.lua" and ln.endswith(".lua")]
        bad = [toc[n] for n in later if n < i]
        out.append(("toc_order", None if h < i < c and not bad else
                    f"Gunsight.lua must come after HudLogic.lua, before CombatHud.lua and before any Gunsight*.lua file "
                    f"(positions HudLogic {h}, Gunsight {i}, CombatHud {c}, earlier Gunsight files {bad})"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))

    theme = THEME.read_text(encoding="utf-8")
    for name in ("gold", "steel", "amber", "warm", "red"):
        want = [int(mu["CSS"][name][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        m = re.search(rf"^Theme\.COLOR_{name.upper()}\s*=\s*\{{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*1\s*\}}", theme, re.M)
        if not m:
            out.append((f"theme_token_{name}", f"Theme.COLOR_{name.upper()} is missing or not an opaque {{r,g,b,1}} table"))
            continue
        got = [float(v) for v in m.groups()]
        bad = [i for i in range(3) if abs(got[i] - want[i]) > 0.0006]
        out.append((f"theme_token_{name}", None if not bad else f"RGB {got} does not match the mockup --{name} {mu['CSS'][name]} ({want})"))
    return out


def main() -> int:
    mu = mockup_constants()
    mu.update(v7_constants())
    dw, dh = design_constants()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if (dw, dh) != (2560, 1440) or abs(mu["W"] * 1.28 - dw) > 1e-9 or abs(mu["H"] * 1.28 - dh) > 1e-9:
        report("design_space", f"mockup {mu['W']}x{mu['H']} * 1.28 must equal Layout {dw}x{dh}")
    else:
        report("design_space", None)

    if not GUNSIGHT.exists():
        report("gunsight_file", f"{GUNSIGHT} does not exist")
        for name, _ in CASES:
            report(name, "Gunsight.lua is missing")
        for name, err in static_checks(mu):
            report(name, err)
        print(f"\n{failures} failed")
        return 1

    src = GUNSIGHT.read_text(encoding="utf-8")
    expect = expected_rects(mu)
    for name, body in CASES:
        try:
            err = run_case(name, body, mu, expect, src)
        except LuaError as e:  # a mock or harness bug, not a pass
            err = f"harness error: {e}"
        report(name, err)
    for name, err in static_checks(mu):
        report(name, err)

    total = 1 + len(CASES) + len(static_checks(mu))
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
