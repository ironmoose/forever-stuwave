-- Forever STUwave: Bags
-- FIRST PASS reskin of the default bag UI: individual containers
-- (ContainerFrame1..ContainerFrame13, feature-detected -- NUM_CONTAINER_FRAMES
-- has varied across client revisions), the modern combined-bag frame
-- (ContainerFrameCombinedBags, confirmed present on interface 16001), and
-- BankFrame + BankPanel (both confirmed present). Every Blizzard name/function
-- is feature-detected; a missing name silently no-ops rather than erroring.
-- Item slots wear OUR plate only (the two-corner cut plate of the deck bag
-- slots and action buttons, plus its cut border); Blizzard's own slot art is
-- hidden and held hidden. The money line wears the data bar's GOLD look.
-- Blizzard's GamepadBagBar (a child of the combined bags, same frame level as
-- the Clean Up button, a bag icon) is hidden while no controller is connected:
-- on a client with the GamePadEnable CVar on and nothing plugged in it drew over
-- the Clean Up (broom) button. C_GamePad missing, C_GamePad.IsEnabled() false or
-- an empty C_GamePad.GetAllDeviceIDs() all count as "no controller". It is
-- re-hidden whenever Blizzard shows it again (post-hooks on Show/SetShown and
-- OnShow, no method replaced), re-evaluated on GAME_PAD_CONNECTED/
-- DISCONNECTED/ACTIVE_CHANGED and PLAYER_ENTERING_WORLD, left alone (and shown
-- again if we hid it) once a controller is present, and deferred out of combat.
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
-- What re-shows this art is a NEW region, not a write to a held one: the button's
-- SetNormalTexture/SetNormalAtlas can build a fresh normal texture (the money
-- buttons do after ClearNormalTexture) and Initialize builds `ItemSlotBackground`,
-- so those three methods get a post-hook that re-sweeps and holds whatever region
-- exists now. A held region also gets a post-hook on its own SetAlpha that writes
-- 0 again (MicroBars.lua's recipe: a per-REGION guard against our own write
-- re-entering the hook, a weak-keyed table so nothing is kept alive): the 12.1
-- ContainerFrame/BankFrame/ItemButton source never writes alpha on these regions,
-- so that hook is only a guard against another writer. SetAtlas and SetTexture on
-- an existing region leave its alpha alone (Blizzard re-points the bank
-- `Background` with SetAtlas, UpdateBackgroundForBankType), so they are not hooked.
--
-- Deliberately NOT touched: IconBorder (the quality border and its colour),
-- IconOverlay/IconOverlay2, NewItemTexture/BattlepayItemTexture/flash (new-item
-- glows), UpgradeIcon, JunkIcon, IconQuestTexture, searchOverlay,
-- ItemContextOverlay, Cooldown, Count, the lock/desaturate state, the pushed and
-- highlight textures (interaction feedback) and ExtendedSlot (the
-- locked-until-secured marker, ContainerFrameItemButtonMixin:UpdateExtended).
local held = setmetatable({}, { __mode = "k" })      -- region -> zeroed and its SetAlpha hook installed
local zeroing = setmetatable({}, { __mode = "k" })   -- region -> our own write is in flight
local clearing = setmetatable({}, { __mode = "k" })  -- icon -> our own clear is in flight

local ART_FIELDS = { "NormalTexture", "ItemSlotBackground", "Background" }
local ART_SETTERS = { "SetNormalTexture", "SetNormalAtlas", "Initialize" }
local EMPTY_SLOT_ATLASES = { ["bags-item-slot64"] = true, ["warband-bank-slot"] = true }

local function ZeroRegion(region)
    if zeroing[region] then return end
    zeroing[region] = true
    pcall(region.SetAlpha, region, 0)
    zeroing[region] = nil
end

local function IsTexture(region)
    if type(region) ~= "table" or type(region.GetObjectType) ~= "function" then return false end
    local ok, kind = pcall(region.GetObjectType, region)
    return ok and kind == "Texture"
end

local function HoldRegion(region)
    if held[region] or not IsTexture(region) or type(region.SetAlpha) ~= "function" then return end
    ZeroRegion(region)
    if type(hooksecurefunc) ~= "function" then
        held[region] = true -- nothing to install, nothing to retry
        return
    end
    -- Recorded only once the hook is in, so a failed install is tried again on the next sweep.
    if pcall(hooksecurefunc, region, "SetAlpha", ZeroRegion) then held[region] = true end
end

-- Holds the button's normal texture whichever way it is reached: the NormalTexture
-- parentKey, and whatever GetNormalTexture hands back now (the engine can swap it
-- for a new region, MoneyFrame_Update does after ClearNormalTexture).
local function HoldNormalTexture(button)
    HoldRegion(button.NormalTexture)
    if type(button.GetNormalTexture) == "function" then
        local ok, normal = pcall(button.GetNormalTexture, button)
        if ok then HoldRegion(normal) end
    end
end

local function HookNormalSetters(button, methods, sweep)
    if type(hooksecurefunc) ~= "function" then return end
    for _, method in ipairs(methods) do
        if type(button[method]) == "function" then pcall(hooksecurefunc, button, method, sweep) end
    end
end

local function SweepSlotArt(button)
    if not button then return end
    HoldNormalTexture(button)
    for _, field in ipairs(ART_FIELDS) do HoldRegion(button[field]) end
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

    local function isEmptyArt(value)
        if type(value) ~= "string" then return false end
        return value == button.emptyBackgroundAtlas or value == button.emptyBackgroundTexture or EMPTY_SLOT_ATLASES[value] == true
    end

    if type(icon.GetAtlas) == "function" then
        local ok, atlas = pcall(icon.GetAtlas, icon)
        if ok and isEmptyArt(atlas) then ClearEmptyIcon(icon) end
    end
    if type(hooksecurefunc) ~= "function" then return end
    if type(icon.SetAtlas) == "function" then
        pcall(hooksecurefunc, icon, "SetAtlas", function(self, atlas)
            if isEmptyArt(atlas) then ClearEmptyIcon(self) end
        end)
    end
    if button.emptyBackgroundTexture ~= nil and type(icon.SetTexture) == "function" then
        pcall(hooksecurefunc, icon, "SetTexture", function(self, texture)
            if isEmptyArt(texture) then ClearEmptyIcon(self) end
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
-- BankPanelItemButtonMixin:Refresh) is deliberately left untouched: it IS the
-- quality signal, and our ring (Theme.SkinCutButton) is a separate OVERLAY
-- layer, never a replacement. The slot art sweep runs on EVERY pass (it only
-- does work for a region it has not held yet), because a combined-bag slot
-- makes its ItemSlotBackground after our first pass.
--
-- The icon is NOT inset to the cut ring (FrameHelpers.SeatCutIcon is not
-- used), same decision as Loot.lua: icons are not inset to the cut ring. The icon
-- is a Blizzard region and the square IconBorder (37 x 37, centred) and
-- NewItemTexture over it would poke past the ring anyway, so moving only the icon
-- would detach the quality border from the item by the inset instead of fixing
-- the corners.
local function SkinItemButton(button)
    if not button then return end
    SweepSlotArt(button)
    if button.fsBagItemSkinned then return end
    button.fsBagItemSkinned = true

    HookNormalSetters(button, ART_SETTERS, SweepSlotArt)
    HookEmptyIcon(button)
    AddPlate(button)
    if SkinCutButton then
        SkinCutButton(button, { count = button.Count })
    end
end

-- Skins every currently-valid item button on a container/combined-bag frame.
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
local function SkinContainerItems(container)
    if not container then return end

    if type(container.EnumerateValidItems) == "function" then
        for _, itemButton in container:EnumerateValidItems() do
            SkinItemButton(itemButton)
        end
    elseif type(container.Items) == "table" then
        for _, itemButton in ipairs(container.Items) do
            SkinItemButton(itemButton)
        end
    end
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
local gamepadHiddenByUs = false -- we hid it, so a controller appearing puts it back
local gamepadPending = false    -- a combat-deferred sync is already queued

-- "No controller" is C_GamePad missing, gamepads disabled, or no device IDs. An
-- API that is there but errors or lacks a call is not proof either way, so it
-- counts as a controller (Blizzard stays in charge).
local function HasController()
    local api = _G["C_GamePad"]
    if type(api) ~= "table" then return false end
    if type(api.IsEnabled) == "function" then
        local ok, enabled = pcall(api.IsEnabled)
        if ok and not enabled then return false end
    end
    if type(api.GetAllDeviceIDs) == "function" then
        local ok, ids = pcall(api.GetAllDeviceIDs)
        if ok and type(ids) == "table" and #ids == 0 then return false end
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

    if InCombatLockdown() then
        if not gamepadPending then
            gamepadPending = true
            FS.PanelSkins.DeferCombat(function()
                gamepadPending = false
                SyncGamepadBagBar()
            end)
        end
        return
    end

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
    elseif gamepadHiddenByUs then
        gamepadHiddenByUs = false
        pcall(bar.Show, bar)
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
local reconEntries = {}
for i = 1, MAX_CONTAINERS do
    reconEntries[#reconEntries + 1] = { name = "ContainerFrame" .. i, guard = "fsBagSkin" }
end
reconEntries[#reconEntries + 1] = { name = "ContainerFrameCombinedBags", guard = "fsBagSkin" }
reconEntries[#reconEntries + 1] = { name = "BankFrame", guard = "fsBagSkin" }
FS.PanelSkins.RegisterRecon("Bags", reconEntries)

FS.PanelSkins.DeferCombat(Apply)
