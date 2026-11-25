#!/usr/bin/env python3
"""Runs the real GunsightWarlock.lua, WarlockState.lua and the generated WarlockArt.lua (the Warlock's Gunsight Class Module).

The module draws the concept "The Grimoire" (2026-11-20): the demon's pact book lit from the bottom by its health, five soul
crystals, and one cue at a time on the right that the book acts out. These checks pin:

  * the art: the committed WarlockArt.lua, warlock_grimoire.tga and warlock_grimoire_lit.tga are exactly what the generator
    writes now; the toc loads the art and the state before the module;
  * GunsightClass.lua no longer claims WARLOCK (the Rogue and the Druid are not this file's business), and under the REAL
    GunsightAreas.lua with both modules loaded a Warlock gets this one;
  * registration: one "class" module for WARLOCK only, a frame named ForeverSTUwaveGunsightWarlock under the host;
  * the shards: a crystal per shard up to five, "+N" past five, question marked crystals for an unknown or secret count;
  * the cue lane: SUMMON (with a note: the demon and the shard it costs, IMP FREE, NO SHARD), BINDING, BOLT and FIRE with a drain bar for the
    10 s window (amber for its last fifth), TAP, DRAIN, REAPING with a bar for the channel's ticks, and the priority between them;
  * the switches: every cue has an off switch that removes exactly that cue;
  * the demon: alive (the engine fills the lit book from the SECRET health, passed straight to the bar, never compared), gone
    (the dark book and its amber outline), unreadable ("?" and NO READ); the demon's identity from the family or the Summon ledger;
  * the events: a gain flash, a spend (with the binding when a Summon was just cast), the Life Tap burst;
  * reduced motion: nothing breathes, blinks, shakes or flies; the state still reads;
  * onShow subscribes and starts one OnUpdate, onHide stops both; a rescale rewrites every size;
  * the paint allocates nothing once warm;
  * under the real areas the host hides with no target, the module stops, and it comes back with a target.

    python3 tools/gunsightwarlock-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
CH = ADDON / "Modules/CombatHud"
MODULE = (CH / "GunsightWarlock.lua").read_text(encoding="utf-8")
STATE = (CH / "WarlockState.lua").read_text(encoding="utf-8")
ARTLUA = (CH / "WarlockArt.lua").read_text(encoding="utf-8")
CLASSLUA = (CH / "GunsightClass.lua").read_text(encoding="utf-8")
GENERATOR = ROOT / "tools/assets/generate_warlock_grimoire.py"
MEDIA = ADDON / "Media/Textures"

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
__all, __frames = {}, {}
local seq = 0
function New(kind, parent)
    seq = seq + 1
    local o = setmetatable({ kind = kind, shown = true, parent = parent, seq = seq, level = 0 }, Obj)
    __all[#__all + 1] = o
    return o
end
function Obj:SetPoint(p, rel, rp, x, y) self.pt = { p, rel, rp, x or 0, y or 0 } end
function Obj:ClearAllPoints() self.pt = nil end
function Obj:SetAllPoints(rel) self.pt = { "TOPLEFT", rel, "TOPLEFT", 0, 0 } end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b) self.tc = { l, r, t, b } end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a or 1 } end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:SetStatusBarTexture(p) self.barTex = p end
function Obj:SetMinMaxValues(a, b) self.min, self.max = a, b end
function Obj:SetValue(v) self.value = v end
function Obj:CreateTexture(name, layer, inh, sub) local t = New("Texture", self); t.layer = layer; t.sub = sub or 0; return t end
function CreateFrame(kind, name, parent)
    local f = New(kind or "Frame", parent); f.name = name
    __frames[#__frames + 1] = f
    return f
end
__now = 1000
__scale = 1
function GetTime() return __now end
SECRET = setmetatable({}, { __tostring = function() return "secret" end })
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
SUBS = {}
HUD = nil
CFG = {}
FS = {
    IsSecret = function(v) return v == SECRET end,
    Gunsight = { ui = function(px) return px * __scale end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end },
    GunsightAreas = Areas,
    Config = { RegisterDefault = function() end, Get = function(k) return CFG[k] end },
    FrameHelpers = { RegisterEvent = function(frame, ev) WSFRAME = frame; frame.events = frame.events or {}; frame.events[ev] = true; return true end },
    Hud = {
        Subscribe = function(fn) SUBS[#SUBS + 1] = fn; if HUD then fn(HUD) end; return fn end,
        Unsubscribe = function(fn) for i = #SUBS, 1, -1 do if SUBS[i] == fn then table.remove(SUBS, i) end end end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
}
function push(state) HUD = state; for i = 1, #SUBS do SUBS[i](state) end end

-- the world the state reads
PET = { exists = true, dead = false, family = "Voidwalker", unreadable = false }
DEAD = false
BOOK = { ["Drain Soul"] = 1, ["Life Tap"] = 2, ["Shadow Bolt"] = 3, ["Summon Imp"] = 4 }
NAMES = { [100] = "Summon Voidwalker", [101] = "Summon Imp", [102] = "Summon Felhunter", [103] = "Summon Succubus", [104] = "Life Tap" }
USABLE = { usable = true, noMana = false }
HEALTH = { v = SECRET, m = SECRET }
UnitClass = function() return "Warlock", "WARLOCK" end
UnitExists = function(u) if u ~= "pet" then return true end if PET.unreadable then return SECRET end return PET.exists end
UnitIsDead = function(u) return PET.dead end
UnitIsDeadOrGhost = function() return DEAD end
UnitCreatureFamily = function() return PET.family end
UnitHealth = function() return HEALTH.v end
UnitHealthMax = function() return HEALTH.m end
C_Spell = {
    GetSpellInfo = function(n) if BOOK[n] then return { spellID = BOOK[n] } end end,
    GetSpellName = function(id) return NAMES[id] end,
    IsSpellUsable = function() return USABLE.usable, USABLE.noMana end,
}
assert(loadstring(ARTLUA_SRC, "@WarlockArt.lua"))("forever-stuwave", FS)
assert(loadstring(STATE_SRC, "@WarlockState.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightWarlock.lua"))("forever-stuwave", FS)
M, Art, WS = FS.GunsightWarlock, FS.WarlockArt, FS.WarlockState
SPEC = Areas.specs[1] and Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function P() return M.parts end
function On(t) return t.shown and t.fsOn == true end
function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
function Paint(t) __now = t or __now; M.Paint(__now) end
-- the world changes, the state re-reads, the module repaints
function World()
    WS.Refresh()
    Paint(__now)
end
function HS(n, o)
    o = o or {}
    local st = { shards = n, procs = {}, inCombat = true }
    if o.trance then st.procs[#st.procs + 1] = { key = "shadow_trance", glow = "gold", active = true } end
    if o.decim then st.procs[#st.procs + 1] = { key = "decimation", glow = "red", active = true } end
    if o.reap then st.channel = { key = "drain_soul", done = o.done or 0, ticks = o.ticks or 5 } end
    return st
end
function Txt(l)
    local o = {}
    for i = 1, l.n do
        local t = l[i]
        if On(t) then
            local n = t.fsName:sub(3)
            o[#o + 1] = ({ minus = "-", q = "?", plus = "+", dot = "." })[n] or n
        end
    end
    return table.concat(o)
end
function ColorIs(t, c, a)
    return t.color and Near(t.color[1], c[1], 1e-4) and Near(t.color[2], c[2], 1e-4) and Near(t.color[3], c[3], 1e-4)
        and (a == nil or Near(t.color[4], a, 1e-4))
end
function Lit()
    local n = 0
    for i = 1, 5 do if On(P().gem[i]) and ColorIs(P().gem[i], { 1, 1, 1 }, 1) and P().gem[i].fsName ~= nil then n = n + 1 end end
    return n
end
function NoLog()
    for k, v in pairs(__logged or {}) do error("logged " .. k .. ": " .. tostring(v)) end
end
function Fire(event, unit, spell)
    WSFRAME.scripts.OnEvent(WSFRAME, event, unit or "player", "guid", spell)
end
function Cue() return M.D.cue end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_warlocks_only", """
    assert(SPEC and SPEC.classes[1] == "WARLOCK" and #SPEC.classes == 1)
    assert(not M.frame, "nothing is built at load")
    local m = Build()
    assert(m and m.name == "ForeverSTUwaveGunsightWarlock" and m.parent == HOST)
    NoLog()
""")

case("the_state_listens_for_the_players_casts_and_the_pet_from_load", """
    for _, ev in ipairs({ "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED",
        "UNIT_SPELLCAST_INTERRUPTED", "UNIT_PET", "PLAYER_DEAD", "PLAYER_ALIVE", "SPELLS_CHANGED" }) do
        assert(WSFRAME.events[ev], "missing " .. ev)
    end
    assert(not WSFRAME.events.COMBAT_LOG_EVENT_UNFILTERED, "never the combat log")
""")

case("the_shards_light_a_gem_each_up_to_five_and_the_number_follows", """
    Build()
    for n = 0, 7 do
        push(HS(n))
        Paint(__now)
        assert(Lit() == math.min(n, 5), n .. " shards lit " .. Lit() .. " gems")
        assert(Txt(P().more) == (n > 5 and ("+" .. (n - 5)) or ""), "past five: " .. Txt(P().more))
        assert(P().sock[1].fsName == "crys_empty")
    end
    push(HS(nil)); Paint(__now)
    assert(Lit() == 0 and Txt(P().more) == "" and P().sock[1].fsName == "crys_q", "unknown: crystals with a question mark")
    push({ shards = SECRET, procs = {} }); Paint(__now)
    assert(M.D.shards == nil and P().sock[1].fsName == "crys_q", "a secret count is unknown, never compared")
    NoLog()
""")

case("a_shard_spent_or_gained_while_hidden_plays_nothing_when_the_module_shows", """
    Build()
    push(HS(4)); Paint(__now)
    SPEC.onHide("lower")
    HUD = HS(3)                              -- a summon with no target: the module is hidden, the Hud moves on
    __now = __now + 30
    SPEC.onShow("lower")                     -- Subscribe pushes the current state at once
    Paint(__now)
    assert(M.D.spendAt == nil or __now - M.D.spendAt > 5, "no spend plays on show for a shard spent while hidden")
    assert(M.D.gainAt == nil or __now - M.D.gainAt > 5, "and no gain")
    assert(Lit() == 3, "the count is the current one")
    push(HS(2)); Paint(__now)
    assert(M.D.spendAt == __now, "a spend after the show still plays")
    NoLog()
""")

case("the_cue_lane_names_what_to_do_and_the_priority_holds", """
    Build()
    push(HS(3)); World()
    assert(Cue() == nil and Txt(P().word) == "" and Txt(P().name) == "VOIDWALKER", "idle: the demon's name, no cue")
    -- drain
    push(HS(2)); Paint(__now)
    assert(Cue() == "drain" and Txt(P().word) == "DRAIN" and Txt(P().note) == "", "only SUMMON has a note")
    push(HS(3)); Paint(__now)
    -- tap
    USABLE.noMana = true; World()
    assert(Cue() == "tap" and Txt(P().word) == "TAP", "tap: " .. tostring(Cue()))
    push(HS(1)); Paint(__now)
    assert(Cue() == "tap", "tap beats drain")
    -- summon beats tap
    PET.exists = false; World()
    assert(Cue() == "summon" and Txt(P().word) == "SUMMON" and Txt(P().note) == "VOIDWALKER-1", "summon: " .. Txt(P().note))
    -- fire beats summon, bolt beats fire
    push(HS(1, { decim = true })); Paint(__now)
    assert(Cue() == "fire" and Txt(P().word) == "FIRE" and Txt(P().note) == "")
    push(HS(1, { decim = true, trance = true })); Paint(__now)
    assert(Cue() == "bolt" and Txt(P().word) == "BOLT")
    -- binding beats bolt
    Fire("UNIT_SPELLCAST_START", "player", 100)
    Paint(__now)
    assert(Cue() == "binding" and Txt(P().word) == "BINDING" and On(P().ring), "binding: " .. tostring(Cue()))
    -- reaping beats everything
    push(HS(1, { decim = true, trance = true, reap = true, done = 2, ticks = 5 })); Paint(__now)
    assert(Cue() == "reap" and Txt(P().word) == "REAPING")
    assert(On(P().track) and P().fill.fsW == 24 and ColorIs(P().fill, M.COLORS.violet), "the channel bar: 2 of 5 ticks of 60 px: " .. tostring(P().fill.fsW))
    Fire("UNIT_SPELLCAST_STOP", "player", 100)
    NoLog()
""")

case("the_summon_cue_names_the_demon_and_its_shard_and_the_imp_is_free", """
    Build()
    PET.exists = false; PET.family = "Voidwalker"
    push(HS(3)); World()
    -- a remembered demon: the voidwalker was out first
    PET.exists = true; World()
    PET.exists = false; World()
    assert(Txt(P().note) == "VOIDWALKER-1" and ColorIs(P().word[1], M.COLORS.amber))
    push(HS(0)); Paint(__now)
    assert(Txt(P().note) == "NOSHARD" and ColorIs(P().word[1], M.COLORS.pink), "no shard: pink")
    assert(ColorIs(P().halo, M.COLORS.pink) and ColorIs(P().rim, M.COLORS.pink), "the halo and the rim warn too")
    PET.exists = true; PET.family = "Imp"; World()
    PET.exists = false; World()
    push(HS(0)); Paint(__now)
    assert(Txt(P().note) == "IMPFREE" and ColorIs(P().word[1], M.COLORS.amber), "an imp costs nothing, even with no shard")
    -- the gem that will be spent blinks amber
    push(HS(3)); PET.family = "Felhunter"; PET.exists = true; World(); PET.exists = false; World()
    local amber, violet = false, false
    for k = 0, 20 do Paint(__now + k * 0.05); local n = P().gem[3].fsName; amber = amber or n == "crys_amber"; violet = violet or n == "crys_lit" end
    assert(amber and violet, "the last lit crystal blinks")
    NoLog()
""")

case("the_proc_cues_carry_a_ten_second_drain_bar_that_turns_amber_at_the_end", """
    Build()
    push(HS(3, { trance = true })); Paint(__now)
    local t0 = __now
    assert(Cue() == "bolt" and P().fill.fsW == 60 and ColorIs(P().fill, M.COLORS.bolt), "a full bar at the start")
    Paint(t0 + 5)
    assert(P().fill.fsW == 30, "half at 5 s: " .. tostring(P().fill.fsW))
    Paint(t0 + 8.5)
    assert(ColorIs(P().fill, M.COLORS.amber) and P().fill.fsW == 9, "amber in the last fifth: " .. tostring(P().fill.fsW))
    Paint(t0 + 11)
    assert(not On(P().fill) and Cue() == "bolt", "past ten seconds the bar is empty and the cue stays while the proc does")
    push(HS(3)); Paint(__now)
    assert(Cue() == nil and not On(P().track), "the proc going away ends the cue")
    push(HS(3, { decim = true })); Paint(__now)
    assert(Cue() == "fire" and ColorIs(P().fill, M.COLORS.orange))
    NoLog()
""")

case("every_cue_has_an_off_switch_that_removes_only_that_cue", """
    Build()
    local function with(key, setup, cue)
        setup()
        World()
        assert(Cue() == cue, key .. " on: wanted " .. tostring(cue) .. " got " .. tostring(Cue()))
        CFG[key] = false
        Paint(__now)
        assert(Cue() ~= cue, key .. " off still shows " .. tostring(Cue()))
        CFG[key] = nil
    end
    with("gunsight.warlock.cue.summon", function() PET.exists = false; push(HS(3)) end, "summon")
    PET.exists = true
    with("gunsight.warlock.cue.procs", function() push(HS(3, { trance = true })) end, "bolt")
    with("gunsight.warlock.cue.tap", function() USABLE.noMana = true; push(HS(3)) end, "tap")
    USABLE.noMana = false
    with("gunsight.warlock.cue.drain", function() push(HS(1)) end, "drain")
    with("gunsight.warlock.cue.drain", function() push(HS(1, { reap = true, ticks = 5 })) end, "reap")
    -- with the Life Tap not in the book the cue never shows
    BOOK["Life Tap"] = nil; USABLE.noMana = true; push(HS(3)); World()
    assert(Cue() == nil, "Life Tap unknown: no tap cue")
    -- a new Warlock with no Summon in the book yet (the Imp comes from a level 4 quest): no SUMMON, never "NO SHARD"
    BOOK["Summon Imp"] = nil; USABLE.noMana = false; PET.exists = false; push(HS(0)); World()
    assert(Cue() ~= "summon" and Txt(P().word) ~= "SUMMON", "no Summon known: no SUMMON cue, got " .. tostring(Cue()))
    BOOK["Summon Imp"] = 4; World()
    assert(Cue() == "summon", "learning the Imp brings the cue: " .. tostring(Cue()))
    NoLog()
""")

case("the_book_is_lit_by_the_secret_health_through_the_bar_and_never_compared", """
    Build()
    push(HS(3)); World()
    local bar = P().bar
    assert(bar.shown and bar.barTex:match("warlock_grimoire_lit%.tga$"), "alive: the lit book")
    assert(bar.value == SECRET and bar.max == SECRET and bar.min == 0, "the secret health goes straight to the bar")
    assert(P().dim.fsName == "book_dark" and On(P().coverGem) and ColorIs(P().coverGem, { 168 / 255, 85 / 255, 247 / 255 }), "the gem in the demon's colour")
    assert(not On(P().rim), "no outline while the demon is out")
    HEALTH.v, HEALTH.m = 40, 100
    Paint(__now)
    assert(bar.value == 40 and bar.max == 100, "a plain health feeds the same")
    -- the demon is gone
    PET.exists = false; World()
    assert(not bar.shown and On(P().rim), "gone: the outline")
    assert(P().dim.fsName == "book_dark", "the dark book stays")
    PET.exists = true; PET.dead = true; World()
    assert(not bar.shown and On(P().rim), "a dead demon reads as gone")
    -- unreadable
    PET.dead = false; PET.unreadable = true; World()
    assert(not bar.shown and Txt(P().unknownQ) == "?" and Txt(P().name) == "NOREAD", "unreadable: a question mark")
    assert(P().dim.fsName == "book_grey" and ColorIs(P().halo, M.COLORS.muted))
    NoLog()
""")

case("the_demon_is_the_family_else_the_summon_ledger", """
    Build()
    for _, pair in ipairs({ { "Imp", "imp" }, { "Voidwalker", "voidwalker" }, { "Succubus", "sayaad" }, { "Incubus", "sayaad" }, { "Felhunter", "felhunter" } }) do
        PET.family = pair[1]; PET.exists = true; World()
        assert(WS.Get().demon == pair[2], pair[1] .. " is " .. pair[2] .. ", got " .. tostring(WS.Get().demon))
    end
    PET.family = SECRET; World()
    assert(WS.Get().demon == "felhunter", "a secret family keeps the last known demon")
    Fire("UNIT_SPELLCAST_SUCCEEDED", "player", 102)
    assert(WS.Get().demon == "felhunter" and WS.Get().summonAt == __now)
    Fire("UNIT_SPELLCAST_SUCCEEDED", "player", 103)
    assert(WS.Get().demon == "sayaad", "a Summon cast names the demon")
    Fire("UNIT_SPELLCAST_SUCCEEDED", "player", 104)
    assert(WS.Get().tapAt == __now, "Life Tap is stamped")
    Fire("UNIT_SPELLCAST_START", "player", 100)
    assert(WS.Get().casting == true)
    Fire("UNIT_SPELLCAST_FAILED", "player", 100)
    assert(WS.Get().casting == false)
    Fire("UNIT_SPELLCAST_START", "target", 100)
    assert(WS.Get().casting == false, "another unit's cast is not ours")
    NoLog()
""")

case("a_gain_a_spend_the_binding_and_the_life_tap_burst_play", """
    Build()
    push(HS(3)); Paint(__now)
    local t0 = __now
    push(HS(4)); Paint(t0 + 0.1)
    assert(On(P().evGem) and P().evGem.fsName == "crys_white", "a shard lands: the white crystal")
    assert(On(P().gainRing[1]), "and a ring")
    Paint(t0 + 0.5)
    assert(not On(P().evGem) and On(P().gainRing[2]), "the flash is short, the ring runs")
    Paint(t0 + 1)
    assert(not On(P().gainRing[1]), "and ends")
    -- a spend without a summon: the sparks fly outward
    push(HS(3)); Paint(__now + 0.1)
    assert(On(P().evSpend) and P().evSpend.fsName == "crys_amber" and not M.D.bind, "a plain spend")
    -- a spend right after a Summon: the binding
    Fire("UNIT_SPELLCAST_SUCCEEDED", "player", 100)
    push(HS(2)); Paint(__now + 0.2)
    assert(M.D.bind and On(P().trailSpend[1]) and P().trailSpend[1].fsX < 96, "a Summon spend flies toward the book")
    -- the Life Tap burst
    Fire("UNIT_SPELLCAST_SUCCEEDED", "player", 104)
    Paint(__now + 0.2)
    local n = 0
    for i = 1, 24 do if On(P().burst[i]) then n = n + 1 end end
    assert(n == 24 and ColorIs(P().burst[1], M.COLORS.pink), "the ring of 24")
    Paint(__now + 1)
    assert(not On(P().burst[1]))
    NoLog()
""")

case("reduced_motion_stops_every_flourish_and_the_state_still_reads", """
    ForeverSTUwaveDB = { reducedMotion = true }
    Build()
    push(HS(3)); World()
    local a = P().halo.fsA
    for k = 1, 10 do Paint(__now + k * 0.31); assert(P().halo.fsA == a, "the halo holds still") end
    assert(not On(P().shine[1]) , "no shimmer")
    push(HS(3, { decim = true })); Paint(__now + 1)
    assert(Cue() == "fire" and Txt(P().word) == "FIRE")
    for i = 1, 10 do assert(not On(P().fire[i]), "no flames") end
    push(HS(3, { trance = true })); Paint(__now + 1)
    assert(not On(P().zapA) and not On(P().zapB), "no bolts")
    PET.exists = false; World()
    push(HS(3)); USABLE.noMana = false; Paint(__now + 1)
    assert(Cue() == "summon")
    local c, x = P().rim.fsA, P().dim.fsX
    for k = 1, 10 do Paint(__now + k * 0.1); assert(P().rim.fsA == c and P().dim.fsX == x, "no pulse, no shake") end
    for i = 1, 3 do assert(not On(P().drops[i]) and not On(P().motes[i])) end
    ForeverSTUwaveDB = nil
    NoLog()
""")

case("with_no_demon_dead_player_and_ghost_there_is_no_cue", """
    Build()
    PET.exists = false; DEAD = true; push(HS(3)); World()
    assert(Cue() == nil, "a dead Warlock gets no cue")
    DEAD = false; World()
    assert(Cue() == "summon")
    NoLog()
""")

case("every_sprite_the_module_draws_is_in_the_manifest", """
    Build()
    local seen = {}
    local function sweep()
        for _, o in ipairs(__all) do if o.kind == "Texture" and o.fsName then seen[o.fsName] = true end end
    end
    local states = {
        function() push(HS(3)) end, function() push(HS(1)) end, function() push(HS(7)) end, function() push(HS(nil)) end,
        function() PET.exists = false; push(HS(3)) end, function() push(HS(3, { trance = true })) end,
        function() PET.exists = true; USABLE.noMana = true; push(HS(3)) end, function() USABLE.noMana = false; push(HS(2, { reap = true, done = 1, ticks = 5 })) end,
        function() push(HS(3, { decim = true })) end,
    }
    for _, setup in ipairs(states) do
        setup(); World()
        for k = 0, 30 do Paint(__now + k * 0.07); sweep() end
    end
    local missing = {}
    for name in pairs(seen) do if not Art.sprites[name] then missing[#missing + 1] = name end end
    assert(#missing == 0, "not in the manifest: " .. table.concat(missing, ", "))
    local n = 0
    for _ in pairs(seen) do n = n + 1 end
    assert(n > 30, "the sweep exercised " .. n .. " sprites")
    NoLog()
""")

case("show_and_hide_drive_the_subscriptions_and_the_ticker", """
    local m = Build()
    assert(#SUBS == 1 and m.scripts.OnUpdate, "onShow subscribes and ticks")
    SPEC.onHide("lower")
    assert(#SUBS == 0 and not m.scripts.OnUpdate, "onHide stops both")
    SPEC.onShow("lower")
    assert(#SUBS == 1 and m.scripts.OnUpdate, "and they come back")
    -- the ticker paints at its own rate
    push(HS(3)); local before = P().word.fsA
    PET.exists = false
    __now = __now + 1
    m.scripts.OnUpdate(m, 0.2)
    assert(Cue() == "summon", "the ticker repaints and re-reads the demon")
    NoLog()
""")

case("a_rescale_rewrites_every_size", """
    Build()
    push(HS(3)); Paint(__now)
    local sock = P().sock[1]
    local w = sock.w
    __scale = 2
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    Paint(__now)
    assert(Near(sock.w, w * 2), "the sockets double with the scale: " .. tostring(sock.w) .. " vs " .. tostring(w))
    assert(Near(P().bar.w, Art.BOX * 1.25 * 2), "the book bar too")
    assert(Near(P().eye[1].w, 2 * 1.25 * 2) , "a flat region too")
    NoLog()
""")

case("the_paint_allocates_nothing_once_warm", """
    Build()
    for _, o in ipairs(__all) do
        o.SetPoint = function(self, p, rel, rp, x, y) self.px, self.py = x, y end
        o.SetTexCoord = function(self, l, r, t, b) self.tl = l end
        o.SetVertexColor = function(self, r, g, b, a) self.ca = a end
    end
    if jit then jit.off() end
    local setups = {
        function() push(HS(3)) end,
        function() PET.exists = false; push(HS(3)) end,
        function() PET.exists = true; push(HS(3, { trance = true })) end,
        function() push(HS(3, { decim = true })) end,
        function() USABLE.noMana = true; push(HS(3)) end,
        function() USABLE.noMana = false; push(HS(2, { reap = true, done = 2, ticks = 5 })) end,
        function() push(HS(nil)) end,
        function() push(HS(6)) end,
    }
    -- the growth of a measurement itself is flat (under 1 KB, the same over 40 or 400 paints); a per paint allocation is not,
    -- so each state is measured over 40 and over 400 paints and the two must agree
    local function growth(n, t0)
        collectgarbage("collect")
        collectgarbage("stop")
        local before = collectgarbage("count")
        for i = 0, n do Paint(t0 + i * 0.033) end
        local grew = collectgarbage("count") - before
        collectgarbage("restart")
        return grew
    end
    local worst = 0
    for _, setup in ipairs(setups) do
        setup(); WS.Refresh()
        local t0 = __now
        for i = 0, 100 do Paint(t0 + i * 0.033) end
        local g1 = growth(40, t0 + 3.4)
        local g2 = growth(400, t0 + 5)
        worst = math.max(worst, g2 - g1)
    end
    assert(worst < 0.5, "the paint allocates per call: 360 extra paints grew " .. worst .. " KB")
    NoLog()
""")


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
UnitExists = function(u) if u == "player" then return true end if u == "pet" then return true end return u == "target" and TARGET.exists end
UnitIsDead = function() return false end
UnitIsDeadOrGhost = function() return false end
UnitCreatureFamily = function() return "Voidwalker" end
UnitHealth = function() return 50 end
UnitHealthMax = function() return 100 end
C_Spell = { GetSpellInfo = function(n) return { spellID = 1 } end, GetSpellName = function() return "x" end, IsSpellUsable = function() return true, false end }
loadAddonFile(AREAS_SRC, "Modules/CombatHud/GunsightAreas.lua")
UnitClass = function() return "Warlock", "WARLOCK" end
loadAddonFile(CLASS_SRC, "Modules/CombatHud/GunsightClass.lua")
loadAddonFile(ARTLUA_SRC, "Modules/CombatHud/WarlockArt.lua")
loadAddonFile(STATE_SRC, "Modules/CombatHud/WarlockState.lua")
loadAddonFile(MODULE_SRC, "Modules/CombatHud/GunsightWarlock.lua")
push({ shards = 3, procs = {}, inCombat = false })
fire("ADDON_LOADED", "forever-stuwave")
fire("PLAYER_LOGIN")

local host = FS.Gunsight and FS.GunsightAreas.Host("lower")
check(host, "the real areas hand out a lower host")
check(isVisible(host), "a target shows the host")
local G = FS.GunsightWarlock
check(G.frame and isVisible(G.frame), "the module (not the Rogue and Druid plate) is built and drawn under the host")
check(onUpdateFrames() == 1, "ticking: " .. onUpdateFrames())
check(isVisible(G.parts.sock[1]) and isVisible(G.parts.dim) and G.parts.bar, "the book is drawn")
TARGET.exists = false
fire("PLAYER_TARGET_CHANGED")
check(not isVisible(host) and not isVisible(G.frame) and not isVisible(G.parts.sock[1]), "no target hides the host and everything under it")
check(onUpdateFrames() == 0, "and stops the OnUpdate")
TARGET.exists = true
fire("PLAYER_TARGET_CHANGED")
check(isVisible(host) and isVisible(G.parts.sock[1]), "a target brings it back")
check(onUpdateFrames() == 1, "and the ticker with it")
for k, v in pairs(DEGRADED) do error("degraded " .. k .. ": " .. tostring(v)) end
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
    g.GUNSIGHT_SRC = (CH / "Gunsight.lua").read_text(encoding="utf-8")
    g.AREAS_SRC = (CH / "GunsightAreas.lua").read_text(encoding="utf-8")
    g.CLASS_SRC = CLASSLUA
    g.ARTLUA_SRC, g.MODULE_SRC, g.STATE_SRC = ARTLUA, MODULE, STATE
    g.HAS_TARGET_SRC = gs.theme_target_rule_lua()
    g.SECRET = lua.eval("setmetatable({}, { __tostring = function() return 'secret' end })")
    try:
        lua.execute(REAL_CASE)
    except LuaError as e:
        return str(e)
    return None


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.ARTLUA_SRC, g.MODULE_SRC, g.STATE_SRC = ARTLUA, MODULE, STATE
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def static_checks() -> list[str]:
    """The committed art is exactly what the generator writes now; the toc and the class list are right."""
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, FS_ASSET_OUTPUT_DIR=tmp, FS_ART_LUA_OUTPUT=str(Path(tmp) / "WarlockArt.lua"))
        run = subprocess.run([sys.executable, str(GENERATOR)], env=env, capture_output=True, text=True)
        if run.returncode != 0:
            return [f"the generator failed: {run.stderr.strip()[-400:]}"]
        if (Path(tmp) / "WarlockArt.lua").read_text(encoding="utf-8") != ARTLUA:
            errs.append("WarlockArt.lua differs from the generator's (run tools/assets/generate_warlock_grimoire.py)")
        names = ["warlock_grimoire", "warlock_grimoire_lit"]
        for name in names:
            mine = MEDIA / f"{name}.tga"
            if not mine.exists():
                errs.append(f"missing texture {name}.tga")
            elif mine.read_bytes() != (Path(tmp) / f"{name}.tga").read_bytes():
                errs.append(f"{name}.tga differs from the generator's")
    toc = [line.strip() for line in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()]
    art, state, mod = (f"Modules/CombatHud/{n}.lua" for n in ("WarlockArt", "WarlockState", "GunsightWarlock"))
    if not all(x in toc for x in (art, state, mod)) or not toc.index(art) < toc.index(mod) or not toc.index(state) < toc.index(mod):
        errs.append("the toc must load WarlockArt.lua and WarlockState.lua before GunsightWarlock.lua")
    classes = re.search(r"local CLASSES = \{([^}]*)\}", CLASSLUA) or re.search(r"classes = \{([^}]*)\}", CLASSLUA)
    if not classes or "WARLOCK" in classes.group(1):
        errs.append("GunsightClass.lua must not claim WARLOCK any more")
    for path in (CH / "GunsightWarlock.lua", CH / "WarlockState.lua", GENERATOR, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        if chr(0x2014) in text:
            errs.append(f"{path.name} has an em dash")
        if "Park" + "er" in text:
            errs.append(f"{path.name} names a person")
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
    name = "under_the_real_areas_a_warlock_gets_this_module_and_the_host_follows_the_target"
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
