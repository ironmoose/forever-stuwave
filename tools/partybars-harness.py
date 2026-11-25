#!/usr/bin/env python3
"""Party frame heights and bar text (lane party-bars): the rows that were greyed on the Party frames Style tab, run through
the real PartyFrames.lua, FrameStyle.lua, FrameHelpers.lua and FrameExtras.lua over the party harness' mock client.

  * a default party row is unchanged: heights 9 / 9, gap 4, the 52.4 row, one CENTER text at size 14, no power text, and
    every setting put back to its default restores the exact geometry of every frame;
  * the frame height is linked to the bar heights (fixed 30 + health + gap 4 + power): the health height moves the row, the
    box, the stack of rows, the pet slot and the tray; Height moves only the health bar; power 0 hides the bar and the
    dispel halo hugs the health rail;
  * rails, box and visual change at once in combat, the secure row, the stack and the pet slot wait for PLAYER_REGEN_ENABLED;
  * health and power text: size, position and offset reseat the font string; None, Percent, Number and Num + % reach
    SetFormattedText with secret stubs that throw when compared, numbers abbreviated by the engine when it takes a secret and
    written raw when it does not;
  * the Missing text: UnitHealthMissing goes to SetFormattedText untouched, the engine gate hides it at full health, a client
    without the API keeps the percent; the Roles page Health text picks the text for a healer unless the Style tab was used;
  * the Style tab preview follows the same settings;
  * PartyFrames.lua gets no new file scope local.

Theme and the frames are stubs. This is NOT the real client.

    python3 tools/partybars-harness.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load("partyframes_harness", "partyframes-harness.py")
PARSE = _load("parse_gate", "parse-gate.py")
FORT = P.FORT

PRELUDE = """
    __combat=false function InCombatLockdown() return __combat end
    FS.Theme.AddRoundedFill=function(panel,color) local t=panel:CreateTexture() t:SetColorTexture(color[1],color[2],color[3],color[4]) end
    FS.Theme.ApplyFontGeneric=function(fs,font,size,color,flags) fs.font={font=font,size=size,flags=flags} end
    -- a secret number or string: a table the engine setters unwrap and arithmetic or comparison refuses
    function __sec(n) return setmetatable({secret=true,nativeNumber=n},getmetatable(__secret)) end
    -- the engine abbreviates a secret and hands back a secret string (as AbbreviateNumbers does on the client)
    __abbrevSecret=0 __abbrevCalls=0
    function AbbreviateNumbers(v)
        __abbrevCalls=__abbrevCalls+1
        if __abbrevThrows then error('AbbreviateNumbers refused') end
        local secret=type(v)=='table'
        local n=secret and v.nativeNumber or v
        local s=n>=1000 and ('%.1fK'):format(n/1000) or tostring(n)
        if secret then __abbrevSecret=__abbrevSecret+1 return __sec(s) end
        return s
    end
    -- the engine percent wraps in a secret when __secPct is set (a Step curve gate stays plain in this mock)
    local origPercent=UnitHealthPercent
    function UnitHealthPercent(unit,predicted,curve)
        local v=origPercent(unit,predicted,curve)
        if __secPct and curve.kind~=Enum.LuaCurveType.Step then return __sec(v) end
        return v
    end
    function UnitPowerPercent(unit,powerType,predicted,curve)
        assert(predicted==false,'UnitPowerPercent predicted flag must be false')
        if curve.kind==Enum.LuaCurveType.Step then return 1 end   -- the empty-hide gate: plain, engine side
        local v=(__powerFraction or .55)*100
        if __secPct then return __sec(v) end
        return v
    end
    function UnitIsPlayer() return true end
    CurveConstants={ScaleTo100=(function() local c=C_CurveUtil.CreateCurve() c:SetType(Enum.LuaCurveType.Linear)
        c:AddPoint(0,0) c:AddPoint(1,100) return c end)()}
    -- secret health, power and the missing amount, set per check
    function UnitHealth() return __secHealth or __health end
    function UnitHealthMax() return __secMax or __max end
    function UnitHealthMissing(unit,predicted) return __secMissing or __missing or 0 end
    function UnitPower() return __secPower or 50 end
    function UnitPowerMax() return __secPowerMax or 100 end
    -- the Roles page: the healer's pick (nil = the role in use is not healer)
    FS.Role={Value=function(key) if key=='heal.hp' then return __rolePick end end,
        Disabled=function() return false end}
    -- every frame's size, shown flag and anchors, by creation order: two snapshots are equal when nothing moved
    function __snap()
        local index={}
        for i,f in ipairs(__frames) do index[f]=i end
        local out={}
        for i,f in ipairs(__frames) do
            local pts={}
            for p,a in pairs(f.points) do
                pts[#pts+1]=p..':'..(index[a.rel] or 0)..':'..tostring(a.x)..':'..tostring(a.y)
            end
            table.sort(pts)
            out[i]=table.concat({tostring(f.w),tostring(f.h),tostring(f.shown),tostring(f.alpha),table.concat(pts,'|')},';')
        end
        return out
    end
"""


def close(a, b, tol=1e-4):
    return abs(a - b) <= tol


def _party(extra: str = "", **kwargs):
    kwargs.setdefault("known", (FORT,))
    rt = P._buff_rt(extra=PRELUDE + extra, **kwargs)
    P._event(rt, "ADDON_LOADED", "'forever-stuwave'")
    P._event(rt, "PLAYER_LOGIN")
    return rt


def _set(rt, **values):
    for suffix, value in values.items():
        lua = f"'{value}'" if isinstance(value, str) else ("nil" if value is None else str(value).lower())
        rt.execute(f"FS.Config.Set('bars.party.{suffix}', {lua})")


def _snap(rt):
    return list(rt.eval("__snap()").values())


def _rows(rt):
    return [rt.eval(f"FS.partyRows[{i}]") for i in range(1, 6)]


def _same(rt, a, b) -> bool:
    return P._same(rt, a, b)


def _leave_combat(rt):
    rt.execute("__combat=false")
    P._event(rt, "PLAYER_REGEN_ENABLED")


def _update(rt, row=None):
    """The row's health and power steps, as UNIT_HEALTH and UNIT_POWER_UPDATE run them."""
    row = row or P._party1(rt)
    P._fire(row, "UNIT_HEALTH")
    P._fire(row, "UNIT_POWER_UPDATE")


# Row geometry the party draws today (PartyFrames.lua): the row from FS.Layout.party, BOX_TOP, the pad and the rail gap.
ROW = (294 - 2 * 8 - 4 * 4) / 5
BOX_TOP = 17
PANEL_PAD = 8
GAP_Y = 4
RAIL_GAP = 4


def _row_y(index: int, height: float) -> float:
    return -PANEL_PAD - (index - 1) * (height + GAP_Y)


# ---------------------------------------------------------------------------------------------
# Defaults and heights
# ---------------------------------------------------------------------------------------------

def _check_defaults_draw_as_today():
    rt = _party()
    row = P._party1(rt)
    assert close(row.h, ROW), (row.h, ROW)
    assert close(row.visual.h, ROW) and close(row.box.h, ROW - BOX_TOP), (row.visual.h, row.box.h)
    assert row.health.shell.h == 9 and row.power.shell.h == 9 and row.health.h == 9
    assert row.power.shell.points.TOPLEFT.y == -RAIL_GAP, "the rail gap moved"
    assert row.power.shell.shown
    _update(rt)
    text = row.health.text
    assert text.shown and text.text == "100%", text.text
    assert text.font.size == 14 and text.font.flags == "OUTLINE", text.font
    assert text.points.CENTER and text.points.CENTER.x == 0 and not text.points.LEFT
    assert not row.power.text.shown, "the power text showed with its format None"
    assert row.power.text.font.size == 14
    for i, member in enumerate(_rows(rt), start=1):
        assert close(member.points.TOPLEFT.y, _row_y(i, ROW)), (i, member.points.TOPLEFT.y)
    assert not rt.eval("FS.Config.IsStored('bars.party.hpH')")
    P._assert_quiet(rt)


def _check_defaults_round_trip():
    """Every setting of this lane moved and put back leaves every frame as it was built."""
    rt = _party()
    before = _snap(rt)
    _set(rt, hpH=14, mpH=3, hpTs=18, hpTa="right", hpTx=7, mpFmt="number", mpTs=9, mpTa="left", mpTx=-3, hpFmt="number")
    assert _snap(rt) != before, "the settings changed nothing"
    for suffix in ("hpH", "mpH", "hpTs", "hpTa", "hpTx", "mpFmt", "mpTs", "mpTa", "mpTx", "hpFmt"):
        _set(rt, **{suffix: None})
    assert _snap(rt) == before, "a default party row did not come back to the built geometry"
    row = P._party1(rt)
    assert row.health.text.points.CENTER and not row.health.text.points.RIGHT
    P._assert_quiet(rt)


def _check_height_follows_the_health_bar():
    rt = _party()
    row, row3, pet = P._party1(rt), _rows(rt)[2], P._party1(rt).petFrame
    _set(rt, hpH=12)
    h = ROW + 3
    assert close(row.h, h) and close(row.visual.h, h), (row.h, row.visual.h)
    assert close(row.box.h, h - BOX_TOP) and close(row.box.edge.h, h - BOX_TOP) and close(row.boxRed.h, h - BOX_TOP)
    assert row.health.shell.h == 12 and row.health.h == 12 and row.health.fsRail.trackLeft.h == 12
    assert row.health.healOverlay.glow.h == 12, "the heal glow kept the old rail height"
    assert row.power.shell.h == 9 and row.power.shell.points.TOPLEFT.y == -RAIL_GAP, "the power rail moved"
    # the rail pair keeps the top offset it has today (the room above and below it is what the 30 fixed height is made of)
    assert close(row.health.shell.points.TOPLEFT.y, -(1 + (ROW - 16 - 1 - 22) / 2)), row.health.shell.points.TOPLEFT.y
    assert close(row3.points.TOPLEFT.y, _row_y(3, h)), (row3.points.TOPLEFT.y, _row_y(3, h))
    assert close(pet.h, h) and close(pet.points.TOPRIGHT.y, _row_y(2, h)), (pet.h, pet.points.TOPRIGHT.y)
    size = row.alertIcons[1].h
    assert close(row.alertIcons[1].points.TOPRIGHT.y, _row_y(2, h) - (h - size) / 2), row.alertIcons[1].points.TOPRIGHT.y
    # the power bar's height is its own: the row grows by it and nothing else moves
    _set(rt, mpH=14)
    h2 = ROW + 3 + 5
    assert close(row.h, h2) and row.power.shell.h == 14 and row.power.fsRail.trackRight.h == 14
    assert close(row.box.h, h2 - BOX_TOP)
    P._assert_quiet(rt)


def _check_frame_height_moves_only_the_health_bar():
    rt = _party()
    row = P._party1(rt)
    assert rt.eval("FS.FrameStyle.FrameHeight('party')") == 52
    rt.execute("FS.FrameStyle.SetFrameHeight('party', 60)")
    assert rt.eval("FS.Config.Get('bars.party.hpH')") == 17 and rt.eval("FS.Config.Get('bars.party.mpH')") == 9
    assert close(row.h, ROW + 8) and row.health.shell.h == 17 and row.power.shell.h == 9, (row.h, row.health.shell.h)
    rt.execute("FS.FrameStyle.SetFrameHeight('party', 52)")
    assert not rt.eval("FS.Config.IsStored('bars.party.hpH')"), "back at 52 should be the default"
    assert close(row.h, ROW)
    P._assert_quiet(rt)


def _check_power_zero_hides_the_bar_and_the_halo_hugs_the_health_rail():
    rt = _party()
    row = P._party1(rt)
    _set(rt, mpH=0)
    assert not row.power.shell.shown, "power height 0 left the bar up"
    h = ROW - (RAIL_GAP + 9)
    assert close(row.h, h) and close(row.box.h, h - BOX_TOP), (row.h, row.box.h)
    hp_bottom = row.health.shell.GetBounds(row.health.shell).bottom
    pw_bottom = row.power.shell.GetBounds(row.power.shell).bottom
    assert close(hp_bottom, pw_bottom), f"the halo's bottom anchor should sit on the health rail: {hp_bottom} {pw_bottom}"
    # a power read must not bring a hidden bar back
    _update(rt)
    assert not row.power.shell.shown, "a power update showed the bar the setting hides"
    _set(rt, mpH=None)
    _update(rt)
    assert row.power.shell.shown and row.power.shell.h == 9
    assert close(row.power.shell.points.TOPLEFT.y, -RAIL_GAP)
    P._assert_quiet(rt)


def _check_heights_in_combat():
    rt = _party()
    row, row3, pet = P._party1(rt), _rows(rt)[2], P._party1(rt).petFrame
    rt.execute("__combat=true")
    _set(rt, hpH=14)
    h = ROW + 5
    assert row.health.shell.h == 14 and close(row.visual.h, h) and close(row.box.h, h - BOX_TOP), "the drawing waited"
    assert close(row.h, ROW) and close(pet.h, ROW), "the secure row and the pet slot moved in combat"
    assert close(row3.points.TOPLEFT.y, _row_y(3, ROW)), "the stack moved in combat"
    _leave_combat(rt)
    assert close(row.h, h) and close(pet.h, h) and close(row3.points.TOPLEFT.y, _row_y(3, h)), (row.h, row3.points.TOPLEFT.y)
    P._assert_quiet(rt)


def _check_box_dashes_follow_the_height():
    rt = _party()
    row = P._party1(rt)
    default = row.box.dashes
    rt.execute("__state='dead'")
    _update(rt)
    assert row.box.dashHost.shown
    n = len(list(default.values()))
    assert all(d.shown for d in default.values())
    _set(rt, hpH=15)
    assert not _same(rt, row.box.dashes, default), "the dashes of the old height stayed"
    assert close(row.box.dashH, ROW + 6 - BOX_TOP), row.box.dashH
    assert all(not d.shown for d in default.values()), "the old dashes stayed up beside the new ones"
    assert all(d.shown for d in row.box.dashes.values())
    _set(rt, hpH=None)
    assert _same(rt, row.box.dashes, default) and close(row.box.dashH, ROW - BOX_TOP)
    assert len(list(row.box.dashes.values())) == n
    assert all(d.shown for d in default.values())
    rt.execute("__state='live'")
    P._assert_quiet(rt)


def _check_pet_placeholder_dashes_follow_the_height():
    rt = _party()
    pet = P._party1(rt).petFrame
    default = pet.placeholderDashes
    _set(rt, hpH=15)
    assert close(pet.h, ROW + 6)
    assert not _same(rt, pet.placeholderDashes, default) and close(pet.placeholderH, ROW + 6 - BOX_TOP), "the placeholder kept the old dashes"
    assert all(not d.shown for d in default.values()) and all(d.shown for d in pet.placeholderDashes.values())
    _set(rt, hpH=None)
    assert close(pet.h, ROW) and _same(rt, pet.placeholderDashes, default) and all(d.shown for d in default.values())
    P._assert_quiet(rt)


def _check_tray_follows_the_row_height_after_combat():
    rt = _party()
    row = P._party1(rt)
    icon = row.alertIcons[1]
    before = icon.points.TOPRIGHT.y
    rt.execute("__combat=true")
    _set(rt, hpH=15)
    assert close(icon.points.TOPRIGHT.y, before), "the tray moved before the secure row did"
    _leave_combat(rt)
    h = ROW + 6
    assert close(icon.points.TOPRIGHT.y, _row_y(2, h) - (h - icon.h) / 2), icon.points.TOPRIGHT.y
    P._assert_quiet(rt)


def _check_hand_edited_heights_are_held_to_the_range():
    rt = _party()
    row = P._party1(rt)
    rt.execute("FS.Config.Set('bars.party.hpH', 999) FS.Config.Set('bars.party.mpH', -5)")
    assert row.health.shell.h == 60 and not row.power.shell.shown and close(row.h, ROW + 51 - 13), (row.health.shell.h, row.h)
    P._assert_quiet(rt)


def _check_width_and_height_together():
    rt = _party()
    row = P._party1(rt)
    _set(rt, w=240, hpH=12)
    assert row.w == 240 and close(row.h, ROW + 3)
    assert close(row.petFrame.points.TOPLEFT.y, 0) and _same(rt, row.petFrame.points.TOPLEFT.rel, row)
    _set(rt, w=None, hpH=None)
    assert close(row.h, ROW) and row.petFrame.points.TOPRIGHT
    P._assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Text rows
# ---------------------------------------------------------------------------------------------

def _check_text_size_position_offset():
    rt = _party()
    row = P._party1(rt)
    _update(rt)
    text = row.health.text
    _set(rt, hpTs=18)
    assert text.font.size == 18 and text.font.flags == "OUTLINE", text.font
    _set(rt, hpTa="left", hpTx=5)
    assert text.points.LEFT and text.points.LEFT.x == 9 and not text.points.CENTER, text.points
    _set(rt, hpTa="right", hpTx=-6)
    assert text.points.RIGHT and text.points.RIGHT.x == -10 and not text.points.LEFT
    _set(rt, hpTa="center", hpTx=3)
    assert text.points.CENTER.x == 3 and not text.points.RIGHT
    _set(rt, mpFmt="percent", mpTs=9, mpTa="right", mpTx=2)
    power = row.power.text
    assert power.font.size == 9 and power.points.RIGHT.x == -2, (power.font, power.points)
    assert _same(rt, power.points.RIGHT.rel, row.power), "the power text sits on the power rail"
    P._assert_quiet(rt)


def _check_health_text_formats_with_secret_stubs():
    rt = _party("""__secHealth=__sec(3120) __secMax=__sec(4000) __secPct=true __fraction=.78""")
    row = P._party1(rt)
    text = row.health.text
    _update(rt)
    assert text.text == "78%", text.text
    _set(rt, hpFmt="number")
    assert text.text == "3.1K / 4.0K" and text.shown, text.text
    assert rt.eval("__abbrevSecret") >= 2, "the secret numbers did not go through the engine's abbreviation"
    _set(rt, hpFmt="both")
    assert text.text == "3.1K / 4.0K  78%", text.text
    _set(rt, hpFmt="percent")
    assert text.text == "78%"
    _set(rt, hpFmt="none")
    assert not text.shown, "None left the text up"
    _set(rt, hpFmt="number")
    assert text.shown
    P._assert_quiet(rt)


def _check_number_text_without_the_engine_abbreviation():
    rt = _party("""__secHealth=__sec(3120) __secMax=__sec(4000) __secPct=true __fraction=.78""")
    row = P._party1(rt)
    text = row.health.text
    rt.execute("AbbreviateNumbers=nil")
    _set(rt, hpFmt="number")
    assert text.text == "3120 / 4000", text.text
    # a refusal latches: the raw numbers show and the engine is not asked again
    rt.execute("AbbreviateNumbers=nil")
    rt2 = _party("""__secHealth=__sec(3120) __secMax=__sec(4000) __secPct=true __fraction=.78 __abbrevThrows=true""")
    row2 = P._party1(rt2)
    _set(rt2, hpFmt="number")
    assert row2.health.text.text == "3120 / 4000", row2.health.text.text
    calls = rt2.eval("__abbrevCalls")
    _update(rt2)
    _update(rt2)
    assert rt2.eval("__abbrevCalls") == calls, "a refused AbbreviateNumbers was asked again"
    assert row2.health.text.text == "3120 / 4000"
    P._assert_quiet(rt)


def _check_power_text_formats():
    rt = _party("""__secPower=__sec(1100) __secPowerMax=__sec(2000) __secPct=true __powerFraction=.55""")
    row = P._party1(rt)
    text = row.power.text
    _update(rt)
    assert not text.shown
    _set(rt, mpFmt="percent")
    assert text.shown and text.text == "55%", text.text
    _set(rt, mpFmt="number")
    assert text.text == "1.1K / 2.0K", text.text
    _set(rt, mpFmt="both")
    assert text.text == "1.1K / 2.0K  55%", text.text
    _set(rt, mpFmt="none")
    assert not text.shown
    # a downed member has no power reading to show
    _set(rt, mpFmt="percent")
    rt.execute("__state='dead'")
    _update(rt)
    assert not text.shown, "a dead member's power text stayed"
    rt.execute("__state='live'")
    _update(rt)
    assert text.shown
    P._assert_quiet(rt)


def _check_a_down_row_shows_its_label_at_full_strength():
    rt = _party("""__secMissing=__sec(880) __fraction=1 __rolePick='missing'""")
    row = P._party1(rt)
    text = row.health.text
    _update(rt)
    assert text.alpha == 0, "full health: the gate hides the missing amount"
    rt.execute("__state='dead'")
    _update(rt)
    assert text.text == "Dead" and text.alpha == 1 and text.shown, (text.text, text.alpha)
    rt.execute("__state='live'")
    _update(rt)
    assert text.alpha == 0, "back alive at full health: hidden again"
    P._assert_quiet(rt)


def _check_without_a_role_api_or_percent_read():
    rt = _party("""__fraction=.78""")
    rt.execute("FS.Role=nil")
    _update(rt)
    assert P._party1(rt).health.text.text == "78%"
    # a power percent with no UnitPowerPercent: the number shows
    rt = _party("""__secPower=__sec(1100) __secPowerMax=__sec(2000) UnitPowerPercent=nil""")
    _set(rt, mpFmt="percent")
    assert P._party1(rt).power.text.text == "1.1K / 2.0K", P._party1(rt).power.text.text
    P._assert_quiet(rt)


def _check_dead_state_shows_its_label_whatever_the_format():
    rt = _party()
    row = P._party1(rt)
    _set(rt, hpFmt="none")
    rt.execute("__state='dead'")
    _update(rt)
    assert row.health.text.text == "Dead" and row.health.text.shown
    rt.execute("__state='live'")
    _update(rt)
    assert not row.health.text.shown, "the live text came back though the format is None"
    _set(rt, hpFmt=None)
    assert row.health.text.shown and row.health.text.text == "100%"
    P._assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# The Missing text and the Roles page
# ---------------------------------------------------------------------------------------------

def _check_missing_text_goes_to_the_engine_untouched():
    rt = _party("""__secMissing=__sec(880) __fraction=.78 __rolePick='missing'""")
    row = P._party1(rt)
    text = row.health.text
    _update(rt)
    assert text.text == "-880" and text.shown, text.text
    assert text.alpha == 1, "a member who is down shows the missing amount at full strength"
    rt.execute("__secMissing=__sec(12345)")
    _update(rt)
    assert text.text == "-12.3K", text.text
    # the engine gate: at full health the text is hidden by alpha, without the value being read
    rt.execute("__fraction=1 __secMissing=__sec(0)")
    _update(rt)
    assert text.alpha == 0, "full health still showed a missing amount"
    rt.execute("__fraction=.5")
    _update(rt)
    assert text.alpha == 1
    # another format puts the alpha back
    _set(rt, hpFmt="number")
    assert text.alpha == 1
    P._assert_quiet(rt)


def _check_missing_text_fallbacks():
    # no UnitHealthMissing: the percent stays
    rt = _party("""__fraction=.78 __rolePick='missing'""")
    rt.execute("UnitHealthMissing=nil")
    _update(rt)
    assert P._party1(rt).health.text.text == "78%", P._party1(rt).health.text.text
    # a refusal falls back too, without throwing
    rt = _party("""__fraction=.78 __rolePick='missing'""")
    rt.execute("UnitHealthMissing=function() error('restricted') end")
    _update(rt)
    assert P._party1(rt).health.text.text == "78%"
    # no abbreviation: the raw amount
    rt = _party("""__secMissing=__sec(880) __fraction=.78 __rolePick='missing'""")
    rt.execute("AbbreviateNumbers=nil")
    _update(rt)
    assert P._party1(rt).health.text.text == "-880"
    # no percent read at all: a plain amount decides (zero hides, 300 shows)
    rt = _party("""__missing=0 __fraction=1 __rolePick='missing'""")
    rt.execute("UnitHealthPercent=nil")
    _update(rt)
    text = P._party1(rt).health.text
    assert not text.shown, "a plain zero missing showed text"
    rt.execute("__missing=300 __fraction=.9")
    _update(rt)
    assert text.shown and text.text == "-300", text.text
    # a secret amount with no gate to hide it at full health shows the percent instead of a -0
    rt = _party("""__secMissing=__sec(0) __fraction=1 __rolePick='missing'""")
    rt.execute("UnitHealthPercent=nil")
    rt.execute("UnitHealthPercent=function() error('gone') end")
    _update(rt)
    assert "-" not in (P._party1(rt).health.text.text or ""), P._party1(rt).health.text.text


def _check_roles_page_picks_the_healer_text():
    rt = _party("""__secHealth=__sec(3120) __secMax=__sec(4000) __secPct=true __secMissing=__sec(880) __fraction=.78""")
    row = P._party1(rt)
    text = row.health.text
    _update(rt)
    assert text.text == "78%", "not a healer: the party text is the percent"
    rt.execute("__rolePick='missing'")
    _update(rt)
    assert text.text == "-880", text.text
    rt.execute("__rolePick='percent'")
    _update(rt)
    assert text.text == "78%"
    rt.execute("__rolePick='none'")
    _update(rt)
    assert not text.shown
    # the party Style tab's own Text, once set, wins over the Roles page
    rt.execute("__rolePick='missing'")
    _set(rt, hpFmt="number")
    assert text.text == "3.1K / 4.0K" and text.shown, text.text
    _set(rt, hpFmt=None)
    _update(rt)
    assert text.text == "-880"
    rt.execute("__rolePick=nil")
    _update(rt)
    assert text.text == "78%"
    P._assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# The preview and the file
# ---------------------------------------------------------------------------------------------

def _check_preview_follows_the_settings():
    rt = _party()
    rt.execute("""
        local stage = CreateFrame('Frame', nil, UIParent)
        __pv = FS.PartyFrames.NewStylePreview(stage)
        __pv.Restyle()
    """)
    row = rt.eval("__pv.frame")
    assert close(row.h, ROW) and row.health.shell.h == 9 and row.power.shell.h == 9
    assert row.health.text.shown and row.health.text.text == "78%", row.health.text.text
    assert not row.power.text.shown
    _set(rt, hpH=15, mpH=0, hpFmt="both", hpTs=16, mpFmt="percent", hpTa="left")
    rt.execute("__pv.Restyle()")
    assert close(row.h, ROW + 6 - 13), (row.h, ROW + 6 - 13)
    assert row.health.shell.h == 15 and not row.power.shell.shown
    assert row.health.text.text == "3.1K / 4.0K  78%", row.health.text.text
    assert row.health.text.font.size == 16 and row.health.text.points.LEFT
    _set(rt, mpH=9, mpFmt="percent")
    rt.execute("__pv.Restyle()")
    assert row.power.shell.shown and row.power.text.shown and row.power.text.text == "55%", row.power.text.text
    rt.execute("__rolePick='missing'")
    _set(rt, hpFmt=None)
    rt.execute("__pv.Restyle()")
    assert row.health.text.text == "-880", row.health.text.text
    P._assert_quiet(rt)


def _check_no_new_file_scope_local():
    src = (ADDON / "Modules/UnitFrames/PartyFrames.lua").read_text(encoding="utf-8")
    count = PARSE.count_file_scope_locals(src)
    assert count <= 187, f"PartyFrames.lua has {count} file scope locals (it had 187, the gate fails at 190)"
    for name in ("PartyFrames.lua", "ConfigPageBars.lua", "ConfigPageRoles.lua"):
        path = next(ADDON.rglob(name))
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text, f"{name} has an em or en dash"


def main() -> int:
    cases = [
        ("a default row draws as today", _check_defaults_draw_as_today),
        ("every setting put back restores the built geometry", _check_defaults_round_trip),
        ("the health height moves the row, box, stack, pet slot and tray", _check_height_follows_the_health_bar),
        ("Height moves only the health bar", _check_frame_height_moves_only_the_health_bar),
        ("power 0 hides the bar and the halo hugs the health rail", _check_power_zero_hides_the_bar_and_the_halo_hugs_the_health_rail),
        ("heights: the drawing at once, the secure row after combat", _check_heights_in_combat),
        ("the box dashes follow the height", _check_box_dashes_follow_the_height),
        ("the pet placeholder dashes follow the height", _check_pet_placeholder_dashes_follow_the_height),
        ("the tray follows the row height after combat", _check_tray_follows_the_row_height_after_combat),
        ("hand edited heights are held to the range", _check_hand_edited_heights_are_held_to_the_range),
        ("width and height together", _check_width_and_height_together),
        ("text size, position and offset", _check_text_size_position_offset),
        ("health text formats with secret stubs", _check_health_text_formats_with_secret_stubs),
        ("number text without the engine abbreviation", _check_number_text_without_the_engine_abbreviation),
        ("power text formats", _check_power_text_formats),
        ("the dead label shows whatever the format", _check_dead_state_shows_its_label_whatever_the_format),
        ("a down row shows its label at full strength", _check_a_down_row_shows_its_label_at_full_strength),
        ("no role API and no percent read", _check_without_a_role_api_or_percent_read),
        ("Missing goes to the engine untouched", _check_missing_text_goes_to_the_engine_untouched),
        ("Missing falls back to the percent", _check_missing_text_fallbacks),
        ("the Roles page picks the healer's text", _check_roles_page_picks_the_healer_text),
        ("the Style tab preview follows the settings", _check_preview_follows_the_settings),
        ("no new file scope local, no dashes", _check_no_new_file_scope_local),
    ]
    failures = 0
    for label, fn in cases:
        try:
            fn()
            print(f"PASS  {label}")
        except Exception as exc:  # noqa: BLE001 - report every case
            failures += 1
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
    print(f"{len(cases) - failures}/{len(cases)} party bars checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
