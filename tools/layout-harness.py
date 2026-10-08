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
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
LAYOUT_FILE = Path(os.environ.get("LAYOUT_LUA", ADDON / "Core/Layout.lua"))   # a mutant copy for mutation checks

UNITFRAMES_FILE = ADDON / "Modules/UnitFrames/UnitFrames.lua"

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
function Frame:UnregisterEvent(e) self._events[e] = nil end
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
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
__printed = {}
function print(...) __printed[#__printed + 1] = table.concat({ ... }, " ") end

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
    chunk("forever-stuwave", fs)
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

-------------------------------------------------------------------------------
-- Saved overrides
-------------------------------------------------------------------------------

local function stanceX() return FS.Layout.stance.x end

-- The override store is the active profile's layout table, handed over with UseStore.
local function useStore(layout)
    layout = layout or {}
    FS.Layout.UseStore(layout)
    return layout
end

function T.overrides_load_and_mutate_the_layout_entry_in_place()
    local entry = FS.Layout.stance
    useStore({ v = 1, frames = { stance = { x = 10.5, y = -400 } } })
    eq(FS.Layout.stance, entry, "the same table, mutated in place")
    eq(entry.x, 10.5); eq(entry.y, -400)
    eq(FS.Layout.action.x, -7, "an id with no override keeps its default")
end

function T.the_login_reseat_seats_frames_at_the_bound_store_overrides()
    local f = seated(false)
    useStore({ v = 1, frames = { stance = { x = 30, y = -300 } } })
    eq(stanceX(), 30, "bound store applied")
    __fire("PLAYER_LOGIN")
    eq(f._points[1].x, 30, "the login pass seats the frame at the override")
    eq(f._points[1].y, -300)
end

function T.defaults_are_snapshotted_before_the_first_mutation()
    local layout = useStore({ v = 1, frames = { stance = { x = 10, y = 20 } } })
    eq(FS.Layout._defaults.stance.x, 0); eq(FS.Layout._defaults.stance.y, -427)
    eq(FS.Layout._defaults.action.x, -7)
    layout.frames.stance = { x = 50, y = 60 }
    FS.Layout.LoadOverrides()
    eq(FS.Layout._defaults.stance.x, 0, "a second load does not snapshot an override")
    eq(stanceX(), 50)
    layout.frames.stance = nil
    FS.Layout.LoadOverrides()
    eq(stanceX(), 0, "a reload without the entry is back on the default")
end

function T.binding_another_store_restores_defaults_then_applies_its_overrides()
    useStore({ v = 1, frames = { stance = { x = 10, y = 20 }, action = { x = 1, y = 2 } } })
    eq(stanceX(), 10); eq(FS.Layout.action.x, 1)
    useStore({ v = 1, frames = { stance = { x = 70, y = 80 } } })
    eq(stanceX(), 70, "the new store's override")
    eq(FS.Layout.action.x, -7, "the old store's override is gone")
    useStore({})
    eq(stanceX(), 0, "an empty store is all defaults")
end

function T.an_unbound_or_non_table_store_applies_nothing_and_refuses_writes()
    useStore({ v = 1, frames = { stance = { x = 10, y = 20 } } })
    FS.Layout.UseStore(nil)
    eq(stanceX(), 0, "unbinding restores the defaults")
    eq(FS.Layout.SetOverride("stance", 1, 2), false)
    eq(FS.Layout.ClearOverride("stance"), false)
    eq(FS.Layout.ClearAllOverrides(), false)
    FS.Layout.UseStore("junk")
    eq(FS.Layout.SetOverride("stance", 1, 2), false, "a non-table store is refused too")
    eq(stanceX(), 0)
    eq(#__printed, 0, "no version warning for a missing store")
end

function T.a_higher_version_is_ignored_with_one_warning_and_never_written()
    local layout = { v = 2, frames = { stance = { x = 5, y = 5 } }, future = "keep" }
    FS.Layout.UseStore(layout)
    FS.Layout.LoadOverrides()
    eq(stanceX(), 0, "overrides not applied")
    eq(#__printed, 1, "one warning")
    eq(layout.v, 2); eq(layout.future, "keep")
    eq(layout.frames.stance.x, 5, "entry untouched")
    eq(FS.Layout.SetOverride("stance", 9, 9), false)
    eq(FS.Layout.ClearOverride("stance"), false)
    eq(FS.Layout.ClearAllOverrides(), false)
    eq(layout.frames.stance.x, 5, "still untouched after every write attempt")
    eq(layout.frames.stance.y, 5)
    eq(stanceX(), 0, "and the layout stayed on the default")
end

function T.a_store_missing_its_version_or_frames_is_repaired_to_the_current_version()
    local layout = useStore({})
    eq(layout.v, 1)
    eq(type(layout.frames), "table")
    layout = useStore({ v = 1, frames = 7 })
    eq(type(layout.frames), "table", "a non-table frames is replaced")
    layout = useStore({ v = "x" })
    eq(layout.v, 1, "a non-numeric version is replaced")
end

function T.garbage_entries_are_ignored()
    useStore({ v = 1, frames = {
        stance = { x = "10", y = 1 },
        action = { x = 3 },
        petbar = { x = 0 / 0, y = 1 },
        nope = { x = 1, y = 1 },
        deck = { x = 1, y = 1 },
        _applied = { x = 1, y = 1 },
        grid = 7,
        [5] = { x = 1, y = 1 },
        pcast = { x = 11, y = -22 },
    } })
    eq(stanceX(), 0, "string x ignored")
    eq(FS.Layout.action.x, -7, "missing y ignored")
    eq(FS.Layout.petbar.x, -380, "NaN ignored")
    eq(FS.Layout.nope, nil, "unknown id not created")
    eq(FS.Layout.deck.x, nil, "an entry with no x/y is not overridable")
    eq(FS.Layout.grid.x, 2, "non-table entry ignored")
    eq(FS.Layout.pcast.x, 11, "a good entry beside the garbage still applies")
    eq(FS.Layout.pcast.y, -22)
end

function T.set_and_clear_override_round_trip_the_store()
    local layout = useStore()
    eq(FS.Layout.SetOverride("stance", 12.3, -400.74), true)
    local saved = layout.frames.stance
    eq(saved.x, 12.5, "rounded to half a design px"); eq(saved.y, -400.5)
    eq(FS.Layout.stance.x, 12.5); eq(FS.Layout.stance.y, -400.5)
    eq(FS.Layout.ClearOverride("stance"), true)
    eq(layout.frames.stance, nil, "store entry removed")
    eq(stanceX(), 0); eq(FS.Layout.stance.y, -427, "default restored")
    FS.Layout.SetOverride("stance", 1, 2)
    FS.Layout.SetOverride("action", 3, 4)
    FS.Layout.ClearAllOverrides()
    eq(next(layout.frames), nil, "every store entry removed")
    eq(stanceX(), 0); eq(FS.Layout.action.x, -7); eq(FS.Layout.action.y, -540)
    eq(layout.v, 1)
end

function T.huge_override_values_are_refused_on_write_and_ignored_on_load()
    local layout = useStore()
    for _, v in ipairs({ 9e307, -9e307, 1e300, 5121, -5121 }) do
        eq(FS.Layout.SetOverride("stance", v, 0), false, "x " .. v)
        eq(FS.Layout.SetOverride("player", 0, v), false, "y " .. v)
    end
    eq(next(layout.frames), nil, "nothing written")
    eq(FS.Layout.SetOverride("stance", 5120, -5120), true, "the bound itself is allowed")
    useStore({ v = 1, frames = {
        stance = { x = 9e307, y = 0 }, action = { x = 0, y = -1e300 }, player = { x = 6000, y = 0 },
        pcast = { x = 100, y = 200 },
    } })
    eq(stanceX(), 0); eq(FS.Layout.action.y, -540); eq(FS.Layout.player.x, 20)
    eq(FS.Layout.pcast.x, 100, "a sane entry beside them still applies")
end

function T.set_override_rejects_unknown_ids_and_non_numbers()
    local layout = useStore()
    eq(FS.Layout.SetOverride("nope", 1, 1), false)
    eq(FS.Layout.SetOverride("deck", 1, 1), false)
    eq(FS.Layout.SetOverride("stance", "1", 1), false)
    eq(FS.Layout.SetOverride("stance", 1, nil), false)
    eq(FS.Layout.SetOverride("stance", 0 / 0, 1), false)
    eq(FS.Layout.SetOverride("stance", math.huge, 1), false)
    eq(next(layout.frames), nil, "nothing written")
    eq(stanceX(), 0)
end

function T.reseat_moves_every_frame_seated_with_that_id_and_runs_the_callbacks()
    useStore()
    local a, b, other = seated(false), seated(true), CreateFrame()
    FS.Layout.Apply(other, "action")
    local why = {}
    FS.Layout.OnRescale(function() why[#why + 1] = tostring(FS.Layout.rescaleWhy) end)
    FS.Layout.SetOverride("stance", 40, -100)
    FS.Layout.Reseat("stance")
    eq(a._points[1].x, 40); eq(a._points[1].y, -100)
    eq(b._points[1].x, 40, "a protected frame is seated out of combat")
    eq(other._points[1].x, -7, "a frame with another id is left alone")
    eq(#a._points, 1, "re-seated, not stacked")
    eq(#why, 1, "the rescale callbacks ran once")
    eq(type(FS.Layout.RunRescaleCallbacks), "function")
end

function T.reseat_all_moves_every_applied_frame_and_runs_the_callbacks_once()
    useStore({ v = 1, frames = { stance = { x = 40, y = -100 }, action = { x = 5, y = 6 } } })
    local a, other = seated(false), CreateFrame()
    FS.Layout.Apply(other, "action")
    local why = {}
    FS.Layout.OnRescale(function() why[#why + 1] = tostring(FS.Layout.rescaleWhy) end)
    FS.Layout.ReseatAll()
    eq(a._points[1].x, 40); eq(other._points[1].x, 5)
    eq(#a._points, 1, "re-seated, not stacked")
    eq(#why, 1, "the rescale callbacks ran once for the whole pass")
end

function T.reseat_defers_a_held_frame_in_combat_and_seats_it_after_regen()
    useStore()
    local held, free = seated(true), seated(false)
    local runs = 0
    FS.Layout.OnRescale(function() runs = runs + 1 end)
    __combat = true
    FS.Layout.SetOverride("stance", 40, -100)
    FS.Layout.Reseat("stance")
    eq(__blocked, 0, "no protected operation was attempted")
    eq(held._points[1].x, 0, "held frame untouched in combat")
    eq(free._points[1].x, 40, "unprotected frame seated at once")
    eq(runs, 1, "callbacks still ran")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(held._points[1].x, 40, "held frame seated after combat")
    eq(#held._points, 1)
    eq(__blocked, 0)
    eq(runs, 2, "and the callbacks ran again once it was seated")
end

function T.reseat_all_defers_a_held_frame_in_combat_and_seats_it_after_regen()
    local held, free = seated(true), seated(false)
    __combat = true
    useStore({ v = 1, frames = { stance = { x = 40, y = -100 } } })
    FS.Layout.ReseatAll()
    eq(__blocked, 0, "no protected operation was attempted")
    eq(held._points[1].x, 0, "held frame untouched in combat")
    eq(free._points[1].x, 40, "unprotected frame seated at once")
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(held._points[1].x, 40, "held frame seated after combat")
    eq(__blocked, 0)
end

-------------------------------------------------------------------------------
-- Player and target seats
-------------------------------------------------------------------------------

function T.player_and_target_land_on_the_old_corner_seat_at_any_ui_scale()
    for _, height in ipairs({ 1440, 1200, 768 }) do
        UIParent:SetHeight(height)
        local p, t = CreateFrame(), CreateFrame()
        p:SetSize(260, 73); t:SetSize(260, 73)   -- the size UnitFrames.lua builds them at
        FS.Layout.Apply(p, "player")
        FS.Layout.Apply(t, "target")
        local a, b = p._points[1], t._points[1]
        eq(a.point, "TOPLEFT", "player point at " .. height); eq(a.rel, UIParent); eq(a.relPoint, "TOPLEFT")
        eq(a.x, 20, "player x is raw UI units at " .. height); eq(a.y, -20)
        eq(b.point, "TOPLEFT"); eq(b.rel, UIParent, "target is not chained to player"); eq(b.relPoint, "TOPLEFT")
        eq(b.x, 300, "target x is raw UI units at " .. height); eq(b.y, -20)
        eq(p._w, 260, "player size untouched at " .. height); eq(p._h, 73)
        eq(t._w, 260); eq(t._h, 73)
    end
end

function T.an_unsized_entry_is_never_resized_by_apply_or_a_rescale()
    local p = CreateFrame()
    p:SetSize(260, 61)   -- SetPanelHeight shrank it for a unit without a power bar
    FS.Layout.Apply(p, "player")
    rescale(0.5)
    eq(p._w, 260); eq(p._h, 61, "the module's own height survives Apply and a rescale")
    eq(p._points[1].x, 20, "and the position stays in raw UI units")
end

function T.scaled_entries_are_unchanged_by_the_unscaled_flag()
    eq(FS.Layout.IsUnscaled("player"), true); eq(FS.Layout.IsUnscaled("target"), true)
    eq(FS.Layout.IsUnscaled("stance"), false); eq(FS.Layout.IsUnscaled("nope"), false)
    UIParent:SetHeight(720)
    local f = CreateFrame()
    FS.Layout.Apply(f, "stance")
    eq(f._points[1].y, -427 * 0.5); eq(f._w, STANCE_W * 0.5); eq(f._h, 38 * 0.5)
end

function T.an_unscaled_override_is_stored_and_applied_in_the_entrys_own_units()
    local layout = useStore()
    UIParent:SetHeight(1200)
    local t = CreateFrame()
    FS.Layout.Apply(t, "target")
    eq(FS.Layout.SetOverride("target", 41.26, -9.8), true)
    eq(layout.frames.target.x, 41.5, "rounded to 0.5 like a scaled entry")
    eq(layout.frames.target.y, -10)
    FS.Layout.Reseat("target")
    eq(t._points[1].x, 41.5, "applied unscaled"); eq(t._points[1].y, -10)
    FS.Layout.ClearOverride("target")
    eq(FS.Layout.target.x, 300)
end

function T.player_and_target_move_independently()
    useStore()
    local p, t = CreateFrame(), CreateFrame()
    FS.Layout.Apply(p, "player")
    FS.Layout.Apply(t, "target")
    FS.Layout.SetOverride("target", 500, -60)
    FS.Layout.Reseat("target")
    eq(t._points[1].x, 500); eq(t._points[1].y, -60)
    eq(p._points[1].x, 20, "player stayed put"); eq(p._points[1].y, -20)
    FS.Layout.SetOverride("player", 80, -90)
    FS.Layout.Reseat("player")
    eq(p._points[1].x, 80)
    eq(t._points[1].x, 500, "target stayed put")
end

__checks = T
"""


def check_unitframes_parity() -> int:
    """The player/target defaults must equal the old chained corner seat in UnitFrames.lua."""
    src = UNITFRAMES_FILE.read_text(encoding="utf-8")

    def const(name: str) -> int:
        match = re.search(rf"^local {name}\s*=\s*(\d+)\b", src, re.M)
        if not match:
            raise SystemExit(f"UnitFrames.lua: constant {name} not found")
        return int(match.group(1))

    width = const("PANEL_WIDTH")
    height = 2 * const("PAD_Y") + const("NAME_ROW_HEIGHT") + const("NAME_GAP") + const("HEALTH_HEIGHT") + const("BAR_GAP") + const("POWER_HEIGHT")
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute("FS = {}")
    lua.eval(LOAD)(LAYOUT_FILE.read_text(encoding="utf-8"), lua.eval("FS"))
    player, target = lua.eval("FS.Layout.player"), lua.eval("FS.Layout.target")
    want_player = (20, -20, width, height)
    want_target = (20 + width + 20, -20, width, height)
    problems = []
    if (player.x, player.y, player.w, player.h) != want_player or player.point != "TOPLEFT" or player.relPoint != "TOPLEFT":
        problems.append(f"FS.Layout.player is not the old corner seat {want_player}")
    if (target.x, target.y, target.w, target.h) != want_target or target.point != "TOPLEFT" or target.relPoint != "TOPLEFT":
        problems.append(f"FS.Layout.target is not where the old chain put it {want_target}")
    if not re.search(r'FS\.Layout\.Apply\(\s*player\s*,\s*"player"\s*\)', src):
        problems.append('UnitFrames.lua does not seat the player with FS.Layout.Apply(player, "player")')
    if not re.search(r'FS\.Layout\.Apply\(\s*target\s*,\s*"target"\s*\)', src):
        problems.append('UnitFrames.lua does not seat the target with FS.Layout.Apply(target, "target")')
    if re.search(r'"TOPRIGHT"\s*,\s*20\s*,\s*0', src) or re.search(r'player:SetPoint|target:SetPoint', src):
        problems.append("UnitFrames.lua still hardcodes the player/target anchors")
    for entry, name in ((player, "player"), (target, "target")):
        if not (entry.unscaled and entry.noSize):
            problems.append(f"FS.Layout.{name} must be unscaled and noSize (approved look at any UI scale)")
    for problem in problems:
        print(f"FAIL  unitframes_parity: {problem}")
    if not problems:
        print("ok    unitframes_parity")
    return len(problems)


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
    failed = 1 if check_unitframes_parity() else 0
    names_total = len(names) + 1
    for name in names:
        # A fresh client per check: the combat flag, the applied frames and the
        # registered callbacks must not leak between them.
        try:
            boot().eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{names_total - failed}/{names_total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
