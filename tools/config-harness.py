#!/usr/bin/env python3
"""Runs the real Config.lua and Layout.lua headless against a small mock WoW API.

Config.lua keeps the account-wide settings store with named profiles inside
ForeverSTUwaveDB (per-character SavedVariables do not restore on this client), keys
each character by its GUID, and points Layout.lua's override store at the active
profile's layout table. These checks pin that:

  * a first login creates Default and assigns the character, and a second character
    gets Default too;
  * Get/Set/RegisterDefault/OnChange fire callbacks only for a changed value;
  * New/Copy/Rename/Delete/Reset obey their name and Default/active-profile rules;
  * switching profile re-seats the layout from the other profile's overrides and
    fires only the callbacks whose value differs, safely in combat;
  * a pre-profile ForeverSTUwaveDB.layout migrates into Default exactly once;
  * a character whose GUID is not readable at ADDON_LOADED is resolved at PLAYER_LOGIN;
  * a higher profilesVersion is read-only with one warning and never overwritten;
  * junk tables are repaired without throwing.

Both Lua files are the real ones; the frames are a recording mock, NOT the real client.

    python3 tools/config-harness.py

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
LAYOUT_FILE = Path(os.environ.get("LAYOUT_LUA", ADDON / "Core/Layout.lua"))
CONFIG_FILE = Path(os.environ.get("CONFIG_LUA", ADDON / "Core/Config.lua"))   # a mutant copy for mutation checks

MOCK = r"""
__combat = false
__blocked = 0
__frames = {}
__errors = {}
__printed = {}

local Frame = {}
Frame.__index = Frame
local function guarded(self)
    if __combat and self._protected then __blocked = __blocked + 1; return true end
end
function Frame:ClearAllPoints() if guarded(self) then return end; self._points = {} end
function Frame:SetPoint(point, rel, relPoint, x, y)
    if guarded(self) then return end
    self._sets = (self._sets or 0) + 1
    self._points[#self._points + 1] = { point = point, rel = rel, relPoint = relPoint, x = x, y = y }
end
function Frame:SetSize(w, h) if guarded(self) then return end; self._w, self._h = w, h end
function Frame:RegisterEvent(e) self._events[e] = true end
function Frame:UnregisterEvent(e) self._events[e] = nil end
function Frame:SetScript(k, fn) self._scripts[k] = fn end
function Frame:IsProtected() return self._protected or false end
function Frame:SetHeight(h) self._h = h end
function Frame:GetHeight() return self._h end

function CreateFrame()
    local f = setmetatable({ _points = {}, _events = {}, _scripts = {} }, Frame)
    __frames[#__frames + 1] = f
    return f
end
function InCombatLockdown() return __combat end
function __fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end
function print(...) __printed[#__printed + 1] = table.concat({ ... }, " ") end

UIParent = CreateFrame()
UIParent:SetHeight(1440)
EditModeManagerFrame = { UpdateLayoutInfo = function() end }
function hooksecurefunc(obj, name, fn)
    local orig = obj[name]
    obj[name] = function(...) local r = { orig(...) }; fn(...); return unpack(r) end
end
__handlerThrows = false
function geterrorhandler()
    return function(err)
        __errors[#__errors + 1] = tostring(err)
        if __handlerThrows then error("handler failed") end
    end
end

__guid, __name, __realm = "Player-1-AAAA", "Bob", "Realm"
function UnitGUID() return __guid end
function UnitName() return __name end
function GetRealmName() return __realm end
"""

SESSION = r"""
function(layoutSrc, configSrc)
    -- A fresh addon namespace and frame list over whatever ForeverSTUwaveDB holds, the
    -- way a relog does; the saved variable is deliberately left alone.
    __frames, __errors, __printed, __combat = {}, {}, {}, false
    __frames[1] = UIParent
    FS = {}
    assert(load(layoutSrc, "@Layout.lua"))("forever-stuwave", FS)
    assert(load(configSrc, "@Config.lua"))("forever-stuwave", FS)
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local G1, G2 = "Player-1-AAAA", "Player-1-BBBB"

local function session() __session(__layoutSrc, __configSrc) end
local function login()
    __fire("ADDON_LOADED", "forever-stuwave")
    __fire("PLAYER_LOGIN")
end
local function boot(db)
    if db ~= nil then ForeverSTUwaveDB = db end
    session()
    login()
    return FS.Config
end
local function seated(protected)
    local f = CreateFrame()
    f._protected = protected
    FS.Layout.Apply(f, "stance")
    return f
end
local function stanceX() return FS.Layout.stance.x end
local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end

local function recorder(C, key)
    local seen = {}
    C.OnChange(key, function(new, old, k) seen[#seen + 1] = { new = new, old = old, key = k } end)
    return seen
end

-- Two profiles in a fresh account: Default (stance 10/20, a=1, b=2) and Raid (stance 50/60, a=1, b=3).
local function twoProfiles()
    local C = boot({})
    C.RegisterDefault("a", 0); C.RegisterDefault("b", 0); C.RegisterDefault("c", "d")
    C.Set("a", 1); C.Set("b", 2)
    FS.Layout.SetOverride("stance", 10, 20)
    eq(C.NewProfile("Raid", "Default"), true)
    return C
end

-------------------------------------------------------------------------------
-- Characters and the Default profile
-------------------------------------------------------------------------------

function T.first_login_creates_default_and_assigns_the_character()
    local C = boot({})
    local db = ForeverSTUwaveDB
    eq(db.profilesVersion, 1)
    eq(type(db.profiles.Default), "table", "Default exists")
    eq(type(db.profiles.Default.settings), "table")
    eq(db.profiles.Default.layout.v, 1)
    eq(type(db.profiles.Default.layout.frames), "table")
    eq(db.profileKeys[G1], "Default", "keyed by GUID")
    eq(db.profileLabels[G1], "Bob-Realm", "a display label beside it")
    eq(C.ActiveProfile(), "Default")
    eq(#__printed, 0, "no warning")
end

function T.the_label_survives_without_a_realm_or_name()
    __realm = nil
    boot({})
    eq(ForeverSTUwaveDB.profileLabels[G1], "Bob")
    __name = nil
    __guid = G2
    session(); login()
    eq(ForeverSTUwaveDB.profileLabels[G2], nil, "no label when the name is unreadable")
    eq(ForeverSTUwaveDB.profileKeys[G2], "Default", "the character is still assigned")
    eq(ForeverSTUwaveDB.profileLabels[G1], "Bob", "the other label is kept")
end

function T.a_second_character_gets_default_too()
    boot({})
    __guid, __name = G2, "Alice"
    local C = boot()
    local db = ForeverSTUwaveDB
    eq(db.profileKeys[G1], "Default"); eq(db.profileKeys[G2], "Default")
    eq(db.profileLabels[G2], "Alice-Realm")
    eq(C.ActiveProfile(), "Default")
    eq(count(db.profiles), 1, "no extra profile")
end

function T.a_character_keeps_its_own_profile_across_sessions()
    local C = boot({})
    C.NewProfile("Raid")
    C.SetActiveProfile("Raid")
    __guid = G2
    eq(boot().ActiveProfile(), "Default", "the other character is untouched")
    __guid = G1
    eq(boot().ActiveProfile(), "Raid", "this one resumes its own")
end

function T.a_key_naming_a_missing_profile_falls_back_to_default()
    local C = boot({ profileKeys = { [G1] = "Gone" } })
    eq(C.ActiveProfile(), "Default")
    eq(ForeverSTUwaveDB.profileKeys[G1], "Default", "the stale key is rewritten")
end

-------------------------------------------------------------------------------
-- Settings
-------------------------------------------------------------------------------

function T.get_returns_the_registered_default_until_set()
    local C = boot({})
    eq(C.Get("x"), nil)
    C.RegisterDefault("x", 5)
    eq(C.Get("x"), 5)
    eq(C.Set("x", 7), true)
    eq(C.Get("x"), 7)
    eq(ForeverSTUwaveDB.profiles.Default.settings.x, 7, "stored in the active profile")
end

function T.is_stored_tells_a_pinned_value_from_a_default()
    local C = boot({})
    C.RegisterDefault("x", 5)
    eq(C.IsStored("x"), false, "a default is not stored")
    C.Set("x", 7)
    eq(C.IsStored("x"), true)
    C.Set("x", 5)
    eq(C.IsStored("x"), false, "back at the default stores nothing")
    eq(C.IsStored(nil), false)
    eq(C.NewProfile("Raid"), true)
    C.Set("x", 7)
    eq(C.SetActiveProfile("Raid"), true)
    eq(C.IsStored("x"), false, "per profile")
end

function T.set_fires_key_and_any_callbacks_with_new_old_and_key()
    local C = boot({})
    C.RegisterDefault("x", 5)
    local seen, any = recorder(C, "x"), {}
    C.OnAnyChange(function(key, new, old) any[#any + 1] = { key = key, new = new, old = old } end)
    C.Set("x", 6)
    eq(#seen, 1); eq(seen[1].new, 6); eq(seen[1].old, 5); eq(seen[1].key, "x")
    eq(#any, 1); eq(any[1].key, "x"); eq(any[1].new, 6); eq(any[1].old, 5)
    C.Set("x", 6)
    eq(#seen, 1, "an unchanged value fires nothing")
    C.Set("other", 1)
    eq(#seen, 1, "another key does not fire this one"); eq(#any, 2, "but the any hook sees it")
end

function T.setting_a_value_equal_to_the_default_or_nil_stores_nothing()
    local C = boot({})
    C.RegisterDefault("x", 5)
    C.Set("x", 6); C.Set("x", 5)
    eq(ForeverSTUwaveDB.profiles.Default.settings.x, nil, "the default is not pinned")
    C.Set("x", 6); C.Set("x", nil)
    eq(C.Get("x"), 5, "nil goes back to the default")
    eq(ForeverSTUwaveDB.profiles.Default.settings.x, nil)
end

function T.a_throwing_callback_is_reported_and_does_not_stop_the_others()
    local C = boot({})
    local ran = 0
    C.OnChange("x", function() error("boom") end)
    C.OnChange("x", function() ran = ran + 1 end)
    C.OnAnyChange(function() ran = ran + 1 end)
    eq(C.Set("x", 1), true)
    eq(ran, 2, "both later callbacks ran")
    eq(#__errors, 1, "the error went to the error handler")
    eq(C.Get("x"), 1)
end

function T.a_throwing_error_handler_does_not_break_the_callback_loop()
    local C = boot({})
    local ran = 0
    __handlerThrows = true
    C.OnChange("x", function() error("boom") end)
    C.OnChange("x", function() ran = ran + 1 end)
    C.OnAnyChange(function() ran = ran + 1 end)
    eq(C.Set("x", 1), true, "Set still returns")
    eq(ran, 2, "the later callbacks still ran")
    eq(#__errors, 1, "the handler was reached")
    eq(C.Get("x"), 1)
end

function T.bad_arguments_are_refused_without_throwing()
    local C = boot({})
    eq(C.Set(nil, 1), false); eq(C.Set("", 1), false); eq(C.Set(5, 1), false)
    eq(C.Get(nil), nil); eq(C.Get(5), nil)
    C.OnChange(nil, function() end); C.OnChange("x", nil); C.OnAnyChange(nil)
    C.RegisterDefault(nil, 1); C.RegisterDefault("", 1)
    eq(C.Get(""), nil)
end

function T.get_and_set_before_the_saved_variables_load_are_safe()
    session()
    local C = FS.Config
    C.RegisterDefault("x", 3)
    eq(C.Get("x"), 3, "defaults answer at file scope")
    eq(C.Set("x", 4), false, "nothing to write into yet")
    eq(C.ActiveProfile(), "Default")
    eq(ForeverSTUwaveDB, nil, "and nothing was created")
end

function T.settings_persist_across_sessions()
    local C = boot({})
    C.Set("x", "kept")
    session(); login()
    eq(FS.Config.Get("x"), "kept")
end

-------------------------------------------------------------------------------
-- Profile management
-------------------------------------------------------------------------------

function T.new_profile_trims_and_validates_the_name()
    local C = boot({})
    local ok, name = C.NewProfile("  Raid  ")
    eq(ok, true); eq(name, "Raid", "trimmed")
    eq(type(ForeverSTUwaveDB.profiles.Raid), "table")
    eq(ForeverSTUwaveDB.profiles.Raid.layout.v, 1)
    eq(C.NewProfile(""), false); eq(C.NewProfile("   \t "), false)
    eq(C.NewProfile(nil), false); eq(C.NewProfile(5), false); eq(C.NewProfile({}), false)
    eq(C.NewProfile(string.rep("x", 33)), false, "over the cap")
    eq(C.NewProfile(string.rep("x", 32)), true, "at the cap")
    eq(C.NewProfile("raid"), false, "duplicates ignore case")
    eq(C.NewProfile("RAID "), false, "and surrounding space")
    eq(C.NewProfile("default"), false, "Default is taken")
    eq(C.NewProfile("a|cffff0000b"), false, "no escape sequences")
    eq(C.NewProfile("a\nb"), false, "no control characters")
    eq(C.ActiveProfile(), "Default", "creating does not switch")
end

function T.new_profile_can_copy_another_independently()
    local C = twoProfiles()
    C.NewProfile("Copy", "Default")
    local p = ForeverSTUwaveDB.profiles
    eq(p.Copy.settings.a, 1); eq(p.Copy.layout.frames.stance.x, 10)
    p.Default.settings.a = 99
    p.Default.layout.frames.stance.x = 99
    eq(p.Copy.settings.a, 1, "settings are a deep copy")
    eq(p.Copy.layout.frames.stance.x, 10, "layout is a deep copy")
    eq(C.NewProfile("Nope", "Missing"), false, "unknown source")
    eq(p.Nope, nil)
    local ok, name = C.NewProfile("Blank")
    eq(next(p.Blank.settings), nil, "no copy source means empty")
end

function T.copy_profile_replaces_the_active_profile_from_another()
    local C = twoProfiles()
    ForeverSTUwaveDB.profiles.Raid.settings.b = 3
    ForeverSTUwaveDB.profiles.Raid.layout.frames.stance = { x = 50, y = 60 }
    local f = seated(false)
    local b, a = recorder(C, "b"), recorder(C, "a")
    eq(C.CopyProfile("Raid"), true)
    eq(C.ActiveProfile(), "Default", "still the active profile")
    eq(C.Get("b"), 3); eq(C.Get("a"), 1)
    eq(stanceX(), 50, "layout store now holds the copy")
    eq(f._points[1].x, 50, "and the frame was re-seated")
    eq(#b, 1); eq(b[1].new, 3); eq(b[1].old, 2)
    eq(#a, 0, "an unchanged value fires nothing")
    ForeverSTUwaveDB.profiles.Raid.settings.b = 8
    eq(C.Get("b"), 3, "independent of the source afterwards")
    eq(FS.Layout.SetOverride("stance", 70, 71), true)
    eq(ForeverSTUwaveDB.profiles.Raid.layout.frames.stance.x, 50, "writes land in the active profile only")
    eq(C.CopyProfile("Default"), false, "not from itself")
    eq(C.CopyProfile("Missing"), false)
    eq(C.CopyProfile(nil), false)
end

function T.rename_profile_follows_the_rules_and_moves_the_keys()
    local C = twoProfiles()
    eq(C.RenameProfile("Default", "Main"), false, "Default cannot be renamed")
    eq(C.RenameProfile("Missing", "X"), false)
    eq(C.RenameProfile("Raid", "default"), false, "collides with Default")
    eq(C.NewProfile("Other"), true)
    eq(C.RenameProfile("Raid", "other"), false, "collides ignoring case")
    eq(C.RenameProfile("Raid", ""), false); eq(C.RenameProfile("Raid", string.rep("y", 40)), false)
    eq(C.SetActiveProfile("Raid"), true)
    ForeverSTUwaveDB.profileKeys["Player-9"] = "Raid"
    local ok, name = C.RenameProfile("Raid", "  Dungeon ")
    eq(ok, true); eq(name, "Dungeon")
    eq(ForeverSTUwaveDB.profiles.Raid, nil); eq(type(ForeverSTUwaveDB.profiles.Dungeon), "table")
    eq(C.ActiveProfile(), "Dungeon", "the active name follows")
    eq(ForeverSTUwaveDB.profileKeys[G1], "Dungeon"); eq(ForeverSTUwaveDB.profileKeys["Player-9"], "Dungeon")
    eq(C.RenameProfile("Dungeon", "DUNGEON"), true, "a case-only rename of itself is fine")
    eq(C.ActiveProfile(), "DUNGEON")
    eq(C.RenameProfile("DUNGEON", "DUNGEON"), true, "renaming to itself changes nothing")
end

function T.delete_profile_refuses_default_and_the_active_one()
    local C = twoProfiles()
    eq(C.DeleteProfile("Default"), false)
    C.SetActiveProfile("Raid")
    eq(C.DeleteProfile("Raid"), false, "the active profile stays")
    eq(C.DeleteProfile("Missing"), false)
    eq(C.DeleteProfile(nil), false)
    ForeverSTUwaveDB.profileKeys["Player-9"] = "Raid"
    C.SetActiveProfile("Default")
    eq(C.DeleteProfile("Raid"), true)
    eq(ForeverSTUwaveDB.profiles.Raid, nil)
    eq(ForeverSTUwaveDB.profileKeys["Player-9"], "Default", "another character on it moves to Default")
    eq(C.DeleteProfile("Raid"), false, "already gone")
end

function T.reset_profile_returns_the_active_profile_to_defaults()
    local C = twoProfiles()
    local f = seated(false)
    eq(f._points[1].x, 10)
    local a, c = recorder(C, "a"), recorder(C, "c")
    eq(C.ResetProfile(), true)
    eq(C.ActiveProfile(), "Default", "still active")
    eq(C.Get("a"), 0); eq(C.Get("b"), 0); eq(C.Get("c"), "d")
    eq(next(ForeverSTUwaveDB.profiles.Default.settings), nil)
    eq(next(ForeverSTUwaveDB.profiles.Default.layout.frames), nil)
    eq(f._points[1].x, 0, "the frame is back on the layout default")
    eq(#a, 1); eq(a[1].new, 0); eq(a[1].old, 1)
    eq(#c, 0, "a value already at its default fires nothing")
    eq(ForeverSTUwaveDB.profiles.Raid.settings.b, 2, "other profiles are untouched")
end

function T.saved_profiles_that_differ_only_by_case_are_kept_and_stay_addressable()
    local db = { profilesVersion = 1, profileLabels = {}, profileKeys = { [G1] = "raid" },
        profiles = {
            Default = { settings = {}, layout = { v = 1, frames = {} } },
            Raid = { settings = { x = 1 }, layout = { v = 1, frames = {} } },
            raid = { settings = { x = 2 }, layout = { v = 1, frames = {} } },
        } }
    local C = boot(db)
    eq(C.ActiveProfile(), "raid", "the exact saved name is honoured")
    eq(C.Get("x"), 2)
    eq(count(db.profiles), 3, "neither profile is dropped")
    eq(#C.ListProfiles(), 3)
    eq(C.NewProfile("RAID"), false)
    eq(C.RenameProfile("Raid", "raid"), false, "cannot rename onto its case twin")
    eq(C.SetActiveProfile("Raid"), true)
    eq(C.Get("x"), 1)
    eq(C.DeleteProfile("raid"), true, "the twin is deletable by its exact name")
    eq(db.profiles.Raid.settings.x, 1)
    eq(C.RenameProfile("Raid", "RAID"), true, "once alone, a case-only rename works")
end

function T.list_profiles_is_sorted_with_default_first()
    local C = boot({})
    C.NewProfile("zeta"); C.NewProfile("Alpha"); C.NewProfile("beta")
    local list = C.ListProfiles()
    eq(#list, 4)
    eq(list[1], "Default"); eq(list[2], "Alpha"); eq(list[3], "beta"); eq(list[4], "zeta")
end

-------------------------------------------------------------------------------
-- Switching
-------------------------------------------------------------------------------

function T.switching_reseats_the_layout_and_fires_only_changed_settings()
    local C = twoProfiles()
    ForeverSTUwaveDB.profiles.Raid.settings.b = 3
    ForeverSTUwaveDB.profiles.Raid.layout.frames.stance = { x = 50, y = 60 }
    ForeverSTUwaveDB.profiles.Raid.layout.frames.action = { x = 1, y = 2 }
    local f, g = seated(false), CreateFrame()
    FS.Layout.Apply(g, "action")
    eq(f._points[1].x, 10, "seated on Default's override")
    eq(g._points[1].x, -7)
    local a, b, c, any = recorder(C, "a"), recorder(C, "b"), recorder(C, "c"), {}
    C.OnAnyChange(function(key) any[#any + 1] = key end)
    local fSeats, gSeats = f._sets, g._sets
    eq(C.SetActiveProfile("Raid"), true)
    eq(C.ActiveProfile(), "Raid")
    eq(f._points[1].x, 50); eq(f._points[1].y, 60, "the other profile's override")
    eq(g._points[1].x, 1, "every id is re-seated, not just one")
    eq(f._sets, fSeats + 1, "each frame was seated exactly once")
    eq(g._sets, gSeats + 1)
    eq(#a, 0, "same value in both: no callback"); eq(#c, 0)
    eq(#b, 1); eq(b[1].new, 3); eq(b[1].old, 2)
    eq(#any, 1); eq(any[1], "b")
    eq(ForeverSTUwaveDB.profileKeys[G1], "Raid", "the choice is remembered")
    eq(C.SetActiveProfile("Default"), true)
    eq(f._points[1].x, 10, "and back"); eq(g._points[1].x, -7, "an id Default does not override is back on its default")
    eq(#b, 2); eq(b[2].new, 2); eq(b[2].old, 3)
    eq(C.SetActiveProfile("Default"), true, "switching to the active profile")
    eq(#b, 2, "does nothing")
    eq(C.SetActiveProfile("Missing"), false)
    eq(C.SetActiveProfile(nil), false)
    eq(C.ActiveProfile(), "Default")
end

function T.a_key_present_in_only_one_profile_fires_when_it_differs_from_the_other()
    local C = twoProfiles()
    ForeverSTUwaveDB.profiles.Raid.settings.only = "x"
    local only = recorder(C, "only")
    C.SetActiveProfile("Raid")
    eq(#only, 1); eq(only[1].new, "x"); eq(only[1].old, nil)
    C.SetActiveProfile("Default")
    eq(#only, 2); eq(only[2].new, nil); eq(only[2].old, "x")
end

function T.overrides_written_after_a_switch_land_in_the_new_profile()
    local C = twoProfiles()
    C.SetActiveProfile("Raid")
    eq(FS.Layout.SetOverride("stance", 90, 91), true)
    eq(ForeverSTUwaveDB.profiles.Raid.layout.frames.stance.x, 90)
    eq(ForeverSTUwaveDB.profiles.Default.layout.frames.stance.x, 10, "the old profile is untouched")
    FS.Layout.ClearAllOverrides()
    eq(next(ForeverSTUwaveDB.profiles.Raid.layout.frames), nil)
    eq(ForeverSTUwaveDB.profiles.Default.layout.frames.stance.x, 10)
end

function T.switching_in_combat_defers_protected_frames_but_fires_callbacks()
    local C = twoProfiles()
    ForeverSTUwaveDB.profiles.Raid.settings.b = 3
    ForeverSTUwaveDB.profiles.Raid.layout.frames.stance = { x = 50, y = 60 }
    local held, free = seated(true), seated(false)
    local b = recorder(C, "b")
    local heldSeats = held._sets
    __combat = true
    eq(C.SetActiveProfile("Raid"), true)
    eq(held._sets, heldSeats, "no seat call reached the protected frame")
    eq(__blocked, 0, "no protected operation was attempted")
    eq(held._points[1].x, 10, "the protected frame is left alone")
    eq(free._points[1].x, 50, "an unprotected one is seated at once")
    eq(#b, 1, "settings callbacks fire in combat")
    eq(C.Get("b"), 3)
    __combat = false
    __fire("PLAYER_REGEN_ENABLED")
    eq(held._points[1].x, 50, "seated when combat ends")
    eq(held._sets, heldSeats + 1, "seated once, not repeatedly")
    eq(__blocked, 0)
end

function T.profile_management_works_in_combat()
    local C = boot({})
    __combat = true
    eq(C.NewProfile("Raid"), true)
    eq(C.Set("x", 1), true)
    eq(C.RenameProfile("Raid", "Raid2"), true)
    eq(C.DeleteProfile("Raid2"), true)
end

-------------------------------------------------------------------------------
-- Migration
-------------------------------------------------------------------------------

function T.an_old_layout_key_moves_into_default_and_applies()
    local old = { v = 1, frames = { stance = { x = 10, y = 20 } } }
    local db = { layout = old, gunsight = { a = 1 }, chatFontSize = 14 }
    boot(db)
    eq(db.layout, nil, "the old key is gone")
    eq(db.profiles.Default.layout, old, "the same table moved")
    eq(db.profiles.Default.layout.frames.stance.x, 10)
    eq(stanceX(), 10, "and it is applied")
    eq(db.gunsight.a, 1, "other module keys are untouched"); eq(db.chatFontSize, 14)
    session(); login()
    eq(stanceX(), 10, "stable on the next session")
    eq(db.layout, nil)
end

function T.migration_keeps_a_higher_version_layout_intact_and_ignored()
    local old = { v = 2, frames = { stance = { x = 10, y = 20 } }, future = "keep" }
    local db = { layout = old }
    boot(db)
    eq(db.profiles.Default.layout, old)
    eq(old.v, 2); eq(old.future, "keep"); eq(old.frames.stance.x, 10)
    eq(stanceX(), 0, "not applied")
    eq(#__printed, 1, "one warning from Layout")
    eq(FS.Layout.SetOverride("stance", 5, 5), false, "never written")
    eq(old.frames.stance.x, 10)
end

function T.migration_does_not_clobber_an_existing_default_layout()
    local existing = { v = 1, frames = { stance = { x = 1, y = 2 } } }
    local old = { v = 1, frames = { stance = { x = 10, y = 20 } } }
    local db = { layout = old, profilesVersion = 1,
        profiles = { Default = { settings = {}, layout = existing } }, profileKeys = {}, profileLabels = {} }
    boot(db)
    eq(db.profiles.Default.layout, existing)
    eq(stanceX(), 1)
    eq(db.layout, old, "the unmigrated layout is kept, not dropped")
    eq(db.layoutMigrated, true, "and marked so it is never imported later")
end

function T.a_reset_then_relog_never_reimports_a_kept_old_layout()
    local existing = { v = 1, frames = { stance = { x = 1, y = 2 } } }
    local old = { v = 1, frames = { stance = { x = 10, y = 20 } } }
    local db = { layout = old, profilesVersion = 1,
        profiles = { Default = { settings = {}, layout = existing } }, profileKeys = {}, profileLabels = {} }
    local C = boot(db)
    eq(C.ResetProfile(), true)
    session(); login()
    eq(next(db.profiles.Default.layout.frames), nil, "Default stays empty")
    eq(stanceX(), 0, "the old positions did not come back")
    eq(db.layout, old)
end

function T.migration_does_not_replace_a_higher_version_default_layout()
    local future = { v = 2, frames = {}, future = "keep" }
    local old = { v = 1, frames = { stance = { x = 10, y = 20 } } }
    local db = { layout = old, profilesVersion = 1,
        profiles = { Default = { settings = {}, layout = future } }, profileKeys = {}, profileLabels = {} }
    boot(db)
    eq(db.profiles.Default.layout, future, "a layout this addon cannot read is not replaced")
    eq(future.future, "keep")
    eq(db.layout, old); eq(db.layoutMigrated, true)
    eq(stanceX(), 0)
end

function T.a_successful_migration_leaves_no_marker_and_a_later_session_changes_nothing()
    local old = { v = 1, frames = { stance = { x = 10, y = 20 } } }
    local db = { layout = old }
    boot(db)
    eq(db.layout, nil); eq(db.layoutMigrated, nil)
    session(); login()
    eq(db.profiles.Default.layout, old)
end

function T.a_junk_old_layout_key_is_dropped()
    local db = { layout = "junk" }
    boot(db)
    eq(db.layout, nil)
    eq(db.profiles.Default.layout.v, 1)
end

-------------------------------------------------------------------------------
-- GUID unavailable at ADDON_LOADED
-------------------------------------------------------------------------------

function T.a_guid_unreadable_at_addon_loaded_is_resolved_at_player_login()
    ForeverSTUwaveDB = {}
    session()
    __guid = nil
    __fire("ADDON_LOADED", "forever-stuwave")
    eq(FS.Config.ActiveProfile(), "Default", "Default until the character is known")
    eq(next(ForeverSTUwaveDB.profileKeys), nil, "nothing assigned yet")
    __guid = G1
    __fire("PLAYER_LOGIN")
    eq(ForeverSTUwaveDB.profileKeys[G1], "Default")
    eq(ForeverSTUwaveDB.profileLabels[G1], "Bob-Realm")
    eq(FS.Config.ActiveProfile(), "Default")
end

function T.the_assigned_profile_layout_is_in_place_after_a_late_guid()
    local db = { profilesVersion = 1, profileLabels = {}, profileKeys = { [G1] = "Raid" },
        profiles = {
            Default = { settings = { b = 1 }, layout = { v = 1, frames = { stance = { x = 10, y = 20 } } } },
            Raid = { settings = { b = 3 }, layout = { v = 1, frames = { stance = { x = 50, y = 60 } } } },
        } }
    ForeverSTUwaveDB = db
    session()
    local f = seated(false)
    local b = recorder(FS.Config, "b")
    __guid = nil
    __fire("ADDON_LOADED", "forever-stuwave")
    eq(stanceX(), 10, "provisional Default overrides are in place for the login pass")
    __guid = G1
    local seats = f._sets
    __fire("PLAYER_LOGIN")
    eq(FS.Config.ActiveProfile(), "Raid")
    eq(stanceX(), 50)
    eq(f._points[#f._points].x, 50, "the frame was re-seated onto the character's profile")
    eq(f._sets, seats + 2, "one login pass plus one profile switch")
    eq(#b, 1, "and the changed setting fired"); eq(b[1].new, 3); eq(b[1].old, 1)
end

function T.a_guid_readable_at_addon_loaded_has_the_profile_in_place_before_the_login_reseat()
    local db = { profilesVersion = 1, profileLabels = {}, profileKeys = { [G1] = "Raid" },
        profiles = {
            Default = { settings = {}, layout = { v = 1, frames = {} } },
            Raid = { settings = {}, layout = { v = 1, frames = { stance = { x = 50, y = 60 } } } },
        } }
    ForeverSTUwaveDB = db
    session()
    local f = seated(false)
    __fire("ADDON_LOADED", "SomeOtherAddon")
    eq(stanceX(), 0, "another addon's load does nothing")
    __fire("ADDON_LOADED", "forever-stuwave")
    eq(stanceX(), 50, "bound on our own ADDON_LOADED")
    __fire("PLAYER_LOGIN")
    eq(f._points[1].x, 50, "the login pass seats the frame at the override")
end

function T.a_guid_that_never_becomes_readable_leaves_default_in_use_and_writes_no_key()
    ForeverSTUwaveDB = {}
    session()
    __guid = nil
    login()
    local C = FS.Config
    eq(C.ActiveProfile(), "Default")
    eq(C.NewProfile("Raid"), true)
    eq(C.SetActiveProfile("Raid"), false, "no character to remember the choice for")
    eq(next(ForeverSTUwaveDB.profileKeys), nil)
    eq(C.Set("x", 1), true, "settings still work on Default")
end

-------------------------------------------------------------------------------
-- Higher profilesVersion and junk tables
-------------------------------------------------------------------------------

function T.a_higher_profiles_version_is_read_only_with_one_warning_and_never_written()
    local layout = { v = 1, frames = { stance = { x = 5, y = 5 } } }
    local profiles = { Default = { settings = { x = 9 }, layout = { v = 1, frames = {} }, future = "keep" } }
    local keys = { [G1] = "Default" }
    local db = { profilesVersion = 2, profiles = profiles, profileKeys = keys, layout = layout, other = "keep" }
    local C = boot(db)
    session(); login()
    C = FS.Config
    eq(#__printed, 1, "one warning per session")
    eq(db.profilesVersion, 2); eq(db.profiles, profiles); eq(db.profileKeys, keys); eq(db.layout, layout)
    eq(profiles.Default.future, "keep"); eq(profiles.Default.settings.x, 9)
    eq(count(db), 5, "no key added to the saved variable")
    eq(count(keys), 1); eq(db.profileLabels, nil)
    eq(C.Get("x"), nil, "newer settings are not interpreted")
    C.RegisterDefault("x", 4)
    eq(C.Get("x"), 4)
    eq(C.Set("x", 1), false)
    eq(C.NewProfile("Raid"), false); eq(C.CopyProfile("Default"), false)
    eq(C.RenameProfile("Default", "X"), false); eq(C.DeleteProfile("Default"), false)
    eq(C.ResetProfile(), false); eq(C.SetActiveProfile("Default"), false)
    eq(C.IsReadOnly(), true)
    eq(stanceX(), 0, "layout overrides are not applied")
    eq(FS.Layout.SetOverride("stance", 9, 9), false)
    eq(layout.frames.stance.x, 5, "untouched")
    eq(count(profiles), 1); eq(count(db), 5)
end

function T.a_non_table_saved_variable_is_read_only_not_an_error()
    ForeverSTUwaveDB = "junk"
    local C = boot()
    eq(ForeverSTUwaveDB, "junk", "never replaced")
    eq(C.IsReadOnly(), true)
    eq(C.Set("x", 1), false)
    eq(#__printed, 1)
end

function T.junk_profile_tables_are_repaired()
    local db = { profilesVersion = "x", profiles = "junk", profileKeys = 5, profileLabels = true }
    local C = boot(db)
    eq(db.profilesVersion, 1)
    eq(type(db.profiles.Default), "table")
    eq(db.profileKeys[G1], "Default"); eq(db.profileLabels[G1], "Bob-Realm")
    eq(C.IsReadOnly(), false)

    db = { profiles = { Default = 7, Raid = { settings = 3, layout = "x" }, [5] = {}, Bad = "x" },
        profileKeys = { [G1] = 12 }, profileLabels = {} }
    C = boot(db)
    eq(type(db.profiles.Default.settings), "table", "Default is rebuilt")
    eq(db.profiles.Default.layout.v, 1)
    eq(type(db.profiles.Raid.settings), "table", "a junk settings table is replaced")
    eq(db.profiles.Raid.layout.v, 1, "a junk layout is replaced")
    eq(db.profiles[5], nil, "a non-string profile name is dropped")
    eq(db.profiles.Bad, nil, "a non-table profile is dropped")
    eq(db.profileKeys[G1], "Default", "a non-string key target falls back to Default")
    eq(C.ActiveProfile(), "Default")
    eq(C.Set("x", 1), true)
end

function T.a_profile_layout_with_a_higher_version_is_left_to_layout_and_never_overwritten()
    local layout = { v = 2, frames = { stance = { x = 5, y = 5 } }, future = "keep" }
    local db = { profilesVersion = 1, profileKeys = { [G1] = "Default" }, profileLabels = {},
        profiles = { Default = { settings = {}, layout = layout } } }
    local C = boot(db)
    eq(db.profiles.Default.layout, layout)
    eq(layout.v, 2); eq(layout.future, "keep")
    eq(stanceX(), 0)
    eq(C.Set("x", 1), true, "settings are unaffected")
    eq(FS.Layout.SetOverride("stance", 9, 9), false)
    eq(C.ResetProfile(), true, "an explicit reset is the user's own act")
end

function T.the_saved_variable_is_created_when_it_does_not_exist()
    ForeverSTUwaveDB = nil
    boot()
    eq(type(ForeverSTUwaveDB), "table")
    eq(ForeverSTUwaveDB.profileKeys[G1], "Default")
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__session = lua.eval(SESSION)
    lua.globals().__layoutSrc = LAYOUT_FILE.read_text(encoding="utf-8")
    lua.globals().__configSrc = CONFIG_FILE.read_text(encoding="utf-8")
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
