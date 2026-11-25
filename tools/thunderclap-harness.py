#!/usr/bin/env python3
"""Runs the real ThunderClapTab.lua headless on the class shoulder world (sealbar and classshoulder harness mocks) as a
Warrior, and pins the Thunder Clap tab (look A, SHOCKWAVE, of the design mockup thunderclap-tab-2026-11-12).

What is pinned here:

  * who: a Warrior with any Thunder Clap rank known gets the tab, the highest rank is the id read; no rank (levels 1 to 5),
    another class or the setting off gets none, and learning a rank brings it;
  * the seat: a 1 x 1 shoulder 16 design px right of the stance tab (x 187.6), the 38 px key on it, the host anchored only
    out of combat;
  * the states: ready (cyan ring, cyan underline, ping), cooling (the violet fill run by the engine from the duration object
    asked with the GCD left out, never a number), RAGE (red ring and word), STANCE (Berserker: grey, desaturated, word),
    another unusable reason (grey, no word), and an unreadable answer keeping the last state;
  * the cast ledger: in combat (secret seconds, plain isActive true) the tab cools until our own last clap plus 6 s, then
    flashes into ready;
  * the clap: a Thunder Clap rank cast by the player plays both waves, the flash and the jolt; another spell, a secret id or
    the motion setting off plays nothing;
  * combat: painting and the clap run in combat with nothing protected touched; the host seat waits for regen;
  * the config page lists the two settings, and the .toc loads the file after FiveSecondTab.lua and before ConfigWindow.lua.

It is NOT the real client: whether the duration object with the GCD left out is empty during another ability's GCD, whether
IsSpellUsable says unusable in Berserker Stance and its rage flag is plain in combat, and how the waves look are in-game
checks.

    python3 tools/thunderclap-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
TAB = ADDON / "Modules/ActionBars/ThunderClapTab.lua"
TOC = ADDON / "forever-stuwave.toc"
CONFIGWINDOW = ADDON / "Modules/Config/ConfigPageAddonTabs.lua"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csh = _load("classshoulder_harness", "classshoulder-harness.py")
sb = csh.sb
g = sb.g

RANKS = (6343, 8198, 8204, 8205, 11580, 11581)
FORMS = [("Battle Stance", True), ("Defensive Stance", False), ("Berserker Stance", False)]

# The client the tab reads: the clock, Thunder Clap's cooldown (plain or secret), its usability, the spellbook, the
# Berserker form id, and animation groups that record Play and Stop.
WORLD = r"""
__now = 1000
function GetTime() return __now end
__tc = { known = { [6343] = true, [8198] = true }, cd = nil, cdSecret = false, usable = true, rage = false,
    useSecret = false, durAsks = {} }
local isPlayer = IsPlayerSpell
function IsPlayerSpell(id)
    for _, r in ipairs({ 6343, 8198, 8204, 8205, 11580, 11581 }) do
        if id == r then return __tc.known[id] == true end
    end
    return isPlayer(id)
end
local cdBase = C_Spell.GetSpellCooldown
C_Spell.GetSpellCooldown = function(id)
    if not __tc.known[id] then return cdBase(id) end
    local c = __tc.cd
    if __tc.cdSecret then
        return { startTime = __SECRET, duration = __SECRET, isEnabled = true, isActive = c ~= nil }
    end
    if not c then return { startTime = 0, duration = 0, isEnabled = true, isActive = false } end
    return { startTime = c[1], duration = c[2], isEnabled = true, isActive = __now < c[1] + c[2] }
end
local durBase = C_Spell.GetSpellCooldownDuration
C_Spell.GetSpellCooldownDuration = function(id, ignoreGCD)
    if __tc.known[id] then
        __tc.durAsks[#__tc.durAsks + 1] = { id = id, ignoreGCD = ignoreGCD }
        return { tc = id, ignoreGCD = ignoreGCD }
    end
    return durBase(id, ignoreGCD)
end
C_Spell.IsSpellUsable = function(id)
    if __tc.useSecret then return __SECRET, __SECRET end
    return __tc.usable, __tc.rage
end
C_Spell.GetSpellTexture = function(id) return 136105 end
-- a StatusBar that can run from a duration object (the cooldown fill), as cooldownfill-harness gives it
Enum = Enum or {}
Enum.StatusBarTimerDirection = { ElapsedTime = 0, RemainingTime = 1 }
Enum.StatusBarInterpolation = { Immediate = 0, ExponentialEaseOut = 1 }
do
    local create = CreateFrame
    function CreateFrame(kind, ...)
        local f = create(kind, ...)
        if kind == "StatusBar" then
            function f:SetStatusBarTexture(t)
                if not self._sbTex then self._sbTex = self:CreateTexture(nil, "ARTWORK") end
            end
            function f:GetStatusBarTexture() return self._sbTex end
            function f:SetStatusBarColor() end
            function f:SetOrientation() end
            function f:SetReverseFill() end
            function f:SetMinMaxValues() end
            function f:SetValue(v) self._value = v end
            function f:SetTimerDuration(obj, interp, dir) self._timer = { obj = obj, dir = dir } end
        end
        return f
    end
end
function __Region:SetDesaturated(v) self._desat = v end
-- animation groups that remember what played
__plays = {}
function __played(r) for _, x in ipairs(__plays) do if x == r then return true end end return false end
function __Region:CreateAnimationGroup()
    local owner = self
    local group = { _playing = false, _anims = {} }
    function group:SetLooping(v) self._looping = v end
    function group:Play() self._playing = true; __plays[#__plays + 1] = owner end
    function group:Stop() self._playing = false end
    function group:IsPlaying() return self._playing end
    function group:CreateAnimation(kind)
        local anim = setmetatable({ _kind = kind }, { __index = function() return function() end end })
        function anim:SetOffset(x, y) self._offset = { x, y } end
        group._anims[#group._anims + 1] = anim
        return anim
    end
    return group
end
"""


def boot(*, klass: str = "WARRIOR", combat: bool = False, pre: str = "", scale: float = 1.0):
    pre_login = (WORLD + "__forms[3].id = 2458\n" + pre)
    return sb.boot(scale, klass=klass, known=[], combat=combat, sealbar=False, forms=FORMS,
                   extra_lua=csh.PATCH, extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, TAB), pre_login=pre_login)


def tab(lua):
    return g(lua).FS.ThunderClapTab


def host(lua):
    return g(lua).FSThunderClapTab


def key(lua):
    return g(lua).FSThunderClapKey


def run(lua, code):
    lua.execute(code)


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


def state(lua):
    return tab(lua).TC.state


def ring_rgb(lua):
    c = key(lua).fsSkin.border.ring._vertex
    return (round(c[1], 3), round(c[2], 3), round(c[3], 3))


def theme(lua, name):
    c = g(lua).FS.Theme[name]
    return (round(c[1], 3), round(c[2], 3), round(c[3], 3))


def paint(lua):
    run(lua, "FS.ThunderClapTab.Paint()")


def played(lua, region) -> bool:
    return bool(lua.eval("__played")(region))


def plays(lua) -> list:
    t = g(lua).__plays
    return [t[i] for i in range(1, len(t) + 1)]


def clear_plays(lua):
    run(lua, "__plays = {}")


def shown(r) -> bool:
    return bool(r._shown)


def standing(lua) -> dict:
    out = {}
    lua.execute("__stand = {}")
    lua.execute("FS.ClassShoulder.EachStanding(function(dx, w, h) __stand[#__stand + 1] = { dx, w, h } end)")
    t = g(lua).__stand
    for i in range(1, len(t) + 1):
        out[round(t[i][1], 3)] = (round(t[i][2], 3), round(t[i][3], 3))
    return out


# ---------------------------------------------------------------------------------------------------------------------


def check_a_warrior_with_a_rank_gets_the_tab_on_the_highest_rank():
    lua = boot()
    assert tab(lua).OwnsShoulder(), "no shoulder"
    assert tab(lua).SpellID() == 8198, f"spell id {tab(lua).SpellID()}"
    assert shown(host(lua)) and shown(key(lua)), "the tab is hidden"
    assert state(lua) == "ready", f"state {state(lua)}"


def check_the_seat_is_a_one_key_shoulder_right_of_the_stances():
    lua = boot()
    st = standing(lua)
    assert 36 in st and st[36][0] == 135.6, f"stance shoulder {st}"
    assert 187.6 in st, f"no shoulder at 187.6: {st}"
    assert st[187.6] == (50.0, 49.0), f"block {st[187.6]}"
    d = csh.D(lua, key(lua))
    sb.approx(d["x"], 187.6 + 6, "key x")
    sb.approx(d["w"], 38, "key width")
    sb.approx(d["y"], -49 + 6, "key top")


def check_no_rank_no_tab_and_learning_brings_it():
    lua = boot(pre="__tc.known = {}\n")
    assert not tab(lua).OwnsShoulder(), "a shoulder with no rank known"
    assert not shown(host(lua)), "host shown with no rank"
    assert 187.6 not in standing(lua), "the shoulder stands"
    run(lua, "__tc.known = { [6343] = true }")
    fire(lua, "SPELLS_CHANGED")
    assert tab(lua).SpellID() == 6343
    assert 187.6 in standing(lua), "learning did not stand the shoulder"
    assert shown(host(lua)), "learning did not show the tab"


def check_another_class_builds_nothing():
    lua = boot(klass="PALADIN")
    assert g(lua).FSThunderClapTab is None, "a Paladin built the tab"
    assert not tab(lua).OwnsShoulder()


def check_the_setting_off_hides_it_and_frees_the_seat():
    lua = boot()
    run(lua, 'FS.Config.Set("thunderclap.enabled", false)')
    assert not shown(host(lua)), "still shown"
    assert 187.6 not in standing(lua), "the shoulder still stands"
    run(lua, 'FS.Config.Set("thunderclap.enabled", true)')
    assert shown(host(lua)) and 187.6 in standing(lua), "did not come back"


def check_ready_is_cyan_with_the_ping():
    lua = boot()
    assert ring_rgb(lua) == theme(lua, "COLOR_POWER"), "ring not cyan"
    assert shown(key(lua).fsUnderline), "no underline"
    assert key(lua).fsPing.group._playing, "no ping while ready"
    assert not shown(key(lua).fsWord), "a word on ready"


def check_cooling_runs_the_engine_fill_from_the_gcd_less_object():
    lua = boot()
    run(lua, "__tc.cd = { __now, 6 }; __tc.durAsks = {}")
    fire(lua, "SPELL_UPDATE_COOLDOWN")
    assert state(lua) == "cool", f"state {state(lua)}"
    assert ring_rgb(lua) == theme(lua, "COLOR_BORDER"), "ring not violet"
    fill = key(lua).fsCdFill
    assert fill and shown(fill), "no fill"
    assert fill._timer.obj.ignoreGCD is True, "the fill must use the duration with the GCD left out"
    assert fill._timer.dir == 1, "remaining time direction"
    assert not shown(key(lua).cooldown), "the swipe shows on a tracker"
    assert not key(lua).fsPing.group._playing, "ping while cooling"


def check_rage_and_stance_and_other_unusable():
    lua = boot()
    run(lua, "__tc.usable = false; __tc.rage = true")
    paint(lua)
    assert state(lua) == "rage" and key(lua).fsWord._text == "RAGE", "rage"
    assert ring_rgb(lua) == theme(lua, "COLOR_RED"), "rage ring not red"
    run(lua, "__tc.rage = false; __forms[1].active = false; __forms[3].active = true")
    paint(lua)
    assert state(lua) == "stance" and key(lua).fsWord._text == "STANCE", f"stance: {state(lua)}"
    assert key(lua).icon._desat, "stance icon not desaturated"
    run(lua, "__forms[3].active = false; __forms[2].active = true")
    paint(lua)
    assert state(lua) == "unusable" and not shown(key(lua).fsWord), "other unusable shows a word"


def check_an_unreadable_answer_keeps_the_last_state():
    lua = boot()
    run(lua, "__tc.usable = false; __tc.rage = true")
    paint(lua)
    run(lua, "__tc.useSecret = true; __tc.cdSecret = true; C_Spell.GetSpellCooldown = function() return __SECRET end")
    paint(lua)
    assert state(lua) == "rage", f"state moved to {state(lua)}"


def check_combat_ledger_cools_six_seconds_after_our_clap_then_flashes_ready():
    lua = boot()
    run(lua, "__combat = true; __tc.cdSecret = true; __tc.cd = { 0, 0 }")
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast", 8198)
    assert state(lua) == "cool", f"after the clap {state(lua)}"
    clear_plays(lua)
    run(lua, "__now = __now + 5.9")
    paint(lua)
    assert state(lua) == "cool", "ready too soon"
    run(lua, "__now = __now + 0.2")
    paint(lua)
    assert state(lua) == "ready", f"not ready after 6 s: {state(lua)}"
    assert played(lua, key(lua).fsArrive), "no arrive flash at ready"
    assert sb.blocked(lua) == 0, "a protected call was refused"


def check_a_clap_plays_waves_flash_and_jolt():
    lua = boot()
    clear_plays(lua)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast", 6343)
    k = key(lua)
    for i, wave in enumerate((k.fsWaves[1], k.fsWaves[2]), 1):
        assert played(lua, wave.tex), f"wave {i} did not play"
    assert played(lua, k.fsFlash), "no flash"
    assert played(lua, k), "no jolt"


def check_other_casts_secret_ids_and_motion_off_play_nothing():
    lua = boot()
    clear_plays(lua)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast", 78)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "cast", 6343)
    lua.eval("__fire_event")("UNIT_SPELLCAST_SUCCEEDED", "player", "cast", lua.eval("__SECRET"))
    assert plays(lua) == [], "something played"
    assert tab(lua).TC.lastCast is None, "the ledger took a cast that was not ours"
    run(lua, 'FS.Config.Set("thunderclap.motion", false)')
    clear_plays(lua)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast", 6343)
    assert plays(lua) == [], "motion off still played"
    assert not key(lua).fsPing.group._playing, "ping with motion off"
    assert tab(lua).TC.lastCast is not None, "motion off must still keep the ledger"


def check_the_seat_waits_for_regen_in_combat():
    lua = boot()
    run(lua, "__combat = true")
    run(lua, "FS.ThunderClapTab.Sync()")
    assert tab(lua).TC.pendingSync, "seated in combat"
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "cast", 6343)
    assert sb.blocked(lua) == 0, "a protected call was refused"
    run(lua, "__combat = false")
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).TC.pendingSync, "regen did not replay the seat"


def check_display_only():
    lua = boot()
    k = key(lua)
    assert not (k._attrs and len(k._attrs)), "the key carries attributes"
    assert k._scripts.OnClick is None and k._scripts.PostClick is None, "the key has a click script"


def check_config_page_and_toc():
    toc = TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/ThunderClapTab.lua")
    assert toc.index("Modules/ActionBars/FiveSecondTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua"), "toc order"
    cw = CONFIGWINDOW.read_text(encoding="utf-8")
    assert 'Module("ThunderClapTab"' in cw and "Thunder Clap tab" in cw, "no config group"
    lua = boot()
    S = tab(lua).SETTINGS
    assert S.enabled.key == "thunderclap.enabled" and S.enabled.default is True
    assert S.motion.key == "thunderclap.motion" and S.motion.default is True


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
