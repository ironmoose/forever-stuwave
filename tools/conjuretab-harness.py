#!/usr/bin/env python3
"""Runs the real ConjureTab.lua headless on the class shoulder world (see shapeshifttab-harness.py, whose world and kit it
shares) as a Mage, and pins the Mage food and water tab (ticket T4).

What is pinned here:

  * who: a Mage who knows any rank of Conjure Food or Conjure Water gets the tab, a Food button then a Water button, each a
    secure spell button on the spell's NAME (the client casts the highest rank of a name) while the icon, tooltip and
    cooldown follow the highest KNOWN rank id, rebound out of combat when a rank is learned; another class, no rank known or
    the master switch off builds and shows nothing;
  * the count: the carried conjured food or water (every rank's item added together) on its button while its switch is on;
    off hides the count only; a secret, throwing or missing answer shows nothing; 0 shows 0 and does not dim the button;
    the count follows the bags in combat;
  * the seat: a one row shoulder 36 design px in, or 16 design px right of the portals tab when that stands too, moving back
    when it goes;
  * combat: nothing protected is touched, the rebind waits for regen; the config rows and defaults.

It is NOT the real client: which conjured items Forever's ranks make (client data 16001 says the ids in ConjureTab.lua),
and how the tab looks are in-game checks.

    python3 tools/conjuretab-harness.py

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
TAB = Path(os.environ.get("CONJURETAB_LUA", ADDON / "Modules/ActionBars/ConjureTab.lua"))
PORTALS = ADDON / "Modules/ActionBars/PortalsTab.lua"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("shapeshifttab_harness", "shapeshifttab-harness.py")
sb, csh = st.sb, st.csh
g, run, fire, combat, shown, attrs, standing = st.g, st.run, st.fire, st.combat, st.shown, st.attrs, st.standing

FOOD = (587, 597, 990, 6129, 10144, 10145, 28612)
WATER = (5504, 5505, 5506, 6127, 10138, 10139, 10140, 468766)
FOOD_ITEMS = (5349, 1113, 1114, 1487, 8075, 8076, 22895)
WATER_ITEMS = (5350, 2288, 2136, 3772, 8077, 8078, 8079, 231778)


def boot(*, learn: tuple = (587, 5504), items: dict | None = None, klass: str = "MAGE", portals: bool = False,
         pre: str = "", **kw):
    setup = ""
    for item, n in (items or {}).items():
        setup += f"__items[{item}] = {n}\n"
    tabs = ((PORTALS,) if portals else ()) + (TAB,)
    return st.boot(klass=klass, tabs=tabs, learn=learn, pre=setup + pre, **kw)


def tab(lua):
    return g(lua).FS.ConjureTab


def btns(lua, n=2):
    return st.buttons(lua, "FSConjureButton", n)


# ---------------------------------------------------------------------------------------------------------------------


def check_a_food_button_and_a_water_button_on_the_spell_names_at_the_highest_known_rank():
    lua = boot(learn=(587, 597, 990, 5504, 5505))
    assert tab(lua).OwnsShoulder(), "no shoulder"
    food, water = btns(lua)
    assert attrs(food) == {"type": "spell", "spell": "Conjure Food"}, attrs(food)
    assert attrs(water) == {"type": "spell", "spell": "Conjure Water"}, attrs(water)
    assert shown(food) and shown(water) and shown(g(lua).FSConjureTab), "not shown"
    assert food.fsSpellID == 990 and water.fsSpellID == 5505, f"ranks {food.fsSpellID} {water.fsSpellID}"
    assert food.icon._texture == 9000 + 990 or food.icon._texture is not None, "no icon"
    assert food._clicks[1] == "AnyUp" and food._clicks[2] == "AnyDown"


def check_every_rank_is_found_and_the_last_known_one_wins():
    for ranks, kind in ((FOOD, "Food"), (WATER, "Water")):
        for i in range(len(ranks)):
            lua = boot(learn=ranks[: i + 1])
            button = btns(lua)[0]
            assert button._attrs["spell"] == f"Conjure {kind}", f"{kind} rank {i + 1}"
            assert button.fsSpellID == ranks[i], f"{kind} rank {i + 1}: {button.fsSpellID}"


def check_a_new_rank_rebinds_the_spell_id_at_the_next_sync_and_nothing_in_combat():
    lua = boot(learn=(587, 5504))
    food = btns(lua)[0]
    assert food.fsSpellID == 587
    combat(lua, True)
    run(lua, "__learn(597)")
    fire(lua, "SPELLS_CHANGED")
    assert food.fsSpellID == 587, "rebound in combat"
    assert sb.blocked(lua) == 0, "a protected call was refused in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert food.fsSpellID == 597, f"not rebound at regen: {food.fsSpellID}"
    assert sb.blocked(lua) == 0


def check_only_one_of_the_two_known_shows_one_button_and_none_shows_nothing():
    lua = boot(learn=(5504,))
    first, second = btns(lua)
    assert shown(first) and not shown(second), "the buttons pack left"
    assert attrs(first) == {"type": "spell", "spell": "Conjure Water"}, attrs(first)
    assert attrs(second) == {}, "a hidden slot carries an attribute"
    sb.approx(standing(lua)[36][0], st.block_w(1), "one button wide")
    lua = boot(learn=())
    assert not tab(lua).OwnsShoulder() and not shown(g(lua).FSConjureTab) and 36 not in standing(lua)
    run(lua, "__learn(587)")
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).OwnsShoulder() and shown(btns(lua)[0]) and 36 in standing(lua), "learning did not bring the tab"


def check_another_class_builds_nothing():
    for klass in ("DRUID", "WARLOCK", "ROGUE"):
        lua = boot(klass=klass, learn=(587, 5504))
        assert g(lua).FSConjureTab is None and g(lua).FSConjureButton1 is None, f"a {klass} built the tab"
        assert not tab(lua).OwnsShoulder()


def check_the_carried_count_adds_every_rank_and_follows_the_bags():
    lua = boot(learn=(587, 990, 5504), items={5349: 3, 1114: 4, 5350: 5, 2136: 6})
    food, water = btns(lua)
    assert food.fsCount._text == "7" and water.fsCount._text == "11", (food.fsCount._text, water.fsCount._text)
    run(lua, "__items[1114] = 0")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert food.fsCount._text == "3", "the bags did not move the count"


def check_a_count_of_zero_shows_zero_and_does_not_dim():
    lua = boot(learn=(587, 5504), items={})
    food = btns(lua)[0]
    assert food.fsCount._text == "0", f"count {food.fsCount._text!r}"
    assert not food.icon._desat, "an empty stack dimmed the button you need to click"


def check_the_count_switch_off_hides_the_count_only():
    lua = boot(learn=(587, 5504), items={5349: 3})
    run(lua, 'FS.Config.Set("tabs.mage.conjureCount", false)')
    food = btns(lua)[0]
    assert not food.fsCount._text and shown(food), "the count stayed or the button went"
    assert tab(lua).SETTINGS.conjureCount.default is True
    run(lua, 'FS.Config.Set("tabs.mage.conjureCount", true)')
    assert food.fsCount._text == "3"


def check_an_unreadable_count_shows_nothing_and_never_throws():
    lua = boot(learn=(587, 5504), items={5349: 3})
    food = btns(lua)[0]
    for mode in ("secret", "throw"):
        run(lua, f'__itemMode = "{mode}"')
        fire(lua, "BAG_UPDATE_DELAYED")
        assert not food.fsCount._text, f"a {mode} count was shown: {food.fsCount._text}"
    run(lua, "__itemMode = nil")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert food.fsCount._text == "3", "did not recover"
    assert sb.blocked(lua) == 0


def check_the_cooldown_swipe_follows_the_highest_rank():
    lua = boot(learn=(587, 597, 5504))
    food = btns(lua)[0]
    run(lua, "__cd[597] = { 1000, 3 }")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sb.cd_of(food) == ("obj", 597), f"swipe {sb.cd_of(food)}"
    food._hooks["OnEnter"][1](food)
    assert g(lua).GameTooltip._spellID == 597, "the tooltip is not the highest rank"


def check_the_master_switch_off_hides_the_tab_and_frees_the_seat():
    lua = boot(learn=(587, 5504))
    run(lua, 'FS.Config.Set("tabs.mage.conjure", false)')
    assert not shown(g(lua).FSConjureTab) and not any(shown(x) for x in btns(lua)), "still shown"
    assert all(attrs(x) == {} for x in btns(lua)), "an attribute is left behind"
    assert 36 not in standing(lua), "the shoulder still stands"
    run(lua, 'FS.Config.Set("tabs.mage.conjure", true)')
    assert shown(btns(lua)[0]) and 36 in standing(lua), "did not come back"


def check_the_seat_is_36_in_alone_and_16_right_of_the_portals_tab_when_both_stand():
    lua = boot(learn=(587, 5504), portals=True)
    st_ = standing(lua)
    assert list(st_) == [36], f"alone: {st_}"
    d = csh.D(lua, btns(lua)[0])
    sb.approx(d["x"], 36 + 6, "alone, first button x")
    run(lua, "__learn(3561, 3562, 10059)")
    fire(lua, "SPELLS_CHANGED")
    st_ = standing(lua)
    want = 36 + st.block_w(2) + 16
    assert sorted(st_) == [36, round(want, 3)], f"both: {st_}, want {want}"
    sb.approx(st_[36][1], 91.8, "the portals block is two rows tall")
    sb.approx(st_[round(want, 3)][1], 49, "the conjure block is one row tall")
    sb.approx(csh.D(lua, btns(lua)[0])["x"], want + 6, "conjure button x after the portals tab")
    sb.approx(csh.D(lua, btns(lua)[1])["x"], want + 6 + 42.8, "second conjure button x")
    run(lua, "__forget(3561, 3562, 10059)")
    fire(lua, "SPELLS_CHANGED")
    assert list(standing(lua)) == [36], f"the conjure tab did not move back: {standing(lua)}"
    sb.approx(csh.D(lua, btns(lua)[0])["x"], 36 + 6, "conjure button x after the portals tab went")


def check_config_rows_and_defaults_are_the_prototypes():
    lua = boot()
    secs = [s for s in st.cfg_sections(lua) if s["title"] == "Food and water tab"]
    assert len(secs) == 1, "no Food and water tab section"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["when"]) == ("tabs", "general", "MAGE"), sec
    assert sec["tip"] == "New. Conjure Food and Conjure Water as two buttons, always your highest rank.", sec["tip"]
    assert [(r["key"], r["label"], bool(r["sub"])) for r in sec["rows"]] == [
        ("tabs.mage.conjure", "Food and water tab", False), ("tabs.mage.conjureCount", "Show how many you carry", True)]
    assert sec["rows"][1]["needs"] == "tabs.mage.conjure"
    get = g(lua).FS.Config.Get
    assert get("tabs.mage.conjure") is True and get("tabs.mage.conjureCount") is True


def check_the_file_is_in_the_toc_and_says_no_dashes():
    toc = st.TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/ConjureTab.lua")
    assert toc.index("Modules/ActionBars/PortalsTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua")
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
