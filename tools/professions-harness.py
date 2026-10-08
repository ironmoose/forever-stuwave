#!/usr/bin/env python3
"""Runs the real Professions.lua headless to pin the click-to-open rows and their combat safety.

Each row of the professions panel is a secure button (type "spell") that casts its profession and
so opens its window. These checks pin that:

  * the attribute mapping is an allowlist: the crafting professions cast their own name, Mining casts
    Smelting, and everything else (Herbalism, Skinning, Fishing, Archaeology, localized or unknown names)
    gets no type or spell attribute and no "Click to open" line;
  * a row that changes profession rewrites (and clears) its attributes;
  * the rows register AnyUp and AnyDown clicks and are secure buttons;
  * SetAttribute, Show and Hide on a secure button, or on the panel that parents one, never run
    while InCombatLockdown() is true, and the refresh replays on PLAYER_REGEN_ENABLED;
  * SetPoint, ClearAllPoints, SetSize, SetParent and Layout.Apply are not made on the panel or a row in
    combat either, and run on the regen replay;
  * a login in combat builds nothing until combat ends;
  * PLAYER_ENTERING_WORLD in combat after the panel exists parks one Setup for PLAYER_REGEN_ENABLED;
  * one click casts once, whichever edge ActionButtonUseKeyDown and useOnKeyDown select (the model is the
    harness's reading of SecureActionButton_OnClick, so it pins our registration and that nothing
    overrides OnClick, not the client's dispatch);
  * /fsprof in combat prints that it applies after combat and applies then (latest request wins);
  * the saved hidden state is still restored at login and not re-applied by a later loading screen;
  * visibility is the profile setting professions.shown (default true): a change from /fsprof, the config
    window or a profile switch takes the same combat deferral, the legacy ForeverSTUwaveDB.professionsHidden
    migrates once into the active profile without overwriting a pinned value and is then cleared, and a
    read-only Config refuses the toggle;
  * the tooltip names the profession and adds "Click to open" only on a clickable row;
  * the minimise glyph is a plain (non-secure) button reusing the chat's glyph texture and idle/hover alphas, its
    tooltip reads Minimise or Restore, a click folds the rows into the title band with the top edge fixed and
    a second click restores them, the state is the profile setting professions.minimized (default false), is
    applied at login and survives /fsprof, a reseat or a profile switch, and in combat every part of it
    (hide, show, resize, re-anchor) waits for PLAYER_REGEN_ENABLED.

Professions.lua and Config.lua are the real files; the frames are a recording mock that refuses protected
calls in combat the way the client does, and Theme / PanelSkins are stubs. This is NOT the real client.

    python3 tools/professions-harness.py

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
# PROFESSIONS_LUA points the harness at a mutant copy (a check must fail on a broken one).
PROFESSIONS_FILE = Path(os.environ.get("PROFESSIONS_LUA", ADDON / "Modules/Skins/Professions.lua"))
CONFIG_FILE = ADDON / "Core/Config.lua"

MOCK = r"""
__combat = false
__frames = {}
__printed = {}
__violations = {}   -- protected calls attempted in combat (refused, like the client)

local Frame = {}
local FrameMT = {}
FrameMT.__index = function(self, k)
    local m = Frame[k]
    if m then return m end
    if type(k) == "string" and k:find("^%u") then
        return function() end   -- any widget method the checks do not care about
    end
    return nil   -- a field (fsBuilt, name, _shown): absent on a real frame too
end

function newFrame(kind, name, parent, template)
    local f = setmetatable({ _kind = kind, _name = name, _parent = parent, _events = {}, _scripts = {}, _hooks = {},
        _attrs = {}, _clicks = nil, _shown = true, _text = nil, _points = {},
        _protected = type(template) == "string" and template:find("Secure", 1, true) ~= nil }, FrameMT)
    __frames[#__frames + 1] = f
    if name then _G[name] = f end
    if f._protected and parent then
        local p = parent
        while p do p._hasProtectedChild = true; p = p._parent end
    end
    return f
end
function CreateFrame(kind, name, parent, template) return newFrame(kind, name, parent, template) end
function Frame.CreateTexture(self) return newFrame("Texture", nil, self) end
function Frame.CreateFontString(self) return newFrame("FontString", nil, self) end
function Frame.SetScript(self, k, fn) self._scripts[k] = fn end
function Frame.HookScript(self, k, fn) self._hooks[k] = self._hooks[k] or {}; table.insert(self._hooks[k], fn) end
function Frame.RegisterEvent(self, e) self._events[e] = true end
function Frame.UnregisterEvent(self, e) self._events[e] = nil end
function Frame.RegisterForClicks(self, ...) self._clicks = table.concat({ ... }, ",") end
function Frame.SetText(self, t) self._text = t end
function Frame.GetText(self) return self._text end
function Frame.SetTexture(self, t) self._texture = t end
function Frame.SetVertexColor(self, r, g, b, a) self._vc = { r, g, b, a } end

local function locked(self) return __combat and (self._protected or self._hasProtectedChild) end
local function refuse(self, what)
    __violations[#__violations + 1] = what .. ":" .. tostring(self._name or self._kind)
end
function Frame.SetAttribute(self, k, v)
    if locked(self) then return refuse(self, "SetAttribute") end
    self._attrs[k] = v
end
-- Geometry is recorded (points as { point, relativeTo, relPoint, x, y }, size as _w/_h) so a check can
-- read where a frame sits; each call is refused on a locked frame in combat, like the client.
function Frame.SetPoint(self, point, rel, relPoint, x, y)
    if locked(self) then return refuse(self, "SetPoint") end
    self._points[#self._points + 1] = { point, rel, relPoint, x, y }
end
function Frame.ClearAllPoints(self)
    if locked(self) then return refuse(self, "ClearAllPoints") end
    self._points = {}
end
function Frame.SetSize(self, w, h)
    if locked(self) then return refuse(self, "SetSize") end
    self._w, self._h = w, h
end
function Frame.SetHeight(self, h)
    if locked(self) then return refuse(self, "SetHeight") end
    self._h = h
end
function Frame.SetParent(self)
    if locked(self) then return refuse(self, "SetParent") end
end
function Frame.GetAttribute(self, k) return self._attrs[k] end
function Frame.Show(self)
    if locked(self) then return refuse(self, "Show") end
    self._shown = true
end
function Frame.Hide(self)
    if locked(self) then return refuse(self, "Hide") end
    self._shown = false
end
function Frame.IsShown(self) return self._shown end

function InCombatLockdown() return __combat end
function UnitGUID() return "Player-1-AAAA" end
function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[i] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(parts, " ")
end
SlashCmdList = {}

__tip = {}
GameTooltip = {
    SetOwner = function(self, owner, anchor) __tip = { owner = owner, anchor = anchor, lines = {}, shown = false }; self._owner = owner end,
    SetText = function(_, t) __tip.lines = { t } end,   -- SetText replaces the text, AddLine appends
    AddLine = function(_, t) __tip.lines[#__tip.lines + 1] = t end,
    Show = function() __tip.shown = true end,
    Hide = function() __tip.shown = false end,
    GetOwner = function(self) return self._owner end,
}

-- GetProfessions returns six slot indices; __slots holds them, __info maps index -> {name, icon, rank, max}.
__slots, __info = {}, {}
__profCalls = 0
function GetProfessions() __profCalls = __profCalls + 1; return __slots[1], __slots[2], __slots[3], __slots[4], __slots[5], __slots[6] end
function GetProfessionInfo(i)
    local e = __info[i]
    if not e then return nil end
    return e[1], e[2], e[3], e[4]
end

function Fire(event, ...)
    for _, f in ipairs(__frames) do
        if f._events[event] and f._scripts.OnEvent then f._scripts.OnEvent(f, event, ...) end
    end
end

UIParent = newFrame("Frame", "UIParent")
"""

SESSION = r"""
function(src, opts, configSrc)
    opts = opts or {}
    __frames, __printed, __violations, __profCalls, __errors = {}, {}, {}, 0, {}
    __frames[1] = UIParent
    ForeverSTUwaveProfessions = nil
    __combat = opts.combatAtLoad == true
    ForeverSTUwaveDB = opts.db
    __slots, __info = {}, {}
    for i, p in ipairs(opts.profs or {}) do
        __slots[i] = i
        __info[i] = { p, "icon-" .. p, 10 + i, 75 }
    end
    FS = {}
    FS.IsSecret = function() return false end
    FS.LogDegradeOnce = function() end
    __layoutApplied = 0
    -- The seat is the real entry's shape: CENTER on CENTER, scaled by the UI scale (0.5 here).
    __rescale = {}
    FS.Layout = {
        Scale = function() return 0.5 end,
        professions = { point = "CENTER", relPoint = "CENTER", x = 923, y = -450, w = 300, h = 210 },
        OnRescale = function(fn) __rescale[#__rescale + 1] = fn end,
        Apply = function(frame, id)
            __layoutApplied = __layoutApplied + 1
            if __combat then __violations[#__violations + 1] = "Layout.Apply" end
            local L = FS.Layout[id]
            frame:ClearAllPoints()
            frame:SetPoint(L.point, UIParent, L.relPoint, L.x * 0.5, L.y * 0.5)
            frame:SetSize(L.w * 0.5, L.h * 0.5)
            return L
        end,
        ForwardError = function(err) __errors[#__errors + 1] = tostring(err) end,
    }
    __placed = nil
    if opts.chatPlace then
        FS.Chat = { PlaceTermBarTooltip = function(button) __placed = button end }
    end
    FS.PanelSkins = { RegisterRecon = function() end }
    local Theme = {}
    for _, name in ipairs({ "ApplyMono", "AddOuterGlow", "AddRoundedFill", "AddGradientBorder" }) do
        Theme[name] = function() end
    end
    Theme.PanelBandInset = function() return 3 end
    Theme.PANEL_HEADER_H = 20
    Theme.PANEL_RADIUS = 4
    local color = { 1, 1, 1, 1 }
    Theme.COLOR_POWER, Theme.COLOR_TEXT_WHITE, Theme.COLOR_BG = color, color, color
    Theme.COLOR_HEALTH = { 1, 0.180, 0.592, 1 }
    FS.Theme = Theme
    assert(load(configSrc, "@Config.lua"))("forever-stuwave", FS)
    assert(load(src, "@Professions.lua"))("forever-stuwave", FS)
    Fire("ADDON_LOADED", "forever-stuwave")
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local ALL = { "Alchemy", "Mining", "Herbalism", "Skinning", "Fishing", "Cooking" }

local function boot(opts)
    __session(__professionsSrc, opts, __configSrc)
    Fire("PLAYER_LOGIN")
end
local function panel() return ForeverSTUwaveProfessions end
local function rows()
    local out = {}
    for _, f in ipairs(__frames) do
        if f._kind == "Button" and f._parent == panel() and f._protected then out[#out + 1] = f end
    end
    return out
end
local function glyph()
    for _, f in ipairs(__frames) do
        if f._kind == "Button" and f._parent == panel() and not f._protected then return f end
    end
end
local MIN = "professions.minimized"
local FULL_H, BAND_H = 105, 27   -- the scaled seat height (210 * 0.5); band 3 + 20 + 1 rule + 3
-- Screen y of the panel's top edge, from its one anchor and height (the stub UIParent is the origin).
local function topEdge(p)
    local pt = p._points[1]
    if pt[1] == "TOP" then return pt[5] end
    if pt[1] == "CENTER" then return pt[5] + p._h / 2 end
    error("unexpected anchor " .. tostring(pt[1]))
end
local function pinned(value)
    return { profiles = { Default = { settings = { [MIN] = value }, layout = { v = 1, frames = {} } } },
        profileKeys = {}, profilesVersion = 1 }
end
local function shownRows()
    local n = 0
    for _, r in ipairs(rows()) do if r._shown then n = n + 1 end end
    return n
end
local function clickGlyph() glyph()._scripts.OnClick(glyph()) end
local function hoverGlyph() glyph()._scripts.OnEnter(glyph()) end
local function leaveGlyph() glyph()._scripts.OnLeave(glyph()) end
local function slash() SlashCmdList.FSPROF("") end
local function endCombat() __combat = false; Fire("PLAYER_REGEN_ENABLED") end
local function setProfs(list)
    __slots, __info = {}, {}
    for i, p in ipairs(list) do
        __slots[i] = i
        __info[i] = { p, "icon-" .. p, 10 + i, 75 }
    end
end
local function lastPrinted() return __printed[#__printed] or "" end
local function hover(row) for _, fn in ipairs(row._hooks.OnEnter or {}) do fn(row) end end
local function leave(row) for _, fn in ipairs(row._hooks.OnLeave or {}) do fn(row) end end

function T.rows_are_secure_buttons_registered_for_both_click_edges()
    boot({ profs = { "Alchemy" } })
    local r = rows()
    eq(#r, 6, "six pooled rows")
    for i = 1, 6 do
        eq(r[i]._protected, true, "row " .. i .. " is a SecureActionButtonTemplate button")
        eq(r[i]._clicks, "AnyUp,AnyDown", "row " .. i .. " click registration")
    end
end

function T.a_profession_casts_its_own_name()
    boot({ profs = { "Alchemy", "Cooking", "First Aid" } })
    local r = rows()
    for i, want in ipairs({ "Alchemy", "Cooking", "First Aid" }) do
        eq(r[i]._attrs.type, "spell", want .. " type")
        eq(r[i]._attrs.spell, want, want .. " spell")
        eq(r[i]._shown, true, want .. " row shown")
    end
end

function T.mining_opens_smelting()
    boot({ profs = { "Mining" } })
    eq(rows()[1]._attrs.type, "spell")
    eq(rows()[1]._attrs.spell, "Smelting")
end

function T.gathering_rows_get_no_type_and_no_spell()
    boot({ profs = { "Herbalism", "Skinning", "Fishing" } })
    local r = rows()
    for i, n in ipairs({ "Herbalism", "Skinning", "Fishing" }) do
        eq(r[i]._shown, true, n .. " row still shown")
        eq(r[i]._attrs.type, nil, n .. " has no type")
        eq(r[i]._attrs.spell, nil, n .. " has no spell")
    end
end

function T.a_row_that_changes_profession_rewrites_and_clears_its_attributes()
    boot({ profs = { "Alchemy" } })
    eq(rows()[1]._attrs.spell, "Alchemy")
    setProfs({ "Fishing" })
    Fire("SKILL_LINES_CHANGED")
    eq(rows()[1]._attrs.type, nil, "a gathering skill clears the type")
    eq(rows()[1]._attrs.spell, nil, "and the spell")
    setProfs({ "Mining" })
    Fire("SKILL_LINES_CHANGED")
    eq(rows()[1]._attrs.spell, "Smelting")
end

function T.the_full_mapping_in_one_refresh()
    boot({ profs = ALL })
    local want = { "Alchemy", "Smelting", false, false, false, "Cooking" }
    for i, w in ipairs(want) do
        eq(rows()[i]._attrs.spell, w or nil, "row " .. i)
        eq(rows()[i]._attrs.type, w and "spell" or nil, "row " .. i .. " type")
    end
end

function T.no_secure_call_runs_in_combat_and_the_refresh_replays_after()
    boot({ profs = { "Alchemy", "Cooking" } })
    __combat = true
    setProfs({ "Mining" })
    Fire("SKILL_LINES_CHANGED")
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(rows()[1]._attrs.spell, "Alchemy", "attributes untouched in combat")
    eq(rows()[2]._shown, true, "unlearned row stays shown in combat")
    endCombat()
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(rows()[1]._attrs.spell, "Smelting", "replayed after combat")
    eq(rows()[2]._shown, false, "unlearned row hidden after combat")
end

function T.the_label_and_the_click_never_disagree_in_combat()
    boot({ profs = { "Alchemy" } })
    __combat = true
    setProfs({ "Mining" })
    Fire("SKILL_LINES_CHANGED")
    eq(rows()[1].name._text, "Alchemy", "text waits with the attribute")
    endCombat()
    eq(rows()[1].name._text, "Mining")
end

function T.a_login_in_combat_builds_nothing_until_combat_ends()
    boot({ combatAtLoad = true, profs = { "Alchemy", "Mining" } })
    eq(panel(), nil, "no panel built in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(panel() ~= nil, true, "panel built after combat")
    eq(panel()._shown, true)
    eq(rows()[2]._attrs.spell, "Smelting")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_login_in_combat_still_restores_the_hidden_state_afterwards()
    boot({ combatAtLoad = true, db = { professionsHidden = true }, profs = { "Alchemy" } })
    endCombat()
    eq(panel()._shown, false)
end

function T.fsprof_in_combat_defers_and_prints_it()
    boot({ profs = { "Alchemy" } })
    __combat = true
    slash()
    eq(lastPrinted():find("after combat", 1, true) ~= nil, true, lastPrinted())
    eq(panel()._shown, true, "panel untouched in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(FS.Config.Get("professions.shown"), false, "the choice is saved right away, through Config")
    endCombat()
    eq(panel()._shown, false, "applied after combat")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.fsprof_twice_in_combat_nets_out_to_no_change()
    boot({ profs = { "Alchemy" } })
    __combat = true
    slash()
    slash()
    endCombat()
    eq(panel()._shown, true)
    eq(FS.Config.Get("professions.shown"), true)
end

function T.fsprof_in_combat_shows_a_hidden_panel_after_combat()
    boot({ db = { professionsHidden = true }, profs = { "Alchemy" } })
    eq(panel()._shown, false)
    __combat = true
    slash()
    eq(lastPrinted():find("shown after combat", 1, true) ~= nil, true, lastPrinted())
    endCombat()
    eq(panel()._shown, true)
end

function T.fsprof_out_of_combat_still_toggles_immediately()
    boot({ profs = { "Alchemy" } })
    slash()
    eq(panel()._shown, false)
    eq(lastPrinted():find("hidden", 1, true) ~= nil, true, lastPrinted())
    slash()
    eq(panel()._shown, true)
    eq(lastPrinted():find("shown", 1, true) ~= nil, true, lastPrinted())
    eq(#__violations, 0)
end

function T.the_saved_hidden_state_is_restored_at_login()
    boot({ db = { professionsHidden = true }, profs = { "Alchemy" } })
    eq(panel()._shown, false)
end

function T.the_panel_shows_at_login_when_nothing_is_saved()
    boot({ profs = { "Alchemy" } })
    eq(panel()._shown, true)
end

function T.a_later_loading_screen_does_not_undo_a_manual_toggle()
    boot({ db = { professionsHidden = true }, profs = { "Alchemy" } })
    slash()
    eq(panel()._shown, true)
    Fire("PLAYER_ENTERING_WORLD")
    eq(panel()._shown, true)
end

function T.the_tooltip_names_the_profession_and_offers_the_click()
    boot({ profs = { "Alchemy" } })
    local row = rows()[1]
    hover(row)
    eq(__tip.shown, true)
    eq(__tip.lines[1], "Alchemy")
    eq(__tip.lines[2], "Click to open")
    leave(row)
    eq(__tip.shown, false)
end

function T.a_gathering_row_tooltip_has_no_click_line()
    boot({ profs = { "Fishing" } })
    hover(rows()[1])
    eq(__tip.lines[1], "Fishing")
    eq(__tip.lines[2], nil)
end

function T.only_the_allowlisted_names_are_clickable()
    local names = { "Alchemy", "Blacksmithing", "Enchanting", "Engineering", "Leatherworking", "Tailoring" }
    boot({ profs = names })
    for i, n in ipairs(names) do eq(rows()[i]._attrs.spell, n, n) end
    local more = { "Cooking", "First Aid", "Jewelcrafting", "Inscription" }
    setProfs(more)
    Fire("SKILL_LINES_CHANGED")
    for i, n in ipairs(more) do eq(rows()[i]._attrs.spell, n, n) end
end

function T.unknown_localized_and_archaeology_names_get_no_click_and_no_click_line()
    local names = { "Archaeology", "Kr\195\164uterkunde", "Fischen", "Made Up" }
    boot({ profs = names })
    for i, n in ipairs(names) do
        local row = rows()[i]
        eq(row._shown, true, n .. " row shown")
        eq(row._attrs.type, nil, n .. " type")
        eq(row._attrs.spell, nil, n .. " spell")
        hover(row)
        eq(__tip.lines[1], n, n .. " tooltip name")
        eq(__tip.lines[2], nil, n .. " has no click line")
    end
end

function T.the_combat_paths_make_no_geometry_or_layout_call_on_protected_frames()
    boot({ profs = { "Alchemy", "Mining" } })
    local applied = __layoutApplied
    eq(applied >= 1, true, "layout applied at the out-of-combat build")
    __combat = true
    setProfs({ "Cooking" })
    Fire("SKILL_LINES_CHANGED")
    Fire("PLAYER_ENTERING_WORLD")
    slash()
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(__layoutApplied, applied, "no layout call in combat")
    endCombat()
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_login_in_combat_applies_the_layout_only_on_the_regen_replay()
    boot({ combatAtLoad = true, profs = { "Alchemy" } })
    eq(__layoutApplied, 0, "not in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(__layoutApplied, 1, "on the replay")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.entering_world_in_combat_parks_one_setup_for_the_regen()
    boot({ profs = { "Alchemy" } })
    __profCalls = 0
    __combat = true
    setProfs({ "Mining" })
    Fire("PLAYER_ENTERING_WORLD")
    eq(__profCalls, 0, "nothing runs in combat")
    eq(rows()[1]._attrs.spell, "Alchemy")
    endCombat()
    eq(__profCalls, 1, "Setup re-ran once")
    eq(rows()[1]._attrs.spell, "Smelting")
    Fire("PLAYER_REGEN_ENABLED")
    eq(__profCalls, 1, "and is not replayed again")
end

-- ---- visibility is the profile setting professions.shown --------------------------------------------

local KEY = "professions.shown"
local function stored(key) return ForeverSTUwaveDB.profiles.Default.settings[key or KEY] end

function T.visibility_is_a_profile_setting_that_defaults_to_shown()
    boot({ profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), true, "default true")
    eq(FS.Config.IsStored(KEY), false, "the default pins nothing")
    eq(panel()._shown, true)
end

function T.a_config_change_shows_and_hides_the_panel()
    boot({ profs = { "Alchemy" } })
    FS.Config.Set(KEY, false)
    eq(panel()._shown, false, "hidden through Config")
    FS.Config.Set(KEY, true)
    eq(panel()._shown, true, "shown through Config")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_config_change_in_combat_takes_the_same_deferral_as_fsprof()
    boot({ profs = { "Alchemy" } })
    __combat = true
    FS.Config.Set(KEY, false)
    eq(panel()._shown, true, "panel untouched in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(panel()._shown, false, "applied after combat")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.config_changes_in_combat_net_out_and_the_latest_wins()
    boot({ profs = { "Alchemy" } })
    __combat = true
    FS.Config.Set(KEY, false)
    FS.Config.Set(KEY, true)
    endCombat()
    eq(panel()._shown, true)
    __combat = true
    FS.Config.Set(KEY, false)
    slash()                      -- /fsprof reads the parked request: it was going to hide, so this shows
    eq(FS.Config.Get(KEY), true)
    endCombat()
    eq(panel()._shown, true)
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_profile_switch_moves_the_panel_and_defers_in_combat()
    boot({ profs = { "Alchemy" } })
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set(KEY, false)
    eq(panel()._shown, false)
    __combat = true
    FS.Config.SetActiveProfile("Default")
    eq(panel()._shown, false, "no Show in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(panel()._shown, true, "Default shows it after combat")
    FS.Config.SetActiveProfile("Raid")
    eq(panel()._shown, false, "out of combat the switch applies at once")
end

function T.fsprof_writes_through_config_and_leaves_the_legacy_field_alone()
    boot({ profs = { "Alchemy" } })
    slash()
    eq(FS.Config.Get(KEY), false)
    eq(stored(), false, "pinned in the active profile")
    eq(ForeverSTUwaveDB.professionsHidden, nil, "nothing written to the legacy field")
    slash()
    eq(FS.Config.Get(KEY), true)
    eq(stored(), nil, "back to the default pins nothing")
end

function T.fsprof_follows_a_config_change_made_elsewhere()
    boot({ profs = { "Alchemy" } })
    FS.Config.Set(KEY, false)
    slash()
    eq(panel()._shown, true, "the toggle starts from the live state")
    eq(FS.Config.Get(KEY), true)
end

function T.a_read_only_config_refuses_the_toggle_and_says_so()
    boot({ db = { profilesVersion = 99 }, profs = { "Alchemy" } })
    eq(FS.Config.IsReadOnly(), true)
    slash()
    eq(panel()._shown, true, "the panel did not change")
    eq(lastPrinted():lower():find("read-only", 1, true) ~= nil, true, lastPrinted())
end

function T.the_legacy_hidden_flag_migrates_into_the_active_profile_once()
    boot({ db = { professionsHidden = true }, profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), false)
    eq(stored(), false, "pinned in Default")
    eq(ForeverSTUwaveDB.professionsHidden, nil, "the legacy field is cleared")
    eq(panel()._shown, false)
    -- the player turns it back on; the next load must not import anything again
    FS.Config.Set(KEY, true)
    boot({ db = ForeverSTUwaveDB, profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), true, "no second migration")
    eq(panel()._shown, true)
end

function T.a_legacy_shown_flag_migrates_to_the_default_and_is_cleared()
    boot({ db = { professionsHidden = false }, profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), true)
    eq(stored(), nil, "shown is the default, nothing is pinned")
    eq(ForeverSTUwaveDB.professionsHidden, nil)
end

function T.migration_never_overwrites_a_value_the_profile_already_pins()
    local db = {
        professionsHidden = false,
        profiles = { Default = { settings = { [KEY] = false }, layout = { v = 1, frames = {} } } },
        profileKeys = {}, profilesVersion = 1,
    }
    boot({ db = db, profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), false, "the pinned value wins over the legacy shown flag")
    eq(db.professionsHidden, nil, "and the legacy field is still cleared")
    eq(panel()._shown, false)
end

function T.migration_waits_while_config_is_read_only_and_keeps_the_legacy_flag()
    local db = { professionsHidden = true, profilesVersion = 99 }
    boot({ db = db, profs = { "Alchemy" } })
    eq(FS.Config.IsReadOnly(), true)
    eq(db.professionsHidden, true, "kept for a later session")
    eq(panel()._shown, true, "defaults apply in read-only")
end

function T.a_login_in_combat_migrates_without_touching_the_panel()
    boot({ combatAtLoad = true, db = { professionsHidden = true }, profs = { "Alchemy" } })
    eq(FS.Config.Get(KEY), false, "migrated at login")
    eq(ForeverSTUwaveDB.professionsHidden, nil)
    eq(panel(), nil, "no panel in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(panel()._shown, false)
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_config_change_before_the_panel_exists_is_read_at_setup()
    boot({ combatAtLoad = true, profs = { "Alchemy" } })
    FS.Config.Set(KEY, false)
    eq(panel(), nil, "still nothing built in combat")
    endCombat()
    eq(panel()._shown, false, "Setup reads the setting")
    eq(#__violations, 0, table.concat(__violations, ","))
end

-- ---- the minimise glyph (professions.minimized) -------------------------------------------------------

function T.the_glyph_is_a_plain_button_with_the_chat_minimise_texture_and_alphas()
    boot({ profs = { "Alchemy" } })
    local g = glyph()
    eq(g ~= nil, true, "a glyph button exists")
    eq(g._protected, false, "plain, non-secure")
    eq(g._clicks, "LeftButtonUp")
    eq(g.icon._texture, "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\icon_minimize.tga")
    eq(g._points[1][1], "RIGHT", "right end of the title band")
    eq(g._points[1][2]._kind, "Texture", "anchored to the band")
    eq(g._points[1][4], -4, "the chat's 4 px edge gap")
    eq(g._w, 16)
    eq(g._h, 16)
    eq(g.icon._vc[1], 1)
    eq(g.icon._vc[2], 0.180)
    eq(g.icon._vc[4], 0.85, "quiet at rest")
    hoverGlyph()
    eq(g.icon._vc[4], 1.00, "full on hover")
    leaveGlyph()
    eq(g.icon._vc[4], 0.85, "quiet again after leaving")
end

function T.the_glyph_tooltip_reads_minimise_then_restore()
    boot({ profs = { "Alchemy" } })
    hoverGlyph()
    eq(__tip.shown, true)
    eq(__tip.owner, glyph())
    eq(__tip.lines[1], "Minimise")
    leaveGlyph()
    eq(__tip.shown, false)
    clickGlyph()
    hoverGlyph()
    eq(__tip.lines[1], "Restore")
end

function T.a_click_while_hovering_refreshes_the_open_tooltip()
    boot({ profs = { "Alchemy" } })
    hoverGlyph()
    clickGlyph()
    eq(__tip.lines[1], "Restore")
    clickGlyph()
    eq(__tip.lines[1], "Minimise")
end

function T.the_tooltip_uses_the_chat_placement_helper_when_it_exists()
    boot({ chatPlace = true, profs = { "Alchemy" } })
    hoverGlyph()
    eq(__placed, glyph())
    eq(__tip.anchor, "ANCHOR_NONE")
end

function T.the_tooltip_falls_back_to_a_standard_anchor_without_the_chat()
    boot({ profs = { "Alchemy" } })
    hoverGlyph()
    eq(__tip.anchor, "ANCHOR_TOPRIGHT")
end

function T.minimised_defaults_to_false_and_pins_nothing()
    boot({ profs = { "Alchemy", "Cooking" } })
    eq(FS.Config.Get(MIN), false)
    eq(FS.Config.IsStored(MIN), false)
    eq(panel()._h, FULL_H)
    eq(shownRows(), 2)
end

function T.a_click_folds_the_rows_into_the_band_and_keeps_the_top_edge()
    boot({ profs = { "Alchemy", "Cooking", "Mining" } })
    local top, left = topEdge(panel()), panel()._points[1][4]
    clickGlyph()
    eq(shownRows(), 0, "every row hidden")
    eq(panel()._h, BAND_H, "height is the title band")
    eq(topEdge(panel()), top, "top edge did not move")
    eq(panel()._points[1][4], left, "nor did the horizontal seat")
    eq(#panel()._points, 1, "one anchor")
    eq(panel()._shown, true, "the band itself stays up")
    eq(FS.Config.Get(MIN), true)
    eq(stored(MIN), true, "saved in the active profile")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_second_click_restores_the_full_list()
    boot({ profs = { "Alchemy", "Cooking", "Mining" } })
    local top = topEdge(panel())
    clickGlyph()
    clickGlyph()
    eq(shownRows(), 3, "the learned rows are back")
    eq(rows()[4]._shown, false, "unlearned rows stay hidden")
    eq(panel()._h, FULL_H)
    eq(topEdge(panel()), top)
    eq(panel()._points[1][1], "CENTER", "the layout seat is back")
    eq(FS.Config.Get(MIN), false)
    eq(stored(MIN), nil, "the default pins nothing")
    eq(rows()[1]._attrs.spell, "Alchemy", "the click action survived the fold")
end

function T.the_stored_state_is_applied_on_load()
    boot({ db = pinned(true), profs = { "Alchemy", "Cooking" } })
    eq(shownRows(), 0)
    eq(panel()._h, BAND_H)
    eq(panel()._shown, true)
    hoverGlyph()
    eq(__tip.lines[1], "Restore")
end

function T.the_state_survives_a_reload()
    boot({ profs = { "Alchemy" } })
    clickGlyph()
    boot({ db = ForeverSTUwaveDB, profs = { "Alchemy" } })
    eq(FS.Config.Get(MIN), true)
    eq(shownRows(), 0)
    eq(panel()._h, BAND_H)
end

function T.a_minimised_panel_builds_with_a_single_layout_apply()
    boot({ db = pinned(true), profs = { "Alchemy" } })
    eq(__layoutApplied, 1)
end

function T.a_skill_refresh_does_not_reopen_a_minimised_panel()
    boot({ profs = { "Alchemy" } })
    clickGlyph()
    setProfs({ "Mining", "Cooking" })
    Fire("SKILL_LINES_CHANGED")
    eq(shownRows(), 0, "still folded")
    eq(rows()[1].name._text, "Mining", "but the rows track the skills")
    clickGlyph()
    eq(shownRows(), 2)
    eq(rows()[1]._attrs.spell, "Smelting")
end

function T.fsprof_hide_and_show_keeps_the_minimised_state()
    boot({ profs = { "Alchemy", "Cooking" } })
    clickGlyph()
    slash()
    eq(panel()._shown, false)
    slash()
    eq(panel()._shown, true)
    eq(shownRows(), 0)
    eq(panel()._h, BAND_H)
    eq(FS.Config.Get(MIN), true)
end

function T.minimising_a_hidden_panel_applies_when_it_is_shown()
    boot({ profs = { "Alchemy" } })
    slash()
    FS.Config.Set(MIN, true)
    eq(panel()._shown, false)
    slash()
    eq(panel()._shown, true)
    eq(panel()._h, BAND_H)
    eq(shownRows(), 0)
end

function T.a_click_in_combat_defers_everything_and_says_so()
    boot({ profs = { "Alchemy", "Cooking" } })
    __combat = true
    clickGlyph()
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(shownRows(), 2, "rows untouched in combat")
    eq(panel()._h, FULL_H, "no resize in combat")
    eq(panel()._points[1][1], "CENTER", "no re-anchor in combat")
    eq(lastPrinted():find("after combat", 1, true) ~= nil, true, lastPrinted())
    endCombat()
    eq(shownRows(), 0, "folded when combat ends")
    eq(panel()._h, BAND_H)
    eq(panel()._points[1][1], "TOP")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_restore_click_in_combat_waits_for_regen_too()
    boot({ db = pinned(true), profs = { "Alchemy", "Cooking" } })
    __combat = true
    clickGlyph()
    eq(shownRows(), 0)
    eq(panel()._h, BAND_H)
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(shownRows(), 2)
    eq(panel()._h, FULL_H)
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.clicks_in_combat_net_out_to_the_latest()
    boot({ profs = { "Alchemy" } })
    __combat = true
    clickGlyph()
    clickGlyph()
    endCombat()
    eq(shownRows(), 1)
    eq(panel()._h, FULL_H)
    eq(FS.Config.Get(MIN), false)
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_login_in_combat_builds_minimised_after_combat()
    boot({ combatAtLoad = true, db = pinned(true), profs = { "Alchemy" } })
    eq(panel(), nil)
    endCombat()
    eq(shownRows(), 0)
    eq(panel()._h, BAND_H)
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.a_reseat_keeps_a_minimised_panel_folded_on_its_top_edge()
    boot({ profs = { "Alchemy" } })
    local top = topEdge(panel())
    clickGlyph()
    FS.Layout.Apply(panel(), "professions")   -- what the rescale watcher and /fsedit do first
    eq(panel()._h, FULL_H, "the reseat alone restores the seat height")
    for _, fn in ipairs(__rescale) do fn() end
    eq(panel()._h, BAND_H, "the rescale callback folds it again")
    eq(topEdge(panel()), top)
end

function T.a_reseat_after_dragging_moves_the_folded_panel_with_its_seat()
    boot({ db = pinned(true), profs = { "Alchemy" } })
    FS.Layout.professions.x = FS.Layout.professions.x - 100
    FS.Layout.professions.y = FS.Layout.professions.y + 40
    FS.Layout.Apply(panel(), "professions")
    for _, fn in ipairs(__rescale) do fn() end
    eq(panel()._points[1][1], "TOP")
    eq(panel()._points[1][4], (923 - 100) * 0.5)
    eq(topEdge(panel()), (-450 + 40 + 105) * 0.5, "top of the full seat, not its centre")
end

function T.a_rescale_in_combat_touches_nothing_and_the_regen_refolds()
    boot({ db = pinned(true), profs = { "Alchemy" } })
    __combat = true
    local applied = __layoutApplied
    for _, fn in ipairs(__rescale) do fn() end
    eq(#__violations, 0, table.concat(__violations, ","))
    eq(__layoutApplied, applied, "no layout call in combat")
    endCombat()
    eq(__layoutApplied, applied + 1, "the regen re-seated and refolded the parked change")
    eq(panel()._h, BAND_H)
    FS.Layout.Apply(panel(), "professions")   -- the watcher's own regen pass, then the callbacks
    for _, fn in ipairs(__rescale) do fn() end
    eq(panel()._h, BAND_H)
    eq(topEdge(panel()), (-450 + 105) * 0.5, "top of the full seat")
    eq(#__violations, 0, table.concat(__violations, ","))
end

function T.only_the_first_parked_click_in_a_fight_prints()
    boot({ profs = { "Alchemy" } })
    __combat = true
    clickGlyph()
    local first = #__printed
    eq(first >= 1, true, "the first parked click says so")
    clickGlyph()
    eq(#__printed, first, "the second stays quiet")
    eq(lastPrinted():find("after combat", 1, true) ~= nil, true, lastPrinted())
end

function T.a_profile_switch_carries_each_profile_its_own_state()
    boot({ profs = { "Alchemy" } })
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    clickGlyph()
    eq(panel()._h, BAND_H)
    FS.Config.SetActiveProfile("Default")
    eq(panel()._h, FULL_H, "Default is open")
    eq(shownRows(), 1)
    FS.Config.SetActiveProfile("Raid")
    eq(panel()._h, BAND_H, "Raid is folded")
    eq(shownRows(), 0)
end

function T.a_profile_switch_in_combat_waits_for_regen()
    boot({ db = pinned(true), profs = { "Alchemy" } })
    FS.Config.NewProfile("Raid")
    __combat = true
    FS.Config.SetActiveProfile("Raid")
    eq(panel()._h, BAND_H, "untouched in combat")
    eq(#__violations, 0, table.concat(__violations, ","))
    endCombat()
    eq(panel()._h, FULL_H)
    eq(shownRows(), 1)
end

function T.a_read_only_config_refuses_the_click_and_says_so()
    boot({ db = { profilesVersion = 99 }, profs = { "Alchemy" } })
    clickGlyph()
    eq(shownRows(), 1)
    eq(panel()._h, FULL_H)
    eq(lastPrinted():lower():find("read-only", 1, true) ~= nil, true, lastPrinted())
end

-- The harness's model of SecureActionButton_OnClick: the action runs on the one edge picked by the
-- button's useOnKeyDown attribute (nil follows the ActionButtonUseKeyDown CVar), and only for an edge
-- the button registered for. OnClick must not be overridden, or the secure handler never runs.
local function click(row, cvarDown)
    local registered = row._clicks or ""
    local useDown = row._attrs.useOnKeyDown
    if useDown == nil then useDown = cvarDown end
    local casts = 0
    for _, down in ipairs({ true, false }) do
        local edge = down and "AnyDown" or "AnyUp"
        if registered:find(edge, 1, true) and down == useDown and row._attrs.type == "spell" then
            casts = casts + 1
        end
    end
    return casts
end

function T.one_click_casts_exactly_once_on_either_edge_setting()
    boot({ profs = { "Alchemy", "Fishing" } })
    local row = rows()[1]
    eq(row._scripts.OnClick, nil, "OnClick is not overridden")
    for _, useAttr in ipairs({ "nil", "true", "false" }) do
        for _, cvar in ipairs({ true, false }) do
            row._attrs.useOnKeyDown = ({ ["nil"] = nil, ["true"] = true, ["false"] = false })[useAttr]
            eq(click(row, cvar), 1, "useOnKeyDown=" .. useAttr .. " cvar=" .. tostring(cvar))
        end
    end
    row._attrs.useOnKeyDown = nil
    eq(click(rows()[2], true), 0, "a no-window row never casts")
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__session = lua.eval(SESSION)
    lua.globals().__professionsSrc = PROFESSIONS_FILE.read_text(encoding="utf-8")
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
