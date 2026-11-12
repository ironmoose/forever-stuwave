-- Forever STUwave: Inspect
-- The inspect window (InspectFrame) from the approved INSPECT mockup (mockups/character-spells-2026-11-12.html, section 2): the
-- paper doll's chrome and header band (stuwave://inspect with a built-in switch for the stock tabs), every equipment slot wearing the
-- shared item slot, and a DELTA CHIP on each slot: the item level of their piece against the piece you wear in the same slot, cyan
-- when theirs is higher, pink when lower, nothing when level, empty or unreadable. Rings and trinkets compare against your best of
-- the pair. Footer chips: their item level and how it stands against yours ("vs you +9": theirs minus yours).
--
-- Skin only. Every stock script, tooltip and tab stays; the stock tabs are held and the switch drives their own Click. No slot is
-- moved, resized, reparented or attributed. Item levels come from C_Item.GetDetailedItemLevelInfo on the item link and from
-- C_PaperDollInfo.GetInspectItemLevel; both are read through FS.IsSecret and a chip is hidden for anything that is not a plain
-- number (an item the client has not cached yet fills in on GET_ITEM_INFO_RECEIVED). There is no wear on another player's gear.
--
-- Names: the 16001 dump (InspectFrame, InspectFrameInset, InspectFrameTab1/2, Inspect<Slot>Slot, InspectPaperDollFrame,
-- InspectModelFrame, InspectFrameTitleText) and the retail 12.1.0 Blizzard_InspectUI. The window's own `unit` field is the stock
-- InspectFrame.unit. The LoD addon is picked up when it loads.

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

local function SkinSlots()
    for _, name in ipairs(Char.SLOT_NAMES) do
        local button = _G["Inspect" .. name .. "Slot"]
        if button then
            local id = Plain(Try(button.GetID, button))
            if type(id) == "number" then
                Char.SkinSlot(button, id, UnitNow)
                S.deltas[button] = S.deltas[button] or { id = id }
                Insp.PaintDelta(button)
            end
        end
    end
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

local function Chip(win, color)
    local chip = CreateFrame("Frame", nil, win)
    chip:SetFrameLevel((win:GetFrameLevel() or 0) + 6)
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

function Insp.Refresh()
    if not S.done then return end
    SkinSlots()
    for button in pairs(S.deltas) do Insp.PaintDelta(button) end
    Insp.RefreshChips()
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
    Step("chips", function() S.chips = { ilvl = Chip(win, C.amber), you = Chip(win, C.cyan) } end)
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
