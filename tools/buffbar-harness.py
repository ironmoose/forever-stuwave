#!/usr/bin/env python3
"""Runs the real ShamanBuffs.lua and BuffTab.lua (the Shaman buff tab: IMBUE and SHIELD tiles) headless, in
totembar-harness's world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua,
PetActionBar.lua, PetDock.lua, ClassShoulder.lua, TotemPiece.lua and TotemBar.lua.

The tab is a second Shaman shoulder on the Console's top edge (mockups/shaman-buff-tab-2026-10-12.html): 2 columns x
1 row (92.8 x 49 design px) at 316 design px, right of the totem tab. The numbers and colours below are read out of
the mockup, so a mockup move fails here. Checked:

  * the weapon tooltip parse (C_TooltipInfo.GetInventoryItem lines such as "Rockbiter 1 (56 min)"): minutes, seconds,
    hours, with and without a rank, localized strings, lines that are not an imbue, secret and unreadable answers;
  * the imbue model: both hands read, the least time shows, a weapon hand without an imbue asks for one (a shield or an
    empty off hand never does), the tooltip is NEVER read in combat, the clock counts down from the last read, a cast
    in combat starts a fresh hour on the right hand and a weapon swapped in combat is forgotten, not guessed;
  * the shield model: orbs from the aura snapshot, the expiring time, the combat estimate, Water Shield is not nagged,
    a Water Shield cast in combat clears the pending Lightning Shield cast, and a missing aura end is the application
    time plus the duration, not the last read plus ten minutes;
  * the tiles: states and colours from the mockup (quiet gold, pink expiring, amber hollow missing, hollow "?"), the
    locked dotted mold with its level, the absent imbue tile, the hover border and the tooltip lines;
  * the secure buttons: type "spell" with the spell name, written out of combat only and queued for regen, never a
    field or attribute Blizzard's secure click path reads, built once, bound through Bindings.xml;
  * the seat: shoulder block, host and buttons at the mockup's geometry, the Console gap and the bridge between the
    two shoulders, Console on and off, a rescale, a player who is not a Shaman gets nothing, and a failed build leaves
    no listener running;
  * visibility needs no target.

The mock is strict and is NOT the real client. BUFFTAB_LUA, SHAMANBUFFS_LUA, BINDINGS_XML and TOC_FILE point the
harness at mutant copies (a check must fail on a broken one).

    python3 tools/buffbar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
BUFFTAB = Path(os.environ.get("BUFFTAB_LUA", ADDON / "Modules/ActionBars/BuffTab.lua"))
SHAMANBUFFS = Path(os.environ.get("SHAMANBUFFS_LUA", ADDON / "Modules/ActionBars/ShamanBuffs.lua"))
BINDINGS = Path(os.environ.get("BINDINGS_XML", ADDON / "Bindings.xml"))
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))
MOCKUP = HERE.parent / "mockups" / "shaman-buff-tab-2026-10-12.html"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tbh = _load("totembar_harness", "totembar-harness.py")
csh = tbh.csh
sb = csh.sb
g = sb.g


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


approx = sb.approx
set_combat = sb.set_combat
blocked = sb.blocked
SCALES = csh.SCALES


# ---------------------------------------------------------------------------------------------
# The mockup's numbers
# ---------------------------------------------------------------------------------------------


def _hex(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def mockup() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    pal = sb._m(r"var C=\{(.*?)\};", src, "palette").group(1)
    colors = {k: _hex(v) for k, v in re.findall(r"(\w+):'(#[0-9a-fA-F]{6})'", pal)}
    geo = sb._m(r"var G=\{(.*?)\};", src, "geometry").group(1)
    num = {k: float(v) for k, v in re.findall(r"(\w+):([\d.]+)", geo)}
    chip = sb._m(r"function chip\(cx,cy,code,m\)\{(.*?)\n\}", src, "chip").group(1)
    warn_fill = float(sb._m(r"m==='warn'\)\{s=C\.amber;f=mix\(C\.bg,C\.amber,([\d.]+)\)", chip, "warn chip fill").group(1))
    exp_fill = float(sb._m(r"m==='exp'\)\{s=C\.pink;f=mix\(C\.bg,C\.pink,([\d.]+)\)", chip, "exp chip fill").group(1))
    on_fill = float(sb._m(r"else\{s=C\.gold;f=mix\(C\.bg,C\.gold,([\d.]+)\)", chip, "on chip fill").group(1))
    body = sb._m(r"function tileBody\(x,y,st\)\{(.*?)\n\}", src, "tileBody").group(1)
    alphas = {}
    for mode, a in re.findall(r"if\(m==='(exp|warn|hollow)'\)\{bc=C\.\w+;ba=([\d.]+);", body):
        alphas[mode] = float(a)
    alphas["on"] = float(sb._m(r"else\{bc=C\.violet;ba=([\d.]+);", body, "quiet border alpha").group(1))
    on_text = float(sb._m(r"op:m==='on'\?([\d.]+):1", body, "quiet text alpha").group(1))
    return dict(colors=colors, num=num, warn_fill=warn_fill, exp_fill=exp_fill, on_fill=on_fill, ring_alpha=alphas,
                on_text=on_text)


MK = mockup()
C = MK["colors"]
N = MK["num"]
BG = C["bg"]

# ---------------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------------

IMBUE_IDS = {"Rockbiter Weapon": 8017, "Flametongue Weapon": 8024, "Frostbrand Weapon": 8033, "Windfury Weapon": 8232}
SHIELD_ID, WATER_ID = 324, 24398
ALL_SPELLS = dict(IMBUE_IDS, **{"Lightning Shield": SHIELD_ID, "Water Shield": WATER_ID})
GUID = tbh.GUID

MOCKS = r"""
FS.Theme.COLOR_HEALTH = FS.Theme.COLOR_HEALTH or { 1, 0.18, 0.592, 1 }
FS.Theme.COLOR_POWER = FS.Theme.COLOR_POWER or { 0.133, 0.878, 1, 1 }
FS.Theme.COLOR_BORDER = FS.Theme.COLOR_BORDER or { 0.659, 0.333, 0.969, 1 }
FS.Theme.COLOR_AMBER = FS.Theme.COLOR_AMBER or { 1, 0.7137, 0.2824, 1 }
FS.Theme.COLOR_MUTED = FS.Theme.COLOR_MUTED or { 0.6157, 0.5765, 0.7686, 1 }
-- the host parents secure buttons, so it is restricted in combat like the Console root
do
    local create = CreateFrame
    function CreateFrame(kind, name, ...)
        if name and name == __failBuild then error("CreateFrame blew up for " .. name) end
        local f = create(kind, name, ...)
        if name == "FSBuffTab" then f._protected = true end
        return f
    end
end
__now = 10000
-- equipment: slot -> item id, item id -> equip location
__eq, __loc, __eqMode = {}, {}, nil
function GetInventoryItemID(unit, slot)
    if __eqMode == "throw" then error("GetInventoryItemID blew up") end
    if __eqMode == "secret" then return __SECRET end
    return __eq[slot]
end
C_Item = C_Item or {}
C_Item.GetItemInfoInstant = function(id) return id, "Weapon", "Sword", __loc[id], 1 end
function __weapon(slot, loc)
    __nextItem = (__nextItem or 500) + 1
    __eq[slot] = __nextItem
    __loc[__nextItem] = loc or "INVTYPE_WEAPON"
end
-- the weapon tooltip: slot -> list of left texts ("<secret>" is a secret one)
__tip, __tipMode, __tipCalls = {}, nil, {}
C_TooltipInfo = {
    GetInventoryItem = function(unit, slot)
        __tipCalls[#__tipCalls + 1] = { slot = slot, combat = __combat and true or false }
        if __tipMode == "throw" then error("GetInventoryItem blew up") end
        if __tipMode == "secret" then return __SECRET end
        if __tipMode == "nolines" then return {} end
        local lines = __tip[slot]
        if not lines then return nil end
        local out = {}
        for i, text in ipairs(lines) do out[i] = { leftText = (text == "<secret>") and __SECRET or text, type = 0 } end
        return { lines = out }
    end,
}
-- GetWeaponEnchantInfo answers false/nil on this client; a case may make it answer true
__gwei = { false, 0, 0, 0, false, 0, 0, 0 }
function GetWeaponEnchantInfo() return unpack(__gwei) end
-- the player aura snapshot (frozen in combat)
__snap = { buffs = {} }
FS.PlayerAuras = { Get = function() return __snap end, IsFrozen = function() return __combat and true or false end }
function __shield(count, remaining, duration)
    __snap = { buffs = { { name = "Lightning Shield", count = count, spellId = 324,
        expirationTime = remaining and (__now + remaining) or 0, duration = duration or 600 } } }
end
function __water() __snap = { buffs = { { name = "Water Shield", count = 3, spellId = 24398, expirationTime = __now + 600 } } } end
function __noshield() __snap = { buffs = { { name = "Mark of the Wild", count = 0, expirationTime = 0 } } } end
function __castOk(id) __fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
function __tickAll(dt)
    __advance(dt)
    local list = {}
    for _, f in ipairs(__frames) do if f._scripts.OnUpdate then list[#list + 1] = f end end
    for _, f in ipairs(list) do f._scripts.OnUpdate(f, dt) end
end
"""


def boot(scale: float = 1.0, *, klass: str = "SHAMAN", spells=("Rockbiter Weapon", "Lightning Shield"),
         weapons=None, tips=None, combat: bool = False, console: bool = True, pre_login: str = ""):
    """A Shaman world. `spells`: spell names the spellbook knows; `weapons`: {slot: equip location}; `tips`: {slot:
    [tooltip lines]}."""
    mocks = tbh.MOCKS % dict(guid=GUID, bar=tbh.BAR, all="{}") + "\n" + MOCKS
    setup = []
    for name, sid in ALL_SPELLS.items():
        setup.append(f'__spell("{name}", {sid}, {"true" if name in spells else "false"})')
    for slot, loc in (weapons or {}).items():
        setup.append(f'__weapon({slot}, "{loc}")')
    for slot, lines in (tips or {}).items():
        items = ",".join('"%s"' % x for x in lines)
        setup.append(f"__tip[{slot}] = {{{items}}}")
    return sb.boot(scale, klass=klass, known=[], combat=combat, console=console,
                   extra_lua=csh.PATCH + mocks + "\n" + "\n".join(setup),
                   extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, tbh.TOTEMPIECE, tbh.TOTEMBAR, SHAMANBUFFS, BUFFTAB),
                   pre_login=csh.SPIES + pre_login)


def btn(lua, i):
    return g(lua)[f"FSBuffTabButton{i}"]


IMBUE, SHIELD = 1, 2


def attr(b, name):
    return b._attrs[name]


def shown(b) -> bool:
    return bool(b._shown)


def bt(lua):
    return g(lua).FS.BuffTab


def sbuf(lua):
    return g(lua).FS.ShamanBuffs


def view(lua, key):
    return sbuf(lua).View()[key]


def update(lua):
    """One tick of the tab: the data refreshed and the tiles repainted."""
    sbuf(lua).Update()
    bt(lua).Paint()


def tick(lua, dt):
    lua.eval("__tickAll")(dt)


def run(lua, code):
    lua.execute(code)


def tip(lua, slot, lines):
    items = "nil" if lines is None else "{" + ",".join('"%s"' % x for x in lines) + "}"
    run(lua, f"__tip[{slot}] = {items}")


def cast(lua, name):
    run(lua, f"__castOk({ALL_SPELLS[name]})")


def leave_combat(lua):
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")


def rgb(v):
    return tuple(float(v[i]) for i in (1, 2, 3))


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def tip_calls(lua):
    t = g(lua).__tipCalls
    return [(int(t[i].slot), bool(t[i].combat)) for i in range(1, len(t) + 1)]


def tile(lua, i):
    """What a tile shows: chip code, text, chip stroke / fill colours and alpha, border, underline."""
    b = btn(lua, i)
    return dict(
        code=b.fsChip.code._text, text=b.fsText._text, chip=rgb(b.fsChip.ring._vertex),
        fill=rgb(b.fsChip.fill._vertex), fill_a=float(b.fsChip.fill._vertex[4]),
        ring=rgb(b.fsSkin.border.ring._vertex), ring_a=float(b.fsSkin.border.ring._vertex[4]),
        text_color=rgb(b.fsText._textColor), text_a=float(b.fsText._textColor[4]),
        code_color=rgb(b.fsChip.code._textColor), line=rgb(b.fsLine._vertex), line_a=float(b.fsLine._vertex[4]),
        dashes=[float(d._alpha) for d in [b.fsDashes[k] for k in range(1, 5)]],
    )


def tip_text(lua, i):
    b = btn(lua, i)
    run(lua, "GameTooltip._lines = {}")
    lua.eval("__Region.Fire")(b, "OnEnter")
    return [str(x) for x in csh.seq(g(lua).GameTooltip._lines)]


MIN = 60


def one_hand(lua, line="Rockbiter 1 (56 min)"):
    """Boot-after helper: a main hand weapon carrying `line`, read."""
    tip(lua, 16, [line])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)


def world(scale: float = 1.0, **kw):
    """A Shaman with a main hand weapon (and what `tips` says is on it), after the first sync."""
    kw.setdefault("weapons", {16: "INVTYPE_WEAPON"})
    return boot(scale, **kw)


# ---------------------------------------------------------------------------------------------
# Checks: the tooltip parse
# ---------------------------------------------------------------------------------------------


def parse(lua, text):
    r = sbuf(lua).ParseImbueLine(text)
    if r is None:
        return None
    code, secs, unit = r
    return str(code), float(secs), float(unit)


def check_parse_reads_minutes_seconds_hours_with_and_without_a_rank():
    lua = boot()
    cases = {
        "Rockbiter 1 (56 min)": ("RB", 56 * 60, 60),
        "Rockbiter 7 (1 min)": ("RB", 60, 60),
        "Flametongue 3 (59 min)": ("FT", 59 * 60, 60),
        "Frostbrand 2 (30 sec)": ("FB", 30, 1),
        "Windfury 1 (1 hour)": ("WF", 3600, 3600),
        "Windfury Weapon (5 min)": ("WF", 300, 60),
        "Rockbiter (12 min)": ("RB", 720, 60),
        "Flametongue IV (12 min)": ("FT", 720, 60),
        "|cff1eff00Frostbrand 1|r (45 min)": ("FB", 2700, 60),
    }
    for text, want in cases.items():
        assert parse(lua, text) == want, f"{text!r} parsed as {parse(lua, text)}, want {want}"


def check_parse_ignores_lines_that_are_not_an_imbue_with_a_time():
    lua = boot()
    for text in ("Crusader (56 min)", "Rockbiter 1", "Rockbiter 1 (56 min) extra", "Durability 100 / 100", "",
                 "Flametongue Totem (5 min)", "Requires Level 10", "(56 min)", "Rockbiter 1 (soon)"):
        assert parse(lua, text) is None, f"{text!r} parsed as {parse(lua, text)}"
    for bad in ("nil", "42", "{}", "__SECRET"):
        assert lua.eval(f"FS.ShamanBuffs.ParseImbueLine({bad})") is None, f"{bad} parsed"


def check_parse_follows_the_clients_own_enchant_time_strings_and_spell_names():
    # a localized client: the spell names and Blizzard's time strings come from the client, not from this file
    lua = boot(pre_login=r"""
        ITEM_ENCHANT_TIME_LEFT_MIN = "%s (%d |4Minute:Min;)"
        ITEM_ENCHANT_TIME_LEFT_SEC = "%s [%d s]"
        __idNames[8017] = "Armeroc Arme"
        __spells["Armeroc Arme"] = 8017
    """)
    assert parse(lua, "Armeroc 2 (40 Min)") == ("RB", 2400, 60), parse(lua, "Armeroc 2 (40 Min)")
    assert parse(lua, "Armeroc Arme [20 s]") == ("RB", 20, 1), parse(lua, "Armeroc Arme [20 s]")
    # the English short names keep working next to the localized ones
    assert parse(lua, "Flametongue 1 (3 Min)") == ("FT", 180, 60)
    # a client with none of the Blizzard strings falls back to the English ones
    lua = boot(pre_login="ITEM_ENCHANT_TIME_LEFT_MIN = nil; ITEM_ENCHANT_TIME_LEFT_SEC = 12")
    assert parse(lua, "Rockbiter 1 (56 min)") == ("RB", 3360, 60)
    assert parse(lua, "Rockbiter 1 (9 sec)") == ("RB", 9, 1)


def check_the_imbue_names_come_from_the_spell_ids_not_from_english_text():
    lua = boot(pre_login='__idNames[8024] = "Zungenflamme Waffe"; __spells["Zungenflamme Waffe"] = 8024')
    assert parse(lua, "Zungenflamme 1 (10 min)") == ("FT", 600, 60)


def read_tip(lua, slot):
    r = sbuf(lua).ReadTooltip(slot)
    return r if isinstance(r, str) else r


def check_tooltip_reads_say_imbue_none_or_unreadable():
    lua = world(tips={16: ["Heavy Axe", "Rockbiter 1 (56 min)", "Durability 90 / 100"]})
    r = sbuf(lua).ReadTooltip(16)
    assert tuple(r)[:1] == ("imbue",), r
    tip(lua, 16, ["Heavy Axe", "Durability 90 / 100"])
    assert str(sbuf(lua).ReadTooltip(16)) == "none"
    tip(lua, 16, ["Heavy Axe", "<secret>", "Durability 90 / 100"])
    assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", "a secret line could hide the imbue"
    tip(lua, 16, ["Rockbiter 1 (56 min)", "<secret>"])
    assert str(sbuf(lua).ReadTooltip(16)[0]) == "imbue", "a plain imbue line wins over a secret one"
    for mode in ("throw", "secret", "nolines"):
        run(lua, f'__tipMode = "{mode}"')
        assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", mode
    run(lua, "__tipMode = nil; C_TooltipInfo = nil")
    assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", "no tooltip API"


# ---------------------------------------------------------------------------------------------
# Checks: the imbue model
# ---------------------------------------------------------------------------------------------


def check_the_main_hand_imbue_shows_its_code_and_time_in_the_quiet_look():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "RB", "56m"), (v.mode, v.code, v.text)
    t = tile(lua, IMBUE)
    assert (t["code"], t["text"]) == ("RB", "56m")
    close(t["chip"], C["gold"], "quiet chip stroke")
    close(t["fill"], _mix(BG, C["gold"], MK["on_fill"]), "quiet chip fill")
    close(t["ring"], C["violet"], "quiet border")
    approx(t["ring_a"], MK["ring_alpha"]["on"], "quiet border alpha")
    close(t["code_color"], C["white"], "quiet code", 0.06)
    close(t["text_color"], C["fg"], "quiet text")
    approx(t["text_a"], MK["on_text"], "quiet text alpha")
    close(t["line"], C["gold"], "quiet underline")
    assert t["dashes"] == [0.0] * 4, "the dashes are the shield estimate's only"
    for code, name in (("FT", "Flametongue"), ("FB", "Frostbrand"), ("WF", "Windfury")):
        tip(lua, 16, [f"{name} 1 (59 min)"])
        fire(lua, "UNIT_INVENTORY_CHANGED", "player")
        update(lua)
        assert tile(lua, IMBUE)["code"] == code, name


def check_under_five_minutes_the_tile_turns_pink_and_under_one_minute_counts_seconds():
    lua = world(tips={16: ["Rockbiter 1 (5 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("exp", "5m"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    close(t["chip"], C["pink"], "expiring chip")
    close(t["fill"], _mix(BG, C["pink"], MK["exp_fill"]), "expiring chip fill")
    close(t["ring"], C["pink"], "expiring border"), approx(t["ring_a"], MK["ring_alpha"]["exp"], "expiring border alpha")
    close(t["text_color"], C["pink"], "expiring text"), approx(t["text_a"], 1.0, "expiring text alpha")
    close(t["line"], C["pink"], "expiring underline")
    tip(lua, 16, ["Rockbiter 1 (6 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "on", "six minutes is still quiet"
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert (view(lua, "imbue").mode, tile(lua, IMBUE)["text"]) == ("exp", "42s")


def check_a_missing_imbue_is_an_amber_hollow_word_and_an_unreadable_one_a_hollow_question_mark():
    lua = world(tips={16: ["Heavy Axe"]})
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("warn", "IMBUE"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    close(t["chip"], C["amber"], "missing chip"), close(t["fill"], _mix(BG, C["amber"], MK["warn_fill"]), "missing fill")
    close(t["ring"], C["amber"], "missing border"), approx(t["ring_a"], MK["ring_alpha"]["warn"], "missing alpha")
    close(t["text_color"], C["amber"], "missing word"), close(t["code_color"], C["amber"], "missing code")
    assert t["text"] == "IMBUE"
    # nothing to go on: no tooltip data at all
    lua = world(pre_login='__tipMode = "throw"')
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("hollow", "?"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    close(t["ring"], C["muted"], "hollow border"), approx(t["ring_a"], MK["ring_alpha"]["hollow"], "hollow alpha")
    close(t["text_color"], C["muted"], "hollow ?"), assert_eq(t["text"], "?")
    close(t["line"], C["muted"], "hollow underline")
    # no weapon at all: nothing to imbue, so no nagging
    lua = boot(weapons={})
    assert view(lua, "imbue").mode == "hollow", view(lua, "imbue").mode


def assert_eq(a, b, what=""):
    assert a == b, f"{what} {a!r} != {b!r}"


def check_dual_wield_shows_the_least_time_and_asks_for_the_missing_hand():
    lua = boot(weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"},
               tips={16: ["Windfury 1 (50 min)"], 17: ["Flametongue 1 (20 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text, v.hand) == ("on", "FT", "20m", "off"), (v.mode, v.code, v.text, v.hand)
    tip(lua, 17, ["Light Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    v = view(lua, "imbue")
    assert (v.mode, v.text, v.lackHand) == ("warn", "IMBUE", "off"), (v.mode, v.text, v.lackHand)
    tip(lua, 16, ["Heavy Axe"])
    tip(lua, 17, ["Windfury 1 (9 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert (view(lua, "imbue").mode, view(lua, "imbue").lackHand) == ("warn", "main")


def check_a_shield_or_an_empty_off_hand_never_asks_for_an_imbue():
    for off in ({}, {17: "INVTYPE_SHIELD"}, {17: "INVTYPE_HOLDABLE"}):
        lua = boot(weapons={**{16: "INVTYPE_2HWEAPON" if not off else "INVTYPE_WEAPON"}, **off},
                   tips={16: ["Rockbiter 1 (30 min)"], 17: ["Block 12", "Rockbiter 1 (30 min)"]})
        v = view(lua, "imbue")
        assert (v.mode, v.text) == ("on", "30m"), f"{off}: {v.mode} {v.text}"
    lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    run(lua, "__loc[__eq[16]] = nil")        # an item the client cannot class: nothing to say about that hand
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode != "warn"


def check_a_two_handed_weapon_without_an_imbue_asks_for_one():
    lua = boot(weapons={16: "INVTYPE_2HWEAPON"}, tips={16: ["Great Maul"]})
    assert view(lua, "imbue").mode == "warn"


def check_the_tooltip_is_never_read_in_combat_and_the_clock_counts_down_from_the_last_read():
    lua = world(tips={16: ["Rockbiter 1 (10 min)"]})
    before = len(tip_calls(lua))
    assert view(lua, "imbue").text == "10m"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    for event in ("UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED", "SPELLS_CHANGED"):
        fire(lua, event, "player")
    tick(lua, 30)
    tick(lua, 30)
    tick(lua, 400)
    assert all(not c for _, c in tip_calls(lua)), f"the tooltip was read in combat: {tip_calls(lua)}"
    assert len(tip_calls(lua)) == before, "no read at all happened in combat"
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("exp", "2m"), (v.mode, v.text)         # 10 min less 460 s is 2m 20s
    tick(lua, 60)
    assert view(lua, "imbue").text == "1m", view(lua, "imbue").text
    tick(lua, 30)
    assert view(lua, "imbue").text == "50s", view(lua, "imbue").text
    tick(lua, 60)
    assert view(lua, "imbue").mode == "warn", "an imbue that ran out in combat asks for another"


def check_the_slow_tick_reads_out_of_combat_and_a_read_does_not_stair_step_the_clock():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    reads = len(tip_calls(lua))
    tick(lua, 1)
    assert len(tip_calls(lua)) == reads, "the slow tick is not every second"
    tick(lua, 6)
    assert len(tip_calls(lua)) > reads, "the slow tick reads the weapon out of combat"
    # one minute later the tooltip says 55: the clock stays continuous
    tick(lua, 54)
    tip(lua, 16, ["Rockbiter 1 (55 min)"])
    tick(lua, 6)
    r = float(view(lua, "imbue").remaining)
    assert 3300 - 5 <= r <= 3360 + 1, f"remaining {r} jumped"
    # a real change (the tooltip says 40) is taken at once
    tip(lua, 16, ["Rockbiter 1 (40 min)"])
    tick(lua, 6)
    approx(float(view(lua, "imbue").remaining), 2400, "a real change is taken", 1.0)


def check_a_cast_starts_a_fresh_hour_and_the_next_read_takes_over():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    assert view(lua, "imbue").mode == "warn"
    cast(lua, "Flametongue Weapon")
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FT", "60m"), (v.mode, v.code, v.text)
    tip(lua, 16, ["Flametongue 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert (view(lua, "imbue").code, view(lua, "imbue").text) == ("FT", "59m")


def check_a_cast_in_combat_counts_a_fresh_hour_and_a_weapon_swapped_in_combat_is_forgotten():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Rockbiter 1 (3 min)"]})
    set_combat(lua, True)
    cast(lua, "Flametongue Weapon")
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FT", "60m"), (v.mode, v.code, v.text)
    assert all(not c for _, c in tip_calls(lua))
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16, True)
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("hollow", "?"), "a weapon swapped in combat shows nothing rather than a stale time"
    tip(lua, 16, ["Frostbrand 1 (25 min)"])
    leave_combat(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FB", "25m"), (v.mode, v.code, v.text)


def check_two_imbue_casts_back_to_back_each_go_to_their_own_hand():
    # the old chip taught one enchant id from two casts; the model now has no ids to teach (old finding 1)
    lua = boot(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
               weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"}, tips={16: ["Heavy"], 17: ["Light"]})
    set_combat(lua, True)
    cast(lua, "Rockbiter Weapon")
    cast(lua, "Flametongue Weapon")
    v = view(lua, "imbue")
    assert v.mode == "on" and v.text == "60m", (v.mode, v.text)
    set_combat(lua, False)
    tip(lua, 16, ["Rockbiter 1 (59 min)"])
    tip(lua, 17, ["Flametongue 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "on"


def check_a_recast_on_the_other_hand_does_not_hide_the_sooner_expiring_one():
    # old finding 2: the same imbue cast again showed 60m for up to ten seconds, hiding the 5m hand
    lua = boot(weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"},
               tips={16: ["Rockbiter 1 (5 min)"], 17: ["Heavy"]})
    assert view(lua, "imbue").mode == "warn"
    cast(lua, "Rockbiter Weapon")           # lands on the off hand (the one without)
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.hand, v.text) == ("exp", "main", "5m"), (v.mode, v.hand, v.text)
    # both imbued: a recast replaces the main hand
    tip(lua, 17, ["Rockbiter 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    cast(lua, "Rockbiter Weapon")
    update(lua)
    assert view(lua, "imbue").hand == "off" and view(lua, "imbue").text == "59m"


def check_a_pending_cast_outlasts_an_early_none_read_only_for_the_grace():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    cast(lua, "Rockbiter Weapon")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")          # the weapon has not caught up yet
    assert view(lua, "imbue").mode == "on"
    tick(lua, 3)                                            # the scheduled reads ran: it never caught up
    assert view(lua, "imbue").mode == "warn", view(lua, "imbue").mode


def check_get_weapon_enchant_info_counts_only_when_it_answers_true():
    lua = world(tips={16: ["Heavy Axe"]})
    assert view(lua, "imbue").mode == "warn"
    run(lua, f"__gwei = {{ true, 1800000, 0, 0, false, 0, 0, 0 }}")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("on", "30m"), (v.mode, v.text)
    # secret or false answers add nothing
    lua = world(tips={16: ["Heavy Axe"]})
    run(lua, "__gwei = { __SECRET, __SECRET, 0, 0, __SECRET, __SECRET, 0, 0 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "warn"


def check_no_imbue_known_means_no_tile_and_learning_one_brings_it():
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Heavy Axe"]})
    b = btn(lua, IMBUE)
    assert not shown(b), "the imbue tile is absent while no imbue is known"
    assert attr(b, "spell") is None and attr(b, "type") is None
    run(lua, '__learn("Rockbiter Weapon")')
    run(lua, '__spell("Rockbiter Weapon", 8017, true)')
    fire(lua, "SPELLS_CHANGED")
    assert shown(b) and attr(b, "spell") == "Rockbiter Weapon" and not b.fsLocked
    # an imbue on the weapon from another source is shown even with none known
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Windfury 1 (30 min)"]})
    assert view(lua, "imbue").mode == "on"


# ---------------------------------------------------------------------------------------------
# Checks: the shield model
# ---------------------------------------------------------------------------------------------


def check_the_shield_shows_ls_and_its_orbs_then_its_time_when_expiring():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    t = tile(lua, SHIELD)
    assert (t["code"], t["text"]) == ("LS", "3"), t
    close(t["chip"], C["gold"], "shield chip")
    run(lua, "__shield(1, 480)")
    fire(lua, "UNIT_AURA", "player")
    assert (tile(lua, SHIELD)["text"]) == "1" or view(lua, "shield").text == "1"
    run(lua, "__shield(2, 240)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("exp", "4m"), (v.mode, v.text)
    close(tile(lua, SHIELD)["chip"], C["pink"], "expiring shield chip")
    run(lua, "__shield(2, 38)")
    fire(lua, "UNIT_AURA", "player")
    assert view(lua, "shield").text == "38s"


def check_a_missing_shield_is_amber_and_no_snapshot_yet_is_a_hollow_question_mark():
    lua = world()
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("warn", "SHIELD"), (v.mode, v.text)
    t = tile(lua, SHIELD)
    close(t["chip"], C["amber"], "missing shield chip"), close(t["text_color"], C["amber"], "missing word")
    lua = world(pre_login="FS.PlayerAuras = nil")
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("hollow", "?"), (v.mode, v.text)
    # the 9 px word: SHIELD is longer than IMBUE
    assert btn(lua, SHIELD).fsTextPx in (9, 11)
    run(lua, "FS.PlayerAuras = { Get = function() return __snap end, IsFrozen = function() return false end }; __noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsTextPx == 9, "the word SHIELD is set small to fit the tile"


def check_in_combat_the_shield_is_an_estimate_with_a_tilde_and_dashes():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text, bool(v.estimate)) == ("on", "~3", True), (v.mode, v.text, v.estimate)
    assert tile(lua, SHIELD)["dashes"] == [1.0] * 4, "the estimate underline is dashed"
    assert any("cannot be read in combat" in x for x in tip_text(lua, SHIELD))
    leave_combat(lua)
    tick(lua, 1)
    assert tile(lua, SHIELD)["dashes"] == [0.0] * 4 and view(lua, "shield").text == "3"


def check_a_shield_cast_in_combat_shows_three_orbs_and_a_pending_cast_expires_with_the_clock():
    lua = world()
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    cast(lua, "Lightning Shield")
    update(lua)
    assert (view(lua, "shield").mode, view(lua, "shield").text) == ("on", "~3")
    tick(lua, 601)
    assert view(lua, "shield").mode == "warn", "after its ten minutes with nothing to confirm it, the shield is asked for"


def check_water_shield_is_never_nagged_and_a_water_shield_cast_in_combat_clears_the_lightning_cast():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"))
    run(lua, "__water()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text, bool(v.other)) == ("hollow", "WS", True), (v.mode, v.text, v.other)
    assert any("Water Shield is active" in x for x in tip_text(lua, SHIELD))
    # old finding 3: a Water Shield cast in combat must clear the pending cast and not nag
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"))
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    cast(lua, "Lightning Shield")
    cast(lua, "Water Shield")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, bool(v.other)) == ("hollow", True), (v.mode, v.other)
    tick(lua, 5)
    assert view(lua, "shield").mode == "hollow", "the stale Lightning Shield cast no longer makes the shield 'up'"
    # and a Lightning Shield cast over a Water Shield takes the quiet state back
    cast(lua, "Lightning Shield")
    update(lua)
    assert view(lua, "shield").mode == "on"


def check_a_shield_with_no_aura_end_ends_at_its_application_not_at_the_last_read():
    # old finding 4: the fallback was the last live read plus ten minutes, which outlives a shield read mid life
    lua = world()
    run(lua, "__shield(3, nil)")                  # expirationTime 0: the aura told no end
    fire(lua, "UNIT_AURA", "player")
    start = float(g(lua).__now)
    tick(lua, 400)
    run(lua, "__shield(2, nil)")                  # a charge went: a later live read, same application
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    assert view(lua, "shield").mode in ("on", "exp")
    tick(lua, 150)                                # 550 s since the application, 150 s since the last read
    assert view(lua, "shield").mode in ("on", "exp"), view(lua, "shield").mode
    tick(lua, 60)                                 # 610 s since the application: gone, though the last read was 210 s ago
    assert view(lua, "shield").mode == "warn", f"started {start}, now {g(lua).__now}: {view(lua, 'shield').mode}"
    # the aura's own end wins when it has one
    lua = world()
    run(lua, "__shield(3, 100)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    tick(lua, 50)
    assert view(lua, "shield").mode == "exp"
    tick(lua, 60)
    assert view(lua, "shield").mode == "warn"


def check_lightning_shield_is_a_locked_dotted_mold_until_it_is_known():
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    b = btn(lua, SHIELD)
    assert shown(b), "a locked tile is dimmed by alpha, never hidden"
    assert b.fsLocked and abs(float(b._alpha) - 0.4) < 1e-6, f"alpha {b._alpha}"
    assert view(lua, "shield").mode == "locked"
    assert attr(b, "type") is None and attr(b, "spell") is None, "a locked tile carries nothing castable"
    assert shown(b.fsMold) and shown(b.fsLockText) and b.fsLockText._text == "L8", b.fsLockText._text
    assert not shown(b.fsFace), "the face is hidden while locked"
    assert "Opens at level 8." in tip_text(lua, SHIELD)
    # learned: the mold goes, the tile is live
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    assert not b.fsLocked and abs(float(b._alpha) - 1.0) < 1e-6
    assert shown(b.fsFace) and not shown(b.fsMold) and not shown(b.fsLockText)
    assert attr(b, "type") == "spell" and attr(b, "spell") == "Lightning Shield"
    # the imbue tile never locks
    assert not btn(lua, IMBUE).fsLocked and btn(lua, IMBUE).fsDef.unlock is None
    # the level on the mold is the spell's, the mockup's
    assert int(btn(lua, SHIELD).fsDef.unlock) == 8
    assert "L8" in MOCKUP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Checks: secure buttons
# ---------------------------------------------------------------------------------------------


def check_two_named_secure_buttons_in_the_fixed_order_built_once():
    lua = world(tips={16: ["Rockbiter 1 (30 min)"]})
    for i, key in ((1, "imbue"), (2, "shield")):
        b = btn(lua, i)
        assert b is not None and b._secure, f"FSBuffTabButton{i} is not a secure template button"
        assert b.fsKey == key, f"button {i} is {b.fsKey!r}"
        assert [b._clicks[k] for k in range(1, len(b._clicks) + 1)] == ["AnyUp", "AnyDown"]
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "UPDATE_BINDINGS"):
        fire(lua, event)
    frames = [f for f in g(lua).__frames.values() if f._name and re.match(r"FSBuffTabButton\d$", f._name)]
    assert len(frames) == 2, f"{len(frames)} named buff buttons, expected exactly 2"


def check_click_attributes_are_a_spell_by_name_and_follow_the_imbue_shown():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Flametongue 1 (30 min)"]})
    imb, shd = btn(lua, IMBUE), btn(lua, SHIELD)
    assert (attr(imb, "type"), attr(imb, "spell")) == ("spell", "Flametongue Weapon"), "casts the imbue its chip shows"
    assert (attr(shd, "type"), attr(shd, "spell")) == ("spell", "Lightning Shield")
    assert sorted(str(k) for k in imb._attrs.keys() if imb._attrs[k] is not None) == ["spell", "type"], \
        "nothing but type and spell"
    # none up: the imbue the tile still shows (the last one seen), else the best known
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert attr(imb, "spell") == "Flametongue Weapon", attr(imb, "spell")
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    assert attr(btn(lua, IMBUE), "spell") == "Flametongue Weapon", "the best known imbue when none was ever up"
    lua = world(tips={16: ["Heavy Axe"]})
    assert attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon"


def check_attributes_are_written_out_of_combat_only_and_queued_for_regen():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    imb = btn(lua, IMBUE)
    assert attr(imb, "spell") == "Rockbiter Weapon"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    cast(lua, "Flametongue Weapon")          # the chip now reads FT
    fire(lua, "UNIT_AURA", "player")
    tip(lua, 16, ["Flametongue 1 (59 min)"])
    tick(lua, 3)
    assert view(lua, "imbue").code == "FT"
    assert attr(imb, "spell") == "Rockbiter Weapon", "an attribute changed in combat"
    assert blocked(lua) == 0, f"{blocked(lua)} protected writes were attempted in combat"
    assert tile(lua, IMBUE)["code"] == "FT", "the paint follows in combat (texture and font writes)"
    leave_combat(lua)
    assert attr(imb, "spell") == "Flametongue Weapon", "regen aims the click at the imbue shown"
    assert blocked(lua) == 0


def check_nothing_protected_is_touched_in_combat_by_events_ticks_and_paint():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield", "Water Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    set_combat(lua, True)
    for event, args in (("UNIT_AURA", ("player",)), ("UNIT_INVENTORY_CHANGED", ("player",)),
                        ("PLAYER_EQUIPMENT_CHANGED", (16, True)), ("SPELLS_CHANGED", ()), ("UPDATE_BINDINGS", ()),
                        ("PLAYER_LEVEL_UP", (20,)), ("PLAYER_ENTERING_WORLD", ())):
        fire(lua, event, *args)
    cast(lua, "Flametongue Weapon")
    cast(lua, "Water Shield")
    tick(lua, 5)
    for i in (IMBUE, SHIELD):
        lua.eval("__Region.Fire")(btn(lua, i), "OnEnter")
        lua.eval("__Region.Fire")(btn(lua, i), "OnLeave")
    assert blocked(lua) == 0, f"{blocked(lua)} protected writes in combat"
    assert int(g(lua).__protectedTouch) == 0, "a frame under the protected host was created or moved in combat"


def check_no_forbidden_field_or_attribute_is_ever_written_on_a_secure_button():
    # Blizzard's secure click path reads .bar, .isExtra, .buttonType, CalculateAction and the useparent-* attributes
    # off the button; an addon written value there taints the click (a real bug fixed in ActionBars.lua, 2026-10-12)
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    forbidden = ("bar", "isExtra", "buttonType", "CalculateAction", "action", "actionButton", "useparent",
                 "UpdateAction", "GetActionId", "GetAction", "HasAction", "SetActionUI")
    for _ in range(2):
        for i in (IMBUE, SHIELD):
            b = btn(lua, i)
            for name in forbidden:
                assert lua.eval("rawget")(b, name) is None, f"button {i} carries a .{name} field"
            for name, value in b._attrs.items():
                assert not str(name).startswith("useparent"), f"button {i} carries {name}"
                assert str(name) in ("type", "spell"), f"button {i} carries the attribute {name}"
        cast(lua, "Flametongue Weapon")
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "PLAYER_ENTERING_WORLD")
    text = BUFFTAB.read_text(encoding="utf-8")
    for name in ("bar", "isExtra", "buttonType", "CalculateAction"):
        assert not re.search(rf"(button|self|b)\.{name}\s*=", text), f"BuffTab.lua writes a .{name} field"
    assert "useparent" not in text, "BuffTab.lua mentions a useparent attribute"


def check_the_files_use_no_snippets_and_no_state_drivers():
    for path in (BUFFTAB, SHAMANBUFFS):
        text = path.read_text(encoding="utf-8")
        for token in ("SecureHandler", "RegisterStateDriver", "RegisterAttributeDriver", "_onstate", "WrapScript",
                      "SetFrameRef", "loadstring", "Execute("):
            assert token not in text, f"{path.name} uses {token}"


# ---------------------------------------------------------------------------------------------
# Checks: tooltip, hover, keybinds
# ---------------------------------------------------------------------------------------------


def check_tooltip_lines_follow_the_mockups_wording():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (59 min)"]})
    text = tip_text(lua, IMBUE)
    assert text == ["Rockbiter Weapon", "Main hand imbue, 59 min left.", "Click: cast Rockbiter Weapon."], text
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE)[1] == "Main hand imbue, 42 sec left."
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE) == ["Weapon imbue", "No imbue on your main hand.", "Click: cast Rockbiter Weapon."], \
        tip_text(lua, IMBUE)
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    assert tip_text(lua, SHIELD) == ["Lightning Shield", "3 charges, 8 min left.", "Click: cast Lightning Shield."], \
        tip_text(lua, SHIELD)
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    assert tip_text(lua, SHIELD) == ["Lightning Shield", "Not active.", "Click: cast Lightning Shield."]
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    assert tip_text(lua, SHIELD)[1] == "Charges cannot be read in combat. About 3 left."
    # titles take the tile colour
    lines = bt(lua).TipLines("imbue")
    assert str(lines[1][1]) and len(lines) == 3


def check_the_tooltip_colours_are_gold_pink_amber_and_muted():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    def title(key):
        return rgb(bt(lua).TipLines(key)[1][2])
    close(title("imbue"), C["gold"], "quiet title")
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    close(title("imbue"), C["pink"], "expiring title")
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    close(title("imbue"), C["amber"], "missing title")


def check_hover_turns_the_border_cyan_and_leaving_restores_the_state_colour():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    b = btn(lua, IMBUE)
    lua.eval("__Region.Fire")(b, "OnEnter")
    t = tile(lua, IMBUE)
    close(t["ring"], C["cyan"], "hover border")
    lua.eval("__Region.Fire")(b, "OnLeave")
    t = tile(lua, IMBUE)
    close(t["ring"], C["violet"], "border after leaving"), approx(t["ring_a"], MK["ring_alpha"]["on"], "alpha after leaving")
    assert not shown(g(lua).GameTooltip)


def check_hotkey_text_and_quick_keybind_commands():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    for i in (IMBUE, SHIELD):
        b = btn(lua, i)
        assert b.commandName == f"CLICK FSBuffTabButton{i}:LeftButton", f"{i}: {b.commandName!r}"
        assert b.fsQuickKeybindOverlay is not None
    g(lua).__bindings["CLICK FSBuffTabButton2:LeftButton"] = "SHIFT-F"
    fire(lua, "UPDATE_BINDINGS")
    b = btn(lua, SHIELD)
    assert shown(b.HotKey) and b.HotKey._text == "SHIFT-F", f"hotkey {b.HotKey._text!r}"
    g(lua).__bindings["CLICK FSBuffTabButton2:LeftButton"] = None
    lua.eval("__trigger")("KeybindListener.RebindSuccess")
    assert not shown(b.HotKey)


def check_bindings_xml_declares_the_two_buff_tab_commands_after_the_totems():
    root = ET.parse(BINDINGS).getroot()
    names = [b.get("name") for b in root.findall("Binding")]
    want = [f"CLICK FSBuffTabButton{i}:LeftButton" for i in (1, 2)]
    assert names[-2:] == want, f"binding names {names}"
    assert names[:-2] == [f"CLICK FSSealButton{i}:LeftButton" for i in range(1, 8)] + [
        f"CLICK FSTotemButton{i}:LeftButton" for i in range(1, 7)], "the earlier commands moved"
    assert all(b.get("category") == "ADDONS" and not b.get("header") for b in root.findall("Binding")[-2:])


def check_binding_labels_exist_for_every_class():
    for klass in ("SHAMAN", "PALADIN", "WARRIOR"):
        lua = boot(klass=klass)
        for i, label in ((1, "Weapon imbue"), (2, "Lightning Shield")):
            text = g(lua)[f"BINDING_NAME_CLICK FSBuffTabButton{i}:LeftButton"]
            assert text == label, f"{klass}: label {i} is {text!r}, want {label!r}"


# ---------------------------------------------------------------------------------------------
# Checks: the seat
# ---------------------------------------------------------------------------------------------


def check_the_shoulder_is_the_two_by_one_block_at_316_and_the_buttons_sit_inside_it(scale):
    lua = world(scale, tips={16: ["Rockbiter 1 (59 min)"]})
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("shamanbuff"), "the buff shoulder does not stand"
    w = 2 * N["PAD"] + 2 * N["BTN"] + N["GAP"]
    h = N["PT"] + N["BTN"] + N["PB"]
    approx(w, N["BUFF_W"], "block width against the mockup"), approx(h, N["BH"], "block height against the mockup")
    # the mockup's own sh(): the totem tab ends at 300 and its foot flare reaches 310, six px before the buff tab
    approx(N["TOTEM_X"] + N["TOTEM_W"] + N["FLARE"] + 6, N["BUFF_X"], "six px of chassis line between the tabs")
    stand = None
    for f in g(lua).__frames.values():
        pts = f._points
        if f._kind == "Frame" and len(pts) == 1 and pts[1].rel is not None and pts[1].rel._name == "FSConsole" \
                and abs(float(pts[1].x) - N["BUFF_X"] * scale) < 0.5 * scale:
            stand = f
    assert stand is not None, "no frame is seated at 316 design px on the Console"
    d = csh.D(lua, stand)
    approx(d["w"], w, "art width in design px", 0.01), approx(d["h"], h, "art height in design px", 0.01)
    approx(d["x"], N["BUFF_X"], "art left", 0.5)
    bw, bh, edge = cs.BlockSize("shamanbuff")
    approx(bw, w * scale, "BlockSize width"), approx(bh, h * scale, "BlockSize height")
    host = g(lua).FSBuffTab
    p = host._points[1]
    assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT")
    approx(p.x, N["BUFF_X"] * scale, "host x", 0.5 * scale), approx(p.y, 0, "host y")
    pitch = N["BTN"] + N["GAP"]
    for col in (1, 2):
        b = btn(lua, col)
        q = b._points[1]
        assert sb.same(lua, q.rel, host) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT")
        approx(q.x, (N["PAD"] + (col - 1) * pitch) * scale, f"button {col} x")
        approx(q.y, N["PB"] * scale, f"button {col} y")
        approx(b._w, N["BTN"] * scale, f"button {col} width"), approx(b._h, N["BTN"] * scale, f"button {col} height")
    assert host._level > sb.top_level(g(lua).FSConsole), "the buttons must draw above the chassis"
    assert host._shown
    # the totem tab keeps its own seat and block
    totem = g(lua).FSTotemBar._points[1]
    approx(totem.x, N["TOTEM_X"] * scale, "totem host x", 0.5 * scale)


def check_the_console_gap_is_the_union_and_the_top_line_is_bridged_between_the_tabs():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    gaps = [c for c in csh.calls(lua) if str(c).startswith("gap:")]
    last = [float(x) for x in str(gaps[-1]).split(":")[1:]]
    # line: from the totem tab's left side + 1 to the buff tab's flare foot; halo: a pixel out each side
    approx(last[0], N["TOTEM_X"] + 1, "gap line start"), approx(last[1], N["BUFF_X"] + N["BUFF_W"] + N["FLARE"] - 1, "gap line end")
    approx(last[2], N["TOTEM_X"] - 11, "gap halo start"), approx(last[3], N["BUFF_X"] + N["BUFF_W"] + 15, "gap halo end")
    art = g(lua).FS.Console.art
    bridges = [r for r in csh.seq(art._regions) if r._kind == "Texture" and r._color is not None and r._h == 1
               and r._points[1].x > 300 and r._points[1].x < 320]
    assert len(bridges) == 1 and shown(bridges[0]), f"{len(bridges)} bridge textures"
    br = bridges[0]
    approx(br._points[1].x, N["TOTEM_X"] + N["TOTEM_W"] + N["FLARE"] - 1, "bridge start")
    approx(br._points[1].x + br._w, N["BUFF_X"] + 1, "bridge end")
    approx(br._color[4], g(lua).FS.Console.OUTLINE_ALPHA, "bridge alpha is the Console line's")
    # both tabs leaving takes the gap back
    csh.console(lua).SetActive(False)
    assert not shown(bridges[0]) and not csh.cs(lua).IsShown("shamanbuff")


def check_the_tab_follows_the_console_on_and_off_and_sits_beside_the_totem_tab():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    host = g(lua).FSBuffTab
    csh.console(lua).SetActive(False)
    assert not csh.cs(lua).IsShown("shamanbuff")
    p = host._points[1]
    assert p.rel._name == "FSTotemBar" and (p.point, p.relPoint) == ("BOTTOMLEFT", "BOTTOMRIGHT"), \
        f"Console off: {p.rel._name} {p.relPoint}"
    approx(p.x, 16.0, "gap beside the totem tab")
    assert host._shown and shown(btn(lua, IMBUE)) and shown(btn(lua, SHIELD))
    csh.console(lua).SetActive(True)
    assert csh.cs(lua).IsShown("shamanbuff") and host._points[1].rel._name == "FSConsole"
    # no Console at all: still a seat, no crash
    lua = world(console=False, tips={16: ["Rockbiter 1 (59 min)"]})
    assert g(lua).FSBuffTab._shown


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = world(1.0, tips={16: ["Rockbiter 1 (59 min)"]})
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    approx(btn(lua, 2)._w, N["BTN"] * s, "button width after a rescale")
    q = btn(lua, 2)._points[1]
    approx(q.x, (N["PAD"] + N["BTN"] + N["GAP"]) * s, "button 2 x after a rescale")


def check_no_secure_frame_is_anchored_to_the_shoulder_art():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    stand = [s for s in (csh.cs(lua).shoulder,) if s]
    arts = {id(a) for a in [csh.cs(lua).shoulder.art]}
    for f in g(lua).__frames.values():
        for p in csh.seq(f._points):
            if p.rel is not None and p.rel._name is None and p.rel._kind == "Frame":
                assert f._kind not in ("Button",), "a button is anchored to anonymous art"
    for i in (IMBUE, SHIELD):
        assert btn(lua, i)._parent._name == "FSBuffTab"
    assert g(lua).FSBuffTab._parent is g(lua).UIParent or g(lua).FSBuffTab._parent._name == "UIParent"


def check_a_seat_change_in_combat_waits_for_regen():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    set_combat(lua, True)
    lua.eval("__rescale")(1 / 1.2)
    csh.console(lua).SetActive(False)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


def check_a_login_in_combat_builds_at_regen():
    lua = world(combat=True, tips={16: ["Rockbiter 1 (59 min)"]})
    assert btn(lua, IMBUE) is None, "built in combat"
    leave_combat(lua)
    assert btn(lua, IMBUE) is not None and shown(btn(lua, IMBUE))


# ---------------------------------------------------------------------------------------------
# Checks: who gets a tab, listeners, visibility
# ---------------------------------------------------------------------------------------------


def listeners(lua, event):
    return [f for f in g(lua).__frames.values() if f._registered[event]]


def check_only_a_shaman_gets_a_tab():
    for klass in ("PALADIN", "WARRIOR", "PRIEST", "MAGE", "DRUID"):
        lua = boot(klass=klass)
        assert btn(lua, 1) is None and btn(lua, 2) is None, f"{klass} got a buff button"
        assert g(lua).FSBuffTab is None, f"{klass} got a buff host"
        assert not bt(lua).OwnsShoulder(), f"{klass}: the buff tab claims a shoulder"
        assert not csh.cs(lua).IsShown("shamanbuff"), f"{klass}: the buff shoulder stands"
        for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED"):
            assert not listeners(lua, event), f"{klass}: something listens to {event}"
        assert not [f for f in g(lua).__frames.values() if f._scripts.OnUpdate and f._name is None
                    and False], "x"
    lua = boot(klass="THROW")
    assert btn(lua, 1) is None
    lua = boot(klass="SECRET")
    assert btn(lua, 1) is None


def check_a_failed_build_leaves_no_listener_running():
    lua = boot(pre_login='__failBuild = "FSBuffTabButton2"')
    # the second button could not be built: the tab is not up and nothing listens for the data
    assert btn(lua, 2) is None
    assert not bt(lua).OwnsShoulder(), "a failed build still claims the shoulder"
    assert not csh.cs(lua).IsShown("shamanbuff")
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED", "UNIT_AURA"):
        assert not listeners(lua, event), f"a listener for {event} runs for a tab that never drew"
    cast(lua, "Rockbiter Weapon")        # and a cast changes nothing
    assert sbuf(lua).View().imbue.mode is None


def check_the_listeners_start_once_the_tiles_exist_and_only_for_the_unit_player():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "UNIT_AURA", "PLAYER_EQUIPMENT_CHANGED"):
        assert len(listeners(lua, event)) == 1, f"{event}: {len(listeners(lua, event))} listeners"
    # another unit's cast, aura or inventory changes nothing
    run(lua, '__shield(3, 480)')
    fire(lua, "UNIT_AURA", "player")
    run(lua, '__noshield()')
    fire(lua, "UNIT_AURA", "target")
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", 8017)
    assert view(lua, "shield").mode == "on", view(lua, "shield").mode
    reads = len(tip_calls(lua))
    fire(lua, "UNIT_INVENTORY_CHANGED", "target")
    assert len(tip_calls(lua)) == reads


def check_the_tab_needs_no_target_and_hangs_on_the_ui_not_the_gunsight():
    text = "\n".join(ln for p in (BUFFTAB, SHAMANBUFFS) for ln in p.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("--"))
    for token in ("UnitExists", "HasTarget", "PLAYER_TARGET_CHANGED", "Gunsight", "GunsightAreas", "TakesDots"):
        assert token not in text, f"the buff tab mentions {token}: it is a self buff reminder"
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "UnitExists = function() return false end")
    fire(lua, "PLAYER_TARGET_CHANGED")
    fire(lua, "SPELLS_CHANGED")
    host = g(lua).FSBuffTab
    assert host._shown and shown(btn(lua, IMBUE)) and shown(btn(lua, SHIELD)), "the tab needs no target"
    assert host._parent._name == "UIParent"


def check_the_tab_stands_with_the_gunsight_hud_off():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]}, pre_login="FS.Gunsight = nil; FS.GunsightAreas = nil")
    assert g(lua).FSBuffTab._shown and shown(btn(lua, IMBUE))


# ---------------------------------------------------------------------------------------------
# Checks: robustness, files
# ---------------------------------------------------------------------------------------------


def check_unreadable_sources_keep_the_last_known_imbue_and_never_log_or_throw():
    # a broken source adds nothing: the imbue read before it broke keeps counting down, and no failure reaches chat
    for setup in ('__eqMode = "throw"', '__eqMode = "secret"', '__tipMode = "throw"', '__tipMode = "secret"',
                  "GetWeaponEnchantInfo = nil", "C_Item.GetItemInfoInstant = nil", "GetInventoryItemID = nil",
                  "C_TooltipInfo = nil"):
        lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
        before = int(g(lua).__degradeCount)
        run(lua, setup)
        for event, args in (("UNIT_INVENTORY_CHANGED", ("player",)), ("SPELLS_CHANGED", ()),
                            ("PLAYER_EQUIPMENT_CHANGED", (16, True))):
            fire(lua, event, *args)
        tick(lua, 7)
        v = view(lua, "imbue")
        assert (v.mode, v.code, v.text) == ("on", "RB", "58m"), f"{setup}: {v.mode} {v.code} {v.text}"
        assert shown(btn(lua, IMBUE)) and attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon", setup
        assert int(g(lua).__degradeCount) == before, f"{setup}: a failure was logged to chat"
    # no timer API: a cast still counts, only the follow-up reads are lost
    lua = world(tips={16: ["Heavy Axe"]})
    run(lua, "C_Timer = nil")
    cast(lua, "Rockbiter Weapon")
    tick(lua, 7)
    assert (view(lua, "imbue").mode, view(lua, "imbue").code) in (("on", "RB"), ("warn", "RB"))
    # no aura snapshot: the shield is "?", never a made up count
    lua = world()
    run(lua, "FS.PlayerAuras = nil")
    fire(lua, "UNIT_AURA", "player")
    tick(lua, 2)
    assert view(lua, "shield").mode in ("hollow", "warn"), view(lua, "shield").mode


def check_toc_lists_the_buff_files_after_the_totem_bar():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    for f in ("Modules/ActionBars/ShamanBuffs.lua", "Modules/ActionBars/BuffTab.lua"):
        assert f in mods, f"{f} is not in the .toc"
    assert mods.index("Modules/ActionBars/ShamanBuffs.lua") < mods.index("Modules/ActionBars/BuffTab.lua")
    for dep in ("Modules/ActionBars/ClassShoulder.lua", "Modules/ActionBars/TotemBar.lua", "Modules/Pet/PetDock.lua",
                "Core/FrameHelpers.lua", "Modules/Auras/Buffs.lua", "Core/Theme.lua"):
        assert mods.index(dep) < mods.index("Modules/ActionBars/ShamanBuffs.lua"), f"{dep} must load before ShamanBuffs.lua"


def check_no_em_dashes_and_no_flagged_words_in_the_new_files():
    for path in (BUFFTAB, SHAMANBUFFS, Path(__file__)):
        assert path.exists(), f"{path} is missing"
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{path.name} has an em dash"
    for path in (BUFFTAB, SHAMANBUFFS):
        strings = re.findall(r'"([^"\n]*)"', path.read_text(encoding="utf-8"))
        for s in strings:
            if " " not in s and "_" in s or s.startswith(("Interface", "CLICK", "UNIT_", "PLAYER_")):
                continue
            assert not re.search(r"\b(probe|bot|monitor|test)\b", s, re.I), f"{path.name}: player text {s!r}"


def check_the_old_class_module_chips_are_gone_from_the_gunsight_file():
    text = (ADDON / "Modules/CombatHud/GunsightShaman.lua").read_text(encoding="utf-8")
    for token in ("GetWeaponEnchantInfo", "IMBUE", "SHIELD", "BuildChip", "UNIT_SPELLCAST"):
        assert token not in text.replace("IMBUE and SHIELD chips", ""), f"GunsightShaman.lua still has {token}"


def font_sizes(lua, i):
    b = btn(lua, i)
    return (float(b.fsText._font[2]), float(b.fsChip.code._font[2]), float(b.fsLockText._font[2]))


def check_tile_fonts_are_the_design_size_at_every_scale_and_after_a_rescale():
    # like the totem and seal tabs: text is not scaled with the UI scale, and a rescale leaves it as it was
    lua = world(1.0, tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsText._text == "SHIELD"
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    assert font_sizes(lua, SHIELD) == (9.0, 10.0, 11.0), font_sizes(lua, SHIELD)
    lua.eval("__rescale")(1 / 1.2)
    update(lua)
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    assert font_sizes(lua, SHIELD) == (9.0, 10.0, 11.0), font_sizes(lua, SHIELD)
    # and from a boot at the small scale
    lua = world(1 / 1.2, tips={16: ["Rockbiter 1 (59 min)"]})
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    # a word set small, then back to the time: the size follows the text, also after a rescale
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert font_sizes(lua, SHIELD)[0] == 11.0


def counting(lua):
    run(lua, "__changes = 0; FS.ShamanBuffs.OnChange(function() __changes = __changes + 1 end)")
    return lambda: int(g(lua).__changes)


def check_an_irrelevant_cast_is_a_no_op_and_an_unknown_id_with_the_shield_name_is_ignored():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"), tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    changes = counting(lua)
    run(lua, '__idNames[4242] = "Frost Shock"')
    for sid in (4242, 99999):
        run(lua, f"__castOk({sid})")
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", None)
    assert changes() == 0, "a cast that is not an imbue or a shield reached the tab"
    # an orb proc: the same name as Lightning Shield, an id the player does not know
    run(lua, '__idNames[26364] = "Lightning Shield"')
    update(lua)
    assert view(lua, "shield").mode == "warn"
    run(lua, "__castOk(26364)")
    update(lua)
    assert view(lua, "shield").mode == "warn", "an orb proc faked a fresh Lightning Shield cast"
    assert changes() == 0
    run(lua, '__idNames[26365] = "Water Shield"')
    run(lua, "__castOk(26365)")
    update(lua)
    assert not view(lua, "shield").other and changes() == 0, "an unknown Water Shield id was taken"
    # the real ids still count
    cast(lua, "Lightning Shield")
    update(lua)
    assert view(lua, "shield").mode == "on" and changes() == 1


def check_leaving_combat_keeps_the_shield_an_estimate_until_the_next_tick_reads_the_snapshot():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    set_combat(lua, True)
    update(lua)
    assert view(lua, "shield").text == "~3"
    run(lua, "__shield(1, 470)")                       # the snapshot catches up a moment after regen
    leave_combat(lua)
    update(lua)
    assert view(lua, "shield").text.startswith("~"), "regen read a snapshot that may lag: " + view(lua, "shield").text
    tick(lua, 1)
    assert view(lua, "shield").text == "1" and not view(lua, "shield").estimate, view(lua, "shield").text


def check_a_tooltip_read_that_contradicts_a_fresh_cast_waits_for_the_grace():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (10 min)"]})
    assert view(lua, "imbue").code == "RB"
    cast(lua, "Flametongue Weapon")                    # replaces the main hand imbue
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")      # the weapon still says Rockbiter
    update(lua)
    v = view(lua, "imbue")
    assert (v.code, v.text) == ("FT", "60m"), (v.code, v.text)
    tip(lua, 16, ["Flametongue 1 (60 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").code == "FT"
    # a weapon that never took the cast: the tooltip wins once the grace is over
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (10 min)"]})
    cast(lua, "Flametongue Weapon")
    tick(lua, 3)
    v = view(lua, "imbue")
    assert (v.code, v.text) == ("RB", "10m"), (v.code, v.text)


def event_frames(lua):
    """Every other frame that hears the spellbook events, and the data model's own (it has UNIT_SPELLCAST_SUCCEEDED)."""
    data = listeners(lua, "UNIT_SPELLCAST_SUCCEEDED")
    assert len(data) == 1, len(data)
    others = [f for f in g(lua).__frames.values()
              if f._registered["SPELLS_CHANGED"] and f._scripts.OnEvent and f is not data[0]]
    assert others, "nobody else hears the spellbook events"
    return others, data[0]


def deliver_data_last(lua, event):
    """The worst order: the data model hears of the event after everything else, the tab included."""
    others, data = event_frames(lua)
    for f in others:
        f._scripts.OnEvent(f, event)
    data._scripts.OnEvent(data, event)


def check_learning_lightning_shield_unlocks_the_tile_whichever_handler_runs_first():
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_LEVEL_UP"):
        lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
        b = btn(lua, SHIELD)
        assert b.fsLocked
        run(lua, '__spell("Lightning Shield", 324, true)')
        deliver_data_last(lua, event)
        assert not b.fsLocked and abs(float(b._alpha) - 1.0) < 1e-6, f"{event}: still locked"
        assert attr(b, "type") == "spell" and attr(b, "spell") == "Lightning Shield", event
        assert shown(b.fsFace) and not shown(b.fsMold)
    # a spell the first look missed (false answers do not stick): the world entering asks again
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert not btn(lua, SHIELD).fsLocked
    # learned in combat: nothing protected is touched, the regen finishes it
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    set_combat(lua, True)
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    tick(lua, 2)
    assert blocked(lua) == 0 and btn(lua, SHIELD).fsLocked
    leave_combat(lua)
    assert not btn(lua, SHIELD).fsLocked and attr(btn(lua, SHIELD), "spell") == "Lightning Shield"
    # and the imbue tile appears when the first imbue is learned, handler order aside
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Heavy Axe"]})
    assert not shown(btn(lua, IMBUE))
    run(lua, '__spell("Rockbiter Weapon", 8017, true)')
    deliver_data_last(lua, "SPELLS_CHANGED")
    assert shown(btn(lua, IMBUE)) and attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon"


def check_an_unchanged_tick_allocates_nothing_in_or_out_of_combat():
    for combat in (False, True):
        lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
        run(lua, "__shield(3, 480)")
        fire(lua, "UNIT_AURA", "player")
        if combat:
            set_combat(lua, True)
        run(lua, """
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            local ShamanBuffs, BuffTab = FS.ShamanBuffs, FS.BuffTab
            local t = __now
            local function step(i) ShamanBuffs.Update(t + i * 0.01); BuffTab.Paint() end
            for i = 1, 50 do step(i) end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for i = 51, 450 do step(i) end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        # a table per tick would be 56+ bytes each (the first version grew 100 KB); the rest is the mock itself (about 600 B)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 idle ticks allocated {float(g(lua).__grew):.0f} bytes"


CHECKS = [
    check_parse_reads_minutes_seconds_hours_with_and_without_a_rank,
    check_parse_ignores_lines_that_are_not_an_imbue_with_a_time,
    check_parse_follows_the_clients_own_enchant_time_strings_and_spell_names,
    check_the_imbue_names_come_from_the_spell_ids_not_from_english_text,
    check_tooltip_reads_say_imbue_none_or_unreadable,
    check_the_main_hand_imbue_shows_its_code_and_time_in_the_quiet_look,
    check_under_five_minutes_the_tile_turns_pink_and_under_one_minute_counts_seconds,
    check_a_missing_imbue_is_an_amber_hollow_word_and_an_unreadable_one_a_hollow_question_mark,
    check_dual_wield_shows_the_least_time_and_asks_for_the_missing_hand,
    check_a_shield_or_an_empty_off_hand_never_asks_for_an_imbue,
    check_a_two_handed_weapon_without_an_imbue_asks_for_one,
    check_the_tooltip_is_never_read_in_combat_and_the_clock_counts_down_from_the_last_read,
    check_tile_fonts_are_the_design_size_at_every_scale_and_after_a_rescale,
    check_an_irrelevant_cast_is_a_no_op_and_an_unknown_id_with_the_shield_name_is_ignored,
    check_leaving_combat_keeps_the_shield_an_estimate_until_the_next_tick_reads_the_snapshot,
    check_a_tooltip_read_that_contradicts_a_fresh_cast_waits_for_the_grace,
    check_learning_lightning_shield_unlocks_the_tile_whichever_handler_runs_first,
    check_an_unchanged_tick_allocates_nothing_in_or_out_of_combat,
    check_the_slow_tick_reads_out_of_combat_and_a_read_does_not_stair_step_the_clock,
    check_a_cast_starts_a_fresh_hour_and_the_next_read_takes_over,
    check_a_cast_in_combat_counts_a_fresh_hour_and_a_weapon_swapped_in_combat_is_forgotten,
    check_two_imbue_casts_back_to_back_each_go_to_their_own_hand,
    check_a_recast_on_the_other_hand_does_not_hide_the_sooner_expiring_one,
    check_a_pending_cast_outlasts_an_early_none_read_only_for_the_grace,
    check_get_weapon_enchant_info_counts_only_when_it_answers_true,
    check_no_imbue_known_means_no_tile_and_learning_one_brings_it,
    check_the_shield_shows_ls_and_its_orbs_then_its_time_when_expiring,
    check_a_missing_shield_is_amber_and_no_snapshot_yet_is_a_hollow_question_mark,
    check_in_combat_the_shield_is_an_estimate_with_a_tilde_and_dashes,
    check_a_shield_cast_in_combat_shows_three_orbs_and_a_pending_cast_expires_with_the_clock,
    check_water_shield_is_never_nagged_and_a_water_shield_cast_in_combat_clears_the_lightning_cast,
    check_a_shield_with_no_aura_end_ends_at_its_application_not_at_the_last_read,
    check_lightning_shield_is_a_locked_dotted_mold_until_it_is_known,
    check_two_named_secure_buttons_in_the_fixed_order_built_once,
    check_click_attributes_are_a_spell_by_name_and_follow_the_imbue_shown,
    check_attributes_are_written_out_of_combat_only_and_queued_for_regen,
    check_nothing_protected_is_touched_in_combat_by_events_ticks_and_paint,
    check_no_forbidden_field_or_attribute_is_ever_written_on_a_secure_button,
    check_the_files_use_no_snippets_and_no_state_drivers,
    check_tooltip_lines_follow_the_mockups_wording,
    check_the_tooltip_colours_are_gold_pink_amber_and_muted,
    check_hover_turns_the_border_cyan_and_leaving_restores_the_state_colour,
    check_hotkey_text_and_quick_keybind_commands,
    check_bindings_xml_declares_the_two_buff_tab_commands_after_the_totems,
    check_binding_labels_exist_for_every_class,
    check_the_console_gap_is_the_union_and_the_top_line_is_bridged_between_the_tabs,
    check_the_tab_follows_the_console_on_and_off_and_sits_beside_the_totem_tab,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_no_secure_frame_is_anchored_to_the_shoulder_art,
    check_a_seat_change_in_combat_waits_for_regen,
    check_a_login_in_combat_builds_at_regen,
    check_only_a_shaman_gets_a_tab,
    check_a_failed_build_leaves_no_listener_running,
    check_the_listeners_start_once_the_tiles_exist_and_only_for_the_unit_player,
    check_the_tab_needs_no_target_and_hangs_on_the_ui_not_the_gunsight,
    check_the_tab_stands_with_the_gunsight_hud_off,
    check_unreadable_sources_keep_the_last_known_imbue_and_never_log_or_throw,
    check_toc_lists_the_buff_files_after_the_totem_bar,
    check_no_em_dashes_and_no_flagged_words_in_the_new_files,
    check_the_old_class_module_chips_are_gone_from_the_gunsight_file,
]
SCALED_CHECKS = [
    check_the_shoulder_is_the_two_by_one_block_at_316_and_the_buttons_sit_inside_it,
]


def main() -> int:
    failed = total = 0

    def run_check(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run_check(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run_check(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
