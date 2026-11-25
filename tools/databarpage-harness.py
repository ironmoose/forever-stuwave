#!/usr/bin/env python3
"""Checks for the /fsconfig Data bar page (ticket E1 and E2, page part).

Runs the real ConfigWindow.lua, every page file and the real DataBar.lua (its FS.DataBarSegments API, over the mock APIs of
tools/configwindow-harness.py; the bar frame itself is not built) and pins:

  * the page is one tab, "Segments", with a pinned preview band over one row per segment in the bar's order, each row a
    switch (labelled with the segment's own title), a title box, and two arrows; REP and PROF are there and off by default
  * the band draws only the segments that are on, in order, sharing the width in whole units, each under its title; an
    empty title hides the title and moves the value to the left edge; the count reads "N SHOWN"; it follows a resize
  * its measures are the ones DataBar.lua keeps (read back out of that file), and every segment has a sample value
  * the switch turns a segment on and off through the module (the bar re-lays out), the last one on is disabled with the
    "At least one segment stays on." sentence in its ? tip, and a segment this client cannot show is a dimmed row, switch,
    arrows and title box disabled, its reason first in the tip
  * the arrows swap a segment with its neighbour and the rows stand in the bar's order again; the first row's up and the
    last row's down are disabled; the arrows have hints
  * the arrows are drawn, not typed: 4 by 8 pixel triangles (one unit rect per column) centred on their buttons, pointing
    left and right, with a plain, hover, pressed and disabled look
  * typing in the title box renames the segment on the bar and in the band at once; the box takes ten characters and what
    the module cleans away is not in the box after it lets go; typing the default back stores nothing
  * the title box lets go of the keyboard on Enter, Esc, Tab, a click elsewhere, a click on the window, the window hiding
    and the box hiding; one box has it at a time; it never rewrites its text while it has focus; Enter, Tab and a click
    elsewhere keep what was typed, Esc puts back the title the box had when it was clicked into
  * UI.Order itself (a fixture page, no data bar module) carries the live rename, the lock on the switch, the ON / OFF
    word, the changed marker, the hints and the click away release, so a page needs none of it
  * the changed marker (dot and reset on a row with a stored switch or title, one entry for the order), the page reset, a
    profile switch, and read-only settings
  * every row's text, default and tip is the prototype's (mockups/config-window-2026-11-25.html)
  * the rows and band fit at the smallest, default and largest window

The mock does no anchor layout of its own (tools/configlayout-harness.py's solver does); nothing drawn here is the client.
Everything drawn is pending owner review.
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
# DATABARPAGE_LUA points the harness at a mutant copy of the page (a check must fail on a broken one).
PAGE_FILE = Path(os.environ.get("DATABARPAGE_LUA", ADDON / "Modules/Config/ConfigPageDataBar.lua"))
BAR_FILE = ADDON / "Modules/DataBars/DataBar.lua"
TOC_FILE = ADDON / "forever-stuwave.toc"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load("configwindow_harness", "configwindow-harness.py")
layout = load("configlayout_harness", "configlayout-harness.py")
LuaError = base.LuaError

_config_files = base.config_files


def config_files():
    return [PAGE_FILE if p.name == "ConfigPageDataBar.lua" else p for p in _config_files()]


base.config_files = config_files

MOCKUP = Path(os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups")) / "config-window-2026-11-25.html"

CHECKS = r"""
local Obj = getmetatable(UIParent)
function Obj:SetEnabled(v) self.enabled = v and true or false end
function Obj:SetMaxLetters(n) self.maxLetters = n end
function Obj:HighlightText(from, to) self.highlight = (from == 0 and to == 0) and "none" or "all" end

local DEFAULT_ORDER = { "fps", "mem", "cpu", "latency", "rested", "durability", "bags", "time", "gold", "rep", "prof" }
local DEFAULT_ON = { fps = true, latency = true, rested = true, durability = true, bags = true, time = true, gold = true }

-- ---- fixtures and helpers --------------------------------------------------------------------------------------------

-- Every API the nine segments feature-detect, so every segment is available; `skip` names what to leave out.
local function apis(skip)
    local all = {
        GetFramerate = function() return 118 end,
        UpdateAddOnMemoryUsage = function() end,
        GetAddOnCPUUsage = function() return 0 end,
        GetNetStats = function() return 0, 0, 24, 31 end,
        GetXPExhaustion = function() return 0 end,
        GetInventoryItemDurability = function() return 90, 100 end,
        GetGameTime = function() return 21, 14 end,
        GetMoney = function() return 124007 end,
        GetProfessions = function() return nil end,
        GetProfessionInfo = function() end,
        ToggleCharacter = function() end,
        ToggleCalendar = function() end,
        ToggleProfessionsBook = function() end,
        C_Reputation = { GetWatchedFactionData = function() return nil end },
        C_Container = { GetContainerNumFreeSlots = function() return 5 end, GetContainerNumSlots = function() return 16 end },
        MainMenuBarBackpackButton = {},
    }
    for name, value in pairs(all) do
        if not (skip and skip[name]) then _G[name] = value end
    end
end

-- The window over the real DataBar.lua. The module's own frames never get their login events: only its settings API is used.
local function bootBar(skip, opts)
    apis(skip)
    opts = opts or {}
    opts.preWindow = function()
        local before = #ALL
        assert(load(__dataBarSrc, "@DataBar.lua"))("forever-stuwave", FS)
        for i = before + 1, #ALL do ALL[i].events = {} end
    end
    return boot(opts)
end

local function eqc(a, b, msg)
    for i = 1, 3 do
        if math.abs((a[i] or 0) - (b[i] or 0)) > 0.002 then
            error((msg or "colour") .. ": got " .. table.concat(a, ",") .. ", want " .. table.concat(b, ","), 2)
        end
    end
end

local function rowOf(key)
    for _, e in ipairs(FS.ConfigWindow.Rows()) do
        if e.page == "data" and e.key == "databar.seg." .. key then return e.row, e end
    end
    error("no row for " .. key, 2)
end

-- Segment keys in the order the rows stand in the tab.
local function flowKeys(W)
    local out = {}
    for _, item in ipairs(W.PageBody("data").fsFlow) do
        local e = item.frame.fsEntry
        if e and e.kind == "order" and e.key and e.key:find("^databar%.seg%.") then out[#out + 1] = e.key:sub(13) end
    end
    return out
end

local function joined(list) return table.concat(list, ",") end
local function modelKeys() local out = {}; for _, m in ipairs(FS.DataBarSegments.Model()) do out[#out + 1] = m.key end; return out end
local function modelRow(key) for _, m in ipairs(FS.DataBarSegments.Model()) do if m.key == key then return m end end end
local function tipOf(row) return row.fsHelp and row.fsHelp.fsTip or "" end
local function press(b) if not b.enabled then return false end; b.scripts.OnClick(b, "LeftButton"); return true end
local function hover(b)
    local from = #TOOLTIP.history
    b.scripts.OnEnter(b)
    local lines = {}
    for i = from + 1, #TOOLTIP.history do lines[#lines + 1] = TOOLTIP.history[i] end
    return table.concat(lines, "\n")
end

-- The band: its bar and the segments on it, left to right, with their pieces.
local function band()
    for _, o in ipairs(ALL) do
        if o.fsBand and o:IsShown() then return o end
    end
    error("no band")
end
local function bar()
    local b = band()
    for _, o in ipairs(ALL) do
        if o.parent == b and o.kind == "Frame" and o.h == 20 then return o end
    end
    error("no bar")
end
local function segments()
    local b, out = bar(), {}
    for _, o in ipairs(ALL) do
        if o.parent == b and o.kind == "Frame" and o:IsShown() then
            local seg = { frame = o, x = o.points[1].x, w = o.w, fs = {}, tex = {}, frames = {} }
            for _, p in ipairs(ALL) do
                if p.parent == o then
                    if p.kind == "FontString" then seg.fs[#seg.fs + 1] = p
                    elseif p.kind == "Texture" then seg.tex[#seg.tex + 1] = p
                    elseif p.kind == "Frame" then seg.frames[#seg.frames + 1] = p end
                end
            end
            seg.label, seg.value = seg.fs[1], seg.fs[2]
            seg.track = seg.frames[1]
            out[#out + 1] = seg
        end
    end
    table.sort(out, function(a, b2) return a.x < b2.x end)
    return out
end
local function titles()
    local out = {}
    for _, s in ipairs(segments()) do out[#out + 1] = s.label:IsShown() and s.label:GetText() or "" end
    return out
end
local function countText()
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o.parent == band() then
            local t = o:GetText()
            if t:find(" SHOWN$") then return t end
        end
    end
end

-- Types into a segment's title box the way a player does: focus, text, the change script with userInput.
local function typeTitle(key, text)
    local e = rowOf(key).fsTitleBox
    e:SetFocus()
    e:SetText(text)
    e.scripts.OnTextChanged(e, true)
    return e
end

local function onlyOn(keep)
    for _, k in ipairs(DEFAULT_ORDER) do
        if k ~= keep then FS.DataBarSegments.SetEnabled(k, false) end
    end
end

local function stored(key) return FS.Config.IsStored(key) end

-- ---- the page ------------------------------------------------------------------------------------------------------

function T.the_page_is_one_tab_with_a_band_and_a_row_per_segment_in_the_bars_order()
    local W = bootBar()
    local cat
    for _, c in ipairs(W.Categories()) do if c.key == "data" then cat = c end end
    yes(cat, "the page is registered")
    eq(#cat.tabs, 1)
    eq(cat.tabs[1].label, "Segments")
    eq(cat.group, "PANELS")
    W.Open("data")
    eq(joined(flowKeys(W)), joined(DEFAULT_ORDER))
    local labels = { "FPS", "FS MEM", "FS CPU", "MS", "REST", "DUR", "BAGS", "TIME", "GOLD", "REP", "PROF" }
    for i, key in ipairs(DEFAULT_ORDER) do
        local row, e = rowOf(key)
        eq(row.fsLabel:GetText(), labels[i], key .. " row label")
        eq(e.kind, "order")
        eq(row.control.fsChecked, DEFAULT_ON[key] == true, key .. " default switch")
        yes(row.fsTitleBox and row.fsUp and row.fsDown, key .. " has the title box and both arrows")
    end
    yes(band():IsShown(), "the band is pinned")
end

function T.the_segments_section_carries_the_prototype_tip_and_the_band_its_own()
    local W = bootBar()
    W.Open("data")
    local sec
    for _, e in ipairs(W.Rows()) do if e.page == "data" and e.kind == "order" then sec = e.secObj end end
    yes(sec, "the rows sit in a section")
    eq(sec.title, "Segments")
    eq(sec.tip, __proto.segmentsTip)
    local found
    for _, o in ipairs(ALL) do
        if o.fsTip == __proto.previewTip and under(band(), o) then found = true end
    end
    yes(found, "the PREVIEW tag has the prototype's ? tip")
    local title
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o.parent == band() and o:GetText() == "PREVIEW" then title = o end
    end
    yes(title, "the band has its PREVIEW tag")
end

function T.every_row_is_the_prototypes_label_default_and_tip()
    local W = bootBar()
    W.Open("data")
    eq(#__proto.rows, 11)
    for i, want in ipairs(__proto.rows) do
        local key = DEFAULT_ORDER[i]
        eq(key, want.key, "row " .. i .. " key")
        local row = rowOf(key)
        eq(row.fsLabel:GetText(), want.label, key .. " label")
        eq(row.control.fsChecked, want.on, key .. " default")
        eq(tipOf(row), want.tip, key .. " tip")
    end
end

function T.rep_and_prof_are_in_the_list_and_off_until_turned_on()
    local W = bootBar()
    W.Open("data")
    no(rowOf("rep").control.fsChecked)
    no(rowOf("prof").control.fsChecked)
    no(rowOf("mem").control.fsChecked)
    no(rowOf("cpu").control.fsChecked)
    eq(countText(), "7 SHOWN")
    yes(press(rowOf("rep").control))
    yes(press(rowOf("prof").control))
    yes(rowOf("rep").control.fsChecked)
    eq(FS.Config.Get("databar.seg.rep"), true)
    eq(FS.Config.Get("databar.seg.prof"), true)
    eq(countText(), "9 SHOWN")
    local keys = {}
    for _, m in ipairs(FS.DataBarSegments.Model()) do if m.on then keys[#keys + 1] = m.key end end
    eq(joined(keys), "fps,latency,rested,durability,bags,time,gold,rep,prof")
end

-- ---- the band --------------------------------------------------------------------------------------------------------

function T.the_band_draws_the_segments_that_are_on_in_order_and_they_share_the_width()
    local W = bootBar()
    W.Open("data")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD")
    eq(countText(), "7 SHOWN")
    local segs = segments()
    eq(#segs, 7)
    local x = 0
    for i, s in ipairs(segs) do
        eq(s.x, x, "segment " .. i .. " starts where the last ended")
        yes(s.w >= 101 and s.w <= 102, "segment " .. i .. " is an equal share in whole units, got " .. s.w)
        eq(s.w, math.floor(s.w))
        x = x + s.w
    end
    eq(x, W.D.CONTENT_W, "the shares add up to the band")
    for i, s in ipairs(segs) do
        eq(s.frame.clips, true, "a segment clips what does not fit")
        eq(s.tex[1]:IsShown(), i > 1, "the divider is on every segment but the first")
        eq(s.frame.h, 20)
    end
    local fps = segs[1]
    eq(fps.value:GetText(), "118")
    eq(segs[6].value:GetText(), "9:14 PM")
    eq(segs[3].value:GetText(), "62%")
    yes(segs[3].track:IsShown(), "REST has its meter")
    no(segs[1].track:IsShown(), "FPS has none")
    eq(segs[7].fs[3]:GetText(), "12")
    eq(segs[7].fs[4]:GetText(), "40")
    eq(segs[7].fs[5]:GetText(), "7")
    no(segs[7].value:IsShown(), "GOLD shows coins, not a text value")
end

function T.the_band_follows_a_switch_an_arrow_and_a_title_at_once()
    local W = bootBar()
    W.Open("data")
    FS.DataBarSegments.SetEnabled("mem", true)
    eq(joined(titles()), "FPS,FS MEM,MS,REST,DUR,BAGS,TIME,GOLD")
    eq(countText(), "8 SHOWN")
    FS.DataBarSegments.SetEnabled("fps", false)
    eq(joined(titles()), "FS MEM,MS,REST,DUR,BAGS,TIME,GOLD")
    FS.DataBarSegments.Move("gold", -1)
    eq(joined(titles()), "FS MEM,MS,REST,DUR,BAGS,GOLD,TIME")
    FS.DataBarSegments.SetTitle("time", "CLOCK")
    eq(joined(titles()), "FS MEM,MS,REST,DUR,BAGS,GOLD,CLOCK")
    FS.DataBarSegments.SetTitle("time", "")
    eq(joined(titles()), "FS MEM,MS,REST,DUR,BAGS,GOLD,")
    local segs = segments()
    local last = segs[#segs]
    no(last.label:IsShown(), "an empty title hides the label")
    local p = last.value.points[1]
    eq(p.rel, last.frame, "the value stands on the segment itself")
    eq(p.point, "LEFT"); eq(p.relPoint, "LEFT"); eq(p.x, 8, "at the left padding")
    FS.DataBarSegments.SetTitle("time", "CLOCK")
    local with = segments()[#segs].value.points[1]
    eq(with.rel, segments()[#segs].label, "with a title the value follows it")
    eq(with.x, 6)
end

function T.every_segment_has_a_sample_and_a_clipped_one_never_leaves_its_slot()
    local W = bootBar()
    W.Open("data")
    for _, k in ipairs(DEFAULT_ORDER) do FS.DataBarSegments.SetEnabled(k, true) end
    eq(countText(), "11 SHOWN")
    for i, s in ipairs(segments()) do
        if s.value:IsShown() then yes(s.value:GetText() ~= "--", "segment " .. i .. " has a sample value") end
        for _, tex in ipairs(s.frames) do
            if tex:IsShown() then yes(tex.w >= 16 and tex.w <= 64, "the meter shrinks, but between 16 and 64: " .. tex.w) end
        end
    end
end

function T.the_band_is_drawn_again_when_the_window_is_resized()
    local W = bootBar()
    W.Open("data")
    W.SetSize(1600, 1000, false)
    local b = band()
    b.scripts.OnSizeChanged(b)
    local x = 0
    for _, s in ipairs(segments()) do x = x + s.w end
    eq(x, W.D.CONTENT_W)
    yes(x > 1000, "the shares follow the wider window")
end

-- ---- switches --------------------------------------------------------------------------------------------------------

function T.the_switch_turns_a_segment_on_and_off_through_the_module()
    local W = bootBar()
    W.Open("data")
    local row = rowOf("mem")
    yes(press(row.control))
    eq(FS.Config.Get("databar.seg.mem"), true)
    eq(modelRow("mem").on, true)
    eq(row.fsLabel:GetText(), "FS MEM")
    yes(press(row.control))
    eq(FS.Config.Get("databar.seg.mem"), false)
    no(stored("databar.seg.mem"), "back at the default stores nothing")
    local fps = rowOf("fps")
    yes(press(fps.control))
    eq(FS.Config.Get("databar.seg.fps"), false)
    yes(modelRow("fps").on == false)
    eq(fps.control.fsChecked, false)
end

function T.the_state_word_says_on_or_off()
    local W = bootBar()
    W.Open("data")
    local function word(row)
        for _, o in ipairs(ALL) do
            if o.kind == "FontString" and o.parent == row and (o:GetText() == "ON" or o:GetText() == "OFF") then return o:GetText() end
        end
    end
    eq(word(rowOf("fps")), "ON")
    eq(word(rowOf("mem")), "OFF")
    press(rowOf("mem").control)
    eq(word(rowOf("mem")), "ON")
end

function T.the_last_switch_on_is_disabled_and_its_tip_says_why()
    local W = bootBar()
    W.Open("data")
    onlyOn("fps")
    W.RefreshAll()
    local fps = rowOf("fps")
    yes(fps.control.fsChecked)
    no(fps.control.enabled, "the last switch is disabled")
    eq(fps.control.alpha, 0.4)
    yes(tipOf(fps):find("At least one segment stays on.", 1, true), "the ? tip names the lock: " .. tipOf(fps))
    yes(tipOf(fps):find("Frames per second.", 1, true), "and keeps the row's own tip")
    no(press(fps.control), "a press does nothing")
    eq(FS.Config.Get("databar.seg.fps"), true)
    yes(rowOf("mem").control.enabled, "any other switch still works")
    yes(press(rowOf("mem").control))
    yes(fps.control.enabled, "the lock lifts when a second one is on")
    no(tipOf(fps):find("At least one", 1, true), "and so does its sentence")
    yes(rowOf("fps").fsUp.enabled == false and rowOf("fps").fsDown.enabled == true, "the arrows stay live on the locked row")
    no(rowOf("fps").fsRowOff, "a locked row is not a dimmed row")
end

function T.a_segment_this_client_cannot_show_is_a_dimmed_row_with_its_reason()
    local W = bootBar({ GetFramerate = true })
    W.Open("data")
    local row = rowOf("fps")
    yes(row.fsRowOff, "the row is off")
    eq(row.fsLabel.alpha, 0.4)
    no(row.control.enabled, "the switch is disabled")
    no(row.fsUp.enabled); no(row.fsDown.enabled)
    no(row.fsTitleBox.enabled, "the title box is disabled")
    eq(row.fsTitleBox:GetParent().alpha, 0.4)
    eq(tipOf(row), "FPS\nThis client does not report frames per second.\nFrames per second.")
    eq(row.control.fsChecked, false)
    eq(joined(titles()):find("FPS"), nil, "it is not on the band")
    eq(countText(), "6 SHOWN")
    yes(rowOf("latency").control.enabled, "the others are not touched")
    yes(rowOf("latency").fsTitleBox.enabled)
    no(press(row.control))
    local ok, why = FS.DataBarSegments.SetEnabled("fps", true)
    no(ok)
    eq(why, "This client does not report frames per second.")
end

function T.a_segment_the_client_drops_later_becomes_a_dimmed_row_on_the_next_refresh()
    local W = bootBar()
    W.Open("data")
    yes(rowOf("fps").control.enabled)
    -- a read that throws is what the module marks failed; the page only reads the model
    local real = FS.DataBarSegments.Model
    FS.DataBarSegments.Model = function()
        local list = real()
        for _, m in ipairs(list) do
            if m.key == "latency" then m.available, m.on, m.reason = false, false, "This client does not report latency." end
        end
        return list
    end
    W.RefreshAll()
    yes(rowOf("latency").fsRowOff)
    eq(tipOf(rowOf("latency")):find("This client does not report latency.", 1, true) ~= nil, true)
    eq(countText(), "6 SHOWN")
    FS.DataBarSegments.Model = real
    W.RefreshAll()
    no(rowOf("latency").fsRowOff)
end

-- ---- arrows ----------------------------------------------------------------------------------------------------------

function T.the_arrows_swap_a_segment_with_its_neighbour_and_the_rows_follow()
    local W = bootBar()
    W.Open("data")
    no(rowOf("fps").fsUp.enabled, "the first row cannot go up")
    yes(rowOf("fps").fsDown.enabled)
    no(rowOf("prof").fsDown.enabled, "the last row cannot go down")
    yes(rowOf("prof").fsUp.enabled)
    yes(press(rowOf("fps").fsDown))
    eq(joined(modelKeys()), "mem,fps,cpu,latency,rested,durability,bags,time,gold,rep,prof")
    eq(joined(flowKeys(W)), joined(modelKeys()), "the rows stand in the new order")
    yes(rowOf("mem").fsUp.enabled == false, "MEM is first now")
    yes(rowOf("fps").fsUp.enabled == true, "FPS can come back up")
    local y = {}
    for _, item in ipairs(W.PageBody("data").fsFlow) do
        local e = item.frame.fsEntry
        if e and e.kind == "order" and e.key:find("^databar%.seg%.") then y[e.key:sub(13)] = item.y end
    end
    yes(y.mem < y.fps and y.fps < y.cpu, "the rows are laid out again, top to bottom: " .. tostring(y.mem) .. " " .. tostring(y.fps))
    yes(press(rowOf("gold").fsUp))
    yes(press(rowOf("gold").fsUp))
    eq(joined(flowKeys(W)), "mem,fps,cpu,latency,rested,durability,gold,bags,time,rep,prof")
    eq(joined(titles()), "FPS,MS,REST,DUR,GOLD,BAGS,TIME")
    -- a row of a segment that is off moves too, and the band is untouched
    yes(press(rowOf("mem").fsDown))
    eq(joined(flowKeys(W)), "fps,mem,cpu,latency,rested,durability,gold,bags,time,rep,prof")
    eq(joined(titles()), "FPS,MS,REST,DUR,GOLD,BAGS,TIME")
end

function T.the_row_keeps_its_own_frame_key_and_entry_when_it_moves()
    local W = bootBar()
    W.Open("data")
    local row, entry = rowOf("fps")
    press(row.fsDown)
    local again, entry2 = rowOf("fps")
    eq(again, row)
    eq(entry2, entry)
    eq(entry.key, "databar.seg.fps")
    eq(entry.section, "Segments")
    eq(entry.tab, "g")
end

function T.a_disabled_arrow_moves_nothing_even_when_the_click_script_runs()
    local W = bootBar()
    W.Open("data")
    local first, last = rowOf("fps").fsUp, rowOf("prof").fsDown
    no(first.enabled); no(last.enabled)
    first.scripts.OnClick(first, "LeftButton")
    last.scripts.OnClick(last, "LeftButton")
    eq(joined(modelKeys()), joined(DEFAULT_ORDER), "nothing moved")
end

function T.the_arrows_have_hints_and_a_disabled_one_says_nothing()
    local W = bootBar()
    W.Open("data")
    eq(hover(rowOf("time").fsUp), "Move left")
    eq(hover(rowOf("time").fsDown), "Move right")
    eq(hover(rowOf("fps").fsUp), "", "the first row's up is disabled")
end

-- The pixel triangles on the order arrows: the client fonts have no triangle glyphs, so "^" and "v" read as letters.
local function glyphBox(button)
    local g = button.fsGlyph
    yes(g and g.textures and #g.textures > 0, "the arrow has a glyph made of rects")
    local l, r, t, b = math.huge, -math.huge, -math.huge, math.huge
    local cols = {}
    for _, tex in ipairs(g.textures) do
        local p = tex.points[1]
        eq(p.point, "TOPLEFT"); eq(p.rel, button, "anchored to its button"); eq(p.relPoint, "CENTER")
        eq(p.x, math.floor(p.x), "whole unit x"); eq(p.y, math.floor(p.y), "whole unit y")
        eq(tex.w, 1, "one unit wide"); eq(tex.h, math.floor(tex.h), "whole unit tall")
        l, r = math.min(l, p.x), math.max(r, p.x + tex.w)
        t, b = math.max(t, p.y), math.min(b, p.y - tex.h)
        cols[#cols + 1] = { x = p.x, h = tex.h }
    end
    table.sort(cols, function(a, c) return a.x < c.x end)
    return l, r, t, b, cols
end

function T.the_arrows_are_pixel_glyphs_centred_on_their_buttons_not_typed_characters()
    local W = bootBar()
    W.Open("data")
    for _, k in ipairs(DEFAULT_ORDER) do
        local row = rowOf(k)
        for _, side in ipairs({ "fsUp", "fsDown" }) do
            local b = row[side]
            eq(b.fsLabel:GetText(), "", k .. " " .. side .. " has no text on it")
            eq(b.w, 24); eq(b.h, 24)
            local l, r, t, bt = glyphBox(b)
            eq(r - l, 4, k .. " " .. side .. " is 4 wide")
            eq(t - bt, 8, k .. " " .. side .. " is 8 tall")
            eq(l + r, 0, k .. " " .. side .. " is centred across")
            eq(t + bt, 0, k .. " " .. side .. " is centred up and down")
        end
    end
end

function T.the_up_arrow_points_left_and_the_down_arrow_points_right()
    local W = bootBar()
    W.Open("data")
    local row = rowOf("time")
    local _, _, _, _, left = glyphBox(row.fsUp)
    local _, _, _, _, right = glyphBox(row.fsDown)
    eq(#left, 4); eq(#right, 4)
    for i = 1, 4 do
        eq(left[i].h, 2 * i, "left: the columns grow toward the base on the right")
        eq(right[i].h, 10 - 2 * i, "right: the columns shrink toward the point on the right")
    end
end

function T.an_arrow_has_a_plain_hover_pressed_and_disabled_look()
    local W = bootBar()
    W.Open("data")
    local b = rowOf("time").fsUp
    local function glyph() local c = b.fsGlyph.textures[1].color; return c end
    local function ring() return b.fsSkin.border.ring.color end
    local function fill() return b.fsFill.color end
    local function same(a, c) for i = 1, 3 do if math.abs(a[i] - c[i]) > 0.002 then return false end end return true end
    -- every rect of the glyph wears the same colour
    for _, tex in ipairs(b.fsGlyph.textures) do eqc(tex.color, glyph(), "one colour across the glyph") end
    eqc(glyph(), W.C.cyan, "plain: a cyan glyph")
    eqc(ring(), W.C.line, "plain: the line coloured ring")
    eqc(fill(), W.C.ink, "plain: the ink fill")
    local plainFill = { fill()[1], fill()[2], fill()[3] }
    b.scripts.OnEnter(b)
    eqc(ring(), W.C.cyan, "hover: a cyan ring")
    eqc(glyph(), W.C.cyan)
    no(same(fill(), plainFill), "hover: the fill lifts")
    local hoverFill = { fill()[1], fill()[2], fill()[3] }
    b.scripts.OnMouseDown(b)
    eqc(ring(), W.C.cyan, "pressed: the ring stays cyan")
    no(same(fill(), hoverFill), "pressed: a darker fill than hover")
    yes(fill()[1] < hoverFill[1] or fill()[3] < hoverFill[3] or fill()[2] < hoverFill[2], "pressed is darker")
    b.scripts.OnMouseUp(b)
    eqc(fill(), hoverFill, "released: the hover fill again")
    b.scripts.OnLeave(b)
    eqc(ring(), W.C.line, "left: plain again")
    eqc(fill(), W.C.ink)
    -- disabled (the first row cannot move up): dim violet glyph, no lift
    local first = rowOf("fps").fsUp
    no(first.enabled)
    local dim = first.fsGlyph.textures[1].color
    no(same(dim, W.C.cyan), "disabled: not cyan")
    yes(dim[1] > 0.3 and dim[1] < 0.45 and dim[3] > 0.45 and dim[3] < 0.55, "disabled: the window's dim violet")
    no(same(first.fsSkin.border.ring.color, W.C.cyan), "disabled: not a cyan ring")
    no(same(first.fsFill.color, W.C.ink), "disabled: its own darker fill")
    first.scripts.OnEnter(first)
    no(same(first.fsSkin.border.ring.color, W.C.cyan), "hovering a disabled arrow does not light it")
    no(same(first.fsGlyph.textures[1].color, W.C.cyan))
    first.scripts.OnMouseDown(first)
    no(same(first.fsGlyph.textures[1].color, W.C.cyan), "nor does pressing it")
    first.scripts.OnLeave(first)
    -- a move turns it live and the look follows at once
    press(rowOf("fps").fsDown)
    yes(rowOf("fps").fsUp.enabled)
    eqc(rowOf("fps").fsUp.fsGlyph.textures[1].color, W.C.cyan, "enabled after a move: cyan")
    -- read only: all dim
    local W2 = bootBar(nil, { db = "junk" })
    W2.Open("data")
    for _, k in ipairs(DEFAULT_ORDER) do
        no(same(rowOf(k).fsDown.fsGlyph.textures[1].color, W2.C.cyan), k .. " read only: a dim glyph")
    end
end

-- ---- the title box ---------------------------------------------------------------------------------------------------

function T.the_title_box_shows_the_title_on_the_bar_and_takes_ten_characters()
    local W = bootBar()
    W.Open("data")
    eq(rowOf("time").fsTitleBox:GetText(), "TIME")
    eq(rowOf("fps").fsTitleBox:GetText(), "FPS")
    eq(rowOf("mem").fsTitleBox:GetText(), "FS MEM")
    for _, k in ipairs(DEFAULT_ORDER) do eq(rowOf(k).fsTitleBox.maxLetters, 10, k .. " box limit") end
    eq(FS.DataBarSegments.TITLE_MAX, 10)
end

function T.typing_renames_the_title_on_the_bar_and_in_the_band_as_it_goes()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "C")
    eq(FS.Config.Get("databar.title.time"), "C")
    eq(modelRow("time").title, "C")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,C,GOLD")
    e:SetText("CLOCK")
    e.scripts.OnTextChanged(e, true)
    eq(FS.Config.Get("databar.title.time"), "CLOCK")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,CLOCK,GOLD")
    eq(e:GetText(), "CLOCK", "the box keeps what is typed")
    yes(e:HasFocus(), "and the keyboard")
    eq(FS.Config.Get("databar.title.fps"), "FPS", "the other titles are untouched")
end

function T.the_refresh_that_puts_the_title_back_is_not_a_keystroke()
    local W = bootBar()
    W.Open("data")
    local e = rowOf("time").fsTitleBox
    FS.DataBarSegments.SetTitle("time", "NOON")
    W.RefreshAll()
    eq(e:GetText(), "NOON", "an outside change shows in the box")
    -- the client fires OnTextChanged for SetText too, with userInput false
    e.scripts.OnTextChanged(e, false)
    eq(FS.Config.Get("databar.title.time"), "NOON")
    eq(joined(titles()):find("NOON") ~= nil, true)
end

function T.clearing_the_box_shows_only_the_value()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "")
    eq(FS.Config.Get("databar.title.time"), "")
    eq(modelRow("time").title, "")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,,GOLD")
    e:ClearFocus()
    eq(e:GetText(), "", "the box stays empty")
    yes(stored("databar.title.time"), "an empty title is stored: it is not the default")
    local seg = segments()[6]
    eq(seg.value:GetText(), "9:14 PM")
end

function T.typing_the_default_back_stores_nothing()
    local W = bootBar()
    W.Open("data")
    typeTitle("time", "CLOCK")
    yes(stored("databar.title.time"))
    typeTitle("time", "TIME")
    no(stored("databar.title.time"), "the default title is stored as nothing")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD")
end

function T.what_the_module_cleans_away_is_gone_from_the_box_after_it_lets_go()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "ab|cd")
    eq(e:GetText(), "ab|cd", "while it has focus the box is left alone")
    eq(FS.Config.Get("databar.title.time"), "abcd")
    e:ClearFocus()
    eq(e:GetText(), "abcd")
    local e2 = typeTitle("fps", "ABCDEFGHIJKLMN")
    eq(FS.Config.Get("databar.title.fps"), "ABCDEFGHIJ", "ten characters, even when more got in")
    e2:ClearFocus()
    eq(e2:GetText(), "ABCDEFGHIJ")
    local e3 = typeTitle("gold", "   ")
    eq(FS.Config.Get("databar.title.gold"), "", "spaces alone are no title")
    e3:ClearFocus()
    eq(e3:GetText(), "")
end

function T.the_title_box_has_a_cyan_edge_and_selects_its_text_while_it_has_focus()
    local W = bootBar()
    W.Open("data")
    local e = rowOf("time").fsTitleBox
    local holder = e:GetParent()
    local edges = {}
    for _, o in ipairs(ALL) do
        if o.kind == "Texture" and o.parent == holder and o.layer == "BORDER" then edges[#edges + 1] = o end
    end
    eq(#edges, 4, "four edges")
    for _, t in ipairs(edges) do eqc(t.color, W.C.line, "grey edge while it has no focus") end
    e:SetFocus()
    for _, t in ipairs(edges) do eqc(t.color, W.C.cyan, "cyan edge while it has focus") end
    eq(e.highlight, "all", "the text is selected on focus")
    e:ClearFocus()
    for _, t in ipairs(edges) do eqc(t.color, W.C.line, "grey again") end
    eq(e.highlight, "none", "and not selected after")
end

function T.enter_and_tab_let_go_and_keep_what_was_typed()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "CLOCK")
    e.scripts.OnEnterPressed(e)
    no(e:HasFocus(), "Enter")
    eq(FS.Config.Get("databar.title.time"), "CLOCK")
    eq(e:GetText(), "CLOCK")
    e = typeTitle("gold", "COINS")
    e.scripts.OnTabPressed(e)
    no(e:HasFocus(), "Tab")
    eq(FS.Config.Get("databar.title.gold"), "COINS")
    eq(W.I.sliderFocus, nil, "nothing holds the keyboard")
end

function T.esc_puts_back_the_title_the_box_had_when_it_was_clicked_into()
    local W = bootBar()
    W.Open("data")
    -- from the default
    local e = typeTitle("fps", "FRAMES")
    eq(FS.Config.Get("databar.title.fps"), "FRAMES", "live while typing")
    eq(joined(titles()), "FRAMES,MS,REST,DUR,BAGS,TIME,GOLD")
    e.scripts.OnEscapePressed(e)
    no(e:HasFocus(), "Esc lets go")
    eq(e:GetText(), "FPS", "the box shows the old title")
    eq(FS.Config.Get("databar.title.fps"), "FPS", "and so does the bar")
    no(stored("databar.title.fps"), "the default is stored as nothing again")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD")
    eq(W.I.sliderFocus, nil, "nothing holds the keyboard")
    -- from a title already stored: a first edit stands, the second is the one Esc undoes
    e = typeTitle("time", "CLOCK")
    e.scripts.OnEnterPressed(e)
    e = typeTitle("time", "NOON")
    e:SetText("NOON2")
    e.scripts.OnTextChanged(e, true)
    eq(FS.Config.Get("databar.title.time"), "NOON2")
    e.scripts.OnEscapePressed(e)
    eq(e:GetText(), "CLOCK")
    eq(FS.Config.Get("databar.title.time"), "CLOCK", "back to the title stored before this edit")
    yes(stored("databar.title.time"))
    -- from an emptied title
    e = typeTitle("gold", "")
    e.scripts.OnEnterPressed(e)
    eq(FS.Config.Get("databar.title.gold"), "")
    e = typeTitle("gold", "PURSE")
    e.scripts.OnEscapePressed(e)
    eq(e:GetText(), "", "an empty title comes back empty")
    eq(FS.Config.Get("databar.title.gold"), "")
    -- no typing at all: Esc changes nothing
    e = rowOf("latency").fsTitleBox
    e:SetFocus()
    e.scripts.OnEscapePressed(e)
    eq(FS.Config.Get("databar.title.latency"), "MS")
    no(stored("databar.title.latency"))
end

function T.after_esc_a_later_click_away_keeps_the_restored_title_not_the_typed_one()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "CLOCK")
    e.scripts.OnEscapePressed(e)
    eq(FS.Config.Get("databar.title.time"), "TIME")
    -- the next time the box is clicked into it remembers the title it has now, not the one Esc threw away
    e:SetFocus()
    e:SetText("LATER")
    e.scripts.OnTextChanged(e, true)
    local catcher = W.I.focusCatcher
    catcher.scripts.OnClick(catcher)
    eq(FS.Config.Get("databar.title.time"), "LATER", "a click away keeps what was typed")
    e:SetFocus()
    e:SetText("LATEST")
    e.scripts.OnTextChanged(e, true)
    e.scripts.OnEscapePressed(e)
    eq(FS.Config.Get("databar.title.time"), "LATER", "Esc goes back one edit, not to the default")
end

function T.a_click_elsewhere_the_window_and_the_window_hiding_let_go()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "CLOCK")
    yes(e:HasFocus())
    local catcher = assert(W.I.focusCatcher, "no click catcher")
    yes(catcher:IsShown(), "a click catcher stands behind the window")
    catcher.scripts.OnClick(catcher)
    no(e:HasFocus(), "a click elsewhere")
    no(catcher:IsShown())
    eq(FS.Config.Get("databar.title.time"), "CLOCK")
    local e2 = typeTitle("fps", "FRAMES")
    local w = _G.ForeverSTUwaveConfig
    w.scripts.OnMouseDown(w, "LeftButton")
    no(e2:HasFocus(), "a click on the window")
    local e3 = typeTitle("gold", "COINS")
    W.Close()
    no(e3:HasFocus(), "the window hiding")
    eq(FS.Config.Get("databar.title.gold"), "COINS")
    W.Open("data")
    local e4 = typeTitle("latency", "PING")
    e4:Hide()
    no(e4:HasFocus(), "the box hiding (another page)")
end

function T.one_title_box_has_the_keyboard_at_a_time()
    local W = bootBar()
    W.Open("data")
    local a = typeTitle("time", "ONE")
    local b = typeTitle("fps", "TWO")
    no(a:HasFocus())
    yes(b:HasFocus())
    eq(W.I.sliderFocus, b)
end

function T.a_box_that_goes_disabled_gives_up_the_keyboard()
    local W = bootBar()
    W.Open("data")
    local e = typeTitle("time", "CLOCK")
    local real = FS.DataBarSegments.Model
    FS.DataBarSegments.Model = function()
        local list = real()
        for _, m in ipairs(list) do
            if m.key == "time" then m.available, m.on, m.reason = false, false, "x" end
        end
        return list
    end
    W.RefreshAll()
    no(e:HasFocus(), "a disabled box does not keep the keyboard")
    no(e.enabled)
end

-- ---- changed markers, reset, profiles ----------------------------------------------------------------------------------

function T.a_row_with_a_stored_switch_or_title_shows_its_dot_and_reset()
    local W = bootBar()
    W.Open("data")
    local row = rowOf("time")
    yes(row.fsDot and row.fsReset, "the dot and the reset are built")
    no(row.fsDot:IsShown())
    no(row.fsReset:IsShown())
    local e = typeTitle("time", "CLOCK")
    e:ClearFocus()
    yes(row.fsDot:IsShown(), "a stored title marks the row")
    yes(row.fsReset:IsShown())
    yes(tipOf(row):find("Changed from the default.", 1, true))
    no(rowOf("fps").fsDot:IsShown(), "the others are not marked")
    press(row.fsReset)
    eq(FS.Config.Get("databar.title.time"), "TIME")
    eq(row.fsTitleBox:GetText(), "TIME")
    no(row.fsDot:IsShown())
    press(rowOf("mem").control)
    yes(rowOf("mem").fsDot:IsShown(), "a stored switch marks the row")
    press(rowOf("mem").fsReset)
    eq(FS.Config.Get("databar.seg.mem"), false)
    no(rowOf("mem").fsDot:IsShown())
end

function T.the_order_is_one_changed_entry_on_the_section_and_a_move_marks_no_row()
    local W = bootBar()
    W.Open("data")
    local entry = assert(W.RowByKey("databar.order", "data"), "no entry for the order")
    eq(entry.label, "Segment order")
    eq(entry.section, "Segments")
    no(W.I.EntryChanged(entry))
    press(rowOf("gold").fsUp)
    yes(W.I.EntryChanged(entry), "a move is a change")
    yes(stored("databar.order"))
    for _, k in ipairs(DEFAULT_ORDER) do no(rowOf(k).fsDot:IsShown(), k .. " row is not marked for a neighbour's move") end
    eq(entry.secObj.changed, 1, "the section counts it")
    local keys = W.ChangedKeys("data")
    eq(#keys, 1)
    eq(keys[1], "databar.order")
    W.ResetKeys(keys)
    eq(joined(modelKeys()), joined(DEFAULT_ORDER))
    no(stored("databar.order"))
    eq(joined(flowKeys(W)), joined(DEFAULT_ORDER), "the rows go back too")
    no(W.I.EntryChanged(entry))
end

function T.reset_page_puts_switches_titles_and_order_back()
    local W = bootBar()
    W.Open("data")
    press(rowOf("mem").control)
    press(rowOf("fps").control)
    local e = typeTitle("time", "CLOCK")
    e:ClearFocus()
    press(rowOf("time").fsUp)
    local keys = W.ChangedKeys("data")
    table.sort(keys)
    eq(joined(keys), "databar.order,databar.seg.fps,databar.seg.mem,databar.seg.time")
    W.ResetKeys(keys)
    eq(joined(modelKeys()), joined(DEFAULT_ORDER))
    eq(FS.Config.Get("databar.seg.fps"), true)
    eq(FS.Config.Get("databar.seg.mem"), false)
    eq(FS.Config.Get("databar.title.time"), "TIME")
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD")
    eq(#W.ChangedKeys("data"), 0)
end

function T.a_profile_switch_repaints_the_rows_the_boxes_and_the_band()
    local W = bootBar()
    W.Open("data")
    yes(FS.Config.NewProfile("Raid"))
    yes(FS.Config.SetActiveProfile("Raid"))
    W.RefreshAll()
    FS.DataBarSegments.SetEnabled("mem", true)
    FS.DataBarSegments.SetTitle("fps", "FRAMES")
    FS.DataBarSegments.Move("gold", -1)
    eq(joined(titles()), "FRAMES,FS MEM,MS,REST,DUR,BAGS,GOLD,TIME")
    eq(rowOf("fps").fsTitleBox:GetText(), "FRAMES")
    yes(rowOf("mem").control.fsChecked)
    eq(joined(flowKeys(W)), joined(modelKeys()))
    yes(FS.Config.SetActiveProfile("Default"))
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD")
    eq(rowOf("fps").fsTitleBox:GetText(), "FPS")
    no(rowOf("mem").control.fsChecked)
    eq(joined(flowKeys(W)), joined(DEFAULT_ORDER), "the rows are back in the default order")
    eq(countText(), "7 SHOWN")
end

function T.read_only_settings_disable_every_control()
    local W = bootBar(nil, { db = "junk" })
    yes(FS.Config.IsReadOnly())
    W.Open("data")
    for _, k in ipairs(DEFAULT_ORDER) do
        local row = rowOf(k)
        no(row.control.enabled, k .. " switch")
        no(row.fsUp.enabled, k .. " up")
        no(row.fsDown.enabled, k .. " down")
        no(row.fsTitleBox.enabled, k .. " title box")
    end
    eq(joined(titles()), "FPS,MS,REST,DUR,BAGS,TIME,GOLD", "the band still draws the defaults")
end

-- ---- UI.Order on its own ---------------------------------------------------------------------------------------------

-- One row of the builder with no data bar module: the store is a plain table, so everything under test is the builder's.
local function orderFixture(opts)
    opts = opts or {}
    local W = boot()
    local store = { on = opts.on ~= false, title = opts.title or "ALPHA", typed = {}, moved = {}, sets = {}, locked = opts.locked or false,
        changed = false }
    local row
    W.RegisterCategory({ key = "ox", label = "Ox", group = "GENERAL", order = 70, build = function(c)
        row = W.UI.Order(c, {
            label = "Alpha", tip = "The first one.", regKey = "ox.alpha", maxLetters = 6,
            get = function() return store.on end,
            set = function(v) store.on = v; return true end,
            getTitle = function() return store.title end,
            setTitle = function(t) store.sets[#store.sets + 1] = t; store.title = t end,
            onType = (not opts.noType) and function(t) store.typed[#store.typed + 1] = t; store.title = t end or nil,
            canUp = function() return store.canUp ~= false end,
            canDown = function() return store.canDown ~= false end,
            onUp = function() store.moved[#store.moved + 1] = "up" end,
            onDown = function() store.moved[#store.moved + 1] = "down" end,
            upHint = opts.upHint, downHint = opts.downHint,
            lock = opts.lock and function() return store.locked end or nil,
            isChanged = function() return store.changed end,
            reset = function() store.changed = false; store.title = "ALPHA" end,
        })
    end })
    W.Open("ox")
    return W, store, row
end

function T.the_builder_arrows_are_glyphs_that_say_move_left_and_move_right_by_default()
    local W, store, row = orderFixture()
    eq(row.fsUp.fsLabel:GetText(), "")
    eq(row.fsDown.fsLabel:GetText(), "")
    eq(#row.fsUp.fsGlyph.textures, 4)
    eq(hover(row.fsUp), "Move left")
    eq(hover(row.fsDown), "Move right")
    yes(press(row.fsUp)); yes(press(row.fsDown))
    eq(table.concat(store.moved, ","), "up,down")
end

function T.the_builder_hints_can_be_worded_by_the_page()
    local W, store, row = orderFixture({ upHint = "Earlier", downHint = "Later" })
    eq(hover(row.fsUp), "Earlier")
    eq(hover(row.fsDown), "Later")
end

function T.the_builder_renames_live_while_typing_and_not_on_a_programmatic_set()
    local W, store, row = orderFixture()
    local e = row.fsTitleBox
    eq(e.maxLetters, 6)
    e:SetFocus()
    e:SetText("BETA")
    e.scripts.OnTextChanged(e, true)
    eq(table.concat(store.typed, ","), "BETA")
    e:SetText("SET")
    e.scripts.OnTextChanged(e, false)
    eq(table.concat(store.typed, ","), "BETA", "SetText is not a keystroke")
    e:ClearFocus()
    eq(store.sets[#store.sets], "SET", "letting go commits what the box holds")
end

function T.the_builder_without_a_live_hook_only_commits_when_it_lets_go()
    local W, store, row = orderFixture({ noType = true })
    local e = row.fsTitleBox
    e:SetFocus()
    e:SetText("BETA")
    e.scripts.OnTextChanged(e, true)
    eq(#store.typed, 0); eq(#store.sets, 0)
    e.scripts.OnEnterPressed(e)
    eq(store.sets[#store.sets], "BETA")
    no(e:HasFocus())
end

function T.the_builder_esc_restores_the_title_from_focus_and_a_click_away_commits()
    local W, store, row = orderFixture()
    local e = row.fsTitleBox
    e:SetFocus()
    e:SetText("BETA")
    e.scripts.OnTextChanged(e, true)
    e.scripts.OnEscapePressed(e)
    no(e:HasFocus())
    eq(e:GetText(), "ALPHA")
    eq(store.title, "ALPHA")
    e:SetFocus()
    e:SetText("GAMMA")
    e.scripts.OnTextChanged(e, true)
    local catcher = assert(W.I.focusCatcher, "a click catcher exists")
    yes(catcher:IsShown())
    catcher.scripts.OnClick(catcher)
    no(e:HasFocus(), "a click elsewhere lets go")
    eq(store.title, "GAMMA")
    local w = _G.ForeverSTUwaveConfig
    e:SetFocus()
    w.scripts.OnMouseDown(w, "LeftButton")
    no(e:HasFocus(), "a click on the window")
    e:SetFocus()
    e:Hide()
    no(e:HasFocus(), "hiding the box")
end

function T.the_builder_lock_disables_only_the_switch()
    local W, store, row = orderFixture({ lock = true, locked = true })
    no(row.control.enabled, "the switch is locked")
    eq(row.control.alpha, 0.4)
    yes(row.fsUp.enabled and row.fsDown.enabled, "the arrows stay live")
    yes(row.fsTitleBox.enabled, "so does the title box")
    no(row.fsRowOff, "it is not a dimmed row")
    no(press(row.control), "a press does nothing")
    eq(store.on, true)
    store.locked = false
    W.RefreshAll()
    yes(row.control.enabled)
    eq(row.control.alpha, 1)
    yes(press(row.control))
    eq(store.on, false)
end

function T.the_builder_shows_on_or_off_beside_the_switch_in_colour()
    local W, store, row = orderFixture({ on = false })
    local function word()
        for _, o in ipairs(ALL) do
            if o.kind == "FontString" and o.parent == row and (o:GetText() == "ON" or o:GetText() == "OFF") then return o end
        end
    end
    eq(word():GetText(), "OFF")
    eqc(word().themeColor, W.C.line)
    press(row.control)
    eq(word():GetText(), "ON")
    eqc(word().themeColor, W.C.cyan)
end

function T.the_builder_marks_a_changed_row_and_resets_it()
    local W, store, row = orderFixture()
    no(row.fsReset:IsShown())
    store.changed = true
    W.RefreshAll()
    yes(row.fsDot:IsShown()); yes(row.fsReset:IsShown())
    row.fsReset.scripts.OnClick(row.fsReset)
    no(row.fsReset:IsShown())
    eq(store.title, "ALPHA")
end

function T.the_builder_gives_up_the_keyboard_when_the_row_goes_off()
    local W, store, row = orderFixture()
    local e = row.fsTitleBox
    e:SetFocus()
    row.fsRowOff = true
    W.RefreshAll()
    no(e:HasFocus(), "an off row does not keep the keyboard")
    no(e.enabled)
    eq(e:GetParent().alpha, 0.4)
    row.fsRowOff = nil
    W.RefreshAll()
    yes(e.enabled)
    eq(e:GetParent().alpha, 1)
end

-- ---- without the module, and a module that fails -------------------------------------------------------------------------

function T.without_the_module_the_tab_says_so_and_builds_nothing_else()
    local W = boot()
    W.Open("data")
    yes(W.PageBody("data"), "the tab is built")
    local found
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and o:GetText() == "The data bar is not loaded." then found = true end
    end
    yes(found, "a note says why the tab is empty")
    for _, e in ipairs(W.Rows()) do
        if e.page == "data" then eq(e.kind, "note") end
    end
    for _, o in ipairs(ALL) do no(o.fsBand and o:IsShown(), "no band") end
end

function T.a_model_that_throws_is_forwarded_and_the_page_survives()
    local W = bootBar()
    local real = FS.DataBarSegments.Model
    W.Open("data")
    FS.DataBarSegments.Model = function() error("model broke") end
    W.RefreshAll()
    eq(joined(flowKeys(W)), joined(DEFAULT_ORDER), "the rows stay")
    local n = 0
    for k in pairs(__errors) do n = n + 1 end
    yes(n >= 1, "the failure reached the error handler")
    for k in pairs(__errors) do __errors[k] = nil end
    FS.DataBarSegments.Model = real
    W.RefreshAll()
end

-- ---- layout ----------------------------------------------------------------------------------------------------------

local function overlap(a, b) return math.min(a.r, b.r) - math.max(a.l, b.l) > 0.51 and math.min(a.t, b.t) - math.max(a.b, b.b) > 0.51 end

local function fits(W, w, h)
    W.SetSize(w, h, false)
    W.Open("data")
    local bnd = band()
    bnd.scripts.OnSizeChanged(bnd)
    local rect = solveAll()
    local br = rect(bar())
    yes(math.abs((br.r - br.l) - W.D.CONTENT_W) < 0.51, w .. ": the bar is as wide as the content, got " .. (br.r - br.l))
    eq(br.t - br.b, 20)
    local right = br.l
    for i, s in ipairs(segments()) do
        local r = rect(s.frame)
        yes(math.abs(r.l - right) < 0.51, w .. ": segment " .. i .. " starts where the last ended")
        right = r.r
    end
    yes(math.abs(right - br.r) < 0.51, w .. ": the segments end at the bar's edge")
    for _, k in ipairs(DEFAULT_ORDER) do
        local row = rowOf(k)
        local rr = rect(row)
        local parts = { holder = row.fsTitleBox:GetParent(), up = row.fsUp, down = row.fsDown, toggle = row.control }
        local rects = {}
        for name, f in pairs(parts) do
            rects[name] = rect(f)
            yes(rects[name].l >= rr.l - 0.51 and rects[name].r <= rr.r + 0.51, w .. ": " .. k .. " " .. name .. " is inside the row")
            yes(math.abs((rects[name].t + rects[name].b) / 2 - (rr.t + rr.b) / 2) < 0.51, w .. ": " .. k .. " " .. name .. " is centred in the row")
            eq((rects[name].t - rects[name].b) % 2, 0, k .. " " .. name .. " has an even height")
        end
        for a, ra in pairs(rects) do
            for b, rb in pairs(rects) do
                if a < b then no(overlap(ra, rb), w .. ": " .. k .. " " .. a .. " and " .. b .. " overlap") end
            end
        end
        yes(rects.holder.l - rr.l > #row.fsLabel:GetText() * 6 + 8 + 12 + 8, w .. ": the controls leave room for the label and its ?")
    end
end

function T.the_band_and_the_rows_fit_at_the_smallest_default_and_largest_window()
    local W = bootBar()
    W.Open("data")
    typeTitle("time", "CLOCK"):ClearFocus()
    for _, size in ipairs({ { 780, 560 }, { 960, 640 }, { 1600, 1000 } }) do fits(W, size[1], size[2]) end
end

function T.the_reset_button_of_a_changed_row_sits_left_of_the_title_box_and_fits()
    local W = bootBar()
    W.Open("data")
    typeTitle("time", "CLOCK"):ClearFocus()
    local rect = solveAll()
    local row = rowOf("time")
    local rr, holder, reset = rect(row), rect(row.fsTitleBox:GetParent()), rect(row.fsReset)
    yes(reset.r <= holder.l + 0.51 and reset.r > holder.l - 9, "the reset is one gap left of the title box")
    yes(reset.l >= rr.l)
end
"""

PROTO: dict = {}


def prototype() -> dict:
    html = MOCKUP.read_text(encoding="utf-8")
    seg = re.search(r"const DSEG=\[(.*?)\];", html, re.S)
    tip = re.search(r"const DTIP=\{(.*?)\};", html, re.S)
    if not (seg and tip):
        raise ValueError("DSEG or DTIP is not in the mockup")
    segs = re.findall(r"\['(\w+)','([^']*)',(\d)\]", seg.group(1))
    tips = dict(re.findall(r"(\w+):'([^']*)'", tip.group(1)))
    seg_tip = re.search(r"\{t:'Segments',order:1,tip:'([^']*)'", html)
    prev_tip = re.search(r"i===-5\)\{html='<span class=\"t1\">Preview</span><br>([^']*)';", html)
    if not (seg_tip and prev_tip):
        raise ValueError("the Segments or PREVIEW tip is not in the mockup")
    return {
        "rows": [{"key": k, "label": label, "on": on == "1", "tip": tips[k]} for k, label, on in segs],
        "segmentsTip": seg_tip.group(1),
        "previewTip": prev_tip.group(1),
    }


LAYOUT_NAMES: set[str] = set()


def run_lua_checks() -> int:
    global LAYOUT_NAMES, PROTO
    LAYOUT_NAMES = {n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", CHECKS, re.M)}
    base.CHECKS = base.CHECKS.replace("__checks = T", layout.SOLVER + CHECKS + "\n__checks = T")
    bar_src = BAR_FILE.read_text(encoding="utf-8")
    failed = 0
    try:
        PROTO = prototype()
    except (OSError, ValueError) as err:
        print(f"FAIL  the_prototype_is_readable: {err}")
        PROTO = {"rows": [], "segmentsTip": "", "previewTip": ""}
        failed += 1
    for name in sorted(LAYOUT_NAMES):
        try:
            lua = base.boot()
            lua.globals().__dataBarSrc = bar_src
            lua.globals().__proto = base.to_lua(lua, PROTO)
            lua.eval("__checks")[name]()
            leaked = list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {' '.join(str(err).splitlines()[:2])[:400]}")
    return failed


# ---- python level checks --------------------------------------------------------------------------------------------


def lua_value(text: str, name: str) -> str | None:
    """The right side of `local NAME = ...` (comment cut), spaces squeezed."""
    m = re.search(rf"^local {name}\s*=\s*(.+?)\s*(?:--.*)?$", text, re.M)
    return re.sub(r"\s+", "", m.group(1)) if m else None


def check_the_bands_measures_are_the_ones_dataBar_lua_keeps() -> list[str]:
    page, bar = PAGE_FILE.read_text(encoding="utf-8"), BAR_FILE.read_text(encoding="utf-8")
    problems = []
    for name in ("BAR_HEIGHT", "PAD_X", "LABEL_GAP", "DIVIDER_WIDTH", "METER_WIDTH", "METER_HEIGHT", "COIN_SIZE",
                 "COIN_TEXT_GAP", "COIN_GROUP_GAP", "METER_TRACK_FILL", "METER_FILL_LEFT", "COIN_GOLD", "COIN_SILVER",
                 "COIN_COPPER"):
        a, b = lua_value(page, name), lua_value(bar, name)
        if a is None or b is None or a != b:
            problems.append(f"{name}: page {a!r}, DataBar.lua {b!r}")
    m = re.search(r"^local RAIL_ALPHA, DIVIDER_ALPHA, METER_EDGE_ALPHA = ([\d.]+), ([\d.]+), ([\d.]+)", page, re.M)
    if not m:
        problems.append("RAIL_ALPHA, DIVIDER_ALPHA, METER_EDGE_ALPHA are not on one line")
    else:
        rail, divider, edge = (float(x) for x in m.groups())
        found = {
            "rail": re.search(r"rail:SetColorTexture\(COLOR_POWER\[1\], COLOR_POWER\[2\], COLOR_POWER\[3\], ([\d.]+)\)", bar),
            "divider": re.search(r"divider:SetColorTexture\(COLOR_POWER\[1\], COLOR_POWER\[2\], COLOR_POWER\[3\], ([\d.]+)\)", bar),
            "meter edge": re.search(r"METER_TRACK_BORDER = \{ COLOR_POWER\[1\], COLOR_POWER\[2\], COLOR_POWER\[3\], ([\d.]+) \}", bar),
        }
        for name, want in (("rail", rail), ("divider", divider), ("meter edge", edge)):
            got = found[name]
            if not got or abs(float(got.group(1)) - want) > 1e-9:
                problems.append(f"{name} alpha: page {want}, DataBar.lua {got.group(1) if got else None}")
    sizes = re.search(r"^local LABEL_SIZE, VALUE_SIZE = (\d+), (\d+)", page, re.M)
    label = re.search(r"ApplyOrbitron\(labelText, (\d+), COLOR_POWER\)", bar)
    value = re.search(r"ApplyMono\(valueText, (\d+), COLOR_TEXT_WHITE\)", bar)
    if not (sizes and label and value) or (sizes.group(1), sizes.group(2)) != (label.group(1), value.group(1)):
        problems.append("the label and value sizes differ from DataBar.lua")
    return problems


def check_every_segment_has_a_sample_value() -> list[str]:
    page, bar = PAGE_FILE.read_text(encoding="utf-8"), BAR_FILE.read_text(encoding="utf-8")
    defs = re.findall(r'^    \{ key = "(\w+)"', bar, re.M)
    block = re.search(r"^local SAMPLE = \{\n(.*?)^\}", page, re.M | re.S)
    if not block:
        return ["no SAMPLE table"]
    have = re.findall(r"^    (\w+) = \{", block.group(1), re.M)
    problems = []
    if not defs:
        problems.append("no segments found in DataBar.lua")
    if set(defs) - set(have):
        problems.append(f"no sample for {sorted(set(defs) - set(have))}")
    if set(have) - set(defs):
        problems.append(f"a sample for no segment: {sorted(set(have) - set(defs))}")
    return problems


def check_the_default_order_is_the_prototypes() -> list[str]:
    bar = BAR_FILE.read_text(encoding="utf-8")
    defs = re.findall(r'^    \{ key = "(\w+)", label = "([^"]*)"', bar, re.M)
    proto = [(r["key"], r["label"]) for r in PROTO["rows"]]
    return [] if defs == proto else [f"DataBar.lua {defs} differs from the prototype {proto}"]


def check_no_em_dash_or_tape_in_the_page_file() -> list[str]:
    text = PAGE_FILE.read_text(encoding="utf-8")
    problems = []
    if "—" in text or "–" in text:
        problems.append("an em or en dash")
    if re.search(r"\btape\b", text, re.I):
        problems.append("the word tape")
    return problems


def check_the_page_never_reads_the_bar_frame_or_secret_unit_data() -> list[str]:
    text = PAGE_FILE.read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    problems = []
    for pattern in (r"FS\.dataBar\b", r"ForeverSTUwaveDataBar", r"\bUnit[A-Z]\w+\(", r"InCombatLockdown", r"ReloadUI"):
        if re.search(pattern, code):
            problems.append(f"the page uses {pattern}")
    return problems


def check_the_page_file_is_in_the_toc_after_the_window_and_the_builders() -> list[str]:
    toc = [ln.strip() for ln in TOC_FILE.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("##")]
    want = ["Modules/Config/ConfigWindow.lua", "Modules/Config/ConfigBuilders.lua", "Modules/Config/ConfigPageDataBar.lua"]
    at = [toc.index(w) if w in toc else -1 for w in want]
    return [] if -1 not in at and at == sorted(at) else [f"toc order {at}"]


def main() -> int:
    failed = run_lua_checks()
    py_checks = [
        ("the_bands_measures_are_the_ones_dataBar_lua_keeps", check_the_bands_measures_are_the_ones_dataBar_lua_keeps),
        ("every_segment_has_a_sample_value", check_every_segment_has_a_sample_value),
        ("the_default_order_is_the_prototypes", check_the_default_order_is_the_prototypes),
        ("no_em_dash_or_tape_in_the_page_file", check_no_em_dash_or_tape_in_the_page_file),
        ("the_page_never_reads_the_bar_frame_or_secret_unit_data", check_the_page_never_reads_the_bar_frame_or_secret_unit_data),
        ("the_page_file_is_in_the_toc_after_the_window_and_the_builders", check_the_page_file_is_in_the_toc_after_the_window_and_the_builders),
    ]
    total = len(LAYOUT_NAMES) + len(py_checks)
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
