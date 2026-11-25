#!/usr/bin/env python3
"""Runs the real TrackerSeat.lua headless against a mock Edit Mode API.

TrackerSeat moves the objectives tracker by writing its seat into the active Edit Mode layout,
never by anchoring the tracker. These checks pin that:

  * a move on a preset layout copies the preset to a new account layout named STUwave
    (STUwave 2 when the name is taken), saves presets + saved + new, and activates it;
  * a move on an account layout edits that layout in place, and other systems are untouched;
  * the anchor written is TOPRIGHT of UIParent with the given offsets, out of the default seat;
  * a full set of account layouts and combat both refuse with a reason and save nothing;
  * reset restores the preset's anchor and default seat, and a preset has nothing to reset;
  * the tracker frame itself is never anchored;
  * while Questie's tracker is on, Blizzard's is hidden, so there is no seat to show or move;
  * the tracker's Height (Edit Mode's own setting, 400 to 1000 in steps of 10, stored as (height - 400) / 10) is written
    into the active layout in place, never copying a preset and never anchoring the frame; it snaps to the step and clamps
    to the range; it is refused while the tracker sits in its default seat (the game ignores it there) and held, with a
    "wait" answer, in combat, before the layouts are loaded or without Edit Mode; a Move writes the height the player's
    setting asks for in the same save.

    python3 tools/trackerseat-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

SEAT_FILE = Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Tracker/TrackerSeat.lua"

MOCK = r"""
__combat = false
__saved = {}
__activated = {}
__touched = 0

Enum = {
    EditModeSystem = { ActionBar = 0, ObjectiveTracker = 12 },
    EditModeLayoutType = { Preset = 0, Account = 1, Character = 2 },
    EditModeObjectiveTrackerSetting = { Height = 0, Opacity = 1, TextSize = 2 },
}
Constants = { EditModeConsts = { EditModeMaxLayoutsPerType = 5 } }

function CopyTable(t)
    local c = {}
    for k, v in pairs(t) do c[k] = type(v) == "table" and CopyTable(v) or v end
    return c
end

-- The tracker carries the three settings the game's own layouts do (Height 40 is 800 on screen, Opacity and Text size raw 0).
local function system(id, x, y, default)
    local s = { system = id, isInDefaultPosition = default,
        anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = x, offsetY = y } }
    if id == 12 then s.settings = { { setting = 0, value = 40 }, { setting = 1, value = 0 }, { setting = 2, value = 0 } } end
    return s
end
local function preset(name)
    return { layoutName = name, layoutType = 0,
        systems = { system(0, 0, 0, true), system(12, -110, -260, true) } }
end
EditModePresetLayoutManager = {
    GetCopyOfPresetLayouts = function() return { preset("Modern"), preset("Classic") } end,
}

__saved_layouts = {}     -- what C_EditMode.GetLayouts returns: saved layouts only
__active = 1
C_EditMode = {
    GetLayouts = function() return { activeLayout = __active, layouts = CopyTable(__saved_layouts) } end,
    SaveLayouts = function(info)
        __saved[#__saved + 1] = CopyTable(info)
        local own = {}
        for _, l in ipairs(info.layouts) do if l.layoutType ~= 0 then own[#own + 1] = CopyTable(l) end end
        __saved_layouts = own
    end,
    SetActiveLayout = function(i) __activated[#__activated + 1] = i; __active = i end,
}
function InCombatLockdown() return __combat end

local Frame = {}
Frame.__index = Frame
function Frame:SetPoint() __touched = __touched + 1 end
function Frame:ClearAllPoints() __touched = __touched + 1 end
function Frame:GetEffectiveScale() return self._scale end
function Frame:GetLeft() return self._l end
function Frame:GetTop() return self._t end
function Frame:GetWidth() return self._w end
function Frame:GetHeight() return self._h end
function Frame:GetRight() return self._l + self._w end
UIParent = setmetatable({ _scale = 1, _l = 0, _t = 1440, _w = 2560, _h = 1440 }, Frame)
-- The tracker at scale 0.8 of UIParent: its own units are 1.25x larger in number.
ObjectiveTrackerFrame = setmetatable({ _scale = 0.8, _l = 2800, _t = 1425, _w = 300, _h = 250 }, Frame)

function __load(src, pre)
    FS = pre or {}
    assert(load(src, "@TrackerSeat.lua"))("forever-stuwave", FS)
    return FS.TrackerSeat
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function near(a, b, msg)
    if a == nil or math.abs(a - b) > 1e-6 then error((msg or "not near") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function tracker(layout)
    for _, s in ipairs(layout.systems) do if s.system == 12 then return s end end
end
local function account(name, moved)
    return { layoutName = name, layoutType = 1, systems = { { system = 0, isInDefaultPosition = false, anchorInfo = { offsetX = 5 } },
        { system = 12, isInDefaultPosition = not moved, anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = -110, offsetY = -260 },
          settings = { { setting = 0, value = 40 }, { setting = 1, value = 0 }, { setting = 2, value = 0 } } } } }
end
local function heightOf(layout)
    for _, s in ipairs(tracker(layout).settings) do if s.setting == 0 then return s.value end end
end
-- An account layout with the tracker moved off its default seat, active.
local function movedLayout(name)
    __saved_layouts = { account(name or "Mine", true) }
    __active = 3
end

function T.ready_with_the_edit_mode_api()
    eq(__load(__src).Ready(), true)
end

function T.not_ready_without_the_edit_mode_api()
    C_EditMode = nil
    eq(__load(__src).Ready(), false)
end

function T.rect_and_offsets_are_in_uiparent_units()
    local seat = __load(__src)
    local l, t, w, h = seat.Rect()
    near(l, 2240); near(t, 1140); near(w, 240); near(h, 200)
    local x, y = seat.Offsets()
    near(x, -80, "right edge 2480 vs 2560"); near(y, -300, "top 1140 vs 1440")
end

function T.a_move_on_a_preset_copies_it_to_a_stuwave_account_layout_and_activates_it()
    local seat = __load(__src)
    eq(seat.Move(-29, -286), true)
    eq(#__saved, 1)
    local info = __saved[1]
    eq(#info.layouts, 3, "two presets plus the new layout")
    eq(info.layouts[1].layoutName, "Modern"); eq(info.layouts[2].layoutName, "Classic")
    local new = info.layouts[3]
    eq(new.layoutName, "STUwave"); eq(new.layoutType, 1)
    eq(info.activeLayout, 3); eq(__activated[1], 3)
    local t = tracker(new)
    eq(t.isInDefaultPosition, false)
    eq(t.anchorInfo.point, "TOPRIGHT"); eq(t.anchorInfo.relativeTo, "UIParent"); eq(t.anchorInfo.relativePoint, "TOPRIGHT")
    eq(t.anchorInfo.offsetX, -29); eq(t.anchorInfo.offsetY, -286)
    eq(new.systems[1].isInDefaultPosition, true, "other systems keep the preset's seat")
    eq(__touched, 0, "the tracker frame is never anchored")
end

function T.a_taken_name_gets_a_number()
    __saved_layouts = { account("STUwave") }
    __active = 1   -- Modern is active
    local seat = __load(__src)
    eq(seat.Move(-29, -286), true)
    eq(__saved[1].layouts[4].layoutName, "STUwave 2")
    eq(__activated[1], 4)
end

function T.a_move_on_an_account_layout_edits_it_in_place()
    __saved_layouts = { account("Mine") }
    __active = 3
    local seat = __load(__src)
    eq(seat.Move(-40, -300), true)
    local info = __saved[1]
    eq(#info.layouts, 3, "no copy made")
    eq(info.activeLayout, 3)
    local t = tracker(info.layouts[3])
    eq(t.isInDefaultPosition, false); eq(t.anchorInfo.offsetX, -40); eq(t.anchorInfo.offsetY, -300)
    eq(info.layouts[3].systems[1].anchorInfo.offsetX, 5, "the other system is untouched")
end

function T.a_full_set_of_account_layouts_refuses_and_saves_nothing()
    __saved_layouts = { account("a"), account("b"), account("c"), account("d"), account("e") }
    __active = 1
    local ok, why = __load(__src).Move(-29, -286)
    eq(ok, false); eq(why:find("slot") ~= nil, true, why)
    eq(#__saved, 0)
end

function T.combat_refuses_and_saves_nothing()
    __combat = true
    local ok, why = __load(__src).Move(-29, -286)
    eq(ok, false); eq(why:find("combat") ~= nil, true, why)
    ok = __load(__src).Reset()
    eq(ok, false)
    eq(#__saved, 0)
end

function T.reset_restores_the_preset_seat()
    local seat = __load(__src)
    seat.Move(-29, -286)
    eq(seat.Reset(), true)
    local t = tracker(__saved[2].layouts[3])
    eq(t.isInDefaultPosition, true); eq(t.anchorInfo.offsetX, -110); eq(t.anchorInfo.offsetY, -260)
    eq(__activated[2], 3)
end

function T.reset_on_a_preset_or_a_default_seat_saves_nothing()
    local seat = __load(__src)
    eq(seat.Reset(), true)
    __saved_layouts = { account("Mine") }
    __active = 3
    eq(seat.Reset(), true)
    eq(#__saved, 0)
end

function T.the_visible_panel_is_the_handle_and_the_move_anchors_blizzards_frame()
    local seat = __load(__src)
    -- The panel sits 10 left and 40 below the frame's TOPRIGHT, in UIParent units.
    local panel = setmetatable({ _scale = 1, _l = 2230, _t = 1100, _w = 240, _h = 120 }, getmetatable(UIParent))
    panel.IsShown = function() return true end
    FS.Tracker = { Panel = function() return panel end }
    local l, t, w, h = seat.Rect()
    eq(l, 2230); eq(t, 1100); eq(w, 240); eq(h, 120)
    local x, y = seat.Offsets()
    near(x, -90); near(y, -340)
    seat.Move(-29, -286)
    local a = tracker(__saved[1].layouts[3]).anchorInfo
    near(a.offsetX, -19, "frame right sits 10 right of the panel"); near(a.offsetY, -246, "frame top sits 40 above")
end

function T.a_hidden_panel_falls_back_to_the_frame()
    local seat = __load(__src)
    local panel = setmetatable({ _scale = 1, _l = 0, _t = 0, _w = 1, _h = 1 }, getmetatable(UIParent))
    panel.IsShown = function() return false end
    FS.Tracker = { Panel = function() return panel end }
    local x, y = seat.Offsets()
    near(x, -80); near(y, -300)
end

function T.questies_tracker_leaves_no_seat_to_show_or_move()
    local seat = __load(__src)
    FS.QuestieCompat = { TrackerActive = function() return true end }
    eq(seat.Ready(), false, "Blizzard's tracker is hidden while Questie's is on")
    eq(seat.Rect(), nil, "no rect for an invisible frame")
    eq(seat.Offsets(), nil)
    local ok, why = seat.Move(-29, -286)
    eq(ok, false); eq(why:find("Questie") ~= nil, true, why)
    ok, why = seat.Reset()
    eq(ok, false); eq(why:find("Questie") ~= nil, true, why)
    eq(#__saved, 0, "nothing written to the Edit Mode layout")
    eq(__touched, 0, "the tracker frame is never anchored")
end

function T.the_seat_is_back_when_questies_tracker_is_off()
    local seat = __load(__src)
    FS.QuestieCompat = { TrackerActive = function() return false end }
    eq(seat.Ready(), true)
    near(seat.Rect(), 2240)
    eq(seat.Move(-29, -286), true)
end

function T.questie_active_is_read_each_time_not_remembered()
    local seat = __load(__src)
    local on = true
    FS.QuestieCompat = { TrackerActive = function() return on end }
    eq(seat.Ready(), false)
    on = false
    eq(seat.Ready(), true)
end


-- ---- the tracker's Height ---------------------------------------------------------------------------------------------

function T.the_height_range_is_what_edit_mode_accepts()
    local h = __load(__src).HEIGHT
    eq(h.min, 400); eq(h.max, 1000); eq(h.step, 10); eq(h.default, 800, "the game's own layouts store 40, which is 800")
end

function T.the_height_reads_back_in_screen_units()
    movedLayout()
    local seat = __load(__src)
    eq(seat.Height(), 800)
    __saved_layouts[1].systems[2].settings[1].value = 50
    eq(seat.Height(), 900)
end

function T.moved_is_false_on_a_preset_and_on_a_default_seat_and_true_once_it_is_moved()
    local seat = __load(__src)
    eq(seat.Moved(), false, "a preset keeps the tracker in its default seat")
    __saved_layouts = { account("Mine", false) }
    __active = 3
    eq(seat.Moved(), false, "an account layout whose tracker was never moved")
    movedLayout()
    eq(seat.Moved(), true)
    __active = 1
    __saved_layouts = {}
    seat.Move(-29, -286)
    eq(seat.Moved(), true, "a move copies the preset and takes the tracker off its default seat")
end

function T.moved_is_unknown_while_the_layouts_are_not_loaded_or_edit_mode_is_missing()
    local seat = __load(__src)
    C_EditMode.GetLayouts = function() return nil end
    eq(seat.Moved(), nil, "no layouts yet")
    C_EditMode = nil
    eq(seat.Moved(), nil, "no Edit Mode")
end

function T.a_height_on_a_moved_account_layout_is_written_in_place_as_the_raw_value()
    movedLayout()
    local seat = __load(__src)
    eq(seat.SetHeight(900), true)
    eq(#__saved, 1)
    local info = __saved[1]
    eq(#info.layouts, 3, "no layout was copied")
    eq(info.activeLayout, 3); eq(__activated[1], 3)
    eq(heightOf(info.layouts[3]), 50, "(900 - 400) / 10")
    local t = tracker(info.layouts[3])
    eq(t.isInDefaultPosition, false, "the seat is untouched")
    eq(t.anchorInfo.offsetX, -110)
    eq(#t.settings, 3, "no setting was added")
    eq(t.settings[2].value, 0, "opacity is untouched"); eq(t.settings[3].value, 0, "text size is untouched")
    eq(info.layouts[3].systems[1].anchorInfo.offsetX, 5, "the other system is untouched")
    eq(__touched, 0, "the tracker frame is never anchored")
end

function T.a_height_snaps_to_the_step_and_clamps_to_the_range()
    movedLayout()
    local seat = __load(__src)
    seat.SetHeight(855); eq(heightOf(__saved[#__saved].layouts[3]), 46, "855 rounds to 860")
    seat.SetHeight(851); eq(heightOf(__saved[#__saved].layouts[3]), 45, "851 rounds to 850")
    seat.SetHeight(5000); eq(heightOf(__saved[#__saved].layouts[3]), 60, "above the range is 1000")
    seat.SetHeight(100); eq(heightOf(__saved[#__saved].layouts[3]), 0, "below the range is 400")
    local n = #__saved
    for _, junk in ipairs({ "tall", 0 / 0, 1 / 0, true }) do
        local ok, why, wait = seat.SetHeight(junk)
        eq(ok, false, "junk " .. tostring(junk)); eq(type(why), "string"); eq(wait, nil)
    end
    eq(#__saved, n, "junk saves nothing")
end

function T.an_unchanged_height_saves_nothing()
    movedLayout()
    local seat = __load(__src)
    eq(seat.SetHeight(800), true, "it is already 800")
    eq(#__saved, 0)
    seat.SetHeight(900); seat.SetHeight(900)
    eq(#__saved, 1, "the second write of the same value is not saved again")
end

function T.a_height_on_a_preset_or_a_default_seat_is_refused_for_good_and_copies_nothing()
    local seat = __load(__src)
    local ok, why, wait = seat.SetHeight(900)
    eq(ok, false); eq(why:find("default seat") ~= nil, true, why); eq(wait, nil, "moving the tracker is the player's step, not a wait")
    eq(#__saved, 0, "a preset is not copied for a slider")
    __saved_layouts = { account("Mine", false) }
    __active = 3
    ok, why = seat.SetHeight(900)
    eq(ok, false); eq(why:find("default seat") ~= nil, true, why)
    eq(#__saved, 0)
end

function T.a_height_is_held_in_combat_before_the_layouts_load_and_without_edit_mode_and_says_to_wait()
    movedLayout()
    local seat = __load(__src)
    __combat = true
    local ok, why, wait = seat.SetHeight(900)
    eq(ok, false); eq(why:find("combat") ~= nil, true, why); eq(wait, true)
    __combat = false
    local get = C_EditMode.GetLayouts
    C_EditMode.GetLayouts = function() return nil end
    ok, why, wait = seat.SetHeight(900)
    eq(ok, false); eq(why:find("loaded") ~= nil, true, why); eq(wait, true)
    C_EditMode.GetLayouts = get
    C_EditMode.SaveLayouts = nil
    ok, why, wait = seat.SetHeight(900)
    eq(ok, false); eq(why:find("not available") ~= nil, true, why); eq(wait, true)
    eq(#__saved, 0, "nothing was saved")
end

function T.questie_and_a_module_that_is_off_refuse_the_height_without_waiting()
    movedLayout()
    local seat = __load(__src)
    FS.QuestieCompat = { TrackerActive = function() return true end }
    local ok, why, wait = seat.SetHeight(900)
    eq(ok, false); eq(why:find("Questie") ~= nil, true, why); eq(wait, nil)
    eq(seat.Moved(), nil, "no seat to read while Questie has the tracker")
    FS.QuestieCompat = nil
    local off = __load(__src, { ModuleSwitch = { On = function() return false end } })
    ok, why, wait = off.SetHeight(900)
    eq(ok, false); eq(why:find("module is off") ~= nil, true, why); eq(wait, nil)
    eq(off.Moved(), nil)
    eq(#__saved, 0)
end

function T.a_client_without_the_height_setting_refuses_it()
    movedLayout()
    Enum.EditModeObjectiveTrackerSetting = nil
    local ok, why, wait = __load(__src).SetHeight(900)
    eq(ok, false); eq(type(why), "string"); eq(wait, nil)
    eq(#__saved, 0)
end

function T.a_layout_with_no_height_entry_or_no_settings_list_gets_one()
    movedLayout()
    local t = tracker(__saved_layouts[1])
    t.settings = { { setting = 1, value = 0 } }
    local seat = __load(__src)
    seat.SetHeight(900)
    local got = tracker(__saved[1].layouts[3]).settings
    eq(#got, 2); eq(heightOf(__saved[1].layouts[3]), 50, "an entry was added")
    eq(got[1].setting, 1); eq(got[1].value, 0, "the opacity entry stays")
    t = tracker(__saved_layouts[1])
    t.settings = nil
    seat.SetHeight(950)
    eq(heightOf(__saved[2].layouts[3]), 55, "a list was made")
end

function T.a_move_writes_the_height_the_setting_asks_for_in_the_same_save()
    FS = nil
    local seat = __load(__src, { Tracker = { WantedHeight = function() return 900 end } })
    eq(seat.Move(-29, -286), true)
    eq(#__saved, 1, "one save for the seat and the height")
    local new = __saved[1].layouts[3]
    eq(tracker(new).isInDefaultPosition, false)
    eq(heightOf(new), 50)
end

function T.a_move_leaves_the_layouts_height_alone_when_the_setting_holds_its_default()
    local seat = __load(__src, { Tracker = { WantedHeight = function() return nil end } })
    eq(seat.Move(-29, -286), true)
    eq(heightOf(__saved[1].layouts[3]), 40, "the preset's own height stays")
    local bare = __load(__src)
    bare.Move(-30, -290)
    eq(heightOf(__saved[2].layouts[3]), 40, "and with no Tracker module at all")
    local broken = __load(__src, { Tracker = { WantedHeight = function() error("boom") end } })
    eq(broken.Move(-31, -291), true, "a throwing setting read does not stop the move")
    eq(heightOf(__saved[3].layouts[3]), 40)
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__src = SEAT_FILE.read_text(encoding="utf-8")
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(boot().eval("__checks").keys())
    failed = 0
    for name in names:
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
