#!/usr/bin/env python3
"""Runs the real Layout.lua headless against a small mock WoW API.

Layout.lua's watcher re-seats every frame that has been through FS.Layout.Apply
whenever the UI scale or resolution changes. A protected frame (a secure button, or
the container holding one, like the stance bar's) refuses ClearAllPoints, SetPoint
and SetSize in combat and raises ADDON_ACTION_BLOCKED, so these checks pin that the
watcher:

  * re-seats every applied frame at once out of combat;
  * leaves a protected frame alone in combat, seats an unprotected one at once, and
    seats the held one when combat ends (and does nothing on a combat end that held
    nothing back);
  * treats a frame whose IsProtected throws as protected;
  * still runs the rescale callbacks, once on the rescale and again after the held
    frames are seated.

Layout.lua is the real file; the frames are a recording mock, NOT the real client.

    python3 tools/layout-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"
LAYOUT_FILE = Path(os.environ.get("LAYOUT_LUA", ADDON / "Layout.lua"))   # a mutant copy for mutation checks

MOCK = r"""
__combat = false
__blocked = 0
__frames = {}

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
function Frame:SetSize(w, h) if guarded(self) then return end; self._w, self._h = w, h end
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:IsProtected()
    if self._isProtectedThrows then error("IsProtected failed") end
    return self._protected or false
end
function Frame:SetHeight(h) self._h = h end
function Frame:GetHeight() return self._h end

function CreateFrame()
    local f = setmetatable({ _points = {}, _events = {}, _scripts = {} }, Frame)
    __frames[#__frames + 1] = f
    return f
end
function InCombatLockdown() return __combat end
function __fire(event)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event) end
    end
end

UIParent = CreateFrame()
UIParent:SetHeight(1440)

-- Blizzard_EditMode's manager, loaded before Layout.lua so the post-hook installs at load.
EditModeManagerFrame = { UpdateLayoutInfo = function() end }
function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
function geterrorhandler() return function() end end
"""

LOAD = r"""
function(src, fs)
    local chunk = assert(load(src, "@Layout.lua"))
    chunk("ForeverSynthwave", fs)
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

-- A frame seated through Apply at scale 1, then the UI scale halves.
local function seated(protected)
    local f = CreateFrame()
    f._protected = protected
    FS.Layout.Apply(f, "stance")
    return f
end
local function rescale(to)
    UIParent:SetHeight(1440 * to)
    __fire("UI_SCALE_CHANGED")
end
local function width(f) return f._w end
local STANCE_W = 320

function T.rescale_out_of_combat_reseats_every_applied_frame()
    local a, b = seated(true), seated(false)
    eq(width(a), STANCE_W)
    rescale(0.5)
    eq(width(a), STANCE_W * 0.5, "protected frame follows the new scale")
    eq(width(b), STANCE_W * 0.5, "unprotected frame follows the new scale")
    eq(__blocked, 0)
end

function T.rescale_in_combat_leaves_a_protected_frame_alone_and_seats_the_rest()
    local held, free = seated(true), seated(false)
    __combat = true
    rescale(0.5)
    eq(__blocked, 0, "no protected operation was attempted")
    eq(width(held), STANCE_W, "protected frame untouched in combat")
    eq(#held._points, 1, "and its anchor intact")
    eq(width(free), STANCE_W * 0.5, "unprotected frame seated at once")
end

function T.the_held_frame_is_seated_when_combat_ends()
    local held = seated(true)
    __combat = true
    rescale(0.5)
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(width(held), STANCE_W * 0.5, "seated after combat")
    eq(#held._points, 1, "one anchor, re-seated not stacked")
    eq(__blocked, 0)
end

function T.the_latest_scale_wins_when_it_changes_twice_in_combat()
    local held = seated(true)
    __combat = true
    rescale(0.5)
    rescale(0.25)
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(width(held), STANCE_W * 0.25)
end

function T.combat_ending_with_nothing_held_back_does_no_work()
    local f = seated(true)
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    UIParent:SetHeight(720)   -- changed, but no rescale event reached the watcher
    __fire("PLAYER_REGEN_ENABLED")
    eq(width(f), STANCE_W, "not re-seated by a plain combat end")
    eq(runs, 0, "no callback ran")
end

function T.a_second_combat_end_does_not_repeat_the_deferred_pass()
    seated(true)
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    __combat = true
    rescale(0.5)
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    local after = runs
    __fire("PLAYER_REGEN_ENABLED")
    eq(runs, after, "the pass ran once")
end

function T.an_is_protected_that_throws_counts_as_protected()
    local f = seated(false)
    f._isProtectedThrows = true
    __combat = true
    rescale(0.5)
    eq(__blocked, 0)
    eq(width(f), STANCE_W, "held back")
    f._isProtectedThrows = false
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(width(f), STANCE_W * 0.5, "seated afterwards")
end

function T.rescale_callbacks_run_on_the_rescale_and_again_after_the_held_frames_seat()
    local held = seated(true)
    local seen = {}
    FS.Layout.OnRescale(function() seen[#seen + 1] = width(held) end)
    __combat = true
    rescale(0.5)
    eq(#seen, 1, "once on the rescale itself")
    eq(seen[1], STANCE_W, "the held frame is still at the old size then")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(#seen, 2, "and once more after combat")
    eq(seen[2], STANCE_W * 0.5, "with the held frame seated by then")
end

function T.a_throwing_callback_does_not_stop_the_others_or_the_deferral()
    local held = seated(true)
    local ran = false
    FS.Layout.OnRescale(function() error("boom") end)
    FS.Layout.OnRescale(function() ran = true end)
    __combat = true
    rescale(0.5)
    eq(ran, true, "the next callback still ran")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(width(held), STANCE_W * 0.5)
end

-- The label a rescale callback can read (the minimap seat log records it): the event that
-- ran the pass, or UpdateLayoutInfo / EDIT_MODE_LAYOUTS_UPDATED for the Edit Mode re-seat.
local function editModeFrame()
    local f = CreateFrame()
    f.SetPointBase, f.ClearAllPointsBase = f.SetPoint, f.ClearAllPoints
    FS.Layout.Apply(f, "stance")
    return f
end

function T.rescale_callbacks_can_read_why_the_pass_ran()
    local seen = {}
    FS.Layout.OnRescale(function() seen[#seen + 1] = tostring(FS.Layout.rescaleWhy) end)
    rescale(0.5)
    eq(seen[1], "UI_SCALE_CHANGED", "the event that ran the pass")
    eq(FS.Layout.rescaleWhy, nil, "cleared once the callbacks are done")
end

function T.the_edit_mode_post_hook_labels_its_pass_update_layout_info()
    editModeFrame()
    local seen = {}
    FS.Layout.OnRescale(function() seen[#seen + 1] = tostring(FS.Layout.rescaleWhy) end)
    EditModeManagerFrame:UpdateLayoutInfo()
    eq(#seen, 1, "one pass for the hook")
    eq(seen[1], "UpdateLayoutInfo")
    eq(FS.Layout.rescaleWhy, nil, "cleared afterwards")
end

function T.the_edit_mode_event_fallback_labels_its_pass_with_the_event()
    editModeFrame()
    local seen = {}
    FS.Layout.OnRescale(function() seen[#seen + 1] = tostring(FS.Layout.rescaleWhy) end)
    __fire("EDIT_MODE_LAYOUTS_UPDATED")   -- UpdateLayoutInfo (and so the hook) did not run
    eq(#seen, 1)
    eq(seen[1], "EDIT_MODE_LAYOUTS_UPDATED")
end

-- A component whose frame is measured to sit off its asked seat (the minimap cluster, whose
-- header strip hangs the map below the frame) offers FS.Layout.SeatAdjust[id]: Apply then
-- writes THAT anchor, so the frame is never shown at the raw seat for a frame in between.
function T.a_seat_adjust_replaces_the_anchor_apply_writes()
    FS.Layout.SeatAdjust = { stance = function() return "TOP", "BOTTOM", 5, 6 end }
    local f = CreateFrame()
    FS.Layout.Apply(f, "stance")
    local p = f._points[1]
    eq(#f._points, 1, "one anchor")
    eq(p.point, "TOP"); eq(p.relPoint, "BOTTOM"); eq(p.x, 5); eq(p.y, 6)
    eq(f._w, STANCE_W, "the size is still the layout's")
end

function T.no_seat_adjust_or_an_empty_answer_writes_the_raw_seat()
    local L = FS.Layout.stance
    local f = CreateFrame()
    FS.Layout.SeatAdjust = {}
    FS.Layout.Apply(f, "stance")
    eq(f._points[1].point, L.point); eq(f._points[1].x, L.x)
    FS.Layout.SeatAdjust = { stance = function() return nil end }
    local g = CreateFrame()
    FS.Layout.Apply(g, "stance")
    eq(g._points[1].point, L.point, "nil answer: raw seat")
end

function T.a_throwing_or_malformed_seat_adjust_falls_back_to_the_raw_seat()
    local L = FS.Layout.stance
    for _, fn in ipairs({
        function() error("boom") end,
        function() return "TOP", "BOTTOM", "x", 6 end,
        function() return "TOP", "BOTTOM", 5, 0 / 0 end,
        function() return 3, "BOTTOM", 5, 6 end,
        function() return "TOP", "BOTTOM", math.huge, 6 end,
        function() return "TOP", "BOTTOM", 5, -math.huge end,
    }) do
        FS.Layout.SeatAdjust = { stance = fn }
        local f = CreateFrame()
        FS.Layout.Apply(f, "stance")
        eq(f._points[1].point, L.point, "raw seat")
        eq(f._points[1].x, L.x)
        eq(f._w, STANCE_W)
    end
end

function T.a_registrant_whose_numbers_throw_on_use_falls_back_to_the_raw_seat()
    -- Stands in for a secret number: type() says "number", any arithmetic or ordered
    -- compare on it throws. Apply must contain that, not raise it.
    local secret = setmetatable({}, {})
    local realType = type
    type = function(v) if rawequal(v, secret) then return "number" end return realType(v) end
    FS.Layout.SeatAdjust = { stance = function() return "TOP", "BOTTOM", secret, 6 end }
    local f = CreateFrame()
    local ok, err = pcall(FS.Layout.Apply, f, "stance")
    type = realType
    eq(ok, true, "Apply did not throw: " .. tostring(err))
    eq(f._points[1].point, FS.Layout.stance.point, "raw seat")
    eq(f._points[1].x, FS.Layout.stance.x)
end

function T.a_seat_adjust_registered_for_another_id_changes_only_that_id()
    FS.Layout.other = { point = "CENTER", relPoint = "CENTER", x = 1, y = 2, w = 3, h = 4 }
    FS.Layout.SeatAdjust = { other = function() return "TOP", "BOTTOM", 5, 6 end }
    local a, b = CreateFrame(), CreateFrame()
    FS.Layout.Apply(a, "other")
    FS.Layout.Apply(b, "stance")
    eq(a._points[1].point, "TOP", "the registered id is adjusted")
    eq(a._points[1].x, 5)
    eq(b._points[1].point, FS.Layout.stance.point, "another id is not")
    eq(b._points[1].x, FS.Layout.stance.x)
end

function T.a_seat_adjust_is_not_used_for_a_frame_seated_on_another_parent()
    FS.Layout.SeatAdjust = { stance = function() return "TOP", "BOTTOM", 5, 6 end }
    local other = CreateFrame()
    local f = CreateFrame()
    FS.Layout.Apply(f, "stance", other)
    eq(f._points[1].point, FS.Layout.stance.point)
    eq(f._points[1].rel, other)
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute("FS = {}")
    lua.eval(LOAD)(LAYOUT_FILE.read_text(encoding="utf-8"), lua.eval("FS"))
    lua.execute("__fire('PLAYER_LOGIN')")
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the combat flag, the applied frames and the
        # registered callbacks must not leak between them.
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
