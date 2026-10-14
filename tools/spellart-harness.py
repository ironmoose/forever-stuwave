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
ForeverSTUwaveDB = {}
-- byFile / byName that raise when the secret value (100.5) is read as a key: removing Resolve's IsSecret guard fails a check.
function TrapSecretKeys()
    for _, field in ipairs({ "byFile", "byName" }) do
        local real = FS.SpellArtData[field]
        FS.SpellArtData[field] = setmetatable({}, { __index = function(_, k)
            if k == 100.5 then error("a secret value was used as a key") end
            return real[k]
        end })
    end
end
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
    lua.execute("TrapSecretKeys()")
    ok, got = lua.eval("function() return pcall(FS.SpellArt.Resolve, 100.5) end")()
    check("resolve.a_secret_value_is_never_indexed", ok is True and got == 100.5, f"{ok} {got}")
    ok, got = lua.eval("function() return pcall(FS.SpellArt.Resolve, 5) end")()
    check("resolve.the_trap_is_live_for_plain_ids", ok is True and got == 5, f"{ok} {got}")

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
    check("set.there_is_no_unused_Forget", sa.Forget is None)
    # a texture whose write raises is skipped, never fatal, and the others still repaint
    lua.execute(f"BROKEN = NewBroken(); BIND_OK = pcall(FS.SpellArt.Set, BROKEN, {f1})")
    good = new_tex()
    sa.Set(good, f1)
    cfg_set("icons.spellstyle", "stock")
    cfg_set("icons.spellstyle", "gradient")
    check("set.a_texture_that_errors_never_stops_the_rest", lua.eval("BIND_OK") is True and str(good.tex) == path(n1), f"{lua.eval('BIND_OK')} {good.tex}")


def check_set_never_throws() -> None:
    """Resolve runs inside Set's pcall: a secret, or a setting read that raises, can never throw out of a bind or a repaint."""
    lua = world()
    sa = lua.eval("FS.SpellArt")
    # a MAPPED id, so Resolve reaches Style() (an unmapped one returns before it)
    mapped = next(iter(table_items(lua.eval("FS.SpellArtData.byFile")).keys()))
    lua.execute("TrapSecretKeys()")
    ok = lua.eval("function(t) return (pcall(FS.SpellArt.Set, t, 100.5)) end")(lua.globals().NewTex())
    check("never_throws.a_secret_bind_does_not_throw", ok is True)
    lua.execute("FS.Config.Get = function() error('config exploded') end")
    tex = lua.globals().NewTex()
    ok = lua.eval("function(t, id) return (pcall(FS.SpellArt.Set, t, id)) end")(tex, mapped)
    check("never_throws.a_raising_setting_read_does_not_throw_out_of_Set", ok is True)
    check("never_throws.the_raising_read_really_reaches_Resolve", lua.eval("function() return (pcall(FS.SpellArt.Resolve, " + str(mapped) + ")) end")() is False)
    ok = lua.eval("function() return (pcall(FS.SpellArt.Repaint)) end")()
    check("never_throws.a_raising_setting_read_does_not_throw_out_of_Repaint", ok is True)


def check_unmapped_record() -> None:
    """The icon values the client reports that have no baked art are listed once, in the saved table next to the buff tab state line."""
    lua = world()
    sa = lua.eval("FS.SpellArt")
    check("unmapped.nothing_recorded_at_start", sa.UnmappedLine() is None and sa.UnmappedCount() == 0)
    first_file = next(iter(table_items(lua.eval("FS.SpellArtData.byFile")).keys()))
    sa.Resolve(first_file)
    sa.Resolve(100.5)
    sa.Resolve(None)
    sa.Resolve(True)
    check("unmapped.mapped_secret_nil_and_odd_values_are_not_recorded", sa.UnmappedCount() == 0, f"{sa.UnmappedLine()}")
    sa.Resolve(1234567)
    sa.Resolve(1234567)
    sa.Resolve("Interface\\Icons\\inv_misc_questionmark")
    check("unmapped.an_unmapped_value_is_recorded_once", str(sa.UnmappedLine()) == "1234567, Interface\\Icons\\inv_misc_questionmark" and sa.UnmappedCount() == 2, f"{sa.UnmappedLine()}")
    saved = lua.eval("ForeverSTUwaveDB.buffTabEngine")
    check("unmapped.it_rides_in_the_buff_tab_state_table", saved is not None and str(saved.unmappedIcons) == str(sa.UnmappedLine()), f"{saved}")
    lua.eval("FS.Config.Set")("icons.spellstyle", "stock")
    sa.Resolve(7654321)
    check("unmapped.recorded_in_the_stock_style_too", sa.UnmappedCount() == 3, f"{sa.UnmappedLine()}")
    for n in range(100, 200):
        sa.Resolve(n)
    check("unmapped.the_list_is_capped", sa.UnmappedCount() == 40, f"{sa.UnmappedCount()}")


def check_unmapped_database_guards() -> None:
    """Each guard in its own fresh world (after the cap the recorder returns before the guards), and nothing seen while the database
    could not take it is lost."""
    # read-only: not written, then written once it is writable, from the next sighting of any unmapped icon
    lua = world()
    lua.execute("FS.Config.IsReadOnly = function() return true end; FS.SpellArt.Resolve(555555555)")
    check("unmapped.a_read_only_database_is_not_written", lua.eval("ForeverSTUwaveDB.buffTabEngine") is None)
    check("unmapped.the_list_still_has_it_in_memory", str(lua.eval("FS.SpellArt.UnmappedLine()")) == "555555555")
    lua.execute("FS.Config.IsReadOnly = function() return false end; FS.SpellArt.Resolve(555555555)")
    check("unmapped.an_icon_seen_while_read_only_is_flushed_on_the_next_sighting",
          str(lua.eval("(ForeverSTUwaveDB.buffTabEngine or {}).unmappedIcons")) == "555555555")
    # not a table (the database is not ready): never throws, nothing lost
    lua = world()
    lua.execute("ForeverSTUwaveDB = nil")
    ok = lua.eval("function() return (pcall(FS.SpellArt.Resolve, 666666666)) end")()
    check("unmapped.a_missing_database_never_throws", ok is True)
    lua.execute("ForeverSTUwaveDB = 5")
    ok = lua.eval("function() return (pcall(FS.SpellArt.Resolve, 666666666)) end")()
    check("unmapped.a_database_that_is_not_a_table_never_throws", ok is True)
    lua.execute("ForeverSTUwaveDB = {}")
    lua.execute("FS.SpellArt.Resolve(666666666)")
    check("unmapped.an_icon_seen_before_the_database_was_ready_is_flushed_later",
          str(lua.eval("(ForeverSTUwaveDB.buffTabEngine or {}).unmappedIcons")) == "666666666")
    # a buffTabEngine that is not a table is left alone
    lua = world()
    lua.execute("ForeverSTUwaveDB = { buffTabEngine = 'x' }; FS.SpellArt.Resolve(777777777)")
    check("unmapped.a_state_field_that_is_not_a_table_is_left_alone", str(lua.eval("ForeverSTUwaveDB.buffTabEngine")) == "x")


def check_unmapped_guards_are_pinned() -> None:
    """The recorder's own guards, which the pcall around it would hide: metatable traps on nil, numbers and strings count any index or
    write that gets past them, and a write counter proves a flushed list is not written again."""
    lua = world()
    lua.execute("""
        function TrapRun(db, id)
            local hits = 0
            local trap = function() hits = hits + 1 end
            ForeverSTUwaveDB = db
            local smt = getmetatable("")
            debug.setmetatable(nil, { __index = trap, __newindex = trap })
            debug.setmetatable(0, { __index = trap, __newindex = trap })
            smt.__newindex = trap
            local ok = pcall(FS.SpellArt.Resolve, id)
            smt.__newindex = nil
            debug.setmetatable(0, nil)
            debug.setmetatable(nil, nil)
            ForeverSTUwaveDB = {}
            return ok, hits
        end
        function CountWrites(first, second)
            local writes, store = 0, {}
            ForeverSTUwaveDB = { buffTabEngine = setmetatable({}, {
                __index = store, __newindex = function(_, k, v) writes = writes + 1; store[k] = v end }) }
            FS.SpellArt.Resolve(first)
            local afterFirst = writes
            FS.SpellArt.Resolve(first)
            local afterRepeat = writes
            FS.SpellArt.Resolve(second)
            return afterFirst, afterRepeat, writes
        end
    """)
    ok, hits = lua.globals().TrapRun(None, 880000001)
    check("guards.a_nil_database_is_never_indexed", ok is True and hits == 0, f"ok {ok}, trap hit {hits} times")
    ok, hits = lua.globals().TrapRun(5, 880000002)
    check("guards.a_number_database_is_never_indexed_or_written", ok is True and hits == 0, f"ok {ok}, trap hit {hits} times")
    ok, hits = lua.eval("function() return TrapRun({ buffTabEngine = 'x' }, 880000003) end")()
    check("guards.a_string_state_field_is_never_written", ok is True and hits == 0, f"ok {ok}, trap hit {hits} times")
    ok, hits = lua.globals().TrapRun({}, 880000004)
    check("guards.the_traps_are_quiet_for_a_normal_database", ok is True and hits == 0, f"ok {ok}, trap hit {hits} times")
    first, again, second = lua.globals().CountWrites(990000001, 990000002)
    check("guards.a_flushed_list_is_not_written_again_until_something_new", (first, again, second) == (1, 1, 2),
          f"writes after the first {first}, after the repeat {again}, after a new one {second}")


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
          re.search(r"function Helpers\.SetSpellIcon\(tex, stock\)(?s:.*?)FS\.SpellArt(?s:.*?)pcall\(tex\.SetTexture, tex, stock\)", fh) is not None)
    bt = read("Modules/ActionBars/BuffTab.lua")
    check("sources.the_buff_tab_state_table_carries_the_unmapped_icon_list", "UnmappedLine" in bt and "unmappedIcons" in bt)
    st = read("Modules/ActionBars/StanceBar.lua")
    check("sources.StanceBar_guards_the_form_icon_against_secrets", re.search(r"IsSecret\(icon\)", st) is not None)
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
    check_set_never_throws()
    check_unmapped_record()
    check_unmapped_database_guards()
    check_unmapped_guards_are_pinned()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
