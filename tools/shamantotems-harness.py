#!/usr/bin/env python3
"""Runs the real ShamanTotems.lua (the Shaman totem state, data only) headless.

The module keeps one record per totem slot (Fire 1, Earth 2, Water 3, Air 4) for the Gunsight Shaman module and, later, a
totem gone alert and Next Cast. The mock reproduces the client facts measured on this client:

  * out of combat GetTotemInfo is plain, and haveTotem is TRUE with a blank name when no totem stands;
  * in combat every GetTotemInfo return is a secret (a sentinel that raises on arithmetic, comparison and concatenation);
  * GetTotemDuration answers a plain object only while the slot has a live totem, in and out of combat;
  * UNIT_SPELLCAST_SUCCEEDED for "player" is plain.

The checks pin: an out of combat drop is up with a number; in combat the duration object says up and no secret is touched; haveTotem
with a blank name is NOT up; a drop in combat is stamped from the cast event with the table duration (either event order, a
higher rank through the spell name); a cleared slot is gone; the block count math; the unlocked rule; FAR from two plain
positions only (nil, secret, a changed instance, a Projection cast and a cleared slot never leave it set); subscribers; the
throttled Tick; the listeners and the TOC order.

The mock is strict. It is NOT the real client.

    python3 tools/shamantotems-harness.py

Exit 0 = every check passed. SHAMANTOTEMS_LUA=<path> runs another file in place of ShamanTotems.lua.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
TOTEMS = Path(os.environ.get("SHAMANTOTEMS_LUA") or ADDON / "Modules/CombatHud/ShamanTotems.lua")
TOTEMBAR = ADDON / "Modules/ActionBars/TotemBar.lua"
TOC = ADDON / "forever-stuwave.toc"

MOCK = r"""
NOW = 1000
function GetTime() return NOW end
function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg, eps)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < (eps or 1e-6),
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end

-- A secret: any arithmetic, comparison or concatenation raises, like the client's secret values.
SECRET = setmetatable({}, {
    __lt = function() error("SECRET_OP: compare", 2) end, __le = function() error("SECRET_OP: compare", 2) end,
    __add = function() error("SECRET_OP: arith", 2) end, __sub = function() error("SECRET_OP: arith", 2) end,
    __mul = function() error("SECRET_OP: arith", 2) end, __div = function() error("SECRET_OP: arith", 2) end,
    __unm = function() error("SECRET_OP: arith", 2) end, __concat = function() error("SECRET_OP: concat", 2) end,
    __len = function() error("SECRET_OP: len", 2) end,
    __index = function() error("SECRET_OP: index", 2) end,
    __call = function() error("SECRET_OP: call", 2) end,
})

DEGRADED = {}
FRAMES = {}
KNOWN_EVENTS = {}
for e in ([[PLAYER_LOGIN PLAYER_TOTEM_UPDATE PLAYER_REGEN_DISABLED PLAYER_REGEN_ENABLED PLAYER_ENTERING_WORLD SPELLS_CHANGED PLAYER_LEVEL_UP UNIT_SPELLCAST_SUCCEEDED]]):gmatch("%S+") do KNOWN_EVENTS[e] = true end
local FrameMT = {}
FrameMT.__index = FrameMT
function FrameMT:RegisterEvent(e)
    if not KNOWN_EVENTS[e] then error("Attempt to register unknown event \"" .. tostring(e) .. "\"", 2) end
    self.events[e] = true
end
function FrameMT:RegisterUnitEvent(e, unit)
    if not KNOWN_EVENTS[e] then error("Attempt to register unknown event \"" .. tostring(e) .. "\"", 2) end
    self.events[e] = true
    self.unitOnly = self.unitOnly or {}
    self.unitOnly[e] = unit
end
function FrameMT:UnregisterEvent(e) self.events[e] = nil end
function FrameMT:SetScript(n, fn) self.scripts[n] = fn end
function CreateFrame(kind)
    local f = setmetatable({ events = {}, scripts = {}, kind = kind }, FrameMT)
    FRAMES[#FRAMES + 1] = f
    return f
end
function fire(event, ...)
    local args, n = { ... }, select("#", ...)
    for _, f in ipairs({ unpack(FRAMES) }) do
        local only = f.unitOnly and f.unitOnly[event]
        local wanted = f.events[event] and f.scripts.OnEvent
        if wanted and only and not (args[1] == only) then wanted = false end
        if wanted then f.scripts.OnEvent(f, event, unpack(args, 1, n)) end
    end
end

-- The world: TOT[slot] = { name, start, dur, icon, spell } for a standing totem. COMBAT makes every GetTotemInfo return secret.
TOT, COMBAT, INFO_CALLS, OBJ_CALLS = {}, false, 0, 0
POS = nil                       -- { y, x, z, instance } or nil (instances)
LEVEL = 30
KNOWN_SPELLS = {}
SPELL_NAMES = {}
function GetTotemInfo(slot)
    INFO_CALLS = INFO_CALLS + 1
    if COMBAT then return SECRET, SECRET, SECRET, SECRET, SECRET, SECRET, SECRET end
    local t = TOT[slot]
    if t then return true, t.name, t.start, t.dur, t.icon or 136, 1, t.spell end
    return true, "", 0, 0, 0, 1, 0           -- haveTotem is TRUE with a blank name when no totem stands
end
OBJECTS = {}
function GetTotemDuration(slot)
    OBJ_CALLS = OBJ_CALLS + 1
    if not TOT[slot] then return nil end
    OBJECTS[slot] = OBJECTS[slot] or { object = slot }
    return OBJECTS[slot]
end
function UnitPosition() if POS == nil then return nil end return POS[1], POS[2], POS[3], POS[4] end
function UnitLevel() return LEVEL end
function IsPlayerSpell(id) return KNOWN_SPELLS[id] == true end
C_Spell = {
    GetSpellName = function(id) return SPELL_NAMES[id] end,
    GetSpellTexture = function(id) return 100000 + id end,
}
function UnitClass() return "Shaman", CLASS or "SHAMAN" end

FS = { IsSecret = function(v) return v == SECRET end, LogDegradeOnce = function(k, m) DEGRADED[k] = m end }

STEAM = { name = "Searing Totem", start = 990, dur = 30, spell = 3599 }
function load(opts)
    opts = opts or {}
    CLASS = opts.class or "SHAMAN"
    local fn = assert(loadstring(TOTEMS_SRC, "@ShamanTotems.lua"))
    fn("forever-stuwave", FS)
    fire("PLAYER_LOGIN")
    return FS.ShamanTotems
end
function dropOoc(slot, name, spell, dur)
    TOT[slot] = { name = name, start = NOW, dur = dur, spell = spell }
end
function recorder(T)
    local R = { n = 0, last = nil }
    T.Subscribe(function(slot, st) R.n = R.n + 1; R.last = slot end)
    return R
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("listeners_are_known_events_and_only_a_shaman_starts")(r"""
local T = load({ class = "WARRIOR" })
check(not T.IsStarted(), "a warrior must not start the totem listeners")
local n = 0
for _, f in ipairs(FRAMES) do for _ in pairs(f.events) do n = n + 1 end end
check(n == 0, "no event left registered for a warrior, got " .. n)
for k in pairs(FRAMES) do FRAMES[k] = nil end
FS.ShamanTotems = nil
local T2 = load({})
check(T2.IsStarted(), "a shaman starts")
local seen = {}
for _, f in ipairs(FRAMES) do for e in pairs(f.events) do seen[e] = true end end
for _, e in ipairs({ "PLAYER_TOTEM_UPDATE", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "UNIT_SPELLCAST_SUCCEEDED" }) do
    check(seen[e], "not listening for " .. e)
end
local unit
for _, f in ipairs(FRAMES) do if f.unitOnly and f.unitOnly.UNIT_SPELLCAST_SUCCEEDED then unit = f.unitOnly.UNIT_SPELLCAST_SUCCEEDED end end
check(unit == "player", "the cast event is filtered to the player")
check(next(DEGRADED) == nil, "a degrade was logged: " .. tostring(next(DEGRADED)))
""")

case("out_of_combat_drop_is_up_with_a_number")(r"""
local T = load()
local R = recorder(T)
TOT[1] = { name = "Searing Totem", start = NOW - 5, dur = 30, spell = 3599, icon = 135825 }
fire("PLAYER_TOTEM_UPDATE", 1)
local st = T.Get(1)
check(st.up and T.IsUp(1), "fire slot is up")
check(st.name == "Searing Totem" and st.icon == 135825 and st.spellID == 3599, "name icon and spell are read")
check(st.source == "read" and st.start == NOW - 5 and st.duration == 30, "start and duration are read")
near(st.expires, NOW + 25)
near(T.Remaining(1, NOW), 25)
near(T.Remaining(1, NOW + 100), 0, "never below zero")
near(T.Fraction(1, NOW), 25 / 30)
check(T.Blocks(1, NOW) == 7, "ceil(25/30*8) = 7, got " .. tostring(T.Blocks(1, NOW)))
check(T.DurationObject(1) ~= nil, "the duration object is kept")
check(R.n == 1 and R.last == 1, "one change for the fire slot")
for s = 2, 4 do check(not T.IsUp(s), "slot " .. s .. " stays down") end
""")

case("haveTotem_true_with_a_blank_name_is_not_up")(r"""
local T = load()
local R = recorder(T)
fire("PLAYER_TOTEM_UPDATE", 2)
fire("PLAYER_ENTERING_WORLD")
for s = 1, 4 do
    check(not T.IsUp(s), "slot " .. s .. " must be down while GetTotemInfo says true with a blank name")
    check(T.Remaining(s, NOW) == nil and T.Blocks(s, NOW) == nil and T.DurationObject(s) == nil, "no numbers for a down slot")
end
check(R.n == 0, "nothing changed")
""")

case("a_plain_duration_without_a_name_is_up")(r"""
local T = load()
TOT[3] = { name = "", start = NOW, dur = 300, spell = 5394 }
fire("PLAYER_TOTEM_UPDATE", 3)
check(T.IsUp(3), "a duration above zero is up")
""")

case("in_combat_secret_reads_are_up_through_the_duration_object")(r"""
local T = load()
-- out of combat the totem is read, then the fight starts
TOT[2] = { name = "Stoneskin Totem", start = NOW - 10, dur = 300, spell = 8071 }
fire("PLAYER_REGEN_DISABLED")
check(T.IsUp(2) and T.Get(2).source == "read", "numbers are taken at REGEN_DISABLED")
COMBAT = true
NOW = NOW + 20
fire("PLAYER_TOTEM_UPDATE", 2)           -- every return is secret; any arithmetic on one would raise
check(T.IsUp(2), "still up in combat through the object")
check(T.Get(2).source == "read" and T.Get(2).duration == 300, "the out of combat numbers are kept (fallback A)")
near(T.Remaining(2, NOW), 270)
check(T.Blocks(2, NOW) == 8, "ceil(270/300*8) = 8, got " .. tostring(T.Blocks(2, NOW)))
fire("PLAYER_REGEN_DISABLED"); fire("PLAYER_ENTERING_WORLD")
check(T.IsUp(2) and not T.IsUp(1), "other slots stay down in combat")
""")

case("in_combat_with_no_number_runs_on_the_object_alone")(r"""
local T = load()
TOT[4] = { name = "Grounding Totem", start = NOW, dur = 45, spell = 8177 }
COMBAT = true                              -- a /reload in the fight: nothing was ever read plain
fire("PLAYER_ENTERING_WORLD")
check(T.IsUp(4), "up by the object")
local st = T.Get(4)
check(st.source == nil and st.expires == nil and st.duration == nil, "no number is knowable")
check(T.Remaining(4, NOW) == nil and T.Fraction(4, NOW) == nil and T.Blocks(4, NOW) == nil, "no remaining, no block count")
check(T.DurationObject(4) ~= nil, "but the object is there to drive a timer")
-- partly secret answers are also unreadable
COMBAT = false
local real = GetTotemInfo
GetTotemInfo = function() return true, "Grounding Totem", SECRET, 45, 1, 1, 8177 end
fire("PLAYER_TOTEM_UPDATE", 4)
check(T.IsUp(4) and T.Get(4).source == nil, "one secret return makes the whole read unreadable")
GetTotemInfo = real
""")

case("a_combat_drop_is_stamped_from_the_cast_event")(r"""
local T = load()
local R = recorder(T)
COMBAT = true
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", 8071)      -- Stoneskin, 300 s measured
check(not T.IsUp(2), "not up until the object says so")
TOT[2] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_TOTEM_UPDATE", 2)
local st = T.Get(2)
check(st.up and st.source == "cast", "up, from the cast")
check(st.duration == 300 and st.name == "Stoneskin Totem" and st.spellID == 8071 and st.icon == 108071, "table values")
near(st.start, NOW); near(st.expires, NOW + 300)
check(T.Blocks(2, NOW) == 8)
check(T.Blocks(2, NOW + 150) == 4, "half left = 4, got " .. tostring(T.Blocks(2, NOW + 150)))
check(T.Blocks(2, NOW + 262.4) == 2, "37.6 s left of 300 is ceil(1.003) = 2, got " .. tostring(T.Blocks(2, NOW + 262.4)))
check(T.Blocks(2, NOW + 262.6) == 1, "under 37.5 s is the last block")
check(T.Blocks(2, NOW + 299) == 1)
check(T.Blocks(2, NOW + 400) == 1, "past the estimate the last block stays while the object says up")
""")

case("totem_first_then_cast_is_also_stamped")(r"""
local T = load()
COMBAT = true
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_TOTEM_UPDATE", 1)
check(T.IsUp(1) and T.Get(1).source == nil, "up with no number first")
local R = recorder(T)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
check(T.Get(1).source == "cast" and T.Get(1).duration == 30, "the cast gives the number")
check(R.n >= 1 and R.last == 1, "and tells the subscriber, though up did not change")
""")

case("a_higher_rank_is_found_through_the_spell_name_and_unknown_spells_are_ignored")(r"""
local T = load()
SPELL_NAMES[99001] = "Searing Totem"
SPELL_NAMES[99002] = "Frostbolt"
COMBAT = true
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 99001)
check(T.Get(1).source == "cast" and T.Get(1).duration == 30 and T.Get(1).spellID == 99001, "found by name")
local R = recorder(T)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 99002)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 12345)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", SECRET)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", nil)
check(R.n == 0, "non totem and unreadable casts change nothing")
fire("UNIT_SPELLCAST_SUCCEEDED", SECRET, "g", 8071)
check(not T.IsUp(2), "a secret unit is ignored")
""")

case("a_stamp_with_no_totem_behind_it_expires_after_the_grace")(r"""
local T = load()
COMBAT = true
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 8071)
NOW = NOW + 0.5
fire("PLAYER_TOTEM_UPDATE", 2)
TOT[2] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_TOTEM_UPDATE", 2)
check(T.Get(2).source == "cast", "a fresh stamp survives an earlier empty read (old totem destroyed first)")
TOT[2] = nil
NOW = NOW + 5
fire("PLAYER_TOTEM_UPDATE", 2)
check(not T.IsUp(2) and T.Get(2).expires == nil and T.Get(2).name == nil, "numbers are gone with the slot")
""")

case("a_cleared_slot_is_gone_and_tells_the_subscriber")(r"""
local T = load()
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("PLAYER_TOTEM_UPDATE", 1)
local R = recorder(T)
TOT[1] = nil
fire("PLAYER_TOTEM_UPDATE", 1)
check(not T.IsUp(1) and T.Get(1).source == nil and T.Get(1).start == nil, "gone, numbers cleared")
check(R.n == 1 and R.last == 1, "one change")
fire("PLAYER_TOTEM_UPDATE", 1)
check(R.n == 1, "no change, no call")
-- combat: the object going nil clears too
TOT[3] = { name = "Healing Stream Totem", start = NOW, dur = 300, spell = 5394 }
fire("PLAYER_TOTEM_UPDATE", 3)
COMBAT = true
TOT[3] = nil
fire("PLAYER_TOTEM_UPDATE", 3)
check(not T.IsUp(3), "in combat a nil object is gone")
""")

case("regen_enabled_replaces_estimates_with_plain_reads")(r"""
local T = load()
COMBAT = true
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)       -- stamped: 30 s assumed
TOT[1] = { name = "Searing Totem", start = NOW, dur = 40, spell = 3599 }   -- really rank 3
fire("PLAYER_TOTEM_UPDATE", 1)
check(T.Get(1).duration == 30)
COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(T.Get(1).source == "read" and T.Get(1).duration == 40, "the plain read wins")
""")

case("block_count_math")(r"""
local T = load()
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("PLAYER_TOTEM_UPDATE", 1)
local want = { [30] = 8, [29.9] = 8, [26.25] = 7, [26.3] = 8, [15] = 4, [3.75] = 1, [3.8] = 2, [0.5] = 1, [0] = 1 }
for rem, blocks in pairs(want) do
    local got = T.Blocks(1, NOW + 30 - rem)
    check(got == blocks, rem .. " s left should light " .. blocks .. ", got " .. tostring(got))
end
check(T.Blocks(1, NOW - 100) == 8, "more than the duration clamps at 8")
""")

case("tick_asks_again_after_the_expected_end_and_is_throttled")(r"""
local T = load()
COMBAT = true
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
TOT[1] = { name = "x", start = 0, dur = 0, spell = 0 }
fire("PLAYER_TOTEM_UPDATE", 1)
local before = INFO_CALLS + OBJ_CALLS
NOW = NOW + 10
T.Tick(NOW)
check(INFO_CALLS + OBJ_CALLS == before, "nothing is asked while the estimate has time left")
NOW = NOW + 30                             -- past the expected end, the object still answers
T.Tick(NOW)
local asked = OBJ_CALLS
check(T.IsUp(1) and T.Blocks(1, NOW) == 1, "still up, last block")
T.Tick(NOW + 0.1)
check(OBJ_CALLS == asked, "throttled")
TOT[1] = nil                               -- the totem really went with no event
NOW = NOW + 1
T.Tick(NOW)
check(not T.IsUp(1), "the re-ask finds it gone")
""")

case("subscribe_and_unsubscribe")(r"""
local T = load()
local calls = 0
local fn = function() calls = calls + 1 end
T.Subscribe(fn); T.Subscribe(fn)
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("PLAYER_TOTEM_UPDATE", 1)
check(calls == 1, "a function subscribes once, got " .. calls)
T.Unsubscribe(fn)
TOT[1] = nil
fire("PLAYER_TOTEM_UPDATE", 1)
check(calls == 1, "unsubscribed")
T.Subscribe(function() error("boom") end)
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("PLAYER_TOTEM_UPDATE", 1)
check(T.IsUp(1), "a throwing subscriber breaks nothing")
""")

case("a_bad_slot_in_the_update_event_refreshes_everything")(r"""
local T = load()
TOT[4] = { name = "Grounding Totem", start = NOW, dur = 45, spell = 8177 }
fire("PLAYER_TOTEM_UPDATE", SECRET)
check(T.IsUp(4), "a secret slot argument re-reads all slots")
TOT[4] = nil
fire("PLAYER_TOTEM_UPDATE", nil)
check(not T.IsUp(4), "and so does a missing one")
""")

case("unlocked_follows_known_totems_then_the_level")(r"""
LEVEL = 14
local T = load()
check(T.IsUnlocked(2) and T.IsUnlocked(1), "earth (4) and fire (10) are open at 14")
check(not T.IsUnlocked(3) and not T.IsUnlocked(4), "water (20) and air (30) are locked at 14")
local R = recorder(T)
KNOWN_SPELLS[5394] = true
fire("SPELLS_CHANGED")
check(T.IsUnlocked(3) and R.last == 3, "a known water totem opens it")
LEVEL = 30
fire("PLAYER_LEVEL_UP")
check(T.IsUnlocked(4), "the level opens air")
-- a standing totem is never locked, and an unreadable level never locks
LEVEL = SECRET
local T2 = (function() for k in pairs(FRAMES) do FRAMES[k] = nil end; FS.ShamanTotems = nil; KNOWN_SPELLS = {}; return load() end)()
check(T2.IsUnlocked(1) and T2.IsUnlocked(4), "a secret level locks nothing")
""")

# ---------------------------------------------------------------- FAR

FAR_SETUP = r"""
local T = load()
POS = { 100, 200, 0, 1 }
COMBAT = true
local function drop(id, slot)
    TOT[slot] = { name = "x", start = 0, dur = 0, spell = 0 }
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", id)
end
local function step()
    NOW = NOW + 0.3
    T.Tick(NOW)
end
"""

case("far_is_set_past_the_range_from_two_plain_positions")(FAR_SETUP + r"""
drop(3599, 1)                              -- Searing, 20 yd
check(not T.IsFar(1), "not far at the drop")
POS = { 100, 215, 0, 1 }; step()
check(not T.IsFar(1), "15 yd is in range")
POS = { 100, 225, 0, 1 }; step()
check(T.IsFar(1) and T.Get(1).far, "25 yd is far")
local R = recorder(T)
POS = { 100, 219.5, 0, 1 }; step()
check(T.IsFar(1), "19.5 yd is inside the hysteresis band: still far")
POS = { 100, 218, 0, 1 }; step()
check(not T.IsFar(1) and R.n == 1, "18 yd clears it and tells the subscriber")
-- a sideways distance counts too (y axis)
POS = { 120, 200 + 15, 0, 1 }; step()
check(T.IsFar(1), "sqrt(20^2+15^2) = 25 is far")
""")

case("far_uses_the_totems_own_range")(FAR_SETUP + r"""
drop(8190, 1)                              -- Magma 8 yd
POS = { 100, 210, 0, 1 }; step()
check(T.IsFar(1), "10 yd is past Magma's 8")
drop(8071, 2)                              -- Stoneskin: the 20 yd default
POS = { 100, 215, 0, 1 }; step()
check(not T.IsFar(2), "15 yd is inside the default 20")
""")

case("far_needs_plain_positions_and_the_same_instance")(FAR_SETUP + r"""
drop(3599, 1)
POS = { 100, 260, 0, 1 }; step()
check(T.IsFar(1), "far with plain positions")
POS = nil; step()
check(not T.IsFar(1), "a nil position (instances) clears it")
POS = { SECRET, SECRET, SECRET, SECRET }; step()
check(not T.IsFar(1), "a secret position is never far and raises nothing")
POS = { 100, 260, 0, 1 }; step()
check(T.IsFar(1), "plain again, far again")
POS = { 100, 260, 0, 2 }; step()
check(not T.IsFar(1), "another instance id is never far")
POS = { 100, 260, 0, nil }; step()
check(not T.IsFar(1), "no instance id is never far")
""")

case("far_never_sets_without_a_stamp_from_a_plain_position")(FAR_SETUP + r"""
POS = nil
drop(3599, 1)
POS = { 100, 500, 0, 1 }; step()
check(not T.IsFar(1), "a drop stamped with no position can never be far")
POS = { SECRET, 5, 0, 1 }
drop(8071, 2)
POS = { 100, 500, 0, 1 }; step()
check(not T.IsFar(2), "a drop stamped with a secret position can never be far")
-- a totem read out of combat with no cast seen has no stamp
COMBAT = false
TOT[4] = { name = "Grounding Totem", start = NOW, dur = 45, spell = 8177 }
fire("PLAYER_TOTEM_UPDATE", 4)
POS = { 100, 500, 0, 1 }; step()
check(not T.IsFar(4), "no stamp, no FAR")
""")

case("totemic_projection_and_a_cleared_slot_drop_the_stamps")(FAR_SETUP + r"""
SPELL_NAMES[77001] = "Totemic Projection"
drop(3599, 1); drop(8071, 2)
POS = { 100, 300, 0, 1 }; step()
check(T.IsFar(1) and T.IsFar(2), "both far")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 77001)
check(not T.IsFar(1) and not T.IsFar(2), "Projection clears FAR")
step(); step()
check(not T.IsFar(1) and not T.IsFar(2), "and it stays off until the next drop")
drop(3599, 1)
POS = { 100, 400, 0, 1 }; step()
check(T.IsFar(1), "a new drop stamps again")
TOT[1] = nil
NOW = NOW + 5
fire("PLAYER_TOTEM_UPDATE", 1)
check(not T.IsFar(1) and T.Get(1).posY == nil, "a cleared slot loses its stamp")
""")

case("a_set_drop_stamps_every_slot_with_the_default_range")(FAR_SETUP + r"""
for s = 1, 4 do TOT[s] = { name = "x", start = 0, dur = 0, spell = 0 } end
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 66842)
for s = 1, 4 do check(T.IsUp(s) and T.Get(s).source == nil, "slot " .. s .. " up, no number (which totems is unknown)") end
POS = { 100, 230, 0, 1 }; step()
for s = 1, 4 do check(T.IsFar(s), "slot " .. s .. " far past the default 20") end
""")

case("no_secret_is_ever_touched")(r"""
local T = load()
-- every client answer secret, in and out of combat
GetTotemInfo = function() return SECRET, SECRET, SECRET, SECRET, SECRET, SECRET, SECRET end
GetTotemDuration = function() return SECRET end
UnitPosition = function() return SECRET, SECRET, SECRET, SECRET end
UnitLevel = function() return SECRET end
IsPlayerSpell = function() return SECRET end
C_Spell.GetSpellName = function() return SECRET end
for _, e in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED" }) do fire(e) end
fire("PLAYER_TOTEM_UPDATE", 1)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 3599)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g", 4242)
T.Tick(NOW + 100)
for s = 1, 4 do check(not T.IsUp(s), "unreadable is not up") end
check(next(DEGRADED) == nil, "nothing was logged as a failure: " .. tostring(next(DEGRADED)))
""")

case("get_totem_functions_missing_or_throwing_change_nothing")(r"""
local T = load()
TOT[1] = { name = "Searing Totem", start = NOW, dur = 30, spell = 3599 }
fire("PLAYER_TOTEM_UPDATE", 1)
GetTotemInfo = function() error("boom") end
GetTotemDuration = function() error("boom") end
fire("PLAYER_TOTEM_UPDATE", 1)
check(T.IsUp(1), "nothing can say: the record is left as it was")
GetTotemInfo, GetTotemDuration = nil, nil
fire("PLAYER_REGEN_ENABLED")
check(T.IsUp(1), "missing APIs too")
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        t, s = toc.index("Modules/CombatHud/ShamanTotems.lua"), toc.index("Modules/CombatHud/GunsightShaman.lua")
        out.append(("toc_loads_totem_data_before_the_shaman_module",
                    None if t < s else f"ShamanTotems.lua must load before GunsightShaman.lua (positions {t}, {s})"))
        ts = toc.index("Core/Theme.lua")
        out.append(("toc_loads_totem_data_after_theme", None if t > ts else "ShamanTotems.lua reads FS.IsSecret: after Theme.lua"))
    except ValueError as e:
        out.append(("toc_loads_totem_data_before_the_shaman_module", f"{e}"))
    src = TOTEMS.read_text(encoding="utf-8") if TOTEMS.exists() else ""
    out.append(("no_em_or_en_dashes", None if not re.search("[–—]", src) else "ShamanTotems.lua has an em or en dash"))
    out.append(("never_asks_which_slot_should_be_secret",
                None if "ShouldTotemSlotBeSecret" not in re.sub(r"--.*", "", src) else "C_Secrets.ShouldTotemSlotBeSecret is unreliable"))
    bar = TOTEMBAR.read_text(encoding="utf-8")
    bar_ids = {int(m) for m in re.findall(r"\{\s*(\d{4,5}),\s*\"[A-Za-z ]+Totem\"", bar)}
    mine = {int(m) for m in re.findall(r"id = (\d{4,5}), name = \"[A-Za-z ]+Totem\"", src)}
    out.append(("totem_ids_match_the_totem_bar",
                None if bar_ids and bar_ids == mine else f"TotemBar ids {sorted(bar_ids)} vs ShamanTotems ids {sorted(mine)}"))
    slots = {int(a): int(b) for a, b in re.findall(r"slot = (\d), id = (\d+)", src)}
    out.append(("every_element_has_a_totem", None if set(slots) == {1, 2, 3, 4} else f"slots seen {sorted(slots)}"))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().TOTEMS_SRC = TOTEMS.read_text(encoding="utf-8")
    try:
        lua.execute(body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    if not TOTEMS.exists():
        print(f"FAIL  {TOTEMS.name} is missing")
        return 1
    for name, body in CASES:
        try:
            err = run_case(name, body)
        except LuaError as e:
            err = f"harness error: {e}"
        report(name, err)
    statics = static_checks()
    for name, err in statics:
        report(name, err)
    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
