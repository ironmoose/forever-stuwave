#!/usr/bin/env python3
"""Runs the real GunsightDots.lua (the DoT time scale of the Gunsight HUD) headless against a mock WoW API.

GunsightDots.lua is piece "dot" of mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html
(drawDots): a 0 to 30 s altitude axis on the enemy side, an amber refresh band under 3 s, four
lane guides, and one cut-corner chip per DoT that slides down the scale like a note on a rhythm
game highway. The checks pin:

  * constants: chip size, scale length, band, header and label offsets are parsed back
    out of the mockup's drawDots, so a mockup edit fails here instead of drifting silently;
  * the static scale (axis, 31 ticks with labels at every fifth, band, dashed guides, header,
    vertical REFRESH label) lands where the mockup draws it, and no PENDING PROBE tag exists;
  * chips: a lane per DoT of the active class profile in profile order (warlock four, priest two,
    never more than four), the chip y from expiresAt - GetTime() between pushes (one OnUpdate that
    runs only while a chip is live), the amber band at 3 s or less, a dim hollow absent chip with
    a desaturated icon at 0, an expiring chip turning absent by itself, a white pop for 0.35 s on
    a (re)apply, nothing at all for an unknown DoT;
  * the in-combat rule: the absent chip shows ONLY while the player is in combat, a file-local flag
    set by PLAYER_REGEN_DISABLED / PLAYER_REGEN_ENABLED (with no Hud push) and seeded at build and on
    PLAYER_ENTERING_WORLD from InCombatLockdown() OR UnitAffectingCombat(). The mock models the real
    ordering (InCombatLockdown() reads false during the REGEN_DISABLED dispatch), so a pure
    InCombatLockdown() read fails here. Written only on a change; a live ticking chip is never touched;
  * the piece: registered under key "dot", hidden (and unsubscribed, OnUpdate cleared) when the
    piece is off, nothing built when the gunsight is disabled, re-seated on a rescale, and no
    aura API is ever read.

The mock is strict (a widget method it does not define fails as a nil call). Theme and the
FrameHelpers aura tile helper are STUBS here (their own harnesses cover the real ones); the real
Layout.lua, Gunsight.lua and HudProfiles.lua are loaded.

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
PROFILES = ADDON / "Modules/CombatHud/HudProfiles.lua"
TOC = ADDON / "forever-stuwave.toc"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"


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


def mockup_dots() -> dict:
    """Everything drawDots owns, read out of the mockup."""
    src = MOCKUP.read_text(encoding="utf-8")
    base = _load_gunsight_harness().mockup_constants()
    chs = int(_m(r"var CHS=(\d+),CHP=CHS/2;", src, "CHS").group(1))
    chamfer = int(_m(r"chamfer\(bx,by,CHS,CHS,(\d+)\);\s*A\(\.92\)", src, "chip chamfer").group(1))
    max_s = int(_m(r"function secY\(s\)\{return BOT-s/(\d+)\*\(BOT-TOP\);\}", src, "secY scale").group(1))
    band_s = int(_m(r"var yb=secY\((\d+)\);", src, "band seconds").group(1))
    band_fill = float(_m(r"A\((\.\d+)\);ctx\.fillStyle=K\.amber;ctx\.fillRect\(DOT_AX,yb", src, "band fill alpha").group(1))
    ax_up, ax_dn = (int(v) for v in _m(r"vline\(DOT_AX,TOP-(\d+),BOT\+(\d+),K\.violet", src, "axis ends").groups())
    hdr_y = int(_m(r"header\('DOT TIME',DOT_AX,(\d+),", src, "header").group(1))
    maj = int(_m(r"maj=s%(\d+)===0", src, "major tick step").group(1))
    maj_len, min_len = (int(v) for v in _m(r"tick\(DOT_AX,y,maj\?(\d+):(\d+),-1", src, "tick lengths").groups())
    label_dx = int(_m(r"text\(String\(s\),DOT_AX\+(\d+),y\+4,12", src, "tick label offset").group(1))
    refresh_dx = int(_m(r"ctx\.translate\(DOT_END\+(\d+),\(yb\+BOT\)/2\)", src, "REFRESH label x").group(1))
    pop_s = float(_m(r"var pop=ds\.age<(\.\d+)\?", src, "pop seconds").group(1))
    pop_a = float(_m(r"A\(pop\*(\.\d+)\);ctx\.fillStyle=K\.white", src, "pop alpha").group(1))
    dash_guide = [int(v) for v in _m(r"ctx\.setLineDash\(\[(\d+),(\d+)\]\);vline\(LANE\[l\]", src, "guide dash").groups()]
    dash_band = [int(v) for v in _m(r"ctx\.setLineDash\(\[(\d+),(\d+)\]\);hline\(yb", src, "band dash").groups()]
    wl = _m(r"(?s)var DOTS_WL=\[(.*?)\];", src, "Warlock DoT list").group(1)
    lanes = len(re.findall(r"\{ab:'\w+',ic:'\w+',dur:\d+,rem0:[\d.]+,lane:\d", wl))
    css = {n: v.lower() for n, v in re.findall(r"^\s*--(fg|muted|white|violet|amber):(#[0-9a-fA-F]{6});", src, re.M)}
    for need in ("fg", "muted", "white", "violet", "amber"):
        if need not in css:
            sys.exit(f"mockup: colour token --{need} missing")
    return dict(
        base=base, CHS=chs, CHAMFER=chamfer, MAX_S=max_s, BAND_S=band_s, BAND_FILL=band_fill,
        AX_UP=ax_up, AX_DN=ax_dn, HDR_Y=hdr_y, MAJ=maj, MAJ_LEN=maj_len, MIN_LEN=min_len,
        LABEL_DX=label_dx, REFRESH_DX=refresh_dx, POP_S=pop_s, POP_A=pop_a,
        GUIDE_DASH=dash_guide, BAND_DASH=dash_band, LANES=lanes, CSS=css,
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

-- Builds a Hud state from the profile's own row. spec[key]: "absent", a number of seconds left,
-- a table { remaining =, expiresAt =, duration = }, or nil for an UNKNOWN DoT (every field nil).
function mkState(spec, extra)
    local rows = {}
    for i, key in ipairs(PROFILE.row) do
        local e = { key = key, icon = 130000 + i }
        if PROFILE.dots[key] then
            local s = spec[key]
            if s == "absent" then
                e.missing, e.remaining = true, 0
            elseif type(s) == "number" then
                e.missing, e.remaining, e.expiresAt, e.duration = false, s, NOW + s, 18
            elseif type(s) == "table" then
                e.missing, e.remaining, e.expiresAt, e.duration = false, s.remaining, s.expiresAt, s.duration or 18
            end
        end
        rows[#rows + 1] = e
    end
    local state = { active = true, class = "TEST", row = rows, buffsMissing = {}, procs = {}, inCombat = false }
    for k, v in pairs(extra or {}) do state[k] = v end
    return state
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
local function secY(s) return MU.base.BOT - s / MU.MAX_S * (MU.base.BOT - MU.base.TOP) end

SECRET_FN = function() return false end      -- what FS.IsSecret answers; a case may swap it
local function boot(opts)
    opts = opts or {}
    resetWorld()
    -- The absent chip is the recast cue and shows only in combat (Parker, 2026-10-03), so a case that looks at
    -- one boots in combat; the out-of-combat cases pass combat = false.
    IN_COMBAT = opts.combat ~= false
    AFFECTING = opts.affecting          -- nil follows IN_COMBAT; a case sets it to model a reload mid-combat
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db
    -- Theme.lua's FS.IsSecret (a test may swap SECRET_FN) and the real FS.HasTarget / FS.TargetTakesDots out of it
    FS.IsSecret = function(v) return SECRET_FN(v) end
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    stubTheme_()
    stubHud_()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    loadAddonFile(PROFILES_SRC, "Modules/CombatHud/HudProfiles.lua")
    PROFILE = opts.profile or FS.HudProfiles[opts.class or "WARLOCK"]
    UnitClass = function() return "Class", opts.class or "WARLOCK" end
    if opts.state then STATE = opts.state end
    if opts.refusePiece then FS.Gunsight.RegisterPiece = function() return false end end   -- the registry refuses the "dot" piece
    loadAddonFile(DOTS_SRC, "Modules/CombatHud/GunsightDots.lua")
    if not opts.noEvents then
        fire("ADDON_LOADED", "forever-stuwave")
        fire("PLAYER_LOGIN")
    end
    return FS.GunsightDots
end

local function liveChips(D)
    local out = {}
    for i, c in ipairs(D.chips) do if c.mode == "live" then out[#out + 1] = i end end
    return out
end
local function ringColor(chip) return chip.frame.fsSkin.border.ring.vertex end
local function glowAlpha(chip) return chip.frame.fsSkin.glow.vertex[4] end
local function near3(a, b, what) near(a, b, what, 1e-3) end
local function same(a, b) return math.abs(a - b) < 1e-3 end
local function colorIs(c, want, what)
    check(same(c[1], want[1]) and same(c[2], want[2]) and same(c[3], want[3]),
        string.format("%s: got %.3f %.3f %.3f, want %.3f %.3f %.3f", what, c[1], c[2], c[3], want[1], want[2], want[3]))
end
local function mix(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end

-- A fingerprint of everything the piece frame has drawn: the tree under D.frame in creation order (frames,
-- textures, font strings), each with its geometry, anchors, colours, text and visibility. Two builds that
-- draw the same thing give the same string; the number is a polynomial hash of it (mod 2^31 - 1).
local function fmtv(v)
    if type(v) == "number" then return string.format("%.4f", v) end
    if type(v) == "table" then
        local t = {}
        for i = 1, #v do t[#t + 1] = fmtv(v[i]) end
        return "{" .. table.concat(t, ",") .. "}"
    end
    return tostring(v)
end
function renderDump(D)
    local ids, out = {}, {}
    local function walk(r)
        ids[r] = #out + 1
        local line = { r.kind, tostring(r.name), tostring(r.layer), tostring(r.sublevel), "lv" .. tostring(r.level),
            fmtv(r.w), fmtv(r.h), tostring(r.shown), fmtv(r.alpha) }
        for _, p in ipairs(r.points) do
            line[#line + 1] = p[1] .. ">" .. tostring(ids[p[2]] or p[2].name or "ext") .. ":" .. p[3] .. "@" .. fmtv(p[4]) .. "," .. fmtv(p[5])
        end
        for _, f in ipairs({ "color", "vertex", "path", "blend", "texcoord", "text", "textColor", "font", "justifyH", "justifyV", "slice", "sliceMode" }) do
            if r[f] ~= nil then line[#line + 1] = f .. "=" .. fmtv(r[f]) end
        end
        if r.desaturated then line[#line + 1] = "desat" end
        if r.gradient then line[#line + 1] = "grad=" .. r.gradient.orientation end
        local ev = {}
        for e in pairs(r.events) do ev[#ev + 1] = e end
        table.sort(ev)
        line[#line + 1] = "ev=" .. table.concat(ev, "/")
        if r.scripts.OnUpdate then line[#line + 1] = "OnUpdate" end
        out[#out + 1] = table.concat(line, "|")
        for _, c in ipairs(r.children) do walk(c) end
    end
    walk(D.frame)
    return table.concat(out, "\n"), #out
end
function renderHash(D)
    local text, n = renderDump(D)
    local h = 7
    for i = 1, #text do h = (h * 31 + text:byte(i)) % 2147483647 end
    return h, n
end
"""

case("constants_match_the_mockup")(r"""
local D = boot({ noEvents = true })
check(type(D) == "table" and type(D.D) == "table", "FS.GunsightDots.D (the constants table) is missing")
local c = D.D
local function eq(a, b, what) near(a, b, what .. " (GunsightDots has " .. tostring(a) .. ", mockup has " .. tostring(b) .. ")") end
eq(c.CHS, MU.CHS, "chip size")
eq(c.MAX_S, MU.MAX_S, "scale seconds"); eq(c.BAND_S, MU.BAND_S, "band seconds"); eq(c.BAND_FILL, MU.BAND_FILL, "band fill alpha")
eq(c.AX_UP, MU.AX_UP, "axis overshoot up"); eq(c.AX_DN, MU.AX_DN, "axis overshoot down")
eq(c.HDR_Y, MU.HDR_Y, "header y"); eq(c.MAJ, MU.MAJ, "major tick step")
eq(c.MAJ_LEN, MU.MAJ_LEN, "major tick length"); eq(c.MIN_LEN, MU.MIN_LEN, "minor tick length")
eq(c.LABEL_DX, MU.LABEL_DX, "tick label offset"); eq(c.REFRESH_DX, MU.REFRESH_DX, "REFRESH label offset")
eq(c.POP_S, MU.POP_S, "pop seconds"); eq(c.POP_A, MU.POP_A, "pop alpha")
eq(c.GUIDE_DASH[1], MU.GUIDE_DASH[1], "guide dash on"); eq(c.GUIDE_DASH[2], MU.GUIDE_DASH[2], "guide dash off")
eq(c.BAND_DASH[1], MU.BAND_DASH[1], "band dash on"); eq(c.BAND_DASH[2], MU.BAND_DASH[2], "band dash off")
eq(c.MAX_LANES, MU.LANES, "lane count")
local function rgb(hex) return { tonumber(hex:sub(2, 3), 16) / 255, tonumber(hex:sub(4, 5), 16) / 255, tonumber(hex:sub(6, 7), 16) / 255 } end
for _, name in ipairs({ "fg", "muted", "white", "violet", "amber" }) do
    colorIs(c.COLORS[name], rgb(MU.CSS[name]), "colour " .. name)
end
""")

case("nothing_is_built_before_login_and_nothing_when_disabled")(r"""
local D = boot({ noEvents = true })
check(D.frame == nil, "the piece frame was built at file load (UIParent is not real yet)")
for _, f in ipairs(FRAMES) do check(not (f.name or ""):find("GunsightDots"), "frame built at file load: " .. tostring(f.name)) end
local D2 = boot({ db = { gunsight = { enabled = false } } })
check(D2.frame == nil, "a disabled gunsight must build nothing")
""")

case("registers_piece_dot_and_hides_with_it")(r"""
local D = boot({ db = {} })
check(D.frame and D.frame:GetParent() == FS.Gunsight.root, "piece frame is a child of the gunsight root")
check(D.frame:IsShown() and isVisible(D.frame), "piece on by default")
check(FS.Gunsight.IsPieceOn("dot"), "key dot is on")
check(#SUBS == 1, "subscribes to the Hud while the piece is on, got " .. #SUBS)
FS.Gunsight.SetPiece("dot", false, true)
check(not D.frame:IsShown(), "frame hidden when the piece is off")
check(#SUBS == 0, "unsubscribed while the piece is off, got " .. #SUBS)
check(onUpdateFrames() == 0, "no OnUpdate while the piece is off")
push(mkState({ corruption = 10 }))
check(onUpdateFrames() == 0, "a push while off (a stale subscriber) must not start the OnUpdate")
FS.Gunsight.SetPiece("dot", true, true)
check(D.frame:IsShown() and #SUBS == 1, "back on: shown and subscribed again")
""")

case("piece_off_state_is_applied_at_login")(r"""
local D = boot({ db = { gunsight = { pieces = { dot = false } } } })
check(not D.frame:IsShown(), "a saved off piece stays hidden")
check(#SUBS == 0, "no subscription while saved off")
check(onUpdateFrames() == 0, "no OnUpdate while saved off")
""")

case("static_scale_matches_the_mockup")(r"""
local D = boot({ db = {} })
local P = D.parts
check(P, "FS.GunsightDots.parts is missing")
local B = MU.base
-- axis
local l, t, w, h = imgRect(P.axis)
near3(l + w / 2, B.DOT_AX, "axis x"); near3(t, B.TOP - MU.AX_UP, "axis top"); near3(t + h, B.BOT + MU.AX_DN, "axis bottom")
-- ticks: every second, 10 long every fifth and 5 long between, right edge on the axis
check(#P.ticks == 31, "31 ticks, got " .. #P.ticks)
for s = 0, 30 do
    local tl, tt, tw, th = imgRect(P.ticks[s + 1])
    local maj = s % MU.MAJ == 0
    near3(tt + th / 2, secY(s), "tick " .. s .. " y")
    near3(tl + tw, B.DOT_AX, "tick " .. s .. " right edge")
    near3(tw, maj and MU.MAJ_LEN or MU.MIN_LEN, "tick " .. s .. " length")
end
-- labels: 0 5 ... 30 as text, once each, at the axis + 6
local found = {}
for _, fs in ipairs(FONTSTRINGS) do
    if fs.text and tostring(fs.text):match("^%d+$") then found[fs.text] = (found[fs.text] or 0) + 1 end
end
for s = 0, 30, MU.MAJ do check(found[tostring(s)] == 1, "label " .. s .. " appears " .. tostring(found[tostring(s)]) .. " times") end
for s = 0, 30 do if s % MU.MAJ ~= 0 then check(found[tostring(s)] == nil, "minor tick " .. s .. " must not be labelled") end end
for s = 0, 30, MU.MAJ do
    local fs = P.labels[s]
    check(fs, "label " .. s .. " is not in parts.labels")
    check(fs.monoSize and math.abs(fs.monoSize - 12 * K) < 1e-6, "label font is Mononoki 12 image px, got " .. tostring(fs.monoSize))
    local x, y = imgCenter(fs)
    local ll = imgRect(fs)
    near3(ll, B.DOT_AX + MU.LABEL_DX, "label " .. s .. " left edge")
    near3(y, secY(s), "label " .. s .. " centred on its tick")
end
-- band: amber .16 from 3 s to 0, dashed top, solid bottom
local bl, bt, bw, bh = imgRect(P.band)
near3(bl, B.DOT_AX, "band left"); near3(bl + bw, B.DOT_END, "band right")
near3(bt, secY(MU.BAND_S), "band top is 3 s"); near3(bt + bh, B.BOT, "band bottom is 0")
near3(P.band.color[4], MU.BAND_FILL, "band fill alpha")
colorIs(P.band.color, D.D.COLORS.amber, "band colour")
check(#P.bandTop >= 8, "band top is dashed, got " .. #P.bandTop .. " dashes")
local prevRight
for i, d in ipairs(P.bandTop) do
    local dl, dt, dw, dh = imgRect(d)
    near3(dt + dh / 2, secY(MU.BAND_S), "band dash y")
    if i < #P.bandTop then near3(dw, MU.BAND_DASH[1], "band dash length") else check(dw <= MU.BAND_DASH[1] + 1e-3, "last band dash is clipped to the span") end
    check(dl >= B.DOT_AX - 1e-3 and dl + dw <= B.DOT_END + 1e-3, "band dash inside the band span")
    if prevRight then near3(dl - prevRight, MU.BAND_DASH[2], "band dash gap") end
    prevRight = dl + dw
end
local el, et, ew, eh = imgRect(P.bandBottom)
near3(et + eh / 2, B.BOT, "band bottom line y"); near3(el, B.DOT_AX, "band bottom line left"); near3(el + ew, B.DOT_END, "band bottom line right")
-- lane guides: four dashed verticals from the top to the bottom of the scale
check(#P.guides == 4, "four lane guides")
for lane = 1, 4 do
    local g = P.guides[lane]
    check(#g >= 20, "guide " .. lane .. " is dashed, got " .. #g)
    for i, d in ipairs(g) do
        local dl, dt, dw, dh = imgRect(d)
        near3(dl + dw / 2, B.LANE[lane], "guide " .. lane .. " x")
        near3(dh, MU.GUIDE_DASH[1], "guide dash length")
        check(dt >= B.TOP - 1e-3 and dt + dh <= B.BOT + 1e-3, "guide dash inside the scale")
        if i == 1 then near3(dt, B.TOP, "first dash starts at the top") end
    end
end
-- header and the vertical REFRESH label
local hdr = P.header
check(hdr and hdr.text == "DOT TIME", "header text")
check(math.abs(hdr.monoSize - 11 * K) < 1e-6, "header font 11 image px")
local hl, ht, hw, hh = imgRect(hdr)
near3(hl, B.DOT_AX, "header left")
check(ht + hh <= MU.HDR_Y + 4 and ht + hh >= MU.HDR_Y - 1, "header sits on the 488 baseline, bottom " .. (ht + hh))
local word = {}
for _, fs in ipairs(P.refresh) do word[#word + 1] = fs.text end
check(table.concat(word) == "REFRESH", "REFRESH label letters, got " .. table.concat(word))
local ys = {}
for i, fs in ipairs(P.refresh) do
    local cx, cy = imgCenter(fs)
    near3(cx, B.DOT_END + MU.REFRESH_DX, "REFRESH letter x")
    ys[i] = cy
    if i > 1 then check(ys[i] > ys[i - 1], "REFRESH letters run top to bottom") end
end
near3((ys[1] + ys[#ys]) / 2, (secY(MU.BAND_S) + B.BOT) / 2, "REFRESH label is centred on the band")
-- the decided omission
for _, fs in ipairs(FONTSTRINGS) do
    check(not tostring(fs.text or ""):upper():find("PENDING"), "the PENDING PROBE tag must not be drawn: " .. tostring(fs.text))
end
""")

case("warlock_lanes_follow_the_profile_order")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 15, bane_agony = 20, immolate = 10, siphon = 25 }))
check(#D.chips == 4, "four chips built, got " .. #D.chips)
local keys = { "corruption", "bane_agony", "immolate", "siphon" }
for i = 1, 4 do
    local c = D.chips[i]
    check(c.mode == "live" and c.key == keys[i], "lane " .. i .. " is " .. keys[i] .. ", got " .. tostring(c.key) .. "/" .. tostring(c.mode))
    check(c.frame:IsShown(), "chip " .. i .. " shown")
    near3(imgCenter(c.frame), MU.base.LANE[i], "chip " .. i .. " x is lane " .. i)
end
-- the abbreviations and icons come from the state row
check(D.chips[1].frame.icon.path == 130001, "chip 1 wears the corruption icon, got " .. tostring(D.chips[1].frame.icon.path))
check(D.chips[3].frame.icon.path == 130003, "chip 3 wears the immolate icon")
""")

case("priest_gets_two_lanes")(r"""
local D = boot({ db = {}, class = "PRIEST" })
push(mkState({ sw_pain = 12, dplague = 20 }))
check(D.chips[1].mode == "live" and D.chips[1].key == "sw_pain", "lane 1 is SW:P")
check(D.chips[2].mode == "live" and D.chips[2].key == "dplague", "lane 2 is Devouring Plague")
near3(imgCenter(D.chips[1].frame), MU.base.LANE[1], "SW:P x"); near3(imgCenter(D.chips[2].frame), MU.base.LANE[2], "DP x")
for i = 3, 4 do check(D.chips[i].mode == "off" and not D.chips[i].frame:IsShown(), "chip " .. i .. " is unused for a priest") end
-- a priest below level 20 has no Devouring Plague in the row: one lane
local s = mkState({ sw_pain = 12 })
for i = #s.row, 1, -1 do if s.row[i].key == "dplague" then table.remove(s.row, i) end end
push(s)
check(D.chips[1].mode == "live" and D.chips[2].mode == "off", "an unknown spell is not given a lane")
""")

case("at_most_four_lanes")(r"""
local prof = { row = { "a", "b", "c", "d", "e", "f", "bolt" }, dots = { a = {}, b = {}, c = {}, d = {}, e = {}, f = {} } }
local D = boot({ db = {}, profile = prof })
push(mkState({ a = 5, b = 6, c = 7, d = 8, e = 9, f = 10 }))
check(#D.chips == 4, "never more than four chips, got " .. #D.chips)
for i = 1, 4 do check(D.chips[i].key == string.char(96 + i), "lane " .. i .. " keeps profile order") end
""")

case("chip_y_follows_the_time_left")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 15, bane_agony = 30, immolate = 5, siphon = 0.5 }))
near3(select(2, imgCenter(D.chips[1].frame)), secY(15), "15 s")
near3(select(2, imgCenter(D.chips[2].frame)), secY(30), "30 s sits on the top of the scale")
near3(select(2, imgCenter(D.chips[3].frame)), secY(5), "5 s")
near3(select(2, imgCenter(D.chips[4].frame)), secY(0.5), "half a second")
push(mkState({ corruption = 45 }))
near3(select(2, imgCenter(D.chips[1].frame)), MU.base.TOP, "a DoT longer than the scale is held at the top")
-- the chip is a 24 image px square
local _, _, w, h = imgRect(D.chips[1].frame)
near3(w, MU.CHS, "chip width"); near3(h, MU.CHS, "chip height")
""")

case("chips_slide_between_pushes_on_one_onupdate")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 15, immolate = 8 }))
check(onUpdateFrames() == 1, "exactly one OnUpdate frame, got " .. onUpdateFrames())
check(D.frame:GetScript("OnUpdate") ~= nil, "the OnUpdate lives on the piece frame")
local pushes = 0
FS.Hud.Subscribe(function() pushes = pushes + 1 end)
local pushes0 = pushes
tick(1.0)
near3(select(2, imgCenter(D.chips[1].frame)), secY(14), "one second later, no push")
near3(select(2, imgCenter(D.chips[3].frame)), secY(7), "the other lane moves too")
tick(0.5)
near3(select(2, imgCenter(D.chips[1].frame)), secY(13.5), "half a second more")
check(pushes == pushes0, "movement needs no new Hud push")
-- the rail from the chip down to 0 shortens as the chip falls
local r1 = D.chips[1].rail.h
tick(2.0)
check(D.chips[1].rail.h < r1, "the rail shortens as the chip falls")
""")

case("band_state_at_three_seconds_or_less")(r"""
local D = boot({ db = {} })
local C = D.D.COLORS
push(mkState({ corruption = 3.5, immolate = 3.0, siphon = 3.01, bane_agony = 10 }))
colorIs(ringColor(D.chips[1]), C.violet, "3.5 s is violet")
colorIs(ringColor(D.chips[3]), C.amber, "exactly 3.0 s is in the band")
colorIs(ringColor(D.chips[4]), C.violet, "3.01 s is not")
colorIs(ringColor(D.chips[2]), C.violet, "10 s is violet")
tick(0.6)
colorIs(ringColor(D.chips[1]), C.amber, "3.5 s crossed into the band by time alone")
colorIs(ringColor(D.chips[2]), C.violet, "the 10 s chip stays violet")
-- crossing exactly 3.0 s by time alone (no push) is in the band too
push(mkState({ corruption = 4.0 }))
colorIs(ringColor(D.chips[1]), C.violet, "4 s is violet")
tick(1.0)
colorIs(ringColor(D.chips[1]), C.amber, "reaching exactly 3.0 s on the clock enters the band")
push(mkState({ corruption = 3.5, immolate = 3.0, siphon = 3.01, bane_agony = 10 }))
tick(0.6)
-- the rail and the dot go amber with it
check(D.chips[1].railColor == "amber" and D.chips[2].railColor == "violet", "rail colour follows the band")
-- a chip in the band pulses its glow; one outside holds steady
local seen, steady = {}, {}
for i = 1, 8 do
    tick(0.07)
    seen[#seen + 1] = glowAlpha(D.chips[1]); steady[#steady + 1] = glowAlpha(D.chips[2])
end
local lo, hi = math.huge, -math.huge
for _, v in ipairs(seen) do lo = math.min(lo, v); hi = math.max(hi, v) end
check(hi - lo > 0.05, "the band glow pulses, range " .. (hi - lo))
for i = 2, #steady do near3(steady[i], steady[1], "the violet glow is steady") end
""")

case("absent_chip_is_a_dim_hollow_chip_at_zero")(r"""
local D = boot({ db = {} })
local C = D.D.COLORS
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(c.mode == "absent" and c.frame:IsShown(), "absent chip is shown")
near3(select(2, imgCenter(c.frame)), MU.base.BOT, "rests at 0")
near3(imgCenter(c.frame), MU.base.LANE[1], "in its own lane")
check(c.frame.icon.desaturated == true, "grey desaturated icon")
check(c.frame.icon.alpha < 1 or c.frame.icon.vertex[4] < 1, "the icon is dimmed")
local want = mix(C.muted, { 1, 1, 1 }, 0.25)
colorIs(ringColor(c), want, "absent border is the muted grey")
check(glowAlpha(c) == 0, "no glow on an absent chip")
check(not c.rail:IsShown() and not c.dot:IsShown(), "no rail and no dot on an absent chip")
check(not c.pop:IsShown(), "no pop on an absent chip")
-- the live chip next to it is untouched
check(D.chips[2].frame.icon.desaturated == false and D.chips[2].rail:IsShown(), "a live chip is not desaturated and has a rail")
-- back to live: the saturation is restored
push(mkState({ corruption = 10 }))
check(c.frame.icon.desaturated == false and c.rail:IsShown(), "live again: colour back, rail back")
""")

case("an_absent_chip_shows_nothing_out_of_combat")(r"""
-- Parker, 2026-10-03: "dim recast, it i am not in combat it should hide."
local D = boot({ db = {}, combat = false })
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(c.mode == "absent", "the ledger state is still absent, got " .. tostring(c.mode))
check(not c.frame:IsShown() and not isVisible(c.frame), "out of combat: the absent chip is hidden")
check(not c.rail:IsShown() and not c.dot:IsShown() and not c.pop:IsShown(), "and so are its rail, dot and pop")
check(isVisible(D.chips[2].frame) and D.chips[2].rail:IsShown(), "the live chip next to it is drawn")
check(D.content:IsShown() and D.gate:IsShown(), "the scale itself stays up out of combat")
-- an absent chip that is not drawn must not start the motion driver either
check(onUpdateFrames() == 1, "one OnUpdate, for the live chip only")
""")

case("entering_combat_shows_the_dim_absent_chip_at_zero")(r"""
local D = boot({ db = {}, combat = false })
local C = D.D.COLORS
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(not isVisible(c.frame), "setup: hidden out of combat")
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")           -- no Hud push: the chip must follow the event itself
check(c.frame:IsShown() and isVisible(c.frame), "PLAYER_REGEN_DISABLED shows the absent chip at once")
near3(select(2, imgCenter(c.frame)), MU.base.BOT, "resting at 0")
near3(imgCenter(c.frame), MU.base.LANE[1], "in its own lane")
check(c.frame.icon.desaturated == true, "grey desaturated icon")
colorIs(ringColor(c), mix(C.muted, { 1, 1, 1 }, 0.25), "the muted grey ring")
check(glowAlpha(c) == 0, "no glow on the absent chip")
check(not c.rail:IsShown() and not c.dot:IsShown() and not c.pop:IsShown(), "no rail, dot or pop")
check(isVisible(D.chips[2].frame), "the live chip is untouched")
""")

case("leaving_combat_hides_the_absent_chip_again")(r"""
local D = boot({ db = {} })              -- in combat
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(isVisible(c.frame), "setup: shown in combat")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not c.frame:IsShown() and not isVisible(c.frame), "PLAYER_REGEN_ENABLED hides the absent chip at once")
check(c.mode == "absent", "it is hidden, not dropped: still absent in the ledger")
check(isVisible(D.chips[2].frame) and D.chips[2].rail:IsShown(), "the live chip stays")
-- and the next fight brings it back with no push
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
check(isVisible(c.frame), "the next pull shows it again")
-- a repeat of the same answer writes nothing (written only on a change)
local w = c.frame.writes
fire("PLAYER_REGEN_DISABLED"); fire("PLAYER_REGEN_DISABLED")
check(c.frame.writes == w, "a steady combat state writes no visibility, got " .. tostring(c.frame.writes - w) .. " writes")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
w = c.frame.writes
fire("PLAYER_REGEN_ENABLED"); fire("PLAYER_REGEN_ENABLED")
check(c.frame.writes == w, "a steady rest state writes no visibility, got " .. tostring(c.frame.writes - w) .. " writes")
-- a push out of combat keeps it hidden too (the Hud pushes about once a second)
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(not isVisible(c.frame), "a Hud push out of combat leaves it hidden")
""")

case("a_live_chip_stays_visible_in_and_out_of_combat")(r"""
local D = boot({ db = {}, combat = false })
push(mkState({ corruption = 12, bane_agony = 20 }))
local a, b = D.chips[1], D.chips[2]
check(isVisible(a.frame) and a.rail:IsShown() and isVisible(b.frame), "out of combat: live chips are drawn")
near3(select(2, imgCenter(a.frame)), secY(12), "and sit at their time")
check(onUpdateFrames() == 1, "and tick")
IN_COMBAT = true;  fire("PLAYER_REGEN_DISABLED")
check(isVisible(a.frame) and a.rail:IsShown() and isVisible(b.frame), "entering combat: still drawn")
IN_COMBAT = false; fire("PLAYER_REGEN_ENABLED")
check(isVisible(a.frame) and a.rail:IsShown() and isVisible(b.frame), "leaving combat: still drawn")
tick(1.0)
near3(select(2, imgCenter(a.frame)), secY(11), "still sliding down the scale out of combat")
-- running out out of combat turns it absent, and absent hides at rest
tick(11.5)
check(a.mode == "absent" and not isVisible(a.frame), "expired out of combat: absent and hidden")
check(isVisible(b.frame), "the other live chip is still up")
IN_COMBAT = true;  fire("PLAYER_REGEN_DISABLED")
check(isVisible(a.frame), "the expired DoT is the recast cue once combat starts")
""")

case("both_combat_events_are_registered")(r"""
local D = boot({ db = {} })
local function listens(event)
    for _, f in ipairs(FRAMES) do
        if f.events[event] and f.scripts.OnEvent then
            local p = f
            while p do
                if p == D.frame then return true end
                p = p.parent
            end
        end
    end
    return false
end
check(listens("PLAYER_REGEN_DISABLED"), "PLAYER_REGEN_DISABLED is not registered by the piece")
check(listens("PLAYER_REGEN_ENABLED"), "PLAYER_REGEN_ENABLED is not registered by the piece")
""")

case("an_unreadable_combat_seed_keeps_the_recast_cue_shown")(r"""
-- Like the target gate: never hide on a guess. A throwing or secret seed reads as in combat.
-- A real secret boolean throws on a truth test, so the guard must run BEFORE `r and true or false`. The mock
-- cannot throw there, so the secret answers FALSE (and is flagged for the next IsSecret check): code that skips
-- the guard reads it as plainly "out of combat" and hides the cue.
local D = boot({ db = {}, combat = false })
local flagged = false
local secretFalse = function() flagged = true; return false end
SECRET_FN = function(v)
    if flagged and v == false then flagged = false; return true end
    return false
end
local function seedWith(lock, aff)
    flagged = false
    InCombatLockdown = lock
    UnitAffectingCombat = aff
    fire("PLAYER_ENTERING_WORLD")
end
local no = function() return false end
push(mkState({ corruption = "absent" }))
seedWith(no, no)
check(not isVisible(D.chips[1].frame), "setup: both plainly false hides it")
seedWith(function() error("boom") end, no)
check(isVisible(D.chips[1].frame), "a throwing InCombatLockdown keeps the absent chip shown")
seedWith(no, no)
check(not isVisible(D.chips[1].frame), "setup: back to hidden")
seedWith(no, function() error("boom") end)
check(isVisible(D.chips[1].frame), "a throwing UnitAffectingCombat keeps it shown too")
seedWith(no, no)
check(not isVisible(D.chips[1].frame), "setup: hidden again")
seedWith(secretFalse, no)
check(isVisible(D.chips[1].frame), "a secret (false-reading) InCombatLockdown keeps the absent chip shown")
seedWith(no, no)
check(not isVisible(D.chips[1].frame), "setup: hidden once more")
seedWith(no, secretFalse)
check(isVisible(D.chips[1].frame), "a secret (false-reading) UnitAffectingCombat keeps it shown too")
""")

case("a_stuck_true_combat_flag_heals_from_a_plain_false_hud_push")(r"""
-- A missed PLAYER_REGEN_ENABLED would leave the flag true for good; the Hud's own plainly false
-- state.inCombat (InCombatLockdown, pushed about once a second) clears it, but only if the seed agrees.
local D = boot({ db = {} })              -- in combat
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(isVisible(c.frame), "setup: shown in combat")
IN_COMBAT = false                        -- combat ended, and the REGEN_ENABLED event never reached us
check(isVisible(c.frame), "setup: nothing has told the piece yet, the flag is stuck true")
push(mkState({ corruption = "absent", bane_agony = 10 }))      -- inCombat = false
check(not c.frame:IsShown() and not isVisible(c.frame), "a plainly false Hud inCombat clears the stuck flag and hides the cue")
check(c.mode == "absent" and isVisible(D.chips[2].frame), "the chip is hidden, not dropped, and the live chip stays")
-- healed for good: a steady push writes nothing, and the next pull still turns it on
local w = c.frame.writes
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(c.frame.writes == w, "a steady rest push writes no visibility")
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
check(isVisible(c.frame), "the next pull shows it again")
""")

case("the_hud_can_clear_the_combat_flag_but_never_set_it")(r"""
-- One way only: REGEN_DISABLED and the seed own "true" (HudLogic can flip early).
local D = boot({ db = {}, combat = false })
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(not isVisible(c.frame), "setup: hidden out of combat")
push(mkState({ corruption = "absent", bane_agony = 10 }, { inCombat = true }))
check(not isVisible(c.frame), "a Hud push saying inCombat = true does not show the cue")
push(mkState({ corruption = "absent", bane_agony = 10 }, { inCombat = true }))
check(not isVisible(c.frame), "and neither does a repeat")
""")

case("the_hud_heal_needs_the_seed_to_agree")(r"""
-- state.inCombat is InCombatLockdown() alone, which can read false while UnitAffectingCombat is already true;
-- a push in that window must not hide the cue, so the heal re-reads both APIs and only clears on "both false".
local D = boot({ db = {}, combat = false, affecting = true })
push(mkState({ corruption = "absent", bane_agony = 10 }))      -- inCombat = false (lockdown), affecting true
check(isVisible(D.chips[1].frame), "setup: the seed read in combat from UnitAffectingCombat")
push(mkState({ corruption = "absent", bane_agony = 10, siphon = 5 }))
check(isVisible(D.chips[1].frame), "a Hud inCombat = false does not clear the flag while UnitAffectingCombat says combat")
AFFECTING = false
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(not isVisible(D.chips[1].frame), "once both APIs agree it is over, the next plain false push clears it")
""")

case("the_recast_cue_follows_the_events_when_lockdown_lags_the_event")(r"""
-- The real ordering: InCombatLockdown() is FALSE during the PLAYER_REGEN_DISABLED dispatch and true after.
local D = boot({ db = {}, combat = false })
push(mkState({ corruption = "absent", bane_agony = 10 }))
local c = D.chips[1]
check(not isVisible(c.frame), "setup: hidden out of combat")
IN_COMBAT = true
local seen
local probe = CreateFrame("Frame")
probe:RegisterEvent("PLAYER_REGEN_DISABLED")
probe:SetScript("OnEvent", function() seen = InCombatLockdown() end)
fire("PLAYER_REGEN_DISABLED")
check(seen == false, "the mock models the real ordering: lockdown reads false inside the dispatch, got " .. tostring(seen))
check(InCombatLockdown() == true, "and true once the dispatch is over")
check(c.frame:IsShown() and isVisible(c.frame), "the absent chip shows at once on PLAYER_REGEN_DISABLED, with no Hud push")
check(isVisible(D.chips[2].frame), "the live chip is untouched")
-- the other side: lockdown is already off when PLAYER_REGEN_ENABLED arrives
IN_COMBAT = false
check(InCombatLockdown() == false, "setup: lockdown already false")
fire("PLAYER_REGEN_ENABLED")
check(not c.frame:IsShown() and not isVisible(c.frame), "PLAYER_REGEN_ENABLED hides it with InCombatLockdown already false")
-- and robust to the opposite ordering: lockdown still true while PLAYER_REGEN_ENABLED dispatches
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
check(isVisible(c.frame), "setup: shown again")
InCombatLockdown = function() return true end
fire("PLAYER_REGEN_ENABLED")
check(not isVisible(c.frame), "PLAYER_REGEN_ENABLED hides it even if lockdown lags the event")
""")

case("a_reload_mid_combat_seeds_the_recast_cue_from_the_api")(r"""
-- /reload in a fight: no REGEN event fires, so the build seed decides. UnitAffectingCombat alone is enough.
local D = boot({ db = {}, combat = false, affecting = true })
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(isVisible(D.chips[1].frame), "UnitAffectingCombat true at build shows the absent chip (lockdown still false)")
-- and InCombatLockdown alone is enough too
D = boot({ db = {}, combat = true, affecting = false })
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(isVisible(D.chips[1].frame), "InCombatLockdown true at build shows it (UnitAffectingCombat false)")
-- both false: hidden
D = boot({ db = {}, combat = false, affecting = false })
push(mkState({ corruption = "absent", bane_agony = 10 }))
check(not isVisible(D.chips[1].frame), "both false at build keeps it hidden")
-- zoning mid-combat re-seeds on PLAYER_ENTERING_WORLD
IN_COMBAT, AFFECTING = false, true
fire("PLAYER_ENTERING_WORLD")
check(isVisible(D.chips[1].frame), "PLAYER_ENTERING_WORLD re-seeds from UnitAffectingCombat and shows it")
IN_COMBAT, AFFECTING = false, false
fire("PLAYER_ENTERING_WORLD")
check(not isVisible(D.chips[1].frame), "and re-seeds out of combat, hiding it")
""")

case("unknown_dot_draws_no_chip")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 10, immolate = 12 }))
check(D.chips[2].mode == "off" and not D.chips[2].frame:IsShown(), "an unknown DoT (every field nil) draws nothing")
check(D.chips[1].mode == "live", "a known one is drawn")
push(mkState({}))
for i = 1, 4 do check(not D.chips[i].frame:IsShown(), "all unknown: chip " .. i .. " hidden") end
check(onUpdateFrames() == 0, "nothing live: no OnUpdate")
check(D.content:IsShown(), "the scale itself stays up while the class has DoT lanes")
""")

case("an_expiring_chip_turns_absent_by_itself_and_the_onupdate_stops")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 2.0 }))
check(onUpdateFrames() == 1, "running while a chip is live")
tick(1.0)
check(D.chips[1].mode == "live", "still live at 1 s")
tick(1.5)    -- crossed 0 with no push (Signature would not republish an expired pandemic DoT)
check(D.chips[1].mode == "absent", "expired: absent, got " .. tostring(D.chips[1].mode))
near3(select(2, imgCenter(D.chips[1].frame)), MU.base.BOT, "rests at 0")
check(D.chips[1].frame.icon.desaturated == true and not D.chips[1].rail:IsShown(), "the absent look")
check(onUpdateFrames() == 0, "the OnUpdate stopped with the last live chip")
""")

case("onupdate_runs_only_while_a_chip_is_live")(r"""
local D = boot({ db = {} })
check(onUpdateFrames() == 0, "no state yet: no OnUpdate")
push(mkState({ corruption = "absent", immolate = "absent" }))
check(onUpdateFrames() == 0, "only absent chips: no OnUpdate")
push(mkState({ corruption = 10 }))
check(onUpdateFrames() == 1, "a live chip: OnUpdate")
push(mkState({ corruption = 10, immolate = 4 }))
check(onUpdateFrames() == 1, "still exactly one")
push(mkState({}))
check(onUpdateFrames() == 0, "no chips: OnUpdate cleared")
push({ active = false, row = {}, buffsMissing = {}, procs = {} })
check(onUpdateFrames() == 0, "inactive state: still none")
""")

case("pop_flash_on_apply_and_reapply")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 12 }))
local c = D.chips[1]
check(not c.pop:IsShown(), "no pop for a DoT that was already up when the HUD first saw it")
tick(5.0)
-- reapplied: expiresAt jumps by about the full duration
push(mkState({ corruption = { remaining = 17.9, expiresAt = NOW + 17.9, duration = 18 } }))
check(c.pop:IsShown(), "a reapply pops")
near3(c.pop.vertex[4], MU.POP_A, "the pop starts at .8")
colorIs(c.pop.vertex, D.D.COLORS.white, "the pop is the mockup white")
check(c.pop.path:find("slice_cut2_fill", 1, true), "the pop is the cut fill, not a square: " .. tostring(c.pop.path))
tick(MU.POP_S / 2)
near(c.pop.vertex[4], MU.POP_A * 0.5, "half way through the pop", 0.02)
tick(MU.POP_S / 2 + 0.01)
check(not c.pop:IsShown(), "the pop ends after 0.35 s")
-- a small shift of the expiry (a reconcile correcting the estimate) is not a reapply
local exp1 = c.expiresAt
push(mkState({ corruption = { remaining = exp1 + 0.1 - NOW, expiresAt = exp1 + 0.1, duration = 18 } }))
check(not c.pop:IsShown(), "a 0.1 s shift is not a reapply")
-- absent then applied again pops too
push(mkState({ corruption = "absent" }))
check(not c.pop:IsShown(), "absent: no pop")
push(mkState({ corruption = 18 }))
check(c.pop:IsShown(), "absent to live pops")
""")

case("a_target_switch_is_not_a_reapply")(r"""
local D = boot({ db = {} })
local c = D.chips[1]
-- a target with no DoT, then a target carrying a live one: absent to live on a NEW target is not a reapply
push(mkState({ corruption = "absent" }, { targetEpoch = 1 }))
check(c.mode == "absent", "the first target has no DoT")
push(mkState({ corruption = 12 }, { targetEpoch = 2 }))
check(c.mode == "live", "the new target's DoT is live")
check(not c.pop:IsShown(), "absent to live on a new target does not pop")
near3(select(2, imgCenter(c.frame)), secY(12), "the chip is still placed from the time left")
-- live on one target, live with a later expiry on the next: also no pop
push(mkState({ corruption = 17 }, { targetEpoch = 3 }))
check(not c.pop:IsShown(), "a later expiry on a new target does not pop")
-- a pop still running from the old target is dropped with the switch
tick(1.0)
push(mkState({ corruption = { remaining = 17.9, expiresAt = NOW + 17.9, duration = 18 } }, { targetEpoch = 3 }))
check(c.pop:IsShown(), "a reapply on the same target pops")
push(mkState({ corruption = 5 }, { targetEpoch = 4 }))
check(not c.pop:IsShown(), "the old target's pop does not follow the switch")
-- the flash is back once the target holds still: the next push of the same epoch compares as usual
push(mkState({ corruption = "absent" }, { targetEpoch = 4 }))
push(mkState({ corruption = 18 }, { targetEpoch = 4 }))
check(c.pop:IsShown(), "absent to live on the same target pops")
""")

case("a_fresh_apply_on_a_new_epoch_still_pops")(r"""
local D = boot({ db = {} })
local c = D.chips[1]
push(mkState({ corruption = "absent" }, { targetEpoch = 1 }))
-- Tab plus an instant cast inside one Hud tick: absent to live in a single new-epoch push, remaining == duration
push(mkState({ corruption = { remaining = 18, expiresAt = NOW + 18, duration = 18 } }, { targetEpoch = 2 }))
check(c.mode == "live", "the fresh DoT is live")
check(c.pop:IsShown(), "a fresh apply (remaining == duration) on a new epoch pops")
near3(c.pop.vertex[4], MU.POP_A, "the pop starts at .8")
-- within 0.5 s of the full duration still counts as fresh
tick(1.0)
push(mkState({ corruption = { remaining = 17.6, expiresAt = NOW + 17.6, duration = 18 } }, { targetEpoch = 3 }))
check(c.pop:IsShown(), "remaining 0.4 s under the duration on a new epoch is still a fresh apply")
-- well below the duration is a DoT the new target already carried: no pop
push(mkState({ corruption = { remaining = 12, expiresAt = NOW + 12, duration = 18 } }, { targetEpoch = 4 }))
check(not c.pop:IsShown(), "remaining well below the duration on a new epoch does not pop")
push(mkState({ corruption = { remaining = 17.4, expiresAt = NOW + 17.4, duration = 18 } }, { targetEpoch = 5 }))
check(not c.pop:IsShown(), "remaining 0.6 s under the duration on a new epoch is not fresh")
-- no duration on the row: nothing to compare, so no pop on a new epoch
local noDur = mkState({ corruption = { remaining = 18, expiresAt = NOW + 18 } }, { targetEpoch = 6 })
noDur.row[1].duration = nil
push(noDur)
check(c.mode == "live" and not c.pop:IsShown(), "a row with no usable duration never reads as fresh on a new epoch")
""")

case("piece_hide_resets_the_epoch_memory")(r"""
local D = boot({ db = {} })
local c = D.chips[1]
push(mkState({ corruption = 12 }, { targetEpoch = 5 }))
check(c.mode == "live" and not c.pop:IsShown(), "first sight of a live DoT: no pop")
FS.Gunsight.SetPiece("dot", false, true)
check(c.mode == "off", "hiding the piece forgets the chips")
FS.Gunsight.SetPiece("dot", true, true)    -- Subscribe replays the last state, still epoch 5
push(mkState({ corruption = 11.8 }, { targetEpoch = 5 }))
check(c.mode == "live", "the DoT is live after the re-show")
check(not c.pop:IsShown(), "a mid duration DoT with the same epoch number after hide and show does not pop")
-- the reset is what makes the first push after a show a NEW epoch: a genuine fresh apply right after a
-- re-show then pops (without the reset the same epoch number takes the same-target path, where an "off"
-- chip never pops)
FS.Gunsight.SetPiece("dot", false, true)
STATE = nil
FS.Gunsight.SetPiece("dot", true, true)
push(mkState({ corruption = { remaining = 18, expiresAt = NOW + 18, duration = 18 } }, { targetEpoch = 5 }))
check(c.mode == "live" and c.pop:IsShown(), "after hide and show the epoch is forgotten: a fresh apply pops")
""")

case("same_target_expiry_moved_later_pops")(r"""
local D = boot({ db = {} })
local c = D.chips[1]
push(mkState({ corruption = 12 }, { targetEpoch = 7 }))
check(not c.pop:IsShown(), "first sight: no pop")
tick(5.0)
push(mkState({ corruption = { remaining = 17.9, expiresAt = NOW + 17.9, duration = 18 } }, { targetEpoch = 7 }))
check(c.pop:IsShown(), "expiry moved later by more than 0.5 s on the same target pops")
tick(1.0)
local exp1 = c.expiresAt
push(mkState({ corruption = { remaining = exp1 + 0.2 - NOW, expiresAt = exp1 + 0.2, duration = 18 } }, { targetEpoch = 7 }))
check(not c.pop:IsShown(), "a 0.2 s shift on the same target is not a reapply")
""")

case("scale_hides_for_a_class_with_no_dot_lanes")(r"""
local D = boot({ db = {} })
push(mkState({ corruption = 10 }))
check(D.content:IsShown(), "scale up with a lane")
push({ active = false, row = {}, buffsMissing = {}, procs = {} })
check(not D.content:IsShown(), "an inactive Hud draws no scale")
local s = mkState({ corruption = 10 })
local row = {}
for _, e in ipairs(s.row) do if e.key == "shadow_bolt" then row[#row + 1] = e end end
s.row = row
push(s)
check(not D.content:IsShown(), "no DoT rows: no scale")
check(onUpdateFrames() == 0, "and nothing runs")
""")

case("class_without_a_profile_keeps_the_scale_hidden")(r"""
local D = boot({ db = {}, class = "ROGUE" })    -- HudProfiles has no ROGUE entry: PROFILE is nil
check(PROFILE == nil, "setup: ROGUE resolves to no profile")
push({ active = false, class = "ROGUE", row = {}, buffsMissing = {}, procs = {}, inCombat = false })
check(not isVisible(D.content), "a rogue has no DoT lanes, so the scale is hidden")
IN_COMBAT = true
push({ active = false, class = "ROGUE", row = {}, buffsMissing = {}, procs = {}, inCombat = true })
tick(0.5)
check(not isVisible(D.content), "and stays hidden in combat")
check(onUpdateFrames() == 0, "nothing runs")
check(#AURA_TOUCHED == 0, "no aura (secret) API was read: " .. tostring(AURA_TOUCHED[1]))
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

# The DoT area is a CLASS slot (mockup drawDots for Warlock and Priest, drawSealChamber for the Paladin,
# both behind deck key 6). The Paladin's chamber is another file's; here the Paladin draws nothing.
case("warlock_and_priest_render_is_byte_identical_to_the_approved_look")(r"""
-- Fingerprints include frame names and texture paths as well as geometry and drawn state.
local GOLD = { WL_IDLE = 1183434497, WL_LIVE = 565967534, WL_TICK = 599751858, PR_LIVE = 1901135936,
    RG = 1183434497, WL_ABSENT_OOC = 1410475816 }
local got = {}
local D = boot({ db = {} })
got.WL_IDLE = renderHash(D)
push(mkState({ corruption = 15, bane_agony = 20, immolate = 10, siphon = 25 }))
got.WL_LIVE = renderHash(D)
tick(0.5)
got.WL_TICK = renderHash(D)
D = boot({ db = {}, class = "PRIEST" })
push(mkState({ sw_pain = 12, dplague = 20 }))
got.PR_LIVE = renderHash(D)
D = boot({ db = {}, class = "ROGUE" })      -- no profile: the scale is still built (and hidden), as before
got.RG = renderHash(D)
D = boot({ db = {}, combat = false })
push(mkState({ corruption = "absent", immolate = 2 }))
got.WL_ABSENT_OOC = renderHash(D)
local bad = {}
for k, want in pairs(GOLD) do
    if got[k] ~= want then bad[#bad + 1] = k .. " got " .. tostring(got[k]) .. " want " .. tostring(want) end
end
table.sort(bad)
check(#bad == 0, "render changed: " .. table.concat(bad, "; "))
""")

case("warlock_and_priest_still_build_the_scale_and_subscribe")(r"""
for _, class in ipairs({ "WARLOCK", "PRIEST" }) do
    local D = boot({ db = {}, class = class })
    check(D.parts.axis and #D.parts.ticks == 31 and D.parts.header and D.parts.band, class .. ": the scale is built")
    check(#D.chips == D.D.MAX_LANES, class .. ": all four chip slots are built")
    check(#SUBS == 1, class .. ": subscribed to the Hud while the piece is on")
end
""")

case("paladin_slot_draws_no_scale_and_no_lanes")(r"""
local D = boot({ db = {}, class = "PALADIN" })
check(next(FS.HudProfiles.PALADIN.dots) == nil and type(FS.HudProfiles.PALADIN.seals) == "table",
      "setup: the paladin profile has a seals table and no dots")
-- the piece is still there: the console key's toggle, Gunsight.SetPiece and the chamber's future parent
check(D.frame and D.frame:GetParent() == FS.Gunsight.root, "the piece frame is built under the gunsight root")
check(D.frame.name == "ForeverSTUwaveGunsightDots" and _G.ForeverSTUwaveGunsightDots == D.frame, "and keeps its global name")
check(FS.Gunsight.IsPieceOn("dot") and D.frame:IsShown(), "piece key dot is registered and on")
-- nothing drawn: no axis, no ticks, no labels, no band, no guides, no header, no refresh letters, no chips
check(next(D.parts) == nil, "no scale parts, got " .. tostring(next(D.parts)))
check(#D.chips == 0, "no chips")
local n = 0
for _, t in ipairs(TEXTURES) do
    local p = t
    while p do
        if p == D.frame then n = n + 1 end
        p = p.parent
    end
end
check(n == 0, "no texture under the piece frame, got " .. n)
n = 0
for _, fs in ipairs(FONTSTRINGS) do
    local p = fs
    while p do
        if p == D.frame then n = n + 1 end
        p = p.parent
    end
end
check(n == 0, "no font string under the piece frame, got " .. n)
for _, fs in ipairs(FONTSTRINGS) do
    check(not (fs.text and (tostring(fs.text):match("^%d+$") or fs.text == "DOT TIME")), "a scale label was drawn: " .. tostring(fs.text))
end
-- a paladin state changes nothing: no lanes, nothing runs, no Hud work for a piece with nothing to draw
push(mkState({}))
check(not D.content:IsShown(), "the content stays hidden")
IN_COMBAT = true
push(mkState({}, { inCombat = true, targetEpoch = 2 }))
tick(0.5)
check(not isVisible(D.content), "and in combat")
check(onUpdateFrames() == 0, "no OnUpdate")
check(#SUBS == 0, "the dot piece does not subscribe to the Hud for a class slot it does not draw")
check(#AURA_TOUCHED == 0, "no aura API was read")
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("paladin_piece_toggle_and_target_gate_keep_working")(r"""
local D = boot({ db = {}, class = "PALADIN" })
check(D.gate and D.content, "the gate and the content frame exist for the chamber to hang off")
-- the key's toggle: SetPiece hides and shows the piece frame like any other piece
FS.Gunsight.SetPiece("dot", false, true)
check(not D.frame:IsShown() and not FS.Gunsight.IsPieceOn("dot"), "off hides the piece frame")
FS.Gunsight.SetPiece("dot", true, true)
check(D.frame:IsShown() and FS.Gunsight.IsPieceOn("dot"), "on shows it again")
local seen = {}
FS.Gunsight.OnPieceChanged(function(key, on) seen[#seen + 1] = key .. tostring(on) end)
FS.Gunsight.SetPiece("dot", false, true)
check(#seen == 1 and seen[1] == "dotfalse", "OnPieceChanged fires once with the key and state, got " .. table.concat(seen, ","))
FS.Gunsight.SetPiece("dot", true, true)
-- a saved off piece stays off, with nothing built under it
local D2 = boot({ db = { gunsight = { pieces = { dot = false } } }, class = "PALADIN" })
check(not D2.frame:IsShown(), "a saved off piece stays hidden")
-- the target layer still follows the target: a chamber hung off the gate inherits it
local D3 = boot({ db = {}, class = "PALADIN" })
check(D3.gate:IsShown(), "gate up with a target")
local savedExists = UnitExists
UnitExists = function() return false end
fire("PLAYER_TARGET_CHANGED")
check(not D3.gate:IsShown(), "no target: the gate hides")
UnitExists = savedExists
fire("PLAYER_TARGET_CHANGED")
check(D3.gate:IsShown(), "target back: the gate shows")
-- a rescale re-seats nothing it does not have
local ok = pcall(function() SetScreen(1080); fire("UI_SCALE_CHANGED"); fire("DISPLAY_SIZE_CHANGED") end)
check(ok, "a rescale with an empty slot does not throw")
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("a_profile_with_dots_and_seals_still_draws_the_scale")(r"""
-- the rule is: seals AND no dots. Dots keep the scale whatever else the profile carries.
local prof = { row = { "a", "b" }, dots = { a = {}, b = {} }, seals = { order = { "sor" } } }
local D = boot({ db = {}, profile = prof })
check(D.parts.axis and #D.chips == D.D.MAX_LANES and #SUBS == 1, "dots plus seals: the scale and lanes are built")
push(mkState({ a = 5, b = 6 }))
check(D.chips[1].mode == "live" and D.chips[2].mode == "live", "and drawn")
-- seals with an empty dots table (the paladin shape) draws nothing; seals as a non table does not count
local D2 = boot({ db = {}, profile = { row = {}, dots = {}, seals = { order = {} } } })
check(next(D2.parts) == nil and #D2.chips == 0, "empty dots plus a seals table: nothing drawn")
local D3 = boot({ db = {}, profile = { row = {}, seals = { order = {} } } })
check(next(D3.parts) == nil and #D3.chips == 0, "no dots field plus a seals table: nothing drawn")
local D4 = boot({ db = {}, profile = { row = {}, dots = {}, seals = true } })
check(D4.parts.axis, "a seals value that is not a table is not a class slot")
local D5 = boot({ db = {}, profile = { row = {}, dots = {} } })
check(D5.parts.axis, "no seals: the scale is built as before")
""")

case("no_hud_leaves_the_piece_inert")(r"""
resetWorld()
SetScreen(1440)
stubTheme_()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua"); loadAddonFile(CONFIG_SRC, "Core/Config.lua"); loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
FS.Hud = nil
loadAddonFile(DOTS_SRC, "Modules/CombatHud/GunsightDots.lua")
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(onUpdateFrames() == 0, "no OnUpdate without a Hud")
""")

case("chip_is_built_the_way_the_action_buttons_are")(r"""
local D = boot({ db = {} })
check(#SKIN_CALLS == 4, "SkinButton once per chip, got " .. #SKIN_CALLS)
local C = D.D.COLORS
for i, call in ipairs(SKIN_CALLS) do
    colorIs(call.opts.borderColor, C.violet, "chip " .. i .. " starts with the violet border")
    check(call.button.seatedBy == "SeatAuraTile", "chip " .. i .. " is seated by SeatAuraTile, got " .. tostring(call.button.seatedBy))
    check(call.button.fsAuraPlate and call.button.fsAuraPlate.seated, "chip " .. i .. " has the dark plate behind the icon")
    check(call.button.mouse == false, "chip " .. i .. " is click through")
end
near3(D.chips[1].frame:GetWidth(), 24 * K, "chip is 24 image px wide")
""")

case("chip_label_is_the_fallback_for_a_missing_icon")(r"""
local D = boot({ db = {} })
local s = mkState({ corruption = 10, immolate = 8 })
s.row[1].icon = nil
push(s)
check(D.chips[1].label:IsShown() and D.chips[1].label.text == "CO", "no icon: the abbreviation shows, got " .. tostring(D.chips[1].label.text))
check(D.chips[3].label.text == nil or not D.chips[3].label:IsShown(), "an icon hides the abbreviation")
""")

case("label_set_when_a_row_first_arrives_off_then_live_with_no_icon")(r"""
local D = boot({ db = {} })
-- first push: the row is UNKNOWN (off) and carries no icon
local s = mkState({})
s.row[1].icon = nil
push(s)
check(not D.chips[1].label:IsShown(), "an off chip shows no label")
-- second push: the same key and still no icon, but now live
local s2 = mkState({ corruption = 10 })
s2.row[1].icon = nil
push(s2)
check(D.chips[1].label:IsShown() and D.chips[1].label.text == "CO",
    "off then live with a nil icon: the abbreviation must be set, got " .. tostring(D.chips[1].label.text))
check(not D.chips[1].frame.icon:IsShown(), "no icon: the icon texture stays hidden")
""")

case("rescale_reseats_the_scale_and_the_chips")(r"""
local D = boot({ db = {}, height = 1440 })
push(mkState({ corruption = 15, immolate = 6, siphon = "absent" }))
SetScreen(1200)
fire("UI_SCALE_CHANGED")
near3(D.chips[1].frame:GetWidth(), 24 * K * 1200 / 1440, "chip size at 1200")
near3(select(2, imgCenter(D.chips[1].frame)), secY(15), "chip y after the rescale")
near3(select(2, imgCenter(D.chips[4].frame)), MU.base.BOT, "absent chip y after the rescale")
local l, t, w, h = imgRect(D.parts.axis)
near3(t, MU.base.TOP - MU.AX_UP, "axis top after the rescale"); near3(l + w / 2, MU.base.DOT_AX, "axis x after the rescale")
local _, tt, _, th = imgRect(D.parts.ticks[31])
near3(tt + th / 2, MU.base.TOP, "the 30 s tick after the rescale")
tick(1)
near3(select(2, imgCenter(D.chips[1].frame)), secY(14), "still moving after the rescale")
""")

case("dots_hide_with_no_target_and_show_with_one")(r"""
HAS = false
UnitExists = function(unit) check(unit == "target", "UnitExists asked about " .. tostring(unit)); return HAS end
local D = boot({ db = {} })
check(D.gate, "FS.GunsightDots.gate (the target visibility layer) is missing")
check(D.gate:GetParent() == D.frame and D.content:GetParent() == D.gate, "the layer sits between the piece frame and the content")
check(not D.gate:IsShown() and not isVisible(D.content), "no target at build: the whole scale is hidden")
check(D.gate:GetFrameLevel() == D.frame:GetFrameLevel(),
    "the gate takes the piece frame's level, so it adds no stacking level")
check(D.content:GetFrameLevel() == D.frame:GetFrameLevel() + 1,
    "the content keeps the level it had as a direct child of the piece frame")
check(D.frame:IsShown() and FS.Gunsight.IsPieceOn("dot"), "the piece itself stays on (that is the user's setting)")
push(mkState({ corruption = 10 }))
check(not isVisible(D.chips[1].frame), "a live chip is hidden with no target")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown() and isVisible(D.content) and isVisible(D.chips[1].frame), "a target: scale and chip are visible")
HAS = false; fire("PLAYER_TARGET_CHANGED")
check(not isVisible(D.content) and not isVisible(D.chips[1].frame), "target dropped: hidden again")
check(D.frame:IsShown(), "dropping the target never touches the piece")
HAS = true; fire("PLAYER_ENTERING_WORLD")
check(D.gate:IsShown(), "PLAYER_ENTERING_WORLD re-reads the target")
""")

case("dots_gate_is_written_only_when_its_answer_changes")(r"""
HAS = true
UnitExists = function() return HAS end
local D = boot({ db = {} })
local function writes() return D.gate.writes or 0 end
HAS = false; fire("PLAYER_TARGET_CHANGED")
check(not D.gate:IsShown(), "setup: no target, hidden")
local base = writes()
fire("PLAYER_TARGET_CHANGED"); fire("UNIT_HEALTH", "target"); fire("UNIT_HEALTH", "target")
fire("UNIT_FLAGS", "target"); fire("UNIT_FACTION", "target")
check(writes() == base, "an unchanged hidden answer writes nothing: " .. (writes() - base) .. " extra write(s)")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown() and writes() == base + 1, "a changed answer is written exactly once")
local shown = writes()
fire("PLAYER_TARGET_CHANGED"); fire("UNIT_HEALTH", "target"); fire("UNIT_HEALTH", "target")
check(writes() == shown, "an unchanged shown answer writes nothing: " .. (writes() - shown) .. " extra write(s)")
""")

case("dot_target_layer_composes_with_the_piece_toggle")(r"""
HAS = true
UnitExists = function() return HAS end
local D = boot({ db = {} })
push(mkState({ corruption = 10 }))
check(isVisible(D.content), "piece on and a target: visible")
FS.Gunsight.SetPiece("dot", false, true)
check(not isVisible(D.content) and D.gate:IsShown(), "piece off with a target: hidden by the piece, the layer is untouched")
HAS = false; fire("PLAYER_TARGET_CHANGED")
FS.Gunsight.SetPiece("dot", true, true)
check(D.frame:IsShown() and not isVisible(D.content), "piece on again with no target: still hidden")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(isVisible(D.content), "piece on and a target again: visible")
FS.Gunsight.SetPiece("dot", false, true)
HAS = false; fire("PLAYER_TARGET_CHANGED")
HAS = true; fire("PLAYER_TARGET_CHANGED")
check(not D.frame:IsShown(), "a target change never re-shows a piece the user turned off")
check(not isVisible(D.content), "piece off stays off through target changes")
check(onUpdateFrames() == 0, "the layer adds no OnUpdate")
""")

case("a_secret_target_answer_keeps_the_dots_shown")(r"""
HAS = false
UnitExists = function() return HAS end
local D = boot({ db = {} })
check(not D.gate:IsShown(), "setup: no target, hidden")
-- the mock calls the plain false UnitExists returns "secret": a truth test would hide the scale (the rule
-- itself is pinned once in theme-harness.py; this proves the dots go through it)
SECRET_FN = function(v) return v == false end
fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown(), "a value IsSecret flags keeps the scale shown (never truth-tested)")
""")

case("a_rescale_does_not_re_show_the_dots_without_a_target")(r"""
HAS = false
UnitExists = function() return HAS end
local D = boot({ db = {} })
SetScreen(1200); fire("UI_SCALE_CHANGED")
check(not D.gate:IsShown() and not isVisible(D.content), "hidden with no target after a rescale")
HAS = true; fire("PLAYER_TARGET_CHANGED")
SetScreen(1440); fire("UI_SCALE_CHANGED")
check(D.gate:IsShown(), "still shown with a target after a rescale")
""")

case("a_target_no_dot_can_land_on_shows_no_scale_and_no_stuck_chip")(r"""
-- The reported bug: a SW:P chip left resting at 0 under a friendly target (THRALL). The ledger knows nothing about
-- a GUID it never saw, so it answers "absent" and the dim hollow chip drew for a target nothing can be DoT'd on.
HAS, ATTACKABLE = true, true
UnitExists = function() return HAS end
UnitCanAttack = function(a, b)
    check(a == "player" and b == "target", "UnitCanAttack asked about " .. tostring(a) .. ", " .. tostring(b))
    return ATTACKABLE
end
local D = boot({ db = {} })
push(mkState({ corruption = 10 }, { targetEpoch = 1 }))
check(D.gate:IsShown() and isVisible(D.chips[1].frame), "an attackable target with a live DoT: chip visible")
ATTACKABLE = false; fire("PLAYER_TARGET_CHANGED")
push(mkState({ corruption = "absent" }, { targetEpoch = 2 }))
check(D.chips[1].mode == "absent", "setup: the ledger reads the unseen friendly GUID as absent")
check(not D.gate:IsShown(), "a target that cannot be attacked: the gate is hidden")
check(not isVisible(D.content) and not isVisible(D.chips[1].frame), "no chip, absent or live, shows under a friendly target")
check(D.frame:IsShown() and FS.Gunsight.IsPieceOn("dot"), "the piece toggle is never touched")
ATTACKABLE = true; fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown() and isVisible(D.chips[1].frame), "back on an attackable target: the absent chip is the refresh cue again")
-- a duel or mind control flips attackability with no target change: UNIT_FLAGS / UNIT_FACTION on the target re-read it
ATTACKABLE = false; fire("UNIT_FACTION", "target")
check(not D.gate:IsShown(), "UNIT_FACTION on the target re-reads attackability")
ATTACKABLE = true; fire("UNIT_FLAGS", "target")
check(D.gate:IsShown(), "UNIT_FLAGS on the target re-reads attackability")
""")

case("a_dead_target_hides_the_scale_because_its_dots_are_gone")(r"""
-- A corpse stays targeted and nothing tells the ledger its DoTs died with it: the chip kept sliding, then sat at 0.
HAS, DEAD = true, false
UnitExists = function() return HAS end
UnitIsDeadOrGhost = function(unit) check(unit == "target", "UnitIsDeadOrGhost asked about " .. tostring(unit)); return DEAD end
local D = boot({ db = {} })
push(mkState({ corruption = 12 }))
check(D.gate:IsShown() and isVisible(D.chips[1].frame), "a live target with a DoT: chip visible")
DEAD = true; fire("UNIT_HEALTH", "target")
check(not D.gate:IsShown() and not isVisible(D.chips[1].frame), "the target died: the scale and its chip are gone")
tick(30)
check(not isVisible(D.chips[1].frame), "and the ledger's expiry never brings the corpse's chip back")
DEAD = false; fire("UNIT_HEALTH", "target")
check(D.gate:IsShown(), "alive again: shown")
DEAD = true; fire("PLAYER_TARGET_CHANGED")
check(not D.gate:IsShown(), "a dead target selected: hidden at once")
-- the death event is a target-only unit event: no all-units UNIT_HEALTH spam
local only
for _, f in ipairs(FRAMES) do
    if f.events.UNIT_HEALTH then only = f.unitOnly and f.unitOnly.UNIT_HEALTH end
end
check(only and #only == 1 and only[1] == "target", "UNIT_HEALTH is registered for the target unit only")
""")

case("an_enemy_ghost_hides_the_scale_like_a_dead_target")(r"""
-- UnitIsDead is false for a ghost; UnitIsDeadOrGhost is the one the shared rule asks, so a released enemy player hides it too
HAS = true
UnitExists = function() return HAS end
UnitIsDead = function() return false end
UnitIsDeadOrGhost = function() return true end
local D = boot({ db = {} })
check(not D.gate:IsShown(), "an enemy ghost: the scale is hidden")
UnitIsDeadOrGhost = function() return false end
fire("UNIT_HEALTH", "target")
check(D.gate:IsShown(), "a live enemy: shown")
""")

case("an_unreadable_target_flag_keeps_the_scale_shown")(r"""
HAS = true
UnitExists = function() return HAS end
local D = boot({ db = {} })
-- a secret answer (FS.IsSecret, checked before anything touches the value) reads as "can take a DoT"
UnitCanAttack = function() return false end
UnitIsDeadOrGhost = function() return true end
SECRET_FN = function(v) return v == false or v == true end
fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown(), "secret UnitCanAttack / UnitIsDeadOrGhost keep the scale shown (never truth-tested)")
-- a throwing or odd answer likewise
SECRET_FN = function() return false end
UnitCanAttack = function() error("hidden API") end
UnitIsDeadOrGhost = function() return "odd" end
fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown(), "a throwing or non-boolean answer keeps the scale shown")
-- the legacy 1 / nil forms still mean true / false
UnitCanAttack = function() return nil end
UnitIsDeadOrGhost = function() return nil end
fire("PLAYER_TARGET_CHANGED")
check(not D.gate:IsShown(), "a plain nil from UnitCanAttack is false: hidden")
UnitCanAttack = function() return 1 end
fire("PLAYER_TARGET_CHANGED")
check(D.gate:IsShown(), "a plain 1 is true: shown")
""")

case("one_chip_that_throws_does_not_strand_the_others")(r"""
-- Apply ran every chip inside ONE pcall: a throw in chip 1 skipped chips 2..4 (and the tick start), so they kept
-- their old look, which on a stale push is a stuck icon. Each chip is its own pcall and the failed one goes off.
local D = boot({ db = {}, class = "WARLOCK" })
push(mkState({ corruption = 10, bane_agony = 10, immolate = 10 }))
check(D.chips[2].mode == "live" and D.chips[3].mode == "live", "setup: three live chips")
local boom = D.chips[1].frame.icon
local thrown = false     -- throws ONCE: the retry below must be able to succeed
boom.SetTexture = function(self, id)
    if id == 666 and not thrown then thrown = true; error("boom") end
    self.path = id
end
local state = mkState({ corruption = 10, bane_agony = "absent", immolate = "absent" })
state.row[1].icon = 666
local ok = pcall(push, state)
check(ok, "the throw never escapes the subscriber")
check(D.chips[1].mode == "off" and not isVisible(D.chips[1].frame), "the chip that threw is off and hidden, not left stale")
check(D.chips[2].mode == "absent" and D.chips[3].mode == "absent", "the chips after it still took the new state")
check(not isVisible(D.chips[1].frame) and isVisible(D.chips[2].frame), "the others are drawn")
check(onUpdateFrames() == 0, "no live chip is left: no OnUpdate")
check(DEGRADED.gunsightdots_state ~= nil, "the failure is logged (once per session), not swallowed")
-- the retry: the SAME bad row again, now that the stub no longer throws. DropChip cleared key / iconId, so the
-- chip reseats its icon; without that clear the cache still reads 666 and the stale icon survives on a live chip
check(D.chips[1].frame.icon.path ~= 666, "setup: the throw left the old icon on the chip")
push(state)
check(D.chips[1].mode == "live" and isVisible(D.chips[1].frame), "the retry shows the chip again")
check(D.chips[1].frame.icon.path == 666, "the retry reseated the icon (a skipped reseat leaves the stale one): " .. tostring(D.chips[1].frame.icon.path))
""")

# One rule decides who owns the seat: FS.HudProfiles.ClassSlot (HudProfiles.lua), shared with ConsoleKeys. This
# file asks it at call time, so a swapped answer must change what is drawn (and a missing helper must not throw).
case("the_class_slot_comes_from_the_shared_helper")(r"""
boot({ db = {}, noEvents = true })
local asked = 0
FS.HudProfiles.ClassSlot = function(p) asked = asked + 1; return "seals" end
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
local D = FS.GunsightDots
check(asked >= 1, "the build asked the shared helper")
check(next(D.parts) == nil and #D.chips == 0, "a Warlock profile with the helper answering seals draws no scale")
boot({ db = {}, class = "PALADIN", noEvents = true })
FS.HudProfiles.ClassSlot = function() return "dots" end
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
D = FS.GunsightDots
check(D.parts.axis and #D.chips == D.D.MAX_LANES, "a Paladin profile with the helper answering dots draws the scale")
-- the helper missing (a load order bug) keeps the old path and says so, instead of throwing
boot({ db = {}, noEvents = true })
FS.HudProfiles.ClassSlot = nil
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
D = FS.GunsightDots
check(D.parts.axis and #D.chips == D.D.MAX_LANES, "no helper: the scale is built as before")
check(DEGRADED.gunsightdots_noclassslot ~= nil, "and the missing helper is logged")
-- a throwing helper is contained the same way
boot({ db = {}, noEvents = true })
FS.HudProfiles.ClassSlot = function() error("boom") end
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
D = FS.GunsightDots
check(D.parts.axis, "a throwing helper keeps the scale")
check(DEGRADED.gunsightdots_classslot ~= nil, "and is logged")
""")

# The build latches the class slot once. If the Hud or its profile cannot be read, say so.
case("an_unreadable_profile_at_build_is_logged")(r"""
boot({ db = {}, noEvents = true })
FS.Hud = nil
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(DEGRADED.gunsightdots_noprofile ~= nil, "FS.Hud missing at build is logged")
boot({ db = {}, noEvents = true })
FS.Hud.GetProfile = nil
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(DEGRADED.gunsightdots_noprofile ~= nil, "GetProfile missing at build is logged")
boot({ db = {}, noEvents = true })
FS.Hud.GetProfile = function() error("boom") end
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(DEGRADED.gunsightdots_noprofile ~= nil, "a throwing GetProfile at build is logged")
-- a class that HAS a shipped profile but GetProfile has none yet: the build would latch the dots path
boot({ db = {}, class = "PALADIN", noEvents = true })
PROFILE = nil
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(DEGRADED.gunsightdots_noprofile ~= nil, "no profile yet for a class that has one is logged")
-- a class with no HUD profile at all is normal: silent
boot({ db = {}, class = "ROGUE", noEvents = true })
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(next(DEGRADED) == nil, "a rogue is silent, got " .. tostring(next(DEGRADED)))
boot({ db = {}, class = "WARLOCK", noEvents = true })
fire("ADDON_LOADED", "forever-stuwave"); fire("PLAYER_LOGIN")
check(next(DEGRADED) == nil, "a warlock is silent, got " .. tostring(next(DEGRADED)))
""")

# The dots path was built because no profile was readable then; if the profile turns out to give the seat to the
# seal chamber, the scale steps aside (hidden, unsubscribed) at the next show or push.
case("a_seal_profile_arriving_after_the_build_yields_on_piece_show")(r"""
local D = boot({ db = {}, class = "ROGUE" })    -- no profile at build: the dots path is built
check(PROFILE == nil and D.parts.axis and #D.chips == D.D.MAX_LANES, "setup: the scale was built")
check(#SUBS == 1, "setup: subscribed")
PROFILE = FS.HudProfiles.PALADIN              -- the Hud resolves the profile late
FS.Gunsight.SetPiece("dot", false, true)
check(#SUBS == 0, "off unsubscribes")
FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 0, "on does not subscribe again: the seat belongs to the seal chamber now")
check(not isVisible(D.content), "the scale content is hidden")
for i, c in ipairs(D.chips) do check(not isVisible(c.frame), "chip " .. i .. " is hidden") end
check(onUpdateFrames() == 0, "nothing runs")
check(D.frame:IsShown() and FS.Gunsight.IsPieceOn("dot"), "the piece itself stays registered and on")
push(mkState({}))
check(not isVisible(D.content), "a later push draws nothing")
check(#AURA_TOUCHED == 0, "no aura API was read")
check(next(DEGRADED) == nil, "no degrade: " .. tostring(next(DEGRADED)))
""")

case("a_seal_profile_arriving_after_the_build_yields_on_a_push")(r"""
local D = boot({ db = {}, class = "ROGUE" })
check(#SUBS == 1, "setup: subscribed")
PROFILE = FS.HudProfiles.PALADIN
IN_COMBAT = true
push(mkState({}, { inCombat = true }))
-- the subscription stays (Hud.Unsubscribe inside the Hud's own push loop would skip a neighbour) but is inert
check(not isVisible(D.content), "the push made the scale step aside: content hidden")
for i, c in ipairs(D.chips) do check(not isVisible(c.frame), "chip " .. i .. " is hidden") end
tick(0.5)
check(onUpdateFrames() == 0, "nothing runs")
fire("PLAYER_REGEN_DISABLED"); fire("PLAYER_REGEN_ENABLED")
check(not isVisible(D.content), "combat events do not bring it back")
push(mkState({}, { inCombat = true, targetEpoch = 9 }))
check(not isVisible(D.content) and onUpdateFrames() == 0, "a further push stays inert")
FS.Gunsight.SetPiece("dot", false, true)
check(#SUBS == 0, "the next piece hide drops the subscription")
FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 0 and not isVisible(D.content), "and showing it again does not bring it back")
check(#AURA_TOUCHED == 0, "no aura API was read")
""")

case("a_seal_profile_arriving_while_chips_are_live_clears_them_and_the_ticker")(r"""
local D = boot({ db = {}, class = "ROGUE" })
PROFILE = FS.HudProfiles.WARLOCK
push(mkState({ corruption = 15, immolate = 10 }))     -- a profile that reads as dots for now: chips go live
check(#liveChips(D) == 2 and onUpdateFrames() == 1, "setup: two live chips, one ticker")
PROFILE = FS.HudProfiles.PALADIN
IN_COMBAT = true
push(mkState({}, { inCombat = true }))
check(#liveChips(D) == 0, "no chip is left live")
for i, c in ipairs(D.chips) do
    check(c.mode == "off" and not isVisible(c.frame), "chip " .. i .. " is off and hidden, mode " .. tostring(c.mode))
end
check(onUpdateFrames() == 0, "the ticker is cleared")
check(not isVisible(D.content), "content hidden")
-- once yielded it stays yielded, whatever the profile says later
PROFILE = FS.HudProfiles.WARLOCK
push(mkState({ corruption = 15 }))
check(not isVisible(D.content) and #liveChips(D) == 0 and onUpdateFrames() == 0, "a later dots push does not bring the scale back")
""")

case("a_dots_profile_arriving_after_the_build_keeps_the_scale")(r"""
local D = boot({ db = {}, class = "ROGUE" })    -- built with no profile, then a Warlock profile arrives
PROFILE = FS.HudProfiles.WARLOCK
push(mkState({ corruption = 10 }))
check(#SUBS == 1 and isVisible(D.content), "a dots profile keeps the scale and the subscription")
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
check(#SUBS == 1, "and a toggle resubscribes")
""")

case("the_registered_flag_follows_the_registry_answer")(r"""
local D = boot({ db = {}, class = "WARLOCK" })
check(D.frame ~= nil and D.registered == true, "an accepted piece reads registered, got " .. tostring(D.registered))
local R = boot({ db = {}, class = "WARLOCK", refusePiece = true })
check(R.frame ~= nil, "setup: the build ran and left its frame")
check(R.registered == false, "a refused registration reads false, got " .. tostring(R.registered))
local T = boot({ db = {}, class = "PALADIN" })
check(T.frame ~= nil and T.registered == true, "the seals class slot registers its piece too")
""")

case("no_aura_api_is_ever_read")(r"""
local D = boot({ db = {}, class = "WARLOCK" })
IN_COMBAT = true
push(mkState({ corruption = 10, bane_agony = 2, immolate = "absent" }))
tick(0.5); tick(5)
push(mkState({}))
FS.Gunsight.SetPiece("dot", false, true); FS.Gunsight.SetPiece("dot", true, true)
check(#AURA_TOUCHED == 0, "an aura API was read: " .. tostring(AURA_TOUCHED[1]))
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("a_throwing_stub_never_escapes_a_push")(r"""
local D = boot({ db = {} })
-- a state with garbage in it must not throw out of the subscriber
local ok = pcall(push, { active = true, row = { { key = "corruption", remaining = "x", expiresAt = "y" } }, buffsMissing = {}, procs = {} })
check(ok, "a malformed row threw out of the subscriber")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, d = toc.index("Modules/CombatHud/Gunsight.lua"), toc.index("Modules/CombatHud/GunsightDots.lua")
        out.append(("toc_order", None if d > g else
                    f"GunsightDots.lua must load after Gunsight.lua (positions {g}, {d})"))
        hp = toc.index("Modules/CombatHud/HudProfiles.lua")
        out.append(("toc_after_hud_profiles", None if d > hp else
                    "GunsightDots.lua must load after HudProfiles.lua (it calls FS.HudProfiles.ClassSlot)"))
        fh = toc.index("Core/FrameHelpers.lua")
        out.append(("toc_after_frame_helpers", None if d > fh else "GunsightDots.lua must load after FrameHelpers.lua"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_stays_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "forever-stuwave.toc must stay CRLF"))
    return out


def run_case(name: str, body: str, mu: dict) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    lua.globals().CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    lua.globals().GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    lua.globals().PROFILES_SRC = PROFILES.read_text(encoding="utf-8")
    lua.globals().DOTS_SRC = DOTS.read_text(encoding="utf-8")
    lua.globals().HAS_TARGET_SRC = _load_gunsight_harness().theme_target_rule_lua()
    lua.execute("MU = " + lua_value(mu))
    chunk = PRELUDE + "\n" + body
    try:
        lua.execute(chunk)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    mu = mockup_dots()
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
    for name, err in static_checks():
        report(name, err)

    total = len(CASES) + len(static_checks())
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
