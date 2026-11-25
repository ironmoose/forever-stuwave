#!/usr/bin/env python3
"""Checks for the /fsconfig footer (ticket B2).

Runs the real ConfigWindow.lua, every page file and ConfigFooter.lua over the mock frames of tools/configwindow-harness.py
(the same way tools/configlayout-harness.py does) and pins:

  * RELOAD UI, RESET PAGE, CLOSE and the muted "changes apply instantly" sit in the footer slots at the spec sizes and
    fit at the smallest, default and largest window
  * Reload UI is the secure reload cover (the secure button laid over it on hover); a click without the cover only
    explains; ReloadUI is never called; it works with nothing pending
  * the pending count is the rows whose `reload` function names a change (plus extra sources, once per label); the chip,
    the pink edge and the tooltip follow it and list the labels
  * Reset page asks first with the count and the page name, resets only that page's changed keys through
    CW.ResetKeys, defaults to KEEP THEM on Enter and Esc, and is disabled at 0 and while settings are read-only
  * Esc closes the dialog first, then the window; CLOSE hides the window and says once, in plain words, that a reload waits
  * the window position is saved account wide (never in a profile), restored on the next session and clamped on screen
  * hover, pressed and disabled looks on every button

The mock does no anchor layout (the solver of configlayout-harness does); everything drawn is pending owner review.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FOOTER_FILE = ROOT / "forever-stuwave" / "Modules" / "Config" / "ConfigFooter.lua"
TOC_FILE = ROOT / "forever-stuwave" / "forever-stuwave.toc"


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load("configwindow_harness", "configwindow-harness.py")
layout = load("configlayout_harness", "configlayout-harness.py")
LuaError = base.LuaError

CHECKS = r"""
-- ---- fixtures and helpers --------------------------------------------------------------------------------------------

local function stubSR()
    local log = { covered = {}, explained = 0, reloads = 0, current = nil }
    ReloadUI = function() log.reloads = log.reloads + 1 end
    FS.SecureReload = {
        Cover = function(target) log.covered[#log.covered + 1] = target; log.current = target; return true end,
        Covering = function() return log.current end,
        Uncover = function() log.current = nil end,
        Explain = function() log.explained = log.explained + 1 end,
    }
    return log
end

-- Two pages of keyed switches, and two rows that name a change waiting on a reload (st.a, st.b flip them).
local function fixture(W)
    local st = { a = false, b = false }
    FS.Config.RegisterDefault("fa.one", false)
    FS.Config.RegisterDefault("fa.two", false)
    FS.Config.RegisterDefault("fb.one", false)
    W.RegisterCategory({ key = "fa", label = "Page A", group = "GENERAL", order = 70, build = function(c)
        W.UI.Toggle(c, { label = "Gunsight HUD", key = "fa.one", reload = function() return st.a and "Reload to build it" or nil end })
        W.UI.Toggle(c, { label = "Raid frames", key = "fa.two", reload = function() return st.b and "Reload" or nil end })
    end })
    W.RegisterCategory({ key = "fb", label = "Page B", group = "GENERAL", order = 71, build = function(c)
        W.UI.Toggle(c, { label = "Other", key = "fb.one" })
    end })
    return st
end

local function eqc(a, b, msg)
    for i = 1, 3 do
        if math.abs((a[i] or 0) - (b[i] or 0)) > 0.002 then
            error((msg or "colour") .. ": got " .. table.concat(a, ",") .. ", want " .. table.concat(b, ","), 2)
        end
    end
end

local function tipOf(owner)
    local from = #TOOLTIP.history
    owner.scripts.OnEnter(owner)
    local lines = {}
    for i = from + 1, #TOOLTIP.history do lines[#lines + 1] = TOOLTIP.history[i] end
    return table.concat(lines, "\n")
end

local function printedLines(pattern)
    local n = 0
    for _, line in ipairs(__printed) do if line:lower():find(pattern) then n = n + 1 end end
    return n
end

local function lastPoint(f) return f.points[#f.points] end

local function key(frame, k)
    frame.scripts.OnKeyDown(frame, k)
end

-- ---- the buttons -----------------------------------------------------------------------------------------------------

function T.the_footer_is_built_into_the_slots_when_the_window_first_shows()
    local W = boot()
    local F = W.Footer
    yes(F, "CW.Footer exists")
    eq(F.reload, nil, "nothing is built before the window shows")
    W.Open()
    local left, right = W.FooterSlot("left"), W.FooterSlot("right")
    yes(F.reload and F.reset and F.close and F.message, "the buttons and the message exist")
    eq(F.reload.parent, left); eq(F.reset.parent, left); eq(F.close.parent, right); eq(F.message.parent, right)
    eq(F.reload.fsLabel:GetText(), "RELOAD UI"); eq(F.reset.fsLabel:GetText(), "RESET PAGE"); eq(F.close.fsLabel:GetText(), "CLOSE")
    eq(F.message:GetText(), "changes apply instantly")
    eqc(F.message.themeColor, W.C.muted, "the message is muted")
    local built = F.reload
    W.Close(); W.Open()
    eq(F.reload, built, "built once")
end

function T.every_button_is_btn_h_tall_and_a_multiple_of_text_snap_wide()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local S = W.Spec
    for _, name in ipairs({ "reload", "reset", "edit", "close" }) do
        local b = W.Footer[name]
        eq(b.h, S.BTN_H, name .. " height"); eq(b.w % S.TEXT_SNAP, 0, name .. " width snaps to " .. S.TEXT_SNAP)
        yes(b.w >= b.fsLabel:GetStringWidth() + 2 * S.BTN_PAD_X, name .. " keeps BTN_PAD_X each side of its text")
    end
    st.a = true; st.b = true
    W.RefreshAll()
    local b, chip = W.Footer.reload, W.Footer.reload.fsChip
    eq(chip.h, S.COUNT_H, "the chip is COUNT_H tall"); eq(chip.w % S.TEXT_SNAP, 0, "the chip snaps")
    eq(b.w % S.TEXT_SNAP, 0)
    yes(b.w >= b.fsLabel:GetStringWidth() + S.CTL_GAP + chip.w + 2 * S.BTN_PAD_X, "the button holds the label and the chip")
    eqc(chip.fsEdges[1].color, W.C.pink, "the chip edge is pink")
    eq(chip.fsEdges[1].color[4], 0.5, "at half strength")
end

function T.the_footer_fits_at_the_smallest_default_and_largest_window()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    st.a = true; st.b = true
    W.RefreshAll()
    for _, size in ipairs({ { 780, 560 }, { 960, 640 }, { 1600, 1000 } }) do
        W.SetSize(size[1], size[2], false)
        local rect = solveAll()
        local win, D, S, F = rect(winFrame()), W.D, W.Spec, W.Footer
        for _, name in ipairs({ "reload", "reset", "edit", "close" }) do
            local r = rect(F[name])
            yes(r.l >= win.l + S.PAD - 0.01 and r.r <= win.r - S.PAD + 0.01, name .. " inside the window pad at " .. size[1])
            eq(win.t - r.t, D.BTN_Y, name .. " top is BTN_Y at " .. size[1])
            eq(r.t - r.b, S.BTN_H)
        end
        local a, r, b, c = rect(F.reload), rect(F.reset), rect(F.edit), rect(F.close)
        eq(r.l - a.r, 8, "the footer buttons sit 8 apart")
        eq(b.l - r.r, 8, "EDIT LAYOUT sits 8 after RESET PAGE")
        eq(win.r - S.PAD, c.r, "CLOSE sits at the right padding")
        yes(b.r < (win.l + win.r) / 2, "the left buttons stay in the left half at " .. size[1] .. ": " .. b.r)
        local msgW = #F.message:GetText() * 6
        yes(c.l - 8 - msgW >= b.r, "the message fits between EDIT LAYOUT and CLOSE at " .. size[1] .. ": " .. (c.l - 8 - msgW) .. " vs " .. b.r)
    end
end

-- ---- edit layout -----------------------------------------------------------------------------------------------------

function T.edit_layout_opens_the_layout_editor_and_comes_back_to_this_page()
    local W = boot()
    local asked = {}
    FS.LayoutEdit = { EnterFromConfig = function(page) asked[#asked + 1] = page; return true end }
    W.Open()
    local b = W.Footer.edit
    yes(b, "the button exists"); eq(b.fsLabel:GetText(), "EDIT LAYOUT")
    b.scripts.OnClick(b, "LeftButton")
    eq(#asked, 1, "one click opens the editor once")
    eq(asked[1], W.Current(), "DONE comes back to the page the click came from")
    FS.LayoutEdit = nil
    b.scripts.OnClick(b, "LeftButton")
    eq(#asked, 1, "no editor loaded: the click does nothing and throws nothing")
end

-- ---- reload ----------------------------------------------------------------------------------------------------------

function T.reload_ui_is_the_secure_cover_and_never_the_addon_reload()
    local W = boot()
    local sr = stubSR()
    W.Open()
    local b = W.Footer.reload
    yes(b:IsEnabled(), "works with nothing pending")
    b.scripts.OnEnter(b)
    eq(#sr.covered, 1, "the secure button is laid over it on hover"); eq(sr.covered[1], b)
    b.scripts.OnClick(b, "LeftButton")
    eq(sr.explained, 1, "a click without the cover only says why nothing happened")
    eq(sr.reloads, 0, "ReloadUI is never called from addon code")
    b.scripts.OnHide(b)
    eq(sr.current, nil, "hiding the button takes the cover away")
end

function T.the_cover_keeps_the_hover_look_and_the_tip_until_the_pointer_leaves_it()
    local W = boot()
    local sr = stubSR()
    W.Open()
    local b = W.Footer.reload
    b.scripts.OnEnter(b)
    yes(TOOLTIP.shown and TOOLTIP.owner == b, "the tip is up")
    b.scripts.OnLeave(b)                       -- the cover took the pointer
    yes(TOOLTIP.shown, "the tip stays while the cover is on the button")
    yes(b.fsOver, "and so does the hover look")
    sr.current = nil                           -- the pointer left the cover
    b.scripts.OnLeave(b)
    no(TOOLTIP.shown, "the tip goes with the pointer"); no(b.fsOver)
end

function T.reload_ui_still_answers_when_the_secure_reload_is_missing()
    local W = boot()
    FS.SecureReload = nil
    W.Open()
    local b = W.Footer.reload
    b.scripts.OnEnter(b)
    b.scripts.OnClick(b, "LeftButton")
    no(printedLines("error") > 0)
end

function T.the_pending_count_follows_the_rows_and_the_tip_lists_them_by_label()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    eq(#F.Pending(), 0); eq(F.reload.fsCount, 0)
    no(F.reload.fsChip:IsShown(), "no chip with nothing waiting"); no(F.reload.fsHot)
    yes(tipOf(F.reload):find("Nothing is waiting on a reload.", 1, true), "the tip says nothing waits")
    st.a = true
    W.RefreshAll()
    eq(F.reload.fsCount, 1); yes(F.reload.fsChip:IsShown()); eq(F.reload.fsChip.fsText:GetText(), "1"); yes(F.reload.fsHot)
    st.b = true
    W.RefreshAll()
    eq(F.reload.fsChip.fsText:GetText(), "2")
    local tip = tipOf(F.reload)
    yes(tip:find("Gunsight HUD", 1, true) and tip:find("Raid frames", 1, true), "the tip lists the rows by label: " .. tip)
    no(tip:find("Other", 1, true), "and only the waiting ones")
    st.a = false
    W.RefreshAll()
    eq(F.reload.fsCount, 1); eq(F.reload.fsChip.fsText:GetText(), "1")
    st.b = false
    W.RefreshAll()
    eq(F.reload.fsCount, 0); no(F.reload.fsChip:IsShown()); no(F.reload.fsHot, "the edge goes with the last change")
end

function T.a_changed_setting_row_flips_the_count_through_the_config_change_event()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    st.a = true                                            -- what the module reports once the switch moved
    FS.Config.Set("fa.one", true)                          -- RefreshAll runs on any change
    eq(F.reload.fsCount, 1, "no manual refresh needed")
    W.Close()
    st.b = true
    W.Open("fa")
    eq(F.reload.fsCount, 2, "a change made while the window was shut is counted when it opens")
end

function T.extra_sources_count_once_per_label_and_a_failing_row_or_source_is_skipped()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    st.a, st.b = true, true
    yes(W.AddReloadSource(function() return { "Raid frames", { label = "Data bar", line = "x" }, "", 5 } end))
    yes(W.AddReloadSource(function() error("boom") end))
    no(W.AddReloadSource("nope"), "a bad source is refused")
    W.RegisterCategory({ key = "fc", label = "Page C", group = "GENERAL", order = 72, build = function(c)
        W.UI.Toggle(c, { label = "Broken", key = "fc.broken" })
    end })
    W.Open("fc")
    W.RowByKey("fc.broken").reload = function() error("bad row") end           -- a row whose reload line throws
    W.Open("fa")
    W.RefreshAll()
    local labels = {}
    for _, item in ipairs(F.Pending()) do labels[#labels + 1] = item.label end
    eq(table.concat(labels, ","), "Gunsight HUD,Raid frames,Data bar,5", "the row first, then the sources, each label once")
    eq(F.reload.fsCount, 4)
end

function T.the_reload_button_is_hot_while_something_waits_and_its_glow_breathes()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    local b = F.reload
    eqc(b.fsSkin.border.ring.color, W.C.violet, "violet edge at rest")
    eq(b.scripts.OnUpdate, nil, "no per frame work at rest")
    st.a = true
    W.RefreshAll()
    eqc(b.fsSkin.border.ring.color, W.C.pink, "pink edge while a reload waits")
    eqc(b.fsLabel.themeColor, W.C.pink, "and pink text")
    yes(b.scripts.OnUpdate, "the glow breathes through an OnUpdate")
    local lo, hi = 1, 0
    for i = 0, 16 do
        b.scripts.OnUpdate(b, 0.1)
        local a = b.fsSkin.glow.color[4]
        lo, hi = math.min(lo, a), math.max(hi, a)
    end
    yes(lo >= 0.2 - 0.001 and hi <= 0.5 + 0.001 and hi - lo > 0.2, "the glow stays in 0.2 to 0.5 and moves: " .. lo .. " to " .. hi)
    st.a = false
    W.RefreshAll()
    eq(b.scripts.OnUpdate, nil, "the OnUpdate goes when nothing waits")
    eqc(b.fsSkin.border.ring.color, W.C.violet)
end

-- ---- reset page ------------------------------------------------------------------------------------------------------

function T.reset_page_is_disabled_when_nothing_on_the_page_changed()
    local W = boot()
    fixture(W)
    W.Open("fa")
    local F = W.Footer
    no(F.reset:IsEnabled(), "disabled at 0"); eq(F.reset:GetAlpha(), 0.4, "dimmed")
    no(F.reset.fsChip:IsShown(), "no chip at 0")
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    no(F.Dialog(), "a click on the disabled button asks nothing")
    yes(tipOf(F.reset):find("Nothing on this page differs from its defaults.", 1, true), "the tip says why")
    no(F.OpenReset(), "OpenReset refuses with nothing to reset")
end

function T.the_reset_count_follows_the_page_on_screen()
    local W = boot()
    fixture(W)
    FS.Config.Set("fa.one", true); FS.Config.Set("fa.two", true); FS.Config.Set("fb.one", true)
    W.Open("fa"); W.Open("fb"); W.Open("fa")
    local F = W.Footer
    eq(F.reset.fsCount, 2); eq(F.reset.fsChip.fsText:GetText(), "2"); yes(F.reset:IsEnabled())
    W.Open("fb")
    eq(F.reset.fsCount, 1, "page B has one changed setting")
    FS.Config.Set("fb.one", false)
    eq(F.reset.fsCount, 0); no(F.reset:IsEnabled())
end

function T.reset_page_asks_with_the_count_and_the_page_name_and_resets_only_that_page()
    local W = boot()
    fixture(W)
    FS.Config.Set("fa.one", true); FS.Config.Set("fa.two", true); FS.Config.Set("fb.one", true)
    W.Open("fb"); W.Open("fa")
    local F = W.Footer
    local asked
    local resetKeys = W.ResetKeys
    W.ResetKeys = function(list) asked = list; return resetKeys(list) end
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    local d = F.Dialog()
    yes(d and d.overlay:IsShown(), "the dialog opens")
    eq(asked, nil, "nothing is written before the answer")
    eq(d.message:GetText(), "Put the 2 changed settings on Page A back to their defaults?")
    eq(d.title:GetText(), "RESET PAGE"); eqc(d.title.themeColor, W.C.pink, "the title is pink")
    eq(d.keep.fsLabel:GetText(), "KEEP THEM"); eq(d.reset.fsLabel:GetText(), "RESET 2")
    eqc(d.reset.fsSkin.border.ring.color, W.C.pink, "RESET N is the pink one")
    eq(d.panel.w, W.Spec.DLG_W); eq(d.panel.h, W.Spec.DLG_H)
    eq(FS.Config.Get("fa.one"), true, "still changed")
    d.reset.scripts.OnClick(d.reset, "LeftButton")
    eq(table.concat(asked, ","), "fa.one,fa.two", "CW.ResetKeys got exactly this page's changed keys")
    no(d.overlay:IsShown(), "the dialog closes")
    eq(FS.Config.Get("fa.one"), false); eq(FS.Config.Get("fa.two"), false)
    eq(FS.Config.Get("fb.one"), true, "the other page keeps its change")
    eq(F.reset.fsCount, 0); no(F.reset:IsEnabled(), "disabled again")
end

function T.the_dialog_says_one_setting_in_the_singular()
    local W = boot()
    fixture(W)
    FS.Config.Set("fb.one", true)
    W.Open("fb")
    W.Footer.reset.scripts.OnClick(W.Footer.reset, "LeftButton")
    eq(W.Footer.Dialog().message:GetText(), "Put the 1 changed setting on Page B back to its default?")
    eq(W.Footer.Dialog().reset.fsLabel:GetText(), "RESET 1")
end

function T.keep_them_is_the_default_enter_and_esc_keep_every_setting()
    local W = boot()
    fixture(W)
    FS.Config.Set("fa.one", true)
    W.Open("fa")
    local F = W.Footer
    for _, k in ipairs({ "ENTER", "ESCAPE", "NUMPADENTER" }) do
        F.reset.scripts.OnClick(F.reset, "LeftButton")
        local d = F.Dialog()
        yes(d.overlay:IsShown(), "open before " .. k)
        yes(d.overlay.keyboard, "the dialog takes the keyboard while it is up")
        key(d.overlay, k)
        no(d.overlay:IsShown(), k .. " closes the dialog")
        eq(d.overlay.propagate, false, k .. " is consumed")
        no(d.overlay.keyboard, "the keyboard is released")
        eq(FS.Config.Get("fa.one"), true, k .. " kept the setting")
    end
    local d = F.Dialog()
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    d.keep.scripts.OnClick(d.keep, "LeftButton")
    no(d.overlay:IsShown(), "KEEP THEM closes it"); eq(FS.Config.Get("fa.one"), true)
end

function T.esc_closes_the_dialog_first_then_the_window()
    local W = boot()
    fixture(W)
    FS.Config.Set("fa.one", true)
    W.Open("fa")
    local F = W.Footer
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    local d = F.Dialog()
    key(d.overlay, "W")
    yes(d.overlay:IsShown(), "another key leaves the dialog up"); eq(d.overlay.propagate, true, "and still reaches the game")
    key(d.overlay, "ESCAPE")
    no(d.overlay:IsShown()); yes(W.IsShown(), "the window is still up after the first Esc")
    eq(d.overlay.propagate, false, "so the game's own Esc does not also run")
    local special
    for _, name in ipairs(UISpecialFrames) do if name == "ForeverSTUwaveConfig" then special = name end end
    yes(special, "the window itself closes on the next Esc (a special frame)")
    _G[special]:Hide()
    no(W.IsShown(), "the second Esc closes the window")
end

function T.the_dialog_closes_with_the_window_and_covers_the_generic_one()
    local W = boot()
    fixture(W)
    FS.Config.Set("fa.one", true)
    W.Open("fa")
    local F = W.Footer
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    local d = F.Dialog()
    yes(d.overlay:GetFrameLevel() >= _G.ForeverSTUwaveConfig:GetFrameLevel() + 40, "above the generic confirm dialog")
    W.Close()
    no(d.overlay:IsShown(), "a closed window leaves no dialog behind")
    W.Open("fa")
    no(d.overlay:IsShown(), "and it is not there when the window opens again")
end

function T.read_only_settings_disable_reset_page_but_not_reload()
    local W = boot({ db = "junk" })
    stubSR()
    W.Open()
    local F = W.Footer
    yes(FS.Config.IsReadOnly())
    yes(F.reload:IsEnabled(), "a reload changes no setting")
    no(F.reset:IsEnabled())
    yes(tipOf(F.reset):find("read-only", 1, true), "the tip says why")
    no(F.OpenReset())
end

-- ---- close -----------------------------------------------------------------------------------------------------------

function T.close_hides_the_window_and_says_nothing_with_no_reload_waiting()
    local W = boot()
    fixture(W)
    W.Open("fa")
    local F = W.Footer
    F.close.scripts.OnClick(F.close, "LeftButton")
    no(W.IsShown(), "CLOSE hides the window")
    eq(printedLines("reload"), 0, "no line when nothing waits")
end

function T.closing_with_a_reload_waiting_prints_one_neutral_line()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    st.a = true; st.b = true
    W.RefreshAll()
    local before = #__printed
    F.close.scripts.OnClick(F.close, "LeftButton")
    eq(#__printed - before, 1, "exactly one line")
    local line = __printed[#__printed]
    yes(line:find("2 changes wait for a reload", 1, true), line)
    yes(line:find("Reload UI", 1, true), "it names the button")
    no(line:lower():find("bot") or line:lower():find("auto") or line:lower():find("macro") or line:lower():find("script"),
        "no automation wording: " .. line)
    W.Open("fa")
    W.Close()                                               -- the X and Esc hide the frame the same way
    eq(#__printed - before, 2, "every close says it once")
    st.a, st.b = false, false
    W.Open("fa")
    W.Close()
    eq(#__printed - before, 2, "and nothing once nothing waits")
    st.b = true
    W.Open("fa")
    W.Close()
    yes(__printed[#__printed]:find("1 change waits for a reload", 1, true), "singular: " .. __printed[#__printed])
end

-- ---- window position -------------------------------------------------------------------------------------------------

function T.the_position_is_saved_after_a_drag_account_wide_and_restored_next_session()
    local W = boot()
    W.Open()
    local win = _G.ForeverSTUwaveConfig
    win.left, win.top = 300, 900
    win.scripts.OnDragStop(win)
    eq(ForeverSTUwaveDB.ui.winX, 300); eq(ForeverSTUwaveDB.ui.winY, 900 - 1440, "an offset from the top left of the screen")
    for name, profile in pairs(ForeverSTUwaveDB.profiles) do
        eq(profile.settings.winX, nil, "not in the profile " .. name); eq(profile.settings.winY, nil)
    end
    local W2 = reload()
    W2.Open()
    local p = lastPoint(_G.ForeverSTUwaveConfig)
    eq(p.point, "TOPLEFT"); eq(p.rel, UIParent); eq(p.relPoint, "BOTTOMLEFT")
    eq(p.x, 300); eq(p.y, 900)
end

function T.a_window_never_moved_keeps_its_default_seat()
    local W = boot()
    W.Open()
    local p = lastPoint(_G.ForeverSTUwaveConfig)
    eq(p.point, "CENTER", "no saved position, no change to the seat")
    W.Close()
    eq(ForeverSTUwaveDB.ui.winX, nil, "closing does not save a position")
end

function T.a_saved_position_off_the_screen_is_clamped_back_on()
    local W = boot()
    W.Open()
    ForeverSTUwaveDB.ui = ForeverSTUwaveDB.ui or {}
    ForeverSTUwaveDB.ui.winX, ForeverSTUwaveDB.ui.winY = 5000, 100          -- far right, above the top edge
    local W2 = reload()
    W2.Open()
    local win = _G.ForeverSTUwaveConfig
    local p = lastPoint(win)
    eq(p.x, UIParent.w - win.w, "the right edge stops at the screen edge")
    eq(p.y, UIParent.h, "the top stops at the top edge")
    ForeverSTUwaveDB.ui.winX, ForeverSTUwaveDB.ui.winY = -900, -5000        -- left of the screen, below the bottom
    local W3 = reload()
    W3.Open()
    p = lastPoint(_G.ForeverSTUwaveConfig)
    eq(p.x, 0); eq(p.y, _G.ForeverSTUwaveConfig.h, "the whole window stays above the bottom edge")
end

function T.clamp_position_keeps_the_whole_window_on_the_screen()
    local W = boot()
    local clamp = W.Footer.ClampPosition
    local l, t = clamp(100, 700, 960, 640, 2560, 1440)
    eq(l, 100); eq(t, 700, "inside stays put")
    l, t = clamp(-50, 2000, 960, 640, 2560, 1440)
    eq(l, 0); eq(t, 1440)
    l, t = clamp(2000, 10, 960, 640, 2560, 1440)
    eq(l, 1600); eq(t, 640)
    l, t = clamp(300, 300, 1600, 1000, 1280, 720)
    eq(l, 0, "a window wider than the screen sits at the left"); eq(t, 720, "and one taller sits at the top")
end

function T.a_window_in_another_scale_is_saved_and_seated_in_screen_units()
    local W = boot()
    W.Open()
    local win = _G.ForeverSTUwaveConfig
    function win:GetEffectiveScale() return 0.5 end                          -- UIParent stays 1
    win.left, win.top = 400, 800                                             -- in the window's own units
    win.scripts.OnDragStop(win)
    eq(ForeverSTUwaveDB.ui.winX, 200); eq(ForeverSTUwaveDB.ui.winY, 400 - 1440)
    local W2 = reload()
    W2.Open()
    local win2 = _G.ForeverSTUwaveConfig
    function win2:GetEffectiveScale() return 0.5 end
    W2.Footer.RestorePosition()
    local p = lastPoint(win2)
    eq(p.x, 400); eq(p.y, 800, "seated back in the window's own units")
end

-- ---- looks -----------------------------------------------------------------------------------------------------------

function T.every_button_has_hover_pressed_and_disabled_looks()
    local W = boot()
    local st = fixture(W)
    FS.Config.Set("fa.one", true)
    W.Open("fa")
    local F, C = W.Footer, W.C
    local function walk(b, name, ring)
        local rest = { b.fsFill.color[1], b.fsFill.color[2], b.fsFill.color[3] }
        b.scripts.OnEnter(b)
        local hover = { b.fsFill.color[1], b.fsFill.color[2], b.fsFill.color[3] }
        yes(hover[1] ~= rest[1] or hover[2] ~= rest[2] or hover[3] ~= rest[3], name .. ": hover tints the face")
        b.scripts.OnMouseDown(b)
        local down = { b.fsFill.color[1], b.fsFill.color[2], b.fsFill.color[3] }
        yes(down[1] ~= hover[1] or down[2] ~= hover[2] or down[3] ~= hover[3], name .. ": pressed tints further")
        yes(math.abs(down[1] - rest[1]) + math.abs(down[2] - rest[2]) + math.abs(down[3] - rest[3])
            > math.abs(hover[1] - rest[1]) + math.abs(hover[2] - rest[2]) + math.abs(hover[3] - rest[3]), name .. ": pressed is stronger than hover")
        b.scripts.OnMouseUp(b)
        eqc(b.fsFill.color, hover, name .. ": release goes back to hover")
        b.scripts.OnLeave(b)
        eqc(b.fsFill.color, rest, name .. ": leaving goes back to rest")
    end
    walk(F.reload, "reload"); walk(F.reset, "reset"); walk(F.close, "close")
    st.a = true
    W.RefreshAll()
    walk(F.reload, "hot reload")
    -- disabled: no hover or press, dimmed
    FS.Config.Set("fa.one", false)
    no(F.reset:IsEnabled())
    local rest = { F.reset.fsFill.color[1], F.reset.fsFill.color[2], F.reset.fsFill.color[3] }
    F.reset.scripts.OnEnter(F.reset); F.reset.scripts.OnMouseDown(F.reset)
    eqc(F.reset.fsFill.color, rest, "a disabled button shows no hover or press")
    eq(F.reset:GetAlpha(), 0.4)
    F.reset.scripts.OnLeave(F.reset); F.reset.scripts.OnMouseUp(F.reset)
    FS.Config.Set("fa.one", true)
    eq(F.reset:GetAlpha(), 1, "back to full when there is something to reset")
    -- the dialog buttons
    F.reset.scripts.OnClick(F.reset, "LeftButton")
    local d = F.Dialog()
    walk(d.keep, "keep them"); walk(d.reset, "reset n")
    eqc(d.reset.fsFill.color, W.I.Mix(C.ink, C.pink, 0.08), "RESET N rests on the dark pink face")
    eqc(d.reset.fsLabel.themeColor, C.text, "with plain text")
    eqc(d.keep.fsSkin.border.ring.color, C.violet)
end

-- ---- the refresh -----------------------------------------------------------------------------------------------------

function T.the_footer_repaints_with_every_refresh_and_not_while_the_window_is_hidden()
    local W = boot()
    local st = fixture(W)
    W.Open("fa")
    local F = W.Footer
    local runs = 0
    local update = F.Update
    for i, fn in ipairs(W.I.controls) do if fn == update then runs = runs + 1 end end
    eq(runs, 1, "one global refresh function, not one per build")
    W.Close(); W.Open("fa"); W.Close(); W.Open("fa")
    runs = 0
    for _, fn in ipairs(W.I.controls) do if fn == update then runs = runs + 1 end end
    eq(runs, 1, "still one after the window opened again")
    W.Close()
    st.a = true
    W.RefreshAll()
    eq(F.reload.fsCount, 0, "a hidden window only marks; the count is read when it opens")
    W.Open("fa")
    eq(F.reload.fsCount, 1)
end
"""

LAYOUT_NAMES: set[str] = set()


def run_lua_checks() -> int:
    global LAYOUT_NAMES
    LAYOUT_NAMES = {n for n in re.findall(r"^function T\.([a-z0-9_]+)\(", CHECKS, re.M)}
    base.CHECKS = base.CHECKS.replace("__checks = T", layout.SOLVER + CHECKS + "\n__checks = T")
    failed = 0
    for name in sorted(LAYOUT_NAMES):
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


# ---- python level checks --------------------------------------------------------------------------------------------


def check_the_footer_never_calls_the_addon_reload() -> list[str]:
    text = FOOTER_FILE.read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    problems = []
    for pattern in (r"ReloadUI\s*\(", r"C_UI\.Reload", r"\bReloadUI\b", r"RunScript", r"loadstring"):
        if re.search(pattern, code):
            problems.append(f"ConfigFooter.lua uses {pattern}")
    if "FS.SecureReload" not in code or "SR.Cover" not in code:
        problems.append("the Reload button does not go through FS.SecureReload.Cover")
    return problems


def check_no_em_dash_or_tape_in_the_footer_file() -> list[str]:
    text = FOOTER_FILE.read_text(encoding="utf-8")
    problems = []
    if "—" in text or "–" in text:
        problems.append("an em or en dash")
    if re.search(r"\btape\b", text, re.I):
        problems.append("the word tape")
    return problems


def check_the_footer_loads_after_the_search_file() -> list[str]:
    toc = [ln.strip() for ln in TOC_FILE.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("##")]
    want = ["Modules/Config/ConfigWindow.lua", "Modules/Config/ConfigBuilders.lua", "Modules/Config/ConfigSearch.lua",
            "Modules/Config/ConfigFooter.lua", "Modules/Config/ConfigFlash.lua"]
    at = [toc.index(w) if w in toc else -1 for w in want]
    if -1 in at or at != sorted(at):
        return [f"toc order {at}"]
    return []


def check_the_footer_text_comes_from_the_mockup() -> list[str]:
    root = Path(base.os.environ.get("FS_MOCKUPS_DIR", ROOT / "mockups"))
    html = (root / "config-window-2026-11-25.html").read_text(encoding="utf-8")
    text = FOOTER_FILE.read_text(encoding="utf-8")
    problems = []
    for words in ("RELOAD UI", "RESET PAGE", "CLOSE", "KEEP THEM", "changes apply instantly"):
        if words not in html:
            problems.append(f"{words!r} is not in the mockup")
        if words not in text:
            problems.append(f"{words!r} is not in ConfigFooter.lua")
    m = re.search(r"Put the \$\{pageMods\} changed settings on \$\{P\.label\} back to their defaults\?", html)
    if not m or "their defaults" not in text or "Put the %d changed" not in text:
        problems.append("the dialog message differs from the mockup")
    for name in ("FOOT_H", "BTN_H", "BTN_PAD_X", "DLG_W", "DLG_H", "COUNT_H"):
        if not re.search(rf"\['{name}',\d+", html):
            problems.append(f"{name} is not in the mockup SPEC")
    return problems


def main() -> int:
    failed = run_lua_checks()
    py_checks = [
        ("the_footer_never_calls_the_addon_reload", check_the_footer_never_calls_the_addon_reload),
        ("no_em_dash_or_tape_in_the_footer_file", check_no_em_dash_or_tape_in_the_footer_file),
        ("the_footer_loads_after_the_search_file", check_the_footer_loads_after_the_search_file),
        ("the_footer_text_comes_from_the_mockup", check_the_footer_text_comes_from_the_mockup),
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
