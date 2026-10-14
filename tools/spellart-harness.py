#!/usr/bin/env python3
"""Headless check of the spell icon style (Core/SpellArt.lua over Core/IconStyle.lua and Core/IconStyleData.lua).

Runs the real SpellArt.lua, IconStyle.lua and the generated data under lupa against a small mock Config and a mock
texture API. What it pins:

  * the data: every icon the spell tables name has a look (a colour family that has a shipped ramp texture, and a boost in
    0..1); the by-file, by-name, by-spell and look tables describe the same set of icons; and no texture derived from the
    game is shipped (no spellart_ files: the style draws the game's own textures at runtime);
  * coverage: every totem in ShamanTotems.lua's DEFS, every imbue and shield ShamanBuffs.lua draws, and the
    Paladin seals and auras and the Warrior stances the other class tabs draw have an entry (by spell id);
  * Look: the default `icons.spellstyle` = gradient maps the icon file id the client reports (or an Interface\\Icons path) to
    its look; an icon with no entry, a nil, a secret value and the `stock` setting all give nil, so the tile keeps its stock
    texture and is never blank;
  * Set: the tile keeps the game's own texture; a dressed texture gets three overlays over it (an ADD copy, a MOD ramp, an
    ADD lift) in the right blend order, above it and below nothing else; the tile's own tint, alpha, desaturation, tex
    coords, hide and show follow onto the overlays through post-hooks; replacing the icon with a colour releases them;
    switching the setting repaints every bound texture live (texture writes only), and a texture bound to another icon
    follows that one;
  * the class tabs draw every spell icon through FrameHelpers.SetSpellIcon (no raw SetTexture of a spell icon
    is left), IconStyle and SpellArt load before their first consumer, and the Unit Frames page offers the setting.

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
-- byFile / byName that raise when the secret value (100.5) is read as a key: removing Look's IsSecret guard fails a check.
function TrapSecretKeys()
    for _, field in ipairs({ "byFile", "byName" }) do
        local real = FS.IconStyleData.spells[field]
        FS.IconStyleData.spells[field] = setmetatable({}, { __index = function(_, k)
            if k == 100.5 then error("a secret value was used as a key") end
            return real[k]
        end })
    end
end

-- A strict mock texture: a method it does not define is a nil call (which the code under test would trip over).
local TexMT = {}
TexMT.__index = TexMT
function TexMT:SetTexture(p) self.tex = p; self.color = nil; self.writes = (self.writes or 0) + 1 end
function TexMT:SetColorTexture(r, g, b, a) self.tex = nil; self.color = { r, g, b, a } end
function TexMT:SetTexCoord(...) self.coords = { ... }; if #self.coords == 4 then local l, r, t, b = ...; self.coords = { l, t, l, b, r, t, r, b } end end
function TexMT:GetTexCoord() return unpack(self.coords or { 0, 0, 0, 1, 1, 0, 1, 1 }) end
function TexMT:SetVertexColor(r, g, b, a) self.vertex = { r, g, b, a == nil and 1 or a } end
function TexMT:GetVertexColor() local v = self.vertex or { 1, 1, 1, 1 }; return v[1], v[2], v[3], v[4] end
function TexMT:SetAlpha(a) self.alpha = a end
function TexMT:GetAlpha() return self.alpha or 1 end
function TexMT:SetDesaturated(flag) self.desat = flag and true or false end
function TexMT:IsDesaturated() return self.desat or false end
function TexMT:SetShown(flag) self.shown = flag and true or false end
function TexMT:Show() self.shown = true end
function TexMT:Hide() self.shown = false end
function TexMT:IsShown() return self.shown ~= false end
function TexMT:SetBlendMode(m) self.blend = m end
function TexMT:SetAllPoints(r) self.anchor = r end
function TexMT:GetParent() return self.parent end
function TexMT:GetDrawLayer() return self.layer, self.sub end
function TexMT:SetDrawLayer(layer, sub) self.layer, self.sub = layer, sub end

local ParentMT = {}
ParentMT.__index = ParentMT
function ParentMT:CreateTexture(_, layer, _, sub)
    local tex = setmetatable({ parent = self, layer = layer or "ARTWORK", sub = sub or 0, kids = true }, TexMT)
    self.made[#self.made + 1] = tex
    return tex
end
function NewParent() return setmetatable({ made = {} }, ParentMT) end
function NewTex(parent, layer, sub)
    parent = parent or NewParent()
    local tex = setmetatable({ parent = parent, layer = layer or "ARTWORK", sub = sub or 0 }, TexMT)
    return tex
end
function NewBroken() local t = NewTex(); t.SetTexture = function() error("boom") end; return t end
-- hooksecurefunc as the client has it: the hook runs after the original, with the same arguments.
function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
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
    for name in ("IconStyleData.lua", "IconStyle.lua", "SpellArt.lua"):
        load((ADDON / "Core" / name).read_text(encoding="utf-8"), "@" + name)
    return lua


def table_items(t) -> dict:
    return {k: v for k, v in t.items()}


def check_data(lua: LuaRuntime) -> None:
    data = lua.eval("FS.IconStyleData")
    spells = data.spells
    by_file, by_name, by_spell, look = (table_items(spells.byFile), table_items(spells.byName), table_items(spells.bySpell),
                                        table_items(spells.look))
    ramps = table_items(data.ramps)
    names = set(by_file.values())
    check("data.nine_ramp_families_each_with_a_shipped_ramp_texture",
          len(ramps) == 9 and all((MEDIA / str(r.file)).exists() for r in ramps.values()), f"{sorted(ramps)}")
    check("data.every_icon_has_a_look_in_a_known_family_with_a_boost_in_range",
          len(names) >= 30 and set(look) == names and all(str(v.fam) in {str(k) for k in ramps} and 0 <= v.boost <= 1 for v in look.values()),
          f"{len(names)} names, {len(look)} looks")
    gone = sorted(p.name for p in MEDIA.glob("spellart_*"))
    check("data.no_texture_derived_from_the_game_is_shipped", not gone, f"{gone[:3]} ({len(gone)})")
    check("data.the_tables_describe_the_same_icons",
          set(by_name) == names == set(by_name.values()) and set(by_spell.values()) == names,
          f"file {len(names)} name {len(by_name)} spell {len(set(by_spell.values()))}")
    check("data.names_are_lower_case", all(k == str(k).lower() for k in by_name), f"{[k for k in by_name if k != str(k).lower()]}")

    ids = set(int(i) for i in by_spell)
    totems = {int(m) for m in re.findall(r"id = (\d+), name = \"[^\"]+ Totem\"", (ADDON / "Modules/CombatHud/ShamanTotems.lua").read_text(encoding="utf-8"))}
    buffs = {int(m) for m in re.findall(r"base = (\d+)", (ADDON / "Modules/ActionBars/ShamanBuffs.lua").read_text(encoding="utf-8"))}
    check("coverage.every_totem_has_a_look", len(totems) >= 15 and totems <= ids, f"{len(totems)} totems, missing {sorted(totems - ids)}")
    check("coverage.every_imbue_and_shield_has_a_look", len(buffs) >= 6 and buffs <= ids, f"{sorted(buffs)} missing {sorted(buffs - ids)}")
    check("coverage.paladin_seals_auras_and_warrior_stances_have_a_look", set(OTHER_TAB_SPELLS) <= ids,
          f"missing {sorted(set(OTHER_TAB_SPELLS) - ids)}")


def check_look() -> None:
    lua = world()
    sa = lua.eval("FS.SpellArt")
    first_file, first_name = next(iter(table_items(lua.eval("FS.IconStyleData.spells.byFile")).items()))
    want = lua.eval("FS.IconStyleData.spells.look")[first_name]
    check("look.default_style_is_gradient", str(sa.Style()) == "gradient", f"{sa.Style()}")
    got = sa.Look(first_file)
    check("look.mapped_file_id_gives_its_look", got is not None and str(got.fam) == str(want.fam) and got.boost == want.boost, f"{got}")
    check("look.interface_icons_path_maps_by_name",
          sa.Look(f"Interface\\Icons\\{first_name.upper()}") is not None and sa.Look(f"interface/icons/{first_name}.blp") is not None)
    check("look.unmapped_icons_get_none", sa.Look(1234567) is None and sa.Look("Interface\\Icons\\inv_misc_questionmark") is None)
    check("look.nil_and_odd_values_get_none", sa.Look(None) is None and sa.Look(True) is None)
    lua.execute("TrapSecretKeys()")
    ok, got = lua.eval("function() return pcall(FS.SpellArt.Look, 100.5) end")()
    check("look.a_secret_value_is_never_indexed", ok is True and got is None, f"{ok} {got}")
    ok, got = lua.eval("function() return pcall(FS.SpellArt.Look, 5) end")()
    check("look.the_trap_is_live_for_plain_ids", ok is True and got is None, f"{ok} {got}")

    lua.eval("FS.Config.Set")("icons.spellstyle", "stock")
    check("look.stock_setting_gives_none", sa.Look(first_file) is None and str(sa.Style()) == "stock")
    lua.eval("FS.Config.Set")("icons.spellstyle", "nonsense")
    check("look.an_unknown_value_means_the_default", str(sa.Style()) == "gradient" and sa.Look(first_file) is not None)


def overlays(parent) -> dict:
    """The three overlay textures SpellArt made on a mock parent, by blend order: boost (ADD), mod (MOD), lift (ADD)."""
    made = [parent.made[i] for i in range(1, len(parent.made) + 1)]
    return {"boost": made[0], "mod": made[1], "lift": made[2]} if len(made) == 3 else {}


def check_set_and_repaint() -> None:
    lua = world()
    sa = lua.eval("FS.SpellArt")
    new_tex, new_parent = lua.globals().NewTex, lua.globals().NewParent
    cfg_set = lua.eval("FS.Config.Set")
    by_file = table_items(lua.eval("FS.IconStyleData.spells.byFile"))
    look = lua.eval("FS.IconStyleData.spells.look")
    (f1, n1), (f2, n2) = list(by_file.items())[:2]
    check("set.applies_is_false_until_a_tab_binds_an_icon", sa.Applies() is False)
    pa, pb, pc = new_parent(), new_parent(), new_parent()
    a, b, c = new_tex(pa, "ARTWORK", 0), new_tex(pb, "ARTWORK", 0), new_tex(pc, "ARTWORK", 0)
    sa.Set(a, f1)
    sa.Set(b, f2)
    sa.Set(c, 999999)
    check("set.the_tile_keeps_the_games_own_texture", a.tex == f1 and b.tex == f2 and c.tex == 999999, f"{a.tex} {b.tex} {c.tex}")
    check("set.applies_once_an_icon_is_bound", sa.Applies() is True)
    ov = overlays(pa)
    check("set.a_mapped_icon_gets_three_overlays_an_unmapped_one_none", len(ov) == 3 and len(table_items(pc.made)) == 0, f"{len(table_items(pa.made))} {len(table_items(pc.made))}")
    boost, mod, lift = ov["boost"], ov["mod"], ov["lift"]
    check("set.blend_order_is_ADD_copy_then_MOD_ramp_then_ADD_lift", (boost.blend, mod.blend, lift.blend) == ("ADD", "MOD", "ADD"),
          f"{boost.blend} {mod.blend} {lift.blend}")
    check("set.overlays_sit_above_the_icon_in_that_order_in_its_layer",
          all(o.layer == "ARTWORK" for o in (boost, mod, lift)) and a.sub < boost.sub < mod.sub < lift.sub <= 7, f"{a.sub} {boost.sub} {mod.sub} {lift.sub}")
    same = lua.eval("function(o, t) return o.anchor == t end")
    check("set.overlays_follow_the_icons_rectangle", all(same(o, a) for o in (boost, mod, lift)))
    check("set.the_boost_copy_is_the_same_texture", boost.tex == f1 and boost.desat is True, f"{boost.tex} {boost.desat}")
    ramp = lua.eval("FS.IconStyleData.ramps")[look[n1].fam]
    check("set.the_mod_layer_is_the_familys_ramp", str(mod.tex).endswith(str(ramp.file)), f"{mod.tex}")
    check("set.the_lift_is_the_familys_flat_colour", lift.color is not None and abs(lift.color[1] - ramp.lift[1]) < 1e-6, f"{lift.color}")
    check("set.the_base_is_drawn_desaturated_the_ramp_supplies_the_colour", a.desat is True and mod.desat is False)
    check("set.boost_strength_follows_the_data", abs(boost.vertex[1] - look[n1].boost) < 1e-6 and boost.vertex[4] == 1, f"{boost.vertex} {look[n1].boost}")
    check("set.overlays_start_shown", all(o.shown is not False for o in (boost, mod, lift)) or look[n1].boost < 0.02)

    # the tile keeps driving its texture; the overlays follow
    lua.eval("function(t) t:SetVertexColor(0.5, 0.25, 0.75, 1) end")(a)
    check("follow.a_tint_dims_the_boost_and_the_lift",
          abs(boost.vertex[1] - 0.5 * look[n1].boost) < 1e-6 and abs(boost.vertex[3] - 0.75 * look[n1].boost) < 1e-6
          and abs(lift.vertex[4] - 0.5) < 1e-6, f"{boost.vertex} {lift.vertex}")
    lua.eval("function(t) t:SetAlpha(0.4) end")(a)
    check("follow.alpha_reaches_the_boost_and_the_lift", abs(boost.vertex[4] - 0.4) < 1e-6 and abs(lift.vertex[4] - 0.4 * (0.5 + 0.25 + 0.75) / 3) < 1e-6, f"{boost.vertex} {lift.vertex}")
    lua.eval("function(t) t:SetAlpha(1); t:SetVertexColor(1, 1, 1, 1) end")(a)
    lua.eval("function(t) t:SetDesaturated(true) end")(a)
    check("follow.a_desaturated_tile_keeps_a_grey_base_and_a_grey_ramp", a.desat is True and mod.desat is True, f"{a.desat} {mod.desat}")
    lua.eval("function(t) t:SetDesaturated(false) end")(a)
    check("follow.back_to_colour_restores_the_ramp_and_keeps_the_base_grey", a.desat is True and mod.desat is False, f"{a.desat} {mod.desat}")
    lua.eval("function(t) t:Hide() end")(a)
    check("follow.hiding_the_tile_hides_the_overlays", all(o.shown is False for o in (boost, mod, lift)), f"{boost.shown} {mod.shown} {lift.shown}")
    lua.eval("function(t) t:Show() end")(a)
    check("follow.showing_it_again_shows_them", mod.shown is True and lift.shown is True)
    lua.eval("function(t) t:SetShown(false) end")(a)
    check("follow.SetShown_is_followed_too", mod.shown is False)
    lua.eval("function(t) t:SetShown(true); t:SetTexCoord(0.07, 0.93, 0.07, 0.93) end")(a)
    c8 = [round(v, 3) for v in table_items(boost.coords).values()]
    check("follow.texcoords_reach_the_boost_copy_and_not_the_ramp", c8[0] == 0.07 and c8[-1] == 0.93 and mod.coords is not None and mod.coords[1] == 0, f"{c8} {mod.coords}")
    lua.eval("function(t) t:SetColorTexture(0.04, 0.02, 0.09, 0.9) end")(a)
    check("follow.replacing_the_icon_with_a_colour_releases_the_overlays", all(o.shown is False for o in (boost, mod, lift)) and a.desat is False, f"{mod.shown} {a.desat}")
    sa.Set(a, f1)
    check("follow.a_new_icon_dresses_it_again", mod.shown is True and a.desat is True and a.tex == f1)

    cfg_set("icons.spellstyle", "stock")
    check("set.switching_to_stock_releases_every_bound_texture",
          a.tex == f1 and b.tex == f2 and c.tex == 999999 and all(o.shown is False for o in (boost, mod, lift)) and a.desat is False, f"{a.tex} {b.tex} {c.tex}")
    cfg_set("icons.spellstyle", "gradient")
    check("set.switching_back_dresses_them_again", mod.shown is True and a.desat is True and overlays(pb)["mod"].shown is True)
    check("set.no_second_set_of_overlays_is_made", len(table_items(pa.made)) == 3 and len(table_items(pb.made)) == 3)
    sa.Set(a, f2)
    cfg_set("icons.spellstyle", "stock")
    check("set.a_rebound_texture_follows_its_new_icon", a.tex == f2, f"{a.tex}")
    cfg_set("icons.spellstyle", "gradient")
    check("set.there_is_no_unused_Forget", sa.Forget is None)
    # a texture whose write raises is skipped, never fatal, and the others still repaint
    lua.execute(f"BROKEN = NewBroken(); BIND_OK = pcall(FS.SpellArt.Set, BROKEN, {f1})")
    good = new_tex(new_parent(), "ARTWORK", 0)
    sa.Set(good, f1)
    cfg_set("icons.spellstyle", "stock")
    cfg_set("icons.spellstyle", "gradient")
    check("set.a_texture_that_errors_never_stops_the_rest", lua.eval("BIND_OK") is True and good.tex == f1 and good.desat is True, f"{lua.eval('BIND_OK')} {good.tex}")
    # a texture already high in its layer is lowered so the chain fits under the engine's limit of 7
    high = new_tex(new_parent(), "OVERLAY", 7)
    sa.Set(high, f1)
    kids = overlays(high.parent)
    check("set.a_texture_at_the_top_sublevel_is_lowered_so_the_overlays_fit",
          high.sub + 3 <= 7 and kids and kids["lift"].sub <= 7 and high.sub < kids["boost"].sub, f"{high.sub} {kids and kids['lift'].sub}")
    # what the tile asked for before it had a look is remembered
    pre = new_tex(new_parent(), "ARTWORK", 0)
    lua.eval("function(t) t:SetDesaturated(true) end")(pre)
    sa.Set(pre, f1)
    check("set.a_desaturation_asked_for_before_the_first_look_survives", overlays(pre.parent)["mod"].desat is True)
    cfg_set("icons.spellstyle", "stock")
    check("set.and_comes_back_when_the_look_is_released", pre.desat is True)


def check_set_never_throws() -> None:
    """Look runs inside Set's pcall: a secret, or a setting read that raises, can never throw out of a bind or a repaint."""
    lua = world()
    sa = lua.eval("FS.SpellArt")
    # a MAPPED id, so Look reaches Style() (an unmapped one returns before it)
    mapped = next(iter(table_items(lua.eval("FS.IconStyleData.spells.byFile")).keys()))
    lua.execute("TrapSecretKeys()")
    ok = lua.eval("function(t) return (pcall(FS.SpellArt.Set, t, 100.5)) end")(lua.globals().NewTex())
    check("never_throws.a_secret_bind_does_not_throw", ok is True)
    lua.execute("FS.Config.Get = function() error('config exploded') end")
    tex = lua.globals().NewTex()
    ok = lua.eval("function(t, id) return (pcall(FS.SpellArt.Set, t, id)) end")(tex, mapped)
    check("never_throws.a_raising_setting_read_does_not_throw_out_of_Set", ok is True)
    check("never_throws.the_raising_read_really_reaches_Look", lua.eval("function() return (pcall(FS.SpellArt.Look, " + str(mapped) + ")) end")() is False)
    ok = lua.eval("function() return (pcall(FS.SpellArt.Repaint)) end")()
    check("never_throws.a_raising_setting_read_does_not_throw_out_of_Repaint", ok is True)
    # a hook that errors (a texture API quirk) never reaches the tile's own call
    lua = world()
    lua.execute("""
        local parent = NewParent()
        HOOKED = NewTex(parent, "ARTWORK", 0)
        FS.SpellArt.Set(HOOKED, next(FS.IconStyleData.spells.byFile))
        HOOKED.GetVertexColor = function() error("boom") end
    """)
    ok = lua.eval("function() return (pcall(function() HOOKED:SetVertexColor(1, 0, 0, 1) end)) end")()
    check("never_throws.a_failing_follow_never_breaks_the_tiles_own_call", ok is True)


def check_unmapped_record() -> None:
    """The icon values the client reports that have no look are listed once, in the saved table next to the buff tab state line."""
    lua = world()
    sa = lua.eval("FS.SpellArt")
    check("unmapped.nothing_recorded_at_start", sa.UnmappedLine() is None and sa.UnmappedCount() == 0)
    first_file = next(iter(table_items(lua.eval("FS.IconStyleData.spells.byFile")).keys()))
    sa.Look(first_file)
    sa.Look(100.5)
    sa.Look(None)
    sa.Look(True)
    check("unmapped.mapped_secret_nil_and_odd_values_are_not_recorded", sa.UnmappedCount() == 0, f"{sa.UnmappedLine()}")
    sa.Look(1234567)
    sa.Look(1234567)
    sa.Look("Interface\\Icons\\inv_misc_questionmark")
    check("unmapped.an_unmapped_value_is_recorded_once", str(sa.UnmappedLine()) == "1234567, Interface\\Icons\\inv_misc_questionmark" and sa.UnmappedCount() == 2, f"{sa.UnmappedLine()}")
    saved = lua.eval("ForeverSTUwaveDB.buffTabEngine")
    check("unmapped.it_rides_in_the_buff_tab_state_table", saved is not None and str(saved.unmappedIcons) == str(sa.UnmappedLine()), f"{saved}")
    lua.eval("FS.Config.Set")("icons.spellstyle", "stock")
    sa.Look(7654321)
    check("unmapped.recorded_in_the_stock_style_too", sa.UnmappedCount() == 3, f"{sa.UnmappedLine()}")
    for n in range(100, 200):
        sa.Look(n)
    check("unmapped.the_list_is_capped", sa.UnmappedCount() == 40, f"{sa.UnmappedCount()}")


def check_unmapped_database_guards() -> None:
    """Each guard in its own fresh world (after the cap the recorder returns before the guards), and nothing seen while the database
    could not take it is lost."""
    # read-only: not written, then written once it is writable, from the next sighting of any unmapped icon
    lua = world()
    lua.execute("FS.Config.IsReadOnly = function() return true end; FS.SpellArt.Look(555555555)")
    check("unmapped.a_read_only_database_is_not_written", lua.eval("ForeverSTUwaveDB.buffTabEngine") is None)
    check("unmapped.the_list_still_has_it_in_memory", str(lua.eval("FS.SpellArt.UnmappedLine()")) == "555555555")
    lua.execute("FS.Config.IsReadOnly = function() return false end; FS.SpellArt.Look(555555555)")
    check("unmapped.an_icon_seen_while_read_only_is_flushed_on_the_next_sighting",
          str(lua.eval("(ForeverSTUwaveDB.buffTabEngine or {}).unmappedIcons")) == "555555555")
    # not a table (the database is not ready): never throws, nothing lost
    lua = world()
    lua.execute("ForeverSTUwaveDB = nil")
    ok = lua.eval("function() return (pcall(FS.SpellArt.Look, 666666666)) end")()
    check("unmapped.a_missing_database_never_throws", ok is True)
    lua.execute("ForeverSTUwaveDB = 5")
    ok = lua.eval("function() return (pcall(FS.SpellArt.Look, 666666666)) end")()
    check("unmapped.a_database_that_is_not_a_table_never_throws", ok is True)
    lua.execute("ForeverSTUwaveDB = {}")
    lua.execute("FS.SpellArt.Look(666666666)")
    check("unmapped.an_icon_seen_before_the_database_was_ready_is_flushed_later",
          str(lua.eval("(ForeverSTUwaveDB.buffTabEngine or {}).unmappedIcons")) == "666666666")
    # a buffTabEngine that is not a table is left alone
    lua = world()
    lua.execute("ForeverSTUwaveDB = { buffTabEngine = 'x' }; FS.SpellArt.Look(777777777)")
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
            local ok = pcall(FS.SpellArt.Look, id)
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
            FS.SpellArt.Look(first)
            local afterFirst = writes
            FS.SpellArt.Look(first)
            local afterRepeat = writes
            FS.SpellArt.Look(second)
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
    pos = {name: toc.index(name) for name in ("Core/IconStyleData.lua", "Core/IconStyle.lua", "Core/SpellArt.lua",
                                              "Modules/ActionBars/StanceBar.lua", "Modules/ActionBars/MicroBars.lua",
                                              "Modules/ActionBars/TotemBar.lua", "Modules/ActionBars/BuffTab.lua") if name in toc}
    check("sources.toc_loads_data_then_IconStyle_then_SpellArt_before_the_first_consumer",
          len(pos) == 7 and pos["Core/IconStyleData.lua"] < pos["Core/IconStyle.lua"] < pos["Core/SpellArt.lua"]
          < min(pos["Modules/ActionBars/StanceBar.lua"], pos["Modules/ActionBars/MicroBars.lua"]), f"{pos}")
    check("sources.the_old_baked_data_file_is_gone", not (ADDON / "Core" / "SpellArtData.lua").exists())
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
    check_look()
    check_set_and_repaint()
    check_set_never_throws()
    check_unmapped_record()
    check_unmapped_database_guards()
    check_unmapped_guards_are_pinned()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall checks passed")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
