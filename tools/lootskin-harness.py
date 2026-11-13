#!/usr/bin/env python3
"""Runs the real Modules/Skins/Loot.lua headless against a mock loot window (tools/charskin_support.py).

Pinned: the loot window wears the panel skin with a `stuwave://loot` band and keeps its close key; every pooled row (item and
money) gets a cut card, a quality LED rail, five signal pips lit to the quality and the slot layer of the item button, while the
stock card art, quality stripe and highlight art are held; the item name keeps the stock vertex tint (white mono base); a row the
stock code re-inits repaints; a locked slot swaps the pips for an amber die; hover lights the card edge; nothing is written on a
Blizzard widget (no script, no attribute); a second scan builds nothing; nothing is built in combat.
Run `python3 tools/lootskin-harness.py [--png debug/loot]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard
local QUALITY_NAMES = { [0] = "Poor", "Common", "Uncommon", "Rare", "Epic", "Legendary" }
-- slot 1 coin, then four items: { texture, name, quantity, currencyID, quality, locked }
LOOT = {
    { "Interface\\Icons\\inv_misc_coin_01", "41 silver 12 copper", 1, nil, 1, false, "money" },
    { "Interface\\Icons\\inv_jewelry_trinket_01", "Cracked Totem Charm", 1, nil, 3, false },
    { "Interface\\Icons\\inv_misc_monsterscales_01", "Thunder Lizard Tail", 2, nil, 1, false },
    { "Interface\\Icons\\inv_bracer_01", "Stonehoof Wrist Wraps", 1, nil, 2, true },
    { "Interface\\Icons\\inv_misc_pelt_wolf_01", "Tattered Wolf Pelt", 1, nil, 0, false },
}
function GetLootSlotInfo(i) local l = LOOT[i]; return l[1], l[2], l[3], l[4], l[5], l[6] end
function GetNumLootItems() return #LOOT end
function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^LootFrame") or k:find("^GroupLoot") or k:find("^MasterLooter") or k:find("^GroupLootHistory")) then _G[k] = nil end
    end
    local win = blz("Frame", "LootFrame", UIParent, 220, 290)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 300, y = -100 }
    win.shown = false
    win.NineSlice = blz("Frame", nil, win, 220, 290)
    atex(win.NineSlice, nil, "BORDER", "UI-Frame-InnerTopLeft", 20, 20)
    win.Bg = tex(win, nil, "BACKGROUND")
    win.TitleContainer = blz("Frame", nil, win, 200, 20, "TOPLEFT", 10, -1)
    win.TitleContainer.TitleText = fstring(win.TitleContainer, nil, "ITEMS", 12)
    local close = blz("Button", "LootFrameClosePanelButton", win, 24, 24, "TOPRIGHT", -2, -2)
    tex(close, nil, "BACKGROUND")
    close.scripts.OnClick = function() win:Hide() end
    win.ClosePanelButton = close
    local box = blz("Frame", nil, win, 214, 260, "TOPLEFT", 4, -22)
    box.ScrollTarget = blz("Frame", nil, box, 214, 1)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function() end
    box.FullUpdate = function() end
    box.SetDataProvider = function() end
    box.upper = tex(box, nil, "OVERLAY")
    box.lower = tex(box, nil, "OVERLAY")
    box.GetUpperShadowTexture = function(self) return self.upper end
    box.GetLowerShadowTexture = function(self) return self.lower end
    win.ScrollBox = box
    local bar = blz("Frame", nil, win, 16, 240, "TOPLEFT", 204, -28)
    bar.shown = false
    win.ScrollBar = bar
    local function item(row, i)
        local b = blz("Button", nil, row, 37, 37, "TOPLEFT", 5, -4)
        b.icon = tex(b, nil, "BORDER")
        b.NormalTexture = tex(b, nil, "ARTWORK")
        b.IconBorder = tex(b, nil, "OVERLAY")
        b.IconQuestTexture = tex(b, nil, "OVERLAY")
        b.Count = fstring(b, nil, "", 12, { 1, 1, 1, 1 })
        b.Count.points[1] = { point = "BOTTOMRIGHT", rel = b, relPoint = "BOTTOMRIGHT", x = -5, y = 2 }
        b.GetNormalTexture = function(self) return self.NormalTexture end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        b.scripts.OnClick = function() end
        b.scripts.OnMouseDown = function() end
        b.scripts.OnMouseUp = function() end
        return b
    end
    local function lootRow(i)
        local data = LOOT[i]
        local row = blz("Frame", nil, box.ScrollTarget, 202, 46, "TOPLEFT", 6, -(6 + (i - 1) * 48))
        row.slot = i
        row.NameFrame = atex(row, nil, "BACKGROUND", "looting_itemcard_bg", 202, 46)
        row.BorderFrame = atex(row, nil, "BORDER", "looting_itemcard_stroke_normal", 202, 46)
        row.IconQuestTexture = tex(row, nil, "OVERLAY")
        row.HighlightNameFrame = atex(row, nil, "OVERLAY", "looting_itemcard_stroke_clickstate", 202, 46)
        row.HighlightNameFrame.shown = false
        row.PushedNameFrame = atex(row, nil, "OVERLAY", "looting_itemcard_stroke_clickstate", 202, 46)
        row.PushedNameFrame.shown = false
        row.Item = item(row, i)
        row.Text = fstring(row, nil, "", 12, { 1, 0.82, 0, 1 })
        row.Text.w, row.Text.h = 150, 30
        row.Text.points[1] = { point = "TOPLEFT", rel = row.Item, relPoint = "TOPRIGHT", x = 8, y = -8 }
        if data[7] ~= "money" then
            row.QualityStripe = atex(row, nil, "BACKGROUND", "looting_raritytag_frame", 100, 13)
            row.QualityStripe.points[1] = { point = "TOPRIGHT", rel = row, relPoint = "TOPRIGHT", x = 0, y = 0 }
            row.QualityText = fstring(row, nil, "", 10, { 1, 1, 1, 1 })
            row.QualityText.points[1] = { point = "TOPRIGHT", rel = row, relPoint = "TOPRIGHT", x = -4, y = -2 }
        end
        row.GetSlotIndex = function(self) return self.slot end
        row.GetQuality = function(self) return LOOT[self.slot][5] end
        row.Init = function(self)
            local d = LOOT[self.slot]
            self.Text:SetText(d[2])
            self.Text:SetVertexColor(1, 1, 1, 1)
            self.Item.icon.path = d[1]
            if self.QualityText then self.QualityText:SetText(QUALITY_NAMES[d[5]]) end
            self.Item.Count:SetText(d[3] > 1 and d[3] or "")
        end
        row:Init()
        box.rows[#box.rows + 1] = row
        return row
    end
    for i = 1, #LOOT do lootRow(i) end
    win.rebuildRow = function(self, i) return lootRow(i) end
    if BuildRolls then BuildRolls() end
    if BuildHistory then BuildHistory() end
end


-- the roll history panel, as LootHistory.xml builds it (261 x 590, rows of 218 x 58)
HISTORY = {
    { name = "Cracked Totem Charm", itemHyperlink = 3, state = "winner", who = "Brannoch" },
    { name = "Stonehoof Wrist Wraps", itemHyperlink = 2, state = "pending", who = "Veyra" },
    { name = "Hawk Feather", itemHyperlink = 1, state = "passed" },
}
function BuildHistory()
    local win = blz("Frame", "GroupLootHistoryFrame", UIParent, 261, 590)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 150, y = -150 }
    win.shown = false
    win.NineSlice = blz("Frame", nil, win, 261, 590)
    atex(win.NineSlice, nil, "BORDER", "UI-Frame-InnerTopLeft", 20, 20)
    win.Bg = tex(win, nil, "BACKGROUND")
    win.TitleContainer = blz("Frame", nil, win, 240, 20, "TOPLEFT", 10, -1)
    win.TitleContainer.TitleText = fstring(win.TitleContainer, nil, "Loot Rolls", 12)
    local close = blz("Button", "GroupLootHistoryFrameClosePanelButton", win, 24, 24, "TOPRIGHT", -2, -2)
    tex(close, nil, "BACKGROUND")
    close.scripts.OnClick = function() win:Hide() end
    win.ClosePanelButton = close
    local drop = blz("Button", nil, win, 160, 22, "TOP", 1, -32)
    drop.points[1] = { point = "TOP", rel = win, relPoint = "TOP", x = 1, y = -32 }
    tex(drop, nil, "BACKGROUND")
    win.EncounterDropdown = drop
    local timer = blz("Frame", nil, win, 238, 13, "TOP", 0, -56)
    timer.points[1] = { point = "TOP", rel = drop, relPoint = "BOTTOM", x = 0, y = 0 }
    timer.Background = atex(timer, nil, "BACKGROUND", "lootroll-timer-background", 238, 13)
    timer.Fill = atex(timer, nil, "ARTWORK", "lootroll-timer-fill", 190, 9)
    timer.Border = atex(timer, nil, "OVERLAY", "lootroll-timer-border", 238, 13)
    win.Timer = timer
    local resize = blz("Button", nil, win, 32, 12, "TOP", 0, 3)
    resize.points[1] = { point = "TOP", rel = win, relPoint = "BOTTOM", x = 0, y = 3 }
    atex(resize, nil, "OVERLAY", "lootroll-resizehandle", 32, 12)
    resize.scripts.OnMouseDown = function() end
    win.ResizeButton = resize
    local box = blz("Frame", nil, win, 232, 496, "TOPLEFT", 6, -90)
    box.ScrollTarget = blz("Frame", nil, box, 232, 1)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function() end
    win.ScrollBox = box
    local bar = blz("Frame", nil, win, 16, 480, "TOPLEFT", 240, -88)
    bar.shown = false
    win.ScrollBar = bar
    for i, h in ipairs(HISTORY) do
        local row = blz("Frame", nil, box.ScrollTarget, 218, 58, "TOPLEFT", 0, -((i - 1) * 60))
        row.Item = blz("Button", nil, row, 48, 48, "LEFT", 6, 0)
        row.Item.icon = tex(row.Item, nil, "BORDER")
        row.Item.NormalTexture = tex(row.Item, nil, "ARTWORK")
        row.Item.IconBorder = tex(row.Item, nil, "OVERLAY")
        row.Item.Count = fstring(row.Item, nil, "", 12, { 1, 1, 1, 1 })
        row.Item.GetNormalTexture = function(self) return self.NormalTexture end
        row.Item.scripts.OnEnter = function() end
        row.Item.scripts.OnLeave = function() end
        row.BackgroundArtFrame = blz("Frame", nil, row, 218, 58, "TOPLEFT", 0, 0)
        row.BackgroundArtFrame.NameFrame = atex(row.BackgroundArtFrame, nil, "BACKGROUND", "looting_itemcard_bg", 218, 58)
        row.BackgroundArtFrame.BorderFrame = atex(row.BackgroundArtFrame, nil, "BORDER", "lootroll-itementry-background", 218, 58)
        row.ItemName = fstring(row, nil, "", 12, { 1, 0.82, 0, 1 })
        row.ItemName.w, row.ItemName.h = 150, 32
        row.ItemName.points[1] = { point = "TOPLEFT", rel = row.Item, relPoint = "TOPRIGHT", x = 6, y = -2 }
        row.WinningRollInfo = blz("Frame", nil, row, 1, 1, "BOTTOMRIGHT", -7, 14)
        row.WinningRollInfo.WinningRoll = fstring(row.WinningRollInfo, nil, "", 12, { 1, 0.82, 0, 1 })
        row.WinningRollInfo.Check = atex(row.WinningRollInfo, nil, "ARTWORK", "lootroll-icon-checkmark", 16, 14)
        row.PendingRollInfo = blz("Frame", nil, row, 1, 1, "BOTTOMRIGHT", -7, 14)
        row.PendingRollInfo.CurrentWinnerText = fstring(row.PendingRollInfo, nil, "", 12, { 0.5, 0.5, 0.5, 1 })
        row.PendingRollInfo.WaitDot1 = atex(row.PendingRollInfo, nil, "ARTWORK", "lootroll-pendingdot", 4, 4)
        row.PendingRollInfo.WaitDot2 = atex(row.PendingRollInfo, nil, "ARTWORK", "lootroll-pendingdot", 4, 4)
        row.AllPassedInfo = blz("Frame", nil, row, 1, 1, "BOTTOMRIGHT", -7, 14)
        row.AllPassedInfo.AllPassedText = fstring(row.AllPassedInfo, nil, "All passed", 12, { 1, 0.1, 0.1, 1 })
        row.AllPassedInfo.Icon = atex(row.AllPassedInfo, nil, "ARTWORK", "lootroll-icon-checkmark", 15, 13)
        for _, pair in ipairs({ { row.WinningRollInfo, row.WinningRollInfo.WinningRoll }, { row.PendingRollInfo, row.PendingRollInfo.CurrentWinnerText },
            { row.AllPassedInfo, row.AllPassedInfo.AllPassedText } }) do
            pair[2].points[1] = { point = "RIGHT", rel = pair[1], relPoint = "RIGHT", x = 0, y = 0 }
        end
        row.PlayerRoll = blz("Frame", nil, row, 37, 33, "CENTER", 5, -4)
        row.PlayerRoll.PlayerRollIcon = tex(row.PlayerRoll, nil, "OVERLAY")
        row.Init = function(self, drop)
            self.dropInfo = drop
            self.ItemName:SetText(drop.name)
            self.ItemName:SetVertexColor(1, 1, 1, 1)
            self.Item.icon.path = "Interface\\Icons\\inv_misc_gem_01"
            self.WinningRollInfo:SetShown(drop.state == "winner")
            self.PendingRollInfo:SetShown(drop.state == "pending")
            self.AllPassedInfo:SetShown(drop.state == "passed")
            if drop.who then
                self.WinningRollInfo.WinningRoll:SetText(drop.who)
                self.PendingRollInfo.CurrentWinnerText:SetText(drop.who)
            end
        end
        row.GetElementData = function() return h end
        row:Init(h)
        box.rows[#box.rows + 1] = row
    end
    C_Item = C_Item or {}
    C_Item.GetItemQualityByID = function(link) return link end
end

-- the four group loot roll frames, as GroupLootFrameTemplate builds them (277 x 67)
ROLLS = {
    { "Interface\\Icons\\inv_jewelry_trinket_01", "Cracked Totem Charm", 1, 3, true, true, true, false },
    { "Interface\\Icons\\inv_bracer_01", "Stonehoof Wrist Wraps", 1, 2, true, true, true, false },
    { "Interface\\Icons\\inv_belt_01", "Palemane Plate Girdle", 1, 3, false, true, true, false },
    { "Interface\\Icons\\inv_sword_01", "Bristleback Cleaver", 1, 2, false, false, true, true },
}
function GetLootRollItemInfo(id)
    local r = ROLLS[id]
    return r[1], r[2], r[3], r[4], false, r[5], r[6], false, 0, 0, 0, 0, r[8]
end
function BuildRolls()
    for i = 1, 4 do
        local f = blz("Frame", "GroupLootFrame" .. i, UIParent, 277, 67, "CENTER", 0, 0)
        f.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -(100 + (i - 1) * 78) }
        f.shown = false
        f.id = i
        f.Background = tex(f, nil, "BACKGROUND")
        f.Border = tex(f, nil, "BORDER")
        f.Border.w, f.Border.h = 286, 76
        f.Border.points[1] = { point = "CENTER", rel = f, relPoint = "CENTER", x = 0, y = 0 }
        f.Name = fstring(f, nil, "Item Name", 12, { 1, 0.82, 0, 1 })
        f.Name.w, f.Name.h = 125, 30
        f.Name.points[1] = { point = "TOPLEFT", rel = f, relPoint = "TOPLEFT", x = 60, y = -15 }
        local icon = blz("Button", nil, f, 34, 34, "TOPLEFT", 10, -13)
        icon.Icon = tex(icon, nil, "ARTWORK")
        icon.Count = fstring(icon, nil, "", 12, { 1, 1, 1, 1 })
        icon.Count.points[1] = { point = "BOTTOMRIGHT", rel = icon, relPoint = "BOTTOMRIGHT", x = -5, y = 2 }
        icon.Border = atex(icon, nil, "OVERLAY", "loottoast-itemborder-green", 42, 42)
        icon.Border.points[1] = { point = "CENTER", rel = icon, relPoint = "CENTER", x = 0, y = 0 }
        icon.scripts.OnEnter = function() end
        icon.scripts.OnLeave = function() end
        icon.scripts.OnClick = function() end
        f.IconFrame = icon
        f.LootButtons = {}
        local function key(name, id, atlas, point, relTo, relPoint, x, y)
            local b = blz("Button", nil, f, 32, 32, point, x, y)
            b.points[1] = { point = point, rel = relTo, relPoint = relPoint, x = x, y = y }
            b.id = id
            b.NormalTexture = atex(b, nil, "ARTWORK", "lootroll-toast-icon-" .. atlas .. "-up", 32, 32)
            b.pushedTex = atex(b, nil, "ARTWORK", "lootroll-toast-icon-" .. atlas .. "-down", 32, 32)
            b.highlightTex = atex(b, nil, "HIGHLIGHT", "lootroll-toast-icon-" .. atlas .. "-highlight", 32, 32)
            b.GetNormalTexture = function(self) return self.NormalTexture end
            b.scripts.OnClick = function() end
            b.scripts.OnEnter = function() end
            b.scripts.OnLeave = function() end
            f.LootButtons[#f.LootButtons + 1] = b
            return b
        end
        f.NeedButton = key("NeedButton", 1, "need", "TOPRIGHT", f, "TOPRIGHT", -44, -6)
        f.PassButton = key("PassButton", 0, "pass", "LEFT", f.NeedButton, "RIGHT", 6, 2)
        f.GreedButton = key("GreedButton", 2, "greed", "TOP", f.NeedButton, "BOTTOM", 0, 5)
        f.TransmogButton = key("TransmogButton", 4, "transmog", "CENTER", f.GreedButton, "CENTER", 0, 0)
        local t = blz("StatusBar", nil, f, 190, 8, "BOTTOMLEFT", 3, 2)
        t.points[1] = { point = "BOTTOMLEFT", rel = f, relPoint = "BOTTOMLEFT", x = 3, y = 2 }
        t.Background = tex(t, nil, "BACKGROUND")
        t.barTex = tex(t, nil, "ARTWORK")
        t.lo, t.hi, t.value = 0, 60000, 0
        t.SetMinMaxValues = function(self, a, b) self.lo, self.hi = a, b end
        t.GetMinMaxValues = function(self) return self.lo, self.hi end
        t.SetValue = function(self, v) self.value = v end
        t.GetValue = function(self) return self.value end
        t.GetStatusBarTexture = function(self) return self.barTex end
        t.SetStatusBarColor = function() end
        f.Timer = t
        f.NeedRollAnim = blz("Frame", nil, f, 128, 128, "CENTER", 0, 0)
        f.NeedRollAnim.shown = false
        f.NeedRollAnim.RollNumber = fstring(f.NeedRollAnim, nil, "", 32)
        f.scripts.OnShow = function(self)
            local tx, name, count, quality, bop, canNeed, canGreed, canDE, _, _, _, _, canTransmog = GetLootRollItemInfo(self.rollID)
            self.IconFrame.Icon.path = tx
            self.Name:SetText(name)
            self.Name:SetVertexColor(1, 1, 1, 1)
            self.IconFrame.Count:SetText(count > 1 and count or "")
            self.NeedButton:SetEnabled(canNeed)
            self.TransmogButton:SetShown(canTransmog)
            self.GreedButton:SetShown(not canTransmog)
            self.GreedButton:SetEnabled(canGreed)
        end
    end
    function OpenRoll(i, left)
        local f = _G["GroupLootFrame" .. i]
        f.rollID = i
        f.Timer:SetMinMaxValues(0, 60000)
        f.Timer:SetValue(left or 60000)
        f:Show()
        return f
    end
end
"""

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "Character": "Modules/Skins/Character.lua",
             "GroupKit": "Modules/Skins/GroupKit.lua", "Loot": "Modules/Skins/Loot.lua", "LootRolls": "Modules/Skins/LootRolls.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); LootFrame:Show(); FlushTimers()"

case("the window wears the panel skin with a loot band, its stock art is stripped and its close key skinned", f"""
    {OPEN}
    local w = LootFrame
    assert(w.fsSkinCache, 'no panel chrome')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText() == 'stuwave://loot', 'band label ' .. tostring(w.fsPanelTitle and w.fsPanelTitle:GetText()))
    assert(w.NineSlice.shown == false and w.Bg.shown == false, 'stock chrome kept')
    assert(FS.ButtonSkins.Parts(w.ClosePanelButton), 'close key not skinned')
    assert(w.ClosePanelButton.scripts.OnClick, 'close click lost')
    assert(w.ScrollBox.upper.alpha == 0 and w.ScrollBox.lower.alpha == 0, 'scroll shadows kept')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("every row holds the stock card art and wears a card, a quality rail and the slot layer", f"""
    {OPEN}
    local S = FS.LootSkin.state
    for i, r in ipairs(LootFrame.ScrollBox.rows) do
        local rec = S.rows[r]
        assert(rec, 'row ' .. i .. ' not skinned')
        for _, k in ipairs({{ 'NameFrame', 'BorderFrame', 'HighlightNameFrame', 'PushedNameFrame' }}) do
            assert(r[k].alpha == 0, 'row ' .. i .. ' kept ' .. k)
        end
        if r.QualityStripe then assert(r.QualityStripe.alpha == 0, 'quality stripe kept on row ' .. i) end
        assert(rec.plate and rec.led and rec.band, 'row ' .. i .. ' lacks card or rail')
        assert(r.Item.IconBorder.alpha == 0 and r.Item.NormalTexture.alpha == 0, 'slot art kept on row ' .. i)
        assert(FS.ItemSlotSkins.Parts(r.Item), 'slot layer missing on row ' .. i)
        assert(r.Item.scripts.OnClick, 'click lost on row ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("the name is mono on a white base so the stock quality tint shows, the rarity word is muted mono", f"""
    {OPEN}
    for i, r in ipairs(LootFrame.ScrollBox.rows) do
        assert(r.Text.fontPath ~= 'stock.ttf', 'name not mono on row ' .. i)
        local c = r.Text.textColor
        assert(c[1] > 0.9 and c[2] > 0.9 and c[3] > 0.9, 'name base not white on row ' .. i)
        if r.QualityText then
            assert(r.QualityText.fontPath ~= 'stock.ttf', 'rarity word not mono on row ' .. i)
            assert(r.QualityText.textColor[1] < 0.7, 'rarity word not muted on row ' .. i)
        end
    end
""")

case("the rail and the five pips take the item quality: lit pips = quality (at least one), the rest dark", f"""
    {OPEN}
    local S = FS.LootSkin.state
    local want = {{ [1] = 0, [2] = 3, [3] = 1, [4] = 2, [5] = 1 }}
    for i, r in ipairs(LootFrame.ScrollBox.rows) do
        local rec = S.rows[r]
        assert(#rec.pips == 5, 'pip count ' .. #rec.pips)
        assert(rec.litCount == want[i], 'row ' .. i .. ' lit ' .. tostring(rec.litCount) .. ' want ' .. want[i])
    end
    local rare = S.rows[LootFrame.ScrollBox.rows[2]].ledColor
    assert(rare[3] > 0.9 and rare[1] < 0.3, 'rare rail not blue')
    local coin = S.rows[LootFrame.ScrollBox.rows[1]]
    assert(coin.ledColor[1] > 0.9 and coin.ledColor[2] > 0.7 and coin.ledColor[3] < 0.5, 'money rail not gold')
    for _, p in ipairs(coin.pips) do assert(not p.shown, 'pips on the coin row') end
""")

case("a row the stock code re-inits for another item repaints its rail and pips", f"""
    {OPEN}
    local S = FS.LootSkin.state
    local r = LootFrame.ScrollBox.rows[5]
    assert(S.rows[r].litCount == 1)
    LOOT[5][5] = 4; LOOT[5][2] = 'Epic Thing'
    r:Init()
    assert(S.rows[r].litCount == 4, 'pips not repainted: ' .. tostring(S.rows[r].litCount))
    local c = S.rows[r].ledColor
    assert(c[1] > 0.6 and c[3] > 0.9, 'rail not epic violet')
""")

case("a locked slot (still in a roll) shows an amber die in place of the pips", f"""
    {OPEN}
    local S = FS.LootSkin.state
    local locked = S.rows[LootFrame.ScrollBox.rows[4]]
    local open = S.rows[LootFrame.ScrollBox.rows[2]]
    assert(locked.die and locked.die.shown, 'no die on the locked row')
    assert(not (open.die and open.die.shown), 'die on an open row')
    for _, p in ipairs(locked.pips) do assert(not p.shown, 'pips kept on the locked row') end
    for _, p in ipairs(open.pips) do assert(p.shown, 'pips hidden on the open row') end
""")

case("hovering the item lights the card edge cyan and leaving puts it back", f"""
    {OPEN}
    local S = FS.LootSkin.state
    local r = LootFrame.ScrollBox.rows[2]
    local rec = S.rows[r]
    local idle = {{ rec.plate.ring.vertex[1], rec.plate.ring.vertex[2], rec.plate.ring.vertex[3] }}
    r.Item:RunScript('OnEnter')
    local v = rec.plate.ring.vertex
    assert(v[1] < 0.3 and v[2] > 0.8 and v[3] > 0.9, 'hover edge not cyan')
    r.Item:RunScript('OnLeave')
    v = rec.plate.ring.vertex
    assert(v[1] == idle[1] and v[2] == idle[2] and v[3] == idle[3], 'edge not restored')
""")

case("nothing is written on a Blizzard widget and a second scan builds nothing", f"""
    {OPEN}
    local n = ObjCount()
    Fire('PLAYER_ENTERING_WORLD'); LootFrame:Hide(); LootFrame:Show(); FlushTimers()
    LootFrame.ScrollBox:Update(); FlushTimers()
    assert(ObjCount() == n, 'rebuilt ' .. (ObjCount() - n) .. ' objects')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'GroupKit', 'Loot', 'LootRolls' }})
    assert(not LootFrame.fsSkinCache, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(LootFrame.fsSkinCache, 'not built when combat ended')
""")

case("every edge a row skin draws lands on a whole screen pixel from the row's right and bottom edge, at 1.2 and at 1.0", f"""
    {OPEN}
    local r = LootFrame.ScrollBox.rows[2]
    local rec = FS.LootSkin.state.rows[r]
    for _, scale in ipairs({{ 1.2, 1.0 }}) do
        PPU = scale
        FS.ControlKit.Reseat()
        local _, _, W, H = Px(r, r)
        local n = 0
        for _, p in ipairs(rec.pips) do
            local l, t, rr, b = Px(p, r)
            for _, v in ipairs({{ W - rr, H - b, rr - l, b - t }}) do
                assert(Near(v, math.floor(v + 0.5), 0.02), 'pip edge ' .. v .. ' at scale ' .. scale)
            end
            n = n + 1
        end
        assert(n == 5)
    end
""")


OPEN_ROLLS = "Fire('PLAYER_ENTERING_WORLD'); FlushTimers(); for i = 1, 4 do OpenRoll(i) end; FlushTimers()"

case("roll frames: the stock toast art is held, each wears a card and a quality rail, the icon the slot layer", f"""
    {OPEN_ROLLS}
    local S = FS.LootRollSkin.state
    for i = 1, 4 do
        local f = _G['GroupLootFrame' .. i]
        local rec = S.frames[f]
        assert(rec, 'frame ' .. i .. ' not skinned')
        assert(f.Background.alpha == 0 and f.Border.alpha == 0, 'toast art kept on ' .. i)
        assert(f.IconFrame.Border.alpha == 0, 'icon border kept on ' .. i)
        assert(f.Timer.Background.alpha == 0 and f.Timer.barTex.alpha == 0, 'stock bar kept on ' .. i)
        assert(rec.plate and rec.led and rec.band, 'card or rail missing on ' .. i)
        assert(FS.ItemSlotSkins.Parts(f.IconFrame), 'slot layer missing on ' .. i)
        assert(f.IconFrame.scripts.OnClick, 'icon click lost on ' .. i)
        assert(f.Name.fontPath ~= 'stock.ttf' and f.Name.textColor[3] > 0.9, 'name not white mono on ' .. i)
    end
    local rare, uncommon = S.frames[GroupLootFrame1].ledColor, S.frames[GroupLootFrame2].ledColor
    assert(rare[3] > 0.9 and uncommon[2] > 0.9 and uncommon[1] < 0.3, 'rail colours')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("roll keys: need cyan die, greed gold coin, transmog gold star, pass pink cross, each a cut key over the stock button", f"""
    {OPEN_ROLLS}
    local S = FS.LootRollSkin.state
    local f = GroupLootFrame1
    local want = {{ NeedButton = 'die', GreedButton = 'coin', PassButton = 'x', TransmogButton = 'star' }}
    for key, glyph in pairs(want) do
        local b = f[key]
        local k = S.keys[b]
        assert(k and k.plate and k.glyph and k.glyph.name == glyph, key .. ' not a ' .. glyph .. ' key')
        assert(b.NormalTexture.alpha == 0 and b.pushedTex.alpha == 0 and b.highlightTex.alpha == 0, key .. ' stock art kept')
        assert(b.scripts.OnClick, key .. ' click lost')
    end
    local need, pass = S.keys[f.NeedButton], S.keys[f.PassButton]
    assert(need.color[3] > 0.9 and need.color[1] < 0.3, 'need not cyan')
    assert(pass.color[1] > 0.9 and pass.color[3] > 0.4 and pass.color[2] < 0.4, 'pass not pink')
    assert(S.keys[f.GreedButton].color[1] > 0.9 and S.keys[f.GreedButton].color[3] < 0.4, 'greed not gold')
""")

case("a need roll the player cannot make dims its key (steel glyph, no LED); hover lights an enabled key", f"""
    {OPEN_ROLLS}
    local S = FS.LootRollSkin.state
    local f = GroupLootFrame3
    local k = S.keys[f.NeedButton]
    assert(not f.NeedButton:IsEnabled(), 'stub: need should be off on frame 3')
    assert(k.glyph.rects[1].color[1] < 0.7 and k.glyph.rects[1].color[3] > 0.5 and k.glyph.rects[1].color[2] > 0.5, 'glyph not steel')
    assert(k.led.alpha == 0 or not k.led.shown, 'LED lit on a blocked key')
    local g = S.keys[f.GreedButton]
    local idle = g.plate.ring.vertex[1]
    f.GreedButton:RunScript('OnEnter')
    assert(g.plate.ring.vertex[1] ~= idle or g.plate.ring.vertex[2] ~= 0.165, 'hover did not repaint')
    f.GreedButton:RunScript('OnLeave')
""")

case("a transmog roll shows the transmog key where greed was and still skins both", f"""
    {OPEN_ROLLS}
    local f = GroupLootFrame4
    assert(f.TransmogButton.shown and not f.GreedButton.shown, 'stub: transmog roll')
    local S = FS.LootRollSkin.state
    assert(S.keys[f.TransmogButton] and S.keys[f.GreedButton], 'a key is missing')
""")

case("the fuse follows the stock timer: cyan, amber under 35 percent, pink under 10 percent with a pink card edge", f"""
    {OPEN_ROLLS}
    local S = FS.LootRollSkin.state
    local f = GroupLootFrame1
    local rec = S.frames[f]
    local function colour(t) return t.color or {{ 0, 0, 0, 0 }} end
    f.Timer:SetValue(48000)
    assert(colour(rec.fuse)[3] > 0.9 and colour(rec.fuse)[1] < 0.3, 'fuse not cyan at 80 percent')
    f.Timer:SetValue(18000)
    assert(colour(rec.fuse)[1] > 0.9 and colour(rec.fuse)[2] > 0.6 and colour(rec.fuse)[3] < 0.5, 'fuse not amber at 30 percent')
    f.Timer:SetValue(3000)
    local c = colour(rec.fuse)
    assert(c[1] > 0.9 and c[2] < 0.4 and c[3] > 0.4, 'fuse not pink at 5 percent')
    assert(rec.plate.ring.vertex[1] > 0.9 and rec.plate.ring.vertex[2] < 0.4, 'card edge not pink under 10 percent')
    -- the width follows the value
    f.Timer:SetValue(30000)
    local _, _, w = Px(rec.fuse, rec.fuse)
    local _, _, tw = Px(rec.track, rec.track)
    assert(math.abs(w / tw - 0.5) < 0.03, 'fuse width ' .. w .. ' of ' .. tw)
    f.Timer:SetValue(0)
    local _, _, w0 = Px(rec.fuse, rec.fuse)
    assert(w0 <= 1, 'fuse not empty at zero')
""")

case("roll frames: nothing is written on a Blizzard widget, a second pass builds nothing, nothing is built in combat", f"""
    {OPEN_ROLLS}
    local n = ObjCount()
    for i = 1, 4 do _G['GroupLootFrame' .. i]:Hide(); _G['GroupLootFrame' .. i]:Show() end
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(ObjCount() == n, 'rebuilt ' .. (ObjCount() - n))
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'GroupKit', 'Loot', 'LootRolls' }})
    assert(not _G.FS.LootRollSkin.state.frames[GroupLootFrame1], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(_G.FS.LootRollSkin.state.frames[GroupLootFrame1], 'not built when combat ended')
""")


OPEN_HISTORY = "Fire('PLAYER_ENTERING_WORLD'); GroupLootHistoryFrame:Show(); FlushTimers()"

case("history: the panel skin with a rolls band, stock timer art held and its fill tinted cyan, the resize grip drawn by us", f"""
    {OPEN_HISTORY}
    local w = GroupLootHistoryFrame
    assert(w.fsSkinCache, 'no panel chrome')
    assert(w.fsPanelTitle and w.fsPanelTitle:GetText() == 'stuwave://rolls', 'band label')
    assert(FS.ButtonSkins.Parts(w.ClosePanelButton), 'close key')
    assert(w.Timer.Background.alpha == 0 and w.Timer.Border.alpha == 0, 'timer art kept')
    assert(w.Timer.Fill.vertex and w.Timer.Fill.vertex[3] > 0.9 and w.Timer.Fill.vertex[1] < 0.3, 'timer fill not cyan')
    assert(w.ResizeButton.scripts.OnMouseDown, 'resize click lost')
    assert(FS.LootRollSkin.state.grip, 'no resize grip')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("history: every row is a card with a quality rail, the slot layer, mono texts and the stock art held", f"""
    {OPEN_HISTORY}
    local S = FS.LootRollSkin.state
    for i, r in ipairs(GroupLootHistoryFrame.ScrollBox.rows) do
        local rec = S.rows[r]
        assert(rec and rec.plate and rec.led, 'row ' .. i .. ' not a card')
        assert(r.BackgroundArtFrame.NameFrame.alpha == 0 and r.BackgroundArtFrame.BorderFrame.alpha == 0, 'row art kept on ' .. i)
        assert(FS.ItemSlotSkins.Parts(r.Item), 'slot layer missing on ' .. i)
        assert(r.ItemName.fontPath ~= 'stock.ttf' and r.ItemName.textColor[3] > 0.9, 'name on ' .. i)
        assert(r.WinningRollInfo.WinningRoll.fontPath ~= 'stock.ttf', 'winner text on ' .. i)
        assert(r.AllPassedInfo.AllPassedText.fontPath ~= 'stock.ttf', 'passed text on ' .. i)
    end
    local rare = S.rows[GroupLootHistoryFrame.ScrollBox.rows[1]].ledColor
    assert(rare[3] > 0.9 and rare[1] < 0.3, 'rare rail')
    -- the stock re-init for another drop repaints the rail
    local r = GroupLootHistoryFrame.ScrollBox.rows[3]
    r:Init({{ name = 'Epic Thing', itemHyperlink = 4, state = 'winner', who = 'Veyra' }})
    local c = S.rows[r].ledColor
    assert(c[1] > 0.6 and c[3] > 0.9, 'rail not epic after Init')
""")

case("history: nothing is written on a Blizzard widget and a second pass builds nothing", f"""
    {OPEN_HISTORY}
    local n = ObjCount()
    GroupLootHistoryFrame:Hide(); GroupLootHistoryFrame:Show(); Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(ObjCount() == n, 'rebuilt ' .. (ObjCount() - n))
""")

SCENES = {
    "loot": "Fire('PLAYER_ENTERING_WORLD'); LootFrame:Show(); FlushTimers(); return DumpOps({ LootFrame })",
    "history": "Fire('PLAYER_ENTERING_WORLD'); GroupLootHistoryFrame:Show(); FlushTimers(); return DumpOps({ GroupLootHistoryFrame })",
    "rolls": "Fire('PLAYER_ENTERING_WORLD'); FlushTimers(); OpenRoll(1, 48000); OpenRoll(2, 21000); OpenRoll(3, 18000); OpenRoll(4, 3000); FlushTimers(); return DumpOps({ GroupLootFrame1, GroupLootFrame2, GroupLootFrame3, GroupLootFrame4 })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("loot skin", SCENES))
