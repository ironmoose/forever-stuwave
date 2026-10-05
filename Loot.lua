-- Forever Synthwave: Loot
-- FIRST PASS synthwave PANEL skin for the loot windows: LootFrame and the
-- four group-loot roll frames GroupLootFrame1..4 (GroupLootContainer is their
-- parent; both confirmed present on interface 16001). LootFrame itself is the
-- modern retail ScrollBox loot window on this client, not the classic
-- LootButton1..4 button row: the 16001 globals dump has LootFrame/
-- LootFrameMixin/LootFrameElementMixin/LootFrameItemElementMixin/
-- LootFrameBaseElementMixin present and NO LootButtonN globals at all, so the
-- prior LootButtonN-based slot skin was dead code (never ran). Loot slot rows
-- are skinned instead through FS.PanelSkins.ApplyGuts' `rows` primitive over
-- LootFrame.ScrollBox -- see LootRowUpdateChild below for the row/field
-- shape and its sourcing. GroupLootFrame1..4 are unchanged from the prior
-- pass. UNVALIDATED in-game: no /fstack or visual check done yet.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local SkinButton = FS.Theme.SkinButton
local ApplyMono = FS.Theme.ApplyMono
local StyleMoney = FS.Theme.StyleMoney
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER

if not FS.PanelSkins.RequireExport(SkinPanel, "Loot.lua disabled: FS.Theme.SkinPanel missing") then return end

local GROUP_LOOT_FRAME_COUNT = 4 -- GroupLootFrame1..4, confirmed present

-------------------------------------------------------------------------------
-- Panel skin (idempotent via frame.fsSkinCache; re-shown on OnShow since
-- both LootFrame and the roll frames toggle Show/Hide per loot/roll rather
-- than being created fresh each time)
-------------------------------------------------------------------------------

local function SkinLootPanel(frame)
    FS.PanelSkins.SkinPanelCached(frame, {
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
    })
end

local function HookLootShow(frame)
    FS.PanelSkins.HookShowOnce(frame, "fsLootShowHooked", SkinLootPanel)
end

-------------------------------------------------------------------------------
-- Quantity text (plain Mononoki)
-------------------------------------------------------------------------------

local function StyleCountText(name)
    local fs = _G[name]
    if fs and fs.SetFont and ApplyMono then
        local _, size = fs:GetFont()
        ApplyMono(fs, size or 11)
    end
end

-------------------------------------------------------------------------------
-- Loot slot rows (LootFrame.ScrollBox)
-------------------------------------------------------------------------------

-- One-time per-row setup for a LootFrame ScrollBox row (FS.PanelSkins.ApplyGuts'
-- `rows.perRow`, re-run over every acquired row on each Update -- see
-- ApplyGutsRows in PanelSkins.lua). `row.Item` (an ItemButton widget) is
-- confirmed via retail Blizzard_UIPanels_Game/LootFrame.xml's
-- LootFrameElementTemplate (parentKey="Item"); not every row carries one (a
-- money/currency-only element may not use the item template), so it's
-- feature-detected rather than assumed. `item.Count` (the stack quantity
-- text) and `item.IconBorder` (the quality border, vertex-colored per-item by
-- SetItemButtonQuality) are confirmed via Blizzard_ItemButton's
-- ItemButtonTemplate.lua and LootFrame.lua's own `self.Item.Count:SetText`/
-- `SetItemButtonQuality(self.Item, quality, ...)` calls, and corroborated by
-- ElvUI's Game/Mainline/Skins/Loot.lua (`item.IconBorder`, `item.icon`).
-- `item.IconBorder` is deliberately left untouched -- it IS the quality
-- signal, and Theme.SkinButton's own border/glow is a separate OVERLAY
-- texture layered on top, never a replacement for it.
--
-- `row.Text` (the item name FontString, confirmed via LootFrame.lua) gets a
-- font-only change. Its quality tint lives in the VERTEX-COLOR channel
-- (LootFrame.lua:279-281 calls `self.Text:SetVertexColor(...)`), which
-- Theme.ApplyMono never touches -- it only calls SetFont + SetTextColor.
-- Capturing GetTextColor and feeding it straight back as ApplyMono's color
-- argument just keeps the template's own BASE text color unchanged instead
-- of defaulting to Theme.ApplyFontGeneric's plain white, so Blizzard's vertex
-- tint keeps compositing against the same base it always did. Only
-- currency/money elements have no `.Text` (see LootFrameMoneyElementTemplate
-- in the same XML), so it's feature-detected too.
local function LootRowUpdateChild(row)
    if row.fsLootRowSkinned then return end
    local item = row.Item
    if not item then return end
    row.fsLootRowSkinned = true

    if SkinButton then
        SkinButton(item, { count = item.Count })
    end

    if ApplyMono and row.Text and row.Text.SetFont and row.Text.GetTextColor then
        local _, size = row.Text:GetFont()
        local r, g, b, a = row.Text:GetTextColor()
        ApplyMono(row.Text, size or 11, { r or 1, g or 1, b or 1, a or 1 })
    end
end

-------------------------------------------------------------------------------
-- LootFrame
-------------------------------------------------------------------------------

local function ApplyLootFrame()
    local frame = LootFrame
    if not frame then return end

    SkinLootPanel(frame)
    HookLootShow(frame)

    if StyleMoney then
        StyleMoney(_G["LootFrameMoneyFrame"])
    end

    FS.PanelSkins.ApplyGuts({
        { parent = "LootFrame", rows = { scrollBox = "LootFrame.ScrollBox", perRow = LootRowUpdateChild } },
    })
end

-------------------------------------------------------------------------------
-- Group loot (need/greed/disenchant roll popups)
-------------------------------------------------------------------------------

local function ApplyGroupLoot()
    for i = 1, GROUP_LOOT_FRAME_COUNT do
        local frame = _G["GroupLootFrame" .. i]
        if frame then
            SkinLootPanel(frame)
            HookLootShow(frame)
            StyleCountText("GroupLootFrame" .. i .. "Count")
        end
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Loot/roll frames are plain non-secure frames, so none of this is
-- combat-illegal; deferred anyway for consistency with the rest of the
-- addon's Init pattern.
local function Apply()
    ApplyLootFrame()
    ApplyGroupLoot()
end

FS.PanelSkins.RegisterRecon("Loot", {
    { name = "LootFrame", guard = "fsSkinCache" },
    { name = "GroupLootFrame1", guard = "fsSkinCache" },
    { name = "GroupLootFrame2", guard = "fsSkinCache" },
    { name = "GroupLootFrame3", guard = "fsSkinCache" },
    { name = "GroupLootFrame4", guard = "fsSkinCache" },
})

FS.PanelSkins.DeferCombat(Apply)
