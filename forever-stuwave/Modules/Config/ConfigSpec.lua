-- Forever STUwave: Config window constants
-- Every size of the /fsconfig window by its prototype name (mockups/config-window-2026-11-25.html, SPEC const), the
-- values derived from the window size by the same formulas, and the colour map. Nothing else in Modules/Config types
-- a size: pages and builders read FS.ConfigWindow.Spec. Harness: tools/configlayout-harness.py.

local _, FS = ...

FS.ConfigWindow = FS.ConfigWindow or {}
local CW = FS.ConfigWindow
CW.I = CW.I or {}                -- internals shared by the Config files (not for other modules)

local Theme = FS.Theme

local S = {}
CW.Spec = S

-- Window
S.WIN_W = 960   -- window width
S.WIN_H = 640   -- window height
S.STRIP_H = 24   -- stuwave://config title strip
S.HEAD_H = 64   -- brand, version, breadcrumb band
S.FOOT_H = 40   -- footer band (old: WELL_BOTTOM)
S.PAD = 16   -- window edge to nav, well and footer contents (old: WIN_PAD)
S.X_W = 28   -- close button width
S.X_H = 16   -- close button height
S.BRAND_SIZE = 24   -- brand font size, line height 24
S.SMALL = 10   -- small text: state, counts, badges (line height 12)
S.TEXT = 12   -- body text, labels, buttons (line height 16)

-- Nav
S.NAV_W = 160   -- nav column width
S.NAV_GAP = 16   -- nav to well (old: WELL_GAP)
S.SEARCH_H = 28   -- search box height
S.SEARCH_PROMPT_W = 24   -- the > prompt cell
S.NAVLAB_GAP = 12   -- search to the first group label
S.NAVLAB_H = 16   -- group label (// FRAMES)
S.NAVGRP_GAP = 8   -- space above a group label
S.NAV_ITEM_H = 24   -- nav item height
S.NAV_ITEM_GAP = 4   -- group label to its first item
S.PWR = 16   -- power button hit box (glyph 12)
S.PWR_R = 4   -- power button to nav item right edge
S.NAV_SEL_W = 2   -- selected bar width
S.COUNT_H = 12   -- changed count chip height

-- Well and tabs
S.TAB_STRIP_H = 32   -- sub tab strip at the top of the well
S.TAB_H = 24   -- one tab
S.TAB_PAD_X = 12   -- tab text inset
S.TAB_GAP = 4   -- between tabs
S.TAB_LINE_H = 2   -- active underline
S.CONTENT_L = 16   -- well left edge to rows
S.CONTENT_R = 24   -- rows to well right edge (holds the scrollbar)
S.CONTENT_T = 8   -- tab strip to first row
S.CONTENT_B = 16   -- last row to well bottom
S.BAR_W = 4   -- scrollbar width
S.BAR_INSET = 8   -- scrollbar to well right edge

-- Rows
S.ROW_H = 32   -- every settings row
S.SEC_H = 24   -- section header row
S.SEC_GAP = 8   -- space above a section (old: GROUP_GAP)
S.SUB_INSET = 16   -- child row label inset
S.HALF_GAP = 28   -- gap between two columns
S.DOT = 4   -- changed dot size
S.DOT_X = -12   -- changed dot x from the label column
S.CTL_GAP = 8   -- between parts of one control (reset, state, switch)
S.Q = 12   -- ? icon size
S.Q_GAP = 8   -- label to ? icon
S.NOTE_H = 28   -- class only note band

-- Controls
S.SW_W = 44   -- switch width
S.SW_H = 20   -- switch height
S.KNOB_W = 16   -- switch knob
S.KNOB_H = 12   -- switch knob
S.KNOB_INSET = 4   -- knob to switch edge
S.STATE_W = 24   -- ON / OFF word, right aligned
S.SLIDER_W = 160   -- slider track
S.SLIDER_H = 20   -- slider hit height
S.THUMB_W = 12   -- thumb
S.THUMB_H = 20   -- thumb (fills the hit height)
S.VALUE_W = 60   -- typed value box (old: READOUT_W)
S.VALUE_H = 24   -- typed value box
S.SEG_H = 24   -- segmented button height
S.SEG_PAD_X = 8   -- segmented text inset
S.SEG_GAP = 4   -- between segments
S.RESET = 24   -- reset button on every changed row, 45% until the row is hovered
S.BTN_H = 24   -- footer and page buttons
S.BTN_PAD_X = 12   -- button text inset
S.TEXT_SNAP = 4   -- a box sized by its text rounds its width UP to the next multiple of this (tabs, segments, buttons, chips)

-- Popups
S.RES_W = 392   -- search results width
S.RES_HEAD_H = 24   -- results header
S.RES_ROW_H = 36   -- one result, two lines
S.RES_FOOT_H = 24   -- keys hint
S.RES_MAX = 8   -- results shown
S.MENU_W = 184   -- edit mode right click menu
S.DLG_W = 380   -- confirm dialog
S.DLG_H = 152   -- confirm dialog
S.SHARE_W = 468   -- export / import dialog
S.SHARE_H = 256   -- export / import dialog
S.SHARE_BOX_H = 96   -- profile string box, 5 lines
S.SHARE_IN_W = 220   -- save as name box
S.MENU_ROW_H = 24   -- menu row (old: MENU_ITEM_H)
S.TIP_W = 272   -- tooltip max width
S.TIP_PAD = 8   -- tooltip inset
S.FLASH_CORNER = 12   -- hover flash corner bracket
S.FLASH_OUT = 4   -- hover flash outline outset

-- The window may be dragged between these sizes (bottom right grip); WIN_W / WIN_H above are the default.
S.WIN_MIN_W, S.WIN_MIN_H = 780, 560
S.WIN_MAX_W, S.WIN_MAX_H = 1600, 1000

-- Everything that follows the window size, by the same formulas as the prototype's applySize().
function S.Derive(w, h)
    local D = {}
    D.WIN_W, D.WIN_H = w, h
    D.BODY_T = S.STRIP_H + S.HEAD_H
    D.BODY_H = h - S.STRIP_H - S.HEAD_H - S.FOOT_H
    D.WELL_X = S.PAD + S.NAV_W + S.NAV_GAP
    D.WELL_W = w - D.WELL_X - S.PAD
    D.CONTENT_W = D.WELL_W - S.CONTENT_L - S.CONTENT_R
    D.HALF_W = (D.CONTENT_W - S.HALF_GAP) / 2
    D.SCROLL_T = D.BODY_T + S.TAB_STRIP_H
    D.SCROLL_H = D.BODY_H - S.TAB_STRIP_H
    D.NAVLAB_Y = D.BODY_T + S.SEARCH_H + S.NAVLAB_GAP
    D.NAV_ITEM_Y = D.NAVLAB_Y + S.NAVLAB_H + S.NAV_ITEM_GAP
    D.NAVFOOT_Y = D.BODY_T + D.BODY_H - S.PAD - 12
    D.NAVSCROLL_H = D.NAVFOOT_Y - 8 - D.NAVLAB_Y
    D.FOOT_Y = h - S.FOOT_H
    D.BTN_Y = D.FOOT_Y + (S.FOOT_H - S.BTN_H) / 2
    D.BRAND_Y = S.STRIP_H + 12
    D.VER_Y = D.BRAND_Y + S.BRAND_SIZE + 4
    return D
end

-- A box sized by its text rounds its width UP to the next multiple of TEXT_SNAP.
function S.Snap(width)
    local snap = S.TEXT_SNAP
    return math.ceil(width / snap) * snap
end

CW.D = S.Derive(S.WIN_W, S.WIN_H)   -- the live derived values; ConfigWindow.lua re-derives them on a resize

-- The colour map (what the old local C table held, plus the prototype's dim and amber).
CW.C = {
    text = { 0.886, 0.910, 0.941, 1 },
    muted = Theme.COLOR_MUTED,
    cyan = Theme.COLOR_POWER,
    violet = Theme.COLOR_BORDER,
    pink = Theme.COLOR_HEALTH,
    line = Theme.COLOR_BAR_BORDER,
    track = Theme.COLOR_BAR_TRACK,
    green = Theme.COLOR_CARET_HEALTH,
    ink = { 0.090, 0.047, 0.165, 1 },
    knob = { 0.357, 0.290, 0.541, 1 },
    amber = { 1, 0.714, 0.282, 1 },
}
