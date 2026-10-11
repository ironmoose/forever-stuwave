#!/usr/bin/env python3
"""Runs the real TotemBar.lua (the Shaman totem tab) headless, in classshoulder-harness's world: the actionbars
mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua, PetActionBar.lua, PetDock.lua and
ClassShoulder.lua.

The tab is a Shaman shoulder on the Console chassis, 6 columns x 1 row (264 x 49 design px), built like the Paladin
seal bar: plain SecureActionButtonTemplate buttons on a separate protected host, attributes written from Lua out of
combat only (no secure snippet, no state driver), cooldown swipes fed from duration objects. Checked here:

  * six named secure buttons FSTotemButton1..6 in the fixed, append only keybind order Fire, Earth, Water, Air,
    Set drop, Recall, built once; the same six CLICK commands in Bindings.xml with a binding label each;
  * an element button's LEFT click is decided at sync time. ACTION mode when the multi-cast bar is usable
    (C_ActionBar.GetMultiCastBarIndex answers a plain number and GetMultiCastTotemSpells lists totems for the
    slot): type1 "action" on action id (bar - 1) * 12 + (set - 1) * 4 + slot, so a pick made in combat needs no
    attribute write. Otherwise SPELL mode: type1 "spell" with the picked totem's NAME. Right click is the secure
    "destroytotem" type on the element's totem slot (FIRE 1, EARTH 2, WATER 3, AIR 4);
  * Set drop is Call of the Elements (shift: Call of the Ancestors once known), Recall is Totemic Recall, both
    locked until known; a locked button carries no castable attribute and is dimmed by alpha, never hidden;
  * every protected write waits out combat and replays at PLAYER_REGEN_ENABLED; SetMultiCastSpell is protected and
    is NEVER called in combat (a pick made there is queued for regen in action mode as in spell mode). A call
    counts as landed only when the slot reads the pick back; the button shows what the slot really holds, a pick
    that never lands (blocked call, slot that never updates) drops the element to spell mode, and a slot that is
    empty or not yet filled never leaves a dead action button;
  * ACTION mode also needs the multi-cast bar to exist (HasMultiCastActionBar, else Call of the Elements known):
    below that the tab is SPELL mode with no SetMultiCastSpell call and no warning. An empty or foreign slot is
    filled only at the id the native multi-cast button reported (a formula id is adopted, never written; a slot
    holding another element's totem is a mapping error). A call that raises twice, or a fill the slot never
    takes, gives the element up to SPELL mode until a learn event (PLAYER_LEVEL_UP, a changed known set) allows
    one fresh try; the tab's own default fill is never saved as the user's pick;
  * totems are found by rank 1 spell id (their localized name finds the highest rank known), not by English name;
  * the picker is a plain frame on UIParent that nothing secure is a child of or anchored to; it opens from the
    arrow tab or an Alt-click (which never drops the totem), lists the known totems, and a click stores the pick
    per character;
  * the Shaman shoulder, the Ghost Wolf stance bar staying where it was, no `.bar` field and no `useparent-`
    attribute on any button (Blizzard's secure code reads both during a click).

The mock is strict and is NOT the real client. TOTEMBAR_LUA, BINDINGS_XML and TOC_FILE point the harness at mutant
copies (a check must fail on a broken one).

    python3 tools/totembar-harness.py

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
TOTEMBAR = Path(os.environ.get("TOTEMBAR_LUA", ADDON / "Modules/ActionBars/TotemBar.lua"))
BINDINGS = Path(os.environ.get("BINDINGS_XML", ADDON / "Bindings.xml"))
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csh = _load("classshoulder_harness", "classshoulder-harness.py")
sb = csh.sb
MU = sb.MU
g = sb.g
fire = sb.fire
approx = sb.approx
set_combat = sb.set_combat
blocked = sb.blocked
SCALES = csh.SCALES
PITCH = MU["BTN"] + MU["BG"]

# The fixed order (it is the saved keybind order): button N is always this element or spell.
ORDER = ["fire", "earth", "water", "air", "set", "recall"]
SLOT = {"fire": 1, "earth": 2, "water": 3, "air": 4}
LABELS = ["Fire totem", "Earth totem", "Water totem", "Air totem", "Totem set drop", "Totemic Recall"]
TOTEMS = {
    "fire": ["Searing Totem", "Frost Resistance Totem", "Magma Totem", "Flametongue Totem"],
    "earth": ["Stoneskin Totem", "Earthbind Totem", "Stoneclaw Totem", "Strength of Earth Totem", "Tremor Totem"],
    "water": ["Healing Stream Totem", "Poison Cleansing Totem", "Mana Spring Totem", "Fire Resistance Totem"],
    "air": ["Grounding Totem", "Nature Resistance Totem"],
}
# the rank 1 spell ids TotemBar.lua carries (the mock names them, so the addon finds the localized name by id)
TOTEM_IDS = {
    "Searing Totem": 3599, "Frost Resistance Totem": 8181, "Magma Totem": 8190, "Flametongue Totem": 8227,
    "Stoneskin Totem": 8071, "Earthbind Totem": 2484, "Stoneclaw Totem": 5730, "Strength of Earth Totem": 8075,
    "Tremor Totem": 8143,
    "Healing Stream Totem": 5394, "Poison Cleansing Totem": 8166, "Mana Spring Totem": 5675,
    "Fire Resistance Totem": 8184,
    "Grounding Totem": 8177, "Nature Resistance Totem": 10595,
}
CALL, ANCESTORS, RECALL = 66842, 66843, 36936
BAR = 12          # what GetMultiCastBarIndex answers in the mock
GUID = "Player-1-0000ABCD"

MOCKS = r"""
FS.Theme.COLOR_AMBER = FS.Theme.COLOR_AMBER or { 1, 0.7137, 0.2824, 1 }
FS.Theme.COLOR_MUTED = FS.Theme.COLOR_MUTED or { 0.6157, 0.5765, 0.7686, 1 }
-- the host parents secure buttons, so it is restricted in combat like the Console root
do
    local create = CreateFrame
    function CreateFrame(kind, name, ...)
        local f = create(kind, name, ...)
        if name == "FSTotemBar" then f._protected = true end
        return f
    end
end
__Region.SetReverse = function(self, v) self._reverse = v end
function GameTooltip:SetOwner(owner) self._lines = {}; self._owner = owner end
function GameTooltip:ClearLines() self._lines = {} end
function GameTooltip:SetText(t) self._lines = { t } end
UISpecialFrames = {}
__alt = false
function IsAltKeyDown() return __alt end
function UnitGUID() return %(guid)r end
-- spells by id: name <-> id, learned or not (the sealbar mock's __spells / __idNames / __learned)
function __spell(name, id, known)
    __spells[name] = id
    __idNames[id] = name
    if known ~= false then __learned[id] = true else __learned[id] = nil end
end
function __unlearn(name) local id = __spells[name]; __learned[id] = nil end
__ids = {}
do
    for name, id in pairs(%(all)s) do __ids[name] = id; __spell(name, id, false) end
end
function __know(name) __learned[__ids[name]] = true end
-- the multi-cast bar: C_ActionBar.GetMultiCastBarIndex, GetMultiCastTotemSpells(slot), SetMultiCastSpell(action, spell)
__mc = { bar = %(bar)d, lists = {}, slots = {}, calls = {}, refuse = false, barMode = nil, listMode = nil, noApi = false,
         hasBar = true }
-- HasMultiCastActionBar: true once the client has the bar (Call of the Elements known); a test sets __mc.hasBar
function HasMultiCastActionBar()
    if __mc.hasBarMode == "throw" then error("HasMultiCastActionBar blew up") end
    if __mc.hasBarMode == "secret" then return __SECRET end
    if __mc.hasBarMode == "number" then return __mc.hasBar and 1 or 0 end
    return __mc.hasBar
end
C_ActionBar.GetMultiCastBarIndex = function()
    if __mc.barMode == "throw" then error("GetMultiCastBarIndex blew up") end
    if __mc.barMode == "secret" then return __SECRET end
    return __mc.bar
end
function __mc_list(slot, names)
    local ids = {}
    for _, name in ipairs(names) do ids[#ids + 1] = __ids[name] end
    __mc.lists[slot] = ids
end
function GetMultiCastTotemSpells(slot)
    if __mc.listMode == "throw" then error("GetMultiCastTotemSpells blew up") end
    if __mc.listMode == "secret" then return __SECRET end
    return unpack(__mc.lists[slot] or {})
end
__mc.queued = {}
function SetMultiCastSpell(action, spell)
    __mc.calls[#__mc.calls + 1] = { action, spell, combat = __combat }
    if __mc.throws then error("SetMultiCastSpell blew up") end
    -- a blocked call from tainted code does nothing at all (here it is a plain no-op)
    if __mc.blocked or (__combat and __mc.refuse) then return end
    -- an event the call raises synchronously (ACTIONBAR_SLOT_CHANGED), once, before the slot has changed
    local ev = __mc.reenter
    if ev then __mc.reenter = nil; __fire_event(ev) end
    -- a slot that updates later: the call is accepted, GetActionInfo shows it only after __mc_flush()
    if __mc.delay then __mc.queued[action] = spell; return end
    __mc.slots[action] = spell
end
function __mc_flush()
    for action, spell in pairs(__mc.queued) do __mc.slots[action] = spell end
    __mc.queued = {}
end
-- a clock and a timer queue: __advance(dt) moves time and runs every queued C_Timer.After callback
__now, __timers = 0, {}
function GetTime() return __now end
C_Timer = { After = function(delay, fn) __timers[#__timers + 1] = fn end }
function __advance(dt)
    __now = __now + dt
    local due = __timers
    __timers = {}
    for _, fn in ipairs(due) do fn() end
end
-- Blizzard's own multi-cast buttons, in SHAMAN_TOTEM_PRIORITIES order (Earth, Fire, Water, Air): button n answers
-- base + n from CalculateAction
function __native(base)
    SHAMAN_TOTEM_PRIORITIES = { 2, 1, 3, 4 }
    for i = 1, 4 do
        _G["MultiCastActionButton" .. i] = { CalculateAction = function() return base + i end }
    end
end
-- the same buttons, answering the id the formula gives for their totem slot (the default world: the native bar and
-- the formula agree, and a test that wants the formula alone boots with native=False)
function __nativeFormula()
    SHAMAN_TOTEM_PRIORITIES = { 2, 1, 3, 4 }
    for i = 1, 4 do
        local slot = SHAMAN_TOTEM_PRIORITIES[i]
        _G["MultiCastActionButton" .. i] = { CalculateAction = function() return (%(bar)d - 1) * 12 + slot end }
    end
end
function GetActionInfo(action)
    if __mc.infoMode == "throw" then error("GetActionInfo blew up") end
    if __mc.infoMode == "secret" then return __SECRET end
    local s = __mc.slots[action]
    if s then return "spell", s end
end
-- totems standing: slot -> { name, start, duration }; GetTotemInfo and the duration object
__tot, __totMode, __totObjNil = {}, nil, false
function GetTotemInfo(slot)
    if __totMode == "throw" then error("GetTotemInfo blew up") end
    if __totMode == "secret" then return __SECRET, __SECRET, __SECRET, __SECRET end
    -- a standing totem read in combat: plain true, "", 0, 0, 0
    if __totMode == "zeros" and __tot[slot] then return true, "", 0, 0, 0 end
    local t = __tot[slot]
    if t then return true, t[1], t[2], t[3], 136000 end
    return false, "", 0, 0, 0
end
function GetTotemDuration(slot)
    if __totMode == "objthrow" then error("GetTotemDuration blew up") end
    local t = __tot[slot]
    if t and not __totObjNil then return { totemFor = slot } end
end
"""

def boot(scale: float = 1.0, *, klass: str = "SHAMAN", learned=(), lists=None, spells=(), combat: bool = False,
         bar_mode=None, list_mode=None, console: bool = True, pre_login: str = "", native: bool = True):
    """A Shaman world. `learned`: totem names the spellbook knows; `lists`: {slot: [names]} the multi-cast
    API reports; `spells`: other spell names to know (Call of the Elements etc., by id through __spell).
    `native`: install Blizzard's multi-cast buttons answering the formula's ids (False: the formula is all there is)."""
    all_ids = "{" + ",".join(f'["{n}"]={i}' for n, i in TOTEM_IDS.items()) + "}"
    mocks = MOCKS % dict(guid=GUID, bar=BAR, all=all_ids)
    setup = ["__nativeFormula()"] if native else []
    setup += [f'__know("{n}")' for n in learned]
    for slot, names in (lists or {}).items():
        setup.append(f"__mc_list({slot}, {{" + ",".join(f'"{n}"' for n in names) + "})")
    for name, sid in (("Call of the Elements", CALL), ("Call of the Ancestors", ANCESTORS),
                      ("Totemic Recall", RECALL)):
        setup.append(f'__spell("{name}", {sid}, {"true" if name in spells else "false"})')
    if bar_mode:
        setup.append(f'__mc.barMode = "{bar_mode}"')
    if list_mode:
        setup.append(f'__mc.listMode = "{list_mode}"')
    return sb.boot(scale, klass=klass, known=[], combat=combat, console=console,
                   extra_lua=csh.PATCH + mocks + "\n" + "\n".join(setup),
                   extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, TOTEMBAR),
                   pre_login=pre_login)


def btn(lua, i):
    return g(lua)[f"FSTotemButton{i}"]


def by_key(lua, key):
    return btn(lua, ORDER.index(key) + 1)


def attr(b, name):
    return b._attrs[name]


def shown(b) -> bool:
    return bool(b._shown)


def tb(lua):
    return g(lua).FS.TotemBar


def click(lua, b, button="LeftButton", down=False):
    lua.eval("__Region.Fire")(b, "OnClick", button, down)


def seq(table) -> list:
    return csh.seq(table)


def mc_calls(lua) -> list:
    return [(int(c[1]), int(c[2]), bool(c.combat)) for c in seq(g(lua).__mc.calls)]


def tid(lua, name) -> int:
    return int(g(lua).__ids[name])


def advance(lua, dt):
    lua.eval("__advance")(dt)


def action_id(slot, bar=BAR, mc_set=1) -> int:
    return (bar - 1) * 12 + (mc_set - 1) * 4 + slot


def picks(lua):
    db = g(lua).ForeverSTUwaveDB
    return db.totemPicks[GUID] if db and db.totemPicks else None


def lists_for(*elements):
    return {SLOT[e]: TOTEMS[e] for e in elements}


def all_known(**kw):
    names = [n for e in ("fire", "earth", "water", "air") for n in TOTEMS[e]]
    return boot(learned=names, spells=("Call of the Elements", "Call of the Ancestors", "Totemic Recall"), **kw)


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------


def check_six_named_secure_buttons_in_the_fixed_order_built_once():
    lua = all_known()
    for i in range(1, 7):
        b = btn(lua, i)
        assert b is not None, f"FSTotemButton{i} was not built"
        assert b._secure, f"FSTotemButton{i} is not a secure template button"
        assert b.fsKey == ORDER[i - 1], f"button {i} is {b.fsKey!r}, want {ORDER[i - 1]!r}"
        clicks = [b._clicks[k] for k in range(1, len(b._clicks) + 1)]
        assert clicks == ["AnyUp", "AnyDown"], f"button {i} clicks {clicks}"
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "UPDATE_BINDINGS",
                  "PLAYER_TOTEM_UPDATE", "SPELL_UPDATE_COOLDOWN"):
        fire(lua, event)
    frames = [f for f in g(lua).__frames.values() if f._name and re.match(r"FSTotemButton\d$", f._name)]
    assert len(frames) == 6, f"{len(frames)} named totem buttons, expected exactly 6"


def check_only_a_shaman_gets_a_tab():
    for klass in ("PALADIN", "WARRIOR", "PRIEST", "MAGE", "DRUID"):
        lua = boot(klass=klass)
        assert btn(lua, 1) is None, f"{klass} got a totem button"
        assert g(lua).FSTotemBar is None, f"{klass} got a totem host"
        assert not tb(lua).OwnsShoulder(), f"{klass}: the totem tab claims the shoulder"
        assert not csh.cs(lua).IsShown() or klass in ("PALADIN", "WARRIOR"), f"{klass}: a shoulder stands"


def check_action_mode_when_the_multicast_bar_is_usable():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    assert b.fsMode == "action", f"mode {b.fsMode!r}"
    assert attr(b, "type1") == "action"
    assert attr(b, "action1") == action_id(2), f"action1 {attr(b, 'action1')} (bar {BAR}, set 1, slot 2)"
    assert attr(b, "spell1") is None, "action mode kept a spell attribute"
    assert attr(b, "type2") == "destroytotem" and attr(b, "totem-slot2") == 2
    assert attr(b, "alt-type1") == "", "Alt-click would drop the totem as well as open the picker"
    # an action id per slot: FIRE 1, EARTH 2, WATER 3, AIR 4
    lua = all_known_with_lists()
    for key, slot in SLOT.items():
        bb = by_key(lua, key)
        assert attr(bb, "action1") == action_id(slot), f"{key}: action1 {attr(bb, 'action1')}"
        assert attr(bb, "totem-slot2") == slot, f"{key}: totem-slot2 {attr(bb, 'totem-slot2')}"
        assert attr(bb, "type2") == "destroytotem"


def all_known_with_lists(**kw):
    names = [n for e in ("fire", "earth", "water", "air") for n in TOTEMS[e]]
    return boot(learned=names, lists=lists_for("fire", "earth", "water", "air"),
                spells=("Call of the Elements", "Call of the Ancestors", "Totemic Recall"), **kw)


def check_spell_mode_when_there_is_no_usable_multicast_bar():
    cases = {
        "no lists": dict(),
        "bar index throws": dict(bar_mode="throw", lists=lists_for("earth")),
        "bar index secret": dict(bar_mode="secret", lists=lists_for("earth")),
        "list throws": dict(list_mode="throw", lists=lists_for("earth")),
        "list secret": dict(list_mode="secret", lists=lists_for("earth")),
    }
    for label, kw in cases.items():
        lua = boot(learned=TOTEMS["earth"], **kw)
        b = by_key(lua, "earth")
        assert b.fsMode == "spell", f"{label}: mode {b.fsMode!r}"
        assert attr(b, "type1") == "spell" and attr(b, "spell1") == "Stoneskin Totem", (
            f"{label}: {attr(b, 'type1')!r} {attr(b, 'spell1')!r}")
        assert attr(b, "action1") is None, f"{label}: an action attribute in spell mode"
        assert attr(b, "type2") == "destroytotem" and attr(b, "totem-slot2") == 2, label
    # the mode is per element: a list for earth only leaves fire in spell mode
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"], lists=lists_for("earth"))
    assert by_key(lua, "earth").fsMode == "action" and by_key(lua, "fire").fsMode == "spell"


def check_no_multicast_api_at_all_degrades_to_spell_mode():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
               pre_login="C_ActionBar.GetMultiCastBarIndex = nil; GetMultiCastTotemSpells = nil")
    # the mode was decided before the strip above at the first sync, so force a fresh one
    fire(lua, "SPELLS_CHANGED")
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and attr(b, "spell1") == "Stoneskin Totem", f"{b.fsMode} {attr(b, 'spell1')}"
    assert attr(b, "action1") is None


def check_a_mode_change_rewrites_the_attributes_cleanly():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    assert b.fsMode == "action"
    lua.execute("__mc.lists[2] = nil")
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "spell" and attr(b, "type1") == "spell" and attr(b, "action1") is None
    lua.execute('__mc_list(2, {"Stoneskin Totem"})')
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "action" and attr(b, "spell1") is None and attr(b, "action1") == action_id(2)


def check_locked_buttons_carry_nothing_castable_and_dim_by_alpha():
    lua = boot()      # nothing known: a level 1 Shaman
    for i in range(1, 7):
        b = btn(lua, i)
        assert b.fsLocked, f"button {i} should be locked"
        for name in ("type", "type1", "type2", "action1", "spell", "spell1", "totem-slot2", "alt-type1",
                     "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1", "shift-type1", "shift-spell1"):
            assert attr(b, name) is None, f"locked button {i} carries {name}={attr(b, name)!r}"
        assert b._alpha < 1, f"locked button {i} is not dimmed"
        assert shown(b), f"locked button {i} was hidden, a locked button is dimmed by alpha"
        assert shown(b.fsMold), f"locked button {i} shows no dotted mold"
    assert by_key(lua, "earth").fsLockText._text == "L4"
    assert by_key(lua, "fire").fsLockText._text == "L10"
    assert by_key(lua, "water").fsLockText._text == "L20"
    assert by_key(lua, "air").fsLockText._text == "L30"
    assert by_key(lua, "set").fsLockText._text == "L20" and by_key(lua, "recall").fsLockText._text == "L20"


def check_learning_a_totem_unlocks_just_that_element():
    lua = boot()
    set_combat(lua, False)
    lua.execute('__know("Stoneskin Totem")')
    fire(lua, "LEARNED_SPELL_IN_TAB")
    earth, fire_b = by_key(lua, "earth"), by_key(lua, "fire")
    assert not earth.fsLocked and earth._alpha == 1 and attr(earth, "type1") == "spell"
    assert not shown(earth.fsMold)
    assert fire_b.fsLocked and attr(fire_b, "type1") is None
    lua.execute('__know("Searing Totem")')
    fire(lua, "PLAYER_LEVEL_UP")
    assert not fire_b.fsLocked and attr(fire_b, "spell1") == "Searing Totem"


def check_set_and_recall_buttons():
    lua = boot(learned=TOTEMS["earth"], spells=("Call of the Elements", "Totemic Recall"))
    s, r = by_key(lua, "set"), by_key(lua, "recall")
    assert not s.fsLocked and attr(s, "type") == "spell" and attr(s, "spell") == "Call of the Elements"
    assert attr(s, "shift-type1") is None and attr(s, "shift-spell1") is None, "Ancestors is not known yet"
    assert not r.fsLocked and attr(r, "type") == "spell" and attr(r, "spell") == "Totemic Recall"
    lua = boot(spells=("Call of the Elements", "Call of the Ancestors", "Totemic Recall"))
    s = by_key(lua, "set")
    assert attr(s, "shift-type1") == "spell" and attr(s, "shift-spell1") == "Call of the Ancestors"
    # unknown: locked, no attribute
    lua = boot(spells=("Totemic Recall",))
    assert by_key(lua, "set").fsLocked and attr(by_key(lua, "set"), "spell") is None
    assert not by_key(lua, "recall").fsLocked
    # neither carries an element totem attribute
    for key in ("set", "recall"):
        assert attr(by_key(lua, key), "type2") is None and attr(by_key(lua, key), "totem-slot2") is None


def check_default_pick_is_the_first_known_totem_and_a_stale_pick_falls_back():
    lua = boot(learned=["Earthbind Totem", "Tremor Totem"])
    b = by_key(lua, "earth")
    assert attr(b, "spell1") == "Earthbind Totem", f"default pick {attr(b, 'spell1')!r}"
    # a stored pick of a totem that is not known any more falls back to the first known
    lua = boot(learned=["Earthbind Totem", "Tremor Totem"], pre_login=(
        f'ForeverSTUwaveDB = {{ totemPicks = {{ [{GUID!r}] = {{ earth = {{ id = 9999, name = "Gone Totem" }} }} }} }}'))
    assert attr(by_key(lua, "earth"), "spell1") == "Earthbind Totem"
    # a stored pick that is known is kept
    lua = boot(learned=["Earthbind Totem", "Tremor Totem"], pre_login=(
        f'ForeverSTUwaveDB = {{ totemPicks = {{ [{GUID!r}] = {{ earth = {{ id = {TOTEM_IDS["Tremor Totem"]}, name = "Tremor Totem" }} }} }} }}'))
    assert attr(by_key(lua, "earth"), "spell1") == "Tremor Totem"


def check_spell_mode_pick_out_of_combat_writes_at_once_and_stores_it():
    lua = boot(learned=TOTEMS["earth"])
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    b = by_key(lua, "earth")
    assert attr(b, "spell1") == "Tremor Totem", f"spell1 {attr(b, 'spell1')!r}"
    saved = picks(lua)
    assert saved is not None and saved.earth.id == tid(lua, "Tremor Totem") and saved.earth.name == "Tremor Totem"
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem"), f"icon {b.icon._texture}"
    assert mc_calls(lua) == [], "spell mode must not touch the multi-cast slot"


def check_spell_mode_pick_in_combat_waits_for_regen():
    lua = boot(learned=TOTEMS["earth"])
    b = by_key(lua, "earth")
    set_combat(lua, True)
    before = blocked(lua)
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert blocked(lua) == before, "a protected write was tried in combat"
    assert attr(b, "spell1") == "Stoneskin Totem", "the attribute changed in combat"
    assert picks(lua).earth.name == "Tremor Totem", "the pick must be stored at once"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert attr(b, "spell1") == "Tremor Totem", f"regen replay left {attr(b, 'spell1')!r}"


def check_action_mode_pick_calls_setmulticastspell_and_stores_it():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert mc_calls(lua)[-1] == (action_id(2), tid(lua, "Tremor Totem"), False), mc_calls(lua)
    assert picks(lua).earth.id == tid(lua, "Tremor Totem")
    assert attr(b, "action1") == action_id(2), "the pick must not need an attribute write"
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem")


def check_action_mode_pick_in_combat_is_queued_and_never_calls_setmulticastspell():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    n = len(mc_calls(lua))
    set_combat(lua, True)
    before = blocked(lua)
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    for event in ("SPELLS_CHANGED", "ACTIONBAR_SLOT_CHANGED", "UPDATE_MULTI_CAST_ACTIONBAR", "PLAYER_TOTEM_UPDATE"):
        fire(lua, event)
    assert blocked(lua) == before, "an attribute write was tried in combat"
    assert len(mc_calls(lua)) == n, f"SetMultiCastSpell was called in combat: {mc_calls(lua)[n:]}"
    # the button shows what the slot really holds, the pick is saved and waits
    assert b.icon._texture == 9000 + tid(lua, "Stoneskin Totem"), "the icon shows a pick that has not landed"
    assert b.fsPick.name == "Stoneskin Totem" and attr(b, "action1") == action_id(2)
    assert picks(lua).earth.name == "Tremor Totem", "the pick must be stored at once"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    calls = mc_calls(lua)
    assert calls[n:] == [(action_id(2), tid(lua, "Tremor Totem"), False)], calls
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem") and b.fsPick.name == "Tremor Totem"
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert len(mc_calls(lua)) == n + 1, "a pick that landed was sent again"


def check_a_blocked_setmulticastspell_never_shows_a_pick_that_did_not_land():
    # slot already holds the pick, so the tab is in action mode; the client then blocks every call (a no-op here)
    slot = f'__mc.slots[{action_id(2)}] = __ids["Stoneskin Totem"]; __mc.blocked = true'
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login=slot)
    b = by_key(lua, "earth")
    assert b.fsMode == "action" and mc_calls(lua) == []
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert len(mc_calls(lua)) == 1
    assert b.icon._texture == 9000 + tid(lua, "Stoneskin Totem"), "the icon shows a pick the slot never took"
    assert b.fsPick.name == "Stoneskin Totem" and b.fsMode == "action" and attr(b, "type1") == "action"
    advance(lua, 0.2)
    assert b.fsMode == "action", "judged before the slot had time to update"
    advance(lua, 2.0)                       # the verify timer: the slot never took it
    assert b.fsMode == "spell", f"mode {b.fsMode!r}: an element whose slot never takes a pick must fall back"
    assert attr(b, "type1") == "spell" and attr(b, "spell1") == "Tremor Totem" and attr(b, "action1") is None
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem"), "spell mode drops the saved pick"
    assert len(mc_calls(lua)) == 1, "the pick was sent again after it was given up"
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "spell" and len(mc_calls(lua)) == 1, "the element went back to action mode"
    assert tb(lua).Picker() is None or not shown(tb(lua).Picker())


def check_a_slot_that_updates_late_is_confirmed_by_the_slot_changed_event():
    slot = f'__mc.slots[{action_id(2)}] = __ids["Stoneskin Totem"]; __mc.delay = true'
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login=slot)
    b = by_key(lua, "earth")
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert b.icon._texture == 9000 + tid(lua, "Stoneskin Totem"), "shown before the slot read it back"
    lua.eval("__mc_flush")()
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem"), "the confirmed pick was not shown"
    assert b.fsMode == "action" and attr(b, "action1") == action_id(2)
    advance(lua, 5.0)
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "action" and len(mc_calls(lua)) == 1, "a confirmed pick was abandoned or resent"


def check_an_unfilled_multicast_slot_never_leaves_a_dead_action_button():
    # the fill is blocked: the slot stays empty, so the button must drop the spell, not an empty slot
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login="__mc.blocked = true")
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and attr(b, "type1") == "spell" and attr(b, "spell1") == "Stoneskin Totem", (
        f"{b.fsMode} {attr(b, 'type1')!r} {attr(b, 'action1')!r}")
    assert attr(b, "action1") is None
    assert len(mc_calls(lua)) == 1
    for _ in range(3):
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert len(mc_calls(lua)) == 1, "the fill was retried on every sync"
    advance(lua, 2.0)
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "spell" and attr(b, "type1") == "spell"
    fire(lua, "SPELLS_CHANGED")
    assert len(mc_calls(lua)) == 1 and b.fsMode == "spell", "the fill was retried after it was given up"
    # a fill that lands a moment late: spell mode until the slot shows it, then action mode
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login="__mc.delay = true")
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and attr(b, "type1") == "spell", "an unconfirmed fill left an action button"
    lua.eval("__mc_flush")()
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert b.fsMode == "action" and attr(b, "action1") == action_id(2) and attr(b, "spell1") is None
    assert len(mc_calls(lua)) == 1
    # a foreign spell in the slot is not a totem of the element: filled over, not pointed at
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login=f"__mc.slots[{action_id(2)}] = 424")
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Stoneskin Totem")
    # an unreadable slot cannot be verified: spell mode, no call
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login='__mc.infoMode = "secret"')
    assert by_key(lua, "earth").fsMode == "spell" and mc_calls(lua) == []


def check_the_action_id_comes_from_the_native_multicast_button_when_it_exists():
    # Earth is the first native button (SHAMAN_TOTEM_PRIORITIES), not the second
    lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"], lists=lists_for("earth", "fire"),
               pre_login="__native(200)")
    earth, fire_b = by_key(lua, "earth"), by_key(lua, "fire")
    assert attr(earth, "action1") == 201, f"earth action1 {attr(earth, 'action1')} (native button 1 = 201)"
    assert attr(fire_b, "action1") == 202, f"fire action1 {attr(fire_b, 'action1')} (native button 2 = 202)"
    assert sorted(c[0] for c in mc_calls(lua)) == [201, 202], mc_calls(lua)
    assert attr(earth, "action1") != action_id(2), "the formula was used with a native button present"
    # a native button that answers nothing usable falls back to the formula, which may ADOPT a slot that already
    # holds one of the element's totems (and never fills one: see the clobber check)
    held = f'__mc.slots[{action_id(2)}] = __ids["Stoneskin Totem"]'
    for broken in ("function() error('boom') end", "function() return __SECRET end", "function() return 'x' end"):
        lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
                   pre_login=f"__native(200); MultiCastActionButton1.CalculateAction = {broken}; {held}")
        assert attr(by_key(lua, "earth"), "action1") == action_id(2), broken
        assert mc_calls(lua) == [], broken
    # no priorities: the mapping cannot be told, formula
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
               pre_login=f"__native(200); SHAMAN_TOTEM_PRIORITIES = nil; {held}")
    assert attr(by_key(lua, "earth"), "action1") == action_id(2)


def check_a_throwing_setmulticastspell_is_queued_not_raised():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    lua.execute("__mc.throws = true")
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))      # must not raise
    assert by_key(lua, "earth").icon._texture == 9000 + tid(lua, "Stoneskin Totem"), "a pick that raised is shown"
    lua.execute("__mc.throws = false")
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Tremor Totem"), "the failed pick was not retried at regen"


def check_an_empty_multicast_slot_is_filled_with_the_pick_and_a_filled_one_is_adopted():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Stoneskin Totem"), "an empty slot was left empty"
    # a slot the native bar already filled wins: the tab shows it and does not overwrite it
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
               pre_login=f'__mc.slots[{action_id(2)}] = __ids["Tremor Totem"]')
    assert mc_calls(lua) == [], f"overwrote the native bar's pick: {mc_calls(lua)}"
    b = by_key(lua, "earth")
    assert b.icon._texture == 9000 + tid(lua, "Tremor Totem")
    assert picks(lua).earth.name == "Tremor Totem"


def check_the_arrow_and_alt_click_open_the_picker_and_alt_does_not_drop():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    assert b.fsArrow is not None and b.fsArrow._kind == "Button"
    assert tb(lua).Picker() is None or not shown(tb(lua).Picker())
    click(lua, b.fsArrow)
    picker = tb(lua).Picker()
    assert picker is not None and shown(picker), "the arrow did not open the picker"
    click(lua, b.fsArrow)
    assert not shown(picker), "the arrow did not close the open picker"
    lua.execute("__alt = true")
    click(lua, b, "LeftButton", True)
    assert not shown(picker), "the key DOWN of an Alt-click opened the picker (take only the release)"
    click(lua, b, "LeftButton", False)
    assert shown(picker), "Alt-click did not open the picker"
    lua.execute("__alt = false")
    tb(lua).ClosePicker()
    click(lua, b, "LeftButton", False)
    assert not shown(picker), "a plain click opened the picker"
    click(lua, b, "RightButton", False)
    assert not shown(picker), "a right click opened the picker"
    # locked elements have no arrow to open
    lua = boot()
    assert not by_key(lua, "fire").fsArrow._mouse, "a locked element's arrow takes the mouse"


def check_the_picker_lists_the_known_totems_and_a_click_picks_and_closes():
    lua = boot(learned=TOTEMS["earth"][:3], lists={2: TOTEMS["earth"][:3]})
    b = by_key(lua, "earth")
    tb(lua).OpenPicker("earth")
    picker = tb(lua).Picker()
    entries = [e for e in seq(picker.fsEntries) if shown(e)]
    ids = [int(e.fsSpellID) for e in entries]
    assert ids == [tid(lua, n) for n in TOTEMS["earth"][:3]], f"entries {ids}"
    click(lua, entries[1])
    assert not shown(picker), "a pick left the picker open"
    assert picks(lua).earth.name == "Earthbind Totem"
    assert mc_calls(lua)[-1][:2] == (action_id(2), tid(lua, "Earthbind Totem"))
    assert b.icon._texture == 9000 + tid(lua, "Earthbind Totem")


def check_the_picker_lists_known_spells_in_spell_mode_too():
    lua = boot(learned=["Earthbind Totem", "Tremor Totem"])
    tb(lua).OpenPicker("earth")
    entries = [e for e in seq(tb(lua).Picker().fsEntries) if shown(e)]
    assert [int(e.fsSpellID) for e in entries] == [tid(lua, "Earthbind Totem"), tid(lua, "Tremor Totem")]


def check_the_picker_is_plain_and_nothing_secure_depends_on_it():
    lua = all_known_with_lists()
    tb(lua).OpenPicker("earth")
    picker = tb(lua).Picker()
    assert picker._parent._name == "UIParent", f"picker parent {picker._parent._name}"
    assert not picker._secure and not picker._protected
    host = g(lua).FSTotemBar

    def descend(f, target):
        for r in seq(f._regions):
            if sb.same(lua, r, target) or descend(r, target):
                return True
        return False
    assert not descend(host, picker), "the picker is a descendant of the secure host"
    for f in g(lua).__frames.values():
        if f._secure or sb.same(lua, f, host):
            for p in seq(f._points):
                assert not sb.same(lua, p.rel, picker), f"{f._name} is anchored to the picker"
        assert not (f._secure and f._parent is not None and sb.same(lua, f._parent, picker)), "a secure frame under the picker"
    secure_under = [f for f in g(lua).__frames.values() if f._secure and descend(picker, f)]
    assert not secure_under, "a secure button inside the picker"


def check_the_picker_opens_and_picks_in_combat_without_a_protected_touch():
    lua = all_known_with_lists()
    set_combat(lua, True)
    before, touch = blocked(lua), int(g(lua).__protectedTouch)
    tb(lua).OpenPicker("water")
    picker = tb(lua).Picker()
    assert shown(picker), "the picker did not open in combat"
    entries = [e for e in seq(picker.fsEntries) if shown(e)]
    click(lua, entries[1])
    tb(lua).OpenPicker("fire")
    tb(lua).ClosePicker()
    assert blocked(lua) == before, "the picker caused a refused protected call"
    assert int(g(lua).__protectedTouch) == touch, "the picker touched a frame under a protected parent in combat"


def check_the_picker_follows_the_element_and_closes_when_the_mouse_leaves():
    lua = all_known_with_lists()
    tb(lua).OpenPicker("air")
    picker = tb(lua).Picker()
    entries = [e for e in seq(picker.fsEntries) if shown(e)]
    assert [int(e.fsSpellID) for e in entries] == [tid(lua, n) for n in TOTEMS["air"]]
    assert sb.same(lua, picker.fsOwner, by_key(lua, "air")), "the picker is not owned by the air button"
    tb(lua).OpenPicker("fire")
    entries = [e for e in seq(picker.fsEntries) if shown(e)]
    assert [int(e.fsSpellID) for e in entries] == [tid(lua, n) for n in TOTEMS["fire"]], "stale entries"
    # the mouse is nowhere near: the idle timer closes it
    onupdate = picker._scripts.OnUpdate
    assert onupdate is not None, "no idle close"
    for _ in range(40):
        onupdate(picker, 0.1)
    assert not shown(picker), "the picker stayed open with the mouse away"
    tb(lua).OpenPicker("fire")
    picker._mouseOver = True
    for _ in range(40):
        picker._scripts.OnUpdate(picker, 0.1)
    assert shown(picker), "the picker closed under the mouse"


def check_attribute_writes_wait_out_combat_and_replay_at_regen():
    lua = boot(learned=[])
    set_combat(lua, True)
    before = blocked(lua)
    lua.execute('__know("Stoneskin Totem"); __spell("Totemic Recall", 36936, true)')
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
        fire(lua, event)
    assert blocked(lua) == before, "a protected write was tried in combat"
    assert by_key(lua, "earth").fsLocked and attr(by_key(lua, "earth"), "type1") is None
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert attr(by_key(lua, "earth"), "spell1") == "Stoneskin Totem" and not by_key(lua, "recall").fsLocked


def check_a_login_in_combat_builds_at_regen():
    lua = boot(learned=TOTEMS["earth"], combat=True)
    assert btn(lua, 1) is None, "built a secure frame in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert btn(lua, 1) is not None and attr(by_key(lua, "earth"), "spell1") == "Stoneskin Totem"


def check_combat_never_creates_moves_resizes_shows_or_hides_a_secure_frame():
    lua = all_known_with_lists()
    host = g(lua).FSTotemBar
    snap = [(b._w, b._h, len(b._points), bool(b._shown)) for b in [btn(lua, i) for i in range(1, 7)]]
    set_combat(lua, True)
    before, touch = blocked(lua), int(g(lua).__protectedTouch)
    n_frames = len(g(lua).__frames)
    for event in ("SPELLS_CHANGED", "PLAYER_TOTEM_UPDATE", "SPELL_UPDATE_COOLDOWN", "UPDATE_BINDINGS",
                  "ACTIONBAR_SLOT_CHANGED", "PLAYER_LEVEL_UP"):
        fire(lua, event)
    lua.eval("__rescale")(1.0)
    csh.console(lua).SetActive(False)
    csh.console(lua).SetActive(True)
    assert blocked(lua) == before, "a protected call was tried in combat"
    assert int(g(lua).__protectedTouch) == touch, "a frame under a protected parent was touched in combat"
    assert [(b._w, b._h, len(b._points), bool(b._shown)) for b in [btn(lua, i) for i in range(1, 7)]] == snap
    assert host._shown


def check_cooldown_swipes_follow_the_picked_totem_by_duration_object():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    assert b.cooldown is not None and b.totemCooldown is not None and not sb.same(lua, b.totemCooldown, b.cooldown)
    sid = tid(lua, "Stoneskin Totem")
    sb.set_cd(lua, sid, 100, 1)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sb.cd_of(b) == ("obj", sid), f"swipe {sb.cd_of(b)}"
    s = by_key(lua, "set")
    sb.set_cd(lua, CALL, 100, 3)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sb.cd_of(s) == ("obj", CALL), f"set swipe {sb.cd_of(s)}"
    set_combat(lua, True)
    before = blocked(lua)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert blocked(lua) == before


def sweep_of(b):
    sw = b.totemCooldown
    if sw._cdObj is not None:
        return ("obj", int(sw._cdObj.totemFor))
    if sw._cd is not None:
        return ("times", int(sw._cd[1]), int(sw._cd[2]))
    return None


def check_the_live_totem_sweep_reads_the_totem_when_plain_and_skips_it_when_secret():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    lua.execute('__tot[2] = { "Stoneskin Totem", 500, 300 }')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("times", 500, 300), sweep_of(b)
    lua.execute("__tot[2] = nil")
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) is None, f"stale sweep {sweep_of(b)}"
    # secret in combat with the totem standing: GetTotemInfo is unreadable, the duration object answers
    lua.execute('__tot[2] = { "Stoneskin Totem", 500, 300 }; __totMode = "secret"')
    set_combat(lua, True)
    fire(lua, "PLAYER_TOTEM_UPDATE")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert sweep_of(b) == ("obj", 2), f"secret answer: {sweep_of(b)}"
    # GetTotemInfo throws: same
    lua.execute('__totMode = "throw"')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"throwing GetTotemInfo: {sweep_of(b)}"
    # nothing readable at all while the sweep runs: it is left alone
    lua.execute('__totMode = "secret"; GetTotemDuration = function() return __SECRET end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"unreadable everything cleared the sweep: {sweep_of(b)}"
    lua.execute('GetTotemDuration = function() error("boom") end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"a throwing GetTotemDuration cleared the sweep: {sweep_of(b)}"
    # the totem is gone and nothing is readable but the duration object is plainly nil: the stale sweep clears
    lua.execute('__tot[2] = nil; GetTotemDuration = function() return nil end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) is None, f"a stale sweep survived a nil duration object: {sweep_of(b)}"


def check_plain_zero_totem_times_in_combat_are_unknown_not_no_totem():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    lua.execute('__tot[2] = { "Stoneskin Totem", 500, 300 }')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("times", 500, 300)
    # combat: GetTotemInfo answers true, "", 0, 0, 0 for the standing totem; the object has the real times
    set_combat(lua, True)
    lua.execute('__totMode = "zeros"')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"plain zeros cleared or kept a wrong sweep: {sweep_of(b)}"
    # even with no object to read, a totem GetTotemInfo says stands is not cleared on its zeros
    lua.execute('__totObjNil = true')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"zeros with a standing totem cleared the sweep: {sweep_of(b)}"
    # the totem really goes: GetTotemInfo says false and the sweep clears
    lua.execute('__tot[2] = nil; __totMode = nil')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) is None, f"{sweep_of(b)}"
    # plain zero times from GetTotemInfo outside combat while the duration object answers: the object wins
    lua = all_known_with_lists()
    b = by_key(lua, "fire")
    lua.execute('__tot[1] = { "Searing Totem", 0, 0 }')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 1), f"{sweep_of(b)}"


def check_alt_modified_clicks_carry_an_empty_type_and_open_the_picker():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    for name in ("alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1"):
        assert name in b._attrs and attr(b, name) == "", f"{name} = {attr(b, name)!r}: that click would drop"
    # Blizzard's SecureTemplates builds alt-ctrl-shift- only; a ctrl-alt spelling can never match
    for name in b._attrs:
        assert not str(name).startswith("ctrl-alt"), f"useless attribute {name}"
    # spell mode carries the same empties
    lua = boot(learned=TOTEMS["earth"])
    for name in ("alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1"):
        assert attr(by_key(lua, "earth"), name) == "", name
    # whatever else is held, an Alt-click release opens the picker
    lua.execute("IsShiftKeyDown = function() return true end; IsControlKeyDown = function() return true end")
    lua.execute("__alt = true")
    click(lua, by_key(lua, "earth"), "LeftButton", False)
    assert shown(tb(lua).Picker()), "Alt+Ctrl+Shift click did not open the picker"


def check_spell_attributes_use_the_localized_totem_name():
    loc = 'Totem de Peau de Pierre'
    lua = boot(learned=TOTEMS["earth"],
               pre_login=f'__idNames[__ids["Stoneskin Totem"]] = "{loc}"')
    b = by_key(lua, "earth")
    assert attr(b, "spell1") == loc, f"spell1 {attr(b, 'spell1')!r}"
    tb(lua).OpenPicker("earth")
    labels = [e.fsLabel._text for e in seq(tb(lua).Picker().fsEntries) if shown(e)]
    assert labels[0] == loc, labels
    lua.eval("__Region.Fire")(b, "OnEnter")
    text = " | ".join(str(x) for x in seq(g(lua).GameTooltip._lines))
    assert loc in text and "Stoneskin" not in text, text
    # the saved pick is the id, so it survives a renamed spell
    tb(lua).Pick("earth", tid(lua, "Stoneskin Totem"))
    fire(lua, "SPELLS_CHANGED")
    assert attr(b, "spell1") == loc


def check_the_saved_pick_is_written_only_by_a_user_pick_or_an_adopted_slot():
    # the default (first known totem) is never saved
    lua = boot(learned=["Tremor Totem"])
    assert picks(lua) is None, f"a default pick was saved: {picks(lua)}"
    # a spellbook that finishes loading later: the default moves to the first known totem, nothing was pinned
    lua.execute('__know("Stoneskin Totem")')
    fire(lua, "SPELLS_CHANGED")
    assert attr(by_key(lua, "earth"), "spell1") == "Stoneskin Totem", "the partly loaded default stuck"
    assert picks(lua) is None
    # the same in action mode with an empty slot we fill with the default
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Stoneskin Totem")
    assert picks(lua) is None, f"our own default fill was saved: {picks(lua)}"
    # a user pick is saved; a slot the native bar already held is adopted and saved
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert picks(lua).earth.name == "Tremor Totem"
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
               pre_login=f'__mc.slots[{action_id(2)}] = __ids["Earthbind Totem"]')
    assert picks(lua).earth.name == "Earthbind Totem"
    # the native bar changes the slot later: adopted again
    lua.execute(f'__mc.slots[{action_id(2)}] = __ids["Tremor Totem"]')
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert picks(lua).earth.name == "Tremor Totem"


def check_the_header_no_longer_claims_a_blocked_call_is_dropped_silently():
    text = TOTEMBAR.read_text(encoding="utf-8")
    assert "dropped, not raised" not in text, "the header still says a blocked call is silently dropped"
    assert "NEVER called in combat" in text


def check_tooltip_text_and_the_unlock_hint():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    lua.eval("__Region.Fire")(b, "OnEnter")
    lines = [str(x) for x in seq(g(lua).GameTooltip._lines)]
    text = " | ".join(lines)
    assert "Stoneskin Totem" in text, text
    assert "Left click: drop Stoneskin Totem. Right click: dismiss. Alt-click or arrow: change totem." in text, text
    lua.eval("__Region.Fire")(b, "OnLeave")
    assert not shown(g(lua).GameTooltip)
    lua = boot()
    f = by_key(lua, "fire")
    lua.eval("__Region.Fire")(f, "OnEnter")
    text = " | ".join(str(x) for x in seq(g(lua).GameTooltip._lines))
    assert "level 10" in text, text


def check_hotkey_text_and_quick_keybind_commands():
    lua = all_known_with_lists()
    for i in range(1, 7):
        b = btn(lua, i)
        assert b.commandName == f"CLICK FSTotemButton{i}:LeftButton", f"{i}: {b.commandName!r}"
        assert b.fsQuickKeybindOverlay is not None
        for script in ("OnClick", "OnShow", "OnHide"):
            assert len([h for h in seq(b._hooks[script])]) >= 1
    g(lua).__bindings["CLICK FSTotemButton3:LeftButton"] = "SHIFT-F"
    fire(lua, "UPDATE_BINDINGS")
    b = btn(lua, 3)
    assert shown(b.HotKey) and b.HotKey._text == "SHIFT-F", f"hotkey {b.HotKey._text!r}"
    g(lua).__bindings["CLICK FSTotemButton3:LeftButton"] = None
    lua.eval("__trigger")("KeybindListener.RebindSuccess")
    assert not shown(b.HotKey)


def check_bindings_xml_declares_six_totem_commands_after_the_seals():
    root = ET.parse(BINDINGS).getroot()
    names = [b.get("name") for b in root.findall("Binding")]
    want = [f"CLICK FSSealButton{i}:LeftButton" for i in range(1, 8)] + [
        f"CLICK FSTotemButton{i}:LeftButton" for i in range(1, 7)]
    assert names == want, f"binding names {names}"
    items = root.findall("Binding")
    assert all(b.get("category") == "ADDONS" for b in items)
    assert [b.get("header") for b in items if b.get("header")] == ["FOREVERSTUWAVE"], "only the first has a header"


def check_binding_labels_exist_for_every_class():
    for klass in ("SHAMAN", "PALADIN", "WARRIOR"):
        lua = boot(klass=klass)
        for i, label in enumerate(LABELS, 1):
            text = g(lua)[f"BINDING_NAME_CLICK FSTotemButton{i}:LeftButton"]
            assert text == label, f"{klass}: label {i} is {text!r}, want {label!r}"


def check_the_shoulder_is_the_six_by_one_block_and_the_buttons_sit_inside_it(scale):
    lua = boot(scale, learned=TOTEMS["earth"])
    s = csh.shoulder(lua)
    assert s is not None and csh.cs(lua).IsShown(), "no Shaman shoulder stands"
    w = 2 * MU["PAD"] + 6 * MU["BTN"] + 5 * MU["BG"]
    h = MU["PT"] + MU["BTN"] + MU["PB"]
    approx(w, 264.0, "block width"), approx(h, 49.0, "block height")
    d = csh.D(lua, s.art)
    approx(d["w"], w, "art width in design px", 0.01), approx(d["h"], h, "art height in design px", 0.01)
    approx(d["x"], MU["DX"], "art left", 0.5)
    bw, bh, edge = csh.cs(lua).BlockSize()
    approx(bw, w * scale, "BlockSize width"), approx(bh, h * scale, "BlockSize height")
    host = g(lua).FSTotemBar
    p = host._points[1]
    assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT")
    approx(p.x, MU["DX"] * scale, "host x", 0.5 * scale), approx(p.y, 0, "host y")
    for col in range(1, 7):
        b = btn(lua, col)
        q = b._points[1]
        assert sb.same(lua, q.rel, host) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT")
        approx(q.x, (MU["PAD"] + (col - 1) * PITCH) * scale, f"button {col} x")
        approx(q.y, MU["PB"] * scale, f"button {col} y")
        approx(b._w, MU["BTN"] * scale, f"button {col} width"), approx(b._h, MU["BTN"] * scale, f"button {col} height")
    assert host._level > sb.top_level(g(lua).FSConsole), "the buttons must draw above the chassis"
    assert host._shown


def check_no_secure_frame_is_anchored_to_the_shoulder_art():
    lua = boot(learned=TOTEMS["earth"])
    art = csh.shoulder(lua).art
    for f in g(lua).__frames.values():
        if f._secure or f._name == "FSTotemBar":
            for p in seq(f._points):
                assert not sb.same(lua, p.rel, art), f"{f._name} is anchored to the art"
            assert f._parent is None or not sb.same(lua, f._parent, art)


def check_the_stance_bar_keeps_ghost_wolf_and_the_tab_takes_no_forms():
    lua = boot(learned=TOTEMS["earth"])
    assert not g(lua).FS.SealBar.OwnsForms()
    assert g(lua).FSStanceBar._shown and g(lua).FSStanceButton1._shown, "a Shaman lost its stance bar"
    assert not g(lua).FS.StanceBar.OwnsShoulder()
    assert csh.cs(lua).IsShown(), "the totem tab wants the shoulder"
    # a Shaman with no forms: the tab still stands
    lua = boot(learned=TOTEMS["earth"], pre_login="GetNumShapeshiftForms = function() return 0 end")
    assert csh.cs(lua).IsShown()


def check_the_tab_follows_the_console_on_and_off():
    lua = boot(learned=TOTEMS["earth"])
    host = g(lua).FSTotemBar
    csh.console(lua).SetActive(False)
    assert not csh.cs(lua).IsShown()
    p = host._points[1]
    assert p.rel._name == "FSStanceBar" and p.relPoint == "TOPLEFT", f"Console off: {p.rel._name}"
    assert host._shown and shown(btn(lua, 1))
    csh.console(lua).SetActive(True)
    assert csh.cs(lua).IsShown() and host._points[1].rel._name == "FSConsole"
    # no Console at all: still a seat, no crash
    lua = boot(learned=TOTEMS["earth"], console=False)
    assert g(lua).FSTotemBar._shown


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = boot(1.0, learned=TOTEMS["earth"])
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    approx(btn(lua, 2)._w, MU["BTN"] * s, "button width after a rescale")
    q = btn(lua, 2)._points[1]
    approx(q.x, (MU["PAD"] + PITCH) * s, "button 2 x after a rescale")


def check_no_bar_field_and_no_useparent_attributes_on_any_button():
    # Blizzard's SecureButton_GetModifiedAttribute reads frame.bar and the useparent-* attributes during a
    # secure click; an addon written value there taints the click. Every button carries explicit attributes.
    lua = all_known_with_lists()
    for i in range(1, 7):
        b = btn(lua, i)
        assert b.bar is None, f"button {i} carries a .bar field"
        for name, value in b._attrs.items():
            assert not str(name).startswith("useparent"), f"button {i} carries {name}"
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    for i in range(1, 7):
        assert btn(lua, i).bar is None
    text = TOTEMBAR.read_text(encoding="utf-8")
    assert not re.search(r"\.bar\s*=", text), "TotemBar.lua writes a .bar field"
    assert "useparent" not in text, "TotemBar.lua mentions a useparent attribute"


def warnings(lua) -> int:
    return int(g(lua).__degradeCount)


def check_a_delayed_fill_is_never_saved_as_the_users_pick():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login="__mc.delay = true")
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and picks(lua) is None, f"{b.fsMode} {picks(lua)}"
    lua.eval("__mc_flush")()
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert b.fsMode == "action" and attr(b, "action1") == action_id(2)
    assert picks(lua) is None, f"the tab's own default fill was saved as the user's pick: {picks(lua)}"
    fire(lua, "SPELLS_CHANGED")
    assert picks(lua) is None, f"a later sync saved the default fill: {picks(lua)}"
    # the user's own pick is saved, and a native change adopted after it
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    lua.eval("__mc_flush")()
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert picks(lua).earth.name == "Tremor Totem"


def check_a_persistently_raising_setmulticastspell_gives_up_after_two_tries_with_one_warning():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), pre_login="__mc.throws = true")
    b = by_key(lua, "earth")
    # the login syncs twice, so both attempts (the limit) are spent before any timer runs
    assert b.fsMode == "spell" and len(mc_calls(lua)) == 2, f"{b.fsMode} {len(mc_calls(lua))}"
    assert warnings(lua) == 1, f"{warnings(lua)} warnings after giving up"
    advance(lua, 1.5)
    for _ in range(4):
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "ACTIONBAR_SLOT_CHANGED")
        fire(lua, "PLAYER_REGEN_ENABLED")
        advance(lua, 2.0)
    assert len(mc_calls(lua)) == 2, f"retried a raising call forever: {len(mc_calls(lua))} calls"
    assert warnings(lua) == 1 and b.fsMode == "spell" and attr(b, "spell1") == "Stoneskin Totem"
    # a pick whose send raised twice is resolved: spell mode with the pick saved, not pending forever
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    lua.execute("__mc.throws = true")
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert b.fsMode == "action" and len(mc_calls(lua)) == 2, "the first failure is retried once"
    advance(lua, 1.5)
    assert len(mc_calls(lua)) == 3, f"{len(mc_calls(lua))} calls"
    assert b.fsMode == "spell" and attr(b, "spell1") == "Tremor Totem", f"{b.fsMode} {attr(b, 'spell1')!r}"
    assert picks(lua).earth.name == "Tremor Totem" and warnings(lua) == 1
    for _ in range(3):
        fire(lua, "PLAYER_REGEN_ENABLED")
        fire(lua, "SPELLS_CHANGED")
        advance(lua, 2.0)
    assert len(mc_calls(lua)) == 3, "a resolved pick was sent again"


def check_below_the_multicast_bar_the_tab_uses_spell_mode_without_trying_or_warning():
    lua = boot(learned=["Stoneskin Totem"], lists=lists_for("earth"), pre_login="__mc.hasBar = false")
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and attr(b, "type1") == "spell" and attr(b, "spell1") == "Stoneskin Totem"
    for _ in range(3):
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "ACTIONBAR_SLOT_CHANGED")
        advance(lua, 2.0)
    assert mc_calls(lua) == [], f"SetMultiCastSpell called below the bar: {mc_calls(lua)}"
    assert warnings(lua) == 0, "warned about a bar that does not exist yet"
    # the picker and a pick are spell mode too
    tb(lua).Pick("earth", tid(lua, "Stoneskin Totem"))
    assert mc_calls(lua) == [] and warnings(lua) == 0
    # learning Call of the Elements brings the bar: one action mode attempt
    lua.execute("__mc.hasBar = true; __learned[66842] = true")
    fire(lua, "SPELLS_CHANGED")
    assert b.fsMode == "action" and attr(b, "action1") == action_id(2) and len(mc_calls(lua)) == 1, (
        f"{b.fsMode} {len(mc_calls(lua))} calls: one fill of the empty slot")
    # without HasMultiCastActionBar (or with a useless answer) the Call of the Elements decides
    for label, setup in (("missing", "HasMultiCastActionBar = nil"), ("throws", '__mc.hasBarMode = "throw"'),
                         ("secret", '__mc.hasBarMode = "secret"')):
        lua = boot(learned=["Stoneskin Totem"], lists=lists_for("earth"), pre_login=setup)
        assert by_key(lua, "earth").fsMode == "spell" and mc_calls(lua) == [], f"{label}: no Call, no bar"
        assert warnings(lua) == 0, label
        lua.execute("__learned[66842] = true")
        fire(lua, "SPELLS_CHANGED")
        assert by_key(lua, "earth").fsMode == "action", f"{label}: Call known, bar expected"
    lua = boot(learned=["Stoneskin Totem"], lists=lists_for("earth"), spells=("Call of the Elements",),
               pre_login='__mc.hasBarMode = "number"; __mc.hasBar = false')
    assert by_key(lua, "earth").fsMode == "spell" and mc_calls(lua) == [], "a numeric 0 answer means no bar"


def check_a_learn_event_allows_one_fresh_multicast_attempt_after_a_give_up():
    # the slot never takes the fill: spell mode for good, until something is learned
    lua = boot(learned=TOTEMS["earth"][:1], lists={2: TOTEMS["earth"][:1]}, pre_login="__mc.blocked = true")
    b = by_key(lua, "earth")
    advance(lua, 2.0)
    fire(lua, "SPELLS_CHANGED")
    assert len(mc_calls(lua)) == 1 and b.fsMode == "spell" and warnings(lua) == 1
    for _ in range(3):
        fire(lua, "SPELLS_CHANGED")
        advance(lua, 2.0)
    assert len(mc_calls(lua)) == 1, "retried without a learn event"
    # a level up: one fresh attempt, which now works
    lua.execute("__mc.blocked = false")
    fire(lua, "PLAYER_LEVEL_UP")
    assert len(mc_calls(lua)) == 2 and b.fsMode == "action", f"{len(mc_calls(lua))} calls, {b.fsMode}"
    # a new totem learned: the known set changed, one fresh attempt
    lua = boot(learned=TOTEMS["earth"][:1], lists={2: TOTEMS["earth"][:1]}, pre_login="__mc.blocked = true")
    b = by_key(lua, "earth")
    advance(lua, 2.0)
    fire(lua, "SPELLS_CHANGED")
    assert len(mc_calls(lua)) == 1 and b.fsMode == "spell"
    lua.execute('__mc.blocked = false; __know("Earthbind Totem"); __mc_list(2, {"Stoneskin Totem", "Earthbind Totem"})')
    fire(lua, "SPELLS_CHANGED")
    assert len(mc_calls(lua)) == 2 and b.fsMode == "action", f"{len(mc_calls(lua))} calls, {b.fsMode}"
    # an unrelated event with nothing new does not retry
    lua = boot(learned=TOTEMS["earth"][:1], lists={2: TOTEMS["earth"][:1]}, pre_login="__mc.blocked = true")
    advance(lua, 2.0)
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert len(mc_calls(lua)) == 1


def check_a_formula_action_id_is_adopted_never_filled_and_another_elements_totem_is_a_mapping_error():
    # formula only (no native multi-cast button): an empty slot is not ours to write
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), native=False)
    b = by_key(lua, "earth")
    assert b.fsMode == "spell" and mc_calls(lua) == [], f"{b.fsMode} {mc_calls(lua)}"
    assert warnings(lua) == 0
    # ... but it adopts a slot that already holds the element's own totem
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), native=False,
               pre_login=f'__mc.slots[{action_id(2)}] = __ids["Earthbind Totem"]')
    b = by_key(lua, "earth")
    assert b.fsMode == "action" and attr(b, "action1") == action_id(2) and mc_calls(lua) == []
    assert picks(lua).earth.name == "Earthbind Totem"
    # a slot holding ANOTHER element's totem (Searing, listed for Fire): no write, spell mode, one warning
    for native in (False, True):
        lua = boot(learned=TOTEMS["earth"] + TOTEMS["fire"], lists=lists_for("earth", "fire"), native=native,
                   pre_login=f'__mc.slots[{action_id(2)}] = __ids["Searing Totem"]')
        b = by_key(lua, "earth")
        assert b.fsMode == "spell" and attr(b, "spell1") == "Stoneskin Totem", f"native={native}: {b.fsMode}"
        assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Searing Totem"), f"native={native}: slot rewritten"
        assert action_id(2) not in [c[0] for c in mc_calls(lua)], f"native={native}: wrote the foreign slot"
        assert warnings(lua) == 1, f"native={native}: {warnings(lua)} warnings"
    # the other element's totem is told from the static table too, with no multi-cast list for that element
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), native=False,
               pre_login=f'__mc.slots[{action_id(2)}] = __ids["Searing Totem"]')
    assert by_key(lua, "earth").fsMode == "spell" and mc_calls(lua) == []
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Searing Totem")


def check_a_slot_event_inside_the_call_does_not_send_the_fill_again():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
               pre_login="__mc.reenter = 'ACTIONBAR_SLOT_CHANGED'")
    assert len(mc_calls(lua)) == 1, f"the fill was sent {len(mc_calls(lua))} times"
    assert by_key(lua, "earth").fsMode == "action"
    # the same for a pick
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    lua.execute("__mc.reenter = 'ACTIONBAR_SLOT_CHANGED'")
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    assert len(mc_calls(lua)) == 2, f"the pick was sent {len(mc_calls(lua)) - 1} times"
    assert by_key(lua, "earth").icon._texture == 9000 + tid(lua, "Tremor Totem")


def check_a_native_slot_change_beats_a_queued_pick():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    n = len(mc_calls(lua))
    set_combat(lua, True)
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    # the slot still reads what it held: nothing to do
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    # the native bar sets another totem, then combat ends: our queued pick must not overwrite it
    lua.execute(f'__mc.slots[{action_id(2)}] = __ids["Earthbind Totem"]')
    fire(lua, "ACTIONBAR_SLOT_CHANGED")
    assert picks(lua).earth.name == "Earthbind Totem", f"pick {picks(lua).earth.name}"
    assert b.icon._texture == 9000 + tid(lua, "Earthbind Totem")
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert len(mc_calls(lua)) == n, f"the queued pick overwrote the native choice: {mc_calls(lua)[n:]}"
    assert int(g(lua).__mc.slots[action_id(2)]) == tid(lua, "Earthbind Totem")


def check_a_plain_false_totem_info_clears_the_sweep_before_the_duration_object_is_asked():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    lua.execute('__tot[2] = { "Stoneskin Totem", 500, 300 }')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("times", 500, 300)
    # no totem stands, yet the duration object still answers (a stale object): the sweep clears
    lua.execute('__tot[2] = nil; GetTotemDuration = function() return { totemFor = 2 } end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) is None, f"a stale duration object kept the sweep alive: {sweep_of(b)}"
    # a secret duration object next to an unreadable GetTotemInfo is left alone
    lua.execute('__tot[2] = { "Stoneskin Totem", 500, 300 }; __totMode = "secret"; GetTotemDuration = function() return { totemFor = 2 } end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2)
    lua.execute('GetTotemDuration = function() return __SECRET end')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    assert sweep_of(b) == ("obj", 2), f"a secret duration object cleared the sweep: {sweep_of(b)}"


def check_totems_are_looked_up_by_spell_id_not_by_english_name():
    # a localized client: the English name resolves to nothing, the id and the localized name do
    loc = "Totem de Peau de Pierre"
    sid = TOTEM_IDS["Stoneskin Totem"]
    setup = f'__spells["Stoneskin Totem"] = nil; __spells["{loc}"] = {sid}; __idNames[{sid}] = "{loc}"'
    lua = boot(learned=["Stoneskin Totem"], pre_login=setup)
    b = by_key(lua, "earth")
    assert not b.fsLocked, "a known totem stayed locked because its English name does not resolve"
    assert attr(b, "spell1") == loc, f"spell1 {attr(b, 'spell1')!r}"
    assert int(b.fsPick.id) == sid
    # a higher rank is known, rank 1 is not (any rank counts); the pick is that rank under the same localized name
    rank2 = 99001
    setup = (f'__spells["Stoneskin Totem"] = nil; __spells["{loc}"] = {rank2}; __idNames[{sid}] = "{loc}"; '
             f'__idNames[{rank2}] = "{loc}"; __learned[{sid}] = nil; __learned[{rank2}] = true')
    lua = boot(learned=[], pre_login=setup)
    b = by_key(lua, "earth")
    assert not b.fsLocked and attr(b, "spell1") == loc and int(b.fsPick.id) == rank2, (
        f"{b.fsLocked} {attr(b, 'spell1')!r} {b.fsPick and b.fsPick.id}")
    # an unknown totem stays locked, whatever the names do
    lua = boot(learned=[], pre_login=f'__spells["Stoneskin Totem"] = nil; __idNames[{sid}] = "{loc}"')
    assert by_key(lua, "earth").fsLocked
    # the static table is spell ids
    text = TOTEMBAR.read_text(encoding="utf-8")
    assert "ResolveSpell(name)" in text and re.search(r"\{ 8071, \"Stoneskin Totem\" \}", text), "no static id table"


def check_a_throwing_secret_or_missing_api_never_breaks_a_sync():
    for mode in ("throw", "secret"):
        lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"),
                   pre_login=f'__mc.infoMode = "{mode}"; __totMode = "{mode}"')
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "PLAYER_TOTEM_UPDATE")
        b = by_key(lua, "earth")
        # an unreadable multi-cast slot cannot be verified: spell mode, nothing sent
        assert b.fsMode == "spell" and attr(b, "spell1") == "Stoneskin Totem", f"{mode}: {b.fsMode}"
        assert mc_calls(lua) == [], f"{mode}: sent a pick to a slot it cannot read"
        # no totem stands and nothing is readable: the sweep is empty
        assert b.totemCooldown._cd is None and b.totemCooldown._cdObj is None, f"{mode}: sweep not clear"
    lua = boot(learned=TOTEMS["earth"], pre_login="IsPlayerSpell = nil")
    assert not by_key(lua, "earth").fsLocked      # a name that resolves counts as known with no spellbook API
    lua = boot(learned=TOTEMS["earth"], pre_login='GetTotemInfo = nil; GetTotemDuration = nil')
    fire(lua, "PLAYER_TOTEM_UPDATE")
    lua = boot(learned=TOTEMS["earth"], pre_login="UnitGUID = function() error('boom') end")
    assert attr(by_key(lua, "earth"), "spell1") == "Stoneskin Totem", "no GUID: the default pick must still work"


def check_picks_are_kept_per_character():
    lua = boot(learned=TOTEMS["earth"])
    tb(lua).Pick("earth", tid(lua, "Tremor Totem"))
    db = g(lua).ForeverSTUwaveDB
    assert db.totemPicks[GUID] is not None
    lua.execute('ForeverSTUwaveDB.totemPicks["Player-9-OTHER"] = '
                f'{{ earth = {{ id = {TOTEM_IDS["Stoneskin Totem"]}, name = "Stoneskin Totem" }} }}')
    fire(lua, "SPELLS_CHANGED")
    assert attr(by_key(lua, "earth"), "spell1") == "Tremor Totem", "another character's pick leaked in"


def check_the_file_uses_no_snippets_and_no_state_drivers():
    text = TOTEMBAR.read_text(encoding="utf-8")
    for needle in ("RegisterStateDriver", "SecureHandler", "WrapScript", ":Execute(", "SetFrameRef"):
        assert needle not in text, f"TotemBar.lua mentions {needle}"


def check_toc_lists_the_totem_bar_after_the_seal_bar():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    t = "Modules/ActionBars/TotemBar.lua"
    assert t in mods, "TotemBar.lua is not in the .toc"
    for dep in ("Modules/ActionBars/StanceBar.lua", "Modules/ActionBars/ClassShoulder.lua",
                "Modules/ActionBars/SealBar.lua", "Modules/Pet/PetDock.lua", "Core/FrameHelpers.lua"):
        assert mods.index(dep) < mods.index(t), f"{dep} must load before TotemBar.lua"


def check_no_em_dashes_in_the_new_files():
    for path in (TOTEMBAR, Path(__file__), HERE / "assets" / "generate_totem_glyphs.py"):
        assert path.exists(), f"{path} is missing"
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), f"{path.name} has an em dash"


CHECKS = [
    check_six_named_secure_buttons_in_the_fixed_order_built_once,
    check_only_a_shaman_gets_a_tab,
    check_action_mode_when_the_multicast_bar_is_usable,
    check_spell_mode_when_there_is_no_usable_multicast_bar,
    check_no_multicast_api_at_all_degrades_to_spell_mode,
    check_a_mode_change_rewrites_the_attributes_cleanly,
    check_locked_buttons_carry_nothing_castable_and_dim_by_alpha,
    check_learning_a_totem_unlocks_just_that_element,
    check_set_and_recall_buttons,
    check_default_pick_is_the_first_known_totem_and_a_stale_pick_falls_back,
    check_spell_mode_pick_out_of_combat_writes_at_once_and_stores_it,
    check_spell_mode_pick_in_combat_waits_for_regen,
    check_action_mode_pick_calls_setmulticastspell_and_stores_it,
    check_action_mode_pick_in_combat_is_queued_and_never_calls_setmulticastspell,
    check_a_blocked_setmulticastspell_never_shows_a_pick_that_did_not_land,
    check_a_slot_that_updates_late_is_confirmed_by_the_slot_changed_event,
    check_an_unfilled_multicast_slot_never_leaves_a_dead_action_button,
    check_the_action_id_comes_from_the_native_multicast_button_when_it_exists,
    check_a_throwing_setmulticastspell_is_queued_not_raised,
    check_an_empty_multicast_slot_is_filled_with_the_pick_and_a_filled_one_is_adopted,
    check_the_arrow_and_alt_click_open_the_picker_and_alt_does_not_drop,
    check_the_picker_lists_the_known_totems_and_a_click_picks_and_closes,
    check_the_picker_lists_known_spells_in_spell_mode_too,
    check_the_picker_is_plain_and_nothing_secure_depends_on_it,
    check_the_picker_opens_and_picks_in_combat_without_a_protected_touch,
    check_the_picker_follows_the_element_and_closes_when_the_mouse_leaves,
    check_attribute_writes_wait_out_combat_and_replay_at_regen,
    check_a_login_in_combat_builds_at_regen,
    check_combat_never_creates_moves_resizes_shows_or_hides_a_secure_frame,
    check_cooldown_swipes_follow_the_picked_totem_by_duration_object,
    check_the_live_totem_sweep_reads_the_totem_when_plain_and_skips_it_when_secret,
    check_plain_zero_totem_times_in_combat_are_unknown_not_no_totem,
    check_alt_modified_clicks_carry_an_empty_type_and_open_the_picker,
    check_spell_attributes_use_the_localized_totem_name,
    check_the_saved_pick_is_written_only_by_a_user_pick_or_an_adopted_slot,
    check_the_header_no_longer_claims_a_blocked_call_is_dropped_silently,
    check_tooltip_text_and_the_unlock_hint,
    check_hotkey_text_and_quick_keybind_commands,
    check_bindings_xml_declares_six_totem_commands_after_the_seals,
    check_binding_labels_exist_for_every_class,
    check_no_secure_frame_is_anchored_to_the_shoulder_art,
    check_the_stance_bar_keeps_ghost_wolf_and_the_tab_takes_no_forms,
    check_the_tab_follows_the_console_on_and_off,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_no_bar_field_and_no_useparent_attributes_on_any_button,
    check_a_delayed_fill_is_never_saved_as_the_users_pick,
    check_a_persistently_raising_setmulticastspell_gives_up_after_two_tries_with_one_warning,
    check_below_the_multicast_bar_the_tab_uses_spell_mode_without_trying_or_warning,
    check_a_learn_event_allows_one_fresh_multicast_attempt_after_a_give_up,
    check_a_formula_action_id_is_adopted_never_filled_and_another_elements_totem_is_a_mapping_error,
    check_a_slot_event_inside_the_call_does_not_send_the_fill_again,
    check_a_native_slot_change_beats_a_queued_pick,
    check_a_plain_false_totem_info_clears_the_sweep_before_the_duration_object_is_asked,
    check_totems_are_looked_up_by_spell_id_not_by_english_name,
    check_a_throwing_secret_or_missing_api_never_breaks_a_sync,
    check_picks_are_kept_per_character,
    check_the_file_uses_no_snippets_and_no_state_drivers,
    check_toc_lists_the_totem_bar_after_the_seal_bar,
    check_no_em_dashes_in_the_new_files,
]
SCALED_CHECKS = [
    check_the_shoulder_is_the_six_by_one_block_and_the_buttons_sit_inside_it,
]


def main() -> int:
    failed = total = 0

    def run(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
