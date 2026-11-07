#!/usr/bin/env python3
"""Runs the real PriestShields.lua and GunsightPriest.lua headless against a mock client.

The Priest Class Module draws the design mockup "Priest shield and mending" (2026-11-07): the round shield that watches the
friendly target (else the player) and Prayer of Mending's beads, heart and party strip. These checks pin:

  * who the shield watches: a friendly target, else the player (a hostile target never carries our shield);
  * secrets: the absorb only ever reaches StatusBar:SetMinMaxValues / SetValue, SetAlpha (the light's gate) and
    AbbreviateNumbers -> SetFormattedText; any compare, arithmetic or concat on it throws (and a throw in a paint is logged and
    fails the case); no aura is read under combat lockdown;
  * the ledger: a Power Word: Shield cast in combat stamps the unit the SENT name matched (else the watched unit), with a 30 s
    shield and a 15 s Weakened Soul read as estimates ("~"), and catches the full mark from the absorb ping that follows;
  * out of combat the auras are the truth (any priest's shield and Weakened Soul; whose they are), and a shield lost early is a
    break (shards);
  * the rims and rune: violet Weakened Soul (a Cooldown fed plain numbers), the cooldown rim, the amber nudge in combat, calm
    and still out of combat, the dotted L6 lock;
  * Prayer of Mending: L40 lock, a cast lights 5 beads on the cast target's seat with a "~" timer, a plain read sets the holder
    and heals left, a plain holder change sparks a jump, the cooldown shade is the engine's timer;
  * the party strip: our own shield on a member fills its seat and draws its Weakened Soul line;
  * onHide stops the ticker and the subscription, onShow brings them back; the ticker stops when nothing moves;
  * under the REAL GunsightAreas.lua the host hides with no target, the module stops, and it comes back with a target;
  * the baked textures exist and the module's cell maps and geometry match the generator.

    python3 tools/gunsightpriest-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
DATA = (ADDON / "Modules/CombatHud/PriestShields.lua").read_text(encoding="utf-8")
MODULE = (ADDON / "Modules/CombatHud/GunsightPriest.lua").read_text(encoding="utf-8")
GENERATOR = (HERE / "assets/generate_priest_shield.py").read_text(encoding="utf-8")
MEDIA = ADDON / "Media/Textures"
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
function Obj:SetTextColor(r, g, b, a) self.tcolor = { r, g, b, a } end
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

-- units: token -> { guid, name, friend, hostile, class }
__units = { player = { guid = "P", name = "Stu", friend = true, class = "PRIEST" } }
function UnitExists(u) return __units[u] ~= nil end
function UnitGUID(u) return __units[u] and __units[u].guid end
function UnitName(u) return __units[u] and __units[u].name end
function UnitCanAssist(_, u) return __units[u] ~= nil and __units[u].friend == true end
function UnitCanAttack(_, u) return __units[u] ~= nil and __units[u].hostile == true end
function UnitIsUnit(a, b) return __units[a] ~= nil and __units[b] ~= nil and __units[a].guid == __units[b].guid end
function UnitClass(u) return "x", __units[u] and __units[u].class end
__level = 60
function UnitLevel() return __level end
RAID_CLASS_COLORS = { PRIEST = { r = 1, g = 1, b = 1 }, WARRIOR = { r = 0.78, g = 0.61, b = 0.43 } }
function SetTarget(kind)
    if kind == nil then __units.target = nil; return end
    local base = kind == "party2" and __units.party2 or { guid = "T", name = kind == "hostile" and "Boar" or "Ally", friend = kind ~= "hostile", hostile = kind == "hostile", class = "WARRIOR" }
    __units.target = base
end
function AddParty(i, guid, name, class) __units["party" .. i] = { guid = guid, name = name, friend = true, class = class or "WARRIOR" } end

ABSORBS = {}
function UnitGetTotalAbsorbs(u) ABSORBS[u] = ABSORBS[u] or Secret("absorb " .. u); return ABSORBS[u] end
ABBREV_FED = 0
ABBREV = Secret("abbrev")
function AbbreviateNumbers(v) if IsSecretValue(v) then ABBREV_FED = ABBREV_FED + 1 end return ABBREV end

__known = { [17] = true, [401859] = true }
function IsPlayerSpell(id) return __known[id] == true end
__names = { [401859] = "Prayer of Mending", [6788] = "Weakened Soul", [133] = "Fireball", [2050] = "Lesser Heal" }
for _, id in ipairs({ 25218, 25217, 10901, 10900, 10899, 10898, 6066, 6065, 3747, 600, 592, 17 }) do __names[id] = "Power Word: Shield" end
__cd = {}                -- spell name -> true while its cooldown runs
local CD_ON = { isActive = true, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
local CD_OFF = { isActive = false, isOnGCD = false, startTime = Secret("start"), duration = Secret("dur") }
C_Spell = {
    GetSpellName = function(id) return __names[id] end,
    GetSpellCooldown = function(id)
        local n = type(id) == "number" and __names[id] or id
        return __cd[n] == true and CD_ON or CD_OFF      -- the client allocates its own; the mock does not, so the tick's is ours
    end,
    GetSpellCooldownDuration = function(id) return { durationOf = id } end,
}
Enum = { StatusBarTimerDirection = { RemainingTime = 1 }, StatusBarInterpolation = { Immediate = 0 } }
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
assert(loadstring(DATA_SRC, "@PriestShields.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightPriest.lua"))("forever-stuwave", FS)
D, M = FS.PriestShields, FS.GunsightPriest
SPEC = Areas.specs[1].spec
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
function Cast(id, targetName) if targetName ~= nil then D._OnSent(targetName, id) end D._OnCast(id) end
function Ping(unit) fire("UNIT_ABSORB_AMOUNT_CHANGED", unit) end
function NoLog()
    for k, v in pairs(__logged) do
        if k ~= "gunsightpriest_noclip" and k ~= "gunsightpriest_nocooldown" then error("logged " .. k .. ": " .. tostring(v), 2) end
    end
end
function Shown(t) return t.shown ~= false and visible(t) end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_priests_only", """
    check(SPEC and SPEC.classes[1] == "PRIEST" and #SPEC.classes == 1)
    local m = Build()
    check(m and m.name == "ForeverSTUwaveGunsightPriest")
    NoLog()
""")

case("the_shield_watches_a_friendly_target_else_the_player", """
    Build()
    check(D.Watched() == "player", "no target: the player")
    SetTarget("friend")
    check(D.Watched() == "target", "a friendly target")
    SetTarget("hostile")
    check(D.Watched() == "player", "an enemy never carries our shield")
""")

case("the_absorb_reaches_only_the_engine_setters", """
    SetTarget("friend")
    Build()
    local p = Parts()
    check(IsSecretValue(p.bar.value), "the light's value is the secret absorb")
    check(IsSecretValue(p.bar.max), "with no mark the max is the absorb itself (full)")
    check(IsSecretValue(p.gate.alpha), "the light's gate alpha is the secret absorb")
    check(ABBREV_FED > 0 and p.absorbLabel.secretFed, "the number goes through AbbreviateNumbers to SetFormattedText")
    Tick(0.05)
    NoLog()
""")

case("a_cast_in_combat_stamps_the_matched_unit_and_catches_the_mark", """
    AddParty(2, "G2", "Tank", "WARRIOR")
    SetTarget("friend")
    Build()
    __combat = true
    Cast(10901, "Tank")
    local r = D.Shield("party2")
    check(r and r.up and r.est and r.mine and r.expires == __now + 30, "the shield on party2, 30 s, an estimate")
    check(r.ws and r.wsEst and r.wsExpires == __now + 15, "Weakened Soul 15 s from the cast")
    check(D.Shield("target") == nil or not D.Shield("target").up, "not on the target")
    check(D._marks.G2 ~= nil and IsSecretValue(D._marks.G2), "the mark is the absorb caught at the cast")
    Tick(0.05)
    local s = Parts().seats[3]
    check(Shown(s.bar) and IsSecretValue(s.bar.value) and IsSecretValue(s.bar.max), "seat 3 fills with party2's absorb")
    check(Shown(s.ws) and s.ws.fsW == 13, "seat 3's Weakened Soul line is full")
    Tick(7.5)
    check(s.ws.fsW == 7, "and drains: " .. tostring(s.ws.fsW))
    check(AURA_IN_COMBAT == 0, "no aura read in combat")
    NoLog()
""")

case("an_unmatched_or_secret_sent_name_falls_back_to_the_watched_unit", """
    SetTarget("hostile")
    Build()
    __combat = true
    Cast(17, Secret("name"))
    check(D.Shield("player") and D.Shield("player").up, "a hostile target: the player got it")
    SetTarget("friend")
    __now = __now + 5
    Cast(17, "Nobody")
    check(D.Shield("target") and D.Shield("target").up, "a friendly target: the target got it")
    NoLog()
""")

case("weakened_soul_after_a_cast_shows_the_violet_rim_from_plain_numbers", """
    SetTarget("friend")
    Build()
    __combat = true
    Cast(17, "Ally")
    Tick(0.05)
    local p = Parts()
    check(Shown(p.wsDark) and Shown(p.wsCd), "the violet rim shows")
    check(p.wsCd.cd[1] == __now - 0.05 and p.wsCd.cd[2] == 15, "SetCooldown(cast, 15)")
    check(p.wsLabel.text == "", "while the guess says there is light, the label is the absorb")
    check(Shown(p.absorbLabel))
    check(p.stateRune.color[1] > 0.7 and p.stateRune.color[2] < 0.4, "the empty rune is violet under the light")
    NoLog()
""")

case("out_of_combat_the_auras_are_the_truth_and_the_label_counts_the_lock", """
    SetTarget("friend")
    Aura("target", "Weakened Soul", { expirationTime = __now + 9, duration = 15, sourceUnit = "party1" })
    Build()
    Tick(0.05)
    local r = D.Shield("target")
    check(r and not r.up and r.ws and not r.wsEst and not r.wsMine, "another priest's Weakened Soul, plain")
    local p = Parts()
    check(p.wsLabel.text == "9s", "the lock's time, plain: " .. tostring(p.wsLabel.text))
    check(not Shown(p.absorbLabel), "no absorb label over it")
    check(p.wsCd.cd[2] == 15 and p.wsCd.cd[1] == __now - 0.05 + 9 - 15, "the rim from the aura's own clock")
    NoLog()
""")

case("a_shield_that_vanishes_early_out_of_combat_breaks", """
    SetTarget("friend")
    Aura("target", "Power Word: Shield", { expirationTime = __now + 25, duration = 30, sourceUnit = "player" })
    Build()
    check(D.Shield("target").up and D.Shield("target").mine)
    Aura("target", "Power Word: Shield", nil)
    fire("UNIT_AURA", "target")
    Tick(0.1)
    local sh = Parts().shards[1]
    check(Shown(sh.big), "the shards fly")
    Tick(1)
    check(not Shown(sh.big), "and settle")
    NoLog()
""")

case("empty_and_clear_nudges_amber_in_combat_and_is_calm_and_still_out_of_it", """
    SetTarget("friend")
    Build()
    local p = Parts()
    Tick(0.05)
    check(not Shown(p.halo), "calm: no halo")
    check(p.stateRim.color[4] == 0.45, "calm: the dim dashed rim")
    check(not Ticking(), "calm: nothing moves, no ticker")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    D.Refresh()
    check(Ticking(), "the nudge pulses")
    local alphas = {}
    for i = 1, 45 do Tick(1 / 30); alphas[p.stateRim.color[4]] = true end
    local n = 0
    for _ in pairs(alphas) do n = n + 1 end
    check(n >= 4 and Shown(p.halo), "the amber dashes breathe with a glow")
    check(p.stateRim.color[1] == 1 and p.stateRim.color[2] > 0.6, "amber")
    NoLog()
""")

case("the_cooldown_rim_shows_while_the_shield_cools", """
    SetTarget("friend")
    __cd["Power Word: Shield"] = true
    Build()
    Tick(0.05)
    local p = Parts()
    check(Shown(p.cdRim) and not Shown(p.stateRim) and not Shown(p.halo), "the dim teal rim")
    NoLog()
""")

case("not_learned_is_the_dotted_rim_and_l6", """
    __known = {}
    __level = 5
    SetTarget("friend")
    Build()
    Tick(0.05)
    local p = Parts()
    check(p.wsLabel.text == "L6", tostring(p.wsLabel.text))
    check(not Shown(p.body) and not Shown(p.bar) and not Shown(p.gate), "only the dotted rim and the rune")
    check(Shown(p.stateRim) and p.stateRim.color[4] == 0.4)
    check(Parts().pomLabel.text == "L40", "and Mending is locked too")
    NoLog()
""")

case("a_hit_flashes_and_shakes_the_watched_shield", """
    SetTarget("friend")
    Build()
    __combat = true
    Cast(17, "Ally")
    Tick(1)
    Ping("target")
    Tick(0.02)
    local p = Parts()
    check(Shown(p.flash), "the flash")
    check(p.sf.fsX == 1 or p.sf.fsX == -1, "the shake")
    Tick(0.3)
    check(not Shown(p.flash) and p.sf.fsX == 0, "both settle")
    Ping("party1")
    Tick(0.02)
    check(not Shown(p.flash), "another unit's ping does not flash the big shield")
    NoLog()
""")

case("mending_cast_lights_five_beads_on_the_targets_seat", """
    AddParty(1, "G1", "Tank", "WARRIOR")
    SetTarget("friend")
    Build()
    __combat = true
    Cast(401859, "Tank")
    Tick(0.05)
    local m = D.Mending()
    check(m.out and m.holder == 2 and m.charges == 5 and m.est, "holder seat 2, 5 heals, an estimate")
    local p = Parts()
    local lit = 0
    for i = 1, 5 do if p.beads[i].fsCell == M.MCELL.beadLit then lit = lit + 1 end end
    check(lit == 5, "five lit beads")
    check(Shown(p.seats[2].heart) and Shown(p.seats[2].glow1), "the holder seat is framed with a heart")
    check(p.pomLabel.text == "~30s", tostring(p.pomLabel.text))
    check(p.heart.fsCell == M.MCELL.heartLit)
    NoLog()
""")

case("out_of_combat_mending_reads_the_holder_and_a_move_sparks_a_jump", """
    AddParty(1, "G1", "Tank", "WARRIOR")
    AddParty(3, "G3", "Dps", "WARRIOR")
    SetTarget("friend")
    Aura("party1", "Prayer of Mending", { applications = 3, expirationTime = __now + 20, sourceUnit = "player" })
    Build()
    Tick(0.05)
    local m = D.Mending()
    check(m.out and m.holder == 2 and m.charges == 3 and not m.est, "plain holder and heals")
    local p = Parts()
    local lit = 0
    for i = 1, 5 do if p.beads[i].fsCell == M.MCELL.beadLit then lit = lit + 1 end end
    check(lit == 3, "three lit beads")
    check(p.pomLabel.text == "20s", tostring(p.pomLabel.text))
    Aura("party1", "Prayer of Mending", nil)
    Aura("party3", "Prayer of Mending", { applications = 2, expirationTime = __now + 30, sourceUnit = "player" })
    fire("UNIT_AURA", "party3")
    Tick(0.1)
    check(m.holder == 4 and m.from == 2, "the jump")
    check(Shown(p.sparkCore), "the spark flies")
    Tick(1)
    check(not Shown(p.sparkCore), "and lands")
    NoLog()
""")

case("mending_locked_cooling_and_nudging", """
    __known[401859] = nil
    SetTarget("friend")
    Build()
    Tick(0.05)
    local p = Parts()
    check(p.pomLabel.text == "L40" and p.heart.fsCell == M.MCELL.heartLocked, "locked")
    check(not Shown(p.seats[1].bg), "no strip while locked (the mockup)")
    __known[401859] = true
    D.Refresh()
    __cd["Prayer of Mending"] = true
    D.Refresh()
    Tick(0.05)
    check(Shown(p.cdBar) and p.cdBar.timer and p.cdBar.timer.dir == 1, "the shade is the engine's timer, remaining time")
    __cd["Prayer of Mending"] = nil
    __combat = true
    D.Refresh()
    Tick(0.05)
    check(not Shown(p.cdBar) and p.heart.fsCell == M.MCELL.heartAmber and p.beads[1].fsCell == M.MCELL.beadDash, "nudge")
    NoLog()
""")

case("on_hide_stops_the_ticker_and_the_subscription_on_show_restarts", """
    SetTarget("friend")
    Build()
    __combat = true
    D.Refresh()
    check(Ticking(), "ticking while shown and moving")
    SPEC.onHide("lower")
    check(not Ticking(), "the OnUpdate stops on hide")
    Cast(17, "Ally")
    check(D.Shield("target").up, "a cast while hidden is still recorded")
    SPEC.onShow("lower")
    check(Ticking(), "the OnUpdate is back on show")
    NoLog()
""")

case("the_steady_tick_allocates_nothing", """
    -- under LuaJIT with the JIT off (as hud-harness.py measures): indicative only, the client runs PUC 5.1
    jit.off()
    jit.flush()
    AddParty(1, "G1", "Tank", "WARRIOR")
    SetTarget("friend")
    Build()
    __combat = true
    Cast(17, "Ally")
    Cast(401859, "Tank")
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
UnitClass = function() return "Priest", "PRIEST" end
UnitGUID = function(u) if u == "player" then return "P" end if u == "target" and TARGET.exists then return "T" end end
UnitName = function(u) return u end
UnitCanAssist = function(_, u) return u == "target" and TARGET.exists end
UnitIsUnit = function(a, b) return a == b end
UnitLevel = function() return 60 end
UnitGetTotalAbsorbs = function() return SECRET end
AbbreviateNumbers = function() return "154" end
IsPlayerSpell = function(id) return id == 17 end
C_Spell = { GetSpellName = function(id) if id == 17 then return "Power Word: Shield" end end,
    GetSpellCooldown = function() return { isActive = false, isOnGCD = false } end }
C_UnitAuras = { GetAuraDataBySpellName = function() return nil end }
FS.AurasReadable = function() return not IN_COMBAT end
loadAddonFile(DATA_SRC, "Modules/CombatHud/PriestShields.lua")
loadAddonFile(PRIEST_SRC, "Modules/CombatHud/GunsightPriest.lua")
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local P = FS.GunsightPriest
check(P.frame and isVisible(P.frame), "the module is built and drawn under the host")
FS.PriestShields._OnCast(17)
check(onUpdateFrames() == 1, "ticking with a shield going: " .. onUpdateFrames())
local body = P.parts.body
check(isVisible(body), "the shield is drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(P.frame) and not isVisible(body) and not isVisible(P.parts.wsLabel),
    "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(body), "a target brings it back")
check(onUpdateFrames() == 1, "and the ticker with it")
for k, v in pairs(DEGRADED) do
    if k ~= "gunsightpriest_noclip" and k ~= "gunsightpriest_nocooldown" then error("degraded " .. k .. ": " .. tostring(v)) end
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
    g.DATA_SRC, g.PRIEST_SRC = DATA, MODULE
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


def static_checks() -> list[str]:
    errs = []
    for name in ("priest_shield", "priest_shield_glint", "priest_shield_rays", "priest_shield_ws", "priest_shield_lit",
                 "priest_mending", "priest_heart_cd"):
        if not (MEDIA / f"{name}.tga").exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_priest_shield.py)")
        if f"{name}.tga" not in MODULE:
            errs.append(f"the module does not use {name}.tga")
    for gen_list, lua_table in (("SHIELD_CELLS", "CELL"), ("MENDING_CELLS", "MCELL")):
        m = re.search(gen_list + r" = \[(.*?)\]", GENERATOR, re.S)
        cells = re.findall(r'"(\w+)"', m.group(1)) if m else []
        lm = re.search(r"local " + lua_table + r" = \{(.*?)\}", MODULE, re.S)
        lua = {k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", lm.group(1))} if lm else {}
        if not cells or {c: i for i, c in enumerate(cells)} != lua:
            errs.append(f"{lua_table} in the module does not match the generator's {gen_list}")
    for gen, lua in (("R, BOSS = (\\d+)", r"SHIELD = \{ cx = 38, cy = 36, r = (\d+) \}"), ("BOX, CENTER = (\\d+)", r"BOX = (\d+)"),
                     (r"BOX, CENTER = \d+, (\d+)", r"CENTER = (\d+)"), (r"RAYS_BOX, RAYS_CENTER = (\d+)", r"RAYS_BOX = (\d+)"),
                     (r"RAYS_BOX, RAYS_CENTER = \d+, (\d+)", r"RAYS_CENTER = (\d+)"),
                     (r"LIT_X0, LIT_Y0, LIT_W, LIT_H = (-?\d+)", r"LIT = \{ x = (-?\d+)"),
                     (r"LIT_X0, LIT_Y0, LIT_W, LIT_H = -?\d+, (-?\d+)", r"LIT = \{ x = -?\d+, y = (-?\d+)"),
                     (r"LIT_X0, LIT_Y0, LIT_W, LIT_H = -?\d+, -?\d+, (\d+)", r"LIT = \{ x = -?\d+, y = -?\d+, w = (\d+)"),
                     (r"LIT_X0, LIT_Y0, LIT_W, LIT_H = -?\d+, -?\d+, \d+, (\d+)", r"h = (\d+) \}"),
                     (r"GLINT_FRAMES = (\d+)", r"GLINT_FRAMES = (\d+)")):
        a, b = re.search(gen, GENERATOR), re.search(lua, MODULE)
        if not (a and b and a.group(1) == b.group(1)):
            errs.append(f"geometry drifted: generator {gen!r} vs module {lua!r}")
    for path in ("Modules/CombatHud/PriestShields.lua", "Modules/CombatHud/GunsightPriest.lua",
                 "Modules/CombatHud/GunsightPriestClick.lua"):
        src = (ADDON / path).read_text(encoding="utf-8")
        if re.search("[\u2013\u2014]", src):
            errs.append(f"{path}: an em or en dash")
        if re.search(r"\b(bots?|automat\w*)\b", src, re.I):
            errs.append(f"{path}: flagged wording")
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        a, d, m, c = (toc.index(f"Modules/CombatHud/{n}.lua") for n in ("GunsightAreas", "PriestShields", "GunsightPriest", "GunsightPriestClick"))
        if not (a < d < m < c):
            errs.append("toc order: GunsightAreas, PriestShields, GunsightPriest, GunsightPriestClick")
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
