#!/usr/bin/env python3
"""Party and raid style settings (lane C1b): markers, the cleanse tray, aggro, text format, bar heights, width, bar looks and
background opacity, run through the real PartyFrames.lua, RaidFrames.lua, FrameExtras.lua and FrameStyle.lua over the party and
raid harnesses' mock client.

  * a default group frame draws as it always did (no marker, no ring, tray of three, no stored key);
  * my heal over time squares, the debuff squares (mine or all), the missing buff square, their size and corner;
  * markers and the tray hold in combat (aura reads refused) and refresh when it ends;
  * the party tray: on or off, side, icon size, most icons, cleansable and missing switches, the class buff switch;
  * aggro: pink ring and the share, amber when close, off by its switch, secret numbers never compared;
  * raid text format, bar heights (cell height), debuff border switch, background opacity, party width, looks and fill.

Theme and the frames are stubs. This is NOT the real client.

    python3 tools/groupstyle-harness.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load("partyframes_harness", "partyframes-harness.py")
R = _load("raidframes_harness", "raidframes-harness.py")

FORT = P.FORT


def close(a, b, tol=1e-4):
    return abs(a - b) <= tol


def px(t):
    return [t.color[k] for k in (1, 2, 3, 4)]


# ---------------------------------------------------------------------------------------------
# Party
# ---------------------------------------------------------------------------------------------

def _party(**kwargs):
    kwargs.setdefault("known", (FORT,))
    kwargs.setdefault("extra", """__combat=false function InCombatLockdown() return __combat end
        FS.Theme.AddRoundedFill=function(panel,color) local t=panel:CreateTexture() t:SetColorTexture(color[1],color[2],color[3],color[4]) end""")
    rt = P._buff_rt(**kwargs)
    P._event(rt, "ADDON_LOADED", "'forever-stuwave'")   # Config answers its saved values from here
    P._event(rt, "PLAYER_LOGIN")
    return rt


def _shown_markers(row):
    return [t for t in row.markers.tex.values() if t.shown]


def _renew(rt, unit="party1", caster="player"):
    P._set_buffs(rt, unit, f"{{{{name='Renew',caster='{caster}',duration=15,expiration=10}}}}")


def _check_defaults_draw_as_today():
    rt = _party()
    row = P._party1(rt)
    P._fire(row, "UNIT_AURA")
    assert P._tiles(row) == [1], P._tiles(row)           # the one missing buff, as ever
    assert not _shown_markers(row), "a marker showed with nothing to mark"
    assert not row.boxAggro.ring.shown, "an aggro ring showed with no threat"
    assert not rt.eval("FS.Config.IsStored('bars.party.alerts')"), "a default stored a key"
    assert row.alertIcons[1].w == 22 and row.alertIcons[4].shown is not True
    pts = row.alertIcons[1].points
    assert "TOPRIGHT" in pts and pts["TOPRIGHT"].x == -6, "the tray moved at the default"
    P._assert_quiet(rt)


def _check_party_hot_markers():
    rt = _party()
    row = P._party1(rt)
    _renew(rt)
    P._fire(row, "UNIT_AURA")
    shown = _shown_markers(row)
    assert len(shown) == 1, f"one Renew, one square: {len(shown)}"
    assert close(shown[0].color[1], 0.224) and close(shown[0].color[2], 1), px(shown[0])
    _renew(rt, caster="party2")
    P._fire(row, "UNIT_AURA")
    assert not _shown_markers(row), "someone else's Renew showed"
    _renew(rt)
    rt.execute("FS.Config.Set('bars.party.mkHot', false)")
    assert not _shown_markers(row), "the switch left the square up"
    rt.execute("FS.Config.Set('bars.party.mkHot', true)")
    P._fire(row, "UNIT_AURA")
    assert len(_shown_markers(row)) == 1
    rt.execute("FS.Config.Set('bars.party.mkSize', 9); FS.Config.Set('bars.party.mkPos', 'bottomleft')")
    m = _shown_markers(row)[0]
    assert m.w == 9 and m.h == 9, (m.w, m.h)
    assert "BOTTOMLEFT" in m.points and m.points["BOTTOMLEFT"].x == 3 and m.points["BOTTOMLEFT"].y == 2, m.points
    P._assert_quiet(rt)


def _check_party_markers_hold_in_combat():
    rt = _party()
    row = P._party1(rt)
    _renew(rt)
    P._fire(row, "UNIT_AURA")
    assert len(_shown_markers(row)) == 1
    rt.execute("FS.AurasReadable=function() return false end __buffs.party1={}")
    P._fire(row, "UNIT_AURA")
    assert len(_shown_markers(row)) == 1, "the square went when the read was refused"
    rt.execute("FS.Config.Set('bars.party.mkSize', 8)")
    assert len(_shown_markers(row)) == 1 and _shown_markers(row)[0].w == 8, "a style change in combat lost the square"
    rt.execute("FS.AurasReadable=function() return true end")
    P._fire(row, "PLAYER_REGEN_ENABLED")
    assert not _shown_markers(row), "the square stayed after the fight"
    P._assert_quiet(rt)


def _check_party_tray_settings():
    rt = _party()
    row = P._party1(rt)
    rt.execute("__debuffs={'Magic','Disease','Magic'}")
    P._fire(row, "UNIT_AURA")
    assert P._tiles(row) == [1, 2, 3], P._tiles(row)       # two cleansables then the missing buff
    rt.execute("FS.Config.Set('bars.party.alertMax', 1)")
    assert [i for i in range(1, 6) if row.alertIcons[i].shown] == [1], "alertMax 1 showed more than one icon"
    rt.execute("FS.Config.Set('bars.party.alertMax', 5)")
    assert len([i for i in range(1, 6) if row.alertIcons[i].shown]) == 4, "three cleansables and the missing buff"
    rt.execute("FS.Config.Set('bars.party.alertCleanse', false)")
    P._fire(row, "UNIT_AURA")
    assert P._tiles(row) == [1], "cleansable switch off still showed debuffs"
    rt.execute("FS.Config.Set('bars.party.alertCleanse', true); FS.Config.Set('bars.party.alertBuffs', false)")
    P._fire(row, "UNIT_AURA")
    assert P._tiles(row) == [1, 2, 3], f"missing buffs switch off: {P._tiles(row)}"
    rt.execute("FS.Config.Set('bars.party.alertBuffs', true); FS.Config.Set('bars.party.alertSize', 30)")
    assert row.alertIcons[1].w == 30 and row.alertIcons[1].h == 30
    rt.execute("FS.Config.Set('bars.party.alertSide', 'right')")
    pts = row.alertIcons[1].points
    assert "TOPLEFT" in pts and rt.eval(
        "FS.partyRows[2].alertIcons[1].points.TOPLEFT.rel == FS.partyRows[2].petFrame"), "the tray did not move to the right side"
    rt.execute("FS.Config.Set('bars.party.alerts', false)")
    assert not any(row.alertIcons[i].shown for i in range(1, 6)), "Alert icons off left icons up"
    P._fire(row, "UNIT_AURA")
    assert not any(row.alertIcons[i].shown for i in range(1, 6))
    # the halo still shows a cleansable debuff: the tray is the only thing the switch owns
    assert row.health.fsRail.halo.host.shown, "the dispel halo went with the tray"
    P._assert_quiet(rt)


def _check_party_class_buff_switch():
    rt = _party(known=(FORT, P.SPIRIT))
    row = P._party1(rt)
    P._fire(row, "UNIT_AURA")
    assert len(P._tiles(row)) == 2, P._tiles(row)
    yes = rt.eval("FS.PartyFrames.shared.SetBuff('spirit', false)")
    assert yes, "SetBuff refused the player's own buff"
    assert P._tiles(row) == [1], f"Divine Spirit off: {P._tiles(row)}"
    assert rt.eval("FS.PartyFrames.shared.SavedBuffValue(FS.PartyFrames.shared.PARTY_BUFFS.PRIEST[2])") is False
    assert not rt.eval("FS.PartyFrames.shared.SetBuff('motw', true)"), "a buff of another class was accepted"
    rt.execute("FS.PartyFrames.shared.SetBuff('spirit', nil)")
    assert len(P._tiles(row)) == 2, "clearing the saved value did not bring the default back"
    P._assert_quiet(rt)


def _threat_stub(rt, status="3", scaled="100"):
    rt.execute(f"""
        __status={status} __scaled={scaled}
        function UnitThreatSituation(unit) return __status end
        function UnitDetailedThreatSituation(unit, mob) return __status==3, __status, __scaled, 0, 0 end
    """)


def _check_party_aggro():
    rt = _party()
    row = P._party1(rt)
    ring = row.boxAggro.ring
    _threat_stub(rt)
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert ring.shown, "a member a mob attacks drew no ring"
    skin = ring.fsSkin
    assert close(skin.border.ring.color[1], 1) and close(skin.border.ring.color[2], 0.18), px(skin.border.ring)
    assert not row.boxAggro.pct.shown, "the share showed with its switch off"
    rt.execute("FS.Config.Set('bars.party.threatPct', true)")
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert row.boxAggro.pct.shown and row.boxAggro.pct.text == "100%", row.boxAggro.pct.text
    _threat_stub(rt, "1", "85")
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert close(skin.border.ring.color[2], 0.7137), "close to the top was not amber"
    _threat_stub(rt, "0", "10")
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert not ring.shown and not row.boxAggro.pct.shown
    _threat_stub(rt)
    rt.execute("FS.Config.Set('bars.party.threat', false)")
    assert not ring.shown, "the switch off left the ring up"
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert not ring.shown
    # a client without the call, and a secret answer, draw nothing and compare nothing
    rt.execute("FS.Config.Set('bars.party.threat', true) UnitThreatSituation=nil")
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert not ring.shown, "no threat API but a ring"
    rt.execute("""function UnitThreatSituation() return __secret end
        function UnitDetailedThreatSituation() return false, __secret, __secret end""")
    P._fire(row, "UNIT_THREAT_SITUATION_UPDATE")
    assert not ring.shown, "a secret threat drew a ring"
    P._assert_quiet(rt)


def _check_party_fill_width_looks():
    rt = _party()
    row = P._party1(rt)
    fill = row.boxFill
    base = fill.shown
    default = rt.eval("FS.FrameStyle.Default('party', 'bgAlpha')")
    rt.execute(f"FS.Config.Set('bars.party.bgAlpha', {default})")
    assert fill.shown == base, "the default opacity redrew the fill"
    rt.execute("FS.Config.Set('bars.party.bgAlpha', 20)")
    assert fill.shown != base and close(fill.shown / 1000, 0.697 * 20 / default, 1e-3), fill.shown
    old = fill.sets[base]
    assert not old[1].shown, "the default fill stayed under the new one"
    assert close(fill.sets[fill.shown][1].color[4], 0.697 * 20 / default, 1e-3), "the new fill is drawn at the new opacity"
    rt.execute(f"FS.Config.Set('bars.party.bgAlpha', {default})")
    assert old[1].shown, "the default fill did not come back"
    # bar looks reach the rails
    rt.execute("FS.Config.Set('bars.party.hpStyle', 'flat'); FS.Config.Set('bars.party.mpStyle', 'led')")
    assert row.health.fsLook == "flat" and row.power.fsLook == "led", (row.health.fsLook, row.power.fsLook)
    # width: a secure size, out of combat; the pet slot follows
    rt.execute("FS.Config.Set('bars.party.w', 240)")
    assert row.w == 240, row.w
    assert rt.eval("FS.partyRows[2].petFrame.points.TOPLEFT.rel == FS.partyRows[2]"), "the pet slot did not follow the width"
    rt.execute("__combat=true FS.Config.Set('bars.party.w', 200)")
    assert row.w == 240, "the width moved in combat"
    rt.execute("__combat=false")
    P._event(rt, "PLAYER_REGEN_ENABLED")
    assert row.w == 200, f"the width did not land after combat: {row.w}"
    P._assert_quiet(rt)


def _check_party_preview():
    rt = _party()
    rt.execute("""
        local stage = CreateFrame('Frame', nil, UIParent)
        __pv = FS.PartyFrames.NewStylePreview(stage)
        FS.Config.Set('bars.party.threatPct', true)
        __pv.Restyle()
    """)
    row = rt.eval("__pv.frame")
    assert len(_shown_markers(row)) == 2, "the preview shows two heal over time squares"
    assert row.boxAggro.ring.shown and row.boxAggro.pct.text == "100%"
    assert row.alertIcons[1].shown and row.alertIcons[2].shown, "the preview tray shows a debuff and a missing buff"
    rt.execute("FS.Config.Set('bars.party.alerts', false); __pv.Restyle()")
    assert not row.alertIcons[1].shown
    P._assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Raid
# ---------------------------------------------------------------------------------------------

def _raid(n=10, cls="PRIEST"):
    rt = R._client(player_class=cls)
    R._roster(rt, n)
    rt.execute("FS.Config.Set('bars.raid.threat', true)")   # the default
    return rt


def _marks(parts):
    return [t for t in parts.markers.tex.values() if t.shown]


def _aura(rt, unit, debuffs="", helpful=""):
    rt.execute(f"""
        __unitDebuffs['{unit}']={{{debuffs}}}
        __unitBuffs=__unitBuffs or {{}}
        __unitBuffs['{unit}']={{{helpful}}}
    """)


RAID_BUFF_MOCK = r"""
local plain = C_UnitAuras.GetAuraDataByIndex
C_UnitAuras.GetAuraDataByIndex = function(unit, index, filter)
    if filter:find('HELPFUL') then
        __auraReads = __auraReads + 1
        local b = (__unitBuffs or {})[unit] and __unitBuffs[unit][index]
        if b then return {name=b.name, icon='bufficon', applications=1, dispelName='', duration=0, expirationTime=0,
            sourceUnit=b.caster, spellId=nil} end
        return nil
    end
    return plain(unit, index, filter)
end
"""


def _raid_rt(n=10, cls="PRIEST"):
    rt = R._client(player_class=cls)
    rt.execute(RAID_BUFF_MOCK)
    R._roster(rt, n)
    return rt


def _check_raid_defaults():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    assert not _marks(parts) and not parts.aggro.ring.shown
    assert R._cell(rt, 3).w == 84 and R._cell(rt, 3).h == 30
    assert parts.fill.shown == int(0.85 * 1000 + 0.5), parts.fill.shown
    assert not parts.fmt.shown, "the always-on text showed at the default (Low only)"
    R._assert_quiet(rt)


def _check_raid_markers():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    _aura(rt, "raid3", "'Magic','Curse','Disease'", "{name='Renew',caster='player'}")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    kinds = [t.color for t in _marks(parts)]
    # Renew, then Magic and Disease (a Priest removes those two); Curse is not removable so it is left out
    assert len(kinds) == 3, f"hot + two removable debuffs: {len(kinds)}"
    rt.execute("FS.Config.Set('bars.raid.mkDebuffWho', 'all')")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert len(_marks(parts)) == 4, "All should add the Curse square"
    rt.execute("FS.Config.Set('bars.raid.mkMagic', false)")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert len(_marks(parts)) == 3
    rt.execute("FS.Config.Set('bars.raid.mkDebuff', false)")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert len(_marks(parts)) == 1, "debuff markers off should leave only the heal over time"
    rt.execute("FS.Config.Set('bars.raid.mkHot', false)")
    assert not _marks(parts), "the heal over time switch left a square up"
    R._assert_quiet(rt)


def _check_raid_missing_buff_marker():
    rt = _raid_rt()
    rt.execute("__spellIds={['Power Word: Fortitude']=1001} __knownIds={[1001]=true}")
    R._event(rt, "SPELLS_CHANGED")
    parts = R._parts(rt, 4)
    R._unit_event(rt, "UNIT_AURA", "raid4")
    assert not _marks(parts), "missing buff markers are off by default"
    rt.execute("FS.Config.Set('bars.raid.mkBuff', true)")
    R._unit_event(rt, "UNIT_AURA", "raid4")
    marks = _marks(parts)
    assert len(marks) == 1 and close(marks[0].color[4], 0.55), "one dim red square for the missing buff"
    _aura(rt, "raid4", "", "{name='Power Word: Fortitude',caster='party2'}")
    R._unit_event(rt, "UNIT_AURA", "raid4")
    assert not _marks(parts), "a buff that is up showed a marker, whoever cast it"
    R._assert_quiet(rt)


def _check_raid_markers_hold_in_combat():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    _aura(rt, "raid3", "'Magic'", "{name='Renew',caster='player'}")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert len(_marks(parts)) == 2
    rt.execute("__combat=true __auraReads=0")
    _aura(rt, "raid3", "", "")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert rt.globals().__auraReads == 0, "an aura read in combat"
    assert len(_marks(parts)) == 2, "the squares changed while reads were refused"
    rt.execute("FS.Config.Set('bars.raid.mkSize', 8); FS.Config.Set('bars.raid.mkPos', 'topleft')")
    assert all(t.w == 8 for t in _marks(parts)), "a size change was refused in combat"
    rt.execute("FS.Config.Set('bars.raid.mkHot', false)")
    assert len(_marks(parts)) == 1, "a switch turned off in combat takes its held squares out"
    rt.execute("__combat=false")
    R._event(rt, "PLAYER_REGEN_ENABLED")
    R._settle(rt)
    assert not _marks(parts), "the regen scan did not refresh the squares"
    R._assert_quiet(rt)


def _check_raid_debuff_border_switch():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    magic = P._dispel_colors()["Magic"]
    _aura(rt, "raid3", "'Magic'", "")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert R._same_rgb(R._rgb(R._ring(parts)), magic)
    rt.execute("FS.Config.Set('bars.raid.dispelEdge', false)")
    assert not R._same_rgb(R._rgb(R._ring(parts)), magic), "the edge kept the debuff colour with the switch off"
    rt.execute("FS.Config.Set('bars.raid.dispelEdge', true)")
    assert R._same_rgb(R._rgb(R._ring(parts)), magic), "the held debuff colour did not come back"
    R._assert_quiet(rt)


def _check_raid_text_format():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    R._member(rt, 3, hp=0.5)
    R._unit_event(rt, "UNIT_HEALTH", "raid3")
    assert not parts.fmt.shown and parts.pct.shown
    rt.execute("FS.Config.Set('bars.raid.raidFmt', 'percent')")
    assert parts.fmt.shown and parts.fmt.text.endswith("%"), parts.fmt.text
    rt.execute("FS.Config.Set('bars.raid.raidFmt', 'number')")
    assert parts.fmt.shown and parts.fmt.text == "500", parts.fmt.text
    rt.execute("FS.Config.Set('bars.raid.raidFmt', 'none')")
    assert not parts.fmt.shown and not parts.pct.shown
    R._member(rt, 3, state="'dead'")
    rt.execute("FS.Config.Set('bars.raid.raidFmt', 'percent')")
    R._unit_event(rt, "UNIT_HEALTH", "raid3")
    assert not parts.fmt.shown, "a down cell showed health text"
    R._assert_quiet(rt)


def _check_raid_bar_heights():
    rt = _raid_rt()
    cell = R._cell(rt, 3)
    parts = R._parts(rt, 3)
    rt.execute("FS.Config.Set('bars.raid.hpH', 10)")
    R._settle(rt)
    assert cell.h == 34, f"cell height {cell.h}"          # 20 + 10 + 2 + 2
    assert parts.health.shell.h == 10 and parts.health.h == 10, (parts.health.shell.h, parts.health.h)
    assert parts.mana.shell.points["TOPLEFT"].y == -(15 + 10 + 2), parts.mana.shell.points
    rt.execute("FS.Config.Set('bars.raid.mpH', 0)")
    R._settle(rt)
    assert cell.h == 30 and not parts.mana.shell.shown, (cell.h, parts.mana.shell.shown)
    rt.execute("FS.Config.Set('bars.raid.mpH', 4)")
    R._settle(rt)
    assert cell.h == 36 and parts.mana.shell.shown and parts.mana.h == 4, (cell.h, parts.mana.h)
    # tiles keep their ratio to the boxes
    R._roster(rt, 25)
    tile = R._cell(rt, 3)
    assert tile.h == round(36 * 40 / 30), tile.h
    R._assert_quiet(rt)


def _check_raid_fill_and_aggro():
    rt = _raid_rt()
    parts = R._parts(rt, 3)
    rt.execute("FS.Config.Set('bars.raid.bgAlpha', 40)")
    assert close(parts.fill.shown / 1000, 0.40, 1e-3), parts.fill.shown
    rt.execute("FS.Config.Set('bars.raid.bgAlpha', 85)")
    assert parts.fill.shown == 850
    _threat_stub(rt)
    R._unit_event(rt, "UNIT_THREAT_SITUATION_UPDATE", "raid3")
    assert parts.aggro.ring.shown, "raid member with a mob on them drew no ring"
    rt.execute("FS.Config.Set('bars.raid.threatPct', true); FS.Config.Set('bars.raid.threatX', -4)")
    R._unit_event(rt, "UNIT_THREAT_LIST_UPDATE", "raid3")
    assert parts.aggro.pct.shown and parts.aggro.pct.text == "100%"
    assert parts.aggro.pct.points["RIGHT"].x == -30, parts.aggro.pct.points
    rt.execute("FS.Config.Set('bars.raid.threat', false)")
    assert not parts.aggro.ring.shown and not parts.aggro.pct.shown
    R._assert_quiet(rt)


def _check_raid_preview():
    """The Style tab's raid is the real cell code on sample members: markers, the debuff edge, the ring and the share show
    through the same switches."""
    rt = _raid_rt()
    rt.execute("FS.Config.Set('bars.raid.mkBuff', true); FS.Config.Set('bars.raid.threatPct', true)")
    assert rt.eval("FS.RaidFrames.Preview.Show()") is True
    R._pv_size(rt, 10)
    marks = sum(len(_marks(R._pv_parts(rt, i))) for i in range(1, 11))
    assert marks >= 5, f"hots, debuff types and missing buffs on the sample members: {marks}"
    assert R._pv_parts(rt, 2).aggro.ring.shown and R._pv_parts(rt, 2).aggro.pct.text == "100%"
    assert not R._pv_parts(rt, 10).aggro.ring.shown and R._pv_parts(rt, 10).aggro.pct.text == "71%"
    magic = P._dispel_colors()["Magic"]
    assert R._same_rgb(R._rgb(R._ring(R._pv_parts(rt, 6))), magic), "the sample Magic debuff did not colour the edge"
    rt.execute("FS.Config.Set('bars.raid.dispelEdge', false)")
    assert not R._same_rgb(R._rgb(R._ring(R._pv_parts(rt, 6))), magic)
    rt.execute("FS.Config.Set('bars.raid.threat', false)")
    assert not R._pv_parts(rt, 2).aggro.ring.shown
    R._assert_quiet(rt)


def main() -> int:
    cases = [
        ("party: a default row draws as today", _check_defaults_draw_as_today),
        ("party: my heal over time squares, size and corner", _check_party_hot_markers),
        ("party: markers hold in combat and refresh after", _check_party_markers_hold_in_combat),
        ("party: cleanse tray switches, side, size and most icons", _check_party_tray_settings),
        ("party: the class buff switch", _check_party_class_buff_switch),
        ("party: aggro ring and share", _check_party_aggro),
        ("party: background opacity, bar looks and width", _check_party_fill_width_looks),
        ("party: the Style tab preview", _check_party_preview),
        ("raid: defaults draw as today", _check_raid_defaults),
        ("raid: markers by type, mine or all", _check_raid_markers),
        ("raid: missing buff marker", _check_raid_missing_buff_marker),
        ("raid: markers hold in combat and refresh after", _check_raid_markers_hold_in_combat),
        ("raid: the debuff border switch", _check_raid_debuff_border_switch),
        ("raid: text format", _check_raid_text_format),
        ("raid: bar heights make the cell height", _check_raid_bar_heights),
        ("raid: background opacity and aggro", _check_raid_fill_and_aggro),
        ("raid: the Style tab sample members", _check_raid_preview),
    ]
    failures = 0
    for label, fn in cases:
        try:
            fn()
            print(f"PASS  {label}")
        except Exception as exc:  # noqa: BLE001 - report every case
            failures += 1
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
    print(f"{len(cases) - failures}/{len(cases)} group style checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
