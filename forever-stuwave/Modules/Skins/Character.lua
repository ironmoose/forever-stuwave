-- Forever STUwave: Character
-- The character window (CharacterFrame) as a STUwave window, from the approved CHARACTER mockup
-- (mockups/character-spells-2026-11-12.html, section 1), laid over the frame tree the 16001 client really has (readout:
-- debug/tree-CharacterFrame-2026-11-12.txt): a 631 x 484 window with LeftPaneHost (paper doll side) and RightPaneHost (stats),
-- PaperDollFrame (TopBackgroundStripHost, PaperDollLevelInfo, CharacterModelScene with ControlFrame, ItemsFrame with the slot
-- buttons), PaperDollSidebarTabs, RightPaneToggleButton, and CharacterFrameModeTabs: six round page tabs down the window's right
-- edge (Character, Reputation, Skills, PvP, Currency, Statistics).
--
--   * panel chrome in place of the stock frame art, and a header band on the stock top strip with a glyph and `stuwave://<page>`
--     (the page name follows whichever of the six sub frames is shown);
--   * the six ModeTabs are restyled in place (a cut plate, a cyan edge on hover, a pink edge and wash when selected): they are
--     the stock tabs, so all six pages work exactly as vanilla and there is no second switch;
--   * every equipment slot wears the shared item slot (a cut plate, the quality ring and LED of Core/ItemSlotSkins.lua, its icon
--     seated in the layer's inset box) and, new here, a WEAR BAR: a 2 px strip up the slot's right edge, as tall as the
--     durability left (cyan above half, amber to a fifth, pink under it, full pink when broken). Durability as a whole is not here;
--   * slot states: the stock pushed square and hover highlight are held (the shared slot layer draws the hover), a slot with
--     nothing in it takes a dim tint, and a broken piece gets a pink halo band three pixels wide around its plate;
--   * the equipment flyout (EquipmentFlyoutFrame: the gear a slot can take, the gear sets): the stock highlight ring desaturated
--     to cyan, the strip and navigation backgrounds held with our own boxes behind them, the page keys Quest.lua's cut keys, the
--     navigation text mono, and every item button seated as a square slot (buttons are made lazily and are met when shown);
--   * the stock level band, pane backgrounds, brown stat rows, gold category headers, model buttons, sidebar tabs and the right
--     pane toggle are held or restyled in place with every stock script and tooltip kept;
--   * a shared footer line under both panes (the window is made one footer taller) with chips for item level, average wear and
--     worn pieces, and the repair bill on the right, each read from a plain API value and left out when the client will not give one.
--
-- Skin only. Slots are secure item buttons: nothing on them is moved, resized, reparented or attributed, and no field is written
-- on them that UseContainerItem reads. Our regions, post-hooks and weak-keyed state only; the one resize is the window's own height
-- (outside combat, never a secure frame). A slot met in combat is decorated when combat ends. Values are read through FS.IsSecret
-- first. The shared helpers (HoldStock, RestyleFrame, SkinKey, SkinPage) are exported on FS.CharacterSkin for Skills, PvP,
-- Statistics, Reputation and Currency, which share the window.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the
-- durability model (the poles, the repair chip and hatching on the 3D model are not picked yet), wear brackets on the body and
-- the live trace from a hovered slot, stat change deltas after a gear swap, the title and gear set panes as rows, and the
-- tooltip changes.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit
if not (Theme and HeldArt and Kit and PanelSkins and PanelSkins.RequireExport(
    Theme.AddPanelChrome and Theme.StripBlizzardChrome and Theme.ApplyMono,
    "Character.lua disabled: FS.Theme chrome helpers, FS.HeldArt or FS.ControlKit missing")) then return end

local Char = {}
FS.CharacterSkin = Char

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, band = Theme.COLOR_CTRL_BAND or { 0.102, 0.051, 0.173 }, ink = Theme.COLOR_CTRL_INK,
    text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 }, panel = { 0.071, 0.039, 0.133, 0.96 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 },
}

-- FOOT_H: the footer band is 28 px under the window's last 29 (band and its rule). The stock weapon row hangs 30.8 units from the
-- window's bottom edge (about 37 px at 1.2) and the slot columns from its top, so at 40 px the rule ran through the weapons; at 28
-- the weapon row and the lowest side slots clear the rule by about the same 7 px, and the 20 px chips keep 4 px above and below.
local G = { FOOT_H = 28, CHIP_H = 20, CHIP_GAP = 8, SIDE = 14, WEAR_W = 2, WEAR_INSET = 4, WEAR_PAD = 6, HALO = 3 }
Char.GEOM = G

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = {
    done = false, slots = {}, chips = {}, decorated = Weak(), held = Weak(), watched = Weak(), details = Weak(), rules = Weak(),
    boxes = Weak(), tabs = Weak(), squares = Weak(), spans = {},
}
Char.state = S

-- Inventory slot name -> id (the paper doll's slot buttons are Character<name>Slot).
local SLOT_NAMES = {
    "Head", "Neck", "Shoulder", "Shirt", "Chest", "Waist", "Legs", "Feet", "Wrist", "Hands", "Finger0", "Finger1",
    "Trinket0", "Trinket1", "Back", "MainHand", "SecondaryHand", "Ranged", "Tabard",
}
local SLOT_ID = {
    Head = 1, Neck = 2, Shoulder = 3, Shirt = 4, Chest = 5, Waist = 6, Legs = 7, Feet = 8, Wrist = 9, Hands = 10,
    Finger0 = 11, Finger1 = 12, Trinket0 = 13, Trinket1 = 14, Back = 15, MainHand = 16, SecondaryHand = 17, Ranged = 18,
    Tabard = 19,
}
Char.SLOT_NAMES = SLOT_NAMES

local function Plain(v) return Kit.Plain(v) end
local function Try(fn, ...) return Kit.Try(fn, ...) end
local function InCombat() return type(InCombatLockdown) == "function" and InCombatLockdown() end

-------------------------------------------------------------------------------
-- Readings
-------------------------------------------------------------------------------

-- Durability left of an inventory slot of `unit` as a fraction 0..1, nil when it has none or it is not a plain number.
function Char.WearOf(slotId, unit)
    if unit and unit ~= "player" then return nil end
    if type(_G.GetInventoryItemDurability) ~= "function" then return nil end
    local cur, max = Try(_G.GetInventoryItemDurability, slotId)
    cur, max = Plain(cur), Plain(max)
    if type(cur) ~= "number" or type(max) ~= "number" or max <= 0 then return nil end
    return math.max(0, math.min(1, cur / max))
end

-- Wear colour: cyan above half, amber to a fifth, pink under it.
function Char.WearColor(frac)
    if frac > 0.5 then return C.cyan end
    if frac >= 0.2 then return C.amber end
    return C.pink
end

-- Average wear (0..100), the number of worn pieces and the repair bill in copper, over the paper doll slots. Each is nil when the
-- client would not say.
function Char.Totals()
    local sum, n, worn, cost, costKnown = 0, 0, 0, 0, false
    for _, name in ipairs(SLOT_NAMES) do
        local id = SLOT_ID[name]
        local frac = Char.WearOf(id)
        if frac then
            sum, n = sum + frac, n + 1
            if frac < 1 then
                worn = worn + 1
                local info = type(_G.C_TooltipInfo) == "table" and Try(_G.C_TooltipInfo.GetInventoryItem, "player", id)
                local repair = type(info) == "table" and Plain(info.repairCost)
                if type(repair) == "number" then cost, costKnown = cost + repair, true end
            end
        end
    end
    if n == 0 then return nil end
    return math.floor(sum / n * 100 + 0.5), worn, costKnown and cost or nil
end

function Char.CoinText(copper)
    local g, s, c = math.floor(copper / 10000), math.floor(copper / 100) % 100, copper % 100
    local parts = {}
    if g > 0 then parts[#parts + 1] = g .. "g" end
    if s > 0 or g > 0 then parts[#parts + 1] = s .. "s" end
    parts[#parts + 1] = c .. "c"
    return table.concat(parts, " ")
end

local function ItemLevel()
    if type(_G.GetAverageItemLevel) ~= "function" then return nil end
    local avg, equipped = Try(_G.GetAverageItemLevel)
    equipped = Plain(equipped)
    if type(equipped) ~= "number" then equipped = Plain(avg) end
    if type(equipped) ~= "number" then return nil end
    return math.floor(equipped + 0.5)
end

-------------------------------------------------------------------------------
-- Equipment slots
-------------------------------------------------------------------------------

local ART_FIELDS = { "NormalTexture", "IconBorder", "IconOverlay", "IconOverlay2", "ItemSlotBackground", "Background" }
local GLOW_FIELDS = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture", "SearchOverlay" }

local function IconOf(button)
    local icon = button.icon
    if type(icon) ~= "table" then icon = button.Icon end
    if type(icon) ~= "table" then
        local name = Try(button.GetName, button)
        if type(name) == "string" then icon = _G[name .. "IconTexture"] end
    end
    return type(icon) == "table" and icon or nil
end
Char.IconOf = IconOf

-- The slot's own pressed art and hover highlight (keyed regions on the 16001 slot): the shared slot layer draws the hover, so the
-- stock square highlight and pressed square are held with the rest.
local STATE_FIELDS = { "PushedTexture", "HighlightTexture" }
local STATE_GETTERS = { "GetPushedTexture", "GetHighlightTexture" }

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(ART_FIELDS) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(GLOW_FIELDS) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(STATE_FIELDS) do HeldArt.Hold(button[f]) end
    for _, getter in ipairs(STATE_GETTERS) do
        if type(button[getter]) == "function" then
            local ok, region = pcall(button[getter], button)
            if ok then HeldArt.Hold(region) end
        end
    end
end

-- A wear bar and a broken ring on a slot: our own regions on the button, laid out from the slot's own pixel size.
local function WearParts(button)
    local w = S.slots[button]
    if w.bar then return w end
    w.bar = Kit.Rect(button, 0, 0, G.WEAR_W, 1, C.cyan, 1, "OVERLAY", 4)
    w.bar:Hide()
    w.track = Kit.Rect(button, 0, 0, G.WEAR_W, 1, C.ink, 0.6, "OVERLAY", 3)
    w.track:Hide()
    -- the broken halo: a pink band HALO px wide around the slot, behind its plate
    w.halo = Kit.Rect(button, 0, 0, 1, 1, C.pink, 0.32, "BACKGROUND", -8)
    w.halo:Hide()
    return w
end

-- Paints the wear of the slot now: hidden at full durability and for a slot with none.
function Char.PaintWear(button)
    local w = S.slots[button]
    if not w then return end
    local parts = WearParts(button)
    local frac = w.id and Char.WearOf(w.id, w.unit)
    if not frac or frac >= 1 then
        parts.bar:Hide()
        parts.track:Hide()
        parts.halo:Hide()
        return
    end
    local pw, ph = Kit.SizePx(button)
    if not pw then return end
    if frac <= 0 then
        Kit.Move(parts.halo, -G.HALO, -G.HALO, pw + 2 * G.HALO, ph + 2 * G.HALO)
        parts.halo:Show()
    else
        parts.halo:Hide()
    end
    local top, full = G.WEAR_PAD, ph - 2 * G.WEAR_PAD
    local h = frac <= 0 and full or math.max(1, math.floor(full * frac + 0.5))
    local x = pw - G.WEAR_INSET - G.WEAR_W
    Kit.Move(parts.track, x, top, G.WEAR_W, full)
    Kit.Move(parts.bar, x, top + full - h, G.WEAR_W, h)
    local color = Char.WearColor(frac)
    parts.bar:SetColorTexture(color[1], color[2], color[3], 1)
    parts.bar:Show()
    parts.track:Show()
end

local function ReadSlot(unit)
    return function(button)
        local w = S.slots[button]
        local id = w and w.id
        if not id then return {} end
        local unit = type(unit) == "function" and unit() or unit
        local quality = _G.GetInventoryItemQuality and Try(_G.GetInventoryItemQuality, unit, id)
        local texture = _G.GetInventoryItemTexture and Try(_G.GetInventoryItemTexture, unit, id)
        return { quality = quality, empty = texture == nil }
    end
end

-- An empty slot shows the stock silhouette of what goes there; it is tinted dim violet, and goes back to white once an item is
-- seated (only a tint of ours is ever undone).
local function PaintEmpty(button)
    local w = S.slots[button]
    local icon = IconOf(button)
    if not (w and icon and type(icon.SetVertexColor) == "function") then return end
    local ok, info = pcall(ReadSlot(w.unit), button)
    if not ok or type(info) ~= "table" then return end
    if info.empty then
        w.tinted = true
        pcall(icon.SetVertexColor, icon, C.dim[1], C.dim[2], C.dim[3], 1)
    elseif w.tinted then
        w.tinted = false
        pcall(icon.SetVertexColor, icon, 1, 1, 1, 1)
    end
end

-- Skins one equipment slot button in place. `unit` is "player" for the paper doll, or a function that answers the unit now (the
-- inspected one); only the player's own slots have wear. Idempotent.
function Char.SkinSlot(button, slotId, unit)
    if type(button) ~= "table" or S.slots[button] then return end
    unit = unit or "player"
    S.slots[button] = { id = slotId, unit = unit }
    SweepSlotArt(button)
    -- The bronze gear-slot ring (UI-Character-Info-GearSlot) lives on a BorderFrame child, out of reach of the region sweep.
    Kit.HoldFrame(button.BorderFrame)
    if type(Theme.AddCut2Texture) == "function" and Theme.SLICE_CUT2_BUTTON_TEXTURE then
        pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    local cut = Theme.SkinCutButton or Theme.SkinButton
    if cut then pcall(cut, button, { count = button.Count }) end
    local icon = IconOf(button)
    if icon and type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, 0.07, 0.93, 0.07, 0.93) end
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, ReadSlot(unit)) and slotSkins.SeatIcon and icon then
        slotSkins.SeatIcon(button, icon)
    end
    Kit.HookFunc(button, "SetNormalTexture", function() SweepSlotArt(button) end)
    Kit.HookScript(button, "OnSizeChanged", function() Char.PaintWear(button) end)
    if icon then Kit.HookFunc(icon, "SetTexture", function() PaintEmpty(button) end) end
    Char.PaintWear(button)
    PaintEmpty(button)
end

local function RefreshSlots()
    for button in pairs(S.slots) do
        Char.PaintWear(button)
        PaintEmpty(button)
        if FS.ItemSlotSkins and FS.ItemSlotSkins.Refresh then FS.ItemSlotSkins.Refresh(button) end
    end
end

local function SkinSlots()
    for _, name in ipairs(SLOT_NAMES) do
        local button = _G["Character" .. name .. "Slot"]
        if button then Char.SkinSlot(button, SLOT_ID[name], "player") end
    end
end


local function PinColor(fs, color)
    if S.held[fs] or type(fs.SetTextColor) ~= "function" then return end
    S.held[fs] = true
    fs:SetTextColor(color[1], color[2], color[3], 1)
    if type(hooksecurefunc) ~= "function" then return end
    local busy = false
    pcall(hooksecurefunc, fs, "SetTextColor", function(self, r, g, b)
        if busy or (r == color[1] and g == color[2] and b == color[3]) then return end
        busy = true
        pcall(self.SetTextColor, self, color[1], color[2], color[3], 1)
        busy = false
    end)
end

-------------------------------------------------------------------------------
-- Shared helpers (every page of this window uses them)
-------------------------------------------------------------------------------

local function List(obj, method)
    if type(obj) ~= "table" or type(obj[method]) ~= "function" then return {} end
    local ok, out = pcall(function() return { obj[method](obj) } end)
    return ok and out or {}
end

local function AtlasOf(region)
    if type(region) ~= "table" or type(region.GetAtlas) ~= "function" then return nil end
    local a = Plain(Try(region.GetAtlas, region))
    return type(a) == "string" and a or nil
end

-- The stock art of this window's pages is told by its atlas name: nothing here has a parentKey or a name to go by.
local STOCK_ATLAS = {
    "^UI%-Character%-Info", "^common%-framedivider", "^common%-insideframe", "^common%-sidetab", "^common%-button%-list",
    "^common%-button%-square", "^common%-stat%-bar%-BG",
}
-- Stock art that is information, not decoration: the plus and minus of a header, the honor badge and its reward ring.
local KEEP_ATLAS = { "list%-minus", "list%-plus", "Honor%-Icon", "Honor%-Bar%-BG%-", "RewardRing" }

local function IsStockAtlas(atlas)
    for _, p in ipairs(KEEP_ATLAS) do if atlas:find(p) then return false end end
    for _, p in ipairs(STOCK_ATLAS) do if atlas:find(p) then return true end end
    return false
end

-- Holds every texture of `frame` and of its sub frames (down to `depth`, scroll bars left out) whose atlas is stock art of this
-- window. Idempotent; the hold is a SetAlpha hook, so recycled rows keep it.
function Char.HoldStock(frame, depth)
    depth = depth or 0
    if type(frame) ~= "table" or depth > 7 then return end
    for _, region in ipairs(List(frame, "GetRegions")) do
        if Try(region.GetObjectType, region) == "Texture" then
            local atlas = AtlasOf(region)
            if atlas and IsStockAtlas(atlas) then HeldArt.Hold(region) end
        end
    end
    for _, child in ipairs(List(frame, "GetChildren")) do
        if type(child) == "table" and child.Track == nil then Char.HoldStock(child, depth + 1) end
    end
end

local FONT_KEYS = {
    Title = { 12, "cyan" }, Subtitle = { 12, "muted" }, EmptyText = { 12, "muted" },
    Name = { 12, "text" }, Label = { 12, "muted" }, Value = { 12, "text" },
}

-- Restyles the text keys a stock row or pane carries (Title, Name, Label, Value ...) in mono, colour pinned.
function Char.RestyleFonts(frame)
    if type(frame) ~= "table" then return end
    for key, spec in pairs(FONT_KEYS) do
        local fs = frame[key]
        if type(fs) == "table" and Try(fs.GetObjectType, fs) == "FontString" then
            Kit.RestyleLabel(fs, frame, spec[1], C[spec[2]])
            PinColor(fs, C[spec[2]])
        end
    end
end

-- A row of one of the pages: its stock art held, its header glyph tinted, its texts in mono.
function Char.PageRow(row)
    if type(row) ~= "table" then return end
    Char.HoldStock(row, 5)
    local icon = row.StateIcon
    if type(icon) == "table" and icon.SetVertexColor then pcall(icon.SetVertexColor, icon, C.cyan[1], C.cyan[2], C.cyan[3], 1) end
    Char.RestyleFonts(row)
end

-- Runs `fn(row)` on every row now and after every update of the ScrollBox `box`.
function Char.WatchRows(box, fn)
    if type(box) ~= "table" or S.watched[box] then return end
    S.watched[box] = true
    local function run()
        if type(box.ForEachFrame) == "function" then
            pcall(box.ForEachFrame, box, function(row) pcall(fn, row) end)
        end
    end
    for _, method in ipairs({ "Update", "FullUpdate", "SetDataProvider" }) do
        Kit.HookFunc(box, method, function() run() end)
    end
    Kit.HookScript(box, "OnShow", function() Kit.Later(run) end)
    run()
end

-- A detail pane (the right hand pane of reputation, skills and pvp): chrome art held, texts and its bar in STUwave.
function Char.SkinDetail(detail)
    if type(detail) ~= "table" or S.details[detail] then return end
    S.details[detail] = true
    Char.HoldStock(detail, 2)
    Char.RestyleFonts(detail)
    for _, key in ipairs({ "StandingBar", "RankBar" }) do
        local bar = detail[key]
        if type(bar) == "table" and bar.CreateTexture then
            local track = bar:CreateTexture(nil, "BACKGROUND", nil, -6)
            track:SetAllPoints(bar)
            track:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.9)
        end
    end
end

-------------------------------------------------------------------------------
-- Boxes: a fill and a ring of rects that follows a stock widget's size
-------------------------------------------------------------------------------

local function LayoutBox(b)
    local u = Kit.U(b.host, b.px or 1)
    local e, h = b.edges, b.ref or b.host
    e[1]:ClearAllPoints(); e[1]:SetPoint("TOPLEFT", h, "TOPLEFT", 0, 0); e[1]:SetPoint("TOPRIGHT", h, "TOPRIGHT", 0, 0); e[1]:SetHeight(u)
    e[2]:ClearAllPoints(); e[2]:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", 0, 0); e[2]:SetPoint("BOTTOMRIGHT", h, "BOTTOMRIGHT", 0, 0); e[2]:SetHeight(u)
    e[3]:ClearAllPoints(); e[3]:SetPoint("TOPLEFT", h, "TOPLEFT", 0, 0); e[3]:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", 0, 0); e[3]:SetWidth(u)
    e[4]:ClearAllPoints(); e[4]:SetPoint("TOPRIGHT", h, "TOPRIGHT", 0, 0); e[4]:SetPoint("BOTTOMRIGHT", h, "BOTTOMRIGHT", 0, 0); e[4]:SetWidth(u)
end

-- `ref` (a frame or a texture) is what the box follows when it is not `host` itself; the textures are `host`'s.
local function Box(host, edgeLayer, ref)
    local b = { host = host, ref = ref, edges = {}, px = 1 }
    b.fill = host:CreateTexture(nil, "BACKGROUND", nil, -7)
    b.fill:SetAllPoints(ref or host)
    for i = 1, 4 do
        local t = host:CreateTexture(nil, edgeLayer or "OVERLAY", nil, 6)
        t:SetColorTexture(1, 1, 1, 1)
        b.edges[i] = t
    end
    LayoutBox(b)
    S.boxes[b] = true
    return b
end

local function PaintBox(b, fill, fa, edge, ea, px)
    b.fill:SetColorTexture(fill[1], fill[2], fill[3], fa or 1)
    for _, t in ipairs(b.edges) do t:SetColorTexture(edge[1], edge[2], edge[3], ea or 1) end
    if px and px ~= b.px then b.px = px; LayoutBox(b) end
end

local function ShownRegion(region)
    return type(region) == "table" and Try(region.IsShown, region) == true
end

-- Follows a texture region's shown state (the stock selected glow of a tab).
local function WatchShown(region, fn)
    for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(region, m, fn) end
end

-------------------------------------------------------------------------------
-- Mode tabs: the six round page tabs down the window's right edge, restyled in place
-------------------------------------------------------------------------------

local function PaintTab(tab)
    local t = S.tabs[tab]
    if not t then return end
    local sel = ShownRegion(tab.SelectedTexture)
    local hover = t.state and t.state.hover
    if sel then PaintBox(t.box, C.band, 1, C.pink, 1, 2)
    elseif hover then PaintBox(t.box, C.ink, 1, C.cyan, 1, 1)
    else PaintBox(t.box, C.ink, 1, C.dim, 1, 1) end
    local icon = tab.Icon
    if type(icon) == "table" and icon.SetVertexColor then
        local v = (sel or hover) and 1 or 0.72
        pcall(icon.SetVertexColor, icon, v, v, v, 1)
    end
end

local function SkinModeTab(tab)
    if type(tab) ~= "table" or S.tabs[tab] then return end
    S.tabs[tab] = { box = Box(tab) }
    for _, key in ipairs({ "Background", "SelectedTexture", "TabGlow", "HighlightTexture" }) do HeldArt.Hold(tab[key]) end
    S.tabs[tab].state = Kit.Track(tab, PaintTab)
    if tab.SelectedTexture then WatchShown(tab.SelectedTexture, function() PaintTab(tab) end) end
    PaintTab(tab)
end

local function SkinModeTabs()
    for i = 1, 6 do SkinModeTab(_G["CharacterFrameModeTab" .. i]) end
end

-------------------------------------------------------------------------------
-- Small square buttons: model zoom and rotate, the sidebar tabs, the right pane toggle
-------------------------------------------------------------------------------

local function PaintSquare(btn)
    local s = S.squares[btn]
    if not s then return end
    local sel = s.selected and s.selected() or false
    local hover = s.state and s.state.hover
    local pressed = s.state and s.state.pressed
    local edge = sel and C.pink or ((hover or pressed) and C.cyan or C.dim)
    local on = true
    if s.plate then
        on = Kit.IsEnabled(btn)
        Kit.PaintPlate(s.plate, sel and C.band or C.ink, 1, on and edge or C.dim, on and 1 or 0.6, sel and 2 or 1)
    else
        PaintBox(s.box, sel and C.band or C.ink, 1, edge, 1, sel and 2 or 1)
    end
    local tint = s.tint and ((hover or pressed or sel) and C.text or s.tint)
    if s.icon and tint and s.icon.SetVertexColor then pcall(s.icon.SetVertexColor, s.icon, tint[1], tint[2], tint[3], 1) end
    if s.glyph then
        local g = (hover or pressed) and C.text or C.cyan
        for _, t in ipairs(s.glyph) do
            t:SetColorTexture(g[1], g[2], g[3], 1)
            if s.plate then t:SetAlpha(on and 1 or 0.35) end
        end
    end
end

local function SkinSquare(btn, opts)
    if type(btn) ~= "table" or S.squares[btn] then return nil end
    opts = opts or {}
    -- The stock art is held BEFORE the box is made: HeldArt.HoldButton holds every region the button has at that moment, so a box
    -- built first would be zeroed with the rest and stay invisible.
    HeldArt.HoldButton(btn, opts.icon and { [opts.icon] = true } or nil)
    local s = { box = Box(btn), icon = opts.icon, tint = opts.tint, selected = opts.selected }
    S.squares[btn] = s
    s.state = Kit.Track(btn, PaintSquare)
    return s
end

-- Cells of a glyph, {x, y, w, h} px each on a gw x gh px grid hung from the MIDDLE of `btn`: the grid's own middle is the button's, so
-- the glyph is centred whatever size the stock button reported when it was skinned (the pixel scale is not settled yet when the
-- skin is built, and an offset worked out from that size stays wrong). Even grids, so the middle falls between two pixels.
local function Cells(btn, gw, gh, cells)
    local out = {}
    local ox, oy = math.floor(gw / 2), math.floor(gh / 2)
    for _, c in ipairs(cells) do
        local t = Kit.Rect(btn, 0, 0, c[3], c[4], C.cyan, 1, "OVERLAY", 7)
        Kit.Place(t, btn, c[1] - ox, c[2] - oy, c[3], c[4], "TOPLEFT", "CENTER", btn)
        out[#out + 1] = t
    end
    return out
end

-- A cut key `size` px square seated on the middle of a stock button (CENTER to CENTER) with a cell glyph, the stock art held first
-- (a plate made before it would be held invisible with the rest). The stock button keeps its size, script and hit rectangle; the key
-- is smaller than it, which is how the model's zoom and rotate buttons (32 units wide, 25.5 apart, so they overlap) get a gap
-- between them. Painted by PaintSquare, with the hover, press and disabled states of the stock button.
local KEY = { SIZE = 26, CUT = 3 }

local function SkinKey(btn, gw, gh, cells)
    if type(btn) ~= "table" or type(btn.CreateTexture) ~= "function" or S.squares[btn] then return nil end
    HeldArt.HoldButton(btn)
    local plate = Kit.Plate(btn, KEY.CUT, KEY.SIZE, KEY.SIZE)
    for _, part in ipairs({ plate.fill, plate.ring }) do
        Kit.Place(part, btn, 0, 0, KEY.SIZE, KEY.SIZE, "CENTER", "CENTER", btn)
    end
    if plate.ring2 then Kit.Place(plate.ring2, btn, 0, 0, KEY.SIZE - 2, KEY.SIZE - 2, "CENTER", "CENTER", btn) end
    local s = { plate = plate, glyph = Cells(btn, gw, gh, cells) }
    S.squares[btn] = s
    s.state = Kit.Track(btn, PaintSquare)
    PaintSquare(btn)
    return s
end

-- The glyphs of the model's keys: a plus and a minus for the zoom, an arrow each way for the turn, a ring with a dot for the reset.
local ARROW_HEAD = { { 4, 0, 2, 2 }, { 2, 2, 2, 2 }, { 0, 4, 2, 2 }, { 2, 6, 2, 2 }, { 4, 8, 2, 2 } }
local function RightArrow()
    local out = { { 0, 4, 12, 2 } }
    for _, c in ipairs(ARROW_HEAD) do out[#out + 1] = { 12 - c[1], c[2], c[3], c[4] } end
    return out
end
local function LeftArrow()
    local out = { { 2, 4, 12, 2 } }
    for _, c in ipairs(ARROW_HEAD) do out[#out + 1] = c end
    return out
end
local MODEL_KEYS = {
    { "zoomInButton", 14, 14, { { 0, 6, 14, 2 }, { 6, 0, 2, 14 } } },
    { "zoomOutButton", 14, 14, { { 0, 6, 14, 2 } } },
    { "rotateLeftButton", 14, 10, LeftArrow() },
    { "rotateRightButton", 14, 10, RightArrow() },
    { "resetButton", 12, 12, { { 2, 0, 8, 2 }, { 2, 10, 8, 2 }, { 0, 2, 2, 8 }, { 10, 2, 2, 8 }, { 5, 5, 2, 2 } } },
}

local function SkinModelControls()
    local scene = _G.CharacterModelScene
    local control = scene and scene.ControlFrame
    if not control then return end
    for _, def in ipairs(MODEL_KEYS) do
        local b = control[def[1]]
        if b and SkinKey(b, def[2], def[3], def[4]) then PaintSquare(b) end
    end
end

local function SelectedRegionOf(btn)
    for _, region in ipairs(List(btn, "GetRegions")) do
        local atlas = AtlasOf(region)
        if atlas and atlas:find("Selected") then return region end
    end
    return nil
end

local function SkinSidebarTabs()
    for i = 1, 4 do
        local btn = _G["PaperDollSidebarTab" .. i]
        if btn and not S.squares[btn] then
            local sel = SelectedRegionOf(btn)
            local s = SkinSquare(btn, { icon = btn.Icon, tint = { 0.8, 0.8, 0.8 }, selected = function() return ShownRegion(sel) end })
            if s then
                if sel then WatchShown(sel, function() PaintSquare(btn) end) end
                Kit.HookFunc(btn, "SetChecked", function() PaintSquare(btn) end)
                PaintSquare(btn)
            end
        end
    end
end

local function SkinToggle()
    local btn = _G.CharacterFrameRightPaneToggleButton
    if not btn or S.squares[btn] then return end
    local s = SkinSquare(btn, {})
    if not s then return end
    -- the pane glyph: a frame with a bar down its right side, 18 x 14 px, hung from the middle of the key
    local gw, gh = 18, 14
    s.glyph = Cells(btn, gw, gh, { { 0, 0, gw, 2 }, { 0, gh - 2, gw, 2 }, { 0, 0, 2, gh }, { gw - 2, 0, 2, gh }, { gw - 7, 2, 2, gh - 4 } })
    PaintSquare(btn)
end

-------------------------------------------------------------------------------
-- The equipment flyout (EquipmentFlyoutFrame)
-------------------------------------------------------------------------------

-- The popup of the gear a slot can take (also the gear sets and the profession tool slots): the frame holds the highlight ring of
-- the slot it opened from (Highlight), a buttonFrame with the leather strip behind the item buttons (bg1, bg2 ... the stock code
-- adds textures as the list grows), a NavigationFrame (BottomBackground, the stock PREVIOUS and NEXT, PrevButton, NextButton) and
-- the item buttons EquipmentFlyoutFrameButtonN, made the first time they are needed. Met again after every stock UpdateItems and
-- Show (post-hooks on the globals), which is also when the strip textures and the buttons exist.

local function SkinFlyout()
    local fly = _G.EquipmentFlyoutFrame
    if type(fly) ~= "table" then return end
    local hi = fly.Highlight
    if type(hi) == "table" then
        if type(hi.SetDesaturated) == "function" then pcall(hi.SetDesaturated, hi, true) end
        if type(hi.SetVertexColor) == "function" then pcall(hi.SetVertexColor, hi, C.cyan[1], C.cyan[2], C.cyan[3], 1) end
    end
    local bf = fly.buttonFrame
    if type(bf) == "table" then
        local n = Plain(bf.numBGs)
        for i = 1, math.max(type(n) == "number" and n or 1, 1) + 1 do HeldArt.Hold(bf["bg" .. i]) end
        if not S.flyBox and type(bf.CreateTexture) == "function" then
            S.flyBox = Box(bf, "BORDER")
            PaintBox(S.flyBox, C.ink, 0.96, C.violet, 1, 1)
        end
    end
    local nav = fly.NavigationFrame
    local Q = FS.QuestSkin
    if type(nav) == "table" then
        HeldArt.Hold(nav.BottomBackground)
        if not S.flyNav and type(nav.CreateTexture) == "function" then
            S.flyNav = Box(nav, "BORDER")
            PaintBox(S.flyNav, C.ink, 0.96, C.violet, 1, 1)
        end
        if Q and Q.PagerKey then
            Q.PagerKey(nav.PrevButton, "<")
            Q.PagerKey(nav.NextButton, ">")
        end
        for _, region in ipairs(List(nav, "GetRegions")) do
            if Try(region.GetObjectType, region) == "FontString" then
                Kit.RestyleLabel(region, nav, 11, C.muted)
                PinColor(region, C.muted)
            end
        end
    end
    -- the item buttons are square item buttons: the slot of the trade window and the bags (Quest.lua's SquareSlot)
    if Q and Q.SquareSlot and type(fly.buttons) == "table" then
        for _, btn in ipairs(fly.buttons) do Q.SquareSlot(btn) end
    end
end

-------------------------------------------------------------------------------
-- Stat rows
-------------------------------------------------------------------------------

local function StatRow(row)
    if type(row) ~= "table" then return end
    HeldArt.Hold(row.Background)
    Char.RestyleFonts(row)
    if not S.rules[row] and row.CreateTexture then
        local rule = row:CreateTexture(nil, "BORDER")
        rule:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 0, 0)
        rule:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", 0, 0)
        S.rules[row] = rule
    end
    local rule = S.rules[row]
    if rule then
        local title = row.Title ~= nil
        local color = title and C.violet or C.dim
        rule:SetColorTexture(color[1], color[2], color[3], title and 0.9 or 0.4)
        rule:SetHeight(Kit.U(row, 1))
    end
end

local function SkinStats()
    for _, name in ipairs({ "CharacterStatsPaneScrollBox", "CharacterStatsPanePetScrollBox" }) do
        local pane = _G[name]
        if pane then
            Char.HoldStock(pane, 0)
            HeldArt.Hold(pane.Border)
            HeldArt.Hold(pane.ClassBackground)
            Char.WatchRows(pane.ScrollBox, StatRow)
        end
    end
    local paper = _G.PaperDollFrame
    if paper then
        Char.HoldStock(paper.TitleManagerPane, 4)
        Char.HoldStock(paper.EquipmentManagerPane, 4)
    end
end

-------------------------------------------------------------------------------
-- Header
-------------------------------------------------------------------------------

local PAGES = {
    { label = "character", frame = "PaperDollFrame" },
    { label = "reputation", frame = "ReputationFrame" },
    { label = "skills", frame = "SkillsFrame" },
    { label = "pvp", frame = "PVPRankFrame" },
    { label = "currency", frame = "TokenFrame" },
    { label = "statistics", frame = "StatisticsFrame" },
}

local function ShownPage()
    for i, page in ipairs(PAGES) do
        local f = _G[page.frame]
        if f and Try(f.IsShown, f) == true then return i end
    end
    return 1
end

function Char.RefreshHeader()
    local h = S.header
    if not h then return end
    h.title:SetText("stuwave://" .. PAGES[ShownPage()].label)
end

-- The height of the stock strip above the panes, in UI units: measured from the frames, 24 when they will not say.
local function TopGapUnits(win)
    local pane = _G.CharacterFrameLeftPaneHost
    local a = Plain(Try(win.GetTop, win))
    local b = pane and Plain(Try(pane.GetTop, pane))
    if type(a) == "number" and type(b) == "number" and a - b >= 8 and a - b <= 80 then return a - b end
    return 24
end

-- A person glyph from one pixel runs: head and shoulders, `k` pixels per run unit.
local function Glyph(win, x, y, k, color)
    local out = {}
    local runs = { { 4, 0, 6, 2 }, { 3, 2, 8, 4 }, { 0, 7, 14, 2 }, { 0, 9, 14, 7 } }
    for _, r in ipairs(runs) do out[#out + 1] = Kit.Rect(win, x + r[1] * k, y + r[2] * k, r[3] * k, r[4] * k, color, 1, "OVERLAY", 3) end
    return out
end

-- A rect that spans the width of `host` from `y` px down, `h` px tall: two anchors, so it follows a window that changes width.
local function Span(host, parent, y, h, color, alpha, layer, sub, fromBottom)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    Kit.Snap(t)
    local rec = { t = t, host = host, y = y, h = h, bottom = fromBottom }
    local function apply()
        local k = Kit.U(host, 1)
        t:ClearAllPoints()
        if rec.bottom then
            t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", 0, rec.y * k)
            t:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", 0, rec.y * k)
        else
            t:SetPoint("TOPLEFT", host, "TOPLEFT", 0, -rec.y * k)
            t:SetPoint("TOPRIGHT", host, "TOPRIGHT", 0, -rec.y * k)
        end
        t:SetHeight(rec.h * k)
    end
    rec.apply = apply
    S.spans[#S.spans + 1] = rec
    apply()
    return t
end

local function BuildHeader(win)
    local gap = TopGapUnits(win)
    local headPx = math.max(24, math.ceil(gap * Kit.Ppu(win)))
    S.headPx = headPx
    local band = Span(win, win, 1, headPx - 1, C.band, 1, "ARTWORK", 0)
    local rule = Span(win, win, headPx, 1, C.violet, 1, "ARTWORK", 1)
    local k = headPx >= 36 and 2 or 1
    local glyph = Glyph(win, 12, math.floor((headPx - 16 * k) / 2), k, C.cyan)
    local title = Kit.Label(win, "stuwave://character", headPx >= 36 and 16 or 13, C.muted, "OVERLAY")
    Kit.Place(title, win, 12 + 14 * k + 10, math.floor(headPx / 2), nil, nil, "LEFT", "TOPLEFT")
    title:SetJustifyH("LEFT")
    S.header = { title = title, band = { band, rule }, glyph = glyph }

    Kit.HoldFrame(_G.CharacterFrameTitleText)
    HeldArt.Hold(_G.CharacterFramePortrait)
    if Theme.SkinCloseButton then pcall(Theme.SkinCloseButton, win) end
    for _, page in ipairs(PAGES) do
        Kit.HookScript(_G[page.frame], "OnShow", function() Char.RefreshHeader(); Char.RefreshChips(); Char.RefreshLevel() end)
    end
    Char.RefreshHeader()
end

-- The stock strip under the header (it carries the level line): held, with our own band under it.
local function SkinTopStrip()
    local paper = _G.PaperDollFrame
    local host = paper and paper.TopBackgroundStripHost
    if host then
        HeldArt.Hold(host.TopBackgroundStrip)
        HeldArt.Hold(host.TopBackgroundStripBottomEdge)
        if not S.stripUnder and host.CreateTexture then
            S.stripUnder = Span(host, host, 0, 1, C.band, 1, "BACKGROUND", -5)
            S.stripUnder:ClearAllPoints()
            S.stripUnder:SetAllPoints(host)
            S.stripRule = Span(host, host, 0, 1, C.dim, 1, "BORDER", 1, true)
        end
    end
    local level = _G.CharacterLevelText
    if level then Kit.RestyleLabel(level, level, 12, C.amber); PinColor(level, C.amber) end
end

-------------------------------------------------------------------------------
-- Panes
-------------------------------------------------------------------------------

local function SkinPanes()
    local left, right = _G.CharacterFrameLeftPaneHost, _G.CharacterFrameRightPaneHost
    if left then Char.HoldStock(left, 0) end
    if right then
        Char.HoldStock(right, 3)
        HeldArt.Hold(_G.CharacterFrameRightPaneHostStoneBg)
        if not S.rightUnder and right.CreateTexture then
            S.rightUnder = right:CreateTexture(nil, "BACKGROUND", nil, -6)
            S.rightUnder:SetAllPoints(right)
            S.rightUnder:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.55)
            S.rightDivider = right:CreateTexture(nil, "BORDER", nil, 2)
            S.rightDivider:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 1)
            S.rightDivider:SetPoint("TOPLEFT", right, "TOPLEFT", 0, 0)
            S.rightDivider:SetPoint("BOTTOMLEFT", right, "BOTTOMLEFT", 0, 0)
            S.rightDivider:SetWidth(Kit.U(right, 1))
        elseif S.rightDivider then
            S.rightDivider:SetWidth(Kit.U(right, 1))
        end
    end
    local scene = _G.CharacterModelScene
    if scene then HeldArt.Hold(scene.BackgroundOverlay) end
end

-- The pages that are not the paper doll: stock art held, detail panes and rows restyled, controls and scroll bars swept.
local function SkinPages()
    local rep = _G.ReputationFrame
    if rep then
        Char.HoldStock(rep.ScrollBox, 2)
        Char.SkinDetail(rep.ReputationDetailFrame)
    end
    local skills = _G.SkillsFrame
    if skills then
        Char.HoldStock(skills.ScrollBox, 2)
        Char.SkinDetail(skills.SkillDetailFrame)
        Char.WatchRows(skills.ScrollBox, Char.PageRow)
    end
    local pvp = _G.PVPRankFrame
    if pvp then
        Char.HoldStock(pvp.MainInfoFrame, 3)
        Char.SkinDetail(pvp.DetailFrame)
        for _, key in ipairs({ "SeasonTimerField", "CurrentSeasonField", "CurrentRankField", "CurrentRankProgressField" }) do
            local fs = pvp[key] or (pvp.MainInfoFrame and pvp.MainInfoFrame[key])
            if type(fs) == "table" and fs.SetFont then Kit.RestyleLabel(fs, pvp, 12, C.text); PinColor(fs, C.text) end
        end
    end
    local stats = _G.StatisticsFrame
    if stats then
        Char.HoldStock(stats.ScrollBox, 2)
        Char.WatchRows(stats.ScrollBox, Char.PageRow)
    end
    local token = _G.TokenFrame
    if token then Char.HoldStock(token.ScrollBox, 2) end
    for _, name in ipairs({ "ReputationFrame", "SkillsFrame", "PVPRankFrame", "StatisticsFrame", "TokenFrame" }) do
        local page = _G[name]
        if page then pcall(PanelSkins.SweepOnShow, page) end
    end
end

-------------------------------------------------------------------------------
-- Footer: one shared line under both panes
-------------------------------------------------------------------------------

local function Chip(win, color, parent)
    parent = parent or win
    local chip = CreateFrame("Frame", nil, parent)
    chip:SetFrameLevel((parent:GetFrameLevel() or 0) + 6)
    local c = { frame = chip, color = color, w = 40 }
    c.plate = Kit.Plate(chip, 4, 40, G.CHIP_H)
    Kit.PaintPlate(c.plate, C.ink, 1, color, 1, 1)
    c.label = Kit.Label(chip, "", 12, color, "OVERLAY")
    Kit.Place(c.label, chip, 8, G.CHIP_H / 2, nil, nil, "LEFT", "TOPLEFT")
    c.label:SetJustifyH("LEFT")
    return c
end

local function Seat(c, text, x, right)
    c.label:SetText(text)
    local w = math.floor(#text * 12 * 0.5615 + 16 + 0.5)
    c.w = w
    local y = -math.floor((G.FOOT_H - G.CHIP_H) / 2)
    if right then
        Kit.Place(c.frame, c.frame:GetParent(), -G.SIDE, y, w, G.CHIP_H, "BOTTOMRIGHT", "BOTTOMRIGHT")
    else
        Kit.Place(c.frame, c.frame:GetParent(), x, y, w, G.CHIP_H, "BOTTOMLEFT", "BOTTOMLEFT")
    end
    c.plate.w = w
    return w
end

local function BuildFooter(win)
    S.footer = {
        band = Span(win, win, 0, G.FOOT_H, C.band, 1, "ARTWORK", 0, true),
        rule = Span(win, win, G.FOOT_H, 1, C.violet, 1, "ARTWORK", 1, true),
    }
    S.chips = { ilvl = Chip(win, C.amber), wear = Chip(win, C.cyan), worn = Chip(win, C.pink), repair = Chip(win, C.muted) }
end

function Char.RefreshChips()
    local chips = S.chips
    if not chips.ilvl then return end
    local pct, worn, cost = Char.Totals()
    local ilvl = ItemLevel()
    local x = G.SIDE
    local function put(c, text)
        if text then
            c.frame:Show()
            x = x + Seat(c, text, x) + G.CHIP_GAP
        else
            c.frame:Hide()
        end
    end
    put(chips.ilvl, ilvl and ("ilvl " .. ilvl))
    put(chips.wear, pct and ("wear " .. pct .. "%"))
    put(chips.worn, worn and worn > 0 and (worn .. " worn"))
    if cost and cost > 0 then
        chips.repair.frame:Show()
        Seat(chips.repair, "repair " .. Char.CoinText(cost), 0, true)
    else
        chips.repair.frame:Hide()
    end
    -- the footer chips belong to the character page only
    if ShownPage() ~= 1 then for _, c in pairs(chips) do c.frame:Hide() end end
end

-- The stock level line (CharacterLevelText, 28 units under the window's top edge) lands on the lower rule of our header band, so it
-- is held and its text is mirrored on an amber chip in the header band, LEVEL.GAP px right of the title, level with it. The chip is a
-- child of the paper doll page, so it goes with that page. The stock line is held only once its text has been read as a plain
-- string; a text the client will not give plainly hides the chip and leaves the stock line (restyled amber) where it was.
local LEVEL = { GAP = 16, MAX_W = 230 }

local function Visible(text) return (text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end

function Char.RefreshLevel()
    local c, head = S.level, S.header
    local line = _G.CharacterLevelText
    if not (c and head and type(line) == "table") then return end
    local text = Plain(Try(line.GetText, line))
    if type(text) ~= "string" or text == "" then c.frame:Hide() return end
    Kit.HoldFrame(line)
    local w = math.min(math.floor(#Visible(text) * 12 * 0.5615 + 16 + 0.5), LEVEL.MAX_W)
    c.label:SetText(text)
    if c.label.SetWordWrap then pcall(c.label.SetWordWrap, c.label, false) end
    Kit.Place(c.frame, head.title, LEVEL.GAP, 0, w, G.CHIP_H, "LEFT", "RIGHT", _G.CharacterFrame)
    Kit.Place(c.label, c.frame, 8, G.CHIP_H / 2, w - 16, G.CHIP_H, "LEFT", "TOPLEFT")
    c.plate.w = w
    c.frame:Show()
end

local function BuildLevel(win)
    local paper, line = _G.PaperDollFrame, _G.CharacterLevelText
    if type(paper) ~= "table" or type(line) ~= "table" or not S.header then return end
    S.level = Chip(win, C.amber, paper)
    for _, m in ipairs({ "SetFormattedText", "SetText" }) do Kit.HookFunc(line, m, Char.RefreshLevel) end
    Char.RefreshLevel()
end

-- The window is made one footer taller (outside combat); stock code that sets its height again is answered with the same.
local function ExtendWindow(win)
    if InCombat() or S.extending then return end
    local h = Plain(Try(win.GetHeight, win))
    if type(h) ~= "number" then return end
    if not S.baseH then S.baseH = h end
    -- whole physical pixels, so the footer's edges land on the pixel grid whatever the scale
    local ppu = Kit.Ppu(win)
    local target = (math.floor(S.baseH * ppu + 0.5) + math.floor(G.FOOT_H * Kit.LAYOUT_SCALE + 0.5)) / ppu
    if math.abs(h - target) < 0.5 then return end
    S.extending = true
    pcall(win.SetHeight, win, target)
    S.extending = false
end

-------------------------------------------------------------------------------
-- Build and drive
-------------------------------------------------------------------------------

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("character:" .. name, ("|cffff4488Forever STUwave|r: character skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local STRIP = { "CharacterFrame.Inset", "CharacterFrame.InsetRight", "PaperDollFrame" }
local MODEL_ART = {
    "CharacterModelFrameBackgroundTopLeft", "CharacterModelFrameBackgroundTopRight", "CharacterModelFrameBackgroundBotLeft",
    "CharacterModelFrameBackgroundBotRight", "CharacterLevelTextBackground",
}

local function Relayout()
    for _, rec in ipairs(S.spans) do rec.apply() end
    for b in pairs(S.boxes) do LayoutBox(b) end
    local win = _G.CharacterFrame
    if win and S.done then ExtendWindow(win) end
end

local function Refresh()
    if not S.done then return end
    Step("slots", SkinSlots)
    Step("slotsRefresh", RefreshSlots)
    Step("tabs", SkinModeTabs)
    Step("panes", SkinPanes)
    Step("strip", SkinTopStrip)
    Step("model", SkinModelControls)
    Step("sidebar", SkinSidebarTabs)
    Step("toggle", SkinToggle)
    Step("stats", SkinStats)
    Step("pages", SkinPages)
    Step("scrollbars", function() PanelSkins.SweepScrollBars(_G.CharacterFrame) end)
    Step("chips", Char.RefreshChips)
    Step("level", Char.RefreshLevel)
    Step("header", Char.RefreshHeader)
    for tab in pairs(S.tabs) do PaintTab(tab) end
end

local function Build()
    local win = _G.CharacterFrame
    if not win or S.done or InCombat() then return end
    S.done = true
    win.fsCharacterSkin = true
    -- Only the parts this client has: CharacterFrame.Inset / InsetRight are absent on 16001, and a missing path logs in chat.
    local present = {}
    for _, path in ipairs(STRIP) do
        local node, first = nil, true
        for field in path:gmatch("[^.]+") do
            if first then node, first = _G[field], false else node = type(node) == "table" and node[field] or nil end
        end
        if node then present[#present + 1] = path end
    end
    PanelSkins.StripNamed(present)
    Step("extend", ExtendWindow, win)
    Step("chrome", function()
        Theme.StripBlizzardChrome(win)
        Theme.AddPanelChrome(win, { fillColor = C.panel, accent = C.violet, glowAlpha = 0.30 })
    end)
    Step("art", function() for _, name in ipairs(MODEL_ART) do HeldArt.Hold(_G[name]) end end)
    Step("header", BuildHeader, win)
    Step("footer", BuildFooter, win)
    Step("levelChip", BuildLevel, win)
    Kit.HookScript(win, "OnShow", function() Kit.Later(function() Relayout(); Refresh() end) end)
    Kit.HookFunc(win, "SetHeight", function() if not S.extending then Kit.Later(function() ExtendWindow(win) end) end end)
    Kit.HookFunc(win, "SetSize", function() if not S.extending then Kit.Later(function() ExtendWindow(win) end) end end)
    Kit.OnReseat(function() Relayout(); Refresh() end)
    Refresh()
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "UPDATE_INVENTORY_DURABILITY", "PLAYER_EQUIPMENT_CHANGED", "PLAYER_AVG_ITEM_LEVEL_UPDATE",
    "UNIT_INVENTORY_CHANGED", "PLAYER_ENTERING_WORLD", "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED", "PLAYER_LEVEL_UP",
    "PLAYER_REGEN_ENABLED" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function(_, event)
    if not S.done then return end
    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
        Kit.Reseat()
        return
    end
    if event == "PLAYER_REGEN_ENABLED" and _G.CharacterFrame then Step("extend", ExtendWindow, _G.CharacterFrame) end
    Step("refresh", Refresh)
end)

if type(_G.PaperDollFrame_UpdateStats) == "function" then
    Kit.HookFunc(_G, "PaperDollFrame_UpdateStats", function() if S.done then Kit.Later(function() Step("stats", SkinStats) end) end end)
end

for _, name in ipairs({ "EquipmentFlyout_Show", "EquipmentFlyout_UpdateItems" }) do
    Kit.HookFunc(_G, name, function() if S.done then Step("flyout", SkinFlyout) end end)
end

-- Exports the other windows read (Inspect shares the slot skin; the pages share the holds).
Char.Box, Char.PaintBox, Char.SkinSquare, Char.PaintSquare, Char.PinColor = Box, PaintBox, SkinSquare, PaintSquare, PinColor
Char.AtlasOf, Char.List = AtlasOf, List

PanelSkins.RegisterInspect("Character", { { name = "CharacterFrame", guard = "fsCharacterSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
