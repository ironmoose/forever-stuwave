#!/usr/bin/env python3
"""Runs the real shared controls kit (Core/ControlKit.lua and the control skins after it) headless against mock Blizzard widgets.

The mock is a small widget engine with a real anchor solver: SetPoint, SetAllPoints and SetSize are resolved to rectangles, so
every margin and size of the shared controls mockup (mockups/shared-controls-2026-11-12.html) is measured in physical pixels
(1.2 px per UI unit, the player's display, and again at other scales) instead of eyeballed. Blizzard's widgets are built
from the shapes of the 12.1.0 Blizzard_SharedXML templates; their SetScript and SetAttribute throw, so a skin that writes
either fails a check. The real Theme.lua, Layout.lua, HeldArt.lua, ControlKit.lua, the skins and PanelSkins.lua are loaded;
only the engine is mocked.

Pinned here, per control family (each family adds its own checks as it lands):

  * checkbox and radio: the 16 px plate centred on whole pixels in a stock rect that keeps its size, the six states of the
    mockup (face, edge colour and width, LED, mark), the tick drawn in over 0.54 s, the breathing LED, the ring pulse, the
    rail and the node's jump, the label restyle, held Blizzard art, detection by shape (action buttons, list rows and
    other widgets are left alone), deferral in combat, and the PanelSkins sweep;
  * slider, edit and search box (their own checks below, each pinned to the mockup's numbers), and the closed dropdown button
    with its open list: the 28 px body, swatch, hairline and flipping chevron, the open glow and LED, lock-on brackets and
    a pink LED on the rows of a modern or legacy list, and the scan wipe that gives every row its own alpha back;
  * every skin: no script or attribute written on a Blizzard widget, nothing resized, idempotent, a hidden control runs no
    animation, a change of pixel scale re-seats every edge onto a whole pixel.

Run:

    python3 tools/controlskins-harness.py                       # checks only
    python3 tools/controlskins-harness.py --png /tmp/controls   # also writes /tmp/controls-<scene>.png

Exit 0 = every check passed. The mock is NOT the real client.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
FILES = {
    "Theme": "Core/Theme.lua",
    "Layout": "Core/Layout.lua",
    "HeldArt": "Core/HeldArt.lua",
    "ControlKit": "Core/ControlKit.lua",
    "CheckSkins": "Core/CheckSkins.lua",
    "SliderSkins": "Core/SliderSkins.lua",
    "FieldSkins": "Core/FieldSkins.lua",
    "DropdownSkins": "Core/DropdownSkins.lua",
    "ItemSlotSkins": "Core/ItemSlotSkins.lua",
    "TabSkins": "Core/TabSkins.lua",
    "InsetSkins": "Core/InsetSkins.lua",
    "PanelSkins": "Core/PanelSkins.lua",
}
SOURCES = {name: (ADDON / path).read_text(encoding="utf-8") for name, path in FILES.items()}
TEXTURES = ADDON / "Media/Textures"
FONT = ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"

MOCK = r"""
PPU = 1.2
UI_W, UI_H = 2560 / 1.2, 1440 / 1.2
DEGRADED = {}
SlashCmdList = {}
UISpecialFrames = {}
__combat = false
function InCombatLockdown() return __combat end
function GetScreenHeight() return UI_H end
function GetScreenWidth() return UI_W end
local TIMERS = {}
C_Timer = { After = function(_, fn) TIMERS[#TIMERS + 1] = fn end }
function FlushTimers()
    for _ = 1, 20 do
        if #TIMERS == 0 then return end
        local list = TIMERS
        TIMERS = {}
        for _, fn in ipairs(list) do fn() end
    end
end

-------------------------------------------------------------------------------
-- Widgets
-------------------------------------------------------------------------------

local Obj = {}
Obj.__index = Obj
local ALL = {}
local seq = 0
local LAYER = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4, HIGHLIGHT = 5 }

local function new(kind, name, parent, blizz)
    seq = seq + 1
    local o = setmetatable({
        kind = kind, fsName = name, parent = parent, seq = seq, blizz = blizz or false, children = {}, regions = {},
        points = {}, shown = true, alpha = 1, scripts = {}, hooks = {}, events = {}, enabled = true, w = 0, h = 0,
        level = parent and ((parent.level or 0) + 1) or 0, layer = "ARTWORK", sub = 0, text = "", size = 12,
        color = nil, vertex = nil, checked = false,
    }, Obj)
    if name then _G[name] = o end
    ALL[#ALL + 1] = o
    return o
end

local REGION = { Texture = true, FontString = true }
local function adopt(parent, o)
    if parent then
        if REGION[o.kind] then parent.regions[#parent.regions + 1] = o else parent.children[#parent.children + 1] = o end
    end
    return o
end

function CreateFrame(kind, name, parent)
    local o = adopt(parent or UIParent, new(kind, name, parent or UIParent, false))
    return o
end
function Obj:CreateTexture(name, layer, template, sub)
    local t = adopt(self, new("Texture", name, self, self.blizz))
    t.layer, t.sub = layer or "ARTWORK", sub or 0
    return t
end
function Obj:CreateFontString(name, layer)
    local f = adopt(self, new("FontString", name, self, self.blizz))
    f.layer = layer or "ARTWORK"
    return f
end

function Obj:GetObjectType() return self.kind end
function Obj:GetName() return self.fsName end
function Obj:GetParent() return self.parent end
function Obj:GetRegions() return unpack(self.regions) end
function Obj:GetChildren() return unpack(self.children) end
function Obj:IsForbidden() return false end
function Obj:IsProtected() return self.protected == true end
function Obj:IsVisible()
    local o = self
    while o do
        if o.shown == false then return false end
        o = o.parent
    end
    return true
end
function Obj:GetLeft() local l = self:Rect(); return l end
function Obj:GetTop() local _, t = self:Rect(); return -t end
function Obj:GetBottom() local _, _, _, b = self:Rect(); return -b end
function Obj:GetRight() local _, _, r = self:Rect(); return r end
function Obj:GetEffectiveScale() return 1 end
function Obj:SetID(i) self.id = i end
function Obj:GetID() return self.id end

-- visibility and scripts
local function runScript(o, k, ...)
    if o.scripts[k] then o.scripts[k](o, ...) end
    for _, fn in ipairs(o.hooks[k] or {}) do fn(o, ...) end
end
Obj.RunScript = runScript
function Obj:Show()
    local was = self.shown
    self.shown = true
    if not was and not REGION[self.kind] then runScript(self, "OnShow") end
end
function Obj:Hide()
    local was = self.shown
    self.shown = false
    if was and not REGION[self.kind] then runScript(self, "OnHide") end
end
function Obj:SetShown(v) if v then self:Show() else self:Hide() end end
function Obj:IsShown() return self.shown end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:GetAlpha() return self.alpha end
function Obj:SetScript(k, fn)
    if self.blizz then error("SetScript on a Blizzard widget: " .. tostring(self.fsName), 2) end
    self.scripts[k] = fn
end
function Obj:GetScript(k) return self.scripts[k] end
function Obj:HookScript(k, fn)
    self.hooks[k] = self.hooks[k] or {}
    table.insert(self.hooks[k], fn)
end
function Obj:SetAttribute() if self.blizz then error("SetAttribute on a Blizzard widget: " .. tostring(self.fsName), 2) end end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:UnregisterEvent(e) self.events[e] = nil end
function Obj:EnableMouse(v) self.mouse = v end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:SetHitRectInsets() end
function Obj:SetClipsChildren() end
function Obj:SetScrollChild(c) self.scrollChild = c end
function Obj:Click() runScript(self, "OnClick", "LeftButton") end
function Obj:Enable() local was = self.enabled; self.enabled = true; if not was then runScript(self, "OnEnable") end end
function Obj:Disable() local was = self.enabled; self.enabled = false; if was then runScript(self, "OnDisable") end end
function Obj:SetEnabled(v) if v then self:Enable() else self:Disable() end end
function Obj:IsEnabled() return self.enabled end
function Obj:SetChecked(v) self.checked = v and true or false end
function Obj:GetChecked() return self.checked end
function Obj:SetFocus()
    if self.focus then return end
    self.focus = true
    runScript(self, "OnEditFocusGained")
end
function Obj:ClearFocus()
    if not self.focus then return end
    self.focus = false
    runScript(self, "OnEditFocusLost")
end
function Obj:HasFocus() return self.focus == true end
function Obj:IsMultiLine() return self.multi == true end
function Obj:GetUTF8CursorPosition() return self.cursor or #(self.text or "") end
function Obj:SetCursorPosition(n) self.cursor = n; runScript(self, "OnCursorChanged", 0, 0, 1, 14) end
function Obj:GetDisplayText() return self.text end
function Obj:SetHighlightColor(r, g, b, a) self.highlight = { r, g, b, a } end
function Obj:SetRotation(r) self.rotation = r end

-- text
function Obj:SetFont(path, size, flags) self.fontPath, self.size, self.flags = path, size, flags; return true end
function Obj:GetFont() return self.fontPath, self.size, self.flags end
function Obj:SetFontObject() end
function Obj:SetNormalFontObject() end
function Obj:SetHighlightFontObject() end
function Obj:SetDisabledFontObject() end
function Obj:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a or 1 } end
function Obj:SetShadowColor() end
function Obj:SetShadowOffset() end
function Obj:SetJustifyH(j) self.justify = j end
function Obj:SetJustifyV() end
function Obj:SetWordWrap() end
function Obj:SetTextInsets(l, r, t, b) self.insets = { l, r, t, b } end
function Obj:GetTextInsets()
    local i = self.insets or { 0, 0, 0, 0 }
    return i[1], i[2], i[3], i[4]
end
function Obj:SetSpacing() end
function Obj:IsTruncated() return false end
function Obj:GetFontString() return self.fs end
function Obj:SetText(t)
    if self.kind == "FontString" and not self.fontPath then error("Font not set", 2) end
    t = t == nil and "" or tostring(t)
    if self.kind == "Button" or self.kind == "CheckButton" then
        if self.fs then self.fs.text = t end
    end
    self.text = t
    if self.kind == "EditBox" then
        self.cursor = nil
        runScript(self, "OnTextChanged", false)
    end
end
function Obj:GetText()
    if self.fs and (self.kind == "Button" or self.kind == "CheckButton") then return self.fs.text end
    return self.text
end
local function plainLen(text)
    text = tostring(text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
    return #text
end
function Obj:GetStringWidth() return plainLen(self.text) * (self.size or 12) * 0.5615 end
function Obj:GetStringHeight() return (self.size or 12) * 1.2 end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:GetWidth() local l, t, r, b = self:Rect(); return r - l end
function Obj:GetHeight() local l, t, r, b = self:Rect(); return b - t end
function Obj:SetSize(w, h) self.w, self.h = w, h end

-- textures
function Obj:SetTexture(path) self.path = path; self.color = nil end
function Obj:GetTexture() return self.path end
function Obj:SetColorTexture(r, g, b, a) self.path = nil; self.color = { r, g, b, a or 1 } end
function Obj:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a or 1 } end
function Obj:SetTexCoord(l, r, t, b) self.coords = { l, r, t, b } end
function Obj:SetBlendMode(m) self.blend = m end
function Obj:SetDrawLayer(layer, sub) self.layer, self.sub = layer, sub or 0 end
function Obj:SetSnapToPixelGrid() end
function Obj:SetTexelSnappingBias() end
function Obj:SetTextureSliceMargins(l) self.slice = l end
function Obj:SetTextureSliceMode() end
function Obj:SetHorizTile() end
-- StatusBar: the bar texture's rect follows the value, or the timer a duration object runs
function Obj:SetStatusBarTexture(path)
    if not self.barTex then
        self.barTex = adopt(self, new("Texture", nil, self, self.blizz))
        self.barTex.layer = "ARTWORK"
        self.barTex.barOf = self
    end
    self.barTex.path = path
    return self.barTex
end
function Obj:GetStatusBarTexture() return self.barTex end
function Obj:SetStatusBarColor(r, g, b, a) if self.barTex then self.barTex.vertex = { r, g, b, a or 1 } end end
function Obj:SetOrientation(o) self.orientation = o end
function Obj:SetReverseFill(v) self.reverse = v and true or false end
function Obj:SetMinMaxValues(a, b) self.min, self.max = a, b end
function Obj:SetValue(v) self.value = v end
local function barFraction(bar)
    local f
    if bar.timer then f = bar.timerFraction else f = ((bar.value or 0) - (bar.min or 0)) / math.max(1e-9, (bar.max or 1) - (bar.min or 0)) end
    return math.max(0, math.min(1, f or 0))
end
local function timerLeft(timer)
    local d = timer.obj
    if issecretvalue(d.start) or issecretvalue(d.duration) then return 1 end
    if not d.duration or d.duration <= 0 then return 0 end
    return math.max(0, math.min(1, (d.start + d.duration - TIME) / d.duration))
end
function Obj:SetTimerDuration(obj, interp, dir)
    self.timer = { obj = obj, interp = interp, dir = dir }
    self.timerFraction = timerLeft(self.timer)
end
function Obj:SetVertTile() end
function Obj:SetDesaturated(v) self.desat = v and true or false end
function Obj:SetAtlas(a) self.atlas = a end
function Obj:GetAtlas() return self.atlas end
function Obj:SetNormalTexture(path)
    if not self.normalTex then
        self.normalTex = adopt(self, new("Texture", nil, self, self.blizz))
        self.normalTex.layer = "ARTWORK"
    end
    self.normalTex.path = path
    self.normalTex.shown = true
end
function Obj:ClearNormalTexture() if self.normalTex then self.normalTex.path = nil end end
function Obj:GetNormalTexture() return self.normalTex end
function Obj:GetPushedTexture() return self.pushedTex end
function Obj:GetHighlightTexture() return self.highlightTex end
function Obj:GetDisabledTexture() return self.disabledTex end
function Obj:GetCheckedTexture() return self.checkedTex end
function Obj:GetDisabledCheckedTexture() return self.disabledCheckedTex end

-- anchors
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetPoint(point, rel, relPoint, x, y)
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    if type(rel) == "string" then error("string anchor " .. rel, 2) end
    -- a point already set is replaced, like the engine
    for i, p in ipairs(self.points) do
        if p.point == point then table.remove(self.points, i) break end
    end
    self.points[#self.points + 1] = { point = point, rel = rel or self.parent, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Obj:SetAllPoints(rel)
    self.points = {}
    local r = rel or self.parent
    self.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 0, y = 0 }
    self.points[2] = { point = "BOTTOMRIGHT", rel = r, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
end
function Obj:GetNumPoints() return #self.points end

local function sizeOf(o)
    if o.kind == "FontString" and (o.w == 0 or o.w == nil) then return o:GetStringWidth(), (o.size or 12) * 1.2 end
    return o.w, o.h
end

-- The rectangle of an object in UI units, y running down: left, top, right, bottom.
function Obj:Rect()
    if self == UIParent then return 0, 0, UI_W, UI_H end
    if self.barOf then
        local bar = self.barOf
        local l, t, r, b = bar:Rect()
        local f = barFraction(bar)
        if bar.orientation == "VERTICAL" then
            local h = (b - t) * f
            if bar.reverse then return l, t, r, t + h end
            return l, b - h, r, b
        end
        local w = (r - l) * f
        if bar.reverse then return r - w, t, r, b end
        return l, t, l + w, b
    end
    local W, H = sizeOf(self)
    local left, right, cx, top, bottom, cy
    for _, p in ipairs(self.points) do
        local rl, rt, rr, rb = p.rel:Rect()
        local ax, ay
        local rp = p.relPoint
        if rp:find("LEFT") then ax = rl elseif rp:find("RIGHT") then ax = rr else ax = (rl + rr) / 2 end
        if rp:find("TOP") then ay = rt elseif rp:find("BOTTOM") then ay = rb else ay = (rt + rb) / 2 end
        ax, ay = ax + p.x, ay - p.y
        local pt = p.point
        if pt:find("LEFT") then left = ax elseif pt:find("RIGHT") then right = ax else cx = ax end
        if pt:find("TOP") then top = ay elseif pt:find("BOTTOM") then bottom = ay else cy = ay end
    end
    if #self.points == 0 then
        local pl, pt = self.parent:Rect()
        left, top = pl, pt
    end
    if left and right then W = right - left
    elseif left then right = left + W
    elseif right then left = right - W
    elseif cx then left = cx - W / 2; right = left + W
    else left = 0; right = W end
    if top and bottom then H = bottom - top
    elseif top then bottom = top + H
    elseif bottom then top = bottom - H
    elseif cy then top = cy - H / 2; bottom = top + H
    else top = 0; bottom = H end
    return left, top, right, bottom
end

DUR_REJECTS_SECRET = false
function hooksecurefunc(a, b, c)
    local tbl, name, fn = _G, a, b
    if type(a) == "table" then tbl, name, fn = a, b, c end
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc: no function " .. tostring(name), 2) end
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

-- The modern menu system's manager: Blizzard_Menu's Menu.GetManager() proxy, which hands back the open menu frame. A test sets
-- MANAGER.open to the frame it wants "opened" and calls MANAGER:OpenMenu(owner, DESC).
MANAGER = { open = nil }
function MANAGER:GetOpenMenu() return self.open end
function MANAGER:OpenMenu() end
function MANAGER:OpenContextMenu() end
Menu = { GetManager = function() return MANAGER end }
function NewDescription()
    local d = {}
    function d:AddMenuAcquiredCallback(fn) self.acquired = fn end
    return d
end

function CreateFont() return { SetFont = function() end, SetTextColor = function() end, SetShadowColor = function() end } end
function GetCursorPosition() return 0, 0 end
function GetPhysicalScreenSize() return 2560, 1440 end
function print() end
TIME = 0
function GetTime() return TIME end

UIParent = new("Frame", "UIParent", nil)

function Fire(event, ...)
    for _, o in ipairs(ALL) do
        if o.events[event] and o.scripts.OnEvent then o.scripts.OnEvent(o, event, ...) end
    end
end


-------------------------------------------------------------------------------
-- Blizzard's control widgets, from the 12.1.0 Blizzard_SharedXML template shapes
-------------------------------------------------------------------------------

function blz(kind, name, parent, w, h, x, y)
    local o = adopt(parent, new(kind, name, parent, true))
    o.w, o.h = w or 0, h or 0
    o.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = x or 0, y = -(y or 0) }
    return o
end
function tex(parent, path, layer)
    local t = adopt(parent, new("Texture", nil, parent, true))
    t.layer = layer or "ARTWORK"
    t.path = path or "Interface\\stock\\art"
    return t
end
function fstring(parent, text, size)
    local f = adopt(parent, new("FontString", nil, parent, true))
    f.fontPath, f.size, f.text = "stock.ttf", size or 12, text or ""
    f.textColor = { 1, 0.82, 0, 1 }
    f.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = 0 }
    return f
end
local function labelRight(b, f, x)
    f.points = { { point = "LEFT", rel = b, relPoint = "RIGHT", x = x, y = 0 } }
end

-- UICheckButtonTemplate / OptionsBaseCheckButtonTemplate: a CheckButton with the five UI-CheckBox textures and a Text.
function CheckBox(parent, label, x, y, w, h)
    local b = blz("CheckButton", nil, parent, w or 26, h or 26, x, y)
    b.normalTex = tex(b, "Interface\\Buttons\\UI-CheckBox-Up")
    b.pushedTex = tex(b, "Interface\\Buttons\\UI-CheckBox-Down")
    b.highlightTex = tex(b, "Interface\\Buttons\\UI-CheckBox-Highlight", "HIGHLIGHT")
    b.checkedTex = tex(b, "Interface\\Buttons\\UI-CheckBox-Check")
    b.disabledCheckedTex = tex(b, "Interface\\Buttons\\UI-CheckBox-Check-Disabled")
    b.Text = fstring(b, label)
    labelRight(b, b.Text, -2)
    return b
end

-- MinimalCheckboxTemplate: the same but with atlases and parentKeys.
function MinimalCheckBox(parent, x, y)
    local b = blz("CheckButton", nil, parent, 30, 29, x, y)
    b.NormalTexture = tex(b); b.NormalTexture.atlas = "checkbox-minimal"
    b.normalTex = b.NormalTexture
    b.checkedTex = tex(b); b.checkedTex.atlas = "checkmark-minimal"
    b.disabledCheckedTex = tex(b); b.disabledCheckedTex.atlas = "checkmark-minimal-disabled"
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    return b
end

-- UIRadioButtonTemplate: 16 x 16, the UI-RadioButton textures, the label under the key `text`.
function RadioBtn(parent, label, x, y)
    local b = blz("CheckButton", nil, parent, 16, 16, x, y)
    b.normalTex = tex(b, "Interface\\Buttons\\UI-RadioButton")
    b.highlightTex = tex(b, "Interface\\Buttons\\UI-RadioButton", "HIGHLIGHT")
    b.checkedTex = tex(b, "Interface\\Buttons\\UI-RadioButton")
    b.text = fstring(b, label)
    labelRight(b, b.text, 5)
    return b
end

-- An action button is a CheckButton too (icon, Count, HotKey, cooldown): never a checkbox.
function ActionBtn(parent, x, y)
    local b = blz("CheckButton", nil, parent, 36, 36, x, y)
    b.icon = tex(b, "Interface\\Icons\\spell", "BACKGROUND")
    b.Count = fstring(b, "")
    b.normalTex = tex(b); b.checkedTex = tex(b)
    return b
end

-- A mail row: a CheckButton as wide as the list.
function RowBtn(parent, x, y)
    local b = blz("CheckButton", nil, parent, 300, 45, x, y)
    b.normalTex = tex(b); b.checkedTex = tex(b)
    return b
end


-- UISliderTemplateWithLabels (144 x 17): a Slider with the NineSlice frame, a thumb texture and Text, Low and High labels.
function SliderBox(parent, x, y, w, h, o)
    o = o or {}
    local s = blz("Slider", nil, parent, w or 144, h or 17, x, y)
    s.min, s.max, s.value, s.step = o.min or 0, o.max or 100, o.value or 50, o.step or 1
    s.orientation = o.orientation or "HORIZONTAL"
    s.thumbTex = tex(s, "Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
    s.Thumb = s.thumbTex
    if not o.minimal then
        s.NineSlice = blz("Frame", nil, s, 0, 0)
        s.NineSlice.points = { { point = "TOPLEFT", rel = s, relPoint = "TOPLEFT", x = 0, y = 0 },
            { point = "BOTTOMRIGHT", rel = s, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
        s.NineSlice.piece = tex(s.NineSlice, "Interface\\Buttons\\UI-SliderBar-Border", "BORDER")
        s.Text, s.Low, s.High = fstring(s, "Opacity"), fstring(s, "LOW", 10), fstring(s, "HIGH", 10)
    else
        s.Left, s.Middle, s.Right = tex(s), tex(s), tex(s)
        for _, t in ipairs({ s.Left, s.Middle, s.Right }) do t.atlas = "Minimal_SliderBar" end
    end
    function s:GetValue() return self.value end
    function s:SetValue(v) self.value = v; self:RunScript("OnValueChanged", v) end
    function s:GetMinMaxValues() return self.min, self.max end
    function s:SetMinMaxValues(a, b) self.min, self.max = a, b; self:RunScript("OnMinMaxChanged", a, b) end
    function s:GetValueStep() return self.step end
    function s:SetValueStep(v) self.step = v end
    function s:GetOrientation() return self.orientation end
    function s:GetThumbTexture() return self.thumbTex end
    function s:IsDraggingThumb() return self.dragging == true end
    return s
end

-- MinimalSliderWithSteppersTemplate (250 x 40): the Slider between a Back and a Forward button, and a RightText.
function SteppedSlider(parent, x, y, o)
    local f = blz("Frame", nil, parent, 250, 40, x, y)
    o = o or {}
    o.minimal = true
    f.Slider = SliderBox(f, 19, 0, 212, 40, o)
    f.Back = blz("Button", nil, f, 11, 19, 4, 10)
    f.Back.art = tex(f.Back, nil, "BACKGROUND"); f.Back.art.atlas = "Minimal_SliderBar_Button_Left"
    f.Forward = blz("Button", nil, f, 9, 18, 231, 10)
    f.Forward.art = tex(f.Forward, nil, "BACKGROUND"); f.Forward.art.atlas = "Minimal_SliderBar_Button_Right"
    f.RightText = fstring(f, "50%")
    return f
end

-- InputBoxTemplate (AddFriendNameEditBox and kin): a single line EditBox with the Left, Middle and Right border art.
function EditBoxW(parent, x, y, w, h, o)
    o = o or {}
    local b = blz("EditBox", nil, parent, w or 130, h or 20, x, y)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do
        b[key] = tex(b, nil, "BACKGROUND")
        b[key].atlas = "common-search-border-" .. key:lower()
    end
    b.fontPath, b.size, b.textColor = "stock.ttf", 12, { 1, 1, 1, 1 }
    b.multi = o.multi
    return b
end

-- InsetFrameTemplate: a Frame keyed layoutType = "InsetFrameTemplate" with the marble Bg and the NineSlice child (the bevel).
function InsetW(parent, x, y, w, h)
    local f = blz("Frame", nil, parent, w, h, x, y)
    f.layoutType = "InsetFrameTemplate"
    f.Bg = tex(f, "Interface\\FrameGeneral\\UI-Background-Marble", "BACKGROUND")
    f.NineSlice = blz("Frame", nil, f, w, h, 0, 0)
    f.NineSlice.bevel = tex(f.NineSlice, "Interface\\stock\\bevel", "BORDER")
    return f
end

-- InputScrollFrameTemplate: a ScrollFrame wearing the nine Common-Input-Border pieces (the border overshoots the rect by 5), the
-- char count and a multi-line EditBox as its scroll child, with the placeholder (`Instructions`).
function AreaW(parent, x, y, w, h)
    local f = blz("ScrollFrame", nil, parent, w, h, x, y)
    for _, key in ipairs({ "TopLeftTex", "TopRightTex", "TopTex", "BottomLeftTex", "BottomRightTex", "BottomTex", "LeftTex",
                           "RightTex", "MiddleTex" }) do
        f[key] = tex(f, nil, "BACKGROUND")
    end
    f.CharCount = fstring(f, "255", 14)
    f.CharCount.textColor = { 0.5, 0.5, 0.5, 1 }
    local e = blz("EditBox", nil, f, w, 1, 0, 0)
    e.multi = true
    e.fontPath, e.size, e.textColor = "stock.ttf", 10, { 1, 1, 1, 1 }
    e.Instructions = fstring(e, "Type here", 10)
    f.EditBox = e
    f.scrollChild = e
    return f
end

-- SearchBoxTemplate: the same plus the search icon, the placeholder (`Instructions`) and the clear button, with the stock handlers
-- (InputBoxInstructions_OnTextChanged, SearchBoxTemplate_OnEditFocusGained / Lost) set the way the XML sets them.
function SearchBoxW(parent, x, y, w, h, o)
    local b = EditBoxW(parent, x, y, w, h, o)
    b.searchIcon = tex(b, nil, "OVERLAY"); b.searchIcon.atlas = "common-search-magnifyingglass"
    b.Instructions = fstring(b, "Search", 10)
    b.Instructions.points = { { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 16, y = 0 },
        { point = "BOTTOMRIGHT", rel = b, relPoint = "BOTTOMRIGHT", x = -20, y = 0 } }
    local bh = b.h
    b.clearButton = blz("Button", nil, b, 17, 17, (w or 130) - 20, (bh - 17) / 2)
    b.clearButton.Icon = tex(b.clearButton, nil, "ARTWORK"); b.clearButton.Icon.atlas = "common-search-clearbutton"
    b.clearButton.Icon.alpha = 0.5
    b.clearButton.shown = false
    b.scripts.OnTextChanged = function(self) self.Instructions:SetShown(self:GetText() == ""); if self:GetText() ~= "" then self.clearButton:Show() end end
    b.scripts.OnEditFocusGained = function(self) self.clearButton:Show() end
    b.scripts.OnEditFocusLost = function(self) if self:GetText() == "" then self.clearButton:Hide() end end
    return b
end

-- WowStyle1DropdownTemplate: a DropdownButton (intrinsic) with the Background, the Arrow and the Text, the stock state colours
-- (OnButtonStateChanged) and the open flag the menu system keeps (IsMenuOpen, OnMenuOpened, OnMenuClosed).
function DropdownW(parent, x, y, w, h, o)
    o = o or {}
    local b = blz("Button", nil, parent, w or 120, h or 25, x, y)
    b.intrinsic = "DropdownButton"
    b.Background = tex(b, nil, "BACKGROUND"); b.Background.atlas = "common-dropdown-textholder"
    b.Arrow = tex(b, nil, "OVERLAY"); b.Arrow.atlas = "common-dropdown-a-button"
    b.Text = fstring(b, o.text or "general")
    b.Text.textColor = { 1, 1, 1, 1 }
    b.Text.points = { { point = "TOPRIGHT", rel = b.Arrow, relPoint = "LEFT", x = 0, y = 0 },
        { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 8, y = -8 } }
    b.open = false
    function b:IsMenuOpen() return self.open end
    function b:OnMenuOpened() self.open = true end
    function b:OnMenuClosed() self.open = false end
    function b:OnButtonStateChanged()
        if self:IsEnabled() then self.Text:SetTextColor(1, 1, 1, 1) else self.Text:SetTextColor(0.5, 0.5, 0.5, 1) end
    end
    return b
end
function OpenList(b) b:OnMenuOpened(); b:RunScript("OnMouseDown") end
function CloseList(b) b:OnMenuClosed() end

-- A modern menu frame: rows are child buttons that answer GetElementDescription, as Blizzard_Menu's compositor builds them.
function MenuW(specs, x, y, w, rowH)
    rowH = rowH or 20
    local m = blz("Frame", nil, UIParent, w or 196, 8 + #specs * rowH, x or 300, y or 300)
    local chrome = m:CreateTexture(nil, "BACKGROUND")
    chrome:SetAllPoints(m)
    chrome:SetColorTexture(0.102, 0.063, 0.145, 0.94)
    m.rows = {}
    for i, spec in ipairs(specs) do
        local r = blz("Button", nil, m, (w or 196) - 16, rowH, 8, 4 + (i - 1) * rowH)
        r.Label = fstring(r, spec.text or "row")
        r.Label.textColor = { 0.133, 0.878, 1, 1 }
        r.Label.points = { { point = "LEFT", rel = r, relPoint = "LEFT", x = 10, y = 0 } }
        r.GetElementDescription = function() return { IsSelected = function() return spec.selected == true end } end
        r.alpha = spec.alpha or 1
        m.rows[i] = r
    end
    return m
end
-- Opens `menu` the way the manager does: the frame becomes the open menu, then OpenMenu runs (our hook is a post-hook).
function OpenMenuFrame(menu, desc)
    MANAGER.open = menu
    menu.shown = true
    MANAGER:OpenMenu(nil, desc or NewDescription())
end

-- UIDropDownMenu's list: a real frame DropDownList1 with buttons DropDownList1Button1.. each with a Check texture.
function LegacyList(specs)
    local l = blz("Frame", "DropDownList1", UIParent, 196, 20 + #specs * 16, 300, 300)
    l.rows = {}
    for i, spec in ipairs(specs) do
        local r = blz("Button", "DropDownList1Button" .. i, l, 176, 16, 10, 10 + (i - 1) * 16)
        r.Label = fstring(r, spec.text or "row")
        local check = tex(r, nil, "ARTWORK")
        _G["DropDownList1Button" .. i .. "Check"] = check
        check.shown = spec.checked == true
        l.rows[i] = r
    end
    l.shown = false
    return l
end

-- 12.0's duration objects and the timer enums StatusBar:SetTimerDuration takes. SetTimeFromStart refuses a secret number when
-- DUR_REJECTS_SECRET is set (the engine may well refuse one from tainted code).
Enum = { StatusBarTimerDirection = { ElapsedTime = 0, RemainingTime = 1 }, StatusBarInterpolation = { Immediate = 0, ExponentialEaseOut = 1 } }
C_DurationUtil = {
    CreateDuration = function()
        local d = { kind = "Duration" }
        local function check(...)
            for i = 1, select("#", ...) do
                local v = select(i, ...)
                if DUR_REJECTS_SECRET and issecretvalue(v) then error("Secret values are only allowed during untainted execution", 3) end
                if v ~= nil and type(v) ~= "number" and not issecretvalue(v) then error("bad argument: number expected", 3) end
            end
        end
        function d:SetTimeFromStart(start, duration, modRate)
            check(start, duration, modRate)
            self.start, self.duration = start, duration
        end
        function d:SetTimeFromEnd(finish, duration, modRate)
            check(finish, duration, modRate)
            self.start, self.duration = finish - duration, duration
        end
        return d
    end,
}
function DurationAt(start, duration)
    local d = C_DurationUtil.CreateDuration()
    d:SetTimeFromStart(start, duration)
    return d
end

-- A Cooldown frame the way an item button has one: the stock SetCooldown, SetCooldownFromDurationObject, Clear and the
-- swipe switch (on by default).
function CooldownW(parent)
    local c = blz("Cooldown", nil, parent, 0, 0)
    c.points = { { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = 0 },
        { point = "BOTTOMRIGHT", rel = parent, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    c.swipe = true
    function c:SetCooldown(start, duration)
        self.cd = { start = start, dur = type(duration) == "number" and duration or 1e9 }
        self.shown = true
    end
    function c:SetCooldownFromDurationObject(obj) self.cdObj = obj; self.shown = true end
    function c:SetCooldownFromExpirationTime(finish, duration) self.cd = { start = finish - duration, dur = duration }; self.shown = true end
    function c:Clear() self.cd, self.cdObj = nil, nil end
    function c:SetDrawSwipe(v) self.swipe = v and true or false end
    function c:GetDrawSwipe() return self.swipe end
    c.shown = false
    return c
end

-- An item button the way ContainerFrameItemButton and kin have one: an ItemButton with its icon, Count and Cooldown, the slot art
-- the skin holds, and no scripts the skin may write (Blizzard's).
function ItemSlotW(parent, x, y, w, h)
    local b = blz("ItemButton", nil, parent, w or 37, h or 37, x, y)
    b.icon = tex(b, "Interface\\Icons\\inv_misc_bag", "ARTWORK")
    b.icon.points = { { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 0, y = 0 },
        { point = "BOTTOMRIGHT", rel = b, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    b.Count = fstring(b, "", 11)
    b.Cooldown = CooldownW(b)
    b.IconBorder = tex(b, nil, "OVERLAY")
    return b
end
-- A slot's state as the caller's reader hands it over.
function SlotState(t)
    local state = t or {}
    return state, function() return state end
end

-- PanelTabButtonTemplate (10 x 32, set wider by PanelTemplates_TabResize): a Button with the six tab art textures (the Active
-- ones hidden until picked), the three Highlight textures and the label under `Text`. A tab with `o.top` is a top tab.
function PanelTab(parent, label, x, y, w, h, o)
    o = o or {}
    local b = blz("Button", nil, parent, w or 84, h or 32, x, y)
    for _, key in ipairs({ "LeftActive", "RightActive", "MiddleActive", "Left", "Right", "Middle" }) do
        b[key] = tex(b, nil, "BACKGROUND")
        b[key].atlas = "uiframe-tab-" .. key:lower()
        b[key].shown = key:find("Active") == nil
    end
    for _, key in ipairs({ "LeftHighlight", "MiddleHighlight", "RightHighlight" }) do
        b[key] = tex(b, nil, "HIGHLIGHT")
        b[key].atlas = "uiframe-tab-" .. key:lower()
    end
    b.Text = fstring(b, label, 10)
    b.Text.points = { { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 2 } }
    b.isTopTab = o.top
    return b
end

-- Blizzard_SharedXML's PanelTemplates tab functions as the 12.1.0 source writes them. The engine re-applies a tab's font object
-- on every state change, so each one also writes the label's font and colour the way the stock font objects would.
local function stockLabel(tab, r, g, b)
    tab.Text:SetFont("stock.ttf", 10)
    tab.Text:SetTextColor(r, g, b, 1)
end
function PanelTemplates_SelectTab(tab)
    tab.Left:Hide(); tab.Middle:Hide(); tab.Right:Hide()
    tab:Disable()
    stockLabel(tab, 1, 1, 1)
    local offsetY = tab.selectedTextY or -3
    if tab.isTopTab then offsetY = -offsetY - 7 end
    tab.Text:SetPoint("CENTER", tab, "CENTER", tab.selectedTextX or 0, offsetY)
    tab.LeftActive:Show(); tab.MiddleActive:Show(); tab.RightActive:Show()
end
function PanelTemplates_DeselectTab(tab)
    tab.Left:Show(); tab.Middle:Show(); tab.Right:Show()
    tab:Enable()
    stockLabel(tab, 1, 0.82, 0)
    local offsetY = tab.deselectedTextY or 2
    if tab.isTopTab then offsetY = -offsetY - 6 end
    tab.Text:SetPoint("CENTER", tab, "CENTER", tab.deselectedTextX or 0, offsetY)
    tab.LeftActive:Hide(); tab.MiddleActive:Hide(); tab.RightActive:Hide()
end
function PanelTemplates_SetDisabledTabState(tab)
    tab.Left:Show(); tab.Middle:Show(); tab.Right:Show()
    tab:Disable()
    stockLabel(tab, 0.5, 0.5, 0.5)
    local offsetY = tab.deselectedTextY or 2
    if tab.isTopTab then offsetY = -offsetY - 6 end
    tab.Text:SetPoint("CENTER", tab, "CENTER", tab.deselectedTextX or 0, offsetY)
    tab.LeftActive:Hide(); tab.MiddleActive:Hide(); tab.RightActive:Hide()
end

-- TabSystemButtonTemplate: the same art, picked through SetTabSelected, with the news flag in SetTabNotification (a pooled
-- notification frame, shared with other windows) and the forced-disabled flag in SetTabEnabled.
function TabSysBtn(parent, label, x, y, w, h, o)
    o = o or {}
    local b = PanelTab(parent, label, x, y, w, h, o)
    b.isTopTab = nil
    b.isTabOnTop = o.top
    b.isSelected, b.forceDisabled, b.tabText = false, false, label
    function b:SetTabSelected(isSelected)
        self.isSelected = isSelected
        self.Left:SetShown(not isSelected); self.Middle:SetShown(not isSelected); self.Right:SetShown(not isSelected)
        self.LeftActive:SetShown(isSelected); self.MiddleActive:SetShown(isSelected); self.RightActive:SetShown(isSelected)
        if isSelected then stockLabel(self, 1, 1, 1) else stockLabel(self, 1, 0.82, 0) end
        self:SetEnabled(not isSelected and not self.forceDisabled)
        local offset = self.isTabOnTop and (isSelected and 0 or -3) or (isSelected and -3 or 2)
        self.Text:SetPoint("CENTER", self, "CENTER", 0, offset)
    end
    function b:SetTabEnabled(enabled)
        self.forceDisabled = not enabled
        self:SetEnabled(enabled and not self.isSelected)
        stockLabel(self, enabled and 1 or 0.5, enabled and 0.82 or 0.5, enabled and 0 or 0.5)
    end
    function b:SetTabNotification(show)
        if show then
            if not self.notificationFrame then
                self.notificationFrame = blz("Frame", nil, self, 20, 20, 0, 0)
                self.notificationFrame.icon = tex(self.notificationFrame, nil, "ARTWORK")
            end
        else
            self.notificationFrame = nil
        end
    end
    function b:IsSelected() return not not self.isSelected end
    return b
end

function Panel(name)
    local f = blz("Frame", name or "TestPanel", UIParent, 400, 300, 100, 100)
    f.shown = true
    return f
end

-- Presses a check button the way the engine does: toggle, then OnClick.
function Press(b)
    b:SetChecked(not b:GetChecked())
    b:Click()
end
-- Picks one radio of a group: the others are unchecked first, as a Blizzard radio group's OnClick does.
function Choose(b, group)
    for _, other in ipairs(group) do
        if other ~= b then other:SetChecked(false) end
    end
    b:SetChecked(true)
    b:Click()
end
function Hover(b) b:RunScript("OnEnter") end
function Unhover(b) b:RunScript("OnLeave") end

-- Runs `dt` seconds of frames in steps of 1/60.
function Step(dt)
    local steps = math.max(1, math.floor(dt * 60 + 0.5))
    for _ = 1, steps do
        TIME = TIME + dt / steps
        for _, o in ipairs(ALL) do
            if o.timer then o.timerFraction = timerLeft(o.timer) end
            if o.cd and not o.cd.done and type(o.cd.start) == "number" and o.cd.dur > 0 and TIME >= o.cd.start + o.cd.dur then
                o.cd.done = true
                o:RunScript("OnCooldownDone")
            end
            if o.scripts.OnUpdate and o:IsVisible() then o.scripts.OnUpdate(o, dt / steps) end
        end
    end
end

-------------------------------------------------------------------------------
-- Loading the addon files
-------------------------------------------------------------------------------

-- The client's own test for a secret value: here a table marked __secret (Theme.lua's FS.IsSecret asks this).
function issecretvalue(v) return type(v) == "table" and v.__secret == true end

function Load(opts)
    opts = opts or {}
    FS = {
        LogDegradeOnce = function(key, msg) DEGRADED[#DEGRADED + 1] = key .. " :: " .. tostring(msg) end,
    }
    FS.FrameHelpers = { PixelsPerUnit = function() return PPU end }
    for _, name in ipairs({ "Theme", "Layout", "HeldArt", "ControlKit", "CheckSkins", "SliderSkins", "FieldSkins", "DropdownSkins", "ItemSlotSkins", "TabSkins", "InsetSkins", "PanelSkins" }) do
        local chunk, err = load(SOURCES[name], "=" .. name .. ".lua")
        if not chunk then error(err) end
        chunk("forever-stuwave", FS)
    end
    return FS
end

-------------------------------------------------------------------------------
-- Measuring
-------------------------------------------------------------------------------

-- Rectangle of `o` in physical pixels relative to the top left of `ref`.
function Px(o, ref)
    local l, t, r, b = o:Rect()
    local rl, rt = ref:Rect()
    return (l - rl) * PPU, (t - rt) * PPU, (r - rl) * PPU, (b - rt) * PPU
end
function Near(a, b, tol) return math.abs(a - b) <= (tol or 0.01) end
function Expect(o, ref, l, t, w, h, what)
    local pl, pt, pr, pb = Px(o, ref)
    assert(Near(pl, l) and Near(pt, t) and Near(pr - pl, w) and Near(pb - pt, h), string.format(
        "%s: x=%.2f y=%.2f w=%.2f h=%.2f, wanted x=%s y=%s w=%s h=%s", what, pl, pt, pr - pl, pb - pt, l, t, w, h))
end
-- A colour table against a Theme token (and an alpha, 1 unless given).
function Is(c, token, alpha, what)
    assert(c, what .. ": no colour set")
    local a = alpha or 1
    assert(Near(c[1], token[1], 0.002) and Near(c[2], token[2], 0.002) and Near(c[3], token[3], 0.002) and Near(c[4], a, 0.002),
        string.format("%s: got %.3f %.3f %.3f %.3f, wanted %.3f %.3f %.3f %.3f", what, c[1], c[2], c[3], c[4], token[1], token[2], token[3], a))
end
-- Every texture and frame under `root` sits on whole screen pixels (fonts excepted). `except` lists stock objects (their
-- rects are never resized, so a fractional stock layout is theirs) to leave out, a frame with everything under it.
function WholePixels(root, ref, what, except)
    local n = 0
    local skip = {}
    for _, o in ipairs(except or {}) do skip[o] = true end
    local function visit(o)
        for _, r in ipairs(o.regions) do
            if r.kind ~= "FontString" and r.shown ~= false and not skip[r] then
                local l, t, rr, b = Px(r, ref)
                for _, v in ipairs({ l, t, rr, b }) do
                    assert(Near(v, math.floor(v + 0.5), 0.001), string.format("%s: %s edge %.4f is not a whole pixel", what, tostring(r.path or r.kind), v))
                end
                n = n + 1
            end
        end
        for _, c in ipairs(o.children) do
            if not skip[c] then visit(c) end
        end
    end
    visit(root)
    return n
end
function Colour(t) return t.color or t.vertex end
function Slk() return FS.SliderSkins end
function Fld() return FS.FieldSkins end
function Dd() return FS.DropdownSkins end
function SkinOne(w) FS.ControlKit.SkinWidget(w); FlushTimers() end
-- Rounds the way the skin does (half up).
function Round(v) return math.floor(v + 0.5) end
function Cks() return FS.CheckSkins end
function Mine(w) return FS.CheckSkins.Parts(w) end
function Skin(panel)
    local n = FS.PanelSkins.SweepControls(panel)
    FlushTimers()
    return n
end
function NoDegrade() assert(#DEGRADED == 0, "degraded: " .. table.concat(DEGRADED, " | ")) end
function HookCount()
    local n = 0
    for _, o in ipairs(ALL) do
        for _, list in pairs(o.hooks) do n = n + #list end
    end
    return n
end
function ObjCount() return #ALL end

-- Ops for the renderer, in draw order.
local function visible(o)
    while o do
        if o.shown == false then return false end
        o = o.parent
    end
    return true
end
local function alphaOf(o)
    local a = 1
    while o do a = a * (o.alpha or 1); o = o.parent end
    return a
end
function DumpOps(roots)
    local ops = {}
    local function region(o)
        if not visible(o) then return end
        local a = alphaOf(o)
        if a <= 0 then return end
        local l, t, r, b = Px(o, UIParent)
        if o.kind == "Texture" then
            local file = o.path and o.path:match("Media\\Textures\\([%w_]+%.tga)$")
            if o.path and o.path:find("slice_cut2") then
                local kind = o.path:find("glow") and "glow" or (o.path:find("outline") or o.path:find("border")) and "ring" or "fill"
                if kind ~= "glow" and o.vertex then
                    ops[#ops + 1] = { kind = kind, l = l, t = t, r = r, b = b, c = o.slice or 4, rgba = { o.vertex[1], o.vertex[2], o.vertex[3], o.vertex[4] * a } }
                end
            elseif file and o.vertex then
                ops[#ops + 1] = { kind = "tex", file = file, coords = o.coords, l = l, t = t, r = r, b = b,
                    rgba = { o.vertex[1], o.vertex[2], o.vertex[3], o.vertex[4] * a } }
            elseif o.color then
                ops[#ops + 1] = { kind = "flat", l = l, t = t, r = r, b = b, rgba = { o.color[1], o.color[2], o.color[3], o.color[4] * a } }
            elseif o.path and o.path:find("WHITE8x8", 1, true) and o.vertex then
                ops[#ops + 1] = { kind = "flat", l = l, t = t, r = r, b = b, rgba = { o.vertex[1], o.vertex[2], o.vertex[3], o.vertex[4] * a } }
            end
        elseif o.kind == "FontString" and o.text and o.text ~= "" then
            local tc = o.textColor or { 1, 1, 1, 1 }
            ops[#ops + 1] = { kind = "text", l = l, t = t, r = r, b = b, text = o.text, size = (o.size or 12) * PPU,
                rgba = { tc[1], tc[2], tc[3], (tc[4] or 1) * a }, justify = o.justify or "LEFT" }
        end
    end
    -- the engine draws every frame of a strata in (frame level, creation) order, whatever the tree says
    local frames = {}
    local function collect(f)
        if not visible(f) then return end
        frames[#frames + 1] = f
        for _, c in ipairs(f.children) do collect(c) end
    end
    local function draw(f)
        local regions = {}
        for _, r in ipairs(f.regions) do regions[#regions + 1] = r end
        table.sort(regions, function(x, y)
            local lx, ly = LAYER[x.layer] or 3, LAYER[y.layer] or 3
            if lx ~= ly then return lx < ly end
            if (x.sub or 0) ~= (y.sub or 0) then return (x.sub or 0) < (y.sub or 0) end
            return x.seq < y.seq
        end)
        for _, r in ipairs(regions) do region(r) end
        -- an edit box draws its own text, inside its insets, over its art and under its children
        if f.kind == "EditBox" and f.text and f.text ~= "" and f.fontPath then
            local l, t, r, b = Px(f, UIParent)
            local ins = f.insets or { 0, 0, 0, 0 }
            local tc = f.textColor or { 1, 1, 1, 1 }
            ops[#ops + 1] = { kind = "text", l = l + ins[1] * PPU, t = t, r = r - ins[2] * PPU, b = b, text = f.text,
                size = (f.size or 12) * PPU, rgba = { tc[1], tc[2], tc[3], (tc[4] or 1) * alphaOf(f) }, justify = "LEFT", clip = true }
        end
    end
    for _, r in ipairs(roots) do collect(r) end
    table.sort(frames, function(x, y)
        if x.level ~= y.level then return x.level < y.level end
        return x.seq < y.seq
    end)
    for _, f in ipairs(frames) do draw(f) end
    return ops
end
"""

CASES: list[tuple[str, str]] = []
SCENES: dict[str, str] = {}


def case(name: str, body: str) -> None:
    CASES.append((name, body))


def run_case(body: str):
    rt = LuaRuntime(unpack_returned_tuples=False)
    for key, src in SOURCES.items():
        rt.globals()["SRC_" + key] = src
    names = ", ".join(f"{key} = SRC_{key}" for key in SOURCES)
    try:
        rt.execute("SOURCES = { " + names + " }")
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc), None
    return None, rt


PRELUDE = """
    local FS = Load()
    local P = Panel()
"""

# -------------------------------------------------------------------------------------------------------------------
# Tokens: the mockup's numbers, hardcoded here (never read back from the code under test)
# -------------------------------------------------------------------------------------------------------------------

case("tokens_are_the_mockups_numbers", PRELUDE + """
    local T, K = FS.Theme, FS.Layout.Controls
    local function hex(c, h)
        local r, g, b = tonumber(h:sub(1, 2), 16) / 255, tonumber(h:sub(3, 4), 16) / 255, tonumber(h:sub(5, 6), 16) / 255
        assert(Near(c[1], r, 0.001) and Near(c[2], g, 0.001) and Near(c[3], b, 0.001), h .. " is not the token " .. c[1] .. " " .. c[2] .. " " .. c[3])
    end
    hex(T.COLOR_CTRL_INK, "07030e"); hex(T.COLOR_CTRL_DIM, "4b2a86"); hex(T.COLOR_CTRL_SEL, "2a0f2e")
    hex(T.COLOR_CTRL_CELL, "25154a"); hex(T.COLOR_CTRL_DIS, "5c5480"); hex(T.COLOR_CTRL_DISFILL, "0a0614")
    hex(T.COLOR_CTRL_DISEDGE, "2a1846"); hex(T.COLOR_CTRL_WELL, "1c1030"); hex(T.COLOR_CTRL_BAND, "1a0d2c")
    hex(T.COLOR_CTRL_TEXT, "e9e2ff"); hex(T.COLOR_HEALTH, "ff2e97"); hex(T.COLOR_POWER, "22e0ff")
    assert(K.CHECK == 16 and K.CHECK_CUT == 4 and K.LED == 3 and K.LED_X == 11 and K.LED_Y == 2)
    assert(K.NODE == 6 and K.NODE_OFFSET == 5)
    assert(K.LED_PULSE == 1.6 and K.LED_FLOOR == 0.3 and K.RING_PERIOD == 1.8 and K.RING_FROM == 0.7 and K.RING_TO == 1.9)
    assert(Near(K.TICK_DRAW, 0.54) and K.RING_ALPHA == 0.9 and K.RAIL_ALPHA == 0.5)
""")

# -------------------------------------------------------------------------------------------------------------------
# Checkbox
# -------------------------------------------------------------------------------------------------------------------

case("checkbox_plate_is_16_px_centred_on_whole_pixels_and_the_stock_rect_is_untouched", PRELUDE + """
    local cb = CheckBox(P, "Show the thing", 20, 20)
    assert(Skin(P) == 1)
    NoDegrade()
    local p = Mine(cb)
    assert(p and p.built and p.kind == "check")
    -- the stock rect keeps its 26 units (31 px); the 16 px plate sits floor((31 - 16) / 2) = 7 px in on both axes
    assert(cb.w == 26 and cb.h == 26, "the stock rect was resized")
    Expect(p.plateFrame, cb, 7, 7, 16, 16, "plate")
    -- the cut ring and fill fill the plate, the tick is the plate's box, the LED is the 3 px square at (11, 2)
    Expect(p.plate.ring, p.plateFrame, 0, 0, 16, 16, "ring")
    Expect(p.plate.fill, p.plateFrame, 0, 0, 16, 16, "fill")
    Expect(p.led, p.plateFrame, 11, 2, 3, 3, "led")
    assert(p.plate.c == 4, "chamfer " .. p.plate.c)
    assert(WholePixels(cb, P, "check") >= 5)
""")

case("checkbox_off_is_ink_with_a_dim_1px_edge_and_no_mark", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    Skin(P)
    local p, T = Mine(cb), FS.Theme
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "edge")
    assert(not p.plate.ring2:IsShown(), "a 1 px edge has no second ring")
    assert(not p.tick:IsShown(), "no tick when off")
    assert(not p.led:IsShown(), "no LED when off")
    assert(FS.ControlKit.AnimationCount() == 0, "an idle box animates nothing")
""")

case("checkbox_hover_turns_the_edge_cyan_and_shows_a_cyan_led_stub", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    Skin(P)
    local p, T = Mine(cb), FS.Theme
    Hover(cb)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "hover face")
    assert(p.led:IsShown())
    Is(p.led.color, T.COLOR_POWER, 0.5, "hover LED stub")
    assert(not p.plate.ring2:IsShown())
    Unhover(cb)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "edge after leaving")
    assert(not p.led:IsShown())
""")

case("checkbox_on_is_the_pink_wash_with_a_2px_pink_edge_tick_and_led", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    Skin(P)
    local p, T = Mine(cb), FS.Theme
    Press(cb)
    Step(1.0)
    Is(Colour(p.plate.fill), T.COLOR_CTRL_SEL, 1, "on face")
    Is(p.plate.ring.vertex, T.COLOR_HEALTH, 1, "on edge")
    assert(p.plate.ring2:IsShown(), "a 2 px edge is two rings")
    Is(p.plate.ring2.vertex, T.COLOR_HEALTH, 1, "inner ring")
    Expect(p.plate.ring2, p.plateFrame, 1, 1, 14, 14, "inner ring")
    assert(p.plate.ring2.slice == 3, "the inner ring is the baked chamfer 3, one less than the outer 4")
    assert(p.tick:IsShown())
    Is(p.tick.vertex, T.COLOR_HEALTH, 1, "tick")
    assert(p.led:IsShown())
    Hover(cb)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "on + hover edge")
    Is(p.plate.ring2.vertex, T.COLOR_POWER, 1, "on + hover inner ring")
    Is(Colour(p.plate.fill), T.COLOR_CTRL_SEL, 1, "on + hover face")
    Is(p.tick.vertex, T.COLOR_HEALTH, 1, "tick stays pink under the hand")
""")

case("checkbox_tick_draws_in_over_054_s_and_the_led_breathes_to_03", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    Skin(P)
    local p = Mine(cb)
    local kit = FS.ControlKit
    Press(cb)
    Step(0)
    assert(not p.tick:IsShown(), "the tick starts undrawn")
    assert(kit.IsAnimating(p.plateFrame, "tick"))
    Step(0.27)
    -- half the polyline (11.31 px long, 3 root 2 then 5 root 2): the leading edge is at x 7 plus the stroke's 1 px
    Expect(p.tick, p.plateFrame, 0, 0, 8, 16, "half drawn tick")
    assert(Near(p.tick.coords[2], 0.5, 0.001) and p.tick.coords[1] == 0 and p.tick.coords[3] == 0 and p.tick.coords[4] == 1)
    Step(0.5)
    Expect(p.tick, p.plateFrame, 0, 0, 16, 16, "drawn tick")
    assert(Near(p.tick.coords[2], 1, 0.001))
    assert(not kit.IsAnimating(p.plateFrame, "tick"), "the draw-in ends")
    -- the LED has run 0.77 s since its first frame; the dip is at 0.8 s, the top again at 1.6 s
    Step(0.03)
    assert(Near(p.led.color[4], 0.3, 0.01), "LED floor " .. p.led.color[4])
    Step(0.8)
    assert(Near(p.led.color[4], 1, 0.01), "LED top " .. p.led.color[4])
    Is(p.led.color, FS.Theme.COLOR_HEALTH, p.led.color[4], "LED colour")
""")

case("checkbox_already_on_when_skinned_shows_the_whole_tick_with_no_draw_in", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    cb:SetChecked(true)
    Skin(P)
    local p = Mine(cb)
    assert(p.tick:IsShown())
    Expect(p.tick, p.plateFrame, 0, 0, 16, 16, "tick")
    assert(not FS.ControlKit.IsAnimating(p.plateFrame, "tick"), "no draw-in for a box that was already on")
    assert(FS.ControlKit.IsAnimating(p.plateFrame, "led"), "the LED breathes")
    Press(cb)
    assert(not p.tick:IsShown() and not p.led:IsShown() and not FS.ControlKit.IsAnimating(p.plateFrame, "led"))
""")

case("checkbox_disabled_is_dim_with_no_led_and_a_still_grey_tick_when_on", PRELUDE + """
    local a, b = CheckBox(P, "off", 20, 20), CheckBox(P, "on", 20, 60)
    b:SetChecked(true)
    Skin(P)
    local T = FS.Theme
    a:Disable(); b:Disable()
    local pa, pb = Mine(a), Mine(b)
    Is(Colour(pa.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled face")
    Is(pa.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge")
    assert(not pa.tick:IsShown() and not pa.led:IsShown() and not pa.plate.ring2:IsShown())
    Is(Colour(pb.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled on face")
    Is(pb.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled on edge")
    assert(not pb.plate.ring2:IsShown(), "a disabled box keeps the 1 px edge")
    assert(pb.tick:IsShown())
    Is(pb.tick.vertex, T.COLOR_CTRL_DIS, 1, "disabled tick")
    assert(not pb.led:IsShown(), "no LED when disabled")
    assert(FS.ControlKit.AnimationCount() == 0, "nothing animates on a disabled box")
    Hover(a)
    Is(pa.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "a disabled box ignores the hand")
    a:Enable()
    Is(pa.plate.ring.vertex, T.COLOR_POWER, 1, "enabled again, under the hand")
""")

case("checkbox_label_is_12px_mono_and_dims_when_disabled", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    Skin(P)
    local T = FS.Theme
    local fs = cb.Text
    assert(fs.fontPath == T.FONT_MONO, "font " .. tostring(fs.fontPath))
    assert(Near(fs.size * PPU, 12, 0.01), "12 px at 1.2 px per unit, got " .. fs.size * PPU)
    Is(fs.textColor, T.COLOR_CTRL_TEXT, 1, "label")
    cb:Disable()
    Is(fs.textColor, T.COLOR_CTRL_DIS, 1, "disabled label")
    cb:Enable()
    Is(fs.textColor, T.COLOR_CTRL_TEXT, 1, "label again")
    assert(fs.alpha == 1, "the label stays visible")
""")


# -------------------------------------------------------------------------------------------------------------------
# Radio
# -------------------------------------------------------------------------------------------------------------------

case("radio_is_a_16_px_diamond_with_a_6_px_node_and_the_mockups_six_states", PRELUDE + """
    local rb = RadioBtn(P, "Plate", 20, 20)
    Skin(P)
    NoDegrade()
    local p, T = Mine(rb), FS.Theme
    assert(p and p.built and p.kind == "radio")
    -- 16 units x 1.2 = 19 px, so the plate sits floor((19 - 16) / 2) = 1 px in
    assert(rb.w == 16 and rb.h == 16)
    Expect(p.plateFrame, rb, 1, 1, 16, 16, "plate")
    for _, name in ipairs({ "fill", "ring1", "ring2" }) do Expect(p[name], p.plateFrame, 0, 0, 16, 16, name) end
    Expect(p.node, p.plateFrame, 5, 5, 6, 6, "node")
    assert(p.fill.path:find("ctl_diamond_fill") and p.ring1.path:find("ctl_diamond_ring1") and p.ring2.path:find("ctl_diamond_ring2"))
    assert(p.node.path:find("ctl_diamond_node") and Near(p.node.coords[2], 0.75) and Near(p.node.coords[4], 0.75), "6 of the 8 texel canvas")
    -- off
    Is(p.fill.vertex, T.COLOR_CTRL_INK, 1, "off face"); Is(p.ring1.vertex, T.COLOR_CTRL_DIM, 1, "off edge")
    assert(p.ring1:IsShown() and not p.ring2:IsShown() and not p.node:IsShown())
    -- hover
    Hover(rb)
    Is(p.ring1.vertex, T.COLOR_POWER, 1, "hover edge")
    Unhover(rb)
    -- on
    Choose(rb, { rb })
    Step(0.1)
    Is(p.fill.vertex, T.COLOR_CTRL_SEL, 1, "on face"); Is(p.ring2.vertex, T.COLOR_HEALTH, 1, "on edge")
    assert(p.ring2:IsShown() and not p.ring1:IsShown() and p.node:IsShown())
    Is(p.node.vertex, T.COLOR_HEALTH, 1, "node")
    -- on + hover
    Hover(rb)
    Is(p.ring2.vertex, T.COLOR_POWER, 1, "on + hover edge"); Is(p.node.vertex, T.COLOR_HEALTH, 1, "node under the hand")
    Unhover(rb)
    -- disabled on: the node stays, grey, nothing moves
    rb:Disable()
    Is(p.fill.vertex, T.COLOR_CTRL_DISFILL, 1, "disabled on face"); Is(p.ring1.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled on edge")
    assert(p.ring1:IsShown() and not p.ring2:IsShown() and p.node:IsShown())
    Is(p.node.vertex, T.COLOR_CTRL_DIS, 1, "disabled node")
    assert(not p.ring:IsShown() and FS.ControlKit.AnimationCount() == 0)
    assert(WholePixels(rb, P, "radio") >= 6)
""")

case("radio_ring_grows_from_07_to_19_of_the_diamond_and_fades_out", PRELUDE + """
    local rb = RadioBtn(P, "Plate", 20, 20)
    Skin(P)
    local p = Mine(rb)
    Choose(rb, { rb })
    Step(0)
    -- the ring starts at 0.7 of the diamond, centred on it, at 0.9 alpha
    Expect(p.ring, p.plateFrame, 8 - 5.6, 8 - 5.6, 11.2, 11.2, "ring at 0")
    assert(Near(p.ring.vertex[4], 0.9, 0.001))
    Is(p.ring.vertex, FS.Theme.COLOR_HEALTH, 0.9, "ring colour")
    assert(p.ring.path:find("ctl_diamond_ring1"))
    -- halfway through its 1.8 s the ease out is at 0.75: 0.7 + 1.2 * 0.75 = 1.6 of 16 px, alpha 0.9 * 0.25
    Step(0.9)
    Expect(p.ring, p.plateFrame, 8 - 12.8, 8 - 12.8, 25.6, 25.6, "ring at half")
    assert(Near(p.ring.vertex[4], 0.225, 0.003), "ring alpha " .. p.ring.vertex[4])
    -- and it starts over: 1.85 s in, 0.05 s into the second period, the ease out is at 0.0548
    Step(0.95)
    local size = 16 * (0.7 + 1.2 * 0.0548)
    Expect(p.ring, p.plateFrame, 8 - size / 2, 8 - size / 2, size, size, "ring in the second period")
""")

case("radio_group_hangs_on_one_rail_and_the_node_jumps_along_it", PRELUDE + """
    local r1, r2, r3 = RadioBtn(P, "plate", 20, 20), RadioBtn(P, "compact", 20, 52), RadioBtn(P, "hidden", 20, 84)
    assert(Skin(P) == 3)
    local p1, p2, p3 = Mine(r1), Mine(r2), Mine(r3)
    -- the head owns the rail: one pixel column through the diamond centres, from the first centre to the last (64 units
    -- apart = 76.8, rounded to 77 px), under the diamonds, violet at half alpha
    assert(p1.rail:IsShown() and not p2.rail:IsShown() and not p3.rail:IsShown())
    Expect(p1.rail, p1.plateFrame, 8, 8, 1, 77, "rail")
    Is(p1.rail.color, FS.Theme.COLOR_BORDER, 0.5, "rail")
    assert(p1.rail.layer == "BACKGROUND" and p1.rail.sub < p1.fill.sub, "the rail draws behind the diamond")
    local group = { r1, r2, r3 }
    Choose(r1, group)
    Step(0.5)
    Expect(p1.node, p1.plateFrame, 5, 5, 6, 6, "the first choice appears in place")
    Choose(r2, group)
    Step(0)
    -- the node starts where the last choice was, 32 units = 38.4 px up, and slides down over 0.16 s
    Expect(p2.node, p2.plateFrame, 5, 5 - 38.4, 6, 6, "node at the start of the jump")
    Step(0.08)
    local _, y = Px(p2.node, p2.plateFrame)
    assert(y > 5 - 38.4 and y < 5, "node mid jump at " .. y)
    Step(0.1)
    Expect(p2.node, p2.plateFrame, 5, 5, 6, 6, "node arrived")
    assert(not FS.ControlKit.IsAnimating(p2.plateFrame, "slide"))
    assert(not p1.node:IsShown() and p2.node:IsShown() and not p3.node:IsShown())
    -- a lone radio has no rail
    local lone = RadioBtn(UIParent, "lone", 600, 20)
    FS.CheckSkins.Skin(lone); FlushTimers()
    assert(not Mine(lone).rail:IsShown())
""")

# -------------------------------------------------------------------------------------------------------------------
# Skin discipline, shared by every control
# -------------------------------------------------------------------------------------------------------------------

case("blizzard_art_is_held_the_label_stays_and_nothing_is_written_to_the_widget", PRELUDE + """
    local cb, rb = CheckBox(P, "Label", 20, 20), RadioBtn(P, "Radio", 20, 60)
    Skin(P)
    NoDegrade()
    for _, b in ipairs({ cb, rb }) do
        for _, key in ipairs({ "normalTex", "pushedTex", "highlightTex", "checkedTex", "disabledCheckedTex" }) do
            if b[key] then
                assert(b[key].alpha == 0, key .. " is not held")
                b[key]:SetAlpha(1) -- Blizzard re-asserts its art; the hold writes 0 again
                assert(b[key].alpha == 0, key .. " came back")
            end
        end
        assert(next(b.scripts) == nil, "a script was written to a Blizzard widget")
        assert(b.w == (b == cb and 26 or 16), "resized")
        assert(#b.points == 1 and b.points[1].point == "TOPLEFT", "re-anchored")
        assert(b.shown and b.parent == P, "reparented or hidden")
    end
    assert(cb.Text.alpha == 1 and rb.text.alpha == 1)
""")

case("detection_is_by_shape_never_by_name", PRELUDE + """
    local check, mini, radio = CheckBox(P, "a", 20, 20), MinimalCheckBox(P, 20, 60), RadioBtn(P, "b", 20, 100)
    local radial = RadioBtn(P, "c", 20, 140); radial.w, radial.h = 18, 18
    radial.normalTex.path = nil; radial.normalTex.atlas = "common-dropdown-tickradial"; radial.text = nil
    local action, row = ActionBtn(P, 200, 20), RowBtn(P, 200, 80)
    local big = CheckBox(P, "big", 200, 140, 64, 64)
    local plainButton = blz("Button", nil, P, 26, 26, 200, 220)
    plainButton.checkedTex = tex(plainButton)
    local frame = blz("Frame", nil, P, 26, 26, 260, 220)
    assert(Cks().Kind(check) == "check" and Cks().Kind(mini) == "check", "UICheckButton and MinimalCheckbox shapes")
    assert(Cks().Kind(radio) == "radio" and Cks().Kind(radial) == "radio", "UIRadioButton by its text key, a radial by its atlas")
    assert(Cks().Kind(action) == nil, "an action button has an icon, a count and a cooldown")
    assert(Cks().Kind(row) == nil, "a list row is a CheckButton as wide as the list")
    assert(Cks().Kind(big) == nil, "too big for a checkbox")
    assert(Cks().Kind(plainButton) == nil and Cks().Kind(frame) == nil, "not a CheckButton")
    assert(Skin(P) == 4, "skinned " .. Skin(P))
    assert(Mine(action) == nil and Mine(row) == nil and Mine(big) == nil)
    -- a stray name changes nothing
    local named = blz("CheckButton", "OptionsCheckThing", P, 26, 26, 300, 20)
    assert(Cks().Kind(named) == nil, "no checked texture, no checkbox, whatever it is called")
""")

case("sweep_skins_nested_controls_once_and_again_when_a_page_is_shown", PRELUDE + """
    local page = blz("Frame", nil, P, 380, 280, 10, 10)
    local nested = blz("Frame", nil, page, 300, 100, 10, 10)
    local c1 = CheckBox(nested, "one", 10, 10)
    local r1 = RadioBtn(page, "two", 10, 150)
    assert(Skin(P) == 2)
    assert(Skin(P) == 0, "a second sweep skins nothing new")
    local objects, hooks = ObjCount(), HookCount()
    assert(Skin(P) == 0 and ObjCount() == objects and HookCount() == hooks, "a repeat builds nothing and hooks nothing")
    FS.PanelSkins.SweepOnShow(P)
    local late = CheckBox(page, "late", 10, 200)
    P:Hide(); P:Show()
    assert(Mine(late) and Mine(late).built, "a control added later is skinned when the panel is shown again")
""")

case("a_control_met_in_combat_is_skinned_when_combat_ends", PRELUDE + """
    local a, b = CheckBox(P, "a", 20, 20), CheckBox(P, "b", 20, 60)
    local before = ObjCount()
    __combat = true
    assert(Skin(P) == 0)
    assert(Mine(a) == nil and Mine(b) == nil, "nothing is skinned in combat")
    assert(ObjCount() == before + 2 or ObjCount() == before + 1, "only the regen watcher is built")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    FlushTimers()
    assert(Mine(a) and Mine(a).built and Mine(b) and Mine(b).built, "both skinned after combat")
    NoDegrade()
""")

case("a_change_of_pixel_scale_reseats_every_edge_on_a_whole_pixel", PRELUDE + """
    local cb, rb = CheckBox(P, "Label", 20, 20), RadioBtn(P, "Radio", 20, 60)
    cb:SetChecked(true); rb:SetChecked(true)
    Skin(P)
    local a, b = Mine(cb), Mine(rb)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w = math.floor(26 * scale + 0.5)
        Expect(a.plateFrame, cb, math.floor((w - 16) / 2), math.floor((w - 16) / 2), 16, 16, "check plate at " .. scale)
        local v = math.floor(16 * scale + 0.5)
        Expect(b.plateFrame, rb, math.floor((v - 16) / 2), math.floor((v - 16) / 2), 16, 16, "radio plate at " .. scale)
        Expect(a.led, a.plateFrame, 11, 2, 3, 3, "led at " .. scale)
        Expect(b.node, b.plateFrame, 5, 5, 6, 6, "node at " .. scale)
        WholePixels(cb, P, "check at " .. scale)
        WholePixels(rb, P, "radio at " .. scale)
    end
""")

case("a_hidden_control_runs_no_animation_and_a_shown_one_resumes", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    cb:SetChecked(true)
    Skin(P)
    local p = Mine(cb)
    Step(0.2)
    local alpha = p.led.color[4]
    P:Hide()
    Step(1.0)
    assert(p.led.color[4] == alpha, "the LED of a hidden box moved")
    P:Show()
    Step(0.2)
    assert(p.led.color[4] ~= alpha, "the LED did not resume")
""")

case("a_secret_checked_value_reads_as_unchecked_without_an_error", PRELUDE + """
    local cb = CheckBox(P, "Label", 20, 20)
    cb.GetChecked = function() return { __secret = true } end
    Skin(P)
    NoDegrade()
    local p = Mine(cb)
    assert(p and p.built)
    assert(not p.tick:IsShown() and not p.led:IsShown())
    Is(Colour(p.plate.fill), FS.Theme.COLOR_CTRL_INK, 1, "face")
""")



# -------------------------------------------------------------------------------------------------------------------
# Closed dropdown button, its open list (hover brackets, the current value's LED, the scan wipe) and the lock-on reticle
# -------------------------------------------------------------------------------------------------------------------

case("dropdown_tokens_are_the_mockups_numbers", PRELUDE + """
    local K = FS.Layout.Controls
    assert(K.DD_ZONE == 28 and K.DD_SWATCH == 8 and K.DD_SWATCH_X == 10 and K.DD_LABEL_X == 26 and K.DD_TEXT_RIGHT == 34, "dropdown body")
    assert(K.DD_CHEV_X == 24 and K.DD_MIN_W == 48 and K.DD_RULE_PAD == 5, "chevron and gates")
    assert(K.ROW_PAD == 2 and K.ROW_LED_W == 4 and K.ROW_LED_H == 8 and K.ROW_LED_X == 2 and K.ROW_WASH_ALPHA == 0.18, "menu row")
    assert(K.RETICLE_LEN == 4 and K.WIPE_TIME == 0.2 and K.WIPE_FRONT == 2, "reticle and wipe")
""")

case("dropdown_is_a_28_px_body_with_swatch_label_hairline_and_chevron", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    assert(Skin(P) == 1, "the sweep skins the dropdown")
    local p, T = Dd().Parts(b), FS.Theme
    assert(p and p.built)
    Expect(p.plate.fill, b, 0, 0, 196, 28, "face")
    Expect(p.plate.ring, b, 0, 0, 196, 28, "edge")
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    Expect(p.swatch, b, 10, 10, 8, 8, "swatch")
    Is(p.swatch.color, T.COLOR_BORDER, 1, "swatch default")
    Expect(p.hair, b, 196 - 28, 5, 1, 18, "hairline 28 from the right")
    Is(p.hair.color, T.COLOR_CTRL_HAIR, 1, "hairline")
    Expect(p.chev, b, 196 - 24, 6, 16, 16, "chevron")
    assert(p.chev.path:find("ctl_chev"), p.chev.path)
    Is(p.chev.vertex, T.COLOR_MUTED, 1, "chevron")
    local l, _, r = Px(b.Text, b)
    assert(Near(l, 26) and Near(r, 196 - 34), "label from 26 to 34 short of the right: " .. l .. " " .. r)
    assert(b.Text.fontPath == T.FONT_MONO and Near(b.Text.size * PPU, 12, 0.01), "12 px mono label")
    Is(b.Text.textColor, T.COLOR_CTRL_TEXT, 1, "label")
    assert(b.Background.alpha == 0 and b.Arrow.alpha == 0, "the stock art is held")
    b.Arrow:SetAlpha(1)
    assert(b.Arrow.alpha == 0, "Blizzard's alpha write is undone")
    assert(not p.glow:IsShown() and not p.led:IsShown(), "no glow or LED at rest")
    Expect(b, P, 20 * 1.2, 20 * 1.2, 196, 28, "the stock rect is untouched")
    NoDegrade()
    WholePixels(b, b, "dropdown", { b.Background, b.Arrow })
""")

case("dropdown_hover_and_open_go_cyan_open_flips_the_chevron_and_adds_glow_and_led", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Dd().Parts(b), FS.Theme
    Hover(b)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    Is(p.chev.vertex, T.COLOR_POWER, 1, "hover chevron")
    assert(not p.glow:IsShown(), "hover has no glow")
    Unhover(b)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle again")
    OpenList(b)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "open edge")
    Is(p.chev.vertex, T.COLOR_POWER, 1, "open chevron")
    assert(p.glow:IsShown() and p.led:IsShown(), "open: glow and LED underline")
    Expect(p.glow, b, -3, -3, 202, 34, "glow 3 px out")
    Is(p.glow.color, T.COLOR_POWER, 0.08, "glow")
    Expect(p.led, b, 1, 25, 194, 2, "LED underline 3 up from the bottom")
    local c = p.chev.coords
    assert(c and c[1] == 0 and c[2] == 1 and c[3] == 1 and c[4] == 0, "the chevron flips upright")
    Step(0.8)
    assert(Near(p.led.color[4], 0.3, 0.02), "LED at the bottom of its breath, got " .. p.led.color[4])
    CloseList(b)
    assert(not p.glow:IsShown() and not p.led:IsShown(), "closed: no glow or LED")
    c = p.chev.coords
    assert(c == nil or (c[3] == 0 and c[4] == 1), "the chevron points down again")
    assert(not FS.ControlKit.IsAnimating(p.over, "led"), "nothing runs closed")
    NoDegrade()
""")

case("dropdown_disabled_is_the_darkest_ink_and_dim_text_and_blizzards_state_colours_never_win", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Dd().Parts(b), FS.Theme
    b:Disable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge")
    Is(p.swatch.color, T.COLOR_CTRL_DISEDGE, 1, "disabled swatch")
    Is(p.hair.color, T.COLOR_CTRL_DISEDGE, 1, "disabled hairline")
    Is(p.chev.vertex, T.COLOR_CTRL_DIS, 1, "disabled chevron")
    Is(b.Text.textColor, T.COLOR_CTRL_DIS, 1, "disabled label")
    Hover(b)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "a disabled dropdown does not light under the hand")
    b:Enable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "enabled face")
    -- the stock OnButtonStateChanged writes the label's colour; ours is painted after it
    b:OnButtonStateChanged()
    Is(b.Text.textColor, T.COLOR_CTRL_TEXT, 1, "our label colour survives the stock state colour")
    NoDegrade()
""")

case("dropdown_swatch_takes_the_colour_of_the_current_choice", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Dd().Parts(b), FS.Theme
    Dd().SetSwatch(b, T.COLOR_POWER)
    Is(p.swatch.color, T.COLOR_POWER, 1, "a chosen swatch")
    b:Disable()
    Is(p.swatch.color, T.COLOR_CTRL_DISEDGE, 1, "disabled wins")
    b:Enable()
    Is(p.swatch.color, T.COLOR_POWER, 1, "the choice returns")
    Dd().SetSwatch(b, nil)
    Is(p.swatch.color, T.COLOR_BORDER, 1, "no choice, the violet default")
    Dd().SetSwatch(b, { __secret = true })
    Is(p.swatch.color, T.COLOR_BORDER, 1, "a secret colour is ignored")
""")

case("dropdown_detection_is_by_shape_and_an_arrow_only_or_tiny_or_tall_one_is_left_alone", PRELUDE + """
    local ok = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    local filter = DropdownW(P, 20, 60, 162 / PPU, 18 / PPU)
    local arrowOnly = blz("Button", nil, P, 25 / PPU, 25 / PPU, 20, 100)
    arrowOnly.intrinsic = "DropdownButton"; arrowOnly.Arrow = tex(arrowOnly, nil, "OVERLAY")
    function arrowOnly:IsMenuOpen() return false end
    local tiny = DropdownW(P, 20, 140, 40 / PPU, 28 / PPU)
    local tall = DropdownW(P, 20, 180, 196 / PPU, 90 / PPU)
    local plain = blz("Button", nil, P, 196 / PPU, 28 / PPU, 20, 280)
    plain.Left, plain.Middle, plain.Right = tex(plain), tex(plain), tex(plain)
    plain.Text = fstring(plain, "Accept")
    local held = DropdownW(P, 300, 20, 196 / PPU, 28 / PPU)
    held.Background:SetAlpha(0)
    local legacy = blz("Frame", nil, P, 196 / PPU, 28 / PPU, 300, 60)
    legacy.Left, legacy.Middle, legacy.Right, legacy.Text = tex(legacy), tex(legacy), tex(legacy), fstring(legacy, "x")
    assert(Dd().Kind(ok) == "dropdown" and Dd().Kind(filter) == "dropdown", "a dropdown and a filter dropdown")
    assert(Dd().Kind(arrowOnly) == nil, "a labelless button without the stock arrow art is not an arrow dropdown")
    assert(Dd().Kind(tiny) == nil and Dd().Kind(tall) == nil, "too small or too tall")
    assert(Dd().Kind(plain) == nil, "a text button is not a dropdown")
    assert(Dd().Kind(held) == nil, "art another skin holds is that skin's")
    assert(Dd().Kind(legacy) == nil, "a legacy UIDropDownMenu frame is not a DropdownButton")
    assert(Skin(P) == 2, "the sweep skins the two dropdowns only")
""")

case("an_arrow_dropdown_is_a_square_cut_key_with_the_kits_chevron_and_its_gold_art_held", PRELUDE + """
    -- the talents search options button (25 x 25, Arrow) and the spellbook settings button (15 x 16, Icon)
    local function ArrowDd(w, h, key, y)
        local b = blz("Button", nil, P, w / PPU, h / PPU, 20, y)
        b.intrinsic = "DropdownButton"
        b[key] = tex(b, nil, "OVERLAY"); b[key].atlas = "common-dropdown-a-button"
        b.open = false
        function b:IsMenuOpen() return self.open end
        function b:OnMenuOpened() self.open = true end
        return b
    end
    local search, settings = ArrowDd(30, 30, "Arrow", 20), ArrowDd(18, 19, "Icon", 80)
    assert(Dd().Kind(search) == "arrow" and Dd().Kind(settings) == "arrow")
    assert(Skin(P) == 2, "the sweep skins both")
    FlushTimers()
    local p, q, T = Dd().Parts(search), Dd().Parts(settings), FS.Theme
    assert(p.arrow and not p.swatch and not p.led, "a key: no swatch, no LED")
    Expect(p.plate.fill, search, 0, 0, 30, 30, "the key fills the 30 px rect")
    Expect(p.chev, search, 7, 7, 16, 16, "the chevron centred")
    Expect(q.plate.fill, settings, -3, -2, 24, 24, "a small rect gets the 24 px key, centred")
    assert(search.Arrow.alpha == 0 and settings.Icon.alpha == 0, "the gold arrow art is held")
    Is(p.chev.vertex, T.COLOR_MUTED, 1, "idle chevron")
    Hover(search)
    Is(p.chev.vertex, T.COLOR_POWER, 1, "hover chevron goes cyan")
    search:OnMenuOpened(); FlushTimers()
    local c = p.chev.coords
    assert(c[3] == 1 and c[4] == 0, "open flips the chevron")
""")

case("a_dropdown_is_skinned_once_and_one_met_in_combat_waits_for_combat_to_end", PRELUDE + """
    local a = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    assert(Skin(P) == 1)
    local hooks, objs = HookCount(), ObjCount()
    assert(Skin(P) == 0 and HookCount() == hooks and ObjCount() == objs, "a repeat sweep builds nothing")
    local late = DropdownW(P, 20, 80, 196 / PPU, 28 / PPU)
    __combat = true
    assert(Skin(P) == 0)
    assert(Dd().Parts(late) == nil, "nothing is skinned in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(Dd().Parts(late) and Dd().Parts(late).built, "skinned after combat")
    NoDegrade()
""")

case("a_change_of_pixel_scale_lays_the_dropdown_out_again_on_whole_pixels", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    Skin(P)
    local p = Dd().Parts(b)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w, h = Round(b.w * scale), Round(b.h * scale)
        Expect(p.plate.ring, b, 0, 0, w, h, "edge at " .. scale)
        Expect(p.hair, b, w - 28, 5, 1, h - 10, "hairline at " .. scale)
        Expect(p.chev, b, w - 24, math.floor((h - 16) / 2), 16, 16, "chevron at " .. scale)
        Expect(p.swatch, b, 10, math.floor((h - 8) / 2), 8, 8, "swatch at " .. scale)
        local l, _, r = Px(b.Text, b)
        assert(Near(l, 26) and Near(r, b.w * scale - 34), "label at " .. scale .. ": " .. l .. " " .. r)
        OpenList(b)
        WholePixels(b, b, "dropdown at " .. scale, { b.Background, b.Arrow })
        CloseList(b)
    end
""")

case("a_hidden_dropdown_runs_no_animation_and_a_shown_one_resumes", PRELUDE + """
    local b = DropdownW(P, 20, 20, 196 / PPU, 28 / PPU)
    Skin(P)
    local p = Dd().Parts(b)
    OpenList(b)
    Step(0.3)
    local alpha = p.led.color[4]
    P:Hide()
    Step(0.7)
    assert(p.led.color[4] == alpha, "the LED of a hidden dropdown moved")
    P:Show()
    Step(0.1)
    assert(p.led.color[4] ~= alpha, "it did not resume")
""")

case("the_lock_on_reticle_is_four_corners_of_2_px_bars_around_a_rect_at_a_pad", PRELUDE + """
    local Kit = FS.ControlKit
    local ret = Kit.Reticle(P, "OVERLAY", 3)
    Kit.SeatReticle(ret, 20, 30, 40, 30, 4, 6)
    -- the mockup's reticle(x, y, w, h, c, pad, len): the path runs at X = x - pad ... and a 2 px stroke is centred on it
    local X, Y, W, H = 20 - 4, 30 - 4, 40 + 8, 30 + 8
    Expect(ret.tlH, P, X - 1, Y - 1, 7, 2, "top left, across")
    Expect(ret.tlV, P, X - 1, Y + 1, 2, 5, "top left, down")
    Expect(ret.trH, P, X + W - 6, Y - 1, 7, 2, "top right, across")
    Expect(ret.trV, P, X + W - 1, Y + 1, 2, 5, "top right, down")
    Expect(ret.brH, P, X + W - 6, Y + H - 1, 7, 2, "bottom right, across")
    Expect(ret.brV, P, X + W - 1, Y + H - 6, 2, 5, "bottom right, up")
    Expect(ret.blH, P, X - 1, Y + H - 1, 7, 2, "bottom left, across")
    Expect(ret.blV, P, X - 1, Y + H - 6, 2, 5, "bottom left, up")
    Kit.PaintReticle(ret, FS.Theme.COLOR_POWER, 1)
    Is(ret.tlH.color, FS.Theme.COLOR_POWER, 1, "cyan")
    Kit.ShowReticle(ret, false)
    assert(not ret.tlH:IsShown() and not ret.blV:IsShown(), "hidden")
    Kit.ShowReticle(ret, true)
    assert(ret.brH:IsShown())
""")

case("menu_rows_get_lock_on_brackets_a_violet_wash_and_a_pink_led_on_the_current_value", PRELUDE + """
    local T = FS.Theme
    local menu = MenuW({ { text = "general", selected = true }, { text = "combat log" }, { text = "trade" } })
    OpenMenuFrame(menu)
    Step(0.4)
    local r1, r2 = menu.rows[1], menu.rows[2]
    local d1, d2 = Dd().RowParts(r1), Dd().RowParts(r2)
    assert(d1 and d2, "every row is decorated")
    assert(d1.led:IsShown() and not d2.led:IsShown(), "the pink LED marks the current value only")
    Expect(d1.led, r1, 2, 8, 4, 8, "LED 4 x 8, 2 in, centred in the 24 px row")
    Is(d1.led.color, T.COLOR_HEALTH, d1.led.color[4], "pink LED")
    assert(d1.led.color[4] >= 0.3 and d1.led.color[4] <= 1, "the LED breathes between 0.3 and 1")
    assert(not d2.wash:IsShown() and not d2.reticle.tlH:IsShown(), "no hover, no wash or brackets")
    Hover(r2)
    assert(d2.wash:IsShown() and d2.reticle.tlH:IsShown())
    Expect(d2.wash, r2, 0, 0, 216, 24, "wash over the row")
    Is(d2.wash.color, T.COLOR_BORDER, 0.18, "violet wash")
    -- brackets on the rect inset 2, pad 0, arms 4 (the mockup: reticle(x + 6, ry + 2, w - 12, rh - 4, cyan, 0, 4))
    Expect(d2.reticle.tlH, r2, 1, 1, 5, 2, "top left across")
    Expect(d2.reticle.tlV, r2, 1, 3, 2, 3, "top left down")
    Expect(d2.reticle.trH, r2, 210, 1, 5, 2, "top right across")
    Expect(d2.reticle.brV, r2, 213, 18, 2, 3, "bottom right up")
    Expect(d2.reticle.blH, r2, 1, 21, 5, 2, "bottom left across")
    Is(d2.reticle.tlH.color, T.COLOR_POWER, 1, "cyan brackets")
    Unhover(r2)
    assert(not d2.wash:IsShown() and not d2.reticle.tlH:IsShown(), "gone with the hand")
    -- a pooled row meets a new description: the LED follows what the row is now
    r1.GetElementDescription = function() return { IsSelected = function() return false end } end
    r2.GetElementDescription = function() return { IsSelected = function() return true end } end
    r1:RunScript("OnShow"); r2:RunScript("OnShow")
    assert(not d1.led:IsShown() and d2.led:IsShown(), "the LED moved with the selection")
    for _, r in ipairs(menu.rows) do assert(r.alpha == 1) end
    NoDegrade()
""")

case("menu_scan_wipe_reveals_the_rows_from_the_top_behind_a_cyan_front_edge_and_restores_them", PRELUDE + """
    local T = FS.Theme
    local menu = MenuW({ { text = "a" }, { text = "b", alpha = 0.5 }, { text = "c" } })
    OpenMenuFrame(menu)
    local scan = Dd().MenuParts(menu)
    assert(scan, "the menu has a scan frame")
    for _, r in ipairs(menu.rows) do assert(r.alpha == 0, "every row waits behind the front at the start") end
    assert(scan.front:IsShown())
    Step(0.06)
    assert(menu.rows[1].alpha == 1 and menu.rows[2].alpha == 0 and menu.rows[3].alpha == 0, "the front has passed the first row only")
    local _, ft, _, fb = Px(scan.front, menu)
    assert(Near(fb - ft, 2), "the front edge is 2 px")
    Is(scan.front.color, T.COLOR_POWER, 1, "cyan front edge")
    local _, t2 = Px(scan.front, menu)
    Step(0.06)
    local _, t3 = Px(scan.front, menu)
    assert(t3 > t2, "the front moves down")
    Step(0.3)
    assert(menu.rows[1].alpha == 1 and menu.rows[2].alpha == 0.5 and menu.rows[3].alpha == 1, "every row is back to the alpha Blizzard gave it")
    assert(not scan.front:IsShown() and not FS.ControlKit.IsAnimating(scan.driver, menu), "the wipe is over")
    -- closed mid-wipe: nothing is left invisible for the next pool user
    OpenMenuFrame(menu)
    Step(0.05)
    menu:Hide()
    Step(0.05)
    assert(menu.rows[1].alpha == 1 and menu.rows[2].alpha == 0.5 and menu.rows[3].alpha == 1, "a menu closed mid-wipe gives its rows back")
    -- and a row that was left half hidden by anything else is not trusted as the original
    OpenMenuFrame(menu)
    OpenMenuFrame(menu)
    Step(0.5)
    assert(menu.rows[2].alpha == 0.5, "opening a menu twice does not make 0 the original alpha")
    NoDegrade()
""")

case("a_submenu_is_decorated_through_the_acquired_callback_and_context_menus_too", PRELUDE + """
    local desc = NewDescription()
    local menu = MenuW({ { text = "a", selected = true } })
    OpenMenuFrame(menu, desc)
    Step(0.4)
    assert(type(desc.acquired) == "function", "the callback for submenus is registered")
    local sub = MenuW({ { text = "x", selected = true }, { text = "y" } }, 600, 300)
    MANAGER.open = sub
    desc.acquired()
    assert(Dd().RowParts(sub.rows[1]) and Dd().RowParts(sub.rows[1]).led:IsShown(), "the submenu rows are decorated")
    local ctx = MenuW({ { text = "whisper" } }, 900, 300)
    MANAGER.open = ctx
    ctx.shown = true
    MANAGER:OpenContextMenu(nil, NewDescription())
    assert(Dd().RowParts(ctx.rows[1]), "a context menu is decorated too")
    NoDegrade()
""")

case("the_legacy_list_gets_the_same_brackets_led_and_wipe_on_show", PRELUDE + """
    local T = FS.Theme
    local list = LegacyList({ { text = "general", checked = true }, { text = "trade" } })
    Dd().HookLegacy()
    list:Show()
    local r1, r2 = list.rows[1], list.rows[2]
    assert(r1.alpha == 0 and r2.alpha == 0, "a legacy list is wiped open too")
    Step(0.4)
    assert(r1.alpha == 1 and r2.alpha == 1)
    local d1, d2 = Dd().RowParts(r1), Dd().RowParts(r2)
    assert(d1 and d2 and d1.led:IsShown() and not d2.led:IsShown(), "the checked row carries the LED")
    Hover(r2)
    assert(d2.wash:IsShown() and d2.reticle.tlH:IsShown())
    Unhover(r2)
    assert(not d2.wash:IsShown())
    Dd().HookLegacy()
    local hooks = HookCount()
    Dd().HookLegacy()
    assert(HookCount() == hooks, "hooking twice adds nothing")
    NoDegrade()
""")

SCENES["checks"] = """
    local FS = Load()
    local P = Panel()
    local states = { "off", "hover", "on", "on + hover", "disabled", "disabled on" }
    local checks, radios = {}, {}
    for i, s in ipairs(states) do
        local x = 10 + (i - 1) * 64
        checks[i] = CheckBox(P, "label", x, 20)
        radios[i] = RadioBtn(P, "label", x, 70)
    end
    local g1, g2, g3 = RadioBtn(P, "plate", 10, 130), RadioBtn(P, "compact", 10, 160), RadioBtn(P, "hidden", 10, 190)
    Skin(P)
    for i, s in ipairs(states) do
        if s:find("on") and s ~= "disabled" then checks[i]:SetChecked(true); radios[i]:SetChecked(true) end
        if s:find("hover") then Hover(checks[i]); Hover(radios[i]) end
        if s:find("disabled") then checks[i]:Disable(); radios[i]:Disable() end
    end
    Choose(g2, { g1, g2, g3 })
    Step(1.0)
    return DumpOps({ P })
"""


SCENES["sliders"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 400, 330
    local rows = {}
    for i = 1, 4 do rows[i] = SteppedSlider(P, 20, 20 + (i - 1) * 70, { value = i == 3 and 70 or 50 }) end
    Skin(P)
    Hover(rows[2].Slider)
    rows[3].Slider.dragging = true; rows[3].Slider:RunScript("OnMouseDown")
    rows[4].Slider:Disable(); rows[4].Back:Disable(); rows[4].Forward:Disable()
    for _, f in ipairs(rows) do f.RightText:SetText("50%") end
    Step(0.3)
    return DumpOps({ P })
"""


# -------------------------------------------------------------------------------------------------------------------
# Slider
# -------------------------------------------------------------------------------------------------------------------

case("slider_tokens_are_the_mockups_numbers", PRELUDE + """
    local K = FS.Layout.Controls
    assert(K.CELL_W == 6 and K.CELL_H == 8 and K.CELL_PITCH == 8)
    assert(K.BRACKET_SPINE == 9 and K.BRACKET_HALF == 10 and K.BRACKET_ARM == 4 and K.STROKE == 2)
    assert(K.TAG_H == 18 and K.TAG_TOP == 34 and K.TAG_CUT == 4 and K.TAG_STEM == 4 and K.TAG_STEM_TOP == 16)
    assert(K.WASH_W == 28 and K.WASH_H == 24 and K.WASH_ALPHA == 0.10 and K.KEY == 20 and K.KEY_CUT == 4)
    assert(K.MARCH_PERIOD == 0.6 and K.CHEV_PITCH == 8 and K.CHEV_ALPHA == 0.18)
    assert(K.TAG_TEXT == 11 and K.LABEL_TEXT == 12 and K.SMALL_TEXT == 10 and K.KEY_GAP == 8 and K.TAG_LABEL_Y == 10)
    assert(K.KEY_MINUS[1] == 6 and K.KEY_MINUS[2] == 9 and K.KEY_MINUS[3] == 8 and K.KEY_MINUS[4] == 2)
    assert(K.KEY_PLUS_UPRIGHT[1] == 9 and K.KEY_PLUS_UPRIGHT[2] == 6 and K.KEY_PLUS_UPRIGHT[3] == 2 and K.KEY_PLUS_UPRIGHT[4] == 8)
""")

case("slider_cells_are_6_by_8_on_a_pitch_of_8_and_the_count_follows_the_track", PRELUDE + """
    -- 232 px wide: the mockup's 29 cells (8 * 29 - 2 = 230 wide, centred in 232)
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    assert(Skin(P) == 1)
    NoDegrade()
    local p = FS.SliderSkins.Parts(s)
    assert(p and p.built and p.n == 29, "cells " .. tostring(p and p.n))
    assert(s.w == 232 / PPU and s.h == 20 / PPU, "the stock rect was resized")
    local x0, y0 = 1, 6
    assert(p.x0 == x0 and p.cy == 10)
    for i = 1, 29 do
        Expect(p.cells[i], p.host, x0 + (i - 1) * 8, y0, 6, 8, "cell " .. i)
    end
    -- the stock 144 x 17 slider is 173 x 20 px: 21 cells, 166 wide, 3 in
    local t = SliderBox(P, 20, 80)
    FS.ControlKit.SkinWidget(t)
    local q = FS.SliderSkins.Parts(t)
    assert(q.n == 21 and q.x0 == 3, "21 cells, got " .. q.n .. " at " .. q.x0)
    Expect(q.cells[21], q.host, 3 + 20 * 8, 6, 6, 8, "last cell")
    assert(WholePixels(s, P, "slider") >= 29 and WholePixels(t, P, "stock slider") >= 21)
""")

case("slider_lit_cells_are_violet_the_head_cyan_pink_while_dragged_and_dim_when_disabled", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p, T = FS.SliderSkins.Parts(s), FS.Theme
    -- 50 % of 29 cells is 14.5, which rounds up to 15 lit: cell 15 is the head
    assert(p.lit == 15)
    for i = 1, 29 do
        local c = Colour(p.cells[i])
        if i < 15 then Is(c, T.COLOR_BORDER, 1, "lit cell " .. i)
        elseif i == 15 then Is(c, T.COLOR_POWER, 1, "head cell")
        else Is(c, T.COLOR_CTRL_CELL, 1, "unlit cell " .. i) end
    end
    s.dragging = true; s:RunScript("OnMouseDown")
    Is(Colour(p.cells[15]), T.COLOR_HEALTH, 1, "head while dragging")
    Is(Colour(p.cells[14]), T.COLOR_BORDER, 1, "lit cells stay violet while dragging")
    s.dragging = false; s:RunScript("OnMouseUp")
    Is(Colour(p.cells[15]), T.COLOR_POWER, 1, "head after the drag")
    s:Disable()
    for i = 1, 15 do Is(Colour(p.cells[i]), T.COLOR_CTRL_DISEDGE, 1, "disabled lit cell " .. i) end
    Is(Colour(p.cells[16]), T.COLOR_CTRL_CELL, 1, "disabled unlit cell")
    s:Enable()
    Is(Colour(p.cells[15]), T.COLOR_POWER, 1, "head again")
""")

case("slider_head_follows_the_value_and_never_drops_below_one_cell", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p = FS.SliderSkins.Parts(s)
    s:SetValue(100)
    assert(p.lit == 29)
    Is(Colour(p.cells[29]), FS.Theme.COLOR_POWER, 1, "head at the end")
    s:SetValue(0)
    assert(p.lit == 1, "a slider at its minimum still shows one cell")
    Is(Colour(p.cells[1]), FS.Theme.COLOR_POWER, 1, "head at the start")
    Is(Colour(p.cells[2]), FS.Theme.COLOR_CTRL_CELL, 1, "nothing else lit")
    s:SetMinMaxValues(0, 10); s:SetValue(5)
    assert(p.lit == 15)
    s:SetMinMaxValues(5, 5)
    assert(p.lit == 1, "an empty range reads as the start")
""")

case("slider_thumb_is_a_pair_of_lock_on_brackets_around_the_head_cell", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p, T = FS.SliderSkins.Parts(s), FS.Theme
    -- head cell 15: it starts at x0 + 14 * 8 = 113 and is 6 wide, so its centre hx is 116; centre line cy 10
    local hx, cy = 1 + 14 * 8 + 3, 10
    assert(p.hx == hx)
    local b = p.brackets
    Expect(b.leftSpine, p.host, hx - 10, cy - 11, 2, 22, "left spine")
    Expect(b.leftTop, p.host, hx - 10, cy - 11, 5, 2, "left top arm")
    Expect(b.leftBottom, p.host, hx - 10, cy + 9, 5, 2, "left bottom arm")
    Expect(b.rightSpine, p.host, hx + 8, cy - 11, 2, 22, "right spine")
    Expect(b.rightTop, p.host, hx + 5, cy - 11, 5, 2, "right top arm")
    Expect(b.rightBottom, p.host, hx + 5, cy + 9, 5, 2, "right bottom arm")
    for _, name in ipairs({ "leftSpine", "leftTop", "leftBottom", "rightSpine", "rightTop", "rightBottom" }) do
        Is(b[name].color, T.COLOR_POWER, 1, name)
    end
    s:SetValue(100)
    assert(p.hx == 1 + 28 * 8 + 3)
    Expect(b.leftSpine, p.host, p.hx - 10, cy - 11, 2, 22, "left spine after the value moved")
    s:Disable()
    Is(b.leftSpine.color, T.COLOR_CTRL_DISEDGE, 1, "disabled brackets")
    s:Enable()
    s.dragging = true; s:RunScript("OnMouseDown")
    Is(b.rightBottom.color, T.COLOR_HEALTH, 1, "dragged brackets")
""")

case("slider_hover_floats_a_value_tag_and_a_wash_over_the_head_cell", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p, T = FS.SliderSkins.Parts(s), FS.Theme
    assert(not p.tag.frame:IsShown() and not p.wash:IsShown(), "no tag at rest")
    Hover(s)
    assert(p.tag.frame:IsShown() and p.wash:IsShown())
    -- "50" is 2 characters: 2 * 7.2 + 12 = 26.4, rounded up to a multiple of 4 = 28 wide, 18 tall, 34 above the centre line
    local hx, cy = p.hx, p.cy
    Expect(p.tag.frame, p.host, hx - 14, cy - 34, 28, 18, "tag")
    assert(p.tag.label.text == "50", "tag text " .. p.tag.label.text)
    assert(Near(p.tag.label.size * PPU, 11, 0.01), "11 px text")
    Is(p.tag.label.textColor, T.COLOR_POWER, 1, "tag text")
    Is(p.tag.plate.ring.vertex, T.COLOR_POWER, 1, "tag edge")
    Is(Colour(p.tag.plate.fill), T.COLOR_CTRL_INK, 1, "tag face")
    Expect(p.tag.stem, p.host, hx, cy - 16, 1, 4, "tag stem")
    Expect(p.wash, p.host, hx - 14, cy - 12, 28, 24, "wash")
    Is(p.wash.color, T.COLOR_POWER, 0.10, "wash")
    s:SetValue(7)
    assert(p.tag.label.text == "7")
    Expect(p.tag.frame, p.host, p.hx - 10, cy - 34, 20, 18, "a one character tag (7.2 + 12 = 19.2, up to 20)")
""")

case("slider_tag_formats_percent_decimals_and_integers_and_goes_pink_while_dragged", PRELUDE + """
    local pct = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { min = 0, max = 1, value = 0.62, step = 0.01 })
    local dec = SliderBox(P, 20, 60, 232 / PPU, 20 / PPU, { min = 0, max = 2, value = 1.25, step = 0.25 })
    local int = SliderBox(P, 20, 100, 232 / PPU, 20 / PPU, { min = 8, max = 20, value = 12, step = 1 })
    Skin(P)
    local a, b, c = FS.SliderSkins.Parts(pct), FS.SliderSkins.Parts(dec), FS.SliderSkins.Parts(int)
    Hover(pct); Hover(dec); Hover(int)
    assert(a.tag.label.text == "62%", a.tag.label.text)
    assert(b.tag.label.text == "1.25", b.tag.label.text)
    assert(c.tag.label.text == "12", c.tag.label.text)
    int.dragging = true; int:RunScript("OnMouseDown")
    Is(c.tag.label.textColor, FS.Theme.COLOR_HEALTH, 1, "dragged tag text")
    Is(c.tag.plate.ring.vertex, FS.Theme.COLOR_HEALTH, 1, "dragged tag edge")
    Is(c.wash.color, FS.Theme.COLOR_HEALTH, 0.10, "dragged wash")
    -- a drag keeps the tag up when the hand leaves the track
    Unhover(int)
    assert(c.tag.frame:IsShown(), "the tag stays while the thumb is held")
    int.dragging = false; int:RunScript("OnMouseUp")
    assert(not c.tag.frame:IsShown(), "and goes when it is let go")
    -- a disabled slider never shows a tag
    local off = SliderBox(P, 20, 140, 232 / PPU, 20 / PPU, {})
    FS.ControlKit.SkinWidget(off); off:Disable(); Hover(off)
    assert(not FS.SliderSkins.Parts(off).tag.frame:IsShown())
""")

case("slider_chevrons_march_over_the_lit_cells_at_18_percent_white", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p, K = FS.SliderSkins.Parts(s), FS.Layout.Controls
    -- lit 15: the strip covers the 14 cells before the head, 14 * 8 - 2 = 110 px, from the first cell, 8 tall
    Expect(p.chev, p.host, 1, 6, 110, 8, "chevron strip")
    assert(p.chev.path:find("ctl_chevron_h8"), p.chev.path)
    Is(p.chev.vertex, { 1, 1, 1 }, 0.18, "chevron tint")
    Step(0)
    assert(Near(p.chev.coords[1], 0, 0.001) and Near(p.chev.coords[2], 110 / 8, 0.001), "starts at the tile's left")
    Step(0.3)
    assert(Near(p.chev.coords[1], -0.5, 0.02), "half a pitch along after 0.3 s, got " .. p.chev.coords[1])
    assert(Near(p.chev.coords[2] - p.chev.coords[1], 110 / 8, 0.001), "the strip keeps its length")
    assert(p.chev.coords[3] == 0 and p.chev.coords[4] == 1)
    Step(0.3)
    assert(Near(p.chev.coords[1], 0, 0.02) or Near(p.chev.coords[1], -1, 0.02), "a full pitch in 0.6 s")
    -- one lit cell has nothing to march over, a disabled slider does not march
    s:SetValue(0)
    assert(not p.chev:IsShown() and not FS.ControlKit.IsAnimating(p.host, "march"))
    s:SetValue(50); s:Disable()
    assert(not p.chev:IsShown() and not FS.ControlKit.IsAnimating(p.host, "march"))
    s:Enable()
    assert(p.chev:IsShown() and FS.ControlKit.IsAnimating(p.host, "march"))
""")

case("slider_art_is_held_the_labels_restyled_and_nothing_is_written_to_the_widget", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    local m = SliderBox(P, 20, 80, 232 / PPU, 20 / PPU, { value = 50, minimal = true })
    Skin(P)
    NoDegrade()
    local T = FS.Theme
    for _, w in ipairs({ s, m }) do
        assert(w.thumbTex.alpha == 0, "the thumb is held")
        w.thumbTex:SetAlpha(1)
        assert(w.thumbTex.alpha == 0, "the thumb came back")
        assert(next(w.scripts) == nil, "a script was written to a Blizzard slider")
        assert(#w.points == 1 and w.parent == P and w.shown)
    end
    assert(s.NineSlice.alpha == 0, "the NineSlice frame is held")
    s.NineSlice:SetAlpha(1)
    assert(s.NineSlice.alpha == 0, "the NineSlice frame comes back to 0 when Blizzard writes it")
    for _, key in ipairs({ "Left", "Middle", "Right" }) do assert(m[key].alpha == 0, key .. " is held") end
    -- labels: the title is 12 px text colour, Low and High 10 px muted
    assert(s.Text.fontPath == T.FONT_MONO and Near(s.Text.size * PPU, 12, 0.01))
    Is(s.Text.textColor, T.COLOR_CTRL_TEXT, 1, "title")
    assert(Near(s.Low.size * PPU, 10, 0.01) and Near(s.High.size * PPU, 10, 0.01))
    Is(s.Low.textColor, T.COLOR_MUTED, 1, "low label")
    -- the skin never touches the stock size or anchors
    assert(s.w == 232 / PPU and s.h == 20 / PPU and #s.points == 1)
""")

case("slider_detection_is_by_shape_and_a_vertical_slider_or_scroll_bar_is_left_alone", PRELUDE + """
    local ok = SliderBox(P, 20, 20)
    local vertical = SliderBox(P, 20, 60, 17, 100, { orientation = "VERTICAL" })
    local scroll = SliderBox(P, 60, 60, 17, 100)
    scroll.ScrollUpButton = blz("Button", nil, scroll, 16, 16)
    local frame = blz("Frame", nil, P, 144, 17, 20, 200)
    frame.GetValue = function() return 1 end
    assert(Slk().Kind(ok) == "slider")
    assert(Slk().Kind(vertical) == nil and Slk().Kind(scroll) == nil and Slk().Kind(frame) == nil)
    assert(Skin(P) == 1)
    -- no thumb texture, no slider
    local bare = SliderBox(P, 20, 240)
    bare.GetThumbTexture = function() return nil end
    assert(Slk().Kind(bare) == nil)
""")


case("stepper_keys_are_20px_plates_with_a_minus_and_a_plus", PRELUDE + """
    local f = SteppedSlider(P, 20, 20, { value = 5, min = 0, max = 10 })
    assert(Skin(P) == 3, "the slider and its two keys")
    NoDegrade()
    local T = FS.Theme
    local back, fwd = Slk().KeyParts(f.Back), Slk().KeyParts(f.Forward)
    assert(back and back.built and fwd and fwd.built)
    assert(f.Back.w == 11 and f.Back.h == 19 and f.Forward.w == 9 and f.Forward.h == 18, "the stock rects were resized")
    -- the stock 11 x 19 button is 13 x 23 px and the 9 x 18 one 11 x 22: a 20 px key is centred on each, floor((w - 20) / 2)
    Expect(back.plateFrame, f.Back, -4, 1, 20, 20, "back key")
    Expect(fwd.plateFrame, f.Forward, -5, 1, 20, 20, "forward key")
    Expect(back.bar, back.plateFrame, 6, 9, 8, 2, "minus bar")
    Expect(fwd.bar, fwd.plateFrame, 6, 9, 8, 2, "plus bar")
    Expect(fwd.upright, fwd.plateFrame, 9, 6, 2, 8, "plus upright")
    assert(back.upright == nil, "a minus has no upright")
    Is(Colour(back.plate.fill), T.COLOR_CTRL_INK, 1, "idle face")
    Is(back.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    Is(Colour(back.bar), T.COLOR_MUTED, 1, "idle glyph")
    Hover(f.Forward)
    Is(fwd.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    Is(Colour(fwd.bar), T.COLOR_POWER, 1, "hover glyph")
    Is(Colour(fwd.upright), T.COLOR_POWER, 1, "hover upright")
    Unhover(f.Forward)
    Is(fwd.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "edge after the hand leaves")
    f.Back:Disable()
    Is(Colour(back.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled face")
    Is(back.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge")
    Is(Colour(back.bar), T.COLOR_CTRL_DIS, 1, "disabled glyph")
    f.Back:Enable()
    Is(back.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "enabled again")
    assert(f.Back.art.alpha == 0 and f.Forward.art.alpha == 0, "the stock art is held")
    assert(next(f.Back.scripts) == nil and next(f.Forward.scripts) == nil, "a script was written to a stepper button")
    -- the stock buttons sit at fractional pixels (4 and 231 UI units), so each skin is measured from its own stock rect
    WholePixels(f.Back, f.Back, "back key")
    WholePixels(f.Forward, f.Forward, "forward key")
    WholePixels(f.Slider, f.Slider, "stepped slider")
""")

case("a_stepper_slider_keeps_its_cells_8_px_clear_of_the_keys", PRELUDE + """
    local f = SteppedSlider(P, 20, 20, { value = 5, min = 0, max = 10 })
    Skin(P)
    local p = Slk().Parts(f.Slider)
    -- the slider is 212 UI units = 254 px, from 22.8 to 277.2 in the frame; the back key ends at 20.8 and the forward key starts
    -- at 272.2, so the track is inset 6 on the left and 13 on the right: 235 px, 29 cells, 230 wide, 2 in
    assert(p.n == 29 and p.x0 == 8, "cells " .. p.n .. " at " .. p.x0)
    local back, fwd = Slk().KeyParts(f.Back), Slk().KeyParts(f.Forward)
    local _, _, backRight = Px(back.plateFrame, f)
    local fwdLeft = Px(fwd.plateFrame, f)
    local firstLeft = Px(p.cells[1], f)
    local _, _, lastRight = Px(p.cells[29], f)
    assert(firstLeft - backRight >= 8, "gap before the first cell " .. (firstLeft - backRight))
    assert(fwdLeft - lastRight >= 8, "gap after the last cell " .. (fwdLeft - lastRight))
""")

case("stepper_text_is_restyled_the_value_in_cyan", PRELUDE + """
    local f = SteppedSlider(P, 20, 20, {})
    f.TopText = fstring(f, "Scale"); f.MinText = fstring(f, "0", 10); f.MaxText = fstring(f, "100", 10)
    Skin(P)
    local T = FS.Theme
    assert(f.RightText.fontPath == T.FONT_MONO and Near(f.RightText.size * PPU, 12, 0.01))
    Is(f.RightText.textColor, T.COLOR_POWER, 1, "value")
    assert(f.TopText.fontPath == T.FONT_MONO and Near(f.TopText.size * PPU, 12, 0.01))
    Is(f.TopText.textColor, T.COLOR_CTRL_TEXT, 1, "title")
    assert(Near(f.MinText.size * PPU, 10, 0.01) and Near(f.MaxText.size * PPU, 10, 0.01))
    Is(f.MinText.textColor, T.COLOR_MUTED, 1, "min")
""")

case("a_slider_is_skinned_once_and_one_met_in_combat_waits_for_combat_to_end", PRELUDE + """
    local a = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, {})
    assert(Skin(P) == 1)
    local hooks, objs = HookCount(), ObjCount()
    assert(Skin(P) == 0 and HookCount() == hooks and ObjCount() == objs, "a repeat sweep builds nothing")
    local late = SliderBox(P, 20, 80, 232 / PPU, 20 / PPU, {})
    __combat = true
    assert(Skin(P) == 0)
    assert(Slk().Parts(late) == nil, "nothing is skinned in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(Slk().Parts(late) and Slk().Parts(late).built, "skinned after combat")
    NoDegrade()
""")

case("a_change_of_pixel_scale_lays_the_slider_out_again_on_whole_pixels", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p = Slk().Parts(s)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local wpx, hpx = Round(s.w * scale), Round(s.h * scale)
        local n = math.max(2, math.floor((wpx + 2) / 8))
        local x0 = math.floor((wpx - (8 * n - 2)) / 2)
        assert(p.n == n and p.x0 == x0 and p.cy == math.floor(hpx / 2), string.format("scale %s: %d cells at %d, wanted %d at %d", scale, p.n, p.x0, n, x0))
        Expect(p.cells[n], p.host, x0 + (n - 1) * 8, p.cy - 4, 6, 8, "last cell at " .. scale)
        assert(p.cells[n + 1] == nil or not p.cells[n + 1]:IsShown(), "a cell past the track at " .. scale)
        Hover(s)
        WholePixels(s, P, "slider at " .. scale)
        Unhover(s)
    end
""")

case("a_hidden_slider_runs_no_animation_and_a_shown_one_resumes", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    Skin(P)
    local p = Slk().Parts(s)
    Step(0.2)
    local before = p.chev.coords[1]
    P:Hide()
    Step(1.0)
    assert(p.chev.coords[1] == before, "the strip of a hidden slider moved")
    P:Show()
    Step(0.1)
    assert(p.chev.coords[1] ~= before, "it did not resume")
""")

case("a_secret_slider_value_reads_as_the_start_without_an_error", PRELUDE + """
    local s = SliderBox(P, 20, 20, 232 / PPU, 20 / PPU, { value = 50 })
    s.GetValue = function() return { __secret = true } end
    Skin(P)
    NoDegrade()
    local p = Slk().Parts(s)
    assert(p and p.built and p.lit == 1, "an unreadable value reads as the start")
    Hover(s)
    assert(not p.tag.frame:IsShown(), "no number is shown from a secret value")
""")


# -------------------------------------------------------------------------------------------------------------------
# Edit box and search box
# -------------------------------------------------------------------------------------------------------------------

case("field_tokens_are_the_mockups_numbers", PRELUDE + """
    local T, K = FS.Theme, FS.Layout.Controls
    local function hex(c, h)
        local r, g, b = tonumber(h:sub(1, 2), 16) / 255, tonumber(h:sub(3, 4), 16) / 255, tonumber(h:sub(5, 6), 16) / 255
        assert(Near(c[1], r, 0.001) and Near(c[2], g, 0.001) and Near(c[3], b, 0.001), h)
    end
    hex(T.COLOR_CTRL_HAIR, "3a2168"); hex(T.COLOR_CTRL_HINT, "6c6396")
    assert(K.FIELD_CUT == 6 and K.FIELD_CELL == 24 and K.FIELD_RULE_PAD == 5 and K.FIELD_GLYPH == 16 and K.FIELD_GLYPH_X == 4)
    assert(K.FIELD_TEXT_X == 34 and K.FIELD_TEXT == 12 and K.FIELD_RIGHT == 10 and K.FIELD_CLEAR == 28)
    assert(K.FIELD_LED_H == 2 and K.FIELD_LED_UP == 3 and K.FIELD_GLOW == 3 and K.FIELD_GLOW_ALPHA == 0.08)
    assert(K.CARET_W == 7 and K.CARET_H == 14 and K.CARET_BLINK == 1.1)
    assert(K.CHIP_H == 20 and K.CHIP_CUT == 4 and K.CHIP_PAD == 12 and K.CHIP_INSET == 6 and K.CHIP_TEXT == 11)
    assert(K.RADAR_PERIOD == 1.6 and K.RADAR_DOT == 2 and K.RADAR_DOT_X == 3 and K.RADAR_DOT_Y == -5)
""")

case("edit_box_is_a_console_line_ink_face_prompt_cell_and_mono_text", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    assert(Skin(P) == 1)
    NoDegrade()
    local p, T = Fld().Parts(b), FS.Theme
    assert(p and p.built and p.kind == "edit")
    assert(b.w == 156 / PPU and b.h == 28 / PPU, "the stock rect was resized")
    Expect(p.plate.ring, b, 0, 0, 156, 28, "edge")
    Expect(p.plate.fill, b, 0, 0, 156, 28, "face")
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    Expect(p.rule, b, 24, 5, 1, 18, "rule at the prompt cell's edge")
    Is(p.rule.color, T.COLOR_CTRL_HAIR, 1, "rule")
    Expect(p.glyph, b, 4, 6, 16, 16, "prompt")
    assert(p.glyph.path:find("ctl_prompt"), p.glyph.path)
    Is(p.glyph.vertex, T.COLOR_MUTED, 1, "prompt")
    assert(b.fontPath == T.FONT_MONO and Near(b.size * PPU, 12, 0.01), "12 px mono text")
    Is(b.textColor, T.COLOR_CTRL_TEXT, 1, "text")
    assert(Near(b.insets[1] * PPU, 34, 0.01) and Near(b.insets[2] * PPU, 10, 0.01), "text 34 in, 10 short of the right edge")
    assert(not p.glow:IsShown() and not p.led:IsShown() and not p.caret:IsShown(), "no focus, no glow, LED or caret")
    assert(p.over.parent == b, "our layer is a child of the box")
    WholePixels(b, b, "edit box")
""")

case("edit_box_hover_and_focus_go_cyan_focus_adds_glow_led_underline_and_caret", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Fld().Parts(b), FS.Theme
    Hover(b)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    Is(p.glyph.vertex, T.COLOR_MUTED, 1, "the prompt stays muted under the hand")
    assert(not p.glow:IsShown() and not p.led:IsShown())
    Unhover(b)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle again")
    b:SetFocus()
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "focus edge")
    Is(p.glyph.vertex, T.COLOR_POWER, 1, "focus prompt")
    assert(p.glow:IsShown())
    Expect(p.glow, b, -3, -3, 162, 34, "glow")
    Is(p.glow.color, T.COLOR_POWER, 0.08, "glow")
    assert(p.led:IsShown())
    Expect(p.led, b, 1, 25, 154, 2, "LED underline")
    assert(p.caret:IsShown())
    Expect(p.caret, b, 34 + 2, 7, 7, 14, "caret 2 px in from the start of the empty line (the mockup: text x + length * 7.2 + 2)")
    Is(p.caret.color, T.COLOR_POWER, 1, "caret")
    b:ClearFocus()
    assert(not p.glow:IsShown() and not p.led:IsShown() and not p.caret:IsShown())
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "edge after focus")
""")

case("edit_box_led_underline_breathes_and_the_caret_blinks_every_1_1_s", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p = Fld().Parts(b)
    b:SetFocus()
    Step(0)
    assert(p.caret.alpha == 1, "caret on at the start of a blink")
    assert(Near(p.led.color[4], 1, 0.01), "LED underline at full")
    Step(0.8)
    assert(Near(p.led.color[4], 0.3, 0.02), "LED underline at the bottom of its breath, got " .. p.led.color[4])
    assert(p.caret.alpha == 0, "caret off in the second half of the blink")
    Step(0.35)
    assert(p.caret.alpha == 1, "caret on again after 1.1 s")
    b:ClearFocus()
    assert(not FS.ControlKit.IsAnimating(p.over, "led") and not FS.ControlKit.IsAnimating(p.over, "blink"), "nothing runs unfocused")
""")

case("edit_box_caret_follows_the_cursor_dims_mid_text_and_hides_when_the_text_scrolls", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p = Fld().Parts(b)
    b:SetFocus()
    b:SetText("stu")
    -- 3 glyphs of 12 px at 0.5615 an em = 20.2 px, rounded to 20, after the 34 px inset
    Expect(p.caret, b, 34 + 20 + 2, 7, 7, 14, "caret 2 px clear of the last glyph, as the mockup draws it")
    Step(0)
    assert(p.caret.alpha == 1, "solid at the end of the text")
    b.cursor = 1
    b:RunScript("OnCursorChanged", 0, 0, 1, 14)
    Expect(p.caret, b, 34 + 7, 7, 7, 14, "caret after the first glyph")
    Step(0)
    assert(Near(p.caret.alpha, 0.45, 0.001), "dimmed over a glyph so the text stays readable, got " .. p.caret.alpha)
    b:SetText("a very long line that is wider than the box so it scrolls")
    assert(not p.caret:IsShown(), "no caret drawn where the text scrolls under the engine's own")
""")

case("edit_box_caret_follows_a_cursor_move_the_client_never_announced", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p = Fld().Parts(b)
    b:SetFocus()
    b:SetText("stu")
    Expect(p.caret, b, 34 + 20 + 2, 7, 7, 14, "caret at the end of the text")
    b.cursor = 1 -- a click inside the text, with no OnCursorChanged
    Step(0.05)
    Expect(p.caret, b, 34 + 7, 7, 7, 14, "the blink found the cursor after the first glyph")
""")

case("edit_box_caret_reads_the_text_when_the_display_text_reads_empty", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    b.GetDisplayText = function() return "" end -- what the 16001 client returns
    Skin(P)
    local p = Fld().Parts(b)
    b:SetFocus()
    b:SetText("stu")
    Expect(p.caret, b, 34 + 20 + 2, 7, 7, 14, "caret after the text, not at the start of an empty line")
""")

case("edit_box_disabled_is_the_darkest_ink_and_dims_its_text", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Fld().Parts(b), FS.Theme
    b:Disable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge")
    Is(p.rule.color, T.COLOR_CTRL_DISEDGE, 1, "disabled rule")
    Is(p.glyph.vertex, T.COLOR_CTRL_DIS, 1, "disabled prompt")
    Is(b.textColor, T.COLOR_CTRL_DIS, 1, "disabled text")
    Hover(b)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "a disabled box does not light under the hand")
    b:Enable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "enabled face")
    Is(b.textColor, T.COLOR_CTRL_TEXT, 1, "enabled text")
""")

case("search_box_swaps_the_prompt_for_a_lens_and_a_sweeping_radar_while_focused", PRELUDE + """
    local b = SearchBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    assert(Skin(P) == 1, "the sweep skins the box, which takes its clear key with it")
    NoDegrade()
    local p, T = Fld().Parts(b), FS.Theme
    assert(p.kind == "search")
    Expect(p.glyph, b, 4, 6, 16, 16, "lens")
    assert(p.glyph.path:find("ctl_lens"), p.glyph.path)
    Is(p.glyph.vertex, T.COLOR_MUTED, 1, "lens")
    assert(not p.radar:IsShown() and not p.arm:IsShown() and not p.dot:IsShown())
    b:SetFocus()
    assert(not p.glyph:IsShown() and p.radar:IsShown() and p.arm:IsShown() and p.dot:IsShown(), "the lens becomes the radar")
    Expect(p.radar, b, 4, 6, 16, 16, "radar ring")
    assert(p.radar.path:find("ctl_radar%.tga"), p.radar.path)
    Is(p.radar.vertex, T.COLOR_POWER, 1, "radar")
    Expect(p.arm, b, 4, 6, 16, 16, "sweep arm")
    Expect(p.dot, b, 15, 9, 2, 2, "pink dot at (centre + 3, centre - 5)")
    Is(p.dot.color, T.COLOR_HEALTH, 1, "dot")
    Step(0)
    assert(Near(p.arm.rotation, 0, 0.01))
    Step(0.4)
    assert(Near(p.arm.rotation, -math.pi / 2, 0.02), "a quarter turn clockwise in 0.4 s of a 1.6 s sweep, got " .. p.arm.rotation)
    Step(1.2)
    assert(Near(math.abs(p.arm.rotation), 0, 0.02) or Near(math.abs(p.arm.rotation), 2 * math.pi, 0.02), "a full turn in 1.6 s")
    b:ClearFocus()
    assert(p.glyph:IsShown() and not p.radar:IsShown() and not FS.ControlKit.IsAnimating(p.over, "sweep"))
""")

case("search_box_placeholder_and_clear_key_are_restyled_and_the_stock_art_is_held", PRELUDE + """
    local b = SearchBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    NoDegrade()
    local p, T = Fld().Parts(b), FS.Theme
    local ins = b.Instructions
    assert(ins.fontPath == T.FONT_MONO and Near(ins.size * PPU, 12, 0.01), "12 px placeholder")
    Is(ins.textColor, T.COLOR_CTRL_HINT, 1, "placeholder")
    assert(#ins.points == 2 and Near(ins.points[1].x * PPU, 34, 0.01) and Near(ins.points[2].x * PPU, -28, 0.01),
        "placeholder runs from the text inset to the clear zone")
    assert(Near(b.insets[1] * PPU, 34, 0.01) and Near(b.insets[2] * PPU, 28, 0.01), "text insets 34 and 28")
    assert(b.searchIcon.alpha == 0 and b.clearButton.Icon.alpha == 0, "the stock icon and clear art are held")
    b.clearButton.Icon:SetAlpha(1)
    assert(b.clearButton.Icon.alpha == 0, "Blizzard's hover alpha write is undone")
    for _, key in ipairs({ "Left", "Middle", "Right" }) do assert(b[key].alpha == 0, key .. " held") end
    assert(next(b.scripts) == nil or b.scripts.OnTextChanged, "no script of ours")
    local cross = Fld().CrossParts(b.clearButton)
    assert(cross and cross.glyph.path:find("ctl_cross"))
    -- the stock clear key is 17 units = 20 px: the 16 px cross is centred on it, 2 in
    Expect(cross.glyph, b.clearButton, 2, 2, 16, 16, "cross")
    Is(cross.glyph.vertex, T.COLOR_MUTED, 1, "cross")
    Hover(b.clearButton)
    Is(cross.glyph.vertex, T.COLOR_HEALTH, 1, "cross under the hand")
    Unhover(b.clearButton)
    Is(cross.glyph.vertex, T.COLOR_MUTED, 1, "cross after")
    b:SetText("chain")
    assert(not ins:IsShown(), "the stock handler hides the placeholder over text")
""")

case("search_box_count_chip_shows_only_where_a_count_source_gives_one", PRELUDE + """
    local b = SearchBoxW(P, 20, 20, 200 / PPU, 28 / PPU)
    local plain = SearchBoxW(P, 20, 80, 200 / PPU, 28 / PPU)
    Skin(P)
    local p, T = Fld().Parts(b), FS.Theme
    assert(not p.chip.frame:IsShown(), "no source, no chip")
    b:SetText("chain")
    assert(not p.chip.frame:IsShown(), "a box nobody counts for shows no chip")
    Fld().SetCount(b, 7)
    assert(p.chip.frame:IsShown())
    assert(p.chip.label.text == "7 found")
    -- "7 found" is 7 glyphs: 7 * 7.2 + 12 = 62.4, up to 64 wide; the clear key's 28 zone is shown, so the chip ends 6 before it
    Expect(p.chip.frame, b, 200 - 28 - 64 - 6, 4, 64, 20, "chip")
    Is(p.chip.plate.ring.vertex, T.COLOR_POWER, 1, "chip edge")
    Is(p.chip.label.textColor, T.COLOR_POWER, 1, "chip text")
    assert(Near(p.chip.label.size * PPU, 11, 0.01))
    assert(Near(b.insets[2] * PPU, 200 - (200 - 28 - 64 - 6) + 6, 0.01), "text stops 6 before the chip, got " .. b.insets[2] * PPU)
    b:SetText("")
    assert(not p.chip.frame:IsShown(), "an empty query has no count")
    b:SetText("x")
    assert(p.chip.frame:IsShown())
    Fld().SetCount(b, nil)
    assert(not p.chip.frame:IsShown() and Near(b.insets[2] * PPU, 28, 0.01), "no count, the clear zone alone")
    -- a source the addon knows (the collections journals) is asked on every text change
    Fld().AddCountSource(function(box) if box == plain then return 3 end end)
    plain:SetText("mo")
    assert(Fld().Parts(plain).chip.frame:IsShown() and Fld().Parts(plain).chip.label.text == "3 found")
    b:SetText("other")
    assert(not p.chip.frame:IsShown(), "a source that has no number for a box leaves it without a chip")
    -- the chip never squeezes the text under 40 px: 28 + 64 + 6 + 34 + 6 + 40 = 178 is the narrowest box that has one
    local fit = SearchBoxW(P, 20, 140, 178 / PPU, 28 / PPU)
    local tight = SearchBoxW(P, 20, 200, 177 / PPU, 28 / PPU)
    Skin(P)
    for _, box in ipairs({ fit, tight }) do Fld().SetCount(box, 7); box:SetText("ab") end
    assert(Fld().Parts(fit).chip.frame:IsShown(), "178 px leaves the text 40 px")
    assert(not Fld().Parts(tight).chip.frame:IsShown(), "177 px would leave it 39: no chip")
    assert(Near(tight.insets[2] * PPU, 28, 0.01), "no chip, the clear zone alone")
""")

case("detection_takes_single_line_template_boxes_of_console_size_only", PRELUDE + """
    local ok = EditBoxW(P, 20, 20, 130, 20)
    local search = SearchBoxW(P, 20, 60, 130, 20)
    local multi = EditBoxW(P, 20, 100, 200, 20, { multi = true })
    local spinner = EditBoxW(P, 20, 140, 31, 20)
    local tall = EditBoxW(P, 20, 180, 130, 80)
    local bare = blz("EditBox", nil, P, 130, 20, 200, 20)
    local owned = EditBoxW(P, 200, 60, 130, 20)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do owned[key]:SetAlpha(0) end
    local button = blz("Button", nil, P, 130, 20, 200, 100)
    assert(Fld().Kind(ok) == "edit" and Fld().Kind(search) == "search")
    assert(Fld().Kind(multi) == nil, "a text area is not a console line")
    assert(Fld().Kind(spinner) == nil, "a spinner is too narrow")
    assert(Fld().Kind(tall) == nil, "too tall")
    assert(Fld().Kind(bare) == nil, "no template art and no placeholder: not a box of the template family")
    assert(Fld().Kind(owned) == nil, "a box whose art something else already holds is that skin's")
    assert(Fld().Kind(button) == nil)
    assert(Skin(P) == 2, "the edit box and the search box, skinned " .. Skin(P))
""")

case("a_field_is_skinned_once_and_one_met_in_combat_waits_for_combat_to_end", PRELUDE + """
    local a = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    assert(Skin(P) == 1)
    local hooks, objs = HookCount(), ObjCount()
    assert(Skin(P) == 0 and HookCount() == hooks and ObjCount() == objs, "a repeat sweep builds nothing")
    local late = SearchBoxW(P, 20, 80, 156 / PPU, 28 / PPU)
    __combat = true
    assert(Skin(P) == 0)
    assert(Fld().Parts(late) == nil, "nothing is skinned in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(Fld().Parts(late) and Fld().Parts(late).built, "skinned after combat")
    NoDegrade()
""")

case("a_change_of_pixel_scale_lays_the_field_out_again_on_whole_pixels", PRELUDE + """
    local b = SearchBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p = Fld().Parts(b)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w, h = Round(b.w * scale), Round(b.h * scale)
        Expect(p.plate.ring, b, 0, 0, w, h, "edge at " .. scale)
        Expect(p.rule, b, 24, 5, 1, h - 10, "rule at " .. scale)
        Expect(p.glyph, b, 4, math.floor((h - 16) / 2), 16, 16, "lens at " .. scale)
        Expect(p.led, b, 1, h - 3, w - 2, 2, "LED at " .. scale)
        assert(Near(b.insets[1] * scale, 34, 0.01), "text inset at " .. scale)
        b:SetFocus(); b:SetText("ab")
        local stock = { b.Left, b.Middle, b.Right, b.searchIcon, b.clearButton }
        WholePixels(b, b, "field at " .. scale, stock)
        WholePixels(b.clearButton, b.clearButton, "clear key at " .. scale, { b.clearButton.Icon })
        b:ClearFocus(); b:SetText("")
    end
""")

case("a_hidden_field_runs_no_animation_and_a_shown_one_resumes", PRELUDE + """
    local b = EditBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    Skin(P)
    local p = Fld().Parts(b)
    b:SetFocus()
    Step(0.3)
    local alpha = p.led.color[4]
    P:Hide()
    Step(0.7)
    assert(p.led.color[4] == alpha, "the LED of a hidden field moved")
    P:Show()
    Step(0.1)
    assert(p.led.color[4] ~= alpha, "it did not resume")
""")

case("a_secret_text_reads_as_empty_without_an_error", PRELUDE + """
    local b = SearchBoxW(P, 20, 20, 156 / PPU, 28 / PPU)
    b.GetText = function() return { __secret = true } end
    b.GetDisplayText = b.GetText
    Skin(P)
    b:SetFocus()
    NoDegrade()
    local p = Fld().Parts(b)
    assert(p and p.built, "skinned without an error")
    Fld().SetCount(b, 4)
    assert(not p.chip.frame:IsShown(), "a count needs readable text")
""")

case("text_area_is_a_cut_face_that_reaches_5_past_the_frame_with_mono_text_and_the_stock_border_held", PRELUDE + """
    local a = AreaW(P, 40, 40, 250, 80)
    local before = { a.w, a.h, a.EditBox.w, a.EditBox.h }
    assert(Skin(P) == 1)
    NoDegrade()
    local p, T = Fld().AreaParts(a), FS.Theme
    assert(p and p.built, "skinned")
    assert(a.w == before[1] and a.h == before[2] and a.EditBox.w == before[3] and a.EditBox.h == before[4], "the stock rects were resized")
    -- the stock border overshoots the frame by 5 units: our face covers the same ground, whole pixels
    Expect(p.plate.fill, a, -6, -6, 312, 108, "face")
    Expect(p.plate.ring, a, -6, -6, 312, 108, "edge")
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    for _, key in ipairs({ "TopLeftTex", "TopRightTex", "TopTex", "BottomLeftTex", "BottomRightTex", "BottomTex", "LeftTex", "RightTex", "MiddleTex" }) do
        assert(a[key].alpha == 0, key .. " not held")
        a[key]:SetAlpha(1)
        assert(a[key].alpha == 0, key .. " came back")
    end
    local e = a.EditBox
    assert(e.fontPath == T.FONT_MONO and Near(e.size * PPU, 12, 0.01), "12 px mono text")
    Is(e.textColor, T.COLOR_CTRL_TEXT, 1, "text")
    assert(e.Instructions.fontPath == T.FONT_MONO and Near(e.Instructions.size * PPU, 12, 0.01), "placeholder in the mono")
    Is(e.Instructions.textColor, T.COLOR_CTRL_HINT, 1, "placeholder")
    assert(a.CharCount.fontPath == T.FONT_MONO and Near(a.CharCount.size * PPU, 10, 0.01), "count in the mono at 10")
    Is(a.CharCount.textColor, T.COLOR_MUTED, 1, "count")
    assert(e.highlight and Near(e.highlight[1], T.COLOR_POWER[1], 0.002) and Near(e.highlight[4], 0.35, 0.002), "selection is cyan")
    assert(a.scripts.OnShow == nil and e.scripts.OnTextChanged == nil, "no script was set on a stock widget")
    assert(not p.glow:IsShown(), "no focus, no glow")
""")

case("text_area_hover_and_focus_go_cyan_focus_adds_the_glow_and_disabled_goes_dark", PRELUDE + """
    local a = AreaW(P, 40, 40, 250, 80)
    Skin(P)
    local p, T = Fld().AreaParts(a), FS.Theme
    Hover(a)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge over the frame")
    Unhover(a)
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle again")
    Hover(a.EditBox)
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge over the text")
    Unhover(a.EditBox)
    a.EditBox:SetFocus()
    Is(p.plate.ring.vertex, T.COLOR_POWER, 1, "focus edge")
    assert(p.glow:IsShown())
    Expect(p.glow, a, -9, -9, 318, 114, "glow 3 px outside the face")
    Is(p.glow.color, T.COLOR_POWER, 0.08, "glow")
    a.EditBox:ClearFocus()
    assert(not p.glow:IsShown())
    a.EditBox:Disable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_DISFILL, 1, "disabled face")
    Is(p.plate.ring.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge")
    Is(a.EditBox.textColor, T.COLOR_CTRL_DIS, 1, "disabled text")
    a.EditBox:Enable()
    Is(Colour(p.plate.fill), T.COLOR_CTRL_INK, 1, "enabled again")
""")

case("text_area_detection_is_by_shape_and_a_single_line_box_a_held_one_or_a_bare_scroll_frame_is_left_alone", PRELUDE + """
    local good = AreaW(P, 20, 20, 250, 80)
    local single = AreaW(P, 20, 140, 250, 80)
    single.EditBox.multi = false
    local held = AreaW(P, 20, 260, 250, 80)
    held.TopLeftTex:SetAlpha(0)
    local noArt = AreaW(P, 320, 20, 250, 80)
    noArt.MiddleTex = nil
    local bare = blz("ScrollFrame", nil, P, 250, 80, 320, 140)
    local multi = EditBoxW(P, 320, 260, 250, 80, { multi = true })
    local F = Fld()
    assert(F.IsArea(good))
    assert(not F.IsArea(single) and not F.IsArea(held) and not F.IsArea(noArt) and not F.IsArea(bare))
    assert(F.Kind(good.EditBox) == nil and F.Kind(multi) == nil, "the box inside a text area is not a console line")
    assert(Skin(P) == 1, "only the stock text area")
""")

case("a_text_area_is_skinned_once_waits_for_combat_and_follows_a_change_of_pixel_scale", PRELUDE + """
    local a = AreaW(P, 40, 40, 250, 80)
    assert(Skin(P) == 1)
    local hooks, objs = HookCount(), ObjCount()
    assert(Skin(P) == 0 and HookCount() == hooks and ObjCount() == objs, "a repeat sweep builds nothing")
    local late = AreaW(P, 40, 200, 250, 80)
    __combat = true
    assert(Skin(P) == 0 and Fld().AreaParts(late) == nil, "nothing is skinned in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(Fld().AreaParts(late) and Fld().AreaParts(late).built, "skinned after combat")
    local p = Fld().AreaParts(a)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local pad = Round(5 * scale)
        local w, h = Round(a.w * scale), Round(a.h * scale)
        Expect(p.plate.ring, a, -pad, -pad, w + 2 * pad, h + 2 * pad, "edge at " .. scale)
        a.EditBox:SetFocus()
        local stock = { a.TopLeftTex, a.TopRightTex, a.TopTex, a.BottomLeftTex, a.BottomRightTex, a.BottomTex, a.LeftTex, a.RightTex,
            a.MiddleTex, a.CharCount, a.EditBox }
        WholePixels(a, a, "text area at " .. scale, stock)
        a.EditBox:ClearFocus()
    end
    NoDegrade()
""")

# -------------------------------------------------------------------------------------------------------------------
# Item slot
# -------------------------------------------------------------------------------------------------------------------

SLOT_PRELUDE = PRELUDE + """
    local Kit = FS.ControlKit
    local function Slot(o, size)
        local state, read = SlotState(o)
        local b = ItemSlotW(P, 20, 20, (size or 40) / PPU, (size or 40) / PPU)
        assert(FS.ItemSlotSkins.Decorate(b, read), "the slot was not decorated")
        FlushTimers()
        return b, state, FS.ItemSlotSkins.Parts(b)
    end
"""

case("slot_tokens_are_the_mockups_numbers", PRELUDE + """
    local T, K = FS.Theme, FS.Layout.Controls
    local function hex(c, h)
        local r, g, b = tonumber(h:sub(1, 2), 16) / 255, tonumber(h:sub(3, 4), 16) / 255, tonumber(h:sub(5, 6), 16) / 255
        assert(Near(c[1], r, 0.001) and Near(c[2], g, 0.001) and Near(c[3], b, 0.001), h .. " is not the token " .. c[1] .. " " .. c[2] .. " " .. c[3])
    end
    local q = T.COLOR_QUALITY
    hex(q[0], "9d9d9d"); hex(q[1], "5b2d9e"); hex(q[2], "1eff00"); hex(q[3], "2f8cff"); hex(q[4], "6a1fd1"); hex(q[5], "ff8000")
    assert(q[1] == T.COLOR_BAG_RING and q[4] == T.COLOR_EPIC_RING, "Common and Epic are the bag colours")
    hex(T.COLOR_AMBER, "ffb648")
    assert(K.SLOT_ICON_X == 4 and K.SLOT_ICON_Y == 3 and K.SLOT_ICON_TRIM_W == 8 and K.SLOT_ICON_TRIM_H == 10)
    assert(K.SLOT_LED_W == 24 and K.SLOT_LED_H == 2 and K.SLOT_LED_UP == 5 and K.SLOT_EDGE_FROM == 2)
    assert(K.SLOT_GLINT == true and K.SLOT_GLINT_MIN == 4 and Near(K.SLOT_GLINT_ALPHA, 0.35) and K.SLOT_GLINT_PERIOD == 3.4)
    assert(Near(K.SLOT_GLINT_SWEEP, 0.6) and K.SLOT_GLINT_FROM == -44 and K.SLOT_GLINT_TO == 64)
    assert(K.SLOT_WASH_PAD == 4 and Near(K.SLOT_WASH_ALPHA, 0.10) and K.SLOT_RETICLE_PAD == 4 and K.SLOT_RETICLE_LEN == 6)
    assert(K.SLOT_RETICLE_PERIOD == 1.2 and Near(K.SLOT_RETICLE_GROW, 0.1))
    assert(Near(K.SLOT_COOLDOWN_ALPHA, 0.78) and K.SLOT_COOLDOWN_FRONT == 2 and Near(K.SLOT_LOCK_ALPHA, 0.55))
    assert(Near(K.SLOT_HAZARD_ALPHA, 0.4) and K.SLOT_LOCK == 16)
""")

case("slot_led_is_24_by_2_five_up_in_the_quality_colour_and_only_on_a_filled_slot", SLOT_PRELUDE + """
    local T, IS = FS.Theme, FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 3 })
    NoDegrade()
    assert(p and p.built)
    Expect(p.led, b, 8, 35, 24, 2, "led")
    for q = 0, 5 do
        state.quality = q; IS.Refresh(b)
        Is(Colour(p.led), T.COLOR_QUALITY[q], 1, "LED of quality " .. q)
    end
    state.quality = 7; IS.Refresh(b)
    Is(Colour(p.led), T.COLOR_QUALITY[5], 1, "above Legendary reads as Legendary")
    state.quality = nil; IS.Refresh(b)
    Is(Colour(p.led), T.COLOR_QUALITY[1], 1, "an unknown quality is Common")
    state.quality = { __secret = true }; IS.Refresh(b)
    Is(Colour(p.led), T.COLOR_QUALITY[1], 1, "a secret quality is never compared and reads as Common")
    state.quality, state.locked = 4, true; IS.Refresh(b)
    Is(Colour(p.led), T.COLOR_CTRL_DISEDGE, 1, "a locked slot's LED is the dim edge")
    state.locked, state.empty = false, true; IS.Refresh(b)
    assert(not p.led:IsShown(), "an empty slot has no LED")
    NoDegrade()
""")

case("slot_edge_is_2_px_from_uncommon_up_in_the_quality_colour", SLOT_PRELUDE + """
    local T, IS = FS.Theme, FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 3 })
    Expect(p.edge, b, 0, 0, 40, 40, "outer edge")
    Expect(p.edge2, b, 1, 1, 38, 38, "inner edge")
    assert(p.edge.slice == 6, "the outer ring is the slot's chamfer 6")
    for q = 2, 5 do
        state.quality = q; IS.Refresh(b)
        assert(p.edge:IsShown() and p.edge2:IsShown(), "a 2 px edge at quality " .. q)
        Is(Colour(p.edge), T.COLOR_QUALITY[q], 1, "outer edge " .. q)
        Is(Colour(p.edge2), T.COLOR_QUALITY[q], 1, "inner edge " .. q)
    end
    for _, q in ipairs({ 0, 1 }) do
        state.quality = q; IS.Refresh(b)
        assert(not p.edge:IsShown() and not p.edge2:IsShown(), "Poor and Common keep the slot's own dim ring: " .. q)
    end
    state.quality, state.empty = 4, true; IS.Refresh(b)
    assert(not p.edge:IsShown() and not p.edge2:IsShown(), "an empty slot has no quality edge")
""")

case("slot_glint_offset_runs_from_minus_44_to_64_in_the_first_0_6_of_a_3_4_s_loop", SLOT_PRELUDE + """
    local IS = FS.ItemSlotSkins
    assert(Near(IS.GlintOffset(0), -44, 0.001), "starts 44 left of the icon")
    assert(Near(IS.GlintOffset(1.02), 10, 0.001), "half way at half the sweep (ease in out)")
    assert(Near(IS.GlintOffset(2.03), 64, 0.1), "ends 64 right of the icon")
    assert(IS.GlintOffset(2.5) == nil and IS.GlintOffset(3.39) == nil, "rests for the other 40 % of the loop")
    assert(Near(IS.GlintOffset(3.4 + 1.02), 10, 0.001), "and loops")
    assert(IS.GlintOffset(0.5) < IS.GlintOffset(1.02) and IS.GlintOffset(1.02) < IS.GlintOffset(1.5))
""")

case("slot_glint_crosses_the_icon_of_an_epic_and_a_legendary_and_not_a_rare", SLOT_PRELUDE + """
    local K, IS = FS.Layout.Controls, FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 4 })
    NoDegrade()
    assert(IS.GlintEnabled() == true and Kit.IsAnimating(b, "glint"))
    Expect(p.glint, b, 4, 3, 32, 30, "the glint shows through the icon area")
    assert(p.glint.path:find("ctl_glint.tga", 1, true))
    Is(p.glint.vertex, { 1, 1, 1 }, 0.35, "white at 0.35")
    Step(0.05)
    assert(not p.glint:IsShown(), "off to the left at the start of the loop")
    Step(0.99)
    assert(p.glint:IsShown(), "on the icon half way")
    -- the band moves right by shifting the window left: at t = 10 the window starts at -10 / 64 and is 32 / 64 wide, 30 / 64 tall
    local c = p.glint.coords
    assert(Near(c[2] - c[1], 32 / 64, 0.001) and Near(c[4], 30 / 64, 0.001) and Near(c[3], 0, 0.001), "window size")
    assert(c[1] < 0 and c[1] > -0.4, "the window has slid left of the sheet: " .. c[1])
    Step(1.5)
    assert(not p.glint:IsShown(), "resting")
    state.quality = 5; IS.Refresh(b)
    assert(Kit.IsAnimating(b, "glint"), "a legendary glints")
    state.quality = 3; IS.Refresh(b)
    assert(not Kit.IsAnimating(b, "glint") and not p.glint:IsShown(), "a rare does not")
    state.quality, state.empty = 4, true; IS.Refresh(b)
    assert(not Kit.IsAnimating(b, "glint"), "an empty slot does not")
""")

case("slot_glint_has_one_named_switch_that_turns_it_off", SLOT_PRELUDE + """
    local K, IS = FS.Layout.Controls, FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 4 })
    assert(Kit.IsAnimating(b, "glint"))
    IS.SetGlint(false)
    assert(IS.GlintEnabled() == false and not Kit.IsAnimating(b, "glint") and not p.glint:IsShown(), "off at run time")
    IS.SetGlint(true)
    assert(Kit.IsAnimating(b, "glint"), "and back on")
    IS.SetGlint(nil)
    K.SLOT_GLINT = false
    local b2, state2, p2 = Slot({ quality = 5 })
    assert(not Kit.IsAnimating(b2, "glint"), "the Layout constant is the default of the switch")
    NoDegrade()
""")

case("slot_hover_wears_a_wash_a_cyan_2_px_edge_and_breathing_lock_on_brackets", SLOT_PRELUDE + """
    local T, K = FS.Theme, FS.Layout.Controls
    local b, state, p = Slot({ quality = 3 })
    for _, w in pairs(p.wash) do assert(not w:IsShown(), "no wash at rest") end
    assert(not p.reticle.tlH:IsShown() and not Kit.IsAnimating(b, "reticle"))
    Hover(b)
    Is(Colour(p.edge), T.COLOR_POWER, 1, "hover edge")
    Is(Colour(p.edge2), T.COLOR_POWER, 1, "hover inner edge")
    -- a 4 px halo outside the slot at 0.10 cyan (the mockup's wash sits under the slot's face)
    Expect(p.wash.top, b, -4, -4, 48, 4, "wash top"); Expect(p.wash.bottom, b, -4, 40, 48, 4, "wash bottom")
    Expect(p.wash.left, b, -4, 0, 4, 40, "wash left"); Expect(p.wash.right, b, 40, 0, 4, 40, "wash right")
    for _, w in pairs(p.wash) do Is(Colour(w), T.COLOR_POWER, 0.10, "wash colour"); assert(w:IsShown()) end
    -- the brackets at rest: pad 4, arms 6, stroke 2 centred on the path (each corner reaches half a stroke past it)
    Step(1 / 60)
    local r = p.reticle
    Expect(r.tlH, b, -5, -5, 7, 2, "top left across"); Expect(r.tlV, b, -5, -3, 2, 5, "top left down")
    Expect(r.brH, b, 38, 43, 7, 2, "bottom right across"); Expect(r.brV, b, 43, 38, 2, 5, "bottom right up")
    Is(Colour(r.tlH), T.COLOR_POWER, 1, "cyan")
    -- they breathe: at the top of the 1.2 s loop the whole box has grown by 0.1 about its centre (pad 4 + 2.4 -> 6, arms 7)
    Step(0.6 - 1 / 60)
    Expect(r.tlH, b, -7, -7, 8, 2, "top left across, grown")
    Step(0.6)
    Expect(r.tlH, b, -5, -5, 7, 2, "and back")
    Unhover(b)
    for _, w in pairs(p.wash) do assert(not w:IsShown(), "no wash once the hand leaves") end
    assert(not r.tlH:IsShown() and not Kit.IsAnimating(b, "reticle"))
    Is(Colour(p.edge), T.COLOR_QUALITY[3], 1, "the quality edge is back")
    state.empty, state.quality = true, nil; FS.ItemSlotSkins.Refresh(b)
    Hover(b)
    assert(p.edge:IsShown() and p.edge2:IsShown(), "an empty slot takes the hover edge too")
    Is(Colour(p.edge), T.COLOR_POWER, 1, "empty hover edge")
    assert(r.tlH:IsShown())
""")

case("slot_cooldown_drains_an_ink_scrim_down_the_icon_behind_a_2_px_cyan_front", SLOT_PRELUDE + """
    local T = FS.Theme
    local b, state, p = Slot({ quality = 2 })
    assert(p.bar and not p.bar:IsShown(), "no cooldown, no scrim")
    TIME = 100
    b.Cooldown:SetCooldown(100, 10)
    assert(p.bar:IsShown())
    assert(b.Cooldown.swipe == false, "the stock swipe gives way to the drain")
    assert(p.bar.orientation == "VERTICAL" and p.bar.reverse == true, "fills from the top, so the scrim drains upward")
    assert(p.bar.timer and p.bar.timer.dir == Enum.StatusBarTimerDirection.RemainingTime and p.bar.timer.interp == Enum.StatusBarInterpolation.Immediate)
    Expect(p.bar, b, 4, 3, 32, 30, "bar on the icon area")
    local scrim = p.bar:GetStatusBarTexture()
    Is(scrim.vertex, T.COLOR_CTRL_INK, 0.78, "scrim")
    Expect(scrim, b, 4, 3, 32, 30, "the whole icon at the start")
    Step(5)
    Expect(scrim, b, 4, 3, 32, 15, "half drained")
    Expect(p.front, b, 4, 3 + 15 - 2, 32, 2, "the 2 px front rides the scrim's bottom edge")
    Is(Colour(p.front), T.COLOR_POWER, 1, "cyan front")
    Step(4.9)
    Expect(scrim, b, 4, 3, 32, 0.3, "nearly gone", 0)
    Step(0.2)
    assert(not p.bar:IsShown() and b.Cooldown.swipe == true, "done: the scrim is hidden and the stock swipe is back")
    NoDegrade()
""")

case("slot_cooldown_takes_a_duration_object_straight_and_clear_hides_the_scrim", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 2 })
    TIME = 50
    local obj = DurationAt(50, 4)
    b.Cooldown:SetCooldownFromDurationObject(obj)
    assert(p.bar:IsShown() and p.bar.timer.obj == obj, "the engine's own object is handed over untouched")
    b.Cooldown:Clear()
    assert(not p.bar:IsShown() and b.Cooldown.swipe == true)
    b.Cooldown:SetCooldownFromExpirationTime(60, 10)
    assert(p.bar:IsShown() and p.bar.timer.obj.start == 50 and p.bar.timer.obj.duration == 10)
    b.Cooldown:SetCooldown(0, 0)
    assert(not p.bar:IsShown(), "a plain zero cooldown is no cooldown")
    NoDegrade()
""")

case("slot_cooldown_never_reads_a_number_it_cannot_see_and_falls_back_to_the_stock_swipe", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 2 })
    local secret = { __secret = true }
    -- a comparison or arithmetic on a secret throws in the mock, so reaching the bar means none was made
    b.Cooldown:SetCooldown(secret, secret)
    assert(p.bar:IsShown(), "a secret cooldown is passed to the engine as is")
    b.Cooldown:Clear()
    DUR_REJECTS_SECRET = true
    b.Cooldown:SetCooldown(secret, secret)
    assert(not p.bar:IsShown() and b.Cooldown.swipe == true, "the engine refused it: the stock swipe stays and nothing throws")
    DUR_REJECTS_SECRET = false
    TIME = 10
    b.Cooldown:SetCooldown(TIME, 5)
    assert(p.bar:IsShown(), "and the next cooldown works")
    NoDegrade()
""")

case("slot_cooldown_is_left_to_the_stock_swipe_when_the_client_has_no_timer_bars", SLOT_PRELUDE + """
    Enum.StatusBarTimerDirection = nil
    local b, state, p = Slot({ quality = 2 })
    b.Cooldown:SetCooldown(TIME, 5)
    assert(not p.bar:IsShown() and b.Cooldown.swipe == true, "no timer enum, no drain")
    NoDegrade()
""")

case("slot_locked_is_an_ink_scrim_amber_tape_and_a_lock_glyph", SLOT_PRELUDE + """
    local T, IS = FS.Theme, FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 1, locked = true })
    NoDegrade()
    Expect(p.scrim, b, 4, 3, 32, 30, "locked scrim")
    Is(Colour(p.scrim), T.COLOR_CTRL_INK, 0.55, "scrim")
    Expect(p.hazard, b, 4, 3, 32, 30, "tape")
    assert(p.hazard.path:find("ctl_hazard.tga", 1, true))
    Is(p.hazard.vertex, T.COLOR_AMBER, 0.4, "amber tape at 0.4")
    local c = p.hazard.coords
    assert(Near(c[1], 0) and Near(c[2], 32 / 64) and Near(c[3], 0) and Near(c[4], 30 / 64), "the top left 32 x 30 texels of the sheet")
    Expect(p.lock, b, 12, 10, 16, 16, "lock glyph centred on the icon")
    assert(p.lock.path:find("ctl_lock.tga", 1, true))
    Is(p.lock.vertex, T.COLOR_AMBER, 1, "amber lock")
    Is(Colour(p.led), T.COLOR_CTRL_DISEDGE, 1, "dim LED")
    state.locked = false; IS.Refresh(b)
    assert(not p.scrim:IsShown() and not p.hazard:IsShown() and not p.lock:IsShown(), "unlocked")
    Is(Colour(p.led), T.COLOR_QUALITY[1], 1, "the LED is back")
    state.locked, state.empty = true, true; IS.Refresh(b)
    assert(not p.scrim:IsShown() and not p.hazard:IsShown() and not p.lock:IsShown(), "an empty slot is never taped")
""")

case("slot_follows_the_reader_when_the_stock_icon_changes_desaturation", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 3 })
    assert(not p.scrim:IsShown())
    state.locked = true
    b.icon:SetDesaturated(true)
    assert(p.scrim:IsShown() and p.hazard:IsShown(), "the stock lock state is the signal: the tape follows it")
    state.locked = false
    b.icon:SetDesaturated(false)
    assert(not p.scrim:IsShown())
""")

case("slot_on_a_44_px_button_keeps_the_numbers_relative_to_its_rect", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 3, locked = true }, 44)
    NoDegrade()
    -- icon area = the rect less 8 wide and 10 tall at (4, 3); the LED is centred, 5 up from the bottom
    Expect(p.led, b, 10, 39, 24, 2, "led")
    Expect(p.scrim, b, 4, 3, 36, 34, "scrim")
    Expect(p.hazard, b, 4, 3, 36, 34, "tape")
    local c = p.hazard.coords
    assert(Near(c[2], 36 / 64) and Near(c[4], 34 / 64), "the tape's window grows with the icon area")
    Expect(p.lock, b, 14, 12, 16, 16, "lock glyph centred")
    Expect(p.edge, b, 0, 0, 44, 44, "edge")
""")

case("an_item_slot_is_decorated_once_in_combat_waits_and_writes_nothing_to_the_button", SLOT_PRELUDE + """
    local IS = FS.ItemSlotSkins
    local b, state, p = Slot({ quality = 3 })
    local hooks, objs = HookCount(), ObjCount()
    assert(IS.Decorate(b, function() return state end) == true and HookCount() == hooks and ObjCount() == objs, "a repeat builds nothing")
    local late = ItemSlotW(P, 120, 20, 40 / PPU, 40 / PPU)
    __combat = true
    assert(IS.Decorate(late, function() return { quality = 2 } end) == false)
    assert(IS.Parts(late) == nil, "nothing is built in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(IS.Parts(late) and IS.Parts(late).built, "decorated after combat")
    NoDegrade()
""")

case("a_hidden_item_slot_runs_no_animation_and_a_shown_one_resumes", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 4 })
    Hover(b)
    Step(0.3)
    local a = p.reticle.tlH.points[1].x
    P:Hide()
    Step(1.0)
    assert(p.reticle.tlH.points[1].x == a, "the brackets of a hidden slot moved")
    P:Show()
    Step(0.3)
    assert(p.reticle.tlH.points[1].x ~= a, "they did not resume")
""")

case("slot_regions_sit_on_whole_pixels_at_every_scale", SLOT_PRELUDE + """
    local b, state, p = Slot({ quality = 4, locked = true })
    b.Cooldown:SetCooldown(TIME, 10)
    Hover(b)
    Step(0.2)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w = Round(b.w * scale)
        Expect(p.scrim, b, 4, 3, w - 8, w - 10, "scrim at " .. scale)
        Expect(p.led, b, math.floor((w - 24) / 2), w - 5, 24, 2, "led at " .. scale)
        WholePixels(b, b, "slot at " .. scale, { b.icon, b.Count, b.IconBorder, b.Cooldown, p.bar, p.edge, p.edge2 })
    end
""")

case("a_secret_reader_answer_is_treated_as_an_unknown_slot_without_an_error", SLOT_PRELUDE + """
    local IS = FS.ItemSlotSkins
    local b = ItemSlotW(P, 20, 20, 40 / PPU, 40 / PPU)
    assert(IS.Decorate(b, function() return { __secret = true } end))
    FlushTimers()
    local p = IS.Parts(b)
    assert(p and p.built)
    Is(Colour(p.led), FS.Theme.COLOR_QUALITY[1], 1, "an unreadable slot reads as Common")
    local c = ItemSlotW(P, 120, 20, 40 / PPU, 40 / PPU)
    assert(IS.Decorate(c, function() error("the reader threw") end))
    FlushTimers()
    assert(IS.Parts(c) and IS.Parts(c).built, "a reader that throws does not stop the build")
""")

# -------------------------------------------------------------------------------------------------------------------
# Tabs: the slanted strip skinned in place, and the switch
# -------------------------------------------------------------------------------------------------------------------

TAB_PRELUDE = PRELUDE + """
    local T = FS.Theme
    -- a tab 100 px wide in a stock rect 32 units tall, skinned; `o.system` builds the TabSystem button, `o.top` a top tab
    local function Tab(o)
        o = o or {}
        local build = o.system and TabSysBtn or PanelTab
        local b = build(P, o.label or "character", o.x or 20, o.y or 20, (o.w or 100) / PPU, 32, o)
        assert(FS.TabSkins.Skin(b), "the tab was not skinned")
        FlushTimers()
        return b, FS.TabSkins.Parts(b)
    end
    local function CentreOf(o, ref)
        local l, t, r, b = Px(o, ref)
        return (l + r) / 2, (t + b) / 2
    end
    local function Stock(b)
        local list = {}
        for _, key in ipairs({ "Left", "Middle", "Right", "LeftActive", "MiddleActive", "RightActive", "LeftHighlight",
            "MiddleHighlight", "RightHighlight" }) do list[#list + 1] = b[key] end
        return list
    end
"""

case("a_bottom_tab_under_a_window_is_a_folder_tab_in_the_windows_own_fill_and_border", TAB_PRELUDE + """
    local W = blz("Frame", nil, P, 300 / PPU, 100 / PPU, 10, 10)
    local b = PanelTab(W, "Buy", 20 / PPU, 102 / PPU, 100 / PPU, 32)
    assert(FS.TabSkins.Skin(b)); FlushTimers()
    local p = FS.TabSkins.Parts(b)
    NoDegrade()
    assert(p.folder, "a tab 2 px under its window hangs from it")
    local f = p.fold
    -- the plate runs up the 2 px gap to the window's edge and down 24 px from the tab's top, cut 6 at the bottom right
    Expect(f.fill, b, 0, -2, 100, 20, "folder fill")
    Expect(f.left, b, 0, -3, 1, 27, "left edge meets the window border")
    Expect(f.bottom, b, 0, 23, 94, 1, "bottom edge stops at the cut")
    Is(Colour(f.fill), T.COLOR_BG, 0.92, "the window's own fill")
    Is(Colour(f.left), T.COLOR_BORDER, 1, "the window's own border")
    assert(not p.fillM:IsShown() and not p.edgeL:IsShown() and not p.chev:IsShown(), "no slanted plate")
    assert(not f.open:IsShown() and not f.rule:IsShown())
    PanelTemplates_SelectTab(b); FlushTimers()
    Is(Colour(f.left), T.COLOR_HEALTH, 1, "selected edge is pink")
    assert(f.open:IsShown() and f.rule:IsShown(), "the selected tab opens into the window")
    Is(b.Text.textColor, T.COLOR_HEALTH, 1, "selected label")
    -- a tab with no window right above it keeps the slanted strip
    local _, q = Tab()
    assert(not q.folder and q.fillM:IsShown())
""")

case("an_icon_tab_is_a_44_px_cut_key_with_a_36_px_icon_cropped_and_unmasked", TAB_PRELUDE + """
    -- the spellbook's category tabs: a 36 x 35 icon on a 54 x 38 px button, masked to the stock frame
    local b = PanelTab(P, "", 20, 20, 54 / PPU, 38 / PPU)
    b.Icon = tex(b, nil, "ARTWORK")
    b.Icon:SetSize(36, 35); b.Icon:SetPoint("CENTER", b, "CENTER", 0, 0)
    local mask = {}
    b.IconMask = mask
    function b.Icon:RemoveMaskTexture(m) if m == mask then self.unmasked = true end end
    assert(FS.TabSkins.Skin(b)); FlushTimers()
    local p = FS.TabSkins.Parts(b)
    NoDegrade()
    Expect(p.key.fill, b, 5, -3, 44, 44, "the key, centred on the rect")
    Expect(b.Icon, b, 9, 1, 36, 36, "icon 4 in from the key's edge")
    assert(b.Icon.unmasked, "the stock frame mask is taken off")
    local c = b.Icon.coords
    assert(c[1] == 0.08 and c[2] == 0.92 and c[3] == 0.08 and c[4] == 0.92, "cropped past the art's own frame")
    assert(not p.fillM:IsShown() and not p.edgeL:IsShown() and not p.chev:IsShown(), "no slanted strip")
    Is(p.key.ring.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    Hover(b)
    Is(p.key.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    PanelTemplates_SelectTab(b); FlushTimers()
    Is(p.key.ring.vertex, T.COLOR_HEALTH, 1, "selected edge is pink")
    Expect(b.Icon, b, 9, 1, 36, 36, "still seated after a select")
""")

case("tab_tokens_are_the_mockups_numbers", PRELUDE + """
    local K = FS.Layout.Controls
    assert(K.TAB_H == 28 and K.TAB_SLANT == 8 and K.TAB_EXTRA == 1 and K.TAB_CHEV_H == 4 and K.TAB_CHEV_ALPHA == 0.95)
    assert(K.TAB_TEXT == 12 and K.TAB_TEXT_Y == 16 and K.TAB_LED == 4 and K.TAB_LED_X == 14 and K.TAB_LED_Y == 7 and K.TAB_ART == 32)
    assert(K.SWITCH_H == 28 and K.SWITCH_CUT == 6 and K.SWITCH_PAD == 3 and K.SWITCH_ITEM_PAD == 24 and K.SWITCH_STEP == 4)
    assert(K.SWITCH_ITEM_Y == 3 and K.SWITCH_ITEM_H == 22 and K.SWITCH_ITEM_CUT == 4 and K.SWITCH_TEXT_Y == 12)
    assert(K.SWITCH_UNDER_Y == 19 and K.SWITCH_UNDER_H == 3 and K.SWITCH_UNDER_INSET == 4 and K.SWITCH_UNDER_ALPHA == 0.9)
    assert(K.SWITCH_BADGE == 4 and K.SWITCH_BADGE_X == 10 and K.SWITCH_BADGE_Y == 3 and K.SWITCH_SLIDE == 0.2)
""")

case("tab_idle_is_a_28_px_slanted_plate_of_ink_with_a_1_px_dim_edge_and_muted_12_px_text", TAB_PRELUDE + """
    local b, p = Tab()
    NoDegrade()
    assert(p.built and p.kind == "tab")
    -- the stock rect keeps its size; the plate is 28 tall from its top, as wide as the rect (100 px)
    assert(b.w == 100 / PPU and b.h == 32, "the stock rect was resized")
    Expect(p.fillL, b, 0, 0, 8, 28, "left cap fill")
    Expect(p.fillM, b, 8, 0, 84, 28, "middle fill")
    Expect(p.fillR, b, 92, 0, 8, 28, "right cap fill")
    Expect(p.edgeL, b, 0, 0, 8, 28, "left cap edge")
    Expect(p.edgeR, b, 92, 0, 8, 28, "right cap edge")
    Expect(p.edgeTop, b, 8, 0, 84, 1, "top edge")
    Expect(p.edgeBottom, b, 8, 27, 84, 1, "bottom edge")
    assert(p.fillL.path:find("ctl_tab_fill") and p.edgeL.path:find("ctl_tab_edge"), "the baked cap textures")
    -- the trailing cap is the leading one turned half way round
    local l, r = p.fillL.coords, p.fillR.coords
    assert(l[1] == 0 and l[2] == 0.25 and l[3] == 0 and l[4] == 0.875, "the 8 x 28 cap of the 32 canvas")
    assert(r[1] == 0.25 and r[2] == 0 and r[3] == 0.875 and r[4] == 0, "flipped on both axes")
    Is(p.fillL.vertex, T.COLOR_CTRL_INK, 1, "left fill"); Is(Colour(p.fillM), T.COLOR_CTRL_INK, 1, "middle fill")
    Is(p.fillR.vertex, T.COLOR_CTRL_INK, 1, "right fill")
    for _, e in ipairs({ p.edgeL, p.edgeR }) do Is(e.vertex, T.COLOR_CTRL_DIM, 1, "cap edge") end
    for _, e in ipairs({ p.edgeTop, p.edgeBottom }) do Is(Colour(e), T.COLOR_CTRL_DIM, 1, "edge run") end
    assert(not p.diagL:IsShown() and not p.diagR:IsShown() and not p.chev:IsShown() and not p.extra:IsShown() and not p.led:IsShown())
    -- the label: the kit's mono at 12 px, centred 16 below the plate's top, muted
    local label = b.Text
    assert(label.fontPath ~= "stock.ttf" and Near(label.size * PPU, 12, 0.01), "mono 12 px, got " .. tostring(label.fontPath) .. " " .. label.size * PPU)
    Is(label.textColor, T.COLOR_MUTED, 1, "idle label")
    local cx, cy = CentreOf(label, b)
    assert(Near(cx, 50, 0.01) and Near(cy, 16, 0.01), string.format("label centre %.2f %.2f", cx, cy))
    assert(#label.points == 1, "one anchor, the stock re-sets that one")
""")

case("tab_hover_turns_the_edge_cyan_the_fill_cell_and_the_text_light", TAB_PRELUDE + """
    local b, p = Tab()
    Hover(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_CELL, 1, "hover fill"); Is(Colour(p.fillM), T.COLOR_CTRL_CELL, 1, "hover fill")
    Is(p.edgeL.vertex, T.COLOR_POWER, 1, "hover edge"); Is(Colour(p.edgeTop), T.COLOR_POWER, 1, "hover edge run")
    Is(b.Text.textColor, T.COLOR_CTRL_TEXT, 1, "hover label")
    Unhover(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_INK, 1, "idle again"); Is(p.edgeL.vertex, T.COLOR_CTRL_DIM, 1, "idle edge")
    Is(b.Text.textColor, T.COLOR_MUTED, 1, "idle label")
""")

case("tab_disabled_is_the_darkest_ink_with_dim_text_and_does_not_light_under_the_hand", TAB_PRELUDE + """
    local b, p = Tab()
    PanelTemplates_SetDisabledTabState(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_DISFILL, 1, "disabled fill"); Is(Colour(p.fillM), T.COLOR_CTRL_DISFILL, 1, "disabled fill")
    Is(p.edgeL.vertex, T.COLOR_CTRL_DISEDGE, 1, "disabled edge"); Is(Colour(p.edgeBottom), T.COLOR_CTRL_DISEDGE, 1, "disabled run")
    Is(b.Text.textColor, T.COLOR_CTRL_DIS, 1, "disabled label")
    assert(not p.chev:IsShown() and not p.diagL:IsShown(), "disabled is not selected")
    Hover(b)
    Is(p.edgeL.vertex, T.COLOR_CTRL_DISEDGE, 1, "a disabled tab does not light")
    Is(b.Text.textColor, T.COLOR_CTRL_DIS, 1, "its label stays dim")
    PanelTemplates_DeselectTab(b)
    Unhover(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_INK, 1, "enabled again")
""")

case("tab_selected_is_pink_with_a_chevron_strip_two_diagonals_and_one_more_row_of_fill", TAB_PRELUDE + """
    local b, p = Tab()
    PanelTemplates_SelectTab(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_SEL, 1, "selected fill"); Is(Colour(p.fillM), T.COLOR_CTRL_SEL, 1, "selected fill")
    Is(p.fillR.vertex, T.COLOR_CTRL_SEL, 1, "selected fill")
    Expect(p.fillL, b, 0, 0, 8, 28, "cap"); Expect(p.fillM, b, 8, 0, 84, 28, "middle")
    -- the fill reaches one row below the base
    Expect(p.extra, b, 0, 28, 92, 1, "the extra row"); Is(Colour(p.extra), T.COLOR_CTRL_SEL, 1, "extra row")
    -- the 4 tall pink chevron strip from the slant to the right end
    Expect(p.chev, b, 8, 0, 92, 4, "chevron strip")
    assert(p.chev.path:find("ctl_chevron_h4"), p.chev.path)
    Is(p.chev.vertex, T.COLOR_HEALTH, 0.95, "chevron tint")
    -- a 1 px pink diagonal on each side, and no other edge
    Expect(p.diagL, b, 0, 0, 8, 28, "left diagonal"); Expect(p.diagR, b, 92, 0, 8, 28, "right diagonal")
    assert(p.diagL.path:find("ctl_tab_diag") and p.diagR.coords[1] == 0.25 and p.diagR.coords[2] == 0, "the same diagonal, turned")
    Is(p.diagL.vertex, T.COLOR_HEALTH, 1, "diagonal"); Is(p.diagR.vertex, T.COLOR_HEALTH, 1, "diagonal")
    for _, e in ipairs({ p.edgeL, p.edgeR, p.edgeTop, p.edgeBottom }) do assert(not e:IsShown(), "a selected tab has no edge run") end
    Is(b.Text.textColor, T.COLOR_HEALTH, 1, "selected label")
    -- the hand does not change a selected tab
    Hover(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_SEL, 1, "still selected under the hand")
    Is(b.Text.textColor, T.COLOR_HEALTH, 1, "still pink")
    Unhover(b)
    PanelTemplates_DeselectTab(b)
    Is(p.fillL.vertex, T.COLOR_CTRL_INK, 1, "put away")
    assert(not p.chev:IsShown() and not p.extra:IsShown() and not p.diagL:IsShown() and p.edgeTop:IsShown())
""")

case("tab_selected_chevrons_march_one_pitch_every_0_6_s_and_only_while_selected", TAB_PRELUDE + """
    local K = FS.Layout.Controls
    local b, p = Tab()
    assert(not FS.ControlKit.IsAnimating(b, "march"), "an idle tab runs nothing")
    PanelTemplates_SelectTab(b)
    assert(FS.ControlKit.IsAnimating(b, "march"))
    Step(0)
    assert(Near(p.chev.coords[1], 0, 0.001) and Near(p.chev.coords[2], 92 / 8, 0.001), "starts at the tile's left")
    Step(0.3)
    assert(Near(p.chev.coords[1], -0.5, 0.02), "half a pitch along after 0.3 s, got " .. p.chev.coords[1])
    assert(Near(p.chev.coords[2] - p.chev.coords[1], 92 / 8, 0.001), "the strip keeps its length")
    assert(p.chev.coords[3] == 0 and p.chev.coords[4] == 1, "the whole 4 row tile")
    Step(0.3)
    assert(Near(p.chev.coords[1], 0, 0.02) or Near(p.chev.coords[1], -1, 0.02), "a full pitch in 0.6 s")
    PanelTemplates_DeselectTab(b)
    assert(not FS.ControlKit.IsAnimating(b, "march"), "nothing runs once it is put away")
""")

case("tab_news_is_a_4_px_amber_led_that_breathes_and_the_stock_notification_is_left_alone", TAB_PRELUDE + """
    local b, p = Tab({ system = true })
    assert(not p.led:IsShown())
    b:SetTabNotification(true)
    assert(p.led:IsShown(), "news shows the LED")
    Expect(p.led, b, 86, 7, 4, 4, "LED 14 in from the right end, 7 down")
    Is(Colour(p.led), T.COLOR_AMBER, 1, "amber")
    local note = b.notificationFrame
    assert(note and note.alpha == 1 and note.shown, "the pooled notification frame is shared with other windows: untouched")
    Step(0.8)
    assert(Near(p.led.color[4], 0.3, 0.02), "LED at the bottom of its breath, got " .. p.led.color[4])
    b:SetTabNotification(false)
    assert(not p.led:IsShown() and not FS.ControlKit.IsAnimating(b, "led"), "no news, no LED, nothing runs")
    -- a window that keeps its own news says so through SetNews
    local c, q = Tab({ y = 80 })
    FS.TabSkins.SetNews(c, true)
    assert(q.led:IsShown())
    FS.TabSkins.SetNews(c, false)
    assert(not q.led:IsShown())
    -- news rides on a selected tab too
    PanelTemplates_SelectTab(c); FS.TabSkins.SetNews(c, true)
    assert(q.led:IsShown() and q.chev:IsShown())
""")

case("tab_label_is_restyled_and_re_seated_after_every_stock_state_change", TAB_PRELUDE + """
    local function check(b, colour, what)
        local label = b.Text
        assert(label.fontPath ~= "stock.ttf" and Near(label.size * PPU, 12, 0.01), what .. ": the stock font came back")
        Is(label.textColor, colour, 1, what)
        local cx, cy = CentreOf(label, b)
        assert(Near(cx, 50, 0.01) and Near(cy, 16, 0.01), string.format("%s: label centre %.2f %.2f", what, cx, cy))
        assert(#label.points == 1, what .. ": one anchor")
    end
    local b, p = Tab()
    PanelTemplates_SelectTab(b);   check(b, T.COLOR_HEALTH, "select")
    PanelTemplates_DeselectTab(b); check(b, T.COLOR_MUTED, "deselect")
    PanelTemplates_SetDisabledTabState(b); check(b, T.COLOR_CTRL_DIS, "disabled")
    PanelTemplates_DeselectTab(b)
    Hover(b); check(b, T.COLOR_CTRL_TEXT, "hover")
    -- TabSystem tabs go through SetTabSelected and SetTabEnabled
    local s = Tab({ system = true, y = 80 })
    s:SetTabSelected(true);  check(s, T.COLOR_HEALTH, "TabSystem selected")
    s:SetTabSelected(false); check(s, T.COLOR_MUTED, "TabSystem unselected")
    s:SetTabEnabled(false);  check(s, T.COLOR_CTRL_DIS, "TabSystem forced disabled")
    s:SetTabEnabled(true);   check(s, T.COLOR_MUTED, "TabSystem enabled again")
    -- the stock resizes a tab: the plate follows and so does the label
    PanelTemplates_DeselectTab(b)
    b:SetWidth(120 / PPU); b:RunScript("OnSizeChanged")
    Expect(p.fillM, b, 8, 0, 104, 28, "middle fill follows the new width"); Expect(p.fillR, b, 112, 0, 8, 28, "right cap")
    local cx, cy = CentreOf(b.Text, b)
    assert(Near(cx, 60, 0.01) and Near(cy, 16, 0.01), string.format("label centre %.2f %.2f", cx, cy))
""")

case("tab_art_is_held_and_nothing_is_written_to_the_widget", TAB_PRELUDE + """
    local b, p = Tab({ system = true })
    for _, t in ipairs(Stock(b)) do assert(t:GetAlpha() == 0, "stock art is held at alpha 0") end
    -- Blizzard shows and hides it all the time: the state stays readable and the alpha holds
    b:SetTabSelected(true)
    assert(b.LeftActive:IsShown() and not b.Left:IsShown(), "the stock shown state is left as the stock wrote it")
    for _, t in ipairs(Stock(b)) do t:SetAlpha(1); assert(t:GetAlpha() == 0, "a stock write of alpha does not win") end
    assert(b.w == 100 / PPU and b.h == 32, "never resized")
    b:SetTabSelected(false)
    assert(b.Left:IsShown() and not b.LeftActive:IsShown())
    NoDegrade()
""")

case("tab_detection_is_by_shape_never_by_name", TAB_PRELUDE + """
    local TS = FS.TabSkins
    local pt, sys = PanelTab(P, "a", 20, 20, 84 / PPU, 32), TabSysBtn(P, "b", 20, 60, 84 / PPU, 32)
    local named = blz("Button", "MailFrameTab1", P, 84 / PPU, 32, 20, 100)
    -- a UIPanelButton shares Left, Middle and Right but has no Active art; a plain button, a frame and a tab with no label are no tab
    local panelButton = blz("Button", nil, P, 84 / PPU, 32, 20, 140)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do panelButton[key] = tex(panelButton) end
    panelButton.Text = fstring(panelButton, "Okay")
    local plain, frame = blz("Button", nil, P, 84 / PPU, 32, 20, 180), blz("Frame", nil, P, 84 / PPU, 32, 20, 220)
    local unlabelled = PanelTab(P, "c", 20, 260, 84 / PPU, 32); unlabelled.Text = nil
    assert(TS.Kind(pt) == "tab" and TS.Kind(sys) == "tab", "PanelTabButtonTemplate and TabSystemButtonTemplate")
    assert(TS.Kind(named) == nil, "a name is not a shape")
    assert(TS.Kind(panelButton) == nil and TS.Kind(plain) == nil and TS.Kind(frame) == nil and TS.Kind(unlabelled) == nil)
    -- art an earlier skin holds is its own
    local owned = PanelTab(P, "d", 120, 20, 84 / PPU, 32)
    FS.HeldArt.Hold(owned.Left)
    assert(TS.Kind(owned) == nil, "another skin holds this tab's art")
""")

case("a_tab_is_skinned_once_and_one_met_in_combat_waits_for_combat_to_end", TAB_PRELUDE + """
    local a, b = PanelTab(P, "a", 20, 20, 84 / PPU, 32), TabSysBtn(P, "b", 120, 20, 84 / PPU, 32)
    __combat = true
    assert(not FS.TabSkins.Skin(a) and not FS.TabSkins.Skin(b))
    assert(FS.TabSkins.Parts(a) == nil and FS.TabSkins.Parts(b) == nil, "nothing is skinned in combat")
    assert(a.LeftActive:GetAlpha() == 1, "and nothing of the stock art is touched")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    FlushTimers()
    assert(FS.TabSkins.Parts(a) and FS.TabSkins.Parts(a).built and FS.TabSkins.Parts(b) and FS.TabSkins.Parts(b).built)
    local objects, hooks = ObjCount(), HookCount()
    assert(not FS.TabSkins.Skin(a), "a second skin does nothing")
    assert(ObjCount() == objects and HookCount() == hooks, "a repeat builds nothing and hooks nothing")
    -- a state change in combat repaints our own plate
    __combat = true
    PanelTemplates_SelectTab(a)
    assert(FS.TabSkins.Parts(a).chev:IsShown(), "our plate follows the stock in combat")
    NoDegrade()
""")

case("a_protected_tab_keeps_its_label_where_the_stock_put_it_in_combat", TAB_PRELUDE + """
    local b, p = Tab()
    b.protected = true
    __combat = true
    PanelTemplates_SelectTab(b)
    local pt = b.Text.points[1]
    assert(pt.rel == b and pt.relPoint == "CENTER" and pt.y == -3, "the stock's own anchor stands until combat ends")
    assert(p.chev:IsShown(), "our own plate still follows")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    FlushTimers()
    local cx, cy = (function() local l, t, r, bt = Px(b.Text, b); return (l + r) / 2, (t + bt) / 2 end)()
    assert(Near(cx, 50, 0.01) and Near(cy, 16, 0.01), "the label is seated when combat ends")
    NoDegrade()
""")

case("a_tab_on_top_seats_its_plate_at_the_bottom_of_the_stock_rect", TAB_PRELUDE + """
    -- the stock rect is 32 units = 38 px tall: 10 px above a 28 px plate
    for _, o in ipairs({ { top = true }, { system = true, top = true, y = 80 } }) do
        local b, p = Tab(o)
        Expect(p.fillL, b, 0, 10, 8, 28, "plate at the bottom")
        Expect(p.edgeBottom, b, 8, 37, 84, 1, "bottom edge")
        local cx, cy = CentreOf(b.Text, b)
        assert(Near(cx, 50, 0.01) and Near(cy, 26, 0.01), string.format("label centre %.2f %.2f", cx, cy))
        PanelTemplates_SelectTab(b)
        Expect(p.chev, b, 8, 10, 92, 4, "chevron strip rides the plate's top")
    end
""")

case("a_change_of_pixel_scale_lays_the_tab_out_again_on_whole_pixels", TAB_PRELUDE + """
    local b, p = Tab({ system = true })
    b:SetTabSelected(true)
    b:SetTabNotification(true)
    assert(p.chev:IsShown() and p.led:IsShown())
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w = Round(b.w * scale)
        Expect(p.fillM, b, 8, 0, w - 16, 28, "middle at " .. scale)
        Expect(p.fillR, b, w - 8, 0, 8, 28, "right cap at " .. scale)
        Expect(p.chev, b, 8, 0, w - 8, 4, "chevrons at " .. scale)
        Expect(p.led, b, w - 14, 7, 4, 4, "LED at " .. scale)
        local list = Stock(b)
        list[#list + 1] = b.notificationFrame
        WholePixels(b, b, "tab at " .. scale, list)
        local cx, cy = CentreOf(b.Text, b)
        assert(Near(cx, w / 2, 0.01) and Near(cy, 16, 0.01), string.format("label centre %.2f %.2f at %s", cx, cy, scale))
    end
""")

case("a_hidden_tab_runs_no_animation_and_a_shown_one_resumes", TAB_PRELUDE + """
    local b, p = Tab({ system = true })
    b:SetTabSelected(true); b:SetTabNotification(true)
    Step(0.15)
    local led, coord = p.led.color[4], p.chev.coords[1]
    P:Hide()
    Step(1.0)
    assert(p.led.color[4] == led and p.chev.coords[1] == coord, "a hidden tab moved")
    P:Show()
    Step(0.1)
    assert(p.led.color[4] ~= led and p.chev.coords[1] ~= coord, "it did not resume")
""")

case("the_sweep_skins_tabs_with_the_other_controls_and_a_text_button_is_left_alone", TAB_PRELUDE + """
    local page = blz("Frame", nil, P, 380, 280, 10, 10)
    local pt, sys = PanelTab(page, "a", 10, 10, 84 / PPU, 32), TabSysBtn(page, "b", 110, 10, 84 / PPU, 32)
    local check = CheckBox(page, "one", 10, 100)
    local button = blz("Button", nil, page, 84 / PPU, 32, 10, 150)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do button[key] = tex(button) end
    button.Text = fstring(button, "Okay")
    assert(Skin(P) == 3, "two tabs and a check box")
    assert(FS.TabSkins.Parts(pt) and FS.TabSkins.Parts(sys) and FS.TabSkins.Parts(button) == nil)
    assert(Skin(P) == 0, "a second sweep skins nothing new")
    NoDegrade()
""")

case("a_secret_state_reads_as_idle_without_an_error", TAB_PRELUDE + """
    local b, p = Tab({ system = true })
    b.isSelected = { __secret = true }
    b.IsEnabled = function() return { __secret = true } end
    b:SetTabNotification(false)
    Is(p.fillL.vertex, T.COLOR_CTRL_INK, 1, "an unreadable tab reads as idle")
    assert(not p.chev:IsShown())
    NoDegrade()
""")

# --- the switch ---

SWITCH_PRELUDE = PRELUDE + """
    local T = FS.Theme
    local function Switch(items, o)
        o = o or {}
        o.x, o.y = o.x or 20, o.y or 20
        local sw = FS.TabSkins.Switch(P, items, o)
        FlushTimers()
        return sw
    end
    local function CentreOf(o, ref)
        local l, t, r, b = Px(o, ref)
        return (l + r) / 2, (t + b) / 2
    end
"""

case("switch_is_a_28_px_body_with_items_3_in_whose_widths_round_up_to_a_multiple_of_4", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail" })
    NoDegrade()
    -- Inbox: 5 x 7.2 + 24 = 60; Send Mail: 9 x 7.2 + 24 = 88.8 -> 92; the body is the two and 6 more
    Expect(sw.frame, P, 20, 20, 158, 28, "body")
    assert(sw.width == 158 and sw.plate.c == 6, "chamfer 6")
    Is(Colour(sw.plate.fill), T.COLOR_CTRL_INK, 1, "body face"); Is(sw.plate.ring.vertex, T.COLOR_CTRL_DIM, 1, "body edge")
    Expect(sw.items[1].button, sw.frame, 3, 3, 60, 22, "first item")
    Expect(sw.items[2].button, sw.frame, 63, 3, 92, 22, "second item")
    for i, item in ipairs(sw.items) do
        local l = item.label
        assert(Near(l.size * PPU, 12, 0.01), "label is 12 px mono")
        local cx, cy = CentreOf(l, item.button)
        assert(Near(cx, item.width / 2, 0.01) and Near(cy, 12, 0.01), string.format("item %d label centre %.2f %.2f", i, cx, cy))
    end
    assert(sw:GetSelected() == 1)
""")

case("switch_selected_item_is_a_pink_slug_with_a_chevron_underline_and_pink_text", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail" })
    Expect(sw.slug, sw.frame, 3, 3, 60, 22, "slug")
    assert(sw.slugPlate.c == 4)
    Is(Colour(sw.slugPlate.fill), T.COLOR_CTRL_SEL, 1, "slug face"); Is(sw.slugPlate.ring.vertex, T.COLOR_HEALTH, 1, "slug edge")
    Expect(sw.under, sw.slug, 4, 19, 52, 3, "underline")
    assert(sw.under.path:find("ctl_chevron_h3"), sw.under.path)
    Is(sw.under.vertex, T.COLOR_HEALTH, 0.9, "underline tint")
    Step(0)
    local c = sw.under.coords
    assert(Near(c[1], 0, 0.001) and Near(c[2], 52 / 8, 0.001) and c[3] == 0 and Near(c[4], 0.75, 0.001), "3 of the tile's 4 rows")
    Step(0.3)
    assert(Near(sw.under.coords[1], -0.5, 0.02), "the underline marches like the cast bar")
    Is(sw.items[1].label.textColor, T.COLOR_HEALTH, 1, "selected text")
    Is(sw.items[2].label.textColor, T.COLOR_MUTED, 1, "idle text")
    assert(sw.slug.level < sw.items[1].button.level, "the slug is under the labels")
""")

case("switch_hover_boxes_an_idle_item_in_cyan_and_a_disabled_item_stays_dim", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail", "Open" })
    local item = sw.items[2]
    assert(not item.plate.fill:IsShown(), "no box at rest")
    Hover(item.button)
    assert(item.plate.fill:IsShown() and item.plate.ring:IsShown())
    Expect(item.button, sw.frame, 63, 3, 92, 22, "the box is the item's rect")
    assert(item.plate.c == 4)
    Is(Colour(item.plate.fill), T.COLOR_CTRL_CELL, 1, "hover face"); Is(item.plate.ring.vertex, T.COLOR_POWER, 1, "hover edge")
    Is(item.label.textColor, T.COLOR_CTRL_TEXT, 1, "hover text")
    Unhover(item.button)
    assert(not item.plate.fill:IsShown())
    Is(item.label.textColor, T.COLOR_MUTED, 1, "idle text")
    -- the selected item takes no box; a disabled one takes no hover and wears the dim text
    Hover(sw.items[1].button)
    assert(not sw.items[1].plate.fill:IsShown(), "the slug is the selected item's box")
    sw:SetDisabled(3, true)
    Is(sw.items[3].label.textColor, T.COLOR_CTRL_DIS, 1, "disabled text")
    Hover(sw.items[3].button)
    assert(not sw.items[3].plate.fill:IsShown(), "a disabled item does not light")
    Unhover(sw.items[3].button)
    sw:SetDisabled(3, false)
    Is(sw.items[3].label.textColor, T.COLOR_MUTED, 1, "enabled again")
""")

case("switch_click_selects_and_calls_back_and_the_slug_slides_in_0_2_s", SWITCH_PRELUDE + """
    local calls = {}
    local sw = Switch({ "Inbox", "Send Mail", "Open" }, { onSelect = function(i, text) calls[#calls + 1] = i .. ":" .. text end })
    sw.items[2].button:Click()
    assert(#calls == 1 and calls[1] == "2:Send Mail" and sw:GetSelected() == 2)
    Is(sw.items[2].label.textColor, T.COLOR_HEALTH, 1, "the new selection is pink at once")
    Is(sw.items[1].label.textColor, T.COLOR_MUTED, 1, "the old one is not")
    assert(FS.ControlKit.IsAnimating(sw.slug, "slide"))
    Step(0.1)
    local l = Px(sw.slug, sw.frame)
    assert(l > 3 and l < 63, "mid slide, got " .. l)
    assert(Near(l, math.floor(l + 0.5), 0.001), "a whole pixel on the way")
    Step(0.2)
    Expect(sw.slug, sw.frame, 63, 3, 92, 22, "arrived with the item's width")
    Expect(sw.under, sw.slug, 4, 19, 84, 3, "underline follows")
    assert(not FS.ControlKit.IsAnimating(sw.slug, "slide"), "the slide ended")
    -- clicking the selected item or a disabled one changes nothing
    sw.items[2].button:Click()
    sw:SetDisabled(3, true)
    sw.items[3].button:Click()
    assert(#calls == 1 and sw:GetSelected() == 2, "no extra callback")
    -- picking it in code is quiet
    sw:SetSelected(1)
    assert(#calls == 1 and sw:GetSelected() == 1, "SetSelected does not call back")
    sw:SetSelected(3)
    assert(sw:GetSelected() == 1, "a disabled item cannot be picked")
    NoDegrade()
""")

case("switch_that_is_not_on_screen_jumps_the_slug_instead_of_sliding", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail" })
    P:Hide()
    sw:SetSelected(2)
    Expect(sw.slug, sw.frame, 63, 3, 92, 22, "jumped")
    assert(not FS.ControlKit.IsAnimating(sw.slug, "slide"), "nothing to run while hidden")
    Step(1.0)
    P:Show()
    Expect(sw.slug, sw.frame, 63, 3, 92, 22, "still there")
""")

case("switch_badge_is_a_pink_4_px_led_that_breathes", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail" })
    assert(not sw.items[2].badge:IsShown())
    sw:SetBadge(2, true)
    Expect(sw.items[2].badge, sw.items[2].button, 82, 3, 4, 4, "badge 10 from the item's right end, 3 down")
    Is(Colour(sw.items[2].badge), T.COLOR_HEALTH, 1, "pink")
    Step(0.8)
    assert(Near(sw.items[2].badge.color[4], 0.3, 0.02), "bottom of its breath, got " .. sw.items[2].badge.color[4])
    sw:SetBadge(2, false)
    assert(not sw.items[2].badge:IsShown() and not FS.ControlKit.IsAnimating(sw.items[2].button, "badge"))
""")

case("switch_takes_its_options_at_creation_and_is_never_registered_with_the_sweep", SWITCH_PRELUDE + """
    local sw = Switch({ "A", "B", "C" }, { selected = 3, disabled = { [2] = true }, badges = { [1] = true } })
    assert(sw:GetSelected() == 3)
    Is(sw.items[2].label.textColor, T.COLOR_CTRL_DIS, 1, "disabled at creation")
    assert(sw.items[1].badge:IsShown(), "badge at creation")
    -- a one letter label is 7.2 + 24 = 31.2 -> 32 wide
    Expect(sw.slug, sw.frame, 3 + 32 + 32, 3, 32, 22, "slug on the third item at once")
    assert(FS.ControlKit.Classify(sw.frame) == nil, "the sweep does not know it")
    local objects = ObjCount()
    assert(Skin(P) == 0 and ObjCount() == objects, "a sweep builds nothing on it")
""")

case("switch_regions_sit_on_whole_pixels_at_every_scale", SWITCH_PRELUDE + """
    local sw = Switch({ "Inbox", "Send Mail" })
    sw:SetBadge(2, true)
    Hover(sw.items[2].button)
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        Expect(sw.frame, P, 20, 20, 158, 28, "body at " .. scale)
        Expect(sw.slug, sw.frame, 3, 3, 60, 22, "slug at " .. scale)
        WholePixels(sw.frame, P, "switch at " .. scale)
    end
""")

# -------------------------------------------------------------------------------------------------------------------
# Inset (InsetFrameTemplate) and the section header plate
# -------------------------------------------------------------------------------------------------------------------

case("inset_tokens_are_the_mockups_numbers", PRELUDE + """
    local K, T = FS.Layout.Controls, FS.Theme
    assert(K.INSET_CUT == 8 and K.INSET_SCAN_PITCH == 4 and K.INSET_SCAN_ALPHA == 0.05)
    assert(K.INSET_MARK_IN == 4 and K.INSET_MARK_ARM == 4 and K.INSET_MARK_ALPHA == 0.35)
    assert(T.SnapCut(K.INSET_CUT) == 6, "8 snaps to the baked 6")
    assert(K.PLATE_H == 24 and K.PLATE_CUT == 6 and K.PLATE_LED_W == 3 and K.PLATE_LED_H == 12)
    assert(K.PLATE_LED_X == 1 and K.PLATE_LED_Y == 6 and K.PLATE_TEXT_X == 14 and K.PLATE_TEXT == 11)
    assert(K.PLATE_CHIP_Y == 2 and K.PLATE_CHIP_GAP == 4 and K.PLATE_CHIP_RIGHT == 6)
    assert(K.PLATE_GLINT_PERIOD == 3.6 and K.PLATE_GLINT_ALPHA == 0.28 and K.PLATE_GLINT_FROM == -60 and K.PLATE_GLINT_PAST == 40)
    assert(K.AREA_CUT == 6 and K.AREA_PAD == 5)
""")

case("inset_is_an_ink_face_with_a_1_px_edge_a_bottom_right_chamfer_and_the_stock_art_held", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    assert(Skin(P) == 1)
    NoDegrade()
    local p, T = FS.InsetSkins.Parts(i), FS.Theme
    assert(p and p.c == 6, "chamfer 8 asked, the baked 6 drawn")
    assert(i.w == 404 / PPU and i.h == 128 / PPU, "the stock rect was resized")
    -- the face: a run to the cut, a run under it, and the baked corner flipped to the bottom right
    Expect(p.fill.mid, i, 0, 0, 404, 122, "face")
    Expect(p.fill.low, i, 0, 122, 398, 6, "face under the cut")
    Expect(p.fill.br, i, 398, 122, 6, 6, "face corner")
    assert(p.fill.br.path:find("fill_cut_c6", 1, true), p.fill.br.path)
    assert(Near(p.fill.br.coords[1], 6 / 16) and p.fill.br.coords[2] == 0 and Near(p.fill.br.coords[3], 6 / 16) and p.fill.br.coords[4] == 0, "bottom right flip")
    assert(p.fill.top == nil and p.fill.tl == nil and p.edge.tl == nil, "the top left stays square")
    Is(Colour(p.fill.mid), T.COLOR_CTRL_INK, 1, "face")
    Is(Colour(p.fill.low), T.COLOR_CTRL_INK, 1, "face")
    Is(Colour(p.fill.br), T.COLOR_CTRL_INK, 1, "face")
    -- the edge: four runs that never overlap, and the baked diagonal at the cut
    Expect(p.edge.top, i, 0, 0, 403, 1, "top edge")
    Expect(p.edge.right, i, 403, 0, 1, 122, "right edge")
    Expect(p.edge.bottom, i, 0, 127, 398, 1, "bottom edge")
    Expect(p.edge.left, i, 0, 1, 1, 126, "left edge")
    Expect(p.edge.br, i, 398, 122, 6, 6, "diagonal")
    assert(p.edge.br.path:find("border_cut_c6_t1", 1, true), p.edge.br.path)
    assert(Near(p.edge.br.coords[1], 6 / 16) and p.edge.br.coords[2] == 0, "bottom right flip")
    for _, key in ipairs({ "top", "right", "bottom", "left" }) do Is(Colour(p.edge[key]), T.COLOR_CTRL_DISEDGE, 1, key .. " edge") end
    Is(Colour(p.edge.br), T.COLOR_CTRL_DISEDGE, 1, "diagonal")
    -- the stock art is held and stays held
    assert(i.Bg.alpha == 0 and i.NineSlice.alpha == 0, "marble and bevel held")
    i.Bg:SetAlpha(1); i.NineSlice:SetAlpha(1)
    assert(i.Bg.alpha == 0 and i.NineSlice.alpha == 0, "the stock re-asserts it and the hold writes 0 again")
""")

case("inset_scanlines_tile_one_texel_per_pixel_every_4_rows_from_row_3_inside_the_edge", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    Skin(P)
    local p, T = FS.InsetSkins.Parts(i), FS.Theme
    Expect(p.scan.main, i, 1, 1, 402, 121, "scanlines")
    Expect(p.scan.low, i, 1, 122, 397, 5, "scanlines beside the cut")
    for _, key in ipairs({ "main", "low" }) do
        local t = p.scan[key]
        assert(t.path:find("ctl_scanline.tga", 1, true), t.path)
        Is(t.vertex, T.COLOR_BORDER, 0.05, "scanline " .. key)
    end
    local c = p.scan.main.coords
    assert(Near(c[1], 1 / 4) and Near(c[2], 403 / 4) and Near(c[3], 1 / 4) and Near(c[4], 122 / 4), "main tile coordinates, one texel a pixel from the inset's own top left")
    c = p.scan.low.coords
    assert(Near(c[1], 1 / 4) and Near(c[2], 398 / 4) and Near(c[3], 122 / 4) and Near(c[4], 127 / 4), "low tile coordinates run on from the main run")
""")

case("inset_register_marks_are_cyan_l_shapes_4_in_with_4_long_arms_in_three_corners", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    Skin(P)
    local p, T = FS.InsetSkins.Parts(i), FS.Theme
    Expect(p.marks.tl.h, i, 4, 4, 4, 1, "top left across");    Expect(p.marks.tl.v, i, 4, 5, 1, 3, "top left down")
    Expect(p.marks.tr.h, i, 396, 4, 4, 1, "top right across"); Expect(p.marks.tr.v, i, 399, 5, 1, 3, "top right down")
    Expect(p.marks.bl.h, i, 4, 123, 4, 1, "bottom left across"); Expect(p.marks.bl.v, i, 4, 120, 1, 3, "bottom left up")
    assert(p.marks.br == nil, "no mark in the cut corner")
    for _, corner in ipairs({ "tl", "tr", "bl" }) do
        for _, arm in ipairs({ "h", "v" }) do Is(Colour(p.marks[corner][arm]), T.COLOR_POWER, 0.35, corner .. arm) end
    end
""")

case("inset_draws_only_under_its_children_and_writes_nothing_to_the_stock_frame", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    local child = blz("Button", nil, i, 40, 20, 10, 10)
    local fsLabel = fstring(i, "Count", 12)
    local kids, rects = #i.children, {}
    Skin(P)
    assert(#i.children == kids, "no frame was added to the inset")
    local ours = 0
    for _, r in ipairs(i.regions) do
        if r.kind == "Texture" and r ~= i.Bg then
            ours = ours + 1
            assert(r.layer == "BACKGROUND" or r.layer == "BORDER", "a region of ours on " .. r.layer .. ": stock text and icons draw over it")
        end
    end
    assert(ours >= 15, "the face, the edge, the scanlines and the marks: " .. ours)
    assert(fsLabel.text == "Count" and child.alpha == 1, "stock content untouched")
    assert(i.scripts.OnShow == nil and i.scripts.OnSizeChanged == nil, "no script was set on the stock frame")
""")

case("inset_follows_a_resize_and_a_change_of_pixel_scale_on_whole_pixels", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    Skin(P)
    local p = FS.InsetSkins.Parts(i)
    i.w, i.h = 200 / PPU, 80 / PPU
    i:RunScript("OnSizeChanged")
    Expect(p.fill.mid, i, 0, 0, 200, 74, "face after a resize")
    Expect(p.edge.right, i, 199, 0, 1, 74, "right edge after a resize")
    Expect(p.marks.tr.h, i, 192, 4, 4, 1, "top right mark after a resize")
    for _, scale in ipairs({ 1.0, 1.5, 2.0, 1.2 }) do
        PPU = scale
        Fire("UI_SCALE_CHANGED")
        local w, h = Round(i.w * scale), Round(i.h * scale)
        Expect(p.fill.mid, i, 0, 0, w, h - 6, "face at " .. scale)
        Expect(p.edge.bottom, i, 0, h - 1, w - 6, 1, "bottom edge at " .. scale)
        Expect(p.marks.bl.h, i, 4, h - 5, 4, 1, "mark at " .. scale)
        WholePixels(i, i, "inset at " .. scale, { i.Bg, i.NineSlice })
    end
""")

case("inset_detection_is_by_shape_and_a_window_a_held_or_hidden_one_and_a_divider_are_left_alone", PRELUDE + """
    local good = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    local window = InsetW(P, 20, 160, 404 / PPU, 128 / PPU)
    window.layoutType = "PortraitFrameTemplate"
    local plain = blz("Frame", nil, P, 404, 128, 20, 300)
    local held = InsetW(P, 440, 20, 404 / PPU, 128 / PPU)
    held.Bg:SetAlpha(0)
    local hidden = InsetW(P, 440, 160, 404 / PPU, 128 / PPU)
    hidden.NineSlice:Hide()
    local divider = InsetW(P, 440, 300, 404 / PPU, 6 / PPU)
    local bare = InsetW(P, 20, 440, 404 / PPU, 128 / PPU)
    bare.Bg = nil
    local I = FS.InsetSkins
    assert(I.IsInset(good), "the stock inset")
    assert(not I.IsInset(window), "a window frame has a Bg and a NineSlice too")
    assert(not I.IsInset(plain) and not I.IsInset(held) and not I.IsInset(hidden), "plain, held, hidden")
    assert(not I.IsInset(divider), "too short to be an inset")
    assert(not I.IsInset(bare), "no marble to hold")
    assert(Skin(P) == 1, "only the stock inset was skinned")
    assert(I.Parts(window) == nil and I.Parts(held) == nil and I.Parts(hidden) == nil)
""")

case("inset_is_skinned_once_its_controls_are_reached_too_and_one_met_in_combat_waits", PRELUDE + """
    local a = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    local box = EditBoxW(a, 10, 10, 156 / PPU, 28 / PPU)
    assert(Skin(P) == 2, "the inset and the edit box inside it")
    local hooks, objs = HookCount(), ObjCount()
    assert(Skin(P) == 0 and HookCount() == hooks and ObjCount() == objs, "a repeat sweep builds nothing")
    local late = InsetW(P, 20, 200, 404 / PPU, 80 / PPU)
    __combat = true
    assert(Skin(P) == 0)
    assert(FS.InsetSkins.Parts(late) == nil, "nothing is skinned in combat")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED"); FlushTimers()
    assert(FS.InsetSkins.Parts(late), "skinned after combat")
    NoDegrade()
""")

case("inset_art_the_stock_re_shows_is_held_again_on_the_next_show", PRELUDE + """
    local i = InsetW(P, 20, 20, 404 / PPU, 128 / PPU)
    FS.PanelSkins.SweepOnShow(P)
    FlushTimers()
    i.NineSlice:Show(); i.Bg:Show()
    P:Hide(); P:Show()
    assert(i.Bg.alpha == 0 and i.NineSlice.alpha == 0)
    assert(FS.InsetSkins.Parts(i).fill.mid.shown ~= false, "our face is still there")
""")

case("plate_is_a_24_px_band_with_a_top_left_chamfer_a_violet_edge_a_pink_led_and_a_cyan_caption", PRELUDE + """
    local plate = FS.InsetSkins.Plate(P, { text = "INVENTORY", width = 404, x = 20, y = 20 })
    NoDegrade()
    local f, T = plate.frame, FS.Theme
    assert(f.parent == P, "the plate is a frame of its own under the parent")
    Expect(f, P, 20, 20, 404, 24, "plate")
    Expect(plate.fill.top, f, 6, 0, 398, 6, "band top run")
    Expect(plate.fill.mid, f, 0, 6, 404, 18, "band")
    Expect(plate.fill.tl, f, 0, 0, 6, 6, "band corner")
    assert(plate.fill.low == nil and plate.fill.br == nil and plate.edge.br == nil, "the bottom right stays square")
    assert(plate.fill.tl.path:find("fill_cut_c6", 1, true) and plate.fill.tl.coords[1] == 0 and Near(plate.fill.tl.coords[2], 6 / 16), "top left piece, unflipped")
    Is(Colour(plate.fill.mid), T.COLOR_CTRL_BAND, 1, "band")
    Expect(plate.edge.top, f, 6, 0, 397, 1, "top edge")
    Expect(plate.edge.right, f, 403, 0, 1, 24, "right edge")
    Expect(plate.edge.bottom, f, 0, 23, 403, 1, "bottom edge")
    Expect(plate.edge.left, f, 0, 6, 1, 17, "left edge")
    Expect(plate.edge.tl, f, 0, 0, 6, 6, "diagonal")
    for _, key in ipairs({ "top", "right", "bottom", "left", "tl" }) do Is(Colour(plate.edge[key]), T.COLOR_BORDER, 1, key) end
    Expect(plate.led, f, 1, 6, 3, 12, "LED")
    Is(plate.led.color, T.COLOR_HEALTH, 1, "LED")
    local l, t, r, b = Px(plate.label, f)
    assert(Near(l, 14, 0.01) and Near((t + b) / 2, 13, 0.01), string.format("caption at x=%.2f, centre y=%.2f", l, (t + b) / 2))
    assert(plate.label.text == "INVENTORY" and plate.label.fontPath == T.FONT_MONO and Near(plate.label.size * PPU, 11, 0.01))
    Is(plate.label.textColor, T.COLOR_POWER, 1, "caption")
    assert(FS.ControlKit.Classify(f) == nil, "a plate is never swept")
""")

case("plate_chips_sit_right_aligned_6_in_and_4_apart_sized_like_the_value_tag", PRELUDE + """
    local T = FS.Theme
    local one = FS.InsetSkins.Plate(P, { text = "INVENTORY", width = 404, chips = { { "18/44", T.COLOR_POWER } } })
    Expect(one.chips[1].frame, one.frame, 350, 2, 48, 20, "one chip: 5 characters = 36 + 12, already a multiple of 4")
    local two = FS.InsetSkins.Plate(P, { text = "EQUIPMENT", width = 408, chips = { { "ilvl 62", T.COLOR_AMBER }, { "2 empty", T.COLOR_MUTED } } })
    Expect(two.chips[2].frame, two.frame, 338, 2, 64, 20, "the last chip ends 6 from the right (7 characters = 62.4, rounded up to 64)")
    Expect(two.chips[1].frame, two.frame, 270, 2, 64, 20, "the first chip is 4 clear of the second")
    Is(Colour(two.chips[1].plate.ring), T.COLOR_AMBER, 1, "chip edge")
    Is(two.chips[1].label.textColor, T.COLOR_AMBER, 1, "chip text")
    assert(two.chips[1].label.text == "ilvl 62" and Near(two.chips[1].label.size * PPU, 11, 0.01))
    local l, t, r, b = Px(two.chips[1].label, two.chips[1].frame)
    assert(Near((l + r) / 2, 32, 0.6) and Near((t + b) / 2, 11, 0.01), "centred in the chip, 11 down")
    FS.InsetSkins.SetChips(two, { { "3 found", T.COLOR_POWER } })
    assert(not two.chips[2].frame:IsShown(), "a chip no longer asked for is hidden")
    Expect(two.chips[1].frame, two.frame, 338, 2, 64, 20, "the one chip moves to the right end")
    FS.InsetSkins.SetText(two, "FILTER")
    assert(two.label.text == "FILTER")
    NoDegrade()
""")

case("plate_led_breathes_to_03_and_a_hidden_plate_runs_nothing", PRELUDE + """
    local plate = FS.InsetSkins.Plate(P, { text = "INVENTORY", width = 404 })
    Step(0.8)
    assert(Near(plate.led.color[4], 0.3, 0.03), "the LED breathes to 0.3 at the half period: " .. plate.led.color[4])
    Step(0.8)
    assert(plate.led.color[4] > 0.95, "and back")
    plate.frame:Hide()
    local a, g = plate.led.color[4], plate.glintAt
    Step(0.9)
    assert(plate.led.color[4] == a and plate.glintAt == g, "a hidden plate runs nothing")
""")

case("plate_glint_is_a_violet_band_that_crosses_from_60_left_to_40_past_the_right_end_every_3_6_s", PRELUDE + """
    local plate = FS.InsetSkins.Plate(P, { text = "INVENTORY", width = 404 })
    local I = FS.InsetSkins
    assert(I.PlateGlintOffset(0, 404) == -60 and Near(I.PlateGlintOffset(1.8, 404), 192) and Near(I.PlateGlintOffset(3.6, 404), -60),
        "linear from -60 to width + 40, then round again")
    Is(plate.glint.vertex, FS.Theme.COLOR_BORDER, 0.28, "glint")
    assert(plate.glint.path:find("ctl_glint.tga", 1, true))
    Expect(plate.glint, plate.frame, 1, 1, 402, 22, "the glint covers the inside of the band")
    Step(0.05)
    assert(not plate.glint:IsShown(), "it starts off the plate, 60 to the left")
    Step(1.75)
    assert(plate.glint:IsShown() and Near(plate.glintAt, I.PlateGlintOffset(1.8, 404), 12), "over the plate half way: " .. tostring(plate.glintAt))
    assert(Near(plate.glint.coords[1] * 64, -plate.glintAt, 0.5), "its sheet slides left as the band goes right")
    Step(1.6)
    assert(not plate.glint:IsShown(), "and it is past the right end near the end of its run")
""")

SCENES["insets"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 900, 320
    local T = FS.Theme
    local modules = {}
    local function Module(x, y, w, h, text, chips)
        local plate = FS.InsetSkins.Plate(P, { text = text, width = w, x = x, y = y, chips = chips })
        local inset = InsetW(P, x / PPU, (y + 24) / PPU, w / PPU, h / PPU)
        modules[#modules + 1] = inset
        return plate, inset
    end
    Module(16, 16, 404, 128, "INVENTORY", { { "18/44", T.COLOR_POWER } })
    Module(436, 16, 408, 128, "EQUIPMENT", { { "ilvl 62", T.COLOR_AMBER }, { "2 empty", T.COLOR_MUTED } })
    Module(16, 184, 404, 80, "MONEY")
    local _, filter = Module(436, 184, 408, 80, "FILTER", { { "rare+", T.COLOR_POWER } })
    EditBoxW(filter, 24 / PPU, 24 / PPU, 220 / PPU, 28 / PPU)
    Skin(P)
    Step(1.7)
    return DumpOps({ P })
"""

SCENES["areas"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 900, 200
    local areas = {}
    for i = 1, 4 do
        areas[i] = AreaW(P, (24 + (i - 1) * 215) / PPU, 24 / PPU, 190 / PPU, 100 / PPU)
        areas[i].EditBox:SetText(i == 1 and "" or "Steps to reproduce")
    end
    Skin(P)
    areas[1].EditBox.Instructions:SetText("Describe what happened")
    Hover(areas[2])
    areas[3].EditBox:SetFocus()
    areas[4].EditBox:Disable()
    return DumpOps({ P })
"""

SCENES["tabs"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 900, 260
    local names = { "character", "reputation", "skills", "honor", "pet", "talents" }
    local x, tabs = 10, {}
    for i, name in ipairs(names) do
        local w = math.ceil((#name * 7.2 + 32) / 4) * 4
        tabs[i] = (i == 4 and TabSysBtn or PanelTab)(P, name, x / PPU, 20 / PPU, w / PPU, 32)
        x = x + w - 8 + 6
    end
    local plain = {}
    for i = 1, 3 do plain[i] = PanelTab(P, ({ "bags 12", "bank", "keys" })[i], (10 + (i - 1) * 100) / PPU, 80 / PPU, 100 / PPU, 32) end
    Skin(P)
    PanelTemplates_SelectTab(tabs[1])
    Hover(tabs[2])
    tabs[4]:SetTabNotification(true)
    PanelTemplates_SetDisabledTabState(tabs[5])
    PanelTemplates_SelectTab(plain[1])
    local sw = FS.TabSkins.Switch(P, { "Inbox", "Send Mail" }, { x = 10, y = 150 })
    local sw2 = FS.TabSkins.Switch(P, { "Inbox", "Send Mail", "Open" }, { x = 200, y = 150, selected = 2, badges = { [3] = true } })
    local sw3 = FS.TabSkins.Switch(P, { "Inbox", "Send Mail", "Open" }, { x = 450, y = 150, disabled = { [3] = true } })
    FlushTimers()
    Hover(sw2.items[1].button)
    Step(0.4)
    return DumpOps({ P })
"""


SCENES["slots"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 900, 260
    local specs = {
        { {}, "empty" }, { { quality = 1 }, "common" }, { { quality = 2 }, "uncommon" }, { { quality = 3 }, "rare" },
        { { quality = 4 }, "epic" }, { { quality = 5 }, "legendary" }, { { quality = 0 }, "poor" },
        { { quality = 3 }, "hover" }, { { quality = 2 }, "cooldown" }, { { quality = 1, locked = true }, "locked" },
    }
    specs[1][1].empty = true
    local slots = {}
    for i, s in ipairs(specs) do
        local state, read = SlotState(s[1])
        local b = ItemSlotW(P, 12 + (i - 1) * 56, 20, 40 / PPU, 40 / PPU)
        b.Count:SetText(i == 4 and "5" or "")
        FS.ItemSlotSkins.Decorate(b, read)
        slots[i] = b
    end
    FlushTimers()
    Hover(slots[8])
    TIME = 100
    slots[9].Cooldown:SetCooldown(100, 10)
    local lower = {}
    for i = 1, 6 do
        local state, read = SlotState({ quality = i - 1 })
        local b = ItemSlotW(P, 12 + (i - 1) * 56, 120, 40 / PPU, 40 / PPU)
        FS.ItemSlotSkins.Decorate(b, read)
    end
    FlushTimers()
    Step(1.05)
    slots[9].Cooldown:SetCooldown(TIME - 4, 10)
    Step(0.1)
    return DumpOps({ P })
"""

SCENES["dropdowns"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 900, 220
    local dd = {}
    for i = 1, 4 do dd[i] = DropdownW(P, 10 + (i - 1) * 177, 20, 196 / PPU, 28 / PPU, { text = "general" }) end
    Skin(P)
    Dd().SetSwatch(dd[1], FS.Theme.COLOR_POWER)
    Dd().SetSwatch(dd[2], FS.Theme.COLOR_POWER)
    Dd().SetSwatch(dd[3], FS.Theme.COLOR_POWER)
    Hover(dd[2]); OpenList(dd[3]); dd[4]:Disable()
    local menu = MenuW({ { text = "general", selected = true }, { text = "combat log" }, { text = "trade" } }, 100 + 10 + 2 * 177, 145, 196 / PPU)
    OpenMenuFrame(menu)
    Step(0.4)
    Hover(menu.rows[2])
    local later = MenuW({ { text = "general", selected = true }, { text = "combat log" }, { text = "trade" } }, 100 + 10 + 3 * 177, 145, 196 / PPU)
    OpenMenuFrame(later)
    Step(0.07)
    return DumpOps({ P, menu, later })
"""

SCENES["fields"] = """
    local FS = Load()
    local P = Panel()
    P.w, P.h = 1000, 220
    local edit = {}
    for i = 1, 5 do edit[i] = EditBoxW(P, 10 + (i - 1) * 140, 20, 130, 23.33) end
    local search = {}
    for i = 1, 5 do search[i] = SearchBoxW(P, 10 + (i - 1) * 190, 100, 170, 23.33) end
    Skin(P)
    Hover(edit[2])
    edit[3]:SetFocus(); edit[3]:SetText("stu")
    edit[4]:SetText("Stu Moolah")
    edit[5]:Disable()
    Hover(search[2])
    search[3]:SetFocus(); search[3]:SetText("chain"); FS.FieldSkins.SetCount(search[3], 7)
    search[4]:SetText("chain")
    search[5]:Disable()
    Step(0.4)
    return DumpOps({ P })
"""


def main() -> int:
    png = None
    if "--png" in sys.argv:
        png = sys.argv[sys.argv.index("--png") + 1]
    failures = 0
    for name, body in CASES:
        err, _ = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    if png:
        render(png)
    return int(failures > 0)


# ---------------------------------------------------------------------------------------------
# Renderer (PNG for a look; the checks above are the contract)
# ---------------------------------------------------------------------------------------------

def render(prefix: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    for scene, code in SCENES.items():
        rt = LuaRuntime(unpack_returned_tuples=False)
        for key, src in SOURCES.items():
            rt.globals()["SRC_" + key] = src
        names = ", ".join(f"{key} = SRC_{key}" for key in SOURCES)
        rt.execute("SOURCES = { " + names + " }")
        rt.execute(MOCK)
        ops = rt.execute("local function main()\n" + code + "\nend\nreturn main()")
        flat = []
        for i in range(1, len(ops) + 1):
            op = ops[i]
            flat.append({k: (dict((j, v[j]) for j in range(1, len(v) + 1)) if hasattr(v, "__len__") and not isinstance(v, str) else v)
                         for k, v in dict(op.items()).items()})
        if not flat:
            continue
        xs = [o["l"] for o in flat] + [o["r"] for o in flat]
        ys = [o["t"] for o in flat] + [o["b"] for o in flat]
        pad = 24
        ox, oy = min(xs) - pad, min(ys) - pad
        W, H = int(max(xs) - ox + pad), int(max(ys) - oy + pad)
        img = Image.new("RGBA", (W, H), (13, 6, 32, 255))
        fonts: dict[int, ImageFont.FreeTypeFont] = {}
        cache: dict[str, Image.Image] = {}
        for op in flat:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            rgba = op["rgba"]
            col = tuple(int(max(0, min(1, rgba[k])) * 255 + 0.5) for k in (1, 2, 3)) + (int(max(0, min(1, rgba[4])) * 255 + 0.5),)
            l, t, r, b = (round(op["l"] - ox), round(op["t"] - oy), round(op["r"] - ox), round(op["b"] - oy))
            kind = op["kind"]
            if kind == "text":
                size = max(6, round(op["size"]))
                font = fonts.setdefault(size, ImageFont.truetype(str(FONT), size))
                text = op["text"]
                if op.get("clip"):
                    while text and font.getlength(text) > r - l:
                        text = text[:-1]
                total = font.getlength(text)
                x = l if op["justify"] == "LEFT" else (r - total if op["justify"] == "RIGHT" else (l + r) / 2 - total / 2)
                d.text((x, (t + b) / 2), text, font=font, fill=col, anchor="lm")
            elif kind == "tex":
                src = cache.get(op["file"])
                if src is None:
                    src = Image.open(TEXTURES / op["file"]).convert("RGBA")
                    cache[op["file"]] = src
                if r - l > 0 and b - t > 0:
                    c = op.get("coords")
                    if c:
                        # texture coordinates may run past 0..1 (a repeating strip): sample the source with wrap
                        w0, h0 = src.size
                        tile = Image.new("RGBA", (r - l, b - t))
                        sp, tp = src.load(), tile.load()
                        for ty in range(b - t):
                            v = c[3] + (ty + 0.5) / (b - t) * (c[4] - c[3])
                            sy = int(v * h0 // 1) % h0
                            for tx in range(r - l):
                                u = c[1] + (tx + 0.5) / (r - l) * (c[2] - c[1])
                                if op["file"] == "ctl_glint.tga" and not 0 <= u < 1:
                                    continue  # the glint's sheet is clamped, not repeated: outside it is transparent
                                tp[tx, ty] = sp[int(u * w0 // 1) % w0, sy]
                    else:
                        tile = src.resize((r - l, b - t), Image.NEAREST)
                    tint = Image.new("RGBA", tile.size, col[:3] + (255,))
                    px = Image.composite(tint, Image.new("RGBA", tile.size, (0, 0, 0, 0)), tile.getchannel("A"))
                    alpha = tile.getchannel("A").point(lambda v: int(v * col[3] / 255))
                    px.putalpha(alpha)
                    layer.paste(px, (l, t))
            else:
                c = max(0, min(int(op.get("c", 0)), (b - t) // 2))
                pts = [(l + c, t), (r - 1, t), (r - 1, b - 1 - c), (r - 1 - c, b - 1), (l, b - 1), (l, t + c)]
                if kind == "flat":
                    d.rectangle([l, t, r - 1, b - 1], fill=col)
                elif kind == "fill":
                    d.polygon(pts, fill=col)
                elif kind == "ring":
                    d.line(pts + [pts[0]], fill=col, width=1)
            img = Image.alpha_composite(img, layer)
        img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
        out = f"{prefix}-{scene}.png"
        img.convert("RGB").save(out)
        print("wrote", out)


if __name__ == "__main__":
    raise SystemExit(main())
