#!/usr/bin/env python3
"""Runs the real FSCheck.lua headless against a mock WoW API.

FSCheck.lua is the opt-in `/fscheck` secret-value check. It runs in the middle of a play
session, so the things worth pinning are the safety properties, not the data it collects:

  * nothing runs before the command: loading the file calls no API, creates no frame,
    registers no event, schedules no timer and touches no SavedVariable;
  * no error escapes (slash command, event handler, timer) when EVERY mocked API throws,
    including issecretvalue itself and CreateFrame;
  * nothing secret is stored: with every API returning secret sentinels, the saved tree
    holds only booleans, numbers and strings, never a sentinel and never a `value` next
    to `isSecret = true`; and no sentinel was touched in a forbidden way (the sentinels'
    metamethods raise SECRET_OP, and a pcall that swallowed one would leave that text in
    the saved error strings);
  * every event is unregistered when the parts finish, no frame runs OnUpdate;
  * the combat snapshot waits for the delay and re-checks InCombatLockdown, the cast
    recorder stops at 10, the AuraContainer test builds, shows for 30s and hides;
  * the class checks (priest, shaman; one shared core) keep the same properties, and the shaman check
    additionally runs nothing protected by itself: SetMultiCastSpell, DestroyTotem and the secure test
    strip exist only behind their explicit subcommands (pinned by text and by call counters), and
    Blizzard's own totem frames are only read.

The mock is NOT the real client. Run:

    python3 tools/fscheck-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "forever-stuwave" / "Modules/Diagnostics/FSCheck.lua"
LAYOUT = HERE.parent / "forever-stuwave" / "Core" / "Layout.lua"


def tcast_top() -> float:
    """Top edge (UI units from screen centre) of our target cast bar, from Layout.lua: its centre y plus half its height."""
    m = re.search(r"^\s*tcast\s*=\s*\{[^}]*\by\s*=\s*(-?\d+)[^}]*\bh\s*=\s*(\d+)", LAYOUT.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit("Layout.lua: no tcast entry to place the shaman totem button row against")
    return int(m.group(1)) + int(m.group(2)) / 2


TCAST_TOP = tcast_top()

MOCK = r"""
__realType = type
local realType = type

__mode = "plain"            -- plain | throw | secret
__issecretThrows = true     -- in throw mode, does issecretvalue throw too?
__issecrettableThrows = false -- issecrettable alone raises, in any mode
__combat = false
__now = 1000
__apiCalls = 0
__timers = {}
__frames = {}
__allFrames = {}            -- every frame, texture, font string and line the mock handed out
__created = 0
__printed = {}
__seq = 0                   -- global call counter, stamps the first time each frame method runs
__lockThrows = false        -- InCombatLockdown raises (the timer path must fail closed)
__template = true
__acCreateThrows = false
__frameThrows = false
__unitEventThrows = false
__registerThrows = false    -- plain RegisterEvent raises too (the fallback path fails as well)
__cleuAttempts = 0          -- RegisterEvent calls naming COMBAT_LOG_EVENT_UNFILTERED (protected on Forever: must stay 0)
__hasTotemSpell = false     -- the dump lists C_Secrets.ShouldTotemSpellBeSecret; the mock omits it

-- Secret sentinels. type() still reports the pretended type, but every operation raises
-- SECRET_OP, so a forbidden touch either throws (and a pcall records the text) or fails.
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
-- A table that issecretvalue() calls plain but issecrettable() calls secret: indexing it raises.
STT = sentinel("table")
PLAINVAL = { [STT] = true }

function type(v)
    local k = SENT[v]
    if k then return k end
    return realType(v)
end

function issecretvalue(v)
    __apiCalls = __apiCalls + 1
    if __mode == "throw" and __issecretThrows then error("boom: issecretvalue") end
    return SENT[v] ~= nil and not PLAINVAL[v]
end
function issecrettable(t)
    if __issecrettableThrows or (__mode == "throw" and __issecretThrows) then error("boom: issecrettable") end
    return SENT[t] == "table"
end

function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
function date() return "2026-10-01 12:00:00" end
SlashCmdList = {}

-- Frames: a catch-all that records calls, plus the few methods the check depends on.
local FrameM = {}
local FrameMT = {}
FrameMT.__index = function(self, k)
    -- __missing: methods this client build does not have (a test sets it before the command runs).
    if __missing and __missing[k] then return nil end
    local m = FrameM[k]
    if m then return m end
    return function(me, ...)
        me._calls[k] = (me._calls[k] or 0) + 1
        me._args[k] = { ... }
        __seq = __seq + 1
        me._at[k] = me._at[k] or __seq
        -- The client throws "Font not set" for SetText / SetFormattedText on a FontString with no font: one
        -- made with an inherits template carries that template's font, otherwise SetFont / SetFontObject must
        -- come first. A write before that kills a pcall'd build there.
        if k == "SetFont" or k == "SetFontObject" then me._hasFont = true end
        if (k == "SetText" or k == "SetFormattedText") and me._kind == "CreateFontString" and not rawget(me, "_hasFont") then
            error("Font not set", 2)
        end
        if string.find(k, "^Create") then return __newFrame(k, ...) end
    end
end
function __newFrame(kind, name, parent, tmpl)
    local f = setmetatable({ _kind = kind, _name = name, _events = {}, _scripts = {}, _calls = {},
        _args = {}, _at = {}, _shown = false, _tmpl = tmpl, _attrs = {}, _hookScripts = {} }, FrameMT)
    -- CreateFontString(name, layer, template) arrives here as (name, layer, template): the template is `tmpl`.
    -- (_hasFont is read with rawget: an absent field on this mock answers with the catch-all function.)
    if kind == "CreateFontString" and realType(tmpl) == "string" then f._hasFont = true end
    if realType(name) == "string" then _G[name] = f end
    __created = __created + 1
    __allFrames[#__allFrames + 1] = f
    return f
end
__FrameM = FrameM
function FrameM.SetScript(self, k, fn) self._scripts[k] = fn end
function FrameM.RegisterEvent(self, e)
    if e == "COMBAT_LOG_EVENT_UNFILTERED" then __cleuAttempts = __cleuAttempts + 1 end
    if __registerThrows then error("boom: RegisterEvent " .. e) end
    self._events[e] = true
end
function FrameM.RegisterUnitEvent(self, e, ...)
    if e == "COMBAT_LOG_EVENT_UNFILTERED" then __cleuAttempts = __cleuAttempts + 1 end
    if __unitEventThrows then error("boom: RegisterUnitEvent") end
    self._events[e] = "unit:" .. table.concat({ ... }, ",")
end
function FrameM.UnregisterEvent(self, e) self._events[e] = nil end
function FrameM.UnregisterAllEvents(self) self._events = {} end
function FrameM.Show(self) self._shown = true; self._calls.Show = (self._calls.Show or 0) + 1 end
function FrameM.Hide(self) self._shown = false; self._calls.Hide = (self._calls.Hide or 0) + 1 end
function FrameM.IsShown(self) return self._shown end
function FrameM.SetAttribute(self, k, v)
    self._calls.SetAttribute = (self._calls.SetAttribute or 0) + 1
    self._attrs[k] = v
end
function FrameM.GetAttribute(self, k) return self._attrs[k] end
function FrameM.HookScript(self, k, fn)
    self._calls.HookScript = (self._calls.HookScript or 0) + 1
    self._hookScripts[k] = fn
end

-- AuraContainer: strict, only the methods the check is allowed to call.
local ACM = {}
for _, n in ipairs({ "SetSize", "SetPoint", "SetAuraGroupLayout", "SetFlowLayoutAnchorPoint",
                     "SetFlowLayoutGrowthDirection", "SetUnit", "SetEnabled", "Show", "Hide", "AddAuraGroup",
                     "UpdateAllAuras", "SetAlpha" }) do
    ACM[n] = function(self, ...)
        self._calls[n] = (self._calls[n] or 0) + 1
        self._args[n] = { ... }
        -- Blizzard's AuraContainer.SetUnit returns early when the token is unchanged, so
        -- only a CHANGED token counts as a real re-point (_unitChanges).
        if n == "SetUnit" then
            if self._unit ~= ... then self._unitChanges = (self._unitChanges or 0) + 1 end
            self._unit = ...
        end
        if n == "Show" then self._shown = true elseif n == "Hide" then self._shown = false end
    end
end
__ACM = ACM
local ACMT = { __index = ACM }

function CreateFrame(kind, name, parent, tmpl)
    __apiCalls = __apiCalls + 1
    if __frameThrows then error("boom: CreateFrame") end
    if kind == "AuraContainer" then
        if __acCreateThrows then error("boom: CreateFrame AuraContainer") end
        local f = setmetatable({ _kind = kind, _name = name, _events = {}, _scripts = {}, _calls = {},
            _args = {}, _shown = false }, ACMT)
        __created = __created + 1
        __allFrames[#__allFrames + 1] = f
        __frames[#__frames + 1] = f
        _G[name] = f
        return f
    end
    local f = __newFrame(kind, name, parent, tmpl)
    f._parent = parent
    __frames[#__frames + 1] = f
    return f
end
UIParent = __newFrame("Frame", nil, nil)

-- API stubs. `plain` answers in plain mode, `secret` (when given) in secret mode.
local function def(path, plain, secret)
    local ns, name = string.match(path, "^(.-)%.(.+)$")
    local fn = function(...)
        __apiCalls = __apiCalls + 1
        if __mode == "throw" then error("boom: " .. path) end
        if __mode == "secret" and secret then return secret(...) end
        return plain(...)
    end
    if ns then
        _G[ns] = _G[ns] or {}
        _G[ns][name] = fn
    else
        _G[path] = fn
    end
end

function plainAura(id)
    return { spellId = id, name = "Aura" .. id, icon = 1, duration = 15, expirationTime = 1015,
        applications = 1, sourceUnit = "player", isFromPlayerOrPlayerPet = true,
        auraInstanceID = 77, dispelName = "Magic" }
end
local function secretAura()
    return { spellId = SN, name = SS, icon = SN, duration = SN, expirationTime = SN,
        applications = SN, sourceUnit = SS, isFromPlayerOrPlayerPet = SB, auraInstanceID = SN }
end

local NAMES = { [589] = "Shadow Word: Pain", [588] = "Inner Fire", [686] = "Shadow Bolt",
    [585] = "Smite", [8092] = "Mind Blast", [172] = "Corruption", [15407] = "Mind Flay",
    [17] = "Power Word: Shield", [586] = "Fade", [61304] = "Global Cooldown" }
local KNOWN = { [589] = true, [686] = true, [585] = true, [588] = true }

def("InCombatLockdown", function()
    if __lockThrows then error("boom: InCombatLockdown (flag)") end
    return __combat
end)
def("UnitClass", function() return "Priest", "PRIEST", 5 end, function() return SS, SS, SN end)
def("UnitLevel", function() return 12 end, function() return SN end)
def("GetBuildInfo", function() return "12.1.0", "65000", "Oct 1 2026", 120100 end)
def("GetTime", function() return __now end)

local SECRETS = { "CanCompareUnitTokens", "GetPowerTypeSecrecy", "GetSpellAuraSecrecy",
    "GetSpellCastSecrecy", "GetSpellCooldownSecrecy", "HasSecretRestrictions",
    "ShouldActionCooldownBeSecret", "ShouldAurasBeSecret", "ShouldCooldownsBeSecret",
    "ShouldSpellAuraBeSecret", "ShouldSpellBookItemCooldownBeSecret", "ShouldSpellCooldownBeSecret",
    "ShouldTotemSlotBeSecret", "ShouldUnitAuraIndexBeSecret", "ShouldUnitAuraInstanceBeSecret",
    "ShouldUnitAuraSlotBeSecret", "ShouldUnitComparisonBeSecret", "ShouldUnitHealthMaxBeSecret",
    "ShouldUnitIdentityBeSecret", "ShouldUnitPowerBeSecret", "ShouldUnitPowerMaxBeSecret",
    "ShouldUnitSpellCastBeSecret", "ShouldUnitSpellCastingBeSecret", "ShouldUnitStatsBeSecret",
    "ShouldUnitThreatStateBeSecret", "ShouldUnitThreatValuesBeSecret" }
for _, n in ipairs(SECRETS) do
    local isEnum = string.find(n, "Secrecy", 1, true)
    def("C_Secrets." .. n, function() return isEnum and 0 or false end,
        function() if isEnum then return SN end return SB end)
end

def("IsPlayerSpell", function(id) return KNOWN[id] == true end, function() return SB end)
def("C_SpellBook.IsSpellKnown", function(id) return KNOWN[id] == true end, function() return SB end)
def("C_Spell.GetSpellName", function(id) return NAMES[id] end)
def("C_Spell.GetSpellInfo", function(a)
    if realType(a) == "string" then
        if a == "Shadow Word: Pain" then return { name = a, spellID = 594, castTime = 0 } end
        return nil
    end
    local n = NAMES[a]
    if not n then return nil end
    return { name = n, spellID = a, castTime = 2500, minRange = 0, maxRange = 30, iconID = 1 }
end, function(a)
    if realType(a) == "string" then return { name = a, spellID = SN, castTime = SN } end
    local n = NAMES[a]
    if not n then return nil end
    return { name = n, spellID = a, castTime = SN }
end)
def("C_Spell.GetSpellCooldown", function()
    return { startTime = 0, duration = 0, isEnabled = true, isActive = false, modRate = 1, isOnGCD = false }
end, function()
    return { startTime = SN, duration = SN, isEnabled = SB, isActive = SB, modRate = SN }
end)
def("C_Spell.GetSpellCooldownDuration", function() return { kind = "durationobject" } end, function() return ST end)
def("C_Spell.IsSpellUsable", function() return true, false end, function() return SB, SB end)
def("C_Spell.IsSpellInRange", function() return true end, function() return SB end)

def("C_UnitAuras.GetUnitAuraBySpellID", function(unit, id)
    if id == 589 or id == 594 then return plainAura(id) end
end, function() return secretAura() end)
def("C_UnitAuras.GetAuraDataBySpellName", function(unit, name)
    if name == "Shadow Word: Pain" or name == "Inner Fire" then return plainAura(589) end
end, function() return ST end)
def("C_UnitAuras.GetAuraDataByIndex", function() return plainAura(589) end, function() return ST end)
def("C_UnitAuras.GetUnitAuras", function() return { plainAura(589) } end, function() return { secretAura() } end)
def("C_UnitAuras.GetAuraDuration", function() return { kind = "durationobject" } end)
def("C_UnitAuras.GetPlayerAuraBySpellID", function(id)
    if id == 588 then return plainAura(588) end
end, function() return secretAura() end)

def("UnitExists", function() return true end)
def("UnitGUID", function() return "Creature-0-1-2-3-4-5" end, function() return SS end)
def("UnitIsDead", function() return false end, function() return SB end)
def("UnitCanAttack", function() return true end, function() return SB end)
def("UnitPower", function() return 100 end, function() return SN end)
def("UnitPowerMax", function() return 200 end, function() return SN end)
def("UnitPowerPercent", function() return 0.5 end, function() return SN end)
def("UnitHealth", function() return 300 end, function() return SN end)
def("UnitHealthMax", function() return 400 end, function() return SN end)
def("UnitHealthPercent", function() return 0.75 end, function() return SN end)
def("GetShapeshiftForm", function() return 0 end, function() return SN end)
def("UnitChannelInfo", function()
    return "Mind Flay", "Mind Flay", 1, 100000, 103000, false, false, 15407, false, 0, nil
end, function() return SS, SS, SN, SN, SN, SB, SB, SN, SB, SN, SN end)
def("C_AssistedCombat.IsAvailable", function() return true end, function() return SB end)
def("C_AssistedCombat.GetNextCastSpell", function() return 686 end, function() return SN end)
def("C_SpellActivationOverlay.IsSpellOverlayed", function() return false end, function() return SB end)
def("C_Item.GetItemCount", function() return 3 end, function() return SN end)
def("C_XMLUtil.GetTemplateInfo", function() if __template then return { name = "x" } end end)
def("C_Timer.After", function(d, fn) __timers[#__timers + 1] = { at = __now + d, fn = fn, d = d } end)

AnchorUtil = { FlowDirection = { Right = 1, Left = -1, Up = 1, Down = -1 } }
AuraContainerSortMethod = { Default = 0, Expiration = 1 }
AuraContainerSortDirection = { Normal = 0 }

-- Test helpers ----------------------------------------------------------------------
function check(c, msg) if not c then error("CHECK FAILED: " .. msg, 2) end end

function evframe()
    for _, f in ipairs(__frames) do if f._scripts.OnEvent then return f end end
end
-- The second event frame (UNIT_AURA plus the proc glow events), kept apart from the cast
-- frame because RegisterUnitEvent's unit whitelist is frame-wide.
function xframe()
    local main = evframe()
    for _, f in ipairs(__frames) do if f._scripts.OnEvent and f ~= main then return f end end
end
function nevents(f) local n = 0 for _ in pairs(f._events) do n = n + 1 end return n end
function said(sub)
    for _, l in ipairs(__printed) do if string.find(l, sub, 1, true) then return true end end
    return false
end
function runCmd(arg)
    local ok, err = pcall(SlashCmdList.FSCHECK, arg)
    check(ok, "slash command threw: " .. tostring(err))
end
function fire(event, ...)
    local f = evframe()
    check(f, "no event frame")
    local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
    check(ok, "event handler threw on " .. event .. ": " .. tostring(err))
end
function advance(dt)
    __now = __now + dt
    local again = true
    while again do
        again = false
        for _, t in ipairs(__timers) do
            if t.at <= __now and not t.fired then
                t.fired = true
                again = true
                local ok, err = pcall(t.fn)
                check(ok, "timer threw: " .. tostring(err))
                break
            end
        end
    end
end
function pendingTimers()
    local n = 0
    for _, t in ipairs(__timers) do if not t.fired then n = n + 1 end end
    return n
end
function casts(n)
    for i = 1, n do
        if __mode == "secret" then
            fire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, SN)
        else
            fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-" .. i, 686)
        end
    end
end
function complete()
    runCmd("")
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    advance(4)
    casts(10)
    advance(30)
    check(ForeverSTUwaveDB.fscheck.meta.status == "done", "run did not finish")
    __combat = false
end
function KNOWN_ONLY(id)
    IsPlayerSpell = function(i) return i == id end
    C_SpellBook.IsSpellKnown = IsPlayerSpell
end
function noOnUpdate()
    for _, f in ipairs(__frames) do check(f._scripts.OnUpdate == nil, "an OnUpdate is set") end
end
-- Every frame, texture and line the mock handed out is hidden (the host stays shown but is
-- never explicitly shown, so a leftover Show is a check test object left on screen).
function allHidden()
    for _, f in ipairs(__allFrames) do
        -- Buttons are the engine's own (it shows them); everything else is a check test object.
        if f ~= UIParent and f._kind ~= "Button" then check(not f._shown, "a " .. tostring(f._kind) .. " test object is still shown") end
    end
end
-- A container whose AddAuraGroup builds `n` buttons through the group's initializeFrame (as the
-- engine does), with the few extra methods the AuraContainer check reads. Returns the buttons.
function gsMockContainer(n)
    local buttons = {}
    local dur = { kind = "buttonDuration" }
    __ACM.GetChildren = function() return unpack(buttons) end
    __ACM.GetAuraGroupFrameCount = function() return #buttons end
    __ACM.AddAuraGroup = function(self, key, filter, opts)
        self._calls.AddAuraGroup = (self._calls.AddAuraGroup or 0) + 1
        check(key == "mine" and filter == "HARMFUL|PLAYER", "group key or filter: " .. tostring(key))
        check(type(opts.initializeFrame) == "function", "no initializeFrame")
        for _ = 1, n do
            local b = __newFrame("Button")
            b._shown = true
            b.GetAuraDuration = function() return dur end
            buttons[#buttons + 1] = b
            opts.initializeFrame(b)
        end
    end
    hooksecurefunc = function(obj, name, fn)
        local h = rawget(obj, "_hooks")
        if not h then h = {}; obj._hooks = h end
        h[name] = fn
    end
    __FrameM.GetStatusBarTexture = function() return { GetHeight = function() return 7 end } end
    __FrameM.IsVisible = function() return true end
    return buttons
end
-- What the engine does once the container is shown on a target: the duration object goes to
-- our Cooldown and StatusBar through the hooked methods.
function engineCalls(duration)
    local cooldowns, bars = 0, 0
    for _, f in ipairs(__frames) do
        local h = rawget(f, "_hooks")
        if h and h.SetCooldownFromDurationObject then
            h.SetCooldownFromDurationObject(f, duration, false)
            cooldowns = cooldowns + 1
        end
        if h and h.SetTimerDuration then
            h.SetTimerDuration(f, duration, 0, 0)
            bars = bars + 1
        end
    end
    return cooldowns, bars
end
-- `/fscheck hot`: AddAuraSlot / AddAuraGroup build buttons through initializeFrame as the engine does,
-- GetChildren lists the slot button and the group buttons. Only party1 and the player exist.
function hotMock(groupButtons)
    UnitExists = function(token) return token == "player" or token == "party1" end
    local orig = C_Spell.GetSpellInfo
    C_Spell.GetSpellInfo = function(a)
        if a == "Renew" then return { name = "Renew", spellID = 9999, castTime = 0 } end
        return orig(a)
    end
    __ACM.IsShown = function(self) return self._shown end
    __ACM.GetNumChildren = function(self) return #(self._kids or {}) end
    __ACM.GetChildren = function(self) return unpack(self._kids or {}) end
    __ACM.GetAuraGroupFrameCount = function(self) return self._groupKids or 0 end
    -- The timer-bar shape's API surface (names from the 12.1.0 documentation dump).
    __missing, __slotThrows = nil, nil
    Enum = {
        StatusBarTimerDirection = { ElapsedTime = 0, RemainingTime = 1 },
        StatusBarInterpolation = { Immediate = 0, ExponentialEaseOut = 1 },
        DurationTextBindingProperty = { RemainingDuration = 0, RemainingPercent = 1 },
        NumericRuleFormatRounding = { Nearest = 0, Up = 1, Down = 2 },
        LuaCurveType = { Linear = 0, Step = 1 },
    }
    __made = { formatters = {}, curves = {} }
    C_StringUtil = {
        CreateNumericRuleFormatter = function()
            local f = { breakpoints = {} }
            function f:AddBreakpoint(bp) self.breakpoints[#self.breakpoints + 1] = bp end
            __made.formatters[#__made.formatters + 1] = f
            return f
        end,
    }
    C_CurveUtil = {
        CreateColorCurve = function()
            local c = { points = {} }
            function c:SetType(t) self.curveType = t end
            function c:AddPoint(x, color) self.points[#self.points + 1] = { x = x, color = color } end
            __made.curves[#__made.curves + 1] = c
            return c
        end,
    }
    CreateColor = function(r, g, b, a) return { r = r, g = g, b = b, a = a or 1 } end
    __FrameM.GetStatusBarTexture = function(self)
        self._sbt = rawget(self, "_sbt") or __newFrame("Texture")
        return self._sbt
    end
    __FrameM.GetFrameLevel = function() return 1 end
    -- Every SetPoint and SetFrameLevel is kept in order (the catch-all keeps only the last args), so a
    -- dropped anchor or a missing level raise shows up.
    local function record(self, k, ...)
        self._calls[k] = (self._calls[k] or 0) + 1
        self._args[k] = { ... }
        self._at[k] = self._at[k] or __seq
    end
    __FrameM.SetPoint = function(self, ...)
        record(self, "SetPoint", ...)
        -- (rawget: an absent field on this mock answers with the catch-all function)
        local pts = rawget(self, "_points") or {}
        self._points = pts
        pts[#pts + 1] = { ... }
    end
    __FrameM.SetFrameLevel = function(self, lvl)
        record(self, "SetFrameLevel", lvl)
        local lv = rawget(self, "_levels") or {}
        self._levels = lv
        lv[#lv + 1] = lvl
    end
    -- Ordering rule of the engine: once SetDurationBar owns a bar, the bar's texture is the engine's.
    __FrameM.SetDurationBar = function(self, bar, opts)
        record(self, "SetDurationBar", bar, opts)
        if type(bar) == "table" then bar._locked = true end
    end
    __FrameM.SetStatusBarTexture = function(self, ...)
        if rawget(self, "_locked") then error("SetStatusBarTexture after SetDurationBar", 2) end
        record(self, "SetStatusBarTexture", ...)
    end
    -- Tripwire: the hot section must never read an aura, a duration, a bar value or a text.
    __auraRead = false
    for _, n in ipairs({ "GetUnitAuraBySpellID", "GetAuraDataBySpellName", "GetAuraDataByIndex",
                         "GetUnitAuras", "GetAuraDuration", "GetPlayerAuraBySpellID" }) do
        C_UnitAuras[n] = function() __auraRead = true end
    end
    for _, n in ipairs({ "GetValue", "GetText", "GetMinMaxValues", "GetFormattedText" }) do
        __FrameM[n] = function() __auraRead = true end
    end
    __ACM.AddAuraSlot = function(self, key, filter, opts)
        check((key == "renew" or key == "renewbar") and filter == "HELPFUL|PLAYER", "slot key or filter: " .. tostring(key) .. " " .. tostring(filter))
        if __slotThrows and __slotThrows[key] then error(__slotThrows[key]) end
        local b = __newFrame("Button")
        self._kids = self._kids or {}
        self._kids[#self._kids + 1] = b
        if key == "renew" then
            self._slotOpts = opts
            self._slotBtn = b
        else
            self._barOpts = opts
            self._barBtn = b
        end
        opts.initializeFrame(b)
        return b
    end
    __ACM.AddAuraGroup = function(self, key, filter, opts)
        check(key == "short" and filter == "HELPFUL|PLAYER", "group key or filter: " .. tostring(key) .. " " .. tostring(filter))
        self._groupOpts = opts
        self._kids = self._kids or {}
        self._groupBtns = {}
        for _ = 1, groupButtons do
            local b = __newFrame("Button")
            self._kids[#self._kids + 1] = b
            self._groupBtns[#self._groupBtns + 1] = b
            opts.initializeFrame(b)
        end
        self._groupKids = groupButtons
    end
end
-- `/fscheck priest`: the extra APIs the priest section reads (the default mock lacks them, which is itself a
-- test: a missing API must record "absent"). Plain mode answers like a healthy client, secret mode with
-- sentinels, throw mode raises. The player knows Power Word: Shield, Smite and Shoot only.
function priestMock()
    local function obj(methods)
        return setmetatable({}, { __index = function(_, k)
            local m = methods[k]
            if not m then return nil end
            return function(self, ...)
                if __mode == "throw" then error("boom: method " .. k) end
                return m(...)
            end
        end })
    end
    IsPlayerSpell = function(id) return id == 17 or id == 585 or id == 5019 end
    C_SpellBook.IsSpellKnown = IsPlayerSpell
    def("GetPowerRegen", function() return 8, 4 end, function() return SN, SN end)
    def("GetPowerRegenForPowerType", function() return 8, 4 end, function() return SN, SN end)
    def("UnitCastingInfo", function() return nil end, function() return SS, SS, SN, SN, SN, SB, SS, SB, SN, SN end)
    def("C_Spell.GetSpellPowerCost", function(id)
        if id == 5019 then return end   -- the real client: no table at all for a free spell
        if id == 2050 then return {} end
        return { { type = 0, name = "MANA", cost = 150, minCost = 150, costPercent = 0 } }
    end, function() return ST end)
    def("C_Spell.GetSpellCharges", function() return { currentCharges = 1, maxCharges = 2, cooldownStartTime = 0, cooldownDuration = 0, chargeModRate = 1, isActive = false } end,
        function() return { currentCharges = SN, maxCharges = 2, cooldownStartTime = SN, cooldownDuration = SN, chargeModRate = SN, isActive = SB } end)
    def("C_Spell.GetSpellCooldownDuration", function()
        return obj({ IsZero = function() return true end, GetRemainingDuration = function() return 0 end })
    end, function() return ST end)
    def("UnitGetTotalAbsorbs", function() return 0 end, function() return SN end)
    def("UnitGetIncomingHeals", function() return 0 end, function() return SN end)
    def("CreateUnitHealPredictionCalculator", function()
        return obj({
            GetDamageAbsorbs = function() if __mode == "secret" then return SN, SB end return 120, false end,
            GetIncomingHeals = function() if __mode == "secret" then return SN, SN, SN, SB end return 300, 200, 100, false end,
            GetHealAbsorbs = function() if __mode == "secret" then return SN, SB end return 0, false end,
        })
    end)
    def("UnitGetDetailedHealPrediction", function() end)
    def("C_StringUtil.TruncateWhenZero", function() return "" end, function() return SS end)
    CurveConstants = { ScaleTo100 = { kind = "curve" } }
    def("UnitClassification", function() return "elite" end, function() return SS end)
    def("UnitEffectiveLevel", function() return 20 end, function() return SN end)
    def("UnitCreatureType", function() return "Beast", 1 end, function() return SS, SN end)
    def("UnitInRange", function() return true, true end, function() return SB, SB end)
    def("UnitIsDeadOrGhost", function() return false end)
    def("UnitIsConnected", function() return true end)
    def("UnitThreatSituation", function() return 1 end, function() return SN end)
    def("UnitDetailedThreatSituation", function() return false, 0, 10, 10, 10 end, function() return SB, SN, SN, SN, SN end)
    def("C_LossOfControl.GetActiveLossOfControlDataCount", function() return 1 end)
    def("C_LossOfControl.GetActiveLossOfControlData", function()
        return { locType = "FEAR", spellID = 8122, displayText = "Feared", priority = 5, displayType = 1, startTime = 1, duration = 8 }
    end, function() return ST end)
    def("C_CombatLog.IsCombatLogRestricted", function() return true end)
    def("C_UnitAuras.GetUnitAuraInstanceIDs", function() return { 77 } end, function() return ST end)
    def("C_UnitAuras.GetAuraDuration", function()
        return obj({
            GetRemainingDuration = function() return 12.5 end, IsZero = function() return false end,
            HasExpired = function() return false end, IsActive = function() return true end,
            EvaluateRemainingDuration = function() return 1 end,
        })
    end, function() return ST end)
    Enum = Enum or {}
    Enum.LuaCurveType = { Linear = 0, Step = 1 }
    C_CurveUtil = C_CurveUtil or {}
    C_CurveUtil.CreateCurve = function()
        return { SetType = function() end, AddPoint = function() end }
    end
end
-- The priest check's own event frame: the one that registered UNIT_POWER_UPDATE.
function pframe()
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and f._events.UNIT_POWER_UPDATE then return f end
    end
end
function pfire(event, ...)
    local f = pframe()
    check(f, "no priest event frame")
    local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
    check(ok, "priest handler threw on " .. event .. ": " .. tostring(err))
end
function pull(dt)
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    advance(dt or 2)
end

-- `/fscheck shaman`. __totem[slot] = { haveTotem, name, startTime, duration, icon, modRate, spellID } is a live
-- totem; an empty slot answers false and zeros. The player knows the ids in SHKNOWN (default: Stoneskin Totem
-- only, a level 4 shaman). __mcSpells[slot] is what GetMultiCastTotemSpells answers, __actions[id] the spell
-- slotted on a multicast action id; SetMultiCastSpell and DestroyTotem are recorded in __setCalls / __destroyCalls
-- and change that state, so the check can be shown to call them only when told to.
SHNAMES = { [8071] = "Stoneskin Totem", [2484] = "Earthbind Totem", [3599] = "Searing Totem", [5394] = "Healing Stream Totem",
    [66842] = "Call of the Elements", [66843] = "Call of the Ancestors", [36936] = "Totemic Recall" }
local function durObj(left)
    local methods = {
        GetRemainingDuration = function() return left end, GetElapsedDuration = function() return 50 end,
        GetTotalDuration = function() return 300 end, IsZero = function() return false end,
        HasExpired = function() return false end, HasStarted = function() return true end,
        IsActive = function() return true end, HasSecretValues = function() return false end,
    }
    return setmetatable({}, { __index = function(_, k)
        local m = methods[k]
        if not m then return nil end
        return function(self, ...)
            if __mode == "throw" then error("boom: method " .. k) end
            return m(...)
        end
    end })
end
function nativeFrame(name, l, b, w, h, shown)
    local f = __newFrame("Frame", name)
    f._shown = shown
    f.GetLeft = function() return l end
    f.GetBottom = function() return b end
    f.GetRight = function() return l + w end
    f.GetTop = function() return b + h end
    f.GetRect = function() return l, b, w, h end
    f.GetWidth = function() return w end
    f.GetHeight = function() return h end
    f.GetSize = function() return w, h end
    f.GetScale = function() return 1 end
    f.GetEffectiveScale = function() return 1 end
    f.GetAlpha = function() return 1 end
    f.GetEffectiveAlpha = function() return 1 end
    f.GetNumPoints = function() return 1 end
    f.GetPoint = function() return "BOTTOM", UIParent, "BOTTOM", 0, 12 end
    f.GetParent = function() return UIParent end
    f.GetName = function() return name end
    return f
end
-- Blizzard's totem frames. Whatever the check does to them (any call that changes a frame) is counted.
SH_BLIZZ = { "MultiCastActionBarFrame", "MultiCastSlotButton1", "MultiCastSlotButton2", "MultiCastSummonSpellButton",
    "MultiCastFlyoutFrame", "TotemFrame" }
function shamanFrames(overlap)
    nativeFrame("MultiCastActionBarFrame", 500, 100, 300, 50, true)
    nativeFrame("MultiCastSlotButton1", 510, 105, 30, 30, true)
    nativeFrame("MultiCastSlotButton2", 550, 105, 30, 30, true)
    nativeFrame("MultiCastSummonSpellButton", 470, 105, 30, 30, false)
    nativeFrame("MultiCastFlyoutFrame", 510, 135, 30, 120, false)
    nativeFrame("TotemFrame", 20, 400, 100, 40, false)
    -- our action bar group: over the native bar, or well clear of it
    if overlap then nativeFrame("FSActionBarStack", 400, 50, 600, 120, true)
    else nativeFrame("FSActionBarStack", 400, 500, 600, 120, true) end
end
-- Any call that could change a frame (a read such as GetPoint or IsShown is fine).
local MUTATORS = { "^Set", "^Show", "^Hide", "^Enable", "^Disable", "^Clear", "^Register", "^Unregister", "^Hook",
    "^Create", "^Click", "^Lock", "^Start", "^Stop", "^Raise", "^Lower", "^Toggle", "^Execute", "^Add", "^Remove" }
function blizzTouched()
    local n, names = 0, {}
    for _, name in ipairs(SH_BLIZZ) do
        local f = _G[name]
        if f then
            for k, v in pairs(f._calls) do
                for _, pat in ipairs(MUTATORS) do
                    if string.find(k, pat) then n = n + v; names[#names + 1] = name .. ":" .. k break end
                end
            end
        end
    end
    return n, table.concat(names, ",")
end
function shamanMock(known)
    SHKNOWN = known or { [8071] = true }
    __totem, __mcSpells, __actions, __setCalls, __destroyCalls = {}, { [2] = { 8071 } }, { [134] = 8071 }, {}, {}
    def("UnitClass", function() return "Shaman", "SHAMAN", 7 end, function() return SS, SS, SN end)
    def("UnitLevel", function() return 4 end, function() return SN end)
    def("IsPlayerSpell", function(id) return SHKNOWN[id] == true end, function() return SB end)
    C_SpellBook.IsSpellKnown = IsPlayerSpell
    def("C_Spell.GetSpellName", function(id) return SHNAMES[id] end)
    def("C_Spell.GetSpellInfo", function(a)
        if realType(a) == "string" then
            for id, n in pairs(SHNAMES) do
                if n == a and SHKNOWN[id] then return { name = n, spellID = id, castTime = 0 } end
            end
            return nil
        end
        local n = SHNAMES[a]
        if not n then return nil end
        return { name = n, spellID = a, castTime = 0 }
    end, function(a)
        if realType(a) == "string" then return { name = a, spellID = SN, castTime = SN } end
        return { name = SS, spellID = a, castTime = SN }
    end)
    def("C_Spell.GetSpellCooldownDuration", function() return durObj(0) end, function() return ST end)
    def("GetNumTotemSlots", function() return 4 end, function() return SN end)
    def("GetTotemInfo", function(slot)
        local t = __totem[slot]
        if t then return unpack(t) end
        return false, "", 0, 0, 0, 0, 0
    end, function() return SB, SS, SN, SN, SN, SN, SN end)
    def("GetTotemTimeLeft", function(slot) if __totem[slot] then return 250 end return 0 end, function() return SN end)
    def("GetTotemCannotDismiss", function() return false end, function() return SB end)
    def("GetTotemDuration", function(slot) return durObj(250) end, function() return ST end)
    def("C_TooltipInfo.GetTotem", function(slot) if __totem[slot] then return { type = 1, id = __totem[slot][7] } end end, function() return ST end)
    def("C_Secrets.ShouldTotemSpellBeSecret", function() return false end, function() return SB end)
    def("C_ActionBar.GetMultiCastBarIndex", function() return 12 end, function() return SN end)
    def("HasMultiCastActionBar", function() return false end, function() return SB end)
    def("HasMultiCastActionPage", function(p) return p == 1 end, function() return SB end)
    def("GetMultiCastTotemSpells", function(id)
        local list = __mcSpells[((id - 1) % 4) + 1]
        if list then return unpack(list) end
    end, function() return SN end)
    def("HasAction", function(id) return __actions[id] ~= nil end, function() return SB end)
    __actionRaw = {}   -- id -> { type, id, subType }: a slot holding something that is not a plain spell (a macro ...)
    def("GetActionInfo", function(id)
        local raw = __actionRaw[id]
        if raw then return unpack(raw) end
        if __actions[id] then return "spell", __actions[id], "spell" end
    end, function() return SS, SN, SS end)
    def("GetActionTexture", function(id) if __actions[id] then return 136098 end end, function() return SN end)
    def("SetMultiCastSpell", function(id, spell)
        __setCalls[#__setCalls + 1] = { id, spell, __combat }
        __actionRaw[id] = nil
        __actions[id] = spell
    end, function() end)
    def("DestroyTotem", function(slot)
        __destroyCalls[#__destroyCalls + 1] = { slot, __combat }
        __totem[slot] = nil
    end, function() end)
    FIRE_TOTEM_SLOT, EARTH_TOTEM_SLOT, WATER_TOTEM_SLOT, AIR_TOTEM_SLOT, MAX_TOTEMS = 1, 2, 3, 4, 4
    SHAMAN_TOTEM_PRIORITIES = { 2, 1, 3, 4 }
    ERR_SPELL_FAILED_TOTEMS = "Requires a totem."
end
-- The shaman check's own event frame: the one that registered PLAYER_TOTEM_UPDATE.
function sframe()
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and f._events.PLAYER_TOTEM_UPDATE then return f end
    end
end
function sfire(event, ...)
    local f = sframe()
    check(f, "no shaman event frame")
    local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
    check(ok, "shaman handler threw on " .. event .. ": " .. tostring(err))
end
-- The frame that waits for PLAYER_REGEN_ENABLED to finish hiding the totem button row (not the check's own event frame).
function regenFrame()
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and f._events.PLAYER_REGEN_ENABLED and not f._events.PLAYER_TOTEM_UPDATE then return f end
    end
end
function fireRegen()
    local f = regenFrame()
    check(f, "no frame is waiting for PLAYER_REGEN_ENABLED")
    local ok, err = pcall(f._scripts.OnEvent, f, "PLAYER_REGEN_ENABLED")
    check(ok, "regen handler threw: " .. tostring(err))
end
-- Counts of every call that could change the totem button row or its secure buttons, and which ones moved between two reads.
local STRIP_KEYS = { "Show", "Hide", "SetPoint", "EnableMouse", "SetAttribute", "SetSize", "RegisterForClicks", "SetAlpha", "SetParent" }
function stripCalls()
    local out = {}
    local list = { FSCheckShamanStrip, FSCheckShamanBtn1, FSCheckShamanBtn2, FSCheckShamanBtn3 }
    for i = 1, 4 do
        for _, k in ipairs(STRIP_KEYS) do out[(i - 1) .. ":" .. k] = list[i] and list[i]._calls[k] or 0 end
    end
    return out
end
function callsMoved(a, b)
    local moved = {}
    for k, v in pairs(b) do if a[k] ~= v then moved[#moved + 1] = k end end
    table.sort(moved)
    return table.concat(moved, ",")
end

-- Walks the saved tree. Only plain strings, numbers and booleans may be stored; no
-- sentinel, no metatable, no value beside isSecret = true, no SECRET_OP text.
function scan(root)
    local stats = { secretTrue = 0, tables = 0 }
    local seen = {}
    local function visit(t, path)
        check(SENT[t] == nil, "sentinel table stored at " .. path)
        if seen[t] then return end
        seen[t] = true
        stats.tables = stats.tables + 1
        check(getmetatable(t) == nil, "metatable on stored table at " .. path)
        for k, v in next, t do
            local tk = realType(k)
            check(tk == "string" or tk == "number", "bad key type " .. tk .. " at " .. path)
            local tv = realType(v)
            if tv == "table" then
                check(SENT[v] == nil, "sentinel stored at " .. path .. "." .. tostring(k))
                visit(v, path .. "." .. tostring(k))
            elseif tv == "string" then
                check(not string.find(v, "SECRET_OP", 1, true),
                    "forbidden secret operation recorded at " .. path .. "." .. tostring(k) .. ": " .. v)
            elseif tv ~= "number" and tv ~= "boolean" then
                error("unsupported " .. tv .. " stored at " .. path .. "." .. tostring(k))
            end
        end
        if rawget(t, "isSecret") == true then
            stats.secretTrue = stats.secretTrue + 1
            check(rawget(t, "value") == nil, "value stored beside isSecret=true at " .. path)
        end
    end
    visit(root, "fscheck")
    return stats
end
"""

# Each case: (name, mode, lua body). The mock is booted fresh per case and FSCheck.lua loaded.
CASES: list[tuple[str, str, str]] = []


def case(name: str, mode: str = "plain"):
    def wrap(body: str):
        CASES.append((name, mode, body))
        return body

    return wrap


case("nothing_runs_before_the_command")(r"""
check(__apiCalls == 0, "an API was called at load: " .. __apiCalls)
check(#__frames == 0, "a frame was created at load")
check(#__timers == 0, "a timer was scheduled at load")
check(ForeverSTUwaveDB == nil, "SavedVariables touched at load")
check(SLASH_FSCHECK1 == "/fscheck", "slash command not registered")
check(type(SlashCmdList.FSCHECK) == "function", "slash handler missing")
-- help and a bad argument must not arm anything either
runCmd("help")
runCmd("nonsense")
check(__apiCalls == 0 and #__frames == 0 and #__timers == 0, "help armed something")
check(said("/fscheck reset"), "usage text missing")
""")

case("full_run_in_plain_mode")(r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db and db.ooc, "ooc snapshot missing")
check(said("snapshot saved (ooc)"), "arm line missing")
local f = evframe()
check(f._events.PLAYER_REGEN_DISABLED == true, "REGEN not registered")
check(f._events.UNIT_SPELLCAST_SUCCEEDED == "unit:player", "SUCCEEDED not a player unit event")
check(f._events.UNIT_SPELLCAST_START == "unit:player", "START not a player unit event")
for _, e in ipairs({ "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_CHANNEL_UPDATE", "UNIT_SPELLCAST_CHANNEL_STOP" }) do
    check(f._events[e] == "unit:player", e .. " not registered")
end

-- ooc content
local env = db.ooc.env
check(env.inCombatLockdown.r1.value == false, "lockdown value")
check(env.unitClass.r2.value == "PRIEST", "class token kept")
check(env.unitLevel.r1.value == 12, "level kept")
check(env.buildInfo.r2.value == "65000", "build kept")
check(db.ooc.secrets.absent == "ShouldTotemSpellBeSecret", "absent list: " .. tostring(db.ooc.secrets.absent))
check(db.ooc.spells.s589.isPlayerSpell.r1.value == true, "589 known")
check(db.ooc.spells.s15473.isPlayerSpell.r1.value == false, "shadowform unknown")
local swp = db.ooc.targetAuras.s589
check(swp.byRank1ID.fields.spellId.type == "number", "rank1 aura fields")
check(swp.byName.fields.auraInstanceID.type == "number", "by name aura")
check(swp.knownRankID == 594, "known rank resolved")
check(swp.byKnownRankID and swp.byKnownRankID.fields, "known rank read")
check(swp.byRank1ID.durationObject and swp.byRank1ID.durationObject.r1.type == "table", "GetAuraDuration recorded")
check(db.ooc.targetAuras.getUnitAuras.count == 1, "GetUnitAuras count")
check(db.ooc.playerAuras.s588.byID.fields.spellId.type == "number", "player aura")
check(db.ooc.cooldowns.s686.cooldown.fields.isActive.type == "boolean", "cooldown fields")
check(db.ooc.cooldowns.s686.cooldown.fields.isOnGCD, "extra cooldown key discovered")
check(db.ooc.cooldowns.shadowBoltInfo.fields.castTime.type == "number", "castTime")
check(db.ooc.assistedCombat.namespace == "present", "assisted combat")
check(db.ooc.spellOverlay.shadowBoltOverlayed.r1.type == "boolean", "overlay")
check(db.ooc.items.soulShardCount.r1.value == 3, "soul shards")
check(db.ooc.secrets.calls["GetPowerTypeSecrecy(0)"].r1.type == "number", "secrecy call recorded")

-- aura container built hidden, group added with the documented arguments
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check(ac, "AuraContainer not created")
check(ac._shown == false, "container visible before combat")
check(ac._args.AddAuraGroup[1] == "mine" and ac._args.AddAuraGroup[2] == "HARMFUL|PLAYER", "AddAuraGroup args")
local options = ac._args.AddAuraGroup[3]
check(type(options.initializeFrame) == "function", "initializeFrame missing")
check(options.layout.elementWidth == 24, "24px icons")
check(db.auracontainer.status == "built", "ac status " .. tostring(db.auracontainer.status))
for k, v in pairs(db.auracontainer.steps) do check(v == "ok", "ac step " .. k .. " = " .. tostring(v)) end

-- initializeFrame uses the Plater button API with the minimum options
local button = __newFrame("Button", nil, ac)
options.initializeFrame(button)
check(button._calls.SetIcon == 1 and button._calls.SetDurationCooldown == 1 and button._calls.SetDurationText == 1,
    "button API not used")
check(db.auracontainer.initCalls == 1 and db.auracontainer.initError == nil, "initializeFrame errored")

-- status while armed does not re-snapshot
local calls = __apiCalls
runCmd("")
check(said("armed."), "status line missing")
check(__apiCalls == calls, "status re-ran the check")

-- combat: the snapshot waits 4s and re-checks the lockdown
__combat = true
fire("PLAYER_REGEN_DISABLED")
check(db.combat == nil, "combat snapshot taken before the delay")
check(pendingTimers() == 1 and __timers[#__timers].d == 4, "4s timer not scheduled")
fire("PLAYER_REGEN_DISABLED")
check(pendingTimers() == 1, "a second REGEN stacked a timer")
__combat = false
advance(4)
check(db.combat == nil, "snapshot taken after combat already ended")
check(f._events.PLAYER_REGEN_DISABLED == true, "REGEN unregistered after a skipped snapshot")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(db.combat and db.combat.env.inCombatLockdown.r1.value == true, "combat snapshot missing")
check(db.combat.combatSkips == 1, "skip not counted")
check(said("combat snapshot saved"), "combat line missing")
check(f._events.PLAYER_REGEN_DISABLED == nil, "REGEN still registered")
check(ac._shown == true and ac._args.SetUnit[1] == "target" and ac._args.SetEnabled[1] == true, "container not shown on target")
local labels = 0
for _, fr in ipairs(__frames) do if fr._name == "FSCheckAuraLabel" and fr._shown then labels = labels + 1 end end
check(labels == 1, "label not shown")

-- channel + casts
fire("UNIT_SPELLCAST_CHANNEL_START", "player", "Cast-c", 15407)
fire("UNIT_SPELLCAST_CHANNEL_STOP", "player", "Cast-c", 15407)
casts(10)
check(#db.casts == 10, "10 casts expected, got " .. #db.casts)
check(#db.channel == 2, "channel events: " .. #db.channel)
local c1 = db.casts[1]
check(c1.arg3.value == 686 and c1.arg3.isSecret == false, "spellID kept when plain")
check(c1.arg1.value == nil and c1.arg2.value == nil, "only the spellID may keep a value")
check(c1.inCombatLockdown.r1.value == true and c1.time.r1.type == "number" and c1.targetGUID.r1.type == "string", "cast context")
check(db.channel[1].channelInfo.startTimeMs.type == "number", "channel info")
check(said("cast recorder saved"), "cast line missing")
check(f._events.UNIT_SPELLCAST_SUCCEEDED == nil and f._events.UNIT_SPELLCAST_CHANNEL_START == nil, "cast events still registered")
check(f._events.UNIT_SPELLCAST_START == nil, "START still registered after the casts finished")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "late", 1)
check(#db.casts == 10, "an 11th cast was recorded")
check(not said("done, /reload"), "finished before the aura test")

-- aura test hides after 30s, then everything is done
advance(29)
check(ac._shown == true, "container hidden early")
advance(1)
check(ac._shown == false, "container still visible after 30s")
check(said("aura test finished"), "aura line missing")
check(said("done, /reload or log out to save"), "done line missing")
check(nevents(f) == 0, "events left registered")
check(db.meta.status == "done", "meta status")
noOnUpdate()
scan(db)

-- reset clears results and disarms
runCmd("reset")
check(ForeverSTUwaveDB.fscheck == nil, "reset left results")
check(nevents(f) == 0, "reset left events")
""")

case("reset_cancels_pending_timers")(r"""
runCmd("")
__combat = true
fire("PLAYER_REGEN_DISABLED")
runCmd("reset")
advance(60)
check(ForeverSTUwaveDB.fscheck == nil, "a stale timer wrote after reset")
check(nevents(evframe()) == 0, "events registered after reset")
""")

case("every_api_throws", "throw")(r"""
__issecretThrows = true
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db.ooc, "ooc snapshot missing")
check(type(db.ooc.env.inCombatLockdown.err) == "string", "error not stored as a string")
check(db.ooc.env.canTestSecret == false, "canTestSecret should be false")
check(db.auracontainer.status == "template check errored", "ac status " .. tostring(db.auracontainer.status))
check(db.ooc.targetAuras.skipped == "no target", "target section should skip when UnitExists throws")
__combat = true
fire("PLAYER_REGEN_DISABLED")
check(db.combat, "no timer: combat snapshot should be taken immediately")
for i = 1, 3 do fire("UNIT_SPELLCAST_CHANNEL_START", "player", "x", 1) end
casts(10)
check(#db.casts == 10 and #db.channel == 3, "recorders under throwing APIs")
check(said("done, /reload or log out to save"), "did not finish")
check(nevents(evframe()) == 0, "events left registered")
noOnUpdate()
scan(db)
""")

case("every_api_throws_but_issecretvalue_works", "throw")(r"""
__issecretThrows = false
runCmd("")
local db = ForeverSTUwaveDB.fscheck
local err = db.ooc.env.inCombatLockdown.err
check(type(err) == "string" and string.find(err, "boom: InCombatLockdown", 1, true), "error text lost: " .. tostring(err))
__combat = true
fire("PLAYER_REGEN_DISABLED")
casts(10)
check(said("done, /reload"), "did not finish")
check(nevents(evframe()) == 0, "events left registered")
scan(db)
""")

case("even_createframe_throws", "throw")(r"""
__frameThrows = true
runCmd("")
check(ForeverSTUwaveDB.fscheck.ooc, "ooc snapshot should still be saved")
check(said("nothing armed"), "should say nothing is armed")
runCmd("")  -- not armed, so this is a fresh attempt, still no throw
runCmd("reset")
""")

case("secret_values_are_never_stored", "secret")(r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(db.combat, "combat snapshot missing")
fire("UNIT_SPELLCAST_CHANNEL_START", SS, SS, SN)
casts(10)
check(#db.casts == 10, "casts under secret args")
advance(30)
check(said("done, /reload"), "did not finish")
check(nevents(evframe()) == 0, "events left registered")
local s1 = scan(db)
check(s1.secretTrue > 50, "too few isSecret=true records: " .. s1.secretTrue)
local c = db.casts[1]
check(c.arg1.isSecret == true and c.arg2.isSecret == true and c.arg3.isSecret == true, "cast args not flagged secret")
check(c.arg1.type == "string" and c.arg3.type == "number", "cast arg types")
check(c.arg3.value == nil, "secret spellID value stored")
check(c.targetGUID.r1.isSecret == true, "GUID secrecy")
check(db.ooc.vitals.playerHealth.r1.isSecret == true and db.ooc.vitals.playerHealth.r1.type == "number", "health secrecy")
check(db.ooc.cooldowns.s686.cooldown.fields.startTime.isSecret == true, "cooldown field secrecy")
check(db.ooc.targetAuras.s589.byRank1ID.fields.spellId.isSecret == true, "aura field secrecy")
check(db.ooc.targetAuras.s589.byName.r1.isSecret == true, "secret aura table flagged, fields not read")
check(db.ooc.targetAuras.s589.byName.fields == nil, "fields read from a secret table")
check(db.channel[1].channelInfo.startTimeMs.isSecret == true, "channel info secrecy")
check(db.ooc.env.unitClass.r1.isSecret == true and db.ooc.env.unitClass.r1.value == nil, "class value stored")
""")

case("template_absent_is_recorded_and_skipped")(r"""
__template = false
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db.auracontainer.status == "absent: CustomAuraContainerTemplate", "status " .. tostring(db.auracontainer.status))
for _, f in ipairs(__frames) do check(f._kind ~= "AuraContainer", "AuraContainer created without the template") end
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
casts(10)
check(said("done, /reload"), "should finish without the aura test")
check(nevents(evframe()) == 0, "events left registered")
""")

case("container_creation_failure_is_recorded")(r"""
__acCreateThrows = true
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db.auracontainer.status == "create failed", "status " .. tostring(db.auracontainer.status))
check(type(db.auracontainer.steps.createFrame) == "string" and db.auracontainer.steps.createFrame ~= "ok", "create error missing")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
casts(10)
check(said("done, /reload"), "should finish after a failed container")
""")

case("unit_event_fallback_drops_foreign_units")(r"""
__unitEventThrows = true
runCmd("")
local f = evframe()
check(f._events.UNIT_SPELLCAST_SUCCEEDED == true, "fallback RegisterEvent not used")
fire("UNIT_SPELLCAST_SUCCEEDED", "party1", "c", 5)
check(ForeverSTUwaveDB.fscheck.casts == nil, "a foreign unit was recorded")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "c", 5)
check(#ForeverSTUwaveDB.fscheck.casts == 1, "player cast not recorded")
""")


case("aura_buttons_are_click_through")(r"""
runCmd("")
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
local button = __newFrame("Button", nil, ac)
ac._args.AddAuraGroup[3].initializeFrame(button)
check(button._args.SetMouseMotionEnabled and button._args.SetMouseMotionEnabled[1] == false, "button motion left enabled")
check(button._args.SetMouseClickEnabled and button._args.SetMouseClickEnabled[1] == false, "button clicks left enabled")
check(button._args.SetHideTooltipInCombat and button._args.SetHideTooltipInCombat[1] == true, "tooltip not hidden in combat")
-- the mouse is turned off BEFORE the button gets its icon, so it never takes a click first
for _, m in ipairs({ "SetMouseMotionEnabled", "SetMouseClickEnabled", "SetHideTooltipInCombat" }) do
    check(button._at[m] and button._at.SetIcon and button._at[m] < button._at.SetIcon, m .. " did not run before SetIcon")
end
local cd
for _, fr in ipairs(__frames) do if fr._kind == "Cooldown" then cd = fr end end
check(cd, "no cooldown child built")
check(cd._args.EnableMouse and cd._args.EnableMouse[1] == false, "cooldown mouse left enabled")
check(cd._args.EnableMouseMotion and cd._args.EnableMouseMotion[1] == false, "cooldown motion left enabled")
""")

case("aura_button_init_survives_missing_and_throwing_mouse_calls")(r"""
runCmd("")
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
local init = ac._args.AddAuraGroup[3].initializeFrame
local function variant(missing, throwing)
    local b = __newFrame("Button", nil, ac)
    local base = getmetatable(b).__index
    setmetatable(b, { __index = function(s, k)
        if k == missing then return nil end
        if k == throwing then return function() error("boom: " .. k) end end
        return base(s, k)
    end })
    init(b)
    return b
end
local b1 = variant("SetHideTooltipInCombat", nil)
check(b1._calls.SetIcon == 1 and b1._calls.SetDurationCooldown == 1 and b1._calls.SetDurationText == 1, "init stopped at a missing SetHideTooltipInCombat")
check(b1._calls.SetMouseMotionEnabled == 1 and b1._calls.SetMouseClickEnabled == 1, "the other mouse calls were skipped")
local b2 = variant(nil, "SetMouseClickEnabled")
check(b2._calls.SetIcon == 1 and b2._calls.SetDurationCooldown == 1 and b2._calls.SetDurationText == 1, "init stopped at a throwing SetMouseClickEnabled")
check(b2._calls.SetMouseMotionEnabled == 1 and b2._calls.SetHideTooltipInCombat == 1, "a throwing call stopped the next one")
local rec = ForeverSTUwaveDB.fscheck.auracontainer
check(rec.initError == nil and rec.initCalls == 2, "the swallowed failures leaked into initError: " .. tostring(rec.initError))
""")

case("combat_timer_fails_closed_when_the_lockdown_check_throws")(r"""
runCmd("")
__combat = true
fire("PLAYER_REGEN_DISABLED")
check(pendingTimers() == 1, "4s timer not scheduled")
__lockThrows = true
advance(4)
local db = ForeverSTUwaveDB.fscheck
check(db.combat, "combat snapshot skipped because InCombatLockdown threw (must fail closed)")
check((db.combat.combatSkips or 0) == 0, "a failed lockdown check was counted as a skip")
check(type(db.combat.env.inCombatLockdown.err) == "string", "the lockdown error was not recorded in the snapshot")
check(said("combat snapshot saved"), "combat line missing")
""")

case("arming_in_combat_is_refused")(r"""
__combat = true
runCmd("")
check(said("leave combat first"), "no refusal line")
check(ForeverSTUwaveDB == nil, "an ooc snapshot was taken in combat")
check(evframe() == nil and #__timers == 0, "armed in combat")
__combat = false
runCmd("")
check(ForeverSTUwaveDB.fscheck.ooc, "could not arm once out of combat")
""")

case("rerun_after_done_keeps_results")(r"""
complete()
local db = ForeverSTUwaveDB.fscheck
runCmd("")
check(said("results exist, /reload to save or /fscheck reset first"), "no results-exist line")
check(ForeverSTUwaveDB.fscheck == db and db.combat and #db.casts == 10, "results were wiped")
check(nevents(evframe()) == 0, "re-armed over finished results")
""")

case("saved_results_from_an_earlier_session_are_kept")(r"""
ForeverSTUwaveDB = { fscheck = { combat = { marker = true } } }
runCmd("")
check(said("results exist, /reload to save or /fscheck reset first"), "no results-exist line")
check(ForeverSTUwaveDB.fscheck.combat.marker == true, "saved combat results were wiped")
check(evframe() == nil, "armed over saved results")
runCmd("reset")
runCmd("")
check(ForeverSTUwaveDB.fscheck.ooc, "could not re-arm after reset")
""")

case("saved_channel_results_alone_are_kept")(r"""
ForeverSTUwaveDB = { fscheck = { channel = { { event = "marker" } } } }
runCmd("")
check(said("results exist, /reload to save or /fscheck reset first"), "a saved channel table was not counted as results")
check(ForeverSTUwaveDB.fscheck.channel[1].event == "marker", "saved channel results were wiped")
check(evframe() == nil, "armed over saved channel results")
""")

case("container_is_built_hidden_and_anchored_top_left")(r"""
runCmd("")
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check((ac._calls.Hide or 0) >= 1 and ac._shown == false, "container not hidden at build")
check(ac._args.SetPoint[1] == "TOPLEFT" and ac._args.SetPoint[4] == -100 and ac._args.SetPoint[5] == 200, "container not anchored TOPLEFT")
local label = _G.FSCheckAuraLabel
check(label and (label._calls.Hide or 0) >= 1 and label._shown == false, "label not hidden at build")
""")

case("reset_disables_container")(r"""
runCmd("")
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
runCmd("reset")
check(ac._args.SetEnabled and ac._args.SetEnabled[1] == false, "reset did not SetEnabled(false)")
""")

case("rearm_reuses_container_and_label")(r"""
runCmd("")
runCmd("reset")
runCmd("")
check(ForeverSTUwaveDB.fscheck.auracontainer.steps.createFrame == "reused", "container not reused")
local containers, labels = 0, 0
for _, fr in ipairs(__frames) do
    if fr._kind == "AuraContainer" then containers = containers + 1 end
    if fr._name == "FSCheckAuraLabel" then labels = labels + 1 end
end
check(containers == 1, "containers built: " .. containers)
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check(ac._calls.AddAuraGroup == 1, "AddAuraGroup called " .. tostring(ac._calls.AddAuraGroup) .. " times across reset + re-arm")
check(ForeverSTUwaveDB.fscheck.auracontainer.steps.addAuraGroup == "reused", "re-arm did not record the group as reused")
check(labels == 1, "labels built: " .. labels)
check(nevents(evframe()) == 9, "re-arm did not re-register (REGEN, SUCCEEDED, START, 3 cast ends, 3 channel)")
""")

case("retarget_refreshes_row_only_while_live")(r"""
runCmd("")
local f = evframe()
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check(f._events.PLAYER_TARGET_CHANGED == nil, "target event registered before the row is live")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(f._events.PLAYER_TARGET_CHANGED == true, "target event not registered while the row is live")
check(ac._calls.SetUnit == 1, "row not seeded")
check((ac._calls.UpdateAllAuras or 0) == 0, "UpdateAllAuras called before any retarget")
fire("PLAYER_TARGET_CHANGED")
check(ac._calls.SetUnit == 2 and ac._args.SetUnit[1] == "target", "retarget did not call SetUnit")
-- SetUnit("target") with the token unchanged is a no-op in Blizzard's container, so the
-- retarget only really refreshes through UpdateAllAuras.
check(ac._unitChanges == 1, "the mock SetUnit should have re-pointed only once")
check(ac._calls.UpdateAllAuras == 1, "retarget did not call UpdateAllAuras (SetUnit alone is a no-op for the same token)")
-- a container without UpdateAllAuras must not break the retarget path
local saved = __ACM.UpdateAllAuras
__ACM.UpdateAllAuras = nil
fire("PLAYER_TARGET_CHANGED")
check(ac._calls.SetUnit == 3 and ac._calls.UpdateAllAuras == 1, "retarget without UpdateAllAuras misbehaved")
check(ForeverSTUwaveDB.fscheck.meta.lastError == nil and ForeverSTUwaveDB.fscheck.auracontainer.retargetErrors == nil, "missing UpdateAllAuras was recorded as an error")
__ACM.UpdateAllAuras = saved
-- a present UpdateAllAuras that throws must not escape the handler, but is counted
__ACM.UpdateAllAuras = function() error("boom") end
fire("PLAYER_TARGET_CHANGED")
check(ac._calls.SetUnit == 4, "retarget handler did not complete when UpdateAllAuras threw")
check(ForeverSTUwaveDB.fscheck.meta.lastError == nil, "a throwing UpdateAllAuras leaked into lastError")
check(ForeverSTUwaveDB.fscheck.auracontainer.retargets == 3, "retarget not recorded when UpdateAllAuras threw")
check(ForeverSTUwaveDB.fscheck.auracontainer.retargetErrors == 1, "a throwing UpdateAllAuras was not counted in retargetErrors")
__ACM.UpdateAllAuras = saved
advance(30)
check(f._events.PLAYER_TARGET_CHANGED == nil, "target event left registered after the row ended")
fire("PLAYER_TARGET_CHANGED")
check(ac._calls.SetUnit == 4 and ac._calls.UpdateAllAuras == 1, "a stale retarget touched the hidden row")
""")


WL_IDS = (
    "{21562, 1459, 6673, 1126, 2823, 8679, 3408, 5761, 17941, 15473, 706, 1243, 589, 594, 980, 172, "
    "348, 18265, 687, 5019}"
)

case("w1_whitelist_is_recorded_in_both_snapshots")(
    r"""
local IDS = """
    + WL_IDS
    + r"""
local function checkWl(wl, label)
    check(wl, label .. " whitelist missing")
    for _, id in ipairs(IDS) do
        local e = wl["s" .. id]
        check(e, label .. " entry missing for " .. id)
        for _, k in ipairs({ "aura", "cast", "cooldown" }) do
            local r = e[k] and e[k].r1
            check(r and r.type == "number" and r.isSecret == false and r.value == 0, label .. " " .. id .. " " .. k)
        end
    end
end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
checkWl(db.ooc.whitelist, "ooc")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
checkWl(db.combat.whitelist, "combat")
-- a function missing at runtime is recorded as absent, the others still run
runCmd("reset")
__combat = false
C_Secrets.GetSpellCastSecrecy = nil
runCmd("")
local wl = ForeverSTUwaveDB.fscheck.ooc.whitelist
check(wl.s21562.cast.exists == false and wl.s21562.aura.r1.value == 0, "absent cast secrecy not recorded as absent")
"""
)

case("w1_whitelist_secret_values_are_not_stored", "secret")(
    r"""
local IDS = """
    + WL_IDS
    + r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
for _, snap in ipairs({ db.ooc, db.combat }) do
    for _, id in ipairs(IDS) do
        for _, k in ipairs({ "aura", "cast", "cooldown" }) do
            local r = snap.whitelist["s" .. id][k].r1
            check(r.isSecret == true and r.type == "number" and r.value == nil, snap.kind .. " " .. id .. " " .. k .. " stored a secret")
        end
    end
end
scan(db)
"""
)

case("a2_unit_aura_payload_plain")(
    r"""
runCmd("")
local x = xframe()
check(x and x._events.UNIT_AURA == "unit:player,target", "UNIT_AURA not registered for player and target")
local info = { isFullUpdate = false, addedAuras = { {}, {} }, updatedAuraInstanceIDs = { 1, 2, 3 }, removedAuraInstanceIDs = {} }
__combat = true
fire("UNIT_AURA", "player", info)
__combat = false
fire("UNIT_AURA", "target", { isFullUpdate = true })
fire("UNIT_AURA", "party1", info)
local a = ForeverSTUwaveDB.fscheck.unitAura
check(a and #a == 2, "foreign unit recorded or events missing: " .. tostring(a and #a))
local r1 = a[1]
check(r1.event == "UNIT_AURA" and r1.unit.value == "player" and r1.unit.isSecret == false, "unit arg")
check(r1.info.type == "table" and r1.info.isSecret == false, "info secrecy")
check(r1.inCombatLockdown.r1.value == true and a[2].inCombatLockdown.r1.value == false, "combat flag")
check(r1.time.r1.type == "number" and r1.time.r1.value == __now and a[2].time.r1.type == "number", "aura time not recorded")
check(r1.fields.isFullUpdate.value == false and r1.fields.isFullUpdate.type == "boolean", "isFullUpdate")
check(r1.fields.addedAuras.count == 2 and r1.fields.addedAuras.type == "table", "added count")
check(r1.fields.updatedAuraInstanceIDs.count == 3 and r1.fields.removedAuraInstanceIDs.count == 0, "id counts")
check(a[2].fields.isFullUpdate.value == true and a[2].fields.addedAuras.type == "nil" and a[2].fields.addedAuras.count == nil, "missing field")
-- out of combat the cap is 5: 1 combat + 1 ooc already recorded, so 3 more ooc fit and the rest drop
for i = 1, 30 do fire("UNIT_AURA", "player", info) end
check(#a == 1 + 5, "out-of-combat cap: " .. #a)
check(x._events.UNIT_AURA == true or x._events.UNIT_AURA == "unit:player,target", "UNIT_AURA dropped while the combat budget is unspent")
-- the combat budget (10) is still whole
__combat = true
for i = 1, 30 do fire("UNIT_AURA", "player", info) end
check(#a == 5 + 10, "combat cap: " .. #a)
check(x._events.UNIT_AURA == nil, "UNIT_AURA left registered after both caps")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
casts(10)
advance(30)
check(nevents(x) == 0, "extra frame events left registered after done")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("a2_ooc_events_cannot_spend_the_combat_budget")(
    r"""
runCmd("")
local x = xframe()
for i = 1, 40 do fire("UNIT_AURA", "player", { isFullUpdate = false }) end
local a = ForeverSTUwaveDB.fscheck.unitAura
check(#a == 5, "ooc events recorded: " .. #a)
__combat = true
fire("UNIT_AURA", "target", { isFullUpdate = false })
check(#a == 6 and a[6].inCombatLockdown.r1.value == true, "the first combat event was dropped after an ooc flood")
for i = 1, 20 do fire("UNIT_AURA", "player", { isFullUpdate = false }) end
check(#a == 15, "total cap: " .. #a)
"""
)

case("a2_table_secret_by_issecrettable_only_is_never_indexed")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
-- issecretvalue says plain, issecrettable says secret: indexing it would raise SECRET_OP.
check(issecretvalue(STT) == false and issecrettable(STT) == true, "mock sentinel is wrong")
fire("UNIT_AURA", "player", STT)
local r = db.unitAura[1]
check(r.info.type == "table" and r.info.isSecret == false and r.info.issecrettable == true, "issecrettable not recorded")
check(r.fields == nil, "a secret table was indexed")
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("a2_secret_payload_table_is_never_indexed", "secret")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
-- Every operation on ST raises SECRET_OP, and a swallowed one would leave that text in the saved errors.
fire("UNIT_AURA", SS, ST)
fire("UNIT_AURA", "player", ST)
fire("UNIT_AURA", "target", { isFullUpdate = SB, addedAuras = ST, updatedAuraInstanceIDs = ST, removedAuraInstanceIDs = ST })
local a = db.unitAura
check(a and #a == 3, "events not recorded")
check(a[1].unit.isSecret == true and a[1].unit.value == nil, "secret unit stored")
check(a[1].info.isSecret == true and a[1].info.type == "table" and a[1].fields == nil, "secret table was read")
check(a[2].info.isSecret == true and a[2].fields == nil, "secret table was read (plain unit)")
local f = a[3].fields
check(a[3].info.isSecret == false, "plain table flagged secret")
check(f.isFullUpdate.isSecret == true and f.isFullUpdate.type == "boolean" and f.isFullUpdate.value == nil, "secret boolean stored")
for _, k in ipairs({ "addedAuras", "updatedAuraInstanceIDs", "removedAuraInstanceIDs" }) do
    check(f[k].isSecret == true and f[k].type == "table" and f[k].count == nil, k .. " counted while secret")
end
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("p1_proc_glow_events_are_capped")(
    r"""
runCmd("")
local x = xframe()
local SHOW, HIDE = "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE"
check(x._events[SHOW] == true and x._events[HIDE] == true, "glow events not registered")
for i = 1, 25 do fire(i % 2 == 1 and SHOW or HIDE, 17941) end
local pg = ForeverSTUwaveDB.fscheck.procGlow
check(#pg == 20, "event cap: " .. #pg)
check(pg[1].event == SHOW and pg[2].event == HIDE, "event names")
check(pg[1].spellID.value == 17941 and pg[1].spellID.isSecret == false, "plain spellID kept")
check(pg[1].inCombatLockdown.r1.type == "boolean" and pg[1].inCombatLockdown.r1.value == false, "proc combat flag")
check(pg[1].time.r1.type == "number" and pg[1].time.r1.value == __now, "proc time")
check(x._events[SHOW] == nil and x._events[HIDE] == nil, "glow events left registered after the cap")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
local o = ForeverSTUwaveDB.fscheck.combat.spellOverlay
check(o.shadowTranceOverlayed.r1.type == "boolean" and o.shadowTranceOverlayed.r1.value == false, "17941 overlay not in the combat snapshot")
check(o.shadowBoltOverlayed.r1.type == "boolean", "686 overlay missing")
"""
)

case("p1_secret_glow_spellid_is_not_stored", "secret")(
    r"""
runCmd("")
fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", SN)
local pg = ForeverSTUwaveDB.fscheck.procGlow
check(#pg == 1 and pg[1].spellID.isSecret == true and pg[1].spellID.type == "number" and pg[1].spellID.value == nil, "secret spellID stored")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("gcd_section_and_isactive_after_a_cast")(
    r"""
C_Spell.GetSpellCooldown = function()
    return { startTime = 1, duration = 1.5, isEnabled = true, isActive = true, modRate = 1, isOnGCD = true }
end
runCmd("")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
local db = ForeverSTUwaveDB.fscheck
for _, id in ipairs({ 61304, 686, 585 }) do
    local e = db.combat.gcd["s" .. id]
    check(e and e.cooldown.fields.isActive.type == "boolean" and e.cooldown.fields.startTime.isSecret == false, "gcd fields " .. id)
    check(e.hasIsOnGCD == true and e.cooldown.fields.isOnGCD.type == "boolean" and e.cooldown.fields.isOnGCD.isSecret == false, "isOnGCD flag " .. id)
    -- the section keeps the plain values it reads
    local f = e.cooldown.fields
    check(f.isActive.value == true and f.isOnGCD.value == true and f.startTime.value == 1 and f.duration.value == 1.5,
        "gcd section stored no values for " .. id)
    check(f.modRate.value == nil and f.isEnabled.value == nil, "gcd section kept a field it should not")
end
-- 585 and 686 are known in the mock, in that order. A check never reads the spell just cast
-- (its own cooldown would pollute the read), so a Shadow Bolt cast checks Smite ...
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.spellId == 585, "check spell: " .. tostring(g.spellId))
check(g.isActive.value == true and g.isActive.isSecret == false and g.isOnGCD.value == true, "isActive not captured after the cast")
-- ... and a Smite cast checks Shadow Bolt
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 585)
check(db.casts[2].gcd.spellId == 686 and db.casts[2].gcd.isActive.value == true, "second cast not checked with the other spell")
-- the control read of the GCD marker (61304) rides in the same sample
local c = g.control
check(c and c.isActive.value == true and c.startTime.value == 1 and c.duration.value == 1.5, "control read missing")
check(c.time.r1.type == "number" and c.time.r1.value == __now, "control GetTime missing")
-- castTime comes from GetSpellInfo while it is plain
check(g.castTime.source == "spellinfo" and g.castTime.value == 2500, "castTime from spell info")
-- a check spell is never the cast spell, even when it is the only one known
runCmd("reset")
__combat = false
KNOWN_ONLY(686)
runCmd("")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-3", 686)
local g3 = ForeverSTUwaveDB.fscheck.casts[1].gcd
check(g3.spellId == nil and g3.skipped ~= nil and g3.control and g3.control.isActive.value == true,
    "the cast spell was checked, or the control read was lost")
"""
)

case("gcd_check_skips_a_spell_that_has_its_own_cooldown")(
    r"""
-- Mind Blast (8092) has an 8s cooldown of its own, so it is not a GCD check candidate
IsPlayerSpell = function() return true end
C_SpellBook.IsSpellKnown = IsPlayerSpell
runCmd("")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 172)
check(ForeverSTUwaveDB.fscheck.casts[1].gcd.spellId == 585, "first candidate: " .. tostring(ForeverSTUwaveDB.fscheck.casts[1].gcd.spellId))
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 585)
check(ForeverSTUwaveDB.fscheck.casts[2].gcd.spellId == 686, "after a Smite: " .. tostring(ForeverSTUwaveDB.fscheck.casts[2].gcd.spellId))
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-3", 8092)
local id = ForeverSTUwaveDB.fscheck.casts[3].gcd.spellId
check(id == 585, "Mind Blast cast checked " .. tostring(id))
"""
)

case("gcd_is_also_sampled_when_a_cast_starts")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_START", "party1", "Cast-x", 686)
check(db.gcdStart == nil, "a foreign unit START was recorded")
fire("UNIT_SPELLCAST_START", "player", "Cast-1", 686)
fire("UNIT_SPELLCAST_START", "player", "Cast-s", 5019)
check(db.casts == nil and db.shoot == nil, "START counted as a cast, or Shoot START recorded")
check(db.gcdStart and #db.gcdStart == 1, "START sample missing")
local r = db.gcdStart[1]
check(r.event == "UNIT_SPELLCAST_START" and r.arg3.value == 686 and r.time.r1.type == "number", "START record")
check(r.gcd.spellId == 585 and r.gcd.isActive.value == false and r.gcd.control.isActive.value == false, "START gcd sample")
check(r.gcd.castTime.source == "spellinfo" and r.gcd.castTime.value == 2500, "START castTime")
for i = 1, 20 do fire("UNIT_SPELLCAST_START", "player", "c" .. i, 686) end
check(#db.gcdStart == 10, "START cap: " .. #db.gcdStart)
"""
)

case("gcd_cast_time_falls_back_to_start_to_succeeded_elapsed")(
    r"""
-- spell info castTime is secret, so the elapsed time between START and SUCCEEDED stands in
C_Spell.GetSpellInfo = function(a) return { name = "Shadow Bolt", spellID = 686, castTime = SN } end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_START", "player", "Cast-1", 686)
advance(2.5)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local ct = db.casts[1].gcd.castTime
check(ct.source == "elapsed" and ct.value == 2.5, "elapsed castTime: " .. tostring(ct.source) .. " " .. tostring(ct.value))
-- an instant cast with no START has neither
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 686)
check(db.casts[2].gcd.castTime.source == "none" and db.casts[2].gcd.castTime.value == nil, "castTime invented")
-- a START for a different spell is not that cast's start
fire("UNIT_SPELLCAST_START", "player", "Cast-3", 585)
advance(1)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-4", 686)
check(db.casts[3].gcd.castTime.source == "none", "a stale START of another spell was used")
scan(db)
"""
)

case("aura_nested_count_is_not_taken_from_a_table_issecrettable_calls_secret")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
-- the info table is plain; its nested fields are tables issecretvalue clears but issecrettable
-- does not (Lua 5.1 ignores __len on a table, so # would silently report 0 instead of raising)
fire("UNIT_AURA", "player", { isFullUpdate = false, addedAuras = STT, updatedAuraInstanceIDs = STT, removedAuraInstanceIDs = STT })
local f = db.unitAura[1].fields
check(f and f.isFullUpdate, "plain info table was not read")
for _, k in ipairs({ "addedAuras", "updatedAuraInstanceIDs", "removedAuraInstanceIDs" }) do
    check(f[k] and f[k].count == nil, "a count was recorded for " .. k)
end
-- a plain nested table still gets its count
fire("UNIT_AURA", "player", { isFullUpdate = false, addedAuras = { {}, {} } })
check(db.unitAura[2].fields.addedAuras.count == 2, "plain nested count lost")
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("stale_start_does_not_produce_a_bogus_elapsed_cast_time")(
    r"""
C_Spell.GetSpellInfo = function(a) return { name = "Shadow Bolt", spellID = 686, castTime = SN } end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
local f = evframe()
for _, e in ipairs({ "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }) do
    check(f._events[e] == "unit:player", e .. " not registered as a player unit event")
end
-- a START that never succeeds, then a later instant cast of the same spell
fire("UNIT_SPELLCAST_START", "player", "Cast-1", 686)
advance(600)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 686)
check(db.casts[1].gcd.castTime.source == "none", "a 600s elapsed castTime was recorded: " .. tostring(db.casts[1].gcd.castTime.value))
-- every way a cast ends without succeeding clears the remembered START
local n = 1
for _, e in ipairs({ "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED" }) do
    n = n + 1
    fire("UNIT_SPELLCAST_START", "player", "S" .. n, 686)
    fire(e, "player", "S" .. n, 686)
    advance(1)
    fire("UNIT_SPELLCAST_SUCCEEDED", "player", "T" .. n, 686)
    check(db.casts[n].gcd.castTime.source == "none", e .. " did not clear the START")
end
-- a foreign unit's STOP leaves the player's START alone
fire("UNIT_SPELLCAST_START", "player", "S9", 686)
fire("UNIT_SPELLCAST_STOP", "party1", "S9", 686)
advance(2)
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "T9", 686)
check(db.casts[5].gcd.castTime.source == "elapsed" and db.casts[5].gcd.castTime.value == 2, "a foreign STOP cleared the START")
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("note_table_fails_closed_when_issecrettable_throws")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
__issecrettableThrows = true
-- the aura info table is plain to issecretvalue, but the secrecy check blew up: count it as secret
fire("UNIT_AURA", "player", { isFullUpdate = false })
local r = db.unitAura[1]
check(r.info.issecrettable == true, "a throwing issecrettable was not recorded as secret")
check(r.fields == nil, "a table whose secrecy check threw was indexed")
-- the same rule for the cooldown tables of the GCD check
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.isActive == nil and g.control.isActive == nil, "a cooldown table whose secrecy check threw was indexed")
__issecrettableThrows = false
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("note_table_treats_a_missing_issecrettable_as_plain")(
    r"""
issecrettable = nil
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_AURA", "player", { isFullUpdate = false, addedAuras = { {} } })
local r = db.unitAura[1]
check(r.info.issecrettable == nil, "issecrettable recorded without the API")
check(r.fields and r.fields.isFullUpdate and r.fields.addedAuras.count == 1, "a plain table was not read without issecrettable")
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("gcd_known_list_is_retried_after_an_empty_result")(
    r"""
IsPlayerSpell = function() return false end
C_SpellBook.IsSpellKnown = IsPlayerSpell
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
check(db.casts[1].gcd.skipped == "no known spell", "nothing was known yet")
-- the spellbook loads later: the empty list must not have been cached
IsPlayerSpell = function() return true end
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 686)
check(db.casts[2].gcd.spellId == 585, "empty known list was cached: " .. tostring(db.casts[2].gcd.spellId) .. " " .. tostring(db.casts[2].gcd.skipped))
scan(db)
"""
)

case("gcd_check_skips_the_cast_spell_when_its_name_is_unavailable")(
    r"""
-- the cast spell's own name cannot be read, so the name compare alone would pick it
local oldName, oldInfo = C_Spell.GetSpellName, C_Spell.GetSpellInfo
C_Spell.GetSpellName = function(id) if id == 585 then return nil end return oldName(id) end
C_Spell.GetSpellInfo = function(id) if id == 585 then return nil end return oldInfo(id) end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 585)
check(db.casts[1].gcd.spellId == 686, "checked the cast spell itself: " .. tostring(db.casts[1].gcd.spellId))
scan(db)
"""
)

case("gcd_check_with_a_secret_cooldown_table_stores_nothing", "plain")(
    r"""
C_Spell.GetSpellCooldown = function() return ST end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.spellId == 585 and g.call.r1.isSecret == true, "check call not recorded as secret")
check(g.isActive == nil and g.isOnGCD == nil, "a secret cooldown table was read")
check(g.control.call.r1.isSecret == true and g.control.isActive == nil and g.control.startTime == nil, "control read indexed a secret table")
local sec = db.ooc.gcd.s61304.cooldown
check(sec.fields == nil, "section read fields of a secret table")
check(db.meta.lastError == nil, "handler error: " .. tostring(db.meta.lastError))
scan(db)
"""
)

case("gcd_cooldown_table_secret_by_issecrettable_only_is_not_indexed")(
    r"""
C_Spell.GetSpellCooldown = function() return STT end
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.isActive == nil and g.control.isActive == nil, "indexed a table issecrettable calls secret")
scan(db)
"""
)

case("gcd_isactive_unknown_or_secret_is_not_stored", "secret")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
check(db.casts[1].gcd.skipped == "no known spell", "unknown spells should skip the check")
check(db.casts[1].gcd.control and db.casts[1].gcd.control.isActive.isSecret == true, "control read should still be taken")
runCmd("reset")
IsPlayerSpell = function() return true end
runCmd("")
db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.spellId == 585, "first candidate should win: " .. tostring(g.spellId))
check(g.isActive.isSecret == true and g.isActive.type == "boolean" and g.isActive.value == nil, "secret isActive stored")
check(g.control.isActive.isSecret == true and g.control.isActive.value == nil and g.control.startTime.value == nil, "secret control stored")
check(g.castTime.source == "none", "a secret castTime was kept")
fire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, SN)
check(db.casts[2].gcd.spellId == 585, "a secret cast id should not exclude any spell")
scan(db)
"""
)

case("pet_exists_is_recorded_with_its_secrecy")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db.ooc.pet.unitExists.r1.value == true and db.ooc.pet.unitExists.r1.isSecret == false, "pet exists")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(db.combat.pet.unitExists.r1.type == "boolean", "pet missing from the combat snapshot")
runCmd("reset")
__combat = false
UnitExists = function() return SB end
runCmd("")
local r = ForeverSTUwaveDB.fscheck.ooc.pet.unitExists.r1
check(r.isSecret == true and r.type == "boolean" and r.value == nil, "secret pet existence stored")
"""
)

case("shoot_events_go_to_their_own_capped_list")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
for i = 1, 3 do fire("UNIT_SPELLCAST_SUCCEEDED", "player", "s" .. i, 5019) end
fire("UNIT_SPELLCAST_CHANNEL_START", "player", "c1", 5019)
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "c1", 5019)
fire("UNIT_SPELLCAST_CHANNEL_STOP", "player", "c1", 5019)
check(db.casts == nil and db.channel == nil, "Shoot was counted as a cast or channel")
check(#db.shoot == 6, "shoot events: " .. #db.shoot)
check(db.shoot[4].event == "UNIT_SPELLCAST_CHANNEL_START" and db.shoot[4].arg3.value == 5019, "shoot channel record")
check(db.shoot[4].time.r1.type == "number" and db.shoot[1].time.r1.type == "number", "shoot time")
for i = 1, 6 do check(db.shoot[i].gcd == nil, "Shoot event " .. i .. " got a GCD check") end
for i = 1, 20 do fire("UNIT_SPELLCAST_SUCCEEDED", "player", "m" .. i, 5019) end
check(#db.shoot == 12, "shoot cap: " .. #db.shoot)
casts(10)
check(#db.casts == 10 and said("cast recorder saved"), "casts should still reach 10 after Shoot spam")
"""
)

case("channel_start_update_stop_record_secrecy_and_time")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
fire("UNIT_SPELLCAST_CHANNEL_START", "player", "c", 15407)
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "c", 15407)
fire("UNIT_SPELLCAST_CHANNEL_STOP", "player", "c", 15407)
check(#db.channel == 3, "channel events: " .. #db.channel)
check(db.channel[1].event:sub(-5) == "START" and db.channel[2].event:sub(-6) == "UPDATE" and db.channel[3].event:sub(-4) == "STOP", "event order")
for i = 1, 3 do
    check(db.channel[i].arg1.isSecret == false and db.channel[i].time.r1.type == "number", "arg secrecy or time " .. i)
end
"""
)


case("rearm_after_reset_zeroes_the_aura_proc_and_shoot_counters")(
    r"""
local SHOW = "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW"
local function flood()
    for i = 1, 40 do
        fire("UNIT_AURA", "player", { isFullUpdate = false })
        fire(SHOW, 17941)
        fire("UNIT_SPELLCAST_SUCCEEDED", "player", "s" .. i, 5019)
    end
end
runCmd("")
flood()
local db = ForeverSTUwaveDB.fscheck
check(#db.unitAura == 5 and #db.procGlow == 20 and #db.shoot == 12, "first run caps: " .. #db.unitAura .. "/" .. #db.procGlow .. "/" .. #db.shoot)
__combat = true
for i = 1, 20 do fire("UNIT_AURA", "player", { isFullUpdate = false }) end
check(#db.unitAura == 15, "first run combat cap: " .. #db.unitAura)
runCmd("reset")
__combat = false
runCmd("")
local x = xframe()
check(x._events.UNIT_AURA == "unit:player,target" and x._events[SHOW] == true, "extra events not re-registered")
flood()
db = ForeverSTUwaveDB.fscheck
check(#db.unitAura == 5, "aura counter not reset: " .. #db.unitAura)
check(#db.procGlow == 20, "proc counter not reset: " .. #db.procGlow)
check(#db.shoot == 12, "shoot counter not reset: " .. #db.shoot)
-- the combat aura budget is whole again too
__combat = true
for i = 1, 20 do fire("UNIT_AURA", "player", { isFullUpdate = false }) end
check(#db.unitAura == 15, "combat aura counter not reset: " .. #db.unitAura)
"""
)

case("register_errors_are_all_kept", "plain")(
    r"""
__unitEventThrows = true
__registerThrows = true
runCmd("")
local e = ForeverSTUwaveDB.fscheck.meta.registerError
check(type(e) == "string", "no registerError recorded")
-- first and last failing registrations are both in the text, not just the last one
check(string.find(e, "UNIT_SPELLCAST_SUCCEEDED", 1, true), "first register error overwritten: " .. e)
check(string.find(e, "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", 1, true), "last register error missing: " .. e)
check(#e < 1200, "registerError grew without a cap: " .. #e)
check(ForeverSTUwaveDB.fscheck.meta.lastError == nil, "arming threw: " .. tostring(ForeverSTUwaveDB.fscheck.meta.lastError))
"""
)


case("gunsight_plain_run_stores_every_check_with_plain_values")(
    r"""
runCmd("gunsight")
local gs = ForeverSTUwaveDB.fscheck.gunsight
for _, k in ipairs({ "meta", "texcoord8", "vertexColorFromBoolean", "verticalBarTimer", "line", "auraApi",
                     "auraContainer", "alphaFromBoolean" }) do
    check(type(gs[k]) == "table", "missing check " .. k)
end
check(gs.meta.buildVersion == "12.1.0" and gs.meta.buildNumber == "65000", "build info is not the plain version pair")
check(gs.meta.checkError == nil and gs.auraContainer.checkError == nil, "a check threw")
check(type(gs.auraContainer.summary) == "string" and said("gunsight auraContainer:"), "no one-line summary")
check(gs.auraContainer.frameType == "ok" and gs.auraContainer.templateAccepted == true, "container not built")
check(gs.auraContainer.addAuraGroup == "ok" and gs.auraContainer.setUnit == "ok", "group or unit refused")
scan(ForeverSTUwaveDB.fscheck)
noOnUpdate()
"""
)

case("gunsight_rerun_creates_no_new_objects_and_hides_them_all")(
    r"""
gsMockContainer(3)
C_DurationUtil = { CreateDuration = function() return { SetTimeFromStart = function() end } end }
runCmd("gunsight")
advance(1)
allHidden()
local created, frames = __created, #__frames
for _ = 1, 3 do
    runCmd("gunsight")
    advance(1)
end
check(__created == created, "re-running created " .. (__created - created) .. " new frames or textures")
check(#__frames == frames, "re-running created " .. (#__frames - frames) .. " new CreateFrame frames")
check(FSCheckGsAuraContainer._calls.AddAuraGroup == 1, "the group was added again on a re-run")
check(ForeverSTUwaveDB.fscheck.gunsight.auraContainer.addAuraGroup == "reused", "re-run did not reuse the group")
allHidden()
"""
)

case("gunsight_hides_the_bar_when_there_is_no_create_duration")(
    r"""
runCmd("gunsight")
allHidden()
check(ForeverSTUwaveDB.fscheck.gunsight.verticalBarTimer.manual.skipped ~= nil, "no skip recorded")
"""
)

case("gunsight_hides_the_bar_when_create_duration_throws")(
    r"""
C_DurationUtil = { CreateDuration = function() error("boom: CreateDuration") end }
runCmd("gunsight")
allHidden()
check(string.find(ForeverSTUwaveDB.fscheck.gunsight.verticalBarTimer.manual.skipped, "threw", 1, true), "throw not recorded")
"""
)

case("gunsight_hides_the_bar_when_the_run_is_superseded")(
    r"""
C_DurationUtil = { CreateDuration = function() return { SetTimeFromStart = function() end } end }
runCmd("gunsight")
runCmd("gunsight")   -- before the first run's 0.5s sample: its timer is now stale
advance(1)
allHidden()
local m = ForeverSTUwaveDB.fscheck.gunsight.verticalBarTimer.manual
check(m.valueAt05 ~= nil, "the live run was not sampled (a stale timer hid or consumed its bar)")
"""
)

case("gunsight_hides_the_cast_bar_after_a_real_cast")(
    r"""
UnitCastingDuration = function() return { kind = "cast" } end
runCmd("gunsight")
check(evframe()._events.UNIT_SPELLCAST_START == "unit:player", "cast not armed")
fire("UNIT_SPELLCAST_START", "player", "Cast-1", 686)
advance(1)
allHidden()
check(ForeverSTUwaveDB.fscheck.gunsight.verticalBarTimer.cast.setTimerDuration == "ok", "cast duration not fed to the bar")
"""
)

case("gunsight_secret_first_aura_id_is_described_not_compared")(
    r"""
local gotSecretId = false
C_UnitAuras.GetUnitAuraInstanceIDs = function() return { SN } end
C_UnitAuras.GetAuraDuration = function(_, id)
    gotSecretId = rawequal(id, SN)
    return { kind = "duration" }
end
runCmd("gunsight")
local ids = ForeverSTUwaveDB.fscheck.gunsight.auraApi.ooc.ids
check(ids.firstIdSecret == true and ids.firstIdType == "number" and ids.firstId == "secret",
    "first id: " .. tostring(ids.firstIdSecret) .. " " .. tostring(ids.firstIdType) .. " " .. tostring(ids.firstId))
check(gotSecretId, "the secret id was not passed on to GetAuraDuration")
check(ForeverSTUwaveDB.fscheck.gunsight.auraApi.ooc.durationOk == true, "duration read skipped for a secret id")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("gunsight_combat_target_exists_false_is_recorded_as_false")(
    r"""
UnitExists = function() return false end
runCmd("gunsight")
pull(2)
for _ = 1, 10 do advance(2) end
local c = ForeverSTUwaveDB.fscheck.gunsight.auraApi.combat
check(c and c.targetExists == false, "targetExists: " .. tostring(c and c.targetExists))
check(c.gaveUp == true, "did not give up after the attempts")
"""
)

case("gunsight_aura_container_engine_window_records_types_forwards_and_hides")(
    r"""
gsMockContainer(3)
local SECRET_DURATION = ST
runCmd("gunsight")
local rec = ForeverSTUwaveDB.fscheck.gunsight.auraContainer
check(rec.initCalls == 3, "init callbacks: " .. tostring(rec.initCalls))
for _, step in ipairs({ "icon", "cooldown", "cooldownHook", "durationText", "applicationCount", "durationBar", "barHook" }) do
    check(rec.initSteps[step] == "ok", "init step " .. step .. ": " .. tostring(rec.initSteps[step]))
end
pull(2)
local container = FSCheckGsAuraContainer
check(container._shown == true and container._unit == "target", "container not pointed at the target and shown")
local cooldowns, bars = engineCalls(SECRET_DURATION)
check(cooldowns == 3 and bars == 3, "mock engine calls: " .. cooldowns .. " " .. bars)
advance(0.5)
advance(0.5)
local c = ForeverSTUwaveDB.fscheck.gunsight.auraContainer.combat
check(c.sampleError == nil and c.heightError == nil, "sample failed: " .. tostring(c.sampleError or c.heightError))
check(c.buttons.shown == 3 and c.buttons.children == 3 and c.allocated == 3, "button counts")
check(c.cooldownHook.calls == 3 and c.cooldownHook.args == "table:secret,boolean:plain", "cooldown hook: " .. tostring(c.cooldownHook.args))
check(c.barHook.calls == 3 and c.barHook.args == "table:secret,number:plain,number:plain", "bar hook: " .. tostring(c.barHook.args))
check(c.barHook.forwardStep == "ok", "engine duration not forwarded: " .. tostring(c.barHook.forwardStep))
check(c.buttonDuration.call == "ok" and c.buttonDuration.forwardStep == "ok", "button duration route")
check(c.engineBars.visible == 3 and c.engineBars.filled == 3 and c.engineBars.maxHeight == 7, "engine bar heights")
check(c.fed.hook.height == 7 and c.fed.get.height == 7, "forwarded bar heights")
check(container._shown == false, "container left shown")
allHidden()
check(said("gunsight auraContainer: combat: 3 of 3 children shown"), "combat summary line missing")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("gunsight_aura_container_with_secret_values_stores_only_plain_data", "secret")(
    r"""
local buttons = gsMockContainer(3)
__FrameM.GetStatusBarTexture = function() return { GetHeight = function() return SN end } end
runCmd("gunsight")
buttons[1].IsShown = function() return SB end
pull(2)
engineCalls(ST)
for _, b in ipairs(buttons) do b.GetAuraDuration = function() return ST end end
advance(0.5)
advance(0.5)
local c = ForeverSTUwaveDB.fscheck.gunsight.auraContainer.combat
check(c.sampleError == nil and c.heightError == nil, "sample failed: " .. tostring(c.sampleError or c.heightError))
check(c.buttons.shown == 2 and c.buttons.unknown == 1, "a secret IsShown must count as unknown")
check(c.buttonDuration.secret == true and c.buttonDuration.type == "table", "secret duration not described")
check(c.engineBars.secret == 3 and c.engineBars.maxHeight == nil, "secret heights must not be stored")
check(c.fed.hook.height == "secret" and c.fed.get.height == "secret", "fed heights: " .. tostring(c.fed.hook.height))
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("gunsight_combat_end_before_capture_hides_the_container")(
    r"""
gsMockContainer(2)
UnitExists = function() return false end
runCmd("gunsight")
pull(2)
check(FSCheckGsAuraContainer._shown == true, "container not shown on the pull")
__combat = false
advance(2)
check(FSCheckGsAuraContainer._shown == false, "container left shown after combat ended")
allHidden()
"""
)

case("gunsight_reset_hides_the_container_and_cached_objects")(
    r"""
gsMockContainer(2)
UnitExists = function() return false end
runCmd("gunsight")
pull(2)
runCmd("reset")
check(FSCheckGsAuraContainer._shown == false, "reset left the container shown")
allHidden()
"""
)

case("gunsight_container_refusals_are_recorded")(
    r"""
__acCreateThrows = true
runCmd("gunsight")
local rec = ForeverSTUwaveDB.fscheck.gunsight.auraContainer
check(string.find(rec.status, "frame type refused", 1, true), "create refusal: " .. tostring(rec.status))
check(ForeverSTUwaveDB.fscheck.gunsight.alphaFromBoolean.texture ~= nil, "later checks did not run")
"""
)

case("gunsight_missing_template_is_recorded")(
    r"""
__template = false
runCmd("gunsight")
check(string.find(ForeverSTUwaveDB.fscheck.gunsight.auraContainer.status, "template absent", 1, true), "template status")
pull(2)
advance(1)
allHidden()
"""
)

case("gunsight_with_every_api_throwing_leaks_nothing", "throw")(
    r"""
gsMockContainer(2)
runCmd("gunsight")
pull(2)
advance(2)
advance(1)
scan(ForeverSTUwaveDB.fscheck)
allHidden()
"""
)

case("gunsight_survives_a_failing_create_frame", "throw")(
    r"""
__frameThrows = true
runCmd("gunsight")
check(ForeverSTUwaveDB.fscheck.gunsight.meta.hostError ~= nil, "host failure not recorded")
"""
)

case("hot_builds_samples_in_and_out_of_combat_and_tears_down")(
    r"""
hotMock(2)
runCmd("hot")
local player, party1 = FSCheckHot_player, FSCheckHot_party1
check(player and party1, "a container is missing for an existing token")
check(FSCheckHot_party2 == nil and FSCheckHot_party4 == nil, "a container was built for a token that does not exist")
check(player._unit == "player" and party1._unit == "party1", "containers not pointed at their token")
check(player._shown == true and player._args.SetEnabled[1] == true, "container not enabled and shown")
check(player._slotOpts.candidateFilters.includeSpellIDs[139] == true, "Renew rank 1 missing from includeSpellIDs")
check(player._slotOpts.candidateFilters.includeSpellIDs[9999] == true, "runtime rank missing from includeSpellIDs")
check(player._groupOpts.candidateFilters.maxDuration == 60, "group maxDuration")
local rec = ForeverSTUwaveDB.fscheck.hot
check(rec.meta.idsUnverified == nil and rec.meta.runtimeRank == 9999, "id bookkeeping")
check(type(rec.meta.idsSource) == "string" and string.find(rec.meta.idsSource, "ElvUI", 1, true), "ids source must cite ElvUI: " .. tostring(rec.meta.idsSource))
local row = rec.tokens.player
check(rec.tokens.party2.exists == false and rec.tokens.party2.built == nil, "party2 should be recorded as absent")
check(row.steps.addAuraSlot == "ok" and row.steps.addAuraGroup == "ok" and row.steps.show == "ok", "build steps")
check(row.initCalls.slot == 1 and row.initCalls.group == 2, "init counts: " .. row.initCalls.slot .. " " .. row.initCalls.group)
for _, step in ipairs({ "slot.icon", "slot.cooldown", "slot.durationText", "group.durationText" }) do
    check(row.initSteps[step] == "ok", "init step " .. step .. ": " .. tostring(row.initSteps[step]))
end
check(row.samples[1] and string.find(row.samples[1], "ooc", 1, true), "no immediate out of combat sample")
-- out of combat: nothing shown for 3 more seconds
advance(1) advance(1) advance(1)
-- into combat: the slot button and one group button are up for 3 samples, then the slot button drops
__combat = true
player._slotBtn._shown = true
player._groupBtns[1]._shown = true
advance(1) advance(1) advance(1)
player._slotBtn._shown = false
advance(1)
check(row.stats.ooc.samples == 4 and row.stats.ooc.withShown == 0, "ooc stats")
check(row.stats.combat.samples == 4 and row.stats.combat.withShown == 4 and row.stats.combat.maxShown == 2, "combat stats")
check(row.stats.combat.slotShown == 3, "slot shown in combat: " .. tostring(row.stats.combat.slotShown))
check(row.stats.transitions == 2 and row.stats.gainedInCombat == 1 and row.stats.lostInCombat == 0, "transitions")
check(string.find(row.samples[5], "COMBAT", 1, true) and string.find(row.samples[5], "shown=2", 1, true), "combat sample text: " .. tostring(row.samples[5]))
check(rec.meta.lockdownSamples == 4, "lockdown samples: " .. tostring(rec.meta.lockdownSamples))
-- the rest of the 120s window
for _ = 1, 125 do advance(1) end
check(rec.meta.ended == "done" and rec.meta.samples == 121, "sampler did not end at 121 samples: " .. tostring(rec.meta.samples))
check(pendingTimers() == 0, "a timer is still pending after the sampler ended")
check(said("hot done (121 samples)"), "summary line missing")
check(rec.summary and string.find(rec.summary, "player ooc", 1, true) and string.find(rec.summary, "party1 ooc", 1, true), "summary text")
__combat = false
runCmd("hot off")
check(player._shown == false and party1._shown == false, "hot off left a container shown")
check(player._args.SetEnabled[1] == false, "hot off did not disable")
allHidden()
noOnUpdate()
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_refuses_to_build_in_combat")(
    r"""
hotMock(1)
__combat = true
runCmd("hot")
check(said("leave combat first"), "no refusal line")
check(FSCheckHot_player == nil and #__frames == 0, "a frame was built in combat")
check(ForeverSTUwaveDB == nil or ForeverSTUwaveDB.fscheck == nil, "a result was written in combat")
check(pendingTimers() == 0, "a timer was scheduled in combat")
"""
)

case("hot_off_in_combat_only_drops_alpha_and_a_second_off_finishes_it")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSCheckHot_player
__combat = true
runCmd("hot off")
check(player._args.SetAlpha[1] == 0, "alpha not dropped")
check((player._calls.Hide or 0) == 0 and player._args.SetEnabled[1] == true, "a protected call was made in combat")
check(said("out of combat"), "no hint to repeat it")
check(said("alpha 0 on the containers, plain holder hidden"), "in combat message must say what was hidden")
advance(2)
check(pendingTimers() == 0, "sampler still running after off")
__combat = false
runCmd("hot off")
check(player._shown == false and player._args.SetEnabled[1] == false, "second off did not finish the teardown")
-- a re-run reuses the container instead of adding the groups twice
runCmd("hot")
check(ForeverSTUwaveDB.fscheck.hot.tokens.player.steps.addAuraSlot == "reused", "re-run did not reuse the container")
check(player._shown == true and player._args.SetAlpha[1] == 1, "re-run did not bring the strip back")
runCmd("reset")
check(player._shown == false, "reset left the strip up")
allHidden()
"""
)

case("hot_survives_a_refused_container_and_secret_buttons", "secret")(
    r"""
hotMock(2)
runCmd("hot")
local player = FSCheckHot_player
player._groupBtns[1].IsShown = function() return SB end
player._groupBtns[2]._shown = true
advance(1)
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
check(string.find(row.samples[2], "unk=1", 1, true), "a secret IsShown must count as unknown: " .. tostring(row.samples[2]))
check(row.stats.ooc.unknown == 1 and row.stats.combat.unknown == 0, "unknown must be counted per bucket")
check(row.stats.ooc.withShown == 0 and row.stats.transitions == 0, "an unknown sample must not feed withShown or transitions")
scan(ForeverSTUwaveDB.fscheck)
"""
)

# In combat the engine's buttons answer IsShown with a secret. That is "unknown", never "hidden":
# it must not count as a loss, a transition or a shown sample, and known, unknown, known must
# not register a transition.
case("hot_secret_buttons_in_combat_are_unknown_not_lost", "secret")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSCheckHot_player
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
player._slotBtn._shown = true
advance(1)
check(row.stats.ooc.withShown == 1 and row.stats.transitions == 1, "setup: out of combat shown sample")
__combat = true
player._slotBtn.IsShown = function() return SB end
advance(1) advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
check(row.stats.lostInCombat == 0, "a secret IsShown counted as lost: " .. tostring(row.stats.lostInCombat))
check(row.stats.transitions == 1, "a secret IsShown counted as a transition: " .. tostring(row.stats.transitions))
check(row.stats.gainedInCombat == 0, "gained in combat")
check(row.stats.combat.samples == 2 and row.stats.combat.unknown == 2, "unknown samples: " .. tostring(row.stats.combat.unknown))
check(row.stats.combat.withShown == 0, "an unknown sample counted as shown or hidden")
check(row.stats.combat.slotSecret == 2 and row.stats.combat.slotShown == 0, "slot secret count: " .. tostring(row.stats.combat.slotSecret))
check(string.find(row.samples[3], "slot=secret", 1, true), "slot text: " .. tostring(row.samples[3]))
-- readable again, same shown count as before the secret run: no transition
player._slotBtn.IsShown = nil
advance(1)
check(row.stats.transitions == 1, "known, unknown, known registered a transition: " .. tostring(row.stats.transitions))
check(row.stats.combat.withShown == 1 and row.stats.combat.unknown == 2, "known sample after the unknown run")
-- the summary line carries the unknown and slot secret counts
__combat = false
runCmd("hot off")
local summary = ForeverSTUwaveDB.fscheck.hot.summary
check(summary and string.find(summary, "unk 2", 1, true) and string.find(summary, "slotsecret 2", 1, true), "summary: " .. tostring(summary))
scan(ForeverSTUwaveDB.fscheck)
"""
)

# A button that really drops out of combat is a transition, but never a loss IN combat.
case("hot_a_button_hidden_out_of_combat_is_a_transition_not_a_loss")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSCheckHot_player
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
player._slotBtn._shown = true
advance(1)
player._slotBtn._shown = false
advance(1)
check(row.stats.transitions == 2, "transitions: " .. tostring(row.stats.transitions))
check(row.stats.lostInCombat == 0 and row.stats.gainedInCombat == 0, "an out of combat drop counted as a combat loss")
-- and a real drop in combat IS a loss (readable IsShown), a real return a gain
__combat = true
player._slotBtn._shown = true
advance(1)
player._slotBtn._shown = false
advance(1)
check(row.stats.lostInCombat == 1 and row.stats.gainedInCombat == 1, "combat loss " .. tostring(row.stats.lostInCombat) .. " gain " .. tostring(row.stats.gainedInCombat))
"""
)

case("hot_records_a_refused_create_frame")(
    r"""
hotMock(1)
__acCreateThrows = true
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
check(row.status == "create failed" and string.find(row.steps.createFrame, "boom", 1, true), "refusal not recorded")
check(said("no container built"), "no summary")
check(pendingTimers() == 0, "sampler started without a container")
"""
)

case("hot_result_survives_a_main_run_rearm")(
    r"""
hotMock(1)
runCmd("hot")
runCmd("")
check(ForeverSTUwaveDB.fscheck.hot ~= nil and ForeverSTUwaveDB.fscheck.ooc ~= nil, "re-arm wiped the hot result")
"""
)


# The HoT TIMER BAR shape: a second slot "renewbar" whose button gets a StatusBar driven by the engine
# (SetDurationBar), a bare-number text (SetDurationText with a numeric rule formatter and a step colour
# curve) and a pandemic overlay (AddPandemicRegion). Every step is pcall'd and recorded in barSteps.
case("hot_bar_slot_builds_the_timer_bar_and_records_every_step")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSCheckHot_player
local btn = player._barBtn
check(btn, "no renewbar slot was added")
check(player._barOpts.candidateFilters.includeSpellIDs[139] == true and player._barOpts.candidateFilters.includeSpellIDs[9999] == true,
    "bar slot must use the same Renew id set")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
check(row.steps.addBarSlot == "ok", "addBarSlot: " .. tostring(row.steps.addBarSlot))
check(row.initCalls.bar == 1, "bar init count")
local bs = row.barSteps
check(type(bs) == "table" and type(bs.api) == "table", "barSteps.api missing")
-- 1. the API surface, by real names
check(bs.api.SetDurationBar == "function" and bs.api.AddPandemicRegion == "function" and bs.api.SetDurationText == "function", "method types")
check(bs.api["Enum.StatusBarTimerDirection"] == "table" and bs.api["Enum.StatusBarTimerDirection.RemainingTime"] == 1, "direction enum")
check(bs.api["Enum.StatusBarInterpolation"] == "table" and bs.api["Enum.StatusBarInterpolation.Immediate"] == 0, "interpolation enum")
check(bs.api["Enum.DurationTextBindingProperty"] == "table" and bs.api["Enum.DurationTextBindingProperty.RemainingDuration"] == 0, "binding property enum")
check(bs.api["Enum.NumericRuleFormatRounding"] == "table" and bs.api["Enum.NumericRuleFormatRounding.Up"] == 1, "rounding enum")
check(bs.api["Enum.LuaCurveType"] == "table" and bs.api["Enum.LuaCurveType.Step"] == 1, "curve type enum")
check(bs.api["C_StringUtil.CreateNumericRuleFormatter"] == "function" and bs.api["C_CurveUtil.CreateColorCurve"] == "function", "factory types")
-- 2. the bar
for _, step in ipairs({ "seat", "bar", "barTexture", "barColor", "barReverse", "barTrack", "setDurationBar",
                        "text", "textCustom", "pandemicTexture", "addPandemicRegion" }) do
    check(bs[step] == "ok", "bar step " .. step .. ": " .. tostring(bs[step]))
end
check(bs.textMode == "custom" and bs.textDefault == nil, "text mode: " .. tostring(bs.textMode))
-- no FS.Theme in this harness: the template font stays and the record says so
check(string.find(bs.textFont, "template font", 1, true), "font record: " .. tostring(bs.textFont))
local args = btn._args.SetDurationBar
local bar = args[1]
check(bar._kind == "StatusBar" and bar._parent == btn, "the bar must be a StatusBar child of the button")
check(bar._args.SetSize[1] == 160 and bar._args.SetSize[2] == 4, "bar size")
check(bar._args.SetReverseFill[1] == true, "reverse fill")
check(bar._calls.SetStatusBarTexture == 1 and bar._calls.SetStatusBarColor == 1, "flat texture and colour")
check(args[2].direction == 1 and args[2].interpolation == 0, "SetDurationBar options: RemainingTime, Immediate")
-- 3. the number
local fsArgs = btn._args.SetDurationText
check(fsArgs[1]._kind == "CreateFontString", "duration text must be a FontString")
local tf = fsArgs[2].textFormat
check(tf.formatString == "{}" and #tf.components == 1 and tf.components[1].property == 0, "textFormat shape")
local bp = tf.components[1].formatter.breakpoints
check(#bp == 1 and bp[1].threshold == 0 and bp[1].step == 1 and bp[1].rounding == 1 and bp[1].format == "%d", "one breakpoint, step 1, round Up, %d")
local tc = fsArgs[2].textColor
check(tc.property == 0 and tc.curve.curveType == 1, "colour curve is a Step on RemainingDuration")
check(#tc.curve.points == 2 and tc.curve.points[1].x == 0 and tc.curve.points[2].x == 3.001, "curve points 0 and 3.001")
local amber, green = tc.curve.points[1].color, tc.curve.points[2].color
check(amber.r > amber.g and amber.g > amber.b, "0 is amber")
check(green.g > green.r, "3.001 is green")
-- 4. the pandemic overlay: amber, hidden, riding the bar's fill texture
local pan = btn._args.AddPandemicRegion[1]
check(pan and pan._kind == "CreateTexture", "pandemic region must be a texture")
check((pan._calls.Hide or 0) >= 1 and pan._shown == false, "pandemic texture must start hidden")
local pts = rawget(pan, "_points")
check(pts and #pts == 2, "pandemic texture needs both corner anchors: " .. tostring(pts and #pts))
check(pts[1][1] == "TOPLEFT" and pts[1][2] == bar._sbt, "pandemic TOPLEFT must anchor to the bar fill texture")
check(pts[2][1] == "BOTTOMRIGHT" and pts[2][2] == bar._sbt, "pandemic BOTTOMRIGHT must anchor to the bar fill texture")
check(pan._calls.SetColorTexture == 1, "pandemic amber colour")
-- laid out visibly under the boxes and labelled
local labelled = false
for _, f in ipairs(__allFrames) do
    if f._kind == "CreateFontString" and f._args.SetText and f._args.SetText[1] == "bar" then labelled = true end
end
check(labelled, "the bar slot must be labelled 'bar'")
check(btn._args.SetAllPoints and btn._args.SetAllPoints[1] ~= nil, "bar button not seated in its strip column")
-- raised above the strip box's tinted texture (the mock box is at level 1)
local lv = rawget(btn, "_levels")
check(lv and #lv == 1 and lv[1] == 4, "bar button frame level raise: " .. tostring(lv and lv[1]))
-- HP.Preamble ran: the bar button takes no clicks
check(btn._args.SetMouseClickEnabled and btn._args.SetMouseClickEnabled[1] == false, "HP.Preamble did not run for the bar button")
-- nothing was read
check(__auraRead == false, "an aura, duration, bar value or text was read")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_missing_bar_api_is_recorded_as_absent_and_nothing_throws")(
    r"""
hotMock(1)
__missing = { SetDurationBar = true, AddPandemicRegion = true }
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
local bs = row.barSteps
check(bs.api.SetDurationBar == "nil" and bs.api.AddPandemicRegion == "nil" and bs.api.SetDurationText == "function", "types recorded")
check(bs.setDurationBar == "absent" and bs.addPandemicRegion == "absent", "missing methods must read absent: " .. tostring(bs.setDurationBar))
check(bs.bar == "ok" and bs.text == "ok" and bs.textMode == "custom" and bs.pandemicTexture == "ok", "the other steps must still run")
check(row.status == "built" and pendingTimers() == 1, "the check must still build and sample")
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_whole_bar_api_absent_records_each_gap")(
    r"""
hotMock(1)
__missing = { SetDurationBar = true, SetDurationText = true, AddPandemicRegion = true }
Enum, C_StringUtil, C_CurveUtil, CreateColor = nil, nil, nil, nil
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
local bs = row.barSteps
check(row.built == true and bs, "the container must still build with a bar record")
check(bs.api.SetDurationBar == "nil" and bs.api["Enum.StatusBarTimerDirection"] == "nil", "enum absence")
check(bs.api["Enum.StatusBarTimerDirection.RemainingTime"] == "nil", "enum field absence")
check(bs.api["C_StringUtil.CreateNumericRuleFormatter"] == "nil" and bs.api["C_CurveUtil.CreateColorCurve"] == "nil", "factory absence")
check(bs.setDurationBar == "absent" and bs.textDefault == "absent" and bs.textMode == "none", "text fallback must be recorded: " .. tostring(bs.textMode))
check(string.find(bs.textCustom, "absent", 1, true), "custom text error must name what is absent: " .. tostring(bs.textCustom))
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_a_throwing_bar_step_does_not_stop_the_next")(
    r"""
hotMock(1)
__FrameM.SetDurationBar = function() error("refused: SetDurationBar") end
__FrameM.SetReverseFill = function() error("refused: SetReverseFill") end
runCmd("hot")
local bs = ForeverSTUwaveDB.fscheck.hot.tokens.player.barSteps
check(string.find(bs.setDurationBar, "refused: SetDurationBar", 1, true), "error text recorded: " .. tostring(bs.setDurationBar))
check(string.find(bs.barReverse, "refused: SetReverseFill", 1, true), "reverse fill error recorded: " .. tostring(bs.barReverse))
check(bs.barTrack == "ok" and bs.text == "ok" and bs.textMode == "custom" and bs.addPandemicRegion == "ok", "later steps still ran")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_custom_text_format_error_falls_back_to_defaults_and_records_it")(
    r"""
hotMock(1)
__FrameM.SetDurationText = function(self, fs, opts)
    self._calls.SetDurationText = (self._calls.SetDurationText or 0) + 1
    self._args.SetDurationText = { fs, opts }
    if next(opts) ~= nil then error("bad textFormat") end
end
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
local bs = row.barSteps
check(string.find(bs.textCustom, "bad textFormat", 1, true), "custom failure not recorded: " .. tostring(bs.textCustom))
check(bs.textDefault == "ok" and bs.textMode == "default", "default retry not recorded: " .. tostring(bs.textMode))
local btn = FSCheckHot_player._barBtn
check(btn._calls.SetDurationText == 2 and next(btn._args.SetDurationText[2]) == nil, "the retry must pass default options")
check(bs.addPandemicRegion == "ok", "the next step must still run")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_a_throwing_formatter_factory_also_falls_back")(
    r"""
hotMock(1)
C_StringUtil.CreateNumericRuleFormatter = function() error("boom: factory") end
runCmd("hot")
local bs = ForeverSTUwaveDB.fscheck.hot.tokens.player.barSteps
check(string.find(bs.textCustom, "boom: factory", 1, true), "factory error not recorded: " .. tostring(bs.textCustom))
check(bs.textMode == "default" and bs.textDefault == "ok", "must fall back to default opts")
"""
)

case("hot_a_refused_bar_slot_does_not_stop_the_group")(
    r"""
hotMock(2)
__slotThrows = { renewbar = "boom: AddAuraSlot renewbar" }
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
check(string.find(row.steps.addBarSlot, "boom: AddAuraSlot renewbar", 1, true), "bar slot refusal not recorded: " .. tostring(row.steps.addBarSlot))
check(row.steps.addAuraSlot == "ok" and row.steps.addAuraGroup == "ok" and row.built == true, "slot and group must still build")
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
check(string.find(row.samples[2], "bar=none", 1, true), "no bar slot samples as none: " .. tostring(row.samples[2]))
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_pandemic_and_bar_visibility_are_counted_and_secrets_are_unknown", "secret")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSCheckHot_player
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
local btn = player._barBtn
local pan = btn._args.AddPandemicRegion[1]
check(string.find(row.samples[1], "bar=false", 1, true) and string.find(row.samples[1], "pan=false", 1, true), "first sample: " .. tostring(row.samples[1]))
-- out of combat: both readable, shown for two samples
btn._shown = true
pan._shown = true
advance(1) advance(1)
check(row.stats.ooc.barShown == 2 and row.stats.ooc.panShown == 2, "ooc bar/pandemic shown: " .. tostring(row.stats.ooc.barShown) .. "/" .. tostring(row.stats.ooc.panShown))
-- in combat the engine answers with secrets: unknown, never shown and never hidden
__combat = true
btn.IsShown = function() return SB end
pan.IsShown = function() return SB end
advance(1) advance(1)
check(row.stats.combat.barSecret == 2 and row.stats.combat.panSecret == 2, "secret counts")
check(row.stats.combat.barShown == 0 and row.stats.combat.panShown == 0, "a secret counted as shown")
check(string.find(row.samples[5], "bar=secret", 1, true) and string.find(row.samples[5], "pan=secret", 1, true), "secret text: " .. tostring(row.samples[5]))
-- readable again, the pandemic overlay up for one sample
btn.IsShown = nil
pan.IsShown = nil
pan._shown = true
advance(1)
check(row.stats.combat.panShown == 1 and row.stats.combat.barShown == 1, "readable combat sample")
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
__combat = false
runCmd("hot off")
local summary = ForeverSTUwaveDB.fscheck.hot.summary
check(string.find(summary, "barshown 3 barunk 2", 1, true), "bar summary: " .. tostring(summary))
check(string.find(summary, "pandemic 3 pandemicunk 2", 1, true), "pandemic summary: " .. tostring(summary))
check(__auraRead == false, "an aura, duration, bar value or text was read")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("hot_rerun_keeps_the_bar_record_and_chat_tells_parker_what_to_watch")(
    r"""
hotMock(1)
runCmd("hot")
check(said("drain") and said("whole seconds") and said("amber") and said("pandemic"), "start line must say what to judge by eye")
runCmd("hot off")
runCmd("hot")
local row = ForeverSTUwaveDB.fscheck.hot.tokens.player
check(row.steps.addBarSlot == "reused", "re-run must reuse the bar slot: " .. tostring(row.steps.addBarSlot))
check(row.barSteps and row.barSteps.bar == "ok" and row.barSteps.api, "re-run lost the bar record")
scan(ForeverSTUwaveDB.fscheck)
"""
)


# --- /fscheck priest -----------------------------------------------------------------------------

case("priest_main_run_section_is_class_gated")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fscheck
check(db.ooc.priest and db.ooc.priest.classToken == "PRIEST", "a priest gets the section")
check(db.ooc.priest.inCombat == false and db.ooc.priest.mana, "ooc priest section must be tagged and filled")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(db.combat.priest.inCombat == true and db.combat.priest.mana, "combat priest section must be tagged true")
scan(db)
"""
)

case("priest_main_run_section_skips_other_classes")(
    r"""
UnitClass = function() return "Warrior", "WARRIOR", 1 end
runCmd("")
local sec = ForeverSTUwaveDB.fscheck.ooc.priest
check(sec.skipped == "not a priest" and sec.classToken == "WARRIOR", "other class must skip: " .. tostring(sec.skipped))
check(sec.mana == nil and sec.spells == nil, "a skipped section must hold no check data")
"""
)

case("priest_main_run_section_skips_when_the_class_is_secret", "secret")(
    r"""
runCmd("")
local sec = ForeverSTUwaveDB.fscheck.ooc.priest
check(sec.skipped == "not a priest" and sec.classToken == "unknown", "secret class must fail closed")
scan(ForeverSTUwaveDB.fscheck)
"""
)

case("priest_command_snapshot_covers_the_checklist")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p and p.ooc and p.ooc.kind == "ooc" and p.ooc.inCombat == false, "ooc snapshot tagged false")
check(p.meta.status == "logging", "status: " .. tostring(p.meta.status))
local o = p.ooc
-- A: secrecy map and predicates
check(o.spells.pw_shield.s17.aura == "number/plain=0", "spell secrecy cell: " .. tostring(o.spells.pw_shield.s17.aura))
check(o.spells.pw_shield.s17.isPlayerSpell == "boolean/plain=true", "isPlayerSpell cell")
check(o.spells.sw_pain.s594, "a rank resolved by name must be checked too")
check(o.secrets.calls["GetPowerTypeSecrecy(0)"].r1.type == "number", "power secrecy recorded")
check(o.secrets.calls["ShouldUnitPowerBeSecret(party1,0)"].inCombat == false, "predicate records are tagged")
-- B: mana
check(o.mana.playerPower.r1.value == 100 and o.mana.playerPower.inCombat == false, "UnitPower sample")
check(o.mana.playerPowerPercentCurve.exists and o.mana.playerPowerPercentCurve.ok, "percent with a curve")
check(o.mana.regen.r1.value == 8 and o.mana.regenForMana.r2.value == 4, "regen reads")
check(o.mana.casting.exists and o.mana.channeling.exists, "cast info reads")
check(o.mana.cost.s585.count == 1 and o.mana.cost.s585.first.cost.value == 150, "mana cost read")
check(o.mana.cost.s5019.ok and o.mana.cost.s5019.n == 0 and o.mana.cost.s5019.count == nil, "wand returns nothing")
check(o.mana.cost.s2050.count == 0, "an empty cost table is recorded as count 0")
-- item 3: the resolved name sits next to every checked id; unresolved ids say so
check(o.spells.pw_shield.s17.spellName == "Power Word: Shield", "spell name beside the id: " .. tostring(o.spells.pw_shield.s17.spellName))
check(o.spells.weakened_soul.s6788.spellName == "unresolved", "an id the client cannot name is marked unresolved")
check(o.spells.fort.s1244 and not o.spells.fort.s21562, "retail Fortitude 21562 must not be checked by the priest list")
check(o.mana.cost.s585.spellName == "Smite", "cost record carries the spell name")
check(o.cooldowns.pw_shield.s17.spellName == "Power Word: Shield" and o.auras.pw_shield.s17.spellName == "Power Word: Shield",
    "cooldown and aura cells carry the spell name")
-- item 5: target durability, plain/secret per read; absent APIs are recorded
local t = o.target
check(t.classification.r1.value == "elite" and t.level.r1.value == 12 and t.effectiveLevel.r1.value == 20, "target reads")
check(t.creatureType.r1.value == "Beast" and t.creatureType.r2.value == 1, "creature type and id")
check(t.isPlusMob.exists == false, "UnitIsPlusMob is absent in the mock and must be recorded absent")
check(t.inCombat == false and t.exists.r1.value == true, "target part is tagged and records existence")
check(o.apis.UnitClassification == "present" and o.apis.UnitIsPlusMob == "absent" and o.apis.UnitLevel == "present" and o.apis.UnitExists == "present",
    "api presence covers the target reads")
-- C: shield
check(o.shield.player.totalAbsorbs.exists and o.shield.player.truncateWhenZero.ok, "absorb reads")
check(o.shield.player.GetDamageAbsorbs.r1.value == 120 and o.shield.player.GetDamageAbsorbs.r2.value == false, "calculator reads")
check(o.shield.party1.GetIncomingHeals.n == 4, "incoming heals return count")
-- D: auras by spell
check(string.find(o.auras.inner_fire.s588.playerByID, "spellId=number/plain", 1, true), "aura cell: " .. tostring(o.auras.inner_fire.s588.playerByID))
check(o.auras.pw_shield.s17.party1 == "no returns" or o.auras.pw_shield.s17.party1 == "nil/plain", "no aura reads nothing: " .. tostring(o.auras.pw_shield.s17.party1))
-- F: cooldowns
local cd = o.cooldowns.pw_shield.s17
check(string.find(cd.cooldown, "isActive=boolean/plain=false", 1, true), "cooldown cell: " .. tostring(cd.cooldown))
check(cd.durationObject and cd.durationIsZero == "boolean/plain=true", "duration object IsZero")
check(string.find(cd.charges, "maxCharges=number/plain=2", 1, true) and string.find(cd.charges, "currentCharges=number/plain=1", 1, true),
    "charges keep the plain counts: " .. tostring(cd.charges))
check(o.cooldowns.fade.skipped == "not known", "unknown spells are not read")
-- G: triage
check(o.triage.party1InRangeOfHeal.exists and o.triage.rangeSpell == "Lesser Heal", "heal range read: " .. tostring(o.triage.rangeSpell))
check(o.triage.unitInRangeParty1.r1.type == "boolean", "UnitInRange read")
check(o.triage.threatPlayer.r1.value == 1, "threat read")
-- H: loss of control
check(o.lossOfControl.count.r1.value == 1 and o.lossOfControl.first.fields.locType.value == "FEAR", "loss of control")
-- I: misc
check(o.misc.combatLogRestricted.r1.value == true, "combat log restricted flag")
check(type(o.misc.cleuRegister) == "string", "CLEU registration result recorded")
check(o.misc.durationObject.evaluateRemaining.r1.value == 1 and o.misc.durationObject.instance == "found", "duration trial")
check(o.misc.items["Holy Candle"].exists, "item count read")
check(o.apis.UnitPowerPercent == "present" and o.apis["C_Spell.GetSpellCharges"] == "present", "api presence map")
-- events: unit filtered where one or two units do
local f = pframe()
check(f._events.UNIT_POWER_UPDATE == "unit:player" and f._events.UNIT_POWER_FREQUENT == "unit:player", "power events")
check(f._events.UNIT_AURA == "unit:player,target", "aura event units")
for _, e in ipairs({ "PARTY_KILL", "UNIT_DIED", "PLAYER_TARGET_DIED", "LOSS_OF_CONTROL_ADDED", "PLAYER_REGEN_DISABLED" }) do
    check(f._events[e] == true, e .. " not registered")
end
check(f._events.UNIT_ABSORB_AMOUNT_CHANGED == "unit:player,party1" and f._events.UNIT_HEAL_PREDICTION == "unit:player,party1",
    "absorb and prediction events must be unit events for player and party1")
check(string.find(o.misc.cleuRegister, "forbidden (ADDON_ACTION_FORBIDDEN", 1, true), "CLEU snapshot records the forbidden result: " .. tostring(o.misc.cleuRegister))
check(__cleuAttempts == 0, "COMBAT_LOG_EVENT_UNFILTERED must never be registered (protected on Forever): " .. tostring(__cleuAttempts))
check(said("Run /fscheck priest again"), "chat line must tell Parker to run the command again")
noOnUpdate()
check(said("priest"), "priest line missing")
scan(p)
"""
)

case("priest_combat_snapshot_follows_the_pull_and_sits_beside_the_ooc_one")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
local f = pframe()
__combat = true
pfire("PLAYER_REGEN_DISABLED")
check(p.combat == nil, "combat snapshot taken before the delay")
advance(3)
check(p.combat == nil, "combat snapshot taken early")
advance(1)
check(p.combat and p.combat.kind == "combat" and p.combat.inCombat == true, "combat snapshot tagged true")
check(p.ooc.inCombat == false and p.combat.mana.playerPower.inCombat == true, "both runs side by side")
check(f._events.PLAYER_REGEN_DISABLED == nil, "REGEN_DISABLED still registered after the combat snapshot")
check(said("priest: combat snapshot"), "combat line missing")
scan(p)
"""
)

case("priest_pull_that_ends_before_the_delay_takes_no_combat_snapshot")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
__combat = true
pfire("PLAYER_REGEN_DISABLED")
__combat = false
advance(4)
check(p.combat == nil, "snapshot taken after combat already ended")
check(pframe()._events.PLAYER_REGEN_DISABLED == true, "must stay armed for the next pull")
"""
)

case("priest_command_in_combat_takes_the_combat_snapshot_then_ooc_after_the_fight")(
    r"""
priestMock()
__combat = true
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p.combat and p.combat.inCombat == true and p.ooc == nil, "in combat the first snapshot is the combat one")
check(string.find(p.combat.misc.cleuRegister, "forbidden (ADDON_ACTION_FORBIDDEN", 1, true), "combat snapshot records the same forbidden CLEU result: " .. tostring(p.combat.misc.cleuRegister))
check(__cleuAttempts == 0, "COMBAT_LOG_EVENT_UNFILTERED must never be registered in combat either: " .. tostring(__cleuAttempts))
__combat = false
pfire("PLAYER_REGEN_ENABLED")
advance(2)
check(p.ooc and p.ooc.inCombat == false, "ooc snapshot follows once the fight ends")
scan(p)
"""
)

case("priest_event_logs_are_capped_ring_buffers")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
local feeds = {
    { "cast", "UNIT_SPELLCAST_SUCCEEDED", { "player", "Cast-1", 585 } },
    { "aura", "UNIT_AURA", { "target", { isFullUpdate = false, addedAuras = {}, updatedAuraInstanceIDs = {}, removedAuraInstanceIDs = {} } } },
    { "shield", "UNIT_ABSORB_AMOUNT_CHANGED", { "party1" } },
    { "kill", "PARTY_KILL", { "Player-1-1", "Creature-1-1" } },
    { "died", "UNIT_DIED", { "Creature-1-1" } },
    { "loc", "LOSS_OF_CONTROL_ADDED", { "player", 1 } },
}
for _, feed in ipairs(feeds) do
    for _ = 1, 80 do
        __now = __now + 0.1
        pfire(feed[2], unpack(feed[3]))
    end
    local log = p.logs[feed[1]]
    check(log, feed[1] .. " log missing")
    check(log.cap == 50 and #log.entries == 50, feed[1] .. " must hold exactly 50: " .. tostring(#log.entries))
    check(log.total == 80 and log.dropped == 30, feed[1] .. " counts: " .. tostring(log.total) .. "/" .. tostring(log.dropped))
    local first, last = log.entries[1], log.entries[50]
    check(type(first.t) == "number" and first.t < last.t, feed[1] .. " entries must be oldest first with GetTime stamps")
    check(first.inCombat == false and first.event == feed[2], feed[1] .. " entry tag")
end
-- the oldest entries went: what is left is the newest 50
check(p.logs.cast.entries[50].t - p.logs.cast.entries[1].t > 4.8, "ring kept the wrong end")
scan(p)
"""
)

case("priest_power_log_filters_and_times_the_five_second_rule")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", "player", "RAGE")
pfire("UNIT_POWER_UPDATE", "party1", "MANA")
check(p.logs.power == nil or p.logs.power.total == 0, "a non-mana or foreign power event was logged")
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 585)
__now = __now + 2
pfire("UNIT_POWER_UPDATE", "player", "MANA")
__now = __now + 2
pfire("UNIT_POWER_UPDATE", "player", "MANA")
local e = p.logs.power.entries
check(#e == 2 and math.abs(e[1].sinceManaCast - 2) < 0.001 and math.abs(e[2].sinceManaCast - 4) < 0.001, "sinceManaCast")
check(math.abs(e[2].gap - 2) < 0.001, "gap between ticks")
local c = p.logs.cast.entries[1]
check(c.manaCost == 150 and c.spellID.value == 585 and c.spellID.isSecret == false, "cast entry carries the mana cost")
-- a free cast (wand) must not restart the clock
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 5019)
check(p.logs.cast.entries[2].manaCost == 0, "wand costs no mana (GetSpellPowerCost returns nothing)")
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(math.abs(e[3].sinceManaCast - 5) < 0.001 and e[3].sinceManaCastUnknown == nil,
    "a free cast restarted or invalidated the five second clock")
-- an empty plain table is free too (Lesser Heal is an empty table in the mock)
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-3", 2050)
check(p.logs.cast.entries[3].manaCost == 0, "an empty cost table is free")
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(e[4].sinceManaCastUnknown == nil and math.abs(e[4].sinceManaCast - 6) < 0.001, "an empty cost table must not mark the clock unknown")
-- foreign units that a plain RegisterEvent fallback would deliver are dropped
pfire("UNIT_ABSORB_AMOUNT_CHANGED", "nameplate3")
check(p.logs.shield == nil or p.logs.shield.total == 0, "a nameplate absorb event was logged")
scan(p)
"""
)

case("priest_unreadable_cost_still_marks_the_five_second_clock_unknown")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
-- a plain table whose cost field is secret stays unknown (never treated as free)
C_Spell.GetSpellPowerCost = function() return { { type = 0, name = "MANA", cost = SN } } end
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 585)
check(p.logs.cast.entries[1].manaCost == nil, "a secret cost field must not read as a cost")
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(p.logs.power.entries[1].sinceManaCastUnknown == true, "an unreadable cost must mark the clock unknown")
-- an error from the cost call is unreadable too
C_Spell.GetSpellPowerCost = function() error("boom") end
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 5019)
check(p.logs.cast.entries[2].manaCost == nil, "a throwing cost call is not free")
scan(p)
"""
)

case("priest_power_frequent_is_sampled_and_keeps_the_raw_count")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
for _ = 1, 100 do
    __now = __now + 0.1
    pfire("UNIT_POWER_FREQUENT", "player", "MANA")
end
local log = p.logs.powerFrequent
check(log.total == 100, "total keeps counting every raw event: " .. tostring(log.total))
check(#log.entries >= 8 and #log.entries <= 12, "a 10 Hz stream is sampled to about 1 Hz: " .. tostring(#log.entries))
check(log.dropped == 0 and log.sampledOut == 100 - #log.entries, "sampledOut counts what was skipped: " .. tostring(log.sampledOut))
check(log.minGap == 1, "the sampling gap is recorded")
check(log.entries[2].skippedBefore >= 8 and log.entries[2].skippedBefore <= 10, "an entry says how many events it stands for: " .. tostring(log.entries[2].skippedBefore))
-- a non-mana type is logged at once (its own stream), without disturbing the mana sampler
local before = #log.entries
pfire("UNIT_POWER_FREQUENT", "player", "RAGE")
check(p.logs.powerOther.entries[1].powerType.value == "RAGE", "other power types go to powerOther")
pfire("UNIT_POWER_FREQUENT", "player", "MANA")
check(#log.entries == before, "mana and other power types sample on separate streams: an interleaved RAGE must not reopen the mana stream")
scan(p)
"""
)

case("priest_power_frequent_logs_a_secret_shape_change_at_once", "secret")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
__now = __now + 1
pfire("UNIT_POWER_FREQUENT", "player", "MANA")
local log = p.logs.powerFrequent
local n = #log.entries
__now = __now + 0.1
pfire("UNIT_POWER_FREQUENT", "player", "MANA")
check(#log.entries == n, "the same shape inside the gap must be sampled out")
__now = __now + 0.1
pfire("UNIT_POWER_FREQUENT", "player", SS)
check(#log.entries == n + 1 and log.entries[n + 1].powerType.isSecret == true, "plain to secret powerType must be logged")
scan(p)
"""
)

case("priest_power_entries_carry_unit_power_type_and_a_power_readout")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", "player", "MANA")
local e = p.logs.power.entries[1]
check(e.unit.value == "player" and e.powerType.value == "MANA", "unit and power type")
check(e.unitPower == "number/plain=100", "UnitPower readout: " .. tostring(e.unitPower))
-- the decoy hunt: a non-mana power type is kept, in its own log, with its own readout
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "ENERGY")
check(p.logs.power.total == 1, "a non-mana event must not enter the mana log")
local o = p.logs.powerOther.entries[1]
check(o.event == "UNIT_POWER_UPDATE" and o.powerType.value == "ENERGY" and o.unitPower, "powerOther entry: " .. tostring(o.unitPower))
scan(p)
"""
)

case("priest_power_readout_is_secret_safe", "secret")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(p.logs.power.entries[1].unitPower == "number/secret", "secret UnitPower is described, not stored: " .. tostring(p.logs.power.entries[1].unitPower))
pfire("UNIT_POWER_UPDATE", SS, SS)
local e = p.logs.power.entries[2]
check(e.unit.isSecret == true and e.powerType.isSecret == true, "the secret event was logged")
check(e.unitPower == nil, "no UnitPower read for a secret unit and power type: " .. tostring(e.unitPower))
pfire("UNIT_POWER_UPDATE", "player", SS)
check(p.logs.power.entries[3].unitPower == nil, "no UnitPower read for a secret power type alone")
scan(p)
"""
)

case("priest_sampled_and_power_logs_hold_a_longer_window_and_stay_bounded")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p.meta.logCaps and p.meta.logCaps.power == 300 and p.meta.logCaps.powerFrequent == 300 and p.meta.logCaps.powerOther == 300,
    "the larger caps are recorded in meta")
for _ = 1, 320 do
    __now = __now + 0.1
    pfire("UNIT_POWER_UPDATE", "player", "MANA")
end
check(p.logs.power.cap == 300 and #p.logs.power.entries == 300 and p.logs.power.total == 320 and p.logs.power.dropped == 20, "power log cap")
-- powerOther: one entry a second for 400 s (the sampler's gap), capped at 300
for _ = 1, 400 do
    __now = __now + 1.1
    pfire("UNIT_POWER_FREQUENT", "player", "ENERGY")
end
local o = p.logs.powerOther
check(o.cap == 300 and #o.entries == 300 and o.total == 400 and o.dropped == 100, "powerOther cap: " .. tostring(#o.entries) .. "/" .. tostring(o.dropped))
-- powerFrequent: the same
for _ = 1, 350 do
    __now = __now + 1.1
    pfire("UNIT_POWER_FREQUENT", "player", "MANA")
end
check(p.logs.powerFrequent.cap == 300 and #p.logs.powerFrequent.entries == 300, "powerFrequent cap")
-- the other logs keep 50
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 585)
check(p.logs.cast.cap == 50, "other logs stay at 50")
scan(p)
"""
)

case("priest_alternating_mana_and_other_frequent_events_still_sample")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
for i = 1, 100 do
    __now = __now + 0.05
    pfire("UNIT_POWER_FREQUENT", "player", i % 2 == 0 and "MANA" or "ENERGY")
end
check(p.logs.powerFrequent.total == 50 and p.logs.powerOther.total == 50, "raw counts per log")
check(#p.logs.powerFrequent.entries <= 6 and #p.logs.powerOther.entries <= 6,
    "alternation defeated sampling: " .. tostring(#p.logs.powerFrequent.entries) .. "/" .. tostring(#p.logs.powerOther.entries))
scan(p)
"""
)

case("priest_secret_gettime_samples_frequent_by_count", "secret")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
GetTime = function() return SN end
for _ = 1, 100 do pfire("UNIT_POWER_FREQUENT", "player", "MANA") end
local log = p.logs.powerFrequent
check(log.total == 100, "raw count")
check(#log.entries >= 9 and #log.entries <= 12, "without a plain clock, about 1 in 10 is kept: " .. tostring(#log.entries))
check(log.countSampling == 10 and log.sampledOut == 100 - #log.entries, "count sampling is recorded in the log")
check(log.entries[2].skippedBefore == 9, "an entry stands for the skipped ones")
scan(p)
"""
)

case("priest_cost_assumption_is_recorded")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p.meta.costAssumption == "nil or empty = free", "meta assumption: " .. tostring(p.meta.costAssumption))
check(p.ooc.mana.costAssumption == "nil or empty = free", "snapshot assumption")
"""
)

case("priest_target_part_records_secret_and_missing_reads", "secret")(
    r"""
priestMock()
runCmd("priest")
local t = ForeverSTUwaveDB.fscheck.priest.ooc.target
check(t.classification.r1.isSecret == true and t.classification.r1.value == nil, "secret classification flagged")
check(t.creatureType.r1.isSecret == true and t.creatureType.r2.isSecret == true, "secret creature type flagged")
check(t.effectiveLevel.r1.isSecret == true, "secret effective level flagged")
scan(ForeverSTUwaveDB.fscheck.priest)
"""
)

case("priest_kill_log_compares_guids_only_when_both_are_plain")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
UnitGUID = function(unit) if unit == "player" then return "Player-1-1" end return "Creature-1-1" end
pfire("PARTY_KILL", "Player-1-1", "Creature-1-1")
pfire("PARTY_KILL", "Player-9-9", "Creature-1-1")
pfire("PLAYER_TARGET_DIED")
local k = p.logs.kill.entries
check(k[1].attackerIsPlayer == true and k[2].attackerIsPlayer == false, "attacker identity")
check(k[1].arg1.value == nil, "guids must not be stored")
check(k[3].event == "PLAYER_TARGET_DIED", "target died logged")
scan(p)
"""
)

case("priest_log_entries_never_touch_secret_payloads", "secret")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", SS, SS)
pfire("UNIT_POWER_FREQUENT", SS, SS)
pfire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, SN)
pfire("UNIT_AURA", SS, ST)
pfire("UNIT_AURA", SS, STT)
pfire("UNIT_ABSORB_AMOUNT_CHANGED", SS)
pfire("UNIT_HEAL_PREDICTION", SS)
pfire("PARTY_KILL", SS, SS)
pfire("UNIT_DIED", SS)
pfire("LOSS_OF_CONTROL_ADDED", SS, SN)
for _, name in ipairs({ "power", "powerFrequent", "cast", "aura", "shield", "kill", "died", "loc" }) do
    check(p.logs[name] and p.logs[name].total >= 1, name .. " log must record a secret payload")
end
check(p.logs.power.entries[1].unit.isSecret == true and p.logs.power.entries[1].powerType.value == nil, "secret power payload")
check(p.logs.cast.entries[1].spellID.isSecret == true and p.logs.cast.entries[1].manaCost == nil, "secret spell id has no cost")
check(p.logs.kill.entries[1].arg1.isSecret == true and p.logs.kill.entries[1].attackerIsPlayer == nil, "secret guid not compared")
scan(p)
"""
)

case("priest_snapshot_with_secret_values_stores_only_plain_data", "secret")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p.ooc.mana.playerPower.r1.isSecret == true and p.ooc.mana.playerPower.r1.value == nil, "secret mana stored as a flag")
check(p.ooc.shield.player.GetDamageAbsorbs.r1.isSecret == true, "secret absorb flagged")
local cd = p.ooc.cooldowns.pw_shield.s17
check(cd and cd.cooldown and string.find(cd.cooldown, "startTime=number/secret", 1, true), "secret cooldown cell: " .. tostring(cd and cd.cooldown))
local st = scan(p)
check(st.secretTrue > 10, "expected many secret flags, got " .. tostring(st.secretTrue))
__combat = true
runCmd("priest")
check(p.combat.inCombat == true, "second command in combat")
scan(p)
"""
)

case("priest_missing_apis_record_absent_and_the_rest_still_runs")(
    r"""
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
local o = p.ooc
check(o.mana.regen.exists == false and o.mana.regenForMana.exists == false, "a missing API must record exists=false")
check(o.mana.playerPower.exists and o.mana.playerPower.ok, "present APIs still read")
check(o.shield.player.calculator.exists == false and o.shield.player.totalAbsorbs.exists == false, "shield APIs absent")
check(o.apis.CreateUnitHealPredictionCalculator == "absent" and o.apis.UnitPowerPercent == "present", "presence map")
for name, sec in pairs(o) do
    if type(sec) == "table" then check(sec.sectionError == nil, name .. " section errored: " .. tostring(sec.sectionError)) end
end
-- one API removed from a fuller client
priestMock()
GetPowerRegen = nil
runCmd("priest off")
runCmd("priest")
check(ForeverSTUwaveDB.fscheck.priest.ooc.mana.regen.exists == false and ForeverSTUwaveDB.fscheck.priest.ooc.mana.regenForMana.ok, "siblings of a missing API")
scan(ForeverSTUwaveDB.fscheck.priest)
"""
)

case("priest_every_api_throws", "throw")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p and p.ooc, "snapshot must still be saved")
check(type(p.ooc.mana.playerPower.err) == "string" and p.ooc.mana.playerPower.ok == false, "error stored as a string")
check(p.ooc.mana.playerPower.inCombat == false, "error records are tagged too")
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "x", 585)
pfire("UNIT_AURA", "player", { isFullUpdate = true })
pfire("PARTY_KILL", "a", "b")
check(p.logs.cast.total == 1 and p.logs.aura.total == 1 and p.logs.kill.total == 1, "events still logged under throwing APIs")
check(p.logs.cast.entries[1].manaCost == nil, "no cost when the cost API throws")
advance(5)
scan(p)
"""
)

case("priest_even_createframe_throws", "throw")(
    r"""
priestMock()
__frameThrows = true
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(p.ooc, "snapshot should still be saved")
check(type(p.meta.frameError) == "string" and said("nothing armed"), "frame failure must be recorded and said")
runCmd("priest off")
runCmd("reset")
"""
)

case("priest_second_command_snapshots_again_without_clearing_the_logs")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", "player", "MANA")
local first = p.ooc
runCmd("priest")
check(ForeverSTUwaveDB.fscheck.priest == p, "second command must keep the record")
check(p.ooc ~= first and p.ooc.kind == "ooc" and p.ooc.mana, "second command must replace the snapshot with a fresh one")
check(ForeverSTUwaveDB.fscheck.priest.logs.power.total == 1, "logs must survive a second command")
check(#__timers >= 1 and pendingTimers() == 1, "exactly one stop timer: " .. pendingTimers())
"""
)

case("priest_off_timeout_reset_and_rearm")(
    r"""
priestMock()
runCmd("priest")
local f = pframe()
runCmd("priest off")
check(nevents(f) == 0 and ForeverSTUwaveDB.fscheck.priest.meta.status == "stopped", "off must unregister")
pcall(f._scripts.OnEvent, f, "UNIT_POWER_UPDATE", "player", "MANA")
check((ForeverSTUwaveDB.fscheck.priest.logs.power or { total = 0 }).total == 0, "an event after off was logged")
-- a fresh start replaces the record; the 20 minute timer unregisters
runCmd("priest")
check(nevents(f) > 0, "restart must register again")
advance(1199)
check(nevents(f) > 0, "stopped early")
advance(2)
check(nevents(f) == 0 and ForeverSTUwaveDB.fscheck.priest.meta.status == "timeout", "timeout must unregister")
-- the old run's timer must not stop a newer run: run A's stop timer is due at +1200, run B starts at +600
runCmd("priest")
runCmd("priest off")
advance(600)
runCmd("priest")
advance(601)
check(nevents(f) > 0 and ForeverSTUwaveDB.fscheck.priest.meta.status == "logging", "a stale timer stopped the newer run")
-- the main run keeps a running priest check and its result
runCmd("")
check(ForeverSTUwaveDB.fscheck.priest and nevents(f) > 0, "main arm wiped or stopped the priest check")
-- reset clears everything and stops it
runCmd("reset")
check(ForeverSTUwaveDB.fscheck == nil and nevents(f) == 0, "reset left priest data or events")
advance(5000)
check(ForeverSTUwaveDB.fscheck == nil, "a stale timer wrote after reset")
noOnUpdate()
"""
)

case("priest_five_second_clock_goes_unknown_when_a_cast_cost_is_unreadable")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c1", 585)
__now = __now + 2
pfire("UNIT_POWER_UPDATE", "player", "MANA")
local e = p.logs.power.entries
check(e[1].sinceManaCast and e[1].sinceManaCastUnknown == nil, "readable cost keeps the clock")
-- a secret spell id: the cast may have cost mana, the clock is stale
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c2", SN)
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(e[2].sinceManaCast == nil and e[2].sinceManaCastUnknown == true, "secret spell id must mark the clock unknown")
-- a readable costed cast restarts the clock and clears the flag
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c3", 585)
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(e[3].sinceManaCast and math.abs(e[3].sinceManaCast - 1) < 0.001 and e[3].sinceManaCastUnknown == nil, "clock must recover")
-- an unreadable cost table (spell id plain) is unknown too
C_Spell.GetSpellPowerCost = function() return ST end
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c4", 585)
pfire("UNIT_POWER_UPDATE", "player", "MANA")
check(e[4].sinceManaCast == nil and e[4].sinceManaCastUnknown == true, "unreadable cost must mark the clock unknown")
check(p.logs.cast.entries[4].manaCost == nil, "no cost recorded")
scan(p)
"""
)

case("priest_cost_table_with_secret_fields_marks_the_five_second_clock_unknown")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c1", 585)
-- a plain cost table whose type or cost field is secret: not a free cast, an unreadable one
C_Spell.GetSpellPowerCost = function() return { { type = SN, cost = SN } } end
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c2", 585)
__now = __now + 1
pfire("UNIT_POWER_UPDATE", "player", "MANA")
local e = p.logs.power.entries[1]
check(e.sinceManaCast == nil and e.sinceManaCastUnknown == true, "secret cost fields must mark the clock unknown")
check(p.logs.cast.entries[2].manaCost == nil, "an unreadable cost must not be recorded as 0")
-- a secret cost field on an entry of another power type is unreadable too
C_Spell.GetSpellPowerCost = function() return { { type = 0, cost = 100 }, { type = SN, cost = 5 } } end
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c3", 585)
check(p.logs.cast.entries[3].manaCost == nil, "any unreadable entry makes the whole cost unknown")
scan(p)
"""
)

case("priest_timeout_stop_failure_is_recorded_not_thrown")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
local f = pframe()
local real = print
print = function() error("boom: print") end
advance(1201)
print = real
check(string.find(p.meta.timerError or "", "boom: print", 1, true), "timeout failure not recorded: " .. tostring(p.meta.timerError))
check(nevents(f) == 0 and p.meta.status == "timeout", "events must be unregistered before the failure")
"""
)

case("priest_failed_start_leaves_nothing_live")(
    r"""
priestMock()
__frameThrows = true
runCmd("priest")
check(pframe() == nil, "no frame, no armed events")
__frameThrows = false
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(pframe() and nevents(pframe()) > 0 and p.meta.status == "logging", "a retry after a failed start must start fresh")
check(p.meta.frameError == nil, "fresh record after the retry")
"""
)

case("priest_cooldown_trial_frame_is_hidden_afterwards")(
    r"""
priestMock()
__FrameM.SetCooldownFromDurationObject = function(self) self._shown = true end
runCmd("priest")
local cds = {}
for _, f in ipairs(__frames) do if f._kind == "Cooldown" then cds[#cds + 1] = f end end
check(#cds == 1, "expected one trial Cooldown frame, got " .. #cds)
check(cds[1]._shown == false, "trial Cooldown frame left shown after the trial")
cds[1]._shown = true
runCmd("priest off")
check(cds[1]._shown == false, "stop must hide the trial frame")
"""
)

case("priest_replacing_a_saved_record_says_so")(
    r"""
priestMock()
runCmd("priest")
check(not said("replacing the saved priest record"), "nothing to replace on the first run")
runCmd("priest off")
runCmd("priest")
check(said("replacing the saved priest record"), "a fresh start over a saved record must say so")
"""
)

case("priest_range_read_falls_back_through_the_spell_list")(
    r"""
priestMock()
C_Spell.IsSpellInRange = function(name) if name == "Flash Heal" then return true end end
runCmd("priest")
local t = ForeverSTUwaveDB.fscheck.priest.ooc.triage
check(t.rangeSpell == "Flash Heal" and t.rangeTried == "Lesser Heal,Heal,Flash Heal", "fallback: " .. tostring(t.rangeSpell) .. " / " .. tostring(t.rangeTried))
check(t.party1InRangeOfHeal.r1.type == "nil" or t.party1InRangeOfHeal.r1.value == true, "party read uses the chosen spell")
runCmd("priest off")
C_Spell.IsSpellInRange = function() end
runCmd("priest")
t = ForeverSTUwaveDB.fscheck.priest.ooc.triage
check(t.rangeSpell == "none answered" and t.rangeTried == "Lesser Heal,Heal,Flash Heal,Renew,Power Word: Shield", "none answered: " .. tostring(t.rangeSpell))
"""
)

case("priest_without_c_timer_snapshots_at_once_and_says_why")(
    r"""
priestMock()
C_Timer.After = nil
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
check(type(p.meta.timerError) == "string", "missing stop timer must be recorded")
__combat = true
pfire("PLAYER_REGEN_DISABLED")
check(p.combat and p.combat.inCombat == true, "no timer: the combat snapshot is taken at once")
check(type(p.meta.delay) == "string", "the missing delay timer must be recorded")
scan(p)
"""
)

case("priest_secret_gettime_marks_entries_notime")(
    r"""
priestMock()
runCmd("priest")
local p = ForeverSTUwaveDB.fscheck.priest
pfire("UNIT_POWER_UPDATE", "player", "MANA")
GetTime = function() return SN end
pfire("UNIT_POWER_UPDATE", "player", "MANA")
pfire("UNIT_SPELLCAST_SUCCEEDED", "player", "c", 585)
local e = p.logs.power.entries
check(e[1].t and e[2].noTime == true and e[2].t == nil and e[2].gap == nil, "a secret GetTime must give noTime and no arithmetic")
check(p.logs.cast.entries[1].noTime == true, "cast entry noTime")
scan(p)
"""
)

case("priest_usage_lists_the_command")(
    r"""
runCmd("help")
check(said("/fscheck priest"), "usage must list /fscheck priest")
"""
)

# --- /fscheck shaman -----------------------------------------------------------------------------

case("shaman_usage_lists_the_command")(
    r"""
runCmd("help")
check(said("/fscheck shaman"), "usage must list /fscheck shaman")
check(said("shaman buttons") and said("shaman setslot") and said("shaman destroy"), "usage must list the explicit subcommands")
"""
)

case("shaman_command_snapshot_covers_the_checklist")(
    r"""
shamanMock({ [8071] = true, [36936] = true })
shamanFrames(true)
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s and s.ooc and s.ooc.kind == "ooc" and s.ooc.inCombat == false, "ooc snapshot tagged false")
check(s.meta.status == "logging", "status: " .. tostring(s.meta.status))
local o = s.ooc
-- player
check(o.classToken == "SHAMAN" and o.player.classToken == "SHAMAN" and o.player.level.r1.value == 4, "class and level")
check(o.player.numTotemSlots.r1.value == 4, "GetNumTotemSlots")
check(o.player.constants.FIRE_TOTEM_SLOT == 1 and o.player.constants.EARTH_TOTEM_SLOT == 2
    and o.player.constants.WATER_TOTEM_SLOT == 3 and o.player.constants.AIR_TOTEM_SLOT == 4, "slot constants")
check(o.player.priorities == "2,1,3,4", "SHAMAN_TOTEM_PRIORITIES: " .. tostring(o.player.priorities))
-- totem state: every return of GetTotemInfo, plain or secret per field
local e = o.totems.slots.s2
check(e.info.r1.value == true and e.info.r2.value == "Stoneskin Totem" and e.info.r3.value == 990
    and e.info.r4.value == 300 and e.info.r5.value == 136098 and e.info.r6.value == 1 and e.info.r7.value == 8071
    and e.info.inCombat == false, "GetTotemInfo, all seven returns")
check(string.find(e.brief, "string/plain=Stoneskin Totem", 1, true), "brief: " .. tostring(e.brief))
check(e.timeLeft.r1.value == 250 and e.cannotDismiss.exists, "GetTotemTimeLeft and GetTotemCannotDismiss")
check(e.duration.object == "table/plain" and e.duration.GetRemainingDuration.r1.value == 250
    and e.duration.IsZero.r1.value == false and e.duration.GetTotalDuration.r1.value == 300, "GetTotemDuration object: " .. tostring(e.duration.object))
check(e.duration.sweep == "ok" and e.duration.statusBar.setTimerDuration == "ok", "duration object into a Cooldown and a StatusBar")
check(e.tooltip and string.find(e.tooltip, "id=number/plain=8071", 1, true), "C_TooltipInfo.GetTotem: " .. tostring(e.tooltip))
check(o.totems.slots.s1.info.r1.value == false and o.totems.active == 1 and o.totems.slots.s4.slot == 4, "empty slots and the live count")
-- secrecy predicates
check(o.secrets.calls["ShouldTotemSlotBeSecret(2)"].r1.type == "boolean", "slot predicate")
check(o.secrets.totemSpells["Stoneskin Totem"] == "boolean/plain=false", "spell predicate: " .. tostring(o.secrets.totemSpells["Stoneskin Totem"]))
-- native bar (P2, P10)
local m = o.multicast
check(m.barIndex.r1.value == 12 and m.hasBar.r1.value == false, "bar index and HasMultiCastActionBar")
check(m.pages.p1 == "boolean/plain=true" and m.pages.p2 == "boolean/plain=false", "HasMultiCastActionPage")
check(m.spellsByAction.a2.count == 1 and string.find(m.spellsByAction.a2.entries[1], "8071 Stoneskin Totem", 1, true), "GetMultiCastTotemSpells(2)")
check(m.spellsByAction.a1.count == 0, "GetMultiCastTotemSpells(1) answers nothing at level 4")
check(m.actions.set1slot2.id == 134 and m.actions.set1slot2.hasAction == "boolean/plain=true"
    and string.find(m.actions.set1slot2.info, "string/plain=spell,number/plain=8071", 1, true), "action id (12-1)*12+2 is slotted")
check(m.actions.set1slot1.hasAction == "boolean/plain=false" and m.actions.set3slot4.id == 144, "action ids for 3 sets x 4 slots")
-- frames (P10), rects and the overlap with our action bar group
local fr = o.frames.list
check(fr.MultiCastActionBarFrame.exists and fr.MultiCastActionBarFrame.shown == true, "bar frame shown")
check(fr.MultiCastActionBarFrame.rect == "500,100,300,50" and fr.MultiCastActionBarFrame.size == "300,50", "bar rect: " .. tostring(fr.MultiCastActionBarFrame.rect))
check(fr.MultiCastActionBarFrame.scale == 1 and fr.MultiCastActionBarFrame.points.p1.point == "BOTTOM", "scale and anchor")
check(fr.MultiCastSlotButton1.exists and fr.MultiCastSummonSpellButton.shown == false, "slot and summon buttons")
check(fr.MultiCastRecallSpellButton.exists == false and fr.TotemFrame.exists, "an absent frame is recorded absent")
check(o.frames.overlap["MultiCastActionBarFrame/FSActionBarStack"] == "overlaps", "overlap: " .. tostring(o.frames.overlap["MultiCastActionBarFrame/FSActionBarStack"]))
-- spells: names and ids, known or not
check(o.spells.stoneskin.s8071.isPlayerSpell == "boolean/plain=true" and o.spells.recall.s36936.spellName == "Totemic Recall", "spell ids and names")
check(o.cooldowns.stoneskin.s8071.durationObject and o.cooldowns.recall.s36936.cooldown, "cooldown reads for a known spell")
check(o.cooldowns.coe.skipped == "not known", "an unknown spell is not read")
-- what could not run
local c = o.checks
check(c.notRunCount > 0 and #c.notRun == c.notRunCount, "notRun list")
check(string.find(c.spellsKnown, "Stoneskin Totem", 1, true) and string.find(c.spellsNotKnown, "Call of the Elements", 1, true), "known and unknown spell lists")
check(string.find(table.concat(c.notRun, "|"), "Call of the Elements", 1, true), "an unknown set spell is named")
check(said("could not run"), "chat must say which checks could not run")
-- events
local f = sframe()
check(f._events.PLAYER_TOTEM_UPDATE == true and f._events.UPDATE_MULTI_CAST_ACTIONBAR == true and f._events.PLAYER_REGEN_DISABLED == true, "events")
check(f._events.UNIT_SPELLCAST_SUCCEEDED == "unit:player" and f._events.UNIT_SPELLCAST_FAILED == "unit:player", "cast events are unit events")
check(__cleuAttempts == 0, "COMBAT_LOG_EVENT_UNFILTERED must never be registered (protected on Forever): " .. tostring(__cleuAttempts))
check(said("/fscheck shaman setslot") and said("/fscheck shaman buttons"), "short usage printed at start")
noOnUpdate()
scan(s)
"""
)

case("shaman_blank_gettotem_info_is_recorded_exactly")(
    r"""
shamanMock()
__totem[2] = { true, "", 0, 0, 0, 1, 0 }
runCmd("shaman")
local e = ForeverSTUwaveDB.fscheck.shaman.ooc.totems.slots.s2
check(e.info.r1.value == true and e.info.r2.value == "" and e.info.r2.isSecret == false, "blank name recorded as a plain empty string")
check(e.brief == "boolean/plain=true,string/plain=,number/plain=0,number/plain=0,number/plain=0,number/plain=1,number/plain=0", "brief: " .. tostring(e.brief))
check(e.looksBlank == true, "a live totem with no name is flagged")
check(ForeverSTUwaveDB.fscheck.shaman.ooc.totems.slots.s1.looksBlank == false, "an empty slot is not a blank report")
"""
)

case("shaman_low_level_names_what_could_not_run")(
    r"""
shamanMock()
runCmd("shaman")
local c = ForeverSTUwaveDB.fscheck.shaman.ooc.checks
local text = table.concat(c.notRun, "|")
for _, name in ipairs({ "Totemic Recall", "Call of the Elements", "Searing Totem", "Fire Nova" }) do
    check(string.find(c.spellsNotKnown, name, 1, true), name .. " must be listed as not known: " .. c.spellsNotKnown)
end
check(c.spellsKnown == "Stoneskin Totem (8071)", "known list: " .. tostring(c.spellsKnown))
check(string.find(text, "no totem was down", 1, true), "no live totem must be said: " .. text)
check(string.find(text, "MultiCastActionBarFrame", 1, true), "an absent native bar frame must be said")
check(string.find(text, "bar", 1, true) and string.find(text, "not shown", 1, true) or string.find(text, "absent", 1, true), "bar state")
check(ForeverSTUwaveDB.fscheck.shaman.ooc.cooldowns.searing.skipped == "no id", "a totem whose name does not resolve is not read")
check(said("checks could not run"), "chat line")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_combat_snapshot_follows_the_pull_and_sits_beside_the_ooc_one")(
    r"""
shamanMock()
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
__combat = true
sfire("PLAYER_REGEN_DISABLED")
advance(2)
check(s.combat == nil, "combat snapshot taken before the delay")
advance(2.1)
check(s.combat and s.combat.kind == "combat" and s.combat.inCombat == true, "combat snapshot tagged true")
check(s.combat.totems.slots.s2.info.inCombat == true and s.ooc.totems.slots.s2.info.inCombat == false, "both runs side by side")
check(sframe()._events.PLAYER_REGEN_DISABLED == nil, "REGEN_DISABLED still registered after the combat snapshot")
check(said("shaman: combat snapshot"), "combat line missing")
scan(s)
"""
)

case("shaman_totem_update_logs_a_readout_per_event")(
    r"""
shamanMock()
runCmd("shaman")
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
sfire("PLAYER_TOTEM_UPDATE", 2)
__totem[2] = nil
advance(1)
sfire("PLAYER_TOTEM_UPDATE", 2)
local log = ForeverSTUwaveDB.fscheck.shaman.logs.totem
check(log.total == 2 and #log.entries == 2, "two events logged")
local a, b = log.entries[1], log.entries[2]
check(a.event == "PLAYER_TOTEM_UPDATE" and a.argCount == 1 and a.slot.type == "number" and a.slot.isSecret == false and a.slot.value == 2, "slot argument plain")
check(string.find(a.info, "string/plain=Stoneskin Totem", 1, true) and string.find(a.timeLeft, "number/plain=250", 1, true), "readout of the totem")
check(string.find(b.info, "boolean/plain=false", 1, true) and b.inCombat == false and b.gap == 1, "the dismissal reads empty: " .. tostring(b.info))
check(a.all == nil, "a plain slot reads that slot only")
"""
)

case("shaman_totem_update_with_a_secret_slot_reads_every_slot", "secret")(
    r"""
shamanMock()
runCmd("shaman")
sfire("PLAYER_TOTEM_UPDATE", SN)
local e = ForeverSTUwaveDB.fscheck.shaman.logs.totem.entries[1]
check(e.slot.isSecret == true and e.slot.value == nil, "a secret slot is described, not stored")
check(e.info == nil and e.all.s1 and e.all.s4, "every slot is read instead")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_cast_and_multicast_logs")(
    r"""
shamanMock()
runCmd("shaman")
sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 8071)
sfire("UNIT_SPELLCAST_SUCCEEDED", "party1", "Cast-2", 8071)
sfire("UNIT_SPELLCAST_FAILED", "player", "Cast-3", 2484)
sfire("UPDATE_MULTI_CAST_ACTIONBAR")
local logs = ForeverSTUwaveDB.fscheck.shaman.logs
check(logs.cast.total == 2 and logs.cast.entries[1].spellName == "Stoneskin Totem" and logs.cast.entries[2].event == "UNIT_SPELLCAST_FAILED", "player casts only, with the spell name")
check(logs.cast.entries[1].spellID.value == 8071 and logs.cast.entries[1].inCombat == false, "cast entry")
check(logs.multicast.total == 1 and string.find(logs.multicast.entries[1].hasBar, "boolean/plain=false", 1, true), "multicast update logged with a readout")
"""
)

case("shaman_logs_are_capped_ring_buffers")(
    r"""
shamanMock()
runCmd("shaman")
for i = 1, 130 do sfire("PLAYER_TOTEM_UPDATE", 2) end
for i = 1, 70 do sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-" .. i, 8071) end
local logs = ForeverSTUwaveDB.fscheck.shaman.logs
check(#logs.totem.entries == logs.totem.cap and logs.totem.cap == 100 and logs.totem.total == 130 and logs.totem.dropped == 30, "totem log capped at 100")
check(#logs.cast.entries == 50 and logs.cast.total == 70 and logs.cast.dropped == 20, "cast log capped at 50")
"""
)

case("shaman_snapshot_with_secret_values_stores_only_plain_data", "secret")(
    r"""
shamanMock()
shamanFrames(true)
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s.ooc.classToken == "unknown", "a secret class fails closed")
check(s.ooc.totems.slots.s2.info.r1.isSecret == true and s.ooc.totems.slots.s2.info.r1.value == nil, "secret totem info is described only")
check(s.ooc.totems.slots.s2.looksBlank == nil or s.ooc.totems.slots.s2.looksBlank == "unknown", "no verdict on a secret read")
sfire("UNIT_SPELLCAST_SUCCEEDED", SS, SS, SN)
sfire("UNIT_SPELLCAST_FAILED", SS, SS, SN)
sfire("PLAYER_TOTEM_UPDATE", SN)
sfire("UPDATE_MULTI_CAST_ACTIONBAR")
__combat = true
sfire("PLAYER_REGEN_DISABLED")
advance(4)
check(s.combat and s.combat.totems, "combat snapshot taken")
runCmd("shaman setslot")
runCmd("shaman destroy")
scan(s)
"""
)

case("shaman_every_api_throws", "throw")(
    r"""
shamanMock()
shamanFrames(true)
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s and s.ooc and s.meta.status == "logging", "snapshot saved despite every API throwing")
sfire("PLAYER_TOTEM_UPDATE", 2)
sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 8071)
sfire("UPDATE_MULTI_CAST_ACTIONBAR")
runCmd("shaman setslot")
runCmd("shaman destroy")
runCmd("shaman buttons")
runCmd("shaman buttons off")
local f = sframe()
runCmd("shaman off")
check(nevents(f) == 0, "off unregisters")
scan(s)
"""
)

case("shaman_even_createframe_throws", "throw")(
    r"""
__frameThrows = true
shamanMock()
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s.ooc and s.meta.status == "no frame", "snapshot saved, nothing armed: " .. tostring(s.meta.status))
runCmd("shaman buttons")
runCmd("shaman buttons off")
scan(s)
"""
)

case("shaman_nothing_protected_or_blocked_runs_automatically")(
    r"""
shamanMock({ [8071] = true, [2484] = true, [36936] = true })
shamanFrames(true)
__mcSpells[2] = { 8071, 2484 }
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman")
__combat = true
sfire("PLAYER_REGEN_DISABLED")
advance(4)
sfire("PLAYER_TOTEM_UPDATE", 2)
sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 8071)
sfire("UPDATE_MULTI_CAST_ACTIONBAR")
__combat = false
sfire("PLAYER_REGEN_ENABLED")
advance(2)
runCmd("shaman")
check(#__setCalls == 0, "SetMultiCastSpell must only run from /fscheck shaman setslot: " .. #__setCalls)
check(#__destroyCalls == 0, "DestroyTotem must only run from /fscheck shaman destroy: " .. #__destroyCalls)
check(blizzTouched() == 0, "Blizzard's totem frames must never be changed: " .. select(2, blizzTouched()))
check(FSCheckShamanBtn1 == nil and FSCheckShamanStrip == nil, "no totem button row unless asked")
"""
)

case("shaman_setslot_is_explicit_and_records_the_result")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
runCmd("shaman")
__combat = true
runCmd("shaman setslot")
check(#__setCalls == 2, "one pick and one restore: " .. #__setCalls)
check(__setCalls[1][1] == 134 and __setCalls[1][2] == 2484 and __setCalls[1][3] == true, "picks the other known totem on the earth slot, in combat")
check(__setCalls[2][1] == 134 and __setCalls[2][2] == 8071, "restores the previous pick")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.inCombat == true and r.actionId == 134 and r.slot == 2 and r.spellId == 2484 and r.previousSpellId == 8071, "run record")
check(r.call.ok == true and r.changed == true and r.restore.call.ok == true, "call results")
check(string.find(r.before.info, "number/plain=8071", 1, true) and string.find(r.after.info, "number/plain=2484", 1, true), "before and after readouts")
check(said("SetMultiCastSpell(134, 2484)") and said("ADDON_ACTION_BLOCKED"), "the chat line comes before the call and names the risk")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_setslot_with_nothing_to_pick_calls_nothing")(
    r"""
shamanMock()
__mcSpells = {}
runCmd("shaman setslot")
check(#__setCalls == 0, "no spell list, no call")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(type(r.skipped) == "string" and string.find(r.skipped, "no totem spells", 1, true), "skip reason recorded: " .. tostring(r.skipped))
check(said("setslot"), "chat line")
"""
)

case("shaman_destroy_is_explicit_and_records_before_and_after")(
    r"""
shamanMock()
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman destroy")
check(#__destroyCalls == 1 and __destroyCalls[1][1] == 2, "the first live slot is dismissed")
local r = ForeverSTUwaveDB.fscheck.shaman.destroy.runs[1]
check(r.slot == 2 and r.call.ok == true and string.find(r.before, "boolean/plain=true", 1, true) and string.find(r.after, "boolean/plain=false", 1, true), "before and after")
runCmd("shaman destroy 3")
check(#__destroyCalls == 2 and __destroyCalls[2][1] == 3, "an explicit slot")
runCmd("shaman destroy 9")
check(#__destroyCalls == 2, "a bad slot is refused")
"""
)

case("shaman_buttons_strip_is_built_out_of_combat_with_the_right_attributes")(
    r"""
shamanMock({ [8071] = true, [2484] = true, [36936] = true })
runCmd("shaman buttons")
local b1, b2, b3 = FSCheckShamanBtn1, FSCheckShamanBtn2, FSCheckShamanBtn3
check(b1 and b2 and b3, "three buttons")
check(b1._tmpl == "SecureActionButtonTemplate" and b2._tmpl == "SecureActionButtonTemplate" and b3._tmpl == "SecureActionButtonTemplate", "secure templates")
check(b1._attrs.type1 == "destroytotem" and b1._attrs["totem-slot1"] == 1 and b1._attrs.type2 == "destroytotem" and b1._attrs["totem-slot2"] == 2, "dismiss slots 1 and 2")
check(b1._attrs["shift-type1"] == "destroytotem" and b1._attrs["shift-totem-slot1"] == 3 and b1._attrs["shift-totem-slot2"] == 4, "dismiss slots 3 and 4 on shift")
check(b2._attrs.type == "macro" and b2._attrs.macrotext == "/castsequence reset=combat/15 Stoneskin Totem, Earthbind Totem", "castsequence: " .. tostring(b2._attrs.macrotext))
check(b3._attrs.type == "spell" and b3._attrs.spell == "Totemic Recall", "recall")
check(FSCheckShamanStrip._shown == true and FSCheckShamanStrip._parent == UIParent, "strip shown on UIParent")
check(ForeverSTUwaveDB.fscheck.shaman.meta.status == "logging", "logging starts with the strip")
check(said("TOTEM BUTTONS") and said("buttons off"), "usage line")
local st = ForeverSTUwaveDB.fscheck.shaman.strip
check(st.shown == true and st.buttons.castsequence.macrotext == b2._attrs.macrotext and st.buttons.recall.spell == "Totemic Recall", "strip recorded")
runCmd("shaman buttons off")
check(FSCheckShamanStrip._shown == false and ForeverSTUwaveDB.fscheck.shaman.strip.shown == false, "hidden by buttons off")
runCmd("shaman buttons")
check(FSCheckShamanStrip._shown == true, "shown again")
check(FSCheckShamanBtn1 == b1 and b1._calls.HookScript == 2, "the buttons are built once and hooked once")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_buttons_skip_what_is_not_known")(
    r"""
shamanMock()
runCmd("shaman buttons")
local b2, b3 = FSCheckShamanBtn2, FSCheckShamanBtn3
check(b2._attrs.macrotext == "/castsequence reset=combat/15 Stoneskin Totem, Stoneskin Totem", "one known totem repeats: " .. tostring(b2._attrs.macrotext))
check(b3._attrs.type == nil and b3._attrs.spell == nil, "an unknown recall button carries no attribute")
local st = ForeverSTUwaveDB.fscheck.shaman.strip.buttons
check(string.find(st.recall.skipped, "Totemic Recall not known", 1, true), "reason: " .. tostring(st.recall.skipped))
shamanMock({})
runCmd("shaman buttons")
check(FSCheckShamanBtn2._attrs.macrotext == nil and string.find(ForeverSTUwaveDB.fscheck.shaman.strip.buttons.castsequence.skipped, "no totem known", 1, true), "no totem known")
"""
)

case("shaman_buttons_never_change_secure_frames_in_combat")(
    r"""
shamanMock()
__combat = true
runCmd("shaman buttons")
check(FSCheckShamanBtn1 == nil and FSCheckShamanStrip == nil, "nothing is built in combat")
check(said("leave combat"), "refusal line")
__combat = false
runCmd("shaman buttons")
local b = FSCheckShamanBtn1
local before = { b._calls.SetAttribute, b._calls.Show, b._calls.Hide, FSCheckShamanStrip._calls.Hide, FSCheckShamanStrip._calls.Show, FSCheckShamanStrip._calls.SetPoint }
__combat = true
runCmd("shaman buttons")
runCmd("shaman buttons off")
local after = { b._calls.SetAttribute, b._calls.Show, b._calls.Hide, FSCheckShamanStrip._calls.Hide, FSCheckShamanStrip._calls.Show, FSCheckShamanStrip._calls.SetPoint }
for i = 1, 6 do check(before[i] == after[i], "a secure frame call ran in combat, index " .. i) end
check(FSCheckShamanStrip._args.SetAlpha[1] == 0 and said("alpha 0"), "in combat the strip is only faded")
__combat = false
runCmd("shaman buttons off")
check(FSCheckShamanStrip._shown == false, "hidden once out of combat")
"""
)

case("shaman_click_outcomes_are_logged_with_what_followed")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
runCmd("shaman buttons")
local b = FSCheckShamanBtn1
check(type(b._hookScripts.PreClick) == "function" and type(b._hookScripts.PostClick) == "function", "click hooks")
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
b._hookScripts.PreClick(b, "RightButton", false)
__totem[2] = nil
sfire("PLAYER_TOTEM_UPDATE", 2)
b._hookScripts.PostClick(b, "RightButton", false)
advance(0.5)
sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 8071)
advance(4)
sfire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 8071)
local click = ForeverSTUwaveDB.fscheck.shaman.logs.click.entries[1]
check(click.event == "PreClick" and click.button == "dismiss" and click.mouse.value == "RightButton" and click.down.value == false, "click entry: " .. tostring(click.button))
check(string.find(click.totemsBefore.s2, "boolean/plain=true", 1, true) and string.find(click.post.totems.s2, "boolean/plain=false", 1, true), "state before and after the click")
check(type(click.post.t) == "number" and click.post.event == "PostClick", "post stamp")
check(#click.follow == 2 and click.follow[1].event == "PLAYER_TOTEM_UPDATE" and click.follow[2].event == "UNIT_SPELLCAST_SUCCEEDED" and click.follow[2].dt == 0.5,
    "events within 3 s follow the click, later ones do not: " .. #click.follow)
check(string.find(click.follow[2].what, "Stoneskin Totem", 1, true), "what followed")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_a_full_session_never_touches_blizzards_totem_frames")(
    r"""
shamanMock({ [8071] = true, [2484] = true, [36936] = true })
shamanFrames(true)
__mcSpells[2] = { 8071, 2484 }
runCmd("shaman")
runCmd("shaman buttons")
local b = FSCheckShamanBtn1
b._hookScripts.PreClick(b, "LeftButton", true)
sfire("PLAYER_TOTEM_UPDATE", 2)
b._hookScripts.PostClick(b, "LeftButton", true)
runCmd("shaman setslot")
runCmd("shaman destroy 2")
__combat = true
sfire("PLAYER_REGEN_DISABLED")
advance(4)
runCmd("shaman buttons off")
__combat = false
runCmd("shaman buttons off")
runCmd("shaman off")
runCmd("reset")
check(blizzTouched() == 0, "Blizzard's totem frames were changed: " .. select(2, blizzTouched()))
"""
)

case("shaman_off_timeout_reset_and_rearm")(
    r"""
shamanMock()
runCmd("shaman")
local f = sframe()
runCmd("shaman off")
check(nevents(f) == 0 and ForeverSTUwaveDB.fscheck.shaman.meta.status == "stopped", "off must unregister")
pcall(f._scripts.OnEvent, f, "PLAYER_TOTEM_UPDATE", 2)
check((ForeverSTUwaveDB.fscheck.shaman.logs.totem or { total = 0 }).total == 0, "an event after off was logged")
runCmd("shaman")
check(nevents(f) > 0, "restart must register again")
advance(1799)
check(nevents(f) > 0, "stopped early")
advance(2)
check(nevents(f) == 0 and ForeverSTUwaveDB.fscheck.shaman.meta.status == "timeout", "timeout must unregister")
runCmd("shaman")
runCmd("shaman off")
advance(600)
runCmd("shaman")
advance(1201)
check(nevents(f) > 0 and ForeverSTUwaveDB.fscheck.shaman.meta.status == "logging", "a stale timer stopped the newer run")
runCmd("")
check(ForeverSTUwaveDB.fscheck.shaman and nevents(f) > 0, "main arm wiped or stopped the shaman check")
runCmd("shaman buttons")
runCmd("reset")
check(ForeverSTUwaveDB.fscheck == nil and nevents(f) == 0, "reset left shaman data or events")
check(FSCheckShamanStrip._shown == false, "reset hides the strip")
advance(5000)
check(ForeverSTUwaveDB.fscheck == nil, "a stale timer wrote after reset")
noOnUpdate()
"""
)

case("shaman_replacing_a_saved_record_says_so")(
    r"""
shamanMock()
runCmd("shaman")
check(not said("replacing the saved shaman record"), "nothing to replace on the first run")
runCmd("shaman off")
runCmd("shaman")
check(said("replacing the saved shaman record"), "a fresh start over a saved record must say so")
"""
)

# --- shaman review fixes: records survive, setslot restore, unreadable slots, combat hide, strip seat -------------

case("shaman_buttons_after_off_keeps_the_saved_record")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman")
sfire("PLAYER_TOTEM_UPDATE", 2)
runCmd("shaman setslot")
runCmd("shaman destroy 2")
runCmd("shaman buttons")
local s = ForeverSTUwaveDB.fscheck.shaman
local ooc, total, setRuns, destroyRuns = s.ooc, s.logs.totem.total, #s.setslot.runs, #s.destroy.runs
check(ooc and total >= 1 and setRuns == 1 and destroyRuns == 1, "setup")
runCmd("shaman off")
check(s.meta.status == "stopped", "stopped")
runCmd("shaman buttons")
local now = ForeverSTUwaveDB.fscheck.shaman
check(now == s and now.ooc == ooc, "buttons after off replaced the record")
check(now.logs.totem.total == total and #now.setslot.runs == setRuns and #now.destroy.runs == destroyRuns, "buttons after off lost logs or runs")
check(now.meta.status == "logging" and nevents(sframe()) > 0, "logging must be re-armed: " .. tostring(now.meta.status))
check(now.strip and now.strip.shown == true, "the strip is shown again")
check(not said("replacing the saved shaman record"), "buttons must not replace a record")
sfire("PLAYER_TOTEM_UPDATE", 2)
check(now.logs.totem.total == total + 1, "the kept log keeps growing")
scan(now)
"""
)

case("shaman_buttons_after_the_timeout_keeps_the_saved_record")(
    r"""
shamanMock()
runCmd("shaman")
sfire("PLAYER_TOTEM_UPDATE", 2)
runCmd("shaman setslot")
local s = ForeverSTUwaveDB.fscheck.shaman
local ooc = s.ooc
advance(1801)
check(s.meta.status == "timeout", "timed out")
runCmd("shaman buttons")
local now = ForeverSTUwaveDB.fscheck.shaman
check(now == s and now.ooc == ooc and now.logs.totem.total == 1 and now.setslot.runs[1], "the timeout then buttons wiped the record")
check(now.meta.status == "logging" and now.meta.resumed == 1, "re-armed and counted: " .. tostring(now.meta.resumed))
advance(1801)
check(now.meta.status == "timeout", "the re-armed run times out too")
"""
)

case("shaman_buttons_after_a_runs_only_record_takes_a_fresh_snapshot_and_keeps_the_runs")(
    r"""
shamanMock()
runCmd("shaman setslot")
local before = ForeverSTUwaveDB.fscheck.shaman
check(before and before.setslot and #before.setslot.runs == 1 and before.ooc == nil and before.meta == nil, "setup: a runs-only record")
runCmd("shaman buttons")
local now = ForeverSTUwaveDB.fscheck.shaman
check(now.ooc and now.ooc.kind == "ooc", "an ooc snapshot is taken at once, not left waiting for a regen event")
check(now.meta and now.meta.status == "logging", "a fresh meta is written")
check(now.setslot and #now.setslot.runs == 1, "the setslot run is carried over")
"""
)

case("shaman_buttons_with_no_record_starts_a_normal_check")(
    r"""
shamanMock()
runCmd("shaman buttons")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s.ooc and s.ooc.kind == "ooc" and s.meta.status == "logging", "no record: buttons starts the check as before")
"""
)

case("shaman_start_keeps_the_explicit_runs_and_the_strip")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
runCmd("shaman setslot")
runCmd("shaman destroy 2")
check(ForeverSTUwaveDB.fscheck.shaman.meta == nil, "explicit runs write without starting")
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
check(s.ooc and s.meta.status == "logging", "started")
check(s.setslot and #s.setslot.runs == 1 and s.destroy and #s.destroy.runs == 1, "a later /fscheck shaman erased the earlier runs")
for i = 1, 8 do runCmd("shaman setslot") end
check(#ForeverSTUwaveDB.fscheck.shaman.setslot.runs == 6, "runs stay capped: " .. #ForeverSTUwaveDB.fscheck.shaman.setslot.runs)
runCmd("shaman buttons")
sfire("PLAYER_TOTEM_UPDATE", 2)
runCmd("shaman off")
runCmd("shaman")
s = ForeverSTUwaveDB.fscheck.shaman
check(#s.setslot.runs == 6 and #s.destroy.runs == 1, "restart kept the runs")
check(s.strip and s.strip.shown == false and s.strip.buttons.dismiss, "restart kept the strip record")
check(s.logs.totem == nil or s.logs.totem.total == 0, "logs are reset for the new run")
check(s.ooc and s.combat == nil, "snapshots are reset for the new run")
runCmd("shaman setslot")
runCmd("shaman off")
runCmd("shaman")
check(#ForeverSTUwaveDB.fscheck.shaman.setslot.runs == 6, "merged and capped across restarts")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_setslot_prefers_the_native_buttons_action_id")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
__actions[137] = 8071
nativeFrame("MultiCastActionButton2", 0, 0, 30, 30, true)
MultiCastActionButton2.CalculateAction = function() return 137 end
runCmd("shaman setslot")
check(#__setCalls == 2 and __setCalls[1][1] == 137 and __setCalls[2][1] == 137 and __setCalls[2][2] == 8071, "the native button's id is used for the pick and the restore")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.actionId == 137 and r.actionSource == "native CalculateAction" and r.computedActionId == 134, "source recorded: " .. tostring(r.actionSource))
check(r.changed == true and r.previousSpellId == 8071, "ran against the native id")
check(blizzTouched() == 0, "the native button was only read")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_setslot_falls_back_to_the_computed_action_id")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
runCmd("shaman setslot")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.actionId == 134 and r.actionSource == "computed (bar-1)*12+slot" and r.computedActionId == nil, "no native button: " .. tostring(r.actionSource))
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
nativeFrame("MultiCastActionButton2", 0, 0, 30, 30, true)
MultiCastActionButton2.CalculateAction = function() return "x" end
runCmd("shaman setslot")
local r2 = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[2]
check(r2.actionId == 134 and r2.actionSource == "computed (bar-1)*12+slot", "an unusable CalculateAction falls back")
"""
)

case("shaman_setslot_on_an_empty_slot_says_it_cannot_restore")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
__actions[134] = nil
runCmd("shaman setslot")
check(#__setCalls == 1, "no previous pick, no restore call: " .. #__setCalls)
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.previousSpellId == nil and r.changed == "unknown", "run record")
check(type(r.restore.skipped) == "string" and r.restore.leftChanged == true, "restore skipped and the bar flagged: " .. tostring(r.restore.skipped))
check(said("slot left changed to") and said("Stoneskin Totem") and said("by hand"), "the chat line says the slot stays changed")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_setslot_does_not_restore_a_slot_that_is_not_a_plain_spell")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
__actions[134] = nil
__actionRaw[134] = { "macro", 8071, "" }
runCmd("shaman setslot")
check(#__setCalls == 1, "a macro's id is not a spell id to restore: " .. #__setCalls)
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.previousSpellId == nil and r.previousType == "macro", "previous type recorded: " .. tostring(r.previousType))
check(said("by hand"), "told to set it back by hand")
"""
)

case("shaman_setslot_with_unreadable_action_info_says_it_cannot_restore")(
    r"""
shamanMock({ [8071] = true, [2484] = true })
__mcSpells[2] = { 8071, 2484 }
GetActionInfo = function() return SS, SN, SS end
runCmd("shaman setslot")
check(#__setCalls == 1, "an unreadable slot is never restored")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(type(r.restore.skipped) == "string" and r.restore.leftChanged == nil, "restore skipped")
check(said("by hand") and said("unreadable"), "told to check and set it back by hand")
scan(ForeverSTUwaveDB.fscheck.shaman)
"""
)

case("shaman_setslot_with_only_one_totem_known_is_a_noop")(
    r"""
shamanMock()
__mcSpells[2] = { 8071 }
runCmd("shaman setslot")
local r = ForeverSTUwaveDB.fscheck.shaman.setslot.runs[1]
check(r.noop == true and r.spellId == 8071 and r.previousSpellId == 8071, "pick equals the current pick")
check(#__setCalls == 1 and r.changed == false, "one call, nothing changed")
check(string.find(r.restore.skipped, "no-op", 1, true), "restore skipped as a no-op: " .. tostring(r.restore.skipped))
check(said("no-op"), "chat says it was a no-op")
check(not said("by hand"), "nothing to put back")
"""
)

case("shaman_secret_totem_info_is_not_reported_as_no_totem", "secret")(
    r"""
shamanMock()
runCmd("shaman")
local s = ForeverSTUwaveDB.fscheck.shaman
local t = s.ooc.totems
check(t.unreadable == 4 and t.active == 0 and t.empty == 0, "counts: " .. tostring(t.unreadable) .. "/" .. tostring(t.active) .. "/" .. tostring(t.empty))
check(t.slots.s2.state == "unknown" and t.slots.s2.live == false, "a secret slot is unknown, not empty")
local text = table.concat(s.ooc.checks.notRun, "|")
check(not string.find(text, "no totem was down", 1, true), "a secret read is not an empty slot: " .. text)
check(string.find(text, "4 of 4 totem slots unreadable (secret)", 1, true), "unreadable slots are counted: " .. text)
check(said("unreadable (secret)"), "the chat line says it")
__combat = true
sfire("PLAYER_REGEN_DISABLED")
advance(4)
local ctext = table.concat(s.combat.checks.notRun, "|")
check(not string.find(ctext, "no totem was down", 1, true) and string.find(ctext, "unreadable (secret)", 1, true), "combat snapshot: " .. ctext)
scan(s)
"""
)

case("shaman_live_empty_and_unreadable_slots_are_counted_apart")(
    r"""
shamanMock()
__totem[2] = { true, "Stoneskin Totem", 990, 300, 136098, 1, 8071 }
runCmd("shaman")
local t = ForeverSTUwaveDB.fscheck.shaman.ooc.totems
check(t.active == 1 and t.empty == 3 and t.unreadable == 0, "counts")
check(t.slots.s2.state == "live" and t.slots.s1.state == "empty", "slot states")
local text = table.concat(ForeverSTUwaveDB.fscheck.shaman.ooc.checks.notRun, "|")
check(not string.find(text, "no totem was down", 1, true) and not string.find(text, "unreadable", 1, true), "a live totem and plain empties need no note: " .. text)
"""
)

case("shaman_off_in_combat_fades_then_hides_on_regen")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host, b1, b3 = FSCheckShamanStrip, FSCheckShamanBtn1, FSCheckShamanBtn3
local before = stripCalls()
__combat = true
runCmd("shaman buttons off")
check(callsMoved(before, stripCalls()) == "0:SetAlpha", "only SetAlpha may run in combat: " .. callsMoved(before, stripCalls()))
check(host._args.SetAlpha[1] == 0 and host._shown == true, "faded, not hidden")
check(said("stay clickable") and said("until combat ends"), "the chat line says the buttons stay clickable")
check(regenFrame() ~= nil, "a real hide is queued for PLAYER_REGEN_ENABLED")
fireRegen()
check(host._shown == true and callsMoved(before, stripCalls()) == "0:SetAlpha", "a regen event that still reads combat hides nothing")
__combat = false
fireRegen()
check(host._shown == false and host._calls.Hide == 1, "hidden on regen")
check(b1._args.EnableMouse[1] == false and b3._args.EnableMouse[1] == false, "mouse off on the secure buttons")
check(regenFrame() == nil, "the regen wait ends")
local st = ForeverSTUwaveDB.fscheck.shaman.strip
check(st.shown == false and st.faded == nil and st.hidePending == nil, "record says hidden")
"""
)

case("shaman_stop_off_in_combat_fades_then_hides_on_regen")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host = FSCheckShamanStrip
local before = stripCalls()
__combat = true
runCmd("shaman off")
check(callsMoved(before, stripCalls()) == "0:SetAlpha", "shaman off in combat: only SetAlpha: " .. callsMoved(before, stripCalls()))
check(said("stay clickable"), "shaman off in combat says the buttons stay clickable")
__combat = false
fireRegen()
check(host._shown == false and FSCheckShamanBtn2._args.EnableMouse[1] == false, "hidden on regen")
"""
)

case("shaman_timeout_in_combat_fades_then_hides_on_regen")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host = FSCheckShamanStrip
local before = stripCalls()
__combat = true
advance(1801)
check(ForeverSTUwaveDB.fscheck.shaman.meta.status == "timeout", "timed out")
check(callsMoved(before, stripCalls()) == "0:SetAlpha", "the timeout in combat: only SetAlpha: " .. callsMoved(before, stripCalls()))
check(host._shown == true and said("stay clickable"), "still shown and said so")
__combat = false
fireRegen()
check(host._shown == false and FSCheckShamanBtn1._args.EnableMouse[1] == false, "hidden on regen")
"""
)

case("shaman_reset_in_combat_fades_then_hides_on_regen")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host = FSCheckShamanStrip
local before = stripCalls()
__combat = true
runCmd("reset")
check(callsMoved(before, stripCalls()) == "0:SetAlpha", "reset in combat: only SetAlpha: " .. callsMoved(before, stripCalls()))
check(said("stay clickable"), "reset in combat says the buttons stay clickable")
__combat = false
fireRegen()
check(host._shown == false and FSCheckShamanBtn3._args.EnableMouse[1] == false, "hidden on regen")
check(ForeverSTUwaveDB.fscheck == nil, "the late hide does not bring the record back")
"""
)

case("shaman_buttons_again_cancels_the_queued_hide")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host = FSCheckShamanStrip
__combat = true
runCmd("shaman buttons off")
__combat = false
runCmd("shaman buttons")
check(host._shown == true and host._args.SetAlpha[1] == 1, "shown and opaque again")
check(regenFrame() == nil, "the queued hide is cancelled")
"""
)

case("shaman_strip_clears_the_target_cast_bar")(
    r"""
shamanMock()
runCmd("shaman buttons")
local host = FSCheckShamanStrip
local p = host._args.SetPoint
local size = host._args.SetSize
check(p[1] == "CENTER" and p[3] == "CENTER" and p[4] == 0, "centred on UIParent")
local bottom = p[5] - size[2] / 2
check(bottom >= __tcastTop + 30, "strip bottom " .. bottom .. " must clear the target cast bar top " .. __tcastTop .. " with a margin")
"""
)


def run_case(name: str, mode: str, body: str, source: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(f'__mode = "{mode}"')
    lua.execute(f"__tcastTop = {TCAST_TOP}")
    try:
        lua.eval("function(src) local fn = assert(loadstring(src, '@FSCheck.lua')); return fn('forever-stuwave', {}) end")(source)
    except LuaError as err:
        return f"FSCheck.lua failed to load: {err}"
    try:
        lua.execute(body)
    except LuaError as err:
        return str(err)
    return None


# A secret may be neither compared nor truth-tested, and the sentinel mock cannot see
# `x ~= nil` (Lua only calls __eq between two tables), so the one value this check holds
# raw is pinned by text: the first aura instance id must be tested with type().
FORBIDDEN_TEXT = ("first ~= nil", "first == nil", "if first then", "not first")


# The hot section never reads an aura, a duration, a bar value or a text: plain widget queries
# (IsShown, GetChildren, counts) only. Comments are stripped so the header may name what it forbids.
HOT_FORBIDDEN = (
    "C_UnitAuras", "GetAuraData", "GetUnitAura", "GetAuraDuration", "UnitAura", "UnitBuff", "UnitDebuff",
    "GetBuffData", "GetDebuffData", "GetValue", "GetText", "GetFormattedText", "GetMinMaxValues",
    "GetRemaining", "GetElapsed", "GetCooldownTimes", "GetTimerDuration",
)


def hot_section(source: str) -> str:
    start = source.index("local HP = {}")
    end = source.index("local function Reset(keepGunsight)")
    lines = [ln for ln in source[start:end].splitlines() if not ln.lstrip().startswith("--")]
    return "\n".join(lines)


# The priest section reads auras only by spell id or name and registers the restricted combat log
# event in exactly one place (the throwaway-frame trial). Comments are stripped like the hot section.
PRIEST_FORBIDDEN = (
    "OnUpdate", "UnitBuff", "UnitDebuff", "UnitAura(", "GetAuraDataByIndex", "GetAuraDataBySlot",
    "CombatLogGetCurrentEventInfo", "GetUnitAuras",
)


def priest_section(source: str) -> str:
    start = source.index("-- Class checks: the machinery /fscheck priest")
    end = source.index("-- /fscheck hot: can an engine AuraContainer")
    lines = [ln for ln in source[start:end].splitlines() if not ln.lstrip().startswith("--")]
    return "\n".join(lines)


# The sentinel mock cannot fault on ==, ~= or a truth test of a secret (LuaJIT only calls __eq between
# two tables and never __index for them), so the secret-mode cases cannot catch those. Pinned by text
# instead, in the priest section: a name that holds a raw event argument or a raw API return must not
# be compared, ordered, truth-tested or used as an and/or operand, bare or in grouping parentheses;
# the same for `...` and `select(n, ...)`. The right test for such a value is type(x) or IsSecret(x)
# (a call, so never flagged). Allowlist: (exact line, guard text that must appear in the four lines
# before it). String literals are blanked first, so the unit token "target" is not the argument `target`.
# `select("#", ...)` counts the arguments and is not a value.
RAW_NAMES = (
    "unit|guid|attacker|target|castGUID|spellID|info|powerType"       # event arguments
    "|dur|calc|curve|mine|absorbs|v|first|token|frame|cd|obj"          # raw API returns
)
RAW_ARG = rf"(?<![\w.])(?:{RAW_NAMES})(?![\w])"
CMP = r"(?:==|~=|<=|>=|<|>)"
KEYWORD = r"\b(?:not|if|while|elseif|and|or)\s+"
# a grouping parenthesis, not the call parenthesis of f(x)
GROUP = r"(?<![\w)\]])\(+\s*"
SELECT = r'select\((?!\s*"")[^()]*\.\.\.\)'
RAW_PATTERNS = [
    rf"{RAW_ARG}\s*{CMP}",
    rf"{CMP}\s*\(*\s*{RAW_ARG}",
    rf"{KEYWORD}\(*\s*{RAW_ARG}",
    rf"{RAW_ARG}\s+(?:and|or|then)\b",
    rf"{GROUP}{RAW_ARG}\s*\)+\s*(?:{CMP}|and\b|or\b|then\b)",
    # varargs
    rf"\.\.\.\s*{CMP}",
    rf"{CMP}\s*\(*\s*\.\.\.",
    rf"{KEYWORD}\(*\s*\.\.\.",
    rf"\.\.\.\s+(?:and|or)\b",
    rf"{GROUP}\.\.\.\s*\)+\s*(?:{CMP}|and\b|or\b|then\b)",
    # select(n, ...)
    rf"{SELECT}\s*{CMP}",
    rf"{CMP}\s*\(*\s*{SELECT}",
    rf"{KEYWORD}\(*\s*{SELECT}",
    rf"{SELECT}\s+(?:and|or|then)\b",
    rf"{GROUP}{SELECT}\s*\)+\s*(?:{CMP}|and\b|or\b|then\b)",
]
RAW_ALLOW = {"return guid == mine": "if IsSecret(guid) or type(guid)"}

# Each of these, added to the clean section, must be caught exactly once.
RAW_INJECTIONS = (
    'if unit == "player" then return end',
    "if unit ~= nil then return end",
    "if (unit) then return end",
    "if not (info) then return end",
    "if not info then return end",
    'if (guid) == "x" then return end',
    "if ( castGUID ) and 1 then return end",
    "local x = spellID and 1 or 2",
    "if dur then return end",
    "if calc == nil then return end",
    "if not curve then return end",
    'if mine ~= "x" then return end',
    "if v then return end",
    "if not absorbs then return end",
    "if not frame then return end",
    "if cd and 1 then return end",
    "if ... == 1 then return end",
    "if (...) then return end",
    "if not ... then return end",
    "local x = ... or 1",
    "if select(2, ...) == 1 then return end",
    "if not select(1, ...) then return end",
    "if (select(2, ...)) then return end",
    "local x = select(2, ...) or 1",
    "if select(2, ...) then return end",
)
# ... and these are the legal forms, which must stay quiet.
RAW_LEGAL = (
    'if type(unit) ~= "string" then return end',
    "if IsSecret(guid) then return end",
    'if select("#", ...) > 0 then return end',
    "local x = Desc((select(2, ...)), true)",
    'if type(dur) ~= "nil" and not IsSecret(dur) then return end',
)


def raw_arg_violations(priest: str) -> list[str]:
    lines = priest.splitlines()
    found = []
    for i, line in enumerate(lines):
        text = re.sub(r'"[^"]*"', '""', line).strip()
        if not any(re.search(pat, text) for pat in RAW_PATTERNS):
            continue
        guard = RAW_ALLOW.get(text)
        if guard and any(guard in prev for prev in lines[max(0, i - 4):i]):
            continue
        found.append(text)
    return found


CLEU_SOURCE_DIR = Path(__file__).resolve().parent.parent / "forever-stuwave"
CLEU_NAME = "COMBAT_LOG_EVENT_UNFILTERED"
CLEU_LITERAL_RE = re.compile(r"""(["'])\s*""" + CLEU_NAME + r"""\s*\1""")
# Each form must be caught (the quoted literal is the signal, so split lines and variables count);
# a comment mentioning the event name must not be.
CLEU_MUST_CATCH = {
    "method call": 'f:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED")',
    "function call": 'RegisterEvent(f, "COMBAT_LOG_EVENT_UNFILTERED")',
    "pcall form": 'pcall(frame.RegisterEvent, frame, "COMBAT_LOG_EVENT_UNFILTERED")',
    "unit event": 'f:RegisterUnitEvent("COMBAT_LOG_EVENT_UNFILTERED", "player")',
    "split across lines": 'f:RegisterEvent(\n    "COMBAT_LOG_EVENT_UNFILTERED"\n)',
    "local variable": 'local E = "COMBAT_LOG_EVENT_UNFILTERED"\nf:RegisterEvent(E)',
    "event table": 'local events = { \'COMBAT_LOG_EVENT_UNFILTERED\' }',
    "after a comment line": '-- note\nf:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED")',
}
CLEU_MUST_PASS = {
    "line comment": "-- COMBAT_LOG_EVENT_UNFILTERED is protected",
    "trailing comment": "local x = 1 -- COMBAT_LOG_EVENT_UNFILTERED",
    "block comment": "--[[\nCOMBAT_LOG_EVENT_UNFILTERED\n]]\nlocal x = 1",
}


def strip_lua_comments(text: str) -> str:
    """Blank out Lua comments (line and block), keeping string literals and line numbers."""
    out, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1]); i += 2; continue
            if c == quote or c == "\n":
                quote = None
            i += 1
        elif c in "\"'":
            quote = c; out.append(c); i += 1
        elif text.startswith("--", i):
            m = re.match(r"--\[(=*)\[", text[i:])
            end = text.find("]" + m.group(1) + "]", i) + len(m.group(1)) + 2 if m else -1
            if m and end >= i + 2:
                out.append("".join("\n" if ch == "\n" else " " for ch in text[i:end])); i = end
            else:
                j = text.find("\n", i)
                i = n if j < 0 else j
        else:
            out.append(c); i += 1
    return "".join(out)


def cleu_register_violations(files: dict[str, str]) -> list[str]:
    """file:line of every quoted COMBAT_LOG_EVENT_UNFILTERED in non-comment code (protected on Forever)."""
    return [f"{name}:{n}" for name, text in files.items()
            for n, line in enumerate(strip_lua_comments(text).splitlines(), 1) if CLEU_LITERAL_RE.search(line)]


def cleu_register_check(root: Path) -> int:
    files = {str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*.lua")}
    bad = cleu_register_violations(files)
    missed = [k for k, v in CLEU_MUST_CATCH.items() if not cleu_register_violations({"x.lua": v})]
    noisy = [k for k, v in CLEU_MUST_PASS.items() if cleu_register_violations({"x.lua": v})]
    if bad or missed or noisy or not files:
        print(f"FAIL  static: COMBAT_LOG_EVENT_UNFILTERED appears as a string literal in code (protected on Forever): {bad}; "
              f"forms NOT caught {missed}; comment forms wrongly flagged {noisy}; lua files scanned: {len(files)}")
        return 1
    print(f"ok    static: no quoted COMBAT_LOG_EVENT_UNFILTERED in non-comment code across {len(files)} Lua files "
          f"({len(CLEU_MUST_CATCH)} forms caught, {len(CLEU_MUST_PASS)} comment forms pass)")
    return 0


# --- the shaman check: protected calls only where Parker types them -------------------------------------------
# /fscheck shaman must never call a protected or blocked API by itself: SetMultiCastSpell and DestroyTotem run only
# inside the two subcommand functions, the secure attributes of the totem button row are written only inside the three
# sync functions (reached from SH.SyncStrip, which SH.ButtonsOn calls after refusing combat), and Blizzard's totem
# frames are only read. Pinned by text, because the mock cannot tell a protected call from a plain one.
SHAMAN_START = "-- /fscheck shaman: what a totem bar can read and do"
EXPLICIT_CALLS = {
    "SetMultiCastSpell": ("SH.SetSlot",),
    "DestroyTotem": ("SH.Destroy",),
    "ChangeMultiCastActionPage": (),
    "TargetTotem": (),
    "CastSpellByID": (),
    "RunScript": (),
}
STRIP_SYNC = ("SH.SyncDismiss", "SH.SyncCastSequence", "SH.SyncRecall")
BLIZZARD_TOTEM_NAMES = ("MultiCast", "TotemFrame")
BLIZZARD_MUTATORS = (":Set", ":Show", ":Hide", ":Enable", ":Disable", ":Register", ":Unregister", ":Hook", ":Clear",
                     "hooksecurefunc", ".SetScript", ".HookScript")


# Calls that are protected on the strip's frames or that hand a duration object to a widget: each lives in ONE function.
# STEP_CALLS are reached through GS.Step(widget, "Name", ...) so the name is a string; they are scanned over the whole class
# check region (core, priest, shaman), where P.Sweep (the hidden Cooldown) and SH.BarTrial (the hidden StatusBar) use them.
STEP_CALLS = {
    "SetCooldownFromDurationObject": ("P.Sweep",),
    "SetTimerDuration": ("SH.BarTrial",),
}
CLASS_CHECK_START = "-- Class checks: the machinery /fscheck priest and /fscheck shaman share"
# Show / SetPoint / EnableMouse on the strip happen only in these (BuildStrip and SyncStrip are reached only after
# SH.ButtonsOn refuses combat; RealHide checks combat itself).
STRIP_MUTATORS = ("Show", "SetPoint", "EnableMouse")
STRIP_MUTATOR_HOMES = ("SH.BuildStrip", "SH.SyncStrip", "SH.RealHide")
# Ways to reach a protected call without naming it as a call: a bracket lookup of its name, a dot reference (as in
# pcall(btn.SetAttribute, ...)), a string loader.
_PROTECTED_NAMES = "|".join([*EXPLICIT_CALLS, "SetAttribute"])
BANNED_FORMS = (
    (re.compile(rf"\[\s*[\"']({_PROTECTED_NAMES})[\"']\s*\]"), "bracket lookup of a protected call"),
    (re.compile(r"[\w\)\]]\.SetAttribute\b"), "SetAttribute as a dot reference"),
    (re.compile(r"\b(loadstring|getglobal|setfenv)\b|rawget\s*\(\s*_G"), "string loader or raw global lookup"),
)


def class_check_section(source: str) -> str:
    start = source.index(CLASS_CHECK_START)
    end = source.index("-- /fscheck hot: can an engine AuraContainer")
    return strip_lua_comments(source[start:end])


def step_call_violations(text: str) -> list[str]:
    """Lines naming a duration-object call outside the one reader that may use it (text is comment-free Lua)."""
    bad = []
    current = "(outside a function)"
    for line in text.splitlines():
        m = re.match(r"\s*function ([\w.:]+)\(", line)
        if m:
            current = m.group(1)
        for call, allowed in STEP_CALLS.items():
            if re.search(rf"\b{call}\b", line) and current not in allowed:
                bad.append(f"{call} used in {current}")
    return bad


def shaman_section(source: str) -> str:
    start = source.index(SHAMAN_START)
    end = source.index("-- /fscheck hot: can an engine AuraContainer")
    return strip_lua_comments(source[start:end])


def lua_functions(text: str) -> tuple[dict[str, str], str]:
    """Top-level `function NAME(...)` ... `end` blocks of comment-free Lua, by name, and the lines outside them."""
    out: dict[str, str] = {}
    outside = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"function ([\w.:]+)\(", lines[i])
        if not m:
            outside.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j] != "end":
            j += 1
        out[m.group(1)] = "\n".join(lines[i : j + 1])
        i = j + 1
    return out, "\n".join(outside)


def _calls_in(call: str, body: str) -> bool:
    """A lookup Api("call") or a bare reference outside string literals (a chat line may name the API)."""
    blanked = "\n".join(re.sub(r'"[^"]*"', '""', ln) for ln in body.splitlines())
    return bool(re.search(rf'Api\("{call}"\)', body) or re.search(rf"(?<![\w.]){call}(?![\w])|_G\.{call}\b", blanked))


def shaman_violations(text: str) -> list[str]:
    """Calls the shaman section makes where it must not (text is comment-free Lua of the section)."""
    bad = []
    funcs, outside = lua_functions(text)
    for call, allowed in EXPLICIT_CALLS.items():
        for name, body in funcs.items():
            if _calls_in(call, body) and name not in allowed:
                bad.append(f"{call} used in {name}")
        if _calls_in(call, outside):
            bad.append(f"{call} used outside a function")
    for name, body in funcs.items():
        if re.search(r"\bSetAttribute\b", body) and name not in STRIP_SYNC:
            bad.append(f"SetAttribute in {name}")
        for method in STRIP_MUTATORS:
            if re.search(rf"[:.]{method}\b", body) and name not in STRIP_MUTATOR_HOMES:
                bad.append(f"{method} in {name}")
        if re.search(r"strip\.host[.:]Hide\b|\bhost[.:]Hide\b", body) and name != "SH.RealHide":
            bad.append(f"strip hidden in {name}")
    for method in STRIP_MUTATORS:
        if re.search(rf"[:.]{method}\b", outside):
            bad.append(f"{method} used outside a function")
    for pattern, what in BANNED_FORMS:
        if pattern.search(text):
            bad.append(what)
    for line in text.splitlines():
        if any(n in line for n in BLIZZARD_TOTEM_NAMES) and any(m in line for m in BLIZZARD_MUTATORS):
            bad.append(f"Blizzard totem frame changed: {line.strip()}")
    if "hooksecurefunc" in text:
        bad.append("hooksecurefunc in the shaman section")
    return bad


def shaman_gate_problems(text: str) -> list[str]:
    """The strip is reached only through SH.ButtonsOn, after it refuses combat; hiding checks combat first."""
    funcs, _ = lua_functions(text)
    bad = []
    on = funcs.get("SH.ButtonsOn", "")
    if not on or "LockedDown(true)" not in on or on.find("LockedDown(true)") > on.find("SH.SyncStrip"):
        bad.append("SH.ButtonsOn must refuse combat before SH.SyncStrip")
    for name, body in funcs.items():
        if name != "SH.ButtonsOn" and "SH.SyncStrip" in body and name != "SH.SyncStrip":
            bad.append(f"SH.SyncStrip reached from {name}")
        if "SH.BuildStrip(" in body and name not in ("SH.SyncStrip", "SH.BuildStrip"):
            bad.append(f"SH.BuildStrip reached from {name}")
    gate = r"LockedDown\(true\)"
    real = funcs.get("SH.RealHide", "")
    first_gate = re.search(gate, real)
    first_hide = re.search(r"strip\.host\.Hide|EnableMouse", real)
    if not real or not first_gate or not first_hide or first_gate.start() > first_hide.start():
        bad.append("SH.RealHide must check combat before hiding or switching the mouse off")
    hide = funcs.get("SH.HideStrip", "")
    if not hide or not re.search(gate, hide) or "SH.RealHide()" not in hide or re.search(r"strip\.host\.Hide|EnableMouse", hide):
        bad.append("SH.HideStrip must check combat and leave the real hide to SH.RealHide")
    elif hide.find("SH.RealHide()") < re.search(gate, hide).start():
        bad.append("SH.HideStrip must check combat before SH.RealHide")
    for name, body in funcs.items():
        if "SH.RealHide(" in body and name not in ("SH.HideStrip", "SH.OnRegen", "SH.RealHide"):
            bad.append(f"SH.RealHide reached from {name}")
    for call, allowed in EXPLICIT_CALLS.items():
        for name in allowed:
            if f'Api("{call}")' not in funcs.get(name, ""):
                bad.append(f"{name} must hold the only {call} lookup")
    return bad


SHAMAN_MUST_CATCH = {
    "set slot from a handler": 'function SH.LogTotem(event)\n    local fn = Api("SetMultiCastSpell")\nend',
    "bare destroy": "function SH.Follow(e)\n    DestroyTotem(2)\nend",
    "destroy lookup in the snapshot": 'function SH.PartTotems(sec)\n    sec.x = Api("DestroyTotem")\nend',
    "attribute outside the sync functions": "function SH.LogCast(event)\n    button:SetAttribute(\"type\", nil)\nend",
    "blizzard frame shown": "function SH.PartFrames(sec)\n    MultiCastActionBarFrame:Show()\nend",
    "blizzard frame hooked": "function SH.PartFrames(sec)\n    hooksecurefunc(MultiCastActionBarFrame, \"Show\", f)\nend",
    "target totem": 'function SH.PartTotems(sec)\n    pcall(TargetTotem, 1)\nend',
    "destroy through _G brackets": 'function SH.Follow(e)\n    _G["DestroyTotem"](2)\nend',
    "set slot through _G dot": 'function SH.Follow(e)\n    _G.SetMultiCastSpell(1, 2)\nend',
    "attribute by bracket lookup": 'function SH.LogCast(event)\n    btn["SetAttribute"](btn, "type", nil)\nend',
    "attribute through pcall": 'function SH.LogCast(event)\n    pcall(btn.SetAttribute, btn, "type", nil)\nend',
    "attribute outside a function": 'local set = button.SetAttribute',
    "string loader": 'function SH.Follow(e)\n    loadstring("DestroyTotem(1)")()\nend',
    "strip shown from a handler": 'function SH.LogCast(event)\n    SH.strip.host:Show()\nend',
    "strip moved from a handler": 'function SH.LogCast(event)\n    SH.strip.host:SetPoint("CENTER")\nend',
    "mouse switched from a handler": 'function SH.LogCast(event)\n    SH.strip.buttons[1]:EnableMouse(true)\nend',
    "strip hidden from the fade": 'function SH.HideStrip(quiet)\n    pcall(strip.host.Hide, strip.host)\nend',
}
SHAMAN_MUST_PASS = {
    "set slot in its own function": 'function SH.SetSlot()\n    local fn = Api("SetMultiCastSpell")\nend',
    "destroy in its own function": 'function SH.Destroy(arg)\n    local fn = Api("DestroyTotem")\nend',
    "attribute in a sync function": "function SH.SyncRecall(button)\n    button:SetAttribute(\"type\", nil)\nend",
    "presence list entry": 'SH.API_LIST = {\n    { "DestroyTotem" }, { "SetMultiCastSpell" },\n}',
    "reading a blizzard frame": 'function SH.PartFrames(sec)\n    local rec = GS.Read(MultiCastActionBarFrame, "IsShown")\nend',
    "strip shown in the sync": 'function SH.SyncStrip()\n    strip.host:Show()\nend',
    "strip built in its function": 'function SH.BuildStrip()\n    host:SetPoint("CENTER")\nend',
    "strip really hidden": 'function SH.RealHide()\n    pcall(strip.host.Hide, strip.host)\n    pcall(b.EnableMouse, b, false)\nend',
    "global lookup by a computed name": 'function SH.PartFrames(sec)\n    local w = _G["MultiCastActionButton" .. i]\nend',
}


STEP_MUST_CATCH = {
    "cooldown fed from a handler": 'function SH.LogCast(event)\n    GS.Step(cd, "SetCooldownFromDurationObject", dur)\nend',
    "bar fed from the snapshot part": 'function SH.PartTotems(sec)\n    GS.Step(bar, "SetTimerDuration", dur)\nend',
    "bar fed from the cooldown reader": 'function P.Sweep(dur)\n    GS.Step(bar, "SetTimerDuration", dur)\nend',
    "direct method call": 'function SH.Follow(e)\n    bar:SetTimerDuration(dur)\nend',
}
STEP_MUST_PASS = {
    "the hidden cooldown": 'function P.Sweep(dur)\n    GS.Step(cd, "SetCooldownFromDurationObject", dur, true)\nend',
    "the hidden status bar": 'function SH.BarTrial(dur)\n    out.setTimerDuration = GS.Step(bar, "SetTimerDuration", dur)\nend',
}


def shaman_static_checks(source: str) -> int:
    text = shaman_section(source)
    failures = 0
    bad = shaman_violations(text)
    missed = [k for k, v in SHAMAN_MUST_CATCH.items() if not shaman_violations(text + "\n" + v)]
    noisy = [k for k, v in SHAMAN_MUST_PASS.items() if shaman_violations(v)]
    if bad or missed or noisy:
        failures += 1
        print(f"FAIL  static: shaman section: {bad}; forms NOT caught {missed}; legal forms wrongly flagged {noisy}")
    else:
        print(f"ok    static: SetMultiCastSpell / DestroyTotem run only in their subcommands, SetAttribute only in the strip sync, "
              f"Blizzard's totem frames are never changed ({len(SHAMAN_MUST_CATCH)} forms caught, {len(SHAMAN_MUST_PASS)} legal forms pass)")
    problems = shaman_gate_problems(text)
    if problems:
        failures += 1
        print(f"FAIL  static: shaman gates: {problems}")
    else:
        print("ok    static: the totem button row is built, shown, moved and un-muted only after SH.ButtonsOn refuses combat, "
              "and the real hide (Hide, EnableMouse false) checks combat itself and is reached only from HideStrip and the regen handler")
    cls = class_check_section(source)
    bad = step_call_violations(cls)
    vacuous = [c for c in STEP_CALLS if not re.search(rf"\b{c}\b", cls)]
    missed = [k for k, v in STEP_MUST_CATCH.items() if not step_call_violations(cls + "\n" + v)]
    noisy = [k for k, v in STEP_MUST_PASS.items() if step_call_violations(v)]
    if bad or vacuous or missed or noisy:
        failures += 1
        print(f"FAIL  static: duration-object calls: {bad}; not found at all {vacuous}; forms NOT caught {missed}; legal forms wrongly flagged {noisy}")
    else:
        print(f"ok    static: SetCooldownFromDurationObject and SetTimerDuration are called only in the snapshot readers P.Sweep and "
              f"SH.BarTrial ({len(STEP_MUST_CATCH)} forms caught, {len(STEP_MUST_PASS)} legal forms pass)")
    return failures


def static_checks(source: str) -> int:
    failures = 0
    priest = priest_section(source)
    bad = raw_arg_violations(priest)
    missed = [inj for inj in RAW_INJECTIONS if len(raw_arg_violations(priest + "\n    " + inj)) != 1]
    noisy = [leg for leg in RAW_LEGAL if raw_arg_violations(priest + "\n    " + leg)]
    if bad or missed or noisy:
        failures += 1
        print(f"FAIL  static: raw values in the class check sections (core, priest, shaman): compared or truth-tested {bad}; "
              f"injections NOT caught {missed}; legal forms wrongly flagged {noisy}")
    else:
        print(f"ok    static: no raw event argument or API return is compared or truth-tested in the class check sections (core, priest, shaman) "
              f"({len(RAW_INJECTIONS)} injected forms are caught, {len(RAW_LEGAL)} legal forms pass)")
    leaked = [n for n in PRIEST_FORBIDDEN if n in priest]
    if leaked:
        failures += 1
        print(f"FAIL  static: a class check section uses a forbidden aura/log API: {leaked}")
    else:
        print("ok    static: the class check sections read no aura by index or slot")
    failures += cleu_register_check(CLEU_SOURCE_DIR)
    failures += shaman_static_checks(source)
    hot = hot_section(source)
    leaked = [n for n in HOT_FORBIDDEN if n in hot]
    if leaked:
        failures += 1
        print(f"FAIL  static: the hot section calls an aura or value read API: {leaked}")
    else:
        print("ok    static: the hot section calls no aura, duration, bar value or text read API")
    reset = source[source.index("local function Reset(keepGunsight)"):source.index("local function SavedResults()")]
    if 0 <= reset.find('PP.Stop("reset", true)') < reset.find("GS.Disarm()"):
        print("ok    static: /fscheck reset stops the priest check before the gunsight and hot teardown")
    else:
        failures += 1
        print("FAIL  static: Reset must call PP.Stop before GS.Disarm / HP.Off")
    for needle in FORBIDDEN_TEXT:
        if needle in source:
            failures += 1
            print(f"FAIL  static: FSCheck.lua compares a possibly secret value: {needle!r}")
    if failures == 0:
        print("ok    static: the raw aura id is never compared with nil")
    return failures


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        failures = static_checks(source)
    print(captured.getvalue(), end="")
    static_total = sum(1 for ln in captured.getvalue().splitlines() if ln.startswith(("ok    static:", "FAIL  static:")))
    for name, mode, body in CASES:
        error = run_case(name, mode, body, source)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    total = len(CASES) + static_total
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
