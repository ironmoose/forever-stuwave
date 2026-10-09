#!/usr/bin/env python3
"""Runs the real Layout.lua, Config.lua and LayoutEdit.lua headless against a small mock WoW API.

LayoutEdit.lua is the /fsedit layout editor: one insecure handle per movable frame, dragged
instead of the (possibly secure) frame, with the drop written through FS.Layout.SetOverride.
These checks pin that:

  * /fsedit refuses in combat and while Blizzard Edit Mode is active, and combat entry
    leaves edit mode and drops an in-flight drag;
  * only ids with an applied frame get a handle, and a handle is an insecure
    FULLSCREEN_DIALOG frame on UIParent that is never anchored to the frame it covers;
  * a drop converts back to layout x/y for scaled CENTER entries and unscaled TOPLEFT
    entries at two UI scales and lands the frame on the same screen point;
  * snap, grid size, arrow and Shift+arrow nudges, Esc, right-click reset and reset all;
  * pet, chat and minimap special cases;
  * the Layout page registers when FS.ConfigWindow exists and is skipped cleanly when not;
  * a DONE panel shows only while editing, and DONE or Esc reopens the Layout page when the
    editor was entered from the config window, never after /fsedit, combat or Blizzard Edit Mode.

The three Lua files are the real ones; the frames are a recording mock with a tiny anchor
solver, NOT the real client. Keyboard propagation is a recorded call, not client behaviour.

    python3 tools/layoutedit-harness.py

Exit 0 = every check passed.
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

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
LAYOUT_FILE = ADDON / "Core/Layout.lua"
CONFIG_FILE = ADDON / "Core/Config.lua"
PETFRAME_FILE = ADDON / "Modules/Pet/PetFrame.lua"
EDIT_FILE = Path(os.environ.get("LAYOUTEDIT_LUA", ADDON / "Core/LayoutEdit.lua"))   # a mutant copy for mutation checks

MOCK = r"""
__combat = false
__blocked = 0
__frames = {}
__printed = {}
__errors = {}
__timers = {}
__moves = {}
__shift = false
__bliz = false
__blizTouched = 0

local function noop() end
local function fx(p) if p:find("LEFT") then return 0 elseif p:find("RIGHT") then return 1 end return 0.5 end
local function fy(p) if p:find("BOTTOM") then return 0 elseif p:find("TOP") then return 1 end return 0.5 end

-- Textures and font strings: record what the checks read, ignore the rest.
local Region = {}
local function fallback(class, k)
    local v = class[k]
    if v ~= nil then return v end
    -- Unknown methods are no-ops; data fields and Edit Mode's *Base originals stay absent.
    if type(k) == "string" and (k:sub(1, 1) == "_" or k:find("Base$")) then return nil end
    return noop
end
Region.__index = function(_, k) return fallback(Region, k) end
function Region:SetText(s) self._text = s end
function Region:GetText() return self._text end
function Region:SetColorTexture(r, g, b, a) self._color = { r, g, b, a } end
function Region:SetVertexColor(r, g, b, a) self._color = { r, g, b, a } end
local function newRegion() return setmetatable({}, Region) end

local Frame = {}
Frame.__index = function(_, k) return fallback(Frame, k) end
local function guarded(self)
    if __combat and self._protected then __blocked = __blocked + 1; return true end
end
function Frame:ClearAllPoints() if guarded(self) then return end; self._points = {} end
function Frame:SetPoint(point, rel, relPoint, x, y)
    if guarded(self) then return end
    self._points[#self._points + 1] = { point = point, rel = rel, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Frame:GetPoint(i)
    local p = self._points[i or 1]
    if not p then return end
    return p.point, p.rel, p.relPoint, p.x, p.y
end
function Frame:SetSize(w, h) if guarded(self) then return end; self._w, self._h = w, h end
function Frame:SetWidth(w) self._w = w end
function Frame:SetHeight(h) self._h = h end
function Frame:GetWidth() return self._w end
function Frame:GetHeight() return self._h end
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:UnregisterEvent(e) self._events[e] = nil end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:GetScript(k) return self._scripts[k] end
function Frame:IsProtected() return self._protected or false end
function Frame:Show() self._shown = true end
function Frame:Hide() self._shown = false end
function Frame:IsShown() return self._shown or false end
function Frame:SetFrameStrata(s) self._strata = s end
function Frame:GetFrameStrata() return self._strata end
function Frame:SetFrameLevel(l) self._level = l end
function Frame:GetFrameLevel() return self._level end
function Frame:EnableMouse(v) self._mouse = v and true or false end
function Frame:EnableKeyboard(v) self._keyboard = v and true or false end
function Frame:SetPropagateKeyboardInput(v) self._propagate = v end
function Frame:StartMoving() self._moving = true; __moves[self] = (__moves[self] or 0) + 1 end
function Frame:StopMovingOrSizing() self._moving = false end
function Frame:GetParent() return self._parent end
function Frame:CreateTexture() return newRegion() end
function Frame:CreateFontString() return newRegion() end
function Frame:GetEffectiveScale() return 1 end
-- Anchor solver: UIParent is the only anchor target a checked frame uses.
function Frame:_rect()
    if self == UIParent then return 0, 0, self._w, self._h end
    local p = self._points[1]
    if not (p and self._w and self._h) then return end
    local rel = p.rel or UIParent
    local rl, rb, rw, rh = rel:_rect()
    if not rl then return end
    local px = rl + rw * fx(p.relPoint) + p.x
    local py = rb + rh * fy(p.relPoint) + p.y
    return px - self._w * fx(p.point), py - self._h * fy(p.point), self._w, self._h
end
function Frame:GetLeft() local l = self:_rect(); return l end
function Frame:GetBottom() local _, b = self:_rect(); return b end
function Frame:GetRight() local l, _, w = self:_rect(); return l and l + w end
function Frame:GetTop() local _, b, _, h = self:_rect(); return b and b + h end
function Frame:GetCenter() local l, b, w, h = self:_rect(); if l then return l + w / 2, b + h / 2 end end

function CreateFrame(kind, _, parent, template)
    local f = setmetatable({ _points = {}, _events = {}, _scripts = {}, _parent = parent, _kind = kind, _template = template }, Frame)
    __frames[#__frames + 1] = f
    return f
end
function InCombatLockdown() return __combat end
function IsShiftKeyDown() return __shift end
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
-- Counts every state-changing call a frame receives, so a check can prove one was left alone.
for _, name in ipairs({ "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight", "Show", "Hide", "SetMovable",
        "EnableMouse", "EnableKeyboard", "StartMoving", "StopMovingOrSizing", "SetScript", "RegisterForDrag", "SetFrameStrata" }) do
    local orig = Frame[name] or noop
    Frame[name] = function(self, ...)
        self._touches = (self._touches or 0) + 1
        return orig(self, ...)
    end
end
function print(...) __printed[#__printed + 1] = table.concat({ ... }, " ") end
function __printedHas(text)
    for _, line in ipairs(__printed) do if line:find(text, 1, true) then return true end end
    return false
end
GameTooltip = {
    SetOwner = function(self, owner) self._owner = owner end,
    SetText = function(self, text) self._text = text end,
    Show = function(self) self._shown = true end,
    Hide = function(self) self._shown = false; self._text = nil end,
}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
SlashCmdList = {}

function __setScreen(height)
    UIParent._w, UIParent._h = height * 16 / 9, height
end
UIParent = CreateFrame()
__setScreen(1200)

function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
function geterrorhandler() return function(e) __errors[#__errors + 1] = tostring(e) end end

-- Blizzard_EditMode's manager: only its two documented members, and any call counts as touched.
EditModeManagerFrame = {
    IsEditModeActive = function() return __bliz end,
    EnterEditMode = function() __blizTouched = __blizTouched + 1 end,
}

__themed = { panels = {}, buttons = {}, fills = {} }
FS_THEME_STUB = {
    COLOR_POWER = { 0.133, 0.878, 1, 1 },
    ApplyMono = function() end,
    SkinPanel = function(frame) __themed.panels[#__themed.panels + 1] = frame end,
    SkinButton = function(button) __themed.buttons[#__themed.buttons + 1] = button end,
    AddCutSliceFill = function(frame)
        __themed.fills[#__themed.fills + 1] = frame
        return newRegion()
    end,
}
"""

SESSION = r"""
function(layoutSrc, configSrc, editSrc)
    __frames, __printed, __errors, __timers, __moves = { UIParent }, {}, {}, {}, {}
    __combat, __shift, __bliz, __blizTouched = false, false, false, 0
    __themed.panels, __themed.buttons, __themed.fills = {}, {}, {}
    GameTooltip._text, GameTooltip._shown, GameTooltip._owner = nil, false, nil
    SlashCmdList = {}
    ForeverSTUwaveDB = nil
    FS = { Theme = FS_THEME_STUB }
    assert(load(layoutSrc, "@Layout.lua"))("forever-stuwave", FS)
    assert(load(configSrc, "@Config.lua"))("forever-stuwave", FS)
    __fire("ADDON_LOADED", "forever-stuwave")
    __fire("PLAYER_LOGIN")
    __loadEdit = function() assert(load(editSrc, "@LayoutEdit.lua"))("forever-stuwave", FS) end
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, tol, msg)
    if a == nil or b == nil or math.abs(a - b) > (tol or 1e-6) then
        error((msg or "not near") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end

local function screen(height) __setScreen(height) end
local function seat(id, protected)
    local f = CreateFrame()
    f._protected = protected
    local L = FS.Layout[id]
    if L.noSize then f:SetSize(L.w, L.h) end
    FS.Layout.Apply(f, id)
    return f
end
local function edit() __loadEdit(); return FS.LayoutEdit end
local function frames() return FS.Config and ForeverSTUwaveDB.profiles.Default.layout.frames end
local function override(id) return ForeverSTUwaveDB.profiles.Default.layout.frames[id] end
local function overlay()
    for _, f in ipairs(__frames) do if f._keyboard then return f end end
end
local function key(k)
    local o = overlay()
    o._scripts.OnKeyDown(o, k)
    return o
end
-- A drag: the client has moved the handle by the time OnDragStop runs.
local function dragTo(id, point, relPoint, x, y)
    local h = FS.LayoutEdit.GetHandle(id)
    h._scripts.OnDragStart(h)
    h:ClearAllPoints()
    h:SetPoint(point, UIParent, relPoint, x, y)
    h._scripts.OnDragStop(h)
    return h
end
local function setSnap(on, grid)
    FS.Config.Set("layout.snap", on)
    if grid then FS.Config.Set("layout.grid", grid) end
end

-------------------------------------------------------------------------------
-- Entry and exit
-------------------------------------------------------------------------------

function T.snap_and_grid_defaults_are_registered()
    edit()
    eq(FS.Config.Get("layout.snap"), true)
    eq(FS.Config.Get("layout.grid"), 8)
end

function T.slash_toggles_edit_mode()
    edit()
    seat("stance")
    eq(type(SLASH_FSEDIT1), "string"); eq(SLASH_FSEDIT1, "/fsedit")
    SlashCmdList.FSEDIT("")
    eq(FS.LayoutEdit.IsEditing(), true)
    SlashCmdList.FSEDIT("")
    eq(FS.LayoutEdit.IsEditing(), false)
end

function T.it_refuses_to_start_in_combat_and_says_why()
    edit(); seat("stance")
    __combat = true
    eq(FS.LayoutEdit.Enter(), false)
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(__printedHas("combat"), true)
    eq(FS.LayoutEdit.GetHandle("stance"), nil, "no handle shown")
end

function T.it_refuses_to_start_while_blizzard_edit_mode_is_active()
    edit(); seat("stance")
    __bliz = true
    eq(FS.LayoutEdit.Enter(), false)
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(__printedHas("Edit Mode"), true)
end

function T.it_starts_when_blizzard_edit_mode_is_missing_entirely()
    EditModeManagerFrame = nil
    edit(); seat("stance")
    eq(FS.LayoutEdit.Enter(), true)
end

function T.combat_exits_edit_mode_and_drops_an_in_flight_drag()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnDragStart(h)
    eq(h._moving, true)
    __fire("PLAYER_REGEN_DISABLED")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(h._moving, false, "the drag was stopped")
    eq(next(frames()), nil, "and nothing was saved")
    eq(overlay(), nil, "the keyboard overlay is released")
    h._scripts.OnDragStop(h)
    eq(next(frames()), nil, "a stale drop after exit saves nothing")
end

function T.escape_leaves_edit_mode_and_is_consumed()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local o = overlay()
    o._scripts.OnKeyDown(o, "ESCAPE")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(o._propagate, false, "Esc is consumed")
end

-------------------------------------------------------------------------------
-- Handles
-------------------------------------------------------------------------------

function T.only_ids_with_an_applied_frame_get_a_handle()
    edit()
    seat("stance"); seat("player")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("stance") ~= nil, true)
    eq(FS.LayoutEdit.GetHandle("player") ~= nil, true)
    for _, id in ipairs({ "chat", "minimap", "buffs", "debuffs", "party", "focus", "boss", "action", "professions", "petcontainer", "target" }) do
        eq(FS.LayoutEdit.GetHandle(id), nil, id .. " has no frame")
    end
end

function T.every_movable_id_gets_a_handle_when_applied()
    edit()
    local ids = { "player", "target", "chat", "minimap", "buffs", "debuffs", "party", "focus", "boss", "stance", "action", "professions", "petcontainer" }
    for _, id in ipairs(ids) do seat(id) end
    FS.LayoutEdit.Enter()
    local labels = {}
    for _, id in ipairs(ids) do
        local h = FS.LayoutEdit.GetHandle(id)
        eq(h ~= nil, true, id)
        labels[id] = h.label._text
    end
    eq(labels.player, "Player frame"); eq(labels.target, "Target frame"); eq(labels.chat, "Chat")
    eq(labels.minimap, "Minimap"); eq(labels.buffs, "Buffs"); eq(labels.debuffs, "Debuffs")
    eq(labels.party, "Party"); eq(labels.focus, "Focus"); eq(labels.boss, "Boss")
    eq(labels.stance, "Stance bar"); eq(labels.action, "Action bars"); eq(labels.professions, "Professions")
    eq(labels.petcontainer, "Pet")
end

function T.the_tooltip_anchor_gets_a_handle_labelled_tooltip_and_resets_with_the_rest()
    edit()
    local f = seat("tooltip")
    setSnap(false)
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("tooltip")
    eq(h ~= nil, true, "tooltip has a handle")
    eq(h.label._text, "Tooltip")
    near(h:GetWidth(), FS.Layout.tooltip.w, 1e-6, "unscaled size")
    near(h:GetRight(), UIParent._w - 9, 1e-6, "handle on the corner seat")
    local startX, startY = FS.Layout.tooltip.x, FS.Layout.tooltip.y
    dragTo("tooltip", "BOTTOMRIGHT", "BOTTOMRIGHT", -100, 120)
    eq(override("tooltip").x, -100, "the drop round-trips in the seat's own units")
    eq(override("tooltip").y, 120)
    near(f:GetRight(), UIParent._w - 100, 1e-6, "the frame landed on the dropped point")
    near(f:GetBottom(), 120, 1e-6)
    h._scripts.OnMouseUp(h, "RightButton")
    eq(override("tooltip"), nil, "right-click resets it")
    eq(FS.Layout.tooltip.x, startX); eq(FS.Layout.tooltip.y, startY)
    near(f:GetRight(), UIParent._w - 9, 1e-6, "back on the corner")
    dragTo("tooltip", "BOTTOMRIGHT", "BOTTOMRIGHT", -100, 120)
    FS.LayoutEdit.ResetAll()
    eq(override("tooltip"), nil, "reset all covers it")
end

function T.the_stack_a_cast_bars_are_movable_only_while_they_are_the_display()
    edit()
    seat("pcast"); seat("tcast")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("pcast").label._text, "Player cast bar")
    eq(FS.LayoutEdit.GetHandle("tcast").label._text, "Target cast bar")
    FS.LayoutEdit.Exit()
    FS.CastBars = { IsStackActive = function() return false end }
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("pcast"), nil, "Gunsight tapes up: Stack A is hidden, so no handle")
    eq(FS.LayoutEdit.GetHandle("tcast"), nil)
    FS.CastBars = nil
end

function T.the_cast_bar_handles_follow_the_gunsight_switch_while_the_editor_is_open()
    local active, notify = false, nil
    FS.Gunsight = { OnActiveChanged = function(fn) notify = fn end }
    FS.CastBars = { IsStackActive = function() return not active end }
    seat("pcast"); seat("tcast")
    edit()
    eq(notify ~= nil, true, "LayoutEdit listens for the switch")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("pcast") ~= nil, true, "Stack A is the display: movable")
    FS.LayoutEdit.Select("pcast")
    active = true                                  -- the Gunsight HUD takes the casts while /fsedit is open
    notify(true)
    eq(FS.LayoutEdit.GetHandle("pcast"), nil, "the tapes are up: nothing to move, the handle goes")
    eq(FS.LayoutEdit.GetHandle("tcast"), nil)
    eq(FS.LayoutEdit.IsEditing(), true, "the editor itself stays open")
    FS.LayoutEdit.Nudge(1, 0)                      -- nothing selected any more: no throw, no write
    eq(override("pcast"), nil, "a nudge writes nothing for the gone handle")
    active = false
    notify(false)
    eq(FS.LayoutEdit.GetHandle("pcast") ~= nil, true, "Stack A back: the handle returns")
    eq(FS.LayoutEdit.GetHandle("tcast") ~= nil, true)
    eq(#FS.LayoutEdit.GetHandle("pcast")._points > 0, true, "and it is seated")
end

function T.the_gunsight_switch_does_nothing_to_the_handles_when_the_editor_is_closed()
    local active, notify = false, nil
    FS.Gunsight = { OnActiveChanged = function(fn) notify = fn end }
    FS.CastBars = { IsStackActive = function() return not active end }
    seat("pcast")
    edit()
    notify(false)
    eq(FS.LayoutEdit.GetHandle("pcast"), nil, "no handle is made while the editor is closed")
    eq(FS.LayoutEdit.IsEditing(), false)
end

function T.a_handle_is_an_insecure_fullscreen_dialog_frame_on_uiparent_never_anchored_to_the_frame()
    edit()
    local f = seat("stance", true)
    local touched = f._touches
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    eq(h._parent, UIParent); eq(h._strata, "FULLSCREEN_DIALOG"); eq(h._mouse, true)
    eq(h._kind, "Frame"); eq(h._template, nil, "a plain frame: no secure template")
    eq(#h._points, 1)
    eq(h._points[1].rel, UIParent, "positioned from layout coords, not from the secure frame")
    eq(h:IsShown(), true)
    eq(f._touches, touched, "entering edit mode calls nothing on the covered frame")
end

function T.handles_sit_on_the_layout_rect_at_two_ui_scales()
    for _, height in ipairs({ 1200, 768 }) do
        screen(height)
        __session(__layoutSrc, __configSrc, __editSrc)
        edit()
        local s = FS.Layout.Scale()
        seat("stance"); seat("player")
        FS.LayoutEdit.Enter()
        local h = FS.LayoutEdit.GetHandle("stance")
        local cx, cy = h:GetCenter()
        near(cx, UIParent._w / 2 + FS.Layout.stance.x * s, 1e-6, "stance cx at " .. height)
        near(cy, UIParent._h / 2 + FS.Layout.stance.y * s, 1e-6, "stance cy at " .. height)
        near(h:GetWidth(), 320 * s, 1e-6); near(h:GetHeight(), 38 * s, 1e-6)
        local p = FS.LayoutEdit.GetHandle("player")
        near(p:GetLeft(), 20, 1e-6, "player left is raw UI units at " .. height)
        near(p:GetTop(), UIParent._h - 20, 1e-6)
    end
end

function T.a_scale_change_while_editing_moves_the_handles()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    screen(768)
    __fire("UI_SCALE_CHANGED")
    local h = FS.LayoutEdit.GetHandle("stance")
    local s = 768 / 1440
    near(h:GetWidth(), 320 * s, 1e-6)
    local cx, cy = h:GetCenter()
    near(cx, UIParent._w / 2 + FS.Layout.stance.x * s, 1e-6, "handle x follows the new scale")
    near(cy, UIParent._h / 2 + FS.Layout.stance.y * s, 1e-6, "handle y follows the new scale")
end

-------------------------------------------------------------------------------
-- Drop math
-------------------------------------------------------------------------------

function T.a_scaled_center_drop_round_trips_to_the_same_screen_point_at_two_scales()
    for _, height in ipairs({ 1200, 768 }) do
        screen(height)
        __session(__layoutSrc, __configSrc, __editSrc)
        edit()
        local f = seat("stance")
        setSnap(false)
        FS.LayoutEdit.Enter()
        local s = FS.Layout.Scale()
        local sx, sy = 100, -50
        dragTo("stance", "CENTER", "CENTER", sx, sy)
        local saved = override("stance")
        near(saved.x, sx / s, 0.25 + 1e-6, "design x at " .. height)
        near(saved.y, sy / s, 0.25 + 1e-6, "design y at " .. height)
        local cx, cy = f:GetCenter()
        near(cx, UIParent._w / 2 + sx, 0.25 * s + 1e-6, "frame lands on the dropped point x")
        near(cy, UIParent._h / 2 + sy, 0.25 * s + 1e-6, "frame lands on the dropped point y")
        local hx, hy = FS.LayoutEdit.GetHandle("stance"):GetCenter()
        near(hx, cx, 1e-6, "handle re-synced onto the frame"); near(hy, cy, 1e-6)
    end
end

function T.an_unscaled_topleft_drop_round_trips_to_the_same_screen_point_at_two_scales()
    for _, height in ipairs({ 1200, 768 }) do
        screen(height)
        __session(__layoutSrc, __configSrc, __editSrc)
        edit()
        local f = seat("target")
        setSnap(false)
        FS.LayoutEdit.Enter()
        dragTo("target", "TOPLEFT", "BOTTOMLEFT", 411, height - 77)
        local saved = override("target")
        near(saved.x, 411, 0.25 + 1e-6, "raw x at " .. height)
        near(saved.y, -77, 0.25 + 1e-6, "raw y at " .. height)
        near(f:GetLeft(), 411, 0.25 + 1e-6); near(f:GetTop(), height - 77, 0.25 + 1e-6)
    end
end

function T.the_drop_is_written_through_set_override_then_reseat_then_the_handle_syncs()
    edit(); seat("stance")
    local calls = {}
    local setO, reseat = FS.Layout.SetOverride, FS.Layout.Reseat
    FS.Layout.SetOverride = function(...) calls[#calls + 1] = "set"; return setO(...) end
    FS.Layout.Reseat = function(id) calls[#calls + 1] = "reseat:" .. id; return reseat(id) end
    FS.LayoutEdit.Enter()
    setSnap(false)
    dragTo("stance", "CENTER", "CENTER", 40, 40)
    eq(table.concat(calls, ","), "set,reseat:stance")
end

function T.dropping_where_it_already_is_writes_nothing()
    edit(); seat("stance")
    setSnap(false)
    FS.LayoutEdit.Enter()
    local s = FS.Layout.Scale()
    dragTo("stance", "CENTER", "CENTER", FS.Layout.stance.x * s, FS.Layout.stance.y * s)
    eq(next(frames()), nil)
end

function T.a_refused_write_is_reported_and_the_handle_returns_to_the_layout()
    edit(); seat("stance")
    FS.Layout.UseStore(nil)
    FS.LayoutEdit.Enter()
    dragTo("stance", "CENTER", "CENTER", 300, 300)
    eq(__printedHas("could not save"), true)
    local h = FS.LayoutEdit.GetHandle("stance")
    local cx = h:GetCenter()
    near(cx, UIParent._w / 2 + FS.Layout.stance.x * FS.Layout.Scale(), 1e-6)
end

-------------------------------------------------------------------------------
-- Snap
-------------------------------------------------------------------------------

local function dropDesign(id, x, y)
    local s = FS.Layout.IsUnscaled(id) and 1 or FS.Layout.Scale()
    if FS.Layout.IsUnscaled(id) then
        dragTo(id, "TOPLEFT", "BOTTOMLEFT", x, UIParent._h + y)
    else
        dragTo(id, "CENTER", "CENTER", x * s, y * s)
    end
end

function T.snap_rounds_to_the_grid_in_the_entrys_own_units()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    dropDesign("stance", 13, -427 + 5)
    eq(override("stance").x, 16, "13 with grid 8"); eq(override("stance").y, -424)
    FS.Config.Set("layout.grid", 16)
    dropDesign("stance", 7.9, 100)
    eq(override("stance").x, 0, "7.9 with grid 16"); eq(override("stance").y, 96)
    FS.Config.Set("layout.grid", 4)
    dropDesign("stance", 5, 6)
    eq(override("stance").x, 4); eq(override("stance").y, 8)
    FS.Config.Set("layout.grid", 32)
    dropDesign("stance", 49, -17)
    eq(override("stance").x, 64); eq(override("stance").y, -32)
end

function T.snap_applies_to_unscaled_entries_in_raw_units()
    edit(); seat("player")
    FS.LayoutEdit.Enter()
    dropDesign("player", 53, -29)
    eq(override("player").x, 56); eq(override("player").y, -32)
end

function T.snap_off_keeps_the_dropped_point()
    edit(); seat("stance")
    setSnap(false)
    FS.LayoutEdit.Enter()
    dropDesign("stance", 13, 100)
    near(override("stance").x, 13, 0.25 + 1e-6)
end

function T.a_grid_size_outside_the_allowed_set_falls_back_to_8()
    edit(); seat("stance")
    FS.Config.Set("layout.grid", 7)
    FS.LayoutEdit.Enter()
    dropDesign("stance", 13, 100)
    eq(override("stance").x, 16)
end

-------------------------------------------------------------------------------
-- Keyboard
-------------------------------------------------------------------------------

function T.arrows_nudge_the_selected_handle_one_unit_and_shift_by_the_grid()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnMouseDown(h, "LeftButton")
    key("RIGHT")
    eq(override("stance").x, 1); eq(override("stance").y, -427)
    key("UP")
    eq(override("stance").y, -426, "up is +y")
    key("LEFT"); key("LEFT")
    eq(override("stance").x, -1)
    key("DOWN")
    eq(override("stance").y, -427)
    __shift = true
    key("RIGHT")
    eq(override("stance").x, 7, "shift steps by the grid (8)")
    local o = key("UP")
    eq(override("stance").y, -419)
    eq(o._propagate, false, "a handled key is consumed")
end

function T.arrows_nudge_unscaled_entries_in_raw_units()
    edit(); seat("target")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("target")
    h._scripts.OnMouseDown(h, "LeftButton")
    key("RIGHT")
    eq(override("target").x, 301); eq(override("target").y, -20)
end

function T.arrows_without_a_selection_and_other_keys_propagate()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local o = key("RIGHT")
    eq(next(frames()), nil, "no selection, no move")
    eq(o._propagate, true)
    o._propagate = false
    key("W")
    eq(o._propagate, true, "an unhandled key restores the pass-through")
end

function T.a_key_up_always_passes_through_so_a_held_movement_key_is_never_stuck()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local o = overlay()
    eq(type(o._scripts.OnKeyUp), "function")
    o._propagate = false
    o._scripts.OnKeyUp(o, "W")
    eq(o._propagate, true)
    o._propagate = false
    o._scripts.OnKeyUp(o, "RIGHT")
    eq(o._propagate, true, "even an arrow's key-up")
end

function T.a_key_press_after_combat_began_leaves_edit_mode_and_reaches_the_game()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local o = overlay()
    __combat = true   -- the regen event has not been delivered yet
    o._scripts.OnKeyDown(o, "W")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(o._propagate, true, "the key is not swallowed")
    eq(next(frames()), nil)
end

-------------------------------------------------------------------------------
-- Reset
-------------------------------------------------------------------------------

function T.right_click_resets_that_frame_only()
    edit()
    local a, b = seat("stance"), seat("action")
    FS.Layout.SetOverride("stance", 50, 50); FS.Layout.SetOverride("action", 60, 60)
    FS.Layout.ReseatAll()
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnMouseUp(h, "LeftButton")
    eq(override("stance") ~= nil, true, "left click does not reset")
    h._scripts.OnMouseUp(h, "RightButton")
    eq(override("stance"), nil)
    eq(override("action") ~= nil, true, "another frame keeps its override")
    near(a:GetCenter(), UIParent._w / 2 + 0, 1e-6, "back on the default seat")
    local hx = h:GetCenter()
    near(hx, UIParent._w / 2, 1e-6, "handle follows")
end

function T.reset_all_asks_for_confirmation_in_chat_then_clears_everything()
    edit()
    seat("stance"); seat("action")
    FS.Layout.SetOverride("stance", 50, 50); FS.Layout.SetOverride("action", 60, 60)
    SlashCmdList.FSEDIT("reset all")
    eq(override("stance") ~= nil, true, "nothing cleared yet")
    eq(__printedHas("reset all confirm"), true)
    SlashCmdList.FSEDIT("reset all confirm")
    eq(next(frames()), nil)
    eq(FS.Layout.stance.x, 0)
end

function T.reset_all_reseats_every_frame()
    edit()
    local a = seat("stance")
    FS.Layout.SetOverride("stance", 50, 50)
    FS.Layout.ReseatAll()
    local n = 0
    local reseatAll = FS.Layout.ReseatAll
    FS.Layout.ReseatAll = function() n = n + 1; return reseatAll() end
    FS.LayoutEdit.ResetAll()
    eq(n, 1)
    near(a:GetCenter(), UIParent._w / 2, 1e-6)
end

-------------------------------------------------------------------------------
-- Secure frames
-------------------------------------------------------------------------------

function T.only_handles_are_ever_started_moving()
    edit()
    local t, s = seat("target", true), seat("stance", true)
    FS.LayoutEdit.Enter()
    dragTo("target", "TOPLEFT", "BOTTOMLEFT", 500, UIParent._h - 100)
    dragTo("stance", "CENTER", "CENTER", 10, 10)
    eq(__moves[t], nil); eq(__moves[s], nil)
    eq(__moves[FS.LayoutEdit.GetHandle("target")], 1)
end

function T.moving_the_minimap_writes_only_the_minimap_entry()
    edit(); seat("minimap")
    FS.LayoutEdit.Enter()
    setSnap(false)
    local s = FS.Layout.Scale()
    dragTo("minimap", "CENTER", "CENTER", (FS.Layout.minimap.x - 100) * s, (FS.Layout.minimap.y - 50) * s)
    eq(override("minimap") ~= nil, true)
    eq(override("minimaptray"), nil, "the drawer is a Minimap child and has no layout seat")
end

function T.writes_while_in_combat_never_touch_a_protected_frame()
    edit()
    local s = seat("stance", true)
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnMouseDown(h, "LeftButton")
    __combat = true
    FS.LayoutEdit.Nudge(1, 0)   -- Commit
    eq(override("stance") ~= nil, true, "the write itself is allowed")
    eq(__blocked, 0, "Commit")
    FS.LayoutEdit.ResetOne("stance")
    eq(__blocked, 0, "ResetOne")
    FS.Layout.SetOverride("stance", 9, 9)
    FS.LayoutEdit.ResetAll()
    eq(__blocked, 0, "ResetAll")
    eq(override("stance"), nil)
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    near(s:GetCenter(), UIParent._w / 2, 1e-6, "seated on the default once combat ends")
end

function T.a_failure_while_building_handles_leaves_edit_mode_off_and_nothing_on_screen()
    edit()
    seat("stance"); seat("action")
    local calls = 0
    FS.Theme.ApplyMono = function() calls = calls + 1; if calls == 2 then error("boom") end end
    eq(FS.LayoutEdit.Enter(), false)
    eq(FS.LayoutEdit.IsEditing(), false)
    for _, f in ipairs(__frames) do
        if f._kind == "Frame" and f._strata == "FULLSCREEN_DIALOG" then eq(f:IsShown(), false, "no stray frame left shown") end
    end
    eq(overlay(), nil, "and the keyboard is released")
    eq(#__errors, 1, "the failure is forwarded to the error handler")
    FS.Theme.ApplyMono = function() end
    eq(FS.LayoutEdit.Enter(), true, "a later try works")
end

-------------------------------------------------------------------------------
-- Special cases
-------------------------------------------------------------------------------

function T.a_floating_pet_moves_through_set_override_and_drops_the_old_pet_drag_position()
    edit()
    local pet = seat("petcontainer")
    ForeverSTUwaveDB.petFrame = { pos = { point = "BOTTOMLEFT", relativePoint = "BOTTOMLEFT", x = 300, y = 200 }, locked = false }
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("petcontainer")
    eq(h ~= nil, true)
    setSnap(false)
    dragTo("petcontainer", "CENTER", "CENTER", 120, -80)
    eq(ForeverSTUwaveDB.petFrame.pos, nil, "the /fspet position no longer wins")
    eq(ForeverSTUwaveDB.petFrame.locked, false, "the rest of petFrame is kept")
    eq(override("petcontainer") ~= nil, true)
    local cx = pet:GetCenter()
    near(cx, UIParent._w / 2 + 120, 0.25 * FS.Layout.Scale() + 1e-6)
end

function T.a_pet_handle_with_an_old_drag_position_starts_on_the_frame_not_the_layout_seat()
    edit()
    local pet = seat("petcontainer")
    pet:ClearAllPoints()
    pet:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", 300, 200)
    ForeverSTUwaveDB.petFrame = { pos = { point = "BOTTOMLEFT", relativePoint = "BOTTOMLEFT", x = 300, y = 200 } }
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("petcontainer")
    local hx, hy = h:GetCenter()
    local fx, fy = pet:GetCenter()
    near(hx, fx, 1e-6); near(hy, fy, 1e-6)
end

-- PetFrame.lua's own SeatDocked, cut out of the real file and run over a stand-in container
-- (the rest of PetFrame.lua needs a far larger mock than this harness carries).
local function realSeatDocked(container)
    local src = "local FS, container = ...; local docked; local function ApplyLockState() end; FS.PetFrame = {}; "
        .. __seatDockedSrc .. "; return FS.PetFrame"
    return assert(load(src, "@PetFrame.lua:SeatDocked"))(FS, container)
end

function T.a_docked_pet_has_no_handle()
    edit()
    local pet = seat("petcontainer")
    local anchor = CreateFrame()
    anchor:SetSize(500, 100); anchor:SetPoint("CENTER", UIParent, "CENTER", 0, -400)
    eq(realSeatDocked(pet).SeatDocked(anchor, 0), true)
    eq(FS.Layout._applied[pet], nil, "the real dock path takes the container off the re-seat list")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("petcontainer"), nil)
end

function T.a_pet_that_docks_while_editing_loses_its_handle_and_a_drop_writes_nothing()
    edit()
    local pet = seat("petcontainer")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("petcontainer")
    h._scripts.OnDragStart(h)
    local anchor = CreateFrame()
    anchor:SetSize(500, 100); anchor:SetPoint("CENTER", UIParent, "CENTER", 0, -400)
    realSeatDocked(pet).SeatDocked(anchor, 0)
    h:ClearAllPoints(); h:SetPoint("CENTER", UIParent, "CENTER", 200, 200)
    h._scripts.OnDragStop(h)
    eq(next(frames()), nil, "nothing was written for a frame that is gone")
    eq(FS.LayoutEdit.GetHandle("petcontainer"), nil, "and its handle is hidden")
    eq(FS.LayoutEdit.IsEditing(), true)
end

function T.a_nudge_on_a_frame_that_is_gone_writes_nothing()
    edit()
    local pet = seat("petcontainer")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("petcontainer")
    h._scripts.OnMouseDown(h, "LeftButton")
    FS.Layout._applied[pet] = nil
    key("RIGHT")
    eq(next(frames()), nil)
    eq(FS.LayoutEdit.GetHandle("petcontainer"), nil)
end

-- StanceBar.lua takes its container off the re-seat list while the Warrior's class shoulder carries the stances
-- (the same way PetFrame.SeatDocked does), and that is all the handle needs: no applied frame, no handle.
function T.a_stance_bar_on_the_class_shoulder_has_no_handle_and_others_keep_theirs()
    edit()
    local stance = seat("stance"); seat("player")
    FS.Layout._applied[stance] = nil
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("stance"), nil, "no handle for a shouldered stance bar")
    eq(FS.LayoutEdit.GetHandle("player") ~= nil, true, "other frames keep theirs")
    FS.LayoutEdit.Exit()
    seat("stance")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("stance") ~= nil, true, "back on its own seat the stance bar is draggable again")
end

function T.a_stance_bar_that_goes_onto_the_shoulder_mid_edit_loses_its_handle_and_a_drop_writes_nothing()
    edit()
    local stance = seat("stance")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnDragStart(h)
    FS.Layout._applied[stance] = nil
    h:ClearAllPoints(); h:SetPoint("CENTER", UIParent, "CENTER", 200, 200)
    h._scripts.OnDragStop(h)
    eq(next(frames()), nil, "nothing was written for a frame that is gone")
    eq(FS.LayoutEdit.GetHandle("stance"), nil, "and its handle is hidden")
end

function T.resetting_the_pet_also_drops_the_old_pet_drag_position()
    edit(); seat("petcontainer")
    ForeverSTUwaveDB.petFrame = { pos = { point = "CENTER", relativePoint = "CENTER", x = 1, y = 1 } }
    FS.Layout.SetOverride("petcontainer", 5, 5)
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("petcontainer")
    h._scripts.OnMouseUp(h, "RightButton")
    eq(ForeverSTUwaveDB.petFrame.pos, nil)
    eq(override("petcontainer"), nil)
end

function T.the_chat_reseats_through_the_chat_modules_own_seat_function()
    edit()
    local frame = CreateFrame()
    local seen = 0
    FS.Chat = { windowState = "normal" }
    function FS.Chat.ReassertPrimaryChat()
        seen = seen + 1
        FS.Layout.Apply(frame, "chat")
    end
    FS.Layout.Apply(frame, "chat")
    local reseated = {}
    local reseat = FS.Layout.Reseat
    FS.Layout.Reseat = function(id) reseated[#reseated + 1] = id; return reseat(id) end
    FS.LayoutEdit.Enter()
    setSnap(false)
    dragTo("chat", "CENTER", "CENTER", -300, -200)
    eq(seen, 1, "the chat module's function ran once")
    eq(#reseated, 0, "not the generic reseat")
    near(frame:GetCenter(), UIParent._w / 2 - 300, 0.25 * FS.Layout.Scale() + 1e-6)
    local h = FS.LayoutEdit.GetHandle("chat")
    h._scripts.OnMouseUp(h, "RightButton")
    eq(seen, 2, "a reset goes through it too")
end

function T.a_minimised_or_maximised_chat_has_no_handle()
    edit()
    FS.Chat = { windowState = "min", ReassertPrimaryChat = function() end }
    seat("chat")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("chat"), nil)
    FS.LayoutEdit.Exit()
    FS.Chat.windowState = "max"
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("chat"), nil)
    FS.LayoutEdit.Exit()
    FS.Chat.windowState = "normal"
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("chat") ~= nil, true)
end

-------------------------------------------------------------------------------
-- Blizzard Edit Mode pointer
-------------------------------------------------------------------------------

function T.blizzard_edit_mode_gets_a_one_line_pointer_and_nothing_else()
    edit(); seat("stance")
    EditModeManagerFrame:EnterEditMode()
    eq(__blizTouched, 1, "Blizzard's own function ran once, untouched")
    local lines = 0
    for _, l in ipairs(__printed) do if l:find("/fsedit", 1, true) then lines = lines + 1 end end
    eq(lines, 1)
end

function T.entering_blizzard_edit_mode_leaves_ours()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    EditModeManagerFrame:EnterEditMode()
    eq(FS.LayoutEdit.IsEditing(), false)
end

function T.a_missing_blizzard_manager_at_load_is_hooked_when_its_addon_loads()
    EditModeManagerFrame = nil
    edit()
    EditModeManagerFrame = { IsEditModeActive = function() return false end, EnterEditMode = function() end }
    __fire("ADDON_LOADED", "Blizzard_EditMode")
    EditModeManagerFrame:EnterEditMode()
    eq(__printedHas("/fsedit"), true)
end

-------------------------------------------------------------------------------
-- Layout page
-------------------------------------------------------------------------------

local function fakeWindow()
    local W = { categories = {}, closed = 0, calls = {}, opened = {} }
    function W.RegisterCategory(def) W.categories[#W.categories + 1] = def end
    function W.Close() W.closed = W.closed + 1 end
    function W.Open(key) W.opened[#W.opened + 1] = key end
    W.UI = {}
    for _, name in ipairs({ "Header", "Button", "Toggle", "Segmented" }) do
        W.UI[name] = function(content, spec, tip)
            W.calls[#W.calls + 1] = { name = name, spec = spec, tip = tip }
            return CreateFrame()
        end
    end
    return W
end

function T.the_layout_page_registers_when_the_config_window_exists()
    FS.ConfigWindow = fakeWindow()
    edit()
    local cats = FS.ConfigWindow.categories
    eq(#cats, 1)
    eq(cats[1].key, "layout"); eq(cats[1].label, "Layout"); eq(cats[1].order, 3)
    eq(type(cats[1].build), "function")
end

function T.the_layout_page_is_skipped_cleanly_when_there_is_no_config_window()
    local ok, err = pcall(edit)
    eq(ok, true, tostring(err))
    eq(FS.ConfigWindow, nil)
end

function T.the_layout_page_registers_at_login_if_the_config_window_loads_later()
    edit()
    FS.ConfigWindow = fakeWindow()
    __fire("PLAYER_LOGIN")
    eq(#FS.ConfigWindow.categories, 1)
    __fire("PLAYER_LOGIN")
    eq(#FS.ConfigWindow.categories, 1, "registered once")
end

function T.the_layout_page_builds_the_mockup_c_sections()
    FS.ConfigWindow = fakeWindow()
    edit()
    FS.ConfigWindow.categories[1].build(CreateFrame())
    local calls = FS.ConfigWindow.calls
    local function find(name, pred)
        for _, c in ipairs(calls) do if c.name == name and pred(c) then return c end end
    end
    local edith = find("Header", function(c) return c.spec == "Edit mode" end)
    eq(edith ~= nil, true); eq(type(edith.tip), "string", "the ? tip")
    eq(edith.tip:find("tape"), nil)
    local big = find("Button", function(c) return c.spec.text == "EDIT LAYOUT" end)
    eq(big ~= nil, true); eq(big.spec.big, true)
    eq(find("Header", function(c) return c.spec == "Snapping" end) ~= nil, true)
    local tog = find("Toggle", function(c) return c.spec.key == "layout.snap" end)
    eq(tog ~= nil, true); eq(tog.spec.label, "Snap to grid")
    local seg = find("Segmented", function(c) return c.spec.key == "layout.grid" end)
    eq(seg ~= nil, true); eq(seg.spec.label, "Grid size")
    local values = {}
    for _, o in ipairs(seg.spec.options) do values[#values + 1] = o.value .. ":" .. o.text end
    eq(table.concat(values, ","), "4:4,8:8,16:16,32:32")
    local rh = find("Header", function(c) return c.spec == "Reset" end)
    eq(rh ~= nil, true); eq(type(rh.tip), "string")
    local warn = find("Button", function(c) return c.spec.text == "Reset all positions" end)
    eq(warn ~= nil, true); eq(warn.spec.warn, true); eq(type(warn.spec.confirm), "string")
end

function T.the_edit_layout_button_closes_the_config_window_then_enters_edit_mode()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    FS.ConfigWindow.categories[1].build(CreateFrame())
    local big
    for _, c in ipairs(FS.ConfigWindow.calls) do if c.name == "Button" and c.spec.big then big = c end end
    __combat = true
    big.spec.onClick()
    eq(FS.ConfigWindow.closed, 0, "in combat the window stays open")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(__printedHas("combat"), true, "and says why")
    __combat = false
    local order = {}
    local close = FS.ConfigWindow.Close
    FS.ConfigWindow.Close = function() order[#order + 1] = "close"; return close() end
    local enter = FS.LayoutEdit.Enter
    FS.LayoutEdit.Enter = function() order[#order + 1] = "enter"; return enter() end
    big.spec.onClick()
    eq(table.concat(order, ","), "close,enter")
    eq(FS.LayoutEdit.IsEditing(), true)
end

function T.the_reset_button_clears_every_override()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    FS.ConfigWindow.categories[1].build(CreateFrame())
    FS.Layout.SetOverride("stance", 9, 9)
    local warn
    for _, c in ipairs(FS.ConfigWindow.calls) do if c.name == "Button" and c.spec.warn then warn = c end end
    warn.spec.onClick()
    eq(next(frames()), nil)
end

-------------------------------------------------------------------------------
-- DONE panel and the way back to settings
-------------------------------------------------------------------------------

local function pageButton()
    FS.ConfigWindow.categories[1].build(CreateFrame())
    for _, c in ipairs(FS.ConfigWindow.calls) do if c.name == "Button" and c.spec.big then return c.spec end end
end
-- Enter the way the config page's EDIT LAYOUT button does.
local function enterFromConfig()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    pageButton().onClick()
    return FS.ConfigWindow
end
local function clickDone()
    local panel = FS.LayoutEdit.GetDonePanel()
    panel.done._scripts.OnClick(panel.done)
end

function T.the_done_panel_shows_only_while_editing()
    edit(); seat("stance")
    eq(FS.LayoutEdit.GetDonePanel(), nil, "not before entering")
    FS.LayoutEdit.Enter()
    local panel = FS.LayoutEdit.GetDonePanel()
    eq(panel ~= nil, true)
    eq(panel._parent, UIParent)
    eq(panel:GetFrameStrata(), "FULLSCREEN_DIALOG")
    eq(panel:GetFrameLevel() > FS.LayoutEdit.GetHandle("stance"):GetFrameLevel(), true, "above the handles")
    eq(panel._mouse, true, "the panel takes clicks")
    eq(overlay()._mouse, false, "the overlay still lets the mouse through")
    eq(panel._protected, nil, "a plain non-secure frame")
    eq(panel.done._template, nil, "no Blizzard button template")
    eq(panel.done.label:GetText(), "DONE")
    local point, rel, relPoint, _, y = panel:GetPoint(1)
    eq(point, "TOP"); eq(rel, UIParent); eq(relPoint, "TOP"); eq(y < 0, true, "just below the top edge")
    FS.LayoutEdit.Exit()
    eq(FS.LayoutEdit.GetDonePanel(), nil, "hidden on exit")
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetDonePanel(), panel, "the same panel is reused")
end

function T.the_done_panel_is_built_from_the_theme_builders()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local panel = FS.LayoutEdit.GetDonePanel()
    eq(#__themed.panels, 1); eq(__themed.panels[1], panel)
    eq(#__themed.buttons, 1); eq(__themed.buttons[1], panel.done)
    eq(#__themed.fills, 1); eq(__themed.fills[1], panel.done)
    FS.LayoutEdit.Exit(); FS.LayoutEdit.Enter()
    eq(#__themed.panels, 1, "skinned once, not on every Enter")
end

function T.clicking_done_leaves_edit_mode()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(FS.LayoutEdit.GetHandle("stance"), nil)
    eq(FS.LayoutEdit.GetDonePanel(), nil)
    eq(overlay(), nil, "the keyboard overlay is released")
end

function T.the_done_tooltip_names_esc_and_clears_on_leave()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local done = FS.LayoutEdit.GetDonePanel().done
    done._scripts.OnEnter(done)
    eq(GameTooltip._owner, done)
    eq(GameTooltip._text:find("Esc", 1, true) ~= nil, true)
    done._scripts.OnLeave(done)
    eq(GameTooltip._shown, false)
end

function T.done_after_entering_from_config_reopens_the_layout_page()
    local W = enterFromConfig()
    eq(FS.LayoutEdit.IsEditing(), true)
    eq(W.closed, 1)
    eq(#W.opened, 0, "settings stay closed while editing")
    clickDone()
    eq(#W.opened, 1)
    eq(W.opened[1], W.categories[1].key)
    eq(W.opened[1], "layout")
    eq(FS.LayoutEdit.IsEditing(), false)
end

function T.escape_after_entering_from_config_reopens_the_layout_page()
    local W = enterFromConfig()
    local o = key("ESCAPE")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(o._propagate, false, "Esc is still consumed")
    eq(#W.opened, 1)
    eq(W.opened[1], "layout")
end

function T.leaving_a_slash_entered_session_does_not_open_settings()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    SlashCmdList.FSEDIT("")
    key("ESCAPE")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#FS.ConfigWindow.opened, 0)
end

function T.a_non_done_exit_after_entering_from_config_does_not_open_settings()
    local exits = {
        combat_event = function() __combat = true; __fire("PLAYER_REGEN_DISABLED") end,
        combat_key = function() __combat = true; key("ESCAPE") end,
        slash_toggle = function() SlashCmdList.FSEDIT("") end,
    }
    for name, leave in pairs(exits) do
        local W = enterFromConfig()
        leave()
        eq(FS.LayoutEdit.IsEditing(), false, name)
        eq(#W.opened, 0, name)
        __combat = false
        FS.LayoutEdit.Exit()
    end
end

function T.entering_from_the_config_page_while_already_editing_does_not_arm_the_return()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    SlashCmdList.FSEDIT("")
    pageButton().onClick()
    eq(FS.LayoutEdit.IsEditing(), true)
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#FS.ConfigWindow.opened, 0)
end

function T.blizzard_edit_mode_exit_after_entering_from_config_does_not_open_settings()
    local W = enterFromConfig()
    EditModeManagerFrame:EnterEditMode()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#W.opened, 0)
end

function T.every_exit_clears_the_return_to_settings_flag()
    local W = enterFromConfig()
    __fire("PLAYER_REGEN_DISABLED")
    __combat = false
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#W.opened, 0, "a stale flag from the earlier config entry would open it")
    pageButton().onClick()
    clickDone()
    eq(#W.opened, 1, "and a fresh config entry still works")
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#W.opened, 1, "the flag was cleared again by that exit")
end

function T.a_refused_entry_from_config_does_not_arm_the_return()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    local spec = pageButton()
    __bliz = true
    spec.onClick()
    eq(FS.LayoutEdit.IsEditing(), false)
    __bliz = false
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#FS.ConfigWindow.opened, 0)
end

function T.leaving_without_a_config_window_is_quiet()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#__errors, 0)
end

__checks = T
"""


def seat_docked_source() -> str:
    text = PETFRAME_FILE.read_text(encoding="utf-8")
    match = re.search(r"^function FS\.PetFrame\.SeatDocked\(.*?^end$", text, re.M | re.S)
    if not match:
        sys.exit("PetFrame.lua: FS.PetFrame.SeatDocked not found")
    return match.group(0)


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__layoutSrc = LAYOUT_FILE.read_text(encoding="utf-8")
    lua.globals().__configSrc = CONFIG_FILE.read_text(encoding="utf-8")
    lua.globals().__editSrc = EDIT_FILE.read_text(encoding="utf-8")
    lua.globals().__seatDockedSrc = seat_docked_source()
    lua.globals().__session = lua.eval(SESSION)
    lua.globals().__session(lua.globals().__layoutSrc, lua.globals().__configSrc, lua.globals().__editSrc)
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the combat flag, the applied frames and the
        # saved variable must not leak between them.
        try:
            boot().eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
