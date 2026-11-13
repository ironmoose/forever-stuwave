#!/usr/bin/env python3
"""Runs the real Modules/Skins/Maps.lua headless against a mock world map and map quest log (tools/charskin_support.py).

Pinned: the border frame's stock art (nine slice, portrait, rock background, title) is held, the canvas wears a cyan ring, the
tutorial and maximize keys are cut keys that keep their clicks, the breadcrumb is a route (a node per button, a line to the
next, the current stop cyan and larger, the stock arrows held) that follows every rebuild of the bar, the overlay keys (the
tracking filter, the pin, the side panel toggle) are plates over their own icons, the quest log side tabs are keys with the
selected one pink, the quest rows are rail nodes (tracked fills cyan, ready to turn in is amber, the super tracked quest is
caught in lock-on brackets, the stock difficulty colour is never pinned), the headers carry a chevron that follows the
collapsed state, the campaign banner and the zone story are plates, and no script or attribute is written on a Blizzard widget.
Run `python3 tools/mapsskin-harness.py [--png debug/maps]`. The mock is NOT the real client.
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
    local win = blz("Frame", "WorldMapFrame", UIParent, 702, 534)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -60 }
    win.shown = false
    tex(win, "WorldMapFramePortraitStock", "ARTWORK")
    local border = blz("Frame", nil, win, 702, 534, "TOPLEFT", 0, 0)
    border.points = { { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = win, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    win.BorderFrame = border
    border.NineSlice = blz("Frame", nil, border, 702, 534)
    atex(border.NineSlice, nil, "BORDER", "UI-Frame-TopLeftCorner", 32, 32)
    border.PortraitContainer = blz("Frame", nil, border, 1, 1)
    border.PortraitContainer.portrait = tex(border.PortraitContainer, "WorldMapFramePortrait", "OVERLAY")
    border.TitleContainer = blz("Frame", nil, border, 600, 20, "TOPLEFT", 58, -1)
    border.TitleContainer.TitleText = fstring(border.TitleContainer, nil, "Map & Quest Log", 12)
    border.Bg = tex(border, nil, "BACKGROUND")
    border.TopTileStreaks = tex(border, nil, "BORDER")
    border.InsetBorderTop = tex(border, nil, "BACKGROUND")
    border.Underlay = tex(border, nil, "ARTWORK"); border.Underlay.shown = false
    local close = blz("Button", "WorldMapFrameCloseButton", border, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    border.CloseButton = close
    local tut = blz("Button", nil, border, 46, 46, "TOPLEFT", 43, 19)
    tut.I = tex(tut, nil, "ARTWORK"); tut.Ring = tex(tut, nil, "OVERLAY"); tut.BigIPulse = tex(tut, nil, "OVERLAY")
    tut.RingPulse = tex(tut, nil, "OVERLAY")
    tut.scripts.OnClick = function() end
    tut.scripts.OnEnter = function() end
    border.Tutorial = tut
    local mm = blz("Frame", nil, border, 24, 24, "TOPRIGHT", -26, -4)
    border.MaximizeMinimizeFrame = mm
    for _, key in ipairs({ "MaximizeButton", "MinimizeButton" }) do
        local b = blz("Button", nil, mm, 24, 24, "TOPLEFT", 0, 0)
        b.points = { { point = "TOPLEFT", rel = mm, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = mm, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
        b.normalTex = atex(b, nil, "ARTWORK", "RedButton-Expand", 24, 24)
        b.pushedTex = atex(b, nil, "ARTWORK", "RedButton-Expand-Pressed", 24, 24)
        b.highlightTex = atex(b, nil, "HIGHLIGHT", "RedButton-Highlight", 24, 24)
        b.scripts.OnClick = function() end
        mm[key] = b
    end
    mm.MaximizeButton.shown = false
    win.TitleCanvasSpacerFrame = blz("Frame", nil, win, 696, 67, "TOPLEFT", 2, 0)
    local canvas = blz("Frame", nil, win, 696, 440, "TOPLEFT", 2, -67)
    win.ScrollContainer = canvas

    -- the overlay frames the map builds, anonymous and in win.overlayFrames
    win.overlayFrames = {}
    local function overlay(f) win.overlayFrames[#win.overlayFrames + 1] = f; return f end
    local trk = overlay(blz("Button", nil, win, 32, 32, "TOPRIGHT", -8, -72))
    trk.Shadow = atex(trk, nil, "BACKGROUND", "MapCornerShadow-Right", 32, 32)
    trk.FilterCounterBanner = atex(trk, nil, "BACKGROUND", "map-filter-banner", 40, 20)
    trk.Background = tex(trk, nil, "BACKGROUND")
    trk.Icon = atex(trk, nil, "ARTWORK", "Map-Filter-Button", 20, 20)
    trk.Border = tex(trk, nil, "OVERLAY")
    trk.FilterCounter = blz("Frame", nil, trk, 24, 22, "RIGHT", -34, 0)
    trk.FilterCounter.Count = fstring(trk.FilterCounter, nil, "2", 12)
    trk.ResetButton = blz("Button", nil, trk, 12, 12, "TOPRIGHT", 0, 0)
    trk.scripts.OnEnter = function() end
    trk.scripts.OnClick = function() end
    local pin = overlay(blz("Button", nil, win, 32, 32, "TOPRIGHT", -8, -104))
    pin.Background = tex(pin, nil, "BACKGROUND")
    pin.Icon = atex(pin, nil, "ARTWORK", "Waypoint-MapPin-Untracked", 20, 20)
    pin.IconOverlay = tex(pin, nil, "OVERLAY"); pin.IconOverlay.shown = false
    pin.Border = tex(pin, nil, "OVERLAY")
    pin.ActiveTexture = tex(pin, nil, "OVERLAY"); pin.ActiveTexture.shown = false
    pin.scripts.OnClick = function() end
    local coords = overlay(blz("Frame", nil, win, 100, 30, "BOTTOMLEFT", 70, 6))
    coords.CursorCoords = blz("Frame", nil, coords, 100, 15, "TOPLEFT", 0, 0)
    coords.CursorCoords.Label = fstring(coords.CursorCoords, nil, "Cursor: 52.0, 30.3", 11, { 1, 1, 1, 1 })
    coords.PlayerCoords = blz("Frame", nil, coords, 100, 15, "TOPLEFT", 0, -15)
    coords.PlayerCoords.Label = fstring(coords.PlayerCoords, nil, "Player: 48.1, 33.7", 11, { 1, 1, 1, 1 })
    local tog = overlay(blz("Frame", nil, win, 32, 32, "BOTTOMRIGHT", -2, 1))
    for _, key in ipairs({ "OpenButton", "CloseButton" }) do
        local b = blz("Button", nil, tog, 32, 32, "CENTER", 0, 0)
        tex(b, nil, "BACKGROUND")
        b.normalTex = atex(b, nil, "ARTWORK", "QuestCollapse-Show-Up", 32, 32)
        b.pushedTex = atex(b, nil, "ARTWORK", "QuestCollapse-Show-Down", 32, 32)
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        tog[key] = b
    end
    tog.OpenButton.shown = false

    -- the breadcrumb: NavigationBar.lua's buttons, with its global functions
    local bar = blz("Frame", nil, win, 600, 34, "TOPLEFT", 66, -25)
    win.NavBar = bar
    win.overlayFrames[#win.overlayFrames + 1] = bar
    tex(bar, nil, "BACKGROUND")
    tex(bar, nil, "BORDER")
    bar.overlay = blz("Frame", nil, bar, 600, 34, "TOPLEFT", 0, 0)
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
        b.MenuArrowButton = blz("Button", nil, b, 27, 31, "RIGHT", -2, 0)
        b.MenuArrowButton.Art = tex(b.MenuArrowButton, nil, "OVERLAY")
        b.MenuArrowButton.normalTex = tex(b.MenuArrowButton, nil, "ARTWORK")
        b.MenuArrowButton.shown = false
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
        b:SetWidth(b.text:GetStringWidth() + 30)
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
    local qm = blz("Frame", "QuestMapFrame", win, 333, 490, "TOPRIGHT", -3, -25)
    qm.shown = false
    for _, spec in ipairs({ { "QuestsTab", 1 }, { "EventsTab", 2 }, { "MapLegendTab", 3 } }) do
        local t = blz("Frame", nil, qm, 43, 55, "TOPLEFT", 335, -(20 + (spec[2] - 1) * 60))
        t.Background = atex(t, nil, "BACKGROUND", "common-sidetab", 55, 60)
        t.Icon = tex(t, nil, "ARTWORK"); t.Icon.w, t.Icon.h = 30, 30
        t.SelectedTexture = atex(t, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        t.TabGlow = atex(t, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        t.HighlightTexture = atex(t, nil, "HIGHLIGHT", "common-sidetab-hover", 55, 60)
        t.SelectedTexture.shown = (spec[2] == 1)
        t.glowing = false
        t.SetChecked = function(self, v) self.SelectedTexture:SetShown(v) end
        t.SetTabGlowAnimationPlaying = function(self, v) self.glowing = v end
        t.IsTabGlowAnimationPlaying = function(self) return self.glowing end
        t.scripts.OnMouseUp = function() end
        t.scripts.OnEnter = function() end
        qm[spec[1]] = t
    end
    local qf = blz("Frame", nil, qm, 320, 450, "TOPLEFT", 6, -30)
    qm.QuestsFrame = qf
    local sf = blz("ScrollFrame", "QuestScrollFrame", qf, 300, 400, "TOPLEFT", 0, -40)
    qf.ScrollFrame = sf
    sf.NoSearchResultsText = fstring(sf, nil, "No quests match", 13, { 1, 1, 1, 1 }); sf.NoSearchResultsText.shown = false
    sf.EmptyText = fstring(sf, nil, "No quests", 16, { 1, 1, 1, 1 }); sf.EmptyText.shown = false
    sf.SearchBox = blz("EditBox", nil, qf, 250, 20, "TOPLEFT", 6, -8)
    sf.SettingsDropdown = blz("Button", nil, qf, 15, 16, "TOPRIGHT", -8, -10)
    sf.SettingsDropdown.intrinsic = "DropdownButton"
    sf.SettingsDropdown.Icon = atex(sf.SettingsDropdown, nil, "ARTWORK", "questlog-icon-setting", 15, 16)
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
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Maps": "Modules/Skins/Maps.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); WorldMapFrame:Show(); QuestMapFrame:Show(); FlushTimers()"


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
    local p = label.points[1]
    assert(p.rel == WorldMapFrame and p.x >= 89, 'title overlaps the tutorial key: x=' .. tostring(p.x))
    WorldMapFrame.BorderFrame.Tutorial:Hide()
    assert(label.points[1].x == 10, 'title did not come back when the tutorial hid')
    WorldMapFrame.BorderFrame.Tutorial:Show()
    assert(label.points[1].x >= 89, 'title did not move out again')
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

case("map overlays: the filter and pin buttons are plates over their own icons, the toggle is a chevron key, the coords are mono", f"""
    {OPEN}
    local S = FS.MapsSkin.state
    local trk, pin, coords, tog
    for _, f in ipairs(WorldMapFrame.overlayFrames) do
        if f.FilterCounter then trk = f elseif f.IconOverlay then pin = f elseif f.CursorCoords then coords = f elseif f.OpenButton then tog = f end
    end
    for _, btn in ipairs({{ trk, pin }}) do
        local k = S.keys[btn]
        assert(k and k.plate, 'no plate')
        assert(btn.Icon.alpha == 1, 'the icon must stay')
        assert(btn.Border.alpha == 0 and btn.Background.alpha == 0, 'round art kept')
        assert(btn.scripts.OnClick, 'click lost')
    end
    assert(trk.FilterCounterBanner.alpha == 0, 'banner kept')
    assert(trk.FilterCounter.Count.fontPath ~= 'stock.ttf', 'count not mono')
    assert(pin.Icon.vertex and pin.Icon.vertex[1] > 0.9 and pin.Icon.vertex[3] < 0.5, 'pin icon not amber')
    assert(trk.Icon.vertex and trk.Icon.vertex[3] > 0.9 and trk.Icon.vertex[1] < 0.3, 'filter icon not cyan')
    for _, k in ipairs({{ 'OpenButton', 'CloseButton' }}) do
        local kk = S.keys[tog[k]]
        assert(kk and #kk.glyph >= 5, k .. ' chevron')
        assert(tog[k].normalTex.alpha == 0, k .. ' stock arrow kept')
    end
    assert(coords.CursorCoords.Label.fontPath ~= 'stock.ttf' and coords.PlayerCoords.Label.fontPath ~= 'stock.ttf', 'coords not mono')
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
    "map": "Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(WorldMapFrame, { title = 'map' }); FS.Theme.SkinPanel(QuestMapFrame, {}); WorldMapFrame:Show(); QuestMapFrame:Show(); SUPER = 12; QuestLogQuests_Update(); NavBar_AddButton(WorldMapFrame.NavBar, { name = 'Bloodhoof' }); FlushTimers(); return DumpOps({ WorldMapFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("maps skin", SCENES))
