#!/usr/bin/env python3
"""Runs ActionBars.lua, StanceBar.lua, PetActionBar.lua and the real
FrameHelpers.lua headless against a small mock WoW API.

Why this exists: the parse gate proves the files compile and lua-lint proves
their names resolve, but neither RUNS a line of them. These checks pin two
behaviours that were only ever seen in game:

  * the cooldown swipe on our custom buttons reaches the button face edge to
    edge (the inherited ActionButtonTemplate anchors it 3px INSIDE the icon);
  * Blizzard's Quick Keybind mode can bind our buttons (they carry a
    commandName and forward their mouse/hover events to the stock handlers).

It is NOT a rendering test and NOT the real client. Two things in the mock are
modelled on Blizzard's own source and are the weak points to keep honest:

  * the ActionButtonTemplate cooldown anchors (3px inset from the icon), copied
    from Blizzard_ActionBar/Mainline/ActionButtonTemplate.xml in the retail 12.1
    reference tree (the 16001 Classic variant is not in that tree);
  * QuickKeybindButtonTemplateMixin / QuickKeybindFrame, a line-for-line
    reduction of Blizzard_QuickKeybind/QuickKeybind.lua.

    python3 tools/actionbars-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"

MOCK = r"""
__frames = {}
__degraded = {}

local Region = {}
Region.__index = Region
__Region = Region
__blocked = 0      -- protected operations the "engine" refused in combat
__protectedTouch = 0   -- frames created, anchored or re-levelled under a protected parent in combat

local function touchUnderProtected(self)
    local p = self._parent
    if __combat and p and p._protected then __protectedTouch = __protectedTouch + 1 end
end
__degradeCount = 0

local function new(kind, name, parent)
    local r = setmetatable({
        _kind = kind, _name = name, _parent = parent, _points = {}, _scripts = {},
        _hooks = {}, _attrs = {}, _regions = {}, _registered = {}, _shown = true,
        _alpha = 1, _level = (parent and parent._level or 0) + 1, _w = 0, _h = 0,
    }, Region)
    if parent then parent._regions[#parent._regions + 1] = r end
    touchUnderProtected(r)
    __frames[#__frames + 1] = r
    if name then _G[name] = r end
    return r
end

function Region:GetObjectType() return self._kind end
function Region:GetName() return self._name end
function Region:SetSize(w, h) self._w, self._h = w, h end
function Region:GetSize() return self._w, self._h end
function Region:SetWidth(w) self._w = w end
function Region:GetWidth() return self._w end
function Region:SetHeight(h) self._h = h end
function Region:GetHeight() return self._h end
function Region:SetPoint(point, rel, relPoint, x, y)
    touchUnderProtected(self)
    if type(rel) == "number" or rel == nil then x, y, rel, relPoint = rel, relPoint, self._parent, point end
    self._points[#self._points + 1] = { point = point, rel = rel or self._parent,
        relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Region:ClearAllPoints() self._points = {} end
function Region:SetAllPoints(rel)
    touchUnderProtected(self)
    self._points = {}
    self:SetPoint("TOPLEFT", rel or self._parent, "TOPLEFT", 0, 0)
    self:SetPoint("BOTTOMRIGHT", rel or self._parent, "BOTTOMRIGHT", 0, 0)
end
function Region:GetParent() return self._parent end
function Region:SetParent(p) self._parent = p end
function Region:GetFrameLevel() return self._level end
function Region:SetFrameLevel(l) touchUnderProtected(self); self._level = l end
function Region:SetFrameStrata(strata) self._strata = strata end
-- The engine refuses protected operations on a protected frame in combat and
-- (for a SecureActionButtonTemplate button) SetAttribute. Frames opt in with
-- _protected; secure buttons are marked in CreateFrame below.
local function blockedInCombat(self)
    if self._protected and __combat then __blocked = __blocked + 1; return true end
end
function Region:CanChangeProtectedState() return not (self._protected and __combat) end
function Region:Show() if blockedInCombat(self) then return end; self._shown = true; Region.Fire(self, "OnShow") end
function Region:Hide() if blockedInCombat(self) then return end; self._shown = false; Region.Fire(self, "OnHide") end
function Region:SetShown(v) if v then self:Show() else self:Hide() end end
function Region:IsShown() return self._shown end
function Region:SetAlpha(a) self._alpha = a end
-- The one sanctioned consumer of a secret boolean; records what it was handed, never tests it.
function Region:SetAlphaFromBoolean(flag, whenTrue, whenFalse)
    self._fromBool = { flag = flag, t = whenTrue, f = whenFalse }
end
function Region:GetAlpha() return self._alpha end
function Region:EnableMouse(v) self._mouse = v end
function Region:IsMouseEnabled() return self._mouse end
-- Child FRAMES only (the engine keeps regions apart); the mock files both in _regions.
function Region:GetChildren()
    local out = {}
    for _, r in ipairs(self._regions) do
        if r._kind ~= "Texture" and r._kind ~= "FontString" and r._kind ~= "MaskTexture" then out[#out + 1] = r end
    end
    return unpack(out)
end
function Region:EnableMouseWheel(v) self._wheel = v end
function Region:SetClipsChildren() end
function Region:SetAttribute(k, v)
    if self._secure and __combat then __blocked = __blocked + 1; return end
    self._attrs[k] = v
end
function Region:GetAttribute(k) return self._attrs[k] end
-- The numeric id a paged button carries (SecureActionButtonMixin:CalculateAction reads it); 0 when unset.
function Region:SetID(id)
    if self._secure and __combat then __blocked = __blocked + 1; return end
    self._id = id
end
function Region:GetID() return self._id or 0 end
function Region:RegisterForClicks(...) self._clicks = { ... } end
function Region:RegisterForDrag() end
function Region:RegisterEvent(e) self._registered[e] = true end
function Region:RegisterUnitEvent(e) self._registered[e] = true end
function Region:UnregisterEvent(e) self._registered[e] = nil end
function Region:UnregisterAllEvents() self._registered = {} end
function Region:SetScript(k, fn) self._scripts[k] = fn end
function Region:GetScript(k) return self._scripts[k] end
function Region:HookScript(k, fn)
    self._hooks[k] = self._hooks[k] or {}
    table.insert(self._hooks[k], fn)
end
-- Runs the main handler, then every HookScript post-hook, like the engine.
function Region.Fire(self, k, ...)
    if self._scripts[k] then self._scripts[k](self, ...) end
    for _, fn in ipairs(self._hooks[k] or {}) do fn(self, ...) end
end
function Region:CreateTexture(name, layer, tmpl, sub)
    local t = new("Texture", name, self); t._layer, t._sub = layer, sub; return t
end
function Region:CreateMaskTexture() return new("MaskTexture", nil, self) end
-- The client throws "Font not set" for SetText / SetFormattedText on a FontString with no font: one made
-- with an inherits template carries that template's font, otherwise SetFont / SetFontObject (Theme.ApplyMono
-- calls SetFont) must come first. A write before that kills a pcall'd build.
function Region:CreateFontString(name, layer, template)
    local f = new("FontString", name, self); f._layer = layer
    if type(template) == "string" then f._hasFont = true end
    return f
end
function Region:GetRegions() return unpack(self._regions) end
-- texture / fontstring bits
function Region:SetTexture(t) self._texture = t end
function Region:SetColorTexture(r, g, b, a) self._color = { r, g, b, a } end
function Region:SetVertexColor(r, g, b, a) self._vertex = { r, g, b, a } end
function Region:SetBlendMode(m) self._blend = m end
function Region:SetTexCoord() end
function Region:SetDrawLayer(l, s) self._layer, self._sub = l, s end
function Region:AddMaskTexture(m) self._maskedBy = m end
function Region:SetText(t)
    if self._kind == "FontString" and not self._hasFont then error("Font not set", 2) end
    self._text = t
end
function Region:SetFormattedText(fmt, ...)
    if self._kind == "FontString" and not self._hasFont then error("Font not set", 2) end
    self._text = string.format(fmt, ...)
end
function Region:GetText() return self._text end
function Region:SetJustifyH() end
function Region:SetFont(path, size, flags) self._hasFont = true; self._font = { path, size, flags }; return true end
function Region:SetFontObject() self._hasFont = true end
function Region:GetFont() return "x", 10, "" end
function Region:SetTextColor(r, g, b, a) self._textColor = { r, g, b, a } end
-- button bits
function Region:SetChecked(v) self._checked = v and true or false end
function Region:GetChecked() return self._checked or false end
function Region:GetNormalTexture() return self.NormalTexture end
function Region:GetHighlightTexture() return self._highlight end
function Region:IsMouseOver() return self._mouseOver or false end
function Region:GetPushedTexture() return self._pushed end
function Region:GetCheckedTexture() return self._checkedT or self._checkedTexture end
function Region:SetPushedTexture(t) self._pushed = t end
function Region:GetButtonState() return self._state or "NORMAL" end
function Region:SetButtonState(state) self._state = state end
function Region:SetCheckedTexture(t) self._checkedTexture = t end
function Region:SetTextureSliceMargins(l, t, r, b) self._slice = { l, t, r, b } end
-- cooldown bits
function Region:SetCooldown(s, d) self._cd = { s, d } end
function Region:SetHideCountdownNumbers(v) self._hideNumbers = v end
-- The template's own countdown FontString, made on first ask and carrying a font like the real one.
function Region:GetCountdownFontString()
    if not self._countdownFs then
        self._countdownFs = new("FontString", nil, self)
        self._countdownFs._hasFont = true
    end
    return self._countdownFs
end
function Region:SetCooldownFromDurationObject(o) self._cdObj = o end
function Region:Clear() self._cdObj = nil end
function Region:SetDrawEdge(v) self._drawEdge = v end
function Region:SetDrawBling(v) self._drawBling = v end
function Region:SetDrawSwipe(v) self._drawSwipe = v end
function Region:SetSwipeTexture(t, r, g, b, a) self._swipeTexture = t; self._swipeColor = { r, g, b, a } end
function Region:SetSwipeColor(r, g, b, a) self._swipeColor = { r, g, b, a } end
function Region:SetUsingParentLevel(v) self._useParentLevel = v end

-- Whole-word match: "SecureActionButtonTemplate" must NOT count as inheriting
-- "ActionButtonTemplate" (the stance and pet buttons use the bare secure one).
local function hasToken(template, token)
    return template and template:find("%f[%w]" .. token) ~= nil
end

-- What Blizzard's ActionButtonTemplate hands every button built on it. The
-- cooldown anchors are the REAL template's: 3px inside the icon on every side
-- (Blizzard_ActionBar/Mainline/ActionButtonTemplate.xml, the <Cooldown ...
-- parentKey="cooldown"> block). Our StyleButton re-anchors the icon, never the
-- cooldown, so that inset survives onto our smaller buttons.
local function applyActionButtonTemplate(btn)
    btn.icon = btn:CreateTexture(nil, "BACKGROUND")
    btn.icon:SetAllPoints(btn)
    btn.NormalTexture = btn:CreateTexture(nil, "ARTWORK")
    btn._highlight = btn:CreateTexture(nil, "HIGHLIGHT")
    btn._checkedT = btn:CreateTexture(nil, "ARTWORK")   -- the template's CheckedTexture
    btn._pushed = btn:CreateTexture(nil, "ARTWORK")   -- the template's PushedTexture, an anonymous region
    -- Blizzard's template XML gives these three their fonts (NumberFontNormal and friends).
    btn.HotKey = btn:CreateFontString(nil, "OVERLAY", "NumberFontNormal")
    btn.Count = btn:CreateFontString(nil, "OVERLAY", "NumberFontNormal")
    btn.Name = btn:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmallOutline")
    local cd = new("Cooldown", nil, btn)
    cd._level = btn._level      -- useParentLevel="true"
    cd:SetPoint("TOPLEFT", btn.icon, "TOPLEFT", 3, -3)
    cd:SetPoint("BOTTOMRIGHT", btn.icon, "BOTTOMRIGHT", -3, 3)
    btn.cooldown = cd
    -- The other two cooldown frames of the real template: the loss-of-control
    -- one has the same 3px inset, the charge one a 2px inset and no swipe. The
    -- loss-of-control swipe colour is deliberately NOT seeded (the real template's
    -- 16001 variant is unknown): the check must prove our code sets the red.
    local loc = new("Cooldown", nil, btn)
    loc._level = btn._level
    loc:SetPoint("TOPLEFT", btn.icon, "TOPLEFT", 3, -3)
    loc:SetPoint("BOTTOMRIGHT", btn.icon, "BOTTOMRIGHT", -3, 3)
    btn.lossOfControlCooldown = loc
    local charge = new("Cooldown", nil, btn)
    charge._level = btn._level
    charge:SetPoint("TOPLEFT", btn.icon, "TOPLEFT", 2, -2)
    charge:SetPoint("BOTTOMRIGHT", btn.icon, "BOTTOMRIGHT", -2, 2)
    charge:SetDrawSwipe(false)
    btn.chargeCooldown = charge
end

function CreateFrame(kind, name, parent, template)
    local f = new(kind, name, parent)
    if hasToken(template, "SecureActionButtonTemplate") or hasToken(template, "ActionButtonTemplate") then
        f._secure, f._protected = true, true
    end
    if hasToken(template, "ActionButtonTemplate") then applyActionButtonTemplate(f) end
    if kind == "Cooldown" then f._level = (parent and parent._level or 0) + 1 end
    return f
end

UIParent = new("Frame", "UIParent", nil)
UIParent._w, UIParent._h = 2560, 1440
function UIParent:GetWidth() return self._w end

-- Insets (l, t, r, b) of frame f measured from `button`'s edges, following
-- TOPLEFT/BOTTOMRIGHT anchors through intermediate regions such as the icon.
function __insets(f, button)
    if f == button then return { 0, 0, 0, 0 } end
    local tl, br
    for _, p in ipairs(f._points) do
        if p.point == "TOPLEFT" then tl = p elseif p.point == "BOTTOMRIGHT" then br = p end
    end
    assert(tl and br, "frame needs TOPLEFT and BOTTOMRIGHT anchors")
    local a, b = __insets(tl.rel, button), __insets(br.rel, button)
    return { a[1] + tl.x, a[2] - tl.y, b[3] - br.x, b[4] + br.y }
end

function __fire_event(event, ...)
    for _, f in ipairs(__frames) do
        if f._registered[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end

-- ---- WoW API surface the three files touch -----------------------------
__combat = false
__bindings = {}
function InCombatLockdown() return __combat end
function GetBindingKey(action) return __bindings[action] end
function GetBindingText(key) return key and key:gsub("^BUTTON", "M") or "" end
-- Mouseover casting settings: the CVar and the MOUSEOVERCAST modified-click key. SetModifiedClick
-- and SaveBindings are protected in combat on the real client (modelled as refused: error + __blocked);
-- __settings records every call in order so a check can pin both the arguments and the sequence.
__cvars = { enableMouseoverCast = "0" }
__modClicks = { PICKUPACTION = "SHIFT", MOUSEOVERCAST = "NONE" }
__settings = {}
__prints = {}
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[i] = tostring((select(i, ...))) end
    __prints[#__prints + 1] = table.concat(t, " ")
end
function GetCVarBool(name) return __cvars[name] == "1" end
function GetCVar(name) return __cvars[name] end
-- __cvarRefuses models the client declining a SetCVar: it returns false without throwing.
__cvarRefuses = false
function SetCVar(name, value)
    __settings[#__settings + 1] = "SetCVar:" .. tostring(name) .. "=" .. tostring(value)
    if __cvarRefuses then return false end
    __cvars[name] = tostring(value)
    return true
end
function GetModifiedClick(action) return __modClicks[action] or "SHIFT" end
function SetModifiedClick(action, key)
    if __combat then __blocked = __blocked + 1; error("SetModifiedClick blocked in combat", 2) end
    __settings[#__settings + 1] = "SetModifiedClick:" .. tostring(action) .. "=" .. tostring(key)
    __modClicks[action] = key
end
function GetCurrentBindingSet() return 1 end
function SaveBindings(set)
    if __combat then __blocked = __blocked + 1; error("SaveBindings blocked in combat", 2) end
    __settings[#__settings + 1] = "SaveBindings:" .. tostring(set)
end
function IsModifiedClick() return false end
function HasAction() return true end
function GetActionTexture() return "tex" end
function GetActionCooldown() return 0, 0, 1 end
function IsUsableAction() return true, false end
function IsActionInRange() return true end
-- Queued / toggled-on state: slot -> true. A value may be __SECRET (what combat hands back).
__current, __autorepeat = {}, {}
function IsCurrentAction(slot) return __current[slot] or false end
function IsAutoRepeatAction(slot) return __autorepeat[slot] or false end
function GetActionBarPage() return 1 end
function GetNumShapeshiftForms() return 2 end
function GetShapeshiftFormInfo(i) return "tex", i == 1, true, 100 + i end
function GetShapeshiftFormCooldown() return 0, 0, 1 end
NUM_PET_ACTION_SLOTS = 3
function GetPetActionInfo(i) return "Attack", "tex", false, false, false, false, 1, false, nil end
function GetPetActionCooldown() return 0, 0, 1 end
function PickupAction() end
function PlaceAction() end
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
SlashCmdList = {}
C_ActionBar = {
    GetActionDisplayCount = function() return "" end,
    GetActionCooldownDuration = function() return { duration = true } end,
}
GameTooltip = new("GameTooltip", nil, UIParent)
function GameTooltip:SetOwner() end
function GameTooltip:SetAction() end
function GameTooltip:SetShapeshift() end
function GameTooltip:SetPetAction() self._lines = {} end
function GameTooltip:AddLine(t) self._lines = self._lines or {}; self._lines[#self._lines + 1] = t end

-- A real secret sentinel: a table every arithmetic, ordering, concat, call and index operation
-- raises on (what a secret does when code uses it). `#`, `==` and truth tests are NOT trapped (a
-- Lua table cannot trap its own truth test, and lupa/luajit does not honour __len or __eq here),
-- so a bare `if secret then` goes through silently; the checks catch that by behaviour (an
-- unguarded read lights or animates a ring), the way __secretFalse catches it for a falsy value.
__SECRET = setmetatable({}, {
    __index = function() error("secret value indexed", 2) end,
    __newindex = function() error("secret value written", 2) end,
    __call = function() error("secret value called", 2) end,
    __concat = function() error("secret value concatenated", 2) end,
    __lt = function() error("secret value compared", 2) end,
    __le = function() error("secret value compared", 2) end,
    __add = function() error("secret value in arithmetic", 2) end,
    __sub = function() error("secret value in arithmetic", 2) end,
    __mul = function() error("secret value in arithmetic", 2) end,
    __div = function() error("secret value in arithmetic", 2) end,
    __unm = function() error("secret value in arithmetic", 2) end,
    __tostring = function() return "<secret>" end,
})

FS = {
    -- Two secret stand-ins: __SECRET (above), and the falsy one the secret-guard checks use: they set
    -- __secretFalse so a bare `false` reads as a secret value (a naive `not <secret>` cannot be mocked,
    -- so a falsy one is what makes unguarded code defer the overlay).
    IsSecret = function(v) return rawequal(v, __SECRET) or (__secretFalse == true and v == false) end,
    LogDegradeOnce = function(key, msg) __degraded[key] = msg; __degradeCount = __degradeCount + 1 end,
    Layout = {
        action = { w = 1089, h = 178 }, stance = { w = 100, h = 38 }, grid = { w = 2560, h = 183 },
        Apply = function(frame, id)
            local L = FS.Layout[id]
            frame:SetSize(L.w, L.h)
            return { w = L.w, h = L.h, scaledW = L.w, scaledH = L.h }
        end,
        OnRescale = function() end,
        Scale = function() return 1 end,
    },
    Theme = {
        FLAT_TEXTURE = "flat", SLICE_BUTTON_TEXTURE = "slice_button",
        SLICE_GLOW_TEXTURE = "slice_glow",
        SLICE_BORDER_TEXTURE = "slice_border",
        COLOR_BORDER = { 0.659, 0.333, 0.969, 1 },
        SLICE_CUT2_BUTTON_TEXTURE = "slice_cut2_button",
        SLICE_CUT2_FILL_TEXTURE = "slice_cut2_fill",
        SLICE_CUT2_OUTLINE_TEXTURE = "slice_cut2_outline",
        SLICE_CUT2_GLOW_TEXTURE = "slice_cut2_glow",
        COLOR_POWER = { 0.13, 0.88, 1 }, COLOR_HEALTH = { 1, 0.18, 0.59 },
        COLOR_TEXT_WHITE = { 1, 1, 1 }, COLOR_CARET_HEALTH = { 0.2, 1, 0.1 },
        AddRoundedFill = function() end,
        AddGradientBorder = function() end, AddOuterGlow = function() end,
        FONT_MONO = "mono.ttf",
        ApplyMono = function(fs, size) fs:SetFont("mono.ttf", size, "") end,   -- the real one calls SetFont
        -- the real one: SetFont then SetTextColor (the shadow and fallback-path parts are not modelled)
        ApplyFontGeneric = function(fs, path, size, color, flags)
            fs:SetFont(path, size, flags == nil and "OUTLINE" or flags)
            local c = color or { 1, 1, 1, 1 }
            fs:SetTextColor(c[1], c[2], c[3], c[4] or 1)
        end,
        -- The numeric SLICE_* constants (margins and glow pads) are the REAL ones too,
        -- evaluated from Theme.lua by boot() through __load_theme_constants, so a
        -- drift there reaches the checks instead of hiding behind a copy.
        -- ApplyNineSlice, AddSliceTexture, AddCut2Texture, SkinButton and
        -- SkinCutButton are the REAL Theme.lua functions, loaded by boot() through
        -- __load_theme_functions, so the cut2 texture opts and slice margins the bars
        -- end up with are what the shipped code produces, not a copy of it.
    },
}
FS.PetFrame = { barSlot = new("Frame", "FSPetBarSlot", UIParent) }

-- The Config surface ActionBars reads: defaults, per-profile settings, OnChange callbacks, and a
-- profile switch that fires the keys whose effective value differs (Config.lua's FireDifferences).
do
    local defaults, callbacks = {}, {}
    local profiles, active = { Default = {}, Other = {} }, "Default"
    local function effective(name, key)
        local v = profiles[name][key]
        if v == nil then v = defaults[key] end
        return v
    end
    FS.Config = {
        RegisterDefault = function(key, value) defaults[key] = value end,
        Get = function(key) return effective(active, key) end,
        Set = function(key, value)
            local old = effective(active, key)
            profiles[active][key] = value
            local new = effective(active, key)
            if old ~= new then
                for _, fn in ipairs(callbacks[key] or {}) do fn(new, old, key) end
            end
            return true
        end,
        OnChange = function(key, fn)
            callbacks[key] = callbacks[key] or {}
            table.insert(callbacks[key], fn)
        end,
        SetActiveProfile = function(name)
            local old = active
            active = name
            for key, fns in pairs(callbacks) do
                local was, now = effective(old, key), effective(active, key)
                if was ~= now then for _, fn in ipairs(fns) do fn(now, was, key) end end
            end
            return true
        end,
    }
end

function __load(path, src)
    local fn = assert(loadstring(src, "@" .. path))
    return fn("forever-stuwave", FS)
end

-- Compiles the named top-level `function Theme.<name>` definitions out of the real
-- Theme.lua source (`defs` maps name -> source text) into FS.Theme.
function __load_theme_functions(defs, names, localDefs)
    local chunk = "local Theme = ...; local warnedNoSliceMargins = false\n"
    for _, src in ipairs(localDefs) do chunk = chunk .. src .. "\n" end
    for _, name in ipairs(names) do chunk = chunk .. defs[name] .. "\n" end
    assert(loadstring(chunk, "@Theme.lua(extract)"))(FS.Theme)
end

-- Runs the named single-line `Theme.<NAME> = <expr>` assignments out of the real
-- Theme.lua (`lines` is their source text, in file order, so a derived constant such
-- as SLICE_CUT2_GLOW_MARGIN sees the ones it is built from).
function __load_theme_constants(lines)
    assert(loadstring("local Theme = ...\n" .. table.concat(lines, "\n"), "@Theme.lua(constants)"))(FS.Theme)
end

function __login()
    __fire_event("PLAYER_LOGIN")
end

function __button(bar, i) return _G[("FSActionButton%d_%d"):format(bar, i)] end

-- ---- Blizzard_QuickKeybind, reduced -------------------------------------
-- Line-for-line the parts of Blizzard_QuickKeybind/QuickKeybind.lua our buttons
-- reach: the mixin methods the stock buttons forward to, and the frame's
-- SetSelected / OnKeyDown entry points (the real ones drive KeybindListener,
-- which is recorded here instead). KeybindFrames_InQuickKeybindMode is the
-- real one-liner from BindingUtil.lua.
function __install_qk()
    __qk = { selected = nil, keys = {}, tooltips = 0 }
    QuickKeybindFrame = new("Button", "QuickKeybindFrame", UIParent)
    QuickKeybindFrame._shown = false
    function QuickKeybindFrame:SetSelected(command, button)
        self.mouseOverButton = button
        __qk.selected = command
    end
    function QuickKeybindFrame:OnKeyDown(input) __qk.keys[#__qk.keys + 1] = input end
    function QuickKeybindFrame:OnMouseWheel(delta) __qk.wheel = delta end
    function KeybindFrames_InQuickKeybindMode()
        return QuickKeybindFrame and QuickKeybindFrame:IsShown()
    end
    QuickKeybindTooltip = { Hide = function() end }
    local M = {}
    function M:QuickKeybindButtonOnClick(button, down)
        if KeybindFrames_InQuickKeybindMode() and button ~= "LeftButton" and button ~= "RightButton" then
            QuickKeybindFrame:OnKeyDown(button)
        end
    end
    function M:QuickKeybindButtonOnEnter()
        if KeybindFrames_InQuickKeybindMode() then
            QuickKeybindFrame:SetSelected(self.commandName, self)
            self:QuickKeybindButtonSetTooltip()
            self.QuickKeybindHighlightTexture:SetAlpha(1)
        end
    end
    function M:QuickKeybindButtonOnLeave()
        if KeybindFrames_InQuickKeybindMode() then
            QuickKeybindFrame:SetSelected(nil, nil)
            self.QuickKeybindHighlightTexture:SetAlpha(0.5)
        end
        QuickKeybindTooltip:Hide()
    end
    function M:QuickKeybindButtonSetTooltip() __qk.tooltips = __qk.tooltips + 1 end
    function M:QuickKeybindButtonOnMouseWheel(delta)
        if KeybindFrames_InQuickKeybindMode() then QuickKeybindFrame:OnMouseWheel(delta) end
    end
    function M:UpdateMouseWheelHandler()
        local on = KeybindFrames_InQuickKeybindMode()
        if on and self:GetScript("OnMouseWheel") == nil then
            self:SetScript("OnMouseWheel", self.QuickKeybindButtonOnMouseWheel)
        elseif not on and self:GetScript("OnMouseWheel") == self.QuickKeybindButtonOnMouseWheel then
            self:SetScript("OnMouseWheel", nil)
        end
    end
    function M:QuickKeybindButtonOnShow() self:UpdateMouseWheelHandler() end
    function M:QuickKeybindButtonOnHide() end
    function M:DoModeChange(on) self.QuickKeybindHighlightTexture:SetShown(on) end
    QuickKeybindButtonTemplateMixin = M
end

__callbacks = {}
EventRegistry = {
    RegisterCallback = function(_, event, fn, owner)
        __callbacks[event] = __callbacks[event] or {}
        table.insert(__callbacks[event], { fn = fn, owner = owner })
    end,
}
function __trigger(event, ...)
    for _, cb in ipairs(__callbacks[event] or {}) do cb.fn(cb.owner, ...) end
end
function Mixin(t, ...)
    for i = 1, select("#", ...) do for k, v in pairs((select(i, ...))) do t[k] = v end end
    return t
end
"""


# The real Theme.lua functions the bars' skinning runs through; see MOCK.
THEME_FUNCTIONS = (
    "ApplyNineSlice", "AddSliceTexture", "AddCut2Texture",
    "SnapCut", "CutSizeIcon", "Cut2ButtonSet", "SkinButton", "SkinCutButton",
)

# File-local helpers those functions close over (CutSizeIcon -> SnapForHeight).
THEME_LOCAL_FUNCTIONS = ("SnapForHeight",)


# The numeric Theme.lua constants the bars' slice plumbing reads, in the order
# Theme.lua defines them (SLICE_CUT2_GLOW_MARGIN is derived from the two before it).
THEME_CONSTANTS = (
    "CHROME_CORNERS", "CUT_SIZES",
    "SLICE_MARGIN", "SLICE_GLOW_PAD", "SLICE_GLOW_MARGIN", "SLICE_CUT_MARGIN",
    "SLICE_CUT2_GLOW_PAD", "SLICE_CUT2_GLOW_MARGIN",
)


def _extract_theme_constant(source: str, name: str) -> str:
    """The single-line `Theme.<name> = ...` assignment, trailing comment included
    (Lua ignores it)."""
    match = re.search(rf"^Theme\.{name} = .*$", source, re.M)
    if not match:
        sys.exit(f"Theme.{name} not found in Theme.lua; update THEME_CONSTANTS")
    return match.group(0)


def _extract_theme_function(source: str, name: str) -> str:
    """Source text of the top-level `function Theme.<name>(...)` ... `end`."""
    match = re.search(rf"^function Theme\.{name}\(.*?^end$", source, re.S | re.M)
    if not match:
        sys.exit(f"Theme.{name} not found in Theme.lua; update THEME_FUNCTIONS")
    return match.group(0)


def _extract_theme_local_function(source: str, name: str) -> str:
    """Source text of the top-level `local function <name>(...)` ... `end`."""
    match = re.search(rf"^local function {name}\(.*?^end$", source, re.S | re.M)
    if not match:
        sys.exit(f"local function {name} not found in Theme.lua; update THEME_LOCAL_FUNCTIONS")
    return match.group(0)


def boot(prelude: str = "", extra: tuple = ()) -> "LuaRuntime":
    """`extra`: further addon files loaded after ActionBars/StanceBar/PetActionBar and
    before PLAYER_LOGIN (console-harness.py loads Console.lua this way)."""
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(prelude)
    lua.execute("__install_qk()")
    load = lua.eval("__load")
    theme_src = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")
    defs = lua.table_from({n: _extract_theme_function(theme_src, n) for n in THEME_FUNCTIONS})
    local_defs = [_extract_theme_local_function(theme_src, n) for n in THEME_LOCAL_FUNCTIONS]
    lua.eval("__load_theme_functions")(
        defs, lua.table_from(list(THEME_FUNCTIONS)), lua.table_from(local_defs))
    consts = [_extract_theme_constant(theme_src, n) for n in THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    for name in ("Core/FrameHelpers.lua", "Modules/ActionBars/ActionBars.lua", "Modules/ActionBars/StanceBar.lua", "Modules/Pet/PetActionBar.lua", *extra):
        load(name, (ADDON / name).read_text(encoding="utf-8"))
    lua.execute("__login()")
    return lua


CHECKS = r"""
local T = {}

local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local function allEdges(insets, want, msg)
    for i = 1, 4 do eq(insets[i], want[i], (msg or "inset") .. " side " .. i) end
end

-- The clearing inset every cut button's icon gets, whatever the client's masks do:
-- at 3px the square icon's corner sits on the outer chamfer line (x + y = 6, the
-- chamfer being SLICE_CUT_MARGIN = 6) and hides under the stroke. CreateMaskTexture
-- exists on the 16001 client but does not clip, so no mask is created.
local ICON_INSET = 3

function T.action_cooldown_reaches_icon_edges()
    -- The icon is inset ICON_INSET (3px, see below); the swipe must be exactly as
    -- wide as the icon, not 3px further in as the template leaves it.
    for _, spec in ipairs({ { 1, 1 }, { 2, 7 }, { 6, 12 } }) do
        local b = __button(spec[1], spec[2])
        local icon = __insets(b.icon, b)
        allEdges(icon, { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "icon inset")
        allEdges(__insets(b.cooldown, b), icon, "cooldown inset bar" .. spec[1])
    end
end

function T.action_cooldown_is_square_edgeless_and_blingless()
    local cd = __button(1, 1).cooldown
    -- Square: masks do not clip here, so the icon is square and a chamfer-shaped
    -- swipe would leave an undimmed sliver at its top-left and bottom-right corners.
    eq(cd._swipeTexture, nil, "swipe is square")
    eq(cd._drawEdge, false, "draw edge")
    eq(cd._drawBling, false, "draw bling")
    eq(cd._swipeColor[4], 0.64, "swipe alpha")
end

function T.action_other_cooldowns_reach_the_edge_and_keep_their_own_look()
    -- The template's loss-of-control (3px) and charge (2px) cooldowns would
    -- otherwise still stop short of the edge during a stun or a recharge.
    local b = __button(2, 5)
    allEdges(__insets(b.lossOfControlCooldown, b), { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "loss of control")
    allEdges(__insets(b.chargeCooldown, b), { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "charge")
    -- Loss of control keeps its dark red (not the GCD's black), only shaped.
    local c = b.lossOfControlCooldown._swipeColor
    eq(c[1], 0.17, "loss of control stays red"); eq(c[2], 0); eq(c[3], 0); eq(c[4], 0.64)
    eq(b.lossOfControlCooldown._swipeTexture, nil, "loss of control swipe is square")
    -- The charge cooldown draws no swipe at all: nothing to colour or shape.
    eq(b.chargeCooldown._drawSwipe, false)
    eq(b.chargeCooldown._swipeTexture, nil)
end

function T.action_swipe_stays_square_without_mask_support()
    -- Variant boot: MaskTexture unsupported, so the icon stays square and the
    -- swipe must too (a cut swipe would leave bright icon corners).
    local b = __button(1, 1)
    eq(b.fsIconMask, nil, "icon not masked in this variant")
    eq(b.cooldown._swipeTexture, nil, "swipe stays square")
    eq(b.lossOfControlCooldown._swipeTexture, nil, "loss of control stays square")
    eq(b.cooldown._swipeColor[4], 0.64, "still the standard swipe colour")
    -- The icon keeps the clearing inset, and the swipe still reaches its edges.
    local icon = __insets(b.icon, b)
    allEdges(icon, { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "icon clears the chamfer")
    allEdges(__insets(b.cooldown, b), icon, "still edge to edge")
end

function T.action_cooldown_geometry_survives_updates()
    local b = __button(3, 4)
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    __fire_event("SPELL_UPDATE_COOLDOWN")
    allEdges(__insets(b.cooldown, b), { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "after update")
    eq(b.cooldown._cdObj ~= nil, true, "duration object still applied")
end

function T.action_text_draws_above_the_swipe()
    -- Full-face swipe would otherwise dim the keybind and the count.
    local b = __button(2, 2)
    local cdLevel = b.cooldown._level
    for _, region in ipairs({ b.HotKey, b.Count, b.fsHotkeyPlate }) do
        eq(region._parent ~= b, true, "text region moved off the button")
        eq(region._parent._level > cdLevel, true, "text host above cooldown")
        eq(region._parent._mouse, false, "text host is click-through")
    end
end

local function stanceButton(i) return _G["FSStanceButton" .. i] end
local function petButton(i) return _G["FSPetActionButton" .. i] end

function T.stance_and_pet_hotkeys_draw_above_the_swipe()
    for _, b in ipairs({ stanceButton(1), petButton(2) }) do
        local host = b.HotKey._parent
        eq(host ~= b, true, "hotkey moved off the button")
        eq(host._level > b.cooldown._level, true, "hotkey host above cooldown")
        eq(host._mouse, false, "hotkey host is click-through")
    end
end

local function bareButton()
    local b = CreateFrame("Button", nil, UIParent)
    b.icon = b:CreateTexture(nil, "BACKGROUND")
    b.cooldown = CreateFrame("Cooldown", nil, b)
    b.HotKey = b:CreateFontString(nil, "OVERLAY", "NumberFontNormal")   -- the template XML's font
    return b
end

function T.text_stays_in_blizzards_container_when_it_is_already_above_the_swipe()
    local b = bareButton()
    local container = CreateFrame("Frame", nil, b)
    container:SetFrameLevel(500)
    b.TextOverlayContainer = container
    b.HotKey:SetParent(container)
    local host = FS.FrameHelpers.SeatButtonText(b, b.HotKey)
    eq(host, container, "container is the host")
    eq(b.HotKey:GetParent(), container, "text left where Blizzard put it")
    eq(b.fsTextHost, nil, "no second host built")
end

function T.text_gets_its_own_host_when_the_container_is_below_the_swipe_or_absent()
    local low = bareButton()
    low.TextOverlayContainer = CreateFrame("Frame", nil, low)
    low.TextOverlayContainer:SetFrameLevel(low.cooldown:GetFrameLevel() - 1)
    for _, b in ipairs({ low, bareButton() }) do
        local host = FS.FrameHelpers.SeatButtonText(b, b.HotKey)
        eq(host ~= b.TextOverlayContainer, true, "not the low container")
        eq(b.HotKey:GetParent(), host)
        eq(host:GetFrameLevel() > b.cooldown:GetFrameLevel(), true, "above the swipe")
        eq(host._mouse, false, "click-through")
    end
end

function T.stance_and_pet_cooldowns_are_edgeless_full_face()
    for _, b in ipairs({ stanceButton(1), stanceButton(2), petButton(1), petButton(3) }) do
        allEdges(__insets(b.cooldown, b), { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET }, "cooldown inset")
        eq(b.cooldown._drawEdge, false, "draw edge")
        eq(b.cooldown._drawBling, false, "draw bling")
        -- Their icons are square (masks do not clip), so the swipe is square too.
        eq(b.cooldown._swipeTexture, nil, "square swipe")
    end
end

function T.all_three_bar_types_use_the_cut2_fill_and_outline_with_no_icon_mask()
    local function texturePaths(b)
        local paths = {}
        for _, r in ipairs({ b:GetRegions() }) do
            if r._texture then paths[r._texture] = true end
        end
        return paths
    end
    for _, b in ipairs({ __button(1, 1), stanceButton(1), petButton(1) }) do
        local paths = texturePaths(b)
        -- Plate fill: the cut2 gradient plate, and NOT the rounded one.
        eq(paths["slice_cut2_button"], true, "cut2 fill " .. tostring(b:GetName()))
        eq(paths["slice_button"], nil, "no rounded fill")
        -- Border: the cut2 outline, reached through SkinCutButton, not SkinButton.
        eq(b.fsSkin.border.ring._texture, "slice_cut2_outline", "cut2 outline")
        eq(b.fsSkin.glow._texture, "slice_cut2_glow", "cut2 glow")
        -- The real SkinCutButton's opts reached the slice plumbing: the ring is
        -- sliced at the chamfer margin and the glow at the cut2 glow margin.
        eq(b.fsSkin.border.ring._slice[1], 6, "outline slice margin")
        eq(b.fsSkin.glow._slice[1], 10, "glow slice margin")
        for _, r in ipairs({ b:GetRegions() }) do
            if r._texture == "slice_cut2_button" then eq(r._slice[1], 6, "plate slice margin") end
        end
        -- No icon mask (it would be a dead region); swipe: square.
        eq(b.fsIconMask, nil, "no icon mask")
        eq(b.cooldown._swipeTexture, nil, "square swipe")
    end
end

function T.cut_icon_is_inset_only_when_mask_apis_exist_but_do_not_clip()
    -- Variant boot: AddMaskTexture exists and records the mask, as on the 16001
    -- client, but nothing clips. So no mask is attached (it would be a dead region
    -- on every button); the 3px inset is what keeps the square icon corners inside
    -- the chamfer.
    for _, b in ipairs({ __button(1, 1), stanceButton(1), petButton(1) }) do
        local name = tostring(b:GetName())
        eq(b.fsIconMask, nil, "no mask attached " .. name)
        eq(b.icon._maskedBy, nil, "icon takes no mask " .. name)
        for _, r in ipairs({ b:GetRegions() }) do
            eq(r._kind ~= "MaskTexture", true, "no MaskTexture region " .. name)
        end
        allEdges(__insets(b.icon, b), { ICON_INSET, ICON_INSET, ICON_INSET, ICON_INSET },
            "icon inset " .. name)
    end
end

function T.pet_washes_are_cut2_fill_nine_slices_not_masked_flat_squares()
    -- The checked and hover washes used to be flat squares that leaned on the icon
    -- mask to lose the chamfered corners. The mask does not clip on this client, so
    -- they are the baked cut2 fill, nine-sliced at the chamfer, ADD blended, sized
    -- to the button, like the main bar's hover wash.
    for i = 1, 3 do
        local b = petButton(i)
        local checked = b._checkedTexture
        eq(checked ~= nil, true, "checked texture set")
        eq(b.fsHighlight ~= nil, true, "hover wash built")
        for what, wash in pairs({ checked = checked, hover = b.fsHighlight }) do
            eq(wash._texture, "slice_cut2_fill", what .. " wash texture")
            eq(wash._slice ~= nil and wash._slice[1], 6, what .. " wash slice margin")
            eq(wash._blend, "ADD", what .. " wash blend")
            eq(wash._maskedBy, nil, what .. " wash does not lean on the dead mask")
            allEdges(__insets(wash, b), { 0, 0, 0, 0 }, what .. " wash covers the button")
        end
    end
end

-- ---- Queued / active state ----------------------------------------------
-- Heroic Strike (next swing), Attack (toggled on) and auto-repeat spells are "checked" on
-- Blizzard's button via IsCurrentAction / IsAutoRepeatAction; ours drew nothing at all.
local function pairShown(wash, glow)
    return wash ~= nil and glow ~= nil and wash:IsShown() and glow:IsShown()
end
-- Lit by either flag: IsCurrentAction drives one wash+glow pair, IsAutoRepeatAction the other.
local function queued(b)
    return pairShown(b.fsQueuedWash, b.fsQueuedGlow) or pairShown(b.fsRepeatWash, b.fsRepeatGlow)
end

function T.queued_state_follows_is_current_action_and_clears()
    local b, other = __button(2, 3), __button(2, 4)
    eq(b.fsQueuedWash ~= nil, true, "queued wash built")
    eq(queued(b), false, "idle button shows nothing")
    __current[b.action] = true
    __fire_event("ACTIONBAR_UPDATE_STATE")
    eq(queued(b), true, "queued spell lights its button")
    eq(queued(other), false, "a neighbour stays dark")
    __current[b.action] = nil
    __fire_event("ACTIONBAR_UPDATE_STATE")
    eq(queued(b), false, "state clears when the spell fires")
end

function T.queued_state_follows_auto_repeat()
    local b = __button(1, 1)
    __autorepeat[b.action] = true
    __fire_event("START_AUTOREPEAT_SPELL")
    eq(queued(b), true, "auto shot / wand lights its button")
    __autorepeat[b.action] = nil
    __fire_event("STOP_AUTOREPEAT_SPELL")
    eq(queued(b), false, "stop clears it")
end

function T.queued_state_refreshes_on_the_state_only_events()
    local b = __button(3, 5)
    for _, event in ipairs({ "CURRENT_SPELL_CAST_CHANGED", "PLAYER_ENTER_COMBAT", "PLAYER_LEAVE_COMBAT" }) do
        __current[b.action] = true
        __fire_event(event)
        eq(queued(b), true, event .. " refreshes the state")
        __current[b.action] = nil
        __fire_event(event)
        eq(queued(b), false, event .. " clears the state")
    end
end

function T.queued_state_wash_and_glow_are_cut2_shaped_and_cyan()
    local b = __button(1, 2)
    local wash, glow = b.fsQueuedWash, b.fsQueuedGlow
    eq(wash._texture, "slice_cut2_fill", "wash texture")
    eq(wash._blend, "ADD", "wash blend")
    eq(wash._vertex[1] < wash._vertex[3], true, "wash is cyan (blue above red)")
    allEdges(__insets(wash, b), { 0, 0, 0, 0 }, "wash covers the button")
    eq(glow._texture, "slice_cut2_glow", "glow texture")
    eq(glow._blend, "ADD", "glow blend")
end

function T.queued_state_never_leaves_the_checkbutton_checked()
    local b = __button(1, 1)
    b:SetChecked(true)   -- what a click does to a CheckButton
    __fire_event("ACTIONBAR_UPDATE_STATE")
    eq(b:GetChecked(), false, "click toggle does not linger")
end

function T.queued_state_in_combat_goes_through_set_alpha_from_boolean()
    local b = __button(1, 1)
    __current[b.action] = __SECRET
    __fire_event("CURRENT_SPELL_CAST_CHANGED")   -- a compare or arithmetic on it would throw
    for _, tex in ipairs({ b.fsQueuedWash, b.fsQueuedGlow }) do
        eq(tex._fromBool ~= nil and rawequal(tex._fromBool.flag, __SECRET), true, "secret reaches SetAlphaFromBoolean")
        eq(tex._fromBool.t, 1, "visible when true")
        eq(tex._fromBool.f, 0, "invisible when false")
        eq(tex:IsShown(), true, "shown, alpha decides")
    end
    __current[b.action] = false
    __fire_event("CURRENT_SPELL_CAST_CHANGED")
    eq(queued(b), false, "back out of combat the plain path hides it again")
    eq(b.fsQueuedWash._alpha, 1, "alpha restored for the plain path")
end

-- L1: a secret IsCurrentAction used to swallow IsAutoRepeatAction, so Auto Shot / a wand
-- could stay unlit in combat. Each flag now owns its pair; ADD blending ORs them on screen.
function T.queued_state_secret_current_does_not_swallow_a_plain_auto_repeat()
    local b = __button(1, 1)
    __current[b.action] = __SECRET
    __autorepeat[b.action] = true
    __fire_event("START_AUTOREPEAT_SPELL")
    eq(pairShown(b.fsRepeatWash, b.fsRepeatGlow), true, "plain auto-repeat still lights its pair")
    eq(b.fsRepeatWash._alpha, 1, "at full alpha")
    eq(b.fsQueuedWash._fromBool ~= nil and rawequal(b.fsQueuedWash._fromBool.flag, __SECRET), true,
        "the secret current flag still reaches its own pair")
end

function T.queued_state_each_secret_flag_drives_only_its_own_pair()
    local b = __button(1, 1)
    __current[b.action] = __SECRET
    __autorepeat[b.action] = __SECRET
    __fire_event("CURRENT_SPELL_CAST_CHANGED")
    for _, tex in ipairs({ b.fsQueuedWash, b.fsQueuedGlow, b.fsRepeatWash, b.fsRepeatGlow }) do
        eq(tex._fromBool ~= nil and rawequal(tex._fromBool.flag, __SECRET), true, "secret routed")
        eq(tex._fromBool.t, 1, "visible when true")
        eq(tex._fromBool.f, 0, "invisible when false")
    end
    -- Out of combat both are plain again: the secret alpha must not linger.
    __current[b.action], __autorepeat[b.action] = nil, nil
    __fire_event("CURRENT_SPELL_CAST_CHANGED")
    eq(queued(b), false, "both pairs hide")
    eq(b.fsRepeatWash._alpha, 1, "alpha restored")
end

-- L2: a click flips the CheckButton to checked; the template's CheckedTexture must not show.
function T.queued_state_click_flip_is_undone_after_the_click()
    local b = __button(1, 1)
    b:SetChecked(true)   -- the engine's own toggle on a click
    b.Fire(b, "PostClick", "LeftButton")
    eq(b:GetChecked(), false, "PostClick re-pins the check")
    local checked = b:GetCheckedTexture()
    eq(checked ~= nil and checked._alpha, 0, "template checked art stays blank")
end

-- Bar 6 (MultiBar5) lived on slots 73-84, which is action page 7: the BONUS bar, exactly
-- where the paged main bar goes in Warrior Battle Stance, Druid cat, Rogue stealth. Both bars
-- then showed the same twelve actions and a drag onto one mirrored on the other. Blizzard puts
-- MultiBar5 on MULTIBAR_5_ACTIONBAR_PAGE (13, slots 145-156).
function T.bar6_never_shares_slots_with_the_main_bar_on_any_page()
    local slots = {}
    for i = 1, 12 do slots[#slots + 1] = __button(6, i).action end
    for page = 1, 10 do   -- 1-6 paged, 7-10 bonus / stance
        local first = (page - 1) * 12 + 1
        for _, a in ipairs(slots) do
            eq(a >= first and a < first + 12, false,
                ("bar 6 slot %d sits on action page %d"):format(a, page))
        end
    end
    eq(slots[1], 145, "MULTIBAR_5_ACTIONBAR_PAGE 13 fallback, (13 - 1) * 12 + 1")
    eq(slots[12], 156, "twelve consecutive slots")
end

function T.bar6_first_slot_follows_the_clients_multibar5_page()
    eq(__button(6, 1).action, 169, "page 15 -> slot 169")
    eq(__button(6, 12).action, 180, "...through 180")
end

-- ---- Key-press feedback -------------------------------------------------
-- A bound key runs the binding body, which calls ActionButtonDown / MultiActionButtonDown on
-- Blizzard's own hidden twin of the slot; our button never hears it and drew no press.
function T.keybind_press_pushes_our_button_and_release_clears_it()
    local b = __button(1, 3)
    eq(b:GetButtonState(), "NORMAL", "idle")
    ActionButtonDown(3)
    eq(b:GetButtonState(), "PUSHED", "ACTIONBUTTON3 down pushes bar 1 button 3")
    eq(__button(1, 4):GetButtonState(), "NORMAL", "neighbour untouched")
    ActionButtonUp(3)
    eq(b:GetButtonState(), "NORMAL", "release clears it")
end

function T.keybind_press_maps_every_blizzard_multibar_to_its_bar()
    -- Blizzard's MultiBarLeft is MULTIACTIONBAR4, MultiBarRight is 3 (see BARS): the map
    -- follows the binding names, not the order the bars are drawn in.
    for blizz, bar in pairs({ MultiBarBottomLeft = 2, MultiBarBottomRight = 3, MultiBarRight = 4,
                              MultiBarLeft = 5, MultiBar5 = 6 }) do
        local b = __button(bar, 5)
        MultiActionButtonDown(blizz, 5)
        eq(b:GetButtonState(), "PUSHED", blizz .. " down")
        MultiActionButtonUp(blizz, 5)
        eq(b:GetButtonState(), "NORMAL", blizz .. " up")
    end
end

-- A release that never arrives (alt-tab, binding changed mid-press) must not leave a button lit.
function T.keybind_press_is_released_when_the_release_never_arrives()
    for _, event in ipairs({ "PLAYER_REGEN_ENABLED", "UPDATE_BINDINGS" }) do
        local b = __button(1, 3)
        ActionButtonDown(3)
        eq(b:GetButtonState(), "PUSHED", "held")
        __fire_event(event)
        eq(b:GetButtonState(), "NORMAL", event .. " re-pins it")
    end
    local m = __button(4, 2)
    MultiActionButtonDown("MultiBarRight", 2)
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(m:GetButtonState(), "NORMAL", "multibar buttons too")
end

-- Pulling a mob must not clear the key that opened combat (and PLAYER_REGEN_DISABLED would run a
-- full UpdateAll of all 72 buttons for nothing): it is not a release trigger.
function T.keybind_press_survives_the_start_of_combat()
    local b = __button(1, 3)
    ActionButtonDown(3)
    __fire_event("PLAYER_REGEN_DISABLED")
    eq(b:GetButtonState(), "PUSHED", "a held key still reads held when combat starts")
end

-- A release is only assumed lost for a button the mouse is NOT on: a held mouse press there is real.
function T.keybind_release_sweep_leaves_a_hovered_button_alone()
    local b, other = __button(1, 3), __button(1, 4)
    ActionButtonDown(3); ActionButtonDown(4)
    b._mouseOver = true
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(b:GetButtonState(), "PUSHED", "hovered button keeps its press")
    eq(other:GetButtonState(), "NORMAL", "the other one is re-pinned")
    b._mouseOver = false
    __fire_event("UPDATE_BINDINGS")
    eq(b:GetButtonState(), "NORMAL", "released once the mouse is off it")
end

-- StyleButton's PostClick re-pin is installed exactly once per button, however often the bars refresh.
function T.postclick_repin_is_installed_once_per_button()
    for bar = 1, 6 do
        for i = 1, 12 do
            local b = __button(bar, i)
            eq(#(b._hooks.PostClick or {}), 1, ("bar %d button %d PostClick hooks"):format(bar, i))
        end
    end
    __fire_event("PLAYER_ENTERING_WORLD")
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(#(__button(1, 1)._hooks.PostClick or {}), 1, "still one after refresh events")
end

-- Blizzard's ActionButtonDown returns before pushing anything during a pet battle.
function T.keybind_press_is_skipped_during_a_pet_battle()
    local b = __button(1, 3)
    __petBattle = true
    ActionButtonDown(3)
    eq(b:GetButtonState(), "NORMAL", "not pushed in a pet battle")
    __petBattle = false
    ActionButtonDown(3)
    eq(b:GetButtonState(), "PUSHED", "pushed again outside one")
    __petBattle = true
    ActionButtonUp(3)
    eq(b:GetButtonState(), "NORMAL", "a release is always honoured")
end

function T.keybind_press_with_no_matching_button_does_not_throw()
    MultiActionButtonDown("MultiBar6", 5)
    MultiActionButtonUp("MultiBar6", 5)
    MultiActionButtonDown(nil, nil)
    ActionButtonDown(99)
    ActionButtonUp(99)
    ActionButtonDown(nil)
end

function T.keybind_press_look_is_a_cut2_wash_above_the_icon()
    local b = __button(2, 2)
    local pushed = b:GetPushedTexture()
    eq(pushed._texture, "slice_cut2_fill", "pressed wash texture")
    eq(pushed._blend, "ADD", "pressed wash blend")
    eq(pushed._alpha, 1, "template's blanked alpha is restored")
    eq(pushed._layer, "OVERLAY", "drawn above the icon")
    allEdges(__insets(pushed, b), { 0, 0, 0, 0 }, "pressed wash covers the button")
end

-- The GCD swipe: the duration object comes from the action slot with the GCD INCLUDED (the
-- API's ignoreGCD argument is left at its default false) and goes straight to the cooldown.
function T.gcd_swipe_is_asked_for_with_the_gcd_included_and_applied()
    local b = __button(1, 1)
    local seen   -- recorded by the variant's API stand-in, installed before the addon loads
    __gcdSeen[b.action] = nil
    b.cooldown._cdObj = nil
    __fire_event("SPELL_UPDATE_COOLDOWN")
    seen = __gcdSeen[b.action]
    eq(seen ~= nil, true, "cooldown duration requested for the slot on SPELL_UPDATE_COOLDOWN")
    eq(seen.ignore == nil or seen.ignore == false, true, "GCD is not ignored")
    eq(b.cooldown._cdObj ~= nil and b.cooldown._cdObj.gcd, true, "object reaches the cooldown frame")
    eq(b.cooldown:IsShown(), true, "cooldown frame shown")
    b.cooldown._cdObj = nil
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.cooldown._cdObj ~= nil, true, "ACTIONBAR_UPDATE_COOLDOWN refreshes it too")
end

-- The usable/state events can fire many times a second while idle, and each one used to
-- rebuild every button's hotkey strings and cooldown duration object. Only the events that own that
-- data may pay for it, and an empty slot never asks for a duration object at all.
function T.idle_usable_and_state_events_skip_hotkeys_and_cooldown_objects()
    __cdAsked, __keyAsked = 0, 0
    for _, ev in ipairs({ "ACTIONBAR_UPDATE_USABLE", "SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_STATE",
                          "PLAYER_TARGET_CHANGED" }) do
        __fire_event(ev)
    end
    eq(__cdAsked, 0, "usable/state events request no cooldown duration objects")
    eq(__keyAsked, 0, "usable/state events resolve no hotkeys")
    __fire_event("SPELL_UPDATE_COOLDOWN")
    eq(__cdAsked > 0, true, "a cooldown event still refreshes the swipe")
    eq(__keyAsked, 0, "a cooldown event resolves no hotkeys")
    __fire_event("UPDATE_BINDINGS")
    eq(__keyAsked > 0, true, "a bindings change still refreshes the hotkeys")
end

-- The cheaper path must still do its job: a usable change reaches the icon tint.
function T.usable_event_still_retints_the_icon()
    local icon = __button(1, 1).icon
    __fire_event("ACTIONBAR_UPDATE_USABLE")
    eq(icon._vertex[1], 1, "usable slot is untinted")
    IsUsableAction = function() return false, false end
    __fire_event("ACTIONBAR_UPDATE_USABLE")
    eq(icon._vertex[1], 0.4, "unusable slot is greyed by the usable event")
    IsUsableAction = function() return true, false end
    IsActionInRange = function() return false end
    __fire_event("PLAYER_TARGET_CHANGED")
    eq(icon._vertex[1], 0.8, "out of range is reddened by a target change")
end

function T.cooldown_refresh_skips_empty_slots()
    local b = __button(1, 1)
    local emptySlot = b.action
    __cdAsked = 0
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    local all = __cdAsked
    eq(all > 1, true, "every filled slot asks for its duration object")
    HasAction = function(slot) return slot ~= emptySlot end
    b.cooldown._cdObj = "stale"
    __cdAsked = 0
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(__cdAsked, all - 1, "the empty slot asks for no duration object")
    eq(b.cooldown._cdObj, nil, "the empty slot's swipe was cleared")
    eq(__button(1, 2).cooldown._cdObj ~= nil, true, "a filled slot still gets its duration object")
end

function T.slot_change_to_an_empty_slot_clears_its_cooldown()
    local b = __button(1, 1)
    __fire_event("ACTIONBAR_UPDATE_COOLDOWN")
    eq(b.cooldown._cdObj ~= nil, true, "swipe shown while the slot is filled")
    local slot = b.action
    HasAction = function(s) return s ~= slot end
    __fire_event("ACTIONBAR_SLOT_CHANGED", slot)
    eq(b.cooldown._cdObj, nil, "slot change to empty cleared the swipe")
end

-- ---- the paged main bar rides MainActionBar's live page -------------------------------------
-- Live test 2026-10-09: stealthed, out of combat, GetActionBarPage() = 1 while MainActionBar's
-- "actionpage" attribute read 7. A button with an ID, no "action" attribute and
-- useparent-actionpage resolves a click to the LIVE page through SecureButton_GetModifiedAttribute
-- (follows frame.bar), including after stealth breaks into combat, with no write from us.
local function liveSlot(page, i) return (page - 1) * 12 + i end

function T.paged_buttons_carry_an_id_and_follow_mainactionbars_page_by_attribute()
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b:GetID(), i, "id " .. i)
        eq(b:GetAttribute("action"), nil, "no fixed action attribute " .. i)
        eq(b:GetAttribute("useparent-actionpage"), true, "follows the parent's page " .. i)
        eq(b.bar, MainActionBar, "bar is MainActionBar " .. i)
        eq(b:GetAttribute("type"), "action", "still an action button " .. i)
        eq(b.action, liveSlot(1, i), "visual slot " .. i)
        -- ActionButton.lua:1612 reads this attribute before self.bar:GetSpellFlyoutDirection(),
        -- so the popup direction does not depend on where Blizzard's hidden host sits.
        eq(b:GetAttribute("flyoutDirection"), "UP", "flyout direction ignores the host " .. i)
    end
    eq(__blocked, 0)
end

function T.fixed_bars_keep_their_attribute_slots()
    for bar = 2, 6 do
        for i = 1, 12 do
            local b = __button(bar, i)
            eq(b:GetID(), 0, ("bar %d id"):format(bar))
            eq(b:GetAttribute("action"), b.action, ("bar %d attribute is its slot"):format(bar))
            eq(b:GetAttribute("useparent-actionpage"), nil, ("bar %d has no page parent"):format(bar))
            eq(b.bar, nil, ("bar %d has no bar field"):format(bar))
        end
    end
    -- and a page change never touches them, in or out of combat
    local before = __button(3, 4).action
    MainActionBar:SetAttribute("actionpage", 7)
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(__button(3, 4).action, before)
    eq(__button(3, 4):GetAttribute("action"), before)
end

function T.paged_bonus_page_change_in_combat_writes_nothing_and_the_visuals_follow()
    local seen = {}
    function GetActionTexture(slot) return "tex" .. slot end
    function GameTooltip:SetAction(slot) seen[#seen + 1] = slot end
    __combat = true
    __attrWrites = 0
    for n, event in ipairs({ "UPDATE_BONUS_ACTIONBAR", "ACTIONBAR_PAGE_CHANGED", "UPDATE_SHAPESHIFT_FORM",
        "UPDATE_VEHICLE_ACTIONBAR", "UPDATE_OVERRIDE_ACTIONBAR" }) do
        local page = 6 + n          -- a different page each time
        MainActionBar:SetAttribute("actionpage", page)
        __fire_event(event)
        for _, i in ipairs({ 1, 6, 12 }) do
            local b = __button(1, i)
            eq(b.action, liveSlot(page, i), event .. " slot " .. i)
            eq(b.icon._texture, "tex" .. liveSlot(page, i), event .. " icon " .. i)
        end
    end
    eq(__attrWrites, 0, "no SetAttribute on any secure button in combat")
    eq(__blocked, 0, "nothing was refused")
    -- the same slot feeds the tooltip
    __button(1, 3).Fire(__button(1, 3), "OnEnter")
    eq(seen[#seen], liveSlot(11, 3), "tooltip reads the live slot")
    -- and combat ending changes neither the slots nor the attribute count
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__button(1, 1).action, liveSlot(11, 1), "held after combat")
    eq(__attrWrites, 0, "regen writes nothing either")
end

function T.paged_page_is_read_again_on_the_next_frame_without_stacking()
    function GetActionTexture(slot) return "tex" .. slot end
    -- Blizzard may write MainActionBar's attribute after our event handler ran in the same frame.
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    __fire_event("ACTIONBAR_PAGE_CHANGED")
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(#__timers, 1, "one pending re-read, not one per event")
    MainActionBar:SetAttribute("actionpage", 7)     -- the controller's late write
    eq(__button(1, 2).action, liveSlot(1, 2), "not yet seen")
    __flushTimers()
    eq(__button(1, 2).action, liveSlot(7, 2), "caught on the next frame")
    eq(__button(1, 2).icon._texture, "tex" .. liveSlot(7, 2), "repainted from the new slot")
    eq(#__timers, 0)
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(#__timers, 1, "a later event can queue again")
end

function T.paged_next_frame_reread_in_combat_writes_nothing()
    __combat = true
    __attrWrites = 0
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    MainActionBar:SetAttribute("actionpage", 8)
    __flushTimers()
    eq(__button(1, 5).action, liveSlot(8, 5))
    eq(__attrWrites, 0)
end

function T.paged_click_resolves_to_the_live_page_in_combat()
    -- __calcAction is SecureActionButtonMixin:CalculateAction (SecureTemplates.lua:670-686) over
    -- SecureButton_GetModifiedAttribute's useparent-<name> / frame.bar walk.
    __combat = true
    for _, page in ipairs({ 1, 7, 9, 12 }) do
        MainActionBar:SetAttribute("actionpage", page)
        __fire_event("UPDATE_BONUS_ACTIONBAR")
        for i = 1, 12 do
            local b = __button(1, i)
            eq(__calcAction(b), liveSlot(page, i), ("click page %d slot %d"):format(page, i))
            eq(__calcAction(b), b.action, "what is drawn is what the click fires")
        end
    end
    -- a fixed bar still resolves from its attribute
    eq(__calcAction(__button(3, 4)), __button(3, 4).action)
    -- and with the attribute path gone no stale slot can be fired from the old page
    eq(__button(1, 1):GetAttribute("action"), nil)
end

function T.paged_page_falls_back_to_the_clients_page_like_calculateaction_when_the_attribute_is_unset()
    -- MainActionBar exists but Blizzard has not written "actionpage": CalculateAction uses
    -- C_ActionBar.GetActionBarPage() (bonus and the other special pages are not consulted), so the
    -- visual has to as well or a click fires a different slot than the one drawn.
    eq(MainActionBar:GetAttribute("actionpage"), nil, "fixture: no attribute")
    function HasBonusActionBar() return true end
    function GetBonusBarIndex() return 7 end
    C_ActionBar.GetActionBarPage = function() return 3 end
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(__button(1, 1).action, liveSlot(3, 1), "fallback is the client's page")
    eq(__calcAction(__button(1, 1)), __button(1, 1).action, "click agrees")
end

function T.skinned_vehicle_or_override_bar_moves_the_click_host_to_overrideactionbar()
    -- Skinned vehicle / override: the controller sets OverrideActionBar's own "actionpage" and the
    -- OVERRIDE state; MainActionBar keeps its stale page.
    MainActionBar:SetAttribute("actionpage", 1)
    OverrideActionBar:SetAttribute("actionpage", 12)
    __barState = LE_ACTIONBAR_STATE_OVERRIDE
    __attrWrites = 0
    __fire_event("UPDATE_VEHICLE_ACTIONBAR")
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b.bar, OverrideActionBar, "click host " .. i)
        eq(b.action, liveSlot(12, i), "visual " .. i)
        eq(__calcAction(b), b.action, "click agrees " .. i)
    end
    eq(__button(1, 1):GetID(), 1, "id kept")
    eq(__attrWrites, 0, "bar and ids are not rewritten, only the bar field")
    -- a page change on the override bar is followed
    OverrideActionBar:SetAttribute("actionpage", 14)
    __fire_event("UPDATE_OVERRIDE_ACTIONBAR")
    eq(__button(1, 2).action, liveSlot(14, 2))
    -- and leaving it goes back to MainActionBar's page
    __barState = LE_ACTIONBAR_STATE_MAIN
    __fire_event("UPDATE_OVERRIDE_ACTIONBAR")
    eq(__button(1, 2).bar, MainActionBar)
    eq(__button(1, 2).action, liveSlot(1, 2))
    eq(__calcAction(__button(1, 2)), __button(1, 2).action)
end

function T.skinned_override_entered_in_combat_swaps_the_click_host_at_once()
    -- `.bar` is a plain Lua field, not an attribute, so moving it is legal in combat (live test
    -- 2026-10-09: an insecure write of it was honoured by the combat click). The visual and the
    -- click follow the override bar's page immediately, with no attribute or ID write.
    MainActionBar:SetAttribute("actionpage", 1)
    __combat = true
    __attrWrites = 0
    OverrideActionBar:SetAttribute("actionpage", 12)
    __barState = LE_ACTIONBAR_STATE_OVERRIDE
    __fire_event("UPDATE_VEHICLE_ACTIONBAR")
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b.bar, OverrideActionBar, "swapped in combat " .. i)
        eq(b.action, liveSlot(12, i), "draws the override page " .. i)
        eq(__calcAction(b), b.action, "click agrees " .. i)
        eq(b:GetID(), i, "id untouched " .. i)
    end
    eq(__attrWrites, 0, "no SetAttribute or SetID in combat")
    eq(__blocked, 0)
    -- a late re-read changes nothing, and regen has nothing left to replay
    __flushTimers()
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b.bar, OverrideActionBar, "still the override host after regen " .. i)
        eq(b.action, liveSlot(12, i), "visual after regen " .. i)
        eq(__calcAction(b), b.action, "click agrees after regen " .. i)
    end
    eq(__attrWrites, 0, "regen writes nothing either")
end

function T.skinned_override_left_in_combat_swaps_the_click_host_back_at_once()
    MainActionBar:SetAttribute("actionpage", 1)
    OverrideActionBar:SetAttribute("actionpage", 12)
    __barState = LE_ACTIONBAR_STATE_OVERRIDE
    __fire_event("UPDATE_VEHICLE_ACTIONBAR")
    eq(__button(1, 1).bar, OverrideActionBar, "fixture: on the override bar")
    __combat = true
    __attrWrites = 0
    __barState = LE_ACTIONBAR_STATE_MAIN
    __fire_event("UPDATE_OVERRIDE_ACTIONBAR")
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b.bar, MainActionBar, "back on the main bar in combat " .. i)
        eq(b.action, liveSlot(1, i), "draws MainActionBar's page " .. i)
        eq(__calcAction(b), b.action, "click agrees " .. i)
        eq(b:GetID(), i, "id untouched " .. i)
    end
    eq(__attrWrites, 0, "no SetAttribute or SetID in combat")
    eq(__blocked, 0)
end

function T.entering_world_reads_the_live_page()
    -- Blizzard first writes the attribute at PLAYER_ENTERING_WORLD; Apply runs at PLAYER_LOGIN.
    MainActionBar:SetAttribute("actionpage", 7)
    __fire_event("PLAYER_ENTERING_WORLD")
    eq(__button(1, 1).action, liveSlot(7, 1))
    eq(__calcAction(__button(1, 1)), __button(1, 1).action)
end

function T.paged_slot_change_refreshes_the_flyout_out_of_combat_and_at_regen()
    -- The page no longer flips through SetAttribute("action"), so the stock OnAttributeChanged
    -- UpdateFlyout does not run; we ask for it, outside combat only.
    local function flyouts(bar, i) return __button(bar, i)._flyouts or 0 end
    local before = flyouts(1, 3)
    MainActionBar:SetAttribute("actionpage", 7)
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(flyouts(1, 3), before + 1, "paged button refreshed")
    eq(flyouts(3, 3), 0, "fixed bar untouched")
    __flushTimers()
    eq(flyouts(1, 3), before + 1, "an unchanged re-read does not refresh again")
    __combat = true
    MainActionBar:SetAttribute("actionpage", 8)
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(__button(1, 3).action, liveSlot(8, 3))
    eq(flyouts(1, 3), before + 1, "queued, not run, in combat")
    eq(__flyoutInCombat, 0)
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(flyouts(1, 3), before + 2, "refreshed at regen")
    eq(flyouts(1, 12), before + 2, "every paged button")
end

function T.paged_buttons_keep_the_attribute_path_when_mainactionbar_is_missing()
    eq(MainActionBar, nil, "fixture: no MainActionBar")
    for i = 1, 12 do
        local b = __button(1, i)
        eq(b:GetID(), 0, "no id")
        eq(b:GetAttribute("useparent-actionpage"), nil)
        eq(b.bar, nil)
        eq(b:GetAttribute("action"), liveSlot(1, i), "fixed attribute as before")
    end
    function HasBonusActionBar() return true end
    function GetBonusBarIndex() return 7 end
    -- out of combat the attribute is re-pointed
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(__button(1, 4):GetAttribute("action"), liveSlot(7, 4))
    eq(__button(1, 4).action, liveSlot(7, 4))
    -- in combat it is deferred, and caught up when combat ends
    function GetBonusBarIndex() return 8 end
    __combat = true
    __fire_event("UPDATE_BONUS_ACTIONBAR")
    eq(__blocked, 0, "no refused write")
    eq(__button(1, 4):GetAttribute("action"), liveSlot(7, 4), "held through the fight")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__button(1, 4):GetAttribute("action"), liveSlot(8, 4), "caught up at regen")
    eq(__button(1, 4).action, liveSlot(8, 4))
end

-- ---- Quick Keybind ------------------------------------------------------
local function qkShow() QuickKeybindFrame:Show() end
local function qkHide() QuickKeybindFrame:Hide() end
local function fire(frame, script, ...) frame.Fire(frame, script, ...) end

function T.quickkeybind_command_names_match_the_bindings()
    eq(__button(1, 1).commandName, "ACTIONBUTTON1")
    eq(__button(2, 3).commandName, "MULTIACTIONBAR1BUTTON3")
    eq(__button(4, 12).commandName, "MULTIACTIONBAR3BUTTON12")
    eq(__button(6, 12).commandName, "MULTIACTIONBAR5BUTTON12")
    eq(stanceButton(2).commandName, "SHAPESHIFTBUTTON2")
    eq(petButton(3).commandName, "BONUSACTIONBUTTON3")
end

function T.quickkeybind_hover_selects_our_button()
    local b = __button(2, 3)
    fire(b, "OnEnter")
    eq(__qk.selected, nil, "outside quick keybind mode hover must not select")
    qkShow()
    for _, btn in ipairs({ b, stanceButton(1), petButton(2) }) do
        eq(btn.commandName ~= nil, true, "has a command name")
        fire(btn, "OnEnter")
        eq(__qk.selected, btn.commandName, "selected command")
        eq(QuickKeybindFrame.mouseOverButton, btn, "mouse-over button")
        fire(btn, "OnLeave")
        eq(__qk.selected, nil, "cleared on leave")
    end
end

function T.quickkeybind_mouse_button_4_reaches_the_binder()
    -- Parker: binding a custom button to mouse button 4 "wouldn't take".
    qkShow()
    for _, btn in ipairs({ __button(2, 3), stanceButton(1), petButton(2) }) do
        wipe(__qk.keys)
        fire(btn, "OnClick", "Button4", false)
        fire(btn, "OnClick", "Button5", false)
        eq(#__qk.keys, 2, "two mouse buttons forwarded")
        eq(__qk.keys[1], "Button4")
        -- AnyDown is registered too, so each click arrives twice (down, up):
        -- only the release may count, or one click would bind twice.
        fire(btn, "OnClick", "Button4", true)
        eq(#__qk.keys, 2, "key-down half of a click ignored")
        -- Left and right belong to casting / dragging, never to binding.
        fire(btn, "OnClick", "LeftButton", false)
        fire(btn, "OnClick", "RightButton", false)
        eq(#__qk.keys, 2, "left/right not forwarded")
    end
    qkHide()
    wipe(__qk.keys)
    fire(__button(2, 3), "OnClick", "Button4", false)
    eq(#__qk.keys, 0, "nothing forwarded outside quick keybind mode")
end

local function overlayOf(b) return b.fsQuickKeybindOverlay end

function T.quickkeybind_mode_stops_clicks_with_an_overlay_and_leaves_attributes_alone()
    -- A mouse-enabled insecure child over the button takes the click, so the
    -- secure `type` never has to change (it cannot be written in combat).
    local all = { __button(1, 1), __button(2, 3), stanceButton(1), petButton(2) }
    local types = {}
    for i, b in ipairs(all) do types[i] = b:GetAttribute("type") end
    eq(types[1], "action"); eq(types[3], "spell"); eq(types[4], "pet")
    for i, b in ipairs(all) do eq(overlayOf(b):IsShown(), false, "no overlay outside the mode " .. i) end
    qkShow()
    for i, b in ipairs(all) do
        local o = overlayOf(b)
        eq(o:IsShown(), true, "overlay up in the mode " .. i)
        eq(o._mouse, true, "overlay takes the mouse")
        allEdges(__insets(o, b), { 0, 0, 0, 0 }, "overlay covers the button")
        eq(o._parent, b)
        for _, child in ipairs(b._regions) do
            if child ~= o and child._mouse then eq(o._level > child._level, true, "above mouse-enabled siblings") end
        end
        eq(o._level > b.cooldown._level, true, "above the swipe")
        eq(b:GetAttribute("type"), types[i], "type untouched while open " .. i)
    end
    qkHide()
    for i, b in ipairs(all) do
        eq(overlayOf(b):IsShown(), false, "overlay gone after close " .. i)
        eq(b:GetAttribute("type"), types[i], "type untouched after close " .. i)
    end
end

function T.quickkeybind_overlay_forwards_hover_click_and_wheel()
    -- With the overlay up it, not the button, is what the mouse sees.
    qkShow()
    for _, btn in ipairs({ __button(2, 3), stanceButton(1), petButton(2) }) do
        local o = overlayOf(btn)
        fire(o, "OnEnter")
        eq(__qk.selected, btn.commandName, "hover selects the button's command")
        eq(QuickKeybindFrame.mouseOverButton, btn)
        wipe(__qk.keys)
        fire(o, "OnClick", "Button4", false)
        eq(__qk.keys[1], "Button4", "mouse button 4 binds")
        fire(o, "OnClick", "LeftButton", false)
        eq(#__qk.keys, 1, "left click does not bind")
        eq(o._wheel, true, "overlay listens to the wheel")
        o:GetScript("OnMouseWheel")(o, 1)
        eq(__qk.wheel, 1, "wheel reaches the binder")
        fire(o, "OnLeave")
        eq(__qk.selected, nil, "cleared on leave")
    end
end

function T.quickkeybind_overlay_registers_for_anyup_and_hides_through_the_leave_handler()
    -- AnyUp is what lets mouse buttons 4 and 5 reach OnClick on the overlay.
    local b = __button(2, 3)
    local o = overlayOf(b)
    eq(#o._clicks, 1, "one click set")
    eq(o._clicks[1], "AnyUp", "overlay clicks")
    -- Hiding it while hovered must run the stock leave handler, or the binding
    -- tooltip and the selection stay behind.
    qkShow()
    fire(o, "OnEnter")
    eq(__qk.selected, b.commandName, "hovered")
    o:Hide()
    eq(__qk.selected, nil, "hiding the overlay runs the leave handler")
end

function T.quickkeybind_overlay_still_hides_when_the_protected_check_errors_or_is_secret()
    -- CanChangeProtectedState returns a secret for ObjectSecurity, and testing a
    -- secret throws; the mode-close hook must survive both and drop the overlay.
    local b = __button(2, 3)
    local o = overlayOf(b)
    qkShow()
    eq(o:IsShown(), true)
    o.CanChangeProtectedState = function() error("secret boolean value") end
    qkHide()
    eq(o:IsShown(), false, "hides when the call errors")
    qkShow()
    __secretFalse = true
    o.CanChangeProtectedState = function() return false end
    qkHide()
    eq(o:IsShown(), false, "hides when the result is secret")
    eq(__degradeCount, 0, "no combat notice")
end

function T.quickkeybind_opening_and_closing_in_combat_keeps_bar_clicks_working()
    -- The review's finding: closing the mode mid-fight used to leave every
    -- button without a `type` until combat ended.
    local b = __button(2, 3)
    qkShow()
    __combat = true
    qkHide()
    eq(overlayOf(b):IsShown(), false, "overlay drops in combat")
    qkShow()
    eq(overlayOf(b):IsShown(), true, "and rises in combat")
    qkHide()
    eq(b:GetAttribute("type"), "action", "click casting intact")
    eq(__blocked, 0, "no protected operation was attempted")
    local why = ""
    for k, v in pairs(__degraded) do why = why .. k .. "=" .. v .. "; " end
    eq(__degradeCount, 0, "nothing to report: " .. why)
end

function T.quickkeybind_close_in_combat_reports_once_if_the_overlay_cannot_move()
    -- Fallback for a client where the overlay turns out to be protected: it
    -- stays up until combat ends, and the player is told once.
    local all = { __button(1, 1), __button(2, 3), stanceButton(1) }
    qkShow()
    for _, b in ipairs(all) do overlayOf(b)._protected = true end
    __combat = true
    qkHide()
    qkHide()
    eq(overlayOf(all[2]):IsShown(), true, "could not be moved in combat")
    eq(__degradeCount, 1, "exactly one chat line for the whole bar set")
    eq(__degraded.quickkeybind_combat_close:find("resume after combat", 1, true) ~= nil, true)
    eq(__blocked, 0, "did not try")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    for _, b in ipairs(all) do eq(overlayOf(b):IsShown(), false, "released after combat") end
end

function T.quickkeybind_mode_highlights_bindable_buttons()
    local b = __button(3, 5)
    eq(b.QuickKeybindHighlightTexture:IsShown(), false, "hidden outside the mode")
    qkShow()
    eq(b.QuickKeybindHighlightTexture:IsShown(), true, "shown in the mode")
    eq(stanceButton(1).QuickKeybindHighlightTexture:IsShown(), true)
    eq(petButton(1).QuickKeybindHighlightTexture:IsShown(), true)
    qkHide()
    eq(b.QuickKeybindHighlightTexture:IsShown(), false, "hidden again")
end

function T.quickkeybind_mouse_wheel_binding_is_enabled_in_the_mode()
    local b = __button(2, 1)
    eq(b:GetScript("OnMouseWheel"), nil)
    qkShow()
    eq(b:GetScript("OnMouseWheel") ~= nil, true, "wheel handler installed")
    qkHide()
    eq(b:GetScript("OnMouseWheel"), nil, "wheel handler removed")
end

function T.quickkeybind_survives_a_stance_rebuild_in_the_mode()
    qkShow()
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(overlayOf(stanceButton(1)):IsShown(), true, "rebuilt button gets the overlay too")
    qkHide()
    eq(overlayOf(stanceButton(1)):IsShown(), false)
    eq(stanceButton(1):GetAttribute("type"), "spell")
end

-- ---- stance bar: the cast path and rebuilds ----
-- The engine's secure action types are a fixed list (SECURE_ACTIONS in Blizzard_FrameXML/SecureTemplates.lua:
-- actionbar, action, pet, flyout, multispell, spell, toy, item, macro, ... no shapeshift), and a click on a
-- button whose `type` is not in it does nothing. secureClick models just that lookup for the types a stance
-- button can use; the "spell" body is SECURE_ACTIONS.spell reduced (a numeric attribute goes to CastSpellByID).
local function secureClick(b)
    local t = b:GetAttribute("type")
    if t == "spell" then
        local spell = b:GetAttribute("spell")
        local id = tonumber(spell)
        if id then CastSpellByID(id) elseif spell then CastSpellByName(spell) end
    end
end

local function stanceFrameCount()
    local n = 0
    for _, f in ipairs(__frames) do
        if f._name and f._name:match("^FSStanceButton%d+$") then n = n + 1 end
    end
    return n
end

local function labelsUnder(frame)
    local n = 0
    for _, r in ipairs(frame._regions) do
        if r._kind == "FontString" and r._text and r._text ~= "" then n = n + 1 end
        if r._kind ~= "Texture" and r._kind ~= "FontString" and r._kind ~= "MaskTexture" then n = n + labelsUnder(r) end
    end
    return n
end

function T.stance_buttons_cast_their_form_through_the_spell_attribute()
    local casts = {}
    CastSpellByID = function(id) casts[#casts + 1] = id end
    CastSpellByName = function(name) casts[#casts + 1] = name end
    for i = 1, 2 do
        local b = stanceButton(i)
        eq(b:GetAttribute("type"), "spell", "type " .. i)
        eq(b:GetAttribute("spell"), 100 + i, "the form's spell id " .. i)
        eq(b:GetAttribute("shapeshift"), nil, "no attribute the engine does not know")
        eq(b._clicks[1] == "AnyUp" and b._clicks[2] == "AnyDown", true, "AnyUp + AnyDown stay registered")
        secureClick(b)
    end
    eq(#casts, 2, "each click cast once")
    eq(casts[1], 101); eq(casts[2], 102)
end

function T.stance_spell_follows_the_form_info_out_of_combat_only()
    GetShapeshiftFormInfo = function(i) return "tex", false, true, 200 + i end
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(stanceButton(1):GetAttribute("spell"), 201, "re-read on a state event out of combat")
    __combat = true
    GetShapeshiftFormInfo = function(i) return "tex", false, true, 300 + i end
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(__blocked, 0, "no protected write attempted in combat")
    eq(stanceButton(1):GetAttribute("spell"), 201, "attribute held through the fight")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(stanceButton(1):GetAttribute("spell"), 301, "caught up when combat ends")
    eq(stanceButton(2):GetAttribute("spell"), 302)
end

function T.stance_form_change_in_combat_rebuilds_after_combat()
    __combat = true
    GetNumShapeshiftForms = function() return 1 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(stanceButton(2):IsShown(), true, "nothing rebuilt in combat")
    eq(__blocked, 0)
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(stanceButton(2):IsShown(), false, "rebuilt once combat ended")
    eq(stanceButton(1):IsShown(), true)
end

function T.stance_rebuilds_reuse_the_buttons_instead_of_creating_new_ones()
    local b1, b2 = stanceButton(1), stanceButton(2)
    eq(stanceFrameCount(), 2, "two forms, two frames after login")
    for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS", "UPDATE_SHAPESHIFT_FORMS" }) do
        __fire_event(e)
    end
    eq(stanceFrameCount(), 2, "rebuilds created nothing")
    eq(stanceButton(1) == b1 and stanceButton(2) == b2, true, "same frames behind the globals")
    eq(b1:IsShown() and b2:IsShown(), true)
    eq(b1:GetParent() == _G.FSStanceBar and b2:GetParent() == _G.FSStanceBar, true)
    eq(#b1._points, 1, "one anchor, re-seated rather than stacked")
    eq(#b2._points, 1)
end

function T.stance_form_count_changes_hide_and_return_the_same_buttons()
    local b2 = stanceButton(2)
    GetNumShapeshiftForms = function() return 1 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(b2:IsShown(), false, "the extra button hides")
    eq(stanceButton(1):IsShown(), true)
    GetNumShapeshiftForms = function() return 2 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(stanceButton(2) == b2 and b2:IsShown(), true, "and comes back as the same frame")
    GetNumShapeshiftForms = function() return 0 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(_G.FSStanceBar:IsShown(), false)
    eq(stanceButton(1):IsShown() or stanceButton(2):IsShown(), false, "no form, no visible button")
    eq(stanceFrameCount(), 2, "never more than the two ever needed")
end

function T.stance_button_draws_one_hotkey_label_however_often_it_rebuilds()
    __bindings.SHAPESHIFTBUTTON1 = "BUTTON4"
    for _, e in ipairs({ "UPDATE_BINDINGS", "UPDATE_SHAPESHIFT_FORMS", "PLAYER_ENTERING_WORLD", "UPDATE_BINDINGS" }) do
        __fire_event(e)
    end
    eq(labelsUnder(stanceButton(1)), 1, "one label with text on the button")
    eq(stanceButton(1).HotKey._text, "MB4")
    local n = 0
    for _, f in ipairs(__frames) do
        if f._kind == "FontString" and f._text == "MB4" then n = n + 1 end
    end
    eq(n, 1, "and no other label with that text anywhere (a stale button's would still be a frame)")
end

-- A CheckButton click in engine order (PreClick, the native checked flip, OnClick, PostClick), for
-- both halves of AnyDown + AnyUp.
local function stanceClick(b)
    for _, down in ipairs({ true, false }) do
        b.Fire(b, "PreClick", "LeftButton", down)
        b:SetChecked(not b:GetChecked())
        b.Fire(b, "OnClick", "LeftButton", down)
        b.Fire(b, "PostClick", "LeftButton", down)
    end
end

function T.stance_click_on_the_active_form_keeps_it_checked_and_an_inactive_one_unchecked()
    eq(stanceButton(1):GetChecked(), true, "form 1 is the active one")
    stanceClick(stanceButton(1))
    eq(stanceButton(1):GetChecked(), true, "a no-op click on the active form leaves it checked")
    local b = stanceButton(1)
    b.Fire(b, "PreClick", "LeftButton", false)
    b:SetChecked(not b:GetChecked())
    b.Fire(b, "PostClick", "LeftButton", false)
    eq(b:GetChecked(), true, "an odd number of native flips still ends checked")
    stanceClick(stanceButton(2))
    eq(stanceButton(2):GetChecked(), false, "an inactive form is not checked by the click alone")
    GetShapeshiftFormInfo = function(i) return "tex", i == 2, true, 100 + i end
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(stanceButton(2):GetChecked(), true, "checked when the client reports it active")
    eq(stanceButton(1):GetChecked(), false, "the old form drops")
end

function T.stance_click_resync_never_reads_a_secret_active_flag()
    local b = stanceButton(1)
    GetShapeshiftFormInfo = function(i) return "tex", __SECRET, true, 100 + i end
    local real = b.SetChecked
    b.SetChecked = function(self, v)
        eq(type(v), "boolean", "a secret flag is never turned into a check")
        real(self, v)
    end
    stanceClick(b)
    eq(b:GetChecked(), true, "the last known plain check is restored after the flip")
    local c = stanceButton(2)
    c.fsLastActive = nil
    c:SetChecked(true)
    c.Fire(c, "PostClick", "LeftButton", false)
    eq(c:GetChecked(), true, "with no cached value the native state is left alone")
end

function T.stance_buttons_hook_each_script_once_however_often_they_rebuild()
    local function counts(b)
        local out = {}
        for k, list in pairs(b._hooks) do out[k] = #list end
        return out
    end
    local before = { counts(stanceButton(1)), counts(stanceButton(2)) }
    eq(before[1].PostClick, 1, "the click re-sync is hooked")
    eq(before[1].OnEnter ~= nil and before[1].OnLeave ~= nil, true, "the tooltip is hooked")
    for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS", "UPDATE_BINDINGS", "UPDATE_SHAPESHIFT_FORMS" }) do
        __fire_event(e)
    end
    GetNumShapeshiftForms = function() return 1 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    GetNumShapeshiftForms = function() return 2 end
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    for i = 1, 2 do
        local now = counts(stanceButton(i))
        for k, n in pairs(before[i]) do eq(now[k], n, "hooks on " .. k .. " of button " .. i) end
        for k, n in pairs(now) do eq(before[i][k], n, "no new hooked script " .. k .. " on button " .. i) end
    end
end

function T.stance_spell_still_syncs_when_the_hotkey_update_throws_and_stays_owed_in_combat()
    GetBindingKey = function(action)
        if action:find("^SHAPESHIFTBUTTON") then error("binding lookup failed") end
        return __bindings[action]
    end
    GetShapeshiftFormInfo = function(i) return "tex", i == 1, true, 400 + i end
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(stanceButton(1):GetAttribute("spell"), 401, "synced although the hotkey step threw")
    __combat = true
    GetShapeshiftFormInfo = function(i) return "tex", i == 1, true, 500 + i end
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(__blocked, 0)
    eq(stanceButton(1):GetAttribute("spell"), 401, "held in combat")
    __combat = false
    GetBindingKey = function(action) return __bindings[action] end
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(stanceButton(1):GetAttribute("spell"), 501, "the skipped write is still owed when combat ends")
    eq(stanceButton(2):GetAttribute("spell"), 502)
end

function T.stance_a_throw_while_styling_does_not_leak_the_frame_or_double_the_hooks()
    -- Variant: the first SetSize on FSStanceButton3 throws, i.e. StyleButton dies when a third form shows up.
    GetNumShapeshiftForms = function() return 3 end
    GetShapeshiftFormInfo = function(i) return "tex", i == 1, true, 100 + i end
    local ok = pcall(__fire_event, "UPDATE_SHAPESHIFT_FORMS")
    eq(ok, false, "the fixture made the build throw")
    eq(__sizeThrown, true)
    local third = stanceButton(3)
    eq(third ~= nil, true, "registered even though it was never styled")
    eq(stanceFrameCount(), 3)
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(stanceFrameCount(), 3, "the retry finished the button, no re-CreateFrame")
    eq(stanceButton(3) == third, true, "same frame behind the global")
    eq(third:IsShown(), true)
    eq(#third._hooks.PostClick, 1, "hooked once")
    eq(#third._hooks.OnEnter, #stanceButton(1)._hooks.OnEnter, "as many tooltip hooks as a button built cleanly")
    eq(third._w, stanceButton(1)._w, "styled to the same size")
    eq(labelsUnder(third) <= labelsUnder(stanceButton(1)), true, "no extra labels")
end

function T.stance_missing_spell_id_at_login_is_not_reported_when_a_later_read_supplies_it()
    eq(__degradeCount, 0, "nothing reported at the first read")
    eq(stanceButton(1):GetAttribute("spell"), nil, "no id yet")
    __missingSpell = false
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(stanceButton(1):GetAttribute("spell"), 101)
    __runTimers()
    eq(__degradeCount, 0, "the delayed look found it and stayed quiet")
end

function T.stance_missing_spell_id_is_reported_once_if_it_stays_missing()
    eq(__degradeCount, 0, "not at the first read")
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    eq(__degradeCount, 0, "not on a retry either")
    __runTimers()
    eq(__degradeCount, 1, "once the grace period passed, for the whole bar")
    eq(__degraded.stancebar_nospellid:find("cannot cast", 1, true) ~= nil, true)
    __fire_event("UPDATE_SHAPESHIFT_FORM")
    __runTimers()
    eq(__degradeCount, 1, "and never again")
end

function T.stance_rescale_in_combat_touches_no_protected_frame_and_resizes_after()
    eq(#__rescaleFns >= 1, true, "the stance bar registered for rescales")
    local b = stanceButton(1)
    local w = b._w
    FS.Layout.stance = { w = 200, h = 60 }
    __combat = true
    for _, fn in ipairs(__rescaleFns) do pcall(fn) end
    eq(__blocked, 0, "no protected operation attempted in combat")
    eq(b._w, w, "button untouched in combat")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(b._w, 60, "re-sized once combat ended")
    eq(__blocked, 0)
    FS.Layout.stance = { w = 200, h = 45 }
    for _, fn in ipairs(__rescaleFns) do pcall(fn) end
    eq(b._w, 45, "out of combat it re-sizes at once")
end

-- First login as a Paladin (the variant below): GetNumShapeshiftForms() is 0, so the stance bar must
-- hide cleanly: no buttons, no error (Apply pcalls the build and prints on failure), no degrade, no
-- protected operation, and the state events leave it hidden.
function T.stance_bar_hides_cleanly_for_a_paladin_with_no_forms()
    local _, class = UnitClass("player")
    eq(GetNumShapeshiftForms(), 0, "variant has no forms")
    eq(_G.FSStanceBar ~= nil, true, "the container exists")
    eq(_G.FSStanceBar:IsShown(), false, "and is hidden")
    eq(stanceButton(1), nil, "no stance button was built")
    for _, e in ipairs({ "UPDATE_SHAPESHIFT_FORMS", "UPDATE_SHAPESHIFT_FORM", "UPDATE_SHAPESHIFT_COOLDOWN",
                         "UPDATE_BINDINGS", "PLAYER_ENTERING_WORLD" }) do
        __fire_event(e)
    end
    eq(_G.FSStanceBar:IsShown(), false, "still hidden after the state events")
    eq(stanceButton(1), nil, "still no stance button")
    for _, line in ipairs(__stancePrints) do
        if line:find("stance bar failed", 1, true) then error("stance bar build failed: " .. line) end
    end
    eq(__degradeCount, 0, "no degrade logged")
end

-- ---- mouseover casting ---------------------------------------------------
-- SecureButton_GetModifiedUnit (SecureTemplates.lua, retail 12.1) only applies mouseover, self and
-- focus casting to a button carrying checkmouseovercast / checkselfcast / checkfocuscast, and only
-- Blizzard's own ActionBarActionButtonMixin:OnLoad sets them, so our buttons must.
local MOUSEOVER_HINT = "Forever STUwave: mouseover casting is off. /fsmouseover on to cast on the "
    .. "unit under your mouse without changing target."

local function printed(needle)
    local n = 0
    for _, line in ipairs(__prints) do
        local plain = line:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
        if plain:find(needle, 1, true) then n = n + 1 end
    end
    return n
end

function T.mouseover_every_button_carries_the_three_cast_attributes()
    local count = 0
    for bar = 1, 6 do
        for i = 1, 12 do
            local b = __button(bar, i)
            for _, attr in ipairs({ "checkmouseovercast", "checkselfcast", "checkfocuscast" }) do
                eq(b:GetAttribute(attr), true, ("bar %d button %d %s"):format(bar, i, attr))
            end
            count = count + 1
        end
    end
    eq(count, 72, "every action button was checked")
    eq(__blocked, 0, "no protected call was refused")
end

-- Booted by the `__combat = true` variant: the client logs in mid fight.
function T.mouseover_attributes_are_never_written_in_combat()
    eq(__button(1, 1), nil, "no button is built in combat")
    eq(__blocked, 0, "no secure attribute write was attempted")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__button(1, 1):GetAttribute("checkmouseovercast"), true, "set once combat ends")
    eq(__button(6, 12):GetAttribute("checkselfcast"), true, "last button too")
    eq(__button(6, 12):GetAttribute("checkfocuscast"), true, "focus too")
    eq(__blocked, 0, "the deferred build is out of combat")
end

function T.mouseover_on_and_off_set_the_cvar()
    SlashCmdList["FSMOUSEOVER"]("on")
    eq(__cvars.enableMouseoverCast, "1", "on")
    eq(__settings[#__settings], "SetCVar:enableMouseoverCast=1", "on call")
    SlashCmdList["FSMOUSEOVER"]("off")
    eq(__cvars.enableMouseoverCast, "0", "off")
    eq(__settings[#__settings], "SetCVar:enableMouseoverCast=0", "off call")
    SlashCmdList["FSMOUSEOVER"]("  ON  ")
    eq(__cvars.enableMouseoverCast, "1", "case and spaces are forgiven")
    for _, call in ipairs(__settings) do
        if call:find("SetModifiedClick", 1, true) or call:find("SaveBindings", 1, true) then
            error("on/off alone must not touch the modifier: " .. call)
        end
    end
end

function T.mouseover_a_refused_cvar_prints_the_failure_not_on()
    __cvarRefuses = true
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("on")
    eq(__cvars.enableMouseoverCast, "0", "the client kept the CVar off")
    eq(printed("could not set the enableMouseoverCast CVar"), 1, "failure reported")
    eq(printed("mouseover casting on"), 0, "not claimed to be on")
    __cvarRefuses = false
    SlashCmdList["FSMOUSEOVER"]("on")
    eq(printed("mouseover casting on"), 1, "a successful set still says on")
end

function T.mouseover_a_modifier_sets_the_click_and_saves_the_bindings()
    SlashCmdList["FSMOUSEOVER"]("alt")
    eq(__settings[#__settings - 1], "SetModifiedClick:MOUSEOVERCAST=ALT", "click")
    eq(__settings[#__settings], "SaveBindings:1", "saved after the click, to the current set")
    eq(__modClicks.MOUSEOVERCAST, "ALT", "applied")
    eq(__cvars.enableMouseoverCast, "0", "a bare modifier leaves the CVar alone")
    for _, key in ipairs({ "ctrl", "shift", "none" }) do
        __settings = {}
        SlashCmdList["FSMOUSEOVER"](key)
        eq(__modClicks.MOUSEOVERCAST, key:upper(), key)
        eq(__settings[2], "SaveBindings:1", key .. " saved")
    end
    __settings = {}
    SlashCmdList["FSMOUSEOVER"]("on ctrl")
    eq(__cvars.enableMouseoverCast, "1", "both args: cvar")
    eq(__modClicks.MOUSEOVERCAST, "CTRL", "both args: modifier")
    eq(#__settings, 3, "cvar, click, save")
end

function T.mouseover_an_unknown_argument_changes_nothing_and_prints_usage()
    __settings = {}
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("banana")
    eq(#__settings, 0, "no setting touched")
    eq(printed("/fsmouseover") >= 1, true, "usage printed")
    SlashCmdList["FSMOUSEOVER"]("on banana")
    eq(#__settings, 0, "a bad word anywhere cancels the whole command")
end

function T.mouseover_no_args_reports_the_state()
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("")
    eq(#__settings, 0, "reporting changes nothing")
    eq(printed("mouseover casting is off, modifier NONE (always)"), 1, "cvar off and modifier reported")
    __cvars.enableMouseoverCast = "1"
    __modClicks.MOUSEOVERCAST = "ALT"
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("")
    eq(printed("mouseover casting is on, modifier ALT (hold it)"), 1, "cvar on and modifier ALT reported")
    eq(#__settings, 0, "still nothing written")
end

function T.mouseover_a_modifier_in_combat_waits_for_combat_to_end()
    __combat = true
    __settings = {}
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("alt")
    eq(__blocked, 0, "the protected calls were not even attempted")
    eq(#__settings, 0, "nothing applied yet")
    eq(__modClicks.MOUSEOVERCAST, "NONE", "unchanged")
    eq(printed("combat") >= 1, true, "told the user it is queued")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__modClicks.MOUSEOVERCAST, "ALT", "applied after combat")
    eq(__settings[#__settings], "SaveBindings:1", "saved after combat")
    local n = #__settings
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(#__settings, n, "replayed once only")
end

function T.mouseover_the_latest_queued_modifier_wins()
    __combat = true
    SlashCmdList["FSMOUSEOVER"]("alt")
    SlashCmdList["FSMOUSEOVER"]("ctrl")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__modClicks.MOUSEOVERCAST, "CTRL", "last one")
end

function T.mouseover_a_successful_set_clears_a_stale_pending_modifier()
    __combat = true
    SlashCmdList["FSMOUSEOVER"]("alt")
    __combat = false
    __settings = {}
    SlashCmdList["FSMOUSEOVER"]("ctrl")
    eq(__modClicks.MOUSEOVERCAST, "CTRL", "set directly after combat")
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__modClicks.MOUSEOVERCAST, "CTRL", "the stale ALT was not replayed over it")
    for _, call in ipairs(__settings) do
        if call:find("=ALT", 1, true) then error("stale pending modifier replayed: " .. call) end
    end
    eq(#__settings, 2, "only the one successful set (click + save)")
end

function T.mouseover_a_refused_call_with_no_lockdown_flag_is_still_deferred()
    -- the client can refuse mid-transition while InCombatLockdown() still reads false
    local real = SetModifiedClick
    local refuse = true
    SetModifiedClick = function(...) if refuse then error("blocked", 2) end return real(...) end
    __prints = {}
    SlashCmdList["FSMOUSEOVER"]("shift")
    eq(__modClicks.MOUSEOVERCAST, "NONE", "refused")
    refuse = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eq(__modClicks.MOUSEOVERCAST, "SHIFT", "retried after combat")
end

function T.mouseover_hint_prints_once_when_the_cvar_is_off()
    eq(printed(MOUSEOVER_HINT), 1, "printed at first login")
    eq(ForeverSTUwaveDB.mouseoverHintSeen, true, "flag stored")
end

function T.mouseover_hint_stays_quiet_once_seen()
    eq(printed(MOUSEOVER_HINT), 0, "seen flag from an earlier session")
end

function T.mouseover_hint_stays_quiet_when_the_cvar_is_on()
    eq(printed(MOUSEOVER_HINT), 0, "already on")
end

-- ---- hotkey text --------------------------------------------------------
function T.hotkey_text_follows_binding_changes()
    local main, multi = __button(1, 1), __button(2, 3)
    eq(multi.HotKey._text == nil or multi.HotKey._text == "", true, "unbound at start")
    __bindings["MULTIACTIONBAR1BUTTON3"] = "BUTTON4"
    __fire_event("UPDATE_BINDINGS")
    eq(multi.HotKey._text, "MB4")
    eq(multi.HotKey:IsShown(), true)
    __bindings["MULTIACTIONBAR1BUTTON3"] = nil
    __fire_event("UPDATE_BINDINGS")
    eq(multi.HotKey:IsShown(), false, "hidden when unbound")
end

function T.hotkey_text_refreshes_from_quick_keybind_mode_itself()
    -- The binder calls SetBinding; UPDATE_BINDINGS is not guaranteed to be the
    -- only signal, so the mode's own success event and its close also refresh.
    local multi = __button(2, 3)
    qkShow()
    __bindings["MULTIACTIONBAR1BUTTON3"] = "BUTTON5"
    __trigger("KeybindListener.RebindSuccess", "MULTIACTIONBAR1BUTTON3")
    eq(multi.HotKey._text, "MB5", "after a successful rebind")
    __bindings["MULTIACTIONBAR1BUTTON3"] = "BUTTON4"
    qkHide()
    eq(multi.HotKey._text, "MB4", "after the mode closes")
end

function T.action_pill_chrome_lives_on_a_hideable_child()
    -- One hide call must take a pill's whole look (fill, border, MAIN glow, tag)
    -- and nothing else: the buttons stay.
    local header = _G.FSActionBar1
    local chrome = header.fsChrome
    eq(chrome ~= nil, true, "chrome child exists")
    eq(chrome._parent, header, "chrome is a child of the pill")
    eq(chrome:IsShown(), true, "chrome shown by default")
    FS.ActionBars.SetConsoleActive(true)
    for i = 1, 6 do
        eq(_G["FSActionBar" .. i].fsChrome:IsShown(), false, "chrome hidden under the console, bar " .. i)
    end
    eq(__button(1, 1):IsShown(), true, "buttons stay under the console")
    FS.ActionBars.SetConsoleActive(false)
    eq(chrome:IsShown(), true, "chrome back with the console off")
end

function T.action_spine_gap_widens_under_the_console_and_keeps_the_stack_centred()
    local stack = _G.FSActionBarStack
    local function leftX(bar) return _G["FSActionBar" .. bar]._points[1].x end
    local function stackW() return stack:GetWidth() end
    local barW = FS.ActionBars.geometry.barW
    local before = { w = stackW(), left = leftX(1), right = leftX(2), gap = FS.ActionBars.geometry.gap, btn = FS.ActionBars.geometry.btnSize }
    eq(before.right - before.left, barW + before.gap, "default pitch")
    FS.ActionBars.SetConsoleActive(true)
    local g = FS.ActionBars.geometry
    eq(g.gap, FS.ActionBars.SPINE_DESIGN * FS.Layout.Scale(), "gap is the spine width in design px")
    eq(g.gap > before.gap, true, "spine is wider than the pill gap")
    eq(leftX(2) - leftX(1), barW + g.gap, "right half starts a spine further over")
    eq(leftX(1), before.left, "left half does not move")
    -- Centred: the spine is the stack centre, both halves the same distance off it.
    eq(g.spineX, stackW() / 2, "spine on the stack centre")
    local leftEdge = leftX(1) + barW
    local rightEdge = leftX(2)
    eq(g.spineX - leftEdge, rightEdge - g.spineX, "halves equidistant from the spine")
    eq(stackW(), before.w + (g.gap - before.gap), "stack grew by exactly the extra gap")
    eq(g.btnSize, before.btn, "buttons keep their size")
    FS.ActionBars.SetConsoleActive(false)
    eq(FS.ActionBars.geometry.gap, before.gap, "old gap back")
    eq(stackW(), before.w, "old width back")
end

function T.stance_and_pet_hotkeys_follow_bindings()
    __bindings["SHAPESHIFTBUTTON2"] = "BUTTON4"
    __bindings["BONUSACTIONBUTTON3"] = "BUTTON5"
    __fire_event("UPDATE_BINDINGS")
    eq(stanceButton(2).HotKey._text, "MB4", "stance")
    eq(stanceButton(2).HotKey:IsShown(), true)
    eq(petButton(3).HotKey._text, "MB5", "pet")
end

-- ---- pet clicks: right click toggles autocast, the mode check survives a click ----
-- The secure template runs CastPetAction for EVERY mouse button, so a right click needs its own
-- route: `type2 = "macro"` clicking Blizzard's hidden PetActionButton<i> (its OnClick calls
-- TogglePetAutocast). Attributes are set once at build, never in combat.
local function refreshPetBar() __fire_event("PET_BAR_UPDATE") end
local function setPetMode(i, name, active) __pet[i] = { name = name, active = active } end
-- A CheckButton click in engine order: PreClick, the native checked flip, OnClick, PostClick.
local function nativeClick(b, mouse, down)
    fire(b, "PreClick", mouse, down)
    b:SetChecked(not b:GetChecked())
    fire(b, "OnClick", mouse, down)
    fire(b, "PostClick", mouse, down)
end
local function fullClick(b, mouse)    -- AnyDown + AnyUp: both halves of one click
    nativeClick(b, mouse, true)
    nativeClick(b, mouse, false)
end

function T.pet_click_right_button_routes_to_the_hidden_blizzard_button_and_left_still_casts()
    for i = 1, 10 do
        local b = petButton(i)
        eq(b:GetAttribute("type"), "pet", "left click type " .. i)
        eq(b:GetAttribute("action"), i, "left click action " .. i)
        eq(b:GetAttribute("type2"), "macro", "right click type " .. i)
        eq(b:GetAttribute("macrotext2"), "/click PetActionButton" .. i .. " RightButton", "macrotext " .. i)
        -- Only an UNMODIFIED right click is routed: a modified one falls back to type="pet".
        for _, mod in ipairs({ "shift-", "ctrl-", "alt-" }) do
            eq(b:GetAttribute(mod .. "type2"), nil, mod .. "type2 " .. i)
            eq(b:GetAttribute(mod .. "macrotext2"), nil, mod .. "macrotext2 " .. i)
        end
    end
end

-- Booted by the `__combat = true` variant below: the client logs in mid fight.
function T.pet_click_attributes_are_never_written_in_combat()
    eq(petButton(1), nil, "no button is built in combat")
    eq(__blocked, 0, "no protected call was attempted")
    __fire_event("PET_BAR_UPDATE")
    __fire_event("UNIT_PET", "player")
    eq(petButton(1), nil, "events in combat still build nothing")
    eq(__blocked, 0, "still no protected call")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    for i = 1, 10 do
        eq(petButton(i):GetAttribute("type2"), "macro", "built after combat with the route " .. i)
        eq(petButton(i):GetAttribute("macrotext2"), "/click PetActionButton" .. i .. " RightButton", "macrotext " .. i)
    end
    eq(__blocked, 0, "the deferred build is out of combat")
end

function T.pet_click_on_the_active_mode_keeps_it_checked_without_a_pet_bar_update()
    setPetMode(1, "Follow", true)
    refreshPetBar()
    eq(petButton(1):GetChecked(), true, "checked before")
    fullClick(petButton(1), "LeftButton")
    eq(petButton(1):GetChecked(), true, "still checked after clicking the active mode")
    nativeClick(petButton(1), "LeftButton", false)   -- an odd number of native flips
    eq(petButton(1):GetChecked(), true, "an odd flip count still ends checked")
end

function T.pet_click_on_an_inactive_mode_checks_only_once_the_pet_reports_it_active()
    setPetMode(1, "Follow", true); setPetMode(2, "Stay", false)
    refreshPetBar()
    eq(petButton(2):GetChecked(), false, "unchecked before")
    fullClick(petButton(2), "LeftButton")
    eq(petButton(2):GetChecked(), false, "the click alone does not check it")
    nativeClick(petButton(2), "LeftButton", false)   -- a single native flip
    eq(petButton(2):GetChecked(), false, "one flip does not check it either")
    setPetMode(1, "Follow", false); setPetMode(2, "Stay", true)
    refreshPetBar()
    eq(petButton(2):GetChecked(), true, "checked when the pet reports it active")
    eq(petButton(1):GetChecked(), false, "the old mode drops")
end

function T.pet_click_resync_never_reads_a_secret_active_flag()
    setPetMode(1, "Follow", true)
    refreshPetBar()
    __pet[1].active = __SECRET
    local b = petButton(1)
    -- the secret flag must not be compared: SetChecked only ever sees a plain boolean
    local real = b.SetChecked
    b.SetChecked = function(self, v)
        eq(type(v), "boolean", "a secret flag is never turned into a check")
        real(self, v)
    end
    nativeClick(b, "LeftButton", false)         -- the native flip unchecks it; must not throw
    eq(b:GetChecked(), true, "the last known plain check is restored after the flip")
    __pet[2] = { name = "Stay", active = __SECRET }
    local c = petButton(2)
    c.fsLastActive = nil                        -- nothing cached for this button
    c:SetChecked(true)
    fire(c, "PostClick", "LeftButton", false)
    eq(c:GetChecked(), true, "with no cached value the native state is left alone")
end

function T.pet_click_tooltip_hints_right_click_only_where_autocast_is_allowed()
    __pet[1] = { name = "Firebolt", allowed = true, enabled = false }
    __pet[2] = { name = "Attack", allowed = false, enabled = false }
    fire(petButton(1), "OnEnter")
    eq(GameTooltip._lines[1], "Right-click: toggle autocast", "autocast slot hint")
    fire(petButton(1), "OnLeave")
    fire(petButton(2), "OnEnter")
    eq(#GameTooltip._lines, 0, "no hint where autocast is not allowed")
end

-- ---- pet console-dock look (mockup option C): countdown seconds, hotkey plate ----
-- Booted with PET_RING_PRELUDE (10 slots, a controllable UI scale via __rescale).
function T.pet_style_countdown_numbers_are_enabled()
    for _, i in ipairs({ 1, 5, 10 }) do
        eq(petButton(i).cooldown._hideNumbers, false, "countdown numbers on, button " .. i)
    end
end

function T.pet_style_countdown_font_is_white_mono_11_outlined()
    for _, i in ipairs({ 1, 10 }) do
        local fs = petButton(i).cooldown:GetCountdownFontString()
        eq(fs._font ~= nil and fs._font[1], "mono.ttf", "mono font token, button " .. i)
        eq(fs._font[2], 11, "size 11")
        eq(fs._font[3], "OUTLINE", "outlined")
        eq(fs._textColor ~= nil and fs._textColor[1] == 1 and fs._textColor[2] == 1 and fs._textColor[3] == 1, true, "white")
    end
end

function T.pet_style_a_cooldown_without_a_countdown_fontstring_still_builds()
    -- Booted with GetCountdownFontString removed (PET_VARIANTS): the buttons still build, and the
    -- numbers are still switched on.
    local b = petButton(1)
    eq(b ~= nil and b.cooldown ~= nil, true, "button built")
    eq(b.cooldown._hideNumbers, false, "numbers still enabled")
end

function T.pet_style_countdown_font_survives_a_rescale()
    -- The template (or anything else) putting its own face back must not outlast a rescale:
    -- ResizeButtons re-applies StyleCountdown.
    for _, i in ipairs({ 1, 10 }) do
        local fs = petButton(i).cooldown:GetCountdownFontString()
        fs._font = { "stock.ttf", 14, "" }
        fs._textColor = { 0.5, 0.5, 0.5 }
    end
    __rescale(2)
    for _, i in ipairs({ 1, 10 }) do
        local fs = petButton(i).cooldown:GetCountdownFontString()
        eq(fs._font[1], "mono.ttf", "mono font restored, button " .. i)
        eq(fs._font[2], 11, "size 11 and NOT scaled with the UI scale")
        eq(fs._font[3], "OUTLINE", "outlined")
        eq(fs._textColor[1] == 1 and fs._textColor[2] == 1 and fs._textColor[3] == 1, true, "white")
    end
end

function T.pet_style_countdown_uses_a_named_font_object_when_the_client_has_one()
    -- Booted with CreateFont and Cooldown:SetCountdownFont (PET_VARIANTS): the cooldown is handed
    -- the font object by name, and the FontString is left to the engine.
    for _, i in ipairs({ 1, 10 }) do
        eq(petButton(i).cooldown._countdownFontName, "FSPetCountdownFont", "font object, button " .. i)
    end
    local fo = __fontObjects["FSPetCountdownFont"]
    eq(fo ~= nil and fo._font[1], "mono.ttf", "mono face")
    eq(fo._font[2], 11, "size 11")
    eq(fo._font[3], "OUTLINE", "outlined")
    eq(fo._color[1] == 1 and fo._color[2] == 1 and fo._color[3] == 1, true, "white")
    __rescale(2)
    eq(petButton(1).cooldown._countdownFontName, "FSPetCountdownFont", "still set after a rescale")
    eq(fo._font[2], 11, "size untouched by the rescale")
end

function T.pet_cooldown_a_plain_one_shows_and_a_secret_one_stays_hidden_uncompared()
    local b = petButton(2)
    GetPetActionCooldown = function() return 100, 8, 1 end
    refreshPetBar()
    eq(b.cooldown:IsShown(), true, "a plain cooldown shows")
    eq(b.cooldown._cd[1] == 100 and b.cooldown._cd[2] == 8, true, "and is set from the plain values")
    b.cooldown._cd = nil
    -- start and duration are secret: hidden, never handed to SetCooldown, never compared
    -- (any compare or arithmetic on __SECRET raises; the guarded update pcall would swallow it,
    -- so SetCooldown must also stay untouched).
    GetPetActionCooldown = function() return __SECRET, __SECRET, 1 end
    refreshPetBar()
    eq(b.cooldown:IsShown(), false, "a secret cooldown stays hidden")
    eq(b.cooldown._cd, nil, "SetCooldown never saw a secret")
    GetPetActionCooldown = function() return 100, __SECRET, 1 end
    refreshPetBar()
    eq(b.cooldown:IsShown(), false, "a secret duration alone hides it too")
    eq(b.cooldown._cd, nil, "SetCooldown never saw a secret duration")
end

local function plateOf(b) return b.fsHotkeyPlate end
local function plateAnchors(b)
    local plate, tl, br = plateOf(b), nil, nil
    for _, p in ipairs(plate._points) do
        if p.point == "TOPLEFT" then tl = p elseif p.point == "BOTTOMRIGHT" then br = p end
    end
    return tl, br
end

function T.pet_style_hotkey_plate_is_a_dark_plate_sized_from_the_text()
    __bindings["BONUSACTIONBUTTON1"] = "SHIFT-F"
    __fire_event("UPDATE_BINDINGS")
    local b = petButton(1)
    local plate = plateOf(b)
    eq(plate ~= nil, true, "plate exists")
    eq(plate._kind, "Texture", "a texture")
    eq(plate._parent, b.HotKey._parent, "on the text host with the hotkey, above the swipe")
    eq(plate._parent._level > b.cooldown._level, true, "above the swipe")
    local c = plate._color
    eq(c ~= nil and math.abs(c[1] - 0.024) < 0.002 and math.abs(c[2] - 0.012) < 0.002
        and math.abs(c[3] - 0.071) < 0.002 and math.abs(c[4] - 0.78) < 0.002, true, "AB_PLATE colour")
    local tl, br = plateAnchors(b)
    eq(tl ~= nil and br ~= nil, true, "pinned by two corners")
    eq(tl.rel, b.HotKey, "top left follows the text")
    eq(br.rel, b.HotKey, "bottom right follows the text")
    eq(tl.x < 0 and br.x > 0, true, "padded left and right of the text")
    eq(tl.y > 0 and br.y < 0, true, "padded above and below the text")
    eq(plate:IsShown(), true, "shown with a bound key")
    __bindings["BONUSACTIONBUTTON1"] = nil
    __fire_event("UPDATE_BINDINGS")
    eq(plate:IsShown(), false, "gone with an unbound key")
    eq(b.HotKey:IsShown(), false, "with its text")
end

function T.pet_style_hotkey_plate_and_text_follow_a_rescale()
    __bindings["BONUSACTIONBUTTON1"] = "F"
    __fire_event("UPDATE_BINDINGS")
    local b = petButton(1)
    local tl1, br1 = plateAnchors(b)
    local size1 = b.HotKey._font[2]
    local seat1 = b.HotKey._points[1]
    __rescale(2)
    local tl2, br2 = plateAnchors(b)
    eq(math.abs(b.HotKey._font[2] - 2 * size1) < 1e-6, true, "text doubles: " .. tostring(b.HotKey._font[2]))
    eq(math.abs(tl2.x - 2 * tl1.x) < 1e-6 and math.abs(br2.x - 2 * br1.x) < 1e-6, true, "plate padding x doubles")
    eq(math.abs(tl2.y - 2 * tl1.y) < 1e-6 and math.abs(br2.y - 2 * br1.y) < 1e-6, true, "plate padding y doubles")
    local seat2 = b.HotKey._points[1]
    eq(#b.HotKey._points, 1, "the text keeps ONE anchor")
    eq(seat2.point, "TOPRIGHT", "still top right")
    eq(math.abs(seat2.x - 2 * seat1.x) < 1e-6 and math.abs(seat2.y - 2 * seat1.y) < 1e-6, true, "text seat doubles")
    eq(tl2.rel, b.HotKey, "still follows the text")
    __rescale(0.5)
    eq(math.abs(b.HotKey._font[2] - 0.5 * size1) < 1e-6, true, "and halves")
    eq(plateOf(b):IsShown(), true, "still shown")
end

-- ---- pet autocast ring (the approved "Pet slot rings" mockup, driven by FS.ChevronCastBar.Fx) ----
-- Booted with PET_RING_PRELUDE (a stepped GetTime, 10 pet slots, GetPetActionInfo from __pet) and the
-- real ChevronCastBar.lua loaded after PetActionBar.lua.
local function setPet(i, name, allowed, enabled) __pet[i] = { name = name, allowed = allowed, enabled = enabled } end
local function refreshPet() __fire_event("PET_BAR_UPDATE") end
local function onUpdateFrames()
    local list = {}
    for _, f in ipairs(__frames) do if f._scripts.OnUpdate then list[#list + 1] = f end end
    return list
end
local function tick(dt)
    __now = __now + dt
    for _, f in ipairs(onUpdateFrames()) do f._scripts.OnUpdate(f, dt) end
end
local function arcsOf(i)
    local ring = petButton(i).fsAutoCastRing
    return ring and ring.arcs or {}
end
local function shownArcs(i)
    local n = 0
    for _, t in ipairs(arcsOf(i)) do if t:IsShown() then n = n + 1 end end
    return n
end

local FAINT = 0.14   -- the mockup's unlit ring: rgba(green, 0.14)

local function eqArcs(i, alpha, msg)
    local arcs = arcsOf(i)
    eq(#arcs, 16, msg .. ": sixteen arcs")
    for n, t in ipairs(arcs) do
        eq(t:IsShown(), true, msg .. ": arc " .. n .. " shown")
        eq(math.abs(t._vertex[4] - alpha) < 1e-6, true, msg .. ": arc " .. n .. " alpha " .. tostring(t._vertex[4]))
    end
end

function T.pet_ring_enabled_autocast_is_a_steady_lit_ring_with_no_driver()
    setPet(1, "Firebolt", true, true)
    setPet(2, "Attack", false, false)
    refreshPet()
    eq(#arcsOf(1), 16, "sixteen arcs")
    eq(shownArcs(1), 16, "all lit")
    local arc = arcsOf(1)[5]
    eq(arc._texture:find("pet_slot_ring_04.tga", 1, true) ~= nil, true, "arc 5 texture")
    eq(arc._vertex[4], 1, "steady alpha")
    eq(math.abs(arc._vertex[1] - 0.2) < 1e-6 and math.abs(arc._vertex[2] - 1) < 1e-6, true, "addon green")
    eq(arc:GetWidth(), 38, "ring box is the 30 button plus a 4 pad each side")
    eq(shownArcs(2), 0, "no ring where autocast is not allowed")
    eq(#onUpdateFrames(), 0, "no OnUpdate after a snap")
    eq(petButton(1)._attrs.type, "pet", "button untouched")
end

function T.pet_ring_allowed_but_off_is_a_steady_faint_ring()
    -- The approved mockup draws the faint unlit circle permanently while autocast is allowed but off.
    setPet(1, "Firebolt", true, false)
    refreshPet()
    eqArcs(1, FAINT, "allowed and off")
    local arc = arcsOf(1)[1]
    eq(math.abs(arc._vertex[1] - 0.2) < 1e-6 and math.abs(arc._vertex[2] - 1) < 1e-6, true, "addon green")
    eq(#onUpdateFrames(), 0, "a steady faint ring costs no frames")
    tick(2)
    eqArcs(1, FAINT, "still faint two seconds later")
end

function T.pet_ring_not_allowed_is_absent_even_when_enabled()
    -- First paint: allowed false with enabled true builds no ring at all.
    setPet(1, "Torment", false, true)
    refreshPet()
    eq(petButton(1).fsAutoCastRing, nil, "no ring built for a slot that cannot autocast")
    -- A lit ring whose same action stops being allowed goes straight to absent, no outage.
    setPet(2, "Firebolt", true, true); refreshPet()
    eq(shownArcs(2), 16, "lit first")
    setPet(2, "Firebolt", false, true); refreshPet()
    eq(#onUpdateFrames(), 0, "no outage, no driver")
    eq(shownArcs(2), 0, "absent")
end

function T.pet_ring_turning_on_ignites_then_the_driver_goes_away()
    setPet(1, "Firebolt", true, false); refreshPet()
    eqArcs(1, FAINT, "off is the faint ring")
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 1, "one driver while igniting")
    tick(0.05)
    eq(shownArcs(1), 16, "the ring is up while it ignites")
    tick(0.5)
    eq(#onUpdateFrames(), 0, "driver removed once the ignite settles")
    eqArcs(1, 1, "steady lit")
end

function T.pet_ring_turning_off_runs_the_outage_then_ends_on_the_faint_ring()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, "Firebolt", true, false); refreshPet()
    eq(#onUpdateFrames(), 1, "driver for the outage")
    tick(0.5)
    eq(#onUpdateFrames(), 1, "still running mid outage")
    eq(shownArcs(1) > 0, true, "ring still up mid outage")
    tick(0.6)
    eq(#onUpdateFrames(), 0, "driver removed after the 1.0 s outage")
    eqArcs(1, FAINT, "the outage ends on the faint ring, not on nothing")
end

function T.pet_ring_first_paint_of_ten_enabled_buttons_installs_no_driver()
    for i = 1, 10 do setPet(i, "Spell" .. i, true, true) end
    refreshPet()
    eq(#onUpdateFrames(), 0, "no ignite storm")
    for i = 1, 10 do eq(shownArcs(i), 16, "button " .. i .. " lit") end
end

function T.pet_ring_a_new_pet_snaps_instead_of_burning_out()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, nil, nil, nil); refreshPet()          -- dismissed
    eq(#onUpdateFrames(), 0, "no outage for a dismissed pet")
    eq(shownArcs(1), 0, "ring gone")
    setPet(1, "Torment", true, true); refreshPet()  -- another pet, another action in the slot
    eq(#onUpdateFrames(), 0, "no ignite for a summoned pet")
    eq(shownArcs(1), 16, "lit at once")
end

function T.pet_ring_a_dismissed_pet_mid_animation_removes_the_driver()
    setPet(1, "Firebolt", true, true)
    setPet(2, "Torment", true, false)
    refreshPet()
    setPet(1, "Firebolt", true, false)     -- slot 1 starts its outage
    setPet(2, "Torment", true, true)       -- slot 2 starts igniting
    refreshPet()
    eq(#onUpdateFrames(), 1, "both animating on one driver")
    tick(0.1)
    setPet(1, nil, nil, nil)
    setPet(2, nil, nil, nil)
    refreshPet()
    tick(0.016)                          -- the driver clears itself on its next frame
    eq(#onUpdateFrames(), 0, "driver removed")
    eq(shownArcs(1), 0, "outage ring snapped away")
    eq(shownArcs(2), 0, "igniting ring snapped away")
    tick(0.5)
    eq(shownArcs(1) + shownArcs(2), 0, "nothing comes back")
end

function T.pet_ring_a_button_that_is_not_visible_snaps()
    setPet(1, "Firebolt", true, false); refreshPet()
    petButton(1):Hide()
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 0, "an invisible button never animates")
    eqArcs(1, 1, "lit at once")
    setPet(1, "Firebolt", true, false); refreshPet()
    eq(#onUpdateFrames(), 0, "nor does it burn out")
    eqArcs(1, FAINT, "faint at once")
end

function T.pet_ring_a_button_hidden_mid_animation_snaps()
    setPet(1, "Firebolt", true, false); refreshPet()
    setPet(1, "Firebolt", true, true); refreshPet()
    tick(0.05)
    eq(#onUpdateFrames(), 1, "igniting")
    petButton(1):Hide()
    refreshPet()
    tick(0.016)                          -- the driver clears itself on its next frame
    eq(#onUpdateFrames(), 0, "driver removed once the button is hidden")
    eqArcs(1, 1, "ignite snapped to steady lit")
    petButton(1):Show()
    setPet(1, "Firebolt", true, false); refreshPet()
    tick(0.05)
    eq(#onUpdateFrames(), 1, "burning out")
    petButton(1):Hide()
    refreshPet()
    tick(0.016)
    eq(#onUpdateFrames(), 0, "driver removed")
    eqArcs(1, FAINT, "outage snapped to the faint ring")
end

function T.pet_ring_a_repeat_update_mid_animation_does_not_restart()
    setPet(1, "Firebolt", true, false); refreshPet()
    setPet(1, "Firebolt", true, true); refreshPet()
    local ring = petButton(1).fsAutoCastRing
    local t0 = ring.t0
    tick(0.1)
    refreshPet()                         -- PET_BAR_UPDATE fires again mid ignite
    eq(ring.t0, t0, "the ignite clock is not reset")
    eq(ring.phase, "on", "still igniting")
    eq(#onUpdateFrames(), 1, "one driver")
    tick(0.6)
    setPet(1, "Firebolt", true, false); refreshPet()
    t0 = ring.t0
    tick(0.3)
    refreshPet()                         -- and again mid outage
    eq(ring.t0, t0, "the outage clock is not reset")
    eq(ring.phase, "outage", "still in the outage")
    tick(0.8)
    eq(#onUpdateFrames(), 0, "the outage ends on its original schedule")
    eqArcs(1, FAINT, "faint")
end

function T.pet_ring_reduced_motion_snaps()
    ForeverSTUwaveDB = { reducedMotion = true }
    setPet(1, "Firebolt", true, false); refreshPet()
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 0, "no ignite under reduced motion")
    eqArcs(1, 1, "lit at once")
    setPet(1, "Firebolt", true, false); refreshPet()
    eq(#onUpdateFrames(), 0, "no outage under reduced motion")
    eqArcs(1, FAINT, "faint at once")
end

function T.pet_ring_host_is_click_through_above_the_swipe_and_below_the_hotkey()
    setPet(1, "Firebolt", true, true); refreshPet()
    local button = petButton(1)
    local host = button.fsAutoCastRing.host
    eq(host._mouse, false, "the ring host never takes the mouse")
    eq(host:GetParent(), button, "child of the button")
    eq(host:GetFrameLevel() > button.cooldown:GetFrameLevel(), true, "above the cooldown swipe")
    eq(button.fsTextHost:GetFrameLevel() > host:GetFrameLevel(), true, "below the hotkey text host")
end

function T.pet_ring_a_resize_reseats_the_arcs()
    setPet(1, "Firebolt", true, true)
    setPet(2, "Torment", true, false)
    refreshPet()
    eq(arcsOf(1)[1]:GetWidth(), 38, "ring box at scale 1")
    __rescale(2)
    eq(petButton(1):GetWidth(), 60, "the button follows the scale")
    eq(arcsOf(1)[1]:GetWidth(), 76, "the lit ring follows the button")
    eq(arcsOf(2)[16]:GetWidth(), 76, "so does the faint one")
end

function T.pet_ring_secret_allowed_keeps_the_last_look_and_builds_nothing()
    setPet(1, "Firebolt", true, true)
    refreshPet()
    setPet(1, "Firebolt", __SECRET, false); refreshPet()
    eq(#onUpdateFrames(), 0, "never animates on unknown")
    eqArcs(1, 1, "keeps the last look")
    setPet(2, "Torment", __SECRET, true); refreshPet()
    eq(petButton(2).fsAutoCastRing, nil, "no ring is built from an unknown state")
end

function T.pet_ring_secret_enabled_keeps_the_last_look_and_the_next_read_snaps()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, "Firebolt", true, __SECRET); refreshPet()
    eq(#onUpdateFrames(), 0, "never animates on unknown")
    eqArcs(1, 1, "keeps the last look")
    -- The slot was not read, so a stale same-name read must not be taken for a real transition.
    setPet(1, "Firebolt", true, false); refreshPet()
    eq(#onUpdateFrames(), 0, "the read after a secret one snaps")
    eqArcs(1, FAINT, "faint at once")
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 1, "the next plain read of the same action animates again")
end

function T.pet_ring_a_secret_name_resets_the_slot_and_the_next_read_snaps()
    setPet(1, "Firebolt", true, true); refreshPet()
    eqArcs(1, 1, "lit")
    setPet(1, __SECRET, true, false); refreshPet()
    eq(petButton(1).fsAutoCastName, nil, "an unreadable name forgets the slot's action")
    eq(#onUpdateFrames(), 0, "no outage from a name that could not be read")
    eqArcs(1, FAINT, "snapped to the faint ring")
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 0, "the read after it snaps too")
    eqArcs(1, 1, "lit at once")
end

function T.pet_ring_allowed_flipping_on_the_same_action_snaps()
    setPet(1, "Firebolt", true, true); refreshPet()
    eqArcs(1, 1, "lit")
    setPet(1, "Firebolt", false, false); refreshPet()
    eq(shownArcs(1), 0, "not allowed: absent")
    eq(#onUpdateFrames(), 0, "no outage when the action stops being allowed")
    setPet(1, "Firebolt", true, false); refreshPet()
    eq(#onUpdateFrames(), 0, "allowed again snaps, no driver")
    eqArcs(1, FAINT, "faint")
    setPet(1, "Firebolt", false, false); refreshPet()
    setPet(1, "Firebolt", true, true); refreshPet()
    eq(#onUpdateFrames(), 0, "allowed and on snaps, never ignites")
    eqArcs(1, 1, "lit")
end

function T.pet_ring_allowed_dropping_mid_outage_removes_the_driver()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, "Firebolt", true, false); refreshPet()
    tick(0.1)
    eq(#onUpdateFrames(), 1, "burning out")
    setPet(1, "Firebolt", false, false); refreshPet()   -- same action, no longer allowed
    tick(0.016)
    eq(#onUpdateFrames(), 0, "driver gone")
    eq(shownArcs(1), 0, "ring absent")
    tick(1)
    eq(shownArcs(1), 0, "and it stays absent")
end

function T.pet_ring_losing_fx_mid_outage_snaps_the_ring_steady_and_stops_the_driver()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, "Firebolt", true, false); refreshPet()
    tick(0.1)
    eq(#onUpdateFrames(), 1, "burning out")
    FS.ChevronCastBar.Fx = nil
    tick(0.016)
    eq(#onUpdateFrames(), 0, "driver gone")
    eq(petButton(1).fsAutoCastRing.phase, "off", "the outage ring is off, not stuck mid outage")
    eqArcs(1, FAINT, "snapped to the steady faint ring")
    tick(1)
    eqArcs(1, FAINT, "and it stays there")
end

function T.pet_ring_secret_read_mid_outage_starts_nothing_and_the_outage_ends_steady()
    setPet(1, "Firebolt", true, true); refreshPet()
    setPet(1, "Firebolt", true, false); refreshPet()
    local ring = petButton(1).fsAutoCastRing
    local t0 = ring.t0
    tick(0.3)
    setPet(1, "Firebolt", true, __SECRET); refreshPet()
    eq(ring.t0, t0, "the secret read does not restart the clock")
    eq(ring.phase, "outage", "the running outage is untouched")
    eq(#onUpdateFrames(), 1, "the running outage keeps its one driver")
    tick(0.8)
    eq(#onUpdateFrames(), 0, "the outage finished")
    eqArcs(1, FAINT, "and ended on the faint ring")
end

function T.pet_ring_never_builds_in_combat_and_the_deferred_build_snaps()
    __combat = true
    setPet(1, "Firebolt", true, true); refreshPet()   -- a pet summoned mid fight
    eq(petButton(1).fsAutoCastRing, nil, "no ring is built in combat")
    eq(__protectedTouch, 0, "nothing was created or anchored under the secure button")
    eq(#onUpdateFrames(), 0, "no driver")
    __combat = false
    __fire_event("PLAYER_REGEN_ENABLED")
    eqArcs(1, 1, "built after combat, lit")
    eq(#onUpdateFrames(), 0, "the deferred build snaps, it does not ignite")
end

-- ---- Blizzard's own bars (see BLIZZ_PRELUDE) ------------------------------
local BLIZZ_BARS = {
    "MainActionBar", "MultiBarBottomLeft", "MultiBarBottomRight", "MultiBarRight",
    "MultiBarLeft", "MultiBar5", "MultiBar6", "MultiBar7", "OverrideActionBar",
}

local function stockButtons(name)
    local out = {}
    for _, b in ipairs(__blizz.buttons[name]) do out[#out + 1] = b end
    return out
end

-- The live bug (2026-10-03): the shipped default "stash" ran Blizzard's own HideOverride and
-- the OnHide cascade into every stock button under OUR taint, and the hidden MultiBarBottomLeft
-- button then threw "Secret values are only allowed during untainted execution" in combat.
-- No Hide, SetParent, SetScript or HookScript may reach a Blizzard bar or any of its buttons.
function T.blizz_default_hide_is_dim_and_runs_no_blizzard_script()
    for _, name in ipairs(BLIZZ_BARS) do
        local bar = _G[name]
        eq(bar._alpha, 0, name .. " dimmed")
        eq(bar:IsShown(), true, name .. " still shown (Hide would run Blizzard's HideOverride)")
        eq(bar:GetParent(), UIParent, name .. " still where Blizzard put it")
    end
    for k, v in pairs(__blizz.calls) do error("Blizzard frame touched: " .. k .. " x" .. v) end
end

-- The bar's own children are the ActionBarButtonContainerN frames, NOT the buttons, so a bar
-- sweep alone leaves the real buttons clickable at alpha 0 over our own.
function T.blizz_dim_reaches_the_stock_buttons_not_only_the_containers()
    for _, name in ipairs(BLIZZ_BARS) do
        local buttons = stockButtons(name)
        eq(#buttons, 3, name .. " fixture")
        for i, b in ipairs(buttons) do
            eq(b._mouse, false, name .. " button " .. i .. " mouse")
            eq(b._alpha, 0, name .. " button " .. i .. " alpha")
        end
    end
    -- A button reachable ONLY through the bar's actionButtons table (parented elsewhere, so
    -- GetChildren never sees it) must be dimmed too.
    for _, name in ipairs(BLIZZ_BARS) do
        local o = __blizz.orphans[name]
        if o then
            eq(o._alpha, 0, name .. " actionButtons-only button alpha")
            eq(o._mouse, false, name .. " actionButtons-only button mouse")
        end
    end
    eq(_G.StanceBar._alpha, 0, "stance bar dimmed")
    for i, b in ipairs(stockButtons("StanceBar")) do
        eq(b._mouse, false, "stance button " .. i .. " mouse")
    end
end

-- The perspective grid: FSActionGrid shows only while actionbars.grid is on AND the bars are ours.
function T.grid_is_shown_by_default()
    local g = _G.FSActionGrid
    eq(g ~= nil, true, "grid frame built")
    eq(g:IsShown(), true, "shown by default")
    eq(FS.Config.Get("actionbars.grid"), true, "default is on")
end

function T.grid_turning_the_key_off_hides_it_and_on_shows_it_again()
    local g = _G.FSActionGrid
    FS.Config.Set("actionbars.grid", false)
    eq(g:IsShown(), false, "hidden at once")
    FS.Config.Set("actionbars.grid", true)
    eq(g:IsShown(), true, "shown again")
    __combat = true
    FS.Config.Set("actionbars.grid", false)
    eq(g:IsShown(), false, "also hidden in combat")
    __combat = false
end

function T.grid_fsbars_blizz_still_hides_it_whatever_the_key_says()
    local g = _G.FSActionGrid
    SlashCmdList["FSBARS"]("blizz")
    eq(g:IsShown(), false, "hidden by blizz")
    FS.Config.Set("actionbars.grid", false)
    FS.Config.Set("actionbars.grid", true)
    eq(g:IsShown(), false, "the key being on does not beat /fsbars blizz")
    SlashCmdList["FSBARS"]("fs")
    eq(g:IsShown(), true, "/fsbars fs with the key on brings it back")
end

function T.grid_fsbars_fs_honours_a_key_that_is_off()
    local g = _G.FSActionGrid
    FS.Config.Set("actionbars.grid", false)
    SlashCmdList["FSBARS"]("blizz")
    SlashCmdList["FSBARS"]("fs")
    eq(g:IsShown(), false, "fs mode with the grid off keeps it hidden")
    FS.Config.Set("actionbars.grid", true)
    eq(g:IsShown(), true, "and turning it on shows it")
end

function T.grid_a_profile_switch_applies_the_new_profiles_value()
    local g = _G.FSActionGrid
    FS.Config.SetActiveProfile("Other")
    FS.Config.Set("actionbars.grid", false)
    eq(g:IsShown(), false, "Other hides it")
    FS.Config.SetActiveProfile("Default")
    eq(g:IsShown(), true, "Default shows it again")
    FS.Config.SetActiveProfile("Other")
    eq(g:IsShown(), false, "switching back hides it")
end

function T.grid_look_is_unchanged()
    local g = _G.FSActionGrid
    eq(g._strata, "BACKGROUND", "strata unchanged")
    eq(g._mouse, false, "still click-through")
    eq(g:GetWidth(), UIParent:GetWidth(), "edge to edge")
    eq(g:GetHeight(), 183, "layout height")
    eq(g.fsTexture._texture, "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\grid.tga", "texture")
end

-- ActionBarButtonEventsFrame.frames is what the dispatcher iterates; other Blizzard systems
-- read it too, so a write from addon code taints them. Leave the hidden stock buttons updating.
function T.blizz_event_dispatch_frames_are_never_written()
    for _, name in ipairs({ "ActionBarButtonEventsFrame", "ActionBarActionEventsFrame" }) do
        local f = _G[name]
        local snap = __blizz.snapshot[name]
        eq(f.frames, snap.proxy, name .. ".frames replaced wholesale")
        eq(__blizz.writes[name], 0, name .. ".frames written (assignment or overwrite)")
        eq(#snap.store, #snap.items, name .. ".frames length changed")
        for i, item in ipairs(snap.items) do eq(snap.store[i], item, name .. ".frames[" .. i .. "] changed") end
        eq(f._registered["ACTIONBAR_UPDATE_COOLDOWN"], true, name .. " keeps its events")
        eq(__blizz.calls[name .. ":UnregisterAllEvents"], nil, name .. " unregistered")
        eq(__blizz.calls[name .. ":SetScript"], nil, name .. " script replaced")
        eq(__blizz.calls[name .. ":HookScript"], nil, name .. " script hooked")
    end
end

-- Silencing the bar's own events was justified by a false claim (stock buttons never register
-- events; the dispatcher drives them) and /fsbars blizz never re-registered them.
function T.blizz_bars_keep_their_own_events()
    for _, name in ipairs(BLIZZ_BARS) do
        eq(_G[name]._registered["PLAYER_REGEN_ENABLED"], true, name .. " own events")
    end
end

function T.blizz_fsbars_blizz_restores_a_dimmed_bar()
    SlashCmdList["FSBARS"]("blizz")
    for _, name in ipairs(BLIZZ_BARS) do
        eq(_G[name]._alpha, 1, name .. " alpha restored")
        for i, b in ipairs(stockButtons(name)) do
            eq(b._alpha, 1, name .. " button " .. i .. " alpha restored")
            eq(b._mouse, true, name .. " button " .. i .. " mouse restored")
        end
        local o = __blizz.orphans[name]
        if o then
            eq(o._alpha, 1, name .. " actionButtons-only button alpha restored")
            eq(o._mouse, true, name .. " actionButtons-only button mouse restored")
        end
    end
    SlashCmdList["FSBARS"]("fs")
    eq(MultiBarBottomLeft._alpha, 0, "dimmed again")
end

-- `stash` stays an explicit experiment toggle: a save that chose it keeps getting it.
function T.blizz_saved_stash_is_still_honoured()
    eq(MultiBarBottomLeft:GetParent() ~= UIParent, true, "reparented")
    eq(MultiBarBottomLeft:IsShown(), false, "hidden")
end

function T.blizz_login_in_combat_leaves_blizzard_bars_alone()
    for _, name in ipairs(BLIZZ_BARS) do eq(_G[name]._alpha, 1, name) end
end

-- Forms arrive after PLAYER_LOGIN, so the stock bar can gain buttons the login sweep never saw: the
-- sweep runs again with every rebuild instead of leaving them clickable.
function T.blizz_stance_rebuild_dims_stock_buttons_the_bar_gained_late()
    local container = CreateFrame("Frame", nil, StanceBar)
    container:EnableMouse(true)
    local late = CreateFrame("CheckButton", nil, container)
    late:EnableMouse(true)
    __fire_event("UPDATE_SHAPESHIFT_FORMS")
    eq(late._alpha, 0, "late stock button dimmed")
    eq(late._mouse, false, "and click-through")
    eq(__blizz.calls["StanceBar:Hide"], nil, "still no Hide on the Edit Mode bar")
    eq(__blizz.calls["StanceBar:SetScript"], nil)
    eq(__blizz.calls["StanceBar:HookScript"], nil)
end

function T.blizz_stance_bar_dim_runs_no_blizzard_script()
    eq(StanceBar:IsShown(), true, "not hidden (StanceBar is an Edit Mode system with a HideOverride)")
    eq(__blizz.calls["StanceBar:Hide"], nil, "Hide")
    eq(__blizz.calls["StanceBar:HookScript"], nil, "HookScript")
    eq(__blizz.calls["StanceBar:SetScript"], nil, "SetScript")
end

__checks = T
"""


# Checks that need a different client: name -> Lua run before the addon loads.
PRESS_HOOKS = """
    function ActionButtonDown() end
    function ActionButtonUp() end
    function MultiActionButtonDown() end
    function MultiActionButtonUp() end
    function hooksecurefunc(name, fn)
        local orig = _G[name]
        _G[name] = function(...) orig(...); fn(...) end
    end
"""
# First read of the form info at login hands back no spell id; C_Timer.After is queued so a check runs it.
STANCE_NO_SPELL = """
    __missingSpell = true
    function GetShapeshiftFormInfo(i) return "tex", i == 1, true, (not __missingSpell) and 100 + i or nil end
    __timers = {}
    C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
    function __runTimers()
        local run = __timers
        __timers = {}
        for _, fn in ipairs(run) do fn() end
    end
"""
# A recorded OnRescale list, so a check can fire a UI scale change at the stance bar.
STANCE_RESCALE = """
    __rescaleFns = {}
    FS.Layout.OnRescale = function(fn) __rescaleFns[#__rescaleFns + 1] = fn end
"""

# Counting stand-ins for the two calls that allocate per button, installed before the addon loads.
COUNT_APIS = """
    __cdAsked, __keyAsked = 0, 0
    C_ActionBar.GetActionCooldownDuration = function() __cdAsked = __cdAsked + 1; return { duration = true } end
    local realGetBindingKey = GetBindingKey
    GetBindingKey = function(action) __keyAsked = __keyAsked + 1; return realGetBindingKey(action) end
"""

# A live MainActionBar, as Blizzard builds it: an insecure bar whose "actionpage" attribute the
# ActionBarController rewrites. __attrWrites counts every SetAttribute our secure buttons receive;
# __calcAction is SecureActionButtonMixin:CalculateAction (SecureTemplates.lua:670-686) with the
# useparent-<name> / frame.bar walk of SecureButton_GetModifiedAttribute (:127-132); C_Timer.After
# queues until __flushTimers (the next frame).
LIVE_BAR = """
MainActionBar = CreateFrame("Frame", "MainActionBar", UIParent)
__attrWrites = 0
do
    local real = __Region.SetAttribute
    function __Region:SetAttribute(k, v)
        if self._secure then __attrWrites = __attrWrites + 1 end
        return real(self, k, v)
    end
end
do
    local realSetID = __Region.SetID
    function __Region:SetID(id)
        if self._secure then __attrWrites = __attrWrites + 1 end
        return realSetID(self, id)
    end
end
C_ActionBar.GetActionBarPage = function() return 1 end
-- The skinned vehicle / override surface: the controller gives OverrideActionBar its own
-- "actionpage" and reports LE_ACTIONBAR_STATE_OVERRIDE (ActionBarController.lua:149-157).
OverrideActionBar = CreateFrame("Frame", "OverrideActionBar", UIParent)
LE_ACTIONBAR_STATE_MAIN, LE_ACTIONBAR_STATE_OVERRIDE = 1, 2
__barState = LE_ACTIONBAR_STATE_MAIN
function ActionBarController_GetCurrentActionBarState() return __barState end
-- BaseActionButtonMixin:UpdateFlyout stand-in: counts calls, and those made in combat.
__flyoutInCombat = 0
function __Region:UpdateFlyout()
    if __combat then __flyoutInCombat = __flyoutInCombat + 1 end
    self._flyouts = (self._flyouts or 0) + 1
end
__timers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
function __flushTimers()
    local run = __timers
    __timers = {}
    for _, fn in ipairs(run) do fn() end
end
local function modifiedAttribute(frame, name)
    local value = frame:GetAttribute(name)
    if value == nil and frame:GetAttribute("useparent-" .. name) then
        local parent = frame.bar or frame:GetParent()
        if parent then value = modifiedAttribute(parent, name) end
    end
    return value
end
function __calcAction(self)
    if self:GetID() > 0 then
        local page = modifiedAttribute(self, "actionpage")
        if not page then page = C_ActionBar.GetActionBarPage() end
        return self:GetID() + (page - 1) * 12
    end
    return modifiedAttribute(self, "action") or 1
end
"""

VARIANTS = {
    "paged_buttons_carry_an_id_and_follow_mainactionbars_page_by_attribute": LIVE_BAR,
    "fixed_bars_keep_their_attribute_slots": LIVE_BAR,
    "paged_bonus_page_change_in_combat_writes_nothing_and_the_visuals_follow": LIVE_BAR,
    "paged_page_is_read_again_on_the_next_frame_without_stacking": LIVE_BAR,
    "paged_next_frame_reread_in_combat_writes_nothing": LIVE_BAR,
    "paged_click_resolves_to_the_live_page_in_combat": LIVE_BAR,
    "paged_page_falls_back_to_the_clients_page_like_calculateaction_when_the_attribute_is_unset": LIVE_BAR,
    "skinned_vehicle_or_override_bar_moves_the_click_host_to_overrideactionbar": LIVE_BAR,
    "skinned_override_entered_in_combat_swaps_the_click_host_at_once": LIVE_BAR,
    "skinned_override_left_in_combat_swaps_the_click_host_back_at_once": LIVE_BAR,
    "entering_world_reads_the_live_page": LIVE_BAR,
    "paged_slot_change_refreshes_the_flyout_out_of_combat_and_at_regen": LIVE_BAR,
    "bar6_first_slot_follows_the_clients_multibar5_page": "MULTIBAR_5_ACTIONBAR_PAGE = 15",
    "gcd_swipe_is_asked_for_with_the_gcd_included_and_applied": """
        __gcdSeen = {}
        C_ActionBar.GetActionCooldownDuration = function(slot, ignoreGCD)
            __gcdSeen[slot] = { ignore = ignoreGCD }
            return { gcd = true }
        end
    """,
    "idle_usable_and_state_events_skip_hotkeys_and_cooldown_objects": COUNT_APIS,
    "cooldown_refresh_skips_empty_slots": COUNT_APIS,
    "keybind_press_pushes_our_button_and_release_clears_it": PRESS_HOOKS,
    "keybind_press_is_released_when_the_release_never_arrives": PRESS_HOOKS,
    "keybind_press_survives_the_start_of_combat": PRESS_HOOKS,
    "keybind_release_sweep_leaves_a_hovered_button_alone": PRESS_HOOKS,
    "keybind_press_is_skipped_during_a_pet_battle": PRESS_HOOKS + """
        __petBattle = false
        C_PetBattles = { IsInBattle = function() return __petBattle end }
    """,
    "keybind_press_with_no_matching_button_does_not_throw": PRESS_HOOKS,
    "keybind_press_maps_every_blizzard_multibar_to_its_bar": PRESS_HOOKS,
    "stance_bar_hides_cleanly_for_a_paladin_with_no_forms": """
        function UnitClass() return "Paladin", "PALADIN", 2 end
        function GetNumShapeshiftForms() return 0 end
        __stancePrints = {}
        function print(...) local t = {} for i = 1, select("#", ...) do t[i] = tostring((select(i, ...))) end
            __stancePrints[#__stancePrints + 1] = table.concat(t, " ") end
    """,
    "stance_a_throw_while_styling_does_not_leak_the_frame_or_double_the_hooks": """
        __sizeThrown = false
        local realSetSize = __Region.SetSize
        function __Region:SetSize(...)
            if self._name == "FSStanceButton3" and not __sizeThrown then
                __sizeThrown = true
                error("SetSize failed")
            end
            return realSetSize(self, ...)
        end
    """,
    "stance_missing_spell_id_at_login_is_not_reported_when_a_later_read_supplies_it": STANCE_NO_SPELL,
    "stance_missing_spell_id_is_reported_once_if_it_stays_missing": STANCE_NO_SPELL,
    "stance_rescale_in_combat_touches_no_protected_frame_and_resizes_after": STANCE_RESCALE,
    "mouseover_attributes_are_never_written_in_combat": "__combat = true",
    "mouseover_hint_stays_quiet_once_seen": "ForeverSTUwaveDB = { mouseoverHintSeen = true }",
    "mouseover_hint_stays_quiet_when_the_cvar_is_on": '__cvars.enableMouseoverCast = "1"',
    "action_swipe_stays_square_without_mask_support": "__Region.AddMaskTexture = nil",
    # The mock's default AddMaskTexture already records and does not clip, i.e. the
    # shipped client's behaviour; the variant spells it out so the check survives a
    # change of default.
    "cut_icon_is_inset_only_when_mask_apis_exist_but_do_not_clip":
        "__Region.AddMaskTexture = function(self, m) self._maskedBy = m end",
}


# Blizzard's own bars, as the 12.1 reference builds them (ActionBarMixin:ActionBar_OnLoad): a bar
# whose children are ActionBarButtonContainerN frames, each holding one stock button, plus the
# bar's `actionButtons` table (plus one extra button listed there but parented elsewhere). Every method that would run Blizzard code (Hide is HideOverride on
# an Edit Mode bar) is wrapped to count, and the two event-dispatch frames count writes to their
# `frames` tables. OverrideActionBar has no actionButtons table: its buttons are direct children.
BLIZZ_PRELUDE = """
__blizz = { calls = {}, writes = {}, buttons = {}, orphans = {}, snapshot = {} }
local TRACKED = { "Hide", "Show", "SetParent", "SetScript", "HookScript", "UnregisterAllEvents" }
local function spy(f, label)
    for _, m in ipairs(TRACKED) do
        local base = __Region[m]
        f[m] = function(self, ...)
            local k = label .. ":" .. m
            __blizz.calls[k] = (__blizz.calls[k] or 0) + 1
            return base(self, ...)
        end
    end
end
local function stockButton(parent, name)
    local b = CreateFrame("CheckButton", name, parent)
    b:EnableMouse(true)
    return b
end
local names = { "MainActionBar", "MultiBarBottomLeft", "MultiBarBottomRight", "MultiBarRight",
    "MultiBarLeft", "MultiBar5", "MultiBar6", "MultiBar7", "OverrideActionBar", "StanceBar" }
local all = {}
for _, name in ipairs(names) do
    local bar = CreateFrame("Frame", name, UIParent)
    bar:RegisterEvent("PLAYER_REGEN_ENABLED")
    bar:EnableMouse(true)
    __blizz.buttons[name] = {}
    if name ~= "OverrideActionBar" then bar.actionButtons = {} end
    for i = 1, 3 do
        local parent = bar
        if name ~= "OverrideActionBar" then
            parent = CreateFrame("Frame", name .. "ButtonContainer" .. i, bar)
            parent:EnableMouse(true)
        end
        local b = stockButton(parent, name .. "Button" .. i)
        if bar.actionButtons then bar.actionButtons[i] = b end
        __blizz.buttons[name][i] = b
        if parent ~= bar then all[#all + 1] = { parent, name .. "ButtonContainer" .. i } end
        all[#all + 1] = { b, name .. "Button" .. i }
    end
    if bar.actionButtons then
        -- Listed in actionButtons but NOT a descendant of the bar: only that table reaches it.
        local o = stockButton(UIParent, name .. "OrphanButton")
        bar.actionButtons[4] = o
        __blizz.orphans[name] = o
        all[#all + 1] = { o, name .. "OrphanButton" }
    end
    all[#all + 1] = { bar, name }
end
-- The dispatchers: events registered, `frames` is the table Blizzard iterates.
for _, name in ipairs({ "ActionBarButtonEventsFrame", "ActionBarActionEventsFrame" }) do
    local f = CreateFrame("Frame", name, UIParent)
    f:RegisterEvent("ACTIONBAR_UPDATE_COOLDOWN")
    __blizz.writes[name] = 0
    -- A proxy: the real contents live in `store`, so the proxy stays empty and EVERY assignment
    -- to it (new key or overwrite of an existing one) reaches __newindex. Replacing f.frames
    -- itself is caught by comparing against the proxy identity.
    local store, items = {}, {}
    for i, b in ipairs(__blizz.buttons.MultiBarBottomLeft) do store[i] = b; items[i] = b end
    local proxy = setmetatable({}, {
        __index = store,
        __len = function() return #store end,
        __newindex = function() __blizz.writes[name] = __blizz.writes[name] + 1 end,
    })
    f.frames = proxy
    __blizz.snapshot[name] = { proxy = proxy, store = store, items = items }
    all[#all + 1] = { f, name }
end
-- Spy last, so building the fixture does not count.
for _, pair in ipairs(all) do spy(pair[1], pair[2]) end
"""
# Variants of the above: name -> Lua run after the prelude, before the addon loads.
BLIZZ_VARIANTS = {
    "blizz_saved_stash_is_still_honoured": 'ForeverSTUwaveDB = { barHideStrategy = "stash" }',
    "blizz_login_in_combat_leaves_blizzard_bars_alone": "__combat = true",
}
BLIZZ_PREFIX = "blizz_"


# Pet ring checks: 10 pet slots, a stepped clock, GetPetActionInfo read from __pet, a real IsVisible,
# and the real ChevronCastBar.lua (its Fx export) loaded after PetActionBar.lua.
PET_RING_PRELUDE = """
NUM_PET_ACTION_SLOTS = 10
__now = 100
function GetTime() return __now end
__pet = {}
-- A controllable scale and a recorded OnRescale list: __rescale(s) is a UI scale change.
__scale = 1
FS.Layout.Scale = function() return __scale end
__rescaleFns = {}
FS.Layout.OnRescale = function(fn) __rescaleFns[#__rescaleFns + 1] = fn end
function __rescale(s)
    __scale = s
    for _, fn in ipairs(__rescaleFns) do fn() end
end
function GetPetActionInfo(i)
    local p = __pet[i] or {}
    return p.name, "tex", false, p.active, p.allowed, p.enabled, 1, false, nil
end
function __Region:IsVisible()
    local f = self
    while f do
        if not f._shown then return false end
        f = f._parent
    end
    return true
end
"""
PET_RING_PREFIXES = ("pet_ring_", "pet_click_", "pet_style_", "pet_cooldown_")
# Pet checks that need a different client: name -> Lua appended to PET_RING_PRELUDE.
PET_VARIANTS = {
    "pet_click_attributes_are_never_written_in_combat": "__combat = true",
    "pet_style_a_cooldown_without_a_countdown_fontstring_still_builds": "__Region.GetCountdownFontString = nil",
    "pet_style_countdown_uses_a_named_font_object_when_the_client_has_one": """
__fontObjects = {}
function CreateFont(name)
    local fo = { _name = name }
    function fo:SetFont(path, size, flags) self._font = { path, size, flags }; return true end
    function fo:SetTextColor(r, g, b, a) self._color = { r, g, b, a } end
    __fontObjects[name] = fo
    return fo
end
function __Region:SetCountdownFont(name) self._countdownFontName = name end
""",
}


def main() -> int:
    lua = boot()
    lua.execute(CHECKS)
    names = sorted(k for k in lua.eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: state (combat flag, attributes, bindings)
        # must not leak between them, and a failure must not hide the rest.
        if name.startswith(BLIZZ_PREFIX):
            lua = boot(BLIZZ_PRELUDE + BLIZZ_VARIANTS.get(name, ""))
        elif name.startswith(PET_RING_PREFIXES):
            lua = boot(PET_RING_PRELUDE + PET_VARIANTS.get(name, ""), ("Core/ChevronCastBar.lua",))
        else:
            lua = boot(VARIANTS.get(name, ""))
        lua.execute(CHECKS)
        try:
            lua.eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
