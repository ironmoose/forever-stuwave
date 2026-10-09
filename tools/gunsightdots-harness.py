#!/usr/bin/env python3
"""Runs the real GunsightDots.lua (the Gunsight "Target debuffs" modules, Horizontal and Vertical) headless
against a mock WoW API.

GunsightDots.lua registers two modules with FS.GunsightAreas, "debuffsH" and "debuffsV", that draw
FS.TargetDebuffs inside one target side area. The numbers are parsed back out of
mockups/gunsight-modules-concepts-v7-2026-10-08.html (dotsH, dotsV), so a mockup edit fails here instead of
drifting. The checks pin:

  * the seam: both modules register with the areas, the dot piece is NOT registered here any more, nothing
    is built before the areas call build, and a missing FS.GunsightAreas loads silently;
  * Horizontal: at most five rows at a 24.4 px pitch from the area top (the upper area 8 px down, the lower 2 px
    up), each an icon chip, the time ("13s" above 3 s, "2.6s" below), a 0 to 30 s drain bar that turns amber at
    3 s or less, "xN" for stacks, a dim "--" row for an absent debuff, and the ruler rules and ticks;
  * Vertical: the existing time axis compressed into 112 px (3.73 px a second) with its axis 26 px right of the
    target cast bar, ticks and labels inside, the amber band, four lanes, a header, a chip per debuff;
  * the in-combat rule: the absent row or chip shows ONLY in combat (a file-local flag from the REGEN events,
    seeded from InCombatLockdown() OR UnitAffectingCombat(), one-way self heal on a push), a live one is never
    touched, and a visibility write happens only on a change;
  * motion: one OnUpdate per module, only while a row is live, a row turning absent by itself, a white pop for
    0.35 s on a (re)apply, and nothing read from any aura API.

The mock is strict (a widget method it does not define fails as a nil call). Theme and the FrameHelpers aura
tile helper are STUBS here, and FS.GunsightAreas and FS.TargetDebuffs are fakes with the real API (their own
harnesses cover the real ones); the real Layout.lua and Gunsight.lua are loaded.

    python3 tools/gunsightdots-harness.py

Exit 0 = every check passed. GUNSIGHTDOTS_LUA=<path> runs another file in place of GunsightDots.lua.
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
ADDON = HERE.parent / "forever-stuwave"
DOTS = Path(os.environ.get("GUNSIGHTDOTS_LUA") or ADDON / "Modules/CombatHud/GunsightDots.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
AREAS = ADDON / "Modules/CombatHud/GunsightAreas.lua"
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = HERE.parent / "mockups" / "gunsight-modules-concepts-v7-2026-10-08.html"


def _load_gunsight_harness():
    spec = importlib.util.spec_from_file_location("gunsight_harness", HERE / "gunsight-harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup_v7() -> dict:
    """Everything dotsH and dotsV own, read out of the v7 mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    top, tbot, pdiv = (int(v) for v in _m(r"var TOP=(\d+),TBOT=(\d+),PITCH=\(TBOT-TOP\)/(\d+),", src, "TOP / TBOT / PITCH").groups())
    hz = int(_m(r"var HZ=(\d+);", src, "HZ").group(1))
    upper_y, area_h = (int(v) for v in _m(r"emptySlot\((\d+),(\d+),'UPPER AREA, EMPTY'\)", src, "upper area").groups())
    lower_y = int(_m(r"emptySlot\((\d+),\d+,'LOWER AREA, EMPTY'\)", src, "lower area").group(1))
    area_x, area_w = (int(v) for v in _m(r'<rect x="(\d+)" y="\'\+y\+\'" width="(\d+)"', src, "area x and width").groups())
    chip_x, chip_dy, chip = (int(v) for v in _m(r"chipIcon\((\d+),cy-(\d+),(\d+),d,abs\)", src, "H chip").groups())
    stack_x, stack_size = (int(v) for v in _m(r"txt\((\d+),cy\+4,'x'\+d\.n,(\d+),C\.white\)", src, "H stacks").groups())
    abs_x, abs_size = (int(v) for v in _m(r"txt\((\d+),cy\+4\.5,'--',(\d+),C\.muted,\{op:\.7\}\)", src, "H absent dash").groups())
    abs_bar_a = float(_m(r"rect\(\d+,cy-2,\d+,4,C\.muted,(\.\d+)\)", src, "H absent bar").group(1))
    time_x, tenths, time_size = (int(v) for v in _m(
        r"txt\((\d+),cy\+4\.5,\(d\.rem<(\d+)\?d\.rem\.toFixed\(1\):Math\.round\(d\.rem\)\)\+'s',(\d+),band\?C\.amber:C\.white\)", src, "H time").groups())
    bar_x, bar_w, bar_secs = (int(v) for v in _m(
        r"rect\((\d+),cy-2,(\d+),4,col,\.2\)\+rect\(\1,cy-2,\2\*d\.rem/(\d+),4,col\)", src, "H drain bar").groups())
    bar_h = 4
    bar_bg_a = float(_m(r"rect\(\d+,cy-2,\d+,4,col,(\.\d+)\)\+rect", src, "H bar background alpha").group(1))
    band_s = int(_m(r"band=!abs&&d\.rem<=(\d+)", src, "band seconds").group(1))
    sep_x0, sep_x1, sep_hz, sep_a = _m(
        r"line\((\d+),ty,(\d+),ty,C\.violet,k===5\?(\.\d+):(\.\d+),1\)", src, "H separators").groups()
    sep_x0, sep_x1, sep_hz, sep_a = int(sep_x0), int(sep_x1), float(sep_hz), float(sep_a)
    tick_x0, tick_x1, tick_a = (float(v) for v in _m(r"line\((\d+),ty,(\d+),ty,C\.pink,(\.\d+),1\)", src, "H pink ticks").groups())
    # V
    axt, axb = (int(v) for v in _m(r"var AXT=(\d+),AXB=(\d+);", src, "AXT / AXB").groups())
    dot_ax, lanes = _m(r"var DOT_AX=(\d+),LANE=\[([\d,]+)\];", src, "DOT_AX / LANE").groups()
    lanes = [int(v) for v in lanes.split(",")]
    ax, end, shift = (int(v) for v in _m(r"AX=(\d+),END=(\d+),LV=LANE\.map\(function\(x\)\{return x-(\d+);\}\)", src, "AX / END / LV").groups())
    hdr_x, hdr_y, hdr_size = (int(v) for v in _m(r"txt\((\d+),(\d+),'TARGET DEBUFFS',(\d+),C\.violet,\{a:'end',op:\.9\}\)", src, "header").groups())
    band_fill = float(_m(r"rect\(AX,yb,END-AX,AXB-yb,C\.amber,(\.\d+)\)", src, "V band fill").group(1))
    band_dash = [int(v) for v in _m(r"line\(AX,yb,END,yb,C\.amber,\.75,1,'(\d+) (\d+)'\)", src, "V band dash").groups()]
    guide_a = float(_m(r"line\(LV\[i\],AXT,LV\[i\],AXB,C\.violet,(\.\d+),1,'2 6'\)", src, "V guides").group(1))
    guide_dash = [int(v) for v in _m(r"line\(LV\[i\],AXT,LV\[i\],AXB,C\.violet,\.\d+,1,'(\d+) (\d+)'\)", src, "V guide dash").groups()]
    ax_up, ax_dn = (int(v) for v in _m(r"line\(AX,AXT-(\d+),AX,AXB\+(\d+),C\.violet,\.85,1\.2\)", src, "V axis ends").groups())
    maj_len, min_len = (int(v) for v in _m(r"line\(AX,y,AX\+\(maj\?(\d+):(\d+)\),y,C\.violet", src, "V tick lengths").groups())
    maj = int(_m(r"maj=s%(\d+)===0", src, "V major step").group(1))
    label_dx, label_size = (int(v) for v in _m(r"txt\(AX\+(\d+),y\+4,String\(s\),(\d+),C\.fg", src, "V labels").groups())
    refresh_dx, refresh_size = (int(v) for v in _m(r"txt\(END\+(\d+),\(yb\+AXB\)/2\+3,'REFRESH',(\d+),", src, "V REFRESH").groups())
    v_chip = int(_m(r"ch\(x-12,y-12,(\d+),\d+,5\)", src, "V chip").group(1))
    css = {n: v.lower() for n, v in re.findall(r"\b(fg|muted|white|violet|amber|pink):'(#[0-9a-fA-F]{6})'", src)}
    for need in ("fg", "muted", "white", "violet", "amber"):
        if need not in css:
            sys.exit(f"mockup: colour token {need} missing")
    return dict(
        TOP=top, TBOT=tbot, PITCH=(tbot - top) / pdiv, HZ=hz,
        AREA_X=area_x, AREA_W=area_w, AREA_H=area_h, UPPER_Y=upper_y, LOWER_Y=lower_y,
        CHIP_X=chip_x, CHIP_DY=chip_dy, CHIP=chip, STACK_X=stack_x, STACK_SIZE=stack_size,
        ABS_X=abs_x, ABS_SIZE=abs_size, ABS_BAR_A=abs_bar_a,
        TIME_X=time_x, TENTHS=tenths, TIME_SIZE=time_size, BAR_X=bar_x, BAR_W=bar_w, BAR_H=bar_h, BAR_SECS=bar_secs,
        BAR_BG_A=bar_bg_a, BAND_S=band_s, SEP_X0=sep_x0, SEP_X1=sep_x1, SEP_A=sep_a, SEP_HZ=sep_hz,
        TICK_X0=tick_x0, TICK_X1=tick_x1, TICK_A=tick_a,
        AXT=axt, AXB=axb, DOT_AX=int(dot_ax), LANES=lanes, AX=ax, END=end, LV_SHIFT=shift,
        HDR_X=hdr_x, HDR_Y=hdr_y, HDR_SIZE=hdr_size, V_BAND_FILL=band_fill, V_BAND_DASH=band_dash,
        GUIDE_A=guide_a, GUIDE_DASH=guide_dash, AX_UP=ax_up, AX_DN=ax_dn, MAJ=maj, MAJ_LEN=maj_len, MIN_LEN=min_len,
        LABEL_DX=label_dx, LABEL_SIZE=label_size, REFRESH_DX=refresh_dx, REFRESH_SIZE=refresh_size, V_CHIP=v_chip,
        CSS=css,
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
# The mock client
# ---------------------------------------------------------------------------------------

MOCK = r"""
FRAMES = {}
TEXTURES = {}
FONTSTRINGS = {}
PRINTED = {}
IN_COMBAT = false
DEGRADED = {}
SlashCmdList = {}
NOW = 5000
AURA_TOUCHED = {}

function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    PRINTED[#PRINTED + 1] = table.concat(t, " ")
end
-- The real ordering: PLAYER_REGEN_DISABLED fires just BEFORE lockdown begins, so InCombatLockdown() reads
-- false for the whole dispatch of that event and true afterwards; PLAYER_REGEN_ENABLED fires with lockdown
-- already off. IN_COMBAT is the truth after the event; IN_REGEN_DISABLED is true only during that dispatch.
-- UnitAffectingCombat flips with the fight (AFFECTING, when set, overrides it to model a reload).
IN_REGEN_DISABLED = false
AFFECTING = nil
function InCombatLockdown()
    if IN_REGEN_DISABLED then return false end
    return IN_COMBAT
end
function UnitAffectingCombat()
    if AFFECTING ~= nil then return AFFECTING end
    return IN_COMBAT
end
function GetTime() return NOW end
function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg, eps)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < (eps or 1e-6),
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a } end

-- No aura API may ever be read from here: the DoT ledger is the only combat-safe source.
for _, name in ipairs({ "UnitAura", "UnitBuff", "UnitDebuff", "GetAuraDataByIndex", "GetPlayerAuraBySpellID" }) do
    _G[name] = function() AURA_TOUCHED[#AURA_TOUCHED + 1] = name; error("aura API read: " .. name) end
end
C_UnitAuras = setmetatable({}, { __index = function(_, k)
    return function() AURA_TOUCHED[#AURA_TOUCHED + 1] = "C_UnitAuras." .. k; error("aura API read: C_UnitAuras." .. k) end
end })

local ANCHOR = {
    TOPLEFT = { -0.5, 0.5 }, TOP = { 0, 0.5 }, TOPRIGHT = { 0.5, 0.5 },
    LEFT = { -0.5, 0 }, CENTER = { 0, 0 }, RIGHT = { 0.5, 0 },
    BOTTOMLEFT = { -0.5, -0.5 }, BOTTOM = { 0, -0.5 }, BOTTOMRIGHT = { 0.5, -0.5 },
}

local Frame = {}
Frame.__index = Frame

local function newRegion(kind, parent)
    return setmetatable({
        kind = kind, parent = parent, points = {}, w = 0, h = 0, alpha = 1, shown = true,
        strata = "MEDIUM", level = 1, events = {}, scripts = {}, mouse = true, children = {},
        setPointCalls = 0,
    }, Frame)
end

-- SetPoint REPLACES an anchor of the same point name, like the client.
function Frame:SetPoint(point, rel, relPoint, x, y)
    self.setPointCalls = self.setPointCalls + 1
    check(ANCHOR[point], "bad anchor point " .. tostring(point))
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    if rel == nil then rel = self.parent end
    check(rel ~= nil, "SetPoint with no relative frame")
    local entry = { point, rel, relPoint or point, x or 0, y or 0 }
    for i, p in ipairs(self.points) do
        if p[1] == point then self.points[i] = entry; return end
    end
    self.points[#self.points + 1] = entry
end
function Frame:ClearAllPoints() self.points = {} end
function Frame:GetNumPoints() return #self.points end
function Frame:GetPoint(i)
    local p = self.points[i or 1]
    if not p then return nil end
    return p[1], p[2], p[3], p[4], p[5]
end
function Frame:SetAllPoints(rel)
    self.points = {}
    self.allPoints = rel or self.parent
end
function Frame:SetSize(w, h) self.w, self.h = w, h end
function Frame:SetWidth(w) self.w = w end
function Frame:SetHeight(h) self.h = h end
function Frame:GetWidth() return self.w end
function Frame:GetHeight() return self.h end
function Frame:SetAlpha(a) self.alpha = a end
function Frame:GetAlpha() return self.alpha end
-- `writes` counts every visibility write, so a case can prove a frame is written only when its answer changes.
function Frame:Show() self.writes = (self.writes or 0) + 1; self.shown = true end
function Frame:Hide() self.writes = (self.writes or 0) + 1; self.shown = false end
function Frame:SetShown(on) self.writes = (self.writes or 0) + 1; self.shown = on and true or false end
function Frame:IsShown() return self.shown end
function Frame:GetParent() return self.parent end
function Frame:SetParent(p) self.parent = p end
function Frame:SetFrameStrata(s) self.strata = s end
function Frame:GetFrameStrata() return self.strata end
function Frame:SetFrameLevel(l) self.level = l end
function Frame:GetFrameLevel() return self.level end
function Frame:IsProtected() return false, false end
function Frame:EnableMouse(on) self.mouse = on and true or false end
function Frame:IsMouseEnabled() return self.mouse end
function Frame:RegisterEvent(e) self.events[e] = true end
-- RegisterUnitEvent: the client only delivers the event for the listed units, so fire() filters by arg 1.
function Frame:RegisterUnitEvent(e, ...)
    self.events[e] = true
    self.unitOnly = self.unitOnly or {}
    self.unitOnly[e] = { ... }
end
function Frame:UnregisterEvent(e) self.events[e] = nil end
function Frame:SetScript(name, fn) self.scripts[name] = fn end
function Frame:GetScript(name) return self.scripts[name] end
function Frame:HookScript() error("HookScript is not mocked") end

function Frame:CreateTexture(name, layer, template, sublevel)
    local t = newRegion("Texture", self)
    t.layer, t.sublevel = layer, sublevel
    t.desaturated = false
    t.vertex = { 1, 1, 1, 1 }
    function t:SetColorTexture(r, g, b, a) self.color = { r, g, b, a }; self.path = nil; self.gradient = nil end
    function t:SetTexture(p) self.path = p; self.color = nil end
    function t:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a == nil and 1 or a } end
    function t:SetDesaturated(on) self.desaturated = on and true or false end
    function t:SetBlendMode(m) self.blend = m end
    function t:SetTexCoord(...) self.texcoord = { ... } end
    function t:SetDrawLayer(l, s) self.layer, self.sublevel = l, s end
    function t:SetTextureSliceMargins(a, b, c, d) self.slice = { a, b, c, d } end
    function t:SetTextureSliceMode(m) self.sliceMode = m end
    function t:SetGradient(orientation, minC, maxC)
        check(orientation == "VERTICAL" or orientation == "HORIZONTAL", "gradient orientation")
        check(type(minC) == "table" and type(maxC) == "table", "gradient colours")
        self.gradient = { orientation = orientation, min = minC, max = maxC }
    end
    self.children[#self.children + 1] = t
    TEXTURES[#TEXTURES + 1] = t
    return t
end
function Frame:CreateFontString(name, layer, template)
    local s = newRegion("FontString", self)
    s.layer = layer
    -- The client throws "Font not set" for SetText / SetFormattedText on a FontString with no font: one
    -- made with an inherits template carries that template's font, otherwise SetFont / SetFontObject (or
    -- Theme.ApplyMono, which calls SetFont) must come first. A write before that kills a pcall'd build.
    if type(template) == "string" then s.hasFont = true end
    function s:SetText(t)
        if not self.hasFont then error("Font not set", 2) end
        self.text = t
    end
    function s:SetFormattedText(fmt, ...)
        if not self.hasFont then error("Font not set", 2) end
        self.text = string.format(fmt, ...)
    end
    function s:GetText() return self.text end
    function s:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a } end
    function s:SetFontObject() self.hasFont = true end
    function s:SetFont(path, size, flags) self.hasFont = true; self.font = { path, size, flags } end
    function s:GetFont() return self.font and self.font[1], self.font and self.font[2], self.font and self.font[3] end
    function s:SetJustifyH(j) self.justifyH = j end
    function s:SetJustifyV(j) self.justifyV = j end
    function s:SetDrawLayer(l, sub) self.layer, self.sublevel = l, sub end
    function s:SetShadowColor() end
    function s:SetWordWrap() end
    self.children[#self.children + 1] = s
    FONTSTRINGS[#FONTSTRINGS + 1] = s
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
        g.anims[#g.anims + 1] = a
        return a
    end
    function g:SetScript(n, fn) self.scripts[n] = fn end
    function g:SetToFinalAlpha(v) self.finalAlpha = v end
    function g:Play() self.playing = true; PLAYING[self] = true end
    function g:Stop() self.playing = false; PLAYING[self] = nil end
    function g:IsPlaying() return self.playing end
    return g
end

function CreateFrame(kind, name, parent, template)
    check(kind == "Frame", "mock only builds plain Frames, got " .. tostring(kind))
    check(template == nil, "mock builds no templated frames, got " .. tostring(template))
    local f = newRegion("Frame", parent)
    f.name = name
    if parent then f.level = parent.level + 1 end      -- the client: a new frame stacks one above its parent
    FRAMES[#FRAMES + 1] = f
    if parent then parent.children[#parent.children + 1] = f end
    if name then _G[name] = f end
    return f
end

UIParent = newRegion("Frame", nil)
UIParent.name = "UIParent"
function SetScreen(h)
    UIParent.h = h
    UIParent.w = h * 16 / 9
end

function fire(event, ...)
    local list = {}
    for _, f in ipairs(FRAMES) do
        local only = f.unitOnly and f.unitOnly[event]
        local wanted = true
        if only then
            wanted = false
            for _, u in ipairs(only) do if u == (...) then wanted = true end end
        end
        if wanted and f.events[event] and f.scripts.OnEvent then list[#list + 1] = f end
    end
    if event == "PLAYER_REGEN_DISABLED" then IN_REGEN_DISABLED = true end
    local args = { ... }
    local nargs = select("#", ...)
    local ok, err = pcall(function()
        for _, f in ipairs(list) do f.scripts.OnEvent(f, event, unpack(args, 1, nargs)) end
    end)
    IN_REGEN_DISABLED = false
    if not ok then error(err, 0) end
end

local function visible(f)
    while f do
        if f.shown == false then return false end
        f = f.parent
    end
    return true
end
function isVisible(f) return visible(f) end

-- Advances the clock and runs every OnUpdate the client would run (shown frames only).
function tick(dt)
    NOW = NOW + dt
    local list = {}
    for _, f in ipairs(FRAMES) do
        if f.scripts.OnUpdate and visible(f) then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f.scripts.OnUpdate(f, dt) end
end
function onUpdateFrames()
    local n = 0
    for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then n = n + 1 end end
    return n
end

local function position(f, point)
    if f == UIParent then
        local a = ANCHOR[point]
        return a[1] * f.w, a[2] * f.h
    end
    local p = f.points[1]
    check(p, "region has no single anchor (name " .. tostring(f.name) .. ", kind " .. tostring(f.kind) .. ")")
    check(#f.points == 1, "region has more than one anchor: harness resolves single anchors only")
    local rx, ry = position(p[2], p[3])
    local ax, ay = rx + p[4], ry + p[5]
    local mine = ANCHOR[p[1]]
    local cx, cy = ax - mine[1] * f.w, ay - mine[2] * f.h
    local want = ANCHOR[point]
    return cx + want[1] * f.w, cy + want[2] * f.h
end
function centerOf(f) return position(f, "CENTER") end

-- A region's rect in mockup IMAGE px: left, top (y down), width, height.
function imgRect(f)
    local k = 1.28 * FS.Layout.Scale()
    local rx, ry = position(FS.Gunsight.root, "CENTER")
    local l, t = position(f, "TOPLEFT")
    local G = FS.Gunsight.G
    return G.CX + (l - rx) / k, G.CY - (t - ry) / k, f.w / k, f.h / k
end
function imgCenter(f)
    local l, t, w, h = imgRect(f)
    return l + w / 2, t + h / 2
end

local function wipeList(t) for i = #t, 1, -1 do t[i] = nil end end
function resetWorld()
    wipeList(FRAMES); wipeList(TEXTURES); wipeList(FONTSTRINGS); wipeList(PRINTED); wipeList(SUBS)
    wipeList(SKIN_CALLS); wipeList(AURA_TOUCHED)
    for k in pairs(DEGRADED) do DEGRADED[k] = nil end
    for k in pairs(PLAYING) do PLAYING[k] = nil end
    STATE, IN_COMBAT, IN_REGEN_DISABLED, AFFECTING = nil, false, false, nil
    FS = {}
    FS.LogDegradeOnce = function(key, msg) DEGRADED[key] = msg end
end

FS = {}
function FS.LogDegradeOnce(key, msg) DEGRADED[key] = msg end

function loadAddonFile(src, name)
    local fn, err = loadstring(src, "@" .. name)
    if not fn then error(err) end
    return fn("forever-stuwave", FS)
end

SKIN_CALLS = {}
SUBS = {}
STATE = nil
PROFILE = nil

-- Stubs for Theme and the FrameHelpers aura tile. They are strict about call order, which is
-- the contract GunsightDots.lua relies on: size first, then SkinButton, then the tile seat.
function stubTheme_()
    local Theme = {
        COLOR_BORDER = { 0.659, 0.333, 0.969, 1 },
        COLOR_AMBER = { 1, 0.7137, 0.2824, 1 },
        COLOR_STEEL = { 0.5529, 0.5765, 0.6510, 1 },
        FONT_MONO = "mono.ttf",
        SLICE_CUT2_FILL_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_fill.tga",
        SLICE_CUT2_BUTTON_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\slice_cut2_button.tga",
    }
    function Theme.ApplyMono(fs, size, color) fs.monoSize = size; fs.monoColor = color; fs.hasFont = true end  -- the real one calls SetFont
    function Theme.ApplyNineSlice(tex, margin) tex.margin = margin; return true end
    function Theme.AddSliceTexture(frame, path, color, layer, sublevel)
        local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
        t:SetTexture(path)
        t:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
        t:SetSize(frame.w, frame.h)
        if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
        t.slicePath = path
        return t
    end
    function Theme.SkinButton(button, opts)
        check(button.w > 0 and button.h > 0, "SkinButton before the chip has a size (the chamfer comes from the height)")
        check(button.icon, "SkinButton before button.icon exists")
        SKIN_CALLS[#SKIN_CALLS + 1] = { button = button, opts = opts }
        local c = opts and opts.borderColor or Theme.COLOR_BORDER
        local glow = button:CreateTexture(nil, "OVERLAY", nil, 0)
        glow:SetBlendMode("ADD")
        glow:SetVertexColor(c[1], c[2], c[3], 0.35)
        local ring = button:CreateTexture(nil, "OVERLAY", nil, 1)
        ring:SetVertexColor(c[1], c[2], c[3], 1)
        button.fsSkin = { chamfer = 6, glow = glow, border = { ring = ring } }
        return button.fsSkin
    end
    FS.Theme = Theme
    FS.FrameHelpers = {
        SeatAuraTile = function(button)
            check(button.fsSkin, "SeatAuraTile before Theme.SkinButton")
            button.fsAuraPlate = button:CreateTexture(nil, "BACKGROUND", nil, -8)
            button.fsAuraPlate.seated = true
            button.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
            button.seatedBy = "SeatAuraTile"
        end,
        SeatCutIcon = function(button) button.seatedBy = "SeatCutIcon" end,
    }
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


PRELUDE = r"""
local K = 1.28
local RECTS = {
    upper = { x = MU.AREA_X, y = MU.UPPER_Y, w = MU.AREA_W, h = MU.AREA_H },
    lower = { x = MU.AREA_X, y = MU.LOWER_Y, w = MU.AREA_W, h = MU.AREA_H },
}
local function near3(a, b, what) near(a, b, what, 1e-3) end
local function same(a, b) return math.abs(a - b) < 1e-3 end
local function colorIs(c, want, what)
    check(c and same(c[1], want[1]) and same(c[2], want[2]) and same(c[3], want[3]),
        string.format("%s: got %s, want %.3f %.3f %.3f", what, c and string.format("%.3f %.3f %.3f", c[1], c[2], c[3]) or "nil", want[1], want[2], want[3]))
end
local function mix(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end

-- A secret value: any touch but passing it along throws.
local function boom() error("secret value touched", 2) end
SECRETV = setmetatable({}, { __lt = boom, __le = boom, __add = boom, __sub = boom, __mul = boom, __div = boom,
    __concat = boom, __len = boom, __unm = boom, __index = boom, __call = boom })
SECRET_FN = function(v) return rawequal(v, SECRETV) end

MODULES, PIECE_CALLS, TDSUBS = {}, {}, {}
TDLIST, TDEPOCH = {}, 1

local function boot(opts)
    opts = opts or {}
    resetWorld()
    MODULES, PIECE_CALLS, TDSUBS, TDLIST, TDEPOCH = {}, {}, {}, {}, 1
    IN_COMBAT = opts.combat ~= false
    AFFECTING = opts.affecting
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db or {}
    FS.IsSecret = function(v) return SECRET_FN(v) end
    stubTheme_()
    if opts.realareas then assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))() end
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    local realPiece = FS.Gunsight.RegisterPiece
    FS.Gunsight.RegisterPiece = function(key, spec) PIECE_CALLS[#PIECE_CALLS + 1] = key; return realPiece(key, spec) end
    if opts.realareas then
        loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
    elseif not opts.noareas then
        FS.GunsightAreas = {
            RegisterModule = function(id, spec) MODULES[id] = spec; return true end,
            AreaOf = function() return nil end,
            OnAreaChanged = function() end,
        }
    end
    FS.TargetDebuffs = {
        Subscribe = function(fn) TDSUBS[#TDSUBS + 1] = fn; fn(TDLIST, TDEPOCH) end,
        Unsubscribe = function(fn) for i = #TDSUBS, 1, -1 do if TDSUBS[i] == fn then table.remove(TDSUBS, i) end end end,
        Get = function() return TDLIST end,
        Epoch = function() return TDEPOCH end,
    }
    UnitClass = function() return "Class", "WARRIOR" end
    loadAddonFile(DOTS_SRC, "Modules/CombatHud/GunsightDots.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    fire("PLAYER_LOGIN")
    return FS.GunsightDots
end

-- What GunsightAreas does for a module: build, seat, show, onShow.
local function mount(id, area, rect)
    local host = CreateFrame("Frame", "Host_" .. id, FS.Gunsight.root)
    local spec = MODULES[id]
    check(spec, "module not registered: " .. tostring(id))
    local frame = spec.build(host)
    spec.seat(rect or RECTS[area])
    frame:Show()
    spec.onShow(area)
    return FS.GunsightDots.modules[id], frame, spec
end

local nid = 0
-- rem: seconds left, 0 = absent (expiry in the past), nil = unknown duration.
local function ent(name, rem, o)
    o = o or {}
    nid = nid + 1
    local e = { name = name, icon = (not o.noicon) and (9000 + nid) or nil, count = o.count or 1, order = nid, duration = o.duration or 18 }
    if rem == nil then e.expires = nil elseif rem <= 0 then e.expires = 0 else e.expires = NOW + rem end
    return e
end
local function pushList(list, epoch)
    TDLIST = list
    if epoch then TDEPOCH = epoch end
    for _, fn in ipairs({ unpack(TDSUBS) }) do fn(TDLIST, TDEPOCH) end
end
local function rowCenterY(top, j) return top + MU.PITCH * (j - 0.5) end
local function liveRows(m) local n = 0 for _, r in ipairs(m.rows) do if r.mode == "live" then n = n + 1 end end return n end
"""

case("constants_match_the_mockup")(r"""
local D = boot()
local H, V, C = D.H, D.V, D.D
check(type(H) == "table" and type(V) == "table" and type(C) == "table", "FS.GunsightDots.D, .H and .V are the constants tables")
local function eq(a, b, what) near(a, b, what .. " (GunsightDots has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")") end
eq(H.PITCH, MU.PITCH, "row pitch"); eq(H.MAX_ROWS, 5, "rows per area")
eq(H.TOP_UPPER, MU.TOP - MU.UPPER_Y, "upper row top"); eq(H.TOP_LOWER, MU.HZ - MU.LOWER_Y, "lower row top")
eq(H.CHIP, MU.CHIP, "chip size"); eq(H.CHIP_DX, MU.CHIP_X - MU.AREA_X, "chip x")
eq(H.TIME_DX, MU.TIME_X - MU.AREA_X, "time x"); eq(H.TIME_SIZE, MU.TIME_SIZE, "time font"); eq(H.TENTHS_S, MU.TENTHS, "tenths below")
eq(H.BAR_DX, MU.BAR_X - MU.AREA_X, "bar x"); eq(H.BAR_W, MU.BAR_W, "bar width"); eq(H.BAR_H, MU.BAR_H, "bar height")
eq(H.BAR_BG_A, MU.BAR_BG_A, "bar background alpha"); eq(H.ABSENT_BAR_A, MU.ABS_BAR_A, "absent bar alpha")
eq(H.STACK_DX, MU.STACK_X - MU.AREA_X, "stack x"); eq(H.STACK_SIZE, MU.STACK_SIZE, "stack font")
eq(H.SEP_W, MU.SEP_X1 - MU.SEP_X0, "rule width"); eq(H.SEP_A, MU.SEP_A, "rule alpha"); eq(H.SEP_HZ_A, MU.SEP_HZ, "horizon rule alpha")
eq(H.TICK_DX, MU.TICK_X0 - MU.AREA_X, "tick x"); eq(H.TICK_A, MU.TICK_A, "tick alpha")
eq(C.MAX_S, MU.BAR_SECS, "drain seconds"); eq(C.BAND_S, MU.BAND_S, "band seconds")
eq(V.AXT_DY, MU.AXT - MU.UPPER_Y, "axis top"); eq(V.AXB_DY, MU.AXB - MU.UPPER_Y, "axis bottom"); eq(V.SPAN, MU.AXB - MU.AXT, "axis span")
eq(V.AX_DX, MU.AX - MU.AREA_X, "axis x"); eq(V.END_DX, MU.END - MU.AREA_X, "band end")
for i = 1, 4 do eq(V.LANE_DX[i], MU.LANES[i] - MU.LV_SHIFT - MU.AREA_X, "lane " .. i) end
eq(V.AX_UP, MU.AX_UP, "axis overshoot up"); eq(V.AX_DN, MU.AX_DN, "axis overshoot down")
eq(V.HDR_DX, MU.HDR_X - MU.AREA_X, "header x"); eq(V.HDR_DY, MU.HDR_Y - MU.UPPER_Y, "header y"); eq(V.HDR_SIZE, MU.HDR_SIZE, "header font")
eq(V.MAJ, MU.MAJ, "major tick step"); eq(V.MAJ_LEN, MU.MAJ_LEN, "major tick length"); eq(V.MIN_LEN, MU.MIN_LEN, "minor tick length")
eq(V.LABEL_DX, MU.LABEL_DX, "label x"); eq(V.LABEL_SIZE, MU.LABEL_SIZE, "label font")
eq(V.REFRESH_DX, MU.REFRESH_DX, "REFRESH x"); eq(V.REFRESH_SIZE, MU.REFRESH_SIZE, "REFRESH font")
eq(V.BAND_FILL, MU.V_BAND_FILL, "band fill"); eq(V.GUIDE_A, MU.GUIDE_A, "guide alpha")
eq(V.GUIDE_DASH[1], MU.GUIDE_DASH[1], "guide dash"); eq(V.GUIDE_DASH[2], MU.GUIDE_DASH[2], "guide gap")
eq(V.BAND_DASH[1], MU.V_BAND_DASH[1], "band dash"); eq(V.BAND_DASH[2], MU.V_BAND_DASH[2], "band gap")
eq(V.CHIP, MU.V_CHIP, "vertical chip size")
near(V.PX_PER_S, 112 / 30, "3.7 px a second", 1e-6)
local function rgb(hex) return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 } end
for _, name in ipairs({ "fg", "muted", "white", "violet", "amber" }) do colorIs(C.COLORS[name], rgb(MU.CSS[name]), "colour " .. name) end
""")

case("registers_two_modules_with_the_seam_and_no_dot_piece")(r"""
local D = boot()
for _, id in ipairs({ "debuffsH", "debuffsV" }) do
    local spec = MODULES[id]
    check(spec, id .. " is registered with FS.GunsightAreas")
    for _, fn in ipairs({ "build", "seat", "onShow", "onHide" }) do check(type(spec[fn]) == "function", id .. "." .. fn .. " is a function") end
end
check(D.registered == true, "FS.GunsightDots.registered reads true once both registered")
check(#PIECE_CALLS == 0, "GunsightAreas owns the dot piece: RegisterPiece was called " .. #PIECE_CALLS .. " times (" .. tostring(PIECE_CALLS[1]) .. ")")
check(FS.Gunsight.IsPieceOn("dot"), "the key stays known to the registry")
""")

case("nothing_is_built_until_the_areas_call_build")(r"""
local D = boot()
for _, f in ipairs(FRAMES) do check(not (f.name or ""):find("Debuffs"), "frame built at load: " .. tostring(f.name)) end
check(D.modules.debuffsH.built ~= true, "the horizontal module is not built before build()")
mount("debuffsH", "upper")
local found = false
for _, f in ipairs(FRAMES) do if f.name == "ForeverSTUwaveGunsightDebuffsH" then found = true end end
check(found, "build() makes the module frame")
local vfound = false
for _, f in ipairs(FRAMES) do if f.name == "ForeverSTUwaveGunsightDebuffsV" then vfound = true end end
check(not vfound, "the other module is still unbuilt")
""")

case("a_missing_areas_registry_loads_silently")(r"""
local D = boot({ noareas = true })
check(type(D) == "table", "the file still loads")
check(next(MODULES) == nil, "nothing to register with")
check(next(DEGRADED) == nil, "and nothing to log: " .. tostring(next(DEGRADED)))
FS.GunsightAreas = {}
loadAddonFile(DOTS_SRC, "Modules/CombatHud/GunsightDots.lua")
check(next(DEGRADED) == nil, "a registry without RegisterModule is silent too")
""")

case("horizontal_rows_follow_the_v7_layout_in_the_upper_area")(r"""
boot({ combat = true })
local m = mount("debuffsH", "upper")
local list = { ent("Rend", 9), ent("Deep Wounds", 12), ent("Thunder Clap", 2.8), ent("Sunder Armor", 22, { count = 5 }), ent("Demoralizing Shout", 26) }
pushList(list)
check(#m.rows == 5, "five rows are built, got " .. #m.rows)
local want = { "9s", "12s", "2.8s", "22s", "26s" }
local rem = { 9, 12, 2.8, 22, 26 }
for j = 1, 5 do
    local row = m.rows[j]
    local cy = rowCenterY(MU.TOP, j)
    check(row.mode == "live" and isVisible(row.frame), "row " .. j .. " is live and shown")
    local cx, cyy = imgCenter(row.chip.frame)
    near3(cx, MU.CHIP_X + MU.CHIP / 2, "row " .. j .. " chip x"); near3(cyy, cy, "row " .. j .. " chip y")
    near3(row.chip.frame:GetWidth(), MU.CHIP * K, "row " .. j .. " chip size")
    check(row.chip.frame.icon.path == list[j].icon, "row " .. j .. " shows the entry's icon")
    local tl, ty = imgRect(row.time)
    near3(tl, MU.TIME_X, "row " .. j .. " time x"); near3(ty, cy, "row " .. j .. " time y")
    near3(row.time.monoSize, MU.TIME_SIZE * K, "row " .. j .. " time font")
    check(row.time.text == want[j], "row " .. j .. " time, got " .. tostring(row.time.text) .. ", want " .. want[j])
    local bl, bt, bw, bh = imgRect(row.barBg)
    near3(bl, MU.BAR_X, "row " .. j .. " bar x"); near3(bw, MU.BAR_W, "row " .. j .. " bar width")
    near3(bt + bh / 2, cy, "row " .. j .. " bar y"); near3(bh, MU.BAR_H, "row " .. j .. " bar height")
    local fl, ft, fw = imgRect(row.fillTex)
    near3(fl, MU.BAR_X, "row " .. j .. " fill x"); near3(fw, MU.BAR_W * rem[j] / MU.BAR_SECS, "row " .. j .. " fill width")
    near3(row.barBg.color[4], MU.BAR_BG_A, "row " .. j .. " bar background alpha")
end
check(m.rows[4].stack.text == "x5", "the stack count reads x5, got " .. tostring(m.rows[4].stack.text))
local sl = imgRect(m.rows[4].stack)
near3(sl, MU.STACK_X, "stack x"); near3(m.rows[4].stack.monoSize, MU.STACK_SIZE * K, "stack font")
for _, j in ipairs({ 1, 2, 3, 5 }) do check(m.rows[j].stack.text == "", "row " .. j .. " has one stack: no text") end
""")

case("horizontal_rows_in_the_lower_area_start_at_the_horizon")(r"""
boot()
local m = mount("debuffsH", "lower")
pushList({ ent("Holy Vengeance", 12, { count = 5 }), ent("Hammer of Justice", 4) })
for j = 1, 2 do
    local _, cy = imgCenter(m.rows[j].chip.frame)
    near3(cy, rowCenterY(MU.HZ, j), "lower row " .. j .. " y")
end
local l = imgRect(m.rows[1].time)
near3(l, MU.TIME_X, "same x as the upper area")
""")

case("at_most_five_rows_per_area")(r"""
boot()
local m = mount("debuffsH", "upper")
local list = {}
for i = 1, 8 do list[i] = ent("Debuff " .. i, 10 + i) end
pushList(list)
check(#m.rows == 5, "never more than five rows, got " .. #m.rows)
check(m.rows[5].key == "Debuff 5", "the first five entries are the rows, got " .. tostring(m.rows[5].key))
local shown = 0
for _, r in ipairs(m.rows) do if isVisible(r.frame) then shown = shown + 1 end end
check(shown == 5, "five shown")
pushList({ list[1], list[2] })
shown = 0
for _, r in ipairs(m.rows) do if isVisible(r.frame) then shown = shown + 1 end end
check(shown == 2 and m.rows[3].mode == "off", "a shorter list hides the extra rows, shown " .. shown)
""")

case("time_text_is_whole_seconds_above_three_and_tenths_below")(r"""
boot()
local m = mount("debuffsH", "upper")
local function textFor(rem) pushList({ ent("Rend", rem) }); return m.rows[1].time.text end
check(textFor(13.4) == "13s", "13.4 reads 13s, got " .. textFor(13.4))
check(textFor(13.6) == "14s", "13.6 reads 14s, got " .. textFor(13.6))
check(textFor(2.6) == "2.6s", "2.6 reads 2.6s, got " .. textFor(2.6))
check(textFor(3) == "3s", "exactly 3 reads 3s, got " .. textFor(3))
check(textFor(0.4) == "0.4s", "0.4 reads 0.4s, got " .. textFor(0.4))
check(textFor(45) == "45s", "45 reads 45s, got " .. textFor(45))
check(textFor(130) == "2m", "130 reads 2m, got " .. textFor(130))
""")

case("the_drain_bar_runs_zero_to_thirty_seconds_and_turns_amber_at_three")(r"""
local D = boot()
local C = D.D.COLORS
local m = mount("debuffsH", "upper")
local function fillW(rem) pushList({ ent("Rend", rem) }); local _, _, w = imgRect(m.rows[1].fillTex); return w end
near3(fillW(15), MU.BAR_W / 2, "15 s is half the bar")
near3(fillW(45), MU.BAR_W, "past 30 s the bar is full")
near3(fillW(3), MU.BAR_W * 3 / 30, "3 s")
local row = m.rows[1]
pushList({ ent("Rend", 3) })
colorIs(row.time.textColor, C.amber, "time at 3 s"); colorIs(row.fillTex.color, C.amber, "fill at 3 s")
colorIs(row.barBg.color, C.amber, "bar background at 3 s"); colorIs(row.chip.frame.fsSkin.border.ring.vertex, C.amber, "ring at 3 s")
pushList({ ent("Rend", 3.5) })
colorIs(row.time.textColor, C.white, "time above 3 s"); colorIs(row.fillTex.color, mix(C.violet, { 1, 1, 1 }, 0.25), "fill above 3 s")
colorIs(row.chip.frame.fsSkin.border.ring.vertex, C.violet, "ring above 3 s")
""")

case("an_absent_row_is_dim_with_dashes_and_no_fill")(r"""
local D = boot()
local C = D.D.COLORS
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0), ent("Deep Wounds", 9) })
local row = m.rows[1]
check(row.mode == "absent", "mode absent, got " .. tostring(row.mode))
check(row.time.text == "--", "the time reads --, got " .. tostring(row.time.text))
colorIs(row.time.textColor, C.muted, "dash colour"); near3(row.time.textColor[4], 0.7, "dash alpha")
check(not row.fillTex:IsShown(), "no drain fill")
colorIs(row.barBg.color, C.muted, "bar background colour"); near3(row.barBg.color[4], MU.ABS_BAR_A, "bar background alpha")
check(row.chip.frame.icon.desaturated == true, "grey icon")
colorIs(row.chip.frame.fsSkin.border.ring.vertex, mix(C.muted, { 1, 1, 1 }, 0.25), "grey ring")
near3(row.chip.frame.fsSkin.glow.vertex[4], 0, "no glow")
check(isVisible(row.frame), "in combat the row shows")
local _, cy = imgCenter(row.chip.frame)
near3(cy, rowCenterY(MU.TOP, 1), "an absent row keeps its row")
""")

case("an_unknown_duration_shows_the_icon_and_dashes_in_and_out_of_combat")(r"""
local D = boot({ combat = false })
local m = mount("debuffsH", "upper")
pushList({ ent("Thunder Clap", nil) })
local row = m.rows[1]
check(row.mode == "unknown", "mode unknown, got " .. tostring(row.mode))
check(isVisible(row.frame), "an unknown row is shown out of combat (it is not the recast cue)")
check(row.time.text == "?", "an unknown duration reads ?, not the absent row's --, got " .. tostring(row.time.text))
check(row.chip.frame.icon.desaturated == false and row.chip.frame.icon.path ~= nil, "the icon is drawn normally")
check(not row.fillTex:IsShown(), "no fill without a duration")
check(not row.barBg:IsShown(), "no empty bar track for a duration nobody knows")
pushList({ ent("Thunder Clap", 9) })
check(row.mode == "live" and row.barBg:IsShown(), "a known duration brings the bar track back")
pushList({ ent("Thunder Clap", nil) })
check(not row.barBg:IsShown() and row.time.text == "?", "and an unknown one hides it again")
check(onUpdateFrames() == 0, "nothing to animate")
""")

case("the_ruler_rules_and_ticks_follow_the_area")(r"""
local D = boot()
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 9) })
local R, T = m.parts.rules, m.parts.ticks
for j = 0, 5 do
    local y = MU.TOP + MU.PITCH * j
    check(R[j]:IsShown(), "upper rule " .. j .. " is drawn")
    local l, _, w = imgRect(R[j]); local _, cy = imgCenter(R[j])
    near3(l, MU.SEP_X0, "rule " .. j .. " x"); near3(w, MU.SEP_X1 - MU.SEP_X0, "rule " .. j .. " width"); near3(cy, y, "rule " .. j .. " y")
    near3(R[j].color[4], j == 5 and MU.SEP_HZ or MU.SEP_A, "rule " .. j .. " alpha")
end
for j = 1, 5 do
    local l, _, w = imgRect(T[j]); local _, cy = imgCenter(T[j])
    near3(l, MU.TICK_X0, "tick " .. j .. " x"); near3(w, MU.TICK_X1 - MU.TICK_X0, "tick " .. j .. " width")
    near3(cy, MU.TOP + MU.PITCH * j, "tick " .. j .. " y"); near3(T[j].color[4], MU.TICK_A, "tick " .. j .. " alpha")
end
local L = boot()
local ml = mount("debuffsH", "lower")
pushList({ ent("Rend", 9) })
check(not ml.parts.rules[0]:IsShown(), "the lower area has no rule at the horizon (the divider is there)")
for j = 1, 5 do
    local _, cy = imgCenter(ml.parts.rules[j])
    check(ml.parts.rules[j]:IsShown(), "lower rule " .. j)
    near3(cy, MU.HZ + MU.PITCH * j, "lower rule " .. j .. " y"); near3(ml.parts.rules[j].color[4], MU.SEP_A, "lower rule alpha")
end
""")

case("rows_slide_on_one_onupdate_and_the_driver_stops_when_none_is_live")(r"""
boot()
local m, frame = mount("debuffsH", "upper")
pushList({ ent("Rend", 9), ent("Deep Wounds", 12) })
check(onUpdateFrames() == 1 and frame.scripts.OnUpdate, "one OnUpdate, on the module frame")
tick(1.0)
check(m.rows[1].time.text == "8s" and m.rows[2].time.text == "11s", "times follow GetTime, got " .. m.rows[1].time.text .. " " .. m.rows[2].time.text)
local _, _, w = imgRect(m.rows[1].fillTex)
near3(w, MU.BAR_W * 8 / 30, "the fill drains")
local writes = m.rows[1].fillTex.setPointCalls
tick(0.001)
check(m.rows[1].fillTex.setPointCalls == writes, "a steady frame re-anchors nothing")
tick(8)                                -- Rend runs out at 9 s (1.001 s are gone already)
check(m.rows[1].mode == "absent" and m.rows[1].time.text == "--", "an expiring row turns absent by itself")
check(m.rows[2].mode == "live", "the other keeps counting")
check(onUpdateFrames() == 1, "still one OnUpdate")
tick(5)
check(m.rows[2].mode == "absent" and onUpdateFrames() == 0, "the driver is gone with the last live row")
pushList({})
check(onUpdateFrames() == 0, "an empty list runs nothing")
""")

case("the_band_pulses_and_a_row_enters_it_by_itself")(r"""
local D = boot()
local C = D.D.COLORS
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 3.4) })
local row = m.rows[1]
colorIs(row.time.textColor, C.white, "outside the band")
tick(0.5)
colorIs(row.time.textColor, C.amber, "inside the band after 0.5 s")
colorIs(row.fillTex.color, C.amber, "fill turned amber with no push")
check(row.time.text == "2.9s", "tenths below three seconds, got " .. tostring(row.time.text))
""")

case("a_pop_flashes_on_apply_and_reapply_and_not_on_a_target_switch")(r"""
local D = boot()
local C = D.D.COLORS
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 12) }, 1)
local row = m.rows[1]
check(not row.chip.pop:IsShown(), "a debuff already up when first seen does not pop")
tick(5)
pushList({ ent("Rend", 17.9) }, 1)
check(row.chip.pop:IsShown(), "a reapply pops")
near3(row.chip.pop.vertex[4], D.D.POP_A, "starts at .8"); colorIs(row.chip.pop.vertex, C.white, "white")
tick(D.D.POP_S / 2)
near(row.chip.pop.vertex[4], D.D.POP_A * 0.5, "half way", 0.02)
tick(D.D.POP_S / 2 + 0.01)
check(not row.chip.pop:IsShown(), "the pop ends after 0.35 s")
local e = ent("Rend", 12.1 - 0.0); e.expires = row.expires + 0.1
pushList({ e }, 1)
check(not row.chip.pop:IsShown(), "a 0.1 s shift is not a reapply")
pushList({ ent("Rend", 0) }, 1)
pushList({ ent("Rend", 18) }, 1)
check(row.chip.pop:IsShown(), "absent to live on the same target pops")
pushList({ ent("Rend", 9) }, 2)
check(not row.chip.pop:IsShown(), "a new target's debuff that was already up does not pop")
pushList({ ent("Rend", 18, { duration = 18 }) }, 3)
check(row.chip.pop:IsShown(), "a fresh apply on a new target (remaining == duration) pops")
pushList({ ent("Sunder Armor", 18) }, 3)
check(not row.chip.pop:IsShown(), "another debuff in the same row is not a reapply")
""")

case("the_absent_cue_shows_only_in_combat_and_follows_the_events")(r"""
boot({ combat = false })
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0), ent("Deep Wounds", 10) })
local a, b = m.rows[1], m.rows[2]
check(a.mode == "absent" and not isVisible(a.frame), "out of combat the absent row is hidden")
check(isVisible(b.frame) and b.mode == "live", "the live row is drawn")
check(onUpdateFrames() == 1, "one OnUpdate, for the live row only")
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
check(isVisible(a.frame), "PLAYER_REGEN_DISABLED shows it with no push, even though lockdown reads false in the dispatch")
local w = a.frame.writes
fire("PLAYER_REGEN_DISABLED"); fire("PLAYER_REGEN_DISABLED")
check(a.frame.writes == w, "a steady state writes no visibility, got " .. (a.frame.writes - w))
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not isVisible(a.frame) and a.mode == "absent", "PLAYER_REGEN_ENABLED hides it again: hidden, not dropped")
check(isVisible(b.frame), "the live row never changes")
pushList({ ent("Rend", 0), ent("Deep Wounds", 10) })
check(not isVisible(a.frame), "a push out of combat keeps it hidden")
""")

case("lockdown_lagging_the_regen_enabled_event_does_not_keep_the_cue")(r"""
boot({ combat = true })
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0) })
check(isVisible(m.rows[1].frame), "setup: shown in combat")
InCombatLockdown = function() return true end
fire("PLAYER_REGEN_ENABLED")
check(not isVisible(m.rows[1].frame), "the event decides, not a live InCombatLockdown() read")
""")

case("a_reload_mid_combat_seeds_the_flag_from_either_api")(r"""
boot({ combat = false, affecting = true })
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0) })
check(isVisible(m.rows[1].frame), "UnitAffectingCombat true at build shows the cue")
boot({ combat = true, affecting = false })
m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0) })
check(isVisible(m.rows[1].frame), "InCombatLockdown true at build shows it")
boot({ combat = false, affecting = false })
m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0) })
check(not isVisible(m.rows[1].frame), "both false keeps it hidden")
IN_COMBAT, AFFECTING = false, true
fire("PLAYER_ENTERING_WORLD")
check(isVisible(m.rows[1].frame), "PLAYER_ENTERING_WORLD re-seeds and shows it")
IN_COMBAT, AFFECTING = false, false
fire("PLAYER_ENTERING_WORLD")
check(not isVisible(m.rows[1].frame), "and hides it again")
""")

case("an_unreadable_seed_keeps_the_cue_shown")(r"""
boot({ combat = false })
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0) })
local no = function() return false end
InCombatLockdown, UnitAffectingCombat = no, no
fire("PLAYER_ENTERING_WORLD")
check(not isVisible(m.rows[1].frame), "setup: hidden when both are plainly false")
InCombatLockdown = function() error("boom") end
fire("PLAYER_ENTERING_WORLD")
check(isVisible(m.rows[1].frame), "a throwing InCombatLockdown keeps it shown")
InCombatLockdown = no
fire("PLAYER_ENTERING_WORLD")
UnitAffectingCombat = function() return SECRETV end
fire("PLAYER_ENTERING_WORLD")
check(isVisible(m.rows[1].frame), "a secret UnitAffectingCombat keeps it shown")
""")

case("a_stuck_combat_flag_heals_from_a_push_but_a_push_never_sets_it")(r"""
boot({ combat = true })
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 0), ent("Deep Wounds", 10) })
check(isVisible(m.rows[1].frame), "setup: shown in combat")
IN_COMBAT = false                       -- the REGEN_ENABLED event never reached us
check(isVisible(m.rows[1].frame), "setup: still stuck")
pushList({ ent("Rend", 0), ent("Deep Wounds", 10) })
check(not isVisible(m.rows[1].frame), "a push that finds both APIs false clears the flag")
IN_COMBAT = true                        -- combat began, but REGEN_DISABLED was missed
pushList({ ent("Rend", 0), ent("Deep Wounds", 10) })
check(not isVisible(m.rows[1].frame), "a push never sets the flag")
""")

case("the_vertical_axis_geometry_is_112_px_with_the_axis_26_px_from_the_cast_bar")(r"""
local D = boot()
local C = D.D.COLORS
local m = mount("debuffsV", "upper")
local P = m.parts
pushList({ ent("Rend", 18) })
local G = FS.Gunsight.G
local l, t, w, h = imgRect(P.axis)
near3(l + w / 2, MU.AX, "axis x")
near3(l + w / 2 - G.TR.x1, 26, "26 px right of the target cast bar")
near3(t, MU.AXT - MU.AX_UP, "axis top"); near3(t + h, MU.AXB + MU.AX_DN, "axis bottom")
check(#P.ticks == 31, "31 ticks, got " .. #P.ticks)
local function secY(s) return MU.AXB - s / 30 * (MU.AXB - MU.AXT) end
near3(MU.AXB - MU.AXT, 112, "the scale is 112 px")
near3(secY(0) - secY(1), 112 / 30, "3.73 px a second")
for s = 0, 30 do
    local tl, _, tw = imgRect(P.ticks[s + 1]); local _, ty = imgCenter(P.ticks[s + 1])
    local maj = s % MU.MAJ == 0
    near3(ty, secY(s), "tick " .. s .. " y"); near3(tl, MU.AX, "tick " .. s .. " starts on the axis")
    near3(tw, maj and MU.MAJ_LEN or MU.MIN_LEN, "tick " .. s .. " points inward, length")
end
for s = 0, 30, 5 do
    local fs = P.labels[s]
    check(fs and fs.text == tostring(s), "label " .. s)
    local ll, ly = imgRect(fs)
    near3(ll, MU.AX + MU.LABEL_DX, "label " .. s .. " x (inside the scale)"); near3(ly, secY(s), "label " .. s .. " y")
    near3(fs.monoSize, MU.LABEL_SIZE * K, "label font")
end
local n = 0
for _, fs in ipairs(FONTSTRINGS) do if fs.text and tostring(fs.text):match("^%d+$") then n = n + 1 end end
check(n == 7, "labels at every fifth second only, got " .. n)
local bl, bt, bw, bh = imgRect(P.band)
near3(bl, MU.AX, "band left"); near3(bl + bw, MU.END, "band right")
near3(bt, secY(3), "band top is 3 s"); near3(bt + bh, MU.AXB, "band bottom is 0")
near3(P.band.color[4], MU.V_BAND_FILL, "band alpha"); colorIs(P.band.color, C.amber, "band colour")
local prevRight
for i, d in ipairs(P.bandTop) do
    local dl, _, dw = imgRect(d); local _, dy = imgCenter(d)
    near3(dy, secY(3), "band dash y")
    if i < #P.bandTop then near3(dw, MU.V_BAND_DASH[1], "band dash") else check(dw <= MU.V_BAND_DASH[1] + 1e-3, "last dash clipped") end
    if prevRight then near3(dl - prevRight, MU.V_BAND_DASH[2], "band gap") end
    prevRight = dl + dw
end
check(#P.bandTop >= 8, "dashed band top")
local el, _, ew = imgRect(P.bandBottom); local _, ey = imgCenter(P.bandBottom)
near3(el, MU.AX, "band bottom left"); near3(el + ew, MU.END, "band bottom right"); near3(ey, MU.AXB, "band bottom y")
check(#P.guides == 4, "four lane guides")
for lane = 1, 4 do
    for i, d in ipairs(P.guides[lane]) do
        local dl, dt, dw, dh = imgRect(d)
        near3(dl + dw / 2, MU.LANES[lane] - MU.LV_SHIFT, "guide " .. lane .. " x")
        check(dt >= MU.AXT - 1e-3 and dt + dh <= MU.AXB + 1e-3, "guide inside the axis")
        if i < #P.guides[lane] then near3(dh, MU.GUIDE_DASH[1], "guide dash") end
    end
    near3(select(2, imgRect(P.guides[lane][1])), MU.AXT, "guide starts at the top")
    near3(P.guides[lane][1].color[4], MU.GUIDE_A, "guide alpha")
end
check(P.header.text == "TARGET DEBUFFS", "header text")
local hl, hy = imgRect(P.header)
near3(hl, MU.HDR_X, "header right edge x"); near3(P.header.monoSize, MU.HDR_SIZE * K, "header font")
check(P.header.justifyH == "RIGHT", "header is right aligned")
local word = {}
for _, fs in ipairs(P.refresh) do word[#word + 1] = fs.text end
check(table.concat(word) == "REFRESH", "REFRESH letters, got " .. table.concat(word))
""")

case("vertical_chips_sit_on_their_lane_at_3_7_px_a_second")(r"""
local D = boot({ combat = true })
local C = D.D.COLORS
local m = mount("debuffsV", "upper")
local list = { ent("Corruption", 18), ent("Curse of Agony", 22), ent("Immolate", 2.4), ent("Siphon Life", 0) }
pushList(list)
local function secY(s) return MU.AXB - s / 30 * (MU.AXB - MU.AXT) end
local rem = { 18, 22, 2.4, 0 }
for i = 1, 4 do
    local row = m.rows[i]
    local cx, cy = imgCenter(row.chip.frame)
    near3(cx, MU.LANES[i] - MU.LV_SHIFT, "chip " .. i .. " lane x"); near3(cy, secY(rem[i]), "chip " .. i .. " y")
    near3(row.chip.frame:GetWidth(), MU.V_CHIP * K, "chip size")
end
check(m.rows[1].mode == "live" and m.rows[3].mode == "live" and m.rows[4].mode == "absent", "modes")
check(m.rows[1].rail:IsShown() and m.rows[1].dot:IsShown(), "a live chip has its rail and dot")
colorIs(m.rows[1].chip.frame.fsSkin.border.ring.vertex, C.violet, "violet outside the band")
colorIs(m.rows[3].chip.frame.fsSkin.border.ring.vertex, C.amber, "amber inside the band")
check(isVisible(m.rows[4].frame) and not m.rows[4].rail:IsShown(), "the absent chip rests at 0 with no rail")
check(m.rows[4].chip.frame.icon.desaturated == true, "grey")
local _, y10 = imgCenter(m.rows[1].chip.frame)
pushList({ ent("Corruption", 10) })
local _, y10b = imgCenter(m.rows[1].chip.frame)
near3(y10b - y10, 8 * 112 / 30, "eight seconds less is 29.9 px further down the axis")
""")

case("vertical_chips_slide_and_the_absent_chip_follows_combat")(r"""
boot({ combat = false })
local m, frame = mount("debuffsV", "upper")
pushList({ ent("Corruption", 0), ent("Immolate", 12) })
check(not isVisible(m.rows[1].frame), "out of combat the absent chip is hidden")
check(isVisible(m.rows[2].frame) and m.rows[2].rail:IsShown(), "the live one is drawn")
local _, y0 = imgCenter(m.rows[2].chip.frame)
tick(1.0)
local _, y1 = imgCenter(m.rows[2].chip.frame)
near3(y1 - y0, 112 / 30, "one second slides 3.73 px")
check(onUpdateFrames() == 1, "one OnUpdate")
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
check(isVisible(m.rows[1].frame), "the cue shows at pull")
tick(11.5)
check(m.rows[2].mode == "absent" and isVisible(m.rows[2].frame), "an expired chip becomes the recast cue")
near3(select(2, imgCenter(m.rows[2].chip.frame)), MU.AXB, "resting at 0")
check(onUpdateFrames() == 0, "no OnUpdate with nothing live")
""")

case("the_vertical_axis_takes_four_lanes_and_skips_entries_with_no_expiry")(r"""
boot()
local m = mount("debuffsV", "upper")
local list = { ent("Sunder Armor", nil), ent("A", 10), ent("B", 11), ent("C", 12), ent("D", 13), ent("E", 14) }
pushList(list)
check(#m.rows == 4, "four lanes, got " .. #m.rows)
check(m.rows[1].key == "A" and m.rows[4].key == "D", "an unknown duration has no place on the axis; the next entries take the lanes, got " .. tostring(m.rows[1].key))
pushList({ ent("Sunder Armor", nil) })
check(m.rows[1].mode == "off" and not isVisible(m.rows[1].frame), "only unknowns: nothing drawn")
check(not isVisible(m.parts.axis), "and the scale hides")
""")

case("the_vertical_scale_is_seated_from_the_lower_area_rect_too")(r"""
boot()
local m = mount("debuffsV", "lower")
pushList({ ent("Rend", 15) })
local lx, ly, lw, lh = RECTS.lower.x, RECTS.lower.y, RECTS.lower.w, RECTS.lower.h
local l, t, w, h = imgRect(m.parts.axis)
near3(l + w / 2, lx + MU.AX - MU.AREA_X, "axis x")
near3(t, ly + (MU.AXT - MU.UPPER_Y) - MU.AX_UP, "axis top follows the rect")
local _, cy = imgCenter(m.rows[1].chip.frame)
near3(cy, ly + (MU.AXB - MU.UPPER_Y) - 15 * 112 / 30, "chip y follows the rect")
""")

case("both_modules_run_side_by_side_with_their_own_subscriptions")(r"""
boot()
local mv = mount("debuffsV", "upper")
local mh = mount("debuffsH", "lower")
check(#TDSUBS == 2, "two subscriptions, got " .. #TDSUBS)
pushList({ ent("Rend", 9), ent("Deep Wounds", 12) })
check(mv.rows[1].mode == "live" and mh.rows[1].mode == "live", "both took the list")
check(onUpdateFrames() == 2, "one OnUpdate each, got " .. onUpdateFrames())
MODULES.debuffsH.onHide("lower")
check(#TDSUBS == 1 and onUpdateFrames() == 1, "hiding one leaves the other running")
check(mv.rows[1].mode == "live", "the vertical module is untouched")
""")

case("show_subscribes_once_and_hide_releases_everything")(r"""
boot()
local m, frame, spec = mount("debuffsH", "upper")
check(#TDSUBS == 1, "subscribed on show")
spec.onShow("upper")
check(#TDSUBS == 1, "a second onShow does not subscribe again")
pushList({ ent("Rend", 9) })
check(onUpdateFrames() == 1, "ticking")
spec.onHide("upper")
check(#TDSUBS == 0, "unsubscribed on hide")
check(onUpdateFrames() == 0, "OnUpdate cleared")
check(m.rows[1].mode == "off" and not isVisible(m.rows[1].frame) and not m.body:IsShown(), "rows forgotten and hidden")
local ok = pcall(pushList, { ent("Rend", 9) })
check(ok and m.rows[1].mode == "off" and onUpdateFrames() == 0, "a stale push after hide does nothing")
spec.onShow("lower")
check(#TDSUBS == 1 and m.rows[1].mode == "live", "show again replays the current list")
""")

case("an_empty_list_hides_the_body_and_the_scale")(r"""
boot()
local m = mount("debuffsH", "upper")
pushList({})
check(not m.body:IsShown(), "no rows: the ruler is not drawn")
pushList({ ent("Rend", 9) })
check(m.body:IsShown(), "a row brings it back")
local mv = mount("debuffsV", "lower")
pushList({})
check(not mv.body:IsShown(), "no lanes: no axis")
""")

case("a_rescale_reseats_rows_and_the_axis_in_image_pixels")(r"""
boot({ height = 1440 })
local m, _, spec = mount("debuffsH", "upper")
pushList({ ent("Rend", 15), ent("Deep Wounds", 6) })
SetScreen(1200)
fire("UI_SCALE_CHANGED")
spec.seat(RECTS.upper)
near3(m.rows[1].chip.frame:GetWidth(), 20 * K * 1200 / 1440, "chip size at 1200")
local cx, cy = imgCenter(m.rows[1].chip.frame)
near3(cx, MU.CHIP_X + MU.CHIP / 2, "chip x after the rescale"); near3(cy, rowCenterY(MU.TOP, 1), "chip y after the rescale")
local _, _, w = imgRect(m.rows[1].fillTex)
near3(w, MU.BAR_W * 15 / 30, "the drain keeps its width in image px")
check(m.rows[1].time.monoSize and math.abs(m.rows[1].time.monoSize - MU.TIME_SIZE * K * 1200 / 1440) < 1e-6, "text restyled")
-- the vertical one too
SetScreen(1440)
local mv, _, vspec = mount("debuffsV", "upper")
pushList({ ent("Corruption", 15) })
SetScreen(1200)
vspec.seat(RECTS.upper)
local _, ty = imgCenter(mv.rows[1].chip.frame)
near3(ty, MU.AXB - 15 * 112 / 30, "vertical chip y after the rescale")
""")

case("seat_copies_the_rect_and_does_not_keep_the_table")(r"""
boot()
local m, _, spec = mount("debuffsH", "upper")
pushList({ ent("Rend", 9) })
local shared = { x = MU.AREA_X, y = MU.LOWER_Y, w = MU.AREA_W, h = MU.AREA_H }
spec.seat(shared)
shared.y = 0                            -- GunsightAreas reuses one table per area
local _, cy = imgCenter(m.rows[1].chip.frame)
near3(cy, rowCenterY(MU.HZ, 1), "the row stays where it was seated")
spec.seat(RECTS.lower)
local _, cy2 = imgCenter(m.rows[1].chip.frame)
near3(cy2, rowCenterY(MU.HZ, 1), "moved to the lower area")
""")

case("secret_or_malformed_entries_never_throw_and_draw_nothing")(r"""
boot()
local m = mount("debuffsH", "upper")
local ok = pcall(pushList, {
    { name = SECRETV, icon = 1, expires = NOW + 5, count = 1 },
    { name = "Rend", icon = 1, expires = SECRETV, count = SECRETV, duration = SECRETV },
    { name = "Sunder Armor", icon = SECRETV, expires = NOW + 9, count = 3, duration = 30 },
    { name = "Expose Armor", icon = 5, expires = "soon", count = "x" },
    { name = "Garrote", icon = 5, expires = NOW + 7 },
})
check(ok, "a throw escaped the subscriber")
check(m.rows[1].mode == "off" and m.rows[2].mode == "off", "a secret name or expiry reads as unusable")
check(m.rows[3].mode == "live" and m.rows[3].chip.label:IsShown(), "a secret icon falls back to the abbreviation")
check(m.rows[3].stack.text == "x3", "plain stacks still show")
check(m.rows[4].mode == "off", "a string expiry is not a number")
check(m.rows[5].mode == "live" and m.rows[5].time.text == "7s", "the plain one is drawn")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("one_row_that_throws_does_not_strand_the_others")(r"""
boot()
local m = mount("debuffsH", "upper")
m.rows[1].chip.frame.icon.SetTexture = function() error("boom") end
local ok = pcall(pushList, { ent("Rend", 9), ent("Deep Wounds", 12), ent("Thunder Clap", 5) })
check(ok, "the throw never escapes the subscriber")
check(m.rows[1].mode == "off" and not isVisible(m.rows[1].frame), "the row that threw is off and hidden")
check(m.rows[2].mode == "live" and m.rows[3].mode == "live" and isVisible(m.rows[3].frame), "the rows after it took the list")
check(DEGRADED.gunsightdots_state ~= nil, "logged once under gunsightdots_state")
""")

case("a_chip_is_built_the_way_the_action_buttons_are")(r"""
local D = boot()
local m = mount("debuffsH", "upper")
check(#SKIN_CALLS == 5, "SkinButton once per row, got " .. #SKIN_CALLS)
for i, call in ipairs(SKIN_CALLS) do
    colorIs(call.opts.borderColor, D.D.COLORS.violet, "chip " .. i .. " violet border")
    check(call.button.seatedBy == "SeatAuraTile", "chip " .. i .. " seated by SeatAuraTile")
    check(call.button.fsAuraPlate and call.button.fsAuraPlate.seated, "chip " .. i .. " has the plate")
    check(call.button.mouse == false, "chip " .. i .. " is click through")
end
local mv = mount("debuffsV", "lower")
check(#SKIN_CALLS == 9, "four chips more for the axis, got " .. #SKIN_CALLS)
""")

case("a_missing_icon_falls_back_to_the_abbreviation")(r"""
boot()
local m = mount("debuffsH", "upper")
pushList({ ent("Rend", 9, { noicon = true }), ent("Deep Wounds", 9) })
check(m.rows[1].chip.label:IsShown() and m.rows[1].chip.label.text == "RE", "no icon: two letters of the name, got " .. tostring(m.rows[1].chip.label.text))
check(not m.rows[1].chip.frame.icon:IsShown(), "the icon texture is hidden")
check(not m.rows[2].chip.label:IsShown(), "an icon hides the label")
""")

case("no_aura_api_is_ever_read_and_nothing_is_logged")(r"""
boot()
local mh = mount("debuffsH", "upper")
local mv = mount("debuffsV", "lower")
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
pushList({ ent("Rend", 9), ent("Deep Wounds", 0), ent("Thunder Clap", nil), ent("Sunder Armor", 2.5, { count = 5 }) }, 4)
tick(0.5); tick(5); tick(10)
pushList({})
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(#AURA_TOUCHED == 0, "an aura API was read: " .. tostring(AURA_TOUCHED[1]))
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")


case("the_modules_work_inside_the_real_gunsight_areas")(r"""
boot({ realareas = true })
local Areas = FS.GunsightAreas
check(Areas.AreaOf("debuffsH") == "upper", "the default upper area holds Target debuffs Horizontal, got " .. tostring(Areas.AreaOf("debuffsH")))
local mh = FS.GunsightDots.modules.debuffsH
check(mh.built and #TDSUBS == 1, "the areas built the module and onShow subscribed it")
pushList({ ent("Rend", 9), ent("Deep Wounds", 12) })
check(isVisible(mh.rows[1].frame), "a row is drawn inside the real upper host")
local _, cy = imgCenter(mh.rows[1].chip.frame)
near3(cy, rowCenterY(MU.TOP, 1), "row 1 sits on the first tick gap of the upper area")
FS.Gunsight.SetArea("upper", "debuffsV")
check(Areas.AreaOf("debuffsH") == nil and Areas.AreaOf("debuffsV") == "upper", "the picker swaps the module")
local mv = FS.GunsightDots.modules.debuffsV
check(#TDSUBS == 1 and mh.rows[1].mode == "off", "the old module released its subscription and rows")
check(mv.rows[1].mode == "live", "the new one drew the current list")
local _, vy = imgCenter(mv.rows[1].chip.frame)
near3(vy, MU.AXB - 9 * 112 / 30, "vertical chip on the 0 to 30 s axis")
FS.Gunsight.SetArea("upper", "empty")
FS.Gunsight.SetArea("lower", "debuffsH")
check(Areas.AreaOf("debuffsH") == "lower", "Horizontal can move to the lower area")
local _, ly = imgCenter(mh.rows[1].chip.frame)
near3(ly, rowCenterY(MU.HZ, 1), "and its rows start at the horizon there")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        d = toc.index("Modules/CombatHud/GunsightDots.lua")
        for dep in ("Modules/CombatHud/Gunsight.lua", "Modules/CombatHud/GunsightAreas.lua",
                    "Modules/CombatHud/TargetDebuffs.lua", "Core/FrameHelpers.lua"):
            out.append((f"toc_after_{Path(dep).stem}", None if toc.index(dep) < d else f"GunsightDots.lua must load after {dep}"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "forever-stuwave.toc must stay CRLF"))
    src = DOTS.read_text(encoding="utf-8") if DOTS.exists() else ""
    out.append(("source_does_not_register_the_dot_piece", None if "RegisterPiece" not in src else
                "GunsightDots.lua mentions RegisterPiece: GunsightAreas owns the dot piece"))
    for pat in ("UnitAura", "UnitDebuff", "GetAuraDataByIndex", "C_UnitAuras", "ReadAuraSlot"):
        out.append((f"source_never_reads_{pat}", None if pat not in src else f"GunsightDots.lua mentions {pat}"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    lua.globals().CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    lua.globals().GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    lua.globals().DOTS_SRC = DOTS.read_text(encoding="utf-8")
    lua.globals().AREAS_SRC = AREAS.read_text(encoding="utf-8")
    lua.globals().HAS_TARGET_SRC = _load_gunsight_harness().theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu))
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_v7()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not DOTS.exists():
        for name, _ in CASES:
            report(name, f"{DOTS.name} is missing")
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
