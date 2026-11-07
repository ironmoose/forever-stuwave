#!/usr/bin/env python3
"""Runs the real GunsightWarriorClick.lua (click a Warrior helm to shout) headless.

A left click on the Battle Shout helm casts Battle Shout, on the Demoralizing Shout helm Demoralizing Shout, in and out of combat.
The catchers are secure action buttons OUTSIDE the Gunsight host tree (hung from Gunsight.root through a unit watched holder), as
GunsightShamanDrop.lua's are. The mock is strict about combat: every write to a secure frame raises in combat. Pinned here:

  * nothing is built until the module exists and has been seated; a catcher exists for a known shout only;
  * a catcher casts its shout by name (type1 / spell1), every Alt form is an empty type, and it carries no unit;
  * the holder is the client's unit watch (unit = "target"), never shown or hidden by us;
  * the mouse is on only while the class module is in an area, the Gunsight is the display and the shout is known;
  * position and size cover the helm sprite box, follow the module and a rescale, and are not rewritten when nothing moved;
  * in combat nothing secure is written; PLAYER_REGEN_ENABLED replays it; a shout learned later gets its catcher.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightwarriorclick-harness.py

Exit 0 = every check passed. GUNSIGHTWARRIORCLICK_LUA=<path> runs another file in place of GunsightWarriorClick.lua.
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
CLICK = Path(os.environ.get("GUNSIGHTWARRIORCLICK_LUA") or ADDON / "Modules/CombatHud/GunsightWarriorClick.lua")
WARRIOR = ADDON / "Modules/CombatHud/GunsightWarrior.lua"
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
local activeCbs, areaCbs, seatCbs, shoutCbs = {}, {}, {}, {}
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
MODULE = CreateFrame("Frame", "MODULE", nil)
MODULE.level = 7
FS.GunsightWarrior = {
    C = { SPX = 1.25, CY = 35, HELM_W = 32, HELM_H = 32, HELM_OX = 3,
        RINGS = { battle = { cx = 42 }, demo = { cx = 112 } } },
    Origin = function() return OX, OY end,
    OnSeat = function(fn) seatCbs[#seatCbs + 1] = fn end,
}
KNOWN = { battle = true, demo = true }
FS.WarriorShouts = {
    DEFS = { battle = { name = "Battle Shout" }, demo = { name = "Demoralizing Shout" } },
    Get = function(key) return { known = KNOWN[key], localName = LOCAL_NAME and LOCAL_NAME[key] or nil } end,
    Subscribe = function(fn) shoutCbs[#shoutCbs + 1] = fn end,
}

function seat() for _, fn in ipairs(seatCbs) do fn(OX, OY) end end
function areaChanged() for _, fn in ipairs(areaCbs) do fn() end end
function activeChanged() for _, fn in ipairs(activeCbs) do fn(ACTIVE) end end
function learn() for _, fn in ipairs(shoutCbs) do fn("demo", "learn") end end
function listenerCounts() return #seatCbs, #areaCbs, #activeCbs end

function load()
    local fn = assert(loadstring(CLICK_SRC, "@GunsightWarriorClick.lua"))
    fn("forever-stuwave", FS)
    return FS.GunsightWarriorClick
end

-- the helm box as the file must seat it (sprite px from the module, times SPX image px)
function checkSeat(D, key, ox, oy, what)
    local b = D.catchers[key]
    check(b, what .. ": no catcher " .. key)
    local W = FS.GunsightWarrior.C
    local k = GRID * SCALE
    local x = ox + (W.RINGS[key].cx - 13 - W.HELM_OX - 1) * W.SPX
    local y = oy + (W.CY - 12 - 1) * W.SPX
    check(#b.points == 1, what .. ": " .. #b.points .. " anchor points")
    local p = b.points[1]
    check(p[1] == "TOPLEFT" and p[2] == ROOT and p[3] == "CENTER", what .. ": anchor")
    near(p[4], (x - CX) * k, what .. " x"); near(p[5], -(y - CY) * k, what .. " y")
    near(b.w, (W.HELM_W + 2) * W.SPX * k, what .. " w"); near(b.h, (W.HELM_H + 2) * W.SPX * k, what .. " h")
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("nothing_is_built_before_the_module_and_one_listener_of_each_kind")(r"""
local n = #FRAMES
local D = load()
check(#FRAMES == n, "a frame was made at load")
local a, b, c = listenerCounts()
check(a == 1 and b == 1 and c == 1, "one listener of each kind")
seat()
check(next(D.catchers) == nil, "no catcher without the module frame")
FS.GunsightWarrior.frame = MODULE
seat()
check(D.catchers.battle and D.catchers.demo, "both catchers once the module exists")
""")

case("a_catcher_casts_its_shout_by_name_with_no_alt_and_no_unit")(r"""
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
local b, d = D.catchers.battle, D.catchers.demo
check(b.attrs.type1 == "spell" and b.attrs.spell1 == "Battle Shout", "battle casts Battle Shout")
check(d.attrs.type1 == "spell" and d.attrs.spell1 == "Demoralizing Shout", "demo casts Demoralizing Shout")
for _, n in ipairs({ "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" }) do
    check(b.attrs[n] == "" and d.attrs[n] == "", n .. " is an empty type")
end
check(b.attrs.unit == nil and d.attrs.unit == nil, "no unit on a catcher")
check(b.clicks[1] == "AnyUp" and b.clicks[2] == "AnyDown", "AnyUp and AnyDown")
check(b.passThrough[1] == "RightButton" and b.passThrough[2] == "MiddleButton", "right and middle pass through")
""")

case("the_clients_own_spell_name_wins")(r"""
LOCAL_NAME = { battle = "Schlachtruf" }
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
check(D.catchers.battle.attrs.spell1 == "Schlachtruf", "the localized name")
check(D.catchers.demo.attrs.spell1 == "Demoralizing Shout", "the English name when none was read")
""")

case("the_holder_is_the_unit_watch_and_is_never_shown_or_hidden")(r"""
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
check(#WATCHED == 1, "one unit watch")
local h = WATCHED[1]
check(h.template == "SecureUnitButtonTemplate" and h.attrs.unit == "target" and h.parent == ROOT and h.mouse == false, "the holder")
check(h.level > MODULE.level, "above the module")
for _, b in pairs(D.catchers) do check(b.parent == h and b.template == "SecureActionButtonTemplate" and b.level > h.level, "catcher") end
for i = 1, 3 do seat(); areaChanged(); activeChanged(); learn() end
check(h.writes.Show == nil and h.writes.Hide == nil, "shown or hidden by us")
check(#WATCHED == 1, "the watch was registered again")
""")

case("an_unknown_shout_has_no_catcher_until_it_is_learned")(r"""
KNOWN.demo = false
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
check(D.catchers.battle and D.catchers.demo == nil, "only the known shout")
KNOWN.demo = true
learn()
check(D.catchers.demo and D.catchers.demo.mouse == true, "built on learn")
checkSeat(D, "demo", OX, OY, "late")
""")

case("the_mouse_follows_the_area_and_the_switch")(r"""
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
check(D.catchers.battle.mouse and D.catchers.demo.mouse, "on")
AREA = nil; areaChanged()
check(not D.catchers.battle.mouse and not D.catchers.demo.mouse, "off out of the area")
AREA = "lower"; areaChanged()
check(D.catchers.battle.mouse, "back on")
ACTIVE = false; activeChanged()
check(not D.catchers.battle.mouse, "off with the Gunsight off")
""")

case("the_catchers_cover_the_helms_and_follow_the_module_and_a_rescale")(r"""
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
checkSeat(D, "battle", OX, OY, "battle"); checkSeat(D, "demo", OX, OY, "demo")
local a, b = D.catchers.battle, D.catchers.demo
check(a.points[1][4] + a.w <= b.points[1][4], "the two helms do not overlap")
local before = WRITES
for i = 1, 4 do areaChanged(); activeChanged(); seat() end
check(WRITES == before, "an unchanged sync wrote " .. (WRITES - before))
OX, OY = 60, 170; SCALE = 0.8
seat()
checkSeat(D, "battle", 60, 170, "moved"); checkSeat(D, "demo", 60, 170, "moved")
""")

case("nothing_secure_is_written_in_combat_and_the_regen_replays_it")(r"""
KNOWN.demo = false
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
COMBAT = true
local before = WRITES
AREA = nil; areaChanged()
OX, OY = 40, 90; SCALE = 0.7; seat()
KNOWN.demo = true; learn()
check(#BLOCKED == 0, "a secure write in combat: " .. tostring(BLOCKED[1]))
check(WRITES == before, "written in combat")
check(D.catchers.demo == nil, "no frame built in combat")
COMBAT = false; AREA = "upper"
fire("PLAYER_REGEN_ENABLED")
check(#BLOCKED == 0)
check(D.catchers.demo and D.catchers.demo.mouse, "built at regen")
checkSeat(D, "battle", 40, 90, "regen")
""")

case("without_a_unit_watch_the_catchers_stay_off_and_say_so")(r"""
RegisterUnitWatch = nil
FS.GunsightWarrior.frame = MODULE
local D = load()
seat()
check(next(D.catchers) == nil, "no catcher without a unit watch")
check(DEGRADED.gunsightwarriorclick_nounitwatch == 1)
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        d = toc.index("Modules/CombatHud/GunsightWarriorClick.lua")
        for dep in ("Modules/CombatHud/GunsightWarrior.lua", "Modules/CombatHud/WarriorShouts.lua", "Modules/CombatHud/GunsightAreas.lua"):
            out.append((f"toc_loads_the_click_catchers_after_{Path(dep).stem.lower()}",
                        None if toc.index(dep) < d else f"GunsightWarriorClick.lua must load after {dep}"))
    except ValueError as e:
        out.append(("toc_lists_the_click_catchers", f"{e}"))
    src = CLICK.read_text(encoding="utf-8") if CLICK.exists() else ""
    code = re.sub(r"--.*", "", src)
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "an em or en dash"))
    out.append(("no_state_driver_snippet_or_execute",
                None if not re.search(r"RegisterStateDriver|RegisterAttributeDriver|SecureHandler|WrapScript|:Execute\(|SetFrameRef|_onstate", code)
                else "state drivers and secure snippets do not run on this client"))
    out.append(("no_unit_attribute_on_a_catcher",
                None if len(re.findall(r'SetAttribute\("unit"', code)) == 1 else "only the holder carries a unit"))
    out.append(("never_shows_or_hides_a_secure_frame",
                None if not re.search(r":\s*(Show|Hide)\s*\(", code) else "never call Show or Hide"))
    warrior = WARRIOR.read_text(encoding="utf-8")
    bad = []
    for k, v in {"SPX": "1.25", "CY": "35", "HELM_W": "32", "HELM_H": "32", "HELM_OX": "3"}.items():
        m = re.search(rf"\b{k} = ([\d.]+)", warrior)
        if not m or m.group(1) != v:
            bad.append(f"{k}: harness {v}, module {m.group(1) if m else 'missing'}")
    for key, cx in (("battle", "42"), ("demo", "112")):
        if not re.search(rf"{key} = {{ cx = {cx},", warrior):
            bad.append(f"{key} cx changed")
    out.append(("fake_module_constants_match_gunsightwarrior", None if not bad else "; ".join(bad)))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().CLICK_SRC = CLICK.read_text(encoding="utf-8")
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

    if not CLICK.exists():
        print(f"FAIL  {CLICK.name} is missing")
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
