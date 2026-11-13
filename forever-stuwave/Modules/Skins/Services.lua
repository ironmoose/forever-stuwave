-- Forever STUwave: Trainer, trade, profession, channel and flight map windows
-- The class and profession trainer, the trade window, the profession window's rank bar and recipe list, the chat channels window
-- with its add popup, and the flight map (the fixed node map and the zoomable map), restyled in place from the QUEST, NPC AND CRAFT
-- mockup (mockups/quest-npc-craft-2026-11-12.html, sections C to H). The window chrome, the parchment strip, the text retint, the
-- text buttons (Train, Trade, Cancel, Add, Settings), the scroll bars and the money text already wear the shared panel skin
-- (Panels.lua and PanelSkins); this file adds the parts that were still stock. One section per window below. The shared card, slot
-- and pooled row helpers are Quest.lua's (FS.QuestSkin).
--
-- Skin only, as in Commerce.lua and Quest.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard
-- frame, post-hooks and alpha holds (FS.HeldArt) only, so every click, drag, tooltip, train, trade offer, channel pick and flight
-- stays stock. Names are the real 12.1 tree (Blizzard_TrainerUI, Blizzard_UIPanels_Game TradeFrame.xml and TaxiFrame.xml,
-- Blizzard_Professions and Blizzard_ProfessionsTemplates, Blizzard_Channels, Blizzard_FlightMap); each is feature-detected and a
-- missing frame is skipped silently. The pooled rows (trainer services, recipes, roster names) are met through their ScrollBox
-- and skinned once, guarded by a weak table; the channel buttons through the channel list's own Update.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the trainer's level rail, the "short" chips, the "after" line and the train all key; the profession reagent cell
-- strips, the quantity line, the skill zone strip and the round output and reagent slot art (masked stock art); the channel tuner
-- dial, the equaliser, the voice ring, the per channel colour bars and the "in chat" preview; the trade clasp lamps on the accept
-- keys, the "accepted" and "waiting" chips and the hazard striped enchant well; the flight map cost card, legend, purse and route
-- draw animation. The stock text, tick marks, route lines and icons they replace keep working.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, Q = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.QuestSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.PaintBox and Q and Q.NewCard and Q.CardSlot
    and Q.SquareSlot and Q.WatchRows and Q.colors and PanelSkins.RequireExport(Theme.ApplyMono and Theme.StyleMoney,
    "Services.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.QuestSkin missing")) then return end

local Sv = {}
FS.ServicesSkin = Sv

local C = Q.colors

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = {
    trainer = Weak(), tradeRows = Weak(), tradeHighlights = Weak(), insets = Weak(), recipes = Weak(), channels = Weak(),
    taxi = Weak(), pins = Weak(), done = {},
}
Sv.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List = Char.List
local Region, Mono = Q.Region, Q.Mono

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("services:" .. name, ("|cffff4488Forever STUwave|r: services skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

-- Holds every texture region of `frame` (not its sub frames), except those in `keep`. Text regions are not textures and stay.
local function HoldTextures(frame, keep)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

local function Shown(region)
    return type(region) == "table" and Try(region.IsShown, region) == true
end

-- Follows a texture region's shown state (the stock selected glow of a row).
local function Watch(region, fn)
    for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(region, m, fn) end
end

-- Mono at `px`, in the colour the stock code has set now (a class colour, a quality colour), so a restyle never flattens it.
local function MonoKeep(fs, host, px)
    if type(fs) ~= "table" or type(fs.SetFont) ~= "function" then return end
    local r, g, b, a = Try(fs.GetTextColor, fs)
    r, g, b, a = Plain(r), Plain(g), Plain(b), Plain(a)
    local color = (type(r) == "number" and type(g) == "number" and type(b) == "number") and { r, g, b, a or 1 } or C.text
    Kit.RestyleLabel(fs, host, px, color)
end

-- A ring box on the rect of a held stock frame, drawn on `host` over it.
local function RingOver(host, ref, fill, edge)
    if type(host) ~= "table" or type(ref) ~= "table" or type(host.CreateTexture) ~= "function" then return nil end
    local box = Char.Box(host, "OVERLAY", ref)
    Char.PaintBox(box, fill or C.ink, 1, edge or C.violet, 1, 1)
    return box
end

-- The money text of a pooled row (a trainer price): mono, the colour the stock code gives it (red when short).
local function MoneyTexts(money, host, px)
    if type(money) ~= "table" then return end
    for _, coin in ipairs(List(money, "GetChildren")) do
        local fs = Try(coin.GetFontString, coin)
        if type(fs) ~= "table" then
            for _, region in ipairs(List(coin, "GetRegions")) do
                if Try(region.GetObjectType, region) == "FontString" then fs = region break end
            end
        end
        MonoKeep(fs, host, px)
    end
end

-------------------------------------------------------------------------------
-- Shared: the card of a pooled row, with the pink pick and the lock-on brackets
-------------------------------------------------------------------------------

-- A card on the row's rect, `padY` UI units out of it (negative pulls it in, to leave a gap between flush rows). Rows that can be
-- picked also get the four lock-on brackets of the quest reward pick.
local function NewRow(row, padY, brackets)
    local rec = Q.NewCard(row, 0, padY)
    rec.padY = padY
    if brackets then
        rec.reticle = Kit.Reticle(row, "OVERLAY", 7)
        Kit.ShowReticle(rec.reticle, false)
    end
    return rec
end

local function PaintRow(rec, row, selected)
    local hover = rec.state and rec.state.hover
    local edge = (selected and C.pink) or (hover and C.cyan) or C.dim
    Char.PaintBox(rec.box, selected and C.band or C.row, 1, edge, 1, selected and 2 or 1)
    local ret = rec.reticle
    if ret then
        Kit.ShowReticle(ret, selected and true or false)
        if selected then
            Kit.PaintReticle(ret, C.pink, 1)
            local w, h = Kit.SizePx(row)
            if w then
                local inset = math.floor(-(rec.padY or 0) * Kit.Ppu(row) + 0.5)
                Kit.SeatReticle(ret, 0, inset, w, h - 2 * inset, 0, 8)
            end
        end
    end
end

local function PaintHeader(rec)
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, C.band, 1, hover and C.cyan or C.violet, 1, 1)
end

-------------------------------------------------------------------------------
-- The trainers (ClassTrainerFrame)
-------------------------------------------------------------------------------

local function PaintTrainer(row)
    local rec = S.trainer[row]
    if not rec then return end
    if rec.header then PaintHeader(rec) else PaintRow(rec, row, Shown(row.selectedTex)) end
end

-- One service row, or the step button of a profession trainer: the stock plate, highlight, selected glow and disabled wash held,
-- a card behind it, a slot on its icon, the texts in mono. The pick is the stock selected glow's state, so it follows the stock
-- selection (the click and the tooltip are stock). A category row is a band.
local function SkinTrainerRow(row)
    if type(row) ~= "table" or S.trainer[row] or type(row.CreateTexture) ~= "function" then return end
    HeldArt.HoldNormal(row)
    HeldArt.Hold(Try(row.GetHighlightTexture, row))
    if type(row.name) ~= "table" then
        local rec = NewRow(row, 0, false)
        rec.header = true
        S.trainer[row] = rec
        Mono(Try(row.GetFontString, row) or Region(row, "Text") or Region(row, "Label"), row, 12, C.cyan)
        rec.state = Kit.Track(row, PaintTrainer)
        PaintTrainer(row)
        return
    end
    HeldArt.Hold(row.selectedTex)
    HeldArt.Hold(row.disabledBG)
    S.trainer[row] = NewRow(row, -2, true)
    if type(row.icon) == "table" then Q.CardSlot(row, row.icon) end
    Mono(row.name, row, 13, C.text)
    Mono(row.subText, row, 11, C.muted)
    MoneyTexts(row.money, row, 12)
    S.trainer[row].state = Kit.Track(row, PaintTrainer)
    if type(row.selectedTex) == "table" then Watch(row.selectedTex, function() PaintTrainer(row) end) end
    PaintTrainer(row)
end

local function SkinTrainerBar()
    local bar = _G.ClassTrainerStatusBar
    if type(bar) ~= "table" or S.trainerBar or type(bar.CreateTexture) ~= "function" then return end
    S.trainerBar = RingOver(bar, bar, C.ink, C.violet)
    Mono(bar.rankText or _G.ClassTrainerStatusBarSkillRank, bar, 12, C.text)
end

local function RefreshTrainer()
    local win = _G.ClassTrainerFrame
    if type(win) ~= "table" then return end
    Q.WatchRows(win.ScrollBox, SkinTrainerRow)
    Step("trainer.step", SkinTrainerRow, win.skillStepButton or _G.ClassTrainerFrameSkillStepButton)
    Step("trainer.bar", SkinTrainerBar)
end

local function BuildTrainer()
    local win = _G.ClassTrainerFrame
    if type(win) ~= "table" or S.done.trainer then return end
    S.done.trainer = true
    win.fsServicesSkin = true
    Kit.HookScript(win, "OnShow", function() Kit.Later(RefreshTrainer) end)
    RefreshTrainer()
end

-------------------------------------------------------------------------------
-- The trade window (TradeFrame)
-------------------------------------------------------------------------------

local TRADE_ROWS = 7
local TRADE_PAD = 2        -- UI units out of the row, so the slot sits 2 in from the card on three sides
local TRADE_TRIM = 7       -- the stock row is wider than its column, so the card's right edge comes in by this much
local TRADE_INSETS = { "TradePlayerItemsInset", "TradeRecipientItemsInset", "TradePlayerEnchantInset", "TradeRecipientEnchantInset",
    "TradePlayerInputMoneyInset", "TradeRecipientMoneyInset" }
-- The half of the window that has accepted lights its column: ours cyan, theirs amber.
local TRADE_HIGHLIGHTS = {
    { "TradeHighlightPlayer", "TradePlayerItemsInset", "cyan" }, { "TradeHighlightRecipient", "TradeRecipientItemsInset", "amber" },
    { "TradeHighlightPlayerEnchant", "TradePlayerEnchantInset", "cyan" }, { "TradeHighlightRecipientEnchant", "TradeRecipientEnchantInset", "amber" },
}

local function PaintTradeRow(row)
    local rec = S.tradeRows[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, C.row, 1, hover and C.cyan or C.dim, 1, 1)
end

-- One side's row: the stock slot plate and name frame held (the seventh row's enchant picture too), a card behind it, the item
-- button a square slot of ours, the name in mono in the colour the stock code gives the item.
local function SkinTradeRow(row, seventh)
    if type(row) ~= "table" or S.tradeRows[row] or type(row.CreateTexture) ~= "function" then return end
    local name = Try(row.GetName, row)
    if seventh then
        HoldTextures(row)
    else
        HeldArt.Hold(row.SlotTexture)
        if type(name) == "string" then HeldArt.Hold(_G[name .. "NameFrame"]) end
    end
    local rec = Q.NewCard(row, TRADE_PAD, TRADE_PAD)
    rec.ref:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", -TRADE_TRIM, -TRADE_PAD)
    S.tradeRows[row] = rec
    local button = type(name) == "string" and _G[name .. "ItemButton"] or nil
    if type(button) == "table" then
        Q.SquareSlot(button)
        S.tradeRows[row].state = Kit.Track(button, function() PaintTradeRow(row) end)
    end
    MonoKeep(type(name) == "string" and _G[name .. "Name"] or Region(row, "Name"), row, 11)
    PaintTradeRow(row)
end

local function SkinTradeHighlight(spec)
    local frame, ref = _G[spec[1]], _G[spec[2]]
    if type(frame) ~= "table" or S.tradeHighlights[frame] or type(frame.CreateTexture) ~= "function" then return end
    HoldTextures(frame)
    local color = C[spec[3]]
    local box = Char.Box(frame, "OVERLAY", type(ref) == "table" and ref or frame)
    Char.PaintBox(box, color, 0.06, color, 1, 2)
    S.tradeHighlights[frame] = box
end

local function RefreshTrade()
    local win = _G.TradeFrame
    if type(win) ~= "table" then return end
    for _, side in ipairs({ "Player", "Recipient" }) do
        for i = 1, TRADE_ROWS do
            Step("trade.row", SkinTradeRow, _G["Trade" .. side .. "Item" .. i], i == TRADE_ROWS)
        end
    end
    -- the six inset wells are art-only frames: held, and a ring box of ours over the same rect
    for _, n in ipairs(TRADE_INSETS) do
        local inset = _G[n]
        if type(inset) == "table" and not S.insets[inset] then
            Kit.HoldFrame(inset)
            S.insets[inset] = RingOver(win, inset, C.ink, C.violet) or true
        end
    end
    Kit.HoldFrame(_G.TradeRecipientMoneyBg)
    for _, spec in ipairs(TRADE_HIGHLIGHTS) do Step("trade.highlight", SkinTradeHighlight, spec) end
    local com = FS.CommerceSkin
    if com and com.SkinMoneyInput then Step("trade.money", com.SkinMoneyInput, _G.TradePlayerInputMoneyFrame) end
    Theme.StyleMoney(_G.TradeRecipientMoneyFrame)
    if not S.done.tradeTexts then
        S.done.tradeTexts = true
        Mono(_G.TradeFramePlayerNameText, win, 12, C.text)
        Mono(_G.TradeFrameRecipientNameText, win, 12, C.text)
        Mono(_G.TradeFramePlayerEnchantText, win, 11, C.muted)
        Mono(_G.TradeFrameRecipientEnchantText, win, 11, C.muted)
    end
end

local function BuildTrade()
    local win = _G.TradeFrame
    if type(win) ~= "table" or S.done.trade then return end
    S.done.trade = true
    win.fsServicesSkin = true
    Kit.HookScript(win, "OnShow", function() Kit.Later(RefreshTrade) end)
    RefreshTrade()
end

-------------------------------------------------------------------------------
-- The profession window (ProfessionsFrame.CraftingPage)
-------------------------------------------------------------------------------

-- The skill bar's stock frame, background and flare held (the masked fill stays: it is the value), a track box of ours round the
-- rect the fill can reach, the rank text in mono.
local function SkinRankBar(page)
    local bar = page.RankBar
    if type(bar) ~= "table" or S.rankBar or type(bar.CreateTexture) ~= "function" then return end
    for _, key in ipairs({ "Background", "Border", "Flare" }) do HeldArt.Hold(bar[key]) end
    local ref = bar:CreateTexture(nil, "BACKGROUND", nil, -8)
    ref:SetPoint("TOPLEFT", bar, "TOPLEFT", 4, -2)
    ref:SetPoint("BOTTOMRIGHT", bar, "TOPLEFT", 447, -22)
    S.rankBar = RingOver(bar, ref, C.ink, C.violet)
    local rank = Region(bar, "Rank")
    Mono(rank and rank.Text, bar, 12, C.text)
end

local function PaintRecipe(row)
    local rec = S.recipes[row]
    if not rec then return end
    if rec.header then PaintHeader(rec) else PaintRow(rec, row, Shown(row.SelectedOverlay)) end
end

-- A category row is a band, a recipe row a card with the stock selection as its pick. The label font is Panels' (it re-asserts it on
-- every font swap), the plus and minus, the skill up marks and the count are stock.
local function SkinRecipeRow(row)
    if type(row) ~= "table" or S.recipes[row] or type(row.CreateTexture) ~= "function" then return end
    if row.CollapseIcon then
        for _, key in ipairs({ "LeftPiece", "RightPiece", "CenterPiece" }) do HeldArt.Hold(row[key]) end
        local rec = NewRow(row, -1, false)
        rec.header = true
        S.recipes[row] = rec
        rec.state = Kit.Track(row, PaintRecipe)
        PaintRecipe(row)
    elseif row.Count then
        HeldArt.Hold(row.SelectedOverlay)
        HeldArt.Hold(row.HighlightOverlay)
        S.recipes[row] = NewRow(row, -1, false)
        S.recipes[row].state = Kit.Track(row, PaintRecipe)
        if type(row.SelectedOverlay) == "table" then Watch(row.SelectedOverlay, function() PaintRecipe(row) end) end
        PaintRecipe(row)
    end
end

local function RefreshProfessions()
    local win = _G.ProfessionsFrame
    local page = type(win) == "table" and win.CraftingPage or nil
    if type(page) ~= "table" then return end
    Step("prof.rank", SkinRankBar, page)
    local list = page.RecipeList
    Q.WatchRows(type(list) == "table" and list.ScrollBox or nil, SkinRecipeRow)
end

local function BuildProfessions()
    local win = _G.ProfessionsFrame
    if type(win) ~= "table" or type(win.CraftingPage) ~= "table" or S.done.prof then return end
    S.done.prof = true
    win.fsServicesSkin = true
    Kit.HookScript(win, "OnShow", function() Kit.Later(RefreshProfessions) end)
    RefreshProfessions()
end

-------------------------------------------------------------------------------
-- The chat channels window (ChannelFrame, CreateChannelPopup)
-------------------------------------------------------------------------------

local function ChannelList()
    local win = _G.ChannelFrame
    return type(win) == "table" and type(win.ChannelList) == "table" and win.ChannelList or nil
end

local function PaintChannel(button)
    local rec = S.channels[button]
    if not rec then return end
    if rec.header then
        PaintHeader(rec)
        return
    end
    local list = ChannelList()
    local picked = list and Plain(Try(list.GetSelectedChannelButton, list))
    PaintRow(rec, button, picked == button)
end

local function PaintAllChannels()
    for button in pairs(S.channels) do PaintChannel(button) end
end

-- One channel button of the list (a header, a text, voice or community channel): the stock row and highlight held (the plus and
-- minus of a header and the speaker stay), a card, the name in mono. The selected channel is the one the list says is selected.
local function SkinChannelButton(button)
    if type(button) ~= "table" or S.channels[button] or type(button.CreateTexture) ~= "function" then return end
    local header = Try(button.IsHeader, button) == true
    HeldArt.HoldButton(button, header and type(button.Collapsed) == "table" and { [button.Collapsed] = true } or nil)
    local rec = NewRow(button, -1, false)
    rec.header = header
    S.channels[button] = rec
    Mono(Region(button, "Text") or Try(button.GetFontString, button), button, header and 11 or 12, header and C.cyan or C.text)
    rec.state = Kit.Track(button, PaintChannel)
    PaintChannel(button)
end

local function SweepChannelButtons()
    local list = ChannelList()
    if not list then return end
    for _, button in ipairs(List(list.Child, "GetChildren")) do Step("channel.button", SkinChannelButton, button) end
    PaintAllChannels()
end

local function PaintRoster(row)
    local rec = S.channels[row]
    if rec then PaintRow(rec, row, false) end
end

-- A roster name: the stock row and highlight held (the rank crown and the mute keys stay), a card, the name in mono in its class colour.
local function SkinRosterRow(row)
    if type(row) ~= "table" or S.channels[row] or type(row.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(row, type(row.Rank) == "table" and { [row.Rank] = true } or nil)
    S.channels[row] = NewRow(row, -1, false)
    MonoKeep(row.Name, row, 12)
    S.channels[row].state = Kit.Track(row, PaintRoster)
    PaintRoster(row)
end

local function RefreshChannels()
    local win = _G.ChannelFrame
    if type(win) ~= "table" then return end
    SweepChannelButtons()
    local roster = win.ChannelRoster
    Q.WatchRows(type(roster) == "table" and roster.ScrollBox or nil, SkinRosterRow)
    if not S.done.channelTexts then
        S.done.channelTexts = true
        if type(roster) == "table" then
            Mono(roster.ChannelName, win, 13, C.text)
            Mono(roster.ChannelCount, win, 11, C.muted)
        end
    end
end

local function BuildChannels()
    local win = _G.ChannelFrame
    if type(win) ~= "table" or S.done.channels then return end
    S.done.channels = true
    win.fsServicesSkin = true
    for _, key in ipairs({ "LeftInset", "RightInset" }) do
        local inset = win[key]
        if type(inset) == "table" then
            Kit.HoldFrame(inset)
            S.insets[inset] = RingOver(win, inset, C.ink, C.violet) or true
        end
    end
    local list = ChannelList()
    if list then
        Kit.HookFunc(list, "Update", SweepChannelButtons)
        Kit.HookFunc(list, "SetSelectedChannel", PaintAllChannels)
    end
    Kit.HookScript(win, "OnShow", function() Kit.Later(RefreshChannels) end)
    RefreshChannels()
end

local function BuildChannelPopup()
    local pop = _G.CreateChannelPopup
    if type(pop) ~= "table" or S.done.popup then return end
    S.done.popup = true
    pop.fsServicesSkin = true
    Kit.HoldFrame(pop.BG)
    local header = pop.Header
    if type(header) == "table" then
        HoldTextures(header)
        Mono(header.Text, pop, 13, C.text)
    end
    local com = FS.CommerceSkin
    if com and com.Dialog then Step("popup.dialog", com.Dialog, pop, C.cyan) end
    for _, key in ipairs({ "Name", "Password" }) do
        local box = pop[key]
        if type(box) == "table" then Mono(box.Label, pop, 12, C.muted) end
    end
    PanelSkins.SweepOnShow(pop)
end

-------------------------------------------------------------------------------
-- The flight map (TaxiFrame node buttons, FlightMapFrame pins)
-------------------------------------------------------------------------------

-- A node is a diamond of 1 px rows centred on the stock button or pin: pink where you are, cyan where you can fly, dim where you
-- cannot. Built once per button; the stock icon and highlight are held under it.
local DIAMOND_ROWS = 8
local DIAMOND_RADIUS = { current = 8, reachable = 6, unreachable = 4 }

local function NewDiamond(host)
    local rows = {}
    for i = -DIAMOND_ROWS, DIAMOND_ROWS do
        local t = Kit.Rect(host, 0, 0, 1, 1, C.cyan, 1, "OVERLAY", 7)
        t.fsRow = i
        rows[#rows + 1] = t
    end
    return rows
end

local function PaintDiamond(rows, host, kind, hover)
    local radius = DIAMOND_RADIUS[kind] or DIAMOND_RADIUS.unreachable
    local color = hover and C.text or (kind == "current" and C.pink) or (kind == "reachable" and C.cyan) or C.dim
    for _, t in ipairs(rows) do
        t:SetColorTexture(color[1], color[2], color[3], 1)
        local d = math.abs(t.fsRow)
        if d > radius then
            t:Hide()
        else
            local half = radius - d
            Kit.Place(t, host, -half - 1, t.fsRow, 2 * half + 2, 1, "TOPLEFT", "CENTER")
            t:Show()
        end
    end
end

local function TaxiKind(button)
    local id = Plain(Try(button.GetID, button))
    local kind = type(id) == "number" and Plain(Try(_G.TaxiNodeGetType, id)) or nil
    if kind == "CURRENT" then return "current" end
    if kind == "REACHABLE" then return "reachable" end
    return "unreachable"
end

local function PaintTaxi(button)
    local rec = S.taxi[button]
    if rec then PaintDiamond(rec.glyph, button, TaxiKind(button), rec.state and rec.state.hover) end
end

local function SkinTaxiButton(button)
    if type(button) ~= "table" or S.taxi[button] or type(button.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(button)
    local rec = { glyph = NewDiamond(button) }
    S.taxi[button] = rec
    rec.state = Kit.Track(button, PaintTaxi)
    Kit.HookFunc(button, "SetNormalTexture", function() PaintTaxi(button) end)
    PaintTaxi(button)
end

local function SweepTaxi()
    local count = type(_G.NumTaxiNodes) == "function" and Plain(Try(_G.NumTaxiNodes)) or nil
    if type(count) ~= "number" then count = 0 end
    for i = 1, count do Step("taxi.button", SkinTaxiButton, _G["TaxiButton" .. i]) end
    for button in pairs(S.taxi) do PaintTaxi(button) end
end

local function BuildTaxi()
    local win = _G.TaxiFrame
    if type(win) ~= "table" or S.done.taxi then return end
    S.done.taxi = true
    win.fsServicesSkin = true
    if type(win.InsetBg) == "table" and type(win.CreateTexture) == "function" then
        S.taxiRing = Char.Box(win, "OVERLAY", win.InsetBg)
        Char.PaintBox(S.taxiRing, C.ink, 0, C.violet, 1, 1)
    end
    -- the stock OnShow makes the buttons and sets their textures; ours runs after it
    Kit.HookScript(win, "OnShow", SweepTaxi)
    SweepTaxi()
end

local function PinKind(pin)
    local state = Plain(Try(pin.GetTaxiNodeState, pin))
    local enum = _G.Enum and _G.Enum.FlightPathState
    if type(enum) == "table" then
        if state == enum.Current then return "current" end
        if state == enum.Reachable then return "reachable" end
    end
    return "unreachable"
end

local function PaintPin(pin)
    local rec = S.pins[pin]
    if rec then PaintDiamond(rec.glyph, pin, PinKind(pin), rec.state and rec.state.hover) end
end

-- A pin with its own art (a map layer transition, a themed flight master) keeps it.
local function SkinPin(pin)
    if type(pin) ~= "table" or S.pins[pin] or type(pin.CreateTexture) ~= "function" then return end
    if pin.isMapLayerTransition or pin.textureKit then return end
    HeldArt.Hold(pin.Icon)
    HeldArt.Hold(pin.IconHighlight)
    local rec = { glyph = NewDiamond(pin) }
    S.pins[pin] = rec
    rec.state = Kit.Track(pin, PaintPin)
    Kit.HookFunc(pin, "SetFlightPathStyle", function() PaintPin(pin) end)
    PaintPin(pin)
end

local function SweepPins()
    local map = _G.FlightMapFrame
    if type(map) ~= "table" or type(map.EnumeratePinsByTemplate) ~= "function" then return end
    pcall(function()
        for pin in map:EnumeratePinsByTemplate("FlightMap_FlightPointPinTemplate") do Step("pin", SkinPin, pin) end
    end)
end

local function BuildFlightMap()
    local win = _G.FlightMapFrame
    if type(win) ~= "table" or S.done.flightmap then return end
    S.done.flightmap = true
    win.fsServicesSkin = true
    local border = win.BorderFrame
    if type(border) == "table" then
        Kit.HoldFrame(border.NineSlice)
        HeldArt.Hold(border.TopBorder)
        if type(border.CreateTexture) == "function" then
            S.mapRing = Char.Box(border, "OVERLAY", border)
            Char.PaintBox(S.mapRing, C.ink, 0, C.violet, 1, 1)
        end
    end
    -- a pin is skinned the moment the map acquires it, before it is drawn
    Kit.HookFunc(win, "AcquirePin", SweepPins)
    Kit.HookScript(win, "OnShow", SweepPins)
    SweepPins()
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("trainer", BuildTrainer)
    Step("trade", BuildTrade)
    Step("professions", BuildProfessions)
    Step("channels", BuildChannels)
    Step("popup", BuildChannelPopup)
    Step("taxi", BuildTaxi)
    Step("flightmap", BuildFlightMap)
end

PanelSkins.RegisterInspect("Services", { { name = "ClassTrainerFrame", guard = "fsServicesSkin" }, { name = "TradeFrame", guard = "fsServicesSkin" },
    { name = "ProfessionsFrame", guard = "fsServicesSkin" }, { name = "ChannelFrame", guard = "fsServicesSkin" },
    { name = "CreateChannelPopup", guard = "fsServicesSkin" }, { name = "TaxiFrame", guard = "fsServicesSkin" },
    { name = "FlightMapFrame", guard = "fsServicesSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
