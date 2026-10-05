#!/usr/bin/env python3
"""Runs the real Diagnostics.lua headless against a mock WoW API, for the `/fsmo` and `/fsrecon class` probes.

`/fsrecon class` is the class spell and aura recon a tester runs once so a class's real spell ids,
form data and aura shapes are known before class features are built. Its properties pinned here:
it runs for PALADIN (the full candidate table) and WARLOCK (a small table plus the real HudProfile
keys) and for a class with no table, secret values print "secret", throwing and missing APIs never
error, aura reads are skipped in combat, the chat output has one fixed shape, list sizes are
capped, and the result is handed to /fsbug through GetClassRecon (fsbug-harness.py pins the report
side). The routing of the subcommand lives in PanelSkins.lua; the real dispatcher is loaded and driven.

`/fsmo` is the mouseover-cast probe Parker runs in game. The properties worth pinning are the
safety ones: the toggle registers and unregisters UPDATE_MOUSEOVER_UNIT, one compact line is
printed per CHANGE of unit or frame (never per event), a secret name or flag prints the word
"secret" without ever being compared or concatenated, the watch turns itself off after 120s (and
a stale timer from an earlier session never kills a later one), and every API throwing or being
absent is survived.

Secret sentinels raise on indexing, calling, concatenation, arithmetic, `<`, `<=`, `#` and
tostring(), so a code path doing any of those with one fails the check instead of passing
silently. They CANNOT trap a boolean test (`if v then`) or a comparison with `nil` or another
non-table value (`v == nil`, `v == "x"`): Lua never calls a metamethod for those, so the harness
cannot see them.

The mock is NOT the real client. Run:

    python3 tools/diagnostics-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverSynthwave"
DIAG_SRC = (ADDON / "Diagnostics.lua").read_text(encoding="utf-8")
HUD_SPELLS_SRC = (ADDON / "HudSpells.lua").read_text(encoding="utf-8")
HUD_PROFILES_SRC = (ADDON / "HudProfiles.lua").read_text(encoding="utf-8")
PANELSKINS_SRC = (ADDON / "PanelSkins.lua").read_text(encoding="utf-8")

MOCK = r"""
realType = type

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

-- print() raises on a sentinel, so a secret that reaches chat fails the case.
__printed = {}
function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
function Lines()
    local out = {}
    for i, l in ipairs(__printed) do
        out[i] = (l:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""))
    end
    return out
end

-- Timers fire by elapsed time, so a stale 120s timer is distinguishable from a fresh one.
__clock = 0
__timers = {}
C_Timer = { After = function(sec, fn) __timers[#__timers + 1] = { at = __clock + sec, fn = fn } end }
function Advance(dt)
    __clock = __clock + dt
    local due, rest = {}, {}
    for _, t in ipairs(__timers) do
        if t.at <= __clock then due[#due + 1] = t else rest[#rest + 1] = t end
    end
    __timers = rest
    for _, t in ipairs(due) do t.fn() end
end

SlashCmdList = {}
__all = {}
local FM = {}
local FMT = {}
FMT.__index = function(self, k)
    local m = FM[k]
    if m then return m end
    return function() return nil end
end
local function newFrame(kind, name)
    local f = setmetatable({ _kind = kind, _name = name, _events = {}, _scripts = {} }, FMT)
    __all[#__all + 1] = f
    return f
end
function CreateFrame(kind, name) return newFrame(kind, name) end
function FM.SetScript(s, k, fn) s._scripts[k] = fn end
function FM.RegisterEvent(s, e) s._events[e] = true end
function FM.UnregisterEvent(s, e) s._events[e] = nil end
function FM.GetName(s) return s._name end

function Fire(event, ...)
    for _, f in ipairs(__all) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
function Watching()
    for _, f in ipairs(__all) do
        if f._events.UPDATE_MOUSEOVER_UNIT then return true end
    end
    return false
end

-- Mouseover world the cases mutate.
M = { exists = true, name = "Thrall", friend = true, frame = "PlayerFrame", cvar = "1", click = "NONE" }
THROW = {}
local function guard(key, fn)
    return function(...)
        if THROW[key] then error("boom: " .. key) end
        return fn(...)
    end
end
function UnitExists(u) return guard("UnitExists", function() return M.exists end)(u) end
function UnitName(u) return guard("UnitName", function() return M.name end)(u) end
function UnitGUID(u) return guard("UnitGUID", function() return M.guid end)(u) end
function UnitIsFriend(a, b) return guard("UnitIsFriend", function() return M.friend end)(a, b) end
function GetCVar(n) return guard("GetCVar", function() return M.cvar end)(n) end
function GetModifiedClick(n) return guard("GetModifiedClick", function() return M.click end)(n) end
function MouseFrame()
    if M.frame == nil then return nil end
    return { GetName = function()
        if THROW.GetName then error("boom: GetName") end
        return M.frame ~= false and M.frame or nil
    end }
end
function GetMouseFoci() return guard("GetMouseFoci", function() return { MouseFrame() } end)() end

function LoadDiag()
    FS = { Theme = {} }
    -- Theme.lua's FS.IsSecret: false when the client has no issecretvalue, decided once at load.
    local hasIsSecretValue = type(issecretvalue) == "function"
    FS.IsSecret = function(v)
        if THROW.IsSecret then error("boom: IsSecret") end
        return hasIsSecretValue and issecretvalue(v)
    end
    local chunk = assert(loadstring(DIAG_SRC, "@Diagnostics.lua"))
    chunk("ForeverSynthwave", FS)
    return FS
end
function On() SlashCmdList.FSMO("") end
function Hover() Fire("UPDATE_MOUSEOVER_UNIT") end
"""

# The class world for /fsrecon class. Appended to MOCK so it shares its `guard` and `sentinel`
# locals. ClassWorld() installs the APIs; every API reads CW at call time and can be made to throw
# through THROW[key]. Mouseover cases never call it, so UnitExists stays the mouseover one for them.
CLASS_MOCK = r"""
CW = nil
__auraCalls = 0
function ClassWorld(over)
    CW = {
        class = "Paladin", token = "PALADIN", level = 12, combat = false, now = 5000,
        tabs = { { "Holy", "i1", 0 }, { "Protection", "i2", 0 }, { "Retribution", "i3", 5 } },
        talentInfo = { {}, {}, {
            { talentID = 101, name = "Improved Blessing of Might", rank = 5, maxRank = 5 },
            { talentID = 102, name = "Benediction", rank = 0, maxRank = 5 },
            { talentID = 103, name = "Vindication", rank = 3, maxRank = 5 },
        } },
        forms = {},
        spells = {
            ["Seal of Righteousness"] = 21084, ["Seal of the Crusader"] = 21082, ["Judgement"] = 20271,
            ["Holy Light"] = 635, ["Devotion Aura"] = 465, ["Blessing of Might"] = 19740,
        },
        known = { [21084] = true, [20271] = true, [635] = true, [465] = true, [19740] = true },
        secrecy = { [21084] = 0, [21082] = 1, [20271] = 2, [635] = 0, [465] = 0, [19740] = 0 },
        exists = { target = true, party1 = true },
        auras = {},
    }
    CW.auras["player|HELPFUL"] = {
        { name = "Seal of Righteousness", spellId = 21084, duration = 30, expirationTime = 5028.5, sourceUnit = "player" },
        { name = "Devotion Aura", spellId = 465, duration = 0, expirationTime = 0, sourceUnit = "player" },
    }
    CW.auras["target|HARMFUL|PLAYER"] = {
        { name = "Judgement of Light", spellId = 20185, duration = 20, expirationTime = 5010 },
    }
    CW.auras["party1|HELPFUL|PLAYER"] = {
        { name = "Blessing of Might", spellId = 19740, duration = 300, expirationTime = 5300 },
    }
    for k, v in pairs(over or {}) do CW[k] = v end
    __auraCalls = 0
    THROW = {}
    __printed = {}
    ForeverSynthwaveDB = {}
    UnitClass = guard("UnitClass", function() return CW.class, CW.token, 2 end)
    UnitLevel = guard("UnitLevel", function() return CW.level end)
    InCombatLockdown = guard("InCombatLockdown", function() return CW.combat end)
    GetTime = guard("GetTime", function() return CW.now end)
    GetNumTalentTabs = guard("GetNumTalentTabs", function() return #CW.tabs end)
    GetTalentTabInfo = guard("GetTalentTabInfo", function(i)
        local t = CW.tabs[i]
        if t then return t[1], t[2], t[3], "bg" end
    end)
    date = guard("date", function() return CW.date or "2026-10-03 10:00:00" end)
    GetNumSpecializations = guard("GetNumSpecializations", function() return #CW.tabs end)
    __talentCalls, __nodeArgs, __treeArgs, __cfgArgs, __entryArgs, __defArgs = 0, {}, {}, {}, {}, {}
    C_SpecializationInfo = {
        GetTalentInfo = guard("GetTalentInfo", function(q)
            assert(realType(q) == "table" and q.isInspect == false and q.isPet == false, "query shape")
            __talentCalls = __talentCalls + 1
            local tab = CW.talentInfo[q.specializationIndex]
            return tab and tab[q.talentIndex]
        end),
    }
    C_ClassTalents, C_Traits = nil, nil
    local T = CW.traits
    if T then
        C_ClassTalents = { GetActiveConfigID = guard("GetActiveConfigID", function() return T.cfg end) }
        -- Every id an API receives is recorded, so a test can prove what never reached it.
        local function rec(list, id) list.n = (list.n or 0) + 1; list[#list + 1] = id; return id end
        C_Traits = {
            GetConfigInfo = guard("GetConfigInfo", function(cfg)
                rec(__cfgArgs, cfg)
                return T.cfg == cfg and { treeIDs = T.trees } or nil
            end),
            GetTreeNodes = guard("GetTreeNodes", function(tree)
                rec(__treeArgs, tree)
                return T.treeNodes and T.treeNodes[tree] or T.nodes
            end),
            GetNodeInfo = guard("GetNodeInfo", function(cfg, node) rec(__nodeArgs, node) return T.node[node] end),
            GetEntryInfo = guard("GetEntryInfo", function(cfg, entry) rec(__entryArgs, entry) return T.entry[entry] end),
            GetDefinitionInfo = guard("GetDefinitionInfo", function(def) rec(__defArgs, def) return T.def[def] end),
        }
    end
    GetNumShapeshiftForms = guard("GetNumShapeshiftForms", function() return #CW.forms end)
    GetShapeshiftFormInfo = guard("GetShapeshiftFormInfo", function(i)
        local f = CW.forms[i]
        if f then return unpack(f, 1, 5) end
    end)
    C_Spell = {
        GetSpellInfo = guard("GetSpellInfo", function(name)
            local id = CW.spells[name]
            if id then return { name = name, spellID = id, iconID = 1 } end
        end),
        GetSpellAuraSecrecy = guard("GetSpellAuraSecrecy", function(id) return CW.secrecy[id] end),
    }
    IsPlayerSpell = guard("IsPlayerSpell", function(id) return CW.known[id] == true end)
    C_UnitAuras = {
        GetAuraDataByIndex = guard("GetAuraDataByIndex", function(unit, i, filter)
            __auraCalls = __auraCalls + 1
            if CW.auraZero then return end
            local list = CW.auras[unit .. "|" .. filter]
            return list and list[i]
        end),
    }
    UnitExists = guard("UnitExists", function(u)
        local v = CW.exists[u]
        if v == nil then return false end
        return v
    end)
    return CW
end

function LoadHud(FS)
    local a = assert(loadstring(HUD_SPELLS_SRC, "@HudSpells.lua"))
    a("ForeverSynthwave", FS)
    local b = assert(loadstring(HUD_PROFILES_SRC, "@HudProfiles.lua"))
    b("ForeverSynthwave", FS)
end

-- Runs the recon and returns FS, the data and the printed lines (colour codes removed).
function RunClass(over, noHud)
    ClassWorld(over)
    local FS = LoadDiag()
    if not noHud then LoadHud(FS) end
    FS.Diagnostics.RunClassRecon()
    return FS, FS.Diagnostics.GetClassRecon(), Lines()
end

function HasSentinel(v, seen)
    if SENT[v] then return true end
    if realType(v) ~= "table" then return false end
    seen = seen or {}
    if seen[v] then return false end
    seen[v] = true
    for k, x in pairs(v) do
        if HasSentinel(k, seen) or HasSentinel(x, seen) then return true end
    end
    return false
end

-- A trait-based client: ranked nodes 1001 and 1003 of one tree, 1002 unspent.
TRAITS = {
    cfg = 77, trees = { 500 }, nodes = { 1001, 1002, 1003 },
    node = {
        [1001] = { activeRank = 2, maxRanks = 5, activeEntry = { entryID = 9001 } },
        [1002] = { activeRank = 0, maxRanks = 1 },
        [1003] = { activeRank = 1, maxRanks = 1, activeEntry = { entryID = 9003 } },
    },
    entry = { [9001] = { definitionID = 8001 }, [9003] = { definitionID = 8003 } },
    def = { [8001] = { spellID = 20271 }, [8003] = { spellID = 635 } },
}

function Join(lines) return table.concat(lines, "\n") end
function Has(s, sub) return s:find(sub, 1, true) ~= nil end
function Spell(data, name)
    for _, e in ipairs(data.spells) do if e.name == name then return e end end
end
"""
MOCK = MOCK + CLASS_MOCK

CASES: list[tuple[str, str]] = []


def case(name: str, body: str):
    CASES.append((name, body))


case("slash_registered", """
    LoadDiag()
    assert(SlashCmdList.FSMO and SLASH_FSMO1 == "/fsmo")
    assert(not Watching(), "nothing watches at load")
""")

case("toggle_on_then_off", """
    LoadDiag()
    On()
    assert(Watching(), "on registers UPDATE_MOUSEOVER_UNIT")
    On()
    assert(not Watching(), "second call unregisters")
    On()
    assert(Watching(), "third call is on again")
""")

case("toggle_prints_state_lines", """
    LoadDiag()
    On()
    local l = Lines()
    assert(#l == 1, #l)
    assert(l[1] == "synthwave://mouseover  on  enableMouseoverCast=1  MOUSEOVERCAST=NONE  (auto-off 120s)", l[1])
    On()
    l = Lines()
    assert(l[2] == "synthwave://mouseover  off", l[2])
""")

case("event_prints_one_compact_line", """
    LoadDiag()
    On()
    Hover()
    local l = Lines()
    assert(#l == 2, #l)
    assert(l[2] == "synthwave://mouseover  exists=true name=Thrall friend=true frame=PlayerFrame", l[2])
""")

case("no_event_while_off", """
    LoadDiag()
    Hover()
    On(); On()
    local n = #Lines()
    Hover()
    assert(#Lines() == n, "an off watch prints nothing")
""")

case("anon_frame_and_no_unit", """
    LoadDiag()
    M.exists, M.name, M.friend, M.frame = false, nil, nil, false
    On(); Hover()
    local l = Lines()
    assert(l[2] == "synthwave://mouseover  exists=false name=nil friend=nil frame=anon", l[2])
""")

case("no_frame_under_mouse", """
    LoadDiag()
    M.frame = nil
    On(); Hover()
    assert(Lines()[2]:find("frame=none", 1, true), Lines()[2])
""")

case("falls_back_to_getmousefocus", """
    LoadDiag()
    GetMouseFoci = nil
    function GetMouseFocus() return MouseFrame() end
    On(); Hover()
    assert(Lines()[2]:find("frame=PlayerFrame", 1, true), Lines()[2])
""")

case("secret_name_prints_secret_without_compare", """
    LoadDiag()
    M.name = SS
    On(); Hover()
    local l = Lines()
    assert(l[2] == "synthwave://mouseover  exists=true name=secret friend=true frame=PlayerFrame", l[2])
""")

case("secret_exists_and_friend_print_secret", """
    LoadDiag()
    M.exists, M.friend = SB, SB
    On(); Hover()
    assert(Lines()[2] == "synthwave://mouseover  exists=secret name=Thrall friend=secret frame=PlayerFrame", Lines()[2])
""")

case("secret_cvar_and_click_print_secret", """
    LoadDiag()
    M.cvar, M.click = SS, SS
    On()
    assert(Lines()[1] == "synthwave://mouseover  on  enableMouseoverCast=secret  MOUSEOVERCAST=secret  (auto-off 120s)", Lines()[1])
""")

case("secret_guid_is_not_compared", """
    LoadDiag()
    M.guid = SS
    On(); Hover(); Hover()
    assert(#Lines() == 2, "same secret-guid unit stays throttled")
""")

case("throttle_same_unit_same_frame_prints_once", """
    LoadDiag()
    On()
    for i = 1, 10 do Hover() end
    assert(#Lines() == 2, #Lines())
""")

case("throttle_secret_name_stays_throttled", """
    LoadDiag()
    M.name = SS
    On()
    for i = 1, 5 do Hover() end
    assert(#Lines() == 2, #Lines())
""")

case("throttle_prints_on_unit_change", """
    LoadDiag()
    On(); Hover(); Hover()
    M.name = "Jaina"
    Hover(); Hover()
    local l = Lines()
    assert(#l == 3 and l[3]:find("name=Jaina", 1, true), table.concat(l, "|"))
""")

case("throttle_prints_on_guid_change_same_name", """
    LoadDiag()
    M.guid = "Creature-1"
    On(); Hover(); Hover()
    M.guid = "Creature-2"
    Hover()
    assert(#Lines() == 3, #Lines())
""")

case("throttle_prints_on_frame_change", """
    LoadDiag()
    On(); Hover()
    M.frame = "TargetFrame"
    Hover(); Hover()
    local l = Lines()
    assert(#l == 3 and l[3]:find("frame=TargetFrame", 1, true), table.concat(l, "|"))
""")

case("throttle_resets_when_toggled_again", """
    LoadDiag()
    On(); Hover(); On(); On(); Hover()
    local n = 0
    for _, l in ipairs(Lines()) do if l:find("exists=", 1, true) then n = n + 1 end end
    assert(n == 2, n)
""")

case("auto_off_after_120s", """
    LoadDiag()
    On()
    Advance(119)
    assert(Watching(), "still on at 119s")
    Advance(1)
    assert(not Watching(), "off at 120s")
    local l = Lines()
    assert(l[#l] == "synthwave://mouseover  off  (120s timeout)", l[#l])
    local n = #l
    Hover()
    assert(#Lines() == n, "no output after auto-off")
""")

case("auto_off_does_not_fire_after_manual_off", """
    LoadDiag()
    On(); On()
    local n = #Lines()
    Advance(500)
    assert(#Lines() == n, "a stale timer prints nothing")
""")

case("stale_timer_does_not_kill_a_later_session", """
    LoadDiag()
    On()
    Advance(100)
    On()              -- off
    On()              -- on again at t=100, timer due at 220
    Advance(20)       -- t=120: the FIRST session's timer is due now
    assert(Watching(), "first session's timer must be ignored")
    Advance(99)       -- t=219
    assert(Watching())
    Advance(1)        -- t=220
    assert(not Watching(), "second session ends on its own clock")
""")

case("throwing_apis_do_not_error", """
    for _, k in ipairs({ "UnitExists", "UnitName", "UnitGUID", "UnitIsFriend", "GetMouseFoci", "GetCVar", "GetModifiedClick", "GetName", "IsSecret" }) do
        LoadDiag()
        THROW = { [k] = true }
        __printed = {}
        local ok, err = pcall(function() On(); Hover(); On() end)
        assert(ok, k .. ": " .. tostring(err))
        THROW = {}
    end
""")

case("everything_throwing_at_once", """
    LoadDiag()
    THROW = { UnitExists = true, UnitName = true, UnitGUID = true, UnitIsFriend = true, GetMouseFoci = true,
              GetCVar = true, GetModifiedClick = true, GetName = true, IsSecret = true }
    On(); Hover(); Hover()
    local l = Lines()
    assert(#l == 2, table.concat(l, "|"))
    assert(l[1] == "synthwave://mouseover  on  enableMouseoverCast=error  MOUSEOVERCAST=error  (auto-off 120s)", l[1])
    assert(l[2] == "synthwave://mouseover  exists=error name=error friend=error frame=error", l[2])
    On()
    assert(not Watching())
""")

case("absent_apis_do_not_error", """
    LoadDiag()
    UnitExists, UnitName, UnitGUID, UnitIsFriend, GetMouseFoci, GetMouseFocus, GetCVar, GetModifiedClick =
        nil, nil, nil, nil, nil, nil, nil, nil
    local ok, err = pcall(function() On(); Hover() end)
    assert(ok, tostring(err))
    local l = Lines()
    assert(l[1] == "synthwave://mouseover  on  enableMouseoverCast=n/a  MOUSEOVERCAST=n/a  (auto-off 120s)", l[1])
    assert(l[2] == "synthwave://mouseover  exists=n/a name=n/a friend=n/a frame=n/a", l[2])
""")

# FS.IsSecret is false when the client has no issecretvalue (Theme.lua), so every read is plain data.
case("absent_issecretvalue_reads_plain_data", """
    issecretvalue = nil
    LoadDiag()
    local ok, err = pcall(function() On(); Hover() end)
    assert(ok, tostring(err))
    local l = Lines()
    assert(l[2] == "synthwave://mouseover  exists=true name=Thrall friend=true frame=PlayerFrame", l[2])
""")

case("no_timer_available", """
    LoadDiag()
    C_Timer = nil
    On()
    local l = Lines()
    assert(l[1] == "synthwave://mouseover  on  enableMouseoverCast=1  MOUSEOVERCAST=NONE  (no auto-off timer)", l[1])
    Hover()
    assert(#Lines() == 2)
    On()
    assert(not Watching())
""")

case("secret_frame_name_prints_secret", """
    LoadDiag()
    M.frame = SS
    On(); Hover(); Hover()
    local l = Lines()
    assert(#l == 2, #l)
    assert(l[2] == "synthwave://mouseover  exists=true name=Thrall friend=true frame=secret", l[2])
""")


# ---------------------------------------------------------------------------
# /fsrecon class
# ---------------------------------------------------------------------------

case("class_paladin_chat_shape", """
    local _, data, l = RunClass()
    local P = "synthwave://class  "
    local want = {
        P .. "class=PALADIN level=12 spec=n/a combat=false",
        P .. "talents  GetTalentTabInfo=ok C_SpecializationInfo=unavailable GetSpecialization=unavailable  Holy=0 Protection=0 Retribution=5",
        P .. "ranks  ok via C_SpecializationInfo.GetTalentInfo  2  Improved Blessing of Might=5/5; Vindication=3/5",
        P .. "forms=0",
        P .. "spells  38 candidates, 6 resolved, 5 known  info=C_Spell.GetSpellInfo secrecy=C_Spell.GetSpellAuraSecrecy",
        P .. "seals  Seal of Righteousness=21084 known s=0; Seal of the Crusader=21082 unknown s=1; Seal of Fury=none; Seal of Command=none; Seal of Justice=none; Seal of Light=none; Seal of Wisdom=none",
        P .. "judgement  Judgement=20271 known s=2; Judgment=none",
        P .. "strike  Holy Strike=none",
        P .. "auras  Devotion Aura=465 known s=0; Retribution Aura=none; Concentration Aura=none; Shadow Resistance Aura=none; Frost Resistance Aura=none; Fire Resistance Aura=none",
        P .. "blessings  Blessing of Might=19740 known s=0; Blessing of Wisdom=none; Blessing of Kings=none; Blessing of Protection=none; Blessing of Salvation=none; Blessing of Light=none; Blessing of Sanctuary=none; Greater Blessing of Might=none; Greater Blessing of Wisdom=none; Greater Blessing of Kings=none; Greater Blessing of Protection=none; Greater Blessing of Salvation=none; Greater Blessing of Light=none; Greater Blessing of Sanctuary=none",
        P .. "other  Purify=none; Cleanse=none; Consecration=none; Hammer of Justice=none; Lay on Hands=none; Divine Protection=none; Holy Light=635 known s=0; Flash of Light=none",
        P .. "hud  PALADIN profile keys=0  ",       -- the real PALADIN profile has no row, dots, channels or self buffs
        P .. "buffs  2  Seal of Righteousness id=21084 dur=30 left=28.5 src=player dispel=nil; Devotion Aura id=465 dur=0 left=none src=player dispel=nil",
        P .. "target debuffs (mine)  1  Judgement of Light id=20185 dur=20",
        P .. "party buffs (mine)  party1: Blessing of Might id=19740; party2: absent; party3: absent; party4: absent",
        P .. "saved to recon.class, /fsbug includes it",
    }
    for i, w in ipairs(want) do assert(l[i] == w, "line " .. i .. ":\\n  got  " .. tostring(l[i]) .. "\\n  want " .. w) end
    assert(#l == #want, "extra lines: " .. #l)
""")

case("class_paladin_data", """
    local _, d = RunClass()
    assert(d.token == "PALADIN" and d.class == "Paladin" and d.level == 12 and d.inCombat == false)
    assert(#d.spells == 38, #d.spells)
    local sr = Spell(d, "Seal of Righteousness")
    assert(sr.id == 21084 and sr.known == true and sr.secrecy == 0 and sr.group == "seals")
    assert(sr.secrecyName == "NeverSecret", "the enum number is stored with its decoded name")
    local cr = Spell(d, "Seal of the Crusader")
    assert(cr.id == 21082 and cr.known == false and cr.secrecy == 1 and cr.secrecyName == "AlwaysSecret")
    assert(Spell(d, "Judgement").secrecyName == "ContextuallySecret")
    assert(Spell(d, "Seal of Fury").id == "none" and Spell(d, "Seal of Fury").known == nil)
    assert(Spell(d, "Judgement").id == 20271 and Spell(d, "Judgment").id == "none")
    assert(Spell(d, "Holy Strike") and Spell(d, "Greater Blessing of Sanctuary") and Spell(d, "Lay on Hands"))
    assert(d.spellApi.info == "C_Spell.GetSpellInfo" and d.spellApi.secrecy == "C_Spell.GetSpellAuraSecrecy")
    assert(d.talents.tabs[3].name == "Retribution" and d.talents.tabs[3].points == 5 and #d.talents.tabs == 3)
    assert(d.talents.api.GetTalentTabInfo == "ok" and d.talents.api.GetSpecialization == "unavailable")
    local rk = d.talents.ranks
    assert(rk.status == "ok" and rk.source == "C_SpecializationInfo.GetTalentInfo" and #rk.list == 2 and not rk.capped)
    assert(rk.list[1].name == "Improved Blessing of Might" and rk.list[1].id == 101 and rk.list[1].rank == 5
        and rk.list[1].maxRank == 5 and rk.list[1].tab == 3, "rank 0 talents are left out")
    assert(rk.list[2].id == 103 and rk.list[2].rank == 3)
    assert(d.forms.count == 0 and #d.forms.list == 0)
    assert(d.hud.profile == true and d.hud.token == "PALADIN" and #d.hud.keys == 0, "the real PALADIN profile lists no HUD spell keys")
    assert(d.buffs.status == "ok" and d.buffs.count == 2 and d.buffs.list[1].left == 28.5)
    assert(d.buffs.list[2].left == "none" and d.buffs.list[2].dispelName == nil)
    assert(d.debuffs.status == "ok" and d.debuffs.list[1].spellId == 20185 and d.debuffs.list[1].duration == 20)
    assert(d.party.party1.list[1].spellId == 19740 and d.party.party2.status == "absent")
    assert(not HasSentinel(d))
""")

case("class_data_is_stored_stamped_and_marked_for_the_bug_report", """
    local FS = LoadDiag()
    assert(type(FS.Diagnostics.RunClassRecon) == "function" and FS.Diagnostics.GetClassRecon() == nil)
    FS.Diagnostics.MarkClassReconReported()    -- nothing recorded yet: harmless
    ClassWorld()
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(ForeverSynthwaveDB.recon.class == d, "stored where the other recon probes store")
    assert(d.taken == "2026-10-03 10:00:00" and d.reported == nil)
    FS.Diagnostics.MarkClassReconReported()
    assert(d.reported == true and ForeverSynthwaveDB.recon.class.reported == true)
    ClassWorld({ level = 13, date = "2026-10-03 11:30:00" })
    FS.Diagnostics.RunClassRecon()
    local d2 = FS.Diagnostics.GetClassRecon()
    assert(d2 ~= d and d2.level == 13 and ForeverSynthwaveDB.recon.class == d2, "a rerun replaces, never accumulates")
    assert(d2.reported == nil and d2.taken == "2026-10-03 11:30:00", "a rerun is fresh and unreported")
    -- the stamp is plain: a missing or throwing date is "unavailable", not an error
    for _, how in ipairs({ "missing", "throw" }) do
        ClassWorld()
        if how == "missing" then date = nil else THROW = { date = true } end
        FS.Diagnostics.RunClassRecon()
        assert(FS.Diagnostics.GetClassRecon().taken == "unavailable", how)
    end
    -- a run kept only in SavedVariables (a new session) can still be marked
    ForeverSynthwaveDB = { recon = { class = { taken = "x" } } }
    local fresh = LoadDiag()
    fresh.Diagnostics.MarkClassReconReported()
    assert(ForeverSynthwaveDB.recon.class.reported == true)
""")

case("class_warlock_runs_with_its_own_table_and_the_real_hud_keys", """
    local FS, d, l = RunClass({
        class = "Warlock", token = "WARLOCK",
        spells = { Corruption = 172, ["Shadow Bolt"] = 686, ["Life Tap"] = 1454, ["Demon Armor"] = 706 },
        known = { [172] = true, [686] = true, [1454] = true, [706] = true },
        secrecy = { [172] = 0, [686] = 0, [1454] = 0, [706] = 0 },
    })
    assert(d.token == "WARLOCK")
    for _, e in ipairs(d.spells) do
        assert(not e.name:find("Seal") and not e.name:find("Blessing"), "no paladin spells for a warlock: " .. e.name)
    end
    assert(#d.spells == 8, "the warlock table has eight names: " .. #d.spells)
    assert(Spell(d, "Corruption").id == 172 and Spell(d, "Corruption").known == true)
    assert(d.hud.profile == true and #d.hud.keys > 3 and #d.hud.keys <= 40, #d.hud.keys)
    local byKey = {}
    for _, e in ipairs(d.hud.keys) do byKey[e.key] = e end
    assert(byKey.corruption.name == "Corruption" and byKey.corruption.id == 172 and byKey.corruption.known == true)
    assert(byKey.corruption.dictId == 25311, "the dictionary's own first id is shown beside the live one")
    assert(byKey.shadow_bolt.id == 686 and byKey.immolate.id == "none")
    assert(byKey.demon_armor.name == "Demon Armor")
    local text = Join(l)
    assert(Has(text, "class=WARLOCK level=12"))
    assert(Has(text, "hud  WARLOCK profile keys="), text)
    assert(Has(text, "corruption=172 known"))
    assert(d.buffs.status == "ok" and #d.forms.list == 0, "the generic sections run for any class")
""")

case("class_unknown_class_has_no_candidates_but_runs_the_generic_sections", """
    local _, d, l = RunClass({ class = "Mage", token = "MAGE" })
    assert(#d.spells == 0)
    assert(d.talents.tabs[3].points == 5 and d.forms.count == 0 and d.buffs.status == "ok")
    assert(d.hud.profile == false)
    assert(Has(Join(l), "spells  0 candidates"), Join(l))
""")

case("class_talent_apis_are_all_probed_and_both_tab_layouts_read", """
    -- Retail tab layout: id, name, description, icon, points. Plus both spec APIs.
    ClassWorld()
    local FS = LoadDiag()
    GetTalentTabInfo = function(i)
        local t = CW.tabs[i]
        if t then return 100 + i, t[1], "desc", "icon", t[3] end
    end
    C_SpecializationInfo.GetSpecialization = function() return 3 end
    C_SpecializationInfo.GetSpecializationInfo = function(i) return 70, "Retribution", "desc", "icon", "DAMAGER", 1, i * 2 end
    GetSpecialization = function() return 2 end
    GetSpecializationInfo = function(i) return 66, "Protection" end
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.talents.tabs[3].name == "Retribution" and d.talents.tabs[3].points == 5, d.talents.tabs[3].name)
    assert(d.talents.api.C_SpecializationInfo == "ok" and d.talents.api.GetSpecialization == "ok")
    assert(d.talents.specIndex.C_SpecializationInfo == 3 and d.talents.specIndex.GetSpecialization == 2)
    assert(d.spec == "Retribution", tostring(d.spec))
    assert(Has(Join(Lines()), "spec=Retribution"))
    -- This client has no GetTalentTabInfo at all: names and points come from GetSpecializationInfo
    -- (specId, name, description, icon, role, primaryStat, pointsSpent).
    GetTalentTabInfo = nil
    FS.Diagnostics.RunClassRecon()
    d = FS.Diagnostics.GetClassRecon()
    assert(d.talents.api.GetTalentTabInfo == "unavailable" and d.talents.tabSource == "C_SpecializationInfo.GetSpecializationInfo")
    assert(#d.talents.tabs == 3 and d.talents.tabs[3].name == "Retribution" and d.talents.tabs[3].points == 6)
""")

case("class_talent_ranks_fall_back_to_traits_when_the_spec_api_has_nothing", """
    for _, how in ipairs({ "absent", "empty" }) do
        local FS = LoadDiag()
        ClassWorld({ traits = TRAITS })
        if how == "absent" then C_SpecializationInfo = nil else CW.talentInfo = {} end
        FS.Diagnostics.RunClassRecon()
        local rk = FS.Diagnostics.GetClassRecon().talents.ranks
        assert(rk.status == "ok" and rk.source == "C_Traits (C_ClassTalents.GetActiveConfigID)" and #rk.list == 2, how)
        assert(rk.list[1].node == 1001 and rk.list[1].rank == 2 and rk.list[1].maxRank == 5 and rk.list[1].spellId == 20271)
        assert(rk.list[2].node == 1003 and rk.list[2].spellId == 635, "an unspent node is left out")
        assert(Has(Join(Lines()), "ranks  ok via C_Traits (C_ClassTalents.GetActiveConfigID)  2  20271=2/5; 635=1/1"), Join(Lines()))
    end
    -- nothing verifiable: a plain "unavailable" with the reason
    local FS = LoadDiag()
    ClassWorld()
    C_SpecializationInfo = nil
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "unavailable" and rk.reason == "GetTalentInfo=unavailable traits=unavailable" and #rk.list == 0, rk.reason)
    assert(Has(Join(Lines()), "ranks  unavailable  GetTalentInfo=unavailable traits=unavailable"))
""")

case("class_traits_a_secret_or_missing_id_never_reaches_the_next_api", """
    -- every level of the trait walk: a secret (or absent) id is not handed on
    local FS = LoadDiag()
    ClassWorld({ talentInfo = {}, traits = {
        cfg = 77, trees = { SN, 500 }, nodes = { SN, 1001, 1002, 1003, 1004, 1005 },
        node = {
            [1001] = { activeRank = 2, maxRanks = 5, activeEntry = { entryID = SN } },
            [1002] = { activeRank = 0, maxRanks = 1 },
            [1003] = { activeRank = 1, maxRanks = 1, activeEntry = { entryID = 9003 } },
            [1004] = { activeRank = 1, maxRanks = 1 },
            [1005] = { activeRank = 1, maxRanks = 1, activeEntry = { entryID = 9005 } },
        },
        entry = { [9003] = { definitionID = SN }, [9005] = { definitionID = 8005 } },
        def = { [8005] = { spellID = 635 } },
    } })
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "ok" and #rk.list == 4, rk.status .. " " .. #rk.list)
    assert(rk.skipped == 2, "the secret tree id and the secret node id are counted, not skipped silently: " .. tostring(rk.skipped))
    assert(__cfgArgs.n == 1 and __cfgArgs[1] == 77)
    assert(__treeArgs.n == 1 and __treeArgs[1] == 500, "a secret tree id reached GetTreeNodes: " .. tostring(__treeArgs.n))
    assert(__nodeArgs.n == 5 and __nodeArgs[1] == 1001, "a secret node id reached GetNodeInfo: " .. tostring(__nodeArgs.n))
    assert(__entryArgs.n == 2 and __entryArgs[1] == 9003 and __entryArgs[2] == 9005,
        "a secret or missing entry id reached GetEntryInfo: " .. tostring(__entryArgs.n))
    assert(__defArgs.n == 1 and __defArgs[1] == 8005, "a secret definition id reached GetDefinitionInfo: " .. tostring(__defArgs.n))
    assert(rk.list[1].node == 1001 and rk.list[1].spellId == nil, "no entry id, no spell")
    assert(rk.list[2].node == 1003 and rk.list[2].spellId == nil, "no definition id, no spell")
    assert(rk.list[3].node == 1004 and rk.list[3].spellId == nil)
    assert(rk.list[4].node == 1005 and rk.list[4].spellId == 635, "plain ids still resolve")
""")

case("class_traits_an_unreadable_tree_is_counted_and_the_reason_says_why", """
    local FS = LoadDiag()
    local function world(trees, treeNodes)
        ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = trees, treeNodes = treeNodes, nodes = TRAITS.nodes,
            node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
    end
    local function run()
        FS.Diagnostics.RunClassRecon()
        return FS.Diagnostics.GetClassRecon().talents.ranks
    end
    -- a secret tree id and a secret GetTreeNodes table are unreadable trees, not empty ones
    world({ SN, 500 }, { [500] = ST })
    local rk = run()
    assert(rk.status == "unavailable" and rk.reason == "GetTalentInfo=empty traits=secret" and rk.skipped == 2,
        tostring(rk.reason) .. " " .. tostring(rk.skipped))
    assert(__treeArgs.n == 1 and __treeArgs[1] == 500 and __nodeArgs.n == nil, "a secret id reached an API")
    assert(Has(Join(Lines()), "ranks  unavailable  GetTalentInfo=empty traits=secret"), Join(Lines()))
    assert(not HasSentinel(FS.Diagnostics.GetClassRecon()))
    -- GetTreeNodes throwing is an error state, kept (it used to be lost and read as empty)
    world({ 500 })
    THROW.GetTreeNodes = true
    rk = run()
    assert(rk.reason == "GetTalentInfo=empty traits=error" and rk.skipped == 1, tostring(rk.reason) .. " " .. tostring(rk.skipped))
    -- a readable tree still reads, and the count says what was missed
    world({ SN, 500 })
    rk = run()
    assert(rk.status == "ok" and #rk.list == 2 and rk.skipped == 1, rk.status .. " " .. tostring(rk.skipped))
    assert(Has(Join(Lines()), "ranks  ok via C_Traits (C_ClassTalents.GetActiveConfigID)  2 (1 unreadable)  "), Join(Lines()))
    -- a tree that plainly answers nothing is empty, not unreadable
    world({ 500 }, { [500] = {} })
    rk = run()
    assert(rk.reason == "GetTalentInfo=empty traits=empty" and rk.skipped == nil, tostring(rk.reason))
""")

case("class_traits_a_plain_string_node_id_never_becomes_the_status", """
    local FS = LoadDiag()
    local function run(nodes)
        ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = nodes, node = TRAITS.node,
            entry = TRAITS.entry, def = TRAITS.def } })
        FS.Diagnostics.RunClassRecon()
        return FS.Diagnostics.GetClassRecon().talents.ranks
    end
    local rk = run({ "banana" })
    assert(rk.reason == "GetTalentInfo=empty traits=empty" and rk.skipped == nil, tostring(rk.reason))
    assert(__nodeArgs.n == nil, "a string id reached GetNodeInfo")
    rk = run({ "banana", SN })
    assert(rk.reason == "GetTalentInfo=empty traits=secret" and rk.skipped == 1, tostring(rk.reason) .. " " .. tostring(rk.skipped))
""")

case("class_traits_a_secret_config_id_stops_the_walk", """
    for _, bad in ipairs({ "secret", "absent" }) do
        local FS = LoadDiag()
        ClassWorld({ talentInfo = {}, traits = { cfg = bad == "secret" and SN or nil, trees = { 500 }, nodes = { 1001 },
            node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
        FS.Diagnostics.RunClassRecon()
        local rk = FS.Diagnostics.GetClassRecon().talents.ranks
        assert(__cfgArgs.n == nil and __treeArgs.n == nil and __nodeArgs.n == nil, bad .. ": the walk went on")
        assert(rk.status == "unavailable" and #rk.list == 0, bad .. " " .. tostring(rk.status))
        assert(rk.reason == "GetTalentInfo=empty traits=" .. (bad == "secret" and "secret" or "empty"), rk.reason)
    end
""")

case("class_traits_a_secret_tree_id_list_is_secret_not_empty", """
    -- GetConfigInfo answers with a secret treeIDs table: that is "secret" (and counted), never "empty"
    local FS = LoadDiag()
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = ST, nodes = { 1001 },
        node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
    FS.Diagnostics.RunClassRecon()
    local data = FS.Diagnostics.GetClassRecon()
    local rk = data.talents.ranks
    assert(__cfgArgs.n == 1 and __treeArgs.n == nil and __nodeArgs.n == nil, "the walk went on past a secret tree list")
    assert(rk.status == "unavailable" and #rk.list == 0, tostring(rk.status))
    assert(rk.reason == "GetTalentInfo=empty traits=secret", tostring(rk.reason))
    assert(rk.skipped == 1, "the unreadable tree list is counted: " .. tostring(rk.skipped))
    assert(not HasSentinel(data))
    -- a tree list that is plainly missing or not a table is still empty
    for _, plain in ipairs({ "none", "banana", 5 }) do
        ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = plain ~= "none" and plain or nil, nodes = { 1001 },
            node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
        FS.Diagnostics.RunClassRecon()
        rk = FS.Diagnostics.GetClassRecon().talents.ranks
        assert(rk.reason == "GetTalentInfo=empty traits=empty" and rk.skipped == nil, tostring(plain) .. " " .. tostring(rk.reason))
    end
    -- a readable list still walks, and a skipped count stays off a clean walk
    ClassWorld({ talentInfo = {}, traits = TRAITS })
    FS.Diagnostics.RunClassRecon()
    rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "ok" and rk.skipped == nil, tostring(rk.status))
""")

case("class_traits_a_plain_non_number_config_id_is_not_secret", """
    -- only a real secret is "secret"; a plain string (even one spelled like a marker), a boolean or a
    -- table is an answer the walk cannot use ("unavailable"), and nothing at all is "empty"
    local FS = LoadDiag()
    for n, case in ipairs({
        { "banana", "unavailable" }, { "secret", "unavailable" }, { "error", "unavailable" },
        { true, "unavailable" }, { {}, "unavailable" }, { 0/0, "unavailable" }, { SN, "secret" },
    }) do
        ClassWorld({ talentInfo = {}, traits = { cfg = case[1], trees = { 500 }, nodes = { 1001 },
            node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
        FS.Diagnostics.RunClassRecon()
        local data = FS.Diagnostics.GetClassRecon()
        local rk = data.talents.ranks
        assert(__cfgArgs.n == nil and __treeArgs.n == nil and __nodeArgs.n == nil, "case " .. n .. ": the walk went on")
        assert(rk.reason == "GetTalentInfo=empty traits=" .. case[2], "case " .. n .. " " .. tostring(rk.reason))
        assert(not HasSentinel(data))
    end
""")

case("class_traits_caps_hold", """
    -- more trees than the tree cap, and more nodes than the node cap
    local FS = LoadDiag()
    local treeNodes = {}
    for i = 1, 5 do treeNodes[i] = {} end
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 1, 2, 3, 4, 5 }, treeNodes = treeNodes, nodes = {},
        node = {}, entry = {}, def = {} } })
    FS.Diagnostics.RunClassRecon()
    assert(__treeArgs.n == 3, "tree cap: " .. tostring(__treeArgs.n))
    local nodes, info = {}, {}
    for i = 1, 450 do nodes[i] = i; info[i] = { activeRank = 0, maxRanks = 1 } end
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = nodes, node = info, entry = {}, def = {} } })
    FS.Diagnostics.RunClassRecon()
    assert(__nodeArgs.n == 400, "node cap: " .. tostring(__nodeArgs.n))
    -- more ranked nodes than the 60 entry cap: the list stops at 60 and says so
    local ranked, rinfo = {}, {}
    for i = 1, 100 do ranked[i] = i; rinfo[i] = { activeRank = 1, maxRanks = 1 } end
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = ranked, node = rinfo, entry = {}, def = {} } })
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(#rk.list == 60 and rk.capped == true and rk.status == "ok", #rk.list)
    assert(__nodeArgs.n == 61, "the scan stops at the first ranked node past the cap: " .. tostring(__nodeArgs.n))
    assert(Has(Join(Lines()), "(capped)"))
""")

case("class_traits_lists_are_read_with_rawget_never_an_index", """
    -- a list with a hole whose __index raises: an index would throw, rawget just sees nothing there
    local function trapped(a, b)
        local list = { a, 0, b }
        list[2] = nil
        return setmetatable(list, { __index = function() error("indexed a list") end })
    end
    local FS = LoadDiag()
    ClassWorld({ talentInfo = {}, traits = {
        cfg = 77, trees = trapped(500, 501), treeNodes = { [500] = trapped(1001, 1003), [501] = {} },
        nodes = {}, node = TRAITS.node, entry = TRAITS.entry, def = TRAITS.def } })
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "ok" and #rk.list == 2, tostring(rk.status))
    assert(__treeArgs.n == 2 and __nodeArgs.n == 2, "the holes are skipped: " .. tostring(__treeArgs.n) .. " " .. tostring(__nodeArgs.n))
""")

case("class_traits_unreadable_node_tables_are_counted", """
    local FS = LoadDiag()
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = { 1001, 1002, 1003, 1004 },
        node = { [1001] = ST, [1002] = TRAITS.node[1001], [1003] = ST, [1004] = TRAITS.node[1003] },
        entry = TRAITS.entry, def = TRAITS.def } })
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "ok" and #rk.list == 2 and rk.skipped == 2, tostring(rk.skipped))
    assert(Has(Join(Lines()), "ranks  ok via C_Traits (C_ClassTalents.GetActiveConfigID)  2 (2 unreadable)  20271=2/5; 635=1/1"),
        Join(Lines()))
    -- every node secret: nothing was read, and the reason says why
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = { 1001, 1002 }, node = { [1001] = ST, [1002] = ST },
        entry = {}, def = {} } })
    FS.Diagnostics.RunClassRecon()
    rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "unavailable" and rk.reason == "GetTalentInfo=empty traits=secret" and rk.skipped == 2, tostring(rk.reason))
    -- a plain table with nothing in it is not "unreadable"
    ClassWorld({ talentInfo = {}, traits = { cfg = 77, trees = { 500 }, nodes = { 1001, 1002 }, node = { [1002] = TRAITS.node[1001] },
        entry = TRAITS.entry, def = TRAITS.def } })
    FS.Diagnostics.RunClassRecon()
    assert(FS.Diagnostics.GetClassRecon().talents.ranks.skipped == nil)
""")

case("class_ranks_a_mid_scan_error_or_secret_keeps_the_partial_list", """
    local FS = LoadDiag()
    local function stopAt(tab, idx, how)
        return function(q)
            if q.specializationIndex == tab and q.talentIndex == idx then
                if how == "error" then error("boom") end
                return ST
            end
            local row = CW.talentInfo[q.specializationIndex]
            return row and row[q.talentIndex]
        end
    end
    local function world(how)
        ClassWorld({ traits = TRAITS, talentInfo = {
            { { talentID = 1, name = "Alpha", rank = 2, maxRank = 5 }, { talentID = 2, name = "Beta", rank = 0, maxRank = 5 } },
            { { talentID = 3, name = "Gamma", rank = 1, maxRank = 1 } },
        } })
        return how
    end
    for _, how in ipairs({ "error", "secret" }) do
        world(how)
        C_SpecializationInfo.GetTalentInfo = stopAt(2, 2, how)
        FS.Diagnostics.RunClassRecon()
        local rk = FS.Diagnostics.GetClassRecon().talents.ranks
        local want = "partial (" .. how .. " at tab 2 idx 2)"
        assert(rk.status == want and #rk.list == 2 and rk.list[2].name == "Gamma", how .. ": " .. tostring(rk.status))
        assert(rk.source == "C_SpecializationInfo.GetTalentInfo" and rk.stoppedAt == how .. " at tab 2 idx 2")
        assert(__cfgArgs.n == nil, "a non empty partial list does not fall back to the traits")
        assert(Has(Join(Lines()), "ranks  " .. want .. " via C_SpecializationInfo.GetTalentInfo  2  Alpha=2/5; Gamma=1/1"),
            Join(Lines()))
        assert(not HasSentinel(FS.Diagnostics.GetClassRecon()))
    end
    -- nothing read before the stop: the trait route still gets its turn
    world()
    C_SpecializationInfo.GetTalentInfo = stopAt(1, 1, "error")
    FS.Diagnostics.RunClassRecon()
    local rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "ok" and rk.source == "C_Traits (C_ClassTalents.GetActiveConfigID)" and #rk.list == 2, tostring(rk.status))
    -- and with no trait route either, the stop is the status and the reason
    ClassWorld({ talentInfo = { {} } })
    C_SpecializationInfo.GetTalentInfo = stopAt(1, 1, "secret")
    FS.Diagnostics.RunClassRecon()
    rk = FS.Diagnostics.GetClassRecon().talents.ranks
    assert(rk.status == "secret" and #rk.list == 0 and rk.reason == "GetTalentInfo=secret traits=unavailable", tostring(rk.reason))
    assert(rk.stoppedAt == "secret at tab 1 idx 1")
""")

case("class_a_zero_or_missing_count_falls_back_to_three_tabs", """
    -- GetNumSpecializations and GetNumTalentTabs: a count below 1 is as good as no answer
    for _, count in ipairs({ "absent", 0, -1 }) do
        local FS = LoadDiag()
        ClassWorld()
        if count == "absent" then
            GetNumSpecializations, GetNumTalentTabs = nil, nil
        else
            GetNumSpecializations = function() return count end
            GetNumTalentTabs = function() return count end
        end
        FS.Diagnostics.RunClassRecon()
        local d = FS.Diagnostics.GetClassRecon()
        assert(#d.talents.tabs == 3 and d.talents.tabs[3].name == "Retribution", tostring(count) .. " tabs: " .. #d.talents.tabs)
        assert(d.talents.ranks.status == "ok" and #d.talents.ranks.list == 2, tostring(count) .. " ranks")
    end
    -- the spec API route for names and points reads the same default
    local FS = LoadDiag()
    ClassWorld()
    GetTalentTabInfo = nil
    GetNumSpecializations = function() return 0 end
    C_SpecializationInfo.GetSpecializationInfo = function(i)
        if i <= 3 then return 70 + i, "Spec" .. i, "d", "i", "DAMAGER", 1, i end
    end
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(#d.talents.tabs == 3 and d.talents.tabs[3].name == "Spec3" and d.talents.tabs[3].points == 3, #d.talents.tabs)
""")

case("class_shapeshift_forms_in_both_return_layouts", """
    local _, d, l = RunClass({ class = "Druid", token = "DRUID",
        forms = { { 132276, true, true, 5487 }, { 132115, false, false, 768 } } })
    assert(d.forms.count == 2 and #d.forms.list == 2)
    local f1, f2 = d.forms.list[1], d.forms.list[2]
    assert(f1.index == 1 and f1.icon == 132276 and f1.active == true and f1.castable == true and f1.spellId == 5487)
    assert(f2.active == false and f2.castable == false and f2.spellId == 768 and f1.name == nil)
    assert(Has(Join(l), "forms=2"))
    assert(Has(Join(l), "form 1  id=5487 active=true castable=true icon=132276"), Join(l))
    -- Classic layout: icon, name, active, castable, spellID.
    local _, d2 = RunClass({ class = "Druid", token = "DRUID",
        forms = { { "Interface\\\\Icons\\\\Bear", "Bear Form", true, true, 5487 } } })
    local c = d2.forms.list[1]
    assert(c.name == "Bear Form" and c.active == true and c.castable == true and c.spellId == 5487, c.spellId)
""")

case("class_secret_values_print_secret_and_are_never_touched", """
    local FS = LoadDiag()
    ClassWorld({ forms = { { SN, SB, SB, SN } } })
    C_Spell.GetSpellInfo = function(name)
        if name == "Holy Light" then return ST end
        if name == "Seal of Righteousness" then return SS end
        return { spellID = SN }
    end
    local passed = 0    -- a secret id must never reach another API
    IsPlayerSpell = function() passed = passed + 1 return SB end
    C_Spell.GetSpellAuraSecrecy = function() passed = passed + 1 return SN end
    UnitLevel = function() return SN end
    GetTalentTabInfo = function(i) return SS, SS, SN end
    C_SpecializationInfo.GetTalentInfo = function(q)
        if q.specializationIndex == 1 and q.talentIndex == 1 then return { talentID = SN, name = SS, rank = SN, maxRank = SN } end
        if q.specializationIndex == 2 and q.talentIndex == 1 then return ST end
    end
    CW.auras["player|HELPFUL"] = {
        { name = SS, spellId = SN, duration = SN, expirationTime = SN, sourceUnit = SS, dispelName = SS },
        ST,
    }
    CW.auras["target|HARMFUL|PLAYER"] = { { name = SS, spellId = SN, duration = SN } }
    CW.exists.target = SB
    CW.exists.party1 = SB
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(not HasSentinel(d), "a sentinel reached the stored data")
    assert(d.level == "secret")
    assert(passed == 0, "a secret id reached IsPlayerSpell or the secrecy API: " .. passed)
    local tl = d.talents.ranks.list[1]
    assert(d.talents.ranks.status == "partial (secret at tab 2 idx 1)" and tl.id == "secret" and tl.name == "secret"
        and tl.rank == "secret" and tl.maxRank == "secret" and #d.talents.ranks.list == 1,
        "a secret talent table stops the scan and keeps what was read: " .. tostring(d.talents.ranks.status))
    assert(Spell(d, "Holy Light").id == "secret" and Spell(d, "Holy Light").known == nil)
    assert(Spell(d, "Seal of Righteousness").id == "secret")
    assert(Spell(d, "Seal of Fury").id == "secret", "a table with a secret spellID field reads secret")
    assert(d.forms.list[1].icon == "secret" and d.forms.list[1].active == "secret" and d.forms.list[1].spellId == "secret")
    local b = d.buffs.list[1]
    assert(b.name == "secret" and b.spellId == "secret" and b.duration == "secret" and b.left == "secret")
    assert(b.sourceUnit == "secret" and b.dispelName == "secret")
    assert(d.buffs.list[2] == "secret" and d.buffs.count == 2, "a secret aura table is marked, not indexed")
    assert(d.debuffs.status == "unknown target", d.debuffs.status)
    assert(d.party.party1.status == "unknown", d.party.party1.status)
    local text = Join(Lines())
    assert(Has(text, "level=secret") and Has(text, "secret id=secret dur=secret left=secret src=secret dispel=secret"), text)
    assert(not Has(text, "SECRET_OP"))
""")

case("class_a_secret_check_that_answers_anything_but_false_fails_closed", """
    for _, answer in ipairs({ "yes", 1, "nil" }) do
        local FS = LoadDiag()
        ClassWorld()
        FS.IsSecret = function() if answer ~= "nil" then return answer end end
        FS.Diagnostics.RunClassRecon()
        local d = FS.Diagnostics.GetClassRecon()
        assert(d.token == "secret" and d.level == "secret", tostring(answer) .. " read as plain: " .. tostring(d.level))
    end
""")

case("class_a_table_that_issecrettable_flags_is_never_read", """
    -- issecretvalue says plain, issecrettable says secret: the second check must stop the read.
    local FS = LoadDiag()
    ClassWorld()
    local hidden = { name = "LEAKED", spellId = 1 }
    issecrettable = function(t) return t == hidden end
    CW.auras["player|HELPFUL"] = { hidden, { name = "Plain", spellId = 2, duration = 1 } }
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.buffs.list[1] == "secret" and d.buffs.list[2].name == "Plain", tostring(d.buffs.list[1]))
    issecrettable = function() error("boom") end
    FS.Diagnostics.RunClassRecon()
    assert(FS.Diagnostics.GetClassRecon().buffs.list[1] == "secret", "a throwing issecrettable is not plain")
    issecrettable = nil
""")

case("class_every_api_throwing_or_missing_degrades_to_markers", """
    local KEYS = { "UnitClass", "UnitLevel", "InCombatLockdown", "GetTime", "GetNumTalentTabs", "GetTalentTabInfo",
        "GetNumSpecializations", "GetTalentInfo", "GetActiveConfigID", "GetConfigInfo", "GetTreeNodes", "GetNodeInfo",
        "GetEntryInfo", "GetDefinitionInfo", "GetNumShapeshiftForms", "GetShapeshiftFormInfo", "GetSpellInfo",
        "GetSpellAuraSecrecy", "IsPlayerSpell", "GetAuraDataByIndex", "UnitExists", "IsSecret", "date" }
    -- the spec-API world, and a trait-only world so the trait calls run too
    local WORLDS = { { forms = { { 1, true, true, 5 } } }, { forms = {}, traits = TRAITS, talentInfo = {} } }
    -- 1. each API throwing alone: no error, plain data, a full chat output
    for _, world in ipairs(WORLDS) do
        for _, k in ipairs(KEYS) do
            local FS = LoadDiag()
            ClassWorld(world)
            THROW = { [k] = true }
            local ok, err = pcall(FS.Diagnostics.RunClassRecon)
            assert(ok, k .. ": " .. tostring(err))
            local d = FS.Diagnostics.GetClassRecon()
            assert(d and not HasSentinel(d), k)
            assert(#Lines() >= 8, k .. " printed " .. #Lines())
        end
    end
    -- 2. what a throw reads as in the data
    local FS = LoadDiag()
    ClassWorld({ forms = { { 1, true, true, 5 } } })
    THROW = { UnitLevel = true, GetSpellInfo = true, GetNumShapeshiftForms = true, GetAuraDataByIndex = true,
              GetTalentTabInfo = true, GetTalentInfo = true }
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.level == "error" and Spell(d, "Holy Light").id == "error" and d.forms.count == "error" and #d.forms.list == 0)
    assert(d.buffs.status == "error" and d.talents.api.GetTalentTabInfo == "error", d.buffs.status)
    assert(d.talents.ranks.status == "error" and d.talents.ranks.reason == "GetTalentInfo=error traits=unavailable")
    -- 3. everything throwing at once
    local all = {}
    for _, k in ipairs(KEYS) do all[k] = true end
    ClassWorld({ forms = { { 1, true, true, 5 } } })
    THROW = all
    assert(pcall(FS.Diagnostics.RunClassRecon))
    d = FS.Diagnostics.GetClassRecon()
    assert(d and d.token == "error" and d.level == "error" and d.inCombat == "unknown")
    -- 4. everything missing
    ClassWorld({ traits = TRAITS })
    UnitClass, UnitLevel, InCombatLockdown, GetTime, GetNumTalentTabs, GetTalentTabInfo, GetNumSpecializations =
        nil, nil, nil, nil, nil, nil, nil
    GetNumShapeshiftForms, GetShapeshiftFormInfo, C_Spell, IsPlayerSpell, C_UnitAuras, UnitExists, date =
        nil, nil, nil, nil, nil, nil, nil
    C_SpecializationInfo, C_ClassTalents, C_Traits = nil, nil, nil
    local ok, err = pcall(FS.Diagnostics.RunClassRecon)
    assert(ok, tostring(err))
    d = FS.Diagnostics.GetClassRecon()
    assert(d.token == "unavailable" and d.level == "unavailable" and d.taken == "unavailable")
    assert(d.talents.api.GetTalentTabInfo == "unavailable" and d.forms.count == "unavailable")
    assert(d.talents.ranks.status == "unavailable" and #d.talents.ranks.list == 0)
    assert(d.buffs.status:find("skipped", 1, true), d.buffs.status)
    assert(#Lines() >= 8, #Lines())
""")

case("class_missing_issecretvalue_reads_plain_data", """
    -- Theme.lua's FS.IsSecret is false without issecretvalue, so nothing reads as secret and the
    -- recon records the plain values.
    issecretvalue = nil
    local FS = LoadDiag()
    ClassWorld()
    assert(pcall(FS.Diagnostics.RunClassRecon))
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.level == 12 and d.token == "PALADIN" and d.buffs.status == "ok", tostring(d.level))
""")

case("class_aura_gate_reads_only_on_a_plain_false_from_both_checks", """
    local function Run(over, setup)
        local FS = LoadDiag()
        ClassWorld(over)
        C_Secrets = nil
        THROW = {}
        setup()
        FS.Diagnostics.RunClassRecon()
        return FS.Diagnostics.GetClassRecon()
    end
    local COMBAT, SECRETS = "skipped (combat state unknown)", "skipped (auras secret)"
    local gate = {
        { "in combat", function() CW.combat = true end, "skipped (in combat)", true },
        { "combat throws", function() THROW = { InCombatLockdown = true } end, COMBAT, "unknown" },
        { "combat secret", function() InCombatLockdown = function() return SB end end, COMBAT, "unknown" },
        { "combat missing", function() InCombatLockdown = nil end, COMBAT, "unknown" },
        { "auras should be secret", function() C_Secrets = { ShouldAurasBeSecret = function() return true end } end, SECRETS, false },
        { "secrecy answer secret", function() C_Secrets = { ShouldAurasBeSecret = function() return SB end } end, SECRETS, false },
        { "secrecy answer throws", function() C_Secrets = { ShouldAurasBeSecret = function() error("boom") end } end, SECRETS, false },
        -- with no C_Secrets the reads still go through pcall and the readable checks
        { "no secrecy API", function() end, "ok", false },
        { "secrecy plain false", function() C_Secrets = { ShouldAurasBeSecret = function() return false end } end, "ok", false },
    }
    for _, g in ipairs(gate) do
        local d = Run({}, g[2])
        local skipped = g[3] ~= "ok"
        assert(d.buffs.status == g[3], g[1] .. ": " .. tostring(d.buffs.status))
        assert(d.inCombat == g[4], g[1] .. " inCombat " .. tostring(d.inCombat))
        assert(skipped == (__auraCalls == 0), g[1] .. " aura calls " .. __auraCalls)
        if skipped then assert(d.debuffs.status == g[3] and d.party.status == g[3], g[1]) end
    end
    -- the skip shows in chat, and the non-aura sections still run
    local d = Run({ combat = true }, function() end)
    local text = Join(Lines())
    assert(Has(text, "buffs  skipped (in combat)") and Has(text, "target debuffs (mine)  skipped (in combat)")
        and Has(text, "party buffs (mine)  skipped (in combat)") and Has(text, "combat=true"), text)
    assert(#d.spells == 38 and d.talents.tabs[3].points == 5 and #d.talents.ranks.list == 2)
""")

case("class_an_aura_scan_with_no_values_is_unreadable_not_empty", """
    local _, d, l = RunClass({ auraZero = true })
    assert(d.buffs.status == "unreadable (no values)", d.buffs.status)
    assert(d.buffs.count == nil and d.buffs.list == nil)
    assert(Has(Join(l), "buffs  unreadable (no values)"))
""")

case("class_no_target_and_no_party", """
    local _, d, l = RunClass({ exists = {} })
    assert(d.debuffs.status == "no target" and #(d.debuffs.list or {}) == 0)
    assert(d.party.party1.status == "absent" and d.party.party4.status == "absent")
    local text = Join(l)
    assert(Has(text, "target debuffs (mine)  no target"))
    assert(Has(text, "party1: absent; party2: absent; party3: absent; party4: absent"), text)
""")

case("class_empty_aura_lists_say_none", """
    local _, d, l = RunClass({ auras = {} })
    assert(d.buffs.status == "ok" and d.buffs.count == 0)
    local text = Join(l)
    assert(Has(text, "buffs  0"), text)
    assert(Has(text, "target debuffs (mine)  0"))
    assert(Has(text, "party1: none; party2: absent"), text)
""")

case("class_aura_filters_are_the_requested_ones", """
    local seen = {}
    ClassWorld()
    local FS = LoadDiag()
    local real = C_UnitAuras.GetAuraDataByIndex
    C_UnitAuras.GetAuraDataByIndex = function(unit, i, filter)
        if i == 1 then seen[unit] = filter end
        return real(unit, i, filter)
    end
    FS.Diagnostics.RunClassRecon()
    assert(seen.player == "HELPFUL" and seen.target == "HARMFUL|PLAYER", tostring(seen.player) .. " " .. tostring(seen.target))
    assert(seen.party1 == "HELPFUL|PLAYER" and seen.party4 == nil, "party4 does not exist")
""")

case("class_expiration_arithmetic_only_on_plain_numbers", """
    ClassWorld()
    local FS = LoadDiag()
    CW.auras["player|HELPFUL"] = {
        { name = "a", spellId = 1, duration = 10, expirationTime = "later" },
        { name = "b", spellId = 2, duration = 10 },
        { name = "c", spellId = 3, duration = 10, expirationTime = 5001.04 },
    }
    FS.Diagnostics.RunClassRecon()
    local b = FS.Diagnostics.GetClassRecon().buffs.list
    assert(b[1].left == nil and b[2].left == nil and b[3].left == 1, tostring(b[3].left))
    ClassWorld()
    GetTime = nil
    CW.auras["player|HELPFUL"] = { { name = "a", spellId = 1, duration = 10, expirationTime = 5003 } }
    FS = LoadDiag()
    FS.Diagnostics.RunClassRecon()
    assert(FS.Diagnostics.GetClassRecon().buffs.list[1].left == nil, "no GetTime, no remaining time")
""")

case("class_caps_hold", """
    local many, forms, tabs, debuffs, party = {}, {}, {}, {}, {}
    for i = 1, 100 do
        many[i] = { name = "B" .. i, spellId = i, duration = 1, expirationTime = 5001, sourceUnit = "player" }
        debuffs[i] = { name = "D" .. i, spellId = i, duration = 1 }
        party[i] = { name = "P" .. i, spellId = i, duration = 1 }
        forms[i] = { 1, false, true, i }
    end
    for i = 1, 20 do tabs[i] = { "T" .. i, "i", i } end
    local FS = LoadDiag()
    local ranked = {}
    for i = 1, 100 do ranked[i] = { talentID = i, name = "R" .. i, rank = 1, maxRank = 5 } end
    ClassWorld({ forms = forms, tabs = tabs, talentInfo = { ranked, ranked, ranked } })
    CW.auras["player|HELPFUL"] = many
    CW.auras["target|HARMFUL|PLAYER"] = debuffs
    for _, u in ipairs({ "party1", "party2", "party3", "party4" }) do
        CW.exists[u] = true
        CW.auras[u .. "|HELPFUL|PLAYER"] = party
    end
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(#d.buffs.list == 40 and d.buffs.capped == true and d.buffs.count == 40, #d.buffs.list)
    assert(#d.debuffs.list == 16 and d.debuffs.capped == true, #d.debuffs.list)
    for _, u in ipairs({ "party1", "party2", "party3", "party4" }) do
        assert(#d.party[u].list == 20 and d.party[u].capped == true, u)
    end
    assert(__auraCalls == 40 + 16 + 80, "aura calls are bounded by the caps: " .. __auraCalls)
    assert(#d.forms.list == 10 and d.forms.count == 100, #d.forms.list)
    assert(#d.talents.tabs == 5, #d.talents.tabs)
    assert(#d.talents.ranks.list == 60 and d.talents.ranks.capped == true, #d.talents.ranks.list)
    assert(__talentCalls <= 61 and Has(Join(Lines()), "(capped)"), "the 60 entry cap stops the scan: " .. __talentCalls)
    -- an unranked tree adds nothing to the list, so only the per tab scan cap bounds the calls
    local unranked = {}
    for i = 1, 100 do unranked[i] = { talentID = i, name = "U" .. i, rank = 0, maxRank = 5 } end
    ClassWorld({ talentInfo = { unranked, unranked, unranked } })
    FS.Diagnostics.RunClassRecon()
    assert(__talentCalls == 3 * 40, "scan cap per tab: " .. __talentCalls)
    local lines = Lines()
    assert(#lines < 60, "the chat output stays bounded: " .. #lines)
    for _, ln in ipairs(lines) do assert(#ln < 4000, "a chat line grew past 4000 bytes: " .. #ln) end
""")

case("class_long_names_are_capped", """
    local long = string.rep("x", 500)
    ClassWorld()
    local FS = LoadDiag()
    CW.auras["player|HELPFUL"] = { { name = long, spellId = 1, duration = 1, sourceUnit = long, dispelName = long } }
    CW.tabs = { { long, "i", 1 } }
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(#d.buffs.list[1].name <= 60 and #d.buffs.list[1].sourceUnit <= 60 and #d.buffs.list[1].dispelName <= 60)
    assert(#d.talents.tabs[1].name <= 60)
""")

case("class_other_non_plain_values_are_dropped", """
    local FS = LoadDiag()
    ClassWorld()
    CW.auras["player|HELPFUL"] = { { name = print, spellId = {}, duration = 0 / 0, expirationTime = 1 / 0 } }
    FS.Diagnostics.RunClassRecon()
    local b = FS.Diagnostics.GetClassRecon().buffs.list[1]
    assert(b.name == nil and b.spellId == nil)
    assert(b.duration == "nan" and b.left == "nan", tostring(b.duration) .. " " .. tostring(b.left))
""")

case("class_secrecy_api_falls_back_to_c_secrets_then_gives_up", """
    local FS = LoadDiag()
    ClassWorld()
    local fn = C_Spell.GetSpellAuraSecrecy
    C_Spell.GetSpellAuraSecrecy = nil
    C_Secrets = { GetSpellAuraSecrecy = fn }
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.spellApi.secrecy == "C_Secrets.GetSpellAuraSecrecy", d.spellApi.secrecy)
    assert(Spell(d, "Holy Light").secrecy == 0)
    C_Secrets = nil
    __printed = {}
    FS.Diagnostics.RunClassRecon()
    d = FS.Diagnostics.GetClassRecon()
    assert(d.spellApi.secrecy == "unavailable" and Spell(d, "Holy Light").secrecy == nil)
    assert(Has(Join(Lines()), "secrecy=unavailable"))
    for _, ln in ipairs(Lines()) do
        if ln:find("^synthwave://class  seals") then assert(not Has(ln, " s="), "no s= field without the API: " .. ln) end
    end
""")

case("class_spell_lookup_falls_back_to_the_legacy_getspellinfo", """
    local FS = LoadDiag()
    ClassWorld()
    C_Spell.GetSpellInfo = nil
    GetSpellInfo = function(name)
        local id = CW.spells[name]
        if id then return name, nil, 1, 0, 0, 0, id end
    end
    FS.Diagnostics.RunClassRecon()
    local d = FS.Diagnostics.GetClassRecon()
    assert(d.spellApi.info == "GetSpellInfo", d.spellApi.info)
    assert(Spell(d, "Holy Light").id == 635 and Spell(d, "Holy Light").known == true)
    GetSpellInfo = nil
""")


case("class_slash_is_routed_by_the_real_panelskins_dispatcher", """
    local FS = { Theme = {}, LogDegradeOnce = function() end }
    local called = 0
    FS.Diagnostics = { RunClassRecon = function() called = called + 1 end }
    local chunk = assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))
    chunk("ForeverSynthwave", FS)
    assert(SLASH_FSRECON1 == "/fsrecon" and SlashCmdList.FSRECON)
    SlashCmdList.FSRECON("class")
    assert(called == 1, "plain class runs the recon")
    SlashCmdList.FSRECON("class now")
    assert(called == 2, "words after class are ignored like surname's")
    SlashCmdList.FSRECON("classy")
    assert(called == 2, "a word merely starting with class is not the command")
    __printed = {}
    SlashCmdList.FSRECON("nonsense")
    local want = "Forever STUwave: /fsrecon skins | pos <frame> | threat [auto [N]|clear] | "
        .. "pet [auto [N]|clear] | probe [stop] | surname | minimap [paint|spill|clear] | microbags | plateauras [arm|off] | class | all -- panel-skin idempotency readback | "
        .. "frame position report | threat/role/reaction secret-value probe | pet Phase-0 probe | "
        .. "name-API surname probe | Minimap/MinimapCluster geometry probe | "
        .. "hidden native nameplate aura frame probe (not part of all; arm waits for combat, off disarms) | "
        .. "class spell, form and aura recon (out of combat; not part of all; /fsbug includes it) | all -- run every probe"
    local got = Lines()
    assert(#got == 1 and got[1] == want, "usage text:\\n  got  " .. tostring(got[1]) .. "\\n  want " .. want)
""")

def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().DIAG_SRC = DIAG_SRC
    rt.globals().HUD_SPELLS_SRC = HUD_SPELLS_SRC
    rt.globals().HUD_PROFILES_SRC = HUD_PROFILES_SRC
    rt.globals().PANELSKINS_SRC = PANELSKINS_SRC
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    total = len(CASES)
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{total - failures}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
