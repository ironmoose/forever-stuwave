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
  * the tooltip names the profession and adds "Click to open" only on a clickable row.

Professions.lua is the real file; the frames are a recording mock that refuses protected calls in
combat the way the client does, and Theme / PanelSkins are stubs. This is NOT the real client.

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
        _attrs = {}, _clicks = nil, _shown = true, _text = nil,
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

local function locked(self) return __combat and (self._protected or self._hasProtectedChild) end
local function refuse(self, what)
    __violations[#__violations + 1] = what .. ":" .. tostring(self._name or self._kind)
end
function Frame.SetAttribute(self, k, v)
    if locked(self) then return refuse(self, "SetAttribute") end
    self._attrs[k] = v
end
for _, m in ipairs({ "SetPoint", "ClearAllPoints", "SetSize", "SetParent" }) do
    Frame[m] = function(self)
        if locked(self) then return refuse(self, m) end
    end
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
function print(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[i] = tostring((select(i, ...))) end
    __printed[#__printed + 1] = table.concat(parts, " ")
end
SlashCmdList = {}

__tip = {}
GameTooltip = {
    SetOwner = function(self, owner) __tip = { owner = owner, lines = {}, shown = false }; self._owner = owner end,
    SetText = function(_, t) __tip.lines[#__tip.lines + 1] = t end,
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
function(src, opts)
    opts = opts or {}
    __frames, __printed, __violations, __profCalls = {}, {}, {}, 0
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
    FS.Layout = { Apply = function(frame)
        __layoutApplied = __layoutApplied + 1
        if __combat then __violations[#__violations + 1] = "Layout.Apply" end
    end }
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
    FS.Theme = Theme
    assert(load(src, "@Professions.lua"))("forever-stuwave", FS)
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end

local ALL = { "Alchemy", "Mining", "Herbalism", "Skinning", "Fishing", "Cooking" }

local function boot(opts)
    __session(__professionsSrc, opts)
    Fire("PLAYER_LOGIN")
end
local function panel() return ForeverSTUwaveProfessions end
local function rows()
    local out = {}
    for _, f in ipairs(__frames) do
        if f._kind == "Button" and f._parent == panel() then out[#out + 1] = f end
    end
    return out
end
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
    eq(ForeverSTUwaveDB.professionsHidden, true, "the choice is saved right away")
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
    eq(ForeverSTUwaveDB.professionsHidden, false)
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
