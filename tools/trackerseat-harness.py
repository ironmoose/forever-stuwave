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
  * while Questie's tracker is on, Blizzard's is hidden, so there is no seat to show or move.

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
}
Constants = { EditModeConsts = { EditModeMaxLayoutsPerType = 5 } }

function CopyTable(t)
    local c = {}
    for k, v in pairs(t) do c[k] = type(v) == "table" and CopyTable(v) or v end
    return c
end

local function system(id, x, y, default)
    return { system = id, isInDefaultPosition = default,
        anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = x, offsetY = y } }
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

function __load(src)
    FS = {}
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
local function account(name)
    return { layoutName = name, layoutType = 1, systems = { { system = 0, isInDefaultPosition = false, anchorInfo = { offsetX = 5 } },
        { system = 12, isInDefaultPosition = true, anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = -110, offsetY = -260 } } } }
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
