-- Forever STUwave: Loot rolls
-- The group loot roll frames (GroupLootFrame1 to 4, the toasts that ask need, greed or pass) and the roll history panel
-- (GroupLootHistoryFrame) restyled in place from the approved LOOT + GROUP mockup (mockups/loot-group-2026-11-12.html, sections 2
-- and 3), over the real tree (Blizzard_UIPanels_Game GroupLootFrame.xml: a 277 x 67 toast with Background, Border, IconFrame
-- (Icon, Count, Border), Name, NeedButton / GreedButton / TransmogButton / PassButton, a Timer StatusBar and NeedRollAnim;
-- Blizzard_FrameXML LootHistory.xml for the history). The kit it draws with (glyphs, cut card, item slot) is FS.LootSkin, Loot.lua.
--
--   * every roll frame is a cut card (ink face, violet edge) with a LEFT QUALITY RAIL (the quality of the item being rolled for);
--     the stock toast background and border art, the icon border and the stock bar are held;
--   * "the fuse": the Timer stays the stock bar (its values and its updates are untouched) and a lit fuse is drawn along the card's
--     foot from them: cyan, amber under 35 percent of the time, pink under 10 percent with a pink card edge, a bright head at the
--     burning tip;
--   * the four keys are cut keys over the stock buttons, glyph in the key's colour with a lit line under it: need a cyan die, greed
--     a gold coin, transmog a gold star, pass a pink cross; hover lights the edge, a roll the player cannot make (the stock code
--     disables the button) goes steel and loses its line. Clicks, tooltips and the reason text stay stock;
--   * the icon wears the shared slot layer, the item name is mono on a white base so the stock quality tint shows.
--   * the roll history panel: panel skin with a `stuwave://rolls` band, every row a card with the item slot layer and a quality rail,
--     the stock row art and timer art held, texts mono.
--
-- Skin only, as in Commerce.lua and Loot.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard
-- frame, post-hooks and alpha holds only.
--
-- Left out on purpose, because the mockup shows a display this client has no data for or a function the stock frame does not
-- have: the ballot pips (who has rolled and what), the disenchant key (no such button in the 12.1 XML), the sub line under the
-- name (bind text, "need: roll 1-100", the blocked reason: the stock tooltips already say it), the stamped result chip and the
-- seconds left (computed), the paused and passed card states, and on the history the dice line, the encounter switch and the legend.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G, L = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin, FS.LootSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and L and L.Glyph and L.Card and L.ItemSlot) then return end

local R = {}
FS.LootRollSkin = R

local C = L.C
local Plain, Try = Kit.Plain, Kit.Try
local Step = L.Step

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { frames = Weak(), keys = Weak(), rows = Weak(), done = {} }
R.state = S

-------------------------------------------------------------------------------
-- Strip: a line along the foot of a frame that follows its width
-------------------------------------------------------------------------------

local strips = {}
Kit.OnReseat(function() for _, rec in ipairs(strips) do rec.apply() end end)

-- A bar `h` pixels tall, `bottom` pixels up from the foot of `host`, `left` and `right` pixels in from its sides.
local function Strip(host, color, alpha, layer, sub, left, right, bottom, h)
    local t = host:CreateTexture(nil, layer, nil, sub)
    t:SetColorTexture(color[1], color[2], color[3], alpha)
    local rec = {}
    function rec.apply()
        local u = Kit.U(host, 1)
        t:ClearAllPoints()
        t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", left * u, bottom * u)
        t:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -right * u, bottom * u)
        t:SetHeight(h * u)
    end
    strips[#strips + 1] = rec
    rec.apply()
    return t
end

-------------------------------------------------------------------------------
-- The keys
-------------------------------------------------------------------------------

local KEY = { SIZE = 24, CUT = 4, GLYPH_X = 4, GLYPH_Y = 2, LED_Y = 20 }
local KEYS = {
    { key = "NeedButton", glyph = "die", color = C.cyan },
    { key = "GreedButton", glyph = "coin", color = C.gold },
    { key = "TransmogButton", glyph = "star", color = C.gold },
    { key = "PassButton", glyph = "x", color = C.pink },
}

local function PaintKey(btn)
    local k = S.keys[btn]
    if not k then return end
    local on = Kit.IsEnabled(btn)
    local hover = on and k.state and (k.state.hover or k.state.pressed)
    local col = on and k.color or C.steel
    Kit.PaintPlate(k.plate, hover and C.well or C.ink, on and (hover and 1 or 0.55) or 0.4,
        hover and col or (on and C.line or C.steel), on and 1 or 0.6, hover and 2 or 1)
    k.glyph.Paint(col, on and 1 or 0.5)
    k.led:SetColorTexture(col[1], col[2], col[3], hover and 1 or 0.7)
    k.led:SetShown(on)
end

local function SkinKey(btn, spec)
    if type(btn) ~= "table" or S.keys[btn] or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 38, bh or 38
    local P = KEY.SIZE
    local x, y = math.floor((bw - P) / 2), math.floor((bh - P) / 2)
    local k = { color = spec.color }
    k.plate = Kit.Plate(btn, KEY.CUT, P, P)
    Kit.Place(k.plate.fill, btn, x, y, P, P)
    Kit.Place(k.plate.ring, btn, x, y, P, P)
    if k.plate.ring2 then Kit.Place(k.plate.ring2, btn, x + 1, y + 1, P - 2, P - 2) end
    k.glyph = L.Glyph(btn, spec.glyph, x + KEY.GLYPH_X, y + KEY.GLYPH_Y, spec.color, "OVERLAY", 5)
    k.led = Kit.Rect(btn, x + KEY.GLYPH_X, y + KEY.LED_Y, 16, 2, spec.color, 0.7, "OVERLAY", 5)
    S.keys[btn] = k
    k.state = Kit.Track(btn, PaintKey)
    PaintKey(btn)
end

-------------------------------------------------------------------------------
-- The roll frames
-------------------------------------------------------------------------------

local FRAME_COUNT = 4
local FUSE = { MARGIN = 6, BOTTOM = 6, H = 4, AMBER = 0.35, PINK = 0.10 }

local function Fraction(timer)
    if type(timer) ~= "table" then return nil end
    local lo, hi = Try(timer.GetMinMaxValues, timer)
    local v = Try(timer.GetValue, timer)
    lo, hi, v = Plain(lo), Plain(hi), Plain(v)
    if type(lo) ~= "number" or type(hi) ~= "number" or type(v) ~= "number" or hi <= lo then return nil end
    return math.max(0, math.min(1, (v - lo) / (hi - lo)))
end

local function PaintFrame(f)
    local rec = S.frames[f]
    if not rec then return end
    local frac = Fraction(f.Timer) or 1
    local low = frac < FUSE.PINK
    local color = low and C.pink or (frac < FUSE.AMBER and C.amber or C.cyan)
    rec.fuse:SetColorTexture(color[1], color[2], color[3], 1)
    rec.head:SetColorTexture(color[1], color[2], color[3], 1)
    local W = Kit.SizePx(f) or 332
    local track = math.max(1, W - 2 * FUSE.MARGIN)
    local w = math.floor(track * frac + 0.5)
    Kit.Move(rec.fuse, FUSE.MARGIN, -FUSE.BOTTOM, w, FUSE.H)
    Kit.Move(rec.head, FUSE.MARGIN + math.max(0, w - 2), -(FUSE.BOTTOM - 1), 3, FUSE.H + 2)
    rec.head:SetShown(w > 0)
    rec.low = low
    Kit.PaintPlate(rec.plate, C.ink, 1, low and C.pink or C.violet, 1, 1)
end

-- What the frame is rolling for: the quality colour of the rail, read from the same call the stock frame fills itself from.
local function Refresh(f)
    local rec = S.frames[f]
    if not rec then return end
    local quality = 1
    if type(_G.GetLootRollItemInfo) == "function" and Plain(f.rollID) ~= nil then
        local ok, _, _, _, q = pcall(_G.GetLootRollItemInfo, f.rollID)
        if ok then quality = L.QualityOf(q) end
    end
    local color = L.Q[quality]
    rec.ledColor = color
    rec.led.Paint(color, 1)
    rec.band.Paint(color, 0.16)
    if type(f.IconFrame) == "table" then
        L.state.quality[f.IconFrame] = quality
        L.RefreshSlot(f.IconFrame)
    end
    for _, spec in ipairs(KEYS) do PaintKey(f[spec.key]) end
    PaintFrame(f)
end

local function SkinFrame(f)
    if type(f) ~= "table" or S.frames[f] or type(f.CreateTexture) ~= "function" then return end
    HeldArt.Hold(f.Background)
    HeldArt.Hold(f.Border)
    local icon = f.IconFrame
    local timer = f.Timer
    local rec = {}
    S.frames[f] = rec
    f.fsLootRollSkin = true
    rec.plate = L.Card(f, 6)
    rec.band = G.Bar(f, C.gold, 6, 6, 1)
    rec.led = G.Bar(f, C.gold, 2, 6, 1)
    if type(icon) == "table" then
        HeldArt.Hold(icon.Border)
        L.ItemSlot(icon)
    end
    G.Mono(f.Name, f, 11, C.white)
    if type(timer) == "table" then
        HeldArt.Hold(timer.Background)
        HeldArt.Hold(Try(timer.GetStatusBarTexture, timer))
        rec.track = Strip(f, C.violet, 0.18, "ARTWORK", 3, FUSE.MARGIN, FUSE.MARGIN, FUSE.BOTTOM, FUSE.H)
    end
    rec.fuse = Kit.Rect(f, FUSE.MARGIN, -FUSE.BOTTOM, 1, FUSE.H, C.cyan, 1, "ARTWORK", 4)
    Kit.Place(rec.fuse, f, FUSE.MARGIN, -FUSE.BOTTOM, 1, FUSE.H, "BOTTOMLEFT", "BOTTOMLEFT", f)
    rec.head = Kit.Rect(f, FUSE.MARGIN, -(FUSE.BOTTOM - 1), 3, FUSE.H + 2, C.cyan, 1, "ARTWORK", 5)
    Kit.Place(rec.head, f, FUSE.MARGIN, -(FUSE.BOTTOM - 1), 3, FUSE.H + 2, "BOTTOMLEFT", "BOTTOMLEFT", f)
    -- the fuse and the key colours move with the frame's own state
    for _, spec in ipairs(KEYS) do SkinKey(f[spec.key], spec) end
    if type(timer) == "table" then
        for _, method in ipairs({ "SetValue", "SetMinMaxValues" }) do
            Kit.HookFunc(timer, method, function() PaintFrame(f) end)
        end
    end
    Kit.HookScript(f, "OnShow", function() Refresh(f) end)
    Refresh(f)
end

-------------------------------------------------------------------------------
-- The roll history (GroupLootHistoryFrame)
-------------------------------------------------------------------------------

local HIST = { SKIN = { fillColor = Theme.COLOR_BG, accent = C.violet, title = "rolls" } }

-- The quality of the drop a history row shows, from the item link the stock Init was handed (nil when the client has not cached it).
local function DropQuality(drop)
    local link = type(drop) == "table" and Plain(drop.itemHyperlink) or nil
    local api = _G.C_Item
    if link == nil or type(api) ~= "table" or type(api.GetItemQualityByID) ~= "function" then return nil end
    local ok, q = pcall(api.GetItemQualityByID, link)
    return ok and Plain(q) or nil
end

local function PaintHistoryRow(row, drop)
    local rec = S.rows[row]
    if not rec then return end
    if drop ~= nil then rec.quality = DropQuality(drop) or rec.quality end
    local q = L.QualityOf(rec.quality)
    local color = L.Q[q]
    rec.ledColor = color
    rec.led.Paint(color, 1)
    rec.band.Paint(color, 0.18)
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Kit.PaintPlate(rec.plate, C.ink, 1, hover and C.cyan or C.line, 1, 1)
    if type(row.Item) == "table" then
        L.state.quality[row.Item] = q
        L.RefreshSlot(row.Item)
    end
end

local function SkinHistoryRow(row)
    -- the "passed" header and spacer rows are plain frames with no item: only drop rows are cards
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" or type(row.ItemName) ~= "table" then return end
    local art = row.BackgroundArtFrame
    if type(art) == "table" then
        HeldArt.Hold(art.NameFrame)
        HeldArt.Hold(art.BorderFrame)
        G.HoldRegions(art)
    end
    local rec = {}
    S.rows[row] = rec
    rec.plate = L.Card(row, 4)
    rec.band = G.Bar(row, C.gold, 6, 8, 1)
    rec.led = G.Bar(row, C.gold, 2, 8, 1)
    if type(row.Item) == "table" then L.ItemSlot(row.Item) end
    G.Mono(row.ItemName, row, 11, C.white)
    for _, spec in ipairs({ { "WinningRollInfo", "WinningRoll", C.text }, { "PendingRollInfo", "CurrentWinnerText", C.muted },
        { "AllPassedInfo", "AllPassedText", C.pink } }) do
        local info = row[spec[1]]
        if type(info) == "table" then G.Mono(info[spec[2]], row, 11, spec[3]) end
    end
    rec.state = Kit.Track(row, function() PaintHistoryRow(row) end)
    Kit.HookFunc(row, "Init", function(_, drop) PaintHistoryRow(row, drop) end)
    PaintHistoryRow(row, row.dropInfo)
end

local function PaintGrip(btn)
    local g = S.grip
    if not g then return end
    local hover = g.state and (g.state.hover or g.state.pressed)
    local c = hover and C.cyan or C.violet
    for _, t in ipairs(g.rects) do t:SetColorTexture(c[1], c[2], c[3], 1) end
end

local function SkinGrip(btn)
    if type(btn) ~= "table" or S.grip or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 38, bh or 14
    local x, y = math.floor((bw - 20) / 2), math.floor((bh - 6) / 2)
    S.grip = { rects = { Kit.Rect(btn, x, y, 20, 2, C.violet, 1, "OVERLAY", 4), Kit.Rect(btn, x + 4, y + 4, 12, 2, C.violet, 1, "OVERLAY", 4) } }
    S.grip.state = Kit.Track(btn, PaintGrip)
    PaintGrip(btn)
end

local function SkinHistory(win)
    if type(win) ~= "table" or S.done.history then return end
    S.done.history = true
    PanelSkins.SkinPanelCached(win, HIST.SKIN)
    PanelSkins.HookShowOnce(win, "fsLootHistoryShowHooked", function(self) PanelSkins.SkinPanelCached(self, HIST.SKIN) end)
    local timer = win.Timer
    if type(timer) == "table" then
        HeldArt.Hold(timer.Background)
        HeldArt.Hold(timer.Border)
        if type(timer.Fill) == "table" and type(timer.Fill.SetVertexColor) == "function" then
            pcall(timer.Fill.SetVertexColor, timer.Fill, C.cyan[1], C.cyan[2], C.cyan[3], 1)
        end
        Char.PaintBox(Char.Box(win, "BORDER", timer), C.ink, 1, C.dim, 1, 1)
    end
    SkinGrip(win.ResizeButton)
    PanelSkins.SweepOnShow(win)
    G.Rows(win.ScrollBox, function(row) Step("history.row", SkinHistoryRow, row) end)
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    for i = 1, FRAME_COUNT do Step("frame" .. i, SkinFrame, G.Named("GroupLootFrame" .. i)) end
    Step("history", SkinHistory, G.Named("GroupLootHistoryFrame"))
end

local entries = {}
for i = 1, FRAME_COUNT do entries[i] = { name = "GroupLootFrame" .. i, guard = "fsLootRollSkin" } end
entries[#entries + 1] = { name = "GroupLootHistoryFrame", guard = "fsSkinCache" }
PanelSkins.RegisterInspect("LootRolls", entries)

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
