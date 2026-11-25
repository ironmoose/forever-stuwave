#!/usr/bin/env python3
"""Runs the real DemonTab.lua headless on the class shoulder world (see shapeshifttab-harness.py, whose world and kit it
shares) as a Warlock, and pins the Warlock summon demon tab (ticket T6).

What is pinned here:

  * the buttons: one secure spell button per demon the Warlock can summon, in the order Imp, Voidwalker, Succubus (the
    Incubus stands in when it is the one known), Felhunter, Felguard (found by any of its rune spell ids, else by the spell's
    name), each casting by the spell name; none known shows nothing, learning one brings the tab;
  * the light: the demon that is out (UnitExists and UnitIsDead on the pet, then its creature family) is lit; none when no
    pet or a dead one is out or the family is none of ours; a secret or throwing answer keeps what was painted; the light
    switch off paints none;
  * the Soul Shard count (item 6265) on every demon that costs a shard (all but the Imp), dimmed at 0; an unreadable count
    shows nothing; its switch off shows no number and no dim; the count follows the bags in combat;
  * the seat: a one row shoulder right of the pet panel (PetDock), as wide as its buttons;
  * the master switch, another class, combat queueing and the config rows.

It is NOT the real client: whether Forever teaches a Felguard summon and under which id, which family string a Succubus
and an Incubus report, and how the tab looks are in-game checks.

    python3 tools/demontab-harness.py

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
TAB = Path(os.environ.get("DEMONTAB_LUA", ADDON / "Modules/ActionBars/DemonTab.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("shapeshifttab_harness", "shapeshifttab-harness.py")
sb, csh = st.sb, st.csh
g, run, fire, combat, shown, attrs, standing = st.g, st.run, st.fire, st.combat, st.shown, st.attrs, st.standing

# The pet that is out: exists, dead, and the creature family it reports; mode "secret" or "throw" breaks all three.
WORLD = r"""
__petExists, __petDead, __family, __petMode = false, false, nil, nil
do
    local baseExists, baseDead = UnitExists, UnitIsDead
    local function pet(read)
        if __petMode == "secret" then return __SECRET end
        if __petMode == "throw" then error("pet read blew up") end
        return read
    end
    function UnitExists(unit)
        if unit == "pet" then return pet(__petExists) end
        if baseExists then return baseExists(unit) end
        return false
    end
    function UnitIsDead(unit)
        if unit == "pet" then return pet(__petDead) end
        if baseDead then return baseDead(unit) end
        return false
    end
    function UnitCreatureFamily(unit)
        if unit == "pet" then return pet(__family) end
        return nil
    end
end
"""
IMP, VOID, SUCC, INCU, HUNT = 688, 697, 712, 713, 691
FELGUARD = (427733, 427748, 431754)
SHARD = 6265
ALL = (IMP, VOID, SUCC, HUNT, FELGUARD[0])
SPELLS = ["Summon Imp", "Summon Voidwalker", "Summon Succubus", "Summon Felhunter", "Summon Felguard"]


def boot(*, learn: tuple = ALL, out: str | None = None, shards: int | None = 5, pre: str = "", klass: str = "WARLOCK",
         **kw):
    setup = WORLD
    if out is not None:
        setup += f'__petExists = true; __family = "{out}"\n'
    if shards is not None:
        setup += f"__items[{SHARD}] = {shards}\n"
    return st.boot(klass=klass, tabs=(TAB,), learn=learn, pre=setup + pre, **kw)


def tab(lua):
    return g(lua).FS.DemonTab


def btns(lua, n=5):
    return st.buttons(lua, "FSDemonButton", n)


def lit(lua, n=5) -> list:
    return [bool(x.fsLit) for x in btns(lua, n)]


def counts(lua, n=5) -> list:
    return [x.fsCount._text or "" for x in btns(lua, n)]


def dock_seat(lua) -> float:
    return float(g(lua).FS.PetDock.DockRight()) + 16


# ---------------------------------------------------------------------------------------------------------------------


def check_one_secure_spell_button_per_known_demon_in_order():
    lua = boot()
    assert tab(lua).OwnsShoulder(), "no shoulder"
    b = btns(lua)
    assert [attrs(x) for x in b] == [{"type": "spell", "spell": s} for s in SPELLS], [attrs(x) for x in b]
    assert all(shown(x) for x in b) and shown(g(lua).FSDemonTab), "buttons or host hidden"
    assert b[0]._clicks[1] == "AnyUp" and b[0]._clicks[2] == "AnyDown"
    lua = boot(learn=(VOID, HUNT))
    assert [attrs(x).get("spell") for x in btns(lua) if shown(x)] == ["Summon Voidwalker", "Summon Felhunter"]


def check_an_incubus_stands_in_for_a_succubus_and_the_succubus_wins_when_both_are_known():
    lua = boot(learn=(IMP, INCU))
    assert [attrs(x).get("spell") for x in btns(lua) if shown(x)] == ["Summon Imp", "Summon Incubus"]
    lua = boot(learn=(IMP, SUCC, INCU))
    assert [attrs(x).get("spell") for x in btns(lua) if shown(x)] == ["Summon Imp", "Summon Succubus"]


def check_the_felguard_is_found_by_any_of_its_rune_ids_else_by_name():
    for rune in FELGUARD:
        lua = boot(learn=(IMP, rune))
        got = [attrs(x).get("spell") for x in btns(lua) if shown(x)]
        assert got == ["Summon Imp", "Summon Felguard"], f"rune {rune}: {got}"
    lua = boot(learn=(IMP,), pre='__names[999999] = "Summon Felguard"; __byName["Summon Felguard"] = 999999; __learn(999999)')
    assert [attrs(x).get("spell") for x in btns(lua) if shown(x)] == ["Summon Imp", "Summon Felguard"], \
        "a Felguard known only under an id the tab does not list was not found by its name"


def check_no_demon_known_shows_no_tab_and_learning_one_brings_it():
    lua = boot(learn=())
    assert not tab(lua).OwnsShoulder() and not shown(g(lua).FSDemonTab) and not any(shown(x) for x in btns(lua))
    assert round(dock_seat(lua), 3) not in standing(lua), "a shoulder stands with nothing to show"
    run(lua, f"__learn({IMP})")
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).OwnsShoulder() and shown(btns(lua)[0]) and attrs(btns(lua)[0])["spell"] == "Summon Imp"
    assert round(dock_seat(lua), 3) in standing(lua)


def check_the_demon_that_is_out_is_lit_and_none_when_none_is_out():
    lua = boot(out="Voidwalker")
    assert lit(lua) == [False, True, False, False, False], "the demon out is not the one lit"
    assert shown(btns(lua)[1].fsWash) and not shown(btns(lua)[0].fsWash)
    run(lua, '__family = "Felhunter"')
    fire(lua, "UNIT_PET", "player")
    assert lit(lua) == [False, False, False, True, False], "the light did not move"
    run(lua, '__family = "Imp"')
    fire(lua, "PET_BAR_UPDATE")
    assert lit(lua) == [True, False, False, False, False]
    run(lua, '__family = "Felguard"')
    fire(lua, "UNIT_PET", "player")
    assert lit(lua) == [False, False, False, False, True]
    run(lua, "__petExists = false")
    fire(lua, "UNIT_PET", "player")
    assert not any(lit(lua)), "lit with no pet out"
    run(lua, "__petExists = true; __petDead = true")
    fire(lua, "UNIT_PET", "player")
    assert not any(lit(lua)), "lit with a dead pet"
    run(lua, '__petDead = false; __family = "Doomguard"')
    fire(lua, "UNIT_PET", "player")
    assert not any(lit(lua)), "lit for a pet that is none of ours"


def check_a_succubus_and_an_incubus_light_the_one_button_they_share():
    lua = boot(learn=(IMP, SUCC), out="Succubus")
    assert lit(lua, 2) == [False, True]
    run(lua, '__family = "Incubus"')
    fire(lua, "UNIT_PET", "player")
    assert lit(lua, 2) == [False, True], "an Incubus out did not light the Succubus button"
    lua = boot(learn=(IMP, INCU), out="Incubus")
    assert lit(lua, 2) == [False, True]


def check_an_unreadable_pet_keeps_the_light_and_the_switch_off_paints_none():
    lua = boot(out="Imp")
    assert lit(lua)[0]
    for mode in ("secret", "throw"):
        run(lua, f'__petMode = "{mode}"')
        fire(lua, "UNIT_PET", "player")
        assert lit(lua)[0], f"a {mode} pet read cleared the light"
        assert not any(lit(lua)[1:]), f"a {mode} pet read lit another"
    run(lua, '__petMode = nil; FS.Config.Set("tabs.warlock.demonsLit", false)')
    assert not any(lit(lua)), "lit with the switch off"
    fire(lua, "UNIT_PET", "player")
    assert not any(lit(lua)), "the pet event relit it"
    assert tab(lua).SETTINGS.demonsLit.default is True
    run(lua, 'FS.Config.Set("tabs.warlock.demonsLit", true)')
    assert lit(lua)[0], "the light did not come back with its switch"


def check_shards_count_the_costly_demons_dim_at_zero_and_say_nothing_when_unreadable():
    lua = boot(shards=7)
    assert counts(lua) == ["", "7", "7", "7", "7"], f"the Imp costs no shard: {counts(lua)}"
    assert not any(x.icon._desat for x in btns(lua)), "dimmed with shards in the bag"
    run(lua, f"__items[{SHARD}] = 0")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert counts(lua) == ["", "0", "0", "0", "0"], counts(lua)
    assert [bool(x.icon._desat) for x in btns(lua)] == [False, True, True, True, True], "the costly demons did not dim"
    run(lua, '__itemMode = "secret"')
    fire(lua, "BAG_UPDATE_DELAYED")
    assert counts(lua) == [""] * 5, f"a secret count showed: {counts(lua)}"
    assert not any(x.icon._desat for x in btns(lua)), "dimmed on a count nobody could read"
    run(lua, '__itemMode = "throw"')
    fire(lua, "BAG_UPDATE_DELAYED")
    assert counts(lua) == [""] * 5
    run(lua, '__itemMode = nil; FS.Config.Set("tabs.warlock.demonsShards", false)')
    assert counts(lua) == [""] * 5 and not any(x.icon._desat for x in btns(lua)), "number or dim with the switch off"
    assert tab(lua).SETTINGS.demonsShards.default is True
    run(lua, 'FS.Config.Set("tabs.warlock.demonsShards", true)')
    assert counts(lua)[1] == "0"


def check_the_master_switch_off_hides_the_tab_and_frees_the_seat():
    lua = boot()
    seat = dock_seat(lua)
    assert round(seat, 3) in standing(lua), f"the shoulder is not right of the pet panel: {standing(lua)} vs {seat}"
    run(lua, 'FS.Config.Set("tabs.warlock.demons", false)')
    assert not shown(g(lua).FSDemonTab) and not any(shown(x) for x in btns(lua))
    assert all(attrs(x) == {} for x in btns(lua)), "an attribute is left behind"
    assert round(seat, 3) not in standing(lua), "the shoulder still stands"
    run(lua, 'FS.Config.Set("tabs.warlock.demons", true)')
    assert shown(btns(lua)[0]) and round(seat, 3) in standing(lua)


def check_the_seat_is_a_one_row_block_right_of_the_pet_panel():
    lua = boot()
    seat = dock_seat(lua)
    st_ = standing(lua)
    assert round(seat, 3) in st_, st_
    sb.approx(st_[round(seat, 3)][0], st.block_w(5), "block width")
    sb.approx(st_[round(seat, 3)][1], 49, "block height")
    for i, btn in enumerate(btns(lua)):
        sb.approx(csh.D(lua, btn)["x"], seat + 6 + i * 42.8, f"button {i + 1} x")
    lua = boot(learn=(IMP, VOID))
    sb.approx(standing(lua)[round(dock_seat(lua), 3)][0], st.block_w(2), "two button block width")


def check_another_class_builds_nothing():
    for klass in ("DRUID", "HUNTER", "ROGUE"):
        lua = boot(klass=klass)
        assert g(lua).FSDemonTab is None and g(lua).FSDemonButton1 is None, f"a {klass} built the tab"
        assert not tab(lua).OwnsShoulder()


def check_combat_touches_nothing_protected_and_the_update_waits_for_regen():
    lua = boot(learn=(IMP, VOID), out="Imp", shards=3)
    combat(lua, True)
    run(lua, f"__learn({HUNT}); __family = 'Voidwalker'; __items[{SHARD}] = 1")
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "UNIT_PET", "player")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert sb.blocked(lua) == 0, "a protected call was refused"
    assert tab(lua).T.pendingSync, "nothing was parked"
    assert not shown(btns(lua)[2]), "a button came in combat"
    assert lit(lua, 2) == [False, True], "the light did not follow in combat"
    assert counts(lua, 2) == ["", "1"], "the count did not follow the bags in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).T.pendingSync
    assert [x._attrs["spell"] for x in btns(lua)[:3]] == ["Summon Imp", "Summon Voidwalker", "Summon Felhunter"]
    assert sb.blocked(lua) == 0


def check_config_rows_and_defaults_are_the_prototypes():
    lua = boot()
    secs = [s for s in st.cfg_sections(lua) if s["title"] == "Summon demon tab"]
    assert len(secs) == 1, "no Summon demon tab section"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["when"]) == ("tabs", "general", "WARLOCK"), sec
    assert sec["tip"] == ("New. One button per demon you know: Imp, Voidwalker, Succubus, Felhunter, Felguard. Click one to "
                          "summon it."), sec["tip"]
    assert [(r["key"], r["label"], bool(r["sub"])) for r in sec["rows"]] == [
        ("tabs.warlock.demons", "Summon demon tab", False), ("tabs.warlock.demonsLit", "Light the demon that is out", True),
        ("tabs.warlock.demonsShards", "Show Soul Shard count", True)], sec["rows"]
    assert all(r["needs"] == "tabs.warlock.demons" for r in sec["rows"][1:])
    get = g(lua).FS.Config.Get
    for key in ("demons", "demonsLit", "demonsShards"):
        assert get(f"tabs.warlock.{key}") is True, key


def check_the_file_is_in_the_toc_and_says_no_dashes():
    toc = st.TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/DemonTab.lua")
    assert toc.index("Modules/ActionBars/PoisonsTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua")
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
