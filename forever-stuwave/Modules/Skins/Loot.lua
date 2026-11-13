-- Forever STUwave: Loot window
-- The loot window (LootFrame) restyled in place from the approved LOOT + GROUP mockup (mockups/loot-group-2026-11-12.html,
-- section 1, "the manifest"), laid over the frame tree the retail 12.x client really has (Blizzard_UIPanels_Game LootFrame.xml,
-- ScrollingFlatPanel.xml): a 220 wide ScrollingFlatPanel window whose ScrollBox recycles one LootFrameItemElementTemplate row per
-- item (Item button, Text, QualityText, QualityStripe, NameFrame, BorderFrame, HighlightNameFrame) and one
-- LootFrameMoneyElementTemplate row for the coin. This file also holds the small kit that LootRolls.lua and GroupPopups.lua draw
-- with (FS.LootSkin: palette, pixel glyphs, cut card, item slot).
--
--   * the window wears the panel skin with a `stuwave://loot` band and the shared pink close key; the stock frame art, the title
--     and the scroll shadows are stripped or held, and the scroll bar takes the shared scroll bar skin;
--   * every row is a cut card (ink face, dim edge, top left and bottom right chamfer) with a LEFT QUALITY RAIL (a 2 px LED and a
--     6 px wash in the item's quality colour) and FIVE SIGNAL PIPS at its right edge lit to the quality, the mockup's rarity
--     ladder: one lit up to Common, two Uncommon, three Rare, four Epic, five Legendary; hover lights the edge cyan;
--   * the item button wears the shared slot layer (cut plate, quality LED, glint, lock) and its icon cropped, the name is mono on
--     a white base so the stock quality tint (a vertex colour) still shows, the rarity word is muted mono;
--   * a slot that is still inside a roll (the stock code reds its icon) swaps the pips for an amber die;
--   * the coin row is the same card with a gold rail and no pips.
--
-- Skin only, as in Commerce.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard frame,
-- post-hooks and alpha holds (FS.HeldArt) only, so every click, modified click, drag and tooltip stays stock. Names are the real
-- tree; each is feature-detected and a missing one is skipped. The rows are pooled: the stock code re-runs Init on a recycled
-- row, so the card repaints from a post-hook on Init and from the ScrollBox's own update.
--
-- Left out on purpose, because the mockup shows a display this client has no data for or a function the stock window does not
-- have ("keep the functionality the same as vanilla"): the take all key and its read head sweep (no such button in LootFrame.xml),
-- the bags meter and the bags full state, the coin strip as a separate header (the coin is its own row here), the corpse chip (the
-- window carries no mob name), the vendor price on grey items and the seconds left on a locked slot (computed), and the master
-- looter list (the retail master loot path is switched off in GroupLootFrame.lua).

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and PanelSkins.RequireExport(
    Theme.SkinPanel and Theme.ApplyMono and Theme.AddCut2Texture,
    "Loot.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local L = {}
FS.LootSkin = L

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, gold = Theme.COLOR_GOLD or { 1, 0.824, 0.247 },
    line = { 0.227, 0.129, 0.408 }, off = { 0.165, 0.094, 0.275 }, well = { 0.110, 0.063, 0.188 },
    steel = { 0.553, 0.576, 0.651 }, green = { 0.224, 1, 0.078 }, white = { 1, 1, 1 },
}
L.C = C

-- Item quality as the mockup draws it (the rarity ladder): Poor grey, Common near white, Uncommon green, Rare blue, Epic violet,
-- Legendary orange. Indexed by Enum.ItemQuality; anything above Legendary reads as Legendary.
L.Q = {
    [0] = { 0.616, 0.616, 0.616 }, [1] = { 0.953, 0.953, 0.953 }, [2] = { 0.118, 1, 0 },
    [3] = { 0.184, 0.549, 1 }, [4] = { 0.706, 0.361, 1 }, [5] = { 1, 0.502, 0 },
}

local Plain, Try, List = Kit.Plain, Kit.Try, Char.List

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { rows = Weak(), slots = Weak(), quality = Weak(), locked = Weak(), done = {} }
L.state = S

local function Step(name, fn, ...) return G.Step("loot", name, fn, ...) end
L.Step = Step

-- The quality of a value the client handed over, 0 to 5 (a missing or secret one reads as Common).
function L.QualityOf(q)
    q = Plain(q)
    if type(q) ~= "number" then return 1 end
    return math.max(0, math.min(5, math.floor(q)))
end

-------------------------------------------------------------------------------
-- Pixel glyphs: 16 x 16 bitmaps drawn as runs of one pixel tall rects, so they stay on the pixel grid at any scale
-------------------------------------------------------------------------------

local BITS = {
    die = {
        "................", "................", ".....#########..", "....#........#..", "...#.........#..", "..#.##....##.#..",
        "..#.##....##.#..", "..#....##....#..", "..#....##....#..", "..#.##....##.#..", "..#.##....##.#..", "..#.........#...",
        "..#........#....", "..#########.....", "................", "................",
    },
    coin = {
        "................", "................", "................", "....########....", "..##........##..", "..##........##..",
        "....########....", "..##........##..", "..##........##..", "....########....", "..##........##..", "..##........##..",
        "....########....", "................", "................", "................",
    },
    x = {
        "................", "................", "................", "................", "...##......##...", "....##....##....",
        ".....##..##.....", "......####......", ".......##.......", "......####......", ".....##..##.....", "....##....##....",
        "...##......##...", "................", "................", "................",
    },
    check = {
        "................", "................", "................", "................", "................", "............##..",
        "...........##...", "..........##....", "...##....##.....", "....##..##......", ".....####.......", "......##........",
        "................", "................", "................", "................",
    },
    star = {
        "................", "................", "................", ".......##.......", ".......##.......", "......#..#......",
        "..####....####..", "...#........#...", "....#......#....", ".....#....#.....", ".....#....#.....", ".....######.....",
        "....##....##....", "....#......#....", "................", "................",
    },
}
L.BITS = BITS

-- Draws the glyph `name` with its 16 x 16 box at (x, y) physical pixels from the `origin` corner of `host` (top left by default;
-- a negative x from TOPRIGHT, a negative y from BOTTOMLEFT); `scale` (default 1) draws each bitmap cell as a scale x scale block of
-- pixels. Returns { rects, shown, Paint(color, alpha), SetShown(bool) }.
function L.Glyph(host, name, x, y, color, layer, sub, origin, scale)
    local g = { rects = {}, shown = true, name = name }
    scale = scale or 1
    for r, line in ipairs(BITS[name] or {}) do
        local c = 1
        while c <= #line do
            if line:sub(c, c) == "#" then
                local e = c
                while line:sub(e + 1, e + 1) == "#" do e = e + 1 end
                local t = Kit.Rect(host, 0, 0, (e - c + 1) * scale, scale, color, 1, layer or "OVERLAY", sub or 5)
                Kit.Place(t, host, x + (c - 1) * scale, y + (r - 1) * scale, (e - c + 1) * scale, scale, "TOPLEFT", origin or "TOPLEFT", host)
                g.rects[#g.rects + 1] = t
                c = e + 1
            else
                c = c + 1
            end
        end
    end
    function g.Paint(col, alpha)
        for _, t in ipairs(g.rects) do t:SetColorTexture(col[1], col[2], col[3], alpha or col[4] or 1) end
    end
    function g.SetShown(v)
        g.shown = v and true or false
        for _, t in ipairs(g.rects) do t:SetShown(g.shown) end
    end
    return g
end

-------------------------------------------------------------------------------
-- Cut card and slot
-------------------------------------------------------------------------------

-- A cut plate (ink face, one pixel ring, top left and bottom right chamfer `c`) over the whole of `host`: its textures are
-- anchored to the host's corners, so it follows the host's size. Returns the plate (Kit.PaintPlate paints it).
function L.Card(host, c)
    local w, h = Kit.SizePx(host)
    return Kit.Plate(host, c or 4, w or 200, h or 46)
end

local SLOT_ART = { "NormalTexture", "IconBorder", "IconOverlay", "IconOverlay2", "ItemSlotBackground", "Background" }
local SLOT_GLOW = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture", "SearchOverlay" }

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(SLOT_ART) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(SLOT_GLOW) do HeldArt.Hold(button[f]) end
end

local function ReadSlot(button)
    local icon = Char.IconOf(button)
    local texture = icon and Plain(Try(icon.GetTexture, icon))
    return { quality = S.quality[button], empty = texture == nil or texture == "" or texture == 0, locked = S.locked[button] }
end

-- Skins one item button in place, the way Commerce.lua skins a vendor slot: the stock art held, the cut plate and ring of the
-- bags, the shared slot layer (quality LED, glint, hover, lock), the icon seated and cropped. `S.quality[button]` is what the slot
-- layer reads; a caller writes it before it asks for a refresh.
function L.ItemSlot(button, read)
    if type(button) ~= "table" or S.slots[button] then return end
    S.slots[button] = true
    SweepSlotArt(button)
    if type(Theme.AddCut2Texture) == "function" and Theme.SLICE_CUT2_BUTTON_TEXTURE then
        pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    local cut = Theme.SkinCutButton or Theme.SkinButton
    if cut then pcall(cut, button, { count = button.Count }) end
    local icon = Char.IconOf(button)
    if icon and type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, read or ReadSlot) and slotSkins.SeatIcon and icon then
        slotSkins.SeatIcon(button, icon)
    end
    Kit.HookFunc(button, "SetNormalTexture", function() SweepSlotArt(button) end)
end

function L.RefreshSlot(button)
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Refresh then slotSkins.Refresh(button) end
end

-------------------------------------------------------------------------------
-- Rows
-------------------------------------------------------------------------------

local ROW = { LED = 2, BAND = 6, LED_X = 1, LED_INSET = 8, PIP_W = 4, PIP_PITCH = 6, PIP_H0 = 6, PIP_STEP = 3, PIP_RIGHT = 8, PIP_BOTTOM = 10 }

local function IsLocked(row)
    if type(_G.GetLootSlotInfo) ~= "function" or type(row.GetSlotIndex) ~= "function" then return false end
    local slot = Plain(Try(row.GetSlotIndex, row))
    if type(slot) ~= "number" then return false end
    local ok, _, _, _, _, _, locked = pcall(_G.GetLootSlotInfo, slot)
    return ok and Plain(locked) == true
end

local function PaintRow(row)
    local rec = S.rows[row]
    if not rec then return end
    local money = rec.money
    local q = L.QualityOf(Try(row.GetQuality, row))
    local color = money and C.gold or L.Q[q]
    rec.ledColor = color
    rec.led.Paint(color, 1)
    rec.band.Paint(color, 0.18)
    local locked = not money and IsLocked(row)
    rec.locked = locked
    local lit = money and 0 or math.max(q, 1)
    rec.litCount = lit
    for j, pip in ipairs(rec.pips) do
        local c = j <= lit and color or C.off
        pip:SetColorTexture(c[1], c[2], c[3], 1)
        pip:SetShown(not money and not locked)
    end
    rec.die.SetShown(locked)
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Kit.PaintPlate(rec.plate, C.ink, 1, hover and C.cyan or C.line, 1, 1)
    if type(row.Item) == "table" then
        S.quality[row.Item] = money and 1 or q
        S.locked[row.Item] = locked
        L.RefreshSlot(row.Item)
    end
end

local function SkinRow(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    local item = row.Item
    if type(item) ~= "table" then return end
    for _, key in ipairs({ "NameFrame", "BorderFrame", "QualityStripe", "HighlightNameFrame", "PushedNameFrame", "IconQuestTexture" }) do
        HeldArt.Hold(row[key])
    end
    local rec = { money = type(row.QualityText) ~= "table", pips = {} }
    S.rows[row] = rec
    rec.plate = L.Card(row, 4)
    local inset = ROW.LED_INSET
    rec.band = G.Bar(row, C.gold, ROW.BAND, inset, ROW.LED_X)
    rec.led = G.Bar(row, C.gold, ROW.LED, inset, ROW.LED_X)
    for j = 1, 5 do
        local h = ROW.PIP_H0 + (j - 1) * ROW.PIP_STEP
        local t = Kit.Rect(row, 0, 0, ROW.PIP_W, h, C.off, 1, "OVERLAY", 4)
        local fromRight = ROW.PIP_RIGHT + (5 - j) * ROW.PIP_PITCH
        Kit.Place(t, row, -fromRight, -ROW.PIP_BOTTOM, ROW.PIP_W, h, "BOTTOMRIGHT", "BOTTOMRIGHT", row)
        rec.pips[j] = t
    end
    -- the die sits where the pips are: centred on the row's height, over the same stretch of its right edge
    rec.die = L.Glyph(row, "die", -(ROW.PIP_RIGHT + 5 * ROW.PIP_PITCH - 2 - 7), -8, C.amber, "OVERLAY", 4, "RIGHT")
    rec.die.SetShown(false)
    L.ItemSlot(item)
    G.Mono(row.Text, row, 11, C.white)
    if type(row.QualityText) == "table" then G.Mono(row.QualityText, row, 9, C.muted) end
    rec.state = Kit.Track(item, function() PaintRow(row) end)
    Kit.HookFunc(row, "Init", function() PaintRow(row) end)
    PaintRow(row)
end

-------------------------------------------------------------------------------
-- The window
-------------------------------------------------------------------------------

local SKIN = { fillColor = Theme.COLOR_BG, accent = C.violet, title = "loot" }

local function SkinWindow(win)
    if type(win) ~= "table" then return end
    PanelSkins.SkinPanelCached(win, SKIN)
    PanelSkins.HookShowOnce(win, "fsLootShowHooked", function(self) PanelSkins.SkinPanelCached(self, SKIN) end)
    local box = win.ScrollBox
    if type(box) == "table" then
        for _, getter in ipairs({ "GetUpperShadowTexture", "GetLowerShadowTexture" }) do
            if type(box[getter]) == "function" then HeldArt.Hold(Try(box[getter], box)) end
        end
    end
    if not S.done.sweep then
        S.done.sweep = true
        PanelSkins.SweepOnShow(win)
    end
    G.Rows(box, function(row) Step("row", SkinRow, row) end)
end

local function Build()
    Step("window", SkinWindow, G.Named("LootFrame"))
end

PanelSkins.RegisterInspect("Loot", { { name = "LootFrame", guard = "fsSkinCache" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
