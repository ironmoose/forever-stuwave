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
-- shared item slot layer cannot take the button as its slot. A child frame seated inside the card with the same padding on three
-- sides is the slot instead; its plate is drawn on the button behind the icon, and the stock icon is centred in it (the slot layer's
-- own icon box is moved to match). The name takes the rest of the card on one line, the count sits in the icon's corner.
--
-- The dialog (GossipFrame and the quest greeting list) is the "incoming transmission": a speaker band over the list (the NPC's
-- name from UnitName, a live waveform), the greeting typed in line by line with a cyan caret on a text card, then the option rows
-- landing one after another. Each row is a cut card on the stock row's rect with a glyph for what it does (the stock icon is held:
-- its atlas, path or file id says the kind) and a "ready" chip on a quest that can be turned in. Only a real button with text is a
-- card: the greeting frame and the spacers of the list get nothing, and a pooled frame that stops being a button drops its card.
-- Typing and landing are decorative and never in the way: a click on a row, the greeting or the window shows everything at once,
-- a row can be clicked while it is still invisible, and nothing runs while the window is hidden.
-- A pooled row (a gossip option, a quest title button) is skinned whenever the ScrollBox updates; the stock row height is fixed by
-- the ScrollBox, so a row fades in rather than rises.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the XP level bar with the pulsing gain, the have / need gauges on the required items with their amber and cyan
-- states, the "short 9s" and "pick a reward" chips, the level and group chips beside a quest title, and the leaf stack and
-- page-turn sweep of a book. The stock text, tick marks and icons they replace keep working.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.PaintBox and Char.PinColor and PanelSkins.RequireExport(
    Theme.ApplyMono and Theme.StyleMoney and Theme.AddCut2Texture and Theme.SkinCutButton,
    "Quest.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Q = {}
FS.QuestSkin = Q

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    gold = Theme.COLOR_GOLD or { 1, 0.8235, 0.2471 }, grey = { 0.478, 0.439, 0.588 },
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, row = { 0.059, 0.031, 0.125 }, band = { 0.102, 0.051, 0.173 },
    hair = Theme.COLOR_CTRL_HAIR or { 0.227, 0.129, 0.408 }, well = Theme.COLOR_CTRL_WELL or { 0.11, 0.063, 0.188 },
    dis = Theme.COLOR_CTRL_DIS or { 0.361, 0.329, 0.502 }, disEdge = Theme.COLOR_CTRL_DISEDGE or { 0.165, 0.094, 0.275 },
}
Q.colors = C

local function Weak() return setmetatable({}, { __mode = "k" }) end
-- cards, slots, rows, pagers, squares: what this file drew, by stock frame. textCards: the card behind a greeting paragraph, by its
-- FontString. intros: one per dialog window (the band, the typing, the landing). band and typed are the intro of the window shown last.
local S = {
    cards = Weak(), slots = Weak(), quality = Weak(), rows = Weak(), pagers = Weak(), squares = Weak(), done = {}, choices = {},
    watched = Weak(), textCards = Weak(), greeted = Weak(), rails = Weak(), intros = {}, bands = {}, stamp = 0,
}
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

-- A slot over the stock `icon` of a card button, seated inside the card: a frame SLOT_SEAT px in from the button's left and top
-- and as tall as the button less the same seat top and bottom (the card reaches one unit past the button on those three sides, so
-- the padding is equal), the plate and ring of the cut slot, the shared slot layer on it, the icon centred in it with ICON_MARGIN px
-- on every side. Returns the slot frame (nil when the layer is missing).
local SLOT_SEAT, ICON_MARGIN, NAME_GAP = 3, 5, 6

local function CardSlotSize(button)
    local _, h = Kit.SizePx(button)
    if not h then h = math.floor(41 * Kit.Ppu(button) + 0.5) end
    return math.max(24, h - 2 * SLOT_SEAT)
end

-- The slot layer lays its overlays out for a bag slot (an icon box 4 px in and 3 down, 10 short at the foot for the LED row). Ours
-- is centred, so the glint, the cooldown scrim, the hazard tape and the lock follow the icon, and the LED sits in the margin under
-- it. The layer lays out again on every size or scale change, so this runs after each (a hook on the slot and a re-seat).
local function FitSlot(slot)
    local icon = slot.Icon
    local size = Kit.SizePx(slot)
    if not size then return end
    local m = ICON_MARGIN
    local n = size - 2 * m
    if type(icon) == "table" then Kit.Place(icon, slot, m, m, n, n) end
    local slotSkins, K = FS.ItemSlotSkins, FS.Layout and FS.Layout.Controls
    local p = slotSkins and slotSkins.Parts and slotSkins.Parts(slot)
    if not (p and K) then return end
    p.iw, p.ih = n, n
    for _, key in ipairs({ "glint", "scrim", "hazard" }) do
        if p[key] then Kit.Move(p[key], m, m, n, n) end
    end
    if p.hazard and K.SLOT_HAZARD_SHEET then p.hazard:SetTexCoord(0, n / K.SLOT_HAZARD_SHEET, 0, n / K.SLOT_HAZARD_SHEET) end
    if p.lock and K.SLOT_LOCK then
        local at = m + math.floor((n - K.SLOT_LOCK) / 2)
        Kit.Move(p.lock, at, at, K.SLOT_LOCK, K.SLOT_LOCK)
    end
    if p.led and K.SLOT_LED_W then Kit.Move(p.led, math.floor((size - K.SLOT_LED_W) / 2), size - 4, K.SLOT_LED_W, K.SLOT_LED_H) end
end

function Q.CardSlot(button, icon)
    if type(button) ~= "table" or type(icon) ~= "table" or S.slots[button] then return S.slots[button] end
    local slotSkins = FS.ItemSlotSkins
    if not (slotSkins and slotSkins.Decorate and type(button.CreateTexture) == "function") then return nil end
    Q.HookQuality()
    local slot = CreateFrame("Frame", nil, button)
    slot.fsOwner, slot.Icon = button, icon
    S.slots[button] = slot
    local size = CardSlotSize(button)
    Kit.Place(slot, button, SLOT_SEAT, SLOT_SEAT, size, size)
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
    Kit.Place(icon, slot, ICON_MARGIN, ICON_MARGIN, size - 2 * ICON_MARGIN, size - 2 * ICON_MARGIN)
    if slotSkins.Decorate(slot, ReadSlot) then FitSlot(slot) end
    Kit.HookScript(slot, "OnSizeChanged", function() FitSlot(slot) end)
    Kit.Later(function() FitSlot(slot) end)
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

-- Seats a card's slot and its name: the slot from the button's size now, the name from the slot's right edge to the card's, so a
-- name of a dozen letters stays on one line (the stock name is 90 units wide and wraps).
local function SeatCard(button)
    local slot = S.slots[button]
    if not slot then return end
    local size = CardSlotSize(button)
    Kit.Move(slot, SLOT_SEAT, SLOT_SEAT, size, size)
    FitSlot(slot)
    local name = button.Name
    if type(name) == "table" and type(name.SetPoint) == "function" then
        local u = Kit.U(button, NAME_GAP)
        pcall(function()
            name:ClearAllPoints()
            name:SetPoint("LEFT", slot, "RIGHT", u, 0)
            name:SetPoint("RIGHT", button, "RIGHT", -u, 0)
        end)
    end
end

Kit.OnReseat(function()
    for button in pairs(S.slots) do SeatCard(button) end
end)

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
-- pooled, built after the window, and recycled, so every row is met through the box. `after(box)` runs once after each pass.
-- Hooks installed once per box. Returns the sweep, so a window that has just opened can run it at once.
function Q.WatchRows(box, perRow, after)
    if type(box) ~= "table" then return nil end
    if S.watched[box] then return S.watched[box] end
    local function sweep()
        S.stamp = S.stamp + 1
        if type(box.ForEachFrame) == "function" then pcall(box.ForEachFrame, box, function(row) Step("row", perRow, row) end) end
        if after then Step("rows.after", after, box) end
    end
    S.watched[box] = sweep
    sweep()
    for _, m in ipairs({ "Update", "FullUpdate", "SetDataProvider" }) do Kit.HookFunc(box, m, function() Kit.Later(sweep) end) end
    return sweep
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
    if icon and Q.CardSlot(button, icon) then SeatCard(button) end
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
    -- a slot decorated after combat ended, or laid out again by the layer, is fitted to its icon
    for _, slot in pairs(S.slots) do FitSlot(slot) end
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

-------------------------------------------------------------------------------
-- The dialog rows: a gossip option or a quest title is a cut card with a glyph, and a chip on a quest that is ready
-------------------------------------------------------------------------------

local GLYPHS = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\gossip_glyphs.tga"
local GLYPH_PX, GLYPH_X, BAR_W, BAR_INSET, ROW_GAP, CARD_H = 12, 6, 3, 3, 2, 20
-- A quest greeting row is at least ROW_PX tall (live ask 2026-11-14: bigger rows); the stock code sizes it to its text (16 units).
local ROW_PX = 24
local CHIP = { H = 14, PAD = 6, RIGHT = 6 }
-- Each quest row says what it is in words (live 2026-11-14: the marks alone did not tell new, in progress and ready apart).
local CHIP_OF = { qnew = { "new", C.gold }, qwip = { "in progress", C.grey }, qdone = { "ready", C.cyan } }

-- Cell of the 4 x 4 glyph sheet and tint of each kind (tools/assets/generate_gossip_glyphs.py: 16 px cells, the 12 px art 2 px in):
-- talk bubble 0, vendor bag 1, trainer book 2, inn house 3, flight plane 4, gold "!" 5, "?" 6, paid coin 7, bank vault 8,
-- battlemaster sword 9, tabard shield 10, healer cross 11, auction gavel 12, petition scroll 13, transmog hanger 14, work order
-- hammer 15. Every service is cyan, each its own mark (live ask 2026-11-14); the quest marks keep the gold ! and ?.
local KIND = {
    gossip = { 0, C.cyan }, vendor = { 1, C.cyan }, trainer = { 2, C.cyan }, binder = { 3, C.cyan }, flight = { 4, C.cyan },
    qnew = { 5, C.gold }, qdone = { 6, C.gold }, qwip = { 6, C.grey }, paid = { 7, C.cyan }, bank = { 8, C.cyan },
    battle = { 9, C.cyan }, tabard = { 10, C.cyan }, healer = { 11, C.cyan }, auction = { 12, C.cyan }, petition = { 13, C.cyan },
    transmog = { 14, C.cyan }, workorder = { 15, C.cyan },
}

local function GlyphCoords(cell)
    local x, y = (cell % 4) * 16 + 2, math.floor(cell / 4) * 16 + 2
    return x / 64, (x + GLYPH_PX) / 64, y / 64, (y + GLYPH_PX) / 64
end

-- A gossip option's icon is a file id (C_GossipInfo option .icon). The client turns the stock Interface\GossipFrame paths into
-- their ids (GetFileIDFromPath, in the 16001 globals dump), so the kind is read from the id the row was given; 132060, the
-- vendor bag, is the id warcraft.wiki.gg documents, kept in case the lookup is missing.
local ICON_FILES = {
    GossipGossipIcon = "gossip", VendorGossipIcon = "vendor", TrainerGossipIcon = "trainer", UnlearnGossipIcon = "trainer",
    BinderGossipIcon = "binder", InnGossipIcon = "binder", InnkeeperGossipIcon = "binder", TaxiGossipIcon = "flight",
    BankerGossipIcon = "bank", BattleMasterGossipIcon = "battle", TabardGossipIcon = "tabard", HealerGossipIcon = "healer",
    AuctioneerIcon = "auction", PetitionGossipIcon = "petition", TransmogrifyGossipIcon = "transmog",
    WorkOrderGossipIcon = "workorder",
}
local ICON_IDS = { [132060] = "vendor" }
do
    local lookup = _G.GetFileIDFromPath
    if type(lookup) == "function" then
        for file, kind in pairs(ICON_FILES) do
            local ok, id = pcall(lookup, "Interface\\GossipFrame\\" .. file)
            if ok and type(id) == "number" and id > 0 then ICON_IDS[id] = kind end
        end
    end
end

-- What the stock icon says it is, in lower case: its atlas, else its path, else the path of its file id. "" when it says nothing.
local function IconKey(icon)
    local atlas = Plain(Try(icon.GetAtlas, icon))
    if type(atlas) == "string" and atlas ~= "" then return atlas:lower() end
    local tex = Plain(Try(icon.GetTexture, icon))
    if type(tex) == "number" and ICON_IDS[tex] then return "kind:" .. ICON_IDS[tex] end
    if type(tex) == "number" then
        local api = _G.C_Texture
        tex = type(api) == "table" and Plain(Try(api.GetFilenameFromFileDataID, tex)) or nil
    end
    if type(tex) == "string" then return (tex:gsub("\\", "/"):lower()) end
    return ""
end

local function Has(key, part) return key:find(part, 1, true) ~= nil end

-- The kind of a row from what the client gave it, never from its place in the list: a coin in the text is a paid option; the quest
-- marks are told by the icon (in progress, available or a daily offer, ready); the rest by the gossip icon. Anything else is a
-- talk bubble.
local function KindOf(key, text)
    if Has(text:lower(), "moneyframe") then return "paid" end
    if key:sub(1, 5) == "kind:" then return key:sub(6) end
    if Has(key, "inprogress") or Has(key, "incomplete") then return "qwip" end
    if Has(key, "available") or key:find("dailyactive[a-z]*quest") then return "qnew" end
    if key:find("active[a-z]*quest") then return "qdone" end
    for file, kind in pairs(ICON_FILES) do
        if Has(key, file:lower()) then return kind end
    end
    return "gossip"
end

-- The status of a gossip option by its order index, read once per pass over the rows.
local function OptionStatus(id)
    if S.statusStamp ~= S.stamp then
        S.statusStamp, S.status = S.stamp, {}
        local api = _G.C_GossipInfo
        local list = type(api) == "table" and Plain(Try(api.GetOptions)) or nil
        if type(list) == "table" then
            for _, option in ipairs(list) do
                local index = type(option) == "table" and Plain(option.orderIndex) or nil
                if type(index) == "number" then S.status[index] = Plain(option.status) end
            end
        end
    end
    return id ~= nil and S.status[id] or nil
end

-- A quest row's state from the quest data, not its icon (the 16001 icon names did not match, so every quest read as a talk
-- bubble): a greeting title button carries isActive (1 a quest of yours, 0 one on offer) and its index; a gossip row carries its
-- element data (buttonType 4 a quest of yours, 5 one on offer, info.isComplete). nil for anything that is not a quest.
local function QuestKind(row)
    local data = Plain(Try(row.GetElementData, row))
    if type(data) == "table" then
        local bt = Plain(data.buttonType)
        if bt == (_G.GOSSIP_BUTTON_TYPE_AVAILABLE_QUEST or 5) then return "qnew" end
        if bt == (_G.GOSSIP_BUTTON_TYPE_ACTIVE_QUEST or 4) then
            local info = type(data.info) == "table" and data.info or nil
            return info and Plain(info.isComplete) == true and "qdone" or "qwip"
        end
        return nil
    end
    local active = Plain(row.isActive)
    if active == 0 then return "qnew" end
    if active == 1 then
        local id = Plain(Try(row.GetID, row))
        local fn = _G.GetActiveTitle
        if type(id) == "number" and type(fn) == "function" then
            local _, done = Try(fn, id)
            return Plain(done) and "qdone" or "qwip"
        end
    end
    return nil
end

-- Greyed in the stock row: a quest whose mark the stock code dimmed (trivial or ignored), an option the client says is not
-- available or locked.
local function IsDim(row, icon, kind)
    if kind:sub(1, 1) == "q" then
        local r = Plain(Try(icon.GetVertexColor, icon))
        return type(r) == "number" and r < 0.8
    end
    local status = OptionStatus(Plain(Try(row.GetID, row)))
    if type(status) ~= "number" then return false end
    local E = type(_G.Enum) == "table" and _G.Enum.GossipOptionStatus or nil
    return status == (E and E.Unavailable or 1) or status == (E and E.Locked or 2)
end

-- The stock icon and text of a row that is a button: nothing for a spacer, the greeting frame, a frame with no icon or no text.
local function RowIcon(row)
    local icon = IconOf(row)
    if not icon or type(row.GetFontString) ~= "function" then return nil end
    local text = Plain(Try(row.GetText, row))
    if type(text) ~= "string" or not text:find("%S") then return nil end
    return icon, text
end

local function PaintRow(row)
    local rec = S.rows[row]
    if not (rec and rec.on) then return end
    local hover = rec.state and rec.state.hover and true or false
    Kit.PaintPlate(rec.plate, hover and C.well or C.row, 1, hover and C.cyan or (rec.dim and C.disEdge or C.hair), 1, 1)
    rec.bar:SetShown(hover)
    local tint = rec.dim and C.dis or (KIND[rec.kind] or KIND.gossip)[2]
    rec.glyph:SetVertexColor(tint[1], tint[2], tint[3], 1)
end

local function ShowRow(rec, on)
    rec.fill:SetShown(on)
    rec.ring:SetShown(on)
    rec.glyph:SetShown(on)
    if not on then rec.bar:Hide() end
end

-- The "ready" chip: made when a quest first needs it, right of the row, centred on its line.
local function SetChip(row, rec, on, h)
    local spec = CHIP_OF[rec.kind]
    on = on and spec ~= nil
    if on and not rec.chip then
        local plate = Kit.Plate(row, 2, 40, CHIP.H)
        rec.chipPlate, rec.chip, rec.chipRing = plate, plate.fill, plate.ring
        rec.chipLabel = Kit.Label(row, spec[1], 11, spec[2], "OVERLAY")
    end
    if not rec.chip then return end
    if on then
        Kit.PaintPlate(rec.chipPlate, C.ink, 1, spec[2], 1, 1)
        if rec.chipText ~= spec[1] then
            rec.chipText = spec[1]
            rec.chipLabel:SetText(spec[1])
        end
        Kit.Recolor(rec.chipLabel, spec[2])
        local sw = Plain(Try(rec.chipLabel.GetStringWidth, rec.chipLabel))
        local w = math.ceil((type(sw) == "number" and sw or 30) * Kit.Ppu(row)) + 2 * CHIP.PAD
        -- on the card's whole pixels (LayoutRow), never taller than the card: a 1 px edge on a fraction of a pixel is cut
        local g = rec.grid or { dx = 0, dy = 0, top = 0, ch = h, cw = 300 }
        local ppu = Kit.Ppu(row)
        local ch = math.min(CHIP.H, g.ch - 4)
        local x = g.dx + g.cw - CHIP.RIGHT - w
        local y = g.top + g.dy + math.floor((g.ch - ch) / 2)
        for _, t in ipairs({ rec.chip, rec.chipRing }) do
            t:ClearAllPoints()
            t:SetPoint("TOPLEFT", row, "TOPLEFT", x / ppu, -y / ppu)
            t:SetSize(w / ppu, ch / ppu)
        end
        rec.chipLabel:ClearAllPoints()
        rec.chipLabel:SetPoint("CENTER", rec.chip, "CENTER", 0, 0)
    end
    rec.chip:SetShown(on)
    rec.chipRing:SetShown(on)
    rec.chipLabel:SetShown(on)
end

-- Seats the card on the stock row's rect (a pixel in from the top and bottom), the glyph 12 px in the gutter before the label and
-- centred on the row's height, the hover bar on the left edge. Returns the row's height in pixels.
local function LayoutRow(row, rec)
    local w, h = Kit.SizePx(row)
    if not h then w, h = 300, math.floor(16 * Kit.Ppu(row) + 0.5) end
    -- the stock rows sit edge to edge (and a row restyled to the mono label can stand a little taller than its slot), so the
    -- card is at most CARD_H px tall and centred on the row, ROW_GAP px in from each edge: neighbouring cards and their hover
    -- rings keep a gap between them. The stock rows sit on fractions of a pixel, and a 1 px edge on a fraction draws as no line
    -- on one side and a thick one on the other (live 2026-11-14, the hover ring), so the card is moved onto whole pixels: dx and
    -- dy are what the row's own left and top lack.
    local ppu = Kit.Ppu(row)
    local left, top0 = Plain(Try(row.GetLeft, row)), Plain(Try(row.GetTop, row))
    local dx = type(left) == "number" and (1 - (left * ppu) % 1) % 1 or 0
    local dy = type(top0) == "number" and (top0 * ppu) % 1 or 0
    local ch = math.max(8, math.min(h - 2 * ROW_GAP, CARD_H))
    local top = math.floor((h - ch) / 2)
    local cw = w - 1
    rec.grid = { dx = dx, dy = dy, top = top, ch = ch, cw = cw }
    local function seat(t, inset)
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", row, "TOPLEFT", (dx + inset) / ppu, -(top + dy + inset) / ppu)
        t:SetSize((cw - 2 * inset) / ppu, (ch - 2 * inset) / ppu)
    end
    seat(rec.fill, 0)
    seat(rec.ring, 0)
    if rec.plate.ring2 then seat(rec.plate.ring2, 1) end
    rec.glyph:ClearAllPoints()
    rec.glyph:SetPoint("TOPLEFT", row, "TOPLEFT", (dx + GLYPH_X) / ppu, -(top + dy + math.floor((ch - GLYPH_PX) / 2)) / ppu)
    rec.glyph:SetSize(GLYPH_PX / ppu, GLYPH_PX / ppu)
    rec.bar:ClearAllPoints()
    rec.bar:SetPoint("TOPLEFT", row, "TOPLEFT", (dx + 1) / ppu, -(top + dy + BAR_INSET) / ppu)
    rec.bar:SetSize(BAR_W / ppu, math.max(2, ch - 2 * BAR_INSET) / ppu)
    return h
end

-- A quest greeting row (a QuestFrameGreetingPanel title button: it has isActive, and the panel chains each row under the one
-- before) is made ROW_PX tall when the stock code left it shorter; the rows under it follow by their anchors. Gossip rows sit in a
-- scroll box that measures them itself, so they keep their height.
local function GrowRow(row)
    if Plain(row.isActive) == nil or type(row.SetHeight) ~= "function" then return end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return end
    local _, h = Kit.SizePx(row)
    if h and h < ROW_PX then pcall(row.SetHeight, row, ROW_PX / Kit.Ppu(row)) end
    -- QuestTitleButtonTemplate pins its label TOPLEFT (20, 0), so in the taller row it rode the top of the card (live
    -- 2026-11-14); it keeps its 20 units in and is centred on the row's height instead
    local label = Try(row.GetFontString, row)
    if type(label) == "table" and type(label.SetPoint) == "function" and not S.centred[label] then
        S.centred[label] = true
        label:ClearAllPoints()
        label:SetPoint("LEFT", row, "LEFT", 20, 0)
    end
end

local function BuildRow(row, owner, icon)
    HeldArt.Hold(Try(row.GetHighlightTexture, row))
    HeldArt.Hold(icon)
    local plate = Kit.Plate(row, 3, 300, 19)
    local rec = { plate = plate, fill = plate.fill, ring = plate.ring, owner = owner, on = false }
    rec.glyph = Kit.Glyph(row, GLYPHS, GLYPH_X, 3, GLYPH_PX, GLYPH_PX, C.cyan, 1, "ARTWORK", 2)
    rec.bar = Kit.Rect(row, 0, BAR_INSET, BAR_W, 12, C.cyan, 1, "OVERLAY", 5)
    rec.bar:Hide()
    S.rows[row] = rec
    local label = Try(row.GetFontString, row)
    rec.label = type(label) == "table" and label or nil
    if rec.label then Mono(rec.label, row, 13, C.text) end
    rec.state = Kit.Track(row, PaintRow)
    -- the list grows a row after it was carded (GrowGossip, GrowRow) and moves it: the card follows the new rect
    Kit.HookScript(row, "OnSizeChanged", function()
        if not rec.on then return end
        local h = LayoutRow(row, rec)
        if rec.chip and rec.chip:IsShown() then SetChip(row, rec, true, h) end
    end)
    -- a press on a row shows the whole transmission at once; the stock click that follows is untouched
    Kit.HookScript(row, "OnMouseDown", function() Q.Skip(rec.owner) end)
    return rec
end

-- A frame that was a button and is a spacer (or an empty row) now drops its card and gives its alpha back.
function Q.DropRow(row)
    local rec = S.rows[row]
    if not (rec and rec.on) then return end
    rec.on = false
    ShowRow(rec, false)
    if rec.chip then
        rec.chip:Hide()
        rec.chipRing:Hide()
        rec.chipLabel:Hide()
    end
    if rec.label then pcall(rec.label.SetAlpha, rec.label, 1) end
    pcall(row.SetAlpha, row, 1)
end

-- A one line stock row (a gossip option, a quest title). Only a button with an icon and text is carded; read again on every pass,
-- because the frame is pooled and the next element may be another kind, or a spacer.
function Q.SkinRow(row, owner)
    if type(row) ~= "table" or type(row.CreateTexture) ~= "function" then return end
    local rec = S.rows[row]
    local icon, text = RowIcon(row)
    if not icon then
        if rec then Q.DropRow(row) end
        return
    end
    local kind = QuestKind(row) or KindOf(IconKey(icon), text)
    HeldArt.Hold(icon)
    HeldArt.Hold(row.Icon) -- the stock mark under ours (live 2026-11-14: a vendor row showed both)
    if not rec then rec = BuildRow(row, owner, icon) end
    GrowRow(row)
    rec.owner = owner or rec.owner
    rec.kind, rec.dim = kind, IsDim(row, icon, kind)
    if not rec.on then
        rec.on = true
        ShowRow(rec, true)
    end
    rec.glyph:SetTexCoord(GlyphCoords((KIND[kind] or KIND.gossip)[1]))
    SetChip(row, rec, true, LayoutRow(row, rec))
    if rec.label then pcall(rec.label.SetAlpha, rec.label, rec.dim and 0.55 or 1) end
    PaintRow(row)
end

local function OnReseatRows()
    for row, rec in pairs(S.rows) do
        if rec.on then
            local h = LayoutRow(row, rec)
            if rec.chip and rec.chip:IsShown() then SetChip(row, rec, true, h) end
        end
    end
end

-------------------------------------------------------------------------------
-- The speaker band, the typed greeting and the landing of the rows
-------------------------------------------------------------------------------

local BAND = {
    H = 40, GAP = 6, PAD = 6, LETTER = 28, NAME_X = 42, BARS = 16, PITCH = 5, BAR_W = 3, BAR_MAX = 24, BAR_MIN = 2,
    CHIP_H = 16, CHIP_PAD = 7, WAVE_GAP = 10, NAME_GAP = 8, STEP = 0.06,
}
local TYPE = { CPS = 80, GRADIENT = 5, CARET_W = 6, LAND_STEP = 0.07, LAND_TIME = 0.35, PAD = 6 }

-- How the greeting arrives (live ask 2026-11-14: "people don't want to wait"): typed at 240 a second (the default), at the
-- first 80, or all at once with the rows already in place.
Q.SPEED_SETTING = {
    key = "quest.textSpeed", label = "Dialog text", default = "fast",
    tip = "How the text in quest and gossip windows appears: typed out fast, typed at the slower original speed, or all at once.",
    options = { { value = "instant", text = "Instant" }, { value = "fast", text = "Fast" }, { value = "normal", text = "Normal" } },
}
local SPEED_CPS = { fast = 240, normal = 80 }
if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(Q.SPEED_SETTING.key, Q.SPEED_SETTING.default) end

local function Speed()
    local cfg = FS.Config
    local ok, v = false, nil
    if cfg and cfg.Get then ok, v = pcall(cfg.Get, Q.SPEED_SETTING.key) end
    if ok and (v == "instant" or SPEED_CPS[v]) then return v end
    return Q.SPEED_SETTING.default
end

local WAVE_SPEED, WAVE_PHASE = {}, {}
for i = 1, BAND.BARS do
    WAVE_SPEED[i] = 5 + (i * 7) % 6
    WAVE_PHASE[i] = i * 1.7
end

-- The name of whoever is speaking, from the unit the dialog is open on. A secret or missing name is "unknown".
local function NpcName()
    for _, unit in ipairs({ "npc", "questnpc" }) do
        local name = Plain(Try(_G.UnitName, unit))
        if type(name) == "string" and name:find("%S") then return name end
    end
    return nil
end

function Q.RefreshBand(band)
    local name = NpcName()
    band.name:SetText(name or "unknown")
    local initial = name and name:match("^[%z\1-\127\194-\244][\128-\191]*") or "?"
    band.letter:SetText(initial:upper())
end

-- Seats the band 6 px over the list, as wide as it, 40 px tall; the "speaking" chip at its right end, the waveform left of the chip
-- and the name between the initial and the waveform. Every number is whole pixels from the edge it is seated on.
function Q.LayoutBand(band)
    if band.laying then return end
    band.laying = true
    local f = band.frame
    local u = Kit.U(f, 1)
    f:ClearAllPoints()
    f:SetPoint("BOTTOMLEFT", band.ref, "TOPLEFT", 0, BAND.GAP * u)
    f:SetPoint("BOTTOMRIGHT", band.ref, "TOPRIGHT", 0, BAND.GAP * u)
    f:SetHeight(BAND.H * u)
    local sw = Plain(Try(band.chipLabel.GetStringWidth, band.chipLabel))
    local cw = math.ceil((type(sw) == "number" and sw or 40) * Kit.Ppu(f)) + 2 * BAND.CHIP_PAD
    Kit.Place(band.chipBox, f, -BAND.PAD, (BAND.H - BAND.CHIP_H) / 2, cw, BAND.CHIP_H, "TOPRIGHT", "TOPRIGHT")
    local right = BAND.PAD + cw + BAND.WAVE_GAP
    for i, bar in ipairs(band.bars) do
        local h = band.h[i] or BAND.BAR_MIN
        band.h[i] = h
        band.bx[i] = -(right + (BAND.BARS - i) * BAND.PITCH)
        Kit.Place(bar, f, band.bx[i], (BAND.H - h) / 2, BAND.BAR_W, h, "TOPRIGHT", "TOPRIGHT")
    end
    local waveLeft = right + (BAND.BARS - 1) * BAND.PITCH + BAND.BAR_W
    band.name:ClearAllPoints()
    band.name:SetPoint("LEFT", f, "LEFT", BAND.NAME_X * u, 0)
    band.name:SetPoint("RIGHT", f, "RIGHT", -(waveLeft + BAND.NAME_GAP) * u, 0)
    band.laying = false
end

-- One frame of the waveform at `t` seconds: each bar a sine of its own speed and phase, an even height (so it stays centred on
-- whole pixels) between BAR_MIN and BAR_MAX.
function Q.WaveStep(band, t)
    for i, bar in ipairs(band.bars) do
        local s = 0.5 + 0.5 * math.sin(t * WAVE_SPEED[i] + WAVE_PHASE[i])
        local h = BAND.BAR_MIN + 2 * math.floor(s * (BAND.BAR_MAX - BAND.BAR_MIN) / 2 + 0.5)
        if h ~= band.h[i] then
            band.h[i] = h
            Kit.Move(bar, band.bx[i], (BAND.H - h) / 2, BAND.BAR_W, h)
        end
    end
end

-- The wave runs only while its window is open (the shared ticker skips a hidden owner, and Q.WindowHidden stops it), 15 times a second.
function Q.BandStart(band)
    Kit.Animate(band.frame, "wave", function(dt, elapsed)
        band.acc = band.acc + dt
        if band.acc < BAND.STEP then return end
        band.acc = 0
        band.ticks = band.ticks + 1
        Q.WaveStep(band, elapsed)
    end)
end

function Q.BandStop(band)
    Kit.StopAnimate(band.frame, "wave")
end

-- The band over a list: `parent` is the stock panel it lives and dies with, `ref` the list it sits on. It draws under the NPC
-- friendship bar of the window (`friend`), which stock puts in the same strip.
function Q.NewBand(parent, ref, friend)
    if type(parent) ~= "table" or type(ref) ~= "table" or type(CreateFrame) ~= "function" then return nil end
    local f = CreateFrame("Frame", nil, parent)
    local level = friend and Plain(Try(friend.GetFrameLevel, friend))
    if type(level) == "number" then level = level - 1 else level = (Plain(Try(parent.GetFrameLevel, parent)) or 0) + 1 end
    f:SetFrameLevel(math.max(0, level))
    local band = { frame = f, ref = ref, bars = {}, h = {}, bx = {}, ticks = 0, acc = 0 }
    band.plate = Kit.Plate(f, 4, 360, BAND.H)
    Kit.PaintPlate(band.plate, C.band, 1, C.violet, 1, 1)
    band.box = CreateFrame("Frame", nil, f)
    Kit.Place(band.box, f, BAND.PAD, (BAND.H - BAND.LETTER) / 2, BAND.LETTER, BAND.LETTER)
    Kit.PaintPlate(Kit.Plate(band.box, 3, BAND.LETTER, BAND.LETTER), C.ink, 1, C.pink, 1, 1)
    band.letter = Kit.Label(band.box, "?", 16, C.pink)
    Kit.Place(band.letter, band.box, 0, 0, nil, nil, "CENTER", "CENTER")
    band.name = Kit.Label(f, "", 15, C.text)
    band.chipBox = CreateFrame("Frame", nil, f)
    Kit.PaintPlate(Kit.Plate(band.chipBox, 2, 60, BAND.CHIP_H), C.ink, 1, C.cyan, 1, 1)
    band.chipLabel = Kit.Label(band.chipBox, "speaking", 11, C.cyan)
    Kit.Place(band.chipLabel, band.chipBox, 0, 0, nil, nil, "CENTER", "CENTER")
    for i = 1, BAND.BARS do
        band.bars[i] = Kit.Rect(f, 0, 0, BAND.BAR_W, BAND.BAR_MIN, C.cyan, 0.35 + ((i * 7) % 10) / 16, "OVERLAY", 3)
    end
    S.bands[#S.bands + 1] = band
    Q.LayoutBand(band)
    Q.WaveStep(band, 0)
    Q.RefreshBand(band)
    return band
end

Kit.OnReseat(function()
    for _, band in ipairs(S.bands) do Q.LayoutBand(band) end
    OnReseatRows()
end)

-- The number of characters the typing counts: the text as drawn, without colour and texture codes.
local function CountChars(text)
    local shown = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", ""):gsub("|H.-|h", ""):gsub("|h", "")
    return select(2, shown:gsub("[^\128-\191]", ""))
end

function Q.NewIntro(kind, parent, ref, friend)
    local band = Q.NewBand(parent, ref, friend)
    if not band then return nil end
    local intro = { kind = kind, band = band, items = {}, touched = Weak(), carets = Weak(), fresh = true }
    S.intros[kind] = intro
    return intro
end

-- The caret is a texture of the frame the paragraph lives on, so it scrolls and clips with it.
function Q.CaretFor(intro, host)
    local caret = intro.carets[host]
    if not caret and type(host.CreateTexture) == "function" then
        caret = Kit.Rect(host, 0, 0, TYPE.CARET_W, 10, C.cyan, 1, "OVERLAY", 6)
        caret:Hide()
        intro.carets[host] = caret
    end
    if intro.caret and intro.caret ~= caret then intro.caret:Hide() end
    return caret
end

-- The caret after character `n` of the paragraph, whole pixels from its top left, the height of the line it is on. The span the
-- client answers for comes as { left, bottom, width, height } rects from the paragraph's bottom left; anything else hides the caret.
function Q.PlaceCaret(intro, n)
    local caret, fs, host = intro.caret, intro.fs, intro.host
    if not caret then return end
    local index = math.min(math.max(n, 1), math.max(intro.total, 1))
    local areas = Plain(Try(fs.CalculateScreenAreaFromCharacterSpan, fs, index, index))
    local a = type(areas) == "table" and areas[#areas] or nil
    local left, bottom, width, height, full
    if type(a) == "table" then
        left, bottom, width, height = Plain(a.left), Plain(a.bottom), Plain(a.width), Plain(a.height)
        full = Plain(Try(fs.GetHeight, fs))
    end
    if not (type(left) == "number" and type(bottom) == "number" and type(width) == "number" and type(height) == "number"
        and type(full) == "number") then
        caret:Hide()
        return
    end
    local ppu = Kit.Ppu(host)
    local x = math.floor((n < 1 and left or left + width) * ppu + 0.5) + (n < 1 and 0 or 1)
    local y = math.floor((full - bottom - height) * ppu + 0.5) + 1
    Kit.Place(caret, fs, x, y, TYPE.CARET_W, math.max(6, math.floor(height * ppu + 0.5) - 2), "TOPLEFT", "TOPLEFT", host)
    caret:Show()
end

function Q.Reveal(intro, n)
    local fs = intro.fs
    pcall(fs.SetAlphaGradient, fs, n, TYPE.GRADIENT)
    Q.PlaceCaret(intro, n)
end

local function HideItem(intro, row)
    intro.touched[row] = true
    pcall(row.SetAlpha, row, 0)
end

-- Gives everything back: the stock paragraph with no gradient, every row at full alpha, no caret, nothing running. Safe at any time.
function Q.EndIntro(intro)
    Kit.StopAnimate(intro.band.frame, "intro")
    intro.running, intro.phase = false, nil
    local fs = intro.fs
    if type(fs) == "table" and type(fs.ClearAlphaGradient) == "function" then pcall(fs.ClearAlphaGradient, fs) end
    if intro.caret then intro.caret:Hide() end
    for row in pairs(intro.touched) do pcall(row.SetAlpha, row, 1) end
    intro.touched = Weak()
end

-- A click, a press on a row, the greeting or the window: the whole transmission now.
function Q.Skip(intro)
    if intro and intro.running then Q.EndIntro(intro) end
end

-- One frame of the intro: the characters up to the clock (the gradient start), the caret behind them; when the text is whole the
-- rows land one after another, each a quad-eased fade. The alpha is the row's own, so a click lands whatever it is.
function Q.IntroTick(intro, elapsed)
    if intro.phase == "type" then
        local n = math.floor(elapsed * (intro.cps or TYPE.CPS))
        if n >= intro.total + TYPE.GRADIENT then
            local fs = intro.fs
            pcall(fs.ClearAlphaGradient, fs)
            if intro.caret then intro.caret:Hide() end
            intro.phase, intro.landStart = "land", elapsed
        elseif n ~= intro.shown then
            intro.shown = n
            Q.Reveal(intro, n)
        end
    end
    if intro.phase == "land" then
        local t = elapsed - intro.landStart
        local items = intro.items
        for k, row in ipairs(items) do
            local p = (t - (k - 1) * TYPE.LAND_STEP) / TYPE.LAND_TIME
            p = p < 0 and 0 or (p > 1 and 1 or p)
            intro.touched[row] = true
            pcall(row.SetAlpha, row, Kit.Ease.outQuad(p))
        end
        if t >= (#items - 1) * TYPE.LAND_STEP + TYPE.LAND_TIME then Q.EndIntro(intro) end
    end
end

function Q.StartIntro(intro, fs, host, text, items)
    Q.EndIntro(intro)
    intro.fresh, intro.fs, intro.host, intro.text, intro.items = false, fs, host, text, items
    local speed = Speed()
    if speed == "instant" then return end
    intro.cps = SPEED_CPS[speed]
    intro.total, intro.shown, intro.landStart = CountChars(text), -1, 0
    local canType = type(fs.SetAlphaGradient) == "function"
    for _, row in ipairs(items) do HideItem(intro, row) end
    intro.caret = canType and Q.CaretFor(intro, host) or nil
    intro.phase, intro.running = canType and "type" or "land", true
    if canType then Q.Reveal(intro, 0) end
    Kit.Animate(intro.band.frame, "intro", function(_, elapsed) Q.IntroTick(intro, elapsed) end)
end

-- A row that arrives while the intro runs waits with the rest.
function Q.AdoptItems(intro, items)
    intro.items = items
    for _, row in ipairs(items) do
        if not intro.touched[row] then
            intro.touched[row] = true
            if intro.phase == "type" then pcall(row.SetAlpha, row, 0) end
        end
    end
end

-- Called after every pass over the rows with the paragraph (a FontString and the frame it lives on) and the carded rows in list
-- order. A new text, or the first one after the window opened, is typed; the same text on a later update is not. No text, nothing
-- to wait for: the rows stay as they are.
function Q.SyncIntro(intro, fs, host, items)
    if not Plain(Try(intro.band.frame.IsVisible, intro.band.frame)) then return end
    Q.RefreshBand(intro.band)
    local text = type(fs) == "table" and Plain(Try(fs.GetText, fs)) or nil
    if type(text) ~= "string" or not text:find("%S") or type(host) ~= "table" then
        if intro.running then Q.EndIntro(intro) end
        return
    end
    if intro.fresh or text ~= intro.text then
        Q.StartIntro(intro, fs, host, text, items)
    elseif intro.running then
        Q.AdoptItems(intro, items)
    end
end

-- The card behind a greeting paragraph: from the left edge of its frame to its right edge, from the top of the frame to TYPE.PAD px
-- under the last line (the stock paragraph sits 10 units in and down and runs past the bottom of its frame), a cut plate in the
-- row colours. Seated again on every pass, because the text and so the height change.
function Q.SkinTextCard(fs, host)
    if type(fs) ~= "table" or type(host) ~= "table" or type(host.CreateTexture) ~= "function" then return end
    local tc = S.textCards[fs]
    if not tc then
        local plate = Kit.Plate(host, 4, 300, 60)
        Kit.PaintPlate(plate, C.row, 1, C.hair, 1, 1)
        tc = { plate = plate, fill = plate.fill, ring = plate.ring }
        S.textCards[fs] = tc
    end
    local text = Plain(Try(fs.GetText, fs))
    local has = type(text) == "string" and text:find("%S") ~= nil
    tc.fill:SetShown(has)
    tc.ring:SetShown(has)
    if not has then return end
    local hostW, fsW = Plain(Try(host.GetWidth, host)), Plain(Try(fs.GetWidth, fs))
    local hostL, fsL = Plain(Try(host.GetLeft, host)), Plain(Try(fs.GetLeft, fs))
    local dx = 0
    if type(hostW) == "number" and type(fsW) == "number" and type(hostL) == "number" and type(fsL) == "number" then
        dx = hostW - ((fsL - hostL) + fsW)
    end
    local pad = Kit.U(host, TYPE.PAD)
    for _, t in ipairs({ tc.fill, tc.ring }) do
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", host, "TOPLEFT", 0, 0)
        t:SetPoint("BOTTOMRIGHT", fs, "BOTTOMRIGHT", dx, -pad)
    end
end

-- A greeting frame of the gossip list: its paragraph in mono, a press on it skips, the card behind it. Never a button card.
function Q.SkinGreeting(frame, fs, intro)
    if not S.greeted[frame] then
        S.greeted[frame] = true
        Mono(fs, frame, 13, C.text)
        Kit.HookScript(frame, "OnMouseDown", function() Q.Skip(intro) end)
    end
    Q.SkinTextCard(fs, frame)
end

function Q.WindowShown(intro)
    S.band, S.typed = intro.band, intro
    intro.fresh = true
    Q.LayoutBand(intro.band)
    Q.RefreshBand(intro.band)
    Q.BandStart(intro.band)
end

function Q.WindowHidden(intro)
    Q.EndIntro(intro)
    Q.BandStop(intro.band)
end

-- The kit's scroll bar on a list that scrolls: its rail (the stock bar keeps its track whether or not there is anything to scroll)
-- is shown only while the thumb is, so a list that fits has no bare rail beside it.
function Q.FollowRail(bar)
    local skins = FS.ScrollBarSkins
    local parts = type(bar) == "table" and skins and skins.Parts and skins.Parts(bar) or nil
    local track = type(bar) == "table" and bar.Track or nil
    local thumb = type(track) == "table" and track.Thumb or (type(bar) == "table" and bar.Thumb or nil)
    if not (parts and parts.rail and type(thumb) == "table") or S.rails[bar] then return end
    S.rails[bar] = true
    local function sync() parts.rail:SetShown(Plain(Try(thumb.IsShown, thumb)) == true) end
    for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(thumb, m, sync) end
    Kit.HookFunc(bar, "Update", sync)
    sync()
end

-------------------------------------------------------------------------------
-- The quest greeting list (QuestFrameGreetingPanel)
-------------------------------------------------------------------------------

local function SweepGreeting()
    S.stamp = S.stamp + 1
    local panel = _G.QuestFrameGreetingPanel
    local pool = type(panel) == "table" and panel.titleButtonPool or nil
    if type(pool) == "table" and type(pool.EnumerateActive) == "function" then
        pcall(function()
            for b in pool:EnumerateActive() do Step("greeting.row", Q.SkinRow, b, S.intros.quest) end
        end)
        -- a grown row moves the rows under it, so every card is seated again on the final rects
        Kit.Later(OnReseatRows)
    end
end

local function TopOf(o)
    local t = Plain(Try(o.GetTop, o))
    return type(t) == "number" and t or 0
end

-- The quest list's intro: the paragraph on its card, then the headers and the title buttons top to bottom (the pool answers in no
-- order, so the position says it).
local function SyncQuestGreeting()
    local intro, panel, fs = S.intros.quest, _G.QuestFrameGreetingPanel, _G.GreetingText
    if not (intro and type(panel) == "table" and type(fs) == "table") then return end
    local host = Try(fs.GetParent, fs)
    if type(host) ~= "table" then return end
    Q.SkinTextCard(fs, host)
    local found = {}
    local pool = panel.titleButtonPool
    if type(pool) == "table" and type(pool.EnumerateActive) == "function" then
        pcall(function()
            for b in pool:EnumerateActive() do
                local rec = S.rows[b]
                if rec and rec.on then found[#found + 1] = b end
            end
        end)
    end
    for _, name in ipairs({ "CurrentQuestsText", "AvailableQuestsText" }) do
        local header = _G[name]
        if type(header) == "table" and Plain(Try(header.IsShown, header)) then found[#found + 1] = header end
    end
    local list = {}
    for i, o in ipairs(found) do list[i] = { o = o, i = i, top = TopOf(o) } end
    table.sort(list, function(a, b)
        if a.top ~= b.top then return a.top > b.top end
        return a.i < b.i
    end)
    local items = {}
    for i, e in ipairs(list) do items[i] = e.o end
    Q.SyncIntro(intro, fs, host, items)
end

function Q.RefreshGreeting()
    Step("greeting.rows", SweepGreeting)
    Step("greeting.sync", SyncQuestGreeting)
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
    -- the speaker band and the typed greeting on the list page, the stock break between the groups held, the bar's bare rail gone
    local panel, scroll = _G.QuestFrameGreetingPanel, _G.QuestGreetingScrollFrame
    if type(panel) == "table" and type(scroll) == "table" then
        HeldArt.Hold(_G.QuestGreetingFrameHorizontalBreak)
        Step("quest.rail", function()
            if PanelSkins.SweepScrollBars then PanelSkins.SweepScrollBars(win) end
            Q.FollowRail(scroll.ScrollBar)
        end)
        local intro = Q.NewIntro("quest", panel, scroll, win.FriendshipStatusBar)
        if intro then
            Kit.HookScript(panel, "OnShow", function()
                Q.WindowShown(intro)
                Q.RefreshGreeting()
            end)
            Kit.HookScript(panel, "OnHide", function() Q.WindowHidden(intro) end)
            Kit.HookScript(win, "OnHide", function() Q.WindowHidden(intro) end)
            Kit.HookScript(panel, "OnMouseDown", function() Q.Skip(intro) end)
            Kit.HookScript(win, "OnMouseDown", function() Q.Skip(intro) end)
        end
    end
    Q.RefreshQuest()
    Q.RefreshGreeting()
end

-------------------------------------------------------------------------------
-- The NPC dialog (GossipFrame)
-------------------------------------------------------------------------------

local function SkinGossipRow(row)
    if type(row) ~= "table" then return end
    if type(row.GreetingText) == "table" then
        -- the greeting paragraph is a frame of its own, not a button: text and a card behind it, never a row card
        Q.SkinGreeting(row, row.GreetingText, S.intros.gossip)
        return
    end
    Q.SkinRow(row, S.intros.gossip)
end

-- After a pass over the list: the greeting paragraph and the carded rows in list order go to the intro.
-- Gossip rows are measured by Blizzard (GossipFrameShared.lua: the list's extent calculator sets up one shared button per kind
-- and asks its height, max(text height + 2, Icon height)). Our cards hide the stock Icon, so raising the Icon to ROW_PX on those
-- measuring buttons, and on the rows, makes every row ROW_PX tall (live ask 2026-11-14) without touching the list's code. The
-- measuring buttons are first met in the data the list already laid out, so the window is asked to lay out once more.
local MEASURERS = { "titleOptionButton", "activeQuestButton", "availableQuestButton" }
S.grownIcons = Weak()
S.centred = Weak()
local function GrowIcon(icon, ppu)
    if type(icon) ~= "table" or S.grownIcons[icon] or type(icon.SetHeight) ~= "function" then return false end
    S.grownIcons[icon] = true
    pcall(icon.SetHeight, icon, ROW_PX / ppu)
    return true
end

local function GrowGossip(box)
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return end
    local dp = Plain(Try(box.GetDataProvider, box))
    if type(dp) ~= "table" or type(dp.ForEach) ~= "function" then return end
    local ppu, grew = Kit.Ppu(box), false
    pcall(dp.ForEach, dp, function(data)
        if type(data) ~= "table" then return end
        for _, key in ipairs(MEASURERS) do
            local m = data[key]
            if type(m) == "table" and GrowIcon(m.Icon, ppu) then grew = true end
        end
    end)
    pcall(box.ForEachFrame, box, function(row)
        if type(row.Icon) == "table" and type(row.Resize) == "function" and GrowIcon(row.Icon, ppu) then grew = true end
    end)
    -- Never ask the window to lay out again from here: GossipFrame:Update run by this addon writes the window's own state
    -- (buttons, options, the list's data) as addon code, and the banker's gossip handing over to the bank then opened the bank
    -- tainted, which blocked every bag click (live 2026-11-14). The Setup post-hook below makes the first layout tall instead.
    return grew
end

-- Every gossip row and measuring button runs its kind's Setup before the list asks its height. A secure post-hook on the three
-- mixins (copied into each button when it is made, so it must be in place before the first window opens) raises the button to
-- ROW_PX with widget calls only: no Blizzard table is written, and the list measures the taller height on its first layout.
local function GrowAfterSetup(button)
    if type(button) ~= "table" or type(button.GetHeight) ~= "function" then return end
    local ppu = Kit.Ppu(button)
    if not ppu or ppu <= 0 then return end
    local want = ROW_PX / ppu
    local icon = button.Icon
    if type(icon) == "table" and type(icon.SetHeight) == "function" then pcall(icon.SetHeight, icon, want) end
    local ok, h = pcall(button.GetHeight, button)
    if ok and type(h) == "number" and h < want then pcall(button.SetHeight, button, want) end
end

for _, name in ipairs({ "GossipOptionButtonMixin", "GossipActiveQuestButtonMixin", "GossipAvailableQuestButtonMixin" }) do
    local mixin = _G[name]
    if type(mixin) == "table" and type(mixin.Setup) == "function" and type(hooksecurefunc) == "function" then
        pcall(hooksecurefunc, mixin, "Setup", GrowAfterSetup)
    end
end

local function SyncGossip(box)
    Step("gossip.grow", GrowGossip, box)
    -- the scroll box seats its rows after this pass; seat every card again on the final rects
    Kit.Later(OnReseatRows)
    local intro = S.intros.gossip
    if not intro then return end
    local greeting, items = nil, {}
    pcall(box.ForEachFrame, box, function(row)
        if type(row.GreetingText) == "table" then
            greeting = greeting or row
        else
            local rec = S.rows[row]
            if rec and rec.on then items[#items + 1] = row end
        end
    end)
    Q.SyncIntro(intro, greeting and greeting.GreetingText, greeting, items)
end

local function BuildGossip()
    local win = _G.GossipFrame
    if type(win) ~= "table" or S.done.gossip then return end
    local panel = win.GreetingPanel
    local box = type(panel) == "table" and panel.ScrollBox or nil
    if not box then return end
    S.done.gossip = true
    win.fsQuestSkin = true
    local intro = Q.NewIntro("gossip", panel, box, win.FriendshipStatusBar)
    local sweep = Q.WatchRows(box, SkinGossipRow, SyncGossip)
    Step("gossip.rail", function()
        if PanelSkins.SweepScrollBars then PanelSkins.SweepScrollBars(win) end
        Q.FollowRail(panel.ScrollBar)
    end)
    if intro then
        Kit.HookScript(win, "OnShow", function()
            Q.WindowShown(intro)
            if sweep then sweep() end
            Kit.Later(function() if sweep then sweep() end end)
        end)
        Kit.HookScript(win, "OnHide", function() Q.WindowHidden(intro) end)
        Kit.HookScript(win, "OnMouseDown", function() Q.Skip(intro) end)
    end
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
