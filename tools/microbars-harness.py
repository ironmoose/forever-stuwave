#!/usr/bin/env python3
"""Headless check of MicroBars.lua (the twelve micro keys) and the deck slot it seats into.

Runs the real addons/forever-stuwave/Deck.lua and MicroBars.lua under lupa against a small STRICT
mock WoW API (a widget method the mock does not define is a nil call, which the code under test
turns into a degrade log, which every case asserts is empty). The mock models just enough of
Blizzard's micro button to catch the bugs Parker saw in game: textures created by SetNormalAtlas
and friends, a Portrait, flash regions, and Blizzard's own alpha writes on those regions.

What it pins:

  * layout: the keys NEST like the mockup's parallelograms (control-deck-v1-2026-10-01.html: PITCH =
    (KW - LEAN) + 3, LEAN = 0.34 * KW, the lean of media/cell_slant.tga), right-aligned with the
    rightmost box flush with the slot, at UI scale 1 and 0.64; too many keys shrink by one factor;
  * no opaque rectangle under the slanted plate (the old "well" showed as a black square), and the
    glyph drawn once (the old 1.4x ADD copy read as a second, larger icon);
  * Blizzard's own button art (normal, pushed, disabled, highlight, portrait) stays at alpha 0 even
    when Blizzard re-sets an atlas, writes the region's alpha, or creates the region later;
    the button itself is never SetAlpha'd or SetScript'd;
    the flash regions are pinned and hidden by vertex alpha, which a UIFrameFlash alpha write leaves at 0;
  * the SetAlpha hook's re-entry guard is per region;
  * hit rects: each seated button is inset so neighbouring hit rects meet at the middle of the gap;
    nothing is reseated in combat, and the reseat after combat uses the new scale;
  * Deck shape: a plain rectangle chassis (no trapezoid, shoulders, perspective grid, sun, rivets, scanlines or
    breathe animation), built like PetFrame's panel: a two-corner cut fill (slice_cut2_fill) tinted
    Theme.COLOR_HUD_SCRIM and a two-corner cut 1 texel outline tinted COLOR_POWER at the data bar's alpha (read from
    DataBar.lua), with no glow texture, no ADD blend, no gradient on either; the old deck_shoulder, deck_grid and
    deck_sun art is gone from media/.
  * Deck width: chassis = 2 * pad + micro slot + divider + bag slot, and Layout.deck.w is the MAX of that sum (the
    micro slot at the 12 key size). The micro slot FOLLOWS the shown key count (RowWidth of 12, 10 and 9 shown
    keys; more than 12 clamp to the max and shrink): the keys fill it flush, no empty run on the left, and the right
    edge (chassis anchor, bag slot seat, micro slot seat) never moves, so the deck grows and shrinks leftward.
    All of it at UI scale 1 and 0.64 and after a live rescale. In combat the keys are not reseated but the deck width
    always matches them: MicroBars tells Deck from the same reseat path, so after combat both agree. Without FS.Deck
    the keys still seat in the standalone container.

    python3 tools/microbars-harness.py

Exit 0 = every check passed; otherwise the number of failures.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
MICRO_LUA = Path(os.environ.get("MICROBARS_LUA") or ADDON / "Modules/ActionBars/MicroBars.lua")
DECK_LUA = Path(os.environ.get("DECK_LUA") or ADDON / "Modules/ActionBars/Deck.lua")
LAYOUT_LUA = ADDON / "Core/Layout.lua"
THEME_LUA = ADDON / "Core/Theme.lua"
DATABAR_LUA = ADDON / "Modules/DataBars/DataBar.lua"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "control-deck-v1-2026-10-01.html"
CELL_SLANT = ADDON / "Media" / "Textures" / "cell_slant.tga"
EPS = 0.01


# ---------------------------------------------------------------------------------------
# Numbers the mockup, the texture and Layout.lua own. Read, never retyped.
# ---------------------------------------------------------------------------------------

def mockup_numbers() -> tuple[float, float]:
    """(LEAN_FRAC, GAP) from the mockup's `LEAN = 0.34 * KW` and `PITCH = (KW - LEAN) + 3`."""
    src = MOCKUP.read_text(encoding="utf-8")
    lean = re.search(r"LEAN\s*=\s*([\d.]+)\s*\*\s*KW", src)
    gap = re.search(r"PITCH\s*=\s*\(KW\s*-\s*LEAN\)\s*\+\s*([\d.]+)", src)
    if not (lean and gap):
        sys.exit("mockup: LEAN / PITCH constants not found")
    return float(lean.group(1)), float(gap.group(1))


def tga_lean_frac(path: Path) -> float:
    """How far the top edge starts right of the bottom edge, as a fraction of the width."""
    d = path.read_bytes()
    idlen, w, h, bpp, desc = d[0], int.from_bytes(d[12:14], "little"), int.from_bytes(d[14:16], "little"), d[16], d[17]
    px, b = d[18 + idlen:], d[16] // 8

    def alpha(x: int, y: int) -> int:
        row = y if desc & 0x20 else h - 1 - y
        return px[(row * w + x) * b + 3]

    first = lambda y: next(x for x in range(w) if alpha(x, y) > 127)  # noqa: E731
    return (first(0) - first(h - 1)) / w


def theme_color_power() -> tuple[float, float, float, float]:
    """Theme.COLOR_POWER (the cyan every other panel edge uses), read from Theme.lua, never retyped."""
    m = re.search(r"Theme\.COLOR_POWER\s*=\s*\{([^}]*)\}", THEME_LUA.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Theme.lua: Theme.COLOR_POWER not found")
    r, g, b, a = (float(v) for v in m.group(1).split(","))
    return r, g, b, a


def theme_color_scrim() -> tuple[float, float, float, float]:
    """Theme.COLOR_HUD_SCRIM (the panel fill the pet panel uses), read from Theme.lua."""
    m = re.search(r"Theme\.COLOR_HUD_SCRIM\s*=\s*\{([^}]*)\}", THEME_LUA.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Theme.lua: Theme.COLOR_HUD_SCRIM not found")
    r, g, b, a = (float(v) for v in m.group(1).split(","))
    return r, g, b, a


def databar_rail() -> tuple[float, int]:
    """(alpha, height) of the data bar's 1px border rail: the `rail:SetColorTexture(COLOR_POWER..., a)` and
    `rail:SetHeight(h)` pair in DataBar.lua, which the deck border must match."""
    src = DATABAR_LUA.read_text(encoding="utf-8")
    color = re.search(r"rail:SetColorTexture\(COLOR_POWER\[1\],\s*COLOR_POWER\[2\],\s*COLOR_POWER\[3\],\s*([\d.]+)\)", src)
    height = re.search(r"rail:SetHeight\((\d+)\)", src)
    if not (color and height):
        sys.exit("DataBar.lua: the border rail (SetColorTexture / SetHeight) was not found")
    return float(color.group(1)), int(height.group(1))


def layout_deck_w() -> int:
    m = re.search(r"\bdeck\s*=\s*\{\s*w\s*=\s*(\d+)", LAYOUT_LUA.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Layout.lua: deck = { w = ... } not found")
    return int(m.group(1))


# ---------------------------------------------------------------------------------------
# The mock
# ---------------------------------------------------------------------------------------

MOCK = r"""
SCALE, IN_COMBAT, NOW = 1, false, 100
EFFECTIVE_SCALE = 1
RESCALE, LOGS, ALL, POINTCALLS, ANIMGROUPS = {}, {}, {}, 0, {}
local noop = function() end

local M = {}
local Obj = { __index = M }
local function newObj(kind, parent, name)
    local o = setmetatable({ kind = kind, parent = parent, name = name, shown = true, w = 0, h = 0, pts = {},
        level = 0, alpha = 1, alphaWrites = 0, setScriptCalls = 0, regions = {}, kids = {}, hooks = {},
        scripts = {}, events = {}, mouse = true }, Obj)
    ALL[#ALL + 1] = o
    if parent and parent.kids then parent.kids[#parent.kids + 1] = o end
    if name then _G[name] = o end
    return o
end

function M:GetObjectType() return self.kind end
function M:GetName() return self.name end
function M:SetSize(w, h) self.w, self.h = w, h end
function M:SetWidth(w) self.w = w end
function M:SetHeight(h) self.h = h end
function M:GetWidth() return self.w end
function M:GetHeight() return self.h end
function M:SetPoint(point, rel, relPoint, x, y)
    POINTCALLS = POINTCALLS + 1
    self.pts[#self.pts + 1] = { point, rel, relPoint or point, x or 0, y or 0 }
end
function M:ClearAllPoints() self.pts = {}; self.allPoints = nil end
function M:GetPoint(i) local p = self.pts[i or 1]; if p then return p[1], p[2], p[3], p[4], p[5] end end
function M:SetAllPoints(rel) self.pts = {}; self.allPoints = rel or self.parent end
function M:SetParent(p) self.parent = p end
function M:GetParent() return self.parent end
function M:Show() self.shown = true end
function M:Hide() self.shown = false end
function M:SetShown(v) self.shown = v and true or false end
function M:IsShown() return self.shown end
function M:IsForbidden() return false end
function M:IsVisible() return self.shown end
function M:HookScript(which, fn) self.hooks[which] = self.hooks[which] or {}; table.insert(self.hooks[which], fn) end
function M:SetScript(which, fn) self.setScriptCalls = self.setScriptCalls + 1; self.scripts[which] = fn end
function M:HasScript(which) return which == "OnShow" or which == "OnHide" end
function M:RegisterEvent(e) self.events[e] = true end
function M:UnregisterEvent(e) self.events[e] = nil end
function M:EnableMouse(v) self.mouse = v end
function M:IsMouseEnabled() return self.mouse end
function M:SetFrameLevel(l) self.level = l end
function M:GetFrameLevel() return self.level end
function M:SetFrameStrata(s) self.strata = s end
function M:SetClipsChildren(v) self.clips = v and true or false end
function M:SetAlpha(a)
    self.alpha = a; self.alphaWrites = self.alphaWrites + 1
    if self.onAlphaWrite then self.onAlphaWrite(self, a) end   -- test hook: Blizzard code reacting inside a write
end
function M:GetAlpha() return self.alpha end
function M:SetIgnoreParentAlpha() end
function M:SetHitRectInsets(l, r, t, b) self.hit = { l = l, r = r, t = t, b = b }; self.hitCalls = (self.hitCalls or 0) + 1 end
function M:GetChildren() return unpack(self.kids) end
function M:GetRegions() return unpack(self.regions) end
function M:CreateTexture(_, layer, _, sub)
    local t = newObj("Texture", self)
    t.layer, t.sublevel = layer, sub
    self.regions[#self.regions + 1] = t
    return t
end
function M:SetTexture(p) self.tex = p end
function M:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
function M:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a } end
function M:SetBlendMode(mode) self.blend = mode end
function M:SetTexCoord(...) self.coords = { ... } end
-- A MaskTexture does not clip on this client (Theme.lua): the mock raises on one so no key quietly relies on it.
function M:CreateMaskTexture() error("CreateMaskTexture: masks do not clip on this client") end
function M:SetHorizTile() end
function M:SetVertTile() end
function M:SetDesaturated(v) self.desat = v end
function M:SetSnapToPixelGrid(v) self.snap = v end
function M:SetTexelSnappingBias(v) self.bias = v end
function M:GetEffectiveScale() return EFFECTIVE_SCALE end
function CreateColor(r, g, b, a) return { r, g, b, a } end
function M:SetGradient(orientation, c1, c2) self.gradient = { orientation, c1, c2 } end

local function Stub()
    return setmetatable({}, { __index = function(_, k)
        if k == "CreateAnimation" then return function() return Stub() end end
        return noop
    end })
end
function M:CreateAnimationGroup()
    ANIMGROUPS[#ANIMGROUPS + 1] = self
    return Stub()
end

-- Button: Blizzard builds its art through these, creating each region on first use.
local function art(self, slot, atlas)
    if not self[slot] then self[slot] = self:CreateTexture() end
    self[slot].atlas = atlas
    self[slot].alpha = 1     -- a template state change resets the region; the engine does not call SetAlpha for it
end
function M:SetNormalAtlas(a) art(self, "normalTex", a) end
function M:SetPushedAtlas(a) art(self, "pushedTex", a) end
function M:SetDisabledAtlas(a) art(self, "disabledTex", a) end
function M:SetHighlightAtlas(a) art(self, "highlightTex", a) end
function M:GetNormalTexture() return self.normalTex end
function M:GetPushedTexture() return self.pushedTex end
function M:GetDisabledTexture() return self.disabledTex end
function M:GetHighlightTexture() return self.highlightTex end
function M:IsEnabled() return self.isDisabled ~= true end
function M:GetButtonState() return "NORMAL" end
function M:SetButtonState() end

function CreateFrame(kind, name, parent) return newObj(kind, parent, name) end
function hooksecurefunc(a, b, c)
    local tbl, name, fn = a, b, c
    if type(a) == "string" then tbl, name, fn = _G, a, b end
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc(): " .. tostring(name) .. " is not a function") end
    tbl[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
function InCombatLockdown() return IN_COMBAT end
-- The player the keys read when they are built: CLASS_TOKEN / FACTION are set by the World, CLASS_ERR makes UnitClass raise.
function UnitClass()
    if CLASS_ERR then error("UnitClass exploded") end
    return "Local", CLASS_TOKEN, 1
end
function UnitFactionGroup() return FACTION end
function GetTime() return NOW end

UIParent = newObj("Frame", nil, "UIParent")
newObj("Frame", UIParent, "ForeverSTUwaveXPBar")
GameTooltip = newObj("Frame", nil, "GameTooltip")

INSPECT = {}
CONFIG, CALLBACKS = {}, {}
-- The one number the mock treats as a secret value (a secret is still type "number" in the client).
SECRET_W = 100.5
FS = {
    Layout = { Scale = function() return SCALE end, OnRescale = function(fn) RESCALE[#RESCALE + 1] = fn end },
    PanelSkins = { RequireExport = function() return true end, RegisterInspect = function(group, list) INSPECT[group] = list end },
    IsSecret = function(v) return v == SECRET_W end,
    Config = {
        RegisterDefault = function(key, value) if CONFIG[key] == nil then CONFIG[key] = value end end,
        Get = function(key) return CONFIG[key] end,
        Set = function(key, value)
            local old = CONFIG[key]
            CONFIG[key] = value
            if old ~= value then for _, fn in ipairs(CALLBACKS[key] or {}) do fn(value, old, key) end end
        end,
        OnChange = function(key, fn) CALLBACKS[key] = CALLBACKS[key] or {}; table.insert(CALLBACKS[key], fn) end,
    },
    LogDegradeOnce = function(key, msg) LOGS[#LOGS + 1] = key .. ": " .. msg end,
    Theme = { SCANLINE_TEXTURE = "scan", GLOW_EDGE_TEXTURE = "glow", SLICE_CUT_MARGIN = 6,
        SLICE_CUT2_FILL_TEXTURE = "cut2_fill", SLICE_CUT2_OUTLINE_TEXTURE = "cut2_outline" },
}
-- Theme.AddCut2Texture as Theme.lua builds it: one texture covering `frame` (TOPLEFT and BOTTOMRIGHT, `inset`),
-- the path set, nine-sliced at the chamfer margin, tinted by `color`.
function FS.Theme.AddCut2Texture(frame, path, color, layer, sublevel, inset)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND", nil, sublevel)
    t:SetTexture(path)
    t.slice = FS.Theme.SLICE_CUT_MARGIN
    inset = inset or 0
    t:SetPoint("TOPLEFT", frame, "TOPLEFT", inset, -inset)
    t:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -inset, inset)
    if color then t:SetVertexColor(color[1], color[2], color[3], color[4] or 1) end
    return t
end

-- A micro button the way Blizzard builds it: atlas-made art regions, a Background, flash regions, a
-- NotificationOverlay; the Character button also has a Portrait.
function MakeButton(name, index, menu)
    local b = newObj("Button", menu, name)
    b.layoutIndex = index
    b:SetSize(29, 37)
    b:SetNormalAtlas("n"); b:SetPushedAtlas("p"); b:SetDisabledAtlas("d"); b:SetHighlightAtlas("h")
    if name == "HelpMicroButton" then b.normalTex, b.pushedTex, b.disabledTex, b.highlightTex = b.normalTex, nil, nil, nil end
    b.Background = b:CreateTexture()
    b.FlashContent = b:CreateTexture()
    b.FlashBorder = b:CreateTexture()                 -- Mainline: setAllPoints, atlas, UIFrameFlash'd with FlashContent
    if name == "HelpMicroButton" then b.Flash = b:CreateTexture() end   -- Classic's single flash region
    b.NotificationOverlay = newObj("Frame", b)
    if name == "CharacterMicroButton" then b.Portrait = b:CreateTexture() end
    return b
end

-- A forbidden object, the way the client treats one for addon code: IsForbidden answers (true), the
-- name is readable, and every other method raises. Plain fields (set by the mock itself) stay readable.
local function forbid(o)
    o.forbidden, o.kidsAtForbid = true, #o.kids
    setmetatable(o, { __index = function(_, k)
        if k == "IsForbidden" then return function() return true end end
        if k == "GetName" or k == "GetObjectType" then return M[k] end
        if type(M[k]) == "function" then
            return function() error("Attempt to access forbidden object from code tainted by an AddOn", 2) end
        end
    end })
end

BUTTONS = {}
-- STORE: nil | "button" (StoreMicroButton is forbidden) | "window" (StoreFrame is forbidden)
function h_setup(n, hiddenCsv, deckW)
    FS.Theme.COLOR_POWER = COLOR_POWER   -- Theme.lua's values, injected by World before h_setup (Theme loads first in the toc)
    FS.Theme.COLOR_HUD_SCRIM = COLOR_SCRIM
    FS.Layout.deck = deckW and { w = deckW, h = 38, rightMargin = 92 } or nil
    MicroMenu = newObj("Frame", UIParent, "MicroMenu")
    local names = { "CharacterMicroButton", "ProfessionMicroButton", "HelpMicroButton" }
    for i = 1, n do
        local name = names[i] or ("Key" .. i .. "MicroButton")
        if i == STORE_IDX then name = "StoreMicroButton" end
        BUTTONS[i] = MakeButton(name, i, MicroMenu)
        if NOLAYOUT then BUTTONS[i].layoutIndex = nil end
    end
    if STORE then
        local frame = newObj("Frame", UIParent, "StoreFrame")
        if STORE == "window" then forbid(frame) else forbid(BUTTONS[STORE_IDX]) end
    end
    for idx in (hiddenCsv or ""):gmatch("%d+") do BUTTONS[tonumber(idx)]:Hide() end
    if not NODECK then assert(loadstring(DECK_SRC, "@Deck.lua"))("forever-stuwave", FS) end
    assert(loadstring(DATA_SRC, "@IconStyleData.lua"))("forever-stuwave", FS)
    assert(loadstring(STYLE_SRC, "@IconStyle.lua"))("forever-stuwave", FS)
    assert(loadstring(MICRO_SRC, "@MicroBars.lua"))("forever-stuwave", FS)
end
function h_fire(event)
    for _, f in ipairs(ALL) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event) end
    end
end
function h_rescale(s) SCALE = s; for _, fn in ipairs(RESCALE) do fn() end end
function h_runHooks(which) for _, b in ipairs(BUTTONS) do for _, fn in ipairs(b.hooks[which] or {}) do fn(b) end end end
function h_logs() return table.concat(LOGS, "\n") end

-- One row per button: where it sits relative to the slot centre, its size and its hit insets.
function h_keys()
    local out = {}
    for i, b in ipairs(BUTTONS) do
        if rawget(b, "forbidden") then
            out[i] = { name = b.name, shown = false, x = 0, w = 0, h = 0, hitCalls = 0, alphaWrites = 0, setScriptCalls = 0 }
            goto continue
        end
        local _, _, _, x = b:GetPoint(1)
        local hit = b.hit or {}
        out[i] = { name = b.name, shown = b.shown, x = x or 0, w = b.w, h = b.h, hitL = hit.l, hitR = hit.r,
            hitT = hit.t, hitB = hit.b, hitCalls = b.hitCalls or 0, alphaWrites = b.alphaWrites,
            setScriptCalls = b.setScriptCalls }
        ::continue::
    end
    return out
end
-- What our code did to the forbidden StoreMicroButton: it must have touched nothing on it.
function h_storeTouched()
    local b = BUTTONS[STORE_IDX]
    return { newKids = #rawget(b, "kids") - b.kidsAtForbid, fsMicroKey = rawget(b, "fsMicroKey") ~= nil }
end
-- The names MicroBars registered with PanelSkins.RegisterInspect, comma-joined.
function h_inspectNames()
    local out = {}
    for i, e in ipairs(INSPECT.MicroMenu or {}) do out[i] = e.name end
    return table.concat(out, ",")
end
function h_slotW() return (FS.Deck and FS.Deck.microSlot or _G.ForeverSTUwaveMicroBar):GetWidth() end
function h_chassisW() return FS.Deck.frame:GetWidth() end

-- Is `o` a descendant of one of the micro buttons?
local function underButton(o)
    while o do
        for _, b in ipairs(BUTTONS) do if o == b then return true end end
        o = o.parent
    end
    return false
end

-- Textures our overlay made: an opaque colour fill that covers its whole parent frame.
function h_opaqueFills()
    local n = 0
    for _, o in ipairs(ALL) do
        if o.kind == "Texture" and o.color and o.color[4] == 1 and o.allPoints and o.blend ~= "ADD" and underButton(o) then n = n + 1 end   -- the low ADD lift under the ramp is not a well
    end
    return n
end
-- The micro key built for a button (FS.MicroBars.keys), nil before the key exists.
local function keyOf(b)
    for _, k in ipairs(FS.MicroBars.keys) do if k.button == b then return k end end
end
-- What every key draws: the texture of its glyph (a file id, a path or a baked file), and its kind.
function h_glyphPaths()
    local out = {}
    for i, b in ipairs(BUTTONS) do
        local k = keyOf(b)
        if k then out[#out + 1] = { tex = tostring(k.glyph.tex), kind = k.spec.kind, file = k.spec.file } end
    end
    return out
end
-- Per button: the glyph texture (rectangle, layer), the ring texture it must sit under, and the pieces of its look.
function h_glyphInfo()
    local out = {}
    for i, b in ipairs(BUTTONS) do
        local k = keyOf(b)
        local info = { bw = b.w, bh = b.h }
        if k then
            local g = k.glyph
            info.kind, info.tex, info.layer, info.sub, info.c = k.spec.kind, tostring(g.tex), g.layer, g.sublevel, g.coords
            info.w, info.h = g.w, g.h
            info.vertex, info.desat = g.vertex, g.desat
            if #g.pts == 2 then   -- a rectangle between two corners of the key
                info.left, info.right, info.top, info.bottom = g.pts[1][4], -g.pts[2][4], g.pts[1][5], -g.pts[2][5]
            end
            info.edgeLayer, info.edgeSub = k.edge.layer, k.edge.sublevel
            if k.chain then
                local c = k.chain
                info.boostSub, info.modSub, info.liftSub = c.boost.sublevel, c.mod.sublevel, c.lift.sublevel
                info.boostBlend, info.modBlend, info.liftBlend = c.boost.blend, c.mod.blend, c.lift.blend
                info.boostTex, info.modTex, info.liftColor = tostring(c.boost.tex), tostring(c.mod.tex), c.lift.color
                info.boostVertex, info.liftVertex, info.modDesat = c.boost.vertex, c.lift.vertex, c.mod.desat
                info.boostShown, info.modShown, info.liftShown = c.boost.shown, c.mod.shown, c.lift.shown
                info.boostAnchor = c.boost.allPoints == g
                info.modAnchor, info.liftAnchor = c.mod.allPoints == k.cover, c.lift.allPoints == k.cover
                info.boostCoords = c.boost.coords
                info.coverTex, info.coverSub, info.coverLayer = tostring(k.cover.tex), k.cover.sublevel, k.cover.layer
                info.coverShown = k.cover.shown
                info.cl, info.cr = k.cover.pts[1][4], -k.cover.pts[2][4]
                if #g.pts == 2 then
                    info.vert = { g = { g.pts[1][5], -g.pts[2][5] }, c = { k.cover.pts[1][5], -k.cover.pts[2][5] } }
                end
                info.snaps = { g.snap, k.cover.snap, c.boost.snap, c.mod.snap, c.lift.snap }
                info.biases = { g.bias, k.cover.bias, c.boost.bias, c.mod.bias, c.lift.bias }
            end
        end
        out[i] = info
    end
    return out
end
-- GlyphSpec's answers for a class token that is odd: a secret string, a table, a number, nil, an unknown name. The class table
-- is trapped so reading the secret as a key raises.
function h_oddClasses()
    local real = FS.IsSecret
    FS.IsSecret = function(v) return v == "SHAMAN" end
    local classes = FS.IconStyleData.class
    FS.IconStyleData.class = setmetatable({}, { __index = function(_, k)
        if k == "SHAMAN" then error("a secret class token was used as a key") end
        return classes[k]
    end })
    local GS = FS.MicroBars.GlyphSpec
    local out = {}
    for i, c in ipairs({ "SHAMAN", {}, 42, false, "NOTACLASS", "" }) do
        local ok, spec = pcall(GS, "character", nil, c)
        out[i] = ok and spec.kind or "error"
    end
    local ok, spec = pcall(GS, "character", nil, nil)
    out[#out + 1] = ok and spec.kind or "error"
    FS.IsSecret = real
    FS.IconStyleData.class = classes
    return out
end
-- A faction that is a secret value (a string the client will not let code index with), a table or a number never reaches the pvp table.
function h_oddFactions()
    local real = FS.IsSecret
    FS.IsSecret = function(v) return v == "Alliance" end
    local data = FS.IconStyleData
    local pvp = data.pvp
    data.pvp = setmetatable({}, { __index = function(_, k)
        if k == "Alliance" then error("a secret faction was used as a key") end
        return pvp[k]
    end })
    local GS = FS.MicroBars.GlyphSpec
    local out = {}
    for i, f in ipairs({ "Alliance", {}, 42, false }) do
        local ok, spec = pcall(GS, "pvp", f, nil)
        out[i] = ok and tostring(spec.file) or "error"
    end
    local ok, spec = pcall(GS, "pvp", nil, nil)
    out[#out + 1] = ok and tostring(spec.file) or "error"
    FS.IsSecret = real
    data.pvp = pvp
    return out
end
-- Drive one button's state the way the client does: run the hooks of a script, or flip its enabled flag and run OnEnable/OnDisable.
function h_script(i, which)
    local b = BUTTONS[i]
    for _, fn in ipairs(b.hooks[which] or {}) do fn(b) end
end
function h_enabled(i, on)
    local b = BUTTONS[i]
    b.isDisabled = not on
    h_script(i, on and "OnEnable" or "OnDisable")
end
-- Per button: how many textures under it draw the key's glyph texture (the base and, for the game's textures, the ADD copy that
-- brightens it), and how many of those are NOT the base's rectangle (the old 1.4x ADD copy read as a second, larger icon).
function h_glyphCounts()
    local out = {}
    for i, b in ipairs(BUTTONS) do
        local k = keyOf(b)
        local n, strays = 0, 0
        if k then
            for _, o in ipairs(ALL) do
                if o.kind == "Texture" and o.tex ~= nil and o.tex == k.glyph.tex then
                    local p = o.parent
                    while p and p ~= b do p = p.parent end
                    if p == b then
                        n = n + 1
                        local same = o == k.glyph or o.allPoints == k.glyph
                        if not same then strays = strays + 1 end
                    end
                end
            end
        end
        out[i] = { n = n, strays = strays }
    end
    return out
end

-- Blizzard's own art regions and what it does to them.
function h_art(i)
    local b = BUTTONS[i]
    local function a(t) return t and t.alpha or "none" end
    return { normal = a(b.normalTex), pushed = a(b.pushedTex), disabled = a(b.disabledTex),
        highlight = a(b.highlightTex), portrait = a(b.Portrait), background = a(b.Background),
        flash = a(b.FlashContent), flashVertexA = b.FlashContent.vertex and b.FlashContent.vertex[4] or "none", notify = b.NotificationOverlay.alpha,
        flashPinned = b.FlashContent.allPoints == b }
end
-- UIFrameFlash writes the flash regions' alpha every frame; what is left is the vertex colour alpha.
function h_flashPulse(i)
    local b, out = BUTTONS[i], {}
    for _, f in ipairs({ "FlashContent", "FlashBorder", "Flash" }) do
        local r = b[f]
        if r then r:SetAlpha(1); out[f] = r.vertex and r.vertex[4] or "none" end
    end
    return out
end
-- A region's SetAlpha is hooked, then Blizzard writes it from outside; count the writes and see where it ends.
function h_alphaStorm(i)
    local r = BUTTONS[i].normalTex
    r.alphaWrites = 0
    local ok = pcall(r.SetAlpha, r, 1)
    return { ok = ok, writes = r.alphaWrites, alpha = r.alpha }
end
-- Region A's write makes Blizzard code SetAlpha(1) a second region B from inside that write.
function h_nestedAlpha(i)
    local a, b = BUTTONS[i].normalTex, BUTTONS[i].pushedTex
    a.onAlphaWrite = function() b:SetAlpha(1) end
    b.alphaWrites = 0
    local ok = pcall(a.SetAlpha, a, 1)
    a.onAlphaWrite = nil
    return { ok = ok, a = a.alpha, b = b.alpha, writes = b.alphaWrites }
end
function h_blizzOnLeave(i) BUTTONS[i].normalTex:SetAlpha(1) end                 -- MainMenuBarMicroButtonMixin:OnLeave
function h_blizzSetPushed(i) BUTTONS[i].highlightTex:SetAlpha(0.5) end           -- :SetPushed
function h_blizzReatlas(i)                                                       -- LoadMicroButtonTextures again
    local b = BUTTONS[i]
    b:SetNormalAtlas("n2"); b:SetPushedAtlas("p2"); b:SetDisabledAtlas("d2"); b:SetHighlightAtlas("h2")
end
function h_microExports()
    local m = FS.MicroBars
    return { keyLayout = type(m.KeyLayout) == "function", pitch = type(m.Pitch) == "function",
        rowWidth = type(m.RowWidth) == "function" }
end
function h_rowWidth(count) return FS.MicroBars.RowWidth(count) end

-- Chassis decoration: everything drawn on the chassis itself (its own regions) or on a child frame that is not
-- one of the two slots, with enough to judge it.
local function snap(o)
    local pts = {}
    for i, p in ipairs(o.pts) do pts[i] = { point = p[1], rel = p[2] == FS.Deck.frame and "chassis" or "other", relPoint = p[3], x = p[4], y = p[5] } end
    return { tex = o.tex, layer = o.layer, color = o.color, vertex = o.vertex, gradient = o.gradient ~= nil,
        blend = o.blend, w = o.w, h = o.h, slice = o.slice, pts = pts,
        onChassis = o.pts[1] ~= nil and o.pts[1][2] == FS.Deck.frame }
end
local function underChassis(o)
    while o do
        if o == FS.Deck.microSlot or o == FS.Deck.bagSlot then return false end
        if o == FS.Deck.frame then return true end
        o = o.parent
    end
    return false
end
-- Every Texture the deck draws (chassis regions and any decoration host), in creation order.
function h_chassisTextures()
    local out = {}
    for _, o in ipairs(ALL) do
        if o.kind == "Texture" and underChassis(o) then out[#out + 1] = snap(o) end
    end
    return out
end
-- Frames under the chassis other than the two slots, and animation groups and clips anywhere in the deck's own art.
function h_chassisExtras()
    local frames, groups, clips = 0, 0, 0
    for _, o in ipairs(ALL) do
        if o.kind == "Frame" and o ~= FS.Deck.frame and underChassis(o) then frames = frames + 1 end
        if o.clips and underChassis(o) then clips = clips + 1 end
    end
    for _, o in ipairs(ANIMGROUPS) do
        if underChassis(o) then groups = groups + 1 end
    end
    return { frames = frames, groups = groups, clips = clips, strata = FS.Deck.frame.strata, level = FS.Deck.frame.level,
        slotLevel = FS.Deck.microSlot.level }
end
local function pt(o, i) local p = o.pts[i or 1]; if not p then return { n = 0 } end
    return { n = #o.pts, point = p[1], rel = p[2] == FS.Deck.frame and "chassis" or "other", relPoint = p[3], x = p[4], y = p[5] } end
function h_slots()
    local m, b, c = FS.Deck.microSlot, FS.Deck.bagSlot, FS.Deck.frame
    return { mw = m.w, mh = m.h, bw = b.w, bh = b.h, mp = pt(m), bp = pt(b), cw = c.w, ch = c.h, cp = pt(c) }
end
-- The divider mark: the texture using deck_divider, with where it is seated.
function h_divider()
    for _, o in ipairs(ALL) do
        if o.kind == "Texture" and tostring(o.tex or ""):find("deck_divider", 1, true) and underChassis(o) then
            return { found = true, w = o.w, h = o.h, p = pt(o) }
        end
    end
    return { found = false }
end
function h_deckConst()
    local d = FS.Deck
    return { lean = d.LEAN_FRAC, gap = d.KEY_GAP, keyW = d.KEY_W, pad = d.PAD, divider = d.DIVIDER_W, bagW = d.BAG_W,
        microMax = d.MICRO_W_MAX, getMicro = type(d.GetMicroWidth) == "function" and d.GetMicroWidth() or -1,
        hasSet = type(d.SetMicroWidth) == "function" }
end
function h_setMicro(w) return FS.Deck.SetMicroWidth(w) end
function h_hide(i) BUTTONS[i]:Hide() end
function h_show(i) BUTTONS[i]:Show() end
function h_standaloneFrame()
    local f = _G.ForeverSTUwaveMicroBar
    return { exists = f ~= nil, w = f and f.w or -1, deck = FS.Deck ~= nil }
end
"""


class World:
    def __init__(self, n: int = 12, scale: float = 1.0, hidden: tuple[int, ...] = (), layout_cfg: bool = True,
                 store: str | None = None, nolayout: bool = False, deck: bool = True, cls: str | None = "SHAMAN",
                 faction: str | None = "Horde", class_error: bool = False, pixel_factor: float | None = None,
                 effective_scale: float = 1.0, style: str | None = None, help_zoom: float | None = None):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        g = self.lua.globals()
        g.STORE, g.STORE_IDX, g.NOLAYOUT, g.NODECK = store, n, nolayout, not deck   # the Store button is the last one built
        g.DECK_SRC = DECK_LUA.read_text(encoding="utf-8")
        g.MICRO_SRC = MICRO_LUA.read_text(encoding="utf-8")
        g.DATA_SRC = (ADDON / "Core" / "IconStyleData.lua").read_text(encoding="utf-8")
        g.STYLE_SRC = (ADDON / "Core" / "IconStyle.lua").read_text(encoding="utf-8")
        g.CLASS_TOKEN, g.FACTION, g.CLASS_ERR = cls, faction, class_error
        g.EFFECTIVE_SCALE = effective_scale
        if pixel_factor is not None:
            self.lua.execute(f"PixelUtil = {{ GetPixelToUIUnitFactor = function() return {pixel_factor} end }}")
        g.SCALE = scale
        g.HELP_ZOOM = help_zoom
        g.COLOR_POWER = self.lua.table_from(list(theme_color_power()))
        g.COLOR_SCRIM = self.lua.table_from(list(theme_color_scrim()))
        self.g = g
        g.h_setup(n, ",".join(str(h) for h in hidden), layout_deck_w() if layout_cfg else None)
        if help_zoom is not None:   # a zoom on the Help glyph (the generic glyph of every unnamed key) before the keys are built
            self.lua.execute("FS.IconStyleData.micro.help.zoom = HELP_ZOOM")
        if style is not None:   # the icon style setting before the keys are built (the default is stock)
            self.lua.eval("FS.Config.Set")("icons.microstyle", style)

    def login(self) -> "World":
        self.g.h_fire("PLAYER_LOGIN")
        return self

    def keys(self) -> list[dict]:
        blank = {"hitL": None, "hitR": None, "hitT": None, "hitB": None}
        return [{**blank, **dict(v.items())} for _, v in self.g.h_keys().items()]

    def art(self, i: int) -> dict:
        return dict(self.g.h_art(i).items())

    def call(self, fn: str, *args):
        return getattr(self.g, fn)(*args)

    def logs(self) -> str:
        return self.g.h_logs()

    def get(self, name: str):
        return self.lua.eval(name)


# ---------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def near(a: float, b: float, eps: float = EPS) -> bool:
    return abs(a - b) <= eps


def seated(world: World) -> list[dict]:
    return [k for k in world.keys() if k["shown"]]


def check_layout(lean: float, gap: float) -> None:
    for scale in (1.0, 0.64):
        w = World(12, scale).login()
        keys_w = w.call("h_deckConst")["keyW"]
        pitch = (keys_w * (1 - lean) + gap) * scale
        slot_w = w.call("h_slotW")
        ks = seated(w)
        steps = [ks[i + 1]["x"] - ks[i]["x"] for i in range(len(ks) - 1)]
        check(f"layout.pitch_is_nested@{scale}", all(near(s, pitch) for s in steps), f"steps {steps[:3]} want {pitch:.3f}")
        check(f"layout.key_size@{scale}", all(near(k["w"], keys_w * scale) for k in ks), f"{[k['w'] for k in ks[:2]]}")
        right = ks[-1]["x"] + ks[-1]["w"] / 2
        check(f"layout.rightmost_flush@{scale}", near(right, slot_w / 2), f"right {right:.3f} slot/2 {slot_w / 2:.3f}")
        left = ks[0]["x"] - ks[0]["w"] / 2
        check(f"layout.row_fits_slot@{scale}", left >= -slot_w / 2 - EPS, f"left {left:.3f} slot {slot_w:.3f}")
        before = w.get("POINTCALLS")
        w.call("h_runHooks", "OnShow")
        check(f"layout.shown_churn_does_not_reseat@{scale}", w.get("POINTCALLS") == before)
        check(f"layout.no_degrade_logs@{scale}", w.logs() == "", w.logs())

    # Fewer keys shown: the row stays right-aligned at the same pitch, hidden ones are skipped.
    w = World(12, 1.0, hidden=(2, 5, 9)).login()
    ks = seated(w)
    steps = [ks[i + 1]["x"] - ks[i]["x"] for i in range(len(ks) - 1)]
    pitch = (w.call("h_deckConst")["keyW"] * (1 - lean) + gap)
    right = ks[-1]["x"] + ks[-1]["w"] / 2
    check("layout.hidden_keys_leave_the_row", len(ks) == 9 and all(near(s, pitch) for s in steps) and near(right, w.call("h_slotW") / 2))

    # More keys than the slot holds: key width, gap and lean shrink together by one factor.
    w = World(16, 1.0).login()
    ks = seated(w)
    keys_w = w.call("h_deckConst")["keyW"]
    slot_w = w.call("h_slotW")
    natural = keys_w + 15 * (keys_w * (1 - lean) + gap)
    f = slot_w / natural
    steps = [ks[i + 1]["x"] - ks[i]["x"] for i in range(len(ks) - 1)]
    want = (keys_w * (1 - lean) + gap) * f
    ok = (all(near(k["w"], keys_w * f) for k in ks) and all(near(s, want) for s in steps)
          and near(ks[-1]["x"] + ks[-1]["w"] / 2, slot_w / 2) and ks[0]["x"] - ks[0]["w"] / 2 >= -slot_w / 2 - EPS)
    check("layout.overflow_shrinks_by_one_factor", ok, f"f={f:.4f} steps {steps[:2]} widths {[k['w'] for k in ks[:2]]}")


def check_overlay() -> None:
    w = World(12).login()
    check("overlay.no_opaque_rect_under_the_plate", w.call("h_opaqueFills") == 0, f"{w.call('h_opaqueFills')} opaque fills")
    counts = [dict(c.items()) for _, c in w.call("h_glyphCounts").items()]
    check("overlay.glyph_and_its_copy_only_per_key", all(c["n"] <= 2 and c["strays"] == 0 for c in counts), f"{counts[:2]}")


def tga_header(path: Path) -> tuple[int, int, int, int, int, int]:
    """(image type, width, height, bits per pixel, descriptor, file size) of a TGA."""
    data = path.read_bytes()
    h = data[:18]
    return h[2], int.from_bytes(h[12:14], "little"), int.from_bytes(h[14:16], "little"), h[16], h[17], len(data)


CLASS_NAMES = {"WARRIOR": "Warrior", "PALADIN": "Paladin", "HUNTER": "Hunter", "ROGUE": "Rogue", "PRIEST": "Priest",
               "SHAMAN": "Shaman", "MAGE": "Mage", "WARLOCK": "Warlock", "DRUID": "Druid"}
# Independent oracle: the ramp and cover files the generator writes, and the two keys drawn from our own hand drawn shapes.
OWN_BAKED = ["glyphart_character.tga", "glyphart_legacy.tga"]


def spec_dict(spec) -> dict:
    out = {str(k): v for k, v in spec.items()}
    if "coords" in out:
        out["coords"] = [spec.coords[i] for i in range(1, len(spec.coords) + 1)]
    out["size"] = [spec.size[i] for i in (1, 2)] if spec.size is not None else None
    out["limit"] = [spec.limit[i] for i in (1, 2, 3, 4)] if spec.limit is not None else None
    return out


def check_glyph_files() -> None:
    """Every micro entry resolves to the game's own texture with a look, or to our own baked art, and the data is sane."""
    media = ADDON / "Media" / "Textures"
    w = World(12).login()
    infos = [dict(v.items()) for _, v in w.call("h_glyphInfo").items()]
    check("glyphs.every_built_key_has_a_glyph", len(infos) == 12 and all(i.get("kind") for i in infos), f"{len(infos)}")
    check("glyphs.no_built_key_wears_a_baked_game_texture",
          all(i["kind"] == "runtime" or str(i["tex"]).endswith(tuple(OWN_BAKED)) for i in infos), f"{[i['tex'] for i in infos]}")

    mb = w.get("FS.MicroBars")
    data = w.get("FS.IconStyleData")
    stems = sorted({str(v) for _, v in mb.Glyphs.items()} | {str(mb.GlyphGeneric)})
    own = {"character", "legacy"}
    ramps = {str(k) for k, _ in data.ramps.items()}
    rect_aspect = (data.cover.x1 - data.cover.x0) * 34 / 26   # the icon rectangle: the cover's columns by the key's height
    bad: list[str] = []
    n_runtime = 0
    for stem in stems:
        for faction in ("Alliance", "Horde", "Neutral", None):
            spec = spec_dict(mb.GlyphSpec(stem, faction, "SHAMAN"))
            if spec["kind"] == "baked":
                if stem not in own or not str(spec["file"]).endswith(f"glyphart_{stem}.tga"):
                    bad.append(f"{stem}/{faction} baked {spec['file']}")
                continue
            n_runtime += 1
            c, size, limit = spec["coords"], spec["size"], spec["limit"]
            # upright, never sheared: four values (l, r, t, b) of the texture, and the texel window has the rectangle's aspect
            # (the rectangle is the key's inside, 32 x 26 design px), so the picture is zoomed to fill it and never stretched
            shape = (len(c) == 4 and all(0 <= v <= 1 for v in c) and c[0] < c[1] and c[2] < c[3] and size is not None
                     and abs(((c[1] - c[0]) * size[0]) / ((c[3] - c[2]) * size[1]) / rect_aspect - 1) <= 0.02
                     # and the window sits inside the glyph's own part of the texture (the limit)
                     and limit is not None and limit[0] <= c[0] + 1e-4 and c[1] <= limit[1] + 1e-4 and limit[2] <= c[2] + 1e-4 and c[3] <= limit[3] + 1e-4)
            ok = (isinstance(spec["file"], (int, str)) and shape and str(spec["fam"]) in ramps and 0 <= spec["boost"] <= 1)
            if not ok:
                bad.append(f"{stem}/{faction} {spec}")
    check("glyphs.every_name_and_faction_resolves_to_a_sound_spec", len(stems) >= 18 and "character" in stems and "legacy" in stems
          and n_runtime >= 16 * 4 and not bad, f"{len(stems)} stems, {n_runtime} runtime, bad {bad[:2]}")
    # Character is the class icon, Legacy always our own art, and every other name draws a game texture.
    check("glyphs.legacy_is_our_own_baked_art", spec_dict(mb.GlyphSpec("legacy", None, "SHAMAN"))["kind"] == "baked")
    check("glyphs.the_nonexistent_name_gets_the_generic_glyph",
          spec_dict(mb.GlyphSpec("nonsense", None, None))["file"] == spec_dict(mb.GlyphSpec(str(mb.GlyphGeneric), None, None))["file"])
    # all nine classes: the class icon path is the client's own Interface\Icons\ClassIcon_<Class>
    got = {t: spec_dict(mb.GlyphSpec("character", None, t)) for t in CLASS_NAMES}
    check("glyphs.all_nine_classes_wear_their_own_class_icon",
          all(g["kind"] == "runtime" and g["file"] == f"Interface\\Icons\\ClassIcon_{CLASS_NAMES[t]}" and len(g["coords"]) == 4
              and g["coords"][:2] == [0.07, 0.93] and near(g["coords"][3] - g["coords"][2], 0.86 * 26 / 32, 1e-3)
              and near(g["coords"][2] + g["coords"][3], 1.0, 1e-3) for t, g in got.items()), f"{got}")
    check("glyphs.the_nine_class_icons_are_nine_different_files", len({g["file"] for g in got.values()}) == 9)
    fallback = [str(v) for _, v in w.call("h_oddClasses").items()]
    check("glyphs.a_secret_nil_unknown_or_odd_class_token_gets_the_person_glyph_and_is_never_indexed",
          fallback == ["baked"] * 7, f"{fallback}")
    # PvP follows the faction, and an odd faction gets the free emblem
    pvp = {f: spec_dict(mb.GlyphSpec("pvp", f, None))["file"] for f in ("Alliance", "Horde", "Neutral", None)}
    check("glyphs.pvp_follows_the_players_faction",
          pvp["Alliance"] != pvp["Horde"] and pvp["Neutral"] == pvp[None] and len(set(pvp.values())) == 3, f"{pvp}")
    odd = [str(v) for _, v in w.call("h_oddFactions").items()]
    check("glyphs.a_secret_or_non_string_faction_gets_the_free_emblem_and_is_never_indexed",
          len(odd) == 5 and set(odd) == {str(pvp[None])}, f"{odd}")

    # Which class the key shows is read when the key is built
    for token in ("PRIEST", "WARRIOR"):
        first = dict(World(12, cls=token).login().call("h_glyphInfo")[1].items())
        check(f"glyphs.the_character_key_reads_the_class_at_build.{token.lower()}",
              str(first["tex"]).endswith(f"ClassIcon_{CLASS_NAMES[token]}"), f"{first['tex']}")
    for label, kwargs in (("no_class", {"cls": None}), ("class_lookup_raises", {"class_error": True})):
        info = dict(World(12, **kwargs).login().call("h_glyphInfo")[1].items())
        check(f"glyphs.the_character_key_falls_back_to_the_person_glyph.{label}", str(info["tex"]).endswith("glyphart_character.tga"), f"{info['tex']}")
    check("glyphs.no_degrade_logs", w.logs() == "", w.logs())

    # What is shipped: our own two baked keys, the ramps and the covers; nothing derived from the game.
    baked = sorted(p.name for p in media.glob("glyphart_*.tga"))
    check("glyphs.only_our_own_hand_drawn_keys_are_baked", baked == OWN_BAKED, f"{baked}")
    bad = [n for n in baked if tga_header(media / n) != (2, 64, 64, 32, 0x28, 18 + 64 * 64 * 4)]
    check("glyphs.baked_art_is_64x64_bgra_tga_of_exact_size", not bad, f"bad {bad}")
    missing = [str(r.file) for _, r in data.ramps.items() if not (media / str(r.file)).exists()]
    missing += [str(data.cover.file)] if not (media / str(data.cover.file)).exists() else []
    check("glyphs.every_ramp_and_the_cover_is_shipped", not missing and len(ramps) == 9, f"{missing}")
    odd_sizes = [str(r.file) for _, r in data.ramps.items() if tga_header(media / str(r.file))[:4] != (2, 8, 8, 32)]
    odd_sizes += [str(data.cover.file)] if tga_header(media / str(data.cover.file))[:4] != (2, 128, 128, 32) else []
    check("glyphs.ramps_are_8x8_and_the_cover_128x128_bgra", not odd_sizes, f"{odd_sizes}")
    # The baked keys' alpha IS the key's slanted shape: compare against the shape recomputed from the key's geometry
    # (tools/assets/synthwave_icons.py key_shape_alpha), within one 8 bit step. That pins the fixed crop band (rows 7 to
    # 56 of 64) and also the lean, any horizontal shift and any clipped corner.
    spec = importlib.util.spec_from_file_location("synthwave_icons", HERE / "assets" / "synthwave_icons.py")
    icons = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(icons)
    want = [round(float(v) * 255) for v in icons.key_shape_alpha(64).reshape(-1)]
    off = {}
    for n in baked:
        raw = (media / n).read_bytes()[18:]
        worst = max(abs(raw[i * 4 + 3] - w_) for i, w_ in enumerate(want))
        if worst > 1:
            off[n] = worst
    check("glyphs.baked_art_alpha_is_the_keys_shape", len(baked) == 2 and not off, f"off by more than one step: {off}")
    # Outside the shape the RGB is the plate colour, not the art: a straight alpha bilinear fetch blends in the RGB of
    # transparent texels, and bright art there would fringe into the gap.
    dark = (0x14, 0x0A, 0x24)
    bleed = {}
    for n in baked:
        raw = (media / n).read_bytes()[18:]
        worst = 0
        for i in range(0, len(raw), 4):
            if raw[i + 3] == 0:
                worst = max(worst, abs(raw[i + 2] - dark[0]), abs(raw[i + 1] - dark[1]), abs(raw[i] - dark[2]))
        if worst > 3:
            bleed[n] = worst
    check("glyphs.transparent_texels_carry_the_plate_colour_not_the_art", not bleed, f"{bleed}")
    stale = sorted(p.name for p in media.glob("glyph_*.tga") if not p.name.startswith("glyph_hud_"))
    check("glyphs.no_unreferenced_line_glyph_files", not stale, f"{stale}")
    check("glyphs.no_degrade_logs_after_the_file_checks", w.logs() == "", w.logs())


def _plate_and_ring(info: dict, px: float):
    """The key's plate and ring alpha (0..1, rows top to bottom) at `px` screen px per design px, from the real textures."""
    media = ADDON / "Media" / "Textures"
    kw, kh = round(info["bw"] * px), round(info["bh"] * px)
    out = []
    for name in ("cell_slant.tga", "deck_key_slant_outline.tga"):
        im = Image.open(media / name).convert("RGBA").getchannel("A")
        out.append(np.asarray(im.resize((kw, kh), Image.BILINEAR), dtype=float) / 255)
    return out[0], out[1], kw, kh


def _inside(plate, ring, px: float):
    """True where a pixel is well inside the key: on the plate and clear of the ring's line (the ring draws over the rest)."""
    kh, kw = plate.shape
    reach = round(px * 0.5) + 1
    padded = np.pad(ring, reach, mode="edge")
    near_ring = np.max([padded[reach + dy:reach + dy + kh, reach + dx:reach + dx + kw]
                        for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)], axis=0)
    return (plate - near_ring) >= 0.75


def check_cover_geometry() -> None:
    """The icon is a plain rectangle and the cover hides what sticks out of the slanted key. At every key count, and at 3 and
    1 screen px per design px (1 is the live case on a 2560x1440 window, where the 128 texel art is minified to about 34), the
    cover must hide every texel of the rectangle outside the plate and must stay off the plate's inside (the ring draws over it).
    The cover texture is compared with the REAL plate and ring, so a cover that leans the wrong way (\\ for /) fails here."""
    media = ADDON / "Media" / "Textures"
    bad = {}
    for count, px in ((c, k) for c in (12, 14, 16, 18) for k in (3, 1)):
        w = World(count).login()
        keys = list(w.get("FS.MicroBars.keys").values())
        for i, info in enumerate((dict(v.items()) for _, v in w.call("h_glyphInfo").items())):
            if info.get("kind") != "runtime" or keys[i].spec.zoom is not None:   # a zoomed-out glyph leaves the sides to the plate on purpose
                continue
            plate, ring, kw, kh = _plate_and_ring(info, px)
            left, right = round(info["cl"] * px), round(info["cr"] * px)
            cover_im = Image.open(media / "iconcover_key.tga").convert("RGBA").getchannel("A")
            cover = np.asarray(cover_im.resize((kw - left - right, kh), Image.BILINEAR), dtype=float) / 255
            region = slice(left, kw - right)
            outside = 1.0 - plate[:, region]
            leak = float((outside - cover).max())            # outside the plate and not covered: the icon would show there
            inner = _inside(plate, ring, px)[:, region]
            under = float(cover[inner].max()) if inner.any() else 0.0   # the cover over the plate's inside would hide icon
            if leak > 0.08 or under > 0.2:
                bad[(count, px, i)] = (round(leak, 2), round(under, 2))
    check("cover.hides_everything_outside_the_plate_and_nothing_inside_it_at_every_key_count", not bad, f"{len(bad)} bad, first {list(bad.items())[:3]}")
    # and it meets the ring: along the ring's soft inner edge (its alpha falling from 0.15 to 0.04, the first design px inside
    # the line) the cover is clear, so no band of plate colour is left between the ring and the art
    info = dict(World(12).login().call("h_glyphInfo")[1].items())
    px = 8
    plate, ring, kw, kh = _plate_and_ring(info, px)
    left, right = round(info["cl"] * px), round(info["cr"] * px)
    cover_im = Image.open(media / "iconcover_key.tga").convert("RGBA").getchannel("A")
    cover = np.asarray(cover_im.resize((kw - left - right, kh), Image.BILINEAR), dtype=float) / 255
    edge = ((plate >= 0.9) & (ring >= 0.04) & (ring <= 0.15))[:, left:kw - right]
    band = float(cover[edge].max()) if edge.any() else 1.0
    check("cover.is_clear_right_up_to_the_rings_inner_edge", edge.sum() > 200 and band < 0.35, f"{int(edge.sum())} edge pixels, cover up to {band:.2f}")


def check_slant_direction() -> None:
    """The slant is pinned against the key plate: the plate leans / (its top row sits right of its bottom row), the ring the
    same, and so does the cover's clear area; the cover's SOLID wedges are the top left and the bottom right."""
    media = ADDON / "Media" / "Textures"
    w = World(12).login()
    info = dict(w.call("h_glyphInfo")[1].items())
    plate, ring, kw, kh = _plate_and_ring(info, 8)
    centre = lambda a: float((a.sum(axis=0) * np.arange(a.shape[1])).sum() / a.sum())  # noqa: E731
    top_p, bottom_p = centre(plate[: kh // 8]), centre(plate[-kh // 8:])
    top_r, bottom_r = centre(ring[: kh // 8]), centre(ring[-kh // 8:])
    check("slant.the_plate_and_the_ring_lean_slash", top_p > bottom_p + 20 and top_r > bottom_r + 20, f"plate {top_p:.0f}/{bottom_p:.0f} ring {top_r:.0f}/{bottom_r:.0f}")
    cover = np.asarray(Image.open(media / "iconcover_key.tga").convert("RGBA").getchannel("A"), dtype=float) / 255
    clear = 1.0 - cover
    top_c, bottom_c = centre(clear[: len(clear) // 8]), centre(clear[-len(clear) // 8:])
    check("slant.the_covers_clear_area_leans_the_same_way", top_c > bottom_c + 10, f"{top_c:.0f} {bottom_c:.0f}")
    n = cover.shape[0]
    tl, tr, bl, br = (float(cover[:n // 4, :n // 4].mean()), float(cover[:n // 4, -n // 4:].mean()),
                      float(cover[-n // 4:, :n // 4].mean()), float(cover[-n // 4:, -n // 4:].mean()))
    check("slant.the_solid_wedges_are_the_top_left_and_the_bottom_right", tl > 0.8 and br > 0.8 and tr < 0.6 and bl < 0.6 and tl - tr > 0.35 and br - bl > 0.35, f"tl {tl:.2f} tr {tr:.2f} bl {bl:.2f} br {br:.2f}")
    # the cover and the plate line up: where the plate is solid and well inside, the cover is clear, in every corner of the key
    inner = _inside(plate, ring, 8)
    cov_at_key = np.asarray(Image.open(media / "iconcover_key.tga").convert("RGBA").getchannel("A").resize(
        (round(info["cr"] * 0 + (1 - 0) * 0) + round((w.get("FS.IconStyleData.cover.x1") - w.get("FS.IconStyleData.cover.x0")) * kw), kh), Image.BILINEAR), dtype=float) / 255
    x0 = round(w.get("FS.IconStyleData.cover.x0") * kw)
    inside_in_cover = inner[:, x0:x0 + cov_at_key.shape[1]]
    check("slant.the_cover_is_clear_wherever_the_plate_is_well_inside", float(cov_at_key[inside_in_cover].max()) < 0.2)


def _texcoords_at(coords: list[float], fx: np.ndarray, fy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The texture point the client draws at fractions (fx, fy) of the glyph rectangle: SetTexCoord's four values (l, r, t, b)
    stretch that window over it."""
    l, r, t, b = coords
    return l + (r - l) * fx, t + (b - t) * fy


def _key_wedge_misses(info: dict, px: float, tol: float = 0.004) -> int:
    """How many pixels inside the ring of the built key `info` (drawn at `px` screen pixels per UI unit) are not drawn from the
    glyph's own window: the glyph's rectangle is placed by its two corner offsets, whole pixels where the client says so."""
    plate, ring, kw, kh = _plate_and_ring(info, px)
    inner = _inside(plate, ring, px)
    gl, gr = round(info["left"] * px), kw - round(info["right"] * px)
    n = len(info["c"])
    coords = [float(info["c"][k]) for k in range(1, n + 1)]
    if n != 4:   # a glyph is upright: four texcoords
        return -1
    wl, wr, wt, wb = coords
    ys, xs = np.nonzero(inner)
    fx, fy = (xs + 0.5 - gl) / (gr - gl), (ys + 0.5) / kh
    u, v = _texcoords_at(coords, fx, fy)
    miss = (fx < 0) | (fx > 1) | (u < wl - tol) | (u > wr + tol) | (v < wt - tol) | (v > wb + tol)
    return int(miss.sum())


def check_no_empty_wedge() -> None:
    """No plate pixel inside the ring is left without art: every pixel inside the key's ring is drawn from the glyph's own window
    of the game's texture. The key leans /, so a glyph rectangle narrower than the key's inside leaves a wedge with no art at
    two corners; an upright glyph is zoomed to fill the whole inside (the cover's columns, full height, four texcoords) and
    the cover trims the two outside triangles. Checked per key against the real plate and ring, at every key count and at 3
    and 1 screen px per design px."""
    bad = {}
    seen = set()
    tol = 0.004  # texture fractions, a quarter texel of a 64 texel texture
    for count, px in ((c, k) for c in (12, 16) for k in (3, 1)):
        w = World(count).login()
        keys = list(w.get("FS.MicroBars.keys").values())
        for i, info in enumerate((dict(v.items()) for _, v in w.call("h_glyphInfo").items())):
            if info.get("kind") != "runtime" or keys[i].spec.zoom is not None:   # a zoomed-out glyph leaves the sides to the plate on purpose
                continue
            seen.add(count)
            missed = _key_wedge_misses(info, px, tol)
            if missed:
                bad[(count, px, i)] = missed
    check("wedge.every_pixel_inside_the_ring_is_drawn_from_the_glyphs_own_window_at_every_key_count", seen == {12, 16} and not bad,
          f"{len(bad)} keys, first {list(bad.items())[:3]}")
    # the world only builds a few keys (the rest wear the generic glyph), so every entry of the data is walked too: the micro
    # buttons, the faction emblems and the nine class icons, in the rectangle SizeKey gives them
    w = World(12).login()
    data = w.get("FS.IconStyleData")
    info = dict(w.call("h_glyphInfo")[1].items())
    entries = [(f"micro.{k}", e) for k, e in data.micro.items()] + [(f"pvp.{k}", e) for k, e in data.pvp.items()] + [(f"class.{k}", e) for k, e in data["class"].items()]
    bad = {}
    for px in (3, 1):
        plate, ring, kw, kh = _plate_and_ring(info, px)
        inner = _inside(plate, ring, px)
        gl, gr = round(data.cover.x0 * kw), round(data.cover.x1 * kw)
        ys, xs = np.nonzero(inner)
        fx, fy = (xs + 0.5 - gl) / (gr - gl), (ys + 0.5) / kh
        for name, e in entries:
            if e.zoom is not None:   # zoomed out: the picture is drawn narrower, so the sides are plate (check_zoomed_key)
                continue
            coords = [float(e.coords[k]) for k in range(1, len(e.coords) + 1)]
            if len(coords) != 4:   # a glyph is upright: four texcoords
                bad[(px, name)] = -1
                continue
            wl, wr, wt, wb = coords
            u, v = _texcoords_at(coords, fx, fy)
            miss = (fx < 0) | (fx > 1) | (u < wl - tol) | (u > wr + tol) | (v < wt - tol) | (v > wb + tol)
            if miss.any():
                bad[(px, name)] = int(miss.sum())
    check("wedge.every_entry_of_the_data_draws_every_pixel_inside_the_ring_from_its_own_window", len(entries) == 15 + 3 + 9 and not bad,
          f"{len(entries)} entries, {len(bad)} bad, first {list(bad.items())[:3]}")


def check_fill() -> None:
    """The game's textures get a plain rectangle over the key's inside (the cover's columns, full height) with the cover over it,
    in a fixed order under the ring (no mask: it would not clip); our own baked art covers its key, cropped to a FIXED band so
    the baked slant matches the plate at any key width."""
    baked_pad = (1 - 26 / 34) / 2  # the baked shape's rows (tools/assets/synthwave_icons.py KEY_W, KEY_H)
    data = World(12).login().get("FS.IconStyleData")
    cover_cols = (data.cover.x0, data.cover.x1)
    for count, scale in ((12, 1.0), (12, 0.64), (14, 1.0), (16, 1.0)):
        w = World(count, scale=scale).login()
        infos = [dict(v.items()) for _, v in w.call("h_glyphInfo").items()]
        keys = list(w.get("FS.MicroBars.keys").values())
        tag = f"keys_{count}_scale_{scale}"
        check(f"fill.{tag}.every_key_has_a_glyph", len(infos) == count and all(i["kind"] == "runtime" for i in infos), f"{len(infos)}")
        # the glyph and the cover span the cover's columns, in whole pixels
        # a zoomed-out key (data `zoom`) draws its glyph narrower, centred in these columns (check_zoomed_key); the cover is the same
        zoomed = [k.spec.zoom is not None for k in keys]
        glyph_ok = [abs(i["cl"] - cover_cols[0] * i["bw"]) <= 0.5 and abs(i["cr"] - (1 - cover_cols[1]) * i["bw"]) <= 0.5
                    and i["cl"] == int(i["cl"]) and i["cr"] == int(i["cr"])
                    and ((i["left"] >= i["cl"] and i["right"] >= i["cr"]) if z else
                         (abs(i["left"] - cover_cols[0] * i["bw"]) <= 0.5 and abs(i["right"] - (1 - cover_cols[1]) * i["bw"]) <= 0.5
                          and i["left"] == int(i["left"]) and i["right"] == int(i["right"])))
                    for i, z in zip(infos, zoomed)]
        check(f"fill.{tag}.the_glyph_sits_in_the_covers_columns_in_whole_pixels", all(glyph_ok), f"{[(i['left'], i['right']) for i in infos][:3]}")
        cover_ok = [z or (i["cl"] == i["left"] and i["cr"] == i["right"]) for i, z in zip(infos, zoomed)]
        check(f"fill.{tag}.the_cover_and_the_glyph_share_the_same_columns", all(cover_ok), f"{[(i['cl'], i['cr'], i['left'], i['right']) for i in infos][:3]}")
        # full height: within half a UI unit (the height is rounded to whole pixels, see check_crisp), both pieces alike
        check(f"fill.{tag}.the_rectangles_are_the_keys_full_height",
              all(i["top"] == 0 and abs(i["bottom"]) <= 0.5 + EPS and tuple(i["vert"]["g"].values()) == tuple(i["vert"]["c"].values()) for i in infos),
              f"{[(i['top'], i['bottom']) for i in infos][:2]}")
        check(f"fill.{tag}.the_boost_follows_the_glyph_and_the_ramp_and_lift_follow_the_cover", all(i["boostAnchor"] and i["modAnchor"] and i["liftAnchor"] for i in infos))
        order = [(i["sub"], i["boostSub"], i["modSub"], i["liftSub"], i["coverSub"], i["edgeSub"]) for i in infos]
        check(f"fill.{tag}.glyph_boost_ramp_lift_cover_then_the_ring_in_that_order",
              all(all(x < y for x, y in zip(o, o[1:])) and i["layer"] == i["edgeLayer"] == i["coverLayer"] == "ARTWORK" for o, i in zip(order, infos)), f"{order[:1]}")
        check(f"fill.{tag}.the_lowest_piece_is_inside_the_engines_sublevel_range", all(-8 <= o[0] and o[-1] <= 7 for o in order), f"{order[:1]}")
        check(f"fill.{tag}.blend_modes_are_ADD_MOD_ADD", all((i["boostBlend"], i["modBlend"], i["liftBlend"]) == ("ADD", "MOD", "ADD") for i in infos))
        check(f"fill.{tag}.the_boost_copy_and_the_glyph_show_the_same_window",
              all(i["boostTex"] == i["tex"] and i.get("boostCoords") is not None and len(i["boostCoords"]) == len(i["c"])
                  and [i["boostCoords"][k] for k in range(1, len(i["c"]) + 1)] == [i["c"][k] for k in range(1, len(i["c"]) + 1)] for i in infos),
              f"{infos[0].get('boostCoords')} {infos[0]['c']}")
        check(f"fill.{tag}.the_glyph_and_its_spec_are_four_upright_texcoords",
              all(len(i["c"]) == 4 and len(k.spec.coords) == 4 for i, k in zip(infos, keys)), f"{[len(i['c']) for i in infos]}")
        check(f"fill.{tag}.no_degrade_logs", w.logs() == "", w.logs())
    # a key without a class (our own baked art): the whole key, the fixed band
    for count, scale in ((12, 1.0), (14, 1.0)):
        w = World(count, scale=scale, cls=None).login()
        first = dict(w.call("h_glyphInfo")[1].items())
        tag = f"baked_{count}_scale_{scale}"
        check(f"fill.{tag}.art_is_the_size_of_the_key", near(first["w"], first["bw"]) and near(first["h"], first["bh"]), f"{first['w']}x{first['h']} vs {first['bw']}x{first['bh']}")
        check(f"fill.{tag}.art_crops_to_the_baked_band",
              near(first["c"][1], 0) and near(first["c"][2], 1) and near(first["c"][3], baked_pad) and near(first["c"][4], 1 - baked_pad), f"{first['c']}")
        check(f"fill.{tag}.ring_draws_over_the_icon", first["layer"] == "ARTWORK" and first["edgeLayer"] == "ARTWORK" and first["sub"] < first["edgeSub"])
        check(f"fill.{tag}.a_baked_key_has_no_overlays", first.get("boostSub") is None, f"{first.get('boostSub')}")


def check_crisp() -> None:
    """Pixel crisp: where the client says what a physical pixel is, every edge of the icon pieces is a whole number of them, and
    the pieces have the engine's own snapping off and a texel bias of 0. Without the numbers (no PixelUtil) whole UI units."""
    # UI scale 0.64 of a 1440 screen: 34 design px * 0.64 = 21.76
    # The first two cases have a pixel of exactly one UI unit (the effective scale equals the factor), so edges on whole UI units
    # are whole pixels there: they pin the scale 0.64 sizes only. The cases that tell rounding to physical pixels from rounding
    # to UI units are the effective scale 1.0 one (a pixel of 0.5333 units) and the live one, (768 / 1440, 0.64, 0.64): a pixel
    # of 0.8333 units, so no edge falls on a whole unit by luck.
    for factor, eff, scale in ((768 / 1440, 768 / 1440, 0.64), (768 / 1080, 768 / 1080, 0.64), (768 / 1440, 1.0, 1.0), (768 / 1440, 0.64, 0.64)):
        w = World(12, scale=scale, pixel_factor=factor, effective_scale=eff).login()
        px = factor / eff
        infos = [dict(v.items()) for _, v in w.call("h_glyphInfo").items()]
        offs = [(i["left"], i["right"], i["cl"], i["cr"]) for i in infos]
        whole = all(abs(v / px - round(v / px)) < 1e-6 for o in offs for v in o)
        check(f"crisp.every_edge_is_a_whole_number_of_physical_pixels.factor_{factor:.3f}_eff_{eff:.4f}_scale_{scale}", whole, f"px {px:.4f} {offs[:2]}")
        cover_x0 = w.get("FS.IconStyleData.cover.x0")
        check(f"crisp.no_piece_is_more_than_half_a_pixel_off_its_design_place.eff_{eff:.4f}_scale_{scale}",
              all(abs(i["cl"] - cover_x0 * i["bw"]) <= px / 2 + 1e-6 for i in infos), f"{[(i['cl'], cover_x0 * i['bw']) for i in infos][:2]}")
        check(f"crisp.pieces_have_engine_snapping_on_and_bias_0.eff_{eff:.4f}_scale_{scale}",
              all(all(v is True for v in i["snaps"].values()) and all(v == 0 for v in i["biases"].values()) for i in infos), f"{infos[0]['snaps']} {infos[0]['biases']}")
        # and the art still meets the ring when the glyph's edges are rounded to those pixels: drawn at that many screen pixels
        # per UI unit, no pixel inside the ring falls outside the glyph's window
        missed = {n: _key_wedge_misses(i, 1 / px) for n, i in enumerate(infos) if i["kind"] == "runtime"}
        check(f"crisp.the_art_meets_the_ring_on_whole_physical_pixels.factor_{factor:.3f}_eff_{eff:.4f}_scale_{scale}",
              len(missed) == 12 and not any(missed.values()), f"px {px:.4f} {missed}")
        # top and bottom edges: the key height lands on whole physical pixels too, both pieces alike
        heights = [(i["bh"] + i["vert"][p][2] - i["vert"][p][1]) for i in infos for p in ("g", "c")]
        check(f"crisp.the_key_height_is_a_whole_number_of_physical_pixels.factor_{factor:.3f}_eff_{eff:.4f}_scale_{scale}",
              all(abs(v / px - round(v / px)) < 1e-6 for v in heights) and all(abs(v - infos[0]["bh"]) <= px / 2 + 1e-6 for v in heights), f"px {px:.4f} {heights[:3]} bh {infos[0]['bh']}")
    # no PixelUtil: whole UI units, as before
    w = World(12, scale=0.64).login()
    infos = [dict(v.items()) for _, v in w.call("h_glyphInfo").items()]
    check("crisp.without_pixel_numbers_edges_are_whole_ui_units", all(i["left"] == int(i["left"]) and i["cl"] == int(i["cl"]) for i in infos))


def check_window_follows_the_rect() -> None:
    """When the layout shrinks the keys (more keys than the slot holds) the rectangle gets narrower but keeps its height, so a
    window with the nominal aspect would be squeezed sideways. The window is refitted to the rendered rectangle (after the
    edges are snapped to pixels): its texel aspect equals the rectangle's within 2% or one physical pixel, at 12, 14 and 16
    keys, at the live scale and at 1.0, for every game texture including the class icon; and it stays inside the glyph's own
    limit."""
    cases = ((768 / 1440, 0.64, 0.64), (768 / 1440, 1.0, 1.0))
    bad, seen, widths = {}, 0, set()
    for count in (12, 14, 16):
        for factor, eff, scale in cases:
            w = World(count, scale=scale, pixel_factor=factor, effective_scale=eff).login()
            px = factor / eff
            keys = list(w.get("FS.MicroBars.keys").values())
            for n, (k, i) in enumerate(zip(keys, (dict(v.items()) for _, v in w.call("h_glyphInfo").items()))):
                if i["kind"] != "runtime":
                    continue
                seen += 1
                rw = i["bw"] - i["left"] - i["right"]
                rh = i["bh"] + i["vert"]["g"][2] - i["vert"]["g"][1]
                c = [float(i["c"][m]) for m in (1, 2, 3, 4)]
                size, limit = k.spec.size, k.spec.limit
                tw, th = (c[1] - c[0]) * size[1], (c[3] - c[2]) * size[2]
                widths.add(round(rw / rh, 2))
                inside = limit is not None and all(float(limit[1]) - 1e-4 <= c[0] and c[1] <= float(limit[2]) + 1e-4
                                                    and float(limit[3]) - 1e-4 <= c[2] and c[3] <= float(limit[4]) + 1e-4 for _ in (0,))
                ok = (abs(tw / th - rw / rh) <= 0.02 * rw / rh or abs(tw / th * rh - rw) <= px) and inside and th > 0
                boost = i.get("boostCoords")
                if boost is not None:
                    ok = ok and [float(boost[m]) for m in (1, 2, 3, 4)] == c
                if not ok:
                    bad[(count, scale, n)] = (round(tw / th, 3), round(rw / rh, 3))
    check("window.the_texel_aspect_follows_the_rendered_rectangle_when_the_keys_shrink", seen > 30 and not bad and len(widths) >= 3,
          f"{seen} keys, aspects {sorted(widths)}, bad {list(bad.items())[:3]}")


def check_fit_window() -> None:
    """FitWindow, the pure part: the data's window at its own aspect; a narrower rectangle narrows the window at the same height
    and centre; one too wide for the glyph's own part of the texture shrinks the height instead; no aspect, no change."""
    w = World(12).login()
    fit = w.get("FS.MicroBars.FitWindow")
    spec = w.lua.eval("{ coords = { 0.25, 0.75, 0.4, 0.6 }, size = { 64, 64 }, limit = { 0.2, 0.8, 0.3, 0.7 } }")   # 32 x 12.8 texels
    got = lambda a: [float(v) for v in fit(spec, a)]  # noqa: E731
    nominal = [0.25, 0.75, 0.4, 0.6]
    check("fit.the_nominal_aspect_gives_the_data_window", all(near(a, b, 1e-6) for a, b in zip(got(2.5), nominal)), f"{got(2.5)}")
    narrow = got(2.0)
    check("fit.a_narrower_rectangle_narrows_the_window_at_the_same_height_and_centre",
          near(narrow[3] - narrow[2], 0.2, 1e-6) and near((narrow[1] - narrow[0]) * 64 / ((narrow[3] - narrow[2]) * 64), 2.0, 1e-6)
          and near(narrow[0] + narrow[1], 1.0, 1e-6) and near(narrow[2] + narrow[3], 1.0, 1e-6), f"{narrow}")
    wide = got(5.0)
    check("fit.a_width_the_limit_cannot_hold_shrinks_the_height_and_stays_inside",
          near((wide[1] - wide[0]) * 64 / ((wide[3] - wide[2]) * 64), 5.0, 1e-6) and wide[0] >= 0.2 - 1e-6 and wide[1] <= 0.8 + 1e-6
          and wide[2] >= 0.3 - 1e-6 and wide[3] <= 0.7 + 1e-6 and wide[3] - wide[2] < 0.2, f"{wide}")
    edge = w.lua.eval("{ coords = { 0.2, 0.3, 0.4, 0.6 }, size = { 64, 64 }, limit = { 0.2, 0.8, 0.3, 0.7 } }")   # 6.4 x 12.8 texels at the edge
    pushed = [float(v) for v in fit(edge, 2.5)]
    check("fit.a_window_that_grows_past_the_limits_edge_is_pushed_back_inside_it", near(pushed[0], 0.2, 1e-6) and near(pushed[1], 0.7, 1e-6), f"{pushed}")
    check("fit.no_aspect_or_a_bad_one_changes_nothing",
          all([float(v) for v in fit(spec, a)] == nominal for a in (None, 0, -1, float("nan"), float("inf"))))


# The icon data as v5 (5dac1c0, the look Parker approved) wrote it, minus the zoom-out: every entry's own line of
# Core/IconStyleData.lua. A zoom-out may add `zoom = z` to the keys listed in ZOOMED and nothing else; every other entry, and the
# rest of a zoomed one, is this text exactly.
CLASSIC_V5 = 'coords = { 0.1562, 0.8438, 0.54, 0.8193 }, size = { 32, 64 }, limit = { 0.1562, 0.8438, 0.4531, 0.9062 }'
V5_ENTRIES = {
    "micro.spellbook": f'file = 130810, {CLASSIC_V5}, fam = "house_violet", boost = 0.36',
    "micro.talents": f'file = 130813, {CLASSIC_V5}, fam = "house_pink", boost = 0.34',
    "micro.achievement": f'file = 235422, {CLASSIC_V5}, fam = "house_violet", boost = 0',
    "micro.questlog": f'file = 130804, {CLASSIC_V5}, fam = "house_pink", boost = 0.01',
    "micro.socials": f'file = 130807, {CLASSIC_V5}, fam = "house_violet", boost = 0',
    "micro.lfd": f'file = 130798, {CLASSIC_V5}, fam = "house_pink", boost = 0.49',
    "micro.mainmenu": f'file = 130801, {CLASSIC_V5}, fam = "house_cyan", boost = 0.18',
    "micro.help": f'file = 130794, {CLASSIC_V5}, fam = "house_pink", boost = 1',
    "micro.worldmap": f'file = 130816, {CLASSIC_V5}, fam = "house_cyan", boost = 0.52',
    "micro.ej": f'file = 525019, {CLASSIC_V5}, fam = "house_pink", boost = 0.75',
    "micro.collections": f'file = 615164, {CLASSIC_V5}, fam = "house_violet", boost = 0.18',
    "micro.store": f'file = 902317, {CLASSIC_V5}, fam = "house_violet", boost = 0.19',
    "micro.professions": 'file = 4708813, coords = { 0.3908, 0.4481, 0.6966, 0.7897 }, size = { 1024, 512 }, limit = { 0.3877, 0.4502, 0.6582, 0.8184 }, fam = "house_cyan", boost = 0.42',
    "micro.guild": 'file = 4708813, coords = { 0.2588, 0.3213, 0.8535, 0.9551 }, size = { 1024, 512 }, limit = { 0.2588, 0.3213, 0.8223, 0.9824 }, fam = "house_cyan", boost = 0.25',
    "micro.housing": 'file = 4708813, coords = { 0.3232, 0.3857, 0.6885, 0.79 }, size = { 1024, 512 }, limit = { 0.3232, 0.3857, 0.6582, 0.8184 }, fam = "house_violet", boost = 0.07',
    "pvp.Alliance": 'file = 136998, coords = { 0, 0.7339, 0.03, 0.6262 }, size = { 64, 64 }, limit = { 0, 1, 0, 1 }, fam = "house_cyan", boost = 0.24',
    "pvp.Horde": 'file = 137000, coords = { 0, 0.7339, 0.0144, 0.6106 }, size = { 64, 64 }, limit = { 0, 1, 0, 1 }, fam = "house_cyan", boost = 1',
    "pvp.other": 'file = 136999, coords = { 0, 0.795, 0, 0.6459 }, size = { 64, 64 }, limit = { 0, 1, 0, 1 }, fam = "house_cyan", boost = 0.69',
}
CLASS_V5_BOOST = {"WARRIOR": "0.03", "PALADIN": "0.04", "HUNTER": "0.83", "ROGUE": "0.02", "PRIEST": "0.07", "SHAMAN": "0.27",
                  "MAGE": "0", "WARLOCK": "0.12", "DRUID": "0.34"}
for _tok, _boost in CLASS_V5_BOOST.items():
    V5_ENTRIES[f"class.{_tok}"] = ('file = "Interface\\\\Icons\\\\ClassIcon_' + CLASS_NAMES[_tok] + '", coords = { 0.07, 0.93, 0.1506, 0.8494 }, '
                                   'size = { 64, 64 }, limit = { 0.07, 0.93, 0.07, 0.93 }, fam = "house_cyan", boost = ' + _boost)
# The micro keys whose close-up crop reads as a blob (positions 2, 4, 5, 7, 10 and 12 of the v5 row), by the name the data holds.
ZOOMED = {"micro.spellbook", "micro.achievement", "micro.questlog", "micro.lfd", "micro.worldmap", "micro.collections"}


def data_lines() -> dict[str, str]:
    """Each entry of Core/IconStyleData.lua (micro, pvp, class) as its text between the braces."""
    out, section = {}, None
    for line in (ADDON / "Core" / "IconStyleData.lua").read_text(encoding="utf-8").splitlines():
        m = re.match(r"  (micro|pvp|class) = \{$", line)
        if m:
            section = m.group(1)
            continue
        if line == "  },":
            section = None
        m = re.match(r"    (\w+) = \{ (.*) \},$", line)
        if section and m:
            out[f"{section}.{m.group(1)}"] = m.group(2)
    return out


def check_zoom_data() -> None:
    """The zoom-out touches only the keys it was asked for. Every other entry of the icon data is v5's text, and a zoomed entry
    is v5's text plus one `zoom` value in (0, 1] (0 is v5's close-up, 1 is the whole glyph): so the other keys, and every key's
    texture, window, limit, family and boost, are pixel identical to what Parker approved."""
    got = data_lines()
    check("zoom.the_data_has_exactly_the_v5_entries", set(got) == set(V5_ENTRIES), f"{sorted(set(got) ^ set(V5_ENTRIES))}")
    bad, zoomed = [], set()
    for name, text in got.items():
        m = re.search(r", zoom = ([0-9.]+)$", text)
        base = text[:m.start()] if m else text
        if m:
            zoomed.add(name)
            if not 0 < float(m.group(1)) <= 1:
                bad.append((name, "zoom out of (0, 1]"))
        if base != V5_ENTRIES.get(name):
            bad.append((name, base))
    check("zoom.every_entry_is_v5s_text_apart_from_the_zoom_value", not bad, f"{bad[:2]}")
    check("zoom.exactly_the_asked_for_keys_carry_a_zoom", zoomed == ZOOMED, f"{sorted(zoomed ^ ZOOMED)}")
    # and the spec a key is built from carries the data's zoom, nothing more: a key with none must not get one on the way
    w = World(12).login()
    mb, data = w.get("FS.MicroBars"), w.get("FS.IconStyleData")
    via = {}
    for name in data.micro.keys():
        via[f"micro.{name}"] = (mb.GlyphSpec(name, None, None).zoom, data.micro[name].zoom)
    for faction in data.pvp.keys():
        via[f"pvp.{faction}"] = (mb.GlyphSpec("pvp", faction if faction != "other" else "Neutral", None).zoom, data.pvp[faction].zoom)
    for token in data["class"].keys():
        via[f"class.{token}"] = (mb.GlyphSpec("character", None, token).zoom, data["class"][token].zoom)
    check("zoom.the_spec_of_every_glyph_carries_exactly_the_datas_zoom", len(via) == 27 and all(a == b for a, b in via.values()),
          f"{[(k, v) for k, v in via.items() if v[0] != v[1]][:3]}")


def check_glyph_view() -> None:
    """GlyphView, the pure part: no zoom (or a bad one) is FitWindow's window filling the rectangle; a zoom grows the window's
    height from the fill window's toward the glyph's whole part of the texture (`limit`) at the same width and centre, and
    answers the aspect the picture is then drawn at (its own), so the picture is shown whole instead of cropped, never stretched."""
    w = World(12).login()
    view = w.get("FS.MicroBars.GlyphView")
    fit = w.get("FS.MicroBars.FitWindow")

    def spec(zoom="nil"):   # 32 x 12.8 texels in a limit of 38.4 x 25.6
        return w.lua.eval("{ coords = { 0.25, 0.75, 0.4, 0.6 }, size = { 64, 64 }, limit = { 0.2, 0.8, 0.3, 0.7 }, zoom = " + str(zoom) + " }")
    got = lambda sp, a, d=None: [None if v is None else float(v) for v in view(sp, a, d)]  # noqa: E731
    plain = got(spec(), 2.5)
    check("view.without_a_zoom_it_is_the_fit_window_filling_the_rectangle",
          plain[:4] == [float(v) for v in fit(spec(), 2.5)] and plain[4] is None, f"{plain}")
    check("view.a_zero_or_bad_zoom_is_no_zoom", all(got(spec(z), 2.5) == plain for z in (0, -0.5, "0/0", "'x'", "{}")),
          f"{[got(spec(z), 2.5) for z in (0, -0.5)]}")
    half = got(spec(0.5), 2.5)
    th = (half[3] - half[2]) * 64
    tw = (half[1] - half[0]) * 64
    check("view.a_zoom_grows_the_height_part_of_the_way_to_the_whole_limit_at_the_same_width_and_centre",
          near(th, 12.8 + 0.5 * (25.6 - 12.8), 1e-4) and near(tw, 32, 1e-4) and near(half[0] + half[1], 1.0, 1e-6) and near(half[2] + half[3], 1.0, 1e-6),
          f"{half} {tw}x{th}")
    check("view.the_drawn_aspect_is_the_windows_own_so_nothing_is_stretched", near(half[4], tw / th, 1e-4) and half[4] < 2.5, f"{half[4]} {tw / th}")
    full = got(spec(1), 2.5)
    check("view.a_zoom_of_1_shows_the_whole_height_of_the_limit",
          near(full[2], 0.3, 1e-6) and near(full[3], 0.7, 1e-6) and near(full[4], 32 / 25.6, 1e-4), f"{full}")
    check("view.a_zoom_past_1_is_1", got(spec(7), 2.5) == full, f"{got(spec(7), 2.5)}")
    snapped = got(spec(0.5), 2.5, 1.5)
    check("view.a_drawn_aspect_given_by_the_caller_sets_the_windows_width_at_that_height",
          near((snapped[1] - snapped[0]) / (snapped[3] - snapped[2]), 1.5, 1e-4) and near(snapped[3] - snapped[2], half[3] - half[2], 1e-6) and near(snapped[4], half[4], 1e-6),
          f"{snapped}")
    edge = w.lua.eval("{ coords = { 0.2, 0.8, 0.3, 0.45 }, size = { 64, 64 }, limit = { 0.2, 0.8, 0.3, 0.7 }, zoom = 1 }")
    pushed = got(edge, 4.0)
    check("view.a_window_at_the_limits_edge_stays_inside_it_when_it_grows",
          near(pushed[2], 0.3, 1e-6) and near(pushed[3], 0.7, 1e-6) and pushed[0] >= 0.2 - 1e-6 and pushed[1] <= 0.8 + 1e-6, f"{pushed}")
    check("view.no_aspect_or_a_bad_one_changes_nothing",
          all(got(spec(0.5), a)[:4] == [0.25, 0.75, 0.4, 0.6] and got(spec(0.5), a)[4] is None for a in (None, 0, -1, float("nan"), float("inf"))))


def check_zoomed_key() -> None:
    """A zoomed key draws the glyph's window zoomed out and the rectangle it fills narrower, centred in the key's inside (the plate
    shows at the two sides): the window has the rectangle's aspect (nothing stretched), on whole physical pixels, with the cover
    still over the whole inside and the ARTWORK stack unchanged. Keys with no zoom are untouched. At every key count."""
    bad, seen = {}, 0
    for count in (12, 14, 16):
        for factor, eff, scale in ((768 / 1440, 0.64, 0.64), (768 / 1440, 1.0, 1.0), (768 / 1440, 768 / 1440, 0.64)):
            w = World(count, scale=scale, pixel_factor=factor, effective_scale=eff, help_zoom=0.5).login()
            px = factor / eff
            keys = list(w.get("FS.MicroBars.keys").values())
            infos = [dict(v.items()) for _, v in w.call("h_glyphInfo").items()]
            for n, (k, i) in enumerate(zip(keys, infos)):
                if i["kind"] != "runtime":
                    continue
                rw = i["bw"] - i["left"] - i["right"]
                rh = i["bh"] + i["vert"]["g"][2] - i["vert"]["g"][1]
                cw = i["bw"] - i["cr"] - i["cl"]
                c = [float(i["c"][m]) for m in (1, 2, 3, 4)]
                size, limit = k.spec.size, k.spec.limit
                tw, th = (c[1] - c[0]) * size[1], (c[3] - c[2]) * size[2]
                if k.spec.zoom is None:
                    ok = abs(i["left"] - i["cl"]) < 1e-6 and abs(i["right"] - i["cr"]) < 1e-6
                else:
                    seen += 1
                    fill_h = (float(k.spec.coords[4]) - float(k.spec.coords[3])) * size[2]
                    ok = (cw - rw > 2 * px                                                            # narrower than the cover's inside
                          and abs((i["left"] - i["cl"]) - (i["right"] - i["cr"])) <= px + 1e-6          # centred within a pixel
                          and abs(tw / th * rh - rw) <= 1e-3                                          # the window is the SNAPPED rectangle's aspect
                          and th > fill_h + 1                                                         # the window shows more rows than v5's
                          and all(abs(v / px - round(v / px)) < 1e-6 for v in (i["left"], i["right"]))
                          and float(limit[3]) - 1e-4 <= c[2] and c[3] <= float(limit[4]) + 1e-4
                          and i["cl"] <= i["left"] and i["cr"] <= i["right"]
                          and i["boostAnchor"] and i["modAnchor"] and i["liftAnchor"])
                    boost = i.get("boostCoords")
                    ok = ok and boost is not None and [float(boost[m]) for m in (1, 2, 3, 4)] == c
                if not ok:
                    bad[(count, scale, eff, n)] = (rw, cw, i["left"], i["right"], round(tw / th, 3))
    check("zoomed.the_rectangle_is_narrower_and_centred_and_shows_the_window_at_its_own_aspect_at_every_key_count", seen > 60 and not bad,
          f"{seen} zoomed keys, bad {list(bad.items())[:3]}")
    # a zoom of 1 shows the whole of the glyph's part of the texture, but for the hair a whole pixel rectangle takes off one axis
    w = World(12, help_zoom=1).login()
    k = list(w.get("FS.MicroBars.keys").values())[2]
    i = dict(w.call("h_glyphInfo")[3].items())
    c = [float(i["c"][m]) for m in (1, 2, 3, 4)]
    lim = [float(k.spec.limit[m]) for m in (1, 2, 3, 4)]
    check("zoomed.at_1_the_window_is_the_whole_limit_of_the_texture_within_a_pixel_of_the_rectangle",
          lim[0] - 1e-4 <= c[0] and c[1] <= lim[1] + 1e-4 and lim[2] - 1e-4 <= c[2] and c[3] <= lim[3] + 1e-4
          and (c[1] - c[0]) >= 0.97 * (lim[1] - lim[0]) and (c[3] - c[2]) >= 0.97 * (lim[3] - lim[2]), f"{c} vs {lim}")


def check_late_class() -> None:
    """UnitClass answering nothing at build (the client is still loading the player): the Character key wears the person glyph,
    and at PLAYER_ENTERING_WORLD, out of combat, it is dressed with the class icon; PvP follows a faction learned late."""
    w = World(12, cls=None, faction=None, style="gradient").login()
    first = dict(w.call("h_glyphInfo")[1].items())
    check("late.the_character_key_starts_on_the_person_glyph", first["kind"] == "baked" and str(first["tex"]).endswith("glyphart_character.tga"), f"{first['tex']}")
    w.g.CLASS_TOKEN = "PRIEST"
    w.g.IN_COMBAT = True
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    held = dict(w.call("h_glyphInfo")[1].items())
    check("late.nothing_changes_in_combat", held["kind"] == "baked", f"{held['kind']}")
    w.g.IN_COMBAT = False
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    got = dict(w.call("h_glyphInfo")[1].items())
    check("late.the_class_icon_arrives_out_of_combat", got["kind"] == "runtime" and str(got["tex"]).endswith("ClassIcon_Priest"), f"{got['kind']} {got['tex']}")
    check("late.the_late_key_has_its_chain_and_is_sized_and_painted", got["modShown"] and got["cl"] > 0 and got["left"] > 0 and got["desat"] is True and got["coverShown"], f"{got.get('modShown')} {got.get('cl')}")
    # and back again when the answer goes (a different class: the key follows it)
    w.g.CLASS_TOKEN = "WARRIOR"
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    again = dict(w.call("h_glyphInfo")[1].items())
    check("late.a_changed_class_changes_the_icon", str(again["tex"]).endswith("ClassIcon_Warrior"), f"{again['tex']}")
    w.g.CLASS_TOKEN = None
    w.g.h_fire("PLAYER_ENTERING_WORLD")
    gone = dict(w.call("h_glyphInfo")[1].items())
    check("late.an_unknown_class_goes_back_to_the_person_glyph_and_releases_the_chain", gone["kind"] == "baked" and not gone.get("modShown"), f"{gone['kind']} {gone.get('modShown')}")
    check("late.no_degrade_logs", w.logs() == "", w.logs())


def check_glyph_tint() -> None:
    """The glyph is full colour: idle is a touch calm, hover, active and pressed are the glyph as styled, disabled is desaturated and dim."""
    w = World(12, style="gradient").login()
    mb = w.get("FS.MicroBars")
    tint = {}
    for name, flags in (("idle", {}), ("hover", {"hover": True}), ("active", {"active": True}), ("pressed", {"pressed": True}), ("disabled", {"disabled": True})):
        v = mb.ComputeVisual(w.lua.table_from(flags), w.lua.table_from([1, 1, 1]), None)
        tint[name] = (tuple(v.glyph[i] for i in (1, 2, 3)), v.glyphA, bool(v.glyphDesat))
    idle, hot = tint["idle"], (((1, 1, 1)), 1, False)
    check("tint.idle_is_a_touch_calm_not_dark", all(0.88 <= c < 1 for c in idle[0]) and idle[1] == 1 and not idle[2], f"{idle}")
    check("tint.hover_active_pressed_are_the_glyph_as_styled", all(tint[k] == hot for k in ("hover", "active", "pressed")), f"{tint}")
    off = tint["disabled"]
    check("tint.disabled_is_desaturated_and_dim_not_a_dark_multiply", off[2] and off[1] < 1 and all(c >= 0.7 for c in off[0]), f"{off}")

    def painted(i: int) -> dict:
        info = dict(w.call("h_glyphInfo")[i].items())
        boost = float(w.get("FS.MicroBars.keys")[i].spec.boost)
        return {"base": [info["vertex"][k] for k in (1, 2, 3, 4)], "baseDesat": bool(info["desat"]),
                "boost": [info["boostVertex"][k] for k in (1, 2, 3, 4)], "rampGrey": bool(info["modDesat"]),
                "lift": info["liftVertex"][4], "boostK": boost, "modShown": info["modShown"]}

    base, base2 = painted(1), painted(2)
    check("tint.a_key_paints_idle_at_login", near(base["base"][3], 1) and all(0.88 <= c < 1 for c in base["base"][:3]) and not base["rampGrey"], f"{base}")
    check("tint.the_glyph_is_always_drawn_grey_under_its_ramp", base["baseDesat"] is True, f"{base}")
    check("tint.the_boost_copy_wears_the_same_tint_scaled_by_its_boost",
          all(near(base["boost"][k], base["base"][k] * base["boostK"]) for k in range(3)) and near(base["boost"][3], base["base"][3]), f"{base}")
    w.call("h_script", 1, "OnEnter")
    hov = painted(1)
    check("tint.a_hovered_key_paints_full_colour", hov["base"] == [1, 1, 1, 1] and not hov["rampGrey"] and near(hov["lift"], 1), f"{hov}")
    w.call("h_script", 1, "OnLeave")
    check("tint.leaving_returns_to_idle", painted(1) == base, f"{painted(1)} vs {base}")
    w.call("h_enabled", 2, False)
    dis = painted(2)
    check("tint.a_disabled_key_is_grey_and_dim_with_no_ramp_like_a_dimmed_spell_tile",
          dis["modShown"] is False and dis["base"][3] < 1 and dis["baseDesat"] and dis["boost"][3] < 1 and dis["lift"] < 1, f"{dis}")
    check("tint.a_hovered_or_idle_key_keeps_its_ramp", base["modShown"] is True and hov["modShown"] is True, f"{base['modShown']} {hov['modShown']}")
    w.call("h_enabled", 2, True)
    check("tint.re_enabling_restores_colour", painted(2) == base2 and painted(1) == base, f"{painted(2)}")
    # a baked key (no class): the plain baked art is tinted and desaturated as before
    wb = World(12, cls=None).login()
    info = dict(wb.call("h_glyphInfo")[1].items())
    check("tint.a_baked_key_paints_idle_and_not_desaturated", not info["desat"] and near(info["vertex"][4], 1), f"{info['vertex']} {info['desat']}")
    wb.call("h_enabled", 1, False)
    info = dict(wb.call("h_glyphInfo")[1].items())
    check("tint.a_disabled_baked_key_is_desaturated", info["desat"] is True and info["vertex"][4] < 1)
    check("tint.no_degrade_logs", w.logs() == "" and wb.logs() == "", w.logs())


def check_art() -> None:
    w = World(12).login()
    zero = lambda a: all(a[k] in (0, "none") for k in ("normal", "pushed", "disabled", "highlight", "portrait"))  # noqa: E731
    arts = [w.art(i) for i in range(1, 13)]
    check("art.textures_start_at_alpha_0", all(zero(a) for a in arts), f"{[a for a in arts if not zero(a)][:1]}")
    check("art.character_portrait_is_faded", arts[0]["portrait"] == 0, f"{arts[0]['portrait']}")
    check("art.existing_fade_fields_kept", all(a["background"] == 0 and a["notify"] == 0 for a in arts))
    check("art.flash_regions_left_to_UIFrameFlash", all(a["flash"] == 1 and a["flashPinned"] for a in arts), f"{arts[0]}")
    check("art.flash_regions_hidden_by_vertex_alpha", all(a["flashVertexA"] == 0 for a in arts), f"{arts[0]}")
    pulses = [dict(w.call("h_flashPulse", i).items()) for i in (1, 3)]
    check("art.flash_stays_invisible_when_UIFrameFlash_writes_alpha",
          all(v == 0 for p in pulses for v in p.values()) and "FlashBorder" in pulses[0] and "Flash" in pulses[1], f"{pulses}")

    w.call("h_blizzOnLeave", 1)
    w.call("h_blizzSetPushed", 1)
    a = w.art(1)
    check("art.blizzard_alpha_writes_are_re_zeroed", a["normal"] == 0 and a["highlight"] == 0, f"{a}")
    w.call("h_blizzReatlas", 2)
    check("art.reatlas_leaves_alpha_0", zero(w.art(2)), f"{w.art(2)}")

    # The SetAlpha post-hook's re-entry guard is per region: without any guard a write loops forever,
    # and with one shared flag a region written from inside another's write is skipped and stays visible.
    storm = dict(w.call("h_alphaStorm", 4).items())
    check("art.alpha_write_does_not_recurse", storm["writes"] <= 3 and storm["alpha"] == 0, f"{storm}")
    nested = dict(w.call("h_nestedAlpha", 5).items())
    check("art.nested_alpha_write_on_another_region_still_ends_at_0",
          nested["a"] == 0 and nested["b"] == 0 and nested["writes"] <= 4, f"{nested}")

    # The Help button had only a normal region at build time; Blizzard makes the rest later.
    before = w.art(3)
    w.call("h_blizzReatlas", 3)
    late = w.art(3)
    check("art.regions_created_later_come_out_at_alpha_0", before["pushed"] == "none" and zero(late), f"{before} -> {late}")

    ks = w.keys()
    check("art.button_alpha_never_written", all(k["alphaWrites"] == 0 for k in ks), f"{[k['alphaWrites'] for k in ks]}")
    check("art.button_scripts_never_set", all(k["setScriptCalls"] == 0 for k in ks))
    check("art.no_degrade_logs", w.logs() == "", w.logs())


def check_hit_rects(lean: float, gap: float) -> None:
    w = World(12).login()
    ks = seated(w)
    keys_w = w.call("h_deckConst")["keyW"]
    want = (keys_w * lean - gap) / 2          # half of (lean - gap): see the arithmetic in MicroBars.lua
    check("hit.insets_set_on_every_button", all(k["hitL"] is not None for k in ks), f"{ks[0]}")
    if all(k["hitL"] is not None for k in ks):
        check("hit.inset_is_half_lean_minus_gap", all(near(k["hitL"], want) and near(k["hitR"], want) for k in ks),
              f"{ks[0]['hitL']} want {want:.3f}")
        check("hit.vertical_insets_zero", all((k["hitT"] or 0) == 0 and (k["hitB"] or 0) == 0 for k in ks))
        meets = [(ks[i + 1]["x"] - ks[i + 1]["w"] / 2 + ks[i + 1]["hitL"]) - (ks[i]["x"] + ks[i]["w"] / 2 - ks[i]["hitR"])
                 for i in range(len(ks) - 1)]
        check("hit.adjacent_rects_tile_without_overlap", all(abs(m) <= EPS for m in meets), f"{meets[:3]}")

    # Combat: nothing is reseated or inset; the reseat after combat uses the new scale.
    w.g.IN_COMBAT = True
    snap = w.keys()
    w.call("h_rescale", 0.64)
    w.call("h_fire", "PLAYER_ENTERING_WORLD")
    check("hit.nothing_reseated_in_combat", w.keys() == snap)
    w.g.IN_COMBAT = False
    w.call("h_fire", "PLAYER_REGEN_ENABLED")
    after = seated(w)
    want_inset = want * 0.64
    check("hit.reseat_after_combat_uses_new_scale",
          all(near(k["w"], keys_w * 0.64) and near(k["hitL"] or -1, want_inset) for k in after),
          f"{after[0]}")


def py(v):
    """A Lua table (or scalar) as plain Python."""
    if hasattr(v, "items"):
        d = {k: py(x) for k, x in v.items()}
        if d and all(isinstance(k, int) for k in d):
            return [d[k] for k in sorted(d)]
        return d
    return v


def consts(w: World | None = None) -> dict:
    """Deck.lua's exported numbers; a missing one reads -1 so the check fails instead of the run."""
    c = py((w or World(1)).call("h_deckConst"))
    return {"lean": -1, "gap": -1, "keyW": -1, "pad": -1, "divider": -1, "bagW": -1, "microMax": -1, "getMicro": -1, "hasSet": False, **c}


def deck_state(w: World) -> dict:
    return py(w.call("h_slots"))


def check_deck(lean: float, gap: float) -> None:
    c = consts()
    check("deck.exports_the_resize_api", c["hasSet"] and c["getMicro"] > 0, f"{c}")
    natural12 = c["keyW"] + 11 * (c["keyW"] * (1 - lean) + gap)
    check("deck.micro_max_is_the_12_key_row_rounded_up", c["microMax"] == math.ceil(natural12 - 1e-4) and 0 <= c["microMax"] - natural12 < 1,
          f"max {c['microMax']} natural {natural12:.3f}")
    max_w = 2 * c["pad"] + c["microMax"] + c["divider"] + c["bagW"]
    check("deck.layout_w_is_the_max_of_the_parts_sum", layout_deck_w() == max_w, f"Layout.lua says {layout_deck_w()}, parts sum {max_w}")

    w = World(12, 1.0, layout_cfg=False).login()
    check("deck.layout_cfg_absent_still_builds_the_same_chassis", deck_state(w)["cw"] <= max_w and not w.logs(), f"{deck_state(w)['cw']} {w.logs()}")
    check("deck.chassis_never_exceeds_the_max_with_12_keys", deck_state(w)["cw"] <= max_w + EPS, f"{deck_state(w)['cw']} vs {max_w}")
    w16 = World(16, 1.0).login()
    check("deck.more_than_12_keys_clamp_to_the_max_width", near(deck_state(w16)["cw"], max_w) and near(deck_state(w16)["mw"], c["microMax"]),
          f"{deck_state(w16)}")
    exports = py(w.call("h_microExports"))
    check("deck.microbars_exports_layout_helpers", all(exports.values()), f"{exports}")
    if exports["rowWidth"]:
        check("deck.microbars_row_width_matches", near(w.call("h_rowWidth", 12), natural12), f"{w.call('h_rowWidth', 12)}")


def check_shape() -> None:
    """The chassis is a plain two-corner cut rectangle in the data bar's border look, built like PetFrame's panel."""
    r, g_, b, _ = theme_color_power()
    alpha, _height = databar_rail()
    cyan = [r, g_, b, alpha]
    scrim = list(theme_color_scrim())

    # Scale independent (the scale permutations live in fit.* and layout.*), so one scale is enough.
    w = World(12, 1.0, layout_cfg=False).login()
    blank = {"tex": None, "layer": None, "color": None, "vertex": None, "blend": None, "slice": None, "pts": [], "onChassis": False, "gradient": False}
    tex = [{**blank, **t} for t in py(w.call("h_chassisTextures"))]
    fill = [t for t in tex if t["tex"] == "cut2_fill"]
    outline = [t for t in tex if t["tex"] == "cut2_outline"]
    check("shape.one_cut2_fill", len(fill) == 1, f"{len(fill)}")
    check("shape.one_cut2_outline", len(outline) == 1, f"{len(outline)}")
    if len(fill) == 1:
        t = fill[0]
        check("shape.fill_is_tinted_COLOR_HUD_SCRIM",
              t["vertex"] is not None and len(t["vertex"]) == 4 and all(near(a, e, 1e-6) for a, e in zip(t["vertex"], scrim)), f"{t['vertex']} vs {scrim}")
        check("shape.fill_is_behind_everything_else", t["layer"] == "BACKGROUND" and not t["gradient"], f"{t['layer']}")
        check("shape.fill_covers_the_chassis", t["onChassis"] and len(t["pts"]) == 2
              and {p["point"] for p in t["pts"]} == {"TOPLEFT", "BOTTOMRIGHT"} and all(p["x"] == 0 and p["y"] == 0 for p in t["pts"]), f"{t['pts']}")
        check("shape.fill_is_nine_sliced_at_the_chamfer", t["slice"] == 6, f"{t['slice']}")
    if len(outline) == 1:
        t = outline[0]
        check("shape.outline_is_COLOR_POWER_at_the_databar_alpha",
              t["vertex"] is not None and len(t["vertex"]) == 4 and all(near(a, e, 1e-6) for a, e in zip(t["vertex"], cyan)), f"{t['vertex']} vs {cyan}")
        check("shape.outline_is_flat_not_gradient_not_additive", not t["gradient"] and t["blend"] != "ADD" and t["color"] is None)
        check("shape.outline_is_on_the_border_layer", t["layer"] == "BORDER", f"{t['layer']}")
        check("shape.outline_covers_the_chassis", t["onChassis"] and len(t["pts"]) == 2
              and {p["point"] for p in t["pts"]} == {"TOPLEFT", "BOTTOMRIGHT"} and all(p["x"] == 0 and p["y"] == 0 for p in t["pts"]), f"{t['pts']}")
        check("shape.outline_is_nine_sliced_at_the_chamfer", t["slice"] == 6, f"{t['slice']}")

    banned = ("shoulder", "grid", "sun", "glint", "glow", "scan", "tab_slant", "rivet")
    check("shape.no_shoulder_grid_sun_glow_or_scanline_texture",
          not any(any(k in str(t["tex"] or "") for k in banned) for t in tex), f"{[t['tex'] for t in tex]}")
    check("shape.nothing_is_additive", all(t["blend"] != "ADD" for t in tex), f"{[t['blend'] for t in tex]}")
    # The only other thing on the chassis is the // divider mark.
    others = [t for t in tex if t["tex"] not in ("cut2_fill", "cut2_outline")]
    check("shape.only_the_divider_besides_fill_and_outline",
          len(others) == 1 and "deck_divider" in str(others[0]["tex"]), f"{[t['tex'] for t in others]}")
    extra = py(w.call("h_chassisExtras"))
    check("shape.no_decoration_frames_animation_or_clip", extra["frames"] == 0 and extra["groups"] == 0 and extra["clips"] == 0, f"{extra}")
    check("shape.strata_and_levels_as_before", extra["strata"] == "HIGH" and extra["level"] == 20 and extra["slotLevel"] == 23, f"{extra}")
    check("shape.builds_clean", w.logs() == "", w.logs())


def check_fit() -> None:
    """The micro slot follows the shown key count; the keys fill it flush; the right edge never moves."""
    c = consts()
    base_right = None
    for scale in (1.0, 0.64):
        for hidden, label in (((), "12"), ((2, 5), "10"), ((2, 5, 9), "9")):
            tag = f"@{label}_keys_scale_{scale}"
            w = World(12, scale, hidden=hidden).login()
            shown = 12 - len(hidden)
            need = w.call("h_rowWidth", shown)
            st = deck_state(w)
            ks = seated(w)
            check("fit.micro_slot_is_RowWidth_of_the_shown_keys" + tag, near(st["mw"], need * scale), f"slot {st['mw']} want {need * scale:.3f}")
            check("fit.chassis_is_the_sum_of_its_parts" + tag,
                  near(st["cw"], (2 * c["pad"] + need + c["divider"] + c["bagW"]) * scale), f"{st['cw']}")
            left = ks[0]["x"] - ks[0]["w"] / 2
            right = ks[-1]["x"] + ks[-1]["w"] / 2
            check("fit.keys_fill_the_slot_flush_no_empty_run" + tag,
                  len(ks) == shown and near(left, -st["mw"] / 2) and near(right, st["mw"] / 2), f"left {left:.3f} right {right:.3f} slot {st['mw']:.3f}")
            steps = [ks[i + 1]["x"] - ks[i]["x"] for i in range(len(ks) - 1)]
            pitch = (c["keyW"] * (1 - 0.34) + c["gap"]) * scale
            check("fit.pitch_is_unchanged" + tag, all(near(s_, pitch) for s_ in steps), f"{steps[:2]} want {pitch:.3f}")
            # Right edge fixed: chassis anchor, bag slot seat and micro slot right edge do not depend on the count.
            cp, bp, mp = st["cp"], st["bp"], st["mp"]
            check("fit.chassis_anchor_is_the_xp_bar_top_right" + tag,
                  cp["point"] == "BOTTOMRIGHT" and cp["relPoint"] == "TOPRIGHT" and near(cp["x"], -92 * scale) and cp["n"] == 1, f"{cp}")
            check("fit.bag_slot_is_seated_from_the_right_edge" + tag,
                  bp["point"] == "RIGHT" and bp["relPoint"] == "RIGHT" and near(bp["x"], -c["pad"] * scale) and bp["n"] == 1, f"{bp}")
            check("fit.micro_slot_right_edge_is_beside_the_divider" + tag,
                  mp["point"] == "RIGHT" and mp["relPoint"] == "RIGHT"
                  and near(mp["x"], -(c["pad"] + c["bagW"] + c["divider"]) * scale) and mp["n"] == 1, f"{mp}")
            div = py(w.call("h_divider"))
            check("fit.divider_sits_between_the_slots" + tag,
                  div["found"] and div["p"]["relPoint"] == "RIGHT"
                  and near(div["p"]["x"], -(c["pad"] + c["bagW"] + c["divider"] / 2) * scale), f"{div}")
            check("fit.left_pad_is_the_pad" + tag,
                  near(st["cw"] - abs(mp["x"]) - st["mw"], c["pad"] * scale), f"{st['cw'] - abs(mp['x']) - st['mw']}")
            check("fit.no_degrade_logs" + tag, w.logs() == "", w.logs())
            if scale == 1.0:
                right_edge = (cp["x"], bp["x"], mp["x"])
                base_right = base_right or right_edge
                check("fit.right_edge_does_not_move_with_the_count" + tag, right_edge == base_right, f"{right_edge} vs {base_right}")

    # A key appearing or disappearing after login (Blizzard shows Help, Talent and Housing late) resizes the deck.
    w = World(12, 1.0, hidden=(2, 5, 9)).login()
    w.call("h_show", 5)
    w.call("h_runHooks", "OnShow")
    st = deck_state(w)
    check("fit.a_late_shown_key_widens_the_deck", near(st["mw"], w.call("h_rowWidth", 10)) and len(seated(w)) == 10, f"{st['mw']} {len(seated(w))}")
    w.call("h_hide", 5)
    w.call("h_hide", 6)
    w.call("h_runHooks", "OnHide")
    st = deck_state(w)
    check("fit.hiding_keys_narrows_it_again", near(st["mw"], w.call("h_rowWidth", 8)) and len(seated(w)) == 8, f"{st['mw']} {len(seated(w))}")

    # Hostile widths are ignored (a secret is still a number, so only IsSecret catches it), a width above the max
    # (a huge one, or infinity) is clamped.
    w = World(12, 1.0).login()
    before = deck_state(w)["mw"]
    threw = []
    for bad in (-5, float("nan"), "wide", w.get("SECRET_W")):
        try:
            w.call("h_setMicro", bad)
        except Exception:  # noqa: BLE001 - a throw from the API would be the failure
            threw.append(bad)
    check("fit.bad_width_does_not_throw", not threw, f"threw on {threw}")
    check("fit.bad_widths_are_ignored", near(deck_state(w)["mw"], before), f"{deck_state(w)['mw']} vs {before}")
    c = py(w.call("h_deckConst"))
    clamped = []
    for huge in (9999, float("inf")):
        w.call("h_setMicro", 100)
        w.call("h_setMicro", huge)
        clamped.append(deck_state(w)["mw"])
    check("fit.width_above_the_max_is_clamped", all(near(m, c["microMax"]) for m in clamped), f"{clamped} vs {c['microMax']}")

    # No shown key at all (login, before Blizzard shows its buttons): the deck keeps its width instead of collapsing.
    w = World(12, 1.0, hidden=tuple(range(1, 13))).login()
    check("fit.no_shown_key_leaves_the_deck_at_its_width", near(deck_state(w)["mw"], c["microMax"]) and not w.logs(), f"{deck_state(w)['mw']} {w.logs()}")


def check_combat_deck() -> None:
    """Keys are reseated out of combat only, and the deck width follows the keys: both agree after combat."""
    c = consts()
    w = World(12, 1.0).login()
    w.g.IN_COMBAT = True
    geom = lambda: [(k["x"], k["w"], k["hitL"]) for k in w.keys()]  # noqa: E731 - where the keys sit, not whether they are shown
    snap = geom()
    st0 = deck_state(w)
    w.call("h_hide", 2)
    w.call("h_hide", 5)
    w.call("h_runHooks", "OnHide")
    w.call("h_fire", "PLAYER_ENTERING_WORLD")
    check("combat.keys_and_deck_hold_still_while_the_shown_set_changes", geom() == snap and near(deck_state(w)["mw"], st0["mw"]) and near(deck_state(w)["cw"], st0["cw"]))
    w.call("h_rescale", 0.64)
    st = deck_state(w)
    # The bag slots are secure buttons (BagBar.lua), so the chassis is protected: a rescale in combat is deferred.
    check("combat.a_rescale_waits_for_regen_the_deck_holds", near(st["cw"], st0["cw"]) and near(st["mw"], st0["mw"]), f"{st['cw']} {st['mw']}")
    check("combat.keys_are_not_reseated_by_it", geom() == snap)
    w.g.IN_COMBAT = False
    w.call("h_fire", "PLAYER_REGEN_ENABLED")
    st = deck_state(w)
    ks = seated(w)
    need = w.call("h_rowWidth", 10)
    left = ks[0]["x"] - ks[0]["w"] / 2
    right = ks[-1]["x"] + ks[-1]["w"] / 2
    check("combat.after_combat_the_deck_width_matches_the_keys",
          len(ks) == 10 and near(st["mw"], need * 0.64) and near(left, -st["mw"] / 2) and near(right, st["mw"] / 2)
          and near(st["cw"], (2 * c["pad"] + need + c["divider"] + c["bagW"]) * 0.64), f"slot {st['mw']} keys {left:.3f}..{right:.3f} chassis {st['cw']}")
    check("combat.no_degrade_logs", w.logs() == "", w.logs())


def check_standalone() -> None:
    """Without FS.Deck the keys still seat in the bare container, which is sized to its keys."""
    for hidden in ((), (2, 5, 9)):
        w = World(12, 1.0, hidden=hidden, deck=False).login()
        st = py(w.call("h_standaloneFrame"))
        shown = 12 - len(hidden)
        ks = seated(w)
        check(f"standalone.container_is_sized_to_the_{shown}_keys",
              st["exists"] and not st["deck"] and near(st["w"], w.call("h_rowWidth", shown)) and len(ks) == shown, f"{st} {len(ks)}")
        left, right = ks[0]["x"] - ks[0]["w"] / 2, ks[-1]["x"] + ks[-1]["w"] / 2
        check(f"standalone.{shown}_keys_are_flush", near(left, -st["w"] / 2) and near(right, st["w"] / 2), f"{left} {right} {st['w']}")
        check(f"standalone.{shown}_keys_only_log_the_no_deck_degrade", w.logs().count("\n") == 0 and "no-deck" in w.logs(), w.logs())


def check_removed_art() -> None:
    """The trapezoid's textures are gone, and no addon source or .toc still points at them."""
    media = ADDON / "Media" / "Textures"
    gone = [f for f in ("deck_shoulder.tga", "deck_grid.tga", "deck_sun.tga", "generate_deck_shoulder.py") if (media / f).exists()]
    check("removed.shoulder_grid_sun_files_are_gone", not gone, f"{gone}")
    removed = ("deck_shoulder", "deck_grid", "deck_sun", "deck_glint")
    sources = {p.resolve() for pattern in ("*.lua", "*.toc") for p in ADDON.rglob(pattern)}
    sources.add(DECK_LUA.resolve())  # an overridden Deck.lua is scanned too
    refs = sorted(f"{p.name}:{name}" for p in sources for name in removed if name in p.read_text(encoding="utf-8", errors="replace"))
    check("removed.no_lua_or_toc_references_a_removed_texture", len(sources) > 20 and not refs, f"{len(sources)} files, refs {refs}")


def check_forbidden_store(lean: float, gap: float) -> None:
    """StoreMicroButton is a forbidden frame on the client: any method call from addon code throws."""
    keys_w = dict(World(1).g.h_deckConst().items())["keyW"]
    pitch = keys_w * (1 - lean) + gap

    w = World(12, 1.0, store="button").login()
    ks = seated(w)
    steps = [ks[i + 1]["x"] - ks[i]["x"] for i in range(len(ks) - 1)]
    slot_w = w.call("h_slotW")
    touched = dict(w.call("h_storeTouched").items())
    # Any method call on the forbidden mock raises, so a reparent, anchor or hook could not land silently:
    # the guard is the key count (no key built for it), no child added, no fsMicroKey stamp, and an empty log.
    check("forbidden.button_gets_no_key_hooks_or_reparent",
          len(w.get("FS.MicroBars.keys")) == 11 and touched["newKids"] == 0 and not touched["fsMicroKey"] and w.logs() == "",
          f"keys {len(w.get('FS.MicroBars.keys'))} touched {touched}")
    inspect = w.call("h_inspectNames").split(",")
    check("forbidden.inspect_list_excludes_it", len(inspect) == 11 and "StoreMicroButton" not in inspect, f"{inspect}")
    check("forbidden.other_keys_nest_as_if_it_were_absent",
          len(ks) == 11 and all(near(s, pitch) for s in steps) and near(ks[-1]["x"] + ks[-1]["w"] / 2, slot_w / 2),
          f"{len(ks)} keys, steps {steps[:2]}")
    check("forbidden.button_prints_nothing", w.logs() == "", w.logs())

    # Camelot fallback (no layoutIndex on any child) skips it too; the only log is the fallback note.
    w = World(4, 1.0, store="button", nolayout=True).login()
    check("forbidden.fallback_order_skips_it", len(w.get("FS.MicroBars.keys")) == 3 and w.logs().count("\n") == 0
          and "list-fallback" in w.logs() and not any(dict(w.call("h_storeTouched").items()).values()), w.logs())

    # The log line in game came from the Store WINDOW (StoreFrame) being forbidden: the key still builds.
    w = World(12, 1.0, store="window").login()
    check("forbidden.window_frame_does_not_break_its_key", len(w.get("FS.MicroBars.keys")) == 12 and w.logs() == "", w.logs())


def check_constants(lean: float, gap: float) -> None:
    c = dict(World(1).g.h_deckConst().items())
    check("constants.deck_gap_matches_mockup", c["gap"] == gap, f"{c['gap']} vs mockup {gap}")
    check("constants.deck_lean_matches_mockup", c.get("lean") == lean, f"{c.get('lean')} vs mockup {lean}")
    tga = tga_lean_frac(CELL_SLANT)
    check("constants.lean_matches_cell_slant_tga", abs(tga - lean) <= 1 / 32, f"tga {tga:.4f} vs {lean}")


def check_microstyle() -> None:
    """icons.microstyle: stock (the default) shows the game's textures in their own colours, upright and cut to the key by the cover; gradient restyles them; our own baked keys (Legacy, the person glyph) do not change; every key repaints
    live."""
    def plain(x):
        return {k: plain(v) for k, v in x.items()} if hasattr(x, "items") else x

    def infos(w: World) -> list[dict]:
        return [plain(v) for _, v in w.call("h_glyphInfo").items()]

    def runtime(w: World) -> list[int]:
        return [i + 1 for i, k in enumerate(infos(w)) if k["kind"] == "runtime"]

    w = World(12).login()
    mb = w.get("FS.MicroBars")
    cfg_set = w.get("FS.Config.Set")
    setting = mb.SETTING
    check("microstyle.the_setting_is_icons_microstyle_with_a_stock_default_and_a_tip",
          setting is not None and setting.key == "icons.microstyle" and setting.default == "stock" and len(str(setting.tip)) > 20
          and w.get("FS.Config.Get")("icons.microstyle") == "stock", f"{setting}")
    check("microstyle.the_label_is_micro_menu_icons", str(setting.label) == "Micro menu icons", f"{setting.label}")
    # the style is read from Config once at load and again on a change, never per paint
    w.lua.execute("GETS = 0; REAL_GET = FS.Config.Get; FS.Config.Get = function(k) GETS = GETS + 1; return REAL_GET(k) end")
    w.call("h_script", 1, "OnEnter"); w.call("h_script", 1, "OnLeave"); w.call("h_enabled", 2, False); w.call("h_enabled", 2, True)
    check("microstyle.painting_never_reads_the_config", w.get("GETS") == 0, f"{w.get('GETS')} reads")
    w.lua.execute("FS.Config.Get = REAL_GET")
    check("microstyle.the_styles_are_stock_and_gradient", [str(v) for _, v in mb.STYLES.items()] == ["stock", "gradient"])
    rt = runtime(w)
    check("microstyle.most_keys_draw_the_games_texture", len(rt) >= 10, f"{rt}")
    stock = infos(w)
    bad = [i for i in rt if stock[i - 1]["desat"] or list(stock[i - 1]["vertex"].values()) != [1, 1, 1, 1]]
    check("microstyle.stock_shows_the_games_colours_untinted_and_not_desaturated", not bad, f"{bad}")
    bad = [i for i in rt if stock[i - 1]["boostShown"] or stock[i - 1]["modShown"] or stock[i - 1]["liftShown"]]
    check("microstyle.stock_hides_the_whole_gradient_chain", not bad, f"{bad}")
    bad = [i for i in rt if not stock[i - 1]["coverShown"] or "iconcover" not in stock[i - 1]["coverTex"]]
    check("microstyle.stock_is_still_cut_to_the_key_by_the_cover", not bad, f"{bad}")

    cfg_set("icons.microstyle", "gradient")
    grad = infos(w)
    check("microstyle.gradient_greys_the_base_and_shows_the_chain",
          all(grad[i - 1]["desat"] is True and grad[i - 1]["modShown"] and grad[i - 1]["liftShown"] for i in rt))
    bad = [i for i in rt if stock[i - 1]["left"] != grad[i - 1]["left"] or stock[i - 1]["right"] != grad[i - 1]["right"]
           or stock[i - 1]["tex"] != grad[i - 1]["tex"] or dict(stock[i - 1]["c"]) != dict(grad[i - 1]["c"])]
    check("microstyle.both_styles_draw_the_same_texture_with_the_same_window_in_the_same_place", not bad, f"{bad}")
    # no class known: the Character key falls back to our baked person glyph (Legacy is baked too, see the glyph checks)
    wo = World(16, cls=None).login()
    before = infos(wo)
    wo.get("FS.Config.Set")("icons.microstyle", "gradient")
    after = infos(wo)
    own = [i for i in range(len(before)) if before[i]["kind"] != "runtime"]
    check("microstyle.own_art_keys_exist_and_do_not_change_with_the_style",
          len(own) >= 1 and all(after[i] == before[i] for i in own), f"{own}")

    cfg_set("icons.microstyle", "stock")
    w.call("h_script", 1, "OnEnter")
    hov = infos(w)[0]
    check("microstyle.a_hovered_stock_key_stays_plain", not hov["modShown"] and not hov["desat"] and list(hov["vertex"].values()) == [1, 1, 1, 1], f"{hov['vertex']}")
    w.call("h_script", 1, "OnLeave")
    w.call("h_enabled", 2, False)
    dis = infos(w)[1]
    check("microstyle.a_disabled_stock_key_is_dim_and_desaturated_with_no_chain", dis["desat"] is True and dis["vertex"][4] < 1 and not dis["modShown"], f"{dis['vertex']} {dis['desat']}")
    cfg_set("icons.microstyle", "gradient")
    back = infos(w)
    check("microstyle.gradient_repaints_every_key_live_even_a_disabled_one",
          all(back[i - 1]["modShown"] and back[i - 1]["desat"] is True for i in rt if i != 2)
          and back[1]["modShown"] is False and back[1]["desat"] is True and back[1]["vertex"][4] < 1, f"{back[1]['modShown']}")
    cfg_set("icons.microstyle", "stock")
    w.call("h_enabled", 2, True)
    shown = ("desat", "vertex", "boostShown", "modShown", "liftShown", "coverShown", "left", "right", "tex", "c")
    check("microstyle.the_round_trip_restores_the_stock_look", [{k: i.get(k) for k in shown} for i in infos(w)] == [{k: i.get(k) for k in shown} for i in stock])

    cfg_set("icons.microstyle", "gradient")
    cfg_set("icons.microstyle", "nonsense")
    check("microstyle.an_unknown_value_is_stock", not any(infos(w)[i - 1]["modShown"] for i in rt))
    w.g.IN_COMBAT = True
    cfg_set("icons.microstyle", "gradient")
    check("microstyle.texture_writes_follow_the_style_in_combat_too", all(infos(w)[i - 1]["modShown"] for i in rt))
    cfg_set("icons.microstyle", "stock")
    check("microstyle.and_back_to_stock_in_combat", not any(infos(w)[i - 1]["modShown"] for i in rt))
    w.g.IN_COMBAT = False

    # a world that logs in with the setting already on gradient paints gradient from the start
    ws = World(12)
    ws.get("FS.Config.Set")("icons.microstyle", "gradient")
    ws.login()
    si = infos(ws)
    check("microstyle.a_key_built_under_gradient_paints_gradient_at_login",
          all(si[i - 1]["modShown"] and si[i - 1]["desat"] for i in runtime(ws)), f"{[si[i-1]['modShown'] for i in runtime(ws)]}")
    # a saved value the Config already holds when the player logs in (no change event fires for it) is read at login
    wl = World(12)
    wl.lua.execute('CONFIG["icons.microstyle"] = "gradient"')
    wl.login()
    li = infos(wl)
    check("microstyle.a_saved_gradient_value_is_read_at_login", all(li[i - 1]["modShown"] and li[i - 1]["desat"] for i in runtime(wl)), f"{[li[i-1]['modShown'] for i in runtime(wl)]}")
    check("microstyle.no_degrade_logs", w.logs() == "" and ws.logs() == "", w.logs())


def main() -> int:
    lean, gap = mockup_numbers()
    check_constants(lean, gap)
    check_layout(lean, gap)
    check_overlay()
    check_glyph_files()
    check_fill()
    check_cover_geometry()
    check_slant_direction()
    check_no_empty_wedge()
    check_crisp()
    check_window_follows_the_rect()
    check_fit_window()
    check_zoom_data()
    check_glyph_view()
    check_zoomed_key()
    check_late_class()
    check_glyph_tint()
    check_microstyle()
    check_art()
    check_hit_rects(lean, gap)
    check_deck(lean, gap)
    check_shape()
    check_fit()
    check_combat_deck()
    check_standalone()
    check_removed_art()
    check_forbidden_store(lean, gap)
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
