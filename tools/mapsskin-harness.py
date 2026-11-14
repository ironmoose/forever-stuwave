#!/usr/bin/env python3
"""Runs the real Modules/Skins/Maps.lua headless against a mock world map and map quest log (tools/charskin_support.py).

Pinned: the border frame's stock art (nine slice, portrait, rock background, title) is held, the canvas wears a cyan ring, the
tutorial and maximize keys are cut keys that keep their clicks, the breadcrumb is a route (a node per button, a line to the
next, the current stop cyan and larger, the stock arrows held) that follows every rebuild of the bar, the overlay keys (the
tracking filter, the pin, the side panel toggle) are plates over their own icons, the quest log side tabs are keys with the
selected one pink, the quest rows are rail nodes (tracked fills cyan, ready to turn in is amber, the super tracked quest is
caught in lock-on brackets, the stock difficulty colour is never pinned), the headers carry a chevron that follows the
collapsed state, the campaign banner and the zone story are plates, and no script or attribute is written on a Blizzard widget.
Run `python3 tools/mapsskin-harness.py [--png debug/maps]`. The mock is NOT the real client, but its sizes, shown states and
anchors follow the live readout of 2026-11-14 (debug/tree-WorldMapFrame-2026-11-14.txt and tree-QuestMapFrame): a 1035 x 534
window, a 697 x 465 canvas, the nav bar with a dropdown arrow on each stop, the filter button with its ResetButton, the pin and
Krowi buttons, the side panel toggle, the player read-out, the quest count pill and the settings key. A scene is skinned while the
pixel scale is still the 1440 / 768 of a client that has not applied the UI scale yet, then settled to the live 1.2 (Settle), which
is how the live keys came out displaced. Stock art that is still visible is drawn in its stock colour (t.stock).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
SUPER = 0
COMPLETE = {}
C_SuperTrack = { GetSuperTrackedQuestID = function() return SUPER end }
C_QuestLog = { IsComplete = function(id) return COMPLETE[id] == true end }

local function pool(parent, make)
    local p = { free = {}, active = {}, all = {} }
    function p:Acquire()
        local f = table.remove(self.free) or make(parent)
        f:Show()
        self.active[#self.active + 1] = f
        self.all[#self.all + 1] = f
        return f
    end
    function p:ReleaseAll()
        for _, f in ipairs(self.active) do f:Hide(); self.free[#self.free + 1] = f end
        self.active = {}
    end
    function p:EnumerateActive()
        local i = 0
        return function() i = i + 1; return self.active[i] end
    end
    return p
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^WorldMap") or k:find("^QuestMap") or k:find("^QuestScroll") or k:find("^NavBar")
            or k:find("^QuestLog") or k:find("^QuestInfo")) then _G[k] = nil end
    end

    -- the map window, as Blizzard_WorldMap.xml builds it
    local win = blz("Frame", "WorldMapFrame", UIParent, 1035, 534)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -60 }
    win.shown = false
    tex(win, "WorldMapFramePortraitStock", "ARTWORK")
    local border = blz("Frame", nil, win, 1035, 534, "TOPLEFT", 0, 0)
    border.points = { { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = win, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    win.BorderFrame = border
    border.NineSlice = blz("Frame", nil, border, 1035, 534)
    atex(border.NineSlice, nil, "BORDER", "UI-Frame-TopLeftCorner", 32, 32)
    border.PortraitContainer = blz("Frame", nil, border, 1, 1)
    border.PortraitContainer.portrait = tex(border.PortraitContainer, "WorldMapFramePortrait", "OVERLAY")
    border.TitleContainer = blz("Frame", nil, border, 953, 20, "TOPLEFT", 58, -1)
    border.TitleContainer.TitleText = fstring(border.TitleContainer, nil, "Cursor: 146.2 X, -16.5 Y  |  Player: 46.1 X , 67.4 Y", 12)
    border.Bg = tex(border, nil, "BACKGROUND")
    border.TopTileStreaks = tex(border, nil, "BORDER")
    border.InsetBorderTop = tex(border, nil, "BACKGROUND")
    border.Underlay = tex(border, nil, "ARTWORK"); border.Underlay.shown = false
    local close = blz("Button", "WorldMapFrameCloseButton", border, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    border.CloseButton = close
    local tut = blz("Button", nil, border, 64, 64, "TOPLEFT", 34, 10)
    tut.shown = false
    tut.I = tex(tut, nil, "ARTWORK"); tut.Ring = tex(tut, nil, "OVERLAY"); tut.BigIPulse = tex(tut, nil, "OVERLAY")
    tut.RingPulse = tex(tut, nil, "OVERLAY")
    tut.scripts.OnClick = function() end
    tut.scripts.OnEnter = function() end
    border.Tutorial = tut
    local mm = blz("Frame", nil, border, 28, 28, "TOPRIGHT", -26, -2)
    border.MaximizeMinimizeFrame = mm
    for _, key in ipairs({ "MaximizeButton", "MinimizeButton" }) do
        local b = blz("Button", nil, mm, 28, 28, "TOPLEFT", 0, 0)
        b.points = { { point = "TOPLEFT", rel = mm, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = mm, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
        b.normalTex = atex(b, nil, "ARTWORK", "RedButton-Expand", 24, 24)
        b.pushedTex = atex(b, nil, "ARTWORK", "RedButton-Expand-Pressed", 24, 24)
        b.highlightTex = atex(b, nil, "HIGHLIGHT", "RedButton-Highlight", 24, 24)
        b.scripts.OnClick = function() end
        mm[key] = b
    end
    mm.MinimizeButton.shown = false
    win.TitleCanvasSpacerFrame = blz("Frame", nil, win, 697, 67, "TOPLEFT", 2, 0)
    local canvas = blz("Frame", nil, win, 697, 465, "TOPLEFT", 2, -67)
    win.ScrollContainer = canvas
    local parchment = tex(canvas, nil, "BACKGROUND")
    parchment.stock = { 0.62, 0.45, 0.2 }
    parchment.points = { { point = "TOPLEFT", rel = canvas, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = canvas, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }

    -- the overlay frames the map builds, in win.overlayFrames: the live 12.x set (the tracking options dropdown with its
    -- ResetButton, the pin, the side panel toggle, the read-outs). Krowi's map button is a direct child of the window, not an overlay.
    win.overlayFrames = {}
    local function overlay(f) win.overlayFrames[#win.overlayFrames + 1] = f; return f end
    local RED, GREEN, GOLD, BRONZE, GREY = { 0.92, 0.18, 0.18 }, { 0.2, 0.85, 0.25 }, { 0.95, 0.75, 0.2 }, { 0.75, 0.62, 0.35 }, { 0.5, 0.5, 0.55 }
    -- a stock texture centred on its frame, w x h, drawn in its stock colour while it is not held
    local function mark(t, color, w, h)
        t.stock = color
        t.w, t.h = w, h
        t.points[1] = { point = "CENTER", rel = t.parent, relPoint = "CENTER", x = 0, y = 0 }
        return t
    end
    -- WorldMapTrackingOptionsButton: 32 x 32 at (659, 27.5); no FilterCounter on this client; its ResetButton (23 x 23, the red
    -- filter X) hangs on its top right corner. The generic dropdown skin dresses the button itself (StandInFilter below).
    local trk = overlay(blz("Button", "WorldMapTrackingOptionsButton", win, 32, 32, "TOPLEFT", 659, -27.5))
    trk.Icon = mark(atex(trk, nil, "ARTWORK", "common-dropdown-a-button"), GREY, 27, 27)
    trk.scripts.OnEnter = function() end
    trk.scripts.OnClick = function() end
    local reset = blz("Button", nil, trk, 23, 23)
    reset.points[1] = { point = "CENTER", rel = trk, relPoint = "TOPRIGHT", x = -6, y = -6 }
    reset.Art = mark(atex(reset, nil, "ARTWORK", "auctionhouse-ui-filter-redx"), RED, 23, 23)
    reset.hl = atex(reset, nil, "HIGHLIGHT", "auctionhouse-ui-filter-redx", 23, 23)
    reset.scripts.OnClick = function() end
    reset.scripts.OnEnter = function() end
    trk.ResetButton = reset
    -- WorldMapTrackingPinButton and Krowi_WorldMapButtons2: the same 32 x 32 template (a 25 x 25 background, the icon, a 54 x 54
    -- bronze border), stacked 29 apart at the canvas' top left corner
    local function mapButton(name, y, iconColor, parent)
        local b = blz("Button", name, win, 32, 32, "TOPLEFT", 5.5, y)
        b.Background = mark(tex(b, nil, "BACKGROUND"), { 0.1, 0.1, 0.12 }, 25, 25)
        b.Icon = mark(atex(b, nil, "ARTWORK", "Waypoint-MapPin-Untracked"), iconColor, 20, 20)
        b.IconOverlay = mark(tex(b, nil, "OVERLAY"), GOLD, 20, 20); b.IconOverlay.shown = false
        b.Border = mark(tex(b, nil, "OVERLAY"), BRONZE, 54, 54)
        b.ActiveTexture = tex(b, nil, "OVERLAY"); b.ActiveTexture.shown = false
        b.scripts.OnClick = function() end
        return b
    end
    local pin = overlay(mapButton("WorldMapTrackingPinButton", -70.7, { 0.95, 0.6, 0.15 }))
    local krowi = mapButton("Krowi_WorldMapButtons2", -99.8, GOLD)
    -- the read-outs: a 100 x 18 frame at the bottom left, the cursor row hidden, the player row shown; the text starts 66 units in
    -- and its middle is 11 units above the canvas' bottom edge
    local coords = overlay(blz("Frame", nil, win, 100, 18))
    coords.points[1] = { point = "BOTTOMLEFT", rel = win, relPoint = "BOTTOMLEFT", x = 66.5, y = 4 }
    coords.CursorCoords = blz("Frame", nil, coords, 100, 15, "TOPLEFT", 0, -4)
    coords.CursorCoords.shown = false
    coords.CursorCoords.Label = fstring(coords.CursorCoords, nil, "Cursor: 99.3, 70.5", 9, { 1, 1, 1, 1 })
    coords.PlayerCoords = blz("Frame", nil, coords, 100, 15, "TOPLEFT", 0, -4)
    coords.PlayerCoords.Label = fstring(coords.PlayerCoords, nil, "Player: 46.1, 67.4", 9, { 1, 1, 1, 1 })
    -- SidePanelToggle: 32 x 32, its bottom right corner on the canvas' bottom right corner; the open key is hidden, the close key shown
    local tog = overlay(blz("Button", "SidePanelToggle", win, 32, 32))
    tog.points[1] = { point = "BOTTOMRIGHT", rel = canvas, relPoint = "BOTTOMRIGHT", x = 0, y = 0 }
    for _, key in ipairs({ "OpenButton", "CloseButton" }) do
        local b = blz("Button", nil, tog, 32, 32, "CENTER", 0, 0)
        tex(b, nil, "BACKGROUND")
        b.normalTex = mark(atex(b, nil, "ARTWORK", key == "CloseButton" and "QuestCollapse-Hide-Up" or "QuestCollapse-Show-Up"), GOLD, 32, 32)
        b.pushedTex = atex(b, nil, "ARTWORK", "QuestCollapse-Show-Down", 32, 32)
        b.pushedTex.shown = false
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        tog[key] = b
    end
    tog.OpenButton.shown = false

    -- the breadcrumb: NavigationBar.lua's buttons, with its global functions
    local bar = blz("Frame", nil, win, 583, 33, "TOPLEFT", 66, -25)
    win.NavBar = bar
    win.overlayFrames[#win.overlayFrames + 1] = bar
    tex(bar, nil, "BACKGROUND")
    tex(bar, nil, "BORDER")
    bar.overlay = blz("Frame", nil, bar, 583, 33, "TOPLEFT", 0, 0)
    tex(bar.overlay, nil, "OVERLAY")
    bar.navList = {}
    bar.freeButtons = {}
    local function navbutton(parent, home)
        local b = blz("Button", nil, parent, 80, 30, "LEFT", 0, 0)
        b.normalTex = tex(b, nil, "ARTWORK"); b.pushedTex = tex(b, nil, "ARTWORK"); b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.arrowUp = tex(b, nil, "OVERLAY"); b.arrowDown = tex(b, nil, "OVERLAY"); b.selected = tex(b, nil, "OVERLAY")
        b.arrowDown.shown, b.selected.shown = false, false
        b.text = fstring(b, nil, "", 12)
        b.text.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = home and 10 or 20, y = 0 }
        b.xoffset = home and -15 or 0
        -- the dropdown arrow: a 27 x 31 button at the right end, its Art the stock 12 x 12 green triangle; home has none
        if not home then
            b.MenuArrowButton = blz("Button", nil, b, 27, 31, "RIGHT", -2, 0)
            b.MenuArrowButton.Art = mark(tex(b.MenuArrowButton, nil, "OVERLAY"), GREEN, 12, 12)
            b.MenuArrowButton.normalTex = tex(b.MenuArrowButton, nil, "ARTWORK")
        end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.SetText = function(self, t) self.text:SetText(t) end
        return b
    end
    local home = navbutton(bar, true)
    home.Left = tex(home, nil, "OVERLAY")
    home.text:SetText("World")
    home:SetWidth(home.text:GetStringWidth() + 30)
    bar.home = home
    bar.homeButton = home
    bar.navList[1] = home
    local over = navbutton(bar)
    over.shown = false
    bar.overflow = over
    bar.overflowButton = over
    function NavBar_CheckLength(self)
        for i, b in ipairs(self.navList) do
            b:Show()
            if i > 1 then
                local prev = self.navList[i - 1]
                b.points = { { point = "LEFT", rel = prev, relPoint = "RIGHT", x = prev.xoffset or 0, y = 0 } }
            end
            if i < #self.navList then
                b.selected:Hide(); b:Enable()
            else
                b.selected:Show(); b:Disable()
            end
        end
    end
    function NavBar_AddButton(self, data)
        local b = table.remove(self.freeButtons) or navbutton(self)
        self.navList[#self.navList + 1] = b
        b:SetText(data.name)
        b:SetWidth(b.text:GetStringWidth() + 30 + 28)
        b:Show()
        NavBar_CheckLength(self)
    end
    function NavBar_Reset(self)
        for i = #self.navList, 2, -1 do
            self.navList[i]:Hide()
            self.freeButtons[#self.freeButtons + 1] = self.navList[i]
            self.navList[i] = nil
        end
        NavBar_CheckLength(self)
    end
    NavBar_AddButton(bar, { name = "Kalimdor" })
    NavBar_AddButton(bar, { name = "Mulgore" })

    -- the quest log, as QuestMapFrame.xml builds it
    local qm = blz("Frame", "QuestMapFrame", win, 330, 506, "TOPLEFT", 703, -27)
    qm.shown = false
    for _, spec in ipairs({ { "QuestsTab", 1 }, { "EventsTab", 2 }, { "MapLegendTab", 3 } }) do
        local t = blz("Frame", nil, qm, 43, 55, "TOPLEFT", 335, -(20 + (spec[2] - 1) * 60))
        t.Background = atex(t, nil, "BACKGROUND", "common-sidetab", 55, 60)
        t.Icon = tex(t, nil, "ARTWORK"); t.Icon.w, t.Icon.h = 30, 30
        t.SelectedTexture = atex(t, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        t.TabGlow = atex(t, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        t.HighlightTexture = atex(t, nil, "HIGHLIGHT", "common-sidetab-hover", 55, 60)
        t.shown = false
        t.SelectedTexture.shown = (spec[2] == 1)
        t.glowing = false
        t.SetChecked = function(self, v) self.SelectedTexture:SetShown(v) end
        t.SetTabGlowAnimationPlaying = function(self, v) self.glowing = v end
        t.IsTabGlowAnimationPlaying = function(self) return self.glowing end
        t.scripts.OnMouseUp = function() end
        t.scripts.OnEnter = function() end
        qm[spec[1]] = t
    end
    local qf = blz("Frame", nil, qm, 308, 497, "TOPLEFT", 0, 0)
    qm.QuestsFrame = qf
    local sf = blz("ScrollFrame", "QuestScrollFrame", qf, 308, 468, "TOPLEFT", 0, -30)
    qf.ScrollFrame = sf
    sf.NoSearchResultsText = fstring(sf, nil, "No quests match", 13, { 1, 1, 1, 1 }); sf.NoSearchResultsText.shown = false
    sf.EmptyText = fstring(sf, nil, "No quests", 16, { 1, 1, 1, 1 }); sf.EmptyText.shown = false
    -- the top row as live: the search box (200 wide, from 5.8), the Quests pill (100 x 20 from 204.5, so it overlaps the search box by
    -- 1.3) and the settings key (15 x 16 from 308.7, right of the 308 wide scroll frame), all 0.5 under the top
    sf.SearchBox = blz("EditBox", "QuestScrollFrameSearchBox", qf, 200, 20, "TOPLEFT", 5.8, -0.5)
    local pill = blz("Frame", "QuestLogCount", qf, 100, 20, "TOPLEFT", 204.5, -0.5)
    for _, key in ipairs({ "Left", "Right", "Middle" }) do
        pill[key] = atex(pill, nil, "BACKGROUND", "common-search-border-" .. key:lower(), key == "Middle" and 89 or 8, 20)
        pill[key].stock = BRONZE
        pill[key].points[1] = { point = key == "Right" and "TOPRIGHT" or "TOPLEFT", rel = pill, relPoint = key == "Right" and "TOPRIGHT" or "TOPLEFT", x = key == "Middle" and 8 or 0, y = 0 }
    end
    pill.Count = fstring(pill, "QuestLogQuestCount", "Quests: |cffffffff3|r|cffffffff/40|r", 9, { 1, 0.82, 0, 1 })
    pill.Count.points[1] = { point = "RIGHT", rel = pill, relPoint = "RIGHT", x = -10, y = 0 }
    pill.Count.justify = "RIGHT"
    sf.SettingsDropdown = blz("Button", nil, qf, 15, 16, "TOPLEFT", 308.7, -0.5)
    sf.SettingsDropdown.intrinsic = "DropdownButton"
    sf.SettingsDropdown.Icon = mark(atex(sf.SettingsDropdown, nil, "ARTWORK", "questlog-icon-setting"), GOLD, 15, 16)
    sf.SettingsDropdown.hl = atex(sf.SettingsDropdown, nil, "HIGHLIGHT", "questlog-icon-setting", 15, 16)
    sf.SettingsDropdown.scripts.OnMouseDown = function() end
    local contents = blz("Frame", nil, sf, 290, 600, "TOPLEFT", 0, 0)
    sf.Contents = contents
    contents.selectedCalls = 0
    contents.SelectButton = function(self, b) self.selectedCalls = self.selectedCalls + 1 end
    contents.ClearSelection = function(self) end
    contents.Separator = blz("Frame", nil, contents, 290, 8)
    atex(contents.Separator, nil, "ARTWORK", "QuestLog-frame-devider", 290, 8)
    contents.Separator.Divider = contents.Separator.regions[1]
    local story = blz("Frame", nil, contents, 290, 50, "TOPLEFT", 0, -10)
    story.Background = atex(story, nil, "BACKGROUND", "StoryHeader-BG", 290, 50)
    story.Text = fstring(story, nil, "Mulgore", 14, { 1, 1, 1, 1 })
    story.Progress = fstring(story, nil, "3 / 9", 11, { 1, 1, 1, 1 })
    story.HighlightTexture = atex(story, nil, "HIGHLIGHT", "StoryHeader-BG", 290, 50); story.HighlightTexture.shown = false
    story.Divider = atex(story, nil, "ARTWORK", "QuestLog-frame-devider", 290, 8)
    story.scripts.OnEnter = function() end
    contents.StoryHeader = story
    local bf = blz("Frame", nil, sf, 300, 400, "TOPLEFT", 0, 0)
    sf.BorderFrame = bf
    atex(bf, nil, "BORDER", "questlog-frame", 300, 400)

    local function header(parent)
        local b = blz("Button", nil, parent, 289, 22, "TOPLEFT", 0, 0)
        b.normalTex = atex(b, nil, "BACKGROUND", "common-button-list-collapseExpand", 289, 22)
        b.highlightTex = atex(b, nil, "HIGHLIGHT", "common-button-list-collapseExpand", 289, 22)
        b.text = fstring(b, nil, "", 15, { 0.5, 0.5, 0.5, 1 })
        b.ButtonText = b.text
        local cb = blz("Button", nil, b, 20, 20, "RIGHT", -6, 0)
        cb.Icon = atex(cb, nil, "ARTWORK", "common-button-list-minus", 13, 4)
        cb.collapsed = false
        cb.UpdateCollapsedState = function(self, collapsed) self.collapsed = collapsed end
        b.CollapseButton = cb
        b.CheckHighlightTitle = function(self, over) self.text:SetTextColor(1, 1, 1, 1) end
        b.SetText = function(self, t) self.text:SetText(t) end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        return b
    end
    local function title(parent)
        local b = blz("Button", nil, parent, 290, 40, "TOPLEFT", 0, 0)
        b.Checkbox = blz("Frame", nil, b, 14, 14, "TOPRIGHT", 0, -8)
        atex(b.Checkbox, nil, "ARTWORK", "questlog-icon-ticksquare", 14, 14)
        b.Checkbox.CheckMark = atex(b.Checkbox, nil, "OVERLAY", "questlog-icon-checkmark-yellow", 14, 14)
        atex(b.Checkbox, nil, "HIGHLIGHT", "questlog-icon-ticksquare", 14, 14)
        b.TagTexture = tex(b, nil, "ARTWORK"); b.TagTexture.shown = false
        b.StorylineTexture = atex(b, nil, "ARTWORK", "questlog-storylineicon", 20, 20); b.StorylineTexture.shown = false
        b.Text = fstring(b, nil, "", 12, { 0.75, 0.61, 0 })
        b.Text.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 31, y = -8 }
        b.TaskIcon = tex(b, nil, "ARTWORK"); b.TaskIcon.shown = false
        b.HighlightTexture = atex(b, nil, "BORDER", "questlog-quest-glow-yellow", 290, 24); b.HighlightTexture.shown = false
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function(self) self.HighlightTexture:Show() end
        b.scripts.OnLeave = function(self) self.HighlightTexture:Hide() end
        return b
    end
    local function objective(parent)
        local o = blz("Frame", nil, parent, 220, 16, "TOPLEFT", 0, 0)
        o.Dash = fstring(o, nil, "-", 11, { 0.8, 0.8, 0.8, 1 })
        o.Text = fstring(o, nil, "", 11, { 0.8, 0.8, 0.8, 1 })
        return o
    end
    local function campaign(parent)
        local c = blz("Frame", nil, parent, 289, 60, "TOPLEFT", 0, 0)
        c.Background = atex(c, nil, "BACKGROUND", "Campaign_Horde", 289, 60)
        c.Text = fstring(c, nil, "", 15, { 1, 1, 1, 1 })
        c.Progress = fstring(c, nil, "", 11, { 1, 1, 1, 1 })
        c.HighlightTexture = atex(c, nil, "HIGHLIGHT", "Campaign_Horde", 289, 60); c.HighlightTexture.shown = false
        c.TopFiligree = atex(c, nil, "ARTWORK", "QuestLog-frame-devider", 289, 8)
        c.SelectedHighlight = atex(c, nil, "BACKGROUND", "questlog-header-glow-yellow", 289, 60)
        c.CollapseButton = blz("Button", nil, c, 20, 20, "RIGHT", -6, 0)
        c.CollapseButton.Icon = atex(c.CollapseButton, nil, "ARTWORK", "common-button-list-minus", 13, 4)
        c.CollapseButton.UpdateCollapsedState = function(self, collapsed) self.collapsed = collapsed end
        c.LoreButton = blz("Button", nil, c, 24, 24, "TOPRIGHT", -30, -6)
        c.scripts.OnEnter = function() end
        return c
    end
    sf.titleFramePool = pool(contents, title)
    sf.objectiveFramePool = pool(contents, objective)
    sf.headerFramePool = pool(contents, header)
    sf.campaignHeaderFramePool = pool(contents, campaign)
    sf.campaignHeaderMinimalFramePool = pool(contents, header)
    sf.covenantCallingsHeaderFramePool = pool(contents, header)

    QUESTS = {
        { id = 11, name = "Rites of the Earthmother", tracked = true, color = { 1, 0.82, 0 }, objectives = { "Gather herbs 2/5" } },
        { id = 12, name = "The Hunt Begins", tracked = false, color = { 0.25, 0.75, 0.25 }, objectives = {} },
        { id = 13, name = "Winterhoof Water Well", tracked = true, color = { 0.5, 0.5, 0.5 }, objectives = { "Done" }, complete = true },
    }
    function QuestLogQuests_Update()
        for _, p in ipairs({ sf.titleFramePool, sf.objectiveFramePool, sf.headerFramePool, sf.campaignHeaderFramePool,
            sf.campaignHeaderMinimalFramePool, sf.covenantCallingsHeaderFramePool }) do p:ReleaseAll() end
        -- a VerticalLayoutFrame, as far as the pictures need: rows stack down the contents, 6 apart
        local y = 8
        local function seat(f, h, x)
            f.points = { { point = "TOPLEFT", rel = contents, relPoint = "TOPLEFT", x = x or 0, y = -y } }
            f.h = h
            y = y + h + 6
        end
        local camp = sf.campaignHeaderFramePool:Acquire()
        camp.Text:SetText("Earthmother's Path"); camp.Progress:SetText("3 / 9")
        camp.Text.points[1] = { point = "TOPLEFT", rel = camp, relPoint = "TOPLEFT", x = 36, y = -12 }
        camp.Progress.points[1] = { point = "TOPRIGHT", rel = camp, relPoint = "TOPRIGHT", x = -40, y = -14 }
        camp.CollapseButton:UpdateCollapsedState(false)
        seat(camp, 44)
        seat(story, 40)
        local h = sf.headerFramePool:Acquire()
        h:SetText("Mulgore")
        h.CollapseButton:UpdateCollapsedState(false)
        seat(h, 22)
        for _, q in ipairs(QUESTS) do
            local b = sf.titleFramePool:Acquire()
            b.questID = q.id
            b.Text:SetText(q.name)
            b.Text:SetTextColor(q.color[1], q.color[2], q.color[3])
            b.Checkbox.CheckMark:SetShown(q.tracked)
            COMPLETE[q.id] = q.complete == true
            local top = y
            seat(b, 8 + 16 + 16 * #q.objectives + 6)
            for i, line in ipairs(q.objectives) do
                local o = sf.objectiveFramePool:Acquire()
                o.questID = q.id
                o.Text:SetText(line)
                o.Text:SetTextColor(0.8, 0.8, 0.8)
                o.points = { { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 31, y = -(8 + 16 + 16 * (i - 1)) } }
                o.Text.points[1] = { point = "LEFT", rel = o, relPoint = "LEFT", x = 12, y = 0 }
            end
        end
        local h2 = sf.headerFramePool:Acquire()
        h2:SetText("Thunder Bluff")
        h2.CollapseButton:UpdateCollapsedState(true)
        seat(h2, 22)
        story:Show()
        contents:SelectButton()
    end
    function QuestMapFrame_UpdateAll() QuestLogQuests_Update() end
    win.QuestLog = qm
    QuestLogQuests_Update()

    local sess = blz("Frame", nil, qm, 300, 40, "BOTTOMLEFT", 6, 6)
    qm.QuestSessionManagement = sess
    sess.BG = atex(sess, nil, "BACKGROUND", "QuestSharing-QuestLog-Background", 300, 40)
    sess.CommandText = fstring(sess, nil, "Start", 12)
    sess.HelpText = fstring(sess, nil, "Party sync", 10)
    local details = blz("Frame", nil, qm, 320, 450, "TOPLEFT", 6, -30)
    details.shown = false
    qm.DetailsFrame = details
    details.BackFrame = blz("Frame", nil, details, 320, 30, "TOPLEFT", 0, 0)
    atex(details.BackFrame, nil, "ARTWORK", "questlog-reward-top-frame", 320, 30)
    details.BackFrame.BackButton = blz("Button", nil, details.BackFrame, 80, 21, "LEFT", 4, 0)
    details.BackFrame.BackButton.scripts.OnClick = function() end
    details.DestinationMapButton = blz("Button", nil, details, 32, 32, "TOPRIGHT", -10, -40)
    details.DestinationMapButton.Icon = tex(details.DestinationMapButton, nil, "ARTWORK")
    details.DestinationMapButton.HighlightIcon = tex(details.DestinationMapButton, nil, "OVERLAY")
    details.DestinationMapButton.scripts.OnClick = function() end
    if BuildExtras then BuildExtras() end
end

-- The skin is built while the client still reports 1440 / 768 pixels per unit (PPU 1.875) and the UI scale is applied after, so a
-- pixel offset worked out at build time from a stock size is stale for good. Settle is that later moment: the live 1.2, and the
-- kit re-seats everything it recorded in pixels.
function Settle()
    PPU = 1.2
    FS.ControlKit.Reseat()
    -- the quest log lays its rows out again once it has a size, which paints every row and header against the settled scale
    if QuestLogQuests_Update then QuestLogQuests_Update() end
    FlushTimers()
end

-- The generic control skins (not loaded here) dress the filter button and the search box on the live client: a cut key with a
-- chevron, a plate. Drawn the same way, after the settle, so a scene shows what the live window shows next to the map skin.
-- left, top, right, bottom in physical pixels of a list of regions, and its middle
function BoxOf(list)
    local l, t, r, b = math.huge, math.huge, -math.huge, -math.huge
    for _, o in ipairs(list) do
        local a, c, d, e = Px(o, UIParent)
        l, t, r, b = math.min(l, a), math.min(t, c), math.max(r, d), math.max(b, e)
    end
    return l, t, r, b, (l + r) / 2, (t + b) / 2
end

function StandIn()
    local MK = FS.MapsSkin.kit
    MK.Key(WorldMapTrackingOptionsButton, { size = 32, glyph = MK.ChevronGlyph("down") })
    local search = QuestScrollFrameSearchBox
    local box = FS.CharacterSkin.Box(search, "BORDER")
    FS.CharacterSkin.PaintBox(box, { 0.059, 0.031, 0.125 }, 1, { 0.294, 0.165, 0.525 }, 1, 1)
end
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Maps": "Modules/Skins/Maps.lua"}, BLIZZARD)
case = H.case

# every case and scene starts at the unsettled scale; OPEN shows the windows, settles the scale and dresses what the live client's
# generic skins dress
_load = H.load_line
H.load_line = lambda: "PPU = 1.875\n" + _load()
OPEN = "Fire('PLAYER_ENTERING_WORLD'); WorldMapFrame:Show(); QuestMapFrame:Show(); FlushTimers(); Settle(); StandIn()"


case("world map: the border frame's stock art is held, the title hidden, the canvas wears a cyan ring", f"""
    {OPEN}
    local win = WorldMapFrame
    local b = win.BorderFrame
    assert(win.fsMapsSkin, 'not built')
    assert(b.NineSlice.alpha == 0 and b.PortraitContainer.alpha == 0, 'frame art kept')
    assert(b.Bg.alpha == 0 and b.TopTileStreaks.alpha == 0 and b.InsetBorderTop.alpha == 0, 'rock or streaks kept')
    assert(b.TitleContainer.TitleText.alpha == 0, 'stock title kept')
    b.NineSlice:SetAlpha(1)
    assert(b.NineSlice.alpha == 0, 'hold did not survive a re-show')
    local ring = FS.MapsSkin.state.ring
    assert(ring and ring.edges[1].color[2] > 0.8 and ring.edges[1].color[1] < 0.3, 'ring is not cyan')
    assert(b.CloseButton.shown ~= false, 'close lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("world map: the panel title starts right of the tutorial key and returns to the band inset when it hides", f"""
    FS = Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Character', 'Maps' }})
    FS.Theme.SkinPanel(WorldMapFrame, {{ title = 'map' }})
    {OPEN}
    local label = WorldMapFrame.fsPanelTitle
    assert(label, 'no panel title')
    assert(label.points[1].x == 10, 'the tutorial is hidden: the title keeps the band inset, x=' .. tostring(label.points[1].x))
    WorldMapFrame.BorderFrame.Tutorial:Show()
    local p = label.points[1]
    assert(p.rel == WorldMapFrame and p.x >= 107, 'title overlaps the tutorial key: x=' .. tostring(p.x))
    WorldMapFrame.BorderFrame.Tutorial:Hide()
    assert(label.points[1].x == 10, 'title did not come back when the tutorial hid')
    WorldMapFrame.BorderFrame.Tutorial:Show()
    assert(label.points[1].x >= 107, 'title did not move out again')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("world map: tutorial and maximize keys are cut keys that keep their art off and their clicks on", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local b = WorldMapFrame.BorderFrame
    for _, btn in ipairs({{ b.Tutorial, b.MaximizeMinimizeFrame.MaximizeButton, b.MaximizeMinimizeFrame.MinimizeButton }}) do
        local k = S.keys[btn]
        assert(k and k.plate and k.plate.ring.alpha ~= 0 and k.plate.fill.alpha ~= 0, 'no key')
        assert(btn.scripts.OnClick, 'click lost')
    end
    assert(b.Tutorial.Ring.alpha == 0 and b.Tutorial.BigIPulse.alpha == 0, 'tutorial ring kept')
    assert(b.MaximizeMinimizeFrame.MinimizeButton.normalTex.alpha == 0, 'stock arrows kept')
    assert(#S.keys[b.MaximizeMinimizeFrame.MinimizeButton].glyph >= 1, 'no glyph')
    for _, btn in ipairs({{ b.Tutorial, b.MaximizeMinimizeFrame.MaximizeButton, b.MaximizeMinimizeFrame.MinimizeButton }}) do
        local bx, by = CenterOf(btn, UIParent)
        local px, py = CenterOf(S.keys[btn].plate.ring, UIParent)
        assert(math.abs(bx - px) <= 0.6 and math.abs(by - py) <= 0.6, string.format('plate off the middle of its button by %.1f, %.1f px', px - bx, py - by))
        local _, _, _, _, gx, gy = BoxOf(S.keys[btn].glyph)
        if #S.keys[btn].glyph > 0 then
            -- the minimise bar sits low in its cell by design (the glyph of a window shrinking to the baseline), so only x is held there
            local lowBar = btn == b.MaximizeMinimizeFrame.MinimizeButton
            assert(math.abs(bx - gx) <= 0.6 and (lowBar or math.abs(by - gy) <= 0.6), string.format('glyph off the middle of its button by %.1f, %.1f px', gx - bx, gy - by))
        end
    end
    local e = S.keys[b.Tutorial].plate.ring
    b.Tutorial:RunScript('OnEnter')
    assert(e.vertex[2] > 0.8 and e.vertex[1] < 0.3, 'hover edge not cyan')
    b.Tutorial:RunScript('OnLeave')
    assert(e.vertex[1] > 0.6 and e.vertex[1] < 0.7 and e.vertex[3] > 0.9, 'idle edge not violet')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nav bar: every button is a route node with a line to the next, the current one cyan and larger, arrows held", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local bar = WorldMapFrame.NavBar
    assert(#bar.navList == 3, 'buttons')
    for i, b in ipairs(bar.navList) do
        local n = S.nav[b]
        assert(n and n.node, 'button ' .. i .. ' not a route node')
        assert(b.arrowUp.alpha == 0 and b.selected.alpha == 0 and b.normalTex.alpha == 0, 'stock arrow art kept on ' .. i)
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'script lost')
        assert(b.text.fontPath ~= 'stock.ttf', 'text not mono')
        if i < #bar.navList then
            assert(n.line.shown ~= false and #n.line.points == 2, 'no line to the next on ' .. i)
            assert(n.line.points[2].rel == bar.navList[i + 1].text, 'line does not run to the next text')
        else
            assert(n.line.shown == false, 'the last stop has a line')
        end
    end
    local cur, prev = S.nav[bar.navList[3]], S.nav[bar.navList[2]]
    assert(cur.node.w > prev.node.w, 'current node not larger')
    assert(cur.node.color[2] > 0.8 and cur.node.color[1] < 0.3, 'current node not cyan')
    assert(bar.navList[3].text.textColor[2] > 0.8 and bar.navList[3].text.textColor[1] < 0.3, 'current text not cyan')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nav bar: a button added later and a reset both re-run the route, the freed button's line is gone", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local bar = WorldMapFrame.NavBar
    NavBar_AddButton(bar, {{ name = 'Bloodhoof' }})
    FlushTimers()
    assert(#bar.navList == 4 and S.nav[bar.navList[4]], 'new button not skinned')
    assert(S.nav[bar.navList[3]].line.shown ~= false, 'the old current stop lost its line')
    assert(S.nav[bar.navList[4]].line.shown == false, 'new current stop has a line')
    local freed = bar.navList[4]
    NavBar_Reset(bar)
    FlushTimers()
    assert(#bar.navList == 1, 'reset')
    assert(S.nav[bar.navList[1]].line.shown == false, 'a lone home has a line')
    assert(S.nav[bar.navList[1]].node.color[2] > 0.8, 'lone home is not the current stop')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("map overlays: the pin and Krowi buttons are cut keys of ours over their own icons, centred, clear of the canvas edge", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local canvas = WorldMapFrame.ScrollContainer
    local cl, ct, cr, cb = Px(canvas, UIParent)
    local prev
    for _, btn in ipairs({{ WorldMapTrackingPinButton, Krowi_WorldMapButtons2 }}) do
        local name = btn:GetName()
        local k = S.keys[btn]
        assert(k and k.plate, name .. ' is not a key of ours')
        assert(btn.Border.alpha == 0 and btn.Background.alpha == 0, name .. ': the round stock art is kept')
        assert(btn.Icon.alpha == 1, name .. ': the icon must stay')
        assert(btn.scripts.OnClick, name .. ': click lost')
        assert(btn.Icon.vertex and btn.Icon.vertex[1] > 0.9 and btn.Icon.vertex[3] < 0.5, name .. ': icon not amber')
        assert(btn.Icon.desat == true, name .. ': a stock coloured icon is tinted from grey')
        local bx, by = CenterOf(btn, UIParent)
        local px, py = CenterOf(k.plate.ring, UIParent)
        assert(math.abs(bx - px) <= 0.6 and math.abs(by - py) <= 0.6, string.format('%s: plate off the middle of its button by %.1f, %.1f px', name, px - bx, py - by))
        local pl, pt, pr, pb = Px(k.plate.ring, UIParent)
        assert(pl - cl >= 5 and pt - ct >= 5, string.format('%s: plate hugs the canvas corner (%.1f, %.1f px in)', name, pl - cl, pt - ct))
        if prev then assert(pt - prev >= 2, string.format('%s: the keys touch (%.1f px between)', name, pt - prev)) end
        prev = pb
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("map overlays: the filter's ResetButton is a small key of ours tucked in the key's corner, its stock red X held", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local trk = WorldMapTrackingOptionsButton
    local reset = trk.ResetButton
    assert(reset.Art.alpha == 0 and reset.hl.alpha == 0, 'the stock red X is still drawn')
    local k = S.keys[reset]
    assert(k and k.plate and #k.glyph >= 10, 'no key of ours on the reset button')
    assert(reset.scripts.OnClick and reset.scripts.OnEnter, 'reset click lost')
    local pl, pt, pr, pb = Px(k.plate.ring, UIParent)
    local tl, tt, tr, tb = Px(trk, UIParent)
    assert(pr <= tr + 0.01 and pt >= tt - 0.01, string.format('the reset key pokes out of the filter key (%.1f px right, %.1f px up)', pr - tr, tt - pt))
    assert(pr - pl <= 16 and pb - pt <= 16, 'the reset key is no badge: ' .. (pr - pl) .. ' px')
    local _, _, _, _, gx, gy = BoxOf(k.glyph)
    assert(math.abs(gx - (pl + pr) / 2) <= 0.6 and math.abs(gy - (pt + pb) / 2) <= 0.6, 'x not in the middle of the reset key')
    local g = k.glyph[1].color
    assert(g[1] > 0.9 and g[3] < 0.5, 'the reset x is not amber, so it reads as a second close')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("map overlays: the side panel toggle is a chevron key seated clear of the canvas edge", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local tog = SidePanelToggle
    local canvas = WorldMapFrame.ScrollContainer
    local cl, ct, cr, cb = Px(canvas, UIParent)
    for _, k in ipairs({{ 'OpenButton', 'CloseButton' }}) do
        local btn = tog[k]
        local kk = S.keys[btn]
        assert(kk and #kk.glyph >= 5, k .. ' chevron')
        assert(btn.normalTex.alpha == 0, k .. ' stock arrow kept')
        local bx, by = CenterOf(btn, UIParent)
        local pl, pt, pr, pb, px, py = BoxOf({{ kk.plate.ring }})
        assert(math.abs(bx - px) <= 0.6 and math.abs(by - py) <= 0.6, string.format('%s: plate off the middle of its button by %.1f, %.1f px', k, px - bx, py - by))
        local _, _, _, _, gx, gy = BoxOf(kk.glyph)
        assert(math.abs(gx - px) <= 0.6 and math.abs(gy - py) <= 0.6, string.format('%s: chevron off the middle of its key by %.1f, %.1f px', k, gx - px, gy - py))
        assert(cr - pr >= 4 and cb - pb >= 4, string.format('%s: key hugs the canvas edge (%.1f px right, %.1f px below)', k, cr - pr, cb - pb))
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("map read-outs: mono and pink or cyan, mirrored on chips seated inside the canvas, never on its edge", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local coords
    for _, f in ipairs(WorldMapFrame.overlayFrames) do if f.CursorCoords then coords = f end end
    local canvas = WorldMapFrame.ScrollContainer
    local cl, ct, cr, cb = Px(canvas, UIParent)
    local pc = S.coords and S.coords.player
    assert(pc and pc.frame.shown ~= false, 'no player chip')
    assert(coords.PlayerCoords.Label.alpha == 0, 'the stock player text is kept under the chip')
    assert(pc.label.text == 'Player: 46.1, 67.4', 'chip text: ' .. tostring(pc.label.text))
    local l, t, r, b = Px(pc.frame, UIParent)
    assert(l - cl >= 6 and cb - b >= 6, string.format('the player chip hugs the canvas edge (%.1f px left, %.1f px above the bottom)', l - cl, cb - b))
    assert(S.coords.cursor.frame.shown == false, 'a cursor chip for a hidden cursor row')
    coords.PlayerCoords.Label:SetText('Player: 12.5, 8.0')
    assert(pc.label.text == 'Player: 12.5, 8.0', 'the chip did not follow the stock text')
    coords.CursorCoords:Show()
    coords.CursorCoords.Label:SetText('Cursor: 1.0, 2.0')
    local cc = S.coords.cursor
    assert(cc.frame.shown ~= false and cc.label.text == 'Cursor: 1.0, 2.0', 'no cursor chip')
    local l2, t2, r2, b2 = Px(cc.frame, UIParent)
    assert(b2 <= t - 2 and l2 == l, string.format('the cursor chip does not stack over the player chip (%.1f px between)', t - b2))
    coords.PlayerCoords.Label.text = Secret()
    FS.MapsSkin.RefreshCoords()
    assert(pc.frame.shown == false, 'a secret text must hide the chip')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest log top row: the Quests pill is a plate of ours clear of the search box, the settings key sits clear of the pill and the panel edge", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local sf = QuestScrollFrame
    local pill, gear = QuestLogCount, sf.SettingsDropdown
    assert(pill.Left.alpha == 0 and pill.Right.alpha == 0 and pill.Middle.alpha == 0, 'the tan pill art is kept')
    assert(QuestLogQuestCount.fontPath ~= 'stock.ttf', 'the count is not mono')
    local count = S.count
    assert(count and count.box, 'no plate of ours on the pill')
    local pl, pt, pr, pb = Px(count.box.ref, UIParent)
    local sl, st, sr, sb = Px(QuestScrollFrameSearchBox, UIParent)
    assert(pl - sr >= 3, string.format('the pill plate touches the search box (%.1f px between)', pl - sr))
    local k = S.keys[gear]
    assert(k and k.plate, 'no key on the settings button')
    local kl, kt, kr, kb = Px(k.plate.ring, UIParent)
    local ql, qt, qr, qb = Px(QuestMapFrame, UIParent)
    assert(kl - pr >= 4, string.format('the settings key touches the pill (%.1f px between)', kl - pr))
    assert(qr - kr >= 4, string.format('the settings key is cut by the panel edge (%.1f px inside)', qr - kr))
    local _, _, _, _, _, py = BoxOf({{ count.box.ref }})
    local ky = (kt + kb) / 2
    assert(math.abs(ky - py) <= 1.5, string.format('the settings key is not level with the pill (%.1f px off)', ky - py))
    assert(gear.Icon.alpha == 1 and gear.scripts.OnMouseDown, 'icon or click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nav bar: the dropdown arrows are chevrons of ours centred on the stock arrow button, the route line leaves clear of them", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local bar = WorldMapFrame.NavBar
    local seen = 0
    for i, b in ipairs(bar.navList) do
        local menu = b.MenuArrowButton
        local n = S.nav[b]
        if menu and menu.shown ~= false then
            seen = seen + 1
            assert(menu.Art.alpha == 0, 'the stock green arrow is still drawn on stop ' .. i)
            assert(n.arrow and #n.arrow.cells == 5, 'no chevron on stop ' .. i)
            local gl, gt, gr, gb, gx, gy = BoxOf(n.arrow.cells)
            local mx, my = CenterOf(menu, UIParent)
            assert(math.abs(gx - mx) <= 0.6 and math.abs(gy - my) <= 0.6, string.format('stop %d: chevron off the middle of its arrow button by %.1f, %.1f px', i, gx - mx, gy - my))
            assert(math.abs(gr - gl - 10) < 0.01 and math.abs(gb - gt - 6) < 0.01, string.format('chevron is not 10 x 6 (%.2f x %.2f)', gr - gl, gb - gt))
            assert(n.arrow.cells[1].color[2] > 0.8 and n.arrow.cells[1].color[1] < 0.3, 'chevron not cyan')
            if n.line.shown ~= false then
                local ll = Px(n.line, UIParent)
                assert(ll - gr >= 4, string.format('stop %d: the route line runs through the chevron (starts %.1f px after it)', i, ll - gr))
            end
        end
    end
    assert(seen == 2, 'arrows seen: ' .. seen)
    local home = S.nav[bar.navList[1]]
    assert(home.arrow == nil, 'a chevron on home')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest log tabs: keys over their own icons, the selected one pink, hover cyan, the new-quest glow is amber", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local q, e = QuestMapFrame.QuestsTab, QuestMapFrame.EventsTab
    for _, t in ipairs({{ q, e, QuestMapFrame.MapLegendTab }}) do
        assert(S.keys[t] and S.keys[t].plate, 'no key')
        assert(t.Background.alpha == 0 and t.SelectedTexture.alpha == 0 and t.TabGlow.alpha == 0 and t.HighlightTexture.alpha == 0, 'stock art kept')
        assert(t.Icon.alpha == 1, 'icon held')
        assert(t.scripts.OnMouseUp, 'click lost')
    end
    local qe, ee = S.keys[q].plate.ring, S.keys[e].plate.ring
    assert(qe.vertex[1] > 0.9 and qe.vertex[2] < 0.3, 'selected tab not pink')
    assert(ee.vertex[1] < 0.4 and ee.vertex[2] < 0.3, 'idle tab not dim')
    e:RunScript('OnEnter')
    assert(ee.vertex[2] > 0.8 and ee.vertex[1] < 0.3, 'hover not cyan')
    e:RunScript('OnLeave')
    e:SetChecked(true); q:SetChecked(false)
    assert(ee.vertex[1] > 0.9 and ee.vertex[2] < 0.3, 'check did not move the pink')
    q:SetTabGlowAnimationPlaying(true)
    assert(qe.vertex[1] > 0.9 and qe.vertex[2] > 0.6 and qe.vertex[3] < 0.4, 'glow not amber')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest log: the settings key, the empty texts and the party sync bar are restyled in place", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local sf = QuestScrollFrame
    assert(S.keys[sf.SettingsDropdown] and sf.SettingsDropdown.Icon.alpha == 1, 'settings key')
    assert(sf.SettingsDropdown.hl.alpha == 0, 'settings highlight kept')
    assert(sf.EmptyText.fontPath ~= 'stock.ttf' and sf.NoSearchResultsText.fontPath ~= 'stock.ttf', 'empty texts not mono')
    local sess = QuestMapFrame.QuestSessionManagement
    assert(sess.BG.alpha == 0 and sess.CommandText.fontPath ~= 'stock.ttf', 'party sync bar')
    assert(QuestScrollFrame.BorderFrame ~= nil)
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest rows: a node per quest (tracked fills cyan, ready to turn in is amber), the stock difficulty colour is never pinned", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local rows = QuestScrollFrame.titleFramePool.active
    assert(#rows == 3, 'rows')
    for _, r in ipairs(rows) do
        local rec = S.titles[r]
        assert(rec and rec.node, 'row not skinned')
        assert(r.HighlightTexture.alpha == 0, 'stock glow kept')
        assert(r.Checkbox.CheckMark.alpha == 0, 'stock check kept')
        assert(r.Text.fontPath ~= 'stock.ttf', 'title not mono')
        assert(r.scripts.OnClick, 'click lost')
    end
    assert(rows[1].Text.textColor[1] == 1 and rows[1].Text.textColor[2] == 0.82, 'stock colour changed on 1')
    assert(rows[2].Text.textColor[2] == 0.75, 'stock colour changed on 2')
    rows[2].Text:SetTextColor(0.1, 0.2, 0.9)
    assert(rows[2].Text.textColor[3] == 0.9, 'the colour is pinned')
    local n1, n2, n3 = S.titles[rows[1]].core, S.titles[rows[2]].core, S.titles[rows[3]].core
    assert(n1.shown ~= false and n1.color[2] > 0.8 and n1.color[1] < 0.3, 'tracked node not cyan')
    assert(n2.shown == false, 'untracked node filled')
    assert(n3.shown ~= false and n3.color[1] > 0.9 and n3.color[3] < 0.5, 'ready quest not amber')
    rows[2].Checkbox.CheckMark:SetShown(true)
    assert(n2.shown ~= false, 'the node did not follow the check')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest rows: the super tracked quest is caught in lock-on brackets, a hover washes the row, objectives are mono", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local rows = QuestScrollFrame.titleFramePool.active
    SUPER = 12
    QuestLogQuests_Update(); FlushTimers()
    local rec = {{}}
    for i, r in ipairs(QuestScrollFrame.titleFramePool.active) do rec[i] = S.titles[r] end
    assert(rec[2].reticle.tlH.shown ~= false and rec[2].reticle.brV.shown ~= false, 'selected row not caught')
    assert(rec[1].reticle.tlH.shown == false and rec[3].reticle.tlH.shown == false, 'other rows caught')
    SUPER = 0
    contents = QuestScrollFrame.Contents
    contents:ClearSelection(); FlushTimers()
    rows = QuestScrollFrame.titleFramePool.active
    rows[1]:RunScript('OnEnter')
    assert(S.titles[rows[1]].wash.shown ~= false, 'no hover wash')
    rows[1]:RunScript('OnLeave')
    assert(S.titles[rows[1]].wash.shown == false, 'wash stayed')
    for o in QuestScrollFrame.objectiveFramePool:EnumerateActive() do
        assert(o.Text.fontPath ~= 'stock.ttf' and o.Dash.fontPath ~= 'stock.ttf', 'objective not mono')
        assert(o.Text.textColor[1] == 0.8, 'objective colour changed')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest rows: pooled frames reused by the next update stay skinned, new ones are skinned by the update hook", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local before = {{}}
    for _, r in ipairs(QuestScrollFrame.titleFramePool.active) do before[r] = true end
    QUESTS[#QUESTS + 1] = {{ id = 14, name = 'Fourth', tracked = false, color = {{ 1, 1, 1 }}, objectives = {{ 'x' }} }}
    QuestMapFrame_UpdateAll(); FlushTimers()
    local n = 0
    for _, r in ipairs(QuestScrollFrame.titleFramePool.active) do
        n = n + 1
        assert(S.titles[r], 'row ' .. n .. ' not skinned')
    end
    assert(n == 4, 'rows ' .. n)
    local reused = 0
    for _, r in ipairs(QuestScrollFrame.titleFramePool.active) do if before[r] then reused = reused + 1 end end
    assert(reused == 3, 'frames were not reused')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest headers: a chevron that follows the collapsed state, the stock plate and plus held, title colour is ours", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local hs = QuestScrollFrame.headerFramePool.active
    assert(#hs == 2, 'headers')
    for _, h in ipairs(hs) do
        local rec = S.headers[h]
        assert(rec and #rec.cells == 5, 'no chevron')
        assert(h.normalTex.alpha == 0 and h.highlightTex.alpha == 0, 'stock plate kept')
        assert(h.CollapseButton.Icon.alpha == 0, 'stock plus kept')
        assert(h.scripts.OnClick, 'click lost')
        assert(h.text.fontPath ~= 'stock.ttf', 'header not mono')
    end
    local open, shut = S.headers[hs[1]], S.headers[hs[2]]
    assert(open.down == true and shut.down == false, 'chevron state')
    assert(open.cells[4].points[1].x ~= shut.cells[4].points[1].x, 'chevrons are the same shape')
    hs[2].CollapseButton:UpdateCollapsedState(false)
    assert(shut.down == true, 'chevron did not follow')
    hs[1]:CheckHighlightTitle(true)
    assert(hs[1].text.textColor[1] < 0.9 or hs[1].text.textColor[2] < 0.9, 'stock white pinned on a header')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("campaign banner and zone story: stock art held, an amber and a violet plate, mono texts, hover and click stay", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local c = QuestScrollFrame.campaignHeaderFramePool.active[1]
    assert(S.banners[c], 'campaign not skinned')
    assert(c.Background.alpha == 0 and c.TopFiligree.alpha == 0 and c.SelectedHighlight.alpha == 0 and c.HighlightTexture.alpha == 0, 'stock art kept')
    assert(c.Text.fontPath ~= 'stock.ttf' and c.Progress.fontPath ~= 'stock.ttf', 'campaign texts not mono')
    local e = S.banners[c].box.edges[1].color
    assert(e[1] > 0.9 and e[2] > 0.6 and e[3] < 0.4, 'campaign edge not amber')
    local st = QuestScrollFrame.Contents.StoryHeader
    assert(S.banners[st], 'story not skinned')
    assert(st.Divider.alpha == 0 and st.HighlightTexture.alpha == 0, 'story art kept')
    assert(st.scripts.OnEnter, 'story hover lost')
    assert(QuestScrollFrame.Contents.Separator.Divider.alpha == 0, 'separator filigree kept')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Character', 'Maps' }})
    assert(not WorldMapFrame.fsMapsSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(WorldMapFrame.fsMapsSkin, 'not built when combat ended')
""")

SCENES = {
    "map": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(WorldMapFrame, { title = 'map' }); FS.Theme.SkinPanel(QuestMapFrame, {}); WorldMapFrame:Show(); QuestMapFrame:Show(); SUPER = 12; QuestLogQuests_Update(); FlushTimers(); Settle(); StandIn(); return DumpOps({ WorldMapFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("maps skin", SCENES))
