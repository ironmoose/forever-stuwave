#!/usr/bin/env python3
"""Runs the real FSProbe.lua headless against a mock WoW API.

FSProbe.lua is the opt-in `/fsprobe` secret-value probe. It runs in the middle of a play
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
    recorder stops at 10, the AuraContainer test builds, shows for 30s and hides.

The mock is NOT the real client. Run:

    python3 tools/fsprobe-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "forever-stuwave" / "Modules/Diagnostics/FSProbe.lua"

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

-- Frames: a catch-all that records calls, plus the few methods the probe depends on.
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
        _args = {}, _at = {}, _shown = false }, FrameMT)
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
    if __registerThrows then error("boom: RegisterEvent " .. e) end
    self._events[e] = true
end
function FrameM.RegisterUnitEvent(self, e, ...)
    if __unitEventThrows then error("boom: RegisterUnitEvent") end
    self._events[e] = "unit:" .. table.concat({ ... }, ",")
end
function FrameM.UnregisterEvent(self, e) self._events[e] = nil end
function FrameM.UnregisterAllEvents(self) self._events = {} end
function FrameM.Show(self) self._shown = true; self._calls.Show = (self._calls.Show or 0) + 1 end
function FrameM.Hide(self) self._shown = false; self._calls.Hide = (self._calls.Hide or 0) + 1 end
function FrameM.IsShown(self) return self._shown end

-- AuraContainer: strict, only the methods the probe is allowed to call.
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
    local ok, err = pcall(SlashCmdList.FSPROBE, arg)
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
    check(ForeverSTUwaveDB.fsprobe.meta.status == "done", "run did not finish")
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
-- never explicitly shown, so a leftover Show is a probe test object left on screen).
function allHidden()
    for _, f in ipairs(__allFrames) do
        -- Buttons are the engine's own (it shows them); everything else is a probe test object.
        if f ~= UIParent and f._kind ~= "Button" then check(not f._shown, "a " .. tostring(f._kind) .. " test object is still shown") end
    end
end
-- A container whose AddAuraGroup builds `n` buttons through the group's initializeFrame (as the
-- engine does), with the few extra methods the AuraContainer probe reads. Returns the buttons.
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
-- `/fsprobe hot`: AddAuraSlot / AddAuraGroup build buttons through initializeFrame as the engine does,
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
function pull(dt)
    __combat = true
    fire("PLAYER_REGEN_DISABLED")
    advance(dt or 2)
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
    visit(root, "fsprobe")
    return stats
end
"""

# Each case: (name, mode, lua body). The mock is booted fresh per case and FSProbe.lua loaded.
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
check(SLASH_FSPROBE1 == "/fsprobe", "slash command not registered")
check(type(SlashCmdList.FSPROBE) == "function", "slash handler missing")
-- help and a bad argument must not arm anything either
runCmd("help")
runCmd("nonsense")
check(__apiCalls == 0 and #__frames == 0 and #__timers == 0, "help armed something")
check(said("/fsprobe reset"), "usage text missing")
""")

case("full_run_in_plain_mode")(r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
check(__apiCalls == calls, "status re-ran the probe")

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
for _, fr in ipairs(__frames) do if fr._name == "FSProbeAuraLabel" and fr._shown then labels = labels + 1 end end
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
check(ForeverSTUwaveDB.fsprobe == nil, "reset left results")
check(nevents(f) == 0, "reset left events")
""")

case("reset_cancels_pending_timers")(r"""
runCmd("")
__combat = true
fire("PLAYER_REGEN_DISABLED")
runCmd("reset")
advance(60)
check(ForeverSTUwaveDB.fsprobe == nil, "a stale timer wrote after reset")
check(nevents(evframe()) == 0, "events registered after reset")
""")

case("every_api_throws", "throw")(r"""
__issecretThrows = true
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
check(ForeverSTUwaveDB.fsprobe.ooc, "ooc snapshot should still be saved")
check(said("nothing armed"), "should say nothing is armed")
runCmd("")  -- not armed, so this is a fresh attempt, still no throw
runCmd("reset")
""")

case("secret_values_are_never_stored", "secret")(r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
check(ForeverSTUwaveDB.fsprobe.casts == nil, "a foreign unit was recorded")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "c", 5)
check(#ForeverSTUwaveDB.fsprobe.casts == 1, "player cast not recorded")
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
local rec = ForeverSTUwaveDB.fsprobe.auracontainer
check(rec.initError == nil and rec.initCalls == 2, "the swallowed failures leaked into initError: " .. tostring(rec.initError))
""")

case("combat_timer_fails_closed_when_the_lockdown_check_throws")(r"""
runCmd("")
__combat = true
fire("PLAYER_REGEN_DISABLED")
check(pendingTimers() == 1, "4s timer not scheduled")
__lockThrows = true
advance(4)
local db = ForeverSTUwaveDB.fsprobe
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
check(ForeverSTUwaveDB.fsprobe.ooc, "could not arm once out of combat")
""")

case("rerun_after_done_keeps_results")(r"""
complete()
local db = ForeverSTUwaveDB.fsprobe
runCmd("")
check(said("results exist, /reload to save or /fsprobe reset first"), "no results-exist line")
check(ForeverSTUwaveDB.fsprobe == db and db.combat and #db.casts == 10, "results were wiped")
check(nevents(evframe()) == 0, "re-armed over finished results")
""")

case("saved_results_from_an_earlier_session_are_kept")(r"""
ForeverSTUwaveDB = { fsprobe = { combat = { marker = true } } }
runCmd("")
check(said("results exist, /reload to save or /fsprobe reset first"), "no results-exist line")
check(ForeverSTUwaveDB.fsprobe.combat.marker == true, "saved combat results were wiped")
check(evframe() == nil, "armed over saved results")
runCmd("reset")
runCmd("")
check(ForeverSTUwaveDB.fsprobe.ooc, "could not re-arm after reset")
""")

case("saved_channel_results_alone_are_kept")(r"""
ForeverSTUwaveDB = { fsprobe = { channel = { { event = "marker" } } } }
runCmd("")
check(said("results exist, /reload to save or /fsprobe reset first"), "a saved channel table was not counted as results")
check(ForeverSTUwaveDB.fsprobe.channel[1].event == "marker", "saved channel results were wiped")
check(evframe() == nil, "armed over saved channel results")
""")

case("container_is_built_hidden_and_anchored_top_left")(r"""
runCmd("")
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check((ac._calls.Hide or 0) >= 1 and ac._shown == false, "container not hidden at build")
check(ac._args.SetPoint[1] == "TOPLEFT" and ac._args.SetPoint[4] == -100 and ac._args.SetPoint[5] == 200, "container not anchored TOPLEFT")
local label = _G.FSProbeAuraLabel
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
check(ForeverSTUwaveDB.fsprobe.auracontainer.steps.createFrame == "reused", "container not reused")
local containers, labels = 0, 0
for _, fr in ipairs(__frames) do
    if fr._kind == "AuraContainer" then containers = containers + 1 end
    if fr._name == "FSProbeAuraLabel" then labels = labels + 1 end
end
check(containers == 1, "containers built: " .. containers)
local ac
for _, fr in ipairs(__frames) do if fr._kind == "AuraContainer" then ac = fr end end
check(ac._calls.AddAuraGroup == 1, "AddAuraGroup called " .. tostring(ac._calls.AddAuraGroup) .. " times across reset + re-arm")
check(ForeverSTUwaveDB.fsprobe.auracontainer.steps.addAuraGroup == "reused", "re-arm did not record the group as reused")
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
check(ForeverSTUwaveDB.fsprobe.meta.lastError == nil and ForeverSTUwaveDB.fsprobe.auracontainer.retargetErrors == nil, "missing UpdateAllAuras was recorded as an error")
__ACM.UpdateAllAuras = saved
-- a present UpdateAllAuras that throws must not escape the handler, but is counted
__ACM.UpdateAllAuras = function() error("boom") end
fire("PLAYER_TARGET_CHANGED")
check(ac._calls.SetUnit == 4, "retarget handler did not complete when UpdateAllAuras threw")
check(ForeverSTUwaveDB.fsprobe.meta.lastError == nil, "a throwing UpdateAllAuras leaked into lastError")
check(ForeverSTUwaveDB.fsprobe.auracontainer.retargets == 3, "retarget not recorded when UpdateAllAuras threw")
check(ForeverSTUwaveDB.fsprobe.auracontainer.retargetErrors == 1, "a throwing UpdateAllAuras was not counted in retargetErrors")
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
local db = ForeverSTUwaveDB.fsprobe
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
local wl = ForeverSTUwaveDB.fsprobe.ooc.whitelist
check(wl.s21562.cast.exists == false and wl.s21562.aura.r1.value == 0, "absent cast secrecy not recorded as absent")
"""
)

case("w1_whitelist_secret_values_are_not_stored", "secret")(
    r"""
local IDS = """
    + WL_IDS
    + r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
local a = ForeverSTUwaveDB.fsprobe.unitAura
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
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("a2_ooc_events_cannot_spend_the_combat_budget")(
    r"""
runCmd("")
local x = xframe()
for i = 1, 40 do fire("UNIT_AURA", "player", { isFullUpdate = false }) end
local a = ForeverSTUwaveDB.fsprobe.unitAura
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
local pg = ForeverSTUwaveDB.fsprobe.procGlow
check(#pg == 20, "event cap: " .. #pg)
check(pg[1].event == SHOW and pg[2].event == HIDE, "event names")
check(pg[1].spellID.value == 17941 and pg[1].spellID.isSecret == false, "plain spellID kept")
check(pg[1].inCombatLockdown.r1.type == "boolean" and pg[1].inCombatLockdown.r1.value == false, "proc combat flag")
check(pg[1].time.r1.type == "number" and pg[1].time.r1.value == __now, "proc time")
check(x._events[SHOW] == nil and x._events[HIDE] == nil, "glow events left registered after the cap")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
local o = ForeverSTUwaveDB.fsprobe.combat.spellOverlay
check(o.shadowTranceOverlayed.r1.type == "boolean" and o.shadowTranceOverlayed.r1.value == false, "17941 overlay not in the combat snapshot")
check(o.shadowBoltOverlayed.r1.type == "boolean", "686 overlay missing")
"""
)

case("p1_secret_glow_spellid_is_not_stored", "secret")(
    r"""
runCmd("")
fire("SPELL_ACTIVATION_OVERLAY_GLOW_SHOW", SN)
local pg = ForeverSTUwaveDB.fsprobe.procGlow
check(#pg == 1 and pg[1].spellID.isSecret == true and pg[1].spellID.type == "number" and pg[1].spellID.value == nil, "secret spellID stored")
scan(ForeverSTUwaveDB.fsprobe)
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
local db = ForeverSTUwaveDB.fsprobe
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
-- 585 and 686 are known in the mock, in that order. A probe never reads the spell just cast
-- (its own cooldown would pollute the read), so a Shadow Bolt cast probes Smite ...
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.spellId == 585, "probe spell: " .. tostring(g.spellId))
check(g.isActive.value == true and g.isActive.isSecret == false and g.isOnGCD.value == true, "isActive not captured after the cast")
-- ... and a Smite cast probes Shadow Bolt
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 585)
check(db.casts[2].gcd.spellId == 686 and db.casts[2].gcd.isActive.value == true, "second cast not probed with the other spell")
-- the control read of the GCD marker (61304) rides in the same sample
local c = g.control
check(c and c.isActive.value == true and c.startTime.value == 1 and c.duration.value == 1.5, "control read missing")
check(c.time.r1.type == "number" and c.time.r1.value == __now, "control GetTime missing")
-- castTime comes from GetSpellInfo while it is plain
check(g.castTime.source == "spellinfo" and g.castTime.value == 2500, "castTime from spell info")
-- a probe spell is never the cast spell, even when it is the only one known
runCmd("reset")
__combat = false
KNOWN_ONLY(686)
runCmd("")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-3", 686)
local g3 = ForeverSTUwaveDB.fsprobe.casts[1].gcd
check(g3.spellId == nil and g3.skipped ~= nil and g3.control and g3.control.isActive.value == true,
    "the cast spell was probed, or the control read was lost")
"""
)

case("gcd_probe_skips_a_spell_that_has_its_own_cooldown")(
    r"""
-- Mind Blast (8092) has an 8s cooldown of its own, so it is not a GCD probe candidate
IsPlayerSpell = function() return true end
C_SpellBook.IsSpellKnown = IsPlayerSpell
runCmd("")
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 172)
check(ForeverSTUwaveDB.fsprobe.casts[1].gcd.spellId == 585, "first candidate: " .. tostring(ForeverSTUwaveDB.fsprobe.casts[1].gcd.spellId))
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 585)
check(ForeverSTUwaveDB.fsprobe.casts[2].gcd.spellId == 686, "after a Smite: " .. tostring(ForeverSTUwaveDB.fsprobe.casts[2].gcd.spellId))
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-3", 8092)
local id = ForeverSTUwaveDB.fsprobe.casts[3].gcd.spellId
check(id == 585, "Mind Blast cast probed " .. tostring(id))
"""
)

case("gcd_is_also_sampled_when_a_cast_starts")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
__issecrettableThrows = true
-- the aura info table is plain to issecretvalue, but the secrecy check blew up: count it as secret
fire("UNIT_AURA", "player", { isFullUpdate = false })
local r = db.unitAura[1]
check(r.info.issecrettable == true, "a throwing issecrettable was not recorded as secret")
check(r.fields == nil, "a table whose secrecy check threw was indexed")
-- the same rule for the cooldown tables of the GCD probe
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
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
check(db.casts[1].gcd.skipped == "no known spell", "nothing was known yet")
-- the spellbook loads later: the empty list must not have been cached
IsPlayerSpell = function() return true end
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-2", 686)
check(db.casts[2].gcd.spellId == 585, "empty known list was cached: " .. tostring(db.casts[2].gcd.spellId) .. " " .. tostring(db.casts[2].gcd.skipped))
scan(db)
"""
)

case("gcd_probe_skips_the_cast_spell_when_its_name_is_unavailable")(
    r"""
-- the cast spell's own name cannot be read, so the name compare alone would pick it
local oldName, oldInfo = C_Spell.GetSpellName, C_Spell.GetSpellInfo
C_Spell.GetSpellName = function(id) if id == 585 then return nil end return oldName(id) end
C_Spell.GetSpellInfo = function(id) if id == 585 then return nil end return oldInfo(id) end
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 585)
check(db.casts[1].gcd.spellId == 686, "probed the cast spell itself: " .. tostring(db.casts[1].gcd.spellId))
scan(db)
"""
)

case("gcd_probe_with_a_secret_cooldown_table_stores_nothing", "plain")(
    r"""
C_Spell.GetSpellCooldown = function() return ST end
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.spellId == 585 and g.call.r1.isSecret == true, "probe call not recorded as secret")
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
local db = ForeverSTUwaveDB.fsprobe
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
local g = db.casts[1].gcd
check(g.isActive == nil and g.control.isActive == nil, "indexed a table issecrettable calls secret")
scan(db)
"""
)

case("gcd_isactive_unknown_or_secret_is_not_stored", "secret")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 686)
check(db.casts[1].gcd.skipped == "no known spell", "unknown spells should skip the probe")
check(db.casts[1].gcd.control and db.casts[1].gcd.control.isActive.isSecret == true, "control read should still be taken")
runCmd("reset")
IsPlayerSpell = function() return true end
runCmd("")
db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
check(db.ooc.pet.unitExists.r1.value == true and db.ooc.pet.unitExists.r1.isSecret == false, "pet exists")
__combat = true
fire("PLAYER_REGEN_DISABLED")
advance(4)
check(db.combat.pet.unitExists.r1.type == "boolean", "pet missing from the combat snapshot")
runCmd("reset")
__combat = false
UnitExists = function() return SB end
runCmd("")
local r = ForeverSTUwaveDB.fsprobe.ooc.pet.unitExists.r1
check(r.isSecret == true and r.type == "boolean" and r.value == nil, "secret pet existence stored")
"""
)

case("shoot_events_go_to_their_own_capped_list")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
for i = 1, 3 do fire("UNIT_SPELLCAST_SUCCEEDED", "player", "s" .. i, 5019) end
fire("UNIT_SPELLCAST_CHANNEL_START", "player", "c1", 5019)
fire("UNIT_SPELLCAST_CHANNEL_UPDATE", "player", "c1", 5019)
fire("UNIT_SPELLCAST_CHANNEL_STOP", "player", "c1", 5019)
check(db.casts == nil and db.channel == nil, "Shoot was counted as a cast or channel")
check(#db.shoot == 6, "shoot events: " .. #db.shoot)
check(db.shoot[4].event == "UNIT_SPELLCAST_CHANNEL_START" and db.shoot[4].arg3.value == 5019, "shoot channel record")
check(db.shoot[4].time.r1.type == "number" and db.shoot[1].time.r1.type == "number", "shoot time")
for i = 1, 6 do check(db.shoot[i].gcd == nil, "Shoot event " .. i .. " got a GCD probe") end
for i = 1, 20 do fire("UNIT_SPELLCAST_SUCCEEDED", "player", "m" .. i, 5019) end
check(#db.shoot == 12, "shoot cap: " .. #db.shoot)
casts(10)
check(#db.casts == 10 and said("cast recorder saved"), "casts should still reach 10 after Shoot spam")
"""
)

case("channel_start_update_stop_record_secrecy_and_time")(
    r"""
runCmd("")
local db = ForeverSTUwaveDB.fsprobe
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
local db = ForeverSTUwaveDB.fsprobe
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
db = ForeverSTUwaveDB.fsprobe
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
local e = ForeverSTUwaveDB.fsprobe.meta.registerError
check(type(e) == "string", "no registerError recorded")
-- first and last failing registrations are both in the text, not just the last one
check(string.find(e, "UNIT_SPELLCAST_SUCCEEDED", 1, true), "first register error overwritten: " .. e)
check(string.find(e, "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", 1, true), "last register error missing: " .. e)
check(#e < 1200, "registerError grew without a cap: " .. #e)
check(ForeverSTUwaveDB.fsprobe.meta.lastError == nil, "arming threw: " .. tostring(ForeverSTUwaveDB.fsprobe.meta.lastError))
"""
)


case("gunsight_plain_run_stores_every_probe_with_plain_values")(
    r"""
runCmd("gunsight")
local gs = ForeverSTUwaveDB.fsprobe.gunsight
for _, k in ipairs({ "meta", "texcoord8", "vertexColorFromBoolean", "verticalBarTimer", "line", "auraApi",
                     "auraContainer", "alphaFromBoolean" }) do
    check(type(gs[k]) == "table", "missing probe " .. k)
end
check(gs.meta.buildVersion == "12.1.0" and gs.meta.buildNumber == "65000", "build info is not the plain version pair")
check(gs.meta.probeError == nil and gs.auraContainer.probeError == nil, "a probe threw")
check(type(gs.auraContainer.summary) == "string" and said("gunsight auraContainer:"), "no one-line summary")
check(gs.auraContainer.frameType == "ok" and gs.auraContainer.templateAccepted == true, "container not built")
check(gs.auraContainer.addAuraGroup == "ok" and gs.auraContainer.setUnit == "ok", "group or unit refused")
scan(ForeverSTUwaveDB.fsprobe)
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
check(FSProbeGsAuraContainer._calls.AddAuraGroup == 1, "the group was added again on a re-run")
check(ForeverSTUwaveDB.fsprobe.gunsight.auraContainer.addAuraGroup == "reused", "re-run did not reuse the group")
allHidden()
"""
)

case("gunsight_hides_the_bar_when_there_is_no_create_duration")(
    r"""
runCmd("gunsight")
allHidden()
check(ForeverSTUwaveDB.fsprobe.gunsight.verticalBarTimer.manual.skipped ~= nil, "no skip recorded")
"""
)

case("gunsight_hides_the_bar_when_create_duration_throws")(
    r"""
C_DurationUtil = { CreateDuration = function() error("boom: CreateDuration") end }
runCmd("gunsight")
allHidden()
check(string.find(ForeverSTUwaveDB.fsprobe.gunsight.verticalBarTimer.manual.skipped, "threw", 1, true), "throw not recorded")
"""
)

case("gunsight_hides_the_bar_when_the_run_is_superseded")(
    r"""
C_DurationUtil = { CreateDuration = function() return { SetTimeFromStart = function() end } end }
runCmd("gunsight")
runCmd("gunsight")   -- before the first run's 0.5s sample: its timer is now stale
advance(1)
allHidden()
local m = ForeverSTUwaveDB.fsprobe.gunsight.verticalBarTimer.manual
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
check(ForeverSTUwaveDB.fsprobe.gunsight.verticalBarTimer.cast.setTimerDuration == "ok", "cast duration not fed to the bar")
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
local ids = ForeverSTUwaveDB.fsprobe.gunsight.auraApi.ooc.ids
check(ids.firstIdSecret == true and ids.firstIdType == "number" and ids.firstId == "secret",
    "first id: " .. tostring(ids.firstIdSecret) .. " " .. tostring(ids.firstIdType) .. " " .. tostring(ids.firstId))
check(gotSecretId, "the secret id was not passed on to GetAuraDuration")
check(ForeverSTUwaveDB.fsprobe.gunsight.auraApi.ooc.durationOk == true, "duration read skipped for a secret id")
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("gunsight_combat_target_exists_false_is_recorded_as_false")(
    r"""
UnitExists = function() return false end
runCmd("gunsight")
pull(2)
for _ = 1, 10 do advance(2) end
local c = ForeverSTUwaveDB.fsprobe.gunsight.auraApi.combat
check(c and c.targetExists == false, "targetExists: " .. tostring(c and c.targetExists))
check(c.gaveUp == true, "did not give up after the attempts")
"""
)

case("gunsight_aura_container_engine_window_records_types_forwards_and_hides")(
    r"""
gsMockContainer(3)
local SECRET_DURATION = ST
runCmd("gunsight")
local rec = ForeverSTUwaveDB.fsprobe.gunsight.auraContainer
check(rec.initCalls == 3, "init callbacks: " .. tostring(rec.initCalls))
for _, step in ipairs({ "icon", "cooldown", "cooldownHook", "durationText", "applicationCount", "durationBar", "barHook" }) do
    check(rec.initSteps[step] == "ok", "init step " .. step .. ": " .. tostring(rec.initSteps[step]))
end
pull(2)
local container = FSProbeGsAuraContainer
check(container._shown == true and container._unit == "target", "container not pointed at the target and shown")
local cooldowns, bars = engineCalls(SECRET_DURATION)
check(cooldowns == 3 and bars == 3, "mock engine calls: " .. cooldowns .. " " .. bars)
advance(0.5)
advance(0.5)
local c = ForeverSTUwaveDB.fsprobe.gunsight.auraContainer.combat
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
scan(ForeverSTUwaveDB.fsprobe)
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
local c = ForeverSTUwaveDB.fsprobe.gunsight.auraContainer.combat
check(c.sampleError == nil and c.heightError == nil, "sample failed: " .. tostring(c.sampleError or c.heightError))
check(c.buttons.shown == 2 and c.buttons.unknown == 1, "a secret IsShown must count as unknown")
check(c.buttonDuration.secret == true and c.buttonDuration.type == "table", "secret duration not described")
check(c.engineBars.secret == 3 and c.engineBars.maxHeight == nil, "secret heights must not be stored")
check(c.fed.hook.height == "secret" and c.fed.get.height == "secret", "fed heights: " .. tostring(c.fed.hook.height))
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("gunsight_combat_end_before_capture_hides_the_container")(
    r"""
gsMockContainer(2)
UnitExists = function() return false end
runCmd("gunsight")
pull(2)
check(FSProbeGsAuraContainer._shown == true, "container not shown on the pull")
__combat = false
advance(2)
check(FSProbeGsAuraContainer._shown == false, "container left shown after combat ended")
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
check(FSProbeGsAuraContainer._shown == false, "reset left the container shown")
allHidden()
"""
)

case("gunsight_container_refusals_are_recorded")(
    r"""
__acCreateThrows = true
runCmd("gunsight")
local rec = ForeverSTUwaveDB.fsprobe.gunsight.auraContainer
check(string.find(rec.status, "frame type refused", 1, true), "create refusal: " .. tostring(rec.status))
check(ForeverSTUwaveDB.fsprobe.gunsight.alphaFromBoolean.texture ~= nil, "later probes did not run")
"""
)

case("gunsight_missing_template_is_recorded")(
    r"""
__template = false
runCmd("gunsight")
check(string.find(ForeverSTUwaveDB.fsprobe.gunsight.auraContainer.status, "template absent", 1, true), "template status")
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
scan(ForeverSTUwaveDB.fsprobe)
allHidden()
"""
)

case("gunsight_survives_a_failing_create_frame", "throw")(
    r"""
__frameThrows = true
runCmd("gunsight")
check(ForeverSTUwaveDB.fsprobe.gunsight.meta.hostError ~= nil, "host failure not recorded")
"""
)

case("hot_builds_samples_in_and_out_of_combat_and_tears_down")(
    r"""
hotMock(2)
runCmd("hot")
local player, party1 = FSProbeHot_player, FSProbeHot_party1
check(player and party1, "a container is missing for an existing token")
check(FSProbeHot_party2 == nil and FSProbeHot_party4 == nil, "a container was built for a token that does not exist")
check(player._unit == "player" and party1._unit == "party1", "containers not pointed at their token")
check(player._shown == true and player._args.SetEnabled[1] == true, "container not enabled and shown")
check(player._slotOpts.candidateFilters.includeSpellIDs[139] == true, "Renew rank 1 missing from includeSpellIDs")
check(player._slotOpts.candidateFilters.includeSpellIDs[9999] == true, "runtime rank missing from includeSpellIDs")
check(player._groupOpts.candidateFilters.maxDuration == 60, "group maxDuration")
local rec = ForeverSTUwaveDB.fsprobe.hot
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
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_refuses_to_build_in_combat")(
    r"""
hotMock(1)
__combat = true
runCmd("hot")
check(said("leave combat first"), "no refusal line")
check(FSProbeHot_player == nil and #__frames == 0, "a frame was built in combat")
check(ForeverSTUwaveDB == nil or ForeverSTUwaveDB.fsprobe == nil, "a result was written in combat")
check(pendingTimers() == 0, "a timer was scheduled in combat")
"""
)

case("hot_off_in_combat_only_drops_alpha_and_a_second_off_finishes_it")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSProbeHot_player
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
check(ForeverSTUwaveDB.fsprobe.hot.tokens.player.steps.addAuraSlot == "reused", "re-run did not reuse the container")
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
local player = FSProbeHot_player
player._groupBtns[1].IsShown = function() return SB end
player._groupBtns[2]._shown = true
advance(1)
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
check(string.find(row.samples[2], "unk=1", 1, true), "a secret IsShown must count as unknown: " .. tostring(row.samples[2]))
check(row.stats.ooc.unknown == 1 and row.stats.combat.unknown == 0, "unknown must be counted per bucket")
check(row.stats.ooc.withShown == 0 and row.stats.transitions == 0, "an unknown sample must not feed withShown or transitions")
scan(ForeverSTUwaveDB.fsprobe)
"""
)

# In combat the engine's buttons answer IsShown with a secret. That is "unknown", never "hidden":
# it must not count as a loss, a transition or a shown sample, and known, unknown, known must
# not register a transition.
case("hot_secret_buttons_in_combat_are_unknown_not_lost", "secret")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSProbeHot_player
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
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
local summary = ForeverSTUwaveDB.fsprobe.hot.summary
check(summary and string.find(summary, "unk 2", 1, true) and string.find(summary, "slotsecret 2", 1, true), "summary: " .. tostring(summary))
scan(ForeverSTUwaveDB.fsprobe)
"""
)

# A button that really drops out of combat is a transition, but never a loss IN combat.
case("hot_a_button_hidden_out_of_combat_is_a_transition_not_a_loss")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSProbeHot_player
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
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
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
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
check(ForeverSTUwaveDB.fsprobe.hot ~= nil and ForeverSTUwaveDB.fsprobe.ooc ~= nil, "re-arm wiped the hot result")
"""
)


# The HoT TIMER BAR shape: a second slot "renewbar" whose button gets a StatusBar driven by the engine
# (SetDurationBar), a bare-number text (SetDurationText with a numeric rule formatter and a step colour
# curve) and a pandemic overlay (AddPandemicRegion). Every step is pcall'd and recorded in barSteps.
case("hot_bar_slot_builds_the_timer_bar_and_records_every_step")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSProbeHot_player
local btn = player._barBtn
check(btn, "no renewbar slot was added")
check(player._barOpts.candidateFilters.includeSpellIDs[139] == true and player._barOpts.candidateFilters.includeSpellIDs[9999] == true,
    "bar slot must use the same Renew id set")
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
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
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_missing_bar_api_is_recorded_as_absent_and_nothing_throws")(
    r"""
hotMock(1)
__missing = { SetDurationBar = true, AddPandemicRegion = true }
runCmd("hot")
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
local bs = row.barSteps
check(bs.api.SetDurationBar == "nil" and bs.api.AddPandemicRegion == "nil" and bs.api.SetDurationText == "function", "types recorded")
check(bs.setDurationBar == "absent" and bs.addPandemicRegion == "absent", "missing methods must read absent: " .. tostring(bs.setDurationBar))
check(bs.bar == "ok" and bs.text == "ok" and bs.textMode == "custom" and bs.pandemicTexture == "ok", "the other steps must still run")
check(row.status == "built" and pendingTimers() == 1, "the probe must still build and sample")
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_whole_bar_api_absent_records_each_gap")(
    r"""
hotMock(1)
__missing = { SetDurationBar = true, SetDurationText = true, AddPandemicRegion = true }
Enum, C_StringUtil, C_CurveUtil, CreateColor = nil, nil, nil, nil
runCmd("hot")
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
local bs = row.barSteps
check(row.built == true and bs, "the container must still build with a bar record")
check(bs.api.SetDurationBar == "nil" and bs.api["Enum.StatusBarTimerDirection"] == "nil", "enum absence")
check(bs.api["Enum.StatusBarTimerDirection.RemainingTime"] == "nil", "enum field absence")
check(bs.api["C_StringUtil.CreateNumericRuleFormatter"] == "nil" and bs.api["C_CurveUtil.CreateColorCurve"] == "nil", "factory absence")
check(bs.setDurationBar == "absent" and bs.textDefault == "absent" and bs.textMode == "none", "text fallback must be recorded: " .. tostring(bs.textMode))
check(string.find(bs.textCustom, "absent", 1, true), "custom text error must name what is absent: " .. tostring(bs.textCustom))
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_a_throwing_bar_step_does_not_stop_the_next")(
    r"""
hotMock(1)
__FrameM.SetDurationBar = function() error("refused: SetDurationBar") end
__FrameM.SetReverseFill = function() error("refused: SetReverseFill") end
runCmd("hot")
local bs = ForeverSTUwaveDB.fsprobe.hot.tokens.player.barSteps
check(string.find(bs.setDurationBar, "refused: SetDurationBar", 1, true), "error text recorded: " .. tostring(bs.setDurationBar))
check(string.find(bs.barReverse, "refused: SetReverseFill", 1, true), "reverse fill error recorded: " .. tostring(bs.barReverse))
check(bs.barTrack == "ok" and bs.text == "ok" and bs.textMode == "custom" and bs.addPandemicRegion == "ok", "later steps still ran")
scan(ForeverSTUwaveDB.fsprobe)
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
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
local bs = row.barSteps
check(string.find(bs.textCustom, "bad textFormat", 1, true), "custom failure not recorded: " .. tostring(bs.textCustom))
check(bs.textDefault == "ok" and bs.textMode == "default", "default retry not recorded: " .. tostring(bs.textMode))
local btn = FSProbeHot_player._barBtn
check(btn._calls.SetDurationText == 2 and next(btn._args.SetDurationText[2]) == nil, "the retry must pass default options")
check(bs.addPandemicRegion == "ok", "the next step must still run")
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_a_throwing_formatter_factory_also_falls_back")(
    r"""
hotMock(1)
C_StringUtil.CreateNumericRuleFormatter = function() error("boom: factory") end
runCmd("hot")
local bs = ForeverSTUwaveDB.fsprobe.hot.tokens.player.barSteps
check(string.find(bs.textCustom, "boom: factory", 1, true), "factory error not recorded: " .. tostring(bs.textCustom))
check(bs.textMode == "default" and bs.textDefault == "ok", "must fall back to default opts")
"""
)

case("hot_a_refused_bar_slot_does_not_stop_the_group")(
    r"""
hotMock(2)
__slotThrows = { renewbar = "boom: AddAuraSlot renewbar" }
runCmd("hot")
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
check(string.find(row.steps.addBarSlot, "boom: AddAuraSlot renewbar", 1, true), "bar slot refusal not recorded: " .. tostring(row.steps.addBarSlot))
check(row.steps.addAuraSlot == "ok" and row.steps.addAuraGroup == "ok" and row.built == true, "slot and group must still build")
advance(1)
check(row.sampleErrors == nil, "sample failed: " .. tostring(row.firstSampleError))
check(string.find(row.samples[2], "bar=none", 1, true), "no bar slot samples as none: " .. tostring(row.samples[2]))
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_pandemic_and_bar_visibility_are_counted_and_secrets_are_unknown", "secret")(
    r"""
hotMock(1)
runCmd("hot")
local player = FSProbeHot_player
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
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
local summary = ForeverSTUwaveDB.fsprobe.hot.summary
check(string.find(summary, "barshown 3 barunk 2", 1, true), "bar summary: " .. tostring(summary))
check(string.find(summary, "pandemic 3 pandemicunk 2", 1, true), "pandemic summary: " .. tostring(summary))
check(__auraRead == false, "an aura, duration, bar value or text was read")
scan(ForeverSTUwaveDB.fsprobe)
"""
)

case("hot_rerun_keeps_the_bar_record_and_chat_tells_parker_what_to_watch")(
    r"""
hotMock(1)
runCmd("hot")
check(said("drain") and said("whole seconds") and said("amber") and said("pandemic"), "start line must say what to judge by eye")
runCmd("hot off")
runCmd("hot")
local row = ForeverSTUwaveDB.fsprobe.hot.tokens.player
check(row.steps.addBarSlot == "reused", "re-run must reuse the bar slot: " .. tostring(row.steps.addBarSlot))
check(row.barSteps and row.barSteps.bar == "ok" and row.barSteps.api, "re-run lost the bar record")
scan(ForeverSTUwaveDB.fsprobe)
"""
)


def run_case(name: str, mode: str, body: str, source: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.execute(f'__mode = "{mode}"')
    try:
        lua.eval("function(src) local fn = assert(loadstring(src, '@FSProbe.lua')); return fn('forever-stuwave', {}) end")(source)
    except LuaError as err:
        return f"FSProbe.lua failed to load: {err}"
    try:
        lua.execute(body)
    except LuaError as err:
        return str(err)
    return None


# A secret may be neither compared nor truth-tested, and the sentinel mock cannot see
# `x ~= nil` (Lua only calls __eq between two tables), so the one value this probe holds
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


def static_checks(source: str) -> int:
    failures = 0
    hot = hot_section(source)
    leaked = [n for n in HOT_FORBIDDEN if n in hot]
    if leaked:
        failures += 1
        print(f"FAIL  static: the hot section calls an aura or value read API: {leaked}")
    else:
        print("ok    static: the hot section calls no aura, duration, bar value or text read API")
    for needle in FORBIDDEN_TEXT:
        if needle in source:
            failures += 1
            print(f"FAIL  static: FSProbe.lua compares a possibly secret value: {needle!r}")
    if failures == 0:
        print("ok    static: the raw aura id is never compared with nil")
    return failures


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    failures = static_checks(source)
    for name, mode, body in CASES:
        error = run_case(name, mode, body, source)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    total = len(CASES) + 2
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
