#!/usr/bin/env python3
"""Runs the real AmmoTab.lua and HunterState.lua headless on the class shoulder world (sealbar and classshoulder harness
mocks) and pins the ammo tab (the regen family mockup ammo-tab-regen-family-2026-11-20: look B, the glyph in the chip, the
glyphs lying level).

What is pinned here:

  * who: a Warrior, Hunter or Rogue with a bow, crossbow or gun in the ranged slot gets the tab; a wand, a thrown weapon, a
    relic or nothing there gets none (HunterState.Ammo is nil, not 0), and equipping a bow brings it; another class builds
    nothing; the setting off frees the seat;
  * the seat: 16 design px right of the last shoulder (Hunter: after the mana regen module, 144.8; Warrior: after Thunder
    Clap, 253.6; Rogue: the first seat, 36), a 2 x 1 block;
  * the face is the mana regen module's: four of its fourteen segment cells (10 x 12 texels on a 12 pitch, centred on the
    16 px hero tile), its gauge and its bottom line slots; the number right aligned with the places before it unlit, 0000 at
    zero, 9999 at most; the full mark as "/600"; the chip holds the level arrow for a bow or crossbow, the level cartridge
    for a gun; cells and glyph runs on whole pixels at the layout's texel size;
  * the states: plenty (the regen module's resting look, muted), low at the shared warn count (amber), out (pink, the blink
    plays once on the way in); the low colours switch and the motion switch; the hover ring;
  * the gauge: the count over the full mark (the biggest count since it last rose), a restock resets the mark;
  * secrets and combat: a secret count falls back to the plain slot count, both secret is no tab; a paint in combat touches
    nothing protected and the seat waits for regen;
  * display only, the config group, the .toc order.

It is NOT the real client: that the ammo slot is slot 0 and its count plain in combat on a Hunter, GetItemInfoInstant's
class and subclass for Forever's bows, and how the digits look at the live scales are in-game checks.

    python3 tools/ammotab-harness.py

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
TAB = ADDON / "Modules/ActionBars/AmmoTab.lua"
STATE = ADDON / "Modules/CombatHud/HunterState.lua"
TOC = ADDON / "forever-stuwave.toc"
CONFIGWINDOW = ADDON / "Modules/Config/ConfigWindow.lua"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fsh = _load("fivesecond_harness", "fivesecond-harness.py")
tch = _load("thunderclap_harness", "thunderclap-harness.py")
bbh, tbh, csh, sb = fsh.bbh, fsh.tbh, fsh.csh, fsh.sb
g = sb.g

BOW, XBOW, GUN, THROWN, WAND, TOTEM = 3036, 15808, 2508, 2947, 11287, 263412
SUBCLASS = {BOW: (2, 2), XBOW: (2, 18), GUN: (2, 3), THROWN: (2, 16), WAND: (2, 19), TOTEM: (4, 0)}

AMMO_WORLD = r"""
__ammo = { weapon = %(weapon)s, item = 2512, n = %(n)d, bags = nil, secretCount = false, secretSlot = false }
__sub = %(sub)s
C_Item = C_Item or {}
C_Item.GetItemInfoInstant = function(id)
    local cs = __sub[id]
    if not cs then return nil end
    return id, "Weapon", "", "INVTYPE_RANGED", 1, cs[1], cs[2]
end
function GetInventoryItemID(unit, slot)
    if slot == 18 then return __ammo.weapon end
    if slot == 0 then return __ammo.item end
end
function GetItemCount(id)
    if __ammo.secretCount then return __SECRET end
    return __ammo.bags or __ammo.n
end
function GetInventoryItemCount(unit, slot)
    if __ammo.secretSlot then return __SECRET end
    return __ammo.n
end
"""


def boot(*, klass: str = "HUNTER", weapon=BOW, n: int = 412, combat: bool = False, pre: str = "", scale: float = 1.0):
    sub = "{" + ", ".join(f"[{k}] = {{ {a}, {b} }}" for k, (a, b) in SUBCLASS.items()) + "}"
    world = AMMO_WORLD % dict(weapon="nil" if weapon is None else weapon, n=n, sub=sub)
    files = [csh.PETDOCK, csh.CLASSSHOULDER]
    forms = None
    pre_login = csh.SPIES + world
    if klass == "WARRIOR":
        files.append(tch.TAB)
        forms = tch.FORMS
        pre_login += tch.WORLD + "__forms[3].id = 2458\n"
    elif klass in ("HUNTER", "PRIEST"):
        files.append(fsh.FSTAB)
    files += [TAB, STATE]
    mocks = tbh.MOCKS % dict(guid=tbh.GUID, bar=tbh.BAR, all="{}") + "\n" + bbh.MOCKS + "\n" + fsh.MOCKS
    return sb.boot(scale, klass=klass, known=[], combat=combat, sealbar=False, forms=forms,
                   extra_lua=csh.PATCH + mocks, extra_files=tuple(files), pre_login=pre_login + pre)


def tab(lua):
    return g(lua).FS.AmmoTab


def host(lua):
    return g(lua).FSAmmoTab


def run(lua, code):
    lua.execute(code)


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


def set_count(lua, n: int):
    run(lua, f"__ammo.n = {n}")
    fire(lua, "BAG_UPDATE_DELAYED")


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


def rgb(v) -> tuple:
    return (round(v[1], 3), round(v[2], 3), round(v[3], 3))


def theme(lua, name):
    c = g(lua).FS.Theme[name]
    return (round(c[1], 3), round(c[2], 3), round(c[3], 3))


def lit_names(lua, i: int) -> list:
    """The segment names lit in digit cell i (1..4): lit segments carry the lit alpha, unlit ones the faint ghost."""
    AT = tab(lua).AT
    cell = AT.digits[i]
    order = tab(lua).SEGMENT_ORDER
    return sorted(order[k] for k in range(1, 15) if cell.seg[k]._vertex[4] > 0.2)


def digit_of(lua, i: int):
    lit = lit_names(lua, i)
    if not lit:
        return None
    text = tab(lua).DIGIT_TEXT
    for ch in "0123456789":
        if sorted(text[ch].split()) == lit:
            return ch
    return "?" + " ".join(lit)


def readout(lua) -> str:
    return "".join(digit_of(lua, i) or "_" for i in range(1, 5))


def lit_colour(lua):
    """The colour of the first lit digit segment."""
    AT = tab(lua).AT
    for i in range(1, 5):
        for k in range(1, 15):
            seg = AT.digits[i].seg[k]
            if seg._vertex[4] > 0.2:
                return rgb(seg._vertex)
    return None


def gauge_lit(lua) -> int:
    AT = tab(lua).AT
    violet = theme(lua, "COLOR_BORDER")
    return sum(1 for i in range(1, 11) if rgb(AT.gauge.seg[i]._vertex) != violet)


def blinking(lua) -> bool:
    return bool(lua.eval("FS.AmmoTab.AT.blink:IsPlaying()"))


def glyph(lua) -> str:
    G = tab(lua).AT.chip.glyph
    a = all(shown(r) for r in G.arrow.values())
    b = all(shown(r) for r in G.bullet.values())
    na = not any(shown(r) for r in G.arrow.values())
    nb = not any(shown(r) for r in G.bullet.values())
    return "arrow" if a and nb else "bullet" if b and na else f"both? {a} {b}"


# ---------------------------------------------------------------------------------------------------------------------


def check_a_hunter_with_a_bow_gets_the_count_after_the_mana_regen_module():
    lua = boot()
    assert tab(lua).OwnsShoulder(), "no shoulder"
    assert shown(host(lua)), "host hidden"
    st = standing(lua)
    assert 36 in st and 144.8 in st, f"seats {st}"
    assert st[144.8] == (92.8, 49.0), f"block {st[144.8]}"
    assert readout(lua) == "_412", readout(lua)
    assert glyph(lua) == "arrow"
    assert tab(lua).AT.state == "plenty"
    assert lit_colour(lua) == theme(lua, "COLOR_MUTED"), "plenty is not the resting muted look"
    assert g(lua).FS.AmmoTab.AT.mark._text == "/412", g(lua).FS.AmmoTab.AT.mark._text


def check_a_warrior_with_a_bow_stands_after_thunder_clap():
    lua = boot(klass="WARRIOR", pre="__tc.known = { [6343] = true }\n")
    st = standing(lua)
    assert 187.6 in st and 253.6 in st, f"seats {st}"
    assert shown(host(lua))


def check_a_rogue_with_a_gun_takes_the_first_seat_and_the_bullet():
    lua = boot(klass="ROGUE", weapon=GUN, n=48)
    st = standing(lua)
    assert 36 in st and st[36] == (92.8, 49.0), f"seats {st}"
    assert glyph(lua) == "bullet"
    assert readout(lua) == "__48"


def check_a_crossbow_takes_arrows():
    lua = boot(klass="ROGUE", weapon=XBOW)
    assert glyph(lua) == "arrow"
    assert g(lua).FS.HunterState.AmmoKind() == "arrow"


def check_no_ammo_weapon_no_tab_and_equipping_a_bow_brings_it():
    for weapon in (WAND, THROWN, TOTEM, None):
        lua = boot(klass="ROGUE", weapon=weapon)
        assert g(lua).FS.HunterState.Ammo() is None, f"{weapon}: count {g(lua).FS.HunterState.Ammo()}"
        assert not tab(lua).OwnsShoulder(), f"{weapon}: a shoulder"
        assert not standing(lua), f"{weapon}: seats {standing(lua)}"
        assert not shown(host(lua)), f"{weapon}: host shown"
    run(lua, f"__ammo.weapon = {BOW}")
    fire(lua, "PLAYER_EQUIPMENT_CHANGED")
    assert 36 in standing(lua), "equipping a bow did not stand the shoulder"
    assert shown(host(lua)), "equipping a bow did not show the tab"


def check_another_class_builds_nothing():
    lua = boot(klass="PRIEST")
    assert g(lua).FSAmmoTab is None, "a Priest built the tab"
    assert not tab(lua).OwnsShoulder()


def check_the_setting_off_frees_the_seat():
    lua = boot(klass="ROGUE")
    run(lua, 'FS.Config.Set("ammotab.enabled", false)')
    assert not shown(host(lua)) and not standing(lua), "still there"
    run(lua, 'FS.Config.Set("ammotab.enabled", true)')
    assert shown(host(lua)) and 36 in standing(lua), "did not come back"


def check_digits_right_aligned_zero_and_cap():
    lua = boot(klass="ROGUE", n=7)
    assert readout(lua) == "___7"
    set_count(lua, 1000)
    assert readout(lua) == "1000"
    set_count(lua, 12345)
    assert readout(lua) == "9999"
    set_count(lua, 0)
    assert readout(lua) == "0000"


def check_low_is_amber_at_the_shared_warn_count_and_out_is_pink_with_one_blink():
    lua = boot(klass="ROGUE", n=61)
    AT = tab(lua).AT
    assert AT.state == "plenty"
    set_count(lua, 60)
    assert AT.state == "low" and lit_colour(lua) == theme(lua, "COLOR_AMBER"), f"{AT.state} {lit_colour(lua)}"
    assert rgb(AT.markBar._vertex) == theme(lua, "COLOR_AMBER"), "mark bar not amber"
    assert rgb(AT.chip.ring._vertex) == theme(lua, "COLOR_AMBER"), "chip ring not amber"
    run(lua, 'FS.Config.Set("gunsight.hunter.ammowarn", 30)')
    assert AT.state == "plenty", "the shared warn count did not move the tab"
    run(lua, 'FS.Config.Set("gunsight.hunter.ammowarn", 60)')
    assert not blinking(lua)
    set_count(lua, 0)
    assert AT.state == "out" and lit_colour(lua) == theme(lua, "COLOR_HEALTH"), f"{AT.state} {lit_colour(lua)}"
    assert blinking(lua), "no blink on running out"
    run(lua, "FS.AmmoTab.AT.blink:Stop()")
    set_count(lua, 0)
    assert not blinking(lua), "the blink played again without a change"
    set_count(lua, 200)
    assert AT.state == "plenty"


def check_the_switches():
    lua = boot(klass="ROGUE", n=20)
    AT = tab(lua).AT
    run(lua, 'FS.Config.Set("ammotab.lowwarn", false)')
    assert AT.state == "plenty" and lit_colour(lua) == theme(lua, "COLOR_MUTED"), "low colours off still warns"
    run(lua, 'FS.Config.Set("ammotab.lowwarn", true)')
    assert AT.state == "low"
    run(lua, 'FS.Config.Set("ammotab.motion", false)')
    set_count(lua, 0)
    assert AT.state == "out" and not blinking(lua), "motion off still blinks"


def check_a_fresh_out_at_login_does_not_blink():
    lua = boot(klass="ROGUE", n=0)
    assert tab(lua).AT.state == "out"
    assert not blinking(lua), "blinked at login"
    assert tab(lua).AT.mark._text == "/--", f"no mark yet reads {tab(lua).AT.mark._text}"
    set_count(lua, 200)
    assert tab(lua).AT.mark._text == "/200"
    set_count(lua, 0)
    assert tab(lua).AT.mark._text == "/200", "the mark forgot the restock"


def check_the_gauge_drains_against_the_full_mark():
    lua = boot(klass="ROGUE", n=600)
    assert gauge_lit(lua) == 10
    set_count(lua, 300)
    assert gauge_lit(lua) == 5, gauge_lit(lua)
    set_count(lua, 1)
    assert gauge_lit(lua) == 1, "one round left lights no segment"
    set_count(lua, 500)
    assert tab(lua).AT.full == 500 and gauge_lit(lua) == 10, "a restock did not reset the mark"
    set_count(lua, 0)
    assert gauge_lit(lua) == 0


def check_the_ammo_slot_stack_counts_when_the_bags_read_zero():
    # live 2026-11-20: Forever keeps the equipped stack in the slot, GetItemCount (bags) says 0, the slot says 200
    lua = boot(klass="WARRIOR", n=200, pre="__tc.known = { [6343] = true }\n__ammo.bags = 0\n")
    assert readout(lua) == "_200", readout(lua)
    run(lua, "__ammo.n = 199")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert readout(lua) == "_199", "a spent arrow did not move the count"


def check_secret_counts():
    lua = boot(klass="ROGUE", n=90)
    run(lua, "__ammo.secretCount = true")
    set_count(lua, 80)
    assert readout(lua) == "__80", "the plain slot count was not used"
    run(lua, "__ammo.secretSlot = true")
    fire(lua, "BAG_UPDATE_DELAYED")
    assert g(lua).FS.HunterState.Ammo() is None
    assert not shown(host(lua)) and not standing(lua), "a tab with no readable count"


def check_combat_paints_and_the_seat_waits():
    lua = boot(klass="ROGUE", n=90)
    run(lua, "__combat = true")
    set_count(lua, 40)
    assert readout(lua) == "__40" and tab(lua).AT.state == "low", "no paint in combat"
    run(lua, "FS.AmmoTab.Sync()")
    assert tab(lua).AT.pendingSync, "seated in combat"
    assert sb.blocked(lua) == 0, "a protected call was refused"
    run(lua, "__combat = false")
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert not tab(lua).AT.pendingSync, "regen did not replay the seat"


def check_cells_and_glyph_on_whole_pixels():
    for scale in (1.0, 0.8, 1.5):
        lua = boot(klass="ROGUE", scale=scale)
        AT = tab(lua).AT
        n = AT.n
        assert n >= 1
        px = AT.px / scale

        def whole(r, what):
            d = csh.D(lua, r)
            for v in (d["x"], d["y"], d["w"], d["h"]):
                k = v / px
                assert abs(k - round(k)) < 1e-6, f"scale {scale}: {what} off the pixel grid ({v})"
            return d

        xs = []
        for i in range(1, 5):
            d = whole(AT.digits[i].frame, f"digit {i}")
            xs.append(d["x"])
            sb.approx(d["w"] * scale / AT.px, 10 * n, f"digit width at {scale}")
            sb.approx(d["h"] * scale / AT.px, 12 * n, f"digit height at {scale}")
        pitch = [round((xs[i + 1] - xs[i]) * scale / AT.px, 6) for i in range(3)]
        assert pitch == [12 * n] * 3, f"pitch {pitch}"
        hero = csh.D(lua, AT.hero)
        last = csh.D(lua, AT.digits[4].frame)
        assert xs[0] >= hero["x"] and last["x"] + last["w"] <= hero["x"] + hero["w"], "readout leaves the tile"
        chip = csh.D(lua, AT.chip.fill)
        for kind in ("arrow", "bullet"):
            for k, r in AT.chip.glyph[kind].items():
                d = whole(r, f"{kind} run {k}")
                assert chip["x"] <= d["x"] and d["x"] + d["w"] <= chip["x"] + chip["w"] + 1e-6, f"{kind} leaves the chip"


def check_the_face_matches_the_mana_regen_module():
    lua = boot(klass="HUNTER")
    AT, FT = tab(lua).AT, g(lua).FS.FiveSecondTab.FT
    for key in ("HOST_W", "HOST_H", "CELL_W", "CELL_H", "GAUGE_N", "GAUGE_Y", "GAUGE_H", "GAUGE_X", "GAUGE_PITCH",
                "GAUGE_SEG_W", "GAUGE_SEG_Y", "GAUGE_SEG_H", "LED_CX", "IDLE_ALPHA", "WORD_IDLE", "GHOST_IDLE"):
        assert AT[key] == FT[key], f"{key}: {AT[key]} vs {FT[key]}"
    for key in ("x", "y", "w", "h"):
        assert AT.HERO[key] == FT.HERO[key] and AT.CHIP[key] == FT.CHIP[key], key
    assert tuple(tab(lua).SEGMENT_ORDER.values()) == tuple(g(lua).FS.FiveSecondTab.SEGMENT_ORDER.values())
    for ch in "0123456789":
        assert tab(lua).DIGIT_TEXT[ch] == g(lua).FS.FiveSecondTab.GLYPH_TEXT[ch], ch
    src = TAB.read_text(encoding="utf-8")
    assert "led_ammo" not in src and "led_segments.tga" in src, "not the regen module's art"


def check_hover_rings_cyan():
    lua = boot(klass="ROGUE")
    AT = tab(lua).AT
    run(lua, 'FSAmmoTab:GetScript("OnEnter")(FSAmmoTab)')
    assert rgb(AT.hero.fsSkin.border.ring._vertex) == theme(lua, "COLOR_POWER"), "no hover ring"
    run(lua, 'FSAmmoTab:GetScript("OnLeave")(FSAmmoTab)')
    assert rgb(AT.hero.fsSkin.border.ring._vertex) == theme(lua, "COLOR_BORDER"), "hover ring stuck"


def check_display_only():
    lua = boot(klass="ROGUE")
    h = host(lua)
    assert not (h._attrs and len(h._attrs)), "the host carries attributes"
    assert h._scripts.OnClick is None, "a click script"
    assert h._scripts.OnEnter is not None, "no tooltip"


def check_config_page_and_toc():
    toc = TOC.read_text(encoding="utf-8").splitlines()
    i = toc.index("Modules/ActionBars/AmmoTab.lua")
    assert toc.index("Modules/ActionBars/ThunderClapTab.lua") < i < toc.index("Modules/Config/ConfigWindow.lua"), "toc order"
    cw = CONFIGWINDOW.read_text(encoding="utf-8")
    assert "local function AmmoTabGroup" in cw and "AmmoTabGroup(page)\n" in cw, "no config group"
    lua = boot(klass="ROGUE")
    S = tab(lua).SETTINGS
    for name, key in (("enabled", "ammotab.enabled"), ("lowwarn", "ammotab.lowwarn"), ("motion", "ammotab.motion")):
        assert S[name].key == key and S[name].default is True and S[name].tip, name


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
