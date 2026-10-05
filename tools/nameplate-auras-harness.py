#!/usr/bin/env python3
"""Runs the real ForeverSynthwave.lua (nameplates) headless against a mock WoW API.

Pins the nameplate debuff row: one AuraContainer per plate (the Plater design), so the
engine reads and draws the auras and no aura data ever enters addon Lua. The old path
(reparenting Blizzard's hidden AurasFrame, plus a custom row that only works out of combat)
is what these checks replaced.

  * the container path is used when CustomAuraContainerTemplate exists, the old custom row
    (and UNIT_AURA) only when it does not;
  * a container has two groups ("own" HARMFUL|PLAYER max 5, "other" HARMFUL|!PLAYER max 3),
    added once at creation, flowing left and up from the health bar's top right;
  * plate added: acquire, parent, anchor, raise, enable, SetUnit, Show; the same unit again skips
    SetUnit (SetEnabled and Show rescan; an already live container is rescanned by hand);
    plate removed: disable, hide, unparent, back to the pool; two plates get distinct containers;
  * the pool (8) is built out of combat (PLAYER_ENTERING_WORLD, topped up after combat, in small
    batches) and only grown in combat when it is empty, under pcall, logged once on failure;
  * a half-built container is parked, never pooled or used; 3 consecutive failed builds give the
    container path up (fallback row, lazily, UNIT_AURA registered, logged once); a failed attach
    (SetParent or SetUnit throws) clears fsUnit and goes to the back of the pool, parked on its
    second failure; AURA_BUILD_FAIL_LIMIT consecutive attach failures out of combat
    (a real SetParent or SetUnit fault, not a lockdown refusal) give the path up too; an
    in-combat failure neither counts nor resets that count;
  * a plate refused a container in a fight (refused attach, or no build allowed in combat) is
    retried on PLAYER_REGEN_ENABLED (after the pool top-up): it gets a live container, plates that
    already have one are left alone, a failed retry out of combat counts toward the give-up limit,
    and after the give-up the retry builds and attaches nothing;
  * a permanently throwing InCombatLockdown (fail closed) with a healthy attach still gives a
    plate a live container;
  * initializeFrame turns the mouse off before anything else, survives missing or throwing
    methods, and bakes each group's border colour;
  * no aura read API is ever called on the container path (the mocks throw).

The mock is NOT the real client. Theme and FrameHelpers are permissive stubs here, the real
ForeverSynthwave.lua is loaded unchanged.

    python3 tools/nameplate-auras-harness.py

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
SOURCE = HERE.parent / "ForeverSynthwave.lua"

MOCK = r"""
__realType = type
__combat = false
__template = true           -- C_XMLUtil.GetTemplateInfo("CustomAuraContainerTemplate")
__acThrows = false          -- CreateFrame("AuraContainer", ...) raises
__acAttempts = 0            -- CreateFrame("AuraContainer", ...) calls, failed ones included
__acGroupThrows = nil       -- AddAuraGroup(<this name>) raises, after the frame exists
__acSetUnitThrows = false   -- SetUnit raises
__acParentThrows = false    -- SetParent raises (refused in combat)
__acIsEnabledThrows = false -- IsEnabled raises (the release/attach liveness probe)
__combatThrows = false      -- InCombatLockdown raises
__seq = 0
__now = 0
__frames, __acs, __printed, __timers, __degrade, __skins = {}, {}, {}, {}, {}, {}
__auraRead = nil            -- name of the first aura read API that was touched
__slotReads = 0             -- FrameHelpers.ReadAuraSlot calls (the old custom row)
__readableCallbacks = {}    -- FS.OnAurasReadable registrations
__kindMissing, __kindThrows = {}, {}
__skinThrows = false

function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
function hooksecurefunc() end
function InCombatLockdown()
    if __combatThrows then error("boom: InCombatLockdown") end
    return __combat
end
function GetTime() return __now end

-- Frames: capitalised keys are widget methods (recorded, stamped in call order), lowercase
-- keys are plain fields and stay nil. Get* answers a ghost frame, Create* a child.
local FrameM = {}
local FrameMT = {}
local function one() return 1 end
FrameMT.__add, FrameMT.__sub, FrameMT.__mul, FrameMT.__div, FrameMT.__unm = one, one, one, one, one
FrameMT.__lt, FrameMT.__le = function() return false end, function() return false end
FrameMT.__index = function(self, k)
    local m = FrameM[k]
    if m then return m end
    if __realType(k) ~= "string" or not k:match("^%u") then return nil end
    local miss = rawget(self, "_missing")
    if miss and miss[k] then return nil end
    return function(me, ...)
        if me._throws and me._throws[k] then error("boom: " .. k, 2) end
        me._calls[k] = (me._calls[k] or 0) + 1
        me._args[k] = { ... }
        __seq = __seq + 1
        me._at[k] = me._at[k] or __seq
        local what = k:match("^Create(%a+)")
        if what then return __newFrame(what, nil, me) end
        if k:match("^Get") then return __newFrame("Ghost", nil, me) end
    end
end
function __newFrame(kind, name, parent)
    local f = setmetatable({ _kind = kind, _name = name, _parent = parent, _events = {}, _scripts = {},
        _calls = {}, _args = {}, _at = {}, _shown = false, _points = {},
        _missing = __kindMissing[kind], _throws = __kindThrows[kind] }, FrameMT)
    if __realType(name) == "string" then _G[name] = f end
    __frames[#__frames + 1] = f
    return f
end
function FrameM.SetScript(self, k, fn) self._scripts[k] = fn end
function FrameM.RegisterEvent(self, e) self._events[e] = true end
function FrameM.UnregisterEvent(self, e) self._events[e] = nil end
function FrameM.Show(self) self._shown = true end
function FrameM.Hide(self) self._shown = false end
function FrameM.IsShown(self) return self._shown end
function FrameM.SetParent(self, p) self._parent = p end
function FrameM.GetParent(self) return self._parent end
function FrameM.ClearAllPoints(self) self._points = {} end
function FrameM.SetPoint(self, ...) self._points[#self._points + 1] = { ... } end
function FrameM.SetFont(self, ...) self._args.SetFont = { ... }; return true end
function FrameM.SetFrameLevel(self, l) self._level = l end
function FrameM.GetFrameLevel(self) return self._level or 1 end
function FrameM.GetEffectiveScale() return __effScale end
function FrameM.GetWidth() return 10 end
function FrameM.GetHeight() return 10 end
function FrameM.GetStatusBarTexture(self)
    self._fill = self._fill or __newFrame("Texture", nil, self)
    return self._fill
end

-- AuraContainer: strict, only the methods the addon is allowed to call.
local ACM = {}
for _, n in ipairs({ "SetSize", "SetFrameLevel", "SetAuraGroupLayout", "SetFlowLayoutAnchorPoint",
                     "SetFlowLayoutGrowthDirection", "SetFlowLayoutMaximumLineSize", "SetUnit",
                     "SetEnabled", "UpdateAllAuras", "AddAuraGroup" }) do
    ACM[n] = function(self, ...)
        self._calls[n] = (self._calls[n] or 0) + 1
        self._args[n] = { ... }
        __seq = __seq + 1
        self._at[n] = self._at[n] or __seq
        self._order[#self._order + 1] = n
        if n == "SetUnit" and __acSetUnitThrows then error("boom: SetUnit") end
        if n == "SetFrameLevel" then self._level = (...) end
        if n == "SetUnit" then self._unit = (...) end
        if n == "SetEnabled" then self._enabled = (...) end
        if n == "AddAuraGroup" then
            local name, filter, opts = ...
            if name == __acGroupThrows then error("boom: AddAuraGroup " .. name) end
            self._groups[name] = { filter = filter, opts = opts }
            self._groupOrder[#self._groupOrder + 1] = name
        end
    end
end
for k, fn in pairs({ SetParent = FrameM.SetParent, SetPoint = FrameM.SetPoint, ClearAllPoints = FrameM.ClearAllPoints,
                     Show = FrameM.Show, Hide = FrameM.Hide, IsShown = FrameM.IsShown, GetParent = FrameM.GetParent }) do
    ACM[k] = function(self, ...)
        self._calls[k] = (self._calls[k] or 0) + 1
        self._order[#self._order + 1] = k
        if k == "SetParent" and (...) ~= nil then self._parentTries = (self._parentTries or 0) + 1 end
        if k == "SetParent" and __acParentThrows then error("boom: SetParent") end
        return fn(self, ...)
    end
end
ACM.IsEnabled = function(self)
    if __acIsEnabledThrows then error("boom: IsEnabled") end
    return self._enabled == true
end
local ACMT = { __index = ACM }

function CreateFrame(kind, name, parent, tmpl)
    if kind == "AuraContainer" then
        __acAttempts = __acAttempts + 1
        if __acThrows then error("boom: CreateFrame AuraContainer") end
        assert(tmpl == "CustomAuraContainerTemplate", "wrong template: " .. tostring(tmpl))
        local f = setmetatable({ _kind = kind, _calls = {}, _args = {}, _at = {}, _order = {}, _groups = {},
            _groupOrder = {}, _points = {}, _shown = false, _parent = parent, _createdInCombat = __combat }, ACMT)
        __acs[#__acs + 1] = f
        return f
    end
    return __newFrame(kind, name, parent)
end
UIParent = __newFrame("Frame", nil, nil)
GameFontNormal = __newFrame("Font", nil, nil)

SlashCmdList = {}
C_Timer = { After = function(d, fn) __timers[#__timers + 1] = { at = __now + d, fn = fn } end }
C_XMLUtil = { GetTemplateInfo = function(name)
    if __template == "throw" then error("boom: GetTemplateInfo") end
    if __template and name == "CustomAuraContainerTemplate" then return { name = name } end
end }
AnchorUtil = { FlowDirection = { Right = 1, Left = -1, Up = 1, Down = -1 } }
AuraContainerSortMethod = { Default = 0, Expiration = 1 }
AuraContainerSortDirection = { Normal = 0 }

-- Every aura read API is a tripwire.
local function tripwire(path)
    return function() __auraRead = __auraRead or path; error("aura read: " .. path) end
end
C_UnitAuras = {}
for _, n in ipairs({ "GetAuraDataByIndex", "GetUnitAuras", "GetPlayerAuraBySpellID", "GetAuraDataBySpellName",
                     "GetUnitAuraBySpellID", "GetAuraDuration", "GetAuraDataByAuraInstanceID" }) do
    C_UnitAuras[n] = tripwire("C_UnitAuras." .. n)
end
UnitAura, UnitBuff, UnitDebuff = tripwire("UnitAura"), tripwire("UnitBuff"), tripwire("UnitDebuff")
AuraUtil = { ForEachAura = tripwire("AuraUtil.ForEachAura"), FindAuraByName = tripwire("AuraUtil.FindAuraByName") }

-- Plain unit and misc API stubs: unknown Unit*/Get* calls answer nil.
setmetatable(_G, { __index = function(_, k)
    if __realType(k) == "string" and (k:match("^Unit") or k:match("^Get")) then return function() end end
end })
function UnitCanAttack() return true end
function UnitIsFriend() return false end
function UnitIsUnit() return false end
function UnitHealth() return 100 end
function UnitHealthMax() return 100 end
function UnitReaction() return 2 end
function UnitPowerType() return 0 end

-- Permissive Theme/FrameHelpers: ALL_CAPS keys are constants, anything else a ghost-returning function.
local COLOR_HEALTH = { 1, 0.18, 0.59, 1 }
local COLOR_BORDER = { 0.49, 0.23, 0.93, 1 }
local Theme = setmetatable({ COLOR_HEALTH = COLOR_HEALTH, COLOR_BORDER = COLOR_BORDER, FONT_MONO = "MONO" }, {
    __index = function(t, k)
        if k:match("^COLOR_") then return { 1, 1, 1, 1 } end
        if k:match("TEXTURE$") then return "path" end
        if k:match("^[A-Z0-9_]+$") then return 1 end
        return function() return __newFrame("Ghost", nil, nil) end
    end })
function Theme.CutSizeIcon(h) return h >= 36 and 6 or (h >= 24 and 4 or 3) end -- h / 5 rule, 18 -> 3
-- Plate chrome and fill mask (cut-corner migration): recording stubs, real values for the
-- constants the nameplate code reads. AddFillCorners/AddLeadingEdgeCorners hand back the same
-- { quads } shape as Theme.lua, with each quad tagged fsCutCorner the way the real one does.
Theme.CHROME_CORNERS, Theme.SLICE_MARGIN, Theme.BAR_FILL_INSET, Theme.BAR_CORNER_MASK_LEVEL = "cut", 6, 1, 5
function Theme.SnapCut(r) local best = 2 for _, c in ipairs({ 2, 3, 4, 6 }) do if c <= r then best = c end end return best end
__chrome, __fillCorners, __leadCorners = {}, {}, {}
function Theme.AddPanelChrome(frame, opts)
    local fill, glow, border = __newFrame("Texture", nil, frame), __newFrame("Texture", nil, frame), __newFrame("Texture", nil, frame)
    __chrome[#__chrome + 1] = { frame = frame, opts = opts, fill = fill, glow = glow, border = border }
    return fill, glow, border
end
local function cutQuads(host, corners)
    local quads = {}
    for _, corner in ipairs(corners) do
        local q = __newFrame("Texture", nil, host)
        q.fsCutCorner = corner
        q._shown = true
        quads[#quads + 1] = q
    end
    local handle = { quads = quads, setRadiusCalls = 0 }
    -- like Theme.lua's CornerQuadHandle: snap, show again when c > 0
    function handle.SetRadius(r)
        handle.setRadiusCalls = handle.setRadiusCalls + 1
        handle.radius = Theme.SnapCut(r)
        for _, q in ipairs(quads) do q._shown = handle.radius > 0 end
    end
    return handle
end
function Theme.AddFillCorners(host, anchor, color, radius)
    local h = cutQuads(host, { "TOPLEFT", "BOTTOMRIGHT" })
    __fillCorners[#__fillCorners + 1] = { host = host, anchor = anchor, radius = radius, handle = h }
    return h
end
__cutErase, __gates, __eraseRefused, __gateRefused, __gateThrows = {}, {}, false, false, false
function Theme.AddCutFillErase(host, plate, color)
    if Theme.CHROME_CORNERS ~= "cut" or __eraseRefused then return nil end
    local clip = __newFrame("Frame", nil, host)
    clip._shown = true
    local texture = __newFrame("Texture", nil, clip)
    texture._shown = true
    local h = { texture = texture, frame = clip }
    __cutErase[#__cutErase + 1] = { host = host, anchor = plate, color = color, handle = h }
    return h
end
function Theme.AddGatedCutCorner(host, anchor, color, c)
    if __gateThrows then error("boom: AddGatedCutCorner") end
    if Theme.CHROME_CORNERS ~= "cut" or __gateRefused then return nil end
    local bar = __newFrame("StatusBar", nil, host)
    bar._shown = true
    __gates[#__gates + 1] = { host = host, anchor = anchor, color = color, c = c, bar = bar }
    return bar
end
function Theme.AddLeadingEdgeCorners(host, bar, color, radius)
    local h = cutQuads(host, { "BOTTOMRIGHT" })
    __leadCorners[#__leadCorners + 1] = { host = host, bar = bar, radius = radius, handle = h }
    return h
end
function Theme.SkinButton(button, opts)
    if __skinThrows then error("boom: SkinButton") end
    __skins[#__skins + 1] = { button = button, opts = opts }
    button.fsSkin = { border = {} }
    return button.fsSkin
end
FS = {
    IsSecret = function() return false end,
    AurasReadable = function() return not __combat end,
    LogDegradeOnce = function(key, msg) __degrade[#__degrade + 1] = key end,
    Theme = Theme,
    FrameHelpers = setmetatable({
        CreateCaret = function() return { host = __newFrame("Frame", nil, nil) } end,
        NewStepRunner = function() return function() end, function() end end,
        ReadAuraSlot = function() __slotReads = __slotReads + 1 return nil end,
    }, { __index = function() return function() end end }),
}
C_NamePlate = { GetNamePlateForUnit = function(unit)
    __plates = __plates or {}
    if not __plates[unit] then
        local p = __newFrame("Frame", nil, nil)
        p.UnitFrame = __newFrame("Frame", nil, p)
        __plates[unit] = p
    end
    return __plates[unit]
end }

-- .toc order: ForeverSynthwave.lua loads BEFORE Theme.lua, FrameHelpers.lua and the rest, so
-- none of what they put on FS exists while this file's top level runs. The file is loaded with
-- those fields absent and they are installed after it, as the later files would.
local LOADED_LATER = { "Theme", "FrameHelpers", "AurasReadable", "OnAurasReadable", "IsSecret", "LogDegradeOnce" }
function boot()
    local fn = assert(loadstring(__SRC, "@ForeverSynthwave.lua"))
    local later = {}
    for _, k in ipairs(LOADED_LATER) do later[k] = FS[k]; FS[k] = nil end
    local ok, err = pcall(fn, "ForeverSynthwave", FS)
    FS.Theme = later.Theme
    FS.FrameHelpers = later.FrameHelpers
    FS.AurasReadable = later.AurasReadable
    FS.IsSecret = later.IsSecret
    FS.LogDegradeOnce = later.LogDegradeOnce
    FS.OnAurasReadable = function(f) __readableCallbacks[#__readableCallbacks + 1] = f end
    if not ok then error("loading ForeverSynthwave.lua before Theme.lua threw: " .. tostring(err), 0) end
end

-- Test helpers ------------------------------------------------------------------------
function check(c, msg) if not c then error("CHECK FAILED: " .. msg, 2) end end
function evframe()
    for _, f in ipairs(__frames) do if f._scripts.OnEvent then return f end end
end
function fire(event, ...)
    local f = evframe()
    check(f, "no event frame")
    local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
    check(ok, "event handler threw on " .. event .. ": " .. tostring(err))
end
function drain()
    local n = 0
    while true do
        local t
        for _, x in ipairs(__timers) do if not x.fired then t = x break end end
        if not t then return n end
        t.fired = true
        n = n + 1
        local ok, err = pcall(t.fn)
        check(ok, "timer threw: " .. tostring(err))
        check(n < 200, "timers never settle")
    end
end
function pendingTimers()
    local n = 0
    for _, t in ipairs(__timers) do if not t.fired then n = n + 1 end end
    return n
end
function addPlate(unit) fire("NAME_PLATE_UNIT_ADDED", unit) end
function removePlate(unit) fire("NAME_PLATE_UNIT_REMOVED", unit) end
function degraded(key)
    local n = 0
    for _, k in ipairs(__degrade) do if k == key then n = n + 1 end end
    return n
end
function colorEq(a, b) return a and b and a[1] == b[1] and a[2] == b[2] and a[3] == b[3] end
function children(parent, kind)
    local out = {}
    for _, f in ipairs(__frames) do
        if f._parent == parent and (kind == nil or f._kind == kind) then out[#out + 1] = f end
    end
    return out
end
"""

# Each case: (name, template state, body). The body runs after the mock; boot() loads the file.
CASES: list[tuple[str, str, str]] = [
    ("container used when the template exists", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD")
drain()
check(#__acs > 0, "no AuraContainer was built")
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
check(root.auraIcons == nil, "the old custom row was built next to the container")
check(root.auraContainer and root.auraContainer._unit == "nameplate1", "plate has no live container")
local ec = evframe()
check(ec._events.UNIT_AURA == nil, "UNIT_AURA registered although the engine updates the container")
-- group setup: once, at creation, never again across add/remove cycles
for _ = 1, 3 do removePlate("nameplate1"); addPlate("nameplate1") end
local c = root.auraContainer
check(c._calls.AddAuraGroup == 2, "AddAuraGroup calls: " .. tostring(c._calls.AddAuraGroup))
local own, other = c._groups.own, c._groups.other
check(own and own.filter == "HARMFUL|PLAYER" and own.opts.maxFrameCount == 5, "own group wrong")
check(other and other.filter == "HARMFUL|!PLAYER" and other.opts.maxFrameCount == 3, "other group wrong")
check(c._groupOrder[1] == "own" and c._groupOrder[2] == "other", "own must come first")
for _, g in ipairs({ own, other }) do
    local l = g.opts.layout
    check(l.elementWidth == 18 and l.elementHeight == 18 and l.elementSpacing == 2, "layout not 18/18/2")
    check(l.maximumLineSize == nil, "maximumLineSize in the group layout (the engine ignores it there)")
    check(type(g.opts.initializeFrame) == "function", "no initializeFrame")
end
check(c._args.SetFlowLayoutAnchorPoint[1] == "BOTTOMRIGHT", "flow anchor not BOTTOMRIGHT")
check(c._args.SetFlowLayoutGrowthDirection[1] == -1 and c._args.SetFlowLayoutGrowthDirection[2] == 1, "growth not Left, Up")
check(c._args.SetSize[1] == 1 and c._args.SetSize[2] == 1, "container not 1x1")
check(c._calls.SetAuraGroupLayout == nil, "SetAuraGroupLayout called although AddAuraGroup already took the layout")
check(c._args.SetFlowLayoutMaximumLineSize[1] == 6 * 20 + 1, "flow line size not 6 icons wide")
"""),

    ("fallback row when the template is absent", "false", r"""
boot()
fire("PLAYER_ENTERING_WORLD")
drain()
check(#__acs == 0, "a container was built without the template")
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
check(root.auraContainer == nil, "plate has a container without the template")
check(root.auraIcons and #root.auraIcons == 5, "the custom row is missing")
check(evframe()._events.UNIT_AURA, "UNIT_AURA not registered for the custom row")
check(__slotReads > 0, "the custom row never scanned out of combat")
__slotReads = 0
__combat = true
fire("UNIT_AURA", "nameplate1")
check(__slotReads == 0, "the custom row scanned in combat")
"""),

    ("the fallback row is rescanned through FS.OnAurasReadable when a regen read was refused", "false", r"""
boot()
fire("PLAYER_ENTERING_WORLD")
drain()
addPlate("nameplate1")
check(#__readableCallbacks == 1, "nothing registered with FS.OnAurasReadable: " .. #__readableCallbacks)
__slotReads = 0
__readableCallbacks[1]()
check(__slotReads > 0, "the readable callback did not rescan the fallback row")
"""),

    ("loads with Theme.lua still unloaded; the readable callback is registered once, by login, not per plate", "true", r"""
boot()
check(#__readableCallbacks == 0, "FS.OnAurasReadable was called while the file loaded")
addPlate("nameplate1"); addPlate("nameplate2")
check(#__readableCallbacks == 0, "registered per plate")
fire("PLAYER_ENTERING_WORLD"); drain()
fire("PLAYER_ENTERING_WORLD"); drain()
check(#__readableCallbacks == 1, "expected one registration, got " .. #__readableCallbacks)
"""),

    ("the container path has nothing to rescan when reads become possible", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD")
drain()
addPlate("nameplate1")
__slotReads = 0
__readableCallbacks[1]()
check(__slotReads == 0, "the container path read auras from the readable callback")
"""),

    ("a throwing template check also falls back", '"throw"', r"""
boot()
addPlate("nameplate1")
check(#__acs == 0 and FS.framesByUnit.nameplate1.auraIcons, "did not fall back when the template check threw")
"""),

    ("plate added acquires, parents, anchors, enables and sets the unit", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local built = #__acs
addPlate("nameplate1")
check(#__acs == built, "a container was built although the pool had one")
local root = FS.framesByUnit.nameplate1
local c = root.auraContainer
check(c._parent == root, "not parented to the plate root")
local p = c._points[1]
check(p[1] == "BOTTOMRIGHT" and p[2] == root.healthBar and p[3] == "TOPRIGHT" and p[4] == 0 and p[5] == 2, "bad anchor")
check(c._enabled == true and c._unit == "nameplate1" and c._shown == true, "not enabled, unit set and shown")
check(c._at.SetEnabled < c._at.SetUnit, "SetUnit before SetEnabled(true)")
check(c._calls.UpdateAllAuras == nil, "UpdateAllAuras on a fresh unit")
"""),

    ("same unit again skips SetUnit and leaves the rescan to SetEnabled and Show", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
addPlate("nameplate1")   -- no REMOVED in between: released, then taken again
check(FS.framesByUnit.nameplate1.auraContainer == c, "container not reused")
check(c._calls.SetUnit == 1, "SetUnit again for an unchanged token: " .. tostring(c._calls.SetUnit))
check(c._calls.UpdateAllAuras == nil, "explicit UpdateAllAuras although SetEnabled(true) and Show rebuild: "
    .. tostring(c._calls.UpdateAllAuras))
removePlate("nameplate1"); addPlate("nameplate1")
check(c._calls.SetUnit == 1 and c._calls.UpdateAllAuras == nil, "remove and re-add rescanned by hand")
check(c._enabled == true and c._shown == true, "not live after the re-add")
removePlate("nameplate1"); addPlate("nameplate2")
check(c._calls.SetUnit == 2 and c._unit == "nameplate2", "a different unit did not SetUnit")
"""),

    ("a container already enabled and shown (release half-failed) is rescanned by hand", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
removePlate("nameplate1")
c._enabled, c._shown = true, true     -- the release steps did not take
addPlate("nameplate1")
check(FS.framesByUnit.nameplate1.auraContainer == c, "container not reused")
check(c._calls.SetUnit == 1 and c._calls.UpdateAllAuras == 1, "live container with the same token: SetUnit "
    .. tostring(c._calls.SetUnit) .. " UpdateAllAuras " .. tostring(c._calls.UpdateAllAuras))
"""),

    ("two plates at once get distinct, live containers", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1"); addPlate("nameplate2")
local r1, r2 = FS.framesByUnit.nameplate1, FS.framesByUnit.nameplate2
local c1, c2 = r1.auraContainer, r2.auraContainer
check(c1 and c2 and c1 ~= c2, "two live plates share (or lack) a container")
check(c1._unit == "nameplate1" and c2._unit == "nameplate2", "containers watch the wrong units")
check(c1._parent == r1 and c2._parent == r2, "containers parented to the wrong plates")
check(c1._enabled and c2._enabled and c1._shown and c2._shown, "a container is not live")
removePlate("nameplate1")
check(c2._enabled == true and c2._shown == true and c2._parent == r2, "releasing plate 1 disturbed plate 2")
"""),

    ("the container is raised above the plate root", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local plate = C_NamePlate.GetNamePlateForUnit("nameplate1")
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
root:SetFrameLevel(10)
removePlate("nameplate1"); addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
check(c._args.SetFrameLevel and c._args.SetFrameLevel[1] == root:GetFrameLevel() + 5,
    "container level " .. tostring(c._args.SetFrameLevel and c._args.SetFrameLevel[1]) .. " not root + 5")
check(c._args.SetFrameLevel[1] > root:GetFrameLevel(), "container not above the root")
"""),

    ("plate removed disables, hides, unparents and pools the container", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
local c = root.auraContainer
local total = #__acs
removePlate("nameplate1")
check(c._enabled == false and c._shown == false, "not disabled and hidden")
check(c._parent == nil and #c._points == 0, "not unparented and unanchored")
check(root.auraContainer == nil, "root still holds the container")
addPlate("nameplate2")
check(#__acs == total and FS.framesByUnit.nameplate2.auraContainer == c, "released container not back in the pool")
"""),

    ("pool prefills out of combat, in batches", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD")
check(#__acs > 0 and #__acs < 8 and pendingTimers() > 0, "prefill is not batched: " .. #__acs)
drain()
check(#__acs == 8, "pool prefilled to " .. #__acs)
for _, c in ipairs(__acs) do check(not c._createdInCombat, "a container was built in combat") end
-- fight with a stocked pool: nothing is built
__combat = true
fire("PLAYER_ENTERING_WORLD"); drain()
for i = 1, 4 do addPlate("nameplate" .. i) end
check(#__acs == 8, "containers built in combat although the pool had some: " .. #__acs)
-- combat over: the pool is topped up
__combat = false
fire("PLAYER_REGEN_ENABLED"); drain()
check(#__acs == 12, "pool not topped up after combat: " .. #__acs)
"""),

    ("combat with an empty pool builds one under pcall, a failure leaves the plate bare and logs once", "true", r"""
boot()
__combat = true
fire("PLAYER_ENTERING_WORLD"); drain()
check(#__acs == 0, "prefilled in combat")
addPlate("nameplate1")
check(#__acs == 1 and __acs[1]._createdInCombat and FS.framesByUnit.nameplate1.auraContainer == __acs[1],
    "empty pool in combat did not build one")
__acThrows = true
addPlate("nameplate2"); addPlate("nameplate3")
check(FS.framesByUnit.nameplate2.auraContainer == nil and FS.framesByUnit.nameplate3.auraContainer == nil,
    "failed plates got a container")
check(FS.framesByUnit.nameplate2._shown == true, "the plate itself broke with its row")
check(degraded("plate_aura_container") == 1, "degrade logged " .. degraded("plate_aura_container") .. " times")
"""),

    ("initializeFrame turns the mouse off first and bakes the group colour", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local c = __acs[1]
local function newButton() return __newFrame("Button", nil, UIParent) end
local b = newButton()
c._groups.own.opts.initializeFrame(b)
check(b._args.SetMouseMotionEnabled[1] == false and b._args.SetMouseClickEnabled[1] == false, "mouse left on")
check(b._args.SetHideTooltipInCombat[1] == true, "tooltip not hidden in combat")
check(b._at.SetMouseMotionEnabled < b._at.SetIcon and b._at.SetMouseClickEnabled < b._at.SetIcon, "mouse disabled after SetIcon")
check(b._calls.SetIcon == 1 and b._calls.SetDurationCooldown == 1 and b._calls.SetDurationText == 1
    and b._calls.SetApplicationCount == 1, "a binder is missing")
check(b._args.SetSize[1] == 18 and b._args.SetSize[2] == 18, "not 18x18")
local cd = children(b, "Cooldown")[1]
check(cd and cd._args.SetHideCountdownNumbers[1] == true and cd._args.SetDrawEdge[1] == false
    and cd._args.SetReverse[1] == true and cd._args.EnableMouse[1] == false, "cooldown not set up")
local fs = children(cd, "FontString")[1]
check(fs and fs._args.SetFont[1] == "MONO" and fs._args.SetFont[2] == 8, "duration text is not 8pt mono")
check(type(b._args.SetDurationText[2]) == "table", "SetDurationText needs an options table")
-- the border colour is baked per group, and nothing retints afterwards
local b2 = newButton()
c._groups.other.opts.initializeFrame(b2)
check(colorEq(__skins[1].opts.borderColor, FS.Theme.COLOR_HEALTH), "own group border is not pink")
check(colorEq(__skins[2].opts.borderColor, FS.Theme.COLOR_BORDER), "other group border is not violet")
-- the engine builds the button unsized, so SkinButton cannot read a height: the 18px icon
-- chamfer has to come in through opts, not fall back to c = 6
check(__skins[1].opts.chamfer == 3 and __skins[2].opts.chamfer == 3,
    "aura SkinButton chamfer is " .. tostring(__skins[1].opts.chamfer) .. ", want CutSizeIcon(18) = 3")
check(b._calls.SetVertexColor == nil and b._calls.SetColorTexture == nil, "the button was retinted")
"""),

    ("initializeFrame survives missing and throwing methods", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local c = __acs[1]
local b = __newFrame("Button", nil, UIParent)
b._missing = { SetHideTooltipInCombat = true, SetSize = true }
b._throws = { SetMouseClickEnabled = true, SetIcon = true }
__kindMissing.Cooldown = { SetDrawEdge = true }
__kindThrows.Cooldown = { EnableMouse = true, SetReverse = true }
__skinThrows = true
local ok, err = pcall(c._groups.own.opts.initializeFrame, b)
check(ok, "initializeFrame threw: " .. tostring(err))
check(b._calls.SetMouseMotionEnabled == 1, "a throwing SetMouseClickEnabled stopped the next call")
check(b._calls.SetDurationCooldown == 1 and b._calls.SetDurationText == 1 and b._calls.SetApplicationCount == 1,
    "a throwing SetIcon stopped the rest of the setup")
local cd = children(b, "Cooldown")[1]
check(cd._args.SetHideCountdownNumbers[1] == true, "cooldown setup stopped at a throwing call")
check(#children(b, "Texture") == 5, "icon plus four border edges expected when SkinButton threw")
"""),

    ("no aura read API on the container path", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
for _, combat in ipairs({ false, true }) do
    __combat = combat
    addPlate("nameplate1")
    fire("UNIT_AURA", "nameplate1")
    fire("UNIT_FACTION", "nameplate1")
    fire("UNIT_FLAGS", "player")
    fire("PLAYER_REGEN_ENABLED")
    fire("PLAYER_TARGET_CHANGED")
    removePlate("nameplate1")
end
check(__auraRead == nil, "aura read API touched: " .. tostring(__auraRead))
check(__slotReads == 0, "the old custom row scanned auras")
"""),

    ("a half-built container (AddAuraGroup throws) is parked, never used, and the build stops after 3 tries", "true", r"""
boot()
__acGroupThrows = "other"
fire("PLAYER_ENTERING_WORLD"); drain()
for i = 1, 20 do addPlate("nameplate" .. i) end
check(#__acs <= 3 and __acAttempts <= 3, "build attempts: " .. __acAttempts .. ", frames " .. #__acs)
for _, c in ipairs(__acs) do
    check(c._shown == false and c._enabled ~= true and c._unit == nil, "a half-built container was brought to life")
    check(c._parent == UIParent, "a half-built container was handed to a plate")
end
for i = 1, 20 do
    local root = FS.framesByUnit["nameplate" .. i]
    check(root.auraContainer == nil, "plate " .. i .. " holds a container")
    check(root.auraIcons and #root.auraIcons == 5, "plate " .. i .. " has no fallback row")
end
check(evframe()._events.UNIT_AURA, "UNIT_AURA not registered once the fallback row took over")
check(degraded("plate_aura_container_giveup") == 1, "give-up logged " .. degraded("plate_aura_container_giveup") .. " times")
__slotReads = 0
fire("UNIT_AURA", "nameplate7")
check(__slotReads > 0, "the fallback row never scanned out of combat")
-- a plate that arrives afterwards builds its row lazily and does not retry the build
addPlate("nameplate21")
check(FS.framesByUnit.nameplate21.auraIcons and #FS.framesByUnit.nameplate21.auraIcons == 5, "later plate has no fallback row")
check(__acAttempts <= 3, "builds retried after giving up: " .. __acAttempts)
"""),

    ("CreateFrame itself keeps throwing: 3 tries, then the fallback row, one log", "true", r"""
boot()
__acThrows = true
for i = 1, 10 do addPlate("nameplate" .. i) end
check(__acAttempts == 3, "build attempts: " .. __acAttempts)
for i = 1, 10 do
    check(FS.framesByUnit["nameplate" .. i].auraIcons, "plate " .. i .. " has no fallback row")
end
check(degraded("plate_aura_container") == 1, "first failure logged " .. degraded("plate_aura_container") .. " times")
check(degraded("plate_aura_container_giveup") == 1, "give-up logged " .. degraded("plate_aura_container_giveup") .. " times")
"""),

    ("a successful build resets the failure count", "true", r"""
boot()
__acThrows = true
addPlate("nameplate1"); addPlate("nameplate2")        -- two failures
__acThrows = false
addPlate("nameplate3")                                -- success: count back to zero
check(FS.framesByUnit.nameplate3.auraContainer, "build after two failures did not work")
__acThrows = true
removePlate("nameplate3")                             -- container returns to the pool
for i = 4, 6 do addPlate("nameplate" .. i) end        -- the pooled one, then two more failures
check(FS.framesByUnit.nameplate6.auraIcons == nil, "gave up on only two consecutive failures")
"""),

    ("an attach that fails goes to the back of the pool, twice means parked for good", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local pooled = #__acs
__acParentThrows = true
addPlate("nameplate1"); addPlate("nameplate2")
check(FS.framesByUnit.nameplate1.auraContainer == nil and FS.framesByUnit.nameplate2.auraContainer == nil,
    "a failed attach left a container on the plate")
local tried = {}
for _, c in ipairs(__acs) do if (c._parentTries or 0) > 0 then tried[#tried + 1] = c end end
check(#tried == 2, "the failed container was handed out again at once: " .. #tried .. " distinct tried")
__acParentThrows = false
addPlate("nameplate3")
local c3 = FS.framesByUnit.nameplate3.auraContainer
check(c3 and c3 ~= tried[1] and c3 ~= tried[2], "a container that just failed was at the front of the pool")
check(#__acs == pooled, "a container was built although the pool had healthy ones")
"""),

    ("a container whose attach fails twice is parked and never handed out again", "true", r"""
boot()
__combat = true
__acParentThrows = true
addPlate("nameplate1")                      -- builds c1, attach fails (1)
addPlate("nameplate2")                      -- takes c1 again, attach fails (2): parked
local c1 = __acs[1]
check(c1._parentTries == 2, "c1 attach tries: " .. tostring(c1._parentTries))
addPlate("nameplate3")                      -- pool empty and an attach already failed this fight: no new build
check(#__acs == 1, "built another container in a fight where attaching is refused: " .. #__acs)
check(FS.framesByUnit.nameplate3.auraContainer == nil, "plate 3 got a container")
__combat = false
__acParentThrows = false
fire("PLAYER_REGEN_ENABLED"); drain()
addPlate("nameplate4")
check(FS.framesByUnit.nameplate4.auraContainer and FS.framesByUnit.nameplate4.auraContainer ~= c1, "the parked container came back")
check(c1._parentTries == 2, "the parked container was used again")
"""),

    ("fsUnit is cleared when the attach fails", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
check(c.fsUnit == "nameplate1", "fsUnit not recorded on success")
removePlate("nameplate1")
check(c.fsUnit == "nameplate1", "fsUnit lost on release (the token is kept for the next attach)")
__acSetUnitThrows = true
addPlate("nameplate2")
check(FS.framesByUnit.nameplate2.auraContainer == nil, "plate holds a container whose SetUnit threw")
check(c.fsUnit == nil, "fsUnit still " .. tostring(c.fsUnit) .. " after a failed attach")
check(c._enabled == false and c._shown == false, "the failed container was left live")
"""),

    ("a persistent attach failure out of combat gives the container path up, with bounded containers", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local pooled = #__acs
__acParentThrows = true
for i = 1, 20 do addPlate("nameplate" .. i) end
check(#__acs == pooled, "containers built while every attach fails: " .. #__acs .. " vs " .. pooled)
check(evframe()._events.UNIT_AURA, "the container path was never given up")
check(degraded("plate_aura_container_giveup") == 1, "give-up logged " .. degraded("plate_aura_container_giveup") .. " times")
for i = 1, 20 do
    local root = FS.framesByUnit["nameplate" .. i]
    check(root.auraContainer == nil, "plate " .. i .. " holds a container")
    check(root.auraIcons and #root.auraIcons == 5, "plate " .. i .. " has no fallback row")
end
local tries = 0
for _, c in ipairs(__acs) do tries = tries + (c._parentTries or 0) end
check(tries <= 3, "attaches kept going after giving up: " .. tries)
"""),

    ("a successful attach resets the attach failure count", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__acParentThrows = true
addPlate("nameplate1"); addPlate("nameplate2")        -- two failures
__acParentThrows = false
addPlate("nameplate3")                                -- success: count back to zero
check(FS.framesByUnit.nameplate3.auraContainer, "attach after two failures did not work")
__acParentThrows = true
addPlate("nameplate4"); addPlate("nameplate5")        -- two more failures
check(evframe()._events.UNIT_AURA == nil and FS.framesByUnit.nameplate5.auraIcons == nil,
    "gave up on only two consecutive failures")
addPlate("nameplate6")                                -- the third in a row
check(evframe()._events.UNIT_AURA, "three consecutive failures did not give up")
"""),

    ("attach failures in combat, or with InCombatLockdown throwing, never give the path up", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__combat = true
__acParentThrows = true
for i = 1, 10 do addPlate("nameplate" .. i) end
check(evframe()._events.UNIT_AURA == nil and FS.framesByUnit.nameplate10.auraIcons == nil,
    "gave up on lockdown refusals")
__combat = false
__combatThrows = true
for i = 11, 20 do addPlate("nameplate" .. i) end
check(evframe()._events.UNIT_AURA == nil and FS.framesByUnit.nameplate20.auraIcons == nil,
    "gave up although the combat check threw (fail closed)")
__combatThrows = false
"""),

    ("giving up leaves a plate that holds a live container alone, later plates get the row", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local r1 = FS.framesByUnit.nameplate1
local c1 = r1.auraContainer
check(c1 and c1._enabled, "no live container")
__combat = true                                       -- drain the pool, then break the builds
for i = 2, 9 do addPlate("nameplate" .. i) end
__acThrows = true
for i = 10, 14 do addPlate("nameplate" .. i) end
check(evframe()._events.UNIT_AURA, "the container path was never given up")
check(r1.auraContainer == c1 and c1._enabled and c1._shown, "the live container was disturbed")
check(r1.auraIcons == nil, "a plate with a live container also got a fallback row")
check(FS.framesByUnit.nameplate14.auraIcons, "a bare plate got no fallback row")
__slotReads = 0
fire("UNIT_AURA", "nameplate1"); fire("UNIT_AURA", "nameplate14")
check(__slotReads == 0, "the fallback row scanned in combat")
-- a frame built before the give-up, released and acquired again after it, gets its row
removePlate("nameplate1"); addPlate("nameplate1")
local again = FS.framesByUnit.nameplate1
check(again.auraContainer == nil and again.auraIcons and #again.auraIcons == 5,
    "a pre-give-up frame reused after the give-up got no row")
-- lockdown lifts: the fallback row is refreshed at once
__combat = false
__slotReads = 0
fire("PLAYER_REGEN_ENABLED")
check(__slotReads > 0, "the fallback row was not refreshed when combat ended")
"""),

    ("fsAttachFails is cleared by a successful attach", "true", r"""
boot()
__acParentThrows = true
addPlate("nameplate1")                                -- builds c1 (no prefill); attach fails (1)
local c1 = __acs[1]
check(c1._parentTries == 1 and FS.framesByUnit.nameplate1.auraContainer == nil, "setup: first attach did not fail")
__acParentThrows = false
addPlate("nameplate2")
check(FS.framesByUnit.nameplate2.auraContainer == c1, "setup: c1 not reused")
removePlate("nameplate2")
__acParentThrows = true
addPlate("nameplate3")                                -- fails again: the first since the success
__acParentThrows = false
addPlate("nameplate4")
check(FS.framesByUnit.nameplate4.auraContainer == c1 and #__acs == 1,
    "c1 was parked: the failure count survived a success (frames " .. #__acs .. ")")
"""),

    ("the attach refusal flag ends with the fight, and only blocks builds during combat", "true", r"""
boot()
__combat = true
__acParentThrows = true
addPlate("nameplate1"); addPlate("nameplate2")        -- c1 fails twice: parked, flag set
addPlate("nameplate3")
check(#__acs == 1, "built another container after a refused attach in the fight: " .. #__acs)
__acParentThrows = false
__combat = false                                      -- lockdown lifted, REGEN not handled yet
addPlate("nameplate4")
check(FS.framesByUnit.nameplate4.auraContainer and #__acs == 2, "the flag blocked a build out of combat")
fire("PLAYER_REGEN_ENABLED"); drain()
__combat = true                                       -- second fight: use the whole pool up
local pool = #__acs
for i = 5, 12 do addPlate("nameplate" .. i) end
addPlate("nameplate13")
check(#__acs == pool + 1 and FS.framesByUnit.nameplate13.auraContainer,
    "the flag was not reset: no build in the second fight (" .. #__acs .. " vs " .. pool .. ")")
"""),

    ("a container that is enabled or shown, but not both, is not rescanned by hand", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
for _, state in ipairs({ { true, false }, { false, true } }) do
    removePlate("nameplate1")
    c._enabled, c._shown = state[1], state[2]
    addPlate("nameplate1")
    check(FS.framesByUnit.nameplate1.auraContainer == c, "container not reused")
    check(c._calls.UpdateAllAuras == nil, "rescanned by hand with enabled=" .. tostring(state[1])
        .. " shown=" .. tostring(state[2]))
end
"""),

    ("a throwing IsEnabled does not stop the attach", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__acIsEnabledThrows = true
addPlate("nameplate1")
local c = FS.framesByUnit.nameplate1.auraContainer
check(c and c._enabled == true and c._shown == true and c._unit == "nameplate1", "attach failed with IsEnabled throwing")
removePlate("nameplate1"); addPlate("nameplate1")
check(FS.framesByUnit.nameplate1.auraContainer == c and c._calls.UpdateAllAuras == nil,
    "an unreadable container state was treated as live")
"""),

    ("a permanently throwing InCombatLockdown, with a healthy attach, still gives every plate a live container", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
local pooled = #__acs
__combatThrows = true                                 -- fail closed: every check reads "in combat"
for i = 1, pooled + 1 do addPlate("nameplate" .. i) end   -- the pool, then one build under pcall
check(#__acs == pooled + 1, "the empty pool did not build one container: " .. #__acs)
for i = 1, pooled + 1 do
    local c = FS.framesByUnit["nameplate" .. i].auraContainer
    check(c and c._enabled == true and c._shown == true and c._unit == "nameplate" .. i,
        "plate " .. i .. " has no live container")
end
check(evframe()._events.UNIT_AURA == nil, "gave up although every attach worked")
"""),

    ("a plate refused a container in combat gets one when combat ends", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
addPlate("nameplate1")                                -- live before the fight
local live = FS.framesByUnit.nameplate1.auraContainer
check(live and live._enabled, "setup: no live container")
local liveTries = live._parentTries
__combat = true
__acParentThrows = true
addPlate("nameplate2"); addPlate("nameplate3")        -- refused in the fight: bare
check(FS.framesByUnit.nameplate2.auraContainer == nil and FS.framesByUnit.nameplate3.auraContainer == nil,
    "setup: a refused attach left a container on the plate")
__acParentThrows = false
__combat = false
fire("PLAYER_REGEN_ENABLED"); drain()
local c2, c3 = FS.framesByUnit.nameplate2.auraContainer, FS.framesByUnit.nameplate3.auraContainer
check(c2 and c2._unit == "nameplate2" and c2._enabled and c2._shown, "plate 2 stayed bare after combat")
check(c3 and c3._unit == "nameplate3" and c3._enabled and c3._shown, "plate 3 stayed bare after combat")
check(c2 ~= c3 and c2 ~= live and c3 ~= live, "two plates share a container")
check(FS.framesByUnit.nameplate1.auraContainer == live and live._parentTries == liveTries,
    "the retry re-attached a plate that already had its container")
check(FS.framesByUnit.nameplate2.auraIcons == nil, "a retried plate also got a fallback row")
-- a second REGEN does not touch plates that are all served
fire("PLAYER_REGEN_ENABLED"); drain()
check(c2._calls.SetUnit == 1 and FS.framesByUnit.nameplate2.auraContainer == c2,
    "a plate that already has a container was retried: SetUnit " .. tostring(c2._calls.SetUnit))
"""),

    ("a plate refused because no container could be built in combat is retried with a built one", "true", r"""
boot()
__combat = true
__acParentThrows = true
addPlate("nameplate1")                                -- builds c1, attach fails (1)
addPlate("nameplate2")                                -- c1 again, fails (2): parked, flag set
addPlate("nameplate3")                                -- pool empty, flag set: no build, bare
check(#__acs == 1, "setup: built another container in a refused fight: " .. #__acs)
__acParentThrows = false
__combat = false
fire("PLAYER_REGEN_ENABLED"); drain()
local c1 = __acs[1]
for i = 1, 3 do
    local c = FS.framesByUnit["nameplate" .. i].auraContainer
    check(c and c ~= c1 and c._unit == "nameplate" .. i and c._enabled and c._shown,
        "plate " .. i .. " did not get a healthy container after combat")
end
check(c1._parentTries == 2, "the parked container was used again")
"""),

    ("the regen retry counts toward the give-up limit and stops once it is reached", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__combat = true
__acParentThrows = true
for i = 1, 5 do addPlate("nameplate" .. i) end        -- refused in the fight: bare, nothing counted
check(evframe()._events.UNIT_AURA == nil, "setup: gave up on lockdown refusals")
local function tries()
    local n = 0
    for _, c in ipairs(__acs) do n = n + (c._parentTries or 0) end
    return n
end
local before = tries()
__combat = false                                      -- the fault persists out of combat
fire("PLAYER_REGEN_ENABLED"); drain()
check(tries() - before == 3, "retry attaches: " .. (tries() - before) .. ", want exactly the give-up limit (3)")
check(evframe()._events.UNIT_AURA, "failed retries did not give the container path up")
check(degraded("plate_aura_container_giveup") == 1, "give-up logged " .. degraded("plate_aura_container_giveup") .. " times")
for i = 1, 5 do
    local root = FS.framesByUnit["nameplate" .. i]
    check(root.auraContainer == nil and root.auraIcons and #root.auraIcons == 5, "plate " .. i .. " has no fallback row")
end
"""),

    ("after the give-up the regen retry builds and attaches nothing", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__acParentThrows = true
for i = 1, 20 do addPlate("nameplate" .. i) end       -- out of combat: gives up
check(evframe()._events.UNIT_AURA, "setup: the container path was never given up")
local frames = #__acs
local tries = 0
for _, c in ipairs(__acs) do tries = tries + (c._parentTries or 0) end
__acParentThrows = false
fire("PLAYER_REGEN_ENABLED"); drain()
local after = 0
for _, c in ipairs(__acs) do after = after + (c._parentTries or 0) end
check(#__acs == frames, "built containers after giving up: " .. #__acs .. " vs " .. frames)
check(after == tries, "attached after giving up: " .. (after - tries))
for i = 1, 20 do
    local root = FS.framesByUnit["nameplate" .. i]
    check(root.auraContainer == nil and root.auraIcons and #root.auraIcons == 5, "plate " .. i .. " lost its fallback row")
end
"""),

    ("an attach failure in combat neither counts toward the give-up limit nor resets it", "true", r"""
boot()
fire("PLAYER_ENTERING_WORLD"); drain()
__acParentThrows = true
addPlate("nameplate1"); addPlate("nameplate2")        -- two out-of-combat failures
__combat = true
addPlate("nameplate3")                                -- refused in combat: not counted, not a reset
check(evframe()._events.UNIT_AURA == nil, "a lockdown refusal counted toward the limit")
__combat = false
addPlate("nameplate4")                                -- the third out-of-combat failure
check(evframe()._events.UNIT_AURA, "an in-combat failure reset the out-of-combat failure count")
"""),
    ("plate chrome goes through AddPanelChrome and the fills cut TOP-LEFT and BOTTOM-RIGHT only", "true", r"""
boot()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
check(#__chrome >= 1, "the plate chrome did not go through Theme.AddPanelChrome")
local ch
for _, c in ipairs(__chrome) do if c.frame == root then ch = c end end
check(ch, "AddPanelChrome was not given the plate root")
check(colorEq(ch.opts.accent, FS.Theme.COLOR_BORDER) and ch.opts.glowAlpha == 0.30, "accent/glowAlpha not the old plate values")
check(root.fsGlow == ch.glow and root.fsBorder == ch.border, "fsGlow/fsBorder are not the AddPanelChrome handles")

-- Parker 2026-10-04 (playtest): a quad riding the fill's right edge cut a travelling BOTTOM-RIGHT
-- notch into the fill (and into the caret line) at every mid-bar level. The cut shape is FIXED:
-- the static erase at the bar's own corners is the whole mask, so the fill's right end is
-- square mid-bar and takes the chamfer only when it reaches the end.
check(#__leadCorners == 0, "a leading-edge corner quad was built under cut: " .. #__leadCorners)
-- Parker 2026-10-04 (second playtest): "slight black in the corners". The unit-sized anti_cut
-- quads overshot the nine-sliced stroke's diagonal at the engine's own texel ratio. Under cut each
-- bar gets a NINE-SLICE erase laid over the plate ROOT rect (the stroke's own rect, so the engine
-- scales wedge and stroke together at any plate scale), hosted on the bar's clipping mask so the
-- bar rect trims it. No unit-sized quad is built for the plate at all.
check(#__fillCorners == 0, "a unit-sized fill-corner quad was built for the plate: " .. #__fillCorners)
local he, pe
for _, e in ipairs(__cutErase) do
    if e.host._parent == root.healthBar then he = e end
    if e.host._parent == root.powerBar then pe = e end
end
check(he and pe, "a bar has no nine-slice erase")
check(he.anchor == root and pe.anchor == root, "the erase is not laid over the plate root")
check(colorEq(he.color, FS.Theme.COLOR_BAR_TRACK) and colorEq(pe.color, FS.Theme.COLOR_BAR_TRACK), "erase not the track colour")
-- the erase clears the caret host (bar + 2) and its mask clips it at the bar rect
check(he.host:GetFrameLevel() == root.healthBar:GetFrameLevel() + FS.Theme.BAR_CORNER_MASK_LEVEL,
    "health mask host not at bar + BAR_CORNER_MASK_LEVEL")
check(pe.host:GetFrameLevel() == root.powerBar:GetFrameLevel() + FS.Theme.BAR_CORNER_MASK_LEVEL,
    "power mask host not at bar + BAR_CORNER_MASK_LEVEL")
check(he.host._calls.SetClipsChildren and pe.host._calls.SetClipsChildren, "a mask host does not clip its children")
check(root.healthBar.fsFillErase == he.handle and root.powerBar.fsFillErase == pe.handle, "erase handles not kept on the bars")
-- The health bar ALSO keeps its own bottom-right chamfer mid-plate while the power strip grows the
-- plate below it (the approved look). It is a gated wedge on the health mask only; the power strip
-- has none (its BOTTOM-RIGHT is the plate corner, the root erase owns it).
check(#__gates == 1 and __gates[1].anchor == root.healthBar and __gates[1].host == he.host, "no gated mid-plate wedge on the health bar")
check(__gates[1].c == 6 and colorEq(__gates[1].color, FS.Theme.COLOR_BAR_TRACK), "mid-plate wedge not chamfer 6 in the track colour")
check(root.fsMidWedge == __gates[1].bar, "the gate is not kept on the plate")
check(root.powerBar.fsFillErase and not root.powerBar.fsMidWedge, "the power strip got a mid-plate wedge")
-- closed at build: the sizer's own reset value
check(__gates[1].bar._args.SetValue == nil or __gates[1].bar._args.SetValue[1] == 0, "gate not closed at build")

-- the stroke is drawn ABOVE the erase (R2), so the erase cannot overpaint it
local host = root.fsBorder._parent
check(host ~= root and host._parent == root, "border not re-hosted on a child frame of the plate")
check(host:GetFrameLevel() > root.healthBar:GetFrameLevel() + FS.Theme.BAR_CORNER_MASK_LEVEL, "stroke host not above the health mask")
check(host:GetFrameLevel() > root.powerBar:GetFrameLevel() + FS.Theme.BAR_CORNER_MASK_LEVEL, "stroke host not above the power mask")
"""),

    ("a refused stroke re-host logs one degrade across plates and does not error", "true", r"""
boot()
local realAdd = FS.Theme.AddPanelChrome
FS.Theme.AddPanelChrome = function(frame, opts)
    local fill, glow, border = realAdd(frame, opts)
    border.SetParent = function() error("boom: SetParent") end -- instance field wins over FrameM
    return fill, glow, border
end
addPlate("nameplate1")
addPlate("nameplate2")
local r1, r2 = FS.framesByUnit.nameplate1, FS.framesByUnit.nameplate2
check(r1 and r2 and r1 ~= r2, "both plates did not build")
check(r1.fsBorder._parent == r1 and r2.fsBorder._parent == r2, "a refused border moved anyway")
check(degraded("nameplate_stroke_reparent") == 1,
    "stroke reparent degrade logged " .. degraded("nameplate_stroke_reparent") .. " times")
"""),

    ("the cut wedge is anchored to the plate root, so no refit timer, no SetRadius, UI scale and plate-scale events do nothing", "true", r"""
PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1440 end }
__effScale = 768 / 1440
boot()
addPlate("nameplate1"); addPlate("nameplate2")
check(pendingTimers() == 0, "a plate add scheduled a deferred refit: " .. pendingTimers())
local before = #__cutErase
__effScale = (768 / 1440) * 1.437   -- the selected-plate scale the engine applies
fire("PLAYER_TARGET_CHANGED")
fire("UI_SCALE_CHANGED")
fire("DISPLAY_SIZE_CHANGED")
fire("CVAR_UPDATE", "nameplateSelectedScale", "1.2")
check(pendingTimers() == 0, "a scale event scheduled a refit: " .. pendingTimers())
check(#__cutErase == before and #__fillCorners == 0, "a scale event rebuilt the wedges")
"""),

    ("a client that cannot slice the erase falls back to the unit-sized quads at the plate chamfer", "true", r"""
__eraseRefused = true
boot()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
check(#__cutErase == 0, "setup: the erase was not refused")
local hf, pf
for _, f in ipairs(__fillCorners) do
    if f.anchor == root.healthBar then hf = f end
    if f.anchor == root.powerBar then pf = f end
end
check(hf and hf.radius == 6, "fallback health chamfer not 6: " .. tostring(hf and hf.radius))
check(pf and pf.radius == 6, "fallback power chamfer not 6: " .. tostring(pf and pf.radius))
check(hf.handle.quads[1]._shown and hf.handle.quads[2]._shown, "a fallback health quad was hidden")
for _, q in ipairs(pf.handle.quads) do
    if q.fsCutCorner == "TOPLEFT" then check(q._shown == false, "fallback power TOP-LEFT quad not hidden")
    else check(q._shown, "fallback power BOTTOM-RIGHT quad hidden") end
end
check(#__leadCorners == 0, "the fallback built a leading-edge quad under cut")
check(root.healthBar.fsFillErase == nil and root.fsMidWedge == nil, "a refused erase was recorded as built")
check(#__gates == 0, "the fallback built a gated wedge")
UnitPowerMax = function() return 100 end
fire("UNIT_MAXPOWER", "nameplate1")
check(root.fsSizer._args.SetValue[1] == 100, "the sizer plumbing broke without a gate")
"""),

    ("a refused gated wedge sends the whole plate to the quad fallback, with no erase left drawn", "true", r"""
__gateRefused = true
boot()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
check(root.healthBar.fsFillErase == nil and root.fsMidWedge == nil, "half the erase pair was kept")
local drawn = 0
for _, e in ipairs(__cutErase) do
    if e.handle.texture:IsShown() and e.handle.frame:IsShown() then drawn = drawn + 1 end
end
check(drawn == 1, "the unused erase was left drawn on top of the quads (the overshoot would be back): " .. drawn)
local hf
for _, f in ipairs(__fillCorners) do if f.anchor == root.healthBar then hf = f end end
check(hf and hf.radius == 6, "no quad fallback after a refused gate")
"""),

    ("the mid-plate wedge opens and closes with the plate's growth, fed the sizer's own value", "true", r"""
UnitPower = function() return 50 end
UnitPowerMax = function() return 100 end
boot()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
local sizer, gate = root.fsSizer, root.fsMidWedge
local function last(f) return f._args.SetValue and f._args.SetValue[1] end
check(gate, "setup: no gate")
-- a unit with a power pool: the strip shows and the plate grows; the wedge opens with it
check(root.powerBar:IsShown(), "setup: the power strip is hidden")
check(last(sizer) == 100 and last(gate) == 100, "pool: sizer " .. tostring(last(sizer)) .. " gate " .. tostring(last(gate)))
-- a mana-type unit with NO pool: the strip is shown but the plate does not grow. A plain power
-- type test would still open the wedge here (the common mob case); the sizer value closes it.
UnitPowerMax = function() return 0 end
fire("UNIT_MAXPOWER", "nameplate1")
check(root.powerBar:IsShown(), "setup: a mana-type unit with max 0 hides its strip")
check(last(sizer) == 0 and last(gate) == 0, "no pool: sizer " .. tostring(last(sizer)) .. " gate " .. tostring(last(gate)))
-- a nil max collapses both
UnitPowerMax = function() return 100 end
fire("UNIT_MAXPOWER", "nameplate1")
check(last(gate) == 100, "setup: the pool did not reopen the gate")
UnitPowerMax = function() return nil end
fire("UNIT_MAXPOWER", "nameplate1")
check(last(sizer) == 0 and last(gate) == 0, "nil max: sizer " .. tostring(last(sizer)) .. " gate " .. tostring(last(gate)))
-- a power type with no strip hides it and closes both
UnitPowerMax = function() return 100 end
fire("UNIT_MAXPOWER", "nameplate1")
UnitPowerType = function() return 99 end
fire("UNIT_DISPLAYPOWER", "nameplate1")
check(not root.powerBar:IsShown(), "setup: an unlisted power type kept the strip")
check(last(sizer) == 0 and last(gate) == 0, "unlisted type: sizer " .. tostring(last(sizer)) .. " gate " .. tostring(last(gate)))
-- release and re-acquire: both start closed
UnitPowerType = function() return 0 end
fire("UNIT_MAXPOWER", "nameplate1")
check(last(gate) == 100, "setup: reopened")
fire("NAME_PLATE_UNIT_REMOVED", "nameplate1")
check(last(sizer) == 0 and last(gate) == 0, "release: sizer " .. tostring(last(sizer)) .. " gate " .. tostring(last(gate)))
UnitPowerMax = function() return 100 end
addPlate("nameplate2")
check(FS.framesByUnit.nameplate2 == root, "setup: the pooled plate was not reused")
check(last(sizer) == 100 and last(gate) == 100, "re-acquire: both follow the new unit")
"""),

    ("without SetReverseFill the plate is always grown, so the mid-plate wedge is pinned open on every path", "true", r"""
__kindMissing.StatusBar = { SetReverseFill = true }
UnitPower = function() return 0 end
UnitPowerMax = function() return 0 end
boot()
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
local function last(f) return f._args.SetValue and f._args.SetValue[1] end
check(root.fsSizerAnchor == root.fsSizer, "setup: SetReverseFill was not missing")
check(root.fsMidWedge, "setup: no gate")
check(last(root.fsMidWedge) == 1, "acquire, max 0: wedge " .. tostring(last(root.fsMidWedge)))
UnitPowerMax = function() return nil end
fire("UNIT_MAXPOWER", "nameplate1")
check(last(root.fsMidWedge) == 1, "nil max: wedge " .. tostring(last(root.fsMidWedge)))
UnitPowerMax = function() return 100 end
UnitPowerType = function() return 99 end
fire("UNIT_DISPLAYPOWER", "nameplate1")
check(not root.powerBar:IsShown(), "setup: an unlisted power type kept the strip")
check(last(root.fsMidWedge) == 1, "unlisted type: wedge " .. tostring(last(root.fsMidWedge)))
fire("NAME_PLATE_UNIT_REMOVED", "nameplate1")
check(last(root.fsMidWedge) == 1, "release: wedge " .. tostring(last(root.fsMidWedge)))
UnitPowerType = function() return 0 end
UnitPowerMax = function() return 0 end
addPlate("nameplate2")
check(FS.framesByUnit.nameplate2 == root, "setup: the pooled plate was not reused")
check(last(root.fsMidWedge) == 1, "re-acquire: wedge " .. tostring(last(root.fsMidWedge)))
"""),

    ("a throwing gated wedge hides the built erase, uses the quads and logs once", "true", r"""
__gateThrows = true
boot()
addPlate("nameplate1"); addPlate("nameplate2")
local root = FS.framesByUnit.nameplate1
check(#__cutErase >= 1, "setup: the erase was never built")
local healthErases = 0
for _, e in ipairs(__cutErase) do
    if e.host._parent == root.healthBar or e.host._parent == FS.framesByUnit.nameplate2.healthBar then
        healthErases = healthErases + 1
        check(not e.handle.texture:IsShown() and not e.handle.frame:IsShown(), "the health bar's built erase was left drawn")
    end
end
check(healthErases == 2, "setup: expected one health erase per plate, got " .. healthErases)
check(root.healthBar.fsFillErase == nil and root.fsMidWedge == nil, "half the erase pair was kept")
local hf
for _, f in ipairs(__fillCorners) do if f.anchor == root.healthBar then hf = f end end
check(hf and hf.radius == 6, "no quad fallback after a throwing gate")
check(degraded("plate_gated_wedge") == 1, "degrade logged " .. degraded("plate_gated_wedge") .. " times")
"""),

    ("a secret power max reaches the sizer and the wedge gate untouched, and a refusing sizer reserves both", "true", r"""
local SECRET = setmetatable({}, { __eq = function() error("compared a secret") end,
    __lt = function() error("compared a secret") end, __le = function() error("compared a secret") end })
UnitPower = function() return SECRET end
UnitPowerMax = function() return SECRET end
boot()
FS.IsSecret = function(v) return rawequal(v, SECRET) end
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
local function last(f) return f._args.SetValue and f._args.SetValue[1] end
check(rawequal(last(root.fsSizer), SECRET) and rawequal(last(root.fsMidWedge), SECRET), "the secret max was altered or compared on the way to the setters")
-- a sizer that refuses anything but 0 and 1: the strip is reserved and the wedge opened with it
local realSet = root.fsSizer.SetValue
root.fsSizer.SetValue = function(self, v)
    if rawequal(v, SECRET) then error("boom: refused") end
    return realSet(self, v)
end
fire("UNIT_MAXPOWER", "nameplate1")
check(last(root.fsSizer) == 1 and last(root.fsMidWedge) == 1, "refused max: sizer " .. tostring(last(root.fsSizer)) .. " gate " .. tostring(last(root.fsMidWedge)))
"""),

    ("/fsplate reads back the scale, the stroke chamfer in units, pixels per unit, the bar inset in texels and which erase the bars use", "true", r"""
PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1440 end }
__effScale = (768 / 1440) * 1.437
local printed = {}
print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
UnitIsUnit = function(u, t) return u == "nameplate2" and t == "target" end
UIParent = __newFrame("Frame", nil, nil)
boot()
addPlate("nameplate1"); addPlate("nameplate2")
check(type(SlashCmdList.FSPLATE) == "function" and SLASH_FSPLATE1 == "/fsplate", "/fsplate not registered")
SlashCmdList.FSPLATE()
local text = table.concat(printed, "\n")
check(text:find("target nameplate2", 1, true), "no target plate line:\n" .. text)
check(text:find("other nameplate1", 1, true), "no non-target plate line:\n" .. text)
check(text:find("effScale=0.766", 1, true), "effective scale missing:\n" .. text)
check(text:find("strokeChamferUnits=4.1", 1, true), "stroke chamfer in units missing:\n" .. text)
check(text:find("unitPx=1.437", 1, true), "pixels per unit missing:\n" .. text)
check(text:find("deltaAt1pxTexel=1.437", 1, true), "bar inset in texels (at one pixel per texel) missing:\n" .. text)
check(text:find("erase=nineslice", 1, true), "erase mode missing:\n" .. text)
check(not text:find("wedge=", 1, true), "the retired wedge readout is still printed:\n" .. text)
"""),

    ("round chrome keeps the old fill radius and four corners", "true", r"""
boot()
FS.Theme.CHROME_CORNERS = "round"
FS.Theme.SLICE_MARGIN = 5
addPlate("nameplate1")
local root = FS.framesByUnit.nameplate1
local hf, pf
for _, f in ipairs(__fillCorners) do
    if f.anchor == root.healthBar then hf = f end
    if f.anchor == root.powerBar then pf = f end
end
check(hf.radius == 4 and pf.radius == 2.5, "round radii changed: " .. tostring(hf.radius) .. " " .. tostring(pf.radius))
-- the round path keeps its moving right-end quads (pill ends follow the fill)
local lead = 0
for _, l in ipairs(__leadCorners) do
    if l.bar == root.healthBar or l.bar == root.powerBar then lead = lead + 1 end
end
check(lead == 2, "round chrome lost its leading-edge quads: " .. lead)
for _, q in ipairs(pf.handle.quads) do check(q._shown, "round power quad hidden") end
check(root.fsBorder._parent == root, "round border was re-hosted")
"""),
]


def run_case(name: str, template: str, body: str, source: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__SRC = source
    lua.execute(f"__template = {template}")
    try:
        lua.execute(body)
    except LuaError as err:
        return str(err)
    return None


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    failures = 0
    for name, template, body in CASES:
        error = run_case(name, template, body, source)
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
