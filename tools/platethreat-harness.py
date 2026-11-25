#!/usr/bin/env python3
"""The threat view on the nameplates (ticket C3): Modules/Nameplates/PlateThreat.lua.

Runs the real Nameplates.lua, Core/Role.lua and PlateThreat.lua together on the nameplates harness' mock client and pins:

  * the two providers (FS.Nameplates.SetColorProvider / SetTextProvider) are installed only for a role that needs one and
    only while its switch is on: tank (aggro colours, threat text), melee and ranged (aggro colours), healer (none);
  * tank colours: on me cyan, slipping amber (tanking, another player is above), not on me pink; DPS colours: on me pink,
    close amber (scaled threat at or over the Warn at value), safe cyan; a mob that is not on your threat list, a missing API
    or an unreadable (secret) answer keeps the plate's own colour; the colour tables are stable (the plate skips a fill it
    already wears);
  * the tank's threat text: Aggro % and Lead, plain values rounded, a secret value goes through a scratch font string and
    is never compared; nothing for the other roles;
  * alerts, each with an off switch: the tank's lost aggro (flash, sound), the healer's "a mob turns to me" (flash, sound),
    the DPS warn near the tank (flash); they fire on a change from a known state only, once per second at most per mob, and
    the settings of another role do nothing;
  * "Dim target out of melee / spell range": the target's health bar drops to the dim alpha when the target is out of
    range, a secret answer goes to SetAlphaFromBoolean, an unknown answer leaves the bar alone, the bar is restored when
    the switch goes off, the role changes, the target changes or the plate goes away;
  * a role or setting change applies at once (no reload, no threat event needed); a plate that goes away leaves nothing
    behind; the OnUpdate driver only runs while a flash or the range check needs it; a failing API read never reaches the
    plates; nothing compares a secret.

The mock is NOT the real client.

    python3 tools/platethreat-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
THREAT = ADDON / "Modules/Nameplates/PlateThreat.lua"
ROLE = ADDON / "Core/Role.lua"
NAMEPLATES = ADDON / "Modules/Nameplates/Nameplates.lua"
TOC = ADDON / "forever-stuwave.toc"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NP = load("nameplates_harness", "nameplates-harness.py")
PARSE_GATE = load("parse_gate", "parse-gate.py")

LOCALS_LIMIT = 150

# ---- the mock client: the nameplates harness' plus threat, range, sound and group reads ---------------------------------

PRE2 = r"""
local baseType = type
SECRETSTR = setmetatable({}, {
    __index = function() error("indexed a secret string", 2) end,
    __concat = function() error("joined a secret string", 2) end,
    __eq = function() error("compared a secret string", 2) end,
    __lt = function() error("compared a secret string", 2) end, __le = function() error("compared a secret string", 2) end,
    __len = function() error("measured a secret string", 2) end,
})
function type(v) if rawequal(v, SECRETSTR) then return "string" end return baseType(v) end

-- Threat reads. T[mob] = { tanking, status, scaled, raw, lead, secret = { field = true }, noDetailed = true }
T = {}
__threatThrows = false
local function tv(t, k) if t.secret and t.secret[k] then return SECRET end return t[k] end
function UnitDetailedThreatSituation(unit, mob)
    if __threatThrows then error("boom: UnitDetailedThreatSituation") end
    local t = T[mob]
    if not t or t.noDetailed then return nil end
    return tv(t, "tanking"), tv(t, "status"), tv(t, "scaled"), tv(t, "raw"), tv(t, "value")
end
function UnitThreatSituation(unit, mob)
    local t = T[mob]
    if not t or t.noPlain then return nil end
    return tv(t, "status")
end
function UnitThreatPercentageOfLead(unit, mob)
    local t = T[mob]
    if not t then return nil end
    return tv(t, "lead")
end

G = { role = "NONE" }
function UnitGroupRolesAssigned() return G.role end
CLASSTOKEN = "WARRIOR"
function UnitClass() return "Class", CLASSTOKEN end

-- Range reads: RANGE[spell name] = true | false | SECRET | nil, NEAR[index] = answer of CheckInteractDistance.
RANGE, NEAR, __rangeAsked = {}, {}, {}
__rangeThrows = false
C_Spell = { IsSpellInRange = function(spell, unit)
    __rangeAsked[#__rangeAsked + 1] = spell
    if __rangeThrows then error("boom: IsSpellInRange") end
    return RANGE[spell]
end }
function CheckInteractDistance(unit, i) return NEAR[i] end

__sounds = {}
SOUNDKIT = { RAID_WARNING = 8959, TELL_MESSAGE = 3081 }
function PlaySound(id) __sounds[#__sounds + 1] = id end

-- Font strings keep their text so a round trip through SetFormattedText / GetText can be told apart.
__formatted, __formatFails, __getTextNil = {}, false, false
local baseNew = __newFrame
function __newFrame(kind, name, parent)
    local f = baseNew(kind, name, parent)
    if kind == "FontString" then
        rawset(f, "SetFormattedText", function(self, fmt, ...)
            __formatted[#__formatted + 1] = { self, fmt, ... }
            if __formatFails then error("boom: SetFormattedText") end
            self._calls.SetFormattedText = (self._calls.SetFormattedText or 0) + 1
            local secret = false
            for i = 1, select("#", ...) do if rawequal((select(i, ...)), SECRET) then secret = true end end
            if secret then self._text = SECRETSTR else self._text = string.format(fmt, ...) end
        end)
        rawset(f, "GetText", function(self)
            if __getTextNil then return nil end
            return self._text
        end)
    end
    return f
end

__forwarded = {}

function emit(event, ...)
    local n = 0
    for _, f in ipairs(__frames) do
        if f._scripts.OnEvent and f._events[event] then
            n = n + 1
            local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
            check(ok, "handler threw on " .. event .. ": " .. tostring(err))
        end
    end
    check(n > 0, "nobody listens to " .. event)
end
function addPlate(unit) emit("NAME_PLATE_UNIT_ADDED", unit) end
function removePlate(unit) emit("NAME_PLATE_UNIT_REMOVED", unit) end

-- Loads the plates, the config, the role and the threat view the way the .toc does, then logs in.
function go(opts)
    opts = opts or {}
    boot()
    FS.IsSecret = function(v) return rawequal(v, SECRET) or rawequal(v, SECRETSTR) end
    FS.Config = mkConfig(opts.config)
    FS.Layout = { ForwardError = function(e) __forwarded[#__forwarded + 1] = tostring(e) end }
    FS.FrameHelpers.RegisterEvents = function(f, list) for _, e in ipairs(list) do f:RegisterEvent(e) end end
    CLASSTOKEN = opts.class or CLASSTOKEN
    if opts.noSounds then PlaySound, SOUNDKIT = nil, nil end
    if opts.noRangeApi then C_Spell = nil end
    assert(loadstring(__ROLE_SRC, "@Core/Role.lua"))("forever-stuwave", FS)
    if opts.before then opts.before() end
    assert(loadstring(__THREAT_SRC, "@Modules/Nameplates/PlateThreat.lua"))("forever-stuwave", FS)
    Role, PT, Plates = FS.Role, FS.PlateThreat, FS.Nameplates
    emit("PLAYER_LOGIN"); emit("PLAYER_ENTERING_WORLD"); drain()
    if opts.pick then check(Role.SetPick(opts.pick), "the pick " .. opts.pick .. " was refused") end
end

function rootOf(unit) return FS.framesByUnit[unit] end
function threat(unit) emit("UNIT_THREAT_SITUATION_UPDATE", unit) end
function setThreat(unit, t) T[unit] = t; threat(unit) end
function tick(dt, n)
    for _ = 1, (n or 1) do
        __now = __now + dt
        local f = PT.driver
        local fn = f and f._scripts.OnUpdate
        if fn then
            local ok, err = pcall(fn, f, dt)
            check(ok, "OnUpdate threw: " .. tostring(err))
        end
    end
end
function barAlpha(unit) local a = rootOf(unit).healthBar._args.SetAlpha return a and a[1] end
function textOf(unit) local t = rootOf(unit).threatText return t:IsShown() and t._args.SetText[1] or nil end
function fillOf(unit) return rootOf(unit).fillColor end
function target(unit) __target = unit; emit("PLAYER_TARGET_CHANGED") end
function noErrors() check(#__forwarded == 0, "an error was forwarded: " .. tostring(__forwarded[1])) end
"""

CASES: list[tuple[str, str]] = [
    ("the module loads, exports its palette and swatches, and registers no stray providers", r"""
go()
check(type(PT) == "table", "no FS.PlateThreat")
for _, k in ipairs({ "cyan", "amber", "pink" }) do
    local c = PT.PALETTE[k]
    check(type(c) == "table" and type(c[1]) == "number" and type(c[2]) == "number" and type(c[3]) == "number", "palette " .. k)
end
local function hex(c) return string.format("#%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5)) end
check(hex(PT.PALETTE.cyan) == "#22e0ff", "cyan is " .. hex(PT.PALETTE.cyan))
check(hex(PT.PALETTE.amber) == "#ffb648", "amber is " .. hex(PT.PALETTE.amber))
check(hex(PT.PALETTE.pink) == "#ff2e97", "pink is " .. hex(PT.PALETTE.pink))
local function words(rows) local out = {} for _, r in ipairs(rows) do out[#out + 1] = r[2] end return table.concat(out, ",") end
local function colours(rows) local out = {} for _, r in ipairs(rows) do out[#out + 1] = hex(r[1]) end return table.concat(out, ",") end
check(words(PT.SWATCHES.tank) == "on me,slipping,not on me", "tank swatch words " .. words(PT.SWATCHES.tank))
check(colours(PT.SWATCHES.tank) == "#22e0ff,#ffb648,#ff2e97", "tank swatch colours " .. colours(PT.SWATCHES.tank))
for _, role in ipairs({ "melee", "ranged" }) do
    check(words(PT.SWATCHES[role]) == "on me,close,safe", role .. " swatch words")
    check(colours(PT.SWATCHES[role]) == "#ff2e97,#ffb648,#22e0ff", role .. " swatch colours")
end
check(PT.SWATCHES.healer == nil, "the healer has no swatches")
check(PT.TUNING and PT.TUNING.DIM_ALPHA < 1 and PT.TUNING.DIM_ALPHA > 0, "a dim alpha")
noErrors()
"""),

    ("providers are installed only for a role that needs one and only while its switch is on", r"""
go({ pick = "healer" })
check(Plates.colorProvider == nil and Plates.textProvider == nil, "the healer got a provider")
Role.SetPick("tank")
check(Plates.colorProvider ~= nil, "the tank has no colour provider")
check(Plates.textProvider == nil, "threat text is Off by default, no text provider")
FS.Config.Set("tank.threat", "pct")
check(Plates.textProvider ~= nil, "Aggro % did not install the text provider")
FS.Config.Set("tank.threat", "lead")
check(Plates.textProvider ~= nil, "Lead did not install the text provider")
FS.Config.Set("tank.threat", "off")
check(Plates.textProvider == nil, "Off did not take the text provider away")
FS.Config.Set("tank.aggro", false)
check(Plates.colorProvider == nil, "Aggro colours off did not take the colour provider away")
FS.Config.Set("tank.aggro", true)
check(Plates.colorProvider ~= nil, "Aggro colours on did not bring it back")
Role.SetPick("melee")
check(Plates.colorProvider ~= nil and Plates.textProvider == nil, "melee: colours yes, text no")
FS.Config.Set("tank.threat", "pct")
check(Plates.textProvider == nil, "the tank's threat text reached the melee role")
FS.Config.Set("melee.aggro", false)
check(Plates.colorProvider == nil, "melee.aggro off")
Role.SetPick("ranged")
check(Plates.colorProvider ~= nil, "ranged has its own aggro switch")
Role.SetPick("healer")
check(Plates.colorProvider == nil and Plates.textProvider == nil, "back to the healer")
noErrors()
"""),

    ("the settings of the other roles do nothing", r"""
go({ pick = "tank" })
FS.Config.Set("melee.aggro", false); FS.Config.Set("ranged.aggro", false); FS.Config.Set("heal.aggro", false)
check(Plates.colorProvider ~= nil, "a switch of another role took the tank's colours away")
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "tank on me is cyan")
FS.Config.Set("melee.pct", 70)
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "the melee Warn at moved the tank")
noErrors()
"""),

    ("tank colours: on me cyan, slipping amber, not on me pink", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "status 3 should be cyan")
setThreat("nameplate1", { tanking = true, status = 2, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.amber, "status 2 should be amber")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 91 })
check(fillOf("nameplate1") == PT.PALETTE.pink, "status 1 should be pink")
setThreat("nameplate1", { tanking = false, status = 0, scaled = 40 })
check(fillOf("nameplate1") == PT.PALETTE.pink, "status 0 should be pink")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "and back to cyan")
noErrors()
"""),

    ("tank: a mob that is not on your threat list keeps the plate's own colour", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", nil)
check(fillOf("nameplate1") == FS.Theme.COLOR_HEALTH, "an untouched hostile mob keeps its reaction colour")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "engaged")
setThreat("nameplate1", nil)
check(fillOf("nameplate1") == FS.Theme.COLOR_HEALTH, "off the list again keeps the plate's own colour")
noErrors()
"""),

    ("tank: secret answers keep the plate's colour, plain pieces still count", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { tanking = true, status = true, scaled = true } })
check(fillOf("nameplate1") ~= PT.PALETTE.cyan and fillOf("nameplate1") ~= PT.PALETTE.amber and fillOf("nameplate1") ~= PT.PALETTE.pink,
    "a fully secret answer painted a threat colour")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { status = true, scaled = true } })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "a plain isTanking alone says on me")
setThreat("nameplate1", { tanking = false, status = 3, scaled = 100, secret = { status = true, scaled = true } })
check(fillOf("nameplate1") == PT.PALETTE.pink, "a plain isTanking false says not on me")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { tanking = true } })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "a plain status 3 says on me")
setThreat("nameplate1", { tanking = true, status = 2, scaled = 100, secret = { tanking = true } })
check(fillOf("nameplate1") == PT.PALETTE.amber, "a plain status 2 says slipping")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { tanking = true, status = true } })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "a plain scaled 100 alone says on me")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 60, secret = { tanking = true, status = true } })
check(fillOf("nameplate1") == PT.PALETTE.pink, "a plain scaled 60 alone says not on me")
noErrors()
"""),

    ("tank: the plain status read is used when the detailed read tells nothing", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { status = 3, noDetailed = true })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "UnitThreatSituation 3 should be cyan")
setThreat("nameplate1", { status = 0, noDetailed = true })
check(fillOf("nameplate1") == PT.PALETTE.pink, "UnitThreatSituation 0 should be pink")
noErrors()
"""),

    ("melee and ranged colours: on me pink, close amber at the Warn at value, safe cyan", r"""
for _, role in ipairs({ "melee", "ranged" }) do
    go({ pick = role })
    plate("nameplate1")
    setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
    check(fillOf("nameplate1") == PT.PALETTE.pink, role .. " on me is pink")
    setThreat("nameplate1", { tanking = false, status = 0, scaled = 50 })
    check(fillOf("nameplate1") == PT.PALETTE.cyan, role .. " at 50 is safe, cyan")
    setThreat("nameplate1", { tanking = false, status = 0, scaled = 89.9 })
    check(fillOf("nameplate1") == PT.PALETTE.cyan, role .. " at 89.9 is still safe")
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 90 })
    check(fillOf("nameplate1") == PT.PALETTE.amber, role .. " at 90 (the default) is close, amber")
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 99 })
    check(fillOf("nameplate1") == PT.PALETTE.amber, role .. " at 99 is close")
    FS.Config.Set(role .. ".pct", 100)
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 95 })
    check(fillOf("nameplate1") == PT.PALETTE.cyan, role .. " at 95 with Warn at 100 is safe")
    FS.Config.Set(role .. ".pct", 70)
    setThreat("nameplate1", { tanking = false, status = 0, scaled = 72 })
    check(fillOf("nameplate1") == PT.PALETTE.amber, role .. " at 72 with Warn at 70 is close")
    FS.Config.Set(role .. ".warn", false)
    check(fillOf("nameplate1") == PT.PALETTE.amber, role .. ": the Warn switch is the flash, the colours stay")
    FS.Config.Set(role .. ".aggro", false)
    check(Plates.colorProvider == nil, role .. " aggro colours off")
    noErrors()
end
"""),

    ("melee and ranged: the plain status stands in for an unreadable percent; all secret keeps the plate's colour", r"""
go({ pick = "melee" })
plate("nameplate1")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 99, secret = { scaled = true } })
check(fillOf("nameplate1") == PT.PALETTE.amber, "status 1 without a percent is close")
setThreat("nameplate1", { tanking = false, status = 0, scaled = 99, secret = { scaled = true } })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "status 0 without a percent is safe")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { scaled = true, status = true } })
check(fillOf("nameplate1") == PT.PALETTE.pink, "a plain isTanking alone says on me")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { tanking = true, status = true, scaled = true } })
check(fillOf("nameplate1") ~= PT.PALETTE.pink and fillOf("nameplate1") ~= PT.PALETTE.amber and fillOf("nameplate1") ~= PT.PALETTE.cyan,
    "everything secret kept a threat colour")
setThreat("nameplate1", nil)
check(fillOf("nameplate1") == FS.Theme.COLOR_HEALTH, "off the list keeps the plate's colour")
noErrors()
"""),

    ("colour tables are stable and a tap denied plate keeps its grey", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
local first = fillOf("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 98 })
check(fillOf("nameplate1") == first, "the same state gave another table")
check(Plates.ProvidedColor("nameplate1") == PT.PALETTE.cyan, "the provider answers the palette table")
plate("nameplate2", { name = "Tapped", level = 20, health = 100, max = 100, pct = 100, tapped = true })
T.nameplate2 = { tanking = true, status = 3, scaled = 100 }
threat("nameplate2")
check(fillOf("nameplate2") == Plates.PALETTE.tapped, "a tap denied mob must stay grey")
noErrors()
"""),

    ("a role change repaints the plates at once, no threat event needed", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(fillOf("nameplate1") == PT.PALETTE.cyan, "tank")
Role.SetPick("melee")
check(fillOf("nameplate1") == PT.PALETTE.pink, "melee on me is pink, at once")
Role.SetPick("healer")
check(fillOf("nameplate1") == Plates.PALETTE.aggro, "the healer gets the plate's own engagement colour back")
Role.SetPick("tank")
check(fillOf("nameplate1") == PT.PALETTE.cyan, "and the tank again")
noErrors()
"""),

    ("Auto follows the group role into and out of the providers", r"""
go()
check(Role.Current() == "melee", "setup: Warrior with no points is melee, got " .. tostring(Role.Current()))
G.role = "TANK"; emit("PLAYER_ROLES_ASSIGNED")
check(Role.Current() == "tank" and Plates.colorProvider ~= nil, "the group tank role")
G.role = "HEALER"; emit("PLAYER_ROLES_ASSIGNED")
check(Role.Current() == "healer" and Plates.colorProvider == nil, "the group healer role takes the colours away")
noErrors()
"""),

    ("tank threat text: Aggro % rounds a plain value, Lead adds a plus, Off hides it", r"""
go({ pick = "tank" })
plate("nameplate1")
FS.Config.Set("tank.threat", "pct")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 87.4, lead = 34.2 })
check(textOf("nameplate1") == "87%", "Aggro % shows " .. tostring(textOf("nameplate1")))
setThreat("nameplate1", { tanking = false, status = 1, scaled = 99.6, lead = 0 })
check(textOf("nameplate1") == "100%", "99.6 rounds to 100%, got " .. tostring(textOf("nameplate1")))
FS.Config.Set("tank.threat", "lead")
check(textOf("nameplate1") == "0%", "Lead of 0 shows " .. tostring(textOf("nameplate1")))
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, lead = 34.2 })
check(textOf("nameplate1") == "+34%", "Lead shows " .. tostring(textOf("nameplate1")))
FS.Config.Set("tank.threat", "off")
check(textOf("nameplate1") == nil, "Off hides the text")
noErrors()
"""),

    ("tank threat text: no text for a mob that is not on the list or an API that is missing", r"""
go({ pick = "tank" })
plate("nameplate1")
FS.Config.Set("tank.threat", "pct")
setThreat("nameplate1", nil)
check(textOf("nameplate1") == nil, "text for a mob that is not on the list")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(textOf("nameplate1") == "100%", "setup")
FS.Config.Set("tank.threat", "lead")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(textOf("nameplate1") == nil, "Lead with no lead value shows nothing")
UnitThreatPercentageOfLead = nil
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, lead = 20 })
check(textOf("nameplate1") == nil, "Lead without the API shows nothing")
noErrors()
"""),

    ("tank threat text: a secret value goes through a scratch font string, never compared", r"""
go({ pick = "tank" })
plate("nameplate1")
FS.Config.Set("tank.threat", "pct")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, secret = { scaled = true, tanking = true, status = true } })
local text = textOf("nameplate1")
check(rawequal(text, SECRETSTR), "the secret string did not reach SetText: " .. tostring(text))
local last = __formatted[#__formatted]
check(last and last[2] == "%d%%" and rawequal(last[3], SECRET), "the scratch font string was not given the secret through SetFormattedText")
FS.Config.Set("tank.threat", "lead")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100, lead = 20, secret = { lead = true } })
check(rawequal(textOf("nameplate1"), SECRETSTR), "a secret lead")
__getTextNil = true
threat("nameplate1")
check(textOf("nameplate1") == nil, "a scratch font string that gives nothing back must hide the text")
__getTextNil = false
__formatFails = true
threat("nameplate1")
check(textOf("nameplate1") == nil, "a failing SetFormattedText must hide the text")
noErrors()
"""),

    ("the lost aggro alert: flash and sound on a change from mine to not mine, each with its switch", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 80 })
check(not PT.Flashing("nameplate1"), "first sight, not mine: no alert")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(not PT.Flashing("nameplate1") and #__sounds == 0, "other to mine is not a loss")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
check(PT.Flashing("nameplate1"), "mine to not mine did not flash")
check(#__sounds == 1 and __sounds[1] == SOUNDKIT.RAID_WARNING, "no lost aggro sound")
local tex = rootOf("nameplate1").threatFlash
check(tex and tex:IsShown(), "no flash texture on the plate")
local c = tex._args.SetColorTexture
check(c and c[1] == PT.PALETTE.pink[1] and c[2] == PT.PALETTE.pink[2] and c[3] == PT.PALETTE.pink[3], "the flash is pink")
tick(0.3)
check(PT.Flashing("nameplate1") and tex:IsShown(), "the flash ended early")
tick(0.3, 4)
check(not PT.Flashing("nameplate1") and not tex:IsShown(), "the flash did not end")
check(PT.driver._scripts.OnUpdate == nil, "the driver kept running with nothing to do")
noErrors()
"""),

    ("the lost aggro alert: the one second pause, the sound switch and the alert switch", r"""
go({ pick = "tank" })
plate("nameplate1")
local function lose()
    setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
end
lose()
check(#__sounds == 1, "the first loss should chime")
tick(0.3, 2)
lose()
check(#__sounds == 1, "a second loss within a second chimed again")
tick(0.3, 2)
lose()
check(#__sounds == 2, "a loss after the pause did not chime")
tick(0.3, 5)
FS.Config.Set("tank.lost.snd", false)
lose()
check(PT.Flashing("nameplate1") and #__sounds == 2, "the Sound switch off must keep the flash and drop the sound")
tick(0.3, 5)
FS.Config.Set("tank.lost", false)
lose()
check(not PT.Flashing("nameplate1"), "Lost aggro off must not flash")
noErrors()
"""),

    ("the lost aggro alert: unreadable answers change nothing, the missing sound API is not an error", r"""
go({ pick = "tank", noSounds = true })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100, secret = { tanking = true, status = true, scaled = true } })
check(not PT.Flashing("nameplate1"), "a secret answer counted as a loss")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
check(PT.Flashing("nameplate1"), "the loss was forgotten after a secret answer")
noErrors()
"""),

    ("the healer's alert: a mob turns to me, flash and sound, first sight and the off switches", r"""
go({ pick = "healer" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(not PT.Flashing("nameplate1"), "first sight on me: no alert")
setThreat("nameplate1", { tanking = false, status = 0, scaled = 20 })
check(not PT.Flashing("nameplate1"), "mine to other is not the healer's alert")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(PT.Flashing("nameplate1"), "other to mine did not flash")
check(#__sounds == 1 and __sounds[1] == SOUNDKIT.TELL_MESSAGE, "no sound for the healer")
tick(0.3, 5)
FS.Config.Set("heal.aggro.snd", false)
setThreat("nameplate1", { tanking = false, status = 0, scaled = 20 })
tick(1.2)
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(PT.Flashing("nameplate1") and #__sounds == 1, "Sound off keeps the flash, drops the sound")
tick(0.3, 5)
FS.Config.Set("heal.aggro", false)
setThreat("nameplate1", { tanking = false, status = 0, scaled = 20 })
tick(1.2)
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
check(not PT.Flashing("nameplate1"), "A mob turns to me off")
noErrors()
"""),

    ("the DPS warn: a flash on the way from safe to close, no sound, its switch per role", r"""
for _, role in ipairs({ "melee", "ranged" }) do
    go({ pick = role })
    plate("nameplate1")
    setThreat("nameplate1", { tanking = false, status = 0, scaled = 50 })
    check(not PT.Flashing("nameplate1"), role .. ": safe is quiet")
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 92 })
    check(PT.Flashing("nameplate1"), role .. ": close did not flash")
    local c = rootOf("nameplate1").threatFlash._args.SetColorTexture
    check(c[1] == PT.PALETTE.amber[1] and c[2] == PT.PALETTE.amber[2], role .. ": the warning flash is amber")
    check(#__sounds == 0, role .. ": the warning has no sound")
    tick(0.3, 5)
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 95 })
    tick(1.2)
    check(not PT.Flashing("nameplate1"), role .. ": still close is not a new warning")
    setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
    check(not PT.Flashing("nameplate1"), role .. ": pulling it is the colour, not a warning")
    FS.Config.Set(role .. ".warn", false)
    setThreat("nameplate1", { tanking = false, status = 0, scaled = 50 })
    tick(1.2)
    setThreat("nameplate1", { tanking = false, status = 1, scaled = 92 })
    check(not PT.Flashing("nameplate1"), role .. ": Warn near the tank off")
    noErrors()
end
go({ pick = "ranged", config = { ["melee.warn"] = false } })
plate("nameplate1")
setThreat("nameplate1", { tanking = false, status = 0, scaled = 50 })
setThreat("nameplate1", { tanking = false, status = 1, scaled = 92 })
check(PT.Flashing("nameplate1"), "the melee switch muted the ranged warning")
noErrors()
"""),

    ("an alert never fires for a role that has none, or after a role change", r"""
go({ pick = "melee" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
check(not PT.Flashing("nameplate1"), "the lost aggro alert fired for a melee player")
Role.SetPick("tank")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
Role.SetPick("healer")
setThreat("nameplate1", { tanking = false, status = 0, scaled = 20 })
check(not PT.Flashing("nameplate1"), "the tank's state leaked into the healer")
noErrors()
"""),

    ("a plate that goes away takes its flash and its memory with it", r"""
go({ pick = "tank" })
local root = plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
check(PT.Flashing("nameplate1"), "setup: flashing")
local tex = root.threatFlash
removePlate("nameplate1")
tick(0.1)
check(not PT.Flashing("nameplate1"), "a removed plate still flashes")
check(not tex:IsShown(), "the flash texture stayed shown on the pooled plate")
check(PT.driver._scripts.OnUpdate == nil, "the driver stayed on")
local again = plate("nameplate2")
setThreat("nameplate2", { tanking = false, status = 1, scaled = 100 })
check(not PT.Flashing("nameplate2"), "memory of the old plate made a loss")
noErrors()
"""),

    ("combat ending forgets what the mobs were doing", r"""
go({ pick = "tank" })
plate("nameplate1")
setThreat("nameplate1", { tanking = true, status = 3, scaled = 100 })
emit("PLAYER_REGEN_ENABLED")
setThreat("nameplate1", { tanking = false, status = 1, scaled = 100 })
check(not PT.Flashing("nameplate1"), "a state from the last fight made a loss")
noErrors()
"""),

    ("melee range: the target's bar dims out of range and comes back", r"""
go({ pick = "melee", class = "WARRIOR" })
plate("nameplate1"); plate("nameplate2")
target("nameplate1")
check(PT.driver._scripts.OnUpdate ~= nil, "the driver is not running for the range check")
RANGE["Heroic Strike"] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "out of melee range should dim, alpha " .. tostring(barAlpha("nameplate1")))
check(barAlpha("nameplate2") == nil, "a plate that is not the target was touched")
RANGE["Heroic Strike"] = true
NEAR[3] = true
tick(0.3)
check(barAlpha("nameplate1") == 1, "back in range should restore the bar, alpha " .. tostring(barAlpha("nameplate1")))
RANGE["Heroic Strike"] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "dimmed again")
target("nameplate2")
check(barAlpha("nameplate1") == 1, "the old target's bar was not restored")
tick(0.3)
check(barAlpha("nameplate2") == PT.TUNING.DIM_ALPHA, "the new target is out of range too")
__target = nil
emit("PLAYER_TARGET_CHANGED")
check(barAlpha("nameplate2") == 1, "no target: the bar is restored")
noErrors()
"""),

    ("melee range: the spell says in range, the duel distance says no (a spell that answers true at any distance)", r"""
go({ pick = "melee", class = "WARRIOR" })
plate("nameplate1")
target("nameplate1")
RANGE["Heroic Strike"] = true
NEAR[3] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "the duel distance did not overrule the spell")
NEAR[3] = nil
tick(0.3)
check(barAlpha("nameplate1") == 1, "an unknown duel distance with an in range spell is in range")
noErrors()
"""),

    ("melee range: no usable spell falls back to the duel distance; unknown leaves the bar alone", r"""
go({ pick = "melee", class = "SHAMAN" })
plate("nameplate1")
target("nameplate1")
NEAR[3] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "the duel distance fallback did not dim")
NEAR[3] = true
tick(0.3)
check(barAlpha("nameplate1") == 1, "the duel distance fallback did not restore")
NEAR[3] = nil
tick(0.3)
check(barAlpha("nameplate1") == 1, "no answer at all must leave the bar alone")
__rangeThrows = true
tick(0.3)
check(barAlpha("nameplate1") == 1, "a throwing range API must leave the bar alone")
noErrors()
"""),

    ("range: a secret answer goes to SetAlphaFromBoolean and is never compared", r"""
go({ pick = "melee", class = "WARRIOR" })
plate("nameplate1")
target("nameplate1")
RANGE["Heroic Strike"] = SECRET
NEAR[3] = false
tick(0.3)
local a = rootOf("nameplate1").healthBar._args.SetAlphaFromBoolean
check(a and rawequal(a[1], SECRET) and a[2] == 1 and a[3] == PT.TUNING.DIM_ALPHA, "SetAlphaFromBoolean was not given the secret and the two alphas")
Role.SetPick("healer")
check(barAlpha("nameplate1") == 1, "the healer role did not restore the bar")
noErrors()
"""),

    ("ranged range: the class's spell list, its own switch, nothing without the API", r"""
go({ pick = "ranged", class = "MAGE" })
plate("nameplate1")
target("nameplate1")
RANGE["Fireball"] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "out of spell range should dim")
RANGE["Fireball"] = true
tick(0.3)
check(barAlpha("nameplate1") == 1, "in spell range should restore")
RANGE["Fireball"] = false
tick(0.3)
FS.Config.Set("ranged.range", false)
check(barAlpha("nameplate1") == 1, "the switch off must restore the bar at once")
tick(0.3, 3)
check(barAlpha("nameplate1") == 1, "and keep it restored")
check(PT.driver._scripts.OnUpdate == nil, "the driver kept running with the range switch off")
FS.Config.Set("ranged.range", true)
FS.Config.Set("melee.range", false)
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "the melee switch reached the ranged role")
noErrors()
"""),

    ("ranged range: no spell API, no friendly targets", r"""
go({ pick = "ranged", class = "MAGE", noRangeApi = true })
plate("nameplate1")
target("nameplate1")
tick(0.3, 3)
check(barAlpha("nameplate1") == nil or barAlpha("nameplate1") == 1, "no API: the bar must be left alone")
noErrors()
"""),

    ("ranged range: a friendly target is never dimmed", r"""
go({ pick = "ranged", class = "MAGE" })
plate("nameplate1", { name = "Friend", level = 20, health = 100, max = 100, pct = 100, hostile = false, friend = true })
target("nameplate1")
RANGE["Fireball"] = false
tick(0.3, 3)
check(barAlpha("nameplate1") == nil or barAlpha("nameplate1") == 1, "a friendly target was dimmed")
noErrors()
"""),

    ("range: the role change, the removal and the driver", r"""
go({ pick = "melee", class = "WARRIOR" })
local root = plate("nameplate1")
target("nameplate1")
RANGE["Heroic Strike"] = false
tick(0.3)
check(barAlpha("nameplate1") == PT.TUNING.DIM_ALPHA, "setup: dimmed")
removePlate("nameplate1")
check(root.healthBar._args.SetAlpha[1] == 1, "a removed plate kept its dim on the pooled root")
Role.SetPick("healer")
check(PT.driver._scripts.OnUpdate == nil, "the driver stayed on for a healer")
Role.SetPick("tank")
check(PT.driver._scripts.OnUpdate == nil, "the driver stayed on for a tank")
Role.SetPick("melee")
check(PT.driver._scripts.OnUpdate ~= nil, "the driver did not start for melee")
noErrors()
"""),

    ("a throwing or odd threat read never reaches the plates", r"""
go({ pick = "tank" })
plate("nameplate1")
FS.Config.Set("tank.threat", "pct")
__threatThrows = true
threat("nameplate1")
check(fillOf("nameplate1") ~= PT.PALETTE.cyan, "a throwing read painted a colour")
check(degraded("plate_color_provider") == 0 and degraded("plate_text_provider") == 0, "the provider itself threw instead of answering nil")
__threatThrows = false
T.nameplate1 = { tanking = "yes", status = "high", scaled = {}, lead = "x", noPlain = true }
threat("nameplate1")
check(textOf("nameplate1") == nil, "odd values made text")
T.nameplate1 = { tanking = true, status = 3, scaled = 0 / 0, lead = 1 / 0 }
threat("nameplate1")
noErrors()
"""),

    ("the events: the threat frame listens for what the alerts and the range check need", r"""
go({ pick = "tank" })
check(PT.frame and PT.frame._scripts.OnEvent, "the threat view has no event frame")
for _, e in ipairs({ "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "UNIT_THREAT_SITUATION_UPDATE", "UNIT_THREAT_LIST_UPDATE",
    "NAME_PLATE_UNIT_REMOVED", "PLAYER_REGEN_ENABLED", "PLAYER_TARGET_CHANGED" }) do
    check(PT.frame._events[e], "the threat frame does not listen to " .. e)
end
noErrors()
"""),

    ("Nameplates without the threat module has no providers", r"""
boot()
FS.IsSecret = function(v) return rawequal(v, SECRET) end
FS.Config = mkConfig()
fire("PLAYER_ENTERING_WORLD"); drain()
check(FS.PlateThreat == nil, "setup")
plate("nameplate1")
check(FS.Nameplates.colorProvider == nil and FS.Nameplates.textProvider == nil, "providers without the threat module")
"""),
]


# ---- python level checks -------------------------------------------------------------------------------------------

DASHES = (chr(0x2014), chr(0x2013))


def run_case(name: str, body: str, np_source: str, role_source: str, threat_source: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(NP.AURAS.MOCK)
    lua.globals().__SRC = np_source
    lua.globals().__ROLE_SRC = role_source
    lua.globals().__THREAT_SRC = threat_source
    lua.execute("__template = true")
    lua.globals().GOLDEN = ""
    lua.execute(f"NUMBERS = {NP.NUMBER_ROWS}; BOOLS = {NP.BOOL_ROWS}; CHOICES = {NP.CHOICE_ROWS}")
    try:
        lua.execute(NP.PRE)
        lua.execute(PRE2)
        lua.execute(body)
    except LuaError as err:
        return " ".join(str(err).splitlines()[:4])[:900]
    return None


def check_no_dashes() -> list[str]:
    problems = []
    for path in (THREAT, Path(__file__)):
        text = path.read_text(encoding="utf-8")
        for mark in DASHES:
            if mark in text:
                problems.append(f"{path.name} has a dash character ({mark!r})")
    return problems


def check_toc_order() -> list[str]:
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("##")]
    want = "Modules/Nameplates/PlateThreat.lua"
    if want not in toc:
        return [f"{want} is not in the .toc"]
    problems = []
    for before in ("Core/Role.lua", "Modules/Nameplates/Nameplates.lua"):
        if toc.index(want) < toc.index(before):
            problems.append(f"{want} must load after {before}")
    return problems


def check_file_scope_locals() -> list[str]:
    count = PARSE_GATE.count_file_scope_locals(THREAT.read_text(encoding="utf-8"))
    print(f"      PlateThreat.lua file scope locals: {count} (limit {LOCALS_LIMIT} here, the parse gate fails at 200)")
    if count >= LOCALS_LIMIT:
        return [f"{count} file scope locals"]
    return []


def main() -> int:
    np_source = NAMEPLATES.read_text(encoding="utf-8")
    role_source = ROLE.read_text(encoding="utf-8")
    threat_source = THREAT.read_text(encoding="utf-8")
    failures = 0
    total = 0
    for name, body in CASES:
        total += 1
        error = run_case(name, body, np_source, role_source, threat_source)
        if error is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      {error}")
    for label, problems in (
        ("platethreat_loads_after_role_and_nameplates", check_toc_order()),
        ("no_dash_characters_in_platethreat", check_no_dashes()),
        ("platethreat_file_scope_locals", check_file_scope_locals()),
    ):
        total += 1
        if problems:
            failures += 1
            print(f"FAIL  {label}\n      " + "\n      ".join(problems))
        else:
            print(f"ok    {label}")
    print(f"{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
