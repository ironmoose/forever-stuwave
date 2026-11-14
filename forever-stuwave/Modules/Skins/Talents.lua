-- Forever STUwave: Talents and Spellbook
-- The talent trees and the spellbook (PlayerSpellsFrame, readout debug/tree-PlayerSpellsFrame-2026-11-12.txt) restyled in place,
-- from the approved SPELLS mockup (mockups/character-spells-2026-11-12.html, section 2). The window chrome, the Primary and
-- Secondary tabs, the search box and the Apply Changes button already wear the shared panel and control skins (Panels.lua and
-- the controls sweep); this adds the parts that were still stock:
--
--   * the TalentsFrame: the gold top band, inner frame border, dividers, clouds and particles are held, a one pixel violet frame
--     and dividers stand in; the class art stays;
--   * the three spec headers (round icon with its count, name, small divider): the gold ring is desaturated to cyan, the count
--     box is an amber box, the name is mono;
--   * the Unspent Talents box: our own box and mono texts;
--   * every talent button gets a RING ONLY: its stock border art is desaturated and tinted by state, read from the atlas the
--     stock code set (locked or gray dim, yellow amber, green cyan), and follows it when the stock code swaps the atlas. Nothing
--     else on a talent button is touched, so every click, tooltip, drag and the commit flow stay stock;
--   * the arrows between talent buttons (pooled edge frames): the line and the arrow head take the same state colours (gray and
--     locked dim, yellow amber, red pink), read from their atlas and following each swap; the respec ghost parts stay stock;
--   * the window's minimise and maximise buttons: held art, a plate, a glyph;
--   * the spellbook: parchment page art held with a dark underlay, dark parchment text retinted, category tab frames held;
--   * every spellbook entry (the pooled SpellBookItemTemplate frames of the two page views) is a cut card: its stock backplate,
--     icon frame, trainable art and sheen held, an edge by state (learned violet, passive cyan, can be learned now pink, level
--     locked dim), a hover that lights the card from the icon, the name and sub text mono with the state colour following the stock
--     repaint, the required level amber (pink when it can be learned now), and the icon button seated as a square slot
--     (Quest.lua's SquareSlot, asked for lazily: Quest.lua loads after this file). A section header gets a rule under it and mono
--     text. The page keys are Quest.lua's cut keys with a cyan chevron, the "Page 1/3" text mono;
--   * the talent arrows (above).
--
-- Skin only: no SetAttribute, no reparent, no resize of a Blizzard frame, no field written on a talent or spell button, post-hooks
-- only. Talent buttons are met again whenever the tree is rebuilt (spec change, respec); the sweep is idempotent. A pooled spell
-- entry is met once and repainted by a post-hook on its own UpdateVisuals; frames the pool hands out later are met when the pages
-- redisplay.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the action
-- key echo strip and the key LED on each entry, the live trace from an entry to its key and the free-key pulse while dragging, the
-- cooldown sweep over the icon, the separate "train / passive / lvl" chips and the "on" state of a toggle (the edge colour carries
-- the same facts), the circuit-board trace layout, the level gates and the hold-to-commit button of the talent page (the stock
-- Apply Changes flow stays), the slanted school tabs, the rank text restyle (the stock number and its four outline copies are
-- re-fonted by the art code on every state change; they stay stock), and the help plate button.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.SkinSquare and PanelSkins.RequireExport(
    Theme.ApplyMono and PanelSkins.RetintDarkText,
    "Talents.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Tal = {}
FS.TalentsSkin = Tal

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 },
}

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { done = false, nodes = Weak(), edges = Weak(), specs = Weak(), books = Weak(), rules = {}, texts = Weak(), items = Weak(), heads = Weak() }
Tal.state = S

local Plain, Try = Kit.Plain, Kit.Try
local List, AtlasOf = Char.List, Char.AtlasOf

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("talents:" .. name, ("|cffff4488Forever STUwave|r: talents skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

-- A 1 px line anchored over `ref` (a frame or a texture): across it ("h", through its middle) or along it ("v", through its
-- middle), colour `color`. Re-sized on a change of pixel scale.
local function Rule(host, ref, orient, color, alpha)
    local t = host:CreateTexture(nil, "OVERLAY", nil, 5)
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    local rec = { t = t, host = host, ref = ref, orient = orient }
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        if orient == "h" then
            t:SetPoint("LEFT", ref, "LEFT", 0, 0)
            t:SetPoint("RIGHT", ref, "RIGHT", 0, 0)
            t:SetHeight(u)
        else
            t:SetPoint("TOP", ref, "TOP", 0, 0)
            t:SetPoint("BOTTOM", ref, "BOTTOM", 0, 0)
            t:SetWidth(u)
        end
    end
    S.rules[#S.rules + 1] = rec
    rec.apply()
    return t
end

local function Tint(region, color, desaturate)
    if type(region) ~= "table" then return end
    if desaturate and type(region.SetDesaturated) == "function" then pcall(region.SetDesaturated, region, true) end
    if type(region.SetVertexColor) == "function" then pcall(region.SetVertexColor, region, color[1], color[2], color[3], 1) end
end

-------------------------------------------------------------------------------
-- Talent buttons: a ring only
-------------------------------------------------------------------------------

-- The ring colour of a state, told by the atlas the stock code gave the border; nil for one this does not know (left stock).
local function RingColor(atlas)
    if type(atlas) ~= "string" then return nil end
    atlas = atlas:lower()
    if atlas:find("locked") or atlas:find("gray") or atlas:find("grey") or atlas:find("disabled") then return C.dim end
    if atlas:find("yellow") or atlas:find("gold") or atlas:find("maxed") then return C.amber end
    if atlas:find("green") or atlas:find("learn") then return C.cyan end
    if atlas:find("red") then return C.pink end
    return nil
end

local function PaintNode(btn)
    local border = btn.StateBorder
    local color = RingColor(AtlasOf(border))
    if color then Tint(border, color, true) end
    Tint(btn.StateBorderHover, C.cyan, true)
    Tint(btn.Glow, C.cyan, true)
    Tint(btn.SelectableGlow, C.cyan, true)
end

local NODE_HOOKS = { "UpdateStateBorder", "UpdateVisualState", "UpdateNonStateVisuals", "SetVisualState", "UpdateAll" }

local function SkinNode(btn)
    if type(btn) ~= "table" or S.nodes[btn] or type(btn.StateBorder) ~= "table" then return end
    S.nodes[btn] = true
    if btn.StateBorder.SetAtlas then Kit.HookFunc(btn.StateBorder, "SetAtlas", function() PaintNode(btn) end) end
    for _, m in ipairs(NODE_HOOKS) do Kit.HookFunc(btn, m, function() PaintNode(btn) end) end
    PaintNode(btn)
end

-- The arrows between nodes (TalentEdgeArrowTemplate, children of the ButtonsParent, pooled): a Line and an ArrowHead whose atlas
-- the stock UpdateState swaps by state (gray, yellow, locked, red). Same rule as the ring: tinted by the atlas read back, and
-- follows each swap. The ghost line and ghost head (the respec preview) stay stock.
local EDGE_PARTS = { "Line", "ArrowHead" }

local function PaintEdge(edge)
    for _, key in ipairs(EDGE_PARTS) do
        local part = edge[key]
        local color = RingColor(AtlasOf(part))
        if color then Tint(part, color, true) end
    end
end

local function IsEdge(frame)
    return type(frame.Line) == "table" and type(frame.ArrowHead) == "table" and frame.StateBorder == nil
end

local function SkinEdge(edge)
    if S.edges[edge] or not IsEdge(edge) then return end
    S.edges[edge] = true
    for _, key in ipairs(EDGE_PARTS) do
        if edge[key].SetAtlas then Kit.HookFunc(edge[key], "SetAtlas", function() PaintEdge(edge) end) end
    end
    Kit.HookFunc(edge, "UpdateState", function() PaintEdge(edge) end)
    PaintEdge(edge)
end

local function SkinNodes(frame)
    local parent = frame.ButtonsParent
    if type(parent) ~= "table" then return end
    for _, child in ipairs(List(parent, "GetChildren")) do
        SkinNode(child)
        SkinEdge(child)
    end
end

-------------------------------------------------------------------------------
-- The talent frame
-------------------------------------------------------------------------------

local FRAME_ART = {
    "Background", "BackgroundBorder", "DividerHorizontalLeft", "DividerHorizontalRight", "DividerVerticalLeft",
    "DividerVerticalRight", "Clouds1", "Clouds2", "AirParticlesClose", "AirParticlesFar",
}

local function SkinFrameArt(frame)
    for _, key in ipairs(FRAME_ART) do HeldArt.Hold(frame[key]) end
    if S.frameRules then return end
    S.frameRules = true
    local border = frame.BackgroundBorder
    if border then
        local box = Char.Box(frame, "OVERLAY", border)
        Char.PaintBox(box, C.ink, 0, C.violet, 1, 1)
    end
    for _, key in ipairs({ "DividerVerticalLeft", "DividerVerticalRight" }) do
        if frame[key] then Rule(frame, frame[key], "v", C.violet, 0.8) end
    end
    for _, key in ipairs({ "DividerHorizontalLeft", "DividerHorizontalRight" }) do
        if frame[key] then Rule(frame, frame[key], "h", C.violet, 0.8) end
    end
end

local function SkinSpecHeader(head)
    if S.specs[head] then return end
    S.specs[head] = true
    HeldArt.Hold(head.TextBackground)
    HeldArt.Hold(head.Divider)
    Tint(head.MainRing, C.cyan, true)
    if head.TextBackground then
        local box = Char.Box(head, "OVERLAY", head.TextBackground)
        Char.PaintBox(box, C.ink, 1, C.amber, 1, 1)
    end
    if head.Divider then Rule(head, head.Divider, "h", C.violet, 0.8) end
    if head.Name then Kit.RestyleLabel(head.Name, head, 15, C.text); Char.PinColor(head.Name, C.text) end
    if head.Text then Kit.RestyleLabel(head.Text, head, 12, C.amber); Char.PinColor(head.Text, C.amber) end
end

local function SkinSpecHeaders(frame)
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.MainRing and child.TextBackground and child.Name then SkinSpecHeader(child) end
    end
end

local function SkinCurrency(frame)
    local box = frame.ClassCurrencyDisplay
    if type(box) ~= "table" or S.currency then return end
    S.currency = true
    HeldArt.Hold(box.Border)
    if box.Border then
        local b = Char.Box(box, "OVERLAY", box.Border)
        Char.PaintBox(b, C.ink, 1, C.violet, 1, 1)
    end
    if box.UnspentLabel then Kit.RestyleLabel(box.UnspentLabel, box, 12, C.muted); Char.PinColor(box.UnspentLabel, C.muted) end
    local amount = box.CurrentAmountContainer and box.CurrentAmountContainer.CurrencyAmount
    if amount then Kit.RestyleLabel(amount, box, 22, C.amber); Char.PinColor(amount, C.amber) end
end

local function SkinTalents(frame)
    SkinFrameArt(frame)
    SkinSpecHeaders(frame)
    SkinCurrency(frame)
    SkinNodes(frame)
end

-------------------------------------------------------------------------------
-- Minimise and maximise
-------------------------------------------------------------------------------

-- The window's size toggle wears the close button's key, cyan, seated just left of the close button: a window glyph to
-- maximise, a bar to restore.
local function SkinSizeButton(btn, glyph, close)
    if type(btn) ~= "table" or not (FS.ButtonSkins and FS.ButtonSkins.SkinCloseButton) then return end
    FS.ButtonSkins.SkinCloseButton(btn, { glyph = glyph, accent = C.cyan, beside = close })
end

local function SkinSizeButtons(win)
    local pair = win.MaximizeMinimizeButton
    if type(pair) ~= "table" then return end
    local close = type(win.CloseButton) == "table" and win.CloseButton or nil
    SkinSizeButton(pair.MinimizeButton, "minus", close)
    SkinSizeButton(pair.MaximizeButton, "max", close)
end

-------------------------------------------------------------------------------
-- The spellbook entries, headers and page keys
-------------------------------------------------------------------------------

-- The book's pages are a PagedContent frame: its two views hold pooled frames (a SpellBookItemTemplate entry: Backplate, a
-- TextContainer with Name, SubName and RequiredLevel, and a Button with the icon, an icon frame and the trainable art; a
-- SpellBookHeaderTemplate header). A pooled frame is met once (weak table) and repainted by a post-hook on its own UpdateVisuals,
-- the stock code's one repaint of an entry.

local ENTRY = { CUT = 6, PAD = 2, OVER = 6, W = 220, H = 60 }
local ENTRY_BUTTON_ART = { "Border", "TrainableBackplate", "TrainableShadow", "BorderSheen", "IconHighlight" }

local function Flag(v) return Plain(v) == true end

-- learned, passive, trainable (learnable at a trainer now) and level locked (unlearned and not trainable), read from the fields the
-- stock code writes on the entry; a value the client keeps secret reads as plain false.
local function EntryState(item)
    local info = Plain(item.spellBookItemInfo)
    local passive = type(info) == "table" and Flag(info.isPassive)
    local unlearned, trainable = Flag(item.isUnlearned), Flag(item.isTrainable)
    return { unlearned = unlearned, trainable = trainable, passive = passive, locked = unlearned and not trainable }
end

-- A text whose colour is ours and moves with the entry's state: the stock SetTextColor is answered with `read()`. Returns the
-- function that applies it now.
local function Follow(fs, read)
    if type(fs) ~= "table" or type(fs.SetTextColor) ~= "function" then return function() end end
    local busy = false
    local function apply()
        local c = read()
        if busy or not c then return end
        busy = true
        pcall(fs.SetTextColor, fs, c[1], c[2], c[3], 1)
        busy = false
    end
    Kit.HookFunc(fs, "SetTextColor", function() if not busy then apply() end end)
    return apply
end

local function PaintEntry(item)
    local rec = S.items[item]
    if not rec then return end
    local st = EntryState(item)
    local hover = rec.state and rec.state.hover
    local edge, edgeAlpha, fill, fillAlpha = C.violet, 0.6, C.ink, 0.85
    if st.trainable then edge, edgeAlpha = C.pink, 1
    elseif st.locked then edge, edgeAlpha, fillAlpha = C.dim, 0.9, 0.55
    elseif st.passive then edge, edgeAlpha = C.cyan, 0.6 end
    if hover then fill, fillAlpha, edgeAlpha = Kit.Mix(C.ink, edge, 0.22), 1, 1 end
    Kit.PaintPlate(rec.plate, fill, fillAlpha, edge, edgeAlpha, 1)
    rec.colors.name = st.trainable and C.pink or (st.locked and C.muted or C.text)
    rec.colors.sub = C.muted
    rec.colors.req = st.trainable and C.pink or C.amber
    for _, apply in pairs(rec.pins) do apply() end
end

-- The card is the entry's rect, PAD physical pixels in on the top, right and bottom so two neighbours never share an edge, and
-- OVER pixels out on the left, so the icon (the stock code seats it flush at the entry's left edge) has a margin inside the card.
-- Re-seated when the entry's pixel size is not the one it was seated at (a change of scale).
local function SeatEntry(item, rec)
    local w, h = Kit.SizePx(item)
    w, h = w or ENTRY.W, h or ENTRY.H
    if rec.w == w and rec.h == h then return end
    rec.w, rec.h = w, h
    local pad, over = ENTRY.PAD, ENTRY.OVER
    local x, y, pw, ph = -over, pad, w + over - pad, h - 2 * pad
    Kit.Place(rec.plate.fill, item, x, y, pw, ph)
    Kit.Place(rec.plate.ring, item, x, y, pw, ph)
    if rec.plate.ring2 then Kit.Place(rec.plate.ring2, item, x + 1, y + 1, pw - 2, ph - 2) end
end

local function BuildEntry(item, btn)
    HeldArt.Hold(item.Backplate)
    for _, key in ipairs(ENTRY_BUTTON_ART) do HeldArt.Hold(btn[key]) end
    local w, h = Kit.SizePx(item)
    local rec = { plate = Kit.Plate(item, ENTRY.CUT, (w or ENTRY.W) + ENTRY.OVER - ENTRY.PAD, (h or ENTRY.H) - 2 * ENTRY.PAD), colors = {}, pins = {} }
    S.items[item] = rec
    SeatEntry(item, rec)
    local host = item.TextContainer or item
    for _, spec in ipairs({ { "Name", 14, "name" }, { "SubName", 11, "sub" }, { "RequiredLevel", 11, "req" } }) do
        local fs = item[spec[1]]
        if type(fs) == "table" then
            Kit.RestyleLabel(fs, host, spec[2], C.text)
            local key = spec[3]
            rec.pins[key] = Follow(fs, function() return rec.colors[key] end)
        end
    end
    -- the card follows the icon's hover (that is the stock widget under the hand), and the stock repaint of the entry
    rec.state = Kit.Track(btn, function() PaintEntry(item) end)
    Kit.HookFunc(item, "UpdateVisuals", function() SeatEntry(item, rec); PaintEntry(item) end)
    PaintEntry(item)
    return rec
end

-- An entry is built once; the slot on its icon button is asked for on every pass until the shared slot layer (Quest.lua, loaded
-- after this file) answers: the icon button is the slot, with the stock art held, the cut plate, the quality-less slot layer (hover
-- brackets, cooldown drain) and the icon seated.
local function SkinEntry(item)
    local btn = item.Button
    if type(btn) ~= "table" then return end
    local rec = S.items[item] or BuildEntry(item, btn)
    if rec.slot then return end
    local Q = FS.QuestSkin
    if Q and Q.SquareSlot then
        Q.SquareSlot(btn)
        rec.slot = true
    end
end

local function SkinHeader(head)
    if S.heads[head] then return end
    S.heads[head] = true
    HeldArt.Hold(head.Backplate)
    HeldArt.Hold(head.Border)
    if head.Border then Rule(head, head.Border, "h", C.violet, 0.8) end
    if head.Text then Kit.RestyleLabel(head.Text, head, 16, C.text); Char.PinColor(head.Text, C.text) end
end

local function IsEntry(f)
    return type(f.Button) == "table" and type(f.TextContainer) == "table" and type(f.Button.Icon) == "table"
end

local function IsHeader(f)
    return f.Button == nil and type(f.Text) == "table" and type(f.Backplate) == "table" and type(f.Border) == "table"
end

-- Every entry and header the two views hold now: through the paged frame's own ForEachFrame and by the views' children (the
-- second covers a client where the first is missing; a frame met twice is skipped by the weak tables).
local function PageFrames(paged)
    local out = {}
    if type(paged.ForEachFrame) == "function" then pcall(paged.ForEachFrame, paged, function(f) out[#out + 1] = f end) end
    for _, key in ipairs({ "View1", "View2" }) do
        for _, f in ipairs(List(paged[key], "GetChildren")) do out[#out + 1] = f end
    end
    return out
end

local function SkinPages(paged)
    for _, f in ipairs(PageFrames(paged)) do
        if type(f) == "table" then
            if IsEntry(f) then Step("entry", SkinEntry, f) elseif IsHeader(f) then Step("header", SkinHeader, f) end
        end
    end
end

-- The page keys are Quest.lua's cut keys (resolved now: Quest.lua loads after this file); the stock "Page 1/3" text goes mono.
local function SkinPaging(paging)
    if type(paging) ~= "table" then return end
    local Q = FS.QuestSkin
    if Q and Q.PagerKey then
        Q.PagerKey(paging.PrevPageButton, "<")
        Q.PagerKey(paging.NextPageButton, ">")
    end
    if type(paging.PageText) == "table" then
        Kit.RestyleLabel(paging.PageText, paging, 13, C.text)
        Char.PinColor(paging.PageText, C.text)
    end
end

local PAGED_REFRESH = { "DisplayViewsForCurrentPage", "OnPageChanged", "SetDataProvider", "SetViewsPerPage" }

local function SkinPaged(book)
    local paged = book.PagedSpellsFrame
    if type(paged) ~= "table" then return end
    if not S.books[paged] then
        S.books[paged] = true
        for _, m in ipairs(PAGED_REFRESH) do Kit.HookFunc(paged, m, function() Kit.Later(function() SkinPages(paged) end) end) end
    end
    Step("paging", SkinPaging, paged.PagingControls)
    SkinPages(paged)
end

-------------------------------------------------------------------------------
-- The spellbook
-------------------------------------------------------------------------------

local BOOK_KEEP = { "rotationhelper", "Tab%-Frame" }

local function IsBookArt(atlas)
    if not atlas:find("^spellbook%-") then return false end
    for _, p in ipairs(BOOK_KEEP) do if atlas:find(p) then return false end end
    return true
end

local function HoldBookArt(frame, depth)
    if type(frame) ~= "table" or depth > 7 then return end
    for _, region in ipairs(List(frame, "GetRegions")) do
        local kind = Try(region.GetObjectType, region)
        if kind == "Texture" then
            local atlas = AtlasOf(region)
            if atlas and IsBookArt(atlas) then HeldArt.Hold(region) end
        elseif kind == "FontString" then
            -- the pages were written for parchment: dark text is lifted to the light text colour, state colours pass through
            pcall(PanelSkins.RetintDarkText, region, C.text)
        end
    end
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.Track == nil then HoldBookArt(child, depth + 1) end
    end
end

-- The names the book's own refresh runs under (SpellBookFrameMixin: UpdateAllSpellData, UpdateDisplayedSpells, OnActiveCategoryChanged),
-- and older guesses kept for a client that names them differently.
local BOOK_REFRESH = { "UpdateAllSpellData", "UpdateDisplayedSpells", "OnActiveCategoryChanged", "UpdateDisplay", "Update", "UpdateTabs", "DisplayPage", "SetCategory", "RefreshDisplay" }

local function RefreshBook(book)
    HoldBookArt(book, 0)
    SkinPaged(book)
end

local function SkinBook(book)
    if type(book) ~= "table" then return end
    for _, key in ipairs({ "BookBGHalved", "BookBGLeft", "BookBGRight", "BookCornerFlipbook" }) do HeldArt.Hold(book[key]) end
    if not S.books[book] then
        S.books[book] = true
        local under = book:CreateTexture(nil, "BACKGROUND", nil, -6)
        under:SetAllPoints(book)
        under:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.55)
        for _, m in ipairs(BOOK_REFRESH) do Kit.HookFunc(book, m, function() Kit.Later(function() Step("book", RefreshBook, book) end) end) end
        Kit.HookScript(book, "OnShow", function() Kit.Later(function() Step("book", RefreshBook, book) end) end)
    end
    -- the category tabs keep their STUwave plate; the stock gold square frame behind each icon is held
    local tabs = book.tabSystem
    for _, tab in ipairs(List(tabs, "GetChildren")) do
        for _, key in ipairs({ "SquareBackground", "SquareBackgroundActive", "SquareBackgroundActiveGlow" }) do HeldArt.Hold(tab[key]) end
    end
    RefreshBook(book)
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

function Tal.Refresh()
    if not S.done then return end
    local win = _G.PlayerSpellsFrame
    if not win then return end
    Step("size", SkinSizeButtons, win)
    if win.TalentsFrame then Step("talents", SkinTalents, win.TalentsFrame) end
    if win.SpellBookFrame then Step("book", SkinBook, win.SpellBookFrame) end
end

local function Relayout()
    for _, rec in ipairs(S.rules) do rec.apply() end
end

local TALENT_REFRESH = { "UpdateTreeInfo", "UpdateInspecting", "RefreshAllData", "ReleaseAllTalentButtons", "UpdateAll", "LoadTalentTree" }

local function Build()
    local win = _G.PlayerSpellsFrame
    if not win or S.done then return end
    S.done = true
    win.fsTalentsSkin = true
    local talents = win.TalentsFrame
    if talents then
        for _, m in ipairs(TALENT_REFRESH) do Kit.HookFunc(talents, m, function() Kit.Later(Tal.Refresh) end) end
        Kit.HookScript(talents, "OnShow", function() Kit.Later(Tal.Refresh) end)
    end
    Kit.HookScript(win, "OnShow", function() Kit.Later(Tal.Refresh) end)
    Kit.OnReseat(function() Relayout(); Tal.Refresh() end)
    Tal.Refresh()
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "TRAIT_CONFIG_UPDATED", "TRAIT_TREE_CURRENCY_INFO_UPDATED", "PLAYER_TALENT_UPDATE", "ACTIVE_PLAYER_SPECIALIZATION_CHANGED" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function() if S.done then Kit.Later(Tal.Refresh) end end)

PanelSkins.RegisterInspect("Talents", { { name = "PlayerSpellsFrame", guard = "fsTalentsSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
