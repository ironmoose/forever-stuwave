#!/usr/bin/env python3
"""Runs the real WarriorPowerUps.lua (with the real WarriorWindows.lua and the generated art manifest) headless against a mock client.

The Warrior power-up alerts (design mockup "Gunsight Warrior: proc alerts v2", 2026-11-17: the Overpower double axe and rune
circle, the Revenge Viking skull on a shield, the Victory Rush crossed flaming axes) are baked frame lists replayed by the module.
These checks pin:

  * flows per spell: a window opens and the alert plays enter, then held; the last 1.5 s play amber; a cast plays the cast exit;
    a window that runs out plays the expiry exit; the drain bar's fill follows the real remaining time;
  * the least time left wins when two windows are open; Victory Rush held back by the health gate shows nothing, the module polls
    until it is shown;
  * the master and the per spell switches hide and block; Gunsight.IsActive() false hides everything; other classes build nothing;
  * the frame is registered with FS.Layout and /fsedit (a handle, a static preview while the editor is on);
  * the OnUpdate runs only while an alert plays (or a window waits), nothing allocates per tick, the texture stack keeps the baked
    back to front order (child frame, layer, sublevel);
  * REPLAY: every sampled frame of every sequence, played through the real module, composites to the same pixels as the baked
    display lists (the drain bar rows aside, which the module draws from the real remaining time);
  * the generator is deterministic: it rewrites the committed textures and manifest byte for byte.

    python3 tools/warriorpowerups-harness.py [--png debug/warrior-powerups]

`--png PREFIX` also writes PREFIX-<spell>.png: the mockup's own strip frames of each spell (entrance, held, amber, cast and expiry;
2 px per sprite px, over the dark ground), for a look next to the mockup. Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ROOT = Path(__file__).resolve().parent.parent
CH = ROOT / "forever-stuwave/Modules/CombatHud"
WINDOWS = (CH / "WarriorWindows.lua").read_text(encoding="utf-8")
ART = (CH / "WarriorPowerUpArt.lua").read_text(encoding="utf-8")
MODULE = (CH / "WarriorPowerUps.lua").read_text(encoding="utf-8")
TOC = (ROOT / "forever-stuwave/forever-stuwave.toc").read_text(encoding="utf-8")
LAYOUT = (ROOT / "forever-stuwave/Core/Layout.lua").read_text(encoding="utf-8")
LAYOUTEDIT = (ROOT / "forever-stuwave/Core/LayoutEdit.lua").read_text(encoding="utf-8")
CONFIGWINDOW = (ROOT / "forever-stuwave/Modules/Config/ConfigPageClassModules.lua").read_text(encoding="utf-8")
MEDIA = ROOT / "forever-stuwave/Media/Textures"
BG = (10, 4, 22)
GW, GH, SPX = 150, 96, 2.5

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind) return setmetatable({ kind = kind, shown = true, level = 0 }, Obj) end
-- no table is made by any mock call (the allocation check counts what the module itself allocates)
function Obj:SetPoint(p, rel, rp, x, y) self.np = (self.np or 0) + 1; self.px, self.py, self.prel, self.has = x or 0, y or 0, rel, true end
function Obj:ClearAllPoints() self.has = false end
function Obj:SetAllPoints(rel) self.allpoints = rel end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetFrameLevel(n) self.level = n end
function Obj:GetFrameLevel() return self.level end
function Obj:SetFrameStrata(s) self.strata = s end
function Obj:EnableMouse(b) self.mouse = b end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts and self.scripts[n] end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:UnregisterAllEvents() self.events = {} end
function Obj:SetTexture(p, ...) self.tex = p; self.filter = select(3, ...) end
function Obj:SetTexCoord(l, r, t, b) self.l, self.r, self.t, self.b = l, r, t, b end
function Obj:CreateTexture(name, layer, template, sub)
    local t = New("Texture"); t.layer, t.sub, t.parent = layer, sub or 0, self; t.shown = true
    __textures[#__textures + 1] = t
    return t
end
__textures, __frames = {}, {}
UIParent = New("Frame")
function CreateFrame(kind, name, parent)
    local f = New("Frame"); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    return f
end
__now = 1000
function GetTime() return __now end
__class = "WARRIOR"
function UnitClass() return "Warrior", __class, 1 end
__hp, __hpmax = 100, 100
function UnitHealth() return __hp end
function UnitHealthMax() return __hpmax end
__names = {}
for _, id in ipairs({ 11585, 11584, 7887, 7384 }) do __names[id] = "Overpower" end
for _, id in ipairs({ 30357, 25269, 25288, 11601, 11600, 7379, 6574, 6572 }) do __names[id] = "Revenge" end
__names[34428] = "Victory Rush"
C_Spell = { GetSpellName = function(id) return __names[id] end, IsSpellUsable = function() return nil, false end }
function IsPlayerSpell() return true end
local Deny = function() error("a secret value was used") end
SECRET = setmetatable({}, { __lt = Deny, __le = Deny, __add = Deny, __sub = Deny, __mul = Deny, __div = Deny, __concat = Deny,
    __len = Deny, __index = Deny, __call = Deny })
__cfg, __cfgfn = {}, {}
__gun = true
__gunfn, __ready = {}, nil
__edit, __editfn = false, {}
__applied, __rescale = {}, {}
FS = {
    IsSecret = function(v) return v == SECRET end,
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
    FrameHelpers = {
        IsKnownSpellId = function() return true end,
        RegisterEvent = function(f, e) f.events = f.events or {}; f.events[e] = true end,
        RegisterEvents = function(f, list) f.events = f.events or {}; for _, e in ipairs(list) do f.events[e] = true end end,
    },
    Config = {
        defaults = {},
        RegisterDefault = function(k, v) FS.Config.defaults[k] = v end,
        Get = function(k) local v = __cfg[k]; if v == nil then return FS.Config.defaults[k] end return v end,
        Set = function(k, v) __cfg[k] = v; for _, fn in ipairs(__cfgfn[k] or {}) do fn() end end,
        OnChange = function(k, fn) __cfgfn[k] = __cfgfn[k] or {}; table.insert(__cfgfn[k], fn) end,
    },
    Gunsight = {
        IsActive = function() return __gun end,
        OnActiveChanged = function(fn) __gunfn[#__gunfn + 1] = fn end,
        OnReady = function(fn) __ready = fn end,
    },
    Layout = {
        Scale = function() return __scale or 1 end,
        Apply = function(frame, id) __applied[#__applied + 1] = id; frame.layoutId = id end,
        OnRescale = function(fn) __rescale[#__rescale + 1] = fn end,
    },
    LayoutEdit = {
        IsEditing = function() return __edit end,
        OnEditChanged = function(fn) __editfn[#__editfn + 1] = fn end,
    },
}
function SetGun(v) __gun = v; for _, fn in ipairs(__gunfn) do fn(v) end end
function SetEdit(v) __edit = v; for _, fn in ipairs(__editfn) do fn(v) end end
assert(loadstring(WINDOWS_SRC, "@WarriorWindows.lua"))("forever-stuwave", FS)
assert(loadstring(ART_SRC, "@WarriorPowerUpArt.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@WarriorPowerUps.lua"))("forever-stuwave", FS)
Win, PU, Art = FS.WarriorWindows, FS.WarriorPowerUps, FS.WarriorPowerUpArt
BOOT = __frames[#__frames]
function Boot() BOOT.scripts.OnEvent(BOOT, "PLAYER_LOGIN"); return PU.Init() end
function Driver() return PU._driver() end
function Driving() local d = Driver(); return d ~= nil and d.scripts ~= nil and d.scripts.OnUpdate ~= nil end
function Tick(dt) __now = __now + dt; local d = Driver(); local fn = d and d.scripts and d.scripts.OnUpdate; if fn then fn(d, dt) end end
function TickFor(sec) local n = math.floor(sec * 30 + 0.5) for _ = 1, n do Tick(1 / 30) end end
function Glow(key, shown) Win._OnGlow(({ overpower = 11585, revenge = 30357, victoryrush = 34428 })[key], shown) end
function CastKey(key) Win._OnCast(({ overpower = 11585, revenge = 30357, victoryrush = 34428 })[key]) end
function State() local k, s, i, p = PU._state(); return k, s, i, p end
function Root() return PU._root() end
function RootShown() local r = Root(); return r ~= nil and r.shown == true end
function VisibleCount() local n = 0 for _, t in ipairs(__textures) do if t.shown then n = n + 1 end end return n end
function Cfg(k, v) FS.Config.Set(k, v) end
function Run(maxSec, pred) for _ = 1, math.floor(maxSec * 30) do Tick(1 / 30); if pred() then return true end end return false end
LAYER_IDX = { BACKGROUND = 1, BORDER = 2, ARTWORK = 3, OVERLAY = 4 }
-- the visible textures back to front, as flat rows: parent level, layer, sublevel, tc l r t b, size, position (UI units)
function Dump()
    local rows = {}
    for _, t in ipairs(__textures) do
        if t.shown and t.has and t.w then
            rows[#rows + 1] = { lvl = t.parent.level, layer = LAYER_IDX[t.layer], sub = t.sub, l = t.l, r = t.r, t = t.t, b = t.b,
                w = t.w, h = t.h, x = t.px, y = -t.py, tex = t.tex }
        end
    end
    table.sort(rows, function(a, b)
        if a.lvl ~= b.lvl then return a.lvl < b.lvl end
        if a.layer ~= b.layer then return a.layer < b.layer end
        return a.sub < b.sub
    end)
    return rows
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("the_config_preview_loops_enter_hold_exit_gap_and_stops_on_hide_and_in_combat", """
    assert(Boot() == true)
    local P = PU.Preview
    assert(P.Show() == true, "the preview comes up")
    assert(P.Phase() == "enter", "it starts with the real enter animation")
    local d = P.Driver()
    assert(d and d.scripts.OnUpdate, "the loop has a driver")
    local seen, shownAtHold = {}, nil
    local function step(sec)
        for _ = 1, math.floor(sec * 30 + 0.5) do
            local ph = P.Phase()
            if d.scripts.OnUpdate then d.scripts.OnUpdate(d, 1 / 30) end
            if P.Phase() then seen[P.Phase()] = true end
        end
    end
    step(5 - 0.5)
    assert(seen.hold and not seen.exit, "the alert holds for the real 5 s window before it exits")
    step(2.5)
    assert(seen.enter and seen.hold and seen.exit and seen.gap, "ignite, hold, exit and gap all ran")
    step(8)
    assert(P.Phase() ~= nil, "and it keeps repeating")
    P.Hide()
    assert(P.Phase() == nil and not d.scripts.OnUpdate, "the loop stops on hide")
    assert(not RootShown(), "and the alert is down")
    InCombatLockdown = function() return true end
    assert(P.Show() == false and P.Phase() == nil, "nothing loops in combat")
    InCombatLockdown = nil
""")

case("builds_for_warriors_only", """
    __class = "MAGE"
    assert(Boot() == false)
    assert(Root() == nil and #__applied == 0 and #__textures == 0 and #__editfn == 0)
    assert(not Driving())
""")

case("a_warrior_builds_a_hidden_plain_frame_seated_by_the_layout", """
    assert(Boot() == true)
    local r = Root()
    assert(r and r.name == "ForeverSTUwaveWarriorPowerUps" and r.parent == UIParent and r.layoutId == "warriorpowerup")
    assert(r.shown == false and r.strata == "MEDIUM" and r.mouse == false)
    assert(#__applied == 1 and __applied[1] == "warriorpowerup")
    assert(VisibleCount() == 0 and not Driving())
    assert(#__editfn == 1 and #__rescale == 1)
""")

case("idle_has_no_onupdate_and_a_secret_class_token_builds_nothing", """
    Boot()
    TickFor(1)
    assert(not Driving() and not RootShown())
    __class = SECRET
    assert(PU.Applies() == false)
""")

for _key, _id in (("overpower", 5), ("revenge", 5), ("victoryrush", 20)):
    case(f"{_key}_open_plays_enter_then_held_and_the_bar_drains", f"""
        Boot()
        __hp = 40
        Glow("{_key}", true)
        local k, s, i = State()
        assert(k == "{_key}" and s == "enter" and i == 1, tostring(k) .. tostring(s) .. tostring(i))
        assert(RootShown() and Driving())
        assert(VisibleCount() > 3)
        TickFor(1.5)
        k, s, i = State()
        assert(k == "{_key}" and s == "held", tostring(s))
        -- the fill: three slots stretched to remaining / window, 98 sprite px at full
        local want = math.floor((({_id} - 1.5) / {_id}) * 98 + 0.5)
        local fill = Art.SPELL.{_key}.fill
        for n = 1, 3 do
            local t = __textures[fill[n]]
            assert(t.shown and t.has, "fill slot " .. n .. " is up")
            assert(math.abs(t.w / 2.5 - want) <= 1, t.w / 2.5 .. " vs " .. want)
        end
    """)

case("the_last_one_and_a_half_seconds_play_amber", """
    Boot()
    Glow("overpower", true)
    TickFor(3.4)
    local _, s = State()
    assert(s == "held", s)
    assert(Run(0.3, function() local _, s2 = State() return s2 == "amber" end))
    local _, s2, i2 = State()
    assert(s2 == "amber" and i2 >= 1)
    Glow("victoryrush", false)
    TickFor(1.4)
    _, s2 = State()
    assert(s2 == "amber" or s2 == "exp", s2)
""")

case("revenge_and_victory_rush_hold_their_loop_phase_into_amber", """
    Boot()
    Glow("victoryrush", true)
    __hp = 40
    Win._PollAll(__now)
    TickFor(10)
    local _, s, i = State()
    assert(s == "held", s)
    assert(Run(10, function() local _, s2 = State() return s2 == "amber" end))
    local _, s2, i2 = State()
    assert(s2 == "amber" and i2 >= 1 and i2 <= 72, tostring(i2))          -- the 2.4 s loop is 72 frames
    TickFor(0.2)
    local _, s3 = State()
    assert(s3 == "amber")
""")

case("a_cast_plays_the_cast_exit_and_the_alert_goes_quiet", """
    Boot()
    Glow("overpower", true)
    TickFor(1.2)
    CastKey("overpower")
    local k, s, i = State()
    assert(k == "overpower" and s == "cast" and i == 1, tostring(s))
    assert(RootShown())
    local frames = #Art.SPELL.overpower.seqs.cast
    TickFor((frames - 1) / 30 + 0.1)
    k = State()
    assert(k == nil, "the exit must end")
    assert(not RootShown() and VisibleCount() == 0)
    assert(not Driving(), "no window open: the driver stops")
""")

case("an_unused_window_plays_the_expiry_exit", """
    Boot()
    Glow("revenge", true)
    assert(Run(6, function() local _, s = State() return s == "exp" end))
    local k, s = State()
    assert(k == "revenge" and s == "exp")
    local frames = #Art.SPELL.revenge.seqs.exp
    TickFor((frames - 1) / 30 + 0.2)
    assert(State() == nil and not RootShown() and not Driving())
""")

case("a_window_that_closes_quietly_hides_the_alert", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    assert(RootShown())
    Glow("overpower", false)
    assert(State() == nil and not RootShown())
    assert(not Driving())
""")

case("a_quiet_close_then_a_cast_inside_the_grace_still_plays_the_cast_exit", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    Glow("overpower", false)
    assert(State() == nil)
    __now = __now + 0.3
    CastKey("overpower")
    local k, s = State()
    assert(k == "overpower" and s == "cast", tostring(s))
""")

case("a_cast_of_a_window_that_was_never_shown_plays_nothing", """
    Boot()
    __hp = 100
    Glow("victoryrush", true)
    Win._PollAll(__now)
    assert(State() == nil)
    CastKey("victoryrush")
    assert(State() == nil and not RootShown())
""")

case("the_window_with_the_least_time_left_wins", """
    Boot()
    __hp = 50
    Glow("victoryrush", true)
    Win._PollAll(__now)
    TickFor(1)
    assert(State() == "victoryrush")
    Glow("overpower", true)
    local k, s = State()
    assert(k == "overpower" and s == "enter", tostring(k))
    CastKey("overpower")
    assert(select(2, State()) == "cast")
    TickFor(0.7)
    local k2, s2 = State()
    assert(k2 == "victoryrush" and s2 == "enter", tostring(k2) .. tostring(s2))
""")

case("victory_rush_above_the_health_gate_shows_nothing_and_the_module_polls", """
    Boot()
    __hp = 100
    Glow("victoryrush", true)
    assert(Win.Get("victoryrush").open and Win.Get("victoryrush").hidden == true)
    assert(State() == nil and not RootShown())
    assert(Driving(), "a held back window is polled")
    TickFor(0.5)
    assert(State() == nil)
    __hp = 40
    assert(Run(1, function() return State() == "victoryrush" end), "shown once health drops")
    assert(select(2, State()) == "enter" and RootShown())
    __hp = 100
    assert(Run(1, function() return State() == nil end), "held back again once health is above the gate")
""")

case("the_master_switch_hides_and_blocks", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    assert(RootShown())
    Cfg("gunsight.warrior.powerups", false)
    assert(State() == nil and not RootShown() and not Driving())
    Glow("revenge", true)
    assert(State() == nil)
    Cfg("gunsight.warrior.powerups", true)
    assert(State() ~= nil and RootShown())
""")

case("a_spell_switch_blocks_only_that_spell", """
    Boot()
    Cfg("gunsight.warrior.powerup.overpower", false)
    Glow("overpower", true)
    assert(State() == nil)
    Glow("revenge", true)
    assert(State() == "revenge")
    CastKey("overpower")
    assert(select(2, State()) ~= "cast", "no exit for a spell that is switched off")
""")

case("gunsight_off_hides_every_alert_and_on_brings_it_back", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    SetGun(false)
    assert(State() == nil and not RootShown())
    TickFor(0.5)
    SetGun(true)
    assert(State() == "overpower" and RootShown())
""")

case("the_layout_editor_shows_a_static_overpower_frame", """
    Boot()
    SetEdit(true)
    assert(RootShown() and VisibleCount() > 20)
    assert(State() == nil and not Driving(), "static: no ticker")
    local before = VisibleCount()
    TickFor(1)
    assert(VisibleCount() == before)
    Glow("revenge", true)
    assert(State() == nil, "no live alert while the editor is on")
    SetEdit(false)
    assert(State() == "revenge" and RootShown())
""")

case("a_cast_while_the_editor_is_on_plays_nothing_over_the_preview", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    SetEdit(true)
    CastKey("overpower")
    assert(State() == nil and select(4, State()) == true)
    local n = VisibleCount()
    TickFor(1)
    assert(VisibleCount() == n and not Driving())
""")

case("a_held_back_window_that_runs_out_plays_no_exit_and_the_polling_stops", """
    Boot()
    __hp = 100
    Glow("victoryrush", true)
    assert(Driving())
    TickFor(20.5)
    assert(State() == nil and not RootShown())
    assert(not Driving(), "no window open any more: the driver stops")
""")

case("the_editor_preview_survives_a_rescale", """
    Boot()
    SetEdit(true)
    local n = VisibleCount()
    __scale = 0.5
    for _, fn in ipairs(__rescale) do fn() end
    assert(VisibleCount() == n)
    local d = Dump()
    local top = d[1]
    assert(top.w > 0)
    SetEdit(false)
    assert(not RootShown())
""")

case("the_onupdate_is_only_set_while_an_alert_plays_or_a_window_waits", """
    Boot()
    assert(not Driving())
    Glow("overpower", true)
    assert(Driving())
    CastKey("overpower")
    assert(Driving())
    TickFor(1)
    assert(not Driving())
""")

case("a_tick_allocates_nothing", """
    if jit then jit.off() end                 -- trace compiling allocates, and it is not the module
    Boot()
    Win.Tick = function() end                 -- the window ledger is not under test here and allocates in its poll
    __hp = 40
    Glow("victoryrush", true)
    TickFor(5)                                -- two passes round the 2.4 s held loop warm every slot (the mock grows a field on a first seat)
    collectgarbage("collect"); collectgarbage("stop")
    local a = collectgarbage("count")
    for _ = 1, 240 do Tick(1 / 30) end        -- three more passes round the loop, then the 18.5 s mark is not yet reached
    local b = collectgarbage("count")
    collectgarbage("restart")
    local _, s = State()
    assert(s == "held", s)
    assert(b - a < 1, "a tick allocated " .. (b - a) .. " KB over 240 ticks")
""")

case("the_texture_stack_keeps_the_baked_order", """
    Boot()
    local seen, lastKey = 0, -1
    for i, t in ipairs(__textures) do
        local lvl = t.parent.level
        local key = lvl * 1000 + LAYER_IDX[t.layer] * 20 + (t.sub + 8)
        assert(key > lastKey, "slot " .. i .. " is not above slot " .. (i - 1))
        assert(t.sub >= -8 and t.sub <= 7)
        lastKey = key
        seen = seen + 1
    end
    local most = 0
    for _, s in pairs(Art.SPELL) do most = math.max(most, s.slots) end
    assert(seen == most, seen .. " textures for " .. most .. " slots")
    assert(__textures[1].tex == nil, "no texture is given a file before it shows")
""")

case("textures_are_filtered_nearest_and_sized_in_ui_units", """
    Boot()
    Glow("overpower", true)
    TickFor(0.5)
    local n = 0
    for _, row in ipairs(Dump()) do
        assert(row.tex:find("warrior_powerups_%d+%.tga$"), row.tex)
        assert(row.w > 0 and row.h > 0 and row.l < row.r and row.t < row.b)
        assert(math.abs(row.w / 2.5 - math.floor(row.w / 2.5 + 0.5)) < 1e-6 or row.h == 2.5)
        n = n + 1
    end
    assert(n > 10)
""")


def static_checks() -> list[str]:
    errs: list[str] = []
    toc = [line.strip() for line in TOC.splitlines()]
    try:
        order = [toc.index(f"Modules/CombatHud/{n}.lua") for n in ("WarriorWindows", "WarriorPowerUpArt", "WarriorPowerUps")]
        if order != sorted(order):
            errs.append("the toc must load WarriorWindows, WarriorPowerUpArt, WarriorPowerUps in that order")
    except ValueError:
        errs.append("the toc does not list WarriorPowerUpArt.lua and WarriorPowerUps.lua after WarriorWindows.lua")
    if not re.search(r'id = "warriorpowerup",\s+label = "[^"]+"', LAYOUTEDIT):
        errs.append("LayoutEdit.lua has no MOVABLE entry for warriorpowerup")
    m = re.search(r"warriorpowerup = \{ point = \"CENTER\", relPoint = \"CENTER\", x = (-?\d+),\s+y = (-?\d+),\s+w = (\d+),\s+h = (\d+)", LAYOUT)
    if not m:
        errs.append("Layout.lua has no warriorpowerup entry")
    elif (int(m.group(3)), int(m.group(4))) != (375, 240):
        errs.append(f"the warriorpowerup entry is {m.group(3)} x {m.group(4)}, want 375 x 240 (150 x 96 sprite px at 2.5)")
    if "PU.SETTING.key" not in CONFIGWINDOW:
        errs.append("ConfigPageClassModules.lua does not build the Warrior power-up group")
    if "OnEditChanged" not in LAYOUTEDIT:
        errs.append("LayoutEdit.lua has no OnEditChanged hook")
    for needle in ("COMBAT_LOG_EVENT_UNFILTERED", "CreateFrame(\"Button\"", "SecureActionButton", "SecureHandler"):
        for line in MODULE.splitlines():
            if needle in line and not line.lstrip().startswith("--"):
                errs.append(f"WarriorPowerUps.lua must not use {needle}")
    for word in ("bot", "automation", "macro"):
        if re.search(rf"\b{word}\b", MODULE.lower()) or re.search(rf"\b{word}\b", ART.lower()):
            errs.append(f"client visible text mentions '{word}'")
    atlas = re.findall(r'\{ file = "(\w+)", w = (\d+), h = (\d+) \}', ART)
    for name, w, h in atlas:
        path = MEDIA / f"{name}.tga"
        if not path.exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_warrior_powerups.py)")
        elif path.stat().st_size != 18 + int(w) * int(h) * 4:
            errs.append(f"{name}.tga is {path.stat().st_size} bytes, the manifest says {w} x {h}")
    return errs


def generator_is_deterministic() -> list[str]:
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "WarriorPowerUpArt.lua"))
        run = subprocess.run([sys.executable, str(ROOT / "tools/assets/generate_warrior_powerups.py")], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip().splitlines()[-1:]}"]
        if (Path(tmp) / "WarriorPowerUpArt.lua").read_bytes() != (CH / "WarriorPowerUpArt.lua").read_bytes():
            errs.append("WarriorPowerUpArt.lua is not what the generator writes (regenerate it)")
        for tga in sorted(Path(tmp).glob("warrior_powerups_*.tga")):
            committed = MEDIA / tga.name
            if not committed.exists() or committed.read_bytes() != tga.read_bytes():
                errs.append(f"{tga.name} is not what the generator writes (regenerate it)")
    return errs


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.WINDOWS_SRC, g.ART_SRC, g.MODULE_SRC = WINDOWS, ART, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# ----------------------------------------------------------------------------------------------------------------------
# Replay: the real module against the baked lists
# ----------------------------------------------------------------------------------------------------------------------
def load_manifest():
    import numpy as np
    from PIL import Image
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute("function load(src) local FS = {}; assert(loadstring(src, '@art'))('x', FS); return FS.WarriorPowerUpArt end")
    art = rt.eval("load")(ART)
    sprites = [tuple(int(art.SPRITE[i][k]) for k in range(1, 6)) for i in range(1, len(art.SPRITE) + 1)]
    spells = {}
    for name in ("overpower", "revenge", "victoryrush"):
        sp = art.SPELL[name]
        seqs = {}
        for seq in ("enter", "held", "amber", "cast", "exp"):
            seqs[seq] = [[int(v) for v in sp.seqs[seq][i].values()] for i in range(1, len(sp.seqs[seq]) + 1)]
        spells[name] = dict(slots=int(sp.slots), fill=[int(v) for v in sp.fill.values()], win=int(sp.win), seqs=seqs)
    atlases = []
    for i in range(1, len(art.ATLAS) + 1):
        file = str(art.ATLAS[i].file)
        atlases.append(np.asarray(Image.open(MEDIA / f"{file}.tga").convert("RGBA")))
    return sprites, spells, atlases


def blit(canvas, atlas, sprite, x, y, width=None):
    """Alpha composite one sprite (width overrides it for the stretched fill texel) onto the float canvas."""
    import numpy as np
    _, tx, ty, w, h = sprite
    src = atlas[ty:ty + h, tx:tx + w].astype(float)
    if width is not None:
        src = np.repeat(src[:, :1], width, axis=1)
        w = width
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, GW), min(y + h, GH)
    if x1 <= x0 or y1 <= y0:
        return
    src = src[y0 - y:y1 - y, x0 - x:x1 - x]
    a = src[..., 3:4] / 255
    canvas[y0:y1, x0:x1] = src[..., :3] * a + canvas[y0:y1, x0:x1] * (1 - a)


def expected_image(sprites, spell, atlases, seq, idx, fill_w):
    import numpy as np
    state: dict[int, tuple[int, int, int]] = {}
    frames = spell["seqs"][seq]
    for i in range(idx):
        flat = frames[i]
        if i == 0:
            state = {}
        for k in range(0, len(flat), 4):
            s, sid, x, y = flat[k:k + 4]
            if sid == 0:
                state.pop(s, None)
            else:
                state[s] = (sid, x, y)
    canvas = np.zeros((GH, GW, 3)) + BG
    for s in sorted(state):
        sid, x, y = state[s]
        sp = sprites[sid - 1]
        if s in spell["fill"]:
            if fill_w <= 0:
                continue
            blit(canvas, atlases[sp[0] - 1], sp, x, y, fill_w)
        else:
            blit(canvas, atlases[sp[0] - 1], sp, x, y)
    return canvas


def actual_image(rows, atlases):
    import numpy as np
    canvas = np.zeros((GH, GW, 3)) + BG
    for row in rows:
        n = int(re.search(r"warrior_powerups_(\d+)\.tga$", row["tex"]).group(1))
        atlas = atlases[n - 1]
        aw, ah = atlas.shape[1], atlas.shape[0]
        tx, ty = round(row["l"] * aw), round(row["t"] * ah)
        w, h = round((row["r"] - row["l"]) * aw), round((row["b"] - row["t"]) * ah)
        sprite = (n, tx, ty, w, h)
        x, y = round(row["x"] / SPX), round(row["y"] / SPX)
        wide = round(row["w"] / SPX) if w == 1 else None
        blit(canvas, atlas, sprite, x, y, wide)
    return canvas


SAMPLE_HELD = 7


def sampled(name: str, seq: str, idx: int, total: int) -> bool:
    if (seq, idx) in SHEET_WANT.get(name, ()):
        return True
    return idx <= 3 or idx == total or idx % SAMPLE_HELD == 0 if seq in ("held", "amber") else True


def replay_checks(keep: dict | None = None) -> list[str]:
    """Plays each spell's whole life and its cast, and compares sampled frames of the real module with the baked lists."""
    import numpy as np
    sprites, spells, atlases = load_manifest()
    errs: list[str] = []
    compared = 0
    for name in ("overpower", "revenge", "victoryrush"):
        spell = spells[name]
        for mode in ("life", "cast"):
            rt = LuaRuntime(unpack_returned_tuples=False)
            g = rt.globals()
            g.WINDOWS_SRC, g.ART_SRC, g.MODULE_SRC = WINDOWS, ART, MODULE
            rt.execute(MOCK)
            rt.execute("__hp = 40; Boot(); Glow('%s', true)" % name)
            state, tick, dump = rt.eval("State"), rt.eval("Tick"), rt.eval("Dump")
            seen = set()
            cast_done = mode == "life"
            for n in range(40 * 30):
                if mode == "cast" and not cast_done and n == 45:
                    rt.execute("CastKey('%s')" % name)
                    cast_done = True
                k, seq, idx, _ = state()
                if k is not None and (seq, idx) not in seen and seq is not None:
                    seen.add((seq, idx))
                    if sampled(name, str(seq), int(idx), len(spell["seqs"][str(seq)])):
                        rows = dump()
                        rows = [{key: rows[i][key] for key in ("l", "r", "t", "b", "w", "h", "x", "y", "tex")} for i in range(1, len(rows) + 1)]
                        want = expected_image(sprites, spell, atlases, str(seq), int(idx), 98)
                        got = actual_image(rows, atlases)
                        d = np.abs(want - got).max(axis=2)
                        d[82:92, :] = 0                      # the drain bar: its fill is drawn from the real remaining time
                        compared += 1
                        if int((d > 1).sum()) > 0:
                            errs.append(f"{name} {mode} {seq} frame {idx}: {int((d > 1).sum())} px differ")
                        if keep is not None:
                            keep[(name, str(seq), int(idx))] = got
                if k is None and n > 60:
                    break
                tick(1 / 30)
    if compared < 300:
        errs.append(f"only {compared} frames were compared")
    print(f"      replay compared {compared} frames")
    return errs


# The strip frames of the mockup (seq, 1-based frame in the sequence, caption): entrance, impact or cackle, held, amber, the exits.
SHEET = {
    "overpower": [("enter", 3, "entrance 0.08 s"), ("enter", 7, "impact 0.20 s"), ("enter", 13, "entrance 0.40 s"), ("held", 34, "held 1.6 s"),
                  ("held", 76, "held 3.0 s"), ("amber", 19, "amber 4.1 s"), ("cast", 5, "cast exit 0.13 s"), ("cast", 13, "cast exit 0.40 s"),
                  ("exp", 10, "expiry exit 0.30 s"), ("exp", 19, "expiry exit 0.60 s")],
    "revenge": [("enter", 3, "shield 0.06 s"), ("enter", 6, "rising 0.17 s"), ("enter", 10, "cackle 0.30 s"), ("enter", 30, "title 0.97 s"),
                ("held", 16, "held 1.6 s"), ("held", 52, "cackle 2.8 s"), ("amber", 16, "amber 1.6 s"), ("cast", 5, "cast exit 0.13 s"),
                ("exp", 4, "expiry exit 0.10 s"), ("exp", 10, "expiry exit 0.30 s")],
    "victoryrush": [("enter", 3, "iris 0.07 s"), ("enter", 5, "axes in 0.13 s"), ("enter", 6, "clang 0.17 s"), ("enter", 10, "flames 0.30 s"),
                    ("held", 10, "clang 1.2 s"), ("held", 40, "held 2.2 s"), ("amber", 40, "amber 2.2 s"), ("cast", 5, "cast exit 0.13 s"),
                    ("exp", 4, "expiry exit 0.10 s"), ("exp", 12, "expiry exit 0.37 s")],
}
SHEET_WANT = {name: {(seq, idx) for seq, idx, _ in frames} for name, frames in SHEET.items()}


def png(prefix: str) -> None:
    """One sheet per spell: the SHEET frames at 2 px per sprite px."""
    from PIL import Image, ImageDraw
    keep: dict = {}
    replay_checks(keep)
    for name in ("overpower", "revenge", "victoryrush"):
        frames = [(seq, idx) for seq, idx, _ in SHEET[name]]
        captions = {(seq, idx): cap for seq, idx, cap in SHEET[name]}
        cols = 5
        rows = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 300, rows * 210), (30, 20, 50))
        draw = ImageDraw.Draw(sheet)
        for n, (seq, idx) in enumerate(frames):
            cap = captions[(seq, idx)]
            img = keep.get((name, seq, idx))
            if img is None:
                near = [k for k in keep if k[0] == name and k[1] == seq]
                if not near:
                    continue
                pick = min(near, key=lambda k: abs(k[2] - idx))
                img = keep[pick]
                cap += f" (frame {pick[2]})"
            tile = Image.fromarray(img.round().clip(0, 255).astype("uint8")).resize((300, 192), Image.NEAREST)
            x, y = (n % cols) * 300, (n // cols) * 210
            sheet.paste(tile, (x, y + 16))
            draw.text((x + 4, y + 2), cap, fill=(200, 190, 230))
        out = f"{prefix}-{name}.png"
        sheet.save(out)
        print("wrote", out)


def main() -> int:
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    total = len(CASES)
    errs = replay_checks()
    for e in errs:
        failures += 1
        print(f"FAIL  replay: {e}")
    if not errs:
        print("ok    replay_matches_the_baked_lists")
    total += 1
    errs = generator_is_deterministic()
    for e in errs:
        failures += 1
        print(f"FAIL  generator: {e}")
    if not errs:
        print("ok    generator_is_deterministic")
    total += 1
    print(f"{total - min(failures, total)}/{total} checks passed")
    if "--png" in sys.argv:
        prefix = sys.argv[sys.argv.index("--png") + 1]
        Path(prefix).parent.mkdir(parents=True, exist_ok=True)
        png(prefix)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
