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
    hover piece or an Alt-click (which never drops the totem) and is the ICON flyout: 32 px tiles with no text, gap 3,
    pad 3, in a column on the button's axis whose first tile is 4 px over the piece top, the real spell tooltip to the
    right of the hovered tile, the current pick marked, a click stores the pick per character and closes it. Its
    chimney (TotemPiece.lua) rises out of the bump as one continuous outline, rasterised from the baked textures
    here; the whole path (piece or Alt-click, the cursor over the gap onto a tile, the tile the topmost mouse
    target, the click) is walked with a cursor model;
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
import struct
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
TOTEMPIECE = Path(os.environ.get("TOTEMPIECE_LUA", ADDON / "Modules/ActionBars/TotemPiece.lua"))
PIECE_GENERATOR = HERE / "assets" / "generate_totem_piece.py"
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
-- the texture coordinates a region was last given (the mock's own SetTexCoord keeps none)
__Region.SetTexCoord = function(self, ...) self._coord = { ... } end
function GameTooltip:SetOwner(owner, anchor) self._lines = {}; self._owner = owner; self._anchor = anchor; self._points = {} end
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
-- usability: IsUsableAction(action) and C_Spell.IsSpellUsable(spell) answer usable, notEnoughMana from
-- __use[kind][key] (unset: usable). __use.mode: "secret" (both answers secret), "throw" (for the keys in __use.throwOn,
-- so the main bars, which share IsUsableAction here, are not thrown at), "none" (no answer).
-- The counters, the last key asked and the set of keys ever asked only allocate for a key not seen before, so a hot
-- loop over the same buttons allocates nothing.
__use = { action = {}, spell = {}, mode = nil, throwOn = {}, n = { action = 0, spell = 0, legacy = 0 },
          last = {}, seen = { action = {}, spell = {}, legacy = {} } }
function __usable(kind, key, usable, noMana) __use[kind][key] = { usable, noMana } end
function __use_reset()
    __use.n.action, __use.n.spell, __use.n.legacy = 0, 0, 0
    __use.last.action, __use.last.spell, __use.last.legacy = nil, nil, nil
    __use.seen = { action = {}, spell = {}, legacy = {} }
end
local function usableAnswer(kind, key)
    __use.n[kind] = __use.n[kind] + 1
    __use.last[kind] = key
    __use.seen[kind][key] = true
    if __use.mode == "throw" and __use.throwOn[key] then error("usability blew up") end
    if __use.mode == "secret" then return __SECRET, __SECRET end
    if __use.mode == "none" then return end
    if __use.mode == "nilvalue" then return nil end         -- the old 1-or-nil style: nil means "not usable"
    local a = __use[kind == "legacy" and "spell" or kind][key]
    if __use.mode == "secretmana" then return (a and a[1]) or (a == nil), __SECRET end
    if a then return a[1], a[2] end
    return true, false
end
function IsUsableAction(action) return usableAnswer("action", action) end
C_Spell.IsSpellUsable = function(spell) return usableAnswer("spell", spell) end
function IsUsableSpell(spell) return usableAnswer("legacy", spell) end
"""

def boot(scale: float = 1.0, *, klass: str = "SHAMAN", learned=(), lists=None, spells=(), combat: bool = False,
         bar_mode=None, list_mode=None, console: bool = True, pre_login: str = "", native: bool = True, piece_file: bool = True):
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
                   extra_files=(csh.PETDOCK, csh.CLASSSHOULDER) + ((TOTEMPIECE,) if piece_file else ()) + (TOTEMBAR,),
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


def fire_script(lua, frame, script, *args):
    lua.eval("__Region.Fire")(frame, script, *args)


def over(frame, value: bool):
    """Where the cursor is, as IsMouseOver answers it (the mock has no geometry of its own)."""
    frame._mouseOver = value


def enter(lua, b):
    """The cursor moves onto an element button."""
    over(b, True)
    fire_script(lua, b, "OnEnter")


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


def check_listeners_hear_each_element_button_after_its_attributes_settle_and_never_in_combat():
    # GunsightShamanDrop.lua copies type1 / action1 / spell1 onto the pole click catchers from this announcement
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    lua.execute("""
        __ann = {}
        FS.TotemBar.OnAttributes(function(b)
            __ann[#__ann + 1] = { key = b.fsKey, slot = b.fsDef.slot, type1 = b:GetAttribute("type1"),
                spell1 = b:GetAttribute("spell1"), action1 = b:GetAttribute("action1"), locked = b.fsLocked }
        end)
        FS.TotemBar.OnAttributes(function() error("a listener that throws is skipped") end)
        __n = #__ann
    """)
    fire(lua, "SPELLS_CHANGED")
    seen = {str(row["key"]): row for row in seq(lua.eval("__ann"))}
    assert sorted(seen) == ["air", "earth", "fire", "water"], sorted(seen)    # element buttons only, not Set drop or Recall
    assert [int(seen[k]["slot"]) for k in ("fire", "earth", "water", "air")] == [1, 2, 3, 4]
    earth = seen["earth"]
    assert not earth["locked"] and str(earth["type1"]) == "action" and int(earth["action1"]) == action_id(2), "settled attributes at call time"
    for k in ("fire", "water", "air"):
        assert seen[k]["locked"] and seen[k]["type1"] is None, f"{k} is announced stripped"
    # a spell mode pick is announced with its spell
    lua.execute("__mc.lists[2] = nil")
    fire(lua, "SPELLS_CHANGED")
    last = [row for row in seq(lua.eval("__ann")) if str(row["key"]) == "earth"][-1]
    assert str(last["type1"]) == "spell" and last["spell1"] is not None and last["action1"] is None
    # in combat nothing settles, so nothing is announced; regen announces
    assert warnings(lua) == 1, f"a throwing listener is named once in chat, got {warnings(lua)}"
    set_combat(lua, True)
    lua.execute("__n = #__ann")
    fire(lua, "SPELLS_CHANGED")
    assert int(lua.eval("#__ann - __n")) == 0, "an announcement in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert int(lua.eval("#__ann - __n")) >= 4, "the replayed sync announces"


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
    fire(lua, "LEARNED_SPELL_IN_SKILL_LINE")
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
    enter(lua, b)
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


def check_the_arrow_shows_only_while_the_cursor_is_over_the_button_or_the_arrow():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    a = b.fsArrow
    assert not shown(a), "the arrow is up at rest"
    enter(lua, b)
    assert shown(a), "the arrow did not appear on mouse over"
    # the cursor crosses onto the arrow: the button's OnLeave fires first, the arrow is already under the cursor
    over(a, True)
    fire_script(lua, b, "OnLeave")
    assert shown(a), "the arrow flickered out crossing from the button onto it"
    fire_script(lua, a, "OnEnter")
    assert shown(a)
    # and back onto the button face below the arrow
    over(a, False)
    fire_script(lua, a, "OnLeave")
    assert shown(a), "the arrow left while the cursor was still over the button"
    fire_script(lua, b, "OnEnter")
    # off both: gone
    over(b, False)
    fire_script(lua, b, "OnLeave")
    assert not shown(a), "the arrow stayed after the cursor left the button"
    # off the arrow upwards (never over the button)
    enter(lua, b)
    over(a, True)
    over(b, False)
    fire_script(lua, b, "OnLeave")
    assert shown(a)
    over(a, False)
    fire_script(lua, a, "OnLeave")
    assert not shown(a), "the arrow stayed after the cursor left it"
    # a missed OnLeave (the button hidden or the cursor warped) is caught by the arrow's own poll
    enter(lua, b)
    assert shown(a)
    over(b, False)
    fire_script(lua, a, "OnUpdate", 0.016)
    assert not shown(a), "the poll did not hide an arrow with the cursor nowhere near"
    enter(lua, b)
    fire_script(lua, a, "OnUpdate", 0.016)
    assert shown(a), "the poll hid an arrow with the cursor on the button"
    # hiding the button takes the arrow with it
    fire_script(lua, b, "OnHide")
    assert not shown(a)


def check_a_locked_button_never_shows_an_arrow():
    lua = boot()
    b = by_key(lua, "fire")
    assert b.fsLocked
    enter(lua, b)
    assert not shown(b.fsArrow), "a locked element's arrow appeared"
    # learning the totem unlocks it: still hidden until the cursor comes
    lua2 = boot(learned=TOTEMS["fire"], lists=lists_for("fire"))
    f2 = by_key(lua2, "fire")
    assert not f2.fsLocked and not shown(f2.fsArrow) and f2.fsArrow._mouse
    # a button that unlocks under a cursor already on it brings the arrow up at once
    lua3 = boot()
    f3 = by_key(lua3, "earth")
    over(f3, True)
    lua3.execute('__know("Stoneskin Totem")')
    fire(lua3, "LEARNED_SPELL_IN_SKILL_LINE")
    assert not f3.fsLocked and shown(f3.fsArrow), "the unlocked button under the cursor has no arrow"


def check_the_arrow_shows_and_hides_in_combat_without_a_protected_touch():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    a = b.fsArrow
    assert not a._protected and not a._secure, "the arrow is a protected frame"
    set_combat(lua, True)
    before = (blocked(lua), int(lua.eval("__protectedTouch")))
    enter(lua, b)
    assert shown(a), "the arrow did not show in combat"
    over(b, False)
    fire_script(lua, b, "OnLeave")
    assert not shown(a), "the arrow did not hide in combat"
    enter(lua, b)
    over(b, False)
    fire_script(lua, a, "OnUpdate", 0.016)
    assert not shown(a)
    after = (blocked(lua), int(lua.eval("__protectedTouch")))
    assert before == after, f"protected operations in combat: {before} -> {after}"


_FX = {"LEFT": 0.0, "TOPLEFT": 0.0, "BOTTOMLEFT": 0.0, "TOP": 0.5, "CENTER": 0.5, "BOTTOM": 0.5,
       "RIGHT": 1.0, "TOPRIGHT": 1.0, "BOTTOMRIGHT": 1.0}
_FY = {"TOP": 1.0, "TOPLEFT": 1.0, "TOPRIGHT": 1.0, "CENTER": 0.5, "LEFT": 0.5, "RIGHT": 0.5,
       "BOTTOM": 0.0, "BOTTOMLEFT": 0.0, "BOTTOMRIGHT": 0.0}


def _rect(parent_rect, frame, rel_rect):
    """Rect (l, b, r, t) of `frame`, anchored by one point to a rect, in the parent's coordinates."""
    p = frame._points[1]
    w, h = float(frame._w), float(frame._h)
    rl, rb, rr, rt = rel_rect
    ax = rl + (rr - rl) * _FX[p.relPoint] + float(p.x)
    ay = rb + (rt - rb) * _FY[p.relPoint] + float(p.y)
    left, bottom = ax - w * _FX[p.point], ay - h * _FY[p.point]
    return (left, bottom, left + w, bottom + h)


def _button_rect(b):
    q = b._points[1]
    return (float(q.x), float(q.y), float(q.x) + float(b._w), float(q.y) + float(b._h))


def check_the_piece_hit_area_is_38_by_13_flush_with_the_button_top(scale):
    lua = boot(scale, learned=TOTEMS["earth"] + TOTEMS["fire"], lists=lists_for("earth", "fire"))
    host = g(lua).FSTotemBar
    tab = (0.0, 0.0, float(host._w), float(host._h))
    eps = 1e-6
    for key in ("fire", "earth", "water", "air"):
        b = by_key(lua, key)
        brect = _button_rect(b)
        a = b.fsArrow
        assert len(seq(a._points)) == 1, "the arrow is anchored by more than one point"
        approx(a._w, 38 * scale, f"{key} hit width"), approx(a._h, 13 * scale, f"{key} hit height")
        p = a._points[1]
        assert (p.point, p.relPoint) == ("BOTTOMLEFT", "TOPLEFT") and sb.same(lua, p.rel, b), \
            f"{key}: the hit area is anchored {p.point} to {p.relPoint} of {p.rel}"
        arect = _rect(None, a, brect)
        # 0 px into the face: it starts at the button top, and spans exactly the button's width
        assert abs(arect[1] - brect[3]) < eps, f"{key} hit area reaches {brect[3] - arect[1]} into the face"
        assert abs(arect[0] - brect[0]) < eps and abs(arect[2] - brect[2]) < eps, f"{key} hit area is not the button wide"
        # the piece rises 7 px over the tab's top rail (the host's top)
        approx(arect[3] - tab[3], 7 * scale, f"{key} rise over the tab's top rail", 0.01 * scale)


def check_clicks_on_the_button_face_never_land_on_the_piece(scale):
    lua = boot(scale, learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    brect = _button_rect(b)
    arect = _rect(None, b.fsArrow, brect)
    top, left, right = brect[3], brect[0], brect[2]

    def hits_arrow(x, y):
        return arect[0] <= x <= arect[2] and arect[1] <= y <= arect[3]

    step = scale / 2
    y = top - step
    while y >= top - float(b._h) / 4:
        x = left
        while x <= right:
            assert not hits_arrow(x, y), f"the piece eats a click {(top - y) / scale:.1f} px under the button top"
            x += step
        y -= step
    # the wedge tip under the button top is not clickable either; the seam and the bar are
    assert hits_arrow((left + right) / 2, top + 1 * scale) and hits_arrow(left + 1 * scale, top + 12 * scale)


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


DESTROY_ALL = "\n".join(f"/click FSTotemDestroy{n}" for n in range(1, 5))


def destroy_buttons(lua):
    return [g(lua)[f"FSTotemDestroy{n}"] for n in range(1, 5)]


def check_shift_right_click_dismisses_all_four_totems_through_hidden_secure_buttons():
    lua = all_known_with_lists()
    hidden = destroy_buttons(lua)
    host = g(lua).FSTotemBar
    for n, h in enumerate(hidden, start=1):
        assert h is not None and h._secure, f"FSTotemDestroy{n} is not a secure button"
        assert sb.same(lua, h._parent, host), f"FSTotemDestroy{n} is not on the tab's host"
        keys = sorted(str(k) for k in h._attrs.keys())
        assert keys == ["totem-slot", "type", "useOnKeyDown"], f"FSTotemDestroy{n} carries {keys}"
        assert attr(h, "useOnKeyDown") is False, "the up-click must count whatever the CVar says"
        assert attr(h, "type") == "destroytotem" and int(attr(h, "totem-slot")) == n
        # no field Blizzard's click path reads, no modifier prefix a held Shift could be redirected by
        assert h.bar is None, "a .bar field on a secure button"
        clicks = [h._clicks[k] for k in range(1, len(h._clicks) + 1)]
        assert clicks == ["AnyUp", "AnyDown"], f"FSTotemDestroy{n} clicks {clicks}"
        assert not h._mouse, f"FSTotemDestroy{n} takes the mouse"
    for key in ("fire", "earth", "water", "air"):
        b = by_key(lua, key)
        assert attr(b, "type2") == "destroytotem" and int(attr(b, "totem-slot2")) == SLOT[key], key
        assert attr(b, "shift-type2") == "macro", f"{key} shift-right click is {attr(b, 'shift-type2')!r}"
        assert attr(b, "shift-macrotext2") == DESTROY_ALL, repr(attr(b, "shift-macrotext2"))
    # set drop and recall are not totem elements
    for key in ("set", "recall"):
        assert attr(by_key(lua, key), "shift-type2") is None


# SecureTemplates.lua, SecureActionButton_ShouldUseOnKeyDown and the clickAction line of SecureActionButton_OnClick,
# for a click that is not a real mouse press (what /click sends): the attribute decides, the CVar only when it is unset.
CLICK_MODEL = """
__destroyed = {}
function DestroyTotem(slot) __destroyed[#__destroyed + 1] = slot end
function __secureClick(button, down)
    local use = button._attrs["useOnKeyDown"]
    if use == nil then use = __cvars.ActionButtonUseKeyDown == "1" end
    local clickAction = (down and use) or (not down and not use)
    if clickAction and button._attrs["type"] == "destroytotem" then DestroyTotem(button._attrs["totem-slot"]) end
end
"""


def check_a_macro_click_with_the_use_key_down_cvar_on_still_destroys_the_totem():
    lua = all_known_with_lists()
    lua.execute(CLICK_MODEL)
    lua.execute('__cvars = __cvars or {}; __cvars.ActionButtonUseKeyDown = "1"')
    for n, h in enumerate(destroy_buttons(lua), start=1):
        lua.eval("__secureClick")(h, False)          # /click: down=false
        assert [int(x) for x in seq(g(lua).__destroyed)] == list(range(1, n + 1)), f"slot {n} was not destroyed"
    # the model sees the failure it guards against: the same click on a button without the attribute does nothing
    lua.execute("__destroyed = {}")
    h = destroy_buttons(lua)[0]
    lua.eval("function(b) b._attrs['useOnKeyDown'] = nil end")(h)
    lua.eval("__secureClick")(h, False)
    assert len(seq(g(lua).__destroyed)) == 0, "the model lets an up-click through with the CVar on"
    # with the CVar off the click works either way
    lua.execute('__cvars.ActionButtonUseKeyDown = "0"')
    lua.eval("__secureClick")(h, False)
    assert len(seq(g(lua).__destroyed)) == 1


def check_the_dismiss_all_attributes_are_written_out_of_combat_only():
    lua = boot(learned=[])
    set_combat(lua, True)
    before = blocked(lua)
    lua.execute('__know("Stoneskin Totem")')
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP"):
        fire(lua, event)
    assert blocked(lua) == before, "a protected write was tried in combat"
    assert attr(by_key(lua, "earth"), "shift-type2") is None, "written in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert attr(by_key(lua, "earth"), "shift-macrotext2") == DESTROY_ALL
    # a login in combat builds nothing until regen, hidden buttons included
    lua = boot(learned=TOTEMS["earth"], combat=True)
    assert g(lua).FSTotemDestroy1 is None, "built a secure frame in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert all(h is not None for h in destroy_buttons(lua))
    assert attr(by_key(lua, "earth"), "shift-type2") == "macro"
    assert attr(destroy_buttons(lua)[1], "totem-slot") == 2


def check_a_locked_element_carries_no_dismiss_all():
    lua = boot()
    for key in ("fire", "earth", "water", "air"):
        b = by_key(lua, key)
        assert b.fsLocked and attr(b, "shift-type2") is None and attr(b, "shift-macrotext2") is None, key
    # the hidden buttons exist anyway (built once with the tab) and still carry only type and totem-slot
    for h in destroy_buttons(lua):
        assert sorted(str(k) for k in h._attrs.keys()) == ["totem-slot", "type", "useOnKeyDown"]


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
    fire_script(lua, entries[0], "OnEnter")
    fire_script(lua, entries[0], "OnLeave")
    click(lua, entries[1])
    tb(lua).OpenPicker("fire")
    fire_script(lua, [e for e in seq(picker.fsEntries) if shown(e)][0], "OnEnter")
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
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
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
    first = [e for e in seq(tb(lua).Picker().fsEntries) if shown(e)][0]
    fire_script(lua, first, "OnEnter")
    assert int(g(lua).GameTooltip._spellID) == tid(lua, "Stoneskin Totem"), "the tile asks the tooltip for the spell id"
    fire_script(lua, first, "OnLeave")
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
    assert "Left click: drop Stoneskin Totem. Right click: dismiss. Shift-right click: dismiss all. Alt-click or arrow: change totem." in text, text
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


def check_bindings_xml_declares_the_totem_commands_after_the_seals():
    root = ET.parse(BINDINGS).getroot()
    # the buff tab's two commands follow (buffbar-harness.py pins them)
    names = [b.get("name") for b in root.findall("Binding") if "FSBuffTabButton" not in b.get("name", "")]
    want = [f"CLICK FSSealButton{i}:LeftButton" for i in range(1, 8)] + [
        f"CLICK FSTotemButton{i}:LeftButton" for i in range(1, 9)]    # six buttons, the preset dial and GNARLY (TotemPresets.lua)
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


def piece(lua, key):
    return by_key(lua, key).fsArrow.fsPiece


def coord(tex):
    return [float(v) for v in seq(tex._coord)]


def tp(lua):
    return g(lua).FS.TotemPiece


def shoulder_obj(lua):
    return csh.shoulder(lua)


def check_the_piece_is_made_of_plain_regions_of_the_plain_arrow_button():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    a = b.fsArrow
    assert a._kind == "Button" and not a._secure and not a._protected, "the arrow is not a plain Button"
    assert sb.same(lua, a._parent, b)
    pc = piece(lua, "earth")
    for key in ("fill", "scan", "glow", "edge", "hazeA", "hazeB", "bodyA", "bodyB", "core"):
        tex = pc[key]
        assert tex is not None and tex._kind == "Texture" and sb.same(lua, tex._parent, a), f"{key} is not on the arrow"
        assert str(tex._texture).endswith(".tga"), f"{key} has no baked texture: {tex._texture}"
    for k in ("fire", "earth", "water", "air"):
        other = by_key(lua, k).fsArrow
        assert not other._secure and not other._protected, f"{k}'s arrow is secure"
        assert not [1 for _ in seq(other._attrs)], f"{k}'s arrow carries attributes"


def check_the_piece_shows_on_button_hover_dim_and_goes_lit_on_the_piece_and_hides_away():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    a = b.fsArrow
    pc = piece(lua, "earth")
    assert not shown(a), "the piece is up at rest"
    enter(lua, b)
    assert shown(a) and not pc.lit, "button hover must bring the piece up dim"
    assert not shown(pc.glow), "the dim piece glows"
    over(a, True)
    fire_script(lua, b, "OnLeave")
    fire_script(lua, a, "OnEnter")
    assert shown(a) and pc.lit and shown(pc.glow), "the cursor on the piece must light it"
    over(a, False)
    fire_script(lua, a, "OnLeave")
    assert shown(a) and not pc.lit, "off the piece but still on the button it must go back to dim"
    over(b, False)
    fire_script(lua, b, "OnLeave")
    assert not shown(a), "the piece stayed after the cursor left"


def check_the_chevron_points_up_and_flips_down_while_the_picker_is_open():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    b = by_key(lua, "earth")
    a = b.fsArrow
    pc = piece(lua, "earth")
    enter(lua, b)
    assert not pc.flipped and coord(pc.bodyA) == [0, 1, 0, 1], f"the chevron does not point up: {coord(pc.bodyA)}"
    click(lua, a)
    picker = tb(lua).Picker()
    assert shown(picker) and pc.flipped and pc.lit, "an open picker must flip the chevron and light the piece"
    assert abs(float(picker._points[1].y) - 17) < 1e-6, "the flyout is not where the v3 mockup's open state has it"
    for key in ("hazeA", "hazeB", "bodyA", "bodyB", "core"):
        assert coord(pc[key]) == [0, 1, 1, 0], f"{key} is not flipped down: {coord(pc[key])}"
    # the cursor leaves everything: the piece stays up while the picker is open for this element
    over(a, False)
    over(b, False)
    picker._mouseOver = True
    fire_script(lua, b, "OnLeave")
    fire_script(lua, a, "OnLeave")
    fire_script(lua, a, "OnUpdate", 0.016)
    assert shown(a) and pc.flipped, "the piece dropped while its picker was open"
    # the picker closes: the chevron points up again and the piece goes with the cursor away
    click(lua, a)
    assert not shown(picker)
    assert not shown(a), "the piece stayed up after the picker closed with the cursor away"
    assert coord(pc.bodyA) == [0, 1, 0, 1] and not pc.flipped, "the chevron did not flip back up"
    # the picker opened by something else (a key, Alt-click) brings the piece up in its open state
    tb(lua).OpenPicker("earth")
    assert shown(a) and pc.flipped
    tb(lua).ClosePicker()
    assert not shown(a)
    # a picker for another element does not flip this one
    lua = all_known_with_lists()
    tb(lua).OpenPicker("fire")
    assert piece(lua, "fire").flipped and not piece(lua, "earth").flipped and not shown(by_key(lua, "earth").fsArrow)
    tb(lua).OpenPicker("earth")
    assert not piece(lua, "fire").flipped and piece(lua, "earth").flipped
    assert not shown(by_key(lua, "fire").fsArrow), "the old owner's piece stayed up"


def check_the_bump_stands_only_around_the_hovered_button_and_the_rail_opens_under_it():
    lua = all_known_with_lists()
    sh = shoulder_obj(lua)
    p = tp(lua)
    assert p.BumpCol() is None and sh.TopGap(sh) is None
    top = sh.rail.stroke
    rest = (float(top._points[1].x), float(top._w))
    earth, fire_b = by_key(lua, "earth"), by_key(lua, "fire")
    enter(lua, earth)
    assert int(p.BumpCol()) == 2, "no bump around the hovered element"
    gap = sh.TopGap(sh)
    assert gap is not None
    rect = p.BumpRect(2)
    approx(gap[1], rect.left, "the rail opens at the bump's left wall")
    approx(gap[2], rect.right + 5, "the rail resumes under the foot")
    assert float(top._w) < rest[1], "the original rail was not cut short"
    assert shown(sh.rail.extraStroke) and shown(sh.rail.extraHalo), "the right part of the rail is not drawn"
    # one bump at a time: another element's hover moves it
    over(earth, False)
    fire_script(lua, earth, "OnLeave")
    assert p.BumpCol() is None and sh.TopGap(sh) is None, "the bump stayed after the cursor left"
    assert (float(top._points[1].x), float(top._w)) == rest, "the rail was not put back as it was"
    assert not shown(sh.rail.extraStroke), "the rail's right part stayed"
    enter(lua, fire_b)
    assert int(p.BumpCol()) == 1 and int(p.BumpCol()) != 2
    over(fire_b, False)
    fire_script(lua, fire_b, "OnLeave")
    assert p.BumpCol() is None
    # a locked button never brings one up
    lua = boot()
    enter(lua, by_key(lua, "fire"))
    assert tp(lua).BumpCol() is None


def check_hovering_another_element_never_leaves_an_open_picker_without_its_bump():
    lua = all_known_with_lists()
    sh = shoulder_obj(lua)
    p = tp(lua)
    fire_b, earth = by_key(lua, "fire"), by_key(lua, "earth")
    tb(lua).OpenPicker("fire")
    assert int(p.BumpCol()) == 1 and shown(fire_b.fsArrow), "the open picker has no piece or bump"
    # the cursor passes over another element and leaves it again: the open picker's bump comes back
    enter(lua, earth)
    assert int(p.BumpCol()) == 2, "the hovered element has no bump"
    over(earth, False)
    fire_script(lua, earth, "OnLeave")
    assert not shown(earth.fsArrow)
    assert shown(fire_b.fsArrow) and p.BumpCol() is not None and int(p.BumpCol()) == 1, \
        "the open picker's piece stands without its bump"
    assert sh.TopGap(sh) is not None, "the open picker's rail stayed closed"
    # an Alt-click opened picker is the same
    tb(lua).OpenPicker("earth")
    water = by_key(lua, "water")
    enter(lua, water)
    over(water, False)
    fire_script(lua, water, "OnLeave")
    assert int(p.BumpCol()) == 2 and shown(earth.fsArrow), "Alt-click picker lost its bump"
    # the picker closes with the cursor away: everything goes
    tb(lua).ClosePicker()
    assert p.BumpCol() is None and sh.TopGap(sh) is None and not shown(earth.fsArrow)


def check_escape_closing_the_picker_drops_the_bump_and_flips_the_chevron_back():
    lua = all_known_with_lists()
    sh = shoulder_obj(lua)
    p = tp(lua)
    earth = by_key(lua, "earth")
    pc = piece(lua, "earth")
    tb(lua).OpenPicker("earth")
    assert "FSTotemPicker" in [str(v) for v in seq(g(lua).UISpecialFrames)], "the picker is not an Escape frame"
    assert pc.flipped and int(p.BumpCol()) == 2
    picker = tb(lua).Picker()
    # Escape hides every UISpecialFrames frame; the cursor is away
    picker.Hide(picker)
    assert not shown(picker)
    assert not pc.flipped and coord(pc.bodyA) == [0, 1, 0, 1], "the chevron stayed down after Escape"
    assert not shown(earth.fsArrow), "the piece stayed up after Escape with the cursor away"
    assert p.BumpCol() is None and sh.TopGap(sh) is None, "the bump stayed after Escape"
    # with the cursor still on the button the piece and bump stay, the chevron up
    tb(lua).OpenPicker("earth")
    over(earth, True)
    picker.Hide(picker)
    assert shown(earth.fsArrow) and not pc.flipped and int(p.BumpCol()) == 2


def check_the_tab_builds_without_the_piece_file():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), piece_file=False)
    assert g(lua).FS.TotemPiece is None, "the piece file loaded"
    assert len([1 for i in range(1, 7) if btn(lua, i) is not None]) == 6, "the tab did not build"
    b = by_key(lua, "earth")
    # a build that stopped at the missing piece leaves the button unsized
    assert float(b._w) == 38 and float(b._h) == 38, "the tab's build stopped at the missing piece"
    assert b.fsArrow is None, "an arrow without a piece"
    enter(lua, b)       # no piece, no error
    over(b, False)
    fire_script(lua, b, "OnLeave")
    tb(lua).OpenPicker("earth")
    assert shown(tb(lua).Picker()), "the picker needs the piece"
    tb(lua).ClosePicker()


def check_the_fire_bump_uses_the_6_px_left_shoulder_and_the_others_4():
    lua = all_known_with_lists()
    sh = shoulder_obj(lua)
    p = tp(lua)
    cs = g(lua).FS.ClassShoulder.C
    pitch = float(cs.BTN) + float(cs.GAP)
    for col, key in ((1, "fire"), (2, "earth"), (3, "water"), (4, "air")):
        rect = p.BumpRect(col)
        button = float(cs.PAD) + (col - 1) * pitch
        wall = 6 if col == 1 else 4
        approx(rect.left, button - wall, f"{key} bump left wall")
        approx(rect.right, button + 38 + 4, f"{key} bump right wall")
        approx(rect.top, -11, f"{key} bump top")
        b = by_key(lua, key)
        enter(lua, b)
        parts = [f for f in g(lua).__frames.values() if f._kind == "Texture" and sb.same(lua, f._parent, sh.art)
                 and f._points and f._points[1].y is not None]
        # the bump's body fill: its left edge is the wall
        body = [t for t in parts if abs(float(t._points[1].x) - rect.left) < 1e-6 and abs(float(t._points[1].y) - 11) < 1e-6]
        assert body, f"{key}: no fill starting at the left wall {rect.left}"
        approx(float(body[0]._w), rect.right - rect.left, f"{key} body width")
        corner_hidden = not shown(sh.rail.corner[1])
        assert corner_hidden == (col == 1), f"{key}: the top left cut must be hidden for Fire only"
        gap = sh.TopGap(sh)
        approx(gap[1], rect.left, f"{key} rail gap start")
        assert gap[5] == (col == 1)
        over(b, False)
        fire_script(lua, b, "OnLeave")
        assert shown(sh.rail.corner[1]) and sh.TopGap(sh) is None, f"{key}: the cut corner did not come back"


def check_the_piece_and_the_bump_work_in_combat_without_a_protected_touch():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    a = b.fsArrow
    pc = piece(lua, "earth")
    sh = shoulder_obj(lua)
    set_combat(lua, True)
    before = (blocked(lua), int(lua.eval("__protectedTouch")))
    enter(lua, b)
    assert shown(a) and int(tp(lua).BumpCol()) == 2 and sh.TopGap(sh) is not None, "no piece or bump in combat"
    click(lua, a)
    assert shown(tb(lua).Picker()) and pc.flipped, "the chevron did not flip in combat"
    click(lua, a)
    over(b, False)
    fire_script(lua, b, "OnLeave")
    assert not shown(a) and tp(lua).BumpCol() is None and sh.TopGap(sh) is None, "the piece or bump stayed in combat"
    after = (blocked(lua), int(lua.eval("__protectedTouch")))
    assert before == after, f"protected operations in combat: {before} -> {after}"


def check_opening_the_rail_refuses_bad_numbers_and_a_tab_that_is_not_standing_has_no_bump():
    lua = all_known_with_lists()
    sh = shoulder_obj(lua)
    top = sh.rail.stroke
    rest = (float(top._points[1].x), float(top._w))
    nan = float("nan")
    for args in ((50, 40, 40, 90, False), (nan, 60, 40, 90, False), (50, 60, 40, 40, False),
                 (50, 300, 40, 90, False), (50, 60, 40, 900, False)):
        assert not sh.OpenTop(sh, *args), f"OpenTop took {args}"
        assert sh.TopGap(sh) is None and (float(top._points[1].x), float(top._w)) == rest
    assert not sh.CloseTop(sh), "CloseTop on a closed rail"
    # a retint reaches the rail's second part
    assert sh.OpenTop(sh, 50, 60, 40, 80, False)
    assert sh.SetEdge(sh, lua.table_from([1, 0, 0]), 0.5, 0.25)
    assert [float(v) for v in seq(sh.rail.extraStroke._vertex)] == [1, 0, 0, 0.5]
    assert [float(v) for v in seq(sh.rail.extraHalo._vertex)] == [1, 0, 0, 0.25]
    assert sh.CloseTop(sh) and (float(top._points[1].x), float(top._w)) == rest
    # the Console goes off: no shoulder stands, so hovering brings the piece but no bump
    lua = all_known_with_lists()
    csh.console(lua).SetActive(False)
    b = by_key(lua, "earth")
    enter(lua, b)
    assert tp(lua).BumpCol() is None, "a bump on a tab that is not drawn"
    assert shown(b.fsArrow), "the piece still works without the chassis"


def check_the_baked_art_and_the_lua_numbers_agree():
    import importlib.util as iu
    spec = iu.spec_from_file_location("generate_totem_piece", PIECE_GENERATOR)
    gen = iu.module_from_spec(spec)
    spec.loader.exec_module(gen)
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    c = tp(lua).C
    approx(float(c.SEAM), gen.SEAM, "seam"), approx(float(c.BAR), gen.BAR, "bar")
    approx(float(c.HIT_H), gen.SEAM + gen.BAR, "hit height"), approx(float(c.HIT_W), gen.BTN_W, "hit width")
    assert [float(v) for v in seq(c.PIECE_ORIGIN)] == [float(v) for v in gen.PIECE_ORIGIN]
    assert [float(v) for v in seq(c.CHEV_ORIGIN)] == [float(v) for v in gen.CHEV_ORIGIN]
    assert float(c.CANVAS_W) * gen.PIECE_K == gen.PIECE_CANVAS_W and float(c.CANVAS_H) * gen.PIECE_K == gen.PIECE_CANVAS_H
    assert (float(c.FOOT), float(c.RISE), float(c.HALO_PAD)) == (gen.BUMP_FOOT, gen.BUMP_RISE, gen.GLOW_PAD)
    assert (float(c.SHOULDER), float(c.SHOULDER_FIRST)) == (-gen.VARIANTS["normal"], -gen.VARIANTS["fire"])
    assert float(c.SHOULDER) == gen.BUMP_RIGHT - gen.BTN_W, "the right wall is as far out as the left one"
    for name, table, at in (("STROKE", c.STROKE, gen.BUMP_STROKE_AT), ("HALO", c.HALO, gen.BUMP_HALO_AT)):
        for variant in ("normal", "fire"):
            region = gen.BUMP_STROKE_REGION[variant] if name == "STROKE" else gen.BUMP_HALO_REGION[variant]
            want = [float(v) for v in region] + [float(v) for v in at[variant]]
            got = [float(v) for v in seq(table[variant])]
            assert got == want, f"{name} {variant}: Lua {got} vs generator {want}"
    assert float(c.STROKE.k) == gen.BUMP_K and float(c.STROKE.size) == gen.BUMP_CANVAS
    assert (float(c.HALO.w), float(c.HALO.h)) == (gen.HALO_CANVAS_W, gen.HALO_CANVAS_H)
    # the open outline's junction halos
    for name, side in (("left", "left"), ("leftFire", "left_fire"), ("right", "right")):
        want = [float(v) for v in gen.FLY_HALO_REGION[side]] + [float(v) for v in gen.FLY_HALO_AT[side]]
        got = [float(v) for v in seq(c.FLY_HALO[name])]
        assert got == want, f"FLY_HALO {name}: Lua {got} vs generator {want}"
    assert float(c.FLY_HALO.size) == gen.FLY_HALO_CANVAS
    assert float(c.HALO_PAD) == gen.GLOW_PAD == -gen.FLY_HALO_REGION["left"][1] + gen.BUMP_TOP, "the junctions start one halo pad over the bump top"
    assert (gen.FLY_LEFT, gen.FLY_RIGHT) == (0.0, float(c.BTN)), "the chimney's walls are the button's edges"
    # the baked files exist, power of two, the sizes the Lua cuts them at
    import struct
    tex = ADDON / "Media" / "Textures"
    for name, size in (("totem_piece_fill", (256, 128)), ("totem_chev_core", (256, 128)),
                       ("totem_bump_stroke", (256, 256)), ("totem_bump_halo", (128, 64)),
                       ("totem_flyout_halo", (64, 64))):
        data = (tex / f"{name}.tga").read_bytes()
        assert struct.unpack("<HH", data[12:16]) == size, f"{name}.tga is not {size}"


# ---------------------------------------------------------------------------------------------
# The icon flyout (mockups/totem-picker-arrow-2026-10-13.html concept A, open state of
# mockups/totem-picker-arrow-v3-2026-10-13.html V1): tiles on the picker frame, chimney chrome on the tab
# ---------------------------------------------------------------------------------------------

V3_MOCKUP = HERE.parent / "mockups" / "totem-picker-arrow-v3-2026-10-13.html"
TEXTURES = ADDON / "Media" / "Textures"
_TGA = {}


def _tga(path):
    if path not in _TGA:
        data = Path(path).read_bytes()
        w, h = struct.unpack("<HH", data[12:16])
        assert data[16] == 32, f"{path} is not 32 bit"
        off = 18 + data[0]
        _TGA[path] = (w, h, data[off:off + w * h * 4], bool(data[17] & 0x20))
    return _TGA[path]


def _alpha_at(path, u, v):
    w, h, px, top_first = _tga(path)
    x, y = min(w - 1, max(0, int(u * w))), min(h - 1, max(0, int(v * h)))
    row = y if top_first else h - 1 - y
    return px[(row * w + x) * 4 + 3] / 255.0


def tex_info(t):
    """((x, y, w, h) in the art's design px, the baked file or None for a flat one, the texcoord window l r t b)."""
    p = t._points[1]
    name = str(t._texture)
    path = TEXTURES / name.replace("\\", "/").split("/")[-1] if name.endswith(".tga") else None
    c = [float(v) for v in seq(t._coord)] if t._coord is not None else [0.0, 1.0, 0.0, 1.0]
    assert len(c) == 4, f"{name}: a texcoord with {len(c)} numbers"
    return (float(p.x), -float(p.y), float(t._w), float(t._h)), path, c


def tab_infos(frame, layer):
    return [tex_info(t) for t in seq(frame._regions) if t._kind == "Texture" and t._layer == layer and t._shown]


def sample(infos, x, y):
    """The summed alpha of every piece at the art point (x, y)."""
    total = 0.0
    for (bx_, by_, bw, bh), path, (l, r, tp_, bt) in infos:
        if bx_ <= x < bx_ + bw and by_ <= y < by_ + bh:
            if path is None:
                total += 1.0
            else:
                total += _alpha_at(path, l + (r - l) * (x - bx_) / bw, tp_ + (bt - tp_) * (y - by_) / bh)
    return total


def overlap(a, b):
    ax, ay, aw, ah = a[0]
    bx_, by_, bw, bh = b[0]
    return min(ax + aw, bx_ + bw) - max(ax, bx_) > 1e-6 and min(ay + ah, by_ + bh) - max(ay, by_) > 1e-6


def snapshot(sh):
    return sorted((tuple(round(v, 6) for v in info[0]), str(info[1]), tuple(info[2]))
                  for info in tab_infos(sh.normal, "BORDER") + tab_infos(sh.normal, "BACKGROUND")
                  + tab_infos(sh.art, "BACKGROUND"))


def flyout_height(n):
    return n * 32 + (n - 1) * 3 + 5


def _flyout_case(key):
    lua = all_known_with_lists()
    sh, p = shoulder_obj(lua), tp(lua)
    col, n = ORDER.index(key) + 1, len(TOTEMS[key])
    b = by_key(lua, key)
    enter(lua, b)
    rect = p.BumpRect(col)
    left, floor = float(rect.button), float(rect.top)
    top, wall_out = floor - flyout_height(n), (6 if key == "fire" else 4)
    hover = snapshot(sh)
    hover_strokes = tab_infos(sh.normal, "BORDER")
    assert sample(hover_strokes, left + 19.5, floor + 0.5) >= 0.99, "the hover bump has no top line to open"
    tb(lua).OpenPicker(key)
    assert p.FlyoutCol() is not None and int(p.FlyoutCol()) == col, "no chimney around the open picker"
    fr = p.FlyoutRect(col, flyout_height(n))
    for name, want in (("left", left), ("right", left + 38), ("floor", floor), ("top", top)):
        approx(fr[name], want, f"flyout {name}")
    assert abs(float(rect.buttonTop) - floor - 17) < 1e-6, "the bump top is not 17 px over the button top"
    strokes = tab_infos(sh.normal, "BORDER")
    # the chimney's own outline: two walls, the top line and the top left cut
    boxes = [tuple(round(v, 6) for v in s[0]) for s in strokes]
    for want, label in (((left, top + 6, 1, floor + 1 - top - 6), "left wall"), ((left + 37, top + 1, 1, floor - top), "right wall"),
                        ((left + 6, top, 32, 1), "top line"), ((left, top, 6, 6), "top left cut")):
        assert tuple(round(v, 6) for v in want) in boxes, f"{key}: no chimney {label} at {want}; strokes {boxes}"
    # the bump's own stroke is split at the walls: the part left of the left wall and the part right of the right
    bump_parts = [s for s in strokes if s[1] is not None and s[1].name == "totem_bump_stroke.tga"]
    assert len(bump_parts) == 2, f"{key}: the bump stroke is {len(bump_parts)} pieces while open"
    bump_parts.sort(key=lambda s: s[0][0])
    approx(bump_parts[0][0][0] + bump_parts[0][0][2], left, f"{key} bump stroke ends at the left wall")
    approx(bump_parts[1][0][0], left + 38, f"{key} bump stroke resumes at the right wall")
    # no stroke piece lies on another (the rail's pieces run under the foot's window by design: the raster below
    # counts those pixels)
    above = [s_ for s_ in strokes if s_[0][1] < -1]
    for i in range(len(above)):
        for j in range(i + 1, len(above)):
            assert not overlap(above[i], above[j]), f"{key}: stroke pieces {above[i][0]} and {above[j][0]} overlap"
    # raster: the opening has no line across it, the outline is one connected line, nowhere doubled
    assert sample(strokes, left + 19.5, floor + 0.5) < 0.01, f"{key}: a line still crosses the chimney's mouth"
    h = int(flyout_height(n))
    lit, worst = set(), 0.0
    for i in range(-10, 52):
        for j in range(-h - 2, 12):
            a = sample(strokes, left + i + 0.5, floor + j + 0.5)
            if a >= 0.5:
                lit.add((i, j))
            if j <= 4:
                worst = max(worst, a)
    assert worst <= 1.001, f"{key}: a stroke is drawn twice (summed alpha {worst})"
    assert (0, -10) in lit, f"{key}: the chimney's left wall is not lit"
    seen, todo = {(0, -10)}, [(0, -10)]
    while todo:
        ci, cj = todo.pop()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                q = (ci + di, cj + dj)
                if q in lit and q not in seen:
                    seen.add(q)
                    todo.append(q)
    for q, label in (((19, -h), "top line"), ((37, -10), "right wall"), ((40, 0), "right shoulder"),
                     ((41, 3), "bump right wall"), ((46, 9), "the foot"), ((48, 11), "the rail past the foot"),
                     ((-wall_out, 11), "the rail at the left wall"), ((-wall_out, 0), "bump left wall")):
        assert q in seen, f"{key}: {label} {q} is not on the one continuous outline"
    # the fill: one layer everywhere inside, none in the cut corner, the bump's fill meeting it at the floor
    fills = tab_infos(sh.art, "BACKGROUND")
    for i in range(38):
        for j in range(h):
            d = i + 0.5 + j + 0.5
            if abs(d - 6) < 1.6:
                continue
            c = sum(1 for f in fills if sample([f], left + i + 0.5, top + j + 0.5) >= 0.5)
            assert c == (0 if d < 6 else 1), f"{key}: {c} fill layers at chimney pixel {(i, j)}"
    assert sum(1 for f in fills if sample([f], left + 19.5, floor + 0.5) >= 0.5) == 1, "the bump fill does not meet the chimney"
    # the halo: the bump's own is gone from inside the chimney, the walls and the top glow outside
    halos = tab_infos(sh.normal, "BACKGROUND")
    assert sample(halos, left + 19.5, floor - 6) < 0.01, f"{key}: the bump's halo lights the chimney's mouth"
    assert sample(halos, left - 2.5, floor - 5.5) > 0.2, f"{key}: no halo beside the chimney wall above the shoulder"
    assert sample(halos, left + 40.5, floor - 14.5) > 0.2, f"{key}: no halo beside the right wall"
    assert sample(halos, left + 19.5, top - 2.5) > 0.2, f"{key}: no halo over the top"
    # closing puts the hover bump back, piece for piece
    tb(lua).ClosePicker()
    assert p.FlyoutCol() is None
    assert snapshot(sh) == hover, f"{key}: closing did not restore the hover bump"


def check_the_chimney_grows_out_of_the_bump_as_one_outline_earth():
    _flyout_case("earth")


def check_the_chimney_grows_out_of_the_bump_as_one_outline_fire():
    _flyout_case("fire")


def check_the_flyout_numbers_are_the_v3_mockups():
    html = V3_MOCKUP.read_text(encoding="utf-8")
    for needle in ("TILE:32,TGAP:3,TPAD:3", "var H=4+n*G.TILE+(n-1)*G.TGAP+5;", "bt=fl-4", "fl=BY-(k.s+k.th)",
                   "var w=G.TILE,cu=4,", "lx=(el==='fire')?xl-6:xl-4", "[xr,bt],[xr+4,bt]", "tx=ch.xl+G.TPAD"):
        assert needle in html, f"the v3 mockup no longer says {needle!r}; re-read the open state"
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    f = tb(lua).FLYOUT
    assert (int(f.TILE), int(f.GAP), int(f.PAD), int(f.TOP_PAD), int(f.CUT), int(f.ABOVE)) == (32, 3, 3, 5, 4, 4)
    c = tp(lua).C
    assert int(f.RISE) == int(f.ABOVE) + int(c.SEAM) + int(c.BAR) == 17, "the flyout is not 4 px over the piece top"
    assert int(f.RISE) == int(c.RISE) + 6, "the flyout does not start at the bump top"


def check_the_picker_is_an_icon_only_column_of_32_px_tiles_on_the_buttons_axis(scale):
    lua = boot(scale, learned=TOTEMS["earth"], lists=lists_for("earth"))
    tb(lua).OpenPicker("earth")
    picker, b = tb(lua).Picker(), by_key(lua, "earth")
    tiles = [e for e in seq(picker.fsEntries) if shown(e)]
    assert len(tiles) == 5
    pr, br, ar = csh.D(lua, picker), csh.D(lua, b), csh.D(lua, b.fsArrow)
    approx(pr["x"], br["x"], "the column is on the button's axis", 0.01), approx(pr["w"], 38, "flyout width", 0.01)
    approx(pr["h"], flyout_height(5), "flyout height", 0.01)
    bottom = pr["y"] + pr["h"]
    approx(bottom, br["y"] - 17, "the flyout starts 17 px over the button top", 0.01)
    approx(bottom, ar["y"] - 4, "the first tile is 4 px over the piece top", 0.01)
    for i, tile in enumerate(tiles):
        d = csh.D(lua, tile)
        assert tile._kind == "Button" and not tile._secure and not tile._protected, "a tile is not a plain Button"
        approx(d["w"], 32, f"tile {i} width", 0.01), approx(d["h"], 32, f"tile {i} height", 0.01)
        approx(d["x"], br["x"] + 3, f"tile {i} left pad", 0.01)
        approx(br["x"] + 38 - (d["x"] + d["w"]), 3, f"tile {i} right pad", 0.01)
        approx(d["y"] + d["h"], bottom - i * 35, f"tile {i} bottom (gap 3)", 0.01)
        assert tile.icon._texture == 9000 + tid(lua, TOTEMS["earth"][i]), "a tile does not carry its spell icon"
        assert [r for r in seq(tile._regions) if r._kind == "FontString"] == [], "a tile carries a name FontString"
        assert tile.fsSkin.chamfer == 4, "a tile is not the cut 4 button"
    assert [r for r in seq(picker._regions) if r._kind == "FontString"] == [], "the picker carries text"


def check_a_tile_shows_the_real_spell_tooltip_to_the_right_and_hides_it_on_leave(scale):
    lua = boot(scale, learned=TOTEMS["earth"], lists=lists_for("earth"))
    tb(lua).OpenPicker("earth")
    picker = tb(lua).Picker()
    tiles = [e for e in seq(picker.fsEntries) if shown(e)]
    tip = g(lua).GameTooltip
    fire_script(lua, tiles[1], "OnEnter")
    assert int(tip._spellID) == tid(lua, "Earthbind Totem") and shown(tip), "the tile did not ask for its spell tooltip"
    pt = tip._points[1]
    assert (pt.point, pt.relPoint) == ("LEFT", "RIGHT") and sb.same(lua, pt.rel, tiles[1]), "the tooltip is not beside the tile"
    approx(pt.x, 5 * scale, "tooltip gap to the right of the tile"), approx(pt.y, 0, "tooltip centred on the tile")
    assert tiles[1].fsHover, "the hovered tile does not light"
    fire_script(lua, tiles[1], "OnLeave")
    assert not shown(tip), "the tooltip stayed after the cursor left the tile"
    assert not tiles[1].fsHover
    # the picker closing under the cursor takes the tooltip with it
    fire_script(lua, tiles[0], "OnEnter")
    assert shown(tip)
    tb(lua).ClosePicker()
    assert not shown(tip), "the tooltip outlived the picker"


def check_the_picked_tile_is_marked_and_only_it():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"))
    tb(lua).Pick("earth", tid(lua, "Earthbind Totem"))
    tb(lua).OpenPicker("earth")
    tiles = [e for e in seq(tb(lua).Picker().fsEntries) if shown(e)]
    marks = [bool(shown(t.fsUnderline)) for t in tiles]
    assert marks == [False, True, False, False, False], f"marks {marks}"
    ring = [float(v) for v in seq(tiles[1].fsSkin.border.ring._vertex)]
    rest = [float(v) for v in seq(tiles[0].fsSkin.border.ring._vertex)]
    approx(ring[3], 0.75, "the picked tile's ring"), approx(rest[3], 0.35, "an ordinary tile's ring")
    assert ring[:3] != rest[:3], "the picked ring is not the element colour"
    click(lua, tiles[3])
    tb(lua).OpenPicker("earth")
    marks = [bool(shown(t.fsUnderline)) for t in [e for e in seq(tb(lua).Picker().fsEntries) if shown(e)]]
    assert marks == [False, False, False, True, False], f"the mark did not follow the pick: {marks}"


def check_the_flyout_chrome_follows_the_picker_and_the_bump():
    lua = all_known_with_lists()
    p = tp(lua)

    def col():
        v = p.FlyoutCol()
        return None if v is None else int(v)
    assert col() is None
    tb(lua).OpenPicker("earth")
    picker = tb(lua).Picker()
    assert col() == 2
    tiles = [e for e in seq(picker.fsEntries) if shown(e)]
    click(lua, tiles[0])
    assert not shown(picker) and col() is None, "a pick left the chimney standing"
    tb(lua).OpenPicker("earth")
    picker.Hide(picker)
    assert col() is None, "Escape left the chimney standing"
    tb(lua).OpenPicker("earth")
    idle = picker._scripts.OnUpdate
    for _ in range(40):
        idle(picker, 0.1)
    assert not shown(picker) and col() is None, "the idle close left the chimney standing"
    tb(lua).OpenPicker("earth")
    tb(lua).OpenPicker("fire")
    assert col() == 1, "the chimney did not move to the element whose picker opened"
    # another element's hover moves the one bump away; the chimney goes with it and returns with the bump
    water = by_key(lua, "water")
    enter(lua, water)
    assert col() is None and int(p.BumpCol()) == 3, "the chimney stands without its bump"
    over(water, False)
    fire_script(lua, water, "OnLeave")
    assert col() == 1, "the chimney did not come back with the open picker's bump"
    tb(lua).ClosePicker()
    assert col() is None


# --- the whole path, the way the mouse takes it ------------------------------------------------

STRATA = ["WORLD", "BACKGROUND", "LOW", "MEDIUM", "HIGH", "DIALOG", "FULLSCREEN", "FULLSCREEN_DIALOG", "TOOLTIP"]


def _strata(f):
    while f is not None:
        if f._strata:
            return STRATA.index(str(f._strata))
        f = f._parent
    return STRATA.index("MEDIUM")


def _chain_shown(f):
    while f is not None:
        if not f._shown:
            return False
        f = f._parent
    return True


class Mouse:
    """A cursor in design px (D coordinates). It finds the topmost mouse-enabled frame under it the way the
    engine does (strata, then frame level), moves each frame's IsMouseOver flag, and fires OnEnter / OnLeave
    when the target changes."""

    def __init__(self, lua):
        self.lua, self.target = lua, None

    def frames(self):
        out = []
        for f in g(self.lua)["__frames"].values():
            if f._kind in ("Texture", "FontString", "MaskTexture") or f is g(self.lua).UIParent:
                continue
            m = f._mouse
            if m is False or not (m or f._clicks):
                continue
            out.append(f)
        return out

    def rect(self, f):
        try:
            return csh.D(self.lua, f)
        except LuaError:
            return None

    def hit(self, x, y):
        best, key = None, None
        for f in self.frames():
            if not _chain_shown(f):
                continue
            d = self.rect(f)
            if d and d["x"] <= x < d["x"] + d["w"] and d["y"] <= y < d["y"] + d["h"]:
                k = (_strata(f), float(f._level or 0))
                if key is None or k >= key:
                    best, key = f, k
        return best

    def move(self, x, y):
        top = self.hit(x, y)
        for f in self.frames():
            d = self.rect(f)
            over(f, bool(d and _chain_shown(f) and d["x"] <= x < d["x"] + d["w"] and d["y"] <= y < d["y"] + d["h"]))
        same = (top is None and self.target is None) or (top is not None and self.target is not None
                                                        and sb.same(self.lua, top, self.target))
        if not same:
            if self.target is not None:
                fire_script(self.lua, self.target, "OnLeave")
            self.target = top
            if top is not None:
                fire_script(self.lua, top, "OnEnter")
        return top

    def tick(self, dt):
        for f in self.frames():
            if f._scripts.OnUpdate is not None and _chain_shown(f):
                f._scripts.OnUpdate(f, dt)


def _centre(lua, f):
    d = csh.D(lua, f)
    return d["x"] + d["w"] / 2, d["y"] + d["h"] / 2


def _walk(mouse, a, b, steps=60):
    for i in range(steps + 1):
        mouse.move(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
        mouse.tick(0.016)


def _end_to_end(open_by, scale=1.0):
    lua = boot(scale, learned=TOTEMS["earth"], lists=lists_for("earth"))
    lua.execute("local o = FS.TotemBar.Pick; __picked = {}; "
                "FS.TotemBar.Pick = function(k, id) __picked[#__picked + 1] = { k, id }; return o(k, id) end")
    b = by_key(lua, "earth")
    a = b.fsArrow
    mouse = Mouse(lua)
    start = _centre(lua, b)
    assert sb.same(lua, mouse.move(*start), b), "the button is not what the cursor hits on its face"
    assert shown(a), "the piece did not come up under the cursor"
    if open_by == "piece":
        _walk(mouse, start, _centre(lua, a))
        assert sb.same(lua, mouse.hit(*_centre(lua, a)), a), "something sits over the piece and eats its click"
        click(lua, a)
        here = _centre(lua, a)
    else:
        lua.execute("__alt = true")
        click(lua, b, "LeftButton", False)
        here = start
    picker = tb(lua).Picker()
    assert shown(picker), f"opening by the {open_by} did not open the picker"
    tiles = [e for e in seq(picker.fsEntries) if shown(e)]
    # the cursor goes from where it is, over the piece and the gap, onto the third tile; the picker must stay open
    for t in (tiles[0], tiles[2]):
        _walk(mouse, here, _centre(lua, t))
        here = _centre(lua, t)
        assert shown(picker), "the picker closed on the way to a tile"
        assert sb.same(lua, mouse.hit(*here), t), "the tile is not the topmost mouse target at its centre"
    for dx, dy in ((-12, -10), (12, -10), (-12, 10), (12, 10)):
        assert sb.same(lua, mouse.hit(here[0] + dx, here[1] + dy), tiles[2]), f"a frame covers part of the tile at {(dx, dy)}"
    assert int(g(lua).GameTooltip._spellID) == int(tiles[2].fsSpellID) and shown(g(lua).GameTooltip)
    assert shown(a) and int(tp(lua).BumpCol()) == 2 and int(tp(lua).FlyoutCol()) == 2
    for _ in range(80):
        mouse.tick(0.05)
    assert shown(picker), "the picker closed under the cursor"
    click(lua, mouse.hit(*here))
    got = [(str(x[1]), int(x[2])) for x in seq(g(lua).__picked)]
    assert got == [("earth", tid(lua, "Stoneclaw Totem"))], f"Pick was called with {got}"
    assert not shown(picker), "the picker stayed open after the pick"
    assert picks(lua).earth.name == "Stoneclaw Totem", "the pick was not saved"
    assert mc_calls(lua)[-1][:2] == (action_id(2), tid(lua, "Stoneclaw Totem")), "the multi-cast slot was not asked"


def check_the_whole_path_from_the_piece_click_to_a_picked_totem(scale):
    _end_to_end("piece", scale)


def check_the_whole_path_from_an_alt_click_to_a_picked_totem(scale):
    _end_to_end("alt", scale)


def check_toc_lists_the_totem_bar_after_the_seal_bar():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    t = "Modules/ActionBars/TotemBar.lua"
    assert t in mods, "TotemBar.lua is not in the .toc"
    for dep in ("Modules/ActionBars/StanceBar.lua", "Modules/ActionBars/ClassShoulder.lua",
                "Modules/ActionBars/SealBar.lua", "Modules/Pet/PetDock.lua", "Core/FrameHelpers.lua",
                "Modules/ActionBars/TotemPiece.lua"):
        assert dep in mods, f"{dep} is not in the .toc"
        assert mods.index(dep) < mods.index(t), f"{dep} must load before TotemBar.lua"
    assert mods.index("Modules/ActionBars/ClassShoulder.lua") < mods.index("Modules/ActionBars/TotemPiece.lua")


def check_no_em_dashes_in_the_new_files():
    for path in (TOTEMBAR, TOTEMPIECE, Path(__file__), HERE / "assets" / "generate_totem_glyphs.py", PIECE_GENERATOR):
        assert path.exists(), f"{path} is missing"
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), f"{path.name} has an em dash"


# ---------------------------------------------------------------------------------------------
# Usability feedback: out of mana -> blue, unusable -> grey, usable -> normal (the main bars' colours)
# ---------------------------------------------------------------------------------------------


def theme_color(lua, name):
    c = getattr(g(lua).FS.Theme, name)
    return (float(c[1]), float(c[2]), float(c[3]))


def tint_of(region):
    """The rgb a region was last tinted with; a region never tinted is plain white."""
    v = region._vertex
    return (1.0, 1.0, 1.0) if v is None else (float(v[1]), float(v[2]), float(v[3]))


def usable(lua, kind, key, ok, no_mana=False):
    lua.execute(f"__usable({kind!r}, {key}, {'true' if ok else 'false'}, {'true' if no_mana else 'false'})")


def use_mode(lua, mode):
    lua.execute(f"__use.mode = {('nil' if mode is None else repr(mode))}")


def use_count(lua, kind) -> int:
    return int(g(lua).__use.n[kind])


def same_rgb(a, b, what):
    for i in range(3):
        approx(a[i], b[i], what)


def check_the_main_bars_feedback_colours_live_in_the_theme():
    lua = all_known_with_lists()
    th = g(lua).FS.Theme
    assert theme_color(lua, "COLOR_OOM") == (0.5, 0.5, 1.0), "out of mana is not Blizzard's blue"
    assert theme_color(lua, "COLOR_UNUSABLE") == (0.4, 0.4, 0.4), "unusable is not Blizzard's grey"
    assert th.COLOR_OUT_OF_RANGE is not None
    src = (ADDON / "Modules/ActionBars/ActionBars.lua").read_text(encoding="utf-8")
    assert not re.search(r"COLOR_(OOM|UNUSABLE)\s*=\s*\{", src), "ActionBars.lua still carries its own colour literals"


def check_an_action_mode_element_tints_its_icon_by_the_slots_usability():
    lua = all_known_with_lists()
    b = by_key(lua, "earth")
    assert b.fsMode == "action"
    slot = action_id(2)
    assert tint_of(b.icon) == (1.0, 1.0, 1.0), "a usable totem is not plain"
    usable(lua, "action", slot, False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_OOM"), "out of mana")
    usable(lua, "action", slot, False, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_UNUSABLE"), "unusable")
    usable(lua, "action", slot, True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.icon), (1, 1, 1), "usable again")
    # the tint is per button: the fire totem asked its own slot
    usable(lua, "action", action_id(1), False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(by_key(lua, "fire").icon), theme_color(lua, "COLOR_OOM"), "fire out of mana")
    same_rgb(tint_of(b.icon), (1, 1, 1), "earth stayed usable")


def check_a_spell_mode_element_asks_the_spell_api_about_its_current_pick():
    lua = boot(learned=TOTEMS["earth"])
    b = by_key(lua, "earth")
    assert b.fsMode == "spell"
    lua.execute("__use_reset()")
    stone = tid(lua, "Stoneskin Totem")
    usable(lua, "spell", stone, False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_OOM"), "out of mana in spell mode")
    assert use_count(lua, "spell") > 0, "spell mode never asked the spell API"
    assert int(g(lua).__use.last.spell) == stone, "the spell API was not asked about the current pick"
    assert action_id(2) not in {int(k) for k in g(lua).__use.seen.action.keys()}, "spell mode asked about its action slot"
    # a new pick is judged on its own spell at once, with no usable event in between
    magma_free = tid(lua, "Earthbind Totem")
    usable(lua, "spell", magma_free, False, False)
    tb(lua).Pick("earth", magma_free)
    same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_UNUSABLE"), "the new pick is unusable")
    # the legacy API answers when C_Spell has none
    lua.execute("C_Spell.IsSpellUsable = nil; __use_reset()")
    usable(lua, "spell", magma_free, False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_OOM"), "legacy IsUsableSpell")
    assert use_count(lua, "legacy") > 0


def check_an_action_mode_element_never_asks_the_spell_api():
    lua = all_known_with_lists()
    lua.execute("__use_reset()")
    fire(lua, "SPELL_UPDATE_USABLE")
    fire(lua, "ACTIONBAR_UPDATE_USABLE")
    asked = {int(k) for k in g(lua).__use.seen.action.keys()}
    assert {action_id(s) for s in SLOT.values()} <= asked, f"the four multi-cast slots were not all asked: {sorted(asked)}"
    # only the set drop and recall (plain spell buttons) ask the spell API
    spells = {int(k) for k in g(lua).__use.seen.spell.keys()}
    assert spells == {CALL, RECALL}, f"the spell API was asked about {sorted(spells)}"


def check_the_set_drop_and_recall_tint_their_glyph_and_leave_the_dark_plate_alone():
    lua = all_known_with_lists()
    for key, sid in (("set", CALL), ("recall", RECALL)):
        b = by_key(lua, key)
        base = tint_of(b.fsGlyph)
        want = tuple(float(b.fsColor[i]) for i in (1, 2, 3))
        same_rgb(base, want, f"{key} glyph at rest")
        plate = [float(x) for x in seq(b.icon._color)]
        usable(lua, "spell", sid, False, True)
        fire(lua, "SPELL_UPDATE_USABLE")
        same_rgb(tint_of(b.fsGlyph), theme_color(lua, "COLOR_OOM"), f"{key} glyph out of mana")
        approx(b.fsGlyph._vertex[4], 0.95, f"{key} glyph alpha")
        usable(lua, "spell", sid, False, False)
        fire(lua, "SPELL_UPDATE_USABLE")
        same_rgb(tint_of(b.fsGlyph), theme_color(lua, "COLOR_UNUSABLE"), f"{key} glyph unusable")
        usable(lua, "spell", sid, True, False)
        fire(lua, "SPELL_UPDATE_USABLE")
        same_rgb(tint_of(b.fsGlyph), want, f"{key} glyph usable again")
        approx(b.fsGlyph._vertex[4], 0.95, f"{key} glyph alpha restored")
        assert [float(x) for x in seq(b.icon._color)] == plate, f"{key}: the dark plate changed"
        assert tint_of(b.icon) == (1.0, 1.0, 1.0), f"{key}: the plate was tinted"


def check_the_tint_composes_with_the_element_glyph_and_underline_colours():
    lua = all_known_with_lists()
    for key in SLOT:
        b = by_key(lua, key)
        usable(lua, "action", action_id(SLOT[key]), False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    for key in SLOT:
        b = by_key(lua, key)
        want = tuple(float(b.fsColor[i]) for i in (1, 2, 3))
        same_rgb(tint_of(b.fsGlyph), want, f"{key}: the crown lost its element colour")
        approx(b.fsGlyph._vertex[4], 0.95, f"{key}: crown alpha")
        c = [float(x) for x in seq(b.fsUnderline._color)]
        same_rgb(c, want, f"{key}: the underline lost its element colour")
        same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_OOM"), f"{key}: the icon is not blue")


def check_a_locked_button_stays_as_it_is_whatever_usability_says():
    lua = boot(learned=TOTEMS["earth"], lists=lists_for("earth"), spells=("Call of the Elements",))
    recall, fire_b = by_key(lua, "recall"), by_key(lua, "fire")
    for b in (recall, fire_b):
        assert b.fsLocked and shown(b.fsMold), f"{b.fsKey} is not locked"
    lua.execute("__use.default = nil; __use_reset()")
    for sid in (RECALL, 3599):
        usable(lua, "spell", sid, False, True)
    usable(lua, "action", action_id(1), False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    for b in (recall, fire_b):
        want = tuple(float(b.fsColor[i]) for i in (1, 2, 3))
        same_rgb(tint_of(b.fsGlyph), want, f"locked {b.fsKey} glyph")
        assert tint_of(b.icon) == (1.0, 1.0, 1.0), f"locked {b.fsKey} icon"
        assert shown(b.fsMold) and shown(b.fsLockText) and float(b._alpha) == 0.4, f"locked {b.fsKey} look changed"
    # a tint taken while the button was live is dropped when it locks (the mold is not blue)
    lua2 = all_known_with_lists()
    b = by_key(lua2, "recall")
    usable(lua2, "spell", RECALL, False, True)
    fire(lua2, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(b.fsGlyph), theme_color(lua2, "COLOR_OOM"), "live tint")
    lua2.execute('__unlearn("Totemic Recall")')
    fire(lua2, "SPELLS_CHANGED")
    assert b.fsLocked
    same_rgb(tint_of(b.fsGlyph), tuple(float(b.fsColor[i]) for i in (1, 2, 3)), "a locked glyph kept the tint")


def check_a_secret_or_missing_answer_leaves_the_current_tint():
    lua = all_known_with_lists()
    earth, recall = by_key(lua, "earth"), by_key(lua, "recall")
    usable(lua, "action", action_id(2), False, True)
    usable(lua, "spell", RECALL, False, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    oom, grey = theme_color(lua, "COLOR_OOM"), theme_color(lua, "COLOR_UNUSABLE")
    same_rgb(tint_of(earth.icon), oom, "start"), same_rgb(tint_of(recall.fsGlyph), grey, "start")
    lua.execute(f"__use.throwOn[{action_id(2)}] = true; __use.throwOn[{RECALL}] = true")
    for mode in ("secret", "throw", "none"):
        use_mode(lua, mode)
        fire(lua, "SPELL_UPDATE_USABLE")
        same_rgb(tint_of(earth.icon), oom, f"{mode}: the icon guessed")
        same_rgb(tint_of(recall.fsGlyph), grey, f"{mode}: the glyph guessed")
    # in combat too, where the client hands back secrets
    set_combat(lua, True)
    use_mode(lua, "secret")
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(earth.icon), oom, "combat secret")
    # a plain answer in combat is a texture write and lands
    use_mode(lua, None)
    usable(lua, "action", action_id(2), True, False)
    fire(lua, "ACTIONBAR_UPDATE_USABLE")
    same_rgb(tint_of(earth.icon), (1, 1, 1), "a plain answer in combat")
    assert blocked(lua) == 0, "usability touched a protected frame in combat"
    # one half secret: not enough mana is plainly true, so it is blue whatever the other half is
    lua.execute("""
        local real = IsUsableAction
        function IsUsableAction(a) return __SECRET, true end
    """)
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(earth.icon), oom, "not enough mana plainly true")
    lua.execute("function IsUsableAction(a) return false, __SECRET end")
    fire(lua, "SPELL_UPDATE_USABLE")
    same_rgb(tint_of(earth.icon), theme_color(lua, "COLOR_UNUSABLE"),
             "a secret mana flag with a plainly unusable spell is grey, like the main bars")


def check_the_tint_refreshes_on_each_usability_event_and_leaving_combat():
    for event in ("SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_USABLE", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED"):
        lua = all_known_with_lists()
        b = by_key(lua, "water")
        usable(lua, "action", action_id(3), False, True)
        if event == "PLAYER_REGEN_ENABLED":
            set_combat(lua, True)
            set_combat(lua, False)
        fire(lua, event)
        same_rgb(tint_of(b.icon), theme_color(lua, "COLOR_OOM"), f"{event} did not refresh the tint")
    # a sync (learning, a rescale) paints it too, without a usability event
    lua = all_known_with_lists()
    usable(lua, "action", action_id(3), False, False)
    fire(lua, "SPELLS_CHANGED")
    same_rgb(tint_of(by_key(lua, "water").icon), theme_color(lua, "COLOR_UNUSABLE"), "a sync")


def check_the_usability_refresh_allocates_nothing_and_rewrites_nothing_unchanged():
    for combat in (False, True):
        lua = all_known_with_lists()
        usable(lua, "action", action_id(2), False, True)
        usable(lua, "spell", RECALL, False, False)
        fire(lua, "SPELL_UPDATE_USABLE")
        if combat:
            set_combat(lua, True)
        lua.execute("""
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            local update = FS.TotemBar.UpdateUsable
            for i = 1, 50 do update() end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for i = 1, 400 do update() end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 refreshes allocated {float(g(lua).__grew):.0f} bytes"


def check_the_usability_path_has_no_per_frame_script():
    src = TOTEMBAR.read_text(encoding="utf-8")
    body = src[src.index("local function UpdateUsable"):src.index("local function UpdateAllUsable")]
    assert "OnUpdate" not in body, "usability polls per frame"


def check_the_picked_tiles_underline_is_scaled_with_the_tile(scale):
    lua = boot(scale, learned=TOTEMS["earth"], lists=lists_for("earth"))
    tb(lua).OpenPicker("earth")
    picker = tb(lua).Picker()
    tiles = [e for e in seq(picker.fsEntries) if shown(e)]
    for tile in tiles:
        pts = {str(p.point): p for p in seq(tile.fsUnderline._points)}
        assert set(pts) == {"BOTTOMLEFT", "BOTTOMRIGHT"}, f"underline anchors {sorted(pts)}"
        approx(pts["BOTTOMLEFT"].x, 5 * scale, "underline left inset"), approx(pts["BOTTOMLEFT"].y, 2 * scale, "underline lift")
        approx(pts["BOTTOMRIGHT"].x, -5 * scale, "underline right inset"), approx(pts["BOTTOMRIGHT"].y, 2 * scale, "underline lift (right)")
        approx(tile.fsUnderline._h, 2 * scale, "underline height")
        approx(tile._w, 32 * scale, "tile width")



CHECKS = [
    check_six_named_secure_buttons_in_the_fixed_order_built_once,
    check_only_a_shaman_gets_a_tab,
    check_action_mode_when_the_multicast_bar_is_usable,
    check_spell_mode_when_there_is_no_usable_multicast_bar,
    check_no_multicast_api_at_all_degrades_to_spell_mode,
    check_a_mode_change_rewrites_the_attributes_cleanly,
    check_listeners_hear_each_element_button_after_its_attributes_settle_and_never_in_combat,
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
    check_the_arrow_shows_only_while_the_cursor_is_over_the_button_or_the_arrow,
    check_a_locked_button_never_shows_an_arrow,
    check_the_arrow_shows_and_hides_in_combat_without_a_protected_touch,
    check_shift_right_click_dismisses_all_four_totems_through_hidden_secure_buttons,
    check_a_macro_click_with_the_use_key_down_cvar_on_still_destroys_the_totem,
    check_the_dismiss_all_attributes_are_written_out_of_combat_only,
    check_a_locked_element_carries_no_dismiss_all,
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
    check_bindings_xml_declares_the_totem_commands_after_the_seals,
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
    check_the_piece_is_made_of_plain_regions_of_the_plain_arrow_button,
    check_the_piece_shows_on_button_hover_dim_and_goes_lit_on_the_piece_and_hides_away,
    check_the_chevron_points_up_and_flips_down_while_the_picker_is_open,
    check_the_bump_stands_only_around_the_hovered_button_and_the_rail_opens_under_it,
    check_hovering_another_element_never_leaves_an_open_picker_without_its_bump,
    check_escape_closing_the_picker_drops_the_bump_and_flips_the_chevron_back,
    check_the_tab_builds_without_the_piece_file,
    check_the_fire_bump_uses_the_6_px_left_shoulder_and_the_others_4,
    check_the_piece_and_the_bump_work_in_combat_without_a_protected_touch,
    check_opening_the_rail_refuses_bad_numbers_and_a_tab_that_is_not_standing_has_no_bump,
    check_the_baked_art_and_the_lua_numbers_agree,
    check_the_chimney_grows_out_of_the_bump_as_one_outline_earth,
    check_the_chimney_grows_out_of_the_bump_as_one_outline_fire,
    check_the_flyout_numbers_are_the_v3_mockups,
    check_the_picked_tile_is_marked_and_only_it,
    check_the_flyout_chrome_follows_the_picker_and_the_bump,
    check_toc_lists_the_totem_bar_after_the_seal_bar,
    check_no_em_dashes_in_the_new_files,
    check_the_main_bars_feedback_colours_live_in_the_theme,
    check_an_action_mode_element_tints_its_icon_by_the_slots_usability,
    check_a_spell_mode_element_asks_the_spell_api_about_its_current_pick,
    check_an_action_mode_element_never_asks_the_spell_api,
    check_the_set_drop_and_recall_tint_their_glyph_and_leave_the_dark_plate_alone,
    check_the_tint_composes_with_the_element_glyph_and_underline_colours,
    check_a_locked_button_stays_as_it_is_whatever_usability_says,
    check_a_secret_or_missing_answer_leaves_the_current_tint,
    check_the_tint_refreshes_on_each_usability_event_and_leaving_combat,
    check_the_usability_refresh_allocates_nothing_and_rewrites_nothing_unchanged,
    check_the_usability_path_has_no_per_frame_script,
]
SCALED_CHECKS = [
    check_the_picked_tiles_underline_is_scaled_with_the_tile,
    check_the_piece_hit_area_is_38_by_13_flush_with_the_button_top,
    check_clicks_on_the_button_face_never_land_on_the_piece,
    check_the_shoulder_is_the_six_by_one_block_and_the_buttons_sit_inside_it,
    check_the_picker_is_an_icon_only_column_of_32_px_tiles_on_the_buttons_axis,
    check_a_tile_shows_the_real_spell_tooltip_to_the_right_and_hides_it_on_leave,
    check_the_whole_path_from_the_piece_click_to_a_picked_totem,
    check_the_whole_path_from_an_alt_click_to_a_picked_totem,
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
