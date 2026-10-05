#!/usr/bin/env python3
"""Runs the real Layout.lua and ChatWindowState.lua headless against a small mock WoW API.

Bug (playtest 2026-10-04): on the FIRST login of a new character the chat sat too high
and only /reload put it right. ChatFrame1 is an Edit Mode system frame on this client:
EDIT_MODE_LAYOUTS_UPDATED runs EditModeManagerFrame:UpdateLayoutInfo, which parks every
system at TOPLEFT 0,0 (InitSystemAnchors) and then runs each system's UpdateSystem
(ApplySystemAnchor, then the settings SetSize, then OnSystemPositionChange, which READS
GetPoint(1) back into the layout's anchorInfo). On a fresh character that lands after our
seat. The mock models that real order and Blizzard's SetPointOverride (which writes
EditModeManagerFrame.editModeSystemAnchorDirty). These checks pin that:

  * the re-seat runs from an UpdateLayoutInfo post-hook, i.e. AFTER every system applied,
    so the layout's anchorInfo is never our seat and our size is not overwritten;
  * the ApplySystemAnchor hook is log-only and defers the re-seat a frame (Reset paths);
  * our seat goes through ClearAllPointsBase/SetPointBase, so it never writes the Edit
    Mode dirty flag under our taint, and falls back to plain calls without them;
  * the EDIT_MODE_LAYOUTS_UPDATED watcher and the first PLAYER_ENTERING_WORLD of a login
    or reload (not a zone change) also re-seat, without recursing;
  * a maximised or minimised chat goes back through ApplyWindowState;
  * a protected chat frame is left alone in combat and seated when combat ends;
  * every seat and every foreign move is logged in ForeverSynthwaveDB.chatSeatLog (capped
    at 20, the first 10 pinned), our own seat is never logged as foreign, and the
    seating flag is reset when a seat throws.

Layout.lua and ChatWindowState.lua are the real files; the frames are a recording mock,
NOT the real client.

    python3 tools/chatreseat-harness.py

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

ADDON = Path(__file__).resolve().parent.parent

MOCK = r"""
__combat = false
__blocked = 0
__frames = {}
__now = 0

local Frame = {}
Frame.__index = Frame
local function guarded(self)
    if __combat and self._protected then __blocked = __blocked + 1; return true end
end
function Frame:ClearAllPoints() if guarded(self) then return end; self._points = {} end
function Frame:SetPoint(point, rel, relPoint, x, y)
    if guarded(self) then return end
    self._points[#self._points + 1] = { point = point, rel = rel, relPoint = relPoint, x = x, y = y }
end
function Frame:GetPoint(i)
    local p = self._points[i or 1]
    if not p then return end
    return p.point, p.rel, p.relPoint, p.x, p.y
end
function Frame:GetNumPoints() return #self._points end
function Frame:SetSize(w, h) if guarded(self) then return end; self._w, self._h = w, h end
function Frame:SetHeight(h) self._h = h end
function Frame:GetHeight() return self._h end
function Frame:GetWidth() return self._w end
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:UnregisterEvent(e) self._events[e] = nil end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:IsProtected() return self._protected or false end
function Frame:GetTop() return 1440 end
function Frame:GetEffectiveScale() return 1 end
function Frame:GetBottom() return self._bottom end
function Frame:GetLeft() return self._left end
function Frame:Show() self._shown = true end
function Frame:Hide() self._shown = false end
__Frame = Frame

function CreateFrame()
    local f = setmetatable({ _points = {}, _events = {}, _scripts = {} }, Frame)
    __frames[#__frames + 1] = f
    return f
end
function InCombatLockdown() return __combat end
function GetTime() __now = __now + 1; return __now end
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end

-- hooksecurefunc(tbl, name, fn): the original runs first, then fn with the same arguments.
function hooksecurefunc(tbl, name, fn)
    local orig = tbl[name]
    assert(type(orig) == "function", "hooksecurefunc: " .. tostring(name) .. " is not a function")
    tbl[name] = function(...)
        local r = { orig(...) }
        fn(...)
        return unpack(r)
    end
end

-- The client's error handler: every forwarded error lands here.
__errors = {}
function geterrorhandler() return function(e) __errors[#__errors + 1] = e end end

__timers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
function __flush()
    local run = __timers
    __timers = {}
    for _, fn in ipairs(run) do fn() end
end

UIParent = CreateFrame()
UIParent:SetHeight(1440)

ForeverSynthwaveDB = {}
"""

LOAD = r"""
function(file, src, fs)
    local chunk = assert(load(src, "@" .. file))
    chunk("ForeverSynthwave", fs)
end
"""

# Blizzard's ChatFrame1 as Edit Mode builds it: SetPoint is already an override on the frame,
# and ApplySystemAnchor is a method that clears and re-anchors it.
CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

-- Edit Mode's layout for ChatFrame1: where its saved anchor and size say it goes.
local LAYOUT_POINT, LAYOUT_X, LAYOUT_Y, LAYOUT_W, LAYOUT_H = "BOTTOMLEFT", 0, 100, 480, 200

-- ChatFrame1 as Edit Mode builds it. SetPoint/ClearAllPoints are the overrides
-- (EditModeSystemMixin:OnSystemLoad); the stored originals are the *Base fields.
-- opts: noBase, noApplySystemAnchor, noManager, protected.
local function newChat(opts)
    opts = opts or {}
    local f = CreateFrame()
    f._protected = opts.protected
    local rawClear, rawSet = __Frame.ClearAllPoints, __Frame.SetPoint

    local emm = EditModeManagerFrame
    if opts.noManager then
        EditModeManagerFrame = nil
        emm = nil
    else
        emm.dirtyWrites = 0
        emm.anchorInfo = { point = LAYOUT_POINT, x = LAYOUT_X, y = LAYOUT_Y }
        emm.isInDefaultPosition = true
        -- EditModeManagerFrameMixin:UpdateLayoutInfo: InitSystemAnchors, then UpdateSystems.
        emm.apply = function()
            f:ClearAllPoints()
            f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
            if f.cluster then
                f.cluster:ClearAllPoints()
                f.cluster:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
            end
            f:UpdateSystem()
        end
    end
    -- Blizzard's manager registered first, so its handler runs before ours.
    local manager = CreateFrame()
    table.remove(__frames)
    table.insert(__frames, 1, manager)   -- registered before every addon: runs first
    manager:RegisterEvent("EDIT_MODE_LAYOUTS_UPDATED")
    -- The engine isolates handlers: a throw reaches the error handler, not the next handler.
    manager:SetScript("OnEvent", function() if emm then pcall(emm.UpdateLayoutInfo, emm) end end)

    if not opts.noBase then
        f.ClearAllPointsBase = rawClear
        f.SetPointBase = rawSet
    end
    function f:ClearAllPoints() rawClear(self) end
    function f:SetPoint(...)
        rawSet(self, ...)
        if emm then emm.dirtyWrites = emm.dirtyWrites + 1 end
    end

    f.applyCount = 0
    function f:OnSystemPositionChange()   -- UpdateSystemAnchorInfo
        local point, _, _, x, y = self:GetPoint(1)
        local a = emm.anchorInfo
        if a.point ~= point or a.x ~= x or a.y ~= y then
            a.point, a.x, a.y = point, x, y
            emm.isInDefaultPosition = false
        end
    end
    if not opts.noApplySystemAnchor then
        function f:ApplySystemAnchor()
            self.applyCount = self.applyCount + 1
            self:ClearAllPoints()
            self:SetPoint(LAYOUT_POINT, UIParent, LAYOUT_POINT, LAYOUT_X, LAYOUT_Y)
        end
    end
    -- EditModeSystemMixin:UpdateSystem: anchor, then settings SetSize, then position read-back.
    function f:UpdateSystem()
        if self.ApplySystemAnchor then self:ApplySystemAnchor() end
        self:SetSize(LAYOUT_W, LAYOUT_H)
        if emm then self:OnSystemPositionChange() end
    end
    ChatFrame1 = f
    return f
end

-- MinimapCluster: another Edit Mode system seated through Layout.Apply.
local function newCluster(f, opts)
    opts = opts or {}
    local c = CreateFrame()
    c._protected = opts.protected
    local rawClear, rawSet = __Frame.ClearAllPoints, __Frame.SetPoint
    c.ClearAllPointsBase, c.SetPointBase = rawClear, rawSet
    function c:ClearAllPoints() rawClear(self) end
    function c:SetPoint(...)
        rawSet(self, ...)
        local e = EditModeManagerFrame
        if e then e.dirtyWrites = e.dirtyWrites + 1 end
    end
    f.cluster = c
    FS.Layout.Apply(c, "minimap")
    return c
end

local function atLayout(frame, id)
    local p = frame._points[1]
    local s = FS.Layout.Scale()
    local L = FS.Layout[id]
    return #frame._points == 1 and p.point == L.point and p.relPoint == L.relPoint
        and p.x == L.x * s and p.y == L.y * s and frame._w == L.w * s and frame._h == L.h * s
end

local function setup(opts)
    local f = newChat(opts)
    FS.Chat.windowState = "normal"
    FS.Chat.HookPrimaryChatReseat()
    FS.Chat.SeatPrimaryChat(f)
    return f
end

local function seatedAtLayout(f)
    local p = f._points[1]
    local s = FS.Layout.Scale()
    local L = FS.Layout.chat
    return #f._points == 1 and p.point == L.point and p.relPoint == L.relPoint
        and p.x == L.x * s and p.y == L.y * s and f._w == L.w * s and f._h == L.h * s
end

local function noForeignSetPoint()
    for _, e in ipairs(ForeverSynthwaveDB.chatSeatLog) do
        if e.ev == "SetPoint" then return false end
    end
    return true
end

local function evs()
    local set = {}
    for _, e in ipairs(ForeverSynthwaveDB.chatSeatLog) do set[e.ev] = true end
    return set
end

function T.update_layout_info_posthook_reseats_after_every_system_applied()
    local f = setup()
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(seatedAtLayout(f), true, "back at our seat, with our size, right after the call")
end

function T.the_layouts_anchor_info_is_never_our_seat()
    local f = setup()
    EditModeManagerFrame:UpdateLayoutInfo()
    local a = EditModeManagerFrame.anchorInfo
    eq(a.point, LAYOUT_POINT, "OnSystemPositionChange read Blizzard's own anchor, not ours")
    eq(a.x, LAYOUT_X)
    eq(a.y, LAYOUT_Y)
    eq(EditModeManagerFrame.isInDefaultPosition, true, "the layout still says default position")
    __flush()
    eq(EditModeManagerFrame.anchorInfo.point, LAYOUT_POINT, "and still does after the deferred pass")
end

function T.the_event_and_the_posthook_together_in_blizzards_call_order()
    local f = setup()
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(seatedAtLayout(f), true, "seated once both triggers have run")
    eq(EditModeManagerFrame.anchorInfo.point, LAYOUT_POINT, "layout untouched")
    eq(EditModeManagerFrame.isInDefaultPosition, true)
    eq(#f._points, 1, "one anchor, not stacked")
    __flush()
    eq(seatedAtLayout(f), true, "the deferred pass changes nothing")
end

function T.the_apply_system_anchor_hook_is_log_only_and_defers_the_reseat()
    local f = setup()
    f:ApplySystemAnchor()   -- a Reset-to-default path: no UpdateLayoutInfo around it
    eq(seatedAtLayout(f), false, "not re-seated in the middle of Blizzard's call")
    eq(evs()["ApplySystemAnchor"], true, "but the call is logged")
    __flush()
    eq(seatedAtLayout(f), true, "re-seated a frame later")
end

function T.the_reseat_does_not_write_the_edit_mode_dirty_flag()
    local f = setup()
    local before = EditModeManagerFrame.dirtyWrites
    FS.Chat.ReassertPrimaryChat()
    eq(EditModeManagerFrame.dirtyWrites, before, "SetPointOverride never ran under our taint")
    FS.Chat.SeatPrimaryChat(f)
    eq(EditModeManagerFrame.dirtyWrites, before, "nor from a plain seat")
    FS.Layout.Apply(f, "chat")
    eq(EditModeManagerFrame.dirtyWrites, before, "nor from the Layout watcher's Apply")
end

function T.without_the_base_methods_it_falls_back_to_plain_calls()
    local f = setup({ noBase = true })
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(seatedAtLayout(f), true)
    for _, e in ipairs(ForeverSynthwaveDB.chatSeatLog) do
        eq(e.ev == "SetPoint" and e.pt == "CENTER", false, "our CENTER seat is not logged as a foreign move")
    end
end

function T.without_edit_mode_manager_the_event_alone_corrects_it()
    local f = setup({ noManager = true, noApplySystemAnchor = true })
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    f:SetSize(300, 200)
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(seatedAtLayout(f), true)
end

function T.the_first_world_entry_of_a_login_or_reload_reseats_but_a_zone_change_does_not()
    local f = setup()
    EditModeManagerFrame:UpdateLayoutInfo()
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    __fire("PLAYER_ENTERING_WORLD", false, false)
    eq(seatedAtLayout(f), false, "a plain zone change leaves it alone")
    __fire("PLAYER_ENTERING_WORLD", true, false)
    eq(seatedAtLayout(f), true, "initial login re-seats")
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    __fire("PLAYER_ENTERING_WORLD", false, true)
    eq(seatedAtLayout(f), true, "reload re-seats")
end

function T.a_reentrant_reassert_from_our_own_seat_does_not_seat_twice()
    local f = setup()
    -- Pathological: while we seat, something re-enters the re-seat.
    local seats, realApply = 0, FS.Layout.Apply
    FS.Layout.Apply = function(...)
        seats = seats + 1
        if seats == 1 then FS.Chat.ReassertPrimaryChat() end
        return realApply(...)
    end
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(seats, 1, "the nested call was refused by the guard")
    eq(seatedAtLayout(f), true)
end

function T.a_non_normal_window_state_goes_back_through_apply_window_state()
    local f = setup()
    local calls = 0
    FS.Chat.ApplyWindowState = function() calls = calls + 1 end
    FS.Chat.windowState = "max"
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(calls, 1, "max re-derives through ApplyWindowState")
    FS.Chat.windowState = "min"
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(calls, 2, "so does min")
    FS.Chat.windowState = "normal"
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(calls, 2, "normal is a bare seat")
end

function T.a_protected_chat_frame_is_left_alone_in_combat_and_seated_after()
    local f = setup({ protected = true })
    EditModeManagerFrame:UpdateLayoutInfo()   -- settles: seated (out of combat)
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    eq(seatedAtLayout(f), false, "Blizzard moved it out of combat")
    __combat = true
    local before = __blocked
    f:ApplySystemAnchor()
    __flush()
    eq(__blocked - before, 2, "only Blizzard's ClearAllPoints and SetPoint were refused; we attempted nothing")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(seatedAtLayout(f), true, "seated once combat ends")
    eq(__blocked - before, 2, "and that seat was not blocked")
end

function T.every_seat_and_foreign_move_is_logged()
    local f = setup()
    local log = ForeverSynthwaveDB.chatSeatLog
    eq(log[#log].ev, "seat", "our own seat is recorded")
    EditModeManagerFrame:UpdateLayoutInfo()
    local e = evs()
    for _, name in ipairs({ "SetPoint", "ApplySystemAnchor", "UpdateLayoutInfo", "reseat" }) do
        eq(e[name], true, name .. " is recorded")
    end
    eq(type(log[1].t), "number", "stamped with GetTime")
    __fire("UI_SCALE_CHANGED")
    __fire("DISPLAY_SIZE_CHANGED")
    __fire("UPDATE_CHAT_WINDOWS")
    e = evs()
    eq(e["UI_SCALE_CHANGED"] and e["DISPLAY_SIZE_CHANGED"] and e["UPDATE_CHAT_WINDOWS"], true, "scale and window events too")
end

function T.the_log_is_capped_and_pins_the_first_ten()
    local f = setup()
    for i = 1, 15 do f:ClearAllPoints(); f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", i, i) end
    local log = ForeverSynthwaveDB.chatSeatLog
    local firstTen = {}
    for i = 1, 10 do firstTen[i] = tostring(log[i].ev) .. ":" .. tostring(log[i].x) end
    for i = 16, 115 do f:ClearAllPoints(); f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", i, i) end
    eq(#log, 20, "capped at 20")
    for i = 1, 10 do
        eq(tostring(log[i].ev) .. ":" .. tostring(log[i].x), firstTen[i], "entry " .. i .. " is the session's own early one")
    end
    eq(log[20].x, 115, "the tail is rolling")
end

function T.our_own_seat_is_not_logged_as_a_foreign_move()
    local f = setup({ noBase = true })
    FS.Chat.SeatPrimaryChat(f)
    eq(noForeignSetPoint(), true, "SeatPrimaryChat")
    UIParent:SetHeight(720)
    __fire("UI_SCALE_CHANGED")   -- the Layout watcher re-seats the chat frame through Apply
    eq(noForeignSetPoint(), true, "the Layout watcher's re-seat")
    eq(FS.Layout.applying, false, "flag reset")
end

function T.the_seating_flag_is_reset_when_a_seat_throws()
    local f = setup({ noBase = true })
    f._bottom, f._left = 100, 50
    FS.Chat.PAD_TOP = 40
    local realApply = FS.Layout.Apply
    FS.Layout.Apply = function() error("boom") end
    eq(pcall(FS.Chat.SeatPrimaryChat, f), false, "the error still surfaces")
    eq(FS.Chat.seating, false, "seating reset after a throwing seat")
    FS.Layout.Apply = realApply

    -- The maximise branch of the real ApplyWindowState, with SetHeight throwing mid-way.
    FS.Chat.windowState = "max"
    f._h = 200
    f.SetHeight = function() error("boom") end
    eq(pcall(FS.Chat.ApplyWindowState), false, "the error still surfaces")
    eq(FS.Chat.seating, false, "seating reset after a throwing maximise")
end

function T.a_throwing_layout_apply_resets_its_flag()
    local f = setup()
    f.SetSize = function() error("boom") end
    eq(pcall(FS.Layout.Apply, f, "chat"), false)
    eq(FS.Layout.applying, false)
end

function T.the_previous_sessions_log_is_kept_for_the_bug_report()
    ForeverSynthwaveDB.chatSeatLog = { { ev = "old" } }
    setup()
    eq(ForeverSynthwaveDB.chatSeatLogPrev[1].ev, "old")
end

function T.minimap_cluster_is_reseated_after_update_layout_info_and_rescale_callbacks_run()
    local f = setup()
    local c = newCluster(f)
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    local before = EditModeManagerFrame.dirtyWrites
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(atLayout(c, "minimap"), true, "the cluster is back at the layout's minimap seat")
    eq(runs, 1, "the size-dependent callbacks ran once, after the move")
    eq(seatedAtLayout(f), true, "and the chat is still seated")
    -- Blizzard's own SetPoint calls bump the counter (two parks); ours must add none.
    eq(EditModeManagerFrame.dirtyWrites - before, 3, "only Blizzard's three SetPoints wrote the dirty flag")
end

function T.the_chat_is_seated_once_by_its_own_hook_not_twice_by_layout()
    local f = setup()
    newCluster(f)
    local chatSeats, realApply = 0, FS.Layout.Apply
    FS.Layout.Apply = function(frame, id, ...)
        if id == "chat" then chatSeats = chatSeats + 1 end
        return realApply(frame, id, ...)
    end
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(chatSeats, 1, "Layout's generic re-seat skips the chat")
end

function T.the_layouts_updated_event_reseats_the_cluster_when_the_posthook_is_missing()
    -- A fresh Layout.lua loaded while Blizzard_EditMode is absent never installs the
    -- post-hook, so its own event watcher is the only path.
    EditModeManagerFrame = nil
    local FS2 = { Chat = FS.Chat }
    __load("Layout.lua", __layoutSrc, FS2)
    local c = CreateFrame()
    c.ClearAllPointsBase, c.SetPointBase = __Frame.ClearAllPoints, __Frame.SetPoint
    FS2.Layout.Apply(c, "minimap")
    c:ClearAllPoints()
    c:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    local runs = 0
    FS2.Layout.OnRescale(function() runs = runs + 1 end)
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(c._points[1].point, FS2.Layout.minimap.point, "the event path re-seated the frame")
    eq(runs, 1, "and ran the callbacks")
end

function T.a_frame_without_the_edit_mode_base_calls_is_not_touched()
    local f = setup()
    local plain = CreateFrame()
    FS.Layout.Apply(plain, "stance")
    plain:ClearAllPoints()
    plain:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 3, 3)
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(plain._points[1].x, 3, "ordinary Layout frames are not re-seated by the Edit Mode hook")
end

function T.a_protected_cluster_is_held_in_combat_and_seated_when_it_ends()
    local f = setup()
    local c = newCluster(f, { protected = true })
    EditModeManagerFrame:UpdateLayoutInfo()
    c:ClearAllPoints()
    c:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    __combat = true
    local before = __blocked
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(__blocked - before, 2, "only Blizzard's own park of the cluster was refused")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(atLayout(c, "minimap"), true, "seated after combat")
end

function T.layout_apply_keeps_the_inner_stack_when_it_rethrows()
    local f = CreateFrame()
    f.SetSize = function() error("inner boom") end
    local ok, err = pcall(FS.Layout.Apply, f, "chat")
    eq(ok, false)
    eq(type(err) == "string" and err:find("inner boom", 1, true) ~= nil, true, "original message kept")
    eq(err:find("stack traceback", 1, true) ~= nil or err:find("in function", 1, true) ~= nil, true,
        "and the stack at the throw site rides along")
end

function T.layout_hooks_edit_mode_when_blizzard_edit_mode_loads_late()
    local FS2 = { Chat = FS.Chat }
    EditModeManagerFrame = nil
    __load("Layout.lua", __layoutSrc, FS2)
    local emm = { calls = 0 }
    function emm:UpdateLayoutInfo() self.calls = self.calls + 1 end
    EditModeManagerFrame = emm
    __fire("ADDON_LOADED", "Blizzard_EditMode")
    local f = CreateFrame()
    f.ClearAllPointsBase, f.SetPointBase = __Frame.ClearAllPoints, __Frame.SetPoint
    FS2.Layout.Apply(f, "minimap")
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    emm:UpdateLayoutInfo()
    eq(f._points[1].point, FS2.Layout.minimap.point, "the late hook re-seated the frame")
end

-- Another Edit Mode system seated through Layout.Apply under any layout id.
local function seatEditModeFrame(id)
    local c = CreateFrame()
    local rawClear, rawSet = __Frame.ClearAllPoints, __Frame.SetPoint
    c.ClearAllPointsBase, c.SetPointBase = rawClear, rawSet
    FS.Layout.Apply(c, id)
    c:ClearAllPoints()
    c:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    return c
end

function T.the_layouts_updated_event_after_the_posthook_reseats_once_not_twice()
    local f = setup()
    newCluster(f)
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    -- Blizzard's OnEvent runs UpdateLayoutInfo (our post-hook re-seats); our own event
    -- watcher must then stand down instead of re-seating and running every callback again.
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(runs, 1, "callbacks ran once for one event")
end

-- pairs order is not ours to pick, so each frame takes a turn at throwing (one client each).
local function throwingFrameCase(badId)
    local f = setup()
    local goodId = badId == "minimap" and "stance" or "minimap"
    local bad, good = seatEditModeFrame(badId), seatEditModeFrame(goodId)
    bad.SetSize = function() error("boom " .. badId) end
    local ran = false
    FS.Layout.OnRescale(function() ran = true end)
    local ok = pcall(EditModeManagerFrame.UpdateLayoutInfo, EditModeManagerFrame)
    eq(atLayout(good, goodId), true, goodId .. " re-seated although " .. badId .. " threw")
    eq(ran, true, "the rescale callbacks still ran")
    eq(ok, true, "the hook does not throw into Blizzard's caller")
    eq(#__errors, 1, "the failure reaches the error handler exactly once")
    eq(__errors[1]:find("boom " .. badId, 1, true) ~= nil, true, "with the original message")
end

function T.a_throwing_minimap_frame_does_not_skip_the_others_or_the_callbacks()
    throwingFrameCase("minimap")
end

function T.a_throwing_stance_frame_does_not_skip_the_others_or_the_callbacks()
    throwingFrameCase("stance")
end

function T.calltraced_uses_the_error_alone_when_the_stack_is_secret()
    local SECRET = "SECRET-STACK"
    debugstack = function() return SECRET end
    issecretvalue = function(v) return v == SECRET end
    local ok, err = FS.Layout.CallTraced(function() error("real error", 0) end)
    eq(ok, false)
    eq(err, "real error", "the real error survives, with no stack appended")
end

function T.calltraced_uses_the_error_alone_when_debugstack_throws()
    debugstack = function() error("no stack for you") end
    local ok, err = FS.Layout.CallTraced(function() error("real error", 0) end)
    eq(ok, false)
    eq(err, "real error")
end

function T.calltraced_appends_a_plain_stack()
    debugstack = function() return "FRAMES" end
    local ok, err = FS.Layout.CallTraced(function() error("real error", 0) end)
    eq(err, "real error\nFRAMES")
end

function T.a_rethrown_chat_error_carries_one_stack_not_two()
    local f = setup()
    f.SetSize = function() error("inner boom") end
    local ok, err = pcall(FS.Chat.ReassertPrimaryChat)
    eq(ok, false)
    eq(type(err) == "string" and err:find("inner boom", 1, true) ~= nil, true, "message kept")
    local _, n = err:gsub("stack traceback:", "")
    eq(n, 1, "exactly one stack trace")
end

function T.a_throwing_apply_in_the_hook_does_not_unwind_blizzards_caller()
    local f = setup()
    local bad = seatEditModeFrame("minimap")
    bad.SetSize = function() error("boom hook") end
    -- Blizzard's EditModeManagerFrame calls UpdateLayoutInfo and then goes on
    -- (UpdateTopFramePositions, NotifyChatOfLayoutChange, ...): that must still run.
    local after = false
    local function blizzardCaller()
        EditModeManagerFrame:UpdateLayoutInfo()
        after = true
    end
    local ok = pcall(blizzardCaller)
    eq(ok, true, "the caller was not unwound")
    eq(after, true, "Blizzard's later steps ran")
    eq(#__errors, 1, "forwarded once")
    eq(__errors[1]:find("boom hook", 1, true) ~= nil, true)
end

function T.the_event_with_the_hook_running_reseats_and_forwards_once()
    local f = setup()
    local bad = seatEditModeFrame("minimap")
    bad.SetSize = function() error("boom evt") end
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(#__errors, 1, "one report: the hook's, the watcher stood down")
end

function T.the_event_reseats_when_update_layout_info_threw_before_the_hook_ran()
    local f = setup()
    local c = seatEditModeFrame("minimap")
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    -- Blizzard throws before hooksecurefunc's post-hook gets to run.
    EditModeManagerFrame.apply = function() error("blizzard boom") end
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(atLayout(c, "minimap"), true, "the watcher re-seated: the hook never ran for this event")
    eq(runs, 1, "callbacks ran once")
    -- And the next, healthy event is covered by the hook alone.
    c:ClearAllPoints()
    c:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 0, 0)
    EditModeManagerFrame.apply = nil
    __fire("EDIT_MODE_LAYOUTS_UPDATED")
    eq(atLayout(c, "minimap"), true)
    eq(runs, 2, "one more run, not two")
end

function T.two_throwing_frames_in_one_pass_each_carry_one_stack()
    debugstack = function() return "FRAMES" end
    local _, e1 = FS.Layout.CallTraced(function() error("first", 0) end)
    local _, e2 = FS.Layout.CallTraced(function() error("second", 0) end)
    local _, e3 = FS.Layout.CallTraced(function() error(e1, 0) end)
    eq(e3, e1, "the first error, rethrown through an outer CallTraced, gains no second stack")
    local _, e4 = FS.Layout.CallTraced(function() error(e2, 0) end)
    eq(e4, e2, "nor the second")
end

function T.the_recent_set_is_bounded()
    debugstack = function() return "FRAMES" end
    local _, first = FS.Layout.CallTraced(function() error("e1", 0) end)
    for i = 2, 6 do FS.Layout.CallTraced(function() error("e" .. i, 0) end) end
    local _, again = FS.Layout.CallTraced(function() error(first, 0) end)
    eq(again, first .. "\nFRAMES", "an error older than the bound is no longer recognised")
end

function T.calltraced_asks_debugstack_for_level_3_under_pcall()
    local level
    debugstack = function(l) level = l; return "FRAMES" end
    FS.Layout.CallTraced(function() error("x", 0) end)
    eq(level, 3, "pcall is level 1, the handler 2, the throw site 3")
end

function T.calltraced_returns_a_secret_message_untouched_without_reading_a_stack()
    local SECRET = "SECRET-MESSAGE"
    local asked = false
    debugstack = function() asked = true; return "FRAMES" end
    issecretvalue = function(v) return v == SECRET end
    local ok, err = FS.Layout.CallTraced(function() error(SECRET, 0) end)
    eq(ok, false)
    eq(err, SECRET, "the message goes out as is, nothing concatenated")
    eq(asked, false, "no stack was read for it")
end

-- A frame whose SetPointBase lookup throws (outside Apply). It lives in _applied for good.
local function addOddFrame()
    local odd = setmetatable({}, { __index = function(_, k)
        if k == "SetPointBase" then error("boom lookup") end
    end })
    FS.Layout._applied[odd] = { id = "minimap" }
end

function T.a_frame_whose_lookup_throws_skips_neither_the_others_nor_the_callbacks()
    local f = setup()
    addOddFrame()
    local good = seatEditModeFrame("stance")
    local ran = false
    FS.Layout.OnRescale(function() ran = true end)
    local ok = pcall(EditModeManagerFrame.UpdateLayoutInfo, EditModeManagerFrame)
    eq(ok, true, "the hook did not throw")
    eq(atLayout(good, "stance"), true, "the other frame was re-seated whatever the order")
    eq(ran, true, "the callbacks ran")
    eq(#__errors, 1, "forwarded once")
    eq(__errors[1]:find("boom lookup", 1, true) ~= nil, true)
end

function T.a_throw_that_escapes_the_whole_reseat_still_does_not_unwind_blizzards_caller()
    -- A fresh Layout.lua hooked onto its own manager; iterating _applied itself throws,
    -- which no per-frame isolation can catch.
    local emm = {}
    function emm:UpdateLayoutInfo() end
    EditModeManagerFrame = emm
    local FS2 = { Chat = FS.Chat }
    __load("Layout.lua", __layoutSrc, FS2)
    FS2.Layout._applied = 42
    local after = false
    local ok = pcall(function()
        emm:UpdateLayoutInfo()
        after = true
    end)
    eq(ok, true, "the hook did not throw")
    eq(after, true, "Blizzard's later steps ran")
    eq(#__errors, 1, "forwarded once")
end

function T.the_hook_survives_an_error_handler_lookup_that_throws()
    local f = setup()
    local bad = seatEditModeFrame("minimap")
    bad.SetSize = function() error("boom hook") end
    geterrorhandler = function() error("no handler") end
    local ok = pcall(EditModeManagerFrame.UpdateLayoutInfo, EditModeManagerFrame)
    eq(ok, true, "the hook did not throw")
end

function T.forward_error_hands_the_error_to_the_handler_and_never_throws()
    FS.Layout.ForwardError("e1")
    eq(__errors[1], "e1")
    FS.Layout.ForwardError(nil)
    eq(#__errors, 1, "nil is not an error")
    geterrorhandler = function() return function() error("handler boom") end end
    eq(pcall(FS.Layout.ForwardError, "e2"), true)
    geterrorhandler = nil
    eq(pcall(FS.Layout.ForwardError, "e3"), true)
end

function T.a_throwing_chat_seat_in_the_hook_does_not_unwind_blizzards_caller()
    local f = setup()
    local realSetSize = f.SetSize
    f.SetSize = function(self, ...)
        if FS.Layout.applying then error("boom chat") end
        return realSetSize(self, ...)
    end
    local after = false
    local ok = pcall(function()
        EditModeManagerFrame:UpdateLayoutInfo()
        after = true
    end)
    eq(ok, true, "the chat's hook did not throw")
    eq(after, true, "Blizzard's later steps ran")
    eq(#__errors, 1, "forwarded exactly once")
    eq(__errors[1]:find("boom chat", 1, true) ~= nil, true)
    local _, n = __errors[1]:gsub("stack traceback:", "")
    eq(n, 1, "with one stack")
end

function T.the_layouts_updated_event_still_rethrows_a_chat_seat_error()
    local f = setup()
    local realSetSize = f.SetSize
    EditModeManagerFrame.apply = nil
    f.SetSize = function(self, ...)
        if FS.Layout.applying then error("boom chat") end
        return realSetSize(self, ...)
    end
    -- Blizzard's manager is pcall-isolated and its UpdateLayoutInfo hook now forwards;
    -- the chat's own watcher runs the event path, which may throw into the engine.
    local watcher
    for _, fr in ipairs(__frames) do
        if fr._events.UPDATE_FLOATING_CHAT_WINDOWS then watcher = fr end
    end
    local ok = pcall(watcher._scripts.OnEvent, watcher, "EDIT_MODE_LAYOUTS_UPDATED")
    eq(ok, false, "the event path keeps rethrowing")
end

__checks = T
"""


def repr_lua(text: str) -> str:
    return "[==[" + text + "]==]"


# Blizzard's manager exists before any addon loads; Layout.lua hooks it once, at load, so
# each check swaps the behaviour behind UpdateLayoutInfo instead of replacing the object.
BASE_EMM = r"""
EditModeManagerFrame = { dirtyWrites = 0 }
function EditModeManagerFrame:UpdateLayoutInfo()
    if self.apply then self.apply(self) end
end
"""


# A secret error value cannot be compared (== / ~= on a secret is illegal, and the mock cannot
# model that: __eq only fires table against table, never against nil), so the code tests a plain
# flag instead. This pin is what holds the line: no `<error-ish name> ==/~= nil`, either order.
# `msg` / `message` are deliberately broad: a false positive costs a rename, a false negative
# costs an illegal comparison on a secret.
ERRISH = r"(?:e|\w*(?:[Ee]rr|[Ee]rror|[Tt]hrown|[Mm]sg|[Mm]essage)\w*)"
NIL_COMPARE = re.compile(
    rf"\b{ERRISH}\s*[=~]=\s*nil\b|\bnil\s*[=~]=\s*{ERRISH}\b"
)
LONG_OPEN = re.compile(r"\[(=*)\[")
PINNED_FILES = ("Layout.lua", "ChatWindowState.lua")


def strip_lua(text: str) -> str:
    """Source with comments removed and string contents blanked, newlines kept.

    One pass over short strings ('..' and ".." with escapes), long brackets [[ ]] / [=[ ]=],
    line comments and block comments --[[ ]] / --[=[ ]=], so a `--` inside a string, a block
    comment spanning lines and a block comment ahead of code on the same line all come out right.
    """
    out: list[str] = []
    i, n = 0, len(text)

    def blank(chunk: str) -> str:
        return "".join(c if c == "\n" else " " for c in chunk)

    def skip_long(start: int, level: str) -> int:
        close = "]" + level + "]"
        end = text.find(close, start)
        return n if end < 0 else end + len(close)

    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            m = LONG_OPEN.match(text, i + 2)
            if m:
                end = skip_long(m.end(), m.group(1))
                out.append(blank(text[i:end]))
                i = end
            else:
                end = text.find("\n", i)
                end = n if end < 0 else end
                out.append(blank(text[i:end]))
                i = end
        elif ch == "[" and (m := LONG_OPEN.match(text, i)):
            end = skip_long(m.end(), m.group(1))
            out.append(blank(text[i:end]))
            i = end
        elif ch in "'\"":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            closed = j < n and text[j] == ch
            out.append(ch + blank(text[i + 1:j]) + (ch if closed else ""))
            i = j + 1 if closed else j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def find_error_nil_compares(text: str) -> list[str]:
    hits = []
    original = text.splitlines()
    for n, line in enumerate(strip_lua(text).splitlines(), 1):
        if NIL_COMPARE.search(line):
            hits.append(f"{n}: {original[n - 1].strip()}")
    return hits


STRIPPER_CASES = [
    ("a block comment spanning lines", "--[[ err == nil\n]] x = 1", 0),
    ("a leveled block comment", "--[==[ err == nil ]==]\nx = 1", 0),
    ("a -- inside a string does not hide code", 's = "a -- b"; if err == nil then end', 1),
    ("a block comment ahead of code on one line", "--[[ x ]] if err == nil then end", 1),
    ("a comparison inside a string is not code", 's = "err == nil"', 0),
]


def check_stripper() -> int:
    bad = 0
    for what, src, want in STRIPPER_CASES:
        got = len(find_error_nil_compares(src))
        if got != want or strip_lua(src).count("\n") != src.count("\n"):
            bad += 1
            print(f"FAIL  stripper: {what}: {got} hits, want {want}")
        else:
            print(f"ok    stripper: {what}")
    return bad


def check_no_error_nil_compares() -> int:
    bad = check_stripper()
    for name in PINNED_FILES:
        hits = find_error_nil_compares((ADDON / name).read_text(encoding="utf-8"))
        if hits:
            bad += 1
            print(f"FAIL  {name} compares an error value with nil: {hits}")
        else:
            print(f"ok    {name} never compares an error value with nil")
    return bad


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(BASE_EMM)
    lua.execute(
        "FS = { Chat = { PAD_TOP = 40, ApplyDockState = function() end, "
        "termPanel = { SetFrameStrata = function() end, SetFrameLevel = function() end } } }"
    )
    load = lua.eval(LOAD)
    for name in ("Layout.lua", "ChatWindowState.lua"):
        load(name, (ADDON / name).read_text(encoding="utf-8"), lua.eval("FS"))
    lua.execute("__load = " + LOAD)
    lua.execute("__layoutSrc = " + repr_lua((ADDON / "Layout.lua").read_text(encoding="utf-8")))
    lua.execute("__fire('PLAYER_LOGIN')")
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the combat flag, the hooks and the log must not leak.
        try:
            boot().eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    failed += check_no_error_nil_compares()
    # Lua checks, pinned files, stripper cases
    total = len(names) + len(PINNED_FILES) + len(STRIPPER_CASES)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
