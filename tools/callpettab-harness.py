#!/usr/bin/env python3
"""Runs the real CallPetTab.lua headless on the class shoulder world (see shapeshifttab-harness.py, whose world and kit it
shares) as a Hunter, and pins the Hunter call pet tab (ticket T2).

What is pinned here:

  * who: a Hunter whose client lists MORE THAN ONE callable pet gets the tab, one secure spell button per pet on that pet's
    Call Pet spell; none, one pet, a pet whose Call Pet slot spell is not learned (Forever teaches only Call Pet, slot 1),
    a client with no pet list API, another class or the master switch off shows nothing;
  * the extras: Revive Pet and Dismiss Pet after the pets, only while their switch is on and the spell is known;
  * the light: the pet that is out (UnitName("pet") against the list) is lit, none when no pet is out, none with the light
    switch off, an unreadable name keeps the last light;
  * the seat: a one row shoulder right of the pet panel (PetDock), as wide as its buttons;
  * combat: nothing protected is touched, the list change waits for regen; the config rows and defaults.

It is NOT the real client: which fields the client's pet list carries, whether Forever ever lists a second pet, and how the
tab looks are in-game checks (the harness feeds the retail shape: a list of { name, icon, slotID }).

    python3 tools/callpettab-harness.py

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
TAB = Path(os.environ.get("CALLPETTAB_LUA", ADDON / "Modules/ActionBars/CallPetTab.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = _load("shapeshifttab_harness", "shapeshifttab-harness.py")
sb, csh = st.sb, st.csh
g, run, fire, combat, shown, attrs, standing = st.g, st.run, st.fire, st.combat, st.shown, st.attrs, st.standing

# The client's pet list (retail shape) and the pet that is out.
WORLD = r"""
__pets, __petOut, __petMode, __listMode = {}, nil, nil, nil
C_StableInfo = C_StableInfo or {}
C_StableInfo.GetActivePetList = function()
    if __listMode == "secret" then return __SECRET end
    if __listMode == "throw" then error("GetActivePetList blew up") end
    return __pets
end
do
    local base = UnitName
    function UnitName(unit)
        if unit == "pet" then
            if __petMode == "secret" then return __SECRET end
            if __petMode == "throw" then error("UnitName blew up") end
            return __petOut
        end
        if base then return base(unit) end
        return "Hunter"
    end
end
function __setPets(list)
    __pets = {}
    for i, p in ipairs(list) do __pets[i] = { name = p[1], icon = 7000 + i, slotID = i } end
end
"""
CALLS = (883, 83242, 83243, 83244, 83245)


def boot(*, learn: tuple = (883, 982, 2641), pets: list | None = None, out: str | None = None, pre: str = "",
         klass: str = "HUNTER", **kw):
    setup = WORLD
    if pets is not None:
        setup += "__setPets({" + ",".join(f'{{"{n}"}}' for n in pets) + "})\n"
    if out is not None:
        setup += f'__petOut = "{out}"\n'
    return st.boot(klass=klass, tabs=(TAB,), learn=learn, pre=setup + pre, **kw)


def tab(lua):
    return g(lua).FS.CallPetTab


def btns(lua, n=7):
    return st.buttons(lua, "FSCallPetButton", n)


THREE = ("Rex", "Cat", "Owl")
ALL_CALLS = CALLS + (982, 2641)


def dock_seat(lua) -> float:
    return float(g(lua).FS.PetDock.DockRight()) + 16


# ---------------------------------------------------------------------------------------------------------------------


def check_three_pets_get_three_call_pet_buttons_and_the_extras():
    lua = boot(learn=ALL_CALLS, pets=THREE, out="Rex")
    t = tab(lua)
    assert t.OwnsShoulder(), "no shoulder"
    b = btns(lua)
    got = [attrs(x) for x in b[:5]]
    assert got == [
        {"type": "spell", "spell": "Call Pet"}, {"type": "spell", "spell": "Call Pet 2"},
        {"type": "spell", "spell": "Call Pet 3"}, {"type": "spell", "spell": "Revive Pet"},
        {"type": "spell", "spell": "Dismiss Pet"}], got
    assert all(shown(x) for x in b[:5]) and not any(shown(x) for x in b[5:]), "wrong buttons shown"
    assert shown(g(lua).FSCallPetTab), "host hidden"
    assert b[0]._clicks[1] == "AnyUp" and b[0]._clicks[2] == "AnyDown"


def check_no_pet_and_one_pet_show_nothing_and_a_second_brings_the_tab():
    for pets in ([], ["Rex"]):
        lua = boot(learn=ALL_CALLS, pets=pets, out="Rex")
        assert not tab(lua).OwnsShoulder(), f"a shoulder with {len(pets)} pets"
        assert not shown(g(lua).FSCallPetTab), "host shown"
        assert not any(shown(x) for x in btns(lua)), "a button shown"
    lua = boot(learn=ALL_CALLS, pets=["Rex"])
    run(lua, '__setPets({{"Rex"}, {"Cat"}})')
    fire(lua, "PET_STABLE_UPDATE")
    assert tab(lua).OwnsShoulder() and shown(btns(lua)[0]), "a second pet did not bring the tab"
    assert [x._attrs["spell"] for x in btns(lua)[:4]] == ["Call Pet", "Call Pet 2", "Revive Pet", "Dismiss Pet"]
    run(lua, '__setPets({{"Rex"}})')
    fire(lua, "PET_STABLE_UPDATE")
    assert not tab(lua).OwnsShoulder() and not shown(btns(lua)[0]), "losing the pet did not hide the tab"


def check_a_pets_slot_spell_that_is_not_learned_hides_it_the_forever_case():
    # Forever teaches Call Pet only: a second listed pet has no spell to call it with
    lua = boot(learn=(883, 982, 2641), pets=THREE)
    assert not tab(lua).OwnsShoulder(), "the tab shows pets it cannot call"
    lua = boot(learn=(883, 83242, 982), pets=THREE)
    assert [x._attrs["spell"] for x in btns(lua)[:3]] == ["Call Pet", "Call Pet 2", "Revive Pet"], \
        "a pet without its spell was not skipped"


def check_a_client_with_no_pet_list_or_a_bad_answer_hides_it_and_never_throws():
    lua = boot(learn=ALL_CALLS, pets=THREE)
    for mode in ("secret", "throw"):
        run(lua, f'__listMode = "{mode}"')
        fire(lua, "PET_STABLE_UPDATE")
        assert not tab(lua).OwnsShoulder(), f"{mode} list still shows the tab"
    run(lua, '__listMode = nil')
    fire(lua, "PET_STABLE_UPDATE")
    assert tab(lua).OwnsShoulder(), "did not recover"
    run(lua, "C_StableInfo = nil")
    fire(lua, "PET_STABLE_UPDATE")
    assert not tab(lua).OwnsShoulder(), "no pet API still shows the tab"
    run(lua, "C_StableInfo = { GetActivePetList = function() return { 5, 'x', { name = __SECRET } } end }")
    fire(lua, "PET_STABLE_UPDATE")
    assert not tab(lua).OwnsShoulder(), "junk entries counted as pets"
    assert sb.blocked(lua) == 0


def check_revive_and_dismiss_follow_their_switch_and_the_spell_being_known():
    lua = boot(learn=ALL_CALLS, pets=THREE)
    assert tab(lua).SETTINGS.petsExtra.default is True
    run(lua, 'FS.Config.Set("tabs.hunter.petsExtra", false)')
    b = btns(lua)
    assert [x._attrs["spell"] for x in b[:4]] == ["Call Pet", "Call Pet 2", "Call Pet 3", None], "extras stayed"
    assert not shown(b[3]) and not shown(b[4]), "an extra stayed shown"
    run(lua, 'FS.Config.Set("tabs.hunter.petsExtra", true)')
    assert shown(b[3]) and b[3]._attrs["spell"] == "Revive Pet" and b[4]._attrs["spell"] == "Dismiss Pet"
    run(lua, "__forget(2641)")
    fire(lua, "SPELLS_CHANGED")
    assert shown(b[3]) and not shown(b[4]), "an unknown Dismiss Pet was offered"


def check_the_pet_that_is_out_is_lit_and_none_when_none_is_out():
    lua = boot(learn=ALL_CALLS, pets=THREE, out="Cat")
    b = btns(lua)
    assert [bool(x.fsLit) for x in b[:5]] == [False, True, False, False, False], "the pet out is not the one lit"
    assert shown(b[1].fsWash) and not shown(b[0].fsWash)
    run(lua, "__petOut = nil")
    fire(lua, "UNIT_PET", "player")
    assert not any(x.fsLit for x in b[:5]), "lit with no pet out"
    run(lua, '__petOut = "Owl"')
    fire(lua, "UNIT_PET", "player")
    assert [bool(x.fsLit) for x in b[:3]] == [False, False, True], "the light did not move"


def check_the_light_switch_off_draws_nothing_lit_and_an_unreadable_name_keeps_it():
    lua = boot(learn=ALL_CALLS, pets=THREE, out="Rex")
    assert btns(lua)[0].fsLit
    run(lua, '__petMode = "secret"')
    fire(lua, "UNIT_PET", "player")
    assert btns(lua)[0].fsLit, "an unreadable name cleared the light"
    run(lua, '__petMode = "throw"')
    fire(lua, "UNIT_PET", "player")
    assert btns(lua)[0].fsLit, "a throwing name cleared the light"
    run(lua, '__petMode = nil; FS.Config.Set("tabs.hunter.petsLit", false)')
    assert not any(x.fsLit for x in btns(lua)), "lit with the switch off"
    fire(lua, "UNIT_PET", "player")
    assert not any(x.fsLit for x in btns(lua)), "the pet event relit it"
    assert tab(lua).SETTINGS.petsLit.default is True


def check_the_master_switch_off_hides_the_tab_and_frees_the_seat():
    lua = boot(learn=ALL_CALLS, pets=THREE)
    seat = dock_seat(lua)
    assert round(seat, 3) in standing(lua), f"the shoulder is not right of the pet panel: {standing(lua)} vs {seat}"
    run(lua, 'FS.Config.Set("tabs.hunter.pets", false)')
    assert not shown(g(lua).FSCallPetTab) and not any(shown(x) for x in btns(lua))
    assert all(attrs(x) == {} for x in btns(lua)), "an attribute is left behind"
    assert round(seat, 3) not in standing(lua), "the shoulder still stands"
    run(lua, 'FS.Config.Set("tabs.hunter.pets", true)')
    assert shown(btns(lua)[0]) and round(seat, 3) in standing(lua)


def check_the_seat_is_a_one_row_block_right_of_the_pet_panel():
    lua = boot(learn=ALL_CALLS, pets=THREE)
    seat = dock_seat(lua)
    st_ = standing(lua)
    assert round(seat, 3) in st_, st_
    sb.approx(st_[round(seat, 3)][0], st.block_w(5), "block width")
    sb.approx(st_[round(seat, 3)][1], 49, "block height")
    for i, btn in enumerate(btns(lua)[:5]):
        d = csh.D(lua, btn)
        sb.approx(d["x"], seat + 6 + i * 42.8, f"button {i + 1} x")


def check_another_class_builds_nothing():
    for klass in ("DRUID", "WARLOCK", "WARRIOR"):
        lua = boot(klass=klass, learn=ALL_CALLS, pets=THREE)
        assert g(lua).FSCallPetTab is None and g(lua).FSCallPetButton1 is None, f"a {klass} built the tab"
        assert not tab(lua).OwnsShoulder()


def check_combat_touches_nothing_protected_and_the_update_waits_for_regen():
    lua = boot(learn=ALL_CALLS, pets=THREE, out="Rex")
    combat(lua, True)
    run(lua, '__setPets({{"Rex"}, {"Cat"}}); __petOut = "Cat"')
    fire(lua, "PET_STABLE_UPDATE")
    fire(lua, "UNIT_PET", "player")
    assert sb.blocked(lua) == 0, "a protected call was refused"
    assert tab(lua).T.pendingSync, "nothing was parked"
    assert shown(btns(lua)[2]), "the third button was hidden in combat"
    assert btns(lua)[1].fsLit and not btns(lua)[0].fsLit, "the light did not follow in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).T.pendingSync
    assert [x._attrs["spell"] for x in btns(lua)[:4]] == ["Call Pet", "Call Pet 2", "Revive Pet", "Dismiss Pet"]
    assert sb.blocked(lua) == 0


def check_config_rows_and_defaults_are_the_prototypes():
    lua = boot(learn=ALL_CALLS, pets=THREE)
    secs = [s for s in st.cfg_sections(lua) if s["title"] == "Call pet tab"]
    assert len(secs) == 1, "no Call pet tab section"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["when"]) == ("tabs", "general", "HUNTER"), sec
    assert sec["tip"] == ("New. One button per tamed pet, so you pick which one comes. It only shows once you have more "
                          "than one pet."), sec["tip"]
    assert [(r["key"], r["label"], bool(r["sub"])) for r in sec["rows"]] == [
        ("tabs.hunter.pets", "Call pet tab", False), ("tabs.hunter.petsLit", "Light the pet that is out", True),
        ("tabs.hunter.petsExtra", "Add Revive Pet and Dismiss Pet", True)], sec["rows"]
    assert all(r["needs"] == "tabs.hunter.pets" for r in sec["rows"][1:])
    get = g(lua).FS.Config.Get
    assert get("tabs.hunter.pets") is True and get("tabs.hunter.petsLit") is True and get("tabs.hunter.petsExtra") is True


def check_the_file_is_in_the_toc_and_says_no_dashes():
    toc = st.TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/CallPetTab.lua")
    assert toc.index("Modules/ActionBars/ShapeshiftTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua")
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
