#!/usr/bin/env python3
"""Runs the real Modules/Skins/Settings.lua and System.lua headless against mock Blizzard windows (tools/charskin_support.py).

Pinned, per window: the Options panel (inner frame art held, wells ringed, tabs, category list rows, the pooled rows of the
settings list with their label pins, hover washes, stepper keys and controls, the keybinding key cells), the addon list rows,
the key bind dialog and the support frame. Nothing is written as a script or attribute on a Blizzard widget, a row the pool
makes later is skinned, and nothing is built in combat. Run `python3 tools/settingsskin-harness.py [--png debug/settings]`.
The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard

-- GameFontNormal and friends: SetFontObject hands the stock font and colour back
local function stockFont(self, gray)
    self.fontPath, self.textColor = "stock.ttf", { 1, 0.82, 0, 1 }
end
local function label(parent, text, size, color)
    local f = fstring(parent, nil, text, size, color)
    f.SetFontObject = stockFont
    return f
end
local function wash(parent)
    local t = tex(parent, nil, "BACKGROUND")
    t.path, t.color, t.shown = nil, { 1, 1, 1, 0.1 }, false
    return t
end
-- UIMenuButtonStretchTemplate: nine pieces, no Left / Middle / Right (the shape KeyBindingFrameBindingButtonTemplate has)
local function menuStretch(b, text)
    for _, n in ipairs({ "TopLeft", "TopRight", "BottomLeft", "BottomRight", "TopMiddle", "MiddleLeft", "MiddleRight",
                         "BottomMiddle", "MiddleMiddle" }) do
        b[n] = tex(b, nil, "BACKGROUND")
    end
    b.fs = fstring(b, nil, text, 12, { 1, 0.82, 0, 1 })
    b.fs.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    return b
end
local function threeSlice(b, text, w)
    b.Left, b.Middle, b.Right = tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND")
    b.fs = fstring(b, nil, text, 12, { 1, 0.82, 0, 1 })
    b.fs.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    return b
end

-- a ScrollBox of recycled rows: ForEachFrame walks the active ones
local function scrollBox(parent, w, h, x, y)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.ScrollTarget = blz("Frame", nil, box, w, 1)
    box.rows, box.y = {}, 0
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function() end
    box.FullUpdate = function() end
    box.SetDataProvider = function() end
    return box
end
local function rowFrame(box, kind, w, h, x)
    local r = blz(kind or "Frame", nil, box.ScrollTarget, w, h, "TOPLEFT", x or 0, -box.y)
    box.y = box.y + h
    box.rows[#box.rows + 1] = r
    return r
end

local function minimalCheck(parent)
    local b = blz("CheckButton", nil, parent, 30, 29, "LEFT", 220, 0)
    b.NormalTexture = tex(b); b.NormalTexture.atlas = "checkbox-minimal"
    b.normalTex = b.NormalTexture
    b.checkedTex = tex(b); b.checkedTex.atlas = "checkmark-minimal"
    b.disabledCheckedTex = tex(b); b.disabledCheckedTex.atlas = "checkmark-minimal-disabled"
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.HoverBackground = wash(b)
    b.scripts.OnClick = function() end
    return b
end
local function slider(parent, w, h, o)
    local s = blz("Slider", nil, parent, w, h, "TOPLEFT", 19, 0)
    s.min, s.max, s.value, s.step = 0, 100, o.value or 50, 1
    s.orientation = "HORIZONTAL"
    s.thumbTex = tex(s, "Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
    s.Left, s.Middle, s.Right = tex(s), tex(s), tex(s)
    function s:GetValue() return self.value end
    function s:SetValue(v) self.value = v; self:RunScript("OnValueChanged", v) end
    function s:GetMinMaxValues() return self.min, self.max end
    function s:SetMinMaxValues(a, b) self.min, self.max = a, b end
    function s:GetValueStep() return self.step end
    function s:SetValueStep(v) self.step = v end
    function s:GetOrientation() return self.orientation end
    function s:GetThumbTexture() return self.thumbTex end
    function s:IsDraggingThumb() return false end
    return s
end
local function steppedSlider(parent, value)
    local f = blz("Frame", nil, parent, 250, 40, "LEFT", 220, 0)
    f.Slider = slider(f, 212, 40, { value = value })
    f.Back = blz("Button", nil, f, 11, 19, "TOPLEFT", 4, -10)
    f.Back.art = tex(f.Back, nil, "BACKGROUND"); f.Back.art.atlas = "Minimal_SliderBar_Button_Left"
    f.Forward = blz("Button", nil, f, 9, 18, "TOPLEFT", 231, -10)
    f.Forward.art = tex(f.Forward, nil, "BACKGROUND"); f.Forward.art.atlas = "Minimal_SliderBar_Button_Right"
    f.RightText = fstring(f, nil, value .. "%", 12, { 1, 1, 1, 1 })
    return f
end
local function dropdown(parent, text)
    local b = blz("Button", nil, parent, 150, 25, "CENTER", 0, 0)
    b.intrinsic = "DropdownButton"
    b.Background = tex(b, nil, "BACKGROUND"); b.Background.atlas = "common-dropdown-textholder"
    b.Arrow = tex(b, nil, "OVERLAY"); b.Arrow.atlas = "common-dropdown-a-button"
    b.Text = fstring(b, nil, text, 12, { 1, 1, 1, 1 })
    b.Text.points = { { point = "TOPRIGHT", rel = b.Arrow, relPoint = "LEFT", x = 0, y = 0 }, { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 8, y = -8 } }
    b.open = false
    function b:IsMenuOpen() return self.open end
    function b:OnMenuOpened() self.open = true end
    function b:OnMenuClosed() self.open = false end
    return b
end
local function iconButton(parent, atlas, point, x)
    local b = blz("Button", nil, parent, 22, 22, point, x, 0)
    b.NormalTexture = atex(b, nil, "ARTWORK", atlas, 22, 22)
    b.GetNormalTexture = function(self) return self.NormalTexture end
    b.scripts.OnClick = function() end
    return b
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Settings") or k:find("^AddonList") or k:find("^QuickKeybind") or k:find("^HelpFrame")
            or k:find("^Help")) then _G[k] = nil end
    end
    -- the Options panel, as Blizzard_SettingsPanel.xml builds it (920 x 724)
    local win = blz("Frame", "SettingsPanel", UIParent, 920, 724)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -60 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 920, 724)
    win.TitleContainer = blz("Frame", nil, win, 800, 20)
    fstring(win, "SettingsPanelTitleText", "Options")
    win.InnerFrameTex = atex(win, nil, "OVERLAY", "Options_InnerFrame", 886, 640)
    win.InnerFrameTex.points[1] = { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 17, y = -64 }
    win.OutputText = label(win, "", 12, { 1, 1, 1, 1 })
    win.OutputText.points[1] = { point = "BOTTOM", rel = win, relPoint = "BOTTOM", x = 0, y = 24 }

    local function tab(key, text, x)
        local t = blz("Button", nil, win, 100, 37, "TOPLEFT", x, -27)
        t.Left, t.Middle, t.Right = atex(t, nil, "BACKGROUND", "Options_Tab_Left", 12, 37), atex(t, nil, "BACKGROUND", "Options_Tab_Middle", 76, 37), atex(t, nil, "BACKGROUND", "Options_Tab_Right", 12, 37)
        t.Text = label(t, text, 11, { 1, 0.82, 0, 1 })
        t.Text.points[1] = { point = "BOTTOM", rel = t, relPoint = "BOTTOM", x = 0, y = 4 }
        t.selected = false
        t.IsSelected = function(self) return self.selected end
        t.OnSelected = function(self, sel) self.selected = sel; self.Text:SetFontObject() end
        t.scripts.OnClick = function() end
        t.scripts.OnEnter = function(self) self.over = true end
        t.scripts.OnLeave = function(self) self.over = nil end
        win[key] = t
        return t
    end
    tab("GameTab", "Game", 32):OnSelected(true)
    tab("AddOnsTab", "AddOns", 137)
    local close = threeSlice(blz("Button", nil, win, 96, 22, "BOTTOMRIGHT", -16, 16), "Close")
    close.points[1].relPoint = "BOTTOMRIGHT"
    win.CloseButton = close
    local apply = threeSlice(blz("Button", nil, win, 96, 22, "BOTTOMRIGHT", -114, 16), "Apply")
    apply.points[1].relPoint = "BOTTOMRIGHT"
    win.ApplyButton = apply

    -- the category list (a ScrollBox of header and button rows)
    local cl = blz("Frame", nil, win, 199, 569, "TOPLEFT", 18, -76)
    win.CategoryList = cl
    cl.ScrollBox = scrollBox(cl, 175, 569, 0, 0)
    local function catHeader(text, idx)
        local r = rowFrame(cl.ScrollBox, "Frame", 175, 30)
        r.Background = atex(r, nil, "ARTWORK", "Options_CategoryHeader_" .. idx, 175, 30)
        r.Label = label(r, text, 14, { 1, 1, 1, 1 })
        r.Label.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 20, y = -1 }
        return r
    end
    local function catButton(text, o)
        o = o or {}
        local r = rowFrame(cl.ScrollBox, "Button", 175, 20, o.indent)
        r.Texture = atex(r, nil, "BACKGROUND", "Options_List_Active", 175, 20)
        r.Texture.shown = false
        r.Label = label(r, text, 12, { 1, 0.82, 0, 1 })
        r.Label.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 36, y = 1 }
        r.Toggle = blz("Button", nil, r, 22, 22, "LEFT", 9, 0)
        r.Toggle.shown = o.parent == true
        r.Toggle.NormalTexture = atex(r.Toggle, nil, "ARTWORK", "common-button-dropdown-open", 22, 22)
        r.Toggle.GetNormalTexture = function(self) return self.NormalTexture end
        r.Toggle.scripts.OnClick = function() end
        r.NewFeature = blz("Frame", nil, r, 1, 1); r.NewFeature.shown = false
        r.cat = { expanded = o.expanded ~= false }
        function r.cat:IsExpanded() return self.expanded end
        function r:GetElementData() return { data = { category = self.cat } } end
        function r:SetExpanded(e) self.cat.expanded = e end
        function r:UpdateStateInternal(sel)
            self.sel = sel
            self.Label:SetFontObject()
            self.Texture:SetShown(sel or self.over == true)
        end
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function(self) self.over = true; self:UpdateStateInternal(self.sel) end
        r.scripts.OnLeave = function(self) self.over = nil; self:UpdateStateInternal(self.sel) end
        r:UpdateStateInternal(o.selected == true)
        return r
    end
    catHeader("Game", 1)
    catButton("Sound", { parent = true })
    catButton("Volume", { indent = 12, selected = true })
    catButton("Controls")
    catButton("Interface")
    catButton("Keybindings")
    catHeader("AddOns", 2)
    SETTINGS_CATEGORY_BUTTON = catButton

    -- the page: a header and a ScrollBox of recycled rows
    local container = blz("Frame", nil, win, 623, 569, "TOPLEFT", 233, -76)
    win.Container = container
    local list = blz("Frame", nil, container, 623, 569, "TOPLEFT", 0, 0)
    container.SettingsList = list
    local head = blz("Frame", nil, list, 623, 50, "TOPLEFT", 0, 0)
    list.Header = head
    head.Title = label(head, "Volume", 20, { 1, 1, 1, 1 })
    head.Title.points[1] = { point = "TOPLEFT", rel = head, relPoint = "TOPLEFT", x = 7, y = -22 }
    head.Divider = atex(head, nil, "ARTWORK", "Options_HorizontalDivider", 623, 8)
    head.Divider.points[1] = { point = "TOP", rel = head, relPoint = "TOP", x = 0, y = -50 }
    head.DefaultsButton = threeSlice(blz("Button", nil, head, 96, 22, "TOPRIGHT", -36, -16), "Defaults")
    head.DefaultsButton.points[1].relPoint = "TOPRIGHT"
    list.ScrollBox = scrollBox(list, 600, 510, 0, -56)

    local box = list.ScrollBox
    local function element(text, h)
        local r = rowFrame(box, "Frame", 600, h or 26)
        r.Text = label(r, text, 12, { 1, 0.82, 0, 1 })
        r.Text.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 37, y = 0 }
        r.Tooltip = blz("Frame", nil, r, 140, h or 26, "TOPLEFT", 0, 0)
        r.Tooltip.HoverBackground = wash(r.Tooltip)
        r.NewFeature = blz("Frame", nil, r, 1, 1); r.NewFeature.shown = false
        return r
    end
    SETTINGS_ELEMENT = element
    local function sectionHeader(text)
        local r = rowFrame(box, "Frame", 600, 45)
        r.Title = label(r, text, 16, { 1, 1, 1, 1 })
        r.Title.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 7, y = -16 }
        r.NewFeature = blz("Frame", nil, r, 1, 1); r.NewFeature.shown = false
        return r
    end
    SETTINGS_HEADER = sectionHeader
    sectionHeader("Output")
    local r = element("Play in background")
    r.Checkbox = minimalCheck(r)
    r = element("Enable reverb")
    r.Checkbox = minimalCheck(r)
    r.Checkbox.checked = true
    r = element("Hardware reverb")
    r.Checkbox = minimalCheck(r)
    r.Text:SetTextColor(0.5, 0.5, 0.5, 1)
    r = element("Music", 40)
    r.SliderWithSteppers = steppedSlider(r, 60)
    r = element("Sound output")
    r.Control = blz("Frame", nil, r, 223, 38, "LEFT", 220, 0)
    r.Control.Dropdown = dropdown(r.Control, "system default")
    r.Control.DecrementButton = iconButton(r.Control, "common-dropdown-icon-back", "LEFT", 0)
    r.Control.IncrementButton = iconButton(r.Control, "common-dropdown-icon-next", "RIGHT", 0)
    r = rowFrame(box, "EventFrame", 600, 25)
    r.Button = blz("Button", nil, r, 580, 30, "TOPLEFT", 0, 0)
    r.Button.Left, r.Button.Right = atex(r.Button, nil, "BACKGROUND", "Options_ListExpand_Left", 20, 30), atex(r.Button, nil, "BACKGROUND", "Options_ListExpand_Right", 20, 30)
    atex(r.Button, nil, "BACKGROUND", "_Options_ListExpand_Middle", 540, 30)
    r.Button.Text = label(r.Button, "Advanced", 12, { 1, 0.82, 0, 1 })
    r.Button.Text.points[1] = { point = "LEFT", rel = r.Button, relPoint = "LEFT", x = 21, y = 2 }
    local sec = r
    sec.data = { expanded = false }
    function sec:GetElementData() return { data = self.data } end
    sec.Button.scripts.OnClick = function() sec.data.expanded = not sec.data.expanded end
    r = element("Reset camera")
    r.Button = threeSlice(blz("Button", nil, r, 140, 26, "LEFT", 220, 0), "Reset")
    r.Button.points[1].relPoint = "LEFT"
    -- a search result row
    local s = rowFrame(box, "Button", 600, 45)
    s.MouseoverOverlay = wash(s)
    s.Title = label(s, "Mouse speed", 14, { 1, 0.82, 0, 1 })
    s.Title.points[1] = { point = "TOPLEFT", rel = s, relPoint = "TOPLEFT", x = 16, y = -16 }
    s.scripts.OnClick = function() end
    s.scripts.OnEnter = function() end
    s.scripts.OnLeave = function() end
    SETTINGS_SEARCH = s

    -- a keybinding row (KeyBindingFrameBindingTemplate)
    local function binding(text, k1, k2)
        local b = rowFrame(box, "Frame", 560, 25)
        b.Label = label(b, text, 12, { 1, 0.82, 0, 1 })
        b.Label.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 37, y = 0 }
        b.Highlight = wash(b)
        b.NewFeature = blz("Frame", nil, b, 1, 1); b.NewFeature.shown = false
        for i, key in ipairs({ "Button1", "Button2" }) do
            local c = menuStretch(blz("Button", nil, b, 160, 22, "LEFT", i == 1 and 200 or 360, 0), (i == 1 and k1) or k2 or NOT_BOUND)
            c.points[1].relPoint = "LEFT"
            c.SelectedHighlight = tex(c, nil, "OVERLAY"); c.SelectedHighlight.shown = false
            c.SetSelected = function(self, sel) self.SelectedHighlight:SetShown(sel) end
            c.scripts.OnEnter = function() end
            c.scripts.OnLeave = function() end
            b[key] = c
        end
        b.Buttons = { b.Button1, b.Button2 }
        return b
    end
    NOT_BOUND = "Not Bound"
    SETTINGS_BINDING = binding
    if BuildExtras then BuildExtras() end
end
"""


SYSTEM = r"""
function BuildExtras()
    local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, BLZ.atex
    Enum = { AddOnEnableState = { None = 0, Some = 1, All = 2 } }
    local function lab(parent, text, size, color)
        local f = fstring(parent, nil, text, size, color)
        f.SetFontObject = function(self) self.fontPath, self.textColor = "stock.ttf", { 1, 0.82, 0, 1 } end
        return f
    end
    local function slices(b, text)
        b.Left, b.Middle, b.Right = tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND"), tex(b, nil, "BACKGROUND")
        b.fs = fstring(b, nil, text, 12, { 1, 0.82, 0, 1 })
        b.fs.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        return b
    end
    local function check(parent, point, x, y)
        local b = blz("CheckButton", nil, parent, 24, 24, point, x, y)
        b.NormalTexture = tex(b); b.NormalTexture.atlas = "checkbox-minimal"
        b.normalTex = b.NormalTexture
        b.checkedTex = tex(b); b.checkedTex.atlas = "checkmark-minimal"
        b.disabledCheckedTex = tex(b); b.disabledCheckedTex.atlas = "checkmark-minimal-disabled"
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        return b
    end
    local function box(parent, name, w, h, x, y)
        local f = blz("Frame", name, parent, w, h, "TOPLEFT", x, y)
        f.NineSlice = blz("Frame", nil, f, w, h)
        f.Bg = tex(f, nil, "BACKGROUND")
        return f
    end

    -- the addon list (AddonList.xml: ButtonFrameTemplate, a Performance strip, a ScrollBox of category and entry rows)
    local win = box(UIParent, "AddonList", 600, 550, 200, -60)
    win.shown = false
    win.TitleContainer = blz("Frame", nil, win, 500, 20)
    local perf = blz("Frame", nil, win, 550, 55, "TOPLEFT", 25, -65)
    win.Performance = perf
    perf.Header = lab(perf, "Add-On CPU Usage", 12)
    perf.Current, perf.Average, perf.Peak = lab(perf, "Now 2.1%", 12, { 1, 1, 1, 1 }), lab(perf, "Avg 1.4%", 12, { 1, 1, 1, 1 }), lab(perf, "Peak 9.3%", 12, { 1, 1, 1, 1 })
    perf.Current.points[1] = { point = "TOPLEFT", rel = perf, relPoint = "TOPLEFT", x = 0, y = -26 }
    perf.Average.points[1] = { point = "TOP", rel = perf, relPoint = "TOP", x = 0, y = -26 }
    perf.Peak.points[1] = { point = "TOPRIGHT", rel = perf, relPoint = "TOPRIGHT", x = 0, y = -26 }
    perf.Divider = atex(perf, nil, "ARTWORK", "Options_HorizontalDivider", 550, 8)
    perf.Divider.points[1] = { point = "BOTTOM", rel = perf, relPoint = "BOTTOM", x = 0, y = 5 }
    win.ForceLoad = check(win, "TOP", -80, -27)
    win.ForceLoad.label = lab(win.ForceLoad, "Load out of date AddOns", 11)
    win.ForceLoad.label.points[1] = { point = "LEFT", rel = win.ForceLoad, relPoint = "LEFT", x = 36, y = 0 }
    win.OkayButton = slices(blz("Button", nil, win, 80, 22, "BOTTOMRIGHT", -88, 4), "Okay")
    win.OkayButton.points[1].relPoint = "BOTTOMRIGHT"
    win.CancelButton = slices(blz("Button", nil, win, 80, 22, "BOTTOMRIGHT", -4, 4), "Cancel")
    win.CancelButton.points[1].relPoint = "BOTTOMRIGHT"
    local list = blz("Frame", nil, win, 466, 386, "TOPLEFT", 7, -120)
    list.ScrollTarget = blz("Frame", nil, list, 466, 1)
    list.rows, list.y = {}, 0
    list.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    list.Update, list.FullUpdate, list.SetDataProvider = function() end, function() end, function() end
    win.ScrollBox = list
    local function row(h)
        local r = blz("Button", nil, list.ScrollTarget, 520, h or 16, "TOPLEFT", 0, -list.y)
        list.y = list.y + (h or 16) + 2
        list.rows[#list.rows + 1] = r
        r.highlightTex = tex(r, nil, "HIGHLIGHT")
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function() end
        r.scripts.OnLeave = function() end
        return r
    end
    ADDON_CATEGORY = function(text, collapsed)
        local r = row()
        r.Title = lab(r, text, 12)
        r.Title.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 31, y = 0 }
        local cx = blz("Button", nil, r, 10, 16, "LEFT", 13, 0)
        cx.Normal = atex(cx, nil, "ARTWORK", "bag-arrow", 10, 16)
        cx.Pushed = atex(cx, nil, "ARTWORK", "bag-arrow", 10, 16)
        cx.Highlight = atex(cx, nil, "HIGHLIGHT", "bag-arrow", 10, 16)
        cx.GetNormalTexture = function(self) return self.Normal end
        cx.treeNode = { collapsed = collapsed == true }
        function cx.treeNode:IsCollapsed() return self.collapsed end
        function cx:UpdateState() end
        cx.scripts.OnClick = function(self) self.treeNode.collapsed = not self.treeNode.collapsed; self:UpdateState() end
        r.CollapseExpand = cx
        return r
    end
    ADDON_ENTRY = function(text, o)
        o = o or {}
        local r = row()
        r.Title = lab(r, text, 12, o.color or { 1, 0.78, 0, 1 })
        r.Title.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 32, y = 0 }
        r.Status = lab(r, o.status or "", 11)
        r.Status.points[1] = { point = "RIGHT", rel = r, relPoint = "RIGHT", x = 0, y = 0 }
        r.Reload = lab(r, "Requires Reload", 12, { 1, 0.1, 0.1, 1 })
        r.Reload.points[1] = { point = "RIGHT", rel = r, relPoint = "RIGHT", x = 0, y = 0 }
        r.Reload.shown = o.reload == true
        r.Enabled = check(r, "LEFT", 5, 0)
        r.Enabled.checked = o.checked ~= false
        r.Enabled.state = o.some and Enum.AddOnEnableState.Some or Enum.AddOnEnableState.All
        r.LoadAddonButton = slices(blz("Button", nil, r, 100, 22, "LEFT", 360, 0), "Load AddOn")
        r.LoadAddonButton.points[1].relPoint = "LEFT"
        r.LoadAddonButton.shown = o.lod == true
        return r
    end
    ADDON_CATEGORY("Interface", false)
    ADDON_ENTRY("Forever STUwave", { checked = true })
    ADDON_ENTRY("Deadly Boss Mods", { some = true })
    ADDON_ENTRY("Old Bags", { color = { 0.5, 0.5, 0.5, 1 }, checked = false, status = "Disabled" })
    ADDON_ENTRY("Broken Thing", { color = { 1, 0.1, 0.1, 1 }, status = "Missing Dependency" })
    ADDON_ENTRY("Reload Me", { reload = true, lod = false })
    ADDON_ENTRY("Lazy Module", { lod = true })

    local dlg = blz("Frame", "AddonDialog", UIParent, 1920, 1080, "CENTER", 0, 0)
    dlg.shown = false
    local bg = blz("Frame", "AddonDialogBackground", dlg, 512, 256, "CENTER", 0, 0)
    bg.NineSlice = blz("Frame", nil, bg, 512, 256)
    bg.Bg = tex(bg, nil, "BACKGROUND")
    bg.text = lab(bg, "This add-on wants to do a thing.", 14, { 1, 0.82, 0, 1 })
    bg.text.points[1] = { point = "TOP", rel = bg, relPoint = "TOP", x = 0, y = -16 }
    bg.text.w, bg.text.h = 440, 40
    _G.AddonDialogText = bg.text
    slices(blz("Button", "AddonDialogButton1", bg, 120, 22, "BOTTOMLEFT", 100, 24), "Yes").points[1].relPoint = "BOTTOMLEFT"
    slices(blz("Button", "AddonDialogButton2", bg, 120, 22, "BOTTOMRIGHT", -100, 24), "No").points[1].relPoint = "BOTTOMRIGHT"

    -- the quick key bind dialog (QuickKeybind.xml)
    local qk = blz("Button", "QuickKeybindFrame", UIParent, 450, 250, "TOPLEFT", 300, -120)
    qk.shown = false
    qk.InstructionText = lab(qk, "Hover over a button to set its key.", 12, { 1, 1, 1, 1 })
    qk.CancelDescriptionText = lab(qk, "Press escape to cancel.", 12, { 1, 1, 1, 1 })
    qk.OutputText = lab(qk, "Pressed W", 12, { 1, 1, 1, 1 })
    for key, y in pairs({ InstructionText = -20, CancelDescriptionText = -70, OutputText = -120 }) do
        qk[key].points[1] = { point = "TOP", rel = qk, relPoint = "TOP", x = 0, y = y }
        qk[key].w, qk[key].h = 400, 50
    end
    qk.BG = blz("Frame", nil, qk, 450, 250, "TOPLEFT", 0, 0)
    tex(qk.BG, nil, "BORDER")
    qk.Header = blz("Frame", nil, qk, 200, 39, "TOP", 0, 11)
    qk.Header.LeftBG, qk.Header.RightBG, qk.Header.CenterBG = tex(qk.Header, nil, "ARTWORK"), tex(qk.Header, nil, "ARTWORK"), tex(qk.Header, nil, "ARTWORK")
    qk.Header.Text = lab(qk.Header, "Quick Keybind Mode", 14, { 1, 0.82, 0, 1 })
    qk.Header.Text.points[1] = { point = "CENTER", rel = qk.Header, relPoint = "CENTER", x = 0, y = 4 }
    qk.UseCharacterBindingsButton = check(qk, "CENTER", -82, -65)
    qk.DefaultsButton = slices(blz("Button", nil, qk, 128, 22, "CENTER", 0, -95), "Defaults")
    qk.CancelButton = slices(blz("Button", nil, qk, 96, 22, "CENTER", 110, -95), "Cancel")
    qk.OkayButton = slices(blz("Button", nil, qk, 96, 22, "CENTER", -110, -95), "Okay")

    -- the support frame (HelpFrame.xml: DefaultPanelTemplate, a Browser in an inset, a spinner)
    local help = box(UIParent, "HelpFrame", 974, 628, 80, -40)
    help.shown = false
    help.TitleContainer = blz("Frame", nil, help, 900, 20)
    help.CloseButton = blz("Button", nil, help, 15, 15, "TOPRIGHT", -6, -4)
    tex(help.CloseButton, nil, "BACKGROUND")
    local br = blz("Frame", "HelpBrowser", help, 964, 602, "TOPLEFT", 7, -22)
    help.Browser = br
    br.BrowserInset = box(br, nil, 970, 606, -3, 3)
    help.SpinnerOverlay = blz("Frame", nil, help, 120, 120, "CENTER", 0, 0)
    help.loading = true
    function help:SetInitialLoading(v) self.loading = v end
    function help:GetInitialLoading() return self.loading end
    function help:ShowUnavailable() end
    function help:OnError() end
end
"""
BLIZZARD = BLIZZARD + SYSTEM

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "ScrollBarSkins": "Core/ScrollBarSkins.lua", "CheckSkins": "Core/CheckSkins.lua",
             "SliderSkins": "Core/SliderSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "DropdownSkins": "Core/DropdownSkins.lua",
             "Character": "Modules/Skins/Character.lua", "GroupKit": "Modules/Skins/GroupKit.lua",
             "Settings": "Modules/Skins/Settings.lua", "System": "Modules/Skins/System.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); SettingsPanel:Show(); FlushTimers()"

case("panel: the inner frame art is held, the output text is mono, the two wells are ringed boxes", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local p = SettingsPanel
    assert(p.fsSettingsSkin, 'not built')
    assert(p.InnerFrameTex.alpha == 0, 'inner frame kept')
    p.InnerFrameTex:SetAlpha(1)
    assert(p.InnerFrameTex.alpha == 0, 'hold not kept')
    assert(p.OutputText.fontPath ~= 'stock.ttf', 'output text not mono')
    assert(S.wells[p.CategoryList] and S.wells[p.Container], 'wells')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("tabs: the stock art is held, a cut plate and mono label are ours, the selected tab is cyan, hover and selection follow", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local game, addons = SettingsPanel.GameTab, SettingsPanel.AddOnsTab
    for _, t in ipairs({{ game, addons }}) do
        assert(S.tabs[t], 'tab not skinned')
        assert(t.Left.alpha == 0 and t.Middle.alpha == 0 and t.Right.alpha == 0, 'stock tab art kept')
        assert(t.Text.fontPath ~= 'stock.ttf', 'label not mono')
        assert(t.scripts.OnClick and t.scripts.OnEnter, 'script lost')
    end
    assert(game.Text.textColor[3] > 0.9 and game.Text.textColor[1] < 0.3, 'selected label not cyan')
    assert(addons.Text.textColor[1] < 0.7, 'idle label not muted')
    addons:OnSelected(true); game:OnSelected(false)
    assert(addons.Text.textColor[3] > 0.9 and addons.Text.textColor[1] < 0.3, 'selection not followed')
    assert(game.Text.textColor[1] < 0.7, 'old tab not muted')
    assert(game.Text.fontPath ~= 'stock.ttf', 'font lost on SetFontObject')
    game:RunScript('OnEnter')
    assert(game.Text.textColor[1] > 0.8, 'hover label not text colour')
    game:RunScript('OnLeave')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("categories: header art held, button rows hold the stock bar, selected = cyan bar and band, hover = violet wash, labels mono", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local rows = SettingsPanel.CategoryList.ScrollBox.rows
    local head, sound, volume, controls = rows[1], rows[2], rows[3], rows[4]
    assert(head.Background.alpha == 0, 'header art kept')
    assert(head.Label.fontPath ~= 'stock.ttf', 'header label')
    for _, r in ipairs({{ sound, volume, controls }}) do
        assert(r.Texture.alpha == 0, 'stock bar kept')
        assert(r.Label.fontPath ~= 'stock.ttf', 'label not mono')
        assert(S.cats[r], 'row not skinned')
    end
    assert(S.cats[volume].led.t.color[4] == 1 and S.cats[volume].led.t.color[2] > 0.8, 'selected bar not cyan')
    assert(S.cats[controls].led.t.color[4] == 0, 'idle bar visible')
    assert(volume.Label.textColor[3] > 0.9 and volume.Label.textColor[1] < 0.3, 'selected label not cyan')
    assert(controls.Label.textColor[1] > 0.8, 'idle label not text')
    controls:RunScript('OnEnter')
    assert(S.cats[controls].box.fill.color[4] > 0.05, 'hover wash missing')
    controls:RunScript('OnLeave')
    controls:UpdateStateInternal(true)
    assert(S.cats[controls].led.t.color[4] == 1, 'selection not followed')
    assert(controls.Label.fontPath ~= 'stock.ttf', 'font lost on SetFontObject')
    assert(controls.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("categories: the expander is a held button with our chevron that follows SetExpanded", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local sound = SettingsPanel.CategoryList.ScrollBox.rows[2]
    local rec = S.toggles[sound.Toggle]
    assert(rec and #rec.open.cells == 5 and #rec.closed.cells == 5, 'chevrons')
    assert(sound.Toggle.NormalTexture.alpha == 0, 'stock expander art kept')
    assert(rec.open.cells[1]:IsShown() and not rec.closed.cells[1]:IsShown(), 'expanded shows the down chevron')
    sound:SetExpanded(false)
    assert(not rec.open.cells[1]:IsShown() and rec.closed.cells[1]:IsShown(), 'collapse not followed')
    assert(sound.Toggle.scripts.OnClick, 'toggle click lost')
""")

case("category rows the pool makes later are skinned after an Update", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local box = SettingsPanel.CategoryList.ScrollBox
    local late = SETTINGS_CATEGORY_BUTTON('Accessibility')
    assert(not S.cats[late], 'skinned before the update')
    box:Update()
    assert(S.cats[late] and late.Texture.alpha == 0, 'late row not skinned')
""")

case("list header: the title is mono cyan, the divider art is held, a rule of ours sits under it", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local head = SettingsPanel.Container.SettingsList.Header
    assert(head.Title.fontPath ~= 'stock.ttf' and head.Title.textColor[3] > 0.9 and head.Title.textColor[1] < 0.3, 'title')
    assert(head.Divider.alpha == 0, 'divider kept')
    assert(S.headers[head], 'no rule')
    assert(head.DefaultsButton.scripts.OnClick, 'defaults click lost')
""")

case("rows: a section title is mono cyan with a rule, an element label is mono text with the stock wash tinted violet", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local rows = SettingsPanel.Container.SettingsList.ScrollBox.rows
    local sec, check, dim = rows[1], rows[2], rows[4]
    assert(sec.Title.fontPath ~= 'stock.ttf' and sec.Title.textColor[3] > 0.9, 'section title')
    assert(S.rows[sec] == 'header', 'section kind ' .. tostring(S.rows[sec]))
    assert(check.Text.fontPath ~= 'stock.ttf' and check.Text.textColor[1] > 0.8, 'label not mono text')
    local w = check.Tooltip.HoverBackground.color
    assert(w[3] > w[1] and w[4] < 0.3, 'row wash not violet ' .. table.concat(w, ','))
    local w2 = check.Checkbox.HoverBackground.color
    assert(w2[3] > w2[1], 'check wash not violet')
    assert(FS.CheckSkins.Parts(check.Checkbox), 'check box not swept')
    assert(dim.Text.textColor[1] < 0.7, 'disabled label not dimmed')
    dim.Text:SetTextColor(1, 0.82, 0, 1)
    assert(dim.Text.textColor[1] > 0.8, 'enabled label not text')
    dim.Text:SetTextColor(0.5, 0.5, 0.5, 1)
    assert(dim.Text.textColor[1] < 0.7 and dim.Text.textColor[3] < 0.7, 'gray not pinned dim')
    check.Text:SetFontObject()
    assert(check.Text.fontPath ~= 'stock.ttf', 'font lost on SetFontObject')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("rows: the slider and the dropdown are swept, the dropdown steppers are held buttons with a violet chevron that lights on hover", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local rows = SettingsPanel.Container.SettingsList.ScrollBox.rows
    local music, out = rows[5], rows[6]
    assert(FS.SliderSkins.Parts(music.SliderWithSteppers.Slider), 'slider not swept')
    assert(FS.DropdownSkins.Parts(out.Control.Dropdown), 'dropdown not swept')
    local dec, inc = out.Control.DecrementButton, out.Control.IncrementButton
    for _, b in ipairs({{ dec, inc }}) do
        assert(S.steppers[b] and #S.steppers[b].cells == 7, 'stepper chevron')
        assert(b.NormalTexture.alpha == 0, 'stock stepper art kept')
        assert(b.scripts.OnClick, 'stepper click lost')
    end
    local c = S.steppers[dec].cells[1].color
    assert(c[3] > 0.8 and c[2] < 0.5, 'idle stepper not violet ' .. table.concat(c, ','))
    dec:RunScript('OnEnter')
    assert(S.steppers[dec].cells[1].color[2] > 0.8, 'hover stepper not cyan')
    dec:RunScript('OnLeave')
    inc:Disable()
    assert(S.steppers[inc].cells[1].color[4] < 1 or S.steppers[inc].cells[1].alpha < 1, 'disabled stepper not dimmed')
""")

case("rows: an expandable section is a band bar with a plus that turns to a minus, the stock art held, the click stays", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local rows = SettingsPanel.Container.SettingsList.ScrollBox.rows
    local sec = rows[7]
    local b = sec.Button
    assert(S.rows[sec] == 'section', 'kind ' .. tostring(S.rows[sec]))
    assert(b.Left.alpha == 0 and b.Right.alpha == 0, 'stock bar kept')
    assert(b.Text.fontPath ~= 'stock.ttf', 'label not mono')
    local g = S.sections[b]
    assert(g and g.vbar:IsShown(), 'collapsed section must show a plus')
    b:RunScript('OnClick')
    assert(not g.vbar:IsShown(), 'expanded section must show a minus')
    assert(b.scripts.OnClick, 'click lost')
""")

case("rows: a button row and a search result are skinned in place", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local rows = SettingsPanel.Container.SettingsList.ScrollBox.rows
    local reset = rows[8]
    assert(FS.ButtonSkins.Parts(reset.Button), 'button row not a text button')
    local s = SETTINGS_SEARCH
    assert(S.rows[s] == 'search' and s.MouseoverOverlay.alpha == 0, 'search row')
    assert(s.Title.fontPath ~= 'stock.ttf', 'search title not mono')
    assert(FS.GroupSkin.cards[s], 'search row not a card')
    s:RunScript('OnEnter')
""")

case("keybindings: the label is mono, the stock highlight is violet, each key cell is a text button with an LED that follows the state", f"""
    {OPEN}
    local S = FS.SettingsSkin.state
    local box = SettingsPanel.Container.SettingsList.ScrollBox
    local row = SETTINGS_BINDING('Move forward', 'W')
    box:Update()
    assert(S.rows[row] == 'binding', 'kind ' .. tostring(S.rows[row]))
    assert(row.Label.fontPath ~= 'stock.ttf', 'label not mono')
    local hl = row.Highlight.color
    assert(hl[3] > hl[1], 'highlight not violet')
    local b1, b2 = row.Button1, row.Button2
    assert(FS.ButtonSkins.Parts(b1) and FS.ButtonSkins.Parts(b2), 'keys not text buttons')
    assert(b1.SelectedHighlight.alpha == 0, 'stock selected art kept')
    local k1, k2 = S.keys[b1], S.keys[b2]
    assert(k1 and k2, 'no key state')
    assert(k1.led.color[3] > 0.8 and k1.led.color[2] < 0.5 and k1.led.color[4] == 1, 'bound key LED not violet')
    assert(k2.led.color[4] < 1, 'unbound key LED not dim')
    b1:SetSelected(true)
    assert(k1.led.color[1] > 0.9 and k1.led.color[2] > 0.6 and k1.led.color[3] < 0.5, 'listening LED not amber')
    assert(k1.box.edges[1].color[4] == 1, 'listening ring missing')
    b1:SetSelected(false)
    assert(k1.box.edges[1].color[4] == 0, 'ring not cleared')
    b2:SetText('V'); b2:SetSelected(false)
    assert(k2.led.color[4] == 1, 'a newly bound key keeps the dim LED')
    assert(b1.scripts.OnClick, 'key click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")


OPEN_ADDONS = "Fire('PLAYER_ENTERING_WORLD'); AddonList:Show(); FlushTimers()"

case("addon list: the performance strip and the force load label are restyled, the divider art is held, the rows are swept", f"""
    {OPEN_ADDONS}
    local S = FS.SystemSkin.state
    local win = AddonList
    assert(win.fsSystemSkin, 'not built')
    assert(win.Performance.Divider.alpha == 0, 'divider kept')
    assert(win.Performance.Header.fontPath ~= 'stock.ttf' and win.Performance.Current.fontPath ~= 'stock.ttf', 'performance texts not mono')
    assert(win.ForceLoad.label.fontPath ~= 'stock.ttf', 'force load label not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("addon list: a category row holds the stock arrow, draws a chevron that follows its collapse state, and its title is cyan mono", f"""
    {OPEN_ADDONS}
    local S = FS.SystemSkin.state
    local cat = AddonList.ScrollBox.rows[1]
    local cx = cat.CollapseExpand
    assert(S.cats[cat], 'category not skinned')
    assert(cx.Normal.alpha == 0 and cx.Pushed.alpha == 0 and cx.Highlight.alpha == 0, 'stock arrow kept')
    assert(cat.Title.fontPath ~= 'stock.ttf' and cat.Title.textColor[3] > 0.9 and cat.Title.textColor[1] < 0.3, 'title not cyan mono')
    local rec = S.cats[cat]
    assert(rec.open.cells[1]:IsShown() and not rec.closed.cells[1]:IsShown(), 'expanded shows the down chevron')
    cx:RunScript('OnClick')
    assert(not rec.open.cells[1]:IsShown() and rec.closed.cells[1]:IsShown(), 'collapse not followed')
    assert(cx.scripts.OnClick and cat.scripts.OnClick, 'click lost')
""")

case("addon list: an entry row maps the stock title colours (gold, red, gray), pins status and reload, holds the stock highlight, lights on hover", f"""
    {OPEN_ADDONS}
    local S = FS.SystemSkin.state
    local rows = AddonList.ScrollBox.rows
    local ok, some, off, bad, reload, lod = rows[2], rows[3], rows[4], rows[5], rows[6], rows[7]
    for _, r in ipairs({{ ok, some, off, bad }}) do
        assert(S.rows[r], 'entry not skinned')
        assert(r.Title.fontPath ~= 'stock.ttf', 'title not mono')
        assert(r.highlightTex.alpha == 0, 'stock highlight kept')
    end
    assert(ok.Title.textColor[1] > 0.8 and ok.Title.textColor[3] > 0.9, 'enabled title not text colour')
    assert(off.Title.textColor[1] < 0.5 and off.Title.textColor[3] < 0.7, 'disabled title not dim')
    assert(bad.Title.textColor[1] > 0.9 and bad.Title.textColor[2] < 0.3 and bad.Title.textColor[3] > 0.4, 'failed title not pink')
    ok.Title:SetTextColor(0.5, 0.5, 0.5, 1)
    assert(ok.Title.textColor[1] < 0.5, 'gray not followed')
    ok.Title:SetFontObject()
    assert(ok.Title.fontPath ~= 'stock.ttf', 'font lost on SetFontObject')
    assert(off.Status.fontPath ~= 'stock.ttf' and off.Status.textColor[1] > 0.9 and off.Status.textColor[3] < 0.5, 'status not amber mono')
    assert(reload.Reload.fontPath ~= 'stock.ttf' and reload.Reload.textColor[1] > 0.9 and reload.Reload.textColor[3] > 0.4, 'reload not pink')
    assert(FS.CheckSkins.Parts(ok.Enabled), 'lamp not the shared check')
    assert(FS.ButtonSkins.Parts(lod.LoadAddonButton), 'load button not a text button')
    assert(S.rows[some].some:IsShown() and not S.rows[ok].some:IsShown(), 'partial bar')
    ok:RunScript('OnEnter')
    assert(S.rows[ok].box.fill.color[4] > 0.05, 'hover wash missing')
    ok:RunScript('OnLeave')
    assert(S.rows[ok].box.fill.color[4] == 0, 'hover wash stuck')
    assert(ok.scripts.OnClick and ok.scripts.OnEnter, 'script lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("addon list: rows the pool makes later are skinned after an Update", f"""
    {OPEN_ADDONS}
    local S = FS.SystemSkin.state
    local late = ADDON_ENTRY('Late Addon', {{}})
    assert(not S.rows[late], 'skinned before the update')
    AddonList.ScrollBox:Update()
    assert(S.rows[late] and late.highlightTex.alpha == 0, 'late row not skinned')
""")

case("addon dialog: the border frame and art are held, the chrome and an LED are ours, the text is mono, the buttons are swept", f"""
    Fire('PLAYER_ENTERING_WORLD'); AddonDialog:Show(); FlushTimers()
    local S = FS.SystemSkin.state
    local bg = AddonDialogBackground
    assert(S.dialogs[bg], 'no chrome')
    assert(bg.NineSlice.alpha == 0 and bg.Bg.alpha == 0, 'border kept')
    assert(AddonDialogText.fontPath ~= 'stock.ttf', 'text not mono')
    assert(FS.ButtonSkins.Parts(AddonDialogButton1) and FS.ButtonSkins.Parts(AddonDialogButton2), 'buttons not swept')
    assert(AddonDialogButton1.scripts.OnClick, 'click lost')
""")

case("quick key bind: the dialog border is held, the header is a cut tab with cyan mono text, the texts are mono, the keys are swept", f"""
    Fire('PLAYER_ENTERING_WORLD'); QuickKeybindFrame:Show(); FlushTimers()
    local S = FS.SystemSkin.state
    local qk = QuickKeybindFrame
    assert(qk.fsSystemSkin and S.dialogs[qk], 'not built')
    assert(qk.BG.alpha == 0, 'border frame kept')
    local h = qk.Header
    assert(h.LeftBG.alpha == 0 and h.RightBG.alpha == 0 and h.CenterBG.alpha == 0, 'stock header art kept')
    assert(S.headers[h], 'no header plate')
    assert(h.Text.fontPath ~= 'stock.ttf' and h.Text.textColor[3] > 0.9 and h.Text.textColor[1] < 0.3, 'header text')
    for _, k in ipairs({{ 'InstructionText', 'CancelDescriptionText', 'OutputText' }}) do
        assert(qk[k].fontPath ~= 'stock.ttf', k .. ' not mono')
    end
    assert(FS.ButtonSkins.Parts(qk.OkayButton) and FS.ButtonSkins.Parts(qk.CancelButton) and FS.ButtonSkins.Parts(qk.DefaultsButton), 'keys')
    assert(FS.CheckSkins.Parts(qk.UseCharacterBindingsButton), 'check not swept')
    assert(qk.DefaultsButton.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("help: the panel wears the shared skin, the browser inset is held, a ring and brackets sit over the page, the state chip follows the stock state", f"""
    Fire('PLAYER_ENTERING_WORLD'); HelpFrame:Show(); FlushTimers()
    local S = FS.SystemSkin.state
    local help = HelpFrame
    assert(help.fsHelpSkin and help.fsPanelSkin, 'not built')
    assert(help.Browser.BrowserInset.NineSlice.alpha == 0 and help.Browser.BrowserInset.Bg.alpha == 0, 'inset kept')
    local h = S.help
    assert(h and h.ring and h.brackets, 'no ring or brackets')
    assert(h.ring.fill.color[4] == 0, 'the ring box must not cover the page')
    assert(h.chip.label.text == 'connecting' and h.chip.color[1] > 0.9 and h.chip.color[3] < 0.5, 'connecting is amber')
    help:SetInitialLoading(false)
    assert(h.chip.label.text == 'linked' and h.chip.color[3] > 0.9 and h.chip.color[1] < 0.3, 'linked is cyan')
    help:ShowUnavailable()
    assert(h.chip.label.text == 'no signal' and h.chip.color[1] > 0.9 and h.chip.color[3] > 0.4, 'no signal is pink')
    help:SetInitialLoading(true)
    assert(h.chip.label.text == 'connecting', 'connecting again')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'GroupKit', 'Settings', 'System' }})
    assert(not SettingsPanel.fsSettingsSkin and not AddonList.fsSystemSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(SettingsPanel.fsSettingsSkin and AddonList.fsSystemSkin, 'not built when combat ended')
""")

# what Panels.lua does to the window (SkinPanel, the sweep, the Apply and Defaults plates), so the render shows the whole window
CHROME = """Fire('PLAYER_ENTERING_WORLD')
    FS.Theme.SkinPanel(SettingsPanel, { fillColor = FS.Theme.COLOR_BG, borderColor = FS.Theme.COLOR_BORDER, title = 'settings' })
    FS.PanelSkins.SweepOnShow(SettingsPanel)
    FS.ButtonSkins.SkinTextButton(SettingsPanel.ApplyButton)
    FS.ButtonSkins.SkinTextButton(SettingsPanel.Container.SettingsList.Header.DefaultsButton, { accent = 'pink' })
    SettingsPanel:Show(); FlushTimers()"""
KEYS = """local box = SettingsPanel.Container.SettingsList.ScrollBox
    for _, r in ipairs(box.rows) do r:Hide() end
    box.y = 0
    SettingsPanel.Container.SettingsList.Header.Title:SetText('Keybindings')
    for _, spec in ipairs({ { 'Move forward', 'W', 'UP' }, { 'Move backward', 'S', 'DOWN' }, { 'Turn left', 'A' }, { 'Turn right', 'D' },
        { 'Jump', 'SPACE' }, { 'Toggle auto run', nil }, { 'Action button 1', '1' } }) do
        SETTINGS_BINDING(spec[1], spec[2], spec[3])
    end
    box:Update(); FlushTimers()
    box.rows[#box.rows - 1].Button1:RunScript('OnEnter')
    box.rows[#box.rows].Button2:SetSelected(true)
    box.rows[#box.rows - 3].Highlight:Show()"""

ADDONS = """Fire('PLAYER_ENTERING_WORLD')
    FS.Theme.SkinPanel(AddonList, { fillColor = FS.Theme.COLOR_BG, borderColor = FS.Theme.COLOR_BORDER, title = 'addons' })
    FS.PanelSkins.SweepOnShow(AddonList)
    AddonList:Show(); FlushTimers()
    AddonList.ScrollBox.rows[2].Enabled:SetChecked(true)
    AddonList.ScrollBox.rows[4]:RunScript('OnEnter')"""

SCENES = {
    "settings": CHROME + "; return DumpOps({ SettingsPanel })",
    "addons": ADDONS + "; return DumpOps({ AddonList })",
    "quickkeybind": "Fire('PLAYER_ENTERING_WORLD'); QuickKeybindFrame:Show(); FlushTimers(); return DumpOps({ QuickKeybindFrame })",
    "help": "Fire('PLAYER_ENTERING_WORLD'); HelpFrame:Show(); FlushTimers(); HelpFrame:SetInitialLoading(false); return DumpOps({ HelpFrame })",
    "addondialog": "Fire('PLAYER_ENTERING_WORLD'); AddonDialog:Show(); FlushTimers(); return DumpOps({ AddonDialogBackground })",
    "keybindings": CHROME + "\n    " + KEYS + "\n    return DumpOps({ SettingsPanel })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("settings skin", SCENES))
