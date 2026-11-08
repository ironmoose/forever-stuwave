#!/usr/bin/env python3
"""Runs the real GunsightMageClick.lua (click the Mage's ward to cast it) headless.

A left click on the ward casts Ice Barrier when the Mage knows it, else Mana Shield (the pick MageState's WardKind makes), in and
out of combat. The catcher is a secure action button OUTSIDE the Gunsight host tree (hung from Gunsight.root through a unit
watched holder), as GunsightPriestClick.lua's is. Both wards are self spells, so the button carries unit = "player" and needs no
remap. The mock is strict about combat: every write to a secure frame raises in combat. Pinned here:

  * nothing is built until the module exists and has been seated; the catcher exists only once a ward is known;
  * the attributes: unit = "player", type1 / spell1 the ward by name (Ice Barrier first), every Alt form an empty type;
  * resolved the way SecureTemplates.lua (12.1 FrameXML) resolves a click: any target (or none) casts on the player, an Alt click
    does nothing, a right click does nothing; and a target switch needs no attribute write;
  * the ward changing (Ice Barrier learned while Mana Shield was the ward) rewrites spell1, out of combat only;
  * the holder is the client's unit watch (unit = "target"), never shown or hidden by us;
  * the mouse is on only while the class module is in an area, the Gunsight is the display and a ward is known;
  * position and size cover the ward oval and its buff ring, follow the module and a rescale, and are not rewritten when nothing
    moved;
  * in combat nothing secure is written; PLAYER_REGEN_ENABLED replays it.

The mock is strict. It is NOT the real client.

    python3 tools/gunsightmageclick-harness.py

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

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
CLICK = ADDON / "Modules/CombatHud/GunsightMageClick.lua"
MAGE = ADDON / "Modules/CombatHud/GunsightMage.lua"
TOC = ADDON / "forever-stuwave.toc"

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg, eps)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < (eps or 1e-6),
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end

COMBAT = false
BLOCKED = {}
WRITES = 0
DEGRADED = {}
function InCombatLockdown() return COMBAT end

FRAMES = {}
local FrameMT = {}
FrameMT.__index = FrameMT
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
function FrameMT:SetAttribute(k, v) guard(self, "SetAttribute"); self.attrs[k] = v end
function FrameMT:GetAttribute(k) return self.attrs[k] end
function FrameMT:Show() guard(self, "Show"); self.shown = true end
function FrameMT:Hide() guard(self, "Hide"); self.shown = false end
function FrameMT:RegisterForClicks(...) self.clicks = { ... } end
function FrameMT:RegisterEvent(e) self.events[e] = true end
function FrameMT:SetScript(n, fn) self.scripts[n] = fn end
function FrameMT:SetPassThroughButtons(...) self.passThrough = { ... } end
function FrameMT:ShouldButtonPassThrough(b)
    for _, x in ipairs(self.passThrough or {}) do if x == b then return true end end
    return false
end
function CreateFrame(kind, name, parent, template)
    local f = setmetatable({ kind = kind, name = name, parent = parent, template = template, attrs = {}, points = {}, events = {},
        scripts = {}, writes = {}, shown = true, level = (parent and parent.level or 0) + 1,
        secure = template ~= nil and template:find("Secure") ~= nil }, FrameMT)
    FRAMES[#FRAMES + 1] = f
    return f
end
function fire(event)
    for _, f in ipairs({ unpack(FRAMES) }) do
        if f.events[event] and f.scripts.OnEvent then f.scripts.OnEvent(f, event) end
    end
end
WATCHED = {}
function RegisterUnitWatch(f) WATCHED[#WATCHED + 1] = f end

-- SecureTemplates.lua (12.1 FrameXML), the parts a left click goes through: the modifier prefix, the button suffix, the
-- five-way attribute lookup, ATTRIBUTE_NOOP, and GetConvertedButtonUnitAndActionType's harmbutton / helpbutton remap.
MODS = ""                       -- "alt-", "shift-", ... held at click time
TARGET = nil                    -- "friend" | "hostile" | "neutral" | nil
local function lookup(frame, prefix, name, suffix)
    local a = frame.attrs
    return a[prefix .. name .. suffix] or a["*" .. name .. suffix] or a[prefix .. name .. "*"] or a["*" .. name .. "*"] or a[name]
end
local function suffixOf(button)
    if button == "LeftButton" then return "1" elseif button == "RightButton" then return "2" elseif button == "MiddleButton" then return "3" end
    return "-" .. button
end
local function modified(frame, name, button)
    local v = lookup(frame, MODS, name, suffixOf(button))
    if v == "" then v = nil end
    return v
end
function SecureClick(frame, button)
    local unit = modified(frame, "unit", button)
    if unit then
        local orig = button
        local canAttack = unit == "target" and TARGET == "hostile"
        local canAssist = unit == "player" or (unit == "target" and TARGET == "friend")
        if canAttack then button = modified(frame, "harmbutton", button) or button
        elseif canAssist then button = modified(frame, "helpbutton", button) or button end
        if button ~= orig then unit = modified(frame, "unit", button) end
    end
    local kind = modified(frame, "type", button)
    if kind ~= "spell" then return nil end
    return modified(frame, "spell", button), unit
end

GRID, CX, CY = 2, 100, 50
SCALE = 1
ROOT = CreateFrame("Frame", "ROOT")
ACTIVE, AREA = true, "upper"
local activeCbs, areaCbs, seatCbs, dataCbs = {}, {}, {}, {}
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
FS.GunsightMage = {
    C = { SPX = 1.25, WARD = { x = 121, y = 31 } },
    Origin = function() return OX, OY end,
    OnSeat = function(fn) seatCbs[#seatCbs + 1] = fn end,
}
KIND = "barrier"                -- "barrier" | "mana" | nil: which ward MageState says the Mage has
FS.MageState = {
    DEFS = { icebarrier = { name = "Ice Barrier" }, manashield = { name = "Mana Shield" } },
    WardKind = function() return KIND end,
    Subscribe = function(fn) dataCbs[#dataCbs + 1] = fn end,
}
function seat() for _, fn in ipairs(seatCbs) do fn(OX, OY) end end
function areaChanged() for _, fn in ipairs(areaCbs) do fn() end end
function activeChanged() for _, fn in ipairs(activeCbs) do fn(ACTIVE) end end
function learn() for _, fn in ipairs(dataCbs) do fn("learn") end end
function listenerCounts() return #seatCbs, #areaCbs, #activeCbs end
function load()
    local fn = assert(loadstring(CLICK_SRC, "@GunsightMageClick.lua"))
    fn("forever-stuwave", FS)
    return FS.GunsightMageClick
end
function checkSeat(D, ox, oy, what)
    local b = D.catcher
    check(b, what .. ": no catcher")
    local P = FS.GunsightMage.C
    local k = GRID * SCALE
    local x = ox + (P.WARD.x - 21) * P.SPX
    local y = oy + (P.WARD.y - 26) * P.SPX
    check(#b.points == 1, what .. ": " .. #b.points .. " anchor points")
    local p = b.points[1]
    check(p[1] == "TOPLEFT" and p[2] == ROOT and p[3] == "CENTER", what .. ": anchor")
    near(p[4], (x - CX) * k, what .. " x"); near(p[5], -(y - CY) * k, what .. " y")
    near(b.w, 42 * P.SPX * k, what .. " w"); near(b.h, 52 * P.SPX * k, what .. " h")
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
check(D.catcher == nil, "no catcher without the module frame")
FS.GunsightMage.frame = MODULE
seat()
check(D.catcher, "the catcher once the module exists")
""")

case("the_attributes_cast_the_ward_on_the_player_whatever_is_targeted")(r"""
FS.GunsightMage.frame = MODULE
local D = load()
seat()
local b = D.catcher
check(b.attrs.unit == "player" and b.attrs.type1 == "spell" and b.attrs.spell1 == "Ice Barrier", "the left click")
check(b.attrs.harmbutton1 == nil and b.attrs.helpbutton1 == nil, "no remap: the ward is a self spell")
for _, n in ipairs({ "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" }) do
    check(b.attrs[n] == "", n .. " is an empty type")
end
check(b.clicks[1] == "AnyUp" and b.clicks[2] == "AnyDown", "AnyUp and AnyDown")
check(b.passThrough[1] == "RightButton" and b.passThrough[2] == "MiddleButton", "right and middle pass through")
local before = WRITES
for _, t in ipairs({ "friend", "hostile", "neutral", false }) do
    TARGET = t or nil
    local spell, unit = SecureClick(b, "LeftButton")
    check(spell == "Ice Barrier" and unit == "player", tostring(t) .. ": cast on the player, got " .. tostring(unit))
end
MODS = "alt-"
check(SecureClick(b, "LeftButton") == nil, "an Alt click does nothing")
MODS = ""
check(SecureClick(b, "RightButton") == nil, "a right click casts nothing")
check(WRITES == before, "a target switch wrote an attribute")
""")

case("mana_shield_is_cast_without_ice_barrier_and_the_switch_rewrites_it_out_of_combat")(r"""
KIND = "mana"
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(D.catcher.attrs.spell1 == "Mana Shield", "Mana Shield alone: " .. tostring(D.catcher.attrs.spell1))
KIND = "barrier"
learn()
check(D.catcher.attrs.spell1 == "Ice Barrier", "Ice Barrier once it is learned")
COMBAT = true
KIND = "mana"
learn()
check(#BLOCKED == 0 and D.catcher.attrs.spell1 == "Ice Barrier", "nothing is written in combat")
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(D.catcher.attrs.spell1 == "Mana Shield", "and the regen replays it")
""")

case("the_clients_own_spell_name_wins")(r"""
FS.MageState.DEFS.icebarrier.localName = "Eisbarriere"
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(D.catcher.attrs.spell1 == "Eisbarriere")
""")

case("the_holder_is_the_unit_watch_and_is_never_shown_or_hidden")(r"""
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(#WATCHED == 1, "one unit watch")
local h = WATCHED[1]
check(h.template == "SecureUnitButtonTemplate" and h.attrs.unit == "target" and h.parent == ROOT and h.mouse == false, "the holder")
check(h.level > MODULE.level, "above the module")
check(D.catcher.parent == h and D.catcher.template == "SecureActionButtonTemplate" and D.catcher.level > h.level, "catcher")
for i = 1, 3 do seat(); areaChanged(); activeChanged(); learn() end
check(h.writes.Show == nil and h.writes.Hide == nil, "shown or hidden by us")
check(#WATCHED == 1, "the watch was registered again")
""")

case("no_ward_has_no_catcher_until_one_is_learned")(r"""
KIND = nil
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(D.catcher == nil, "no catcher before a ward is known")
KIND = "mana"
learn()
check(D.catcher and D.catcher.mouse == true, "built on learn")
checkSeat(D, OX, OY, "late")
KIND = nil
learn()
check(not D.catcher.mouse, "off again when no ward is known")
""")

case("the_mouse_follows_the_area_and_the_switch")(r"""
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(D.catcher.mouse, "on")
AREA = nil; areaChanged()
check(not D.catcher.mouse, "off out of the area")
AREA = "lower"; areaChanged()
check(D.catcher.mouse, "back on")
ACTIVE = false; activeChanged()
check(not D.catcher.mouse, "off with the Gunsight off")
""")

case("the_catcher_covers_the_ward_and_follows_the_module_and_a_rescale")(r"""
FS.GunsightMage.frame = MODULE
local D = load()
seat()
checkSeat(D, OX, OY, "first")
local before = WRITES
for i = 1, 4 do areaChanged(); activeChanged(); seat() end
check(WRITES == before, "an unchanged sync wrote " .. (WRITES - before))
OX, OY = 60, 170; SCALE = 0.8
seat()
checkSeat(D, 60, 170, "moved")
""")

case("nothing_secure_is_written_in_combat_and_the_regen_replays_it")(r"""
KIND = nil
FS.GunsightMage.frame = MODULE
local D = load()
seat()
COMBAT = true
local before = WRITES
OX, OY = 40, 90; SCALE = 0.7; seat()
KIND = "barrier"; learn()
areaChanged()
check(#BLOCKED == 0, "a secure write in combat: " .. tostring(BLOCKED[1]))
check(WRITES == before, "written in combat")
check(D.catcher == nil, "no frame built in combat")
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(#BLOCKED == 0)
check(D.catcher and D.catcher.mouse, "built at regen")
checkSeat(D, 40, 90, "regen")
""")

case("without_a_unit_watch_the_catcher_stays_off_and_says_so")(r"""
RegisterUnitWatch = nil
FS.GunsightMage.frame = MODULE
local D = load()
seat()
check(D.catcher == nil, "no catcher without a unit watch")
check(DEGRADED.gunsightmageclick_nounitwatch == 1)
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        d = toc.index("Modules/CombatHud/GunsightMageClick.lua")
        for dep in ("Modules/CombatHud/GunsightMage.lua", "Modules/CombatHud/MageState.lua", "Modules/CombatHud/GunsightAreas.lua"):
            out.append((f"toc_loads_the_click_catcher_after_{Path(dep).stem.lower()}",
                        None if toc.index(dep) < d else f"GunsightMageClick.lua must load after {dep}"))
    except ValueError as e:
        out.append(("toc_lists_the_click_catcher", f"{e}"))
    src = CLICK.read_text(encoding="utf-8")
    code = re.sub(r"--.*", "", src)
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "an em or en dash"))
    out.append(("no_state_driver_snippet_or_execute",
                None if not re.search(r"RegisterStateDriver|RegisterAttributeDriver|SecureHandler|WrapScript|:Execute\(|SetFrameRef|_onstate", code)
                else "state drivers and secure snippets do not run on this client"))
    out.append(("never_shows_or_hides_a_secure_frame",
                None if not re.search(r":\s*(Show|Hide)\s*\(", code) else "never call Show or Hide"))
    out.append(("no_flagged_wording", None if not re.search(r"\b(bots?|automat\w*)\b", src, re.I) else "flagged wording"))
    mage = MAGE.read_text(encoding="utf-8")
    bad = []
    if not re.search(r"\bSPX = 1\.25,", mage):
        bad.append("SPX")
    if not re.search(r"WARD = \{ x = 121, y = 31 \}", mage):
        bad.append("WARD")
    out.append(("fake_module_constants_match_gunsightmage", None if not bad else "changed: " + ", ".join(bad)))
    return out


def run_case(body: str) -> str | None:
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

    for name, body in CASES:
        report(name, run_case(body))
    statics = static_checks()
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
