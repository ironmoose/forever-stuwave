#!/usr/bin/env python3
"""Runs the real GunsightShamanDrop.lua (click a Shaman pole to drop its totem) headless.

A left click on an element's pole column casts what that element's button on the totem tab casts, in and out of combat. The
catchers are secure action buttons OUTSIDE the Gunsight host tree (hung from Gunsight.root through a unit watched holder), because
the poles are plain frames and a secure child would make the host protected. The mock is strict about combat: SetAttribute,
SetPoint, ClearAllPoints, SetSize, SetFrameLevel, EnableMouse, Show and Hide on a secure frame raise in combat and are recorded, so
a case fails if the file writes one then. Pinned here:

  * nothing is built until the module has been seated; a catcher exists for an open element whose tab button casts, and for no other;
  * a catcher carries a COPY of the tab button's type1 / action1 / spell1 (spell mode and action mode), an empty type on every Alt form,
    no unit attribute (a unit would be handed to the cast), and nothing is ever written to the tab's buttons;
  * visibility is the client's own unit watch: the holder carries unit = "target" and RegisterUnitWatch (the equivalent of
    [@target,exists] show; hide), the holder is never shown or hidden by us, every catcher hangs from it, and the file uses no state
    driver, snippet, Execute or WrapScript (none run on this client);
  * the mouse is on only while the class module is in an area, the Gunsight is the display and the element is open and casts;
  * position and size follow the pole column in both areas and after a rescale, and are not rewritten when nothing moved;
  * in combat nothing secure is written; every change waits and PLAYER_REGEN_ENABLED replays it;
  * a locked or stripped tab button turns its catcher off and strips the copy; an element learned later gets a catcher at the next
    sync; a client without pass-through still works and says so once.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightshamandrop-harness.py

Exit 0 = every check passed. GUNSIGHTSHAMANDROP_LUA=<path> runs another file in place of GunsightShamanDrop.lua.
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

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
DROP = Path(os.environ.get("GUNSIGHTSHAMANDROP_LUA") or ADDON / "Modules/CombatHud/GunsightShamanDrop.lua")
SHAMAN = ADDON / "Modules/CombatHud/GunsightShaman.lua"
TOTEMBAR = ADDON / "Modules/ActionBars/TotemBar.lua"
TOC = ADDON / "forever-stuwave.toc"

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg, eps)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < (eps or 1e-6),
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end

COMBAT = false
BLOCKED = {}            -- every write a secure frame refused in combat
WRITES = 0              -- every write to a secure frame that was allowed
DEGRADED = {}
function InCombatLockdown() return COMBAT end

FRAMES = {}
local FrameMT = {}
FrameMT.__index = FrameMT
local SECURE_WRITES = { SetSize = true, SetPoint = true, ClearAllPoints = true, SetFrameLevel = true, EnableMouse = true,
    SetAttribute = true, Show = true, Hide = true }
local function guard(f, op)
    if not f.secure then return end
    if COMBAT then
        BLOCKED[#BLOCKED + 1] = op .. ":" .. tostring(f.name or f.kind)
        error("ADDON_ACTION_BLOCKED: " .. op .. " on " .. tostring(f.name or f.kind), 3)
    end
    WRITES = WRITES + 1
    f.writes[op] = (f.writes[op] or 0) + 1
end
function FrameMT:SetSize(w, h) guard(self, "SetSize"); self.w, self.h = w, h end
function FrameMT:SetPoint(point, rel, relPoint, x, y)
    guard(self, "SetPoint")
    self.points[#self.points + 1] = { point, rel, relPoint, x or 0, y or 0 }
end
function FrameMT:ClearAllPoints() guard(self, "ClearAllPoints"); self.points = {} end
function FrameMT:SetFrameLevel(n) guard(self, "SetFrameLevel"); self.level = n end
function FrameMT:GetFrameLevel() return self.level end
function FrameMT:EnableMouse(on) guard(self, "EnableMouse"); self.mouse = on and true or false end
function FrameMT:SetAttribute(k, v)
    guard(self, "SetAttribute")
    if self.readOnly then error("TAB_WRITTEN: " .. tostring(self.name) .. " " .. tostring(k), 2) end
    self.attrs[k] = v
end
function FrameMT:GetAttribute(k) return self.attrs[k] end
function FrameMT:Show() guard(self, "Show"); self.shown = true end
function FrameMT:Hide() guard(self, "Hide"); self.shown = false end
function FrameMT:IsShown() return self.shown end
function FrameMT:RegisterForClicks(...) self.clicks = { ... } end
function FrameMT:RegisterEvent(e) self.events[e] = true end
function FrameMT:SetScript(n, fn) self.scripts[n] = fn end
function FrameMT:GetParent() return self.parent end
function FrameMT:SetPassThroughButtons(...)
    if NO_PASSTHROUGH then error("not supported") end
    self.passThrough = { ... }
end
function FrameMT:ShouldButtonPassThrough(b)
    for _, x in ipairs(self.passThrough or {}) do if x == b then return true end end
    return false
end
function CreateFrame(kind, name, parent, template)
    local f = setmetatable({ kind = kind, name = name, parent = parent, template = template, attrs = {}, points = {}, events = {},
        scripts = {}, writes = {}, shown = true, level = (parent and parent.level or 0) + 1,
        secure = template ~= nil and template:find("Secure") ~= nil }, FrameMT)
    if NO_PASSTHROUGH then f.SetPassThroughButtons = false end     -- the method is absent on such a client
    FRAMES[#FRAMES + 1] = f
    if name then _G[name] = f end
    return f
end
function fire(event)
    for _, f in ipairs({ unpack(FRAMES) }) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event) end
    end
end

WATCHED = {}
function RegisterUnitWatch(f) WATCHED[#WATCHED + 1] = f end

-- The Gunsight: Point puts a frame's anchor at an image coordinate relative to the root's CENTER, exactly as Gunsight.lua does
GRID, CX, CY = 2, 100, 50
SCALE = 1
ROOT = CreateFrame("Frame", "ROOT")
ACTIVE, AREA = true, "upper"
local activeCbs, areaCbs, seatCbs, attrCbs, totemCbs = {}, {}, {}, {}, {}
FS = { LogDegradeOnce = function(k, m) DEGRADED[k] = (DEGRADED[k] or 0) + 1 end }
FS.Gunsight = {
    root = ROOT,
    ui = function(px) return px * GRID * SCALE end,
    Point = function(f, point, x, y)
        f:ClearAllPoints()
        f:SetPoint(point, ROOT, "CENTER", (x - CX) * GRID * SCALE, -(y - CY) * GRID * SCALE)
    end,
    IsActive = function() return ACTIVE end,
    OnActiveChanged = function(fn) activeCbs[#activeCbs + 1] = fn end,
}
FS.GunsightAreas = { AreaOf = function(id) check(id == "class", "asked for " .. tostring(id)); return AREA end,
    OnAreaChanged = function(fn) areaCbs[#areaCbs + 1] = fn end }
OX, OY = 100, 20
MODULE = CreateFrame("Frame", "MODULE", UIPARENT)
MODULE.level = 7
FS.GunsightShaman = {
    C = { GY = 78, NB = 8, BP = 6, HEAD_H = 9, CROWN_UP = 3, LABEL_Y = 19,
        POLES = { { key = "fire", x = 0, w = 50 }, { key = "earth", x = 54, w = 32 }, { key = "water", x = 90, w = 32 },
            { key = "air", x = 126, w = 32 } } },
    Origin = function() return OX, OY end,
    OnSeat = function(fn) seatCbs[#seatCbs + 1] = fn end,
}
FS.TotemBar = { OnAttributes = function(fn) attrCbs[#attrCbs + 1] = fn end }
UNLOCKED = { true, true, true, true }
FS.ShamanTotems = { IsUnlocked = function(slot) return UNLOCKED[slot] end,
    Subscribe = function(fn) totemCbs[#totemCbs + 1] = fn end }

-- the tab's four element buttons: read only for the file under test
TAB = {}
for slot = 1, 4 do
    local b = CreateFrame("Button", "FSTotemButton" .. slot, nil, "SecureActionButtonTemplate")
    TAB[slot] = b
end
function tabCasts(slot, mode, what)
    local b = TAB[slot]
    b.readOnly = false
    for _, k in ipairs({ "type1", "action1", "spell1" }) do b.attrs[k] = nil end
    if mode == "spell" then b.attrs.type1, b.attrs.spell1 = "spell", what
    elseif mode == "action" then b.attrs.type1, b.attrs.action1 = "action", what end
    b.readOnly = true
end
function tabAll()
    tabCasts(1, "spell", "Searing Totem"); tabCasts(2, "action", 25); tabCasts(3, "spell", "Mana Spring Totem")
    tabCasts(4, "spell", "Grace of Air Totem")
end

function listenerCounts() return #seatCbs, #areaCbs, #activeCbs, #attrCbs end
function seat() for _, fn in ipairs(seatCbs) do fn(OX, OY) end end
function areaChanged() for _, fn in ipairs(areaCbs) do fn() end end
function activeChanged() for _, fn in ipairs(activeCbs) do fn(ACTIVE) end end
function announce(slot) for _, fn in ipairs(attrCbs) do fn(TAB[slot]) end end
function totemNotify() for _, fn in ipairs(totemCbs) do fn(1, {}) end end

function load()
    local fn = assert(loadstring(DROP_SRC, "@GunsightShamanDrop.lua"))
    fn("forever-stuwave", FS)
    return FS.GunsightShamanDrop
end

-- the catcher's TOPLEFT as the file must seat it: the pole column from the module origin
function expectedPoint(slot, ox, oy)
    local def = FS.GunsightShaman.C.POLES[slot]
    local k = GRID * SCALE
    return (ox + def.x - CX) * k, -(oy + 10 - CY) * k, def.w * k, (101 - 10) * k
end
function checkSeat(D, slot, ox, oy, what)
    local b = D.catchers[slot]
    check(b, what .. ": no catcher " .. slot)
    local x, y, w, h = expectedPoint(slot, ox, oy)
    check(#b.points == 1, what .. ": " .. #b.points .. " anchor points")
    local p = b.points[1]
    check(p[1] == "TOPLEFT" and p[2] == ROOT and p[3] == "CENTER", what .. ": anchored " .. tostring(p[1]) .. " to " .. tostring(p[2] and p[2].name))
    near(p[4], x, what .. " x"); near(p[5], y, what .. " y"); near(b.w, w, what .. " w"); near(b.h, h, what .. " h")
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("nothing_is_built_at_load_and_one_listener_of_each_kind_is_registered")(r"""
local nFrames = #FRAMES
local D = load()
check(#FRAMES == nFrames, "a frame was made at load")
local a, b, c, d = listenerCounts()
check(a == 1 and b == 1 and c == 1 and d == 1, "one listener of each kind, got " .. a .. b .. c .. d)
check(next(D.catchers) == nil, "no catcher before the module exists")
FS.GunsightShaman.frame = MODULE
tabAll()
seat()
check(next(D.catchers) ~= nil, "a catcher once the module is built and seated")
""")

case("it_stays_silent_while_the_module_frame_does_not_exist")(r"""
FS.GunsightShaman.frame = nil
local D = load()
tabAll()
seat(); areaChanged(); announce(1); activeChanged(); totemNotify()
check(next(D.catchers) == nil, "a catcher was built with no module")
check(#WATCHED == 0, "a unit watch was registered with no module")
""")

case("a_catcher_exists_for_an_open_element_that_casts_and_for_no_other")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
tabCasts(3, nil)                  -- the tab's Water button has nothing to cast (locked)
UNLOCKED[4] = false               -- Air is not open yet on the poles
seat()
check(D.catchers[1] and D.catchers[2], "Fire and Earth catchers")
check(D.catchers[3] == nil, "a tab button with no type1 gets no catcher")
check(D.catchers[4] == nil, "a pole that is not open gets no catcher")
""")

case("a_catcher_carries_a_copy_of_the_tab_buttons_attributes_and_nothing_is_written_to_the_tab")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
local f, e = D.catchers[1], D.catchers[2]
check(f.attrs.type1 == "spell" and f.attrs.spell1 == "Searing Totem" and f.attrs.action1 == nil, "spell mode copy")
check(e.attrs.type1 == "action" and e.attrs.action1 == 25 and e.attrs.spell1 == nil, "action mode copy")
for _, n in ipairs({ "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" }) do
    check(f.attrs[n] == "", n .. " is an empty type")
end
check(f.attrs.unit == nil and e.attrs.unit == nil, "a unit attribute would be handed to the cast")
check(f.attrs.type == nil and f.attrs.spell == nil, "only the type1 family is copied")
for slot = 1, 4 do check(next(TAB[slot].writes) == nil, "the tab button " .. slot .. " was written: " .. tostring(next(TAB[slot].writes))) end
-- the tab changes its pick (spell to action), announces: the copy follows, the stale field goes
tabCasts(1, "action", 61)
announce(1)
check(f.attrs.type1 == "action" and f.attrs.action1 == 61 and f.attrs.spell1 == nil, "copy follows the tab's new pick")
""")

case("the_holder_is_the_unit_watch_and_every_catcher_hangs_from_it")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
check(#WATCHED == 1, "exactly one unit watch, got " .. #WATCHED)
local h = WATCHED[1]
check(h.template == "SecureUnitButtonTemplate", "the holder is a unit button, like the target menu's: " .. tostring(h.template))
check(h.attrs.unit == "target", "unit = target is [@target,exists]")
check(h.parent == ROOT, "the holder hangs from the Gunsight root")
check(h.mouse == false, "the holder takes no mouse")
check(h.level > MODULE.level, "the holder stands above the module frame")
for slot, b in pairs(D.catchers) do
    check(b.parent == h, "catcher " .. slot .. " hangs from the holder")
    check(b.template == "SecureActionButtonTemplate", "catcher " .. slot .. " template " .. tostring(b.template))
    check(b.level > h.level, "catcher above the holder")
end
-- the engine shows and hides it: we never do, in any of the many syncs
for i = 1, 3 do areaChanged(); seat(); activeChanged(); announce(1); totemNotify() end
check(h.writes.Show == nil and h.writes.Hide == nil, "the holder was shown or hidden by us")
for _, b in pairs(D.catchers) do check(b.writes.Hide == nil, "a catcher was hidden by us") end
check(#WATCHED == 1, "the unit watch was registered again")
""")

case("a_catcher_takes_left_clicks_on_the_tabs_click_registration_and_passes_the_rest_through")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
local b = D.catchers[1]
check(b.clicks and b.clicks[1] == "AnyUp" and b.clicks[2] == "AnyDown", "AnyUp and AnyDown, as the tab's buttons")
check(b.passThrough and b.passThrough[1] == "RightButton" and b.passThrough[2] == "MiddleButton", "right and middle fall through")
check(DEGRADED.gunsightshamandrop_passthrough == nil, "no complaint when pass-through works")
""")

case("a_client_without_pass_through_still_works_and_says_so_once")(r"""
NO_PASSTHROUGH = true
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
check(D.catchers[1] and D.catchers[1].mouse == true, "the pole click works without pass-through")
check(DEGRADED.gunsightshamandrop_passthrough == 1, "one line, however many catchers: got " .. tostring(DEGRADED.gunsightshamandrop_passthrough))
""")

case("the_mouse_follows_the_area_the_switch_and_the_element")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
for slot = 1, 4 do check(D.catchers[slot].mouse == true, "mouse on " .. slot) end
AREA = nil; areaChanged()
for slot = 1, 4 do check(D.catchers[slot].mouse == false, "module out of its area: mouse off " .. slot) end
AREA = "lower"; areaChanged()
for slot = 1, 4 do check(D.catchers[slot].mouse == true, "module back: mouse on " .. slot) end
ACTIVE = false; activeChanged()
for slot = 1, 4 do check(D.catchers[slot].mouse == false, "Gunsight off: mouse off " .. slot) end
ACTIVE = true; activeChanged()
UNLOCKED[2] = false; totemNotify()
check(D.catchers[2].mouse == false and D.catchers[1].mouse == true, "a pole that closed takes no click")
UNLOCKED[2] = true; totemNotify()
check(D.catchers[2].mouse == true, "and takes it again")
""")

case("a_stripped_tab_button_turns_its_catcher_off_and_strips_the_copy")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
tabCasts(2, nil)
announce(2)
local e = D.catchers[2]
check(e.mouse == false, "no cast, no click")
check(e.attrs.type1 == nil and e.attrs.action1 == nil and e.attrs["alt-type1"] == nil, "the copy is stripped")
tabCasts(2, "spell", "Stoneskin Totem")
announce(2)
check(e.mouse == true and e.attrs.spell1 == "Stoneskin Totem", "and comes back with the new pick")
""")

case("an_element_learned_later_gets_its_catcher_at_the_next_sync")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
tabCasts(3, nil); UNLOCKED[3] = false
seat()
check(D.catchers[3] == nil)
UNLOCKED[3] = true; tabCasts(3, "spell", "Healing Stream Totem")
announce(3)
check(D.catchers[3] and D.catchers[3].mouse == true and D.catchers[3].attrs.spell1 == "Healing Stream Totem", "built on the announcement")
checkSeat(D, 3, OX, OY, "late catcher")
""")

case("the_catchers_sit_over_the_pole_columns_in_both_areas")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
OX, OY = 107, 20
seat()
for slot = 1, 4 do checkSeat(D, slot, 107, 20, "upper") end
OX, OY = 107, 168                               -- the module moved to the lower area: seat(rect) says so
AREA = "lower"
seat(); areaChanged()
for slot = 1, 4 do checkSeat(D, slot, 107, 168, "lower") end
-- the columns do not overlap and are the poles' x ranges
local a, b = D.catchers[1], D.catchers[2]
check(a.points[1][4] + a.w <= b.points[1][4], "Fire's column ends before Earth's starts")
""")

case("a_rescale_resizes_and_reseats_and_an_unchanged_sync_writes_nothing")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
local before = WRITES
for i = 1, 5 do areaChanged(); announce(1); totemNotify(); activeChanged() end
check(WRITES == before, "an unchanged sync wrote " .. (WRITES - before) .. " times")
SCALE = 0.8
seat()
for slot = 1, 4 do checkSeat(D, slot, OX, OY, "rescaled") end
""")

case("nothing_secure_is_written_in_combat_and_the_regen_replays_it")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
tabCasts(3, nil); UNLOCKED[3] = false
seat()
COMBAT = true
local before = WRITES
-- everything that can change a catcher happens in combat: area, switch, a new pick, a rescale, a move, an element learned
AREA = nil; areaChanged()
ACTIVE = false; activeChanged()
tabCasts(1, "spell", "Magma Totem"); announce(1)
SCALE = 0.7; OX, OY = 50, 60; seat()
UNLOCKED[3] = true; tabCasts(3, "spell", "Healing Stream Totem"); announce(3)
totemNotify()
check(#BLOCKED == 0, "a secure write was attempted in combat: " .. tostring(BLOCKED[1]))
check(WRITES == before, "a secure frame was written in combat")
check(D.catchers[1].mouse == true and D.catchers[1].attrs.spell1 == "Searing Totem", "the catchers wait as they were")
check(D.catchers[3] == nil, "no frame is built in combat")
COMBAT = false
AREA = "upper"; ACTIVE = true
fire("PLAYER_REGEN_ENABLED")
check(#BLOCKED == 0)
check(D.catchers[1].attrs.spell1 == "Magma Totem", "the pick is copied at regen")
check(D.catchers[1].mouse == true and D.catchers[3] and D.catchers[3].mouse == true, "mouse and the late catcher at regen")
for slot = 1, 4 do checkSeat(D, slot, 50, 60, "regen") end
""")

case("a_regen_with_nothing_owed_writes_nothing")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
local before = WRITES
fire("PLAYER_REGEN_ENABLED")
check(WRITES == before, "nothing was owed")
""")

case("a_throwing_apply_is_logged_not_raised")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
FS.GunsightShaman.Origin = function() error("boom") end
seat()
check(DEGRADED.gunsightshamandrop_apply == 1, "the failure is logged once")
""")

case("an_apply_that_throws_is_retried_at_the_next_regen")(r"""
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
local origin = FS.GunsightShaman.Origin
local fail = true
FS.GunsightShaman.Origin = function() if fail then error("boom") end return origin() end
seat()
check(DEGRADED.gunsightshamandrop_apply == 1, "logged once")
check(next(D.catchers) == nil, "nothing was built yet")
fail = false
fire("PLAYER_REGEN_ENABLED")               -- no combat in between: the failed apply left itself owed
check(D.catchers[1] and D.catchers[1].mouse == true, "the retry at regen built and armed the catchers")
fire("PLAYER_REGEN_ENABLED")
check(DEGRADED.gunsightshamandrop_apply == 1, "no second line")
""")

case("without_a_unit_watch_api_the_catchers_stay_off_and_say_so")(r"""
RegisterUnitWatch = nil
FS.GunsightShaman.frame = MODULE
local D = load()
tabAll()
seat()
check(next(D.catchers) == nil, "without a unit watch the catchers would sit over the poles with no target: stay off")
check(DEGRADED.gunsightshamandrop_nounitwatch == 1)
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        d = toc.index("Modules/CombatHud/GunsightShamanDrop.lua")
        for dep in ("Modules/CombatHud/GunsightShaman.lua", "Modules/ActionBars/TotemBar.lua", "Modules/CombatHud/GunsightAreas.lua",
                    "Modules/CombatHud/ShamanTotems.lua"):
            out.append((f"toc_loads_the_click_catchers_after_{Path(dep).stem.lower()}",
                        None if toc.index(dep) < d else f"GunsightShamanDrop.lua must load after {dep}"))
    except ValueError as e:
        out.append(("toc_lists_the_click_catchers", f"{e}"))
    src = DROP.read_text(encoding="utf-8") if DROP.exists() else ""
    code = re.sub(r"--.*", "", src)
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "GunsightShamanDrop.lua has an em or en dash"))
    out.append(("no_state_driver_snippet_or_execute",
                None if not re.search(r"RegisterStateDriver|RegisterAttributeDriver|SecureHandler|WrapScript|:Execute\(|SetFrameRef|_onstate", code)
                else "state drivers and secure snippets do not run on this client"))
    out.append(("never_writes_the_tab_buttons",
                None if not re.search(r"\btab\s*:\s*SetAttribute|FSTotemButton\w*\s*:\s*SetAttribute|_G\[[^\]]*TAB[^\]]*\]\s*:\s*SetAttribute", code)
                else "the tab's buttons are read only from here"))
    out.append(("no_unit_attribute_on_a_catcher",
                None if len(re.findall(r'SetAttribute\("unit"', code)) == 1 else "only the holder carries a unit"))
    out.append(("never_shows_or_hides_a_secure_frame",
                None if not re.search(r":\s*(Show|Hide)\s*\(", code) else "the unit watch shows and hides the holder; never call Show or Hide"))
    out.append(("reads_no_totem_api_and_no_secret",
                None if not re.search(r"GetTotemInfo|GetTotemDuration|UnitPosition|UnitExists", code) else "this file decides no totem fact"))
    # the constants the fake module carries are the real module's
    shaman = SHAMAN.read_text(encoding="utf-8")
    want = {"GY": 78, "NB": 8, "BP": 6, "HEAD_H": 9, "CROWN_UP": 3, "LABEL_Y": 19}
    bad = []
    for k, v in want.items():
        m = re.search(rf"\b{k} = (\d+)", shaman)
        if not m or int(m.group(1)) != v:
            bad.append(f"{k}: harness {v}, GunsightShaman.lua {m.group(1) if m else 'missing'}")
    poles = re.findall(r'key = "(\w+)", x = (\d+), w = (\d+)', shaman)
    if poles != [("fire", "0", "50"), ("earth", "54", "32"), ("water", "90", "32"), ("air", "126", "32")]:
        bad.append(f"pole columns changed: {poles}")
    out.append(("fake_module_constants_match_gunsightshaman", None if not bad else "; ".join(bad)))
    bar = TOTEMBAR.read_text(encoding="utf-8")
    out.append(("totem_bar_announces_after_every_element_settle",
                None if bar.count("AnnounceAttributes(button)") == 3 and "function TotemBar.OnAttributes" in bar
                else "TotemBar.lua must call AnnounceAttributes after Lock and after the attributes are settled"))
    out.append(("tab_buttons_are_named_by_their_binding_slot",
                None if 'button = CreateFrame("Button", "FSTotemButton" .. index' in bar else "the tab's button names changed"))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().DROP_SRC = DROP.read_text(encoding="utf-8")
    try:
        lua.execute(body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not DROP.exists():
        print(f"FAIL  {DROP.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body)
        except LuaError as e:
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
