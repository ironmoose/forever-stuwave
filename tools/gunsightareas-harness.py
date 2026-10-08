#!/usr/bin/env python3
"""Runs the real GunsightAreas.lua (the two target side areas of the Gunsight HUD) headless against a mock WoW API.

GunsightAreas.lua owns the dot piece frame, the upper and lower area hosts under it, and the module
registry (FS.GunsightAreas.RegisterModule / AreaOf / OnAreaChanged) that the Target Debuffs and the
class modules plug into (mockups/gunsight-modules-concepts-v7-2026-10-08.html). The checks pin:

  * registration before and after the areas build, a module built once and lazily, the class spec
    chosen by the player's class token, a bad spec refused, a replaced spec retired;
  * the seam contract: build(host), seat(rect) with the area's image px rect (at build, on a move and
    on a rescale), onShow / onHide with the area name, AreaOf, OnAreaChanged;
  * assignment: a pick, a swap, a profile switch and a direct config write move modules between areas,
    Empty draws nothing, the dot piece off hides both areas, two areas that name one family show it once;
  * the "classSoon" fallback: shown in an area set to the Class Module only when the player's class has no class
    module, retired by a later registration, never shown for an unreadable class token;
  * the target gate: a Target Debuffs host follows FS.TargetTakesDots, the class host does not.

The mock is the Gunsight harness mock plus SetParent and RegisterUnitEvent. Theme is not loaded and
FS.TargetTakesDots, UnitClass are stubs; the real Layout.lua, Config.lua, Gunsight.lua are loaded.

    python3 tools/gunsightareas-harness.py

Exit 0 = every check passed. GUNSIGHTAREAS_LUA=<path> runs another file in place of GunsightAreas.lua.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
AREAS = Path(os.environ.get("GUNSIGHTAREAS_LUA") or ADDON / "Modules/CombatHud/GunsightAreas.lua")
GUNSIGHT = ADDON / "Modules/CombatHud/Gunsight.lua"
LAYOUT = ADDON / "Core/Layout.lua"
CONFIG = ADDON / "Core/Config.lua"
TOC = ADDON / "forever-stuwave.toc"


def _load_gunsight_harness():
    spec = importlib.util.spec_from_file_location("gunsight_harness", HERE / "gunsight-harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GH = _load_gunsight_harness()

EXTRA_MOCK = r"""
local Frame = getmetatable(UIParent).__index
function Frame:SetParent(p)
    if self.parent then
        for i, c in ipairs(self.parent.children) do
            if c == self then table.remove(self.parent.children, i) break end
        end
    end
    self.parent = p
    if p then p.children[#p.children + 1] = self end
end
function Frame:RegisterUnitEvent(e) self.events[e] = true end

TARGET = true
CLASS = "WARLOCK"
function UnitClass() return CLASS == "WARLOCK" and "Warlock" or CLASS, CLASS end
"""

PRELUDE = r"""
local function boot(opts)
    opts = opts or {}
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db or {}
    function UnitGUID() return "Player-1-0001" end
    CLASS = opts.class or "WARLOCK"
    TARGET = true
    function FS.TargetTakesDots() return TARGET end
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
    if opts.before then opts.before() end
    fire("ADDON_LOADED", "forever-stuwave")
    if opts.beforeLogin then opts.beforeLogin() end
    fire("PLAYER_LOGIN")
    return FS.Gunsight, FS.GunsightAreas
end

-- A fake module: records every call the seam makes.
local function module(name)
    local m = { name = name, built = 0, seated = {}, shows = {}, hides = {} }
    m.spec = {
        build = function(host)
            m.built = m.built + 1
            m.host = host
            m.frame = CreateFrame("Frame", "Fake" .. name, host)
            return m.frame
        end,
        seat = function(rect) m.seated[#m.seated + 1] = { x = rect.x, y = rect.y, w = rect.w, h = rect.h } end,
        onShow = function(area) m.shows[#m.shows + 1] = area end,
        onHide = function(area) m.hides[#m.hides + 1] = area end,
    }
    return m
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("registered_before_the_build_gets_host_rect_and_onshow")(r"""
local dh = module("dh")
local Gs, Areas = boot({ before = function() FS.GunsightAreas.RegisterModule("debuffsH", dh.spec) end })
check(dh.built == 1, "build ran once, got " .. dh.built)
check(dh.host == Areas.Host("upper"), "build gets the upper host")
check(dh.frame:GetParent() == dh.host, "the module frame hangs off its host")
local r = dh.seated[1]
check(r and r.x == 1213 and r.y == 500 and r.w == 202 and r.h == 128, "seat rect is the upper area in image px")
check(table.concat(dh.shows, ",") == "upper", "onShow(upper), got " .. table.concat(dh.shows, ","))
check(Areas.AreaOf("debuffsH") == "upper", "AreaOf debuffsH")
check(Areas.AreaOf("debuffsV") == nil and Areas.AreaOf("class") == nil, "unregistered modules are nowhere")
check(dh.frame:IsShown(), "the module frame is shown")
""")

case("registered_after_the_build_works_the_same")(r"""
local Gs, Areas = boot()
local calls = 0
Areas.OnAreaChanged(function() calls = calls + 1 end)
local before = calls
local cl = module("cl")
cl.spec.classes = { "WARLOCK" }
check(Areas.RegisterModule("class", cl.spec) == true, "RegisterModule class")
check(cl.built == 1 and cl.host == Areas.Host("lower"), "class built into the lower host")
check(Areas.AreaOf("class") == "lower", "AreaOf class")
check(table.concat(cl.shows, ",") == "lower", "onShow(lower)")
check(calls == before + 1, "OnAreaChanged fired for the registration")
""")

case("the_class_spec_is_chosen_by_the_class_token")(r"""
local pal, wl = module("pal"), module("wl")
pal.spec.classes = { "PALADIN" }
wl.spec.classes = { "WARLOCK", "ROGUE" }
local Gs, Areas = boot({ class = "ROGUE", before = function()
    FS.GunsightAreas.RegisterModule("class", pal.spec)
    FS.GunsightAreas.RegisterModule("class", wl.spec)
end })
check(pal.built == 0, "the paladin class module is never built for a rogue")
check(wl.built == 1 and Areas.AreaOf("class") == "lower", "the rogue gets the module whose classes list it")
""")

case("a_class_with_no_spec_draws_nothing")(r"""
local pal = module("pal")
pal.spec.classes = { "PALADIN" }
local Gs, Areas = boot({ class = "MAGE", before = function() FS.GunsightAreas.RegisterModule("class", pal.spec) end })
check(pal.built == 0, "no build for another class")
check(Areas.AreaOf("class") == nil, "AreaOf class is nil for a mage")
check(not Areas.Host("lower"):IsShown(), "the lower host draws nothing")
""")

case("a_class_with_no_module_falls_back_to_the_coming_soon_plate")(r"""
local pal, soon = module("pal"), module("soon")
pal.spec.classes = { "PALADIN" }
local Gs, Areas = boot({ class = "MAGE", before = function()
    FS.GunsightAreas.RegisterModule("class", pal.spec)
    FS.GunsightAreas.RegisterModule("classSoon", soon.spec)
end })
check(Gs.GetArea("lower") == "class", "the lower area is set to the Class Module by default")
check(soon.built == 1 and soon.host == Areas.Host("lower"), "the plate is built into the lower host")
check(soon.frame:IsShown() and table.concat(soon.shows, ",") == "lower", "the plate is shown with onShow(lower)")
check(soon.seated[1] and soon.seated[1].y == 632, "the plate is seated with the lower rect")
check(pal.built == 0, "another class's module is never built")
check(Areas.AreaOf("class") == nil, "AreaOf class stays nil: no real class module is shown")
check(Areas.AreaOf("classSoon") == "lower", "AreaOf classSoon reports where the plate is")
check(Areas.Host("lower"):IsShown(), "the host is shown for the plate")
Gs.SetArea("upper", "class")
check(Areas.AreaOf("classSoon") == "upper" and soon.shows[#soon.shows] == "upper", "the plate follows the Class Module pick")
check(soon.hides[#soon.hides] == "lower", "and left the lower area")
""")

case("a_class_with_a_module_never_gets_the_plate")(r"""
local cl, soon = module("cl"), module("soon")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ class = "WARLOCK", before = function()
    FS.GunsightAreas.RegisterModule("classSoon", soon.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
check(cl.built == 1 and Areas.AreaOf("class") == "lower", "the real module is shown")
check(soon.built == 0 and #soon.shows == 0 and Areas.AreaOf("classSoon") == nil, "the plate is never built or shown")
""")

case("the_plate_shows_only_while_an_area_is_set_to_the_class_module")(r"""
local soon = module("soon")
local Gs, Areas = boot({ class = "MAGE", before = function() FS.GunsightAreas.RegisterModule("classSoon", soon.spec) end })
check(Areas.AreaOf("classSoon") == "lower", "shown while the lower area is the Class Module")
Gs.SetArea("lower", "empty")
check(Areas.AreaOf("classSoon") == nil and not soon.frame:IsShown(), "an area set to Empty hides it")
check(soon.hides[#soon.hides] == "lower", "onHide(lower)")
Gs.SetArea("upper", "empty")
Gs.SetArea("lower", "debuffsH")
check(Areas.AreaOf("classSoon") == nil, "no plate while no area is the Class Module")
local before = #soon.shows
Gs.SetArea("lower", "class")
check(Areas.AreaOf("classSoon") == "lower" and #soon.shows == before + 1, "back when the pick returns")
Gs.SetPiece("dot", false, true)
check(Areas.AreaOf("classSoon") == nil and not soon.frame:IsShown(), "the dot piece off hides it")
""")

case("a_class_module_registered_later_retires_the_plate")(r"""
local soon, cl = module("soon"), module("cl")
cl.spec.classes = { "MAGE" }
local Gs, Areas = boot({ class = "MAGE", before = function() FS.GunsightAreas.RegisterModule("classSoon", soon.spec) end })
check(Areas.AreaOf("classSoon") == "lower", "the plate shows first")
Areas.RegisterModule("class", cl.spec)
check(Areas.AreaOf("class") == "lower" and cl.frame:IsShown(), "the new module takes the area")
check(Areas.AreaOf("classSoon") == nil and not soon.frame:IsShown(), "the plate is gone without any change to the plate")
check(soon.hides[#soon.hides] == "lower", "onHide(lower)")
""")

case("no_plate_when_the_class_cannot_be_read")(r"""
local soon = module("soon")
local Gs, Areas = boot({ class = nil, before = function()
    CLASS = nil
    FS.GunsightAreas.RegisterModule("classSoon", soon.spec)
end })
check(Areas.AreaOf("classSoon") == nil and soon.built == 0, "an unreadable class token draws nothing, not a wrong coming soon")
""")

case("bad_specs_are_refused")(r"""
local Gs, Areas = boot()
check(Areas.RegisterModule("bogus", module("x").spec) == false, "unknown id")
check(Areas.RegisterModule("debuffsH", {}) == false, "no build function")
check(Areas.RegisterModule("debuffsH", nil) == false, "no spec")
local noClasses = module("n")
check(Areas.RegisterModule("class", noClasses.spec) == false, "a class spec needs classes")
check(Areas.RegisterModule("class", { build = noClasses.spec.build, classes = {} }) == false, "an empty classes list")
check(Areas.AreaOf("debuffsH") == nil, "nothing was registered")
""")

case("a_throwing_build_draws_nothing_and_is_logged_once")(r"""
local n = 0
local Gs, Areas = boot()
Areas.RegisterModule("debuffsH", { build = function() n = n + 1 error("boom") end })
check(Areas.AreaOf("debuffsH") == nil, "a module that failed to build is not shown")
check(n == 1, "a failed build is not retried every refresh, ran " .. n)
local cl = module("cl")
cl.spec.classes = { "WARLOCK" }
Areas.RegisterModule("class", cl.spec)
check(Areas.AreaOf("class") == "lower", "another module still works")
local any = false
for k in pairs(DEGRADED) do any = true end
check(any, "the failure is logged")
""")

case("a_throwing_hook_does_not_break_the_areas")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
dh.spec.onShow = function() error("boom") end
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
check(Areas.AreaOf("debuffsH") == "upper" and Areas.AreaOf("class") == "lower", "both still placed")
""")

case("the_dot_piece_owns_the_hosts_and_gates_both_areas")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
local up, lo = Areas.Host("upper"), Areas.Host("lower")
check(up:GetParent() == lo:GetParent(), "both hosts share one parent: the dot piece frame")
local piece = up:GetParent()
check(piece:GetParent() == Gs.root, "the piece frame hangs off the Gunsight root")
check(piece:IsShown() and Gs.IsPieceOn("dot"), "the dot piece is on and shown")
Gs.SetPiece("dot", false, true)
check(not piece:IsShown(), "the piece off hides the frame that holds both areas")
check(Areas.AreaOf("debuffsH") == nil and Areas.AreaOf("class") == nil, "AreaOf is nil with the dot piece off")
check(dh.hides[#dh.hides] == "upper" and cl.hides[#cl.hides] == "lower", "onHide ran for both with their areas")
check(not dh.frame:IsShown() and not cl.frame:IsShown(), "the module frames are hidden")
Gs.SetPiece("dot", true, true)
check(piece:IsShown(), "the piece on shows the frame again")
check(Areas.AreaOf("debuffsH") == "upper" and Areas.AreaOf("class") == "lower", "AreaOf is back")
check(dh.shows[#dh.shows] == "upper" and cl.shows[#cl.shows] == "lower", "onShow ran again")
""")

case("the_dot_piece_is_the_target_side_master_switch_via_config")(r"""
local dh = module("dh")
local Gs, Areas = boot({ db = { }, before = function() FS.GunsightAreas.RegisterModule("debuffsH", dh.spec) end })
FS.Config.Set("gunsight.pieces.dot", false)
check(Areas.AreaOf("debuffsH") == nil, "a config write that turns the piece off hides the area")
FS.Config.Set("gunsight.pieces.dot", true)
check(Areas.AreaOf("debuffsH") == "upper", "and on shows it")
""")

case("a_pick_swaps_modules_between_the_areas")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
local calls = 0
Areas.OnAreaChanged(function() calls = calls + 1 end)
local seatsDh, seatsCl = #dh.seated, #cl.seated
Gs.SetArea("upper", "class")
check(calls == 1, "one notification for a swap, got " .. calls)
check(Areas.AreaOf("class") == "upper" and Areas.AreaOf("debuffsH") == "lower", "modules swapped")
check(dh.hides[#dh.hides] == "upper" and dh.shows[#dh.shows] == "lower", "debuffs left upper and entered lower")
check(cl.hides[#cl.hides] == "lower" and cl.shows[#cl.shows] == "upper", "class left lower and entered upper")
local r = dh.seated[#dh.seated]
check(#dh.seated == seatsDh + 1 and r.y == 632, "debuffs seated once with the lower rect, y " .. tostring(r.y))
check(cl.seated[#cl.seated].y == 500, "class seated with the upper rect")
check(dh.frame:GetParent() == Areas.Host("lower") and cl.frame:GetParent() == Areas.Host("upper"), "frames moved to the other host")
check(dh.built == 1 and cl.built == 1, "a module is built once, however often it moves")
check(dh.frame:IsShown() and cl.frame:IsShown(), "both visible")
""")

case("empty_draws_nothing")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
Gs.SetArea("lower", "empty")
check(Areas.AreaOf("class") == nil, "class is nowhere")
check(not cl.frame:IsShown() and not Areas.Host("lower"):IsShown(), "the empty area shows no frame")
check(cl.hides[#cl.hides] == "lower", "onHide(lower)")
Gs.SetArea("upper", "empty")
check(Areas.AreaOf("debuffsH") == nil and not Areas.Host("upper"):IsShown(), "both empty")
local shown = 0
for _, f in ipairs(FRAMES) do if f.shown and f.kind == "Frame" and f.name and f.name:find("^Fake") then shown = shown + 1 end end
check(shown == 0, "no module frame is shown")
""")

case("unbuilt_modules_are_not_built_until_assigned")(r"""
local dv = module("dv")
local Gs, Areas = boot({ before = function() FS.GunsightAreas.RegisterModule("debuffsV", dv.spec) end })
check(dv.built == 0, "debuffsV is not assigned, so it is not built")
Gs.SetArea("upper", "debuffsV")
check(dv.built == 1 and Areas.AreaOf("debuffsV") == "upper", "built when picked")
""")

case("a_profile_switch_moves_the_modules")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
Gs.SetArea("upper", "class")
check(Areas.AreaOf("class") == "upper", "set up")
local calls = 0
Areas.OnAreaChanged(function() calls = calls + 1 end)
check(FS.Config.NewProfile("Other") == true, "NewProfile")
check(FS.Config.SetActiveProfile("Other") == true, "SetActiveProfile")
check(Areas.AreaOf("class") == "lower" and Areas.AreaOf("debuffsH") == "upper", "the other profile's defaults apply")
check(calls >= 1, "OnAreaChanged fired for the switch")
check(dh.frame:GetParent() == Areas.Host("upper") and cl.frame:GetParent() == Areas.Host("lower"), "frames follow")
""")

case("one_family_in_both_areas_shows_once_in_the_upper")(r"""
local cl = module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function() FS.GunsightAreas.RegisterModule("class", cl.spec) end })
FS.Config.Set("gunsight.target.upper", "class")
check(Areas.AreaOf("class") == "upper", "the upper area wins")
check(cl.built == 1, "one frame, one build")
FS.Config.Set("gunsight.target.upper", "debuffsH")
FS.Config.Set("gunsight.target.lower", "debuffsV")
local dh, dv = module("dh"), module("dv")
Areas.RegisterModule("debuffsH", dh.spec)
Areas.RegisterModule("debuffsV", dv.spec)
check(Areas.AreaOf("debuffsH") == "upper" and Areas.AreaOf("debuffsV") == nil, "H and V are one family, the lower yields")
""")

case("rescale_reseats_the_hosts_and_the_shown_modules")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ height = 1440, before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
local up = Areas.Host("upper")
local l, b, w, h = rect(up)
near(w, 202 * 1.28, "upper host width at 1440"); near(h, 128 * 1.28, "upper host height at 1440")
local l2, b2, w2, h2 = rect(Gs.anchors.areaU)
near(l, l2, "host left matches the areaU anchor"); near(b + h, b2 + h2, "host top matches the areaU anchor")
local n = #dh.seated
SetScreen(1200)
fire("UI_SCALE_CHANGED")
local _, _, w3 = rect(up)
near(w3, 202 * 1.28 * 1200 / 1440, "upper host width at 1200")
local lowW = select(3, rect(Areas.Host("lower")))
near(lowW, 202 * 1.28 * 1200 / 1440, "lower host width at 1200")
check(#dh.seated == n + 1 and #cl.seated >= 2, "seat is called again on a rescale")
check(dh.seated[#dh.seated].w == 202, "the rect stays in image px")
""")

case("the_debuffs_host_follows_the_target_gate_but_the_class_host_does_not")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
local up, lo = Areas.Host("upper"), Areas.Host("lower")
check(up:IsShown() and lo:IsShown(), "both hosts shown with a target")
local hidesBefore = #dh.hides
TARGET = false
fire("PLAYER_TARGET_CHANGED")
check(not up:IsShown(), "no attackable target hides the debuffs host")
check(lo:IsShown(), "the class host is not gated by the target")
check(Areas.AreaOf("debuffsH") == "upper", "AreaOf ignores the gate")
check(#dh.hides == hidesBefore, "the gate is not onHide, so the Hud ledger keeps running")
TARGET = true
fire("PLAYER_TARGET_CHANGED")
check(up:IsShown(), "a target brings it back")
TARGET = false
fire("UNIT_HEALTH", "target")
check(not up:IsShown(), "a unit event for the target re-reads the gate")
TARGET = true
fire("PLAYER_ENTERING_WORLD")
check(up:IsShown(), "entering the world re-reads the gate")
-- the gate follows the module, not the area: swap and the class host moves up, ungated
TARGET = false
fire("PLAYER_TARGET_CHANGED")
Gs.SetArea("upper", "class")
check(up:IsShown() and not lo:IsShown(), "after a swap the gated host is the lower one")
""")

case("the_dot_piece_registers_with_the_gunsight")(r"""
local Gs, Areas = boot()
local found
for _, f in ipairs(FRAMES) do
    if f.name == "ForeverSTUwaveGunsightTargetSide" then found = f end
end
check(found and found:GetParent() == Gs.root, "the piece frame exists under the root")
check(Areas.Host("upper") ~= nil and Areas.Host("lower") ~= nil and Areas.Host("middle") == nil, "Host answers upper and lower only")
local ok = Gs.RegisterPiece("dot", { frame = found })
check(ok, "the dot key is a known piece")
""")

case("a_disabled_gunsight_builds_nothing")(r"""
local dh = module("dh")
local Gs, Areas = boot({ db = { gunsight = { enabled = false } },
    before = function() FS.GunsightAreas.RegisterModule("debuffsH", dh.spec) end })
check(Gs.IsEnabled() == false, "disabled")
check(dh.built == 0 and Areas.AreaOf("debuffsH") == nil, "nothing is built while disabled")
check(Areas.Host("upper") == nil, "no host frames")
""")

case("replacing_a_module_retires_the_old_one")(r"""
local a, b = module("a"), module("b")
local Gs, Areas = boot({ before = function() FS.GunsightAreas.RegisterModule("debuffsH", a.spec) end })
check(Areas.AreaOf("debuffsH") == "upper" and a.built == 1, "first registered")
Areas.RegisterModule("debuffsH", b.spec)
check(a.hides[#a.hides] == "upper" and not a.frame:IsShown(), "the old module is hidden")
check(b.built == 1 and b.shows[#b.shows] == "upper" and b.frame:IsShown(), "the new one takes the area")
""")

case("on_area_changed_callbacks_survive_a_throwing_listener")(r"""
local Gs, Areas = boot()
local got = 0
Areas.OnAreaChanged(function() error("boom") end)
Areas.OnAreaChanged(function() got = got + 1 end)
Gs.SetArea("upper", "empty")
check(got >= 1, "the second listener still runs")
""")


case("the_coming_soon_plate_shows_swaps_and_hides_in_combat")(r"""
-- a class with no module (MAGE), so the plate really is the occupant; the plate is a plain frame and nothing gates it on combat
local soon = module("soon")
IN_COMBAT = true
local Gs, Areas = boot({ class = "MAGE", before = function() FS.GunsightAreas.RegisterModule("classSoon", soon.spec) end })
check(InCombatLockdown() == true, "the case runs in combat")
check(Areas.AreaOf("classSoon") == "lower" and soon.frame:IsShown(), "the plate shows in combat")
check(soon.shows[#soon.shows] == "lower", "onShow(lower) in combat")
Gs.SetArea("upper", "class")
check(Areas.AreaOf("classSoon") == "upper" and soon.shows[#soon.shows] == "upper", "the plate follows a swap to the upper area in combat")
check(soon.hides[#soon.hides] == "lower" and soon.frame:IsShown(), "and left the lower area in combat")
Gs.SetArea("upper", "empty")
check(Areas.AreaOf("classSoon") == nil and not soon.frame:IsShown(), "an area set to something else hides the plate in combat")
check(soon.hides[#soon.hides] == "upper", "onHide(upper) in combat")
Gs.SetArea("lower", "class")
check(Areas.AreaOf("classSoon") == "lower" and soon.frame:IsShown(), "and it comes back in combat")
check(#BLOCKED == 0, "nothing protected was touched in combat: " .. table.concat(BLOCKED, ","))
""")

case("refreshing_in_combat_blocks_nothing")(r"""
local dh, cl = module("dh"), module("cl")
cl.spec.classes = { "WARLOCK" }
local Gs, Areas = boot({ before = function()
    FS.GunsightAreas.RegisterModule("debuffsH", dh.spec)
    FS.GunsightAreas.RegisterModule("class", cl.spec)
end })
-- every frame the areas own is plain, and the mock records any Show, Hide or EnableMouse on a protected frame in combat
IN_COMBAT = true
Gs.SetArea("upper", "class")
check(Areas.AreaOf("class") == "upper" and Areas.AreaOf("debuffsH") == "lower", "a swap in combat still moves the modules")
Gs.SetPiece("dot", false, true)
Gs.SetPiece("dot", true, true)
TARGET = false
fire("PLAYER_TARGET_CHANGED")
check(not Areas.Host("lower"):IsShown(), "the gate still works in combat")
SetScreen(1200)
fire("UI_SCALE_CHANGED")
local late = module("late")
Areas.RegisterModule("debuffsV", late.spec)
Gs.SetArea("lower", "debuffsV")
check(Areas.AreaOf("debuffsV") == "lower", "a module first built in combat is placed")
for _, f in ipairs(FRAMES) do
    check(f.protected ~= true, "no frame is protected: " .. tostring(f.name))
end
check(#BLOCKED == 0, "nothing protected was touched in combat: " .. table.concat(BLOCKED, ","))
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        g, a = toc.index("Modules/CombatHud/Gunsight.lua"), toc.index("Modules/CombatHud/GunsightAreas.lua")
        first = min(toc.index(f"Modules/CombatHud/{n}.lua") for n in ("TargetDebuffs", "GunsightDots", "GunsightSeals", "GunsightClass"))
        out.append(("toc_order", None if g < a < first else
                    f"GunsightAreas.lua must load after Gunsight.lua and before the modules (positions {g}, {a}, {first})"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = AREAS.read_text(encoding="utf-8") if AREAS.exists() else ""
    out.append(("no_em_dash_and_no_tape_wording", None if chr(0x2014) not in src and "tape" not in src.lower() else
                "GunsightAreas.lua has an em dash or the word tape"))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(GH.MOCK)
    lua.execute(EXTRA_MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = LAYOUT.read_text(encoding="utf-8")
    g.CONFIG_SRC = CONFIG.read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = GUNSIGHT.read_text(encoding="utf-8")
    g.AREAS_SRC = AREAS.read_text(encoding="utf-8")
    runner = lua.eval(
        "function(src) local f, e = loadstring(src, '=case'); if not f then return false, e end; "
        "local ok, err = pcall(f); if ok then if #BLOCKED > 0 then return false, 'ADDON_ACTION_BLOCKED: ' .. "
        "table.concat(BLOCKED, ', ') end; return true, '' end; return false, tostring(err) end")
    ok, err = runner(PRELUDE + "\n" + body)
    return None if ok else str(err)


def main() -> int:
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    for name, body in CASES:
        try:
            err = run_case(name, body)
        except LuaError as e:  # a harness bug, not a pass
            err = f"harness error: {e}"
        report(name, err)
    for name, err in static_checks():
        report(name, err)
    total = len(CASES) + len(static_checks())
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
