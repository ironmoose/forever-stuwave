#!/usr/bin/env python3
"""Runs the real Modules/Skins/Quest.lua headless against mock quest, gossip and book windows (tools/charskin_support.py).

Pinned, per window: the quest reward and required item cards get a card, a slot of the shared item slot layer over the stock icon
(the stock name plate and quality border held), the picked reward lights pink and the rest dim, gossip rows and quest greeting
buttons are cards that follow the pooled rows, the book page keys are cut keys with a chevron, no script or attribute is written
on a Blizzard widget, and nothing is built in combat. Run `python3 tools/questskin-harness.py [--png debug/quest]`.
The mock is NOT the real client.
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

local function money(parent, name, x, y)
    local m = blz("Frame", name, parent, 100, 14, "TOPLEFT", x, y)
    m.staticMoney = true
    for _, k in ipairs({ "Gold", "Silver", "Copper" }) do fstring(m, name .. k .. "ButtonText", "12", 12, { 1, 1, 1, 1 }) end
    return m
end

-- LargeItemButtonTemplate: 147 x 41, Icon 39 x 39 at the top left, NameFrame and Name, Count, the quality border and overlays
local function largeItem(parent, name, x, y, id, kind)
    local b = blz("Button", name, parent, 147, 41, "TOPLEFT", x, y)
    b.id, b.type = id, kind
    b.Icon = tex(b, name .. "IconTexture", "BACKGROUND")
    b.Icon.w, b.Icon.h = 39, 39
    b.Icon.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 0, y = 0 }
    b.NameFrame = tex(b, name .. "NameFrame", "BACKGROUND")
    b.NameFrame.w, b.NameFrame.h = 128, 64
    b.NameFrame.points[1] = { point = "LEFT", rel = b.Icon, relPoint = "RIGHT", x = -10, y = 0 }
    b.Name = fstring(b, name .. "Name", "Item", 12, { 1, 1, 1, 1 })
    b.Name.w, b.Name.h = 90, 36
    b.Name.points[1] = { point = "LEFT", rel = b.NameFrame, relPoint = "LEFT", x = 15, y = 0 }
    b.IconBorder = tex(b, nil, "OVERLAY")
    b.IconOverlay = tex(b, nil, "OVERLAY")
    b.IconOverlay2 = tex(b, nil, "OVERLAY")
    b.Count = fstring(b, name .. "Count", "", 12, { 1, 1, 1, 1 })
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = QuestInfoItem_OnClick
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    return b
end

local function pager(parent, name, dir)
    local b = blz("Button", name, parent, 32, 32, "CENTER", dir == "<" and 25 or 310, 96)
    b.points[1].relPoint = "BOTTOMLEFT"
    local label = fstring(b, nil, dir == "<" and "PREV" or "NEXT", 12, { 1, 0.82, 0, 1 })
    label.points[1] = { point = dir == "<" and "LEFT" or "RIGHT", rel = b, relPoint = dir == "<" and "RIGHT" or "LEFT", x = 0, y = 0 }
    b.NormalTexture = tex(b, nil, "ARTWORK")
    b.GetNormalTexture = function(self) return self.NormalTexture end
    b.pushedTex, b.highlightTex = tex(b, nil, "ARTWORK"), tex(b, nil, "HIGHLIGHT")
    b.scripts.OnClick = function() end
    return b
end

function SetItemButtonQuality(button, quality)
    if button.SetItemButtonQuality then button:SetItemButtonQuality(quality) else button.q = quality end
end

function BuildBlizzard()
    build()
    atex = BLZ.atex
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Quest") or k:find("^Gossip") or k:find("^ItemText") or k:find("^Greeting")
            or k:find("^CurrentQuests") or k:find("^AvailableQuests")) then _G[k] = nil end
    end
    QuestInfoFrame = { itemChoice = 0 }
    function QuestInfoItem_OnClick(self)
        if self.type == "choice" then
            QuestInfoItemHighlight:SetPoint("TOPLEFT", self, "TOPLEFT", -8, 7)
            QuestInfoItemHighlight:Show()
            QuestInfoFrame.itemChoice = self:GetID()
        end
    end
    function QuestInfo_Display() end
    function QuestFrameProgressItems_Update() end
    -- QuestFrame and its four pages
    local win = blz("Frame", "QuestFrame", UIParent, 338, 496)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 100, y = -80 }
    win.shown = false
    local pages = {}
    for _, n in ipairs({ "QuestFrameDetailPanel", "QuestFrameProgressPanel", "QuestFrameRewardPanel", "QuestFrameGreetingPanel" }) do
        pages[n] = blz("Frame", n, win, 338, 496, "TOPLEFT", 0, 0)
        pages[n].shown = false
    end
    local detail, progress, reward, greeting = pages.QuestFrameDetailPanel, pages.QuestFrameProgressPanel, pages.QuestFrameRewardPanel, pages.QuestFrameGreetingPanel
    for _, spec in ipairs({
        { detail, "QuestInfoTitleHeader", "Taming the Beast", 18 }, { detail, "QuestInfoDescriptionText", "The wild beasts have grown bold.", 13 },
        { detail, "QuestInfoObjectivesHeader", "Objectives", 18 }, { detail, "QuestInfoObjectivesText", "Kill Plainstrider Hens", 13 },
        { detail, "QuestInfoObjective1", "Plainstrider Hens: 0/8", 13 }, { detail, "QuestInfoObjective2", "Hen Feathers: 3/6", 13 },
        { detail, "QuestInfoRewardText", "Well hunted.", 13 },
        { progress, "QuestProgressTitleText", "Hunting Pack", 18 }, { progress, "QuestProgressText", "Show me what you have.", 13 },
        { progress, "QuestProgressRequiredItemsText", "Required items", 18 }, { progress, "QuestProgressRequiredMoneyText", "Required money:", 13 },
        { greeting, "GreetingText", "Greetings, Stu.", 13 }, { greeting, "CurrentQuestsText", "Current quests", 18 },
        { greeting, "AvailableQuestsText", "Available quests", 18 },
    }) do
        local f = fstring(spec[1], spec[2], spec[3], spec[4], { 0.2, 0.1, 0.05, 1 })
        f.w, f.h = 280, 20
    end
    for i, f in ipairs({ QuestInfoTitleHeader, QuestInfoDescriptionText, QuestInfoObjectivesHeader, QuestInfoObjectivesText, QuestInfoObjective1,
        QuestInfoObjective2, QuestInfoRewardText }) do f.points[1] = { point = "TOPLEFT", rel = detail, relPoint = "TOPLEFT", x = 20, y = -20 - (i - 1) * 24 } end
    for n, y in pairs({ QuestProgressTitleText = 14, QuestProgressText = 44, QuestProgressRequiredItemsText = 92, QuestProgressRequiredMoneyText = 252,
        GreetingText = 14, CurrentQuestsText = 40 }) do
        local f = _G[n]
        f.points[1] = { point = "TOPLEFT", rel = f.parent, relPoint = "TOPLEFT", x = 20, y = -y }
    end
    AvailableQuestsText.points[1] = { point = "TOPLEFT", rel = greeting, relPoint = "TOPLEFT", x = 20, y = -150 }
    -- the rewards frame: header texts, five buttons built on demand, the money and XP lines, the pick highlight
    local rf = blz("Frame", "QuestInfoRewardsFrame", detail, 285, 220, "TOPLEFT", 20, -190)
    win.QuestInfoRewardsFrame = rf
    rf.Header = fstring(rf, nil, "Rewards", 18, { 0.2, 0.1, 0.05, 1 })
    rf.ItemChooseText = fstring(rf, nil, "You will be able to choose one of these rewards:", 13, { 0.2, 0.1, 0.05, 1 })
    rf.ItemReceiveText = fstring(rf, nil, "You will receive:", 13, { 0.2, 0.1, 0.05, 1 })
    for i, f in ipairs({ rf.Header, rf.ItemChooseText, rf.ItemReceiveText }) do
        f.w, f.h = 280, 18
        f.points[1] = { point = "TOPLEFT", rel = rf, relPoint = "TOPLEFT", x = 0, y = -(i - 1) * 20 }
    end
    rf.RewardButtons = {}
    for i = 1, 5 do
        local col, r = (i - 1) % 2, math.floor((i - 1) / 2)
        local b = largeItem(rf, "QuestInfoRewardsFrameQuestInfoItem" .. i, col * 150, -(70 + r * 44), i, i <= 3 and "choice" or "reward")
        b.Name:SetText(({ "Hunting Gloves", "Tracker's Belt", "Hide Bracers", "Linen Bandage", "Hunter's Mark Scroll" })[i])
        b.Icon.path = "Interface\\Icons\\inv_" .. i
        rf.RewardButtons[i] = b
    end
    rf.MoneyFrame = money(rf, "QuestInfoMoneyFrame", 90, -200)
    rf.XPFrame = blz("Frame", "QuestInfoXPFrame", rf, 200, 18, "TOPLEFT", 0, -196)
    rf.XPFrame.ReceiveText = fstring(rf.XPFrame, nil, "Experience:", 13, { 0.2, 0.1, 0.05, 1 })
    rf.XPFrame.ValueText = fstring(rf.XPFrame, nil, "450", 13, { 1, 1, 1, 1 })
    rf.XPFrame.ValueText.points[1] = { point = "LEFT", rel = rf.XPFrame, relPoint = "LEFT", x = 90, y = 0 }
    rf.XPFrame.ReceiveText.points[1] = { point = "LEFT", rel = rf.XPFrame, relPoint = "LEFT", x = 0, y = 0 }
    rf.ItemHighlight = blz("Frame", "QuestInfoItemHighlight", rf, 256, 64, "TOPLEFT", 0, 0)
    rf.ItemHighlight.shown = false
    tex(rf.ItemHighlight, nil, "BACKGROUND").path = "Interface\\QuestFrame\\UI-QuestItemHighlight"
    -- the progress page's required item buttons
    for i = 1, 4 do
        local col, r = (i - 1) % 2, math.floor((i - 1) / 2)
        local b = largeItem(progress, "QuestProgressItem" .. i, 20 + col * 149, -(120 + r * 44), i, "required")
        b.Name:SetText(({ "Plainstrider Feather", "Hen Meat", "Swoop Talon", "Empty Vial" })[i])
        b.Icon.path = "Interface\\Icons\\inv_misc_" .. i
        b.Count:SetText(i == 2 and "8" or "")
    end
    QuestProgressItem4:Hide()
    progress.MoneyFrame = money(progress, "QuestProgressRequiredMoneyFrame", 150, -250)
    -- the greeting page's quest title buttons (a pool)
    local active = {}
    for i = 1, 3 do
        local b = blz("Button", "QuestTitleButton" .. i, greeting, 300, 16, "TOPLEFT", 14, -(60 + (i - 1) * 24))
        b.Icon = tex(b, "QuestTitleButton" .. i .. "QuestIcon", "BACKGROUND")
        b.Icon.w, b.Icon.h = 16, 16
        b.Icon.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 4, y = 0 }
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.fs = fstring(b, nil, ({ "Taming the Beast", "Hunting Pack", "Swoop Talon Bounty" })[i], 12, { 1, 0.82, 0, 1 })
        b.fs.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 20, y = 0 }
        b.scripts.OnClick = function() end
        active[#active + 1] = b
    end
    greeting.titleButtonPool = { EnumerateActive = function() local i = 0 return function() i = i + 1 return active[i] end end }
    function QuestFrameGreetingPanel_OnShow() end
    -- the gossip window: a ScrollBox of pooled rows
    local g = blz("Frame", "GossipFrame", UIParent, 338, 496)
    g.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 500, y = -80 }
    g.shown = false
    local gp = blz("Frame", nil, g, 338, 470, "TOPLEFT", 0, -20)
    g.GreetingPanel = gp
    gp.GoodbyeButton = blz("Button", nil, gp, 80, 22, "BOTTOMRIGHT", -10, 10)
    gp.GoodbyeButton.scripts.OnClick = function() end
    local box = blz("Frame", nil, gp, 300, 403, "TOPLEFT", 8, -65)
    gp.ScrollBox = box
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.GetView = function() return {} end
    box.Update = function() end
    local greet = blz("Frame", nil, box, 270, 60, "TOPLEFT", 0, 0)
    greet.GreetingText = fstring(greet, nil, "Greetings, Stu. The hunt has been poor this season.", 13, { 0.2, 0.1, 0.05, 1 })
    greet.GreetingText.w, greet.GreetingText.h = 270, 52
    box.rows[1] = greet
    for i, label in ipairs({ "I want to browse your goods.", "Train me in the ways of the Shaman.", "Make this inn my home.", "Taming the Beast" }) do
        local b = blz("Button", nil, box, 300, 16, "TOPLEFT", 0, -(70 + (i - 1) * 22))
        b.Icon = tex(b, nil, "BACKGROUND")
        b.Icon.w, b.Icon.h = 16, 16
        b.Icon.points[1] = { point = "TOPLEFT", rel = b, relPoint = "TOPLEFT", x = 3, y = 1 }
        b.highlightTex = tex(b, nil, "HIGHLIGHT")
        b.fs = fstring(b, nil, label, 12, { 0.2, 0.1, 0.05, 1 })
        b.fs.points[1] = { point = "LEFT", rel = b, relPoint = "LEFT", x = 20, y = 0 }
        b.scripts.OnClick = function() end
        b.scripts.OnEnter = function() end
        box.rows[#box.rows + 1] = b
    end
    -- a book
    local book = blz("Frame", "ItemTextFrame", UIParent, 338, 496)
    book.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 900, y = -80 }
    book.shown = false
    atex(book, "ItemTextFramePageBg", "BACKGROUND", "QuestBG-Parchment", 330, 440)
    local sf = blz("ScrollFrame", "ItemTextScrollFrame", book, 280, 360, "TOPLEFT", 20, -60)
    fstring(book, "ItemTextCurrentPage", "Page 1", 12, { 1, 0.82, 0, 1 }).points[1] = { point = "BOTTOM", rel = book, relPoint = "BOTTOM", x = 0, y = 40 }
    pager(book, "ItemTextPrevPageButton", "<").enabled = false
    pager(book, "ItemTextNextPageButton", ">")
end
"""

H = Harness({"ButtonSkins": "Core/ButtonSkins.lua", "FieldSkins": "Core/FieldSkins.lua", "Character": "Modules/Skins/Character.lua",
             "Quest": "Modules/Skins/Quest.lua"}, BLIZZARD)
case = H.case

OPEN = "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Show(); QuestInfo_Display(); FlushTimers()"
OPEN_PROGRESS = ("Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Hide(); QuestFrameProgressPanel:Show(); "
                 "QuestFrameProgressItems_Update(); FlushTimers()")

case("quest rewards: every button gets a card and a slot over its icon, the stock name plate and quality border are held, scripts stay", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local rf = QuestInfoRewardsFrame
    for i = 1, 5 do
        local b = rf.RewardButtons[i]
        assert(S.cards[b], 'button ' .. i .. ' not carded')
        assert(b.NameFrame.alpha == 0 and b.IconBorder.alpha == 0 and b.IconOverlay.alpha == 0 and b.IconOverlay2.alpha == 0, 'stock art kept on ' .. i)
        assert(b.Icon.alpha ~= 0, 'the icon must stay on ' .. i)
        assert(b.scripts.OnClick and b.scripts.OnEnter, 'stock script lost on ' .. i)
        assert(b.Name.fontPath ~= 'stock.ttf', 'name not mono on ' .. i)
        local host = S.slots[b]
        assert(host and FS.ItemSlotSkins.Parts(host), 'no slot layer on ' .. i)
        assert(b.Icon.points[1].rel == host, 'icon not seated in its slot on ' .. i)
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest rewards: the slot takes its quality from SetItemButtonQuality and a card dims when its row is empty", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local b = QuestInfoRewardsFrame.RewardButtons[2]
    SetItemButtonQuality(b, 4)
    local parts = FS.ItemSlotSkins.Parts(S.slots[b])
    local epic = FS.Theme.COLOR_QUALITY[4]
    assert(math.abs(parts.led.color[1] - epic[1]) < 0.01 and math.abs(parts.led.color[3] - epic[3]) < 0.01, 'LED not epic')
    SetItemButtonQuality(b, 2)
    assert(math.abs(parts.led.color[2] - FS.Theme.COLOR_QUALITY[2][2]) < 0.01, 'LED did not follow the quality')
""")

case("quest rewards: the picked choice lights pink, the other choices dim, a reward that is not a choice is untouched; the stock glow is held", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local rf = QuestInfoRewardsFrame
    local c1, c2, c3, r4 = rf.RewardButtons[1], rf.RewardButtons[2], rf.RewardButtons[3], rf.RewardButtons[4]
    local idle = S.cards[c1].box.edges[1].color
    assert(idle[3] > 0.4 and idle[1] < 0.4, 'idle edge not the dim violet')
    assert(not S.cards[c2].scrim.shown, 'a scrim before any pick')
    c2:RunScript('OnClick')
    local pink = S.cards[c2].box.edges[1].color
    assert(pink[1] > 0.9 and pink[2] < 0.3, 'picked card not pink')
    assert(S.cards[c1].scrim.shown and S.cards[c3].scrim.shown and not S.cards[c2].scrim.shown, 'the others must dim, the pick must not')
    assert(not S.cards[r4].scrim.shown, 'a plain reward dimmed')
    assert(S.cards[c2].reticle and S.cards[c2].reticle.tlH.shown, 'no lock-on brackets on the pick')
    for _, t in ipairs(rf.ItemHighlight.regions) do assert(t.alpha == 0, 'stock pick glow kept') end
    -- a new page clears the pick
    QuestInfoFrame.itemChoice = 0
    QuestInfo_Display()
    assert(not S.cards[c2].scrim.shown and not S.cards[c1].scrim.shown, 'the pick outlived the page')
""")

case("quest rewards: a card lights cyan under the hand and returns", f"""
    {OPEN}
    local S = FS.QuestSkin.state
    local b = QuestInfoRewardsFrame.RewardButtons[1]
    b:RunScript('OnEnter')
    assert(S.cards[b].box.edges[1].color[2] > 0.8 and S.cards[b].box.edges[1].color[1] < 0.3, 'hover edge not cyan')
    assert(FS.ItemSlotSkins.Parts(S.slots[b]).state.hover, 'the slot did not follow the hover')
    b:RunScript('OnLeave')
    assert(S.cards[b].box.edges[1].color[2] < 0.4, 'did not return to idle')
    assert(not FS.ItemSlotSkins.Parts(S.slots[b]).state.hover, 'the slot kept the hover')
""")

case("quest text: the headers and texts are mono, the money and XP lines wear the shared money style", f"""
    {OPEN}
    for _, n in ipairs({{ 'QuestInfoTitleHeader', 'QuestInfoDescriptionText', 'QuestInfoObjectivesHeader', 'QuestInfoObjectivesText',
        'QuestInfoObjective1', 'QuestInfoObjective2', 'QuestInfoRewardText' }}) do
        assert(_G[n].fontPath ~= 'stock.ttf', n .. ' not mono')
    end
    local rf = QuestInfoRewardsFrame
    assert(rf.Header.fontPath ~= 'stock.ttf' and rf.ItemChooseText.fontPath ~= 'stock.ttf' and rf.XPFrame.ReceiveText.fontPath ~= 'stock.ttf', 'rewards texts')
    assert(QuestInfoMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'money not styled')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest progress: the required items are cards with a slot, the money line is styled, the page texts are mono", f"""
    {OPEN_PROGRESS}
    local S = FS.QuestSkin.state
    for i = 1, 4 do
        local b = _G['QuestProgressItem' .. i]
        assert(S.cards[b] and S.slots[b], 'item ' .. i .. ' not skinned')
        assert(b.NameFrame.alpha == 0, 'name plate kept on ' .. i)
        assert(b.Count.fontPath ~= 'stock.ttf', 'count not mono')
    end
    assert(QuestProgressRequiredMoneyFrameGoldButtonText.fontPath ~= 'stock.ttf', 'fee not styled')
    assert(QuestProgressText.fontPath ~= 'stock.ttf' and QuestProgressTitleText.fontPath ~= 'stock.ttf', 'texts')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("quest greeting: the title buttons are cards, the stock highlight is held, the click stays", f"""
    Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameGreetingPanel:Show(); FlushTimers()
    local S = FS.QuestSkin.state
    local n = 0
    for b in pairs(S.rows) do n = n + 1 end
    assert(n >= 3, 'title buttons carded: ' .. n)
    for i = 1, 3 do
        local b = _G['QuestTitleButton' .. i]
        assert(S.rows[b] and b.highlightTex.alpha == 0, 'title button ' .. i .. ' not skinned')
        assert(b.scripts.OnClick, 'click lost')
        assert(b.fs.fontPath ~= 'stock.ttf', 'title not mono')
    end
    assert(GreetingText.fontPath ~= 'stock.ttf' and CurrentQuestsText.fontPath ~= 'stock.ttf', 'greeting texts')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: every row of the ScrollBox is a card, a recycled row is not carded twice, the greeting text is mono and the click stays", f"""
    Fire('PLAYER_ENTERING_WORLD'); GossipFrame:Show(); FlushTimers()
    local S = FS.QuestSkin.state
    local box = GossipFrame.GreetingPanel.ScrollBox
    local rows = 0
    for i, r in ipairs(box.rows) do
        if r.fs then
            rows = rows + 1
            assert(S.rows[r], 'option row ' .. i .. ' not carded')
            assert(r.highlightTex.alpha == 0, 'stock highlight kept')
            assert(r.scripts.OnClick and r.scripts.OnEnter, 'row script lost')
            assert(r.fs.fontPath ~= 'stock.ttf', 'row not mono')
        end
    end
    assert(rows == 4, 'rows ' .. rows)
    assert(box.rows[1].GreetingText.fontPath ~= 'stock.ttf', 'greeting not mono')
    local first = box.rows[2]
    local fillA = S.rows[first].box.fill
    box:Update()
    assert(S.rows[first].box.fill == fillA, 'recycled row carded twice')
    -- a row that arrives on a later page is carded by the Update hook
    local b = BLZ.blz('Button', nil, box, 300, 16, 'TOPLEFT', 0, -200)
    b.Icon = BLZ.tex(b, nil, 'BACKGROUND'); b.highlightTex = BLZ.tex(b, nil, 'HIGHLIGHT'); b.fs = BLZ.fstring(b, nil, 'New', 12)
    box.rows[#box.rows + 1] = b
    box:Update(); FlushTimers()
    assert(S.rows[b], 'a later row was not carded')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("gossip: a row lights cyan under the hand", f"""
    Fire('PLAYER_ENTERING_WORLD'); GossipFrame:Show(); FlushTimers()
    local S = FS.QuestSkin.state
    local r = GossipFrame.GreetingPanel.ScrollBox.rows[2]
    local e = S.rows[r].box.edges[1]
    assert(e.color[3] > 0.4 and e.color[1] < 0.4, 'idle edge not the dim violet')
    r:RunScript('OnEnter')
    assert(e.color[2] > 0.8 and e.color[1] < 0.3, 'hover edge not cyan')
    r:RunScript('OnLeave')
    assert(e.color[2] < 0.4, 'did not return to idle')
""")

case("books: the page keys hold the stock arrows and draw a cut key with a chevron, the page gets a ring box, the clicks stay", f"""
    Fire('PLAYER_ENTERING_WORLD'); ItemTextFrame:Show(); FlushTimers()
    local S = FS.QuestSkin.state
    local prev, nxt = ItemTextPrevPageButton, ItemTextNextPageButton
    local P = S.pagers
    assert(P[prev] and #P[prev].glyph == 9 and P[prev].key, 'prev key')
    assert(P[nxt] and #P[nxt].glyph == 9 and P[nxt].key, 'next key')
    assert(P[prev].key.ring.alpha ~= 0 and P[prev].key.fill.alpha ~= 0, 'the key must not be held')
    assert(prev.NormalTexture.alpha == 0 and nxt.NormalTexture.alpha == 0, 'stock arrow kept')
    assert(prev.scripts.OnClick and nxt.scripts.OnClick, 'page click lost')
    assert(P[prev].glyph[1].alpha == 0.35, 'disabled previous page not dimmed')
    assert(P[nxt].glyph[1].alpha == 1, 'enabled next page dimmed')
    prev:Enable()
    assert(P[prev].glyph[1].alpha == 1, 'enable did not undim')
    assert(S.page, 'no page box')
    assert(ItemTextCurrentPage.fontPath ~= 'stock.ttf', 'page number not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("nothing is built in combat; it is built when combat ends", f"""
    Reset()
    __combat = true
    Load({{ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins', 'ButtonSkins', 'FieldSkins', 'Character', 'Quest' }})
    assert(not QuestFrame.fsQuestSkin, 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(QuestFrame.fsQuestSkin and GossipFrame.fsQuestSkin and ItemTextFrame.fsQuestSkin, 'not built when combat ended')
""")

SCENES = {
    "detail": "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Show(); QuestInfo_Display(); QuestInfoRewardsFrame.RewardButtons[2]:RunScript('OnClick'); FlushTimers(); return DumpOps({ QuestFrame })",
    "progress": "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameDetailPanel:Hide(); QuestFrameProgressPanel:Show(); QuestFrameProgressItems_Update(); FlushTimers(); return DumpOps({ QuestFrame })",
    "greeting": "Fire('PLAYER_ENTERING_WORLD'); QuestFrame:Show(); QuestFrameGreetingPanel:Show(); FlushTimers(); return DumpOps({ QuestFrame })",
    "gossip": "Fire('PLAYER_ENTERING_WORLD'); GossipFrame:Show(); FlushTimers(); return DumpOps({ GossipFrame })",
    "book": "Fire('PLAYER_ENTERING_WORLD'); ItemTextFrame:Show(); FlushTimers(); return DumpOps({ ItemTextFrame })",
}

if __name__ == "__main__":
    raise SystemExit(H.main("quest skin", SCENES))
