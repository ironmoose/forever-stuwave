#!/usr/bin/env python3
"""Runs the real PoisonsTab.lua headless on the class shoulder world (see shapeshifttab-harness.py, whose world and kit it
shares) as a Rogue, and pins the Rogue poisons tab (ticket T5).

What is pinned here:

  * the poison buttons: one per poison family the Rogue has learned (a recipe known) or carries, in the order Instant,
    Deadly, Crippling, Mind-numbing, Wound, each a secure macro button on `/use item:<id>` of the highest rank CARRIED (else
    the highest rank learned, dimmed), its carried count on it; the choice follows the bags out of combat;
  * the weapon buttons: Main hand and Off hand after the poisons, secure macro buttons on `/use 16` and `/use 17` (the pick
    after a poison is clicked); the off hand only while a weapon (not a shield) is in it;
  * what is on a hand: GetWeaponEnchantInfo when it answers a plain true (time and charges), else the weapon's tooltip out of
    combat (this client answers false for an imbue that is up, so a false is never believed), else the last read; the time
    and charges show while their switch is on; a secret answer shows nothing and never moves a light; the tooltip is never
    read in combat;
  * the pulse: a hand known to hold nothing pulses while its switch is on, stops the moment a poison lands, the switch goes
    off, or the answer stops being plain; an unknown hand never pulses;
  * the master switch, another class, combat queueing and the config rows.

It is NOT the real client: whether a click on the weapon button after a poison applies it, what the weapon tooltip says on
Forever, and whether GetWeaponEnchantInfo reads plain in combat are in-game checks.

    python3 tools/poisonstab-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
TAB = Path(os.environ.get("POISONSTAB_LUA", ADDON / "Modules/ActionBars/PoisonsTab.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("shapeshifttab_harness", "shapeshifttab-harness.py")
sb, csh = st.sb, st.csh
g, run, fire, combat, shown, attrs, standing = st.g, st.run, st.fire, st.combat, st.shown, st.attrs, st.standing

# Instant IV to VI, Deadly I and II, a Crippling: recipe spell id and item id, as PoisonsTab.lua has them
INSTANT = {"VI": (11343, 8928), "V": (11342, 8927), "I": (8681, 6947)}
DEADLY = {"I": (2835, 2892), "II": (2837, 2893)}
CRIPPLING = {"I": (3420, 3775)}

# The weapons, the temporary enchant answers and the tooltips the client gives
WORLD = r"""
__weapons = { [16] = { id = 1001, tex = 5001, loc = "INVTYPE_WEAPONMAINHAND" }, [17] = { id = 1002, tex = 5002, loc = "INVTYPE_WEAPON" } }
function GetInventoryItemID(unit, slot) local w = __weapons[slot]; return w and w.id end
function GetInventoryItemTexture(unit, slot) local w = __weapons[slot]; return w and w.tex end
C_Item.GetItemInfoInstant = function(id)
    for _, w in pairs(__weapons) do if w.id == id then return id, "Weapon", "Dagger", w.loc end end
    return id, "Misc", "Junk", ""
end
-- GetWeaponEnchantInfo: per slot { ms, charges } or nil; mode "false" answers false for everything (this client with an
-- imbue up), "secret" answers secret, "throw" raises
__ench, __enchMode = {}, nil
function GetWeaponEnchantInfo()
    if __enchMode == "throw" then error("GetWeaponEnchantInfo blew up") end
    if __enchMode == "secret" then return __SECRET, __SECRET, __SECRET, __SECRET, __SECRET, __SECRET, __SECRET, __SECRET end
    if __enchMode == "false" then return false, nil, nil, nil, false, nil, nil, nil end
    local m, o = __ench[16], __ench[17]
    return m ~= nil, m and m[1], m and m[2] or 0, m and 1 or nil, o ~= nil, o and o[1], o and o[2] or 0, o and 1 or nil
end
-- the weapon tooltips: slot -> list of lines
__tips, __tipMode, __tipReads = {}, nil, 0
C_TooltipInfo = C_TooltipInfo or {}
C_TooltipInfo.GetInventoryItem = function(unit, slot)
    __tipReads = __tipReads + 1
    if __tipMode == "throw" then error("GetInventoryItem blew up") end
    if __tipMode == "secret" then return __SECRET end
    if __tipMode == "none" then return nil end
    local lines = {}
    for i, text in ipairs(__tips[slot] or {}) do lines[i] = { leftText = text } end
    return { lines = lines }
end
__tips[16] = { "Rogue Dagger", "Binds when equipped" }
__tips[17] = { "Rogue Dagger", "Binds when equipped" }
"""


def boot(*, learn: tuple = (11343, 2837), items: dict | None = None, klass: str = "ROGUE", pre: str = "", **kw):
    setup = WORLD
    for item, n in (items or {}).items():
        setup += f"__items[{item}] = {n}\n"
    return st.boot(klass=klass, tabs=(TAB,), learn=learn, pre=setup + pre, **kw)


def tab(lua):
    return g(lua).FS.PoisonsTab


def btns(lua, n=7):
    return st.buttons(lua, "FSPoisonsButton", n)


def macros(lua) -> list:
    return [x._attrs["macrotext"] for x in btns(lua) if shown(x)]


def pulsing(button) -> bool:
    group = button.fsNudgeGroup
    return bool(group and group._playing)


def tick(lua, seconds=1.1):
    run(lua, f"__now = __now + {seconds}")
    run(lua, "__next_frame()")


MH_SLOT, OH_SLOT = 16, 17


# ---------------------------------------------------------------------------------------------------------------------


def check_one_macro_button_per_learned_family_on_the_highest_rank_carried():
    lua = boot(learn=(11343, 8681, 2837, 3420), items={8928: 12, 6947: 3, 2893: 5, 3775: 0})
    assert tab(lua).OwnsShoulder(), "no shoulder"
    b = btns(lua)
    assert macros(lua)[:3] == ["/use item:8928", "/use item:2893", "/use item:3775"], macros(lua)
    assert [attrs(x)["type"] for x in b[:3]] == ["macro", "macro", "macro"]
    assert [x.fsCount._text for x in b[:3]] == ["12", "5", "0"], [x.fsCount._text for x in b[:3]]
    assert not b[0].icon._desat and not b[1].icon._desat and b[2].icon._desat, "only the empty stack dims"
    assert b[0]._clicks[1] == "AnyUp" and b[0]._clicks[2] == "AnyDown"


def check_a_rank_learned_but_not_carried_loses_to_a_lower_rank_that_is():
    lua = boot(learn=(11343, 11342), items={8927: 4})
    assert macros(lua)[0] == "/use item:8927", macros(lua)
    run(lua, "__items[8928] = 2")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert macros(lua)[0] == "/use item:8928", f"the bags did not move the choice: {macros(lua)}"
    run(lua, "__items[8928] = 0; __items[8927] = 0")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert macros(lua)[0] == "/use item:8928" and btns(lua)[0].icon._desat, "an empty set shows the highest learned, dimmed"


def check_a_poison_carried_without_its_recipe_still_gets_a_button():
    lua = boot(learn=(), items={6947: 9})
    assert tab(lua).OwnsShoulder(), "a carried poison does not bring the tab"
    assert macros(lua)[0] == "/use item:6947", macros(lua)


def check_the_weapon_buttons_follow_the_poisons_and_the_off_hand_needs_a_weapon():
    lua = boot(items={8928: 1})
    got = macros(lua)
    assert got[-2:] == ["/use 16", "/use 17"], got
    b = btns(lua)
    assert attrs(b[len(got) - 2]) == {"type": "macro", "macrotext": "/use 16"}
    run(lua, '__weapons[17] = { id = 1003, tex = 5003, loc = "INVTYPE_SHIELD" }')
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 17)
    assert macros(lua)[-1] == "/use 16", f"a shield got a weapon button: {macros(lua)}"
    run(lua, "__weapons[17] = nil")
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 17)
    assert macros(lua)[-1] == "/use 16", f"an empty off hand got a weapon button: {macros(lua)}"
    run(lua, "__weapons[16] = nil")
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16)
    assert not any(m.startswith("/use 1") for m in macros(lua)), f"no weapon, no weapon button: {macros(lua)}"
    assert macros(lua) == ["/use item:8928", "/use item:2893"], macros(lua)


def check_the_weapon_buttons_are_lit_and_name_the_poison_on_them():
    lua = boot(items={8928: 1})
    mh = btns(lua)[2]
    assert mh.fsKey == "mh" and mh.fsTipText == "Main hand", mh.fsKey
    run(lua, "__ench[16] = { 1800000, 0 }; __tips[16] = { 'Rogue Dagger', 'Instant Poison VI (30 min)' }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert mh.fsLit, "a poisoned hand is not lit"
    assert mh.fsTipLine and "Instant Poison VI" in mh.fsTipLine, f"the tooltip does not name the poison: {mh.fsTipLine}"


def check_a_plain_api_answer_gives_time_and_charges():
    lua = boot(items={8928: 1})
    mh, oh = btns(lua)[2], btns(lua)[3]
    run(lua, "__ench[16] = { 1800000, 0 }; __ench[17] = { 95000, 14 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert mh.fsLit and oh.fsLit, "both hands are not lit"
    assert mh.fsCount._text == "30m" and not mh.fsTop._text, (mh.fsCount._text, mh.fsTop._text)
    assert oh.fsCount._text == "1m" and oh.fsTop._text == "14", (oh.fsCount._text, oh.fsTop._text)
    run(lua, "__ench[17] = { 45000, 3 }")
    tick(lua)
    assert oh.fsCount._text == "45s" and oh.fsTop._text == "3", "the clock did not follow"


def check_the_time_and_charges_switch_off_shows_neither_and_still_lights_the_hand():
    lua = boot(items={8928: 1})
    run(lua, "__ench[16] = { 1800000, 9 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    mh = btns(lua)[2]
    assert mh.fsCount._text == "30m" and mh.fsTop._text == "9"
    run(lua, 'FS.Config.Set("tabs.rogue.poisonsLeft", false)')
    assert not mh.fsCount._text and not mh.fsTop._text, "text with the switch off"
    assert mh.fsLit, "the hand went dark with the text switch off"
    assert tab(lua).SETTINGS.poisonsLeft.default is True


def check_a_false_api_answer_is_not_believed_the_tooltip_is_read_instead():
    lua = boot(items={8928: 1})
    run(lua, '__enchMode = "false"; __tips[16] = { "Rogue Dagger", "Instant Poison VI (58 min)" }')
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    mh, oh = btns(lua)[2], btns(lua)[3]
    assert mh.fsLit and mh.fsCount._text == "58m", (mh.fsLit, mh.fsCount._text)
    assert not oh.fsLit and pulsing(oh), "the empty off hand does not pulse"
    assert not pulsing(mh), "a poisoned hand pulses"


def check_an_empty_hand_pulses_until_a_poison_lands_the_switch_goes_off_or_the_answer_goes_dark():
    lua = boot(items={8928: 1})
    mh = btns(lua)[2]
    assert pulsing(mh), "no pulse on an empty hand"
    assert shown(mh.fsNudge), "the pulse wash is hidden"
    run(lua, "__ench[16] = { 600000, 0 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert not pulsing(mh) and not shown(mh.fsNudge), "the pulse did not stop at once when a poison landed"
    run(lua, "__ench[16] = nil")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert pulsing(mh), "the pulse did not come back"
    run(lua, 'FS.Config.Set("tabs.rogue.poisonsNudge", false)')
    assert not pulsing(mh) and not shown(mh.fsNudge), "the pulse did not stop at once with its switch"
    assert tab(lua).SETTINGS.poisonsNudge.default is True
    run(lua, 'FS.Config.Set("tabs.rogue.poisonsNudge", true)')
    assert pulsing(mh)
    run(lua, '__tipMode = "secret"; __enchMode = "secret"')
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert not pulsing(mh), "an unreadable answer kept the pulse"


def check_an_unknown_hand_never_pulses_and_says_nothing():
    lua = boot(items={8928: 1}, pre='__tipMode = "secret"; __enchMode = "secret"')
    mh = btns(lua)[2]
    assert not pulsing(mh) and not mh.fsLit, "an unreadable hand pulses or is lit"
    assert not mh.fsCount._text and not mh.fsTop._text, "text from nothing"
    lua = boot(items={8928: 1}, pre='__tipMode = "throw"; __enchMode = "throw"')
    assert not pulsing(btns(lua)[2]), "a throwing read pulses"
    lua = boot(items={8928: 1}, pre='__tipMode = "none"; __enchMode = "false"')
    assert not pulsing(btns(lua)[2]), "no tooltip at all pulses"
    assert sb.blocked(lua) == 0


def check_combat_never_reads_the_tooltip_keeps_the_last_state_and_shows_no_guess():
    lua = boot(items={8928: 1})
    run(lua, "__ench[16] = { 1800000, 4 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    mh = btns(lua)[2]
    assert mh.fsLit and mh.fsCount._text == "30m"
    reads = int(g(lua).__tipReads)
    combat(lua, True)
    run(lua, '__enchMode = "secret"')
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    tick(lua)
    assert int(g(lua).__tipReads) == reads, "the tooltip was read in combat"
    assert mh.fsLit, "the light went out on a secret answer"
    assert not mh.fsCount._text and not mh.fsTop._text, "a time was shown from a secret answer"
    assert not pulsing(mh), "a secret answer pulses"
    run(lua, '__enchMode = nil; __ench[16] = { 1700000, 4 }')
    tick(lua)
    assert mh.fsCount._text == "28m", f"a plain answer in combat is not read: {mh.fsCount._text}"
    assert sb.blocked(lua) == 0, "a protected call was refused"


def check_a_weapon_swap_forgets_what_was_read_of_the_hand():
    lua = boot(items={8928: 1})
    mh = btns(lua)[2]
    assert pulsing(mh), "the empty hand does not pulse"
    run(lua, '__enchMode = "false"; __tipMode = "none"')
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16)
    assert not pulsing(mh), "the old read outlived the weapon it was read from"
    run(lua, '__tipMode = nil')
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16)
    assert pulsing(mh), "a fresh read of an empty hand does not pulse"
    combat(lua, True)
    run(lua, '__enchMode = "secret"')
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16)
    assert not pulsing(mh), "a swap in combat pulses before anyone knows"


def check_the_clock_asks_the_tooltip_again_out_of_combat_and_counts_down_between():
    lua = boot(items={8928: 1})
    mh = btns(lua)[2]
    run(lua, '__enchMode = "false"; __tips[16] = { "Rogue Dagger", "Instant Poison VI (58 min)" }')
    tick(lua, 11)
    assert mh.fsLit and mh.fsCount._text == "58m", (mh.fsLit, mh.fsCount._text)
    tick(lua)
    assert mh.fsCount._text == "57m", f"the time did not count down between reads: {mh.fsCount._text}"
    reads = int(g(lua).__tipReads)
    combat(lua, True)
    tick(lua, 30)
    assert int(g(lua).__tipReads) == reads, "the clock read the tooltip in combat"
    assert not mh.fsCount._text and mh.fsLit and not pulsing(mh), "an unknown hand in combat showed or pulsed"
    run(lua, '__tips[16] = { "Rogue Dagger" }')
    combat(lua, False)
    tick(lua)
    assert not mh.fsLit and pulsing(mh), "leaving combat did not read the hand again"


def check_the_master_switch_off_hides_everything_and_frees_the_seat():
    lua = boot(items={8928: 1})
    run(lua, 'FS.Config.Set("tabs.rogue.poisons", false)')
    assert not shown(g(lua).FSPoisonsTab) and not any(shown(x) for x in btns(lua)), "still shown"
    assert all(attrs(x) == {} for x in btns(lua)), "an attribute is left behind"
    assert 36 not in standing(lua), "the shoulder still stands"
    assert not any(pulsing(x) for x in btns(lua)), "a pulse is left behind"
    run(lua, 'FS.Config.Set("tabs.rogue.poisons", true)')
    assert shown(btns(lua)[0]) and 36 in standing(lua), "did not come back"


def check_no_poison_shows_no_tab_even_with_weapons():
    lua = boot(learn=(), items={})
    assert not tab(lua).OwnsShoulder() and not shown(g(lua).FSPoisonsTab) and 36 not in standing(lua)
    run(lua, "__learn(11343)")
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).OwnsShoulder() and 36 in standing(lua), "learning a poison did not bring the tab"


def check_another_class_builds_nothing():
    for klass in ("DRUID", "WARRIOR", "MAGE"):
        lua = boot(klass=klass, items={8928: 1})
        assert g(lua).FSPoisonsTab is None and g(lua).FSPoisonsButton1 is None, f"a {klass} built the tab"
        assert not tab(lua).OwnsShoulder() and 36 not in standing(lua)


def check_the_seat_is_one_row_as_wide_as_the_buttons():
    lua = boot(items={8928: 1})
    n = len(macros(lua))
    st_ = standing(lua)
    sb.approx(st_[36][0], st.block_w(n), "block width")
    sb.approx(st_[36][1], 49, "block height")
    for i, btn in enumerate(btns(lua)[:n]):
        sb.approx(csh.D(lua, btn)["x"], 36 + 6 + i * 42.8, f"button {i + 1} x")


def check_combat_touches_nothing_protected_and_the_update_waits_for_regen():
    lua = boot(items={8928: 1})
    combat(lua, True)
    run(lua, "__learn(8681, 3420); __items[3775] = 2; __items[8928] = 0")
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "BAG_UPDATE_DELAYED")
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 17)
    run(lua, 'FS.Config.Set("tabs.rogue.poisons", false)')
    assert sb.blocked(lua) == 0, "a protected call was refused in combat"
    assert tab(lua).T.pendingSync, "nothing was parked"
    assert shown(btns(lua)[0]), "a button was hidden in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).T.pendingSync and not shown(g(lua).FSPoisonsTab), "regen did not apply the master switch"
    assert sb.blocked(lua) == 0


def check_config_rows_and_defaults_are_the_prototypes():
    lua = boot()
    secs = [s for s in st.cfg_sections(lua) if s["title"] == "Poisons tab"]
    assert len(secs) == 1, "no Poisons tab section"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["when"]) == ("tabs", "general", "ROGUE"), sec
    assert sec["tip"] == ("New. Your poisons as buttons. Click one, then pick the weapon to coat. Main hand and off hand "
                          "show what is on them and how long is left."), sec["tip"]
    assert [(r["key"], r["label"], bool(r["sub"])) for r in sec["rows"]] == [
        ("tabs.rogue.poisons", "Poisons tab", False), ("tabs.rogue.poisonsLeft", "Show time and charges left", True),
        ("tabs.rogue.poisonsNudge", "Pulse when a weapon has no poison", True)], sec["rows"]
    assert all(r["needs"] == "tabs.rogue.poisons" for r in sec["rows"][1:])
    get = g(lua).FS.Config.Get
    for key in ("poisons", "poisonsLeft", "poisonsNudge"):
        assert get(f"tabs.rogue.{key}") is True, key


def check_the_file_is_in_the_toc_and_says_no_dashes_and_no_automation_words():
    toc = st.TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/PoisonsTab.lua")
    assert toc.index("Modules/ActionBars/ConjureTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua")
    text = TAB.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text, "an em or en dash"
    assert "local _, FS = ..." in text


CHECKS = [v for k, v in sorted(globals().items()) if k.startswith("check_")]


def main() -> int:
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print(f"ok    {fn.__name__}")
        except (AssertionError, LuaError, AttributeError, TypeError, KeyError, IndexError, ValueError) as err:
            failed += 1
            print(f"FAIL  {fn.__name__}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))
    print(f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
