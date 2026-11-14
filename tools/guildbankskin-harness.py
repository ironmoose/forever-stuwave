#!/usr/bin/env python3
"""Runs the real Modules/Skins/GuildBank.lua (with OddsEnds.lua, GroupKit.lua and Commerce.lua) headless against a mock guild bank,
its tab name pop up and the guild control window (tools/charskin_support.py).

Pinned: the guild bank wears the panel skin with its stock marble, corner and tab name art held and ringed name chips that follow
the stock title and limit art; the 98 item slots keep their icons, counts and search overlay under the cut plate and ring of the
other item windows, each column is a ring card; the eight tab keys on the right hold their frames and light for the chosen tab;
the money box, the log and the tab info pages are ringed with their text in mono; the icon picker pop up is a dialog with its
border art held and a ringed icon key; the guild control window wears the panel skin, its rank rows, bank tab rows and sections
are cards, its square keys keep their icons; no script or attribute is written on a Blizzard widget, a frame a client does not
have is skipped, and nothing is built in combat. Run `python3 tools/guildbankskin-harness.py [--png debug/odds]`. The mock is
NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local build = BuildBlizzard
local STOCK = "Interface\\stock\\art"

function Ours(frame)
    local n = 0
    for _, r in ipairs(frame.regions) do
        if r.kind == "Texture" and r.path ~= STOCK then n = n + 1 end
    end
    return n
end

local function label(parent, name, text, size, color, point, x, y)
    local f = fstring(parent, name, text, size, color)
    f.points[1] = { point = point or "TOPLEFT", rel = parent, relPoint = point or "TOPLEFT", x = x or 0, y = y or 0 }
    return f
end

local function panelButton(parent, name, text, point, x, y)
    local b = blz("Button", name, parent, 100, 21, point, x, y)
    b.Left = tex(b, nil, "BACKGROUND"); b.Middle = tex(b, nil, "BACKGROUND"); b.Right = tex(b, nil, "BACKGROUND")
    b.fs = fstring(b, nil, text, 11, { 1, 1, 1, 1 })
    b.fs.points[1] = { point = "CENTER", rel = b, relPoint = "CENTER", x = 0, y = 0 }
    b.GetFontString = function(self) return self.fs end
    b.scripts.OnClick = function() end
    return b
end

local function money(parent, name, point, x, y)
    local m = blz("Frame", name, parent, 120, 18, point, x, y)
    for _, c in ipairs({ "Gold", "Silver", "Copper" }) do
        local b = blz("Button", name .. c .. "Button", m, 30, 18, "LEFT", 0, 0)
        fstring(b, name .. c .. "ButtonText", "1", 12, { 1, 1, 1, 1 })
    end
    return m
end

function BuildBlizzard()
    build()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^GuildBank") or k:find("^GuildItem") or k:find("^GuildControl") or k:find("^RankChange")) then _G[k] = nil end
    end
    SetItemButtonQuality = function(button, q) button.q = q end

    -- the guild bank, as Blizzard_GuildBankUI.xml (Mainline, the tree the 16001 dump matches) builds it: 750 x 428, BasicFrameTemplate
    local win = blz("Frame", "GuildBankFrame", UIParent, 750, 428, "TOPLEFT", 60, -100)
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.TopTileStreaks = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 750, 428)
    win.TitleContainer = blz("Frame", nil, win, 700, 20)
    fstring(win.TitleContainer, "GuildBankFrameTitleText", "Guild Bank")
    win.CloseButton = blz("Button", "GuildBankFrameCloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(win.CloseButton, nil, "BACKGROUND")
    for _, k in ipairs({ "TabTitleBG", "TabTitleBGLeft", "TabTitleBGRight", "TabLimitBG", "TabLimitBGLeft", "TabLimitBGRight",
        "Portrait", "RedMarbleBG", "BlackBG" }) do win[k] = tex(win, nil, "BACKGROUND") end
    win.TabTitleBG.w, win.TabTitleBG.h = 120, 18
    win.TabTitleBG.points[1] = { point = "TOP", rel = win, relPoint = "TOP", x = 0, y = -30 }
    win.TabTitleBGLeft.w, win.TabTitleBGLeft.h = 8, 18
    win.TabTitleBGLeft.points[1] = { point = "RIGHT", rel = win.TabTitleBG, relPoint = "LEFT", x = 0, y = 0 }
    win.TabTitleBGRight.w, win.TabTitleBGRight.h = 8, 18
    win.TabTitleBGRight.points[1] = { point = "LEFT", rel = win.TabTitleBG, relPoint = "RIGHT", x = 0, y = 0 }
    win.TabLimitBG.w, win.TabLimitBG.h = 260, 18
    win.TabLimitBG.points[1] = { point = "TOP", rel = win, relPoint = "TOP", x = 6, y = -378 }
    win.TabLimitBGLeft.w, win.TabLimitBGLeft.h = 8, 18
    win.TabLimitBGLeft.points[1] = { point = "RIGHT", rel = win.TabLimitBG, relPoint = "LEFT", x = 0, y = 0 }
    win.TabLimitBGRight.w, win.TabLimitBGRight.h = 8, 18
    win.TabLimitBGRight.points[1] = { point = "LEFT", rel = win.TabLimitBG, relPoint = "RIGHT", x = 0, y = 0 }
    for _, n in ipairs({ "BottomLeftOuter", "TopRightInner", "LeftOuter", "TopOuter" }) do tex(win, "GuildBankFrame" .. n, "BORDER") end
    win.TabTitle = label(win, nil, "Weapons", 12, { 1, 0.82, 0, 1 }, "TOP", 0, -33)
    win.LimitLabel = label(win, nil, "Remaining withdrawals: 25", 11, { 1, 0.82, 0, 1 }, "TOP", 6, -387)
    win.ErrorMessage = label(win, nil, "No tabs", 12, { 1, 0.82, 0, 1 }, "TOP", 0, -216)
    win.ErrorMessage.shown = false
    local emblem = blz("Frame", nil, win, 40, 40, "TOPLEFT", 7, -5)
    emblem.Left = tex(emblem, nil, "ARTWORK"); emblem.Right = tex(emblem, nil, "ARTWORK")
    win.Emblem = emblem

    -- 7 columns of 14 item buttons
    win.Columns = {}
    for c = 1, 7 do
        local col = blz("Frame", nil, win, 100, 311, "TOPLEFT", 18 + (c - 1) * 103, -59)
        col.Background = tex(col, nil, "BACKGROUND")
        col.Buttons = {}
        for i = 1, 14 do
            local b = blz("Button", nil, col, 37, 37, "TOPLEFT", i <= 7 and 7 or 56, -3 - ((i - 1) % 7) * 44)
            b.icon = tex(b, nil, "BORDER"); b.icon.path = "Interface\\Icons\\inv_misc_" .. i
            b.NormalTexture = tex(b, nil, "ARTWORK")
            b.normalTex = b.NormalTexture
            b.IconBorder = tex(b, nil, "OVERLAY")
            b.IconOverlay = tex(b, nil, "OVERLAY")
            b.SearchOverlay = tex(b, nil, "OVERLAY"); b.SearchOverlay.shown = false
            b.Count = label(b, nil, "", 12, { 1, 1, 1, 1 }, "BOTTOMRIGHT", -5, 2)
            b.highlightTex = tex(b, nil, "HIGHLIGHT")
            b.scripts.OnClick = function() end; b.scripts.OnEnter = function() end; b.scripts.OnLeave = function() end
            b.scripts.OnDragStart = function() end
            b.SetItemButtonQuality = function(self, q) self.q = q end
            col["Button" .. i] = b
            col.Buttons[i] = b
        end
        win.Columns[c] = col
        win["Column" .. c] = col
    end

    -- money
    win.MoneyFrameBG = blz("Frame", nil, win, 740, 24, "BOTTOMLEFT", 1, 25)
    tex(win.MoneyFrameBG, nil, "BACKGROUND"); tex(win.MoneyFrameBG, nil, "BORDER")
    win.MoneyFrameBG.LimitLabel = label(win.MoneyFrameBG, "GuildBankMoneyLimitLabel", "Available:", 11, { 1, 0.82, 0, 1 }, "BOTTOMLEFT", 8, 6)
    win.MoneyFrameBG.UnlimitedLabel = label(win.MoneyFrameBG, "GuildBankMoneyUnlimitedLabel", "Unlimited", 11, { 1, 1, 1, 1 }, "BOTTOMLEFT", 80, 6)
    win.MoneyFrame = money(win, "GuildBankMoneyFrame", "BOTTOMRIGHT", -2, 6)
    win.WithdrawMoneyFrame = money(win, "GuildBankWithdrawMoneyFrame", "BOTTOMLEFT", 100, 6)
    win.DepositButton = panelButton(win, nil, "Deposit", "BOTTOMRIGHT", -8, 30)
    win.WithdrawButton = panelButton(win, nil, "Withdraw", "BOTTOMRIGHT", -111, 30)

    -- the four bottom tabs and the eight bank tabs
    for i, text in ipairs({ "Bank", "Log", "Money Log", "Tab Info" }) do
        local t = blz("Button", "GuildBankFrameTab" .. i, win, 90, 32, "BOTTOMLEFT", 7 + (i - 1) * 92, -30)
        t.Left = tex(t, nil, "BACKGROUND"); t.Middle = tex(t, nil, "BACKGROUND"); t.Right = tex(t, nil, "BACKGROUND")
        t.LeftActive = tex(t, nil, "BACKGROUND"); t.MiddleActive = tex(t, nil, "BACKGROUND"); t.RightActive = tex(t, nil, "BACKGROUND")
        t.Text = fstring(t, nil, text, 11, { 1, 0.82, 0, 1 })
        t.GetFontString = function(self) return self.Text end
        t.scripts.OnClick = function() end
    end
    win.BankTabs = {}
    for i = 1, 8 do
        local tab = blz("Frame", "GuildBankTab" .. i, win, 42, 50, "TOPLEFT", 749, -17 - (i - 1) * 50)
        tex(tab, nil, "BACKGROUND")
        local b = blz("CheckButton", nil, tab, 36, 34, "TOPLEFT", 2, -8)
        b.IconTexture = tex(b, nil, "BORDER"); b.IconTexture.path = "Interface\\Icons\\inv_misc_bag_" .. i
        b.Count = label(b, nil, "", 12, { 1, 1, 1, 1 }, "BOTTOMRIGHT", -5, 2); b.Count.shown = false
        b.SearchOverlay = tex(b, nil, "ARTWORK"); b.SearchOverlay.shown = false
        b.NormalTexture = tex(b, nil, "ARTWORK"); b.normalTex = b.NormalTexture
        b.pushedTex = tex(b, nil, "ARTWORK"); b.highlightTex = tex(b, nil, "HIGHLIGHT"); b.checkedTex = tex(b, nil, "ARTWORK")
        b.scripts.OnClick = function() end; b.scripts.OnEnter = function() end; b.scripts.OnLeave = function() end
        tab.Button = b
        win.BankTabs[i] = tab
        win["BankTab" .. i] = tab
    end
    win.BankTabs[1].Button:SetChecked(true); win.BankTabs[1].Button:Disable()

    -- buy a tab
    local buy = blz("Frame", nil, win, 20, 20, "TOP", 0, -194)
    buy.shown = false
    buy.TabText = label(buy, nil, "Buy a tab", 12, { 1, 1, 1, 1 }, "TOP", 0, 0)
    buy.PurchasedText = label(buy, nil, "Purchased: 1", 11, { 1, 1, 1, 1 }, "TOP", 0, -16)
    label(buy, "GuildBankFrameTabCost", "Cost:", 12, { 1, 0.82, 0, 1 }, "TOP", -93, -38)
    money(buy, "GuildBankFrameTabCostMoneyFrame", "LEFT", 10, 0)
    buy.PurchaseButton = panelButton(buy, nil, "Purchase", "LEFT", 130, 0)
    win.BuyInfo = buy

    -- the log
    local log = blz("Frame", nil, win, 10, 10, "TOPLEFT", 0, 0)
    log.shown = false
    log.MessageFrame = blz("ScrollingMessageFrame", "GuildBankMessageFrame", log, 688, 304, "TOPLEFT", 24, -64)
    log.MessageFrame.fontPath, log.MessageFrame.size = "stock.ttf", 12
    log.ScrollBar = blz("Frame", nil, log, 12, 300, "TOPLEFT", 718, -64)
    win.Log = log

    -- tab info
    local info = blz("Frame", "GuildBankInfo", win, 10, 10, "TOPLEFT", 32, -74)
    info.shown = false
    info.SaveButton = panelButton(info, "GuildBankInfoSaveButton", "Save Changes", "BOTTOMLEFT", 20, 31)
    info.SaveButton.shown = false
    info.ScrollFrame = blz("ScrollFrame", "GuildBankInfoScrollFrame", info, 691, 306, "TOPLEFT", -9, 12)
    info.ScrollFrame.ScrollBar = blz("Frame", nil, info.ScrollFrame, 12, 300, "TOPRIGHT", 4, -2)
    info.EditBox = blz("EditBox", "GuildBankTabInfoEditBox", info.ScrollFrame, 690, 218, "TOPLEFT", 0, 0)
    info.EditBox.fontPath, info.EditBox.size = "stock.ttf", 12
    info.ScrollFrame.EditBox = info.EditBox
    win.Info = info

    -- the search box
    local search = blz("EditBox", "GuildItemSearchBox", win, 130, 20, "TOPRIGHT", -15, -36)
    search.fontPath, search.size = "stock.ttf", 12

    -- the tab name and icon pop up (IconSelectorPopupFrameTemplate)
    local pop = blz("Frame", "GuildBankPopupFrame", win, 525, 495, "TOPLEFT", 820, -90)
    pop.shown = false
    pop.BG = tex(pop, nil, "BACKGROUND")
    local bb = blz("Frame", nil, pop, 525, 495, "TOPLEFT", 0, 0)
    pop.BorderBox = bb
    for _, k in ipairs({ "TopLeftCorner", "TopRightCorner", "TopEdge", "LeftEdge" }) do tex(bb, nil, "BORDER") end
    bb.EditBoxHeaderText = label(bb, nil, "Tab name", 11, { 1, 1, 1, 1 }, "TOPLEFT", 24, -21)
    bb.IconSelectionText = label(bb, nil, "Choose an icon", 11, { 1, 1, 1, 1 }, "TOPLEFT", 24, -79)
    bb.CancelButton = panelButton(bb, nil, "Cancel", "BOTTOMRIGHT", -11, 13)
    bb.OkayButton = panelButton(bb, nil, "Okay", "BOTTOMRIGHT", -115, 13)
    local area = blz("Frame", nil, bb, 275, 45, "TOPRIGHT", -13, -13)
    bb.SelectedIconArea = area
    local sib = blz("Button", nil, area, 36, 36, "TOPRIGHT", -4, -3)
    sib.Back = tex(sib, nil, "BACKGROUND")
    sib.Icon = tex(sib, nil, "ARTWORK"); sib.Icon.path = "Interface\\Icons\\inv_misc_bag_1"
    sib.normalTex = sib.Icon
    sib.Highlight = tex(sib, nil, "HIGHLIGHT"); sib.highlightTex = sib.Highlight
    sib.scripts.OnClick = function() end; sib.scripts.OnEnter = function() end; sib.scripts.OnLeave = function() end
    area.SelectedIconButton = sib
    local st = blz("Frame", nil, area, 200, 30, "TOPRIGHT", -46, -10)
    st.SelectedIconHeader = label(st, nil, "Current icon", 10, { 1, 0.82, 0, 1 }, "TOPRIGHT", 0, 0)
    st.SelectedIconDescription = label(st, nil, "Click to change", 10, { 1, 1, 1, 1 }, "TOPRIGHT", 0, -14)
    st.SelectedIconDescription.SetFontObject = function(self) self.fontPath = "stock.ttf" end
    area.SelectedIconText = st
    local eb = blz("EditBox", nil, bb, 182, 20, "TOPLEFT", 29, -35)
    eb.fontPath, eb.size = "stock.ttf", 12
    eb.IconSelectorPopupNameLeft = tex(eb, nil, "BACKGROUND")
    eb.IconSelectorPopupNameMiddle = tex(eb, nil, "BACKGROUND")
    eb.IconSelectorPopupNameRight = tex(eb, nil, "BACKGROUND")
    bb.IconSelectorEditBox = eb
    pop.IconSelector = blz("Frame", nil, pop, 480, 300, "TOPLEFT", 20, -110)

    -- the guild control window (Blizzard_GuildControlUI.xml): a TranslucentFrameTemplate with named art and a Hbar
    local gc = blz("Frame", "GuildControlUI", UIParent, 340, 460, "TOPLEFT", 60, -120)
    gc.shown = false
    for _, n in ipairs({ "Bg", "TopBg", "TopBorder", "BottomBorder", "LeftBorder", "RightBorder", "TopLeftCorner", "BottomRightCorner" }) do
        tex(gc, "GuildControlUI" .. n, "BACKGROUND")
    end
    gc.title = label(gc, "GuildControlUITitle", "Guild Control", 12, { 1, 0.82, 0, 1 }, "TOP", 0, -10)
    local hbar = blz("Frame", "GuildControlUIHbar", gc, 340, 24, "TOPLEFT", 0, -40)
    for _, n in ipairs({ "Bg", "TopBorder", "BottomBorder" }) do tex(hbar, "GuildControlUIHbar" .. n, "BACKGROUND") end
    local gclose = blz("Button", "GuildControlUICloseButton", gc, 15, 15, "TOPRIGHT", -6, -4)
    tex(gclose, nil, "BACKGROUND")
    gc.dropdown = blz("Button", "GuildControlUINavigationDropdown", gc, 160, 24, "TOPLEFT", 90, -44)
    local order = blz("Frame", "GuildControlUIRankOrderFrame", gc, 320, 300, "TOPLEFT", 10, -80)
    order.shown = false
    gc.orderFrame = order
    function NewRankRow(i)
        local row = blz("Frame", "GuildControlUIRankOrderFrameRank" .. i, order, 300, 30, "TOPLEFT", 0, -(i - 1) * 34)
        row.rankLabel = label(row, nil, "Rank " .. i, 12, { 1, 0.82, 0, 1 }, "LEFT", 4, 0)
        row.nameBox = blz("EditBox", nil, row, 120, 20, "LEFT", 60, 0)
        row.nameBox.fontPath, row.nameBox.size = "stock.ttf", 12
        for _, spec in ipairs({ { "deleteButton", "DeleteButton", 0 }, { "downButton", "ShiftDownButton", -44 }, { "upButton", "ShiftUpButton", -88 } }) do
            local b = blz("Button", row:GetName() .. spec[2], row, 24, 24, "RIGHT", spec[3], 0)
            b.NormalTexture = tex(b, nil, "ARTWORK"); b.normalTex = b.NormalTexture
            b.highlightTex = tex(b, nil, "HIGHLIGHT"); b.pushedTex = tex(b, nil, "ARTWORK")
            b.icon = tex(b, row:GetName() .. spec[2] .. "Icon", "OVERLAY"); b.icon.w, b.icon.h = 14, 14
            b.scripts.OnClick = function() end; b.scripts.OnEnter = function() end; b.scripts.OnLeave = function() end
            row[spec[1]] = b
        end
        return row
    end
    NewRankRow(1); NewRankRow(2)
    order.newButton = panelButton(order, nil, "Add Rank", "BOTTOMLEFT", 0, 0)
    function GuildControlUI_RankOrder_Update(self) end

    local bank = blz("Frame", "GuildControlUIRankBankFrame", gc, 320, 340, "TOPLEFT", 10, -80)
    bank.shown = false
    gc.bankTabFrame = bank
    bank.dropdown = blz("Button", "GuildControlUIRankBankFrameRankDropdown", bank, 160, 24, "TOPLEFT", 120, 0)
    bank.inset = blz("Frame", "GuildControlUIRankBankFrameInset", bank, 300, 280, "TOPLEFT", 0, -40)
    bank.inset.NineSlice = blz("Frame", nil, bank.inset, 300, 280)
    bank.inset.Bg = tex(bank.inset, nil, "BACKGROUND")
    bank.scrollFrame = blz("ScrollFrame", "GuildControlUIRankBankFrameInsetScrollFrame", bank.inset, 270, 270, "TOPLEFT", 2, -2)
    local child = blz("Frame", nil, bank.scrollFrame, 268, 600, "TOPLEFT", 0, 0)
    bank.scrollFrame.child = child
    bank.scrollFrame.GetScrollChild = function(self) return self.child end
    function NewBankTabRow(i)
        local row = blz("Frame", "GuildControlBankTab" .. i, child, 268, 74, "TOPLEFT", 0, -(i - 1) * 76)
        tex(row, "GuildControlBankTab" .. i .. "Bg", "BACKGROUND")
        local owned = blz("Frame", "GuildControlBankTab" .. i .. "Owned", row, 268, 74, "TOPLEFT", 0, 0)
        owned.tabIcon = tex(owned, nil, "OVERLAY"); owned.tabIcon.path = "Interface\\Icons\\inv_misc_bag_" .. i
        owned.tabName = label(owned, nil, "Tab " .. i, 11, { 1, 0.82, 0, 1 }, "TOPLEFT", 28, -6)
        owned.viewCB = blz("CheckButton", nil, owned, 20, 20, "TOPRIGHT", -95, -3)
        owned.viewCB.text = label(owned.viewCB, nil, "View Tab", 10, { 1, 1, 1, 1 }, "LEFT", 22, 0)
        owned.editBox = blz("EditBox", nil, owned, 80, 20, "BOTTOMLEFT", 15, 3)
        owned.editBox.fontPath, owned.editBox.size = "stock.ttf", 12
        label(owned.editBox, "GuildControlBankTab" .. i .. "OwnedStackBoxLabelText", "Withdraw items", 11, { 1, 1, 1, 1 }, "BOTTOMLEFT", 0, 20)
        row.owned = owned
        local buy = blz("Frame", nil, row, 268, 74, "TOPLEFT", 0, 0)
        buy.shown = false
        buy.text = label(buy, "GuildControlBankTab" .. i .. "BuyText", "Buy a tab", 12, { 1, 1, 1, 1 }, "TOP", 0, -10)
        row.buy = buy
        return row
    end
    NewBankTabRow(1); NewBankTabRow(2)
    function GuildControlUI_BankTabPermissions_Update(self) end

    local perm = blz("Frame", "GuildControlUIRankSettingsFrame", gc, 320, 380, "TOPLEFT", 10, -80)
    perm.shown = false
    gc.rankPermFrame = perm
    for _, n in ipairs({ "OfficerBg", "RosterBg", "BankBg" }) do
        local t = tex(perm, "GuildControlUIRankSettingsFrame" .. n, "BACKGROUND")
        t.points[1] = { point = "TOPLEFT", rel = perm, relPoint = "TOPLEFT", x = 0, y = n == "OfficerBg" and -30 or (n == "RosterBg" and -70 or -250) }
        t.points[2] = { point = "BOTTOMRIGHT", rel = perm, relPoint = "TOPRIGHT", x = 0, y = n == "OfficerBg" and -64 or (n == "RosterBg" and -240 or -330) }
        perm[n] = t
    end
    perm.OfficerPermissions = label(perm, nil, "Officer", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 8, -40)
    label(perm, "GuildControlUIRankSettingsFrameBankLabel", "Guild Bank", 12, { 1, 0.82, 0, 1 }, "TOPLEFT", 8, -256)
    perm.dropdown = blz("Button", "GuildControlUIRankSettingsFrameRankDropdown", perm, 160, 24, "TOPLEFT", 120, 0)
    for i, id in ipairs({ 5, 6, 7, 8 }) do
        local c = blz("CheckButton", "GuildControlUIRankSettingsFrameCheckbox" .. id, perm, 20, 20, "TOPLEFT", 12, -78 - (i - 1) * 24)
        c.NormalTexture = tex(c, nil, "ARTWORK"); c.normalTex = c.NormalTexture
        c.text = label(c, "GuildControlUIRankSettingsFrameCheckbox" .. id .. "Text", "Right " .. id, 10, { 1, 1, 1, 1 }, "LEFT", 22, 0)
    end
    perm.goldBox = blz("EditBox", "GuildControlUIRankSettingsFrameGoldBox", perm, 80, 20, "TOPLEFT", 12, -290)
    perm.goldBox.fontPath, perm.goldBox.size = "stock.ttf", 12
end
"""

H = Harness({
    "ButtonSkins": "Core/ButtonSkins.lua",
    "Character": "Modules/Skins/Character.lua",
    "Commerce": "Modules/Skins/Commerce.lua",
    "GroupKit": "Modules/Skins/GroupKit.lua",
    "OddsEnds": "Modules/Skins/OddsEnds.lua",
    "GuildBank": "Modules/Skins/GuildBank.lua",
}, BLIZZARD)

BOOT = "Fire('PLAYER_ENTERING_WORLD'); FlushTimers()"


def case(name, body):
    H.case(name, body.replace("@BOOT@", BOOT))


case("guild bank: the window wears the panel skin, the marble, corner and tab name art is held, the emblem is left", """
    @BOOT@
    local w, S = GuildBankFrame, FS.GuildBankSkin.state
    assert(S.panels[w] and w.fsStripped, 'panel not skinned')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText():find('guild bank'), 'no title band')
    for _, k in ipairs({ 'TabTitleBG', 'TabTitleBGLeft', 'TabTitleBGRight', 'TabLimitBG', 'TabLimitBGLeft', 'TabLimitBGRight', 'Portrait', 'RedMarbleBG', 'BlackBG' }) do
        assert(w[k].alpha == 0, 'art kept ' .. k)
    end
    assert(GuildBankFrameBottomLeftOuter.alpha == 0 and GuildBankFrameTopOuter.alpha == 0, 'corner art kept')
    assert(w.Emblem.Left.alpha == 1 and w.Emblem.Right.alpha == 1, 'emblem held')
    assert(w.TabTitle.fontPath ~= 'stock.ttf' and w.LimitLabel.fontPath ~= 'stock.ttf' and w.ErrorMessage.fontPath ~= 'stock.ttf', 'labels not mono')
    assert(w.fsGuildBankSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("guild bank: the name chips are rings that follow the stock title and limit art", """
    @BOOT@
    local w, S = GuildBankFrame, FS.GuildBankSkin.state
    local chips = S.chips
    assert(chips and chips.title and chips.limit, 'no chips')
    assert(chips.title.fill.shown and chips.limit.fill.shown, 'chips hidden while the stock art shows')
    w.TabTitle:Hide()
    assert(not chips.title.fill.shown and not chips.title.edges[1].shown, 'title chip stays without a title')
    assert(chips.limit.fill.shown, 'limit chip follows the wrong label')
    w.TabTitle:Show()
    assert(chips.title.fill.shown and chips.title.edges[1].shown, 'title chip does not come back')
""")

case("guild bank slots: all 98 keep icons, counts and search overlay under a plate, the stock art is held, columns are cards", """
    @BOOT@
    local S = FS.GuildBankSkin.state
    local n = 0
    for c = 1, 7 do
        local col = GuildBankFrame.Columns[c]
        assert(col.Background.alpha == 0, 'well art kept ' .. c)
        assert(S.wells[col], 'column ' .. c .. ' not a card')
        for i = 1, 14 do
            local b = col.Buttons[i]
            assert(S.slots[b], 'slot not skinned')
            assert(b.NormalTexture.alpha == 0 and b.IconBorder.alpha == 0, 'slot art kept')
            assert(b.icon.alpha == 1, 'icon held')
            assert(b.SearchOverlay.alpha == 1, 'search overlay held')
            assert(b.scripts.OnClick and b.scripts.OnDragStart, 'click or drag lost')
            n = n + 1
        end
    end
    assert(n == 98, 'slots ' .. n)
    assert(FS.ItemSlotSkins.Parts(GuildBankFrame.Columns[1].Buttons[1]), 'no slot layer')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("guild bank slots: the quality the stock code hands over is read for the slot", """
    @BOOT@
    local b = GuildBankFrame.Columns[2].Buttons[3]
    SetItemButtonQuality(b, 4)
    assert(FS.GuildBankSkin.state.quality[b] == 4, 'quality not read')
""")

case("guild bank tabs: the frame art is held, each key is a ring keeping its icon and search overlay, the chosen tab is lit", """
    @BOOT@
    local S, RK = FS.GuildBankSkin.state, FS.OddsEndsSkin.state.keys
    for i = 1, 8 do
        local tab = GuildBankFrame.BankTabs[i]
        local b = tab.Button
        assert(tab.regions[1].alpha == 0, 'tab frame art kept ' .. i)
        assert(RK[b], 'tab ' .. i .. ' not a ring key')
        assert(b.NormalTexture.alpha == 0 and b.highlightTex.alpha == 0, 'key art kept ' .. i)
        assert(b.IconTexture.alpha == 1 and b.SearchOverlay.alpha == 1, 'icon or search overlay held')
        assert(b.scripts.OnClick, 'click lost')
    end
    local c = RK[GuildBankFrame.BankTabs[1].Button].box.edges[1].color
    local cy = FS.Theme.COLOR_POWER
    assert(math.abs(c[1] - cy[1]) < 0.01 and math.abs(c[2] - cy[2]) < 0.01, 'chosen tab not cyan')
""")

case("guild bank money and keys: the money box is ringed, the labels are mono, money styled, keys swept", """
    @BOOT@
    local w = GuildBankFrame
    assert(w.MoneyFrameBG.NineSlice == nil)
    assert(w.MoneyFrameBG.regions[1].alpha == 0 and w.MoneyFrameBG.regions[2].alpha == 0, 'money box art kept')
    assert(w.MoneyFrameBG.LimitLabel.fontPath ~= 'stock.ttf' and w.MoneyFrameBG.UnlimitedLabel.fontPath ~= 'stock.ttf', 'money labels not mono')
    assert(GuildBankMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf' and GuildBankWithdrawMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf'
        and GuildBankFrameTabCostMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'money not styled')
    assert(FS.ButtonSkins.Parts(w.DepositButton) and FS.ButtonSkins.Parts(w.WithdrawButton), 'deposit keys not swept')
    assert(FS.ButtonSkins.Parts(w.BuyInfo.PurchaseButton) and FS.ButtonSkins.Parts(w.Info.SaveButton), 'purchase or save key not swept')
    assert(w.BuyInfo.TabText.fontPath ~= 'stock.ttf' and GuildBankFrameTabCost.fontPath ~= 'stock.ttf', 'buy labels not mono')
""")

case("guild bank log and tab info: ringed pages with mono text", """
    @BOOT@
    local w, S = GuildBankFrame, FS.GuildBankSkin.state
    assert(S.pages[w.Log] and S.pages[w.Info], 'pages not ringed')
    assert(Ours(w.Log) >= 5 and Ours(w.Info) >= 5, 'no ring drawn')
    assert(w.Log.MessageFrame.fontPath ~= 'stock.ttf', 'log not mono')
    assert(w.Info.EditBox.fontPath ~= 'stock.ttf', 'info box not mono')
""")

case("icon picker: a dialog with the border art held, a ringed icon key that keeps its icon, a mono description that stays mono", """
    @BOOT@
    local p, S = GuildBankPopupFrame, FS.GuildBankSkin.state
    assert(S.panels[p] and FS.CommerceSkin.state.dialogs[p], 'popup not a dialog')
    assert(p.BG.alpha == 0, 'popup backdrop kept')
    for _, r in ipairs(p.BorderBox.regions) do if r.path == 'Interface\\\\stock\\\\art' then assert(r.alpha == 0, 'border art kept') end end
    local sib = p.BorderBox.SelectedIconArea.SelectedIconButton
    assert(FS.OddsEndsSkin.state.keys[sib], 'icon key not a ring key')
    assert(sib.Back.alpha == 0 and sib.Icon.alpha == 1, 'slot art kept or icon held')
    local d = p.BorderBox.SelectedIconArea.SelectedIconText.SelectedIconDescription
    assert(d.fontPath ~= 'stock.ttf', 'description not mono')
    d:SetFontObject()
    assert(d.fontPath ~= 'stock.ttf', 'stock font object undid the mono')
    local eb = p.BorderBox.IconSelectorEditBox
    assert(eb.IconSelectorPopupNameLeft.alpha == 0 and eb.IconSelectorPopupNameMiddle.alpha == 0, 'edit backdrop kept')
    assert(FS.ButtonSkins.Parts(p.BorderBox.OkayButton) and FS.ButtonSkins.Parts(p.BorderBox.CancelButton), 'okay or cancel not swept')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("guild control: the window wears the panel skin, the Hbar and the section art are held", """
    @BOOT@
    local g, S = GuildControlUI, FS.GuildBankSkin.state
    assert(S.panels[g] and g.fsStripped, 'panel not skinned')
    assert(g.fsPanelTitle and g.fsPanelTitle:GetText():find('guild control'), 'no title band')
    assert(GuildControlUIHbar.alpha == 0, 'hbar kept')
    for _, n in ipairs({ 'OfficerBg', 'RosterBg', 'BankBg' }) do assert(g.rankPermFrame[n].alpha == 0, n .. ' kept') end
    assert(g.title.alpha == 0, 'the stock title shows over the band')
    g.title:SetAlpha(1)
    assert(g.title.alpha == 0, 'the stock title came back')
    assert(g.fsGuildControlSkin, 'no inspect marker')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("guild control: rank rows are cards with square keys that keep their icons, the stock rows made later are caught too", """
    @BOOT@
    local S = FS.GuildBankSkin.state
    local late = NewRankRow(3)
    GuildControlUI_RankOrder_Update(GuildControlUI.orderFrame)
    for i = 1, 3 do
        local row = _G['GuildControlUIRankOrderFrameRank' .. i]
        assert(S.rows[row], 'row ' .. i .. ' not carded')
        assert(row.rankLabel.fontPath ~= 'stock.ttf', 'rank label not mono')
        for _, k in ipairs({ 'deleteButton', 'downButton', 'upButton' }) do
            local b = row[k]
            assert(FS.GroupSkin.squares[b], k .. ' not a square key')
            assert(b.icon.alpha == 1 and b.NormalTexture.alpha == 0, k .. ' art wrong')
            assert(b.scripts.OnClick, 'click lost')
        end
    end
    assert(FS.ButtonSkins.Parts(GuildControlUI.orderFrame.newButton), 'add rank key not swept')
""")

case("guild control: bank tab rows and the settings sections are cards, the labels are mono", """
    @BOOT@
    local S, g = FS.GuildBankSkin.state, GuildControlUI
    NewBankTabRow(3)
    GuildControlUI_BankTabPermissions_Update(g.bankTabFrame)
    for i = 1, 3 do
        local row = _G['GuildControlBankTab' .. i]
        assert(S.rows[row], 'bank row ' .. i)
        assert(_G['GuildControlBankTab' .. i .. 'Bg'].alpha == 0, 'row wash kept')
        assert(row.owned.tabName.fontPath ~= 'stock.ttf' and row.owned.viewCB.text.fontPath ~= 'stock.ttf', 'row text not mono')
        assert(row.owned.tabIcon.alpha == 1, 'tab icon held')
    end
    for _, n in ipairs({ 'OfficerBg', 'RosterBg', 'BankBg' }) do assert(S.sections[g.rankPermFrame[n]], n .. ' not a section card') end
    assert(g.rankPermFrame.OfficerPermissions.fontPath ~= 'stock.ttf' and GuildControlUIRankSettingsFrameBankLabel.fontPath ~= 'stock.ttf', 'section labels not mono')
    assert(GuildControlUIRankSettingsFrameCheckbox5.text.fontPath ~= 'stock.ttf', 'check label not mono')
""")

case("no script or attribute is written on a Blizzard widget (the mock raises on it), and a second pass adds nothing", """
    @BOOT@
    GuildBankFrame:Show(); GuildBankPopupFrame:Show(); GuildControlUI:Show(); FlushTimers()
    local n, m = Ours(GuildBankFrame), Ours(GuildControlUI)
    local k = Ours(GuildBankFrame.Columns[1])
    FS.GuildBankSkin.Build(); FlushTimers()
    assert(Ours(GuildBankFrame) == n and Ours(GuildControlUI) == m and Ours(GuildBankFrame.Columns[1]) == k, 'a second build drew again')
""")

case("a client without these frames degrades quietly", """
    GuildBankFrame, GuildBankPopupFrame, GuildControlUI = nil, nil, nil
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("combat: nothing is built while in combat, the build runs when it ends", """
    Reset()
    __combat = true
    FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'Character', 'Commerce', 'GroupKit', 'OddsEnds', 'GuildBank' })
    assert(not FS.GuildBankSkin.state.panels[GuildBankFrame], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.GuildBankSkin.state.panels[GuildBankFrame], 'not built when combat ended')
""")

SCENES = {
    "bank": "Fire('PLAYER_ENTERING_WORLD'); GuildBankFrame:Show(); local c = GuildBankFrame.Columns[1].Buttons; for i = 1, 14, 2 do SetItemButtonQuality(c[i], (i % 5) + 1) end; FlushTimers(); return DumpOps({ GuildBankFrame })",
    "popup": "Fire('PLAYER_ENTERING_WORLD'); GuildBankFrame:Show(); GuildBankPopupFrame:Show(); FlushTimers(); return DumpOps({ GuildBankPopupFrame })",
    "log": "Fire('PLAYER_ENTERING_WORLD'); GuildBankFrame:Show(); GuildBankFrame.Columns[1]:Hide(); for i = 2, 7 do GuildBankFrame.Columns[i]:Hide() end; GuildBankFrame.Log:Show(); GuildBankFrame.BuyInfo:Show(); FlushTimers(); return DumpOps({ GuildBankFrame })",
    "control": "Fire('PLAYER_ENTERING_WORLD'); GuildControlUI:Show(); GuildControlUI.orderFrame:Show(); NewRankRow(3); GuildControlUI_RankOrder_Update(GuildControlUI.orderFrame); FlushTimers(); return DumpOps({ GuildControlUI })",
    "controlperm": "Fire('PLAYER_ENTERING_WORLD'); GuildControlUI:Show(); GuildControlUI.rankPermFrame:Show(); FlushTimers(); return DumpOps({ GuildControlUI })",
    "controlbank": "Fire('PLAYER_ENTERING_WORLD'); GuildControlUI:Show(); GuildControlUI.bankTabFrame:Show(); NewBankTabRow(3); GuildControlUI_BankTabPermissions_Update(GuildControlUI.bankTabFrame); FlushTimers(); return DumpOps({ GuildControlUI })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("guild bank skin", SCENES))
