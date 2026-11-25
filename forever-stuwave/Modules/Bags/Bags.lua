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
-- the border is tinted by the item's quality (Poor grey, Common and empty a dark violet).
-- The money line wears the data bar's GOLD look.
-- The bag windows (ContainerFrame1..13 and the combined bags) are redrawn as one window of our own (see "Window" below):
-- a header row (search field, sort key, close key), the item grid, a footer (slot count left, money right) and no
-- stock art; an EMPTY slot is covered by a dark well that follows the item API rather than the name of Blizzard's art.
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
-- The GamePadEnable CVar is never touched; the sort button keeps its own click (only its art and place change).
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
-- The new-item glows (NewItemTexture, BattlepayItemTexture, flash) and the quest border (IconQuestTexture) are square art
-- bigger than the slot, so they poked past the cut ring: they are held too (GLOW_FIELDS), their alpha animations stopped
-- when they start (an Alpha animation writes alpha in the engine, past the SetAlpha hook), and a quest item's ring is
-- amber instead (ReadSlotRing).
--
-- Deliberately NOT touched: IconOverlay/IconOverlay2, UpgradeIcon, JunkIcon, searchOverlay,
-- ItemContextOverlay, Cooldown, Count, the lock/desaturate state, the pushed and
-- highlight textures (interaction feedback) and ExtendedSlot (the
-- locked-until-secured marker, ContainerFrameItemButtonMixin:UpdateExtended).
local clearing = setmetatable({}, { __mode = "k" })  -- icon -> our own clear is in flight

-- State kept OFF Blizzard's frames: the open ADDON_ACTION_FORBIDDEN UseContainerItem report is blamed on this addon, so
-- nothing new is written as a field on an item button or a container (the fs* fields below are the older ones).
local bagSlots = setmetatable({}, { __mode = "k" })   -- item button -> true for a bag slot (the bank's are not)
local wells = setmetatable({}, { __mode = "k" })      -- item button -> its empty-slot well region
local insetIcons = setmetatable({}, { __mode = "k" }) -- item button -> true once its icon sits in the slot layer's inset box
local SlotIsEmpty                                      -- (button) -> true / false / nil, defined with the item reads below

local ART_FIELDS = { "NormalTexture", "ItemSlotBackground", "Background", "IconBorder" }
local ART_SETTERS = { "SetNormalTexture", "SetNormalAtlas", "Initialize" }
local EMPTY_SLOT_ATLASES = { ["bags-item-slot64"] = true, ["warband-bank-slot"] = true }

local HeldArt = FS.HeldArt
local HoldRegion, HoldNormalTexture, HookNormalSetters = HeldArt.Hold, HeldArt.HoldNormal, HeldArt.HookSetters

-- The slot's icon region by Blizzard's own lookup (GetItemButtonIconTexture in ItemButtonTemplate.lua): `Icon`, then `icon`, then
-- the global `<name>IconTexture`. Only the ItemButton intrinsic's `icon` was read before, so a template that names it `Icon`
-- (the other item button templates do) never had the empty-art clear or the corner and ring follow installed.
local function ItemIcon(button)
    if type(button) ~= "table" then return nil end
    local icon = button.Icon
    if type(icon) ~= "table" then icon = button.icon end
    if type(icon) ~= "table" and type(button.GetName) == "function" then
        local ok, name = pcall(button.GetName, button)
        if ok and type(name) == "string" then icon = _G[name .. "IconTexture"] end
    end
    if type(icon) == "table" then return icon end
    return nil
end

local GLOW_FIELDS = { "NewItemTexture", "BattlepayItemTexture", "flash", "IconQuestTexture" }
local GLOW_ANIMS = { "newitemglowAnim", "flashAnim" }
local stoppedAnims = setmetatable({}, { __mode = "k" })

local function SweepSlotArt(button)
    if not button then return end
    HoldNormalTexture(button)
    for _, field in ipairs(ART_FIELDS) do HoldRegion(button[field]) end
    for _, field in ipairs(GLOW_FIELDS) do HoldRegion(button[field]) end
    for _, field in ipairs(GLOW_ANIMS) do
        local anim = button[field]
        if type(anim) == "table" and type(anim.Stop) == "function" then
            pcall(anim.Stop, anim)
            if not stoppedAnims[anim] and type(hooksecurefunc) == "function"
                and pcall(hooksecurefunc, anim, "Play", function(self) pcall(self.Stop, self) end) then
                stoppedAnims[anim] = true
            end
        end
    end
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
    local icon = ItemIcon(button)
    if not icon then return end

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
local function IconArtIsAnItem(button, icon)
    if not ReadIcon(icon, "IsShown") then return false end
    local texture, atlas = ReadIcon(icon, "GetTexture"), ReadIcon(icon, "GetAtlas")
    if FS.IsSecret and (FS.IsSecret(texture) or FS.IsSecret(atlas)) then return true end
    if type(atlas) == "string" then return not IsEmptySlotArt(button, atlas) end
    return texture ~= nil and not IsEmptySlotArt(button, texture)
end

-- The art alone cannot tell an item from Blizzard's empty-slot art once the patch renames that art, so for a bag slot the
-- item API has the last word: a slot it reports empty never holds an item, whatever its icon shows.
local function IconHoldsItem(button)
    local icon = ItemIcon(button)
    if not icon then return false end
    if not IconArtIsAnItem(button, icon) then return false end
    return SlotIsEmpty(button) ~= true
end

local function SyncIconCorners(button)
    local corners = button.fsBagCorners
    -- An inset icon (DecorateSlot) has no corner past the cut. The wedge was opaque panel ink over a panel the world shows
    -- through, so it read as a black notch in every cut corner.
    if corners then corners:SetShown(not insetIcons[button] and IconHoldsItem(button)) end
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

-- The ring (the cut outline Theme.SkinButton puts on every slot) takes the colour of the item's quality, so junk and
-- good items read apart at a glance. The default ring, on an empty or Common slot, is the dark violet
-- Theme.COLOR_BAG_RING (#5b2d9e; COLOR_BORDER on a Theme without it), dark enough that Blizzard's bright Epic purple
-- stands clear of it. Poor is grey; Uncommon, Rare, Epic, Legendary and up take Blizzard's bag colour for that
-- quality; an unknown quality and anything unreadable keep the default ring. Only the ring: the glow, the plate and
-- the icon are not touched. (BagBar.lua tints its slot edges the same way from Uncommon up.)
--
-- Colours: ColorManager.GetColorDataForBagItemQuality, the colours Blizzard's own item border used on these slots, and
-- the player's colour overrides come through it (12.1 ColorManager.lua). It has no Poor entry, so Poor reads
-- ColorManager.GetColorDataForItemQuality(0), also override-aware. A client without ColorManager falls back to the
-- ITEM_QUALITY_COLORS table BagBar.lua reads, and a client with neither keeps the default ring and logs once.
--
-- The quality is read per slot, not from Blizzard's border: C_Container.GetContainerItemInfo(bag, slot) for a container slot,
-- the `itemInfo` Blizzard just read for a bank slot (BankPanelItemButtonMixin:RefreshItemInfo). Both are plain
-- numbers on this API; a secret answer is never compared and keeps the default ring. The read happens on every skin
-- pass, which follows every UpdateItems and bank refresh, in combat too (bags are usable in combat, this API is not
-- restricted, and only our own ring region is written). The icon's state hooks re-apply the cached colour: an
-- icon that no longer holds an item drops it at once, without waiting for a pass.
local QUALITY_POOR, QUALITY_UNCOMMON = 0, 2   -- Enum.ItemQuality

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

-- True when the item API says this BAG slot holds nothing, false when it holds something, nil when that cannot be told (a
-- bank slot, no API, a secret answer). It reads (GetBagID, GetID) exactly as ContainerFrameMixin:UpdateItems does, so it
-- is the same answer Blizzard just painted from.
SlotIsEmpty = function(button)
    if not bagSlots[button] then return nil end
    if type(C_Container) ~= "table" or type(C_Container.GetContainerItemInfo) ~= "function" then return nil end
    local bag = BagIDOf(button)
    if not bag or type(button.GetID) ~= "function" then return nil end
    local okSlot, slot = pcall(button.GetID, button)
    if not okSlot or type(slot) ~= "number" or IsSecretValue(slot) then return nil end
    local ok, info = pcall(C_Container.GetContainerItemInfo, bag, slot)
    if not ok or IsSecretValue(info) then return nil end
    return info == nil
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
    if quality ~= QUALITY_POOR and quality < QUALITY_UNCOMMON then return nil end -- Common, and anything below Poor
    return QualityColorChannels(quality)
end

-- Reads the slot's item now and caches the ring colour it earns.
-- The slot's quest state (C_Container.GetContainerItemQuestInfo): isQuest when it holds a quest item, starts when the item
-- begins a quest not yet taken (the stock bag shows a "!" for it, TEXTURE_ITEM_QUEST_BANG on IconQuestTexture). Both false
-- when it cannot be read.
local function SlotQuestState(button)
    if not bagSlots[button] or type(C_Container) ~= "table" or type(C_Container.GetContainerItemQuestInfo) ~= "function" then
        return false, false
    end
    local bag = BagIDOf(button)
    if not bag or type(button.GetID) ~= "function" then return false, false end
    local okSlot, slot = pcall(button.GetID, button)
    if not okSlot or type(slot) ~= "number" or IsSecretValue(slot) then return false, false end
    local ok, quest = pcall(C_Container.GetContainerItemQuestInfo, bag, slot)
    if not ok or IsSecretValue(quest) or type(quest) ~= "table" then return false, false end
    local isQuest, questID, isActive = quest.isQuestItem, quest.questID, quest.isActive
    if IsSecretValue(isQuest) or IsSecretValue(questID) or IsSecretValue(isActive) then return false, false end
    local hasQuest = type(questID) == "number" and questID > 0
    return isQuest == true or hasQuest, hasQuest and not isActive
end

-- The quest-start mark: the stock "!" lives on IconQuestTexture, which is held (square art past the cut ring), so a
-- quest starter gets our own amber "!" in the slot's top-left corner instead. Kept off the button's fields (bangs).
local bangs = setmetatable({}, { __mode = "k" })
local function SyncQuestBang(button, starts)
    local bang = bangs[button]
    if not bang then
        if not starts or type(button.CreateFontString) ~= "function" then return end
        bang = button:CreateFontString(nil, "OVERLAY", nil, 7)
        if type(FS.Theme.ApplyFontGeneric) == "function" then
            FS.Theme.ApplyFontGeneric(bang, FS.Theme.FONT_MONO, 16, FS.Theme.COLOR_AMBER, "OUTLINE")
        else
            bang:SetFont(FS.Theme.FONT_MONO, 16, "OUTLINE")
        end
        local amber = FS.Theme.COLOR_AMBER or { 1, 0.71, 0.28 }
        bang:SetTextColor(amber[1], amber[2], amber[3], 1)
        bang:SetPoint("TOPLEFT", button, "TOPLEFT", 5, -3)
        bang:SetText("!")
        bangs[button] = bang
    end
    bang:SetShown(starts and IconHoldsItem(button) and true or false)
end

local function ReadSlotRing(button)
    local info = SlotItemInfo(button)
    local r, g, b = QualityRingColor(info and info.quality)
    local isQuest, starts = SlotQuestState(button)
    if isQuest then
        local amber = FS.Theme.COLOR_AMBER
        if amber then r, g, b = amber[1], amber[2], amber[3] end
    end
    button.fsBagRingColor = r and { r, g, b } or nil
    SyncQuestBang(button, starts)
end

-- Writes the ring: the cached quality colour while the icon holds an item, else the default ring.
local function SyncSlotRing(button)
    local skin = button.fsSkin
    local ring = skin and skin.border and skin.border.ring
    if not ring then return end
    if not IconHoldsItem(button) then button.fsBagRingColor = nil end
    local color = button.fsBagRingColor or FS.Theme.COLOR_BAG_RING or FS.Theme.COLOR_BORDER
    if color then ring:SetVertexColor(color[1], color[2], color[3], 1) end
end

-- The empty-slot well. An empty bag slot's stock art is the ICON pointed at an atlas (emptyBackgroundAtlas, ItemButtonTemplate
-- SetItemButtonTexture_Base), and what the older code had was a name match on that atlas, installed per button once, on
-- the one `icon` key, with IconHoldsItem counting any unrecognised art as an item (so the wedge and ring then treated the
-- slot as filled). Why the pouch still showed in game could not be read offline (the release client's art is not in the
-- repo); each of those is a way for it to slip past, and none of them can fail a cover that follows the item API. The
-- well does not look at the art. It is the slot plate's own shape,
-- drawn over the icon (OVERLAY -3: above the icon, under the corner wedge, the glow and the ring) and shown exactly while
-- the item API says the slot is empty, so whatever Blizzard puts in an empty icon is covered, and that art is also cleared
-- off the icon (the same SetTexture(nil) the exact-name clear makes). Our own region only: nothing protected is touched.
local WELL_SUBLEVEL = -3

local wellWarned = false
local function AddWell(button)
    if wells[button] ~= nil then return end   -- made, or failed once (false): never retried, so no orphan region per pass
    local Theme = FS.Theme
    if type(Theme.AddCut2Texture) ~= "function" or not Theme.SLICE_CUT2_BUTTON_TEXTURE then return end -- AddPlate logs it
    local ok, well = pcall(Theme.AddCut2Texture, button, Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "OVERLAY", WELL_SUBLEVEL)
    if not ok then
        wells[button] = false
        if not wellWarned then
            wellWarned = true
            FS.LogDegradeOnce("bags_well", "Bags.lua: no empty-slot well: " .. tostring(well))
        end
        return
    end
    well:Hide()
    wells[button] = well
end

-- Drops whatever art an emptied bag slot's icon still wears (an atlas or a texture; a secret one is left alone).
local function ClearIconArt(icon)
    if type(icon) ~= "table" then return end
    local atlas, texture = ReadIcon(icon, "GetAtlas"), ReadIcon(icon, "GetTexture")
    if IsSecretValue(atlas) or IsSecretValue(texture) then return end
    if atlas ~= nil or texture ~= nil then ClearEmptyIcon(icon) end
end

local function SyncWell(button)
    local well = wells[button]
    if not well then return end
    local empty = SlotIsEmpty(button) == true
    well:SetShown(empty)
    if empty then ClearIconArt(ItemIcon(button)) end
end

-- The shared item slot's layer (Core/ItemSlotSkins.lua: quality LED and 2 px edge, glint, hover brackets, cooldown drain, locked
-- tape) sits over this base skin and asks what the slot holds through this reader. The item API answers it fresh each time (the
-- lock state changes without any of the icon's art changing), never a cached ring colour; a quality or lock flag that cannot
-- be read plainly is the layer's to treat as unknown. The layer is absent from a build without the file (and from the Bags
-- harness), so every call here is a no-op then.
local function SlotDecorState(button)
    local info = SlotItemInfo(button)
    return { quality = info and info.quality, locked = info and info.isLocked, empty = not IconHoldsItem(button) }
end

local function DecorateSlot(button)
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Decorate and slotSkins.Decorate(button, SlotDecorState) and slotSkins.SeatIcon then
        -- the icon in the layer's inset box: its corners clear the cut, so the corner wedge is not shown under the layer
        slotSkins.SeatIcon(button, ItemIcon(button))
        insetIcons[button] = true
    end
end

local function RefreshSlotDecor(button)
    local slotSkins = FS.ItemSlotSkins
    if slotSkins and slotSkins.Refresh then slotSkins.Refresh(button) end
end

-- Everything that follows the icon: the well, the corner wedge, the ring and the shared slot layer.
local function SyncSlot(button)
    SyncWell(button)
    SyncIconCorners(button)
    SyncSlotRing(button)
    RefreshSlotDecor(button)
end

-- One post-hook per icon state setter (no method replaced), installed once per button.
-- Item icon art carries a light 1 to 2 px bevel of its own, which showed as a silver edge at the slot's two uncut
-- corners, inside our ring. The icon is cropped 7% a side as on the action bars; SetAtlas (the empty-slot art)
-- writes its own coords, so the crop goes back on after every texture or atlas the icon takes.
local ICON_CROP = { 0.07, 0.93, 0.07, 0.93 }
local function CropIcon(icon)
    if type(icon.SetTexCoord) == "function" then pcall(icon.SetTexCoord, icon, ICON_CROP[1], ICON_CROP[2], ICON_CROP[3], ICON_CROP[4]) end
end

local function HookIconState(button)
    local icon = ItemIcon(button)
    if not icon or type(hooksecurefunc) ~= "function" then return end
    CropIcon(icon)
    local function sync() CropIcon(icon); SyncSlot(button) end
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
local function SkinItemButton(button, isBagSlot)
    if not button then return end
    SweepSlotArt(button)
    if isBagSlot then bagSlots[button] = true end
    if not button.fsBagItemSkinned then
        button.fsBagItemSkinned = true

        HookNormalSetters(button, ART_SETTERS, SweepSlotArt)
        HookEmptyIcon(button)
        AddPlate(button)
        if SkinCutButton then
            SkinCutButton(button, { count = button.Count })
        end
        AddIconCorners(button)
        if isBagSlot then AddWell(button) end
        HookIconState(button)
        DecorateSlot(button)
    end
    if isBagSlot and wells[button] == nil then AddWell(button) end
    ReadSlotRing(button)
    SyncSlot(button)
end

-- Calls fn(itemButton) for every currently-valid item button of a container or
-- the combined-bag frame: container.Items[1 .. size], the slots Blizzard's own
-- EnumerateValidItems walks.
--
-- Never call EnumerateValidItems (or GetBagSize) from here. GetBagSize fills
-- `self.size` itself when it is nil (a container frame never generated, or the
-- individual frames while the combined window is in use), so from addon code
-- that write lands under OUR taint. The stock item click reads the frame's
-- size, so a later right click on a bag item became ADDON_ACTION_FORBIDDEN
-- UseContainerItem (live 2026-11-18: the block-time sweep found
-- ContainerFrame1-6.size written by forever-stuwave). Reading the field is
-- harmless; a nil size means no valid slots yet, so nothing to visit.
local function EachContainerItem(container, fn)
    if type(container) ~= "table" or type(container.Items) ~= "table" then return end
    local size = rawget(container, "size")
    if type(size) ~= "number" then return end
    for i = 1, size do
        local itemButton = container.Items[i]
        if not itemButton then return end
        fn(itemButton)
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

-- One container that throws must not skip the others; logged once.
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
local RefreshWindow  -- (frame): lays the window out around the grid; defined with the window below

local function SkinContainerItems(container)
    local shown = container and ContainerShown(container) or false
    EachContainerItem(container, function(itemButton)
        SkinItemButton(itemButton, true)
        SyncItemHighlight(itemButton, shown)
    end)
    if container and RefreshWindow then RefreshWindow(container) end
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
-- Window: header row, item grid, footer (the approved bag redesign)
-------------------------------------------------------------------------------

-- Design: mockups/minimap-bags-cleanup-2026-11-12.html, "BAGS // HEADER + LEFTOVER ART", the PROPOSED panel (drawn at 2x:
-- every number below is that mockup's pixels halved). From the top: the window edge, MARGIN, one header row (the search
-- field from the grid's left edge, the sort key and the close key ending on the grid's right edge), MARGIN, the item
-- grid, RULE_GAP, a one pixel violet rule, the footer line (slot count at the grid's left edge, money at its right
-- edge), the window edge FOOT_BELOW under the grid.
--
-- Blizzard keeps ~75 units above the grid for its own title, search box and buttons and anchors the grid to the money
-- frame, and neither can change without replacing container methods, so the window is OUR chrome frame, a child of the
-- container, sized around the MEASURED item grid (the window's top lies below the container's top, its bottom a little
-- under the container's bottom). What Blizzard owns and keeps (the search box, the sort button, the close button and the
-- money frame) is not replaced: the first three keep their scripts, get their stock art held invisible (FS.HeldArt) and
-- are re-anchored onto our rects after every Blizzard placement (the post-hook on UpdateItems already there runs after
-- ContainerFrameMixin:UpdateSearchBox in Update()); the money frame stays functional at alpha 0 while our own footer shows
-- the amount. Item buttons are never anchored to, resized or reparented, and every anchor of ours points at the container
-- or at our own frames, so a protected container is left alone in combat.
--
-- The watched-currency strip (BackpackTokenFrame, shown under the money line while a currency is on the backpack) is not in
-- the approved mockup; it was Blizzard's gold-edged box hanging off the window and over the footer. While it is shown the
-- window gets a row of its own for it under the footer (a cut plate of ours under it, the strip seated on the row the way the
-- search box is, its border art held, its counts in the footer's mono); with no strip the window is exactly the approved one.
-- Structure from the retail 12.1.0 Blizzard_TokenUI and ContainerFrame.lua (the 16001 dump has the frame, not its children).
--
-- Pixels: every edge is a whole screen pixel (a design value is rounded once, so equal values give equal pixel counts at
-- any UI scale); a key is the next EVEN pixel count up from its 17 units, so a glyph of even size centres exactly.
local METRICS = {
    MARGIN = 7,          -- window edge to the header row, the row to the grid, the window edge to the grid sides
    KEY = 17,            -- the sort and close keys, and the height of the search field
    KEY_GAP = 4,         -- sort key to close key
    SEARCH_GAP = 6,      -- search field to sort key
    CELL = 19,           -- the magnifier's cell at the left of the search field
    KEY_CHAMFER = 3,
    SEARCH_CHAMFER = 4,
    RULE_GAP = 7,        -- grid to the footer rule
    FOOT_BELOW = 27,     -- grid to the window's bottom edge
    FONT = 11,           -- the footer's mono size, the data bar's
    TOKEN_H = 17,        -- the watched-currency strip under the footer (its stock height); only while Blizzard shows it
    TOKEN_PAD = 13,      -- the stock strip's padding right of its last token: tokens sit 17 from its edge, their icon 4 past that
}

-- The layout of one window in UI units, from the grid's size and the pixels per unit. Positions are from the chrome's top
-- left corner (x right, y down). opts.search / opts.sort: whether the header row has them (a bag without them has the
-- close key alone). opts.tokens: whether Blizzard's watched-currency strip is shown in this window (it gets a row of its
-- own under the footer). Pure: no frame is read or written.
local function ComputeLayout(gridWidth, gridHeight, es, opts)
    opts = opts or {}
    local function px(units) return math.floor(units * es + 0.5) end
    local function even(units)
        local n = math.max(2, math.ceil(units * es - 1e-6))
        if n % 2 == 1 then n = n + 1 end
        return n
    end
    local m, key = px(METRICS.MARGIN), even(METRICS.KEY)
    local keyGap, searchGap, cell = px(METRICS.KEY_GAP), px(METRICS.SEARCH_GAP), even(METRICS.CELL)
    local gw, gh = math.max(1, px(gridWidth)), math.max(1, px(gridHeight))

    local gridLeft, gridTop = m, m + key + m
    local gridRight, gridBottom = gridLeft + gw, gridTop + gh
    local width = gridRight + m
    local ruleY = gridBottom + px(METRICS.RULE_GAP)
    local footBottom = gridBottom + px(METRICS.FOOT_BELOW)
    local height = footBottom
    local bandTop = ruleY + 1
    local centre = math.floor((bandTop + footBottom) / 2 + 0.5)
    -- the watched-currency strip: a row under the footer (the window grows by the strip and a margin under it). Blizzard's
    -- strip keeps 13 of padding right of its last token, so its frame ends that much less MARGIN past the plate: the tokens
    -- then end a margin inside the plate like everything else
    local tokens
    if opts.tokens then
        tokens = { x = gridLeft, y = footBottom, w = gw, h = px(METRICS.TOKEN_H), slack = px(METRICS.TOKEN_PAD) - m }
        height = footBottom + tokens.h + m
    end

    local closeX = gridRight - key
    local out = {
        es = es, width = width, height = height,
        grid = { left = gridLeft, right = gridRight, top = gridTop, bottom = gridBottom },
        close = { x = closeX, y = m, w = key, h = key },
        rule = { x = gridLeft, y = ruleY, w = gw, h = 1 },
        band = { y = bandTop, h = footBottom - bandTop },
        count = { x = gridLeft, cy = centre },
        money = { right = gridRight, cy = centre },
        tokens = tokens,
    }
    local rightEdge = closeX
    if opts.sort then
        local sortX = closeX - keyGap - key
        out.sort = { x = sortX, y = m, w = key, h = key }
        rightEdge = sortX
        if opts.search then
            local w = sortX - searchGap - gridLeft
            if w >= cell + px(8) then
                out.search = { x = gridLeft, y = m, w = w, h = key }
                out.cell = { x = gridLeft, y = m, w = cell, h = key }
            end
        end
    end
    -- every value above is a whole pixel count so far; back to units
    local function units(t)
        for k, v in pairs(t) do
            if type(v) == "table" then units(v) elseif type(v) == "number" and k ~= "es" then t[k] = v / es end
        end
    end
    units(out)
    return out
end

-- The pixels per UI unit at `frame`; 1 when the client will not say.
local function PixelsPerUnit(frame)
    local helpers = FS.FrameHelpers
    if not (helpers and helpers.PixelsPerUnit) then return 1 end
    local ok, ppu = pcall(helpers.PixelsPerUnit, frame)
    if ok and type(ppu) == "number" and ppu > 0 and not IsSecretValue(ppu) then return ppu end
    return 1
end

local function RoundPx(units, es) return math.floor(units * es + 0.5) / es end

-- One frame's rect { left, right, top, bottom }, nil unless all four are plain numbers.
local function ReadRect(object)
    if type(object) ~= "table" then return nil end
    local function get(method)
        if type(object[method]) ~= "function" then return nil end
        local ok, value = pcall(object[method], object)
        if not ok or type(value) ~= "number" or IsSecretValue(value) then return nil end
        return value
    end
    local l, r, t, b = get("GetLeft"), get("GetRight"), get("GetTop"), get("GetBottom")
    if l and r and t and b then return { left = l, right = r, top = t, bottom = b } end
    return nil
end

-- The item grid's bounding rect, measured from the item buttons themselves (read only: a geometry read of a secure button
-- is allowed in combat, and nothing is ever anchored to one).
local function GridRect(container)
    local grid
    local ok = pcall(EachContainerItem, container, function(itemButton)
        local rect = ReadRect(itemButton)
        if not rect then return end
        if not grid then
            grid = { left = rect.left, right = rect.right, top = rect.top, bottom = rect.bottom }
        else
            grid.left, grid.right = math.min(grid.left, rect.left), math.max(grid.right, rect.right)
            grid.top, grid.bottom = math.max(grid.top, rect.top), math.min(grid.bottom, rect.bottom)
        end
    end)
    return ok and grid or nil
end

-- True when the frame is protected AND we are in combat: its anchors, and anything anchored to it, are off limits.
local function FrameLocked(frame)
    if not (InCombatLockdown and InCombatLockdown()) then return false end
    if type(frame.IsProtected) ~= "function" then return false end
    local ok, protected = pcall(frame.IsProtected, frame)
    return ok and protected and true or false
end

local function Snap(texture)
    if texture and texture.SetSnapToPixelGrid then
        pcall(texture.SetSnapToPixelGrid, texture, true)
        if texture.SetTexelSnappingBias then pcall(texture.SetTexelSnappingBias, texture, 0) end
    end
end

-- Glyphs: pixel cells { x, y, w, h [, colour] } on a grid of PHYSICAL pixels (like the close X of ButtonSkins), laid out
-- with an even bounding box so they centre exactly in an even-pixel slot.
local SORT_CELLS = {                 -- three stepped bars (long, medium, short) and a down arrow: 14 x 8
    { 0, 0, 8, 2, "bars" }, { 0, 3, 6, 2, "bars" }, { 0, 6, 4, 2, "bars" },
    { 11, 0, 1, 7, "arrow" },
    { 9, 5, 1, 1, "arrow" }, { 10, 6, 1, 1, "arrow" }, { 11, 7, 1, 1, "arrow" }, { 12, 6, 1, 1, "arrow" }, { 13, 5, 1, 1, "arrow" },
}
local SEARCH_CELLS = {               -- a lens and its handle: 10 x 10
    { 2, 0, 3, 1 }, { 2, 6, 3, 1 }, { 0, 2, 1, 3 }, { 6, 2, 1, 3 },
    { 1, 1, 1, 1 }, { 5, 1, 1, 1 }, { 1, 5, 1, 1 }, { 5, 5, 1, 1 },
    { 6, 6, 1, 1 }, { 7, 7, 1, 1 }, { 8, 8, 1, 1 }, { 9, 9, 1, 1 },
}
local X_FALLBACK = 6

local function CloseCells()
    local skins = FS.ButtonSkins
    local cells = {}
    local n = (skins and skins.X and skins.X.GLYPH) or X_FALLBACK
    local source = skins and skins.XCells and skins.XCells(n)
    if not source then
        source = {}
        for k = 0, n - 1 do source[#source + 1] = { k, k }; source[#source + 1] = { n - 1 - k, k } end
    end
    for _, c in ipairs(source) do cells[#cells + 1] = { c[1], c[2], 1, 1 } end
    return cells
end

-- Where each glyph's cells go, per plate. Plate state (hover, pressed, focus) is kept here, never on a Blizzard frame.
local windows = setmetatable({}, { __mode = "k" })   -- container -> its window pieces
local controlHooked = setmetatable({}, { __mode = "k" }) -- Blizzard control -> our state hooks are in
local controlsHeld = setmetatable({}, { __mode = "k" })  -- Blizzard control -> its art is held
local searchStyled = setmetatable({}, { __mode = "k" })  -- search box -> its fonts are set
local layoutPending = false                             -- a protected window was not laid out in combat

local windowWarned = false
local function WarnWindow(why)
    if windowWarned then return end
    windowWarned = true
    FS.LogDegradeOnce("bags_window", "Bags.lua: bag window not drawn, " .. why)
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local WHITE = { 1, 1, 1 }
local PLATE_STATES = {   -- glyph lift toward white, halo alpha
    normal  = { lift = 0,    halo = 0.12 },
    hover   = { lift = 0.12, halo = 0.45 },
    pressed = { lift = 0.40, halo = 0.30 },
}

-- One plate: our own frame with the cut ring (Theme.SkinButton at the plate's chamfer) and, for the search field, an ink
-- face. `colour` is the ring colour, `ringAlpha` its normal alpha.
local function NewPlate(chrome, colour, chamfer, ringAlpha, ink)
    local Theme = FS.Theme
    local plate = CreateFrame("Frame", nil, chrome)
    plate:SetFrameLevel(chrome:GetFrameLevel())
    local skin = Theme.SkinButton(plate, { borderColor = colour, chamfer = chamfer, cut = true, glowAlpha = PLATE_STATES.normal.halo })
    if not (skin and skin.border and skin.border.ring) then error("Theme.SkinButton gave no ring") end
    local face
    if ink then
        face = type(Theme.AddCutSliceFill) == "function" and Theme.AddCutSliceFill(plate, ink, chamfer) or nil
        if not face then
            face = plate:CreateTexture(nil, "BACKGROUND")
            face:SetAllPoints(plate)
            face:SetColorTexture(ink[1], ink[2], ink[3], ink[4] or 1)
        end
    end
    return { frame = plate, skin = skin, face = face, colour = colour, ringAlpha = ringAlpha, glyph = {}, state = {} }
end

local function PaintPlate(piece)
    local state = PLATE_STATES.pressed
    if not piece.state.pressed then state = (piece.state.hover and PLATE_STATES.hover) or PLATE_STATES.normal end
    local c = piece.colour
    local ring = piece.skin.border.ring
    local alpha = piece.ringAlpha
    if piece.focusRing and (piece.state.focus or piece.state.hover) then alpha = piece.state.focus and 1 or 0.8 end
    ring:SetVertexColor(c[1], c[2], c[3], alpha)
    if piece.skin.glow then piece.skin.glow:SetVertexColor(c[1], c[2], c[3], state.halo) end
    for _, t in ipairs(piece.glyph) do
        local base = t.base
        local g = Mix(base, WHITE, state.lift)
        t.texture:SetColorTexture(g[1], g[2], g[3], 1)
    end
end

-- Lays a glyph's cells in a slot of slotW x slotH physical pixels, its bounding box centred.
local function SeatGlyph(piece, host, cells, colours, slotW, slotH, es)
    local seatKey = slotW .. ":" .. slotH .. ":" .. es
    if piece.seatKey == seatKey then return end
    piece.seatKey = seatKey
    local minX, minY, maxX, maxY = math.huge, math.huge, -math.huge, -math.huge
    for _, c in ipairs(cells) do
        minX, minY = math.min(minX, c[1]), math.min(minY, c[2])
        maxX, maxY = math.max(maxX, c[1] + c[3]), math.max(maxY, c[2] + c[4])
    end
    local ox = math.floor((slotW - (maxX - minX)) / 2) - minX
    local oy = math.floor((slotH - (maxY - minY)) / 2) - minY
    local px = 1 / es
    for i, c in ipairs(cells) do
        local entry = piece.glyph[i]
        if not entry then
            local t = host:CreateTexture(nil, "OVERLAY", nil, 3)
            Snap(t)
            entry = { texture = t }
            piece.glyph[i] = entry
        end
        entry.base = colours[c[5] or "main"] or colours.main
        local t = entry.texture
        t:ClearAllPoints()
        t:SetSize(c[3] * px, c[4] * px)
        t:SetPoint("TOPLEFT", host, "TOPLEFT", (ox + c[1]) * px, -(oy + c[2]) * px)
        t:Show()
    end
    for i = #cells + 1, #piece.glyph do piece.glyph[i].texture:Hide() end
end

-- Hover / press / focus follow Blizzard's own control (a post-hook per script; nothing replaced), once per control. The
-- search box and the sort button are SHARED by the backpack and the combined window, so the hook looks up the window that
-- owns the control (its parent) when it fires, and paints that window's plate under `key`.
local function FollowControl(control, key, scripts)
    if type(control) ~= "table" or controlHooked[control] or type(control.HookScript) ~= "function" then return end
    controlHooked[control] = true
    for script, apply in pairs(scripts) do
        pcall(control.HookScript, control, script, function(self)
            local okParent, parent = pcall(self.GetParent, self)
            local win = okParent and windows[parent] or nil
            local piece = win and win[key]
            if piece then apply(piece.state); PaintPlate(piece) end
        end)
    end
end

local function HoldControl(control)
    if type(control) ~= "table" or controlsHeld[control] then return end
    controlsHeld[control] = true
    HeldArt.HoldButton(control)
end

local function MoneyAmountText(amount)
    if type(amount) ~= "number" or IsSecretValue(amount) or amount < 0 then return nil end
    amount = math.floor(amount)
    local gold, silver, copper = math.floor(amount / 10000), math.floor(amount / 100) % 100, amount % 100
    local function piece(color, text)
        return string.format("|cff%02x%02x%02x%s|r", math.floor(color[1] * 255 + 0.5), math.floor(color[2] * 255 + 0.5),
            math.floor(color[3] * 255 + 0.5), text)
    end
    local parts = {}
    if gold > 0 then parts[#parts + 1] = piece(COIN_GOLD, gold .. "g") end
    if gold > 0 or silver > 0 then parts[#parts + 1] = piece(COIN_SILVER, silver .. "s") end
    parts[#parts + 1] = piece(COIN_COPPER, copper .. "c")
    return table.concat(parts, " ")
end

-- Slots in use over slots, from the item API (the icon art when the API cannot say).
local function SlotCount(frame)
    local used, total = 0, 0
    pcall(EachContainerItem, frame, function(itemButton)
        total = total + 1
        local empty = SlotIsEmpty(itemButton)
        if empty == nil then
            if IconHoldsItem(itemButton) then used = used + 1 end
        elseif not empty then
            used = used + 1
        end
    end)
    return used, total
end

local function FrameShown(object)
    if type(object) ~= "table" or type(object.IsShown) ~= "function" then return false end
    local ok, shown = pcall(object.IsShown, object)
    return ok and shown and true or false
end

local function RefreshFooter(frame)
    local win = windows[frame]
    if not (win and win.count) then return end
    local used, total = SlotCount(frame)
    win.count:SetText(used .. "/" .. total)
    if win.hasMoney then
        local ok, amount = pcall(GetMoney)
        local text = ok and MoneyAmountText(amount) or nil
        if text then win.money:SetText(text) end
    end
end

-- The window's pieces, made once per container. Returns the pieces, or nil (with one log) when the Theme cannot draw it.
local function BuildWindow(frame)
    local Theme = FS.Theme
    if type(Theme.StripBlizzardChrome) ~= "function" or type(Theme.SkinButton) ~= "function" or type(frame.CreateFontString) ~= "function"
        or type(CreateFrame) ~= "function" then
        WarnWindow("Theme.StripBlizzardChrome / SkinButton missing")
        return nil
    end
    local chrome
    local ok, err = pcall(function()
        Theme.StripBlizzardChrome(frame)
        chrome = CreateFrame("Frame", nil, frame)
        chrome:SetFrameLevel(frame:GetFrameLevel())
        chrome:Hide()
        SkinPanel(chrome, { strip = false })

        local win = { chrome = chrome, state = {} }
        local ink = Theme.COLOR_BAR_TRACK or { 0.039, 0.016, 0.086, 1 }
        local cyan, violet, pink = Theme.COLOR_POWER or { 0.133, 0.878, 1, 1 }, Theme.COLOR_BORDER or { 0.659, 0.333, 0.969, 1 },
            Theme.COLOR_HEALTH or { 1, 0.18, 0.592, 1 }
        local muted = Theme.COLOR_MUTED or { 0.616, 0.577, 0.769, 1 }

        win.search = NewPlate(chrome, cyan, METRICS.SEARCH_CHAMFER, 0.55, ink)
        win.search.focusRing = true
        win.sort = NewPlate(chrome, violet, METRICS.KEY_CHAMFER, 1)
        win.close = NewPlate(chrome, pink, METRICS.KEY_CHAMFER, 1)
        win.tokens = NewPlate(chrome, violet, METRICS.SEARCH_CHAMFER, 0.55, ink)
        win.searchPlate, win.sortPlate, win.closePlate = win.search.frame, win.sort.frame, win.close.frame
        win.tokensPlate = win.tokens.frame
        win.searchPlate:Hide(); win.sortPlate:Hide(); win.closePlate:Hide(); win.tokensPlate:Hide()
        win.searchCell = CreateFrame("Frame", nil, win.searchPlate)
        win.searchCell:SetFrameLevel(win.searchPlate:GetFrameLevel())
        win.searchCell:SetPoint("TOPLEFT", win.searchPlate, "TOPLEFT", 0, 0)

        win.colours = {
            search = { main = muted }, sort = { bars = violet, arrow = cyan, main = violet }, close = { main = pink },
        }

        win.rule = chrome:CreateTexture(nil, "ARTWORK")
        win.rule:SetColorTexture(violet[1], violet[2], violet[3], 0.40)
        Snap(win.rule)
        win.rule:Hide()
        if type(Theme.ApplyMono) == "function" then
            win.count = chrome:CreateFontString(nil, "OVERLAY")
            Theme.ApplyMono(win.count, METRICS.FONT, cyan)
            win.money = chrome:CreateFontString(nil, "OVERLAY")
            Theme.ApplyMono(win.money, METRICS.FONT, { 1, 1, 1 })
            win.count:Hide(); win.money:Hide()
        end

        -- Blizzard's own pieces that stay: their art goes, their scripts are untouched.
        local closeButton = frame.CloseButton
        if type(closeButton) == "table" then HoldControl(closeButton) end
        local portrait = frame.PortraitButton
        if type(portrait) == "table" then HoldRegion(portrait.Highlight) end
        HoldControl(_G["BagItemSearchBox"])
        HoldControl(_G["BagItemAutoSortButton"])

        local pointer = {
            OnEnter = function(st) st.hover = true end,
            OnLeave = function(st) st.hover, st.pressed = false, false end,
            OnMouseDown = function(st) st.pressed = true end,
            OnMouseUp = function(st) st.pressed = false end,
        }
        FollowControl(closeButton, "close", pointer)
        FollowControl(_G["BagItemAutoSortButton"], "sort", pointer)
        FollowControl(_G["BagItemSearchBox"], "search", {
            OnEnter = pointer.OnEnter, OnLeave = function(st) st.hover = false end,
            OnEditFocusGained = function(st) st.focus = true end, OnEditFocusLost = function(st) st.focus = false end,
        })
        windows[frame] = win
        for _, piece in ipairs({ win.search, win.sort, win.close, win.tokens }) do PaintPlate(piece) end
    end)
    if not ok then
        if chrome then pcall(chrome.Hide, chrome) end
        windows[frame] = nil
        WarnWindow(tostring(err))
        return nil
    end
    return windows[frame]
end

local function ControlOwned(control, frame)
    if type(control) ~= "table" or type(control.GetParent) ~= "function" then return false end
    local ok, parent = pcall(control.GetParent, control)
    return ok and parent == frame and FrameShown(control)
end

-- Puts one Blizzard control on a rect of the chrome (x, y from the chrome's top left; Blizzard may have anchored it
-- anywhere since). The control is an unprotected frame; the anchor points at our own chrome.
local function SeatControl(control, chrome, rect)
    if type(control) ~= "table" or not rect then return end
    control:ClearAllPoints()
    control:SetPoint("TOPLEFT", chrome, "TOPLEFT", rect.x, -rect.y)
    control:SetSize(rect.w, rect.h)
end

-- A window that no longer owns the shared search box and sort button (Blizzard re-parented them to another bag window) hides
-- the plates it drew for them.
local function DropLostPlates(frame, win)
    if win.searchPlate:IsShown() and not ControlOwned(_G["BagItemSearchBox"], frame) then win.searchPlate:Hide() end
    if win.sortPlate:IsShown() and not ControlOwned(_G["BagItemAutoSortButton"], frame) then win.sortPlate:Hide() end
    if win.tokensPlate:IsShown() and not ControlOwned(_G["BackpackTokenFrame"], frame) then win.tokensPlate:Hide() end
end

local function SeatPlate(piece, chrome, rect, shown)
    local f = piece.frame
    if not (rect and shown) then f:Hide(); return end
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", chrome, "TOPLEFT", rect.x, -rect.y)
    f:SetSize(rect.w, rect.h)
    f:Show()
end

-- The watched-currency strip (BackpackTokenFrame, one frame Blizzard moves between the bag windows): its border art (Left,
-- Middle, Right of the Border frame) is held, the counts of its pooled token buttons get the footer's mono face, and the
-- strip itself is seated on the window's own row like the search box is (Blizzard re-anchors it from UpdateCurrencyFrames,
-- which the container hooks below answer). The click and tooltip of each token stay Blizzard's.
local tokenHooked = setmetatable({}, { __mode = "k" })  -- strip -> its Update post-hook and art hold are in
local countStyled = setmetatable({}, { __mode = "k" })  -- token button -> its count font is set

local function StyleTokens(tracker)
    local tokens = type(tracker) == "table" and tracker.Tokens
    if type(tokens) ~= "table" or type(FS.Theme.ApplyMono) ~= "function" then return end
    for _, button in pairs(tokens) do
        local count = type(button) == "table" and button.Count
        if type(count) == "table" and not countStyled[count] then
            countStyled[count] = true
            pcall(FS.Theme.ApplyMono, count, METRICS.FONT, WHITE)
        end
    end
end

local function SkinTokens(tracker)
    if tokenHooked[tracker] then return end
    tokenHooked[tracker] = true
    local border = tracker.Border
    if type(border) == "table" then
        for _, field in ipairs({ "Left", "Middle", "Right" }) do HoldRegion(border[field]) end
    end
    if type(hooksecurefunc) == "function" and type(tracker.Update) == "function" then
        pcall(hooksecurefunc, tracker, "Update", StyleTokens)
    end
end

local function SeatTokens(tracker, chrome, rect)
    if type(tracker) ~= "table" or not rect then return end
    SkinTokens(tracker)
    tracker:ClearAllPoints()
    tracker:SetPoint("TOPLEFT", chrome, "TOPLEFT", rect.x, -rect.y)
    tracker:SetSize(rect.w + rect.slack, rect.h)
    StyleTokens(tracker)
end

local function ApplyWindow(frame, win)
    local es = PixelsPerUnit(frame)
    local rect, grid = ReadRect(frame), GridRect(frame)
    if not (rect and grid) then return end

    local searchBox, sortButton = _G["BagItemSearchBox"], _G["BagItemAutoSortButton"]
    local hasSearch, hasSort = ControlOwned(searchBox, frame), ControlOwned(sortButton, frame)
    local tracker = _G["BackpackTokenFrame"]
    local hasTokens = ControlOwned(tracker, frame)
    local lay = ComputeLayout(grid.right - grid.left, grid.top - grid.bottom, es, { search = hasSearch, sort = hasSort, tokens = hasTokens })
    win.layout = lay
    local chrome = win.chrome

    -- the chrome: its top left corner so that the grid lands on the layout's grid rect
    local dx = RoundPx(grid.left - lay.grid.left - rect.left, es)
    local dy = RoundPx(grid.top + lay.grid.top - rect.top, es)
    chrome:ClearAllPoints()
    chrome:SetPoint("TOPLEFT", frame, "TOPLEFT", dx, dy)
    chrome:SetSize(lay.width, lay.height)
    chrome:Show()

    local keyPx = math.floor(lay.close.w * es + 0.5)
    SeatPlate(win.close, chrome, lay.close, true)
    SeatPlate(win.sort, chrome, lay.sort, hasSort)
    SeatPlate(win.search, chrome, lay.search, hasSearch and lay.search ~= nil)
    SeatPlate(win.tokens, chrome, lay.tokens, hasTokens)
    if hasTokens then SeatTokens(tracker, chrome, lay.tokens) end
    SeatControl(frame.CloseButton, chrome, lay.close)
    if hasSort then SeatControl(sortButton, chrome, lay.sort) end
    if hasSearch and lay.search then
        SeatControl(searchBox, chrome, lay.search)
        local cellUnits = lay.cell.w
        if type(searchBox.SetTextInsets) == "function" then pcall(searchBox.SetTextInsets, searchBox, cellUnits, 20, 0, 0) end
        local hint = searchBox.Instructions
        if type(hint) == "table" and type(hint.SetPoint) == "function" then
            hint:ClearAllPoints()
            hint:SetPoint("BOTTOMRIGHT", searchBox, "BOTTOMRIGHT", -20, 0)
            hint:SetPoint("TOPLEFT", searchBox, "TOPLEFT", cellUnits, 0)
            if FS.Theme.ApplyMono and not searchStyled[searchBox] then
                searchStyled[searchBox] = true
                pcall(FS.Theme.ApplyMono, hint, METRICS.FONT, FS.Theme.COLOR_MUTED or { 0.616, 0.577, 0.769 })
                pcall(FS.Theme.ApplyMono, searchBox, METRICS.FONT, { 1, 1, 1 })
            end
        end
        win.searchCell:SetSize(lay.cell.w, lay.cell.h)
        SeatGlyph(win.search, win.searchCell, SEARCH_CELLS, win.colours.search, math.floor(lay.cell.w * es + 0.5), keyPx, es)
    end
    SeatGlyph(win.sort, win.sortPlate, SORT_CELLS, win.colours.sort, keyPx, keyPx, es)
    SeatGlyph(win.close, win.closePlate, CloseCells(), win.colours.close, keyPx, keyPx, es)
    for _, piece in ipairs({ win.search, win.sort, win.close }) do PaintPlate(piece) end

    -- the footer: rule, count at the grid's left edge, money at its right edge
    win.hasMoney = FrameShown(frame.MoneyFrame)
    win.rule:ClearAllPoints()
    win.rule:SetPoint("TOPLEFT", chrome, "TOPLEFT", lay.rule.x, -lay.rule.y)
    win.rule:SetSize(lay.rule.w, lay.rule.h)
    win.rule:Show()
    if win.count then
        win.count:ClearAllPoints()
        win.count:SetPoint("LEFT", chrome, "TOPLEFT", lay.count.x, -lay.count.cy)
        win.count:Show()
        win.money:ClearAllPoints()
        win.money:SetPoint("RIGHT", chrome, "TOPLEFT", lay.money.right, -lay.money.cy)
        win.money:SetShown(win.hasMoney)
        if win.hasMoney and type(frame.MoneyFrame.SetAlpha) == "function" then frame.MoneyFrame:SetAlpha(0) end
        RefreshFooter(frame)
    end

    for other, otherWin in pairs(windows) do
        if other ~= frame then DropLostPlates(other, otherWin) end
    end

    -- the container's own mouse rect shrinks to the visible window (the band above it is empty)
    if type(frame.SetHitRectInsets) == "function" then
        local l = math.max(0, dx)
        local t = math.max(0, -dy)
        local r = math.max(0, rect.right - (rect.left + dx + lay.width))
        local b = math.max(0, (rect.top + dy - lay.height) - rect.bottom)
        pcall(frame.SetHitRectInsets, frame, l, r, t, b)
    end
end

RefreshWindow = function(frame)
    local win = windows[frame]
    if not win then return end
    if FrameLocked(frame) then layoutPending = true; return end
    local ok, err = pcall(ApplyWindow, frame, win)
    if not ok then WarnWindow("layout failed: " .. tostring(err)) end
end

FS.BagsWindow = {
    Of = function(frame) return windows[frame] end,
    Layout = ComputeLayout,
    METRICS = METRICS,
}

local windowEvents = CreateFrame("Frame")
for _, event in ipairs({ "PLAYER_MONEY", "PLAYER_REGEN_ENABLED" }) do pcall(windowEvents.RegisterEvent, windowEvents, event) end
windowEvents:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if not layoutPending then return end
        layoutPending = false
    end
    for frame in pairs(windows) do
        if event == "PLAYER_MONEY" then pcall(RefreshFooter, frame) else RefreshWindow(frame) end
    end
end)

-------------------------------------------------------------------------------
-- Panel skin (idempotent via frame.fsBagSkin)
-------------------------------------------------------------------------------

-- `windowed`: a bag window (ContainerFrame1..13, the combined bags) wears the window above; the bank keeps the panel skin
-- (and so does a bag window the Theme cannot draw).
local function SkinBagFrame(frame, windowed)
    if not frame or frame.fsBagSkin then return end

    if not (windowed == true and BuildWindow(frame)) then SkinPanel(frame) end
    if not StyleBagMoney(frame) then FS.PanelSkins.TryStyleMoney(frame) end

    frame.fsBagSkin = true
end

-- OnShow of a bag window: the skin once, the layout every time (the frame may have been resized or moved since).
local function ShowBagWindow(frame)
    SkinBagFrame(frame, true)
    RefreshWindow(frame)
end

-------------------------------------------------------------------------------
-- Individual containers (ContainerFrame1..ContainerFrame13)
-------------------------------------------------------------------------------

-- Containers are re-shown/re-laid-out constantly (bag toggles, slot count
-- changes); OnShow re-applies the skin, but SkinBagFrame's fsBagSkin guard
-- means every call after the first is a cheap no-op rather than a rebuild.
local function HookContainerShow(frame, onShow)
    if not frame or frame.fsBagShowHooked then return end
    frame:HookScript("OnShow", onShow or SkinBagFrame)
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
            SkinBagFrame(frame, true)
            HookContainerShow(frame, ShowBagWindow)
            HookContainerHide(frame)
            SkinContainerItems(frame)
            HookItemRefresh(frame, "UpdateItems", SkinContainerItems)
            HookItemRefresh(frame, "UpdateCurrencyFrames", RefreshWindow)
        end
    end
end

-------------------------------------------------------------------------------
-- Combined bags (modern retail feature; player can toggle combined/individual)
-------------------------------------------------------------------------------

local function ApplyCombinedBags()
    local frame = ContainerFrameCombinedBags
    if not frame then return end

    SkinBagFrame(frame, true)
    HookContainerShow(frame, ShowBagWindow)
    HookContainerHide(frame)
    SkinContainerItems(frame)
    HookItemRefresh(frame, "UpdateItems", SkinContainerItems)
    HookItemRefresh(frame, "UpdateCurrencyFrames", RefreshWindow)
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

-- RegisterEvent throws on a name the client does not know, so each is its own pcall. Made with the build below, so with the
-- Bags switch off nothing watches the gamepad and the game's own bag bar is never hidden.
local function WatchGamepad()
    local gamepadEvents = CreateFrame("Frame")
    for _, event in ipairs({ "GAME_PAD_CONNECTED", "GAME_PAD_DISCONNECTED", "GAME_PAD_ACTIVE_CHANGED", "PLAYER_ENTERING_WORLD" }) do
        pcall(gamepadEvents.RegisterEvent, gamepadEvents, event)
    end
    gamepadEvents:SetScript("OnEvent", SyncGamepadBagBar)
end

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
    WatchGamepad()
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

-- Module power (Core/ModuleSwitch.lua): the skin, the window layout and the gamepad watch start only with the Bags switch
-- on. Off, the game's own bags, bank and bag bar are left exactly as the client draws them (FS.BagHighlight and
-- FS.BagsWindow stay defined and answer from an empty state).
local MS = FS.ModuleSwitch
local function Start()
    if MS then MS.MarkBuilt("m.bags") end
    FS.PanelSkins.DeferCombat(Apply, "m.bags")
end
if MS then MS.WhenOn("m.bags", Start) else Start() end
