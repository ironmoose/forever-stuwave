#!/usr/bin/env python3
"""Runs the real Buffs.lua (player buffs/debuffs) headless against a mock WoW API.

Pins the in-combat display: the player buff and debuff rows are drawn by AuraContainer
frames (the Plater/ElvUI design), so the engine reads and draws the auras and no aura data
ever enters addon Lua. That works in and out of combat, where every addon aura read is
refused. What the checks pin:

  * two containers (buffs, debuffs) for unit "player", parented to the layout holders,
    anchored TOPRIGHT, flowing left then down, wrapping at the mockup's column counts;
  * buffs are one HELPFUL group; debuffs are HARMFUL split by dispel type (the border colour
    is baked per group, like the nameplate row), the groups partition every dispel name;
  * weapon enchants are the container's own item enchantments (after the aura groups, on a
    new line); a client without AddItemEnchantment keeps the old polled enchant buttons;
  * initializeFrame styles the engine button on a plain child face (cut-corner tile, icon
    inset, label plates, duration text tinted by remaining time through a colour curve),
    keeps the button's mouse on (tooltip, right-click cancel) and survives missing methods;
  * the row never depends on an aura read in combat: the read APIs throw there, the cache
    freezes at lockdown (one last read at the combat-start instant), refreshes at regen, and
    only plain values ever enter it;
  * AuraContainer missing or failing: the old custom row, drawn from the cache, logged once;
  * FS.AurasReadable (the real function out of Theme.lua) fails closed: readable only when
    InCombatLockdown is false AND C_Secrets.ShouldAurasBeSecret (when it exists) plainly says
    false; and the snapshot is retried a few times after combat, because that answer can lag.

The mock is NOT the real client. Theme and FrameHelpers are stubs here; Buffs.lua and the
FS.AurasReadable text from Theme.lua are loaded unchanged.

    python3 tools/buffs-harness.py
    BUFFS_LUA=/path/to/mutant.lua python3 tools/buffs-harness.py

Exit 0 = every check passed.
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
# BUFFS_LUA / THEME_LUA point the run at a mutant copy (the other harnesses do the same).
SOURCE = Path(os.environ.get("BUFFS_LUA", ADDON / "Modules/Auras/Buffs.lua"))
THEME = Path(os.environ.get("THEME_LUA", ADDON / "Core/Theme.lua"))


def theme_readiness_lua() -> str:
    """The REAL aura readiness block out of Theme.lua: `function FS.AurasReadable()` through the
    `-- END aura readiness` marker (it also holds FS.OnAurasReadable and the regen retry chain).
    It reads FS.IsSecret, C_Secrets, InCombatLockdown, C_Timer and CreateFrame at call time."""
    src = THEME.read_text(encoding="utf-8")
    m = re.search(r"^function FS\.AurasReadable\(\)\n.*?^-- END aura readiness$", src, re.M | re.S)
    if not m:
        sys.exit("Theme.lua: the `function FS.AurasReadable()` .. `-- END aura readiness` block was not found")
    return m.group(0) + "\n"


def theme_dispel_lua() -> str:
    """The REAL `Theme.DISPEL_COLORS = { ... }` table out of Theme.lua."""
    src = THEME.read_text(encoding="utf-8")
    m = re.search(r"^Theme\.DISPEL_COLORS = \{\n.*?^\}", src, re.M | re.S)
    if not m:
        sys.exit("Theme.lua: `Theme.DISPEL_COLORS = {` not found")
    return "local Theme = FS.Theme\n" + m.group(0) + "\n"


MOCK = r"""
__realType = type
__combat = false            -- InCombatLockdown()
__apiSecret = nil           -- ShouldAurasBeSecret answer; nil = follows __combat
__noApi = false             -- C_Secrets absent
__template = true           -- C_XMLUtil.GetTemplateInfo("CustomAuraContainerTemplate")
__acThrows = false          -- CreateFrame("AuraContainer") raises
__acGroupThrows = nil       -- AddAuraGroup(<group name>) raises (after the frame exists)
__noEnchantApi = false      -- the container has no AddItemEnchantment
__noCurve = false           -- no C_CurveUtil / Enum.DurationTextBindingProperty
__rejectTextColor = false   -- SetDurationText raises when options.textColor is given
__useKeyDown = false        -- ActionButtonUseKeyDown
__seq, __now = 0, 100
__frames, __acs, __printed, __degrade, __reports, __skins, __seated = {}, {}, {}, {}, {}, {}, {}
__readAttempts = 0          -- GetAuraDataByIndex / UnitAura calls, refused ones included
__enchantReads = 0
__enchants = {}             -- { main = { remainingMS, charges }, off = ... }
__auras = { HELPFUL = {}, HARMFUL = {} }
__dimmed = {}

function print(...)
    local t = {}
    for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(t, " ")
end
function hooksecurefunc() end
function InCombatLockdown() return __combat end
function UnitAffectingCombat() if __affecting ~= nil then return __affecting end return __combat end
__affecting = nil           -- UnitAffectingCombat answer; nil = follows __combat
__timers = {}               -- C_Timer.After callbacks, run by the test
C_Timer = { After = function(delay, fn) __timers[#__timers + 1] = { delay, fn } end }
__enchantThrows = nil       -- AddItemEnchantment(<slot>) raises for this slot
__layoutThrows = false      -- SetItemEnchantmentLayout raises
function GetTime() return __now end
function UnitExists() return true end

-- A secret stand-in: any attempt to use it raises. FS.IsSecret recognises it.
function __secret()
    return setmetatable({ __isSecret = true }, {
        __eq = function() error("secret compared") end, __lt = function() error("secret compared") end,
        __le = function() error("secret compared") end, __add = function() error("secret arithmetic") end,
        __concat = function() error("secret concatenated") end, __len = function() error("secret length") end,
        __index = function(_, k) if k ~= "__isSecret" then error("secret indexed") end end,
    })
end

-- Frames: capitalised keys are widget methods (recorded in call order), lowercase keys are
-- plain fields. Create* answers a child, Get* a ghost.
local FrameM = {}
local FrameMT = {}
FrameMT.__index = function(self, k)
    local m = FrameM[k]
    if m then return m end
    if __realType(k) ~= "string" or not k:match("^%u") then return nil end
    local miss = rawget(self, "_missing")
    if miss and miss[k] then return nil end
    return function(me, ...)
        me._calls[k] = (me._calls[k] or 0) + 1
        me._args[k] = { ... }
        me._log[#me._log + 1] = k
        if me._throws and me._throws[k] then error("boom: " .. k, 2) end
        local what = k:match("^Create(%a+)")
        if what then return __newFrame(what, nil, me) end
        if k:match("^Get") then return __newFrame("Ghost", nil, me) end
    end
end
function __newFrame(kind, name, parent)
    local f = setmetatable({ _kind = kind, _name = name, _parent = parent, _events = {}, _scripts = {},
        _calls = {}, _args = {}, _log = {}, _shown = false, _points = {} }, FrameMT)
    if __realType(name) == "string" then _G[name] = f end
    __frames[#__frames + 1] = f
    return f
end
function FrameM.SetScript(self, k, fn) self._scripts[k] = fn end
function FrameM.RegisterEvent(self, e) self._events[e] = true end
function FrameM.UnregisterEvent(self, e) self._events[e] = nil end
function FrameM.Show(self) self._calls.Show = (self._calls.Show or 0) + 1; self._shown = true end
function FrameM.Hide(self) self._calls.Hide = (self._calls.Hide or 0) + 1; self._shown = false end
function FrameM.IsShown(self) return self._shown end
function FrameM.GetParent(self) return self._parent end
function FrameM.SetParent(self, p) self._parent = p end
function FrameM.ClearAllPoints(self) self._points = {} end
function FrameM.SetPoint(self, ...) self._points[#self._points + 1] = { ... } end
function FrameM.GetHeight() return 32 end
function FrameM.GetWidth() return 32 end
function FrameM.GetFont() return "MONO", 9, "" end
function FrameM.SetText(self, t) self._text = t end
function FrameM.GetText(self) return self._text end
function FrameM.SetTexture(self, t) self._texture = t; self._calls.SetTexture = (self._calls.SetTexture or 0) + 1 end

-- AuraContainer: strict, only the methods the addon is allowed to call.
local ACM = {}
local allowed = { "SetSize", "SetFlowLayoutAnchorPoint", "SetFlowLayoutGrowthDirection",
    "SetFlowLayoutMaximumLineSize", "SetUnit", "SetEnabled", "UpdateAllAuras", "AddAuraGroup",
    "AddItemEnchantment", "SetItemEnchantmentLayout", "SetFrameLevel", "SetPoint", "ClearAllPoints",
    "Show", "Hide", "IsShown", "SetParent" }
for _, n in ipairs(allowed) do
    ACM[n] = function(self, ...)
        self._calls[n] = (self._calls[n] or 0) + 1
        self._args[n] = { ... }
        self._log[#self._log + 1] = n
        if n == "SetUnit" then self._unit = (...) end
        if n == "SetEnabled" then self._enabled = (...) end
        if n == "SetPoint" then self._points[#self._points + 1] = { ... } end
        if n == "ClearAllPoints" then self._points = {} end
        if n == "Show" then self._shown = true end
        if n == "Hide" then self._shown = false end
        if n == "AddAuraGroup" then
            local name, filter, opts = ...
            if name == __acGroupThrows then error("boom: AddAuraGroup " .. name) end
            self._groups[name] = { filter = filter, opts = opts }
            self._groupOrder[#self._groupOrder + 1] = name
        end
        if n == "AddItemEnchantment" then
            if (...) == __enchantThrows then error("boom: AddItemEnchantment") end
            self._enchants[(...)] = select(2, ...)
        end
        if n == "SetItemEnchantmentLayout" then
            if __layoutThrows then error("boom: SetItemEnchantmentLayout") end
            self._enchantLayout = (...)
        end
        if n == "IsShown" then return self._shown end
    end
end
local ACMT = { __index = function(t, k)
    if k == "AddItemEnchantment" and __noEnchantApi then return nil end
    if k == "SetItemEnchantmentLayout" and __noEnchantApi then return nil end
    return ACM[k]
end }

function CreateFrame(kind, name, parent, tmpl)
    if kind == "AuraContainer" then
        if __acThrows then error("boom: CreateFrame AuraContainer") end
        assert(tmpl == "CustomAuraContainerTemplate", "wrong template: " .. tostring(tmpl))
        local f = setmetatable({ _kind = kind, _tmpl = tmpl, _calls = {}, _args = {}, _log = {}, _groups = {},
            _groupOrder = {}, _enchants = {}, _points = {}, _shown = false, _parent = parent }, ACMT)
        __acs[#__acs + 1] = f
        return f
    end
    return __newFrame(kind, name, parent)
end
UIParent = __newFrame("Frame", nil, nil)
BuffFrame, DebuffFrame = __newFrame("Frame", nil, nil), __newFrame("Frame", nil, nil)

C_XMLUtil = { GetTemplateInfo = function(name)
    if __template == "throw" then error("boom: GetTemplateInfo") end
    if __template and name == "CustomAuraContainerTemplate" then return { name = name } end
end }
AnchorUtil = { FlowDirection = { Right = 1, Left = -1, Up = 1, Down = -1 } }
AuraContainerSortMethod = { Default = 0 }
AuraContainerSortDirection = { Normal = 0 }
AuraContainerItemEnchantmentSlot = { MainHand = 0, OffHand = 1, Ranged = 2 }
CustomAuraContainerItemEnchantmentPlacement = { BeforeAuraGroups = 0, AfterAuraGroups = 1 }
C_CVar = { GetCVarBool = function() return __useKeyDown end }
-- DebuffTypeColor does not exist on 16001, so the mock does not define it either.
function CreateColor(r, g, b, a) return { r = r, g = g, b = b, a = a or 1 } end
__curves = {}
function __installCurve()
    C_CurveUtil = { CreateColorCurve = function()
        local c = { points = {} }
        function c:SetType(t) self.type = t end
        function c:AddPoint(x, color) self.points[#self.points + 1] = { x = x, color = color } end
        __curves[#__curves + 1] = c
        return c
    end }
    Enum = { LuaCurveType = { Linear = 0, Step = 1 }, DurationTextBindingProperty = { RemainingDuration = 0 } }
end
function __removeCurve() C_CurveUtil, Enum = nil, nil end
__installCurve()

-- Aura reads: refused while auras are secret, every attempt counted.
function __aurasSecret()
    if __noApi then return __combat end
    if __apiSecret ~= nil then return __apiSecret end
    return __combat
end
C_UnitAuras = { GetAuraDataByIndex = function(unit, index, filter)
    __readAttempts = __readAttempts + 1
    if __aurasSecret() then error("Auras cannot be accessed when secret while tainted") end
    return __auras[filter:match("^%u+")][index]
end }
UnitAura = function() __readAttempts = __readAttempts + 1; error("UnitAura must not be used") end
function GetWeaponEnchantInfo()
    __enchantReads = __enchantReads + 1
    local m, o = __enchants.main, __enchants.off
    return m ~= nil, m and m[1] or 0, m and m[2] or 0, 0, o ~= nil, o and o[1] or 0, o and o[2] or 0, 0
end
function GetInventorySlotInfo(name) return name == "MainHandSlot" and 16 or 17 end
function GetInventoryItemTexture() return "enchant-icon" end
GameTooltip = __newFrame("Frame", nil, nil)

-- Theme / FrameHelpers: stubs with real values for what Buffs.lua reads.
local COLOR_BORDER = { 0.49, 0.23, 0.93, 1 }
local COLOR_TEXT_WHITE = { 1, 1, 1, 1 }
FS = {
    IsSecret = function(v) return __realType(v) == "table" and rawget(v, "__isSecret") == true end,
    LogDegradeOnce = function(key, msg) __degrade[#__degrade + 1] = key end,
    Layout = { buffs = {}, debuffs = {}, applied = {} },
}
function FS.Layout.Apply(frame, id) FS.Layout.applied[#FS.Layout.applied + 1] = { frame = frame, id = id } end
FS.Theme = {
    COLOR_BORDER = COLOR_BORDER, COLOR_TEXT_WHITE = COLOR_TEXT_WHITE,
    ApplyMono = function(fs, size) fs._mono = size; fs._monoCalls = (fs._monoCalls or 0) + 1 end,
    CutSizeIcon = function(h) return h >= 36 and 6 or (h >= 24 and 4 or 3) end,
    SkinButton = function(button, opts)
        __skins[#__skins + 1] = { button = button, opts = opts }
        local ring = __newFrame("Texture", nil, button)
        button.fsSkin = { chamfer = opts and opts.chamfer or 6, border = { ring = ring } }
        return button.fsSkin
    end,
}
FS.FrameHelpers = {
    DimBlizzardFrame = function(f) __dimmed[#__dimmed + 1] = f end,
    NewStepRunner = function(fmt)
        return function() end, function(label, err) __reports[#__reports + 1] = label .. ": " .. tostring(err) end
    end,
    SafeRegisterUnitEvent = function(events, event, unit)
        events._unitEvents = events._unitEvents or {}
        events._unitEvents[event] = unit
    end,
    SetAuraLabel = function(fs, text) fs._text = text end,
    ReadAuraSlot = function(unit, index, filter, report)
        if not FS.AurasReadable() then return nil end
        local ok, data = pcall(C_UnitAuras.GetAuraDataByIndex, unit, index, filter)
        if not ok then report("read aura (C_UnitAuras)", data) return nil end
        if not data then return nil end
        return { name = data.name, icon = data.icon, count = data.applications or 0,
            dispelType = data.dispelName, duration = data.duration or 0,
            expirationTime = data.expirationTime or 0, caster = data.sourceUnit }
    end,
    SeatAuraTile = function(button)
        __seated[#__seated + 1] = { button = button, hadLabels = button.count ~= nil or button.duration ~= nil }
    end,
    ShowAuraTooltip = function() end,
}
function __setClient()
    if __noApi then C_Secrets = nil
    else C_Secrets = { ShouldAurasBeSecret = function() return __aurasSecret() end } end
end

function boot()
    __setClient()
    loadstring(__DISPEL_SRC, "@Theme.lua(DISPEL_COLORS)")()
    loadstring(__READABLE_SRC, "@Theme.lua(readiness)")()
    local fn = assert(loadstring(__SRC, "@Buffs.lua"))
    fn("forever-stuwave", FS)
end

-- Test helpers ------------------------------------------------------------------------
function check(c, msg) if not c then error("CHECK FAILED: " .. msg, 2) end end
function evframe()
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and f._unitEvents and f._unitEvents.UNIT_AURA then return f end
    end
end
function tickframe()
    for _, f in ipairs(__frames) do if f._scripts.OnUpdate then return f end end
end
-- Every frame with an OnEvent script that registered `event` (or any, for a plain Frame the
-- handler was set on) gets it, in creation order, like the client; a throw from one handler
-- is an escaped error here, so a test sees it.
function fire(event, ...)
    check(evframe(), "no event frame")
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and (f._events[event] or f == evframe()) then
            local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
            check(ok, "event handler threw on " .. event .. ": " .. tostring(err))
        end
    end
end
function aura(name, opts)
    opts = opts or {}
    return { name = name, icon = "icon-" .. name, applications = opts.count or 1, dispelName = opts.dispel,
        duration = opts.duration or 60, expirationTime = opts.expires or (__now + 60), sourceUnit = opts.source }
end
function degraded(key)
    local n = 0
    for _, k in ipairs(__degrade) do if k == key then n = n + 1 end end
    return n
end
function children(parent, kind)
    local out = {}
    for _, f in ipairs(__frames) do
        if f._parent == parent and (kind == nil or f._kind == kind) then out[#out + 1] = f end
    end
    return out
end
function colorEq(a, b)
    if not (a and b) then return false end
    local ar, ag, ab = a.r or a[1], a.g or a[2], a.b or a[3]
    local br, bg, bb = b.r or b[1], b.g or b[2], b.b or b[3]
    return ar == br and ag == bg and ab == bb
end
-- Blizzard's AuraContainerUtil.DoesAuraPassCandidateFilters, the dispel part.
function passes(cf, dispel)
    if cf == nil then return true end
    if cf.excludeDispelTypes and cf.excludeDispelTypes[dispel] then return false end
    if cf.includeDispelTypes and not cf.includeDispelTypes[dispel] then return false end
    return true
end
function newButton() return __newFrame("AuraButton", nil, nil) end
function visibleTiles(holder)
    local out = {}
    for _, f in ipairs(children(holder, "Frame")) do
        if f.icon and f._shown then out[#out + 1] = f end
    end
    return out
end
"""

# Each case: (name, setup Lua, body Lua). Setup runs before boot(); the body runs after the mock.
CASES: list[tuple[str, str, str]] = [
    ("two containers for the player, parented to the holders, anchored top right, flowing left then down", "", r"""
boot()
local b, d = FS.buffsAuraContainer, FS.debuffsAuraContainer
check(b and d and b ~= d, "no engine containers exported")
check(#__acs == 2, "AuraContainer count " .. #__acs)
check(b._parent == FS.buffsContainer and d._parent == FS.debuffsContainer, "containers not parented to the holders")
for _, c in ipairs({ b, d }) do
    check(c._tmpl == "CustomAuraContainerTemplate", "template")
    check(c._unit == "player" and c._enabled == true and c._shown, "not live for the player")
    local p = c._points[1]
    check(p and p[1] == "TOPRIGHT" and p[3] == "TOPRIGHT" and p[2] == c._parent, "not anchored TOPRIGHT to its holder")
    check(c._args.SetFlowLayoutAnchorPoint[1] == "TOPRIGHT", "flow anchor")
    check(c._args.SetFlowLayoutGrowthDirection[1] == -1 and c._args.SetFlowLayoutGrowthDirection[2] == -1,
        "growth is not left then down")
end
check(b._args.SetFlowLayoutMaximumLineSize[1] == 10 * 36 + 1, "buff row wrap " .. tostring(b._args.SetFlowLayoutMaximumLineSize[1]))
check(d._args.SetFlowLayoutMaximumLineSize[1] == 8 * 36 + 1, "debuff row wrap " .. tostring(d._args.SetFlowLayoutMaximumLineSize[1]))
check(FS.PlayerAuras.IsEngineDrawn() == true, "IsEngineDrawn")
check(evframe()._unitEvents.UNIT_AURA == "player", "UNIT_AURA not registered for the player")
"""),
    ("buffs are one HELPFUL group; every group lays out 32 tiles with a 4 gap", "", r"""
boot()
local b = FS.buffsAuraContainer
check(#b._groupOrder == 1 and b._groupOrder[1] == "buffs", "buff groups: " .. table.concat(b._groupOrder, ","))
local g = b._groups.buffs
check(g.filter == "HELPFUL" and g.opts.maxFrameCount == 32, "buff group filter/max")
check(g.opts.candidateFilters == nil, "buff group has candidate filters")
local l = g.opts.layout
check(l.elementWidth == 32 and l.elementHeight == 32 and l.elementSpacing == 4 and l.lineSpacing == 4, "buff layout")
check(l.groupSpacing == 0 and l.groupLineSpacing == 0, "group spacing must add nothing to the even 4 gap")
check(type(g.opts.initializeFrame) == "function", "no initializeFrame")
check(g.opts.sortMethod == 0 and g.opts.sortDirection == 0, "sort defaults")
"""),
    ("debuffs are HARMFUL split by dispel type, and the groups partition every dispel name", "", r"""
boot()
local d = FS.debuffsAuraContainer
check(#d._groupOrder == 5, "debuff group count " .. #d._groupOrder)
for _, name in ipairs(d._groupOrder) do
    local g = d._groups[name]
    check(g.filter == "HARMFUL" and g.opts.maxFrameCount == 16, name .. ": filter/max")
    local l = g.opts.layout
    check(l.elementWidth == 32 and l.elementHeight == 32 and l.elementSpacing == 4 and l.lineSpacing == 4, name .. ": layout")
    check(l.groupSpacing == 0 and l.groupLineSpacing == 0, name .. ": group spacing must add nothing to the even 4 gap")
end
for _, dispel in ipairs({ "Magic", "Curse", "Disease", "Poison", "Bleed", "none-sentinel" }) do
    local hits = {}
    for _, name in ipairs(d._groupOrder) do
        if passes(d._groups[name].opts.candidateFilters, dispel) then hits[#hits + 1] = name end
    end
    check(#hits == 1, dispel .. " lands in " .. #hits .. " groups")
end
local noDispel = {}
for _, name in ipairs(d._groupOrder) do
    if passes(d._groups[name].opts.candidateFilters, nil) then noDispel[#noDispel + 1] = name end
end
check(#noDispel == 1, "an aura with no dispel type lands in " .. #noDispel .. " groups")
"""),
    ("initializeFrame styles the tile on a plain face and leaves the button's mouse on", "", r"""
boot()
local g = FS.buffsAuraContainer._groups.buffs
local button = newButton()
g.opts.initializeFrame(button)
check(button._args.SetSize and button._args.SetSize[1] == 32 and button._args.SetSize[2] == 32, "button not sized 32")
for _, k in ipairs({ "EnableMouse", "SetMouseClickEnabled", "SetMouseMotionEnabled", "SetHideTooltipInCombat" }) do
    check(button._calls[k] == nil, "the button's " .. k .. " was touched (tooltip and cancel need the mouse)")
end
check(button._args.SetCancelAuraButtons and button._args.SetCancelAuraButtons[1] == "RightButtonUp", "no right click cancel")
check(button._args.SetTooltipAnchorPoint and button._args.SetTooltipAnchorPoint[1] == "ANCHOR_TOPLEFT", "tooltip anchor")
check(button.icon == nil and button.fsSkin == nil and button.count == nil, "fields were written on the engine button")
local faces = children(button, "Frame")
check(#faces == 1, "expected one plain face frame, got " .. #faces)
local face = faces[1]
check(face._args.EnableMouse and face._args.EnableMouse[1] == false, "face mouse not off")
check(face.icon and face.count and face.duration, "face lacks icon/count/duration")
check(button._args.SetIcon[1] == face.icon, "SetIcon not given the face icon")
check(button._args.SetApplicationCount[1] == face.count, "SetApplicationCount not given the count")
local fs, opts = button._args.SetDurationText[1], button._args.SetDurationText[2]
check(fs == face.duration, "SetDurationText not given the duration")
check(face.count._mono == 10 and face.duration._mono == 9, "fonts not applied before the engine got them")
-- skinned on the face, cut ring 4, violet
check(#__skins == 1 and __skins[1].button == face, "SkinButton not run on the face")
check(__skins[1].opts.chamfer == 4 and colorEq(__skins[1].opts.borderColor, FS.Theme.COLOR_BORDER), "skin opts")
check(#__seated == 1 and __seated[1].button == face and __seated[1].hadLabels == false,
    "SeatAuraTile must run on the face without the label fields (it would add plates that never show)")
-- label plates: own, visible from the start, hugging the text (zero padding so an empty label draws nothing)
for _, label in ipairs({ face.count, face.duration }) do
    local plate = label.fsPlate
    check(plate and plate._calls.Hide == nil, "label plate missing or hidden")
    local tl, br = plate._points[1], plate._points[2]
    check(tl and tl[2] == label and tl[4] == 0, "plate left not flush with the text")
    check(br and br[2] == label and br[4] == 0, "plate right not flush with the text")
end
check(face.count._points[1][1] == "TOPRIGHT" and face.duration._points[1][1] == "BOTTOMRIGHT", "label corners")
"""),
    ("duration text turns pink through a colour curve under two minutes", "", r"""
boot()
local button = newButton()
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(button)
local opts = button._args.SetDurationText[2]
check(opts and opts.textColor, "no textColor option")
check(opts.textColor.property == 0, "property not RemainingDuration")
local curve = opts.textColor.curve
check(curve == __curves[1] and curve.type == 1, "not a Step colour curve")
check(#curve.points == 2, "points " .. #curve.points)
check(curve.points[1].x == 0 and colorEq(curve.points[1].color, { 0.925, 0.286, 0.600 }), "pink from 0")
check(curve.points[2].x == 120 and colorEq(curve.points[2].color, FS.Theme.COLOR_TEXT_WHITE), "white from 120 s")
"""),
    ("no curve API: the duration text still works, untinted", "__noCurve = true; __removeCurve()", r"""
boot()
local button = newButton()
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(button)
check(button._args.SetDurationText, "SetDurationText not called")
check(button._args.SetDurationText[2].textColor == nil, "textColor given without a curve API")
"""),
    ("an engine that refuses textColor gets the plain duration text", "__rejectTextColor = true", r"""
boot()
local calls = 0
local button = newButton()
button.SetDurationText = function(self, fs, opts)
    calls = calls + 1
    self._lastOpts = opts
    if opts and opts.textColor then error("boom: textColor") end
end
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(button)
check(calls == 2, "SetDurationText calls " .. calls)
check(button._lastOpts.textColor == nil, "the retry still carried textColor")
check(#__reports == 0, "a swallowed retry was reported")
"""),
    ("debuff tiles wear a baked dispel colour (no DebuffTypeColor on 16001), the rest and buffs the violet", "", r"""
boot()
check(DebuffTypeColor == nil, "the mock must not define DebuffTypeColor")
check(type(FS.Theme.DISPEL_COLORS) == "table", "the palette is not shared through FS.Theme.DISPEL_COLORS")
local d = FS.debuffsAuraContainer
local BAKED = {
    Magic = { 0.247, 0.780, 0.922 }, Curse = { 0.639, 0.208, 0.933 },
    Disease = { 0.627, 0.322, 0.176 }, Poison = { 0.251, 0.749, 0.251 },
}
local seenOther = false
local seen = {}
for _, name in ipairs(d._groupOrder) do
    local button = newButton()
    d._groups[name].opts.initializeFrame(button)
    local skin = __skins[#__skins]
    check(skin.button == children(button, "Frame")[1], name .. ": skin not on the face")
    local want
    local include = d._groups[name].opts.candidateFilters.includeDispelTypes
    for key, color in pairs(BAKED) do
        if include and include[key] then want = color; seen[key] = true end
    end
    if not want then want = FS.Theme.COLOR_BORDER; seenOther = true end
    check(colorEq(skin.opts.borderColor, want), name .. ": border colour is not the expected one")
end
check(seenOther, "no group wears the plain violet")
for key in pairs(BAKED) do check(seen[key], key .. " has no group") end
local b = newButton()
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(b)
check(colorEq(__skins[#__skins].opts.borderColor, FS.Theme.COLOR_BORDER), "buffs are not violet")
"""),
    ("right click cancels on key down when the client binds actions on key down", "__useKeyDown = true", r"""
boot()
local button = newButton()
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(button)
check(button._args.SetCancelAuraButtons[1] == "RightButtonDown", "cancel button " .. tostring(button._args.SetCancelAuraButtons[1]))
"""),
    ("a missing or throwing engine button method never stops the next step", "", r"""
boot()
local button = newButton()
button._throws = { SetIcon = true, SetCancelAuraButtons = true, SetTooltipAnchorPoint = true }
button._missing = { SetApplicationCount = true }
FS.buffsAuraContainer._groups.buffs.opts.initializeFrame(button)
check(button._args.SetDurationText, "SetDurationText not reached after SetIcon threw")
check(#__skins == 1, "skin not reached")
check(button._args.SetSize and button._args.SetSize[1] == 32, "SetSize not reached")
"""),
    ("weapon enchants are the container's own item enchantments, after the aura groups, on a new line", "", r"""
boot()
local b = FS.buffsAuraContainer
check(b._enchants[0] and b._enchants[1], "main hand and off hand not added")
check(type(b._enchants[0].initializeFrame) == "function", "enchantment has no initializeFrame")
local l = b._enchantLayout
check(l and l.placement == 1 and l.forceNewLine == true, "enchant layout placement/forceNewLine")
check(l.elementSpacing == 4 and l.elementWidth == 32 and l.elementHeight == 32, "enchant layout sizes")
check(__enchantReads == 0, "the polled enchant path ran next to the native one")
check(tickframe() == nil, "an OnUpdate ticker exists although nothing needs polling")
local button = newButton()
b._enchants[0].initializeFrame(button)
check(#__skins == 1 and colorEq(__skins[1].opts.borderColor, FS.Theme.COLOR_BORDER), "enchant tile not styled like a buff")
check(button._args.SetCancelAuraButtons[1] == "RightButtonUp", "enchant cancel")
"""),
    ("no native enchant API: the polled enchant buttons stay, and keep polling in combat", "__noEnchantApi = true; __enchants.main = { 120000, 0 }", r"""
boot()
local holder = FS.buffsContainer
local tiles = visibleTiles(holder)
check(#tiles == 1, "enchant tile not shown: " .. #tiles)
check(tiles[1].icon._texture == "enchant-icon", "enchant icon")
local tf = tickframe()
check(tf, "no ticker for the polled enchants")
__combat = true
__enchants.off = { 60000, 3 }
__now = __now + 1
tf._scripts.OnUpdate(tf, 1)
check(#visibleTiles(holder) == 2, "an in-combat poll missed the off hand enchant")
check(#__reports == 0, "enchant polling reported " .. tostring(__reports[1]))
"""),
    ("in combat nothing reads an aura and the containers are left alone", "", r"""
boot()
__auras.HELPFUL = { aura("Fortitude"), aura("Mark") }
__auras.HARMFUL = { aura("Curse of Agony", { dispel = "Curse" }) }
fire("UNIT_AURA")
local b, d = FS.buffsAuraContainer, FS.debuffsAuraContainer
local reads0 = __readAttempts
local counts = { b._calls.SetUnit, b._calls.SetEnabled, b._calls.Hide, d._calls.SetUnit, d._calls.Hide, b._calls.AddAuraGroup }
__combat = true
for _ = 1, 5 do fire("UNIT_AURA", "player", { isFullUpdate = true }) end
fire("PLAYER_ENTERING_WORLD")
check(__readAttempts == reads0, "aura reads attempted in combat: " .. (__readAttempts - reads0))
check(#__reports == 0, "a swallowed refusal was reported: " .. tostring(__reports[1]))
local after = { b._calls.SetUnit, b._calls.SetEnabled, b._calls.Hide, d._calls.SetUnit, d._calls.Hide, b._calls.AddAuraGroup }
for i = 1, #counts do check(after[i] == counts[i], "a container call changed in combat (#" .. i .. ")") end
check(b._shown and d._shown and b._enabled and d._enabled, "a container went down in combat")
"""),
    ("cache: plain snapshot out of combat, one last read at the combat-start instant, frozen at lockdown, fresh at regen", "", r"""
boot()
local PA = FS.PlayerAuras
for _, event in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PLAYER_ENTERING_WORLD" }) do
    check(evframe()._events[event], event .. " not registered")
end
__auras.HELPFUL = { aura("Fortitude", { count = 1, duration = 1800, expires = __now + 1800 }), aura("Mark", { count = 3 }) }
__auras.HARMFUL = { aura("Curse of Agony", { dispel = "Curse", duration = 24 }) }
fire("UNIT_AURA")
local s = PA.Get()
check(#s.buffs == 2 and #s.debuffs == 1, "snapshot sizes " .. #s.buffs .. "/" .. #s.debuffs)
check(s.buffs[1].name == "Fortitude" and s.buffs[1].icon == "icon-Fortitude" and s.buffs[1].duration == 1800, "buff fields")
check(s.buffs[2].count == 3 and s.debuffs[1].dispelType == "Curse", "count / dispel")
check(PA.IsFrozen() == false, "frozen out of combat")
-- a buff lands in the instant before lockdown (readable): one more read, caught
__auras.HELPFUL[3] = aura("Inner Fire")
fire("PLAYER_REGEN_DISABLED")
check(#PA.Get().buffs == 3, "the combat-start read was missed")
-- lockdown: the list changes, the cache must not
__combat = true
__auras.HELPFUL[4] = aura("Power Word: Shield")
__auras.HARMFUL = {}
local reads0 = __readAttempts
fire("UNIT_AURA")
check(__readAttempts == reads0, "read attempted in lockdown")
check(PA.IsFrozen() == true, "not frozen in lockdown")
check(#PA.Get().buffs == 3 and #PA.Get().debuffs == 1, "the cache moved in lockdown")
__combat = false
fire("PLAYER_REGEN_ENABLED")
check(#PA.Get().buffs == 4 and #PA.Get().debuffs == 0, "no refresh at regen")
check(PA.IsFrozen() == false, "still frozen after regen")
"""),
    ("cache: a buff carries its plain sourceUnit (a party caster), a secret or missing one is nil", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("Arcane Intellect", { source = "party2" }), aura("Mark"), aura("Fortitude", { source = "player" }),
    { name = "Hidden", icon = "icon-Hidden", applications = 1, duration = 60, expirationTime = __now + 60, sourceUnit = __secret() } }
fire("UNIT_AURA")
local b = PA.Get().buffs
check(b[1].sourceUnit == "party2", "a party-cast buff lost its source: " .. tostring(b[1].sourceUnit))
check(b[2].sourceUnit == nil, "a buff with no source got one")
check(b[3].sourceUnit == "player", "your own buff's source")
check(b[4].sourceUnit == nil, "a secret source was stored")
"""),
    ("cache: secret fields never enter it, and a list that cannot be read keeps the last snapshot", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("Fortitude") }
fire("UNIT_AURA")
check(#PA.Get().buffs == 1, "baseline")
__auras.HELPFUL = { { name = __secret(), icon = __secret(), applications = __secret(), dispelName = __secret(),
    duration = __secret(), expirationTime = __secret() }, aura("Mark") }
fire("UNIT_AURA")
local b = PA.Get().buffs
check(#b == 2, "secret entry dropped the row")
check(b[1].name == nil and b[1].icon == nil and b[1].dispelType == nil, "secret strings stored")
check(b[1].count == 0 and b[1].duration == 0 and b[1].expirationTime == 0, "secret numbers stored")
check(b[2].name == "Mark", "plain entry after a secret one")
-- a throwing read keeps what was there
local keepBuffs, keepDebuffs = PA.Get().buffs, PA.Get().debuffs
C_UnitAuras.GetAuraDataByIndex = function() __readAttempts = __readAttempts + 1; error("boom: read") end
fire("UNIT_AURA")
check(PA.Get().buffs == keepBuffs and PA.Get().debuffs == keepDebuffs and #PA.Get().buffs == 2,
    "a failed read emptied or replaced the cache")
check(#__reports >= 1, "a failed read was not reported")
"""),
    ("AuraContainer template missing: the old row, drawn from the cache, logged once", "__template = false", r"""
boot()
check(#__acs == 0, "an AuraContainer was built without the template")
check(FS.buffsAuraContainer == nil and FS.PlayerAuras.IsEngineDrawn() == false, "engine exports with no template")
check(degraded("buffs_aura_container") == 1, "degrade logged " .. degraded("buffs_aura_container"))
__auras.HELPFUL = { aura("Fortitude"), aura("Mark") }
__auras.HARMFUL = { aura("Curse of Agony", { dispel = "Curse" }) }
fire("UNIT_AURA")
check(#visibleTiles(FS.buffsContainer) == 2 and #visibleTiles(FS.debuffsContainer) == 1, "fallback row not drawn")
check(colorEq(visibleTiles(FS.debuffsContainer)[1].fsBaseColor, { 0.639, 0.208, 0.933 }),
    "the fallback debuff tile does not wear the baked Curse colour")
-- in combat the row holds, nothing is read
local reads0 = __readAttempts
__combat = true
__auras.HELPFUL = {}
fire("UNIT_AURA")
check(__readAttempts == reads0, "fallback read in combat")
check(#visibleTiles(FS.buffsContainer) == 2, "fallback row changed in combat")
__combat = false
fire("PLAYER_REGEN_ENABLED")
check(#visibleTiles(FS.buffsContainer) == 0, "fallback row not refreshed at regen")
check(degraded("buffs_aura_container") == 1, "degrade logged again")
"""),
    ("AuraContainer creation throwing falls back the same way", "__acThrows = true", r"""
boot()
check(degraded("buffs_aura_container") == 1, "degrade logged " .. degraded("buffs_aura_container"))
check(FS.PlayerAuras.IsEngineDrawn() == false, "engine mode after a failed build")
__auras.HELPFUL = { aura("Fortitude") }
fire("UNIT_AURA")
check(#visibleTiles(FS.buffsContainer) == 1, "fallback row not drawn")
"""),
    ("a build that fails after the first container parks both frames and falls back", "__acGroupThrows = 'debuff_other'", r"""
boot()
check(#__acs == 2, "container count " .. #__acs)
for i, c in ipairs(__acs) do
    check(c._shown == false and c._enabled ~= true, "half built container " .. i .. " left live")
end
check(FS.buffsAuraContainer == nil and FS.debuffsAuraContainer == nil, "half built containers exported")
check(degraded("buffs_aura_container") == 1, "degrade logged " .. degraded("buffs_aura_container"))
__auras.HELPFUL = { aura("Fortitude") }
fire("UNIT_AURA")
check(#visibleTiles(FS.buffsContainer) == 1, "fallback row not drawn")
"""),
    ("Blizzard's own aura frames are dimmed, not hidden", "", r"""
boot()
local seen = {}
for _, f in ipairs(__dimmed) do seen[f] = true end
check(seen[BuffFrame] and seen[DebuffFrame], "BuffFrame/DebuffFrame not dimmed")
check(BuffFrame._calls.Hide == nil and DebuffFrame._calls.Hide == nil, "a Blizzard aura frame was hidden")
"""),
    ("holders are seated from FS.Layout", "", r"""
boot()
local ids = {}
for _, a in ipairs(FS.Layout.applied) do ids[a.id] = a.frame end
check(ids.buffs == FS.buffsContainer and ids.debuffs == FS.debuffsContainer, "holders not seated by Layout")
"""),
    ("FS.AurasReadable fails closed: lockdown AND the client's own answer must both allow the read", "", r"""
__setClient()
loadstring(__READABLE_SRC, "@Theme.lua(AurasReadable)")()
local function readable(combat, api)
    __combat = combat
    __noApi = (api == "absent")
    __apiSecret = nil
    if api == "absent" then C_Secrets = nil
    else
        C_Secrets = { ShouldAurasBeSecret = function()
            if api == "throws" then error("boom") end
            if api == "secret" then return __secret() end
            if api == "number" then return 1 end
            if api == "nil" then return nil end
            return api
        end }
    end
    return FS.AurasReadable()
end
check(readable(false, "absent") == true and readable(true, "absent") == false, "no API: lockdown decides")
check(readable(false, false) == true, "API false out of combat")
check(readable(true, false) == false, "API false in lockdown must still read as unreadable")
check(readable(false, true) == false, "API true out of combat must read as unreadable")
check(readable(true, true) == false, "API true in lockdown")
for _, bad in ipairs({ "throws", "secret", "number", "nil" }) do
    check(readable(false, bad) == false, bad .. " answer out of combat must fail closed")
    check(readable(true, bad) == false, bad .. " answer in lockdown must fail closed")
end
"""),
    ("after combat the snapshot is retried a few times while the client still says secret", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("A") }
-- lockdown ends but the client still answers "secret"
__apiSecret = true
local reads0 = __readAttempts
fire("PLAYER_REGEN_ENABLED")
check(__readAttempts == reads0, "a read while the client said secret")
check(#__timers == 1, "no retry scheduled: " .. #__timers)
check(#PA.Get().buffs == 0, "snapshot changed before it could be read")
__apiSecret = false
local t = table.remove(__timers, 1)
t[2]()
check(#PA.Get().buffs == 1, "the retry did not refresh the snapshot")
check(#__timers == 0, "the retry kept going after it read")
-- a client that never says readable: exactly the limit (3), then it stops
__apiSecret = true
fire("PLAYER_REGEN_ENABLED")
local runs = 0
while #__timers > 0 and runs < 20 do
    runs = runs + 1
    table.remove(__timers, 1)[2]()
end
check(runs == 3, "retries are not bounded to exactly 3: " .. runs)
-- a newer regen supersedes an older pending retry
__apiSecret = true
fire("PLAYER_REGEN_ENABLED")
local stale = table.remove(__timers, 1)
fire("PLAYER_REGEN_ENABLED")
__apiSecret = false
__auras.HELPFUL = { aura("A"), aura("B") }
stale[2]()
check(#PA.Get().buffs == 1, "a superseded retry still ran")
"""),
    ("combat re-entered during the retry chain: the attempts burn harmlessly, the next regen starts fresh", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("A") }
__apiSecret = true
fire("PLAYER_REGEN_ENABLED")
check(#__timers == 1, "no retry scheduled")
__combat = true
fire("PLAYER_REGEN_DISABLED")
local reads0 = __readAttempts
local runs = 0
while #__timers > 0 and runs < 20 do
    runs = runs + 1
    table.remove(__timers, 1)[2]()
end
check(runs == 3, "the chain did not burn its 3 attempts: " .. runs)
check(__readAttempts == reads0, "an attempt read auras in lockdown")
check(#PA.Get().buffs == 0, "the snapshot changed in lockdown")
-- the fight ends again, readable at once: no timers, refreshed
__combat = false
__apiSecret = false
fire("PLAYER_REGEN_ENABLED")
check(#__timers == 0 and #PA.Get().buffs == 1, "the next regen did not start fresh")
-- and an old chain still pending across a second fight does not fire in it
__apiSecret = true
fire("PLAYER_REGEN_ENABLED")
local pending = table.remove(__timers, 1)
__combat = true
fire("PLAYER_REGEN_DISABLED")
__combat = false
__apiSecret = false
__auras.HELPFUL = { aura("A"), aura("B") }
fire("PLAYER_REGEN_ENABLED")
check(#PA.Get().buffs == 2, "the second regen did not refresh")
__auras.HELPFUL = { aura("A"), aura("B"), aura("C") }
pending[2]()
check(#PA.Get().buffs == 2, "an old chain fired after a newer regen")
"""),
    ("a refresh that throws at regen does not cost the retry", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("A") }
__apiSecret = true
local realExists = UnitExists
UnitExists = function() error("boom") end
fire("PLAYER_REGEN_ENABLED")
check(#__timers == 1, "the retry was not scheduled after a throwing refresh: " .. #__timers)
UnitExists = realExists
__apiSecret = false
table.remove(__timers, 1)[2]()
check(#PA.Get().buffs == 1, "the retry did not refresh after the throwing regen")
"""),
    ("FS.OnAurasReadable: callbacks run once when reads become possible after combat, never when readable at regen", "", r"""
boot()
local a, b, c = 0, 0, 0
FS.OnAurasReadable(function() a = a + 1 end)
FS.OnAurasReadable(function() b = b + 1; error("boom") end)   -- a throwing callback must not block the rest
FS.OnAurasReadable(function() c = c + 1 end)
fire("PLAYER_REGEN_ENABLED")                                  -- readable at once: modules refresh themselves
check(#__timers == 0 and a == 0 and b == 0 and c == 0, "callbacks ran or a retry started although reads were possible")
__apiSecret = true
fire("PLAYER_REGEN_ENABLED")
check(#__timers == 1 and a == 0, "no retry chain")
table.remove(__timers, 1)[2]()                                -- still secret
check(a == 0 and #__timers == 1, "callbacks ran while still secret")
__apiSecret = false
table.remove(__timers, 1)[2]()
check(a == 1 and b == 1 and c == 1, "callbacks did not all run once: " .. a .. b .. c)
check(#__timers == 0, "the chain kept going after the callbacks ran")
"""),
    ("readable at regen: no retry is scheduled", "", r"""
boot()
fire("PLAYER_REGEN_ENABLED")
check(#__timers == 0, "a retry was scheduled although the snapshot refreshed: " .. #__timers)
"""),
    ("engine mode: UNIT_AURA in combat skips the scan even before lockdown, the combat-start read still happens", "", r"""
boot()
local PA = FS.PlayerAuras
__auras.HELPFUL = { aura("A") }
__affecting = true          -- in combat, lockdown not on yet
local reads0 = __readAttempts
fire("UNIT_AURA", "player")
check(__readAttempts == reads0, "UNIT_AURA scanned while in combat")
fire("PLAYER_REGEN_DISABLED")
check(#PA.Get().buffs == 1, "the combat-start read was skipped")
__affecting = false
__auras.HELPFUL = { aura("A"), aura("B") }
fire("UNIT_AURA", "player")
check(#PA.Get().buffs == 2, "out of combat UNIT_AURA no longer refreshes")
"""),
    ("fallback mode keeps scanning on UNIT_AURA at the combat-start instant (the row is the display)", "__template = false", r"""
boot()
__affecting = true
__auras.HELPFUL = { aura("A") }
fire("UNIT_AURA", "player")
check(#visibleTiles(FS.buffsContainer) == 1, "the fallback row skipped a readable update")
"""),
    ("an item enchantment failure keeps buffs and debuffs on the engine, and the polled enchants take over", "__enchantThrows = 0; __enchants.main = { 120000, 0 }", r"""
boot()
check(FS.PlayerAuras.IsEngineDrawn() == true and FS.buffsAuraContainer and FS.debuffsAuraContainer,
    "an enchant failure threw the engine path away")
check(FS.buffsAuraContainer._groups.buffs and #FS.debuffsAuraContainer._groupOrder == 5, "groups missing")
check(FS.buffsAuraContainer._shown and FS.buffsAuraContainer._enabled == true and FS.debuffsAuraContainer._shown,
    "a container is not live")
check(degraded("buffs_aura_container") == 0, "the whole-path fallback was logged for an enchant failure")
check(degraded("buffs_native_enchants") == 1, "enchant failure logged " .. degraded("buffs_native_enchants"))
check(#visibleTiles(FS.buffsContainer) == 1, "the polled enchant button did not take over")
check(tickframe() ~= nil, "no poll for the polled enchants")
"""),
    ("a layout failure for the enchantments is contained the same way", "__layoutThrows = true", r"""
boot()
check(FS.PlayerAuras.IsEngineDrawn() == true, "a layout failure threw the engine path away")
check(degraded("buffs_native_enchants") == 1, "enchant failure logged " .. degraded("buffs_native_enchants"))
"""),
    ("only the off hand failing keeps the main hand native and polls ONLY the off hand, beside it", "__enchantThrows = 1; __enchants.main = { 120000, 0 }; __enchants.off = { 60000, 0 }", r"""
boot()
check(FS.PlayerAuras.IsEngineDrawn() == true and FS.buffsAuraContainer._enchants[0], "the main hand is not native")
check(FS.buffsAuraContainer._enchants[1] == nil, "the failing off hand was recorded")
check(degraded("buffs_native_enchants") == 1, "partial failure not logged once")
local tiles = visibleTiles(FS.buffsContainer)
check(#tiles == 1, "expected exactly the off hand polled, got " .. #tiles)
check(tiles[1].enchantSlotId == 17, "the polled tile is not the off hand: " .. tostring(tiles[1].enchantSlotId))
check(tickframe() ~= nil, "the polled off hand has no poll")
local x1 = tiles[1]._points[#tiles[1]._points][4]
check(x1 == -36, "the off hand should sit one tile (32 + 4) left of the native main hand, x = " .. tostring(x1))
-- with no main hand enchant the off hand moves up into the first slot
__enchants.main = nil
__now = __now + 1
local tf = tickframe()
tf._scripts.OnUpdate(tf, 1)
local t2 = visibleTiles(FS.buffsContainer)
check(#t2 == 1 and t2[1].enchantSlotId == 17, "off hand not polled after the main hand lapsed")
local x0 = t2[1]._points[#t2[1]._points][4]
check(x0 == 0, "with no main hand enchant the off hand should take the first slot, x = " .. tostring(x0))
"""),
    ("only the main hand enchanted and the off hand failing: no polled duplicate", "__enchantThrows = 1; __enchants.main = { 120000, 0 }", r"""
boot()
check(#visibleTiles(FS.buffsContainer) == 0, "a polled enchant button duplicates the native main hand")
"""),
    ("the main hand failing leaves both enchants to the polled buttons", "__enchantThrows = 0; __enchants.main = { 120000, 0 }; __enchants.off = { 60000, 0 }", r"""
boot()
check(FS.buffsAuraContainer._enchants[0] == nil and FS.buffsAuraContainer._enchants[1] == nil, "an enchant was added")
check(#visibleTiles(FS.buffsContainer) == 2, "both enchants should be polled")
"""),
]


def run_case(name: str, setup: str, body: str, source: str, readable: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__SRC = source
    lua.globals().__READABLE_SRC = readable
    lua.globals().__DISPEL_SRC = theme_dispel_lua()
    try:
        if setup:
            lua.execute(setup)
        lua.execute(body)
    except LuaError as err:
        return str(err)
    return None


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    readable = theme_readiness_lua()
    failures = 0
    for name, setup, body in CASES:
        err = run_case(name, setup, body, source, readable)
        if err is None:
            print(f"ok   {name}")
        else:
            failures += 1
            print(f"FAIL {name}\n     {err}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
