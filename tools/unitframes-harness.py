#!/usr/bin/env python3
"""Runs the real UnitFrames.lua and Config.lua headless to pin the hide player / hide target settings.

UnitFrames.lua builds FS.player and FS.target as secure buttons at file load. The settings
unitFrames.hidePlayer and unitFrames.hideTarget (both default false) hide a frame the taint-safe
way: alpha 0 plus EnableMouse(false), never Hide/Show, never UnregisterUnitWatch. These checks pin that:

  * both frames start shown (alpha 1, mouse on) and the defaults are registered as false;
  * hiding sets alpha 0 and mouse off on that frame only, showing restores both;
  * the frames stay built (FS.player, FS.target, .visual) and the target keeps its unit watch;
  * no Hide, Show or UnregisterUnitWatch call is made after load;
  * a change in combat touches nothing until PLAYER_REGEN_ENABLED, then the latest value wins;
  * a profile switch, a profile reset and a login that resolves the character apply the setting;
  * a load in combat (frames not built yet) survives and applies once the frames exist;
  * /fsframes prints the state and sets either frame;
  * a target aura button (mouse live, a child of the target's visual) shows no tooltip while the
    target is hidden and shows it again when the target is shown.

UnitFrames.lua, TargetAuras.lua and Config.lua are the real files; the frames are a recording mock and
Theme / FrameHelpers are stubs. This is NOT the real client.

    python3 tools/unitframes-harness.py

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

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
# UNITFRAMES_LUA points the harness at a mutant copy (a check must fail on a broken one).
UNITFRAMES_FILE = Path(os.environ.get("UNITFRAMES_LUA", ADDON / "Modules/UnitFrames/UnitFrames.lua"))
CONFIG_FILE = ADDON / "Core/Config.lua"
TARGETAURAS_FILE = ADDON / "Modules/Auras/TargetAuras.lua"

MOCK = r"""
__combat = false
__frames = {}
__log = {}          -- every Hide / Show / UnregisterUnitWatch after __log is reset
__printed = {}
__watched = {}

local Frame = {}
local FrameMT = {}
FrameMT.__index = function(self, k)
    local m = Frame[k]
    if m then return m end
    return function() end   -- any widget method the checks do not care about
end

function newFrame(kind, name, parent, template)
    local f = setmetatable({ _kind = kind, _name = name, _parent = parent, _events = {}, _scripts = {}, _attrs = {},
        _alpha = 1, _mouse = true, _h = 0, _calls = 0,
        _protected = type(template) == "string" and template:find("Secure", 1, true) ~= nil }, FrameMT)
    __frames[#__frames + 1] = f
    return f
end
function CreateFrame(kind, name, parent, template) return newFrame(kind, name, parent, template) end
function Frame.CreateTexture(self) return newFrame("Texture", nil, self) end
function Frame.CreateFontString(self) return newFrame("FontString", nil, self) end
function Frame.GetParent(self) return self._parent end
function Frame.GetStatusBarTexture(self) return newFrame("Texture", nil, self) end
function Frame.GetFrameLevel() return 1 end
function Frame.SetHeight(self, h) self._h = h end
function Frame.GetHeight(self) return self._h end
function Frame.SetSize(self, w, h) self._w, self._h = w, h end
function Frame.SetScript(self, k, fn) self._scripts[k] = fn end
function Frame.RegisterEvent(self, e) self._events[e] = true end
function Frame.UnregisterEvent(self, e) self._events[e] = nil end
function Frame.SetAttribute(self, k, v) self._attrs[k] = v end
function Frame.GetName(self) return self._name end
function Frame.IsProtected(self) return self._protected end

-- The state the setting drives. A call on a protected frame in combat is recorded as blocked.
__blocked = 0
local function guard(self)
    if __combat and self._protected then __blocked = __blocked + 1 end
    self._calls = self._calls + 1
end
function Frame.SetAlpha(self, a) guard(self); self._alpha = a end
function Frame.GetAlpha(self) return self._alpha end
function Frame.EnableMouse(self, on) guard(self); self._mouse = on end
function Frame.IsMouseEnabled(self) return self._mouse end
function Frame.Hide(self) __log[#__log + 1] = "Hide:" .. tostring(self._name) end
function Frame.Show(self) __log[#__log + 1] = "Show:" .. tostring(self._name) end
function Frame.SetShown(self, v) __log[#__log + 1] = "SetShown:" .. tostring(self._name) end

function RegisterUnitWatch(f) __watched[f] = true end
function UnregisterUnitWatch(f) __watched[f] = nil; __log[#__log + 1] = "UnregisterUnitWatch:" .. tostring(f._name) end

function InCombatLockdown() return __combat end
__exists = {}
function UnitExists(unit) return __exists[unit] == true end
__tooltips = 0
-- Records what the tooltip was asked to show (the real-tooltip checks read _spell / _text / _lines).
GameTooltip = {
    SetOwner = function(self, o) self._owner, self._spell, self._text, self._lines = o, nil, nil, {} end,
    GetOwner = function(self) return self._owner end,
    Hide = function() end,
    Show = function() end,
    SetText = function(self, t) self._text = t end,
    AddLine = function(self, t) self._lines[#self._lines + 1] = t end,
    SetSpellByID = function(self, id) self._spell = id end,
}
__SECRET = {}
function UnitGUID() return __guid end
function UnitName() return "Bob" end
function GetRealmName() return "Realm" end
function print(...) __printed[#__printed + 1] = table.concat({ ... }, " ") end
SlashCmdList = {}
function geterrorhandler() return function(err) __errors[#__errors + 1] = tostring(err) end end
__errors = {}

function Fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end

UIParent = newFrame("Frame", "UIParent")
__guid = "Player-1-AAAA"
"""

SESSION = r"""
function(unitFramesSrc, configSrc, targetAurasSrc, opts)
    opts = opts or {}
    __frames, __log, __printed, __errors, __watched, __blocked = {}, {}, {}, {}, {}, 0
    __frames[1] = UIParent
    __combat = opts.combatAtLoad == true
    __exists, __tooltips = opts.exists or {}, 0
    ForeverSTUwaveDB = opts.db
    FS = {}
    FS.IsSecret = function(v) return v ~= nil and rawequal(v, __SECRET) end
    __unreadable, __aura = false, opts.aura or { name = "Rend", icon = "i" }
    FS.LogDegradeOnce = function() end
    FS.GetFullUnitName = function() return "Bob" end
    FS.Layout = {
        Apply = function() end, UseStore = function() end, ReseatAll = function() end,
        ForwardError = function(err) __errors[#__errors + 1] = tostring(err) end,
        boss = {}, focus = {},
    }
    local function any() return newFrame("Frame") end
    local Theme = {}
    for _, name in ipairs({ "ApplyFontGeneric", "ApplyMono", "AddOuterGlow", "AddRoundedFill", "AddGradientBorder" }) do
        Theme[name] = function() end
    end
    local bar = { 1, 1, 1, 1 }
    for _, name in ipairs({ "COLOR_TEXT_WHITE", "COLOR_BG", "COLOR_BORDER", "COLOR_BAR_BORDER", "COLOR_HEALTH",
        "COLOR_POWER", "COLOR_HEAL", "COLOR_CARET_HEALTH", "COLOR_CARET_POWER" }) do
        Theme[name] = bar
    end
    Theme.PANEL_RADIUS = 4
    Theme.FONT_ORBITRON, Theme.FLAT_TEXTURE, Theme.HATCH_TEXTURE = "f", "flat", "hatch"
    Theme.SkinButton = function() end
    FS.Theme = Theme
    FS.AurasReadable = function() return not __unreadable end
    FS.OnAurasReadable = function() end
    FS.FrameHelpers = {
        DimBlizzardFrame = function() end,
        NewStepRunner = function() return function() end, function() end end,
        SetAuraLabel = function() end,
        SeatAuraTile = function() end,
        SafeRegisterUnitEvent = function() end,
        ReadAuraSlot = function(unit, slot, filter)
            if slot == 1 and filter == "HARMFUL" then
                return { name = __aura.name, icon = __aura.icon, spellId = __aura.spellId }
            end
        end,
        ShowAuraTooltip = function() __tooltips = __tooltips + 1 end,
        SetTipSpell = function(frame, id, name) frame.fsSpellID, frame.fsName = id, name end,
        UpdateCaretFull = function() end,
        CreateCaret = any,
        CreateLevelChip = function(parent) local chip = newFrame("Frame", nil, parent); chip.text = any(); return chip end,
        CreatePillBar = function(parent)
            local pill = newFrame("StatusBar", nil, parent)
            pill.shell, pill.text = any(), any()
            return pill
        end,
    }
    if opts.realTips then
        -- The real tooltip helpers, so a hover is judged by what the tooltip is asked to show.
        local real = { IsSecret = FS.IsSecret, AurasReadable = FS.AurasReadable, Theme = {} }
        assert(load(__helpersSrc, "@FrameHelpers.lua"))("forever-stuwave", real)
        FS.FrameHelpers.ShowAuraTooltip = real.FrameHelpers.ShowAuraTooltip
        FS.FrameHelpers.SetTipSpell = real.FrameHelpers.SetTipSpell
    end
    assert(load(configSrc, "@Config.lua"))("forever-stuwave", FS)
    assert(load(unitFramesSrc, "@UnitFrames.lua"))("forever-stuwave", FS)
    assert(load(targetAurasSrc, "@TargetAuras.lua"))("forever-stuwave", FS)
    __log = {}     -- only calls made after the frames are built count
    __blocked = 0
    for _, f in ipairs(__frames) do f._calls = 0 end
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local function boot(opts)
    __session(__unitFramesSrc, __configSrc, __targetAurasSrc, opts)
    Fire("ADDON_LOADED", "forever-stuwave")
    Fire("PLAYER_LOGIN")
    return FS.Config
end
local function shown(f) return f._alpha == 1 and f._mouse == true end
local function hidden(f) return f._alpha == 0 and f._mouse == false end
local function endCombat() __combat = false; Fire("PLAYER_REGEN_ENABLED") end
local function slash(msg) SlashCmdList.FSFRAMES(msg) end
local function lastPrinted() return __printed[#__printed] or "" end

function T.defaults_are_false_and_both_frames_start_shown()
    local C = boot()
    eq(C.Get("unitFrames.hidePlayer"), false)
    eq(C.Get("unitFrames.hideTarget"), false)
    eq(shown(FS.player), true, "player shown")
    eq(shown(FS.target), true, "target shown")
end

function T.hiding_the_player_sets_alpha_zero_and_mouse_off_on_that_frame_only()
    local C = boot()
    eq(C.Set("unitFrames.hidePlayer", true), true)
    eq(hidden(FS.player), true, "player hidden")
    eq(shown(FS.target), true, "target untouched")
end

function T.hiding_the_target_sets_alpha_zero_and_mouse_off_on_that_frame_only()
    local C = boot()
    C.Set("unitFrames.hideTarget", true)
    eq(hidden(FS.target), true, "target hidden")
    eq(shown(FS.player), true, "player untouched")
end

function T.showing_again_restores_alpha_and_mouse()
    local C = boot()
    C.Set("unitFrames.hidePlayer", true)
    C.Set("unitFrames.hideTarget", true)
    C.Set("unitFrames.hidePlayer", false)
    C.Set("unitFrames.hideTarget", false)
    eq(shown(FS.player), true)
    eq(shown(FS.target), true)
end

function T.the_frames_stay_built_and_the_target_keeps_its_unit_watch()
    local C = boot()
    C.Set("unitFrames.hidePlayer", true)
    C.Set("unitFrames.hideTarget", true)
    eq(FS.player ~= nil and FS.player.visual ~= nil, true, "FS.player and its visual remain")
    eq(FS.target ~= nil and FS.target.visual ~= nil, true, "FS.target and its visual remain")
    eq(__watched[FS.target], true, "unit watch still registered")
end

function T.hiding_and_showing_never_calls_hide_show_or_unregister_unit_watch()
    local C = boot()
    C.Set("unitFrames.hidePlayer", true)
    C.Set("unitFrames.hideTarget", true)
    C.Set("unitFrames.hidePlayer", false)
    C.Set("unitFrames.hideTarget", false)
    slash("target off")
    slash("target on")
    eq(#__log, 0, "unexpected calls: " .. table.concat(__log, ","))
end

function T.a_change_in_combat_touches_nothing_until_combat_ends()
    local C = boot()
    FS.player._calls, FS.target._calls = 0, 0
    __combat = true
    C.Set("unitFrames.hidePlayer", true)
    C.Set("unitFrames.hideTarget", true)
    eq(shown(FS.player), true, "player unchanged in combat")
    eq(shown(FS.target), true, "target unchanged in combat")
    eq(FS.player._calls + FS.target._calls, 0, "no call reached either frame in combat")
    eq(__blocked, 0, "nothing restricted was attempted")
    endCombat()
    eq(hidden(FS.player), true, "player hidden after combat")
    eq(hidden(FS.target), true, "target hidden after combat")
    eq(__blocked, 0)
end

function T.the_latest_value_wins_when_a_setting_flips_twice_in_combat()
    local C = boot()
    __combat = true
    C.Set("unitFrames.hidePlayer", true)
    C.Set("unitFrames.hidePlayer", false)
    endCombat()
    eq(shown(FS.player), true)
    C.Set("unitFrames.hidePlayer", true)
    eq(hidden(FS.player), true)
end

function T.regen_after_a_applied_change_does_not_touch_the_frames_again()
    local C = boot()
    __combat = true
    C.Set("unitFrames.hidePlayer", true)
    endCombat()
    local calls = FS.player._calls
    __combat = true
    endCombat()
    eq(FS.player._calls, calls, "no pending apply remains")
end

function T.a_profile_switch_applies_the_other_profiles_setting()
    local C = boot()
    eq(C.NewProfile("Quiet"), true)
    local db = ForeverSTUwaveDB
    db.profiles.Quiet.settings["unitFrames.hidePlayer"] = true
    db.profiles.Quiet.settings["unitFrames.hideTarget"] = true
    eq(C.SetActiveProfile("Quiet"), true)
    eq(hidden(FS.player), true, "player hidden by the profile")
    eq(hidden(FS.target), true, "target hidden by the profile")
    eq(C.SetActiveProfile("Default"), true)
    eq(shown(FS.player), true, "player shown by Default")
    eq(shown(FS.target), true, "target shown by Default")
end

function T.a_profile_reset_applies_the_defaults()
    local C = boot()
    C.Set("unitFrames.hidePlayer", true)
    eq(hidden(FS.player), true)
    eq(C.ResetProfile(), true)
    eq(shown(FS.player), true)
end

function T.a_profile_switch_in_combat_defers_to_regen()
    local C = boot()
    C.NewProfile("Quiet")
    ForeverSTUwaveDB.profiles.Quiet.settings["unitFrames.hideTarget"] = true
    __combat = true
    eq(C.SetActiveProfile("Quiet"), true)
    eq(shown(FS.target), true, "unchanged in combat")
    endCombat()
    eq(hidden(FS.target), true)
end

function T.a_saved_hidden_setting_applies_at_login()
    local db = { profilesVersion = 1, profileKeys = { ["Player-1-AAAA"] = "Default" }, profileLabels = {},
        profiles = { Default = { settings = { ["unitFrames.hidePlayer"] = true }, layout = { v = 1, frames = {} } } } }
    boot({ db = db })
    eq(hidden(FS.player), true, "player hidden from the saved profile")
    eq(shown(FS.target), true)
end

function T.a_load_in_combat_builds_nothing_yet_and_applies_once_the_frames_exist()
    __session(__unitFramesSrc, __configSrc, __targetAurasSrc, { combatAtLoad = true })
    Fire("ADDON_LOADED", "forever-stuwave")
    Fire("PLAYER_LOGIN")
    eq(FS.player, nil, "frames are not built in combat")
    FS.Config.Set("unitFrames.hideTarget", true)
    eq(#__errors, 0, "no error with the frames missing: " .. tostring(__errors[1]))
    endCombat()
    eq(FS.target ~= nil, true, "frames built after combat")
    eq(hidden(FS.target), true)
    eq(shown(FS.player), true)
end

function T.slash_with_no_argument_prints_the_state()
    local C = boot()
    C.Set("unitFrames.hideTarget", true)
    slash("")
    local line = lastPrinted()
    eq(line:find("player", 1, true) ~= nil and line:find("target", 1, true) ~= nil, true, line)
    eq(line:find("shown", 1, true) ~= nil and line:find("hidden", 1, true) ~= nil, true, line)
end

function T.slash_off_hides_and_on_shows_either_frame()
    local C = boot()
    slash("player off")
    eq(C.Get("unitFrames.hidePlayer"), true)
    eq(hidden(FS.player), true)
    slash("target off")
    eq(hidden(FS.target), true)
    slash("  Player   ON ")
    eq(shown(FS.player), true)
    eq(C.Get("unitFrames.hidePlayer"), false)
    slash("target on")
    eq(shown(FS.target), true)
end

function T.slash_with_a_bad_word_prints_usage_and_changes_nothing()
    local C = boot()
    slash("player maybe")
    slash("focus off")
    eq(shown(FS.player), true)
    eq(C.Get("unitFrames.hidePlayer"), false)
    eq(lastPrinted():find("/fsframes", 1, true) ~= nil, true, lastPrinted())
end

function T.slash_says_so_when_settings_are_read_only()
    local C = boot({ db = { profilesVersion = 99 } })
    slash("player off")
    eq(shown(FS.player), true)
    eq(lastPrinted():find("read-only", 1, true) ~= nil, true, lastPrinted())
end

-- The Frame whose OnEnter is an aura button's, found among the mock's frames.
local function auraButton()
    for _, f in ipairs(__frames) do
        if f._scripts.OnEnter and f._mouse then return f end
    end
end

function T.a_target_aura_button_shows_no_tooltip_while_the_target_is_hidden()
    local C = boot({ exists = { target = true } })
    local button = auraButton()
    eq(button ~= nil, true, "an aura button was built under the target")
    button._scripts.OnEnter(button)
    eq(__tooltips, 1, "shown target: tooltip appears")
    C.Set("unitFrames.hideTarget", true)
    button._scripts.OnEnter(button)
    eq(__tooltips, 1, "hidden target: no tooltip")
    C.Set("unitFrames.hideTarget", false)
    button._scripts.OnEnter(button)
    eq(__tooltips, 2, "shown again: tooltip appears")
end

function T.hiding_the_player_does_not_silence_target_aura_tooltips()
    local C = boot({ exists = { target = true } })
    C.Set("unitFrames.hidePlayer", true)
    local button = auraButton()
    button._scripts.OnEnter(button)
    eq(__tooltips, 1)
end

function T.a_target_aura_button_keeps_showing_tooltips_until_a_combat_hide_applies()
    local C = boot({ exists = { target = true } })
    local button = auraButton()
    __combat = true
    C.Set("unitFrames.hideTarget", true)
    button._scripts.OnEnter(button)
    eq(__tooltips, 1, "frame still visible in combat, so the tooltip matches what is on screen")
    endCombat()
    button._scripts.OnEnter(button)
    eq(__tooltips, 1, "hidden after combat: no tooltip")
end

-- In combat the aura slot cannot be read, so the tooltip is only as good as what the painter cached.
function T.a_target_aura_shows_its_spell_in_combat_from_the_cached_id()
    boot({ exists = { target = true }, realTips = true, aura = { name = "Rend", icon = "i", spellId = 772 } })
    local button = auraButton()
    __combat, __unreadable = true, true
    button._scripts.OnEnter(button)
    eq(GameTooltip._spell, 772, "the spell tooltip, not the bare name")
end

function T.a_target_aura_slot_reused_by_another_aura_shows_no_stale_spell()
    boot({ exists = { target = true }, realTips = true, aura = { name = "Rend", icon = "i", spellId = 772 } })
    local button = auraButton()
    __aura = { name = "Corruption", icon = "j", spellId = __SECRET }
    Fire("PLAYER_TARGET_CHANGED")
    __combat, __unreadable = true, true
    button._scripts.OnEnter(button)
    eq(GameTooltip._spell, nil, "Rend's id must not survive onto Corruption")
    eq(GameTooltip._text, "Corruption", "the new aura's name instead")
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__session = lua.eval(SESSION)
    lua.globals().__unitFramesSrc = UNITFRAMES_FILE.read_text(encoding="utf-8")
    lua.globals().__configSrc = CONFIG_FILE.read_text(encoding="utf-8")
    lua.globals().__targetAurasSrc = TARGETAURAS_FILE.read_text(encoding="utf-8")
    lua.globals().__helpersSrc = (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8")
    lua.execute(CHECKS)
    return lua


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the saved variable, frames and callbacks must not leak.
        try:
            boot().eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(names) - failed}/{len(names)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
