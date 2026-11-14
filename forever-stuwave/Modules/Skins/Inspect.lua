-- Forever STUwave: Inspect
-- The inspect window (InspectFrame) from the approved INSPECT mockup (mockups/character-spells-2026-11-12.html, section 2): the
-- paper doll's chrome and header band (stuwave://inspect with a built-in switch for the stock tabs), every equipment slot wearing the
-- shared item slot, and a DELTA CHIP on each slot: the item level of their piece against the piece you wear in the same slot, cyan
-- when theirs is higher, pink when lower, nothing when level, empty or unreadable. Rings and trinkets compare against your best of
-- the pair. Footer chips: their item level and how it stands against yours ("vs you +9": theirs minus yours).
--
-- The model well: the stock background and border art held, a GUNSIGHT of four cyan corner brackets (an L of ten pixels, three in
-- from each corner) around it, the model control panel's keys as square keys (Char.SkinSquare, the paper doll's own), the stock
-- level line held and its text mirrored on an amber chip in the well's bottom left (the stock line is anchored inside the header
-- band, so it cannot stay where it is: nothing of a Blizzard frame is moved), the stock slot frames (Char-LeftSlot and friends)
-- held, and the two stock text buttons (view in dressing room, talents) skinned by PanelSkins.SweepOnShow.
--
-- Skin only. Every stock script, tooltip and tab stays; the stock tabs are held and the switch drives their own Click. No slot is
-- moved, resized, reparented or attributed. Item levels come from C_Item.GetDetailedItemLevelInfo on the item link and from
-- C_PaperDollInfo.GetInspectItemLevel; both are read through FS.IsSecret and a chip is hidden for anything that is not a plain
-- number (an item the client has not cached yet fills in on GET_ITEM_INFO_RECEIVED). There is no wear on another player's gear.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the scan
-- line that sweeps the model on open and the gunsight's flicker, the name and race lines drawn inside the well (the level line is
-- the stock one, mirrored), the wear brackets on the body (no wear data for another player), the PvP and guild
-- pages and the talents tab (their own windows), the socket display next to a slot (functional, left stock).
--
-- Names: the 16001 dump (InspectFrame, InspectFrameInset, InspectFrameTab1/2, Inspect<Slot>Slot, InspectPaperDollFrame,
-- InspectModelFrame, InspectFrameTitleText) and the retail 12.1.0 Blizzard_InspectUI (InspectModelFrame with its Background* and
-- Border* textures and the ModelWithControlsTemplate control panel, InspectLevelText, Inspect<Slot>SlotFrame). The window's own
-- `unit` field is the stock InspectFrame.unit. The LoD addon is picked up when it loads.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and Char and PanelSkins and PanelSkins.RequireExport(
    Theme.AddPanelChrome and Theme.StripBlizzardChrome and Theme.ApplyMono,
    "Inspect.lua disabled: FS.Theme chrome helpers, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then return end

local Insp = {}
FS.InspectSkin = Insp

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, band = Theme.COLOR_CTRL_BAND or { 0.102, 0.051, 0.173 }, ink = Theme.COLOR_CTRL_INK,
    panel = { 0.071, 0.039, 0.133, 0.96 },
}

local G = { HEAD_H = 44, CHIP_H = 20, CHIP_GAP = 8, FOOT_UP = 8, SIDE = 14, DELTA_H = 14, DELTA_X = -4, DELTA_Y = -4 }
Insp.GEOM = G

local S = { done = false, deltas = setmetatable({}, { __mode = "k" }), chips = {} }
Insp.state = S

local function Plain(v) return Kit.Plain(v) end
local function Try(fn, ...) return Kit.Try(fn, ...) end

local function UnitNow()
    local win = _G.InspectFrame
    local unit = win and Plain(win.unit)
    if type(unit) == "string" then return unit end
    return "target"
end
Insp.UnitNow = UnitNow

-- The item level of the piece in `unit`'s slot, nil when it is empty or the client will not say plainly.
local function PieceLevel(unit, slotId)
    if type(_G.GetInventoryItemLink) ~= "function" then return nil end
    local link = Plain(Try(_G.GetInventoryItemLink, unit, slotId))
    if type(link) ~= "string" then return nil end
    local info = type(_G.C_Item) == "table" and _G.C_Item.GetDetailedItemLevelInfo
    if type(info) ~= "function" then return nil end
    local level = Plain(Try(info, link))
    if type(level) ~= "number" or level <= 0 then return nil end
    return level
end
Insp.PieceLevel = PieceLevel

-- What to compare against: your piece in the same slot; a ring or trinket against the better of your pair.
local PAIR = { [11] = { 11, 12 }, [12] = { 11, 12 }, [13] = { 13, 14 }, [14] = { 13, 14 } }
local function MineFor(slotId)
    local best
    for _, id in ipairs(PAIR[slotId] or { slotId }) do
        local level = PieceLevel("player", id)
        if level and (not best or level > best) then best = level end
    end
    return best
end

-- Their level minus yours for a slot; nil when either side is empty or unreadable, or the two are level.
function Insp.Delta(slotId, unit)
    local theirs = PieceLevel(unit or UnitNow(), slotId)
    local mine = MineFor(slotId)
    if not theirs or not mine or theirs == mine then return nil end
    return theirs - mine
end

local function DeltaParts(button)
    local d = S.deltas[button]
    if d.plate then return d end
    d.plate = Kit.Rect(button, G.DELTA_X, G.DELTA_Y, 20, G.DELTA_H, C.ink, 1, "OVERLAY", 6)
    d.label = Kit.Label(button, "", 11, C.cyan, "OVERLAY")
    d.label:SetDrawLayer("OVERLAY", 7)
    Kit.Place(d.label, button, G.DELTA_X + 10, G.DELTA_Y + G.DELTA_H / 2, nil, nil, "CENTER", "TOPLEFT")
    d.plate:Hide()
    d.label:Hide()
    return d
end

function Insp.PaintDelta(button)
    local d = S.deltas[button]
    if not d then return end
    local parts = DeltaParts(button)
    local delta = Insp.Delta(d.id)
    if not delta then
        parts.plate:Hide()
        parts.label:Hide()
        return
    end
    local color = delta > 0 and C.cyan or C.pink
    local text = (delta > 0 and "+" or "-") .. math.abs(math.floor(delta))
    parts.label:SetText(text)
    parts.label:SetTextColor(color[1], color[2], color[3], 1)
    local w = math.floor(#text * 11 * 0.5615 + 8)
    Kit.Move(parts.plate, G.DELTA_X, G.DELTA_Y, w, G.DELTA_H)
    Kit.Move(parts.label, G.DELTA_X + w / 2, G.DELTA_Y + G.DELTA_H / 2)
    parts.plate:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.92)
    parts.plate:Show()
    parts.label:Show()
end

-- The stock slot frame (Char-LeftSlot, Char-RightSlot, Char-BottomSlot: the named `$parentFrame` region) and the corner piece the
-- main hand carries: decoration the shared slot replaces.
local function HoldSlotFrame(button, name)
    HeldArt.Hold(_G["Inspect" .. name .. "SlotFrame"])
    for _, region in ipairs(Char.List(button, "GetRegions")) do
        local atlas = Char.AtlasOf(region)
        if atlas and atlas:find("^Char%-") then HeldArt.Hold(region) end
    end
end

local function SkinSlots()
    for _, name in ipairs(Char.SLOT_NAMES) do
        local button = _G["Inspect" .. name .. "Slot"]
        if button then
            local id = Plain(Try(button.GetID, button))
            if type(id) == "number" then
                Char.SkinSlot(button, id, UnitNow)
                HoldSlotFrame(button, name)
                S.deltas[button] = S.deltas[button] or { id = id }
                Insp.PaintDelta(button)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- The model well, the level line and the stock buttons
-------------------------------------------------------------------------------

local MODEL_ART = {
    "InspectModelFrameBackgroundTopLeft", "InspectModelFrameBackgroundTopRight", "InspectModelFrameBackgroundBotLeft",
    "InspectModelFrameBackgroundBotRight", "InspectModelFrameBackgroundOverlay",
    "InspectModelFrameBorderTopLeft", "InspectModelFrameBorderTopRight", "InspectModelFrameBorderBottomLeft",
    "InspectModelFrameBorderBottomRight", "InspectModelFrameBorderLeft", "InspectModelFrameBorderRight",
    "InspectModelFrameBorderTop", "InspectModelFrameBorderBottom", "InspectModelFrameBorderBottom2",
}
local MODEL_KEYS = { "BackgroundTopLeft", "BackgroundTopRight", "BackgroundBotLeft", "BackgroundBotRight", "BackgroundOverlay" }
local RET = { MARGIN = 3, ARM = 10 }
Insp.RETICLE = RET

local function ControlFrameOf(model)
    local control = model.controlFrame
    if type(control) ~= "table" then control = model.ControlFrame end
    return type(control) == "table" and control or nil
end

-- The stock background and border art of the well and the panel behind the control keys, held at alpha 0.
local function HoldModelArt(model)
    for _, name in ipairs(MODEL_ART) do HeldArt.Hold(_G[name]) end
    for _, key in ipairs(MODEL_KEYS) do HeldArt.Hold(model[key]) end
    local control = ControlFrameOf(model)
    if control then
        for _, region in ipairs(Char.List(control, "GetRegions")) do
            if Try(region.GetObjectType, region) == "Texture" then HeldArt.Hold(region) end
        end
    end
end

-- The gunsight: an L at each corner of the well, laid out from the model's own pixel size (re-laid on a reseat).
local function PlaceReticle(model)
    local r = S.reticle
    local W, H = Kit.SizePx(model)
    if not (r and W and H) then return end
    local m, L = RET.MARGIN, RET.ARM
    local spots = {
        { m, m, L, 1 }, { m, m + 1, 1, L - 1 },
        { W - m - L, m, L, 1 }, { W - m - 1, m + 1, 1, L - 1 },
        { m, H - m - 1, L, 1 }, { m, H - m - L, 1, L - 1 },
        { W - m - L, H - m - 1, L, 1 }, { W - m - 1, H - m - L, 1, L - 1 },
    }
    for i, p in ipairs(spots) do Kit.Move(r[i], p[1], p[2], p[3], p[4]) end
end

local function BuildReticle(model)
    if S.reticle then return end
    S.reticle = {}
    for i = 1, 8 do S.reticle[i] = Kit.Rect(model, 0, 0, 1, 1, C.cyan, 1, "OVERLAY", 5) end
    PlaceReticle(model)
end

-- The model control keys (zoom, pan, rotate, reset): square keys with a cyan icon, found by shape under the control panel.
local function SkinModelControls(model)
    local control = ControlFrameOf(model)
    if not (control and Char.SkinSquare and Char.PaintSquare) then return end
    for _, child in ipairs(Char.List(control, "GetChildren")) do
        if type(child) == "table" and Try(child.GetObjectType, child) == "Button" then
            local icon = child.icon
            if type(icon) ~= "table" then icon = child.Icon end
            if Char.SkinSquare(child, { icon = type(icon) == "table" and icon or nil, tint = C.cyan }) then Char.PaintSquare(child) end
        end
    end
end

local function SkinModel(win)
    local model = _G.InspectModelFrame
    if type(model) == "table" then
        HoldModelArt(model)
        BuildReticle(model)
        SkinModelControls(model)
    end
    local doll = _G.InspectPaperDollFrame
    if type(doll) == "table" then PanelSkins.SweepOnShow(doll) end
end

-------------------------------------------------------------------------------
-- Header and footer
-------------------------------------------------------------------------------

local TAB_MAX = 4

local function Tabs()
    local list = {}
    for i = 1, TAB_MAX do
        local tab = _G["InspectFrameTab" .. i]
        if tab and type(tab.Click) == "function" and Try(tab.IsShown, tab) ~= false then
            local text = Plain(Try(tab.GetText, tab))
            list[#list + 1] = { tab = tab, label = type(text) == "string" and text ~= "" and text:lower() or ("tab " .. i), index = i }
        end
    end
    return list
end

function Insp.RefreshHeader()
    local h = S.header
    if not h then return end
    local win = _G.InspectFrame
    local selected = Plain(win and win.selectedTab)
    for pos, t in ipairs(h.tabs) do
        if t.index == selected then h.switch:SetSelected(pos, true) end
    end
end

local function BuildHeader(win)
    local W = Kit.SizePx(win) or 440
    Kit.Rect(win, 7, 1, W - 8, 5, C.band, 1, "ARTWORK", 0)
    Kit.Rect(win, 1, 6, W - 2, G.HEAD_H - 6, C.band, 1, "ARTWORK", 0)
    Kit.Rect(win, 1, G.HEAD_H, W - 2, 1, C.violet, 1, "ARTWORK", 1)
    -- an eye glyph: the lock-on scan
    for _, r in ipairs({ { 4, 4, 14, 2 }, { 2, 6, 18, 2 }, { 0, 8, 22, 4 }, { 2, 12, 18, 2 }, { 4, 14, 14, 2 }, { 9, 7, 4, 6 } }) do
        Kit.Rect(win, 16 + r[1], 14 + r[2] - 2, r[3], r[4], r[1] == 9 and C.pink or C.cyan, 1, "OVERLAY", 3)
    end
    local title = Kit.Label(win, "stuwave://inspect", 16, C.muted, "OVERLAY")
    Kit.Place(title, win, 52, G.HEAD_H / 2, nil, nil, "LEFT", "TOPLEFT")
    title:SetJustifyH("LEFT")
    local tabs = Tabs()
    local labels = {}
    for i, t in ipairs(tabs) do labels[i] = t.label end
    if #labels > 1 and FS.TabSkins and FS.TabSkins.Switch then
        local sw = FS.TabSkins.Switch(win, labels, { onSelect = function(i)
            local tab = tabs[i] and tabs[i].tab
            if tab then pcall(tab.Click, tab) end
        end })
        Kit.Place(sw.frame, win, -48, 8, sw.width, 28, "TOPRIGHT", "TOPRIGHT")
        S.header = { switch = sw, tabs = tabs }
        for _, t in ipairs(tabs) do
            Kit.HoldFrame(t.tab)
            if t.tab.EnableMouse then pcall(t.tab.EnableMouse, t.tab, false) end
        end
        Kit.HookFunc(_G, "InspectSwitchTabs", Insp.RefreshHeader)
        Kit.HookFunc(_G, "InspectFrameTab_OnClick", Insp.RefreshHeader)
    end
    Kit.HoldFrame(_G.InspectFrameTitleText)
    HeldArt.Hold(_G.InspectFramePortrait)
    if Theme.SkinCloseButton then pcall(Theme.SkinCloseButton, win) end
end

local function Chip(win, color, parent)
    parent = parent or win
    local chip = CreateFrame("Frame", nil, parent)
    chip:SetFrameLevel((parent:GetFrameLevel() or 0) + 6)
    local c = { frame = chip, color = color }
    c.plate = Kit.Plate(chip, 4, 40, G.CHIP_H)
    Kit.PaintPlate(c.plate, C.ink, 1, color, 1, 1)
    c.label = Kit.Label(chip, "", 12, color, "OVERLAY")
    Kit.Place(c.label, chip, 8, G.CHIP_H / 2, nil, nil, "LEFT", "TOPLEFT")
    c.label:SetJustifyH("LEFT")
    return c
end

local function Put(c, text, x)
    if not text then c.frame:Hide() return x end
    c.label:SetText(text)
    local w = math.floor(#text * 12 * 0.5615 + 16 + 0.5)
    Kit.Place(c.frame, c.frame:GetParent(), x, -G.FOOT_UP, w, G.CHIP_H, "BOTTOMLEFT", "BOTTOMLEFT")
    c.frame:Show()
    return x + w + G.CHIP_GAP
end

local function MyLevel()
    if type(_G.GetAverageItemLevel) ~= "function" then return nil end
    local _, equipped = Try(_G.GetAverageItemLevel)
    equipped = Plain(equipped)
    return type(equipped) == "number" and equipped or nil
end

function Insp.RefreshChips()
    local c = S.chips
    if not c.ilvl then return end
    local theirs
    if type(_G.C_PaperDollInfo) == "table" and _G.C_PaperDollInfo.GetInspectItemLevel then
        theirs = Plain(Try(_G.C_PaperDollInfo.GetInspectItemLevel, UnitNow()))
    end
    if type(theirs) ~= "number" or theirs <= 0 then theirs = nil end
    local x = G.SIDE
    x = Put(c.ilvl, theirs and ("ilvl " .. math.floor(theirs + 0.5)), x)
    local mine = MyLevel()
    local diff = theirs and mine and math.floor(theirs - mine + 0.5)
    local color = diff and diff < 0 and C.pink or C.cyan
    c.you.label:SetTextColor(color[1], color[2], color[3], 1)
    Kit.PaintPlate(c.you.plate, C.ink, 1, color, 1, 1)
    Put(c.you, diff and diff ~= 0 and ("vs you " .. (diff > 0 and "+" or "-") .. math.abs(diff)) or nil, x)
end

-- The stock level line (InspectLevelText, anchored 27 units under the window's top edge, which is inside our header band) is held,
-- and its text is mirrored on an amber chip in the model well's bottom left: LEVEL.X pixels in from the left and LEVEL.UP up from the
-- bottom, clear of the gunsight. The stock line is held only once its text has been read plainly; a text the client will not give
-- plainly hides the chip. The class colour is an escape inside the string and carries over.
local LEVEL = { X = 12, UP = 12 }
Insp.LEVEL = LEVEL

local function Visible(text) return (text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")) end

function Insp.RefreshLevel()
    local c = S.chips.level
    local line, model = _G.InspectLevelText, _G.InspectModelFrame
    if not (c and type(line) == "table" and type(model) == "table") then return end
    local text = Plain(Try(line.GetText, line))
    if type(text) ~= "string" or text == "" then c.frame:Hide() return end
    Kit.HoldFrame(line)
    local W = Kit.SizePx(model)
    local w = math.floor(#Visible(text) * 12 * 0.5615 + 16 + 0.5)
    if W then w = math.min(w, W - 2 * LEVEL.X) end
    c.label:SetText(text)
    if c.label.SetWordWrap then pcall(c.label.SetWordWrap, c.label, false) end
    Kit.Place(c.frame, model, LEVEL.X, -LEVEL.UP, w, G.CHIP_H, "BOTTOMLEFT", "BOTTOMLEFT")
    Kit.Place(c.label, c.frame, 8, G.CHIP_H / 2, w - 16, G.CHIP_H, "LEFT", "TOPLEFT")
    c.frame:Show()
end

function Insp.Refresh()
    if not S.done then return end
    SkinSlots()
    local model = _G.InspectModelFrame
    if type(model) == "table" then PlaceReticle(model) end
    for button in pairs(S.deltas) do Insp.PaintDelta(button) end
    Insp.RefreshChips()
    Insp.RefreshLevel()
    Insp.RefreshHeader()
end

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("inspect:" .. name, ("|cffff4488Forever STUwave|r: inspect skin step '%s' failed: %s"):format(name, tostring(err)))
    end
end

local STRIP = { "InspectFrameInset", "InspectPaperDollFrame" }

local function Build()
    local win = _G.InspectFrame
    if not win or S.done or (type(InCombatLockdown) == "function" and InCombatLockdown()) then return end
    S.done = true
    win.fsInspectSkin = true
    PanelSkins.StripNamed(STRIP)
    Step("chrome", function()
        Theme.StripBlizzardChrome(win)
        Theme.AddPanelChrome(win, { fillColor = C.panel, accent = C.violet, glowAlpha = 0.30 })
    end)
    Step("header", BuildHeader, win)
    Step("chips", function()
        local doll = _G.InspectPaperDollFrame
        S.chips = { ilvl = Chip(win, C.amber), you = Chip(win, C.cyan), level = type(doll) == "table" and Chip(win, C.amber, doll) or nil }
        local line = _G.InspectLevelText
        if type(line) == "table" then
            for _, m in ipairs({ "SetFormattedText", "SetText" }) do Kit.HookFunc(line, m, Insp.RefreshLevel) end
        end
    end)
    Step("model", SkinModel, win)
    Kit.HookScript(win, "OnShow", function() Kit.Later(function() Step("refresh", Insp.Refresh) end) end)
    Kit.OnReseat(Insp.Refresh)
    Step("refresh", Insp.Refresh)
end

local watcher = CreateFrame("Frame")
for _, event in ipairs({ "INSPECT_READY", "PLAYER_EQUIPMENT_CHANGED", "UNIT_INVENTORY_CHANGED", "GET_ITEM_INFO_RECEIVED",
    "PLAYER_AVG_ITEM_LEVEL_UPDATE", "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED" }) do
    pcall(watcher.RegisterEvent, watcher, event)
end
watcher:SetScript("OnEvent", function(_, event)
    if not S.done then return end
    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then Kit.Reseat() return end
    Step("refresh", Insp.Refresh)
end)

PanelSkins.RegisterInspect("Inspect", { { name = "InspectFrame", guard = "fsInspectSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
