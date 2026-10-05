#!/usr/bin/env python3
"""Runs the real SealBar.lua (Paladin SEAL and AURA buttons) headless, next to the real
FrameHelpers.lua, ActionBars.lua, StanceBar.lua, PetActionBar.lua and Console.lua.

The buttons are the Paladin shoulder of the approved Gunsight mockup (`LS_*`, `SEALS`, `AURAS`,
`lsBtn`, the seal bar over the aura bar), so Parker can bind them with Blizzard's built-in Quick
Keybind mode. The checks read the mockup's own numbers back out of the HTML, so a mockup move
fails here:

  * 14 named secure buttons (`FSSealButton1..7`, `FSAuraButton1..7`), built once, type spell,
    clicks AnyUp+AnyDown;
  * a SEAL button's `spell` is the Nth KNOWN seal name in mockup order; unknown seals are hidden
    and the known ones packed left; spellbook events re-evaluate;
  * an AURA button is a SHAPESHIFT FORM (auras are forms on this client): one per form i of
    GetNumShapeshiftForms(), `spell` = the 4th return of GetShapeshiftFormInfo(i), ordered by the
    mockup's aura order when the form's spell name matches it, each button keeping its own form
    index i for its command `SHAPESHIFTBUTTONi`; the active form lights a wash;
  * the active form lights an ADD wash (alpha .4, the border colour) and a brighter ring;
  * every button has a cooldown swipe fed from the spell cooldown (duration object, else the
    legacy secret-guarded path), refreshed on SPELL_UPDATE_COOLDOWN, legal in combat;
  * every protected operation (SetAttribute, Show, Hide, SetPoint, SetSize) waits out combat and
    replays at PLAYER_REGEN_ENABLED;
  * the SEAL Quick Keybind command is `CLICK FSSealButtonN:LeftButton`, declared in Bindings.xml
    (seals only: an aura key is Blizzard's own SHAPESHIFTBUTTONi);
  * the shoulder stands on the Console's top edge where the mockup puts it (above the stance bar's
    seat when the Console is not drawn), through two small
    seat functions (`SealBar.HostPoint`, `SealBar.SlotPoint`) a later class shoulder can replace;
  * a Paladin's stance bar hands its forms over to this bar, across every rebuild.

The mock is strict and is NOT the real client. SEALBAR_LUA, STANCEBAR_LUA, BINDINGS_XML and TOC_FILE point the harness at
mutant copies (a check must fail on a broken one).

    python3 tools/sealbar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "addon" / "ForeverSynthwave"
MOCKUP = Path(__file__).resolve().parent.parent / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"
TOC = Path(os.environ.get("TOC_FILE", ADDON / "ForeverSynthwave.toc"))
BINDINGS = Path(os.environ.get("BINDINGS_XML", ADDON / "Bindings.xml"))
SEALBAR = Path(os.environ.get("SEALBAR_LUA", ADDON / "SealBar.lua"))
STANCEBAR = Path(os.environ.get("STANCEBAR_LUA", ADDON / "StanceBar.lua"))
CONSOLE = Path(os.environ.get("CONSOLE_LUA", ADDON / "Console.lua"))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


abh = _load("actionbars_harness", "actionbars-harness.py")
ch = _load("console_harness", "console-harness.py")

SCALES = (1 / 1.2, 1.0)

# English spell names, by the mockup's ids (the lead's list; the harness owns the id to name map,
# the ORDER comes from the mockup).
SEAL_NAMES = {
    "righteousness": "Seal of Righteousness", "crusader": "Seal of the Crusader", "fury": "Seal of Fury",
    "command": "Seal of Command", "light": "Seal of Light", "wisdom": "Seal of Wisdom",
    "justice": "Seal of Justice",
}
AURA_NAMES = {
    "dv": "Devotion Aura", "rt": "Retribution Aura", "cn": "Concentration Aura",
    "sh": "Shadow Resistance Aura", "fr": "Frost Resistance Aura", "fi": "Fire Resistance Aura",
    "sa": "Sanctity Aura",
}


# ---------------------------------------------------------------------------------------------
# The mockup's numbers
# ---------------------------------------------------------------------------------------------


def _m(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"mockup: cannot find {what} (pattern {pattern!r}); the mockup changed shape")
    return m


def mockup() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    ls = _m(r"var LS_X=(\d+),LS_PAD=(\d+),LS_PT=(\d+),LS_PB=(\d+),LS_BTN=(\d+),LS_BG=([\d.]+),", src, "LS_ constants")
    x, pad, pt, pb, btn, bg = (float(v) for v in ls.groups())
    sb = _m(r"var SB_S=(\d+)\*AU,SB_G=([\d.]+)\*AU;", src, "SB_S / SB_G")
    assert float(sb.group(1)) == btn and float(sb.group(2)) == bg, "SB_S / SB_G no longer equal LS_BTN / LS_BG"
    # the paladin shoulder: ONE block, 7 buttons wide, 2 rows
    _m(r"else if\(CLS==='pl'\)o\.push\(\{id:'sl',x:LS_X,n:7,rows:2\}\)", src, "paladin shoulder (7 wide, 2 rows)")
    # seals are row 0 (the top row), auras row 1 (against the chassis)
    _m(r"for\(j=0;j<SEAL_IDS\.length;j\+\+\)\{.*?xy=lsBtn\(q,j,0\);", src, "seal row 0")
    _m(r"for\(j=0;j<AURAS\.length;j\+\+\)\{xy=lsBtn\(q,j,1\);", src, "aura row 1")
    _m(r"function lsBtn\(q,col,row\)\{return \[\(q\.x\+LS_PAD\)\*AU\+col\*\(SB_S\+SB_G\),"
       r"lsBase\(\)-\(q\.h-LS_PT\)\*AU\+row\*\(SB_S\+SB_G\)\];\}", src, "lsBtn")
    _m(r"d\.h=LS_PT\+d\.rows\*LS_BTN\+\(d\.rows-1\)\*LS_BG\+LS_PB;", src, "shoulder height")
    _m(r"function lsRowW\(n\)\{return 2\*LS_PAD\+n\*LS_BTN\+\(n-1\)\*LS_BG;\}", src, "shoulder width")
    seal_ids = re.findall(r"'(\w+)'", _m(r"var SEAL_IDS=\[([^\]]*)\];", src, "SEAL_IDS").group(1))
    colors = {}
    block = _m(r"var SEALS=\{(.*?)\n\};", src, "SEALS").group(1)
    for sid, hexcol in re.findall(r"(\w+):\{n:'\w+',c:'#([0-9a-fA-F]{6})'", block):
        colors[sid] = tuple(int(hexcol[i:i + 2], 16) / 255 for i in (0, 2, 4))
    aura_ids = re.findall(r"\{id:'(\w\w)',k:'au\w+'", _m(r"var AURAS=\[(.*?)\];", src, "AURAS").group(1))
    # the dock offset: the chassis left, in design px (the PetDock check's derivation, with LS_X)
    def expr(name: str) -> str:
        mm = re.search(rf"\b{name}\s*=\s*([^,;]+)", src)
        assert mm, f"the mockup no longer defines {name}"
        return mm.group(1)
    au = 1 / 1.28
    assert expr("AU") == "1/1.28", "the mockup's design to image scale changed"
    env = {"__builtins__": {}, "AU": au}
    ab_x0, ab_bx = eval(expr("AB_X0"), env), eval(expr("AB_BX"), env)
    spine, cpad, marg = (float(expr(n)) for n in ("CN_SPINE", "CN_PAD", "CN_MARG"))
    chassis_left = ab_x0 - (spine - 7.2) / 2 * au + ab_bx - (cpad + marg) * au
    return dict(
        X=x, PAD=pad, PT=pt, PB=pb, BTN=btn, BG=bg, SEAL_IDS=seal_ids, SEAL_COLORS=colors,
        AURA_IDS=aura_ids, DX=(x * au - chassis_left) / au,
    )


MU = mockup()


def expected_seals() -> list[str]:
    return [SEAL_NAMES[i] for i in MU["SEAL_IDS"]]


def expected_auras() -> list[str]:
    return [AURA_NAMES[i] for i in MU["AURA_IDS"]]


# ---------------------------------------------------------------------------------------------
# The world: the actionbars mock plus the spellbook, the class and the real files
# ---------------------------------------------------------------------------------------------

MOCKS = r"""
__class = %(klass)r
if __class == "THROW" then
    function UnitClass() error("UnitClass blew up") end
elseif __class == "SECRET" then
    function UnitClass() return "Paladin", __SECRET end
else
    function UnitClass() return "Paladin", __class end
end
-- name -> id when the spell NAME resolves; id -> true when IsPlayerSpell says known
__spells, __learned = {}, {}
__nextId = 300
function __learn(name, resolves, knows)
    __nextId = __nextId + 1
    if resolves ~= false then __spells[name] = __nextId end
    if knows ~= false then __learned[__nextId] = true end
    return __nextId
end
function __forget(name)
    local id = __spells[name]
    __spells[name] = nil
    if id then __learned[id] = nil end
end
__infoMode, __knownMode = nil, nil
-- shapeshift forms (the auras): id <-> English name, ids handed out per name on first use
__formIds, __idNames, __nextFormId, __forms, __formMode = {}, {}, 700, nil, nil
function __formId(name)
    if not __formIds[name] then
        __nextFormId = __nextFormId + 1
        __formIds[name] = __nextFormId
        __idNames[__nextFormId] = name
    end
    return __formIds[name]
end
function __set_forms(list)
    __forms = {}
    for i, f in ipairs(list) do
        local id = __formId(f[1])
        __forms[i] = { id = id, active = f[2], icon = 8000 + id }
    end
end
C_Spell = {
    GetSpellInfo = function(arg)
        if __infoMode == "secret" then return __SECRET end
        if __infoMode == "throw" then error("GetSpellInfo blew up") end
        if type(arg) == "number" then
            local n = __idNames[arg]
            if n then return { name = n, spellID = arg, iconID = 9000 + arg } end
            return nil
        end
        local id = __spells[arg]
        if id then return { name = arg, spellID = id, iconID = 9000 + id } end
    end,
}
function GameTooltip:SetShapeshift(i) self._shapeshift = i end
-- the real Cooldown:Clear() drops both the object and the times
do
    local create = CreateFrame
    function CreateFrame(kind, ...)
        local f = create(kind, ...)
        if kind == "Cooldown" then
            function f:Clear() self._cdObj = nil; self._cd = nil; self._clears = (self._clears or 0) + 1 end
        end
        return f
    end
end
-- spell cooldowns: id -> { start, duration }; a duration-object API and a legacy table API
__cd, __cdMode = {}, nil
C_Spell.GetSpellCooldownDuration = function(id)
    __cdReads = (__cdReads or 0) + 1
    if __cdMode == "throw" then error("duration API blew up") end
    if __cdMode == "secretobj" then return __SECRET end
    local c = __cd[id]
    if c then return { cdFor = id, start = c[1], duration = c[2] } end
end
C_Spell.GetSpellCooldown = function(id)
    if __cdMode == "secret" then return { startTime = __SECRET, duration = __SECRET, isEnabled = true } end
    local c = __cd[id]
    if c then return { startTime = c[1], duration = c[2], isEnabled = __cdMode ~= "disabled" } end
    return { startTime = 0, duration = 0, isEnabled = true }
end
-- the stock stance bar (an Edit Mode action bar) with one stock button
StanceBar = CreateFrame("Frame", "StanceBar", UIParent)
StanceBar:EnableMouse(true)
StanceButton1 = CreateFrame("CheckButton", "StanceButton1", StanceBar)
StanceButton1:EnableMouse(true)
-- a plain number the secret guard treats as secret (a secret number is still a number to type())
local baseIsSecret = FS.IsSecret
FS.IsSecret = function(v) return baseIsSecret(v) or v == 424242 end
if %(forms)s then
    __set_forms(%(forms)s)
    function GetNumShapeshiftForms()
        if __formMode == "num_throw" then error("GetNumShapeshiftForms blew up") end
        if __formMode == "num_secret" then return 424242 end
        return #__forms
    end
    function GetShapeshiftFormInfo(i)
        if __formMode == "info_throw" then error("GetShapeshiftFormInfo blew up") end
        local f = __forms[i]
        if not f then return end
        local id, active = f.id, f.active
        if __formMode == "id_secret" then id = __SECRET end
        if __formMode == "active_secret" then active = __SECRET end
        if __formMode == "active_nil" then active = nil end
        local icon = f.icon
        if __formMode == "icon_secret" then icon = 424242 end
        return icon, active, true, id
    end
    -- the form's own cooldown: index -> { start, duration, enabled } (legacy shape, like the stance bar's)
    __fcd = {}
    function GetShapeshiftFormCooldown(i)
        if __cdMode == "secret" then return __SECRET, __SECRET, 1 end
        local c = __fcd[i]
        if c then return c[1], c[2], 1 end
        return 0, 0, 1
    end
    function GetShapeshiftForm()
        if __curMode == "throw" then error("GetShapeshiftForm blew up") end
        if __curMode == "secret" then return __SECRET end
        for i, f in ipairs(__forms) do if f.active then return i end end
        return 0
    end
end
function IsPlayerSpell(id)
    if __knownMode == "secret" then return __SECRET end
    if __knownMode == "throw" then error("IsPlayerSpell blew up") end
    return __learned[id] or false
end
function GameTooltip:SetSpellByID(id) self._spellID = id end
for _, name in ipairs(%(known)s) do __learn(name) end
if %(combat)s then __combat = true end
"""


def lua_list(names) -> str:
    return "{" + ",".join(f'"{n}"' for n in names) + "}"


def lua_forms(forms) -> str:
    """forms: None (keep the mock's default two forms) or a list of names / (name, active)."""
    if forms is None:
        return "nil"
    items = []
    for f in forms:
        name, active = (f, False) if isinstance(f, str) else f
        items.append('{"%s",%s}' % (name, "true" if active else "false"))
    return "{" + ",".join(items) + "}"


def boot(scale: float = 1.0, *, klass: str = "PALADIN", known=None, combat: bool = False,
         console: bool = True, sealbar: bool = True, geometry: bool = True, spellbook: bool = True,
         forms=None, extra_lua: str = "", extra_files: tuple = (), pre_login: str = ""):
    """The actionbars mock with the Console prelude, then the real files. `known` defaults to
    every seal; `forms` (names or (name, active) pairs, in FORM INDEX order) defaults to every aura
    in mockup order for a Paladin and to the mock's own two forms for any other class.
    `extra_lua` runs and `extra_files` (paths) load after the pet action bar and before SealBar (the
    class shoulder harness puts PetDock.lua and ClassShoulder.lua there); `pre_login` runs just
    before the login event."""
    if known is None:
        known = expected_seals()
    if forms is None and klass == "PALADIN":
        forms = expected_auras()
    prelude = ch.make_prelude(scale, MOCKS % dict(klass=klass, known=lua_list(known),
                                                  combat="true" if combat else "false",
                                                  forms=lua_forms(forms)))
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(abh.MOCK)
    lua.execute(prelude)
    lua.execute("__install_qk()")
    if not spellbook:
        lua.execute("IsPlayerSpell = nil")      # no spellbook API at all: a name that resolves is known
    load = lua.eval("__load")
    theme_src = (ADDON / "Theme.lua").read_text(encoding="utf-8")
    defs = lua.table_from({n: abh._extract_theme_function(theme_src, n) for n in abh.THEME_FUNCTIONS})
    local_defs = [abh._extract_theme_local_function(theme_src, n) for n in abh.THEME_LOCAL_FUNCTIONS]
    lua.eval("__load_theme_functions")(defs, lua.table_from(list(abh.THEME_FUNCTIONS)), lua.table_from(local_defs))
    consts = [abh._extract_theme_constant(theme_src, n) for n in abh.THEME_CONSTANTS]
    lua.eval("__load_theme_constants")(lua.table_from(consts))
    files = [ADDON / "FrameHelpers.lua", ADDON / "ActionBars.lua"]
    if console:
        files.append(CONSOLE)
    files += [STANCEBAR, ADDON / "PetActionBar.lua"]
    for path in files:
        load(path.name, path.read_text(encoding="utf-8"))
    if extra_lua:
        lua.execute(extra_lua)
    for path in extra_files:
        load(path.name, path.read_text(encoding="utf-8"))
    if not geometry:
        # ActionBars never tells anyone about its seats (the stack failed to build, say)
        lua.execute("FS.ActionBars.OnGeometry = function() end")
    if sealbar:
        load(SEALBAR.name, SEALBAR.read_text(encoding="utf-8"))
    if pre_login:
        lua.execute(pre_login)
    lua.execute("__login()")
    return lua


def g(lua):
    return lua.globals()


def seal(lua, i):
    return g(lua)[f"FSSealButton{i}"]


def aura(lua, i):
    return g(lua)[f"FSAuraButton{i}"]


def spell_of(btn):
    return btn._attrs["spell"]


def shown(btn) -> bool:
    return bool(btn._shown)


def same(lua, a, b) -> bool:
    return bool(lua.eval("rawequal")(a, b))


def set_cd(lua, spell_id, start=None, duration=None):
    """Sets (or with no times clears) the mock cooldown of a spell id."""
    value = "nil" if start is None else f"{{ {start}, {duration} }}"
    lua.execute(f"__cd[{int(spell_id)}] = {value}")


def seal_id(lua, name) -> int:
    return int(g(lua).__spells[name])


def cd_of(btn):
    """What the swipe was last handed: ('obj', id), ('time', start, duration) or None."""
    cd = btn.cooldown
    if cd._cdObj is not None:
        return ("obj", int(cd._cdObj.cdFor))
    if cd._cd is not None:
        return ("time", cd._cd[1], cd._cd[2])
    return None


def form_id(lua, name) -> int:
    return int(lua.eval("__formId")(name))


def set_forms(lua, forms):
    lua.execute(f"__set_forms({lua_forms(forms)})")


def form_mode(lua, mode):
    lua.execute(f"__formMode = {'nil' if mode is None else repr(mode).replace(chr(39), chr(34))}")


def fire(lua, event):
    lua.eval("__fire_event")(event)


def set_combat(lua, on: bool):
    lua.execute(f"__combat = {'true' if on else 'false'}")


def blocked(lua) -> int:
    return int(lua.eval("__blocked"))


def approx(a, b, what, tol=1e-3):
    assert abs(float(a) - float(b)) <= tol, f"{what}: {a} != {b}"


def top_level(frame) -> int:
    """The highest frame level in `frame`'s subtree (child frames only)."""
    best = frame._level
    for i in range(1, len(frame._regions) + 1):
        child = frame._regions[i]
        if child._kind not in ("Texture", "FontString", "MaskTexture"):
            best = max(best, top_level(child))
    return best


def all_buttons(lua):
    return [seal(lua, i) for i in range(1, 8)] + [aura(lua, i) for i in range(1, 8)]


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------


def check_fourteen_named_secure_buttons_built_once():
    lua = boot()
    for i in range(1, 8):
        for name in (f"FSSealButton{i}", f"FSAuraButton{i}"):
            btn = g(lua)[name]
            assert btn is not None, f"{name} was not built"
            assert btn._secure, f"{name} is not a secure template button"
            assert btn._attrs["type"] == "spell", f"{name} type is {btn._attrs['type']!r}"
            clicks = [btn._clicks[k] for k in range(1, len(btn._clicks) + 1)]
            assert clicks == ["AnyUp", "AnyDown"], f"{name} clicks {clicks}"
            assert btn._attrs["useOnKeyDown"] is None, f"{name} sets useOnKeyDown"
    frames = [f for f in g(lua).__frames.values() if f._name and re.match(r"FS(Seal|Aura)Button\d$", f._name)]
    assert len(frames) == 14, f"{len(frames)} named seal/aura frames, expected exactly 14"
    # a second pass over every event builds nothing new
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "UPDATE_BINDINGS"):
        fire(lua, event)
    frames = [f for f in g(lua).__frames.values() if f._name and re.match(r"FS(Seal|Aura)Button\d$", f._name)]
    assert len(frames) == 14, "an event rebuilt a named button"


def check_known_spells_pack_left_in_mockup_order():
    seals, auras = expected_seals(), expected_auras()
    seal_idx = [0, 3, 5]                        # Righteousness, Command, Wisdom: buttons 1, 4, 6
    want_auras = [auras[0], auras[2], auras[6]]
    lua = boot(known=[seals[i] for i in seal_idx], forms=want_auras)
    for i in range(1, 8):
        sb, ab = seal(lua, i), aura(lua, i)
        if (i - 1) in seal_idx:
            slot = seal_idx.index(i - 1) + 1
            assert shown(sb) and spell_of(sb) == seals[i - 1], f"FSSealButton{i}: {spell_of(sb)!r}"
            approx(sb._points[1].x, slot_x(slot), f"FSSealButton{i} seat", 0.01)
        else:
            assert not shown(sb) and spell_of(sb) is None, f"FSSealButton{i} should be inert, has {spell_of(sb)!r}"
        if i <= 3:
            assert shown(ab) and spell_of(ab) == form_id(lua, want_auras[i - 1]), f"aura slot {i}: {spell_of(ab)!r}"
        else:
            assert not shown(ab) and spell_of(ab) is None, f"aura slot {i} should be empty, has {spell_of(ab)!r}"


def check_all_known_fills_every_slot_in_mockup_order():
    lua = boot()
    for i, name in enumerate(expected_seals(), 1):
        assert spell_of(seal(lua, i)) == name, f"seal {i}: {spell_of(seal(lua, i))!r} != {name!r}"
    for i, name in enumerate(expected_auras(), 1):
        want = form_id(lua, name)
        assert spell_of(aura(lua, i)) == want, f"aura {i}: {spell_of(aura(lua, i))!r} != {want!r} ({name})"
        assert isinstance(spell_of(aura(lua, i)), (int, float)), "an aura casts by its form spell ID, not a name"
    assert all(shown(b) for b in all_buttons(lua)), "a button with a known spell is hidden"


def check_nothing_known_shows_nothing():
    lua = boot(known=[], forms=[])
    assert not any(shown(b) for b in all_buttons(lua)), "a button shows with no known spell"
    assert all(spell_of(b) is None for b in all_buttons(lua)), "a button keeps a spell attribute with none known"


def check_known_needs_both_the_name_and_the_spellbook():
    seals = expected_seals()
    lua = boot(known=[])
    g(lua).__learn(seals[0], True, False)    # the name resolves, the spellbook says no
    g(lua).__learn(seals[1], False, True)    # the spellbook says yes for an id the name never resolves
    g(lua).__learn(seals[2], True, True)
    fire(lua, "SPELLS_CHANGED")
    assert spell_of(seal(lua, 3)) == seals[2], f"FSSealButton3 holds {spell_of(seal(lua, 3))!r}"
    approx(seal(lua, 3)._points[1].x, slot_x(1), "the only known seal packs to slot 1", 0.01)
    assert not shown(seal(lua, 1)) and not shown(seal(lua, 2)), (
        "an unlearned name or an unresolved name showed a button")


def check_a_client_with_no_spellbook_api_trusts_the_name():
    seals = expected_seals()
    lua = boot(known=[seals[0]], spellbook=False)
    assert shown(seal(lua, 1)) and spell_of(seal(lua, 1)) == seals[0], "a resolved name was not trusted"
    assert not shown(seal(lua, 2)), "an unresolved name showed"


def check_secret_throwing_and_unreadable_answers_hide_and_never_throw():
    seals = expected_seals()
    for key, mode in (("__infoMode", "secret"), ("__infoMode", "throw"),
                      ("__knownMode", "secret"), ("__knownMode", "throw")):
        lua = boot(known=[seals[0]])
        assert shown(seal(lua, 1)), "setup: the known seal should show"
        g(lua)[key] = mode
        fire(lua, "SPELLS_CHANGED")      # must not throw out of the handler
        assert not shown(seal(lua, 1)) and spell_of(seal(lua, 1)) is None, f"{key}={mode} kept a button"
        g(lua)[key] = None
        fire(lua, "SPELLS_CHANGED")
        assert shown(seal(lua, 1)), f"{key}={mode} never recovered"


def check_every_spellbook_event_reevaluates():
    seals = expected_seals()
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
        lua = boot(known=[seals[0]])
        assert not shown(seal(lua, 2))
        g(lua).__learn(seals[1])
        fire(lua, event)
        assert shown(seal(lua, 2)) and spell_of(seal(lua, 2)) == seals[1], f"{event} did not re-evaluate"
        g(lua).__forget(seals[1])
        fire(lua, event)
        assert not shown(seal(lua, 2)) and spell_of(seal(lua, 2)) is None, f"{event} kept a forgotten spell"


def slot_x(slot, scale=1.0):
    """BOTTOMLEFT x of a button in packed slot `slot` (1 based)."""
    return (MU["PAD"] + (slot - 1) * (MU["BTN"] + MU["BG"])) * scale


def check_a_binding_stays_on_its_seal_when_an_earlier_seal_is_learned():
    seals = expected_seals()
    lua = boot(known=[seals[1]])
    btn = seal(lua, 2)
    assert spell_of(btn) == seals[1] and shown(btn) and not shown(seal(lua, 1))
    approx(btn._points[1].x, slot_x(1), "sotc seat before", 0.01)
    assert btn.commandName == "CLICK FSSealButton2:LeftButton"
    g(lua).__learn(seals[0])
    fire(lua, "SPELLS_CHANGED")
    assert spell_of(btn) == seals[1] and btn.commandName == "CLICK FSSealButton2:LeftButton", (
        "button 2 no longer casts the Crusader: its key would follow the slot")
    assert spell_of(seal(lua, 1)) == seals[0] and shown(seal(lua, 1))
    approx(seal(lua, 1)._points[1].x, slot_x(1), "sor seat", 0.01)
    approx(btn._points[1].x, slot_x(2), "sotc seat after", 0.01)


def check_learned_seals_pack_left_by_moving_their_own_named_frames():
    seals = expected_seals()
    lua = boot(known=[seals[1], seals[5]])
    a, b = seal(lua, 2), seal(lua, 6)
    assert a._name == "FSSealButton2" and b._name == "FSSealButton6"
    assert spell_of(a) == seals[1] and spell_of(b) == seals[5]
    approx(a._points[1].x, slot_x(1), "first learned seal", 0.01)
    approx(b._points[1].x, slot_x(2), "second learned seal", 0.01)
    for i in (1, 3, 4, 5, 7):
        assert not shown(seal(lua, i)) and spell_of(seal(lua, i)) is None, f"unlearned FSSealButton{i} is not inert"


def check_seal_seats_and_attributes_wait_for_regen():
    seals = expected_seals()
    lua = boot(known=[seals[1]])
    set_combat(lua, True)
    g(lua).__learn(seals[0])
    fire(lua, "SPELLS_CHANGED")
    assert blocked(lua) == 0 and not shown(seal(lua, 1)), "a seal appeared in combat"
    approx(seal(lua, 2)._points[1].x, slot_x(1), "sotc seat in combat", 0.01)
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert shown(seal(lua, 1)) and spell_of(seal(lua, 1)) == seals[0]
    approx(seal(lua, 2)._points[1].x, slot_x(2), "sotc seat after regen", 0.01)


def check_learning_an_earlier_seal_moves_the_later_frames_not_their_names():
    seals = expected_seals()
    lua = boot(known=[seals[1]])
    g(lua).__bindings["CLICK FSSealButton2:LeftButton"] = "SHIFT-F"
    fire(lua, "UPDATE_BINDINGS")
    assert seal(lua, 2).HotKey._text == "SHIFT-F"
    g(lua).__learn(seals[0])
    fire(lua, "SPELLS_CHANGED")
    assert seal(lua, 2).HotKey._text == "SHIFT-F" and seal(lua, 1).HotKey._text in (None, ""), (
        "the key text did not stay with its seal")
    assert [seal(lua, i)._name for i in (1, 2)] == ["FSSealButton1", "FSSealButton2"]


def check_the_icon_follows_the_spell():
    seals = expected_seals()
    lua = boot(known=[seals[2]])
    sid = g(lua).__spells[seals[2]]
    assert seal(lua, 3).icon._texture == 9000 + sid, f"icon {seal(lua, 3).icon._texture!r}"
    # an aura wears its form's own icon
    auras = expected_auras()
    lua = boot(forms=[auras[1]])
    fid = form_id(lua, auras[1])
    assert aura(lua, 1).icon._texture == 8000 + fid, f"aura icon {aura(lua, 1).icon._texture!r}"


def check_a_non_paladin_gets_nothing_and_keeps_its_stance_bar():
    for klass in ("WARRIOR", "SECRET", "THROW"):
        lua = boot(klass=klass)
        assert g(lua).FSSealBar is None and g(lua).FSSealButton1 is None, f"{klass} got seal buttons"
        assert g(lua).FSStanceBar._shown, f"{klass}: the stance bar was taken away"
        assert not g(lua).FS.SealBar or not g(lua).FS.SealBar.OwnsForms(), f"{klass}: OwnsForms is true"


def check_a_paladin_stance_bar_hands_its_forms_over():
    lua = boot()
    assert g(lua).FS.SealBar.OwnsForms(), "SealBar should own the forms for a Paladin"
    assert callable(g(lua).FS.StanceBar.Rebuild), "StanceBar.Rebuild is not exported"
    assert not g(lua).FSStanceBar._shown, "the stance container is still shown for a Paladin"
    assert not g(lua).FSStanceButton1._shown, "a stance button is still shown for a Paladin"
    # the same stance bar for a Warrior shows its two forms (class agnostic gate)
    lua = boot(klass="WARRIOR")
    assert g(lua).FSStanceBar._shown and g(lua).FSStanceButton1._shown


def check_stance_events_keep_the_gate():
    lua = boot()
    for event in ("UPDATE_SHAPESHIFT_FORMS", "PLAYER_ENTERING_WORLD"):
        fire(lua, event)
        assert not g(lua).FSStanceBar._shown, f"{event} brought the stance bar back for a Paladin"


def check_the_stance_suppression_holds_across_every_rebuild():
    """StanceBar.Build shows its container on every rebuild; a one-time hide would come back."""
    lua = boot()
    stock, button = g(lua).StanceBar, g(lua).StanceButton1
    assert stock._alpha == 0 and button._mouse is False, "the stock stance bar is not dimmed at login"
    for event in ("UPDATE_SHAPESHIFT_FORMS", "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORMS"):
        stock._alpha, button._mouse = 1, True          # Blizzard brings its bar back
        fire(lua, event)
        assert not g(lua).FSStanceBar._shown, f"{event} showed the stance container again"
        assert not g(lua).FSStanceButton1._shown, f"{event} showed a stance button again"
        assert stock._alpha == 0 and button._mouse is False, f"{event} left the stock stance bar up"
    # a form count change still rebuilds nothing visible
    set_forms(lua, [(expected_auras()[0], True)])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not g(lua).FSStanceBar._shown, "a form change brought the stance container back"


def check_the_stance_suppression_waits_out_combat():
    lua = boot()
    stock, button = g(lua).StanceBar, g(lua).StanceButton1
    stock._alpha, button._mouse = 1, True
    set_combat(lua, True)
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert blocked(lua) == 0, "a protected operation ran in combat"
    assert not g(lua).FSStanceBar._shown, "the stance container showed in combat"
    assert stock._alpha == 1, "the stock bar was touched in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not g(lua).FSStanceBar._shown and not g(lua).FSStanceButton1._shown, "the rebuild after combat showed the bar"
    assert stock._alpha == 0 and button._mouse is False, "the stock bar was not dimmed after combat"
    assert blocked(lua) == 0


def check_the_stance_bar_keeps_other_classes_and_a_failed_sealbar():
    lua = boot(klass="WARRIOR")
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert g(lua).FSStanceBar._shown and g(lua).FSStanceButton1._shown, "a Warrior lost its stance bar"
    lua = boot(sealbar=False)       # SealBar never loaded: the stance bar keeps the forms
    assert g(lua).FSStanceBar._shown, "the stance bar vanished with no SealBar"


def check_the_aura_row_is_the_shapeshift_forms_in_mockup_order():
    auras = expected_auras()
    # forms in a different index order than the mockup: Retribution is form 1, Devotion form 2
    lua = boot(forms=[auras[1], auras[0], auras[2]])
    want = [(auras[0], 2), (auras[1], 1), (auras[2], 3)]
    for slot, (name, index) in enumerate(want, 1):
        btn = aura(lua, slot)
        assert shown(btn) and spell_of(btn) == form_id(lua, name), f"slot {slot} holds {spell_of(btn)!r}, not {name}"
        assert btn.fsFormIndex == index, f"slot {slot} ({name}) form index {btn.fsFormIndex!r}, expected {index}"
        assert btn.commandName == f"SHAPESHIFTBUTTON{index}", f"slot {slot} command {btn.commandName!r}"
    assert not shown(aura(lua, 4)) and spell_of(aura(lua, 4)) is None and aura(lua, 4).fsFormIndex is None
    # a form the mockup does not know sorts after the known ones, in form order
    lua = boot(forms=["Crusader Aura", auras[3], "Zeal Aura", auras[0]])
    got = [(spell_of(aura(lua, i)), aura(lua, i).fsFormIndex) for i in range(1, 5)]
    want = [(form_id(lua, n), idx) for n, idx in ((auras[0], 4), (auras[3], 2), ("Crusader Aura", 1), ("Zeal Aura", 3))]
    assert got == want, f"{got} != {want}"
    # the row holds seven at most
    lua = boot(forms=[f"Extra Aura {i}" for i in range(1, 10)])
    assert all(shown(aura(lua, i)) for i in range(1, 8)), "seven forms should fill the row"
    assert aura(lua, 7).fsFormIndex == 7, "the row is not capped at seven in form order"


def check_a_form_change_rewrites_the_aura_row():
    auras = expected_auras()
    lua = boot(forms=[auras[0]])
    assert not shown(aura(lua, 2))
    set_forms(lua, [auras[0], auras[2]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert shown(aura(lua, 2)) and spell_of(aura(lua, 2)) == form_id(lua, auras[2]), "UPDATE_SHAPESHIFT_FORMS did not re-read"
    assert aura(lua, 2).commandName == "SHAPESHIFTBUTTON2"
    set_forms(lua, [auras[2], auras[0]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert spell_of(aura(lua, 1)) == form_id(lua, auras[0]) and aura(lua, 1).commandName == "SHAPESHIFTBUTTON2", (
        "the button did not follow its spell to the new form index")
    set_forms(lua, [])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not shown(aura(lua, 1)) and spell_of(aura(lua, 1)) is None and aura(lua, 1).fsFormIndex is None


def check_form_changes_in_combat_wait_for_regen():
    auras = expected_auras()
    lua = boot(forms=[auras[0]])
    set_combat(lua, True)
    set_forms(lua, [auras[1], auras[0]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert blocked(lua) == 0, "SetAttribute, Show or Hide ran against a protected button in combat"
    assert spell_of(aura(lua, 1)) == form_id(lua, auras[0]) and not shown(aura(lua, 2)), "an aura button changed in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert spell_of(aura(lua, 1)) == form_id(lua, auras[0]) and spell_of(aura(lua, 2)) == form_id(lua, auras[1]), (
        "the pending form change was not replayed")
    assert blocked(lua) == 0


def check_every_button_has_a_black_edgeless_swipe_on_its_icon():
    lua = boot()
    for btn in all_buttons(lua):
        cd = btn.cooldown
        assert cd is not None and cd._kind == "Cooldown", f"{btn._name} has no cooldown frame"
        assert cd._drawEdge is False and cd._drawBling is False, f"{btn._name}: edge or bling on"
        c = cd._swipeColor
        assert (c[1], c[2], c[3]) == (0, 0, 0) and abs(c[4] - 0.64) < 1e-6, f"{btn._name} swipe {c}"
        assert cd._points[1] is not None and same(lua, cd._points[1].rel, btn.icon), f"{btn._name} swipe is not on the icon"


def check_the_swipe_follows_the_spell_cooldown_by_duration_object():
    seals, auras = expected_seals(), expected_auras()
    lua = boot(forms=[auras[1], auras[0]])
    sid, fid = seal_id(lua, seals[1]), form_id(lua, auras[0])
    assert cd_of(seal(lua, 2)) is None
    set_cd(lua, sid, 100, 8)
    set_cd(lua, fid, 200, 3)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 2)) == ("obj", sid), f"seal swipe {cd_of(seal(lua, 2))}"
    assert cd_of(aura(lua, 1)) == ("obj", fid), f"aura swipe {cd_of(aura(lua, 1))} (Devotion is slot 1)"
    assert cd_of(seal(lua, 1)) is None and cd_of(aura(lua, 2)) is None, "an unrelated swipe lit"
    # the cooldown ends
    set_cd(lua, sid)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 2)) is None, "an ended cooldown kept its swipe"
    # the swipe moves with the spell when the slots shift, and a cleared slot loses it
    set_cd(lua, sid, 100, 8)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    lua2 = boot(known=[seals[1]])
    sid2 = seal_id(lua2, seals[1])
    set_cd(lua2, sid2, 100, 8)
    fire(lua2, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua2, 2)) == ("obj", sid2)
    g(lua2).__learn(seals[0])
    fire(lua2, "SPELLS_CHANGED")
    assert cd_of(seal(lua2, 1)) is None and cd_of(seal(lua2, 2)) == ("obj", sid2), "the swipe left its seal"
    # a seal learned while its cooldown runs shows the swipe at the sync, with no cooldown event
    lua2b = boot(known=[seals[1]])
    g(lua2b).__learn(seals[0])
    set_cd(lua2b, seal_id(lua2b, seals[0]), 100, 8)
    fire(lua2b, "SPELLS_CHANGED")
    assert cd_of(seal(lua2b, 1)) == ("obj", seal_id(lua2b, seals[0])), "a newly shown seal missed its running cooldown"
    g(lua2).__forget(seals[1])
    fire(lua2, "SPELLS_CHANGED")
    assert cd_of(seal(lua2, 2)) is None, "an emptied slot kept a swipe"
    # a secret or throwing duration answer never reaches the swipe and never throws
    for mode in ("secretobj", "throw"):
        lua3 = boot(known=[seals[0]])
        sid3 = seal_id(lua3, seals[0])
        set_cd(lua3, sid3, 100, 8)
        fire(lua3, "SPELL_UPDATE_COOLDOWN")
        assert cd_of(seal(lua3, 1)) == ("obj", sid3)
        lua3.execute(f'__cdMode = "{mode}"')
        fire(lua3, "SPELL_UPDATE_COOLDOWN")
        assert cd_of(seal(lua3, 1)) is None, f"{mode}: the swipe kept an unreadable answer"


def check_the_swipe_falls_back_to_the_legacy_cooldown_and_guards_secrets():
    seals = expected_seals()
    lua = boot(known=[seals[0]])
    sid = seal_id(lua, seals[0])
    lua.execute("C_Spell.GetSpellCooldownDuration = nil")
    set_cd(lua, sid, 100, 8)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 1)) == ("time", 100, 8), f"legacy swipe {cd_of(seal(lua, 1))}"
    g(lua).__cdMode = "secret"
    set_cd(lua, sid, 300, 9)
    fire(lua, "SPELL_UPDATE_COOLDOWN")        # a secret start and duration are never handed over
    assert cd_of(seal(lua, 1)) == ("time", 100, 8), "a secret cooldown reached SetCooldown"
    assert not shown(seal(lua, 1).cooldown), "a secret cooldown left the swipe up"
    # a finished cooldown (zero duration) and a disabled one light nothing
    lua.execute("__cdMode = nil")
    set_cd(lua, sid, 0, 0)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 1)) is None and not shown(seal(lua, 1).cooldown), "a zero duration lit the swipe"
    lua.execute('__cdMode = "disabled"')
    set_cd(lua, sid, 100, 8)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 1)) is None and not shown(seal(lua, 1).cooldown), "a disabled cooldown lit the swipe"
    # the old global API, when C_Spell has none
    lua = boot(known=[seals[0]])
    lua.execute("""
        C_Spell.GetSpellCooldownDuration = nil
        C_Spell.GetSpellCooldown = nil
        function GetSpellCooldown(id) return 50, 6, 1 end
    """)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert cd_of(seal(lua, 1)) == ("time", 50, 6), f"global API swipe {cd_of(seal(lua, 1))}"


def check_the_swipe_refreshes_in_combat_without_a_protected_call():
    seals = expected_seals()
    lua = boot(known=[seals[0]])
    sid = seal_id(lua, seals[0])
    set_combat(lua, True)
    set_cd(lua, sid, 100, 8)
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert blocked(lua) == 0, "the cooldown refresh touched a protected frame in combat"
    assert cd_of(seal(lua, 1)) == ("obj", sid), "the swipe did not update in combat"


def check_unreadable_form_answers_hide_the_aura_and_never_throw():
    auras = expected_auras()
    for mode in ("num_throw", "num_secret", "info_throw", "id_secret"):
        lua = boot(forms=[auras[0]])
        assert shown(aura(lua, 1)), "setup: the aura should show"
        form_mode(lua, mode)
        fire(lua, "SPELLS_CHANGED")        # must not throw out of the handler
        assert not shown(aura(lua, 1)) and spell_of(aura(lua, 1)) is None, f"{mode} kept an aura button"
        assert shown(seal(lua, 1)), f"{mode} took the seals down too"
        form_mode(lua, None)
        fire(lua, "SPELLS_CHANGED")
        assert shown(aura(lua, 1)), f"{mode} never recovered"
        assert g(lua).__degraded["sealbar_sync"] is None, f"{mode}: a form read escaped into the sync guard"
    # a secret icon is never handed to the texture
    lua = boot(forms=[auras[0]])
    form_mode(lua, "icon_secret")
    fire(lua, "SPELLS_CHANGED")
    assert shown(aura(lua, 1)) and aura(lua, 1).icon._texture != 424242, "a secret icon reached SetTexture"
    # an absurd form count is bounded, not walked
    lua = boot(forms=[auras[0]])
    lua.execute("""
        __infoCalls = 0
        GetNumShapeshiftForms = function() return 1e9 end
        local real = GetShapeshiftFormInfo
        GetShapeshiftFormInfo = function(i) __infoCalls = __infoCalls + 1; return real(i) end
    """)
    fire(lua, "SPELLS_CHANGED")
    assert g(lua).__infoCalls <= 64, f"{g(lua).__infoCalls} form reads for an absurd count"
    # no form API at all: hidden, logged once
    lua = boot(forms=[auras[0]])
    lua.execute("GetNumShapeshiftForms = nil")
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not shown(aura(lua, 1)), "an aura shows with no form API"
    assert g(lua).__degraded["sealbar_noforms"], "the missing form API was not logged"
    n = g(lua).__degradeCount
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    fire(lua, "SPELLS_CHANGED")
    assert g(lua).__degradeCount == n, "the missing form API log repeated"


def check_unreadable_spell_names_keep_the_aura_row_in_form_order():
    auras = expected_auras()
    for mode in ("secret", "throw"):
        lua = boot(forms=[auras[1], auras[0]])
        assert spell_of(aura(lua, 1)) == form_id(lua, auras[0]), "setup: Devotion should sort first"
        g(lua).__infoMode = mode
        fire(lua, "SPELLS_CHANGED")
        assert g(lua).__degraded["sealbar_sync"] is None, f"{mode} names escaped into the sync guard"
        assert spell_of(aura(lua, 1)) == form_id(lua, auras[1]) and aura(lua, 1).fsFormIndex == 1, (
            f"{mode} names: the row should fall back to form order")
        assert spell_of(aura(lua, 2)) == form_id(lua, auras[0]) and shown(aura(lua, 2))


def check_hidden_slots_make_no_cooldown_read():
    seals, auras = expected_seals(), expected_auras()
    lua = boot(known=[seals[0], seals[1]], forms=[auras[0]])
    lua.execute("__cdReads = 0")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    reads = int(g(lua).__cdReads)
    assert reads == 3, f"{reads} cooldown reads for 2 seals and 1 form (hidden slots must make none)"


def check_a_sync_pending_in_combat_is_replayed_at_regen():
    seals = expected_seals()
    lua = boot(known=[seals[1]])
    set_combat(lua, True)
    g(lua).__learn(seals[0])
    fire(lua, "SPELLS_CHANGED")
    assert not shown(seal(lua, 1)) and blocked(lua) == 0, "the slots moved in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert spell_of(seal(lua, 1)) == seals[0] and spell_of(seal(lua, 2)) == seals[1], "regen did not re-attribute"
    approx(seal(lua, 2)._points[1].x, slot_x(2), "regen did not re-seat", 0.01)


def check_no_value_is_compared_to_nil_before_its_secret_guard():
    """The mock cannot trap `== nil` on a secret (Lua 5.1 `__eq` never fires against nil), so read the
    source: EVERY identifier compared to nil in SealBar.lua, on either side of the operator, must
    have `IsSecret(X)` earlier on the same line, unless it is allowlisted here with the reason it can
    never hold a secret."""
    own_state = {
        "current": "a local cache of this file: nil, false or a number we computed",
        "button.fsSpellKey": "a field of this file, only ever a spell name or id we stored",
    }
    ident = r"([A-Za-z_][\w.]*)"
    seen, used = 0, set()
    for n, line in enumerate(SEALBAR.read_text().splitlines(), 1):
        code = line.split("--")[0]
        hits = [(m.start(), m.group(1), m.group(0)) for m in re.finditer(ident + r"\s*(?:==|~=)\s*nil\b", code)]
        hits += [(m.start(), m.group(1), m.group(0)) for m in re.finditer(r"\bnil\s*(?:==|~=)\s*" + ident, code)]
        for start, name, text in hits:
            seen += 1
            if name in own_state:
                used.add(name)
                continue
            assert f"IsSecret({name})" in code[:start], (
                f"SealBar.lua:{n}: `{text}` before IsSecret({name}): {line.strip()}")
    assert seen >= 7, f"only {seen} nil comparisons matched; the scan is broken"
    assert used == set(own_state), f"stale allowlist entries: {sorted(set(own_state) - used)}"


def check_a_button_with_no_spell_gets_no_cooldown_write():
    seals = expected_seals()
    lua = boot(known=[seals[0]])
    empty = [b for b in all_buttons(lua) if not b.fsSpellID]
    assert empty, "the fixture has no spell-less button"
    for b in all_buttons(lua):
        b.cooldown._clears = 0
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    touched = [b._name for b in empty if (b.cooldown._clears or 0) > 0]
    assert not touched, f"spell-less buttons had their cooldown written: {touched}"


def check_the_swipe_also_follows_the_shapeshift_cooldown_event():
    seals = expected_seals()
    lua = boot(known=[seals[0]])
    sid = seal_id(lua, seals[0])
    set_cd(lua, sid, 100, 8)
    fire(lua, "UPDATE_SHAPESHIFT_COOLDOWN")
    assert cd_of(seal(lua, 1)) == ("obj", sid), "UPDATE_SHAPESHIFT_COOLDOWN did not refresh the swipe"
    # in combat only the state route can refresh it (Sync waits), with no protected call
    set_combat(lua, True)
    set_cd(lua, sid)
    fire(lua, "UPDATE_SHAPESHIFT_COOLDOWN")
    assert cd_of(seal(lua, 1)) is None and blocked(lua) == 0, "UPDATE_SHAPESHIFT_COOLDOWN did not refresh in combat"


def check_a_form_uses_its_own_form_cooldown_on_the_legacy_path():
    auras = expected_auras()
    lua = boot(forms=[auras[1], auras[0]])        # Devotion is form 2, slot 1
    lua.execute("C_Spell.GetSpellCooldownDuration = nil")
    lua.execute("__fcd[2] = { 50, 6 }")
    fire(lua, "UPDATE_SHAPESHIFT_COOLDOWN")
    assert cd_of(aura(lua, 1)) == ("time", 50, 6), f"form cooldown swipe {cd_of(aura(lua, 1))}"
    assert cd_of(aura(lua, 2)) is None, "the other form lit"
    lua.execute('__cdMode = "secret"')
    lua.execute("__fcd[2] = { 90, 9 }")
    fire(lua, "UPDATE_SHAPESHIFT_COOLDOWN")
    assert cd_of(aura(lua, 1)) == ("time", 50, 6) and not shown(aura(lua, 1).cooldown), "a secret form cooldown was used"


def check_the_active_flag_falls_back_to_the_current_form():
    auras = expected_auras()
    lua = boot(forms=[auras[1], (auras[0], True), auras[2]])
    wash = lambda slot: aura(lua, slot).fsActiveWash
    assert shown(wash(1)) and not shown(wash(2))
    # the flag is nil: GetShapeshiftForm says form 3 is current
    set_forms(lua, [auras[1], auras[0], (auras[2], True)])
    form_mode(lua, "active_nil")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not shown(wash(1)) and not shown(wash(2)) and shown(wash(3)), "nil flag: the cross-check did not light form 3"
    # a secret flag takes the same fallback
    set_forms(lua, [auras[1], (auras[0], True), auras[2]])
    form_mode(lua, "active_secret")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert shown(wash(1)) and not shown(wash(2)) and not shown(wash(3)), "secret flag: the cross-check did not light form 1"
    # the cross-check itself unreadable (secret or throwing): the look stays as it was
    for cur in ("secret", "throw"):
        lua.execute(f'__curMode = "{cur}"')
        set_forms(lua, [auras[1], auras[0], (auras[2], True)])
        fire(lua, "UPDATE_SHAPESHIFT_FORM")
        assert shown(wash(1)) and not shown(wash(3)), f"GetShapeshiftForm {cur}: the look changed"
    # a plain flag is never second guessed by the cross-check
    lua.execute('__curMode = nil')
    form_mode(lua, None)
    set_forms(lua, [auras[1], (auras[0], True), auras[2]])
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert shown(wash(1))
    lua.execute("GetShapeshiftForm = function() return 3 end")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert shown(wash(1)) and not shown(wash(3)), "a plain flag was overridden by the cross-check"


def check_the_active_form_lights_its_wash():
    auras = expected_auras()
    lua = boot(forms=[auras[1], (auras[0], True), auras[2]])    # Devotion (form 2) is active
    wash = lambda slot: aura(lua, slot).fsActiveWash
    assert shown(wash(1)) and not shown(wash(2)) and not shown(wash(3)), "only the active form's wash should show"
    cyan = g(lua).FS.Theme.COLOR_POWER
    v = wash(1)._vertex
    assert abs(v[4] - 0.4) < 1e-6 and max(abs(v[1] - cyan[1]), abs(v[2] - cyan[2]), abs(v[3] - cyan[3])) < 0.01, (
        f"the wash is {tuple(v[i] for i in (1, 2, 3, 4))}: alpha .4 in the border colour")
    # the active ring is brighter than the others, and the glow stronger
    ring = lambda slot: aura(lua, slot).fsSkin.border.ring._vertex
    glow = lambda slot: aura(lua, slot).fsSkin.glow._vertex
    lum = lambda c: c[1] + c[2] + c[3]
    assert lum(ring(1)) > lum(ring(2)) + 0.2, "the active ring is not brighter"
    assert abs(lum(ring(2)) - lum(cyan)) < 0.01 and abs(lum(ring(3)) - lum(ring(2))) < 1e-6
    assert glow(1)[4] > glow(2)[4] + 0.2, "the active glow is not stronger"
    assert seal(lua, 1).fsActiveWash is None, "a seal button got an aura wash"
    # the active form changes: UPDATE_SHAPESHIFT_FORM refreshes it, in combat too
    set_forms(lua, [auras[1], auras[0], (auras[2], True)])
    set_combat(lua, True)
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert blocked(lua) == 0, "the active refresh touched a protected frame in combat"
    assert not shown(wash(1)) and not shown(wash(2)) and shown(wash(3)), "the wash did not follow the active form"
    ring = lambda slot: aura(lua, slot).fsSkin.border.ring._vertex
    assert ring(3)[1] + ring(3)[2] + ring(3)[3] > ring(1)[1] + ring(1)[2] + ring(1)[3] + 0.2, "the ring did not follow"
    # UPDATE_SHAPESHIFT_FORMS in combat refreshes the look too (Sync waits, the textures do not)
    set_forms(lua, [auras[1], (auras[0], True), auras[2]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert blocked(lua) == 0 and shown(wash(1)) and not shown(wash(3)), "UPDATE_SHAPESHIFT_FORMS did not refresh the look"
    # no form active: all dark
    set_forms(lua, [auras[1], auras[0], auras[2]])
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert not any(shown(wash(i)) for i in (1, 2, 3)), "a wash stayed lit with no active form"
    # a secret flag keeps the last plain look and never throws
    set_forms(lua, [auras[1], (auras[0], True), auras[2]])
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    form_mode(lua, "active_secret")
    fire(lua, "UPDATE_SHAPESHIFT_FORM")
    assert shown(wash(1)) and not shown(wash(2)) and not shown(wash(3)), "a secret active flag changed the wash"
    ring_sum = lambda slot: sum(aura(lua, slot).fsSkin.border.ring._vertex[i] for i in (1, 2, 3))
    assert ring_sum(1) > ring_sum(2) + 0.2 and abs(ring_sum(2) - ring_sum(3)) < 1e-6, "a secret flag changed the ring"
    # a slot that empties and fills again under a secret flag does not keep a stale wash
    form_mode(lua, None)
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    set_forms(lua, [])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    form_mode(lua, "active_secret")
    set_forms(lua, [auras[0]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert shown(aura(lua, 1)) and not shown(wash(1)), "a refilled slot kept the old wash"
    assert abs(ring_sum(1) - sum(g(lua).FS.Theme.COLOR_POWER[i] for i in (1, 2, 3))) < 0.01, "a refilled slot kept the old ring"


def check_the_wash_follows_the_spell_when_the_rows_shift():
    auras = expected_auras()
    lua = boot(forms=[(auras[1], True)])
    assert shown(aura(lua, 1).fsActiveWash)
    set_forms(lua, [(auras[1], True), auras[0]])         # Devotion joins and sorts first
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not shown(aura(lua, 1).fsActiveWash) and shown(aura(lua, 2).fsActiveWash), "the wash stayed on the slot"



def check_geometry_is_the_mockups(scale):
    lua = boot(scale)
    s = scale
    host = g(lua).FSSealBar
    w = (2 * MU["PAD"] + 7 * MU["BTN"] + 6 * MU["BG"]) * s
    h = (MU["PT"] + 2 * MU["BTN"] + MU["BG"] + MU["PB"]) * s
    approx(host._w, w, "host width", 0.01)
    approx(host._h, h, "host height", 0.01)
    pitch = MU["BTN"] + MU["BG"]
    for col in range(7):
        for row, btn in ((0, seal(lua, col + 1)), (1, aura(lua, col + 1))):
            approx(btn._w, MU["BTN"] * s, f"row {row} col {col} width", 0.01)
            approx(btn._h, MU["BTN"] * s, f"row {row} col {col} height", 0.01)
            p = btn._points[1]
            assert p.point == "BOTTOMLEFT" and p.rel._name == "FSSealBar" and p.relPoint == "BOTTOMLEFT", (
                f"row {row} col {col} anchor {p.point}/{p.relPoint}")
            approx(p.x, (MU["PAD"] + col * pitch) * s, f"row {row} col {col} x", 0.01)
            approx(p.y, (MU["PB"] + (1 - row) * pitch) * s, f"row {row} col {col} y", 0.01)


def check_the_shoulder_stands_on_the_console_top_edge(scale):
    lua = boot(scale)
    assert g(lua).FS.Console.IsDrawn(), "setup: the Console should be drawn"
    host = g(lua).FSSealBar
    assert len(host._points) == 1, f"host has {len(host._points)} points"
    p = host._points[1]
    assert p.point == "BOTTOMLEFT" and p.rel._name == "FSConsole" and p.relPoint == "TOPLEFT", (
        f"host anchor {p.point} to {p.relPoint} of {p.rel and p.rel._name}")
    approx(p.x, MU["DX"] * scale, "host dx", 0.5 * scale)
    approx(p.y, 0, "host dy")
    assert host._shown, "host should be shown with the Console drawn"
    assert host._level > top_level(g(lua).FSConsole), "the buttons must draw above everything on the chassis"


def check_the_shoulder_follows_the_console_on_and_off():
    lua = boot()
    host = g(lua).FSSealBar
    g(lua).FS.Console.SetActive(False)
    assert not g(lua).FS.Console.IsDrawn()
    assert host._shown, "the shoulder hid with the Console off"
    p = host._points[1]
    assert p.rel._name == "FSStanceBar" and p.point == "BOTTOMLEFT" and p.relPoint == "TOPLEFT", (
        f"Console off: anchor {p.rel and p.rel._name}")
    assert p.x == 0 and abs(p.y - 4) < 1e-6, f"Console off: offset ({p.x}, {p.y})"
    assert g(lua).__degraded["sealbar_noconsole"] is None, "Console off is a normal case, not a degrade"
    assert all(shown(b) for b in all_buttons(lua)), "a button went missing with the Console off"
    g(lua).FS.Console.SetActive(True)
    p = host._points[1]
    assert g(lua).FS.Console.IsDrawn() and host._shown and p.rel._name == "FSConsole", (
        "the shoulder did not come back to the Console")


def check_without_a_console_the_shoulder_sits_above_the_stance_seat_and_logs_once():
    lua = boot(console=False)
    host = g(lua).FSSealBar
    p = host._points[1]
    assert p.rel._name == "FSStanceBar" and p.relPoint == "TOPLEFT", f"fallback anchor {p.rel and p.rel._name}"
    assert p.point == "BOTTOMLEFT" and p.x == 0 and abs(p.y - 4) < 1e-6, (
        f"the fallback sits at ({p.x}, {p.y}), not 4 design px above the stance seat")
    assert host._shown, "the fallback shoulder is hidden"
    assert g(lua).__degraded["sealbar_noconsole"], "the fallback was not logged"
    n = g(lua).__degradeCount
    fire(lua, "SPELLS_CHANGED")
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert g(lua).__degradeCount == n, "the fallback log repeated"


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = boot(1.0)
    lua.eval("__rescale")(0.64)
    s = 0.64
    approx(seal(lua, 3)._w, MU["BTN"] * s, "button width after rescale", 0.01)
    approx(seal(lua, 3)._points[1].x, (MU["PAD"] + 2 * (MU["BTN"] + MU["BG"])) * s, "button x after rescale", 0.01)
    p = g(lua).FSSealBar._points[1]
    approx(p.x, MU["DX"] * s, "host dx after rescale", 0.5 * s)


def check_a_rescale_reaches_the_bar_without_a_geometry_notice():
    lua = boot(1.0, geometry=False)
    lua.eval("__rescale")(0.64)
    approx(seal(lua, 3)._w, MU["BTN"] * 0.64, "button width after a rescale with no geometry notice", 0.01)


def check_a_rescale_in_combat_waits_for_regen():
    lua = boot(1.0)
    set_combat(lua, True)
    lua.eval("__rescale")(0.64)
    assert blocked(lua) == 0, "a protected operation ran in combat"
    approx(seal(lua, 3)._w, MU["BTN"], "button width in combat", 0.01)
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    approx(seal(lua, 3)._w, MU["BTN"] * 0.64, "button width after regen", 0.01)


def check_spellbook_changes_in_combat_wait_for_regen():
    seals = expected_seals()
    lua = boot(known=[seals[0]])
    set_combat(lua, True)
    g(lua).__learn(seals[1])
    g(lua).__forget(seals[0])
    for event in ("SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD"):
        fire(lua, event)
    assert blocked(lua) == 0, "SetAttribute, Show or Hide ran against a protected button in combat"
    assert spell_of(seal(lua, 1)) == seals[0] and shown(seal(lua, 1)), "a button changed in combat"
    assert not shown(seal(lua, 2)), "a button showed in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert spell_of(seal(lua, 2)) == seals[1] and shown(seal(lua, 2)) and not shown(seal(lua, 1)), (
        "the pending change was not replayed")
    assert spell_of(seal(lua, 1)) is None
    approx(seal(lua, 2)._points[1].x, slot_x(1), "the learned seal did not pack to slot 1", 0.01)
    assert blocked(lua) == 0


def check_the_console_toggle_in_combat_never_touches_the_host():
    lua = boot()
    host = g(lua).FSSealBar
    set_combat(lua, True)
    g(lua).FS.Console.SetActive(False)       # ActionBars defers the real switch to regen
    assert blocked(lua) == 0 and host._shown and host._points[1].rel._name == "FSConsole"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert host._shown and host._points[1].rel._name == "FSStanceBar" and blocked(lua) == 0, (
        "the host did not move to the stance seat after combat")


def check_a_login_in_combat_builds_at_regen():
    lua = boot(combat=True)
    assert g(lua).FSSealButton1 is None, "buttons were built in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert g(lua).FSSealButton1 is not None and g(lua).FSAuraButton7 is not None, "buttons not built at regen"
    assert shown(seal(lua, 1)), "the first seal is not shown after the late build"


def check_quick_keybind_commands_and_one_hook_set():
    lua = boot()
    for i in range(1, 8):
        for prefix, getter, command in (
                ("FSSealButton", seal, f"CLICK FSSealButton{i}:LeftButton"),
                ("FSAuraButton", aura, f"SHAPESHIFTBUTTON{i}")):
            btn = getter(lua, i)
            assert btn.commandName == command, f"{prefix}{i}: {btn.commandName!r} != {command!r}"
            assert btn.fsQuickKeybindOverlay is not None, f"{prefix}{i} has no click-eating overlay"
            assert btn.QuickKeybindHighlightTexture is not None
            for script in ("OnClick", "OnShow", "OnHide"):
                assert len(btn._hooks[script]) == 1, f"{prefix}{i}: {len(btn._hooks[script])} {script} hooks"
    # a slot with no form keeps the aura command too, never a CLICK one
    lua = boot(forms=[])
    for i in range(1, 8):
        assert aura(lua, i).commandName == f"SHAPESHIFTBUTTON{i}", f"empty aura slot {i}: {aura(lua, i).commandName!r}"
    # the command follows the form, and a re-sync adds no second hook set
    auras = expected_auras()
    lua = boot(forms=[auras[1], auras[0]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert aura(lua, 1).commandName == "SHAPESHIFTBUTTON2", "Devotion is form 2 and sorts first"
    for script in ("OnClick", "OnShow", "OnHide"):
        assert len(aura(lua, 1)._hooks[script]) == 1, f"a re-sync added a {script} hook"


def check_bindings_xml_declares_the_seven_seal_commands_only():
    assert BINDINGS.exists(), "Bindings.xml is missing"
    root = ET.parse(BINDINGS).getroot()
    items = root.findall("Binding")
    names = [b.get("name") for b in items]
    want = [f"CLICK FSSealButton{i}:LeftButton" for i in range(1, 8)]
    assert names == want, f"binding names {names} (seals only: an aura key is Blizzard's SHAPESHIFTBUTTONi)"
    headers = [b.get("header") for b in items]
    assert headers[0] == "FOREVERSYNTHWAVE" and all(h is None for h in headers[1:]), f"headers {headers}"
    assert all(b.get("category") == "ADDONS" for b in items), "category is not ADDONS on every binding"


def check_binding_globals_exist_for_every_class_for_the_seals_only():
    for klass in ("PALADIN", "WARRIOR"):
        lua = boot(klass=klass)
        assert g(lua).BINDING_HEADER_FOREVERSYNTHWAVE, f"{klass}: no BINDING_HEADER_FOREVERSYNTHWAVE"
        for i in range(1, 8):
            text = g(lua)[f"BINDING_NAME_CLICK FSSealButton{i}:LeftButton"]
            assert text == expected_seals()[i - 1], f"{klass}: binding name for FSSealButton{i} is {text!r}"
            assert g(lua)[f"BINDING_NAME_CLICK FSAuraButton{i}:LeftButton"] is None, (
                f"{klass}: a binding name for FSAuraButton{i}, which has no CLICK binding")
            assert g(lua)[f"BINDING_NAME_SHAPESHIFTBUTTON{i}"] is None, "SHAPESHIFTBUTTON names are Blizzard's"


def check_hotkey_text_follows_the_click_binding():
    lua = boot()
    btn = seal(lua, 2)
    assert btn.HotKey is not None
    assert not shown(btn.HotKey) and btn.HotKey._text in (None, ""), "hotkey text with no binding"
    g(lua).__bindings["CLICK FSSealButton2:LeftButton"] = "SHIFT-F"
    fire(lua, "UPDATE_BINDINGS")
    assert shown(btn.HotKey) and btn.HotKey._text == "SHIFT-F", f"hotkey {btn.HotKey._text!r}"
    g(lua).__bindings["CLICK FSSealButton2:LeftButton"] = None
    lua.eval("__trigger")("KeybindListener.RebindSuccess")
    assert not shown(btn.HotKey), "the Quick Keybind refresh left a stale hotkey"
    # an aura reads Blizzard's SHAPESHIFTBUTTONi of its own form, never a CLICK command
    g(lua).__bindings["CLICK FSAuraButton5:LeftButton"] = "ALT-9"
    fire(lua, "UPDATE_BINDINGS")
    assert not shown(aura(lua, 5).HotKey), "an aura read a CLICK binding"
    g(lua).__bindings["SHAPESHIFTBUTTON5"] = "ALT-2"
    fire(lua, "UPDATE_BINDINGS")
    assert aura(lua, 5).HotKey._text == "ALT-2" and not shown(btn.HotKey)
    # the key belongs to the FORM: Devotion is form 2 here and sorts into slot 1
    auras = expected_auras()
    lua = boot(forms=[auras[1], auras[0]])
    g(lua).__bindings["SHAPESHIFTBUTTON2"] = "F"
    fire(lua, "UPDATE_BINDINGS")
    assert aura(lua, 1).HotKey._text == "F" and not shown(aura(lua, 2).HotKey), "the hotkey followed the slot"
    g(lua).__bindings["SHAPESHIFTBUTTON2"] = "G"
    lua.eval("__trigger")("KeybindListener.RebindSuccess")
    assert aura(lua, 1).HotKey._text == "G", "the Quick Keybind refresh missed an aura hotkey"
    # a re-sync that moves the form index repaints the hotkey
    set_forms(lua, [auras[0], auras[1]])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not shown(aura(lua, 1).HotKey), "the hotkey stayed on the old form index after a re-sync"


def check_the_look_is_the_stance_bars_with_the_seals_own_colour():
    lua = boot()
    colors = MU["SEAL_COLORS"]
    for i, sid in enumerate(MU["SEAL_IDS"], 1):
        btn = seal(lua, i)
        assert btn.fsSkin is not None and btn.icon is not None, f"seal {i} is not skinned"
        r, gg, b = colors[sid]
        v = btn.fsSkin.border.ring._vertex
        assert max(abs(v[1] - r), abs(v[2] - gg), abs(v[3] - b)) < 0.01, f"seal {i} ({sid}) ring {v}"
        gv = btn.fsSkin.glow._vertex
        assert max(abs(gv[1] - r), abs(gv[2] - gg), abs(gv[3] - b)) < 0.01, f"seal {i} ({sid}) glow {gv}"
    cyan = g(lua).FS.Theme.COLOR_POWER
    for i in range(1, 8):
        v = aura(lua, i).fsSkin.border.ring._vertex
        assert max(abs(v[1] - cyan[1]), abs(v[2] - cyan[2]), abs(v[3] - cyan[3])) < 0.01, f"aura {i} ring {v}"
    # the border follows the spell, not the slot (a shift moves the colour with the seal)
    seals = expected_seals()
    lua = boot(known=[seals[1]])
    r, gg, b = colors[MU["SEAL_IDS"][1]]
    v = seal(lua, 2).fsSkin.border.ring._vertex
    assert max(abs(v[1] - r), abs(v[2] - gg), abs(v[3] - b)) < 0.01, f"the Crusader button wears {v}"
    g(lua).__learn(seals[0])
    fire(lua, "SPELLS_CHANGED")
    r, gg, b = colors[MU["SEAL_IDS"][0]]
    v = seal(lua, 1).fsSkin.border.ring._vertex
    assert max(abs(v[1] - r), abs(v[2] - gg), abs(v[3] - b)) < 0.01, f"the Righteousness button wears {v}"


def check_the_tooltip_shows_the_spell():
    lua = boot()
    btn = seal(lua, 3)
    sid = g(lua).__spells[expected_seals()[2]]
    for fn in (btn._hooks["OnEnter"][i] for i in range(1, len(btn._hooks["OnEnter"]) + 1)):
        fn(btn)
    assert g(lua).GameTooltip._spellID == sid, f"tooltip spell {g(lua).GameTooltip._spellID!r} != {sid}"
    # an aura shows its form's tooltip, by form index
    auras = expected_auras()
    lua = boot(forms=[auras[1], auras[0]])
    btn = aura(lua, 1)                      # Devotion, form 2
    for fn in (btn._hooks["OnEnter"][i] for i in range(1, len(btn._hooks["OnEnter"]) + 1)):
        fn(btn)
    assert g(lua).GameTooltip._shapeshift == 2, f"aura tooltip form {g(lua).GameTooltip._shapeshift!r}"


def check_slot_point_and_host_point_are_the_only_seats(scale):
    lua = boot(scale)
    sb = g(lua).FS.SealBar
    host = g(lua).FSSealBar
    pitch = MU["BTN"] + MU["BG"]
    for row, getter in ((1, seal), (2, aura)):
        for col in range(1, 8):
            point, rel, rel_point, x, y = sb.SlotPoint(row, col)
            assert point == "BOTTOMLEFT" and rel._name == "FSSealBar" and rel_point == "BOTTOMLEFT", (
                f"SlotPoint({row},{col}): {point} {rel and rel._name} {rel_point}")
            approx(x, (MU["PAD"] + (col - 1) * pitch) * scale, f"SlotPoint({row},{col}) x", 0.01)
            approx(y, (MU["PB"] + (2 - row) * pitch) * scale, f"SlotPoint({row},{col}) y", 0.01)
            p = getter(lua, col)._points[1]
            assert (p.point, p.rel._name, p.relPoint) == (point, "FSSealBar", rel_point), "button not seated by SlotPoint"
            approx(p.x, x, f"button ({row},{col}) x"), approx(p.y, y, f"button ({row},{col}) y")
    point, rel, rel_point, x, y = sb.HostPoint()
    assert (point, rel._name, rel_point) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT"), f"HostPoint {point} {rel_point}"
    approx(x, MU["DX"] * scale, "HostPoint x", 0.5 * scale)
    approx(y, 0, "HostPoint y")
    hp = host._points[1]
    assert (hp.point, hp.rel._name, hp.relPoint) == (point, "FSConsole", rel_point), "host not seated by HostPoint"
    approx(hp.x, x, "host x"), approx(hp.y, y, "host y")


def check_a_replaced_seat_function_moves_the_buttons_and_the_host():
    """The later class shoulder swaps these two functions; nothing else may hold a copy."""
    lua = boot()
    lua.execute("""
        local sb = FS.SealBar
        local other = CreateFrame("Frame", "OtherShoulder", UIParent)
        other:SetSize(300, 90)
        sb.HostPoint = function() return "BOTTOMLEFT", other, "BOTTOMLEFT", 11, 22 end
        sb.SlotPoint = function(row, col) return "BOTTOMLEFT", FSSealBar, "BOTTOMLEFT", col * 100, row * 10 end
    """)
    fire(lua, "SPELLS_CHANGED")
    hp = g(lua).FSSealBar._points[1]
    assert hp.rel._name == "OtherShoulder" and hp.x == 11 and hp.y == 22, f"host ignored HostPoint: {hp.rel and hp.rel._name} {hp.x} {hp.y}"
    p = seal(lua, 3)._points[1]
    assert p.x == 300 and p.y == 10, f"button ignored SlotPoint: {p.x} {p.y}"
    p = aura(lua, 2)._points[1]
    assert p.x == 200 and p.y == 20, f"aura button ignored SlotPoint: {p.x} {p.y}"
    # a HostPoint with nothing to answer hides the shoulder
    lua.execute("FS.SealBar.HostPoint = function() return nil end")
    fire(lua, "SPELLS_CHANGED")
    assert not g(lua).FSSealBar._shown, "a shoulder with no seat stayed up"


def _seat_snapshot(lua):
    """Every point, shown flag and secure attribute of the host and the 14 buttons."""
    def pts(f):
        return [(q.point, getattr(q.rel, "_name", None), q.relPoint, round(q.x, 4), round(q.y, 4))
                for q in f._points.values()]
    out = {"host": (pts(g(lua).FSSealBar), bool(g(lua).FSSealBar._shown))}
    for i in range(1, 8):
        for label, btn in (("seal", seal(lua, i)), ("aura", aura(lua, i))):
            out[f"{label}{i}"] = (pts(btn), shown(btn), spell_of(btn), btn.fsCommand if label == "aura" else None)
    return out


def check_a_throwing_shoulder_falls_back_to_the_seat_arithmetic():
    """A throwing ClassShoulder.SlotPoint or HostPoint (each alone, then both) must leave the host and
    every button seated exactly as with no shoulder, and every attribute applied: the pcall around
    each call is what keeps a bad shoulder from taking the buttons down with it."""
    base = _seat_snapshot(boot())
    assert base["host"][1] and base["seal1"][1], "the control boot seated nothing"
    for label, body in (
        ("both", "HostPoint = function() error('boom') end, SlotPoint = function() error('boom') end"),
        ("slot only", "SlotPoint = function() error('boom') end"),
        ("host only", "HostPoint = function() error('boom') end"),
    ):
        lua = boot(extra_lua=f"FS.ClassShoulder = {{ {body} }}")
        assert _seat_snapshot(lua) == base, f"{label}: a throwing shoulder changed the seat or the attributes"
        fire(lua, "SPELLS_CHANGED")
        assert _seat_snapshot(lua) == base, f"{label}: a re-sync with a throwing shoulder changed them"


def check_the_seal_order_is_pinned_independently_of_the_mockup():
    """The index of a seal is its button name and so its saved keybind: append only, never reorder.
    The literal list here is deliberately NOT read from the mockup."""
    pinned = ["Seal of Righteousness", "Seal of the Crusader", "Seal of Fury", "Seal of Command",
              "Seal of Light", "Seal of Wisdom", "Seal of Justice"]
    lua = boot()
    src = SEALBAR.read_text()
    found = re.findall(r'\{ "(Seal of [^"]+)", "[0-9a-f]{6}" \}', src)
    assert found == pinned, f"SB.SEALS order changed: {found}"
    for i, name in enumerate(pinned, 1):
        assert spell_of(seal(lua, i)) == name, f"FSSealButton{i} casts {spell_of(seal(lua, i))!r}, not {name!r}"


def check_toc_lists_sealbar_after_stancebar_and_the_console_files():
    raw = TOC.read_bytes()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "the .toc lost its CRLF endings"
    lines = [ln.strip() for ln in raw.decode("utf-8").splitlines()]
    assert lines.count("SealBar.lua") == 1, "SealBar.lua must be listed exactly once"
    at = lines.index("SealBar.lua")
    for dep in ("StanceBar.lua", "Console.lua", "ConsoleKeys.lua", "FrameHelpers.lua", "ActionBars.lua"):
        assert lines.index(dep) < at, f"SealBar.lua loads before {dep}"


def check_no_em_dashes_in_the_new_files():
    for path in (SEALBAR, BINDINGS, Path(__file__)):
        assert path.exists(), f"{path} is missing"
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{path.name} has an em dash"


def check_few_file_scope_locals():
    text = SEALBAR.read_text(encoding="utf-8")
    n = len(re.findall(r"^local (?:function )?\w+", text, re.M))
    assert n < 60, f"{n} file scope locals in SealBar.lua"


CHECKS = [
    check_fourteen_named_secure_buttons_built_once,
    check_known_spells_pack_left_in_mockup_order,
    check_all_known_fills_every_slot_in_mockup_order,
    check_nothing_known_shows_nothing,
    check_known_needs_both_the_name_and_the_spellbook,
    check_a_client_with_no_spellbook_api_trusts_the_name,
    check_secret_throwing_and_unreadable_answers_hide_and_never_throw,
    check_every_spellbook_event_reevaluates,
    check_learning_an_earlier_seal_moves_the_later_frames_not_their_names,
    check_the_icon_follows_the_spell,
    check_a_non_paladin_gets_nothing_and_keeps_its_stance_bar,
    check_a_paladin_stance_bar_hands_its_forms_over,
    check_stance_events_keep_the_gate,
    check_the_stance_suppression_holds_across_every_rebuild,
    check_the_stance_suppression_waits_out_combat,
    check_the_stance_bar_keeps_other_classes_and_a_failed_sealbar,
    check_every_button_has_a_black_edgeless_swipe_on_its_icon,
    check_the_swipe_follows_the_spell_cooldown_by_duration_object,
    check_the_swipe_falls_back_to_the_legacy_cooldown_and_guards_secrets,
    check_the_swipe_refreshes_in_combat_without_a_protected_call,
    check_a_binding_stays_on_its_seal_when_an_earlier_seal_is_learned,
    check_learned_seals_pack_left_by_moving_their_own_named_frames,
    check_seal_seats_and_attributes_wait_for_regen,
    check_the_swipe_also_follows_the_shapeshift_cooldown_event,
    check_hidden_slots_make_no_cooldown_read,
    check_a_sync_pending_in_combat_is_replayed_at_regen,
    check_no_value_is_compared_to_nil_before_its_secret_guard,
    check_a_button_with_no_spell_gets_no_cooldown_write,
    check_a_form_uses_its_own_form_cooldown_on_the_legacy_path,
    check_the_active_flag_falls_back_to_the_current_form,
    check_the_aura_row_is_the_shapeshift_forms_in_mockup_order,
    check_a_form_change_rewrites_the_aura_row,
    check_form_changes_in_combat_wait_for_regen,
    check_unreadable_form_answers_hide_the_aura_and_never_throw,
    check_unreadable_spell_names_keep_the_aura_row_in_form_order,
    check_the_active_form_lights_its_wash,
    check_the_wash_follows_the_spell_when_the_rows_shift,
    check_a_replaced_seat_function_moves_the_buttons_and_the_host,
    check_a_throwing_shoulder_falls_back_to_the_seat_arithmetic,
    check_the_seal_order_is_pinned_independently_of_the_mockup,
    check_the_shoulder_follows_the_console_on_and_off,
    check_without_a_console_the_shoulder_sits_above_the_stance_seat_and_logs_once,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_a_rescale_reaches_the_bar_without_a_geometry_notice,
    check_a_rescale_in_combat_waits_for_regen,
    check_spellbook_changes_in_combat_wait_for_regen,
    check_the_console_toggle_in_combat_never_touches_the_host,
    check_a_login_in_combat_builds_at_regen,
    check_quick_keybind_commands_and_one_hook_set,
    check_bindings_xml_declares_the_seven_seal_commands_only,
    check_binding_globals_exist_for_every_class_for_the_seals_only,
    check_hotkey_text_follows_the_click_binding,
    check_the_look_is_the_stance_bars_with_the_seals_own_colour,
    check_the_tooltip_shows_the_spell,
    check_toc_lists_sealbar_after_stancebar_and_the_console_files,
    check_no_em_dashes_in_the_new_files,
    check_few_file_scope_locals,
]
SCALED_CHECKS = [
    check_geometry_is_the_mockups,
    check_the_shoulder_stands_on_the_console_top_edge,
    check_slot_point_and_host_point_are_the_only_seats,
]


def main() -> int:
    failed = total = 0

    def run(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError) as err:
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
