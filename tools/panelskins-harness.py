#!/usr/bin/env python3
"""Runs the real PanelSkins.lua `HookInlineColorRewrite` headless against a mock button.

Blizzard writes a quest title row with an inline black color code (`NORMAL_QUEST_DISPLAY` is
`|cff000000%s|r`) BEFORE our row skin runs, so a hook that only watches FUTURE SetText calls leaves
the first-acquired row black on the dark panel (playtest 2026-10-04: all three trainer quests black
after /reload, the plain option row light). The properties pinned here:

  * text already on the target when the hook is installed is rewritten at once;
  * later SetText / SetFormattedText calls are still rewritten;
  * a bright state colour (red "can't afford") is never touched, hooked or not;
  * hooking the same target twice installs one hook (one rewrite, no recursion);
  * the emitted code is the exact parchment hex (#bfe9d6), rounded not truncated;
  * a secret current text, a number or a secret SetText argument is skipped without error;
  * a SetText that throws inside the rewrite does not leave the target stuck (it keeps rewriting);
  * a rewrite that keeps throwing logs one degrade line per session (the latch), and a missing
    FS.LogDegradeOnce neither errors nor spends the latch;
  * the quest log pane (QuestMapFrame) is skinned WITHOUT a title: its Blizzard search box sits in
    the top band the title would draw, so the `stuwave://questlog` label read as a second, offset
    "Search Quest Log" (playtest 2026-10-21). The real Panels.lua runs against a recording SkinPanel.

  * the text button sweep (PanelSkins.SweepTextButtons): every stock text button in a skinned panel's tree
    (UIPanelButtonTemplate keys Left, Middle, Right; ThreeSliceButtonTemplate keys Left, Center, Right, with a
    label) gets the shared STUwave text button, its accent chosen by the label (cyan commits, pink declines),
    while tabs, icon-only buttons, dropdowns, scroll rows and buttons an earlier skin owns are left alone, the
    walk is bounded, and no script or attribute of a Blizzard button is ever written;
  * the scroll bar sweep (PanelSkins.SweepScrollBars): every scroll bar the shared skin recognises in a skinned
    panel's tree, beside its ScrollBox wherever that sits, is skinned once, never walked into, and a bar
    built after the first sweep is skinned when the panel is shown again.

The dark-text gate is the real `IsDarkText` text lifted out of Theme.lua, so a gate change fails
here. The mock is NOT the real client. Run:

    python3 tools/panelskins-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
PANELSKINS_SRC = (ADDON / "Core/PanelSkins.lua").read_text(encoding="utf-8")
PANELS_SRC = (ADDON / "Modules/Skins/Panels.lua").read_text(encoding="utf-8")
THEME_SRC = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")


def theme_dark_text_lua() -> str:
    """The real Luma / DARK_TEXT_LUMA / IsDarkText text from Theme.lua, so the gate cannot drift."""
    luma = re.search(r"local function Luma\(.*?\nend\n", THEME_SRC, re.S)
    thresh = re.search(r"^local DARK_TEXT_LUMA = [0-9.]+$", THEME_SRC, re.M)
    gate = re.search(r"local function IsDarkText\(.*?\nend\n", THEME_SRC, re.S)
    parchment = re.search(r"^Theme\.COLOR_TEXT_PARCHMENT = \{.*?\}", THEME_SRC, re.M)
    if not (luma and thresh and gate and parchment):
        sys.exit("panelskins-harness: could not find Luma/IsDarkText/COLOR_TEXT_PARCHMENT in Theme.lua")
    return "\n".join(
        [luma.group(0), thresh.group(0), gate.group(0), parchment.group(0).replace("Theme.", "THEME.", 1)]
    )


MOCK = r"""
SlashCmdList = {}
function CreateFrame() return setmetatable({}, { __index = function() return function() end end }) end
function InCombatLockdown() return false end

-- hooksecurefunc(tbl, name, fn): the real one swaps tbl[name] for a wrapper that runs the original
-- then fn with the same arguments; a call made from inside fn goes back through the wrapper.
function hooksecurefunc(tbl, name, fn)
    local orig = tbl[name]
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

-- A Button's text accessors. `writes` counts every underlying SetText, hook re-writes included.
function NewButton(initial)
    local b = { text = initial, writes = 0 }
    function b:SetText(t)
        self.writes = self.writes + 1
        -- failOnRewrite: throw once when the hook writes the rewritten (parchment) code back;
        -- failForever keeps throwing on every such write (what the log latch exists for).
        if self.failOnRewrite and type(t) == "string" and t:find(PARCHMENT_CODE, 1, true) then
            if not self.failForever then self.failOnRewrite = false end
            error("SetText blew up")
        end
        self.text = t
    end
    function b:SetFormattedText(fmt, ...) self.writes = self.writes + 1; self.text = string.format(fmt, ...) end
    function b:GetText() return self.text end
    return b
end

function LoadPanelSkins()
    THEME = {}
    local degraded = {}
    local FS = {
        Theme = THEME,
        degraded = degraded, -- every LogDegradeOnce call as {key, msg}; the real one does not dedupe
        LogDegradeOnce = function(key, msg) degraded[#degraded + 1] = { key, msg } end,
        -- SECRET_TEXT carries a dark code, so skipping it (not rewriting it) is observable.
        IsSecret = function(v) return v == SECRET_TEXT end,
    }
    assert(loadstring(THEME_DARK_TEXT_SRC .. "\nTHEME.IsDarkText = IsDarkText", "@Theme.lua(gate)"))()
    local chunk = assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))
    chunk("forever-stuwave", FS)
    return FS
end

-- Runs the real Panels.lua over the real PanelSkins.lua with every frame in `present` existing as an
-- empty table, and returns { [frame name] = the opts SkinPanel was given }. Theme is a recorder: the
-- point is WHICH frames get WHICH chrome options, not how the chrome draws.
function LoadPanels(present)
    local FS = LoadPanelSkins()
    local skinned = {}
    local function noop() end
    THEME.SkinPanel = function(frame, opts) skinned[frame.fsName] = opts end
    THEME.StyleMoney, THEME.ApplyMono, THEME.SkinButton, THEME.LightenParchmentFonts = noop, noop, noop, noop
    THEME.COLOR_BG, THEME.COLOR_BORDER, THEME.COLOR_POWER = { 0, 0, 0 }, { 1, 1, 1 }, { 1, 1, 1 }
    THEME.COLOR_TEXT_PARCHMENT = { 0.749, 0.914, 0.839 }
    for _, name in ipairs(present) do _G[name] = { fsName = name } end
    assert(loadstring(PANELS_SRC, "@Panels.lua"))("forever-stuwave", FS)
    for _, name in ipairs(present) do _G[name] = nil end
    return skinned
end

-- A Blizzard frame or button for the text button sweep. SetScript and SetAttribute throw: the sweep adds
-- textures and post-hooks (through ButtonSkins) only, never a write to a Blizzard widget's own handlers.
function Widget(kind, fields)
    local w = { kind = kind, children = {}, hooks = {}, shown = true }
    function w:GetObjectType() return self.kind end
    function w:GetChildren() return unpack(self.children) end
    function w:GetText() return self.text end
    function w:IsShown() return self.shown end
    function w:IsProtected() return self.protected == true end
    function w:HookScript(script, fn)
        self.hooks[script] = self.hooks[script] or {}
        table.insert(self.hooks[script], fn)
    end
    function w:SetScript() error("SetScript on a Blizzard widget") end
    function w:SetAttribute() error("SetAttribute on a Blizzard widget") end
    if fields then for k, v in pairs(fields) do w[k] = v end end
    return w
end
function Add(parent, child) parent.children[#parent.children + 1] = child; return child end
function StockButton(text, extra)
    local b = Widget("Button", { text = text, Left = {}, Middle = {}, Right = {} })
    if extra then for k, v in pairs(extra) do b[k] = v end end
    return b
end
function ShowAgain(w) for _, fn in ipairs(w.hooks.OnShow or {}) do fn(w) end end

-- PanelSkins plus a recorder for the shared text button. `owned` = buttons an earlier skin already owns.
function LoadSweep()
    local FS = LoadPanelSkins()
    local calls, owned = {}, {}
    FS.ButtonSkins = {
        Parts = function(button) return owned[button] end,
        SkinTextButton = function(button, opts)
            calls[#calls + 1] = { button = button, opts = opts or {} }
            owned[button] = owned[button] or { accent = (opts or {}).accent } -- what the real skin does
        end,
    }
    local bars, barOwned = {}, {}
    FS.ScrollBarSkins = {
        IsScrollBar = function(obj) return type(obj) == "table" and obj.isBar == true end,
        Parts = function(obj) return barOwned[obj] end,
        Skin = function(obj) bars[#bars + 1] = obj; barOwned[obj] = {}; return true end,
    }
    return FS, calls, owned, bars, barOwned
end
function Bar() return Widget("EventFrame", { isBar = true }) end
function CallFor(calls, button)
    for _, c in ipairs(calls) do if c.button == button then return c end end
end

-- The code the rewrite must emit for the parchment token, spelled out rather than recomputed so a
-- truncating format (0.749 * 255 -> be, not bf) cannot agree with itself.
PARCHMENT_CODE = "|cffbfe9d6"
function ParchmentCode() return PARCHMENT_CODE end
SECRET_TEXT = "|cff000000secret|r"
ACCEPT, DECLINE, CANCEL, OKAY = "Accept", "Decline", "Cancel", "Okay"
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("text_already_on_the_target_is_rewritten_when_it_is_hooked", """
    local FS = LoadPanelSkins()
    local row = NewButton("|cff000000Rattling the Rattlecages|r")
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(not row:GetText():find("|cff000000", 1, true), "dark code survived: " .. row:GetText())
    assert(row:GetText() == "|cffbfe9d6Rattling the Rattlecages|r", row:GetText())
""")

case("later_set_formatted_text_is_still_rewritten", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetFormattedText("|cff000000%s|r", "Coming to Terms")
    assert(row:GetText() == ParchmentCode() .. "Coming to Terms|r", row:GetText())
""")

case("a_bright_state_colour_is_left_alone", """
    local FS = LoadPanelSkins()
    local row = NewButton("|cffff2020Can't afford|r")
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(row:GetText() == "|cffff2020Can't afford|r", row:GetText())
    assert(row.writes == 0, "a bright line must not be re-written, got " .. row.writes .. " writes")
""")

case("hooking_twice_installs_one_hook_and_does_not_recurse", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetText("|cff000000Dark|r")
    assert(row:GetText() == ParchmentCode() .. "Dark|r", row:GetText())
    assert(row.writes == 2, "one write plus one rewrite expected, got " .. row.writes)
""")

case("a_secret_current_text_is_skipped_without_error", """
    local FS = LoadPanelSkins()
    local row = NewButton(SECRET_TEXT)
    FS.PanelSkins.HookInlineColorRewrite(row)
    assert(row:GetText() == SECRET_TEXT and row.writes == 0, "secret text was touched: " .. row:GetText())
""")

case("a_number_or_secret_set_text_argument_does_not_throw", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row:SetText(5)
    row:SetText(SECRET_TEXT)
    assert(row:GetText() == SECRET_TEXT and row.writes == 2, "writes: " .. row.writes)
""")

case("a_set_text_that_throws_inside_the_rewrite_does_not_stick_the_target", """
    local FS = LoadPanelSkins()
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite = true
    row:SetText("|cff000000First|r") -- the rewrite's inner SetText throws once; the hook must absorb it
    row:SetText("|cff000000Second|r")
    assert(row:GetText() == ParchmentCode() .. "Second|r", "target stopped rewriting: " .. row:GetText())
""")

case("a_rewrite_that_keeps_throwing_logs_one_degrade_line_for_the_session", """
    local FS = LoadPanelSkins()
    local loadLogs = #FS.degraded -- the module load itself may log (RequireExport); count only after it
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite, row.failForever = true, true
    row:SetText("|cff000000First|r") -- both rewrites throw; the once-per-session latch logs only the first
    row:SetText("|cff000000Second|r")
    local logged = #FS.degraded - loadLogs
    assert(logged == 1, "expected exactly one degrade log, got " .. logged)
    local call = FS.degraded[loadLogs + 1]
    assert(call[1] == "inline_rewrite", "degrade key: " .. tostring(call[1]))
    assert(type(call[2]) == "string", "degrade message is not a string")
""")


case("a_missing_degrade_logger_does_not_error_or_spend_the_log_latch", """
    local FS = LoadPanelSkins()
    local loadLogs = #FS.degraded
    local row = NewButton("")
    FS.PanelSkins.HookInlineColorRewrite(row)
    row.failOnRewrite, row.failForever = true, true
    FS.LogDegradeOnce = nil
    row:SetText("|cff000000First|r") -- throws with no logger: must be absorbed silently
    FS.LogDegradeOnce = function(key, msg) FS.degraded[#FS.degraded + 1] = { key, msg } end
    row:SetText("|cff000000Second|r") -- the logger is back: the unspent latch lets this one log
    local logged = #FS.degraded - loadLogs
    assert(logged == 1, "expected exactly one degrade log once the logger returned, got " .. logged)
""")

case("the_quest_log_pane_is_skinned_without_a_title_band_over_its_search_box", """
    local skinned = LoadPanels({ "QuestMapFrame", "WorldMapFrame" })
    assert(skinned.QuestMapFrame, "QuestMapFrame was not skinned at all")
    assert(skinned.QuestMapFrame.title == nil,
        "the quest log pane's title band sits under its search box: " .. tostring(skinned.QuestMapFrame.title))
    -- The map window that hosts it keeps its own title; only the embedded pane loses one.
    assert(skinned.WorldMapFrame and skinned.WorldMapFrame.title == "map", "WorldMapFrame lost its title")
""")



case("a_stock_text_button_anywhere_in_the_tree_is_skinned_with_its_accent_by_label", """
    local FS, calls = LoadSweep()
    local panel = Widget("Frame")
    local page = Add(panel, Widget("Frame"))
    local accept = Add(page, StockButton(ACCEPT))
    local decline = Add(Add(page, Widget("Frame")), StockButton(DECLINE))
    local reply = Add(panel, StockButton("Reply"))
    local slice = Add(panel, Widget("Button", { text = "Do it", Left = {}, Center = {}, Right = {} }))
    local n = FS.PanelSkins.SweepTextButtons(panel)
    assert(n == 4 and #calls == 4, "skinned " .. n .. " / " .. #calls)
    assert(CallFor(calls, accept).opts.accent == "cyan", "Accept: " .. tostring(CallFor(calls, accept).opts.accent))
    assert(CallFor(calls, decline).opts.accent == "pink", "Decline: " .. tostring(CallFor(calls, decline).opts.accent))
    assert(CallFor(calls, reply).opts.accent == nil, "an unlisted label keeps the default accent")
    assert(CallFor(calls, slice), "a three slice button with a label was not skinned")
""")

case("tabs_icon_buttons_dropdowns_other_widgets_and_owned_buttons_are_left_alone", """
    local FS, calls, owned = LoadSweep()
    local panel = Widget("Frame")
    Add(panel, StockButton("Quests", { LeftActive = {}, MiddleActive = {}, RightActive = {} })) -- a tab
    Add(panel, StockButton(nil))                                                                    -- icon only
    Add(panel, StockButton(""))
    Add(panel, Widget("Button", { text = "Filter" }))                                               -- a dropdown: no slices
    Add(panel, Widget("CheckButton", { text = "Option", Left = {}, Middle = {}, Right = {} }))      -- not a Button
    Add(panel, Widget("Frame", { text = "Frame", Left = {}, Middle = {}, Right = {} }))
    local mine = Add(panel, StockButton("Defaults"))
    owned[mine] = { accent = "pink" }                                                                -- a hand set accent
    local secret = Add(panel, StockButton(SECRET_TEXT))
    FS.IsSecret = function(v) return v == SECRET_TEXT end
    local n = FS.PanelSkins.SweepTextButtons(panel)
    assert(n == 0 and #calls == 0, "something was skinned: " .. n)
""")

case("scroll_box_rows_are_not_walked_but_old_scroll_frames_are", """
    local FS, calls = LoadSweep()
    local panel = Widget("Frame")
    local box = Add(panel, Widget("Frame", { ScrollTarget = {} }))
    local row = Add(box, StockButton("Row"))
    local scroll = Add(panel, Widget("ScrollFrame"))
    local inner = Add(Add(scroll, Widget("Frame")), StockButton("Inside"))
    FS.PanelSkins.SweepTextButtons(panel)
    assert(CallFor(calls, row) == nil, "a ScrollBox row was skinned")
    assert(CallFor(calls, inner), "a button inside an old scroll frame was not skinned")
""")

case("the_walk_is_bounded_in_depth_and_in_nodes_and_a_frame_that_throws_is_skipped", """
    local FS, calls = LoadSweep()
    local panel = Widget("Frame")
    local node = panel
    for _ = 1, 60 do node = Add(node, Widget("Frame")) end
    local deep = Add(node, StockButton("Deep"))
    for _ = 1, 3000 do Add(panel, Widget("Frame")) end
    Add(panel, Widget("Frame", { GetChildren = function() error("no children for you") end }))
    local late = Add(panel, StockButton("After the cap"))
    FS.PanelSkins.SweepTextButtons(panel)
    assert(CallFor(calls, deep) == nil, "the walk went 60 levels deep")
    assert(CallFor(calls, late) == nil, "the walk ran past its node cap")
""")

case("sweeping_twice_skins_a_button_once_per_pass_and_never_overwrites_the_accent_of_an_owned_one", """
    local FS, calls, owned = LoadSweep()
    local panel = Widget("Frame")
    local b = Add(panel, StockButton(ACCEPT))
    FS.PanelSkins.SweepTextButtons(panel)
    owned[b] = { accent = "cyan" }                      -- ButtonSkins now owns it
    FS.PanelSkins.SweepTextButtons(panel)
    assert(#calls == 1, "a skinned button was handed to the skin again: " .. #calls)
""")

case("sweep_on_show_sweeps_now_hooks_the_panel_once_and_sweeps_again_when_it_is_shown", """
    local FS, calls = LoadSweep()
    local panel = Widget("Frame")
    Add(panel, StockButton(ACCEPT))
    FS.PanelSkins.SweepOnShow(panel)
    FS.PanelSkins.SweepOnShow(panel)
    assert(#calls == 1, "swept now: " .. #calls)
    assert(#(panel.hooks.OnShow or {}) == 1, "OnShow hooks: " .. #(panel.hooks.OnShow or {}))
    local late = Add(panel, StockButton(DECLINE))       -- built after the first sweep
    ShowAgain(panel)
    assert(CallFor(calls, late), "a button made later was not swept when the panel was shown")
""")

case("a_page_that_was_hidden_at_the_first_sweep_is_swept_when_it_is_shown", """
    local FS, calls = LoadSweep()
    local panel = Widget("Frame")
    local page = Add(panel, Widget("Frame", { shown = false }))
    local inside = Add(page, StockButton(CANCEL))
    local protectedPage = Add(panel, Widget("Frame", { shown = false, protected = true }))
    FS.PanelSkins.SweepOnShow(panel)
    assert(#(page.hooks.OnShow or {}) == 1, "the hidden page was not hooked")
    assert(#(protectedPage.hooks.OnShow or {}) == 0, "a protected page was hooked")
    local later = Add(page, StockButton(OKAY))
    page.shown = true
    ShowAgain(page)
    assert(CallFor(calls, later), "the page's new button was not swept on show")
    FS.PanelSkins.SweepOnShow(panel)
    assert(#(page.hooks.OnShow or {}) == 1, "the page got a second hook")
""")

case("a_missing_text_button_skin_or_a_frame_with_no_children_is_a_quiet_no_op", """
    local FS = LoadPanelSkins()
    FS.ButtonSkins = nil
    assert(FS.PanelSkins.SweepTextButtons(Widget("Frame")) == 0)
    FS.ButtonSkins = { Parts = function() end, SkinTextButton = function() error("not reached") end }
    assert(FS.PanelSkins.SweepTextButtons({}) == 0, "a bare table")
    assert(FS.PanelSkins.SweepTextButtons(nil) == 0)
    FS.PanelSkins.SweepOnShow(nil)
    FS.PanelSkins.SweepOnShow({})
""")

case("every_skinned_panel_is_swept_when_panels_lua_skins_it", """
    local swept = {}
    local FS = LoadPanelSkins()
    local noop = function() end
    THEME.SkinPanel = noop
    THEME.StyleMoney, THEME.ApplyMono, THEME.SkinButton, THEME.LightenParchmentFonts = noop, noop, noop, noop
    THEME.COLOR_BG, THEME.COLOR_BORDER, THEME.COLOR_POWER = { 0, 0, 0 }, { 1, 1, 1 }, { 1, 1, 1 }
    THEME.COLOR_TEXT_PARCHMENT = { 0.749, 0.914, 0.839 }
    FS.PanelSkins.SweepOnShow = function(frame) swept[frame.fsName] = (swept[frame.fsName] or 0) + 1 end
    _G.MailFrame = { fsName = "MailFrame" }
    _G.QuestFrame = { fsName = "QuestFrame" }
    assert(loadstring(PANELS_SRC, "@Panels.lua"))("forever-stuwave", FS)
    assert(swept.MailFrame == 1 and swept.QuestFrame == 1, "swept: " .. tostring(swept.MailFrame) .. " " .. tostring(swept.QuestFrame))
""")

case("a_scroll_bar_beside_its_scrollbox_anywhere_in_the_tree_is_skinned_once", """
    local FS, calls, owned, bars = LoadSweep()
    local panel = Widget("Frame")
    local topBar = Add(panel, Bar())
    local box = Add(panel, Widget("Frame", { ScrollTarget = {} }))
    local page = Add(panel, Widget("Frame"))
    local inner = Add(page, Widget("Frame"))
    local deepBar = Add(inner, Bar())
    Add(panel, Widget("Frame"))                         -- not a bar
    local n = FS.PanelSkins.SweepScrollBars(panel)
    assert(n == 2 and #bars == 2, "skinned " .. n .. " / " .. #bars)
    assert(bars[1] == topBar and bars[2] == deepBar, "the wrong bars were skinned")
""")

case("a_scroll_bar_is_not_walked_into_and_a_scrollbox_hides_what_is_inside_it", """
    local FS, calls, owned, bars = LoadSweep()
    local panel = Widget("Frame")
    local bar = Add(panel, Bar())
    local insideBar = Add(bar, Bar())                   -- only seen if the walk went into the bar
    local box = Add(panel, Widget("Frame", { ScrollTarget = {} }))
    local insideBox = Add(box, Bar())                   -- only seen if the walk went into the ScrollBox
    FS.PanelSkins.SweepScrollBars(panel)
    assert(#bars == 1 and bars[1] == bar, "bars skinned: " .. #bars)
""")

case("a_bar_that_is_already_skinned_is_not_handed_to_the_skin_again", """
    local FS, calls, owned, bars, barOwned = LoadSweep()
    local panel = Widget("Frame")
    local bar = Add(panel, Bar())
    assert(FS.PanelSkins.SweepScrollBars(panel) == 1)
    assert(FS.PanelSkins.SweepScrollBars(panel) == 0 and #bars == 1, "skinned again: " .. #bars)
""")

case("the_scroll_bar_sweep_walk_is_bounded_and_skips_a_frame_that_throws", """
    local FS, calls, owned, bars = LoadSweep()
    local panel = Widget("Frame")
    local node = panel
    for _ = 1, 60 do node = Add(node, Widget("Frame")) end
    local deep = Add(node, Bar())
    Add(panel, Widget("Frame", { GetChildren = function() error("no children for you") end }))
    for _ = 1, 3000 do Add(panel, Widget("Frame")) end
    local late = Add(panel, Bar())
    FS.PanelSkins.SweepScrollBars(panel)
    assert(#bars == 0, "the walk went too deep or past its cap: " .. #bars)
""")

case("sweep_on_show_skins_a_bar_built_later_when_the_panel_or_a_hidden_page_is_shown", """
    local FS, calls, owned, bars = LoadSweep()
    local panel = Widget("Frame")
    local early = Add(panel, Bar())
    local page = Add(panel, Widget("Frame", { shown = false }))
    FS.PanelSkins.SweepOnShow(panel)
    assert(#bars == 1 and bars[1] == early, "swept now: " .. #bars)
    local late = Add(panel, Bar())
    ShowAgain(panel)
    assert(#bars == 2 and bars[2] == late, "a bar made later was not skinned when the panel was shown")
    local pageBar = Add(page, Bar())
    page.shown = true
    ShowAgain(page)
    assert(#bars == 3 and bars[3] == pageBar, "a hidden page's bar was not skinned when it was shown")
""")

case("a_missing_scroll_bar_skin_or_nothing_to_sweep_is_a_quiet_no_op_and_text_buttons_still_sweep", """
    local FS, calls, owned, bars = LoadSweep()
    local panel = Widget("Frame")
    local accept = Add(panel, StockButton(ACCEPT))
    Add(panel, Bar())
    FS.ScrollBarSkins = nil
    assert(FS.PanelSkins.SweepScrollBars(panel) == 0)
    FS.PanelSkins.SweepOnShow(panel)
    assert(CallFor(calls, accept), "the text buttons were not swept without a scroll bar skin")
    FS.ScrollBarSkins = { IsScrollBar = function() return true end, Parts = function() end, Skin = function() error("not reached") end }
    assert(FS.PanelSkins.SweepScrollBars(nil) == 0 and FS.PanelSkins.SweepScrollBars({}) == 0, "non-frames")
    assert(FS.PanelSkins.SweepScrollBars(Widget("Frame")) == 0, "no children")
""")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.globals().PANELSKINS_SRC = PANELSKINS_SRC
    rt.globals().PANELS_SRC = PANELS_SRC
    rt.globals().THEME_DARK_TEXT_SRC = theme_dark_text_lua()
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    total = len(CASES)
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{total - failures}/{total} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
