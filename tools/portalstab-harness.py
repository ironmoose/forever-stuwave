#!/usr/bin/env python3
"""Runs the real PortalsTab.lua headless on the class shoulder world (see shapeshifttab-harness.py, whose world and kit it
shares) as a Mage, and pins the Mage portals and teleports tab (ticket T3).

What is pinned here:

  * who: a Mage with any teleport or portal learned gets the tab; teleports on the top row, portals on the bottom row,
    learned ones only, each a secure spell button on its spell's NAME; another class, nothing learned or the master switch
    off builds and shows nothing, and learning one brings it;
  * the seat: a two row shoulder, as wide as the longer row, 36 design px in from the chassis left; a row that is switched
    off or empty leaves the other on the bottom row (the one against the chassis);
  * the rune count: the carried Rune of Teleportation count on every teleport button and the Rune of Portals count on
    every portal button, while its switch is on; a secret, throwing or missing answer shows nothing; a count of 0 dims
    the buttons; the count follows the bags in combat;
  * the switches: Teleports and Portals each hide their row, the master hides the tab, none leaves a frame behind;
  * combat: nothing protected is touched, the update waits for regen; the config rows and defaults.

It is NOT the real client: whether the client's carried count includes the reagent slot, which spells a Mage of each
faction learns, and how the tab looks are in-game checks.

    python3 tools/portalstab-harness.py

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
TAB = Path(os.environ.get("PORTALSTAB_LUA", ADDON / "Modules/ActionBars/PortalsTab.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("shapeshifttab_harness", "shapeshifttab-harness.py")
sb, csh = st.sb, st.csh
g, run, fire, combat, shown, attrs, standing = st.g, st.run, st.fire, st.combat, st.shown, st.attrs, st.standing

TELE = {"Stormwind": 3561, "Ironforge": 3562, "Undercity": 3563, "Darnassus": 3565, "Thunder Bluff": 3566,
        "Orgrimmar": 3567, "Dalaran": 1297659}
PORTAL = {"Stormwind": 10059, "Ironforge": 11416, "Orgrimmar": 11417, "Undercity": 11418, "Darnassus": 11419,
          "Thunder Bluff": 11420}
ALLIANCE_TELE = (TELE["Stormwind"], TELE["Ironforge"], TELE["Darnassus"])
ALLIANCE_PORTAL = (PORTAL["Stormwind"], PORTAL["Ironforge"], PORTAL["Darnassus"])
RUNE_TELE, RUNE_PORTAL = 17031, 17032


def boot(*, learn: tuple = ALLIANCE_TELE + ALLIANCE_PORTAL, items: dict | None = None, klass: str = "MAGE",
         pre: str = "", **kw):
    setup = ""
    for item, n in (items or {}).items():
        setup += f"__items[{item}] = {n}\n"
    return st.boot(klass=klass, tabs=(TAB,), learn=learn, pre=setup + pre, **kw)


def tab(lua):
    return g(lua).FS.PortalsTab


def btns(lua, n=13):
    return st.buttons(lua, "FSPortalsButton", n)


def spells(lua) -> list:
    return [x._attrs["spell"] for x in btns(lua) if shown(x)]


def top_of(lua, btn) -> float:
    return csh.D(lua, btn)["y"]


ROW1_TOP, ROW2_TOP = -91.8 + 6, -91.8 + 6 + 42.8


# ---------------------------------------------------------------------------------------------------------------------


def check_teleports_on_the_top_row_portals_on_the_bottom_row_learned_ones_only():
    lua = boot(learn=(3561, 3562, 10059))
    t = tab(lua)
    assert t.OwnsShoulder(), "no shoulder"
    assert spells(lua) == ["Teleport: Stormwind", "Teleport: Ironforge", "Portal: Stormwind"], spells(lua)
    b = btns(lua)
    assert [attrs(x) for x in b[:3]] == [
        {"type": "spell", "spell": "Teleport: Stormwind"}, {"type": "spell", "spell": "Teleport: Ironforge"},
        {"type": "spell", "spell": "Portal: Stormwind"}], [attrs(x) for x in b[:3]]
    sb.approx(top_of(lua, b[0]), ROW1_TOP, "teleport row")
    sb.approx(top_of(lua, b[1]), ROW1_TOP, "teleport row, second")
    sb.approx(top_of(lua, b[2]), ROW2_TOP, "portal row")
    sb.approx(csh.D(lua, b[2])["x"], 36 + 6, "the portal packs left")
    assert not any(shown(x) for x in b[3:]), "extra buttons shown"
    assert b[0]._clicks[1] == "AnyUp" and b[0]._clicks[2] == "AnyDown"
    assert shown(g(lua).FSPortalsTab), "host hidden"


def check_a_full_horde_set_and_dalaran_in_their_own_order():
    lua = boot(learn=(3567, 3566, 3563, 1297659, 11417, 11420, 11418))
    assert spells(lua) == ["Teleport: Orgrimmar", "Teleport: Thunder Bluff", "Teleport: Undercity", "Teleport: Dalaran",
                           "Portal: Orgrimmar", "Portal: Thunder Bluff", "Portal: Undercity"], spells(lua)
    st_ = standing(lua)
    sb.approx(st_[36][0], st.block_w(4), "the block is as wide as the longer row")
    sb.approx(st_[36][1], 91.8, "the block is two rows tall")


def check_nothing_learned_shows_nothing_and_learning_one_brings_the_tab():
    lua = boot(learn=())
    assert not tab(lua).OwnsShoulder() and not shown(g(lua).FSPortalsTab), "a tab with nothing learned"
    assert 36 not in standing(lua), "a shoulder stands"
    run(lua, "__learn(11416)")
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).OwnsShoulder() and spells(lua) == ["Portal: Ironforge"], spells(lua)
    sb.approx(top_of(lua, btns(lua)[0]), ROW2_TOP, "a lone portal sits on the bottom row")


def check_another_class_builds_nothing():
    for klass in ("DRUID", "WARLOCK", "PRIEST"):
        lua = boot(klass=klass)
        assert g(lua).FSPortalsTab is None and g(lua).FSPortalsButton1 is None, f"a {klass} built the tab"
        assert not tab(lua).OwnsShoulder() and 36 not in standing(lua)


def check_the_teleports_switch_hides_that_row_and_the_portals_stay_on_the_bottom():
    lua = boot(learn=(3561, 10059, 11416))
    run(lua, 'FS.Config.Set("tabs.mage.travelTele", false)')
    assert spells(lua) == ["Portal: Stormwind", "Portal: Ironforge"], spells(lua)
    sb.approx(top_of(lua, btns(lua)[0]), ROW2_TOP, "portals stay on the bottom row")
    run(lua, 'FS.Config.Set("tabs.mage.travelTele", true)')
    assert spells(lua)[0] == "Teleport: Stormwind"


def check_the_portals_switch_hides_that_row_and_the_teleports_drop_to_the_bottom_row():
    lua = boot(learn=(3561, 3562, 10059))
    run(lua, 'FS.Config.Set("tabs.mage.travelPortal", false)')
    assert spells(lua) == ["Teleport: Stormwind", "Teleport: Ironforge"], spells(lua)
    sb.approx(top_of(lua, btns(lua)[0]), ROW2_TOP, "a teleport row with no portals sits against the chassis")
    run(lua, 'FS.Config.Set("tabs.mage.travelPortal", true)')
    sb.approx(top_of(lua, btns(lua)[0]), ROW1_TOP, "the teleports did not go back to the top row")
    assert spells(lua)[-1] == "Portal: Stormwind"


def check_both_row_switches_off_leave_no_tab():
    lua = boot()
    run(lua, 'FS.Config.Set("tabs.mage.travelTele", false); FS.Config.Set("tabs.mage.travelPortal", false)')
    assert not tab(lua).OwnsShoulder() and not shown(g(lua).FSPortalsTab) and 36 not in standing(lua)


def check_the_master_switch_off_hides_everything_and_frees_the_seat():
    lua = boot()
    run(lua, 'FS.Config.Set("tabs.mage.travel", false)')
    assert not shown(g(lua).FSPortalsTab) and not any(shown(x) for x in btns(lua)), "something is still shown"
    assert all(attrs(x) == {} for x in btns(lua)), "an attribute is left behind"
    assert 36 not in standing(lua), "the shoulder still stands"
    run(lua, 'FS.Config.Set("tabs.mage.travel", true)')
    assert shown(btns(lua)[0]) and 36 in standing(lua), "did not come back"


def check_the_rune_counts_sit_on_their_rows_and_follow_the_bags():
    lua = boot(items={RUNE_TELE: 7, RUNE_PORTAL: 2})
    b = btns(lua)
    assert [x.fsCount._text for x in b[:3]] == ["7", "7", "7"], [x.fsCount._text for x in b[:3]]
    assert [x.fsCount._text for x in b[3:6]] == ["2", "2", "2"], [x.fsCount._text for x in b[3:6]]
    assert shown(b[0].fsCount.fsPlate), "no plate behind the count"
    run(lua, f"__items[{RUNE_TELE}] = 6")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert b[0].fsCount._text == "6" and b[3].fsCount._text == "2", "the bags did not move the count"


def check_a_count_of_zero_dims_the_row_and_the_rune_switch_off_shows_nothing():
    lua = boot(items={RUNE_TELE: 0, RUNE_PORTAL: 5})
    b = btns(lua)
    assert b[0].fsCount._text == "0" and b[0].icon._desat, "an empty rune stack is not dimmed"
    assert b[3].fsCount._text == "5" and not b[3].icon._desat, "a stocked row was dimmed"
    run(lua, 'FS.Config.Set("tabs.mage.travelRunes", false)')
    assert all(not x.fsCount._text for x in b[:6]), "a count with the switch off"
    assert not b[0].icon._desat, "dimmed with the switch off"
    assert tab(lua).SETTINGS.travelRunes.default is True


def check_an_unreadable_count_shows_nothing_and_never_throws():
    lua = boot(items={RUNE_TELE: 7})
    b = btns(lua)
    run(lua, '__itemMode = "secret"')
    fire(lua, "BAG_UPDATE_DELAYED")
    assert all(not x.fsCount._text for x in b[:6]), "a secret count was shown"
    assert not b[0].icon._desat, "a secret count dimmed the row"
    run(lua, '__itemMode = "throw"')
    fire(lua, "BAG_UPDATE_DELAYED")
    assert all(not x.fsCount._text for x in b[:6]), "a throwing count was shown"
    run(lua, '__itemMode = nil')
    fire(lua, "BAG_UPDATE_DELAYED")
    assert b[0].fsCount._text == "7", "did not recover"
    assert sb.blocked(lua) == 0


def check_combat_touches_nothing_protected_and_the_update_waits_for_regen():
    lua = boot(learn=(3561,), items={RUNE_TELE: 3})
    combat(lua, True)
    run(lua, "__learn(3562, 10059); __items[17031] = 2")
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "BAG_UPDATE_DELAYED")
    run(lua, 'FS.Config.Set("tabs.mage.travelTele", false)')
    assert sb.blocked(lua) == 0, "a protected call was refused in combat"
    assert tab(lua).T.pendingSync, "nothing was parked"
    assert btns(lua)[0].fsCount._text == "2", "the count did not follow in combat"
    assert spells(lua) == ["Teleport: Stormwind"], "buttons moved in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert spells(lua) == ["Portal: Stormwind"], spells(lua)
    assert sb.blocked(lua) == 0


def check_config_rows_and_defaults_are_the_prototypes():
    lua = boot()
    secs = [s for s in st.cfg_sections(lua) if s["title"] == "Portals and teleports tab"]
    assert len(secs) == 1, "no Portals and teleports tab section"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["when"]) == ("tabs", "general", "MAGE"), sec
    assert sec["tip"] == "New. Teleports on the top row and portals on the bottom row, learned ones only.", sec["tip"]
    assert [(r["key"], r["label"], bool(r["sub"])) for r in sec["rows"]] == [
        ("tabs.mage.travel", "Portals and teleports tab", False), ("tabs.mage.travelTele", "Teleports", True),
        ("tabs.mage.travelPortal", "Portals", True), ("tabs.mage.travelRunes", "Show rune count", True)], sec["rows"]
    assert all(r["needs"] == "tabs.mage.travel" for r in sec["rows"][1:])
    assert sec["rows"][3]["tip"] == "How many Runes of Teleportation and Runes of Portals you carry."
    get = g(lua).FS.Config.Get
    for key in ("travel", "travelTele", "travelPortal", "travelRunes"):
        assert get(f"tabs.mage.{key}") is True, key


def check_the_file_is_in_the_toc_and_says_no_dashes():
    toc = st.TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/PortalsTab.lua")
    assert toc.index("Modules/ActionBars/CallPetTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua")
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
