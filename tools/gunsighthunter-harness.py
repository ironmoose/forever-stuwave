#!/usr/bin/env python3
"""Runs the real HunterState.lua and GunsightHunter.lua headless against a mock client.

The Hunter Class Module draws the design mockup "Hunter Lock-on and Traps" (2026-11-07, design D radar): the range scope with the
shot timer on its rim and a skull on the ring the target is in, and the traps (the jaws on the shared 30 s cooldown and the fire
and frost slots). These checks pin:

  * the shot clock: the rim fills cyan, the last 0.5 s is the dim gold plant zone with its plant line and whole second ticks, the
    fill turns gold in the wind-up and the brackets snap in, a flash crosses the plant line, the arrow and burst on the shot;
  * moving in the wind-up (pink rim, shaking brackets, the late counter), a late shot's +x.x, a melee swing reset (and the
    constant that switches it off), Auto Shot off in combat (the amber nudge) and calm out of combat;
  * range: the four states from the spell range checks, the skull's ring and its slide, a due shot held out of range;
  * ammo: the quiver and count under the threshold setting, NO AMMO at zero, nothing with no ranged weapon;
  * traps: open jaws and READY, the snap and SET on an own cast, the engine's refill (never a number), the two ledger slots
    with their "~N" and their minute, the calm look and nothing learned;
  * secrets: an unreadable weapon speed, range or cooldown falls back and never throws; no table is built per tick;
  * onHide stops the ticker and the subscription (the ledger keeps listening), onShow brings them back;
  * under the REAL GunsightAreas.lua the host hides with no target and the module stops with it;
  * the baked textures exist, and the module's cell maps, atlas geometry, boxes and pools match the generators.

    python3 tools/gunsighthunter-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import math
import re
import struct
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
DATA = (ADDON / "Modules/CombatHud/HunterState.lua").read_text(encoding="utf-8")
MODULE = (ADDON / "Modules/CombatHud/GunsightHunter.lua").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
ASSETS = HERE / "assets"
TOC = ADDON / "forever-stuwave.toc"

MOCK = r"""
function check(c, msg) if not c then error(msg or "check failed", 2) end end
SECRET_MT = {
    __lt = function() error("SECRET_OP: compare", 2) end, __le = function() error("SECRET_OP: compare", 2) end,
    __add = function() error("SECRET_OP: arith", 2) end, __sub = function() error("SECRET_OP: arith", 2) end,
    __mul = function() error("SECRET_OP: arith", 2) end, __div = function() error("SECRET_OP: arith", 2) end,
    __unm = function() error("SECRET_OP: arith", 2) end, __concat = function() error("SECRET_OP: concat", 2) end,
    __len = function() error("SECRET_OP: len", 2) end, __tostring = function() return "secret" end,
}
function Secret(tag) return setmetatable({ tag = tag }, SECRET_MT) end
function IsSecretValue(v) return getmetatable(v) == SECRET_MT end

local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind, parent) return setmetatable({ kind = kind, parent = parent, shown = true, events = {}, scripts = {} }, Obj) end
-- the anchor is written into the region's own table (no allocation: the steady tick case measures the module, not the mock)
function Obj:SetPoint(p, rel, rp, x, y)
    local pt = self.pt or {}
    pt[1], pt[2], pt[3], pt[4], pt[5] = p, rel, rp, x or 0, y or 0
    self.pt = pt
end
function Obj:ClearAllPoints() end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts[n] end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:RegisterUnitEvent(e, ...) self.events[e] = { ... } end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level or 1 end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b)
    local c = self.tc or {}
    c[1], c[2], c[3], c[4] = l, r, t, b
    self.tc = c
end
function Obj:SetVertexColor(r, g, b, a)
    local c = self.color or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.color = c
end
function Obj:SetText(t) self.text = t end
function Obj:SetTextColor(r, g, b, a)
    local c = self.tcolor or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.tcolor = c
end
function Obj:CreateTexture() local t = New("Texture", self); __textures[#__textures + 1] = t; return t end
function Obj:CreateFontString() local f = New("FontString", self); __fonts[#__fonts + 1] = f; return f end
-- StatusBar
function Obj:SetMinMaxValues(a, b) self.min, self.max = a, b end
function Obj:SetValue(v) self.value = v end
function Obj:SetStatusBarTexture(p) self.fill = self.fill or New("Texture", self); self.fill.tex = p end
function Obj:SetTimerDuration(obj, interp, dir) self.timer = { obj = obj, interp = interp, dir = dir } end
__textures, __fonts, __frames = {}, {}, {}
function CreateFrame(kind, name, parent)
    local f = New(kind, parent); f.name = name
    __frames[#__frames + 1] = f
    return f
end
function fire(event, ...)
    for _, f in ipairs({ unpack(__frames) }) do
        local reg = f.events[event]
        if reg and f.scripts.OnEvent then
            local ok = true
            if type(reg) == "table" then
                ok = false
                for _, u in ipairs(reg) do if u == (...) then ok = true end end
            end
            if ok then f.scripts.OnEvent(f, event, ...) end
        end
    end
end
function visible(r) while r do if r.shown == false then return false end; r = r.parent end return true end

__now = 1000
function GetTime() return __now end
__timers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end }
function RunTimers() local t = __timers; __timers = {}; for _, fn in ipairs(t) do fn() end end
__combat = false
function InCombatLockdown() return __combat end

-- units
__units = { player = { guid = "P", name = "Stu", friend = true, class = "HUNTER" } }
function UnitExists(u) return __units[u] ~= nil end
function UnitGUID(u) return __units[u] and __units[u].guid end
function UnitIsUnit(a, b) return __units[a] ~= nil and __units[b] ~= nil and __units[a].guid == __units[b].guid end
__level = 12
function UnitLevel() return __level end
__canAttack = true
function UnitCanAttack() return __canAttack end
function SetTarget(kind)
    if kind == nil then __units.target = nil; return end
    __units.target = { guid = "T", name = "Boar", friend = kind == "friend", hostile = kind == "hostile" }
end

-- spells: every id of a spell answers to its name; IsPlayerSpell says what the Hunter has learned
CAST = { autoshot = 75, raptor = 2973, mongoose = 1495, wingclip = 2974, feign = 5384, immolation = 13795, freezing = 1499,
    explosive = 13813, frost = 13809 }
__known, __names, __byname = {}, {}, {}
function IsPlayerSpell(id) return __known[id] == true end
function Forget(key) __known[CAST[key]] = nil end
__cd = {}                -- spell name -> true while its own cooldown runs
local CD_ON = { isActive = true, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
local CD_OFF = { isActive = false, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
Enum = { StatusBarTimerDirection = { ElapsedTime = 1, RemainingTime = 0 }, StatusBarInterpolation = { Immediate = 0 } }
__range = { ["Raptor Strike"] = false, ["Auto Shot"] = true }      -- spell name -> true / false / "secret" / nil
local function NameOf(ref) return type(ref) == "number" and __names[ref] or ref end
C_Spell = {
    GetSpellName = function(id) return __names[id] end,
    GetSpellInfo = function(name) local id = __byname[name]; return id and { spellID = id, name = name } or nil end,
    GetSpellCooldown = function(id) return __cd[NameOf(id)] == true and CD_ON or CD_OFF end,
    GetSpellCooldownDuration = function(id) return { durationOf = id } end,
    IsSpellInRange = function(ref, unit)
        local r = __range[NameOf(ref)]
        if r == "secret" then return Secret("range") end
        return r
    end,
}
__near = false
function CheckInteractDistance(unit, idx) __interactIdx = idx; return __near end
__speed = 2.8
function UnitRangedDamage() if __speed == "secret" then return Secret("speed") end return __speed, 10, 20 end
__moving = false
function GetUnitSpeed() return __moving and 7 or 0, 7 end
__auto = false
function IsAutoRepeatSpell() return __auto end
__bow, __ammoItem, __ammo = 2504, 2515, 180
function GetInventoryItemID(unit, slot)
    if slot == 18 then return __bow end
    if slot == 0 then return __ammoItem end
end
function GetItemCount(id) return __ammo end

CFG = {}
__logged = {}
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
FS = {
    IsSecret = IsSecretValue,
    Config = { RegisterDefault = function(k, v) CFG[k] = CFG[k] == nil and v or CFG[k] end, Get = function(k) return CFG[k] end },
    Gunsight = { ui = function(px) return px end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    Theme = { ApplyMono = function(fs, size) fs.size = size end },
    LogDegradeOnce = function(k, m) __logged[k] = m end,
}
assert(loadstring(DATA_SRC, "@HunterState.lua"))("forever-stuwave", FS)
D = FS.HunterState
for _, d in pairs(D.DEFS) do for _, id in ipairs(d.ids) do __names[id] = d.name end end
for key, id in pairs(CAST) do
    __names[id] = D.DEFS[key].name
    __byname[D.DEFS[key].name] = id
    __known[id] = true
end
assert(loadstring(MODULE_SRC, "@GunsightHunter.lua"))("forever-stuwave", FS)
H = FS.GunsightHunter
SPEC = Areas.specs[1].spec
CELL = H.CELL
KC = H.C.COLORS
ELAPSED = Enum.StatusBarTimerDirection.ElapsedTime
SetTarget("hostile")
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function Parts() return H.parts end
function Tick(dt)
    __now = __now + dt
    local f = H.frame.scripts.OnUpdate
    if f then f(H.frame, dt) end
end
function Ticking() return H.frame.scripts.OnUpdate ~= nil end
function Cast(key) fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", CAST[key]) end
function AutoOn(on) __auto = on; fire(on and "START_AUTOREPEAT_SPELL" or "STOP_AUTOREPEAT_SPELL") end
function NoLog()
    for k, v in pairs(__logged) do error("logged " .. k .. ": " .. tostring(v), 2) end
end
function Shown(t) return t.shown ~= false and visible(t) end
-- a fresh shot clock: Auto Shot on in combat, a shot just fired
function Fight()
    __combat = true
    Build()
    AutoOn(true)
    Cast("autoshot")
    Tick(1 / 30)
end
-- how many rim px wear the colour c (or any of the list)
function RimCount(...)
    local n, cols = 0, { ... }
    for _, p in ipairs(Parts().rim.px) do
        for _, c in ipairs(cols) do if p.c == c then n = n + 1 break end end
    end
    return n
end
function RimBelow(angle)
    local n = 0
    for _, p in ipairs(Parts().rim.px) do if p.a < angle then n = n + 1 end end
    return n
end
function Lab() return Parts().labels.main.text end
function BracketsShown()
    local n = 0
    for _, b in pairs(Parts().lock.br) do if Shown(b) then n = n + 1 end end
    return n
end
function CornersShown()
    local n = 0
    for name, c in pairs(Parts().lock.corner) do
        local b = Parts().lock.br[name]
        if Shown(c) and c.color[1] == b.color[1] and c.color[4] == b.color[4] then n = n + 1 end
    end
    return n
end
function DotsShown()
    local n = 0
    for _, d in ipairs(Parts().lock.dots) do if Shown(d) then n = n + 1 end end
    return n
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_hunters_only", """
    check(SPEC and SPEC.classes[1] == "HUNTER" and #SPEC.classes == 1)
    local m = Build()
    check(m and m.name == "ForeverSTUwaveGunsightHunter")
    check(Parts().rim.n > 400, "the rim is the mockup's px ring: " .. Parts().rim.n)
    NoLog()
""")

case("calm_out_of_combat_is_dim_and_still", """
    Build()
    local p = Parts()
    Tick(0.05)
    check(not Ticking(), "calm: nothing moves, no ticker")
    check(Lab() == "", "no label")
    check(RimCount(KC.rimBase) == p.rim.n, "the rim is the dark track")
    check(Shown(p.zones.unlit.ranged) and not Shown(p.zones.lit.ranged), "no zone is lit")
    check(not Shown(p.zones.cross) and not Shown(p.skull.body) and BracketsShown() == 0 and CornersShown() == 0, "no cross hairs, skull or brackets")
    check(Shown(p.trap.dim), "the trap piece is dimmed")
    check(p.trap.label.text == "", "and says nothing")
    NoLog()
""")

case("auto_shot_off_in_combat_in_range_nudges_amber_and_says_auto", """
    __combat = true
    Build()
    local p = Parts()
    check(Ticking(), "the nudge pulses")
    check(Lab() == "AUTO", "AUTO: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.amber[1] and p.labels.main.tcolor[4] >= 0.35, "amber")
    check(RimCount(KC.amber) > 0 and RimCount(KC.amber) < p.rim.n, "alternate dashes of the rim")
    local seen, n = {}, 0
    for i = 1, 45 do Tick(1 / 30); local a = p.labels.main.tcolor[4]; if not seen[a] then seen[a] = true; n = n + 1 end end
    check(n >= 4, "it breathes: " .. n)
    check(BracketsShown() == 0, "no lock-on yet")
    -- the same fight in melee: no nudge, the skull is on the inner ring
    __range["Raptor Strike"] = true; __range["Auto Shot"] = false
    Tick(0.2)
    check(Lab() == "MELEE", "melee with Auto Shot off: " .. tostring(Lab()))
    NoLog()
""")

case("the_rim_fills_cyan_and_the_last_half_second_is_dim_gold_with_a_plant_line_and_ticks", """
    Fight()
    local p = Parts()
    Tick(1.4)                                      -- half of a 2.8 s cycle
    local filled = RimBelow(2 * math.pi * D.Fill(__now))
    check(RimCount(KC.free, KC.freeHi) == filled and filled > 100, "cyan to the fill edge: " .. RimCount(KC.free, KC.freeHi) .. " of " .. filled)
    local pa = 2 * math.pi * (2.8 - 0.5) / 2.8
    local zone = p.rim.n - RimBelow(pa)
    check(RimCount(KC.outerLo, KC.plantLo) >= zone, "the plant zone is dim gold: " .. RimCount(KC.outerLo, KC.plantLo) .. " >= " .. zone)
    check(Shown(p.rim.marks) and p.rim.lineShown > 8, "the plant line is laid out: " .. p.rim.lineShown)
    check(p.rim.tickShown >= 2, "ticks at whole seconds: " .. p.rim.tickShown)
    check(p.rim.line[1].color[1] == KC.plant[1] and p.rim.line[1].color[3] == KC.plant[3], "the plant line is gold before the wind-up")
    check(p.rim.sparkShown > 3, "the spark rides the fill's edge: " .. p.rim.sparkShown)
    check(Lab():match("^%d%.%d$") and tonumber(Lab()) > 0.5 and tonumber(Lab()) < 1.1, "seconds you may walk: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.freeHi[1], "in the free colour")
    check(BracketsShown() == 4 and p.lock.br.TL.color[4] == 0.45, "loose brackets at a low alpha")
    check(CornersShown() == 4, "each bracket's corner px is drawn twice, like the mockup's, in the bracket's colour")
    check(DotsShown() >= 3, "a dotted aim line: " .. DotsShown())
    NoLog()
""")

case("the_plant_zone_follows_the_cycle_when_haste_changes_it", """
    Fight()
    local p = Parts()
    Tick(0.2)
    local before = p.rim.plantAngle
    check(math.abs(before - 2 * math.pi * 2.3 / 2.8) < 1e-9)
    __speed = 2.0
    fire("UNIT_ATTACK_SPEED", "player")
    Tick(0.2)
    check(D.Shot().cycle == 2.0 and math.abs(p.rim.plantAngle - 2 * math.pi * 1.5 / 2.0) < 1e-9, "re-laid out for the new cycle: " .. tostring(p.rim.plantAngle))
    local t2 = p.rim.tickShown
    check(t2 > 0 and t2 < 6, "the one whole second tick of a 2 s cycle: " .. t2)
    __speed = 5.0
    fire("UNIT_ATTACK_SPEED", "player")
    Tick(0.2)
    check(p.rim.tickShown > 2 * t2, "four ticks in a 5 s cycle: " .. p.rim.tickShown .. " px against " .. t2)
    NoLog()
""")

case("the_wind_up_turns_the_fill_gold_snaps_the_brackets_in_and_says_plant", """
    Fight()
    local p = Parts()
    Tick(2.1)
    check(Lab() ~= "PLANT", "not yet")
    Tick(0.25)                                     -- 2.35 s of 2.8: inside the last half second
    check(Lab() == "PLANT", "PLANT: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.plantHi[1], "in pale gold")
    check(RimCount(KC.plantHi, KC.plant) > 150, "the whole fill is gold: " .. RimCount(KC.plantHi, KC.plant))
    check(RimCount(KC.free, KC.freeHi) == 0, "and nothing is cyan")
    check(p.rim.line[1].color[1] == KC.white[1], "the plant line is white in the wind-up")
    local k = (2.35 / 2.8 - 2.3 / 2.8) / (1 - 2.3 / 2.8)
    local want = math.floor(12 - 6 * k + 0.5)
    check(BracketsShown() == 4 and p.lock.br.TL.color[1] == KC.plant[1], "brackets in gold")
    local sx = p.lock.br.TL.fsX
    Tick(0.2)
    check(p.lock.br.TL.fsX > sx, "and closing in")
    check(p.you.feetL.fsW == 2 and p.you.feetL.color[1] == KC.plantHi[1], "feet planted")
    check(p.you.dot.color[1] == KC.plantHi[1], "you in pale gold")
    local seen, n = {}, 0
    for i = 1, 20 do
        Tick(0.01)
        local a = p.rim.px[1].al
        if not seen[a] then seen[a] = true; n = n + 1 end
    end
    NoLog()
""")

case("crossing_the_plant_line_flashes_white_once", """
    Fight()
    local p = Parts()
    Tick(2.2)
    check(not Shown(p.rim.flash), "before the line: " .. tostring(p.rim.flash.shown))
    Tick(0.1)
    check(Shown(p.rim.flash), "the flash")
    local a = p.rim.flash.color[4]
    check(a > 0.4, "bright at first: " .. a)
    Tick(0.2)
    check(not Shown(p.rim.flash), "and gone inside 0.15 s")
    NoLog()
""")

case("a_shot_flies_an_arrow_down_the_line_and_bursts_and_the_rim_starts_over", """
    Fight()
    local p = Parts()
    Tick(2.5)
    Cast("autoshot")
    Tick(0.05)
    check(Shown(p.fx.trail[0]) and Shown(p.fx.plusH), "the arrow")
    check(RimCount(KC.free, KC.freeHi) < 30 and RimCount(KC.plantHi, KC.plant) == 0, "the rim starts over")
    Tick(0.15)
    check(Shown(p.fx.ring5) and Shown(p.fx.sparks[1]), "the burst")
    Tick(0.2)
    check(Shown(p.fx.ring7), "the larger ring later")
    Tick(0.5)
    check(not Shown(p.fx.ring7) and not Shown(p.fx.sparks[1]) and not Shown(p.fx.trail[0]), "and it clears")
    check(BracketsShown() == 4 and p.lock.br.TL.color[4] == 0.45, "the loose brackets are back")
    NoLog()
""")

case("the_free_brackets_stay_away_for_half_a_second_after_a_shot", """
    Fight()
    local p = Parts()
    Tick(0.1)
    check(BracketsShown() == 0 and DotsShown() == 0, "hidden just after a shot")
    Tick(0.45)
    check(BracketsShown() == 4, "back after 0.5 s")
    NoLog()
""")

case("moving_in_the_wind_up_is_pink_with_shaking_brackets_and_the_late_counter", """
    Fight()
    local p = Parts()
    Tick(2.4)
    __moving = true
    Tick(0.1)
    check(RimCount(KC.pink) == p.rim.n, "the whole rim is pink")
    check(BracketsShown() == 4 and p.lock.br.TL.color[1] == KC.pink[1], "pink brackets")
    local sizes, n = {}, 0
    for i = 1, 20 do
        Tick(1 / 30)
        local s = p.lock.br.TL.fsX
        if not sizes[s] then sizes[s] = true; n = n + 1 end
    end
    check(n >= 2, "the brackets shake apart")
    Tick(0.4)                                      -- past the due time: 2.8 s
    local late = D.Late(__now)
    check(late > 0.05 and Lab() == "+" .. string.format("%.1f", late), "the late counter: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.pinkHi[1], "in light pink")
    check(p.you.feetL.color[1] == KC.pink[1], "feet moving in pink")
    __moving = false
    Tick(0.1)
    check(RimCount(KC.pink) == 0 and RimCount(KC.plantHi, KC.plant) == p.rim.n, "standing still turns the full rim gold again")
    check(Lab():sub(1, 1) == "+", "still counting late")
    NoLog()
""")

case("a_late_shot_shows_how_late_for_one_and_a_half_seconds", """
    Fight()
    local p = Parts()
    Tick(3.8)
    Cast("autoshot")
    Tick(0.1)
    check(D.Shot().lateAmt and math.abs(D.Shot().lateAmt - 1.0) < 0.15, "ledger: " .. tostring(D.Shot().lateAmt))
    check(Lab() == "+1.0" or Lab() == "+1.1" or Lab() == "+0.9", "+1.0 shows: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.pink[1], "in pink")
    Tick(1.5)
    check(Lab() ~= "+1.0" and Lab():sub(1, 1) ~= "+", "and goes after 1.5 s: " .. tostring(Lab()))
    NoLog()
""")

case("a_shot_on_time_shows_no_late_count", """
    Fight()
    Tick(2.8)
    Cast("autoshot")
    Tick(0.1)
    check(D.Shot().lateAmt == nil and Lab():sub(1, 1) ~= "+")
    NoLog()
""")

case("a_melee_swing_ability_resets_the_shot_and_flashes_the_rim_pink", """
    Fight()
    local p = Parts()
    Tick(2.0)
    Cast("raptor")
    Tick(0.05)
    check(Lab() == "RESET", "RESET: " .. tostring(Lab()))
    check(Shown(p.rim.reset), "the reset flash")
    check(D.Fill(__now) < 0.05, "the clock starts over")
    Tick(0.5)
    check(not Shown(p.rim.reset) and Lab() == "RESET", "the flash is short, the label stays 1 s")
    Tick(0.6)
    check(Lab() ~= "RESET")
    -- the constant that switches it off
    D.TUNING.MELEE_RESET = false
    Tick(1.0)
    local last = D.Shot().last
    Cast("raptor")
    check(D.Shot().last == last, "a fixed client: no reset")
    D.TUNING.MELEE_RESET = true
    Cast("feign")
    check(D.Shot().last == __now, "Feign Death resets either way")
    NoLog()
""")

case("the_range_states_come_from_the_spell_range_checks_and_the_skull_sits_on_its_ring", """
    Fight()
    local p = Parts()
    local function at(name) local f = p.skull.body; return f.fsX, f.fsY end
    Tick(0.1)
    local rx, ry = at()
    check(Shown(p.zones.lit.ranged) and not Shown(p.zones.unlit.ranged), "the shooting range ring is lit")
    __range["Raptor Strike"] = true; __range["Auto Shot"] = false
    Tick(0.5); Tick(0.5)
    check(Shown(p.zones.lit.melee) and Shown(p.zones.unlit.ranged), "melee")
    check(Shown(p.skull.claws) and not Shown(p.skull.strike), "claws on a melee skull")
    local mx, my = at()
    check(my > ry and mx < rx, "the skull is closer to the centre")
    __range["Raptor Strike"] = false; __near = true
    Tick(0.5)
    check(Shown(p.zones.lit.dead) and Shown(p.skull.strike) and not Shown(p.skull.claws), "dead zone, struck through")
    check(__interactIdx == 3, "told from too far by the duel distance")
    __near = false
    Tick(0.5)
    check(Shown(p.zones.lit.far) and p.skull.body.color[4] == 0.55, "too far: lit outer ring, faded skull")
    __range["Auto Shot"] = true
    Tick(0.5)
    check(Shown(p.zones.lit.ranged), "back in range")
    NoLog()
""")

case("the_skull_slides_between_rings_over_a_third_of_a_second", """
    Fight()
    local p = Parts()
    Tick(0.1)
    local _, y0 = p.skull.body.fsX, p.skull.body.fsY
    __range["Raptor Strike"] = true; __range["Auto Shot"] = false
    Tick(0.12)                                     -- the range re-read lands
    local mid = p.skull.body.fsY
    Tick(0.1)
    local mid2 = p.skull.body.fsY
    Tick(0.4)
    local end_ = p.skull.body.fsY
    check(mid ~= end_ or mid2 ~= end_, "it is mid slide for a moment: " .. mid .. " " .. mid2 .. " " .. end_)
    check(end_ > y0, "and ends nearer: " .. end_ .. " vs " .. y0)
    NoLog()
""")

case("a_due_shot_out_of_shooting_range_is_held_with_a_striped_rim_and_the_zone_name", """
    Fight()
    local p = Parts()
    __range["Auto Shot"] = false; __near = true
    Tick(3.0)                                      -- the cycle ran out while out of range
    check(Lab() == "DEAD ZONE", "label: " .. tostring(Lab()))
    check(p.labels.main.tcolor[1] == KC.pink[1], "in the zone colour")
    check(D.Late(__now) > 0, "the shot is overdue")
    check(RimCount(KC.pink) == p.rim.n, "the rim wears the zone colour")
    local a1 = p.rim.px[5].al
    local differ = false
    for i = 1, 12 do Tick(0.125); if p.rim.px[5].al ~= a1 then differ = true end end
    check(differ, "and the stripes run")
    check(BracketsShown() == 4 and p.lock.br.TL.color[1] == KC.pink[1], "open brackets in the zone colour")
    check(not Shown(p.rim.marks) and not Shown(p.rim.flash), "no ticks, no plant line")
    __range["Raptor Strike"] = true; __near = false
    Tick(0.5)
    check(Lab() == "MELEE" and p.labels.main.tcolor[1] == KC.melee[1], "melee: " .. tostring(Lab()))
    __range["Raptor Strike"] = false
    Tick(0.5)
    check(Lab() == "FAR", "too far: " .. tostring(Lab()))
    __range["Auto Shot"] = true
    Tick(0.5)
    check(Lab():sub(1, 1) == "+", "in range again the shot is simply late: " .. tostring(Lab()))
    NoLog()
""")

case("the_lock_on_does_not_close_while_out_of_range", """
    Fight()
    local p = Parts()
    __range["Auto Shot"] = false; __near = true
    Tick(2.4)
    check(Lab() == "DEAD ZONE" and p.lock.br.TL.color[4] == 0.45 and p.lock.br.TL.color[1] == KC.free[1], "open, loose brackets")
    NoLog()
""")

case("ammo_shows_under_the_threshold_and_no_ammo_at_zero", """
    Fight()
    local p = Parts()
    __ammo = 180; fire("BAG_UPDATE_DELAYED"); Tick(0.1)
    check(not Shown(p.labels.quiver) and not Shown(p.labels.ammo), "plenty: nothing")
    __ammo = 60; fire("BAG_UPDATE_DELAYED"); Tick(0.1)
    check(Shown(p.labels.quiver) and Shown(p.labels.ammo) and p.labels.ammo.text == "60", "at the threshold: 60")
    check(p.labels.ammo.tcolor[1] == KC.amber[1], "amber")
    CFG["gunsight.hunter.ammowarn"] = 30
    Tick(0.1)
    check(not Shown(p.labels.quiver), "a lower threshold hides it")
    CFG["gunsight.hunter.ammowarn"] = 0
    __ammo = 0; fire("BAG_UPDATE_DELAYED"); Tick(0.1)
    check(Lab() == "NO AMMO" and p.labels.main.tcolor[1] == KC.pink[1], "NO AMMO: " .. tostring(Lab()))
    check(Shown(p.labels.quiver) and p.labels.ammo.text == "0" and p.labels.ammo.tcolor[1] == KC.pink[1], "and a pink 0")
    __ammo = 5; fire("BAG_UPDATE_DELAYED"); Tick(0.1)
    check(not Shown(p.labels.quiver), "a threshold of 0 shows only NO AMMO")
    __bow = nil; __ammo = 0; fire("PLAYER_EQUIPMENT_CHANGED"); Tick(0.1)
    check(D.Ammo() == nil and Lab() ~= "NO AMMO", "no ranged weapon: nothing to count")
    NoLog()
""")

case("the_trap_lies_open_with_ready_while_the_shared_cooldown_is_up", """
    Fight()
    local t = Parts().trap
    Tick(0.1)
    check(Shown(t.open) and Shown(t.glow) and not Shown(t.dark) and not Shown(t.lit) and not Shown(t.white), "jaws open with a glow")
    check(t.label.text == "READY" and t.label.tcolor[1] == KC.mintHi[1], "READY")
    local seen, n = {}, 0
    for i = 1, 60 do Tick(1 / 30); local a = t.glow.color[4]; if not seen[a] then seen[a] = true; n = n + 1 end end
    check(n >= 4, "the glow breathes: " .. n)
    check(not Shown(t.dim), "bright in combat")
    NoLog()
""")

case("a_trap_cast_snaps_the_jaws_shut_says_set_and_then_refills_on_the_engines_timer", """
    Fight()
    local t = Parts().trap
    __cd["Freezing Trap"] = true
    Cast("freezing")
    Tick(1 / 30)
    check(Shown(t.white) and not Shown(t.open) and not Shown(t.dark), "the white snap")
    check(t.label.text == "SET" and t.label.tcolor[1] == 1, "SET")
    Tick(0.2)
    check(not Shown(t.white) and Shown(t.dark) and not Shown(t.open), "the dark shut jaws")
    check(Shown(t.lit) and t.lit.timer and t.lit.timer.dir == ELAPSED and t.lit.timer.obj.durationOf, "lit from the bottom on the engine's own timer")
    check(not Shown(t.glow), "no glow while it refills")
    check(t.label.text == "SET", "SET stays 0.8 s")
    Tick(0.7)
    check(t.label.text == "", "then nothing: the refill has no number")
    __cd["Freezing Trap"] = nil
    fire("SPELL_UPDATE_COOLDOWN"); Tick(0.1)
    check(Shown(t.open) and t.label.text == "READY" and not Shown(t.lit), "ready again")
    NoLog()
""")

case("the_cooldown_object_is_asked_for_once_per_refill", """
    Fight()
    local t = Parts().trap
    __cd["Immolation Trap"] = true
    Cast("immolation")
    Tick(0.5)
    local obj = t.lit.timer.obj
    for i = 1, 30 do Tick(1 / 30) end
    check(t.lit.timer.obj == obj, "the same duration object all the way")
    NoLog()
""")

case("the_two_slots_count_a_minute_from_the_own_cast_with_a_tilde", """
    Fight()
    local t = Parts().trap
    local fire_, frost = t.slots.fire, t.slots.frost
    check(Shown(fire_.iconOff) and not Shown(fire_.fill) and not Shown(frost.fill), "both empty")
    Cast("immolation")
    Tick(0.1)
    check(Shown(fire_.iconX) and Shown(fire_.fill) and not Shown(frost.fill), "the fire slot")
    check(fire_.label.text == "~60", "~60: " .. tostring(fire_.label.text))
    check(fire_.fill.fsW == 40, "a full bar: " .. tostring(fire_.fill.fsW))
    check(Shown(fire_.flash), "a flash on a fresh trap")
    Tick(1)
    Cast("freezing")
    Tick(0.1)
    check(Shown(frost.fill) and frost.label.text == "~60" and fire_.label.text == "~59", "the frost slot, the fire one drains: " .. tostring(fire_.label.text))
    Tick(29)
    check(fire_.label.text == "~30" and fire_.fill.fsW >= 19 and fire_.fill.fsW <= 21, "half a bar: " .. tostring(fire_.fill.fsW) .. " " .. tostring(fire_.label.text))
    Cast("explosive")                              -- the same family replaces the old trap
    Tick(0.1)
    check(fire_.label.text == "~60", "a second fire trap restarts the slot")
    Tick(60.5)
    check(not Shown(fire_.fill) and not Shown(frost.fill) and Shown(fire_.iconOff), "a minute later both are gone")
    NoLog()
""")

case("out_of_combat_the_trap_piece_is_dim_and_a_cast_still_snaps_and_settles", """
    Build()
    local t = Parts().trap
    Tick(0.1)
    check(Shown(t.dim) and Shown(t.open) and not Shown(t.glow) and t.label.text == "", "calm: open, dim, no READY")
    __cd["Freezing Trap"] = true
    Cast("freezing")
    check(Ticking(), "the snap needs the ticker")
    Tick(0.1)
    check(Shown(t.white), "the white snap")
    Tick(1.0)
    check(Shown(t.dark) and t.label.text == "" and not Ticking(), "settled, the ticker stops: " .. tostring(Ticking()))
    check(not Shown(t.slots.frost.fill), "the slots show their calm look")
    NoLog()
""")

case("with_no_trap_learned_the_piece_is_dim_and_says_nothing", """
    Forget("immolation"); Forget("freezing"); Forget("explosive"); Forget("frost")
    Fight()
    local t = Parts().trap
    Tick(0.1)
    check(D.TrapKey() == nil and Shown(t.dim) and t.label.text == "" and not Shown(t.glow))
    NoLog()
""")

case("an_unreadable_weapon_speed_falls_back_to_the_measured_gap_then_the_default", """
    __speed = "secret"
    Fight()
    check(D.Shot().cycle == 2.8 and D.Shot().source == "default", "the default with nothing else")
    Tick(2.0)
    Cast("autoshot")
    local m = D.Shot().measured
    check(m and math.abs(m - 2.0) < 0.05 and D.Shot().cycle == m and D.Shot().source == "measured", "the gap of two shots: " .. tostring(D.Shot().cycle))
    Tick(3.5)
    Cast("autoshot")
    check(D.Shot().measured == m, "a late gap is not the cycle")
    Tick(1.0)
    Cast("raptor")
    Tick(2.0)
    Cast("autoshot")
    check(D.Shot().measured == m, "nor is one a reset cut short")
    NoLog()
""")

case("an_unreadable_range_is_a_calm_scope_that_still_runs_the_clock", """
    Fight()
    local p = Parts()
    __range["Auto Shot"] = "secret"; __range["Raptor Strike"] = "secret"
    Tick(0.3)
    check(D.Range(__now) == nil, "range unreadable")
    check(Shown(p.zones.unlit.ranged) and not Shown(p.skull.body), "dim rings, no skull")
    check(RimCount(KC.free, KC.freeHi) > 0 and Lab():match("^%d%.%d$"), "but the rim and the seconds run: " .. tostring(Lab()))
    __range["Auto Shot"] = true; __range["Raptor Strike"] = false
    __canAttack = false
    Tick(0.3)
    check(D.Range(__now) == nil, "a friendly target has no range")
    __canAttack = true
    NoLog()
""")

case("an_unreadable_cooldown_or_a_missing_timer_shows_the_dark_jaws_with_no_fill", """
    Fight()
    local t = Parts().trap
    Enum.StatusBarTimerDirection = nil
    __cd["Freezing Trap"] = true
    Cast("freezing")
    Tick(0.5)
    check(Shown(t.dark) and not Shown(t.lit), "no timer direction: dark jaws, no fill")
    Enum.StatusBarTimerDirection = { ElapsedTime = 1 }
    NoLog()
""")

case("the_first_shot_after_auto_shot_turns_on_waits_the_wind_up", """
    __combat = true
    Build()
    AutoOn(true)
    Tick(0.1)
    local f = D.Fill(__now)
    check(f > 0.78 and f < 0.95, "the cycle starts with the cast time left: " .. f)
    check(Lab() == "PLANT" or Lab():match("^%d%.%d$"), "label: " .. tostring(Lab()))
    NoLog()
""")

case("only_the_players_own_casts_count", """
    Fight()
    local last = D.Shot().last
    fire("UNIT_SPELLCAST_SUCCEEDED", "target", "guid", CAST.autoshot)
    check(D.Shot().last == last, "a unit event for another unit is not delivered")
    D._OnCast(Secret("id"))
    check(D.Shot().last == last, "a secret spell id is dropped")
    NoLog()
""")

case("on_hide_stops_the_ticker_and_the_subscription_on_show_restarts_and_the_ledger_never_stops", """
    Fight()
    check(Ticking(), "the shot clock ticks")
    SPEC.onHide("lower")
    check(not Ticking(), "the OnUpdate stops on hide")
    Cast("freezing")
    check(D.Traps().frost.up, "a cast while hidden is still recorded")
    check(Parts().trap.slots.frost.label.text ~= "~60", "and nothing is drawn")
    SPEC.onShow("lower")
    check(Ticking(), "the OnUpdate is back on show")
    Tick(0.1)
    check(Parts().trap.slots.frost.label.text == "~60" and Shown(Parts().trap.slots.frost.fill), "the slot shows at once")
    NoLog()
""")

case("the_steady_tick_allocates_nothing_in_every_state", """
    -- under LuaJIT with the JIT off (as hud-harness.py measures): indicative only, the client runs PUC 5.1
    jit.off()
    jit.flush()
    Fight()
    local p = Parts()
    Cast("freezing"); Cast("immolation")
    __cd["Freezing Trap"] = true
    __ammo = 20; fire("BAG_UPDATE_DELAYED")
    local function measure(label)
        for i = 1, 30 do Tick(1 / 30) end
        collectgarbage("stop")
        collectgarbage("collect")
        local before = collectgarbage("count")
        for i = 1, 150 do Tick(1 / 30) end
        local grew = (collectgarbage("count") - before) * 1024 / 150
        collectgarbage("restart")
        check(grew < 64, label .. ": a tick allocated " .. grew .. " bytes on average")
    end
    measure("free to move")
    Tick(1.6)
    __moving = true; Tick(0.8)
    measure("moving, late")
    __moving = false
    Cast("autoshot"); Tick(2.4)
    measure("wind-up")
    __range["Auto Shot"] = false; __near = true
    Tick(4)
    measure("held")
    __range["Auto Shot"] = true
    AutoOn(false); Tick(0.2)
    measure("amber nudge")
    NoLog()
""")


# --- the real GunsightAreas.lua: the target gate -------------------------------------------------------------------------

def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REAL_CASE = r"""
STRICT_EVENTS = false
resetKnownEvents()
resetWorld()
SetScreen(1440)
ForeverSTUwaveDB = nil
FS.IsSecret = function(v) return v == SECRET end
stubTheme_()
stubHud_()
assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
loadAddonFile(CONFIG_SRC, "Core/Config.lua")
loadAddonFile(FRAMEHELPERS_SRC, "Core/FrameHelpers.lua")
loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
TARGET = { exists = true }
UnitExists = function(u) if u == "player" then return true end return u == "target" and TARGET.exists end
loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
UnitClass = function() return "Hunter", "HUNTER" end
UnitGUID = function(u) if u == "player" then return "P" end if u == "target" and TARGET.exists then return "T" end end
UnitName = function(u) return u end
UnitIsUnit = function(a, b) return a == b end
UnitLevel = function() return 12 end
UnitCanAttack = function() return true end
IsPlayerSpell = function(id) return id == 75 or id == 2973 or id == 1499 end
C_Spell = { GetSpellName = function(id) if id == 75 then return "Auto Shot" elseif id == 1499 then return "Freezing Trap" end end,
    GetSpellCooldown = function() return { isActive = false, isOnGCD = false } end,
    IsSpellInRange = function(ref) return ref == "Auto Shot" or ref == 75 end }
CheckInteractDistance = function() return false end
UnitRangedDamage = function() return 2.8 end
GetUnitSpeed = function() return 0 end
GetInventoryItemID = function() return 2504 end
GetItemCount = function() return 180 end
FS.AurasReadable = function() return not IN_COMBAT end
loadAddonFile(DATA_SRC, "Modules/CombatHud/HunterState.lua")
loadAddonFile(HUNTER_SRC, "Modules/CombatHud/GunsightHunter.lua")
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local G = FS.GunsightHunter
check(G.frame and isVisible(G.frame), "the module is built and drawn under the host")
FS.HunterState._OnCast(1499)
FS.HunterState._SetAuto(true)
check(onUpdateFrames() == 1, "ticking with a trap set and Auto Shot on: " .. onUpdateFrames())
local body = G.parts.skull.body
check(isVisible(G.parts.rim.px[1].t), "the rim is drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(G.parts.rim.px[1].t) and not isVisible(G.parts.labels.main),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(G.parts.rim.px[1].t), "a target brings it back")
check(onUpdateFrames() == 1, "and the ticker with it")
for k, v in pairs(DEGRADED) do
    error("degraded " .. k .. ": " .. tostring(v))
end
"""


def run_real_case() -> str | None:
    cls = _load("gunsightclass-harness")
    gs = _load("gunsight-harness")
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(cls.MOCK)
    g = lua.globals()
    g.LAYOUT_SRC = (ADDON / "Core/Layout.lua").read_text(encoding="utf-8")
    g.CONFIG_SRC = (ADDON / "Core/Config.lua").read_text(encoding="utf-8")
    g.FRAMEHELPERS_SRC = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    g.GUNSIGHT_SRC = (ADDON / "Modules/CombatHud/Gunsight.lua").read_text(encoding="utf-8")
    g.AREAS_SRC = (ADDON / "Modules/CombatHud/GunsightAreas.lua").read_text(encoding="utf-8")
    g.DATA_SRC, g.HUNTER_SRC = DATA, MODULE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.DATA_SRC, g.MODULE_SRC = DATA, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


# --- static checks: the files, the cell maps and the geometry the generators bake ---------------------------------------------

TEXTURES = ("hunter_zones", "hunter_rings", "hunter_sprites", "hunter_trap", "hunter_trap_lit")


def tga_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:18]
    return struct.unpack("<HH", head[12:16])


def gen_text(name: str) -> str:
    return (ASSETS / f"generate_hunter_{name}.py").read_text(encoding="utf-8")


def gen_list(src: str, name: str) -> list[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\]", src, re.S)
    return re.findall(r'"(\w+)"', m.group(1)) if m else []


def gen_ints(src: str, pattern: str) -> list[int] | None:
    m = re.search(pattern, src)
    return [int(x) for x in m.groups()] if m else None


def lua_table(src: str, name: str) -> dict[str, int]:
    m = re.search(r"local " + name + r" = \{(.*?)\}", src, re.S)
    return {k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", m.group(1))} if m else {}


def probe_module():
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.DATA_SRC, g.MODULE_SRC = DATA, MODULE
    rt.execute(MOCK)
    return rt.eval("FS.GunsightHunter")


def ring_px(r0: float, r1: float, cx: int = 38, cy: int = 37, edge: float = 35.5):
    """The mockup's ring px (distance measured from the px corner), as (x, y, angle)."""
    out = []
    for y in range(86):
        for x in range(150):
            dx, dy = x - cx, y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if d <= edge and r0 <= d <= r1:
                a = math.atan2(dx, -dy)
                out.append((x, y, a + 2 * math.pi if a < 0 else a, d))
    return out


def static_checks() -> list[str]:
    errs = []
    for name in TEXTURES:
        if not (MEDIA / f"{name}.tga").exists():
            errs.append(f"missing texture {name}.tga (run the tools/assets/generate_hunter_*.py scripts)")
        if f"{name}.tga" not in MODULE:
            errs.append(f"the module does not use {name}.tga")
    for name in set(re.findall(r"hunter_\w+\.tga", MODULE)):
        if name[:-4] not in TEXTURES:
            errs.append(f"the module uses {name}, which this harness does not know")
    scope, traps = gen_text("scope"), gen_text("traps")
    for table, src, glist in (("ZCELL", scope, "ZONE_CELLS"), ("RCELL", scope, "RING_CELLS"), ("SCELL", scope, "SPRITE_CELLS"),
                              ("TCELL", traps, "TRAP_CELLS")):
        cells = {c: i for i, c in enumerate(gen_list(src, glist))}
        lua = lua_table(MODULE, table)
        if not lua:
            errs.append(f"{table}: not found in the module")
        for k, v in lua.items():
            if cells.get(k) != v:
                errs.append(f"{table}.{k} = {v} in the module but {cells.get(k)} in the generator's {glist}")
        if lua and set(lua) != set(cells):
            errs.append(f"{table}: the module and the generator's {glist} do not name the same cells")
    try:
        M = probe_module()
    except LuaError as e:
        return errs + [f"could not load the module for the geometry check: {e}"]
    cx, cy = gen_ints(scope, r"C_X, C_Y = (\d+), (\d+)")
    zox, zoy = gen_ints(scope, r"ZONE_OX, ZONE_OY = (\d+), (\d+)")
    rox, roy = gen_ints(scope, r"RING_OX, RING_OY = (-?\d+), (-?\d+)")
    so = gen_ints(scope, r"SPRITE_O = (\d+)")[0]
    tcx, tcy = gen_ints(traps, r"TC_X, TC_Y = (\d+), (\d+)")
    oox, ooy = gen_ints(traps, r"OPEN_OX, OPEN_OY = (\d+), (\d+)")
    if (int(M["C"]["SCOPE"]["x"]), int(M["C"]["SCOPE"]["y"])) != (cx, cy):
        errs.append("the scope centre drifted from the generators")
    if (int(M["C"]["TRAP"]["x"]), int(M["C"]["TRAP"]["y"])) != (tcx, tcy):
        errs.append("the trap centre drifted from the generator")
    origins = {"zones": (cx - zox, cy - zoy), "rings": (cx - rox, cy - roy), "sprites": (so, so), "trapOpen": (oox, ooy),
               "trapBox": (0, 0), "trapSlot": (0, 0)}
    files = {"zones": "hunter_zones.tga", "rings": "hunter_rings.tga", "sprites": "hunter_sprites.tga", "trapOpen": "hunter_trap.tga",
             "trapBox": "hunter_trap.tga", "trapSlot": "hunter_trap.tga"}
    for key, (ox, oy) in origins.items():
        a = M["A"][key]
        w, h = tga_size(MEDIA / files[key]) if (MEDIA / files[key]).exists() else (0, 0)
        if a["file"] != files[key]:
            errs.append(f"atlas {key}: file {a['file']}, expected {files[key]}")
        if (a["w"], a["h"]) != (w, h):
            errs.append(f"atlas {key}: {a['w']}x{a['h']} in the module, {w}x{h} on disk")
        if (a["ox"], a["oy"]) != (ox, oy):
            errs.append(f"atlas {key}: art point ({a['ox']}, {a['oy']}) in the module, ({ox}, {oy}) in the generator")
        if a["cols"] * a["cw"] > a["w"] or a["bw"] * 2 > a["cw"] or a["bh"] * 2 > a["ch"]:
            errs.append(f"atlas {key}: the cell grid does not fit the file")
    cell_sizes = {"zones": (gen_ints(scope, r"ZONE_CELL = (\d+)")[0],) * 2, "rings": (gen_ints(scope, r"RING_CELL = (\d+)")[0],) * 2,
                  "sprites": (gen_ints(scope, r"SPRITE_CELL = (\d+)")[0],) * 2, "trapOpen": tuple(gen_ints(traps, r"TRAP_CELL = \((\d+), (\d+)\)"))}
    for key, (cw, ch) in cell_sizes.items():
        a = M["A"][key]
        if (a["cw"], a["ch"]) != (cw, ch):
            errs.append(f"atlas {key}: cell {a['cw']}x{a['ch']} in the module, {cw}x{ch} in the generator")
    sbx, sby = tcx - 16, tcy - 5
    sw, sh = gen_ints(traps, r"SHUT_W, SHUT_H = (\d+), (\d+)")
    box = [int(M["C"]["SHUT"][i]) for i in (1, 2, 3, 4)]
    if box != [sbx, sby, sw, sh]:
        errs.append(f"SHUT box {box} in the module, {[sbx, sby, sw, sh]} in the generator")
    if (M["A"]["trapBox"]["bw"], M["A"]["trapBox"]["bh"]) != (sw, sh):
        errs.append("the shut jaws' atlas box drifted from the generator")
    lw, lh = tga_size(MEDIA / "hunter_trap_lit.tga") if (MEDIA / "hunter_trap_lit.tga").exists() else (0, 0)
    lit_w, lit_h = gen_ints(traps, r"LIT_W, LIT_H = (\d+), (\d+)")
    lit_dx, lit_dy = gen_ints(traps, r"LIT_BOX = \(TC_X - (\d+), TC_Y - (\d+)\)")
    lit_box = [tcx - lit_dx, tcy - lit_dy, lit_w, lit_h]
    have = [int(M["C"]["LIT"][i]) for i in (1, 2, 3, 4)]
    if have != lit_box:
        errs.append(f"LIT box {have} in the module, {lit_box} in the generator")
    if (lw, lh) != (lit_w * 2, lit_h * 2):
        errs.append(f"hunter_trap_lit.tga is {lw}x{lh}, the lit box is {lit_w * 2}x{lit_h * 2} texels (a StatusBar crops the file as the box)")
    bw, bh = gen_ints(traps, r"SLOT_BW, SLOT_BH = (\d+), (\d+)")
    if (int(M["C"]["BAR_W"]), int(M["C"]["BAR_H"])) != (bw, bh):
        errs.append("the slot bar size drifted from the generator")
    if (M["A"]["trapSlot"]["bw"], M["A"]["trapSlot"]["bh"]) != (bw + 2, bh + 2):
        errs.append("the slot frame atlas box drifted from the generator")
    # the rim: the module's px ring is the mockup's, and its pools cover every cycle length
    rim = ring_px(float(M["C"]["RIM0"]), float(M["C"]["RIM1"]))
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().DATA_SRC, rt.globals().MODULE_SRC = DATA, MODULE
    rt.execute(MOCK)
    n = rt.eval("(function() SetTarget('hostile'); Build(); return Parts().rim.n end)()")
    if n != len(rim):
        errs.append(f"the rim has {n} px in the module, {len(rim)} in the mockup's geometry")
    marks, ticks, sparks = int(M["C"]["MARKS"]), int(M["C"]["TICKS"]), int(M["C"]["SPARKS"])
    for cycle in [1.0 + 0.1 * i for i in range(0, 61)]:
        pa = 2 * math.pi * (cycle - 0.5) / cycle
        line = sum(1 for (_, _, a, d) in ring_px(29.5, 36.2) if abs(a - pa) < 0.045)
        if line > marks:
            errs.append(f"the plant line of a {cycle:.1f} s cycle needs {line} px, the pool has {marks}")
            break
    for cycle in [1.0 + 0.1 * i for i in range(0, 61)]:
        outer = [(a) for (_, _, a, d) in ring_px(34.2001, 35.1999)]
        count = sum(1 for a in outer if any(abs(a - 2 * math.pi * k / cycle) < 0.03 for k in range(1, math.ceil(cycle))))
        if count > ticks:
            errs.append(f"the ticks of a {cycle:.1f} s cycle need {count} px, the pool has {ticks}")
            break
    spark = sorted(a for (_, _, a, d) in ring_px(float(M["C"]["RIM0"]) - 0.5, float(M["C"]["RIM1"]) + 0.5))
    worst = max(sum(1 for a in spark if abs(a - A) < 0.05) for A in [i * 0.01 for i in range(1, 628)])
    if worst > sparks:
        errs.append(f"the spark covers up to {worst} px, the pool has {sparks}")
    for path in ("Modules/CombatHud/HunterState.lua", "Modules/CombatHud/GunsightHunter.lua"):
        src = (ADDON / path).read_text(encoding="utf-8")
        if re.search("[\u2013\u2014]", src):
            errs.append(f"{path}: an em or en dash")
        if re.search(r"\b(bots?|automat\w*)\b", src, re.I):
            errs.append(f"{path}: flagged wording")
        if re.search("Park" + "er", src):         # assembled from pieces, as private-name-gate.py does, so this file never holds the name
            errs.append(f"{path}: a private name")
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        a, d, m = (toc.index(f"Modules/CombatHud/{n}.lua") for n in ("GunsightAreas", "HunterState", "GunsightHunter"))
        if not (a < d < m):
            errs.append("toc order: GunsightAreas, HunterState, GunsightHunter")
    except ValueError as e:
        errs.append(f"toc: {e}")
    return errs


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
    err = run_real_case()
    name = "under_the_real_areas_the_host_follows_the_target_and_the_module_stops_with_it"
    if err is None:
        print(f"ok    {name}")
    else:
        failures += 1
        print(f"FAIL  {name}: {err}")
    total = len(CASES) + 1
    print(f"{total - min(failures, total)}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
