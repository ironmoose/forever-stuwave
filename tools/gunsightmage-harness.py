#!/usr/bin/env python3
"""Runs the real MageState.lua and GunsightMage.lua headless against a mock client.

The Mage Class Module draws the design mockup "Mage Gunsight Module" (2026-11-07): the spec piece (Frost snowflake with the
Fingers of Frost crystals, the Arcane sigil with its four gems, or the Fire flame with its Kaun rune), the Ice Lance spike or
the Fire Blast comet under it, and the ward (Ice Barrier, else Mana Shield). These checks pin:

  * the spec pick from the talents (and the Frost fallback with no talent API), and that only that piece shows;
  * secrets: the absorb only ever reaches StatusBar:SetMinMaxValues / SetValue, SetAlpha (the light's gate) and
    AbbreviateNumbers -> SetFormattedText; any compare, arithmetic or concat on it throws (a throw in a paint is logged and fails
    the case); no aura is read under combat lockdown; SetCooldown is only ever fed plain numbers;
  * the ward: Ice Barrier over Mana Shield, the locked L20 look, the own cast stamping the 60 s ledger, the pink buff ring, the
    mark caught from the absorb ping, the hit flash and shake, the break shards, the amber nudge in combat only;
  * Frost Nova: the cooldown refill is the engine's timer, the Frozen window drains with a "~" label;
  * Fingers of Frost: the glow event, the Frostbolt-then-aura window, spending casts, the plain aura read correcting it,
    hidden without talents;
  * Arcane: gems and eye by stacks, an 18 s ring that is never refreshed, the amber last seconds, the shatter at expiry, the
    cost number, Clearcasting from a free Blast;
  * Fire: the flame by Fire Vulnerability stacks, the 30 s ring each Scorch refills, the embers, the plain read correcting it;
  * the marks: the spike (Ice Lance) or the comet (Fire Blast), by spec and what is learned, their engine refill and flash;
  * onHide stops the ticker and the subscription (the ledger keeps listening), onShow brings them back; the ticker stops when
    nothing moves; a steady tick allocates nothing;
  * under the REAL GunsightAreas.lua the host hides with no target, the module stops, and it comes back with a target;
  * the baked textures exist, and the module's cell maps, atlas geometry and boxes match the generators.

    python3 tools/gunsightmage-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
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
DATA = (ADDON / "Modules/CombatHud/MageState.lua").read_text(encoding="utf-8")
MODULE = (ADDON / "Modules/CombatHud/GunsightMage.lua").read_text(encoding="utf-8")
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
function Obj:SetFormattedText(fmt, v)
    self.formatted = v
    if IsSecretValue(v) then self.text = nil; self.secretFed = true; return end
    self.secretFed = false
    self.text = string.format(fmt, v)
end
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
function Obj:GetStatusBarTexture() return self.fill end
function Obj:SetTimerDuration(obj, interp, dir) self.timer = { obj = obj, interp = interp, dir = dir } end
function Obj:SetClipsChildren(on) self.clips = on end
-- Cooldown
function Obj:SetCooldown(start, dur)
    check(not IsSecretValue(start) and not IsSecretValue(dur), "SetCooldown refuses a secret from addon code")
    self.cd = { start, dur }
end
function Obj:SetSwipeTexture(p) self.swipe = p end
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
__units = { player = { guid = "P", name = "Stu", friend = true, class = "MAGE" } }
function UnitExists(u) return __units[u] ~= nil end
function UnitGUID(u) return __units[u] and __units[u].guid end
function UnitIsUnit(a, b) return __units[a] ~= nil and __units[b] ~= nil and __units[a].guid == __units[b].guid end
__level = 70
function UnitLevel() return __level end
function SetTarget(kind)
    if kind == nil then __units.target = nil; return end
    __units.target = { guid = "T", name = "Boar", friend = kind == "friend", hostile = kind == "hostile" }
end

ABSORBS = {}
function UnitGetTotalAbsorbs(u) ABSORBS[u] = ABSORBS[u] or Secret("absorb " .. u); return ABSORBS[u] end
ABBREV_FED = 0
ABBREV = Secret("abbrev")
function AbbreviateNumbers(v) if IsSecretValue(v) then ABBREV_FED = ABBREV_FED + 1 end return ABBREV end

-- the talents: points in the Arcane, Fire and Frost tabs
__tabs = { names = { "Arcane", "Fire", "Frost" }, pts = { 0, 0, 31 } }
function Tabs(a, f, fr, names) __tabs.pts = { a, f, fr }; if names then __tabs.names = names end end
function GetTalentTabInfo(i) return __tabs.names[i], "icon", __tabs.pts[i] end

-- spells: every id of a spell answers to its name; IsPlayerSpell says what the Mage has learned
CAST = { nova = 122, lance = 30455, fireblast = 2136, frostbolt = 116, arcaneblast = 30451, scorch = 2948, icebarrier = 11426,
    manashield = 1463 }
__known, __names, __byname = {}, {}, {}
function IsPlayerSpell(id) return __known[id] == true end
function Forget(key) __known[CAST[key]] = nil end
__cd = {}                -- spell name -> true while its own cooldown runs
local CD_ON = { isActive = true, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
local CD_OFF = { isActive = false, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
__cost = 335
local COSTS = { { type = 0, cost = 335 } }
Enum = { StatusBarTimerDirection = { ElapsedTime = 1, RemainingTime = 0 }, StatusBarInterpolation = { Immediate = 0 },
    PowerType = { Mana = 0 } }
C_Spell = {
    GetSpellName = function(id) return __names[id] end,
    GetSpellInfo = function(name) local id = __byname[name]; return id and { spellID = id, name = name } or nil end,
    GetSpellCooldown = function(id)
        local n = type(id) == "number" and __names[id] or id
        return __cd[n] == true and CD_ON or CD_OFF      -- the client allocates its own; the mock does not, so the tick's is ours
    end,
    GetSpellCooldownDuration = function(id) return { durationOf = id } end,
    GetSpellPowerCost = function() COSTS[1].cost = __cost; return COSTS end,
}
-- auras: unit -> name -> aura table (plain); any read under lockdown is a refusal and is recorded
__auras, AURA_IN_COMBAT = {}, 0
C_UnitAuras = {
    GetAuraDataBySpellName = function(unit, name)
        if __combat then AURA_IN_COMBAT = AURA_IN_COMBAT + 1; error("Auras cannot be accessed when secret") end
        return __auras[unit] and __auras[unit][name]
    end,
}
function Aura(unit, name, fields) __auras[unit] = __auras[unit] or {}; __auras[unit][name] = fields end

__logged = {}
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
FS = {
    IsSecret = IsSecretValue,
    AurasReadable = function() return not __combat end,
    Gunsight = { ui = function(px) return px end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    Theme = { ApplyMono = function(fs, size) fs.size = size end },
    LogDegradeOnce = function(k, m) __logged[k] = m end,
}
assert(loadstring(DATA_SRC, "@MageState.lua"))("forever-stuwave", FS)
D = FS.MageState
for _, d in pairs(D.DEFS) do for _, id in ipairs(d.ids) do __names[id] = d.name end end
for key, id in pairs(CAST) do
    __names[id] = D.DEFS[key].name
    __byname[D.DEFS[key].name] = id
    __known[id] = true
end
assert(loadstring(MODULE_SRC, "@GunsightMage.lua"))("forever-stuwave", FS)
M = FS.GunsightMage
SPEC = Areas.specs[1].spec
CELL = M.CELL
ELAPSED = Enum.StatusBarTimerDirection.ElapsedTime
SetTarget("hostile")
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function Parts() return M.parts end
function Tick(dt)
    __now = __now + dt
    local f = M.frame.scripts.OnUpdate
    if f then f(M.frame, dt) end
end
function Ticking() return M.frame.scripts.OnUpdate ~= nil end
function Cast(key) fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", CAST[key]) end
function Ping(unit) fire("UNIT_ABSORB_AMOUNT_CHANGED", unit) end
function NoLog()
    for k, v in pairs(__logged) do error("logged " .. k .. ": " .. tostring(v), 2) end
end
function Shown(t) return t.shown ~= false and visible(t) end
function Distinct(fn, steps, dt)
    local seen, n = {}, 0
    for i = 1, steps do Tick(dt); local v = fn(); if not seen[v] then seen[v] = true; n = n + 1 end end
    return n
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_mages_only", """
    check(SPEC and SPEC.classes[1] == "MAGE" and #SPEC.classes == 1)
    local m = Build()
    check(m and m.name == "ForeverSTUwaveGunsightMage")
    NoLog()
""")

case("the_spec_piece_follows_the_talents", """
    Tabs(31, 0, 0)
    Build()
    local p = Parts()
    check(D.Spec() == "ARCANE" and D.Talented())
    check(Shown(p.arcane.root) and not Shown(p.frost.root) and not Shown(p.fire.root), "only the Arcane piece")
    Tabs(0, 31, 0); fire("PLAYER_TALENT_UPDATE")
    check(D.Spec() == "FIRE" and Shown(p.fire.root) and not Shown(p.arcane.root), "Fire after a respec")
    Tabs(0, 0, 31); fire("PLAYER_TALENT_UPDATE")
    check(D.Spec() == "FROST" and Shown(p.frost.root) and not Shown(p.fire.root), "and Frost")
    Tabs(20, 0, 0, { "Frost", "Arcane", "Fire" }); fire("PLAYER_TALENT_UPDATE")
    check(D.Spec() == "FROST", "the tab's name wins over its place: " .. D.Spec())
    NoLog()
""")

case("with_no_talent_api_it_is_frost_without_fingers", """
    GetTalentTabInfo = nil
    Build()
    local p = Parts()
    check(D.Spec() == "FROST" and not D.Talented(), "the fallback")
    check(Shown(p.frost.root) and not Shown(p.frost.fingers[1].crystal) and not Shown(p.frost.fingers[2].crystal),
        "no crystals without talents")
    __level = 5
    Tabs(3, 0, 0); GetTalentTabInfo = function(i) return __tabs.names[i], "icon", __tabs.pts[i] end
    fire("PLAYER_LEVEL_UP")
    check(not D.Talented(), "below level 10 there are no talents to count")
    NoLog()
""")

case("the_absorb_reaches_only_the_engine_setters", """
    Build()
    local W = Parts().ward
    check(IsSecretValue(W.iceBar.value), "the light's value is the secret absorb")
    check(IsSecretValue(W.iceBar.max), "with no mark the max is the absorb itself (full)")
    check(IsSecretValue(W.iceGate.alpha), "the gate's alpha is the secret absorb")
    check(ABBREV_FED > 0 and W.iceLabel.secretFed, "the number goes through AbbreviateNumbers to SetFormattedText")
    check(W.manaGate.alpha == 0 and W.mistBar.value == 0, "the Mana Shield side stays shut")
    Tick(0.05)
    NoLog()
""")

case("ice_barrier_wins_over_mana_shield_and_mana_shield_alone_takes_its_place", """
    Build()
    local W = Parts().ward
    check(D.WardKind() == "barrier" and Shown(W.ice) and not Shown(W.mana) and not Shown(W.locked), "both known: Ice Barrier")
    Forget("icebarrier"); fire("SPELLS_CHANGED")
    check(D.WardKind() == "mana" and Shown(W.mana) and not Shown(W.ice), "Mana Shield alone")
    check(IsSecretValue(W.mistBar.value) and IsSecretValue(W.manaGate.alpha) and W.iceGate.alpha == 0, "the mist is fed, the ice is shut")
    check(W.iceBar.value == 0, "and the empty bar is empty")
    check(W.manaLabel.secretFed, "its number")
    Forget("manashield"); fire("SPELLS_CHANGED")
    check(D.WardKind() == nil and Shown(W.locked) and W.lockLabel.text == "L20", "neither: the dotted oval and L20")
    check(not Shown(W.ice) and not Shown(W.mana))
    NoLog()
""")

case("an_own_ice_barrier_cast_stamps_the_ledger_the_buff_ring_and_the_mark", """
    Build()
    __combat = true
    Cast("icebarrier")
    local w = D.Ward()
    check(w.up and w.est and w.kind == "barrier" and w.expires == __now + 60, "the 60 s ledger, an estimate")
    check(D.Buff().expires == __now + 60, "the pink buff ring is a ledger of the cast")
    check(IsSecretValue(D.Mark()), "the mark is the absorb caught at the cast")
    Tick(0.05)
    local W = Parts().ward
    check(Shown(W.buffRing.cd) and W.buffRing.cd.cd[1] == 1000 and W.buffRing.cd.cd[2] == 60, "SetCooldown(cast, 60), plain")
    check(Shown(W.buffDark) and not Shown(W.buffDash), "the ring track, not the dashes")
    check(IsSecretValue(W.iceBar.max), "the lit bar's max is the mark")
    check(AURA_IN_COMBAT == 0, "no aura read in combat")
    NoLog()
""")

case("a_hit_flashes_and_shakes_the_ward_and_only_its_own_pings_count", """
    Build()
    __combat = true
    Cast("icebarrier")
    RunTimers()
    Tick(1)
    local W = Parts().ward
    Ping("party1")
    Tick(0.02)
    check(not Shown(W.flashIce), "another unit's ping is not delivered")
    Ping("player")
    Tick(0.02)
    check(Shown(W.flashIce), "the flash")
    check(W.root.fsX == 1 or W.root.fsX == -1, "the shake")
    Tick(0.3)
    check(not Shown(W.flashIce) and W.root.fsX == 0, "both settle")
    NoLog()
""")

case("a_ward_lost_early_out_of_combat_breaks_and_the_buff_time_takes_the_label", """
    Aura("player", "Ice Barrier", { expirationTime = __now + 40 })
    Build()
    Cast("icebarrier")
    RunTimers()
    check(D.Ward().up and not D.Ward().est, "the aura confirms the cast")
    Aura("player", "Ice Barrier", nil)
    fire("UNIT_AURA", "player", {})
    Tick(0.1)
    local W = Parts().ward
    check(not D.Ward().up, "gone")
    check(Shown(W.shards[1].big), "the shards fly")
    check(Shown(W.buffLabel) and W.buffLabel.text:sub(1, 1) == "~", "the pink buff time is a ledger, so it has a ~: " .. tostring(W.buffLabel.text))
    Tick(1)
    check(not Shown(W.shards[1].big), "and settle")
    NoLog()
""")

case("the_empty_ice_barrier_nudges_amber_in_combat_and_is_calm_and_still_out_of_it", """
    Tabs(31, 0, 0)          -- Arcane with no stacks: nothing else moves
    Build()
    local W = Parts().ward
    Tick(0.05)
    check(not Shown(W.spikeNudge) and Shown(W.spikeDark), "calm: dark spikes")
    check(not Ticking(), "calm: nothing moves, no ticker")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    check(Ticking(), "the nudge pulses")
    check(Shown(W.spikeNudge) and not Shown(W.spikeDark) and W.spikeNudge.color[1] == 1 and W.spikeNudge.color[2] > 0.6, "amber")
    local n = Distinct(function() return W.spikeNudge.color[4] end, 45, 1 / 30)
    check(n >= 4, "it breathes: " .. n)
    __cd["Ice Barrier"] = true; fire("SPELL_UPDATE_COOLDOWN")
    check(Shown(W.edgeCd) and not Shown(W.spikeNudge), "while the 30 s cooldown runs there is no nudge")
    check(Shown(W.cdBar) and W.cdBar.timer and W.cdBar.timer.dir == ELAPSED, "the refill is the engine's elapsed timer")
    __cd["Ice Barrier"] = nil; __combat = false; fire("PLAYER_REGEN_ENABLED")
    check(not Shown(W.spikeNudge) and not Shown(W.cdBar), "back to calm")
    NoLog()
""")

case("mana_shield_breathes_through_its_vapour_and_core", """
    Forget("icebarrier")
    Build()
    local W = Parts().ward
    check(D.WardKind() == "mana" and Ticking(), "the mist moves")
    local n = Distinct(function() return W.vapour.fsCell end, 20, 0.1)
    check(n >= 3, "the vapour flipbook turns: " .. n)
    check(Shown(W.manaTop) and Shown(W.core) and Shown(W.glyphLit[1]), "core and glyphs sit under the gate")
    local m = Distinct(function() return W.core.alpha end, 30, 0.1)
    check(m >= 4, "the core pulses: " .. m)
    NoLog()
""")

case("frost_nova_refills_on_the_engines_timer_and_the_frozen_window_drains", """
    Build()
    local F = Parts().frost
    check(Shown(F.flake) and F.flake.fsCell == CELL.frost.flakeReady and Shown(F.tip), "ready and twinkling")
    check(not Shown(F.bar) and not Shown(F.crust), "no refill, no crust")
    Cast("nova")
    local fz = D.Frozen()
    check(fz.up and fz.est and fz.expires == __now + 8, "the Frozen window is 8 s from the own cast, an estimate")
    __cd["Frost Nova"] = true; fire("SPELL_UPDATE_COOLDOWN")
    Tick(0.05)
    check(F.flake.fsCell == CELL.frost.flakeOff and not Shown(F.tip), "dark while the cooldown runs")
    check(Shown(F.bar) and F.bar.timer and F.bar.timer.dir == ELAPSED, "the fill is the engine's elapsed timer")
    check(Shown(F.crust) and F.crust.cd[1] == 1000 and F.crust.cd[2] == 8, "the crust swipe from plain numbers")
    check(F.label.text == "~8s" and Shown(F.flash) and Shown(F.nova), "the label, the flash and the burst: " .. tostring(F.label.text))
    Tick(1)
    check(not Shown(F.nova) and not Shown(F.flash) and F.label.text == "~7s", "the burst settles, the label counts: " .. tostring(F.label.text))
    __cd["Frost Nova"] = nil; fire("SPELL_UPDATE_COOLDOWN")
    Tick(7)
    check(not Shown(F.crust) and F.label.text == "" and Shown(F.crustIdle), "the window ends")
    check(F.flake.fsCell == CELL.frost.flakeReady and not Shown(F.bar), "ready again")
    NoLog()
""")

case("a_client_without_the_elapsed_timer_shows_the_dark_look_and_no_fill", """
    Enum.StatusBarTimerDirection = nil
    __cd["Frost Nova"] = true
    Build()
    local F = Parts().frost
    Tick(0.05)
    check(F.flake.fsCell == CELL.frost.flakeOff and not Shown(F.bar), "dark, no fill")
    NoLog()
""")

case("fingers_of_frost_from_the_glow_then_spent_by_casts_and_corrected_by_a_plain_read", """
    Build()
    local F = Parts().frost
    __combat = true
    fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", CAST.lance)
    local fo = D.Fingers()
    check(fo.n == 2 and fo.est and fo.expires == __now + 15, "two charges, 15 s, a guess in combat")
    Tick(0.05)
    check(F.fingers[1].crystal.fsCell == CELL.fingers.on and F.fingers[2].crystal.fsCell == CELL.fingers.on, "both lit")
    check(Shown(F.fingers[1].glow) and Shown(F.fingerMark) and F.fingerMark.text == "~", "the ~ marks the guess")
    Cast("lance")
    Tick(0.05)
    check(D.Fingers().n == 1 and F.fingers[2].crystal.fsCell == CELL.fingers.off and not Shown(F.fingers[2].glow), "one spent")
    Cast("fireblast")
    check(D.Fingers().n == 0, "Fire Blast spends one too")
    Tick(0.05)
    check(not Shown(F.fingerMark), "no mark with none")
    fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", CAST.lance)
    fire("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", CAST.lance)
    check(D.Fingers().n == 0, "the glow going away clears it")
    check(AURA_IN_COMBAT == 0, "no aura read in combat")
    __combat = false
    Aura("player", "Fingers of Frost", { applications = 1, expirationTime = __now + 10 })
    fire("UNIT_AURA", "player", {})
    fo = D.Fingers()
    check(fo.n == 1 and not fo.est and fo.expires == __now + 10, "out of combat the aura is the truth")
    Tick(0.05)
    check(not Shown(F.fingerMark), "and the ~ goes")
    NoLog()
""")

case("a_frostbolt_then_a_player_aura_change_is_the_other_fingers_signal", """
    Build()
    __combat = true
    Cast("frostbolt")
    Tick(0.5)
    fire("UNIT_AURA", "player", { addedAuras = { 1 } })
    check(D.Fingers().n == 2 and D.Fingers().est, "the proc landed")
    Cast("frostbolt")
    check(D.Fingers().n == 1, "a Frostbolt spends one")
    __now = __now + 5
    fire("UNIT_AURA", "player", { addedAuras = { 1 } })
    check(D.Fingers().n == 1, "an aura change long after a cast is no signal")
    __now = __now + 30
    Tick(0.05)
    check(D.Fingers().n == 0, "the 15 s run out")
    NoLog()
""")

case("the_marks_by_spec_the_spike_for_frost_and_the_comet_for_fire", """
    Build()
    local M_ = Parts().marks
    check(D.MarkKind() == "lance" and Shown(M_.spikeRoot) and not Shown(M_.cometRoot), "Frost with Ice Lance: the spike")
    check(M_.spike.fsCell == CELL.spike.ready and not Shown(M_.spikeBar))
    Cast("lance")
    Tick(0.05)
    check(Shown(M_.spikeFlash), "the cast flash")
    __cd["Ice Lance"] = true; fire("SPELL_UPDATE_COOLDOWN")
    check(M_.spike.fsCell == CELL.spike.off and Shown(M_.spikeBar) and M_.spikeBar.timer.dir == ELAPSED, "dark, refilling")
    __cd["Ice Lance"] = nil; fire("SPELL_UPDATE_COOLDOWN")
    Cast("nova")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    Tick(0.1)
    check(Shown(M_.flare[1]) and Shown(M_.flare[3]), "it shines for a Frozen target in combat")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(not Shown(M_.flare[1]), "and not out of combat")
    Forget("lance"); fire("SPELLS_CHANGED")
    check(D.MarkKind() == "comet" and Shown(M_.cometRoot) and not Shown(M_.spikeRoot), "Frost without Ice Lance: the comet")
    check(M_.comet.fsX == 10, "tucked 6 px left under the Frost piece: " .. tostring(M_.comet.fsX))
    NoLog()
""")

case("the_comet_under_fire_runs_its_loop_and_refills_on_the_engines_timer", """
    Tabs(0, 31, 0)
    Build()
    local M_ = Parts().marks
    check(D.MarkKind() == "comet" and Shown(M_.cometRoot) and M_.comet.fsX == 16, "Fire: the comet at the main piece")
    local n = Distinct(function() return M_.comet.fsCell end, 24, 1 / 12)
    check(n >= 20, "the 24 frame loop plays: " .. n)
    __cd["Fire Blast"] = true; fire("SPELL_UPDATE_COOLDOWN")
    Tick(0.05)
    check(M_.comet.fsCell == CELL.comet.off and Shown(M_.cometBar) and M_.cometBar.timer.dir == ELAPSED, "dark and refilling")
    Cast("fireblast")
    Tick(0.02)
    check(Shown(M_.cometFlash), "the flash")
    NoLog()
""")

case("arcane_has_no_mark", """
    Tabs(31, 0, 0)
    Build()
    local M_ = Parts().marks
    check(D.MarkKind() == nil and not Shown(M_.spikeRoot) and not Shown(M_.cometRoot))
    NoLog()
""")

case("arcane_blast_stacks_fill_gems_the_eye_and_an_18_s_ring_that_never_refreshes", """
    Tabs(31, 0, 0)
    Build()
    local R = Parts().arcane
    check(R.eye.fsCell == CELL.arcane.eyeShut and not Ticking(), "shut and calm at 0 stacks")
    check(R.cost.text == "335", "the next Blast's cost is the only number: " .. tostring(R.cost.text))
    Cast("arcaneblast")
    local a = D.Arcane()
    check(a.stacks == 1 and a.est and a.expires == __now + 18, "18 s from the first Blast, an estimate")
    Tick(0.05)
    check(R.eye.fsCell == CELL.arcane.eyeOpen, "open at 1 to 3")
    check(R.gems[1].base.fsCell == CELL.gems.on and R.gems[2].base.fsCell == CELL.gems.off, "one gem")
    check(R.ring.cd.cd[1] == 1000 and R.ring.cd.cd[2] == 18, "the ring swipe from plain numbers")
    check(R.label.text == "~18s", tostring(R.label.text))
    check(Shown(R.gems[1].pop) and Shown(R.gems[1].flare), "the pop")
    Tick(0.5)
    check(not Shown(R.gems[1].pop), "and it settles")
    local exp = a.expires
    for _ = 1, 3 do Cast("arcaneblast") end
    check(a.stacks == 4 and a.expires == exp, "four stacks, same expiry")
    Cast("arcaneblast")
    check(a.stacks == 4 and a.expires == exp, "a fifth Blast neither adds nor refreshes")
    Tick(0.05)
    check(R.eye.fsCell == CELL.arcane.eyeFull and Shown(R.pupil) and Shown(R.tip), "blazing at 4")
    check(R.gems[4].base.fsCell == CELL.gems.on, "all four gems")
    Tick(14)
    check(Shown(R.ring.low) and not Shown(R.ring.cd), "the last seconds go amber")
    check(R.label.tcolor[1] == 1 and R.label.tcolor[2] > 0.65 and R.label.tcolor[3] < 0.4, "amber label")
    Tick(4)
    check(a.stacks == 0 and Shown(R.shatter[1].big), "they run out with a shatter")
    check(R.eye.fsCell == CELL.arcane.eyeShut and R.label.text == "", "shut again")
    Tick(1)
    check(not Shown(R.shatter[1].big), "and it settles")
    NoLog()
""")

case("arcane_stacks_are_read_back_out_of_combat", """
    Tabs(31, 0, 0)
    Build()
    local R = Parts().arcane
    Aura("player", "Arcane Blast", { applications = 3, expirationTime = __now + 12 })
    fire("UNIT_AURA", "player", {})
    local a = D.Arcane()
    check(a.stacks == 3 and not a.est and a.expires == __now + 12, "the aura is the truth out of combat")
    Tick(0.05)
    check(R.label.text == "12s", "no ~: " .. tostring(R.label.text))
    NoLog()
""")

case("clearcasting_is_a_free_blast_in_combat_and_the_aura_out_of_it", """
    Tabs(31, 0, 0)
    Build()
    local R = Parts().arcane
    check(not Shown(R.ccCore))
    __combat = true
    __cost = 0
    D.RefreshCost()
    local cc = D.Clearcasting()
    check(cc.up and cc.est, "a Blast that costs nothing: Clearcasting, a guess")
    Tick(0.05)
    check(Shown(R.ccCore) and Shown(R.ccArms) and R.cost.text == "0", "the spark")
    Cast("arcaneblast")
    __cost = 335
    D.RefreshCost()
    check(not D.Clearcasting().up, "the next cast spends it")
    Tick(0.05)
    check(not Shown(R.ccCore), "the spark goes")
    fire("UNIT_AURA", "player", { addedAuras = { 1 } })
    check(not D.Clearcasting().up, "an Arcane Blast's own aura change is no Clearcasting signal")
    __combat = false
    Aura("player", "Clearcasting", { expirationTime = __now + 12 })
    fire("UNIT_AURA", "player", {})
    check(D.Clearcasting().up and not D.Clearcasting().est, "out of combat the aura is the truth")
    NoLog()
""")

case("the_blast_cost_turns_hot_when_it_climbs", """
    Tabs(31, 0, 0)
    Build()
    local R = Parts().arcane
    Cast("arcaneblast")
    Tick(0.05)
    check(R.cost.tcolor[3] > 0.9 and R.cost.tcolor[2] > 0.65, "cool: lavender " .. R.cost.tcolor[2])
    __cost = 800
    D.RefreshCost()
    Tick(0.05)
    check(R.cost.text == "800" and R.cost.tcolor[1] > 0.9 and R.cost.tcolor[2] < 0.6, "hot: pink")
    NoLog()
""")

case("fire_vulnerability_grows_the_flame_the_ring_and_the_embers", """
    Tabs(0, 31, 0)
    Build()
    local Fi = Parts().fire
    check(Fi.flame.fsCell < 12 and Fi.label.text == "", "an empty flame at 0")
    Cast("scorch"); Cast("scorch")
    local f = D.Fire()
    check(f.stacks == 2 and f.est and f.expires == __now + 30, "2 stacks, 30 s from the last Scorch")
    Tick(0.05)
    check(Fi.flame.fsCell >= 24 and Fi.flame.fsCell < 36, "the stack 2 frames: " .. Fi.flame.fsCell)
    check(Fi.embers[2].socket.fsCell == CELL.fire.emberOn and Fi.embers[3].socket.fsCell == CELL.fire.emberOff, "two embers")
    check(Fi.ring.cd.cd[1] == 1000 and Fi.ring.cd.cd[2] == 30, "the 30 s ring")
    check(Fi.label.text == "~30s", tostring(Fi.label.text))
    check(Fi.rune.color[1] == 1 and Fi.rune.color[2] == 1, "the rune flares white on the pop")
    Tick(1)
    check(Fi.rune.color[1] < 0.3, "and settles dark")
    Tick(10)
    Cast("scorch")
    check(f.expires == __now + 30, "each Scorch refills the ring")
    for _ = 1, 4 do Cast("scorch") end
    check(f.stacks == 5, "capped at 5")
    Tick(0.05)
    check(Fi.flame.fsCell >= 60 and Fi.embers[5].socket.fsCell == CELL.fire.emberOn, "the biggest flame, five embers")
    NoLog()
""")

case("fire_vulnerability_is_read_back_from_the_target_out_of_combat", """
    Tabs(0, 31, 0)
    Build()
    local Fi = Parts().fire
    Aura("target", "Fire Vulnerability", { applications = 3, expirationTime = __now + 20 })
    fire("PLAYER_TARGET_CHANGED")
    local f = D.Fire()
    check(f.stacks == 3 and not f.est and f.expires == __now + 20, "the debuff is the truth out of combat")
    check(Fi.label.text == "20s", tostring(Fi.label.text))
    NoLog()
""")

case("on_hide_stops_the_ticker_and_the_subscription_on_show_restarts_and_the_ledger_never_stops", """
    Build()
    local F = Parts().frost
    check(Ticking(), "a ready Nova twinkles")
    SPEC.onHide("lower")
    check(not Ticking(), "the OnUpdate stops on hide")
    Cast("nova")
    check(D.Frozen().up, "a cast while hidden is still recorded")
    check(F.label.text == "", "and nothing is drawn")
    SPEC.onShow("lower")
    check(Ticking(), "the OnUpdate is back on show")
    check(F.label.text == "~8s" and Shown(F.crust), "the window shows at once")
    NoLog()
""")

case("the_steady_tick_allocates_nothing", """
    -- under LuaJIT with the JIT off (as hud-harness.py measures): indicative only, the client runs PUC 5.1
    jit.off()
    jit.flush()
    Build()
    __combat = true
    Cast("icebarrier"); Cast("nova")
    fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", CAST.lance)
    __cd["Ice Lance"] = true; fire("SPELL_UPDATE_COOLDOWN")
    for i = 1, 30 do Tick(1 / 30) end
    collectgarbage("stop")
    collectgarbage("collect")
    local before = collectgarbage("count")
    for i = 1, 300 do Tick(1 / 30) end
    local grew = (collectgarbage("count") - before) * 1024 / 300
    collectgarbage("restart")
    check(grew < 64, "a tick allocated " .. grew .. " bytes on average")
    NoLog()
""")

case("the_steady_tick_allocates_nothing_for_arcane_and_fire_either", """
    jit.off()
    jit.flush()
    for _, tabs in ipairs({ { 31, 0, 0 }, { 0, 31, 0 } }) do
        Tabs(tabs[1], tabs[2], tabs[3])
        if M.frame then fire("PLAYER_TALENT_UPDATE") else Build() end
        __combat = true
        for _ = 1, 4 do Cast("arcaneblast"); Cast("scorch") end
        Cast("manashield")
        for i = 1, 30 do Tick(1 / 30) end
        collectgarbage("stop")
        collectgarbage("collect")
        local before = collectgarbage("count")
        for i = 1, 300 do Tick(1 / 30) end
        local grew = (collectgarbage("count") - before) * 1024 / 300
        collectgarbage("restart")
        check(grew < 64, D.Spec() .. ": a tick allocated " .. grew .. " bytes on average")
    end
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
UnitClass = function() return "Mage", "MAGE" end
UnitGUID = function(u) if u == "player" then return "P" end if u == "target" and TARGET.exists then return "T" end end
UnitName = function(u) return u end
UnitIsUnit = function(a, b) return a == b end
UnitLevel = function() return 70 end
UnitGetTotalAbsorbs = function() return SECRET end
AbbreviateNumbers = function() return "154" end
IsPlayerSpell = function(id) return id == 11426 or id == 122 end
C_Spell = { GetSpellName = function(id) if id == 11426 then return "Ice Barrier" elseif id == 122 then return "Frost Nova" end end,
    GetSpellCooldown = function() return { isActive = false, isOnGCD = false } end }
C_UnitAuras = { GetAuraDataBySpellName = function() return nil end }
FS.AurasReadable = function() return not IN_COMBAT end
loadAddonFile(DATA_SRC, "Modules/CombatHud/MageState.lua")
loadAddonFile(MAGE_SRC, "Modules/CombatHud/GunsightMage.lua")
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local G = FS.GunsightMage
check(G.frame and isVisible(G.frame), "the module is built and drawn under the host")
FS.MageState._OnCast(122)
check(onUpdateFrames() == 1, "ticking with a freeze going: " .. onUpdateFrames())
local flake = G.parts.frost.flake
check(isVisible(flake), "the snowflake is drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(flake) and not isVisible(G.parts.ward.iceLabel),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(flake), "a target brings it back")
check(onUpdateFrames() == 1, "and the ticker with it")
for k, v in pairs(DEGRADED) do
    -- the class harness's frames cannot clip children: the module logs once and falls back to the whole oval
    if k ~= "gunsightmage_noclip" then error("degraded " .. k .. ": " .. tostring(v)) end
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
    g.DATA_SRC, g.MAGE_SRC = DATA, MODULE
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

TEXTURES = ("mage_frost", "mage_frost_glint", "mage_flake_mid", "mage_crust_swipe", "mage_fingers", "mage_spike", "mage_spike_mid",
            "mage_comet", "mage_comet_mid", "mage_arcane", "mage_arcane_gems", "mage_arcane_ring", "mage_arcane_ring_low",
            "mage_fire_flame", "mage_fire", "mage_fire_ring", "mage_fire_ring_low", "mage_ward", "mage_ward_mist", "mage_ward_glyph",
            "mage_ward_buff", "mage_ice_lit", "mage_ice_cd", "mage_mist_dense")


def tga_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:18]
    return struct.unpack("<HH", head[12:16])


def gen_text(name: str) -> str:
    return (ASSETS / f"generate_mage_{name}.py").read_text(encoding="utf-8")


def gen_list(src: str, name: str) -> list[str]:
    m = re.search(name + r"\s*=\s*\[(.*?)\]", src, re.S)
    return re.findall(r'"(\w+)"', m.group(1)) if m else []


def gen_int(src: str, pattern: str) -> int | None:
    m = re.search(pattern, src)
    return int(m.group(1)) if m else None


def lua_table(src: str, name: str) -> dict[str, int]:
    m = re.search(r"local " + name + r" = \{(.*?)\}", src, re.S)
    return {k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", m.group(1))} if m else {}


def probe_module():
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.DATA_SRC, g.MODULE_SRC = DATA, MODULE
    rt.execute(MOCK)
    return rt.eval("FS.GunsightMage")


def static_checks() -> list[str]:
    errs = []
    for name in TEXTURES:
        if not (MEDIA / f"{name}.tga").exists():
            errs.append(f"missing texture {name}.tga (run the tools/assets/generate_mage_*.py scripts)")
        if f"{name}.tga" not in MODULE:
            errs.append(f"the module does not use {name}.tga")
    for name in set(re.findall(r"mage_\w+\.tga", MODULE)):
        if name[:-4] not in TEXTURES:
            errs.append(f"the module uses {name}, which this harness does not know")
    frost, mark, arcane, fire, ward = (gen_text(n) for n in ("frost", "mark", "arcane", "fire", "ward"))
    for table, src, glist in (("FCELL", frost, "FROST_CELLS"), ("FING", frost, "FING_CELLS"), ("SPK", mark, "SPIKE_CELLS"),
                              ("ACELL", arcane, "ARC_CELLS"), ("GCELL", arcane, "GEM_CELLS"), ("FIRECELL", fire, "FIRE_CELLS"),
                              ("WCELL", ward, "WARD_CELLS"), ("MCELL", ward, "MIST_CELLS"), ("COMETCELL", mark, "COMET_CELLS")):
        cells = {c: i for i, c in enumerate(gen_list(src, glist))}
        if glist == "COMET_CELLS":       # ready0..ready<N-1>, then off and flash (a list comprehension, not a literal list)
            frames = gen_int(src, r"COMET_FRAMES, COMET_FPS = (\d+)") or -1
            cells = {"off": frames, "flash": frames + 1}
        lua = lua_table(MODULE, table)
        if not lua:
            errs.append(f"{table}: not found in the module")
        for k, v in lua.items():
            if cells.get(k) != v:
                errs.append(f"{table}.{k} = {v} in the module but {cells.get(k)} in the generator's {glist}")
    if gen_int(mark, r"COMET_FRAMES, COMET_FPS = (\d+)") != 24 or "COMET_FRAMES = 24" not in MODULE:
        errs.append("the comet frame count drifted")
    if gen_int(frost, r"GLINT_FRAMES = (\d+)") != 8 or "GLINT_FRAMES = 8" not in MODULE:
        errs.append("the glint frame count drifted")
    if gen_int(fire, r"FLAME_FRAMES, FLAME_STACKS = (\d+)") != 12 or "FLAME_FRAMES = 12" not in MODULE:
        errs.append("the flame frame count drifted")
    # atlas geometry: the descriptor against the file, and the art points against the generators
    try:
        M = probe_module()
    except LuaError as e:
        return errs + [f"could not load the module for the geometry check: {e}"]
    origins = {
        "frost": (gen_int(frost, r"BOX, CENTER, CELL = \d+, (\d+)"),) * 2,
        "glint": (gen_int(frost, r"BOX, CENTER, CELL = \d+, (\d+)"),) * 2,
        "fingers": (2, 2), "spike": (gen_int(mark, r"SPIKE_OX, SPIKE_OY = (\d+)"), gen_int(mark, r"SPIKE_OX, SPIKE_OY = \d+, (\d+)")),
        "comet": (gen_int(mark, r"COMET_OX, COMET_OY = (-?\d+)"), gen_int(mark, r"COMET_OX, COMET_OY = -?\d+, (-?\d+)")),
        "arcane": (gen_int(arcane, r"CENTER = (\d+)"),) * 2, "gems": (gen_int(arcane, r"GEM_ORIGIN = (\d+)"),) * 2,
        "flame": (gen_int(fire, r"FLAME_OX, FLAME_OY = (\d+)"), gen_int(fire, r"FLAME_OX, FLAME_OY = \d+, (\d+)")),
        "fire": (gen_int(fire, r"CENTER = (\d+)"),) * 2, "ward": (gen_int(ward, r"CENTER = (\d+)"),) * 2,
        "mist": (gen_int(ward, r"CENTER = (\d+)"),) * 2, "glyph": (gen_int(ward, r"GLYPH_CELL, GLYPH_ORIGIN = \d+, (\d+)"),) * 2,
    }
    for key, (ox, oy) in origins.items():
        a = M["A"][key]
        stem = a["file"][:-4]
        w, h = tga_size(MEDIA / a["file"]) if (MEDIA / a["file"]).exists() else (0, 0)
        if (a["w"], a["h"]) != (w, h):
            errs.append(f"atlas {key}: {a['w']}x{a['h']} in the module, {w}x{h} on disk ({stem})")
        if (a["ox"], a["oy"]) != (ox, oy):
            errs.append(f"atlas {key}: art point ({a['ox']}, {a['oy']}) in the module, ({ox}, {oy}) in the generator")
        if a["cols"] * a["cw"] > a["w"] or a["bw"] * 2 > a["cw"] or a["bh"] * 2 > a["ch"]:
            errs.append(f"atlas {key}: the cell grid does not fit the file")
    boxes = (("FLAKE_BOX", frost, r"FLAKE_BOX = \((.*?)\)"), ("SPIKE_BOX", mark, r"SPIKE_BOX = \((.*?)\)"),
             ("COMET_BOX", mark, r"COMET_BOX = \((.*?)\)"), ("ICE_LIT", ward, r"ICE_LIT_BOX = \((.*?)\)"),
             ("ICE_CD", ward, r"ICE_CD_BOX = \((.*?)\)"), ("MIST_BOX", ward, r"MIST_BOX = \((.*?)\)"))
    for lua_key, src, pat in boxes:
        m = re.search(pat, src)
        want = [int(x) for x in m.group(1).split(",")] if m else []
        have = [int(M["C"][lua_key][i]) for i in (1, 2, 3, 4)]
        if want != have:
            errs.append(f"{lua_key}: {have} in the module, {want} in the generator")
    for path in ("Modules/CombatHud/MageState.lua", "Modules/CombatHud/GunsightMage.lua", "Modules/CombatHud/GunsightMageClick.lua"):
        src = (ADDON / path).read_text(encoding="utf-8")
        if re.search("[–—]", src):
            errs.append(f"{path}: an em or en dash")
        if re.search(r"\b(bots?|automat\w*)\b", src, re.I):
            errs.append(f"{path}: flagged wording")
        if re.search(r"Parker", src):
            errs.append(f"{path}: a private name")
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        a, d, m, c = (toc.index(f"Modules/CombatHud/{n}.lua") for n in ("GunsightAreas", "MageState", "GunsightMage", "GunsightMageClick"))
        if not (a < d < m < c):
            errs.append("toc order: GunsightAreas, MageState, GunsightMage, GunsightMageClick")
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
