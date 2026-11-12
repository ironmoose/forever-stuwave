#!/usr/bin/env python3
"""Pin the minimap's ONE BODY against the REAL Theme.lua, FrameHelpers.lua and Layout.lua.

Loads Minimap.lua under lupa on a permissive mock WoW API, fires PLAYER_LOGIN, and checks the design of mockup A
("ONE BODY", mockups/minimap-bags-cleanup-2026-11-12.html), under Theme.CHROME_CORNERS "cut" and "round":

  * ONE body: the map, the key row and (open) the tray's row sit in one frame with one cyan edge and one plate that starts
    where the map ends; under "cut" only its TOP-LEFT and BOTTOM-RIGHT are chamfered (baked c = 6 pieces), the map's mask
    cuts only the top-left, and none of the old separate boxes (a bezel fill and border, a coords box, a tray box, a
    SkinButton key) is drawn any more;
  * the key row: tracking (cyan), calendar (violet), the STU key (pink), the tray toggle (amber), then mail (pink) while mail
    waits: bare glyphs over a 2 px LED, no boxes; a hovered key gets a thin outline in its own colour and a bright LED; keys
    are placed by the keys that are showing, so the row has no hole;
  * SPACING, every number a whole screen pixel and the mockup's (its px / 2, scaled by the map's pixel width over 248):
    equal margins left, right, above and below the keys, keys evenly spaced, glyphs centred in their keys, the divider
    centred in the row, the coords right aligned at the same margin, tray tiles on the key columns;
  * the coords: the player position only (no clock), fitted between the divider and the right margin;
  * the addon-button tray (LibDBIcon collection), against a fake LibStub whose "LibDBIcon-1.0" object is shaped like the
    real LibDBIcon-1.0 (minor 56): collected buttons become keys of a second row under a dashed amber rule (the body ends at
    the drawer while it is open), wrap onto more rows, are toggled by the row's fourth key (count and chevron, persisted),
    and combat defers every reparent;
  * the Edit Mode seat compensation of the map itself (unchanged by the redesign).

    python3 tools/minimap-harness.py
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

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
THEME_SRC = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
# MINIMAP_LUA / LAYOUT_LUA point the harness at a mutant copy (mutation checks).
LAYOUT_SRC = Path(os.environ.get("LAYOUT_LUA", ADDON / "Core/Layout.lua")).read_text(encoding="utf-8")
MINIMAP_SRC = Path(os.environ.get("MINIMAP_LUA", ADDON / "Modules/Minimap/Minimap.lua")).read_text(encoding="utf-8")
FRAMEHELPERS_SRC = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
CONFIGWINDOW_SRC = (ADDON / "Modules/Config/ConfigWindow.lua").read_text(encoding="utf-8")

MOCK = r"""
local THEME_SRC, MINIMAP_SRC, MODE, UI_HEIGHT, LAYOUT_SRC, SETUP, PRE_DB = ...
local mediaPrefix = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local Region = {}
Region.__index = function(t, k)
    if Region[k] then return Region[k] end
    if type(k) == "string" and k:match("^[SGHEMRCIPAUFLD]%l") and not k:match("^Zoom") then
        local verb = k:match("^%u%l+")
        local verbs = { Set = 1, Get = 1, Hide = 1, Show = 1, Enable = 1, Register = 1, Unregister = 1,
            Clear = 1, Is = 1, Hook = 1, Create = 1, Raise = 1, Lower = 1, Disable = 1, Update = 1 }
        if verbs[verb] then return function() end end
    end
end
allFrames = {}
local function new(kind, parent)
    local o = setmetatable({ kind = kind, parent = parent, regions = {}, children = {}, w = 250, h = 250,
        scripts = {}, points = {}, shown = true, events = {}, level = 1,
        strata = (parent and parent.strata) or "MEDIUM" }, Region)
    if kind == "frame" then allFrames[#allFrames + 1] = o end
    return o
end
function Region:SetSize(w, h) self.w, self.h = w, h end
function Region:SetWidth(w) self.w = w end
function Region:SetHeight(h) self.h = h end
function Region:GetWidth() return self.w end
function Region:GetHeight() return self.h end
function Region:SetTexture(p) self.texture = p end
function Region:GetTexture() return self.texture end
function Region:SetVertexColor(r, g, b, a) self.tint = { r, g, b, a } end
function Region:SetTextureSliceMargins(l) self.slice = l end
function Region:SetScript(n, fn) self.scripts[n] = fn end
function Region:GetScript(n) return self.scripts[n] end
-- HookScript keeps its hooks (post-handlers); __fire runs a script then its hooks, as the client does for a state change.
function Region:HookScript(n, fn)
    self.hooks = self.hooks or {}
    self.hooks[n] = self.hooks[n] or {}
    table.insert(self.hooks[n], fn)
end
function Region:__fire(n)
    local s = self.scripts[n]
    if s then s(self) end
    for _, fn in ipairs(self.hooks and self.hooks[n] or {}) do fn(self) end
end
function Region:SetAlpha(a) self.alpha = a end
function Region:GetAlpha() return self.alpha or 1 end
function Region:SetColorTexture(r, g, b, a) self.color = { r, g, b, a == nil and 1 or a } end
function Region:SetTexCoord(l, r, t, b) self.coords = { l, r, t, b } end
function Region:SetDrawLayer(layer, sub) self.layer, self.sublevel = layer, sub end
function Region:SetMaskTexture(p) self.mask = p end
function Region:SetAllPoints(rel)
    rel = rel or self.parent
    self.allPoints = rel
    self.points = { TOPLEFT = { rel = rel, relPoint = "TOPLEFT", x = 0, y = 0 },
                    BOTTOMRIGHT = { rel = rel, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
end
function Region:CreateTexture(_, layer, _, sublevel)
    local t = new("texture", self)
    t.layer, t.sublevel = layer, sublevel
    self.regions[#self.regions + 1] = t
    return t
end
function Region:CreateFontString()
    local f = new("fontstring", self)
    self.regions[#self.regions + 1] = f
    return f
end
function Region:SetParent(p)
    if self.parent then
        for i, c in ipairs(self.parent.children) do
            if c == self then table.remove(self.parent.children, i) break end
        end
    end
    self.parent = p
    if p then p.children[#p.children + 1] = self end
end
function Region:GetParent() return self.parent end
function Region:GetChildren() return unpack(self.children) end
function Region:GetRegions() return unpack(self.regions) end
function Region:GetObjectType()
    if self.kind == "texture" then return "Texture" end
    if self.kind == "fontstring" then return "FontString" end
    return self.otype or "Frame"
end
function Region:GetName() return self.name end
-- A frame whose shown state changes runs OnShow / OnHide (a texture has none); a Show on a shown frame does nothing.
function Region:Show()
    local was = self.shown
    self.shown = true
    if not was and self.kind == "frame" then self:__fire("OnShow") end
end
function Region:Hide()
    local was = self.shown
    self.shown = false
    if was and self.kind == "frame" then self:__fire("OnHide") end
end
function Region:IsShown() return self.shown end
function Region:IsVisible()
    if not self.shown then return false end
    return (not self.parent) or self.parent:IsVisible()
end
function Region:SetPoint(point, rel, relPoint, x, y)
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    self.points[point] = { rel = rel, relPoint = relPoint, x = x or 0, y = y or 0 }
end
function Region:ClearAllPoints() self.points = {} end
function Region:RegisterEvent(e) self.events[e] = true end
function Region:UnregisterEvent(e) self.events[e] = nil end
function Region:RegisterForDrag(...) self.dragButtons = select("#", ...) end
function Region:SetText(t) self.text = t end
function Region:GetText() return self.text end
-- Strata/level: a frame flagged fixed ignores a plain set (the conservative reading of
-- SetFixedFrameStrata/Level, which LibDBIcon buttons use), so only an unfix-first caller moves it.
function Region:SetFrameLevel(l) if not self.fixedLevel then self.level = l end end
function Region:GetFrameLevel() return self.level end
function Region:SetFrameStrata(s) if not self.fixedStrata then self.strata = s end end
function Region:GetFrameStrata() return self.strata end
function Region:SetFixedFrameStrata(v) self.fixedStrata = v and true or false end
function Region:SetFixedFrameLevel(v) self.fixedLevel = v and true or false end
function Region:SetScale(s) self.scale = s end
function Region:GetScale() return self.scale or 1 end
function Region:IsProtected() return self.protected and true or false end
function Region:SetHighlightTexture(tex, mode)
    self.highlight = self.highlight or new("texture", self)
    self.highlight.texture, self.highlight.mode = tex, mode
end
function Region:GetHighlightTexture() return self.highlight end
function Region:GetFont() return "font", 10 end
function Region:SetFont(_, size) self.fontSize = size; return true end
function Region:GetStringWidth() return 20 end
function Region:GetLeft() return 0 end
function Region:GetTop() return 0 end
function Region:GetEffectiveScale() return 1 end

function CreateFrame(otype, name, parent)
    local f = new("frame", parent)
    f.otype = otype or "Frame"
    f.name = name
    if name then _G[name] = f end
    if parent then parent.children[#parent.children + 1] = f end
    __last = f
    return f
end
UIParent = new("frame")
if UI_HEIGHT then UIParent.h = UI_HEIGHT end
Minimap = new("frame", UIParent)
MinimapCluster = new("frame", UIParent)
MinimapCluster.Tracking = new("frame", MinimapCluster)
MinimapCluster.Tracking.otype = "Button"
GameFontNormal = new("font")
DEFAULT_CHAT_FRAME = new("frame")
__combat = false
function InCombatLockdown() return __combat end
function hooksecurefunc(a, b, c)
    local obj, name, fn = a, b, c
    if type(a) == "string" then obj, name, fn = _G, a, b end
    local orig = obj[name]
    if type(orig) ~= "function" then return end
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
Enum = { UITextureSliceMode = { Stretched = 1 } }
__timers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
function RunTimers()
    local t = __timers; __timers = {}
    for _, fn in ipairs(t) do fn() end
end
function FireEvent(ev, ...)
    for _, f in ipairs(allFrames) do
        if f.events[ev] and f.scripts.OnEvent then f.scripts.OnEvent(f, ev, ...) end
    end
end
GameTooltip = { text = nil, shown = false }
function GameTooltip:SetOwner(o) self.owner = o end
function GameTooltip:SetText(t) self.text = t end
function GameTooltip:Show() self.shown = true end
function GameTooltip:Hide() self.shown = false end

FS = { LogDegradeOnce = function() end }
assert(loadstring(THEME_SRC, "@Theme.lua"))("forever-stuwave", FS)
local Theme = FS.Theme
Theme.CHROME_CORNERS = MODE
Theme.FONT_MONO = Theme.FONT_MONO or "mono"

calls = { glow = {}, border = {}, fill = {}, skin = {} }
local function wrap(name, bucket)
    local orig = Theme[name]
    Theme[name] = function(frame, ...)
        local args = { ... }
        calls[bucket][#calls[bucket] + 1] = { frame = frame, args = args, isMap = (frame == Minimap) }
        return orig(frame, ...)
    end
end
wrap("AddOuterGlow", "glow")
wrap("AddGradientBorder", "border")
wrap("AddRoundedFill", "fill")
wrap("SkinButton", "skin")

if PRE_DB then ForeverSTUwaveDB = PRE_DB end
if SETUP then assert(loadstring(SETUP, "@setup"))() end

-- With a UIParent height, seat the real FS.Layout so Minimap.lua derives its metrics from
-- the scaled map size exactly as in game (scale = UI_HEIGHT / 1440).
if UI_HEIGHT then assert(loadstring(LAYOUT_SRC, "@Layout.lua"))("forever-stuwave", FS) end
assert(loadstring(MINIMAP_SRC, "@Minimap.lua"))("forever-stuwave", FS)
-- the loader frame is the last frame created at file scope
__loader = __last
__Theme = Theme
return Theme
"""


# A LibDBIcon-1.0 look-alike, kept to what the real source (minor 56) does: createButton builds a
# Button parented to Minimap named LibDBIcon10_<name> with .border/.background/.icon and fires
# lib.callbacks "LibDBIcon_IconCreated" (button, name); updatePosition is a file-local that
# SetPoint("CENTER", Minimap, "CENTER", x, y) and is what Refresh / Show / SetButtonRadius call.
# lib.RegisterCallback(owner, event, fn) calls fn(event, ...) per CallbackHandler-1.0.
LIB_SETUP = r"""
local lib = { objects = {}, radius = 5 }
lib.callbacks = { events = {} }
function lib.callbacks:Fire(ev, ...)
    for _, fn in pairs(self.events[ev] or {}) do fn(ev, ...) end
end
function lib.RegisterCallback(owner, ev, fn)
    lib.callbacks.events[ev] = lib.callbacks.events[ev] or {}
    lib.callbacks.events[ev][owner] = fn
end
local function updatePosition(button, position)
    button:SetPoint("CENTER", Minimap, "CENTER", 120, 40)
end
function lib:Register(name, object, db)
    local button = CreateFrame("Button", "LibDBIcon10_" .. name, Minimap)
    button.dataObject = object
    button.db = db
    lib.objects[name] = button
    -- createButton pins strata and level as FIXED (LibDBIcon-1.0 lines 257-260)
    button:SetFrameStrata("MEDIUM")
    button:SetFixedFrameStrata(true)
    button:SetFrameLevel(8)
    button:SetFixedFrameLevel(true)
    button:RegisterForDrag("LeftButton")
    lib:ResetButtonHighlightTexture(name)
    lib:ResetButtonSize(name)
    button.border = button:CreateTexture(nil, "OVERLAY")
    lib:ResetButtonBorder(name)
    button.background = button:CreateTexture(nil, "BACKGROUND")
    lib:ResetButtonBackground(name)
    button.icon = button:CreateTexture(nil, "ARTWORK")
    lib:ResetButtonIcon(name)
    updatePosition(button, db and db.minimapPos)
    lib.callbacks:Fire("LibDBIcon_IconCreated", button, name)
end
function lib:GetMinimapButton(name) return lib.objects[name] end
-- Button configuration, shaped like the real lib's non-mainline branch.
function lib:SetButtonSize(name, size)
    local button = lib:GetMinimapButton(name)
    if button and type(size) == "number" then button:SetSize(size, size) end
end
function lib:ResetButtonSize(name)
    local button = lib:GetMinimapButton(name)
    if button then button:SetSize(31, 31) end
end
function lib:SetButtonHighlightTexture(name, tex)
    local button = lib:GetMinimapButton(name)
    if button and (type(tex) == "number" or type(tex) == "string") then button:SetHighlightTexture(tex) end
end
function lib:ResetButtonHighlightTexture(name)
    local button = lib:GetMinimapButton(name)
    if button then button:SetHighlightTexture(136477) end
end
function lib:ResetButtonBorder(name)
    local button = lib:GetMinimapButton(name)
    if button.border then
        button.border:Show()
        button.border:ClearAllPoints()
        button.border:SetPoint("TOPLEFT", 0, 0)
        button.border:SetTexture(136430)
        button.border:SetSize(53, 53)
    end
end
function lib:SetButtonBorder(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.border then
        lib:ResetButtonBorder(name)
        if type(tex) == "number" or type(tex) == "string" then button.border:SetTexture(tex) end
        if type(size) == "number" then button.border:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.border:ClearAllPoints()
            button.border:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:ResetButtonBackground(name)
    local button = lib:GetMinimapButton(name)
    if button.background then
        button.background:Show()
        button.background:ClearAllPoints()
        button.background:SetTexture(136467)
        button.background:SetSize(20, 20)
        button.background:SetPoint("TOPLEFT", 7, -5)
    end
end
function lib:SetButtonBackground(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.background then
        lib:ResetButtonBackground(name)
        if type(tex) == "number" or type(tex) == "string" then button.background:SetTexture(tex) end
        if type(size) == "number" then button.background:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.background:ClearAllPoints()
            button.background:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:ResetButtonIcon(name)
    local button = lib:GetMinimapButton(name)
    if button.icon then
        button.icon:SetTexture(button.dataObject.icon)
        button.icon:SetSize(17, 17)
        button.icon:ClearAllPoints()
        button.icon:SetPoint("TOPLEFT", 7, -6)
    end
end
function lib:SetButtonIcon(name, tex, size, framePoint, ox, oy)
    local button = lib:GetMinimapButton(name)
    if button.icon then
        lib:ResetButtonIcon(name)
        if type(tex) == "number" or type(tex) == "string" then button.icon:SetTexture(tex) end
        if type(size) == "number" then button.icon:SetSize(size, size) end
        if type(framePoint) == "string" then
            button.icon:ClearAllPoints()
            button.icon:SetPoint(framePoint, ox or 0, oy or 0)
        end
    end
end
function lib:GetButtonList()
    local t = {}
    for name in next, lib.objects do t[#t + 1] = name end
    return t
end
function lib:Refresh(name, db)
    local button = lib:GetMinimapButton(name)
    if button then updatePosition(button, db and db.minimapPos); button:Show() end
end
function lib:Show(name)
    local button = lib:GetMinimapButton(name)
    if button then button:Show(); updatePosition(button) end
end
function lib:Hide(name)
    local button = lib:GetMinimapButton(name)
    if button then button:Hide() end
end
function lib:SetButtonRadius(radius)
    lib.radius = radius
    for _, button in next, lib.objects do updatePosition(button) end
end
function lib:ShowOnEnter(name, value)
    local button = lib:GetMinimapButton(name)
    if button then button.showOnMouseover = value and true or false; button:SetAlpha(value and 0 or 1) end
end
LibStub = setmetatable({}, { __call = function(_, name, silent)
    if name == "LibDBIcon-1.0" then return lib end
end })
__lib = lib
function MakeObj(name) return { type = "launcher", icon = "Interface\\Icons\\" .. name } end
"""

def run(mode: str, ui_height: float | None = None, setup: str | None = None, pre_db=None,
        login: bool = True):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("function ___run(...) " + MOCK + " end")
    pre = None
    if pre_db is not None:
        pre = lua.table_from(pre_db)
    lua.globals().___run(THEME_SRC, MINIMAP_SRC, mode, ui_height, LAYOUT_SRC, setup, pre)
    if login:
        lua.execute("__loader.scripts.OnEvent(__loader)")
    return lua


failures = 0


def check(label: str, ok: bool) -> None:
    global failures
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures += 1


TEXTURES = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
SEARCH_TEXTURE = TEXTURES + "icon_key_search.tga"
CALENDAR_TEXTURE = TEXTURES + "icon_key_calendar.tga"
CHEVRON_TEXTURE = TEXTURES + "icon_key_chevron.tga"
STU_TEXTURE = TEXTURES + "icon_stu.tga"
MASK_TEXTURE = TEXTURES + "mask_minimap_tl.tga"
GLOW_ROUND = TEXTURES + "glow_round.tga"
CUT_BORDER_C6 = TEXTURES + "border_cut_c6_t1.tga"
CUT_FILL_C6 = TEXTURES + "fill_cut_c6.tga"
STU_KEY = "ForeverSTUwaveMinimapSTUKey"
TOGGLE = "ForeverSTUwaveMinimapTrayToggle"
LAYER_RANK = {"BACKGROUND": 0, "BORDER": 1, "ARTWORK": 2, "OVERLAY": 3, "HIGHLIGHT": 4}

# The mockup is drawn at 2x, so each number is its px / 2 at the reference map of 496 / 2 = 248 px (Minimap.lua SPEC).
REF_MAP = 248
BODY_PLATE = (0.043, 0.024, 0.094, 0.94)
STU_INK_BOTTOM = 25 / 32   # the bottom edge of icon_stu.tga's last solid texel row, as a fraction of its canvas
MONO_ADVANCE = 0.5615   # Mononoki Nerd Font Mono, measured with PIL (em); the widest reading is "99.9, 99.9" (10 glyphs)
READOUT_CHARS = 10
LED_REST, LED_BRIGHT, WASH_ALPHA = 0.75, 1.0, 0.18
KEY_DOT_SIZE, KEY_DOT_OFFSET, KEY_DOT_REACH = 6, 2, 3


def geo(width_px: float) -> dict:
    """The key row's geometry in whole screen pixels for a map `width_px` wide: the mockup's numbers (px / 2) scaled by
    width / 248 and rounded, glyph and STU canvas forced to the key's parity (an odd gap would leave half a pixel)."""
    k = width_px / REF_MAP

    def s(n):
        return max(1, math.floor(n * k + 0.5))

    def like(n, ref):
        return n + 1 if (n - ref) % 2 else n

    g = {"width": math.floor(width_px + 0.5)}
    g["row"] = s(28)
    g["keyW"] = s(18)
    g["keyH"] = min(like(s(22), g["row"]), g["row"])
    g["topM"] = (g["row"] - g["keyH"]) / 2
    g["margin"] = s(8)
    g["keyGap"] = s(8)
    g["pitch"] = g["keyW"] + g["keyGap"]
    g["toggleW"] = like(s(30), g["keyW"])
    g["led"] = s(2)
    g["glyph"] = like(s(16), g["keyW"])
    g["glyphGap"] = s(3)
    g["glyphY"] = max(0, g["keyH"] - g["led"] - g["glyphGap"] - g["glyph"])
    g["stu"] = like(s(32), g["keyW"])
    g["stuX"] = (g["keyW"] - g["stu"]) / 2
    g["stuGap"] = s(2)
    g["stuY"] = math.floor(g["keyH"] - g["led"] - g["stuGap"] - STU_INK_BOTTOM * g["stu"] + 0.5)
    g["coords"] = s(12)
    g["count"] = s(10)
    g["dividerH"] = min(like(s(18), g["row"]), g["row"])
    g["chevW"], g["chevH"] = s(8), s(4)
    g["outlineX"] = s(3)
    g["outlineY"] = max(1, min(math.floor(g["topM"]), s(1)))
    g["halo"] = s(1)
    g["dash"], g["ruleInset"] = s(2), s(6)
    return g


# What the design pins at the reference map (a 250 px map is within a pixel of 248): the mockup's own px / 2.
MOCKUP_250 = {"row": 28, "margin": 8, "keyW": 18, "keyGap": 8, "keyH": 22, "topM": 3, "glyph": 16, "glyphY": 1, "led": 2,
              "stu": 32, "dividerH": 18, "coords": 12, "count": 10, "pitch": 26}

# (label, UIParent height or None, UI units per pixel): a 250 px map, a 208 px one (1200 tall UIParent) and one 469 px wide
WORLDS = (("250", None, 1.0), ("208", 1200, 1.0), ("469", None, 768 / 1440))

PIXELS = r"""
PixelUtil = { GetPixelToUIUnitFactor = function() return %r end }
local R = getmetatable(UIParent)
function R:SetSnapToPixelGrid(v) self.snap = v end
function R:SetTexelSnappingBias(v) self.bias = v end
assert(loadstring(FH_SRC, "@FrameHelpers.lua"))("forever-stuwave", FS)
"""

# Blizzard furniture the key row adopts or must leave alone, with the stock art the keys blank: a sun on the calendar, an
# icon on the tracking button, plate art on the mail frame. As in Blizzard's XML the mail frame starts hidden.
BLIZZARD_KEYS = r"""
GameTimeFrame = CreateFrame("Button", "GameTimeFrame", Minimap)
GameTimeFrame.sun = GameTimeFrame:CreateTexture(nil, "ARTWORK")
GameTimeFrame.sun:SetTexture("blizzard-sun")
GameTimeFrame.day = GameTimeFrame:CreateFontString()
MinimapCluster.Tracking.plate = MinimapCluster.Tracking:CreateTexture(nil, "BACKGROUND")
MinimapCluster.Tracking.Button = CreateFrame("Button", nil, MinimapCluster.Tracking)
MinimapCluster.Tracking.Button.icon = MinimapCluster.Tracking.Button:CreateTexture(nil, "ARTWORK")
MinimapCluster.Tracking.Button.icon:SetTexture("blizzard-tracking")
ExpansionLandingPageMinimapButton = CreateFrame("Button", "ExpansionLandingPageMinimapButton", Minimap)
Minimap.ZoomIn = CreateFrame("Button", "MinimapZoomIn", Minimap)
MinimapCluster.IndicatorFrame = { MailFrame = CreateFrame("Button", "MiniMapMailFrame", MinimapCluster) }
MinimapCluster.IndicatorFrame.MailFrame.Border = MinimapCluster.IndicatorFrame.MailFrame:CreateTexture(nil, "BORDER")
MinimapCluster.IndicatorFrame.MailFrame:Hide()
MiniMapMailIcon = MinimapCluster:CreateTexture(nil, "ARTWORK") -- Blizzard draws the envelope on ARTWORK
MiniMapMailIcon:Hide()
SomeRandomButton = CreateFrame("Button", "SomeRandomButton", Minimap)
SomeRandomFrame = CreateFrame("Frame", "SomeRandomMinimapButtonHolder", Minimap)
-- excluded by the hidden-by-HideBlizzardChrome flag alone, and by a Blizzard name prefix alone
FlagHiddenMinimapButton = CreateFrame("Button", "FlagHiddenMinimapButton", Minimap)
FlagHiddenMinimapButton.fsHideHooked = true
ExpansionLandingPageMinimapButton2 = CreateFrame("Button", "ExpansionLandingPageMinimapButton2", Minimap)
"""

HELPERS = r"""
function __same(a, b) return a == b end
function __click(f) f.scripts.OnClick(f, "LeftButton") end
function __hover(f, on) f:__fire(on and "OnEnter" or "OnLeave") end
function __toggles_reset() __toggles = 0; FS.ConfigWindow = { Toggle = function() __toggles = __toggles + 1 end } end
-- What Blizzard 12.1 does when UPDATE_PENDING_MAIL says there is mail (Blizzard_Minimap/Mainline/Minimap.lua):
-- MiniMapMailFrameMixin:OnEvent shows the FRAME, starts the arrival animation (MinimapMailAnimMixin:OnPlay hides the envelope,
-- 0.4 to 0.5 s) and asks the PARENT to lay out. The envelope (MiniMapMailIcon, hidden="true" in the XML) is shown only by
-- MinimapMailAnimMixin:OnFinished, and MiniMapMailFrameMixin:OnHide runs ResetMailIcon, which hides it. The parent was
-- MinimapCluster.IndicatorFrame, a LayoutFrame; after our reparent it is the bezel.
function __mail_arrives()
    local mail = MinimapCluster.IndicatorFrame.MailFrame
    MiniMapMailIcon:Hide()
    mail:Show()
    mail:GetParent():Layout()
end
function __mail_anim_finished() MiniMapMailIcon:Show() end
function __mail_hides()
    MinimapCluster.IndicatorFrame.MailFrame:Hide()
    MiniMapMailIcon:Hide()
end
function __visible(r) return r:IsVisible() end
function __rescale()
    for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end
end
"""


def pixel_setup(factor: float, extra: str = "", tray: str = "") -> str:
    return ("FH_SRC = [==[" + FRAMEHELPERS_SRC + "]==]\n" + PIXELS % factor + LIB_SETUP + BLIZZARD_KEYS + extra + tray)


def world(label_ui_factor, extra="", tray="", pre_db=None, mode="cut"):
    """(lua, globals, px) for a world with the real FrameHelpers answering PixelUnit = `factor` UI units per pixel."""
    _, ui_height, factor = label_ui_factor
    lua = run(mode, ui_height, pixel_setup(factor, extra, tray), pre_db)
    lua.execute(HELPERS)
    return lua, lua.globals(), factor


def whole(v: float, px: float) -> bool:
    return abs(v / px - round(v / px)) < 1e-6


def regions(frame) -> list:
    return list(frame.regions.values())


def led_of(frame):
    """The LED underline: the flat texture pinned to the key's bottom edge across its full width."""
    found = [r for r in regions(frame) if r.color is not None and r.points.BOTTOMLEFT is not None
             and r.points.BOTTOMLEFT.y == 0 and r.points.BOTTOMLEFT.x == 0 and r.points.BOTTOMRIGHT is not None
             and r.points.BOTTOMRIGHT.x == 0 and r.h is not None and r.points.BOTTOMLEFT.rel is not None]
    return found[0] if len(found) == 1 else None


def wash_of(frame):
    found = [r for r in regions(frame) if r.color is not None and r.points.BOTTOMLEFT is not None
             and r.points.BOTTOMLEFT.y < 0]
    return found[0] if len(found) == 1 else None


def outline_of(frame):
    found = [r for r in regions(frame) if r.slice is not None]
    return found[0] if len(found) == 1 else None


def glyph_of(frame, path):
    found = [r for r in regions(frame) if r.texture == path]
    return found[0] if len(found) == 1 else None


def coords_of(r) -> tuple:
    """(L, R, T, B) of a texture's SetTexCoord, rounded."""
    return tuple(round(r.coords[i], 4) for i in (1, 2, 3, 4))


def near(a, b, tol=1e-6) -> bool:
    return abs(a - b) <= tol


def rgb_of(c) -> tuple:
    """(r, g, b) of a Python tuple or a Lua colour table (1-based)."""
    return (c[1], c[2], c[3]) if hasattr(c, "items") else tuple(c[:3])


def tint_is(r, rgb, alpha=None, tol=1e-3) -> bool:
    t = r.tint if r.tint is not None else r.color
    if t is None:
        return False
    want = rgb_of(rgb)
    ok = all(near(t[i + 1], want[i], tol) for i in range(3))
    return ok and (alpha is None or near(t[4], alpha, tol))


def body_checks() -> None:
    """One body, one edge, one plate; chamfered top-left and bottom-right only; nothing of the old boxes."""
    for mode in ("cut", "round"):
        for w in WORLDS[:2]:
            label = f"{mode}@{w[0]}"
            lua, g, px = world(w, mode=mode)
            body, bezel, minimap = g.Minimap.fsBody, g.Minimap.fsBezel, g.Minimap
            calls = g.calls

            def same(a, b):
                return bool(g.__same(a, b))

            check(f"[body {label}] one body frame, a child of the bezel, a level above it",
                  body is not None and same(body.parent, bezel) and body.level == bezel.level + 1)
            tl, br = body.points.TOPLEFT, body.points.BOTTOMRIGHT
            check(f"[body {label}] it runs from the map's top-left to the bezel's bottom-right, no offsets (tray closed)",
                  same(tl.rel, minimap) and tl.relPoint == "TOPLEFT" and tl.x == 0 and tl.y == 0
                  and same(br.rel, bezel) and br.relPoint == "BOTTOMRIGHT" and br.x == 0 and br.y == 0)
            check(f"[body {label}] none of the old boxes: no rounded fill, no gradient border, no SkinButton key",
                  len(calls.fill) == 0 and len(calls.border) == 0 and len(calls.skin) == 0)
            want = 6 if mode == "cut" else 0
            glow = list(calls.glow.values())
            check(f"[body {label}] one outer glow, on the body (not the map), chamfer {want}",
                  len(glow) == 1 and same(glow[0].frame, body) and glow[0].args[6] == want)
            check(f"[body {label}] the map's mask cuts only its top-left", minimap.mask == MASK_TEXTURE)
            flats = [r for r in regions(body) if r.color is not None]
            edge = [r for r in flats if tint_is(r, (0.133, 0.878, 1.0), 1.0)]
            check(f"[body {label}] one cyan edge: four flat full alpha lines", len(edge) == 4)
            top = [r for r in edge if r.points.TOPLEFT is not None and r.points.TOPRIGHT is not None]
            bottom = [r for r in edge if r.points.BOTTOMLEFT is not None and r.points.BOTTOMRIGHT is not None
                      and r.points.BOTTOMLEFT.rel is not None and r.points.BOTTOMLEFT.y == 0
                      and r.points.BOTTOMLEFT.relPoint == "BOTTOMLEFT" and r.points.BOTTOMLEFT.x == 0]
            check(f"[body {label}] the top and bottom lines are 1 px ({top[0].h / px:g} and {bottom[0].h / px:g}), the "
                  f"sides 1 px wide",
                  len(top) == 1 and len(bottom) == 1 and near(top[0].h, px) and near(bottom[0].h, px)
                  and all(near(r.w, px) for r in edge if r.points.TOPLEFT is not None and r.points.BOTTOMLEFT is not None
                          and r.points.TOPRIGHT is None))
            pieces = [r for r in regions(body) if r.texture == CUT_BORDER_C6]
            plate_corner = [r for r in regions(body) if r.texture == CUT_FILL_C6]
            plate = [r for r in flats if tint_is(r, BODY_PLATE[:3], BODY_PLATE[3])]
            check(f"[body {label}] the plate is flat #0b0618 at .94, three runs and one corner piece, none over the map",
                  len(plate) == 2 and len(plate_corner) == 1
                  and all(same(r.points.TOPLEFT.rel, minimap) and r.points.TOPLEFT.relPoint == "BOTTOMLEFT"
                          for r in plate if r.points.TOPLEFT is not None))
            if mode == "cut":
                coords = sorted((coords_of(p), next(iter(p.points.keys()))) for p in pieces)
                check(f"[body {label}] the cut: exactly a top-left and a bottom-right piece at chamfer 6, nothing at the "
                      f"other two corners",
                      coords == sorted([((0, 0.375, 0, 0.375), "TOPLEFT"), ((0.375, 0, 0.375, 0), "BOTTOMRIGHT")])
                      and all(p.shown is True and near(p.w, 6 * px) and near(p.h, 6 * px) for p in pieces)
                      and all(tint_is(p, (0.133, 0.878, 1.0), 1.0) for p in pieces))
                corner = plate_corner[0]
                check(f"[body {label}] the plate's corner piece sits in the bottom-right and is flipped both ways",
                      coords_of(corner) == (0.375, 0, 0.375, 0)
                      and next(iter(corner.points.keys())) == "BOTTOMRIGHT" and near(corner.w, 6 * px))
            else:
                check(f"[body {label}] round mode: the square body, no cut pieces drawn",
                      all(p.shown is False for p in pieces) and all(p.shown is False for p in plate_corner))
            rule = [r for r in flats if tint_is(r, (0.133, 0.878, 1.0), 0.35)]
            check(f"[body {label}] the rule where the map meets the first row: cyan at 35%, 1 px, the map's full width",
                  len(rule) == 1 and same(rule[0].points.TOPLEFT.rel, minimap)
                  and rule[0].points.TOPLEFT.relPoint == "BOTTOMLEFT" and near(rule[0].h, px)
                  and same(rule[0].points.TOPRIGHT.rel, minimap) and rule[0].points.TOPRIGHT.relPoint == "BOTTOMRIGHT")

    # the body ends at the drawer while the tray is open, and goes back to the bezel when it closes
    lua, g, px = world(WORLDS[0], tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
    body, bezel, tray = g.Minimap.fsBody, g.Minimap.fsBezel, g.Minimap.fsTray
    check("[body] tray closed: the body ends at the bezel", bool(g.__same(body.points.BOTTOMRIGHT.rel, bezel)))
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[body] tray open: the body ends at the drawer's bottom-right", bool(g.__same(body.points.BOTTOMRIGHT.rel, tray))
          and body.points.BOTTOMRIGHT.relPoint == "BOTTOMRIGHT" and body.points.BOTTOMRIGHT.x == 0
          and body.points.BOTTOMRIGHT.y == 0 and bool(g.__same(body.points.TOPLEFT.rel, g.Minimap)))
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[body] tray closed again: back to the bezel", bool(g.__same(body.points.BOTTOMRIGHT.rel, bezel)))
    lua, g, px = world(WORLDS[0], tray="", pre_db={"minimapTrayOpen": True})
    check("[body] no buttons: the drawer stays hidden even when saved open, so the body stays at the bezel",
          g.Minimap.fsTray.shown is False and bool(g.__same(g.Minimap.fsBody.points.BOTTOMRIGHT.rel, g.Minimap.fsBezel)))


def spacing_checks() -> None:
    """The key row's spacing: the mockup's numbers on whole pixels, equal margins, even pitch, centred glyphs."""
    # the design's own numbers at the reference map
    ref = geo(250.0)
    check("[spacing] the design numbers at a 250 px map are the mockup's px / 2: "
          + ", ".join(f"{k} {v}" for k, v in MOCKUP_250.items()),
          all(ref[k] == v for k, v in MOCKUP_250.items()))

    for w in WORLDS:
        label = w[0]
        lua, g, px = world(w, tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
        e = geo(g.Minimap.w / px)
        bezel = g.Minimap.fsBezel
        keys = [("tracking", g.MinimapCluster.Tracking, SEARCH_TEXTURE), ("calendar", g.GameTimeFrame, CALENDAR_TEXTURE),
                ("stu", g.Minimap.fsSTUKey, STU_TEXTURE), ("toggle", g.Minimap.fsTrayToggle, None)]
        resolved = [str(g.Minimap.fsBezelResolved[i]) for i in range(1, len(g.Minimap.fsBezelResolved) + 1)]
        check(f"[spacing@{label}] the keys built are tracking, calendar, stu, mail ({resolved}); the toggle joins from the tray",
              resolved == ["tracking", "calendar", "stu", "mail"] and all(f is not None for _, f, _ in keys))
        check(f"[spacing@{label}] the bezel is {e['row']} px tall (the row), the map {g.Minimap.w / px:.1f} px wide "
              f"(scale {g.Minimap.w / px / REF_MAP:.3f})",
              near(bezel.h, e["row"] * px) and whole(bezel.h, px))

        # every key is keyW wide but the tray toggle, which is toggleW (its count and chevron need the room)
        xs, ws, want_x = [], [], e["margin"]
        for i, (name, frame, tex) in enumerate(keys):
            p = frame.points.TOPLEFT
            x, y = p.x / px, -p.y / px
            kw = e["toggleW"] if name == "toggle" else e["keyW"]
            xs.append(x)
            ws.append(kw)
            check(f"[spacing@{label}] key {i + 1} ({name}) is {kw} x {e['keyH']} px at x {want_x}, "
                  f"y {e['topM']:g} from the row's top, on whole pixels (got {frame.w / px:g} x {frame.h / px:g} at {x:g}, {y:g})",
                  bool(g.__same(p.rel, bezel)) and p.relPoint == "TOPLEFT"
                  and near(x, want_x) and near(y, e["topM"])
                  and near(frame.w / px, kw) and near(frame.h / px, e["keyH"])
                  and all(whole(v, px) for v in (p.x, p.y, frame.w, frame.h)))
            want_x += kw + e["keyGap"]
        row_end = want_x
        gaps = [xs[i + 1] - xs[i] - ws[i] for i in range(len(xs) - 1)]
        check(f"[spacing@{label}] keys are evenly spaced: every gap is {e['keyGap']} px ({gaps})",
              all(near(gp, e["keyGap"]) for gp in gaps))
        check(f"[spacing@{label}] equal margins above and below the keys: {e['topM']:g} px each ("
              f"{e['topM']:g} above, {e['row'] - e['topM'] - e['keyH']:g} below)",
              near(e["row"] - e["topM"] - e["keyH"], e["topM"]))

        # glyphs centred in their keys, and the LED across the full key at the bottom
        for name, frame, tex in keys:
            kw = e["toggleW"] if name == "toggle" else e["keyW"]
            led = led_of(frame)
            check(f"[spacing@{label}] {name}: the LED is the key's full width, {e['led']} px, at its bottom edge",
                  led is not None and near(led.h, e["led"] * px) and whole(led.h, px)
                  and bool(g.__same(led.points.BOTTOMLEFT.rel, frame)))
            if tex is None:
                continue
            glyph = glyph_of(frame, tex)
            p = glyph.points.TOPLEFT
            if name == "stu":
                ink_bottom = e["stuY"] + STU_INK_BOTTOM * e["stu"]
                check(f"[spacing@{label}] stu: the {e['stu']} px icon canvas is centred on the key sideways "
                      f"({e['stuX']:g} px each side) and hung so its ink ends {e['stuGap']} px above the LED "
                      f"({-p.y / px:g} below top, key {e['keyH']} px)",
                      near(glyph.w / px, e["stu"]) and near(glyph.h / px, e["stu"]) and near(p.x / px, e["stuX"])
                      and near(p.y / px, -e["stuY"]) and whole(p.x, px) and whole(p.y, px)
                      and near(p.x / px + glyph.w / px / 2, e["keyW"] / 2)
                      and abs((e["keyH"] - e["led"] - ink_bottom) - e["stuGap"]) <= 0.5)
                continue
            side = (e["keyW"] - e["glyph"]) / 2
            check(f"[spacing@{label}] {name}: the {e['glyph']} px glyph is centred in the {e['keyW']} px key "
                  f"({side:g} px each side, whole), {e['glyphY']} px below the key's top, {e['glyphGap']} px above the LED",
                  near(glyph.w / px, e["glyph"]) and near(glyph.h / px, e["glyph"]) and near(p.x / px, side)
                  and near(-p.y / px, e["glyphY"]) and side == int(side) and whole(p.x, px) and whole(p.y, px)
                  and near(e["keyH"] - (e["glyphY"] + e["glyph"]) - e["led"], e["glyphGap"])
                  and glyph.snap is True and glyph.bias == 0)

        # the divider and the coords
        coords = g.Minimap.fsReadoutCoords
        n_keys = len(keys)
        divider = [r for r in regions(g.Minimap.fsBody) if r.color is not None and tint_is(r, (0.133, 0.878, 1.0), 0.3)]
        check(f"[spacing@{label}] one divider, cyan at 30%", len(divider) == 1)
        d = divider[0]
        dx = d.points.TOPLEFT.x / px
        check(f"[spacing@{label}] the divider is one key gap past the last key ({row_end} px), 1 px "
              f"wide, {e['dividerH']} px tall, centred in the {e['row']} px row (got x {dx:g}, y {-d.points.TOPLEFT.y / px:g})",
              near(dx, row_end) and near(dx - xs[-1] - ws[-1], e["keyGap"])
              and near(d.w, px) and near(d.h / px, e["dividerH"])
              and near(-d.points.TOPLEFT.y / px, (e["row"] - e["dividerH"]) / 2)
              and all(whole(v, px) for v in (d.points.TOPLEFT.x, d.points.TOPLEFT.y, d.w, d.h)))
        right = coords.points.RIGHT
        check(f"[spacing@{label}] the coords are right aligned at the same margin as the first key: {-right.x / px:g} px "
              f"(left margin {xs[0]:g})",
              bool(g.__same(right.rel, bezel)) and right.relPoint == "RIGHT" and right.y == 0
              and near(-right.x / px, e["margin"]) and near(xs[0], e["margin"]) and whole(right.x, px))
        room = e["width"] - e["margin"] - (row_end + 1 + e["keyGap"])
        want_font = max(5, min(e["coords"], math.floor(room / (READOUT_CHARS * MONO_ADVANCE))))
        check(f"[spacing@{label}] the coords font is {want_font} px (its {e['coords']} px, or what the room {room} px takes) "
              f"and a reading is {READOUT_CHARS * MONO_ADVANCE * want_font:.1f} px, clear of the divider",
              near(coords.fontSize / px, want_font) and READOUT_CHARS * MONO_ADVANCE * want_font <= room + 1e-6)

        # the toggle's count and chevron, on the glyph row
        toggle = g.Minimap.fsTrayToggle
        chev = glyph_of(toggle, CHEVRON_TEXTURE)
        count = toggle.count
        cw = 20 / px  # the mock FontString:GetStringWidth() is 20 UI units
        group = math.floor(cw + 0.5) + e["glyphGap"] + e["chevW"]
        want_right = min(math.floor((e["toggleW"] + group) / 2), e["toggleW"] - 1)
        check(f"[spacing@{label}] the toggle's chevron is {e['chevW']} x {e['chevH']} px, the count and chevron centred as one group "
              f"across the {e['toggleW']} px key (chevron right at {want_right}), on the glyph row; the count is {e['count']} px, "
              f"a {e['glyphGap']} px gap left of it",
              near(chev.w / px, e["chevW"]) and near(chev.h / px, e["chevH"])
              and bool(g.__same(chev.points.RIGHT.rel, toggle)) and chev.points.RIGHT.relPoint == "TOPLEFT"
              and near(chev.points.RIGHT.x / px, want_right, 1)
              and near(chev.points.RIGHT.y / px, -(e["glyphY"] + e["glyph"] / 2))
              and near(count.fontSize / px, e["count"]) and bool(g.__same(count.points.RIGHT.rel, chev))
              and count.points.RIGHT.relPoint == "LEFT" and near(count.points.RIGHT.x / px, -e["glyphGap"]))


def row_checks() -> None:
    """Which keys the row has, in what order, and that it packs by the keys showing (no hole)."""
    for w in WORLDS[:2]:
        label = w[0]
        # buttons collected: tracking, calendar, stu, toggle; mail joins as the fifth when it arrives
        lua, g, px = world(w, tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
        e = geo(g.Minimap.w / px)
        mail = g.MinimapCluster.IndicatorFrame.MailFrame
        bezel = g.Minimap.fsBezel

        def slot(frame):
            return round((frame.points.TOPLEFT.x / px - e["margin"]) / e["pitch"])

        check(f"[row@{label}] mail waits for mail: hidden, no slot, the divider after four keys",
              mail.shown is False and mail.parent is not None and bool(g.__same(mail.parent, bezel)))
        divider = [r for r in regions(g.Minimap.fsBody) if r.color is not None and tint_is(r, (0.133, 0.878, 1.0), 0.3)][0]
        before = divider.points.TOPLEFT.x
        lua.execute("__mail_arrives()")
        check(f"[row@{label}] mail arriving takes the fifth slot at once (the key's own OnShow reseats the row)",
              mail.shown is True and near(mail.points.TOPLEFT.x / px, e["margin"] + 3 * e["pitch"] + e["toggleW"] + e["keyGap"])
              and near(mail.w / px, e["keyW"]) and near(mail.h / px, e["keyH"]))
        check(f"[row@{label}] the divider moves right one key pitch ({(divider.points.TOPLEFT.x - before) / px:g} px)",
              near((divider.points.TOPLEFT.x - before) / px, e["pitch"]))
        lua.execute("__mail_hides()")
        check(f"[row@{label}] mail hiding gives the slot back (the divider returns)",
              near(divider.points.TOPLEFT.x, before))

        # no tray buttons: the toggle gives its slot back; mail then takes the fourth
        lua, g, px = world(w)
        e = geo(g.Minimap.w / px)
        mail = g.MinimapCluster.IndicatorFrame.MailFrame
        toggle = g.Minimap.fsTrayToggle
        check(f"[row@{label}] no addon buttons: the toggle is hidden and the row is three keys",
              toggle.shown is False)
        lua.execute("__mail_arrives()")
        check(f"[row@{label}] ... so mail takes the fourth slot, no hole where the toggle is",
              near(mail.points.TOPLEFT.x / px, e["margin"] + 3 * e["pitch"]))
        lua.execute('__lib:Register("Alpha", MakeObj("Alpha"), {})')
        check(f"[row@{label}] ... and the first addon button brings the toggle back in the fourth slot, mail to the fifth",
              toggle.shown is True and near(toggle.points.TOPLEFT.x / px, e["margin"] + 3 * e["pitch"])
              and near(mail.points.TOPLEFT.x / px, e["margin"] + 3 * e["pitch"] + e["toggleW"] + e["keyGap"]))

    # a client without the calendar button: the next key takes its place, no hole
    lua, g, px = world(WORLDS[0], extra="GameTimeFrame:Hide(); GameTimeFrame = nil")
    e = geo(g.Minimap.w / px)
    resolved = [str(g.Minimap.fsBezelResolved[i]) for i in range(1, len(g.Minimap.fsBezelResolved) + 1)]
    check("[row] no calendar button on this client: it is skipped and the STU key takes the second slot",
          resolved == ["tracking", "stu", "mail"] and near(g.Minimap.fsSTUKey.points.TOPLEFT.x / px, e["margin"] + e["pitch"]))

    # a throw while building the STU key is logged, leaves nothing half built, and the rest of the row still comes up
    lua, g, px = world(WORLDS[0], extra=LOGGING + r"""
    local create = CreateFrame
    function CreateFrame(otype, name, parent)
        local f = create(otype, name, parent)
        if name == "ForeverSTUwaveMinimapSTUKey" then f.RegisterForClicks = function() error("stuboom") end end
        return f
    end
    """, tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
    e = geo(g.Minimap.w / px)
    logs = [str(g.__logs[i]) for i in range(1, len(g.__logs) + 1)]
    key = g[STU_KEY]
    check("[row] a failing STU key build is logged once under minimap_key_stu, with the error",
          len(logs) == 1 and logs[0].startswith("minimap_key_stu|") and "stuboom" in logs[0])
    check("[row] ... the half-built key is hidden and unpublished, and no slot is spent on it",
          key is not None and key.shown is False and g.Minimap.fsSTUKey is None
          and near(g.Minimap.fsTrayToggle.points.TOPLEFT.x / px, e["margin"] + 2 * e["pitch"]))
    check("[row] ... and tracking, calendar and the toggle still come up in slots 1, 2 and 3",
          near(g.MinimapCluster.Tracking.points.TOPLEFT.x / px, e["margin"])
          and near(g.GameTimeFrame.points.TOPLEFT.x / px, e["margin"] + e["pitch"]))
    resolved = [str(g.Minimap.fsBezelResolved[i]) for i in range(1, len(g.Minimap.fsBezelResolved) + 1)]
    check(f"[row] the resolved and skipped lists say so ({resolved})", resolved == ["tracking", "calendar", "mail"])

    # Blizzard's keys: reparented onto the bezel, their own art blanked, ours drawn; the zoom and expansion buttons are not
    lua, g, px = world(WORLDS[0])
    bezel, tracking, calendar, mail = (g.Minimap.fsBezel, g.MinimapCluster.Tracking, g.GameTimeFrame,
                                       g.MinimapCluster.IndicatorFrame.MailFrame)

    def same(a, b):
        return bool(g.__same(a, b))

    check("[row] tracking, calendar and mail are reparented onto the bezel, above the body",
          same(tracking.parent, bezel) and same(calendar.parent, bezel) and same(mail.parent, bezel)
          and tracking.level == calendar.level == mail.level == bezel.level + 3 > g.Minimap.fsBody.level)
    check("[row] tracking and calendar are shown, with the mouse on, at full alpha (HideBlizzardChrome's hide undone)",
          tracking.shown is True and calendar.shown is True and tracking.alpha == 1 and calendar.alpha == 1)
    check("[row] the stock calendar sun and the date number are blanked (alpha 0), our calendar glyph is not",
          g.GameTimeFrame.sun.alpha == 0 and g.GameTimeFrame.day.alpha == 0
          and glyph_of(calendar, CALENDAR_TEXTURE).alpha is None)
    check("[row] the stock tracking plate and icon are blanked (alpha 0) and the button is pinned to the key "
          "(SetAllPoints), our magnifier glyph is not",
          tracking.plate.alpha == 0 and tracking.Button.icon.alpha == 0
          and tracking.Button.allPoints is not None and same(tracking.Button.allPoints, tracking)
          and glyph_of(tracking, SEARCH_TEXTURE).alpha is None)
    check("[row] the mail frame keeps its own shown state (hidden until mail), its plate art is blanked",
          mail.shown is False and mail.Border.alpha == 0)
    check("[row] tracking and calendar glyphs are tinted cyan and violet, the LEDs the same colours at .75",
          tint_is(glyph_of(tracking, SEARCH_TEXTURE), g.__Theme.COLOR_POWER)
          and tint_is(glyph_of(calendar, CALENDAR_TEXTURE), g.__Theme.COLOR_BORDER)
          and tint_is(led_of(tracking), g.__Theme.COLOR_POWER, 1.0) and led_of(tracking).alpha == LED_REST
          and tint_is(led_of(calendar), g.__Theme.COLOR_BORDER, 1.0) and led_of(calendar).alpha == LED_REST
          and tint_is(led_of(g.Minimap.fsSTUKey), g.__Theme.COLOR_HEALTH, 1.0)
          and led_of(g.Minimap.fsSTUKey).alpha == LED_REST)
    check("[row] the zoom and expansion buttons are not keys (left where they are)",
          same(g.Minimap.ZoomIn.parent, g.Minimap) and same(g.ExpansionLandingPageMinimapButton.parent, g.Minimap))
    check("[row] the bezel answers Layout() with a no-op, so mail's GetParent():Layout() cannot throw",
          g.Minimap.fsBezel.Layout is not None)


def hover_checks() -> None:
    """A hovered key: a thin chamfered outline in its own colour and a bright LED (and the wash behind it)."""
    lua, g, px = world(WORLDS[0], tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
    e = geo(g.Minimap.w / px)
    tracking, calendar, stu, toggle = (g.MinimapCluster.Tracking, g.GameTimeFrame, g.Minimap.fsSTUKey,
                                       g.Minimap.fsTrayToggle)
    lua.execute("__mail_arrives()")
    mail = g.MinimapCluster.IndicatorFrame.MailFrame
    for name, frame, rgb, extra in (("tracking", tracking, g.__Theme.COLOR_POWER, tracking.Button),
                                    ("calendar", calendar, g.__Theme.COLOR_BORDER, None),
                                    ("stu", stu, g.__Theme.COLOR_HEALTH, None),
                                    ("toggle", toggle, (1, 0.7137, 0.2824), None),
                                    ("mail", mail, g.__Theme.COLOR_HEALTH, None)):
        led, wash, outline = led_of(frame), wash_of(frame), outline_of(frame)
        target = extra if extra is not None else frame
        check(f"[hover] {name}: at rest the LED is at {LED_REST}, no wash, no outline",
              led.alpha == LED_REST and wash.shown is False and outline.shown is False)
        check(f"[hover] {name}: the outline is the chamfered button ring in the key's own colour, {e['outlineX']} px out "
              f"at the sides, {e['outlineY']} px above and below",
              tint_is(outline, rgb) and tint_is(wash, rgb, WASH_ALPHA)
              and near(outline.points.TOPLEFT.x / px, -e["outlineX"]) and near(outline.points.TOPLEFT.y / px, e["outlineY"])
              and near(outline.points.BOTTOMRIGHT.x / px, e["outlineX"])
              and near(outline.points.BOTTOMRIGHT.y / px, -e["outlineY"])
              and outline.texture is not None and outline.texture.startswith(TEXTURES + "slice_cut2_outline")
              and outline.slice == g.__Theme.SnapCut(e["outlineX"]))
        check(f"[hover] {name}: the wash reaches {e['halo']} px past the LED, inside the outline that stands "
              f"{e['outlineY']} px out below and {e['outlineX']} px at the sides",
              near(wash.points.BOTTOMLEFT.x / px, -e["halo"]) and near(wash.points.BOTTOMLEFT.y / px, -e["halo"])
              and near(wash.points.BOTTOMRIGHT.x / px, e["halo"]) and near(wash.h / px, e["led"] + 2 * e["halo"])
              and e["halo"] <= e["outlineY"] and e["halo"] <= e["outlineX"])
        g.__hover(target, True)
        check(f"[hover] {name}: hovering shows the outline, brightens the LED to {LED_BRIGHT} and lights the wash",
              outline.shown is True and led.alpha == LED_BRIGHT and wash.shown is True)
        g.__hover(target, False)
        check(f"[hover] {name}: leaving puts it all back",
              outline.shown is False and led.alpha == LED_REST and wash.shown is False)

    # the STU key's own behaviour: tooltip, click, and a hide with the mouse on it clears the hover
    lua.execute("__toggles_reset()")
    g.__hover(stu, True)
    check("[hover] the STU key shows the tooltip 'Settings' on itself",
          g.GameTooltip.text == "Settings" and g.GameTooltip.shown is True and bool(g.__same(g.GameTooltip.owner, stu)))
    lua.execute("__click(Minimap.fsSTUKey)")
    check("[hover] a click toggles the config window (the toggle /fsconfig runs)", g.__toggles == 1)
    g.__hover(stu, False)
    check("[hover] leaving hides the tooltip", g.GameTooltip.shown is False)
    g.__hover(stu, True)
    stu.Hide(stu)
    check("[hover] a key hidden under the mouse (no OnLeave comes) clears its hover", outline_of(stu).shown is False
          and led_of(stu).alpha == LED_REST)
    stu.Show(stu)
    g.GameTooltip.text = None
    lua.execute("FS.ConfigWindow = nil; __click(Minimap.fsSTUKey)")
    check("[hover] with no config window loaded, a click does nothing and does not throw", True)
    check("[hover] ConfigWindow exports Toggle and /fsconfig calls that same Toggle (pinned on its own text)",
          "function CW.Toggle()" in CONFIGWINDOW_SRC and 'SLASH_FSCONFIG1 = "/fsconfig"' in CONFIGWINDOW_SRC
          and re.search(r'SlashCmdList\["FSCONFIG"\].*?CW\.Toggle\(\)', CONFIGWINDOW_SRC, re.S) is not None)

    # the open tray's toggle stays bright while open, hover or not
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[hover] an open tray holds the toggle's LED bright and its wash lit (no hover)",
          led_of(toggle).alpha == LED_BRIGHT and wash_of(toggle).shown is True and outline_of(toggle).shown is False)
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[hover] closing it lets the LED rest again", led_of(toggle).alpha == LED_REST)


LOGGING = r"""
__logs = {}
FS.LogDegradeOnce = function(key, msg) __logs[#__logs + 1] = tostring(key) .. "|" .. tostring(msg) end
"""

FOO = 'FooMinimapButton = CreateFrame("Button", "FooMinimapButton", Minimap)\n__lib:Register("Alpha", MakeObj("Alpha"), {})\n'


def tray_checks() -> None:
    w = WORLDS[0]

    # ---- A: a lib button, a stray, Blizzard furniture, a late IconCreated, the lib re-seating
    lua, g, px = world(w, tray=FOO)
    e = geo(g.Minimap.w / px)
    tray, toggle, bezel = g.Minimap.fsTray, g.Minimap.fsTrayToggle, g.Minimap.fsBezel
    alpha, foo = g.__lib.objects.Alpha, g.FooMinimapButton

    def same(a, b):
        return bool(g.__same(a, b))

    def only_tray_anchor(b):
        pts = list(b.points.keys())
        return pts == ["TOPLEFT"] and same(b.points.TOPLEFT.rel, tray)

    check("[tray] drawer and toggle exist", tray is not None and toggle is not None)
    check("[tray] lib button Alpha is parented in the drawer", same(alpha.parent, tray))
    check("[tray] stray FooMinimapButton is parented in the drawer", same(foo.parent, tray))
    check("[tray] both are seated as keys (single TOPLEFT anchor on the drawer)",
          only_tray_anchor(alpha) and only_tray_anchor(foo))
    check(f"[tray] tiles are key-sized ({e['keyW']} x {e['keyH']} px) on the key row's columns, "
          f"{e['topM']:g} px below the drawer's top, whole pixels",
          near(alpha.w / px, e["keyW"]) and near(alpha.h / px, e["keyH"]) and near(foo.w, alpha.w)
          and near(alpha.points.TOPLEFT.x / px, e["margin"]) and near(foo.points.TOPLEFT.x / px, e["margin"] + e["pitch"])
          and near(alpha.points.TOPLEFT.y / px, -e["topM"]) and near(foo.points.TOPLEFT.y / px, -e["topM"])
          and all(whole(v, px) for v in (alpha.w, alpha.h, alpha.points.TOPLEFT.x, alpha.points.TOPLEFT.y)))
    check("[tray] LibDBIcon round border and background art are hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    side = (e["keyW"] - e["glyph"]) / 2
    check(f"[tray] LibDBIcon icon is re-seated in the glyph box ({e['glyph']} px, {side:g} px in, {e['glyphY']} px down)",
          list(alpha.icon.points.keys()) == ["TOPLEFT"] and near(alpha.icon.w / px, e["glyph"])
          and near(alpha.icon.points.TOPLEFT.x / px, side) and near(alpha.icon.points.TOPLEFT.y / px, -e["glyphY"]))
    check("[tray] drag-to-move is switched off (RegisterForDrag with no buttons)",
          alpha.dragButtons == 0 and foo.dragButtons == 0)
    check("[tray] tile chrome: an LED in the tile's accent (cyan, then pink), the wash and the hover outline",
          led_of(alpha) is not None and tint_is(led_of(alpha), g.__Theme.COLOR_POWER, 1.0)
          and led_of(alpha).alpha == LED_REST and tint_is(led_of(foo), g.__Theme.COLOR_HEALTH, 1.0)
          and wash_of(alpha) is not None and outline_of(alpha) is not None and near(led_of(alpha).h / px, e["led"]))
    check("[tray] the lib's round highlight is replaced by a flat one at no alpha (the hover look is the key's own)",
          alpha.highlight.texture == "Interface\\Buttons\\WHITE8X8" and alpha.highlight.mode == "ADD"
          and alpha.highlight.alpha == 0)
    g.__hover(alpha, True)
    check("[tray] a collected button's own OnEnter hover lights its outline and LED",
          outline_of(alpha).shown is True and led_of(alpha).alpha == LED_BRIGHT)
    g.__hover(alpha, False)

    check("[tray] bezel keys stay in the bezel (tracking, calendar, mail, STU)",
          same(g.MinimapCluster.Tracking.parent, bezel) and same(g.GameTimeFrame.parent, bezel)
          and same(g.MinimapCluster.IndicatorFrame.MailFrame.parent, bezel) and same(g.Minimap.fsSTUKey.parent, bezel))
    check("[tray] the toggle is a key of the bezel row, not of the drawer", same(toggle.parent, bezel))
    check("[tray] expansion button, zoom button, a random button and a non-button are NOT collected",
          same(g.ExpansionLandingPageMinimapButton.parent, g.Minimap) and same(g.Minimap.ZoomIn.parent, g.Minimap)
          and same(g.SomeRandomButton.parent, g.Minimap) and same(g.SomeRandomFrame.parent, g.Minimap))
    check("[tray] a button HideBlizzardChrome hid, and a Blizzard-prefixed one, are NOT collected",
          same(g.FlagHiddenMinimapButton.parent, g.Minimap) and same(g.ExpansionLandingPageMinimapButton2.parent, g.Minimap))

    check("[tray] count reads 2", toggle.count.text == "2")
    check("[tray] toggle is shown with buttons collected", toggle.shown is True)
    g.__hover(toggle, True)
    check("[tray] toggle tooltip reads 'Addon buttons (2)'", g.GameTooltip.text == "Addon buttons (2)")
    g.__hover(toggle, False)

    # late IconCreated
    lua.execute('__lib:Register("Bravo", MakeObj("Bravo"), {})')
    bravo = g.__lib.objects.Bravo
    check("[tray] a later IconCreated button is collected and seated on the third column",
          same(bravo.parent, tray) and only_tray_anchor(bravo)
          and near(bravo.points.TOPLEFT.x / px, e["margin"] + 2 * e["pitch"]))
    check("[tray] count reads 3 after the late button", toggle.count.text == "3")

    # the lib's own reposition must not drag a collected button back around the map
    lua.execute('__lib:Refresh("Alpha", {}); __lib:Show("Alpha"); __lib:SetButtonRadius(9)')
    check("[tray] lib Refresh/Show/SetButtonRadius do not move a collected button back",
          same(alpha.parent, tray) and only_tray_anchor(alpha) and alpha.points.CENTER is None and only_tray_anchor(bravo))
    lua.execute('__lib:ShowOnEnter("Alpha", true)')
    check("[tray] a hover-fade request does not blank a collected button", alpha.showOnMouseover is False)

    # lib sizing / reparent / scale calls after adoption must not undo the tile
    tile = alpha.w
    lua.execute('__lib:SetButtonSize("Alpha", 40); __lib:ResetButtonSize("Alpha")')
    check("[tray] lib SetButtonSize/ResetButtonSize leave the button key-sized", alpha.w == tile and near(alpha.h / px, e["keyH"]))
    lua.execute('local a = __lib.objects.Alpha; a:SetSize(50, 50); a:SetWidth(60); a:SetHeight(61); '
                'a:SetScale(2); a:SetParent(Minimap)')
    check("[tray] direct SetSize/SetWidth/SetHeight/SetScale/SetParent are ignored",
          alpha.w == tile and near(alpha.h / px, e["keyH"]) and alpha.scale == 1 and same(alpha.parent, tray))
    check("[tray] strata matches the drawer and level sits above it, flags re-fixed",
          alpha.strata == tray.strata and alpha.level == tray.level + 2
          and alpha.fixedStrata is True and alpha.fixedLevel is True and foo.level == tray.level + 2)

    # lib art re-applications after adoption must be re-stripped / re-seated
    lua.execute('''
        __lib:ResetButtonBorder("Alpha"); __lib:ResetButtonBackground("Alpha")
        __lib:ResetButtonIcon("Alpha"); __lib:ResetButtonHighlightTexture("Alpha")
    ''')
    check("[tray] lib ResetButtonBorder/Background keep the round art hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    check("[tray] lib ResetButtonIcon keeps the icon in the glyph box",
          list(alpha.icon.points.keys()) == ["TOPLEFT"] and near(alpha.icon.w / px, e["glyph"]))
    check("[tray] lib ResetButtonHighlightTexture keeps the flat no-alpha highlight",
          alpha.highlight.texture == "Interface\\Buttons\\WHITE8X8" and alpha.highlight.mode == "ADD"
          and alpha.highlight.alpha == 0)
    lua.execute('''
        __lib:SetButtonBorder("Alpha", 136430, 40, "TOPLEFT", 1, 1)
        __lib:SetButtonBackground("Alpha", 136467, 30, "CENTER", 0, 0)
        __lib:SetButtonIcon("Alpha", "NewIcon", 18, "TOPLEFT", 7, -6)
        __lib:SetButtonHighlightTexture("Alpha", 136477)
    ''')
    check("[tray] lib SetButtonBorder/Background keep the round art hidden",
          alpha.border.shown is False and alpha.background.shown is False)
    check("[tray] lib SetButtonIcon keeps the icon in the glyph box",
          list(alpha.icon.points.keys()) == ["TOPLEFT"] and near(alpha.icon.w / px, e["glyph"]))
    check("[tray] lib SetButtonHighlightTexture keeps the flat no-alpha highlight",
          alpha.highlight.texture == "Interface\\Buttons\\WHITE8X8" and alpha.highlight.alpha == 0)

    # an addon hiding its own button drops it from the count; showing it brings it back
    alpha.Hide(alpha)
    check("[tray] a hidden button leaves the count", toggle.count.text == "2")
    alpha.Show(alpha)
    check("[tray] a shown button rejoins the count", toggle.count.text == "3")

    # a Show/Hide that changes nothing must not relayout (drawer:SetHeight is the layout's tell)
    lua.execute('__relayouts = 0; local d = Minimap.fsTray; local orig = d.SetHeight; '
                'd.SetHeight = function(self, h) __relayouts = __relayouts + 1; return orig(self, h) end')
    alpha.Show(alpha)
    alpha.Show(alpha)
    check("[tray] Show on an already shown button does not relayout", g.__relayouts == 0)
    alpha.Hide(alpha)
    alpha.Hide(alpha)
    check("[tray] Hide twice relayouts once", g.__relayouts == 1)
    alpha.Show(alpha)
    check("[tray] Show after Hide relayouts once more", g.__relayouts == 2)

    # toggle: default closed, click opens and persists, click closes and persists; the chevron flips with it
    chev = glyph_of(toggle, CHEVRON_TEXTURE)
    check("[tray] drawer starts closed, the chevron points down", tray.shown is False
          and coords_of(chev) == (0, 1, 0, 1))
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] toggle click opens the drawer and persists open", tray.shown is True
          and g.ForeverSTUwaveDB.minimapTrayOpen is True)
    check("[tray] open: the chevron points up", coords_of(chev) == (0, 1, 1, 0))
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] second click closes the drawer and persists closed", tray.shown is False
          and g.ForeverSTUwaveDB.minimapTrayOpen is False)
    check("[tray] closed: the chevron points down again", coords_of(chev) == (0, 1, 0, 1))

    # the drawer: a second row of the row's height under the bezel, a dashed amber rule on its top edge
    drawer_px = near(tray.h / px, e["row"]) and whole(tray.h, px)
    check(f"[tray] the drawer hangs flush under the bezel (TOPLEFT/TOPRIGHT on BOTTOMLEFT/BOTTOMRIGHT, no offset), one "
          f"row ({tray.h / px:g} px) tall for up to nine tiles",
          same(tray.points.TOPLEFT.rel, bezel) and tray.points.TOPLEFT.relPoint == "BOTTOMLEFT"
          and tray.points.TOPLEFT.x == 0 and tray.points.TOPLEFT.y == 0
          and same(tray.points.TOPRIGHT.rel, bezel) and tray.points.TOPRIGHT.relPoint == "BOTTOMRIGHT" and drawer_px)
    dashes = sorted((r for r in regions(tray) if r.color is not None), key=lambda r: r.points.TOPLEFT.x)
    inset, dash = e["ruleInset"], e["dash"]
    n = math.floor((e["width"] - 2 * inset + dash) / (2 * dash))
    check(f"[tray] the rule: {n} amber dashes, {dash} px long with {dash} px gaps, 1 px tall, from {inset} px in, on the "
          f"drawer's top edge",
          len(dashes) == n and all(tint_is(r, (1, 0.7137, 0.2824), 0.35) for r in dashes)
          and all(near(r.w, dash * px) and near(r.h, px) and r.points.TOPLEFT.y == 0 for r in dashes)
          and near(dashes[0].points.TOPLEFT.x / px, inset)
          and all(near((dashes[i + 1].points.TOPLEFT.x - dashes[i].points.TOPLEFT.x) / px, 2 * dash)
                  for i in range(len(dashes) - 1))
          and e["width"] - (dashes[-1].points.TOPLEFT.x / px + dash) >= inset - 1e-6)
    check("[tray] there is no 'ADDONS' label and no text tab: the drawer holds no font string",
          all(r.kind != "fontstring" for r in regions(tray)))

    # ---- B: saved open state is restored at login
    lua, g, px = world(w, tray=FOO, pre_db={"minimapTrayOpen": True})
    check("[tray] saved open state reopens the drawer at login", g.Minimap.fsTray.shown is True
          and bool(g.__same(g.Minimap.fsBody.points.BOTTOMRIGHT.rel, g.Minimap.fsTray)))

    # ---- C: nothing to collect: toggle and drawer hidden; a late stray is picked up by a re-sweep
    lua, g, px = world(w, pre_db={"minimapTrayOpen": True})
    check("[tray] zero buttons: toggle hidden", g.Minimap.fsTrayToggle.shown is False)
    check("[tray] zero buttons: drawer hidden even when saved open", g.Minimap.fsTray.shown is False)
    lua.execute('LateMinimapButton = CreateFrame("Button", "LateMinimapButton", Minimap); '
                'FireEvent("ADDON_LOADED", "SomeAddon")')
    check("[tray] a button created late is collected on ADDON_LOADED",
          bool(g.__same(g.LateMinimapButton.parent, g.Minimap.fsTray)) and g.Minimap.fsTrayToggle.shown is True)
    lua.execute('LaterMinimapIcon = CreateFrame("Button", "LaterMinimapIcon", Minimap); '
                'FireEvent("PLAYER_ENTERING_WORLD"); RunTimers()')
    check("[tray] PLAYER_ENTERING_WORLD plus the delayed timer sweeps again",
          bool(g.__same(g.LaterMinimapIcon.parent, g.Minimap.fsTray)) and g.Minimap.fsTrayToggle.count.text == "2")

    # ---- D: tiles wrap onto more rows of the row's height, on the key columns, and the drawer grows
    lua, g, px = world(w, tray='for i = 1, 20 do CreateFrame("Button", "Wrap" .. i .. "MinimapButton", Minimap) end',
                       pre_db={"minimapTrayOpen": True})
    e = geo(g.Minimap.w / px)
    tray = g.Minimap.fsTray
    cols = math.floor((e["width"] - 2 * e["margin"] + e["keyGap"]) / e["pitch"])
    rows = math.ceil(20 / cols)
    pts = [g[f"Wrap{i}MinimapButton"].points.TOPLEFT for i in range(1, 21)]
    ys = sorted({round(-p.y / px, 3) for p in pts})
    xs = sorted({round(p.x / px, 3) for p in pts})
    check(f"[tray] 20 tiles wrap onto {rows} rows of {e['row']} px ({cols} columns), each {e['topM']:g} px below its "
          f"row's top (got y {ys})",
          ys == [e["topM"] + r * e["row"] for r in range(rows)] and len(xs) == cols)
    check(f"[tray] every tile sits on a key column: x = {e['margin']} + column * {e['pitch']} px",
          xs == [e["margin"] + c * e["pitch"] for c in range(cols)])
    check(f"[tray] the drawer is {rows} rows tall ({tray.h / px:g} px) and the body ends at it",
          near(tray.h / px, rows * e["row"]) and bool(g.__same(g.Minimap.fsBody.points.BOTTOMRIGHT.rel, tray)))
    check("[tray] no tile spills past the drawer's right edge or the margin",
          max(p.x for p in pts) + g.Wrap1MinimapButton.w <= g.Minimap.w - e["margin"] * px + 1e-6)
    check("[tray] 20 tiles collected, count 20", g.Minimap.fsTrayToggle.count.text == "20")

    # ---- E: combat defers the collection to PLAYER_REGEN_ENABLED
    lua, g, px = world(w)
    lua.execute('__combat = true; __lib:Register("Charlie", MakeObj("Charlie"), {})')
    charlie = g.__lib.objects.Charlie
    check("[tray] in combat a new button is not reparented", bool(g.__same(charlie.parent, g.Minimap)))
    lua.execute('__combat = false; FireEvent("PLAYER_REGEN_ENABLED")')
    check("[tray] PLAYER_REGEN_ENABLED collects it", bool(g.__same(charlie.parent, g.Minimap.fsTray))
          and list(charlie.points.keys()) == ["TOPLEFT"])


def tray_failure_checks() -> None:
    w = WORLDS[0]

    # ---- F: a failing adopt step is logged, not swallowed, and the other steps still run
    lua, g, px = world(w, extra=LOGGING, tray=r"""
    BoomMinimapButton = CreateFrame("Button", "BoomMinimapButton", Minimap)
    BoomMinimapButton.SetMovable = function() error("movableboom") end
    """)
    logs = [str(g.__logs[i]) for i in range(1, len(g.__logs) + 1)]
    check("[tray] a failing adopt step is logged through LogTrayFailure",
          len(logs) == 1 and "movableboom" in logs[0] and logs[0].startswith("minimap_tray|"))
    check("[tray] a failing adopt step does not stop the rest (still in the drawer, counted)",
          bool(g.__same(g.BoomMinimapButton.parent, g.Minimap.fsTray)) and g.Minimap.fsTrayToggle.count.text == "1")

    # ---- G: a throw while building the toggle leaves no half-built key or drawer
    lua, g, px = world(w, extra=LOGGING + r"""
    local orig = FS.Theme.ApplyMono
    FS.Theme.ApplyMono = function(fontString, ...)
        if fontString.parent and fontString.parent.name == "ForeverSTUwaveMinimapTrayToggle" then error("toggleboom") end
        return orig(fontString, ...)
    end
    """)
    logs = [str(g.__logs[i]) for i in range(1, len(g.__logs) + 1)]
    toggle = g.ForeverSTUwaveMinimapTrayToggle
    e = geo(g.Minimap.w / px)
    check("[tray] a toggle build failure is logged", len(logs) == 1 and "toggleboom" in logs[0])
    check("[tray] a toggle build failure leaves Minimap.fsTray / fsTrayToggle unset",
          g.Minimap.fsTray is None and g.Minimap.fsTrayToggle is None)
    check("[tray] the half-built key is not left visible, and spends no slot (mail would take the fourth)",
          toggle is not None and toggle.shown is False)
    lua.execute("__mail_arrives()")
    check("[tray] ... mail takes the fourth slot after tracking, calendar and STU",
          near(g.MinimapCluster.IndicatorFrame.MailFrame.points.TOPLEFT.x / px, e["margin"] + 3 * e["pitch"]))

    # ---- H: drawer visibility in combat with a protected collected button waits for the regen
    lua, g, px = world(w, tray='__lib:Register("Prot", MakeObj("Prot"), {})\n__lib:Register("Plain", MakeObj("Plain"), {})')
    tray = g.Minimap.fsTray
    lua.execute("__lib.objects.Prot.protected = true; __combat = true")
    lua.execute("__click(Minimap.fsTrayToggle)")
    check("[tray] combat + protected button: the open click is deferred (drawer untouched)",
          tray.shown is False and g.ForeverSTUwaveDB.minimapTrayOpen is True)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED')")
    check("[tray] PLAYER_REGEN_ENABLED applies the deferred open (and the body follows)",
          tray.shown is True and bool(g.__same(g.Minimap.fsBody.points.BOTTOMRIGHT.rel, tray)))
    lua.execute("__combat = true; __click(Minimap.fsTrayToggle)")
    check("[tray] combat + protected button: the close click is deferred too", tray.shown is True)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED')")
    check("[tray] PLAYER_REGEN_ENABLED applies the deferred close", tray.shown is False
          and bool(g.__same(g.Minimap.fsBody.points.BOTTOMRIGHT.rel, g.Minimap.fsBezel)))
    lua.execute("__lib.objects.Prot.protected = false; __combat = true; __click(Minimap.fsTrayToggle)")
    check("[tray] combat with no protected button: the drawer toggles at once", tray.shown is True)
    lua.execute("__combat = false")


def mail_checks() -> None:
    """Mail arriving shows the mail key in the next free slot; the envelope sits centred on the glyph row at glyph width, the
    dot straddles the key's top-right corner, and both come and go with the frame."""
    for w in WORLDS[:2]:
        label = w[0]
        lua, g, px = world(w)
        e = geo(g.Minimap.w / px)
        lua.execute("__mail_arrives()")
        bezel = g.Minimap.fsBezel
        mail, icon = g.MinimapCluster.IndicatorFrame.MailFrame, g.MiniMapMailIcon

        def same(a, b):
            return bool(g.__same(a, b))

        dot_px = max(3, math.floor(KEY_DOT_SIZE * e["width"] / REF_MAP + 0.5))
        reach = KEY_DOT_REACH
        check(f"[mail@{label}] the key is parented in the bezel, shown, above the body and at the key size",
              same(mail.parent, bezel) and mail.shown is True and mail.level == bezel.level + 3
              and near(mail.w / px, e["keyW"]) and near(mail.h / px, e["keyH"]))
        check(f"[mail@{label}] the envelope is on the glyph row: anchored CENTER to the key's TOPLEFT at "
              f"({e['keyW'] / 2:g}, -{e['glyphY'] + e['glyph'] / 2:g}) px, {e['glyph']} px wide, 3/4 as tall",
              same(icon.parent, mail) and list(icon.points.keys()) == ["CENTER"]
              and same(icon.points.CENTER.rel, mail) and icon.points.CENTER.relPoint == "TOPLEFT"
              and near(icon.points.CENTER.x / px, e["keyW"] / 2)
              and near(icon.points.CENTER.y / px, -(e["glyphY"] + e["glyph"] / 2))
              and near(icon.w / px, e["glyph"]) and near(icon.h / px, math.floor(e["glyph"] * 3 / 4 + 0.5))
              and tint_is(icon, g.__Theme.COLOR_HEALTH, 1.0))
        dots = [r for r in regions(mail) if r.points.TOPRIGHT is not None and same(r.points.TOPRIGHT.rel, mail)]
        dot = dots[0] if len(dots) == 1 else None
        halos = [r for r in regions(mail) if dot is not None and r.points.CENTER is not None
                 and same(r.points.CENTER.rel, dot)]
        halo = halos[0] if len(halos) == 1 else None
        check(f"[mail@{label}] a notification dot and its halo exist: glow_round textures on the key",
              dot is not None and halo is not None and dot.texture == GLOW_ROUND and halo.texture == GLOW_ROUND)
        if dot is None or halo is None:
            continue
        check(f"[mail@{label}] the dot is round, {dot_px} px, anchored TOPRIGHT of the key at +{KEY_DOT_OFFSET},+{KEY_DOT_OFFSET} px, pink",
              near(dot.w / px, dot_px) and near(dot.h / px, dot_px)
              and near(dot.points.TOPRIGHT.x / px, KEY_DOT_OFFSET) and near(dot.points.TOPRIGHT.y / px, KEY_DOT_OFFSET)
              and tint_is(dot, g.__Theme.COLOR_HEALTH, 1.0))
        check(f"[mail@{label}] the halo is centred on the dot and reaches {reach} px past its edge",
              near(halo.w / px, dot_px + 2 * reach) and near(halo.points.CENTER.x, 0) and near(halo.points.CENTER.y, 0))
        # Mid animation (frame shown, envelope not yet): the dot is up and the envelope is not.
        check(f"[mail@{label}] while the arrival animation plays the dot shows alone, the envelope is not up yet",
              bool(g.__visible(dot)) and not bool(g.__visible(icon)))
        lua.execute("__mail_anim_finished()")
        check(f"[mail@{label}] the envelope shows once the animation finishes, with the dot still up",
              bool(g.__visible(icon)) and bool(g.__visible(dot)))
        lua.execute("__mail_hides()")
        check(f"[mail@{label}] hiding the frame hides the envelope and the dot together",
              not bool(g.__visible(icon)) and not bool(g.__visible(dot)) and not bool(g.__visible(halo)))
        lua.execute("__mail_arrives()")
        rank = lambda r: (LAYER_RANK.get(str(r.layer), -1), r.sublevel or 0)
        check(f"[mail@{label}] the dot sits above the envelope ({dot.layer}/{dot.sublevel} over {icon.layer}/{icon.sublevel}), "
              f"the halo below the dot", rank(dot) > rank(icon) and rank(halo) < rank(dot))


def coords_setup(x: float, y: float, secret: bool = False) -> str:
    """Seat a player map position (0-1 fractions) and a game clock before the addon loads, so the readout's first update at
    login formats them (the game clock is there to prove it is NOT shown). With secret=True the position's numbers are an
    opaque sentinel that throws on any arithmetic, and FS.IsSecret recognises it, like a secret number on a live client."""
    pos = "__SECRET, __SECRET" if secret else f"{x}, {y}"
    return f"""
__SECRET = setmetatable({{}}, {{ __mul = function() error("secret arithmetic", 2) end }})
FS.IsSecret = function(v) return v == __SECRET end
C_Map = {{
    GetBestMapForUnit = function() return 1 end,
    GetPlayerMapPosition = function() return {{ GetXY = function() return {pos} end }} end,
}}
function GetGameTime() return 19, 56 end
"""


# Every FontString the addon makes, in creation order (the permissive mock keeps none), and the colour each was given.
READOUT_LUA = r"""
local R = getmetatable(UIParent)
local create = R.CreateFontString
__fontstrings = {}
function R:CreateFontString(...)
    local fs = create(self, ...)
    __fontstrings[#__fontstrings + 1] = fs
    return fs
end
function R:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a } end
"""


def coords_checks() -> None:
    """The readout shows the player position as 'x, y' percentages, nothing else (no clock), as cyan mono text right aligned in
    the key row and fitted between the divider and the right margin. A fraction of 1.0 would format as '100.0' (12 glyphs,
    wider than the 10 the row is sized for), so each axis clamps to 99.9, and a secret position shows dashes instead of
    throwing."""
    cases = (
        ("(1.0, 1.0) clamps to 99.9, 99.9", 1.0, 1.0, False, "99.9, 99.9"),
        ("(0.9996, 1.5) rounds and clamps, never 100.0", 0.9996, 1.5, False, "99.9, 99.9"),
        ("(0.5, 0.25) is untouched", 0.5, 0.25, False, "50.0, 25.0"),
        ("a typical position (0.55, 0.414)", 0.55, 0.414, False, "55.0, 41.4"),
        ("a corner position (0.0, 0.05)", 0.0, 0.05, False, "0.0, 5.0"),
        ("a secret position shows dashes", 0, 0, True, "--.-, --.-"),
    )
    for w in WORLDS:
        label = w[0]
        for name, x, y, secret, want in cases:
            lua, g, px = world(w, extra=coords_setup(x, y, secret) + READOUT_LUA,
                               tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
            e = geo(g.Minimap.w / px)
            coords = g.Minimap.fsReadoutCoords
            check(f"[coords@{label}] {name}: reads {want!r}", (coords.text or "") == want)
            room = e["width"] - e["margin"] - (e["margin"] + 4 * e["pitch"] + 1 + e["keyGap"])
            need = len(coords.text) * MONO_ADVANCE * coords.fontSize / px
            check(f"[coords@{label}] {name}: {len(coords.text)} glyphs ({need:.1f} px) fit the {room} px between the "
                  f"divider and the margin", len(coords.text) <= READOUT_CHARS and need <= room + 1e-6)

    lua, g, px = world(WORLDS[0], extra=coords_setup(0.55, 0.414) + READOUT_LUA, tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
    fonts = [g.__fontstrings[i] for i in range(1, len(g.__fontstrings) + 1)]
    times = [str(f.text) for f in fonts if f.text and re.fullmatch(r"\d{1,2}:\d{2}(\s?[AP]M)?", str(f.text))]
    coords = g.Minimap.fsReadoutCoords
    check(f"[coords] there is no clock: no clock field, and no text reads like a time {times}",
          g.Minimap.fsReadoutClock is None and not times)
    check("[coords] there is no box: no readout box, and the coords are plain text on the body",
          g.Minimap.fsReadoutBox is None and bool(g.__same(coords.parent, g.Minimap.fsBody)))
    check("[coords] the coords are cyan mono text, justified right",
          all(near(coords.textColor[i + 1], (0.133, 0.878, 1.0)[i], 1e-3) for i in range(3)))
    check("[coords] nothing but the tray's drawer hangs under the bezel (one body, no row of its own)",
          sum(1 for f in g.allFrames.values() if f.points.TOPLEFT is not None
              and bool(g.__same(f.points.TOPLEFT.rel, g.Minimap.fsBezel)) and f.points.TOPLEFT.relPoint == "BOTTOMLEFT") == 1)


def rescale_checks() -> None:
    """A UI scale or resolution change moves the pixel: a rescale pass seats every key, the divider, the coords and the
    body's pieces on the new pixel grid again (nothing is cached across it)."""
    lua, g, px = world(WORLDS[1], tray='__lib:Register("Alpha", MakeObj("Alpha"), {})')
    old = g.Minimap.fsBezel.h
    px2 = 768 / 1080
    lua.execute(f"PixelUtil = {{ GetPixelToUIUnitFactor = function() return {px2!r} end }}; __rescale()")
    e = geo(g.Minimap.w / px2)
    bezel = g.Minimap.fsBezel
    keys = [g.MinimapCluster.Tracking, g.GameTimeFrame, g.Minimap.fsSTUKey, g.Minimap.fsTrayToggle]
    check(f"[rescale] the row is re-seated on the new pixel ({bezel.h / px2:g} px tall, was {old / px:g} px)",
          bezel.h != old and near(bezel.h / px2, e["row"]) and whole(bezel.h, px2))
    check("[rescale] every key is re-seated on the new pixel grid at the new spacing",
          all(near(k.points.TOPLEFT.x / px2, e["margin"] + i * e["pitch"])
              and near(k.w / px2, e["toggleW"] if i == 3 else e["keyW"])
              and whole(k.points.TOPLEFT.x, px2) and whole(k.w, px2) and whole(k.h, px2) for i, k in enumerate(keys)))
    lua.execute("__combat = true; PixelUtil = { GetPixelToUIUnitFactor = function() return 1 end }; __rescale(); __combat = false")
    e1 = geo(g.Minimap.w)
    check("[rescale] a rescale in combat seats the (unprotected) row at once too, back on the first pixel size",
          near(bezel.h, e1["row"]) and near(keys[0].points.TOPLEFT.x, e1["margin"]))


# A geometry world for the Edit Mode seat checks. The permissive mock above answers 0 for every
# rect, so the compensation never measures anything there; this one resolves single-anchor frames
# into UIParent coordinates (offsets and sizes scaled by the frame's effective scale), and shapes
# MinimapCluster like the 12.1 source:
#   * a ResizeLayoutFrame (Minimap.xml:3): any Layout pass (the synchronous one in
#     EditModeMinimapSystemMixin:UpdateSystemSettingHeaderUnderneath, or the deferred OnUpdate one a
#     MarkDirty arms) resets its size to the children's extents, overriding the SetSize
#     FS.Layout.Apply wrote;
#   * MinimapContainer (parentKey) anchored TOP of the cluster at (10, -30), the Minimap CENTERed in
#     it, so the map hangs from the cluster's TOP edge and its centre column, not from its middle;
#   * an Edit Mode system: InitSystemAnchors parks it TOPLEFT 0,0, UpdateSystem runs
#     ApplySystemAnchor, then the Size setting (SetEditModeScale on the container) and
#     SetHeaderUnderneath (re-anchors the container, then Layout()).
# EditModeManagerFrame:UpdateLayoutInfo is that sequence; Layout.lua hooks it at load.
LAYOUT_W, LAYOUT_H = 256, 270   # what a Layout pass leaves the cluster at (children's extents)

GEO_SETUP = r"""
ForeverSTUwaveDB = {}
local now = 100
function GetTime() now = now + 0.25; return now end
local R = getmetatable(UIParent)
UIParent.w = UIParent.h * 16 / 9
local LAYOUT_W, LAYOUT_H = %(lw)d, %(lh)d
local FRAC = { TOPLEFT = { 0, 1 }, TOP = { .5, 1 }, TOPRIGHT = { 1, 1 }, LEFT = { 0, .5 },
    CENTER = { .5, .5 }, RIGHT = { 1, .5 }, BOTTOMLEFT = { 0, 0 }, BOTTOM = { .5, 0 }, BOTTOMRIGHT = { 1, 0 } }
local function escale(f)
    local s = 1
    while f and f ~= UIParent do s = s * (f.scale or 1); f = f.parent end
    return s
end
local function rect(f)
    if f == UIParent then return 0, 0, UIParent.w, UIParent.h end
    local es = escale(f)
    local w, h = f.w * es, f.h * es
    local point, p = next(f.points)
    if not p then return 0, 0, w, h end
    local rl, rb, rw, rh = rect(p.rel or f.parent or UIParent)
    local rf = FRAC[p.relPoint or point]
    local ff = FRAC[point]
    local x, y = rl + rf[1] * rw + p.x * es, rb + rf[2] * rh + p.y * es
    return x - ff[1] * w, y - ff[2] * h, w, h
end
-- Like the client, GetLeft/GetTop/... answer in the frame's OWN scale space (screen units divided
-- by its effective scale): the Minimap inside a container scaled by Edit Mode's Size setting reads
-- bigger numbers than the unscaled cluster for the same screen position. __rect stays absolute.
function R:GetEffectiveScale() return escale(self) end
function R:GetLeft() local l = rect(self); return l / escale(self) end
function R:GetBottom() local _, b = rect(self); return b / escale(self) end
function R:GetRight() local l, _, w = rect(self); return (l + w) / escale(self) end
function R:GetTop() local _, b, _, h = rect(self); return (b + h) / escale(self) end
function R:GetCenter() local l, b, w, h = rect(self); local s = escale(self); return (l + w / 2) / s, (b + h / 2) / s end
function R:GetPoint(i)
    local point, p = next(self.points)
    if not p then return end
    return point, p.rel or self.parent, p.relPoint or point, p.x, p.y
end
function R:IsClampedToScreen() return self.clamped and true or false end
function R:SetClampedToScreen(v) self.clamped = v and true or false end
__rect = rect

local container = CreateFrame("Frame", nil, MinimapCluster)
container.w, container.h = 215, 226
container:SetPoint("TOP", MinimapCluster, "TOP", 10, -30)
MinimapCluster:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
MinimapCluster.MinimapContainer = container
Minimap:SetParent(container)
Minimap.w, Minimap.h = 198, 198
Minimap:SetPoint("CENTER", container, "CENTER", 0, 0)
MinimapCluster.w, MinimapCluster.h = LAYOUT_W, LAYOUT_H
MinimapCluster.clamped = true                       -- EditModeSystemTemplate clampedToScreen="true"

function MinimapCluster:Layout() self.w, self.h = LAYOUT_W, LAYOUT_H; self.dirty = false; __layouts = (__layouts or 0) + 1 end
function MinimapCluster:MarkDirty() self.dirty = true end
function MinimapCluster:SetEditModeScale(s) container.scale = s end
-- Blizzard_Minimap/Mainline/Minimap.lua SetHeaderUnderneath: Header Underneath hangs the container
-- from the cluster's BOTTOM edge (10, 30) instead of its TOP edge (10, -30), both /scale.
function MinimapCluster:SetHeaderUnderneath(under)
    local s = container.scale or 1
    container:ClearAllPoints()
    if under then
        container:SetPoint("BOTTOM", self, "BOTTOM", 10 / s, 30 / s)
    else
        container:SetPoint("TOP", self, "TOP", 10 / s, -30 / s)
    end
end
-- Edit Mode system frames keep the originals as *Base and override SetPoint/ClearAllPoints.
MinimapCluster.SetPointBase, MinimapCluster.ClearAllPointsBase = R.SetPoint, R.ClearAllPoints
function MinimapCluster:SetPoint(...) __dirtyFlagWrites = (__dirtyFlagWrites or 0) + 1; return R.SetPoint(self, ...) end
function MinimapCluster:ApplySystemAnchor()
    R.ClearAllPoints(self); R.SetPoint(self, "TOPRIGHT", UIParent, "TOPRIGHT", 0, 0)
end
__editScale = 1
__header = false
function MinimapCluster:UpdateSystem()
    self:ApplySystemAnchor()
    self:SetEditModeScale(__editScale)
    self:SetHeaderUnderneath(__header or false)
    self:Layout()
end
function MinimapCluster:GetNumPoints() return 1 end

EditModeManagerFrame = CreateFrame("Frame", "EditModeManagerFrame", UIParent)
function EditModeManagerFrame:UpdateLayoutInfo()
    R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    MinimapCluster:UpdateSystem()
end

-- One client frame. Whether the deferred Layout OnUpdate or a C_Timer.After(0) timer runs first in
-- a frame is the engine's business, so every sequence is driven in both orders.
function __frame(layoutFirst)
    local function layout() if MinimapCluster.dirty then MinimapCluster:Layout() end end
    if layoutFirst then layout(); RunTimers() else RunTimers(); layout() end
end
function __frames(n, layoutFirst) for _ = 1, n do __frame(layoutFirst) end end

-- The map's expected edges for the layout entry: top and left from the entry, in UIParent coords.
function __want()
    local L, s = FS.Layout.minimap, FS.Layout.Scale()
    local left = UIParent.w / 2 + L.x * s - L.w * s / 2
    return UIParent.h / 2 + L.y * s + L.h * s / 2, left, left + L.w * s
end
function __got()
    local l, b, w, h = rect(Minimap)
    return b + h, l, l + w
end
"""


def geo_world(setup_extra: str = "") -> "LuaRuntime":
    setup = GEO_SETUP % {"lw": LAYOUT_W, "lh": LAYOUT_H} + setup_extra
    return run("cut", 1200, setup, None, login=False)


def first_login_checks() -> None:
    """A new character's first login: the seat at PLAYER_LOGIN is right, then the server's
    EDIT_MODE_LAYOUTS_UPDATED runs EditModeManagerFrame:UpdateLayoutInfo, which parks MinimapCluster
    at TOPLEFT 0,0, re-applies its system anchor, its Size (the container scale) and its header
    (re-anchoring the container and running a Layout pass that resets the cluster's size to its
    children's extents), and a later dirty-triggered Layout pass can land after our re-seat. The
    visible MAP must end up at FS.Layout.minimap's top and left (and right at scale 1) in every
    ordering, and again after a /reload-style sequence."""
    tol = 0.01

    def at_target(g, scale_one: bool) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f} right {gr:.2f}/{wr:.2f}"

    for order in (False, True):
        o = "layout-first" if order else "timers-first"
        flag = "true" if order else "false"
        # --- first login: seat, settle, then the server's layout update, then Blizzard dirties it
        lua = geo_world()
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] map on target after the PLAYER_LOGIN seat ({msg})", ok)
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo()")
        lua.execute("MinimapCluster:MarkDirty()")   # Blizzard dirties the cluster after our hook
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] map on target after UpdateLayoutInfo + a later Layout pass ({msg})", ok)
        # a Layout pass that lands after our last re-seat (Blizzard dirties the cluster again)
        lua.execute("MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[first login {o}] the cluster really was re-laid out after our seat (size "
              f"{g.MinimapCluster.h:g} = children's extents {LAYOUT_H}) and the map is still on target ({msg})",
              g.MinimapCluster.h == LAYOUT_H and ok)

        # --- a Size change (container scale 1.2) arriving later moves the map's edges, not its anchor
        lua.execute("__editScale = 1.2; MinimapCluster:SetEditModeScale(1.2); MinimapCluster:SetHeaderUnderneath(false)")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, False)
        check(f"[first login {o}] map top and left on target after a later Edit Mode Size change ({msg})", ok)

        # --- the whole first-login sequence with a non-default Size
        lua = geo_world("__editScale = 1.2")
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(3, {flag})")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, False)
        check(f"[first login {o}] Size 120: map top and left on target ({msg})", ok)

        # --- /reload: Edit Mode already applied (and the layout settled) before the addon loads
        lua = geo_world("EditModeManagerFrame:UpdateLayoutInfo()")
        g = lua.globals()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute(f"__frames(4, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map on target after the PLAYER_LOGIN seat ({msg})", ok)
        lua.execute("MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map still on target after a later Layout pass ({msg})", ok)
        lua.execute('FireEvent("PLAYER_ENTERING_WORLD", false, true)')
        lua.execute(f"__frames(3, {flag})")
        ok, msg = at_target(g, True)
        check(f"[reload {o}] map on target after PLAYER_ENTERING_WORLD ({msg})", ok)

    # --- no double compensation: re-running the compensation does not move the cluster twice
    lua = geo_world()
    g = lua.globals()
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    lua.execute("__p0 = { MinimapCluster:GetPoint() }")
    before = list(lua.eval("__p0").values())
    lua.execute(r"""
        for _ = 1, 3 do
            for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end
            __frames(2, false)
        end
        __p1 = { MinimapCluster:GetPoint() }
    """)
    after = list(lua.eval("__p1").values())
    same_anchor = (before[0], before[2]) == (after[0], after[2]) and all(
        abs(float(a) - float(b)) < 1e-6 for a, b in zip(before[3:], after[3:]))
    ok, msg = at_target(g, True)
    check(f"[idempotent] three more compensation passes leave the cluster anchor unchanged "
          f"({before[0]} {before[3]:.3f},{before[4]:.3f} -> {after[0]} {after[3]:.3f},{after[4]:.3f})", same_anchor)
    check(f"[idempotent] and the map on target ({msg})", ok)
    # a UI scale change re-Applies the raw seat, then the compensation puts the correction back once
    lua.execute("UIParent.h = 1080; UIParent.w = 1080 * 16 / 9; FireEvent('UI_SCALE_CHANGED'); __frames(3, false)")
    ok, msg = at_target(g, False)
    check(f"[idempotent] a UI scale change re-seats and the map is on target again ({msg})", ok)
    check("[clamp] screen clamping stays off on the cluster after the sequence",
          not g.MinimapCluster.IsClampedToScreen(g.MinimapCluster))


def trigger_checks() -> None:
    """Each thing Blizzard can do to the cluster after our seat, ALONE (no other hook rescues it),
    must end with the map back on target; plus the combat hold and the one-timer coalescing."""
    tol = 0.01

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    def seated():
        lua = geo_world()
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    # The container scale alone (Edit Mode's Size setting), then the header alone.
    lua, g = seated()
    lua.execute("__editScale = 1.2; MinimapCluster:SetEditModeScale(1.2)")
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g)
    check(f"[trigger] SetEditModeScale alone re-compensates ({msg})", ok)
    lua, g = seated()
    lua.execute("MinimapCluster:SetHeaderUnderneath(true)")
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] SetHeaderUnderneath alone re-compensates ({msg})", ok)

    # ApplySystemAnchor reached without UpdateLayoutInfo (Reset to default position) re-seats a frame later.
    lua, g = seated()
    lua.execute("MinimapCluster:ApplySystemAnchor()")
    wrong = not on_target(g, True)[0]
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] ApplySystemAnchor alone: the cluster really moved, then is re-seated ({msg})", wrong and ok)

    # Blizzard moves the cluster AFTER UpdateLayoutInfo returned (its callers' later steps), through
    # the Base call so no hooked method runs: our own post-hook and the event watcher re-seat a frame later.
    for how, fire in (("UpdateLayoutInfo hook", "EditModeManagerFrame:UpdateLayoutInfo()"),
                      ("EDIT_MODE_LAYOUTS_UPDATED", 'FireEvent("EDIT_MODE_LAYOUTS_UPDATED")')):
        lua, g = seated()
        lua.execute(fire)
        lua.execute("""local R = getmetatable(UIParent)
            R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)""")
        wrong = not on_target(g, True)[0]
        lua.execute("__frames(3, false)")
        ok, msg = on_target(g, True)
        check(f"[trigger] a move after {how} returned is re-seated a frame later ({msg})", wrong and ok)

    # The first PLAYER_ENTERING_WORLD of a login re-seats; a zone change does not.
    lua, g = seated()
    lua.execute("""local R = getmetatable(UIParent)
        R.ClearAllPoints(MinimapCluster); R.SetPoint(MinimapCluster, "TOPLEFT", UIParent, "TOPLEFT", 0, 0)""")
    lua.execute('FireEvent("PLAYER_ENTERING_WORLD", true, false)')
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] PLAYER_ENTERING_WORLD of a login re-seats ({msg})", ok)
    lua, g = seated()
    lua.execute('FireEvent("PLAYER_ENTERING_WORLD", false, false)')
    lua.execute("__frames(3, false)")
    seen = lua.eval('(function() for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                    'if e.ev == "PLAYER_ENTERING_WORLD" or e.ev == "reseat" then return true end end return false end)()')
    check("[trigger] a zone-change PLAYER_ENTERING_WORLD does not re-seat", not seen)

    # Combat: a protected cluster is not touched (no SetPoint), and the seat lands when combat ends.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __writes = 0
        local base = MinimapCluster.SetPointBase
        MinimapCluster.SetPointBase = function(...) __writes = __writes + 1; return base(...) end
        __combat = true
        EditModeManagerFrame:UpdateLayoutInfo()
        __frames(3, false)
    """)
    held = lua.eval("__writes") == 0
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[trigger] a protected cluster is left alone in combat and re-seated when it ends "
          f"(writes in combat held: {held}; {msg})", held and ok)

    # Many hook calls in one frame arm one timer, not one each.
    lua, g = seated()
    lua.execute("__timers = {}; for _ = 1, 6 do MinimapCluster:SetEditModeScale(1) end")
    n = lua.eval("#__timers")
    check(f"[trigger] six SetEditModeScale calls in a frame arm one compensation timer (got {n})", n == 1)
    lua.execute("__timers = {}; for _ = 1, 6 do MinimapCluster:ApplySystemAnchor() end")
    n = lua.eval("#__timers")
    check(f"[trigger] six ApplySystemAnchor calls in a frame arm one re-seat timer (got {n})", n == 1)


def review_checks() -> None:
    """Held compensation, Header Underneath, scale spaces, the log's session handling, hook retry."""
    tol = 0.01

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    def seated(extra: str = ""):
        lua = geo_world(extra)
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    # --- a compensation refused in combat is finished at regen, and compensation works afterwards
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        __editScale = 1.2
        MinimapCluster:SetEditModeScale(1.2)
        __frames(3, false)
    """)
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[held] SetEditModeScale in combat, then regen: the map lands on target ({msg})", ok)
    lua.execute("__header = true; MinimapCluster:SetHeaderUnderneath(true); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[held] and a later SetHeaderUnderneath is still compensated (the pending flag was released) ({msg})", ok)

    # --- Header Underneath hangs the map from the cluster's BOTTOM: still on target, still idempotent
    for order in (False, True):
        o = "layout-first" if order else "timers-first"
        flag = "true" if order else "false"
        lua, g = seated("__header = true")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = on_target(g, True)
        check(f"[header under {o}] first login: map on target after UpdateLayoutInfo + a Layout pass ({msg})", ok)
        lua.execute("__p0 = { MinimapCluster:GetPoint() }")
        lua.execute(f"MinimapCluster:MarkDirty(); __frames(3, {flag})")
        lua.execute("""
            for _ = 1, 3 do for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end; __frames(2, false) end
            __p1 = { MinimapCluster:GetPoint() }
        """)
        before, after = list(lua.eval("__p0").values()), list(lua.eval("__p1").values())
        same = before[0] == after[0] and all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(before[3:], after[3:]))
        ok, msg = on_target(g, True)
        check(f"[header under {o}] a later Layout pass and three more compensations leave the anchor "
              f"({before[0]}) and the map unchanged ({msg})", same and ok)
        lua, g = seated("__header = true; __editScale = 1.2")
        lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); MinimapCluster:MarkDirty()")
        lua.execute(f"__frames(4, {flag})")
        ok, msg = on_target(g)
        check(f"[header under {o}] Size 120: map top and left on target ({msg})", ok)

    # --- the idempotent pass writes nothing: no anchor write at all
    lua, g = seated()
    lua.execute("""
        __writes = 0
        local base, clear = MinimapCluster.SetPointBase, MinimapCluster.ClearAllPointsBase
        MinimapCluster.SetPointBase = function(...) __writes = __writes + 1; return base(...) end
        MinimapCluster.ClearAllPointsBase = function(...) __writes = __writes + 1; return clear(...) end
        for _ = 1, 4 do for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end; __frames(2, false) end
        MinimapCluster:SetEditModeScale(1); __frames(2, false)
    """)
    check("[idempotent] a compensation that finds the anchor already right writes nothing (no clear, no set)",
          lua.eval("__writes") == 0)
    lua.execute("""
        __writes = 0
        MinimapCluster:MarkDirty(); __frames(3, false)   -- a Layout pass moves nothing: still no write
    """)
    check("[idempotent] and a later Layout pass needs no write either", lua.eval("__writes") == 0)

    # --- GetTop/GetLeft are in each frame's own scale space (the map sits at container scale 1.2)
    lua, g = seated("__editScale = 1.2")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    ok, msg = on_target(g)
    scale_space = abs(float(lua.eval("Minimap:GetLeft() - select(1, __rect(Minimap))")) ) > 1
    check(f"[scale spaces] the mock really answers in frame space at Size 120, and the map is on target ({msg})",
          scale_space and ok)

    # --- the log: this session starts with the PLAYER_LOGIN rescale pass, the previous one is untouched
    lua = geo_world('ForeverSTUwaveDB.minimapSeatLog = { { ev = "old1" }, { ev = "old2" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    prev = lua.eval('(function() local t = {} for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLogPrev or {}) do '
                    't[#t + 1] = e.ev end return table.concat(t, ",") end)()')
    check(f"[seat log] the PLAYER_LOGIN rescale pass lands in this session's log, the previous log stays "
          f"exactly as it was ({prev})", prev == "old1,old2"
          and lua.eval("ForeverSTUwaveDB.minimapSeatLog[1].ev") == "rescale:PLAYER_LOGIN")

    # --- minimapSeatLogFirst: filled only when no log existed, never rotated or overwritten
    lua = geo_world()
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    check("[first slot] the first session ever logged fills minimapSeatLogFirst (it holds the login sequence)",
          lua.eval('(function() local f = ForeverSTUwaveDB.minimapSeatLogFirst; if not f then return false end '
                   'for _, e in ipairs(f) do if e.ev == "UpdateLayoutInfo" then return true end end return false end)()'))
    lua = geo_world('ForeverSTUwaveDB.minimapSeatLogFirst = { { ev = "first1" } }; '
                    'ForeverSTUwaveDB.minimapSeatLog = { { ev = "second" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    lua.execute("for i = 1, 40 do UIParent.h = 1200 + i; FireEvent('EDIT_MODE_LAYOUTS_UPDATED'); __frames(2, false) end")
    check("[first slot] later sessions leave it alone however much they log, and the previous session rotates as before",
          lua.eval("#(ForeverSTUwaveDB.minimapSeatLogFirst or {})") == 1
          and lua.eval("(ForeverSTUwaveDB.minimapSeatLogFirst[1] or {}).ev") == "first1"
          and lua.eval("((ForeverSTUwaveDB.minimapSeatLogPrev or {})[1] or {}).ev") == "second")
    lua = geo_world('ForeverSTUwaveDB.minimapSeatLog = { { ev = "old" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")'); lua.execute("__frames(3, false)")
    check("[first slot] a session that finds a log from before does not fill it",
          lua.eval("ForeverSTUwaveDB.minimapSeatLogFirst") is None)

    # --- hooks: a missing method is skipped, the log says which exist, the retry installs it later
    lua, g = seated("__asa = MinimapCluster.ApplySystemAnchor; MinimapCluster.ApplySystemAnchor = nil")
    hk = lua.eval('(function() for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                  'if e.ev == "hooks" then return e.hk end end end)()')
    check(f"[hooks] a client without ApplySystemAnchor installs the others and logs which ({hk})", hk == "SHU")
    lua.execute("MinimapCluster.ApplySystemAnchor = __asa; FireEvent('ADDON_LOADED', 'Blizzard_EditMode')")
    hk2 = lua.eval('(function() local last; for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                   'if e.ev == "hooks" then last = e.hk end end return last end)()')
    lua.execute("MinimapCluster:ApplySystemAnchor()")
    wrong = not on_target(g, True)[0]
    lua.execute("__frames(3, false)")
    ok, msg = on_target(g, True)
    check(f"[hooks] a method that appears when Blizzard_EditMode loads is hooked then ({hk2}); "
          f"the Reset path is re-seated ({msg})", hk2 == "SHAU" and wrong and ok)
    lua, g = seated()
    hk = lua.eval('(function() for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                  'if e.ev == "hooks" then return e.hk end end end)()')
    check(f"[hooks] a full client logs all four hooks installed ({hk})", hk == "SHAU")


def mutation_gap_checks() -> None:
    """Behaviours the first mutation pass left unpinned: the cluster's own scale, the regen
    replay of a held re-seat, the raw seat between a re-seat and its compensation, the log's
    dedupe of two hook installs, and the log's scale space."""
    tol = 0.01

    def seated(extra: str = ""):
        lua = geo_world(extra)
        lua.execute('FireEvent("PLAYER_LOGIN")')
        lua.execute("__frames(3, false)")
        return lua, lua.globals()

    def on_target(g, scale_one: bool = False) -> tuple[bool, str]:
        wt, wl, wr = g.__want()
        gt, gl, gr = g.__got()
        ok = abs(gt - wt) < tol and abs(gl - wl) < tol and (not scale_one or abs(gr - wr) < tol)
        return ok, f"top {gt:.2f}/{wt:.2f} left {gl:.2f}/{wl:.2f}"

    # A cluster whose own scale is not UIParent's: SetPoint offsets are in the cluster's space.
    lua, g = seated("MinimapCluster.scale = 0.8")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    ok, msg = on_target(g)
    check(f"[cluster scale] a cluster scaled 0.8 still puts the map on target ({msg})", ok)

    # A re-seat refused in combat (only ApplySystemAnchor ran, no scale or header hook to rescue it)
    # is replayed at regen.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        MinimapCluster:ApplySystemAnchor()
        __frames(3, false)
    """)
    wrong = not on_target(g, True)[0]
    lua.execute("__combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)")
    ok, msg = on_target(g, True)
    check(f"[regen] a re-seat refused in combat is done at regen (it was off target: {wrong}; {msg})", wrong and ok)

    # The held compensation is released at regen: a second regen arms nothing.
    lua, g = seated()
    lua.execute("""
        MinimapCluster.IsProtected = function() return true end
        __combat = true
        MinimapCluster:SetEditModeScale(1.2)
        __frames(3, false)
        __combat = false; FireEvent('PLAYER_REGEN_ENABLED'); __frames(4, false)
        __timers = {}
        FireEvent('PLAYER_REGEN_ENABLED')
    """)
    n = lua.eval("#__timers")
    check(f"[regen] a second regen after the held compensation finished arms no timer (got {n})", n == 0)

    # A re-seat shows the map where it belongs at once: the cluster is written once, with the
    # inset measured before, so no rendered frame sees the raw layout seat (the map ~38 units off).
    lua, g = seated()
    lua.execute("""
        MinimapCluster:ApplySystemAnchor()
        local timers = __timers; __timers = {}
        for _, fn in ipairs(timers) do fn() end       -- only the re-seat timer, not the compensation it arms
        __armed = #__timers
    """)
    ok, msg = on_target(g, True)
    check(f"[reseat] the map is on target as soon as the re-seat ran, with a compensation still armed "
          f"({msg}, armed {lua.eval('__armed')})", ok and lua.eval("__armed") == 1)

    # Per rendered frame: after the first seat, none of the events that re-seat the cluster shows the
    # map off target for even one frame (sampled right after the event and after every client frame).
    for size_label, extra in (("Size 100", ""), ("Size 120", "__editScale = 1.2"),
                              ("Header Underneath", "__header = true")):
        for ev_label, ev in (("reload PLAYER_ENTERING_WORLD", 'FireEvent("PLAYER_ENTERING_WORLD", false, true)'),
                             ("EDIT_MODE_LAYOUTS_UPDATED", 'FireEvent("EDIT_MODE_LAYOUTS_UPDATED")'),
                             ("UpdateLayoutInfo", "EditModeManagerFrame:UpdateLayoutInfo()")):
            for layout_first in ("false", "true"):
                lua = geo_world(extra + "; EditModeManagerFrame:UpdateLayoutInfo()")
                g = lua.globals()
                lua.execute('FireEvent("PLAYER_LOGIN")')
                lua.execute(f"__frames(5, {layout_first})")
                lua.execute(ev)
                devs = []
                for _ in range(4):
                    devs.append(abs(g.__got()[0] - g.__want()[0]))
                    lua.execute(f"__frame({layout_first})")
                check(f"[no jump] {size_label}, {ev_label}, layout {'first' if layout_first == 'true' else 'last'}: "
                      f"no rendered frame is off target (worst {max(devs):.2f})", max(devs) < tol)

    # Two hook-install entries in a row are two entries, not a repeat.
    lua = geo_world("__asa = MinimapCluster.ApplySystemAnchor; MinimapCluster.ApplySystemAnchor = nil")
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("MinimapCluster.ApplySystemAnchor = __asa; FireEvent('ADDON_LOADED', 'Blizzard_EditMode')")
    hks = lua.eval('(function() local t = {} for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                   'if e.ev == "hooks" then t[#t + 1] = e.hk end end return table.concat(t, ",") end)()')
    check(f"[seat log] a late hook install right after the first is its own entry ({hks})", hks == "SHU,SHAU")

    # The log's map readings are in the same space as its targets (UIParent units) at Size 120.
    lua, g = seated("__editScale = 1.2")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(4, false)")
    d = lua.eval('(function() local last; for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                 'if e.ev == "compensate" then last = e end end '
                 'return { mt = last.mt, tt = last.tt, ml = last.ml, tl = last.tl } end)()')
    ok = (None not in (d["mt"], d["tt"], d["ml"], d["tl"])
          and abs(float(d["mt"]) - float(d["tt"])) < 0.2 and abs(float(d["ml"]) - float(d["tl"])) < 0.2)
    check(f"[seat log] at Size 120 the logged map edges match the logged targets "
          f"(mt {d['mt']} tt {d['tt']}, ml {d['ml']} tl {d['tl']})", ok)


def seat_log_checks() -> None:
    """ForeverSTUwaveDB.minimapSeatLog: what /fsbug shows when the minimap is seated wrong."""
    lua = geo_world()
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("EditModeManagerFrame:UpdateLayoutInfo(); __frames(3, false)")
    lua.execute("""
        local evs, fields = {}, true
        for i, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do
            evs[#evs + 1] = e.ev
            for _, k in ipairs({ "ev", "t", "pt", "x", "y", "mt", "ml", "tt", "tl", "sc", "clamp" }) do
                if e[k] == nil then fields = false end
            end
            for k, v in pairs(e) do
                local t = type(v)
                if t ~= "number" and t ~= "string" and t ~= "boolean" then fields = false end
            end
        end
        __seatEvs, __seatFields = table.concat(evs, ","), fields
    """)
    evs = str(lua.eval("__seatEvs"))
    check(f"[seat log] the login sequence is logged in order ({evs})",
          evs.startswith("rescale:PLAYER_LOGIN,seat,hooks,") and ",UpdateLayoutInfo," in evs and "compensate" in evs
          and "rescale:UpdateLayoutInfo" in evs)
    lua.execute('FireEvent("EDIT_MODE_LAYOUTS_UPDATED"); __frames(2, false)')
    check("[seat log] the server's EDIT_MODE_LAYOUTS_UPDATED is logged, so its order against our seat can be read",
          bool(lua.eval('(function() for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do '
                        'if e.ev == "EDIT_MODE_LAYOUTS_UPDATED" then return true end end return false end)()')))
    check("[seat log] every entry carries event, time, cluster point and offsets, map top and left, "
          "layout target, scale and clamp, as plain numbers, strings or booleans", bool(lua.eval("__seatFields")))
    check("[seat log] the cluster's clamp is logged as off after the compensation",
          bool(lua.eval("ForeverSTUwaveDB.minimapSeatLog[#ForeverSTUwaveDB.minimapSeatLog].clamp == false")))

    # --- 20 entries, the first 10 pinned, a repeat counts up instead of taking a slot
    lua.execute("""
        for i = 1, 4 do                                   -- pad the login sequence past 10 entries
            UIParent.h = 1200 - i; UIParent.w = UIParent.h * 16 / 9
            FireEvent("EDIT_MODE_LAYOUTS_UPDATED"); __frames(2, false)
        end
        __first10 = {}
        for i = 1, 10 do __first10[i] = ForeverSTUwaveDB.minimapSeatLog[i].ev .. ":" .. ForeverSTUwaveDB.minimapSeatLog[i].t end
        local n0 = #ForeverSTUwaveDB.minimapSeatLog
        for i = 1, 60 do
            UIParent.h = 1200 + i                       -- a different state every time
            UIParent.w = UIParent.h * 16 / 9
            FireEvent("EDIT_MODE_LAYOUTS_UPDATED")
            __frames(2, false)
        end
        __logN = #ForeverSTUwaveDB.minimapSeatLog
        __pinned = true
        for i = 1, 10 do
            local e = ForeverSTUwaveDB.minimapSeatLog[i]
            if e.ev .. ":" .. e.t ~= __first10[i] then __pinned = false end
        end
    """)
    check(f"[seat log] capped at 20 entries ({lua.eval('__logN')})", lua.eval("__logN") == 20)
    check("[seat log] the first 10 entries (the login sequence) stay pinned", bool(lua.eval("__pinned")))
    lua.execute("""
        local before = #ForeverSTUwaveDB.minimapSeatLog
        for _ = 1, 5 do FS.Layout.rescaleWhy = "repeat"; for _, fn in ipairs(FS.Layout._rescaleCallbacks) do pcall(fn) end end
        FS.Layout.rescaleWhy = nil
        local last = ForeverSTUwaveDB.minimapSeatLog[#ForeverSTUwaveDB.minimapSeatLog]
        __repeatN, __repeatGrew = last.n, #ForeverSTUwaveDB.minimapSeatLog > before + 1
    """)
    check(f"[seat log] the same state repeated counts up (n={lua.eval('__repeatN')}) instead of taking slots",
          lua.eval("__repeatN") == 5 and not lua.eval("__repeatGrew"))

    # --- the previous session is kept, the new one starts empty
    lua = geo_world('ForeverSTUwaveDB.minimapSeatLog = { { ev = "old session" } }')
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    check("[seat log] the previous session's log is kept as minimapSeatLogPrev",
          lua.eval("((ForeverSTUwaveDB.minimapSeatLogPrev or {})[1] or {}).ev") == "old session")
    check("[seat log] and this session starts a fresh log",
          lua.eval("ForeverSTUwaveDB.minimapSeatLog[1].ev") == "rescale:PLAYER_LOGIN")

    # --- a secret reading never lands in the log or breaks the seat
    lua = geo_world("""
        FS.IsSecret = function(v) return v == __secret end
        __secret = 12345.5
        local R2 = getmetatable(UIParent)
        local orig = R2.GetLeft
        R2.GetLeft = function(self) if self == Minimap then return __secret end return orig(self) end
    """)
    lua.execute('FireEvent("PLAYER_LOGIN")')
    lua.execute("__frames(3, false)")
    lua.execute("""
        __secretLeaked = false
        for _, e in ipairs(ForeverSTUwaveDB.minimapSeatLog) do
            for _, v in pairs(e) do if v == __secret then __secretLeaked = true end end
        end
    """)
    check("[seat log] a secret map reading is dropped, never stored, and does not throw",
          not lua.eval("__secretLeaked") and lua.eval("#ForeverSTUwaveDB.minimapSeatLog") > 0)



def main() -> int:
    body_checks()
    spacing_checks()
    row_checks()
    hover_checks()
    tray_checks()
    tray_failure_checks()
    mail_checks()
    coords_checks()
    rescale_checks()
    first_login_checks()
    trigger_checks()
    review_checks()
    mutation_gap_checks()
    seat_log_checks()
    print("failures:", failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
