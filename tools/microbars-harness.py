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

import math
import os
import re
import sys
from pathlib import Path

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
function M:SetTexCoord() end
function M:SetHorizTile() end
function M:SetVertTile() end
function M:SetDesaturated() end
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
function M:IsEnabled() return true end
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
function GetTime() return NOW end

UIParent = newObj("Frame", nil, "UIParent")
newObj("Frame", UIParent, "ForeverSTUwaveXPBar")
GameTooltip = newObj("Frame", nil, "GameTooltip")

RECON = {}
-- The one number the mock treats as a secret value (a secret is still type "number" in the client).
SECRET_W = 100.5
FS = {
    Layout = { Scale = function() return SCALE end, OnRescale = function(fn) RESCALE[#RESCALE + 1] = fn end },
    PanelSkins = { RequireExport = function() return true end, RegisterRecon = function(group, list) RECON[group] = list end },
    IsSecret = function(v) return v == SECRET_W end,
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
-- The names MicroBars registered with PanelSkins.RegisterRecon, comma-joined.
function h_reconNames()
    local out = {}
    for i, e in ipairs(RECON.MicroMenu or {}) do out[i] = e.name end
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
        if o.kind == "Texture" and o.color and o.color[4] == 1 and o.allPoints and underButton(o) then n = n + 1 end
    end
    return n
end
-- Per button: how many textures under its overlay use a glyph file.
function h_glyphCounts()
    local out = {}
    for i, b in ipairs(BUTTONS) do
        local n = 0
        for _, o in ipairs(ALL) do
            if o.kind == "Texture" and o.tex and tostring(o.tex):find("glyph_", 1, true) then
                local p = o.parent
                while p and p ~= b do p = p.parent end
                if p == b then n = n + 1 end
            end
        end
        out[i] = n
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
                 store: str | None = None, nolayout: bool = False, deck: bool = True):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK)
        g = self.lua.globals()
        g.STORE, g.STORE_IDX, g.NOLAYOUT, g.NODECK = store, n, nolayout, not deck   # the Store button is the last one built
        g.DECK_SRC = DECK_LUA.read_text(encoding="utf-8")
        g.MICRO_SRC = MICRO_LUA.read_text(encoding="utf-8")
        g.SCALE = scale
        g.COLOR_POWER = self.lua.table_from(list(theme_color_power()))
        g.COLOR_SCRIM = self.lua.table_from(list(theme_color_scrim()))
        self.g = g
        g.h_setup(n, ",".join(str(h) for h in hidden), layout_deck_w() if layout_cfg else None)

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
    counts = [c for _, c in w.call("h_glyphCounts").items()]
    check("overlay.glyph_drawn_once_per_key", counts == [1] * 12, f"{counts}")


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
    check("deck.micro_max_is_the_12_key_row_rounded_up", c["microMax"] == math.ceil(natural12 - 1e-9) and 0 <= c["microMax"] - natural12 < 1,
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
    recon = w.call("h_reconNames").split(",")
    check("forbidden.recon_list_excludes_it", len(recon) == 11 and "StoreMicroButton" not in recon, f"{recon}")
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


def main() -> int:
    lean, gap = mockup_numbers()
    check_constants(lean, gap)
    check_layout(lean, gap)
    check_overlay()
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
