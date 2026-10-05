#!/usr/bin/env python3
"""Runs the real HudSpells.lua, HudProfiles.lua and HudLogic.lua headless against a mock WoW API.

The combat HUD logic layer answers one question per tick: what is the next cast, and what is
up or down on the target. The things worth pinning are the rotation decisions and the
secrecy rules, not the plumbing:

  * the first rotation rule whose spell is known and whose primitives are ALL true wins;
    a primitive that returns nil (unreadable under secrecy) skips the rule, it is never
    guessed, and an unknown spell is skipped (a low level warlock has no Conflagrate);
  * the own-cast ledger (target GUID + spell) expires, honours the pandemic window, the
    bane group and Conflagrate consuming Immolate, and goes unknown on a retarget when the
    GUID is secret;
  * nothing secret is ever compared or indexed: the sentinels raise on any operation, and
    the mock `pcall` records every swallowed SECRET_OP so a guarded-away touch still fails;
  * by-spell aura lookups return ZERO values in combat on 1.60.1 (verified in-game), so the
    proc and buff reads are nil in combat, never "missing";
  * channel tick count and the cut flag, out-of-combat buff reminders, the shard count.

The mock is NOT the real client. Run:

    python3 tools/hud-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
# HUD_HARNESS_ADDON_DIR points the harness at a scratch copy, for mutation checks.
ADDON = Path(os.environ.get("HUD_HARNESS_ADDON_DIR") or HERE.parent / "forever-stuwave")
FILES = ["Modules/CombatHud/HudSpells.lua", "Modules/CombatHud/HudProfiles.lua", "Modules/CombatHud/HudLogic.lua"]

MOCK = r"""
__realType = type
local realType = type
local realPcall = pcall

-- Secret sentinels: type() still reports the pretended type, but every operation raises
-- SECRET_OP, so a forbidden touch either throws or (inside a pcall) is recorded below.
SENT = {}
local function sentinel(kind)
    local function bad(what) return function() error("SECRET_OP " .. what, 2) end end
    local s = setmetatable({}, {
        __index = bad("index"), __newindex = bad("newindex"), __call = bad("call"),
        __concat = bad("concat"), __add = bad("add"), __sub = bad("sub"), __mul = bad("mul"),
        __div = bad("div"), __mod = bad("mod"), __pow = bad("pow"), __unm = bad("unm"),
        __lt = bad("lt"), __le = bad("le"), __eq = bad("eq"), __len = bad("len"),
        __tostring = bad("tostring"),
    })
    SENT[s] = kind
    return s
end
SN, SB, SS, ST = sentinel("number"), sentinel("boolean"), sentinel("string"), sentinel("table")

function type(v)
    local k = SENT[v]
    if k then return k end
    return realType(v)
end
function issecretvalue(v) return SENT[v] ~= nil end

-- Every error a pcall swallows is inspected: a SECRET_OP in there is a forbidden touch that
-- the code under test guarded away, which still means it touched a secret.
__touches = {}
local function noteTouch(ok, ...)
    if not ok then
        local m = ...
        if realType(m) == "string" and string.find(m, "SECRET_OP", 1, true) then
            __touches[#__touches + 1] = m
        end
    end
    return ok, ...
end
function pcall(f, ...) return noteTouch(realPcall(f, ...)) end

__errors = {}        -- FS.LogDegradeOnce lands here: an error escaped a handler or the tick
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function date() return "2026-10-01 12:00:00" end

-- Frames ------------------------------------------------------------------------------
__frames = {}
function CreateFrame(kind, name)
    local f = { _kind = kind, _scripts = {}, _events = {} }
    function f:SetScript(k, fn) self._scripts[k] = fn end
    function f:RegisterEvent(e) self._events[e] = true end
    function f:RegisterUnitEvent(e, ...) self._events[e] = { ... } end
    function f:UnregisterAllEvents() self._events = {} end
    __frames[#__frames + 1] = f
    return f
end

-- World -------------------------------------------------------------------------------
-- id/name table: the dictionary's own rank ids plus rank ids it does NOT list (594, 17311):
-- own casts report the rank actually cast, so those must still map back by name.
NAME_ID = {
    ["Shadow Word: Pain"] = 10894, ["Devouring Plague"] = 25467, ["Mind Blast"] = 10947,
    ["Shadow Word: Death"] = 1309636, ["Mind Flay"] = 18807, ["Smite"] = 25364,
    ["Shadowfiend"] = 401977, ["Shadowform"] = 15473, ["Power Word: Fortitude"] = 10938,
    ["Inner Fire"] = 10952, ["Shoot"] = 5019,
    ["Corruption"] = 25311, ["Bane of Agony"] = 980, ["Bane of Doom"] = 603,
    ["Immolate"] = 25309, ["Conflagrate"] = 1293817, ["Siphon Life"] = 18265,
    ["Shadow Bolt"] = 25307, ["Life Tap"] = 11689, ["Drain Soul"] = 11675,
    ["Drain Life"] = 11700, ["Demon Armor"] = 13787, ["Summon Imp"] = 688,
    ["Vampiric Embrace"] = 15286, ["Power Word: Shield"] = 10901, ["Wrack"] = 1400001,
    ["Shadowburn"] = 18871, ["Soul Fire"] = 6353, ["Incinerate"] = 29722,
    ["Holy Strike"] = 10333, ["Judgement"] = 20271,
    -- the dictionary pins only SoR (21084) and SotC (21082); the other ids here exist for the mock
    -- alone, so a name-only seal still resolves through C_Spell.GetSpellInfo(name)
    ["Seal of Righteousness"] = 21084, ["Seal of the Crusader"] = 21082, ["Seal of Fury"] = 1400101,
    ["Seal of Command"] = 20375, ["Seal of Light"] = 20165, ["Seal of Wisdom"] = 20166,
    ["Seal of Justice"] = 20164,
}
ID_NAME = { [594] = "Shadow Word: Pain", [17311] = "Mind Flay", [695] = "Shadow Bolt" }
for n, id in pairs(NAME_ID) do ID_NAME[id] = n end
-- the dictionary ids that are NOT the mock's top rank still need a name
ID_NAME[589] = "Shadow Word: Pain"; ID_NAME[8092] = "Mind Blast"; ID_NAME[15407] = "Mind Flay"
ID_NAME[686] = "Shadow Bolt"; ID_NAME[172] = "Corruption"; ID_NAME[348] = "Immolate"
ID_NAME[585] = "Smite"; ID_NAME[1243] = "Power Word: Fortitude"; ID_NAME[588] = "Inner Fire"
ID_NAME[1309595] = "Shadow Word: Death"
ID_NAME[6222] = "Corruption"; ID_NAME[6223] = "Corruption"; ID_NAME[7648] = "Corruption"
-- a Holy Strike rank id the dictionary does not list: own casts must still map back by name
ID_NAME[679] = "Holy Strike"
-- Seal of Righteousness rank 1: own casts report the rank id, which the dictionary does not list
ID_NAME[20154] = "Seal of Righteousness"

W = nil
function resetWorld(class)
    W = {
        class = class, combat = false, now = 1000,
        guid = "Creature-A", targetExists = true, canAttack = true,
        known = {}, cd = {}, playerAuras = {}, auras = { player = {}, target = {} },
        aurasSecret = false, aurasSecretThrows = false,
        power = 100, powerMax = 100, health = 100, healthMax = 100,
        thealth = 100, thealthMax = 100, shards = 0, form = 0, pet = true, wand = false, targetDead = false,
        usable = {}, noMana = {}, range = {},
        secret = false, sec = {}, overlay = {}, channelEnd = nil,
    }
    for n in pairs(NAME_ID) do W.known[n] = true end
end
local function S_(kind) return W.secret or W.sec[kind] end

function UnitClass() return W.class, W.class, 1 end
function InCombatLockdown() return W.combat end
function GetTime() return W.now end
function UnitGUID(unit)
    if unit ~= "target" then return "Player-1" end
    if S_("guid") then return SS end
    if not W.targetExists then return nil end
    return W.guid
end
function UnitExists(unit)
    if unit == "pet" then return W.pet end
    return W.targetExists
end
function UnitCanAttack() return W.canAttack end
function UnitIsDead() return W.targetDead end
function UnitIsDeadOrGhost() return W.targetDead or W.targetGhost end
function UnitAffectingCombat() return W.combat end
function GetShapeshiftForm() if S_("form") then return SN end return W.form end
function GetItemCount() if S_("item") then return SN end return W.shards end
function UnitPower() if S_("power") then return SN end return W.power end
function UnitPowerMax() return W.powerMax end
function UnitHealth(unit)
    if S_("health") then return SN end
    if unit == "target" then return W.thealth end
    return W.health
end
function UnitHealthMax(unit)
    if unit == "target" then return W.thealthMax end
    return W.healthMax
end

function IsPlayerSpell(id)
    if S_("known") then return SB end
    return W.known[ID_NAME[id]] == true
end
C_Spell = {}
function C_Spell.GetSpellInfo(x)
    local name, id
    if realType(x) == "string" then
        if not W.known[x] then return nil end
        name, id = x, NAME_ID[x]
    else
        name, id = ID_NAME[x], x
    end
    if not name then return nil end
    return { name = name, spellID = id, iconID = 100000 + id }
end
function C_Spell.GetSpellCooldown(id)
    local c = W.cd[id] or { isActive = false }
    if S_("cd") or (W.cdSecretIds and W.cdSecretIds[id]) then
        return { startTime = SN, duration = SN, isEnabled = SB, isActive = SB, modRate = SN }
    end
    -- in combat on 1.60.1 isActive stays plain while startTime and duration are secret
    if W.cdTimingSecret then
        return { startTime = SN, duration = SN, isEnabled = true, isActive = c.isActive,
                 isOnGCD = c.isOnGCD }
    end
    return { startTime = c.startTime or 0, duration = c.duration or 0, isEnabled = true,
             isActive = c.isActive, isOnGCD = c.isOnGCD }
end
function C_Spell.IsSpellUsable(id)
    if id == 5019 then
        if S_("wand") then return SB, SB end
        return W.wand, false
    end
    if S_("usable") then return SB, SB end
    local u = W.usable[id]
    if u == nil then u = true end
    return u, W.noMana[id] or false
end
function C_Spell.IsSpellInRange(id)
    if S_("range") then return SB end
    return W.range[id]
end
function HasWandEquipped()
    if S_("wand") then return SB end
    return W.wand
end
-- the probe saw IsSpellOverlayed answer a plain false
C_SpellActivationOverlay = {}
function C_SpellActivationOverlay.IsSpellOverlayed(id)
    if S_("overlay") then return SB end
    return W.overlay[id] == true
end
-- name, text, texture, startMs, endMs
function UnitChannelInfo()
    if S_("channel") then return SS, SS, SN, SN, SN end
    return "Mind Flay", "", 1, 0, W.channelEnd and W.channelEnd * 1000
end
C_Secrets = {}
function C_Secrets.ShouldAurasBeSecret()
    if W.aurasSecretThrows then error("boom: ShouldAurasBeSecret") end
    if W.secret then return SB end
    return W.aurasSecret
end
C_UnitAuras = {}
function C_UnitAuras.GetPlayerAuraBySpellID(id)
    -- in combat on 1.60.1 this returns ZERO values, not nil
    if W.combat or W.aurasSecret then return end
    if W.playerAuras[id] then return { spellId = id, name = ID_NAME[id] } end
    return nil
end
function C_UnitAuras.GetAuraDataByIndex(unit, i)
    -- in combat on 1.60.1 this THROWS
    if W.combat or W.aurasSecret then error("Auras cannot be accessed when secret while tainted") end
    return W.auras[unit][i]
end

-- Test helpers ------------------------------------------------------------------------
function check(c, msg) if not c then error("CHECK FAILED: " .. msg, 2) end end
function evframe()
    for _, f in ipairs(__frames) do if f._scripts.OnEvent then return f end end
end
function tickframe()
    for _, f in ipairs(__frames) do if f._scripts.OnUpdate then return f end end
end
function fire(event, ...)
    local f = evframe()
    check(f, "no event frame")
    local ok, err = realPcall(f._scripts.OnEvent, f, event, ...)
    check(ok, "event handler threw on " .. event .. ": " .. tostring(err))
end
function tick(dt)
    W.now = W.now + dt
    local f = tickframe()
    check(f, "no tick frame")
    local ok, err = realPcall(f._scripts.OnUpdate, f, dt)
    check(ok, "OnUpdate threw: " .. tostring(err))
end
function at(t) W.now = 1000 + t end
function cast(name, rankId)
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "cast-guid", rankId or NAME_ID[name])
end
function S() return FS.Hud.GetState() end
function nxt() local s = S(); return s.next and s.next.key end
function rowOf(s)
    local m = {}
    for _, e in ipairs(s.row) do m[e.key] = e end
    return m
end
function keysOf(list)
    local m = {}
    for _, e in ipairs(list) do m[e.key] = true end
    return m
end
function forget(name) W.known[name] = nil; fire("SPELLS_CHANGED") end
-- a player HELPFUL aura as GetAuraDataByIndex returns it: `left` seconds remain of a 30 s seal
function sealAura(name, left)
    return { name = name or "Seal of Righteousness", spellId = NAME_ID[name or "Seal of Righteousness"],
             expirationTime = W.now + (left or 20), duration = 30, sourceUnit = "player" }
end
function retarget(guid) W.guid = guid; fire("PLAYER_TARGET_CHANGED") end
"""


# Small TEST profiles: the engine is tested against these, not against the provisional real
# rotation tables, so swapping the real lists never breaks a behaviour check.
TEST_PROFILES = r"""
FS.HudProfiles.TESTLOCK = {
    row = { "corruption", "bane_agony", "immolate", "siphon", "shadow_bolt" },
    dots = { corruption = { pandemic = 0.3 }, bane_agony = { group = "bane" }, bane_doom = { group = "bane" },
             immolate = { consumedBy = { "conflagrate" } }, siphon = {} },
    cooldowns = { "conflagrate" },
    channels = { drain_soul = {} },
    procs = { shadow_trance = { aura = 17941, glow = "gold" } },
    selfBuffs = { { spell = "demon_armor", oocOnly = true }, { spell = "pet", kind = "pet", oocOnly = true } },
    resource = { shards = { item = 6265 } },
    rotation = {
        { cast = "shadow_bolt", when = { { "procActive", "shadow_trance" } } },
        { cast = "corruption", when = { { "dotMissing", "corruption" } } },
        { cast = "bane_agony", when = { { "dotMissing", "bane_agony" }, { "dotMissing", "bane_doom" } } },
        { cast = "immolate", when = { { "dotMissing", "immolate" } } },
        { cast = "conflagrate", when = { { "cooldownReady", "conflagrate" }, { "not", { "dotMissing", "immolate" } } } },
        { cast = "siphon", when = { { "dotMissing", "siphon" } } },
        { cast = "life_tap", when = { { "resourceBelow", 30 } } },
        { cast = "drain_soul", when = { { "targetHealthBelow", 25 } } },
        { cast = "shoot", filler = "wand", when = { { "wandEquipped" } } },
        { cast = "shadow_bolt", filler = "spell", when = {} },
    },
}
FS.HudProfiles.TESTPRIEST = {
    row = { "sw_pain", "mind_blast", "swd", "mind_flay", "smite" },
    dots = { sw_pain = { pandemic = 0.3 } },
    cooldowns = { "mind_blast", "swd" },
    channels = { mind_flay = { clipAfter = 2 } },
    procs = {},
    selfBuffs = { { spell = "shadowform", kind = "form" }, { spell = "fort", warnBelow = 60, oocOnly = true },
                  { spell = "inner_fire", oocOnly = true } },
    rotation = {
        { cast = "mind_blast", when = { { "freshTarget" }, { "cooldownReady", "mind_blast" } } },
        { cast = "sw_pain", when = { { "dotMissing", "sw_pain" } } },
        { cast = "mind_blast", when = { { "cooldownReady", "mind_blast" } } },
        { cast = "swd", when = { { "cooldownReady", "swd" } } },
        { cast = "shoot", filler = "wand", when = { { "wandEquipped" } } },
        { cast = "mind_flay", filler = "spell", when = {} },
        { cast = "smite", filler = "spell", when = {} },
    },
}
"""

# Each case: (name, class, lua body). The mock is booted fresh per case and the files loaded.
CASES: list[tuple[str, str, str]] = []


def case(name: str, cls: str = "TESTLOCK"):
    def wrap(body: str):
        CASES.append((name, cls, body))
        return body

    return wrap


case("opener_first_matching_rule_wins")(r"""
check(nxt() == "corruption", "opener next: " .. tostring(nxt()))
local s = S()
local row = rowOf(s)
check(s.active == true and s.inCombat == false, "state flags")
check(row.corruption.missing == true and row.corruption.isNext == true, "corruption row")
check(row.shadow_bolt.isNext == false, "only one row is next")
check(s.next.icon ~= nil and s.next.icon == row.corruption.icon, "next icon")
""")

case("midfight_dots_up_picks_the_filler")(r"""
at(0); cast("Corruption"); cast("Bane of Agony"); cast("Immolate"); cast("Siphon Life")
at(2)    -- past the global cooldown window, so isActive is believed
W.cd[1293817] = { isActive = true }
check(nxt() == "shadow_bolt", "dots up, conflagrate on cooldown -> filler, got " .. tostring(nxt()))
local row = rowOf(S())
check(row.corruption.missing == false and row.corruption.remaining > 15, "corruption up")
-- Power and health are SECRET on 1.60.1, so threshold rules never fire there; when the
-- client answers plain the thresholds work.
W.power = 20
check(nxt() == "life_tap", "low mana -> life tap, got " .. tostring(nxt()))
W.power = 100; W.thealth = 20
check(nxt() == "drain_soul", "target below 25% -> drain soul, got " .. tostring(nxt()))
W.sec.power = true; W.sec.health = true
check(nxt() == "shadow_bolt", "secret power/health skip both rules, got " .. tostring(nxt()))
local P = FS.Hud.Primitives
check(P.resourceBelow(30) == nil and P.targetHealthBelow(25) == nil and P.playerHealthAbove(50) == nil,
    "threshold primitives are nil when secret")
""")

case("wand_filler_after_higher_priority_spells")(r"""
at(0); cast("Corruption"); cast("Bane of Agony"); cast("Siphon Life")
at(2)
W.cd[1293817] = { isActive = true }
W.wand = true
check(nxt() == "immolate", "a missing DoT still beats the wand, got " .. tostring(nxt()))
cast("Immolate"); at(4)
check(nxt() == "shoot", "wand is the filler, got " .. tostring(nxt()))
check(S().next.icon ~= nil, "shoot has an icon")
W.wand = false
check(nxt() == "shadow_bolt", "no wand: spell fallback, got " .. tostring(nxt()))
""")

case("unreadable_wand_skips_the_shoot_rule")(r"""
at(0); cast("Corruption"); cast("Bane of Agony"); cast("Siphon Life"); cast("Immolate")
at(2)
W.cd[1293817] = { isActive = true }
W.wand = true; W.sec.wand = true
check(FS.Hud.Primitives.wandEquipped() == nil, "secret answer is nil")
check(nxt() == "shadow_bolt", "shoot rule skipped, got " .. tostring(nxt()))
-- no HasWandEquipped on this client: C_Spell.IsSpellUsable answers instead
W.sec.wand = false
HasWandEquipped = nil
check(FS.Hud.Primitives.wandEquipped() == true and nxt() == "shoot", "IsSpellUsable fallback")
W.wand = false
check(FS.Hud.Primitives.wandEquipped() == false, "no wand")
forget("Shoot")
check(FS.Hud.Primitives.wandEquipped() == false, "unknown Shoot is not equipped")
""")

case("proc_overrides_and_glows")(r"""
W.playerAuras[17941] = true
check(nxt() == "shadow_bolt", "proc -> shadow bolt first, got " .. tostring(nxt()))
check(S().next.glow == "gold", "next glow")
check(rowOf(S()).shadow_bolt.proc == "gold", "row proc glow")
-- in combat the by-spell lookup returns zero values: unknown, never "absent"
W.combat = true
check(FS.Hud.Primitives.procActive("shadow_trance") == nil, "proc is nil in combat")
check(nxt() == "corruption", "no proc read in combat, got " .. tostring(nxt()))
""")

case("bane_group_is_exclusive")(r"""
cast("Corruption")
cast("Bane of Agony")
local P = FS.Hud.Primitives
check(P.dotMissing("bane_agony") == false, "agony up")
check(nxt() == "immolate", "agony up -> no bane rule, got " .. tostring(nxt()))
cast("Bane of Doom")
check(P.dotMissing("bane_doom") == false and P.dotMissing("bane_agony") == true, "doom replaced agony")
check(nxt() == "immolate", "doom up -> still no bane rule, got " .. tostring(nxt()))
check(rowOf(S()).bane_agony.missing == false, "the bane slot reads the group, not just agony")
""")

case("conflagrate_consumes_immolate")(r"""
cast("Corruption"); cast("Bane of Agony"); cast("Immolate")
check(nxt() == "conflagrate", "immolate up + conflagrate ready, got " .. tostring(nxt()))
cast("Conflagrate")
check(FS.Hud.Primitives.dotMissing("immolate") == true, "conflagrate consumed immolate")
W.cd[1293817] = { isActive = true }
check(nxt() == "immolate", "recast immolate, got " .. tostring(nxt()))
""")

case("unknown_spells_are_skipped")(r"""
-- a level 30 warlock: no Conflagrate, Bane of Doom or Siphon Life
forget("Conflagrate"); forget("Bane of Doom"); forget("Siphon Life")
cast("Corruption")
check(nxt() == "bane_agony", "unknown doom counts as missing, not as a skipped rule: " .. tostring(nxt()))
cast("Bane of Agony"); cast("Immolate")
check(nxt() == "shadow_bolt", "unknown conflagrate and siphon are skipped, got " .. tostring(nxt()))
check(rowOf(S()).siphon == nil and rowOf(S()).conflagrate == nil, "unknown spells are not in the row")
check(FS.Hud.Primitives.cooldownReady("conflagrate") == false, "unknown spell is never ready")
""")

case("nil_primitive_skips_rule_not_guessed", "TESTPRIEST")(r"""
cast("Mind Blast"); cast("Shadow Word: Pain")      -- not a fresh target, SW:P up
W.cdSecretIds = { [10947] = true }
local P = FS.Hud.Primitives
check(P.cooldownReady("mind_blast") == nil, "secret cooldown reads nil")
check(nxt() == "swd", "mind blast rule skipped, swd next, got " .. tostring(nxt()))
W.cdSecretIds = nil     -- the same cooldown, readable and ready, would have won
check(nxt() == "mind_blast", "readable cooldown wins, got " .. tostring(nxt()))
""")

case("secret_values_are_never_touched")(r"""
local P = FS.Hud.Primitives
check(nxt() == "corruption", "plain baseline")   -- warms the spell cache like a login would
W.secret = true
fire("PLAYER_TARGET_CHANGED")
fire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, SN)
fire("UNIT_SPELLCAST_CHANNEL_START", SS, SS, SN)
fire("UNIT_AURA", SS)
fire("UNIT_SPELLCAST_SENT", "player", SS, SS, SN)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", SS, SN)
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", SS)
fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", SN)
tick(0.25)
for _, c in ipairs({ { "dotMissing", "corruption" }, { "dotRemaining", "corruption" },
        { "cooldownReady", "conflagrate" }, { "procActive", "shadow_trance" },
        { "buffMissing", "demon_armor" }, { "resourceBelow", 30 }, { "shardsAtLeast", 1 },
        { "playerHealthAbove", 50 }, { "targetHealthBelow", 25 }, { "wandEquipped" },
        { "notEnoughMana", "corruption" }, { "inRange", "corruption" },
        { "not", { "dotMissing", "immolate" } } }) do
    check(FS.Hud.Eval(c) == nil, c[1] .. " must be nil under secrecy")
end
local s = S()
check(s.next and s.next.key == "shadow_bolt", "only the unconditional filler is left, got " .. tostring(nxt()))
check(s.shards == nil and s.channel == nil, "shards and channel unknown")
for _, e in ipairs(s.row) do check(e.missing == nil, e.key .. " missing must be nil") end
check(#__touches == 0, "a secret was touched: " .. tostring(__touches[1]))
""")

case("missing_issecretvalue_counts_as_secret", "TESTPRIEST")(r"""
issecretvalue = nil
fire("SPELLS_CHANGED")
local s = S()
check(#s.row == 0 and s.next == nil, "nothing is trusted without issecretvalue")
check(FS.Hud.Primitives.cooldownReady("mind_blast") == nil, "cooldown nil")
issecretvalue = function() error("boom") end
s = S()
check(#s.row == 0 and s.next == nil, "a throwing issecretvalue counts as secret")
""")

case("ledger_expiry_and_pandemic")(r"""
local P = FS.Hud.Primitives
at(0); cast("Corruption"); cast("Immolate")
at(10)
check(P.dotMissing("corruption") == false and math.abs(P.dotRemaining("corruption") - 8) < 0.01, "corruption mid-life")
at(13)   -- 5s left of 18: inside the 30% pandemic window (5.4s)
check(P.dotMissing("corruption") == true, "pandemic window refreshes early")
at(14.9)
check(P.dotMissing("immolate") == false, "immolate has no pandemic")
at(15.1)
check(P.dotMissing("immolate") == true and P.dotRemaining("immolate") == 0, "immolate expired")
at(18.5)
check(P.dotRemaining("corruption") == 0, "corruption expired")
""")

case("rank_ids_map_by_name")(r"""
-- own casts carry the rank actually cast (Corruption 172, Shadow Bolt 695, ...), never one pinned id
cast("Corruption", 172)
check(FS.Hud.Primitives.dotMissing("corruption") == false, "a rank id not pinned in the dictionary still counts")
""")

case("target_change_with_plain_guids")(r"""
W.combat = true      -- no aura reconcile: this is the ledger alone
local P = FS.Hud.Primitives
cast("Corruption")
check(P.dotMissing("corruption") == false, "up on A")
retarget("Creature-B")
check(P.dotMissing("corruption") == true, "never cast on B")
retarget("Creature-A")
check(P.dotMissing("corruption") == false, "A remembered")
""")

case("target_change_with_secret_guid_marks_unknown")(r"""
W.combat = true
local P = FS.Hud.Primitives
W.sec.guid = true
fire("PLAYER_TARGET_CHANGED")
check(P.dotMissing("corruption") == nil, "nothing known about the new target")
cast("Corruption")
check(P.dotMissing("corruption") == false, "a fresh cast is known")
check(P.dotMissing("immolate") == nil, "other dots stay unknown")
fire("PLAYER_TARGET_CHANGED")
check(P.dotMissing("corruption") == nil, "retarget forgets again")
""")

case("reconcile_out_of_combat_only_when_plain")(r"""
local P = FS.Hud.Primitives
W.auras.target = { { name = "Corruption", spellId = 25311, expirationTime = W.now + 9, duration = 18 } }
retarget("Creature-B")
check(P.dotMissing("corruption") == false and math.abs(P.dotRemaining("corruption") - 9) < 0.01, "aura scan reconciled")
check(P.dotMissing("immolate") == true, "absent aura reads missing")
retarget("Creature-C"); W.aurasSecret = true
retarget("Creature-D")
check(P.dotMissing("corruption") == true, "ShouldAurasBeSecret true: no reconcile")
W.aurasSecret = false; W.aurasSecretThrows = true
retarget("Creature-E")
check(P.dotMissing("corruption") == true, "a throwing ShouldAurasBeSecret: no reconcile")
W.aurasSecretThrows = false; W.combat = true
retarget("Creature-F")
check(P.dotMissing("corruption") == true, "in combat: no reconcile")
""")

case("channel_tick_count_and_cut", "TESTPRIEST")(r"""
at(0); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)   -- a rank not in the dictionary
local c = S().channel
check(c and c.key == "mind_flay" and c.done == 0 and c.ticks == 3 and c.cut == false, "just started")
at(1.05); check(S().channel.done == 1 and S().channel.cut == false, "one tick")
at(2.05); check(S().channel.done == 2 and S().channel.cut == true, "two ticks: cut")
at(3.05); check(S().channel.done == 3 and S().channel.cut == true, "three ticks")
fire("UNIT_SPELLCAST_CHANNEL_STOP", "player", "cg", 17311)
check(S().channel == nil, "stop clears the channel")
""")

case("channel_without_clip_never_cuts")(r"""
at(0); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 11675)
at(6.1)
local c = S().channel
check(c.key == "drain_soul" and c.done == 2 and c.ticks == 5 and c.cut == false, "drain soul tick 2")
at(15.6)
check(S().channel == nil, "a missed STOP event cannot leave the channel up")
""")

case("fresh_target_opener", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
check(P.freshTarget() == true and nxt() == "mind_blast", "fresh target opens with Mind Blast, got " .. tostring(nxt()))
cast("Mind Blast")
W.cd[10947] = { isActive = true }
check(P.freshTarget() == false and nxt() == "sw_pain", "touched target: dot next, got " .. tostring(nxt()))
cast("Shadow Word: Pain")
W.cd[10947] = nil
check(nxt() == "mind_blast", "third rule: Mind Blast again when ready, got " .. tostring(nxt()))
W.combat = true
retarget("Creature-B")
check(P.freshTarget() == true, "a new target is fresh")
retarget("Creature-A")
check(P.freshTarget() == false, "back on the touched target")
W.combat = false; fire("PLAYER_REGEN_ENABLED")
check(P.freshTarget() == true, "leaving combat clears the record")
cast("Inner Fire")
check(P.freshTarget() == true, "a self buff is not a cast on the target")
W.targetDead = true
check(P.freshTarget() == false, "a dead target is not fresh")
W.targetDead = false; W.canAttack = false
check(P.freshTarget() == false, "a friendly target is not fresh")
W.canAttack = true; W.targetExists = false
check(P.freshTarget() == false and nxt() == nil, "no target: no suggestion")
""")

case("spell_state_primitives")(r"""
local P = FS.Hud.Primitives
W.combat = true
check(P.inCombat() == true, "in combat")
W.combat = false
check(P.inCombat() == false, "out of combat")
check(P.notEnoughMana("shadow_bolt") == false, "mana fine")
W.noMana[25307] = true
check(P.notEnoughMana("shadow_bolt") == true, "no mana")
W.range[25307] = true
check(P.inRange("shadow_bolt") == true, "in range")
W.range[25307] = nil
check(P.inRange("shadow_bolt") == nil, "nil range stays nil")
local function orUnknown() return FS.Hud.Eval({ "orUnknown", { "inRange", "shadow_bolt" } }) end
check(orUnknown() == true, "orUnknown: an unreadable range is true")
W.range[25307] = false
check(orUnknown() == false, "orUnknown: a plain false stays false")
W.range[25307] = true
check(orUnknown() == true and FS.Hud.Eval({ "orUnknown", { "not", { "inRange", "shadow_bolt" } } }) == false, "orUnknown: true stays true, wraps not")
check(P.known("shadow_bolt") == true and P.known("corruption") == true, "known")
forget("Corruption")
check(P.known("corruption") == false, "unknown spell: not known")
check(P.notEnoughMana("corruption") == nil, "mana state of an unknown spell is unknowable")
""")

case("low_level_priest_without_shadow_spells", "TESTPRIEST")(r"""
-- a level 14 non-Shadow priest: no Shadowform, Mind Flay, Death or Devouring Plague
forget("Shadowform"); forget("Mind Flay"); forget("Devouring Plague"); forget("Shadow Word: Death")
local s = S()
check(s.active == true, "an unknown shadow spell must not hide the HUD")
check(nxt() == "mind_blast", "fresh target: Mind Blast opens, got " .. tostring(nxt()))
cast("Mind Blast"); W.cd[10947] = { isActive = true }
check(nxt() == "sw_pain", "then SW:P, got " .. tostring(nxt()))
cast("Shadow Word: Pain", 594)
check(nxt() == "smite", "Smite is the filler without Mind Flay or a wand, got " .. tostring(nxt()))
W.wand = true
check(nxt() == "shoot", "a wand beats Smite, got " .. tostring(nxt()))
check(rowOf(S()).mind_flay == nil, "unknown Mind Flay is not in the row")
check(keysOf(S().buffsMissing).shadowform == nil, "no Shadowform reminder when it is unknown")
W.known["Shadowform"] = true; fire("SPELLS_CHANGED")
check(keysOf(S().buffsMissing).shadowform == true, "Shadowform reminder once known and not in form")
W.form = 1
check(keysOf(S().buffsMissing).shadowform == nil, "in form: no reminder")
""")

case("ooc_buff_reminders")(r"""
W.pet = false
local b = keysOf(S().buffsMissing)
check(b.demon_armor and b.pet, "armor and pet reminders out of combat")
W.pet = true
W.auras.player = { { name = "Demon Armor", spellId = 13787, expirationTime = W.now + 1000, duration = 1800 } }
fire("UNIT_AURA", "player")
check(next(keysOf(S().buffsMissing)) == nil, "both up: no reminders")
W.auras.player = {}; W.pet = false; W.combat = true
check(next(keysOf(S().buffsMissing)) == nil, "oocOnly reminders are silent in combat")
check(FS.Hud.Primitives.buffMissing("demon_armor") == nil, "aura scan is nil in combat, not missing")
""")

case("ooc_buff_warn_below", "TESTPRIEST")(r"""
W.auras.player = { { name = "Power Word: Fortitude", spellId = 10938, expirationTime = W.now + 30, duration = 3600 },
                   { name = "Inner Fire", spellId = 10952, expirationTime = W.now + 500, duration = 600 } }
fire("UNIT_AURA", "player")
check(keysOf(S().buffsMissing).fort == true, "30s left of Fortitude is under warnBelow")
check(keysOf(S().buffsMissing).inner_fire == nil, "Inner Fire is fine")
W.auras.player[1].expirationTime = W.now + 3000
fire("UNIT_AURA", "player")
check(keysOf(S().buffsMissing).fort == nil, "plenty of time left")
""")

case("shard_count")(r"""
W.shards = 4
local P = FS.Hud.Primitives
check(S().shards == 4, "state shards")
check(P.shardsAtLeast(3) == true and P.shardsAtLeast(5) == false, "shardsAtLeast")
W.sec.item = true
check(S().shards == nil and P.shardsAtLeast(1) == nil, "secret count is unknown")
""")

case("subscribers_hear_changes_only")(r"""
local builds, real = 0, FS.Hud.GetState
FS.Hud.GetState = function() builds = builds + 1; return real() end
tick(0.25)
check(builds == 0, "no subscribers: the tick builds no state")
local n = 0
local function cb(state) n = n + 1; check(state.row ~= nil, "callback gets the state") end
FS.Hud.Subscribe(cb)
check(n == 1, "Subscribe pushes the current state at once")
check(builds == 1, "Subscribe builds the state once, got " .. builds)
tick(0.1)
check(builds == 1, "the tick is throttled to 0.2s: no state built after 0.1s, got " .. builds)
tick(0.25)
check(builds == 2, "a tick past 0.2s builds the state, got " .. builds)
tick(0.25)
check(n == 1, "first tick: nothing changed since the push")
cast("Corruption")
tick(0.25)
check(n == 2, "a changed state publishes")
tick(0.25)
check(n == 2, "unchanged state does not republish")
FS.Hud.Unsubscribe(cb)
cast("Immolate"); tick(0.25)
check(n == 2, "unsubscribed")
""")

case("retarget_mid_cast_lands_on_the_cast_target")(r"""
local P = FS.Hud.Primitives
W.combat = true      -- the ledger alone
-- Corruption goes out at A, the player switches to B during the cast, SUCCEEDED lands with B up
fire("UNIT_SPELLCAST_SENT", "player", "A", "g1", 25311)
retarget("Creature-B")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g1", 25311)
check(P.dotMissing("corruption") == true, "B never got the dot")
retarget("Creature-A")
check(P.dotMissing("corruption") == false, "A did")
-- a hard cast is captured at START as well
fire("UNIT_SPELLCAST_START", "player", "g2", 25309)
retarget("Creature-B")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g2", 25309)
check(P.dotMissing("immolate") == true, "B has no Immolate")
retarget("Creature-A")
check(P.dotMissing("immolate") == false, "A has Immolate")
-- a secret target GUID: the cast is kept only while the target has not changed since SENT
W.sec.guid = true; fire("PLAYER_TARGET_CHANGED")
fire("UNIT_SPELLCAST_SENT", "player", "A", "g3", 18265)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g3", 18265)
check(P.dotMissing("siphon") == false, "same target: the cast is recorded")
fire("UNIT_SPELLCAST_SENT", "player", "A", "g4", 980)
fire("PLAYER_TARGET_CHANGED")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g4", 980)
check(P.dotMissing("bane_agony") == nil, "retargeted under a secret GUID: nowhere to record it")
""")

case("dead_target_gets_no_suggestion")(r"""
check(nxt() == "corruption", "baseline")
W.targetDead = true
check(nxt() == nil, "a dead target gets no suggestion, got " .. tostring(nxt()))
""")

case("enemy_ghost_target_gets_no_suggestion")(r"""
-- the rotation HUD and the DoT scale (FS.TargetTakesDots) agree: an enemy ghost counts as dead
check(nxt() == "corruption", "baseline")
W.targetGhost = true
check(nxt() == nil, "an enemy ghost gets no suggestion, got " .. tostring(nxt()))
W.targetGhost = false
check(nxt() == "corruption", "a live target again: the suggestion is back")
""")

case("gcd_window_heuristic_without_isongcd")(r"""
local P = FS.Hud.Primitives
-- isActive reads true during the GCD and the mock has no isOnGCD field (the probe saw none)
W.cd[25307] = { isActive = true }      -- Shadow Bolt: no cooldown of its own
W.cd[1293817] = { isActive = true }    -- Conflagrate: a real 10s cooldown we never cast
at(0); cast("Corruption")
at(0.5)
check(P.cooldownReady("shadow_bolt") == true, "no-cooldown spell inside the GCD window is ready")
check(P.cooldownReady("conflagrate") == true, "a real cooldown we never cast, inside the window: ready")
at(2.0)
check(P.cooldownReady("shadow_bolt") == false, "outside the window isActive is believed")
check(P.cooldownReady("conflagrate") == false, "outside the window isActive is believed")
at(3); cast("Conflagrate"); at(3.5)
check(P.cooldownReady("conflagrate") == false, "our own cast of it is still on cooldown inside the window")
at(5); cast("Corruption"); at(5.5)
check(P.cooldownReady("conflagrate") == false, "another spell's GCD does not free a cooldown we cast")
""")

case("affordability_is_implicit_in_every_rule")(r"""
W.noMana[25311] = true
check(nxt() == "bane_agony", "Corruption without mana is skipped, got " .. tostring(nxt()))
W.noMana[25311] = nil; W.usable[25311] = false
check(nxt() == "bane_agony", "an unusable Corruption is skipped, got " .. tostring(nxt()))
W.noMana[25311] = true; W.sec.usable = true
check(nxt() == "corruption", "an unreadable answer never skips, got " .. tostring(nxt()))
""")

case("engaged_for_counts_harmful_casts_only")(r"""
local P = FS.Hud.Primitives
check(P.engagedFor(6) == false, "not engaged yet")
at(0); cast("Life Tap")
check(P.engagedFor(6) == false and P.freshTarget() == true, "Life Tap is not a cast on the target")
cast("Corruption")
at(5.9); check(P.engagedFor(6) == false, "5.9s")
at(6.1); check(P.engagedFor(6) == true, "6.1s")
cast("Shadow Bolt")
check(P.engagedFor(6) == true, "the clock runs from the FIRST harmful cast")
retarget("Creature-B")
check(P.engagedFor(6) == false, "another target is not engaged")
W.targetExists = false
check(P.engagedFor(6) == nil, "no target is unknown")
""")

case("corruption_duration_follows_the_cast_rank")(r"""
local P = FS.Hud.Primitives
local function left(id) at(0); cast("Corruption", id); return P.dotRemaining("corruption") end
check(math.abs(left(172) - 12) < 0.01, "rank 1 lasts 12s")
check(math.abs(left(6222) - 15) < 0.01, "rank 2 lasts 15s")
check(math.abs(left(6223) - 18) < 0.01, "rank 3 lasts 18s")
check(math.abs(left(25311) - 18) < 0.01, "the top rank lasts 18s")
""")

case("dot_rows_carry_expires_at_and_duration")(r"""
-- The gunsight DoT scale draws from expiresAt (an absolute GetTime) so a chip moves smoothly
-- between pushes; duration is the full length of the cast actually made.
at(0); cast("Corruption", 172); cast("Immolate")
local row = rowOf(S())
check(math.abs(row.corruption.expiresAt - (W.now + 12)) < 0.001, "corruption rank 1 expiresAt, got " .. tostring(row.corruption.expiresAt))
check(row.corruption.duration == 12, "corruption rank 1 duration, got " .. tostring(row.corruption.duration))
check(row.immolate.duration == 15 and math.abs(row.immolate.expiresAt - (W.now + 15)) < 0.001, "immolate timing")
local exp0 = row.corruption.expiresAt
at(5)
local row5 = rowOf(S())
check(row5.corruption.expiresAt == exp0, "expiresAt is absolute: it does not move as time passes")
check(math.abs(row5.corruption.remaining - 7) < 0.001 and math.abs(row5.corruption.expiresAt - GetTime() - row5.corruption.remaining) < 0.001, "remaining stays expiresAt - now")
check(row5.shadow_bolt.expiresAt == nil and row5.shadow_bolt.duration == nil, "a non DoT row has no timing")
check(row5.siphon.expiresAt == nil and row5.siphon.duration == nil and row5.siphon.missing == true, "a DoT that is not up has no timing")
at(13)
local rowGone = rowOf(S())
check(rowGone.corruption.remaining == 0 and rowGone.corruption.expiresAt == nil, "an expired DoT has no expiresAt")
""")

case("dot_timing_follows_the_bane_group_and_the_reconcile")(r"""
at(0); cast("Bane of Doom")
local row = rowOf(S())
check(row.bane_agony.missing == false, "the slot reads as the whole group")
check(row.bane_agony.duration == 60 and math.abs(row.bane_agony.expiresAt - (W.now + 60)) < 0.001, "the up bane's timing fills the slot")
-- the reconcile takes the aura's own duration and expiry
W.auras.target = { { name = "Immolate", spellId = 25309, expirationTime = W.now + 9, duration = 15 } }
retarget("Creature-B")
local r2 = rowOf(S())
check(math.abs(r2.immolate.expiresAt - (W.now + 9)) < 0.001 and r2.immolate.duration == 15, "reconcile timing from the aura")
W.auras.target = { { name = "Immolate", spellId = 25309, expirationTime = W.now + 9 } }
retarget("Creature-C")
local r3 = rowOf(S())
check(r3.immolate.duration == 15, "an aura with no readable duration falls back to the dictionary length")
""")

case("dot_timing_does_not_change_the_push_frequency")(r"""
tick(0.25)                                -- the first pass reconciles the (empty) target: do it before the cast
at(0); cast("Corruption", 25311)
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
check(n == 1, "pushed at once")
at(1.0); tick(0.25)                       -- 16.75 s left: the whole second changed
check(n == 2, "the whole second changed, n = " .. n)
at(1.3); tick(0.25)                       -- 16.45 s: the same second
check(n == 2, "within a second nothing republishes, n = " .. n)
at(1.8); tick(0.25)                       -- 15.95 s: the next second
check(n == 3, "next second republishes, n = " .. n)
""")

case("target_change_bumps_the_exported_epoch_and_pushes")(r"""
tick(0.25)
retarget("Creature-A")
tick(0.25)
local last, n = nil, 0
FS.Hud.Subscribe(function(s) last = s; n = n + 1 end)
check(n == 1, "pushed at once")
local e0 = last.targetEpoch
check(type(e0) == "number" and e0 == math.floor(e0), "targetEpoch is a plain integer, got " .. tostring(e0))
tick(0.25)
check(n == 1, "nothing changed: no push")
-- two mobs with no DoT and identical timers: only the epoch differs, and it must still push
retarget("Creature-B")
tick(0.25)
check(n == 2, "a target switch with identical timers still pushes, n = " .. n)
check(last.targetEpoch == e0 + 1, "the epoch moved by one, got " .. tostring(last.targetEpoch))
tick(0.25)
check(n == 2, "no further push without a change")
check(S().targetEpoch == last.targetEpoch, "GetState carries the current epoch")
-- never the GUID or anything else secret: the exported value is the integer alone
for k, v in pairs(S()) do
    if type(v) == "string" then check(not v:find("Creature", 1, true), "state." .. k .. " leaks a guid") end
end
check(tostring(last.targetEpoch):find("Creature", 1, true) == nil, "epoch is not a guid")
""")

case("overlay_is_the_first_proc_source")(r"""
local P = FS.Hud.Primitives
FS.Hud.GetProfile().procs.shadow_trance.overlaySpell = "shadow_bolt"
W.combat = true
W.sec.overlay = true
check(P.procActive("shadow_trance") == nil, "a secret overlay answer in combat is unknown")
W.sec.overlay = false
check(P.procActive("shadow_trance") == false, "plain false from the overlay API")
W.overlay[25307] = true
check(P.procActive("shadow_trance") == true and nxt() == "shadow_bolt", "IsSpellOverlayed true")
W.overlay[25307] = nil
fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", 686)      -- a rank id the dictionary pins: same key
check(P.procActive("shadow_trance") == true and S().next.glow == "gold", "GLOW_SHOW")
fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", SN)       -- a secret id is ignored
check(P.procActive("shadow_trance") == true, "a secret spell id changes nothing")
fire("SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", 686)
check(P.procActive("shadow_trance") == false, "GLOW_HIDE")
W.combat = false; W.playerAuras[17941] = true
check(P.procActive("shadow_trance") == true, "out of combat the aura read backs up a plain false")
W.playerAuras[17941] = nil; fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", 686)
check(P.procActive("shadow_trance") == true, "a glowing overlay is trusted over a missing aura")
""")

case("channel_update_rereads_the_end", "TESTPRIEST")(r"""
at(0); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)
at(1.0); W.channelEnd = 1002.0                        -- clipped: ends at t = 2
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "cg", 17311)
at(2.6)
check(S().channel == nil, "the re-read end expired the channel")
at(10); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)
at(11); W.sec.channel = true
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "cg", 17311)
at(12.9)
check(S().channel ~= nil, "a secret end keeps the old one")
""")

case("zero_value_aura_scan_is_unknown", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
local calls = 0
C_UnitAuras.GetAuraDataByIndex = function(unit)      -- ZERO values, no throw
    if unit == "player" then calls = calls + 1 end
end
cast("Shadow Word: Pain")
retarget("Creature-A")                                -- a reconcile attempt
check(P.dotMissing("sw_pain") == false, "a zero-value scan is not 'no auras': the ledger stands")
fire("UNIT_AURA", "player")
local b = keysOf(S().buffsMissing)
check(b.fort == nil and b.inner_fire == nil, "an unreadable scan reports no reminders")
check(calls == 1, "one scan attempt per state, got " .. calls)
""")

case("player_buff_scan_runs_on_unit_aura_only")(r"""
local calls, real = 0, C_UnitAuras.GetAuraDataByIndex
C_UnitAuras.GetAuraDataByIndex = function(unit, ...)
    if unit == "player" then calls = calls + 1 end
    return real(unit, ...)
end
S(); S(); S()
check(calls == 1, "cached after the first scan, got " .. calls)
fire("UNIT_AURA", "player")
S(); S()
check(calls == 2, "UNIT_AURA(player) dirties it once, got " .. calls)
W.combat = true; fire("PLAYER_REGEN_ENABLED"); W.combat = false
S()
check(calls == 3, "leaving combat dirties it, got " .. calls)
""")

case("real_priest_opener_and_wand_first_filler", "PRIEST")(r"""
local prof = FS.Hud.GetProfile()
W.form = 1                       -- in Shadowform
check(nxt() == "mind_blast", "opener: Mind Blast on a fresh target, got " .. tostring(nxt()))
at(0); cast("Mind Blast"); W.cd[10947] = { isActive = true }
check(nxt() == "sw_pain", "then Shadow Word: Pain, got " .. tostring(nxt()))
cast("Shadow Word: Pain"); W.wand = true
at(2)
check(nxt() == "shoot", "Mind Blast on cooldown: the wand, got " .. tostring(nxt()))
W.cd[10947] = nil
check(nxt() == "mind_blast", "Mind Blast again when it is ready, got " .. tostring(nxt()))
W.cd[10947] = { isActive = true }
check(prof.fillerOrder == nil or prof.fillerOrder == "wand", "wand first is the default")
prof.fillerOrder = "spell"
check(nxt() == "mind_flay", "fillerOrder = spell swaps Mind Flay ahead of the wand, got " .. tostring(nxt()))
""")

case("wand_shot_does_not_open_the_gcd_window", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
-- Mind Blast went on cooldown before the addon loaded: no ledger entry, isActive true
W.cd[10947] = { isActive = true }
at(0.7); cast("Shoot")
at(1.0)
check(P.cooldownReady("mind_blast") == false, "a wand shot is off the GCD: no window, isActive is believed")
-- control: a spell that does start the GCD opens it (the documented cost of the heuristic)
cast("Smite"); at(1.3)
check(P.cooldownReady("mind_blast") == true, "a real GCD opens the window")
""")

case("wand_shot_does_not_engage_the_target", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
at(0); cast("Shoot")
check(P.freshTarget() == true, "a wand shot is not an engagement")
check(nxt() == "mind_blast", "the Mind Blast opener survives a first wand shot, got " .. tostring(nxt()))
check(P.engagedFor(1) == false, "no fight clock yet")
at(5); cast("Shadow Word: Pain")
at(6.5)
check(P.engagedFor(1) == true and P.engagedFor(2) == false, "the clock runs from the first harmful cast, not the wand")
""")

case("cast_times_survive_entering_the_world", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
W.combat = true      -- no aura reconcile after the loading screen: the ledger alone
at(0); cast("Mind Blast"); cast("Shadow Word: Pain")
fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)
check(S().channel ~= nil and P.freshTarget() == false and P.dotMissing("sw_pain") == false, "setup")
W.cd[10947] = { isActive = true }
fire("PLAYER_ENTERING_WORLD")
check(P.dotMissing("sw_pain") == true, "the DoT ledger is wiped")
check(P.freshTarget() == true, "the engaged record is wiped")
check(S().channel == nil, "the channel is cleared")
-- GetTime is monotonic across a loading screen: our own cast times stay valid
at(0.5); cast("Smite")
at(1.0)
check(P.cooldownReady("mind_blast") == false, "our Mind Blast cast is still remembered")
""")

case("plain_cooldown_timing_beats_the_heuristic", "TESTPRIEST")(r"""
local P = FS.Hud.Primitives
at(0); cast("Smite")                 -- opens the GCD window
at(0.5)
-- Mind Blast was cast 5s ago before the addon loaded: plain timing says 3s left
W.cd[10947] = { isActive = true, startTime = W.now - 5, duration = 8 }
check(P.cooldownReady("mind_blast") == false, "plain timing: still on cooldown inside the window")
local e = rowOf(S()).mind_blast
check(e.onCd == true and math.abs(e.cdRemaining - 3) < 0.01, "remaining from the plain timing")
W.cd[10947] = { isActive = true, startTime = W.now - 9, duration = 8 }
check(P.cooldownReady("mind_blast") == true, "plain timing: the cooldown is over")
-- a cooldown no longer than the GCD is the GCD, whatever the ledger says
at(3)
W.cd[25364] = { isActive = true, startTime = W.now - 0.2, duration = 1.5 }
check(P.cooldownReady("smite") == true, "a GCD-length cooldown reads ready outside the window")
-- in combat the timing is secret: never touched, the heuristic answers
W.cdTimingSecret = true
check(P.cooldownReady("smite") == false, "secret timing outside the window: isActive is believed")
at(3.5); cast("Smite"); at(4.0)
check(P.cooldownReady("smite") == true, "secret timing inside the window: the heuristic")
at(6)
local e2 = rowOf(S()).mind_blast
check(e2.onCd == true and e2.cdRemaining == nil, "secret timing: on cooldown, no remaining time")
""")

case("plain_isongcd_means_ready")(r"""
local P = FS.Hud.Primitives
W.cd[25307] = { isActive = true, isOnGCD = true }          -- no ledger, no window
check(P.cooldownReady("shadow_bolt") == true, "a plain isOnGCD is honoured")
W.cd[1293817] = { isActive = true, isOnGCD = true }        -- a real cooldown spell: only the GCD
check(P.cooldownReady("conflagrate") == true, "isOnGCD on a spell with a real cooldown")
W.cd[1293817] = { isActive = true, isOnGCD = false }
check(P.cooldownReady("conflagrate") == false, "isOnGCD false: the cooldown is real")
W.cd[1293817] = { isActive = true, isOnGCD = SB }
check(P.cooldownReady("conflagrate") == false, "a secret isOnGCD is not trusted")
""")

case("channel_update_end_is_bounded", "TESTPRIEST")(r"""
at(0); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)     -- ends at t = 3
at(1); W.channelEnd = 1090; fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "cg", 17311)
at(3.6)
check(S().channel == nil, "an end 60s or more past the start is not believed")
at(10); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)
at(11); W.channelEnd = 1005; fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "cg", 17311)
at(12)
check(S().channel ~= nil, "an end before the start is not believed: the channel keeps its own end")
at(13.6)
check(S().channel == nil, "and that own end still expires it")
at(20); fire("UNIT_SPELLCAST_CHANNEL_START", "player", "cg", 17311)
at(21); W.channelEnd = 1079.9; fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "cg", 17311)
at(40)
check(S().channel ~= nil, "an end just inside the bound is believed")
""")

case("reconcile_found_dot_bounds_the_fight_age")(r"""
local P = FS.Hud.Primitives
at(0)
-- the target already carries our Corruption, applied 9s ago (expires in 9 of 18)
W.auras.target = { { name = "Corruption", spellId = 25311, expirationTime = W.now + 9, duration = 18 } }
retarget("Creature-B")
check(P.freshTarget() == false, "it carries our DoT: not a fresh target")
check(P.engagedFor(6) == true and P.engagedFor(10) == false, "fight age is bounded from below by the aura application")
at(5)
check(P.engagedFor(10) == true, "and it keeps counting")
-- no readable duration: the age is unknown, never guessed
W.auras.target = { { name = "Corruption", spellId = 25311, expirationTime = W.now + 9 } }
retarget("Creature-C")
check(P.freshTarget() == false, "still not fresh")
check(P.engagedFor(6) == nil, "unknown age is nil")
""")

case("prune_drops_stale_pending_casts_and_survives_false_entries")(r"""
local P = FS.Hud.Primitives
W.combat = true
at(0); cast("Immolate"); cast("Conflagrate"); cast("Corruption")    -- Immolate is a `false` entry now
tick(0.25)                                                           -- the first sweep
at(1); fire("UNIT_SPELLCAST_SENT", "player", "A", "g1", 25311)
retarget("Creature-B")
at(70); tick(0.25)                                                   -- the next sweep: g1 is stale
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g1", 25311)
check(P.dotMissing("corruption") == false, "a pruned pending cast falls back to the current target")
retarget("Creature-A")
check(P.dotMissing("corruption") == true and P.dotMissing("immolate") == true, "expired and consumed entries read missing")
""")

case("zero_value_proc_lookup_out_of_combat_is_unknown")(r"""
local P = FS.Hud.Primitives
check(P.procActive("shadow_trance") == false, "a plain nil from the lookup is 'absent'")
W.playerAuras[17941] = true
check(P.procActive("shadow_trance") == true, "present")
C_UnitAuras.GetPlayerAuraBySpellID = function() end        -- ZERO values, out of combat
check(P.procActive("shadow_trance") == nil, "zero values are unknown, not absent")
""")

case("signature_follows_cooldown_remaining_and_icon", "TESTPRIEST")(r"""
W.cd[10947] = { isActive = true, startTime = W.now, duration = 8 }
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
check(n == 1, "pushed at once")
at(1.0); tick(0.25)                       -- 6.75s left: the whole second changed
check(n == 2, "a ticking cooldown republishes, n = " .. n)
at(1.3); tick(0.25)                       -- 6.45s: the same second
check(n == 2, "within a second nothing republishes, n = " .. n)
NAME_ID["Smite"] = 26000; ID_NAME[26000] = "Smite"       -- a new rank: a new icon
fire("SPELLS_CHANGED"); tick(0.25)
check(n == 3, "a changed icon republishes, n = " .. n)
""")

case("filler_order_spell_keeps_the_wand_ahead_of_the_last_spell", "TESTPRIEST")(r"""
local prof = FS.Hud.GetProfile()
at(0); cast("Mind Blast"); cast("Shadow Word: Pain")
W.cd[10947] = { isActive = true }; W.cd[1309636] = { isActive = true }
at(2); W.wand = true
check(nxt() == "shoot", "default: the wand leads")
prof.fillerOrder = "spell"
check(nxt() == "mind_flay", "spell first: Mind Flay")
W.noMana[18807] = true
check(nxt() == "shoot", "Mind Flay unaffordable: the wand takes over before Smite, got " .. tostring(nxt()))
W.wand = false
check(nxt() == "smite", "no wand: Smite stays the last resort, got " .. tostring(nxt()))
""")

case("real_priest_opener_needs_range", "PRIEST")(r"""
W.form = 1
W.range[10947] = true
check(nxt() == "mind_blast", "in range: the opener, got " .. tostring(nxt()))
W.range[10947] = false
check(nxt() == "sw_pain", "out of range: the opener is skipped, SW:P pulls, got " .. tostring(nxt()))
W.range[10947] = nil
check(nxt() == "mind_blast", "an unreadable range never hides the opener, got " .. tostring(nxt()))
W.range[10947] = false; W.sec.range = true
check(nxt() == "mind_blast", "a secret range never hides it either, got " .. tostring(nxt()))
""")

case("real_priest_form_gates_and_shadowfiend", "PRIEST")(r"""
W.form = 0
check(nxt() == "shadowform", "known and not in form: Shadowform first, got " .. tostring(nxt()))
W.form = 1; W.wand = true
at(0); cast("Mind Blast"); cast("Shadow Word: Pain")
W.cd[10947] = { isActive = true }
local b = keysOf(S().buffsMissing)
check(b.fort and b.inner_fire, "Fortitude and Inner Fire reminders out of combat")
check(b.pw_shield == nil, "Power Word: Shield is not a maintained buff")
at(2)
check(nxt() == "shoot", "a young fight: no Plague, no Death, the wand, got " .. tostring(nxt()))
at(6.5)
check(nxt() == "dplague", "after 6s: Devouring Plague, got " .. tostring(nxt()))
cast("Devouring Plague")
at(7.5)
check(nxt() == "shoot", "Plague up, Death still gated, got " .. tostring(nxt()))
at(8.5)
check(nxt() == "swd", "after 8s: Shadow Word: Death, got " .. tostring(nxt()))
cast("Shadow Word: Death"); W.cd[1309636] = { isActive = true }
at(10.5)
check(nxt() == "shoot", "Death on cooldown, got " .. tostring(nxt()))
W.noMana[10947] = true; W.combat = true
check(nxt() == "sfiend", "cannot afford Mind Blast in combat: Shadowfiend, got " .. tostring(nxt()))
W.combat = false
check(nxt() == "shoot", "Shadowfiend is a combat rule, got " .. tostring(nxt()))
W.wand = false
check(nxt() == "mind_flay", "no wand: Mind Flay, got " .. tostring(nxt()))
forget("Mind Flay")
check(nxt() == "smite", "no Mind Flay either: Smite, got " .. tostring(nxt()))
""")

case("real_warlock_opener_wand_first_and_life_tap", "WARLOCK")(r"""
-- a level 20 warlock: no Wrack, Soul Fire, Incinerate, Conflagrate, Shadowburn, Siphon Life or Doom
for _, n in ipairs({ "Wrack", "Soul Fire", "Incinerate", "Conflagrate", "Shadowburn", "Siphon Life",
        "Bane of Doom" }) do W.known[n] = nil end
fire("SPELLS_CHANGED")
W.shards = 3
at(0)
W.overlay[25307] = true
check(nxt() == "shadow_bolt", "Nightfall glow: Shadow Bolt first, got " .. tostring(nxt()))
W.overlay[25307] = nil
check(nxt() == "immolate", "opener: the hard cast, got " .. tostring(nxt()))
cast("Immolate")
check(nxt() == "corruption", "then Corruption, got " .. tostring(nxt()))
cast("Corruption")
check(nxt() == "bane_agony", "then Bane of Agony, got " .. tostring(nxt()))
cast("Bane of Agony")
W.wand = true
check(nxt() == "shoot", "dots up: the wand before Shadow Bolt, got " .. tostring(nxt()))
W.wand = false
check(nxt() == "shadow_bolt", "no wand: Shadow Bolt, got " .. tostring(nxt()))
W.shards = 0
check(nxt() == "drain_soul", "under 3 shards: Drain Soul before the filler, got " .. tostring(nxt()))
W.shards = 3
W.noMana[25307] = true                 -- "cannot afford a Shadow Bolt" stands in for low mana
W.combat = true
check(nxt() == "life_tap", "no mana and no wand: Life Tap even in combat, got " .. tostring(nxt()))
W.wand = true
check(nxt() == "shoot", "with a wand Life Tap waits in combat, got " .. tostring(nxt()))
W.combat = false
check(nxt() == "life_tap", "out of combat: Life Tap whatever the wand, got " .. tostring(nxt()))
""")

case("real_warlock_spec_branches_and_fight_age_gates", "WARLOCK")(r"""
W.shards = 3; W.wand = true
at(0)
W.overlay[6353] = true
check(nxt() == "soul_fire", "Decimation glow: Soul Fire first, got " .. tostring(nxt()))
W.overlay[6353] = nil
-- Affliction: Wrack is known, Immolate is dropped
check(nxt() == "corruption", "Wrack known: Corruption opens, got " .. tostring(nxt()))
cast("Corruption")
check(nxt() == "bane_agony", "got " .. tostring(nxt()))
cast("Bane of Agony")
check(nxt() == "siphon", "got " .. tostring(nxt()))
cast("Siphon Life")
at(2)
check(nxt() == "wrack", "the Shadow DoTs are up: Wrack, got " .. tostring(nxt()))
cast("Wrack")
check(nxt() == "shoot", "a young fight: no Shadowburn, no Soul Fire, the wand, got " .. tostring(nxt()))
at(6.5)
check(nxt() == "shadowburn", "after 6s: Shadowburn, got " .. tostring(nxt()))
cast("Shadowburn"); W.cd[18871] = { isActive = true }
at(7.2)
check(nxt() == "soul_fire", "after 7s: Soul Fire, got " .. tostring(nxt()))
-- Destruction: no Wrack, Immolate returns, Conflagrate and Incinerate follow it
W.known["Wrack"] = nil; W.known["Soul Fire"] = nil; fire("SPELLS_CHANGED")
retarget("Creature-B")
at(20)
check(nxt() == "immolate", "got " .. tostring(nxt()))
cast("Immolate"); cast("Corruption"); cast("Bane of Agony"); cast("Siphon Life")
check(nxt() == "conflagrate", "Immolate up and Conflagrate ready, got " .. tostring(nxt()))
W.cd[1293817] = { isActive = true }
at(22)
check(nxt() == "incinerate", "Conflagrate on cooldown, a young fight: Incinerate, got " .. tostring(nxt()))
""")

# The real rotations are data and get re-researched, so only their STRUCTURE is pinned here
# (every key and primitive they name exists), plus the decisions the user made explicitly:
# the priest opener and the wand-first filler default (see real_priest_opener_and_wand_first_filler)
# and the warlock wand-first filler, Life Tap and shard rules. The real_* cases above pin which
# rule wins in each situation, so deleting a rule fails the suite.
STRUCTURE = r"""
local prof = FS.Hud.GetProfile()
check(prof, "profile loaded for the class")
local D, P = FS.HudSpells, FS.Hud.Primitives
local function spell(k, where) check(D[k], where .. " names a spell missing from the dictionary: " .. tostring(k)) end
for _, k in ipairs(prof.row) do spell(k, "row") end
local inRow = {}
for _, k in ipairs(prof.row) do inRow[k] = true end
for _, k in ipairs(prof.cooldowns) do
    spell(k, "cooldowns")
    check(D[k] and type(D[k].cooldown) == "number", "cooldowns names " .. k .. " which has no numeric cooldown in the dictionary, so the in-combat window reads it as ready")
    check(inRow[k], "cooldowns names " .. k .. " which is not in the row, so it is never reported")
end
for k, d in pairs(prof.dots) do
    spell(k, "dots")
    check(D[k].apply, "dot " .. k .. " has no apply duration")
    for _, c in ipairs(d.consumedBy or {}) do spell(c, "consumedBy") end
end
for k, ch in pairs(prof.channels) do
    spell(k, "channels")
    check((ch.period or D[k].period) and (ch.ticks or D[k].ticks), "channel " .. k .. " has no tick data")
end
for k, pr in pairs(prof.procs) do
    if pr.overlaySpell then spell(pr.overlaySpell, "proc " .. k .. " overlaySpell") end
end
check(prof.fillerOrder == nil or prof.fillerOrder == "wand" or prof.fillerOrder == "spell", "fillerOrder")
for _, b in ipairs(prof.selfBuffs) do spell(b.spell, "selfBuffs") end
local function walk(cond)
    local name = cond[1]
    if name == "not" or name == "orUnknown" then return walk(cond[2]) end
    check(P[name], "rotation uses an unknown primitive: " .. tostring(name))
    if name == "procActive" then check(prof.procs[cond[2]], "unknown proc " .. tostring(cond[2])) end
    if name == "dotMissing" or name == "dotRemaining" then check(prof.dots[cond[2]], "not a tracked dot: " .. tostring(cond[2])) end
    if name == "cooldownReady" or name == "notEnoughMana" or name == "inRange" or name == "known" then
        spell(cond[2], name)
    end
end
for _, rule in ipairs(prof.rotation) do
    spell(rule.cast, "rotation cast")
    check(rule.filler == nil or rule.filler == "wand" or rule.filler == "spell", "filler tag")
    for _, c in ipairs(rule.when) do walk(c) end
end
local last = prof.rotation[#prof.rotation]
check(#last.when == 0, "the last rule is an unconditional filler")
local s = S()
check(s.active and s.next, "with everything known there is always a next cast, got none")
"""
case("class_without_a_profile_keeps_the_hud_off", "ROGUE")(r"""
-- HudProfiles has no ROGUE entry: no profile, an inactive state, and nothing secret read on any path
check(FS.Hud.GetProfile() == nil, "a rogue resolves no profile")
local st = S()
check(st.active == false and st.next == nil and #st.row == 0 and #st.procs == 0, "the state is inactive and empty")
W.combat = true
fire("PLAYER_REGEN_DISABLED"); fire("PLAYER_TARGET_CHANGED"); fire("UNIT_AURA", "player"); fire("SPELLS_CHANGED")
check(tickframe() == nil, "no profile means no OnUpdate ticker")
check(S().active == false, "still inactive in combat")
W.secret = true
fire("PLAYER_TARGET_CHANGED"); fire("UNIT_AURA", SS)
check(S().active == false, "still inactive with every read secret")
""")

# The class slot rule: who owns the Gunsight DoT area (deck key 6). HudProfiles.lua is the one home of the
# rule; ConsoleKeys.lua (the key) and GunsightDots.lua (the scale) both call it, so they cannot disagree.
case("class_slot_truth_table", "ROGUE")(r"""
local CS = FS.HudProfiles.ClassSlot
check(type(CS) == "function", "FS.HudProfiles.ClassSlot exists")
local D, S = { a = {} }, {}
local rows = {
    -- profile, want, label
    { nil, nil, "nil" },
    { 5, nil, "a number" }, { "dots", nil, "a string" }, { true, nil, "a boolean" }, { function() end, nil, "a function" },
    { {}, nil, "an empty profile" },
    { { dots = {} }, nil, "empty dots, no seals" },
    { { dots = D }, "dots", "dots" },
    { { seals = S }, "seals", "seals alone" },
    { { seals = S, dots = {} }, "seals", "seals with empty dots" },
    { { seals = S, dots = D }, "dots", "dots plus seals stays dots" },
    { { seals = 5 }, nil, "a non table seals" },
    { { seals = 5, dots = {} }, nil, "a non table seals, empty dots" },
    { { seals = 5, dots = D }, "dots", "a non table seals beside real dots" },
    { { seals = "x", dots = D }, "dots", "a string seals beside real dots" },
    { { dots = 5, seals = S }, "seals", "non table dots beside seals" },
    { { dots = true }, nil, "non table dots alone" },
    { { dots = "x", seals = 5 }, nil, "both non table" },
}
for _, r in ipairs(rows) do
    check(CS(r[1]) == r[2], r[3] .. ": want " .. tostring(r[2]) .. ", got " .. tostring(CS(r[1])))
end
-- the shipped profiles
check(CS(FS.HudProfiles.WARLOCK) == "dots", "WARLOCK keeps the DoT tape")
check(CS(FS.HudProfiles.PRIEST) == "dots", "PRIEST keeps the DoT tape")
check(CS(FS.HudProfiles.PALADIN) == "seals", "PALADIN gets the seal chamber")
-- no write, no secret read: a profile is only ever indexed and walked with next
local before = 0
for _ in pairs(FS.HudProfiles.PALADIN) do before = before + 1 end
CS(FS.HudProfiles.PALADIN)
local after = 0
for _ in pairs(FS.HudProfiles.PALADIN) do after = after + 1 end
check(before == after, "the profile table was not touched")
""")

# Paladin Holy Strike / Judgement cooldown tracker. The two procs are `ready` rungs: lit while
# the spell is off cooldown, read through CooldownState (so the global cooldown never darkens
# one). Everything here runs in combat with secret cooldown timing, the 1.60.1 case.
case("paladin_ready_rungs_survive_the_gcd_and_go_dark_for_the_cooldown", "PALADIN")(r"""
local P = FS.Hud.Primitives
local HS, JD = NAME_ID["Holy Strike"], NAME_ID["Judgement"]
W.combat = true; W.cdTimingSecret = true
local function lit(key)
    for _, p in ipairs(S().procs) do if p.key == key then return p.active end end
end
at(0)
check(lit("hs") == true and lit("jd") == true, "both rungs lit when nothing is on cooldown")
-- the seal is unknown in combat (nothing cast, no readable aura), so the seal rule is skipped and
-- Judgement, listed before Holy Strike, is NEXT
check(nxt() == "jd" and S().next.glow == "gold", "NEXT is Judgement, gold while it is ready, got " .. tostring(nxt()) .. "/" .. tostring(S().next and S().next.glow))
-- another spell opens the global cooldown: isActive is true for Holy Strike during it only
cast("Smite"); at(0.5)
W.cd[HS] = { isActive = true }; W.cd[JD] = { isActive = true }
check(P.cooldownReady("hs") == true and lit("hs") == true, "the GCD does not darken the Holy Strike rung")
check(lit("jd") == true, "nor the Judgement rung")
check(nxt() == "jd" and S().next.glow == "gold", "NEXT stays Judgement through the GCD")
at(2); W.cd[HS] = { isActive = false }; W.cd[JD] = { isActive = false }
check(lit("hs") == true, "lit after the GCD")
-- Holy Strike itself (a rank id the dictionary does not list): dark for its 10 s cooldown
at(3); cast("Holy Strike", 679)
W.cd[HS] = { isActive = true }; W.cd[JD] = { isActive = true }
at(3.5)
check(lit("hs") == false, "Holy Strike goes dark when cast")
check(lit("jd") == true, "Judgement is not Holy Strike's cooldown: lit through Holy Strike's GCD")
check(nxt() == "jd", "Holy Strike on cooldown, Judgement ready: NEXT is Judgement, got " .. tostring(nxt()))
W.cd[JD] = { isActive = false }
at(6); check(lit("hs") == false, "still dark mid cooldown")
-- an own cast of another spell opens a GCD with isActive true for Holy Strike, but Holy Strike's own
-- 10 s window (last cast at 3) still running beats the GCD heuristic: still dark, not lit
cast("Smite"); at(6.5); W.cd[HS] = { isActive = true }
check(lit("hs") == false, "another cast's GCD does not relight Holy Strike inside its own 10 s")
at(12.9); check(lit("hs") == false, "cooldown timing: still dark at 12.9 s, before the 10 s are up")
at(13.2); W.cd[HS] = { isActive = false }
check(lit("hs") == true, "lit again after 10 s")
check(nxt() == "jd", "Judgement still leads Holy Strike, got " .. tostring(nxt()))
W.cd[JD] = { isActive = true }        -- Judgement down (outside the GCD window): Holy Strike is NEXT
check(lit("jd") == false and nxt() == "hs" and S().next.glow == "gold", "Holy Strike is NEXT and gold again, got " .. tostring(nxt()))
""")

# Judgement can only be cast on a hostile target, so its rung (needsTarget) shows only while the target is
# attackable: no target, a friendly one or a dead one hides it. The entry and its icon stay, so the rung
# fades out normally. Holy Strike has no such flag.
case("paladin_judgement_rung_needs_an_attackable_target", "PALADIN")(r"""
local P = FS.Hud.Primitives
local function entry(key)
    for _, p in ipairs(S().procs) do if p.key == key then return p end end
end
local function lit(key) return entry(key).active end
at(0)
check(lit("jd") == true and lit("hs") == true, "attackable target: both rungs lit")
W.targetExists = false
check(lit("jd") == false and P.procActive("jd") == false, "no target: Judgement is dark")
check(entry("jd").icon == 100000 + NAME_ID["Judgement"], "and the entry and its icon stay, so the rung fades")
check(lit("hs") == true, "Holy Strike is unaffected by having no target")
W.targetExists = true; W.canAttack = false
check(lit("jd") == false, "friendly target: Judgement is dark")
check(lit("hs") == true, "Holy Strike unaffected by a friendly target")
W.canAttack = true; W.targetDead = true
check(lit("jd") == false and lit("hs") == true, "dead target: Judgement dark, Holy Strike unaffected")
W.targetDead = false; W.targetGhost = true
check(lit("jd") == false, "enemy ghost: Judgement dark")
W.targetGhost = false
check(lit("jd") == true, "a live hostile target again: lit")
-- a ready answer is still required: on cooldown stays dark even with a target
W.combat = true; at(3); cast("Judgement"); W.cd[NAME_ID["Judgement"]] = { isActive = true }; at(3.5)
check(lit("jd") == false, "attackable target but on cooldown: dark")
""")

case("paladin_judgement_rung_stays_lit_when_the_target_answer_is_secret", "PALADIN")(r"""
local function lit(key)
    for _, p in ipairs(S().procs) do if p.key == key then return p.active end end
end
at(0)
W.canAttack = SB
check(lit("jd") == true, "a secret UnitCanAttack reads as attackable: still lit")
W.canAttack = true; W.targetExists = SB
check(lit("jd") == true, "a secret UnitExists reads as attackable: still lit")
""")

case("paladin_judgement_unreadable_cooldown_stays_nil_without_a_target", "PALADIN")(r"""
local P = FS.Hud.Primitives
at(0)
W.sec.cd = true
check(P.procActive("jd") == nil, "unreadable cooldown with a target: nil")
W.targetExists = false
check(P.procActive("jd") == nil, "unreadable cooldown and no target: still nil, not guessed dark")
""")

case("paladin_target_loss_pushes_the_judgement_flip", "PALADIN")(r"""
local last, n = nil, 0
FS.Hud.Subscribe(function(s) last = s; n = n + 1 end)
local function jd(s) for _, p in ipairs(s.procs) do if p.key == "jd" then return p.active end end end
check(n == 1 and jd(last) == true, "pushed at once, Judgement lit")
tick(0.25)
check(n == 1, "nothing changed: no push")
-- no PLAYER_TARGET_CHANGED here: the active flip alone must change the signature and reach the subscriber
W.targetExists = false
tick(0.25)
check(n == 2 and jd(last) == false, "losing the target pushes Judgement dark on the tick, n = " .. n)
W.targetExists = true
fire("PLAYER_TARGET_CHANGED")
tick(0.25)
check(jd(last) == true, "a new hostile target pushes Judgement lit again")
""")

case("paladin_next_needs_melee_range_unless_range_is_unknown", "PALADIN")(r"""
local HS, JD = NAME_ID["Holy Strike"], NAME_ID["Judgement"]
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 20) }       -- a seal is up
W.cd[JD] = { isActive = true, startTime = W.now - 1, duration = 10 }     -- Judgement is down, so Holy Strike is the candidate
W.range[HS] = false
check(nxt() == nil, "out of range (plain false): no NEXT for a melee spell, got " .. tostring(nxt()))
W.range[HS] = nil
check(nxt() == "hs" and S().next.glow == "gold", "unknown range (nil) still gives a gold NEXT, got " .. tostring(nxt()))
W.range[HS] = true
check(nxt() == "hs" and S().next.glow == "gold", "in range gives a gold NEXT")
""")

case("paladin_ready_rung_is_unlit_for_an_unknown_spell_and_nil_when_unreadable", "PALADIN")(r"""
local P = FS.Hud.Primitives
local function entry(key)
    for _, p in ipairs(S().procs) do if p.key == key then return p end end
end
check(P.procActive("hs") == true and entry("hs").icon == 100000 + NAME_ID["Holy Strike"], "known: ready, and the entry carries the spell icon")
forget("Holy Strike")
check(P.procActive("hs") == false, "an unknown spell is not ready")
check(entry("hs") == nil, "and has no rung at all (a level 5 paladin)")
check(entry("jd") ~= nil and entry("jd").active == true, "Judgement is unaffected")
W.auras.player = { sealAura("Seal of Righteousness", 20) }       -- a seal is up
fire("UNIT_AURA", "player")
check(nxt() == "jd", "no Holy Strike: Judgement is NEXT, got " .. tostring(nxt()))
W.cd[NAME_ID["Judgement"]] = { isActive = true, startTime = W.now - 1, duration = 10 }
check(nxt() == nil, "no Holy Strike and Judgement down: no NEXT")
W.cd[NAME_ID["Judgement"]] = nil
W.known["Holy Strike"] = true; fire("SPELLS_CHANGED")
W.sec.cd = true
check(P.procActive("hs") == nil and entry("hs").active == nil, "a secret cooldown reads nil, not lit and not dark")
check(nxt() == nil, "an unreadable cooldown never guesses a NEXT")
""")

case("paladin_profile_is_well_formed", "PALADIN")(r"""
local prof = FS.Hud.GetProfile()
check(prof, "profile loaded for the class")
local D, P = FS.HudSpells, FS.Hud.Primitives
for k, pr in pairs(prof.procs) do
    check(pr.ready and D[pr.ready] and type(D[pr.ready].cooldown) == "number", "proc " .. k .. " names a dictionary spell with a numeric cooldown")
    check(pr.side == "left" or pr.side == "right", "proc " .. k .. " has a side")
    check(type(pr.label) == "string", "proc " .. k .. " has a label")
end
check(prof.procs.hs.side == "left" and prof.procs.jd.side == "right", "Holy Strike left, Judgement right")
check(prof.procs.jd.needsTarget == true and prof.procs.hs.needsTarget == nil, "only Judgement needs a target")
check(#prof.rotation == 3, "three rotation rules: seal, Judgement, Holy Strike, got " .. #prof.rotation)
local r1, r2, r3 = prof.rotation[1], prof.rotation[2], prof.rotation[3]
check(r1.cast == "sor" and #r1.when == 1 and r1.when[1][1] == "sealMissing" and r1.when[1][2] == 5, "rule 1: Seal of Righteousness when the seal is missing or has 5 s left")
check(r2.cast == "jd" and r2.when[1][1] == "procActive" and r2.when[1][2] == "jd", "rule 2: Judgement, gated on it being ready (and, through procActive, on a target)")
check(r2.when[2][1] == "orUnknown" and r2.when[2][2][1] == "inRange" and r2.when[2][2][2] == "jd", "rule 2: and on range, unknown range allowed")
check(r3.cast == "hs", "rule 3: Holy Strike")
local w = r3.when
check(w[1][1] == "procActive" and w[1][2] == "hs", "gated on Holy Strike being ready")
check(w[2][1] == "orUnknown" and w[2][2][1] == "inRange" and w[2][2][2] == "hs", "and on melee range, unknown range allowed")
for _, rule in ipairs(prof.rotation) do
    check(D[rule.cast], "rotation names a spell missing from the dictionary: " .. rule.cast)
    for _, c in ipairs(rule.when) do
        local inner = (c[1] == "orUnknown" or c[1] == "not") and c[2] or c
        check(P[inner[1]], "unknown primitive " .. tostring(inner[1]))
    end
end
local sl = prof.seals
check(sl and sl.duration == 30, "seals: 30 s")
local want = { "sor", "sotc", "sofu", "soc", "sol", "sow", "soj" }
check(#sl.order == #want, "seals: seven in order")
for i, k in ipairs(want) do
    check(sl.order[i] == k, "seals order " .. i)
    check(D[k] and D[k].seal == true and D[k].self == true and D[k].apply == 30, "seal " .. k .. " is a self, seal, 30 s dictionary entry")
end
check(D.sor.ids and D.sor.ids[1] == 21084 and #D.sor.ids == 1 and D.sotc.ids and D.sotc.ids[1] == 21082 and #D.sotc.ids == 1, "SoR and SotC carry their verified ids")
for k, id in pairs({ sofu = 20163, soc = 20375, sol = 20165, soj = 20164 }) do
    check(D[k].ids and D[k].ids[1] == id, "seal " .. k .. " uses its published Forever spell ID")
end
check(D.sow.ids == nil, "Wisdom is above the level-30 beta cap and stays name-only")
check(#D.hs.ids == 4 and D.hs.ids[1] == 680 and D.hs.ids[2] == 1866 and D.hs.ids[3] == 678 and D.hs.ids[4] == 679,
    "Holy Strike fallback ranks cover levels 6 through 28")
check(D.sor.names[1] == "Seal of Righteousness" and D.sotc.names[1] == "Seal of the Crusader" and D.sofu.names[1] == "Seal of Fury"
    and D.soc.names[1] == "Seal of Command" and D.sol.names[1] == "Seal of Light" and D.sow.names[1] == "Seal of Wisdom"
    and D.soj.names[1] == "Seal of Justice", "seal names")
check(sl.judge.sotc == 40 and sl.judge.sol == 40 and sl.judge.sow == 40 and sl.judge.soj == 10, "judge seconds are data")
for k in pairs(sl.judge) do check(D[k] and D[k].seal, "judge names a seal: " .. k) end
check(type(prof.dotLabel) == "table" and prof.dotLabel.n == "Seal Chamber" and prof.dotLabel.d == "Active seal, drain timer and Judgement lane", "dotLabel is data")
check(#prof.row == 0 and next(prof.dots) == nil and #prof.selfBuffs == 0 and prof.resource == nil, "no row, dots, buffs or shards")
check(D.hs.cooldown == 10 and D.jd.cooldown == 10, "both are 10 s cooldowns")
check(D.hs.offGcd == nil and D.jd.offGcd == nil, "neither is marked off the global cooldown (unverified)")
""")

# Paladin seal ledger. state.seal is nil (unknown), false (no seal) or { key, id, expiresAt, duration,
# castAt }. Own seal casts run on UNIT_SPELLCAST_SUCCEEDED, before the self-spell early return.
case("seal_cast_sets_the_ledger_and_a_second_seal_replaces_it", "PALADIN")(r"""
W.combat = true      -- no aura reconcile: the ledger alone
at(0)
check(S().seal == nil, "nothing cast, nothing readable: the seal is unknown, got " .. tostring(S().seal))
cast("Seal of Righteousness")
local s = S().seal
check(type(s) == "table" and s.key == "sor" and s.id == 21084, "key and id, got " .. tostring(s and s.key) .. "/" .. tostring(s and s.id))
check(s.expiresAt == 1030 and s.duration == 30 and s.castAt == 1000, "30 s from the cast, got " .. tostring(s.expiresAt) .. "/" .. tostring(s.duration) .. "/" .. tostring(s.castAt))
at(10); cast("Seal of the Crusader")
s = S().seal
check(s.key == "sotc" and s.expiresAt == 1040 and s.castAt == 1010, "a second seal replaces the first, got " .. tostring(s.key) .. "/" .. tostring(s.expiresAt))
-- own casts report the rank id: SoR rank 1 is not in the dictionary and still maps back by name
at(12); cast("Seal of Righteousness", 20154)
check(S().seal.key == "sor" and S().seal.id == 20154 and S().seal.expiresAt == 1042, "a rank id maps by name")
-- a seal with a published fallback ID is still matched by its name
at(14); cast("Seal of Command")
check(S().seal.key == "soc" and S().seal.expiresAt == 1044, "a seal resolves by name, got " .. tostring(S().seal.key))
-- the returned table is a copy: a consumer cannot edit the ledger
S().seal.expiresAt = 0
check(S().seal.expiresAt == 1044, "state.seal is a copy of the ledger")
""")

case("seal_reads_false_once_it_has_expired", "PALADIN")(r"""
W.combat = true
at(0); cast("Seal of Righteousness")
at(29.9)
check(type(S().seal) == "table", "still up at 29.9 s")
at(30.1)
check(S().seal == false, "past expiresAt the seal reads false, got " .. tostring(S().seal))
at(31); cast("Seal of Righteousness")
check(type(S().seal) == "table" and S().seal.expiresAt == 1061, "recast after the expiry")
""")

case("seal_cast_is_not_a_cast_on_the_target_and_other_self_spells_still_are_not", "PALADIN")(r"""
local P = FS.Hud.Primitives
W.combat = true
at(0); cast("Seal of Righteousness")
check(P.freshTarget() == true and P.engagedFor(0) == false, "a seal is not an engagement")
cast("Inner Fire")
check(S().seal.key == "sor", "another self spell leaves the seal alone")
check(P.freshTarget() == true and P.engagedFor(0) == false, "and is still not a cast on the target")
cast("Judgement")
check(P.freshTarget() == false, "control: Judgement is a cast on the target")
""")

case("seal_reconcile_reads_the_player_aura_out_of_combat", "PALADIN")(r"""
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
local s = S().seal
check(type(s) == "table" and s.key == "sor" and s.id == 21084, "the aura sets the seal, got " .. tostring(s))
check(s.expiresAt == W.now + 20 and s.duration == 30 and s.castAt == W.now - 10, "timing from expirationTime and duration, got " .. tostring(s.expiresAt) .. "/" .. tostring(s.castAt))
-- a readable scan with no seal aura is a plain "no seal"
W.auras.player = { { name = "Demon Armor", spellId = 13787, expirationTime = W.now + 1000, duration = 1800 } }
fire("UNIT_AURA", "player")
check(S().seal == false, "a readable scan with no seal aura: false, got " .. tostring(S().seal))
W.auras.player = {}
fire("UNIT_AURA", "player")
check(S().seal == false, "an empty readable list: false")
-- matched by spell id when the name is secret
W.auras.player = { { name = SS, spellId = 21082, expirationTime = W.now + 8, duration = 30, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sotc" and S().seal.expiresAt == W.now + 8, "a secret name falls back to the id")
-- someone else's seal aura on us is not ours
local other = sealAura("Seal of Righteousness", 20); other.sourceUnit = "party1"
W.auras.player = { other }
fire("UNIT_AURA", "player")
check(S().seal == false, "an aura from another source is not our seal")
-- the reconcile corrects a ledger entry the aura disagrees with (a cast that missed the aura)
W.auras.player = { sealAura("Seal of Light", 12) }
fire("UNIT_AURA", "player")
check(S().seal.key == "sol" and S().seal.expiresAt == W.now + 12, "the aura wins over an older ledger entry")
""")

case("seal_reconcile_waits_for_readable_auras_and_catches_up_after_combat", "PALADIN")(r"""
at(0)
check(S().seal == false, "an out of combat read with no seal aura: false")
W.combat = true
W.auras.player = { sealAura("Seal of Righteousness", 20) }       -- applied in combat: unreadable, no event matters
check(S().seal == false, "in combat the aura is not read, the ledger stands")
W.combat = false; fire("PLAYER_REGEN_ENABLED")
check(S().seal and S().seal.key == "sor", "leaving combat reconciles on its own")
W.auras.player = {}
W.aurasSecret = true; fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "ShouldAurasBeSecret true: no read, the ledger stands")
W.aurasSecret = false
check(S().seal == false, "readable again: the dirty flag is still set, so it reconciles")
""")

case("seal_unreadable_scan_changes_nothing", "PALADIN")(r"""
at(0)
C_UnitAuras.GetAuraDataByIndex = function() error("boom") end      -- a throwing read
fire("UNIT_AURA", "player")
check(S().seal == nil, "an unreadable scan from unknown stays unknown, got " .. tostring(S().seal))
C_UnitAuras.GetAuraDataByIndex = function(unit, i) return W.auras[unit][i] end
cast("Seal of Righteousness")
at(5)
W.combat = true
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "combat: no read, the cast seal stands")
W.combat = false; W.aurasSecret = true
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "ShouldAurasBeSecret: no read, the cast seal stands")
W.aurasSecret = false
C_UnitAuras.GetAuraDataByIndex = function() error("boom") end
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "a throwing read changes nothing")
C_UnitAuras.GetAuraDataByIndex = function() return SN end          -- a secret entry
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "a secret aura entry changes nothing")
""")

case("seal_zero_value_scan_reads_as_an_empty_list", "PALADIN")(r"""
-- Parker's live recon: a buffed player reads fine; a buffless one may return ZERO values at index 1,
-- which for the seal (and only the seal) means 'no auras', so the seal rule can fire
at(0)
C_UnitAuras.GetAuraDataByIndex = function() end                    -- ZERO values, no throw
fire("UNIT_AURA", "player")
check(S().seal == false, "zero values at index 1 out of combat: no seal, got " .. tostring(S().seal))
check(nxt() == "sor", "and Seal of Righteousness fires, got " .. tostring(nxt()))
-- a cast seal that is gone (older than the aura lag window) is corrected by it
C_UnitAuras.GetAuraDataByIndex = function(unit, i) return W.auras[unit][i] end
cast("Seal of Righteousness")
at(5)
C_UnitAuras.GetAuraDataByIndex = function() end
fire("UNIT_AURA", "player")
check(S().seal == false, "an old cast seal with an empty scan: gone, got " .. tostring(S().seal))
-- the same zero values in combat are still not read at all
cast("Seal of Righteousness")
W.combat = true; fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "in combat the ledger stands")
""")

case("seal_fresh_cast_survives_a_scan_that_lags_the_aura", "PALADIN")(r"""
at(0)
cast("Seal of Righteousness")
W.auras.player = {}                         -- the aura is not listed yet (lag, or an unverified name)
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "a seal cast under a second ago is kept, got " .. tostring(S().seal))
at(0.9); fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "still kept at 0.9 s")
at(1.1); fire("UNIT_AURA", "player")
check(S().seal == false, "an older cast the scan cannot find is gone, got " .. tostring(S().seal))
-- the same rule for a name the dictionary does not know: a readable scan with only unknown buffs
cast("Seal of Light")
W.auras.player = { { name = "Mystery Seal", spellId = 99999, expirationTime = W.now + 30, duration = 30, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sol", "an unrecognised aura name does not wipe a fresh cast")
""")

case("seal_death_then_leaving_combat_rescans", "PALADIN")(r"""
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "up")
fire("PLAYER_DEAD")
check(S().seal == false, "death: false")
-- the seal aura is gone after the release; leaving combat rescans and agrees
W.auras.player = {}
fire("PLAYER_REGEN_ENABLED")
check(S().seal == false, "regen with the aura gone stays false, got " .. tostring(S().seal))
-- the aura survived the death (it is still listed): the regen rescan brings the seal back
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("PLAYER_DEAD")
check(S().seal == false, "death again: false")
fire("PLAYER_REGEN_ENABLED")
check(S().seal and S().seal.key == "sor", "regen with the aura still listed reads it again, got " .. tostring(S().seal))
""")

case("seal_reconcile_after_a_cast_keeps_the_entry_and_pushes_once", "PALADIN")(r"""
at(0)
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
tick(0.25)
local base = n
cast("Seal of Righteousness", 20154)        -- the rank id; the aura carries 21084
tick(0.25)
check(n == base + 1, "the cast pushes once, n = " .. n)
local s = S().seal
local castAt, exp = s.castAt, s.expiresAt
-- the cast's own UNIT_AURA: the aura expires 0.4 s off the ledger (server rounding)
local a = { name = "Seal of Righteousness", spellId = 21084, expirationTime = exp + 0.4, duration = 30, sourceUnit = "player" }
W.auras.player = { a }
fire("UNIT_AURA", "player"); tick(0.25)
s = S().seal
check(s.castAt == castAt and s.id == 20154 and s.expiresAt == exp, "an agreeing aura keeps the cast entry (castAt, id, expiry), got " .. tostring(s.castAt) .. "/" .. tostring(s.id) .. "/" .. tostring(s.expiresAt))
check(n == base + 1, "and the reconcile pushes nothing more, n = " .. n)
-- an aura that disagrees by more than a second wins, and the id can switch to the aura's
local t = W.now
a.expirationTime = t + 25
fire("UNIT_AURA", "player"); tick(0.25)
s = S().seal
check(s.expiresAt == t + 25 and s.id == 21084 and s.castAt == t - 5, "a disagreeing aura replaces the entry, got " .. tostring(s.expiresAt) .. "/" .. tostring(s.id))
-- a different seal key is never kept
cast("Seal of Light")
local e = S().seal.expiresAt
W.auras.player = { { name = "Seal of Righteousness", spellId = 21084, expirationTime = e + 0.2, duration = 30, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal.key == "sor" and S().seal.id == 21084, "the aura names another seal (expiry within a second): it wins, got " .. tostring(S().seal.key))
""")

case("seal_aura_with_a_secret_timing_is_never_compared", "PALADIN")(r"""
at(0)
W.auras.player = { { name = "Seal of Righteousness", spellId = 21084, expirationTime = SN, duration = SN, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal == nil, "a seal aura whose timing is secret: present but unknowable, got " .. tostring(S().seal))
check(FS.Hud.Primitives.sealMissing(5) == nil, "and sealMissing is nil, not a guess")
cast("Seal of Righteousness")
W.auras.player = { { name = "Seal of Righteousness", spellId = 21084, expirationTime = SN, duration = SN, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor" and S().seal.expiresAt == W.now + 30, "the cast's own timing is kept when it names the same seal")
-- a plain expiry with a secret duration: the dictionary length stands in for the duration only
W.auras.player = { { name = "Seal of Light", spellId = 20165, expirationTime = W.now + 15, duration = SN, sourceUnit = "player" } }
fire("UNIT_AURA", "player")
check(S().seal.key == "sol" and S().seal.expiresAt == W.now + 15 and S().seal.duration == 30, "secret duration: 30 s, plain expiry")
""")

case("seal_player_dead_is_false_and_entering_world_is_unknown", "PALADIN")(r"""
at(0)
check(evframe()._events.PLAYER_DEAD, "PLAYER_DEAD is registered")
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "reconciled from the aura")
fire("UNIT_AURA", "player")                  -- a reconcile is pending when the player dies
fire("PLAYER_DEAD")
check(S().seal == false, "death clears the seal even while the dying aura is still listed, got " .. tostring(S().seal))
fire("UNIT_AURA", "player")
check(S().seal and S().seal.key == "sor", "a later readable scan decides again")
W.combat = true
fire("PLAYER_ENTERING_WORLD")
check(S().seal == nil, "entering the world marks it unknown, got " .. tostring(S().seal))
W.combat = false; fire("PLAYER_REGEN_ENABLED")
check(S().seal and S().seal.key == "sor", "and the reconcile re-reads it (a loading screen strips no aura)")
-- a /reload loses the ledger: the seal is unknown until the reconcile reads it
fire("PLAYER_ENTERING_WORLD")
check(S().seal and S().seal.key == "sor", "entering the world out of combat re-reads at once")
""")

case("seal_change_pushes_and_the_clock_does_not", "PALADIN")(r"""
W.combat = true
at(0)
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
check(n == 1, "pushed at once")
tick(0.25)
check(n == 1, "nothing changed")
cast("Seal of Righteousness"); tick(0.25)
check(n == 2, "a seal cast pushes, n = " .. n)
at(5); tick(0.25); at(10); tick(0.25); at(15); tick(0.25); at(20); tick(0.25)
check(n == 2, "a running seal timer does not push each second, n = " .. n)
at(21); cast("Seal of the Crusader"); tick(0.25)
check(n == 3, "a different seal pushes (NEXT is unchanged), n = " .. n)
at(60); tick(0.25)
check(n == 4, "the expiry pushes once, n = " .. n)
at(70); tick(0.25)
check(n == 4, "and nothing after it, n = " .. n)
fire("PLAYER_DEAD"); tick(0.25)
check(n == 4, "death changes nothing (false stays false)")
""")

case("seal_cast_beats_a_pending_reconcile", "PALADIN")(r"""
at(0)
W.auras.player = {}
fire("UNIT_AURA", "player")                  -- a reconcile is pending and would read 'no seal'
cast("Seal of Righteousness")
check(S().seal and S().seal.key == "sor", "the cast is fresher than the pending reconcile, got " .. tostring(S().seal))
W.auras.player = { sealAura("Seal of Righteousness", 30) }
fire("UNIT_AURA", "player")                  -- the cast's own UNIT_AURA: the aura is there now
check(S().seal and S().seal.key == "sor" and S().seal.expiresAt == W.now + 30, "and the aura confirms it")
""")

case("seal_unknown_and_no_seal_are_different_signatures", "PALADIN")(r"""
W.combat = true
W.noMana[21084] = true          -- the seal rule is skipped either way, so NEXT is Judgement in both states
at(0)
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
check(S().seal == nil and nxt() == "jd", "unknown, NEXT is Judgement")
fire("PLAYER_DEAD"); tick(0.25)
check(S().seal == false and nxt() == "jd", "no seal, NEXT unchanged")
check(n == 2, "unknown to no seal still pushes, n = " .. n)
fire("PLAYER_ENTERING_WORLD"); tick(0.25)
check(S().seal == nil and n == 3, "and back to unknown pushes, n = " .. n)
""")

case("seal_cast_with_the_same_key_later_pushes_a_new_cast_time", "PALADIN")(r"""
W.combat = true
at(0); cast("Seal of Righteousness")
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
at(3); cast("Seal of Righteousness"); tick(0.25)
check(n == 2, "recasting the same seal refreshes castAt and pushes, n = " .. n)
""")

# Paladin Judgement ledger. state.judgeAt is the GetTime of our last own Judgement cast (nil before one);
# state.judged is the Judgement debuff on the CURRENT target: nil unknown, false none, else
# { key, appliedAt, expiresAt, duration }. Both come from plain own-cast numbers only. Judgement does not
# consume the seal, and a seal with no `seals.judge` entry (Righteousness) leaves a judgeAt but no entry.
case("judge_cast_records_judge_at_and_leaves_the_seal_alone", "PALADIN")(r"""
at(0)
check(S().judgeAt == nil, "no Judgement cast yet: nil, got " .. tostring(S().judgeAt))
cast("Seal of Righteousness")
local before = S().seal
at(3); cast("Judgement")
check(S().judgeAt == 1003, "judgeAt is the jd cast time, got " .. tostring(S().judgeAt))
local s = S().seal
check(s and s.key == "sor" and s.castAt == before.castAt and s.expiresAt == before.expiresAt, "Judgement does not consume or touch the seal")
check(S().judged == false, "Seal of Righteousness has no Judgement debuff entry, got " .. tostring(S().judged))
at(8); cast("Judgement", 20271)
check(S().judgeAt == 1008, "a later Judgement moves judgeAt, got " .. tostring(S().judgeAt))
check(FS.Hud.Primitives.sealMissing(5) == false, "the seal still has time left")
cast("Holy Strike")
check(S().judgeAt == 1008, "another spell leaves judgeAt alone")
""")

case("judge_cast_records_the_debuff_by_seal_with_its_duration", "PALADIN")(r"""
local want = { { "Seal of the Crusader", "sotc", 40 }, { "Seal of Light", "sol", 40 },
                { "Seal of Wisdom", "sow", 40 }, { "Seal of Justice", "soj", 10 } }
local base = 0
for _, w in ipairs(want) do
    at(base); cast(w[1])
    at(base + 2); cast("Judgement")
    local j = S().judged
    check(type(j) == "table" and j.key == w[2], w[2] .. ": entry keyed by the seal at cast time, got " .. tostring(j and j.key))
    check(j.appliedAt == 1000 + base + 2 and j.duration == w[3] and j.expiresAt == 1000 + base + 2 + w[3],
        w[2] .. ": appliedAt and expiresAt = appliedAt + " .. w[3] .. ", got " .. tostring(j.appliedAt) .. "/" .. tostring(j.expiresAt))
    local g = FS.Hud.GetJudgement()
    check(g.key == w[2] and g.remaining == w[3] and g.judgeAt == 1000 + base + 2, w[2] .. ": accessor, got " .. tostring(g.key) .. "/" .. tostring(g.remaining))
    at(base + 2 + w[3] - 0.5)
    check(FS.Hud.GetJudgement().remaining == 0.5 and FS.Hud.GetJudgement().key == w[2], w[2] .. ": half a second left")
    check(type(S().judged) == "table", w[2] .. ": still up just before the end")
    at(base + 2 + w[3])
    check(S().judged == false, w[2] .. ": gone at expiresAt, got " .. tostring(S().judged))
    g = FS.Hud.GetJudgement()
    check(g.remaining == 0 and g.key == nil, w[2] .. ": accessor reads none after the expiry")
    base = base + 100
end
-- the entry is a copy: editing state does not edit the ledger
at(base); cast("Seal of Light"); at(base + 1); cast("Judgement")
S().judged.expiresAt = 0
check(S().judged.expiresAt == 1000 + base + 41, "state.judged is a copy of the ledger entry")
-- a new Judgement under another seal replaces the entry
at(base + 2); cast("Seal of Justice"); at(base + 3); cast("Judgement")
check(S().judged.key == "soj" and S().judged.expiresAt == 1000 + base + 13, "a new Judgement replaces the entry")
""")

case("judge_cast_with_no_known_seal_records_judge_at_only", "PALADIN")(r"""
W.combat = true
at(0)
check(S().seal == nil, "the seal is unknown")
cast("Judgement")
check(S().judgeAt == 1000, "judgeAt is recorded, got " .. tostring(S().judgeAt))
check(S().judged == false, "no entry without a known seal, got " .. tostring(S().judged))
check(S().seal == nil, "and the unknown seal stays unknown")
-- no seal at all (a readable empty scan)
W.combat = false
fire("UNIT_AURA", "player")
check(S().seal == false, "a readable scan: no seal")
at(1); cast("Judgement")
check(S().judgeAt == 1001 and S().judged == false, "no seal: judgeAt only")
-- an expired seal reads false
at(5); cast("Seal of Light")
at(40); cast("Judgement")
check(S().judgeAt == 1040 and S().judged == false, "an expired seal records no entry, got " .. tostring(S().judged))
-- a Judgement with no target still stamps judgeAt
at(41); cast("Seal of Light"); W.targetExists = false; at(42); cast("Judgement")
check(S().judgeAt == 1042, "no target: judgeAt is still recorded")
W.targetExists = true
check(S().judged == false, "and no entry went anywhere")
""")

case("judge_entry_is_per_target", "PALADIN")(r"""
at(0)
cast("Seal of the Crusader"); at(1); cast("Judgement")          -- on Creature-A
check(S().judged and S().judged.key == "sotc", "A is judged")
retarget("Creature-B")
check(S().judged == false, "B does not inherit it, got " .. tostring(S().judged))
check(FS.Hud.GetJudgement().remaining == 0 and FS.Hud.GetJudgement().key == nil, "accessor: nothing on B")
at(2); cast("Seal of Justice"); at(3); cast("Judgement")        -- on Creature-B
check(S().judged.key == "soj" and S().judged.duration == 10, "B is judged under its own seal")
retarget("Creature-A")
check(S().judged and S().judged.key == "sotc" and S().judged.appliedAt == 1001, "back on A: its own entry, untouched by B, got " .. tostring(S().judged and S().judged.key))
check(FS.Hud.GetJudgement().key == "sotc" and FS.Hud.GetJudgement().remaining == 38, "accessor follows the target")
-- a retarget mid cast lands the debuff on the cast's target
W.combat = true
fire("UNIT_SPELLCAST_SENT", "player", "B", "g1", NAME_ID["Judgement"])
retarget("Creature-C")
at(4); fire("UNIT_SPELLCAST_SUCCEEDED", "player", "g1", NAME_ID["Judgement"])
check(S().judged == false, "C is not judged, got " .. tostring(S().judged))
retarget("Creature-A")
check(S().judged and S().judged.appliedAt == 1004, "the entry went to the target the cast was sent at")
-- a secret GUID: nowhere known to read, but a cast under it is readable until the next retarget
W.sec.guid = true
retarget("Creature-D")
check(S().judged == nil and FS.Hud.GetJudgement().remaining == nil, "secret GUID after a retarget: unknown")
at(5); cast("Judgement")
check(S().judged and S().judged.key == "soj", "a cast under a secret GUID is readable on the current target")
retarget("Creature-E")
check(S().judged == nil, "and unknown again after the next retarget")
""")

case("judge_at_survives_death_and_the_world_and_the_debuff_ledger_does_not", "PALADIN")(r"""
at(0)
cast("Seal of Light"); at(1); cast("Judgement")
check(S().judgeAt == 1001 and S().judged and S().judged.key == "sol", "judged")
fire("PLAYER_DEAD")
check(S().judgeAt == 1001, "death keeps judgeAt (cooldowns persist), got " .. tostring(S().judgeAt))
check(S().judged and S().judged.key == "sol", "the mob's debuff is a target ledger entry: like a DoT, death leaves it")
at(2); cast("Seal of Light"); at(3); cast("Judgement")
check(S().judgeAt == 1003, "judgeAt moves with the next cast")
fire("PLAYER_ENTERING_WORLD")
check(S().judgeAt == 1003, "entering the world keeps judgeAt (a loading screen does not reset a cooldown), got " .. tostring(S().judgeAt))
check(S().judged == nil, "the target ledger is dropped and the debuff is unknown, got " .. tostring(S().judged))
check(FS.Hud.GetJudgement().judgeAt == 1003 and FS.Hud.GetJudgement().remaining == nil, "accessor agrees")
""")

case("judged_is_unknown_until_a_judgement_is_seen_after_a_reset", "PALADIN")(r"""
at(0)
check(S().judged == nil, "a fresh start: nothing known about the target, got " .. tostring(S().judged))
local g = FS.Hud.GetJudgement()
check(g.remaining == nil and g.key == nil and g.judgeAt == nil, "accessor: unknown")
-- the out of combat reconcile (a retarget runs it) writes no judged entry and must not turn unknown into none
retarget("Creature-B")
check(S().judged == nil, "a reconcile does not make it known, got " .. tostring(S().judged))
cast("Judgement")                                  -- no seal known: judgeAt only, but a Judgement is now seen
check(S().judged == false and FS.Hud.GetJudgement().remaining == 0, "after a Judgement is seen, no entry means none, got " .. tostring(S().judged))
cast("Seal of Light"); at(1); cast("Judgement")
check(S().judged and S().judged.key == "sol", "and a recorded one reads as up")
fire("PLAYER_ENTERING_WORLD")
check(S().judged == nil and FS.Hud.GetJudgement().remaining == nil, "a loading screen makes it unknown again, got " .. tostring(S().judged))
retarget("Creature-A")
check(S().judged == nil, "also on another target after the reset")
""")

case("judged_stays_unknown_after_a_reset_until_a_judgement_not_any_cast", "PALADIN")(r"""
at(0)
fire("PLAYER_ENTERING_WORLD")
check(S().judged == nil, "unknown after the reset")
cast("Seal of Light")
check(S().judged == nil, "a seal cast does not make it known, got " .. tostring(S().judged))
at(1); cast("Holy Strike")
check(S().judged == nil, "nor does another own spell, got " .. tostring(S().judged))
check(FS.Hud.GetJudgement().remaining == nil, "accessor: still unknown")
at(2); cast("Judgement")
check(type(S().judged) == "table", "only a Judgement does")
""")

case("judged_seen_survives_death", "PALADIN")(r"""
at(0)
cast("Seal of Light"); at(1); cast("Judgement")
fire("PLAYER_DEAD")
check(type(S().judged) == "table", "the debuff on the mob survives death, got " .. tostring(S().judged))
retarget("Creature-B")
check(S().judged == false, "a mob with no Judgement reads none, not unknown, after death, got " .. tostring(S().judged))
check(FS.Hud.GetJudgement().remaining == 0, "accessor agrees")
""")

case("judge_changes_push_and_the_clock_does_not", "PALADIN")(r"""
W.combat = true
at(0)
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
cast("Seal of Justice"); tick(0.25)
local base = n
at(2); cast("Judgement"); tick(0.25)
check(n == base + 1, "a Judgement cast pushes (judgeAt and the entry), n = " .. n)
at(3); tick(0.25); at(5); tick(0.25); at(8); tick(0.25)
check(n == base + 1, "a running Judgement timer does not push each second, n = " .. n)
at(12); tick(0.25)
check(n == base + 2, "the debuff expiring pushes once (judgeAt unchanged), n = " .. n)
at(20); tick(0.25)
check(n == base + 2, "and nothing after it, n = " .. n)
at(21); cast("Judgement"); tick(0.25)
check(n == base + 3, "a second Judgement pushes again, n = " .. n)
fire("PLAYER_DEAD")
check(S().judgeAt == 1021, "death leaves judgeAt alone")
""")

case("judge_cast_with_no_debuff_entry_still_pushes_on_judge_at", "PALADIN")(r"""
W.combat = true
at(0); cast("Seal of Righteousness")
local n = 0
FS.Hud.Subscribe(function() n = n + 1 end)
tick(0.25)
local base = n
at(2); cast("Judgement"); tick(0.25)
check(n == base + 1, "Righteousness has no entry: judgeAt alone pushes, n = " .. n)
at(12); cast("Judgement"); tick(0.25)
check(n == base + 2, "a second Judgement moves judgeAt and pushes, n = " .. n)
""")

case("judge_state_is_absent_for_a_class_without_seals", "PRIEST")(r"""
check(S().judgeAt == nil and S().judged == nil, "no judgement fields for a priest")
local g = FS.Hud.GetJudgement()
check(type(g) == "table" and g.judgeAt == nil and g.remaining == nil and g.key == nil, "empty accessor")
""")

case("get_seals_lists_the_known_seals_in_profile_order", "PALADIN")(r"""
local seals = FS.Hud.GetSeals()
local want = { "sor", "sotc", "sofu", "soc", "sol", "sow", "soj" }
check(#seals == 7, "all seven known, got " .. #seals)
for i, k in ipairs(want) do check(seals[i].key == k, "order " .. i .. ", got " .. tostring(seals[i].key)) end
check(seals[1].name == "Seal of Righteousness" and seals[1].id == 21084, "name and id of SoR")
check(seals[3].name == "Seal of Fury" and seals[3].id == NAME_ID["Seal of Fury"], "a seal name resolves through the client before its fallback ID")
forget("Seal of the Crusader"); forget("Seal of Light")
seals = FS.Hud.GetSeals()
for _, e in ipairs(seals) do check(type(e.key) == "string" and type(e.name) == "string" and type(e.id) == "number", "plain data") end
check(#seals == 5 and seals[1].key == "sor" and seals[2].key == "sofu" and seals[3].key == "soc" and seals[4].key == "sow" and seals[5].key == "soj", "unknown seals are filtered, order kept")
for _, k in ipairs({ "Seal of Righteousness", "Seal of Fury", "Seal of Command", "Seal of Wisdom", "Seal of Justice" }) do W.known[k] = nil end
fire("SPELLS_CHANGED")
check(#FS.Hud.GetSeals() == 0, "none known")
""")

case("get_seals_is_empty_for_a_class_without_seals", "PRIEST")(r"""
check(type(FS.Hud.GetSeals()) == "table" and #FS.Hud.GetSeals() == 0, "a priest has no seals")
check(S().seal == nil, "and no seal field value")
""")

case("seal_missing_primitive_true_false_nil", "PALADIN")(r"""
local P = FS.Hud.Primitives
W.combat = true
at(0)
check(P.sealMissing(5) == nil, "unknown seal: nil")
cast("Seal of Righteousness")
at(10)
check(P.sealMissing(5) == false, "20 s left: not missing")
at(24.9)
check(P.sealMissing(5) == false, "5.1 s left: not missing")
at(25)
check(P.sealMissing(5) == true, "exactly 5 s left: missing (at or below)")
at(29)
check(P.sealMissing(5) == true, "1 s left: missing")
check(P.sealMissing(0) == false, "with a 0 s window it is not missing until it expires")
at(31)
check(P.sealMissing(5) == true and P.sealMissing(0) == true, "expired: missing")
check(P.sealMissing("five") == nil and P.sealMissing(nil) == nil, "a non-number window is nil")
check(FS.Hud.Eval({ "sealMissing", 5 }) == true and FS.Hud.Eval({ "not", { "sealMissing", 5 } }) == false, "Eval reaches it")
fire("PLAYER_ENTERING_WORLD")
check(P.sealMissing(5) == nil, "unknown again")
fire("PLAYER_DEAD")
check(P.sealMissing(5) == true, "no seal at all: missing")
""")

case("seal_secrets_are_never_touched", "PALADIN")(r"""
local P = FS.Hud.Primitives
at(0); cast("Seal of Righteousness")
W.secret = true
fire("PLAYER_TARGET_CHANGED")
fire("UNIT_AURA", SS)
fire("UNIT_AURA", "player")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", SS, SN)
fire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, 21084)
tick(0.25)
check(S().seal and S().seal.key == "sor", "a secret spell id never sets a seal and a secret read never clears one")
check(P.sealMissing(5) == false, "the ledger answers from our own plain numbers")
W.secret = false
check(#FS.Hud.GetSeals() > 0, "GetSeals after a secret spell")
""")


# The real PALADIN rotation, first true rule wins: seal missing -> Seal of Righteousness, then
# Judgement (off the GCD, so it leads), then Holy Strike. Deleting any rule fails one of these.
case("paladin_rotation_no_seal_casts_the_seal_plain_cyan", "PALADIN")(r"""
at(0)
check(nxt() == "sor", "a readable scan with no seal aura: Seal of Righteousness first, got " .. tostring(nxt()))
check(S().seal == false, "the reconcile set 'no seal'")
check(S().next.glow == nil, "the seal rule is not tied to a proc: plain cyan, got " .. tostring(S().next.glow))
check(S().next.icon == 100000 + 21084, "and carries the spell icon")
-- the seal rule beats a ready Judgement and a ready Holy Strike
check(S().procs[1].active == true and S().procs[2].active == true, "Holy Strike and Judgement are both ready")
-- Seal of Righteousness unaffordable: the rule is skipped (implicit mana check)
W.noMana[21084] = true
check(nxt() == "jd", "no mana for the seal: Judgement, got " .. tostring(nxt()))
W.noMana[21084] = nil; W.usable[21084] = false
check(nxt() == "jd", "an unusable seal is skipped, got " .. tostring(nxt()))
""")

case("paladin_rotation_seal_up_and_judgement_ready_casts_judgement_gold", "PALADIN")(r"""
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
check(nxt() == "jd", "seal up, Judgement ready, target: Judgement, got " .. tostring(nxt()))
check(S().next.glow == "gold", "gold through the procActive link, got " .. tostring(S().next.glow))
W.range[NAME_ID["Judgement"]] = false
check(nxt() == "hs", "Judgement out of range (plain false): skipped, Holy Strike, got " .. tostring(nxt()))
W.range[NAME_ID["Judgement"]] = nil
check(nxt() == "jd", "an unknown range never hides it")
W.targetExists = false
check(nxt() == nil, "no target: no suggestion")
""")

case("paladin_rotation_judgement_down_holy_strike_ready", "PALADIN")(r"""
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
W.cd[NAME_ID["Judgement"]] = { isActive = true, startTime = W.now - 1, duration = 10 }
check(nxt() == "hs" and S().next.glow == "gold", "Judgement on cooldown: Holy Strike, gold, got " .. tostring(nxt()))
W.cd[NAME_ID["Holy Strike"]] = { isActive = true, startTime = W.now - 1, duration = 10 }
check(nxt() == nil, "both on cooldown: nothing, got " .. tostring(nxt()))
W.cd[NAME_ID["Judgement"]] = nil
check(nxt() == "jd", "Judgement is back")
""")

case("paladin_rotation_a_lapsing_seal_is_refreshed_at_five_seconds", "PALADIN")(r"""
at(0)
W.auras.player = { sealAura("Seal of Righteousness", 6) }
fire("UNIT_AURA", "player")
check(nxt() == "jd", "6 s left: Judgement, got " .. tostring(nxt()))
at(1.5)
check(nxt() == "sor", "4.5 s left: refresh the seal before it drops, got " .. tostring(nxt()))
at(2)
check(nxt() == "sor", "exactly 4 s left, got " .. tostring(nxt()))
""")

case("paladin_rotation_unknown_seal_skips_to_judgement", "PALADIN")(r"""
at(0)
W.combat = true      -- no aura read, nothing cast: the seal is unknown
check(S().seal == nil, "unknown")
check(nxt() == "jd" and S().next.glow == "gold", "the nil primitive skips the seal rule, never guessed, got " .. tostring(nxt()))
W.cd[NAME_ID["Judgement"]] = { isActive = true }
at(5)
check(nxt() == "hs", "and on to Holy Strike, got " .. tostring(nxt()))
""")

case("paladin_rotation_at_low_levels_skips_unknown_spells", "PALADIN")(r"""
at(0)
-- a level 3 paladin: Seal of Righteousness only
forget("Judgement"); forget("Holy Strike")
check(nxt() == "sor", "no seal: cast it, got " .. tostring(nxt()))
W.auras.player = { sealAura("Seal of Righteousness", 20) }
fire("UNIT_AURA", "player")
check(nxt() == nil, "seal up, no Judgement and no Holy Strike: nothing to suggest, got " .. tostring(nxt()))
check(#S().procs == 0, "and no rungs")
-- a level 5 paladin: Judgement, no Holy Strike
W.known["Judgement"] = true; fire("SPELLS_CHANGED")
check(nxt() == "jd", "level 5: Judgement, got " .. tostring(nxt()))
W.cd[NAME_ID["Judgement"]] = { isActive = true, startTime = W.now - 1, duration = 10 }
check(nxt() == nil, "level 5, Judgement down: nothing, got " .. tostring(nxt()))
-- a level 1 paladin with no seal spell known at all
forget("Seal of Righteousness")
W.auras.player = {}
fire("UNIT_AURA", "player")
check(nxt() == nil, "no seal spell: the rule is skipped, got " .. tostring(nxt()))
""")

case("priest_profile_is_well_formed", "PRIEST")(STRUCTURE)
case("warlock_profile_is_well_formed", "WARLOCK")(STRUCTURE)


def run_case(name: str, cls: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(f'resetWorld("{cls}"); FS = {{}}')
    lua.execute("FS.LogDegradeOnce = function(k, m) __errors[#__errors + 1] = k .. ': ' .. tostring(m) end")
    loader = lua.eval("function(src, name) local fn = assert(loadstring(src, '@' .. name)); return fn('forever-stuwave', FS) end")
    for fname in FILES:
        path = ADDON / fname
        if not path.exists():
            return f"{fname} is missing"
        try:
            loader(path.read_text(encoding="utf-8"), fname)
            if fname == "Modules/CombatHud/HudProfiles.lua":
                lua.execute(TEST_PROFILES)
        except LuaError as err:
            return f"{fname} failed to load: {err}"
    try:
        lua.execute('fire("PLAYER_LOGIN")')
        lua.execute(body)
        lua.execute('check(#__touches == 0, "a secret was touched: " .. tostring(__touches[1]))')
        lua.execute('check(#__errors == 0, "an error escaped: " .. tostring(__errors[1]))')
    except LuaError as err:
        return str(err)
    return None


def main() -> int:
    failures = 0
    for name, cls, body in CASES:
        error = run_case(name, cls, body)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    total = len(CASES)
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
