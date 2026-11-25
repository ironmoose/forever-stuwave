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

function T.a_pending_reload_marks_the_row_the_nav_count_and_the_registry_and_clears_when_turned_back()
    local W = msboot()
    W.Open("modules")
    local entry = W.RowByKey("m.cast", "modules")
    no(anyText("RELOAD"), "no tag yet")
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
    no(anyText("RELOAD"), "turning both back clears the tag")
    no(chip(), "and the count")
    errorsClean()
end

function T.a_live_row_has_no_reload_tag()
    local W = msboot()
    W.Open("modules")
    yes(press_label("Nameplates"))
    eq(MS().Wanted("m.np"), false)
    no(anyText("RELOAD"))
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
    local self = { _label = label, _scripts = {}, _events = {}, _hooks = {}, _regions = {} }
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
    elseif k == "GetChildren" or k == "GetRegions" or k == "GetPoint" then
        return function() end
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
C_Timer = { After = function(_, fn) __timers[#__timers + 1] = fn end, NewTicker = function(_, fn) return { Cancel = function() end } end }
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
    Fire("PLAYER_REGEN_ENABLED")
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


def main() -> int:
    failed = run_lua_checks()
    failed += run_gate_checks()
    py_checks = [
        ("the_files_are_clean", check_the_files_are_clean),
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
