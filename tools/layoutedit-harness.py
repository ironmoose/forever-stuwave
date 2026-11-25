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
  * snap, grid size, arrow and Shift+arrow nudges, Esc, the right click menu's Reset position and reset all;
  * the snap grid: lines on the places Snap rounds to (per picked piece), one whole pixel thick, a brighter centre cross, a
    step change, snap off and Show grid off, strata below the handles, gone on every way out;
  * the position panel: fields that follow nudges and drags, typed X / Y in px or grid units committed through the drop's
    path, refused input, clamping, Esc and Tab, the origin tip, provider pieces (tracker, raid, pet);
  * the right click menu: at the cursor, closes on a click elsewhere or Esc, Settings calls Open(page, tab, row) from the
    map (every handle id has an entry, rows exist in the window's registry when it has one), greyed for pieces with none,
    Set position focuses X, the editor drops under the config window while it is up;
  * pet, chat and minimap special cases;
  * the Layout page registers when FS.ConfigWindow exists and is skipped cleanly when not;
  * a DONE panel shows only while editing, and DONE or Esc reopens the page that started the editor
    from the config window (the Layout page's button, or another page through EnterFromConfig),
    never after /fsedit, combat or Blizzard Edit Mode.

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
-- The client throws "Font not set" for SetText on a FontString that has no font yet (seen in game 2026-11-10).
function Region:SetText(s)
    if self._isFontString and not (self._mono or self._hasFont) then error("Font not set", 2) end
    self._text = s
end
function Region:SetFont() self._hasFont = true; return true end
function Region:GetText() return self._text end
function Region:ClearAllPoints() self._points = {} end
function Region:SetPoint(point, rel, relPoint, x, y)
    self._points = self._points or {}
    self._points[#self._points + 1] = { point = point, rel = rel, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Region:SetWidth(w) self._w = w end
function Region:SetHeight(h) self._h = h end
function Region:SetSize(w, h) self._w, self._h = w, h end
function Region:Show() self._hidden = false end
function Region:Hide() self._hidden = true end
function Region:IsShown() return not self._hidden end
function Region:SetSnapToPixelGrid(v) self._snapPixel = v end
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
function Frame:CreateFontString() local r = newRegion(); r._isFontString = true; return r end
function Frame:SetText(t) self._text = t end
function Frame:GetText() return self._text end
function Frame:GetEffectiveScale() return 1 end
-- An edit box: focus fires the box's own focus scripts, as the client does.
function Frame:SetFocus()
    self._focused = true
    local f = self._scripts.OnEditFocusGained
    if f then f(self) end
end
function Frame:ClearFocus()
    if not self._focused then return end
    self._focused = false
    local f = self._scripts.OnEditFocusLost
    if f then f(self) end
end
function Frame:HasFocus() return self._focused or false end
__cursor = { 0, 0 }
function GetCursorPosition() return __cursor[1], __cursor[2] end
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

__themed = { panels = {}, buttons = {}, fills = {}, text = {} }
FS_THEME_STUB = {
    COLOR_POWER = { 0.133, 0.878, 1, 1 },
    COLOR_HEALTH = { 1, 0.18, 0.592, 1 },
    COLOR_BORDER = { 0.545, 0.361, 0.965, 1 },
    COLOR_STEEL = { 0.62, 0.66, 0.74, 1 },
    COLOR_BUTTON_INK = { 0.051, 0.024, 0.125, 1 },
    ApplyMono = function(region, size, color) region._mono = { size = size, color = color } end,
    SkinPanel = function(frame) __themed.panels[#__themed.panels + 1] = frame end,
    SkinButton = function(button) __themed.buttons[#__themed.buttons + 1] = button end,
    AddCutSliceFill = function(frame)
        __themed.fills[#__themed.fills + 1] = frame
        return newRegion()
    end,
}
FS_BUTTONSKINS_STUB = {
    SkinTextButton = function(button, opts) __themed.text[#__themed.text + 1] = { button = button, opts = opts } end,
}
"""

SESSION = r"""
function(layoutSrc, configSrc, editSrc)
    __frames, __printed, __errors, __timers, __moves = { UIParent }, {}, {}, {}, {}
    __combat, __shift, __bliz, __blizTouched = false, false, false, 0
    __themed.panels, __themed.buttons, __themed.fills, __themed.text = {}, {}, {}, {}
    GameTooltip._text, GameTooltip._shown, GameTooltip._owner = nil, false, nil
    SlashCmdList = {}
    ForeverSTUwaveDB = nil
    FS = { Theme = FS_THEME_STUB, ButtonSkins = FS_BUTTONSKINS_STUB }
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
-- A right click opens the piece's menu; a row's OnClick is a pick (settings, position or reset).
local function rightClick(h)
    h._scripts.OnMouseUp(h, "RightButton")
    return FS.LayoutEdit.GetMenu()
end
local function menuPick(h, which)
    local menu = rightClick(h)
    if not menu then error("the right click opened no menu", 2) end
    local item = menu.items[which]
    item._scripts.OnClick(item)
    return item
end
local function setSnap(on, grid)
    FS.Config.Set("layout.snap", on)
    if grid then FS.Config.Set("layout.grid", grid) end
end

-- A stand-in for FS.TrackerSeat: a tracker rect in UIParent units whose TOPRIGHT follows Move.
local function fakeSeat(opts)
    opts = opts or {}
    local seat = { moves = {}, resets = 0, right = -29, top = -286, w = 300, h = 200, ready = opts.ready ~= false }
    function seat.Ready() return seat.ready end
    function seat.Rect()
        local r, t = UIParent:GetRight() + seat.right, UIParent:GetTop() + seat.top
        return r - seat.w, t, seat.w, seat.h
    end
    function seat.Offsets() return seat.right, seat.top end
    function seat.Move(x, y)
        seat.moves[#seat.moves + 1] = { x, y }
        if opts.refuse then return false, "no free slot" end
        seat.right, seat.top = x, y
        return true
    end
    function seat.Reset()
        seat.resets = seat.resets + 1
        seat.right, seat.top = -10, -200
        return true
    end
    FS.TrackerSeat = seat
    return seat
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
    menuPick(h, "reset")
    eq(override("tooltip"), nil, "Reset position resets it")
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

function T.the_gunsight_switch_mid_drag_stops_the_drag_and_drops_the_selection()
    for _, id in ipairs({ "pcast", "tcast" }) do
        local active, notify = false, nil
        FS.Gunsight = { OnActiveChanged = function(fn) notify = fn end }
        FS.CastBars = { IsStackActive = function() return not active end }
        seat("pcast"); seat("tcast")
        edit()
        FS.LayoutEdit.Enter()
        local h = FS.LayoutEdit.GetHandle(id)
        h._scripts.OnDragStart(h)
        eq(h._moving, true, id .. " is being dragged")
        active = true
        notify(true)                               -- the Gunsight takes the casts mid drag
        eq(h._moving, false, id .. ": the drag is stopped when its handle goes")
        eq(FS.LayoutEdit.GetHandle(id), nil)
        active = false
        notify(false)                              -- Stack A back, the handle returns
        h:ClearAllPoints(); h:SetPoint("CENTER", UIParent, "CENTER", 200, 200)
        h._scripts.OnDragStop(h)
        eq(override(id), nil, id .. ": the stale drop saves nothing (dragging was cleared)")
        FS.LayoutEdit.Nudge(1, 0)
        eq(override(id), nil, id .. ": and nothing is selected any more")
        FS.LayoutEdit.Exit()
    end
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
    rightClick(h)
    eq(override("stance") ~= nil, true, "a right click alone only opens the menu")
    local menu = FS.LayoutEdit.GetMenu()
    menu.items.reset._scripts.OnClick(menu.items.reset)
    eq(FS.LayoutEdit.GetMenu(), nil, "the pick closes the menu")
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
    local applyMono = FS.Theme.ApplyMono
    FS.Theme.ApplyMono = function(...) calls = calls + 1; if calls == 2 then error("boom") end return applyMono(...) end
    eq(FS.LayoutEdit.Enter(), false)
    eq(FS.LayoutEdit.IsEditing(), false)
    for _, f in ipairs(__frames) do
        if f._kind == "Frame" and f._strata == "FULLSCREEN_DIALOG" then eq(f:IsShown(), false, "no stray frame left shown") end
    end
    eq(overlay(), nil, "and the keyboard is released")
    eq(#__errors, 1, "the failure is forwarded to the error handler")
    FS.Theme.ApplyMono = applyMono
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
    menuPick(h, "reset")
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
    menuPick(h, "reset")
    eq(seen, 2, "a reset goes through it too")
end

local function fakeChat()
    local size = { w = FS.Layout.chat.w, h = FS.Layout.chat.h }
    local calls = {}
    FS.Chat = { windowState = "normal", ReassertPrimaryChat = function() end,
        SIZE = { w = { min = 300, max = 1000 }, h = { min = 150, max = 700 } } }
    function FS.Chat.GetSize() return size.w, size.h end
    function FS.Chat.SyncSize() FS.Layout.chat.w, FS.Layout.chat.h = size.w, size.h end
    function FS.Chat.SetSize(w, h)
        calls[#calls + 1] = { w, h }
        size.w, size.h = w, h
        FS.Chat.SyncSize()
        return true
    end
    return calls, size
end

function T.the_chat_corner_resizes_through_chat_setsize_and_keeps_the_top_left()
    edit()
    local frame = seat("chat")
    local calls, size = fakeChat()
    FS.LayoutEdit.Enter()
    setSnap(false)
    local h = FS.LayoutEdit.GetHandle("chat")
    eq(h.corner ~= nil, true, "the chat handle has a corner")
    local left, top = h:GetLeft(), h:GetTop()
    local unit = FS.Layout.Scale()
    local oldW, oldH, L = size.w, size.h, FS.Layout.chat
    local oldX, oldY = L.x, L.y
    __cursor = { left + 800 * unit, top - 400 * unit }
    h.corner._scripts.OnDragStart(h.corner)
    h.corner._scripts.OnUpdate(h.corner, 1)
    near(h:GetLeft(), left, 1e-6, "the top left stays while dragging")
    near(h:GetWidth(), 800 * unit, 1e-6, "the handle follows the pointer")
    eq(#calls, 0, "nothing is stored until the drop")
    h.corner._scripts.OnDragStop(h.corner)
    eq(#calls, 1); eq(calls[1][1], 800); eq(calls[1][2], 400)
    near(FS.Layout.chat.x, oldX + (800 - oldW) / 2, 1e-6, "the centre moved half the change")
    near(FS.Layout.chat.y, oldY - (400 - oldH) / 2, 1e-6)
    near(h:GetLeft(), left, 1e-3, "after the drop the top left is still where it was")
    near(h:GetTop(), top, 1e-3)
    eq(h.corner._scripts.OnUpdate, nil, "no per frame work after the drop")
end

function T.the_chat_corner_is_clamped_to_the_slider_range()
    edit()
    seat("chat")
    local calls = fakeChat()
    FS.LayoutEdit.Enter()
    setSnap(false)
    local h = FS.LayoutEdit.GetHandle("chat")
    __cursor = { h:GetLeft() + 5000, h:GetTop() - 5000 }
    h.corner._scripts.OnDragStart(h.corner)
    h.corner._scripts.OnUpdate(h.corner, 1)
    h.corner._scripts.OnDragStop(h.corner)
    eq(calls[1][1], 1000); eq(calls[1][2], 700)
end

function T.a_slider_change_moves_the_chat_handle()
    edit()
    seat("chat")
    local _, size = fakeChat()
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("chat")
    local before = h:GetWidth()
    size.w = size.w + 100
    FS.Config.Set("chat.w", size.w)
    near(h:GetWidth(), before + 100 * FS.Layout.Scale(), 1e-6, "the handle follows the saved width")
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
    local W = { categories = {}, closed = 0, calls = {}, opened = {}, openCalls = {}, shown = false }
    function W.RegisterCategory(def) W.categories[#W.categories + 1] = def end
    function W.Close() W.closed = W.closed + 1; W.shown = false end
    -- Open(page, tab, row): `opened` keeps the pages, `openCalls` the whole call.
    function W.Open(page, tab, row)
        W.opened[#W.opened + 1] = page
        W.openCalls[#W.openCalls + 1] = { page = page, tab = tab, row = row }
        W.shown = true
    end
    function W.IsShown() return W.shown end
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
    eq(panel.done:GetText(), "DONE", "the button holds its own label")
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
    eq(#__themed.text, 1, "the DONE button is the shared text button"); eq(__themed.text[1].button, panel.done)
    eq(__themed.text[1].opts.accent, "cyan")
    eq(#__themed.buttons, 0, "no hand drawn ring"); eq(#__themed.fills, 0, "no hand drawn face")
    FS.LayoutEdit.Exit(); FS.LayoutEdit.Enter()
    eq(#__themed.panels, 1, "skinned once, not on every Enter")
    eq(#__themed.text, 1, "the button is skinned once too")
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
    eq(FS.ConfigWindow.closed, 0, "the window is not closed for an entry Blizzard's Edit Mode refuses")
    eq(__printedHas("Edit Mode"), true, "and says why")
    __bliz = false
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#FS.ConfigWindow.opened, 0)
end

-- ---- another page of the config window starts the editor too (EnterFromConfig) ----

function T.another_page_enters_the_editor_and_done_and_esc_bring_that_page_back()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    local order = {}
    local close = FS.ConfigWindow.Close
    FS.ConfigWindow.Close = function() order[#order + 1] = "close"; return close() end
    local enter = FS.LayoutEdit.Enter
    FS.LayoutEdit.Enter = function() order[#order + 1] = "enter"; return enter() end
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), true)
    eq(table.concat(order, ","), "close,enter", "the window closes, then the editor opens")
    eq(FS.LayoutEdit.IsEditing(), true)
    eq(#FS.ConfigWindow.opened, 0, "settings stay closed while editing")
    clickDone()
    eq(FS.ConfigWindow.opened[1], "unitframes", "DONE reopens the page that started it")
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), true)
    key("ESCAPE")
    eq(FS.ConfigWindow.opened[2], "unitframes", "and so does Esc")
    eq(FS.LayoutEdit.EnterFromConfig(), true)
    clickDone()
    eq(FS.ConfigWindow.opened[3], "layout", "no page named: the Layout page")
end

function T.entering_from_another_page_in_combat_keeps_the_window_open_and_says_why()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    __combat = true
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), false)
    eq(FS.ConfigWindow.closed, 0, "the window stays open")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(__printedHas("combat"), true, "and says why")
    __combat = false
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#FS.ConfigWindow.opened, 0, "a refused entry arms nothing")
end

function T.entering_from_another_page_while_blizzard_edit_mode_is_active_keeps_the_window_open_and_arms_nothing()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    local entered = 0
    local enter = FS.LayoutEdit.Enter
    FS.LayoutEdit.Enter = function() entered = entered + 1; return enter() end
    __bliz = true
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), false)
    eq(FS.ConfigWindow.closed, 0, "the window stays open, so the player keeps their place")
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(FS.LayoutEdit.GetHandle("stance"), nil, "no handle shown")
    eq(FS.LayoutEdit.GetDonePanel(), nil, "no DONE bar")
    eq(__printedHas("Edit Mode"), true, "and says why")
    eq(entered, 0, "the editor is not even asked: nothing to undo")
    __bliz = false
    SlashCmdList.FSEDIT("")
    clickDone()
    eq(#FS.ConfigWindow.opened, 0, "a refused entry arms no way back")
    __bliz = true
    eq(FS.LayoutEdit.EnterFromConfig(), false)
    eq(FS.ConfigWindow.closed, 0, "the same for the Layout page's default")
end

function T.entering_from_another_page_while_already_editing_does_not_arm_the_return()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    SlashCmdList.FSEDIT("")
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), true)
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#FS.ConfigWindow.opened, 0)
end

function T.entering_from_a_page_with_no_config_window_still_enters()
    edit(); seat("stance")
    eq(FS.LayoutEdit.EnterFromConfig("unitframes"), true)
    eq(FS.LayoutEdit.IsEditing(), true)
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#__errors, 0)
end

function T.leaving_without_a_config_window_is_quiet()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    clickDone()
    eq(FS.LayoutEdit.IsEditing(), false)
    eq(#__errors, 0)
end

-------------------------------------------------------------------------------
-- Objectives tracker (Edit Mode seat)
-------------------------------------------------------------------------------

function T.the_objectives_handle_sits_on_the_tracker_rect()
    local seat = fakeSeat()
    edit(); FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("objectives")
    eq(h ~= nil, true, "handle shown")
    eq(h.label._text, "Objectives")
    near(h:GetRight(), UIParent:GetRight() - 29, 1e-6, "right edge")
    near(h:GetTop(), UIParent:GetTop() - 286, 1e-6, "top edge")
    eq(h._w, 300); eq(h._h, 200)
    eq(#seat.moves, 0, "showing writes nothing")
end

function T.no_objectives_handle_without_a_ready_seat()
    edit(); FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("objectives"), nil, "no provider")
    FS.LayoutEdit.Exit()
    fakeSeat({ ready = false })
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("objectives"), nil, "Edit Mode missing")
end

function T.an_objectives_drop_moves_the_seat_by_its_topright_snapped()
    local seat = fakeSeat()
    edit(); FS.LayoutEdit.Enter()
    dragTo("objectives", "TOPRIGHT", "TOPRIGHT", -45, -301)
    eq(#seat.moves, 1)
    eq(seat.moves[1][1], -48, "x snapped to 8"); eq(seat.moves[1][2], -304, "y snapped to 8")
    local h = FS.LayoutEdit.GetHandle("objectives")
    near(h:GetRight(), UIParent:GetRight() - 48, 1e-6, "handle follows the seat")
    eq(next(frames()), nil, "nothing written to the STUwave layout")
end

function T.an_objectives_drop_without_snap_keeps_the_exact_point()
    local seat = fakeSeat()
    edit(); setSnap(false); FS.LayoutEdit.Enter()
    dragTo("objectives", "TOPRIGHT", "TOPRIGHT", -45, -301)
    eq(seat.moves[1][1], -45); eq(seat.moves[1][2], -301)
end

function T.arrows_nudge_the_objectives_seat()
    local seat = fakeSeat()
    edit(); FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("objectives")
    key("LEFT")
    eq(seat.moves[1][1], -30); eq(seat.moves[1][2], -286)
    __shift = true
    key("DOWN")
    eq(seat.moves[2][1], -30); eq(seat.moves[2][2], -294)
end

function T.a_refused_objectives_move_is_reported_and_the_handle_goes_back()
    local seat = fakeSeat({ refuse = true })
    edit(); FS.LayoutEdit.Enter()
    dragTo("objectives", "TOPRIGHT", "TOPRIGHT", -100, -400)
    eq(__printedHas("no free slot"), true)
    local h = FS.LayoutEdit.GetHandle("objectives")
    near(h:GetRight(), UIParent:GetRight() - 29, 1e-6, "back on the tracker")
end

function T.right_click_and_reset_all_reset_the_objectives_seat()
    local seat = fakeSeat()
    edit(); FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("objectives")
    menuPick(h, "reset")
    eq(seat.resets, 1)
    near(h:GetRight(), UIParent:GetRight() - 10, 1e-6, "handle follows the reset")
    FS.LayoutEdit.ResetAll()
    eq(seat.resets, 2)
end


-------------------------------------------------------------------------------
-- Raid frames (the editor's preview grid, RaidFrames.lua)
-------------------------------------------------------------------------------

-- A stand-in for FS.RaidFrames.Preview: a grid whose top left sits on the seat of its size's own entry (raid<size>: UIParent
-- centre plus x and y, scaled) and whose size follows the raid size. The real preview and the real seats are checked
-- against the real RaidFrames.lua in raidframes-harness.py.
local function fakePreview(opts)
    opts = opts or {}
    local pv = { SIZES = { 5, 10, 15, 20, 25, 40 }, KEY = "raid.previewSize", shown = false, size = 10,
        shows = 0, hides = 0, asked = {}, listeners = {} }
    local function notify() for _, fn in ipairs(pv.listeners) do fn() end end
    function pv.IsShown() return pv.shown end
    function pv.Size() return pv.size end
    function pv.SeatId() return "raid" .. pv.size end
    function pv.Show()
        if __combat or opts.refuse then return false end
        pv.shown = true; pv.shows = pv.shows + 1
        notify()
        return true
    end
    function pv.Hide() pv.shown = false; pv.hides = pv.hides + 1 end
    function pv.SetSize(n)
        pv.asked[#pv.asked + 1] = n
        pv.size = n
        FS.Config.Set(pv.KEY, n)
        if pv.shown then notify() end
        return true
    end
    function pv.Rect()
        if not pv.shown or (opts.lateRect and not pv.ready) then return nil end
        local L, scale = FS.Layout["raid" .. pv.size], FS.Layout.Scale()
        local cx, cy = UIParent:GetCenter()
        return cx + L.x * scale, cy + L.y * scale, pv.size * 9 * scale, 120 * scale
    end
    function pv.OnChange(fn) pv.listeners[#pv.listeners + 1] = fn end
    FS.RaidFrames = { Preview = pv }
    FS.Config.RegisterDefault(pv.KEY, 10)
    return pv
end

-- The ring's outer and inner edges around handle `h`, read off its four edge textures (anchored to the handle by
-- offsets in UI units, one pixel per unit here): { left, bottom, right, top } of the area the ring and tint cover.
local function outlineOf(h)
    local top, bottom, left, right = h.edges[1], h.edges[2], h.edges[3], h.edges[4]
    local outL = left._points[1].x
    local outT = top._points[1].y
    local outR = right._points[1].x
    local outB = bottom._points[1].y
    return outL, outB, outR, outT
end

function T.the_raid_handle_covers_the_preview_and_exists_only_while_it_shows()
    local pv = fakePreview()
    edit(); setSnap(false)
    FS.LayoutEdit.Enter()
    eq(pv.shown, true, "entering shows the preview")
    local h = FS.LayoutEdit.GetHandle("raid10")
    eq(h ~= nil, true, "handle shown")
    eq(h.label._text, "Raid 10", "labelled with its size")
    eq(FS.LayoutEdit.GetHandle("raid"), nil, "no handle for the removed shared entry")
    eq(h._parent, UIParent, "an insecure frame on UIParent")
    eq(h._protected, nil)
    local left, top, w, hh = pv.Rect()
    near(h:GetLeft(), left, 1e-6); near(h:GetTop(), top, 1e-6)
    near(h:GetWidth(), w, 1e-6); near(h:GetHeight(), hh, 1e-6)
    for _, p in ipairs(h._points) do eq(p.rel, UIParent, "never anchored to a grid") end
    -- A preview that cannot show (combat, a refusal) leaves no handle to move.
    FS.LayoutEdit.Exit()
    eq(FS.LayoutEdit.GetHandle("raid10"), nil, "no handle once out")
    pv.Show = function() return false end
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("raid10"), nil, "no preview, no handle")
end

function T.a_preview_the_engine_has_not_laid_out_yet_gets_its_handle_a_moment_later()
    local pv = fakePreview({ lateRect = true })
    edit()
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("raid10"), nil, "no rect yet, no handle")
    pv.ready = true
    for _, fn in ipairs(__timers) do fn() end
    eq(FS.LayoutEdit.GetHandle("raid10") ~= nil, true, "the retry found it")
    -- Leaving before the retry runs does nothing.
    FS.LayoutEdit.Exit()
    pv.ready = false
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Exit()
    for _, fn in ipairs(__timers) do fn() end
    eq(FS.LayoutEdit.GetHandle("raid10"), nil)
    eq(#__errors, 0)
end

function T.a_size_switched_before_the_engine_has_laid_it_out_gets_its_handle_a_moment_later()
    local pv = fakePreview({ lateRect = true })
    edit()
    pv.ready = true
    FS.LayoutEdit.Enter()
    eq(FS.LayoutEdit.GetHandle("raid10") ~= nil, true)
    pv.ready = false
    pv.SetSize(25)
    eq(FS.LayoutEdit.GetHandle("raid25"), nil, "no rect yet")
    eq(FS.LayoutEdit.GetHandle("raid10"), nil, "and the old size's handle is down")
    pv.ready = true
    for _, fn in ipairs(__timers) do fn() end
    eq(FS.LayoutEdit.GetHandle("raid25") ~= nil, true, "the retry found it")
    eq(#__errors, 0)
end

function T.there_is_no_raid_handle_where_the_raid_frames_did_not_load()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    for _, n in ipairs({ 5, 10, 15, 20, 25, 40 }) do eq(FS.LayoutEdit.GetHandle("raid" .. n), nil) end
    eq(rawget(FS.LayoutEdit.GetDonePanel(), "sizeButtons"), nil, "and no size row on the panel")
    eq(FS.LayoutEdit.GetDonePanel()._h, 36, "the panel keeps its one row (ROW_H + 4)")
    FS.LayoutEdit.Exit()
    eq(#__errors, 0)
end

function T.every_way_out_of_the_editor_hides_the_preview()
    local pv = fakePreview()
    edit()
    FS.LayoutEdit.Enter()
    eq(pv.shows, 1)
    FS.LayoutEdit.Exit()
    eq(pv.shown, false, "Exit"); eq(pv.hides, 1)
    FS.LayoutEdit.Enter()
    SlashCmdList.FSEDIT("")
    eq(pv.shown, false, "/fsedit off")
    FS.LayoutEdit.Enter()
    local o = overlay(); o._scripts.OnKeyDown(o, "ESCAPE")
    eq(pv.shown, false, "Esc")
    FS.LayoutEdit.Enter()
    __fire("PLAYER_REGEN_DISABLED")
    eq(pv.shown, false, "combat")
    __combat = true
    eq(FS.LayoutEdit.Enter(), false)
    eq(pv.shown, false, "the editor never starts in combat, so the preview never shows there")
    eq(#__errors, 0)
end

function T.a_raid_drop_saves_the_snapped_seat_and_right_click_resets_it()
    local pv = fakePreview()
    edit()
    FS.LayoutEdit.Enter()
    dragTo("raid10", "TOPLEFT", "CENTER", -403, 197)   -- UIParent is 1200 high: scale 1200 / 1440
    local s = FS.Layout.Scale()
    eq(override("raid10").x, 8 * math.floor(-403 / s / 8 + 0.5), "snapped to 8 in design px")
    eq(override("raid10").y, 8 * math.floor(197 / s / 8 + 0.5))
    eq(override("raid25"), nil, "no other size is written")
    eq(override("raid"), nil)
    local left, top = pv.Rect()
    local h = FS.LayoutEdit.GetHandle("raid10")
    near(h:GetLeft(), left, 1e-6, "the handle follows the seat the preview took")
    near(h:GetTop(), top, 1e-6)
    menuPick(h, "reset")
    eq(override("raid10"), nil, "Reset position resets it")
    eq(FS.Layout.raid10.x, -696.5, "to the shipped entry")
    eq(__printedHas("could not"), false)
end

function T.arrows_and_reset_all_move_and_clear_the_raid_seat()
    fakePreview()
    edit(); setSnap(false)
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("raid10")
    key("RIGHT")
    eq(override("raid10").x, -695.5); eq(override("raid10").y, 140)
    __shift = true
    key("DOWN")
    eq(override("raid10").y, 132, "Shift nudges by the grid step")
    FS.LayoutEdit.ResetAll()
    eq(override("raid10"), nil, "reset all clears it")
    local h = FS.LayoutEdit.GetHandle("raid10")
    local left, top = FS.RaidFrames.Preview.Rect()
    near(h:GetLeft(), left, 1e-6, "and the handle goes back with it")
end

function T.a_resized_preview_swaps_the_handle_and_the_selection_goes_with_it()
    local pv = fakePreview()
    edit(); setSnap(false)
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("raid10")
    local before = FS.LayoutEdit.GetHandle("raid10"):GetWidth()
    pv.SetSize(40)
    eq(FS.LayoutEdit.GetHandle("raid10"), nil, "the old size's handle is down")
    local h = FS.LayoutEdit.GetHandle("raid40")
    eq(h ~= nil, true, "the new size's handle is up")
    eq(h:GetWidth() > before, true, "it took the bigger grid")
    near(h:GetWidth(), select(3, pv.Rect()), 1e-6)
    eq(h.label._text, "Raid 40")
    key("LEFT")
    eq(override("raid40").x, -1010.5, "an arrow nudges the layout on screen")
    eq(override("raid10"), nil, "and not the one that was left")
    -- With nothing selected, a switch selects nothing.
    FS.LayoutEdit.Select(nil)
    pv.SetSize(5)
    key("LEFT")
    eq(override("raid5"), nil)
    eq(#__errors, 0)
end

function T.every_handle_outline_sits_clear_of_the_frame_it_covers()
    local pv = fakePreview()
    edit(); seat("stance"); seat("party")
    FS.LayoutEdit.Enter()
    for _, id in ipairs({ "stance", "party", "raid10" }) do
        local h = FS.LayoutEdit.GetHandle(id)
        eq(h ~= nil, true, id)
        local l, b, r, t = outlineOf(h)
        -- Outside the covered rect by the gap and the ring, on every side (one pixel per unit in this mock).
        eq(l, -5, id .. " left"); eq(r, 5, id .. " right"); eq(t, 5, id .. " top"); eq(b, -5, id .. " bottom")
        -- The ring is two pixels thick and its inner edge is the 3 pixel gap from the frame.
        eq(h.edges[1]._h, 2); eq(h.edges[2]._h, 2); eq(h.edges[3]._w, 2); eq(h.edges[4]._w, 2)
        -- The tint covers the same outer rect, and the edges meet at the corners without overlapping.
        eq(h.fill._points[1].x, -5); eq(h.fill._points[1].y, 5)
        eq(h.fill._points[2].x, 5); eq(h.fill._points[2].y, -5)
        eq(h.edges[3]._points[1].y, 3, id .. " the side edge starts under the top edge")
        eq(h.edges[3]._points[2].y, -3)
        eq(h.edges[4]._points[1].y, 3)
        -- The handle frame itself is the frame's own rect: the drag maths and the hit area are unchanged.
        local L = FS.Layout[id]
        if id ~= "raid10" then
            local scale = FS.Layout.Scale()
            near(h:GetWidth(), L.w * scale, 1e-6, id .. " width")
        end
    end
end

function T.the_outline_follows_the_pixel_scale()
    fakePreview()
    edit(); seat("stance")
    FS.FrameHelpers = { PixelsPerUnit = function() return 1.2 end }
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    -- 5 pixels (3 clear and a 2 pixel ring) at 1.2 pixels per unit.
    near(h.edges[1]._points[1].y, 5 / 1.2, 1e-9); near(h.edges[1]._h, 2 / 1.2, 1e-9)
    FS.FrameHelpers = { PixelsPerUnit = function() return 1 end }
    __fire("UI_SCALE_CHANGED")
    near(h.edges[1]._points[1].y, 5, 1e-9, "re-seated when the scale changes")
    eq(#__errors, 0)
end

function T.a_raid_label_sits_outside_the_ring_and_other_labels_stay_centred()
    local pv = fakePreview()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local raid = FS.LayoutEdit.GetHandle("raid10")
    local p = raid.label._points[#raid.label._points]
    eq(p.point, "BOTTOMLEFT", "above the ring, from the left")
    eq(p.relPoint, "TOPLEFT"); eq(p.rel, raid)
    eq(p.x, -5); eq(p.y, 7, "5 outside plus the label gap")
    -- Too near the top of the screen: it goes under the ring instead.
    local left, top = pv.Rect()
    local _, _, w, hh = pv.Rect()
    pv.Rect = function() return left, UIParent:GetTop() - 4, w, hh end
    pv.SetSize(10)
    p = raid.label._points[#raid.label._points]
    eq(p.point, "TOPLEFT", "below the ring when there is no room above")
    eq(p.relPoint, "BOTTOMLEFT")
    eq(p.y, -7)
    -- Every other handle keeps the label on the piece.
    local stance = FS.LayoutEdit.GetHandle("stance")
    local q = stance.label._points[#stance.label._points]
    eq(q.point, "CENTER"); eq(q.rel, stance)
end

function T.the_panel_has_a_size_chip_per_raid_size_and_a_click_asks_for_it()
    local pv = fakePreview()
    edit()
    FS.LayoutEdit.Enter()
    local panel = FS.LayoutEdit.GetDonePanel()
    eq(#panel.sizeButtons, 6)
    eq(panel._h > 36, true, "a second row")
    local labels = {}
    for i, b in ipairs(panel.sizeButtons) do labels[i] = b.label._text end
    eq(table.concat(labels, ","), "5,10,15,20,25,40")
    -- Not the shared text button skin (its plate, ring and halo read as two outlines at this size); only DONE has it.
    for _, c in ipairs(__themed.text) do
        for _, b in ipairs(panel.sizeButtons) do if c.button == b then error("a size chip took the text button skin") end end
    end
    local cyan, violet = FS_THEME_STUB.COLOR_POWER, FS_THEME_STUB.COLOR_BORDER
    local function ringOf(b)
        local c = b.edges[1]._color
        return c
    end
    local function same(c, want) return math.abs(c[1] - want[1]) < 1e-9 and math.abs(c[2] - want[2]) < 1e-9 end
    eq(panel.sizeButtons[2].fsSelected, true, "the current size is selected")
    eq(same(ringOf(panel.sizeButtons[2]), cyan), true, "its ring is cyan")
    eq(ringOf(panel.sizeButtons[2])[4], 1)
    eq(panel.sizeButtons[1].fsSelected, false)
    eq(same(ringOf(panel.sizeButtons[1]), violet), true, "the rest are violet")
    eq(ringOf(panel.sizeButtons[1])[4] < 1, true, "and dimmer")
    -- The selected chip's fill is washed toward cyan; the others are the ink.
    local sel, other = panel.sizeButtons[2].fill._color, panel.sizeButtons[1].fill._color
    eq(sel[3] > other[3] and sel[2] > other[2], true, "a cyan wash on the selected fill")
    eq(panel.sizeButtons[2].label._mono.color, FS_THEME_STUB.COLOR_POWER, "a cyan label")
    eq(panel.sizeButtons[1].label._mono.color, FS_THEME_STUB.COLOR_STEEL, "a steel label")
    local b = panel.sizeButtons[5]
    b._scripts.OnClick(b)
    eq(pv.asked[1], 25)
    eq(panel.sizeButtons[5].fsSelected, true, "the pick moves the selection")
    eq(panel.sizeButtons[2].fsSelected, false)
    eq(same(ringOf(panel.sizeButtons[5]), cyan), true)
    eq(same(ringOf(panel.sizeButtons[2]), violet), true)
    -- Hover brightens an unselected chip and leaving puts it back.
    local o = panel.sizeButtons[1]
    local dim = ringOf(o)[4]
    o._scripts.OnEnter(o)
    eq(ringOf(o)[4], 1, "hover takes the ring to full")
    eq(GameTooltip._text:find("25", 1, true), nil, "the tooltip names its own size")
    eq(GameTooltip._text:find("5", 1, true) ~= nil, true)
    o._scripts.OnLeave(o)
    eq(ringOf(o)[4], dim); eq(GameTooltip._shown, false)
    -- One pixel ring: four edges one pixel thick, sides starting under the top edge, so no corner is drawn twice.
    for _, chip in ipairs(panel.sizeButtons) do
        eq(chip.edges[1]._h, 1); eq(chip.edges[2]._h, 1); eq(chip.edges[3]._w, 1); eq(chip.edges[4]._w, 1)
        eq(chip.edges[3]._points[1].y, -1)
        eq(chip.edges[3]._points[2].y, 1)
    end
    -- The row never reaches past the panel, and the chips do not overlap.
    local right
    for _, button in ipairs(panel.sizeButtons) do
        local p = button._points[1]
        eq(p.x >= 0 and p.x + button._w <= panel._w, true, "inside the panel")
        eq(-p.y + button._h <= panel._h, true, "inside the panel")
        if right then eq(p.x >= right, true, "the chips do not overlap") end
        right = p.x + button._w
    end
end

function T.the_size_chips_sit_on_whole_pixels_at_any_scale()
    fakePreview()
    edit()
    FS.FrameHelpers = { PixelsPerUnit = function() return 1.2 end }
    FS.LayoutEdit.Enter()
    local panel = FS.LayoutEdit.GetDonePanel()
    for _, button in ipairs(panel.sizeButtons) do
        local px = button._w * 1.2
        near(px, math.floor(px + 0.5), 1e-9, "the chip is a whole number of pixels wide")
        local py = button._h * 1.2
        near(py, math.floor(py + 0.5), 1e-9, "and high")
        near(button.edges[1]._h * 1.2, 1, 1e-9, "its ring is one pixel")
    end
    local a, b = panel.sizeButtons[1]._points[1].x, panel.sizeButtons[2]._points[1].x
    near((b - a) * 1.2, math.floor((b - a) * 1.2 + 0.5), 1e-9, "the pitch is whole pixels")
    eq(#__errors, 0)
end

function T.the_layout_page_offers_the_raid_preview()
    FS.ConfigWindow = fakeWindow()
    local pv = fakePreview()
    edit(); seat("stance")
    FS.ConfigWindow.categories[1].build(CreateFrame())
    local calls = FS.ConfigWindow.calls
    local function find(name, pred)
        for _, c in ipairs(calls) do if c.name == name and pred(c) then return c end end
    end
    local header = find("Header", function(c) return c.spec == "Raid frames" end)
    eq(header ~= nil, true); eq(type(header.tip), "string", "the ? tip")
    eq(header.tip:find("\226\128\148"), nil, "no em dash")
    local seg = find("Segmented", function(c) return c.spec.key == pv.KEY end)
    eq(seg ~= nil, true, "a size control"); eq(seg.spec.label, "Preview size")
    local values = {}
    for _, o in ipairs(seg.spec.options) do values[#values + 1] = o.value .. ":" .. o.text end
    eq(table.concat(values, ","), "5:5,10:10,15:15,20:20,25:25,40:40")
    local move = find("Button", function(c) return c.spec.text == "MOVE RAID FRAMES" end)
    eq(move ~= nil, true, "a way in")
    eq(move.spec.big, nil, "EDIT LAYOUT stays the one big button")
    move.spec.onClick()
    eq(FS.ConfigWindow.closed, 1, "the window closes")
    eq(FS.LayoutEdit.IsEditing(), true)
    eq(pv.shown, true, "the preview is up")
    clickDone()
    eq(FS.ConfigWindow.opened[1], "layout", "DONE brings the Layout page back")
end

function T.the_layout_page_has_no_raid_section_without_the_raid_frames()
    FS.ConfigWindow = fakeWindow()
    edit()
    FS.ConfigWindow.categories[1].build(CreateFrame())
    for _, c in ipairs(FS.ConfigWindow.calls) do
        if c.name == "Header" and c.spec == "Raid frames" then error("a raid section with nothing to preview") end
        if c.name == "Button" and c.spec.text == "MOVE RAID FRAMES" then error("a raid button with nothing to preview") end
    end
end

-------------------------------------------------------------------------------
-- Snap grid overlay
-------------------------------------------------------------------------------

local function gridNow() return FS.LayoutEdit.GetGrid() end
local function litLines(list)
    local out = {}
    for _, line in ipairs(list) do if not line._hidden then out[#out + 1] = line end end
    return out
end
-- Where the shown lines sit, in UIParent units from the left edge (verticals) or the bottom edge (horizontals).
local function lineXs(grid)
    local out = {}
    for _, line in ipairs(litLines(grid.v)) do out[#out + 1] = line._points[1].x end
    return out
end
local function lineYs(grid)
    local out = {}
    for _, line in ipairs(litLines(grid.h)) do out[#out + 1] = line._points[1].y end
    return out
end
local function hasLine(values, v, tol)
    for _, o in ipairs(values) do if math.abs(o - v) <= tol then return true end end
    return false
end
-- A UIParent anchor point on the screen, in UIParent units.
local function screenPoint(relPoint)
    local px = relPoint:find("LEFT") and 0 or relPoint:find("RIGHT") and 1 or 0.5
    local py = relPoint:find("BOTTOM") and 0 or relPoint:find("TOP") and 1 or 0.5
    return UIParent._w * px, UIParent._h * py
end
-- A drop of `id` at layout (x, y) of its own entry, whatever the entry's anchor.
local function dropAt(id, x, y)
    local L = FS.Layout[id]
    local unit = FS.Layout.IsUnscaled(id) and 1 or FS.Layout.Scale()
    return dragTo(id, L.point, L.relPoint, x * unit, y * unit)
end

function T.the_grid_shows_on_enter_at_the_current_step_and_every_line_hides_on_leave()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    eq(gridNow(), nil, "no grid before the editor")
    FS.LayoutEdit.Enter()
    local grid = gridNow()
    eq(grid ~= nil, true, "a grid on enter")
    eq(#lineXs(grid), 321, "2560 wide at step 8: a line every 8 from the left edge to the right edge")
    eq(#lineYs(grid), 181, "1440 high at step 8")
    FS.LayoutEdit.Exit()
    eq(gridNow(), nil, "no grid once out")
    eq(grid._shown, false, "the grid frame is hidden")
    for _, list in ipairs({ grid.v, grid.h, grid.cross }) do
        for _, line in ipairs(list) do eq(line._hidden, true, "a line is still showing") end
    end
    FS.LayoutEdit.Enter()
    eq(#lineXs(gridNow()), 321, "back on re-entry")
    __combat = true
    __fire("PLAYER_REGEN_DISABLED")
    eq(gridNow(), nil, "combat takes the grid away with the editor")
    for _, line in ipairs(grid.v) do eq(line._hidden, true) end
    eq(#__errors, 0)
end

function T.the_grid_lines_are_the_places_snap_puts_a_piece()
    for _, height in ipairs({ 1440, 1200, 1080 }) do
        screen(height)
        __session(__layoutSrc, __configSrc, __editSrc)
        edit()
        local tracker = fakeSeat()
        local ids = { "stance", "player", "target", "tcast", "minimap", "tooltip" }
        for _, id in ipairs(ids) do seat(id) end
        ids[#ids + 1] = "objectives"
        FS.LayoutEdit.Enter()
        -- A line is on a whole pixel, so it is within half a pixel of the exact place (exact where the scale is 1).
        local tol = height == 1440 and 1e-6 or 0.5 + 1e-6
        for _, step in ipairs({ 4, 8, 16, 32 }) do
            FS.Config.Set("layout.grid", step)
            for _, id in ipairs(ids) do
                local where = id .. " at step " .. step .. " on a " .. height .. " screen"
                local px, py
                if id == "objectives" then
                    dragTo(id, "TOPRIGHT", "TOPRIGHT", -45.3, -301.7)
                    px, py = UIParent._w + tracker.right, UIParent._h + tracker.top
                    eq(tracker.right % step, 0, where .. ": the tracker seat is a whole step")
                else
                    local L = FS.Layout[id]
                    local x = L.relPoint:find("RIGHT") and -113.3 or (L.relPoint:find("LEFT") and 113.3 or 13.3)
                    local y = L.relPoint:find("TOP") and -141.7 or (L.relPoint:find("BOTTOM") and 141.7 or -41.7)
                    dropAt(id, x, y)
                    local saved = FS.Layout[id]
                    eq(saved.x % step, 0, where .. ": x is a whole step"); eq(saved.y % step, 0, where .. ": y is a whole step")
                    local ox, oy = screenPoint(saved.relPoint)
                    local unit = FS.Layout.IsUnscaled(id) and 1 or FS.Layout.Scale()
                    px, py = ox + saved.x * unit, oy + saved.y * unit
                end
                local grid = gridNow()
                eq(grid ~= nil, true, where .. ": a grid")
                eq(hasLine(lineXs(grid), px, tol), true, where .. ": no vertical line at " .. px)
                eq(hasLine(lineYs(grid), py, tol), true, where .. ": no horizontal line at " .. py)
            end
        end
        -- The spacing is the step in the piece's own unit, read off two neighbouring lines.
        FS.Config.Set("layout.grid", 8)
        FS.LayoutEdit.Select("stance")
        local xs = lineXs(gridNow())
        near(xs[3] - xs[2], 8 * FS.Layout.Scale(), 1.0, "spacing on a " .. height .. " screen")
        -- With nothing picked it is the screen centre lattice in design pixels.
        FS.LayoutEdit.Select(nil)
        eq(hasLine(lineXs(gridNow()), UIParent._w / 2, tol), true, "centre line, nothing picked")
        eq(hasLine(lineYs(gridNow()), UIParent._h / 2, tol), true)
    end
end

function T.grid_lines_are_one_physical_pixel_and_sit_on_whole_pixels()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    for _, ppu in ipairs({ 1, 1.2, 0.75 }) do
        FS.FrameHelpers = { PixelsPerUnit = function() return ppu end }
        FS.LayoutEdit.Exit()
        FS.LayoutEdit.Enter()
        local grid = gridNow()
        local n = 0
        for _, list in ipairs({ grid.v, grid.cross }) do
            for _, line in ipairs(litLines(list)) do
                if line._points[1].point == "TOPLEFT" then
                    near(line._w * ppu, 1, 1e-9, "a vertical line is one pixel wide at " .. ppu)
                    near(line._points[1].x * ppu, math.floor(line._points[1].x * ppu + 0.5), 1e-6, "on a whole pixel")
                    n = n + 1
                end
            end
        end
        for _, list in ipairs({ grid.h, grid.cross }) do
            for _, line in ipairs(litLines(list)) do
                if line._points[1].point == "BOTTOMLEFT" then
                    near(line._h * ppu, 1, 1e-9, "a horizontal line is one pixel tall at " .. ppu)
                    near(line._points[1].y * ppu, math.floor(line._points[1].y * ppu + 0.5), 1e-6)
                    n = n + 1
                end
            end
        end
        eq(n > 400, true, "every kind of line was checked")
        for _, list in ipairs({ grid.v, grid.h, grid.cross }) do
            for _, line in ipairs(litLines(list)) do eq(line._snapPixel, true, "snapped to the pixel grid") end
        end
    end
end

function T.the_centre_cross_is_brighter_than_the_grid_on_both_axes()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local grid = gridNow()
    local plain = grid.v[1]._color
    local down, across = grid.cross[1], grid.cross[2]
    eq(down._hidden, false); eq(across._hidden, false)
    near(down._points[1].x, UIParent._w / 2, 1e-6, "the vertical arm is on the screen centre")
    near(across._points[1].y, UIParent._h / 2, 1e-6, "the horizontal arm is on the screen centre")
    for _, arm in ipairs({ down, across }) do
        eq(arm._color[4] > plain[4] * 4, true, "much brighter than a grid line")
        near(arm._color[1], 1); near(arm._color[2], 0.18, 1e-6)   -- the health pink
    end
    -- It stays on the screen centre when a piece with another lattice is picked.
    FS.LayoutEdit.Select("stance")
    near(grid.cross[1]._points[1].x, UIParent._w / 2, 1e-6)
end

function T.a_step_change_redraws_the_grid_at_once_and_hides_the_lines_it_no_longer_needs()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local grid = gridNow()
    local pool = #grid.v
    eq(#lineXs(grid), 321)
    FS.Config.Set("layout.grid", 16)
    eq(#lineXs(grid), 161, "step 16"); eq(#lineYs(grid), 91)
    eq(#grid.v, pool, "the pool is kept")
    for i = 162, #grid.v do eq(grid.v[i]._hidden, true, "a spare line is hidden") end
    FS.Config.Set("layout.grid", 4)
    eq(#lineXs(grid), 641, "step 4"); eq(#lineYs(grid), 361)
    -- The Done panel's chips do the same through Config.
    local panel = FS.LayoutEdit.GetDonePanel()
    local chip = panel.stepChips[4]
    eq(chip.fsStep, 32)
    chip._scripts.OnClick(chip)
    eq(FS.Config.Get("layout.grid"), 32)
    eq(#lineXs(grid), 81, "step 32 from the chip"); eq(#lineYs(grid), 45)
    eq(chip.fsSelected, true, "the chip shows it is on")
    eq(#__errors, 0)
end

function T.snap_off_or_show_grid_off_takes_the_grid_away()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    eq(FS.Config.Get("layout.showGrid"), true, "Show grid is on by default")
    FS.LayoutEdit.Enter()
    local grid = gridNow()
    FS.Config.Set("layout.snap", false)
    eq(gridNow(), nil, "snap off hides the grid")
    for _, line in ipairs(grid.v) do eq(line._hidden, true) end
    FS.Config.Set("layout.snap", true)
    eq(#lineXs(gridNow()), 321, "snap on brings it back")
    -- The Done panel's switch writes layout.showGrid.
    local switch = FS.LayoutEdit.GetDonePanel().gridSwitch
    eq(switch.fsOn, true)
    switch._scripts.OnClick(switch)
    eq(FS.Config.Get("layout.showGrid"), false, "the switch is saved as layout.showGrid")
    eq(gridNow(), nil, "Show grid off hides it")
    eq(switch.fsOn, false, "and the switch says so")
    FS.LayoutEdit.Select("stance")
    eq(gridNow(), nil, "a pick does not bring it back")
    switch._scripts.OnClick(switch)
    eq(FS.Config.Get("layout.showGrid"), true)
    eq(#lineXs(gridNow()) > 100, true)
    -- Snapping itself does not depend on the lines.
    FS.Config.Set("layout.showGrid", false)
    dropAt("stance", 13, -40)
    eq(override("stance").x, 16, "snap still rounds with the lines hidden")
    FS.LayoutEdit.Exit()
    FS.Config.Set("layout.showGrid", true)
    eq(gridNow(), nil, "a setting changed outside edit mode shows nothing")
end

function T.the_grid_sits_below_the_handles_above_the_world_and_takes_no_mouse()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local grid = gridNow()
    local order = { BACKGROUND = 1, LOW = 2, MEDIUM = 3, HIGH = 4, DIALOG = 5, FULLSCREEN = 6, FULLSCREEN_DIALOG = 7, TOOLTIP = 8 }
    local h = FS.LayoutEdit.GetHandle("stance")
    eq(order[grid._strata] > order.HIGH, true, "above the world's frames")
    eq(order[grid._strata] < order[h._strata], true, "below the handles")
    eq(grid._mouse, false, "mouse disabled")
    eq(grid._parent, UIParent); eq(grid._protected, nil, "an insecure frame")
    for _, line in ipairs(litLines(grid.v)) do eq(line._mouse, nil) end
end

function T.a_screen_size_change_redraws_the_grid()
    screen(1440)
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local before = lineXs(gridNow())[2]
    __setScreen(1000)
    __fire("DISPLAY_SIZE_CHANGED")
    local xs, ys = lineXs(gridNow()), lineYs(gridNow())
    eq(xs[2] ~= before, true, "the lines moved")
    -- A line rounds to a whole pixel, so the last one may sit up to half a pixel past the edge.
    eq(xs[#xs] <= UIParent._w + 0.5 + 1e-6 and xs[1] >= -1e-6, true, "inside the new width")
    eq(ys[#ys] <= UIParent._h + 0.5 + 1e-6 and ys[1] >= -1e-6, true, "inside the new height")
    eq(#xs >= 319 and #xs <= 323, true, "about 321 lines at step 8")
    near(gridNow().cross[1]._points[1].x, UIParent._w / 2, 0.5 + 1e-6)
    eq(#__errors, 0)
end

-------------------------------------------------------------------------------
-- Position panel
-------------------------------------------------------------------------------

local function posNow() return FS.LayoutEdit.GetPositionPanel() end
-- Types into both boxes and presses Enter in the X box.
local function typed(panel, x, y)
    panel.xBox.edit:SetText(x)
    panel.yBox.edit:SetText(y)
    panel.xBox.edit._scripts.OnEnterPressed(panel.xBox.edit)
end

function T.picking_a_piece_shows_the_position_panel_over_it_and_dropping_the_pick_hides_it()
    edit(); seat("stance"); seat("player")
    FS.LayoutEdit.Enter()
    eq(posNow(), nil, "nothing picked, no panel")
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    eq(panel ~= nil, true, "a panel for the pick")
    eq(panel._parent, UIParent); eq(panel._protected, nil, "an insecure frame")
    eq(panel._strata, "FULLSCREEN_DIALOG")
    local h = FS.LayoutEdit.GetHandle("stance")
    eq(panel._points[1].rel, h, "anchored to the handle, never to the covered frame")
    eq(panel:GetBottom() > h:GetTop(), true, "clear above the handle's ring")
    eq(panel.xBox.edit._kind, "EditBox"); eq(panel.yBox.edit._kind, "EditBox")
    eq(panel._w > 100, true, "seated and sized")
    -- Another pick moves it; a pick at the top of the screen puts it below.
    FS.LayoutEdit.Select("player")
    local top = FS.LayoutEdit.GetHandle("player")
    eq(panel._points[1].rel, top, "it follows the pick")
    eq(panel:GetTop() <= top:GetBottom(), true, "below a piece near the top of the screen")
    eq(panel:GetTop() <= UIParent._h and panel:GetBottom() >= 0, true, "on the screen")
    FS.LayoutEdit.Select(nil)
    eq(posNow(), nil, "dropping the pick hides it")
    FS.LayoutEdit.Select("stance")
    eq(posNow() ~= nil, true)
    FS.LayoutEdit.Exit()
    eq(posNow(), nil, "leaving hides it")
    eq(panel:IsShown(), false)
end

function T.the_fields_show_the_position_and_follow_nudges_and_drags_live()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    eq(panel.xBox.edit:GetText(), "0"); eq(panel.yBox.edit:GetText(), "-427", "the layout's own numbers")
    key("RIGHT")
    eq(panel.xBox.edit:GetText(), "1", "an arrow nudge")
    __shift = true
    key("UP")
    eq(panel.yBox.edit:GetText(), "-419", "Shift nudges by the grid step")
    __shift = false
    local h = FS.LayoutEdit.GetHandle("stance")
    h._scripts.OnDragStart(h)
    local s = FS.Layout.Scale()
    h:ClearAllPoints()
    h:SetPoint("CENTER", UIParent, "CENTER", 13 * s, -203 * s)
    panel._scripts.OnUpdate(panel, 0.1)
    eq(panel.xBox.edit:GetText(), "16", "live: where it would land, snapped")
    eq(panel.yBox.edit:GetText(), "-200")
    h._scripts.OnDragStop(h)
    eq(panel._scripts.OnUpdate, nil, "the live read stops with the drag")
    eq(panel.xBox.edit:GetText(), "16"); eq(panel.yBox.edit:GetText(), "-200")
    eq(override("stance").x, 16)
    -- A box that is being typed in keeps its text while the piece moves.
    panel.xBox.edit:SetFocus()
    panel.xBox.edit:SetText("55")
    FS.LayoutEdit.Nudge(0, 1)
    eq(panel.xBox.edit:GetText(), "55", "the focused box is left alone")
    eq(panel.yBox.edit:GetText(), "-199")
end

function T.enter_commits_a_typed_position_through_the_drag_path_and_it_reads_back_equal()
    edit(); seat("stance")
    local seen = {}
    local setO, reseat = FS.Layout.SetOverride, FS.Layout.Reseat
    FS.Layout.SetOverride = function(id, x, y) seen[#seen + 1] = { id, x, y }; return setO(id, x, y) end
    FS.Layout.Reseat = function(id) seen[#seen + 1] = { "reseat", id }; return reseat(id) end
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    typed(panel, "13", "-401.5")
    eq(#seen, 2, "set then reseat, as a drop does")
    eq(seen[1][1], "stance"); eq(seen[1][2], 13, "exact: not rounded to the grid step"); eq(seen[1][3], -401.5)
    eq(seen[2][1], "reseat")
    eq(override("stance").x, 13); eq(override("stance").y, -401.5)
    eq(panel.xBox.edit:GetText(), "13", "reads back equal"); eq(panel.yBox.edit:GetText(), "-401.5")
    eq(panel.xBox.edit:HasFocus(), false, "Enter lets go of the keyboard")
    eq(panel.yBox.edit:HasFocus(), false)
    local h = FS.LayoutEdit.GetHandle("stance")
    local s = FS.Layout.Scale()
    local cx, cy = h:GetCenter()
    near(cx, UIParent._w / 2 + 13 * s, 1e-6, "the handle follows"); near(cy, UIParent._h / 2 - 401.5 * s, 1e-6)
    -- The same place by a drag (snap off) goes through the same call with the same numbers.
    FS.LayoutEdit.ResetOne("stance")
    seen = {}
    setSnap(false)
    dropAt("stance", 13, -401.5)
    eq(seen[1][1], "stance"); near(seen[1][2], 13, 1e-9); near(seen[1][3], -401.5, 1e-9)
    -- A typed value that is the position it already has writes nothing.
    seen = {}
    typed(panel, "13", "-401.5")
    eq(#seen, 0, "no change, no write")
    eq(__printedHas("could not"), false)
    -- A position with a plus sign, a bare point or spaces around it is still a number.
    typed(panel, "+5", ".5")
    eq(override("stance").x, 5); eq(override("stance").y, 0.5)
    typed(panel, "  12  ", "5.")
    eq(override("stance").x, 12); eq(override("stance").y, 5)
end

function T.grid_units_are_the_position_over_the_grid_step_and_both_modes_read_back_equal()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    eq(FS.Config.Get("layout.posUnit"), "px", "px is the default")
    eq(panel.pxChip.fsSelected, true); eq(panel.gridChip.fsSelected, false)
    eq(panel.xBox.unit._text, "px")
    panel.gridChip._scripts.OnClick(panel.gridChip)
    eq(FS.Config.Get("layout.posUnit"), "grid", "the unit is a saved choice")
    eq(panel.gridChip.fsSelected, true); eq(panel.pxChip.fsSelected, false)
    eq(panel.xBox.unit._text, "grid"); eq(panel.yBox.unit._text, "grid")
    typed(panel, "3", "-50")
    eq(override("stance").x, 24, "3 at step 8 is 24 px"); eq(override("stance").y, -400)
    eq(panel.xBox.edit:GetText(), "3", "reads back as typed"); eq(panel.yBox.edit:GetText(), "-50")
    FS.Config.Set("layout.grid", 16)
    eq(panel.xBox.edit:GetText(), "1.5", "24 px is 1.5 steps of 16"); eq(panel.yBox.edit:GetText(), "-25")
    typed(panel, "3", "2.5")
    eq(override("stance").x, 48, "3 at step 16"); eq(override("stance").y, 40)
    eq(panel.xBox.edit:GetText(), "3"); eq(panel.yBox.edit:GetText(), "2.5")
    panel.pxChip._scripts.OnClick(panel.pxChip)
    eq(FS.Config.Get("layout.posUnit"), "px")
    eq(panel.xBox.edit:GetText(), "48", "the same piece in px"); eq(panel.yBox.edit:GetText(), "40")
    typed(panel, "7", "-9")
    eq(override("stance").x, 7); eq(override("stance").y, -9)
    eq(panel.xBox.edit:GetText(), "7"); eq(panel.yBox.edit:GetText(), "-9")
end

function T.input_that_is_not_a_number_is_refused_with_a_pink_flash_and_writes_nothing()
    edit(); seat("stance")
    local writes = 0
    local setO = FS.Layout.SetOverride
    FS.Layout.SetOverride = function(...) writes = writes + 1; return setO(...) end
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    local function refused(x, y, badX, badY, what)
        panel.xBox.edit:SetText(x); panel.yBox.edit:SetText(y)
        panel.xBox.edit._scripts.OnEnterPressed(panel.xBox.edit)
        eq(writes, 0, what .. " wrote")
        eq(next(frames()), nil, what .. " saved")
        eq(panel.xBox.fsBad, badX, what .. ": X flash"); eq(panel.yBox.fsBad, badY, what .. ": Y flash")
        local bad = badX and panel.xBox or panel.yBox
        near(bad.edges[1]._color[1], 1); near(bad.edges[1]._color[2], 0.18, 1e-6)   -- the pink ring
        for _, fn in ipairs(__timers) do fn() end
        __timers = {}
        eq(panel.xBox.fsBad, false, what .. ": the flash ends"); eq(panel.yBox.fsBad, false)
    end
    for _, text in ipairs({ "abc", "", "  ", "1e3", "0x10", "1,5", "--3", "12abc", "nan", "inf", "1.2.3", "-", ".", "5 5" }) do
        refused(text, "5", true, false, "X '" .. text .. "'")
        refused("5", text, false, true, "Y '" .. text .. "'")
    end
    refused("x", "y", true, true, "both")
    eq(#__errors, 0)
end

function T.a_typed_position_is_clamped_so_the_piece_stays_on_screen()
    edit(); seat("stance"); seat("player"); fakeSeat()
    FS.LayoutEdit.Enter()
    for _, id in ipairs({ "stance", "player", "objectives" }) do
        FS.LayoutEdit.Select(id)
        local panel = posNow()
        for _, pair in ipairs({ { "99999", "99999" }, { "-99999", "-99999" }, { "99999", "-99999" }, { "-99999", "99999" } }) do
            typed(panel, pair[1], pair[2])
            local h = FS.LayoutEdit.GetHandle(id)
            local where = id .. " at " .. pair[1] .. "," .. pair[2]
            eq(h:GetLeft() >= -1e-6, true, where .. " left"); eq(h:GetRight() <= UIParent._w + 1e-6, true, where .. " right")
            eq(h:GetBottom() >= -1e-6, true, where .. " bottom"); eq(h:GetTop() <= UIParent._h + 1e-6, true, where .. " top")
        end
    end
    -- It lands on the edge, not short of it.
    FS.LayoutEdit.Select("stance")
    typed(posNow(), "99999", "0")
    near(FS.LayoutEdit.GetHandle("stance"):GetRight(), UIParent._w, 1e-6, "on the right edge")
    eq(#__errors, 0)
end

function T.esc_puts_the_numbers_back_and_lets_go_of_the_keyboard_and_tab_goes_to_the_other_box()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local panel = posNow()
    local x, y = panel.xBox.edit, panel.yBox.edit
    x:SetFocus()
    eq(x:HasFocus(), true)
    x:SetText("999")
    x._scripts.OnEscapePressed(x)
    eq(x:GetText(), "0", "the number is back"); eq(x:HasFocus(), false, "focus released")
    eq(next(frames()), nil, "Esc writes nothing")
    eq(FS.LayoutEdit.IsEditing(), true, "and does not leave edit mode")
    x:SetFocus()
    x._scripts.OnTabPressed(x)
    eq(y:HasFocus(), true, "Tab moves X to Y")
    y._scripts.OnTabPressed(y)
    eq(x:HasFocus(), true, "and back")
    -- Picking another piece takes the keys back from the box.
    seat("player")
    FS.LayoutEdit.Exit(); FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    posNow().xBox.edit:SetFocus()
    FS.LayoutEdit.Select("player")
    eq(posNow().xBox.edit:HasFocus(), false, "a new pick releases the boxes")
end

function T.the_position_tip_says_what_the_numbers_count_from()
    edit(); seat("stance"); seat("player"); fakeSeat()
    FS.LayoutEdit.Enter()
    local function tipOf(id)
        FS.LayoutEdit.Select(id)
        local panel = posNow()
        eq(panel.help.fsTip ~= nil, true)
        panel.help._scripts.OnEnter(panel.help)
        eq(GameTooltip._text, panel.help.fsTip, "the ? shows it")
        panel.help._scripts.OnLeave(panel.help)
        return panel.help.fsTip
    end
    local function has(text, part, what) eq(text:find(part, 1, true) ~= nil, true, what .. ": '" .. part .. "' in " .. text) end
    local tip = tipOf("stance")
    has(tip, "centre of the screen to the centre of the piece", "stance")
    has(tip, "X grows to the right", "stance"); has(tip, "Y grows up", "stance"); has(tip, "2560 x 1440 design", "stance")
    tip = tipOf("player")
    has(tip, "top left corner of the screen to the top left corner of the piece", "player")
    has(tip, "UI unit", "player")
    tip = tipOf("objectives")
    has(tip, "top right corner of the screen to the top right corner of the piece", "objectives")
    has(tip, "step (now 8)", "objectives")
end

function T.provider_pieces_type_a_position_the_same_way()
    -- The objectives tracker: offsets from the screen's top right, written through its seat.
    local tracker = fakeSeat()
    edit(); FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("objectives")
    local panel = posNow()
    eq(panel.xBox.edit:GetText(), "-29"); eq(panel.yBox.edit:GetText(), "-286")
    typed(panel, "-100", "-401")
    eq(#tracker.moves, 1); eq(tracker.moves[1][1], -100, "exact, not snapped"); eq(tracker.moves[1][2], -401)
    eq(panel.xBox.edit:GetText(), "-100", "reads back")
    near(FS.LayoutEdit.GetHandle("objectives"):GetRight(), UIParent:GetRight() - 100, 1e-6, "the handle follows the seat")
    panel.gridChip._scripts.OnClick(panel.gridChip)
    typed(panel, "-5", "-30")
    eq(tracker.moves[2][1], -40, "-5 steps of 8"); eq(tracker.moves[2][2], -240)
    eq(next(frames()), nil, "nothing written to the STUwave layout")
    FS.LayoutEdit.Exit()
    -- A raid layout, through the preview.
    __session(__layoutSrc, __configSrc, __editSrc)
    local pv = fakePreview()
    edit(); FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("raid10")
    panel = posNow()
    eq(panel ~= nil, true, "a panel for the raid handle")
    eq(panel.xBox.edit:GetText(), "-696.5"); eq(panel.yBox.edit:GetText(), "140")
    typed(panel, "-600", "100")
    eq(override("raid10").x, -600); eq(override("raid10").y, 100)
    local left, top = pv.Rect()
    near(FS.LayoutEdit.GetHandle("raid10"):GetLeft(), left, 1e-6, "the handle follows the seat")
    FS.LayoutEdit.Exit()
    -- A floating pet.
    __session(__layoutSrc, __configSrc, __editSrc)
    edit(); seat("petcontainer")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("petcontainer")
    panel = posNow()
    typed(panel, "-300", "-420")
    eq(override("petcontainer").x, -300); eq(override("petcontainer").y, -420)
    eq(#__errors, 0)
end

-------------------------------------------------------------------------------
-- Right click menu
-------------------------------------------------------------------------------

local function menuNow() return FS.LayoutEdit.GetMenu() end

function T.right_click_opens_a_menu_at_the_cursor_named_for_the_piece()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    eq(menuNow(), nil, "no menu before a right click")
    h._scripts.OnMouseUp(h, "LeftButton")
    eq(menuNow(), nil, "a left click opens none")
    __cursor = { 300, 400 }
    local m = rightClick(h)
    eq(m ~= nil, true)
    eq(m.header._text, "STANCE BAR", "the piece's name, as the muted header")
    eq(m.items.settings.label._text, "Settings"); eq(m.items.position.label._text, "Set position")
    eq(m.items.reset.label._text, "Reset position")
    local p = m.frame._points[1]
    eq(p.point, "TOPLEFT"); eq(p.rel, UIParent); eq(p.relPoint, "BOTTOMLEFT")
    eq(p.x, 304, "just right of the cursor"); eq(p.y, 396, "and just under it")
    -- Near the bottom right corner it opens up and to the left of the cursor.
    __cursor = { UIParent._w - 10, 20 }
    m = rightClick(h)
    eq(m.frame._points[1].x, math.floor(UIParent._w - 10 - 4 - 184 + 0.5))
    eq(m.frame._points[1].y, 20 + 4 + m.height)
    -- A plain insecure frame in the STUwave look: no Blizzard template, above the handles and the panels.
    for _, f in ipairs({ m.catcher, m.frame, m.items.settings, m.items.position, m.items.reset }) do
        eq(f._protected, nil, "insecure"); eq(f._template, nil, "no Blizzard dropdown template")
    end
    eq(m.catcher._parent, UIParent); eq(m.frame._parent, m.catcher)
    eq(m.catcher._level > FS.LayoutEdit.GetDonePanel()._level, true, "above the Done panel")
    eq(m.frame._level > h._level, true, "above the handle")
    local skinned = false
    for _, f in ipairs(__themed.panels) do if f == m.frame then skinned = true end end
    eq(skinned, true, "skinned by Theme.SkinPanel")
    eq(#__errors, 0)
end

function T.a_click_elsewhere_or_esc_closes_the_menu_and_edit_mode_keeps_running()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    local h = FS.LayoutEdit.GetHandle("stance")
    local m = rightClick(h)
    m.catcher._scripts.OnClick(m.catcher, "LeftButton")
    eq(FS.LayoutEdit.IsMenuOpen(), false, "a click elsewhere closes it")
    eq(FS.LayoutEdit.IsEditing(), true)
    rightClick(h)
    local o = key("ESCAPE")
    eq(FS.LayoutEdit.IsMenuOpen(), false, "Esc closes it")
    eq(FS.LayoutEdit.IsEditing(), true, "and does not leave edit mode")
    eq(o._propagate, false, "Esc is taken by the menu")
    key("ESCAPE")
    eq(FS.LayoutEdit.IsEditing(), false, "the next Esc leaves")
    -- Leaving closes it too; so does the start of a drag; arrows do not nudge a piece behind an open menu.
    FS.LayoutEdit.Enter()
    h = FS.LayoutEdit.GetHandle("stance")
    rightClick(h)
    FS.LayoutEdit.Exit()
    eq(FS.LayoutEdit.IsMenuOpen(), false)
    FS.LayoutEdit.Enter()
    h = FS.LayoutEdit.GetHandle("stance")
    rightClick(h)
    h._scripts.OnDragStart(h)
    eq(FS.LayoutEdit.IsMenuOpen(), false, "a drag closes it")
    h._scripts.OnDragStop(h)
    FS.LayoutEdit.Select("stance")
    rightClick(h)
    local before = override("stance").x
    key("RIGHT")
    eq(override("stance").x, before, "an arrow behind an open menu moves nothing")
    -- An open menu does not need a left click to stay put when the piece is picked.
    eq(FS.LayoutEdit.IsMenuOpen(), true)
end

function T.menu_rows_have_hover_pressed_and_greyed_looks()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance"); seat("tooltip")
    FS.LayoutEdit.Enter()
    local m = rightClick(FS.LayoutEdit.GetHandle("stance"))
    local reset = m.items.reset
    near(reset.wash._color[4], 0, 1e-9, "idle")
    reset._scripts.OnEnter(reset);     near(reset.wash._color[4], 0.12, 1e-9, "hover")
    near(reset.label._mono.color[1], 0.133, 1e-6, "the label goes cyan on hover")
    reset._scripts.OnMouseDown(reset); near(reset.wash._color[4], 0.2, 1e-9, "pressed")
    reset._scripts.OnMouseUp(reset);   near(reset.wash._color[4], 0.12, 1e-9)
    reset._scripts.OnLeave(reset);     near(reset.wash._color[4], 0, 1e-9, "idle again")
    -- A row with nothing to open is greyed: no hover wash, dim text, a ? that carries the reason.
    m = rightClick(FS.LayoutEdit.GetHandle("tooltip"))
    local settings = m.items.settings
    eq(settings.fsDisabled, true)
    eq(settings.hint._hidden, false, "the ? shows"); eq(settings.hint._text, "?")
    settings._scripts.OnEnter(settings)
    near(settings.wash._color[4], 0, 1e-9, "a greyed row takes no hover wash")
    near(settings.label._mono.color[1], 0.361, 1e-6, "dim text")
end

function T.settings_opens_the_config_window_on_the_pieces_page_tab_and_row_and_edit_mode_keeps_running()
    local win = fakeWindow()
    FS.ConfigWindow = win
    edit(); seat("stance"); seat("player"); fakeSeat()
    FS.LayoutEdit.Enter()
    local cases = {
        { "stance", "ab", "g", nil },
        { "player", "unit", "bars", "bars.w" },
        { "objectives", "track", "g", "tracker.w" },
    }
    for _, want in ipairs(cases) do
        win.openCalls, win.shown = {}, false
        menuPick(FS.LayoutEdit.GetHandle(want[1]), "settings")
        eq(#win.openCalls, 1, want[1] .. ": one call")
        eq(win.openCalls[1].page, want[2], want[1] .. " page"); eq(win.openCalls[1].tab, want[3], want[1] .. " tab")
        eq(win.openCalls[1].row, want[4], want[1] .. " row")
        eq(FS.LayoutEdit.IsEditing(), true, "edit mode keeps running")
        eq(FS.LayoutEdit.IsMenuOpen(), false, "the menu closes on a pick")
    end
    -- Every id in the map goes where the map says; a piece with none opens nothing.
    local pieces = FS.LayoutEdit.GetPieces()
    for id, entry in pairs(pieces) do
        win.openCalls = {}
        local ok = FS.LayoutEdit.OpenSettings(id)
        if entry.none then
            eq(ok, false, id .. " has none"); eq(#win.openCalls, 0)
        else
            eq(ok, true, id); eq(win.openCalls[1].page, entry.page); eq(win.openCalls[1].tab, entry.tab)
            eq(win.openCalls[1].row, entry.row)
        end
    end
end

function T.settings_works_with_a_window_that_only_takes_a_page_and_one_that_throws()
    local win = fakeWindow()
    FS.ConfigWindow = win
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    -- The older window: Open(page) only; extra arguments are ignored.
    function win.Open(page) win.opened[#win.opened + 1] = page; win.shown = true end
    eq(FS.LayoutEdit.OpenSettings("player"), true)
    eq(win.opened[#win.opened], "unit")
    -- A window that throws is reported and does not leave the editor.
    function win.Open() error("boom") end
    eq(FS.LayoutEdit.OpenSettings("player"), false)
    eq(FS.LayoutEdit.IsEditing(), true)
    eq(#__errors >= 1, true, "the error is forwarded")
end

function T.the_editor_drops_under_the_config_window_while_it_is_up_and_comes_back_after()
    local win = fakeWindow()
    FS.ConfigWindow = win
    edit(); seat("stance")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("stance")
    local h = FS.LayoutEdit.GetHandle("stance")
    local done, pos, grid = FS.LayoutEdit.GetDonePanel(), posNow(), gridNow()
    local order = { BACKGROUND = 1, LOW = 2, MEDIUM = 3, HIGH = 4, DIALOG = 5, FULLSCREEN = 6, FULLSCREEN_DIALOG = 7, TOOLTIP = 8 }
    eq(h._strata, "FULLSCREEN_DIALOG"); eq(grid._strata, "FULLSCREEN")
    menuPick(h, "settings")
    -- The config window is a DIALOG strata frame: the editor's frames must sit below it.
    for name, f in pairs({ handle = h, done = done, position = pos, grid = grid }) do
        eq(order[f._strata] < order.DIALOG, true, name .. " is under the config window")
    end
    eq(FS.LayoutEdit.IsEditing(), true)
    -- Keys belong to the window while it is up (Esc closes it); they reach the game.
    local o = key("ESCAPE")
    eq(o._propagate, true, "Esc goes to the window")
    eq(FS.LayoutEdit.IsEditing(), true, "and does not leave edit mode")
    -- A handle that appears while the window is up is made under it too.
    eq(order[FS.LayoutEdit.GetHandle("stance")._strata] < order.DIALOG, true)
    win.Close()
    done._scripts.OnUpdate(done, 0.3)
    eq(h._strata, "FULLSCREEN_DIALOG", "the handles are back above the world"); eq(done._strata, "FULLSCREEN_DIALOG")
    eq(pos._strata, "FULLSCREEN_DIALOG"); eq(grid._strata, "FULLSCREEN")
    key("ESCAPE")
    eq(FS.LayoutEdit.IsEditing(), false, "Esc is the editor's again")
end

function T.settings_is_greyed_with_a_tip_for_a_piece_with_no_settings()
    local win = fakeWindow()
    FS.ConfigWindow = win
    edit(); seat("tooltip"); seat("stance"); seat("tcast")
    FS.LayoutEdit.Enter()
    for _, id in ipairs({ "tooltip", "tcast" }) do
        local m = rightClick(FS.LayoutEdit.GetHandle(id))
        local item = m.items.settings
        eq(item.fsDisabled, true, id .. " has no settings")
        item._scripts.OnClick(item)
        eq(#win.openCalls, 0, "a greyed row opens nothing")
        eq(FS.LayoutEdit.IsMenuOpen(), true, "and leaves the menu up")
        item._scripts.OnEnter(item)
        eq(GameTooltip._text, "This piece has no settings.")
        eq(GameTooltip._owner, item)
        item._scripts.OnLeave(item)
        eq(GameTooltip._shown, false)
        eq(m.items.position.fsDisabled, false, "Set position stays on"); eq(m.items.reset.fsDisabled, false)
        FS.LayoutEdit.CloseMenu()
    end
    local m = rightClick(FS.LayoutEdit.GetHandle("stance"))
    eq(m.items.settings.fsDisabled, false, "a piece with settings is live")
    eq(m.items.settings.hint._hidden, true, "and has no ?")
    -- The tooltip row is not sticky: the next menu repaints it.
    FS.LayoutEdit.CloseMenu()
    -- No config window at all: Settings is greyed and says why.
    FS.ConfigWindow = nil
    m = rightClick(FS.LayoutEdit.GetHandle("stance"))
    eq(m.items.settings.fsDisabled, true)
    m.items.settings._scripts.OnEnter(m.items.settings)
    eq(GameTooltip._text, "The config window is not available.")
end

function T.set_position_picks_the_piece_and_puts_the_cursor_in_its_x_box()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance"); seat("player")
    FS.LayoutEdit.Enter()
    FS.LayoutEdit.Select("player")
    local h = FS.LayoutEdit.GetHandle("stance")
    menuPick(h, "position")
    eq(FS.LayoutEdit.IsMenuOpen(), false)
    local panel = posNow()
    eq(panel._points[1].rel, h, "the panel is over the piece that was clicked")
    eq(panel.xBox.edit:HasFocus(), true, "the cursor is in X"); eq(panel.yBox.edit:HasFocus(), false)
    eq(panel.xBox.edit:GetText(), "0")
    typed(panel, "40", "-300")
    eq(override("stance").x, 40, "typed through the menu path"); eq(override("stance").y, -300)
    eq(panel.xBox.edit:HasFocus(), false, "focus released")
    -- A piece with no handle opens nothing.
    eq(FS.LayoutEdit.FocusPosition("chat"), false)
end

function T.reset_position_is_reset_one_for_the_clicked_piece_only()
    FS.ConfigWindow = fakeWindow()
    edit(); seat("stance"); seat("player")
    local asked = {}
    local one = FS.LayoutEdit.ResetOne
    FS.LayoutEdit.ResetOne = function(id) asked[#asked + 1] = id; return one(id) end
    FS.LayoutEdit.Enter()
    setSnap(false)
    dropAt("stance", 100, 100); dropAt("player", 50, -50)
    FS.LayoutEdit.Select("player")
    menuPick(FS.LayoutEdit.GetHandle("stance"), "reset")
    eq(table.concat(asked, ","), "stance")
    eq(override("stance"), nil, "the clicked piece is home"); eq(override("player") ~= nil, true, "the picked one is not")
end

function T.every_handle_id_has_a_settings_map_entry_and_its_row_exists_in_the_window()
    FS.ConfigWindow = fakeWindow()
    edit()
    local pieces = FS.LayoutEdit.GetPieces()
    local ids, known = FS.LayoutEdit.MovableIds(), {}
    for _, id in ipairs(ids) do
        known[id] = true
        local e = pieces[id]
        eq(e ~= nil, true, "no Settings map entry for the handle '" .. id .. "'")
        if not e.none then
            eq(type(e.page), "string", id .. " needs a page"); eq(type(e.tab), "string", id .. " needs a tab")
        end
        eq(e.row == nil or type(e.row) == "string", true, id .. " row")
    end
    for id in pairs(pieces) do eq(known[id], true, "a map entry for '" .. id .. "', which has no handle") end
    -- The row keys must be rows of the window (CW.Rows) wherever the window has the registry; a missing one is reported.
    local function missing(window)
        local rows = window.Rows
        if type(rows) == "function" then rows = rows() end
        if type(rows) ~= "table" then return nil end
        local out = {}
        for id, e in pairs(pieces) do
            if e.row and not e.none then
                local found = rows[e.row] ~= nil
                for _, r in ipairs(rows) do
                    if r.key == e.row and (r.page == nil or r.page == e.page) then found = true end
                end
                if not found then out[#out + 1] = id .. ":" .. e.row end
            end
        end
        table.sort(out)
        return out
    end
    local all = {}
    for _, e in pairs(pieces) do
        if e.row then all[#all + 1] = { key = e.row, page = e.page, tab = e.tab } end
    end
    local win = fakeWindow()
    win.Rows = function() return all end
    eq(#missing(win), 0, "every row key is in a complete registry")
    local short = {}
    for _, r in ipairs(all) do if r.key ~= "tracker.w" then short[#short + 1] = r end end
    win.Rows = function() return short end
    eq(table.concat(missing(win), ","), "objectives:tracker.w", "a row the registry lacks is found")
    eq(missing(fakeWindow()), nil, "no registry, nothing to check")
    -- And against whatever window is loaded.
    if FS.ConfigWindow and FS.ConfigWindow.Rows then eq(#missing(FS.ConfigWindow), 0, "rows missing from the loaded window") end
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
