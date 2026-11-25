#!/usr/bin/env python3
"""Checks for the Class modules page (ticket C4): the page's rows, the keys they write and the code each key reaches.

Two halves.

  * THE PAGE. The real ConfigPageClassModules.lua runs inside the config window harness's mock with the real class module
    files that publish settings (PriestRight, WarlockState, DruidClearcasting, WarriorPowerUps, HunterState). Checked: the tab
    strip (General, then the nine classes in the Addon tabs order), every row of the prototype's Class modules page is
    registered with its key, kind and section (the prototype source is read from the mockups folder), the plate switches and
    sliders write their keys and dim Opacity when there is nothing to scale, the Priest picker with its one line note and the
    Pulse row that follows it, the Warlock cues and the Warrior master with its sub rows, the empty classes and Shaman say so,
    and no section folds on this page.
  * THE CODE BEHIND IT. The alert scale (`gunsight.classModule.alertScale`, read through `Areas.AlertScale()`) reaches both
    pop up alerts that own a frame, the Warrior power-ups and the Druid Clearcasting alert: at 100 percent every texture sits
    exactly where it did, at another value every texture is scaled about the middle of the alert's canvas, live, in the
    layout editor's preview, and again after a rescale. The plate switches, the opacity and the Areas side of the alert scale
    are pinned in gunsightareas-harness.py, the Priest labels in gunsightpriest-harness.py, the Warlock cues in
    gunsightwarlock-harness.py.

    python3 tools/classmodules-harness.py

Exit 0 = every check passed. Everything the page draws is pending owner review: this proves rows and wiring, not looks.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
CH = ADDON / "Modules/CombatHud"
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))
PAGE = ADDON / "Modules/Config/ConfigPageClassModules.lua"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = _load("configwindow-harness")
WP = _load("warriorpowerups-harness")
DC = _load("druidclearcasting-harness")
LuaError = base.LuaError

MODULES = ["PriestRight", "WarlockState", "DruidClearcasting", "WarriorPowerUps", "HunterState"]

# ---- the page -------------------------------------------------------------------------------------------------------

PAGE_CHECKS = r"""
local function cboot(opts)
    opts = opts or {}
    opts.preWindow = function()
        if opts.lite then return end          -- no class module file loaded: a tab leaves out what it cannot read
        for _, name in ipairs(__moduleNames) do
            assert(load(__modSrc[name], "@" .. name .. ".lua"))("forever-stuwave", FS)
        end
    end
    return boot(opts)
end

local TABS = "general,druid,hunter,mage,paladin,priest,rogue,shaman,warlock,warrior"

local function classmod(W)
    for _, c in ipairs(W.Categories()) do if c.key == "classmod" then return c end end
end

local function entriesOf(W, tab)
    W.Open("classmod", tab)
    local list = {}
    for _, e in ipairs(W.Rows()) do
        if e.page == "classmod" and e.tab == tab then list[#list + 1] = e end
    end
    return list
end

-- section | label | key | kind, one per row, in build order
local function shape(W, tab)
    local out = {}
    for _, e in ipairs(entriesOf(W, tab)) do
        out[#out + 1] = table.concat({ tostring(e.section), tostring(e.label), tostring(e.key or ""), e.kind }, "|")
    end
    return out
end

local function sameList(got, want, what)
    local a, b = table.concat(got, "\n"), table.concat(want, "\n")
    if a ~= b then error(what .. ":\n--- got\n" .. a .. "\n--- want\n" .. b, 2) end
end

local function sectionTip(title)
    for _, o in ipairs(ALL) do
        if o.fsSection and o.fsSection.title == title then
            for _, c in ipairs(ALL) do if c.fsTip and c.parent == o then return c.fsTip end end
        end
    end
end

local function entry(W, tab, label)
    for _, e in ipairs(entriesOf(W, tab)) do if e.label == label then return e end end
    error("no row '" .. label .. "' on the " .. tab .. " tab", 2)
end

local function visibleText(needle)
    return findText(needle, nil, true) ~= nil
end

function T.the_page_has_a_general_tab_then_the_nine_classes_in_the_addon_tabs_order()
    local W = cboot()
    local cat = classmod(W)
    yes(cat, "the page is registered")
    eq(cat.group, "SCREEN")
    eq(keys(cat.tabs), TABS)
    local labels = {}
    for _, t in ipairs(cat.tabs) do labels[#labels + 1] = t.label end
    eq(table.concat(labels, ","), "General,Druid,Hunter,Mage,Paladin,Priest,Rogue,Shaman,Warlock,Warrior")
end

function T.the_general_tab_has_the_plate_switches_the_opacity_and_the_alert_scale()
    local W = cboot()
    sameList(shape(W, "general"), {
        "Module plate|Background|gunsight.classModule.bg|switch",
        "Module plate|Border|gunsight.classModule.border|switch",
        "Module plate|Opacity|gunsight.classModule.background|slider",
        "Alerts|Alert scale|gunsight.classModule.alertScale|slider",
    }, "the General tab")
    eq(sectionTip("Module plate"), "The panel the class module sits on, in the Gunsight under your target.")
    yes(sectionTip("Alerts") and sectionTip("Alerts"):find("pop up alerts", 1, true), "the Alerts section explains itself")
    eq(entry(W, "general", "Background").tip, "The dark fill behind the module.")
    eq(entry(W, "general", "Border").tip, "The cyan outline and its glow.")
    local plate = entry(W, "general", "Opacity").tip
    yes(plate:find("plate", 1, true) and plate:find("0 hides both", 1, true), "the opacity tip says what 0 does: " .. plate)
    yes(entry(W, "general", "Alert scale").tip, "the alert scale has a tip")
end

function T.the_plate_defaults_are_the_look_of_today_and_pin_nothing()
    local W = cboot()
    entriesOf(W, "general")
    eq(FS.Config.Get("gunsight.classModule.bg"), true)
    eq(FS.Config.Get("gunsight.classModule.border"), true)
    eq(FS.Config.Get("gunsight.classModule.background"), 80)
    eq(FS.Config.Get("gunsight.classModule.alertScale"), 100)
    for _, k in ipairs({ "bg", "border", "background", "alertScale" }) do
        no(FS.Config.IsStored("gunsight.classModule." .. k), k .. " pins nothing")
    end
    eq(sliderRow("Opacity").fsReadout:GetText(), "80%")
    eq(sliderRow("Alert scale").fsReadout:GetText(), "100%")
end

function T.the_plate_switches_write_their_keys_and_back()
    local W = cboot()
    W.Open("classmod", "general")
    yes(press("Background")); eq(FS.Config.Get("gunsight.classModule.bg"), false)
    yes(press("Background")); eq(FS.Config.Get("gunsight.classModule.bg"), true)
    yes(press("Border")); eq(FS.Config.Get("gunsight.classModule.border"), false)
    yes(press("Border")); eq(FS.Config.Get("gunsight.classModule.border"), true)
    eq(#BLOCKED, 0)
end

function T.the_two_sliders_run_their_ranges_in_steps_of_five()
    local W = cboot()
    W.Open("classmod", "general")
    local opacity, scale = sliderRow("Opacity").control, sliderRow("Alert scale").control
    clickTrack(opacity, 1); eq(FS.Config.Get("gunsight.classModule.background"), 100)
    clickTrack(opacity, 0); eq(FS.Config.Get("gunsight.classModule.background"), 0)
    clickTrack(scale, 1); eq(FS.Config.Get("gunsight.classModule.alertScale"), 200)
    clickTrack(scale, 0); eq(FS.Config.Get("gunsight.classModule.alertScale"), 50)
    clickTrack(scale, 0.5); eq(FS.Config.Get("gunsight.classModule.alertScale") % 5, 0)
    yes(FS.Config.Get("gunsight.classModule.alertScale") >= 120 and FS.Config.Get("gunsight.classModule.alertScale") <= 130)
    eq(sliderRow("Alert scale").fsReadout:GetText(), FS.Config.Get("gunsight.classModule.alertScale") .. "%")
end

function T.opacity_dims_while_both_the_background_and_the_border_are_off()
    local W = cboot()
    W.Open("classmod", "general")
    local r = sliderRow("Opacity")
    no(r.fsRowOff, "on while a part is on")
    press("Background")
    no(r.fsRowOff, "still on: the border is")
    press("Border")
    yes(r.fsRowOff, "both off: nothing to scale")
    local tip = tipOf(r)
    yes(tip and tip:find("Background", 1, true) and tip:find("Border", 1, true), "the tip says what it needs: " .. tostring(tip))
    press("Background")
    no(r.fsRowOff, "the background is back")
    -- the alert scale never depends on the plate
    press("Background"); eq(sliderRow("Alert scale").fsRowOff, nil)
end

function T.the_druid_tab_has_the_clearcasting_switch()
    local W = cboot()
    sameList(shape(W, "druid"), { "Druid alerts|Clearcasting alert|gunsight.druid.clearcasting|switch" }, "the Druid tab")
    eq(FS.Config.Get("gunsight.druid.clearcasting"), true)
    yes(press("Clearcasting alert")); eq(FS.Config.Get("gunsight.druid.clearcasting"), false)
end

function T.the_hunter_tab_has_the_low_ammo_warning_slider()
    local W = cboot()
    sameList(shape(W, "hunter"), { "Hunter class module|Low ammo warning below|gunsight.hunter.ammowarn|slider" }, "the Hunter tab")
    local r = sliderRow("Low ammo warning below")
    eq(FS.Config.Get("gunsight.hunter.ammowarn"), 60)
    eq(r.fsReadout:GetText(), "60")
    local def = entry(W, "hunter", "Low ammo warning below")
    eq(def.min, 0); eq(def.max, 400)
    clickTrack(r.control, 1); eq(FS.Config.Get("gunsight.hunter.ammowarn"), 400)
    clickTrack(r.control, 0); eq(FS.Config.Get("gunsight.hunter.ammowarn"), 0)
    clickTrack(r.control, 0.5); eq(FS.Config.Get("gunsight.hunter.ammowarn") % 10, 0, "steps of 10")
    yes(tipOf(r):find("arrows or bullets", 1, true), "the tip says what it counts")
    yes(sectionTip("Hunter class module"), "the section keeps the module's own ? tip")
end

function T.mage_paladin_and_rogue_say_they_have_nothing_to_set()
    local W = cboot()
    for _, name in ipairs({ "Mage", "Paladin", "Rogue" }) do
        local tab = name:lower()
        sameList(shape(W, tab), { name .. "|The " .. name .. " module has nothing to set yet.||note" }, "the " .. name .. " tab")
        yes(visibleText("The " .. name .. " module has nothing to set yet."), name .. ": the note shows")
    end
end

function T.shaman_says_nothing_to_set_and_keeps_the_modules_tip()
    local W = cboot()
    sameList(shape(W, "shaman"), { "Shaman class module|Nothing to set. Hover the ? for what it shows.||note" }, "the Shaman tab")
    yes(sectionTip("Shaman class module"), "the section has the module's ? tip")
    yes(visibleText("Nothing to set. Hover the ? for what it shows."))
end

local PRIEST_AUTO = "Auto: Spirit Tap and Inner Fire when you play solo or in a small group, Prayer of Mending in a dungeon or raid once you know it."
local PRIEST_SPIRIT = "Two medallions: Spirit Tap time left on top, Inner Fire charges below."
local PRIEST_POM = "Heals left on the beads, and which party member holds it."

function T.the_priest_tab_names_its_two_halves_and_picks_what_sits_beside_the_shield()
    local W = cboot()
    sameList(shape(W, "priest"), {
        "Left: Power Word: Shield|Always shown once you know the spell. Nothing to set.||note",
        "Right: what sits beside the shield|Show|gunsight.priest.rightside|segmented",
        "Right: what sits beside the shield|" .. PRIEST_AUTO .. "||note",
        "Right: what sits beside the shield|" .. PRIEST_SPIRIT .. "||note",
        "Right: what sits beside the shield|" .. PRIEST_POM .. "||note",
        "Right: what sits beside the shield|Pulse Inner Fire when it is missing|gunsight.priest.firenudge|switch",
    }, "the Priest tab")
    eq(sectionTip("Left: Power Word: Shield"),
        "The round shield on the left fills with light while your shield holds. The rim turns violet during Weakened Soul.")
    eq(sectionTip("Right: what sits beside the shield"), "Pick one. A change made in a fight applies when the fight ends.")
    for _, label in ipairs({ "Auto", "Spirit Tap and Inner Fire", "Prayer of Mending", "Nothing" }) do
        yes(findText(label, row("Show")), "a button reads " .. label)
    end
    no(visibleText("Right side shows"), "the old label is gone")
    no(visibleText("Spirit Tap + Inner Fire"), "no plus sign")
end

function T.the_priest_picker_writes_the_stored_values_and_one_note_follows_the_pick()
    local W = cboot()
    W.Open("classmod", "priest")
    local key = "gunsight.priest.rightside"
    local pulse = "Pulse Inner Fire when it is missing"
    local function notes()
        local shown = {}
        for _, t in ipairs({ PRIEST_AUTO, PRIEST_SPIRIT, PRIEST_POM }) do if visibleText(t) then shown[#shown + 1] = t end end
        return shown
    end
    eq(FS.Config.Get(key), "auto"); no(FS.Config.IsStored(key))
    eq(#notes(), 1); eq(notes()[1], PRIEST_AUTO); yes(row(pulse), "Auto shows the pulse row")
    click("Spirit Tap and Inner Fire", row("Show")); eq(FS.Config.Get(key), "spirit")
    eq(#notes(), 1); eq(notes()[1], PRIEST_SPIRIT); yes(row(pulse), "the medallions show the pulse row")
    click("Prayer of Mending", row("Show")); eq(FS.Config.Get(key), "pom")
    eq(#notes(), 1); eq(notes()[1], PRIEST_POM); no(row(pulse), "Prayer of Mending has no Inner Fire to pulse")
    click("Nothing", row("Show")); eq(FS.Config.Get(key), "off")
    eq(#notes(), 0, "Nothing has no note line"); no(row(pulse), "and no pulse row")
    click("Auto", row("Show")); eq(FS.Config.Get(key), "auto")
    eq(notes()[1], PRIEST_AUTO); yes(row(pulse))
    yes(press(pulse)); eq(FS.Config.Get("gunsight.priest.firenudge"), false)
    eq(#BLOCKED, 0)
end

function T.the_warlock_tab_has_one_switch_per_cue()
    local W = cboot()
    sameList(shape(W, "warlock"), {
        "Warlock class module|Demon cue|gunsight.warlock.cue.summon|switch",
        "Warlock class module|Proc cues|gunsight.warlock.cue.procs|switch",
        "Warlock class module|Life Tap cue|gunsight.warlock.cue.tap|switch",
        "Warlock class module|Drain Soul cue|gunsight.warlock.cue.drain|switch",
    }, "the Warlock tab")
    for _, k in ipairs({ "summon", "procs", "tap", "drain" }) do
        eq(FS.Config.Get("gunsight.warlock.cue." .. k), true, k .. " is on by default")
        no(FS.Config.IsStored("gunsight.warlock.cue." .. k))
    end
    yes(entry(W, "warlock", "Life Tap cue").tip:find("TAP", 1, true), "the tap tip names the cue")
    yes(entry(W, "warlock", "Drain Soul cue").tip:find("DRAIN", 1, true), "the drain tip names the cue")
    yes(press("Life Tap cue")); eq(FS.Config.Get("gunsight.warlock.cue.tap"), false)
    eq(FS.Config.Get("gunsight.warlock.cue.drain"), true, "one cue's switch leaves the others")
    yes(press("Drain Soul cue")); eq(FS.Config.Get("gunsight.warlock.cue.drain"), false)
end

function T.the_warrior_tab_has_the_master_and_three_sub_rows_that_need_it()
    local W = cboot()
    sameList(shape(W, "warrior"), {
        "Warrior power-up alerts|Power-up alerts|gunsight.warrior.powerups|switch",
        "Warrior power-up alerts|Overpower|gunsight.warrior.powerup.overpower|switch",
        "Warrior power-up alerts|Revenge|gunsight.warrior.powerup.revenge|switch",
        "Warrior power-up alerts|Victory Rush|gunsight.warrior.powerup.victoryrush|switch",
    }, "the Warrior tab")
    for _, label in ipairs({ "Overpower", "Revenge", "Victory Rush" }) do
        local e = entry(W, "warrior", label)
        yes(e.sub, label .. " is a sub row"); eq(e.needs, "gunsight.warrior.powerups")
        no(row(label).fsRowOff, label .. " is on while the master is")
    end
    yes(press("Power-up alerts")); eq(FS.Config.Get("gunsight.warrior.powerups"), false)
    yes(row("Overpower").fsRowOff, "the sub rows dim with the master off")
    no(press("Overpower"), "and cannot be pressed")
    yes(press("Power-up alerts"))
    yes(press("Revenge")); eq(FS.Config.Get("gunsight.warrior.powerup.revenge"), false)
end

function T.no_section_of_the_page_folds()
    local W = cboot()
    for _, t in ipairs(classmod(W).tabs) do W.Open("classmod", t.key) end
    local seen = 0
    for _, o in ipairs(ALL) do
        if o.fsSection and tostring(o.fsSection.id):sub(1, 9) == "classmod/" then
            seen = seen + 1
            no(o.fsSection.foldable, o.fsSection.title .. " never folds")
            no(o.fsSection.folded, o.fsSection.title .. " is open")
        end
    end
    eq(seen, 12, "the sections were counted")
end

function T.every_registered_key_is_the_real_modules_key()
    local W = cboot()
    W.Open("classmod", "general")
    local Areas = FS.GunsightAreas
    eq(Areas.SETTINGS.bg.key, "gunsight.classModule.bg")
    eq(Areas.SETTINGS.border.key, "gunsight.classModule.border")
    eq(Areas.SETTINGS.background.key, "gunsight.classModule.background")
    eq(Areas.SETTINGS.alertScale.key, "gunsight.classModule.alertScale")
    eq(Areas.ALERT_SCALE_KEY, Areas.SETTINGS.alertScale.key)
    eq(FS.PriestRight.SETTING.key, "gunsight.priest.rightside")
    eq(FS.PriestRight.REMIND.key, "gunsight.priest.firenudge")
    eq(FS.HunterState.SETTINGS.ammoWarn.key, "gunsight.hunter.ammowarn")
    eq(FS.DruidClearcasting.SETTING.key, "gunsight.druid.clearcasting")
    eq(FS.WarriorPowerUps.SETTING.key, "gunsight.warrior.powerups")
end

function T.opening_every_tab_forwards_no_error()
    local W = cboot()
    for _, t in ipairs(classmod(W).tabs) do W.Open("classmod", t.key) end
    eq(#__errors, 0, "errors were forwarded: " .. table.concat(__errors, "; "))
end

function T.a_tab_whose_module_is_absent_builds_without_error()
    local W = cboot({ lite = true })
    for _, t in ipairs(classmod(W).tabs) do W.Open("classmod", t.key) end
    eq(#__errors, 0, "errors were forwarded: " .. table.concat(__errors, "; "))
end

function T.zz_registered_keys()
    local W = cboot()
    for _, t in ipairs(classmod(W).tabs) do W.Open("classmod", t.key) end
    local keys, notes = {}, {}
    for _, e in ipairs(W.Rows()) do
        if e.page == "classmod" then
            if e.key then keys[#keys + 1] = e.key end
            if e.kind == "note" and e.label then notes[#notes + 1] = e.label end
        end
    end
    return { keys = keys, notes = notes }
end
"""

PAGE_NAMES: list[str] = []


def run_page_checks() -> int:
    global PAGE_NAMES
    PAGE_NAMES = [n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", PAGE_CHECKS, re.M) if not n.startswith("zz_")]
    base.CHECKS = base.CHECKS.replace("__checks = T", PAGE_CHECKS + "\n__checks = T")
    failed = 0
    for name in PAGE_NAMES:
        try:
            lua = new_page_runtime()
            lua.eval("__checks")[name]()
            leaked = list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:6])[:900]}")
    return failed


def new_page_runtime():
    lua = base.boot()
    lua.globals().__moduleNames = base.to_lua(lua, list(MODULES))
    srcs = {n: (CH / f"{n}.lua").read_text(encoding="utf-8") for n in MODULES}
    lua.globals().__modSrc = base.to_lua(lua, srcs)
    return lua


# ---- prototype coverage ---------------------------------------------------------------------------------------------

def proto_classmod_chunk() -> str | None:
    have = (ROOT / "mockups").exists() or os.environ.get("FS_MOCKUPS_DIR")
    if not have:
        return None
    src = (MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js").read_text(encoding="utf-8")
    start = src.index(" {key:'classmod'")
    end = src.index(" {key:'cast'", start)
    return src[start:end]


def check_every_prototype_row_is_registered() -> list[str]:
    chunk = proto_classmod_chunk()
    if chunk is None:
        print("      (no mockups/: the prototype coverage check is skipped)")
        return []
    problems = []
    wanted_keys = re.findall(r"\bk:'([a-zA-Z0-9_.]+)'", chunk)
    wanted_notes = re.findall(r"\{ty:'none',l:'((?:[^'\\]|\\.)*)'", chunk)
    if len(wanted_keys) < 15:
        problems.append(f"only {len(wanted_keys)} prototype keys parsed")
    lua = new_page_runtime()
    got = lua.eval("__checks")["zz_registered_keys"]()
    have_keys = {str(k) for k in got["keys"].values()}
    have_notes = {str(k) for k in got["notes"].values()}
    for key in wanted_keys:
        if key not in have_keys:
            problems.append(f"prototype key {key} has no registered row")
    for note in wanted_notes:
        text = note.replace("\\'", "'")
        if text not in have_notes:
            problems.append(f"prototype note not registered: {text[:60]}")
    for key in have_keys:
        if key not in wanted_keys:
            problems.append(f"registered key {key} is not in the prototype")
    return problems


def check_the_page_file_has_no_em_dash_or_tape() -> list[str]:
    text = PAGE.read_text(encoding="utf-8")
    problems = []
    if "\u2014" in text or "\u2013" in text:
        problems.append("an em or en dash")
    if re.search(r"\btape\b", text, re.I):
        problems.append("the word tape")
    return problems


# ---- the alert scale reaches the two alert frames -------------------------------------------------------------------

AREAS_STUB = r"""
KEY = "gunsight.classModule.alertScale"
__alertScale = 1
FS.GunsightAreas = { ALERT_SCALE_KEY = KEY, AlertScale = function() return __alertScale end }
function SetAlertScale(percent) __alertScale = percent / 100; FS.Config.Set(KEY, percent) end
local function near(a, b, msg)
    if math.abs(a - b) > 1e-6 then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 3) end
end
-- every texture of two dumps scaled about the middle of the canvas: size by s, position x' = c (1 - s) + s x
local function scaledAbout(a, b, s, cx, cy, what)
    assert(#a == #b and #a > 10, what .. ": the same textures show, " .. #a .. " vs " .. #b)
    for i = 1, #a do
        near(b[i].w, a[i].w * s, what .. " width " .. i)
        near(b[i].h, a[i].h * s, what .. " height " .. i)
        near(b[i].x, cx * (1 - s) + s * a[i].x, what .. " x " .. i)
        near(b[i].y, cy * (1 - s) + s * a[i].y, what .. " y " .. i)
    end
end
"""

# The 150 x 96 sprite canvas at 2.5 image px per sprite px, times the layout scale: the frame's own size.
CANVAS = "local CX, CY = 150 * 2.5 / 2 * (__scale or 1), 96 * 2.5 / 2 * (__scale or 1)"

ALERT_CASES = {
    "warrior": {
        "boot": 'Boot(); Glow("overpower", true); TickFor(1)',
        "run": WP,
        "sources": lambda: dict(WINDOWS_SRC=WP.WINDOWS, ART_SRC=WP.ART, MODULE_SRC=WP.MODULE),
    },
    "druid": {
        "boot": 'Boot(); Proc(15); TickFor(1)',
        "run": DC,
        "sources": lambda: dict(ART_SRC=DC.ART, MODULE_SRC=DC.MODULE),
    },
}


def run_alert(kind: str, body: str) -> str | None:
    spec = ALERT_CASES[kind]
    try:
        rt = WP.LuaRuntime(unpack_returned_tuples=False)
        for k, v in spec["sources"]().items():
            setattr(rt.globals(), k, v)
        rt.execute(spec["run"].MOCK)
        rt.execute("local function main()\n" + AREAS_STUB + "\n" + CANVAS + "\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def run_alert_dump(kind: str, areas: bool) -> str:
    """The textures of a playing alert as text, with or without the Areas module present."""
    spec = ALERT_CASES[kind]
    rt = WP.LuaRuntime(unpack_returned_tuples=False)
    for k, v in spec["sources"]().items():
        setattr(rt.globals(), k, v)
    rt.execute(spec["run"].MOCK)
    stub = AREAS_STUB if areas else "function SetAlertScale() end"
    return rt.execute(
        "local function main()\n" + stub + "\n" + spec["boot"] + "\n"
        "local out = {}\n"
        "for _, r in ipairs(Dump()) do out[#out + 1] = string.format('%.6f %.6f %.6f %.6f', r.x, r.y, r.w, r.h) end\n"
        "return table.concat(out, '\\n')\nend\nreturn main()")


def alert_cases(kind: str) -> list[tuple[str, str]]:
    boot = ALERT_CASES[kind]["boot"]
    return [
        (f"{kind}_alert_at_150_percent_grows_every_texture_about_the_middle_of_its_canvas", f"""
    {boot}
    local a = Dump()
    SetAlertScale(150)
    scaledAbout(a, Dump(), 1.5, CX, CY, "150 percent")
"""),
        (f"{kind}_alert_at_50_percent_shrinks_it_about_the_same_middle", f"""
    {boot}
    local a = Dump()
    SetAlertScale(50)
    scaledAbout(a, Dump(), 0.5, CX, CY, "50 percent")
    SetAlertScale(100)
    scaledAbout(a, Dump(), 1, CX, CY, "back to 100 percent")
"""),
        (f"{kind}_alert_at_200_percent_and_the_scale_applies_live_while_it_plays", f"""
    {boot}
    local a = Dump()
    SetAlertScale(200)
    scaledAbout(a, Dump(), 2, CX, CY, "200 percent")
    TickFor(0.5)
    assert(#Dump() > 10, "it keeps playing after the change")
    SetAlertScale(100)
    TickFor(0.2)
    assert(#Dump() > 10)
"""),
        (f"{kind}_alert_follows_a_layout_rescale_at_the_new_scale", f"""
    {boot}
    SetAlertScale(150)
    __scale = 0.5
    for _, fn in ipairs(__rescale) do fn() end
    local cx, cy = 150 * 2.5 / 2 * 0.5, 96 * 2.5 / 2 * 0.5
    local a = Dump()
    -- the same textures at scale 100 and the new layout scale
    SetAlertScale(100)
    local b = Dump()
    scaledAbout(b, a, 1.5, cx, cy, "rescaled, 150 percent")
"""),
        (f"{kind}_alert_scale_never_moves_or_resizes_the_frame_and_shows_nothing_when_idle", f"""
    Boot()
    local r = Root()
    local points, shown = r.np, r.shown
    SetAlertScale(175)
    assert(r.np == points, "the frame was not re-seated")
    assert(r.shown == shown and not Driving(), "nothing shows and nothing runs when no alert plays")
    assert(VisibleCount() == 0)
    assert(r.w == nil and r.h == nil, "the frame keeps its size")
"""),
        (f"{kind}_alert_scale_reaches_the_layout_editors_preview", """
    Boot()
    SetEdit(true)
    local a = Dump()
    assert(#a > 10, "the editor preview shows the alert")
    SetAlertScale(150)
    scaledAbout(a, Dump(), 1.5, CX, CY, "the preview at 150 percent")
    SetEdit(false)
"""),
        (f"{kind}_alert_reads_a_junk_scale_as_100_percent", f"""
    {boot}
    local a = Dump()
    for _, junk in ipairs({{ 0, -3, 1 / 0 }}) do
        __alertScale = junk
        FS.Config.Set(KEY, 100)
        scaledAbout(a, Dump(), 1, CX, CY, "junk " .. tostring(junk))
    end
    __alertScale = 0 / 0
    FS.Config.Set(KEY, 100)
    scaledAbout(a, Dump(), 1, CX, CY, "NaN")
    __alertScale = "big"
    FS.Config.Set(KEY, 100)
    scaledAbout(a, Dump(), 1, CX, CY, "a string")
"""),
        (f"{kind}_alert_without_the_areas_module_is_unscaled", f"""
    FS.GunsightAreas = nil
    {boot}
    local a = Dump()
    assert(#a > 10)
    FS.Config.Set(KEY, 150)
    scaledAbout(a, Dump(), 1, CX, CY, "no Areas, no scaling")
"""),
    ]


def check_alert_100_is_identical(kind: str) -> list[str]:
    without, with_areas = run_alert_dump(kind, False), run_alert_dump(kind, True)
    if len(without.splitlines()) < 10:
        return [f"{kind}: too few textures to compare ({len(without.splitlines())})"]
    if without != with_areas:
        a, b = without.splitlines(), with_areas.splitlines()
        first = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
        return [f"{kind}: 100 percent differs from no scaling at texture {first}: {a[first] if first is not None else '?'} vs "
                f"{b[first] if first is not None else '?'}"]
    return []


def check_modules_read_the_areas_scale_and_its_key() -> list[str]:
    problems = []
    for name in ("WarriorPowerUps.lua", "DruidClearcasting.lua"):
        text = (CH / name).read_text(encoding="utf-8")
        for needle in ("GunsightAreas", "AlertScale", "ALERT_SCALE_KEY"):
            if needle not in text:
                problems.append(f"{name} does not use {needle}")
    return problems


def main() -> int:
    failed = run_page_checks()
    total = len(PAGE_NAMES)
    py_checks = [
        ("every_prototype_row_is_registered", check_every_prototype_row_is_registered),
        ("the_page_file_has_no_em_dash_or_tape", check_the_page_file_has_no_em_dash_or_tape),
        ("modules_read_the_areas_scale_and_its_key", check_modules_read_the_areas_scale_and_its_key),
    ]
    for kind in ALERT_CASES:
        py_checks.append((f"{kind}_alert_at_100_percent_is_exactly_where_it_was", lambda k=kind: check_alert_100_is_identical(k)))
    for name, fn in py_checks:
        total += 1
        try:
            problems = fn()
        except Exception as err:  # noqa: BLE001 (report the failure, keep going)
            problems = [f"{type(err).__name__}: {err}"]
        if problems:
            failed += 1
            print(f"FAIL  {name}: {'; '.join(problems)[:700]}")
        else:
            print(f"ok    {name}")
    for kind in ALERT_CASES:
        for name, body in alert_cases(kind):
            total += 1
            err = run_alert(kind, body)
            if err is None:
                print(f"ok    {name}")
            else:
                failed += 1
                print(f"FAIL  {name}\n      " + " ".join(err.splitlines()[:4])[:600])
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
