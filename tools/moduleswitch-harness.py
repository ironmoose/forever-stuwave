#!/usr/bin/env python3
"""Module power (ticket B5): the switch store, the load gate API and the power buttons in the /fsconfig nav.

Runs the real Core/ModuleSwitch.lua, Core/Config.lua and every Modules/Config/Config*.lua headless in the mock frame
tree of tools/configwindow-harness.py (not the client). The checks pin:

  * Register / On / Wanted / WhenOn / Built / MarkBuilt / Set, and the 16 keys, labels, pages and live flags equal the
    prototype (mockups/proto-src-2026-11-25/proto-pages.js: NAV entries with `m`, the Modules page rows)
  * WhenOn runs at this addon's ADDON_LOADED (after SavedVariables, before PLAYER_LOGIN), once, only for a module that is
    on; a late call runs at once; a throwing gate is forwarded and the others still run
  * Set writes the account wide store (ForeverSTUwaveDB.modules, off stored as false, on as nothing); a normal module
    marks a reload pending until the switch is turned back, a live one applies at once and calls its change callbacks
  * requires: turning one off turns its dependents off, turning one on pulls its requirements in; ALL ON turns every
    switch back on; a profile switch, copy or reset never touches the store
  * every module page of the nav gets a power button (PWR x PWR from the SPEC, PWR_R from the nav item edge), the pages
    without a module get none; pink glyph on, dim off, cyan on hover; the nav text mutes when off
  * an off module shows the off card on its page with the prototype's wording; its big button turns the module back on
  * a changed switch that needs a reload marks the list row, the Modules nav item and the registry (entry.reload); turning
    it back clears all three
  * turning off a module another module requires asks once, naming it, and a ? on the power button names the dependents
  * the Profiles Modules section's ALL ON button, read-only settings, the changed dot and reset of a list row

The glyph art and the card are pending the owner's review; this proves behaviour, not looks.

    python3 tools/moduleswitch-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ADDON = ROOT / "forever-stuwave"
MOCKUPS = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))

spec = importlib.util.spec_from_file_location("configwindow_harness", HERE / "configwindow-harness.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
LuaError = base.LuaError

MS_FILE = ADDON / "Core" / "ModuleSwitch.lua"
MODULES_FILE = ADDON / "Modules" / "Config" / "ConfigModules.lua"


# ---- the prototype's module list --------------------------------------------------------------------------------------

def proto_modules() -> dict:
    """The Modules page rows and the NAV entries that carry a power button, from the prototype source."""
    src = (MOCKUPS / "proto-src-2026-11-25" / "proto-pages.js").read_text(encoding="utf-8")
    page = src.split(" {key:'modules'", 1)[1].split("\n];", 1)[0]
    rows = re.findall(r"\{ty:'sw',k:'(m\.[a-z]+)',l:'([^']*)',d:true(,reload:1)?\}", page)
    nav_text = src.split("const NAV=[", 1)[1].split("NAV.forEach", 1)[0]
    nav = re.findall(r"\{k:'([a-z]+)',l:'([^']*)',m:'(m\.[a-z]+)'\}", nav_text)
    return {
        "modules": [{"key": k, "label": label, "reload": bool(reload)} for k, label, reload in rows],
        "nav": [{"page": p, "label": label, "m": m} for p, label, m in nav],
    }


# ---- Lua checks -------------------------------------------------------------------------------------------------------

CHECKS = r"""
-- Loads Core/ModuleSwitch.lua between Config.lua and the window files, as the .toc does.
local function msboot(opts)
    opts = opts or {}
    local pre = opts.preWindow
    opts.preWindow = function()
        assert(load(__msSrc, "@ModuleSwitch.lua"))("forever-stuwave", FS)
        if pre then pre() end
    end
    return boot(opts)
end
local function MS() return FS.ModuleSwitch end
local function near(a, b) return math.abs(a - b) < 0.001 end
local function sameColor(c, want) return c and near(c[1], want[1]) and near(c[2], want[2]) and near(c[3], want[3]) end
local function navButton(W, page)
    for _, r in ipairs(W.NavRows()) do if r.key == page then return r.button end end
end
local function glyphColor(button)
    return button.fsGlyph.textures[1].color
end
local function press(button) button.scripts.OnClick(button, "LeftButton") end
local function hover(button, on)
    local fn = button.scripts[on and "OnEnter" or "OnLeave"]
    if fn then fn(button) end
end
local function visibleText(text, root)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and o:GetText() == text and (root == nil or under(root, o)) then return o end
    end
end
local function anyText(needle)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and o:GetText():find(needle, 1, true) then return o end
    end
end
local function dialogText()
    local d = _G.ForeverSTUwaveConfigDialog
    if not (d and d:IsVisible()) then return nil end
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and under(d, o) and o:GetText():find("Turning off", 1, true) then return o:GetText() end
    end
end
local function confirmDialog()
    local d = _G.ForeverSTUwaveConfigDialog
    eq(d ~= nil and d:IsVisible(), true, "the confirm is open")
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and under(d, o) and o:GetText() == "Confirm" then
            local b = owner(o)
            b.scripts.OnClick(b, "LeftButton")
            return
        end
    end
    error("no Confirm button")
end
local function errorsClean() eq(#__errors, 0, "no error forwarded: " .. table.concat(__errors, " | ")) end

-- ---- core ---------------------------------------------------------------------------------------------------------

function T.the_sixteen_keys_labels_pages_and_live_flags_equal_the_prototype()
    msboot()
    local keys = MS().Keys()
    eq(#PROTO.modules, 16, "the prototype lists sixteen modules")
    eq(#keys, 16, "ModuleSwitch registers sixteen")
    for i, m in ipairs(PROTO.modules) do
        eq(keys[i], m.key, "order at " .. i)
        eq(MS().Label(m.key), m.label, m.key .. " label")
        eq(MS().IsLive(m.key), not m.reload, m.key .. " live flag (only Nameplates turns off at once)")
        eq(MS().On(m.key), true, m.key .. " defaults on")
    end
    for _, n in ipairs(PROTO.nav) do eq(MS().Page(n.m), n.page, n.m .. " page") end
    eq(#PROTO.nav, 16, "sixteen nav entries carry a power button")
end

function T.before_the_addon_loads_every_switch_answers_on_and_nothing_is_written()
    msboot({ noLogin = true })
    eq(MS().Loaded(), false)
    eq(MS().On("m.cast"), true); eq(MS().Wanted("m.cast"), true)
    eq(MS().IsWritable(), false, "no writes before the saved variables are in")
    local ok = MS().Set("m.cast", false)
    eq(ok, false)
end

function T.a_saved_off_switch_is_off_for_the_session_and_in_the_store()
    msboot({ db = { modules = { ["m.cast"] = false, ["m.mini"] = false } } })
    eq(MS().Loaded(), true)
    eq(MS().On("m.cast"), false); eq(MS().Wanted("m.cast"), false)
    eq(MS().On("m.mini"), false)
    eq(MS().On("m.uf"), true)
    eq(MS().Pending("m.cast"), false, "off at load and still off: nothing waits")
    eq(MS().PendingCount(), 0)
end

function T.bad_saved_values_fail_open()
    msboot({ db = { modules = { ["m.cast"] = "no", ["m.mini"] = 0, ["m.bags"] = false } } })
    eq(MS().On("m.cast"), true, "only the value false turns a module off")
    eq(MS().On("m.mini"), true)
    eq(MS().On("m.bags"), false)
    msboot({ db = { modules = "garbage" } })
    eq(MS().On("m.bags"), true, "a store that is not a table reads as all on")
    yes(MS().Set("m.bags", false), "and is replaced on the first write")
    eq(type(ForeverSTUwaveDB.modules), "table")
    eq(ForeverSTUwaveDB.modules["m.bags"], false)
end

function T.when_on_runs_at_addon_loaded_after_saved_variables_and_before_login()
    local order, seen = {}, {}
    msboot({
        noLogin = true,
        db = { modules = { ["m.mini"] = false } },
        beforeLogin = function()
            MS().WhenOn("m.cast", function() order[#order + 1] = "cast"; seen.cast = MS().On("m.cast") end)
            MS().WhenOn("m.mini", function() order[#order + 1] = "mini" end)
            MS().WhenOn("m.bags", function() order[#order + 1] = "bags" end)
            local f = CreateFrame("Frame")
            f:RegisterEvent("PLAYER_LOGIN")
            f:SetScript("OnEvent", function() order[#order + 1] = "login" end)
        end,
    })
    eq(#order, 0, "nothing runs while the files load")
    Fire("ADDON_LOADED", "some-other-addon")
    eq(#order, 0, "another addon's ADDON_LOADED does not open the gate")
    Fire("ADDON_LOADED", "forever-stuwave")
    eq(table.concat(order, ","), "cast,bags", "in call order, the off module skipped, all before PLAYER_LOGIN")
    eq(seen.cast, true, "On answers the saved value inside the gate")
    Fire("PLAYER_LOGIN")
    eq(table.concat(order, ","), "cast,bags,login")
    Fire("ADDON_LOADED", "forever-stuwave")
    eq(table.concat(order, ","), "cast,bags,login", "once")
    errorsClean()
end

function T.a_late_when_on_call_runs_at_once_for_an_on_module_and_never_for_an_off_one()
    msboot({ db = { modules = { ["m.mini"] = false } } })
    local ran = {}
    MS().WhenOn("m.cast", function() ran[#ran + 1] = "cast" end)
    MS().WhenOn("m.mini", function() ran[#ran + 1] = "mini" end)
    eq(table.concat(ran, ","), "cast")
    no(MS().WhenOn("m.cast", "nope"), "a gate must be a function")
end

function T.a_throwing_gate_is_forwarded_and_the_others_still_run()
    local ran = {}
    msboot({
        noLogin = true,
        beforeLogin = function()
            MS().WhenOn("m.cast", function() error("boom") end)
            MS().WhenOn("m.bags", function() ran[#ran + 1] = "bags" end)
            MS().WhenOn("m.nope", function() ran[#ran + 1] = "nope" end)
        end,
    })
    Fire("ADDON_LOADED", "forever-stuwave")
    eq(table.concat(ran, ","), "bags,nope", "the later gates ran; an unknown key fails open")
    local text = table.concat(__errors, " | ")
    yes(text:find("boom", 1, true), "the throw was forwarded: " .. text)
    yes(text:find("m.nope", 1, true), "the unknown key was named: " .. text)
end

function T.set_writes_the_store_and_marks_a_reload_for_a_normal_module()
    msboot()
    eq(MS().Pending("m.cast"), false)
    yes(MS().Set("m.cast", false))
    eq(ForeverSTUwaveDB.modules["m.cast"], false, "off is stored as false")
    eq(MS().Wanted("m.cast"), false)
    eq(MS().On("m.cast"), true, "the session value does not move until a reload")
    eq(MS().Pending("m.cast"), true)
    eq(MS().PendingCount(), 1)
    eq(table.concat(MS().PendingKeys(), ","), "m.cast")
    yes(MS().Set("m.mini", false))
    eq(table.concat(MS().PendingKeys(), ","), "m.cast,m.mini", "in registration order")
end

function T.turning_a_switch_back_before_the_reload_clears_the_pending_mark()
    msboot()
    MS().Set("m.cast", false)
    MS().Set("m.cast", true)
    eq(ForeverSTUwaveDB.modules["m.cast"], nil, "on is stored as nothing")
    eq(MS().Pending("m.cast"), false)
    eq(MS().PendingCount(), 0)
    -- off at load, turned on now: it waits for a reload to be built
    msboot({ db = { modules = { ["m.cast"] = false } } })
    MS().Set("m.cast", true)
    eq(MS().On("m.cast"), false); eq(MS().Pending("m.cast"), true)
    MS().Set("m.cast", false)
    eq(MS().Pending("m.cast"), false)
end

function T.a_live_module_applies_at_once_and_calls_its_change_callbacks()
    msboot()
    local log, any = {}, {}
    MS().OnChange("m.np", function(new, old, key) log[#log + 1] = tostring(new) .. "/" .. tostring(old) .. "/" .. key end)
    MS().OnAnyChange(function(key, new, old) any[#any + 1] = key .. "=" .. tostring(new) end)
    yes(MS().Set("m.np", false))
    eq(MS().On("m.np"), false, "a live module's session value follows the store")
    eq(MS().Pending("m.np"), false, "and never waits for a reload")
    eq(MS().PendingCount(), 0)
    eq(table.concat(log, ","), "false/true/m.np")
    yes(MS().Set("m.np", false), "setting the same value is not an error")
    eq(#log, 1, "and calls nothing")
    MS().Set("m.cast", false)
    eq(table.concat(any, ","), "m.np=false,m.cast=false", "the any callback sees every change")
    errorsClean()
end

function T.a_throwing_change_callback_is_forwarded_and_does_not_block_the_write()
    msboot()
    MS().OnChange("m.cast", function() error("cb boom") end)
    local seen
    MS().OnAnyChange(function(key) seen = key end)
    yes(MS().Set("m.cast", false))
    eq(seen, "m.cast", "the next callback still ran")
    yes(table.concat(__errors, " "):find("cb boom", 1, true))
end

function T.set_refuses_unknown_keys_bad_values_and_read_only_settings()
    msboot()
    local ok, why = MS().Set("m.nope", false)
    eq(ok, false); yes(why and why ~= "")
    ok = MS().Set("m.cast", "off")
    eq(ok, false, "the value must be a boolean")
    eq(MS().Wanted("m.cast"), true)
    -- unreadable saved settings: read-only
    msboot({ db = { profilesVersion = 99 } })
    eq(FS.Config.IsReadOnly(), true)
    eq(MS().IsWritable(), false)
    ok, why = MS().Set("m.cast", false)
    eq(ok, false); yes(why:find("read-only", 1, true))
    eq(ForeverSTUwaveDB.modules, nil, "nothing was written")
end

function T.built_follows_mark_built()
    msboot()
    eq(MS().Built("m.cast"), false)
    MS().MarkBuilt("m.cast")
    eq(MS().Built("m.cast"), true)
    eq(MS().Built("m.mini"), false)
end

function T.requires_and_dependents_cascade_both_ways()
    msboot()
    yes(MS().Register({ key = "m.party", requires = { "m.uf" } }), "re-registering merges and keeps the label")
    eq(MS().Label("m.party"), "Party frames")
    MS().Register({ key = "m.raid", requires = { "m.party" } })
    eq(table.concat(MS().Requires("m.raid"), ","), "m.party")
    eq(table.concat(MS().Dependents("m.uf"), ","), "m.party,m.raid", "transitive, in registration order")
    eq(table.concat(MS().Dependents("m.party"), ","), "m.raid")
    eq(#MS().Dependents("m.cast"), 0)
    local changed = MS().SetWithDeps("m.uf", false)
    eq(table.concat(changed, ","), "m.party,m.raid,m.uf")
    eq(MS().Wanted("m.party"), false); eq(MS().Wanted("m.raid"), false)
    eq(#MS().Dependents("m.uf"), 0, "an off module is not a dependent")
    changed = MS().SetWithDeps("m.raid", true)
    eq(table.concat(changed, ","), "m.uf,m.party,m.raid", "turning one on pulls its requirements in first")
    -- a requirement loop cannot hang
    MS().Register({ key = "m.uf", requires = { "m.raid" } })
    eq(#MS().Dependents("m.uf") >= 0, true)
    MS().SetWithDeps("m.uf", false)
    local none = MS().SetWithDeps("m.cast", false)
    eq(table.concat(none, ","), "m.cast")
end

function T.turn_all_on_clears_every_switch_and_marks_a_reload()
    msboot({ db = { modules = { ["m.cast"] = false, ["m.mini"] = false, ["m.future"] = false } } })
    MS().Set("m.uf", false)
    eq(MS().PendingCount(), 1)
    local log = {}
    MS().OnAnyChange(function(key, new) log[#log + 1] = key .. "=" .. tostring(new) end)
    eq(MS().TurnAllOn(), 3, "three were off")
    for _, key in ipairs(MS().Keys()) do eq(MS().Wanted(key), true, key) end
    eq(ForeverSTUwaveDB.modules["m.future"], false, "a key this version does not know is left alone")
    eq(ForeverSTUwaveDB.modules["m.cast"], nil)
    eq(table.concat(MS().PendingKeys(), ","), "m.cast,m.mini", "off at load and on now: a reload builds them; m.uf is back to what loaded")
    eq(#log, 3)
    eq(MS().TurnAllOn(), 0)
end

function T.the_store_is_account_wide_and_a_profile_switch_does_not_touch_it()
    msboot()
    local C = FS.Config
    MS().Set("m.cast", false)
    local store = ForeverSTUwaveDB.modules
    yes(C.NewProfile("Alt")); yes(C.SetActiveProfile("Alt"))
    eq(MS().Wanted("m.cast"), false, "a new profile still has Cast bars off")
    yes(C.CopyProfile("Default"))
    yes(C.ResetProfile())
    yes(C.SetActiveProfile("Default"))
    eq(MS().Wanted("m.cast"), false)
    eq(ForeverSTUwaveDB.modules, store, "the same table, untouched")
    eq(store["m.cast"], false)
    for name, profile in pairs(ForeverSTUwaveDB.profiles) do
        eq(profile.settings.modules, nil, name .. " holds no module switches")
        for key in pairs(profile.settings) do eq(tostring(key):find("^m%.") == nil, true, "no m.* key in " .. name) end
    end
    eq(MS().PendingCount(), 1)
end

function T.snapshot_lists_every_switch()
    msboot({ db = { modules = { ["m.cast"] = false } } })
    local snap = MS().Snapshot()
    local n = 0
    for key, on in pairs(snap) do n = n + 1; eq(on, key ~= "m.cast", key) end
    eq(n, 16)
end

-- ---- the nav, the card and the list -------------------------------------------------------------------------------

function T.the_modules_page_lists_every_switch_between_profiles_and_help()
    local W = msboot()
    local cats = W.Categories()
    local at = {}
    for i, c in ipairs(cats) do at[c.key] = i end
    yes(at.modules, "the Modules page is registered")
    eq(cats[at.modules].group, "GENERAL")
    yes(at.profiles < at.modules and at.modules < at.help, "after Profiles, before Help")
    W.Open("modules")
    local page, tab = W.Current()
    eq(page, "modules"); eq(tab, "all")
    for _, m in ipairs(PROTO.modules) do
        local entry = W.RowByKey(m.key, "modules")
        yes(entry, m.key .. " has a row")
        eq(entry.label, m.label, m.key)
        eq(entry.kind, "switch")
        yes(visibleText(m.label), m.label .. " is on screen")
        eq(type(entry.reload), "function", m.key .. " exposes its reload line to the footer")
        eq(entry.reload(), nil, "nothing pending yet")
    end
    errorsClean()
end

function T.every_module_page_gets_a_power_button_and_the_others_get_none()
    local W = msboot()
    W.Open("unit")
    local S = W.Spec
    for _, n in ipairs(PROTO.nav) do
        local b = navButton(W, n.page)
        yes(b, n.page .. " has a nav button")
        eq(b.fsLabel:GetText(), n.label, n.page .. " label equals the prototype")
        local p = b.fsPower
        yes(p, n.page .. " has a power button")
        eq(p.w, S.PWR, "PWR wide"); eq(p.h, S.PWR, "PWR tall")
        eq(p.fsKey, n.m)
        local slot = W.NavSlot(n.page)
        eq(p.parent, slot, "seated in the nav slot")
        eq(slot.points[1].x, -S.PWR_R, "PWR_R from the item edge")
    end
    for _, page in ipairs({ "classmod", "role", "profiles", "help", "modules" }) do
        local b = navButton(W, page)
        yes(b, page .. " exists")
        eq(b.fsPower, nil, page .. " has no power button")
    end
    errorsClean()
end

function T.the_power_glyph_is_pink_when_on_dim_when_off_and_cyan_on_hover()
    local W = msboot()
    W.Open("cast")
    local C = W.C
    local p = navButton(W, "cast").fsPower
    yes(#p.fsGlyph.textures >= 5, "the glyph is a set of rects")
    yes(sameColor(glyphColor(p), C.pink), "on: pink")
    hover(p, true)
    yes(sameColor(glyphColor(p), C.cyan), "hover: cyan")
    hover(p, false)
    yes(sameColor(glyphColor(p), C.pink))
    press(p)
    eq(MS().Wanted("m.cast"), false, "a click on the nav power button turns it off")
    local dim = glyphColor(p)
    yes(not sameColor(dim, C.pink) and not sameColor(dim, C.cyan), "off: a dim glyph")
    yes(dim[1] < 0.5 and dim[2] < 0.5, "dimmer than the on state")
    hover(p, true)
    yes(sameColor(glyphColor(p), C.cyan), "hover over an off module: cyan")
    hover(p, false)
    press(p)
    eq(MS().Wanted("m.cast"), true, "and back on")
    yes(sameColor(glyphColor(p), C.pink))
    hover(p, true)
    local tip = table.concat(TOOLTIP.history, " | ")
    yes(tip:find("Turn off Cast bars", 1, true), tip)
    yes(tip:find("Reload UI", 1, true), "the tooltip says a reload applies it: " .. tip)
    errorsClean()
end

function T.the_nav_text_mutes_when_off_and_stays_muted_when_the_nav_repaints()
    local W = msboot()
    W.Open("cast")
    local C = W.C
    local b = navButton(W, "cast")
    b.fsLabel:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    yes(sameColor(b.fsLabel.textColor, C.cyan), "on and selected: cyan")
    MS().Set("m.cast", false)
    local c = b.fsLabel.textColor
    yes(c and c[1] < 0.5 and c[2] > 0.4, "off and selected: a dim cyan, got " .. tostring(c and c[1]) .. "," .. tostring(c and c[2]))
    b.fsLabel:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)      -- what the nav does on every select
    c = b.fsLabel.textColor
    yes(c[1] < 0.5, "a repaint by the nav stays muted")
    b.fsSelected = false
    b.fsLabel:SetTextColor(C.muted[1], C.muted[2], C.muted[3], 1)
    c = b.fsLabel.textColor
    yes(c[1] < C.muted[1] - 0.1, "off and not selected: dimmer than the muted nav text")
    MS().Set("m.cast", true)
    c = b.fsLabel.textColor
    yes(sameColor(c, C.muted), "back on: the nav colour returns")
end

function T.an_off_module_shows_the_off_card_on_its_page()
    local W = msboot({ db = { modules = { ["m.cast"] = false } } })
    W.Open("cast")
    yes(visibleText("Cast bars is off."), "the card says the module is off")
    yes(visibleText("Blizzard's own shows instead. Turning it on takes a Reload UI."))
    no(visibleText("No settings yet. The power button in the list turns cast bars off."), "the page body is covered")
    local card = _G.ForeverSTUwaveConfigOffCard
    yes(card and card:IsShown(), "the card is shown")
    -- the page's tab page is hidden underneath, so nothing under the card is hovered or scrolled
    local rec = W.I.ui.tabRec
    eq(rec.page:IsShown(), false)
    -- a different page is unaffected
    W.Open("mini")
    no(card:IsShown(), "no card on a page whose module is on")
    yes(W.I.ui.tabRec.page:IsShown())
    W.Open("cast")
    yes(card:IsShown(), "and back")
    -- a module turned off this session is still running until the reload
    MS().Set("m.mini", false)
    W.Open("mini")
    yes(visibleText("Minimap turns off at the next Reload UI."), "running now, off after the reload")
    errorsClean()
end

function T.the_off_card_for_a_live_module_says_where_to_turn_it_on()
    local W = msboot()
    W.Open("plates")
    MS().Set("m.np", false)
    yes(visibleText("Nameplates is off."), "a live module is simply off")
    yes(visibleText("Blizzard's own shows instead. Turn it on with the power button here or in the list."))
    errorsClean()
end

function T.the_card_power_button_turns_the_module_back_on()
    local W = msboot({ db = { modules = { ["m.cast"] = false } } })
    W.Open("cast")
    local card = _G.ForeverSTUwaveConfigOffCard
    yes(card:IsShown())
    local big = card.fsBig
    yes(big and big.w == 64 and big.h == 64, "a 64 unit button")
    yes(sameColor(glyphColor(big), W.C.line) == false and glyphColor(big)[1] < 0.5, "dim glyph while off")
    hover(big, true)
    yes(sameColor(glyphColor(big), W.C.cyan), "hover: cyan")
    hover(big, false)
    press(big)
    eq(MS().Wanted("m.cast"), true)
    no(card:IsShown(), "the card closes")
    yes(W.I.ui.tabRec.page:IsShown(), "and the page is back")
    eq(MS().Pending("m.cast"), true, "it was off at load, so a reload builds it")
    errorsClean()
end

-- The Pet bar off card carries a ? (question 180): the game's pet unit frame is Unit frames' to hide, not this switch's.
function T.the_pet_bar_off_card_has_a_help_icon_saying_the_pet_unit_frame_belongs_to_unit_frames()
    local W = msboot({ db = { modules = { ["m.pet"] = false } } })
    W.Open("pet")
    local card = _G.ForeverSTUwaveConfigOffCard
    yes(card and card:IsShown(), "the card is shown")
    local help = card.fsHelp
    yes(help and help:IsShown(), "a ? on the card")
    local tip = help.fsTip
    yes(tip:find("pet unit frame", 1, true) and tip:find("Unit frames", 1, true), "the tip names both: " .. tostring(tip))
    help.scripts.OnEnter(help)
    eq(TOOLTIP.text, tip, "hovering the ? shows it")
    -- seated on the second line, right of where its centred text ends
    local pt = help.points[1]
    eq(pt.rel, card.fsLine2, "anchored to the second line")
    yes(pt.x >= card.fsLine2:GetStringWidth() / 2, "right of the text, not on it")
    yes(visibleText("Pet bar is off."), "the card still says the module is off")
    yes(visibleText("Blizzard's own shows instead. Turning it on takes a Reload UI."), "and keeps its two lines")
    errorsClean()
end

function T.the_pet_bar_help_icon_follows_the_page_and_no_other_off_card_has_one()
    local W = msboot({ db = { modules = { ["m.pet"] = false, ["m.cast"] = false } } })
    W.Open("pet")
    local card = _G.ForeverSTUwaveConfigOffCard
    yes(card.fsHelp and card.fsHelp:IsShown(), "the Pet bar card has its ?")
    W.Open("cast")
    yes(card:IsShown(), "the Cast bars card is up")
    no(card.fsHelp and card.fsHelp:IsShown(), "no ? on a card with nothing to add")
    W.Open("pet")
    yes(card.fsHelp:IsShown(), "and it is back on the Pet bar card")
    -- a module turned back on closes the card, the ? with it
    MS().Set("m.pet", true)
    no(card:IsShown())
    errorsClean()
end

function T.a_pending_reload_marks_the_row_the_nav_count_and_the_registry_and_clears_when_turned_back()
    local W = msboot()
    W.Open("modules")
    local entry = W.RowByKey("m.cast", "modules")
    no(visibleText("RELOAD"), "no tag yet")
    local nav = navButton(W, "modules")
    local function chip()
        for _, o in ipairs(ALL) do
            if o.kind == "FontString" and o:IsVisible() and under(nav, o) and o:GetText():match("^%d+$") then return o end
        end
    end
    no(chip(), "no count yet")
    yes(press_label("Cast bars"))
    eq(MS().Wanted("m.cast"), false)
    yes(visibleText("RELOAD"), "the row carries the reload tag")
    eq(entry.reload(), "Takes a Reload UI.")
    yes(chip() and chip():GetText() == "1", "the Modules nav item counts one")
    yes(press_label("Minimap"))
    eq(chip():GetText(), "2")
    yes(press_label("Cast bars"))
    eq(MS().PendingCount(), 1)
    eq(entry.reload(), nil, "turning it back clears the registry line")
    eq(chip():GetText(), "1")
    yes(press_label("Minimap"))
    no(visibleText("RELOAD"), "turning both back clears the tag")
    no(chip(), "and the count")
    errorsClean()
end

function T.a_live_row_has_no_reload_tag()
    local W = msboot()
    W.Open("modules")
    yes(press_label("Nameplates"))
    eq(MS().Wanted("m.np"), false)
    no(visibleText("RELOAD"))
    eq(W.RowByKey("m.np", "modules").reload(), nil)
end

function T.turning_off_a_module_others_need_asks_once_and_names_them()
    local W = msboot()
    MS().Register({ key = "m.party", requires = { "m.uf" } })
    MS().Register({ key = "m.raid", requires = { "m.uf" } })
    W.Open("unit")
    local p = navButton(W, "unit").fsPower
    press(p)
    eq(MS().Wanted("m.uf"), true, "nothing changed before the answer")
    eq(dialogText(), "Turning off Unit frames also turns off Party frames and Raid frames.")
    confirmDialog()
    eq(MS().Wanted("m.uf"), false); eq(MS().Wanted("m.party"), false); eq(MS().Wanted("m.raid"), false)
    -- cancel leaves everything on
    press(p)   -- turning it back on needs no question
    eq(MS().Wanted("m.uf"), true)
    eq(dialogText(), nil, "turning on never asks")
    press(navButton(W, "party").fsPower)
    eq(MS().Wanted("m.party"), true, "party was pulled back by its parent only when asked; now it is still off or on as set")
    errorsClean()
end

function T.a_cancelled_confirm_changes_nothing()
    local W = msboot()
    MS().Register({ key = "m.party", requires = { "m.uf" } })
    W.Open("unit")
    press(navButton(W, "unit").fsPower)
    local d = _G.ForeverSTUwaveConfigDialog
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and under(d, o) and o:GetText() == "Cancel" then
            local b = owner(o); b.scripts.OnClick(b, "LeftButton")
        end
    end
    eq(MS().Wanted("m.uf"), true); eq(MS().Wanted("m.party"), true)
end

function T.a_help_mark_on_the_power_button_names_the_dependents()
    local W = msboot()
    W.Open("unit")
    local b = navButton(W, "unit")
    no(b.fsPowerHelp:IsShown(), "no mark while nothing needs it")
    MS().Register({ key = "m.party", requires = { "m.uf" } })
    MS().Register({ key = "m.raid", requires = { "m.uf" } })
    W.RefreshAll()
    -- a registration alone does not repaint the nav; any switch change does
    MS().Set("m.chat", false)
    yes(b.fsPowerHelp:IsShown(), "a ? beside the power button")
    local tip = b.fsPowerHelp.fsTip
    yes(tip:find("Party frames", 1, true) and tip:find("Raid frames", 1, true), tip)
    MS().SetWithDeps("m.uf", false)
    no(b.fsPowerHelp:IsShown(), "no mark once the dependents are off")
end

function T.all_on_in_profiles_turns_every_module_back_on_and_marks_a_reload()
    local W = msboot({ db = { modules = { ["m.cast"] = false, ["m.mini"] = false } } })
    MS().Set("m.uf", false)
    W.Open("profiles")
    yes(visibleText("MODULES"), "a Modules section on the Profiles page")
    local entry = W.RowByKey("allon", "profiles") or (function()
        for _, e in ipairs(W.Rows()) do if e.label == "Turn every module back on" then return e end end
    end)()
    yes(entry, "the ALL ON row")
    eq(entry.page, "profiles")
    local b = entry.row.control
    yes(visibleText("ALL ON"))
    local tip = entry.row.fsHelp and entry.row.fsHelp.fsTip or ""
    eq(tip, "Every power button in the list back on. Takes a Reload UI.")
    press(b)
    for _, key in ipairs(MS().Keys()) do eq(MS().Wanted(key), true, key) end
    eq(table.concat(MS().PendingKeys(), ","), "m.cast,m.mini", "the two that were off at load wait for a reload")
    errorsClean()
end

function T.read_only_settings_disable_the_power_buttons()
    local W = msboot({ db = { profilesVersion = 99 } })
    W.Open("cast")
    local p = navButton(W, "cast").fsPower
    press(p)
    eq(MS().Wanted("m.cast"), true, "nothing changed")
    yes(p.alpha < 1, "the disabled look")
    local said = table.concat(__printed, " | ")
    yes(said:find("read-only", 1, true), "the player is told: " .. said)
end

function T.a_list_row_shows_the_changed_dot_and_its_reset_turns_the_module_on()
    local W = msboot()
    W.Open("modules")
    local entry = W.RowByKey("m.cast", "modules")
    no(entry.row.fsDot:IsShown(), "no dot while on")
    MS().Set("m.cast", false)
    W.RefreshAll()
    yes(entry.row.fsDot:IsShown(), "a pink dot while off (not the default)")
    yes(W.ChangedKeys("modules")[1] == "m.cast")
    W.ResetKeys({ "m.cast" })
    eq(MS().Wanted("m.cast"), true)
    no(entry.row.fsDot:IsShown())
end

function T.the_list_toggle_and_the_power_button_stay_in_step()
    local W = msboot()
    W.Open("modules")
    local row = W.RowByKey("m.mini", "modules").row
    row.control.scripts.OnClick(row.control, "LeftButton")
    eq(MS().Wanted("m.mini"), false)
    yes(sameColor(glyphColor(navButton(W, "mini").fsPower), W.C.pink) == false, "the nav button followed")
    press(navButton(W, "mini").fsPower)
    eq(MS().Wanted("m.mini"), true)
    eq(row.control.fsChecked, true, "and the list toggle followed")
end

function T.the_list_asks_before_turning_off_a_module_others_need()
    local W = msboot()
    MS().Register({ key = "m.party", requires = { "m.uf" } })
    W.Open("modules")
    local row = W.RowByKey("m.uf", "modules").row
    row.control.scripts.OnClick(row.control, "LeftButton")
    eq(MS().Wanted("m.uf"), true)
    eq(dialogText(), "Turning off Unit frames also turns off Party frames.")
    confirmDialog()
    eq(MS().Wanted("m.party"), false)
end

function T.a_window_without_the_switch_store_still_opens()
    -- the config harnesses run without Core/ModuleSwitch.lua: ConfigModules.lua must do nothing then
    local W = boot()
    W.Open("cast")
    for _, c in ipairs(W.Categories()) do no(c.key == "modules", "no Modules page without the store") end
    eq(#__errors, 0)
end

local CLASSMOD_TABS = { "general", "druid", "hunter", "mage", "paladin", "priest", "rogue", "shaman", "warlock", "warrior" }

-- the rows the window holds for a Class modules tab (page, tab) as a list of their kinds
local function classmodKinds(W, tab)
    W.Open("classmod", tab)
    local kinds = {}
    for _, e in ipairs(W.Rows()) do
        if e.page == "classmod" and e.tab == tab then kinds[#kinds + 1] = e.kind end
    end
    return kinds
end

function T.with_the_gunsight_off_every_class_modules_tab_says_so_in_place_of_its_rows()
    local W = msboot({ db = { modules = { ["m.gs"] = false } } })
    for _, tab in ipairs(CLASSMOD_TABS) do
        local kinds = classmodKinds(W, tab)
        eq(table.concat(kinds, ","), "note", "the " .. tab .. " tab holds the note and nothing else")
    end
    W.Open("classmod", "general")
    yes(anyText("Gunsight HUD is off. Turning it on takes a Reload UI."), "the off text")
    errorsClean()
end

function T.the_class_modules_note_follows_the_switch_turned_back_on_before_the_reload()
    local W = msboot({ db = { modules = { ["m.gs"] = false } } })
    W.Open("classmod", "general")
    yes(anyText("Gunsight HUD is off."))
    MS().Set("m.gs", true)
    W.RefreshAll()
    yes(anyText("Gunsight HUD turns on at the next Reload UI."), "switched back on, waiting for the reload")
    no(anyText("Gunsight HUD is off."), "the old line is gone")
    errorsClean()
end

function T.with_the_gunsight_on_the_class_modules_tabs_hold_their_rows()
    -- this window loads no class module, so only the General tab (the plate, which needs the Gunsight areas file) has rows
    local W = msboot()
    local kinds = classmodKinds(W, "general")
    yes(#kinds > 0, "the General tab has rows")
    for _, kind in ipairs(kinds) do no(kind == "note", "no off note on General") end
    for _, tab in ipairs(CLASSMOD_TABS) do
        W.Open("classmod", tab)
        no(anyText("Gunsight HUD is off."), "no off text on " .. tab .. " while the module is on")
    end
    errorsClean()
end

function T.zz_unused() end
"""

# press_label: a click on the switch row with this label (the list toggle), shared by several checks
HELPERS = r"""
local function press_label(label)
    local r = row(label)
    if not r then error("no visible row " .. label, 2) end
    local b = r.control
    if not b.enabled then return false end
    b.scripts.OnClick(b, "LeftButton")
    return true
end
"""

CHECK_NAMES: list[str] = []


def run_lua_checks() -> int:
    global CHECK_NAMES
    CHECK_NAMES = [n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", CHECKS, re.M) if not n.startswith("zz_")]
    proto = proto_modules()
    base.CHECKS = base.CHECKS.replace("__checks = T", HELPERS + CHECKS + "\n__checks = T")
    failed = 0
    for name in CHECK_NAMES:
        try:
            lua = base.boot()
            lua.globals().__msSrc = MS_FILE.read_text(encoding="utf-8")
            lua.globals().PROTO = base.to_lua(lua, proto)
            lua.eval("__checks")[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:2])[:500]}")
    return failed


# ---- the module gates (B5a): the real .toc in a tolerant mock client -------------------------------------------------------
#
# The checks above run Core/ModuleSwitch.lua inside the config window harness. These run EVERY file of the real .toc, in
# order, in a mock client whose frames accept any call, then fire ADDON_LOADED, PLAYER_LOGIN and PLAYER_ENTERING_WORLD.
# Each Blizzard frame a module may dim, hook or reparent is a stub that records every call that is not a read. A module
# that is off must build nothing of its own, leave every one of those stubs untouched and keep its API tables defined; the
# same module on must build and take over as before. One row per gated module.

GATE_WORLD = r"""
-- Gate world: a tolerant mock client for loading real module files and watching Blizzard frames.
__touched, __made, __errors, __printed, __evFrames, __timers = {}, {}, {}, {}, {}, {}
__phase, __loadFailed = "load", {}
local watched = {}                 -- stub -> label
local ownMT = {}

-- the files whose code is on the stack (the .toc path is each chunk's name)
local function stackFiles()
    local set, level = {}, 3
    while true do
        local info = debug.getinfo(level, "S")
        if not info then break end
        set[(info.source:gsub("^@", ""))] = true
        level = level + 1
    end
    return set
end
__touchedBy = {}
local function touch(entry)
    __touched[#__touched + 1] = entry
    __touchedBy[#__touched] = stackFiles()
end

local NUMBERS = {
    GetWidth = 250, GetHeight = 252, GetScale = 1, GetEffectiveScale = 1, GetLeft = 100, GetRight = 350,
    GetTop = 700, GetBottom = 450, GetAlpha = 1, GetFrameLevel = 1, GetNumPoints = 0, GetNumChildren = 0,
    GetNumRegions = 0, GetStringWidth = 40, GetStringHeight = 10, GetValue = 0, GetID = 0, GetDrawLayer = nil,
}
local STRINGS = { GetFrameStrata = "MEDIUM", GetObjectType = "Frame", GetText = "", GetTexture = "", GetFont = "x" }

local function isRead(name)
    return name:find("^Get") or name:find("^Is") or name:find("^Has") or name:find("^Can") or name == "Hide" and false
end

local function Sponge(label, isWatched)
    local self = { _label = label, _scripts = {}, _events = {}, _hooks = {}, _regions = {}, _points = {} }
    if isWatched then watched[self] = label end
    return setmetatable(self, ownMT)
end

ownMT.__index = function(t, k)
    if type(k) ~= "string" or not k:find("^%u") then return nil end
    if k == "SetScript" then
        return function(self, name, fn)
            if watched[self] then touch(self._label .. ":SetScript") end
            self._scripts[name] = fn
        end
    elseif k == "HookScript" then
        return function(self, name, fn)
            if watched[self] then touch(self._label .. ":HookScript") end
            self._hooks[name] = self._hooks[name] or {}
            table.insert(self._hooks[name], fn)
        end
    elseif k == "GetScript" then
        return function(self, name) return self._scripts[name] end
    elseif k == "RegisterEvent" or k == "RegisterUnitEvent" then
        return function(self, event)
            if watched[self] then touch(self._label .. ":" .. k) end
            self._events[event] = true
            if not self._listed then self._listed = true; __evFrames[#__evFrames + 1] = self end
        end
    elseif k == "UnregisterEvent" then
        return function(self, event)
            if watched[self] then touch(self._label .. ":UnregisterEvent") end
            self._events[event] = nil
        end
    elseif k == "UnregisterAllEvents" then
        return function(self)
            if watched[self] then touch(self._label .. ":UnregisterAllEvents") end
            self._events = {}
        end
    elseif k == "GetName" then
        return function(self) return self._name end
    elseif k == "GetParent" then
        return function(self) return self._parent end
    elseif k == "GetChildren" or k == "GetRegions" then
        return function() end
    elseif k == "SetPoint" then
        return function(self, point, rel, relPoint, x, y)
            if watched[self] then touch(self._label .. ":SetPoint") end
            self._points[#self._points + 1] = { point, rel, relPoint, x, y }
        end
    elseif k == "ClearAllPoints" then
        return function(self)
            if watched[self] then touch(self._label .. ":ClearAllPoints") end
            self._points = {}
        end
    elseif k == "GetPoint" then
        return function(self, i)
            local p = self._points[i or 1]
            if p then return p[1], p[2], p[3], p[4], p[5] end
        end
    elseif k == "GetNumPoints" then
        return function(self) return #self._points end
    elseif k == "SetParent" then
        return function(self, p)
            if watched[self] then touch(self._label .. ":SetParent") end
            self._parent = p
        end
    elseif k == "Show" or k == "Hide" or k == "SetShown" then
        return function(self, v)
            if watched[self] then touch(self._label .. ":" .. k) end
            if k == "Show" then self._shown = true elseif k == "Hide" then self._shown = false else self._shown = v and true or false end
        end
    elseif k == "IsShown" or k == "IsVisible" then
        return function(self) return self._shown ~= false end
    elseif k:find("^Create") then
        return function(self, ...)
            local child = Sponge((self._label or "?") .. "." .. k)
            child._parent = self
            return child
        end
    elseif NUMBERS[k] ~= nil then
        return function() return NUMBERS[k] end
    elseif STRINGS[k] ~= nil then
        return function() return STRINGS[k] end
    elseif k:find("^Is") or k:find("^Has") or k:find("^Can") then
        return function() return false end
    elseif k:find("^Get") then
        return function() end
    end
    return function(self, ...)
        if watched[self] then touch(self._label .. ":" .. k) end
    end
end
ownMT.__newindex = function(t, k, v)
    -- a script field or method written on a watched Blizzard stub counts as a touch
    if watched[t] and type(k) == "string" and k:sub(1, 1) ~= "_" then
        touch(t._label .. ":write:" .. k)
    end
    rawset(t, k, v)
end

-- A Blizzard frame the module under test may only read: every non-read call on it is recorded.
function Watch(name, fields)
    local f = Sponge(name, true)
    f._name = name
    if fields then for k, v in pairs(fields) do rawset(f, k, v) end end
    _G[name] = f
    return f
end

function CreateFrame(kind, name, parent, template)
    local f = Sponge(name or ("(" .. tostring(kind) .. ")"))
    f._name, f._kind, f._parent = name, kind, parent
    __made[#__made + 1] = { name = name, phase = __phase, files = stackFiles() }
    if name then _G[name] = f end
    return f
end

function hooksecurefunc(a, b, c)
    if type(a) == "string" then
        touch("hooksecurefunc:" .. a)
    elseif type(a) == "table" and watched[a] then
        touch(watched[a] .. ":hooksecurefunc:" .. tostring(b))
    end
end

UIParent = Sponge("UIParent")
UIParent._name = "UIParent"
Minimap = nil
function InCombatLockdown() return false end
function GetTime() return 100 end
function geterrorhandler() return function(e) __errors[#__errors + 1] = tostring(e) end end
function print(...) local t = {} for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end __printed[#__printed + 1] = table.concat(t, " ") end
__tickers = {}
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end, NewTicker = function(_, fn)
    local t = { fn = fn, Cancel = function(self) self.cancelled = true end }
    __tickers[#__tickers + 1] = t
    return t
end }
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function tinsert(t, v) table.insert(t, v) end
function strtrim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
function GetPhysicalScreenSize() return 2560, 1440 end
function GetScreenWidth() return 2560 end
function GetScreenHeight() return 1440 end
PixelUtil = { GetPixelToUIUnitFactor = function() return 768 / 1440 end }
function issecretvalue() return false end
function CopyTable(t) local c = {} for k, v in pairs(t) do c[k] = type(v) == "table" and CopyTable(v) or v end return c end
SlashCmdList = {}
Enum = {}
function InterfaceOptions_AddCategory() end
function GetCVar() return nil end
function IsLoggedIn() return false end
function UnitClass() return "Shaman", "SHAMAN", 7 end
function UnitName() return "Stu" end
function UnitExists() return false end
function RegisterUnitWatch() end
function UnitGUID() return "Player-1" end
time = os.time
function GetLocale() return "enUS" end
function GetAddOnMetadata() return "1.0.0" end
C_AddOns = { GetAddOnMetadata = function() return "1.0.0" end, IsAddOnLoaded = function() return false end }

function Fire(event, ...)
    local list = {}
    for i, f in ipairs(__evFrames) do list[i] = f end
    for _, f in ipairs(list) do
        if f._events[event] and f._scripts.OnEvent then
            local ok, err = pcall(f._scripts.OnEvent, f, event, ...)
            if not ok then __errors[#__errors + 1] = tostring(err) end
        end
    end
end

FS = {}
function __load(path, src)
    local fn, err = loadstring(src, "@" .. path)
    if not fn then error(err, 0) end
    return fn("forever-stuwave", FS)
end

-- assertions
function yes(v, msg) if not v then error(msg or "expected true", 2) end end
function no(v, msg) if v then error(msg or "expected false", 2) end end
function eq(a, b, msg) if a ~= b then error((msg or "") .. " expected " .. tostring(b) .. " got " .. tostring(a), 2) end end

-- The real .toc, in order, the way the client runs it: files, then the saved variables, then ADDON_LOADED and login.
-- opts.off = module keys the saved store holds as false; opts.watch = Blizzard frames to record every non-read call on.
function Boot(opts)
    opts = opts or {}
    for _, name in ipairs(opts.watch or {}) do Watch(name) end
    if opts.pre then opts.pre() end
    __phase = "load"
    for _, rel in ipairs(__toc) do
        local ok, err = pcall(__load, rel, __read(rel))
        if not ok then __loadFailed[rel] = tostring(err) end
    end
    local modules = {}
    for _, key in ipairs(opts.off or {}) do modules[key] = false end
    ForeverSTUwaveDB = { modules = modules }
    __phase = "run"
    Fire("ADDON_LOADED", "forever-stuwave")
    IsLoggedIn = function() return true end
    Fire("PLAYER_LOGIN")
    Fire("PLAYER_ENTERING_WORLD", true, false)
    local timers = __timers
    __timers = {}
    for _, fn in ipairs(timers) do pcall(fn) end
    if not opts.noRegen then Fire("PLAYER_REGEN_ENABLED") end
end

-- Child frames of a watched Blizzard frame ({ Child = { GrandChild = true } }): each is a stub that records its own touches
-- under "Parent.Child", and TouchesOn("Parent") reports them with the parent's own.
local function attach(parent, label, tree)
    for child, sub in pairs(tree) do
        local stub = Sponge(label .. "." .. child, true)
        rawset(parent, child, stub)
        if type(sub) == "table" then attach(stub, label .. "." .. child, sub) end
    end
end
function WatchTree(name, tree)
    attach(_G[name] or Watch(name), name, tree)
end

-- A Blizzard panel the way Theme.SkinPanel meets it: the art children a stripped panel is searched for are absent (false), so
-- the skin finds nothing to hide; `children` adds real (watched) child frames.
local CHROME_KEYS = { "NineSlice", "Bg", "BG", "Background", "TitleBg", "TitleContainer", "TopTileStreaks", "TopBorder",
    "BottomBorder", "LeftBorder", "RightBorder", "PortraitContainer", "PortraitFrame", "portrait", "PortraitOverlay",
    "Inset", "InsetFrame", "ScrollFrameInset", "ListInset", "CloseButton", "Close", "TitleText", "TitleBar" }
function WatchPanel(name, children)
    local f = _G[name] or Watch(name)
    for _, key in ipairs(CHROME_KEYS) do rawset(f, key, false) end
    if children then attach(f, name, children) end
    return f
end

-- every touch recorded on a watched Blizzard frame (and its watched children), as one string ("" when it was left alone);
-- `file` keeps the touches made by code of that file (a frame several modules hook, like EditModeManagerFrame)
function TouchesOn(label, file)
    local list = {}
    for i, t in ipairs(__touched) do
        if (t:find("^" .. label .. "[:.]") or t:find(label .. ":hooksecurefunc", 1, true)) and (file == nil or __touchedBy[i][file]) then
            list[#list + 1] = t
        end
    end
    return table.concat(list, ", ")
end

-- frames this file's code created after the files finished loading (at ADDON_LOADED, login or later); `except` names a
-- file whose calls into this one do not count (another module using this module's API)
function BuiltBy(file, except)
    local n = 0
    for _, m in ipairs(__made) do
        if m.phase == "run" and m.files[file] and not (except and m.files[except]) then n = n + 1 end
    end
    return n
end

function MadeNamed(name)
    for _, m in ipairs(__made) do if m.name == name then return true end end
    return false
end

-- errors the client's handler heard from this file (its chunk name is the .toc path)
function ErrorsFrom(file)
    local list = {}
    for _, e in ipairs(__errors) do
        if e:find(file, 1, true) then list[#list + 1] = e end
    end
    return table.concat(list, " | ")
end

"""

GATE_CHECKS = r"""
local T = {}
local TOCPATH = "forever-stuwave"

-- the whole load must not have thrown inside the files this lane gates
local function loaded(file)
    eq(__loadFailed[file], nil, file .. " loads")
    eq(ErrorsFrom(file), "", file .. " raised no error")
end

local CAST_FILE = "Modules/CastBars/CastBars.lua"
local CAST_BLIZZARD = { "PlayerCastingBarFrame", "TargetFrameSpellBar" }

function T.cast_bars_off_builds_none_of_its_frames_and_leaves_the_stock_bars_alone()
    Boot({ off = { "m.cast" }, watch = CAST_BLIZZARD })
    loaded(CAST_FILE)
    eq(FS.ModuleSwitch.On("m.cast"), false)
    eq(FS.ModuleSwitch.Built("m.cast"), false, "nothing was built")
    eq(BuiltBy(CAST_FILE, "Modules/CombatHud/GunsightTape.lua"), 0, "no frame made after the files loaded")
    no(MadeNamed("ForeverSTUwavePlayerCastBar"), "no player bar")
    no(MadeNamed("ForeverSTUwaveTargetCastBar"), "no target bar")
    eq(FS.playerCastBar, nil)
    eq(FS.targetCastBar, nil)
    for _, name in ipairs(CAST_BLIZZARD) do eq(TouchesOn(name), "", name .. " untouched") end
end

function T.cast_bars_off_keeps_the_api_so_a_reader_can_still_call_it()
    Boot({ off = { "m.cast" }, watch = CAST_BLIZZARD })
    local C = FS.CastBars
    eq(type(C), "table", "FS.CastBars stays defined")
    eq(C.SetIdleHint("player", "x"), false, "no bar to hint")
    eq(C.SetRestAlpha(0.5), true)
    C.SetIdleVisible(true)
    eq(type(C.IsStackActive()), "boolean")
    eq(FS.playerCastBar == nil and FS.targetCastBar == nil, true)
    loaded(CAST_FILE)
end

function T.cast_bars_off_still_lets_the_gunsight_tapes_take_the_cast_state_machine()
    Boot({ off = { "m.cast" }, watch = CAST_BLIZZARD })
    eq(FS.CastBars.IsStackActive(), false, "the tapes hold the view")
    eq(ErrorsFrom("Modules/CombatHud/GunsightTape.lua"), "")
    for _, name in ipairs(CAST_BLIZZARD) do eq(TouchesOn(name), "", name .. " untouched") end
end

function T.cast_bars_on_builds_both_bars_and_dims_the_stock_ones_as_before()
    Boot({ watch = CAST_BLIZZARD })
    loaded(CAST_FILE)
    eq(FS.ModuleSwitch.Built("m.cast"), true)
    yes(MadeNamed("ForeverSTUwavePlayerCastBar"), "player bar")
    yes(MadeNamed("ForeverSTUwaveTargetCastBar"), "target bar")
    yes(FS.playerCastBar and FS.targetCastBar, "exported")
    for _, name in ipairs(CAST_BLIZZARD) do yes(TouchesOn(name) ~= "", name .. " dimmed") end
end

local AURAS_FILE = "Modules/Auras/Buffs.lua"
local AURAS_BLIZZARD = { "BuffFrame", "DebuffFrame", "TemporaryEnchantFrame" }

function T.buffs_off_builds_none_of_its_frames_and_leaves_the_stock_frames_alone()
    Boot({ off = { "m.auras" }, watch = AURAS_BLIZZARD })
    loaded(AURAS_FILE)
    eq(FS.ModuleSwitch.Built("m.auras"), false)
    eq(BuiltBy(AURAS_FILE), 0, "no frame made after the files loaded")
    no(MadeNamed("ForeverSTUwaveBuffsContainer"))
    no(MadeNamed("ForeverSTUwaveDebuffsContainer"))
    eq(FS.buffsContainer, nil)
    eq(FS.debuffsContainer, nil)
    for _, name in ipairs(AURAS_BLIZZARD) do eq(TouchesOn(name), "", name .. " untouched") end
end

function T.buffs_off_keeps_the_snapshot_api_and_says_it_is_frozen_so_a_reader_never_sees_a_missing_buff()
    Boot({ off = { "m.auras" }, watch = AURAS_BLIZZARD })
    local A = FS.PlayerAuras
    eq(type(A), "table", "FS.PlayerAuras stays defined")
    local snap = A.Get()
    eq(type(snap), "table"); eq(#snap.buffs, 0); eq(#snap.debuffs, 0)
    eq(A.IsFrozen(), true, "never refreshed, so a reader must treat it as unknown")
    eq(A.IsEngineDrawn(), false)
    loaded(AURAS_FILE)
end

function T.buffs_on_builds_both_containers_and_dims_the_stock_frames_as_before()
    Boot({ watch = AURAS_BLIZZARD })
    loaded(AURAS_FILE)
    eq(FS.ModuleSwitch.Built("m.auras"), true)
    yes(MadeNamed("ForeverSTUwaveBuffsContainer"))
    yes(MadeNamed("ForeverSTUwaveDebuffsContainer"))
    yes(FS.buffsContainer and FS.debuffsContainer)
    for _, name in ipairs({ "BuffFrame", "DebuffFrame" }) do yes(TouchesOn(name) ~= "", name .. " dimmed") end
    eq(FS.PlayerAuras.IsFrozen(), false, "a built module is as frozen as the client says (readable here)")
end

function T.the_shaman_shield_tile_shows_unknown_not_missing_while_buffs_are_off()
    Boot({ off = { "m.auras" }, watch = AURAS_BLIZZARD })
    yes(type(FS.ShamanBuffs) == "table" and type(FS.ShamanBuffs.Update) == "function", "the reader is loaded")
    local view = FS.ShamanBuffs.Update(200)
    yes(view and view.shield, "a view")
    eq(view.shield.mode, "hollow", "a hollow ? while the snapshot is not kept")
    eq(view.shield.text, "?")
end

function T.the_shaman_shield_tile_still_says_missing_while_buffs_are_on()
    Boot({})
    local view = FS.ShamanBuffs.Update(200)
    eq(view.shield.mode, "warn", "unchanged with the module on")
end

local MINI_FILE = "Modules/Minimap/Minimap.lua"
local BANNER_FILE = "Modules/Minimap/InstanceBanner.lua"
local MINI_BLIZZARD = { "Minimap", "MinimapCluster", "MinimapBackdrop", "GameTimeFrame", "TimeManagerClockButton",
    "ExpansionLandingPageMinimapButton", "EditModeManagerFrame", "MinimapInstanceDifficulty" }
local function miniWorld(off)
    Boot({ off = off, watch = MINI_BLIZZARD, pre = function()
        rawset(MinimapCluster, "InstanceDifficulty", MinimapInstanceDifficulty)
        rawset(MinimapInstanceDifficulty, "ContentModes", {})
        WatchTree("MinimapCluster", { MinimapContainer = true, Tracking = true, BorderTop = true, DielFrame = true,
            IndicatorFrame = { MailFrame = true } })
    end })
    -- what the client does later: a rescale pass, a display change, the timers the build armed, the end of a fight
    Fire("UI_SCALE_CHANGED"); Fire("DISPLAY_SIZE_CHANGED"); Fire("EDIT_MODE_LAYOUTS_UPDATED"); Fire("PLAYER_REGEN_ENABLED")
    local timers = __timers
    __timers = {}
    for _, fn in ipairs(timers) do pcall(fn) end
end

function T.minimap_off_builds_nothing_and_leaves_every_blizzard_minimap_frame_alone()
    miniWorld({ "m.mini" })
    loaded(MINI_FILE); loaded(BANNER_FILE)
    eq(FS.ModuleSwitch.Built("m.mini"), false)
    eq(BuiltBy(MINI_FILE), 0, "no frame made after the files loaded")
    eq(BuiltBy(BANNER_FILE), 0, "no banner plate")
    eq(_G.GetMinimapShape, nil, "the round map keeps its round answer")
    for _, name in ipairs(MINI_BLIZZARD) do
        eq(TouchesOn(name, MINI_FILE), "", name .. " untouched by the map")
        eq(TouchesOn(name, BANNER_FILE), "", name .. " untouched by the banner")
    end
    eq(Minimap.fsBezel, nil)
    eq(Minimap.fsPlaced, nil)
end

function T.minimap_off_keeps_its_settings_and_coords_tables()
    miniWorld({ "m.mini" })
    local S = FS.MinimapSettings
    eq(type(S), "table")
    eq(S.Width(), S.w.default); eq(S.Height(), S.h.default); eq(S.Scale(), 1)
    eq(type(FS.MinimapCoords), "table")
    eq(FS.MinimapCoords.KEY, "minimap.coords")
    FS.Config.Set("minimap.scale", 150)
    FS.Config.Set("minimap.coords", false)
    eq(TouchesOn("Minimap"), "", "a changed setting does not reach the stock map")
    eq(TouchesOn("MinimapCluster"), "")
end

function T.minimap_on_builds_the_body_defines_the_shape_and_marks_itself_built()
    miniWorld({})
    loaded(MINI_FILE); loaded(BANNER_FILE)
    eq(FS.ModuleSwitch.Built("m.mini"), true)
    eq(type(_G.GetMinimapShape), "function")
    eq(_G.GetMinimapShape(), "SQUARE")
    yes(Minimap.fsPlaced, "the map was seated")
    yes(TouchesOn("Minimap") ~= "", "the stock map was reshaped")
    yes(TouchesOn("MinimapInstanceDifficulty") ~= "", "the banner was skinned")
end

local TRACK_FILES = { "Modules/Tracker/Tracker.lua", "Modules/Tracker/TrackerSeat.lua", "Modules/Tracker/QuestTimer.lua",
    "Modules/ActionBars/ConsoleKeys.lua" }
local TRACK_BLIZZARD = { "ObjectiveTrackerFrame", "QuestTimerFrame", "RightManagedFrameContainer",
    "ObjectiveTrackerHeaderFont", "ObjectiveTrackerLineFont", "QuestObjectiveTracker", "CampaignQuestObjectiveTracker",
    "ScenarioObjectiveTracker", "ProfessionsRecipeTracker" }
local editModeSaves
local function trackWorld(off, extraWatch, boot)
    local watch = {}
    for _, n in ipairs(TRACK_BLIZZARD) do watch[#watch + 1] = n end
    for _, n in ipairs(extraWatch or {}) do watch[#watch + 1] = n end
    editModeSaves = 0
    boot = boot or {}
    Boot({ off = off, watch = watch, noRegen = boot.noRegen, pre = function()
        WatchPanel("QuestTimerFrame")
        if boot.combat then InCombatLockdown = function() return true end end
        WatchTree("ObjectiveTrackerFrame", { Header = { MinimizeButton = true, Background = true, Text = true }, NineSlice = true })
        for _, module in ipairs({ "QuestObjectiveTracker", "CampaignQuestObjectiveTracker", "ScenarioObjectiveTracker", "ProfessionsRecipeTracker" }) do
            WatchTree(module, { Header = { Background = true, Text = true, MinimizeButton = true } })
        end
        Enum.EditModeSystem = { ObjectiveTracker = 7 }
        Enum.EditModeLayoutType = { Preset = 0, Account = 1 }
        local system = { system = 7, isInDefaultPosition = true, anchorInfo = { point = "TOPRIGHT", relativeTo = "UIParent", relativePoint = "TOPRIGHT", offsetX = 0, offsetY = -200 } }
        local layout = { layoutType = 1, layoutName = "Mine", systems = { system } }
        C_EditMode = {
            GetLayouts = function() return { layouts = { layout }, activeLayout = 1 } end,
            SaveLayouts = function() editModeSaves = editModeSaves + 1 end,
            SetActiveLayout = function() end,
        }
        EditModePresetLayoutManager = { GetCopyOfPresetLayouts = function() return {} end }
        C_QuestLog = {
            GetNumQuestLogEntries = function() return 1 end,
            GetInfo = function() return { questID = 77, title = "Hurry", isHeader = false } end,
            GetTimeAllowed = function() return 600, 30 end,
        }
    end })
    Fire("QUEST_LOG_UPDATE"); Fire("UPDATE_QUEST_TIMERS"); if not boot.noRegen then Fire("PLAYER_REGEN_ENABLED") end; Fire("UI_SCALE_CHANGED")
    local timers = __timers
    __timers = {}
    for _, fn in ipairs(timers) do pcall(fn) end
end

function T.quest_tracker_off_builds_nothing_hooks_nothing_and_writes_no_edit_mode_layout()
    trackWorld({ "m.track" })
    for _, f in ipairs(TRACK_FILES) do loaded(f) end
    eq(FS.ModuleSwitch.Built("m.track"), false)
    eq(BuiltBy("Modules/Tracker/Tracker.lua"), 0, "no panel frame")
    eq(BuiltBy("Modules/Tracker/QuestTimer.lua"), 0, "no timer drawer, no event frame")
    no(MadeNamed("ForeverSTUwaveQuestTimer"))
    for _, name in ipairs(TRACK_BLIZZARD) do
        for _, f in ipairs(TRACK_FILES) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
    end
    eq(FS.Tracker.Panel(), nil)
    FS.Tracker.Refresh()
    eq(FS.TrackerSeat.Ready(), false, "no seat to report, so the layout editor shows no handle")
    eq(FS.TrackerSeat.Rect(), nil)
    local ok, why = FS.TrackerSeat.Move(10, -10)
    eq(ok, false); yes(why:find("off", 1, true), why)
    ok = FS.TrackerSeat.Reset()
    eq(ok, false)
    eq(editModeSaves, 0, "nothing saved into the Edit Mode layout")
end

function T.quest_tracker_off_keeps_its_api_and_settings_defined()
    trackWorld({ "m.track" })
    eq(type(FS.Tracker.SIZE), "table"); eq(type(FS.Tracker.SIZE_LOCKED), "string")
    eq(FS.Tracker.SIZE.scale.key, "tracker.scale")
    eq(type(FS.QuestTimer.Digits), "function")
    eq(FS.QuestTimer.Read(100) ~= nil, true)
    FS.Config.Set("tracker.scale", 150); FS.Config.Set("tracker.alpha", 50); FS.Config.Set("questTimer.shown", false)
    for _, name in ipairs(TRACK_BLIZZARD) do eq(TouchesOn(name), "", name .. " untouched by a changed setting") end
end

function T.quest_tracker_on_builds_the_panel_and_the_seat_writes_the_layout_as_before()
    trackWorld({})
    for _, f in ipairs(TRACK_FILES) do loaded(f) end
    eq(FS.ModuleSwitch.Built("m.track"), true)
    yes(FS.Tracker.Panel(), "the panel exists")
    yes(TouchesOn("ObjectiveTrackerFrame", "Modules/Tracker/Tracker.lua") ~= "", "the stock tracker is skinned")
    eq(FS.TrackerSeat.Ready(), true)
    eq(FS.TrackerSeat.Move(10, -10), true)
    eq(editModeSaves, 1)
end

function T.the_console_quests_key_does_not_hook_the_stock_tracker_while_the_quest_tracker_is_off()
    trackWorld({ "m.track" })
    eq(TouchesOn("ObjectiveTrackerFrame", "Modules/ActionBars/ConsoleKeys.lua"), "")
    trackWorld({})
    -- on: the key follows a collapse made some other way (a post-hook on SetCollapsed)
    yes(TouchesOn("ObjectiveTrackerFrame", "Modules/ActionBars/ConsoleKeys.lua"):find("SetCollapsed", 1, true), "hooked when on")
end

local function timerDrawer()
    local drawer = _G.ForeverSTUwaveQuestTimer
    yes(drawer, "the timer drawer was built")
    return drawer
end

function T.the_quest_timer_hangs_from_the_minimap_key_row_while_the_minimap_is_ours()
    trackWorld({}, { "Minimap" })
    local d = timerDrawer()
    eq(d._parent, Minimap.fsBezel, "a child of the key row, so it scales with the map")
    eq(d._points[1][2], Minimap.fsBezel)
    eq(d._points[1][3], "BOTTOMLEFT")
end

function T.the_quest_timer_falls_back_to_the_stock_minimap_while_the_minimap_module_is_off()
    trackWorld({ "m.mini" }, { "Minimap" })
    loaded("Modules/Tracker/QuestTimer.lua")
    local d = timerDrawer()
    eq(Minimap.fsBezel, nil)
    eq(d._parent, UIParent)
    eq(#d._points, 1)
    eq(d._points[1][1], "TOPRIGHT"); eq(d._points[1][2], Minimap); eq(d._points[1][3], "BOTTOMRIGHT")
    eq(TouchesOn("Minimap", "Modules/Tracker/QuestTimer.lua"), "", "anchored to, never written to")
end

function T.the_quest_timer_waits_for_a_minimap_that_is_ours_but_not_built_yet()
    -- logged in during a fight: the minimap's build waits for the end of it, and the timer must not seat under the stock map
    trackWorld({}, { "Minimap" }, { combat = true, noRegen = true })
    eq(Minimap.fsBezel, nil, "the map is not built yet")
    no(MadeNamed("ForeverSTUwaveQuestTimer"), "no drawer under the stock map while ours is coming")
    InCombatLockdown = function() return false end
    Fire("PLAYER_REGEN_ENABLED")
    yes(Minimap.fsBezel, "built at the end of the fight")
    FS.QuestTimer.Refresh()
    local d = timerDrawer()
    eq(d._parent, Minimap.fsBezel)
end

function T.the_quest_timer_lays_out_again_on_a_new_grid_when_the_minimap_scale_changes()
    trackWorld({}, { "Minimap" })
    local d = timerDrawer()
    local before = FS.QuestTimer.Pixels()
    yes(#__tickers > 0, "a paint ticker runs while a timer shows")
    rawset(d, "GetEffectiveScale", function() return 1.5 end)   -- the map's Scale is now 150%: the drawer inherits it
    for _, t in ipairs(__tickers) do if not t.cancelled then t.fn() end end
    local after = FS.QuestTimer.Pixels()
    eq(after.scale, 1.5)
    yes(math.abs(after.k / before.k - 1.5) < 0.001, "a design px is 1.5 times as many physical pixels: " .. after.k .. " vs " .. before.k)
    yes(after.n >= before.n)
end

local BAGS_FILES = { "Modules/Bags/Bags.lua", "Modules/Bags/BagBar.lua" }
local BAGS_BLIZZARD = { "MicroButtonAndBagsBar", "BagsBar", "MainMenuBarBackpackButton", "CharacterBag0Slot", "CharacterBag1Slot",
    "KeyRingButton", "BagBarExpandToggle", "ContainerFrame1", "ContainerFrameCombinedBags", "BankFrame" }
local bagCallbacks
local function bagsWorld(off)
    bagCallbacks = 0
    Boot({ off = off, watch = BAGS_BLIZZARD, pre = function()
        WatchPanel("ContainerFrame1"); WatchPanel("ContainerFrameCombinedBags"); WatchPanel("BankFrame")
        EventRegistry = { RegisterCallback = function() bagCallbacks = bagCallbacks + 1 end }
    end })
    Fire("BAG_UPDATE"); Fire("BAG_UPDATE_DELAYED"); Fire("GAME_PAD_ACTIVE_CHANGED"); Fire("PLAYER_REGEN_ENABLED"); Fire("PLAYER_MONEY")
    Fire("UI_SCALE_CHANGED")
end

function T.bags_off_builds_no_bar_hooks_no_bag_frame_and_dims_nothing()
    bagsWorld({ "m.bags" })
    for _, f in ipairs(BAGS_FILES) do loaded(f) end
    eq(FS.ModuleSwitch.Built("m.bags"), false)
    eq(BuiltBy("Modules/Bags/Bags.lua"), 0)
    eq(BuiltBy("Modules/Bags/BagBar.lua"), 0, "no bar, no secure slot buttons")
    no(MadeNamed("ForeverSTUwaveBagBar"))
    eq(bagCallbacks, 0, "no container open or close callback")
    for _, name in ipairs(BAGS_BLIZZARD) do
        for _, f in ipairs(BAGS_FILES) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
    end
end

function T.bags_off_keeps_its_tables_defined_and_inert()
    bagsWorld({ "m.bags" })
    eq(type(FS.BagBar), "table"); eq(FS.BagBar.bar, nil); eq(#FS.BagBar.slots, 0)
    FS.BagBar.Refresh()
    FS.BagBar.HideBlizzardBar()
    eq(type(FS.BagHighlight), "table")
    FS.BagHighlight.Set(1); FS.BagHighlight.Clear()
    eq(type(FS.BagsWindow), "table")
    -- (the bank window is also a Window skins frame, so only the bag files' own touches are counted)
    for _, name in ipairs(BAGS_BLIZZARD) do
        for _, f in ipairs(BAGS_FILES) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
    end
end

function T.bags_on_builds_the_bar_dims_the_stock_bag_bar_and_skins_the_bag_frames_as_before()
    bagsWorld({})
    for _, f in ipairs(BAGS_FILES) do loaded(f) end
    eq(FS.ModuleSwitch.Built("m.bags"), true)
    yes(MadeNamed("ForeverSTUwaveBagBar"))
    yes(FS.BagBar.bar and #FS.BagBar.slots > 0)
    yes(bagCallbacks > 0, "the open and close callbacks are installed")
    yes(TouchesOn("MicroButtonAndBagsBar", "Modules/Bags/BagBar.lua") ~= "", "the stock bag bar is dimmed")
    yes(TouchesOn("ContainerFrame1", "Modules/Bags/Bags.lua") ~= "", "the bag frames are skinned")
end

local SKINS_BLIZZARD = { "CharacterFrame", "InspectFrame", "MailFrame", "PlayerSpellsFrame", "QuestFrame", "GossipFrame",
    "MerchantFrame", "StaticPopup1", "GameTooltip", "LossOfControlFrame", "ChatAlertFrame", "ZoneTextFrame", "ErrorsFrame",
    "ShardTransferImminentFrame", "DamageMeter", "HelpTip", "WorldMapFrame", "AddonList", "FriendsFrame", "TokenFrame" }
local function skinsWorld(off)
    Boot({ off = off, watch = SKINS_BLIZZARD, pre = function()
        for _, name in ipairs({ "CharacterFrame", "InspectFrame", "MailFrame", "PlayerSpellsFrame", "QuestFrame", "GossipFrame",
            "MerchantFrame", "StaticPopup1", "WorldMapFrame", "AddonList", "FriendsFrame", "TokenFrame" }) do
            WatchPanel(name)
        end
        rawset(_G.GossipFrame, "GreetingPanel", false)   -- the game builds this child later; the skin tests it before use
        function GameTooltip_SetDefaultAnchor() end
        function PaperDollFrame_UpdateStats() end
        function EquipmentFlyout_Show() end
        function GetProfessions() return 1 end
        function GetProfessionInfo() return "Mining", "icon", 10, 75 end
    end })
    Fire("PLAYER_ENTERING_WORLD", false, false); Fire("PLAYER_REGEN_ENABLED"); Fire("MAIL_SHOW"); Fire("INSPECT_READY")
    Fire("UI_SCALE_CHANGED"); Fire("SKILL_LINES_CHANGED")
    for _, e in ipairs({ "Blizzard_PlayerSpells", "Blizzard_InspectUI", "Blizzard_Communities" }) do Fire("ADDON_LOADED", e) end
    local timers = __timers
    __timers = {}
    for _, fn in ipairs(timers) do pcall(fn) end
end

function T.window_skins_off_builds_none_hooks_nothing_and_touches_no_blizzard_window()
    skinsWorld({ "m.skins" })
    eq(FS.ModuleSwitch.Built("m.skins"), false)
    for _, f in ipairs(__skinFiles) do
        loaded(f)
        eq(BuiltBy(f), 0, f .. " built nothing")
        eq(TouchesOn("hooksecurefunc", f), "", f .. " hooked nothing")
        for _, name in ipairs(SKINS_BLIZZARD) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
    end
    no(MadeNamed("FSTooltipAnchor"), "no tooltip anchor")
    no(MadeNamed("ForeverSTUwaveProfessions"), "no professions panel")
    eq(SlashCmdList["FSPROF"], nil, "no /fsprof while the panel is off")
end

function T.window_skins_off_keeps_the_shared_helpers_defined()
    skinsWorld({ "m.skins" })
    eq(type(FS.PanelSkins.DeferCombat), "function"); eq(type(FS.PanelSkins.WatchAddonLoad), "function")
    eq(type(FS.PanelSkins.WhenSkinsOn), "function"); eq(type(FS.PanelSkins.RegisterInspect), "function")
    eq(type(FS.TooltipAnchor.Repoint), "function"); eq(type(FS.TooltipAnchor.Install), "function")
    eq(type(FS.DamageMeterSkin), "table")
    FS.PanelSkins.DeferCombat(function() end)   -- a runtime call is not refused
    local ran = false
    FS.PanelSkins.WhenSkinsOn(function() ran = true end)
    eq(ran, true, "a call made after ADDON_LOADED runs at once")
    eq(TouchesOn("GameTooltip"), "")
end

function T.window_skins_on_builds_and_skins_the_game_windows_as_before()
    skinsWorld({})
    eq(FS.ModuleSwitch.Built("m.skins"), true)
    -- only the files this gate edits are held to a clean load here: the rest of the skin files are exercised against real
    -- window shapes by their own harnesses, and this world's stand-in windows are only deep enough for the first few
    for _, f in ipairs({ "Modules/Skins/Popups.lua", "Modules/Skins/Character.lua", "Modules/Skins/TooltipAnchor.lua",
        "Modules/Skins/Professions.lua", "Core/PanelSkins.lua" }) do loaded(f) end
    yes(MadeNamed("FSTooltipAnchor"), "the tooltip anchor")
    yes(TouchesOn("StaticPopup1", "Modules/Skins/Popups.lua") ~= "", "the popup is skinned")
    yes(TouchesOn("CharacterFrame", "Modules/Skins/Character.lua") ~= "", "the character window is skinned")
    yes(TouchesOn("hooksecurefunc", "Modules/Skins/TooltipAnchor.lua") ~= "", "the default anchor hook is installed")
    yes(MadeNamed("ForeverSTUwaveProfessions"), "the professions panel")
    eq(type(SlashCmdList["FSPROF"]), "function")
end

function T.the_layout_editor_gives_the_tooltip_and_professions_no_handle_while_window_skins_are_off()
    skinsWorld({ "m.skins" })
    local LE = FS.LayoutEdit
    if type(LE) == "table" and type(LE.HasHandle) == "function" then
        eq(LE.HasHandle("tooltip"), false); eq(LE.HasHandle("professions"), false)
    end
end


-- ---- B5b: action bars (m.ab), addon tabs (m.class), Gunsight HUD (m.gs), pet bar (m.pet) -----------------------------------
--
-- The same tolerant client, with the stand-ins these four modules need to run to the end on: the action button fields, the
-- unit and action APIs. Every row then plays the events the modules answer (a fight, a form change, a pet, a rescale) and the
-- slash commands that act on the stock bars, so an "off" module has to stay silent through all of them, not only at load.

local B5B = {
    ["m.ab"] = {
        files = { "Modules/ActionBars/ActionBars.lua", "Modules/ActionBars/Console.lua", "Modules/ActionBars/ConsoleKeys.lua",
            "Modules/ActionBars/StanceBar.lua", "Modules/ActionBars/MicroBars.lua", "Modules/ActionBars/ClassShoulder.lua" },
        named = { "FSActionBarStack", "FSConsole", "FSConsoleTab", "FSStanceBar" },
        blizzard = { "MainActionBar", "MultiBarBottomLeft", "MultiBarBottomRight", "MultiBarRight", "MultiBarLeft", "MultiBar5",
            "MultiBar6", "MultiBar7", "OverrideActionBar", "MultiCastActionBarFrame", "StanceBar", "MicroMenu", "MicroMenuContainer" },
    },
    ["m.pet"] = {
        files = { "Modules/Pet/PetFrame.lua", "Modules/Pet/PetActionBar.lua", "Modules/Pet/PetCastBar.lua" },
        named = { "FSPetContainer" },
        blizzard = { "PetActionBar" },
    },
    ["m.class"] = {
        files = { "Modules/ActionBars/SealBar.lua", "Modules/ActionBars/ShapeshiftTab.lua", "Modules/ActionBars/CallPetTab.lua",
            "Modules/ActionBars/PortalsTab.lua", "Modules/ActionBars/ConjureTab.lua", "Modules/ActionBars/PoisonsTab.lua",
            "Modules/ActionBars/DemonTab.lua", "Modules/ActionBars/TotemBar.lua", "Modules/ActionBars/TotemDial.lua",
            "Modules/ActionBars/ShamanBuffs.lua", "Modules/ActionBars/BuffTab.lua", "Modules/ActionBars/FiveSecondTab.lua",
            "Modules/ActionBars/ThunderClapTab.lua", "Modules/ActionBars/AmmoTab.lua" },
        named = { "FSShapeshiftTab", "FSCallPetTab", "FSPortalsTab", "FSConjureTab", "FSPoisonsTab", "FSDemonTab", "FSSealBar",
            "FSTotemBar", "FSBuffTab", "FSFiveSecondTab", "FSThunderClapTab", "FSAmmoTab", "FSTotemDialTicker" },
        blizzard = {},
    },
}
local B5B_HOOKED = { "ActionButtonDown", "ActionButtonUp", "MultiActionButtonDown", "MultiActionButtonUp", "MicroButtonPulse",
    "MicroButtonPulseStop" }
local B5B_EVENTS = {
    { "UI_SCALE_CHANGED" }, { "DISPLAY_SIZE_CHANGED" }, { "UPDATE_BINDINGS" }, { "ACTIONBAR_SLOT_CHANGED", 0 },
    { "ACTIONBAR_PAGE_CHANGED" }, { "UPDATE_BONUS_ACTIONBAR" }, { "UPDATE_SHAPESHIFT_FORM" }, { "UPDATE_SHAPESHIFT_FORMS" },
    { "PET_BAR_UPDATE" }, { "UNIT_PET", "player" }, { "UNIT_AURA", "player" }, { "PLAYER_TOTEM_UPDATE", 1 }, { "SPELLS_CHANGED" },
    { "PLAYER_TARGET_CHANGED" }, { "UNIT_HEALTH", "pet" }, { "UNIT_POWER_UPDATE", "player" }, { "PLAYER_ENTERING_WORLD", false, false },
}
local B5B_SLASH = { { "FSBARS", "blizz" }, { "FSBARS", "fs" }, { "FSTAINT", "stash" }, { "FSCONSOLE", "off" }, { "FSCONSOLE", "on" },
    { "FSPET", "unlock" }, { "FSPET", "reset" }, { "FSPET", "lock" } }

local function b5bStubs()
    date = os.date
    __combat = false
    InCombatLockdown = function() return __combat end
    for name, value in pairs({ UnitXP = 0, UnitXPMax = 100, UnitHealth = 100, UnitHealthMax = 100, UnitPower = 0, UnitPowerMax = 100,
        UnitLevel = 12, GetBindingText = "" }) do
        _G[name] = function() return value end
    end
    UnitPowerType = function() return 0, "MANA" end
    GetBindingKey = function() end
    Watch("Minimap")
    for _, n in ipairs({ "HasAction", "GetActionTexture", "GetActionInfo", "IsUsableAction", "IsActionInRange", "IsCurrentAction",
        "IsAutoRepeatAction", "IsAttackAction", "GetActionCooldown", "GetActionCount", "GetActionText", "IsConsumableAction",
        "IsStackableAction", "IsEquippedAction", "GetActionCharges", "GetActionLossOfControlCooldown", "IsPlayerSpell",
        "IsSpellKnown", "GetSpellInfo", "GetSpellTexture", "GetSpellCooldown", "GetNumShapeshiftForms", "GetShapeshiftForm",
        "GetShapeshiftFormInfo", "GetShapeshiftFormCooldown", "GetActionBarPage", "GetBonusBarOffset", "GetOverrideBarIndex",
        "HasOverrideActionBar", "HasVehicleActionBar", "HasBonusActionBar", "GetPetActionInfo", "GetPetActionCooldown",
        "GetPetActionsUsable", "PetHasActionBar", "UnitAffectingCombat", "GetTotemInfo", "GetItemCount", "GetItemInfo",
        "GetInventoryItemID", "GetInventorySlotInfo" }) do
        if _G[n] == nil then _G[n] = function() end end
    end
    for _, n in ipairs(B5B_HOOKED) do _G[n] = function() end end
    -- the pieces of an action button the stock template brings and the code reads as fields
    local base = CreateFrame
    CreateFrame = function(kind, name, parent, template)
        local f = base(kind, name, parent, template)
        rawset(f, "TextOverlayContainer", false)
        if template and tostring(template):find("ActionButtonTemplate") then
            for _, k in ipairs({ "NormalTexture", "PushedTexture", "HighlightTexture", "CheckedTexture", "QuickKeybindHighlightTexture" }) do
                rawset(f, k, f:CreateTexture())
            end
            for _, k in ipairs({ "HotKey", "Count", "Name" }) do rawset(f, k, f:CreateFontString()) end
            rawset(f, "UpdateFlyout", false)
        end
        return f
    end
end

-- every Blizzard frame any of the four modules may touch is watched; `off` is the saved store
local function b5bWorld(off, extra)
    local watch = {}
    for _, module in pairs(B5B) do
        for _, name in ipairs(module.blizzard) do watch[#watch + 1] = name end
    end
    Boot({ off = off, watch = watch, pre = function() b5bStubs(); if extra then extra() end end })
    for _, ev in ipairs(B5B_EVENTS) do Fire(unpack(ev)) end
    __combat = true
    Fire("PLAYER_REGEN_DISABLED"); Fire("UPDATE_SHAPESHIFT_FORM"); Fire("PET_BAR_UPDATE"); Fire("UNIT_PET", "player")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    for _, pair in ipairs(B5B_SLASH) do
        local fn = SlashCmdList[pair[1]]
        if fn then pcall(fn, pair[2]) end
    end
    local timers = __timers
    __timers = {}
    for _, fn in ipairs(timers) do pcall(fn) end
end

local function b5bClean(key)
    local module = B5B[key]
    for _, f in ipairs(module.files) do loaded(f) end
end

local function b5bNotBuilt(key)
    local module = B5B[key]
    eq(FS.ModuleSwitch.On(key), false)
    eq(FS.ModuleSwitch.Built(key), false, key .. " built nothing")
    for _, f in ipairs(module.files) do eq(BuiltBy(f), 0, f .. " made no frame after the files loaded") end
    for _, name in ipairs(module.named) do no(MadeNamed(name), name .. " exists") end
    for _, f in ipairs(module.files) do
        for _, name in ipairs(module.blizzard) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
        eq(TouchesOn("hooksecurefunc", f), "", f .. " hooked nothing")
    end
end

function T.action_bars_off_builds_nothing_and_leaves_every_stock_bar_alone()
    b5bWorld({ "m.ab" })
    b5bClean("m.ab")
    b5bNotBuilt("m.ab")
end

function T.action_bars_off_keeps_the_api_and_the_slash_commands_answer_without_touching_the_stock_bars()
    b5bWorld({ "m.ab" })
    local A = FS.ActionBars
    eq(type(A), "table", "FS.ActionBars stays defined")
    eq(type(A.OnGeometry), "function"); eq(type(A.SetConsoleActive), "function"); eq(type(A.LivePage), "function")
    eq(A.geometry, nil, "no stack, no geometry: the Console has nothing to follow")
    eq(type(FS.Console), "table"); eq(type(FS.StanceBar), "table"); eq(type(FS.ConsoleKeys), "table")
    eq(type(SlashCmdList["FSBARS"]), "function")
    yes(#__printed > 0)
    for _, f in ipairs(B5B["m.ab"].files) do
        for _, name in ipairs(B5B["m.ab"].blizzard) do eq(TouchesOn(name, f), "", name .. " untouched by " .. f) end
    end
end

function T.action_bars_on_builds_the_stack_dims_the_stock_bars_and_marks_itself_built()
    b5bWorld({})
    b5bClean("m.ab")
    eq(FS.ModuleSwitch.Built("m.ab"), true)
    for _, name in ipairs(B5B["m.ab"].named) do yes(MadeNamed(name), name .. " exists") end
    for _, name in ipairs({ "MainActionBar", "MultiBarBottomLeft", "StanceBar", "MicroMenu" }) do
        yes(TouchesOn(name) ~= "", name .. " dimmed")
    end
end

function T.pet_bar_off_builds_nothing_and_leaves_the_stock_pet_bar_alone()
    b5bWorld({ "m.pet" })
    b5bClean("m.pet")
    b5bNotBuilt("m.pet")
    eq(BuiltBy("Modules/Pet/PetDock.lua", "Modules/ActionBars/ClassShoulder.lua"), 0, "no dock chrome")
    eq(FS.PetFrame.container, nil)
    eq(FS.PetFrame.barSlot, nil)
end

function T.pet_bar_off_keeps_its_api_defined_and_the_pet_commands_say_so()
    b5bWorld({ "m.pet" })
    eq(type(FS.PetFrame), "table"); eq(type(FS.PetCastBar), "table"); eq(type(FS.PetDock), "table")
    eq(FS.PetFrame.SeatDocked(UIParent, 0), false, "nothing to dock")
    eq(FS.PetFrame.SeatFloat(), false)
    eq(FS.PetFrame.IsDocked(), false)
    eq(type(SlashCmdList["FSPET"]), "function")
    __printed = {}
    SlashCmdList["FSPET"]("reset")
    yes(#__printed > 0, "the command answers")
    eq(ErrorsFrom("Modules/Pet/PetFrame.lua"), "")
end

function T.pet_bar_on_builds_the_panel_dims_the_stock_pet_bar_and_marks_itself_built()
    b5bWorld({})
    b5bClean("m.pet")
    eq(FS.ModuleSwitch.Built("m.pet"), true)
    yes(MadeNamed("FSPetContainer"), "the pet panel")
    yes(FS.PetFrame.container and FS.PetFrame.barSlot and FS.PetFrame.castSlot, "exported")
    yes(TouchesOn("PetActionBar", "Modules/Pet/PetFrame.lua") ~= "", "the stock pet bar is hidden")
end

-- a Warlock's class tabs stand right of the pet panel's span; with the pet bar off there is no panel to clear
local function standingFrom(off)
    b5bWorld(off, function() UnitClass = function() return "Warlock", "WARLOCK", 9 end end)
    local least
    if FS.ClassShoulder and FS.ClassShoulder.EachStanding then
        FS.ClassShoulder.EachStanding(function(dx) if least == nil or dx < least then least = dx end end)
    end
    return least
end

function T.the_class_tabs_stand_close_to_the_console_edge_when_there_is_no_pet_bar_to_clear()
    local with = standingFrom({})
    local without = standingFrom({ "m.pet" })
    yes(with ~= nil, "a tab stands in this world")
    yes(without ~= nil, "a tab stands with the pet bar off")
    yes(without < with, "the tabs moved left by the pet span: " .. tostring(without) .. " against " .. tostring(with))
end

-- the tabs by class: what each class's tab is called when it stands (the mock client has no spells, so the host frame is the
-- evidence), and the class numbers
local B5B_CLASSES = {
    DRUID = { id = 11, host = "FSShapeshiftTab" }, HUNTER = { id = 3, host = "FSCallPetTab" }, MAGE = { id = 8, host = "FSPortalsTab" },
    PALADIN = { id = 2, host = "FSSealBar" }, ROGUE = { id = 4, host = "FSPoisonsTab" }, SHAMAN = { id = 7, host = "FSTotemBar" },
    WARLOCK = { id = 9, host = "FSDemonTab" }, WARRIOR = { id = 1, host = "FSThunderClapTab" },
}
local function classWorld(off, token)
    b5bWorld(off, function() UnitClass = function() return token, token, B5B_CLASSES[token].id end end)
end

local function tabsOffRow(token)
    classWorld({ "m.class" }, token)
    b5bClean("m.class")
    b5bNotBuilt("m.class")
    local standing = 0
    FS.ClassShoulder.EachStanding(function() standing = standing + 1 end)
    eq(standing, 0, "no class shoulder stands")
    eq(FS.ShapeshiftTab.OwnsForms(), false, "the Druid forms stay with the stance bar")
    eq(FS.SealBar.OwnsForms(), false, "the Paladin forms stay with the stance bar")
    eq(type(FS.TotemBar), "table"); eq(type(FS.BuffTab), "table"); eq(type(FS.FiveSecondTab), "table")
    eq(type(FS.AmmoTab), "table"); eq(type(FS.ThunderClapTab), "table"); eq(type(FS.TotemPresets), "table")
end

local function tabsOnRow(token)
    classWorld({}, token)
    b5bClean("m.class")
    eq(FS.ModuleSwitch.Built("m.class"), true)
    yes(MadeNamed(B5B_CLASSES[token].host), token .. " tab " .. B5B_CLASSES[token].host)
end

function T.addon_tabs_off_draw_nothing_for_a_druid() tabsOffRow("DRUID") end
function T.addon_tabs_off_draw_nothing_for_a_hunter() tabsOffRow("HUNTER") end
function T.addon_tabs_off_draw_nothing_for_a_mage() tabsOffRow("MAGE") end
function T.addon_tabs_off_draw_nothing_for_a_paladin() tabsOffRow("PALADIN") end
function T.addon_tabs_off_draw_nothing_for_a_rogue() tabsOffRow("ROGUE") end
function T.addon_tabs_off_draw_nothing_for_a_shaman() tabsOffRow("SHAMAN") end
function T.addon_tabs_off_draw_nothing_for_a_warlock() tabsOffRow("WARLOCK") end
function T.addon_tabs_off_draw_nothing_for_a_warrior() tabsOffRow("WARRIOR") end

function T.addon_tabs_on_draw_the_druid_tab() tabsOnRow("DRUID") end
function T.addon_tabs_on_draw_the_hunter_tab() tabsOnRow("HUNTER") end
function T.addon_tabs_on_draw_the_mage_tabs() tabsOnRow("MAGE"); yes(MadeNamed("FSConjureTab")) end
function T.addon_tabs_on_draw_the_paladin_seal_bar() tabsOnRow("PALADIN") end
function T.addon_tabs_on_draw_the_rogue_tab() tabsOnRow("ROGUE") end
function T.addon_tabs_on_draw_the_shaman_totem_and_buff_tabs() tabsOnRow("SHAMAN"); yes(MadeNamed("FSBuffTab")); yes(MadeNamed("FSTotemDialTicker")) end
function T.addon_tabs_on_draw_the_warlock_tab() tabsOnRow("WARLOCK") end
function T.addon_tabs_on_draw_the_warrior_tab() tabsOnRow("WARRIOR") end

function T.the_mana_regen_and_ammo_tabs_follow_the_same_switch()
    classWorld({ "m.class" }, "HUNTER")
    no(MadeNamed("FSFiveSecondTab")); no(MadeNamed("FSAmmoTab"))
end

function T.the_stock_totem_bar_is_dimmed_only_while_the_totem_tab_stands_in_for_it()
    local AB = "Modules/ActionBars/ActionBars.lua"
    classWorld({ "m.class" }, "SHAMAN")
    eq(TouchesOn("MultiCastActionBarFrame", AB), "", "the stock totem bar stays as the game has it")
    eq(TouchesOn("MultiBarBottomLeft", AB) ~= "", true, "the other stock bars are still dimmed (Action bars are on)")
end

function T.the_stock_totem_bar_is_dimmed_when_the_totem_tab_is_on()
    classWorld({}, "SHAMAN")
    yes(TouchesOn("MultiCastActionBarFrame", "Modules/ActionBars/ActionBars.lua") ~= "", "dimmed, as before")
end

function T.addon_tabs_need_the_action_bars_because_every_tab_stands_on_the_console()
    Boot({})
    local list = FS.ModuleSwitch.Requires("m.class")
    eq(#list, 1); eq(list[1], "m.ab")
    local deps = FS.ModuleSwitch.Dependents("m.ab")
    local found = false
    for _, k in ipairs(deps) do if k == "m.class" then found = true end end
    yes(found, "turning the action bars off lists the tabs")
end

-- The Gunsight HUD is every file of Modules/CombatHud except HunterState, which the Hunter's ammo tab (Addon tabs) also runs.
local function hudFiles()
    local list = {}
    for _, rel in ipairs(__toc) do
        if rel:find("^Modules/CombatHud/") and rel ~= "Modules/CombatHud/HunterState.lua" then list[#list + 1] = rel end
    end
    return list
end
local B5B_GS_HOST = {
    DRUID = "ForeverSTUwaveGunsightDruid", HUNTER = "ForeverSTUwaveGunsightHunter", MAGE = "ForeverSTUwaveGunsightMage",
    PALADIN = "ForeverSTUwaveGunsightSeals", PRIEST = "ForeverSTUwaveGunsightPriest", ROGUE = "ForeverSTUwaveGunsightRogue",
    SHAMAN = "ForeverSTUwaveGunsightShaman", WARLOCK = "ForeverSTUwaveGunsightWarlock", WARRIOR = "ForeverSTUwaveGunsightWarrior",
}
B5B_CLASSES.PRIEST = { id = 5 }

local function gunsightNotBuilt()
    eq(FS.ModuleSwitch.On("m.gs"), false)
    eq(FS.ModuleSwitch.Built("m.gs"), false, "nothing was built")
    for _, f in ipairs(hudFiles()) do
        loaded(f)
        eq(BuiltBy(f, "Modules/ActionBars/AmmoTab.lua"), 0, f .. " made no frame after the files loaded")
    end
    for _, name in pairs(B5B_GS_HOST) do no(MadeNamed(name), name .. " exists") end
    for _, name in ipairs({ "ForeverSTUwaveCombatHud", "ForeverSTUwaveWarriorPowerUps", "ForeverSTUwaveDruidClearcasting",
        "ForeverSTUwaveGunsightTargetSide", "ForeverSTUwaveGunsightTargetMenu", "ForeverSTUwaveGunsightMyBuffs" }) do
        no(MadeNamed(name), name .. " exists")
    end
end

local function gunsightOffRow(token)
    classWorld({ "m.gs" }, token)
    gunsightNotBuilt()
end

function T.gunsight_off_builds_nothing_for_a_druid() gunsightOffRow("DRUID") end
function T.gunsight_off_builds_nothing_for_a_hunter() gunsightOffRow("HUNTER") end
function T.gunsight_off_builds_nothing_for_a_mage() gunsightOffRow("MAGE") end
function T.gunsight_off_builds_nothing_for_a_paladin() gunsightOffRow("PALADIN") end
function T.gunsight_off_builds_nothing_for_a_priest() gunsightOffRow("PRIEST") end
function T.gunsight_off_builds_nothing_for_a_rogue() gunsightOffRow("ROGUE") end
function T.gunsight_off_builds_nothing_for_a_shaman() gunsightOffRow("SHAMAN") end
function T.gunsight_off_builds_nothing_for_a_warlock() gunsightOffRow("WARLOCK") end
function T.gunsight_off_builds_nothing_for_a_warrior() gunsightOffRow("WARRIOR") end

function T.gunsight_off_keeps_the_api_and_says_it_is_not_the_display()
    classWorld({ "m.gs" }, "SHAMAN")
    local G = FS.Gunsight
    eq(type(G), "table", "FS.Gunsight stays defined")
    eq(G.IsActive(), false, "the stack A cast bars are the display")
    eq(G.IsEnabled(), false)
    eq(type(G.OnReady), "function"); eq(type(G.OnActiveChanged), "function"); eq(type(G.SetPiece), "function")
    eq(type(FS.Hud), "table"); eq(type(FS.CombatHud), "table")
    eq(FS.CombatHud.IsEnabled(), false, "the classic combat HUD is part of the module and stays off too")
    eq(type(SlashCmdList["FSGUN"]), "function")
    __printed = {}
    SlashCmdList["FSGUN"]("on")
    SlashCmdList["FSHUD"]("on")
    yes(#__printed > 0, "the commands answer")
    eq(FS.CombatHud.IsEnabled(), false, "/fshud on does not build it")
    no(MadeNamed("ForeverSTUwaveCombatHud"))
end

function T.gunsight_off_leaves_the_console_keys_that_are_not_the_hud_standing()
    classWorld({ "m.gs" }, "PRIEST")
    yes(FS.ConsoleKeys.IsBuilt(), "the party, quest and chat keys are built")
    eq(FS.ConsoleKeys.ShownCount(), 3, "party, quests and chat: no HUD key is drawn")
    for _, k in ipairs(FS.ConsoleKeys.keys) do
        local hud = k.key ~= "party" and k.key ~= "quests" and k.key ~= "chat"
        if hud then no(k.shown, k.key .. " is a HUD key") end
    end
end

local function gunsightOnRow(token)
    classWorld({}, token)
    for _, f in ipairs(hudFiles()) do loaded(f) end
    eq(FS.ModuleSwitch.Built("m.gs"), true)
    eq(FS.Gunsight.IsEnabled(), true)
    yes(MadeNamed("ForeverSTUwaveGunsight"))
    yes(MadeNamed(B5B_GS_HOST[token]), B5B_GS_HOST[token])
end

function T.gunsight_on_builds_the_druid_pieces() gunsightOnRow("DRUID") end
function T.gunsight_on_builds_the_hunter_pieces() gunsightOnRow("HUNTER") end
function T.gunsight_on_builds_the_mage_pieces() gunsightOnRow("MAGE") end
function T.gunsight_on_builds_the_paladin_pieces() gunsightOnRow("PALADIN") end
function T.gunsight_on_builds_the_priest_pieces() gunsightOnRow("PRIEST") end
function T.gunsight_on_builds_the_rogue_pieces() gunsightOnRow("ROGUE") end
function T.gunsight_on_builds_the_shaman_pieces() gunsightOnRow("SHAMAN"); yes(BuiltBy("Modules/CombatHud/GunsightTape.lua") > 0, "the tapes") end
function T.gunsight_on_builds_the_warlock_pieces() gunsightOnRow("WARLOCK") end
function T.gunsight_on_builds_the_warrior_pieces() gunsightOnRow("WARRIOR"); yes(MadeNamed("ForeverSTUwaveWarriorPowerUps")) end

function T.the_hunter_ammo_tab_still_has_its_state_with_the_gunsight_off()
    classWorld({ "m.gs" }, "HUNTER")
    yes(MadeNamed("FSAmmoTab"), "the ammo tab is the Addon tabs module's, not the HUD's")
    eq(type(FS.HunterState), "table")
end

-- ---- every pair of the four off together ------------------------------------------------------------------------------
-- The two that are off build nothing, the two that are on build as they do alone, and no module file raises an error through
-- the fight, the shapeshift, the pet summon and the slash commands. A Hunter (pet, ammo tab) and a Shaman (totems, the drop)
-- are the two classes that reach the most of the four.
local B5B_PAIR_HOST = { m_ab = "FSActionBarStack", m_pet = "FSPetContainer", m_gs = "ForeverSTUwaveGunsight" }

local function pairRow(a, b, token)
    classWorld({ a, b }, token)
    local MS = FS.ModuleSwitch
    local function isOff(key) return key == a or key == b end
    for _, key in ipairs({ "m.ab", "m.class", "m.gs", "m.pet" }) do eq(MS.On(key), not isOff(key), key .. " switch") end
    b5bClean("m.ab"); b5bClean("m.class"); b5bClean("m.pet")
    for _, f in ipairs(hudFiles()) do loaded(f) end
    -- what is off is not built
    for _, key in ipairs({ "m.ab", "m.class", "m.pet" }) do
        if isOff(key) then b5bNotBuilt(key) end
    end
    if isOff("m.gs") then gunsightNotBuilt() end
    -- what is on is built as it is alone
    if not isOff("m.ab") then
        eq(MS.Built("m.ab"), true, "action bars built"); yes(MadeNamed("FSActionBarStack"), "the stack")
    end
    if not isOff("m.pet") then
        eq(MS.Built("m.pet"), true, "pet bar built"); yes(MadeNamed("FSPetContainer"), "the pet panel")
    end
    if not isOff("m.gs") then
        eq(MS.Built("m.gs"), true, "Gunsight built"); yes(MadeNamed("ForeverSTUwaveGunsight"), "the Gunsight root")
    end
    if not isOff("m.class") and not isOff("m.ab") then
        eq(MS.Built("m.class"), true, "tabs built"); yes(MadeNamed(B5B_CLASSES[token].host), "the " .. token .. " tab")
    end
    -- a tab with no action bars under it is never seated or shown (a store that turns the tabs on and the bars off by hand
    -- still builds the tab frames, empty and hidden), and the Console is not made
    if isOff("m.ab") then
        no(MadeNamed("FSConsole"), "no Console")
        local standing = 0
        FS.ClassShoulder.EachStanding(function() standing = standing + 1 end)
        eq(standing, 0, "no class shoulder stands without the Console")
        for _, f in ipairs(B5B["m.class"].files) do eq(ErrorsFrom(f), "", f .. " raised no error") end
    end
    -- the Blizzard frames of the off modules were never touched (the on modules dim theirs, as they do alone)
    for _, key in ipairs({ "m.ab", "m.pet" }) do
        if isOff(key) then
            for _, name in ipairs(B5B[key].blizzard) do
                for _, file in ipairs(B5B[key].files) do eq(TouchesOn(name, file), "", name .. " untouched by " .. file) end
            end
        end
    end
end

function T.pair_action_bars_and_addon_tabs_off_for_a_hunter() pairRow("m.ab", "m.class", "HUNTER") end
function T.pair_action_bars_and_gunsight_off_for_a_hunter() pairRow("m.ab", "m.gs", "HUNTER") end
function T.pair_action_bars_and_pet_bar_off_for_a_hunter() pairRow("m.ab", "m.pet", "HUNTER") end
function T.pair_addon_tabs_and_gunsight_off_for_a_hunter() pairRow("m.class", "m.gs", "HUNTER") end
function T.pair_addon_tabs_and_pet_bar_off_for_a_hunter() pairRow("m.class", "m.pet", "HUNTER") end
function T.pair_gunsight_and_pet_bar_off_for_a_hunter() pairRow("m.gs", "m.pet", "HUNTER") end
function T.pair_action_bars_and_addon_tabs_off_for_a_shaman() pairRow("m.ab", "m.class", "SHAMAN") end
function T.pair_action_bars_and_gunsight_off_for_a_shaman() pairRow("m.ab", "m.gs", "SHAMAN") end
function T.pair_action_bars_and_pet_bar_off_for_a_shaman() pairRow("m.ab", "m.pet", "SHAMAN") end
function T.pair_addon_tabs_and_gunsight_off_for_a_shaman() pairRow("m.class", "m.gs", "SHAMAN") end
function T.pair_addon_tabs_and_pet_bar_off_for_a_shaman() pairRow("m.class", "m.pet", "SHAMAN") end
function T.pair_gunsight_and_pet_bar_off_for_a_shaman() pairRow("m.gs", "m.pet", "SHAMAN") end

function T.all_four_off_together_still_loads_and_runs_clean()
    classWorld({ "m.ab", "m.class", "m.gs", "m.pet" }, "SHAMAN")
    for _, key in ipairs({ "m.ab", "m.class", "m.pet" }) do b5bClean(key); b5bNotBuilt(key) end
    for _, f in ipairs(hudFiles()) do loaded(f) end
    gunsightNotBuilt()
end

-- the Deck holds the micro bar (action bars) and the bag bar (bags): it is built while either is on, never when both are off
function T.the_deck_is_built_with_only_the_bags_on()
    classWorld({ "m.ab" }, "SHAMAN")
    yes(MadeNamed("ForeverSTUwaveDeck"), "the deck stands for the bag bar")
    loaded("Modules/ActionBars/Deck.lua")
end

function T.the_deck_is_built_with_only_the_action_bars_on()
    classWorld({ "m.bags" }, "SHAMAN")
    yes(MadeNamed("ForeverSTUwaveDeck"), "the deck stands for the micro bar")
    loaded("Modules/ActionBars/Deck.lua")
end

function T.the_deck_is_not_built_with_the_action_bars_and_the_bags_both_off()
    classWorld({ "m.ab", "m.bags" }, "SHAMAN")
    no(MadeNamed("ForeverSTUwaveDeck"), "no deck")
    no(MadeNamed("ForeverSTUwaveDeckMicroSlot")); no(MadeNamed("ForeverSTUwaveDeckBagSlot"))
    loaded("Modules/ActionBars/Deck.lua"); loaded("Modules/ActionBars/MicroBars.lua"); loaded("Modules/Bags/BagBar.lua")
end

function T.the_deck_is_built_with_both_on()
    classWorld({}, "SHAMAN")
    yes(MadeNamed("ForeverSTUwaveDeck"))
    loaded("Modules/ActionBars/Deck.lua")
end

return T
"""

_TOC_SOURCES: dict[str, str] = {}
GATE_NAMES: list[str] = []


def toc_files() -> list[str]:
    return [ln.strip() for ln in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("##") and ln.strip().endswith(".lua")]


def read_toc_file(rel: str) -> str:
    if rel not in _TOC_SOURCES:
        _TOC_SOURCES[rel] = (ADDON / rel).read_text(encoding="utf-8")
    return _TOC_SOURCES[rel]


def run_gate_checks() -> int:
    """Each gate row runs in a fresh mock client (the whole .toc loads in about 0.2 s). Returns the failure count."""
    global GATE_NAMES
    GATE_NAMES = re.findall(r"^function T\.([a-z0-9_]+)\(", GATE_CHECKS, re.M)
    failed = 0
    for name in GATE_NAMES:
        try:
            lua = base.LuaRuntime(unpack_returned_tuples=True, register_eval=False)
            lua.execute(GATE_WORLD)
            lua.globals().__toc = lua.table_from(toc_files())
            lua.globals().__read = read_toc_file
            lua.globals().__skinFiles = lua.table_from([f for f in toc_files() if f.startswith("Modules/Skins/")])
            checks = lua.execute(GATE_CHECKS)
            checks[name]()
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:2])[:500]}")
    return failed


# ---- python level checks ----------------------------------------------------------------------------------------------

def check_the_files_are_clean() -> list[str]:
    problems = []
    for path in (MS_FILE, MODULES_FILE):
        text = path.read_text(encoding="utf-8")
        if "\u2014" in text or "\u2013" in text:
            problems.append(f"{path.name}: an em or en dash")
        if re.search(r"\bReloadUI\s*\(", text):
            problems.append(f"{path.name}: calls ReloadUI (addon code cannot reload; the secure button does)")
        if re.search(r"\b(loadstring|setfenv)\b", text):
            problems.append(f"{path.name}: loadstring or setfenv")
        if re.search(r"\btape\b", text, re.I):
            problems.append(f"{path.name}: the word tape")
    return problems


def check_the_toc_loads_the_store_before_the_pages_that_gate_on_it() -> list[str]:
    toc = [ln.strip() for ln in (ADDON / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("##")]
    problems = []
    for want in ("Core/Config.lua", "Core/ModuleSwitch.lua", "Modules/Config/ConfigModules.lua"):
        if want not in toc:
            problems.append(f"{want} is not in the toc")
    if not problems:
        if toc.index("Core/Config.lua") > toc.index("Core/ModuleSwitch.lua"):
            problems.append("ModuleSwitch.lua must load after Config.lua (it reads Config.IsReadOnly)")
        gated = [t for t in toc if t.startswith("Modules/") and not t.startswith("Modules/Config/") and t != "Modules/Nameplates/Nameplates.lua"]
        late = [t for t in gated if toc.index(t) < toc.index("Core/ModuleSwitch.lua")]
        if late:
            problems.append(f"modules load before the store: {late}")
        if toc.index("Modules/Config/ConfigModules.lua") < toc.index("Modules/Config/ConfigWindow.lua"):
            problems.append("ConfigModules.lua loads before ConfigWindow.lua")
    return problems


def check_the_footer_count_reads_the_pending_switches() -> list[str]:
    src = MODULES_FILE.read_text(encoding="utf-8")
    problems = []
    if "CW.AddReloadSource" not in src or "MS.PendingKeys()" not in src:
        problems.append("ConfigModules.lua must hand MS.PendingKeys() to the footer through CW.AddReloadSource")
    return problems


def main() -> int:
    failed = run_lua_checks()
    failed += run_gate_checks()
    py_checks = [
        ("the_files_are_clean", check_the_files_are_clean),
        ("the_footer_count_reads_the_pending_switches", check_the_footer_count_reads_the_pending_switches),
        ("the_toc_loads_the_store_before_the_pages_that_gate_on_it", check_the_toc_loads_the_store_before_the_pages_that_gate_on_it),
    ]
    total = len(CHECK_NAMES) + len(GATE_NAMES) + len(py_checks)
    for name, fn in py_checks:
        try:
            problems = fn()
        except Exception as err:  # noqa: BLE001 (report the failure, keep going)
            problems = [f"{type(err).__name__}: {err}"]
        if problems:
            failed += 1
            print(f"FAIL  {name}: {'; '.join(problems)[:600]}")
        else:
            print(f"ok    {name}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
