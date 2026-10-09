#!/usr/bin/env python3
"""Runs the real TargetDebuffs.lua (FS.TargetDebuffs, the data service behind the Gunsight "Target debuffs"
modules) headless against a mock WoW API.

The service answers one question for every class: which debuffs did the player apply to the target, with how
long left and how many stacks. The checks pin:

  * source 1, the aura snapshot: while FS.AurasReadable() is true, HARMFUL auras on "target" are read through
    FrameHelpers.ReadAuraSlot and only sourceUnit == "player" ones kept, as plain values; it runs on UNIT_AURA
    for the target (coalesced), PLAYER_TARGET_CHANGED and at regen, and never in combat;
  * source 2, the combat ledger: UNIT_SPELLCAST_SUCCEEDED for the player, bound to the target captured at
    UNIT_SPELLCAST_SENT, with durations and the stack cap learned from earlier snapshots (session only) or
    from HudSpells; an unknown duration reads as an entry with no expiry; a recast stacks up to the cap;
  * retarget clears the list, dead and friendly targets show nothing, the Paladin's Judgement debuffs are
    left out while the Class Module area is in use, Priest and Warlock rows come from the Hud's DoT ledger
    in profile order with absent rows kept;
  * nothing secret is ever compared, counted or concatenated, and nothing is built before the first
    Subscribe.

FrameHelpers.ReadAuraSlot is a STUB here (its signature is pinned against FrameHelpers.lua by a static
check); the real HudSpells.lua, HudProfiles.lua and the shared target rule out of Theme.lua are loaded.

    python3 tools/targetdebuffs-harness.py

Exit 0 = every check passed. TARGETDEBUFFS_LUA=<path> runs another file in place of TargetDebuffs.lua.
"""

from __future__ import annotations

import importlib.util
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
SERVICE = Path(os.environ.get("TARGETDEBUFFS_LUA") or ADDON / "Modules/CombatHud/TargetDebuffs.lua")
SPELLS = ADDON / "Modules/CombatHud/HudSpells.lua"
PROFILES = ADDON / "Modules/CombatHud/HudProfiles.lua"
FRAME_HELPERS = ADDON / "Core/FrameHelpers.lua"
TOC = ADDON / "forever-stuwave.toc"


def _load_gunsight_harness():
    spec = importlib.util.spec_from_file_location("gunsight_harness", HERE / "gunsight-harness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOCK = r"""
FRAMES = {}
DEGRADED = {}
AURA_TOUCHED = {}
READS = 0
TIMERS = {}
ONREAD = {}
NOW = 5000
IN_COMBAT = false
AURAS = {}            -- the target's harmful auras, in slot order, as ReadAuraSlot shapes
TARGET = { exists = true, guid = "Creature-A", name = "Mob", dead = false, canAttack = true }
SPELLS_BY_ID = {}
AREA = {}
AREACB = {}

function check(c, msg) if not c then error(msg or "check failed", 2) end end
function near(a, b, msg, eps)
    check(type(a) == "number" and type(b) == "number" and math.abs(a - b) < (eps or 1e-6),
        (msg or "near") .. ": got " .. tostring(a) .. ", want " .. tostring(b))
end
function GetTime() return NOW end
function InCombatLockdown() return IN_COMBAT end

-- A secret value: a table that errors on anything but being passed along (compare, math, concat, length, index).
local function boom() error("secret value touched", 2) end
SECRET = setmetatable({}, { __lt = boom, __le = boom, __add = boom, __sub = boom, __mul = boom, __div = boom,
    __concat = boom, __len = boom, __unm = boom, __index = boom, __call = boom })
function IsSecretMock(v) return rawequal(v, SECRET) end

-- No aura API may be read directly: only FrameHelpers.ReadAuraSlot, and only when readable.
for _, name in ipairs({ "UnitAura", "UnitBuff", "UnitDebuff", "GetAuraDataByIndex", "GetPlayerAuraBySpellID" }) do
    _G[name] = function() AURA_TOUCHED[#AURA_TOUCHED + 1] = name; error("aura API read: " .. name) end
end
C_UnitAuras = setmetatable({}, { __index = function(_, k)
    return function() AURA_TOUCHED[#AURA_TOUCHED + 1] = "C_UnitAuras." .. k; error("aura API read: C_UnitAuras." .. k) end
end })

local Frame = {}
Frame.__index = Frame
function Frame:RegisterEvent(e) self.events[e] = true end
function Frame:RegisterUnitEvent(e, ...) self.events[e] = true; self.unitOnly = self.unitOnly or {}; self.unitOnly[e] = { ... } end
function Frame:UnregisterEvent(e) self.events[e] = nil; if self.unitOnly then self.unitOnly[e] = nil end end
function Frame:UnregisterAllEvents() self.events = {}; self.unitOnly = nil end
function Frame:SetScript(n, fn) self.scripts[n] = fn end
function CreateFrame(kind, name, parent)
    local f = setmetatable({ kind = kind, name = name, events = {}, scripts = {} }, Frame)
    FRAMES[#FRAMES + 1] = f
    return f
end
function fire(event, ...)
    local args, n, list = { ... }, select("#", ...), {}
    for _, f in ipairs(FRAMES) do
        local only = f.unitOnly and f.unitOnly[event]
        local wanted = true
        if only then
            wanted = false
            for _, u in ipairs(only) do if u == args[1] then wanted = true end end
        end
        if wanted and f.events[event] and f.scripts.OnEvent then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f.scripts.OnEvent(f, event, unpack(args, 1, n)) end
end
function registeredEvents()
    local out = {}
    for _, f in ipairs(FRAMES) do for e in pairs(f.events) do out[e] = true end end
    return out
end

C_Timer = { After = function(delay, fn) TIMERS[#TIMERS + 1] = { delay = delay, fn = fn } end }
function flushTimers()
    local list = TIMERS
    TIMERS = {}
    for _, t in ipairs(list) do t.fn() end
end

function UnitExists(unit) if unit == "target" then return TARGET.exists end return false end
function UnitName(unit) if unit == "target" then return TARGET.name end return "Player" end
function UnitGUID(unit) if unit == "target" then return TARGET.guid end return "Player-1" end
function UnitIsDeadOrGhost(unit) return TARGET.dead end
function UnitCanAttack() return TARGET.canAttack end
C_Spell = { GetSpellInfo = function(id)
    local s = SPELLS_BY_ID[id]
    if not s then return nil end
    return { name = s.name, spellID = id, iconID = s.icon }
end }

-- ReadAuraSlot stub, same contract as FrameHelpers.ReadAuraSlot: nil when auras are not readable or the slot is empty.
FHSTUB = {}
function FHSTUB.ReadAuraSlot(unit, index, filter, report)
    READS = READS + 1
    check(unit == "target" and filter == "HARMFUL", "scan must be (target, HARMFUL), got " .. tostring(unit) .. " " .. tostring(filter))
    if not FS.AurasReadable() then return nil end
    local a = AURAS[index]
    if a == nil then return nil end
    if a.throws then error("boom") end
    return a
end

function resetWorld()
    for i = #FRAMES, 1, -1 do FRAMES[i] = nil end
    for i = #TIMERS, 1, -1 do TIMERS[i] = nil end
    for i = #ONREAD, 1, -1 do ONREAD[i] = nil end
    for i = #AURA_TOUCHED, 1, -1 do AURA_TOUCHED[i] = nil end
    for k in pairs(DEGRADED) do DEGRADED[k] = nil end
    for k in pairs(AREA) do AREA[k] = nil end
    for i = #AREACB, 1, -1 do AREACB[i] = nil end
    AURAS = {}
    READS, NOW, IN_COMBAT = 0, 5000, false
    TARGET = { exists = true, guid = "Creature-A", name = "Mob", dead = false, canAttack = true }
    SPELLS_BY_ID = {}
    FS = {}
    FS.LogDegradeOnce = function(key, msg) DEGRADED[key] = msg end
end

function loadAddonFile(src, name)
    local fn, err = loadstring(src, "@" .. name)
    if not fn then error(err) end
    return fn("forever-stuwave", FS)
end
"""

PRELUDE = r"""
local function boot(opts)
    opts = opts or {}
    resetWorld()
    ForeverSTUwaveDB = opts.db
    FS.IsSecret = IsSecretMock
    FS.AurasReadable = function() return not IN_COMBAT end
    FS.OnAurasReadable = function(fn) ONREAD[#ONREAD + 1] = fn end
    assert(loadstring(HAS_TARGET_SRC, "@Theme.lua"))()
    FS.FrameHelpers = FHSTUB
    UnitClass = function() return "Class", opts.class or "WARRIOR" end
    loadAddonFile(SPELLS_SRC, "Modules/CombatHud/HudSpells.lua")
    loadAddonFile(PROFILES_SRC, "Modules/CombatHud/HudProfiles.lua")
    SPELLS_BY_ID = {
        [11572] = { name = "Rend", icon = 1001 }, [772] = { name = "Rend", icon = 1001 }, [6548] = { name = "Rend", icon = 1001 },
        [9998] = { name = "Fireball", icon = 1009 }, [9997] = { name = "Fireball", icon = 1009 }, [11597] = { name = "Sunder Armor", icon = 1002 }, [11598] = { name = "Sunder Armor", icon = 1002 },
        [6343] = { name = "Thunder Clap", icon = 1003 }, [7777] = { name = "Thunder Clap", icon = 1003 }, [8647] = { name = "Expose Armor", icon = 1004 },
        [172] = { name = "Corruption", icon = 1005 }, [9999] = { name = "Heroic Strike", icon = 1006 },
        [20271] = { name = "Judgement", icon = 1007 }, [853] = { name = "Hammer of Justice", icon = 1008 },
    }
    FS.GunsightAreas = { AreaOf = function(id) return AREA[id] end,
        OnAreaChanged = function(fn) AREACB[#AREACB + 1] = fn end }
    if opts.hud then
        FS.Hud = {
            GetProfile = function() return FS.HudProfiles[opts.class or "WARRIOR"] end,
            Subscribe = function(fn) HUDSUBS = HUDSUBS or {}; HUDSUBS[#HUDSUBS + 1] = fn; if HUDSTATE then fn(HUDSTATE) end end,
            Unsubscribe = function(fn)
                for i = #HUDSUBS, 1, -1 do if HUDSUBS[i] == fn then table.remove(HUDSUBS, i) end end
            end,
        }
    end
    HUDSUBS, HUDSTATE = {}, nil
    loadAddonFile(SERVICE_SRC, "Modules/CombatHud/TargetDebuffs.lua")
    return FS.TargetDebuffs
end

-- An aura as ReadAuraSlot hands it out.
local function aura(name, exp, dur, count, caster, id, icon)
    return { name = name, icon = icon or 4000, count = count or 0, duration = dur or 0, expirationTime = exp or 0,
        caster = caster or "player", spellId = id or 1, dispelType = nil }
end
local function names(list) local o = {} for i, e in ipairs(list) do o[i] = e.name end return table.concat(o, ",") end
local function byName(list, n) for _, e in ipairs(list) do if e.name == n then return e end end end
local function sync(TD)               -- one coalesced scan: the aura event then the timer it queued
    fire("UNIT_AURA", "target"); flushTimers()
    return TD.Get()
end
local function retarget(guid)
    TARGET.guid = guid
    fire("PLAYER_TARGET_CHANGED")
    flushTimers()
end
local function cast(id, castGUID)
    fire("UNIT_SPELLCAST_SENT", "player", "Mob", castGUID, id)
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", castGUID, id)
end
local n = 0
local function guid() n = n + 1 return "Cast-" .. n end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("api_exists_and_nothing_is_built_before_the_first_subscribe")(r"""
local TD = boot()
check(type(TD) == "table", "FS.TargetDebuffs is missing")
check(type(TD.Subscribe) == "function" and type(TD.Unsubscribe) == "function" and type(TD.Get) == "function",
    "Subscribe, Unsubscribe and Get are the API")
check(#FRAMES == 0, "no frame before a subscriber, got " .. #FRAMES)
check(next(registeredEvents()) == nil, "no event before a subscriber")
check(#TD.Get() == 0, "Get() is an empty list before any scan")
""")

case("subscribe_pushes_at_once_and_unsubscribe_releases_the_events")(r"""
local TD = boot()
AURAS = { aura("Rend", NOW + 12, 21, 0, "player", 11572) }
local calls = {}
local fn = function(list, epoch) calls[#calls + 1] = { n = #list, epoch = epoch } end
TD.Subscribe(fn)
check(#calls == 1, "Subscribe runs the callback at once, got " .. #calls)
check(calls[1].n == 1, "the first push already carries the readable snapshot, got " .. calls[1].n)
check(type(calls[1].epoch) == "number", "the second argument is the target epoch")
local ev = registeredEvents()
for _, e in ipairs({ "PLAYER_TARGET_CHANGED", "UNIT_AURA", "UNIT_SPELLCAST_SENT", "UNIT_SPELLCAST_SUCCEEDED",
    "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD" }) do check(ev[e], "event " .. e .. " is registered while subscribed") end
local before = #calls
AURAS = {}
sync(TD)
check(#calls == before + 1, "a changed snapshot notifies")
TD.Unsubscribe(fn)
check(next(registeredEvents()) == nil, "the last Unsubscribe releases every event, left: " .. tostring(next(registeredEvents())))
sync(TD)
check(#calls == before + 1, "an unsubscribed callback is never called again")
""")

case("snapshot_keeps_only_player_sourced_debuffs_with_plain_fields")(r"""
local TD = boot()
AURAS = {
    aura("Rend", NOW + 12, 21, 0, "player", 11572, 4001),
    aura("Curse of Thorns", NOW + 30, 60, 0, "party1", 7, 4002),
    aura("Sunder Armor", NOW + 25, 30, 3, "player", 11597, 4003),
    aura("Pet Bite", NOW + 5, 10, 0, "pet", 8, 4004),
}
TD.Subscribe(function() end)
local list = TD.Get()
check(#list == 2, "two player-sourced debuffs, got " .. #list .. ": " .. names(list))
local r, s = byName(list, "Rend"), byName(list, "Sunder Armor")
check(r and s, "Rend and Sunder Armor are kept: " .. names(list))
check(not byName(list, "Curse of Thorns") and not byName(list, "Pet Bite"), "other casters are dropped")
near(r.expires, NOW + 12, "expires"); near(r.duration, 21, "duration"); near(r.id, 11572, "id")
check(r.icon == 4001, "icon"); check(r.count == 1, "a 0 application count reads as one stack, got " .. tostring(r.count))
check(s.count == 3, "stacks come from the scan, got " .. tostring(s.count))
check(type(r.order) == "number" and type(s.order) == "number", "every entry carries an order")
check(READS > 0 and #AURA_TOUCHED == 0, "the scan goes through ReadAuraSlot only")
""")

case("the_scan_runs_on_target_aura_events_coalesced_and_on_retarget")(r"""
local TD = boot()
TD.Subscribe(function() end)
local base = READS
fire("UNIT_AURA", "party1"); flushTimers()
check(READS == base, "UNIT_AURA for another unit does not scan")
AURAS = { aura("Rend", NOW + 12, 21, 0, "player", 11572) }
fire("UNIT_AURA", "target"); fire("UNIT_AURA", "target"); fire("UNIT_AURA", "target")
check(#TD.Get() == 0, "the scan waits for the coalescing timer")
check(#TIMERS == 1, "three events queue one timer, got " .. #TIMERS)
flushTimers()
check(#TD.Get() == 1, "the timer runs the scan")
AURAS = { aura("Sunder Armor", NOW + 25, 30, 1, "player", 11597) }
retarget("Creature-B")
check(names(TD.Get()) == "Sunder Armor", "a retarget scans at once, got " .. names(TD.Get()))
""")

case("nothing_is_read_in_combat_and_the_snapshot_is_kept")(r"""
local TD = boot()
AURAS = { aura("Rend", NOW + 12, 21, 0, "player", 11572) }
TD.Subscribe(function() end)
fire("PLAYER_REGEN_DISABLED")
IN_COMBAT = true
local base = READS
AURAS = {}
fire("UNIT_AURA", "target"); flushTimers()
check(READS == base, "no aura slot is read in combat, got " .. (READS - base) .. " reads")
check(names(TD.Get()) == "Rend", "the frozen snapshot is kept in combat")
check(#AURA_TOUCHED == 0, "no aura API touched")
""")

case("combat_ledger_uses_a_duration_learned_from_an_earlier_snapshot")(r"""
local TD = boot()
AURAS = { aura("Rend", NOW + 21, 21, 0, "player", 11572) }
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
check(#TD.Get() == 0, "setup: the debuff fell off")
IN_COMBAT = true; fire("PLAYER_REGEN_DISABLED")
NOW = NOW + 3
cast(11572, guid())
local list = TD.Get()
check(#list == 1 and list[1].name == "Rend", "the cast is in the ledger: " .. names(list))
near(list[1].duration, 21, "the learned duration"); near(list[1].expires, NOW + 21, "expires = cast time + learned duration")
check(list[1].icon == 1001, "the icon comes from the spell")
NOW = NOW + 10
near(list[1].expires - GetTime(), 11, "remaining is expires - GetTime()")
check(next(ForeverSTUwaveDB or {}) == nil, "the learned durations stay in the session, nothing was saved")
""")

case("an_unknown_duration_is_an_entry_with_no_expiry")(r"""
local TD = boot({ class = "ROGUE" })
TD.Subscribe(function() end)
IN_COMBAT = true
cast(8647, guid())                    -- Expose Armor: a Rogue debuff with no table duration, nobody has scanned it yet
local e = byName(TD.Get(), "Expose Armor")
check(e, "a class debuff name is tracked from its first cast")
check(e.expires == nil and e.duration == nil, "no duration is known: expires and duration are nil")
check(e.count == 1, "one stack")
cast(9999, guid())                    -- Heroic Strike is not a debuff
check(#TD.Get() == 1, "a spell that is not a known debuff is ignored, got " .. names(TD.Get()))
""")

case("a_warrior_debuff_is_timed_from_its_first_cast_by_rank")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
NOW = NOW + 1
cast(772, guid())                       -- Rend rank 1: 9 s on Forever, nothing scanned yet
local e = byName(TD.Get(), "Rend")
check(e and e.duration == 9 and e.expires, "rank 1 Rend is timed at 9 s, got " .. tostring(e and e.duration))
near(e.expires, NOW + 9, "expires = cast + 9")
cast(6548, guid())                      -- rank 4: 18 s
near(byName(TD.Get(), "Rend").duration, 18, "rank 4 Rend is 18 s")
cast(11572, guid())                     -- rank 5: 21 s
near(byName(TD.Get(), "Rend").duration, 21, "rank 5 Rend is 21 s")
cast(6343, guid())
near(byName(TD.Get(), "Thunder Clap").duration, 10, "Thunder Clap rank 1 is 10 s")
cast(11597, guid())
near(byName(TD.Get(), "Sunder Armor").duration, 30, "Sunder Armor is 30 s")
""")

case("a_learned_duration_is_kept_per_spell_id_and_beats_another_ranks_table")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Rend", NOW + 7, 9, 0, "player", 772) }
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
IN_COMBAT = true
cast(6548, guid())
near(byName(TD.Get(), "Rend").duration, 18, "rank 4 is not timed by the rank 1 snapshot")
cast(772, guid())
near(byName(TD.Get(), "Rend").duration, 9, "rank 1 keeps what was scanned for rank 1")
""")

case("an_unlisted_rank_id_never_takes_a_lower_ranks_learned_duration")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Thunder Clap", NOW + 8, 10, 0, "player", 6343) }      -- a rank 1 Thunder Clap: 10 s
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
IN_COMBAT = true
cast(7777, guid())                      -- a rank id the table does not list: at least the top rank, not 10 s
local e = byName(TD.Get(), "Thunder Clap")
check(e and e.duration == 30, "an unlisted Thunder Clap id is timed at the top rank, got " .. tostring(e and e.duration))
near(e.expires, NOW + 30, "expires = cast + 30")
cast(6343, guid())
near(byName(TD.Get(), "Thunder Clap").duration, 10, "the listed rank 1 id keeps what was scanned for it")
""")

case("a_scanned_aura_without_a_duration_keeps_the_ledger_timing_or_the_table")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
-- a table-known spell scanned with no duration or expiry is timed from the table, not shown as "?"
AURAS = { aura("Sunder Armor", 0, 0, 1, "player", 11597) }
sync(TD)
local e = byName(TD.Get(), "Sunder Armor")
check(e and e.duration == 30 and e.expires, "table duration when the scan has none, got " .. tostring(e and e.duration))
near(e.expires, NOW + 30, "expires = scan time + table duration")
-- a cast timed in combat keeps its expiry when the next snapshot has no duration
AURAS = {}; sync(TD)
IN_COMBAT = true; fire("PLAYER_REGEN_DISABLED")
cast(11597, guid())
local castExpires = byName(TD.Get(), "Sunder Armor").expires
near(castExpires, NOW + 30, "setup: cast timed by the table")
NOW = NOW + 5
IN_COMBAT = false
AURAS = { aura("Sunder Armor", 0, 0, 1, "player", 11597) }
fire("PLAYER_REGEN_ENABLED")
local after = byName(TD.Get(), "Sunder Armor")
check(after and after.expires, "the entry stays timed")
near(after.expires, castExpires, "the ledger expiry survives a zero-duration snapshot")
-- a spell nobody can time stays untimed
AURAS = { aura("Mystery", 0, 0, 1, "player", 4242) }
sync(TD)
local m = byName(TD.Get(), "Mystery")
check(m and m.expires == nil and m.duration == nil, "an unknown spell without a duration stays untimed")
""")

case("a_learned_duration_above_the_top_rank_wins_for_an_unlisted_rank_id")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Thunder Clap", NOW + 30, 40, 0, "player", 6343) }     -- a talent lengthens it past the top rank's 30 s
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
IN_COMBAT = true
cast(7777, guid())
local e = byName(TD.Get(), "Thunder Clap")
check(e and e.duration == 40, "the learned 40 s beats the top rank, got " .. tostring(e and e.duration))
""")

case("a_learned_duration_is_used_for_a_spell_with_no_rank_table")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Sunder Armor", NOW + 15, 20, 0, "player", 11597) }    -- 20 s learned, table says 30 s and has no ranks
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
IN_COMBAT = true
cast(11598, guid())                     -- another id of the same name: the name's measurement serves
local e = byName(TD.Get(), "Sunder Armor")
check(e and e.duration == 20, "the learned 20 s is used, got " .. tostring(e and e.duration))
""")

case("an_expired_ledger_entry_with_the_aura_still_up_stays_untimed")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true; fire("PLAYER_REGEN_DISABLED")
cast(11597, guid())                     -- timed by the table: expires NOW + 30
NOW = NOW + 40                          -- the ledger expiry is past, then an untracked refresh keeps the aura up
IN_COMBAT = false
AURAS = { aura("Sunder Armor", 0, 0, 1, "player", 11597) }
fire("PLAYER_REGEN_ENABLED")
local e = byName(TD.Get(), "Sunder Armor")
check(e and e.expires == nil and e.duration == nil, "no fresh full-length timer from an expired entry, got " .. tostring(e and e.expires))
""")

case("any_class_spell_seen_once_out_of_combat_is_timed_later_in_combat")(r"""
local TD = boot({ class = "MAGE" })
AURAS = { aura("Fireball", NOW + 6, 8, 0, "player", 9998) }
TD.Subscribe(function() end)
check(byName(TD.Get(), "Fireball"), "setup: the snapshot lists it")
AURAS = {}; sync(TD)
IN_COMBAT = true
NOW = NOW + 2
cast(9997, guid())                      -- another rank id of the same name: the name's duration serves
local e = byName(TD.Get(), "Fireball")
check(e and e.duration == 8 and e.expires, "timed from the learned name duration")
near(e.expires, NOW + 8, "expires")
""")

case("a_secret_duration_in_the_scan_is_ignored_and_never_compared")(r"""
local TD = boot({ class = "MAGE" })
AURAS = { aura("Fireball", SECRET, SECRET, 0, "player", 9998) }
TD.Subscribe(function() end)
local e = byName(TD.Get(), "Fireball")
check(e and e.expires == nil and e.duration == nil, "a secret duration leaves the entry untimed, no error")
""")

case("a_duration_from_hudspells_is_used_when_nothing_was_learned")(r"""
local TD = boot({ class = "WARLOCK" })
TD.Subscribe(function() end)
IN_COMBAT = true
NOW = NOW + 1
cast(172, guid())                      -- Corruption: HudSpells.corruption.apply = 18 (rank 172 is the 12 s rank)
local e = byName(TD.Get(), "Corruption")
check(e and e.duration ~= nil and e.duration > 0, "HudSpells supplies a duration")
near(e.expires, NOW + e.duration, "expires follows it")
""")

case("stacks_come_from_the_scan_and_grow_on_a_recast_up_to_the_scanned_max")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Sunder Armor", NOW + 30, 30, 5, "player", 11597) }
TD.Subscribe(function() end)
check(byName(TD.Get(), "Sunder Armor").count == 5, "scanned stacks")
AURAS = {}; sync(TD)
IN_COMBAT = true
local seen = {}
for i = 1, 7 do cast(11597, guid()); seen[#seen + 1] = byName(TD.Get(), "Sunder Armor").count end
check(table.concat(seen, ",") == "1,2,3,4,5,5,5", "stacks climb to the last scanned max, got " .. table.concat(seen, ","))
-- no scanned max: a recast refreshes, it never invents stacks
cast(11572, guid()); cast(11572, guid())
local r = byName(TD.Get(), "Rend")
check(r and r.count == 1, "no known max keeps one stack, got " .. tostring(r and r.count))
""")

case("a_retarget_clears_the_list_and_a_ledger_comes_back_with_its_target")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
cast(11597, guid())
check(#TD.Get() == 1, "setup: one entry on target A")
local e1 = TD.Epoch and TD.Epoch()
retarget("Creature-B")
check(#TD.Get() == 0, "a new target starts empty, got " .. names(TD.Get()))
cast(6343, guid())
check(names(TD.Get()) == "Thunder Clap", "B carries only its own debuff")
retarget("Creature-A")
check(names(TD.Get()) == "Sunder Armor", "back on A its ledger is shown again, got " .. names(TD.Get()))
TARGET.exists = false; TARGET.guid = nil
fire("PLAYER_TARGET_CHANGED")
check(#TD.Get() == 0, "no target: nothing")
""")

case("a_cast_lands_on_the_target_it_was_sent_to")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
local g = guid()
fire("UNIT_SPELLCAST_SENT", "player", "Mob", g, 11572)   -- sent at A
retarget("Creature-B")                                    -- tab before it lands
fire("UNIT_SPELLCAST_SUCCEEDED", "player", g, 11572)
check(#TD.Get() == 0, "B shows nothing: the cast belongs to A, got " .. names(TD.Get()))
retarget("Creature-A")
check(names(TD.Get()) == "Rend", "A carries it, got " .. names(TD.Get()))
local g2 = guid()
fire("UNIT_SPELLCAST_SENT", "player", "Mob", g2, 11597)
fire("UNIT_SPELLCAST_FAILED", "player", g2, 11597)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", g2, 11597)
check(byName(TD.Get(), "Sunder Armor") ~= nil, "a cast whose SENT was dropped falls back to the current target")
""")

case("other_units_casts_are_ignored")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
fire("UNIT_SPELLCAST_SENT", "party1", "Mob", "x", 11572)
fire("UNIT_SPELLCAST_SUCCEEDED", "party1", "x", 11572)
check(#TD.Get() == 0, "a party member's cast is not ours")
""")

case("an_expired_ledger_entry_stays_as_an_absent_row_with_expiry_in_the_past")(r"""
local TD = boot()
AURAS = { aura("Rend", NOW + 21, 21, 0, "player", 11572) }
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
IN_COMBAT = true
cast(11572, guid())
NOW = NOW + 30
local e = TD.Get()[1]
check(e and e.expires <= GetTime(), "the entry is still listed, its expiry is past: the view draws it as absent")
""")

case("regen_replaces_the_ledger_with_a_fresh_snapshot")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
cast(11597, guid())
IN_COMBAT = false
AURAS = { aura("Rend", NOW + 9, 21, 0, "player", 11572) }
fire("PLAYER_REGEN_ENABLED"); flushTimers()
check(names(TD.Get()) == "Rend", "after combat the snapshot is the truth, got " .. names(TD.Get()))
-- readable only a beat after regen: FS.OnAurasReadable runs the same refresh
IN_COMBAT = true
fire("PLAYER_REGEN_DISABLED")
IN_COMBAT = false
AURAS = { aura("Rend", NOW + 9, 21, 0, "player", 11572), aura("Expose Armor", NOW + 20, 30, 0, "player", 8647) }
check(#ONREAD >= 1, "the service registered with FS.OnAurasReadable")
for _, fn in ipairs(ONREAD) do fn() end
flushTimers()
check(#TD.Get() == 2, "the late readable callback re-scans, got " .. names(TD.Get()))
""")

case("paladin_judgement_is_left_out_while_the_class_module_area_is_in_use")(r"""
local TD = boot({ class = "PALADIN" })
AURAS = {
    aura("Judgement of Light", NOW + 10, 10, 0, "player", 20185),
    aura("Hammer of Justice", NOW + 4, 6, 0, "player", 853),
}
TD.Subscribe(function() end)
check(#TD.Get() == 2, "no Class Module area: Judgement shows here, got " .. names(TD.Get()))
AREA["class"] = "upper"
for _, fn in ipairs(AREACB) do fn() end
check(names(TD.Get()) == "Hammer of Justice", "the Seal module carries Judgement now, got " .. names(TD.Get()))
AREA["class"] = nil
for _, fn in ipairs(AREACB) do fn() end
check(#TD.Get() == 2, "the area is released: Judgement is back")
local W = boot({ class = "WARRIOR" })
AURAS = { aura("Judgement of Light", NOW + 10, 10, 0, "player", 20185) }
AREA["class"] = "lower"
W.Subscribe(function() end)
check(#W.Get() == 1, "only a Paladin drops Judgement")
""")

case("friendly_and_dead_targets_show_nothing")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Rend", NOW + 12, 21, 0, "player", 11572) }
TD.Subscribe(function() end)
check(#TD.Get() == 1, "setup")
TARGET.dead = true
fire("UNIT_HEALTH", "target")
check(#TD.Get() == 0, "a dead target carries none of our debuffs")
TARGET.dead = false
fire("UNIT_FLAGS", "target")
check(#TD.Get() == 1, "alive again")
TARGET.canAttack = false
retarget("Creature-F")
check(#TD.Get() == 0, "a friendly target shows nothing")
""")

case("priest_and_warlock_rows_come_from_the_hud_ledger_in_profile_order")(r"""
local TD = boot({ class = "WARLOCK", hud = true })
-- the Hud rows: Corruption up 10 s, Agony absent, Immolate unknown (all nil)
local function row(key, icon, remaining, expiresAt, duration)
    return { key = key, icon = icon, remaining = remaining, expiresAt = expiresAt, duration = duration }
end
local function state(rows) return { active = true, row = rows, targetEpoch = 1, inCombat = false } end
AURAS = { aura("Corruption", NOW + 99, 18, 0, "player", 172), aura("Curse of Weakness", NOW + 20, 120, 0, "player", 702, 4009) }
TD.Subscribe(function() end)
check(#HUDSUBS == 1, "a profile with dots subscribes to the Hud, got " .. #HUDSUBS)
for _, fn in ipairs({ unpack(HUDSUBS) }) do
    fn(state({ row("corruption", 7001, 10, NOW + 10, 18), row("bane_agony", 7002, 0), row("immolate", 7003) }))
end
local list = TD.Get()
check(list[1].name == "Corruption" and list[2].name == "Bane of Agony", "profile order first, got " .. names(list))
near(list[1].expires, NOW + 10, "the Hud's timer wins over the scan's"); near(list[1].duration, 18, "duration")
check(list[1].icon == 7001, "icon from the Hud row")
check(list[2].expires <= NOW, "an absent DoT is an entry with an expiry in the past (the recast cue)")
check(not byName(list, "Immolate"), "an unknown DoT draws nothing")
check(byName(list, "Curse of Weakness"), "a player debuff outside the profile still shows, after the profile rows")
check(list[#list].name == "Curse of Weakness", "and it sorts after them")
local n = 0
for _, e in ipairs(list) do if e.name == "Corruption" then n = n + 1 end end
check(n == 1, "the scan's Corruption is not listed twice")
""")

case("a_class_without_hud_dots_does_not_subscribe_to_the_hud")(r"""
local TD = boot({ class = "PALADIN", hud = true })
TD.Subscribe(function() end)
check(#HUDSUBS == 0, "a Paladin profile has seals, no dots: the Hud is not subscribed (it would build state for nothing)")
""")

case("secret_values_are_passed_over_never_compared")(r"""
local TD = boot({ class = "WARRIOR" })
-- a readable snapshot with secret fields: dropped or nil, never touched
AURAS = {
    { name = SECRET, icon = SECRET, count = SECRET, duration = SECRET, expirationTime = SECRET, caster = "player", spellId = SECRET },
    { name = "Rend", icon = SECRET, count = SECRET, duration = SECRET, expirationTime = SECRET, caster = SECRET, spellId = 1 },
    { name = "Sunder Armor", icon = 1, count = 2, duration = 30, expirationTime = SECRET, caster = "player", spellId = 2 },
}
TD.Subscribe(function() end)
local list = TD.Get()
check(#list == 1 and list[1].name == "Sunder Armor", "a secret name or caster is skipped, got " .. names(list))
check(list[1].expires == nil and list[1].count == 2, "a secret expiry reads as unknown")
-- combat events whose every argument is secret
IN_COMBAT = true
fire("UNIT_SPELLCAST_SENT", "player", SECRET, SECRET, SECRET)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", SECRET, SECRET)
fire("UNIT_SPELLCAST_SUCCEEDED", SECRET, SECRET, 11597)
TARGET.guid = SECRET
fire("PLAYER_TARGET_CHANGED")
cast(11597, guid())
check(names(TD.Get()) == "Sunder Armor", "a target whose GUID is secret still takes a ledger entry, got " .. names(TD.Get()))
check(#AURA_TOUCHED == 0, "no aura API touched")
check(next(DEGRADED) == nil, "no degrade logged: " .. tostring(next(DEGRADED)))
""")

case("a_throwing_scan_is_contained_and_logged_once")(r"""
local TD = boot()
AURAS = { { throws = true } }
local ok = pcall(TD.Subscribe, function() end)
check(ok, "the throw never escapes Subscribe")
local ok2 = pcall(function() sync(TD); sync(TD) end)
check(ok2, "nor an event")
check(DEGRADED.targetdebuffs_scan ~= nil, "the failure is logged under targetdebuffs_scan")
""")

case("a_throwing_subscriber_does_not_stop_the_others")(r"""
local TD = boot()
local got = 0
TD.Subscribe(function() end)
AURAS = { aura("Rend", NOW + 12, 21, 0, "player", 11572) }
local first = true
TD.Subscribe(function() if first then first = false else error("boom") end end)
TD.Subscribe(function() got = got + 1 end)
sync(TD)
check(got >= 2, "the callback after a throwing one still ran")
""")

case("a_cast_sent_at_another_unit_is_not_attributed_to_the_target")(r"""
local TD = boot({ class = "WARRIOR" })
TD.Subscribe(function() end)
IN_COMBAT = true
local g = guid()
fire("UNIT_SPELLCAST_SENT", "player", "Mouseover Mob", g, 11572)     -- @mouseover: the target is "Mob"
fire("UNIT_SPELLCAST_SUCCEEDED", "player", g, 11572)
check(#TD.Get() == 0, "a cast aimed at a different unit name is not ours to place on the target, got " .. names(TD.Get()))
cast(11597, guid())                                                   -- SENT names "Mob", the target
check(names(TD.Get()) == "Sunder Armor", "the same name attributes as before")
local g2 = guid()
fire("UNIT_SPELLCAST_SENT", "player", "", g2, 6343)                   -- an empty name cannot say: attribute
fire("UNIT_SPELLCAST_SUCCEEDED", "player", g2, 6343)
check(byName(TD.Get(), "Thunder Clap") ~= nil, "an empty name is not evidence of a different unit")
local g3 = guid()
fire("UNIT_SPELLCAST_SENT", "player", SECRET, g3, 11572)               -- a secret name cannot say either
fire("UNIT_SPELLCAST_SUCCEEDED", "player", g3, 11572)
check(byName(TD.Get(), "Rend") ~= nil, "a secret name attributes to the current target")
""")

case("a_retarget_drops_the_hud_rows_of_the_previous_target")(r"""
local TD = boot({ class = "WARLOCK", hud = true })
TD.Subscribe(function() end)
local state = { active = true, targetEpoch = 1, row = { { key = "corruption", icon = 7001, remaining = 10, expiresAt = NOW + 10, duration = 18 } } }
for _, fn in ipairs({ unpack(HUDSUBS) }) do fn(state) end
check(byName(TD.Get(), "Corruption") ~= nil, "setup: the Hud row is listed")
retarget("Creature-B")
check(byName(TD.Get(), "Corruption") == nil, "until the Hud pushes for the new target the old target's row is gone, got " .. names(TD.Get()))
state.targetEpoch = 2
for _, fn in ipairs({ unpack(HUDSUBS) }) do fn(state) end
check(byName(TD.Get(), "Corruption") ~= nil, "the next push brings the new target's rows")
""")

case("ledger_entries_with_no_expiry_are_pruned_by_age")(r"""
local TD = boot({ class = "ROGUE" })
TD.Subscribe(function() end)
IN_COMBAT = true
cast(8647, guid())                      -- Expose Armor, no known duration, on Creature-A
check(#TD.Get() == 1, "setup")
retarget("Creature-B")
NOW = NOW + 60
retarget("Creature-A")
check(#TD.Get() == 1, "a minute later the entry is still believed")
retarget("Creature-B")
NOW = NOW + 400
retarget("Creature-C")
retarget("Creature-A")
check(#TD.Get() == 0, "after a long time the unknown-duration entry is dropped with its target, got " .. names(TD.Get()))
""")

case("a_cast_out_of_combat_is_corrected_by_the_next_snapshot")(r"""
local TD = boot({ class = "WARRIOR" })
AURAS = { aura("Rend", NOW + 21, 21, 0, "player", 11572) }
TD.Subscribe(function() end)
AURAS = {}; sync(TD)
cast(11572, guid())                     -- readable: an estimate is written, then checked
check(names(TD.Get()) == "Rend", "the estimate shows at once")
flushTimers()
check(#TD.Get() == 0, "the resisted cast leaves no ghost row once the snapshot runs, got " .. names(TD.Get()))
IN_COMBAT = true
local base = #TIMERS
cast(11572, guid())
check(#TIMERS == base and names(TD.Get()) == "Rend", "in combat nothing is queued and the estimate stands")
""")

case("judgement_is_matched_by_spell_id_before_the_name")(r"""
local TD = boot({ class = "PALADIN" })
AURAS = {
    aura("Jugement (localised)", NOW + 10, 10, 0, "player", FS.HudSpells.jd.ids[1]),
    aura("Judgement of Light", NOW + 10, 10, 0, "player", 20185),
    aura("Urteil fremd", NOW + 10, 10, 0, "player", 424242),
}
AREA["class"] = "upper"
TD.Subscribe(function() end)
check(names(TD.Get()) == "Urteil fremd", "a Judgement id is excluded whatever it is called, the English name stays as a fallback; got " .. names(TD.Get()))
""")


def static_checks() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        td = toc.index("Modules/CombatHud/TargetDebuffs.lua")
        for dep in ("Core/Theme.lua", "Core/FrameHelpers.lua", "Modules/CombatHud/HudSpells.lua",
                    "Modules/CombatHud/HudProfiles.lua", "Modules/CombatHud/HudLogic.lua",
                    "Modules/CombatHud/GunsightAreas.lua"):
            out.append((f"toc_after_{Path(dep).stem}", None if toc.index(dep) < td else f"TargetDebuffs.lua must load after {dep}"))
        dots = toc.index("Modules/CombatHud/GunsightDots.lua")
        out.append(("toc_before_gunsight_dots", None if td < dots else "TargetDebuffs.lua must load before GunsightDots.lua"))
    except ValueError as e:
        out.append(("toc_order", f"{e}"))
    src = FRAME_HELPERS.read_text(encoding="utf-8")
    out.append(("read_aura_slot_signature", None if re.search(
        r"function Helpers\.ReadAuraSlot\(unit, index, filter, report\)", src) else
        "FrameHelpers.ReadAuraSlot(unit, index, filter, report) changed; the stub in this harness is out of date"))
    for field in ("name", "icon", "count", "duration", "expirationTime", "caster", "spellId"):
        if not re.search(rf"\b{field} = ", src[src.find("function Helpers.ReadAuraSlot"):][:2600]):
            out.append(("read_aura_slot_shape", f"ReadAuraSlot no longer returns `{field}`"))
            break
    else:
        out.append(("read_aura_slot_shape", None))
    return out


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().SPELLS_SRC = SPELLS.read_text(encoding="utf-8")
    lua.globals().PROFILES_SRC = PROFILES.read_text(encoding="utf-8")
    lua.globals().SERVICE_SRC = SERVICE.read_text(encoding="utf-8")
    lua.globals().HAS_TARGET_SRC = _load_gunsight_harness().theme_target_rule_lua()
    try:
        lua.execute(PRELUDE + "\n" + body)
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
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
