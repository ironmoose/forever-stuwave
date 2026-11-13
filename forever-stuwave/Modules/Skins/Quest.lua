-- Forever STUwave: Quest, gossip and book windows
-- The quest pages (detail, progress, reward and the greeting list), the NPC dialog (gossip) and books and letters, restyled in
-- place from the QUEST, NPC AND CRAFT mockup (mockups/quest-npc-craft-2026-11-12.html, section B). The window chrome, the parchment
-- strip, the text retint, the text buttons (Accept, Decline, Complete, Goodbye) and the scroll bars already wear the shared panel
-- skin (Panels.lua and PanelSkins); this file adds the parts that were still stock. One section per window below.
--
-- Skin only, as in Commerce.lua and Character.lua: no SetScript, no SetAttribute, no reparent and no resize of a Blizzard frame,
-- post-hooks and alpha holds (FS.HeldArt) only, so every click, tooltip, reward pick and turn in stays stock. Names are the real
-- 12.1 tree (Blizzard_UIPanels_Game QuestFrame.xml, QuestInfo.xml, QuestFrameTemplates.xml, GossipFrame.xml and GossipFrameShared.xml,
-- ItemTextFrame.xml, Blizzard_ItemButton LargeItemButtonTemplate); each is feature-detected and a missing frame is skipped silently.
--
-- The reward and required item buttons are whole cards (147 x 41: the icon at the left, a name plate, a count), not slots, so the
-- shared item slot layer cannot take the button as its slot. A child frame the size of the stock icon, seated on it, is the slot
-- instead; its plate is drawn on the button behind the icon, and the stock icon is seated inside it (ItemSlotSkins.SeatIcon).
-- A pooled row (a gossip option, a quest title button) is skinned once, guarded by a weak table, whenever the ScrollBox updates.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the XP level bar with the pulsing gain, the have / need gauges on the required items with their amber and cyan
-- states, the "short 9s" and "pick a reward" chips, the speaker waveform and the typed greeting, the glyph per gossip option, the
-- level and group chips beside a quest title, the "ready" chips of the greeting list, and the leaf stack and page-turn sweep of a
-- book. The stock text, tick marks and icons they replace keep working.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.PaintBox and Char.PinColor and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.StyleMoney and Theme.AddCut2Texture and Theme.SkinCutButton,
    "Quest.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Q = {}
FS.QuestSkin = Q

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, row = { 0.059, 0.031, 0.125 }, band = { 0.102, 0.051, 0.173 },
}
Q.colors = C

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { cards = Weak(), slots = Weak(), quality = Weak(), rows = Weak(), pagers = Weak(), squares = Weak(), done = {}, choices = {}, watched = Weak() }
Q.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List = Char.List

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("quest:" .. name, ("|cffff4488Forever STUwave|r: quest skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end
Q.Step = Step

local function Region(frame, key)
    return type(frame) == "table" and type(frame[key]) == "table" and frame[key] or nil
end
Q.Region = Region

local function Mono(fs, host, px, color)
    if type(fs) == "table" then Kit.RestyleLabel(fs, host, px, color or C.text) end
end
Q.Mono = Mono

local function IconOf(button)
    return Char.IconOf and Char.IconOf(button) or nil
end

-------------------------------------------------------------------------------
-- Shared: a slot on a stock icon, a square slot, a card, a page key, a pooled list
-------------------------------------------------------------------------------

local SLOT_ART = { "NormalTexture", "IconBorder", "IconOverlay", "IconOverlay2", "ItemSlotBackground", "Background" }
local SLOT_GLOW = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture", "SearchOverlay" }

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(SLOT_ART) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(SLOT_GLOW) do HeldArt.Hold(button[f]) end
end

-- The state of a slot, read the way ItemSlotSkins asks: the quality the stock code handed SetItemButtonQuality (the button stores
-- none), and empty when there is no icon. `owner` is the stock button, or the slot itself when the button is the slot.
local function ReadSlot(slot)
    local owner = slot.fsOwner or slot
    local icon = IconOf(owner)
    local texture = icon and Plain(Try(icon.GetTexture, icon))
    local empty = texture == nil or texture == "" or texture == 0
    return { quality = S.quality[owner], empty = empty }
end

-- The quality the stock code hands SetItemButtonQuality, kept for the slots of this skin (the button stores none). One hook for
-- every window that has slots of ours (quest rewards, trade); installed with the first slot.
function Q.HookQuality()
    if S.done.quality then return end
    S.done.quality = true
    Kit.HookFunc(_G, "SetItemButtonQuality", function(button, quality)
        if type(button) ~= "table" then return end
        local slot = S.slots[button]
        if not (slot or S.squares[button]) then return end
        S.quality[button] = Plain(quality)
        local slotSkins = FS.ItemSlotSkins
        if slotSkins and slotSkins.Refresh then slotSkins.Refresh(slot or button) end
    end)
end

local function SeatCrop(icon)
    if type(icon) == "table" and type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
end

-- A square item button (a trade slot) is the slot itself: the stock art held, the cut plate and ring of the bags, the shared slot
-- layer (quality LED, glint, hover, lock), the icon seated and cropped. Idempotent.
function Q.SquareSlot(button)
    if type(button) ~= "table" or S.squares[button] then return end
    S.squares[button] = true
    Q.HookQuality()
    SweepSlotArt(button)
    if Theme.SLICE_CUT2_BUTTON_TEXTURE then
        pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    pcall(Theme.SkinCutButton or Theme.SkinButton, button, { count = button.Count })
    local icon = IconOf(button)
    SeatCrop(icon)
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, ReadSlot) and slotSkins.SeatIcon and icon then
        slotSkins.SeatIcon(button, icon)
    end
    Kit.HookFunc(button, "SetNormalTexture", function() SweepSlotArt(button) end)
end

-- A slot over the stock `icon` of a card button: a frame of the icon's size on the icon's anchor, the plate and ring of the cut
-- slot, the shared slot layer on it, the icon seated inside. Returns the slot frame (nil when the layer is missing).
function Q.CardSlot(button, icon)
    if type(button) ~= "table" or type(icon) ~= "table" or S.slots[button] then return S.slots[button] end
    local slotSkins = FS.ItemSlotSkins
    if not (slotSkins and slotSkins.Decorate and type(button.CreateTexture) == "function") then return nil end
    Q.HookQuality()
    local slot = CreateFrame("Frame", nil, button)
    slot.fsOwner, slot.Icon = button, icon
    S.slots[button] = slot
    local ok, point, rel, relPoint, x, y = pcall(icon.GetPoint, icon, 1)
    if ok and point and rel == button then
        slot:SetPoint(point, button, relPoint or point, x or 0, y or 0)
    else
        slot:SetPoint("TOPLEFT", button, "TOPLEFT", 0, 0)
    end
    local w, h = Plain(Try(icon.GetWidth, icon)), Plain(Try(icon.GetHeight, icon))
    slot:SetSize((type(w) == "number" and w > 0) and w or 39, (type(h) == "number" and h > 0) and h or 39)
    if Theme.SLICE_CUT2_BUTTON_TEXTURE then
        local plate = Theme.AddCut2Texture(button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -6)
        if plate then
            plate:ClearAllPoints()
            plate:SetPoint("TOPLEFT", slot, "TOPLEFT", 0, 0)
            plate:SetPoint("BOTTOMRIGHT", slot, "BOTTOMRIGHT", 0, 0)
        end
    end
    pcall(Theme.SkinCutButton or Theme.SkinButton, slot, {})
    SeatCrop(icon)
    if slotSkins.Decorate(slot, ReadSlot) and slotSkins.SeatIcon then slotSkins.SeatIcon(slot, icon) end
    -- the slot is not the widget under the hand, the card is: the card's hover drives the slot's
    local function hover(on)
        local p = slotSkins.Parts and slotSkins.Parts(slot)
        if p and p.state then
            p.state.hover = on
            slotSkins.Refresh(slot)
        end
    end
    Kit.HookScript(button, "OnEnter", function() hover(true) end)
    Kit.HookScript(button, "OnLeave", function() hover(false) end)
    return slot
end

-- The card of a one line stock row or a card button: a box (ink fill, a 1 px edge) on the row's rect, `padX` and `padY` UI units
-- out of it, painted by `paint(row)`. Follows the row's hover.
function Q.NewCard(row, padX, padY)
    local ref = row:CreateTexture(nil, "BACKGROUND", nil, -8)
    ref:SetPoint("TOPLEFT", row, "TOPLEFT", -(padX or 0), padY or 0)
    ref:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", 0, -(padY or 0))
    return { ref = ref, box = Char.Box(row, "BORDER", ref) }
end

-- A page key (the book's Prev and Next): the stock art held FIRST, then a cut-corner key PAGER px across centred on the stock
-- button, a cyan chevron of cells centred in it. Idle ink with a violet edge, hover lights the edge and glyph, disabled dims all.
-- dir is "<" or ">". The stock label beside the button stays where the stock code puts it, in mono.
local PAGER = { SIZE = 26, CUT = 5, STEP = 2, ROWS = 9, THICK = 2 }

local function PaintPager(btn)
    local s = S.pagers[btn]
    if not s then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and s.state and (s.state.hover or s.state.pressed)
    local edge = not on and C.dim or (hover and C.cyan or C.violet)
    Kit.PaintPlate(s.key, C.ink, 1, edge, on and 1 or 0.6, hover and 2 or 1)
    local g = hover and C.text or C.cyan
    for _, t in ipairs(s.glyph) do
        t:SetColorTexture(g[1], g[2], g[3], 1)
        t:SetAlpha(on and 1 or 0.35)
    end
    if s.label then
        local c = not on and C.muted or (hover and C.cyan or C.text)
        Char.PinColor(s.label, c)
    end
end

function Q.PagerKey(btn, dir)
    if type(btn) ~= "table" or S.pagers[btn] then return end
    HeldArt.HoldButton(btn)
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 32, bh or 32
    local P = PAGER
    local x, y = math.floor((bw - P.SIZE) / 2), math.floor((bh - P.SIZE) / 2)
    local s = { key = Kit.Plate(btn, P.CUT, P.SIZE, P.SIZE), glyph = {} }
    Kit.Place(s.key.fill, btn, x, y, P.SIZE, P.SIZE)
    Kit.Place(s.key.ring, btn, x, y, P.SIZE, P.SIZE)
    if s.key.ring2 then Kit.Place(s.key.ring2, btn, x + 1, y + 1, P.SIZE - 2, P.SIZE - 2) end
    local half = (P.ROWS - 1) / 2
    local gw, gh = half * P.STEP + P.THICK, P.ROWS * P.THICK
    local gx, gy = x + math.floor((P.SIZE - gw) / 2), y + math.floor((P.SIZE - gh) / 2)
    for row = 0, P.ROWS - 1 do
        local d = math.abs(row - half)
        local cx = dir == "<" and d * P.STEP or (half - d) * P.STEP
        s.glyph[#s.glyph + 1] = Kit.Rect(btn, gx + cx, gy + row * P.THICK, P.THICK, P.THICK, C.cyan, 1, "OVERLAY", 7)
    end
    for _, region in ipairs(List(btn, "GetRegions")) do
        if Try(region.GetObjectType, region) == "FontString" then
            Mono(region, btn, 12, C.text)
            s.label = region
        end
    end
    S.pagers[btn] = s
    s.state = Kit.Track(btn, PaintPager)
    for _, script in ipairs({ "OnEnable", "OnDisable", "OnShow" }) do Kit.HookScript(btn, script, PaintPager) end
    for _, m in ipairs({ "Enable", "Disable", "SetEnabled" }) do Kit.HookFunc(btn, m, function() PaintPager(btn) end) end
    PaintPager(btn)
end

-- Runs `perRow(row)` over the rows a ScrollBox holds now and again whenever it repaints (a new dialog page, a scroll): rows are
-- pooled, built after the window, and recycled, so every row is met through the box. Hooks installed once per box.
function Q.WatchRows(box, perRow)
    if type(box) ~= "table" then return end
    local function sweep()
        if type(box.ForEachFrame) == "function" then pcall(box.ForEachFrame, box, function(row) Step("row", perRow, row) end) end
    end
    sweep()
    if S.watched[box] then return end
    S.watched[box] = true
    for _, m in ipairs({ "Update", "FullUpdate", "SetDataProvider" }) do Kit.HookFunc(box, m, function() Kit.Later(sweep) end) end
end

-------------------------------------------------------------------------------
-- The quest pages (QuestFrame)
-------------------------------------------------------------------------------

local CARD_PAD = 1
local QUEST_OBJECTIVE_MAX = 10

local function PickedChoice(button)
    local info = _G.QuestInfoFrame
    local choice = type(info) == "table" and Plain(info.itemChoice) or nil
    if type(choice) ~= "number" or choice <= 0 then return false, false end
    local isChoice = button.type == "choice"
    return isChoice and Plain(Try(button.GetID, button)) == choice, isChoice
end

local function PaintCard(button)
    local card = S.cards[button]
    if not card then return end
    local picked, isChoice = PickedChoice(button)
    local anyPicked = false
    local info = _G.QuestInfoFrame
    if isChoice and type(info) == "table" then
        local choice = Plain(info.itemChoice)
        anyPicked = type(choice) == "number" and choice > 0
    end
    local hover = card.state and card.state.hover
    local edge = (picked and C.pink) or (hover and C.cyan) or C.dim
    Char.PaintBox(card.box, picked and C.band or C.row, 1, edge, 1, picked and 2 or 1)
    card.scrim:SetShown(anyPicked and not picked)
    if card.reticle then
        Kit.ShowReticle(card.reticle, picked)
        if picked then
            Kit.PaintReticle(card.reticle, C.pink, 1)
            local w, h = Kit.SizePx(card.veil)
            if w then Kit.SeatReticle(card.reticle, 0, 0, w, h, 3, 8) end
        end
    end
end

-- One reward, required or choice button: the stock name plate and quality border held (the icon and the stock count stay), a card
-- behind it, a slot on its icon, the name in mono, the dim and the lock-on brackets of a pick on a frame above the lot.
local function SkinItemCard(button)
    if type(button) ~= "table" or S.cards[button] or type(button.CreateTexture) ~= "function" then return end
    for _, f in ipairs({ "NameFrame", "IconBorder", "IconOverlay", "IconOverlay2" }) do HeldArt.Hold(button[f]) end
    local highlight = Try(button.GetHighlightTexture, button)
    HeldArt.Hold(highlight)
    local card = Q.NewCard(button, CARD_PAD, CARD_PAD)
    card.veil = CreateFrame("Frame", nil, button)
    card.veil:SetPoint("TOPLEFT", button, "TOPLEFT", -CARD_PAD, CARD_PAD)
    card.veil:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 0, -CARD_PAD)
    card.scrim = card.veil:CreateTexture(nil, "OVERLAY", nil, 2)
    card.scrim:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.62)
    card.scrim:SetAllPoints(card.veil)
    card.scrim:Hide()
    card.reticle = Kit.Reticle(card.veil, "OVERLAY", 7)
    Kit.ShowReticle(card.reticle, false)
    S.cards[button] = card
    local icon = IconOf(button)
    local slot = icon and Q.CardSlot(button, icon)
    if slot and button.Name then
        pcall(function()
            button.Name:ClearAllPoints()
            button.Name:SetPoint("LEFT", slot, "RIGHT", 6, 0)
        end)
    end
    Mono(button.Name, button, 12, C.text)
    Mono(button.Count, button, 11, C.text)
    card.state = Kit.Track(button, PaintCard)
    Kit.HookScript(button, "OnClick", function()
        for _, b in ipairs(S.choices) do PaintCard(b) end
    end)
    S.choices[#S.choices + 1] = button
    PaintCard(button)
end

local function SkinRewardButtons()
    local rf = _G.QuestInfoRewardsFrame
    local buttons = type(rf) == "table" and rf.RewardButtons or nil
    if type(buttons) == "table" then
        for _, b in ipairs(buttons) do SkinItemCard(b) end
    end
    for i = 1, 6 do SkinItemCard(_G["QuestProgressItem" .. i]) end
    for _, b in ipairs(S.choices) do PaintCard(b) end
end

-- The mono text of the pages, one size per role. The stock colour logic (a retint by Panels, an objective turning grey) is left
-- alone; only the headers and the title, which have one fixed meaning, are pinned.
local TEXTS = {
    { "QuestInfoTitleHeader", 20, C.text, true }, { "QuestProgressTitleText", 20, C.text, true },
    { "QuestInfoDescriptionText", 13 }, { "QuestInfoObjectivesText", 13 }, { "QuestInfoRewardText", 13 },
    { "QuestProgressText", 13 }, { "GreetingText", 13 }, { "QuestInfoSubTitleHeader", 12, C.cyan, true },
    { "QuestInfoObjectivesHeader", 12, C.cyan, true }, { "QuestInfoDescriptionHeader", 12, C.cyan, true },
    { "QuestProgressRequiredItemsText", 12, C.cyan, true }, { "QuestProgressRequiredMoneyText", 13 },
    { "CurrentQuestsText", 12, C.cyan, true }, { "AvailableQuestsText", 12, C.cyan, true },
    { "QuestInfoRewardsFrame.Header", 12, C.cyan, true }, { "QuestInfoRewardsFrame.ItemChooseText", 13 },
    { "QuestInfoRewardsFrame.ItemReceiveText", 13 }, { "QuestInfoXPFrame.ReceiveText", 13 }, { "QuestInfoXPFrame.ValueText", 13 },
}

local function Resolve(path)
    local node = _G
    for key in path:gmatch("[^.]+") do
        node = type(node) == "table" and node[key] or nil
    end
    return type(node) == "table" and node or nil
end

local function SkinQuestTexts()
    local win = _G.QuestFrame
    for _, spec in ipairs(TEXTS) do
        local fs = Resolve(spec[1])
        if fs and not S.done["text:" .. spec[1]] and type(fs.SetFont) == "function" then
            S.done["text:" .. spec[1]] = true
            Mono(fs, win or fs, spec[2], spec[3])
            if spec[4] then Char.PinColor(fs, spec[3]) end
        end
    end
    local rf = _G.QuestInfoRewardsFrame
    if rf and rf.XPFrame and not S.done["text:xp"] then
        S.done["text:xp"] = true
        Mono(rf.XPFrame.ReceiveText, win or rf, 13, C.text)
        Mono(rf.XPFrame.ValueText, win or rf, 13, C.text)
    end
    for i = 1, QUEST_OBJECTIVE_MAX do
        local o = _G["QuestInfoObjective" .. i]
        if o and not S.done["text:o" .. i] and type(o.SetFont) == "function" then
            S.done["text:o" .. i] = true
            Mono(o, win or o, 13, C.text)
        end
    end
    for _, name in ipairs({ "QuestInfoMoneyFrame", "QuestProgressRequiredMoneyFrame" }) do Theme.StyleMoney(_G[name]) end
    local rfMoney = rf and rf.MoneyFrame
    if rfMoney then Theme.StyleMoney(rfMoney) end
    -- the stock pick glow is a held texture of ours to draw instead
    local highlight = _G.QuestInfoItemHighlight
    if type(highlight) == "table" then
        for _, region in ipairs(List(highlight, "GetRegions")) do HeldArt.Hold(region) end
    end
end

function Q.RefreshQuest()
    Step("quest.texts", SkinQuestTexts)
    Step("quest.items", SkinRewardButtons)
end

local function SweepGreeting()
    local panel = _G.QuestFrameGreetingPanel
    local pool = type(panel) == "table" and panel.titleButtonPool or nil
    if type(pool) == "table" and type(pool.EnumerateActive) == "function" then
        pcall(function()
            for b in pool:EnumerateActive() do Step("greeting.row", Q.SkinRow, b) end
        end)
    end
end

-- A one line stock row (a gossip option, a quest title): a card on the row, the stock highlight held (the icon stays), the text in
-- mono, cyan under the hand.
local function PaintRow(row)
    local rec = S.rows[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, C.row, 1, hover and C.cyan or C.dim, 1, 1)
end

function Q.SkinRow(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    HeldArt.Hold(Try(row.GetHighlightTexture, row))
    local rec = Q.NewCard(row, 0, 0)
    S.rows[row] = rec
    local label = Try(row.GetFontString, row)
    if type(label) == "table" then Mono(label, row, 13, C.text) end
    rec.state = Kit.Track(row, PaintRow)
    PaintRow(row)
end

function Q.RefreshGreeting()
    Step("greeting.rows", SweepGreeting)
end

local function BuildQuest()
    local win = _G.QuestFrame
    if type(win) ~= "table" or S.done.quest then return end
    S.done.quest = true
    win.fsQuestSkin = true
    Kit.HookFunc(_G, "QuestInfo_Display", function() Q.RefreshQuest() end)
    Kit.HookFunc(_G, "QuestFrameProgressItems_Update", function() Q.RefreshQuest() end)
    Kit.HookFunc(_G, "QuestFrameGreetingPanel_OnShow", function() Q.RefreshGreeting() end)
    Q.HookQuality()
    for _, name in ipairs({ "QuestFrameDetailPanel", "QuestFrameProgressPanel", "QuestFrameRewardPanel" }) do
        Kit.HookScript(_G[name], "OnShow", function() Kit.Later(Q.RefreshQuest) end)
    end
    Kit.HookScript(_G.QuestFrameGreetingPanel, "OnShow", function() Kit.Later(Q.RefreshGreeting) end)
    Kit.HookScript(win, "OnShow", function() Kit.Later(function() Q.RefreshQuest(); Q.RefreshGreeting() end) end)
    Q.RefreshQuest()
    Q.RefreshGreeting()
end

-------------------------------------------------------------------------------
-- The NPC dialog (GossipFrame)
-------------------------------------------------------------------------------

local function SkinGossipRow(row)
    if type(row) ~= "table" then return end
    if row.GreetingText then
        -- the greeting paragraph is a frame of its own, not a button: text only
        if not S.done[row] then
            S.done[row] = true
            Mono(row.GreetingText, row, 13, C.text)
        end
        return
    end
    Q.SkinRow(row)
end

local function BuildGossip()
    local win = _G.GossipFrame
    if type(win) ~= "table" or S.done.gossip then return end
    local panel = win.GreetingPanel
    local box = type(panel) == "table" and panel.ScrollBox or nil
    if not box then return end
    S.done.gossip = true
    win.fsQuestSkin = true
    Q.WatchRows(box, SkinGossipRow)
    Kit.HookScript(win, "OnShow", function() Kit.Later(function() Q.WatchRows(box, SkinGossipRow) end) end)
end

-------------------------------------------------------------------------------
-- Books and letters (ItemTextFrame)
-------------------------------------------------------------------------------

local function BuildBook()
    local win = _G.ItemTextFrame
    if type(win) ~= "table" or S.done.book then return end
    S.done.book = true
    win.fsQuestSkin = true
    Q.PagerKey(_G.ItemTextPrevPageButton, "<")
    Q.PagerKey(_G.ItemTextNextPageButton, ">")
    local page = _G.ItemTextScrollFrame
    if type(page) == "table" and type(win.CreateTexture) == "function" then
        S.page = Char.Box(win, "OVERLAY", page)
        Char.PaintBox(S.page, C.ink, 0.5, C.violet, 1, 1)
    end
    local number = _G.ItemTextCurrentPage
    if type(number) == "table" then
        Mono(number, win, 12, C.muted)
        Char.PinColor(number, C.muted)
    end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("quest", BuildQuest)
    Step("gossip", BuildGossip)
    Step("book", BuildBook)
end

PanelSkins.RegisterInspect("Quest", { { name = "QuestFrame", guard = "fsQuestSkin" }, { name = "GossipFrame", guard = "fsQuestSkin" },
    { name = "ItemTextFrame", guard = "fsQuestSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
