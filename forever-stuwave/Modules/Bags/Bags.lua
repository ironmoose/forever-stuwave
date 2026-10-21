-- Forever STUwave: Bags
-- FIRST PASS reskin of the default bag UI: individual containers
-- (ContainerFrame1..ContainerFrame13, feature-detected -- NUM_CONTAINER_FRAMES
-- has varied across client revisions), the modern combined-bag frame
-- (ContainerFrameCombinedBags, confirmed present on interface 16001), and
-- BankFrame + BankPanel (both confirmed present). Every Blizzard name/function
-- is feature-detected; a missing name silently no-ops rather than erroring.
-- Item slots wear OUR plate only (the two-corner cut plate of the deck bag
-- slots and action buttons, plus its cut border); Blizzard's own slot art is
-- hidden and held hidden, a filled slot's square icon is cut at the two cut
-- corners by a panel-coloured wedge (no MaskTexture: it does not clip here), and
-- the border is tinted by the item's quality (Poor grey, Common default).
-- The money line wears the data bar's GOLD look.
-- Blizzard's GamepadBagBar (a child of the combined bags, same frame level as
-- the Clean Up button, a bag icon) is hidden while no controller is connected:
-- on a client with the GamePadEnable CVar on and nothing plugged in it drew over
-- the Clean Up (broom) button. C_GamePad missing, C_GamePad.IsEnabled() false or
-- an empty C_GamePad.GetAllDeviceIDs() all count as "no controller"; an API that
-- errors counts as a controller. It is
-- re-hidden whenever Blizzard shows it again (post-hooks on Show/SetShown and
-- OnShow, no method replaced), re-evaluated on GAME_PAD_CONNECTED/
-- DISCONNECTED/ACTIVE_CHANGED and PLAYER_ENTERING_WORLD, and left alone once a
-- controller is present (never forced back on: Blizzard shows it on its next
-- update). The bar is unprotected, so this works in combat too.
-- The GamePadEnable CVar and the sort button are never touched.
-- UNVALIDATED in-game: no /fstack or visual check done yet.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local SkinPanel = FS.Theme.SkinPanel
-- The cut border at chamfer 6, the same ring the action buttons and our plate use.
-- SkinButton is the fallback for a Theme without the alias.
local SkinCutButton = FS.Theme.SkinCutButton or FS.Theme.SkinButton

if not FS.PanelSkins.RequireExport(SkinPanel, "Bags.lua disabled: FS.Theme.SkinPanel missing") then return end

local MAX_CONTAINERS = 13 -- historical NUM_CONTAINER_FRAMES ceiling; loop skips gaps

-------------------------------------------------------------------------------
-- Item slots (container / combined-bag / bank item buttons)
-------------------------------------------------------------------------------

-- The 16001 globals dump has no ContainerFrameNItemN globals at all -- this
-- client's item slots are the retail pooled-button structure instead
-- (ContainerFrameMixin/BaseContainerFrameMixin/ContainerFrameItemButtonMixin/
-- ItemButtonMixin/ContainerFrameCombinedBags/BankPanel all present in the
-- dump). Corroborated via retail Blizzard_UIPanels_Game/ContainerFrame.lua and
-- BankFrame.lua (NOT 16001-dump-confirmed themselves, since mixin methods and
-- pooled-array fields aren't widgets).
--
-- Blizzard slot art, hidden and HELD hidden. What the player saw under our
-- violet border was Blizzard's own slot: the button's NormalTexture (the square
-- Interface\Buttons\UI-Quickslot2 frame, ItemButtonTemplate.xml), the combined
-- bag's `ItemSlotBackground` (UI-Bag-Components, made inside
-- ContainerFrameItemButtonMixin:Initialize, i.e. AFTER a first skin pass), the
-- bank slot's `Background` (BankPanelItemButtonMixin:UpdateBackgroundForBankType
-- re-points it with SetAtlas "bags-item-slot64" / "warband-bank-slot"), and the
-- brown winged EMPTY slot, which is none of those: a container slot has no
-- background region of its own, SetItemButtonTexture(nil) points the ICON at the
-- `emptyBackgroundAtlas` KeyValue ("bags-item-slot64",
-- ContainerFrameItemButtonTemplate) instead. So the first three are held at
-- alpha 0 and the icon is cleared when an empty-slot atlas lands on it (the
-- plate under it is what then shows).
--
-- A FILLED slot wears one more piece of Blizzard art, the button's `IconBorder`:
-- UpdateItems and BankPanelItemButtonMixin:Refresh call SetItemButtonQuality, which
-- shows it with Interface\Common\WhiteIconFrame (a square frame with rounded corners;
-- a relic item gets Interface\Artifacts\RelicIconFrame in the same region) and tints it
-- by quality (SetItemButtonBorder, SetItemButtonBorderVertexColor) for Common and up: the
-- qualities in BAG_ITEM_QUALITY_COLORS, Common (grey) first, so Poor (junk) gets none.
-- ColorManager.GetColorDataForBagItemQuality may swap in a colour the player overrode
-- (Blizzard_ItemButton/Mainline/ItemButtonTemplate.lua, Blizzard_Colors/Mainline/
-- ColorConstants.lua and ColorManager.lua, 12.1 source). An empty slot gets no border,
-- which is why only slots holding an item still showed Blizzard's frame, its rounded
-- corners reaching past the cut corners of our ring. So the region, whichever frame
-- texture it wears, is held at alpha 0 with the rest. Blizzard drives it with
-- Show/Hide, SetTexture and SetVertexColor, none of which touch alpha, so its shown state,
-- texture and colour stay Blizzard's; the one alpha write is ItemButtonMixin:SetAlpha
-- (Blizzard_ItemButton/Shared/ItemButtonTemplate.lua), which writes a button's alpha
-- through to the IconBorder, and the SetAlpha hook below re-zeros it. The quality colour is
-- therefore not drawn on an item slot; a treatment of our own for it is a design decision
-- that is not made here (the bag bar tints its edge for Uncommon and up, BagBar.lua).
--
-- What re-shows this art is a NEW region, not a write to a held one: the button's
-- SetNormalTexture/SetNormalAtlas can build a fresh normal texture (the money
-- buttons do after ClearNormalTexture) and Initialize builds `ItemSlotBackground`,
-- so those three methods get a post-hook that re-sweeps and holds whatever region
-- exists now. How a region is held (alpha 0 plus a SetAlpha post-hook) is FS.HeldArt,
-- shared with the close and text button skins: the 12.1
-- ContainerFrame/BankFrame/ItemButton source writes alpha on none of these regions
-- but the IconBorder (ItemButtonMixin:SetAlpha), so for the rest that hook is only a
-- guard against another writer. SetAtlas and SetTexture on
-- an existing region leave its alpha alone (Blizzard re-points the bank
-- `Background` with SetAtlas, UpdateBackgroundForBankType), so they are not hooked.
--
-- Deliberately NOT touched: IconOverlay/IconOverlay2, NewItemTexture/
-- BattlepayItemTexture/flash (new-item glows), UpgradeIcon, JunkIcon,
-- IconQuestTexture, searchOverlay,
-- ItemContextOverlay, Cooldown, Count, the lock/desaturate state, the pushed and
-- highlight textures (interaction feedback) and ExtendedSlot (the
-- locked-until-secured marker, ContainerFrameItemButtonMixin:UpdateExtended).
local clearing = setmetatable({}, { __mode = "k" })  -- icon -> our own clear is in flight

local ART_FIELDS = { "NormalTexture", "ItemSlotBackground", "Background", "IconBorder" }
local ART_SETTERS = { "SetNormalTexture", "SetNormalAtlas", "Initialize" }
local EMPTY_SLOT_ATLASES = { ["bags-item-slot64"] = true, ["warband-bank-slot"] = true }

local HeldArt = FS.HeldArt
local HoldRegion, HoldNormalTexture, HookNormalSetters = HeldArt.Hold, HeldArt.HoldNormal, HeldArt.HookSetters

local function SweepSlotArt(button)
    if not button then return end
    HoldNormalTexture(button)
    for _, field in ipairs(ART_FIELDS) do HoldRegion(button[field]) end
end

-- True when `value` (an atlas name or a texture path) is the empty-slot art of this button.
local function IsEmptySlotArt(button, value)
    if type(value) ~= "string" then return false end
    return value == button.emptyBackgroundAtlas or value == button.emptyBackgroundTexture or EMPTY_SLOT_ATLASES[value] == true
end

local function ClearEmptyIcon(icon)
    if clearing[icon] then return end
    clearing[icon] = true
    pcall(icon.SetTexture, icon, nil)
    clearing[icon] = nil
end

-- An empty container slot's brown winged background IS the icon pointed at the
-- empty-slot atlas (see above), so a post-hook on the icon's own SetAtlas (and
-- SetTexture, for a template that uses `emptyBackgroundTexture`) clears it the
-- moment Blizzard puts it there; a real item texture is never touched.
local function HookEmptyIcon(button)
    local icon = button.icon
    if type(icon) ~= "table" then return end

    if type(icon.GetAtlas) == "function" then
        local ok, atlas = pcall(icon.GetAtlas, icon)
        if ok and IsEmptySlotArt(button, atlas) then ClearEmptyIcon(icon) end
    end
    if type(hooksecurefunc) ~= "function" then return end
    if type(icon.SetAtlas) == "function" then
        pcall(hooksecurefunc, icon, "SetAtlas", function(self, atlas)
            if IsEmptySlotArt(button, atlas) then ClearEmptyIcon(self) end
        end)
    end
    if button.emptyBackgroundTexture ~= nil and type(icon.SetTexture) == "function" then
        pcall(hooksecurefunc, icon, "SetTexture", function(self, texture)
            if IsEmptySlotArt(button, texture) then ClearEmptyIcon(self) end
        end)
    end
end

-- Our plate under the icon: the two-corner cut plate the deck bag slots and the
-- action buttons wear (Theme.AddCut2Texture over slice_cut2_button.tga, TOP-LEFT
-- and BOTTOM-RIGHT chamfered, chamfer 6), BACKGROUND -8 as on the action buttons.
-- An empty slot shows just this and its ring. Without the Theme helper the slot
-- keeps its border and count and logs once.
local plateWarned = false
local function AddPlate(button)
    local Theme = FS.Theme
    if type(Theme.AddCut2Texture) ~= "function" or not Theme.SLICE_CUT2_BUTTON_TEXTURE then
        if not plateWarned then
            plateWarned = true
            FS.LogDegradeOnce("bags_plate", "Bags.lua: no slot plate, Theme.AddCut2Texture / SLICE_CUT2_BUTTON_TEXTURE missing")
        end
        return
    end
    local ok, plate = pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    if ok then
        button.fsBagPlate = plate
    elseif not plateWarned then
        plateWarned = true
        FS.LogDegradeOnce("bags_plate", "Bags.lua: slot plate failed: " .. tostring(plate))
    end
end

-- Icon corners: the cut that a mask would make.
--
-- A filled slot's icon is a SQUARE texture over the whole button, so its TOP-LEFT and BOTTOM-RIGHT corners
-- lie outside the cut of our plate and ring, and the icon art shows there as a pale square nub past the
-- ring. The obvious fix, a MaskTexture on the icon, does nothing on this client:
-- CreateMaskTexture and AddMaskTexture exist and clip nothing (verified in game 2026-09-17 with Blizzard's own
-- TempPortraitAlphaMask; see FILL_CORNER_TEXTURE in Theme.lua and SeatCutIcon in FrameHelpers.lua), and Lua
-- cannot tell a clipping mask from a dead one. So the cut is baked into art instead, the way the nameplate and
-- party bars erase their fill corners: ONE nine-sliced texture, the cut2 erase file (an opaque wedge in the two
-- cut corner slices and nothing else) in the panel colour, laid over the button's rect at the ring's own slice
-- margin so the engine draws its corner cells at the ring's scale. Its cut line sits 7.25 texels from the
-- corner, inside the ring's stroke (6.0 to 7.41), so none of the icon shows outside the cut and no gap shows
-- between stroke and icon. Theme.AddCut2Texture builds it, as it builds the plate.
--
-- Layer: OVERLAY -1. OVERLAY draws over the icon (ARTWORK); the ring (OVERLAY 1) stays on top of the wedge; the
-- glow (OVERLAY 0, ADD) also reaches into the cut triangle and must not be painted over.
--
-- The colour is Theme.COLOR_BG, the fill SkinPanel gives the bag windows, but opaque: that fill is 80% opaque,
-- so on a bright world behind the window the wedge reads a little darker than the panel around it.
-- An empty slot has no icon to cut, and an opaque wedge there would show as a dark triangle on the plate-less
-- corner, so the wedge is shown only while the icon holds an item. That follows the ICON, not a refresh
-- pass: the container path is SetShown then SetAtlas/SetTexture, the bank's is SetTexture then SetShown (an emptied
-- bank slot keeps its old texture and is just hidden), and BankPanelItemButtonMixin:Refresh also runs for a single
-- slot on ITEM_LOCK_CHANGED, outside the panel-wide refresh hooks. So the icon's five state setters get a
-- post-hook each (HookIconState, no method replaced), and every skin pass re-reads it as well.
--
-- All of it is our own region: nothing on the item button's secure side is touched, so it works in combat.
local ICON_CORNER_SUBLEVEL = -1
local ICON_STATE_METHODS = { "SetTexture", "SetAtlas", "SetShown", "Show", "Hide" }

-- One value off the icon; nil when the method is missing or throws.
local function ReadIcon(icon, method)
    if type(icon[method]) ~= "function" then return nil end
    local ok, value = pcall(icon[method], icon)
    if ok then return value end
    return nil
end

-- True while the slot's icon is shown and holds something other than the empty-slot art. A secret texture or
-- atlas is never compared or tested: it counts as an item.
local function IconHoldsItem(button)
    local icon = button.icon
    if type(icon) ~= "table" then return false end
    if not ReadIcon(icon, "IsShown") then return false end
    local texture, atlas = ReadIcon(icon, "GetTexture"), ReadIcon(icon, "GetAtlas")
    if FS.IsSecret and (FS.IsSecret(texture) or FS.IsSecret(atlas)) then return true end
    if type(atlas) == "string" then return not IsEmptySlotArt(button, atlas) end
    return texture ~= nil and not IsEmptySlotArt(button, texture)
end

local function SyncIconCorners(button)
    local corners = button.fsBagCorners
    if corners then corners:SetShown(IconHoldsItem(button)) end
end

local cornersWarned = false
local function WarnNoCorners(why)
    if cornersWarned then return end
    cornersWarned = true
    FS.LogDegradeOnce("bags_icon_corners", "Bags.lua: no icon corner cut, " .. why)
end

local function AddIconCorners(button)
    local Theme = FS.Theme
    local panel = Theme.COLOR_BG
    if type(Theme.AddCut2Texture) ~= "function" or not Theme.SLICE_CUT2_ERASE_TEXTURE or type(panel) ~= "table" then
        WarnNoCorners("Theme.AddCut2Texture / SLICE_CUT2_ERASE_TEXTURE / COLOR_BG missing")
        return
    end
    local ok, corners = pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_ERASE_TEXTURE,
        { panel[1], panel[2], panel[3], 1 }, "OVERLAY", ICON_CORNER_SUBLEVEL)
    if not ok then
        WarnNoCorners(tostring(corners))
        return
    end
    corners:Hide()
    button.fsBagCorners = corners
end

-------------------------------------------------------------------------------
-- Quality ring: the slot's outline, tinted by the item inside
-------------------------------------------------------------------------------

-- The ring (the violet cut outline Theme.SkinButton puts on every slot) takes the colour of the item's
-- quality, so junk and good items read apart at a glance. Poor is grey; Common keeps the default ring;
-- Uncommon, Rare, Legendary and up take Blizzard's bag colour for that quality (Epic is ours, below); an empty slot, an
-- unknown quality and anything unreadable keep the default ring. Only the ring: the glow, the plate and the icon are
-- not touched. (BagBar.lua tints its slot edges the same way from Uncommon up.)
--
-- Colours: ColorManager.GetColorDataForBagItemQuality, the colours Blizzard's own item border used on these slots, and
-- the player's colour overrides come through it (12.1 ColorManager.lua). It has no Poor entry, so Poor reads
-- ColorManager.GetColorDataForItemQuality(0), also override-aware. A client without ColorManager falls back to the
-- ITEM_QUALITY_COLORS table BagBar.lua reads, and a client with neither keeps the default ring and logs once.
-- EPIC is the exception: Blizzard's #a335ee sits almost on top of the default ring (#a855f7), so Epic gets a deeper
-- royal purple of our own, Theme.COLOR_EPIC_RING (#6a1fd1; about 2.4:1 against the panel, 1.9:1 against the default
-- ring), the same colour BagBar.lua gives an Epic bag's edge. Epic therefore ignores a player's Epic colour override;
-- every other quality follows it. A Theme without the token gives Epic the Blizzard colour like the rest.
--
-- The quality is read per slot, not from Blizzard's border: C_Container.GetContainerItemInfo(bag, slot) for a container slot,
-- the `itemInfo` Blizzard just read for a bank slot (BankPanelItemButtonMixin:RefreshItemInfo). Both are plain
-- numbers on this API; a secret answer is never compared and keeps the default ring. The read happens on every skin
-- pass, which follows every UpdateItems and bank refresh, in combat too (bags are usable in combat, this API is not
-- restricted, and only our own ring region is written). The icon's state hooks re-apply the cached colour: an
-- icon that no longer holds an item drops it at once, without waiting for a pass.
local QUALITY_POOR, QUALITY_UNCOMMON, QUALITY_EPIC = 0, 2, 4   -- Enum.ItemQuality

local function BagIDOf(itemButton)
    if type(itemButton.GetBagID) ~= "function" then return nil end
    local ok, id = pcall(itemButton.GetBagID, itemButton)
    if not ok or type(id) ~= "number" or (FS.IsSecret and FS.IsSecret(id)) then return nil end
    return id
end

local function IsSecretValue(value)
    return FS.IsSecret and FS.IsSecret(value) and true or false
end

-- The item info of a slot, nil when there is none or it cannot be read plainly.
local function SlotItemInfo(button)
    local info = button.itemInfo -- a bank slot: Blizzard read it in Refresh
    if info == nil then
        if type(C_Container) ~= "table" or type(C_Container.GetContainerItemInfo) ~= "function" then return nil end
        local bag = BagIDOf(button)
        if not bag or type(button.GetID) ~= "function" then return nil end
        local okSlot, slot = pcall(button.GetID, button)
        if not okSlot or type(slot) ~= "number" or IsSecretValue(slot) then return nil end
        local ok, value = pcall(C_Container.GetContainerItemInfo, bag, slot)
        if not ok then return nil end
        info = value
    end
    if IsSecretValue(info) or type(info) ~= "table" then return nil end
    return info
end

local qualityRingWarned = false

-- r, g, b of a quality colour table, nil unless all three are plain numbers.
local function ChannelsOf(color)
    if type(color) ~= "table" or IsSecretValue(color) then return nil end
    local r, g, b = color.r, color.g, color.b
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return nil end
    if IsSecretValue(r) or IsSecretValue(g) or IsSecretValue(b) then return nil end
    return r, g, b
end

local function QualityColorChannels(quality)
    local sourced = false
    if type(ColorManager) == "table" then
        local read = quality == QUALITY_POOR and ColorManager.GetColorDataForItemQuality or ColorManager.GetColorDataForBagItemQuality
        if type(read) == "function" then
            sourced = true
            local ok, color = pcall(read, quality)
            if ok then
                local r, g, b = ChannelsOf(color)
                if r then return r, g, b end
            end
        end
    end
    if type(ITEM_QUALITY_COLORS) == "table" then return ChannelsOf(ITEM_QUALITY_COLORS[quality]) end
    if not sourced and not qualityRingWarned then
        qualityRingWarned = true
        FS.LogDegradeOnce("bags_quality_ring", "Bags.lua: no item quality colours, slot rings keep the default colour")
    end
    return nil
end

-- r, g, b of the ring for an item quality; nil for the default ring.
local function QualityRingColor(quality)
    if type(quality) ~= "number" or IsSecretValue(quality) then return nil end
    local epic = FS.Theme.COLOR_EPIC_RING
    if quality == QUALITY_EPIC and epic then return epic[1], epic[2], epic[3] end
    if quality ~= QUALITY_POOR and quality < QUALITY_UNCOMMON then return nil end -- Common, and anything below Poor
    return QualityColorChannels(quality)
end

-- Reads the slot's item now and caches the ring colour it earns.
local function ReadSlotRing(button)
    local info = SlotItemInfo(button)
    local r, g, b = QualityRingColor(info and info.quality)
    button.fsBagRingColor = r and { r, g, b } or nil
end

-- Writes the ring: the cached quality colour while the icon holds an item, else the default ring.
local function SyncSlotRing(button)
    local skin = button.fsSkin
    local ring = skin and skin.border and skin.border.ring
    if not ring then return end
    if not IconHoldsItem(button) then button.fsBagRingColor = nil end
    local color = button.fsBagRingColor or FS.Theme.COLOR_BORDER
    if color then ring:SetVertexColor(color[1], color[2], color[3], 1) end
end

-- Everything that follows the icon: the corner wedge and the ring.
local function SyncSlot(button)
    SyncIconCorners(button)
    SyncSlotRing(button)
end

-- One post-hook per icon state setter (no method replaced), installed once per button.
local function HookIconState(button)
    local icon = button.icon
    if type(icon) ~= "table" or type(hooksecurefunc) ~= "function" then return end
    local function sync() SyncSlot(button) end
    for _, method in ipairs(ICON_STATE_METHODS) do
        if type(icon[method]) == "function" then pcall(hooksecurefunc, icon, method, sync) end
    end
end

-- One-time per-button setup (the per-button guard below), same idempotency
-- shape as Loot.lua's fsLootRowSkinned: buttons are POOLED (a container's
-- `.Items` entries are reused across bag-content changes; BankPanel's
-- `itemButtonPool` reuses released buttons the same way), so a plain guard
-- field is correct rather than a per-scan rebuild. `button.Count` is confirmed
-- via ContainerFrameMixin:UpdateItems's own
-- `SetItemButtonCount(itemButton, itemCount)` call and
-- BankPanelItemButtonMixin:Refresh's identical call (ContainerFrame.lua line
-- ~1061, BankFrame.lua line ~536), and Blizzard_ItemButton's
-- ItemButtonTemplate.lua (`button.Count or _G[button:GetName().."Count"]`) --
-- the same native ItemButton widget Loot.lua's row.Item already skins, since
-- every item-slot template here (ContainerFrameItemButtonTemplate,
-- BankItemButtonTemplate) is `<ItemButton mixin="...">`, not a bespoke
-- Button. `.IconBorder` (the quality border, vertex-colored per-item by the
-- shared `SetItemButtonQuality`, called from both UpdateItems and
-- BankPanelItemButtonMixin:Refresh) is slot art too and is held hidden with the
-- rest (see above); our ring (Theme.SkinCutButton) is a separate OVERLAY layer
-- and the only border a slot wears. The slot art sweep runs on EVERY pass (it
-- only does work for a region it has not held yet), because a combined-bag slot
-- makes its ItemSlotBackground after our first pass.
--
-- The icon is NOT inset to the cut ring (FrameHelpers.SeatCutIcon is not
-- used), same decision as Loot.lua: icons are not inset to the cut ring. The icon
-- is a Blizzard region and the square IconQuestTexture (37 x 38) and
-- NewItemTexture over it would poke past the ring anyway, so moving only the icon
-- would detach them from the item by the inset instead of fixing the corners.
-- The icon keeps its full size; its two corners outside the cut are covered by the
-- wedge above (AddIconCorners). The icon hooks go in last so they sit after the empty-art clear.
local function SkinItemButton(button)
    if not button then return end
    SweepSlotArt(button)
    if not button.fsBagItemSkinned then
        button.fsBagItemSkinned = true

        HookNormalSetters(button, ART_SETTERS, SweepSlotArt)
        HookEmptyIcon(button)
        AddPlate(button)
        if SkinCutButton then
            SkinCutButton(button, { count = button.Count })
        end
        AddIconCorners(button)
        HookIconState(button)
    end
    ReadSlotRing(button)
    SyncSlot(button)
end

-- Calls fn(itemButton) for every currently-valid item button of a container or
-- the combined-bag frame.
-- `EnumerateValidItems` (BaseContainerFrameMixin, confirmed via
-- Blizzard_UIPanels_Game/ContainerFrame.lua: returns `index, itemButton` for
-- slots 1..GetBagSize(), reading `container.Items[index]`) is shared by
-- ContainerFrameMixin and ContainerFrameCombinedBagsMixin -- both descend
-- from BaseContainerFrameMixin via CreateFromMixins in the same file, and
-- ContainerFrameCombinedBagsMixin itself calls `self:EnumerateValidItems()`
-- (SetItemsMatchingBagHighlighted), so one function covers both containers
-- and the combined-bag frame. Not itself a widget, so not in the 16001 dump;
-- `container.Items` (the same field the enumerator reads) is the fallback
-- for a client where the method itself is missing.
local function EachContainerItem(container, fn)
    if not container then return end

    if type(container.EnumerateValidItems) == "function" then
        for _, itemButton in container:EnumerateValidItems() do
            fn(itemButton)
        end
    elseif type(container.Items) == "table" then
        for _, itemButton in ipairs(container.Items) do
            fn(itemButton)
        end
    end
end

-------------------------------------------------------------------------------
-- Bag bar hover: light up the slots a bag covers
-------------------------------------------------------------------------------

-- Hovering a bag button in OUR bag bar (BagBar.lua) calls FS.BagHighlight.Set(bagID); the
-- item slots of that bag, in whichever bag window is open (the combined window or the
-- individual ones), wear a thin ring and glow in the hover colour. Leaving calls Clear.
--
-- Why this is not Blizzard's own highlight: the stock one is EventRegistry
-- "BagSlot.OnEnter", which only the STOCK bag buttons trigger (BaseBagSlotButtonMixin:
-- BagSlotOnEnter) and BagBar.lua dims those with mouse off, so it never fires; its
-- listener (ContainerFrameCombinedBagsMixin) exists in the combined window only, bails out
-- unless the stock bar is "expanded", and shows a Blizzard store-art texture (BagIndicator,
-- Interface\Store\store-item-highlight). Faking the event from addon code would run
-- Blizzard's callbacks under our taint. So this is our own pair of regions.
--
-- Only OUR regions on the item buttons are shown or hidden (a ring and a glow, made like
-- the cut border the slots already wear): no attribute, anchor, size, parent or Show/Hide
-- on an item button, which is secure. Texture show/hide is legal in combat.
--
-- The state is the bag ID, not a per-button flag: pooled item buttons are re-used for other
-- bags and (re)built while the window opens, so every UpdateItems pass re-applies it
-- (SyncItemHighlight from SkinContainerItems), and closing the window clears its slots.
local HIGHLIGHT_ALPHA_GLOW = 0.9
local highlightBag = nil              -- the bag ID being hovered, nil = none
local highlightFailed = false         -- Theme could not build the regions; logged once

-- The two regions, made once per button. Same cut2 set as the slot's border (chamfer 6):
-- the outline ring on top, the cut2 glow (ADD, hollow inside, hangs out by its pad) under it.
local function EnsureHighlight(itemButton)
    local hl = itemButton.fsBagHighlight
    if hl or highlightFailed then return hl end
    local Theme = FS.Theme
    local color = Theme.COLOR_HEALTH or { 1, 0.18, 0.592 }
    -- Each region is hidden the moment it exists, so a step that throws after it cannot leave a
    -- visible orphan on the slot. The ring is built here (what Theme.AddCut2Texture does) for the same reason.
    local ok, result = pcall(function()
        local pad = Theme.SLICE_CUT2_GLOW_PAD
        local glow = itemButton:CreateTexture(nil, "OVERLAY", nil, 2)
        glow:Hide()
        glow:SetTexture(Theme.SLICE_CUT2_GLOW_TEXTURE)
        Theme.ApplyNineSlice(glow, Theme.SLICE_CUT2_GLOW_MARGIN)
        glow:SetPoint("TOPLEFT", itemButton, "TOPLEFT", -pad, pad)
        glow:SetPoint("BOTTOMRIGHT", itemButton, "BOTTOMRIGHT", pad, -pad)
        glow:SetBlendMode("ADD")
        glow:SetVertexColor(color[1], color[2], color[3], HIGHLIGHT_ALPHA_GLOW)
        local ring = itemButton:CreateTexture(nil, "OVERLAY", nil, 3)
        ring:Hide()
        ring:SetTexture(Theme.SLICE_CUT2_OUTLINE_TEXTURE)
        Theme.ApplyNineSlice(ring, Theme.SLICE_CUT_MARGIN)
        ring:SetPoint("TOPLEFT", itemButton, "TOPLEFT", 0, 0)
        ring:SetPoint("BOTTOMRIGHT", itemButton, "BOTTOMRIGHT", 0, 0)
        ring:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        return { glow = glow, ring = ring }
    end)
    if ok then
        itemButton.fsBagHighlight = result
        return result
    end
    highlightFailed = true
    FS.LogDegradeOnce("bags_hover_highlight", "Bags.lua: bag hover highlight unavailable: " .. tostring(result))
    return nil
end

-- Brings one item button in line with the hovered bag. `shown` is the owning window's state:
-- a closed window shows nothing. A button that never lit stays untouched while nothing is hovered.
local function SyncItemHighlight(itemButton, shown)
    if not itemButton then return end
    local hl = itemButton.fsBagHighlight
    if not hl and highlightBag == nil then return end
    local want = shown and highlightBag ~= nil and BagIDOf(itemButton) == highlightBag
    if want and not hl then hl = EnsureHighlight(itemButton) end
    if not hl then return end
    hl.ring:SetShown(want and true or false)
    hl.glow:SetShown(want and true or false)
end

local function ContainerShown(container)
    if type(container.IsShown) ~= "function" then return false end
    local ok, shown = pcall(container.IsShown, container)
    return ok and shown and true or false
end

local function SyncContainerHighlight(container)
    if not container then return end
    local shown = ContainerShown(container)
    EachContainerItem(container, function(itemButton) SyncItemHighlight(itemButton, shown) end)
end

-- One container that throws (a broken EnumerateValidItems) must not skip the others; logged once.
local syncFailureLogged = false
local function SafeSyncContainer(container)
    local ok, err = pcall(SyncContainerHighlight, container)
    if not ok and not syncFailureLogged then
        syncFailureLogged = true
        FS.LogDegradeOnce("bags_hover_sync", "Bags.lua: bag hover highlight sync failed: " .. tostring(err))
    end
end

local function SyncAllHighlights()
    for i = 1, MAX_CONTAINERS do
        SafeSyncContainer(_G["ContainerFrame" .. i])
    end
    SafeSyncContainer(_G["ContainerFrameCombinedBags"])
end

FS.BagHighlight = {
    -- bagID: Enum.BagIndex value of the hovered bag; anything that is not a number clears.
    Set = function(bagID)
        highlightBag = type(bagID) == "number" and bagID or nil
        SyncAllHighlights()
    end,
    Clear = function()
        highlightBag = nil
        SyncAllHighlights()
    end,
}

-- Skins every currently-valid item button on a container/combined-bag frame, and re-applies
-- the hover highlight to it (the window just opened or repopulated).
local function SkinContainerItems(container)
    local shown = container and ContainerShown(container) or false
    EachContainerItem(container, function(itemButton)
        SkinItemButton(itemButton)
        SyncItemHighlight(itemButton, shown)
    end)
end

-- Skins every currently-active item button on the bank panel. BankPanelMixin's
-- own `EnumerateValidItems` (confirmed via Blizzard_UIPanels_Game/BankFrame.lua)
-- is a DIFFERENT shape from the container one above: it returns
-- `self.itemButtonPool:EnumerateActive()`, a FramePool iterator yielding just
-- the button (no index), not `index, itemButton` -- so it gets its own loop
-- rather than reusing SkinContainerItems.
local function SkinBankItems(panel)
    if not panel or type(panel.EnumerateValidItems) ~= "function" then return end

    for itemButton in panel:EnumerateValidItems() do
        SkinItemButton(itemButton)
    end
end

-- Hooks a container's (or the bank panel's) item-repopulation method so newly
-- acquired/refreshed buttons get skinned without a separate rescan driver.
-- Per-INSTANCE hooksecurefunc, never on the shared mixin table: `mixin="..."`
-- in the owning template XML (ContainerFrameTemplate, the
-- ContainerFrameCombinedBags frame itself, BankPanelTemplate -- all confirmed
-- in their own .xml) copies each mixin function onto the FRAME INSTANCE at
-- creation time, so e.g. `ContainerFrame1.UpdateItems` is already its own
-- copied reference by the time this file runs; hooking `ContainerFrameMixin.UpdateItems`
-- (the shared table) afterward would hook a function no live frame instance
-- still points at. `frame.fsBagItemHooks`, a table keyed by method name (same
-- per-path-table idiom PanelSkins.lua's `ApplyGutsRows` retry guard uses),
-- since the bank panel needs two independently-guarded hooks on one frame.
local function HookItemRefresh(frame, methodName, skinFn)
    if not frame or type(frame[methodName]) ~= "function" then return end

    frame.fsBagItemHooks = frame.fsBagItemHooks or {}
    if frame.fsBagItemHooks[methodName] then return end
    frame.fsBagItemHooks[methodName] = true

    hooksecurefunc(frame, methodName, function(self)
        skinFn(self)
    end)
end

-------------------------------------------------------------------------------
-- Money line (the data bar's GOLD look on Blizzard's SmallMoneyFrame)
-------------------------------------------------------------------------------

-- The bag window's money line is a SmallMoneyFrame (ContainerMoneyFrameTemplate,
-- `MoneyFrame` on every container and on the combined bags frame; the bank's is
-- `BankPanel.MoneyFrame.MoneyDisplay`): Gold/Silver/CopperButton, each a Button
-- with a `Text` ButtonText and a coin NormalTexture (atlas coin-gold / silver /
-- copper). It is restyled in place, not replaced, so Blizzard keeps owning the
-- amounts, the leading-denomination collapse (a zero gold button is hidden) and
-- the click to pick money up: the coin atlas is held hidden, a glowing dot takes
-- its place, and the text gets the data bar's font and colour.
--
-- DUPLICATION: these numbers mirror DataBar.lua's GOLD segment (COIN_GOLD,
-- COIN_SILVER, COIN_COPPER, COIN_SIZE, COIN_TEXT_GAP, the `ApplyMono(text, 11,
-- color)` call and the glow_round.tga disc, drawn ADD). They are file-local
-- there and DataBar.lua loads after this file, so they cannot be read from it;
-- bags-harness.py parses them out of DataBar.lua and fails if they drift.
local COIN_GOLD   = { 1, 0.714, 0.282 }   -- --amber
local COIN_SILVER = { 0.78, 0.93, 1 }     -- pale cyan-white
local COIN_COPPER = { 1, 0.42, 0.55 }     -- warm pink
local COIN_SIZE = 9
local COIN_TEXT_GAP = 2
local COIN_FONT_SIZE = 11
local COIN_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

local COIN_BUTTONS = {
    { field = "GoldButton", color = COIN_GOLD },
    { field = "SilverButton", color = COIN_SILVER },
    { field = "CopperButton", color = COIN_COPPER },
}

local function StyleCoinText(button, color)
    local text = button.Text
    if type(text) ~= "table" and type(button.GetFontString) == "function" then
        local ok, fontString = pcall(button.GetFontString, button)
        text = ok and fontString or nil
    end
    if type(text) ~= "table" or type(text.SetFont) ~= "function" then return nil end
    if FS.Theme.ApplyMono then pcall(FS.Theme.ApplyMono, text, COIN_FONT_SIZE, color) end
    return text
end

-- Colorblind mode (MoneyFrame.lua reads the `colorblindMode` CVar through
-- CVarCallbackRegistry:GetCVarValueBool, in every MoneyFrame_Update): Blizzard
-- clears the coin textures, sizes each button to its text with no coin gap and
-- prints g/s/c letters after the numbers, so a dot left of the number would sit on
-- the previous denomination's letter. The dots are hidden while it is on.
local function IsColorblind()
    local registry = _G["CVarCallbackRegistry"] -- read via _G, not in .luacheckrc's globals
    if type(registry) == "table" and type(registry.GetCVarValueBool) == "function" then
        local ok, on = pcall(registry.GetCVarValueBool, registry, "colorblindMode")
        if ok then return on == true end
    end
    if type(GetCVar) == "function" then
        local ok, value = pcall(GetCVar, "colorblindMode")
        if ok then return value == "1" end
    end
    return false
end

-- Our dot is an addon texture, so Hide/Show on it is safe. Re-evaluated from every
-- path Blizzard's update takes through the button (SetText runs on each
-- MoneyFrame_Update, which is also where a CVar change lands) and from the restyle
-- hooks below, so the dot follows the mode both ways.
local function SyncCoinDot(button)
    local dot = button.fsBagCoinDot
    if dot then dot:SetShown(not IsColorblind()) end
end

-- One coin button: coin atlas hidden and held, the text restyled and re-restyled
-- when Blizzard swaps the button's font object (SetMoneyFrameColor does), a dot
-- before the number. The dot is a texture ON the button, so a collapsed (hidden)
-- denomination takes its dot with it. The coin sits at the button's right and the
-- number right-aligned next to it, so the dot goes left of the number, into the
-- blank the hidden coin leaves behind the previous denomination.
local function StyleCoinButton(button, color)
    if type(button) ~= "table" or button.fsBagCoin then return end
    button.fsBagCoin = true

    HoldNormalTexture(button)
    HookNormalSetters(button, { "SetNormalTexture", "SetNormalAtlas" }, function(self)
        HoldNormalTexture(self)
        SyncCoinDot(self)
    end)

    local text = StyleCoinText(button, color)
    if type(hooksecurefunc) == "function" and type(button.SetNormalFontObject) == "function" then
        pcall(hooksecurefunc, button, "SetNormalFontObject", function(self)
            StyleCoinText(self, color)
            SyncCoinDot(self)
        end)
    end

    if text and type(button.CreateTexture) == "function" then
        local dot = button:CreateTexture(nil, "OVERLAY")
        dot:SetTexture(COIN_TEXTURE)
        dot:SetBlendMode("ADD")
        dot:SetVertexColor(color[1], color[2], color[3], 1)
        dot:SetSize(COIN_SIZE, COIN_SIZE)
        dot:SetPoint("RIGHT", text, "LEFT", -COIN_TEXT_GAP, 0)
        button.fsBagCoinDot = dot
        SyncCoinDot(button)
        HookNormalSetters(button, { "SetText" }, SyncCoinDot)
    end
end

-- The SmallMoneyFrame behind a container/panel: `frame.MoneyFrame` itself on a
-- container, its `.MoneyDisplay` child on the bank panel's wrapper.
local function ResolveMoneyDisplay(frame)
    local money = type(frame) == "table" and frame.MoneyFrame
    if type(money) ~= "table" then return nil end
    if type(money.GoldButton) == "table" then return money end
    local display = money.MoneyDisplay
    if type(display) == "table" and type(display.GoldButton) == "table" then return display end
    return nil
end

-- True when the frame has a money line in the data bar look (already or now),
-- false when it has none to restyle, so the caller can fall back to the older
-- name-based font-only helper.
local function StyleBagMoney(frame)
    local display = ResolveMoneyDisplay(frame)
    if not display then return false end
    if display.fsBagMoney then return true end
    display.fsBagMoney = true
    for _, spec in ipairs(COIN_BUTTONS) do StyleCoinButton(display[spec.field], spec.color) end
    return true
end

-------------------------------------------------------------------------------
-- Panel skin (idempotent via frame.fsBagSkin)
-------------------------------------------------------------------------------

local function SkinBagFrame(frame)
    if not frame or frame.fsBagSkin then return end

    SkinPanel(frame)
    if not StyleBagMoney(frame) then FS.PanelSkins.TryStyleMoney(frame) end

    frame.fsBagSkin = true
end

-------------------------------------------------------------------------------
-- Individual containers (ContainerFrame1..ContainerFrame13)
-------------------------------------------------------------------------------

-- Containers are re-shown/re-laid-out constantly (bag toggles, slot count
-- changes); OnShow re-applies the skin, but SkinBagFrame's fsBagSkin guard
-- means every call after the first is a cheap no-op rather than a rebuild.
local function HookContainerShow(frame)
    if not frame or frame.fsBagShowHooked then return end
    frame:HookScript("OnShow", SkinBagFrame)
    frame.fsBagShowHooked = true
end

-- A window that closes while a bag is hovered drops its highlights (it is hidden, so
-- ContainerShown reads false); the hover state itself stays, so reopening it while the
-- mouse is still on the bag button lights the slots again. OnShow covers a window whose
-- UpdateItems ran while it was still hidden (the refresh then saw "closed"). HookScript,
-- nothing replaced.
local function HookContainerHide(frame)
    if not frame or frame.fsBagHideHooked then return end
    frame:HookScript("OnHide", SyncContainerHighlight)
    frame:HookScript("OnShow", SyncContainerHighlight)
    frame.fsBagHideHooked = true
end

-- Item-slot skinning is wired per container (not just ContainerFrame1): each
-- one gets its own immediate SkinContainerItems pass (covers a container
-- that's already open/populated when this file's Init runs) plus a
-- hooksecurefunc on its own `UpdateItems` (ContainerFrameMixin, confirmed via
-- ContainerFrame.lua -- called from `Update()` and `AddItemsForRefresh`'s
-- continuation, i.e. every real repopulation) so newly shown/rebuilt slots
-- get skinned too.
local function ApplyContainers()
    for i = 1, MAX_CONTAINERS do
        local frame = _G["ContainerFrame" .. i]
        if frame then
            SkinBagFrame(frame)
            HookContainerShow(frame)
            HookContainerHide(frame)
            SkinContainerItems(frame)
            HookItemRefresh(frame, "UpdateItems", SkinContainerItems)
        end
    end
end

-------------------------------------------------------------------------------
-- Combined bags (modern retail feature; player can toggle combined/individual)
-------------------------------------------------------------------------------

local function ApplyCombinedBags()
    local frame = ContainerFrameCombinedBags
    if not frame then return end

    SkinBagFrame(frame)
    HookContainerShow(frame)
    HookContainerHide(frame)
    SkinContainerItems(frame)
    HookItemRefresh(frame, "UpdateItems", SkinContainerItems)
end

-------------------------------------------------------------------------------
-- Bank
-------------------------------------------------------------------------------

-- BankFrame is the outer window (panel skin only, as before). BankPanel
-- (confirmed as its own top-level global in the 16001 dump, and reachable as
-- BankFrame.BankPanel via its parentKey, per Blizzard_UIPanels_Game/BankFrame.xml)
-- is the actual item-grid frame with the pooled item buttons -- a real bank
-- structure was confirmed from the dump plus retail source, so item slots are
-- skinned here rather than skipped. `GenerateItemSlotsForSelectedTab`
-- (rebuilds the pool -- covers first tab open, since BankPanelMixin:Clean
-- only calls this OR RefreshAllItemsForSelectedTab depending on whether slots
-- already exist, never both) and `RefreshAllItemsForSelectedTab` (re-applies
-- data to already-acquired buttons, e.g. a plain tab refresh) are both
-- hooked, since together they cover every path that can leave a button
-- unskinned.
local function ApplyBank()
    local frame = BankFrame
    if frame then
        SkinBagFrame(frame)
        HookContainerShow(frame)
    end

    local panel = _G["BankPanel"]
    if panel then
        StyleBagMoney(panel)
        SkinBankItems(panel)
        HookItemRefresh(panel, "GenerateItemSlotsForSelectedTab", SkinBankItems)
        HookItemRefresh(panel, "RefreshAllItemsForSelectedTab", SkinBankItems)
    end
end

-------------------------------------------------------------------------------
-- Gamepad bag bar (covers the Clean Up button when no controller is connected)
-------------------------------------------------------------------------------

-- GamepadBagBar is a plain (unprotected) frame parented to the combined bags. A
-- client with the GamePadEnable CVar on and no controller still shows it, on top
-- of BagItemAutoSortButton. Read through _G (not in .luacheckrc's globals) and
-- feature-detected: neither it nor C_GamePad exists on every build.
local gamepadHiddenByUs = false -- we hid it; cleared when a controller appears (Blizzard shows it then)

-- "No controller" is C_GamePad missing, gamepads disabled, or no device IDs. An
-- API that is there but errors is not proof either way, so any error counts as a
-- controller (Blizzard stays in charge).
local function HasController()
    local api = _G["C_GamePad"]
    if type(api) ~= "table" then return false end
    if type(api.IsEnabled) == "function" then
        local ok, enabled = pcall(api.IsEnabled)
        if not ok then return true end
        if not enabled then return false end
    end
    if type(api.GetAllDeviceIDs) == "function" then
        local ok, ids = pcall(api.GetAllDeviceIDs)
        if not ok then return true end
        if type(ids) == "table" and #ids == 0 then return false end
    end
    return true
end

local SyncGamepadBagBar

-- Post-hooks only, installed once per bar object: Blizzard's own Show/SetShown/
-- OnShow run untouched, then we re-hide if there is still no controller.
local function HookGamepadBagBar(bar)
    if bar.fsGamepadHooked then return end
    bar.fsGamepadHooked = true
    if type(hooksecurefunc) == "function" then
        if type(bar.Show) == "function" then pcall(hooksecurefunc, bar, "Show", SyncGamepadBagBar) end
        if type(bar.SetShown) == "function" then pcall(hooksecurefunc, bar, "SetShown", SyncGamepadBagBar) end
    end
    if type(bar.HookScript) == "function" then pcall(bar.HookScript, bar, "OnShow", SyncGamepadBagBar) end
end

SyncGamepadBagBar = function()
    local bar = _G["GamepadBagBar"]
    if type(bar) ~= "table" or type(bar.Hide) ~= "function" or type(bar.Show) ~= "function" then return end
    HookGamepadBagBar(bar)

    if not HasController() then
        local shown = true
        if type(bar.IsShown) == "function" then
            local ok, value = pcall(bar.IsShown, bar)
            shown = not ok or value
        end
        if shown then
            gamepadHiddenByUs = true
            pcall(bar.Hide, bar)
        end
    else
        gamepadHiddenByUs = false
    end
end

-- RegisterEvent throws on a name the client does not know, so each is its own pcall.
local gamepadEvents = CreateFrame("Frame")
for _, event in ipairs({ "GAME_PAD_CONNECTED", "GAME_PAD_DISCONNECTED", "GAME_PAD_ACTIVE_CHANGED", "PLAYER_ENTERING_WORLD" }) do
    pcall(gamepadEvents.RegisterEvent, gamepadEvents, event)
end
gamepadEvents:SetScript("OnEvent", SyncGamepadBagBar)

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Bag/bank frames are plain non-secure frames, so none of this is
-- combat-illegal; deferred anyway for consistency with the rest of the
-- addon's Init pattern.
local function Apply()
    ApplyContainers()
    ApplyCombinedBags()
    ApplyBank()
    SyncGamepadBagBar()
end

-- Verifies every numbered container, the combined-bag frame, and the bank
-- frame picked up the panel skin. Unopened containers/bank correctly report
-- as skipped (frame not loaded yet) rather than missing.
local inspectEntries = {}
for i = 1, MAX_CONTAINERS do
    inspectEntries[#inspectEntries + 1] = { name = "ContainerFrame" .. i, guard = "fsBagSkin" }
end
inspectEntries[#inspectEntries + 1] = { name = "ContainerFrameCombinedBags", guard = "fsBagSkin" }
inspectEntries[#inspectEntries + 1] = { name = "BankFrame", guard = "fsBagSkin" }
FS.PanelSkins.RegisterInspect("Bags", inspectEntries)

FS.PanelSkins.DeferCombat(Apply)
