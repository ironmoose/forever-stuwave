#!/usr/bin/env python3
"""Runs the real FiveSecondTab.lua (the five second rule tab: CELLS and the regen rate) headless, in buffbar-harness's
world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua, PetActionBar.lua, PetDock.lua,
ClassShoulder.lua, and for a Paladin or a Shaman the class tab it is seated after.

The tab is a second Console shoulder (mockups/five-second-rule-module-2026-10-14.html, concept C): 2 columns x 1 row
(92.8 x 49 design px), a cells tile and a rate tile, on the player side, display only. The numbers and colours below
are read out of the mockup, so a mockup move fails here. Checked:

  * the window: a mana cast from the player starts five seconds that drain one cell a second with partial fill, the
    text counts in tenths with a ~, a free cast (cost 0, another power, no cost) or another unit's cast starts nothing,
    a re-cast restarts the full window, a channel holds it open until it ends;
  * the end: cyan cells and the word REGEN, exactly one pulse (none with the pulse toggle off), a sound only with the
    sound toggle on, then the dim idle look after a few seconds;
  * the rate tile: mana per second from GetPowerRegen, read out of combat and kept in combat with a dashed underline,
    the casting rate while suspended and the full rate otherwise, the retention chip (cyan above 0, hollow "0%");
  * the tooltips, the settings and their defaults, the master toggle;
  * who gets it: every mana class, a Druid only in a mana form, never a Warrior or a Rogue;
  * the seat: after the class tab when the class has one (Paladin, Shaman: after the buff tab), otherwise in the class
    tab's place, with the Console gap and a rescale;
  * secret values never reach arithmetic, comparison or concatenation; a throwing or missing API does not break it.

The mock is strict and is NOT the real client. FIVESECONDTAB_LUA and TOC_FILE point the harness at mutant copies (a
check must fail on a broken one).

    python3 tools/fivesecond-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
FSTAB = Path(os.environ.get("FIVESECONDTAB_LUA", ADDON / "Modules/ActionBars/FiveSecondTab.lua"))
CLASSSHOULDER = ADDON / "Modules/ActionBars/ClassShoulder.lua"
CONFIGWINDOW = ADDON / "Modules/Config/ConfigWindow.lua"
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))
MOCKUP = HERE.parent / "mockups" / "five-second-rule-module-2026-10-14.html"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bbh = _load("buffbar_harness", "buffbar-harness.py")
tbh = bbh.tbh
csh = bbh.csh
sb = bbh.sb
g = sb.g
fire = bbh.fire
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
    cell = sb._m(r"function cellTile\(x,y,s\)\{(.*?)\n\}", src, "cellTile").group(1)
    tab = sb._m(r"function tab\(s,labels\)\{(.*?)\n\}", src, "tab").group(1)
    cell_x = float(sb._m(r"cxx=x\+([\d.]+)\+i\*([\d.]+)", cell, "cell x").group(1))
    pitch = float(sb._m(r"cxx=x\+([\d.]+)\+i\*([\d.]+)", cell, "cell pitch").group(2))
    cell_y, cell_w, cell_h = (float(v) for v in sb._m(
        r'<rect x="\'\+cxx\+\'" y="\'\+\(y\+([\d.]+)\)\+\'" width="([\d.]+)" height="([\d.]+)" fill="none"', cell,
        "cell outline").groups())
    cells_n = int(sb._m(r"for\(i=0;i<(\d+);i\+\+\)\{\s*var a=susp", cell, "cell count").group(1))
    w = float(sb._m(r"W=([\d.]+)", tab, "tab width").group(1))
    bh = float(sb._m(r"BH=([\d.]+)", tab, "tab height").group(1))
    res_amber = float(sb._m(r"susp\?mix\(C\.bg,C\.amber,([\d.]+)\)", cell, "suspended plate mix").group(1))
    res_cyan = float(sb._m(r"res\?mix\(C\.bg,C\.cyan,([\d.]+)\)", cell, "resumed plate mix").group(1))
    idle_a = float(sb._m(r"fill-opacity=\"'\+\(idle\?([\d.]+):1\)", cell, "idle cell alpha").group(1))
    rate = sb._m(r"function rateTile\(x,y,s\)\{(.*?)\n\}", src, "rateTile").group(1)
    chip_fill = float(sb._m(r"fill=\"'\+mix\(C\.bg,C\.cyan,([\d.]+)\)\+'\" stroke=\"'\+C\.cyan", rate, "chip fill").group(1))
    return dict(colors=colors, cell_x=cell_x, pitch=pitch, cell_y=cell_y, cell_w=cell_w, cell_h=cell_h, cells=cells_n,
                W=w, BH=bh, susp_plate=res_amber, res_plate=res_cyan, idle_cell_a=idle_a, chip_fill=chip_fill)


MK = mockup()
C = MK["colors"]
BG = C["bg"]
BTN, PAD, GAP, PT, PB = 38, 6, 4.8, 6, 5

# ---------------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------------

MANA, FREE, ENERGY, ZERO, CHAN, HEAL = 585, 1, 2, 3, 4, 2060
MOCKS = r"""
-- GetPowerRegen: a plain pair out of combat, secrets in combat
__regen = { 12.4, 0.001 }
function GetPowerRegen()
    if __regenMode == "throw" then error("GetPowerRegen blew up") end
    if __combat then return __SECRET, __SECRET end
    return __regen[1], __regen[2]
end
-- C_Spell.GetSpellPowerCost: id -> list of { type, cost }, nothing for an id not listed (a free spell)
__costs, __costMode = {}, nil
C_Spell.GetSpellPowerCost = function(id)
    if __costMode == "throw" then error("GetSpellPowerCost blew up") end
    if __costMode == "secret" then return __SECRET end
    if __costMode == "secretentry" then return { { type = __SECRET, cost = 10 } } end
    -- a plain mana entry next to one with a secret field: the secret one could hide a cost, so the answer is unreadable
    if __costMode == "secretcost" then return { { type = 0, cost = __SECRET }, { type = 0, cost = 25 } } end
    if __costMode == "secrettype" then return { { type = __SECRET, cost = 10 }, { type = 0, cost = 25 } } end
    if __costMode == "secretper" then return { { type = 0, cost = 0, costPerSec = __SECRET }, { type = 0, cost = 25 } } end
    return __costs[id]
end
__costs[585] = { { type = 0, cost = 30, minCost = 30, name = "MANA" } }
__costs[2] = { { type = 3, cost = 30, name = "ENERGY" } }
__costs[3] = { { type = 0, cost = 0, name = "MANA" } }
__costs[4] = { { type = 0, cost = 120, name = "MANA" } }
__costs[2060] = { { type = 0, cost = 305, name = "MANA" } }
__costs[5] = { { type = 3, cost = 10 }, { type = 0, cost = 25 } }
-- a Druid's form power: 0 MANA, 3 ENERGY, 1 RAGE
__powerType = { 0, "MANA" }
__powerMode = nil
function UnitPowerType()
    if __powerMode == "throw" then error("UnitPowerType blew up") end
    if __powerMode == "secret" then return __SECRET, __SECRET end
    return __powerType[1], __powerType[2]
end
-- UnitChannelInfo: the name of the channel in progress, or nothing
__channel = nil
function UnitChannelInfo() return __channel end
-- the sound
__sounds = {}
SOUNDKIT = { TELL_MESSAGE = 3081 }
function PlaySound(id) __sounds[#__sounds + 1] = id end
function __castOk(id) __fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
"""


def boot(scale: float = 1.0, *, klass: str = "PRIEST", combat: bool = False, console: bool = True,
         pre_login: str = "", load_tab: bool = True):
    """A world of class `klass` (its own class tab included for a Paladin and a Shaman), with the tab loaded last."""
    mocks = tbh.MOCKS % dict(guid=tbh.GUID, bar=tbh.BAR, all="{}") + "\n" + bbh.MOCKS + "\n" + MOCKS
    files = [csh.PETDOCK, csh.CLASSSHOULDER]
    sealbar = False
    if klass == "PALADIN":
        files.append(sb.SEALBAR)
    elif klass == "SHAMAN":
        files += [tbh.TOTEMPIECE, tbh.TOTEMBAR, bbh.SHAMANBUFFS, bbh.BUFFTAB]
    if load_tab:
        files.append(FSTAB)
    known = None if klass == "PALADIN" else []
    if klass == "SHAMAN":
        known = []
    return sb.boot(scale, klass=klass, known=known, combat=combat, console=console, sealbar=sealbar,
                   extra_lua=csh.PATCH + mocks, extra_files=tuple(files), pre_login=csh.SPIES + pre_login)


def ft(lua):
    return g(lua).FS.FiveSecondTab


def cells_tile(lua):
    return g(lua).FSFiveSecondCells


def rate_tile(lua):
    return g(lua).FSFiveSecondRate


def host(lua):
    return g(lua).FSFiveSecondTab


def run(lua, code):
    lua.execute(code)


def cast(lua, spell=MANA):
    run(lua, f"__castOk({spell})")


def tick(lua, seconds, step=0.05):
    """Moves the clock `seconds` in frame sized steps, running every OnUpdate, then repaints."""
    n = max(1, round(seconds / step))
    for _ in range(n):
        lua.eval("__tickAll")(seconds / n)
    ft(lua).Update()
    ft(lua).Paint()


def refresh(lua):
    ft(lua).Update()
    ft(lua).Paint()


def view(lua):
    ft(lua).Update()
    return ft(lua).View()


def plain_text(s) -> str:
    return re.sub(r"\|r", "", re.sub(r"\|c[0-9a-fA-F]{8}", "", str(s)))


def rgb(v):
    return tuple(float(v[i]) for i in (1, 2, 3))


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def shown(r) -> bool:
    return bool(r._shown)


def conf(lua, key, value):
    g(lua).FS.Config.Set(key, value)


def seq(table) -> list:
    return csh.seq(table)


def fills(lua, scale=1.0) -> list:
    """Each cell's fill as a fraction of the cell height (0 when the fill is hidden)."""
    out = []
    for cell in seq(cells_tile(lua).fsCells):
        f = cell.fill
        out.append(round(float(f._h) / (MK["cell_h"] * scale), 3) if shown(f) else 0.0)
    return out


def cell_color(lua, i=1):
    f = seq(cells_tile(lua).fsCells)[i - 1].fill
    return rgb(f._vertex), float(f._vertex[4])


def cells_look(lua):
    t = cells_tile(lua)
    return dict(
        text=plain_text(t.fsText._text), ring=rgb(t.fsSkin.border.ring._vertex), ring_a=float(t.fsSkin.border.ring._vertex[4]),
        glow=rgb(t.fsSkin.glow._vertex), glow_a=float(t.fsSkin.glow._vertex[4]), plate=rgb(t.fsPlate._vertex),
        line=rgb(t.fsLine._vertex), line_a=float(t.fsLine._vertex[4]), text_color=rgb(t.fsText._textColor),
        text_a=float(t.fsText._textColor[4]),
    )


def rate_look(lua):
    t = rate_tile(lua)
    return dict(
        text=plain_text(t.fsText._text), code=plain_text(t.fsChip.code._text), chip=rgb(t.fsChip.ring._vertex),
        fill=rgb(t.fsChip.fill._vertex), fill_a=float(t.fsChip.fill._vertex[4]), code_color=rgb(t.fsChip.code._textColor),
        chip_glow_a=float(t.fsChip.glow._vertex[4]), line=rgb(t.fsLine._vertex), line_a=float(t.fsLine._vertex[4]),
        dashes=[float(t.fsDashes[k]._alpha) for k in range(1, 5)], ring_a=float(t.fsSkin.border.ring._vertex[4]),
    )


def tip_text(lua, tile):
    run(lua, "GameTooltip._lines = {}")
    lua.eval("__Region.Fire")(tile, "OnEnter")
    return [str(x) for x in seq(g(lua).GameTooltip._lines)]


def leave_tip(lua, tile):
    lua.eval("__Region.Fire")(tile, "OnLeave")


def enter_combat(lua):
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")


def leave_combat(lua):
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")


def world(scale: float = 1.0, **kw):
    return boot(scale, **kw)


# ---------------------------------------------------------------------------------------------
# Checks: the window
# ---------------------------------------------------------------------------------------------


def check_a_mana_cast_starts_five_seconds_and_the_text_counts_in_tenths():
    lua = world()
    v = view(lua)
    assert v.phase == "idle", v.phase
    cast(lua)
    v = view(lua)
    assert v.phase == "susp", v.phase
    approx(v.t, 5.0, "just cast", 0.06)
    refresh(lua)
    assert cells_look(lua)["text"] == "~5.0", cells_look(lua)["text"]
    tick(lua, 2.7)
    v = view(lua)
    assert v.phase == "susp"
    approx(v.t, 2.3, "mid countdown", 0.12)
    assert cells_look(lua)["text"] in ("~2.3", "~2.2", "~2.4"), cells_look(lua)["text"]
    # the "~" is the amber estimate mark in front of the white number
    raw = str(cells_tile(lua).fsText._text)
    assert raw.startswith("|c") and "~" in raw, raw


def check_the_cells_drain_one_a_second_right_to_left_with_a_partial_cell():
    lua = world()
    cast(lua)
    refresh(lua)
    assert fills(lua) == [1.0] * 5, fills(lua)
    tick(lua, 2.7)
    f = fills(lua)
    assert f[0] == 1.0 and f[1] == 1.0, f
    assert 0.25 <= f[2] <= 0.45, f"the third cell should hold about 30%: {f}"
    assert f[3] == 0.0 and f[4] == 0.0, f
    tick(lua, 2.0)
    f = fills(lua)
    assert 0.2 <= f[0] <= 0.4 and f[1:] == [0.0] * 4, f"the last cell empties last: {f}"


def check_the_suspended_look_is_amber_and_the_cells_are_amber():
    lua = world()
    cast(lua)
    tick(lua, 1.0)
    look = cells_look(lua)
    close(look["ring"], C["amber"], "suspended border")
    approx(look["ring_a"], 0.65, "suspended border alpha", 0.02)
    close(look["plate"], _mix(BG, C["amber"], MK["susp_plate"]), "suspended plate")
    close(look["line"], C["amber"], "suspended underline")
    col, a = cell_color(lua, 1)
    close(col, C["amber"], "suspended cell")
    approx(a, 1.0, "suspended cell alpha", 0.01)
    close(look["text_color"], C["white"], "suspended number", 0.06)


def check_a_free_cast_starts_nothing():
    for label, spell in (("zero cost", ZERO), ("another power", ENERGY), ("no cost entry", FREE)):
        lua = world()
        cast(lua, spell)
        assert view(lua).phase == "idle", f"{label} started a window"
    # a mixed cost carries a mana part
    lua = world()
    cast(lua, 5)
    assert view(lua).phase == "susp", "a cost with a mana part starts the rule"


def check_another_units_cast_and_unreadable_costs_start_nothing():
    lua = world()
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", MANA)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "party1", "guid", MANA)
    assert view(lua).phase == "idle"
    for mode in ("throw", "secret", "secretentry", "secretcost", "secrettype", "secretper"):
        lua = world()
        run(lua, f'__costMode = "{mode}"')
        cast(lua)
        assert view(lua).phase == "idle", f"{mode}: an unreadable cost started the rule"
    lua = world()
    run(lua, "C_Spell.GetSpellPowerCost = nil")
    cast(lua)
    assert view(lua).phase == "idle", "no cost API"
    lua = world()
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", g(lua).__SECRET)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", None)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", g(lua).__SECRET, "guid", MANA)
    assert view(lua).phase == "idle", "a secret spell id or unit started the rule"


def check_a_recast_restarts_the_full_window():
    lua = world()
    cast(lua)
    tick(lua, 3.0)
    approx(view(lua).t, 2.0, "before the recast", 0.12)
    cast(lua, HEAL)
    v = view(lua)
    approx(v.t, 5.0, "after the recast", 0.06)
    assert v.phase == "susp"
    # a free cast in the middle does not extend it
    tick(lua, 1.0)
    cast(lua, ZERO)
    approx(view(lua).t, 4.0, "a free cast leaves the window alone", 0.12)


def check_a_cast_after_the_rule_ended_starts_a_new_window():
    lua = world()
    cast(lua)
    tick(lua, 5.6)
    assert view(lua).phase == "res"
    cast(lua)
    v = view(lua)
    assert v.phase == "susp"
    approx(v.t, 5.0, "new window", 0.06)


def check_a_channel_holds_the_window_open_until_it_ends():
    lua = world()
    run(lua, '__channel = "Drain"')
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", CHAN)
    cast(lua, CHAN)
    tick(lua, 8.0)
    v = view(lua)
    assert v.phase == "susp", f"a channel in progress is not regen: {v.phase}"
    approx(v.t, 5.0, "held at the full window", 0.06)
    run(lua, "__channel = nil")
    fire(lua, "UNIT_SPELLCAST_CHANNEL_STOP", "player", "guid", CHAN)
    approx(view(lua).t, 5.0, "the five seconds run from the channel end", 0.12)
    tick(lua, 2.0)
    approx(view(lua).t, 3.0, "counting after the channel", 0.15)
    # a free channel holds nothing
    lua = world()
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", FREE)
    assert view(lua).phase == "idle"
    # another unit's channel holds nothing
    lua = world()
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "target", "guid", CHAN)
    assert view(lua).phase == "idle"


def check_a_channel_whose_end_event_never_comes_is_not_held_forever():
    lua = world()
    run(lua, '__channel = "Drain"')
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", CHAN)
    tick(lua, 2.0)
    assert view(lua).phase == "susp"
    run(lua, "__channel = nil")          # the client says nothing is channeling any more
    tick(lua, 0.5)
    approx(view(lua).t, 5.0, "the window starts when the channel is seen gone", 0.7)
    tick(lua, 6.0)
    assert view(lua).phase in ("res", "idle"), view(lua).phase


def check_death_and_a_loading_screen_clear_the_window():
    lua = world()
    cast(lua)
    tick(lua, 1.0)
    fire(lua, "PLAYER_DEAD")
    assert view(lua).phase == "idle"
    cast(lua)
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert view(lua).phase == "idle"


# ---------------------------------------------------------------------------------------------
# Checks: the end, the pulse, the idle fade
# ---------------------------------------------------------------------------------------------


def check_at_zero_the_cells_turn_cyan_and_say_regen():
    lua = world()
    cast(lua)
    tick(lua, 5.3)
    v = view(lua)
    assert v.phase == "res", v.phase
    refresh(lua)
    look = cells_look(lua)
    assert look["text"] == "REGEN", look["text"]
    close(look["ring"], C["cyan"], "regen border")
    approx(look["ring_a"], 1.0, "regen border alpha", 0.02)
    close(look["plate"], _mix(BG, C["cyan"], MK["res_plate"]), "regen plate")
    close(look["text_color"], C["cyan"], "regen word")
    close(look["line"], C["cyan"], "regen underline")
    assert fills(lua) == [1.0] * 5, fills(lua)
    col, a = cell_color(lua, 3)
    close(col, C["cyan"], "regen cell")
    approx(a, 1.0, "regen cell alpha", 0.01)


def check_regen_pulses_once_and_not_again_while_it_shows():
    lua = world()
    assert int(view(lua).pulses) == 0
    cast(lua)
    tick(lua, 4.8)
    assert int(view(lua).pulses) == 0, "pulsed before the end"
    tick(lua, 0.4)
    assert int(view(lua).pulses) == 1, view(lua).pulses
    glow_now = cells_look(lua)["glow_a"]
    tick(lua, 0.3)
    tick(lua, 0.3)
    assert int(view(lua).pulses) == 1, "a second pulse for the same end"
    tick(lua, 1.5)
    glow_later = cells_look(lua)["glow_a"]
    assert glow_now > glow_later + 0.15, f"the rim does not flash: {glow_now} then {glow_later}"
    assert float(view(lua).pulse) == 0.0, "the pulse never finishes"
    # a new window pulses again at its own end
    cast(lua)
    tick(lua, 5.4)
    assert int(view(lua).pulses) == 2


def check_the_pulse_toggle_off_means_no_pulse_but_the_cyan_look_stays():
    lua = world()
    conf(lua, "fivesecond.pulse", False)
    cast(lua)
    tick(lua, 5.3)
    v = view(lua)
    assert v.phase == "res"
    assert int(v.pulses) == 0, "pulsed with the pulse toggle off"
    assert float(v.pulse) == 0.0
    refresh(lua)
    assert cells_look(lua)["text"] == "REGEN"
    close(cells_look(lua)["ring"], C["cyan"], "still cyan")
    on = world()
    cast(on)
    tick(on, 5.1)
    flash = cells_look(on)["glow_a"]
    assert flash > cells_look(lua)["glow_a"] + 0.15, "the toggle off did not remove the flash"


def check_the_sound_plays_once_at_regen_only_when_its_toggle_is_on():
    lua = world()
    assert g(lua).FS.Config.Get("fivesecond.sound") is False, "the sound is off by default"
    cast(lua)
    tick(lua, 5.6)
    assert len(seq(g(lua).__sounds)) == 0, "a sound played with the toggle off"
    conf(lua, "fivesecond.sound", True)
    cast(lua)
    tick(lua, 4.9)
    assert len(seq(g(lua).__sounds)) == 0, "a sound before the end"
    tick(lua, 0.5)
    tick(lua, 1.0)
    assert len(seq(g(lua).__sounds)) == 1, f"{len(seq(g(lua).__sounds))} sounds"
    # a client with no PlaySound does not throw
    lua = world()
    conf(lua, "fivesecond.sound", True)
    run(lua, "PlaySound = nil")
    cast(lua)
    tick(lua, 5.6)
    assert view(lua).phase == "res"


def check_a_regen_seen_late_makes_no_pulse_and_no_sound():
    lua = world()
    conf(lua, "fivesecond.sound", True)
    cast(lua)
    run(lua, "__advance(12)")        # nobody looked for twelve seconds (a loading screen, a hidden tab)
    v = view(lua)
    assert int(v.pulses) == 0 and len(seq(g(lua).__sounds)) == 0
    assert v.phase == "idle", v.phase


def check_the_cue_fades_to_the_dim_idle_look_a_few_seconds_after_regen():
    lua = world()
    cast(lua)
    tick(lua, 5.3)
    assert view(lua).phase == "res"
    tick(lua, 2.0)
    assert view(lua).phase == "res" and float(view(lua).fade) > 0.99, "regen look is held for a few seconds"
    tick(lua, 1.4)
    mid = float(view(lua).fade)
    assert 0.0 < mid < 1.0, f"the look should be fading: {mid}"
    tick(lua, 2.0)
    v = view(lua)
    assert v.phase == "idle" and float(v.fade) == 0.0, (v.phase, v.fade)
    look = cells_look(lua)
    assert look["text"] == "REGEN"
    close(look["text_color"], C["muted"], "idle word")
    close(look["ring"], C["violet"], "idle border")
    approx(look["ring_a"], 0.35, "idle border alpha", 0.02)
    close(look["line"], C["muted"], "idle underline")
    approx(look["line_a"], 0.5, "idle underline alpha", 0.02)
    col, a = cell_color(lua, 2)
    close(col, C["cyan"], "idle cells stay cyan")
    approx(a, MK["idle_cell_a"], "idle cell alpha", 0.02)
    assert fills(lua) == [1.0] * 5


def check_the_idle_tab_before_any_cast_is_the_same_dim_look():
    lua = world()
    refresh(lua)
    look = cells_look(lua)
    assert look["text"] == "REGEN"
    close(look["text_color"], C["muted"], "idle word")
    approx(look["glow_a"], 0.0, "no glow")


# ---------------------------------------------------------------------------------------------
# Checks: the rate tile
# ---------------------------------------------------------------------------------------------


def check_the_rate_is_the_full_rate_outside_the_rule_and_the_casting_rate_during_it():
    lua = world()
    refresh(lua)
    r = rate_look(lua)
    assert r["text"] == "12.4/s", r["text"]
    close(r["line"], C["cyan"], "rate underline")
    approx(r["line_a"], 0.5, "idle rate underline alpha", 0.02)
    run(lua, "__regen = { 12.4, 4.1 }")
    tick(lua, 1.1)              # out of combat: re-read
    cast(lua)
    refresh(lua)
    assert rate_look(lua)["text"] == "4.1/s", rate_look(lua)["text"]
    approx(rate_look(lua)["line_a"], 0.9, "active rate underline alpha", 0.02)
    tick(lua, 5.5)
    assert rate_look(lua)["text"] == "12.4/s"


def check_the_rate_is_read_out_of_combat_kept_in_combat_and_dashed_while_kept():
    lua = world()
    refresh(lua)
    assert rate_look(lua)["dashes"] == [0.0] * 4, "a live reading is not dashed"
    assert bool(view(lua).cached) is False
    enter_combat(lua)
    run(lua, "__regen = { 20.0, 0.001 }")          # gear changed mid fight: unreadable until we leave
    tick(lua, 2.0)
    assert rate_look(lua)["text"] == "12.4/s", rate_look(lua)["text"]
    assert rate_look(lua)["dashes"] == [1.0] * 4, rate_look(lua)["dashes"]
    assert bool(view(lua).cached) is True
    cast(lua)
    tick(lua, 1.0)
    assert rate_look(lua)["text"] == "0.0/s", "the cached casting rate shows while suspended"
    leave_combat(lua)
    tick(lua, 1.2)
    assert rate_look(lua)["dashes"] == [0.0] * 4, "a reading taken out of combat is live again"
    assert rate_look(lua)["text"] == "0.0/s", "still suspended: the casting rate, now the fresh one"
    tick(lua, 4.0)
    assert rate_look(lua)["text"] == "20.0/s", rate_look(lua)["text"]
    assert blocked(lua) == 0


def check_a_login_in_combat_shows_no_number_until_one_can_be_read():
    lua = world(combat=True)
    refresh(lua)
    assert rate_look(lua)["text"] == "--", rate_look(lua)["text"]
    assert rate_look(lua)["dashes"] == [0.0] * 4, "nothing cached, nothing dashed"
    leave_combat(lua)
    tick(lua, 1.2)
    assert rate_look(lua)["text"] == "12.4/s"


def check_the_retention_chip_is_cyan_above_zero_and_a_hollow_zero_otherwise():
    lua = world()
    run(lua, "__regen = { 14.8, 0.001 }")
    tick(lua, 1.2)
    r = rate_look(lua)
    assert r["code"] == "0%", r["code"]
    close(r["chip"], _mix(C["muted"], (1, 1, 1), 0.25), "hollow chip", 0.03)
    assert r["chip_glow_a"] == 0.0
    assert view(lua).ret is None
    # Meditation: 33%
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    r = rate_look(lua)
    assert r["code"] == "33%", r["code"]
    close(r["chip"], C["cyan"], "retention chip")
    close(r["fill"], _mix(BG, C["cyan"], MK["chip_fill"]), "retention chip fill")
    close(r["code_color"], C["white"], "retention code", 0.06)
    assert r["chip_glow_a"] > 0.0
    assert int(view(lua).ret) == 33
    # staff mp5 only (0.401 of 12.4): 3%, still above zero
    run(lua, "__regen = { 12.4, 0.401 }")
    tick(lua, 1.2)
    assert rate_look(lua)["code"] == "3%", rate_look(lua)["code"]
    # zero base regen is not a division
    run(lua, "__regen = { 0, 0 }")
    tick(lua, 1.2)
    assert rate_look(lua)["code"] == "0%"


def check_the_rate_numbers_survive_secrets_and_bad_values():
    lua = world()
    refresh(lua)
    for setup in ("GetPowerRegen = nil", '__regenMode = "throw"',
                  "function GetPowerRegen() return __SECRET, 1 end",
                  "function GetPowerRegen() return 3, __SECRET end",
                  "function GetPowerRegen() return 'x', 'y' end",
                  "function GetPowerRegen() return -1, 2 end"):
        run(lua, setup)
        tick(lua, 1.3)
        assert rate_look(lua)["text"] == "12.4/s", f"{setup}: {rate_look(lua)['text']}"
    assert blocked(lua) == 0


def check_the_idle_and_the_combat_tick_allocate_nothing():
    for combat in (False, True):
        lua = world()
        refresh(lua)
        tick(lua, 2.0)
        if combat:
            enter_combat(lua)
        run(lua, """
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            local ticker = FSFiveSecondTicker
            local function step() __now = __now + 0.5; ticker._scripts.OnUpdate(ticker, 0.5) end
            for _ = 1, 50 do step() end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for _ = 1, 400 do step() end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 ticks allocated {float(g(lua).__grew):.0f} bytes"


# ---------------------------------------------------------------------------------------------
# Checks: tooltips
# ---------------------------------------------------------------------------------------------


def check_the_cells_tooltip_says_how_long_and_that_it_is_an_estimate():
    lua = world()
    cast(lua)
    tick(lua, 2.7)
    lines = tip_text(lua, cells_tile(lua))
    assert lines[0] == "Five second rule", lines
    assert re.fullmatch(r"About 2\.[2-4] s until regen resumes\.", lines[1]), lines
    assert lines[2] == "Estimate from your own casts. Free casts are not seen.", lines
    assert len(lines) == 3, lines
    # the title colour is amber while suspended
    tip = ft(lua).TipLines("cells")
    close(rgb(tip[1][2]), C["amber"], "suspended title")
    leave_tip(lua, cells_tile(lua))


def check_the_cells_tooltip_after_the_rule_says_regen_is_running():
    lua = world()
    cast(lua)
    tick(lua, 5.4)
    lines = tip_text(lua, cells_tile(lua))
    assert lines[0] == "Five second rule" and "until regen resumes" not in lines[1], lines
    assert lines[-1] == "Estimate from your own casts. Free casts are not seen.", lines
    close(rgb(ft(lua).TipLines("cells")[1][2]), C["cyan"], "regen title")


def check_the_rate_tooltip_names_both_rates_and_the_cache():
    lua = world()
    run(lua, "__regen = { 12.4, 0.001 }")
    tick(lua, 1.2)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "12.4 per second now, 12.4 once the rule ends."], lines
    cast(lua)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "0.0 per second now, 12.4 once the rule ends."], lines
    enter_combat(lua)
    tick(lua, 1.2)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "0.0 per second now, 12.4 once the rule ends.",
                     "Read out of combat, kept while you fight."], lines
    close(rgb(ft(lua).TipLines("rate")[1][2]), C["cyan"], "rate title")
    # Meditation
    lua = world()
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    cast(lua)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines[:2] == ["Mana regen", "4.9 per second now, 14.8 once the rule ends."], lines
    assert "33%" in lines[2] and "cast" in lines[2], lines


def check_the_rate_tooltip_with_no_reading_says_so():
    lua = world(combat=True)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines[0] == "Mana regen" and "cannot be read" in lines[1], lines


def check_a_tooltip_open_on_a_tile_follows_the_countdown():
    lua = world()
    cast(lua)
    tick(lua, 1.0)
    run(lua, "__owners = 0; local so = GameTooltip.SetOwner; function GameTooltip:SetOwner(...) __owners = __owners + 1; return so(self, ...) end")
    first = tip_text(lua, cells_tile(lua))[1]
    run(lua, "function GameTooltip:GetOwner() return self._owner end")
    assert int(g(lua).__owners) == 1, "one SetOwner on enter"
    tick(lua, 1.5)
    assert int(g(lua).__owners) == 1, "the open tooltip was re-anchored on a tick (it would flicker)"
    now = [str(x) for x in seq(g(lua).GameTooltip._lines)][1]
    assert now != first, f"the open tooltip kept {first!r}"
    leave_tip(lua, cells_tile(lua))


# ---------------------------------------------------------------------------------------------
# Checks: settings, master toggle, who gets it
# ---------------------------------------------------------------------------------------------


def check_the_settings_have_their_defaults_and_keys():
    lua = world()
    S = ft(lua).SETTINGS
    assert str(S.enabled.key) == "fivesecond.enabled" and S.enabled.default is True
    assert str(S.pulse.key) == "fivesecond.pulse" and S.pulse.default is True
    assert str(S.sound.key) == "fivesecond.sound" and S.sound.default is False
    for name in ("enabled", "pulse", "sound"):
        assert str(S[name].label), name
        tip = str(S[name].tip)
        assert tip.endswith("."), f"{name}: tip {tip!r}"
    cfg = g(lua).FS.Config
    assert cfg.Get("fivesecond.enabled") is True and cfg.Get("fivesecond.pulse") is True
    assert cfg.Get("fivesecond.sound") is False


def check_the_master_toggle_hides_the_tab_and_its_shoulder_and_shows_them_again():
    lua = world()
    cs = csh.cs(lua)
    assert shown(host(lua)) and cs.IsShown("fivesecond")
    conf(lua, "fivesecond.enabled", False)
    assert not shown(host(lua)), "the host stands with the master toggle off"
    assert not cs.IsShown("fivesecond"), "the shoulder stands with the master toggle off"
    assert not ft(lua).Shown()
    cast(lua)
    tick(lua, 5.6)
    assert len(seq(g(lua).__sounds)) == 0
    conf(lua, "fivesecond.enabled", True)
    assert shown(host(lua)) and cs.IsShown("fivesecond")
    # the master toggle works in combat for the host; the shoulder follows at regen
    enter_combat(lua)
    conf(lua, "fivesecond.enabled", False)
    assert not shown(host(lua))
    assert blocked(lua) == 0
    leave_combat(lua)
    assert not cs.IsShown("fivesecond")


def check_a_warrior_a_rogue_and_unreadable_classes_get_nothing():
    for klass in ("WARRIOR", "ROGUE", "THROW", "SECRET"):
        lua = boot(klass=klass)
        assert host(lua) is None and cells_tile(lua) is None, f"{klass} got a tab"
        assert not ft(lua).OwnsShoulder(), f"{klass}: the tab claims a shoulder"
        assert not csh.cs(lua).IsShown("fivesecond"), f"{klass}: the shoulder stands"
        assert not ft(lua).Applies(), klass
        for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START"):
            assert not listeners(lua, event), f"{klass}: something listens to {event}"


def listeners(lua, event):
    return [f for f in g(lua).__frames.values() if f._registered[event]]


def check_every_mana_class_gets_the_tab():
    for klass in ("PRIEST", "MAGE", "WARLOCK", "HUNTER", "DRUID", "SHAMAN", "PALADIN"):
        lua = boot(klass=klass)
        assert host(lua) is not None, f"{klass} got no tab"
        assert ft(lua).Applies(), klass
        assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond"), f"{klass}: the tab does not stand"
        assert shown(cells_tile(lua)) and shown(rate_tile(lua))


def check_a_druid_in_a_form_without_mana_hides_the_tab_and_keeps_counting():
    lua = boot(klass="DRUID")
    assert shown(host(lua))
    cast(lua)
    run(lua, '__powerType = { 3, "ENERGY" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert not shown(host(lua)), "the Druid's energy form shows the mana cue"
    assert not csh.cs(lua).IsShown("fivesecond"), "the shoulder stands for a form without mana"
    assert view(lua).phase == "susp", "the ledger must keep listening while the tab is hidden"
    run(lua, '__powerType = { 1, "RAGE" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert not shown(host(lua))
    run(lua, '__powerType = { 0, "MANA" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond")
    # an unreadable power type shows the tab (the cue is harmless)
    for mode in ("secret", "throw"):
        run(lua, f'__powerType = {{ 3, "ENERGY" }}; __powerMode = "{mode}"')
        fire(lua, "UNIT_DISPLAYPOWER", "player")
        assert shown(host(lua)), f"{mode}: an unreadable power type hid the tab"
    run(lua, "UnitPowerType = nil")
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua))
    # another class never asks the power type
    lua = boot(klass="PRIEST")
    run(lua, '__powerType = { 3, "ENERGY" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua)), "only a Druid changes form"


def check_the_cue_needs_no_target_and_hangs_on_the_ui_not_the_gunsight():
    text = "\n".join(ln for ln in FSTAB.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--"))
    for token in ("UnitExists", "HasTarget", "PLAYER_TARGET_CHANGED", "Gunsight", "GunsightAreas", "TakesDots"):
        assert token not in text, f"the tab mentions {token}: it is a player side cue"
    lua = world(pre_login="FS.Gunsight = nil; FS.GunsightAreas = nil")
    run(lua, "UnitExists = function() return false end")
    fire(lua, "PLAYER_TARGET_CHANGED")
    assert shown(host(lua)) and shown(cells_tile(lua)), "the tab needs no target"
    assert host(lua)._parent._name == "UIParent"


def check_nothing_in_the_tab_is_secure_or_touches_a_protected_frame_in_combat():
    lua = world()
    for f in g(lua).__frames.values():
        if f._name in ("FSFiveSecondTab", "FSFiveSecondCells", "FSFiveSecondRate"):
            assert not f._secure and not f._protected, f"{f._name} is a protected frame"
    enter_combat(lua)
    cast(lua)
    tick(lua, 5.6)
    lua.eval("__rescale")(1 / 1.2)
    conf(lua, "fivesecond.enabled", False)
    conf(lua, "fivesecond.enabled", True)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    assert int(g(lua).__protectedTouch) == 0, "a frame was touched under a protected parent in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


# ---------------------------------------------------------------------------------------------
# Checks: geometry and seat
# ---------------------------------------------------------------------------------------------


def stand_for(lua, dx, scale):
    for f in g(lua).__frames.values():
        pts = f._points
        if f._kind == "Frame" and len(pts) == 1 and pts[1].rel is not None and pts[1].rel._name == "FSConsole" \
                and (abs(float(pts[1].x) - dx) < 0.5 or abs(float(pts[1].x) - dx * scale) < 0.5 * scale) \
                and f._name is None and f._w > 0 and abs(float(f._w) - MK["W"] * float(f._scale or 1)) > -1 \
                and abs(float(f._h) - MK["BH"]) < 0.5:
            return f
    return None


def check_the_geometry_is_the_mockups(scale):
    approx(MK["W"], 2 * PAD + 2 * BTN + GAP, "tab width against the mockup")
    approx(MK["BH"], PT + BTN + PB, "tab height against the mockup")
    assert MK["cells"] == 5
    lua = world(scale)
    host_ = host(lua)
    approx(float(host_._w), MK["W"] * scale, "host width")
    approx(float(host_._h), MK["BH"] * scale, "host height")
    for col, tile in ((1, cells_tile(lua)), (2, rate_tile(lua))):
        q = tile._points[1]
        assert sb.same(lua, q.rel, host_) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT"), (q.point, q.relPoint)
        approx(q.x, (PAD + (col - 1) * (BTN + GAP)) * scale, f"tile {col} x")
        approx(q.y, PB * scale, f"tile {col} y")
        approx(tile._w, BTN * scale, f"tile {col} width"), approx(tile._h, BTN * scale, f"tile {col} height")
    cell_list = seq(cells_tile(lua).fsCells)
    assert len(cell_list) == 5
    for i, cell in enumerate(cell_list):
        f = cell.fill
        p = f._points[1]
        assert p.point == "BOTTOMLEFT", p.point
        approx(p.x, (MK["cell_x"] + i * MK["pitch"]) * scale, f"cell {i} x")
        approx(p.y, (BTN - MK["cell_y"] - MK["cell_h"]) * scale, f"cell {i} bottom")
        approx(f._w, MK["cell_w"] * scale, f"cell {i} width")
    assert host_._level > sb.top_level(g(lua).FSConsole), "the tab must draw above the chassis"
    lua = boot(scale=scale, klass="PRIEST")
    cs = csh.cs(lua)
    assert cs.IsShown("fivesecond")
    stand = stand_for(lua, 36, scale)
    assert stand is not None, "no frame is seated at 36 design px on the Console"
    d = csh.D(lua, stand)
    approx(d["w"], MK["W"], "art width in design px", 0.01), approx(d["h"], MK["BH"], "art height in design px", 0.01)
    bw, bh, edge = cs.BlockSize("fivesecond")
    approx(bw, MK["W"] * scale, "BlockSize width"), approx(bh, MK["BH"] * scale, "BlockSize height")


def check_a_class_without_a_tab_of_its_own_seats_the_cue_where_the_class_tab_would_stand():
    for klass in ("PRIEST", "MAGE", "WARLOCK", "HUNTER", "DRUID"):
        lua = boot(klass=klass)
        p = host(lua)._points[1]
        assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT"), klass
        approx(p.x, 36.0, f"{klass}: seat"), approx(p.y, 0, "seat y")
        assert csh.cs(lua).Shoulder("fivesecond") is not None, klass
        assert csh.cs(lua).shoulder is None, f"{klass}: the class shoulder slot is for a class tab"


def check_a_paladin_gets_it_after_the_seal_block():
    lua = boot(klass="PALADIN")
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("fivesecond"), "the seal shoulder and the cue both stand"
    seal_w = 2 * PAD + 7 * BTN + 6 * GAP
    want = 36 + seal_w + 16
    p = host(lua)._points[1]
    approx(p.x, want, "after the seal block", 0.5)
    hp = csh.cs(lua).HostPoint("fivesecond")
    approx(float(hp[3]), want, "ClassShoulder.HostPoint answers the same seat", 0.5)
    # the class block keeps its own seat
    approx(cs.HostPoint()[3], 36.0, "the seal block stays at 36")


def check_a_shaman_gets_it_after_the_buff_tab():
    lua = boot(klass="SHAMAN")
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("shamanbuff") and cs.IsShown("fivesecond")
    buff_x = 316
    want = buff_x + MK["W"] + 16
    p = host(lua)._points[1]
    approx(p.x, want, "after the buff tab", 0.5)
    # the totem tab and the buff tab keep their seats
    approx(g(lua).FSTotemBar._points[1].x, 36.0, "totem tab", 0.5)
    approx(g(lua).FSBuffTab._points[1].x, buff_x, "buff tab", 0.5)
    # it stays clear of the HUD keys tab's edge (538 design px in the mockup)
    assert want + MK["W"] + 10 < 538, want


def check_the_cue_moves_when_the_class_tab_arrives_later():
    # the Shaman's totem tab is not up yet: the cue sits in the first seat, then makes way for it
    lua = boot(klass="SHAMAN")
    cs = csh.cs(lua)
    approx(host(lua)._points[1].x, 316 + MK["W"] + 16, "both class tabs up", 0.5)
    run(lua, "FS.BuffTab.OwnsShoulder = function() return false end")
    cs.Refresh()
    approx(host(lua)._points[1].x, 316.0, "the buff tab gone: after the totem tab", 0.5)
    run(lua, "FS.TotemBar.OwnsShoulder = function() return false end")
    cs.Refresh()
    approx(host(lua)._points[1].x, 36.0, "no class tab: the first seat", 0.5)
    assert shown(host(lua))


def check_the_console_gap_covers_the_cue_and_the_top_line_is_bridged_to_the_class_tab():
    lua = boot(klass="PALADIN")
    gaps = [c for c in csh.calls(lua) if str(c).startswith("gap:")]
    last = [float(x) for x in str(gaps[-1]).split(":")[1:]]
    seal_w = 2 * PAD + 7 * BTN + 6 * GAP
    approx(last[0], 36 + 1, "gap line start", 1.5)
    assert last[1] > 36 + seal_w + 16 + MK["W"], f"the gap ends inside the cue: {last}"
    art = g(lua).FS.Console.art
    bridges = [r for r in seq(art._regions) if r._kind == "Texture" and r._color is not None and r._h == 1
               and r._points[1].x > 36 + seal_w - 1 and r._points[1].x < 36 + seal_w + 30]
    assert len(bridges) == 1 and shown(bridges[0]), f"{len(bridges)} bridge textures"
    csh.console(lua).SetActive(False)
    assert not csh.cs(lua).IsShown("fivesecond") and not shown(bridges[0])


def check_the_cue_follows_the_console_on_and_off_and_is_absent_without_one():
    lua = boot(klass="PRIEST")
    cs = csh.cs(lua)
    csh.console(lua).SetActive(False)
    assert not cs.IsShown("fivesecond")
    assert not shown(host(lua)), "no Console, no tab"
    cast(lua)
    assert view(lua).phase == "susp", "the ledger listens without a Console"
    csh.console(lua).SetActive(True)
    assert cs.IsShown("fivesecond") and shown(host(lua))
    lua = boot(klass="PRIEST", console=False)
    assert host(lua) is not None and not shown(host(lua)), "no Console at all: no seat, no crash"


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = boot(klass="PRIEST")
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    approx(float(host(lua)._w), MK["W"] * s, "host width after a rescale")
    q = rate_tile(lua)._points[1]
    approx(q.x, (PAD + BTN + GAP) * s, "tile 2 x after a rescale")
    approx(rate_tile(lua)._w, BTN * s, "tile width after a rescale")


def check_a_seat_change_in_combat_waits_for_regen():
    lua = boot(klass="PRIEST")
    enter_combat(lua)
    lua.eval("__rescale")(1 / 1.2)
    csh.console(lua).SetActive(False)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


def check_a_login_in_combat_builds_at_once_and_seats_at_regen():
    lua = boot(klass="PRIEST", combat=True)
    assert host(lua) is not None and cells_tile(lua) is not None, "the plain tiles build in combat"
    assert not shown(host(lua)) and not csh.cs(lua).IsShown("fivesecond"), "the seat waits for regen"
    assert blocked(lua) == 0 and int(g(lua).__protectedTouch) == 0
    leave_combat(lua)
    assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond")


# ---------------------------------------------------------------------------------------------
# Checks: the chrome, text and listeners
# ---------------------------------------------------------------------------------------------


def check_every_string_fits_inside_its_tile_in_every_state(scale):
    lua = world(scale)
    inner = (BTN - 2 * 3) * scale            # the cut border keeps 3 design px clear each side
    advance = 0.5615
    run(lua, "__regen = { 112.4, 12.5 }")
    tick(lua, 1.2)
    states = []
    for label in ("idle", "susp", "res"):
        if label == "susp":
            cast(lua)
        elif label == "res":
            tick(lua, 5.3)
        refresh(lua)
        states.append(label)
        for name, tile in (("cells", cells_tile(lua)), ("rate", rate_tile(lua))):
            text = plain_text(tile.fsText._text)
            px = float(tile.fsText._font[2])
            width = len(text) * advance * px
            assert width <= inner + 0.01, f"{label} {name} {text!r} at {px}px is {width:.1f} wide in {inner:.1f}"
        code = plain_text(rate_tile(lua).fsChip.code._text)
        px = float(rate_tile(lua).fsChip.code._font[2])
        assert len(code) * advance * px <= (22 - 2) * scale + 0.01 or px <= 6.0, f"{code!r} at {px}px outside the chip"


def check_the_listeners_are_for_the_unit_player_and_start_once():
    lua = world()
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_CHANNEL_STOP"):
        assert len(listeners(lua, event)) == 1, f"{event}: {len(listeners(lua, event))} listeners"
    # a throwing RegisterUnitEvent falls back to RegisterEvent and the unit filter in the handler
    lua = world(pre_login="__Region.RegisterUnitEvent = function() error('no unit events') end")
    cast(lua)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", MANA)
    assert view(lua).phase == "susp"


def check_a_failed_build_leaves_no_listener_running():
    lua = boot(klass="PRIEST", pre_login='__failBuild = "FSFiveSecondRate"')
    assert rate_tile(lua) is None
    assert not ft(lua).OwnsShoulder(), "a failed build still claims the shoulder"
    assert not csh.cs(lua).IsShown("fivesecond")
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START"):
        assert not listeners(lua, event), f"a listener for {event} runs for a tab that never drew"


def check_the_chrome_is_the_buff_tabs_cut_plate_with_a_skinned_border():
    lua = world()
    for tile in (cells_tile(lua), rate_tile(lua)):
        assert tile.fsPlate is not None and tile.fsSkin.border.ring is not None and tile.fsSkin.glow is not None
        assert tile.fsText is not None and tile.fsLine is not None
    # the hover border is the cyan ring, like the buff tab's
    tile = cells_tile(lua)
    lua.eval("__Region.Fire")(tile, "OnEnter")
    close(rgb(tile.fsSkin.border.ring._vertex), C["cyan"], "hover border")
    lua.eval("__Region.Fire")(tile, "OnLeave")
    close(rgb(tile.fsSkin.border.ring._vertex), C["violet"], "border after leaving")


def check_hiding_the_host_under_the_mouse_clears_the_hover_and_the_tooltip():
    lua = world()
    for tile in (cells_tile(lua), rate_tile(lua)):
        lua.eval("__Region.Fire")(tile, "OnEnter")
        close(rgb(tile.fsSkin.border.ring._vertex), C["cyan"], "hover border")
        assert shown(g(lua).GameTooltip), "the tooltip is up"
        host(lua).Hide(host(lua))
        lua.eval("__Region.Fire")(tile, "OnHide")        # the engine runs OnHide on the children of a hidden frame
        assert not tile.fsHover, "the hover survived the hide"
        assert not shown(g(lua).GameTooltip), "the tooltip of a hidden tile stayed up"
        host(lua).Show(host(lua))
        refresh(lua)
        close(rgb(tile.fsSkin.border.ring._vertex), C["violet"], "no hover rim after the host shows again")
    # a tooltip that belongs to something else is left alone
    lua = world()
    tile = cells_tile(lua)
    lua.eval("__Region.Fire")(tile, "OnEnter")
    run(lua, "function GameTooltip:IsOwned(f) return false end")
    lua.eval("__Region.Fire")(tile, "OnHide")
    assert shown(g(lua).GameTooltip), "hid a tooltip another frame owns"
    assert not tile.fsHover


def check_the_rate_tile_underline_is_dashed_with_the_mockups_four_dashes():
    lua = world()
    assert len(seq(rate_tile(lua).fsDashes)) == 4
    for k in range(1, 5):
        d = rate_tile(lua).fsDashes[k]
        approx(d._w, 2 * 1.0, "dash width"), approx(d._h, 2 * 1.0, "dash height")
        approx(d._points[1].x, (5 + 4 + (k - 1) * 6) * 1.0, f"dash {k} x")


def check_toc_lists_the_tab_after_the_buff_tab_and_before_the_config_window():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    f = "Modules/ActionBars/FiveSecondTab.lua"
    assert f in mods, f"{f} is not in the .toc"
    for dep in ("Modules/ActionBars/ClassShoulder.lua", "Modules/ActionBars/SealBar.lua", "Modules/ActionBars/TotemBar.lua",
                "Modules/ActionBars/BuffTab.lua", "Core/FrameHelpers.lua", "Core/Config.lua", "Core/Theme.lua"):
        assert mods.index(dep) < mods.index(f), f"{dep} must load before FiveSecondTab.lua"
    assert mods.index(f) < mods.index("Modules/Config/ConfigWindow.lua")


def check_no_em_dashes_and_no_flagged_words_in_the_new_files():
    for path in (FSTAB, Path(__file__)):
        assert path.exists(), f"{path} is missing"
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{path.name} has an em dash"
    text = FSTAB.read_text(encoding="utf-8")
    for word in (r"bot\b", "automat", "macro", "cheat", "hack", "probe", "monitor"):
        hits = [ln.strip() for ln in text.splitlines() if re.search(rf"\b{word}", ln, re.I)]
        assert not hits, f"FiveSecondTab.lua mentions {word!r}: {hits[:2]}"
    for s in re.findall(r'"([^"\n]*)"', text):
        if " " not in s and "_" in s or s.startswith(("Interface", "UNIT_", "PLAYER_")):
            continue
        assert not re.search(r"\b(probe|bot|monitor|test)\b", s, re.I), f"player text {s!r}"


def check_the_config_window_builds_a_group_for_the_three_settings():
    text = CONFIGWINDOW.read_text(encoding="utf-8")
    assert "FiveSecondTab" in text, "ConfigWindow.lua does not read FS.FiveSecondTab.SETTINGS"
    assert "SETTINGS" in text.split("FiveSecondTab", 1)[1][:600]


def check_the_class_shoulder_names_the_cue_as_a_shoulder_after_every_class_tab():
    text = CLASSSHOULDER.read_text(encoding="utf-8")
    assert "fivesecond" in text and "FiveSecondTab" in text


CHECKS = [
    check_a_mana_cast_starts_five_seconds_and_the_text_counts_in_tenths,
    check_the_cells_drain_one_a_second_right_to_left_with_a_partial_cell,
    check_the_suspended_look_is_amber_and_the_cells_are_amber,
    check_a_free_cast_starts_nothing,
    check_another_units_cast_and_unreadable_costs_start_nothing,
    check_a_recast_restarts_the_full_window,
    check_a_cast_after_the_rule_ended_starts_a_new_window,
    check_a_channel_holds_the_window_open_until_it_ends,
    check_a_channel_whose_end_event_never_comes_is_not_held_forever,
    check_death_and_a_loading_screen_clear_the_window,
    check_at_zero_the_cells_turn_cyan_and_say_regen,
    check_regen_pulses_once_and_not_again_while_it_shows,
    check_the_pulse_toggle_off_means_no_pulse_but_the_cyan_look_stays,
    check_the_sound_plays_once_at_regen_only_when_its_toggle_is_on,
    check_a_regen_seen_late_makes_no_pulse_and_no_sound,
    check_the_cue_fades_to_the_dim_idle_look_a_few_seconds_after_regen,
    check_the_idle_tab_before_any_cast_is_the_same_dim_look,
    check_the_rate_is_the_full_rate_outside_the_rule_and_the_casting_rate_during_it,
    check_the_rate_is_read_out_of_combat_kept_in_combat_and_dashed_while_kept,
    check_a_login_in_combat_shows_no_number_until_one_can_be_read,
    check_the_retention_chip_is_cyan_above_zero_and_a_hollow_zero_otherwise,
    check_the_rate_numbers_survive_secrets_and_bad_values,
    check_the_idle_and_the_combat_tick_allocate_nothing,
    check_the_cells_tooltip_says_how_long_and_that_it_is_an_estimate,
    check_the_cells_tooltip_after_the_rule_says_regen_is_running,
    check_the_rate_tooltip_names_both_rates_and_the_cache,
    check_the_rate_tooltip_with_no_reading_says_so,
    check_a_tooltip_open_on_a_tile_follows_the_countdown,
    check_the_settings_have_their_defaults_and_keys,
    check_the_master_toggle_hides_the_tab_and_its_shoulder_and_shows_them_again,
    check_a_warrior_a_rogue_and_unreadable_classes_get_nothing,
    check_every_mana_class_gets_the_tab,
    check_a_druid_in_a_form_without_mana_hides_the_tab_and_keeps_counting,
    check_the_cue_needs_no_target_and_hangs_on_the_ui_not_the_gunsight,
    check_nothing_in_the_tab_is_secure_or_touches_a_protected_frame_in_combat,
    check_a_class_without_a_tab_of_its_own_seats_the_cue_where_the_class_tab_would_stand,
    check_a_paladin_gets_it_after_the_seal_block,
    check_a_shaman_gets_it_after_the_buff_tab,
    check_the_cue_moves_when_the_class_tab_arrives_later,
    check_the_console_gap_covers_the_cue_and_the_top_line_is_bridged_to_the_class_tab,
    check_the_cue_follows_the_console_on_and_off_and_is_absent_without_one,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_a_seat_change_in_combat_waits_for_regen,
    check_a_login_in_combat_builds_at_once_and_seats_at_regen,
    check_the_listeners_are_for_the_unit_player_and_start_once,
    check_a_failed_build_leaves_no_listener_running,
    check_the_chrome_is_the_buff_tabs_cut_plate_with_a_skinned_border,
    check_hiding_the_host_under_the_mouse_clears_the_hover_and_the_tooltip,
    check_the_rate_tile_underline_is_dashed_with_the_mockups_four_dashes,
    check_toc_lists_the_tab_after_the_buff_tab_and_before_the_config_window,
    check_no_em_dashes_and_no_flagged_words_in_the_new_files,
    check_the_config_window_builds_a_group_for_the_three_settings,
    check_the_class_shoulder_names_the_cue_as_a_shoulder_after_every_class_tab,
]
SCALED_CHECKS = [
    check_the_geometry_is_the_mockups,
    check_every_string_fits_inside_its_tile_in_every_state,
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
