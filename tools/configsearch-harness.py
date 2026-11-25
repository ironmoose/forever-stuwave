#!/usr/bin/env python3
"""Checks for the /fsconfig search box (ticket B1).

Runs the real ConfigWindow.lua, every page file and ConfigSearch.lua over the mock frames of tools/configwindow-harness.py
(the same way tools/configlayout-harness.py does) and pins:

  * the box in CW.SearchSlot(): the > prompt, the placeholder, the clear x, the cyan edge on focus, Esc twice
  * the index: every registered row, extended as tabs build, nothing built or rebuilt by typing, a query inside 5 ms
  * the ranking table (label prefix, substring, section, tip, loose letters, spaces ignored, shorter label first)
  * the results panel: sizes from SPEC, the highlight, the dim reason, the nothing found line, the scroll past RES_MAX
  * keys and mouse: Up, Down, Enter, hover, click, the wheel, all / changed only
  * the jump: CW.Open, the unfolded section, the cyan outline (fade in, held until a click or a new search)
  * rows behind a `when` gate: the class strip and the Style frame picker are set before the scroll
  * the hidden pre build: one tab per frame, paused in combat, the page and tab you were on kept

The mock does no anchor layout, so geometry is checked from the recorded points. Everything drawn is pending owner review.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEARCH_FILE = ROOT / "forever-stuwave" / "Modules" / "Config" / "ConfigSearch.lua"

spec = importlib.util.spec_from_file_location("configwindow_harness", HERE / "configwindow-harness.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
LuaError = base.LuaError

CHECKS = r"""
-- ---- fixtures and helpers --------------------------------------------------------------------------------------------

local function searchOf(W)
    local S = W.Search
    yes(S, "CW.Search exists")
    return S
end

-- Two tabs shaped like the prototype's: cast bars and a folded mana regen section on one, totems and threat on the other.
local function fixture(W, opts)
    opts = opts or {}
    local built = { a = 0, b = 0 }
    FS.Config.RegisterDefault("fx.ycast", true)
    FS.Config.RegisterDefault("fx.tcast", true)
    FS.Config.RegisterDefault("fx.glow", 40)
    W.RegisterCategory({ key = "fx", label = "Fixture", group = "GENERAL", order = 70, tabs = {
        { key = "a", label = "Pieces", build = function(c)
            built.a = built.a + 1
            local U = W.UI
            U.Section(c, { title = "Cast bars", tip = "Where your casts show." })
            U.Toggle(c, { label = "Your cast bar", key = "fx.ycast" })
            U.Toggle(c, { label = "Target cast bar", key = "fx.tcast", tip = "The bar under the target frame." })
            U.Toggle(c, { label = "Cast bar spark", key = "fx.spark", sub = true, needs = "fx.tcast", nl = "Target cast bar" })
            U.Section(c, { title = "Mana regen", fold = true })
            U.Toggle(c, { label = "Regen pulse", key = "fx.pulse" })
            U.Toggle(c, { label = "Regen sound", key = "fx.sound", tip = "Plays a tick when mana regen starts." })
            U.Section(c, { title = "Threat" })
            U.Toggle(c, { label = "Show threat", key = "fx.threat" })
            U.Slider(c, { label = "Aggro glow", key = "fx.glow", min = 0, max = 100, step = 5, fmt = "%d%%",
                tip = "Border strength when a mob is on you." })
        end },
        { key = "b", label = "Other", build = function(c)
            built.b = built.b + 1
            local U = W.UI
            U.Section(c, { title = "Totems" })
            U.Toggle(c, { label = "Totem presets", key = "fx.totem" })
            U.Toggle(c, { label = "Show totem timers", key = "fx.ttimer" })
            U.Section(c, { title = "Odd ones" })
            U.Toggle(c, { label = "Hidden by a switch", key = "fx.odd", when = function() return opts.oddOn == true end })
        end },
    } })
    return built
end

local function filler(W, count)
    W.RegisterCategory({ key = "fl", label = "Filler", group = "GENERAL", order = 71, build = function(c)
        W.UI.Section(c, { title = "Many" })
        for i = 1, count do
            W.UI.Toggle(c, { label = "Filler " .. i, key = "fl.k" .. i, tip = "Row number " .. i .. " of the filler page." })
        end
    end })
end

local function openAll(W)
    for _, cat in ipairs(W.Categories()) do
        for _, tab in ipairs(cat.tabs) do W.Open(cat.key, tab.key) end
    end
end

-- Only the fixture's own tabs, so real page rows cannot change a ranking.
local function openFx(W)
    W.Open("fx", "a")
    W.Open("fx", "b")
end

-- Focuses the box and types; the mock does not fire OnTextChanged from SetText, so the check calls it as the client does.
local function typeText(S, text)
    S.edit:SetFocus()
    S.edit:SetText(text)
    S.edit.scripts.OnTextChanged(S.edit, true)
end

local function labels(list)
    local out = {}
    for i, r in ipairs(list) do out[i] = r.item.label end
    return out
end

local function firstLabel(S, text, changed)
    local list = S.Run(text, changed)
    return list[1] and list[1].item.label or nil
end

local function shownRows(S)
    local out = {}
    for _, r in ipairs(S.rows) do if r:IsShown() then out[#out + 1] = r end end
    return out
end

local function plain(t) return (tostring(t or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end

local function entryOf(W, label)
    for _, e in ipairs(W.Rows()) do if e.label == label then return e end end
end

-- The outline is anchored to the row (the mock keeps SetParent a no-op, so the anchor is what a check can see).
local function onRow(hl, row)
    if not hl then return false end
    for _, p in ipairs(hl.points) do if p.rel == row then return true end end
    return false
end

local function frameCount() return #ALL end

local function pageScroll(W, page, tab)
    local rec = W.I.ui.tabs[page .. "/" .. tab]
    return rec and rec.page and rec.page:GetVerticalScroll() or nil
end

local function tickDriver(S)
    local d = S.driver
    yes(d and d.scripts.OnUpdate, "the pre build driver is running")
    d.scripts.OnUpdate(d, 0.016)
end

local function unbuilt(W)
    local n = 0
    for _, cat in ipairs(W.Categories()) do
        for _, tab in ipairs(cat.tabs) do
            local rec = W.I.ui.tabs[cat.key .. "/" .. tab.key]
            if not (rec and rec.built) then n = n + 1 end
        end
    end
    return n
end

-- Runs the pre build to the end (bounded: it fails rather than loops).
local function finishBuild(W, S)
    local guard = 0
    while unbuilt(W) > 0 and guard < 400 do tickDriver(S); guard = guard + 1 end
    eq(unbuilt(W), 0, "every tab built within " .. guard .. " ticks")
end

-- ---- the box ---------------------------------------------------------------------------------------------------------

function T.the_box_sits_in_the_search_slot_with_a_prompt_a_placeholder_and_a_clear_x()
    local W = boot()
    W.Open()
    local S = searchOf(W)
    local slot = W.SearchSlot()
    yes(S.box and S.box.parent == slot, "the box is a child of the search slot")
    local ok = false
    for _, p in ipairs(S.box.points) do if p.rel == slot then ok = true end end
    yes(ok, "the box is seated on the slot")
    eq(S.prompt:GetText(), ">", "the prompt cell")
    eq(S.placeholder:GetText(), "search settings")
    yes(S.placeholder:IsShown(), "the placeholder shows while the box is empty")
    no(S.clear:IsShown(), "no clear x while the box is empty")
    eq(S.edit.kind, "EditBox")
    typeText(S, "cast")
    no(S.placeholder:IsShown(), "the placeholder leaves with the first letter")
    yes(S.clear:IsShown(), "the clear x shows once there is text")
    S.clear.scripts.OnClick(S.clear, "LeftButton")
    eq(S.edit:GetText(), "", "the clear x empties the box")
    no(S.clear:IsShown())
    yes(S.edit:HasFocus(), "and keeps the keyboard in it")
end

function T.the_edge_is_cyan_while_the_box_has_focus_or_text_and_dim_otherwise()
    local W = boot()
    W.Open()
    local S = searchOf(W)
    local function ring() return S.box.fsSkin.border.ring.color end
    local idle = { ring()[1], ring()[2], ring()[3] }
    S.edit:SetFocus()
    local c = W.C.cyan
    eq(ring()[1], c[1], "cyan on focus"); eq(ring()[3], c[3])
    S.edit:ClearFocus()
    eq(ring()[1], idle[1], "back to the idle edge with nothing typed")
    typeText(S, "cast")
    S.edit:ClearFocus()
    eq(ring()[1], c[1], "stays cyan while there is text")
end

function T.esc_clears_the_box_and_a_second_esc_leaves_it()
    local W = boot()
    W.Open()
    fixture(W)
    local S = searchOf(W)
    typeText(S, "cast")
    yes(S.panel:IsShown(), "results are up")
    S.edit.scripts.OnEscapePressed(S.edit)
    eq(S.edit:GetText(), "", "the first Esc clears the box")
    yes(S.edit:HasFocus(), "and keeps the focus")
    no(S.panel:IsShown(), "and closes the results")
    S.edit.scripts.OnEscapePressed(S.edit)
    no(S.edit:HasFocus(), "the second Esc leaves the box")
end

function T.esc_with_changed_only_on_clears_the_filter_first()
    local W = boot()
    W.Open()
    fixture(W)
    FS.Config.Set("fx.ycast", false)
    local S = searchOf(W)
    typeText(S, "cast")
    S.changedOnly.scripts.OnClick(S.changedOnly, "LeftButton")
    eq(S.state.changed, true)
    typeText(S, "")
    yes(S.panel:IsShown(), "the filter alone keeps the list up")
    S.edit.scripts.OnEscapePressed(S.edit)
    eq(S.state.changed, false, "Esc turns the filter off")
    yes(S.edit:HasFocus())
    no(S.panel:IsShown())
end

function T.the_box_takes_the_keyboard_through_the_shared_focus_catcher()
    local W = boot()
    W.Open()
    local S = searchOf(W)
    S.edit:SetFocus()
    eq(W.I.sliderFocus, S.edit, "the shared focus handler knows the box")
    yes(W.I.focusCatcher and W.I.focusCatcher:IsShown(), "the catcher behind the window is up")
    W.I.focusCatcher.scripts.OnClick(W.I.focusCatcher)
    no(S.edit:HasFocus(), "a click elsewhere gives the keys back")
end

function T.tab_leaves_the_box()
    local W = boot()
    W.Open()
    local S = searchOf(W)
    S.edit:SetFocus()
    S.edit.scripts.OnTabPressed(S.edit)
    no(S.edit:HasFocus())
end

-- ---- the index and the ranking ---------------------------------------------------------------------------------------

function T.every_registered_row_is_in_the_index()
    local W = boot()
    openAll(W)
    local S = searchOf(W)
    local want, have = 0, {}
    for _, item in ipairs(S.Index()) do have[item.entry] = true end
    for _, e in ipairs(W.Rows()) do
        if e.kind ~= "note" and e.page and e.tab and type(e.label) == "string" and e.label ~= "" then
            want = want + 1
            yes(have[e], "not indexed: " .. e.page .. "/" .. e.tab .. " " .. e.label)
        end
    end
    yes(want > 30, "the registry has the real pages in it: " .. want)
    eq(#S.Index(), want, "nothing indexed twice or extra")
end

function T.the_index_grows_when_a_tab_builds_later()
    local W = boot()
    local built = fixture(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    eq(firstLabel(S, "totem"), nil, "the other tab was never built: nothing to find yet")
    W.Open("fx", "b")
    eq(firstLabel(S, "totem"), "Totem presets", "found once it is built")
    eq(built.b, 1)
end

local RANKS = {
    { "cast bar", "Cast bar spark", "label prefix beats substring" },
    { "castbar", "Cast bar spark", "spaces ignored" },
    { "cbar", "Your cast bar", "loose letters, the shorter label first" },
    { "regen", "Regen pulse", "label prefix, equal labels in build order" },
    { "mana regen", "Regen pulse", "section title" },
    { "totem", "Totem presets", "prefix beats substring" },
    { "threat", "Show threat", "label substring beats the section" },
    { "mob is on you", "Aggro glow", "tip text" },
    { "TOTEM", "Totem presets", "case ignored" },
    { "  cast   bar ", "Cast bar spark", "outer and inner spaces ignored" },
}

function T.the_ranking_table_puts_the_expected_row_first()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    for _, r in ipairs(RANKS) do
        eq(firstLabel(S, r[1]), r[2], r[1] .. " (" .. r[3] .. ")")
    end
end

function T.scores_run_prefix_then_substring_then_section_then_tip_then_letters()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    local function score(q, label)
        for _, r in ipairs(S.Run(q)) do if r.item.label == label then return r.score end end
        return 0
    end
    eq(score("cast bar", "Cast bar spark"), 5)
    eq(score("cast bar", "Your cast bar"), 4)
    eq(score("threat", "Aggro glow"), 3)
    eq(score("mob is on you", "Aggro glow"), 2)
    eq(score("cbar", "Your cast bar"), 1)
end

function T.loose_letters_need_three_or_more()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    eq(#S.Run("cb"), 0, "two letters never match loosely")
    yes(#S.Run("cba") >= 1, "three letters do")
    eq(#S.Run("zzzzq"), 0)
    eq(#S.Run(""), 0, "an empty box lists nothing")
end

function T.equal_scores_sort_by_the_shorter_label()
    local W = boot()
    W.RegisterCategory({ key = "tie", label = "Tie", order = 72, build = function(c)
        W.UI.Toggle(c, { label = "Glow strength", key = "tie.b" })
        W.UI.Toggle(c, { label = "Glow", key = "tie.a" })
        W.UI.Toggle(c, { label = "Glow edge soft", key = "tie.c" })
    end })
    W.Open("tie")
    local S = searchOf(W)
    eq(table.concat(labels(S.Run("glow")), "|"), "Glow|Glow strength|Glow edge soft")
end

function T.a_query_takes_under_five_ms_with_every_tab_indexed()
    local W = boot()
    fixture(W)
    filler(W, 600)
    openAll(W)
    local S = searchOf(W)
    local rows = #S.Index()
    yes(rows > 600, "a registry of realistic size: " .. rows)
    local worst = 0
    for _, q in ipairs({ "cast bar", "cbar", "a", "regen", "totem", "threat", "mana regen", "filler 5", "show" }) do
        local best = 1e9
        for _ = 1, 4 do
            local t0 = os.clock()
            S.Run(q)
            best = math.min(best, (os.clock() - t0) * 1000)
        end
        worst = math.max(worst, best)
    end
    yes(worst < 5, "slowest query " .. worst .. " ms")
end

function T.typing_never_builds_frames_or_tabs()
    local W = boot()
    local built = fixture(W)
    openFx(W)
    local S = searchOf(W)
    W.Open("fx", "a")
    typeText(S, "cast")
    local frames = frameCount()
    for _, q in ipairs({ "cast bar", "cbar", "totem", "regen", "zzzz", "", "threat", "mana regen", "a" }) do typeText(S, q) end
    eq(frameCount(), frames, "no frame was created by typing")
    eq(built.a, 1, "tab a built once"); eq(built.b, 1, "tab b built once")
end

-- ---- the results panel -----------------------------------------------------------------------------------------------

function T.the_panel_sits_over_the_well_with_the_spec_sizes()
    local W = boot()
    fixture(W)
    W.Open("fx", "a")
    openFx(W)
    local S = searchOf(W)
    local Sp = W.Spec
    typeText(S, "cast bar")
    local n = #S.Run("cast bar")
    yes(n >= 3 and n <= Sp.RES_MAX)
    local p = S.panel.points[1]
    eq(p.point, "TOPLEFT"); eq(p.rel, W.I.ui.well, "seated on the well"); eq(p.x, -1); eq(p.y, 1)
    eq(S.panel:GetWidth(), Sp.RES_W)
    eq(S.panel:GetHeight(), 2 + Sp.RES_HEAD_H + n * Sp.RES_ROW_H + Sp.RES_FOOT_H, "header, one row each, the keys line, two edges")
    local rows = shownRows(S)
    eq(#rows, n)
    for i, r in ipairs(rows) do
        eq(r:GetHeight(), Sp.RES_ROW_H); eq(r:GetWidth(), Sp.RES_W - 2)
        eq(r.points[1].y, -(1 + Sp.RES_HEAD_H + (i - 1) * Sp.RES_ROW_H), "row " .. i .. " sits under the one above")
    end
    eq(S.header.count:GetText(), n .. " FOUND")
    yes(S.footer:GetText():find("enter", 1, true), "the keys hint")
end

function T.each_result_shows_the_label_with_the_match_in_cyan_and_where_it_lives()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "cast bar")
    local r = shownRows(S)[1]
    eq(plain(r.fsL1:GetText()), "Cast bar spark")
    yes(r.fsL1:GetText():find("|cff22e0ff", 1, true), "the match is cyan")
    yes(r.fsL1:GetText():find("|cff22e0ffCast bar|r", 1, true), "exactly the matched letters")
    eq(plain(r.fsL2:GetText()), "Fixture > Pieces > Cast bars", "page, tab, section")
    typeText(S, "cbar")
    local l = shownRows(S)[1].fsL1:GetText()
    yes(l:find("|cff22e0ffc|r", 1, true) and l:find("|cff22e0ffb|r", 1, true), "loose letters are marked one by one: " .. l)
end

function T.a_one_tab_page_leaves_its_tab_out_of_the_breadcrumb()
    local W = boot()
    filler(W, 3)
    W.Open("fl")
    local S = searchOf(W)
    typeText(S, "filler 2")
    eq(plain(shownRows(S)[1].fsL2:GetText()), "Filler > Many")
end

function T.the_first_result_is_selected_and_the_keys_move_it()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "cast bar")
    eq(S.state.sel, 1)
    S.edit.scripts.OnArrowPressed(S.edit, "DOWN")
    eq(S.state.sel, 2)
    S.edit.scripts.OnArrowPressed(S.edit, "DOWN")
    S.edit.scripts.OnArrowPressed(S.edit, "DOWN")
    S.edit.scripts.OnArrowPressed(S.edit, "DOWN")
    eq(S.state.sel, 3, "clamped at the last result")
    S.edit.scripts.OnArrowPressed(S.edit, "UP")
    eq(S.state.sel, 2)
    S.edit.scripts.OnArrowPressed(S.edit, "UP")
    S.edit.scripts.OnArrowPressed(S.edit, "UP")
    eq(S.state.sel, 1, "clamped at the first")
    yes(shownRows(S)[1].fsSel:IsShown(), "the selected row has the cyan bar and tint")
    no(shownRows(S)[2].fsSel:IsShown())
end

function T.hover_selects_and_a_click_jumps()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "cast bar")
    local rows = shownRows(S)
    rows[3].scripts.OnEnter(rows[3])
    eq(S.state.sel, 3, "pointing at a result selects it")
    W.Open("profiles")
    typeText(S, "cast bar")
    shownRows(S)[2].scripts.OnClick(shownRows(S)[2], "LeftButton")
    local page, tab = W.Current()
    eq(page, "fx"); eq(tab, "a", "a click on a result opens its page and tab")
end

function T.the_list_scrolls_past_res_max()
    local W = boot()
    filler(W, 20)
    W.Open("fl")
    local S = searchOf(W)
    local Sp = W.Spec
    typeText(S, "filler")
    eq(#S.Run("filler"), 20)
    eq(S.header.count:GetText(), "20 FOUND", "the real count, not the page of it")
    eq(#shownRows(S), Sp.RES_MAX, "only RES_MAX rows are drawn")
    eq(S.panel:GetHeight(), 2 + Sp.RES_HEAD_H + Sp.RES_MAX * Sp.RES_ROW_H + Sp.RES_FOOT_H)
    eq(plain(shownRows(S)[1].fsL1:GetText()), "Filler 1")
    S.panel.scripts.OnMouseWheel(S.panel, -1)
    eq(S.state.top, 2, "the wheel scrolls the list a result at a time")
    eq(plain(shownRows(S)[1].fsL1:GetText()), "Filler 2")
    for _ = 1, 40 do S.panel.scripts.OnMouseWheel(S.panel, -1) end
    eq(S.state.top, 20 - Sp.RES_MAX + 1, "the wheel stops at the end")
    for _ = 1, 40 do S.panel.scripts.OnMouseWheel(S.panel, 1) end
    eq(S.state.top, 1)
    yes(S.state.sel >= 1 and S.state.sel <= Sp.RES_MAX, "the wheel keeps the selection in view")
    local base = S.state.sel
    for _ = 1, 10 do S.edit.scripts.OnArrowPressed(S.edit, "DOWN") end
    eq(S.state.sel, base + 10)
    yes(S.state.top > 1 and S.state.sel >= S.state.top and S.state.sel <= S.state.top + Sp.RES_MAX - 1, "the selection stays in view")
end

function T.nothing_found_says_so_and_the_box_keeps_focus()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "xyzzy")
    yes(S.panel:IsShown(), "the panel is still up")
    yes(S.empty:IsShown() and S.empty:GetText() == "Nothing matches.", "the nothing found line")
    eq(#shownRows(S), 0)
    eq(S.header.count:GetText(), "0 FOUND")
    yes(S.edit:HasFocus(), "the box keeps the keyboard")
    S.edit.scripts.OnEnterPressed(S.edit)
    yes(S.edit:HasFocus(), "Enter with nothing selected does nothing")
    typeText(S, "totem")
    no(S.empty:IsShown(), "the line goes when something matches")
end

-- ---- changed only, dim rows, module off ------------------------------------------------------------------------------

function T.changed_only_lists_every_changed_row_with_an_empty_box_and_narrows_a_query()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "x")
    S.changedOnly.scripts.OnClick(S.changedOnly, "LeftButton")
    typeText(S, "")
    eq(#S.Run("", true), 0, "nothing is changed yet")
    FS.Config.Set("fx.ycast", false)
    FS.Config.Set("fx.totem", true)
    FS.Config.Set("fx.glow", 90)
    local list = S.Run("", true)
    local seen = {}
    for _, r in ipairs(list) do seen[r.item.label] = true end
    eq(#list, 3, "exactly the changed rows: " .. table.concat(labels(list), ","))
    yes(seen["Your cast bar"] and seen["Totem presets"] and seen["Aggro glow"])
    eq(#W.ChangedKeys("fx"), 3, "the same rows CW.ChangedKeys counts")
    eq(table.concat(labels(S.Run("cast", true)), ","), "Your cast bar", "a query narrows the changed rows")
    typeText(S, "")
    S.changedOnly.scripts.OnClick(S.changedOnly, "LeftButton")
    eq(#shownRows(S), 3, "the panel lists them with an empty box")
    yes(shownRows(S)[1].fsBadgeText:GetText() == "CHANGED", "each says changed")
    S.all.scripts.OnClick(S.all, "LeftButton")
    eq(S.state.changed, false)
end

function T.the_filter_buttons_are_pink_when_on()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "cast")
    local pink = W.C.pink
    eq(S.all.fsLabel.themeColor[1], pink[1], "all is on")
    S.changedOnly.scripts.OnClick(S.changedOnly, "LeftButton")
    eq(S.changedOnly.fsLabel.themeColor[1], pink[1], "changed only is on")
    no(S.all.fsLabel.themeColor[1] == pink[1])
end

function T.a_disabled_row_shows_dim_with_its_reason()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    FS.Config.Set("fx.tcast", false)
    typeText(S, "cast bar spark")
    local r = shownRows(S)[1]
    eq(plain(r.fsL1:GetText()), "Cast bar spark")
    eq(r.fsDim, true, "the row is dim")
    eq(r.fsBadgeText:GetText(), "NEEDS TARGET CAST BAR")
    yes(plain(S.footer:GetText()):find("Requires Target cast bar to be on.", 1, true), "the footer carries the reason line: " .. S.footer:GetText())
    FS.Config.Set("fx.tcast", true)
    typeText(S, "cast bar spark")
    eq(shownRows(S)[1].fsDim, false, "dim follows the parent switch")
end

function T.an_enabled_function_row_carries_its_reason()
    local W = boot()
    local on = false
    W.RegisterCategory({ key = "en", label = "En", order = 73, build = function(c)
        W.UI.Toggle(c, { label = "Needs a pet", key = "en.pet", enabled = function() return on end, reason = "Needs a hunter pet." })
    end })
    W.Open("en")
    local S = searchOf(W)
    typeText(S, "needs a pet")
    local r = shownRows(S)[1]
    eq(r.fsDim, true)
    yes(plain(S.footer:GetText()):find("Needs a hunter pet.", 1, true), S.footer:GetText())
    on = true
    typeText(S, "needs a pet")
    eq(shownRows(S)[1].fsDim, false)
end

function T.rows_of_a_module_that_is_off_say_module_off()
    local W = boot()
    fixture(W)
    openFx(W)
    local wanted = true
    FS.ModuleSwitch = {
        Keys = function() return { "m.fx" } end, Page = function() return "fx" end, Label = function() return "Fixture bars" end,
        Wanted = function() return wanted end,
    }
    local S = searchOf(W)
    typeText(S, "totem")
    eq(shownRows(S)[1].fsDim, false, "on: nothing says otherwise")
    wanted = false
    typeText(S, "totem")
    local r = shownRows(S)[1]
    eq(r.fsDim, true); eq(r.fsBadgeText:GetText(), "MODULE OFF")
    yes(plain(S.footer:GetText()):find("Fixture bars is off.", 1, true), S.footer:GetText())
    FS.ModuleSwitch = nil
    typeText(S, "totem")
    eq(shownRows(S)[1].fsDim, false, "no module switch store: no flag")
end

-- ---- the jump --------------------------------------------------------------------------------------------------------

function T.enter_opens_the_page_and_tab_unfolds_the_section_and_outlines_the_row()
    local W = boot()
    fixture(W)
    openFx(W)
    W.Open("profiles")
    local S = searchOf(W)
    no(entryOf(W, "Regen pulse").row:IsShown(), "folded at the start")
    local jumps = {}
    W.On("jump", function(entry) jumps[#jumps + 1] = entry.label end)
    typeText(S, "regen pulse")
    S.edit.scripts.OnEnterPressed(S.edit)
    local page, tab = W.Current()
    eq(page, "fx"); eq(tab, "a")
    local e = entryOf(W, "Regen pulse")
    yes(e.row:IsShown(), "the section unfolded")
    eq(e.secObj.folded, false)
    eq(W.IsFolded("fx/a/Mana regen", true), false, "and the fold is remembered")
    eq(jumps[#jumps], "Regen pulse", "the jump event fired through CW.Open")
    local hl = S.hilite
    yes(onRow(hl, e.row) and hl:IsShown(), "the outline is on the row")
    eq(S.edit:GetText(), "", "the box is empty")
    no(S.edit:HasFocus(), "and gives the keys back")
    no(S.panel:IsShown(), "the panel is closed")
    local scroll = pageScroll(W, "fx", "a")
    yes(scroll and scroll >= 0, "the row was scrolled into view")
end

function T.a_far_row_is_scrolled_to_near_the_top()
    local W = boot()
    filler(W, 60)
    W.Open("profiles")
    local S = searchOf(W)
    S.edit:SetFocus()
    finishBuild(W, S)
    typeText(S, "filler 55")
    S.edit.scripts.OnEnterPressed(S.edit)
    local e = entryOf(W, "Filler 55")
    local page = W.I.FindScrollPage(e.row)
    yes(page:GetVerticalScroll() > 0, "scrolled down")
    eq(page:GetVerticalScroll(), math.min(page.fsRange, e.row.fsItem.y - W.Spec.SEC_H), "to the row, a section height below the top")
    yes(e.row:IsShown())
end

function T.the_outline_fades_in_over_a_third_of_a_second_and_holds()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "show threat")
    S.edit.scripts.OnEnterPressed(S.edit)
    local hl = S.hilite
    eq(hl:GetAlpha(), 0, "starts clear")
    hl.scripts.OnUpdate(hl, 0.15)
    yes(math.abs(hl:GetAlpha() - 0.5) < 0.01, "half way after 0.15 s: " .. hl:GetAlpha())
    hl.scripts.OnUpdate(hl, 0.3)
    eq(hl:GetAlpha(), 1, "full after 0.3 s")
    for _ = 1, 50 do hl.scripts.OnUpdate(hl, 1) end
    yes(hl:IsShown() and hl:GetAlpha() == 1, "and it holds")
    -- the edges are cyan one pixel lines
    yes(#hl.fsEdges == 4)
    eq(hl.fsEdges[1].color[1], W.C.cyan[1])
    eq(hl.fsEdges[1].h, 1)
end

function T.the_outline_goes_on_the_next_click_or_a_new_search()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    local down = true
    IsMouseButtonDown = function() return down end
    typeText(S, "show threat")
    S.edit.scripts.OnEnterPressed(S.edit)
    local hl = S.hilite
    hl.scripts.OnUpdate(hl, 0.05)
    yes(hl:IsShown(), "the click that jumped does not end it")
    down = false
    hl.scripts.OnUpdate(hl, 0.05)
    yes(hl:IsShown(), "released")
    down = true
    hl.scripts.OnUpdate(hl, 0.05)
    no(hl:IsShown(), "the next click ends it")
    -- a new search ends it too
    typeText(S, "show threat")
    S.edit.scripts.OnEnterPressed(S.edit)
    yes(S.hilite:IsShown())
    typeText(S, "t")
    no(S.hilite:IsShown(), "typing a new search ends it")
    IsMouseButtonDown = nil
end

function T.jump_highlight_is_the_public_outline_other_lanes_call()
    local W = boot()
    fixture(W)
    openFx(W)
    W.Open("fx", "a")
    local e = entryOf(W, "Show threat")
    W.Open("fx", "a", "fx.threat")
    local S = searchOf(W)
    yes(onRow(S.hilite, e.row) and S.hilite:IsShown(), "CW.Open with a row key outlines it through CW.JumpHighlight")
    local e2 = entryOf(W, "Regen pulse")
    W.JumpHighlight(e2)
    eq(e2.secObj.folded, false, "a caller that skips the search still gets the section unfolded")
    yes(onRow(S.hilite, e2.row) and e2.row:IsShown())
    W.Open("profiles")
    no(S.hilite:IsShown(), "changing tab drops the outline")
end

function T.a_row_the_key_does_not_name_alone_is_still_reached()
    local W = boot()
    W.RegisterCategory({ key = "dup", label = "Dup", order = 74, tabs = {
        { key = "x", label = "X", build = function(c) W.UI.Toggle(c, { label = "Same key one", key = "dup.k" }) end },
        { key = "y", label = "Y", build = function(c) W.UI.Toggle(c, { label = "Same key two", regKey = "dup.k", get = function() return true end, set = function() end }) end },
    } })
    W.Open("dup", "x"); W.Open("dup", "y"); W.Open("profiles")
    local S = searchOf(W)
    typeText(S, "same key two")
    S.edit.scripts.OnEnterPressed(S.edit)
    local _, tab = W.Current()
    eq(tab, "y", "the row's own tab, not the first row with that key")
    yes(onRow(S.hilite, entryOf(W, "Same key two").row), "and its own row")
end

function T.a_row_without_a_key_is_reached_too()
    local W = boot()
    W.RegisterCategory({ key = "nk", label = "Nk", order = 75, build = function(c)
        W.UI.Button(c, { label = "Do the thing", text = "RUN", onClick = function() end })
    end })
    W.Open("nk"); W.Open("profiles")
    local S = searchOf(W)
    typeText(S, "do the thing")
    S.edit.scripts.OnEnterPressed(S.edit)
    eq((W.Current()), "nk")
    yes(S.hilite and S.hilite:IsShown(), "outlined")
end

-- ---- rows behind a `when` gate ---------------------------------------------------------------------------------------

local function classFixture(W)
    FS.Config.RegisterDefault("fx.portal", false)
    W.ExtendTab("tabs", "general", { title = "Fixture mage bar", when = W.ClassWhen("MAGE") }, function(c)
        W.UI.Toggle(c, { label = "Portal bar", key = "fx.portal" })
    end)
    W.ExtendTab("tabs", "general", { title = "Fixture priest bar", when = W.ClassWhen("PRIEST") }, function(c)
        W.UI.Toggle(c, { label = "Prayer bar", key = "fx.prayer" })
    end)
end

function T.a_row_for_another_class_shows_the_class_in_its_breadcrumb_and_sets_the_strip_on_a_jump()
    local W = boot()
    classFixture(W)
    UnitClass = function() return "Warrior", "WARRIOR" end
    W.Open("tabs")
    local S = searchOf(W)
    eq(W.ClassView(), "WARRIOR")
    typeText(S, "portal bar")
    local r = shownRows(S)[1]
    eq(plain(r.fsL1:GetText()), "Portal bar")
    yes(plain(r.fsL2:GetText()):find("Fixture mage bar", 1, true), r.fsL2:GetText())
    yes(plain(r.fsL2:GetText()):match("Mage$"), "the class closes the breadcrumb: " .. plain(r.fsL2:GetText()))
    eq(r.fsDim, false, "a gated row is not dim: the jump can reach it")
    no(entryOf(W, "Portal bar").row:IsShown(), "hidden while the strip shows a Warrior")
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(W.ClassView(), "MAGE", "the class strip was set")
    eq(W.UIState("tabsCls"), "MAGE", "in the account window state")
    yes(entryOf(W, "Portal bar").row:IsShown(), "and the row is on screen")
    yes(onRow(S.hilite, entryOf(W, "Portal bar").row), "outlined")
    yes(#__errors == 0)
    -- Priest is another class on the same strip
    typeText(S, "prayer bar")
    yes(plain(shownRows(S)[1].fsL2:GetText()):match("Priest$"))
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(W.ClassView(), "PRIEST")
end

function T.finding_the_gate_value_leaves_the_strip_where_it_was()
    local W = boot()
    classFixture(W)
    UnitClass = function() return "Warrior", "WARRIOR" end
    W.Open("tabs")
    local S = searchOf(W)
    for _, q in ipairs({ "portal bar", "prayer bar", "portal bar" }) do typeText(S, q) end
    eq(W.ClassView(), "WARRIOR", "typing never moves the strip")
    eq(W.UIState("tabsCls"), nil, "nor writes it")
end

function T.a_row_on_another_frame_sets_the_style_picker_first()
    local W = boot()
    FS.FrameStyle = { LABELS = { player = "Player", target = "Target", focus = "Focus", boss = "Boss" } }
    FS.Config.RegisterDefault("bars.module", "target")
    FS.Config.RegisterDefault("fx.bossonly", false)
    W.ExtendTab("unit", "bars", { title = "Fixture boss extras", when = function() return FS.Config.Get("bars.module") == "boss" end }, function(c)
        W.UI.Toggle(c, { label = "Boss crown", key = "fx.bossonly" })
    end)
    W.ExtendTab("unit", "bars", { title = "Fixture target extras", when = function() return FS.Config.Get("bars.module") == "target" end }, function(c)
        W.UI.Toggle(c, { label = "Target crown", key = "fx.targetonly" })
    end)
    W.Open("unit", "bars")
    local S = searchOf(W)
    typeText(S, "boss crown")
    local r = shownRows(S)[1]
    yes(plain(r.fsL2:GetText()):match("Boss$"), "the frame closes the breadcrumb: " .. plain(r.fsL2:GetText()))
    eq(r.fsDim, false)
    eq(FS.Config.Get("bars.module"), "target", "typing leaves the picker alone")
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(FS.Config.Get("bars.module"), "boss", "the picker was set")
    yes(entryOf(W, "Boss crown").row:IsShown(), "the row shows")
    yes(onRow(S.hilite, entryOf(W, "Boss crown").row))
    typeText(S, "target crown")
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(FS.Config.Get("bars.module"), "target")
    yes(entryOf(W, "Target crown").row:IsShown())
end

function T.a_lane_can_register_its_own_gate()
    local W = boot()
    local pick = "one"
    yes(W.SearchGate({
        id = "fx.pick", page = "gt", tab = "main",
        values = function() return { { value = "one", text = "One" }, { value = "two", text = "Two" } } end,
        set = function(v) pick = v end,
        with = function(v, fn) local old = pick; pick = v; local ok, res = pcall(fn); pick = old; return ok and res end,
    }))
    no(W.SearchGate({ page = "gt" }), "a gate without functions is refused")
    W.RegisterCategory({ key = "gt", label = "Gt", order = 76, build = function(c)
        W.UI.Section(c, { title = "Two only", when = function() return pick == "two" end })
        W.UI.Toggle(c, { label = "Second thing", key = "gt.second" })
    end })
    W.Open("gt")
    local S = searchOf(W)
    typeText(S, "second thing")
    yes(plain(shownRows(S)[1].fsL2:GetText()):match("Two$"))
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(pick, "two")
    yes(entryOf(W, "Second thing").row:IsShown())
end

function T.a_row_no_gate_can_show_is_flagged_hidden_and_the_jump_stops_at_its_section()
    local W = boot()
    fixture(W)
    openFx(W)
    W.Open("profiles")
    local S = searchOf(W)
    typeText(S, "hidden by a switch")
    local r = shownRows(S)[1]
    eq(r.fsDim, true)
    eq(r.fsBadgeText:GetText(), "HIDDEN")
    S.edit.scripts.OnEnterPressed(S.edit)
    local page, tab = W.Current()
    eq(page, "fx"); eq(tab, "b", "the tab still opens")
    yes(not S.hilite or not S.hilite:IsShown(), "no outline on a row that is not there")
    eq(#__errors, 0)
end

-- ---- the hidden pre build --------------------------------------------------------------------------------------------

function T.the_first_focus_builds_the_tabs_nobody_opened_one_per_frame()
    local W = boot()
    local built = fixture(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    local before = unbuilt(W)
    yes(before > 20, "most tabs are unbuilt: " .. before)
    eq(built.b, 0)
    S.edit:SetFocus()
    for i = 1, 3 do
        local n = unbuilt(W)
        tickDriver(S)
        eq(unbuilt(W), n - 1, "tick " .. i .. " builds exactly one tab")
    end
    local guard = 0
    while unbuilt(W) > 0 and guard < 400 do tickDriver(S); guard = guard + 1 end
    eq(unbuilt(W), 0, "every tab is built after " .. guard .. " ticks")
    eq(built.b, 1, "the fixture's second tab was built once")
    eq(built.a, 1, "and the first was not rebuilt")
    yes(S.driver.scripts.OnUpdate == nil, "the driver stops when there is nothing left")
    eq(firstLabel(S, "totem presets"), "Totem presets", "and its rows are searchable")
end

function T.the_pre_build_keeps_the_page_the_tab_the_scroll_and_the_typed_text()
    local W = boot()
    fixture(W)
    filler(W, 60)
    W.Open("fl")
    local rec = W.I.ui.tabs["fl/main"]
    rec.page:SetVerticalScroll(120)
    W.CW = W
    local tabForBefore = {}
    for k, v in pairs(W.I.ui.tabFor or {}) do tabForBefore[k] = v end
    local S = searchOf(W)
    S.edit:SetFocus()
    S.edit:SetText("abc")
    S.edit.scripts.OnTextChanged(S.edit, true)
    local selects = 0
    W.On("select", function() selects = selects + 1 end)
    local guard = 0
    while unbuilt(W) > 0 and guard < 400 do tickDriver(S); guard = guard + 1 end
    yes(selects > 0, "the flip went through the window's own Open")
    local page, tab = W.Current()
    eq(page, "fl"); eq(tab, "main", "back on the page you were on")
    eq(rec.page:GetVerticalScroll(), 120, "with the scroll where it was")
    eq(S.edit:GetText(), "abc", "the typed text survived the flips")
    yes(S.edit:HasFocus(), "and the focus")
    for k, v in pairs(tabForBefore) do eq(W.I.ui.tabFor[k], v, "the remembered tab of " .. k) end
    local extra = 0
    for k in pairs(W.I.ui.tabFor or {}) do if tabForBefore[k] == nil then extra = extra + 1 end end
    eq(extra, 0, "no page gained a remembered tab it never had")
    eq(S.state.text, "abc")
end

function T.the_pre_build_pauses_in_combat_and_resumes_after()
    local W = boot()
    fixture(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    S.edit:SetFocus()
    tickDriver(S)
    local n = unbuilt(W)
    __combat = true
    for _ = 1, 5 do tickDriver(S) end
    eq(unbuilt(W), n, "nothing is built in combat")
    __combat = false
    tickDriver(S)
    eq(unbuilt(W), n - 1, "and it picks up after")
end

function T.the_pre_build_waits_while_the_window_is_closed()
    local W = boot()
    fixture(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    S.edit:SetFocus()
    local n = unbuilt(W)
    W.Close()
    for _ = 1, 3 do tickDriver(S) end
    eq(unbuilt(W), n, "a closed window builds nothing")
    W.Open("fx", "a")
    S.edit:SetFocus()
    tickDriver(S)
    eq(unbuilt(W), n - 1)
end

function T.the_window_hook_for_a_hidden_build_is_used_when_there_is_one()
    local W = boot()
    fixture(W)
    W.Open("fx", "a")
    local calls = {}
    W.BuildTabHidden = function(page, tab)
        calls[#calls + 1] = page .. "/" .. tab
        W.I.ui.tabs[page .. "/" .. tab] = { built = true }
        return true
    end
    local selects = 0
    W.On("select", function() selects = selects + 1 end)
    local S = searchOf(W)
    S.edit:SetFocus()
    tickDriver(S)
    eq(#calls, 1, "the hook built one tab")
    eq(selects, 0, "without touching the shown page")
end

function T.the_pre_build_refreshes_the_open_results_as_tabs_arrive()
    local W = boot()
    fixture(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    typeText(S, "totem")
    eq(S.header.count:GetText(), "0 FOUND", "tab b is not built yet")
    local guard = 0
    while unbuilt(W) > 0 and guard < 400 do tickDriver(S); guard = guard + 1 end
    yes(S.header.count:GetText() ~= "0 FOUND", "the list filled in: " .. S.header.count:GetText())
    eq(plain(shownRows(S)[1].fsL1:GetText()), "Totem presets")
end

-- ---- the window around it --------------------------------------------------------------------------------------------

function T.closing_the_window_clears_the_search_and_the_outline()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "show threat")
    S.edit.scripts.OnEnterPressed(S.edit)
    typeText(S, "cast")
    W.Close()
    eq(S.edit:GetText(), "", "text cleared")
    no(S.panel:IsShown()); no(S.hilite:IsShown())
    eq(S.state.changed, false)
end

function T.picking_a_page_or_tab_yourself_clears_the_search()
    local W = boot()
    fixture(W)
    openFx(W)
    W.Open("fx", "a")
    local S = searchOf(W)
    typeText(S, "cast")
    W.Open("fx", "b")
    eq(S.edit:GetText(), "", "a nav or tab click ends the search")
    no(S.panel:IsShown())
end

function T.the_results_close_when_the_box_loses_focus()
    local W = boot()
    fixture(W)
    openFx(W)
    local S = searchOf(W)
    typeText(S, "cast")
    yes(S.panel:IsShown())
    S.edit:ClearFocus()
    no(S.panel:IsShown(), "a click elsewhere puts the list away")
    eq(S.edit:GetText(), "cast", "the text stays")
    S.edit:SetFocus()
    yes(S.panel:IsShown(), "and it is back with the focus")
end

function T.opening_with_the_box_empty_shows_no_panel()
    local W = boot()
    W.Open()
    local S = searchOf(W)
    S.edit:SetFocus()
    no(S.panel:IsShown(), "nothing to list until you type or ask for changed only")
end

function T.search_on_a_page_open_in_combat_and_the_jump_never_touches_a_protected_frame()
    local W = boot()
    fixture(W)
    openFx(W)
    __combat = true
    local S = searchOf(W)
    typeText(S, "show threat")
    S.edit.scripts.OnEnterPressed(S.edit)
    eq(#BLOCKED, 0, "no blocked action")
    yes(S.hilite:IsShown())
    __combat = false
end
"""

CHECK_NAMES: set[str] = set()


def source_problems() -> list[str]:
    problems = []
    if not SEARCH_FILE.exists():
        return [f"{SEARCH_FILE} does not exist"]
    text = SEARCH_FILE.read_text(encoding="utf-8")
    if "\u2014" in text or "\u2013" in text:
        problems.append("ConfigSearch.lua has an em or en dash")
    if re.search(r"\btape\b", text, re.I):
        problems.append("ConfigSearch.lua says tape")
    if len(text.splitlines()) < 60:
        problems.append("ConfigSearch.lua is still the stub")
    harness = Path(__file__).read_text(encoding="utf-8")
    if "\u2014" in harness or "\u2013" in harness:
        problems.append("this harness has an em or en dash")
    toc = [ln.strip() for ln in (ROOT / "forever-stuwave" / "forever-stuwave.toc").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.startswith("##")]
    name = "Modules/Config/ConfigSearch.lua"
    pages = [t for t in toc if t.startswith("Modules/Config/ConfigPage")]
    if name not in toc:
        problems.append("ConfigSearch.lua is not in the toc")
    elif pages and toc.index(name) < max(toc.index(p) for p in pages if p != "Modules/Config/ConfigPageBars.lua"):
        problems.append("ConfigSearch.lua must load after the page files")
    return problems


def run_lua_checks() -> int:
    global CHECK_NAMES
    CHECK_NAMES = set(re.findall(r"^function T\.([a-z0-9_]+)\(", CHECKS, re.M))
    base.CHECKS = base.CHECKS.replace("__checks = T", CHECKS + "\n__checks = T")
    failed = 0
    for name in sorted(CHECK_NAMES):
        try:
            lua = base.boot()
            lua.eval("__checks")[name]()
            leaked = list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:2])[:400]}")
    return failed


def main() -> int:
    failed = run_lua_checks()
    total = len(CHECK_NAMES) + 1
    problems = source_problems()
    if problems:
        failed += 1
        print(f"FAIL  source: {'; '.join(problems)}")
    else:
        print("ok    source")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
