#!/usr/bin/env python3
"""Runs the real TotemPresets.lua and TotemDial.lua (the Shaman totem presets: two preset cells on the totem tab) headless,
in totembar-harness's world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua,
PetActionBar.lua, PetDock.lua, ClassShoulder.lua, TotemPiece.lua, TotemBar.lua, the buff tab, the mana regen tab.

The look is the two preset design mockup. The numbers and states below are read from the mockup's
description in TotemDial.lua; the live unknowns (a secure cast sequence stepping totems, the spell id of a cast being
plain) are modelled, never claimed. Checked:

  * the data: exactly two preset slots per character saved under the character, each with an outline colour (a cell
    setting, kept when a preset is cleared), names cleaned, a saved file sanitised on load, the old list-and-active-and-
    GNARLY file migrated once into the two slots with the extra presets kept in `retired`, a read-only Config or a
    missing database keeping the presets in memory;
  * the step: the script behind the click (`/castsequence reset=combat/6 ...`, a plain cast for one totem, the locked
    totems left out), written out of combat only; the record the cell draws advances on a matching cast, counts a press
    on the event the game acts on, and starts over at combat end, after six seconds idle, and on any edit;
  * the face: arcs per totem tinted by element, the locked dashed arc, done and next looks, the number and the "+", the
    name plate, the outline colour on the border, glow, underline and plate, hover and pressed looks, the unset look;
  * the tooltips, the editor card (rows, chooser, up and down, name, outline swatches, two step CLEAR), the seats (the
    tab grows by up to two cells, the buff tab and the mana regen tab follow), the state line and its guards;
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
VIOLET = (0.659, 0.333, 0.969)
ROW_FILL = (0.051, 0.024, 0.125)       # the face colour of the editor's buttons and rows


def mix3(a, b, t):
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))

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


def c1(lua):
    return g(lua).FSTotemButton7


def c2(lua):
    return g(lua).FSTotemButton8


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


def make(lua, picks=None, order=None, name=None, slot=None):
    """Makes a preset (a copy of the four buttons, then edited) in `slot`, by default the first unset one; returns the slot.
    picks: {element: totem name or None}."""
    P = PS(lua)
    if slot is None:
        slot = 1 if P.Get(1) is None else 2
    index = P.Create(slot)
    assert index == slot, f"Create({slot}) refused: {index}"
    for element, tname in (picks or {}).items():
        ok = P.SetTotem(index, element, IDS[tname] if tname else None)
        assert ok is True or ok[0] is True, f"SetTotem {element} {tname}: {ok}"
    if order:
        preset = P.Get(index)
        cur = [str(e) for e in seq(preset.order)]
        assert sorted(cur) == sorted(order), f"order {cur} vs {order}"
        for target, element in enumerate(order, 1):
            while [str(e) for e in seq(P.Get(index).order)].index(element) + 1 > target:
                assert P.Move(index, element, -1)
    if name:
        assert P.Rename(index, name)
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


def arcs(lua, key="preset1"):
    """[(shown, texture, (r, g, b, a), core shown)] for the four arcs of a cell."""
    b = btn(lua, key)
    out = []
    for a in seq(b.fsArcs):
        v = a.main._vertex
        out.append((shown(a.main), str(a.main._texture) if a.main._texture else None,
                    tuple(float(x) for x in seq(v)) if v else None, shown(a.core)))
    return out


def kinds(lua, key="preset1") -> list:
    """The look letter of each shown arc (t quiet, g done, k next, d locked) and its arc count."""
    out = []
    for sh, tex, _, _ in arcs(lua, key):
        if sh and tex:
            out.append(re.search(r"_n(\d)_(\d)_(\w)\.tga$", tex).groups())
    return out


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def rail(lua, key="preset1"):
    return btn(lua, key).fsRail


def raise_plate(lua, key="preset1"):
    return btn(lua, key).fsRaise


# ---------------------------------------------------------------------------------------------
# Checks: files, settings
# ---------------------------------------------------------------------------------------------


def check_toc_lists_the_preset_files_after_the_totem_bar_and_bindings_declare_both_cells():
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
    assert "CLICK FSTotemButton7:LeftButton" in names and "CLICK FSTotemButton8:LeftButton" in names, names


def check_the_settings_have_their_keys_defaults_tips_and_registered_defaults():
    lua = boot()
    S = PS(lua).SETTINGS
    # the keys of the cells and the set 2 switch are the ones players already saved; the switching, waiting, applied and
    # GNARLY flash and sound settings are gone with their features
    want = {
        "preset1": ("totems.dial", True), "preset2": ("totems.gnarly", True), "plate": ("totems.dialPlate", True),
        "set2": ("totems.gnarlySet2", True),
    }
    assert sorted(str(k) for k in S.keys()) == sorted(want), sorted(str(k) for k in S.keys())
    for name, (key, default) in want.items():
        assert str(S[name].key) == key and S[name].default is default, name
        assert str(S[name].label), name
        tip = str(S[name].tip)
        assert tip.endswith("."), f"{name}: tip {tip!r}"
        assert g(lua).FS.Config.Get(key) is default, f"{key} default"
    for gone in ("dialRight", "dialWheel", "waitPulse", "waitSound", "appliedFlash", "appliedSound", "gnarlyFlash", "gnarlySound"):
        assert g(lua).FS.Config.Get(f"totems.{gone}") is None, f"totems.{gone} is still registered"
    for text in ("preset1", "preset2"):
        assert "GNARLY" not in str(S[text].label) + str(S[text].tip), "player-facing GNARLY wording"


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

GONE = ("Select", "Cycle", "Pending", "Active", "SlotCount", "IsNew", "ActivePreset", "Gnarly", "SetGnarly", "CreateGnarly",
        "Delete", "GnarlyChoices", "GnarlyName", "OnRegen", "HasRoom", "WouldChange", "Count", "PressAge")


def check_two_slots_start_unset_with_default_colours_and_create_copies_the_four_buttons():
    lua = boot()
    P = PS(lua)
    assert P.Get(1) is None and P.Get(2) is None and P.Get(3) is None and P.Get(0) is None
    assert (P.Color(1), P.Color(2)) == (1, 2), "the default colours are cyan for Preset 1 and pink for Preset 2"
    palette = [(str(c.key), str(c.hex)) for c in seq(P.P.COLORS)]
    assert palette == [("cyan", "22e0ff"), ("pink", "ff2e97"), ("violet", "a855f7"), ("amber", "ffb648"),
                       ("green", "39ff14"), ("red", "ff3b4e"), ("white", "f3fbff")], palette
    rgb = P.ColorRgb(2)
    close((float(rgb[1]), float(rgb[2]), float(rgb[3])), PINK, "Preset 2's default colour")
    assert P.Create(3) is None or P.Create(3)[0] is None, "a third slot was made"
    i = P.Create(1)
    assert i == 1
    p = P.Get(1)
    assert str(p.name) == "PRESET 1"
    assert order_of(lua, 1) == ["earth", "fire", "water", "air"], "the default drop order"
    assert [int(p.picks[e]) for e in ("earth", "fire", "water", "air")] == [
        IDS["Stoneskin Totem"], IDS["Searing Totem"], IDS["Healing Stream Totem"], IDS["Grounding Totem"]]
    s = saved(lua)
    assert s is not None and s.slots[1] is not None and s.slots[2] is None, "saved under the character"
    assert [int(s.colors[1]), int(s.colors[2])] == [1, 2]
    again = P.Create(1)
    assert not again or again[0] is None, "a made slot was made again"
    # a pick that differs from the first one is what the copy carries; the second slot is named for its number
    TB(lua).Pick("fire", IDS["Magma Totem"])
    assert P.Create(2) == 2 and int(P.Get(2).picks.fire) == IDS["Magma Totem"] and str(P.Get(2).name) == "PRESET 2"
    # nothing of the switching, the GNARLY tie, the list or the cap is left
    for name in GONE:
        assert P[name] is None, f"PS.{name} is still there"
    for name in ("MAX", "pending", "applied", "SOUND", "APPLIED_FLASH", "PRESS_FLASH"):
        assert P.P[name] is None, f"P.{name} is still there"


def check_names_are_letters_digits_and_spaces_up_to_eight_uppercased():
    lua = boot()
    P = PS(lua)
    P.Create(1)
    for given, want in (("melee", "MELEE"), ("tank 2!!", "TANK 2"), ("abcdefghijkl", "ABCDEFGH"), ("  hi  ", "HI"),
                        ("a-b_c", "ABC")):
        assert P.Rename(1, given) is True
        assert str(P.Get(1).name) == want, f"{given!r} -> {P.Get(1).name!r}"
    ok = P.Rename(1, "!!!")
    assert ok[0] is False and str(P.Get(1).name) == "ABC", "an empty name is refused"
    assert int(P.P.NAME_MAX) == 8 and len("PRESET 2") <= 8, "the default name must fit the name box"


def check_a_saved_file_is_sanitised_when_it_loads():
    junk = (
        f'ForeverSTUwaveDB = {{ totemPresets = {{ [{GUID!r}] = {{ colors = {{ 9, "x" }}, retired = "oops", slots = {{'
        f' {{ name = "a very long name", picks = {{ earth = {IDS["Stoneskin Totem"]}, fire = 12345, water = "x" }},'
        f'   order = {{ "fire", "earth", "earth", "air" }} }},'
        f' "junk", {{ name = "", picks = {{ air = {IDS["Grounding Totem"]} }}, order = {{}} }} }} }} }} }}')
    lua = boot(pre_login=junk)
    P = PS(lua)
    p = P.Get(1)
    assert str(p.name) == "A VERY L", p.name
    assert [str(e) for e in seq(p.order)] == ["earth"], "only elements that carry a known totem stay in the order"
    assert p.picks.fire is None and p.picks.water is None
    assert P.Get(2) is None, "a slot that is not a preset stayed"
    assert P.Get(3) is None, "a third slot appeared"
    assert (P.Color(1), P.Color(2)) == (1, 2), "a bad colour reads as the slot default"
    s = saved(lua)
    assert s.slots[3] is None and len(seq(s.retired)) == 0, "the file was not tidied"
    assert [int(s.colors[1]), int(s.colors[2])] == [1, 2], "the bad colours were not replaced"
    # a good colour and a mixed pair survive, and a third entry in the slots (a rolled back build's) is dropped
    ok = (f'ForeverSTUwaveDB = {{ totemPresets = {{ [{GUID!r}] = {{ colors = {{ 7, 0.5, 3 }}, slots = {{'
          f' [2] = {{ name = "x", picks = {{}}, order = {{}} }}, [3] = {{ name = "y", picks = {{}}, order = {{}} }} }} }} }} }}')
    lua = boot(pre_login=ok)
    P = PS(lua)
    assert P.Get(1) is None and str(P.Get(2).name) == "X" and P.Get(3) is None
    assert (P.Color(1), P.Color(2)) == (7, 2), "a whole colour in range stays, a fraction reads as the default"
    assert saved(lua).slots[3] is None


def check_presets_are_kept_per_character():
    lua = boot()
    PS(lua).Create(1)
    run(lua, 'ForeverSTUwaveDB.totemPresets["Player-9-OTHER"] = { slots = { { name = "THEIRS", picks = {}, order = {} } }, colors = { 4, 5 } }')
    P = PS(lua)
    assert str(P.Get(1).name) == "PRESET 1" and P.Color(1) == 1, "another character's presets leaked in"


def check_a_read_only_config_or_no_database_keeps_the_presets_in_memory_and_refuses_edits():
    lua = boot()
    run(lua, "ForeverSTUwaveDB.totemPresets = nil; FS.Config.IsReadOnly = function() return true end")
    P = PS(lua)
    assert P.Writable() is False
    for r in (P.Create(1), P.SetColor(1, 3), P.Rename(1, "X"), P.SetTotem(1, "fire", IDS["Searing Totem"])):
        assert not r or r is False or r[0] in (None, False), f"an edit went through a store that cannot be saved: {r}"
    assert P.Get(1) is None and P.Color(1) == 1 and g(lua).ForeverSTUwaveDB.totemPresets is None, "the database was written"
    assert "cannot be saved this session" in str(P.Refusal()), "a read only config got another refusal text"
    lua = boot()
    run(lua, "ForeverSTUwaveDB = nil")
    P = PS(lua)
    assert P.Writable() is False and P.Get(1) is None
    r = P.Create(1)
    assert not r or r[0] is None
    assert g(lua).ForeverSTUwaveDB is None, "a missing database was created"
    assert "cannot be saved this session" in str(P.Refusal()), "a missing database got another refusal text"
    run(lua, 'ForeverSTUwaveDB = "oops"')
    assert P.Writable() is False and P.Get(1) is None and g(lua).ForeverSTUwaveDB == "oops"
    assert "cannot be saved this session" in str(P.Refusal()), "a database that is not a table got another refusal text"


# ---------------------------------------------------------------------------------------------
# Checks: the migration of the old list, active index and GNARLY tie
# ---------------------------------------------------------------------------------------------

LEGACY_FIRE = {"A": "Searing Totem", "B": "Magma Totem", "C": "Flametongue Totem", "D": "Frost Resistance Totem"}


def legacy(names, active=None, gnarly=None):
    """A saved file as the build with the dial, the list of up to four presets and the GNARLY tie wrote it."""
    items = ", ".join(
        f'{{ name = "{n}", picks = {{ fire = {IDS[LEGACY_FIRE[n]]}, earth = {IDS["Stoneskin Totem"]} }}, order = {{ "fire", "earth" }} }}'
        for n in names)
    parts = []
    if active is not None:
        parts.append(f"active = {active}")
    if gnarly is not None:
        parts.append(f"gnarly = {gnarly}")
    parts.append(f"list = {{ {items} }}")
    return f'ForeverSTUwaveDB = {{ totemPresets = {{ [{GUID!r}] = {{ {", ".join(parts)} }} }} }}'


def migrated(names, active=None, gnarly=None):
    """(slot 1 name, slot 2 name, retired names, the saved table) after the load of a legacy file."""
    lua = boot(pre_login=legacy(names, active, gnarly))
    P = PS(lua)
    one, two = P.Get(1), P.Get(2)
    s = saved(lua)
    retired = [str(e.name) for e in seq(s.retired)] if s.retired is not None else None
    return (str(one.name) if one else None, str(two.name) if two else None, retired, s, lua)


def check_the_old_file_moves_into_the_two_slots_once_with_the_extras_kept_in_retired():
    # no presets at all: two unset slots, default colours, nothing retired
    one, two, retired, s, lua = migrated([])
    assert (one, two, retired) == (None, None, []) and [int(s.colors[1]), int(s.colors[2])] == [1, 2]
    # one preset: it is Preset 1
    assert migrated(["A"], active=1)[:3] == ("A", None, [])
    # two presets, the second active and no tie: Preset 1 is the active one, Preset 2 the first other
    assert migrated(["A", "B"], active=2)[:3] == ("B", "A", [])
    # four presets, GNARLY tied to the fourth: Preset 2 is the tied one, the rest retire in list order
    assert migrated(["A", "B", "C", "D"], active=2, gnarly=4)[:3] == ("B", "D", ["A", "C"])
    # GNARLY missing (no tie): the first other preset in list order
    assert migrated(["A", "B", "C", "D"], active=3)[:3] == ("C", "A", ["B", "D"])
    # GNARLY tied to a preset that no longer exists: the same as no tie
    assert migrated(["A", "B", "C"], active=1, gnarly=9)[:3] == ("A", "B", ["C"])
    # GNARLY is the active preset: Preset 2 is the first other one, not the same preset twice
    assert migrated(["A", "B", "C"], active=2, gnarly=2)[:3] == ("B", "A", ["C"])
    assert migrated(["A"], active=1, gnarly=1)[:3] == ("A", None, [])
    # the dial rested on the NEW slot (active past the list): the first preset leads
    assert migrated(["A", "B"], active=3)[:3] == ("A", "B", [])
    assert migrated(["A", "B"], active=9)[:3] == ("A", "B", [])


def check_the_migrated_file_is_written_once_and_loading_it_again_changes_nothing():
    one, two, retired, s, lua = migrated(["A", "B", "C", "D"], active=2, gnarly=4)
    assert s.list is None and s.active is None and s.gnarly is None, "the old fields stayed beside the new ones"
    assert [int(s.colors[1]), int(s.colors[2])] == [1, 2], "colours start as cyan and pink, as the cells looked before"
    # nothing a player made is deleted: the retired presets still carry their totems and names
    ret = seq(s.retired)
    assert [int(r.picks.fire) for r in ret] == [IDS["Searing Totem"], IDS["Flametongue Totem"]]
    snapshot = lua.eval("function() local out = {} local function walk(t, path) for k, v in pairs(t) do "
                        "if type(v) == 'table' then walk(v, path .. '/' .. tostring(k)) else out[#out + 1] = path .. '/' .. tostring(k) .. '=' .. tostring(v) end end end "
                        "walk(ForeverSTUwaveDB.totemPresets, '') table.sort(out) return table.concat(out, ';') end")()
    # a second load of the same table (a /reload) neither migrates again nor adds to retired
    PS(lua).Get(1)
    run(lua, "FS.TotemPresets.Writable()")
    again = lua.eval("function() local out = {} local function walk(t, path) for k, v in pairs(t) do "
                     "if type(v) == 'table' then walk(v, path .. '/' .. tostring(k)) else out[#out + 1] = path .. '/' .. tostring(k) .. '=' .. tostring(v) end end end "
                     "walk(ForeverSTUwaveDB.totemPresets, '') table.sort(out) return table.concat(out, ';') end")()
    assert again == snapshot, "a second pass changed the migrated file"
    # a file that already has slots is never migrated over, whatever old fields sit beside them
    mixed = (f'ForeverSTUwaveDB = {{ totemPresets = {{ [{GUID!r}] = {{ active = 1, list = {{ {{ name = "OLD", picks = {{}},'
             f' order = {{}} }} }}, slots = {{ [1] = {{ name = "KEEP", picks = {{}}, order = {{}} }} }} }} }} }}')
    lua2 = boot(pre_login=mixed)
    assert str(PS(lua2).Get(1).name) == "KEEP" and PS(lua2).Get(2) is None and len(seq(saved(lua2).retired)) == 0


def check_a_migrated_file_gives_each_cell_its_own_script():
    lua = boot(pre_login=legacy(["A", "B", "C"], active=1, gnarly=3))
    TB(lua).Sync()
    t1, t2 = str(c1(lua)._attrs["macrotext1"]), str(c2(lua)._attrs["macrotext1"])
    assert "Searing Totem" in t1 and "Flametongue Totem" in t2 and t1 != t2, (t1, t2)
    assert c1(lua)._attrs["type1"] == "macro" and c2(lua)._attrs["type1"] == "macro"


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
    for bad in (0, 3, 9, "1", None):
        assert P.SetTotem(bad, "fire", IDS["Searing Totem"])[0] is False, f"slot {bad!r} was accepted"
        assert P.Move(bad, "fire", 1)[0] is False and P.Rename(bad, "X")[0] is False and P.SetColor(bad, 2)[0] is False
        assert P.Clear(bad)[0] is False and P.Create(bad)[0] is None


def check_the_first_totem_picked_on_an_unset_slot_makes_the_preset_named_for_its_number():
    lua = boot()
    P = PS(lua)
    assert P.SetTotem(2, "fire", None) is True and P.Get(2) is None, "leaving an element out of nothing made a preset"
    assert P.SetTotem(2, "fire", IDS["Magma Totem"]) is True
    p = P.Get(2)
    assert str(p.name) == "PRESET 2" and order_of(lua, 2) == ["fire"] and int(p.picks.fire) == IDS["Magma Totem"]
    assert P.Get(1) is None, "the other slot was made too"
    assert P.Rename(2, "solo") is True and str(P.Get(2).name) == "SOLO", "a typed name replaces the default"
    assert P.Rename(1, "first") is True and str(P.Get(1).name) == "FIRST" and order_of(lua, 1) == [], \
        "a name typed on an unset slot makes an empty preset with that name"
    assert c1(lua)._attrs["type1"] is None, "an empty preset left a cast on the cell"


def check_every_edit_is_refused_in_combat_and_the_editor_will_not_open():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    set_combat(lua, True)
    before = order_of(lua, i)
    for r in (P.Create(2), P.Rename(i, "X"), P.SetTotem(i, "fire", IDS["Magma Totem"]), P.Move(i, "fire", 1), P.Clear(i),
              P.SetColor(i, 4)):
        assert not r or r is False or r[0] in (None, False), f"an edit went through in combat: {r}"
    assert P.Get(2) is None and order_of(lua, i) == before and str(P.Get(i).name) == "PRESET 1" and P.Color(i) == 1
    DL(lua).OpenEditor(i)
    assert DL(lua).Card() is None or not shown(DL(lua).Card()), "the editor opened in combat"
    set_combat(lua, False)
    DL(lua).OpenEditor(i)
    assert shown(DL(lua).Card())
    enter_combat(lua)
    assert not shown(DL(lua).Card()), "the editor stayed open when combat started"


def check_the_outline_colour_is_a_cell_setting_saved_per_slot_and_kept_when_a_preset_is_cleared():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    j = make(lua)
    assert P.SetColor(1, 5) is True and P.SetColor(2, 7) is True
    assert (P.Color(1), P.Color(2)) == (5, 7) and [int(x) for x in seq(saved(lua).colors)] == [5, 7]
    for bad in (0, 8, -1, 2.5, "3", None):
        assert P.SetColor(1, bad)[0] is False and P.Color(1) == 5, f"colour {bad!r} was accepted"
    # a colour can be chosen for an unset slot: it is the cell's, not the preset's
    assert P.Clear(2) is True and P.Get(2) is None and P.Color(2) == 7, "CLEAR changed the colour"
    assert P.SetColor(2, 4) is True and P.Color(2) == 4
    # editing the totems or the name never touches the colour
    P.SetTotem(1, "fire", IDS["Magma Totem"]), P.Rename(1, "X"), P.Move(1, "earth", 1)
    assert P.Color(1) == 5
    # a colour gone bad in memory reads as the slot default
    run(lua, f"ForeverSTUwaveDB.totemPresets[{GUID!r}].colors[1] = 99")
    assert P.Color(1) == 1


def check_clear_empties_a_preset_keeps_its_colour_and_resets_only_its_own_step():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetColor(a, 3)
    cast_name(lua, "Stoneskin Totem", "preset1")
    cast_name(lua, "Tremor Totem", "preset2")
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (1, 1)
    assert P.IsEmpty(a) is False and P.IsEmpty(b) is False
    assert P.Clear(a) is True
    assert P.Get(a) is None and P.IsEmpty(a) is True and P.Color(a) == 3, "CLEAR kept the preset or lost the colour"
    assert c1(lua)._attrs["type1"] is None, "the cleared cell still casts"
    assert c2(lua)._attrs["type1"] == "macro", "clearing one slot touched the other"
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (0, 1), "a clear should restart only its own step"
    r = P.Clear(a)
    assert r[0] is False, "clearing an empty slot should be refused"
    assert P.Clear(b) is True, "Preset 2 clears"
    # Preset 1 can be cleared like the other, and a named preset with no totems is not empty (its name can be cleared)
    P.Rename(a, "kept")
    assert P.IsEmpty(a) is False and P.Clear(a) is True and P.Get(a) is None


def two_presets(lua):
    a = make(lua, picks={"fire": "Searing Totem", "earth": "Stoneskin Totem", "water": "Healing Stream Totem",
                         "air": "Grounding Totem"}, name="MELEE")
    b = make(lua, picks={"fire": "Magma Totem", "earth": "Tremor Totem", "water": "Mana Spring Totem", "air": None},
             name="CASTER")
    return a, b


def check_a_totem_not_learned_yet_is_skipped_and_stays_locked():
    lua = boot(learned=[n for n in TOTEMS["earth"] + TOTEMS["fire"]])
    P = PS(lua)
    i = make(lua, picks={"water": "Healing Stream Totem", "air": "Grounding Totem"})
    e = P.Entry("water", IDS["Healing Stream Totem"])
    assert e.known is False and int(e.level) == 20, f"level {e.level}"
    assert P.Entry("air", IDS["Grounding Totem"]).known is False
    assert text_of(lua, i).count(",") == 1, text_of(lua, i)


# ---------------------------------------------------------------------------------------------
# Checks: the step
# ---------------------------------------------------------------------------------------------


NUM_SECRET = (
    "local __o = FS.IsSecret; FS.IsSecret = function(v) return __o(v) or (__numSecret ~= nil and v == __numSecret) end\n"
)


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


def check_each_cell_carries_its_own_script_as_secure_attributes_written_out_of_combat_only():
    lua = boot()
    P = PS(lua)
    for cell in (c1(lua), c2(lua)):
        assert cell._attrs["type1"] is None, "an unset cell has nothing to drop"
        assert cell._attrs["shift-type1"] == "" and cell._attrs["alt-type1"] == "", "shift and alt clicks must drop nothing"
    a, b = two_presets(lua)
    d, e = c1(lua), c2(lua)
    assert d._attrs["type1"] == "macro" and e._attrs["type1"] == "macro", "a plain click did not become the step"
    assert str(d._attrs["macrotext1"]) == text_of(lua, a) and str(e._attrs["macrotext1"]) == text_of(lua, b)
    assert "Searing" in str(d._attrs["macrotext1"]) and "Magma" in str(e._attrs["macrotext1"])
    first = str(d._attrs["macrotext1"])
    P.SetTotem(b, "fire", None)
    assert "Magma" not in str(e._attrs["macrotext1"]), "the script did not follow the edit"
    assert str(d._attrs["macrotext1"]) == first, "an edit of Preset 2 changed Preset 1's script"
    P.SetTotem(a, "fire", None)
    assert "Searing" not in str(d._attrs["macrotext1"]) and "Tremor" in str(e._attrs["macrotext1"])
    # in combat a press, a right click and the wheel write nothing, and there is no switch behind any of them
    set_combat(lua, True)
    n = blocked(lua)
    for cell in (d, e):
        click(lua, cell, "LeftButton", False)
        click(lua, cell, "RightButton")
        script(lua, cell, "OnMouseWheel", 1)
    assert blocked(lua) == n, "a secure write was tried in combat"
    assert d._attrs["type1"] == "macro" and e._attrs["type1"] == "macro", "a script changed in combat"
    assert int(P.Tracker("preset1").presses) == 1 and int(P.Tracker("preset2").presses) == 1
    leave_combat(lua)
    # a script that is the same is not written again
    first = str(d._attrs["macrotext1"])
    run(lua, "__writes = 0; local d = FSTotemButton7; local set = d.SetAttribute; "
             "d.SetAttribute = function(self, k, v) if k == 'macrotext1' then __writes = __writes + 1 end return set(self, k, v) end")
    TB(lua).Sync()
    assert int(g(lua).__writes) == 0, "the same script was written again"
    assert str(d._attrs["macrotext1"]) == first


def check_a_press_counts_on_the_event_the_game_acts_on():
    lua = boot()
    make(lua)
    d = c1(lua)
    t = PS(lua).Tracker("preset1")
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
    # an Alt click drops nothing: no press either, on either cell (the second one has a preset too)
    make(lua)
    run(lua, "__alt = true")
    gt = PS(lua).Tracker("preset2")
    for cell_btn in (d, c2(lua)):
        click(lua, cell_btn, "LeftButton", True)
        click(lua, cell_btn, "LeftButton", False)
    assert int(t.presses) == 2 and int(gt.presses) == 0, "an Alt click was counted as a drop"
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


def cast_name(lua, name, cell="preset1"):
    """A press of the cell, then the cast it brings (the game casts after the click)."""
    click(lua, btn(lua, cell), "LeftButton", False)
    cast_raw(lua, name)


def check_the_record_advances_on_the_next_totem_cast_and_ignores_the_rest():
    lua = boot()
    P = PS(lua)
    make(lua)
    assert tuple(P.Progress("preset1")) == (0, 4)
    cast_name(lua, "Searing Totem")
    assert P.Progress("preset1")[0] == 0, "a cast out of turn counted"
    advance(lua, 2.5)
    cast_raw(lua, "Stoneskin Totem")
    assert P.Progress("preset1")[0] == 0, "a cast with no press before it counted"
    cast_name(lua, "Stoneskin Totem")
    assert tuple(P.Progress("preset1")) == (1, 4)
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("preset1")[0] == 1
    for name in ("Searing Totem", "Healing Stream Totem", "Grounding Totem"):
        cast_name(lua, name)
    assert P.Progress("preset1")[0] == 4
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("preset1")[0] == 1, "a finished sequence starts over at the next drop"
    run(lua, '__fire_event("UNIT_SPELLCAST_SUCCEEDED", "target", "guid", %d)' % IDS["Searing Totem"])
    assert P.Progress("preset1")[0] == 1, "another unit's cast counted"
    assert int(P.Tracker("preset1").matched) == 5
    advance(lua, 2.5)
    cast_raw(lua, "Searing Totem")
    assert P.Progress("preset1")[0] == 1, "a cast long after the press counted"


def check_the_record_starts_over_at_combat_end_after_six_idle_seconds_and_on_any_edit():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    cast_name(lua, "Stoneskin Totem")
    cast_name(lua, "Searing Totem")
    assert P.Progress("preset1")[0] == 2
    advance(lua, 5.5)
    tick(lua)
    assert P.Progress("preset1")[0] == 2, "it started over before six seconds"
    advance(lua, 0.6)
    tick(lua)
    assert P.Progress("preset1")[0] == 0, "it did not start over after six seconds"
    # a drop restarts the clock
    cast_name(lua, "Stoneskin Totem")
    advance(lua, 4)
    cast_name(lua, "Searing Totem")
    advance(lua, 4)
    tick(lua)
    assert P.Progress("preset1")[0] == 2, "the clock did not restart on a drop"
    # combat end
    enter_combat(lua)
    cast_name(lua, "Healing Stream Totem")
    assert P.Progress("preset1")[0] == 3
    leave_combat(lua)
    assert P.Progress("preset1")[0] == 0, "combat ended and the step stayed"
    # edits
    cast_name(lua, "Stoneskin Totem")
    P.Rename(i, "ZZ")
    assert P.Progress("preset1")[0] == 1, "a rename should not restart the step"
    P.Move(i, "air", -1)
    assert P.Progress("preset1")[0] == 0, "an edit of the order left a step the script no longer has"
    cast_name(lua, "Stoneskin Totem")
    P.SetTotem(i, "fire", IDS["Magma Totem"])
    assert P.Progress("preset1")[0] == 0
    cast_name(lua, "Stoneskin Totem")
    assert P.Clear(i) is True
    assert tuple(P.Progress("preset1")) == (0, 0), "a clear left the step"


def check_a_secret_number_from_the_clock_is_not_kept_as_a_press_time():
    # the mock secret is a table, which the type tests would catch anyway: a secret NUMBER is what the guards are for
    lua = boot(early=NUM_SECRET)
    make(lua)
    run(lua, "local get = GetTime; __getTime = get; GetTime = function() return 123.5 end; __numSecret = 123.5")
    click(lua, c1(lua))
    assert PS(lua).Tracker("preset1").pressAt is None, "a secret clock was stored as a press time"
    run(lua, "__numSecret = nil")
    click(lua, c1(lua))
    assert float(PS(lua).Tracker("preset1").pressAt) == 123.5, "a plain clock stores the press"
    run(lua, "GetTime = __getTime")


def check_a_secret_spell_id_is_noted_and_never_breaks_the_record():
    lua = boot()
    P = PS(lua)
    make(lua)
    run(lua, '__fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", __SECRET)')
    assert P.Progress("preset1")[0] == 0
    P.SaveState()
    line = str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    assert "castids=secret" in line, line
    run(lua, "__fire_event('UNIT_SPELLCAST_SUCCEEDED', 'player', 'guid', nil)")
    run(lua, "__fire_event('UNIT_SPELLCAST_SUCCEEDED', 'player', 'guid', 'x')")


# ---------------------------------------------------------------------------------------------
# Checks: the face
# ---------------------------------------------------------------------------------------------

PALETTE = [("cyan", "22e0ff"), ("pink", "ff2e97"), ("violet", "a855f7"), ("amber", "ffb648"), ("green", "39ff14"),
           ("red", "ff3b4e"), ("white", "f3fbff")]


def hex_rgb(h):
    return tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))


def vtx(t):
    c = t._vertex
    return tuple(float(x) for x in seq(c)) if c is not None else None


def col(t):
    c = t._color
    return tuple(float(x) for x in seq(c)) if c is not None else None


def ring_of(cell):
    return vtx(cell.fsSkin.border.ring)


def glow_of(cell):
    return vtx(cell.fsSkin.glow)


def dashes_of(cell):
    """[(shown, (r, g, b, a))] of the dashed border of a cell."""
    return [(shown(t), col(t)) for t in seq(cell.fsDashes.dashes)]


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
    assert not shown(btn(lua, "preset1").fsEmpty)


def check_the_number_the_plus_and_the_dashed_empty_ring():
    lua = boot()
    P = PS(lua)
    look(lua)
    d, e = btn(lua, "preset1"), btn(lua, "preset2")
    for cell in (d, e):
        assert str(cell.fsDigit._text) == "+" and shown(cell.fsEmpty), "an unset slot shows a plus on a dashed ring"
    assert not any(sh for sh, *_ in arcs(lua)) and not any(sh for sh, *_ in arcs(lua, "preset2"))
    i = make(lua)
    j = make(lua)
    look(lua)
    assert str(d.fsDigit._text) == "1" and not shown(d.fsEmpty)
    assert str(e.fsDigit._text) == "2" and not shown(e.fsEmpty), "each cell wears its own number"
    P.SetTotem(i, "earth", None), P.SetTotem(i, "fire", None), P.SetTotem(i, "water", None), P.SetTotem(i, "air", None)
    look(lua)
    assert str(d.fsDigit._text) == "+" and shown(d.fsEmpty), "a preset with nothing in it looks empty"
    assert str(e.fsDigit._text) == "2"


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
    assert tuple(P.Progress("preset1")) == (2, 2), "the total counts the totems that drop"
    assert [k for _, _, k in kinds(lua)] == ["g", "g", "d", "d"], kinds(lua)


def check_while_stepping_done_arcs_glow_the_next_is_thick_and_the_icon_replaces_the_number():
    lua = boot()
    make(lua)
    d = btn(lua, "preset1")
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
    for t in seq(d.fsBrackets):
        close(col(t), CYAN, "the brackets stay cyan whatever the outline colour is")
    cast_name(lua, "Searing Totem"), cast_name(lua, "Healing Stream Totem"), cast_name(lua, "Grounding Totem")
    look(lua)
    assert [k for _, _, k in kinds(lua)] == ["g", "g", "g", "g"]
    assert not any(shown(t) for t in seq(d.fsBrackets)), "no next totem, no brackets"
    assert shown(d.fsDigit) and not shown(d.fsNext)
    advance(lua, 6.5), tick(lua)
    assert [k for _, _, k in kinds(lua)] == ["t"] * 4, "the idle restart did not repaint the arcs"


def check_the_name_plates_and_the_step_plate():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    look(lua)
    assert shown(rail(lua)) and str(rail(lua).text._text) == "MELEE"
    assert shown(rail(lua, "preset2")) and str(rail(lua, "preset2").text._text) == "CASTER"
    assert not shown(raise_plate(lua)), "the raised plate is for a step"
    cast_name(lua, "Stoneskin Totem")
    look(lua)
    assert shown(raise_plate(lua)) and str(raise_plate(lua).text._text) == "1/4", raise_plate(lua).text._text
    sq = [s for s in seq(raise_plate(lua).squares) if shown(s)]
    assert len(sq) == 4, "a square for each totem"
    assert not shown(raise_plate(lua, "preset2")), "a step on one cell showed on the other"
    P.Rename(a, "tank")
    assert str(rail(lua).text._text) == "TANK", "the plate did not follow the rename"
    conf(lua, "totems.dialPlate", False)
    look(lua)
    assert not shown(rail(lua)) and not shown(rail(lua, "preset2")), "the plates stayed with their setting off"
    conf(lua, "totems.dialPlate", True)
    look(lua)
    assert str(rail(lua).text._text) == "TANK"
    P.Clear(b)
    look(lua)
    assert str(rail(lua, "preset2").text._text) == "UNSET"


def check_the_outline_colour_draws_the_border_glow_underline_and_plate_of_each_cell_and_not_the_arcs():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    look(lua)
    for key, slot in (("preset1", 1), ("preset2", 2)):
        cell = btn(lua, key)
        want = hex_rgb(PALETTE[P.Color(slot) - 1][1])
        close(ring_of(cell), want, f"{key} border"), close(glow_of(cell), want, f"{key} glow")
        close(vtx(cell.fsBar), want, f"{key} underline")
        close(col(cell.fsRail.edges[1]), want, f"{key} plate edge")
        close(tuple(float(x) for x in seq(cell.fsRail.text._mono.color)), want, f"{key} name label")
        assert abs(ring_of(cell)[3] - 1) < 1e-6 and abs(glow_of(cell)[3] - 0.35) < 1e-6 and abs(vtx(cell.fsBar)[3] - 0.9) < 1e-6
    # every swatch colour reaches all four, for each slot, and the element arcs keep their element colours
    for slot, key in ((1, "preset1"), (2, "preset2")):
        for idx, (name, hx) in enumerate(PALETTE, 1):
            assert P.SetColor(slot, idx) is True
            cell = btn(lua, key)
            want = hex_rgb(hx)
            close(ring_of(cell), want, f"{key} {name} border"), close(glow_of(cell), want, f"{key} {name} glow")
            close(vtx(cell.fsBar), want, f"{key} {name} underline")
            close(col(cell.fsRail.edges[1]), want, f"{key} {name} plate edge")
            close(tuple(float(x) for x in seq(cell.fsRail.text._mono.color)), want, f"{key} {name} label")
            a_ = arcs(lua, key)
            for n, element in enumerate(order_of(lua, slot)):
                close(a_[n][2], ELEMENT_COLOR[element], f"{key} {name} arc {element}")
    # the other cell is not touched by a change of one
    P.SetColor(1, 6)
    close(ring_of(btn(lua, "preset2")), hex_rgb(PALETTE[6][1]), "Preset 2 keeps its own colour")
    # a colour that went bad reads as the slot's default
    run(lua, f"ForeverSTUwaveDB.totemPresets[{GUID!r}].colors[2] = 'junk'")
    look(lua)
    close(ring_of(btn(lua, "preset2")), PINK, "a bad colour reads as the slot default")
    # painting is legal in combat: a hover in combat keeps the chosen colour and writes nothing protected
    P.SetColor(1, 5)
    set_combat(lua, True)
    n = blocked(lua)
    cell = btn(lua, "preset1")
    script(lua, cell, "OnEnter")
    close(ring_of(cell), hex_rgb(PALETTE[4][1]), "the colour in combat")
    script(lua, cell, "OnLeave")
    assert blocked(lua) == n


def check_an_unset_cell_is_dim_dashed_and_muted_with_a_plus_the_plate_unset_and_a_press_does_nothing():
    lua = boot()
    look(lua)
    for key in ("preset1", "preset2"):
        cell = btn(lua, key)
        assert str(cell.fsDigit._text) == "+"
        close(tuple(float(x) for x in seq(cell.fsDigit._textColor)), MUTED, f"{key} plus")
        assert str(cell.fsRail.text._text) == "UNSET"
        close(tuple(float(x) for x in seq(cell.fsRail.text._mono.color)), MUTED, f"{key} plate label")
        close(col(cell.fsRail.edges[1]), MUTED, f"{key} plate edge")
        assert abs(col(cell.fsRail.edges[1])[3] - 0.5) < 1e-6
        assert ring_of(cell)[3] == 0 and glow_of(cell)[3] == 0, f"{key}: the solid border or the glow shows on an unset cell"
        dashes = dashes_of(cell)
        assert dashes and all(sh for sh, _ in dashes), f"{key}: dashed border"
        for _, c in dashes:
            close(c, MUTED, f"{key} dash colour")
            assert abs(c[3] - 0.6) < 1e-6
        close(vtx(cell.fsBar), MUTED, f"{key} underline")
        assert abs(vtx(cell.fsBar)[3] - 0.5) < 1e-6
        tint = vtx(cell.fsTint)
        assert tint[3] > 0.3, f"{key}: an unset cell is not dimmed"
        script(lua, cell, "OnEnter")
        assert all(abs(c[3] - 1) < 1e-6 for _, c in dashes_of(cell)), f"{key}: the dashes do not brighten on hover"
        script(lua, cell, "OnLeave")
        assert cell._attrs["type1"] is None and not cell.fsDisabled
        click(lua, cell, "LeftButton", False)
        assert int(PS(lua).Tracker(key).presses) == 0, "a press on an unset cell was counted"
    # a set cell shows no dashes
    make(lua)
    look(lua)
    dashes = dashes_of(btn(lua, "preset1"))
    assert not any(sh for sh, _ in dashes) and ring_of(btn(lua, "preset1"))[3] == 1


def check_the_cells_light_on_hover_and_press_toward_their_colour_and_restore_in_and_out_of_combat():
    for combat in (False, True):
        lua = boot()
        a, b = two_presets(lua)
        P = PS(lua)
        P.SetColor(1, 4)
        look(lua)
        if combat:
            set_combat(lua, True)
        n = blocked(lua)
        for key, idx in (("preset1", 4), ("preset2", 2)):
            cell = btn(lua, key)
            want = hex_rgb(PALETTE[idx - 1][1])
            state = lambda: (ring_of(cell), glow_of(cell), vtx(cell.fsTint))
            base = state()
            assert base[2][3] == 0, "a quiet cell is not tinted"
            script(lua, cell, "OnEnter")
            hov = state()
            close(hov[2], want, f"{key} hover tint"), close(hov[1], want, f"{key} hover glow")
            assert abs(hov[2][3] - 0.16) < 1e-6 and abs(hov[1][3] - 0.6) < 1e-6 and abs(hov[0][3] - 1) < 1e-6, hov
            script(lua, cell, "OnMouseDown")
            pre = state()
            assert abs(pre[2][3] - 0.32) < 1e-6 and abs(pre[1][3] - 0.6) < 1e-6, pre
            script(lua, cell, "OnMouseUp")
            assert state() == hov, f"{key}: release did not return to hover"
            script(lua, cell, "OnLeave")
            assert state() == base, f"{key} did not restore (combat {combat})"
            # the mouse leaving with the button down drops both looks
            script(lua, cell, "OnEnter")
            script(lua, cell, "OnMouseDown")
            script(lua, cell, "OnLeave")
            assert state() == base, f"{key}: leaving with the button down kept a look"
            script(lua, cell, "OnEnter")
            script(lua, cell, "OnMouseDown")
            script(lua, cell, "OnHide")        # the cell turned off under the mouse
            assert not cell.fsHover and not cell.fsPressed, f"{key}: a hidden cell kept its hover or pressed state"
            script(lua, cell, "OnLeave")
        assert blocked(lua) == n, "a protected write was tried"


# ---------------------------------------------------------------------------------------------
# Checks: tooltips
# ---------------------------------------------------------------------------------------------


def check_the_tooltip_lists_the_totems_in_order_the_left_out_ones_the_hints_and_the_unset_cell():
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"] + TOTEMS["air"] + ["Healing Stream Totem"])
    P = PS(lua)
    d, e = c1(lua), c2(lua)
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "PRESET 1: UNSET" and any("Shift click" in x for x in ls), ls
    unhover(lua, d)
    i = make(lua, picks={"water": None}, name="MELEE")
    hover(lua, d)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "PRESET 1: MELEE", ls
    assert ls[1:4] == ["1 Stoneskin Totem", "2 Searing Totem", "3 Grounding Totem"], ls
    assert any(x.startswith("Water: left out") for x in ls), ls
    assert any(x == "Click: drop the next totem. Shift click: edit. Always ready, even in combat." for x in ls), ls
    assert any(x == "Starts over after combat ends or a 6 s pause." for x in ls), ls
    assert any("|T" in x for x in lines(lua)), "the totem lines carry a colour swatch"
    unhover(lua, d)
    assert not shown(g(lua).GameTooltip)
    j = make(lua, picks={"water": "Healing Stream Totem", "air": "Grounding Totem"}, name="SOLO")
    P.SetTotem(j, "fire", None), P.SetTotem(j, "earth", None)
    hover(lua, e)
    ls = [plain(x) for x in lines(lua)]
    assert ls[0] == "PRESET 2: SOLO" and ls[1] == "1 Healing Stream Totem" and ls[2] == "2 Grounding Totem", ls
    unhover(lua, e)
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"])
    P = PS(lua)
    i = make(lua, name="MELEE")
    P.SetTotem(i, "water", IDS["Healing Stream Totem"]), P.SetTotem(i, "air", IDS["Grounding Totem"])
    hover(lua, c1(lua))
    ls = [plain(x) for x in lines(lua)]
    assert "3 Healing Stream Totem (level 20)" in ls and "4 Grounding Totem (level 30)" in ls, ls
    for text in ls:
        low = text.lower()
        assert "gnarly" not in low and "right click" not in low and "wheel" not in low and "dial" not in low and \
            "next preset" not in low and "waiting" not in low, text


# ---------------------------------------------------------------------------------------------
# Checks: the editor
# ---------------------------------------------------------------------------------------------


def card(lua):
    return DL(lua).Card()


def shift_click(lua, button):
    run(lua, "__shift = true")
    click(lua, button, "LeftButton", True)
    click(lua, button, "LeftButton", False)
    run(lua, "__shift = false")


def check_shift_click_on_a_set_cell_edits_its_preset_and_on_an_unset_cell_makes_it_from_the_four_buttons():
    lua = boot()
    P = PS(lua)
    run(lua, "__shift = true")
    click(lua, c1(lua), "LeftButton", True)
    assert P.Get(1) is None and card(lua) is None, "the key down of a shift click edited"
    click(lua, c1(lua), "LeftButton", False)
    run(lua, "__shift = false")
    assert P.Get(1) is not None and P.Get(2) is None and shown(card(lua)) and int(card(lua).fsIndex) == 1
    assert str(P.Get(1).name) == "PRESET 1" and str(card(lua).name._text) == "PRESET 1"
    assert order_of(lua, 1) == ["earth", "fire", "water", "air"], "the new preset is a copy of the four buttons"
    assert int(PS(lua).Tracker("preset1").presses) == 0, "a shift click was counted as a drop"
    DL(lua).CloseEditor()
    shift_click(lua, c2(lua))
    assert str(P.Get(2).name) == "PRESET 2" and int(card(lua).fsIndex) == 2
    # a made cell opens its own preset and makes nothing
    DL(lua).CloseEditor()
    P.Rename(1, "FIRST")
    shift_click(lua, c1(lua))
    assert int(card(lua).fsIndex) == 1 and str(P.Get(1).name) == "FIRST" and str(P.Get(2).name) == "PRESET 2"
    shift_click(lua, c2(lua))
    assert int(card(lua).fsIndex) == 2, "the card did not move to the other preset"
    # in combat nothing is made and nothing opens
    DL(lua).CloseEditor()
    P.Clear(2)
    set_combat(lua, True)
    shift_click(lua, c2(lua))
    assert P.Get(2) is None and (card(lua) is None or not shown(card(lua))), "a preset was made or opened in combat"
    assert int(P.Tracker("preset2").presses) == 0
    set_combat(lua, False)
    # nothing in the four buttons to copy: the card opens on the unset slot, nothing is made
    run(lua, "FS.TotemBar.CurrentPick = function() return nil end")
    shift_click(lua, c2(lua))
    assert P.Get(2) is None and shown(card(lua)) and int(card(lua).fsIndex) == 2


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
    script(lua, rows(lua)[3], "OnClick")
    ch = DL(lua).Chooser()
    assert ch is not None and shown(ch)
    tiles = [t for t in seq(ch.tiles) if shown(t)]
    assert len(tiles) == len(TOTEMS["fire"]) + 1, f"{len(tiles)} tiles"
    script(lua, tiles[2], "OnClick")
    assert int(P.Get(i).picks.fire) == IDS["Magma Totem"] and order_of(lua, i)[-1] == "fire"
    assert not shown(ch), "the chooser stayed after a choice"
    assert c1(lua)._attrs["macrotext1"] and "Magma" in str(c1(lua)._attrs["macrotext1"]), "the cell script did not follow"
    script(lua, rows(lua)[3], "OnClick")
    tiles = [t for t in seq(DL(lua).Chooser().tiles) if shown(t)]
    script(lua, tiles[-1], "OnClick")
    assert P.Get(i).picks.fire is None and "fire" not in order_of(lua, i), "left out did not remove the totem"
    # a totem not known yet is not offered
    lua = boot(learned=TOTEMS["fire"][:2])
    i = make(lua)
    DL(lua).OpenEditor(i)
    script(lua, rows(lua)[0], "OnClick")
    assert len([t for t in seq(DL(lua).Chooser().tiles) if shown(t)]) == 3, "only the two known totems and left out"


def check_an_unset_slot_opens_empty_and_its_first_totem_makes_the_preset_named_for_its_number():
    lua = boot()
    P = PS(lua)
    DL(lua).OpenEditor(2)
    c = card(lua)
    assert shown(c) and str(c.title._text) == "PRESET 2" and str(c.name._text) == "", "the unset card shows no name"
    r = rows(lua)
    assert all(str(x.label._text) == "left out" and not shown(x.up) and not shown(x.down) for x in r)
    assert float(c.clear._alpha) == 0.4 and c.clear._enabled is False, "CLEAR is live on an empty slot"
    assert P.Get(2) is None
    script(lua, r[1], "OnClick")
    tiles = [t for t in seq(DL(lua).Chooser().tiles) if shown(t)]
    script(lua, tiles[0], "OnClick")
    assert P.Get(2) is not None and str(P.Get(2).name) == "PRESET 2" and str(c.name._text) == "PRESET 2"
    assert P.Get(1) is None and float(c.clear._alpha) == 1 and c.clear._enabled is not False
    # typing a name over the default keeps the totems
    c.name._text = "solo"
    script(lua, c.name, "OnEnterPressed")
    assert str(P.Get(2).name) == "SOLO" and len(order_of(lua, 2)) == 1
    # a name typed on an unset slot makes the preset that holds it
    DL(lua).CloseEditor()
    DL(lua).OpenEditor(1)
    card(lua).name._text = "tank"
    script(lua, card(lua).name, "OnEnterPressed")
    assert str(P.Get(1).name) == "TANK" and order_of(lua, 1) == []


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


def check_clear_asks_twice_the_confirmation_runs_out_and_the_card_stays_open_on_the_empty_slot():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    P.SetColor(a, 4)
    DL(lua).OpenEditor(a)
    c = card(lua)
    cl = c.clear
    assert str(cl.text._text) == "CLEAR"
    script(lua, cl, "OnClick")
    assert P.Get(a) is not None and str(cl.text._text) == "SURE?", "the first click cleared or did not ask"
    advance(lua, 3.5)
    tick(lua)
    assert str(cl.text._text) == "CLEAR", "the armed look outlived its 3 seconds"
    script(lua, cl, "OnClick")
    assert P.Get(a) is not None, "an old confirmation still counted"
    script(lua, cl, "OnClick")
    assert P.Get(a) is None and P.Get(b) is not None, "the second click did not clear exactly this preset"
    assert shown(c) and int(c.fsIndex) == a and str(c.name._text) == "", "the card should stay open on the empty slot"
    assert P.Color(a) == 4, "CLEAR changed the colour"
    assert all(str(x.label._text) == "left out" for x in rows(lua))
    assert c.clear._enabled is False and float(c.clear._alpha) == 0.4, "CLEAR is live on an empty slot"
    look(lua)
    assert str(rail(lua).text._text) == "UNSET"
    assert c1(lua)._attrs["type1"] is None
    # Preset 1 and Preset 2 both clear; a closed card forgets the question
    DL(lua).CloseEditor()
    DL(lua).OpenEditor(b)
    script(lua, card(lua).clear, "OnClick")
    DL(lua).CloseEditor()
    DL(lua).OpenEditor(b)
    assert str(card(lua).clear.text._text) == "CLEAR", "a closed card kept the armed question"
    # in combat it cannot be asked at all
    enter_combat(lua)
    assert not shown(card(lua))
    assert P.Clear(b)[0] is False


def check_the_card_closes_on_escape_and_combat_and_hangs_on_the_last_cell():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    c = card(lua)
    assert "FSTotemEditor" in [str(x) for x in seq(g(lua).UISpecialFrames)], "Escape does not close the card"
    assert c._strata == "DIALOG"
    p = c._points[1]
    assert (p.point, p.relPoint) == ("BOTTOMRIGHT", "TOPRIGHT") and sb.same(lua, p.rel, btn(lua, "preset2")), \
        "the card hangs on the last cell"
    approx(p.x, 4.4, "card x"), approx(p.y, 21, "card y")
    DL(lua).CloseEditor()
    conf(lua, "totems.gnarly", False)
    DL(lua).OpenEditor(i)
    assert sb.same(lua, c._points[len(seq(c._points))].rel, c1(lua)), "with Preset 2 off the card hangs on Preset 1"
    conf(lua, "totems.gnarly", True)
    assert float(c._w) >= 198.0, "the card is narrower than its design width"
    DL(lua).OpenEditor(i)
    script(lua, rows(lua)[0], "OnClick")
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
    for key in ("fire", "earth", "water", "air", "preset1", "preset2"):
        for p in seq(btn(lua, key)._points):
            assert p.rel is None or not sb.same(lua, p.rel, c), "a secure button is anchored to the card"


# ---------------------------------------------------------------------------------------------
# Checks: seats
# ---------------------------------------------------------------------------------------------


def check_the_tab_grows_by_a_cell_for_each_preset_cell_that_is_on_and_the_buff_and_mana_regen_tabs_follow(scale):
    lua = boot(scale, tabs=True)
    cs = csh.cs(lua)
    host = g(lua).FSTotemBar
    w7 = 2 * PAD + 7 * BTN + 6 * GAP
    w8 = 2 * PAD + 8 * BTN + 7 * GAP
    approx(float(host._w) / scale, w8, "host width in design px", 0.01)
    approx(w8, 349.6, "the tab with both cells on is 349.6 px", 1e-6)
    assert TB(lua).Cols() == 8
    d = c1(lua)
    q = d._points[1]
    assert sb.same(lua, q.rel, host) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT")
    approx(q.x, (PAD + 6 * (BTN + GAP)) * scale, "Preset 1 x"), approx(q.y, 5 * scale, "Preset 1 y")
    approx(float(d._w), BTN * scale, "Preset 1 width"), approx(float(d._h), BTN * scale, "Preset 1 height")
    assert shown(d)
    g8 = btn(lua, "preset2")._points[1]
    approx(g8.x, (PAD + 7 * (BTN + GAP)) * scale, "Preset 2 x")
    buff_x = 36 + w8 + 16
    approx(g(lua).FSBuffTab._points[1].x, buff_x * scale, "buff tab follows", 0.5 * scale)
    five_x = buff_x + 92.8 + 16
    approx(g(lua).FSFiveSecondTab._points[1].x, five_x * scale, "mana regen tab follows", 0.5 * scale)
    # Preset 1 off puts them back
    conf(lua, "totems.dial", False)
    approx(float(host._w) / scale, w7, "host width with Preset 1 off", 0.01)
    assert not shown(d), "Preset 1 stayed with its switch off"
    g7 = btn(lua, "preset2")._points[1]
    approx(g7.x, (PAD + 6 * (BTN + GAP)) * scale, "Preset 2 steps into column 7")
    approx(g(lua).FSBuffTab._points[1].x, (36 + w7 + 16) * scale, "buff tab with one cell", 0.5 * scale)
    conf(lua, "totems.gnarly", False)
    approx(float(host._w) / scale, 2 * PAD + 6 * BTN + 5 * GAP, "host width back to six", 0.01)
    assert not shown(btn(lua, "preset2")), "Preset 2 stayed with its switch off"
    approx(g(lua).FSBuffTab._points[1].x, 316 * scale, "buff tab back", 0.5 * scale)
    approx(g(lua).FSFiveSecondTab._points[1].x, (316 + 92.8 + 16) * scale, "mana regen tab back", 0.5 * scale)
    conf(lua, "totems.dial", True), conf(lua, "totems.gnarly", True)
    assert shown(c1(lua)) and shown(btn(lua, "preset2"))
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
    for key in ("preset1", "preset2"):
        b = btn(lua, key)
        for name in ("shift-type1", "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1",
                     "ctrl-shift-type1"):
            assert b._attrs[name] == "", f"{key}: {name} would fall back to the plain click and drop a totem"
    d = c1(lua)
    assert d._attrs["type1"] == "macro" and d._attrs["ctrl-type1"] is None, "a plain ctrl click keeps dropping"
    # a script change keeps the blanks; clearing the preset's totems clears the script but not the blanks
    PS(lua).SetTotem(1, "fire", None)
    assert d._attrs["alt-ctrl-shift-type1"] == ""


def check_the_cell_tips_say_a_shift_keybind_edits():
    lua = boot()
    for name in ("preset1", "preset2"):
        assert "keybind that includes Shift" in str(PS(lua).SETTINGS[name].tip), name


def check_a_character_key_that_cannot_be_read_never_saves_under_a_made_up_one():
    for unreadable in ("nil", "__SECRET", '""'):
        lua = boot()
        run(lua, f"ForeverSTUwaveDB.totemPresets = nil; __guid = UnitGUID; UnitGUID = function() return {unreadable} end")
        P = PS(lua)
        assert P.Get(1) is None and P.Writable() is False
        r = P.Create(1)
        assert not r or r[0] is None, "an edit went through with no character key"
        assert not P.SetColor(1, 3) or P.SetColor(1, 3)[0] is False, "a colour was chosen with no character key"
        assert "editable in a moment" in str(P.Refusal()), "the refusal blames the session instead of the moment"
        db = g(lua).ForeverSTUwaveDB
        assert db.totemPresets is None, f"{unreadable}: presets were saved with no character key"
        run(lua, "UnitGUID = __guid")
        assert P.Writable() is True and P.Get(1) is None
        assert P.Create(1), "creating works once the key reads"
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
    two_presets(lua)
    run(lua, "__kl = 0; local k = FS.TotemBar.KnownList; FS.TotemBar.KnownList = function(...) __kl = __kl + 1 return k(...) end")
    fire(lua, "SPELLS_CHANGED")                    # a cold cache
    for _ in range(20):
        DL(lua).Paint(c1(lua))
        DL(lua).Paint(c2(lua))
    scans = int(g(lua).__kl)
    assert 0 < scans <= 8, f"{scans} spellbook scans over forty repaints of the cells"
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
        scans = int(g(lua).__kl)
        fire(lua, event)
        DL(lua).Paint(c1(lua))
        assert int(g(lua).__kl) > scans, f"{event} did not drop the cached list"
    enter_combat(lua)
    scans = int(g(lua).__kl)
    leave_combat(lua)
    DL(lua).Paint(c1(lua))
    assert int(g(lua).__kl) > scans, "regen did not drop the cached list"
    scans = int(g(lua).__kl)
    TB(lua).Sync()
    assert int(g(lua).__kl) > scans, "a sync did not drop the cached list"


def check_the_cells_stand_right_of_the_six_and_the_buttons_keep_their_slots():
    lua = boot()
    for i, key in enumerate(("fire", "earth", "water", "air", "set", "recall"), 1):
        q = g(lua)[f"FSTotemButton{i}"]._points[1]
        approx(q.x, PAD + (i - 1) * (BTN + GAP), f"button {i} x")
    assert str(c1(lua).fsKey) == "preset1" and c1(lua).commandName == "CLICK FSTotemButton7:LeftButton"
    assert str(g(lua)["BINDING_NAME_CLICK FSTotemButton7:LeftButton"]) == "Totem preset 1"
    assert str(btn(lua, "preset2").fsKey) == "preset2" and btn(lua, "preset2").commandName == "CLICK FSTotemButton8:LeftButton"
    assert str(g(lua)["BINDING_NAME_CLICK FSTotemButton8:LeftButton"]) == "Totem preset 2"
    names = [b.get("name") for b in ET.parse(BINDINGS).getroot().findall("Binding")]
    assert "CLICK FSTotemButton8:LeftButton" in names, names


def check_a_rescale_resizes_and_reseats_the_face():
    lua = boot(1.0, tabs=True)
    make(lua)
    look(lua)
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    d = c1(lua)
    approx(float(d._w), BTN * s, "Preset 1 width after a rescale")
    q = d._points[1]
    approx(q.x, (PAD + 6 * (BTN + GAP)) * s, "Preset 1 x after a rescale")
    approx(float(btn(lua, "preset1").fsRail._h), 12 * s, "plate height after a rescale")
    approx(float(g(lua).FSTotemBar._w), (2 * PAD + 8 * BTN + 7 * GAP) * s, "host width after a rescale")
    approx(g(lua).FSBuffTab._points[1].x, (36 + 2 * PAD + 8 * BTN + 7 * GAP + 16) * s, "buff tab after a rescale", 0.5)


# ---------------------------------------------------------------------------------------------
# Checks: two cells side by side
# ---------------------------------------------------------------------------------------------


def check_two_cells_with_the_same_first_totem_count_a_cast_for_the_one_pressed():
    lua = boot()
    P = PS(lua)
    make(lua, picks={"fire": "Searing Totem", "earth": "Stoneskin Totem", "water": None, "air": None}, name="ONE")
    make(lua, picks={"fire": "Magma Totem", "earth": "Stoneskin Totem", "water": None, "air": None}, name="TWO")
    cast_name(lua, "Stoneskin Totem", "preset2")
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (0, 1), "the cast went to the wrong cell"
    advance(lua, 3)
    cast_name(lua, "Stoneskin Totem", "preset1")
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (1, 1)
    # both pressed, the later press owns the cast
    run(lua, "FS.TotemPresets.ResetSteps()")
    click(lua, c1(lua), "LeftButton", False)
    advance(lua, 0.3)
    click(lua, c2(lua), "LeftButton", False)
    cast_raw(lua, "Stoneskin Totem")
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (0, 1)


def check_each_cell_steps_its_own_preset_whatever_the_other_is_doing_in_and_out_of_combat():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    cast_name(lua, "Searing Totem", "preset1")
    cast_name(lua, "Tremor Totem", "preset2")
    assert tuple(P.Progress("preset1")) == (0, 4), "Preset 1's first totem is Stoneskin: Searing is out of turn"
    assert tuple(P.Progress("preset2")) == (1, 3)
    cast_name(lua, "Stoneskin Totem", "preset1")
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (1, 1), "one cell's step moved the other's"
    enter_combat(lua)
    n = blocked(lua)
    cast_name(lua, "Magma Totem", "preset2")
    assert blocked(lua) == n, "a press tried a protected write"
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (1, 2)
    leave_combat(lua)
    assert (P.Progress("preset1")[0], P.Progress("preset2")[0]) == (0, 0), "combat ended and a step stayed"


def check_clear_is_one_full_width_button_padded_symmetrically_and_snapped_to_whole_pixels():
    for es, sc in ((1.0, 1.0), (0.64, 1.0), (1.3333333, 1.25), (1.2, LIVE_SCALE)):
        lua = boot(sc)
        set_display(lua, es, sc)
        i = make(lua)
        DL(lua).OpenEditor(i)
        c = card(lua)
        b = c.clear
        w, h = float(b._w), float(b._h)
        edge = 2 * round(8 * sc * es) / es
        assert abs(w - (float(c._w) - edge)) < 1e-6, f"es {es}: CLEAR is {w} wide in a card of {float(c._w)}"
        assert abs(w * es - round(w * es)) < 1e-6 and round(w * es) % 2 == 0, f"es {es}: CLEAR is {w * es} pixels wide"
        assert abs(h * es - round(h * es)) < 1e-6 and round(h * es) % 2 == 0, f"es {es}: CLEAR is {h} tall"
        p = b.text._points[1]
        assert (p.point, p.relPoint) == ("CENTER", "CENTER") and not float(p.x or 0) and not float(p.y or 0), \
            "the label is not centred"
        assert sb.same(lua, p.rel, b)
        before = w
        script(lua, b, "OnClick")
        assert str(b.text._text) == "SURE?" and float(b._w) == before, "SURE? changed the width"
        assert abs(float(c.name._w) - (float(c._w) - edge)) < 1e-6 and abs(float(rows(lua)[0]._w) - (float(c._w) - edge)) < 1e-6


def sw_look(sw):
    """Everything a swatch paints: fill, outer ring, inner ring (shown only when selected), dot colour and pixel size."""
    return {"fill": rgba(sw.fill), "ring": [rgba(e) for e in seq(sw.edges)], "inner": [rgba(e) for e in seq(sw.inner)],
            "inner_shown": all(shown(e) for e in seq(sw.inner)), "dot": rgba(sw.dot), "dotw": round(float(sw.dot._w), 4),
            "alpha": float(sw._alpha)}


def swatches(lua):
    return seq(card(lua).swatches)


def check_the_card_has_a_row_of_seven_outline_swatches_that_choose_the_slots_colour():
    lua = boot()
    P = PS(lua)
    a, b = two_presets(lua)
    DL(lua).OpenEditor(1)
    c = card(lua)
    sws = swatches(lua)
    assert len(sws) == 7 and all(shown(w) for w in sws)
    assert str(c.outline._text) == "OUTLINE" and str(c.label._text) == "DROP ORDER"
    for k, (name, hx) in enumerate(PALETTE):
        want = hex_rgb(hx)
        close(rgba(sws[k].dot), want, f"swatch {name} dot")
        assert sws[k].fsColor == k + 1
    # the selected swatch (the slot's colour: cyan) wears a white outer ring, an inner ring in its colour and a bigger dot
    sel = sw_look(sws[0])
    assert all(e[:3] == (1.0, 1.0, 1.0) and e[3] == 1.0 for e in sel["ring"]), "the selected ring is not white"
    assert sel["inner_shown"] and all(abs(e[3] - 1) < 1e-6 for e in sel["inner"])
    close(sel["inner"][0], hex_rgb("22e0ff"), "selected inner ring")
    other = sw_look(sws[1])
    assert not other["inner_shown"] and sel["dotw"] > other["dotw"], "only the selected swatch has the big dot"
    assert abs(other["ring"][0][3] - 0.6) < 1e-3 and abs(other["dot"][3] - 0.9) < 1e-3, "an unselected swatch is quiet"
    close(other["ring"][0], hex_rgb("ff2e97"), "unselected ring colour")
    close(other["fill"], mix3(ROW_FILL, hex_rgb("ff2e97"), 0.22), "unselected fill")
    close(sel["fill"], mix3(ROW_FILL, hex_rgb("22e0ff"), 0.35), "selected fill")
    # a click chooses the colour for this slot only, the cell follows, the selection moves
    script(lua, sws[4], "OnClick")
    assert (P.Color(1), P.Color(2)) == (5, 2)
    close(ring_of(c1(lua)), hex_rgb("39ff14"), "the cell border follows the swatch")
    assert sw_look(swatches(lua)[4])["inner_shown"] and not sw_look(swatches(lua)[0])["inner_shown"]
    DL(lua).OpenEditor(2)
    assert sw_look(swatches(lua)[1])["inner_shown"] and not sw_look(swatches(lua)[4])["inner_shown"], "the card did not follow the slot"
    # an unset slot takes a colour too, and CLEAR keeps it
    DL(lua).CloseEditor()
    P.Clear(2)
    DL(lua).OpenEditor(2)
    script(lua, swatches(lua)[6], "OnClick")
    assert P.Color(2) == 7 and P.Get(2) is None
    close(vtx(btn(lua, "preset2").fsBar), MUTED, "an unset cell keeps the muted underline whatever its colour")


def check_the_swatches_light_on_hover_and_press_restore_and_dim_while_the_presets_cannot_be_saved():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    DL(lua).OpenEditor(i)
    sws = swatches(lua)
    plain = sws[2]
    base = sw_look(plain)
    script(lua, plain, "OnEnter")
    hov = sw_look(plain)
    close(hov["fill"], mix3(ROW_FILL, hex_rgb("a855f7"), 0.35), "hover fill")
    assert hov["ring"][0][3] == 1.0 and hov["dot"][3] == 1.0 and not hov["inner_shown"]
    script(lua, plain, "OnMouseDown")
    pre = sw_look(plain)
    close(pre["fill"], mix3(ROW_FILL, hex_rgb("a855f7"), 0.5), "pressed fill")
    assert pre["ring"][0][3] == 1.0
    script(lua, plain, "OnMouseUp")
    assert sw_look(plain) == hov
    script(lua, plain, "OnLeave")
    assert sw_look(plain) == base, "leaving did not restore the swatch"
    script(lua, plain, "OnEnter")
    script(lua, plain, "OnMouseDown")
    script(lua, plain, "OnLeave")
    assert sw_look(plain) == base, "leaving with the button down kept a look"
    script(lua, plain, "OnEnter")
    DL(lua).CloseEditor()
    script(lua, plain, "OnHide")
    assert sw_look(plain) == base, "hiding kept the hover look"
    # a selected swatch keeps its white ring on hover
    DL(lua).OpenEditor(i)
    selected = swatches(lua)[0]
    sbase = sw_look(selected)
    script(lua, selected, "OnEnter")
    assert sw_look(selected)["ring"] == sbase["ring"] and sw_look(selected)["inner_shown"]
    script(lua, selected, "OnLeave")
    # disabled: dimmed, no clicks, no reaction, and a click that arrives is refused with the reason
    lock_presets(lua)
    DL(lua).RefreshCard()
    for w in swatches(lua):
        assert w._enabled is False and float(w._alpha) == 0.4, "a swatch stayed live while the presets cannot be saved"
    dis = sw_look(plain)
    script(lua, plain, "OnEnter")
    script(lua, plain, "OnMouseDown")
    assert sw_look(plain) == dis, "a disabled swatch reacted to the mouse"
    script(lua, plain, "OnMouseUp")
    script(lua, plain, "OnLeave")
    run(lua, "__errors = {}")
    click(lua, plain)
    assert errors(lua) == ["saving is off"] and P.Color(i) == 1
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    assert all(w._enabled is not False and float(w._alpha) == 1 for w in swatches(lua))
    click(lua, plain)
    assert P.Color(i) == 3
    # every swatch texture is snapped to the pixel grid
    for w in swatches(lua):
        for group in (w.edges, w.inner):
            for t in seq(group):
                assert t._snap is True and float(t._bias) == 0
        assert w.fill._snap is True and w.dot._snap is True


def check_the_card_layout_matches_the_mockup_on_whole_pixels_at_every_scale():
    for es, sc in ((1.0, 1.0), (0.64, 1.0), (1.3333333, 1.25), (1.5, 1.0), (2.2, 1.0), (1.2, LIVE_SCALE)):
        lua = boot(sc)
        set_display(lua, es, sc)
        i = make(lua)
        DL(lua).OpenEditor(i)
        c = card(lua)
        pw = lambda v: float(v) * es
        whole = lambda v: abs(pw(v) - round(pw(v))) < 1e-6
        sws = swatches(lua)
        sizes = {round(pw(w._w)) for w in sws}
        assert len(sizes) == 1 and sizes.pop() % 2 == 0 and all(whole(w._w) and whole(w._h) for w in sws), f"es {es}: swatch size"
        xs = [pw(w._points[1].x) for w in sws]
        ys = {pw(w._points[1].y) for w in sws}
        steps = {round(xs[k + 1] - xs[k], 6) for k in range(6)}
        assert len(steps) == 1 and all(abs(x - round(x)) < 1e-6 for x in xs) and len(ys) == 1, f"es {es}: swatch pitch {steps}"
        assert abs(xs[0] - round(8 * sc * es)) < 1e-6, f"es {es}: the first swatch is not at the left margin"
        assert abs(steps.pop() - 27 * sc * es) <= 1, f"es {es}: swatch pitch is off the mockup's 27"
        # the dot is centred in its swatch (both even)
        for w in sws:
            assert round(pw(w.dot._w)) % 2 == 0 and whole(w.dot._w)
        # the order from top: title, name, OUTLINE, swatches, DROP ORDER, rows, CLEAR
        assert -pw(c.name._points[1].y) < -pw(sws[0]._points[1].y) < -pw(rows(lua)[0]._points[1].y)
        assert -pw(c.outline._points[1].y) < -pw(sws[0]._points[1].y) < -pw(c.label._points[1].y) < -pw(rows(lua)[0]._points[1].y)
        if es == 1.0:
            assert float(c._h) == 232 and float(c._w) == 198, f"card {c._w}x{c._h}"
            assert -float(sws[0]._points[1].y) == 56 and float(sws[0]._w) == 20 and float(sws[1]._points[1].x) - float(sws[0]._points[1].x) == 27
            assert -float(rows(lua)[0]._points[1].y) == 94 and -float(rows(lua)[3]._points[1].y) == 94 + 81
            assert float(rows(lua)[0]._h) == 24 and float(c.clear._h) == 18
            assert -float(c.outline._points[1].y) == 45 and -float(c.label._points[1].y) == 82


def dash_pixels(tile, es):
    """The shown dash textures of a tile as pixel rects (x, y, w, h) from its top left, checked to be whole pixels."""
    out = []
    for t in seq(tile.dashes):
        if not shown(t):
            continue
        p = t._points[1]
        r = (float(p.x) * es, -float(p.y) * es, float(t._w) * es, float(t._h) * es)
        assert all(abs(v - round(v)) < 1e-6 for v in r), f"a dash is off the pixel grid: {r}"
        assert t._snap is True and float(t._bias) == 0
        out.append(tuple(round(v) for v in r))
    return out


def check_a_left_out_row_has_a_dashed_muted_box_and_a_small_dashes_label_and_no_ring():
    lua = boot()
    set_display(lua, 1.0, 1.0)
    i = make(lua, picks={"fire": None}, name="MELEE")
    DL(lua).OpenEditor(i)
    r = rows(lua)
    left, kept = r[3], r[0]
    assert str(left.label._text) == "left out" and str(left.tile.text._text) == "--"
    assert shown(left.tile.text) and left.tile.text._mono.size == 9, "the dashes label is not size 9"
    close(tuple(float(x) for x in seq(left.tile.text._mono.color)), MUTED, "left out dashes label")
    # the ring of a set row (0.35) is hidden here, and the dashed box takes its place
    assert all(rgba(e)[3] == 0 for e in seq(left.tile.hl)), "a left out row shows the 0.35 ring"
    dashes = [t for t in seq(left.tile.dashes) if shown(t)]
    assert dashes and all(abs(rgba(t)[3] - 0.6) < 1e-6 for t in dashes)
    for t in dashes:
        close(rgba(t)[:3], MUTED, "dash colour")
    assert not any(shown(t) for t in seq(kept.tile.dashes)), "a set row shows dashes"
    assert rgba(kept.tile.hl[1])[3] == 0.35
    # the mockup's box: 22 x 22 pixels, 2 on 2 off along the top and bottom, one pixel thick
    px = dash_pixels(left.tile, 1.0)
    w, h = round(float(left.tile._w)), round(float(left.tile._h))
    top = sorted(x for x, y, dw, dh in px if y == 0 and dh == 1)
    assert top == [0, 4, 8, 12, 16, 20] and all(dw == 2 for x, y, dw, dh in px if y == 0 and dh == 1 and x < 20), (w, top)
    assert sorted(x for x, y, dw, dh in px if y == h - 1) == top, "the bottom run differs from the top"
    left_runs = sorted((y, dh) for x, y, dw, dh in px if x == 0 and dw == 1 and 0 < y < h - 1)
    assert left_runs[0] == (1, 1) and left_runs[1] == (4, 2), left_runs
    assert sorted((y, dh) for x, y, dw, dh in px if x == w - 1 and 0 < y < h - 1) == left_runs
    # filling the element hides the dashes and restores the ring; leaving it out again brings them back
    P = PS(lua)
    P.SetTotem(i, "fire", IDS["Magma Totem"])
    for row in rows(lua):
        assert not any(shown(t) for t in seq(row.tile.dashes)), "a full card shows dashes"
        assert rgba(row.tile.hl[1])[3] == 0.35
    P.SetTotem(i, "fire", None)
    assert any(shown(t) for t in seq(rows(lua)[3].tile.dashes))
    # a disabled row dims the box with the rest; the box is still snapped at a fractional scale
    lock_presets(lua)
    DL(lua).RefreshCard()
    assert float(rows(lua)[3].tile._alpha) == 0.4
    lock_presets(lua, False)
    lua = boot(LIVE_SCALE)
    set_display(lua, 1.2, LIVE_SCALE)
    DL(lua).OpenEditor(2)
    assert dash_pixels(rows(lua)[0].tile, 1.2), "no dashes on an unset slot's rows at the live scale"


def check_the_selected_swatchs_inner_ring_sits_one_pixel_inside_the_white_outer_ring():
    for es, sc in ((1.0, 1.0), (1.2, LIVE_SCALE), (2.2, 1.0)):
        lua = boot(sc)
        set_display(lua, es, sc)
        make(lua)
        DL(lua).OpenEditor(1)
        sw = swatches(lua)[0]
        outer, inner = sw.edges, sw.inner
        thick = float(outer[1]._h)
        assert abs(thick * es - round(thick * es)) < 1e-6 and round(thick * es) >= 1
        for k in (1, 2, 3, 4):
            o, n = outer[k]._points[1], inner[k]._points[1]
            assert float(o.x) == 0 and float(o.y) == 0, "the outer ring is not on the border"
            assert abs(abs(float(n.x)) - thick) < 1e-9 or abs(abs(float(n.y)) - thick) < 1e-9, \
                f"es {es}: inner edge {k} is not inset by one ring thickness"
        n1 = inner[1]._points[1]
        assert abs(float(n1.x) - thick) < 1e-9 and abs(float(n1.y) + thick) < 1e-9, "the inner top left is not one ring inside"
        n4 = inner[4]._points[1]
        assert abs(float(n4.x) + thick) < 1e-9 and abs(float(n4.y) + thick) < 1e-9, "the inner right edge is not inset"
        assert sw_look(sw)["inner_shown"] and all(rgba(e)[:3] == (1.0, 1.0, 1.0) for e in seq(outer)), \
            "the white outer ring is covered"


def check_a_disabled_row_ignores_its_arrows_hover_and_a_swatch_tooltip_goes_with_the_card():
    lua = boot()
    i = make(lua)
    DL(lua).OpenEditor(i)
    row = rows(lua)[0]
    lock_presets(lua)
    DL(lua).RefreshCard()
    dim = [rgba(e) for e in seq(row.edges)]
    script(lua, row.down, "OnEnter")
    assert [rgba(e) for e in seq(row.edges)] == dim, "an arrow of a disabled row lit the row's edge"
    script(lua, row.down, "OnLeave")
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    # the swatch tooltip: shown on hover, hidden on leave, and hidden when the card closes with the mouse still on it
    tip = g(lua).GameTooltip
    run(lua, "GameTooltip:Hide(); GameTooltip._lines = {}")
    sw = swatches(lua)[2]
    script(lua, sw, "OnEnter")
    assert shown(tip) and lines(lua) == ["VIOLET"], lines(lua)
    script(lua, sw, "OnLeave")
    assert not shown(tip), "the swatch tooltip stayed after the mouse left"
    script(lua, sw, "OnEnter")
    DL(lua).CloseEditor()
    assert not shown(tip), "the swatch tooltip stayed after the card closed"
    DL(lua).OpenEditor(i)
    script(lua, swatches(lua)[2], "OnEnter")
    enter_combat(lua)
    assert not shown(card(lua)) and not shown(tip), "the swatch tooltip stayed after a combat close"


def check_each_drop_order_row_is_one_button_for_its_whole_width_with_the_arrows_on_top():
    lua = boot()
    P = PS(lua)
    i = make(lua, picks={"fire": None}, name="MELEE")
    DL(lua).OpenEditor(i)
    r = rows(lua)
    for row in r:
        assert row._kind == "Button" or str(row._kind) == "Button", "a row is not a button"
        assert row.tile._enabled is None or row.tile._enabled is not False
        assert not getattr(row.tile, "_mouse", False), "the icon box takes the mouse the row should get"
        for arrow in (row.up, row.down):
            assert float(arrow._level) > float(row._level), "an arrow is not above its row"
    # the click opens the chooser for that row's element from anywhere on the row
    script(lua, r[1], "OnClick")
    ch = DL(lua).Chooser()
    assert shown(ch) and str(ch.tiles[1].fsElement) == "water", "the row did not open its own element's chooser"
    # an arrow's click moves the row and does not open anything
    run(lua, "FS.TotemDial.Chooser():Hide()")
    script(lua, r[0].down, "OnClick")
    assert order_of(lua, i)[:2] == ["water", "earth"] and not shown(DL(lua).Chooser())
    # a row left out shows no arrows and still opens the chooser
    left = rows(lua)[3]
    assert not shown(left.up) and not shown(left.down)
    script(lua, left, "OnClick")
    assert shown(DL(lua).Chooser())


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
           [(f"down{n}", r.down) for n, r in enumerate(rows(lua)) if shown(r.down)] + [("clear", c.clear)]
    for label, b in live:
        drive(lua, b, label)
    # the armed CLEAR has a look of its own, with its own hover
    script(lua, c.clear, "OnClick")
    assert str(c.clear.text._text) == "SURE?"
    armed, armed_hover, _ = drive(lua, c.clear, "armed clear")
    DL(lua).RefreshCard()
    assert look_of(c.clear) == armed, "a repaint changed the armed look"
    DL(lua).CloseEditor()
    DL(lua).OpenEditor(i)
    c = card(lua)
    # disabled: the frame is dimmed and the mouse changes nothing
    run(lua, "__refusal = FS.TotemPresets.Refusal; FS.TotemPresets.Refusal = function() return 'saving is off' end")
    DL(lua).RefreshCard()
    for label, b in [("clear", c.clear)] + [(f"up{n}", r.up) for n, r in enumerate(rows(lua)) if shown(r.up)]:
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
    assert float(c.clear._alpha) == 1
    # an empty slot has nothing to clear: the button is dimmed and takes no click
    P.Clear(i)
    DL(lua).RefreshCard()
    assert float(c.clear._alpha) == 0.4 and c.clear._enabled is False


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
    # the whole row is the button: hover tints its fill 16% toward the violet ring and takes the ring to full alpha, pressed
    # tints 32%, and the icon box ring (element colour) goes from .35 to .9
    row = rows(lua)[0]
    t = row.tile
    ring0, row0, fill0 = [rgba(e) for e in seq(t.hl)], [rgba(e) for e in seq(row.edges)], rgba(row.fill)
    assert ring0[0][3] == 0.35 and row0[0][3] == 0.35
    script(lua, row, "OnEnter")
    assert rgba(t.hl[1])[3] == 0.9 and rgba(row.edges[1])[3] == 1.0
    close(rgba(row.fill)[:3], mix3(ROW_FILL, VIOLET, 0.16), "row hover fill")
    script(lua, row, "OnMouseDown")
    assert rgba(t.hl[1])[3] == 0.9 and rgba(row.edges[1])[3] == 1.0
    close(rgba(row.fill)[:3], mix3(ROW_FILL, VIOLET, 0.32), "row pressed fill")
    script(lua, row, "OnMouseUp")
    script(lua, row, "OnLeave")
    assert [rgba(e) for e in seq(t.hl)] == ring0 and [rgba(e) for e in seq(row.edges)] == row0 and rgba(row.fill) == fill0
    # an arrow under the mouse lights only the row's edge
    script(lua, row.down, "OnEnter")
    assert rgba(row.edges[1])[3] == 1.0 and rgba(row.fill) == fill0, "an arrow tinted the row or did not light its edge"
    script(lua, row.down, "OnLeave")
    assert [rgba(e) for e in seq(row.edges)] == row0
    # the chooser tiles
    script(lua, row, "OnClick")
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
    assert float(n._alpha) == 0.4 and float(t._alpha) == 0.4 and float(row.fill._alpha) == 0.4 and row._enabled is False
    script(lua, n, "OnEnter")
    script(lua, row, "OnEnter")
    assert abs(rgba(row.edges[1])[3] - 0.14) < 1e-3 and abs(rgba(t.hl[1])[3] - 0.14) < 1e-3, "a disabled row lit up"
    close(rgba(row.fill)[:3], fill0[:3], "a disabled row tinted")
    assert rgba(c.nameEdges[1])[3] == 0.4


def shift_click(lua, button):
    run(lua, "__shift = true")
    click(lua, button, "LeftButton", True)
    click(lua, button, "LeftButton", False)
    run(lua, "__shift = false")


def put_b(lua):
    """Seeds Preset 2 (Tremor, Magma, Mana Spring) straight into the saved table, so nothing is written to set 2 until the
    test syncs the tab itself."""
    run(lua, f'ForeverSTUwaveDB.totemPresets[{GUID!r}].slots[2] = {{ name = "CASTER", picks = {{ earth = {IDS["Tremor Totem"]}, '
             f'fire = {IDS["Magma Totem"]}, water = {IDS["Mana Spring Totem"]} }}, order = {{ "earth", "fire", "water" }} }}')
    return 2


def set2_world(lua):
    """Preset 1 made, Preset 2 seeded and not yet synced."""
    a = make(lua, picks={"fire": "Searing Totem", "earth": "Stoneskin Totem", "water": "Healing Stream Totem",
                         "air": "Grounding Totem"}, name="MELEE")
    return a, put_b(lua)


def set2_ids(*elements):
    return {e: tbh.action_id(tbh.SLOT[e], mc_set=2) for e in elements}


def check_preset_two_is_written_into_set_two_once_and_read_back():
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, "__mc.calls = {}")
    TB(lua).Sync()
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
    # set 1 is the player's: no preset writes it
    assert pick_of(lua, "fire") == "Searing Totem" and pick_of(lua, "earth") == "Stoneskin Totem"
    line = str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    assert "set2=ok 3/3" in line and "set1Intact=true" in line, line


def slot2(lua, element):
    return g(lua).__mc.slots[tbh.action_id(tbh.SLOT[element], mc_set=2)]


def check_a_spell_that_comes_back_is_written_to_set_two_again():
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    TB(lua).Sync()
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"]
    P.SetTotem(b, "fire", IDS["Searing Totem"])
    assert int(slot2(lua, "fire")) == IDS["Searing Totem"]
    P.SetTotem(b, "fire", IDS["Magma Totem"])
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"], "Magma, Searing, Magma left the slot on Searing"
    assert P.Set2.state == "ok"


def check_a_set_two_send_that_has_not_shown_is_looked_at_again_and_sent_again_a_few_times():
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    ids = set(set2_ids("earth", "fire", "water").values())

    def sends():
        return [int(c[1]) for c in seq(g(lua).__mc.calls) if int(c[1]) in ids]

    run(lua, "__mc.delay = true")
    TB(lua).Sync()
    assert P.Set2.state == "partial" and len(sends()) == 3
    # the slot updates late: the scheduled look sees it with no Sync from outside
    run(lua, "__mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state == "ok", "the late update was not noticed by the scheduled look"
    assert "set2=ok 3/3" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a slot that never takes the spell is sent again after each settle time, at most SET2_ATTEMPTS times
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, "__mc.delay = true")
    TB(lua).Sync()
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
        a, b = set2_world(lua)
        run(lua, "__mc.delay = true")
        TB(lua).Sync()                         # set 2 sends queue: Magma, Tremor, Mana Spring
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


def check_a_pick_of_the_set_two_totem_inside_the_window_is_the_players_and_is_never_put_back():
    id1 = tbh.action_id(tbh.SLOT["fire"])

    def world():
        lua = boot()
        P = PS(lua)
        a, b = set2_world(lua)
        run(lua, "__mc.delay = true")
        TB(lua).Sync()                         # sends queue: Magma, Tremor, Mana Spring; window open
        return lua, P, a, b

    # a pick from the tab's picker does the same
    lua, P, a, b = world()
    TB(lua).Pick("fire", IDS["Magma Totem"])
    run(lua, "__mc_flush()")
    advance(lua, 1.2)
    assert P.Set2.state != "dead" and P.Set2.set1Intact is True, "a manual pick was blamed as a bleed"
    assert int(g(lua).__mc.slots[id1]) == IDS["Magma Totem"], "the manual pick was put back"


def check_a_set_two_slot_is_written_only_when_it_reads_back_holding_nothing_or_an_element_totem():
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    earth2 = tbh.action_id(tbh.SLOT["earth"], mc_set=2)
    fire2 = tbh.action_id(tbh.SLOT["fire"], mc_set=2)
    run(lua, f"__mc.slots[{earth2}] = 999999")                 # not a totem of the element
    run(lua, f"__mc.slots[{fire2}] = __ids['Searing Totem']")   # another totem of the element: replaced
    TB(lua).Sync()
    assert int(g(lua).__mc.slots[earth2]) == 999999, "a slot holding something else was overwritten"
    assert int(slot2(lua, "fire")) == IDS["Magma Totem"]
    assert P.Set2.state == "partial" and int(P.Set2.unproven) == 1
    assert "unproven=1" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a set 2 slot that cannot be read is not written either
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, f"local base = GetActionInfo; GetActionInfo = function(id) if id == {earth2} then return __SECRET end "
             "return base(id) end")
    run(lua, "__mc.calls = {}")
    TB(lua).Sync()
    assert earth2 not in [int(c[1]) for c in seq(g(lua).__mc.calls)], "an unreadable set 2 slot was written"
    assert int(P.Set2.unproven) == 1 and P.Set2.state == "partial"


def check_set_two_raising_inside_the_refresh_is_caught_and_the_state_is_still_saved():
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    TB(lua).Sync()
    run(lua, "FS.TotemBar.MC.Bar = function() error('boom') end")
    DL(lua).Refresh()
    assert P.Set2.state == "dead" and "raised" in str(P.Set2.why)
    assert "set2=dead" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line), "the state was not saved after the raise"


def check_a_press_is_used_up_by_the_cast_it_brought_and_a_reset_forgets_it():
    lua = boot()
    P = PS(lua)
    make(lua)
    cast_name(lua, "Stoneskin Totem")
    assert P.Progress("preset1")[0] == 1
    cast_raw(lua, "Searing Totem")
    assert P.Progress("preset1")[0] == 1, "one press advanced the record twice"
    # a reset (combat end) forgets a press that was still waiting for its cast
    lua = boot()
    P = PS(lua)
    make(lua)
    click(lua, c1(lua), "LeftButton", False)
    enter_combat(lua)
    leave_combat(lua)
    cast_raw(lua, "Stoneskin Totem")
    assert P.Progress("preset1")[0] == 0, "a press from before the reset counted for a later cast"


def check_set_two_waits_for_what_it_needs_and_never_writes_in_combat():
    # the set 2 setting off, Preset 2's cell off
    for how in ("gnarlySet2", "gnarly"):
        lua = boot()
        P = PS(lua)
        a, b = set2_world(lua)
        conf(lua, f"totems.{how}", False)
        run(lua, "__mc.calls = {}")
        TB(lua).Sync()
        ids = set(set2_ids("earth", "fire", "water", "air").values())
        assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids], f"{how} off still wrote set 2"
        assert P.Set2.state == "off"
    # Call of the Ancestors not known: nothing is written, and it is tried again once it is
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, '__learned[__spells["Call of the Ancestors"]] = nil')
    run(lua, "__mc.calls = {}")
    TB(lua).Sync()
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids] and P.Set2.state == "wait"
    run(lua, '__learned[__spells["Call of the Ancestors"]] = true')
    TB(lua).Sync()
    assert [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids] and P.Set2.state == "ok"
    # in combat the call is never made
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    TB(lua).Sync()
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
    a, b = set2_world(lua)
    run(lua, "__native(500)")
    run(lua, "__mc.calls = {}")
    TB(lua).Sync()
    ids = set(set2_ids("earth", "fire", "water", "air").values())
    assert not [c for c in seq(g(lua).__mc.calls) if int(c[1]) in ids], "set 2 was written on an unproven mapping"
    assert P.Set2.state == "dead" and "map" in str(P.Set2.why)
    assert "set2=dead" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)
    # a write that lands on set 1 as well: set 1 is put back and set 2 is dead for the session
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, "local base = SetMultiCastSpell\n"
             "SetMultiCastSpell = function(act, sp) base(act, sp); if act > (%d - 1) * 12 + 4 then base(act - 4, sp) end end" % tbh.BAR)
    TB(lua).Sync()
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
    a, b = set2_world(lua)
    run(lua, "__mc.throws = false; local base = SetMultiCastSpell\n"
             "SetMultiCastSpell = function(act, sp) if act > (%d - 1) * 12 + 4 then error('boom') end return base(act, sp) end" % tbh.BAR)
    TB(lua).Sync()
    TB(lua).Sync()
    assert P.Set2.state in ("partial", "ok", "off", "wait"), P.Set2.state
    assert P.Set2.state != "ok"
    lua = boot()
    P = PS(lua)
    a, b = set2_world(lua)
    run(lua, "__mc.delay = true")
    TB(lua).Sync()
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
    a, b = set2_world(lua)
    run(lua, "__mc.infoMode = 'secret'")
    TB(lua).Sync()
    assert P.Set2.state == "wait", "unreadable slots must write nothing"


# ---------------------------------------------------------------------------------------------
# Checks: the state line and hygiene
# ---------------------------------------------------------------------------------------------


def check_the_state_line_names_the_live_unknowns():
    lua = boot()
    P = PS(lua)
    i = make(lua)
    click(lua, c1(lua), "LeftButton", False)
    cast_name(lua, "Stoneskin Totem")
    P.SaveState()
    st = g(lua).ForeverSTUwaveDB.totemPresetState
    line = str(st.line)
    for part in ("presets=1", "colors=1,2", "preset1 type1=macro", "step=1/4", "presses=2", "casts=1",
                 "preset2 type1=none"):
        assert part in line, f"{part!r} not in {line!r}"
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
    run(lua, "__degradeCount = 0; ForeverSTUwaveDB = setmetatable({}, { __newindex = function() error('refused') end })")
    PS(lua).SaveState()
    assert int(g(lua).__degradeCount) == 0, "a refused state line write said something to chat"
    assert "could not be saved" in str(g(lua).__quiet.totempresets_state) and "refused" in str(g(lua).__quiet.totempresets_state), \
        "the refused write was not kept in the quiet degrade log with its error"
    # secret values from the cell buttons: no throw and no chat
    lua = boot()
    make(lua)
    run(lua, "__degradeCount = 0; for _, c in ipairs({ 'preset1', 'preset2' }) do local b = FS.TotemBar.Button(c); "
             "if b then b.GetAttribute = function() return __SECRET end end end")
    PS(lua).SaveState()
    assert int(g(lua).__degradeCount) == 0 and g(lua).FS.TotemPresets.P.warned.totempresets_state is None, \
        "secret attributes made the state line fail"
    assert "type1=none" in str(g(lua).ForeverSTUwaveDB.totemPresetState.line)


def check_a_throwing_listener_or_totem_api_never_breaks_a_press_or_a_sync():
    lua = boot()
    P = PS(lua)
    make(lua)
    run(lua, "FS.TotemPresets.OnEvent(function() error('boom') end)")
    click(lua, c1(lua), "LeftButton", False)
    cast_name(lua, "Stoneskin Totem")
    assert P.SetColor(1, 3) is True, "a throwing listener stopped an edit"
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


LIVE_SCALE = 0.8333     # the player's layout scale; with effective scale 0.64 and physical height 1440 one UI unit is 1.2 pixels


def set_display(lua, ppu, scale):
    """The physical pixels in one UI unit, built the way the client has it: an effective scale and a physical screen height
    (one UI unit is effective scale * physical height / 768 pixels). The player's real display is effective scale 0.64 with
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
    t = rows(lua)[0]
    before = (str(c.name._text), P.Get(i).name)
    lock_presets(lua)
    DL(lua).RefreshCard()
    assert float(t.tile._alpha) == 0.4 and t._enabled is False, "the dimmed pick row is still enabled"
    for label, b in [("pick cell", t), ("clear", c.clear)] + \
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
    live_click(lua, c.clear)
    live_click(lua, c.clear)
    assert shown(c) and P.Get(i) is not None and str(c.clear.text._text) == "CLEAR", "a dimmed footer button acted"
    # the chooser open when the refusal begins: its tiles dim, drop clicks, and a click that arrives says why
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    assert t._enabled is not False and float(t.tile._alpha) == 1
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
    t = rows(lua)[0]
    assert float(c.clear._alpha) == 0.4 and t._enabled is False and c.name._enabled is False
    lock_presets(lua, False)
    tick(lua)
    assert float(c.clear._alpha) == 1 and t._enabled is not False and c.name._enabled is not False and float(t.tile._alpha) == 1, \
        "the open card stayed locked after the refusal cleared"
    lock_presets(lua)
    tick(lua)
    assert float(c.clear._alpha) == 0.4 and t._enabled is False and c.name._enabled is False, "the open card did not lock"
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
    ring0, row0, fill0 = [rgba(e) for e in seq(t.hl)], [rgba(e) for e in seq(row.edges)], rgba(row.fill)
    script(lua, row, "OnEnter")
    script(lua, row, "OnMouseDown")
    assert rgba(row.edges[1])[3] == 1.0 and row.fsPressed
    script(lua, row, "OnLeave")
    assert not row.fsPressed and not row.fsHover
    assert [rgba(e) for e in seq(t.hl)] == ring0 and [rgba(e) for e in seq(row.edges)] == row0 and rgba(row.fill) == fill0, \
        "leaving with the button down kept a look"
    # hiding the card drops both states too
    script(lua, row, "OnEnter")
    script(lua, row, "OnMouseDown")
    script(lua, row, "OnHide")
    assert not row.fsPressed and not row.fsHover and rgba(row.fill) == fill0
    script(lua, row, "OnClick")
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
    script(lua, row, "OnEnter")
    assert [rgba(e) for e in seq(row.edges)] == dim, "a disabled row lit its edge on hover"
    script(lua, row, "OnLeave")
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    script(lua, row, "OnEnter")
    assert [rgba(e) for e in seq(row.edges)] != base, "a live row does not light its edge on hover"
    script(lua, row, "OnLeave")
    # every edge and glyph texture of the editor is snapped to the pixel grid, bias 0
    c = card(lua)
    script(lua, row, "OnClick")
    chooser = g(lua).FSTotemChooser
    groups = [c.edges, c.nameEdges, c.close.edges, c.close.glyph, c.clear.edges, row.edges, row.tile.hl,
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
    live_click(lua, row)
    chooser = g(lua).FSTotemChooser
    assert shown(chooser)
    lock_presets(lua)
    DL(lua).RefreshCard()
    tiles = [chooser.tiles[k] for k in range(1, len(seq(chooser.tiles)) + 1) if shown(chooser.tiles[k])]
    assert tiles and all(t._enabled is False and float(t._alpha) == 0.4 for t in tiles)
    run(lua, "FS.TotemDial.Chooser():Hide()")
    lock_presets(lua, False)
    DL(lua).RefreshCard()
    live_click(lua, row)
    assert shown(chooser)
    tiles = [chooser.tiles[k] for k in range(1, len(seq(chooser.tiles)) + 1) if shown(chooser.tiles[k])]
    assert tiles
    for t in tiles:
        assert t._enabled is not False and not t.fsDisabled, "a reopened chooser kept a tile disabled"
        assert float(t._alpha) == 1, "a reopened chooser kept a tile dimmed"
    picks = dict(PS(lua).Get(i).picks)
    click(lua, tiles[-1])
    assert not shown(chooser) and dict(PS(lua).Get(i).picks) != picks, "a reopened chooser tile did not take the click"


def check_the_pixel_unit_falls_through_to_the_screen_height_when_pixelutil_gives_nothing_usable():
    lua = boot()
    unit = lambda: g(lua).FS.FrameHelpers.PixelUnit(g(lua).UIParent)
    ees = "__ees = 0.64"
    run(lua, f"{ees}; GetPhysicalScreenSize = function() return 2560, 1440 end")
    want = 768 / 1440 / 0.64
    for label, setup in (
        ("PixelUtil throws", "PixelUtil = { GetPixelToUIUnitFactor = function() error('boom') end }"),
        ("PixelUtil answers nil", "PixelUtil = { GetPixelToUIUnitFactor = function() return nil end }"),
        ("PixelUtil answers NaN", "PixelUtil = { GetPixelToUIUnitFactor = function() return 0 / 0 end }"),
        ("PixelUtil answers infinity", "PixelUtil = { GetPixelToUIUnitFactor = function() return math.huge end }"),
        ("PixelUtil answers zero", "PixelUtil = { GetPixelToUIUnitFactor = function() return 0 end }"),
        ("PixelUtil answers a string", "PixelUtil = { GetPixelToUIUnitFactor = function() return 'x' end }"),
        ("no PixelUtil", "PixelUtil = nil"),
    ):
        run(lua, setup)
        got = unit()
        assert got is not None and abs(float(got) - want) < 1e-9, f"{label}: {got}, wanted {want}"
    # PixelUtil that works wins over the screen height
    run(lua, "PixelUtil = { GetPixelToUIUnitFactor = function() return 0.5 end }")
    assert abs(float(unit()) - 0.5 / 0.64) < 1e-9
    # nothing usable anywhere: nil, and PixelsPerUnit says 1
    run(lua, "PixelUtil = nil; GetPhysicalScreenSize = function() error('boom') end")
    assert unit() is None and float(g(lua).FS.FrameHelpers.PixelsPerUnit(g(lua).UIParent)) == 1.0
    run(lua, "GetPhysicalScreenSize = function() return 2560, 0 end")
    assert unit() is None


def check_a_bad_effective_scale_is_taken_as_1_by_the_pixel_unit():
    lua = boot()
    run(lua, "PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1440 end }")
    unit = lambda: float(g(lua).FS.FrameHelpers.PixelUnit(g(lua).UIParent))
    run(lua, "__ees = 1")
    base = unit()
    assert abs(base - 768 / 1440) < 1e-9
    for label, value in (("zero", "0"), ("negative", "-0.5"), ("NaN", "0 / 0"), ("infinity", "math.huge"), ("a string", "'x'"),
                         ("nil", "nil")):
        run(lua, f"__ees = {value}")
        got = unit()
        assert abs(got - base) < 1e-9, f"an effective scale of {label} gave {got}, wanted the scale 1 result {base}"
    run(lua, "__ees = 0.64")
    assert abs(unit() - base / 0.64) < 1e-9


CHECKS = [
    check_toc_lists_the_preset_files_after_the_totem_bar_and_bindings_declare_both_cells,
    check_the_settings_have_their_keys_defaults_tips_and_registered_defaults,
    check_only_a_shaman_gets_a_dial_and_a_world_without_the_files_keeps_six_buttons,
    check_two_slots_start_unset_with_default_colours_and_create_copies_the_four_buttons,
    check_names_are_letters_digits_and_spaces_up_to_eight_uppercased,
    check_a_saved_file_is_sanitised_when_it_loads,
    check_presets_are_kept_per_character,
    check_a_read_only_config_or_no_database_keeps_the_presets_in_memory_and_refuses_edits,
    check_the_old_file_moves_into_the_two_slots_once_with_the_extras_kept_in_retired,
    check_the_migrated_file_is_written_once_and_loading_it_again_changes_nothing,
    check_a_migrated_file_gives_each_cell_its_own_script,
    check_filling_leaving_out_and_moving_a_preset,
    check_the_first_totem_picked_on_an_unset_slot_makes_the_preset_named_for_its_number,
    check_every_edit_is_refused_in_combat_and_the_editor_will_not_open,
    check_the_outline_colour_is_a_cell_setting_saved_per_slot_and_kept_when_a_preset_is_cleared,
    check_clear_empties_a_preset_keeps_its_colour_and_resets_only_its_own_step,
    check_a_totem_not_learned_yet_is_skipped_and_stays_locked,
    check_the_script_behind_the_click_is_a_cast_sequence_that_restarts_with_combat_and_idle,
    check_each_cell_carries_its_own_script_as_secure_attributes_written_out_of_combat_only,
    check_a_press_counts_on_the_event_the_game_acts_on,
    check_the_record_advances_on_the_next_totem_cast_and_ignores_the_rest,
    check_the_record_starts_over_at_combat_end_after_six_idle_seconds_and_on_any_edit,
    check_a_secret_number_from_the_clock_is_not_kept_as_a_press_time,
    check_a_secret_spell_id_is_noted_and_never_breaks_the_record,
    check_the_ring_has_one_arc_per_totem_tinted_by_its_element,
    check_the_number_the_plus_and_the_dashed_empty_ring,
    check_a_locked_totem_is_a_dashed_muted_arc_and_the_step_skips_it,
    check_while_stepping_done_arcs_glow_the_next_is_thick_and_the_icon_replaces_the_number,
    check_the_name_plates_and_the_step_plate,
    check_the_outline_colour_draws_the_border_glow_underline_and_plate_of_each_cell_and_not_the_arcs,
    check_an_unset_cell_is_dim_dashed_and_muted_with_a_plus_the_plate_unset_and_a_press_does_nothing,
    check_the_cells_light_on_hover_and_press_toward_their_colour_and_restore_in_and_out_of_combat,
    check_the_tooltip_lists_the_totems_in_order_the_left_out_ones_the_hints_and_the_unset_cell,
    check_shift_click_on_a_set_cell_edits_its_preset_and_on_an_unset_cell_makes_it_from_the_four_buttons,
    check_the_editor_rows_the_chooser_and_the_up_down_buttons,
    check_an_unset_slot_opens_empty_and_its_first_totem_makes_the_preset_named_for_its_number,
    check_the_name_box_commits_on_enter_and_on_losing_focus_and_cleans_the_name,
    check_clear_asks_twice_the_confirmation_runs_out_and_the_card_stays_open_on_the_empty_slot,
    check_the_card_closes_on_escape_and_combat_and_hangs_on_the_last_cell,
    check_no_secure_frame_is_anchored_to_the_card_or_its_pieces,
    check_a_resize_hides_the_art_of_the_old_width,
    check_edit_clicks_in_every_modifier_combination_never_drop_a_totem,
    check_the_cell_tips_say_a_shift_keybind_edits,
    check_a_character_key_that_cannot_be_read_never_saves_under_a_made_up_one,
    check_an_unreadable_character_key_with_a_database_that_cannot_save_keeps_the_session_refusal,
    check_the_known_totems_are_scanned_once_per_event_not_once_per_repaint,
    check_the_cells_stand_right_of_the_six_and_the_buttons_keep_their_slots,
    check_a_rescale_resizes_and_reseats_the_face,
    check_two_cells_with_the_same_first_totem_count_a_cast_for_the_one_pressed,
    check_each_cell_steps_its_own_preset_whatever_the_other_is_doing_in_and_out_of_combat,
    check_clear_is_one_full_width_button_padded_symmetrically_and_snapped_to_whole_pixels,
    check_the_card_has_a_row_of_seven_outline_swatches_that_choose_the_slots_colour,
    check_the_swatches_light_on_hover_and_press_restore_and_dim_while_the_presets_cannot_be_saved,
    check_the_card_layout_matches_the_mockup_on_whole_pixels_at_every_scale,
    check_each_drop_order_row_is_one_button_for_its_whole_width_with_the_arrows_on_top,
    check_a_left_out_row_has_a_dashed_muted_box_and_a_small_dashes_label_and_no_ring,
    check_the_selected_swatchs_inner_ring_sits_one_pixel_inside_the_white_outer_ring,
    check_a_disabled_row_ignores_its_arrows_hover_and_a_swatch_tooltip_goes_with_the_card,
    check_the_close_x_and_the_arrows_are_drawn_on_whole_pixels_with_equal_margins_at_every_scale,
    check_every_interactive_editor_element_has_hover_pressed_and_disabled_looks_and_restores_exactly,
    check_the_name_box_the_pick_cells_and_the_row_light_up_on_hover_and_restore,
    check_preset_two_is_written_into_set_two_once_and_read_back,
    check_a_spell_that_comes_back_is_written_to_set_two_again,
    check_a_set_two_send_that_has_not_shown_is_looked_at_again_and_sent_again_a_few_times,
    check_set_one_is_watched_until_a_set_two_send_is_judged_and_the_line_says_which_check_ran,
    check_a_pick_of_the_set_two_totem_inside_the_window_is_the_players_and_is_never_put_back,
    check_a_set_two_slot_is_written_only_when_it_reads_back_holding_nothing_or_an_element_totem,
    check_set_two_raising_inside_the_refresh_is_caught_and_the_state_is_still_saved,
    check_a_press_is_used_up_by_the_cast_it_brought_and_a_reset_forgets_it,
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
    check_the_pixel_unit_falls_through_to_the_screen_height_when_pixelutil_gives_nothing_usable,
    check_a_bad_effective_scale_is_taken_as_1_by_the_pixel_unit,
    check_leaving_a_pick_cell_with_the_button_down_drops_the_pressed_look,
    check_a_disabled_row_does_not_light_its_edge_and_every_editor_texture_is_pixel_snapped,
    check_the_files_use_no_snippets_no_state_drivers_and_no_flagged_words,
]

SCALED_CHECKS = [
    check_the_tab_grows_by_a_cell_for_each_preset_cell_that_is_on_and_the_buff_and_mana_regen_tabs_follow,
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
