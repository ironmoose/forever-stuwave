-- Forever STUwave: Character
-- The character window (CharacterFrame, with its character / reputation / currency sub frames) as a STUwave window, from the
-- approved CHARACTER mockup (mockups/character-spells-2026-11-12.html, section 1).
--
--   * panel chrome in place of the stock frame art, a header band with a glyph, `stuwave://character` (the page name follows
--     the sub frame) and a built-in switch (TabSkins.Switch) for character / reputation / currency. The stock tabs below the
--     window are held and never hit; the switch drives the stock tab's own Click, or the same ToggleCharacter call the key
--     bindings make when the tab has no Click;
--   * every equipment slot wears the shared item slot (a cut plate, the quality ring and LED of Core/ItemSlotSkins.lua, its icon
--     seated in the layer's inset box) and, new here, a WEAR BAR: a 2 px strip up the slot's right edge, as tall as the
--     durability left (cyan above half, amber to a fifth, pink under it, full pink and a pink ring when broken). Durability as a
--     whole is not here: it has its own HUD;
--   * the stat rows keep every stock script and tooltip: their art is held and their text restyled in place (mono, muted
--     label, light value);
--   * footer chips: item level, average wear, worn pieces and the repair bill, each read from a plain API value and left out
--     when the client will not give one.
--
-- Skin only. Slots are secure item buttons: nothing on them is moved, resized, reparented or attributed, and no field is written
-- on them that UseContainerItem reads. Our regions, post-hooks and weak-keyed state only. A slot met in combat is decorated when
-- combat ends. Values are read through FS.IsSecret first.
--
-- Frame names: the 16001 globals dump (Character<Slot>Slot, CharacterFrameTab1..3, CharacterStatsPane, CharacterLevelText,
-- CharacterModelFrameBackground*) and the retail 12.1.0 Blizzard_UIPanels_Game source (CharacterFrame.xml: Tab1..3, Inset,
-- InsetRight, CharacterStatsPane; PaperDollFrame.lua: ToggleCharacter). The dump also lists CharacterFrameModeTab1..6, a
-- layout the reference source does not have; those are left exactly as they are.

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

local G = { HEAD_H = 44, CHIP_H = 20, CHIP_GAP = 8, FOOT_UP = 8, SIDE = 14, WEAR_W = 2, WEAR_INSET = 4, WEAR_PAD = 6 }
Char.GEOM = G

local S = { done = false, slots = {}, chips = {}, decorated = setmetatable({}, { __mode = "k" }), held = setmetatable({}, { __mode = "k" }) }
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

local function SweepSlotArt(button)
    HeldArt.HoldNormal(button)
    for _, f in ipairs(ART_FIELDS) do HeldArt.Hold(button[f]) end
    for _, f in ipairs(GLOW_FIELDS) do HeldArt.Hold(button[f]) end
end

-- A wear bar and a broken ring on a slot: our own regions on the button, laid out from the slot's own pixel size.
local function WearParts(button)
    local w = S.slots[button]
    if w.bar then return w end
    w.bar = Kit.Rect(button, 0, 0, G.WEAR_W, 1, C.cyan, 1, "OVERLAY", 4)
    w.bar:Hide()
    w.track = Kit.Rect(button, 0, 0, G.WEAR_W, 1, C.ink, 0.6, "OVERLAY", 3)
    w.track:Hide()
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
        return
    end
    local pw, ph = Kit.SizePx(button)
    if not pw then return end
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

-- Skins one equipment slot button in place. `unit` is "player" for the paper doll, or a function that answers the unit now (the
-- inspected one); only the player's own slots have wear. Idempotent.
function Char.SkinSlot(button, slotId, unit)
    if type(button) ~= "table" or S.slots[button] then return end
    unit = unit or "player"
    S.slots[button] = { id = slotId, unit = unit }
    SweepSlotArt(button)
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
    Char.PaintWear(button)
end

local function RefreshSlots()
    for button in pairs(S.slots) do
        Char.PaintWear(button)
        if FS.ItemSlotSkins and FS.ItemSlotSkins.Refresh then FS.ItemSlotSkins.Refresh(button) end
    end
end

local function SkinSlots()
    for _, name in ipairs(SLOT_NAMES) do
        local button = _G["Character" .. name .. "Slot"]
        if button then Char.SkinSlot(button, SLOT_ID[name], "player") end
    end
end

-------------------------------------------------------------------------------
-- Stat rows
-------------------------------------------------------------------------------

local function PinColor(fs, color)
    if S.held[fs] or type(fs.SetTextColor) ~= "function" then return end
    S.held[fs] = true
    fs:SetTextColor(color[1], color[2], color[3], 1)
    if type(hooksecurefunc) ~= "function" then return end
    local busy = false
    pcall(hooksecurefunc, fs, "SetTextColor", function(self, r)
        if busy or r == color[1] then return end
        busy = true
        pcall(self.SetTextColor, self, color[1], color[2], color[3], 1)
        busy = false
    end)
end

-- Restyles a stat row (a frame with a background texture and two text regions: label then value) or a category header (one text
-- region) in place. Stock scripts and tooltips stay.
local function RestyleRow(row)
    if type(row) ~= "table" or type(row.GetRegions) ~= "function" then return end
    local texts = {}
    for _, region in ipairs({ row:GetRegions() }) do
        local kind = Try(region.GetObjectType, region)
        if kind == "Texture" then HeldArt.Hold(region)
        elseif kind == "FontString" then texts[#texts + 1] = region end
    end
    if #texts == 1 then
        Kit.RestyleLabel(texts[1], row, 12, C.cyan)
        PinColor(texts[1], C.cyan)
    elseif #texts >= 2 then
        local label, value = row.Label or texts[1], row.Value or texts[2]
        Kit.RestyleLabel(label, row, 12, C.muted)
        PinColor(label, C.muted)
        Kit.RestyleLabel(value, row, 12, C.text)
        PinColor(value, C.text)
    end
end

local function Walk(frame, depth)
    if type(frame) ~= "table" or depth > 6 then return end
    RestyleRow(frame)
    if type(frame.GetChildren) == "function" then
        for _, child in ipairs({ frame:GetChildren() }) do Walk(child, depth + 1) end
    end
end

local function SkinStats()
    local pane = _G.CharacterStatsPane
    if not pane then return end
    Walk(pane, 0)
    for _, field in ipairs({ "ClassBackground" }) do HeldArt.Hold(pane[field]) end
    local value = pane.ItemLevelFrame and pane.ItemLevelFrame.Value
    if value then Kit.RestyleLabel(value, pane, 20, C.amber); PinColor(value, C.amber) end
end

-------------------------------------------------------------------------------
-- Header
-------------------------------------------------------------------------------

local PAGES = {
    { label = "character", frame = "PaperDollFrame", tab = "CharacterFrameTab1" },
    { label = "reputation", frame = "ReputationFrame", tab = "CharacterFrameTab2" },
    { label = "currency", frame = "TokenFrame", tab = "CharacterFrameTab3" },
}

local function ShownPage()
    for i, page in ipairs(PAGES) do
        local f = _G[page.frame]
        if f and Try(f.IsShown, f) == true then return i end
    end
    return 1
end

local function GoTo(i)
    local page = PAGES[i]
    local tab = _G[page.tab]
    if tab and type(tab.Click) == "function" then
        pcall(tab.Click, tab)
    elseif type(_G.ToggleCharacter) == "function" then
        pcall(_G.ToggleCharacter, page.frame, true)
    end
end

function Char.RefreshHeader()
    local h = S.header
    if not h then return end
    local i = ShownPage()
    h.switch:SetSelected(i, true)
    h.title:SetText("stuwave://" .. PAGES[i].label)
    for j, page in ipairs(PAGES) do
        local tab = _G[page.tab]
        -- a tab the client keeps hidden (currency before it unlocks) cannot be reached by its switch item either
        local off = tab and Try(tab.IsShown, tab) == false and j ~= i
        h.switch:SetDisabled(j, off and true or false)
    end
end

-- A person glyph from one pixel runs: head and shoulders.
local function Glyph(win, x, y, color)
    local out = {}
    local runs = { { 4, 0, 6, 2 }, { 3, 2, 8, 4 }, { 0, 7, 14, 2 }, { 0, 9, 14, 7 } }
    for _, r in ipairs(runs) do out[#out + 1] = Kit.Rect(win, x + r[1] * 2, y + r[2] * 2, r[3] * 2, r[4] * 2, color, 1, "OVERLAY", 3) end
    return out
end

local function BuildHeader(win)
    local W = Kit.SizePx(win) or 540
    local top = Kit.Rect(win, 7, 1, W - 8, 5, C.band, 1, "ARTWORK", 0)
    local band = Kit.Rect(win, 1, 6, W - 2, G.HEAD_H - 6, C.band, 1, "ARTWORK", 0)
    local rule = Kit.Rect(win, 1, G.HEAD_H, W - 2, 1, C.violet, 1, "ARTWORK", 1)
    local glyph = Glyph(win, 16, 12, C.cyan)
    local title = Kit.Label(win, "stuwave://character", 16, C.muted, "OVERLAY")
    Kit.Place(title, win, 52, G.HEAD_H / 2, nil, nil, "LEFT", "TOPLEFT")
    title:SetJustifyH("LEFT")

    local labels = {}
    for i, page in ipairs(PAGES) do labels[i] = page.label end
    local sw = FS.TabSkins and FS.TabSkins.Switch and FS.TabSkins.Switch(win, labels, {
        selected = ShownPage(), onSelect = function(i) GoTo(i) end,
    })
    if sw then
        Kit.Place(sw.frame, win, -48, 8, sw.width, 28, "TOPRIGHT", "TOPRIGHT")
        for _, page in ipairs(PAGES) do
            local tab = _G[page.tab]
            if tab then
                Kit.HoldFrame(tab)
                if tab.EnableMouse then pcall(tab.EnableMouse, tab, false) end
            end
        end
    end
    S.header = { switch = sw, title = title, band = { top, band, rule }, glyph = glyph }
    if not sw then S.header = nil end

    Kit.HoldFrame(_G.CharacterFrameTitleText)
    HeldArt.Hold(_G.CharacterFramePortrait)
    for _, page in ipairs(PAGES) do
        Kit.HookScript(_G[page.frame], "OnShow", Char.RefreshHeader)
    end
    if Theme.SkinCloseButton then pcall(Theme.SkinCloseButton, win) end
    Char.RefreshHeader()
end

-------------------------------------------------------------------------------
-- Footer chips
-------------------------------------------------------------------------------

local function Chip(win, color)
    local chip = CreateFrame("Frame", nil, win)
    chip:SetFrameLevel((win:GetFrameLevel() or 0) + 6)
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
    local w = #text * 12 * 0.5615 + 16
    w = math.floor(w + 0.5)
    c.w = w
    if right then
        Kit.Place(c.frame, c.frame:GetParent(), -(G.SIDE), -G.FOOT_UP, w, G.CHIP_H, "BOTTOMRIGHT", "BOTTOMRIGHT")
    else
        Kit.Place(c.frame, c.frame:GetParent(), x, -G.FOOT_UP, w, G.CHIP_H, "BOTTOMLEFT", "BOTTOMLEFT")
    end
    c.plate.w = w
    return w
end

local function BuildChips(win)
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
    -- the footer belongs to the character page only
    local onChar = ShownPage() == 1
    for _, c in pairs(chips) do if not onChar then c.frame:Hide() end end
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
    "CharacterModelFrameBackgroundBotRight", "CharacterLevelTextBackground", "CharacterFrameRightPaneHostStoneBg",
}

local function Refresh()
    if not S.done then return end
    Step("slots", SkinSlots)
    Step("slotsRefresh", RefreshSlots)
    Step("stats", SkinStats)
    Step("chips", Char.RefreshChips)
    Step("header", Char.RefreshHeader)
end

local function Build()
    local win = _G.CharacterFrame
    if not win or S.done or InCombat() then return end
    S.done = true
    win.fsCharacterSkin = true
    PanelSkins.StripNamed(STRIP)
    Step("chrome", function()
        Theme.StripBlizzardChrome(win)
        Theme.AddPanelChrome(win, { fillColor = C.panel, accent = C.violet, glowAlpha = 0.30 })
    end)
    Step("art", function() for _, name in ipairs(MODEL_ART) do HeldArt.Hold(_G[name]) end end)
    Step("header", BuildHeader, win)
    Step("chips", BuildChips, win)
    Step("level", function()
        local level = _G.CharacterLevelText
        if level then Kit.RestyleLabel(level, win, 12, C.amber); PinColor(level, C.amber) end
    end)
    Kit.HookScript(win, "OnShow", function() Kit.Later(Refresh) end)
    Kit.OnReseat(Refresh)
    Refresh()
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "UPDATE_INVENTORY_DURABILITY", "PLAYER_EQUIPMENT_CHANGED", "PLAYER_AVG_ITEM_LEVEL_UPDATE",
    "UNIT_INVENTORY_CHANGED", "PLAYER_ENTERING_WORLD", "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED", "PLAYER_LEVEL_UP" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function(_, event)
    if not S.done then return end
    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
        Kit.Reseat()
        return
    end
    Step("refresh", Refresh)
end)

if type(_G.PaperDollFrame_UpdateStats) == "function" then
    Kit.HookFunc(_G, "PaperDollFrame_UpdateStats", function() if S.done then Kit.Later(function() Step("stats", SkinStats) end) end end)
end

PanelSkins.RegisterInspect("Character", { { name = "CharacterFrame", guard = "fsCharacterSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
