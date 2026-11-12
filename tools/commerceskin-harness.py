#!/usr/bin/env python3
"""Runs the real Modules/Skins/Commerce.lua headless against mock commerce windows (tools/charskin_support.py).

Pinned, per window: the vendor rows get a card, the stock slot art and name plate are held, the item slot wears the shared slot
layer and takes its quality from SetItemButtonQuality, no script or attribute is written on a Blizzard widget, the repair and
page keys are restyled in place, and nothing is built in combat. Run `python3 tools/commerceskin-harness.py [--png debug/commerce]`.
The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
local function money(parent, name, x, y)
    local m = blz("Frame", name, parent, 100, 14, "TOPLEFT", x, y)
    m.staticMoney = true
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do fstring(m, name .. k .. "ButtonText", "12", 12, { 1, 1, 1, 1 }) end
    return m
end
function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Merchant") or k:find("^BuybackBG") or k:find("^Bank") or k:find("^StackSplit")
            or k:find("^ColorPicker") or k:find("^OpacityFrame") or k:find("^StaticPopup") or k:find("^AuctionHouse")) then _G[k] = nil end
    end
    -- the vendor, as MerchantFrame.xml builds it
    local win = blz("Frame", "MerchantFrame", UIParent, 336, 444)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    tex(win, "MerchantFramePortrait", "BACKGROUND")
    tex(win, "BuybackBG", "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 336, 444)
    win.TitleContainer = blz("Frame", nil, win, 280, 20)
    fstring(win, "MerchantFrameTitleText", "Moo Vendor")
    local close = blz("Button", "MerchantFrameCloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    fstring(win, "MerchantPageText", "Page 1/1", 12, { 1, 0.82, 0, 1 }).points[1] = { point = "BOTTOM", rel = win, relPoint = "BOTTOM", x = 0, y = 86 }
    atex(win, "MerchantFrameBottomLeftBorder", "OVERLAY", "UI-Merchant-BotFrame", 334, 61)
    local ITEMS = {
        { "Linen Cloth", 1, 1, "Interface\\Icons\\inv_fabric_linen_01" }, { "Healing Potion", 2, 2, "Interface\\Icons\\inv_potion_01" },
        { "Hunting Bow", 3, 4, "Interface\\Icons\\inv_weapon_bow_01" }, { "Runed Staff", 4, 3, "Interface\\Icons\\inv_staff_01" },
        { "Dull Axe", 5, 0, "Interface\\Icons\\inv_axe_01" }, { "Spiced Wolf Meat", 6, 1, "Interface\\Icons\\inv_misc_food_01" },
        { "Shadow Cloak", 7, 4, "Interface\\Icons\\inv_misc_cape_01" },
    }
    QUALITY_RGB = { [0] = { 0.6, 0.6, 0.6 }, { 1, 1, 1 }, { 0.12, 1, 0 }, { 0, 0.44, 0.87 }, { 0.64, 0.21, 0.93 } }
    for i = 1, 12 do
        local col, r = (i - 1) % 2, math.floor((i - 1) / 2)
        local row = blz("Frame", "MerchantItem" .. i, win, 153, 44, "TOPLEFT", 11 + col * 165, -(69 + r * 52))
        row.SlotTexture = tex(row, "MerchantItem" .. i .. "SlotTexture", "BACKGROUND")
        row.SlotTexture.w, row.SlotTexture.h = 64, 64
        tex(row, "MerchantItem" .. i .. "NameFrame", "BACKGROUND").w = 128
        row.Name = fstring(row, "MerchantItem" .. i .. "Name", "", 11, { 1, 0.82, 0, 1 })
        row.Name.w, row.Name.h = 100, 30
        row.Name.points[1] = { point = "LEFT", rel = row, relPoint = "LEFT", x = 46, y = 7 }
        local b = blz("Button", "MerchantItem" .. i .. "ItemButton", row, 37, 37, "TOPLEFT", 0, 0)
        row.ItemButton = b
        b.icon = tex(b, "MerchantItem" .. i .. "ItemButtonIconTexture", "BORDER")
        b.NormalTexture = tex(b, "MerchantItem" .. i .. "ItemButtonNormalTexture", "ARTWORK")
        b.IconBorder = tex(b, nil, "OVERLAY")
        b.IconQuestTexture = tex(b, nil, "OVERLAY")
        b.Count = fstring(b, "MerchantItem" .. i .. "ItemButtonCount", "", 12, { 1, 1, 1, 1 })
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        b.SetItemButtonQuality = function(self, q) self.q = q end
        money(row, "MerchantItem" .. i .. "MoneyFrame", 46, -28)
        local item = ITEMS[i]
        if item then
            row.Name:SetText(item[1])
            local qc = QUALITY_RGB[item[3]]
            row.Name:SetTextColor(qc[1], qc[2], qc[3], 1)
            b.icon.path = item[4]
            b:SetItemButtonQuality(item[3])
            b.stockQuality = item[3]
        else
            b.shown = false
            row.Name:SetText("")
            _G["MerchantItem" .. i .. "MoneyFrame"].shown = false
        end
    end
    MerchantItem11.shown, MerchantItem12.shown = false, false
    local function key(name, atlas, x, y, w)
        local b = blz("Button", name, win, w or 36, w or 36, "BOTTOMRIGHT", x, y)
        b.points[1].relPoint = "BOTTOMLEFT"
        tex(b, nil, "BACKGROUND")
        b.Icon = atex(b, nil, "BORDER", atlas, 36, 36)
        b.pushedTex = tex(b, nil, "ARTWORK")
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        return b
    end
    key("MerchantSellAllJunkButton", "SpellIcon-256x256-SellJunk", 160, -33)
    key("MerchantRepairAllButton", "SpellIcon-256x256-RepairAll", 172, -11)
    local rp = key("MerchantRepairItemButton", "SpellIcon-256x256-Repair", 134, -11)
    rp.Icon.desat = true
    local back = blz("Frame", "MerchantBuyBackItem", win, 115, 37, "TOPLEFT", 40, -390)
    back.SlotTexture = tex(back, "MerchantBuyBackItemSlotTexture", "BACKGROUND")
    tex(back, "MerchantBuyBackItemNameFrame", "BACKGROUND")
    back.Name = fstring(back, "MerchantBuyBackItemName", "Dull Axe", 11, { 0.6, 0.6, 0.6, 1 })
    back.Name.points[1] = { point = "LEFT", rel = back, relPoint = "LEFT", x = 46, y = 2 }
    back.ItemButton = blz("Button", "MerchantBuyBackItemItemButton", back, 37, 37, "TOPLEFT", 0, 0)
    back.ItemButton.icon = tex(back.ItemButton, nil, "BORDER")
    back.ItemButton.icon.path = "Interface\\Icons\\inv_axe_01"
    back.ItemButton.UndoFrame = blz("Frame", nil, back.ItemButton, 37, 37)
    back.ItemButton.UndoFrame.Arrow = atex(back.ItemButton.UndoFrame, nil, "ARTWORK", "common-icon-undo", 20, 20)
    back.ItemButton.SetItemButtonQuality = function(self, q) end
    money(back, "MerchantBuyBackItemMoneyFrame", 46, -22)
    for _, n in ipairs({ "MerchantExtraCurrencyInset", "MerchantExtraCurrencyBg", "MerchantMoneyInset", "MerchantMoneyBg" }) do
        local f = blz("Frame", n, win, 160, 30)
        f.NineSlice = blz("Frame", nil, f, 160, 30)
        atex(f, nil, "BACKGROUND", "UI-Frame-InnerBotLeft", 20, 20)
    end
    MerchantExtraCurrencyBg.points[1] = { point = "BOTTOMLEFT", rel = win, relPoint = "BOTTOMLEFT", x = 7, y = 6 }
    MerchantMoneyBg.points[1] = { point = "BOTTOMRIGHT", rel = win, relPoint = "BOTTOMRIGHT", x = -7, y = 6 }
    money(win, "MerchantMoneyFrame", 170, -420)
    local function pager(name, dir)
        local b = blz("Button", name, win, 32, 32, "CENTER", dir == "<" and 25 or 310, 96)
        b.points[1].relPoint = "BOTTOMLEFT"
        tex(b, nil, "BACKGROUND")
        local label = fstring(b, nil, dir == "<" and "PREV" or "NEXT", 12, { 1, 0.82, 0, 1 })
        label.points[1] = { point = dir == "<" and "LEFT" or "RIGHT", rel = b, relPoint = dir == "<" and "RIGHT" or "LEFT", x = 0, y = 0 }
        b.NormalTexture = tex(b, nil, "ARTWORK")
        b.GetNormalTexture = function(self) return self.NormalTexture end
        b.scripts.OnClick = function() end
        return b
    end
    pager("MerchantPrevPageButton", "<").enabled = false
    pager("MerchantNextPageButton", ">")
    function MerchantFrame_Update()
        for i = 1, 12 do
            local b = _G["MerchantItem" .. i .. "ItemButton"]
            if b.stockQuality then
                b:SetItemButtonQuality(b.stockQuality)
                local qc = QUALITY_RGB[b.stockQuality]
                _G["MerchantItem" .. i .. "Name"]:SetTextColor(qc[1], qc[2], qc[3], 1)
            end
        end
    end
    if BuildExtras then BuildExtras() end
end
"""

BANK = r"""
function BuildExtras()
    local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, BLZ.atex
    local function dialogBorder(parent)
        local b = blz("Frame", nil, parent, 10, 10)
        b.points = { { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = 0 }, { point = "BOTTOMRIGHT", rel = parent, relPoint = "BOTTOMRIGHT", x = 0, y = 0 } }
        tex(b, nil, "BORDER")
        return b
    end
    -- the bank, as BankFrame.xml and BankPanelTemplate build it
    local win = blz("Frame", "BankFrame", UIParent, 738, 460)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    win.Background = atex(win, nil, "BACKGROUND", "bank-frame-background", 738, 410)
    fstring(win, "BankFrameTitleText", "Character Bank", 14, { 1, 1, 1, 1 })
    local panel = blz("Frame", "BankPanel", win, 738, 460, "TOPLEFT", 0, 0)
    win.BankPanel = panel
    panel.NineSlice = blz("Frame", nil, panel, 738, 410, "TOPLEFT", 0, -20)
    atex(panel.NineSlice, nil, "BORDER", "UI-Frame-InnerTopLeft", 20, 20)
    panel.EdgeShadows = blz("Frame", nil, panel, 738, 440, "TOPLEFT", 0, 0)
    atex(panel.EdgeShadows, nil, "BORDER", "bank-frame-shadow-cornertopleft", 20, 20)
    panel.Header = blz("Frame", nil, panel, 300, 20, "TOP", 0, -36)
    panel.Header.Text = fstring(panel.Header, nil, "Tab 2", 14, { 1, 1, 1, 1 })
    local money = blz("Frame", nil, panel, 394, 25, "BOTTOMRIGHT", -3, 3)
    panel.MoneyFrame = money
    money.Border = blz("Frame", nil, money, 178, 19, "LEFT", 0, 0)
    atex(money.Border, nil, "BORDER", "UI-Frame-InnerTopLeft", 20, 20)
    local sort = blz("Button", nil, panel, 28, 26, "TOPLEFT", 560, -34)
    sort.NormalTexture = atex(sort, nil, "ARTWORK", "bags-button-autosort-up", 28, 26)
    sort.GetNormalTexture = function(self) return self.NormalTexture end
    sort.scripts.OnClick = function() end
    panel.AutoSortButton = sort
    local function tab(parent, x, y, icon, selected)
        local t = blz("Button", nil, parent, 32, 32, "TOPLEFT", x, y)
        t.Border = tex(t, nil, "BORDER"); t.Border.w, t.Border.h = 64, 64
        t.Icon = tex(t, nil, "ARTWORK"); t.Icon.path = icon
        t.SearchOverlay = tex(t, nil, "ARTWORK"); t.SearchOverlay.shown = false
        t.SelectedTexture = tex(t, nil, "OVERLAY")
        t.SelectedTexture.shown = selected
        t.IsSelected = function() return selected end
        t.scripts.OnClick = function() end
        t.scripts.OnEnter = function() end
        t.Init = function() end
        t.RefreshVisuals = function() end
        return t
    end
    local tabs = { tab(panel, 740, -25, "Interface\\Icons\\inv_misc_bag_08", false), tab(panel, 740, -81, "Interface\\Icons\\inv_misc_bag_09", true),
        tab(panel, 740, -137, "Interface\\Icons\\inv_misc_bag_10", false) }
    panel.bankTabPool = { EnumerateActive = function() local i = 0 return function() i = i + 1 return tabs[i] end end }
    panel.PurchaseTab = tab(panel, 740, -193, "Interface\\Icons\\inv_misc_bag_11", false)
    panel.PurchaseTab.Background = tex(panel.PurchaseTab, nil, "BORDER")
    panel.RefreshBankTabs = function() end
    local function prompt(x, y, w, h, title, text)
        local p = blz("Frame", nil, panel, w, h, "TOPLEFT", x, y)
        for _, k in ipairs({ "TopLeftInner", "TopRightInner", "BottomLeftInner", "BottomRightInner", "LeftInner", "TopInner" }) do
            p[k] = tex(p, nil, "BORDER")
            p[k].w, p[k].h = 32, 32
        end
        p.Background = tex(p, nil, "BACKGROUND")
        p.Background:SetColorTexture(0, 0, 0, 1)
        p.Background.points = { { point = "TOPLEFT", rel = p, relPoint = "TOPLEFT", x = 8, y = -4 }, { point = "BOTTOMRIGHT", rel = p, relPoint = "BOTTOMRIGHT", x = -8, y = 4 } }
        p.Title = fstring(p, nil, title, 22, { 1, 0.82, 0, 1 })
        p.Title.points[1] = { point = "TOP", rel = p, relPoint = "TOP", x = 0, y = -110 }
        p.PromptText = fstring(p, nil, text, 16, { 1, 1, 1, 1 })
        p.PromptText.points[1] = { point = "CENTER", rel = p, relPoint = "CENTER", x = 0, y = 0 }
        return p
    end
    panel.PurchasePrompt = prompt(10, -60, 718, 330, "Unlock bank tab", "Purchase a bank tab to store more items.")
    local cost = blz("Frame", nil, panel.PurchasePrompt, 300, 30, "TOP", 0, -200)
    cost.TabCost = fstring(cost, nil, "Cost:", 13, { 1, 0.82, 0, 1 })
    cost.TabCost.points[1] = { point = "LEFT", rel = cost, relPoint = "LEFT", x = 20, y = 0 }
    cost.MoneyDisplay = blz("Frame", "BankPromptMoney", cost, 100, 14, "LEFT", 90, 0)
    cost.MoneyDisplay.staticMoney = true
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do fstring(cost.MoneyDisplay, "BankPromptMoney" .. k .. "ButtonText", "4", 12, { 1, 1, 1, 1 }) end
    cost.PurchaseButton = blz("Button", nil, cost, 105, 21, "LEFT", 200, 0)
    for _, k in ipairs({ "Left", "Middle", "Right" }) do cost.PurchaseButton[k] = tex(cost.PurchaseButton, nil, "BACKGROUND") end
    cost.PurchaseButton.fs = fstring(cost.PurchaseButton, nil, "Purchase", 12)
    cost.PurchaseButton.scripts.OnClick = function() end
    panel.PurchasePrompt.TabCostFrame = cost
    panel.PurchasePrompt.shown = false
    panel.LockPrompt = prompt(10, -30, 718, 390, "Bank locked", "This bank is not available yet.")
    panel.LockPrompt.shown = false
    local pop = blz("Frame", "BankCleanUpConfirmationPopup", UIParent, 420, 140, "CENTER", 0, 0)
    pop.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 900, y = -200 }
    pop.shown = false
    pop.Border = dialogBorder(pop)
    pop.Text = fstring(pop, nil, "Clean up this bank? Items will be sorted.", 14, { 1, 1, 1, 1 })
    pop.Text.points[1] = { point = "TOP", rel = pop, relPoint = "TOP", x = 0, y = -16 }
    pop.HidePopupCheckbox = blz("Frame", nil, pop, 300, 23, "TOP", 0, -60)
    pop.HidePopupCheckbox.Label = fstring(pop.HidePopupCheckbox, nil, "Do not show again", 12, { 1, 0.82, 0, 1 })
    for i, label in ipairs({ "Accept", "Cancel" }) do
        local b = blz("Button", nil, pop, 128, 21, "TOPLEFT", 20 + (i - 1) * 140, -100)
        for _, k in ipairs({ "Left", "Middle", "Right" }) do b[k] = tex(b, nil, "BACKGROUND") end
        b.fs = fstring(b, nil, label, 12)
        b.scripts.OnClick = function() end
        pop[label .. "Button"] = b
    end

    -- the stack split, as StackSplitFrame.xml builds it
    local split = blz("Frame", "StackSplitFrame", UIParent, 160, 70, "TOPLEFT", 300, -300)
    split.shown = false
    split.SingleItemSplitBackground = tex(split, nil, "BACKGROUND")
    split.MultiItemSplitBackground = tex(split, nil, "BACKGROUND")
    split.StackSplitText = fstring(split, nil, "12", 14, { 1, 1, 1, 1 })
    split.StackItemCountText = fstring(split, nil, "of 40", 11, { 1, 1, 1, 1 })
    for _, k in ipairs({ "LeftButton", "RightButton", "OkayButton", "CancelButton" }) do
        local b = blz("Button", nil, split, 30, 21, "TOPLEFT", 10, -40)
        b.NormalTexture = tex(b, nil, "ARTWORK"); b.GetNormalTexture = function(self) return self.NormalTexture end
        b.fs = fstring(b, nil, k, 11)
        b.scripts.OnClick = function() end
        split[k] = b
    end
    -- the colour picker
    local cp = blz("Frame", "ColorPickerFrame", UIParent, 330, 240, "TOPLEFT", 500, -200)
    cp.shown = false
    cp.Border = dialogBorder(cp)
    cp.Header = blz("Frame", nil, cp, 200, 30, "TOP", 0, 10)
    tex(cp.Header, nil, "ARTWORK"); cp.Header.Text = fstring(cp.Header, nil, "Color Picker", 13, { 1, 1, 1, 1 })
    cp.DragBar = blz("Frame", nil, cp, 300, 20, "TOP", 0, 0); tex(cp.DragBar, nil, "ARTWORK")
    cp.Content = blz("Frame", nil, cp, 300, 160, "TOPLEFT", 10, -30)
    cp.Content.ColorSwatchCurrent = blz("Frame", nil, cp.Content, 40, 40, "TOPLEFT", 10, -10)
    cp.Content.ColorSwatchOriginal = blz("Frame", nil, cp.Content, 40, 40, "TOPLEFT", 60, -10)
    cp.Content.HexBox = blz("Frame", nil, cp.Content, 120, 24, "TOPLEFT", 10, -100)
    cp.Content.HexBox.Hash = fstring(cp.Content.HexBox, nil, "#", 12, { 1, 1, 1, 1 })
    cp.Footer = blz("Frame", nil, cp, 300, 30, "BOTTOM", 0, 5)
    for _, k in ipairs({ "OkayButton", "CancelButton" }) do
        local b = blz("Button", nil, cp.Footer, 90, 21, "LEFT", 10, 0)
        b.fs = fstring(b, nil, k, 12); b.scripts.OnClick = function() end
        cp.Footer[k] = b
    end
    -- a prompt with an edit box and a money input
    local pop1 = blz("Frame", "StaticPopup1", UIParent, 320, 150, "TOPLEFT", 200, -200)
    pop1.shown = false
    pop1.EditBox = blz("EditBox", nil, pop1, 200, 22, "TOPLEFT", 20, -60)
    pop1.EditBox.NineSlice = blz("Frame", nil, pop1.EditBox, 200, 22, "TOPLEFT", 0, 0); tex(pop1.EditBox.NineSlice, nil, "BORDER")
    local mif = blz("Frame", nil, pop1, 200, 22, "TOPLEFT", 20, -100)
    pop1.MoneyInputFrame = mif
    for _, k in ipairs({ "gold", "silver", "copper" }) do
        local e = blz("EditBox", nil, mif, 50, 20, "LEFT", 0, 0)
        e.Left, e.Middle, e.Right = tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND")
        mif[k] = e
    end

    -- the auction house, reduced to the widgets this skin touches
    local ah = blz("Frame", "AuctionHouseFrame", UIParent, 800, 500, "TOPLEFT", 50, -50)
    ah.shown = false
    local cl = blz("Frame", nil, ah, 200, 400, "TOPLEFT", 10, -60)
    ah.CategoriesList = cl
    local fb = {}
    cl.ScrollBox = { ForEachFrame = function(self, fn) for _, b in ipairs(fb) do fn(b) end end }
    for i = 1, 3 do
        local b = blz("Button", nil, cl, 132, 21, "TOPLEFT", 5, -5 - i * 22)
        b.NormalTexture = tex(b, nil, "BACKGROUND"); b.Lines = tex(b, nil, "BACKGROUND"); b.HighlightTexture = tex(b, nil, "BORDER")
        b.SelectedTexture = tex(b, nil, "ARTWORK"); b.SelectedTexture.shown = (i == 2)
        b.fs = fstring(b, nil, "Category " .. i, 11)
        b.GetFontString = function(self) return self.fs end
        b.scripts.OnEnter = function() end
        fb[i] = b
    end
    local sf = blz("Frame", nil, ah, 300, 200, "TOPLEFT", 250, -60)
    ah.ItemSellFrame = sf
    sf.PriceInput = blz("Frame", nil, sf, 200, 24, "TOPLEFT", 0, 0)
    local lm = blz("Frame", nil, sf.PriceInput, 200, 24, "TOPLEFT", 0, 0)
    sf.PriceInput.MoneyInputFrame = lm
    for _, k in ipairs({ "GoldBox", "SilverBox", "CopperBox" }) do
        local e = blz("EditBox", nil, lm, 50, 22, "LEFT", 0, 0)
        e.Left, e.Middle, e.Right = tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND")
        lm[k] = e
    end
end
"""
BLIZZARD = BLIZZARD + BANK

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "Character": "Modules/Skins/Character.lua",
             "Commerce": "Modules/Skins/Commerce.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); MerchantFrame:Show(); MerchantFrame_Update(); FlushTimers()"

case("vendor: every filled row gets a card, the stock slot art and name plate are held, scripts stay", f"""
    {OPEN}
    local S = FS.CommerceSkin.state
    for i = 1, 12 do
        local row = _G['MerchantItem' .. i]
        assert(S.cards[row], 'row ' .. i .. ' not skinned')
        assert(row.SlotTexture.alpha == 0 and _G['MerchantItem' .. i .. 'NameFrame'].alpha == 0, 'stock art kept on ' .. i)
        local b = row.ItemButton
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost')
        assert(row.Name.fontPath ~= 'stock.ttf', 'name not mono')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("vendor: an empty row has no card, a row with an item does; the card lights cyan under the hand", f"""
    {OPEN}
    local S = FS.CommerceSkin.state
    local full, empty = _G.MerchantItem1, _G.MerchantItem8
    assert(full.ItemButton.shown and not empty.ItemButton.shown)
    assert(S.cards[full].box.fill.shown ~= false and S.cards[empty].box.fill.shown == false, 'empty card shown')
    local e = S.cards[full].box.edges[1]
    assert(e.color[3] > 0.4 and e.color[1] < 0.4, 'idle edge not the dim violet')
    full.ItemButton:RunScript('OnEnter')
    assert(e.color[2] > 0.8 and e.color[1] < 0.3, 'hover edge not cyan')
    full.ItemButton:RunScript('OnLeave')
    -- a page change that fills an empty row shows its card
    empty.ItemButton:Show()
    assert(S.cards[empty].box.fill.shown ~= false, 'filled card hidden')
""")

case("vendor: the item slot takes its quality from SetItemButtonQuality", f"""
    {OPEN}
    local parts = FS.ItemSlotSkins.Parts(_G.MerchantItem3ItemButton)
    assert(parts and parts.led, 'no slot layer')
    local epic = FS.Theme.COLOR_QUALITY[4]
    local c = parts.led.color
    assert(math.abs(c[1] - epic[1]) < 0.01 and math.abs(c[3] - epic[3]) < 0.01, 'LED not epic ' .. table.concat(c, ','))
    _G.MerchantItem3ItemButton:SetItemButtonQuality(2)
    local g = FS.Theme.COLOR_QUALITY[2]
    assert(math.abs(parts.led.color[2] - g[2]) < 0.01, 'LED did not follow the quality')
""")

case("vendor: repair keys keep their icon and click, wear a ring; pager keys hold the stock arrows and draw a chevron", f"""
    {OPEN}
    local S = FS.CommerceSkin.state
    local CS = FS.CharacterSkin.state
    for _, n in ipairs({{ 'MerchantSellAllJunkButton', 'MerchantRepairAllButton', 'MerchantRepairItemButton' }}) do
        local b = _G[n]
        assert(CS.squares[b], n .. ' not a square')
        assert(b.Icon.alpha == 1, 'the icon must stay on ' .. n)
        assert(b.scripts.OnClick, 'click lost on ' .. n)
    end
    local prev, nxt = _G.MerchantPrevPageButton, _G.MerchantNextPageButton
    assert(CS.squares[prev] and #CS.squares[prev].glyph == 7, 'chevron')
    assert(prev.NormalTexture.alpha == 0, 'stock arrow kept')
    assert(prev.scripts.OnClick, 'pager click lost')
    assert(CS.squares[prev].glyph[1].alpha == 0.35, 'disabled previous page not dimmed')
    assert(CS.squares[nxt].glyph[1].alpha == 1, 'enabled next page dimmed')
    prev:Enable()
    assert(CS.squares[prev].glyph[1].alpha == 1, 'enable did not undim')
""")

case("vendor: the wells under the shop are held and drawn again as ring boxes", f"""
    {OPEN}
    assert(MerchantMoneyInset.alpha == 0 and MerchantMoneyBg.alpha == 0 and MerchantExtraCurrencyBg.alpha == 0, 'stock wells kept')
    MerchantMoneyBg:SetAlpha(1)
    assert(MerchantMoneyBg.alpha == 0, 'hold not kept')
""")

OPEN_BANK = "Fire('PLAYER_ENTERING_WORLD'); BankFrame:Show(); FlushTimers()"

case("bank: the panel's inset art, edge shadows and the window background are held, the money box is ours", f"""
    {OPEN_BANK}
    assert(BankFrame.Background.alpha == 0, 'window background kept')
    assert(BankPanel.NineSlice.alpha == 0 and BankPanel.EdgeShadows.alpha == 0, 'inset or shadows kept')
    assert(BankPanel.MoneyFrame.Border.alpha == 0, 'stock money border kept')
    assert(BankPanel.Header.Text.fontPath ~= 'stock.ttf', 'header not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("bank: the tab rail is pink when selected, cyan on hover, the stock frame art is held, the search dim and click stay", f"""
    {OPEN_BANK}
    local S = FS.CommerceSkin.state
    local tabs = {{}}
    for _, ch in ipairs({{ BankPanel:GetChildren() }}) do if ch.SelectedTexture then tabs[#tabs + 1] = ch end end
    assert(#tabs == 4, 'tabs ' .. #tabs)
    for _, t in ipairs(tabs) do
        assert(S.bankTabs[t], 'tab not skinned')
        assert(t.Border.alpha == 0 and t.SelectedTexture.alpha == 0, 'stock tab frame kept')
        assert(t.Icon.alpha == 1 and t.SearchOverlay.alpha == 1, 'icon or search dim held')
        assert(t.scripts.OnClick and t.scripts.OnEnter, 'tab script lost')
    end
    local sel = S.bankTabs[tabs[2]].box.edges[1].color
    assert(sel[1] > 0.9 and sel[2] < 0.3, 'selected tab not pink')
    local idle = S.bankTabs[tabs[1]].box.edges[1].color
    tabs[1]:RunScript('OnEnter')
    assert(S.bankTabs[tabs[1]].box.edges[1].color[2] > 0.8, 'hover not cyan')
    tabs[1]:RunScript('OnLeave')
    assert(S.bankTabs[tabs[1]].box.edges[1].color[2] < 0.4, 'did not return to idle')
""")

case("bank: the sort key is a plate with a glyph, the prompts lose their stock corner art and take mono texts", f"""
    {OPEN_BANK}
    local S = FS.CommerceSkin.state
    local sq = FS.CharacterSkin.state.squares[BankPanel.AutoSortButton]
    assert(sq and #sq.glyph == 6, 'sort glyph')
    assert(BankPanel.AutoSortButton.NormalTexture.alpha == 0, 'stock sort art kept')
    for _, p in ipairs({{ BankPanel.PurchasePrompt, BankPanel.LockPrompt }}) do
        assert(p.TopLeftInner.alpha == 0 and p.LeftInner.alpha == 0, 'prompt corner art kept')
        assert(p.Background.alpha == 1, 'the prompt black must stay')
        assert(p.Title.fontPath ~= 'stock.ttf' and p.Title.textColor[3] > 0.9, 'title not cyan mono')
        p.Title:SetTextColor(1, 0.82, 0, 1)
        assert(p.Title.textColor[3] > 0.9, 'title colour not pinned')
    end
    local cost = BankPanel.PurchasePrompt.TabCostFrame
    assert(cost.TabCost.fontPath ~= 'stock.ttf' and cost.PurchaseButton.scripts.OnClick, 'cost row')
""")

case("bank: the clean up confirmation is a dialog of ours: border frame held, chrome, LED, texts, buttons by the sweep", f"""
    {OPEN_BANK}
    local pop = BankCleanUpConfirmationPopup
    assert(pop.Border.alpha == 0, 'border kept')
    assert(FS.CommerceSkin.state.dialogs[pop], 'no dialog chrome')
    assert(#FS.CommerceSkin.state.rules >= 1, 'no LED')
    assert(pop.Text.fontPath ~= 'stock.ttf' and pop.HidePopupCheckbox.Label.fontPath ~= 'stock.ttf', 'texts')
    pop:Show(); FlushTimers()
    assert(FS.ButtonSkins.Parts(pop.AcceptButton) and FS.ButtonSkins.Parts(pop.CancelButton), 'buttons not swept')
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'Commerce' }})
    assert(not MerchantFrame.fsCommerceSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(MerchantFrame.fsCommerceSkin and BankFrame.fsCommerceBankSkin, 'not built when combat ended')
""")

case("stack split: the backgrounds are held, the dialog chrome and keys are ours, the clicks stay", f"""
    Fire('PLAYER_ENTERING_WORLD'); StackSplitFrame:Show(); FlushTimers()
    local w = StackSplitFrame
    assert(w.fsCommerceSplitSkin, 'not built')
    assert(w.SingleItemSplitBackground.alpha == 0 and w.MultiItemSplitBackground.alpha == 0, 'backgrounds kept')
    assert(FS.CommerceSkin.state.dialogs[w], 'no chrome')
    assert(FS.CommerceSkin.state.pagers[w.LeftButton] and FS.CommerceSkin.state.pagers[w.RightButton], 'chevrons')
    assert(FS.ButtonSkins.Parts(w.OkayButton) and FS.ButtonSkins.Parts(w.CancelButton), 'text keys')
    assert(w.OkayButton.scripts.OnClick, 'click lost')
    assert(w.StackSplitText.fontPath ~= 'stock.ttf', 'count not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("colour picker: stock border and header art are held, swatches get a ring, footer keys are ours", f"""
    Fire('PLAYER_ENTERING_WORLD'); ColorPickerFrame:Show(); FlushTimers()
    local w = ColorPickerFrame
    assert(w.fsCommerceColorSkin and FS.CommerceSkin.state.dialogs[w], 'not built')
    assert(w.Border.alpha == 0, 'border kept')
    assert(w.Header.Text.fontPath ~= 'stock.ttf', 'header not mono')
    assert(FS.ButtonSkins.Parts(w.Footer.OkayButton) and FS.ButtonSkins.Parts(w.Footer.CancelButton), 'footer keys')
    assert(w.Footer.OkayButton.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("prompts: the edit box backdrop is held, the money input is ringed per coin and keeps its boxes", f"""
    Fire('PLAYER_ENTERING_WORLD'); StaticPopup1:Show(); FlushTimers()
    local p = StaticPopup1
    assert(FS.CommerceSkin.state.edits[p.EditBox], 'edit not skinned')
    assert(FS.CommerceSkin.state.money[p.MoneyInputFrame], 'money not skinned')
    for _, k in ipairs({{ 'gold', 'silver', 'copper' }}) do
        local e = p.MoneyInputFrame[k]
        assert(e.Left.alpha == 0 and e.Right.alpha == 0, k .. ' art kept')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("auction house: category buttons hold the stock plate and ring the selected one pink, the sell price input is ringed per coin", f"""
    Fire('PLAYER_ENTERING_WORLD'); AuctionHouseFrame:Show(); FlushTimers()
    local ah = AuctionHouseFrame
    local S = FS.CommerceSkin.state
    assert(ah.fsCommerceAHSkin, 'not built')
    for i, b in ipairs(ah.CategoriesList.ScrollBox.frames or {{}}) do end
    local n = 0
    for b in pairs(S.filters) do n = n + 1; assert(b.NormalTexture.alpha == 0 and b.Lines.alpha == 0, 'plate kept') end
    assert(n == 3, 'filters skinned: ' .. n)
    assert(S.money[ah.ItemSellFrame.PriceInput.MoneyInputFrame], 'price input not skinned')
    assert(ah.ItemSellFrame.PriceInput.MoneyInputFrame.GoldBox.Left.alpha == 0, 'box art kept')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("auction house: an addon tab made by LibAHTab wears the strip tab skin, a later one too, and its page is swept", f"""
    local function MakeTab(parent, label)
        local t = CreateFrame('Button', nil, parent)
        t:SetSize(90, 32)
        for _, k in ipairs({{ 'Left', 'Middle', 'Right', 'LeftActive', 'MiddleActive', 'RightActive' }}) do
            t[k] = t:CreateTexture(nil, 'BACKGROUND')
        end
        t.Text = t:CreateFontString(nil, 'OVERLAY')
        t.Text:SetFont('Fonts/FRIZQT__.TTF', 12, ''); t.Text:SetText(label)
        t.frameRef = CreateFrame('Frame', nil, AuctionHouseFrame)
        t.frameRef:Hide()
        return t
    end
    local lib = {{ internalState = {{ Tabs = {{}} }} }}
    function lib:CreateTab(id)
        local t = MakeTab(AuctionHouseFrame, id)
        table.insert(self.internalState.Tabs, t)
        return t
    end
    LibStub = {{ GetLibrary = function(_, name) if name == 'LibAHTab-1-0' then return lib end end }}
    lib:CreateTab('Shopping')
    Fire('PLAYER_ENTERING_WORLD'); AuctionHouseFrame:Show(); FlushTimers()
    local first = lib.internalState.Tabs[1]
    assert(FS.TabSkins.Parts(first), 'addon tab not skinned')
    assert(first.Left.alpha == 0, 'stock tab art kept')
    assert(first.frameRef.fsAddonTabSweep, 'page not swept')
    lib:CreateTab('Selling'); FlushTimers()
    assert(FS.TabSkins.Parts(lib.internalState.Tabs[2]), 'later addon tab not skinned')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "bank": "Fire('PLAYER_ENTERING_WORLD'); BankFrame:Show(); BankCleanUpConfirmationPopup:Show(); FlushTimers(); return DumpOps({ BankFrame, BankCleanUpConfirmationPopup })",
    "bank-purchase": "Fire('PLAYER_ENTERING_WORLD'); BankFrame:Show(); BankPanel.PurchasePrompt:Show(); FlushTimers(); return DumpOps({ BankFrame })",
    "split": "Fire('PLAYER_ENTERING_WORLD'); StackSplitFrame:Show(); StaticPopup1:Show(); ColorPickerFrame:Show(); FlushTimers(); return DumpOps({ StackSplitFrame, ColorPickerFrame, StaticPopup1 })",
    "auction": "Fire('PLAYER_ENTERING_WORLD'); AuctionHouseFrame:Show(); FlushTimers(); return DumpOps({ AuctionHouseFrame })",
    "vendor": "Fire('PLAYER_ENTERING_WORLD'); MerchantFrame:Show(); MerchantFrame_Update(); FlushTimers(); return DumpOps({ MerchantFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("commerce skin", SCENES))
