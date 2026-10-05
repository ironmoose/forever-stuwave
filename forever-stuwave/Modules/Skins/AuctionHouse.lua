-- Forever STUwave: Auction House
-- FIRST PASS synthwave PANEL skin for the Auction House. The AH is
-- load-on-demand and its frame name differs by client: modern retail uses
-- AuctionHouseFrame (Blizzard_AuctionHouseUI), classic/TBC uses AuctionFrame
-- (Blizzard_AuctionUI). Both are feature-detected; only whichever exists on
-- this client gets skinned -- confirmed via the 16001 globals dump that this
-- client is the modern retail AH (AuctionHouseFrameMixin/
-- AuctionHouseBrowseResultsFrameMixin/AuctionHouseItemListMixin/
-- AuctionHouseItemListLineMixin are present; classic's AuctionFrame/
-- BrowseButtonN are not), so the "AuctionFrame" entry below is expected to
-- stay a permanent no-op on this client, not a miss. Browse/buy/sell result
-- rows are now skinned too (see the Item list rows section below);
-- UNVALIDATED in-game: no /fstack or visual check done yet.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
local ApplyMono = FS.Theme.ApplyMono
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER

if not FS.PanelSkins.RequireExport(SkinPanel, "AuctionHouse.lua disabled: FS.Theme.SkinPanel missing") then return end

-------------------------------------------------------------------------------
-- Target list
-------------------------------------------------------------------------------

-- Only one of these two will ever exist on a given client; the other stays
-- nil forever and SkinOne no-ops on it.
local AH_FRAMES = {
    "AuctionHouseFrame", -- modern retail (Blizzard_AuctionHouseUI)
    "AuctionFrame",      -- classic/TBC (Blizzard_AuctionUI)
}

-------------------------------------------------------------------------------
-- Item list rows (browse results / single-auction buy list / sell list)
-------------------------------------------------------------------------------

-- One-time per-row setup for an AH ItemList row (FS.PanelSkins.ApplyGuts'
-- `rows.perRow`). Rows built off AuctionHouseItemListTemplate are TableBuilder
-- rows, not fixed named FontStrings: TableBuilderMixin (Blizzard_SharedXML/
-- TableBuilder.lua) populates a plain `row.cells` array per row, one cell per
-- column, since the column set differs per list (item name vs price vs
-- buyout vs time-left...) -- corroborating-only, since these are Lua table
-- fields, not widgets, and so cannot appear in the 16001 globals dump;
-- ElvUI's own Game/Mainline/Skins/AuctionHouse.lua reads the identical
-- `row.cells[j]` shape (its `HandleListIcon`), which is what confirms this
-- isn't retail-only scaffolding. Every column's cell shares one base
-- template with a `.Text` FontString (AuctionHouseTableCellTextTemplate,
-- confirmed in Blizzard_AuctionHouseTableBuilder.xml); the item-name column's
-- own cell template additionally carries `.Icon`/`.ExtraInfo`
-- (AuctionHouseTableCellItemDisplayTemplate). Quality color arrives as an
-- inline `|cffRRGGBB...|r` code baked directly into the name text
-- (AuctionHouseUtil.GetItemDisplayTextFromItemKey -> WrapTextInColorCode),
-- never a `SetTextColor` call, so a font-only change can't disturb it
-- regardless of what base color gets passed -- the capture-and-reapply below
-- is the same not-actually-a-color-change discipline Loot.lua's item row
-- uses, kept for consistency rather than because this text needs it. The
-- embedded item icon (`cell.Icon`, a plain Texture region, not a Button) is
-- deliberately left unskinned: Theme.SkinButton anchors its border/glow to
-- the full `button` frame's own edges, and here that would be the whole
-- (much wider) name cell, not the small icon square inside it -- there is no
-- existing primitive that borders a sub-region of a frame, and building one
-- is out of scope for this minimal pass.
local function AHItemListRowUpdateChild(row)
    if row.fsAHRowSkinned then return end
    local cells = row.cells
    if type(cells) ~= "table" then return end
    row.fsAHRowSkinned = true

    for _, cell in ipairs(cells) do
        if ApplyMono and cell.Text and cell.Text.SetFont and cell.Text.GetTextColor then
            local _, size = cell.Text:GetFont()
            local r, g, b, a = cell.Text:GetTextColor()
            ApplyMono(cell.Text, size or 11, { r or 1, g or 1, b or 1, a or 1 })
        end
        if ApplyMono and cell.ExtraInfo and cell.ExtraInfo.SetFont and cell.ExtraInfo.GetTextColor then
            local _, size = cell.ExtraInfo:GetFont()
            local r, g, b, a = cell.ExtraInfo:GetTextColor()
            ApplyMono(cell.ExtraInfo, size or 11, { r or 1, g or 1, b or 1, a or 1 })
        end
    end
end

-- Browse results, the single-item "buy this auction" list landed on after
-- picking an item in Browse, and the Sell tab's own posted-auctions list.
-- All three inherit AuctionHouseItemListTemplate (confirmed via
-- Blizzard_AuctionHouseFrame.xml's BrowseResultsFrame/ItemBuyFrame/
-- ItemSellList entries and Blizzard_AuctionHouseBrowseResultsFrame.xml/
-- Blizzard_AuctionHouseItemBuyFrame.xml), so all three ScrollBoxes carry the
-- same TableBuilder row/cell shape AHItemListRowUpdateChild expects.
-- CommoditiesBuyFrame.ItemList is DELIBERATELY excluded: it inherits a
-- different template (AuctionHouseCommoditiesBuyListTemplate, not
-- AuctionHouseItemListTemplate) whose row/cell shape is not confirmed here.
--
-- None of the three has its own top-level `_G` name (only AuctionHouseFrame
-- itself does -- BrowseResultsFrame/ItemBuyFrame/ItemSellList are all
-- unnamed parentKey-only children), so `entry.parent` is "AuctionHouseFrame"
-- for all three below. ApplyGutsRows' OnShow-retry guard is keyed per
-- scrollBox path (`parent.fsGutsRowsRetry[rows.scrollBox]`), not a single
-- flag on the shared parent, so all three entries can independently re-arm
-- their own retry if any of them is still unresolved at apply time.
local AH_ITEM_LIST_SCROLLBOX_PATHS = {
    "AuctionHouseFrame.BrowseResultsFrame.ItemList.ScrollBox",
    "AuctionHouseFrame.ItemBuyFrame.ItemList.ScrollBox",
    "AuctionHouseFrame.ItemSellList.ScrollBox",
}

local AH_ITEM_LIST_GUTS = {}
for _, path in ipairs(AH_ITEM_LIST_SCROLLBOX_PATHS) do
    AH_ITEM_LIST_GUTS[#AH_ITEM_LIST_GUTS + 1] = {
        parent = "AuctionHouseFrame",
        rows = { scrollBox = path, perRow = AHItemListRowUpdateChild },
    }
end

-------------------------------------------------------------------------------
-- Skin pass (idempotent via frame.fsAHSkin)
-------------------------------------------------------------------------------

local function SkinOne(name)
    local frame = _G[name]
    if not frame or frame.fsAHSkin then return end

    SkinPanel(frame, {
        title = "auction",
        fillColor = COLOR_BG,
        borderColor = COLOR_BORDER,
    })
    frame.fsAHSkin = true

    -- Promoted to the shared 3-strategy resolver (parentKey, legacy global
    -- suffix, child-scan fingerprint) rather than this file's own 2-strategy
    -- version: AuctionHouseFrame (Blizzard_AuctionHouseUI, modern retail) is a
    -- combined-style frame whose .MoneyFrame is nil, the same situation
    -- Bags.lua already handles for ContainerFrameCombinedBags -- only the
    -- child-scan strategy catches it.
    FS.PanelSkins.TryStyleMoney(frame)
end

-------------------------------------------------------------------------------
-- Init + load-on-demand re-scan
-------------------------------------------------------------------------------

-- Filtered to the AH's own Blizzard module names (rather than Panels.lua's
-- generic "^Blizzard_" match) since neither AH frame exists until its
-- specific module loads; PLAYER_ENTERING_WORLD stays as a light catch-all.
local function MatchesAHModule(loadedAddonName)
    return loadedAddonName == "Blizzard_AuctionHouseUI" or loadedAddonName == "Blizzard_AuctionUI"
end

-- afterScan runs ApplyGuts on every scan pass (idempotent -- see AHItemListRowUpdateChild
-- and ApplyGutsRows' own guards), same pattern Panels.lua's PANEL_GUTS uses.
local ScanAndSkin = FS.PanelSkins.CreateSkinDriver({
    entries = AH_FRAMES,
    skinEntry = SkinOne,
    matchesAddon = MatchesAHModule,
    afterScan = function() FS.PanelSkins.ApplyGuts(AH_ITEM_LIST_GUTS) end,
})

FS.PanelSkins.RegisterReconFromList("AuctionHouse", AH_FRAMES, "fsAHSkin")

-- Neither AH frame is secure, so none of this is combat-illegal; deferred
-- anyway for consistency with the rest of the addon's Init pattern.
local function Apply()
    ScanAndSkin()
end

FS.PanelSkins.DeferCombat(Apply)
