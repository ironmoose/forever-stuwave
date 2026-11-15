#!/usr/bin/env python3
"""Runs the real Modules/Skins/Services.lua headless against mock trainer, trade, profession, channel and flight map windows
(tools/charskin_support.py). Quest.lua is loaded with it: the shared slot, card and list helpers live there.

Pinned, per window: the trainer rows are cards with a slot on the stock icon and follow the stock selected glow, the trade slots are
square slots on cards, the profession rank bar and recipe rows lose their stock art and take a card, the channel list and roster rows
are cards that follow the stock highlight lock, the add popup is a dialog, the flight points draw a glyph by state over their
held stock icon, no script or attribute is written on a Blizzard widget, and nothing is built in combat. Run
`python3 tools/servicesskin-harness.py [--png debug/services]`. The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring, atex = BLZ.blz, BLZ.tex, BLZ.fstring, nil
local build = BuildBlizzard

function Obj:GetPoint(i)
    local p = self.points[i or 1]
    if not p then return nil end
    return p.point, p.rel, p.relPoint, p.x, p.y
end
function Obj:GetSize() return self:GetWidth(), self:GetHeight() end
function Obj:IsMouseOver() return false end
Enum = { FlightPathState = { Reachable = 0, Current = 1, Unreachable = 2 } }

local function money(parent, name, x, y)
    local m = blz("Frame", name, parent, 100, 14, "TOPLEFT", x, y)
    m.staticMoney = true
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do fstring(m, name .. k .. "ButtonText", "12", 12, { 1, 1, 1, 1 }) end
    return m
end
local function rowMoney(parent, x, y)
    local m = blz("Frame", nil, parent, 100, 14, "TOPRIGHT", x, y)
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do
        local b = blz("Button", nil, m, 30, 14, "RIGHT", 0, 0)
        b.fs = fstring(b, nil, "12", 12, { 1, 1, 1, 1 })
    end
    return m
end
local function textButton(parent, name, label, x, y, w)
    local b = blz("Button", name, parent, w or 100, 22, "TOPLEFT", x or 0, y or 0)
    for _, k in ipairs({ "Left", "Middle", "Right" }) do b[k] = tex(b, nil, "BACKGROUND") end
    b.fs = fstring(b, nil, label, 12)
    b.scripts.OnClick = function() end
    return b
end
local function scrollBox(parent, w, h, x, y)
    local box = blz("Frame", nil, parent, w, h, "TOPLEFT", x, y)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.GetView = function() return {} end
    box.Update = function() end
    return box
end

function SetItemButtonQuality(button, quality)
    if button.SetItemButtonQuality then button:SetItemButtonQuality(quality) else button.q = quality end
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^ClassTrainer") or k:find("^Trade") or k:find("^Professions") or k:find("^Channel")
            or k:find("^CreateChannel") or k:find("^Taxi") or k:find("^FlightMap")) then _G[k] = nil end
    end
    -- the class trainer: a ScrollBox of service rows, the step button, the status bar
    local win = blz("Frame", "ClassTrainerFrame", UIParent, 338, 424)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    local function service(parent, name, x, y, label, rank, state)
        local r = blz("Button", name, parent, 300, 40, "TOPLEFT", x, y)
        r.icon = tex(r, nil, "BORDER")
        r.icon.w, r.icon.h = 32, 32
        r.icon.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 4, y = 0 }
        r.icon.path = "Interface\\Icons\\spell_nature_" .. label:len()
        r.name = fstring(r, nil, label, 12, { 1, 0.82, 0, 1 })
        r.name.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 44, y = -4 }
        r.subText = fstring(r, nil, rank, 11, { 0.5, 0.5, 0.5, 1 })
        r.subText.points[1] = { point = "TOPLEFT", rel = r, relPoint = "TOPLEFT", x = 44, y = -20 }
        r.money = rowMoney(r, -4, -10)
        r.selectedTex = tex(r, nil, "BACKGROUND"); r.selectedTex.shown = (state == "selected")
        r.lock = tex(r, nil, "OVERLAY"); r.lock.shown = (state == "locked")
        r.disabledBG = tex(r, nil, "BACKGROUND"); r.disabledBG.shown = false
        r.highlightTex = tex(r, nil, "HIGHLIGHT")
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function() end
        r.scripts.OnLeave = function() end
        return r
    end
    win.BG = tex(win, nil, "BACKGROUND")
    local box = scrollBox(win, 300, 280, 10, -80)
    win.ScrollBox = box
    for i, spec in ipairs({ { "Earth Shock", "Rank 2", "" }, { "Stoneclaw Totem", "Rank 1", "" }, { "Lightning Bolt", "Rank 3", "" },
        { "Healing Wave", "Rank 2", "selected" }, { "Flametongue Weapon", "Level 14", "locked" } }) do
        box.rows[i] = service(box, nil, 0, -(i - 1) * 44, spec[1], spec[2], spec[3])
    end
    local cat = blz("Button", nil, box, 300, 24, "TOPLEFT", 0, -230)
    cat.Text = fstring(cat, nil, "Spells", 12)
    box.rows[#box.rows + 1] = cat
    win.skillStepButton = service(win, "ClassTrainerFrameSkillStepButton", 10, -350, "Healing Wave", "Rank 2", "")
    ClassTrainerFrameSkillStepButton = win.skillStepButton
    local bar = blz("StatusBar", "ClassTrainerStatusBar", win, 300, 18, "TOPLEFT", 20, -50)
    bar.rankText = fstring(bar, "ClassTrainerStatusBarSkillRank", "187 / 225", 12, { 1, 1, 1, 1 })
    for _, n in ipairs({ "Left", "Middle", "Right", "Background" }) do tex(bar, "ClassTrainerStatusBar" .. n, "BACKGROUND") end
    -- the trade window (344 x 446): seven rows a side, each a frame with a name plate and an item button, the six insets, the highlights
    local trade = blz("Frame", "TradeFrame", UIParent, 344, 446)
    trade.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 500, y = -80 }
    trade.shown = false
    local function at(f, x, y) f.points[1] = { point = "TOPLEFT", rel = trade, relPoint = "TOPLEFT", x = x, y = y } end
    local function inset(name, x1, y1, x2, y2)
        local f = blz("Frame", name, trade, x2 - x1, y1 - y2, "TOPLEFT", x1, y1)
        f.NineSlice = blz("Frame", nil, f, x2 - x1, y1 - y2)
        tex(f, nil, "BACKGROUND")
        return f
    end
    at(fstring(trade, "TradeFramePlayerNameText", "Stu", 13, { 1, 0.82, 0, 1 }), 65, -5)
    at(fstring(trade, "TradeFrameRecipientNameText", "Thessaly", 13, { 1, 0.82, 0, 1 }), 230, -5)
    at(fstring(trade, "TradeFramePlayerEnchantText", "Will not be traded", 11, { 1, 1, 1, 1 }), 15, -360)
    at(fstring(trade, "TradeFrameRecipientEnchantText", "Will not be traded", 11, { 1, 1, 1, 1 }), 181, -360)
    inset("TradePlayerItemsInset", 4, -83, 166, -352); inset("TradeRecipientItemsInset", 175, -83, 338, -352)
    inset("TradePlayerEnchantInset", 4, -354, 166, -418); inset("TradeRecipientEnchantInset", 175, -354, 338, -418)
    inset("TradePlayerInputMoneyInset", 4, -58, 166, -82); inset("TradeRecipientMoneyInset", 175, -58, 338, -81)
    local itemNames = { "Linen Cloak", "Thunder Lizard Tail", "Healing Potion", "", "", "", "Small Locked Chest" }
    for side, x in pairs({ Player = 14, Recipient = 182 }) do
        for i = 1, 7 do
            local name = "Trade" .. side .. "Item" .. i
            local y = -89 - (i - 1) * 44 - (i == 7 and 21 or 0)
            local row = blz("Frame", name, trade, 153, 37, "TOPLEFT", x, y)
            row.id = i
            row.SlotTexture = tex(row, name .. "SlotTexture", "BACKGROUND"); row.SlotTexture.w, row.SlotTexture.h = 64, 64
            row.SlotTexture.points[1] = { point = "TOPLEFT", rel = row, relPoint = "TOPLEFT", x = -13, y = 13 }
            local nf = tex(row, name .. "NameFrame", "BACKGROUND"); nf.w, nf.h = 124, 64
            nf.points[1] = { point = "LEFT", rel = row.SlotTexture, relPoint = "RIGHT", x = -20, y = 0 }
            row.Name = fstring(row, name .. "Name", (side == "Player" or i < 3) and itemNames[i] or "", 11, { 0.12, 1, 0.4, 1 })
            row.Name.w, row.Name.h = 90, 30
            row.Name.points[1] = { point = "LEFT", rel = nf, relPoint = "LEFT", x = 15, y = 0 }
            if i == 7 then tex(row, nil, "ARTWORK").w = 62 end
            local b = blz("Button", name .. "ItemButton", row, 37, 37, "TOPLEFT", 0, 0)
            b.icon = tex(b, name .. "ItemButtonIconTexture", "BORDER"); b.icon.path = "Interface\\Icons\\inv_cloak_" .. i
            b.NormalTexture = tex(b, name .. "ItemButtonNormalTexture", "ARTWORK")
            b.IconBorder = tex(b, nil, "OVERLAY")
            b.Count = fstring(b, name .. "ItemButtonCount", i == 2 and "4" or "", 12, { 1, 1, 1, 1 })
            b.scripts.OnClick = function() end
            b.scripts.OnEnter = function() end
            b.scripts.OnLeave = function() end
            b.SetItemButtonQuality = function(self, q) self.q = q end
        end
    end
    for _, n in ipairs({ "TradeHighlightPlayer", "TradeHighlightRecipient", "TradeHighlightPlayerEnchant", "TradeHighlightRecipientEnchant" }) do
        local h = blz("Frame", n, trade, 150, n:find("Enchant") and 61 or 266, "TOPLEFT", n:find("Recipient") and 176 or 6, n:find("Enchant") and -355 or -85)
        for _, part in ipairs({ "Top", "Middle", "Bottom" }) do tex(h, n .. part, "BACKGROUND") end
        h.shown = (n == "TradeHighlightPlayer")
    end
    local mif = blz("Frame", "TradePlayerInputMoneyFrame", trade, 150, 22, "TOPLEFT", 11, -61)
    for i, k in ipairs({ "gold", "silver", "copper" }) do
        local e = blz("EditBox", nil, mif, 50, 20, "TOPLEFT", (i - 1) * 54, 0)
        e.Left, e.Middle, e.Right = tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND"), tex(e, nil, "BACKGROUND")
        mif[k] = e
    end
    local rbg = blz("Frame", "TradeRecipientMoneyBg", trade, 150, 22, "TOPLEFT", 177, -60)
    rbg.NineSlice = blz("Frame", nil, rbg, 10, 10)
    local rm = money(trade, "TradeRecipientMoneyFrame", 300, -64)
    rm.points[1] = { point = "TOPLEFT", rel = trade, relPoint = "TOPLEFT", x = 300, y = -64 }
    -- the professions window: the rank bar, the recipe list (category bands and recipe rows with their skill up marks), the
    -- detail pane and the Create keys, shaped as in Blizzard_Professions and Blizzard_ProfessionsTemplates 12.1.0. Stock art is
    -- marked with a colour so a piece nobody held shows up in a render.
    local prof = blz("Frame", "ProfessionsFrame", UIParent, 780, 480)
    prof.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -520 }
    prof.shown = false
    local page = blz("Frame", nil, prof, 780, 450, "TOPLEFT", 0, -30)
    prof.CraftingPage = page
    local function stock(t, r, g, b) t.stock = { r, g, b }; return t end
    local rb = blz("Frame", nil, page, 453, 18, "TOPLEFT", 60, -10)
    page.RankBar = rb
    rb.Background = stock(tex(rb, nil, "ARTWORK"), 0.3, 0.2, 0.1); rb.Border = stock(tex(rb, nil, "ARTWORK"), 0.8, 0.6, 0.2)
    rb.Flare = stock(tex(rb, nil, "ARTWORK"), 1, 0.9, 0.5)
    rb.Fill = stock(tex(rb, nil, "ARTWORK"), 1, 0.35, 0.1); rb.Fill.w, rb.Fill.h = 441, 18
    rb.Fill.points[1] = { point = "TOPLEFT", rel = rb, relPoint = "TOPLEFT", x = 5, y = -3 }
    rb.Mask = tex(rb, nil, "ARTWORK"); rb.Mask.w, rb.Mask.h = 441 * 0.58, 18
    rb.Rank = blz("Frame", nil, rb, 300, 18, "CENTER", 0, 0)
    rb.Rank.Text = fstring(rb.Rank, nil, "Blacksmithing 88/150", 12, { 1, 1, 1, 1 })
    local list = blz("Frame", nil, page, 288, 360, "TOPLEFT", 20, -60)
    page.RecipeList = list
    list.Background = stock(tex(list, nil, "BACKGROUND"), 0.3, 0.25, 0.2)
    list.BackgroundNineSlice = blz("Frame", nil, list, 288, 360, "TOPLEFT", 0, 0)
    for _ = 1, 4 do stock(tex(list.BackgroundNineSlice, nil, "BORDER"), 0.7, 0.55, 0.25) end
    list.ScrollBox = scrollBox(list, 288, 360, 0, 0)
    local function category(label, y, collapsed, withBar)
        local c = blz("Button", nil, list.ScrollBox, 270, 25, "TOPLEFT", 0, -y)
        c.Label = fstring(c, nil, label, 12)
        c.Label.points[1] = { point = "LEFT", rel = c, relPoint = "LEFT", x = 10, y = 2 }
        c.LeftPiece, c.RightPiece, c.CenterPiece = stock(tex(c, nil, "BACKGROUND"), 0.55, 0.4, 0.15), stock(tex(c, nil, "BACKGROUND"), 0.55, 0.4, 0.15),
            stock(tex(c, nil, "BACKGROUND"), 0.45, 0.3, 0.1)
        c.CollapseIcon = stock(atex(c, nil, "ARTWORK", collapsed and "Professions-recipe-header-expand" or "Professions-recipe-header-collapse", 12, 12), 1, 0.8, 0.1)
        c.CollapseIcon.points[1] = { point = "RIGHT", rel = c, relPoint = "RIGHT", x = -10, y = 2 }
        c.CollapseIconAlphaAdd = atex(c, nil, "HIGHLIGHT", "Professions-recipe-header-collapse", 12, 12)
        c.Label:SetVertexColor(1, 0.82, 0, 1)
        if withBar then
            local bar = blz("StatusBar", nil, c, 58, 14, "RIGHT", -28, 0)
            bar.BorderLeft, bar.BorderMid, bar.BorderRight = stock(tex(bar, nil, "OVERLAY"), 0.8, 0.6, 0.2), stock(tex(bar, nil, "OVERLAY"), 0.8, 0.6, 0.2),
                stock(tex(bar, nil, "OVERLAY"), 0.8, 0.6, 0.2)
            bar.Rank = fstring(bar, nil, "", 10)
            c.RankBar = bar
        end
        c.scripts.OnClick = function() end
        return c
    end
    local function skillUps(row, atlas, count)
        local u = blz("Button", nil, row, 26, 15, "LEFT", -9, 0)
        u.Icon = stock(atex(u, nil, "OVERLAY", atlas, 15, 12), 0.3, 0.9, 0.3)
        u.Icon.points[1] = { point = "RIGHT", rel = u, relPoint = "RIGHT", x = 0, y = -1 }
        u.Text = fstring(u, nil, count or "", 12, { 1, 1, 1, 1 })
        u.Text.points[1] = { point = "RIGHT", rel = u.Icon, relPoint = "LEFT", x = 0, y = 1 }
        u.Text:SetVertexColor(1, 0.5, 0.25, 1)
        u.shown = atlas ~= nil
        row.SkillUps = u
    end
    local function recipe(label, y, selected, atlas, count)
        local r = blz("Button", nil, list.ScrollBox, 270, 20, "TOPLEFT", 0, -y)
        skillUps(r, atlas, count)
        r.Label = fstring(r, nil, label, 12)
        r.Label.w, r.Label.h = 150, 12
        r.Label.points[1] = { point = "LEFT", rel = r, relPoint = "LEFT", x = 26, y = 0 }
        r.Count = fstring(r, nil, "[3]", 12)
        r.Count.w, r.Count.h = 30, 12
        r.Count.points[1] = { point = "LEFT", rel = r.Label, relPoint = "RIGHT", x = 0, y = 0 }
        r.SelectedOverlay = tex(r, nil, "ARTWORK"); r.SelectedOverlay.shown = selected
        r.HighlightOverlay = tex(r, nil, "HIGHLIGHT")
        r.scripts.OnClick = function() end
        r.scripts.OnEnter = function() end
        r.scripts.OnLeave = function() end
        return r
    end
    local rows = list.ScrollBox.rows
    rows[1] = category("elixirs", 0, false, false)
    rows[2] = recipe("Elixir of Fortitude", 28, false, "Professions-Icon-Skill-Low")
    rows[3] = recipe("Elixir of Wisdom", 52, false, "Professions-Icon-Skill-Medium")
    rows[4] = recipe("Elixir of Agility", 76, true, "Professions-Icon-Skill-High", "2")
    rows[5] = recipe("Elixir of Water Breathing", 100, false, nil)
    rows[6] = category("potions", 124, true, true)
    -- the detail pane and the keys under it
    local form = blz("Frame", nil, page, 440, 360, "TOPLEFT", 320, -60)
    page.SchematicForm = form
    form.NineSlice = blz("Frame", nil, form, 440, 360, "TOPLEFT", 0, 0)
    for _ = 1, 4 do stock(tex(form.NineSlice, nil, "BORDER"), 0.7, 0.55, 0.25) end
    form.Background = stock(tex(form, nil, "BACKGROUND"), 0.3, 0.25, 0.2)
    form.MinimalBackground = stock(tex(form, nil, "BACKGROUND"), 0.3, 0.25, 0.2)
    -- the label is empty until a recipe is picked, so the sweep that finds text buttons by their label does not meet them
    page.CreateButton = textButton(page, nil, "", 650, -420, 80)
    page.CreateAllButton = textButton(page, nil, "", 540, -420, 80)
    page.ViewGuildCraftersButton = textButton(page, nil, "View Crafters", 400, -420, 120)
    page.ViewGuildCraftersButton.shown = false
    for _, k in ipairs({ "CreateButton", "CreateAllButton", "ViewGuildCraftersButton" }) do
        local b = page[k]
        for _, part in ipairs({ "Left", "Middle", "Right" }) do stock(b[part], 0.8, 0.1, 0.1) end
    end
    -- the chat channels: a list of pooled buttons under a Child frame, a roster ScrollBox, the add popup
    local ch = blz("Frame", "ChannelFrame", UIParent, 560, 420)
    ch.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 900, y = -520 }
    ch.shown = false
    ch.NewButton = textButton(ch, nil, "ADD", 10, -390)
    ch.SettingsButton = textButton(ch, nil, "SETTINGS", 120, -390)
    ch.LeftInset = blz("Frame", nil, ch, 190, 330, "TOPLEFT", 8, -40)
    tex(ch.LeftInset, nil, "BACKGROUND")
    ch.RightInset = blz("Frame", nil, ch, 330, 330, "TOPLEFT", 220, -40)
    tex(ch.RightInset, nil, "BACKGROUND")
    local cl = blz("ScrollFrame", nil, ch, 175, 320, "TOPLEFT", 12, -44)
    ch.ChannelList = cl
    cl.Child = blz("Frame", nil, cl, 175, 320, "TOPLEFT", 0, 0)
    cl.Update = function() end
    cl.GetSelectedChannelButton = function(self) return self.selectedChannelButton end
    cl.SetSelectedChannel = function(self, b)
        local prev = self.selectedChannelButton
        self.selectedChannelButton = b
        if prev then prev:SetIsSelectedChannel(false) end
        if b then b:SetIsSelectedChannel(true) end
    end
    local function chanButton(label, y, header, selected)
        local b = blz("Button", nil, cl.Child, 175, 24, "TOPLEFT", 0, -y)
        b.NormalTexture = tex(b, nil, "BACKGROUND")
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.Text = fstring(b, nil, label, 12)
        b.fs = b.Text
        if header then b.Collapsed = tex(b, nil, "ARTWORK") end
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        b.LockHighlight = function(self) self.locked = true end
        b.UnlockHighlight = function(self) self.locked = false end
        b.SetIsSelectedChannel = function(self, v) if v then self:LockHighlight() else self:UnlockHighlight() end end
        b.IsHeader = function() return header and true or false end
        b.id = label
        if selected then cl:SetSelectedChannel(b) end
        return b
    end
    chanButton("Text", 0, true)
    chanButton("1. General", 26, false, true)
    chanButton("2. Trade", 52, false)
    local roster = blz("Frame", nil, ch, 330, 320, "TOPLEFT", 224, -44)
    ch.ChannelRoster = roster
    roster.ScrollBox = scrollBox(roster, 320, 300, 0, 0)
    for i, who in ipairs({ "Stu", "Thessaly", "Brannoch", "Ashka" }) do
        local r = blz("Button", nil, roster.ScrollBox, 320, 20, "TOPLEFT", 0, -(i - 1) * 22)
        r.NormalTexture = tex(r, nil, "BACKGROUND")
        r.highlightTex = tex(r, nil, "HIGHLIGHT")
        r.Name = fstring(r, nil, who, 11, { 1, 1, 1, 1 })
        r.Rank = tex(r, nil, "ARTWORK")
        r.scripts.OnEnter = function() end
        roster.ScrollBox.rows[i] = r
    end
    local pop = blz("Frame", "CreateChannelPopup", UIParent, 320, 180, "TOPLEFT", 1000, -200)
    pop.shown = false
    pop.Header = blz("Frame", nil, pop, 200, 30, "TOP", 0, 10)
    tex(pop.Header, nil, "ARTWORK"); pop.Header.Text = fstring(pop.Header, nil, "Create channel", 13, { 1, 1, 1, 1 })
    pop.BG = blz("Frame", nil, pop, 320, 180, "TOPLEFT", 0, 0); tex(pop.BG, nil, "BORDER")
    pop.Name = blz("EditBox", nil, pop, 200, 22, "TOPLEFT", 20, -50)
    pop.Name.Label = fstring(pop.Name, nil, "Channel name", 12)
    pop.Password = blz("EditBox", nil, pop, 200, 22, "TOPLEFT", 20, -100)
    pop.Password.Label = fstring(pop.Password, nil, "Password", 12)
    pop.OKButton = textButton(pop, nil, "OKAY", 20, -140)
    pop.CancelButton = textButton(pop, nil, "CANCEL", 140, -140)
    -- the flight map: the old fixed map with node buttons, and the zoomable map with pins
    local taxi = blz("Frame", "TaxiFrame", UIParent, 590, 608)
    taxi.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 60, y = -1000 }
    taxi.shown = false
    taxi.InsetBg = tex(taxi, nil, "BACKGROUND"); taxi.InsetBg.w, taxi.InsetBg.h = 580, 580
    taxi.InsetBg.points[1] = { point = "TOPLEFT", rel = taxi, relPoint = "TOPLEFT", x = 5, y = -26 }
    local route = blz("Frame", "TaxiRouteMap", taxi, 580, 580, "TOPLEFT", 5, -26)
    taxi.TitleText = fstring(taxi, nil, "Flight Map", 12)
    for i = 1, 3 do
        local t = tex(route, nil, "BACKGROUND"); t.stock = { 0.1, 0.1, 0.1 }
        _G["TaxiRoute" .. i] = t
    end
    -- a Line region: a texture that records its two end points and thickness
    route.CreateLine = function(self, name, layer)
        local l = tex(self, name, layer)
        l.SetStartPoint = function(me, p, rel, x, y) me.lineStart = { p, rel, x, y } end
        l.SetEndPoint = function(me, p, rel, x, y) me.lineEnd = { p, rel, x, y } end
        l.SetThickness = function(me, w) me.thickness = w end
        return l
    end
    -- the stock helper stretches the line art across the texture; the mock only shows it
    function DrawLine(t, c, sx, sy, ex, ey, w, factor, rel) t:Show() end
    -- the colour of a marker's core on its middle row
    function Hue(g) for _, t in ipairs(g.core) do if t.fsRow == 0 then return t.color end end end
    TAXI_TYPES = { "CURRENT", "REACHABLE", "REACHABLE", "UNREACHABLE", "DISTANT" }
    function NumTaxiNodes() return #TAXI_TYPES end
    function TaxiNodeGetType(i) return TAXI_TYPES[i] end
    for i = 1, #TAXI_TYPES do
        local b = blz("Button", "TaxiButton" .. i, route, 16, 16, "CENTER", 60 + i * 90, -(100 + i * 20))
        b.points[1].relPoint = "BOTTOMLEFT"
        b:SetID(i)
        b:SetNormalTexture("Interface\\TaxiFrame\\UI-Taxi-Icon-White")
        b.GetNormalTexture = function(self) return self.normalTex end
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        b.scripts.OnLeave = function() end
        b.shown = TAXI_TYPES[i] ~= "DISTANT"
    end
    local fm = blz("Frame", "FlightMapFrame", UIParent, 1004, 689)
    fm.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 700, y = -1000 }
    fm.shown = false
    fm.BorderFrame = blz("Frame", nil, fm, 1004, 689, "TOPLEFT", 0, 0)
    fm.BorderFrame.TopBorder = tex(fm.BorderFrame, nil, "BORDER")
    fm.ScrollContainer = blz("ScrollFrame", nil, fm, 960, 620, "TOPLEFT", 20, -50)
    local pins = {}
    FM_PINS = pins
    for i, state in ipairs({ Enum.FlightPathState.Current, Enum.FlightPathState.Reachable, Enum.FlightPathState.Unreachable }) do
        local p = blz("Frame", nil, fm, 18, 18, "TOPLEFT", 100 + i * 150, -(150 + i * 40))
        p.Icon = tex(p, nil, "BACKGROUND"); p.IconHighlight = tex(p, nil, "HIGHLIGHT")
        p.taxiNodeData = { state = state }
        p.GetTaxiNodeState = function(self) return self.taxiNodeData.state end
        p.SetFlightPathStyle = function() end
        p.scripts.OnEnter = function() end
        pins[i] = p
    end
    fm.EnumeratePinsByTemplate = function(self, template)
        local i = 0
        return function() i = i + 1 return pins[i] end
    end
    fm.AcquirePin = function() end
end
"""

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "Character": "Modules/Skins/Character.lua",
             "Commerce": "Modules/Skins/Commerce.lua", "Quest": "Modules/Skins/Quest.lua", "Services": "Modules/Skins/Services.lua"}, BLIZZARD)
case = H.case

case("trainer: every service row is a card with a slot on its icon, the stock selected glow and highlight are held, the row follows the selection", """
    Fire('PLAYER_ENTERING_WORLD'); ClassTrainerFrame:Show(); FlushTimers()
    local S, Q = FS.ServicesSkin.state, FS.QuestSkin.state
    local rows = ClassTrainerFrame.ScrollBox.rows
    for i = 1, 5 do
        local r = rows[i]
        assert(S.trainer[r], 'row ' .. i .. ' not carded')
        assert(r.selectedTex.alpha == 0 and r.disabledBG.alpha == 0 and r.highlightTex.alpha == 0, 'stock art kept on ' .. i)
        assert(Q.slots[r] and FS.ItemSlotSkins.Parts(Q.slots[r]), 'no slot on ' .. i)
        assert(r.name.fontPath ~= 'stock.ttf' and r.subText.fontPath ~= 'stock.ttf', 'texts not mono on ' .. i)
        assert(r.scripts.OnClick and r.scripts.OnEnter, 'script lost')
    end
    assert(S.trainer[ClassTrainerFrameSkillStepButton], 'step button not skinned')
    local sel = S.trainer[rows[4]].box.edges[1].color
    assert(sel[1] > 0.9 and sel[2] < 0.3, 'selected row not pink')
    local idle = S.trainer[rows[1]].box.edges[1].color
    assert(idle[3] > 0.4 and idle[1] < 0.4, 'idle row not the dim violet')
    rows[1]:RunScript('OnEnter')
    assert(S.trainer[rows[1]].box.edges[1].color[2] > 0.8, 'hover not cyan')
    rows[1]:RunScript('OnLeave')
    rows[4].selectedTex:Hide(); rows[1].selectedTex:Show()
    assert(S.trainer[rows[1]].box.edges[1].color[1] > 0.9, 'the selection did not move')
    assert(S.trainer[rows[4]].box.edges[1].color[1] < 0.4, 'the old selection stayed pink')
    assert(S.trainer[rows[6]] and S.trainer[rows[6]].header, 'the category row is not a band')
    assert(rows[1].money:GetChildren().fs.fontPath ~= 'stock.ttf', 'trainer price not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("trainer: the skill bar is a ring box over a track, its stock border art is already held by the panel skin", """
    Fire('PLAYER_ENTERING_WORLD'); ClassTrainerFrame:Show(); FlushTimers()
    assert(FS.ServicesSkin.state.trainerBar, 'no skill bar box')
    assert(ClassTrainerStatusBarSkillRank.fontPath ~= 'stock.ttf', 'rank text not mono')
""")

case("trade: every slot is a square slot on a card, the stock plate and name frame are held, the highlights lose their gold art and ring cyan", """
    Fire('PLAYER_ENTERING_WORLD'); TradeFrame:Show(); FlushTimers()
    local S, Q = FS.ServicesSkin.state, FS.QuestSkin.state
    for _, side in ipairs({ 'Player', 'Recipient' }) do
        for i = 1, 7 do
            local row = _G['Trade' .. side .. 'Item' .. i]
            local b = _G['Trade' .. side .. 'Item' .. i .. 'ItemButton']
            assert(S.tradeRows[row], side .. i .. ' not carded')
            assert(Q.squares[b] and FS.ItemSlotSkins.Parts(b), side .. i .. ' no slot')
            assert(row.SlotTexture.alpha == 0 and _G['Trade' .. side .. 'Item' .. i .. 'NameFrame'].alpha == 0, 'stock art kept')
            assert(b.scripts.OnClick and b.scripts.OnEnter, 'slot script lost')
            assert(row.Name.fontPath ~= 'stock.ttf', 'name not mono')
        end
    end
    SetItemButtonQuality(TradePlayerItem1ItemButton, 3)
    local led = FS.ItemSlotSkins.Parts(TradePlayerItem1ItemButton).led.color
    assert(math.abs(led[3] - FS.Theme.COLOR_QUALITY[3][3]) < 0.01, 'LED did not follow the quality')
    for _, n in ipairs({ 'TradeHighlightPlayer', 'TradeHighlightRecipient', 'TradeHighlightPlayerEnchant', 'TradeHighlightRecipientEnchant' }) do
        for _, part in ipairs({ 'Top', 'Middle', 'Bottom' }) do assert(_G[n .. part].alpha == 0, n .. part .. ' gold art kept') end
        assert(S.tradeHighlights[_G[n]], n .. ' no ring')
    end
    for _, n in ipairs({ 'TradePlayerItemsInset', 'TradeRecipientItemsInset', 'TradePlayerInputMoneyInset' }) do assert(_G[n].alpha == 0, n .. ' kept') end
    assert(FS.CommerceSkin.state.money[TradePlayerInputMoneyFrame], 'money input not skinned')
    assert(TradeRecipientMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'their money not styled')
    assert(TradeFramePlayerNameText.fontPath ~= 'stock.ttf', 'name not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("trade: forbidden money boxes (as on the live client) are skipped without an error", """
    local function forbidden()
        return { IsForbidden = function() return true end, GetName = function() error('Attempt to access forbidden object') end }
    end
    local mif = { gold = forbidden(), silver = forbidden(), copper = forbidden() }
    local ok, err = pcall(FS.CommerceSkin.SkinMoneyInput, mif)
    assert(ok, 'threw on a forbidden box: ' .. tostring(err))
""")

case("professions: the rank bar's stock fill, frame and flare are held and our own fill follows the stock mask", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local rb = ProfessionsFrame.CraftingPage.RankBar
    assert(rb.Background.alpha == 0 and rb.Border.alpha == 0 and rb.Flare.alpha == 0 and rb.Fill.alpha == 0, 'stock bar art kept')
    assert(rb.Rank.Text.fontPath ~= 'stock.ttf', 'rank not mono')
    assert(S.rankBar and S.rankFill, 'no track or fill')
    local fill, inner = S.rankFill.fill, S.rankFill.ref:GetWidth() - 2 / PPU
    assert(fill.color and fill.color[1] < 0.3 and fill.color[3] > 0.8, 'the fill is not cyan')
    assert(math.abs(fill:GetWidth() - inner * 0.58) < 0.5, 'fill is ' .. fill:GetWidth() .. ' of ' .. inner)
    rb.Mask:SetWidth(rb.Fill:GetWidth() * 0.25)
    assert(math.abs(fill:GetWidth() - inner * 0.25) < 0.5, 'fill did not follow the mask')
    rb.Mask:SetWidth(0)
    assert(not fill:IsShown(), 'an empty bar draws a fill')
    rb.Mask:SetWidth(rb.Fill:GetWidth() * 3)
    assert(fill:IsShown() and math.abs(fill:GetWidth() - inner) < 0.5, 'a full bar is clamped to the track')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("professions: recipe rows are cards that follow the stock selection, every stock piece held, hover lights the edge", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local rows = ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.rows
    for i = 2, 5 do
        assert(S.recipes[rows[i]], 'row ' .. i .. ' not carded')
        assert(rows[i].HighlightOverlay.alpha == 0 and rows[i].SelectedOverlay.alpha == 0, 'stock overlays kept on ' .. i)
    end
    assert(rows[4].SelectedOverlay.shown, 'the stock selection state must survive')
    assert(S.recipes[rows[4]].box.edges[1].color[1] > 0.9, 'selected recipe not pink')
    assert(S.recipes[rows[2]].box.edges[1].color[1] < 0.4, 'idle recipe not dim')
    rows[2]:RunScript('OnEnter')
    assert(S.recipes[rows[2]].box.edges[1].color[2] > 0.8, 'hover not cyan')
    assert(rows[2].scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("professions: category rows hold every stock piece, draw their own fold chevron and keep the palette", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local rows = ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.rows
    local open, shut = rows[1], rows[6]
    for _, h in ipairs({ open, shut }) do
        assert(S.recipes[h] and S.recipes[h].header, 'not a band')
        for _, key in ipairs({ 'LeftPiece', 'RightPiece', 'CenterPiece', 'CollapseIcon', 'CollapseIconAlphaAdd' }) do
            assert(h[key].alpha == 0, key .. ' kept')
        end
    end
    local bar = shut.RankBar
    assert(bar.BorderLeft.alpha == 0 and bar.BorderMid.alpha == 0 and bar.BorderRight.alpha == 0, 'the gold border of the mini bar kept')
    assert(bar.Rank.fontPath ~= 'stock.ttf', 'mini bar rank not mono')
    local function shown(cells) local n = 0; for _, c in ipairs(cells) do if c:IsShown() then n = n + 1 end end return n end
    local g = S.recipes[open].glyph
    assert(shown(g.down) == 5 and shown(g.right) == 0, 'an open category is not a down chevron')
    assert(g.down[1].color[2] > 0.8 and g.down[1].color[1] < 0.3, 'open chevron not cyan')
    local g2 = S.recipes[shut].glyph
    assert(shown(g2.right) == 5 and shown(g2.down) == 0, 'a folded category is not a right chevron')
    assert(g2.right[1].color[3] > 0.9 and g2.right[1].color[2] < 0.5, 'folded chevron not violet')
    open.CollapseIcon:SetAtlas('Professions-recipe-header-expand')
    assert(shown(g.right) == 5 and shown(g.down) == 0, 'the chevron did not follow the stock fold')
    open:RunScript('OnEnter')
    assert(g.right[1].color[1] > 0.8, 'hover does not light the chevron')
    open:RunScript('OnLeave')
    -- the stock code writes the label colour on every init: the gold is ours, a grey (unlearned) stays muted
    open.Label:SetVertexColor(1, 0.82, 0, 1)
    assert(open.Label.vertex[1] == 1 and open.Label.vertex[2] == 1 and open.Label.vertex[3] == 1, 'gold vertex not cleared')
    open.Label:SetVertexColor(0.5, 0.5, 0.5, 1)
    assert(open.Label.vertex[1] > 0.5 and open.Label.vertex[1] < 0.8, 'a grey label is not muted')
    assert(open.Label.textColor[3] > 0.9, 'the label text is not ours')
    assert(open.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("professions: skill up marks hold the stock arrow and draw a chip with one to three chevrons in the tier colour", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local rows = ProfessionsFrame.CraftingPage.RecipeList.ScrollBox.rows
    local function shown(ups)
        local chip, out = S.skillUps[ups], {}
        for i = 1, 3 do
            local n = 0
            for _, c in ipairs(chip.cells[i]) do if c:IsShown() then n = n + 1 end end
            out[i] = n
        end
        return out
    end
    local function hue(ups) return S.skillUps[ups].cells[1][1].color end
    local low, med, high = rows[2].SkillUps, rows[3].SkillUps, rows[4].SkillUps
    for _, u in ipairs({ low, med, high }) do
        assert(S.skillUps[u], 'no chip')
        assert(u.Icon.alpha == 0, 'stock arrow kept')
    end
    local a, b, c = shown(low), shown(med), shown(high)
    assert(a[1] == 5 and a[2] == 0 and a[3] == 0, 'easy is not one chevron')
    assert(b[1] == 5 and b[2] == 5 and b[3] == 0, 'medium is not two chevrons')
    assert(c[1] == 5 and c[2] == 5 and c[3] == 5, 'optimal is not three chevrons')
    local g, y, o = hue(low), hue(med), hue(high)
    assert(g[2] > g[1] and g[2] > 0.8, 'easy not green')
    assert(y[1] > 0.9 and y[2] > 0.75 and y[3] < 0.4, 'medium not yellow')
    assert(o[1] > 0.9 and o[2] > 0.45 and o[2] < 0.65 and o[3] < 0.4, 'optimal not orange')
    assert(S.skillUps[high].box.edges[1].color[1] > 0.9, 'the chip edge is not the tier colour')
    assert(S.skillUps[high].box.fill.color[1] < 0.5, 'the chip face is not dark')
    -- the chip sits inside the stock arrow's footprint, right edge on the right edge of the stock frame
    local _, _, cr = S.skillUps[high].ref:Rect()
    local _, _, ur = high:Rect()
    assert(cr <= ur + 0.01, 'the chip pokes out of the mark frame')
    assert(high.Text.fontPath ~= 'stock.ttf', 'the skill up count is not mono')
    -- a row with no skill up has its mark frame hidden, so the chip is hidden with it
    assert(not rows[5].SkillUps.shown and S.skillUps[rows[5].SkillUps], 'a recipe without skill ups shows a chip')
    -- the stock code swaps the atlas when a recipe is re-initialised: the chip re-tiers
    low.Icon:SetAtlas('Professions-Icon-Skill-High')
    local d = shown(low)
    assert(d[1] == 5 and d[2] == 5 and d[3] == 5, 'the chip did not follow the atlas')
    assert(hue(low)[1] > 0.9, 'the chip did not take the new tier colour')
    low.Icon:SetAtlas('Professions-Icon-Skill-Low')
    assert(shown(low)[2] == 0, 'the chip did not go back')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("professions: the stock nine slices are held and the detail pane takes a ring of ours", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local page = ProfessionsFrame.CraftingPage
    assert(page.RecipeList.BackgroundNineSlice.alpha == 0 and page.RecipeList.Background.alpha == 0, 'the list art kept')
    local form = page.SchematicForm
    assert(form.NineSlice.alpha == 0, 'the stock frame of the detail pane kept')
    assert(form.Background.alpha == 0 and form.MinimalBackground.alpha == 0, 'the pane backgrounds kept')
    local ring = S.panes[form]
    assert(ring and ring.edges[1].color[3] > 0.9 and ring.edges[1].color[2] < 0.5, 'no violet ring on the detail pane')
    -- the stock code shows the frame again on every recipe: alpha is what holds
    form.NineSlice:SetAlpha(1)
    assert(form.NineSlice.alpha == 0, 'the stock frame came back')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("professions: Create, Create All and View Crafters wear the text button even while their label is empty", """
    Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers()
    local page = ProfessionsFrame.CraftingPage
    local Parts = FS.ButtonSkins.Parts
    for _, key in ipairs({ 'CreateButton', 'CreateAllButton', 'ViewGuildCraftersButton' }) do
        local b = page[key]
        assert(Parts(b), key .. ' not skinned')
        assert(b.Left.alpha == 0 and b.Middle.alpha == 0 and b.Right.alpha == 0, key .. ' kept its red slices')
        assert(b.scripts.OnClick, key .. ' lost its click')
    end
    assert(Parts(page.CreateButton).accent == 'cyan', 'Create is not the cyan key')
    assert(Parts(page.CreateAllButton).accent == 'violet', 'Create All is not the violet key')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("channels: the list buttons and roster rows are cards with the stock art held, the selected channel is pink, the insets are rings, the click stays", """
    Fire('PLAYER_ENTERING_WORLD'); ChannelFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    local kids = { ChannelFrame.ChannelList.Child:GetChildren() }
    assert(#kids == 3, 'list children ' .. #kids)
    for i, b in ipairs(kids) do
        assert(S.channels[b], 'channel button ' .. i .. ' not carded')
        assert(b.NormalTexture.alpha == 0 and b.highlightTex.alpha == 0, 'stock row art kept')
        assert(b.Text.fontPath ~= 'stock.ttf', 'channel name not mono')
        assert(b.scripts.OnClick, 'click lost')
    end
    assert(S.channels[kids[2]].box.edges[1].color[1] > 0.9, 'selected channel not pink')
    assert(S.channels[kids[3]].box.edges[1].color[1] < 0.4, 'idle channel not dim')
    ChannelFrame.ChannelList:SetSelectedChannel(kids[3])
    assert(S.channels[kids[3]].box.edges[1].color[1] > 0.9 and S.channels[kids[2]].box.edges[1].color[1] < 0.4, 'selection did not move')
    for i, r in ipairs(ChannelFrame.ChannelRoster.ScrollBox.rows) do
        assert(S.channels[r], 'roster row ' .. i .. ' not carded')
        assert(r.NormalTexture.alpha == 0 and r.highlightTex.alpha == 0, 'stock roster art kept')
        assert(r.Name.fontPath ~= 'stock.ttf', 'roster name not mono')
    end
    assert(ChannelFrame.LeftInset.alpha == 0 and ChannelFrame.RightInset.alpha == 0, 'insets kept')
    assert(S.insets[ChannelFrame.LeftInset] and S.insets[ChannelFrame.RightInset], 'no inset rings')
    -- a button that arrives with a later update is carded by the update hook
    local late = BLZ.blz('Button', nil, ChannelFrame.ChannelList.Child, 175, 24, 'TOPLEFT', 0, -80)
    late.NormalTexture = BLZ.tex(late, nil, 'BACKGROUND'); late.highlightTex = BLZ.tex(late, nil, 'HIGHLIGHT'); late.Text = BLZ.fstring(late, nil, '3. LFG', 12)
    ChannelFrame.ChannelList:Update(); FlushTimers()
    assert(S.channels[late], 'a later channel button was not carded')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("channels: the add popup is a dialog of ours with its border frame held, mono labels and swept keys", """
    Fire('PLAYER_ENTERING_WORLD'); CreateChannelPopup:Show(); FlushTimers()
    local p = CreateChannelPopup
    assert(p.BG.alpha == 0, 'stock border kept')
    assert(FS.CommerceSkin.state.dialogs[p], 'no dialog chrome')
    assert(p.Header.Text.fontPath ~= 'stock.ttf' and p.Name.Label.fontPath ~= 'stock.ttf' and p.Password.Label.fontPath ~= 'stock.ttf', 'texts')
    assert(p.fsSweepHook, 'the popup is not swept on show')
    assert(p.OKButton.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("flight map: the node buttons hold the stock icon and draw a glyph by state, hidden nodes stay hidden, the click stays", """
    Fire('PLAYER_ENTERING_WORLD'); TaxiFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    for i = 1, 4 do
        local b = _G['TaxiButton' .. i]
        assert(S.taxi[b], 'button ' .. i .. ' not skinned')
        assert(b.normalTex.alpha == 0 and b.highlightTex.alpha == 0, 'stock icon kept')
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'script lost')
    end
    local cur, reach = Hue(S.taxi[TaxiButton1].glyph), Hue(S.taxi[TaxiButton2].glyph)
    assert(cur[1] > 0.9 and cur[2] < 0.3, 'current node not pink')
    assert(reach[2] > 0.8 and reach[1] < 0.3, 'reachable node not cyan')
    -- a marker: an edge one row past a dark plate, a glow under it, and the ring only round the current node
    local g1, g2 = S.taxi[TaxiButton1].glyph, S.taxi[TaxiButton2].glyph
    local function widest(rows) local w = 0 for _, t in ipairs(rows) do if t.shown ~= false then w = math.max(w, t.w or 0) end end return w end
    assert(widest(g1.edge) > widest(g1.plate), 'edge not round the plate: ' .. widest(g1.edge) .. ' vs ' .. widest(g1.plate))
    assert(widest(g1.edge) > widest(g2.edge), 'current node not larger than a reachable one')
    assert(g1.glow.shown ~= false and g1.glow.blend == 'ADD', 'no glow under the current node')
    assert(g1.ring and g1.ring[1].t.shown ~= false, 'no ring round the current node')
    assert(not g2.ring, 'ring on a reachable node')
    local before = widest(g2.edge)
    TaxiButton2:RunScript('OnEnter')
    assert(widest(g2.edge) > before, 'hover did not grow the marker')
    TaxiButton2:RunScript('OnLeave')
    -- the stock code swaps the icon texture on every show; the hold survives it and the glyph follows the type
    TaxiButton2:SetNormalTexture('Interface\\\\TaxiFrame\\\\UI-Taxi-Icon-Green')
    assert(TaxiButton2.normalTex.alpha == 0, 'swapped icon not held')
    TAXI_TYPES[2] = 'UNREACHABLE'
    TaxiFrame:Hide(); TaxiFrame:Show(); FlushTimers()
    assert(Hue(S.taxi[TaxiButton2].glyph)[1] < 0.5 and Hue(S.taxi[TaxiButton2].glyph)[2] < 0.5, 'unreachable node not dim')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("flight map: the stock title is held, a route drawn by the stock helper becomes a cyan line between the same points and hides with it", """
    Fire('PLAYER_ENTERING_WORLD'); TaxiFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    assert(TaxiFrame.TitleText.alpha == 0, 'stock title kept')
    DrawLine(TaxiRoute1, TaxiRouteMap, 100, 200, 300, 250, 32, 128 / 126, 'BOTTOMLEFT')
    local l = S.routes[TaxiRoute1]
    assert(l, 'no line for the route')
    assert(TaxiRoute1.alpha == 0, 'stock route art kept')
    assert(l.lineStart[1] == 'BOTTOMLEFT' and l.lineStart[2] == TaxiRouteMap and l.lineStart[3] == 100 and l.lineStart[4] == 200, 'start')
    assert(l.lineEnd[3] == 300 and l.lineEnd[4] == 250, 'end')
    assert(l.color[3] > 0.8 and l.color[1] < 0.3, 'line not cyan')
    assert(l.shown ~= false, 'line not shown')
    TaxiRoute1:Hide()
    assert(l.shown == false, 'line stayed when the route hid')
    DrawLine(TaxiRoute1, TaxiRouteMap, 10, 20, 30, 40, 32, 128 / 126, 'BOTTOMLEFT')
    assert(S.routes[TaxiRoute1] == l and l.lineStart[3] == 10 and l.shown ~= false, 'redraw did not reuse and show the line')
    -- a line drawn somewhere else is not touched
    local other = BLZ.tex(UIParent, nil, 'ARTWORK')
    DrawLine(other, UIParent, 0, 0, 5, 5, 32)
    assert(not S.routes[other] and other.alpha ~= 0, 'a line off the flight map was taken')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("flight map: the zoomable map's pins hold the stock icon and draw a glyph by state, the map border art is held", """
    Fire('PLAYER_ENTERING_WORLD'); FlightMapFrame:Show(); FlushTimers()
    local S = FS.ServicesSkin.state
    for i, p in ipairs(FM_PINS) do
        assert(S.pins[p], 'pin ' .. i .. ' not skinned')
        assert(p.Icon.alpha == 0 and p.IconHighlight.alpha == 0, 'stock pin icon kept')
        assert(p.scripts.OnEnter, 'pin script lost')
    end
    assert(Hue(S.pins[FM_PINS[1]].glyph)[1] > 0.9, 'current pin not pink')
    assert(Hue(S.pins[FM_PINS[2]].glyph)[2] > 0.8, 'reachable pin not cyan')
    assert(FlightMapFrame.BorderFrame.TopBorder.alpha == 0, 'map border art kept')
    -- a pin that is restyled by the stock code is drawn again
    FM_PINS[2].taxiNodeData.state = Enum.FlightPathState.Current
    FM_PINS[2]:SetFlightPathStyle(Enum.FlightPathState.Current)
    assert(Hue(S.pins[FM_PINS[2]].glyph)[1] > 0.9, 'glyph did not follow the restyle')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", """
    Reset()
    __combat = true
    Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'Commerce', 'Quest', 'Services' })
    assert(not ClassTrainerFrame.fsServicesSkin and not TradeFrame.fsServicesSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(ClassTrainerFrame.fsServicesSkin and TradeFrame.fsServicesSkin and ProfessionsFrame.fsServicesSkin and ChannelFrame.fsServicesSkin
        and TaxiFrame.fsServicesSkin and FlightMapFrame.fsServicesSkin, 'not built when combat ended')
""")

SCENES = {
    "trainer": "Fire('PLAYER_ENTERING_WORLD'); ClassTrainerFrame:Show(); FlushTimers(); return DumpOps({ ClassTrainerFrame })",
    "trade": "Fire('PLAYER_ENTERING_WORLD'); TradeFrame:Show(); TradePlayerItem2ItemButton:RunScript('OnEnter'); FlushTimers(); return DumpOps({ TradeFrame })",
    "professions": "Fire('PLAYER_ENTERING_WORLD'); ProfessionsFrame:Show(); FlushTimers(); return DumpOps({ ProfessionsFrame })",
    "channels": "Fire('PLAYER_ENTERING_WORLD'); ChannelFrame:Show(); CreateChannelPopup:Show(); FlushTimers(); return DumpOps({ ChannelFrame, CreateChannelPopup })",
    "taxi": "Fire('PLAYER_ENTERING_WORLD'); TaxiFrame:Show(); FlightMapFrame:Show(); FlushTimers(); return DumpOps({ TaxiFrame, FlightMapFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("services skin", SCENES))
