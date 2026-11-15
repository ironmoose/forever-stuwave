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
-- The profession window (ProfessionsFrame.CraftingPage) also swaps its stock art for art of ours, all of it alpha held: the category
-- bands hold every stock piece and fold with a chevron of cells, the skill up arrows are a chip of one to three chevrons in the
-- difficulty colour (orange, yellow, green), the rank bar draws its own cyan fill from the stock mask's width, the detail pane's
-- stock frame is held and ringed, and Create and Create All wear the text button. All of it follows the stock state by post-hooks
-- (SetAtlas, SetVertexColor, SetWidth), never by calling a stock Update, Init or Refresh.
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
    taxi = Weak(), pins = Weak(), routes = Weak(), skillUps = Weak(), panes = Weak(), bars = Weak(), labels = Weak(), done = {},
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

-- The craft mockup's difficulty ramp (DIF): orange a skill up for certain, yellow likely, green unlikely. The stock arrow says it by
-- its atlas (Professions-Icon-Skill-High, -Medium, -Low: three, two and one chevron), so the chip says it the same way.
local TIERS = {
    High = { n = 3, color = { 1, 0.541, 0.239 } },
    Medium = { n = 2, color = { 1, 0.824, 0.247 } },
    Low = { n = 1, color = { 0.239, 0.863, 0.518 } },
}
local TIER_OTHER = { n = 1, color = C.cyan }   -- an arrow this build names differently is still marked, with one chevron

local function AtlasOf(region)
    if type(region) ~= "table" then return nil end
    local atlas = Plain(Try(region.GetAtlas, region))
    return type(atlas) == "string" and atlas or nil
end

local function TierOf(atlas)
    return type(atlas) == "string" and TIERS[atlas:match("Skill%-(%a+)$")] or TIER_OTHER
end

-- A chevron of 2 px cells, five of them (one per column of an up or down chevron, one per row of a right one), as the page keys of
-- Quest.lua draw theirs. The numbers are the cells' (left, top) in physical pixels inside the chevron's own w x h box.
local CELL = 2
local CHEV = {
    up = { w = 10, h = 6, { 0, 4 }, { 2, 2 }, { 4, 0 }, { 6, 2 }, { 8, 4 } },
    down = { w = 10, h = 6, { 0, 0 }, { 2, 2 }, { 4, 4 }, { 6, 2 }, { 8, 0 } },
    right = { w = 6, h = 10, { 0, 0 }, { 2, 2 }, { 4, 4 }, { 2, 6 }, { 0, 8 } },
}

local function NewChevron(host)
    local cells = {}
    for i = 1, 5 do cells[i] = Kit.Rect(host, 0, 0, CELL, CELL, C.cyan, 1, "OVERLAY", 7) end
    return cells
end

-- Seats a chevron with its centre cx px right and cy px down of `point` of `ref`. `host` rules the pixel scale.
local function SeatChevron(cells, dir, ref, point, cx, cy, host)
    local shape = CHEV[dir]
    for i, cell in ipairs(cells) do
        local at = shape[i]
        Kit.Place(cell, ref, cx + at[1] + CELL / 2 - shape.w / 2, cy + at[2] + CELL / 2 - shape.h / 2, CELL, CELL, "CENTER", point, host)
    end
end

local function PaintCells(cells, color, on)
    for _, cell in ipairs(cells) do
        cell:SetColorTexture(color[1], color[2], color[3], 1)
        cell:SetShown(on)
    end
end

-- The skill up mark: the stock arrow (a texture, re-atlased by every row init) held, a chip of ours in its place on the right edge of
-- the mark frame, so the stock count (a number left of the arrow) keeps its place. It shows and hides with that frame, and takes
-- its tier from the atlas the stock code last gave the arrow.
local CHIP_W, CHIP_PAD, CHIP_PITCH = 16, 2, 4

local function BuildChip(ups)
    local chip = { cells = {} }
    chip.ref = ups:CreateTexture(nil, "BACKGROUND", nil, -8)
    Kit.Place(chip.ref, ups, -1, 0, CHIP_W, 10, "RIGHT", "RIGHT")
    chip.box = Char.Box(ups, "OVERLAY", chip.ref)
    for i = 1, 3 do chip.cells[i] = NewChevron(ups) end
    return chip
end

local function PaintChip(ups, chip, atlas)
    local tier = TierOf(atlas)
    local color = tier.color
    Kit.Move(chip.ref, -1, 0, CHIP_W, CHEV.up.h + CHIP_PITCH * (tier.n - 1) + 2 * CHIP_PAD)
    Char.PaintBox(chip.box, Kit.Mix(C.ink, color, 0.16), 1, color, 1, 1)
    for i = 1, 3 do
        PaintCells(chip.cells[i], color, i <= tier.n)
        if i <= tier.n then SeatChevron(chip.cells[i], "up", chip.ref, "CENTER", 0, CHIP_PITCH * (i - 1) - CHIP_PITCH / 2 * (tier.n - 1), ups) end
    end
end

local function SkinSkillUps(row)
    local ups = Region(row, "SkillUps")
    if not ups or S.skillUps[ups] or type(ups.CreateTexture) ~= "function" then return end
    local icon = Region(ups, "Icon")
    HeldArt.Hold(icon)
    local chip = BuildChip(ups)
    S.skillUps[ups] = chip
    PaintChip(ups, chip, AtlasOf(icon))
    Kit.HookFunc(icon, "SetAtlas", function(_, atlas) PaintChip(ups, chip, atlas) end)
    Mono(ups.Text, ups, 14, { 1, 1, 1, 1 })
end

-- The fold mark of a category band: a down chevron (cyan) while it is open, a right one (violet) while it is folded, both lit on
-- hover. The stock icon (a plus or a minus, re-atlased on every click) is held; its atlas says which state the band is in.
local GLYPH_CX, GLYPH_CY = -17, -2

local function BuildGlyph(row)
    local glyph = { down = NewChevron(row), right = NewChevron(row) }
    SeatChevron(glyph.down, "down", row, "RIGHT", GLYPH_CX, GLYPH_CY, row)
    SeatChevron(glyph.right, "right", row, "RIGHT", GLYPH_CX, GLYPH_CY, row)
    return glyph
end

local function PaintGlyph(rec)
    local glyph = rec.glyph
    if not glyph then return end
    local folded = type(rec.atlas) == "string" and rec.atlas:find("expand", 1, true) ~= nil
    local color = (rec.state and rec.state.hover and C.text) or (folded and C.violet or C.cyan)
    PaintCells(glyph.down, color, not folded)
    PaintCells(glyph.right, color, folded)
end

-- A band's label. The stock code writes its colour with SetVertexColor on every init (gold, or grey for a category not learned), and
-- its font object on every hover; the text colour is ours, the gold vertex goes to white and a grey one stays a muted tone.
local MUTED_VERTEX = { 0.62, 0.58, 0.77, 1 }

local function PinHeaderLabel(label)
    if type(label) ~= "table" or type(label.SetVertexColor) ~= "function" or S.labels[label] then return end
    S.labels[label] = true
    local text = C.text
    local function recolor(self) pcall(self.SetTextColor, self, text[1], text[2], text[3], 1) end
    recolor(label)
    local busy = false
    local function retint(self, r, g, b)
        r, g, b = Plain(r), Plain(g), Plain(b)
        if busy or type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return end
        busy = true
        local hi, lo = math.max(r, g, b), math.min(r, g, b)
        local tint = (hi - lo < 0.1 and hi < 0.75) and MUTED_VERTEX or { 1, 1, 1, 1 }
        pcall(self.SetVertexColor, self, tint[1], tint[2], tint[3], tint[4])
        busy = false
    end
    Kit.HookFunc(label, "SetVertexColor", retint)
    Kit.HookFunc(label, "SetFontObject", recolor)
    local r, g, b = Try(label.GetVertexColor, label)
    if type(Plain(r)) == "number" then retint(label, r, g, b) else pcall(label.SetVertexColor, label, 1, 1, 1, 1) end
end

-- The little progress bar a category band carries (only the expansion bands have one): its gold frame held, a violet ring of ours.
local function SkinCategoryBar(bar)
    if type(bar) ~= "table" or S.bars[bar] or type(bar.CreateTexture) ~= "function" then return end
    for _, key in ipairs({ "BorderLeft", "BorderMid", "BorderRight" }) do HeldArt.Hold(bar[key]) end
    S.bars[bar] = RingOver(bar, bar, C.ink, C.violet) or true
    Mono(bar.Rank, bar, 10, C.text)
end

-- The skill bar: the stock frame, background, flare and fill held, a track box of ours round the rect the fill can reach, and a cyan
-- fill of ours as wide as the stock mask is. The stock code sizes the masked fill by setting the width of its Mask (at once when a
-- profession is picked, over half a second when a skill goes up), so a post-hook on the mask's SetWidth draws every step; the rank
-- text is in mono.
local RANK_TRACK_W = 443

local function PaintRankFill(bar)
    local rec = S.rankFill
    if not rec or rec.bar ~= bar then return end
    local maskW = Plain(Try(bar.Mask and bar.Mask.GetWidth, bar.Mask))
    local fullW = Plain(Try(bar.Fill and bar.Fill.GetWidth, bar.Fill))
    if type(maskW) ~= "number" or type(fullW) ~= "number" or fullW <= 0 then return end
    local ratio = math.max(0, math.min(1, maskW / fullW))
    local u = Kit.U(bar, 1)
    local span = Plain(Try(rec.ref.GetWidth, rec.ref))
    if type(span) ~= "number" or span <= 0 then span = RANK_TRACK_W end
    local fill = rec.fill
    fill:ClearAllPoints()
    fill:SetPoint("TOPLEFT", rec.ref, "TOPLEFT", u, -u)
    fill:SetPoint("BOTTOMLEFT", rec.ref, "BOTTOMLEFT", u, u)
    local width = (span - 2 * u) * ratio
    fill:SetWidth(math.max(width, 0.01))
    fill:SetShown(width >= u)
end

local function SkinRankBar(page)
    local bar = page.RankBar
    if type(bar) ~= "table" or S.rankBar or type(bar.CreateTexture) ~= "function" then return end
    for _, key in ipairs({ "Background", "Border", "Flare", "Fill" }) do HeldArt.Hold(bar[key]) end
    local ref = bar:CreateTexture(nil, "BACKGROUND", nil, -8)
    ref:SetPoint("TOPLEFT", bar, "TOPLEFT", 4, -2)
    ref:SetPoint("BOTTOMRIGHT", bar, "TOPLEFT", 447, -22)
    S.rankBar = RingOver(bar, ref, C.ink, C.violet)
    local fill = bar:CreateTexture(nil, "ARTWORK", nil, 3)
    fill:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.6)
    Kit.Snap(fill)
    S.rankFill = { bar = bar, ref = ref, fill = fill }
    Kit.HookFunc(bar.Mask, "SetWidth", function() PaintRankFill(bar) end)
    Kit.HookScript(bar, "OnShow", function() PaintRankFill(bar) end)
    PaintRankFill(bar)
    local rank = Region(bar, "Rank")
    Mono(rank and rank.Text, bar, 12, C.text)
end

-- The two panes under the skill bar. The stock frame of each (a nine slice the stock code shows again on every recipe) is held at
-- alpha, which survives a Show; the detail pane takes a ring of ours in its place.
local function SkinCraftPanes(page)
    local list, form = page.RecipeList, page.SchematicForm
    if type(list) == "table" then
        Kit.HoldFrame(list.BackgroundNineSlice)
        HeldArt.Hold(list.Background)
    end
    if type(form) ~= "table" or S.panes[form] or type(form.CreateTexture) ~= "function" then return end
    Kit.HoldFrame(form.NineSlice)
    HeldArt.Hold(form.Background)
    HeldArt.Hold(form.MinimalBackground)
    local ring = Char.Box(form, "OVERLAY", form)
    Char.PaintBox(ring, C.ink, 0.45, C.violet, 1, 1)
    S.panes[form] = ring
end

-- Create and Create All (and View Crafters for a guild craft list) are red three slice keys whose label is empty until a recipe is
-- picked, which is why the sweep that finds text buttons by their label misses them. Create is the cyan key, the others violet.
local CRAFT_KEYS = { { "CreateButton", "cyan" }, { "CreateAllButton", "violet" }, { "ViewGuildCraftersButton", "violet" } }

local function SkinCraftKeys(page)
    local skins = FS.ButtonSkins
    if not (skins and skins.SkinTextButton) then return end
    for _, spec in ipairs(CRAFT_KEYS) do
        local button = page[spec[1]]
        if type(button) == "table" then skins.SkinTextButton(button, { accent = spec[2] }) end
    end
end

local function PaintRecipe(row)
    local rec = S.recipes[row]
    if not rec then return end
    if rec.header then
        PaintHeader(rec)
        PaintGlyph(rec)
    else
        PaintRow(rec, row, Shown(row.SelectedOverlay))
    end
end

-- A category row is a band, a recipe row a card with the stock selection as its pick. Every stock texture of either is held (read
-- before our own are made, so ours stay): the three slices and the plus or minus of a band, the selected and hover glow of a recipe.
-- The label font is Panels' (it re-asserts it on every font swap), the count is stock.
local function SkinRecipeRow(row)
    if type(row) ~= "table" or S.recipes[row] or type(row.CreateTexture) ~= "function" then return end
    if row.CollapseIcon then
        HoldTextures(row)
        local rec = NewRow(row, -1, false)
        rec.header = true
        rec.atlas = AtlasOf(row.CollapseIcon)
        rec.glyph = BuildGlyph(row)
        S.recipes[row] = rec
        rec.state = Kit.Track(row, PaintRecipe)
        Kit.HookFunc(row.CollapseIcon, "SetAtlas", function(_, atlas) rec.atlas = Plain(atlas); PaintRecipe(row) end)
        PinHeaderLabel(row.Label)
        Step("prof.bar", SkinCategoryBar, row.RankBar)
        PaintRecipe(row)
    elseif row.Count then
        HoldTextures(row)
        S.recipes[row] = NewRow(row, -1, false)
        S.recipes[row].state = Kit.Track(row, PaintRecipe)
        if type(row.SelectedOverlay) == "table" then Watch(row.SelectedOverlay, function() PaintRecipe(row) end) end
        Step("prof.ups", SkinSkillUps, row)
        PaintRecipe(row)
    end
end

local function RefreshProfessions()
    local win = _G.ProfessionsFrame
    local page = type(win) == "table" and win.CraftingPage or nil
    if type(page) ~= "table" then return end
    Step("prof.rank", SkinRankBar, page)
    Step("prof.panes", SkinCraftPanes, page)
    Step("prof.keys", SkinCraftKeys, page)
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

-- A node is a marker: a diamond of 1 px rows (a coloured edge, a dark plate, a bright core) over a soft glow, pink where you are with
-- a thin ring round it, cyan where you can fly, dim where you cannot; hovered, the edge goes white, the diamond a step larger and the
-- glow brighter. Built once per button or pin; the stock icon and highlight are held under it.
local GLOW_TEX = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"
local NODE_LOOK = {
    radius = { current = 9, reachable = 6, unreachable = 4 },
    glow = { current = 0.45, reachable = 0.25, unreachable = 0 },
    ring = 15, rows = 11,
}

local function DiamondRows(host, sub)
    local rows = {}
    for i = -NODE_LOOK.rows, NODE_LOOK.rows do
        local t = Kit.Rect(host, 0, 0, 1, 1, C.cyan, 1, "OVERLAY", sub)
        t.fsRow = i
        rows[#rows + 1] = t
    end
    return rows
end

-- A 1 px circle of radius R: per row a left and a right run between the outer and inner edge (one run across the top and bottom).
local function RingRows(host)
    local runs, R = {}, NODE_LOOK.ring
    for y = -R, R do
        local xo = math.floor(math.sqrt(math.max(0, R * R - y * y)) + 0.5)
        local inner = (R - 1) * (R - 1) - y * y
        local xi = inner > 0 and math.floor(math.sqrt(inner) + 0.5) or 0
        if xi < 1 then
            runs[#runs + 1] = { y = y, x = -xo, w = 2 * xo + 1 }
        else
            local w = math.max(1, xo - xi + 1)
            runs[#runs + 1] = { y = y, x = -xo, w = w }
            runs[#runs + 1] = { y = y, x = xo - w + 1, w = w }
        end
    end
    for _, r in ipairs(runs) do
        r.t = Kit.Rect(host, 0, 0, 1, 1, C.pink, 1, "OVERLAY", 4)
        Kit.Place(r.t, host, r.x, r.y, r.w, 1, "TOPLEFT", "CENTER")
    end
    return runs
end

local function NewDiamond(host)
    local glow = host:CreateTexture(nil, "OVERLAY", nil, 3)
    glow:SetTexture(GLOW_TEX)
    if glow.SetBlendMode then glow:SetBlendMode("ADD") end
    return { glow = glow, edge = DiamondRows(host, 5), plate = DiamondRows(host, 6), core = DiamondRows(host, 7) }
end

local function PaintRows(rows, host, radius, color, alpha)
    for _, t in ipairs(rows) do
        local d = math.abs(t.fsRow)
        if radius < 0 or d > radius then
            t:Hide()
        else
            local half = radius - d
            t:SetColorTexture(color[1], color[2], color[3], alpha)
            Kit.Place(t, host, -half, t.fsRow, 2 * half + 1, 1, "TOPLEFT", "CENTER")
            t:Show()
        end
    end
end

local function PaintDiamond(g, host, kind, hover)
    local r = NODE_LOOK.radius[kind] or NODE_LOOK.radius.unreachable
    if hover then r = r + 1 end
    local color = (kind == "current" and C.pink) or (kind == "reachable" and C.cyan) or C.dim
    PaintRows(g.edge, host, r + 1, hover and C.text or color, 1)
    PaintRows(g.plate, host, r - 1, C.ink, 0.9)
    PaintRows(g.core, host, math.max(1, r - 5), color, 1)
    local ga = hover and 0.55 or NODE_LOOK.glow[kind] or 0
    if ga > 0 then
        local size = 2 * (r + 8)
        g.glow:SetVertexColor(color[1], color[2], color[3], ga)
        Kit.Place(g.glow, host, -size / 2, -size / 2, size, size, "TOPLEFT", "CENTER")
        g.glow:Show()
    else
        g.glow:Hide()
    end
    if kind == "current" and not g.ring then g.ring = RingRows(host) end
    if g.ring then
        for _, run in ipairs(g.ring) do
            run.t:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 0.55)
            if kind == "current" then run.t:Show() else run.t:Hide() end
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

-- Route lines. The stock DrawLine stretches a dark line image across each TaxiRouteN texture, which reads black on the parchment
-- (live 2026-11-14). The texture is held and a 2 px cyan Line is drawn between the same two points; it follows the texture's
-- Show and Hide, so a route the stock code drops on hover goes with it. Only lines drawn on the flight map's canvas are touched.
local function RouteLine(texture, canvas)
    local line = S.routes[texture]
    if line then return line end
    if type(canvas.CreateLine) ~= "function" then return nil end
    local ok, made = pcall(canvas.CreateLine, canvas, nil, "ARTWORK", nil, 2)
    if not ok or type(made) ~= "table" then return nil end
    S.routes[texture] = made
    HeldArt.Hold(texture)
    Kit.HookFunc(texture, "Hide", function() made:Hide() end)
    Kit.HookFunc(texture, "Show", function() made:Show() end)
    return made
end

local function OnDrawLine(texture, canvas, sx, sy, ex, ey, _, a8, a9)
    if canvas == nil or canvas ~= _G.TaxiRouteMap or type(texture) ~= "table" then return end
    for _, v in ipairs({ sx, sy, ex, ey }) do if type(Plain(v)) ~= "number" then return end end
    local rel = (type(a9) == "string" and a9) or (type(a8) == "string" and a8) or "BOTTOMLEFT"
    local line = RouteLine(texture, canvas)
    if not line then return end
    line:ClearAllPoints()
    line:SetStartPoint(rel, canvas, sx, sy)
    line:SetEndPoint(rel, canvas, ex, ey)
    line:SetThickness(Kit.U(canvas, 2))
    line:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    line:Show()
end

local function BuildTaxi()
    local win = _G.TaxiFrame
    if type(win) ~= "table" or S.done.taxi then return end
    S.done.taxi = true
    win.fsServicesSkin = true
    -- the stuwave://taxi tag names the window, so the stock gold title is held like the character and map titles. The map
    -- art sits flush in the panel: a ring of its own read as a second border a few px inside the panel's (live 2026-11-14).
    Kit.HoldFrame(win.TitleText)
    if type(_G.DrawLine) == "function" and type(hooksecurefunc) == "function" then
        pcall(hooksecurefunc, "DrawLine", function(...) Step("taxi.route", OnDrawLine, ...) end)
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
