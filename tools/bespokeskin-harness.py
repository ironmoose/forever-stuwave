#!/usr/bin/env python3
"""Runs the real Modules/Skins/Bespoke.lua headless against mock calendar, achievement, dressing room, tabard, gem socket and
barber shop windows (tools/charskin_support.py).

Pinned: each window wears the panel chrome (a stuwave:// band) over held stock art, the parts that carry meaning are kept (the
tabard emblem is never held or hidden, the sockets keep their gem, colour and shine), the calendar's 42 cells are ink cells whose
edge follows today, the selected day, a day of another month and the cursor, the achievement rows follow earned, selected and hover
and recycle through their scroll box, dark parchment text is lightened and stays light, the arrows and rotate buttons are chevron
keys, and no script or attribute is written on a Blizzard widget (the mock throws on both).
Run `python3 tools/bespokeskin-harness.py [--png debug/bespoke]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
SKINNED = {}

local PREFIXES = { "^Calendar", "^Achievement", "^DressUp", "^Tabard", "^ItemSocketing", "^BarberShop" }

local function scrollbox(parent, make, w, h)
    local box = blz("Frame", nil, parent, w, h)
    box.frames = {}
    function box:ForEachFrame(fn) for _, f in ipairs(self.frames) do fn(f, f.elementData) end end
    function box:Update() end
    function box:Add()
        local f = make(self)
        self.frames[#self.frames + 1] = f
        self:Update()
        return f
    end
    return box
end

-- ButtonFrameTemplate: NineSlice, Bg, TopTileStreaks, PortraitContainer, Inset, TitleContainer, CloseButton
local function buttonFrame(name, w, h)
    local win = blz("Frame", name, UIParent, w, h)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    win.NineSlice = blz("Frame", nil, win, w, h)
    atex(win.NineSlice, nil, "BORDER", "UI-Frame-TopLeftCorner", 32, 32)
    win.Bg = tex(win, nil, "BACKGROUND")
    win.TopTileStreaks = tex(win, nil, "BORDER")
    win.PortraitContainer = blz("Frame", nil, win, 60, 60)
    win.PortraitContainer.portrait = tex(win.PortraitContainer, nil, "OVERLAY")
    win.Inset = blz("Frame", nil, win, w - 20, h - 80, "TOPLEFT", 10, -60)
    win.Inset.Bg = tex(win.Inset, nil, "BACKGROUND")
    win.Inset.NineSlice = blz("Frame", nil, win.Inset, w - 20, h - 80)
    win.TitleContainer = blz("Frame", nil, win, w - 100, 20, "TOPLEFT", 58, -1)
    win.TitleContainer.TitleText = fstring(win.TitleContainer, nil, "Stock Title", 12)
    local close = blz("Button", name .. "CloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    close.scripts.OnClick = function() end
    win.CloseButton = close
    return win
end

local function iconButton(parent, name, w, h, point, x, y)
    local b = blz("Button", name, parent, w, h, point or "TOPLEFT", x or 0, y or 0)
    b.normalTex = atex(b, nil, "ARTWORK", "stock-arrow-up", w, h)
    b.pushedTex = atex(b, nil, "ARTWORK", "stock-arrow-down", w, h)
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    return b
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" then
            for _, p in ipairs(PREFIXES) do if k:find(p) then _G[k] = nil end end
        end
    end
    SKINNED = {}

    ---------------------------------------------------------------------------------------------------------------
    -- Calendar
    ---------------------------------------------------------------------------------------------------------------
    local cal = blz("Frame", "CalendarFrame", UIParent, 659, 624)
    cal.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 15, y = -80 }
    cal.shown = false
    for _, n in ipairs({ "TopLeftTexture", "TopMiddleTexture", "TopRightTexture", "LeftTopTexture", "LeftMiddleTexture",
        "LeftBottomTexture", "RightTopTexture", "RightMiddleTexture", "RightBottomTexture", "BottomLeftTexture",
        "BottomMiddleTexture", "BottomRightTexture" }) do
        tex(cal, "CalendarFrame" .. n, "BORDER")
    end
    for i = 1, 7 do
        local bg = tex(cal, "CalendarWeekday" .. i .. "Background", "BACKGROUND")
        bg.w, bg.h = 91, 28
        bg.points[1] = { point = "TOPLEFT", rel = cal, relPoint = "TOPLEFT", x = 8 + (i - 1) * 91, y = -62 }
        local n = fstring(cal, "CalendarWeekday" .. i .. "Name", ({ "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat" })[i], 12)
        n.points[1] = { point = "CENTER", rel = bg, relPoint = "CENTER", x = 0, y = 0 }
    end
    local mbg = tex(cal, "CalendarMonthBackground", "OVERLAY")
    mbg.w, mbg.h = 142, 36
    mbg.points[1] = { point = "TOP", rel = cal, relPoint = "TOP", x = -3, y = -22 }
    local mname = fstring(cal, "CalendarMonthName", "November", 18, { 1, 1, 1, 1 })
    mname.points[1] = { point = "CENTER", rel = mbg, relPoint = "CENTER", x = 0, y = 0 }
    local ybg = tex(cal, "CalendarYearBackground", "ARTWORK")
    ybg.w, ybg.h = 47, 24
    ybg.points[1] = { point = "TOP", rel = mbg, relPoint = "BOTTOM", x = -2, y = 13 }
    local yname = fstring(cal, "CalendarYearName", "2026", 11)
    yname.points[1] = { point = "CENTER", rel = ybg, relPoint = "CENTER", x = 0, y = -1 }
    tex(cal, "CalendarLastDayDarkTexture", "ARTWORK").shown = false
    tex(cal, "CalendarWeekdaySelectedTexture", "ARTWORK").shown = false
    local today = blz("Frame", "CalendarTodayFrame", cal, 145, 140)
    today.shown = false
    tex(today, "CalendarTodayTexture", "BORDER")
    tex(today, "CalendarTodayTextureGlow", "OVERLAY")
    function today:SetParent(p) self.parent = p end
    local prev = iconButton(cal, "CalendarPrevMonthButton", 32, 32, "TOPLEFT", 40, -24)
    local nxt = iconButton(cal, "CalendarNextMonthButton", 32, 32, "TOPRIGHT", -40, -24)
    cal.CloseBtn = iconButton(cal, "CalendarCloseButton", 20, 20, "TOPRIGHT", 1, -17)
    cal.hovered = {}
    for i = 1, 42 do
        local col, row = (i - 1) % 7, math.floor((i - 1) / 7)
        local name = "CalendarDayButton" .. i
        local b = blz("Button", name, cal, 91, 89, "TOPLEFT", 8 + col * 91, -(90 + row * 89))
        b.normalTex = atex(b, nil, "ARTWORK", "calendar-cell", 91, 91)
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        tex(b, name .. "EventTexture", "BORDER").shown = false
        tex(b, name .. "EventBackgroundTexture", "ARTWORK").shown = false
        tex(b, name .. "PendingInviteTexture", "OVERLAY").shown = false
        local df = blz("Frame", name .. "DateFrame", b, 23, 18, "TOPLEFT", 5, -5)
        tex(df, name .. "DateFrameBackground", "BORDER").shown = false
        local date = fstring(df, name .. "DateFrameDate", tostring(((i + 5) % 30) + 1), 12, { 1, 1, 1, 1 })
        date.points[1] = { point = "CENTER", rel = df, relPoint = "CENTER", x = 0, y = 0 }
        local dark = blz("Frame", name .. "DarkFrame", b, 91, 91, "CENTER", 0, 0)
        dark.shown = false
        for e = 1, 2 do
            local ev = blz("Button", name .. "EventButton" .. e, b, 83, 24, "TOPLEFT", 4, -26 - (e - 1) * 24)
            tex(ev, name .. "EventButton" .. e .. "Black", "ARTWORK").shown = false
            local t1 = fstring(ev, name .. "EventButton" .. e .. "Text1", "Darkmoon Faire", 10, { 1, 0.82, 0, 1 })
            local t2 = fstring(ev, name .. "EventButton" .. e .. "Text2", "", 10, { 1, 1, 1, 1 })
            ev.shown = (i == 5 or i == 12) and e == 1
        end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        function b:LockHighlight() self.lockedHighlight = true end
        function b:UnlockHighlight() self.lockedHighlight = false end
    end
    function CalendarFrame_Update() end
    -- the popups: DialogBorderDarkTemplate Border and DialogHeaderTemplate Header
    local function popup(name, closeName)
        local f = blz("Frame", name, cal, 320, 320, "TOPRIGHT", 320, -24)
        f.shown = false
        tex(f, nil, "BORDER").shown = false
        f.Border = blz("Frame", nil, f, 320, 320)
        atex(f.Border, nil, "BORDER", "UI-Frame-TopLeftCorner", 32, 32)
        f.Header = blz("Frame", nil, f, 200, 32, "TOP", 0, 10)
        tex(f.Header, nil, "BACKGROUND")
        if closeName then iconButton(f, closeName, 20, 20, "TOPRIGHT", 0, 0) end
        return f
    end
    popup("CalendarViewHolidayFrame", "CalendarViewHolidayCloseButton")
    popup("CalendarViewRaidFrame", "CalendarViewRaidCloseButton")
    popup("CalendarViewEventFrame", "CalendarViewEventCloseButton")
    popup("CalendarCreateEventFrame", "CalendarCreateEventCloseButton")
    popup("CalendarEventPickerFrame", nil)

    ---------------------------------------------------------------------------------------------------------------
    -- Achievements
    ---------------------------------------------------------------------------------------------------------------
    local ach = blz("Frame", "AchievementFrame", UIParent, 768, 500)
    ach.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 120, y = -80 }
    ach.shown = false
    ach.Background = tex(ach, nil, "BACKGROUND")
    for _, n in ipairs({ "MetalBorderLeft", "MetalBorderRight", "MetalBorderBottom", "MetalBorderTop", "CategoriesBG", "WaterMark",
        "GuildEmblemLeft", "GuildEmblemRight", "MetalBorderTopLeft", "WoodBorderTopLeft", "WoodBorderBottomRight" }) do
        tex(ach, "AchievementFrame" .. n, "ARTWORK")
    end
    ach.Header = blz("Frame", nil, ach, 529, 38, "TOPLEFT", 190, -22)
    ach.Header.Left = tex(ach.Header, nil, "BACKGROUND")
    ach.Header.Right = tex(ach.Header, nil, "BACKGROUND")
    ach.Header.PointBorder = tex(ach.Header, nil, "BORDER")
    ach.Header.Title = fstring(ach.Header, nil, "Achievements", 12)
    ach.Header.Title.points[1] = { point = "LEFT", rel = ach.Header, relPoint = "LEFT", x = 12, y = 0 }
    ach.Header.Points = fstring(ach.Header, nil, "1245", 14, { 1, 1, 1, 1 })
    ach.Header.Points.points[1] = { point = "RIGHT", rel = ach.Header, relPoint = "RIGHT", x = -30, y = 0 }
    ach.HeaderDetails = blz("Frame", nil, ach, 529, 38, "TOPLEFT", 190, -62)
    ach.HeaderDetails.TopTileStreaks = tex(ach.HeaderDetails, nil, "BACKGROUND")
    ach.HeaderDetails.Filters = blz("Frame", nil, ach.HeaderDetails, 200, 30, "TOPRIGHT", -4, -4)
    ach.HeaderDetails.Filters.SearchBox = blz("EditBox", nil, ach.HeaderDetails.Filters, 107, 30, "TOPLEFT", 0, 0)
    local spc = blz("Frame", nil, ach.HeaderDetails.Filters.SearchBox, 206, 27, "TOPLEFT", 0, -30)
    spc.shown = false
    spc.Background = atex(spc, nil, "BACKGROUND", "_search-rowbg", 206, 27)
    spc.BorderAnchor = tex(spc, nil, "OVERLAY")
    spc.BottomBorder = tex(spc, nil, "OVERLAY")
    ach.HeaderDetails.Filters.SearchBox.SearchPreviewContainer = spc
    ach.SearchResults = blz("Frame", nil, ach, 600, 380, "TOPLEFT", 180, -100)
    ach.SearchResults.shown = false
    tex(ach.SearchResults, nil, "BACKGROUND")
    iconButton(ach, "AchievementFrameCloseButton", 20, 20, "TOPRIGHT", 1, -17)

    local cats = blz("Frame", "AchievementFrameCategories", ach, 175, 400, "TOPLEFT", 14, -62)
    ach.Categories = cats
    cats.NineSlice = blz("Frame", nil, cats, 175, 400)
    atex(cats.NineSlice, nil, "BORDER", "UI-Frame-TopLeftCorner", 32, 32)
    local function catRow(parent)
        local r = blz("Frame", nil, parent, 158, 24)
        local n = #parent.frames
        r.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = -n * 26 }
        r.Button = blz("Button", nil, r, 158, 24, "TOPLEFT", 0, 0)
        r.Button.Background = tex(r.Button, nil, "BACKGROUND")
        r.Button.highlightTex = tex(r.Button, nil, "HIGHLIGHT")
        r.Button.Label = fstring(r.Button, nil, ({ "General", "Quests", "Exploration" })[n + 1] or "Category", 12)
        r.Button.Label.points[1] = { point = "LEFT", rel = r.Button, relPoint = "LEFT", x = 10, y = 0 }
        r.Button.scripts.OnClick = function() end
        r.Button.scripts.OnEnter = function() end
        function r:UpdateSelectionState(selected) self.selected = selected end
        return r
    end
    cats.ScrollBox = scrollbox(cats, catRow, 158, 380)
    cats.ScrollBox.points[1] = { point = "TOPLEFT", rel = cats, relPoint = "TOPLEFT", x = 8, y = -8 }
    CATBOX = cats.ScrollBox

    local page = blz("Frame", "AchievementFrameAchievements", ach, 530, 400, "TOPLEFT", 200, -104)
    page.Background = tex(page, nil, "BACKGROUND")
    local function achRow(parent)
        local r = blz("Button", nil, parent, 500, 64)
        local n = #parent.frames
        r.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = -n * 68 }
        for _, k in ipairs({ "Background", "BottomLeftTsunami", "BottomRightTsunami", "TopLeftTsunami", "TopRightTsunami",
            "BottomTsunami1", "TopTsunami1", "TitleBar", "Glow", "RewardBackground", "GuildCornerL", "GuildCornerR" }) do
            r[k] = tex(r, nil, "BACKGROUND")
        end
        r.NineSlice = blz("Frame", nil, r, 500, 64)
        r.Highlight = blz("Frame", nil, r, 500, 64)
        r.Highlight.shown = false
        r.Icon = blz("Frame", nil, r, 72, 72, "LEFT", 8, 0)
        r.Icon.bling = tex(r.Icon, nil, "BORDER")
        r.Icon.texture = tex(r.Icon, nil, "ARTWORK")
        r.Icon.texture.w, r.Icon.texture.h = 50, 50
        r.Icon.texture.points[1] = { point = "CENTER", rel = r.Icon, relPoint = "CENTER", x = 0, y = 0 }
        r.Icon.frame = tex(r.Icon, nil, "OVERLAY")
        r.Label = fstring(r, nil, "For the Alliance!", 13, { 1, 1, 1, 1 })
        r.Label.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 90, y = -8 }
        r.Description = fstring(r, nil, "Complete the zone quests.", 11, { 0, 0, 0, 1 })
        r.Description.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 90, y = -28 }
        r.HiddenDescription = fstring(r, nil, "", 11, { 0, 0, 0, 1 })
        r.Reward = fstring(r, nil, "", 11, { 1, 0.82, 0, 1 })
        r.Shield = blz("Button", nil, r, 64, 64, "RIGHT", -8, 0)
        r.Shield.Points = fstring(r.Shield, nil, "10", 14, { 1, 1, 1, 1 })
        r.Shield.DateCompleted = fstring(r.Shield, nil, "", 10, { 1, 1, 1, 1 })
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function() end
        function r:IsSelected() return self.selected == true end
        function r:SetSelected(s) self.selected = s end
        function r:Saturate() self.completed = true; self.Description:SetTextColor(0, 0, 0, 1) end
        function r:Desaturate() self.completed = nil; self.Description:SetTextColor(1, 1, 1, 1) end
        function r:Init() end
        function r:Expand() end
        function r:Collapse() end
        return r
    end
    page.ScrollBox = scrollbox(page, achRow, 500, 380)
    ACHBOX = page.ScrollBox
    local obj = blz("Frame", "AchievementFrameAchievementsObjectives", page, 400, 80, "TOPLEFT", 0, -200)
    local crit = blz("Frame", nil, obj, 400, 20, "TOPLEFT", 0, 0)
    CRIT = fstring(crit, nil, "Kill 10 boars", 11, { 0, 0, 0, 1 })
    function AchievementObjectives_DisplayCriteria() CRIT:SetTextColor(0, 0, 0, 1) end
    function AchievementObjectives_DisplayProgressiveAchievement() end

    local stats = blz("Frame", "AchievementFrameStats", ach, 530, 400, "TOPLEFT", 200, -104)
    stats.shown = false
    tex(stats, nil, "BACKGROUND")
    blz("Frame", "AchievementFrameStatsBG", stats, 530, 400)
    tex(_G.AchievementFrameStatsBG, nil, "BACKGROUND")
    stats.ScrollBox = scrollbox(stats, function(parent)
        local r = blz("Button", nil, parent, 500, 20)
        r.Background = tex(r, nil, "BACKGROUND")
        r.Title = fstring(r, nil, "Total deaths", 11, { 0, 0, 0, 1 })
        return r
    end, 500, 380)
    local summary = blz("Frame", "AchievementFrameSummary", ach, 530, 400, "TOPLEFT", 200, -104)
    summary.shown = false
    summary.Background = tex(summary, nil, "BACKGROUND")
    for i = 1, 4 do
        local r = blz("Button", "AchievementFrameSummaryAchievement" .. i, summary, 500, 60, "TOPLEFT", 0, -(i - 1) * 64)
        r.Background = tex(r, nil, "BACKGROUND")
        r.Label = fstring(r, nil, "Latest " .. i, 12, { 1, 1, 1, 1 })
        r.Description = fstring(r, nil, "dark text", 11, { 0, 0, 0, 1 })
    end

    ---------------------------------------------------------------------------------------------------------------
    -- Dressing room
    ---------------------------------------------------------------------------------------------------------------
    local dress = buttonFrame("DressUpFrame", 450, 545)
    dress.ModelScene = blz("Frame", nil, dress, 400, 420, "TOPLEFT", 25, -60)
    dress.ModelBackground = atex(dress, nil, "BACKGROUND", "dressingroom-background-warrior", 400, 420)
    dress.ModelBackground.points = { { point = "TOPLEFT", rel = dress.ModelScene, relPoint = "TOPLEFT", x = 0, y = 0 },
        { point = "BOTTOMRIGHT", rel = dress.ModelScene, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
    local mm = blz("Frame", nil, dress, 24, 24, "TOPRIGHT", -26, -4)
    dress.MaximizeMinimizeFrame = mm
    for _, k in ipairs({ "MaximizeButton", "MinimizeButton" }) do
        local b = blz("Button", nil, mm, 24, 24, "TOPLEFT", 0, 0)
        b.normalTex = atex(b, nil, "ARTWORK", "RedButton-Expand", 24, 24)
        b.scripts.OnClick = function() end
        mm[k] = b
    end
    mm.MaximizeButton.shown = false
    dress.ToggleCustomSetDetailsButton = iconButton(dress, nil, 27, 25, "TOPRIGHT", -11, -30)
    local det = blz("Frame", nil, dress, 313, 473, "TOPRIGHT", 304, -29)
    dress.CustomSetDetailsPanel = det
    det.BlackBackground = tex(det, nil, "BACKGROUND")
    det.ClassBackground = tex(det, nil, "BORDER")
    det.Sideframe = atex(det, nil, "OVERLAY", "dressingroom-sideframe", 313, 473)
    dress.ResetButton = blz("Button", "DressUpFrameResetButton", dress, 80, 22, "BOTTOMRIGHT", -90, 4)
    dress.ResetButton.scripts.OnClick = function() end

    ---------------------------------------------------------------------------------------------------------------
    -- Tabard
    ---------------------------------------------------------------------------------------------------------------
    local tab = buttonFrame("TabardFrame", 384, 512)
    tex(tab, "TabardFramePortrait", "BACKGROUND")
    for _, n in ipairs({ "TopLeft", "Top", "TopRight", "LeftTop", "LeftBottom", "RightTop", "RightBottom", "BottomLeft", "Bottom",
        "BottomRight" }) do
        tex(tab, "TabardFrameOuterFrame" .. n, "OVERLAY")
    end
    for _, n in ipairs({ "TopRight", "BottomRight", "TopLeft", "BottomLeft" }) do
        local e = tex(tab, "TabardFrameEmblem" .. n, "OVERLAY")
        e.blend = "ADD"
        e.w, e.h = 64, 64
    end
    local nameText = fstring(tab, "TabardFrameNameText", "Stu's Tabard", 14)
    nameText.points[1] = { point = "CENTER", rel = tab, relPoint = "CENTER", x = 6, y = 202 }
    local greet = fstring(tab, "TabardFrameGreetingText", "Choose a design", 12, { 1, 1, 1, 1 })
    greet.points[1] = { point = "TOP", rel = tab, relPoint = "TOP", x = 15, y = -28 }
    local model = blz("Frame", "TabardModel", tab, 303, 317, "BOTTOM", 0, 38)
    iconButton(model, "TabardCharacterModelRotateLeftButton", 35, 35, "BOTTOMLEFT", 14, 33)
    iconButton(model, "TabardCharacterModelRotateRightButton", 35, 35, "BOTTOMLEFT", 44, 33)
    local cost = blz("Frame", "TabardFrameCostFrame", tab, 170, 23, "TOPRIGHT", -7, -52)
    cost.NineSlice = blz("Frame", nil, cost, 170, 23)
    local costLabel = fstring(cost, "TabardFrameCostLabel", "Cost", 12, { 1, 1, 1, 1 })
    costLabel.points[1] = { point = "LEFT", rel = cost, relPoint = "LEFT", x = 8, y = 0 }
    blz("Frame", "TabardFrameCostMoneyFrame", cost, 100, 20, "RIGHT", 0, 0)
    local custom = blz("Frame", "TabardFrameCustomizationFrame", tab, 220, 200, "TOPLEFT", 82, -250)
    tex(custom, "TabardFrameCustomizationBorder", "BACKGROUND")
    for i = 1, 5 do
        local n = "TabardFrameCustomization" .. i
        local row = blz("Frame", n, custom, 164, 20, "TOPLEFT", 28, -10 - (i - 1) * 25)
        tex(row, n .. "Left", "BACKGROUND"); tex(row, n .. "Middle", "BACKGROUND"); tex(row, n .. "Right", "BACKGROUND")
        local t = fstring(row, n .. "Text", ({ "Emblem", "Emblem colour", "Border", "Border colour", "Background" })[i], 11, { 1, 1, 1, 1 })
        t.points[1] = { point = "CENTER", rel = row, relPoint = "CENTER", x = 0, y = 0 }
        iconButton(row, n .. "LeftButton", 32, 32, "LEFT", -24, 2)
        iconButton(row, n .. "RightButton", 32, 32, "RIGHT", 24, 2)
    end
    blz("Frame", "TabardFrameMoneyInset", tab, 100, 20, "BOTTOMLEFT", 10, 30)
    blz("Frame", "TabardFrameMoneyBg", tab, 100, 20, "BOTTOMLEFT", 10, 30)
    blz("Frame", "TabardFrameMoneyFrame", tab, 100, 20, "BOTTOMLEFT", 10, 30)

    ---------------------------------------------------------------------------------------------------------------
    -- Gem sockets
    ---------------------------------------------------------------------------------------------------------------
    local sock = buttonFrame("ItemSocketingFrame", 338, 424)
    for _, n in ipairs({ "ParchmentFrame-Top", "ParchmentFrame-Bottom", "ParchmentFrame-Left", "ParchmentFrame-Right", "SocketFrame-Left",
        "SocketFrame-Right", "ButtonFrame-Left", "ButtonFrame-Right", "ButtonBorder-Mid", "GoldBorder-BottomRight", "GoldBorder-Top",
        "BackgroundColor", "BackgroundHighlight", "BorderShadow-Top", "BottomLeftNub" }) do
        sock[n] = tex(sock, nil, "BACKGROUND")
    end
    local cont = blz("Frame", nil, sock, 300, 200, "TOPLEFT", 20, -80)
    sock.SocketingContainer = cont
    cont.SocketFrames = {}
    for i = 1, 3 do
        local s = blz("Button", nil, cont, 40, 40, "TOPLEFT", 20 + (i - 1) * 90, -20)
        s.RightFiligree = tex(s, nil, "BACKGROUND")
        s.LeftFiligree = tex(s, nil, "BACKGROUND")
        tex(s, nil, "BORDER")
        s.Background = atex(s, nil, "BORDER", "socket-red-closed", 43, 44)
        s.Background:SetColorTexture(0.8, 0.12, 0.12, 0.5)
        s.Background.points[1] = { point = "CENTER", rel = s, relPoint = "CENTER", x = 0, y = 0 }
        s.Icon = tex(s, nil, "ARTWORK")
        s.Icon.w, s.Icon.h = 38, 38
        s.Icon:SetColorTexture(0.3, 0.6, 1, 1)
        s.Icon.points[1] = { point = "CENTER", rel = s, relPoint = "CENTER", x = 0, y = 0 }
        s.Shine = blz("Frame", nil, s, 40, 40, "CENTER", 0, 0)
        s.BracketFrame = blz("Frame", nil, s, 40, 40, "TOPLEFT", 0, 0)
        s.BracketFrame.ClosedBracket = atex(s.BracketFrame, nil, "OVERLAY", "socket-red-closed", 52, 52)
        s.BracketFrame.ClosedBracket:SetColorTexture(1, 0.3, 0.3, 0.7)
        s.BracketFrame.ClosedBracket.points[1] = { point = "CENTER", rel = s, relPoint = "CENTER", x = 0, y = 0 }
        s.BracketFrame.OpenBracket = atex(s.BracketFrame, nil, "OVERLAY", "socket-red-open", 52, 52)
        s.BracketFrame.OpenBracket.shown = false
        s.scripts.OnClick = function() end
        cont.SocketFrames[i] = s
    end
    cont.ApplySocketsButton = blz("Button", nil, cont, 100, 22, "BOTTOM", 0, 4)

    ---------------------------------------------------------------------------------------------------------------
    -- Barber shop
    ---------------------------------------------------------------------------------------------------------------
    local barber = blz("Frame", "BarberShopFrame", UIParent, 1280, 720)
    barber.shown = false
    barber.TopBackgroundOverlay = atex(barber, nil, "BACKGROUND", "charactercreate-vignette-top", 1280, 200)
    barber.LeftBackgroundOverlay = atex(barber, nil, "BACKGROUND", "charactercreate-vignette-sides", 200, 720)
    barber.RightBackgroundOverlay = atex(barber, nil, "BACKGROUND", "charactercreate-vignette-sides", 200, 720)
    for i, k in ipairs({ "CancelButton", "ResetButton", "AcceptButton" }) do
        local b = blz("Button", nil, barber, 150, 30, "BOTTOM", (i - 2) * 160, 30)
        b.scripts.OnClick = function() end
        barber[k] = b
    end
end
"""

H = Harness({"Character": "Modules/Skins/Character.lua", "Maps": "Modules/Skins/Maps.lua"}, BLIZZARD)
# the shared button skins are a different harness's business: a stub that records what was asked of them loads before Bespoke.lua
H.sources["BtnStub"] = r"""
local _, FS = ...
FS.ButtonSkins = {
    Parts = function(b) return b.fsSkinned end,
    SkinCloseButton = function(b, o) b.fsSkinned = "x"; SKINNED[#SKINNED + 1] = "x" end,
    SkinTextButton = function(b, o) b.fsSkinned = "text"; SKINNED[#SKINNED + 1] = "text" end,
    SkinFrameClose = function(frame)
        local n = frame:GetName()
        for _, b in ipairs({ frame.CloseButton, n and _G[n .. "CloseButton"] }) do
            if b and not b.fsSkinned then FS.ButtonSkins.SkinCloseButton(b, { anchor = frame }) end
        end
    end,
}
"""
H.sources["Bespoke"] = (Path(__file__).resolve().parent.parent / "forever-stuwave/Modules/Skins/Bespoke.lua").read_text(encoding="utf-8")
H.extra_names = ["Character", "Maps", "BtnStub", "Bespoke"]
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); FlushTimers()"
LOAD_ALL = "Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'Character', 'Maps', 'BtnStub', 'Bespoke' })"


def window(body: str) -> str:
    return f"""
    {OPEN}
    {body}
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
"""


case("every window is built, wears a stuwave:// band over its held stock art, and keeps its close click", window("""
    local want = { CalendarFrame = 'calendar', AchievementFrame = 'achievements', DressUpFrame = 'dressing', TabardFrame = 'tabard',
        ItemSocketingFrame = 'sockets' }
    for name, title in pairs(want) do
        local win = _G[name]
        assert(win.fsBespokeSkin, name .. ' not built')
        assert(win.fsPanelTitle and win.fsPanelTitle.text == 'stuwave://' .. title, name .. ' band: ' .. tostring(win.fsPanelTitle and win.fsPanelTitle.text))
    end
    assert(BarberShopFrame.fsBespokeSkin, 'barber not built')
    assert(CalendarFrameTopLeftTexture.alpha == 0 and CalendarFrameBottomRightTexture.alpha == 0, 'calendar edge art kept')
    CalendarFrameTopLeftTexture:SetAlpha(1)
    assert(CalendarFrameTopLeftTexture.alpha == 0, 'hold did not survive a re-show')
    assert(AchievementFrame.Background.alpha == 0 and AchievementFrameMetalBorderLeft.alpha == 0 and AchievementFrameWaterMark.alpha == 0, 'achievement frame art kept')
    assert(DressUpFrame.NineSlice.alpha == 0 and DressUpFrame.Bg.alpha == 0 and DressUpFrame.Inset.alpha == 0, 'dress frame art kept')
    assert(DressUpFrame.TitleContainer.TitleText.alpha == 0, 'stock title kept')
    assert(DressUpFrame.CloseButton.scripts.OnClick, 'close click lost')
    assert(ItemSocketingFrame['ParchmentFrame-Top'].alpha == 0 and ItemSocketingFrame['GoldBorder-BottomRight'].alpha == 0, 'socket parchment kept')
"""))

case("calendar: weekday and month labels are mono, the month arrows are chevron keys that keep their clicks", window("""
    for i = 1, 7 do assert(_G['CalendarWeekday' .. i .. 'Name'].fontPath ~= 'stock.ttf', 'weekday ' .. i .. ' not mono') end
    assert(CalendarMonthName.fontPath ~= 'stock.ttf' and CalendarYearName.fontPath ~= 'stock.ttf', 'month or year not mono')
    assert(CalendarWeekday1Background.alpha == 0 and CalendarMonthBackground.alpha == 0 and CalendarYearBackground.alpha == 0, 'label plates kept')
    local S = FS.MapsSkin.state
    for _, b in ipairs({ CalendarPrevMonthButton, CalendarNextMonthButton }) do
        local k = S.keys[b]
        assert(k and #k.glyph == 5, 'no chevron key')
        assert(b.normalTex.alpha == 0, 'stock arrow kept')
        assert(b.scripts.OnClick, 'click lost')
    end
    assert(S.keys[CalendarPrevMonthButton].glyph[3].points[1].x ~= S.keys[CalendarNextMonthButton].glyph[3].points[1].x or
        S.keys[CalendarPrevMonthButton].glyph[1].points[1].x ~= S.keys[CalendarNextMonthButton].glyph[1].points[1].x, 'arrows point the same way')
"""))

case("calendar: 42 ink cells, today is cyan, the selected day violet with lock-on brackets, another month dim, hover cyan", window("""
    local S = FS.BespokeSkin.state
    local n = 0
    for _ in pairs(S.days) do n = n + 1 end
    assert(n == 42, 'cells ' .. n)
    local b12, b13, b14 = CalendarDayButton12, CalendarDayButton13, CalendarDayButton14
    local r12 = S.days[b12]
    assert(b12.normalTex.alpha == 0 and b12.highlightTex.alpha == 0, 'stock cell art kept')
    assert(CalendarDayButton12EventBackgroundTexture.alpha == 0, 'event backdrop kept')
    assert(CalendarDayButton12EventTexture.alpha ~= 0 and CalendarDayButton12PendingInviteTexture.alpha ~= 0, 'event picture or invite glow held')
    assert(r12.plate.ring.alpha ~= 0 and r12.plate.fill.alpha ~= 0, 'no plate')
    -- an idle cell: dim violet edge
    local ring = S.days[b13].plate.ring
    assert(ring.vertex[3] > 0.4 and ring.vertex[1] < 0.4, 'idle edge not dim violet')
    -- today
    CalendarTodayFrame:SetParent(b12); CalendarTodayFrame:Show()
    assert(r12.plate.ring.vertex[2] > 0.8 and r12.plate.ring.vertex[1] < 0.3, 'today edge not cyan')
    assert(r12.plate.ring2.shown ~= false, 'today edge is one pixel')
    assert(r12.chip.shown ~= false, 'no date chip on today')
    assert(CalendarDayButton12DateFrameDate.textColor[1] < 0.3, 'date not dark on the chip')
    CalendarTodayFrame:SetParent(b13)
    assert(r12.chip.shown == false, 'chip stayed on the old today')
    assert(S.days[b13].chip.shown ~= false, 'chip did not move')
    -- selected
    b14:LockHighlight()
    local r14 = S.days[b14]
    assert(r14.plate.ring.vertex[1] > 0.6 and r14.plate.ring.vertex[1] < 0.7, 'selected edge not violet')
    assert(r14.reticle.tlH.shown ~= false, 'no lock-on on the selected day')
    b14:UnlockHighlight()
    assert(r14.reticle.tlH.shown == false, 'lock-on stayed')
    -- another month
    local b3 = CalendarDayButton3
    CalendarDayButton3DarkFrame:Show()
    assert(S.days[b3].plate.ring.vertex[4] < 0.6, 'other month not dim')
    -- hover
    local b20 = CalendarDayButton20
    b20:RunScript('OnEnter')
    assert(S.days[b20].plate.ring.vertex[2] > 0.8, 'hover not cyan')
    b20:RunScript('OnLeave')
    assert(b20.scripts.OnClick and b20.scripts.OnEnter, 'script lost')
"""))

case("calendar: event lines keep their own colour in mono, and the day popups wear the panel chrome", window("""
    local t = CalendarDayButton12EventButton1Text1
    assert(t.fontPath ~= 'stock.ttf', 'event title not mono')
    assert(t.textColor[1] == 1 and t.textColor[2] == 0.82, 'event colour changed')
    for name, title in pairs({ CalendarViewHolidayFrame = 'day', CalendarViewRaidFrame = 'day', CalendarViewEventFrame = 'day',
        CalendarCreateEventFrame = 'create', CalendarEventPickerFrame = 'picker' }) do
        local f = _G[name]
        assert(f.fsBespokeSkin, name .. ' not skinned')
        assert(f.fsPanelTitle.text == 'stuwave://' .. title, name .. ' title')
        assert(f.Border.alpha == 0 and f.Header.alpha ~= 0, name .. ' border kept or header lost')
    end
    assert(CalendarViewEventCloseButton.fsSkinned == 'x', 'popup close not skinned')
    assert(CalendarCloseButton.fsSkinned == 'x', 'calendar close not skinned')
"""))

case("achievements: header, tabs frame and pages are held, the category list is a violet box with one row each", window("""
    local ach = AchievementFrame
    assert(ach.Header.Left.alpha == 0 and ach.Header.PointBorder.alpha == 0, 'header art kept')
    assert(ach.Header.Title.fontPath ~= 'stock.ttf' and ach.Header.Points.textColor[1] > 0.9 and ach.Header.Points.textColor[3] < 0.5, 'header text')
    assert(ach.HeaderDetails.TopTileStreaks.alpha == 0, 'streaks kept')
    assert(ach.Categories.NineSlice.alpha == 0, 'category border kept')
    assert(AchievementFrameAchievements.Background.alpha == 0 and AchievementFrameSummary.Background.alpha == 0, 'page backgrounds kept')
    assert(AchievementFrameStatsBG.regions[1].alpha == 0 or AchievementFrameStatsBG.alpha == 0, 'stats background kept')
    local spc = ach.HeaderDetails.Filters.SearchBox.SearchPreviewContainer
    assert(spc.Background.alpha == 0 and spc.BorderAnchor.alpha == 0, 'search preview art kept')
    assert(ach.SearchResults.regions[1].alpha == 0, 'search results art kept')
"""))

case("achievements: category rows are skinned as the box is repainted, selected is cyan, hover cyan, text is mono", window("""
    local S = FS.BespokeSkin.state
    local rows = {}
    for i = 1, 3 do rows[i] = CATBOX:Add() end
    for i, r in ipairs(rows) do
        local rec = S.rows[r]
        assert(rec and rec.slab, 'row ' .. i .. ' not skinned')
        assert(r.Button.Background.alpha == 0 and r.Button.highlightTex.alpha == 0, 'row art kept')
        assert(r.Button.Label.fontPath ~= 'stock.ttf', 'label not mono')
        assert(r.Button.scripts.OnClick, 'click lost')
    end
    local ring = function(i) return S.rows[rows[i]].slab.plate.ring.vertex end
    rows[2]:UpdateSelectionState(true)
    assert(ring(2)[2] > 0.8 and ring(2)[1] < 0.3, 'selected not cyan')
    rows[1].Button:RunScript('OnEnter')
    assert(ring(1)[2] > 0.8, 'hover not cyan')
    rows[1].Button:RunScript('OnLeave')
    assert(ring(1)[1] < 0.5 and ring(1)[2] < 0.3, 'hover stayed')
    rows[2]:UpdateSelectionState(false)
    assert(ring(2)[2] < 0.3, 'selection stayed')
"""))

case("achievements: a row holds its parchment, wears amber when earned and cyan lock-on brackets when selected, and lightens dark text for good", window("""
    local S = FS.BespokeSkin.state
    local r = ACHBOX:Add()
    local rec = S.rows[r]
    assert(rec and rec.slab and rec.iconSlab, 'row not skinned')
    local ring = rec.slab.plate.ring
    assert(r.Background.alpha == 0 and r.TitleBar.alpha == 0 and r.TopLeftTsunami.alpha == 0 and r.Glow.alpha == 0, 'parchment kept')
    assert(r.NineSlice.alpha == 0 and r.Highlight.alpha == 0, 'backdrop or glow kept')
    assert(r.Icon.frame.alpha == 0 and r.Icon.bling.alpha == 0 and r.Icon.texture.alpha ~= 0, 'icon ring kept or picture held')
    assert(r.Shield.Points.fontPath ~= 'stock.ttf', 'points not mono')
    assert(r.Label.fontPath ~= 'stock.ttf' and r.Label.textColor[1] == 1, 'label not mono or recoloured')
    assert(r.Description.textColor[1] > 0.5, 'dark description not lightened')
    r:Saturate()
    assert(r.Description.textColor[1] > 0.5, 'earned description went dark')
    assert(ring.vertex[1] > 0.9 and ring.vertex[2] > 0.6 and ring.vertex[3] < 0.4, 'earned not amber')
    r:SetSelected(true)
    assert(ring.vertex[2] > 0.8 and ring.vertex[1] < 0.3, 'selected not cyan')
    assert(rec.slab.reticle.tlH.shown ~= false, 'selected row not caught in lock-on')
    r:SetSelected(false); r:Desaturate()
    assert(rec.slab.reticle.tlH.shown == false, 'lock-on stayed')
    assert(ring.vertex[1] > 0.6 and ring.vertex[1] < 0.7 and ring.vertex[3] > 0.9, 'idle edge not violet')
    r.h = 120; r:RunScript('OnSizeChanged')
    assert(rec.slab.plate.h == 120 * 1.2 or rec.slab.plate.h == 144, 'the plate did not follow the new height: ' .. tostring(rec.slab.plate.h))
    assert(r.scripts.OnClick and r.scripts.OnEnter, 'script lost')
    -- a second row, and recycling: the box sweeps the new one when it updates
    local r2 = ACHBOX:Add()
    assert(S.rows[r2], 'new row not skinned')
    ACHBOX:Update()
    assert(S.rows[r] == rec, 'row skinned twice')
"""))

case("achievements: criteria text is lightened and stays light, summary and statistics rows are plated", window("""
    local S = FS.BespokeSkin.state
    assert(CRIT.textColor[1] > 0.5, 'criteria text dark')
    AchievementObjectives_DisplayCriteria()
    assert(CRIT.textColor[1] > 0.5, 'criteria text dark again after a refresh')
    for i = 1, 4 do
        local r = _G['AchievementFrameSummaryAchievement' .. i]
        assert(S.rows[r] and r.Background.alpha == 0 and r.Description.textColor[1] > 0.5, 'summary ' .. i)
    end
    local row = AchievementFrameStats.ScrollBox:Add()
    assert(S.rows[row] and row.Background.alpha == 0 and row.Title.textColor[1] > 0.5 and row.Title.fontPath ~= 'stock.ttf', 'stat row')
"""))

case("dressing room: the model backdrop is held, the scene sits in a violet box, the keys are cut keys with their clicks", window("""
    local S = FS.MapsSkin.state
    local win = DressUpFrame
    assert(win.ModelBackground.alpha == 0, 'model backdrop kept')
    local box = FS.BespokeSkin.state.cards[win.ModelScene]
    assert(box and box.plate.ring.vertex[3] > 0.9, 'no violet box on the scene')
    for _, b in ipairs({ win.ToggleCustomSetDetailsButton, win.MaximizeMinimizeFrame.MinimizeButton, win.MaximizeMinimizeFrame.MaximizeButton }) do
        local k = S.keys[b]
        assert(k and k.plate.ring.alpha ~= 0, 'no key')
        assert(b.scripts.OnClick, 'click lost')
    end
    assert(win.ToggleCustomSetDetailsButton.normalTex.alpha == 0, 'stock list icon kept')
    local det = win.CustomSetDetailsPanel
    assert(det.ClassBackground.alpha == 0 and det.Sideframe.alpha == 0, 'details art kept')
    assert(det.BlackBackground.alpha ~= 0, 'details black backdrop held')
"""))

case("tabard: the emblem is never held or hidden, the outer frame and label bars are, the pickers are plates with chevron keys", window("""
    local S = FS.MapsSkin.state
    for _, n in ipairs({ 'TopLeft', 'TopRight', 'BottomLeft', 'BottomRight' }) do
        local e = _G['TabardFrameEmblem' .. n]
        assert(e.alpha == 1 and e.shown ~= false, 'emblem ' .. n .. ' touched')
        e:SetAlpha(0.5)
        assert(e.alpha == 0.5, 'emblem ' .. n .. ' is held')
    end
    assert(TabardFrameOuterFrameTopLeft.alpha == 0 and TabardFramePortrait.alpha == 0, 'outer frame kept')
    assert(TabardFrameCustomizationBorder.alpha == 0, 'picker border kept')
    assert(TabardFrameNameText.fontPath ~= 'stock.ttf', 'name not mono')
    for i = 1, 5 do
        local n = 'TabardFrameCustomization' .. i
        assert(_G[n .. 'Left'].alpha == 0 and _G[n .. 'Middle'].alpha == 0 and _G[n .. 'Right'].alpha == 0, 'label bar ' .. i .. ' kept')
        assert(_G[n .. 'Text'].fontPath ~= 'stock.ttf', 'picker text ' .. i)
        for _, side in ipairs({ 'LeftButton', 'RightButton' }) do
            local b = _G[n .. side]
            assert(S.keys[b] and #S.keys[b].glyph == 5 and b.normalTex.alpha == 0 and b.scripts.OnClick, 'picker key ' .. i .. side)
        end
    end
    for _, n in ipairs({ 'TabardCharacterModelRotateLeftButton', 'TabardCharacterModelRotateRightButton' }) do
        assert(S.keys[_G[n]] and _G[n].scripts.OnClick, n)
    end
    assert(TabardFrameCostFrame.NineSlice.alpha == 0 and FS.BespokeSkin.state.cards[TabardFrameCostFrame], 'cost box')
    assert(TabardFrameMoneyInset.alpha == 0 and TabardFrameMoneyBg.alpha == 0, 'money plate art kept')
"""))

case("gem sockets: parchment, border and filigree are held; the gem, its colour and the brackets stay", window("""
    local win = ItemSocketingFrame
    for _, k in ipairs({ 'ParchmentFrame-Top', 'ParchmentFrame-Left', 'SocketFrame-Left', 'ButtonFrame-Right', 'ButtonBorder-Mid', 'GoldBorder-Top',
        'BackgroundColor', 'BackgroundHighlight', 'BorderShadow-Top', 'BottomLeftNub' }) do
        assert(win[k].alpha == 0, k .. ' kept')
    end
    for i, s in ipairs(win.SocketingContainer.SocketFrames) do
        assert(s.RightFiligree.alpha == 0 and s.LeftFiligree.alpha == 0, 'filigree ' .. i .. ' kept')
        assert(s.Icon.alpha ~= 0 and s.Background.alpha ~= 0, 'gem or colour of socket ' .. i .. ' held')
        assert(s.BracketFrame.ClosedBracket.alpha ~= 0 and s.BracketFrame.OpenBracket.alpha ~= 0, 'brackets held')
        local slab = FS.BespokeSkin.state.cards[s]
        assert(slab and slab.plate.ring.vertex[3] > 0.9, 'no violet well behind socket ' .. i)
        assert(s.scripts.OnClick, 'click lost')
    end
"""))

case("barber shop: the vignettes are tinted, Cancel Reset and Accept are the shared text buttons", window("""
    local v = BarberShopFrame.TopBackgroundOverlay
    assert(v.vertex and v.vertex[3] > v.vertex[1] and v.vertex[1] < 0.5, 'vignette not tinted violet')
    assert(BarberShopFrame.CancelButton.fsSkinned == 'text' and BarberShopFrame.AcceptButton.fsSkinned == 'text' and BarberShopFrame.ResetButton.fsSkinned == 'text', 'buttons not skinned')
    assert(BarberShopFrame.AcceptButton.scripts.OnClick, 'click lost')
"""))

case("a second pass builds nothing twice", window("""
    local S = FS.BespokeSkin.state
    local function count(f)
        local n = 1 + #f.regions
        for _, c in ipairs(f.children) do n = n + count(c) end
        return n
    end
    local before = count(UIParent)
    FS.BespokeSkin.Build(); FlushTimers()
    assert(count(UIParent) == before, 'a second build created ' .. (count(UIParent) - before) .. ' objects')
"""))

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    {LOAD_ALL}
    assert(not CalendarFrame.fsBespokeSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(CalendarFrame.fsBespokeSkin and TabardFrame.fsBespokeSkin, 'not built when combat ended')
""")

SCENES = {
    "calendar": f"Fire('PLAYER_ENTERING_WORLD'); FS.Theme.SkinPanel(WorldMapFrame, {{ title = 'map' }}); CalendarFrame:Show(); CalendarTodayFrame:SetParent(CalendarDayButton12); CalendarTodayFrame:Show(); CalendarDayButton18:LockHighlight(); CalendarDayButton3DarkFrame:Show(); CalendarDayButton5.scripts.OnEnter(); FlushTimers(); return DumpOps({{ CalendarFrame }})",
    "achievements": f"Fire('PLAYER_ENTERING_WORLD'); AchievementFrame:Show(); for i = 1, 3 do CATBOX:Add() end; CATBOX.frames[1]:UpdateSelectionState(true); local a = ACHBOX:Add(); ACHBOX:Add(); a:Saturate(); ACHBOX.frames[2]:SetSelected(true); ACHBOX.frames[2]:Desaturate(); FlushTimers(); return DumpOps({{ AchievementFrame }})",
    "dressing": f"Fire('PLAYER_ENTERING_WORLD'); DressUpFrame:Show(); FlushTimers(); return DumpOps({{ DressUpFrame }})",
    "tabard": f"Fire('PLAYER_ENTERING_WORLD'); TabardFrame:Show(); FlushTimers(); return DumpOps({{ TabardFrame }})",
    "sockets": f"Fire('PLAYER_ENTERING_WORLD'); ItemSocketingFrame:Show(); FlushTimers(); return DumpOps({{ ItemSocketingFrame }})",
}

if __name__ == "__main__":
    raise SystemExit(H.main("bespoke skin", SCENES))
