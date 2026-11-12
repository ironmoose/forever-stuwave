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
function Obj:SetFocus() end
function Obj:ClearFocus() end

-- text
function Obj:SetFont(path, size, flags) self.fontPath, self.size, self.flags = path, size, flags; return true end
function Obj:GetFont() return self.fontPath, self.size, self.flags end
function Obj:SetFontObject() end
function Obj:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a or 1 } end
function Obj:SetShadowColor() end
function Obj:SetShadowOffset() end
function Obj:SetJustifyH(j) self.justify = j end
function Obj:SetJustifyV() end
function Obj:SetWordWrap() end
function Obj:SetTextInsets() end
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
function Obj:SetVertTile() end
function Obj:SetDesaturated() end
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
    for _, name in ipairs({ "Theme", "Layout", "HeldArt", "ControlKit", "CheckSkins", "PanelSkins" }) do
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
-- Every texture and frame under `root` sits on whole screen pixels (fonts excepted).
function WholePixels(root, ref, what)
    local n = 0
    local function visit(o)
        for _, r in ipairs(o.regions) do
            if r.kind ~= "FontString" and r.shown ~= false then
                local l, t, rr, b = Px(r, ref)
                for _, v in ipairs({ l, t, rr, b }) do
                    assert(Near(v, math.floor(v + 0.5), 0.001), string.format("%s: %s edge %.4f is not a whole pixel", what, tostring(r.path or r.kind), v))
                end
                n = n + 1
            end
        end
        for _, c in ipairs(o.children) do visit(c) end
    end
    visit(root)
    return n
end
function Colour(t) return t.color or t.vertex end
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
                total = font.getlength(text)
                x = l if op["justify"] == "LEFT" else (r - total if op["justify"] == "RIGHT" else (l + r) / 2 - total / 2)
                d.text((x, (t + b) / 2), text, font=font, fill=col, anchor="lm")
            elif kind == "tex":
                src = cache.get(op["file"])
                if src is None:
                    src = Image.open(TEXTURES / op["file"]).convert("RGBA")
                    cache[op["file"]] = src
                c = op.get("coords")
                if c:
                    w0, h0 = src.size
                    src2 = src.crop((round(c[1] * w0), round(c[3] * h0), round(c[2] * w0), round(c[4] * h0)))
                else:
                    src2 = src
                if r - l > 0 and b - t > 0:
                    tile = src2.resize((r - l, b - t), Image.NEAREST)
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
