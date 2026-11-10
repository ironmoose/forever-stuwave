#!/usr/bin/env python3
"""Runs the real PriestShields.lua and GunsightPriest.lua headless against a mock client.

The Priest Class Module draws the design mockup "Priest shield and mending" (2026-11-07): the round shield that watches the
friendly target (else the player), and on the right Prayer of Mending's beads, heart and party strip, or (the mockup "Priest
right slot", 2026-11-10, variant A) two round medallions for Spirit Tap and Inner Fire. These checks pin:

  * who the shield watches: a friendly target, else the player (a hostile target never carries our shield);
  * secrets: the absorb only ever reaches StatusBar:SetMinMaxValues / SetValue, SetAlpha (the light's gate) and
    AbbreviateNumbers -> SetFormattedText; any compare, arithmetic or concat on it throws (and a throw in a paint is logged and
    fails the case); no aura is read under combat lockdown;
  * the ledger: a Power Word: Shield cast in combat stamps the unit the SENT name matched (else the watched unit), with a 30 s
    shield and a 15 s Weakened Soul read as estimates ("~"), and catches the full mark from the absorb ping that follows;
  * out of combat the auras are the truth (any priest's shield and Weakened Soul; whose they are), and a shield lost early is a
    break (shards);
  * the rims and rune: violet Weakened Soul (a Cooldown fed plain numbers), the cooldown rim, the amber nudge in combat, calm
    and still out of combat (the GHOST of the off state mockup, option C: only here the ghost cells, every other look keeps the
    dark shield and the dashed rim), the dotted L6 lock;
  * Prayer of Mending: L40 lock, a cast lights 5 beads on the cast target's seat with a "~" timer, a plain read sets the holder
    and heals left, a plain holder change sparks a jump, the cooldown shade is the engine's timer;
  * the party strip: our own shield on a member fills its seat and draws its Weakened Soul line;
  * onHide stops the ticker and the subscription, onShow brings them back; the ticker stops when nothing moves;
  * the right side (PriestRight.lua): the setting "Right side shows" (Auto, Spirit Tap + Inner Fire, Prayer of Mending, Off), Auto's
    group switch (a raid or a dungeon with Mending learned), a change in combat waiting for the end of the fight;
  * the medallions: the locked, calm, nudge and plain lit BASE looks, the engine COVER (an AuraContainer per medallion with one
    aura slot filtered by the spell's ids, the cover regions anchored to our anchor and the engine's number through
    SetDurationText / SetApplicationCount), the proof that gates it (placed on the anchor, unreadable, a misplaced slot put back,
    a failed build retried once and given up after three passes, a new rank id rebuilding it at most three times), no write to a
    slot region and no aura read in combat, no secret ever compared, the kill ledger's pull now cue, the state line;
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
RIGHT = (ADDON / "Modules/CombatHud/PriestRight.lua").read_text(encoding="utf-8")
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
-- a write to a region of an engine aura slot in combat is a refusal on the client: counted (the container's own SetAlpha is fine)
ENGINE_COMBAT_WRITES = 0
local function W(self) if __combat and self.engine then ENGINE_COMBAT_WRITES = ENGINE_COMBAT_WRITES + 1 end end
-- the anchor is written into the region's own table (no allocation: the steady tick case measures the module, not the mock)
function Obj:SetPoint(p, rel, rp, x, y)
    W(self)
    local pt = self.pt or {}
    pt[1], pt[2], pt[3], pt[4], pt[5] = p, rel, rp, x or 0, y or 0
    self.pt = pt
end
function Obj:ClearAllPoints() W(self) end
function Obj:SetSize(w, h) W(self); self.w, self.h = w, h end
function Obj:GetWidth() return self.w end
function Obj:GetHeight() return self.h end
function Obj:Show() W(self); self.shown = true end
function Obj:Hide() W(self); self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetAlpha(a) W(self); self.alpha = a end
-- geometry: every frame answers the same box unless a case gives it its own (`geo`: a table, or false for "cannot be read");
-- SetAllPoints follows its target and forgets the frame's own box
function Obj:SetAllPoints(t) W(self); self.ap = t; self.geo = nil end
local function geo(f) if f.geo ~= nil then return f.geo or {} end if f.ap then return geo(f.ap) end return { 100, 500, 140, 460 } end
function Obj:GetLeft() return geo(self)[1] end
function Obj:GetTop() return geo(self)[2] end
function Obj:GetRight() return geo(self)[3] end
function Obj:GetBottom() return geo(self)[4] end
-- animation groups: the harness only needs to know a breath was started
__groups = {}
function Obj:CreateAnimationGroup()
    local g = New("AnimGroup", self)
    g.anims = {}
    function g:SetLooping(l) self.looping = l end
    function g:CreateAnimation(kind) local a = New("Anim", self); a.akind = kind; self.anims[#self.anims + 1] = a; return a end
    function g:Play() self.playing = true end
    __groups[#__groups + 1] = g
    return g
end
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts[n] end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:RegisterUnitEvent(e, ...) self.events[e] = { ... } end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level or 1 end
function Obj:SetTexture(p) W(self); self.tex = p end
function Obj:SetTexCoord(l, r, t, b)
    W(self)
    local c = self.tc or {}
    c[1], c[2], c[3], c[4] = l, r, t, b
    self.tc = c
end
function Obj:SetVertexColor(r, g, b, a)
    W(self)
    local c = self.color or {}
    c[1], c[2], c[3], c[4] = r, g, b, a
    self.color = c
end
function Obj:SetText(t) W(self); self.text = t end
function Obj:SetFormattedText(fmt, v)
    W(self)
    self.formatted = v
    if IsSecretValue(v) then self.text = nil; self.secretFed = true; return end
    self.secretFed = false
    self.text = string.format(fmt, v)
end
function Obj:SetTextColor(r, g, b, a) self.tcolor = { r, g, b, a } end
function Obj:CreateTexture() local t = New("Texture", self); t.engine = self.engine; __textures[#__textures + 1] = t; return t end
function Obj:CreateFontString() local f = New("FontString", self); f.engine = self.engine; __fonts[#__fonts + 1] = f; return f end
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
-- the engine's aura container: AddAuraSlot calls initializeFrame at once with a slot whose IsShown is secret (as on the release
-- client) and whose SetDurationText / SetApplicationCount only record the font string the engine would write
__containers, __template, __auraFail, __slotGeo = {}, { CustomAuraContainerTemplate = true }, false, nil
C_XMLUtil = { GetTemplateInfo = function(name) if __template[name] then return {} end end }
local function MakeContainer(f)
    f.slots = {}
    function f:SetUnit(u) self.unit = u end
    function f:SetEnabled(on) self.enabled = on end
    function f:IsEnabled() return self.enabled end
    function f:AddAuraSlot(key, filter, opts)
        if __auraFail then error("AddAuraSlot refused") end
        local slot = New("Frame", self)
        slot.engine = true
        slot.key, slot.filter, slot.opts = key, filter, opts
        slot.IsShown = function() return Secret("slot shown") end
        function slot:SetDurationText(fs, o) self.durationFs, self.durationOpts = fs, o end
        function slot:SetApplicationCount(fs) self.countFs = fs end
        self.slots[#self.slots + 1] = slot
        __frames[#__frames + 1] = slot
        opts.initializeFrame(slot)
        slot.geo = __slotGeo                  -- where the engine really put it (nil: on the anchor we gave it)
    end
end
__textures, __fonts, __frames = {}, {}, {}
function CreateFrame(kind, name, parent, template)
    local f = New(kind, parent); f.name = name
    f.template = template
    if kind == "AuraContainer" then MakeContainer(f); __containers[#__containers + 1] = f end
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
-- the right side: spell names -> ids, the group, the setting store (mode "pom" so the older cases keep the mending strip)
__ids = { ["Spirit Tap"] = 15270, ["Inner Fire"] = 588 }
__raid, __inst, __instType = false, false, "none"
function IsInRaid() return __raid end
function IsInInstance() return __inst, __instType end
RIGHTSIDE, FIRENUDGE = "gunsight.priest.rightside", "gunsight.priest.firenudge"
__cfg, __cfgCallbacks = { [RIGHTSIDE] = "pom" }, {}
function SetCfg(key, value)
    __cfg[key] = value
    for _, fn in ipairs(__cfgCallbacks[key] or {}) do fn(value) end
end
function Know(id) __known[id] = true end
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
    Config = {
        RegisterDefault = function(k, v) if __cfg[k] == nil then __cfg[k] = v end end,
        Get = function(k) return __cfg[k] end,
        OnChange = function(k, fn) __cfgCallbacks[k] = __cfgCallbacks[k] or {}; table.insert(__cfgCallbacks[k], fn) end,
    },
    FrameHelpers = {
        ResolveSpell = function(name) return __ids[name] end,
        IsKnownSpellId = function(id) return __known[id] == true end,
        RegisterEvent = function(f, event, ...)
            if select("#", ...) > 0 then f:RegisterUnitEvent(event, ...) else f:RegisterEvent(event) end
            return true
        end,
    },
}
assert(loadstring(DATA_SRC, "@PriestShields.lua"))("forever-stuwave", FS)
assert(loadstring(RIGHT_SRC, "@PriestRight.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightPriest.lua"))("forever-stuwave", FS)
D, M, R = FS.PriestShields, FS.GunsightPriest, FS.PriestRight
SPEC = Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function Parts() return M.parts end
function Med(key) for _, m in ipairs(M.parts.meds) do if m.key == key then return m end end end
function Slot(key) local m = Med(key); return m.st.container and m.st.container.slots[1] end
function Container(key) return Med(key).st.container end
function Unlock() Know(15270); Know(588); fire("SPELLS_CHANGED") end
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
    check(p.body.fsCell == M.CELL.ghost and p.stateRim.fsCell == M.CELL.ghostRim, "calm: the ghost wash and its solid thin rim")
    check(Shown(p.body) and Shown(p.stateRim), "calm: both are drawn")
    check(p.stateRim.color[1] == 1 and p.stateRim.color[4] == 1, "calm: the rim's colours are baked, the region is not tinted")
    check(math.abs(p.stateRune.color[4] - 0.7) < 1e-9 and p.stateRune.color[1] < 0.5 and p.stateRune.color[3] > 0.8, "calm: the rune in ice cyan at 0.7")
    check(not Shown(p.stateLine), "calm: no glow round the rune")
    check(not Ticking(), "calm: nothing moves, no ticker")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    D.Refresh()
    check(Ticking(), "the nudge pulses")
    check(p.body.fsCell == M.CELL.dark and p.stateRim.fsCell == M.CELL.rimDash, "the nudge is the dark shield and the dashed rim again")
    local alphas = {}
    for i = 1, 45 do Tick(1 / 30); alphas[p.stateRim.color[4]] = true end
    local n = 0
    for _ in pairs(alphas) do n = n + 1 end
    check(n >= 4 and Shown(p.halo), "the amber dashes breathe with a glow")
    check(p.stateRim.color[1] == 1 and p.stateRim.color[2] > 0.6, "amber")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    D.Refresh()
    Tick(0.05)
    check(p.body.fsCell == M.CELL.ghost and p.stateRim.fsCell == M.CELL.ghostRim, "out of combat it is the ghost again")
    check(p.stateRim.color[1] == 1 and p.stateRim.color[4] == 1 and not Shown(p.halo), "and the rim is untinted, no halo")
    NoLog()
""")

case("the_ghost_is_only_the_calm_empty_shield_a_cooldown_is_as_before", """
    -- cooling down: the dark shield, no dashed rim, the dim teal rim, a teal rune and no glow round it
    SetTarget("friend")
    __cd["Power Word: Shield"] = true
    Build()
    Tick(0.05)
    local p = Parts()
    check(p.body.fsCell == M.CELL.dark and Shown(p.body), "cooldown: the dark shield")
    check(not Shown(p.stateRim) and Shown(p.cdRim) and not Shown(p.stateLine), "cooldown: only the dim teal rim")
    check(p.stateRune.color[4] == 1 and math.abs(p.stateRune.color[1] - 0x2a / 255) < 1e-6, "cooldown: the teal rune")
    NoLog()
""")

case("the_ghost_is_only_the_calm_empty_shield_weakened_soul_is_as_before", """
    SetTarget("friend")
    Aura("target", "Weakened Soul", { expirationTime = __now + 9, duration = 15, sourceUnit = "party1" })
    Build()
    Tick(0.05)
    local p = Parts()
    check(p.body.fsCell == M.CELL.dark and Shown(p.body), "Weakened Soul: the dark shield")
    check(not Shown(p.stateRim) and Shown(p.wsDark) and Shown(p.wsCd), "Weakened Soul: the violet rim alone")
    check(p.stateRune.color[4] == 1 and p.stateRune.color[1] > 0.7 and p.stateRune.color[2] < 0.4, "Weakened Soul: the violet rune")
    check(Shown(p.stateLine) and p.stateLine.color[4] == 0.25, "Weakened Soul: the violet glow round it")
    NoLog()
""")

case("the_ghost_is_only_the_calm_empty_shield_a_shield_up_is_as_before", """
    SetTarget("friend")
    Aura("target", "Power Word: Shield", { expirationTime = __now + 25, duration = 30, sourceUnit = "player" })
    Build()
    Tick(0.05)
    local p = Parts()
    check(D.Shield("target").up, "the guess says there is light")
    check(p.body.fsCell == M.CELL.dark and p.stateRim.fsCell == M.CELL.rimDash, "up: the dark shield and the dashed rim under the light")
    check(Shown(p.stateRim) and p.stateRim.color[4] == 0.45 and p.stateRim.color[1] < 0.5, "up: the rim at 0.45 in ice cyan")
    check(p.stateRune.color[4] == 1 and Shown(p.stateLine) and p.stateLine.color[4] == 0.22, "up: the full rune with its glow")
    NoLog()
""")

case("the_ghost_is_only_the_calm_empty_shield_not_learned_is_as_before", """
    SetTarget("friend")
    Build()
    Tick(0.05)
    local p = Parts()
    check(p.body.fsCell == M.CELL.ghost, "calm first")
    __known = {}
    __level = 5
    D.Refresh()
    Tick(0.05)
    check(p.wsLabel.text == "L6", tostring(p.wsLabel.text))
    check(p.stateRim.fsCell == M.CELL.rimDash and Shown(p.stateRim) and p.stateRim.color[4] == 0.4 and p.stateRim.color[1] < 0.7,
        "not learned: the dotted rim in muted violet at 0.4, never the ghost's")
    check(p.stateRune.color[4] == 0.22, "not learned: the faint rune")
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

# --- the right side: the setting, the group, the medallions -------------------------------------------------------------

case("right_side_setting_chooses_the_look_and_unknown_values_read_as_auto", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    local p = Parts()
    check(R.Mode() == "medallions" and Shown(p.rf) and not Shown(p.mf) and not Shown(p.pomLabel), "Spirit Tap + Inner Fire")
    SetCfg(RIGHTSIDE, "pom")
    check(R.Mode() == "pom" and Shown(p.mf) and Shown(p.pomLabel) and not Shown(p.rf), "Prayer of Mending")
    SetCfg(RIGHTSIDE, "off")
    check(R.Mode() == "off" and not Shown(p.mf) and not Shown(p.rf) and not Shown(p.pomLabel), "Off: nothing on the right")
    SetCfg(RIGHTSIDE, "bogus")
    check(R.Setting() == "auto", "an unknown value reads as auto")
    NoLog()
""")

case("auto_shows_the_medallions_alone_and_mending_in_a_raid_or_a_dungeon_once_learned", """
    SetCfg(RIGHTSIDE, "auto")
    SetTarget("friend")
    Build()
    local p = Parts()
    check(R.Mode() == "medallions" and Shown(p.rf) and not Shown(p.mf), "alone: the medallions")
    __raid = true
    fire("GROUP_ROSTER_UPDATE")
    check(R.Mode() == "pom" and Shown(p.mf) and not Shown(p.rf), "a raid group with Mending learned: Prayer of Mending")
    __raid, __inst, __instType = false, true, "party"
    fire("ZONE_CHANGED_NEW_AREA")
    check(R.Mode() == "pom", "a dungeon too")
    __instType = "pvp"
    fire("ZONE_CHANGED_NEW_AREA")
    check(R.Mode() == "medallions", "a battleground is neither")
    __instType = "raid"
    fire("ZONE_CHANGED_NEW_AREA")
    check(R.Mode() == "pom", "a raid instance")
    __known[401859] = nil
    D.Refresh()
    fire("SPELLS_CHANGED")
    check(R.Mode() == "medallions" and Shown(p.rf), "Mending not learned yet: Spirit Tap + Inner Fire even in a dungeon")
    __known[401859] = true
    D.Refresh()
    fire("SPELLS_CHANGED")
    check(R.Mode() == "pom", "learned: Prayer of Mending")
    SetCfg(RIGHTSIDE, "spirit")
    check(R.Mode() == "medallions", "the fixed choice ignores the group")
    NoLog()
""")

case("a_change_in_combat_waits_for_the_end_of_the_fight", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    local p = Parts()
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    SetCfg(RIGHTSIDE, "pom")
    check(R.Mode() == "medallions" and R.Pending(), "a setting changed in combat waits")
    SetCfg(RIGHTSIDE, "auto")
    __raid = true
    fire("GROUP_ROSTER_UPDATE")
    Tick(0.05)
    check(R.Mode() == "medallions" and Shown(p.rf) and not Shown(p.mf), "a group change waits too, nothing swaps mid fight")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(R.Mode() == "pom" and not R.Pending() and Shown(p.mf) and not Shown(p.rf), "applied when the fight ends")
    NoLog()
""")

case("not_talented_and_not_learned_are_the_locked_looks", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    local sp, fi = Med("spirit"), Med("fire")
    check(not R.Known("spirit") and not R.Known("fire"), "neither is known")
    for _, m in ipairs({ sp, fi }) do
        check(Shown(m.rim) and m.rim.fsCell == M.MEDCELL.dash and m.rim.color[4] == 0.4 and m.rim.color[1] < 0.7, "the dotted rim, muted")
        check(not Shown(m.face) and not Shown(m.halo) and not Shown(m.glow) and not Shown(m.rimIn), "nothing lit")
    end
    check(sp.glyph.fsCell == M.MEDCELL.skullDots and fi.glyph.fsCell == M.MEDCELL.shieldDots, "the glyphs are dotted")
    check(fi.lock.text == "L12" and sp.lock == nil, "Inner Fire shows its level, Spirit Tap (a talent) shows none")
    check(#__containers == 0, "no container for a spell that is not known")
    check(not Ticking(), "locked: still")
    Unlock()
    check(R.Known("spirit") and R.Known("fire") and fi.lock.text == "", "learned: the level label goes")
    check(sp.glyph.fsCell ~= M.MEDCELL.skullDots and fi.glyph.fsCell ~= M.MEDCELL.shieldDots, "and the dots with it")
    NoLog()
""")

case("calm_and_the_amber_nudge_when_the_engine_is_not_live_follow_a_plain_read_out_of_combat", """
    __slotGeo = false                      -- the engine's slot cannot be located: no proof, no engine cover
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    Tick(0.05)
    local sp, fi = Med("spirit"), Med("fire")
    check(not sp.st.live and not fi.st.live, "neither is live: the slots cannot be read")
    check(Container("spirit").alpha == 0 and Container("fire").alpha == 0, "so the containers stay invisible")
    check(R.PlainUp("spirit") == false and R.PlainUp("fire") == false, "plain reads: both absent")
    check(sp.face.fsCell == M.MEDCELL.ghost and sp.glyph.fsCell == M.MEDCELL.skullDim and not Shown(sp.rim), "Spirit Tap: calm, dim")
    check(fi.face.fsCell == M.MEDCELL.body and fi.rim.fsCell == M.MEDCELL.dash and fi.glyph.fsCell == M.MEDCELL.shieldAmber,
        "Inner Fire missing: the dark body, amber dashes, the amber glyph")
    check(fi.rim.color[1] == 1 and fi.rim.color[2] > 0.6 and fi.rim.color[3] < 0.4 and Shown(fi.halo) and not Shown(fi.glow), "amber, a halo, no glow ring")
    check(Ticking(), "the nudge breathes")
    local seen = {}
    for i = 1, 45 do Tick(1 / 30); seen[fi.rim.color[4]] = true end
    local n = 0
    for _ in pairs(seen) do n = n + 1 end
    check(n >= 4, "the amber dashes breathe: " .. n)
    SetCfg(FIRENUDGE, false)
    check(fi.face.fsCell == M.MEDCELL.ghost and fi.glyph.fsCell == M.MEDCELL.shieldDim and not Shown(fi.rim) and not Ticking(),
        "the reminder off: calm and still")
    SetCfg(FIRENUDGE, true)
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    check(fi.face.fsCell == M.MEDCELL.ghost and fi.glyph.fsCell == M.MEDCELL.shieldDim,
        "in combat, with no engine to tell, the look is calm: no stale claim")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(fi.face.fsCell == M.MEDCELL.body, "and the nudge is back out of combat")
    check(AURA_IN_COMBAT == 0, "no aura read in combat")
    NoLog()
""")

case("a_plain_read_of_the_aura_draws_the_lit_look_without_a_number_while_the_engine_is_not_live", """
    __slotGeo = false
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    Aura("player", "Inner Fire", { applications = 17, expirationTime = __now + 600, duration = 600 })
    Aura("player", "Spirit Tap", { expirationTime = __now + 15, duration = 15 })
    fire("UNIT_AURA", "player")
    Tick(0.05)
    local sp, fi = Med("spirit"), Med("fire")
    check(R.PlainUp("fire") == true and R.PlainUp("spirit") == true)
    check(fi.face.fsCell == M.MEDCELL.body and fi.rim.fsCell == M.MEDCELL.rimOuter and fi.rimIn.fsCell == M.MEDCELL.rimInner
        and fi.glyph.fsCell == M.MEDCELL.shieldLit and not Shown(fi.glow), "Inner Fire up: the lit look")
    check(math.abs(fi.rim.color[2] - 0xd2 / 255) < 1e-6 and fi.rim.color[4] == 1, "in gold")
    check(sp.glyph.fsCell == M.MEDCELL.skullLit and Shown(sp.glow) and sp.rim.fsCell == M.MEDCELL.rimOuter, "Spirit Tap up: lit, with its glow ring")
    check(math.abs(sp.rim.color[1] - 0x3e / 255) < 1e-6 and math.abs(sp.rim.color[3] - 0x8a / 255) < 1e-6, "in spirit green")
    check(not Ticking(), "the plain lit look is still")
    NoLog()
""")

case("the_engine_cover_is_an_aura_slot_per_medallion_with_the_engines_number", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    check(#__containers == 2, "one container per medallion: " .. #__containers)
    local sc, fc = Container("spirit"), Container("fire")
    check(sc.template == "CustomAuraContainerTemplate" and sc.unit == "player" and sc.enabled and Shown(sc), "armed on the player")
    check(sc.parent == Parts().rf and fc.parent == Parts().rf, "inside the right side's frame")
    local ss, fs = Slot("spirit"), Slot("fire")
    check(#sc.slots == 1 and ss.filter == "HELPFUL" and ss.key == "spirit" and fs.key == "fire", "one HELPFUL slot each")
    local ids = ss.opts.candidateFilters.includeSpellIDs
    check(ids[15270] and ids[15338] and ids[15271], "Spirit Tap: the talent ranks and the buff")
    local fids = fs.opts.candidateFilters.includeSpellIDs
    check(fids[588] and fids[25431] and not fids[15270], "Inner Fire: its ranks only")
    local sm, fm = Med("spirit"), Med("fire")
    local sp, fp = sm.eng.parts[1], fm.eng.parts[1]
    check(sp and fp and sp.slot == ss and fp.slot == fs, "the parts are registered")
    check(ss.ap == sm.anc and fs.ap == fm.anc, "the slots sit on our anchors")
    check(#sp.cover == 6 and #fp.cover == 5, "the cover: glow ring only for Spirit Tap, then body, rims, halo, glyph")
    for _, part in ipairs({ sp, fp }) do
        for _, t in ipairs(part.cover) do
            check(t.engine and t.ap == (part == sp and sm.anc or fm.anc), "every cover region is anchored to the medallion's anchor")
            check(t.tc and t.tc[2] - t.tc[1] == 80 / 512 and t.tc[4] - t.tc[3] == 80 / 256, "and is one atlas cell")
        end
    end
    check(ss.durationFs == sp.num and type(ss.durationOpts) == "table" and ss.countFs == nil, "Spirit Tap: the engine's time")
    check(fs.countFs == fp.num and fs.durationFs == nil, "Inner Fire: the engine's charges")
    check(sp.num.size == M.C.NUM_SIZE and sp.num.pt[2] == sm.numAnc and fp.num.pt[2] == fm.numAnc, "the numbers are seated on their anchors")
    check(math.abs(sp.num.cur[1] - 0xc8 / 255) < 1e-6 and math.abs(fp.num.cur[3] - 0xb0 / 255) < 1e-6, "in their own colours")
    local playing = 0
    for _, g in ipairs(__groups) do if g.playing and g.looping == "REPEAT" and #g.anims == 2 then playing = playing + 1 end end
    check(playing == 3, "three breaths run (Spirit Tap's glow and halo, Inner Fire's halo): " .. playing)
    check(sm.st.live and fm.st.live and sc.alpha == 1 and fc.alpha == 1, "the slots are proven on the anchors: live, the containers visible")
    NoLog()
""")

case("the_proof_gates_the_cover_a_misplaced_slot_is_put_back_and_hides_it_until_it_reads_right", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    local m, slot, c = Med("spirit"), Slot("spirit"), Container("spirit")
    check(m.st.live and c.alpha == 1)
    slot.ap = nil
    slot.geo = { 300, 500, 340, 460 }
    M._EngineTick()
    check(not m.st.live and c.alpha == 0, "a slot off its anchor: not live, the cover hidden")
    check(slot.ap == m.anc, "put back on the anchor")
    check(__logged.gunsightpriest_engine_layout, "and said once")
    __logged.gunsightpriest_engine_layout = nil
    M._EngineTick()
    check(m.st.live and c.alpha == 1, "read right on the next pass: live again")
    -- a slot whose rectangle cannot be read, with an aura (not idle), is unproven
    slot.geo = false
    m.eng.parts[1].ok = false
    Aura("player", "Spirit Tap", { expirationTime = __now + 15, duration = 15 })
    fire("UNIT_AURA", "player")
    M._EngineTick()
    check(not m.st.live and c.alpha == 0, "unreadable with its aura up: unproven")
    for i = 1, 6 do M._EngineTick() end
    check(__logged.gunsightpriest_engine_unreadable, "logged after five passes")
    __logged.gunsightpriest_engine_unreadable = nil
    -- an idle slot (the aura readably absent) keeps the proof it had
    slot.geo = nil
    M._EngineTick()
    check(m.st.live, "read right again: live")
    Aura("player", "Spirit Tap", nil)
    fire("UNIT_AURA", "player")
    slot.geo = false
    M._EngineTick()
    check(m.st.live and c.alpha == 1, "an idle slot with no rectangle keeps its proof")
    NoLog()
""")

case("nothing_is_written_to_a_slot_region_and_no_aura_is_read_in_combat", """
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    Aura("player", "Spirit Tap", { expirationTime = __now + 15, duration = 15 })
    fire("UNIT_AURA", "player")
    local c = Container("spirit")
    check(Med("spirit").st.live and c.alpha == 1)
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    for i = 1, 90 do Tick(1 / 30) end
    fire("PARTY_KILL", "P", "T")
    fire("UNIT_AURA", "player")
    SPEC.seat({ x = 0, y = 0, w = 220, h = 140 })           -- a rescale in a fight
    SetCfg(RIGHTSIDE, "pom")
    SetCfg(RIGHTSIDE, "spirit")
    SetCfg(FIRENUDGE, false)
    SetCfg(FIRENUDGE, true)
    M._EngineTick()
    M._EnsureEngines()
    check(ENGINE_COMBAT_WRITES == 0, "no slot region written in combat: " .. ENGINE_COMBAT_WRITES)
    check(AURA_IN_COMBAT == 0, "no aura read in combat")
    check(c.alpha == 1 and c.enabled and Shown(c), "the container is left as it was")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(Med("spirit").eng.parts[1].num.size == 18 and ENGINE_COMBAT_WRITES == 0, "out of combat the number is seated again")
    NoLog()
""")

case("a_failed_build_is_retried_once_and_three_failed_passes_give_it_up", """
    __auraFail = true
    SetCfg(RIGHTSIDE, "spirit")
    SetTarget("friend")
    Build()
    Unlock()
    local m = Med("fire")
    check(m.st.failures == 1 and m.st.retryAt and not m.st.container and not m.st.gaveUp, "one counted attempt")
    check(__logged.gunsightpriest_engine_build, "said once")
    check(#__containers == 2 and not m.st.live, "a parked container, no cover")
    fire("SPELLS_CHANGED")
    check(m.st.failures == 1, "a second try in the same pass is not made")
    M._EngineTick()
    check(m.st.failures == 1 and #__containers == 2, "nor before the retry is due")
    __now = __now + 11
    M._EngineTick()
    check(m.st.failures == 1 and m.st.retryAt == nil and #__containers == 4, "the one uncounted retry runs once")
    __now = __now + 11
    M._EngineTick()
    check(#__containers == 4, "and is not repeated")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    fire("SPELLS_CHANGED")
    check(m.st.failures == 1 and #__containers == 4, "nothing is built in combat")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(m.st.failures == 2 and not m.st.gaveUp, "the next out of combat pass counts again")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(m.st.failures == 3 and m.st.gaveUp, "three failed passes give the route up for the session")
    local n = #__containers
    __auraFail = false
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(#__containers == n and not m.st.live, "given up: no further attempt")
    check(Parts().meds[1].st.gaveUp, "Spirit Tap too")
    Tick(0.05)
    check(Med("fire").face.fsCell == M.MEDCELL.body, "the base still follows a plain read: the nudge")
""")

case("a_client_without_the_template_gives_the_route_up_for_the_session", """
    __template = {}
    SetCfg(RIGHTSIDE, "spirit")
    Build()
    Unlock()
    check(Med("fire").st.gaveUp and Med("spirit").st.gaveUp and #__containers == 0, "no template: given up, nothing built")
    check(__logged.gunsightpriest_engine_template, "said once")
    Tick(0.05)
    check(Med("fire").face.fsCell == M.MEDCELL.body and Med("spirit").face.fsCell == M.MEDCELL.ghost, "the plain looks carry on")
""")

case("a_new_rank_id_rebuilds_the_container_and_the_rebuilds_are_capped", """
    SetCfg(RIGHTSIDE, "spirit")
    Build()
    Unlock()
    local m = Med("fire")
    check(#__containers == 2 and m.st.rebuilds == 0)
    local first = Container("fire")
    for i = 1, 3 do
        __ids["Inner Fire"] = 9000 + i                         -- the name resolves to a rank the filter never had
        fire("SPELLS_CHANGED")
        check(m.st.rebuilds == i and Container("fire") ~= first and #__containers == 2 + i, "rebuild " .. i)
        check(first.enabled == false and first.alpha == 0 and first.shown == false, "the old one is parked")
    end
    __ids["Inner Fire"] = 9999
    fire("SPELLS_CHANGED")
    check(m.st.rebuilds == 3 and #__containers == 5, "capped at three")
    check(__logged.gunsightpriest_engine_cap, "and a line says to /reload")
    check(Slot("fire").opts.candidateFilters.includeSpellIDs[9003], "the newest container covers the newest id")
""")

case("no_secret_is_ever_compared_in_the_right_side", """
    -- a secret slot rectangle, a secret shown flag, a secret group answer, a secret aura read, a secret kill, a secret GUID
    __slotGeo = { Secret("l"), Secret("t"), Secret("r"), Secret("b") }
    SetCfg(RIGHTSIDE, "auto")
    SetTarget("friend")
    function IsInRaid() return Secret("raid") end
    function IsInInstance() return Secret("inside"), Secret("kind") end
    Build()
    Unlock()
    check(R.Mode() == "medallions", "a secret group answer is not a group")
    M._EngineTick()
    check(not Med("spirit").st.live, "a secret rectangle is unproven, not an error")
    C_UnitAuras.GetAuraDataBySpellName = function() return Secret("aura") end
    fire("UNIT_AURA", "player")
    check(R.PlainUp("spirit") == nil and R.PlainUp("fire") == nil, "a secret aura read tells nothing")
    fire("PARTY_KILL", Secret("attacker"), Secret("target"))
    check(R.KillAt() == nil, "a secret killer is ignored")
    function UnitGUID() return Secret("guid") end
    fire("PARTY_KILL", "P", "T")
    check(R.KillAt() == nil, "a secret own GUID is ignored")
    Tick(0.05)
    SetCfg(RIGHTSIDE, "spirit")
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    NoLog()
""")

case("the_kill_ledger_opens_the_pull_now_cue_out_of_combat_only", """
    SetCfg(RIGHTSIDE, "spirit")
    SetCfg(FIRENUDGE, false)
    SetTarget("friend")
    Build()
    Unlock()
    local cue = Parts().cueGlow
    Aura("player", "Spirit Tap", { expirationTime = __now + 15, duration = 15 })
    fire("UNIT_AURA", "player")
    check(not R.Cue(__now) and not Shown(cue), "no kill yet")
    fire("PARTY_KILL", "G9", "T")
    check(R.KillAt() == nil and not Shown(cue), "someone else's kill is not ours")
    fire("PARTY_KILL", "P", "T")
    check(R.KillAt() == __now and R.Cue(__now), "our own kill opens the window")
    check(Shown(cue) and Ticking() and cue.color[1] == 1 and cue.color[2] > 0.6 and cue.color[3] < 0.4, "the amber ring breathes")
    Tick(0.4)
    check(Shown(cue) and cue.color[4] > 0 and cue.color[4] <= 0.9, "within 0.9")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    check(not Shown(cue), "never in combat")
    fire("PARTY_KILL", "P", "T")
    check(not Shown(cue), "a kill in combat shows nothing yet")
    __combat = false
    fire("PLAYER_REGEN_ENABLED")
    check(Shown(cue), "the window is still open when the fight ends")
    Tick(16)
    check(not Shown(cue) and not R.Cue(__now) and not Ticking(), "and lapses after 15 s")
    fire("PARTY_KILL", "P", "T")
    Aura("player", "Spirit Tap", nil)
    fire("UNIT_AURA", "player")
    check(not Shown(cue) and not R.Cue(__now), "a kill that gave no Spirit Tap (grey mob) has no cue")
    NoLog()
""")

case("the_state_line_reports_the_engine_route_for_the_live_test", """
    ForeverSTUwaveDB = {}
    SetCfg(RIGHTSIDE, "spirit")
    Build()
    Unlock()
    local saved = ForeverSTUwaveDB.gunsightPriestRight
    check(saved and type(saved.line) == "string", "a line is saved")
    check(saved.line:find("spirit known=true armed=true live=true", 1, true) and saved.line:find("fire known=true", 1, true), saved.line)
    check(saved.line:find("slot1 shown=?(secret", 1, true), "a secret flag reads as unknown: " .. saved.line)
    local first = saved
    M._EngineTick()
    check(ForeverSTUwaveDB.gunsightPriestRight == first, "unchanged: not rewritten")
    ForeverSTUwaveDB = 5
    M._EngineTick()
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
loadAddonFile(RIGHT_SRC, "Modules/CombatHud/PriestRight.lua")
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
    g.DATA_SRC, g.RIGHT_SRC, g.PRIEST_SRC = DATA, RIGHT, MODULE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.DATA_SRC, g.RIGHT_SRC, g.MODULE_SRC = DATA, RIGHT, MODULE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def static_checks() -> list[str]:
    errs = []
    for name in ("priest_shield", "priest_shield_glint", "priest_shield_rays", "priest_shield_ws", "priest_shield_lit",
                 "priest_mending", "priest_heart_cd", "priest_medallion"):
        if not (MEDIA / f"{name}.tga").exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_priest_shield.py)")
        if f"{name}.tga" not in MODULE:
            errs.append(f"the module does not use {name}.tga")
    for gen_list, lua_table in (("SHIELD_CELLS", "CELL"), ("MENDING_CELLS", "MCELL"), ("MEDALLION_CELLS", "MEDCELL")):
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
                     (r"GLINT_FRAMES = (\d+)", r"GLINT_FRAMES = (\d+)"),
                     (r"MED_BOX, MED_CENTER = (\d+)", r"MED = \{[^}]*BOX = (\d+)"),
                     (r"MED_BOX, MED_CENTER = \d+, (\d+)", r"MED = \{[^}]*CENTER = (\d+)")):
        a, b = re.search(gen, GENERATOR), re.search(lua, MODULE)
        if not (a and b and a.group(1) == b.group(1)):
            errs.append(f"geometry drifted: generator {gen!r} vs module {lua!r}")
    for path in ("Modules/CombatHud/PriestShields.lua", "Modules/CombatHud/PriestRight.lua",
                 "Modules/CombatHud/GunsightPriest.lua", "Modules/CombatHud/GunsightPriestClick.lua"):
        src = (ADDON / path).read_text(encoding="utf-8")
        if re.search("[\u2013\u2014]", src):
            errs.append(f"{path}: an em or en dash")
        if re.search(r"\b(bots?|automat\w*)\b", src, re.I):
            errs.append(f"{path}: flagged wording")
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        a, d, r, m, c = (toc.index(f"Modules/CombatHud/{n}.lua")
                         for n in ("GunsightAreas", "PriestShields", "PriestRight", "GunsightPriest", "GunsightPriestClick"))
        if not (a < d < r < m < c):
            errs.append("toc order: GunsightAreas, PriestShields, PriestRight, GunsightPriest, GunsightPriestClick")
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
