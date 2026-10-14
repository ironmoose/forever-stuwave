#!/usr/bin/env python3
"""Headless check of the spell icon style (Core/SpellArt.lua, Core/SpellArtData.lua).

Runs the real SpellArt.lua and the generated lookup table under lupa against a small mock Config. What it pins:

  * the data: every art name in the table is a shipped 64x64 32 bit TGA (spellart_<icon>.tga) and no shipped
    spellart file is orphaned; the by-file, by-name and by-spell tables describe the same set of icons;
  * coverage: every totem in ShamanTotems.lua's DEFS, every imbue and shield ShamanBuffs.lua draws, and the
    Paladin seals and auras and the Warrior stances the other class tabs draw have an entry (by spell id);
  * Resolve: the default `icons.spellstyle` = gradient maps the icon file id the client reports (or an
    Interface\\Icons path) to the baked file; an icon with no baked art, a nil, a secret value and the `stock`
    setting all give the stock texture back untouched, so a tile is never blank;
  * Set: writes the resolved texture and remembers the stock one, so switching the setting repaints every bound
    texture live (texture writes only), and a texture that is later bound to another icon follows that one;
  * the class tabs draw every spell icon through FrameHelpers.SetSpellIcon (no raw SetTexture of a spell icon
    is left), SpellArt loads before its first consumer, and the Unit Frames page offers the setting.

    python3 tools/spellart-harness.py

Exit 0 = every check passed; otherwise the number of failures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
MEDIA = ADDON / "Media" / "Textures"
FAILS: list[str] = []

# Independent oracle: the spell ids the other class tabs draw (their names are in SealBar.lua SEALS and AURAS and
# StanceBar's forms; the ids are rank 1, TBC). Seal of Fury is a Forever spell with no known id and stays stock.
OTHER_TAB_SPELLS = {
    21084: "Seal of Righteousness", 21082: "Seal of the Crusader", 20375: "Seal of Command", 20165: "Seal of Light",
    20166: "Seal of Wisdom", 20164: "Seal of Justice",
    465: "Devotion Aura", 7294: "Retribution Aura", 19746: "Concentration Aura", 19876: "Shadow Resistance Aura",
    19888: "Frost Resistance Aura", 19891: "Fire Resistance Aura", 20218: "Sanctity Aura",
    2457: "Battle Stance", 71: "Defensive Stance", 2458: "Berserker Stance",
}

MOCK = r"""
CONFIG, CALLBACKS = {}, {}
FS = {
    IsSecret = function(v) return v == 100.5 end,
    Config = {
        RegisterDefault = function(key, value) CONFIG[key] = CONFIG[key] end,
        Get = function(key) return CONFIG[key] end,
        Set = function(key, value)
            local old = CONFIG[key]
            CONFIG[key] = value
            if old ~= value then for _, fn in ipairs(CALLBACKS[key] or {}) do fn(value, old, key) end end
        end,
        OnChange = function(key, fn) CALLBACKS[key] = CALLBACKS[key] or {}; table.insert(CALLBACKS[key], fn) end,
    },
}
function NewTex() return { SetTexture = function(self, p) self.tex = p; self.writes = (self.writes or 0) + 1 end } end
function NewBroken() return { SetTexture = function() error("boom") end } end
function load_chunk(src, name) return assert(loadstring(src, name))("ForeverSTUwave", FS) end
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]"))
    if not ok:
        FAILS.append(name)


def tga_header(path: Path) -> tuple[int, int, int, int]:
    h = path.read_bytes()[:18]
    return h[2], int.from_bytes(h[12:14], "little"), int.from_bytes(h[14:16], "little"), h[16]


def world() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MOCK)
    load = lua.globals().load_chunk
    for name in ("SpellArtData.lua", "SpellArt.lua"):
        load((ADDON / "Core" / name).read_text(encoding="utf-8"), "@" + name)
    return lua


def table_items(t) -> dict:
    return {k: v for k, v in t.items()}


def check_data(lua: LuaRuntime) -> None:
    data = lua.eval("FS.SpellArtData")
    by_file, by_name, by_spell = table_items(data.byFile), table_items(data.byName), table_items(data.bySpell)
    stems = set(by_file.values())
    shipped = sorted(p.name for p in MEDIA.glob("spellart_*.tga"))
    missing = [s for s in sorted(stems) if not (MEDIA / f"spellart_{s}.tga").exists()]
    check("data.every_art_name_is_a_shipped_file", len(stems) >= 30 and not missing, f"{len(stems)} names, missing {missing}")
    bad = [n for n in shipped if tga_header(MEDIA / n) != (2, 64, 64, 32)]
    check("data.art_is_64x64_bgra_tga", shipped and not bad, f"{len(shipped)} files, bad {bad}")
    orphans = [n for n in shipped if n[len("spellart_"):-4] not in stems]
    check("data.no_spellart_file_is_orphaned", not orphans, f"{orphans}")
    check("data.the_three_tables_describe_the_same_icons",
          set(by_name) == stems == set(by_name.values()) and set(by_spell.values()) <= stems and set(by_spell.values()) == stems,
          f"file {len(stems)} name {len(by_name)} spell {len(set(by_spell.values()))}")
    check("data.names_are_lower_case", all(k == str(k).lower() for k in by_name), f"{[k for k in by_name if k != str(k).lower()]}")

    ids = set(int(i) for i in by_spell)
    totems = {int(m) for m in re.findall(r"id = (\d+), name = \"[^\"]+ Totem\"", (ADDON / "Modules/CombatHud/ShamanTotems.lua").read_text(encoding="utf-8"))}
    buffs = {int(m) for m in re.findall(r"base = (\d+)", (ADDON / "Modules/ActionBars/ShamanBuffs.lua").read_text(encoding="utf-8"))}
    check("coverage.every_totem_has_art", len(totems) >= 15 and totems <= ids, f"{len(totems)} totems, missing {sorted(totems - ids)}")
    check("coverage.every_imbue_and_shield_has_art", len(buffs) >= 6 and buffs <= ids, f"{sorted(buffs)} missing {sorted(buffs - ids)}")
    check("coverage.paladin_seals_auras_and_warrior_stances_have_art", set(OTHER_TAB_SPELLS) <= ids,
          f"missing {sorted(set(OTHER_TAB_SPELLS) - ids)}")


def check_resolve() -> None:
    lua = world()
    sa = lua.eval("FS.SpellArt")
    path = lambda name: f"Interface\\AddOns\\forever-stuwave\\Media\\Textures\\spellart_{name}.tga"  # noqa: E731
    first_file, first_name = next(iter(table_items(lua.eval("FS.SpellArtData.byFile")).items()))
    check("resolve.default_style_is_gradient", str(sa.Style()) == "gradient", f"{sa.Style()}")
    check("resolve.mapped_file_id_gives_the_baked_file", str(sa.Resolve(first_file)) == path(first_name), f"{sa.Resolve(first_file)}")
    check("resolve.interface_icons_path_maps_by_name",
          str(sa.Resolve(f"Interface\\Icons\\{first_name.upper()}")) == path(first_name)
          and str(sa.Resolve(f"interface/icons/{first_name}.blp")) == path(first_name), f"{sa.Resolve('Interface\\Icons\\' + first_name)}")
    check("resolve.unmapped_icons_stay_stock", sa.Resolve(1234567) == 1234567 and str(sa.Resolve("Interface\\Icons\\inv_misc_questionmark")) == "Interface\\Icons\\inv_misc_questionmark")
    check("resolve.nil_and_odd_values_come_back_unchanged", sa.Resolve(None) is None and sa.Resolve(True) is True)
    check("resolve.a_secret_value_is_never_indexed", sa.Resolve(100.5) == 100.5)

    lua.eval("FS.Config.Set")("icons.spellstyle", "stock")
    check("resolve.stock_setting_returns_the_stock_texture", sa.Resolve(first_file) == first_file and str(sa.Style()) == "stock")
    lua.eval("FS.Config.Set")("icons.spellstyle", "nonsense")
    check("resolve.an_unknown_value_means_the_default", str(sa.Style()) == "gradient" and str(sa.Resolve(first_file)) == path(first_name))


def check_set_and_repaint() -> None:
    lua = world()
    sa = lua.eval("FS.SpellArt")
    new_tex = lua.globals().NewTex
    cfg_set = lua.eval("FS.Config.Set")
    by_file = table_items(lua.eval("FS.SpellArtData.byFile"))
    (f1, n1), (f2, n2) = list(by_file.items())[:2]
    path = lambda name: f"Interface\\AddOns\\forever-stuwave\\Media\\Textures\\spellart_{name}.tga"  # noqa: E731
    check("set.applies_is_false_until_a_tab_binds_an_icon", sa.Applies() is False)
    a, b, c = new_tex(), new_tex(), new_tex()
    sa.Set(a, f1)
    sa.Set(b, f2)
    sa.Set(c, 999999)
    check("set.writes_the_resolved_texture", str(a.tex) == path(n1) and str(b.tex) == path(n2) and c.tex == 999999, f"{a.tex} {b.tex} {c.tex}")
    check("set.applies_once_an_icon_is_bound", sa.Applies() is True)
    cfg_set("icons.spellstyle", "stock")
    check("set.switching_to_stock_repaints_every_bound_texture", a.tex == f1 and b.tex == f2 and c.tex == 999999, f"{a.tex} {b.tex} {c.tex}")
    cfg_set("icons.spellstyle", "gradient")
    check("set.switching_back_repaints_again", str(a.tex) == path(n1) and str(b.tex) == path(n2) and c.tex == 999999)
    sa.Set(a, f2)
    cfg_set("icons.spellstyle", "stock")
    check("set.a_rebound_texture_follows_its_new_icon", a.tex == f2, f"{a.tex}")
    sa.Forget(b)
    cfg_set("icons.spellstyle", "gradient")
    check("set.a_forgotten_texture_is_left_alone", b.tex == f2 and str(a.tex) == path(n2), f"{b.tex} {a.tex}")
    # a texture whose write raises is skipped, never fatal, and the others still repaint
    lua.execute(f"BROKEN = NewBroken(); BIND_OK = pcall(FS.SpellArt.Set, BROKEN, {f1})")
    good = new_tex()
    sa.Set(good, f1)
    cfg_set("icons.spellstyle", "stock")
    cfg_set("icons.spellstyle", "gradient")
    check("set.a_texture_that_errors_never_stops_the_rest", lua.eval("BIND_OK") is True and str(good.tex) == path(n1), f"{lua.eval('BIND_OK')} {good.tex}")


def check_sources() -> None:
    read = lambda rel: (ADDON / rel).read_text(encoding="utf-8")  # noqa: E731
    users = {
        "Modules/ActionBars/BuffTab.lua": 1, "Modules/ActionBars/TotemBar.lua": 2,
        "Modules/ActionBars/SealBar.lua": 1, "Modules/ActionBars/StanceBar.lua": 1,
    }
    for rel, want in users.items():
        text = read(rel)
        n = len(re.findall(r"SetSpellIcon\(", text))
        raw = re.findall(r"\bicon:SetTexture\(", text)
        check(f"sources.{Path(rel).stem}_draws_spell_icons_through_SetSpellIcon", n >= want and not raw, f"{n} calls, raw {raw}")
    fh = read("Core/FrameHelpers.lua")
    check("sources.FrameHelpers_SetSpellIcon_delegates_with_a_stock_fallback",
          re.search(r"function Helpers\.SetSpellIcon\(tex, stock\)(?s:.*?)FS\.SpellArt(?s:.*?):SetTexture\(stock\)", fh) is not None)
    toc = [line.strip() for line in read("forever-stuwave.toc").splitlines() if line.strip() and not line.startswith("##")]
    pos = {name: toc.index(name) for name in ("Core/SpellArtData.lua", "Core/SpellArt.lua", "Modules/ActionBars/StanceBar.lua",
                                              "Modules/ActionBars/TotemBar.lua", "Modules/ActionBars/BuffTab.lua") if name in toc}
    check("sources.toc_loads_data_then_SpellArt_before_the_first_consumer",
          len(pos) == 5 and pos["Core/SpellArtData.lua"] < pos["Core/SpellArt.lua"] < pos["Modules/ActionBars/StanceBar.lua"], f"{pos}")
    cw = read("Modules/Config/ConfigWindow.lua")
    check("sources.unit_frames_page_offers_the_spell_icon_style", "SpellArt" in cw and "UI.Dropdown" in cw and "spellstyle" in read("Core/SpellArt.lua"))


def main() -> int:
    check_sources()
    try:
        lua = world()
    except Exception as exc:  # noqa: BLE001 (the harness names the failure instead of dying)
        check("world.loads_SpellArt_and_its_data", False, f"{type(exc).__name__}: {exc}")
        print(f"\n{len(FAILS)} failed")
        return len(FAILS)
    check_data(lua)
    check_resolve()
    check_set_and_repaint()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
