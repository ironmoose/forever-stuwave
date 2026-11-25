#!/usr/bin/env python3
"""Runs the real ShapeshiftTab.lua headless on the class shoulder world (sealbar and classshoulder harness mocks) as a Druid,
and pins the Druid shapeshift tab (ticket T1) and the class tab kit (FS.ClassTabKit) the five other class tabs are built on.

What is pinned here:

  * who: a Druid with any form learned gets the tab, one button per learned form in the order Bear, Cat, Travel, Aquatic,
    Moonkin (Dire Bear replaces Bear), each a secure spell button on the form's NAME; another class, no form, or the master
    switch off builds and shows nothing, and learning a form brings it;
  * the seat: a one row shoulder as wide as the buttons, 36 design px in from the chassis left (a Druid has no pet panel),
    the buttons packed left on the Paladin's cell pitch, the host anchored only out of combat;
  * the light: the form the player is in lights its button (GetShapeshiftForm, then the form's spell id), none lights out
    of form, the light switch off draws none, and an unreadable answer keeps the last light;
  * the caster button: off by default, a /cancelform macro button after the forms when its switch is on, lit out of form;
  * combat: nothing protected is touched, the update waits for regen, the light and the cooldown follow in combat;
  * the cooldown swipe from the duration object, the tooltip, secret and throwing client answers, the config rows;
  * the kit: the shared helpers the sibling tabs use (also pinned again by their own harnesses).

It is NOT the real client: how the engine answers GetShapeshiftFormInfo for a Druid, whether /cancelform is accepted as a
secure macro, and how the tab looks are in-game checks.

    python3 tools/shapeshifttab-harness.py

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
KIT = Path(os.environ.get("SHAPESHIFTTAB_LUA", ADDON / "Modules/ActionBars/ShapeshiftTab.lua"))
TOC = ADDON / "forever-stuwave.toc"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csh = _load("classshoulder_harness", "classshoulder-harness.py")
sb = csh.sb
g = sb.g

# Spell ids and English names the six class tabs read (client data 16001; Call Pet 2 to 5 are the retail ids, which Forever
# does not teach, so they appear only in stubs).
NAMES = {
    5487: "Bear Form", 9634: "Dire Bear Form", 768: "Cat Form", 783: "Travel Form", 1066: "Aquatic Form",
    24858: "Moonkin Form",
    883: "Call Pet", 982: "Revive Pet", 2641: "Dismiss Pet", 83242: "Call Pet 2", 83243: "Call Pet 3",
    83244: "Call Pet 4", 83245: "Call Pet 5",
    3561: "Teleport: Stormwind", 3562: "Teleport: Ironforge", 3563: "Teleport: Undercity", 3565: "Teleport: Darnassus",
    3566: "Teleport: Thunder Bluff", 3567: "Teleport: Orgrimmar", 1297659: "Teleport: Dalaran",
    10059: "Portal: Stormwind", 11416: "Portal: Ironforge", 11417: "Portal: Orgrimmar", 11418: "Portal: Undercity",
    11419: "Portal: Darnassus", 11420: "Portal: Thunder Bluff",
    587: "Conjure Food", 597: "Conjure Food", 990: "Conjure Food", 6129: "Conjure Food", 10144: "Conjure Food",
    10145: "Conjure Food", 28612: "Conjure Food",
    5504: "Conjure Water", 5505: "Conjure Water", 5506: "Conjure Water", 6127: "Conjure Water", 10138: "Conjure Water",
    10139: "Conjure Water", 10140: "Conjure Water", 468766: "Conjure Water",
    8681: "Instant Poison", 8687: "Instant Poison II", 8691: "Instant Poison III", 11341: "Instant Poison IV",
    11342: "Instant Poison V", 11343: "Instant Poison VI",
    2835: "Deadly Poison", 2837: "Deadly Poison II", 11357: "Deadly Poison III", 11358: "Deadly Poison IV",
    25347: "Deadly Poison V", 3420: "Crippling Poison", 3421: "Crippling Poison II",
    5763: "Mind-numbing Poison", 8694: "Mind-numbing Poison II", 11400: "Mind-numbing Poison III",
    13220: "Wound Poison", 13228: "Wound Poison II", 13229: "Wound Poison III", 13230: "Wound Poison IV",
    688: "Summon Imp", 697: "Summon Voidwalker", 712: "Summon Succubus", 713: "Summon Incubus", 691: "Summon Felhunter",
    427733: "Summon Felguard", 427748: "Summon Felguard", 431754: "Summon Felguard",
}

# The client the tabs read: the clock, the spellbook (known ids, names both ways), item counts, the shapeshift forms, and the
# few Region and tooltip bits the mock leaves out. Everything has a mode switch so a check can make it secret or throw.
WORLD = r"""
__now = 1000
function GetTime() return __now end
__known, __names, __byName = {}, {}, {}
for id, name in pairs(__NAMES) do __names[id] = name; if not __byName[name] then __byName[name] = id end end
function __learn(...) for _, id in ipairs({ ... }) do __known[id] = true end end
function __forget(...) for _, id in ipairs({ ... }) do __known[id] = nil end end
__knownMode, __infoMode, __itemMode = nil, nil, nil
function IsPlayerSpell(id)
    if __knownMode == "secret" then return __SECRET end
    if __knownMode == "throw" then error("IsPlayerSpell blew up") end
    return __known[id] == true
end
C_Spell.GetSpellInfo = function(arg)
    if __infoMode == "secret" then return __SECRET end
    if __infoMode == "throw" then error("GetSpellInfo blew up") end
    local id = type(arg) == "number" and arg or __byName[arg]
    local name = id and __names[id]
    if name then return { name = name, spellID = id, iconID = 9000 + id } end
end
-- bags: item id -> count
__items = {}
C_Item = C_Item or {}
C_Item.GetItemCount = function(id)
    if __itemMode == "secret" then return __SECRET end
    if __itemMode == "throw" then error("GetItemCount blew up") end
    return __items[id] or 0
end
GetItemCount = C_Item.GetItemCount
-- the Druid's shapeshift forms: list of { id, active }
__sf = {}
__sfMode = nil
function GetNumShapeshiftForms() return #__sf end
function GetShapeshiftFormInfo(i)
    local f = __sf[i]
    if not f then return end
    return 8000 + f.id, f.active, true, f.id
end
function GetShapeshiftForm()
    if __sfMode == "secret" then return __SECRET end
    if __sfMode == "throw" then error("GetShapeshiftForm blew up") end
    for i, f in ipairs(__sf) do if f.active then return i end end
    return 0
end
function __setForms(list)
    __sf = {}
    for i, f in ipairs(list) do __sf[i] = { id = f[1], active = f[2] and true or false } end
end
function __enter(id) for _, f in ipairs(__sf) do f.active = f.id == id end end
-- Region and tooltip bits
function __Region:SetDesaturated(v) self._desat = v end
function GameTooltip:SetOwner(owner) self._owner = owner end
function GameTooltip:SetText(t) self._text = t end
function GameTooltip:SetItemByID(id) self._itemID = id end
__plays = {}
function __Region:CreateAnimationGroup()
    local owner = self
    local group = { _playing = false, _anims = {} }
    function group:SetLooping(v) self._looping = v end
    function group:Play() self._playing = true; __plays[#__plays + 1] = owner end
    function group:Stop() self._playing = false end
    function group:IsPlaying() return self._playing end
    function group:CreateAnimation(kind)
        local anim = setmetatable({ _kind = kind }, { __index = function() return function() end end })
        group._anims[#group._anims + 1] = anim
        return anim
    end
    return group
end
-- the tab hosts parent secure buttons, so the client protects them (the shoulder harness marks only its own)
do
    local create = CreateFrame
    function CreateFrame(kind, name, ...)
        local f = create(kind, name, ...)
        if type(name) == "string" and name:match("^FS%a+Tab$") then f._protected = true end
        return f
    end
end
-- a fake config window: records the sections the tabs add, builds nothing
__cfg = { sections = {} }
FS.ConfigWindow = {
    ClassWhen = function(token) return function() return token end end,
    UI = { Toggle = function(content, o) content.rows[#content.rows + 1] = o end },
    ExtendTab = function(page, tab, title, build, order)
        local content = { rows = {} }
        __cfg.sections[#__cfg.sections + 1] = { page = page, tab = tab, title = title, content = content, build = build,
            order = order }
        return true
    end,
}
"""


def boot(*, klass: str = "DRUID", tabs: tuple = (), combat: bool = False, pre: str = "", scale: float = 1.0,
         forms: list | None = None, learn: tuple = (), config: bool = True):
    """The sealbar world as `klass` with the kit file and `tabs` (more tab files) loaded after the class shoulder.
    `learn` is spell ids known at login, `forms` the Druid's (id, active) forms."""
    names = "__NAMES = {" + ",".join(f"[{k}]={v!r}".replace("'", '"') for k, v in NAMES.items()) + "}\n"
    world = names + WORLD
    if not config:
        world += "FS.ConfigWindow = nil\n"
    if learn:
        world += "__learn(" + ",".join(str(i) for i in learn) + ")\n"
    if forms is not None:
        world += "__setForms({" + ",".join("{%d,%s}" % (i, "true" if a else "false") for i, a in forms) + "})\n"
    return sb.boot(scale, klass=klass, known=[], combat=combat, sealbar=False,
                   extra_lua=csh.PATCH, extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, KIT) + tuple(tabs),
                   pre_login=world + pre)


def run(lua, code):
    lua.execute(code)


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


def combat(lua, on: bool):
    run(lua, f"__combat = {'true' if on else 'false'}")


def kit(lua):
    return g(lua).FS.ClassTabKit


def tab(lua, field="ShapeshiftTab"):
    return g(lua).FS[field]


def buttons(lua, prefix="FSShapeshiftButton", n=6):
    return [g(lua)[f"{prefix}{i}"] for i in range(1, n + 1)]


def shown(frame) -> bool:
    return bool(frame._shown)


def attrs(button) -> dict:
    t = button._attrs
    return {k: t[k] for k in ("type", "spell", "macrotext") if t[k] is not None}


def standing(lua) -> dict:
    out = {}
    lua.execute("__stand = {}")
    lua.execute("FS.ClassShoulder.EachStanding(function(dx, w, h) __stand[#__stand + 1] = { dx, w, h } end)")
    t = g(lua).__stand
    for i in range(1, len(t) + 1):
        out[round(t[i][1], 3)] = (round(t[i][2], 3), round(t[i][3], 3))
    return out


def block_w(cols: int) -> float:
    return 2 * 6 + cols * 38 + (cols - 1) * 4.8


def plays(lua) -> list:
    t = g(lua).__plays
    return [t[i] for i in range(1, len(t) + 1)]


def cfg_sections(lua) -> list[dict]:
    """Every section a tab added to the (fake) config window, built: title opts, rows, the class it shows for."""
    out = []
    t = g(lua).__cfg.sections
    for i in range(1, len(t) + 1):
        sec = t[i]
        sec.build(sec.content)
        title = sec.title
        rows = [dict(label=r.label, key=r.key, tip=r.tip, sub=r.sub, needs=r.needs, nl=r.nl)
                for r in (sec.content.rows[j] for j in range(1, len(sec.content.rows) + 1))]
        out.append(dict(page=sec.page, tab=sec.tab, title=title.title, tip=title.tip, when=title.when(), rows=rows,
                        order=sec.order))
    return out


DRUID_ALL = (5487, 768, 783, 1066, 24858)


# ---------------------------------------------------------------------------------------------------------------------


def check_one_button_per_learned_form_in_order_on_the_form_name():
    lua = boot(learn=(783, 5487, 768))
    t = tab(lua)
    assert t.OwnsShoulder(), "no shoulder"
    b = buttons(lua)
    assert [attrs(x) for x in b[:3]] == [
        {"type": "spell", "spell": "Bear Form"}, {"type": "spell", "spell": "Cat Form"},
        {"type": "spell", "spell": "Travel Form"}], f"attributes {[attrs(x) for x in b]}"
    assert all(shown(x) for x in b[:3]) and not any(shown(x) for x in b[3:]), "wrong buttons shown"
    assert all(attrs(x) == {} for x in b[3:]), "a hidden slot carries an attribute"
    assert shown(g(lua).FSShapeshiftTab), "host hidden"
    assert b[0]._clicks[1] == "AnyUp" and b[0]._clicks[2] == "AnyDown", "clicks not registered on up and down"


def check_all_five_forms_and_dire_bear_replaces_bear():
    lua = boot(learn=DRUID_ALL + (9634,))
    b = buttons(lua)
    assert [x._attrs["spell"] for x in b[:5]] == ["Dire Bear Form", "Cat Form", "Travel Form", "Aquatic Form",
                                                   "Moonkin Form"], [x._attrs["spell"] for x in b]
    assert not shown(b[5]), "the caster slot is up without its switch"


def check_no_form_known_shows_nothing_and_learning_brings_it():
    lua = boot()
    t = tab(lua)
    assert not t.OwnsShoulder(), "a shoulder with no form"
    assert not shown(g(lua).FSShapeshiftTab), "host shown with no form"
    assert 36 not in standing(lua), "a shoulder stands"
    run(lua, "__learn(768)")
    fire(lua, "SPELLS_CHANGED")
    assert t.OwnsShoulder() and shown(buttons(lua)[0]), "learning did not bring the tab"
    assert 36 in standing(lua), "the shoulder did not stand"
    assert buttons(lua)[0]._attrs["spell"] == "Cat Form"


def check_another_class_builds_nothing():
    for klass in ("PALADIN", "WARRIOR", "MAGE"):
        lua = boot(klass=klass, learn=DRUID_ALL)
        assert g(lua).FSShapeshiftTab is None, f"a {klass} built the host"
        assert g(lua).FSShapeshiftButton1 is None, f"a {klass} built a button"
        assert not tab(lua).OwnsShoulder(), f"a {klass} owns a shoulder"
        assert 36 not in standing(lua), f"a {klass} got a shoulder"


def check_the_master_switch_off_hides_everything_and_frees_the_seat():
    lua = boot(learn=DRUID_ALL)
    run(lua, 'FS.Config.Set("tabs.druid.forms", false)')
    assert not shown(g(lua).FSShapeshiftTab), "host still shown"
    assert not any(shown(x) for x in buttons(lua)), "a button still shown"
    assert all(attrs(x) == {} for x in buttons(lua)), "an attribute is left behind"
    assert 36 not in standing(lua), "the shoulder still stands"
    assert not tab(lua).OwnsShoulder()
    run(lua, 'FS.Config.Set("tabs.druid.forms", true)')
    assert shown(g(lua).FSShapeshiftTab) and shown(buttons(lua)[0]), "did not come back"
    assert 36 in standing(lua)


def check_the_tab_owns_the_forms_for_the_stance_bar_only_while_it_is_on():
    lua = boot(learn=DRUID_ALL)
    assert tab(lua).OwnsForms() is True
    rebuilds = []
    run(lua, "FS.StanceBar = { Rebuild = function() __stanceRebuilds = (__stanceRebuilds or 0) + 1 end }")
    run(lua, 'FS.Config.Set("tabs.druid.forms", false)')
    assert tab(lua).OwnsForms() is False, "off: the stance bar draws the forms again"
    assert g(lua).__stanceRebuilds == 1, "the stance bar was asked to rebuild"
    other = boot(klass="WARRIOR")
    assert not tab(other).OwnsForms(), "another class never owns forms"


def check_the_seat_is_a_one_row_shoulder_36_in_with_the_paladin_cell_pitch():
    lua = boot(learn=(768, 783, 1066))
    st = standing(lua)
    assert 36 in st, f"no shoulder at 36: {st}"
    sb.approx(st[36][0], block_w(3), "block width")
    sb.approx(st[36][1], 49, "block height")
    host = g(lua).FSShapeshiftTab
    d = csh.D(lua, host)
    sb.approx(d["x"], 36, "host x")
    for i, btn in enumerate(buttons(lua)[:3]):
        db = csh.D(lua, btn)
        sb.approx(db["x"], 36 + 6 + i * 42.8, f"button {i + 1} x")
        sb.approx(db["w"], 38, f"button {i + 1} width")
        sb.approx(db["y"], -49 + 6, f"button {i + 1} top")


def check_the_block_grows_with_each_form_learned():
    lua = boot(learn=(768,))
    sb.approx(standing(lua)[36][0], block_w(1), "one form")
    run(lua, "__learn(783, 1066, 24858)")
    fire(lua, "SPELLS_CHANGED")
    sb.approx(standing(lua)[36][0], block_w(4), "four forms")
    assert shown(buttons(lua)[3]) and not shown(buttons(lua)[4])


def check_a_rescale_reseats_the_host_and_buttons():
    lua = boot(learn=(768, 783), scale=1.0)
    run(lua, "FS.Layout.Scale = function() return 0.8 end")
    run(lua, "for _, fn in ipairs(FS.Layout._rescale or {}) do fn() end")
    run(lua, "FS.ClassShoulder.Refresh(); FS.ShapeshiftTab.Sync()")
    assert buttons(lua)[0]._w == 38 * 0.8, f"button size {buttons(lua)[0]._w}"


def check_the_form_you_are_in_is_lit_and_none_out_of_form():
    lua = boot(learn=(5487, 768, 783), forms=[(5487, False), (768, False), (783, False)])
    b = buttons(lua)
    assert not any(x.fsLit for x in b[:3]), "a form is lit out of form"
    assert not any(shown(x.fsWash) for x in b[:3]), "a wash is shown out of form"
    run(lua, "__enter(768)")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert [bool(x.fsLit) for x in b[:3]] == [False, True, False], "cat is not the one lit"
    assert shown(b[1].fsWash) and not shown(b[0].fsWash), "the wash does not follow"
    ring = b[1].fsSkin.border.ring._vertex
    plain = b[0].fsSkin.border.ring._vertex
    assert ring[1] > plain[1], "the lit ring is not lifted toward white"
    run(lua, "__enter(0)")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not any(x.fsLit for x in b[:3]), "still lit after leaving the form"


def check_dire_bear_lights_the_bear_button():
    lua = boot(learn=(5487, 9634, 768), forms=[(9634, True), (768, False)])
    b = buttons(lua)
    assert b[0]._attrs["spell"] == "Dire Bear Form" and b[0].fsLit and not b[1].fsLit


def check_the_light_switch_off_draws_nothing_lit():
    lua = boot(learn=(5487, 768), forms=[(5487, True), (768, False)])
    assert buttons(lua)[0].fsLit, "not lit to begin with"
    run(lua, 'FS.Config.Set("tabs.druid.formsLit", false)')
    assert not any(x.fsLit for x in buttons(lua)), "lit with the light switch off"
    assert not any(shown(x.fsWash) for x in buttons(lua)), "a wash with the light switch off"
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not any(x.fsLit for x in buttons(lua)), "the form event relit it"


def check_an_unreadable_form_keeps_the_last_light_and_never_throws():
    lua = boot(learn=(5487, 768), forms=[(5487, True), (768, False)])
    run(lua, '__sfMode = "secret"')
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert buttons(lua)[0].fsLit, "an unreadable form cleared the light"
    run(lua, '__sfMode = "throw"')
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert buttons(lua)[0].fsLit, "a throwing form read cleared the light"
    run(lua, '__sfMode = nil; __enter(768)')
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not buttons(lua)[0].fsLit and buttons(lua)[1].fsLit, "the light did not recover"


def check_the_caster_button_is_off_by_default_and_a_cancelform_macro_when_on():
    lua = boot(learn=(768, 783), forms=[(768, False), (783, False)])
    b = buttons(lua)
    assert not shown(b[2]), "a caster button without its switch"
    assert tab(lua).SETTINGS.formsCaster.default is False
    run(lua, 'FS.Config.Set("tabs.druid.formsCaster", true)')
    assert shown(b[2]), "the caster button did not come"
    assert attrs(b[2]) == {"type": "macro", "macrotext": "/cancelform"}, f"caster attributes {attrs(b[2])}"
    assert b[2].fsLit and not b[0].fsLit, "out of form the caster button is the one lit"
    run(lua, "__enter(768)")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not b[2].fsLit and b[0].fsLit, "in a form the caster button is still lit"
    sb.approx(standing(lua)[36][0], block_w(3), "the caster button widens the block")
    run(lua, 'FS.Config.Set("tabs.druid.formsCaster", false)')
    assert not shown(b[2]) and attrs(b[2]) == {}, "the caster button stayed"
    sb.approx(standing(lua)[36][0], block_w(2), "the block did not narrow")


def check_a_caster_button_alone_is_never_shown():
    lua = boot(learn=())
    run(lua, 'FS.Config.Set("tabs.druid.formsCaster", true)')
    assert not shown(g(lua).FSShapeshiftTab) and 36 not in standing(lua), "a lone caster button stands"


def check_combat_touches_nothing_protected_and_the_update_waits_for_regen():
    lua = boot(learn=(768,), forms=[(768, False)])
    combat(lua, True)
    run(lua, "__learn(783, 1066)")
    fire(lua, "SPELLS_CHANGED")
    run(lua, 'FS.Config.Set("tabs.druid.formsCaster", true)')
    run(lua, "FS.ShapeshiftTab.Sync()")
    assert sb.blocked(lua) == 0, "a protected call was refused in combat"
    assert tab(lua).T.pendingSync, "nothing was parked"
    assert not shown(buttons(lua)[1]), "a button was shown in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).T.pendingSync, "regen did not replay the update"
    assert [x._attrs["spell"] for x in buttons(lua)[:3]] == ["Cat Form", "Travel Form", "Aquatic Form"]
    assert attrs(buttons(lua)[3]).get("macrotext") == "/cancelform", "the caster button is missing after regen"
    assert sb.blocked(lua) == 0


def check_the_light_follows_the_form_in_combat_without_a_protected_call():
    lua = boot(learn=(5487, 768), forms=[(5487, False), (768, False)])
    combat(lua, True)
    run(lua, "__enter(768)")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert buttons(lua)[1].fsLit and not buttons(lua)[0].fsLit, "the light did not follow in combat"
    assert sb.blocked(lua) == 0, "a protected call was refused"


def check_a_login_in_combat_builds_at_regen():
    lua = boot(learn=(768,), combat=True)
    assert g(lua).FSShapeshiftTab is None, "built in combat"
    combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert g(lua).FSShapeshiftTab is not None and shown(buttons(lua)[0]), "regen did not build the tab"
    assert sb.blocked(lua) == 0


def check_the_cooldown_swipe_follows_the_form_spell():
    lua = boot(learn=(768, 783))
    b = buttons(lua)
    assert sb.cd_of(b[0]) is None or sb.cd_of(b[0])[0] == "obj", "no duration object read"
    run(lua, "__cd[768] = { 1000, 1.5 }")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sb.cd_of(b[0]) == ("obj", 768), f"the swipe is {sb.cd_of(b[0])}"
    assert sb.cd_of(b[1]) is None or sb.cd_of(b[1]) != ("obj", 768), "the other button took it"
    run(lua, "__cd[768] = nil")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sb.cd_of(b[0]) is None, f"the swipe stayed: {sb.cd_of(b[0])}"


def check_the_tooltip_is_the_forms_spell_and_the_caster_buttons_own_text():
    lua = boot(learn=(768,), forms=[(768, False)])
    run(lua, 'FS.Config.Set("tabs.druid.formsCaster", true)')
    b = buttons(lua)
    run(lua, "FSShapeshiftButton1._scripts.OnEnter = nil")
    b[0]._hooks["OnEnter"][1](b[0])
    assert g(lua).GameTooltip._spellID == 768, "the tooltip is not the form spell"
    b[1]._hooks["OnEnter"][1](b[1])
    assert g(lua).GameTooltip._text == "Caster form", "the caster button has no text tooltip"


def check_unreadable_spellbook_answers_show_nothing_and_never_throw():
    lua = boot(learn=(768, 783))
    run(lua, '__knownMode = "secret"')
    fire(lua, "SPELLS_CHANGED")
    assert not tab(lua).OwnsShoulder(), "a secret spellbook answer counted as known"
    run(lua, '__knownMode = "throw"')
    fire(lua, "SPELLS_CHANGED")
    assert not tab(lua).OwnsShoulder(), "a throwing spellbook counted as known"
    run(lua, '__knownMode = nil; __infoMode = "secret"')
    fire(lua, "SPELLS_CHANGED")
    assert not tab(lua).OwnsShoulder(), "a secret name counted as a form"
    run(lua, '__infoMode = "throw"')
    fire(lua, "SPELLS_CHANGED")
    run(lua, '__infoMode = nil')
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).OwnsShoulder() and shown(buttons(lua)[0]), "did not recover"
    assert sb.blocked(lua) == 0


def check_a_throwing_entry_read_shows_nothing_and_says_so_once():
    lua = boot(learn=(768,))
    run(lua, "FS.ShapeshiftTab.def.entries = function() error('boom') end")
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "SPELLS_CHANGED")
    assert not tab(lua).OwnsShoulder(), "a failed read still owns the shoulder"
    assert int(g(lua).__degradeCount) == 1, f"the failed read was said {g(lua).__degradeCount} times"
    assert "ShapeshiftTab_entries" in g(lua).__degraded, "the line has no key of its own"


def check_a_clean_run_says_nothing():
    lua = boot(learn=DRUID_ALL, forms=[(768, True)])
    for event in ("UPDATE_SHAPESHIFT_FORM", "SPELL_UPDATE_COOLDOWN", "SPELLS_CHANGED", "PLAYER_ENTERING_WORLD"):
        fire(lua, event)
    assert int(g(lua).__degradeCount) == 0, dict(g(lua).__degraded)


def check_config_rows_are_the_prototypes_with_the_prototypes_tips():
    lua = boot(learn=(768,))
    secs = cfg_sections(lua)
    assert len(secs) == 1, f"{len(secs)} sections"
    sec = secs[0]
    assert (sec["page"], sec["tab"], sec["title"]) == ("tabs", "general", "Shapeshift tab"), sec
    assert sec["when"] == "DRUID", "the section is not tied to the Druid"
    assert sec["tip"] == ("New. Your forms as buttons on the action bars: Bear, Cat, Travel, Aquatic and Moonkin, learned "
                          "ones only. Click one to shift."), sec["tip"]
    rows = sec["rows"]
    assert [(r["key"], r["label"]) for r in rows] == [
        ("tabs.druid.forms", "Shapeshift tab"), ("tabs.druid.formsLit", "Light the form you are in"),
        ("tabs.druid.formsCaster", "Add a caster form button")], rows
    assert not rows[0]["sub"] and rows[1]["sub"] and rows[2]["sub"], "sub rows are wrong"
    assert rows[1]["needs"] == "tabs.druid.forms" and rows[2]["needs"] == "tabs.druid.forms"
    assert rows[2]["tip"] == "One more button that drops you back out of any form.", rows[2]["tip"]
    assert rows[0]["tip"] is None and rows[1]["tip"] is None


def check_config_defaults_are_on_on_on_off():
    lua = boot()
    get = g(lua).FS.Config.Get
    assert get("tabs.druid.forms") is True and get("tabs.druid.formsLit") is True
    assert get("tabs.druid.formsCaster") is False


def check_every_class_registers_its_rows_even_for_another_class():
    lua = boot(klass="WARRIOR")
    secs = cfg_sections(lua)
    assert [s["title"] for s in secs] == ["Shapeshift tab"], "a Warrior's window lost the Druid rows"


def check_no_config_window_means_no_rows_and_no_error():
    lua = boot(learn=(768,), config=False)
    assert tab(lua).OwnsShoulder(), "the tab needs the config window"


def check_the_kit_is_one_shared_table_and_the_toc_orders_the_files():
    lua = boot()
    k = kit(lua)
    assert k is not None and callable(k.New) and callable(k.Plain) and callable(k.Known), "kit missing"
    toc = TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/ShapeshiftTab.lua")
    assert toc.index("Modules/ActionBars/SealBar.lua") < i < toc.index("Modules/ActionBars/CallPetTab.lua"), "toc order"
    assert i < toc.index("Modules/Config/ConfigWindow.lua"), "the tab must load before the window"
    for name in ("CallPetTab", "PortalsTab", "ConjureTab", "PoisonsTab", "DemonTab"):
        assert i < toc.index(f"Modules/ActionBars/{name}.lua"), f"{name} loads before the kit"


def check_the_files_say_no_dashes_and_no_automation_words():
    text = KIT.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text, "an em or en dash"
    for word in ("macro bot", "autoclick", "automation"):
        assert word not in text.lower(), word


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
