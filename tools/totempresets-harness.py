#!/usr/bin/env python3
"""Runs the real TotemPresets.lua and TotemDial.lua (the Shaman totem presets: the dial cell on the totem tab) headless,
in totembar-harness's world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua,
PetActionBar.lua, PetDock.lua, ClassShoulder.lua, TotemPiece.lua, TotemBar.lua, the buff tab, the five second rule tab.

The look is concept C of mockups/totem-presets-2026-10-14.html. The numbers and states below are read from the mockup's
description in TotemDial.lua; the live unknowns (a secure cast sequence stepping totems, the sound kit names, the spell
id of a cast being plain) are modelled, never claimed. Checked:

  * the data: up to four presets per character saved under the character, names cleaned, a saved file sanitised on load,
    the NEW slot while there is room, a read-only Config or a missing database keeping the presets in memory;
  * switching: an element a preset leaves out keeps its pick, a pick is made only for a button that would change, right
    click and the wheel cycle (each its own setting) through the NEW slot, a switch in combat is queued and applies at
    regen, editing is shut in combat;
  * the step: the script behind the click (`/castsequence reset=combat/6 ...`, a plain cast for one totem, the locked
    totems left out), written out of combat only; the record the dial draws advances on a matching cast, counts a press
    on the event the game acts on, and starts over at combat end, after six seconds idle, and on every edit;
  * the face: arcs per totem tinted by element, the locked dashed arc, done and next looks, the digit and the "+", the
    name plate and the raised plate, the pending look and its marks, the applied flash, the cues and their off switches;
  * the tooltips, the editor card (rows, chooser, up and down, name, two step DELETE), the seats (the tab grows by one
    cell, the buff tab and the five second rule tab follow, the dial off puts them back), the state line and its guards;
  * nothing is secure that should not be: no attribute write in combat, no flagged wording.

The mock is strict and is NOT the real client. TOTEMPRESETS_LUA, TOTEMDIAL_LUA, TOTEMBAR_LUA, BINDINGS_XML and TOC_FILE
point the harness at mutant copies (a check must fail on a broken one).

    python3 tools/totempresets-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
PRESETS = Path(os.environ.get("TOTEMPRESETS_LUA", ADDON / "Modules/ActionBars/TotemPresets.lua"))
DIAL = Path(os.environ.get("TOTEMDIAL_LUA", ADDON / "Modules/ActionBars/TotemDial.lua"))
BINDINGS = Path(os.environ.get("BINDINGS_XML", ADDON / "Bindings.xml"))
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))
MOCKUP = HERE.parent / "mockups" / "totem-presets-2026-10-14.html"
THEME = ADDON / "Core/Theme.lua"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tbh = _load("totembar_harness", "totembar-harness.py")
bbh = _load("buffbar_harness", "buffbar-harness.py")
fsh = _load("fivesecond_harness", "fivesecond-harness.py")
csh = tbh.csh
sb = csh.sb
g = sb.g
approx = sb.approx
set_combat = sb.set_combat
blocked = sb.blocked
SCALES = csh.SCALES
GUID = tbh.GUID
TOTEMS = tbh.TOTEMS
IDS = tbh.TOTEM_IDS
BTN, GAP, PAD = 38.0, 4.8, 6.0


def _theme_colors() -> dict:
    src = THEME.read_text(encoding="utf-8")
    block = re.search(r"Theme\.COLOR_TOTEM = \{(.*?)\n\}", src, re.S).group(1)
    out = {}
    for name, a, b, c in re.findall(r"(\w+)\s*=\s*\{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", block):
        out[name] = (float(a), float(b), float(c))
    return out


ELEMENT_COLOR = _theme_colors()
CYAN = (0.133, 0.878, 1.0)
PINK = (1.0, 0.18, 0.592)
AMBER = (1.0, 0.7137, 0.2824)
MUTED = (0.6157, 0.5765, 0.7686)

# ---------------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------------

MOCKS = r"""
-- the editor card's EditBox
function __Region:SetAutoFocus() end
function __Region:SetMaxLetters(n) self._max = n end
function __Region:SetTextInsets() end
-- text width by length (5.4 px a character, the 9 px mono face) and the screen pixels a UI unit covers
function __Region:GetStringWidth() return #(self._text or "") * 5.4 end
-- the pixel model of the client (Blizzard_SharedXML/PixelUtil.lua): one UI unit is effective scale * physical height / 768
-- pixels. `__es` is that count when the effective scale __ees is 1 (the physical height __physH then follows from it); a
-- test of the real display sets __ees and __physH (effective scale 0.64, physical height 1440: 1 unit = 1.2 pixels).
__es = 1
__ees = 1
__physH = nil
PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / (__physH or 768 * __es) end }
function __Region:GetEffectiveScale() return __ees end
function __Region:SetEnabled(on) self._enabled = on ~= false end
function __Region:IsEnabled() return self._enabled ~= false end
function __Region:SetSnapToPixelGrid(on) self._snap = on end
function __Region:SetTexelSnappingBias(v) self._bias = v end
function __Region:ClearFocus() self._focus = false end
function __Region:SetFocus() self._focus = true end
-- the keys and the CVar the click path reads
__shift = false
function IsShiftKeyDown() return __shift end
__alt = false
function IsAltKeyDown() return __alt end
__cvars = { ActionButtonUseKeyDown = "0" }
C_CVar = C_CVar or {}
C_CVar.GetCVar = function(name) return __cvars[name] end
-- the sound kit: a client without these names plays nothing
SOUNDKIT = { IG_MAINMENU_OPTION_CHECKBOX_OFF = 856, IG_MAINMENU_OPTION_CHECKBOX_ON = 857, IG_ABILITY_ICON_DROP = 858 }
__sounds = {}
function PlaySound(id) __sounds[#__sounds + 1] = id end
UIErrorsFrame = { AddMessage = function(self, text) __errors = __errors or {}; __errors[#__errors + 1] = text end }
function __castOk(id) __fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
function GameTooltip:AddLine(t) self._lines = self._lines or {}; self._lines[#self._lines + 1] = t end
"""


def boot(scale: float = 1.0, *, learned=None, combat: bool = False, pre_login: str = "", console: bool = True,
         tabs: bool = False, klass: str = "SHAMAN", early: str = ""):
    """A Shaman world with every totem learned (or the `learned` names) and the preset files loaded last. `tabs`: the
    buff tab and the five second rule tab too (the seat checks)."""
    names = learned if learned is not None else [n for e in ("fire", "earth", "water", "air") for n in TOTEMS[e]]
    all_ids = "{" + ",".join(f'["{n}"]={i}' for n, i in IDS.items()) + "}"
    mocks = tbh.MOCKS % dict(guid=GUID, bar=tbh.BAR, all=all_ids)
    setup = ["__nativeFormula()"] + [f'__know("{n}")' for n in names]
    for element, slot in tbh.SLOT.items():
        setup.append(f"__mc_list({slot}, {{" + ",".join(f'"{n}"' for n in TOTEMS[element] if n in names) + "})")
    for name, sid in (("Call of the Elements", tbh.CALL), ("Call of the Ancestors", tbh.ANCESTORS),
                      ("Totemic Recall", tbh.RECALL)):
        setup.append(f'__spell("{name}", {sid}, true)')
    files = [csh.PETDOCK, csh.CLASSSHOULDER, tbh.TOTEMPIECE, tbh.TOTEMBAR]
    extra = mocks + "\n" + MOCKS + "\n" + "\n".join(setup) + "\n" + early
    if tabs:
        files += [bbh.SHAMANBUFFS, bbh.BUFFTAB]
        extra = mocks + "\n" + bbh.MOCKS + "\n" + fsh.MOCKS + "\n" + MOCKS + "\n" + "\n".join(setup) + "\n" + early
        files.append(fsh.FSTAB)
    files += [PRESETS, DIAL]
    return sb.boot(scale, klass=klass, known=[], combat=combat, console=console, extra_lua=csh.PATCH + extra,
                   extra_files=tuple(files), pre_login=csh.SPIES + pre_login)


def run(lua, code):
    lua.execute(code)


def ev(lua, expr):
    return lua.eval(expr)


def PS(lua):
    return g(lua).FS.TotemPresets


def DL(lua):
    return g(lua).FS.TotemDial


def TB(lua):
    return g(lua).FS.TotemBar


def seq(table) -> list:
    return csh.seq(table)


def dial(lua):
    return g(lua).FSTotemButton7


def btn(lua, key):
    return TB(lua).Button(key)


def shown(r) -> bool:
    return bool(r._shown)


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


def script(lua, frame, name, *args):
    lua.eval("__Region.Fire")(frame, name, *args)


def click(lua, b, button="LeftButton", down=False):
    script(lua, b, "OnClick", button, down)


def advance(lua, dt):
    lua.eval("__advance")(dt)


def tick(lua, dt=0.2):
    script(lua, g(lua).FSTotemDialTicker, "OnUpdate", dt)


def conf(lua, key, value):
    g(lua).FS.Config.Set(key, value)


def leave_combat(lua):
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")


def enter_combat(lua):
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")


def pick_of(lua, element):
    p = TB(lua).CurrentPick(element)
    return str(p.name) if p else None


def mk(lua, element, base_name) -> int:
    """The rank 1 id of a totem by name."""
    return IDS[base_name]


def make(lua, picks=None, order=None, name=None):
    """Creates a preset as a copy of the buttons, then edits it. picks: {element: totem name or None}."""
    index = PS(lua).Create()
    assert index, "Create refused"
    for element, tname in (picks or {}).items():
        ok = PS(lua).SetTotem(index, element, IDS[tname] if tname else None)
        assert ok is True or ok[0] is True, f"SetTotem {element} {tname}: {ok}"
    if order:
        preset = PS(lua).Get(index)
        cur = [str(e) for e in seq(preset.order)]
        assert sorted(cur) == sorted(order), f"order {cur} vs {order}"
        for target, element in enumerate(order, 1):
            while [str(e) for e in seq(PS(lua).Get(index).order)].index(element) + 1 > target:
                assert PS(lua).Move(index, element, -1)
    if name:
        assert PS(lua).Rename(index, name)
    return index


def order_of(lua, index) -> list:
    return [str(e) for e in seq(PS(lua).Get(index).order)]


def text_of(lua, index) -> str:
    return str(PS(lua).StepText(PS(lua).Get(index)))


def saved(lua):
    db = g(lua).ForeverSTUwaveDB
    return db.totemPresets[GUID] if db and db.totemPresets else None


def lines(lua) -> list:
    return [str(x) for x in seq(g(lua).GameTooltip._lines)]


def plain(s) -> str:
    return re.sub(r"\|T.*?\|t ", "", re.sub(r"\|r", "", re.sub(r"\|c[0-9a-fA-F]{8}", "", str(s))))


def hover(lua, b):
    b._mouseOver = True
    script(lua, b, "OnEnter")


def unhover(lua, b):
    b._mouseOver = False
    script(lua, b, "OnLeave")


def look(lua):
    DL(lua).Refresh()


def arcs(lua, key="dial"):
    """[(shown, texture, (r, g, b, a), core shown)] for the four arcs of a cell."""
    b = btn(lua, key)
    out = []
    for a in seq(b.fsArcs):
        v = a.main._vertex
        out.append((shown(a.main), str(a.main._texture) if a.main._texture else None,
                    tuple(float(x) for x in seq(v)) if v else None, shown(a.core)))
    return out


def kinds(lua, key="dial") -> list:
    """The look letter of each shown arc (t quiet, g done, k next, d locked) and its arc count."""
    out = []
    for sh, tex, _, _ in arcs(lua, key):
        if sh and tex:
            out.append(re.search(r"_n(\d)_(\d)_(\w)\.tga$", tex).groups())
    return out


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def rail(lua):
    return btn(lua, "dial").fsRail


def raise_plate(lua):
    return btn(lua, "dial").fsRaise


# ---------------------------------------------------------------------------------------------
# Checks: files, settings
# ---------------------------------------------------------------------------------------------


def check_toc_lists_the_preset_files_after_the_totem_bar_and_bindings_declare_the_dial():
    lines_ = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines_ if ln.endswith(".lua")]
    for f in ("Modules/ActionBars/TotemPresets.lua", "Modules/ActionBars/TotemDial.lua"):
        assert f in mods, f"{f} is not in the .toc"
    bar = mods.index("Modules/ActionBars/TotemBar.lua")
    assert bar < mods.index("Modules/ActionBars/TotemPresets.lua") < mods.index("Modules/ActionBars/TotemDial.lua")
    assert mods.index("Modules/ActionBars/TotemDial.lua") < mods.index("Modules/Config/ConfigWindow.lua")
    raw = TOC.read_bytes()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "the toc is not CRLF all through"
    names = [b.get("name") for b in ET.parse(BINDINGS).getroot().findall("Binding")]
    assert "CLICK FSTotemButton7:LeftButton" in names, names


def check_the_settings_have_their_keys_defaults_tips_and_registered_defaults():
    lua = boot()
    S = PS(lua).SETTINGS
    want = {
        "dial": ("totems.dial", True), "dialPlate": ("totems.dialPlate", True),
        "dialRight": ("totems.dialRight", True), "dialWheel": ("totems.dialWheel", True),
        "waitPulse": ("totems.waitPulse", True), "waitSound": ("totems.waitSound", False),
        "appliedFlash": ("totems.appliedFlash", True), "appliedSound": ("totems.appliedSound", False),
        "gnarly": ("totems.gnarly", True), "gnarlyFlash": ("totems.gnarlyFlash", True),
        "gnarlySound": ("totems.gnarlySound", False), "gnarlySet2": ("totems.gnarlySet2", True),
    }
    for name, (key, default) in want.items():
        assert str(S[name].key) == key and S[name].default is default, name
        assert str(S[name].label), name
        tip = str(S[name].tip)
        assert tip.endswith("."), f"{name}: tip {tip!r}"
        assert g(lua).FS.Config.Get(key) is default, f"{key} default"
    for cue in ("waitSound", "appliedSound", "waitPulse", "appliedFlash", "gnarlyFlash", "gnarlySound"):
        assert cue in want, cue      # each cue has its own off switch


def check_only_a_shaman_gets_a_dial_and_a_world_without_the_files_keeps_six_buttons():
    lua = boot(klass="PALADIN")
    assert PS(lua).Applies() is False
    lua = boot()
    assert PS(lua).Applies() is True
    # a world that loads TotemBar.lua alone: six buttons and 264 px
    lua = sb.boot(1.0, klass="SHAMAN", known=[], extra_lua=csh.PATCH + tbh.MOCKS % dict(guid=GUID, bar=tbh.BAR, all="{}"),
                  extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, tbh.TOTEMPIECE, tbh.TOTEMBAR), pre_login=csh.SPIES)
    assert TB(lua).Cols() == 6
    approx(float(g(lua).FSTotemBar._w), 264.0, "stock host width")
    assert g(lua).FSTotemButton7 is None


# ---------------------------------------------------------------------------------------------
# Checks: the data
# ---------------------------------------------------------------------------------------------


def check_no_presets_is_one_new_slot_and_create_copies_the_four_buttons():
    lua = boot()
    P = PS(lua)
    assert (P.Count(), P.SlotCount(), P.Active()) == (0, 1, 1) and P.IsNew(1) and P.ActivePreset() is None
    i = P.Create()
    assert i == 1 and P.Count() == 1 and P.Active() == 1
    p = P.Get(1)
    assert str(p.name) == "NEW"
    assert order_of(lua, 1) == ["earth", "fire", "water", "air"], "the default drop order"
    assert [int(p.picks[e]) for e in ("earth", "fire", "water", "air")] == [
        IDS["Stoneskin Totem"], IDS["Searing Totem"], IDS["Healing Stream Totem"], IDS["Grounding Totem"]]
    s = saved(lua)
    assert s is not None and int(s.active) == 1 and len(seq(s.list)) == 1, "saved under the character"
    # a pick that differs from the first one is what the copy carries
    TB(lua).Pick("fire", IDS["Magma Totem"])
    j = P.Create()
    assert int(P.Get(j).picks.fire) == IDS["Magma Totem"]
    assert P.SlotCount() == 3, "a NEW slot follows the two presets"


def check_four_presets_at_most_and_the_new_slot_goes_when_there_are_four():
    lua = boot()
    P = PS(lua)
    for n in range(4):
        assert P.Create() == n + 1
    assert P.Count() == 4 and P.SlotCount() == 4 and not P.IsNew(4)
    r = P.Create()
    assert not r or r[0] is None, "a fifth preset was made"
    assert P.Count() == 4
    P.Delete(2)
    assert P.Count() == 3 and P.SlotCount() == 4, "the NEW slot comes back"


def check_names_are_letters_digits_and_spaces_up_to_eight_uppercased():
    lua = boot()
    P = PS(lua)
    P.Create()
    for given, want in (("melee", "MELEE"), ("tank 2!!", "TANK 2"), ("abcdefghijkl", "ABCDEFGH"), ("  hi  ", "HI"),
                        ("a-b_c", "ABC")):
        assert P.Rename(1, given) is True
        assert str(P.Get(1).name) == want, f"{given!r} -> {P.Get(1).name!r}"
    ok = P.Rename(1, "!!!")
    assert ok[0] is False and str(P.Get(1).name) == "ABC", "an empty name is refused"


def check_a_saved_file_is_sanitised_when_it_loads():
    junk = (
        f'ForeverSTUwaveDB = {{ totemPresets = {{ [{GUID!r}] = {{ active = 9, gnarly = 7, list = {{'
        f' {{ name = "a very long name", picks = {{ earth = {IDS["Stoneskin Totem"]}, fire = 12345, water = "x" }},'
        f'   order = {{ "fire", "earth", "earth", "air" }} }},'
        f' "junk", {{ name = "", picks = {{ air = {IDS["Grounding Totem"]} }}, order = {{}} }},'
        f' {{ name = "D" }}, {{ name = "E" }}, {{ name = "F" }} }} }} }} }}')
    lua = boot(pre_login=junk)
    P = PS(lua)
    assert P.Count() == 4, f"count {P.Count()}"
    p = P.Get(1)
    assert str(p.name) == "A VERY L", p.name
    assert [str(e) for e in seq(p.order)] == ["earth"], "only elements that carry a known totem stay in the order"
    assert p.picks.fire is None and p.picks.water is None
    assert str(P.Get(2).name) == "NEW" and [str(e) for e in seq(P.Get(2).order)] == ["air"]
    assert P.Active() == 1 and P.Gnarly() is None, "an active slot out of range falls to 1, a gnarly past the list goes"


def check_presets_are_kept_per_character():
    lua = boot()
    PS(lua).Create()
    run(lua, 'ForeverSTUwaveDB.totemPresets["Player-9-OTHER"] = { list = { { name = "THEIRS", picks = {}, order = {} } }, active = 1 }')
    assert PS(lua).Count() == 1 and str(PS(lua).Get(1).name) == "NEW", "another character's presets leaked in"


def check_a_read_only_config_or_no_database_keeps_the_presets_in_memory_and_refuses_edits():
    lua = boot()
    run(lua, "ForeverSTUwaveDB.totemPresets = nil; FS.Config.IsReadOnly = function() return true end")
    P = PS(lua)
    assert P.Writable() is False
    r = P.Create()
    assert not r or r[0] is None, "an edit went through a store that cannot be saved"
    assert P.Count() == 0 and g(lua).ForeverSTUwaveDB.totemPresets is None, "the database was written"
    assert P.Select(1) in ("applied", "queued", False), "switching still answers"
    assert "cannot be saved this session" in str(P.Refusal()), "a read only config got another refusal text"
    lua = boot()
    run(lua, "ForeverSTUwaveDB = nil")
    P = PS(lua)
    assert P.Writable() is False and P.Count() == 0
    r = P.Create()
    assert not r or r[0] is None
    assert g(lua).ForeverSTUwaveDB is None, "a missing database was created"
    assert "cannot be saved this session" in str(P.Refusal()), "a missing database got another refusal text"
    run(lua, 'ForeverSTUwaveDB = "oops"')
    assert P.Writable() is False and P.Count() == 0 and g(lua).ForeverSTUwaveDB == "oops"
    assert "cannot be saved this session" in str(P.Refusal()), "a database that is not a table got another refusal text"


# ---------------------------------------------------------------------------------------------
# Checks: editing
# ---------------------------------------------------------------------------------------------


def check_filling_leaving_out_and_moving_a_preset():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    assert P.SetTotem(i, "water", None) is True
    assert order_of(lua, i) == ["earth", "fire", "air"] and P.Get(i).picks.water is None
    assert P.SetTotem(i, "water", IDS["Mana Spring Totem"]) is True
    assert order_of(lua, i) == ["earth", "fire", "air", "water"], "a new totem joins the end of the order"
    assert P.Move(i, "water", -1) is True and order_of(lua, i) == ["earth", "fire", "water", "air"]
    assert P.Move(i, "earth", -1)[0] is False and P.Move(i, "air", 1)[0] is False, "moving past an end is refused"
    assert P.SetTotem(i, "fire", 424242)[0] is False, "an id that is not a totem of the element is refused"
    assert P.SetTotem(i, "fire", IDS["Stoneskin Totem"])[0] is False, "a totem of another element is refused"
    assert P.SetTotem(9, "fire", IDS["Searing Totem"])[0] is False


def check_every_edit_is_refused_in_combat_and_the_editor_will_not_open():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    set_combat(lua, True)
    before = order_of(lua, i)
    for r in (P.Create(), P.Rename(i, "X"), P.SetTotem(i, "fire", IDS["Magma Totem"]), P.Move(i, "fire", 1), P.Delete(i)):
        assert not r or r is False or r[0] in (None, False), f"an edit went through in combat: {r}"
    assert P.Count() == 1 and order_of(lua, i) == before and str(P.Get(i).name) == "NEW"
    DL(lua).OpenEditor(i)
    assert DL(lua).Card() is None or not shown(DL(lua).Card()), "the editor opened in combat"
    set_combat(lua, False)
    DL(lua).OpenEditor(i)
    assert shown(DL(lua).Card())
    enter_combat(lua)
    assert not shown(DL(lua).Card()), "the editor stayed open when combat started"


def check_deleting_shifts_the_active_slot_and_clears_a_pending_switch():
    lua = boot()
    P = PS(lua)
    for _ in range(3):
        P.Create()
    P.Select(3)
    run(lua, "FS.TotemPresets.P.pending = 2")
    assert P.Delete(1) is True
    assert P.Count() == 2 and P.Active() == 2, f"active {P.Active()}"
    assert P.Pending() is None, "a pending switch survived a delete"
    P.Select(2)
    P.Delete(2)
    assert P.Active() <= P.SlotCount()


def check_editing_the_active_preset_picks_its_totems_on_the_buttons():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    P.SetTotem(i, "fire", IDS["Magma Totem"])
    assert pick_of(lua, "fire") == "Magma Totem", "the active preset did not reach the fire button"
    # an edit of a preset that is not the active one touches no button
    j = make(lua)
    P.Select(i)
    P.SetTotem(j, "fire", IDS["Searing Totem"])
    assert pick_of(lua, "fire") == "Magma Totem"


# ---------------------------------------------------------------------------------------------
# Checks: switching
# ---------------------------------------------------------------------------------------------


def two_presets(lua):
    a = make(lua, picks={"fire": "Searing Totem", "earth": "Stoneskin Totem", "water": "Healing Stream Totem",
                         "air": "Grounding Totem"}, name="MELEE")
    b = make(lua, picks={"fire": "Magma Totem", "earth": "Tremor Totem", "water": "Mana Spring Totem", "air": None},
             name="CASTER")
    return a, b


def check_an_element_a_preset_leaves_out_keeps_its_pick():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    assert pick_of(lua, "air") == "Grounding Totem"
    TB(lua).Pick("air", IDS["Nature Resistance Totem"])
    assert P.Select(b) == "applied"
    assert pick_of(lua, "air") == "Nature Resistance Totem", "a left out element lost its pick"
    assert (pick_of(lua, "fire"), pick_of(lua, "earth"), pick_of(lua, "water")) == ("Magma Totem", "Tremor Totem", "Mana Spring Totem")
    assert [str(e) for e in seq(P.P.applied.elements)] == ["fire", "earth", "water"] or sorted(
        str(e) for e in seq(P.P.applied.elements)) == ["earth", "fire", "water"]


def check_a_switch_picks_only_the_buttons_that_would_change():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    TB(lua).Pick("fire", IDS["Magma Totem"])
    run(lua, "__mc.calls = {}")
    assert sorted(str(e) for e in seq(P.WouldChange(b))) == ["earth", "water"], "fire already casts Magma"
    P.Select(b)
    elements = sorted(str(e) for e in seq(P.P.applied.elements))
    assert elements == ["earth", "water"], f"changed {elements}"
    assert len(seq(g(lua).__mc.calls)) == 2, f"{len(seq(g(lua).__mc.calls))} multi-cast writes for two changed buttons"
    # switching to what is already there changes nothing
    run(lua, "__mc.calls = {}")
    P.Select(a)
    run(lua, "__mc.calls = {}")
    P.Select(a)
    assert len(seq(P.P.applied.elements)) == 0 and len(seq(g(lua).__mc.calls)) == 0, "a switch to what is there wrote slots"


def check_a_totem_not_learned_yet_is_skipped_and_stays_locked():
    lua = boot(learned=[n for n in TOTEMS["earth"] + TOTEMS["fire"]])
    P = PS(lua)
    i = make(lua, picks={"water": "Healing Stream Totem", "air": "Grounding Totem"})
    e = P.Entry("water", IDS["Healing Stream Totem"])
    assert e.known is False and int(e.level) == 20, f"level {e.level}"
    assert P.Entry("air", IDS["Grounding Totem"]).known is False
    run(lua, "FS.TotemPresets.P.applied = nil")
    P.Select(i)
    changed = [str(x) for x in seq(P.P.applied.elements)] if P.P.applied else []
    assert "water" not in changed and "air" not in changed
    assert text_of(lua, i).count(",") == 1, text_of(lua, i)


def check_right_click_and_the_wheel_cycle_through_the_new_slot_each_on_its_own_setting():
    lua = boot()
    P = PS(lua)
    two_presets(lua)
    d = dial(lua)
    P.Select(1)
    assert P.SlotCount() == 3
    click(lua, d, "RightButton")
    assert P.Active() == 2
    click(lua, d, "RightButton")
    assert P.Active() == 3 and P.IsNew(3), "the NEW slot is part of the turn"
    click(lua, d, "RightButton")
    assert P.Active() == 1, "the turn wraps"
    script(lua, d, "OnMouseWheel", 1)
    assert P.Active() == 2
    script(lua, d, "OnMouseWheel", -1)
    assert P.Active() == 1
    script(lua, d, "OnMouseWheel", -1)
    assert P.Active() == 3, "the wheel turns back through the wrap"
    conf(lua, "totems.dialRight", False)
    P.Select(1)
    click(lua, d, "RightButton")
    assert P.Active() == 1, "right click turned the dial with its setting off"
    script(lua, d, "OnMouseWheel", 1)
    assert P.Active() == 2, "the wheel stopped with the right click setting"
    conf(lua, "totems.dialWheel", False)
    script(lua, d, "OnMouseWheel", 1)
    assert P.Active() == 2, "the wheel turned the dial with its setting off"
    # selecting the NEW slot changes no button
    conf(lua, "totems.dialWheel", True)
    before = (pick_of(lua, "fire"), pick_of(lua, "earth"))
    P.Select(3)
    assert (pick_of(lua, "fire"), pick_of(lua, "earth")) == before


def check_a_switch_in_combat_is_queued_and_applies_at_regen():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    run(lua, "__mc.calls = {}")
    set_combat(lua, True)
    n_blocked = blocked(lua)
    assert P.Select(b) == "queued"
    assert P.Active() == a and P.Pending() == b, "the switch did not wait"
    assert len(seq(g(lua).__mc.calls)) == 0, "the multi-cast slots were written in combat"
    assert blocked(lua) == n_blocked, "a protected write was tried in combat"
    assert pick_of(lua, "fire") == "Searing Totem"
    # cycling in combat moves the pending choice; choosing the active one cancels it
    P.Cycle(1)
    assert P.Pending() == 3, f"pending {P.Pending()}"
    P.Select(a)
    assert P.Pending() is None
    P.Select(b)
    leave_combat(lua)
    assert P.Pending() is None and P.Active() == b
    assert pick_of(lua, "fire") == "Magma Totem" and pick_of(lua, "earth") == "Tremor Totem"


def check_a_failing_preset_hook_never_stops_the_totem_tab_from_catching_up_at_regen():
    lua = boot()
    P = PS(lua)
    set_combat(lua, True)
    TB(lua).Pick("fire", IDS["Magma Totem"])
    assert pick_of(lua, "fire") != "Magma Totem", "the pick landed in combat"
    run(lua, "FS.TotemPresets.OnRegen = function() error('boom') end")
    leave_combat(lua)
    assert pick_of(lua, "fire") == "Magma Totem", "a failing OnRegen stopped the queued pick"


def check_a_slot_that_vanished_while_a_switch_waited_is_dropped_at_regen():
    lua = boot()
    P = PS(lua)
    two_presets(lua)
    set_combat(lua, True)
    P.Select(3)
    set_combat(lua, False)
    run(lua, "FS.TotemPresets.P.pending = 9")
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert P.Pending() is None


# ---------------------------------------------------------------------------------------------
# Checks: the step
# ---------------------------------------------------------------------------------------------


NUM_SECRET = (
    "local __o = FS.IsSecret; FS.IsSecret = function(v) return __o(v) or (__numSecret ~= nil and v == __numSecret) end\n"
)


def check_a_secret_number_from_the_wheel_or_the_clock_is_ignored():
    # the mock secret is a table, which the type tests would catch anyway: a secret NUMBER is what the guards are for
    lua = boot(early=NUM_SECRET)
    P = PS(lua)
    two_presets(lua)
    d = dial(lua)
    P.Select(1)
    run(lua, "__numSecret = 5")
    script(lua, d, "OnMouseWheel", 5)
    assert P.Active() == 1, "a secret wheel step turned the dial"
    script(lua, d, "OnMouseWheel", 1)
    assert P.Active() == 2, "a plain wheel step still turns it"
    run(lua, "__numSecret = nil; local get = GetTime; __getTime = get; GetTime = function() return 123.5 end; __numSecret = 123.5")
    click(lua, d)
    assert P.PressAge("dial") is None, "a secret clock was stored as a press time"
    run(lua, "__numSecret = nil")
    click(lua, d)
    assert P.PressAge("dial") == 0, "a plain clock stores the press"
    run(lua, "GetTime = __getTime")


def check_the_script_behind_the_click_is_a_cast_sequence_that_restarts_with_combat_and_idle():
    lua = boot()
    P = PS(lua)
    i = make(lua, name="MELEE")
    assert text_of(lua, i) == ("/castsequence reset=combat/6 Stoneskin Totem, Searing Totem, Healing Stream Totem, "
                               "Grounding Totem")
    P.Move(i, "air", -1)
    assert text_of(lua, i).endswith("Searing Totem, Grounding Totem, Healing Stream Totem"), text_of(lua, i)
    P.SetTotem(i, "air", None)
    P.SetTotem(i, "water", None)
    P.SetTotem(i, "fire", None)
    assert text_of(lua, i) == "/cast Stoneskin Totem", "one totem is a plain cast"
    P.SetTotem(i, "earth", None)
    assert str(P.StepText(P.Get(i))) == "None", "a preset with nothing to drop has no script"
    assert int(P.P.STEP_IDLE) == 6


def check_the_dial_carries_the_script_as_secure_attributes_written_out_of_combat_only():
    lua = boot()
    P = PS(lua)
    d = dial(lua)
    assert d._attrs["type1"] is None, "the NEW slot has nothing to drop"
    assert d._attrs["shift-type1"] == "" and d._attrs["alt-type1"] == "", "shift and alt clicks must drop nothing"
    i = make(lua)
    assert d._attrs["type1"] == "macro", "a plain click did not become the step"
    assert str(d._attrs["macrotext1"]) == text_of(lua, i)
    P.SetTotem(i, "fire", None)
    assert "Searing" not in str(d._attrs["macrotext1"]), "the script did not follow the edit"
    set_combat(lua, True)
    n = blocked(lua)
    P.Select(2)                    # the NEW slot, queued
    click(lua, d, "RightButton")
    script(lua, d, "OnMouseWheel", 1)
    assert blocked(lua) == n, "a secure write was tried in combat"
    assert d._attrs["type1"] == "macro", "the script changed in combat"
    leave_combat(lua)
    assert d._attrs["type1"] is None, "the script stayed after the dial moved to the NEW slot"
    # a script that is the same is not written again
    P.Select(1)
    first = str(d._attrs["macrotext1"])
    run(lua, "__writes = 0; local d = FSTotemButton7; local set = d.SetAttribute; "
             "d.SetAttribute = function(self, k, v) if k == 'macrotext1' then __writes = __writes + 1 end return set(self, k, v) end")
    TB(lua).Sync()
    assert int(g(lua).__writes) == 0, "the same script was written again"
    assert str(d._attrs["macrotext1"]) == first


def check_a_press_counts_on_the_event_the_game_acts_on():
    lua = boot()
    make(lua)
    d = dial(lua)
    t = PS(lua).Tracker("dial")
    click(lua, d, "LeftButton", True)
    assert int(t.presses) == 0, "a key down counted with the up-event setting"
    click(lua, d, "LeftButton", False)
    assert int(t.presses) == 1
    run(lua, '__cvars.ActionButtonUseKeyDown = "1"')
    click(lua, d, "LeftButton", True)
    click(lua, d, "LeftButton", False)
    assert int(t.presses) == 2, "the down event is the press when the game acts on key down"
    # a shift click is an edit, not a press
    run(lua, "__shift = true")
    click(lua, d, "LeftButton", True)
    click(lua, d, "LeftButton", False)
    assert int(t.presses) == 2, "an edit click was counted as a drop"
    run(lua, "__shift = false")
    DL(lua).CloseEditor()
    # an Alt click drops nothing: no press either, on either cell
    run(lua, "__alt = true")
    gt = PS(lua).Tracker("gnarly")
    for cell_btn in (d, btn(lua, "gnarly")):
        click(lua, cell_btn, "LeftButton", True)
        click(lua, cell_btn, "LeftButton", False)
    assert int(t.presses) == 2 and int(gt.presses) == 0, "an Alt click was counted as a drop"
    assert PS(lua).PressAge("gnarly") is None, "an Alt click started the GNARLY press flash"
    # Alt with Shift is still the shift edit: it opens the editor and counts nothing
    run(lua, "__shift = true")
    click(lua, d, "LeftButton", True)
    click(lua, d, "LeftButton", False)
    assert card(lua) is not None and shown(card(lua)), "alt+shift did not open the editor"
    assert int(t.presses) == 2, "alt+shift was counted as a drop"
    run(lua, "__shift = false")
    DL(lua).CloseEditor()
    run(lua, "__alt = false")
    click(lua, d, "RightButton", False)
    assert int(t.presses) == 2


def cast_raw(lua, name):
    run(lua, f"__castOk({IDS[name]})")


def cast_name(lua, name, cell="dial"):
    """A press of the cell, then the cast it brings (the game casts after the click)."""
    click(lua, btn(lua, cell), "LeftButton", False)
    cast_raw(lua, name)


def check_the_record_advances_on_the_next_totem_cast_and_ignores_the_rest():
    lua = boot()
    P = PS(lua)
    make(lua)
    assert tuple(P.Progress("dial")) == (0, 4)
    cast_name(lua, "Searing Totem")
    assert P.Progress("dial")[0] == 0, "a cast out of turn counted"
    advance(lua, 2.5)
    cast_raw(lua, "Stoneskin Totem")
    assert P.Progress("dial")[0] == 0, "a cast with no press before it counted"
    cast_name(lua, "Stoneskin Totem")
    assert tuple(P.Progress("dial")) == (1, 4)
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("dial")[0] == 1
    for name in ("Searing Totem", "Healing Stream Totem", "Grounding Totem"):
        cast_name(lua, name)
    assert P.Progress("dial")[0] == 4
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("dial")[0] == 1, "a finished sequence starts over at the next drop"
    run(lua, '__fire_event("UNIT_SPELLCAST_SUCCEEDED", "target", "guid", %d)' % IDS["Searing Totem"])
    assert P.Progress("dial")[0] == 1, "another unit's cast counted"
    assert int(P.Tracker("dial").matched) == 5
    advance(lua, 2.5)
    cast_raw(lua, "Searing Totem")
    assert P.Progress("dial")[0] == 1, "a cast long after the press counted"


def check_the_record_starts_over_at_combat_end_after_six_idle_seconds_and_on_any_edit():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    cast_name(lua, "Stoneskin Totem")
    cast_name(lua, "Searing Totem")
    assert P.Progress("dial")[0] == 2
    advance(lua, 5.5)
    tick(lua)
    assert P.Progress("dial")[0] == 2, "it started over before six seconds"
    advance(lua, 0.6)
    tick(lua)
    assert P.Progress("dial")[0] == 0, "it did not start over after six seconds"
    # a drop restarts the clock
    cast_name(lua, "Stoneskin Totem")
    advance(lua, 4)
    cast_name(lua, "Searing Totem")
    advance(lua, 4)
    tick(lua)
    assert P.Progress("dial")[0] == 2, "the clock did not restart on a drop"
    # combat end
    enter_combat(lua)
    cast_name(lua, "Healing Stream Totem")
    assert P.Progress("dial")[0] == 3
    leave_combat(lua)
    assert P.Progress("dial")[0] == 0, "combat ended and the step stayed"
    # edits and switches
    cast_name(lua, "Stoneskin Totem")
    P.Rename(i, "ZZ")
    assert P.Progress("dial")[0] == 1, "a rename should not restart the step"
    P.Move(i, "air", -1)
    assert P.Progress("dial")[0] == 0, "an edit of the order left a step the script no longer has"
    cast_name(lua, "Stoneskin Totem")
    P.SetTotem(i, "fire", IDS["Magma Totem"])
    assert P.Progress("dial")[0] == 0
    cast_name(lua, "Stoneskin Totem")
    P.Select(2)
    assert P.Progress("dial")[0] == 0, "a switch left the step"


def check_a_secret_spell_id_is_noted_and_never_breaks_the_record():
    lua = boot()
    P = PS(lua)
    make(lua)
    run(lua, '__fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", __SECRET)')
    assert P.Progress("dial")[0] == 0
    P.SaveState()
    line = str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    assert "castids=secret" in line, line
    run(lua, "__fire_event('UNIT_SPELLCAST_SUCCEEDED', 'player', 'guid', nil)")
    run(lua, "__fire_event('UNIT_SPELLCAST_SUCCEEDED', 'player', 'guid', 'x')")


# ---------------------------------------------------------------------------------------------
# Checks: the face
# ---------------------------------------------------------------------------------------------


def check_the_ring_has_one_arc_per_totem_tinted_by_its_element():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    look(lua)
    ks = kinds(lua)
    assert [(n, k) for n, _, k in ks] == [("4", "t")] * 4 and [a for _, a, _ in ks] == ["1", "2", "3", "4"], ks
    a = arcs(lua)
    for slot, element in enumerate(order_of(lua, i)):
        close(a[slot][2], ELEMENT_COLOR[element], f"arc {slot + 1} ({element})")
        assert abs(a[slot][2][3] - 0.55) < 0.01, "the quiet arc alpha"
    P.SetTotem(i, "air", None)
    P.SetTotem(i, "fire", None)
    look(lua)
    ks = kinds(lua)
    assert [(n, k) for n, _, k in ks] == [("2", "t")] * 2, ks
    P.SetTotem(i, "water", None)
    look(lua)
    ks = kinds(lua)
    assert ks == [("1", "1", "t")], "one totem is a full circle"
    assert not any(sh for sh, *_ in arcs(lua)[1:]), "unused arcs stayed up"
    assert not shown(btn(lua, "dial").fsEmpty)


def check_the_digit_the_plus_and_the_dashed_empty_ring():
    lua = boot()
    P = PS(lua)
    look(lua)
    d = btn(lua, "dial")
    assert str(d.fsDigit._text) == "+" and shown(d.fsEmpty), "the NEW slot shows a plus on a dashed ring"
    assert not any(sh for sh, *_ in arcs(lua))
    i = make(lua)
    look(lua)
    assert str(d.fsDigit._text) == "1" and not shown(d.fsEmpty)
    P.SetTotem(i, "earth", None), P.SetTotem(i, "fire", None), P.SetTotem(i, "water", None), P.SetTotem(i, "air", None)
    look(lua)
    assert str(d.fsDigit._text) == "+" and shown(d.fsEmpty), "a preset with nothing in it looks empty"
    two = make(lua)
    P.Select(two)
    look(lua)
    assert str(d.fsDigit._text) == "2"


def check_a_locked_totem_is_a_dashed_muted_arc_and_the_step_skips_it():
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"])
    P = PS(lua)
    i = make(lua)
    P.SetTotem(i, "water", IDS["Healing Stream Totem"]), P.SetTotem(i, "air", IDS["Grounding Totem"])
    look(lua)
    ks = kinds(lua)
    locked = [k for n, a, k in ks if k == "d"]
    assert len(locked) == 2, ks
    a = arcs(lua)
    close(a[2][2], MUTED, "a locked arc is muted"), close(a[3][2], MUTED, "a locked arc is muted")
    assert abs(a[2][2][3] - 0.6) < 0.01
    cast_name(lua, "Stoneskin Totem")
    cast_name(lua, "Searing Totem")
    look(lua)
    assert tuple(P.Progress("dial")) == (2, 2), "the total counts the totems that drop"
    assert [k for _, _, k in kinds(lua)] == ["g", "g", "d", "d"], kinds(lua)


def check_while_stepping_done_arcs_glow_the_next_is_thick_and_the_icon_replaces_the_digit():
    lua = boot()
    make(lua)
    d = btn(lua, "dial")
    cast_name(lua, "Stoneskin Totem")
    look(lua)
    ks = [k for _, _, k in kinds(lua)]
    assert ks == ["g", "k", "t", "t"], ks
    a = arcs(lua)
    assert abs(a[0][2][3] - 1.0) < 0.01 and abs(a[1][2][3] - 0.9) < 0.01
    assert [x[3] for x in a] == [False, True, False, False], "only the next arc has the white core"
    assert shown(d.fsNext) and not shown(d.fsDigit), "the next totem's icon stands in the middle"
    assert d.fsNext._texture is not None
    assert all(shown(t) for t in seq(d.fsBrackets)), "brackets stand round the cell on the next state"
    cast_name(lua, "Searing Totem"), cast_name(lua, "Healing Stream Totem"), cast_name(lua, "Grounding Totem")
    look(lua)
    assert [k for _, _, k in kinds(lua)] == ["g", "g", "g", "g"]
    assert not any(shown(t) for t in seq(d.fsBrackets)), "no next totem, no brackets"
    assert shown(d.fsDigit) and not shown(d.fsNext)
    advance(lua, 6.5), tick(lua)
    look(lua)
    assert [k for _, _, k in kinds(lua)] == ["t"] * 4


def check_the_name_plate_and_the_raised_plate():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    look(lua)
    assert shown(rail(lua)) and str(rail(lua).text._text) == "MELEE"
    assert not shown(raise_plate(lua)), "the raised plate is for a pending switch or a step"
    cast_name(lua, "Stoneskin Totem")
    look(lua)
    assert shown(raise_plate(lua)) and str(raise_plate(lua).text._text) == "1/4", raise_plate(lua).text._text
    sq = [s for s in seq(raise_plate(lua).squares) if shown(s)]
    assert len(sq) == 4, "a square for each totem"
    set_combat(lua, True)
    P.Select(b)
    look(lua)
    assert str(raise_plate(lua).text._text) == ">CASTER", "a pending switch names its target"
    leave_combat(lua)
    look(lua)
    assert str(rail(lua).text._text) == "CASTER" and not shown(raise_plate(lua))
    conf(lua, "totems.dialPlate", False)
    look(lua)
    assert not shown(rail(lua)), "the plate stayed with its setting off"
    P.Select(3)
    conf(lua, "totems.dialPlate", True)
    look(lua)
    assert str(rail(lua).text._text) == "NEW"


def check_the_pending_look_marks_the_dial_and_the_buttons_that_will_change():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    advance(lua, 2), tick(lua)
    look(lua)
    d = btn(lua, "dial")
    assert not any(shown(t) for t in seq(d.fsDashes.dashes)), "dashes with nothing pending"
    for e in ("fire", "earth", "water", "air"):
        assert DL(lua).MarkKind(e) is None
    set_combat(lua, True)
    P.Select(b)
    look(lua)
    assert all(shown(t) for t in seq(d.fsDashes.dashes)) and all(shown(t) for t in seq(d.fsDashes.tri)), "dashed amber border and triangle"
    c = seq(seq(d.fsDashes.dashes)[1]._color)
    close(c, AMBER, "dash colour")
    close(seq(d.fsBar._vertex), AMBER, "underline colour")
    assert [str(DL(lua).MarkKind(e)) for e in ("fire", "earth", "water", "air")] == ["amber", "amber", "amber", "None"], \
        "marks sit on the elements that change and only on those"
    leave_combat(lua)
    look(lua)
    assert not any(shown(t) for t in seq(d.fsDashes.dashes))
    assert DL(lua).MarkKind("fire") == "cyan", "the buttons that changed wear the applied mark"
    assert DL(lua).MarkKind("air") is None
    close(seq(d.fsBar._vertex), CYAN, "underline back to cyan")


def check_the_applied_flash_marks_the_changed_buttons_for_a_moment_and_has_its_own_switch():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    P.Select(b)
    assert DL(lua).MarkKind("fire") == "cyan"
    advance(lua, 1.0), tick(lua)
    assert DL(lua).MarkKind("fire") == "cyan", "gone before the flash ended"
    advance(lua, 0.7), tick(lua)
    assert DL(lua).MarkKind("fire") is None, "the flash outlived its 1.6 seconds"
    conf(lua, "totems.appliedFlash", False)
    P.Select(a)
    assert all(DL(lua).MarkKind(e) is None for e in ("fire", "earth", "water", "air")), "the flash played with its setting off"
    conf(lua, "totems.appliedFlash", True)


def check_the_waiting_pulse_breathes_the_amber_and_stops_with_its_setting():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    set_combat(lua, True)
    P.Select(b)
    d = btn(lua, "dial")
    alphas = []
    for _ in range(6):
        advance(lua, 0.2), tick(lua, 0.2)
        alphas.append(round(float(seq(seq(d.fsDashes.dashes)[0]._color)[3]), 3))
    assert len(set(alphas)) > 2, f"the pulse did not move: {alphas}"
    conf(lua, "totems.waitPulse", False)
    alphas = []
    for _ in range(4):
        advance(lua, 0.2), tick(lua, 0.2)
        look(lua)
        alphas.append(round(float(seq(seq(d.fsDashes.dashes)[0]._color)[3]), 3))
    assert len(set(alphas)) == 1, f"the amber moved with the pulse off: {alphas}"


def check_the_sound_cues_play_only_with_their_setting_on_and_only_when_something_happened():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    run(lua, "__sounds = {}")
    set_combat(lua, True)
    P.Select(b)
    leave_combat(lua)
    assert len(seq(g(lua).__sounds)) == 0, "a cue played with both sound settings off"
    P.Select(a)
    assert len(seq(g(lua).__sounds)) == 0, "an applied switch played a sound with its setting off"
    conf(lua, "totems.waitSound", True), conf(lua, "totems.appliedSound", True)
    P.Select(b)
    assert [int(x) for x in seq(g(lua).__sounds)] == [857], "the applied sound"
    run(lua, "__sounds = {}")
    set_combat(lua, True)
    P.Select(a)
    assert [int(x) for x in seq(g(lua).__sounds)] == [856], "the waiting sound"
    P.Select(a)
    assert len(seq(g(lua).__sounds)) == 1, "the waiting sound repeated for the same pending choice"
    leave_combat(lua)
    assert [int(x) for x in seq(g(lua).__sounds)] == [856, 857], "the queued switch did not play the applied sound at regen"
    run(lua, "__sounds = {}")
    P.Select(a)
    assert len(seq(g(lua).__sounds)) == 0, "a switch that changed nothing played the applied sound"
    run(lua, "SOUNDKIT = {}; __sounds = {}")
    P.Select(b)
    assert len(seq(g(lua).__sounds)) == 0, "an unknown sound kit name played something"


# ---------------------------------------------------------------------------------------------
# Checks: tooltips
# ---------------------------------------------------------------------------------------------


def check_the_tooltip_lists_the_totems_in_order_the_left_out_ones_and_the_hints():
    lua = boot()
    P = PS(lua)
    i = make(lua, picks={"water": None}, name="MELEE")
    P.Select(i)
    d = dial(lua)
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "PRESET DIAL: 1 MELEE", ls
    assert ls[1:4] == ["1 Stoneskin Totem", "2 Searing Totem", "3 Grounding Totem"], ls
    assert any(x.startswith("Water: left out") for x in ls), ls
    assert any(x == "Click: drop the next totem. Right click or wheel: next preset. Shift click: edit." for x in ls), ls
    assert any(x == "Starts over after combat ends or a 6 s pause." for x in ls), ls
    assert any("|T" in x for x in lines(lua)), "the totem lines carry a colour swatch"
    conf(lua, "totems.dialWheel", False)
    hover(lua, d)
    assert any("Right click: next preset." in plain(x) and "wheel" not in plain(x).lower() for x in lines(lua))
    unhover(lua, d)
    assert not shown(g(lua).GameTooltip)


def check_the_tooltip_names_a_locked_totem_with_its_level_the_new_slot_and_a_pending_switch():
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"])
    P = PS(lua)
    d = dial(lua)
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0].startswith("PRESET 1: NEW") and any("Shift click" in x for x in ls), ls
    unhover(lua, d)
    i = make(lua, name="MELEE")
    P.SetTotem(i, "water", IDS["Healing Stream Totem"]), P.SetTotem(i, "air", IDS["Grounding Totem"])
    P.Select(i)
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert "3 Healing Stream Totem (level 20)" in ls and "4 Grounding Totem (level 30)" in ls, ls
    unhover(lua, d)
    set_combat(lua, True)
    P.Select(2)
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert any(x.startswith("Waiting for combat to end") for x in ls), ls
    set_combat(lua, False)


# ---------------------------------------------------------------------------------------------
# Checks: the editor
# ---------------------------------------------------------------------------------------------


def card(lua):
    return DL(lua).Card()


def check_shift_click_on_the_new_slot_makes_a_preset_and_opens_the_editor_on_it():
    lua = boot()
    P = PS(lua)
    d = dial(lua)
    run(lua, "__shift = true")
    click(lua, d, "LeftButton", True)
    assert P.Count() == 0 and card(lua) is None, "the key down of a shift click edited"
    click(lua, d, "LeftButton", False)
    assert P.Count() == 1 and card(lua) is not None and shown(card(lua)) and int(card(lua).fsIndex) == 1
    assert str(card(lua).name._text) == "NEW"
    assert int(PS(lua).Tracker("dial").presses) == 0
    run(lua, "__shift = false")
    DL(lua).CloseEditor()
    P.Create()
    P.Select(2)
    run(lua, "__shift = true")
    click(lua, d, "LeftButton", False)
    assert int(card(lua).fsIndex) == 2, "shift click opened the wrong preset"
    P.Create()
    P.Create()
    assert P.Count() == 4
    P.Select(4)
    DL(lua).CloseEditor()
    click(lua, d, "LeftButton", False)
    assert int(card(lua).fsIndex) == 4 and P.Count() == 4


def rows(lua):
    return seq(card(lua).rows)


def check_the_editor_rows_the_chooser_and_the_up_down_buttons():
    lua = boot()
    P = PS(lua)
    i = make(lua, picks={"fire": None}, name="MELEE")
    DL(lua).OpenEditor(i)
    c = card(lua)
    assert str(c.title._text) == "PRESET 1" and str(c.name._text) == "MELEE" and str(c.label._text) == "DROP ORDER"
    r = rows(lua)
    assert [str(x.fsElement) for x in r] == ["earth", "water", "air", "fire"], "set rows first, then the left out ones"
    assert [str(x.label._text) for x in r][:3] == ["Stoneskin", "Healing Stream", "Grounding"], [str(x.label._text) for x in r]
    assert str(r[3].label._text) == "left out" and not shown(r[3].up) and not shown(r[3].down)
    assert not shown(r[0].up) and shown(r[0].down) and shown(r[2].up) and not shown(r[2].down)
    script(lua, r[1].down, "OnClick")
    assert order_of(lua, i) == ["earth", "air", "water"]
    assert [str(x.fsElement) for x in rows(lua)][:3] == ["earth", "air", "water"], "the card did not redraw"
    script(lua, rows(lua)[2].up, "OnClick")
    assert order_of(lua, i) == ["earth", "water", "air"]
    # the chooser: the known totems of the element and "left out"
    script(lua, rows(lua)[3].tile, "OnClick")
    ch = DL(lua).Chooser()
    assert ch is not None and shown(ch)
    tiles = [t for t in seq(ch.tiles) if shown(t)]
    assert len(tiles) == len(TOTEMS["fire"]) + 1, f"{len(tiles)} tiles"
    script(lua, tiles[2], "OnClick")
    assert int(P.Get(i).picks.fire) == IDS["Magma Totem"] and order_of(lua, i)[-1] == "fire"
    assert not shown(ch), "the chooser stayed after a choice"
    assert pick_of(lua, "fire") == "Magma Totem", "the active preset did not reach the button"
    script(lua, rows(lua)[3].tile, "OnClick")
    tiles = [t for t in seq(DL(lua).Chooser().tiles) if shown(t)]
    script(lua, tiles[-1], "OnClick")
    assert P.Get(i).picks.fire is None and "fire" not in order_of(lua, i), "left out did not remove the totem"
    # a totem not known yet is not offered
    lua = boot(learned=TOTEMS["fire"][:2])
    i = make(lua)
    DL(lua).OpenEditor(i)
    script(lua, rows(lua)[0].tile, "OnClick")
    assert len([t for t in seq(DL(lua).Chooser().tiles) if shown(t)]) == 3, "only the two known totems and left out"


def check_the_name_box_commits_on_enter_and_on_losing_focus_and_cleans_the_name():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    nb = card(lua).name
    assert int(nb._max) == 8
    nb._text = "tank!"
    script(lua, nb, "OnEnterPressed")
    assert str(P.Get(i).name) == "TANK"
    nb._text = "heal 2"
    script(lua, nb, "OnEditFocusLost")
    assert str(P.Get(i).name) == "HEAL 2"
    nb._text = ""
    script(lua, nb, "OnEditFocusLost")
    assert str(P.Get(i).name) == "HEAL 2", "an empty name replaced a good one"
    look(lua)
    assert str(rail(lua).text._text) == "HEAL 2", "the name plate did not follow the rename"


def check_delete_asks_twice_and_the_confirmation_runs_out():
    lua = boot()
    P = PS(lua)
    P.Create(), P.Create()
    DL(lua).OpenEditor(1)
    dl = card(lua).delete
    script(lua, dl, "OnClick")
    assert P.Count() == 2 and str(dl.text._text) == "SURE?", "the first click deleted or did not ask"
    advance(lua, 3.5)
    script(lua, dl, "OnClick")
    assert P.Count() == 2, "an old confirmation still counted"
    script(lua, dl, "OnClick")
    assert P.Count() == 1 and not shown(card(lua)), "the second click did not delete and close"


def check_the_card_closes_on_escape_and_combat_and_hangs_on_the_last_cell():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    assert "FSTotemEditor" in [str(x) for x in seq(g(lua).UISpecialFrames)], "Escape does not close the card"
    assert c._strata == "DIALOG"
    p = c._points[1]
    assert (p.point, p.relPoint) == ("BOTTOMRIGHT", "TOPRIGHT") and sb.same(lua, p.rel, btn(lua, "gnarly")), \
        "the card hangs on the last cell"
    approx(p.x, 4.4, "card x"), approx(p.y, 21, "card y")
    DL(lua).CloseEditor()
    conf(lua, "totems.gnarly", False)
    DL(lua).OpenEditor(i)
    assert sb.same(lua, c._points[len(seq(c._points))].rel, dial(lua)), "with GNARLY off the card hangs on the dial"
    conf(lua, "totems.gnarly", True)
    assert float(c._w) >= 198.0, "the card is narrower than its design width"
    approx(float(c._h), 56 + 4 * 27 + 30, "card height")
    DL(lua).OpenEditor(i)
    script(lua, rows(lua)[0].tile, "OnClick")
    assert shown(DL(lua).Chooser())
    DL(lua).CloseEditor()
    assert not shown(c) and not shown(DL(lua).Chooser()), "the chooser outlived the card"
    DL(lua).OpenEditor(i)
    enter_combat(lua)
    assert not shown(c)
    # in combat a chooser does not open either
    DL(lua).OpenEditor(i)
    assert not shown(c)


def check_no_secure_frame_is_anchored_to_the_card_or_its_pieces():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    assert not any(f._secure for f in [c] + seq(c._regions) if f._kind not in ("Texture", "FontString")), \
        "a secure frame is part of the card"
    for key in ("fire", "earth", "water", "air", "dial"):
        for p in seq(btn(lua, key)._points):
            assert p.rel is None or not sb.same(lua, p.rel, c), "a secure button is anchored to the card"


# ---------------------------------------------------------------------------------------------
# Checks: seats
# ---------------------------------------------------------------------------------------------


def check_the_tab_grows_by_one_cell_and_the_buff_and_five_second_tabs_follow(scale):
    lua = boot(scale, tabs=True)
    cs = csh.cs(lua)
    host = g(lua).FSTotemBar
    w7 = 2 * PAD + 7 * BTN + 6 * GAP
    w8 = 2 * PAD + 8 * BTN + 7 * GAP
    approx(float(host._w) / scale, w8, "host width in design px", 0.01)
    assert TB(lua).Cols() == 8
    d = dial(lua)
    q = d._points[1]
    assert sb.same(lua, q.rel, host) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT")
    approx(q.x, (PAD + 6 * (BTN + GAP)) * scale, "dial x"), approx(q.y, 5 * scale, "dial y")
    approx(float(d._w), BTN * scale, "dial width"), approx(float(d._h), BTN * scale, "dial height")
    assert shown(d)
    g8 = btn(lua, "gnarly")._points[1]
    approx(g8.x, (PAD + 7 * (BTN + GAP)) * scale, "GNARLY x")
    buff_x = 36 + w8 + 16
    approx(g(lua).FSBuffTab._points[1].x, buff_x * scale, "buff tab follows", 0.5 * scale)
    five_x = buff_x + 92.8 + 16
    approx(g(lua).FSFiveSecondTab._points[1].x, five_x * scale, "five second tab follows", 0.5 * scale)
    # the dial off puts them back
    conf(lua, "totems.dial", False)
    approx(float(host._w) / scale, w7, "host width with the dial off", 0.01)
    assert not shown(d), "the dial stayed with its switch off"
    g7 = btn(lua, "gnarly")._points[1]
    approx(g7.x, (PAD + 6 * (BTN + GAP)) * scale, "GNARLY steps into column 7")
    approx(g(lua).FSBuffTab._points[1].x, (36 + w7 + 16) * scale, "buff tab with one cell", 0.5 * scale)
    conf(lua, "totems.gnarly", False)
    approx(float(host._w) / scale, 2 * PAD + 6 * BTN + 5 * GAP, "host width back to six", 0.01)
    assert not shown(btn(lua, "gnarly")), "the GNARLY cell stayed with its switch off"
    approx(g(lua).FSBuffTab._points[1].x, 316 * scale, "buff tab back", 0.5 * scale)
    approx(g(lua).FSFiveSecondTab._points[1].x, (316 + 92.8 + 16) * scale, "five second tab back", 0.5 * scale)
    conf(lua, "totems.dial", True), conf(lua, "totems.gnarly", True)
    assert shown(dial(lua)) and shown(btn(lua, "gnarly"))
    approx(g(lua).FSBuffTab._points[1].x, buff_x * scale, "buff tab again", 0.5 * scale)
    # the shoulder art is the wider block
    bw, bh, _ = cs.BlockSize()
    approx(float(bw), w8 * scale, "BlockSize width", 0.5)


def same_obj(lua, a, b) -> bool:
    return bool(lua.eval("function(a, b) return a == b end")(a, b))


def check_a_resize_hides_the_art_of_the_old_width():
    lua = boot()
    cs = g(lua).FS.ClassShoulder
    wide = cs.Shoulder().art
    assert shown(wide)
    conf(lua, "totems.gnarly", False)
    narrow = cs.Shoulder().art
    assert not same_obj(lua, wide, narrow), "the art for the new width was not built"
    assert shown(narrow) and not shown(wide), "the old width's art stayed on screen"
    conf(lua, "totems.gnarly", True)
    assert shown(cs.Shoulder().art) and not shown(narrow), "going back left the narrow art up"


def check_edit_clicks_in_every_modifier_combination_never_drop_a_totem():
    lua = boot()
    make(lua)
    for key in ("dial", "gnarly"):
        b = btn(lua, key)
        for name in ("shift-type1", "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1",
                     "ctrl-shift-type1"):
            assert b._attrs[name] == "", f"{key}: {name} would fall back to the plain click and drop a totem"
    d = dial(lua)
    assert d._attrs["type1"] == "macro" and d._attrs["ctrl-type1"] is None, "a plain ctrl click keeps dropping"
    # a script change keeps the blanks; clearing the preset's totems clears the script but not the blanks
    PS(lua).SetTotem(1, "fire", None)
    assert d._attrs["alt-ctrl-shift-type1"] == ""


def check_the_dial_tip_says_a_shift_keybind_edits():
    lua = boot()
    assert "keybind that includes Shift" in str(PS(lua).SETTINGS.dial.tip)


def check_a_character_key_that_cannot_be_read_never_saves_under_a_made_up_one():
    for unreadable in ("nil", "__SECRET", '""'):
        lua = boot()
        run(lua, f"ForeverSTUwaveDB.totemPresets = nil; __guid = UnitGUID; UnitGUID = function() return {unreadable} end")
        P = PS(lua)
        assert P.Count() == 0 and P.Writable() is False
        r = P.Create()
        assert not r or r[0] is None, "an edit went through with no character key"
        assert "editable in a moment" in str(P.Refusal()), "the refusal blames the session instead of the moment"
        P.Select(1)
        db = g(lua).ForeverSTUwaveDB
        assert db.totemPresets is None, f"{unreadable}: presets were saved with no character key"
        run(lua, "UnitGUID = __guid")
        assert P.Writable() is True and P.Count() == 0
        assert P.Create(), "creating works once the key reads"
        assert saved(lua) is not None and g(lua).ForeverSTUwaveDB.totemPresets["player"] is None


def check_an_unreadable_character_key_with_a_database_that_cannot_save_keeps_the_session_refusal():
    for setup in ("FS.Config.IsReadOnly = function() return true end", "ForeverSTUwaveDB = nil",
                  'ForeverSTUwaveDB = "oops"'):
        lua = boot()
        run(lua, f"UnitGUID = function() return nil end; {setup}")
        P = PS(lua)
        assert P.Writable() is False
        assert "cannot be saved this session" in str(P.Refusal()), f"{setup}: the refusal promised an edit in a moment"


def check_the_known_totems_are_scanned_once_per_event_not_once_per_repaint():
    lua = boot()
    P = PS(lua)
    two_presets(lua)
    P.Select(1)
    enter_combat(lua)
    P.Select(2)
    assert P.Pending() == 2
    run(lua, "__kl = 0; local k = FS.TotemBar.KnownList; FS.TotemBar.KnownList = function(...) __kl = __kl + 1 return k(...) end")
    fire(lua, "SPELLS_CHANGED")                    # a cold cache
    for _ in range(20):
        advance(lua, 0.1)
        tick(lua, 0.1)
    scans = int(g(lua).__kl)
    assert 0 < scans <= 4, f"{scans} spellbook scans over twenty repaints of a waiting switch"
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
        scans = int(g(lua).__kl)
        fire(lua, event)
        advance(lua, 0.1)
        tick(lua, 0.1)
        assert int(g(lua).__kl) > scans, f"{event} did not drop the cached list"
    scans = int(g(lua).__kl)
    leave_combat(lua)
    assert int(g(lua).__kl) > scans, "regen did not drop the cached list"
    scans = int(g(lua).__kl)
    TB(lua).Sync()
    assert int(g(lua).__kl) > scans, "a sync did not drop the cached list"


def check_a_totem_learned_during_the_fight_is_picked_by_the_switch_that_waited():
    lua = boot(learned=[n for n in TOTEMS["earth"] + TOTEMS["fire"]])
    P = PS(lua)
    a = make(lua)
    b = make(lua, picks={"water": "Healing Stream Totem"})
    P.Select(a)
    enter_combat(lua)
    assert P.Select(b) == "queued"
    for _ in range(3):
        advance(lua, 0.1)
        tick(lua, 0.1)                      # paints, so the list of known totems is cached as it was
    assert P.Entry("water", IDS["Healing Stream Totem"]).known is False
    run(lua, '__know("Healing Stream Totem")')   # learned mid fight, no event reached the preset code
    set_combat(lua, False)
    P.OnRegen()
    changed = [str(x) for x in seq(P.P.applied.elements)] if P.P.applied else []
    assert "water" in changed, f"the waiting switch used a stale list: {changed}"


def check_the_dial_switch_pressed_in_combat_waits_for_regen():
    lua = boot(tabs=True)
    d = dial(lua)
    set_combat(lua, True)
    n = blocked(lua)
    conf(lua, "totems.dial", False)
    assert blocked(lua) == n, "a protected write was tried in combat"
    assert shown(d), "the dial hid in combat"
    approx(float(g(lua).FSTotemBar._w), 2 * PAD + 8 * BTN + 7 * GAP, "the host kept its width in combat")
    leave_combat(lua)
    TB(lua).Sync()
    assert not shown(d), "the dial did not hide after combat"
    approx(float(g(lua).FSTotemBar._w), 2 * PAD + 7 * BTN + 6 * GAP, "host one cell narrower after combat")


def check_the_cells_stand_right_of_the_six_and_the_buttons_keep_their_slots():
    lua = boot()
    for i, key in enumerate(("fire", "earth", "water", "air", "set", "recall"), 1):
        q = g(lua)[f"FSTotemButton{i}"]._points[1]
        approx(q.x, PAD + (i - 1) * (BTN + GAP), f"button {i} x")
    assert str(dial(lua).fsKey) == "dial" and dial(lua).commandName == "CLICK FSTotemButton7:LeftButton"
    assert str(g(lua)["BINDING_NAME_CLICK FSTotemButton7:LeftButton"]) == "Totem preset dial"
    assert str(btn(lua, "gnarly").fsKey) == "gnarly" and btn(lua, "gnarly").commandName == "CLICK FSTotemButton8:LeftButton"
    assert str(g(lua)["BINDING_NAME_CLICK FSTotemButton8:LeftButton"]) == "Totem GNARLY preset"
    names = [b.get("name") for b in ET.parse(BINDINGS).getroot().findall("Binding")]
    assert "CLICK FSTotemButton8:LeftButton" in names, names


def check_a_rescale_resizes_and_reseats_the_face():
    lua = boot(1.0, tabs=True)
    make(lua)
    look(lua)
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    d = dial(lua)
    approx(float(d._w), BTN * s, "dial width after a rescale")
    q = d._points[1]
    approx(q.x, (PAD + 6 * (BTN + GAP)) * s, "dial x after a rescale")
    approx(float(btn(lua, "dial").fsRail._h), 12 * s, "plate height after a rescale")
    approx(float(g(lua).FSTotemBar._w), (2 * PAD + 8 * BTN + 7 * GAP) * s, "host width after a rescale")
    approx(g(lua).FSBuffTab._points[1].x, (36 + 2 * PAD + 8 * BTN + 7 * GAP + 16) * s, "buff tab after a rescale", 0.5)


# ---------------------------------------------------------------------------------------------
# Checks: the GNARLY cell
# ---------------------------------------------------------------------------------------------


def gnarly_world(**kw):
    """A world with two presets; the second is the GNARLY preset."""
    lua = boot(**kw)
    a, b = two_presets(lua)
    assert PS(lua).SetGnarly(b) is True
    PS(lua).Select(a)
    return lua, a, b


def gb(lua):
    return btn(lua, "gnarly")


def check_the_gnarly_cell_carries_its_own_preset_whatever_the_dial_is_doing():
    lua = boot()
    P = PS(lua)
    g8 = gb(lua)
    assert g8._attrs["type1"] is None and g8._attrs["shift-type1"] == "" and g8._attrs["alt-type1"] == ""
    a, b = two_presets(lua)
    assert P.Gnarly() is None and P.CellPreset("gnarly") is None
    assert P.SetGnarly(b) is True and P.Gnarly() == b
    assert g8._attrs["type1"] == "macro" and str(g8._attrs["macrotext1"]) == text_of(lua, b)
    assert "Magma Totem" in str(g8._attrs["macrotext1"])
    # the dial turns: GNARLY keeps its script, in and out of combat
    script_text = str(g8._attrs["macrotext1"])
    P.Select(a)
    P.Select(b)
    P.Select(3)
    assert str(g8._attrs["macrotext1"]) == script_text, "a dial switch changed the GNARLY script"
    P.Select(a)
    set_combat(lua, True)
    n = blocked(lua)
    P.Select(b)
    assert P.Pending() == b and str(g8._attrs["macrotext1"]) == script_text
    click(lua, g8, "LeftButton", False)
    assert blocked(lua) == n, "a press tried a protected write"
    assert int(P.Tracker("gnarly").presses) == 1, "GNARLY did not take a press in combat"
    assert int(P.Tracker("dial").presses) == 0
    cast_name(lua, "Tremor Totem", "gnarly")
    assert tuple(P.Progress("gnarly")) == (1, 3), tuple(P.Progress("gnarly"))
    leave_combat(lua)
    assert P.Progress("gnarly")[0] == 0, "combat ended and the GNARLY step stayed"


def check_gnarly_is_set_unset_edited_and_shifted_by_a_delete():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    assert P.SetGnarly(9)[0] is False, "a preset that does not exist was accepted"
    set_combat(lua, True)
    assert P.SetGnarly(b)[0] is False and P.Gnarly() is None, "GNARLY was tied in combat"
    set_combat(lua, False)
    P.SetGnarly(b)
    g8 = gb(lua)
    # an edit of the GNARLY preset reaches its script even when the dial shows another preset
    P.Select(a)
    P.SetTotem(b, "water", None)
    assert "Mana Spring" not in str(g8._attrs["macrotext1"]), "an edit did not reach the GNARLY script"
    P.Move(b, "earth", 1)
    assert str(g8._attrs["macrotext1"]) == text_of(lua, b)
    # a delete before it shifts the tie, a delete of it unties
    c = make(lua)
    P.SetGnarly(c)
    P.Delete(a)
    assert P.Gnarly() == c - 1 and str(g8._attrs["macrotext1"]) == text_of(lua, c - 1)
    P.Delete(P.Gnarly())
    assert P.Gnarly() is None and g8._attrs["type1"] is None, "deleting the GNARLY preset left its script"
    P.SetGnarly(1)
    assert P.SetGnarly(None) is True and P.Gnarly() is None
    assert [str(x.text) for x in seq(P.GnarlyChoices())][:1] == ["None"]
    assert str(P.GnarlyName(0)) == "None"


def check_the_gnarly_cell_looks_pink_with_a_bang_and_its_own_plate():
    lua, a, b = gnarly_world()
    g8 = gb(lua)
    look(lua)
    assert str(g8.fsDigit._text) == "!" and str(g8.fsRail.text._text) == "CASTER"
    ks = kinds(lua, "gnarly")
    assert [(n, k) for n, _, k in ks] == [("3", "t")] * 3, ks
    ring = g8.fsSkin.border.ring._vertex
    close(seq(ring), PINK, "ring colour")
    close(seq(g8.fsBar._vertex), PINK, "underline colour")
    close(seq(g8.fsRail.edges[1]._color), PINK, "plate edge")
    # the dial next to it stays cyan
    close(seq(dial(lua).fsSkin.border.ring._vertex), CYAN, "dial ring colour")
    cast_name(lua, "Tremor Totem", "gnarly")
    look(lua)
    assert str(g8.fsRaise.text._text) == "1/3" and [k for _, _, k in kinds(lua, "gnarly")] == ["g", "k", "t"]
    assert PS(lua).Progress("dial")[0] == 0, "a GNARLY drop moved the dial's step"
    # no preset: a dashed ring with a muted bang and a plate that says so
    PS(lua).SetGnarly(None)
    look(lua)
    assert str(g8.fsDigit._text) == "!" and shown(g8.fsEmpty) and str(g8.fsRail.text._text) == "UNSET"
    close(seq(g8.fsDigit._textColor), MUTED, "the bang is muted without a preset")


def check_two_cells_with_the_same_first_totem_count_a_cast_for_the_one_pressed():
    lua = boot()
    P = PS(lua)
    a = make(lua, picks={"fire": "Searing Totem", "earth": "Stoneskin Totem", "water": None, "air": None}, name="ONE")
    b = make(lua, picks={"fire": "Magma Totem", "earth": "Stoneskin Totem", "water": None, "air": None}, name="TWO")
    P.SetGnarly(b)
    P.Select(a)
    cast_name(lua, "Stoneskin Totem", "gnarly")
    assert (P.Progress("dial")[0], P.Progress("gnarly")[0]) == (0, 1), "the cast went to the wrong cell"
    advance(lua, 3)
    cast_name(lua, "Stoneskin Totem", "dial")
    assert (P.Progress("dial")[0], P.Progress("gnarly")[0]) == (1, 1)
    # both pressed, the later press owns the cast
    run(lua, "FS.TotemPresets.ResetSteps()")
    click(lua, dial(lua), "LeftButton", False)
    advance(lua, 0.3)
    click(lua, gb(lua), "LeftButton", False)
    cast_raw(lua, "Stoneskin Totem")
    assert (P.Progress("dial")[0], P.Progress("gnarly")[0]) == (0, 1)


def check_the_press_flash_and_sound_belong_to_the_gnarly_cell_and_have_their_own_switches():
    lua, a, b = gnarly_world()
    g8 = gb(lua)
    ring = lambda: float(seq(g8.fsSkin.border.ring._vertex)[3])
    look(lua)
    base = ring()
    click(lua, g8, "LeftButton", False)
    assert ring() > base + 0.1, "no flash on a press"
    advance(lua, 0.2), tick(lua)
    assert ring() > base + 0.1, "the flash ended early"
    advance(lua, 0.2), tick(lua)
    assert abs(ring() - base) < 0.01, "the flash outlived its time"
    advance(lua, 6.5), tick(lua), look(lua)
    base = ring()
    conf(lua, "totems.gnarlyFlash", False)
    click(lua, g8, "LeftButton", False)
    assert abs(ring() - base) < 0.01, "the flash played with its setting off"
    # the dial never flashes on a press
    click(lua, dial(lua), "LeftButton", False)
    assert float(seq(dial(lua).fsSkin.border.ring._vertex)[3]) < 0.95
    run(lua, "__sounds = {}")
    click(lua, g8, "LeftButton", False)
    assert len(seq(g(lua).__sounds)) == 0, "a press sound played with its setting off"
    conf(lua, "totems.gnarlySound", True)
    click(lua, g8, "LeftButton", False)
    assert [int(x) for x in seq(g(lua).__sounds)] == [858]
    click(lua, dial(lua), "LeftButton", False)
    assert len(seq(g(lua).__sounds)) == 1, "the dial played the GNARLY press sound"


def check_the_gnarly_tooltip_and_the_unset_tooltip():
    lua, a, b = gnarly_world()
    g8 = gb(lua)
    hover(lua, g8)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "GNARLY PRESET: CASTER", ls
    assert ls[1:4] == ["1 Tremor Totem", "2 Magma Totem", "3 Mana Spring Totem"], ls
    assert "Click: drop the next totem. Always ready, even in combat." in ls, ls
    assert "Starts over after combat ends or a 6 s pause." in ls
    unhover(lua, g8)
    PS(lua).SetGnarly(None)
    hover(lua, g8)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "GNARLY PRESET: NONE" and any("USE AS GNARLY PRESET" in x for x in ls), ls


def check_use_as_gnarly_preset_in_the_editor_ties_and_unties_and_shift_click_edits_it():
    lua, a, b = gnarly_world()
    P = PS(lua)
    P.SetGnarly(None)
    DL(lua).OpenEditor(a)
    ub = card(lua).useGnarly
    assert str(ub.text._text) == "USE AS GNARLY PRESET"
    assert float(ub._w) >= 120 and float(card(lua).delete._w) >= 58
    script(lua, ub, "OnClick")
    assert P.Gnarly() == a and gb(lua)._attrs["type1"] == "macro"
    close(seq(ub.edges[1]._color), PINK, "the tied button is pink")
    script(lua, ub, "OnClick")
    assert P.Gnarly() is None, "a second press did not untie it"
    script(lua, ub, "OnClick")
    DL(lua).CloseEditor()
    P.SetGnarly(b)
    run(lua, "__shift = true")
    click(lua, gb(lua), "LeftButton", False)
    assert shown(card(lua)) and int(card(lua).fsIndex) == b, "shift click on GNARLY did not edit its preset"
    assert int(P.Tracker("gnarly").presses) == 0
    run(lua, "__shift = false")
    DL(lua).CloseEditor()
    P.SetGnarly(None)


def check_the_editor_buttons_that_size_to_their_text_are_padded_symmetrically_and_snapped_to_whole_pixels():
    pad = 14.0                                  # D.BTN_PAD, the config window's buttons: text + 28
    for es, sc in ((1.0, 1.0), (0.64, 1.0), (1.3333333, 1.25), (1.2, LIVE_SCALE)):
        lua = boot(sc)
        set_display(lua, es, sc)
        P = PS(lua)
        i = make(lua)
        DL(lua).OpenEditor(i)
        c = card(lua)
        for name in ("useGnarly", "delete"):
            b = getattr(c, name)
            w = float(b._w)
            for label in {"useGnarly": ["USE AS GNARLY PRESET"], "delete": ["DELETE", "SURE?"]}[name]:
                assert w >= len(label) * 5.4 + 2 * pad * sc - 1e-6, f"es {es}: {name} is {w} wide, {label} needs more"
            assert abs(w * es - round(w * es)) < 1e-6, f"es {es}: {name} is not whole physical pixels ({w * es})"
            assert round(w * es) % 2 == 0, f"es {es}: {name} is an odd number of pixels wide, its centred label lands on a half pixel"
            h = float(b._h)
            assert abs(h * es - round(h * es)) < 1e-6 and round(h * es) % 2 == 0, f"es {es}: {name} is {h} tall"
            p = b.text._points[1]
            assert (p.point, p.relPoint) == ("CENTER", "CENTER") and not float(p.x or 0) and not float(p.y or 0), \
                f"{name}: the label is not centred"
            assert sb.same(lua, p.rel, b)
        # SURE? does not change the width
        before = float(c.delete._w)
        script(lua, c.delete, "OnClick")
        assert str(c.delete.text._text) == "SURE?" and float(c.delete._w) == before
        # side by side inside the card
        assert (8 + 6 + 8) * sc + float(c.useGnarly._w) + float(c.delete._w) <= float(c._w) + 1e-6, "the buttons overflow the card"
        edge = 2 * round(8 * sc * es) / es
        assert abs(float(c.name._w) - (float(c._w) - edge)) < 1e-6 and abs(float(rows(lua)[0]._w) - (float(c._w) - edge)) < 1e-6


def rgba(t):
    c = t._color if t._color is not None else t._vertex
    return tuple(round(float(c[i]), 4) for i in (1, 2, 3, 4)) if c is not None else None


def look_of(b):
    """Everything a button's state paints: fill, edges, label colour, glyph pixels, frame alpha."""
    out = {"fill": rgba(b.fill), "alpha": float(b._alpha), "edges": [rgba(e) for e in seq(b.edges)]}
    tc = b.text._textColor
    out["text"] = tuple(round(float(tc[i]), 4) for i in (1, 2, 3, 4)) if tc is not None else None
    out["glyph"] = [rgba(t) for t in seq(b.glyph)] if b.glyph is not None else []
    return out


def drive(lua, b, label, hover_changes=True):
    """Enter, press, release, leave: each state looks different from the last and leave restores the first exactly."""
    base = look_of(b)
    script(lua, b, "OnEnter")
    hov = look_of(b)
    if hover_changes:
        assert hov != base, f"{label}: hover looks like normal"
    script(lua, b, "OnMouseDown")
    pre = look_of(b)
    if hover_changes:
        assert pre != hov, f"{label}: pressed looks like hover"
    script(lua, b, "OnMouseUp")
    assert look_of(b) == hov, f"{label}: release did not return to hover"
    script(lua, b, "OnLeave")
    assert look_of(b) == base, f"{label}: leave did not restore the normal look"
    # the mouse leaving while the button is held down drops both states
    script(lua, b, "OnEnter")
    script(lua, b, "OnMouseDown")
    script(lua, b, "OnLeave")
    assert look_of(b) == base, f"{label}: leaving with the button down kept a look"
    return base, hov, pre


def glyph_px(b, es):
    """The glyph pixels as integer (x, y) from the button's top left, and the button size in pixels."""
    pts = []
    for t in seq(b.glyph):
        if not t._shown:
            continue
        p = t._points[1]
        x, y = float(p.x) * es, -float(p.y) * es
        assert abs(x - round(x)) < 1e-6 and abs(y - round(y)) < 1e-6, f"glyph pixel off the grid: {x}, {y}"
        assert abs(float(t._w) * es - 1) < 1e-6 and abs(float(t._h) * es - 1) < 1e-6, "glyph pixel is not one pixel"
        pts.append((round(x), round(y)))
    return pts, round(float(b._w) * es), round(float(b._h) * es)


def check_the_close_x_and_the_arrows_are_drawn_on_whole_pixels_with_equal_margins_at_every_scale():
    for es, sc in ((1.0, 1.0), (0.64, 1.0), (1.3333333, 1.25), (0.7, 0.8), (1.2, 1.0), (1.5, 1.0), (0.9, 1.0), (1.1, 1.0),
                   (1.75, 1.0), (2.2, 1.0), (1.2, LIVE_SCALE)):
        lua = boot(sc)
        set_display(lua, es, sc)
        P = PS(lua)
        i = make(lua)
        DL(lua).OpenEditor(i)
        c = card(lua)
        assert len(seq(P.Get(i).order)) >= 3
        shapes = [("close", c.close)] + [(f"up{n}", r.up) for n, r in enumerate(rows(lua)) if shown(r.up)] + \
                 [(f"down{n}", r.down) for n, r in enumerate(rows(lua)) if shown(r.down)]
        assert len(shapes) >= 4
        for label, b in shapes:
            pts, bw, bh = glyph_px(b, es)
            assert pts and bw % 2 == 0 and bh % 2 == 0, f"es {es} {label}: button {bw}x{bh}"
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            left, right = min(xs), bw - 1 - max(xs)
            top, bottom = min(ys), bh - 1 - max(ys)
            assert left == right and top == bottom and left >= 1 and top >= 1, \
                f"es {es} sc {sc} {label}: margins l{left} r{right} t{top} b{bottom} in {bw}x{bh}"
            if label == "close":
                assert max(xs) - min(xs) == max(ys) - min(ys), "the X is not square"
                assert len(set(pts)) == len(pts) and (min(xs), min(ys)) in pts and (max(xs), max(ys)) in pts
                assert (min(xs), max(ys)) in pts and (max(xs), min(ys)) in pts, "the X lacks its corners"
            # the label of a glyph button is empty: nothing for font metrics to put off centre
            assert not b.text._text


def check_every_interactive_editor_element_has_hover_pressed_and_disabled_looks_and_restores_exactly():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    live = [("close", c.close)] + [(f"up{n}", r.up) for n, r in enumerate(rows(lua)) if shown(r.up)] + \
           [(f"down{n}", r.down) for n, r in enumerate(rows(lua)) if shown(r.down)] + \
           [("delete", c.delete), ("useGnarly", c.useGnarly)]
    for label, b in live:
        drive(lua, b, label)
    # the armed DELETE has a look of its own, with its own hover
    script(lua, c.delete, "OnClick")
    assert str(c.delete.text._text) == "SURE?"
    armed, armed_hover, _ = drive(lua, c.delete, "armed delete")
    DL(lua).RefreshCard()
    assert look_of(c.delete) == armed, "a repaint changed the armed look"
    DL(lua).CloseEditor()
    DL(lua).OpenEditor(i)
    c = card(lua)
    # USE AS GNARLY PRESET, tied: its own base look, still reacts
    script(lua, c.useGnarly, "OnClick")
    assert P.Gnarly() == i
    on, on_hover, _ = drive(lua, c.useGnarly, "tied useGnarly")
    assert on != look_of_untied(lua, i)
    # disabled: the frame is dimmed and the mouse changes nothing
    run(lua, "__refusal = FS.TotemPresets.Refusal; FS.TotemPresets.Refusal = function() return 'saving is off' end")
    DL(lua).RefreshCard()
    for label, b in [("delete", c.delete), ("useGnarly", c.useGnarly)] + \
            [(f"up{n}", r.up) for n, r in enumerate(rows(lua)) if shown(r.up)]:
        assert float(b._alpha) == 0.4, f"{label} is not dimmed while the presets cannot be saved"
        dis = look_of(b)
        script(lua, b, "OnEnter")
        script(lua, b, "OnMouseDown")
        assert look_of(b) == dis, f"{label}: a disabled button reacted to the mouse"
        script(lua, b, "OnMouseUp")
        script(lua, b, "OnLeave")
    assert float(c.close._alpha) == 1, "the close button is dimmed"
    run(lua, "FS.TotemPresets.Refusal = __refusal")
    DL(lua).RefreshCard()
    assert float(c.delete._alpha) == 1 and float(c.useGnarly._alpha) == 1


def look_of_untied(lua, i):
    P = PS(lua)
    P.SetGnarly(None)
    DL(lua).RefreshCard()
    out = look_of(card(lua).useGnarly)
    P.SetGnarly(i)
    DL(lua).RefreshCard()
    return out


def check_the_name_box_the_pick_cells_and_the_row_light_up_on_hover_and_restore():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    n = c.name
    base = ([rgba(e) for e in seq(c.nameEdges)], rgba(n.fill))
    script(lua, n, "OnEnter")
    script(lua, n, "OnLeave")
    assert ([rgba(e) for e in seq(c.nameEdges)], rgba(n.fill)) == base, "the name box kept its hover look after leaving"
    script(lua, n, "OnEnter")
    hov = ([rgba(e) for e in seq(c.nameEdges)], rgba(n.fill))
    assert hov != base and hov[0][0][3] > base[0][0][3], "the name box has no hover look"
    script(lua, n, "OnEditFocusGained")
    assert rgba(c.nameEdges[1])[3] == 1.0
    script(lua, n, "OnLeave")
    assert rgba(c.nameEdges[1])[3] == 1.0, "leaving dropped the focus look"
    script(lua, n, "OnEditFocusLost")
    assert ([rgba(e) for e in seq(c.nameEdges)], rgba(n.fill)) == base, "the name box did not return to normal"
    # the pick cell: its ring shows on hover, full while pressed, and the row's edge lights with it
    row = rows(lua)[0]
    t = row.tile
    ring0, row0 = [rgba(e) for e in seq(t.hl)], [rgba(e) for e in seq(row.edges)]
    assert ring0[0][3] == 0
    script(lua, t, "OnEnter")
    assert rgba(t.hl[1])[3] == 0.9 and rgba(row.edges[1])[3] > row0[0][3]
    script(lua, t, "OnMouseDown")
    assert rgba(t.hl[1])[3] == 1.0
    script(lua, t, "OnMouseUp")
    script(lua, t, "OnLeave")
    assert [rgba(e) for e in seq(t.hl)] == ring0 and [rgba(e) for e in seq(row.edges)] == row0
    # the chooser tiles
    script(lua, t, "OnClick")
    tile = g(lua).FSTotemChooser.tiles[1]
    ring0 = [rgba(e) for e in seq(tile.hl)]
    script(lua, tile, "OnEnter")
    assert rgba(tile.hl[1])[3] == 0.9
    script(lua, tile, "OnMouseDown")
    assert rgba(tile.hl[1])[3] == 1.0
    script(lua, tile, "OnMouseUp")
    script(lua, tile, "OnLeave")
    assert [rgba(e) for e in seq(tile.hl)] == ring0
    # disabled while the presets cannot be saved
    run(lua, "FS.TotemPresets.Refusal = function() return 'saving is off' end")
    DL(lua).RefreshCard()
    assert float(n._alpha) == 0.4 and float(t._alpha) == 0.4
    script(lua, n, "OnEnter")
    script(lua, t, "OnEnter")
    assert rgba(t.hl[1])[3] == 0, "a disabled cell lit up"
    assert rgba(c.nameEdges[1])[3] == 0.4


def check_the_dial_and_gnarly_cells_light_on_hover_and_restore_in_and_out_of_combat():
    for combat in (False, True):
        lua, a, b = gnarly_world()
        if combat:
            set_combat(lua, True)
        for cell in (btn(lua, "dial"), gb(lua)):
            ring = cell.fsSkin.border.ring
            glow = cell.fsSkin.glow
            base = (rgba(ring), rgba(glow), rgba(cell.fsTint))
            script(lua, cell, "OnEnter")
            hov = (rgba(ring), rgba(glow), rgba(cell.fsTint))
            assert hov != base, f"{cell.fsKey} has no hover look (combat {combat})"
            script(lua, cell, "OnLeave")
            assert (rgba(ring), rgba(glow), rgba(cell.fsTint)) == base, f"{cell.fsKey} did not restore (combat {combat})"


def shift_click(lua, button):
    run(lua, "__shift = true")
    click(lua, button, "LeftButton", True)
    click(lua, button, "LeftButton", False)
    run(lua, "__shift = false")


def check_shift_click_on_an_unset_gnarly_with_room_makes_an_empty_preset_ties_it_and_opens_it():
    lua, a, b = gnarly_world()
    P = PS(lua)
    P.SetGnarly(None)
    assert P.Count() == 2 and int(P.Active()) == a
    shift_click(lua, gb(lua))
    assert P.Count() == 3, "no preset was made"
    assert P.Gnarly() == 3, "the new preset was not tied as the GNARLY preset"
    assert shown(card(lua)) and int(card(lua).fsIndex) == 3, "the editor is not on the new preset"
    assert str(P.Get(3).name) == "NEW" and len(order_of(lua, 3)) == 0, "the new preset is not empty"
    assert int(P.Active()) == a, "making the GNARLY preset moved the dial"
    assert int(P.Tracker("gnarly").presses) == 0 and int(P.Tracker("dial").presses) == 0, "a shift click was counted"
    assert gb(lua)._attrs["type1"] is None, "an empty GNARLY preset left a cast on the cell"
    # a second shift click edits the same preset, it does not make another
    DL(lua).CloseEditor()
    shift_click(lua, gb(lua))
    assert P.Count() == 3 and int(card(lua).fsIndex) == 3


def check_shift_click_on_an_unset_gnarly_leaves_the_dial_on_its_new_slot():
    lua = boot()
    P = PS(lua)
    P.Create()
    P.Select(2)                                # the NEW slot
    assert P.IsNew(P.Active())
    shift_click(lua, gb(lua))
    assert P.Count() == 2 and P.Gnarly() == 2 and int(card(lua).fsIndex) == 2
    assert int(P.Active()) == 3 and P.IsNew(P.Active()), "the dial left its NEW slot"
    # with the last room taken there is no NEW slot left: the dial is on a real preset, as PS.Active clamps it
    DL(lua).CloseEditor()
    P.SetGnarly(None)
    P.Create()
    P.Select(P.Count() + 1)
    P.SetGnarly(None)
    assert P.Count() == 3 and P.IsNew(P.Active())
    P.SetTotem(1, "fire", IDS["Magma Totem"])
    picks = {e: int(TB(lua).CurrentPick(e).id) for e in ("fire", "earth", "water", "air") if TB(lua).CurrentPick(e)}
    assert picks["fire"] != IDS["Magma Totem"]
    serial = int(g(lua).FS.TotemBar.MC.PickSerial())
    run(lua, "__mc.calls = {}")
    shift_click(lua, gb(lua))
    assert P.Count() == 4 and P.Gnarly() == 4 and int(card(lua).fsIndex) == 4
    assert not P.IsNew(P.Active()) and int(P.Active()) == 1
    # a click on GNARLY never rewrites the live totems, whatever slot the dial lands on
    assert {e: int(TB(lua).CurrentPick(e).id) for e in picks} == picks, "the picks were rewritten"
    assert int(g(lua).FS.TotemBar.MC.PickSerial()) == serial and len(seq(g(lua).__mc.calls)) == 0, \
        "a Pick or a set 1 write happened"


def check_making_the_gnarly_preset_leaves_the_dials_step_record_alone():
    lua, a, b = gnarly_world()
    P = PS(lua)
    P.SetGnarly(None)
    P.Tracker("dial").k = 1
    P.Tracker("gnarly").k = 2
    shift_click(lua, gb(lua))
    assert P.Gnarly() == 3
    assert int(P.Tracker("dial").k) == 1, "the dial's step record was reset"
    assert int(P.Tracker("gnarly").k) == 0, "the GNARLY step record was not reset"


def check_a_press_of_an_empty_gnarly_cell_records_nothing():
    lua, a, b = gnarly_world()
    P = PS(lua)
    P.SetGnarly(None)
    assert gb(lua)._attrs["type1"] is None
    run(lua, "__sounds = {}")
    for down in (True, False):
        click(lua, gb(lua), "LeftButton", down)
    run(lua, '__cvars.ActionButtonUseKeyDown = "1"')
    for down in (True, False):
        click(lua, gb(lua), "LeftButton", down)
    assert int(P.Tracker("gnarly").presses) == 0, "an empty cell counted a press"
    assert P.PressAge("gnarly") is None, "an empty cell started the press flash"
    assert len(seq(g(lua).__sounds)) == 0, "an empty cell played the press sound"
    # a cell with a preset still counts it
    P.SetGnarly(b)
    run(lua, '__cvars.ActionButtonUseKeyDown = "0"')
    click(lua, gb(lua), "LeftButton", False)
    assert int(P.Tracker("gnarly").presses) == 1 and P.PressAge("gnarly") is not None


def check_shift_click_on_an_unset_gnarly_with_every_preset_made_opens_the_active_one():
    lua = boot()
    P = PS(lua)
    for _ in range(4):
        P.Create()
    assert P.Count() == 4 and P.Gnarly() is None
    P.Select(2)
    shift_click(lua, gb(lua))
    assert P.Count() == 4, "a fifth preset was made"
    assert shown(card(lua)) and int(card(lua).fsIndex) == 2, "the active preset was not opened"
    assert P.Gnarly() is None and card(lua).useGnarly is not None, "the GNARLY preset was tied without the button"
    script(lua, card(lua).useGnarly, "OnClick")
    assert P.Gnarly() == 2


def check_shift_click_on_a_set_gnarly_opens_its_own_preset_and_makes_nothing():
    lua, a, b = gnarly_world()
    P = PS(lua)
    shift_click(lua, gb(lua))
    assert P.Count() == 2 and P.Gnarly() == b and int(card(lua).fsIndex) == b and int(P.Active()) == a


def check_shift_click_on_an_unset_gnarly_in_combat_is_refused_and_makes_nothing():
    lua, a, b = gnarly_world()
    P = PS(lua)
    P.SetGnarly(None)
    set_combat(lua, True)
    shift_click(lua, gb(lua))
    assert P.Count() == 2 and P.Gnarly() is None, "a preset was made in combat"
    assert card(lua) is None or not shown(card(lua)), "the editor opened in combat"
    assert int(P.Tracker("gnarly").presses) == 0


def set2_ids(*elements):
    return {e: tbh.action_id(tbh.SLOT[e], mc_set=2) for e in elements}


def check_the_gnarly_preset_is_written_into_set_two_once_and_read_back():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__mc.calls = {}")
    P.SetGnarly(b)
    ids = set2_ids("earth", "fire", "water")
    mc = g(lua).__mc
    calls = [(int(c[1]), int(c[2]), bool(c.combat)) for c in seq(mc.calls)]
    wrote = {act: sp for act, sp, _ in calls if act in ids.values()}
    assert wrote == {ids["earth"]: IDS["Tremor Totem"], ids["fire"]: IDS["Magma Totem"],
                     ids["water"]: IDS["Mana Spring Totem"]}, f"set 2 writes {wrote}"
    assert not any(c for _, _, c in calls), "a set 2 write was made in combat"
    assert tbh.action_id(4, mc_set=2) not in wrote, "the air slot was written though the preset leaves it out"
    assert P.Set2.state == "ok" and P.Set2.set1Intact is True
    # nothing is written again for the same element and spell
    run(lua, "__mc.calls = {}")
    TB(lua).Sync()
    TB(lua).Sync()
    again = [int(c[1]) for c in seq(g(lua).__mc.calls) if int(c[1]) in ids.values()]
    assert again == [], f"set 2 was written again: {again}"
    # a different spell for an element is a new attempt
    P.SetTotem(b, "fire", IDS["Searing Totem"])
    again = {int(c[1]): int(c[2]) for c in seq(g(lua).__mc.calls)}
    assert again.get(ids["fire"]) == IDS["Searing Totem"]
    # set 1 follows the dial (the GNARLY preset is also the active one here), so it holds the new fire totem
    assert pick_of(lua, "fire") == "Searing Totem" and pick_of(lua, "earth") == "Tremor Totem"
    line = str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    assert "set2=ok 3/3" in line and "set1Intact=true" in line, line


def slot2(lua, element):
    return g(lua).__mc.slots[tbh.action_id(tbh.SLOT[element], mc_set=2)]


def check_a_spell_that_comes_back_is_written_to_set_two_again():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetGnarly(b)
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"]
    P.SetTotem(b, "fire", IDS["Searing Totem"])
    assert int(slot2(lua, "fire")) == IDS["Searing Totem"]
    P.SetTotem(b, "fire", IDS["Magma Totem"])
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"], "Magma, Searing, Magma left the slot on Searing"
    assert P.Set2.state == "ok"


def check_a_set_two_send_that_has_not_shown_is_looked_at_again_and_sent_again_a_few_times():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    ids = set(set2_ids("earth", "fire", "water").values())

    def sends():
        return [int(c[1]) for c in seq(g(lua).__mc.calls) if int(c[1]) in ids]

    run(lua, "__mc.delay = true")
    P.SetGnarly(b)
    assert P.Set2.state == "partial" and len(sends()) == 3
    # the slot updates late: the scheduled look sees it with no Sync from outside
    run(lua, "__mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state == "ok", "the late update was not noticed by the scheduled look"
    assert "set2=ok 3/3" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a slot that never takes the spell is sent again after each settle time, at most SET2_ATTEMPTS times
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__mc.delay = true")
    P.SetGnarly(b)
    first = len(sends())
    TB(lua).Sync()
    assert len(sends()) == first, "sent again before the settle time passed"
    for _ in range(6):
        advance(lua, 1.2)
    assert len(sends()) == 3 * int(P.P.SET2_ATTEMPTS), f"{len(sends())} sends"
    assert P.Set2.state == "partial"


def check_set_one_is_watched_until_a_set_two_send_is_judged_and_the_line_says_which_check_ran():
    def world():
        lua = boot()
        P = PS(lua)
        a, b = two_presets(lua)
        P.Select(a)                            # set 1 holds MELEE: Searing, Stoneskin, Healing Stream, Grounding
        run(lua, "__mc.delay = true")
        P.SetGnarly(b)                         # set 2 sends queue: Magma, Tremor, Mana Spring
        return lua, P

    id1 = tbh.action_id(tbh.SLOT["fire"])
    # the late update also reaches set 1: caught by the look that judges the sends, put back, set 2 dead
    lua, P = world()
    assert "set1Check=bracket" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    run(lua, f"__mc.slots[{id1}] = __ids['Magma Totem']; __mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state == "dead" and P.Set2.set1Intact is False and "set 1" in str(P.Set2.why)
    run(lua, "__mc_flush()")
    assert int(g(lua).__mc.slots[id1]) == IDS["Searing Totem"], "set 1 was not put back"
    assert "set1Intact=false" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a set 1 change that is not the spell sent to set 2 is the player's, not a bleed
    lua, P = world()
    run(lua, f"__mc.slots[{id1}] = __ids['Flametongue Totem']; __mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state == "ok" and P.Set2.set1Intact is True
    # once judged, the window is closed: a later change to the same spell is not blamed
    run(lua, f"__mc.slots[{id1}] = __ids['Magma Totem']")
    TB(lua).Sync()
    assert P.Set2.state != "dead" and P.Set2.check == "none"


def check_a_pick_of_the_gnarly_totem_inside_the_window_is_the_players_and_is_never_put_back():
    id1 = tbh.action_id(tbh.SLOT["fire"])

    def world():
        lua = boot()
        P = PS(lua)
        a, b = two_presets(lua)
        P.Select(a)
        run(lua, "__mc.delay = true")
        P.SetGnarly(b)                         # sends queue: Magma, Tremor, Mana Spring; window open
        return lua, P, a, b

    # a preset switch in the same second picks the GNARLY totem onto set 1
    lua, P, a, b = world()
    P.Select(b)
    run(lua, "__mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state != "dead" and P.Set2.set1Intact is True, "a preset switch was blamed as a bleed"
    assert int(g(lua).__mc.slots[id1]) == IDS["Magma Totem"], "the player's pick was put back"
    # a pick from the tab's picker does the same
    lua, P, a, b = world()
    TB(lua).Pick("fire", IDS["Magma Totem"])
    run(lua, "__mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state != "dead" and P.Set2.set1Intact is True, "a manual pick was blamed as a bleed"
    assert int(g(lua).__mc.slots[id1]) == IDS["Magma Totem"], "the manual pick was put back"
    # a set 1 slot that changes to what the active preset wants is not restored, only left unproven
    lua, P, a, b = world()
    run(lua, "FS.TotemPresets.Active = function() return %d end" % b)
    run(lua, f"__mc.slots[{id1}] = __ids['Magma Totem']; __mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state != "dead" and P.Set2.set1Intact is True
    assert int(g(lua).__mc.slots[id1]) == IDS["Magma Totem"], "a slot the active preset wants was put back"
    assert int(P.Set2.unproven) >= 1


def check_a_set_two_slot_is_written_only_when_it_reads_back_holding_nothing_or_an_element_totem():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    earth2 = tbh.action_id(tbh.SLOT["earth"], mc_set=2)
    fire2 = tbh.action_id(tbh.SLOT["fire"], mc_set=2)
    run(lua, f"__mc.slots[{earth2}] = 999999")                 # not a totem of the element
    run(lua, f"__mc.slots[{fire2}] = __ids['Searing Totem']")   # another totem of the element: replaced
    P.SetGnarly(b)
    assert int(g(lua).__mc.slots[earth2]) == 999999, "a slot holding something else was overwritten"
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"]
    assert P.Set2.state == "partial" and int(P.Set2.unproven) == 1
    assert "unproven=1" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a set 2 slot that cannot be read is not written either
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, f"local base = GetActionInfo; GetActionInfo = function(id) if id == {earth2} then return __SECRET end "
             "return base(id) end")
    run(lua, "__mc.calls = {}")
    P.SetGnarly(b)
    assert earth2 not in [int(c[1]) for c in seq(g(lua).__mc.calls)], "an unreadable set 2 slot was written"
    assert int(P.Set2.unproven) == 1 and P.Set2.state == "partial"


def check_set_two_raising_inside_the_refresh_is_caught_and_the_state_is_still_saved():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetGnarly(b)
    run(lua, "FS.TotemBar.MC.Bar = function() error('boom') end")
    DL(lua).Refresh()
    assert P.Set2.state == "dead" and "raised" in str(P.Set2.why)
    assert "set2=dead" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line), "the state was not saved after the raise"


def check_a_press_is_used_up_by_the_cast_it_brought_and_a_reset_forgets_it():
    lua = boot()
    P = PS(lua)
    make(lua)
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("dial")[0] == 1
    cast_raw(lua, "Searing Totem")
    assert P.Progress("dial")[0] == 1, "one press advanced the record twice"
    # a reset (combat end) forgets a press that was still waiting for its cast
    lua = boot()
    P = PS(lua)
    make(lua)
    click(lua, dial(lua), "LeftButton", False)
    enter_combat(lua)
    leave_combat(lua)
    cast_raw(lua, "Stoneskin Totem")
    assert P.Progress("dial")[0] == 0, "a press from before the reset counted for a later cast"


def check_the_ticker_repaints_only_the_cell_that_is_waiting_or_flashing():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetGnarly(b)
    P.Select(a)
    advance(lua, 3)                              # the applied flash is over
    for _ in range(3):
        tick(lua, 0.2)
    run(lua, "__sp = { dial = 0, gnarly = 0 }; local f = FS.TotemDial.StateOf; "
             "FS.TotemDial.StateOf = function(k, ...) __sp[k] = (__sp[k] or 0) + 1 return f(k, ...) end")

    def painted():
        return int(g(lua).__sp.dial), int(g(lua).__sp.gnarly)

    for _ in range(5):
        advance(lua, 0.1)
        tick(lua, 0.1)
    assert painted() == (0, 0), f"an idle tick repainted {painted()}"
    enter_combat(lua)
    P.Select(b)                                  # queued: the dial waits
    run(lua, "__sp = { dial = 0, gnarly = 0 }")
    for _ in range(5):
        advance(lua, 0.1)
        tick(lua, 0.1)
    d, gn = painted()
    assert d >= 5 and gn == 0, f"a waiting dial repainted dial={d} gnarly={gn}"
    leave_combat(lua)
    advance(lua, 5)
    for _ in range(3):
        tick(lua, 0.2)
    click(lua, btn(lua, "gnarly"), "LeftButton", False)      # a press: the GNARLY cell flashes
    run(lua, "__sp = { dial = 0, gnarly = 0 }")
    tick(lua, 0.1)
    d, gn = painted()
    assert gn >= 1 and d == 0, f"a flashing GNARLY cell repainted dial={d} gnarly={gn}"


def check_set_two_waits_for_what_it_needs_and_never_writes_in_combat():
    # setting off, no GNARLY, the cell off
    for how in ("gnarlySet2", "gnarly"):
        lua = boot()
        P = PS(lua)
        a, b = two_presets(lua)
        conf(lua, f"totems.{how}", False)
        run(lua, "__mc.calls = {}")
        P.SetGnarly(b)
        ids = set(set2_ids("earth", "fire", "water", "air").values())
        assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids], f"{how} off still wrote set 2"
        assert P.Set2.state == "off"
    # Call of the Ancestors not known: nothing is written, and it is tried again once it is
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, '__learned[__spells["Call of the Ancestors"]] = nil')
    run(lua, "__mc.calls = {}")
    P.SetGnarly(b)
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids] and P.Set2.state == "wait"
    run(lua, '__learned[__spells["Call of the Ancestors"]] = true')
    TB(lua).Sync()
    assert [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids] and P.Set2.state == "ok"
    # in combat the call is never made
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetGnarly(b)
    run(lua, "__mc.calls = {}; __mc.slots = {}")
    P.Set2.sent = {}
    set_combat(lua, True)
    P.SyncSet2()
    DL(lua).Refresh()
    assert len(seq(g(lua).__mc.calls)) == 0, "SetMultiCastSpell was called in combat"


def check_set_two_is_given_up_when_the_set_one_slot_does_not_map_or_changes():
    # the native button disagrees with the formula: nothing is written at all
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__native(500)")
    run(lua, "__mc.calls = {}")
    P.SetGnarly(b)
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids], "set 2 was written on an unproven mapping"
    assert P.Set2.state == "dead" and "map" in str(P.Set2.why)
    assert "set2=dead" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a write that lands on set 1 as well: set 1 is put back and set 2 is dead for the session
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.Select(a)
    run(lua, "local base = SetMultiCastSpell\n"
             "SetMultiCastSpell = function(act, sp) base(act, sp); if act > (%d - 1) * 12 + 4 then base(act - 4, sp) end end" % tbh.BAR)
    P.SetGnarly(b)
    assert P.Set2.state == "dead" and P.Set2.set1Intact is False, f"{P.Set2.state} {P.Set2.set1Intact}"
    assert pick_of(lua, "fire") == "Searing Totem" and pick_of(lua, "earth") == "Stoneskin Totem", \
        "set 1 was left changed"
    held = g(lua).__mc.slots[tbh.action_id(tbh.SLOT["fire"])]
    assert int(held) == IDS["Searing Totem"], "the set 1 slot was not restored"
    run(lua, "__mc.calls = {}")
    P.SetTotem(b, "fire", IDS["Flametongue Totem"])
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids], "set 2 was tried again after it died"
    line = str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    assert "set2=dead" in line and "set1Intact=false" in line, line


def check_a_set_two_call_that_raises_or_does_not_land_never_breaks_the_tab():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__mc.throws = false; local base = SetMultiCastSpell\n"
             "SetMultiCastSpell = function(act, sp) if act > (%d - 1) * 12 + 4 then error('boom') end return base(act, sp) end" % tbh.BAR)
    P.SetGnarly(b)
    TB(lua).Sync()
    assert P.Set2.state in ("partial", "ok", "off", "wait"), P.Set2.state
    assert P.Set2.state != "ok"
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__mc.delay = true")
    P.SetGnarly(b)
    assert P.Set2.state == "partial", "a write that has not shown yet should read as partial"
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    sent = [int(c[1]) for c in seq(g(lua).__mc.calls) if int(c[1]) in ids]
    TB(lua).Sync()
    TB(lua).Sync()
    assert [int(c[1]) for c in seq(g(lua).__mc.calls) if int(c[1]) in ids] == sent, \
        "a set 2 write that has not landed was sent again (one attempt per element and spell)"
    run(lua, "__mc_flush()")
    TB(lua).Sync()
    assert P.Set2.state == "ok", "the late slot update was not seen"
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    run(lua, "__mc.infoMode = 'secret'")
    P.SetGnarly(b)
    assert P.Set2.state == "wait", "unreadable slots must write nothing"


# ---------------------------------------------------------------------------------------------
# Checks: the state line and hygiene
# ---------------------------------------------------------------------------------------------


def check_the_state_line_names_the_live_unknowns():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    click(lua, dial(lua), "LeftButton", False)
    cast_name(lua, "Stoneskin Totem")
    P.SaveState()
    st = g(lua).ForeverSTUwaveDB.totemPresetState
    line = str(st.line)
    for part in ("presets=1", "active=1", "pending=nil", "dial type1=macro", "step=1/4", "presses=2", "casts=1",
                 "gnarly type1=none"):
        assert part in line, f"{part!r} not in {line!r}"
    assert int(st.active) == 1
    assert int(re.search(r"script=(\d+)", line).group(1)) == len(text_of(lua, i))


def check_the_state_line_never_creates_a_database_never_writes_a_read_only_config_and_survives_a_throwing_one():
    lua = boot()
    make(lua)
    run(lua, "ForeverSTUwaveDB = nil")
    PS(lua).SaveState()
    assert g(lua).ForeverSTUwaveDB is None, "the state line created the database"
    lua = boot()
    make(lua)
    run(lua, "ForeverSTUwaveDB.totemPresetState = nil; FS.Config.IsReadOnly = function() return true end")
    PS(lua).SaveState()
    assert g(lua).ForeverSTUwaveDB.totemPresetState is None, "the state line wrote a read-only profile"
    lua = boot()
    make(lua)
    run(lua, "ForeverSTUwaveDB = setmetatable({}, { __newindex = function() error('refused') end })")
    PS(lua).SaveState()


def check_a_throwing_listener_or_totem_api_never_breaks_a_press_or_a_sync():
    lua = boot()
    P = PS(lua)
    make(lua)
    run(lua, "FS.TotemPresets.OnEvent(function() error('boom') end)")
    click(lua, dial(lua), "LeftButton", False)
    cast_name(lua, "Stoneskin Totem")
    P.Select(1)
    run(lua, "FS.TotemDial.Refresh = function() error('boom') end")
    TB(lua).Sync()
    fire(lua, "SPELLS_CHANGED")


def check_the_files_use_no_snippets_no_state_drivers_and_no_flagged_words():
    for path in (PRESETS, DIAL, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text, f"{path.name}: an em or en dash"
        if path != Path(__file__):
            code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("--"))
            for needle in ("RegisterStateDriver", "SecureHandler", "WrapScript", ":Execute(", "SetFrameRef"):
                assert needle not in code, f"{path.name} mentions {needle}"
            for word in ("bot", "automat", "macro", "cheat", "hack", "probe", "monitor"):
                for ln in text.splitlines():
                    low = ln.lower()
                    if word == "macro" and ('"macro"' in low or "macrotext" in low or "/castsequence" in low):
                        continue
                    assert not re.search(r"\b" + word, low) or word == "bot" and not re.search(r"\bbot\b", low), \
                        f"{path.name}: flagged word {word!r} in: {ln.strip()}"


LIVE_SCALE = 0.8333     # Parker's layout scale; with effective scale 0.64 and physical height 1440 one UI unit is 1.2 pixels


def set_display(lua, ppu, scale):
    """The physical pixels in one UI unit, built the way the client has it: an effective scale and a physical screen height
    (one UI unit is effective scale * physical height / 768 pixels). Parker's real display is effective scale 0.64 with
    physical height 1440 (1.2 pixels at layout scale 0.8333); every other count here uses the same effective scale and the
    height that gives it, so a test that took the effective scale for the pixel count would see 0.64."""
    if ppu == 1.2 and scale == LIVE_SCALE:
        run(lua, "__es = 1; __ees = 0.64; __physH = 1440")
    else:
        run(lua, f"__es = 1; __ees = 0.64; __physH = {ppu * 768 / 0.64!r}")


def live_click(lua, b):
    """A click as the client delivers it: a disabled button gets none."""
    if getattr(b, "_enabled", None) is not False:
        click(lua, b)


def errors(lua):
    e = g(lua).__errors
    return [str(e[k]) for k in range(1, len(e) + 1)] if e is not None else []


def lock_presets(lua, on=True):
    if on:
        run(lua, "__refusal = FS.TotemPresets.Refusal; FS.TotemPresets.Refusal = function() return 'saving is off' end")
    else:
        run(lua, "FS.TotemPresets.Refusal = __refusal")


def check_a_dimmed_pick_cell_and_the_other_dimmed_controls_take_no_clicks_and_say_why():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    t = rows(lua)[0].tile
    before = (str(c.name._text), P.Get(i).name)
    lock_presets(lua)
    DL(lua).RefreshCard()
    assert float(t._alpha) == 0.4 and t._enabled is False, "the dimmed pick cell is still enabled"
    for label, b in [("pick cell", t), ("delete", c.delete), ("useGnarly", c.useGnarly)] + \
            [(f"up{n}", r.up) for n, r in enumerate(rows(lua)) if shown(r.up)] + \
            [(f"down{n}", r.down) for n, r in enumerate(rows(lua)) if shown(r.down)]:
        assert b._enabled is False, f"{label} was left enabled while the presets cannot be saved"
    assert c.name._enabled is False, "the name box was left enabled"
    run(lua, "__errors = {}")
    live_click(lua, t)
    chooser = g(lua).FSTotemChooser
    assert chooser is None or not shown(chooser), "a dimmed pick cell opened the chooser"
    assert errors(lua) == [], "a click the client would drop said something"
    # a click that does arrive (the engine drops none here, but a script can call it) is refused with the reason
    click(lua, t)
    chooser = g(lua).FSTotemChooser
    assert chooser is None or not shown(chooser), "the pick cell opened the chooser while the presets cannot be saved"
    assert errors(lua) == ["saving is off"], errors(lua)
    for b in (c.delete, c.useGnarly):
        live_click(lua, b)
    assert shown(c) and P.Get(i) is not None and P.Gnarly() is None, "a dimmed footer button acted"
    # the chooser open when the refusal begins: its tiles dim, drop clicks, and a click that arrives says why
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    assert t._enabled is not False and float(t._alpha) == 1
    live_click(lua, t)
    chooser = g(lua).FSTotemChooser
    assert shown(chooser)
    tile = chooser.tiles[1]
    other = chooser.tiles[2]
    assert tile._enabled is not False
    lock_presets(lua)
    DL(lua).RefreshCard()
    assert float(tile._alpha) == 0.4 and tile._enabled is False and other._enabled is False, "the chooser tiles stayed live"
    run(lua, "__errors = {}")
    picks = dict(P.Get(i).picks)
    click(lua, other)
    assert errors(lua) == ["saving is off"], f"a chooser tile click was silent: {errors(lua)}"
    assert dict(P.Get(i).picks) == picks and shown(chooser), "a refused chooser click still changed the pick or closed the chooser"
    # a refusal from the store itself is told too
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    run(lua, "__errors = {}; __sp = FS.TotemPresets.SetTotem; FS.TotemPresets.SetTotem = function() return false, 'no such totem' end")
    click(lua, other)
    assert errors(lua) == ["no such totem"], errors(lua)
    run(lua, "FS.TotemPresets.SetTotem = __sp")
    assert float(tile._alpha) == 1 and tile._enabled is not False, "the chooser tiles stayed dimmed after the refusal cleared"


def check_an_open_card_unlocks_when_the_refusal_clears_and_locks_when_it_begins():
    lua = boot()
    i = make(lua)
    lock_presets(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    t = rows(lua)[0].tile
    assert float(c.delete._alpha) == 0.4 and t._enabled is False and c.name._enabled is False
    lock_presets(lua, False)
    tick(lua)
    assert float(c.delete._alpha) == 1 and t._enabled is not False and c.name._enabled is not False and float(t._alpha) == 1, \
        "the open card stayed locked after the refusal cleared"
    lock_presets(lua)
    tick(lua)
    assert float(c.delete._alpha) == 0.4 and t._enabled is False and c.name._enabled is False, "the open card did not lock"
    # a hidden card is not refreshed by the ticker
    DL(lua).CloseEditor()
    run(lua, "__rc = 0; local f = FS.TotemDial.RefreshCard; FS.TotemDial.RefreshCard = function(...) __rc = __rc + 1 return f(...) end")
    lock_presets(lua, False)
    tick(lua)
    assert int(g(lua).__rc) == 0, "the ticker refreshed a hidden card"


def check_the_name_box_drops_its_hover_look_when_the_card_hides():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    base = ([rgba(e) for e in seq(c.nameEdges)], rgba(c.name.fill))
    script(lua, c.name, "OnEnter")
    assert ([rgba(e) for e in seq(c.nameEdges)], rgba(c.name.fill)) != base
    DL(lua).CloseEditor()
    script(lua, c.name, "OnHide")       # the mock does not pass a parent's hide down to its children
    assert not c.name.fsHover, "the name box kept fsHover across a hide"
    assert ([rgba(e) for e in seq(c.nameEdges)], rgba(c.name.fill)) == base, "the name box kept its hover look across a hide"


def check_leaving_a_pick_cell_with_the_button_down_drops_the_pressed_look():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    row = rows(lua)[0]
    t = row.tile
    ring0, row0 = [rgba(e) for e in seq(t.hl)], [rgba(e) for e in seq(row.edges)]
    script(lua, t, "OnEnter")
    script(lua, t, "OnMouseDown")
    assert rgba(t.hl[1])[3] == 1.0
    script(lua, t, "OnLeave")
    assert not t.fsPressed and not t.fsHover
    assert [rgba(e) for e in seq(t.hl)] == ring0 and [rgba(e) for e in seq(row.edges)] == row0, "leaving with the button down kept a look"
    script(lua, t, "OnClick")
    tile = g(lua).FSTotemChooser.tiles[1]
    ring0 = [rgba(e) for e in seq(tile.hl)]
    script(lua, tile, "OnEnter")
    script(lua, tile, "OnMouseDown")
    script(lua, tile, "OnLeave")
    assert not tile.fsPressed and not tile.fsHover
    assert [rgba(e) for e in seq(tile.hl)] == ring0, "the chooser tile kept its pressed look after the mouse left"
    # hiding the chooser or the card drops both states too
    script(lua, tile, "OnEnter")
    script(lua, tile, "OnMouseDown")
    DL(lua).CloseEditor()
    script(lua, tile, "OnHide")
    assert not tile.fsPressed and not tile.fsHover


def check_a_disabled_row_does_not_light_its_edge_and_every_editor_texture_is_pixel_snapped():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    row = rows(lua)[0]
    base = [rgba(e) for e in seq(row.edges)]
    lock_presets(lua)
    DL(lua).RefreshCard()
    dim = [rgba(e) for e in seq(row.edges)]
    script(lua, row.tile, "OnEnter")
    assert [rgba(e) for e in seq(row.edges)] == dim, "a disabled row lit its edge on hover"
    script(lua, row.tile, "OnLeave")
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    script(lua, row.tile, "OnEnter")
    assert [rgba(e) for e in seq(row.edges)] != base, "a live row does not light its edge on hover"
    script(lua, row.tile, "OnLeave")
    # every edge and glyph texture of the editor is snapped to the pixel grid, bias 0
    c = card(lua)
    script(lua, row.tile, "OnClick")
    chooser = g(lua).FSTotemChooser
    groups = [c.edges, c.nameEdges, c.close.edges, c.close.glyph, c.delete.edges, c.useGnarly.edges, row.edges, row.tile.hl,
              row.up.edges, row.up.glyph, chooser.edges, chooser.tiles[1].hl]
    for group in groups:
        assert len(seq(group)) > 0
        for t in seq(group):
            assert t._snap is True and float(t._bias) == 0, "an editor texture is not snapped to the pixel grid"


def check_ticks_with_an_unchanged_refusal_never_refresh_the_open_card():
    for locked in (False, True):
        lua = boot()
        i = make(lua)
        if locked:
            lock_presets(lua)
        DL(lua).OpenEditor(i)
        c = card(lua)
        assert c.fsLocked is locked, "the card does not remember its lock state"
        run(lua, "__rc = 0; local f = FS.TotemDial.RefreshCard; FS.TotemDial.RefreshCard = function(...) __rc = __rc + 1 return f(...) end")
        c.name._text = "TYPING"
        for _ in range(5):
            tick(lua)
        assert int(g(lua).__rc) == 0, f"the ticker refreshed an open card whose refusal had not changed (locked {locked})"
        assert c.name._text == "TYPING", "a tick wiped the name box while typing"


def check_a_chooser_reopened_after_the_refusal_cleared_has_live_tiles():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    row = rows(lua)[0]
    live_click(lua, row.tile)
    chooser = g(lua).FSTotemChooser
    assert shown(chooser)
    lock_presets(lua)
    DL(lua).RefreshCard()
    tiles = [chooser.tiles[k] for k in range(1, len(seq(chooser.tiles)) + 1) if shown(chooser.tiles[k])]
    assert tiles and all(t._enabled is False and float(t._alpha) == 0.4 for t in tiles)
    run(lua, "FS.TotemDial.Chooser():Hide()")
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    live_click(lua, row.tile)
    assert shown(chooser)
    tiles = [chooser.tiles[k] for k in range(1, len(seq(chooser.tiles)) + 1) if shown(chooser.tiles[k])]
    assert tiles
    for t in tiles:
        assert t._enabled is not False and not t.fsDisabled, "a reopened chooser kept a tile disabled"
        assert float(t._alpha) == 1, "a reopened chooser kept a tile dimmed"
    picks = dict(PS(lua).Get(i).picks)
    click(lua, tiles[-1])
    assert not shown(chooser) and dict(PS(lua).Get(i).picks) != picks, "a reopened chooser tile did not take the click"


CHECKS = [
    check_toc_lists_the_preset_files_after_the_totem_bar_and_bindings_declare_the_dial,
    check_the_settings_have_their_keys_defaults_tips_and_registered_defaults,
    check_only_a_shaman_gets_a_dial_and_a_world_without_the_files_keeps_six_buttons,
    check_no_presets_is_one_new_slot_and_create_copies_the_four_buttons,
    check_four_presets_at_most_and_the_new_slot_goes_when_there_are_four,
    check_names_are_letters_digits_and_spaces_up_to_eight_uppercased,
    check_a_saved_file_is_sanitised_when_it_loads,
    check_presets_are_kept_per_character,
    check_a_read_only_config_or_no_database_keeps_the_presets_in_memory_and_refuses_edits,
    check_filling_leaving_out_and_moving_a_preset,
    check_every_edit_is_refused_in_combat_and_the_editor_will_not_open,
    check_deleting_shifts_the_active_slot_and_clears_a_pending_switch,
    check_editing_the_active_preset_picks_its_totems_on_the_buttons,
    check_an_element_a_preset_leaves_out_keeps_its_pick,
    check_a_switch_picks_only_the_buttons_that_would_change,
    check_a_totem_not_learned_yet_is_skipped_and_stays_locked,
    check_right_click_and_the_wheel_cycle_through_the_new_slot_each_on_its_own_setting,
    check_a_switch_in_combat_is_queued_and_applies_at_regen,
    check_a_failing_preset_hook_never_stops_the_totem_tab_from_catching_up_at_regen,
    check_a_slot_that_vanished_while_a_switch_waited_is_dropped_at_regen,
    check_the_script_behind_the_click_is_a_cast_sequence_that_restarts_with_combat_and_idle,
    check_a_secret_number_from_the_wheel_or_the_clock_is_ignored,
    check_the_dial_carries_the_script_as_secure_attributes_written_out_of_combat_only,
    check_a_press_counts_on_the_event_the_game_acts_on,
    check_the_record_advances_on_the_next_totem_cast_and_ignores_the_rest,
    check_the_record_starts_over_at_combat_end_after_six_idle_seconds_and_on_any_edit,
    check_a_secret_spell_id_is_noted_and_never_breaks_the_record,
    check_the_ring_has_one_arc_per_totem_tinted_by_its_element,
    check_the_digit_the_plus_and_the_dashed_empty_ring,
    check_a_locked_totem_is_a_dashed_muted_arc_and_the_step_skips_it,
    check_while_stepping_done_arcs_glow_the_next_is_thick_and_the_icon_replaces_the_digit,
    check_the_name_plate_and_the_raised_plate,
    check_the_pending_look_marks_the_dial_and_the_buttons_that_will_change,
    check_the_applied_flash_marks_the_changed_buttons_for_a_moment_and_has_its_own_switch,
    check_the_waiting_pulse_breathes_the_amber_and_stops_with_its_setting,
    check_the_sound_cues_play_only_with_their_setting_on_and_only_when_something_happened,
    check_the_tooltip_lists_the_totems_in_order_the_left_out_ones_and_the_hints,
    check_the_tooltip_names_a_locked_totem_with_its_level_the_new_slot_and_a_pending_switch,
    check_shift_click_on_the_new_slot_makes_a_preset_and_opens_the_editor_on_it,
    check_the_editor_rows_the_chooser_and_the_up_down_buttons,
    check_the_name_box_commits_on_enter_and_on_losing_focus_and_cleans_the_name,
    check_delete_asks_twice_and_the_confirmation_runs_out,
    check_the_card_closes_on_escape_and_combat_and_hangs_on_the_last_cell,
    check_no_secure_frame_is_anchored_to_the_card_or_its_pieces,
    check_the_dial_switch_pressed_in_combat_waits_for_regen,
    check_a_resize_hides_the_art_of_the_old_width,
    check_edit_clicks_in_every_modifier_combination_never_drop_a_totem,
    check_the_dial_tip_says_a_shift_keybind_edits,
    check_a_character_key_that_cannot_be_read_never_saves_under_a_made_up_one,
    check_an_unreadable_character_key_with_a_database_that_cannot_save_keeps_the_session_refusal,
    check_the_known_totems_are_scanned_once_per_event_not_once_per_repaint,
    check_a_totem_learned_during_the_fight_is_picked_by_the_switch_that_waited,
    check_the_cells_stand_right_of_the_six_and_the_buttons_keep_their_slots,
    check_a_rescale_resizes_and_reseats_the_face,
    check_the_gnarly_cell_carries_its_own_preset_whatever_the_dial_is_doing,
    check_gnarly_is_set_unset_edited_and_shifted_by_a_delete,
    check_the_gnarly_cell_looks_pink_with_a_bang_and_its_own_plate,
    check_two_cells_with_the_same_first_totem_count_a_cast_for_the_one_pressed,
    check_the_press_flash_and_sound_belong_to_the_gnarly_cell_and_have_their_own_switches,
    check_the_gnarly_tooltip_and_the_unset_tooltip,
    check_use_as_gnarly_preset_in_the_editor_ties_and_unties_and_shift_click_edits_it,
    check_the_editor_buttons_that_size_to_their_text_are_padded_symmetrically_and_snapped_to_whole_pixels,
    check_the_close_x_and_the_arrows_are_drawn_on_whole_pixels_with_equal_margins_at_every_scale,
    check_every_interactive_editor_element_has_hover_pressed_and_disabled_looks_and_restores_exactly,
    check_the_name_box_the_pick_cells_and_the_row_light_up_on_hover_and_restore,
    check_the_dial_and_gnarly_cells_light_on_hover_and_restore_in_and_out_of_combat,
    check_shift_click_on_an_unset_gnarly_with_room_makes_an_empty_preset_ties_it_and_opens_it,
    check_shift_click_on_an_unset_gnarly_leaves_the_dial_on_its_new_slot,
    check_making_the_gnarly_preset_leaves_the_dials_step_record_alone,
    check_a_press_of_an_empty_gnarly_cell_records_nothing,
    check_shift_click_on_an_unset_gnarly_with_every_preset_made_opens_the_active_one,
    check_shift_click_on_a_set_gnarly_opens_its_own_preset_and_makes_nothing,
    check_shift_click_on_an_unset_gnarly_in_combat_is_refused_and_makes_nothing,
    check_the_gnarly_preset_is_written_into_set_two_once_and_read_back,
    check_a_spell_that_comes_back_is_written_to_set_two_again,
    check_a_set_two_send_that_has_not_shown_is_looked_at_again_and_sent_again_a_few_times,
    check_set_one_is_watched_until_a_set_two_send_is_judged_and_the_line_says_which_check_ran,
    check_a_pick_of_the_gnarly_totem_inside_the_window_is_the_players_and_is_never_put_back,
    check_a_set_two_slot_is_written_only_when_it_reads_back_holding_nothing_or_an_element_totem,
    check_set_two_raising_inside_the_refresh_is_caught_and_the_state_is_still_saved,
    check_a_press_is_used_up_by_the_cast_it_brought_and_a_reset_forgets_it,
    check_the_ticker_repaints_only_the_cell_that_is_waiting_or_flashing,
    check_set_two_waits_for_what_it_needs_and_never_writes_in_combat,
    check_set_two_is_given_up_when_the_set_one_slot_does_not_map_or_changes,
    check_a_set_two_call_that_raises_or_does_not_land_never_breaks_the_tab,
    check_the_state_line_names_the_live_unknowns,
    check_the_state_line_never_creates_a_database_never_writes_a_read_only_config_and_survives_a_throwing_one,
    check_a_throwing_listener_or_totem_api_never_breaks_a_press_or_a_sync,
    check_a_dimmed_pick_cell_and_the_other_dimmed_controls_take_no_clicks_and_say_why,
    check_an_open_card_unlocks_when_the_refusal_clears_and_locks_when_it_begins,
    check_the_name_box_drops_its_hover_look_when_the_card_hides,
    check_ticks_with_an_unchanged_refusal_never_refresh_the_open_card,
    check_a_chooser_reopened_after_the_refusal_cleared_has_live_tiles,
    check_leaving_a_pick_cell_with_the_button_down_drops_the_pressed_look,
    check_a_disabled_row_does_not_light_its_edge_and_every_editor_texture_is_pixel_snapped,
    check_the_files_use_no_snippets_no_state_drivers_and_no_flagged_words,
]

SCALED_CHECKS = [
    check_the_tab_grows_by_one_cell_and_the_buff_and_five_second_tabs_follow,
]


def main() -> int:
    failed = total = 0

    def run_check(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError, ValueError) as err:
            failed += 1
            where = traceback.extract_tb(err.__traceback__)[-1]
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      ")
                  + f"\n      at line {where.lineno}: {where.line}")

    for fn in CHECKS:
        run_check(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run_check(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
