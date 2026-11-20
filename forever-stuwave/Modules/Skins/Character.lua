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
--   * a shared footer line under both panes (the window is made one footer taller) with chips for the level (filled amber), item level, average wear and
--     worn pieces, and the repair bill on the right, each read from a plain API value and left out when the client will not give one;
--   * an info row under the header in place of the stock level line: the full name (with surname), race and class in mono;
--   * the model well: a cut panel between the slot columns behind the 3D model;
--   * the popout keys of the gear set mode as slim cut keys with a chevron pointing away from the slot, the ammo slot as a slot;
--   * the stats pane as the mockup draws it (left caps category titles, lowercase labels, banded rows), the gear set
--     and title lists as cards, their Equip / Save / New Set keys as STUwave text keys, the set picker as the guild bank's picker;
--   * the other pages' rows, value bars, detail panes, check box labels, collapse keys and the pvp rank emblem (shared helpers).
--
-- Skin only. Slots are secure item buttons: nothing on them is moved, resized, reparented or attributed, and no field is written
-- on them that UseContainerItem reads. Our regions, post-hooks and weak-keyed state only; the one resize is the window's own height
-- (outside combat, never a secure frame). A slot met in combat is decorated when combat ends. Values are read through FS.IsSecret
-- first. The shared helpers (HoldStock, RestyleFrame, SkinKey, SkinPage) are exported on FS.CharacterSkin for Skills, PvP,
-- Statistics, Reputation and Currency, which share the window.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the
-- durability model (the poles, the repair chip and hatching on the 3D model are not picked yet), wear brackets on the body and
-- the live trace from a hovered slot, stat change deltas after a gear swap, and the tooltip changes.

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
-- LIST_GAP: px between a page's scroll list (and its bar) and the footer rule. LIST_RIGHT: the statistics list's bar from the
-- window's right edge, the list spanning both panes there (the right pane is empty on that page).
local G = { FOOT_H = 28, CHIP_H = 20, CHIP_GAP = 8, SIDE = 14, WEAR_W = 2, WEAR_INSET = 4, WEAR_PAD = 6, HALO = 3, LIST_GAP = 8,
    LIST_RIGHT = 14 }
Char.GEOM = G

local function Weak() return setmetatable({}, { __mode = "k" }) end
-- px between the window edge and our bands (header, footer, right pane fill): on the chamfer of the cut corners
local function BandInset() return Theme.PanelBandInset and Theme.PanelBandInset() or 3 end
-- Drawing helpers defined further down (the boxes and glyph cells), used by the page helpers above them.
local LayoutBox, Box, PaintBox, ShownRegion, Cells, WatchShown
local S = {
    done = false, slots = {}, chips = {}, decorated = Weak(), held = Weak(), watched = Weak(), details = Weak(), rules = Weak(),
    boxes = Weak(), tabs = Weak(), squares = Weak(), spans = {}, popouts = Weak(), setRows = Weak(), statRows = Weak(), bands = Weak(),
    vbars = Weak(), washes = Weak(), collapse = Weak(), detailHooks = Weak(),
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
    -- An empty slot's stock art is a dark rounded square with a ghost glyph, smaller than our plate. Drawn additive its black adds
    -- nothing, so the plate shows edge to edge and only the glyph is left, lifted to violet.
    if info.empty then
        w.tinted = true
        if icon.SetBlendMode then pcall(icon.SetBlendMode, icon, "ADD") end
        pcall(icon.SetVertexColor, icon, C.violet[1], C.violet[2], C.violet[3], 1)
    elseif w.tinted then
        w.tinted = false
        if icon.SetBlendMode then pcall(icon.SetBlendMode, icon, "BLEND") end
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

-- The ammo slot (inventory slot 0, a small 27 unit slot right of the ranged one) wears the same slot. Its stock frame art is three
-- regions and a child: a 44 unit GearSlotSmall plate behind it, a 47 unit NormalTexture over it and an anonymous child carrying a
-- GearSlot-Arrow that points left across the ranged slot. All are stock atlas art and held with the rest.
local function SkinAmmo()
    local ammo = _G.CharacterAmmoSlot
    if type(ammo) ~= "table" then return end
    Char.SkinSlot(ammo, 0, "player")
    Char.HoldStock(ammo, 1)
    for _, region in ipairs(Char.List(ammo, "GetRegions")) do
        if Try(region.GetObjectType, region) == "Texture" and region ~= IconOf(ammo) then
            local tex = Plain(Try(region.GetTexture, region))
            -- the second NormalTexture (130841) is unkeyed, so the field sweep misses it
            if tex == 130841 then HeldArt.Hold(region) end
        end
    end
end

local function SkinSlots()
    for _, name in ipairs(SLOT_NAMES) do
        local button = _G["Character" .. name .. "Slot"]
        if button then Char.SkinSlot(button, SLOT_ID[name], "player") end
    end
    SkinAmmo()
    Char.SkinPopouts()
end


-- Pins `fs` to `color`: one SetTextColor post-hook per font string, ever (S.held holds the colour it keeps). A second call only
-- changes the kept colour and writes it, so a pane met again on every open or row select does not stack hooks (it did: each open
-- added a hook, and every SetTextColor ran all of them, so the window got slower to open each time).
local function PinColor(fs, color)
    if type(fs) ~= "table" or type(fs.SetTextColor) ~= "function" then return end
    local pin = S.held[fs]
    if pin then
        pin.color = color
        pcall(fs.SetTextColor, fs, color[1], color[2], color[3], 1)
        return
    end
    pin = { color = color }
    S.held[fs] = pin
    fs:SetTextColor(color[1], color[2], color[3], 1)
    if type(hooksecurefunc) ~= "function" then return end
    local busy = false
    pcall(hooksecurefunc, fs, "SetTextColor", function(self, r, g, b)
        local c = pin.color
        if busy or (r == c[1] and g == c[2] and b == c[3]) then return end
        busy = true
        pcall(self.SetTextColor, self, c[1], c[2], c[3], 1)
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
    "^common%-button%-square", "^common%-stat%-bar%-BG", "^charactercreate%-customize%-dropdown%-linemouseover",
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

-- A value bar of a page (a skill's SkillsBar, the detail pane's RankBar or StandingBar, a 160 x 29 unit StatusBar or plain Frame with
-- a Fill and a FillArea): its stock art held, and a thin cyan line of ours along its foot, as long as the value is through its range
-- (amber when full), under the stock text in mono. The fraction is the bar's own min, max and value when it has them, else the stock
-- Fill's width over its FillArea's; nothing is drawn when neither reads plainly.
local VB = { H = 3, INSET = 6, FOOT = 4 }

local function BarFraction(bar)
    local lo, hi = Try(bar.GetMinMaxValues, bar)
    local v = Try(bar.GetValue, bar)
    lo, hi, v = Plain(lo), Plain(hi), Plain(v)
    if type(lo) == "number" and type(hi) == "number" and type(v) == "number" and hi > lo then
        return math.max(0, math.min(1, (v - lo) / (hi - lo)))
    end
    local fill, area = bar.Fill, bar.FillArea
    local fw = type(fill) == "table" and Plain(Try(fill.GetWidth, fill))
    local aw = type(area) == "table" and Plain(Try(area.GetWidth, area))
    if type(fw) == "number" and type(aw) == "number" and aw > 0 then return math.max(0, math.min(1, fw / aw)) end
    return nil
end
Char.BarFraction = BarFraction

function Char.PaintValueBar(bar)
    local b = S.vbars[bar]
    if not b then return end
    local w, h = Kit.SizePx(bar)
    local frac = BarFraction(bar)
    if not w or not frac then
        b.track:Hide(); b.fill:Hide()
        return
    end
    local full = w - 2 * VB.INSET
    local y = h - VB.FOOT - VB.H
    Kit.Move(b.track, VB.INSET, y, full, VB.H)
    local fw = math.floor(full * frac + 0.5)
    local color = frac >= 1 and C.amber or C.cyan
    b.fill:SetColorTexture(color[1], color[2], color[3], 1)
    if fw > 0 then Kit.Move(b.fill, VB.INSET, y, fw, VB.H); b.fill:Show() else b.fill:Hide() end
    b.track:Show()
end

function Char.SkinValueBar(bar)
    if type(bar) ~= "table" or type(bar.CreateTexture) ~= "function" then return end
    if S.vbars[bar] then Char.PaintValueBar(bar) return end
    Char.HoldStock(bar, 1)
    HeldArt.Hold(bar.Fill)
    local tex = Try(bar.GetStatusBarTexture, bar)
    if type(tex) == "table" then HeldArt.Hold(tex) end
    local b = {
        track = Kit.Rect(bar, 0, 0, 1, VB.H, C.dim, 0.7, "OVERLAY", 1),
        fill = Kit.Rect(bar, 0, 0, 1, VB.H, C.cyan, 1, "OVERLAY", 2),
    }
    S.vbars[bar] = b
    local text = bar.Text or bar.BarText
    if type(text) == "table" and text.SetFont then Kit.RestyleLabel(text, bar, 11, C.text) end
    for _, m in ipairs({ "SetValue", "SetMinMaxValues" }) do Kit.HookFunc(bar, m, function() Char.PaintValueBar(bar) end) end
    if type(bar.Fill) == "table" then Kit.HookFunc(bar.Fill, "SetWidth", function() Char.PaintValueBar(bar) end) end
    Kit.HookScript(bar, "OnSizeChanged", function() Char.PaintValueBar(bar) end)
    Char.PaintValueBar(bar)
end

-- The hover and selected look of a page row. The stock row shows it through its BackgroundHighlight frame (grey line art, faded in
-- and out by the frame's alpha and shown state); that art is held, so a violet wash and a stripe at the row's left edge follow the
-- same frame's alpha and shown state instead.
function Char.PaintWash(row)
    local w = S.washes[row]
    if not w then return end
    local hl = w.hl
    local a = (ShownRegion(hl) and Plain(Try(hl.GetAlpha, hl))) or 0
    if type(a) ~= "number" or a < 0.05 then
        w.wash:Hide(); w.stripe:Hide()
        return
    end
    w.wash:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.22 * a)
    w.stripe:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], a)
    w.stripe:SetWidth(Kit.U(row, 3))
    w.wash:Show(); w.stripe:Show()
end

function Char.SkinWash(row, hl)
    if type(row) ~= "table" or type(hl) ~= "table" or S.washes[row] or type(row.CreateTexture) ~= "function" then return end
    for _, region in ipairs(List(hl, "GetRegions")) do HeldArt.Hold(region) end
    local w = { hl = hl }
    w.wash = row:CreateTexture(nil, "BACKGROUND", nil, -6)
    w.wash:SetAllPoints(row)
    w.stripe = row:CreateTexture(nil, "BORDER", nil, 3)
    w.stripe:SetPoint("TOPLEFT", row, "TOPLEFT", 0, 0)
    w.stripe:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 0, 0)
    S.washes[row] = w
    for _, m in ipairs({ "SetAlpha", "Show", "Hide", "SetShown" }) do Kit.HookFunc(hl, m, function() Char.PaintWash(row) end) end
    Kit.HookScript(row, "OnEnter", function() Char.PaintWash(row) end)
    Kit.HookScript(row, "OnLeave", function() Char.PaintWash(row) end)
    Char.PaintWash(row)
end

-- A header's collapse glyph (the stock list minus / plus, a green tinted atlas) in cyan: desaturated first, then tinted.
function Char.TintStateIcon(icon)
    if type(icon) ~= "table" or type(icon.SetVertexColor) ~= "function" then return end
    if icon.SetDesaturated then pcall(icon.SetDesaturated, icon, true) end
    pcall(icon.SetVertexColor, icon, C.cyan[1], C.cyan[2], C.cyan[3], 1)
end

-- The statistics page's category toggle (ToggleCollapseButton, a red campaign box): held, and a small key of ours in its place with a
-- minus when the category is open and a plus when it is shut, read from the stock atlas (Campaign_HeaderIcon_Open / _Closed).
local MINUS, PLUS = { { 0, 4, 10, 2 } }, { { 0, 4, 10, 2 }, { 4, 0, 2, 10 } }

function Char.PaintCollapse(btn)
    local k = S.collapse[btn]
    if not k then return end
    local nt = Try(btn.GetNormalTexture, btn)
    local atlas = AtlasOf(nt) or ""
    local open = not atlas:find("Closed")
    local hover = k.state and k.state.hover
    PaintBox(k.box, C.ink, 1, hover and C.cyan or C.dim, 1, 1)
    for _, t in ipairs(k.minus) do t:SetShown(open) end
    for _, t in ipairs(k.plus) do t:SetShown(not open) end
end

function Char.SkinCollapse(btn)
    if type(btn) ~= "table" or S.collapse[btn] or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    local plate = CreateFrame("Frame", nil, btn)
    Kit.Place(plate, btn, 0, 0, 16, 16, "CENTER", "CENTER", btn)
    local k = { box = Box(plate, "OVERLAY"), minus = Cells(plate, 10, 10, MINUS), plus = Cells(plate, 10, 10, PLUS) }
    S.collapse[btn] = k
    k.state = Kit.Track(btn, Char.PaintCollapse)
    for _, m in ipairs({ "SetNormalAtlas", "SetNormalTexture" }) do Kit.HookFunc(btn, m, function() Char.PaintCollapse(btn) end) end
    local nt = Try(btn.GetNormalTexture, btn)
    if type(nt) == "table" then Kit.HookFunc(nt, "SetAtlas", function() Char.PaintCollapse(btn) end) end
    Char.PaintCollapse(btn)
end

-- A row of one of the pages: its stock art held, its header glyph tinted, its texts in mono (the 16001 entry rows keep their texts
-- and bar on a Content child), its bar a value bar, its highlight a wash.
function Char.PageRow(row)
    if type(row) ~= "table" then return end
    Char.HoldStock(row, 5)
    Char.TintStateIcon(row.StateIcon)
    Char.RestyleFonts(row)
    local content = row.Content
    if type(content) == "table" then
        Char.RestyleFonts(content)
        for _, key in ipairs({ "SkillsBar", "StatusBar", "ReputationBar" }) do
            if type(content[key]) == "table" then Char.SkinValueBar(content[key]) end
        end
        if type(content.BackgroundHighlight) == "table" then Char.SkinWash(row, content.BackgroundHighlight) end
    end
    if type(row.ToggleCollapseButton) == "table" then Char.SkinCollapse(row.ToggleCollapseButton) end
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

-- A detail pane (the right hand pane of reputation, skills, pvp and currency): chrome art held, its title, subtitle, description,
-- content rows (label and value) and check box labels in mono, its bar a value bar, an icon slot boxed. The pane's content rows and
-- description text are made or refilled each time a row is selected, which always sets the title again, so the pane is met again
-- after every SetText of its title as well as on show.
local function DetailTexts(detail)
    Char.HoldStock(detail, 2)
    Char.RestyleFonts(detail)
    if type(detail.Title) == "table" then
        Kit.RestyleLabel(detail.Title, detail, 13, C.cyan)
        PinColor(detail.Title, C.cyan)
    end
    if type(detail.Subtitle) == "table" then Kit.RestyleLabel(detail.Subtitle, detail, 12, C.text) end
    -- the description: Description.ScrollBox.ScrollTarget > one frame > FontString
    local desc = detail.Description
    local box = type(desc) == "table" and (desc.ScrollBox or desc)
    local target = type(box) == "table" and box.ScrollTarget
    for _, child in ipairs(List(target, "GetChildren")) do
        for _, region in ipairs(List(child, "GetRegions")) do
            if Try(region.GetObjectType, region) == "FontString" then Kit.RestyleLabel(region, detail, 12, C.text) end
        end
    end
    -- the content rows: label and value lines, a rewards title plate, an icon slot
    for _, row in ipairs(List(detail.Content, "GetChildren")) do
        Char.HoldStock(row, 1)
        Char.RestyleFonts(row)
        if type(row.IconSlot) == "table" and not S.details[row] and type(row.CreateTexture) == "function" then
            S.details[row] = true
            HeldArt.Hold(row.IconSlot)
            local ring = Box(row, "BORDER", row.Icon or row.IconSlot)
            PaintBox(ring, C.ink, 1, C.violet, 1, 1)
        end
    end
    -- the check boxes' labels (At War, Move to Inactive, Show as Experience Bar, Unused, Show on Backpack)
    for _, child in ipairs(List(detail, "GetChildren")) do
        if Try(child.GetObjectType, child) == "CheckButton" then
            local label = child.Label or child.Text or child.text
            if type(label) == "table" and label.SetFont then
                Kit.RestyleLabel(label, child, 12, C.text)
                PinColor(label, C.text)
            end
        end
    end
    for _, key in ipairs({ "StandingBar", "RankBar" }) do
        if type(detail[key]) == "table" then Char.SkinValueBar(detail[key]) end
    end
end

function Char.SkinDetail(detail)
    if type(detail) ~= "table" then return end
    DetailTexts(detail)
    if S.detailHooks[detail] then return end
    S.detailHooks[detail] = true
    Kit.HookScript(detail, "OnShow", function() Kit.Later(function() pcall(DetailTexts, detail) end) end)
    if type(detail.Title) == "table" then
        Kit.HookFunc(detail.Title, "SetText", function() Kit.Later(function() pcall(DetailTexts, detail) end) end)
    end
end

-------------------------------------------------------------------------------
-- Boxes: a fill and a ring of rects that follows a stock widget's size
-------------------------------------------------------------------------------

function LayoutBox(b)
    local u = Kit.U(b.host, b.px or 1)
    local e, h = b.edges, b.ref or b.host
    e[1]:ClearAllPoints(); e[1]:SetPoint("TOPLEFT", h, "TOPLEFT", 0, 0); e[1]:SetPoint("TOPRIGHT", h, "TOPRIGHT", 0, 0); e[1]:SetHeight(u)
    e[2]:ClearAllPoints(); e[2]:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", 0, 0); e[2]:SetPoint("BOTTOMRIGHT", h, "BOTTOMRIGHT", 0, 0); e[2]:SetHeight(u)
    e[3]:ClearAllPoints(); e[3]:SetPoint("TOPLEFT", h, "TOPLEFT", 0, 0); e[3]:SetPoint("BOTTOMLEFT", h, "BOTTOMLEFT", 0, 0); e[3]:SetWidth(u)
    e[4]:ClearAllPoints(); e[4]:SetPoint("TOPRIGHT", h, "TOPRIGHT", 0, 0); e[4]:SetPoint("BOTTOMRIGHT", h, "BOTTOMRIGHT", 0, 0); e[4]:SetWidth(u)
end

-- `ref` (a frame or a texture) is what the box follows when it is not `host` itself; the textures are `host`'s.
function Box(host, edgeLayer, ref)
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

function PaintBox(b, fill, fa, edge, ea, px)
    b.fill:SetColorTexture(fill[1], fill[2], fill[3], fa or 1)
    for _, t in ipairs(b.edges) do t:SetColorTexture(edge[1], edge[2], edge[3], ea or 1) end
    if px and px ~= b.px then b.px = px; LayoutBox(b) end
end

function ShownRegion(region)
    return type(region) == "table" and Try(region.IsShown, region) == true
end

-- Follows a texture region's shown state (the stock selected glow of a tab).
function WatchShown(region, fn)
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
function Cells(btn, gw, gh, cells)
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
    -- the stock key has no tooltip here: say what it does
    Kit.HookScript(btn, "OnEnter", function(self)
        local tip, right = _G.GameTooltip, _G.CharacterFrameRightPaneHost
        if not tip then return end
        tip:SetOwner(self, "ANCHOR_BOTTOM")
        local open = right and Try(right.IsShown, right) == true
        tip:SetText(open and "Hide the side panel" or "Show the side panel")
        tip:Show()
    end)
    Kit.HookScript(btn, "OnLeave", function() if _G.GameTooltip then _G.GameTooltip:Hide() end end)
end

-- The pane toggle sits in the header band, left of the close key, on every page (stock, it hangs over the top of the left pane,
-- which on the statistics page, its list spanning both panes, left it floating over the list). A plain button; out of combat.
function Char.SeatToggle()
    local btn, win, close = _G.CharacterFrameRightPaneToggleButton, _G.CharacterFrame, _G.CharacterFrameCloseButton
    if not (btn and win and S.headPx) or InCombat() then return end
    local wr = Plain(Try(win.GetRight, win))
    local cl = close and Plain(Try(close.GetLeft, close))
    if type(wr) ~= "number" then return end
    local dx = (type(cl) == "number" and wr - cl or Kit.U(win, 30)) + Kit.U(win, 8)
    btn:ClearAllPoints()
    btn:SetPoint("RIGHT", win, "TOPRIGHT", -dx, -Kit.U(win, S.headPx / 2))
end

-------------------------------------------------------------------------------
-- Popout keys: the small buttons beside each slot that open the equipment flyout (shown in the gear set mode)
-------------------------------------------------------------------------------

-- The stock key is a 20 x 43 unit leather pull with a yellow arrow (UI-Character-Info-Button-PullSide). It is held and a slim cut
-- key of ours drawn in its middle: an ink face, a dim edge (cyan on hover) and a chevron that points away from the slot it opens
-- from, so the left column points right, the right column left and the weapon row up. Our regions on the stock key only.
local POP = { LONG = 26, SHORT = 12 }
local CHEVRON = {
    right = { { 0, 0, 2, 2 }, { 2, 2, 2, 2 }, { 4, 4, 2, 2 }, { 2, 6, 2, 2 }, { 0, 8, 2, 2 } },
    left = { { 4, 0, 2, 2 }, { 2, 2, 2, 2 }, { 0, 4, 2, 2 }, { 2, 6, 2, 2 }, { 4, 8, 2, 2 } },
    up = { { 4, 0, 2, 2 }, { 2, 2, 2, 2 }, { 6, 2, 2, 2 }, { 0, 4, 2, 2 }, { 8, 4, 2, 2 } },
}

-- Which way a side key points: away from its slot, read from the two centres when painted (the slots are laid out after the skin is
-- built, so a direction read at build time can be wrong).
local function PopoutDir(p, btn)
    if p.dir == "up" then return "up" end
    local bx = Plain(Try(btn.GetCenter, btn))
    local sx = p.slot and Plain(Try(p.slot.GetCenter, p.slot))
    if type(bx) == "number" and type(sx) == "number" then return bx < sx and "left" or "right" end
    return "right"
end

local function PaintPopout(btn)
    local p = S.popouts[btn]
    if not p then return end
    local hover = p.state and (p.state.hover or p.state.pressed)
    PaintBox(p.box, hover and C.band or C.ink, 1, hover and C.cyan or C.dim, 1, 1)
    local g = hover and C.text or C.cyan
    local dir = PopoutDir(p, btn)
    for key, cells in pairs(p.glyphs) do
        for _, t in ipairs(cells) do
            t:SetColorTexture(g[1], g[2], g[3], 1)
            t:SetShown(key == dir)
        end
    end
end

function Char.SkinPopout(btn, slot)
    if type(btn) ~= "table" or S.popouts[btn] or type(btn.CreateTexture) ~= "function" then return end
    HeldArt.HoldButton(btn)
    Char.HoldStock(btn, 0)
    local bw, bh = Plain(Try(btn.GetWidth, btn)), Plain(Try(btn.GetHeight, btn))
    if type(bw) ~= "number" or type(bh) ~= "number" then return end
    local side = bh > bw
    local w, h = side and POP.SHORT or POP.LONG, side and POP.LONG or POP.SHORT
    local plate = CreateFrame("Frame", nil, btn)
    Kit.Place(plate, btn, 0, 0, w, h, "CENTER", "CENTER", btn)
    local p = { box = Box(plate, "OVERLAY"), dir = side and "side" or "up", slot = slot, glyphs = {} }
    if side then
        p.glyphs.left = Cells(plate, 6, 10, CHEVRON.left)
        p.glyphs.right = Cells(plate, 6, 10, CHEVRON.right)
    else
        p.glyphs.up = Cells(plate, 10, 6, CHEVRON.up)
    end
    S.popouts[btn] = p
    p.state = Kit.Track(btn, PaintPopout)
    PaintPopout(btn)
end

function Char.SkinPopouts()
    for _, name in ipairs(SLOT_NAMES) do
        local slot = _G["Character" .. name .. "Slot"]
        local btn = slot and (slot.popoutButton or _G["Character" .. name .. "SlotPopoutButton"])
        if btn then Char.SkinPopout(btn, slot) end
    end
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

-- Stat rows, from the mockup's stats pane: a category row's title sits at the left in small violet caps with a rule running from it to
-- the row's right edge; a stat row reads "strength ... 78" with its label in lowercase mono and no colon, its value right aligned in
-- the stock colour (green when buffed), and every other row carries a faint band (the stock row shows its Background on alternate
-- rows; our band follows that). The title and label texts are rewritten by post-hooks on the stock SetText of those two font
-- strings only (plain strings only), the title re-anchored to the row's left: the stats pane is not secure and nothing reads them back.
local STAT = { TITLE_PX = 11, INSET = 6, RULE_GAP = 8 }

local function Rewrite(fs, fn)
    if type(fs) ~= "table" or S.statRows[fs] or type(hooksecurefunc) ~= "function" then return end
    S.statRows[fs] = true
    local busy = false
    local function apply(self)
        if busy then return end
        local text = Plain(Try(self.GetText, self))
        if type(text) ~= "string" then return end
        local want = fn(text)
        if want == text then return end
        busy = true
        pcall(self.SetText, self, want)
        busy = false
    end
    pcall(hooksecurefunc, fs, "SetText", apply)
    apply(fs)
end

local function TitleText(t) return t:upper() end
local function LabelText(t)
    local body = t:gsub(":%s*$", "")
    if body:find("|c") then return body end
    return body:lower()
end

local function StatRow(row)
    if type(row) ~= "table" then return end
    HeldArt.Hold(row.Background)
    Char.RestyleFonts(row)
    if not S.rules[row] and row.CreateTexture then
        local rule = row:CreateTexture(nil, "BORDER")
        S.rules[row] = rule
        local band = row:CreateTexture(nil, "BACKGROUND", nil, -6)
        band:SetAllPoints(row)
        band:SetColorTexture(C.band[1], C.band[2], C.band[3], 0.8)
        S.bands[row] = band
    end
    local rule = S.rules[row]
    local title = type(row.Title) == "table" and row.Title or nil
    if rule then
        rule:ClearAllPoints()
        if title then
            Kit.RestyleLabel(title, row, STAT.TITLE_PX, C.violet)
            PinColor(title, C.violet)
            if title.SetJustifyH then pcall(title.SetJustifyH, title, "LEFT") end
            pcall(title.ClearAllPoints, title)
            pcall(title.SetPoint, title, "LEFT", row, "LEFT", Kit.U(row, STAT.INSET), 0)
            Rewrite(title, TitleText)
            -- from the text's own width: a title font string may be sized wider than its text
            local tw = Plain(Try(title.GetStringWidth, title))
            tw = type(tw) == "number" and tw or 0
            rule:SetPoint("LEFT", row, "LEFT", Kit.U(row, STAT.INSET + STAT.RULE_GAP) + tw, 0)
            rule:SetPoint("RIGHT", row, "RIGHT", -Kit.U(row, STAT.INSET), 0)
            -- no rule after the title (the horizontal rules read as clutter): the caps title alone heads the group
            rule:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0)
        else
            rule:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 0, 0)
            rule:SetPoint("BOTTOMRIGHT", row, "BOTTOMRIGHT", 0, 0)
            rule:SetColorTexture(C.dim[1], C.dim[2], C.dim[3], 0)
            Rewrite(row.Label, LabelText)
        end
        rule:SetHeight(Kit.U(row, 1))
    end
    local band = S.bands and S.bands[row]
    if band then band:SetShown(not title and ShownRegion(row.Background)) end
end

-- One row of the gear set or title list (pooled by its ScrollBox): stock art held, a card behind it, every text in mono. The
-- selected or equipped state shows through the stock check and icon, which are kept.
local function ListRow(row)
    if type(row) ~= "table" or type(row.CreateTexture) ~= "function" then return end
    if not S.setRows[row] then
        Char.HoldStock(row, 2)
        for _, key in ipairs({ "BgTop", "BgBottom", "BgMiddle", "HighlightBar", "SelectedBar", "Stripe", "Background" }) do
            HeldArt.Hold(row[key])
        end
        local b = Box(row, "BORDER")
        S.setRows[row] = b
        S.setRowState = S.setRowState or Weak()
        S.setRowState[row] = Kit.Track(row, function(r)
            local st = S.setRowState[r]
            PaintBox(S.setRows[r], C.ink, 0.9, st and st.hover and C.cyan or C.dim, 1, 1)
        end)
    end
    PaintBox(S.setRows[row], C.ink, 0.9, C.dim, 1, 1)
    for _, region in ipairs(List(row, "GetRegions")) do
        if Try(region.GetObjectType, region) == "FontString" then
            Kit.RestyleLabel(region, row, 12, C.text)
        end
    end
end

local function SkinSidePanes()
    local paper = _G.PaperDollFrame
    if not paper then return end
    local equip, titles = paper.EquipmentManagerPane, paper.TitleManagerPane
    for _, pane in ipairs({ equip, titles }) do
        if type(pane) == "table" then
            Char.HoldStock(pane, 1)
            HeldArt.Hold(pane.Border)
            if pane.ScrollBox then Char.WatchRows(pane.ScrollBox, ListRow) end
        end
    end
    local skins = FS.ButtonSkins
    if skins and skins.SkinTextButton then
        local function text(btn, accent) if type(btn) == "table" then pcall(skins.SkinTextButton, btn, { accent = accent }) end end
        text(_G.PaperDollFrameEquipSet or (equip and equip.EquipSet), "cyan")
        text(_G.PaperDollFrameSaveSet or (equip and equip.SaveSet), "violet")
        text(_G.PaperDollFrameNewSet or (equip and equip.NewSet), "cyan")
    end
    -- the set name and icon picker the New Set key opens (an IconSelectorPopupFrameTemplate, as the guild bank tab picker)
    local pop = _G.GearManagerPopupFrame
    local gb = FS.GuildBankSkin
    if type(pop) == "table" and gb and gb.SkinIconPopup then pcall(gb.SkinIconPopup, pop) end
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
    SkinSidePanes()
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

local ShowGlyph -- the page glyphs, defined with the header below

function Char.RefreshHeader()
    local h = S.header
    if not h then return end
    local label = PAGES[ShownPage()].label
    h.title:SetText("stuwave://" .. label)
    ShowGlyph(label)
end

-- The height of the stock strip above the panes, in UI units: measured from the frames, 24 when they will not say.
local function TopGapUnits(win)
    local pane = _G.CharacterFrameLeftPaneHost
    local a = Plain(Try(win.GetTop, win))
    local b = pane and Plain(Try(pane.GetTop, pane))
    if type(a) == "number" and type(b) == "number" and a - b >= 8 and a - b <= 80 then return a - b end
    return 24
end

-- The page glyphs (approved 2026-11-19, mockups/header-glyphs-2026-11-19.html, treatment B "neon outline"): 16 x 16 pixel maps,
-- '#' the body, '+' a pink detail. A body pixel on the shape's edge is lit cyan, one inside it is cyan glass, and a halo pixel
-- (empty, next to the shape) carries a faint cyan glow. Drawn as horizontal runs, `k` screen pixels per map pixel.
local GLYPHS = {
    character = {
        "................",
        ".....######.....",
        "....########....",
        "...##########...",
        "...##########...",
        "...#++++++++#...",
        "...##########...",
        "....########....",
        ".....######.....",
        "......####......",
        "..############..",
        ".##############.",
        ".######++######.",
        ".#####++++#####.",
        ".##############.",
        "................",
    },
    reputation = {
        "................",
        ".##.............",
        ".#############..",
        ".############...",
        ".##++++#####....",
        ".##+##+####.....",
        ".##++++#####....",
        ".############...",
        ".#############..",
        ".##.............",
        ".##.............",
        ".##.............",
        ".##.............",
        ".##.............",
        "####............",
        "................",
    },
    skills = {
        "..........##....",
        ".........####...",
        "........####....",
        ".......#.##.....",
        "......#.........",
        ".....#..........",
        "................",
        "..+##########...",
        ".############++.",
        "..##########....",
        "....######......",
        ".....####.......",
        "....######......",
        "...########.....",
        "...########.....",
        "................",
    },
    pvp = {
        "##............##",
        "###..........###",
        ".###........###.",
        "..###......###..",
        "...###....###...",
        "....###..###....",
        ".....######.....",
        "......####......",
        ".....######.....",
        "..+.###..###.+..",
        "...+##....##+...",
        "..+++......+++..",
        ".++..........++.",
        "++............++",
        "................",
        "................",
    },
    currency = {
        "................",
        ".....######.....",
        "...##++++++##...",
        "...##########...",
        "................",
        "..##########....",
        "..#++++++++#....",
        "..##########....",
        "................",
        "....##########..",
        "....#++++++++#..",
        "....##########..",
        "....#++++++++#..",
        "....##########..",
        "................",
        "................",
    },
    statistics = {
        "..............+.",
        "............++..",
        "..........++.##.",
        "........++...##.",
        "......++..##.##.",
        "....++....##.##.",
        "..++..##..##.##.",
        ".+....##..##.##.",
        "..##..##..##.##.",
        "..##..##..##.##.",
        "..##..##..##.##.",
        "..##..##..##.##.",
        "..##..##..##.##.",
        "################",
        "................",
        "................",
    },
}
local GLYPH_PAINT = {
    edge = { "cyan", 1 }, glass = { "cyan", 0.18 }, accent = { "pink", 1 }, halo = { "cyan", 0.22 },
}

local function GlyphClass(map, x, y)
    local function at(i, j)
        if j < 1 or j > 16 or i < 1 or i > 16 then return "." end
        return map[j]:sub(i, i)
    end
    local c = at(x, y)
    local open = at(x + 1, y) == "." or at(x - 1, y) == "." or at(x, y + 1) == "." or at(x, y - 1) == "."
    if c == "+" then return "accent" end
    if c == "#" then return open and "edge" or "glass" end
    local near = at(x + 1, y) ~= "." or at(x - 1, y) ~= "." or at(x, y + 1) ~= "." or at(x, y - 1) ~= "."
    return near and "halo" or nil
end

function Char.GlyphRuns(map)
    local runs = {}
    for y = 0, 17 do
        local x = 0
        while x <= 17 do
            local cls = GlyphClass(map, x, y)
            local n = 1
            while cls and x + n <= 17 and GlyphClass(map, x + n, y) == cls do n = n + 1 end
            if cls then runs[#runs + 1] = { x = x - 1, y = y - 1, n = n, cls = cls } end
            x = x + n
        end
    end
    return runs
end

local function Glyph(win, label, x, y, k)
    local map = GLYPHS[label] or GLYPHS.character
    local out = {}
    for _, r in ipairs(Char.GlyphRuns(map)) do
        local paint = GLYPH_PAINT[r.cls]
        local sub = r.cls == "halo" and 1 or (r.cls == "glass" and 2 or 3)
        out[#out + 1] = Kit.Rect(win, x + r.x * k, y + r.y * k, r.n * k, k, C[paint[1]], paint[2], "OVERLAY", sub)
    end
    return out
end

-- Shows the shown page's glyph, building it the first time that page is met.
ShowGlyph = function(label)
    local h = S.header
    if not h then return end
    if not h.glyphs[label] then h.glyphs[label] = Glyph(h.win, label, h.gx, h.gy, h.gk) end
    for name, set in pairs(h.glyphs) do
        for _, t in ipairs(set) do t:SetShown(name == label) end
    end
end

-- A rect that spans the width of `host` from `y` px down, `h` px tall: two anchors, so it follows a window that changes width.
local function Span(host, parent, y, h, color, alpha, layer, sub, fromBottom, inset)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetColorTexture(color[1], color[2], color[3], alpha or 1)
    Kit.Snap(t)
    local rec = { t = t, host = host, y = y, h = h, bottom = fromBottom, x = inset or 0 }
    local function apply()
        local k = Kit.U(host, 1)
        local x = rec.x * k
        t:ClearAllPoints()
        if rec.bottom then
            t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", x, rec.y * k)
            t:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -x, rec.y * k)
        else
            t:SetPoint("TOPLEFT", host, "TOPLEFT", x, -rec.y * k)
            t:SetPoint("TOPRIGHT", host, "TOPRIGHT", -x, -rec.y * k)
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
    -- under the window's border slice (BORDER 0), as the footer band is, so the border runs unbroken past the header
    -- inset to the chamfer (Theme.PanelBandInset, as every STUwave panel's band), so the cut corners stay cut
    local inset = BandInset()
    local band = Span(win, win, inset, headPx - inset, C.band, 1, "BORDER", -2, false, inset)
    local k = headPx >= 36 and 2 or 1
    local gx, gy = 12, math.floor((headPx - 16 * k) / 2)
    local title = Kit.Label(win, "stuwave://character", headPx >= 36 and 16 or 13, C.muted, "OVERLAY")
    Kit.Place(title, win, gx + 16 * k + 10, math.floor(headPx / 2), nil, nil, "LEFT", "TOPLEFT")
    title:SetJustifyH("LEFT")
    S.header = { title = title, band = { band }, glyphs = {}, win = win, gx = gx, gy = gy, gk = k }

    Kit.HoldFrame(_G.CharacterFrameTitleText)
    HeldArt.Hold(_G.CharacterFramePortrait)
    if Theme.SkinCloseButton then pcall(Theme.SkinCloseButton, win) end
    for _, page in ipairs(PAGES) do
        Kit.HookScript(_G[page.frame], "OnShow", function()
            Char.RefreshHeader(); Char.RefreshChips(); Char.RefreshLevel()
            Kit.Later(function() pcall(Char.FitPages) end)
        end)
    end
    Char.RefreshHeader()
end

-- The stock strip under the header (it carries the level line): held. No band of ours under it: the info row sits on the window
-- fill (a band there, re-seated with the header spans, came back as a 1 px dark line through the header's title).
local function SkinTopStrip()
    local paper = _G.PaperDollFrame
    local host = paper and paper.TopBackgroundStripHost
    if host then
        HeldArt.Hold(host.TopBackgroundStrip)
        HeldArt.Hold(host.TopBackgroundStripBottomEdge)
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
            S.rightUnder:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.55)
            S.rightDivider = right:CreateTexture(nil, "BORDER", nil, 2)
            S.rightDivider:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 1)
        end
        Char.FitRightPane()
    end
    local scene = _G.CharacterModelScene
    if scene then HeldArt.Hold(scene.BackgroundOverlay) end
end

-- The right pane's fill and divider stop at the footer rule (the pane runs to the window's bottom edge, so anchored to it they
-- ran through the footer), and stand down on the statistics page, whose list spans both panes.
function Char.FitRightPane()
    local right, win = _G.CharacterFrameRightPaneHost, _G.CharacterFrame
    local under, divider = S.rightUnder, S.rightDivider
    if not (right and win and under and divider) then return end
    local wb, hb = Plain(Try(win.GetBottom, win)), Plain(Try(right.GetBottom, right))
    local wt, ht = Plain(Try(win.GetTop, win)), Plain(Try(right.GetTop, right))
    local off, top = 0, 0
    if type(wb) == "number" and type(hb) == "number" then off = math.max(0, Kit.U(win, G.FOOT_H) - (hb - wb)) end
    -- the pane starts inside the header band: its fill there read as a dark bar across the header's foot
    if type(wt) == "number" and type(ht) == "number" then top = math.max(0, Kit.U(win, S.headPx or 24) - (wt - ht)) end
    under:ClearAllPoints()
    under:SetPoint("TOPLEFT", right, "TOPLEFT", 0, -top)
    -- clear of the window's right border
    under:SetPoint("BOTTOMRIGHT", right, "BOTTOMRIGHT", -Kit.U(win, BandInset()), off)
    divider:ClearAllPoints()
    divider:SetPoint("TOPLEFT", right, "TOPLEFT", 0, -top)
    divider:SetPoint("BOTTOMLEFT", right, "BOTTOMLEFT", 0, off)
    divider:SetWidth(Kit.U(right, 1))
    local stats = _G.StatisticsFrame
    local wide = stats and Try(stats.IsShown, stats) == true
    under:SetShown(not wide)
    divider:SetShown(not wide)
end

-- A page's detail pane (reputation, skills, pvp, currency) seated the same way on every page: inside the right pane from the header
-- band down to the footer, `margin` px in from every side (stock, each hung at its own height, the title flush under the header on
-- some). Returns true when seated. A plain frame, not a secure one; out of combat.
G.DETAIL_MARGIN = 10
function Char.SeatDetailFrame(detail, margin)
    local host, win = _G.CharacterFrameRightPaneHost, _G.CharacterFrame
    if type(detail) ~= "table" or type(host) ~= "table" or type(win) ~= "table" or InCombat() then return false end
    local m = Kit.U(win, margin or G.DETAIL_MARGIN)
    local wt, ht = Plain(Try(win.GetTop, win)), Plain(Try(host.GetTop, host))
    local wb, hb = Plain(Try(win.GetBottom, win)), Plain(Try(host.GetBottom, host))
    if not (type(wt) == "number" and type(ht) == "number" and type(wb) == "number" and type(hb) == "number") then return false end
    local top = Kit.U(win, S.headPx or 24) + m - (wt - ht)
    local bottom = Kit.U(win, G.FOOT_H) + m - (hb - wb)
    detail:ClearAllPoints()
    detail:SetPoint("TOPLEFT", host, "TOPLEFT", m, -top)
    detail:SetPoint("BOTTOMRIGHT", host, "BOTTOMRIGHT", -m, bottom)
    return true
end

local function DetailOf(name)
    local page = _G[name]
    if type(page) ~= "table" then return nil end
    if name == "SkillsFrame" then return page.SkillDetailFrame end
    if name == "TokenFrame" then return page.DetailFrame or _G.TokenDetailFrame end
    if name == "PVPRankFrame" then return page.DetailFrame end
end

-- The pages with a scroll list (reputation, skills, statistics, currency): the list and its bar end LIST_GAP px above the footer
-- rule (stock, they run on into the footer the window gained, the last row drawn over it). The statistics list also spans both
-- panes. Offsets are read once from the stock layout, then the list is anchored from them; plain frames, not secure ones.
local LIST_PAGES = { ReputationFrame = false, SkillsFrame = false, StatisticsFrame = true, TokenFrame = false }
S.fits = Weak()

function Char.FitList(page, wide)
    local win = _G.CharacterFrame
    local box, bar = type(page) == "table" and page.ScrollBox, type(page) == "table" and page.ScrollBar
    if not (win and type(box) == "table" and type(bar) == "table") then return end
    local rec = S.fits[box]
    if not rec then
        local pl, pt = Plain(Try(page.GetLeft, page)), Plain(Try(page.GetTop, page))
        local bl, bt, br, bw = Plain(Try(box.GetLeft, box)), Plain(Try(box.GetTop, box)), Plain(Try(box.GetRight, box)),
            Plain(Try(box.GetWidth, box))
        local sl, st, sw = Plain(Try(bar.GetLeft, bar)), Plain(Try(bar.GetTop, bar)), Plain(Try(bar.GetWidth, bar))
        for _, v in ipairs({ pl, pt, bl, bt, br, bw, sl, st, sw }) do if type(v) ~= "number" then return end end
        rec = { dx = bl - pl, dy = bt - pt, w = bw, gap = sl - br, bdy = st - bt, bw = sw }
        S.fits[box] = rec
    end
    local pt, pl, wb, wr = Plain(Try(page.GetTop, page)), Plain(Try(page.GetLeft, page)), Plain(Try(win.GetBottom, win)),
        Plain(Try(win.GetRight, win))
    if not (type(pt) == "number" and type(pl) == "number" and type(wb) == "number" and type(wr) == "number") then return end
    local floor = wb + Kit.U(win, G.FOOT_H + G.LIST_GAP)
    local h = pt + rec.dy - floor
    local w = rec.w
    if wide then w = wr - Kit.U(win, G.LIST_RIGHT) - rec.bw - rec.gap - (pl + rec.dx) end
    if h < 40 or w < 40 then return end
    box:ClearAllPoints()
    box:SetPoint("TOPLEFT", page, "TOPLEFT", rec.dx, rec.dy)
    box:SetSize(w, h)
    bar:ClearAllPoints()
    bar:SetPoint("TOPLEFT", box, "TOPRIGHT", rec.gap, rec.bdy)
    bar:SetSize(rec.bw, math.max(8, h + rec.bdy))
end

function Char.FitPages()
    for name, wide in pairs(LIST_PAGES) do
        local page = _G[name]
        if page and Try(page.IsShown, page) == true then Char.FitList(page, wide) end
    end
    for _, name in ipairs({ "SkillsFrame", "TokenFrame", "PVPRankFrame" }) do
        local page = _G[name]
        if page and Try(page.IsShown, page) == true then Char.SeatDetailFrame(DetailOf(name)) end
    end
    Char.FitRightPane()
    Char.SeatToggle()
end

-- The pvp page's rank emblem (MainInfoFrame.RankProgressBarDisplay, a Cooldown whose swipe is the rank progress): the stock glow and
-- the faction disc are held, the ring track under the swipe tinted dim violet, the faction badge kept, the swipe drawn pink; the next reward ring held, a
-- cut box of ours in its place and its level number in amber mono.
function Char.SkinRankEmblem(pvp)
    local info = pvp and pvp.MainInfoFrame
    local disp = type(info) == "table" and info.RankProgressBarDisplay
    if type(disp) ~= "table" or S.details[disp] then return end
    S.details[disp] = true
    for _, region in ipairs(List(disp, "GetRegions")) do
        if region == disp.Bar then
            -- the ring track under the swipe stays, desaturated and dim violet, so the progress arc has a ring to run on
            if region.SetDesaturated then pcall(region.SetDesaturated, region, true) end
            pcall(region.SetVertexColor, region, C.dim[1], C.dim[2], C.dim[3], 1)
        elseif region ~= disp.FactionBadge and Try(region.GetObjectType, region) == "Texture" then
            HeldArt.Hold(region)
        end
    end
    if type(disp.SetSwipeColor) == "function" then pcall(disp.SetSwipeColor, disp, C.pink[1], C.pink[2], C.pink[3], 0.9) end
    local next = disp.NextRewardLevel
    if type(next) == "table" and type(next.CreateTexture) == "function" then
        HeldArt.Hold(next.RingBorder)
        HeldArt.Hold(next.IconCover)
        PaintBox(Box(next, "OVERLAY"), C.ink, 1, C.amber, 1, 1)
        if type(next.LevelLabel) == "table" then
            Kit.RestyleLabel(next.LevelLabel, next, 13, C.amber)
            PinColor(next.LevelLabel, C.amber)
        end
    end
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
        Char.SkinRankEmblem(pvp)
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
    if token then
        Char.HoldStock(token.ScrollBox, 2)
        Char.SkinDetail(token.DetailFrame or _G.TokenDetailFrame)
    end
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
        -- under the window's border slice (BORDER 0), so the border still closes the window round the footer
        band = Span(win, win, BandInset(), G.FOOT_H - BandInset(), C.band, 1, "BORDER", -2, true, BandInset()),
    }
    S.chips = { level = Chip(win, C.amber), ilvl = Chip(win, C.amber), wear = Chip(win, C.cyan), repair = Chip(win, C.muted) }
    -- the level chip is filled amber with dark type, so it reads first
    local lvl = S.chips.level
    Kit.PaintPlate(lvl.plate, C.amber, 1, C.amber, 1, 1)
    lvl.label:SetTextColor(C.ink[1], C.ink[2], C.ink[3], 1)
    PinColor(lvl.label, C.ink)
    S.level = lvl
    -- the durability chip lists every piece's durability on hover, lowest first
    local wear = S.chips.wear.frame
    -- above the model scene (live: CharacterModelScene reaches down over the footer and takes the mouse there)
    local scene = _G.CharacterModelScene
    local top = math.max(Plain(Try(win.GetFrameLevel, win)) or 0, scene and Plain(Try(scene.GetFrameLevel, scene)) or 0)
    wear:SetFrameLevel(top + 10)
    wear:EnableMouse(true)
    wear:SetScript("OnEnter", function(self) Char.ShowDurabilityTip(self) end)
    wear:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
end

-- One line per equipped piece that has durability: the slot name and its percent in the wear colour, lowest first.
function Char.DurabilityLines()
    local out = {}
    for _, name in ipairs(SLOT_NAMES) do
        local frac = Char.WearOf(SLOT_ID[name])
        if frac then
            local label = _G[name:upper() .. "SLOT"]
            out[#out + 1] = { name = type(label) == "string" and label or name, frac = frac, order = #out }
        end
    end
    table.sort(out, function(a, b) if a.frac ~= b.frac then return a.frac < b.frac end return a.order < b.order end)
    return out
end

function Char.ShowDurabilityTip(owner)
    if not GameTooltip then return end
    GameTooltip:SetOwner(owner, "ANCHOR_TOP")
    GameTooltip:ClearLines()
    GameTooltip:AddLine("Durability", C.text[1], C.text[2], C.text[3])
    for _, l in ipairs(Char.DurabilityLines()) do
        local c = Char.WearColor(l.frac)
        GameTooltip:AddDoubleLine(l.name, math.floor(l.frac * 100 + 0.5) .. "%", C.muted[1], C.muted[2], C.muted[3], c[1], c[2], c[3])
    end
    GameTooltip:Show()
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
    local info = Char.InfoText()
    put(chips.level, info and info.level)
    put(chips.ilvl, ilvl and ("ilvl " .. ilvl))
    if pct then
        -- the chip takes the wear colour of the average
        local c = Char.WearColor(pct / 100)
        Kit.PaintPlate(chips.wear.plate, C.ink, 1, c, 1, 1)
        chips.wear.label:SetTextColor(c[1], c[2], c[3], 1)
    end
    put(chips.wear, pct and ("durability " .. pct .. "%"))
    if cost and cost > 0 then
        chips.repair.frame:Show()
        Seat(chips.repair, "repair " .. Char.CoinText(cost), 0, true)
    else
        chips.repair.frame:Hide()
    end
    -- the footer chips belong to the character page only
    if ShownPage() ~= 1 then for _, c in pairs(chips) do c.frame:Hide() end end
end

-- The info row (the band of the stock top strip, under the header): the stock level line ("Level 18 Warrior", centred, its class
-- part in a class colour code) is held, frame and text, and the row reads as the mockup's well caption instead: the name in light
-- mono at the left, the race and class in small muted lowercase after it, and an amber "lvl 18" chip at the right, left of the pane
-- toggle. Every part is read from a plain API value (UnitName, UnitRace, UnitClass, UnitLevel); when the level is not a plain number
-- the row is hidden and the stock line is left as it was (restyled amber). Children of the paper doll page, so they go with it.
local INFO = { PAD = 14, GAP = 10, NAME_PX = 13, SUB_PX = 11 }

local function PlainString(v)
    v = Plain(v)
    return type(v) == "string" and v ~= "" and v or nil
end

function Char.InfoText()
    local level = Plain(Try(_G.UnitLevel, "player"))
    if type(level) ~= "number" then return nil end
    -- GetUnitName(unit, true) carries the surname (UnitName gives the first name only on this client)
    local name = PlainString(Try(_G.GetUnitName, "player", true)) or PlainString(Try(_G.UnitName, "player"))
    local race = PlainString(Try(_G.UnitRace, "player"))
    local class = PlainString(Try(_G.UnitClass, "player"))
    local sub = {}
    if race then sub[#sub + 1] = race:lower() end
    if class then sub[#sub + 1] = class:lower() end
    return { name = name and name:lower() or "", sub = table.concat(sub, " "), level = "lvl " .. level }
end

function Char.RefreshLevel()
    local row = S.info
    if not row then return end
    local info = Char.InfoText()
    if not info then
        row.frame:Hide()
        return
    end
    Kit.HoldFrame(_G.PaperDollLevelInfo)
    Kit.HoldFrame(_G.CharacterLevelText)
    row.name:SetText(info.name)
    row.sub:SetText(info.sub)
    -- the race and class follow the name; the level is the first chip of the footer
    local nw = Plain(Try(row.name.GetUnboundedStringWidth or row.name.GetStringWidth, row.name))
    local k = Kit.Ppu(_G.CharacterFrame)
    local x = INFO.PAD + (type(nw) == "number" and math.floor(nw * k + 0.5) or 0) + INFO.GAP
    row.sub:ClearAllPoints()
    Kit.Place(row.sub, row.frame, x, 0, nil, nil, "LEFT", "LEFT", _G.CharacterFrame)
    Char.RefreshChips()
    row.frame:Show()
end

-- The row sits just under the header rule (the stock level line hung lower, where the row ran into the model well); it runs from
-- the window's left edge to the pane toggle. Worked out from the frames' own rects.
function Char.LayoutInfo()
    local row, win = S.info, _G.CharacterFrame
    if not (row and win and S.headPx) then return end
    local function n(f, m) return f and Plain(Try(f[m], f)) end
    local top, left = n(win, "GetTop"), n(win, "GetLeft")
    if type(top) ~= "number" or type(left) ~= "number" then return end
    local ppu = Kit.Ppu(win)
    -- the row hugs the header (the level chip moved to the footer), leaving air between the name and the model well under it
    local hpx = 16
    local cy = S.headPx + 2 + hpx / 2
    local right = n(_G.CharacterFrameRightPaneToggleButton, "GetLeft")
    local wpx = type(right) == "number" and math.floor((right - left) * ppu - 8) or 380
    Kit.Place(row.frame, win, 0, math.floor(cy - hpx / 2 + 0.5), wpx, hpx, "TOPLEFT", "TOPLEFT", win)
end

local function BuildLevel(win)
    local paper = _G.PaperDollFrame
    local host = paper and paper.TopBackgroundStripHost
    if type(paper) ~= "table" or type(host) ~= "table" then return end
    local row = { frame = CreateFrame("Frame", nil, paper) }
    row.frame:SetFrameLevel((paper:GetFrameLevel() or 0) + 5)
    S.info = row
    Char.LayoutInfo()
    row.name = Kit.Label(row.frame, "", INFO.NAME_PX, C.text, "OVERLAY")
    Kit.Place(row.name, row.frame, INFO.PAD, 0, nil, nil, "LEFT", "LEFT", win)
    row.name:SetJustifyH("LEFT")
    row.sub = Kit.Label(row.frame, "", INFO.SUB_PX, C.muted, "OVERLAY")
    row.sub:SetJustifyH("LEFT")
    local line = _G.CharacterLevelText
    if type(line) == "table" then
        for _, m in ipairs({ "SetFormattedText", "SetText" }) do Kit.HookFunc(line, m, Char.RefreshLevel) end
    end
    Char.RefreshLevel()
end

-- The model well: a cut panel behind the 3D model, between the slot columns, from just above the model's zoom row down to just
-- above the weapon row (the mockup's model box). Our own frame on the paper doll page, one level under the model scene so the
-- model draws over it; laid out from the stock slots' own rects after every show and re-seat (they are never moved).
local WELL = { GAP = 8, TOP = 6, CUT = 8 }
Char.WELL = WELL

function Char.LayoutWell()
    local w = S.well
    if not w then return end
    local paper, head, hands, main = _G.PaperDollFrame, _G.CharacterHeadSlot, _G.CharacterHandsSlot, _G.CharacterMainHandSlot
    local control = _G.CharacterModelScene and _G.CharacterModelScene.ControlFrame
    if not (paper and head and hands and main) then return end
    local function n(f, m) return Plain(Try(f[m], f)) end
    local l, r, mt, ht = n(head, "GetRight"), n(hands, "GetLeft"), n(main, "GetTop"), n(head, "GetTop")
    local ct = control and n(control, "GetTop")
    if type(l) ~= "number" or type(r) ~= "number" or type(mt) ~= "number" or type(ht) ~= "number" then return end
    local gap = Kit.U(paper, WELL.GAP)
    local top = math.max(ht, type(ct) == "number" and ct or ht) + Kit.U(paper, WELL.TOP)
    local width, height = (r - l) - 2 * gap, top - (mt + gap)
    if width <= 0 or height <= 0 then return end
    local ppu = Kit.Ppu(paper)
    width, height = math.floor(width * ppu + 0.5) / ppu, math.floor(height * ppu + 0.5) / ppu
    w.frame:ClearAllPoints()
    w.frame:SetPoint("TOPLEFT", head, "TOPRIGHT", gap, top - ht)
    w.frame:SetSize(width, height)
    w.wpx, w.hpx = math.floor(width * ppu + 0.5), math.floor(height * ppu + 0.5)
    if w.plate.ring2 then Kit.Move(w.plate.ring2, 1, 1, w.wpx - 2, w.hpx - 2) end
    if Char.OnWellLayout then pcall(Char.OnWellLayout, w) end
end

local function BuildWell()
    local paper, scene = _G.PaperDollFrame, _G.CharacterModelScene
    if type(paper) ~= "table" or type(scene) ~= "table" then return end
    local frame = CreateFrame("Frame", nil, paper)
    frame:SetFrameLevel(math.max(0, (Plain(Try(scene.GetFrameLevel, scene)) or 1) - 1))
    local w = { frame = frame, plate = Kit.Plate(frame, WELL.CUT, 100, 100) }
    Kit.PaintPlate(w.plate, C.ink, 0.9, C.violet, 1, 1)
    S.well = w
    Char.LayoutWell()
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
-- Open-time cost readout: each step's last and worst run in ms, and the frame times right after the window opens (a texture
-- loaded on first draw shows there, not in a step), in ForeverSTUwaveDB.charTiming (on disk after a /reload). Diagnostic only.
local clock = type(_G.debugprofilestop) == "function" and _G.debugprofilestop or nil
local function Timing()
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" then return nil end
    if type(db.charTiming) ~= "table" then db.charTiming = { steps = {}, opens = {} } end
    return db.charTiming
end

local function Step(name, fn, ...)
    local t0 = clock and clock()
    local ok, err = pcall(fn, ...)
    if t0 then
        local T = Timing()
        if T then
            local ms = clock() - t0
            local r = T.steps[name]
            if not r then r = { last = 0, max = 0, n = 0 }; T.steps[name] = r end
            r.last, r.n = ms, r.n + 1
            if ms > r.max then r.max = ms end
        end
    end
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
    Step("wellLayout", Char.LayoutWell)
    Step("infoLayout", Char.LayoutInfo)
    local win = _G.CharacterFrame
    if win and S.done then ExtendWindow(win) end
    Step("fitPages", Char.FitPages)
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
    Step("well", BuildWell)
    Kit.HookScript(win, "OnShow", function()
        local T = clock and Timing()
        local open = T and { at = (Kit.Now and Kit.Now()) or 0, frames = {} }
        if open then
            T.opens[#T.opens + 1] = open
            while #T.opens > 5 do table.remove(T.opens, 1) end
            -- the next eight frame times (ms) after the window opens
            local watch = S.openWatch or CreateFrame("Frame")
            S.openWatch = watch
            local n = 0
            watch:SetScript("OnUpdate", function(self, elapsed)
                n = n + 1
                open.frames[n] = math.floor(elapsed * 1000 + 0.5)
                if n >= 8 then self:SetScript("OnUpdate", nil) end
            end)
        end
        Kit.Later(function()
            local t0 = clock and clock()
            Relayout(); Refresh()
            if open and t0 then open.passMs = clock() - t0 end
        end)
    end)
    -- the window gains its footer after the stock layout and the right pane folds away with its toggle: lists follow
    Kit.HookScript(win, "OnSizeChanged", function() Kit.Later(function() Step("fitPages", Char.FitPages) end) end)
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
    -- A closed window is refreshed by its OnShow hook, so nothing here while it is shut: the full pass allocates hundreds
    -- of KB, and durability, inventory and regen events land after every fight.
    local win = _G.CharacterFrame
    if not (win and win:IsShown()) then return end
    if event == "PLAYER_REGEN_ENABLED" then Step("extend", ExtendWindow, win) end
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
