-- Forever STUwave: Bag Bar
--
-- Our OWN bag slot buttons, seated in FS.Deck.bagSlot (the control deck's right
-- block). Replaces the reparent-and-reskin of Blizzard's bag buttons: we own the
-- look and the seat, Blizzard keeps the behaviour.
--
-- THE CLICK IS DELEGATED, NEVER RUN HERE. Each slot is a SecureActionButtonTemplate
-- button with type="click" and clickbutton = Blizzard's own stock bag button
-- (MainMenuBarBackpackButton, CharacterBag0..3Slot, CharacterReagentBag0Slot,
-- KeyRingButton), so a click runs the stock OnClick (BagSlotOnClick) from the
-- secure path, untainted. This file NEVER calls ToggleBackpack / ToggleBag /
-- ToggleAllBags / OpenBag / CloseBag: those run ContainerFrame_GenerateFrame and
-- the item-button pool under OUR taint, and the first item click afterwards
-- (ContainerFrameItemButton_OnClick -> C_Container.UseContainerItem) threw
-- ADDON_ACTION_FORBIDDEN. The stock buttons are only dimmed (alpha 0, mouse off),
-- never hidden by us. UNVERIFIED in game: that Button:Click still runs the OnClick of
-- a dimmed, mouse-off or hidden button (and passes the secure-delegate access checks).
-- It matters because Blizzard itself hides the stock bags 1-4 when the BagsBar
-- collapses, so the hidden case is common, not an edge.
--
-- Secure means PROTECTED, and so is every ancestor and anchor target: in combat
-- the slot buttons, the bar, the deck's bag slot and the chassis cannot be shown,
-- hidden, resized or moved. Structure (availability, size, seat) is therefore
-- applied out of combat only (Structure) and replayed on PLAYER_REGEN_ENABLED;
-- ApplySlotState only touches regions (textures), which stay legal in combat.
--
-- Slots, left to right: backpack, bags 1-4, the reagent bag when this client
-- has one, the keyring when C_ActionBar.ShouldShowKeyring says so.
--
-- Behaviour is Blizzard's BaseBagSlotButtonMixin (Blizzard_MainMenuBarBagButtons):
--     click           the stock button's OnClick, through the secure click type: a modified
--                     click is OPENALLBAGS (toggle all bags) or nothing, never a toggle; plain
--                     click: cursor holds an item -> put it in that bag, else toggle the bag
--     drop            ours: PutItemInBag / PutItemInBackpack / PutKeyInKeyRing, which are C
--                     functions (no FrameXML definition, unprotected, no container Lua)
--     drag            ours: PickupBagFromSlot (C) for bags 1-4 and reagent; the backpack and
--                     keyring cannot move
--     hover           tooltip above the slot (the deck sits at the screen bottom)
--
-- Look: two-corner cut keycaps (slice_cut2_*, TOP-LEFT and BOTTOM-RIGHT only) on a dark glass plate, a neon edge in the
-- slot's accent (backpack cyan, bags violet, reagent green, keyring amber), the
-- bag's icon inset inside, an LED underline (deck_led.tga): dim normally, bright
-- while the bag is open, pulsing while it is a drop target for a bag on the cursor.
-- Every visual state goes through ApplySlotState.
--
-- Blizzard's own bag bar is hidden (alpha 0 + mouse off, never Hide()), because
-- BagsBar is an Edit Mode system and Hide() on it risks taint. A slot whose stock
-- button does not exist is hidden and logged once; there is no Lua fallback.

local _, FS = ...

if not FS.PanelSkins.RequireExport(FS.Layout, "BagBar.lua disabled: FS.Layout missing") then return end
local Theme = FS.Theme
if not FS.PanelSkins.RequireExport(
    Theme and Theme.AddSliceTexture and Theme.AddCut2Texture and Theme.ApplyNineSlice and Theme.ApplyMono,
    "BagBar.lua disabled: FS.Theme chrome helpers missing") then return end

local IsSecret = FS.IsSecret
local Scale = FS.Layout.Scale

local DEFAULT_SIZE = 26 -- design px; FS.Deck.BAG_SIZE overrides
local DEFAULT_GAP = 4   -- design px; FS.Deck.BAG_GAP overrides

local LED_TEXTURE = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\deck_led.tga"
local BACKPACK_ATLAS = "bag-main" -- what MainMenuBarBackpackMixin:GetSlotAtlases paints
local BACKPACK_ICON = "Interface\\Buttons\\Button-Backpack-Up" -- file fallback, no atlas
local KEYRING_ICON = "Interface\\Icons\\INV_Misc_Key_03"
local EMPTY_BAG_ICON = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Bag"
local ICON_L, ICON_R = 0.08, 0.92

local PLATE = { 0.078, 0.039, 0.141, 0.95 }      -- #140a24
local EDGE_EMPTY = { 0.29, 0.23, 0.455 }         -- #4a3a74, the mockup's empty-slot edge
local SILHOUETTE_TINT = { 0.62, 0.52, 0.9 }
local COLOR_CYAN = Theme.COLOR_POWER or { 0.133, 0.878, 1 }
local COLOR_VIOLET = { 0.627, 0.424, 1 }         -- #a06cff
local COLOR_GREEN = { 0.224, 1, 0.078 }          -- #39ff14
local COLOR_AMBER = { 1, 0.69, 0.13 }
local COLOR_PINK = Theme.COLOR_HEALTH or { 1, 0.18, 0.592 }

-- Cursor items that fit a bag slot: containers and quivers/ammo pouches (both ItemClass 11
-- in Classic). INVTYPE_AMMO is the slot for the ammo itself, not a pouch, so it is left out.
local ITEM_CLASS = Enum and Enum.ItemClass
local CLASS_CONTAINER = (ITEM_CLASS and ITEM_CLASS.Container) or 1
local CLASS_QUIVER = (ITEM_CLASS and ITEM_CLASS.Quiver) or 11
local BAG_EQUIP_LOCS = { INVTYPE_BAG = true, INVTYPE_QUIVER = true }

local PULSE_RATE = 5.2 -- radians per second, about a 1.2s cycle

-------------------------------------------------------------------------------
-- Slot definitions
-------------------------------------------------------------------------------

-- bagID is the container ID; the equipped bag's INVENTORY slot (what the Put/Pickup
-- APIs take) is resolved separately by ResolveInvSlot. binding: Blizzard numbers the
-- bag keybinds from the right (TOGGLEBAG1 is the last bag), so bag N is TOGGLEBAG(5-N).
local function BagID(n, enumName)
    local index = Enum and Enum.BagIndex
    local value = index and index[enumName]
    return type(value) == "number" and value or n
end

local DEFS = {
    { key = "backpack", kind = "backpack", bagID = 0, accent = COLOR_CYAN,
      stock = "MainMenuBarBackpackButton", binding = "TOGGLEBACKPACK" },
    { key = "bag1", kind = "bag", bagID = BagID(1, "Bag_1"), accent = COLOR_VIOLET,
      stock = "CharacterBag0Slot", binding = "TOGGLEBAG4" },
    { key = "bag2", kind = "bag", bagID = BagID(2, "Bag_2"), accent = COLOR_VIOLET,
      stock = "CharacterBag1Slot", binding = "TOGGLEBAG3" },
    { key = "bag3", kind = "bag", bagID = BagID(3, "Bag_3"), accent = COLOR_VIOLET,
      stock = "CharacterBag2Slot", binding = "TOGGLEBAG2" },
    { key = "bag4", kind = "bag", bagID = BagID(4, "Bag_4"), accent = COLOR_VIOLET,
      stock = "CharacterBag3Slot", binding = "TOGGLEBAG1" },
    { key = "reagent", kind = "reagent", bagID = BagID(5, "ReagentBag"), accent = COLOR_GREEN,
      stock = "CharacterReagentBag0Slot", binding = "TOGGLEREAGENTBAG1" },
    { key = "keyring", kind = "keyring", accent = COLOR_AMBER,
      stock = "KeyRingButton", binding = "TOGGLEKEYRING" },
}

local slots = {}        -- every slot, built once at load, in display order
local pulse = 1         -- shared 0..1 phase, driven by pulseDriver while a drop target exists
local pulseT = 0

-------------------------------------------------------------------------------
-- API wrappers (all feature-detected; a missing or secret result reads as nil)
-------------------------------------------------------------------------------

local function Clean(ok, value)
    if not ok or IsSecret(value) then return nil end
    return value
end

local function Call(fn, ...)
    if type(fn) ~= "function" then return nil end
    return Clean(pcall(fn, ...))
end

-- FS.LogDegradeOnce does not dedupe by key, so latch each key here.
local degradeLogged = {}
local function LogDegrade(key, message)
    if degradeLogged[key] then return end
    degradeLogged[key] = true
    if type(FS.LogDegradeOnce) == "function" then FS.LogDegradeOnce(key, message) end
end

-- Paints the backpack: Blizzard's atlas when this client has it, else the file texture.
-- SetAtlas resets the texcoords to the atlas rect, so the ICON_L..ICON_R crop is
-- re-applied inside that rect (a plain SetTexCoord would address the whole sheet).
-- Returns false only when the file texture also reads back nil.
local function ApplyBackpackIcon(icon)
    local info = Call(C_Texture and C_Texture.GetAtlasInfo, BACKPACK_ATLAS)
    if type(info) == "table" then
        icon:SetAtlas(BACKPACK_ATLAS, false)
        local l, r, t, b = info.leftTexCoord, info.rightTexCoord, info.topTexCoord, info.bottomTexCoord
        local function Num(v) return type(v) == "number" and not IsSecret(v) end
        if Num(l) and Num(r) and Num(t) and Num(b) then
            local w, h = r - l, b - t
            icon:SetTexCoord(l + w * ICON_L, l + w * ICON_R, t + h * ICON_L, t + h * ICON_R)
        end
        return true
    end
    icon:SetTexture(BACKPACK_ICON)
    icon:SetTexCoord(ICON_L, ICON_R, ICON_L, ICON_R)
    return icon:GetTexture() ~= nil
end

local function KeyringBagID()
    if type(KEYRING_CONTAINER) == "number" then return KEYRING_CONTAINER end
    local index = Enum and Enum.BagIndex
    return index and index.Keyring
end

-- The inventory slot the equipped bag lives in. C_Container first (what the client
-- itself uses), then the stock button's own ID, then GetInventorySlotInfo.
local function ResolveInvSlot(def)
    if def.kind == "backpack" or def.kind == "keyring" then return nil end
    if C_Container then
        local id = Call(C_Container.ContainerIDToInventoryID, def.bagID)
        if type(id) == "number" then return id end
    end
    local stock = def.stock and _G[def.stock]
    if stock and stock.GetID then
        local id = Clean(pcall(stock.GetID, stock))
        if type(id) == "number" and id > 0 then return id end
    end
    return nil
end

local function KeyringWanted()
    local show = C_ActionBar and C_ActionBar.ShouldShowKeyring
    if type(show) == "function" then
        return Call(show) == true
    end
    return Call(rawget(_G, "IsKeyRingEnabled")) == true
end

local function CursorHoldsItem()
    if type(CursorHasItem) == "function" then
        return Call(CursorHasItem) == true
    end
    if type(GetCursorInfo) == "function" then
        return Call(GetCursorInfo) ~= nil
    end
    return false
end

-- True when the cursor holds a bag-type item (container, quiver or ammo pouch), so the
-- bag slots read as drop targets.
local function CursorHoldsBag()
    if type(GetCursorInfo) ~= "function" then return false end
    local ok, kind, itemID = pcall(GetCursorInfo)
    if not ok or IsSecret(kind) or kind ~= "item" then return false end
    if IsSecret(itemID) or type(itemID) ~= "number" then return false end
    local getInfo = C_Item and C_Item.GetItemInfoInstant
    if type(getInfo) ~= "function" then return false end
    local ok2, _, _, _, equipLoc, _, classID = pcall(getInfo, itemID)
    if not ok2 then return false end
    if not IsSecret(classID) and (classID == CLASS_CONTAINER or classID == CLASS_QUIVER) then
        return true
    end
    return not IsSecret(equipLoc) and type(equipLoc) == "string" and BAG_EQUIP_LOCS[equipLoc] == true
end

local function FreeSlotCount()
    local total = C_Container and C_Container.CalculateTotalNumberOfFreeBagSlots
    if type(total) == "function" then
        local n = Call(total)
        if type(n) == "number" then return n end
    end
    local getFree = C_Container and C_Container.GetContainerNumFreeSlots
    if type(getFree) ~= "function" then return nil end
    local sum = 0
    for bag = 0, 4 do
        local ok, free, bagType = pcall(getFree, bag)
        if ok and not IsSecret(free) and not IsSecret(bagType) and type(free) == "number"
            and (bagType == nil or bagType == 0) then
            sum = sum + free
        end
    end
    return sum
end

-------------------------------------------------------------------------------
-- Containers
-------------------------------------------------------------------------------

local function DeckExport()
    local deck = FS.Deck
    if deck and deck.bagSlot then return deck end
    return nil
end

local bar = CreateFrame("Frame", "ForeverSTUwaveBagBar", (DeckExport() and DeckExport().bagSlot) or UIParent)
local fallbackHost

-- Without the deck, a standalone host bottom-right so the bags are never lost.
local function EnsureFallbackHost()
    if fallbackHost then return fallbackHost end
    LogDegrade("bagbar_nodeck",
        "|cffff4488Forever STUwave|r: FS.Deck missing, bag bar seated bottom-right")
    fallbackHost = CreateFrame("Frame", "ForeverSTUwaveBagBarHost", UIParent)
    fallbackHost:SetFrameStrata("MEDIUM")
    bar:SetParent(fallbackHost)
    return fallbackHost
end

local function HostFrame()
    local deck = DeckExport()
    if deck then
        if fallbackHost then bar:SetParent(deck.bagSlot) end
        return deck.bagSlot
    end
    return EnsureFallbackHost()
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

-- The icon sits inset so its square corners clear the cut corners; pressed nudges
-- it one pixel down-right.
local function PlaceIcon(slot)
    local inset = slot.iconInset or 2
    local off = slot.pressed and 1 or 0
    local stamp = inset * 2 + off
    if slot.placedStamp == stamp then return end
    slot.placedStamp = stamp
    for _, region in ipairs({ slot.icon, slot.silhouette }) do
        region:ClearAllPoints()
        region:SetPoint("TOPLEFT", slot.button, "TOPLEFT", inset + off, -inset - off)
        region:SetPoint("BOTTOMRIGHT", slot.button, "BOTTOMRIGHT", -inset + off, inset - off)
    end
end

local function ApplySlotState(slot)
    local button = slot.button
    if not button then return end
    local accent = slot.accent
    local isBag = slot.kind == "bag" or slot.kind == "reagent"
    local hasItem = slot.hasItem
    local open, hover, pressed, locked, drag = slot.open, slot.hover, slot.pressed, slot.locked, slot.dragTarget

    local er, eg, eb, ea
    if drag then
        er, eg, eb, ea = COLOR_GREEN[1], COLOR_GREEN[2], COLOR_GREEN[3], 0.55 + 0.45 * pulse
    elseif pressed then
        er, eg, eb, ea = COLOR_PINK[1], COLOR_PINK[2], COLOR_PINK[3], 1
    elseif hover or open then
        er, eg, eb, ea = accent[1], accent[2], accent[3], 1
    elseif isBag and not hasItem then
        er, eg, eb, ea = EDGE_EMPTY[1], EDGE_EMPTY[2], EDGE_EMPTY[3], 0.55
    elseif slot.quality and slot.quality >= 2 and slot.qualityColor then
        local qc = slot.qualityColor
        er, eg, eb, ea = qc[1], qc[2], qc[3], 0.85
    else
        er, eg, eb, ea = accent[1], accent[2], accent[3], 0.75
    end
    slot.edge:SetVertexColor(er, eg, eb, ea)

    if hover or open or drag then
        local glowAlpha = drag and (0.35 + 0.5 * pulse) or (hover and 0.9 or 0.5)
        slot.glow:SetVertexColor(er, eg, eb, glowAlpha)
        slot.glow:Show()
    else
        slot.glow:Hide()
    end

    local lr, lg, lb = accent[1], accent[2], accent[3]
    local la
    if drag then
        lr, lg, lb, la = COLOR_GREEN[1], COLOR_GREEN[2], COLOR_GREEN[3], 0.45 + 0.55 * pulse
    elseif open then
        la = 1
    elseif hover then
        la = 0.75
    elseif isBag and not hasItem then
        la = 0.12
    else
        la = 0.3
    end
    slot.led:SetVertexColor(lr, lg, lb, la)

    if hasItem then
        slot.icon:Show()
        slot.icon:SetDesaturated(locked and true or false)
        slot.icon:SetAlpha(locked and 0.5 or 1)
        slot.silhouette:Hide()
    else
        slot.icon:Hide()
        slot.silhouette:Show()
        local tint = drag and COLOR_GREEN or SILHOUETTE_TINT
        slot.silhouette:SetVertexColor(tint[1], tint[2], tint[3], drag and 0.6 or (hover and 0.5 or 0.35))
    end
    if slot.glyph then slot.glyph:SetShown(hasItem and slot.glyphOnly == true) end

    PlaceIcon(slot)
end

-- Reads the equipped bag's icon, quality and lock state into the slot.
local function ReadItem(slot)
    if slot.kind == "backpack" or slot.kind == "keyring" then
        slot.hasItem = true
        return
    end
    local inv = slot.invSlot
    if not inv then
        slot.hasItem, slot.quality, slot.qualityColor = false, nil, nil
        return
    end
    local texture = Call(GetInventoryItemTexture, "player", inv)
    slot.hasItem = texture ~= nil
    if slot.hasItem then
        slot.icon:SetTexture(texture)
        local quality = Call(GetInventoryItemQuality, "player", inv)
        slot.quality = type(quality) == "number" and quality or nil
        local colors = ITEM_QUALITY_COLORS
        local color = slot.quality and colors and colors[slot.quality]
        if color then
            slot.qualityColor = { color.r, color.g, color.b }
        else
            slot.qualityColor = nil
        end
    else
        slot.quality, slot.qualityColor = nil, nil
    end
end

local function ReadLock(slot)
    local inv = slot.invSlot
    slot.locked = inv ~= nil and Call(IsInventoryItemLocked, inv) == true
end

local function ReadOpen(slot)
    local bagID = slot.kind == "keyring" and KeyringBagID() or slot.bagID
    if bagID == nil then slot.open = false return end
    slot.open = Call(IsBagOpen, bagID) == true
end

local function EachActive(fn)
    for _, slot in ipairs(slots) do
        if slot.active then fn(slot) end
    end
end

local function RefreshItems()
    EachActive(function(slot)
        ReadItem(slot)
        ReadLock(slot)
        ApplySlotState(slot)
    end)
end

local function RefreshLocks()
    EachActive(function(slot)
        ReadLock(slot)
        ApplySlotState(slot)
    end)
end

local function RefreshOpen()
    EachActive(function(slot)
        ReadOpen(slot)
        ApplySlotState(slot)
    end)
end

local function RefreshFree()
    local free = FreeSlotCount()
    for _, slot in ipairs(slots) do
        if slot.kind == "backpack" and slot.count then
            slot.free = free
            slot.count:SetText(free and tostring(free) or "")
        end
    end
end

local pulseDriver = CreateFrame("Frame")
pulseDriver:Hide()
pulseDriver:SetScript("OnUpdate", function(_, elapsed)
    pulseT = pulseT + (elapsed or 0)
    pulse = 0.5 + 0.5 * math.sin(pulseT * PULSE_RATE)
    EachActive(function(slot)
        if slot.dragTarget then ApplySlotState(slot) end
    end)
end)

local function RefreshCursor()
    local holdsBag = CursorHoldsBag()
    local any = false
    EachActive(function(slot)
        local target = holdsBag and (slot.kind == "bag" or slot.kind == "reagent") and slot.invSlot ~= nil
        if target then any = true end
        if (slot.dragTarget or false) ~= target then
            slot.dragTarget = target
            ApplySlotState(slot)
        end
    end)
    pulseDriver:SetShown(any)
end

-------------------------------------------------------------------------------
-- Interaction
-------------------------------------------------------------------------------

-- Drop onto a slot: the C put functions only, no container Lua. The CLICK is not here at
-- all: it is the secure delegation to the stock button wired by BindSlot.
local function PutCursorItem(slot)
    if slot.kind == "backpack" then
        if type(PutItemInBackpack) == "function" then PutItemInBackpack() end
    elseif slot.kind == "keyring" then
        if type(PutKeyInKeyRing) == "function" then PutKeyInKeyRing() end
    elseif slot.invSlot and type(PutItemInBag) == "function" then
        PutItemInBag(slot.invSlot)
    end
end

-- Wires the slot's secure click to its stock button: type="click" plus clickbutton makes
-- SECURE_ACTIONS.click call stock:Click(mouseButton), i.e. the stock OnClick
-- (BagSlotOnClick) from the secure path. The click lands on mouse UP regardless of
-- useOnKeyDown: SecureActionButton_OnClick (12.1) treats an engine-dispatched mouse press
-- as a secure mouse press and forces it to the up event, and RegisterForClicks("AnyUp")
-- means no down event is dispatched to the slot at all, so starting a drag never toggles
-- the bag. useOnKeyDown=false is kept as belt and braces: it still governs a key press
-- or an addon-originated :Click(), which would otherwise follow the ActionButtonUseKeyDown
-- CVar. SetAttribute is protected in combat, so this runs out of combat only and a slot
-- stays unbound (inactive, hidden) until it does; a missing stock button leaves it
-- unbound and logs once.
local function BindSlot(slot)
    if slot.bound then return true end
    local stock = slot.stock and _G[slot.stock]
    if type(stock) ~= "table" or type(stock.Click) ~= "function" then
        if not slot.warnedNoStock then
            slot.warnedNoStock = true
            LogDegrade("bagbar_nostock_" .. slot.key,
                "|cffff4488Forever STUwave|r: bag slot " .. slot.key .. " has no stock button ("
                .. tostring(slot.stock) .. "), hidden")
        end
        return false
    end
    if InCombatLockdown() then return false end
    local button = slot.button
    local ok = pcall(function()
        button:SetAttribute("type", "click")
        button:SetAttribute("clickbutton", stock)
        button:SetAttribute("useOnKeyDown", false)
    end)
    if not ok then return false end
    slot.bound = true
    return true
end

local function OnSlotReceiveDrag(slot)
    if CursorHoldsItem() then PutCursorItem(slot) end
end

local function OnSlotDragStart(slot)
    if (slot.kind == "bag" or slot.kind == "reagent") and slot.invSlot
        and type(PickupBagFromSlot) == "function" then
        PickupBagFromSlot(slot.invSlot)
    end
end

local function BindingSuffix(command)
    if not command or type(GetBindingKey) ~= "function" then return "" end
    local key = Call(GetBindingKey, command)
    if type(key) ~= "string" or key == "" then return "" end
    local text = Call(GetBindingText, key)
    if type(text) ~= "string" then text = key end
    return " |cffffd100(" .. text .. ")|r"
end

local function ShowTooltip(slot)
    local tip = GameTooltip
    if not tip then return end
    tip:SetOwner(slot.button, "ANCHOR_NONE")
    tip:ClearAllPoints()
    tip:SetPoint("BOTTOM", slot.button, "TOP", 0, 8)
    local suffix = BindingSuffix(slot.binding)

    if slot.kind == "backpack" then
        tip:SetText((BACKPACK_TOOLTIP or "Backpack") .. suffix, 1, 1, 1)
        local free = FreeSlotCount() or 0
        local line = type(NUM_FREE_SLOTS) == "string" and Clean(pcall(string.format, NUM_FREE_SLOTS, free))
        tip:AddLine(line or (free .. " Free Slots"))
    elseif slot.kind == "keyring" then
        tip:SetText((KEYRING or "Keyring") .. suffix, 1, 1, 1)
    else
        local has = slot.invSlot and Call(tip.SetInventoryItem, tip, "player", slot.invSlot)
        if has then
            if suffix ~= "" and tip.AppendText then pcall(tip.AppendText, tip, suffix) end
        else
            local title = slot.kind == "reagent" and (EQUIP_CONTAINER_REAGENT or EQUIP_CONTAINER)
                or EQUIP_CONTAINER or BAGSLOT or "Bag"
            tip:SetText(title, 1, 1, 1)
        end
    end
    tip:Show()
end

local function HideTooltip(slot)
    local tip = GameTooltip
    if tip and tip.GetOwner and tip:GetOwner() == slot.button then tip:Hide() end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function BuildSlot(def)
    local slot = {
        key = def.key, kind = def.kind, bagID = def.bagID, accent = def.accent,
        binding = def.binding, stock = def.stock, def = def, active = false,
        hasItem = def.kind == "backpack" or def.kind == "keyring",
    }

    -- SecureActionButtonTemplate: its own OnClick runs the secure action (see the file header),
    -- so nothing here may SetScript("OnClick") over it. Mouse UP only, with useOnKeyDown=false
    -- set by BindSlot.
    local button = CreateFrame("Button", "ForeverSTUwaveBagSlot_" .. def.key, bar, "SecureActionButtonTemplate")
    button:RegisterForClicks("AnyUp")
    button:RegisterForDrag("LeftButton")
    slot.button = button

    local fill = Theme.AddCut2Texture(button, Theme.SLICE_CUT2_FILL_TEXTURE, PLATE, "BACKGROUND")
    slot.fill = fill

    slot.silhouette = button:CreateTexture(nil, "ARTWORK", nil, 0)
    slot.silhouette:SetTexture(EMPTY_BAG_ICON)
    slot.silhouette:SetTexCoord(ICON_L, ICON_R, ICON_L, ICON_R)
    slot.silhouette:SetDesaturated(true)

    slot.icon = button:CreateTexture(nil, "ARTWORK", nil, 1)
    slot.icon:SetTexCoord(ICON_L, ICON_R, ICON_L, ICON_R)
    local hasArt = true
    if def.kind == "backpack" then
        hasArt = ApplyBackpackIcon(slot.icon)
    elseif def.kind == "keyring" then
        slot.icon:SetTexture(KEYRING_ICON)
        hasArt = slot.icon:GetTexture() ~= nil
    end
    if not hasArt then
        -- No usable art: fall back to a letter glyph.
        slot.glyphOnly = true
        slot.glyph = button:CreateFontString(nil, "ARTWORK")
        slot.glyph:SetPoint("CENTER", button, "CENTER", 0, 0)
        Theme.ApplyMono(slot.glyph, 12, def.accent)
        slot.glyph:SetText(def.kind == "backpack" and "B" or "K")
    end

    slot.edge = Theme.AddCut2Texture(button, Theme.SLICE_CUT2_OUTLINE_TEXTURE, def.accent, "OVERLAY", 1)

    local glow = button:CreateTexture(nil, "OVERLAY", nil, 0)
    glow:SetTexture(Theme.SLICE_GLOW_TEXTURE)
    Theme.ApplyNineSlice(glow, Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")
    glow:Hide()
    slot.glow = glow

    local led = button:CreateTexture(nil, "OVERLAY", nil, 2)
    led:SetTexture(LED_TEXTURE)
    slot.led = led

    if def.kind == "backpack" then
        slot.count = button:CreateFontString(nil, "OVERLAY")
        Theme.ApplyMono(slot.count, 10, COLOR_CYAN)
    end

    button:SetScript("OnReceiveDrag", function() OnSlotReceiveDrag(slot) end)
    button:SetScript("OnDragStart", function() OnSlotDragStart(slot) end)
    button:SetScript("OnEnter", function()
        slot.hover = true
        ApplySlotState(slot)
        ShowTooltip(slot)
    end)
    button:SetScript("OnLeave", function()
        slot.hover = false
        slot.pressed = false
        ApplySlotState(slot)
        HideTooltip(slot)
    end)
    button:SetScript("OnMouseDown", function()
        slot.pressed = true
        ApplySlotState(slot)
    end)
    button:SetScript("OnMouseUp", function()
        slot.pressed = false
        ApplySlotState(slot)
    end)
    button:SetScript("OnHide", function()
        slot.hover, slot.pressed = false, false
    end)

    return slot
end

for _, def in ipairs(DEFS) do
    slots[#slots + 1] = BuildSlot(def)
end

-- Which slots exist on this client right now. Reagent needs the enum and a
-- resolvable inventory slot; keyring needs ShouldShowKeyring; bags need their
-- inventory slot (a bag whose slot cannot be found is hidden, not left dead).
-- Every slot also needs its stock button bound (BindSlot): without one there is no click
-- to delegate, so it is hidden and logged once rather than falling back to Lua toggles.
-- Shows and hides the protected slot buttons: out of combat only (see Structure).
local function RefreshAvailability()
    for _, slot in ipairs(slots) do
        local active
        if slot.kind == "backpack" then
            active = true
        elseif slot.kind == "keyring" then
            active = KeyringWanted() and KeyringBagID() ~= nil
        else
            slot.invSlot = slot.invSlot or ResolveInvSlot(slot.def)
            active = slot.invSlot ~= nil
            if slot.kind == "reagent" then
                active = active and Enum ~= nil and Enum.BagIndex ~= nil and Enum.BagIndex.ReagentBag ~= nil
            elseif not active and not slot.warnedNoInv then
                slot.warnedNoInv = true
                LogDegrade("bagbar_noinv_" .. slot.key,
                    "|cffff4488Forever STUwave|r: bag slot " .. slot.key .. " has no inventory slot, hidden")
            end
        end
        if active and not BindSlot(slot) then active = false end
        slot.active = active and true or false
        slot.button:SetShown(slot.active)
        if not slot.active then
            slot.dragTarget, slot.hover, slot.pressed = false, false, false
        end
    end
end

local function SizeSlot(slot, size, scale)
    local button = slot.button
    button:SetSize(size, size)

    -- Cut corners are drawn at the texture's own pixel size, so the icon must clear
    -- half the chamfer on each axis for its square corners not to poke out.
    local chamfer = Theme.SLICE_CUT_MARGIN or 6
    slot.iconInset = math.max(2 * scale, chamfer * 0.5 + 0.5)

    local pad = Theme.SLICE_GLOW_PAD or 4
    slot.glow:ClearAllPoints()
    slot.glow:SetPoint("TOPLEFT", button, "TOPLEFT", -pad, pad)
    slot.glow:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", pad, -pad)

    local ledW = size * 0.7
    slot.led:ClearAllPoints()
    slot.led:SetSize(ledW, ledW / 4)
    slot.led:SetPoint("BOTTOM", button, "BOTTOM", 0, 1.5 * scale)

    if slot.count then
        slot.count:ClearAllPoints()
        slot.count:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -4 * scale, 5 * scale)
        Theme.ApplyMono(slot.count, math.max(8, math.floor(10 * scale + 0.5)), COLOR_CYAN)
    end
end

local function LayoutSlots()
    local deck = FS.Deck
    local scale = Scale()
    local size = ((deck and deck.BAG_SIZE) or DEFAULT_SIZE) * scale
    local gap = ((deck and deck.BAG_GAP) or DEFAULT_GAP) * scale

    local host = HostFrame()
    if host == fallbackHost then
        host:ClearAllPoints()
        host:SetPoint("BOTTOMRIGHT", UIParent, "BOTTOMRIGHT", -8 * scale, 8 * scale)
        host:SetSize((7 * DEFAULT_SIZE + 6 * DEFAULT_GAP) * scale, DEFAULT_SIZE * scale)
    end

    local count = 0
    for _, slot in ipairs(slots) do
        if slot.active then count = count + 1 end
    end
    bar:ClearAllPoints()
    bar:SetPoint("CENTER", host, "CENTER", 0, 0)
    bar:SetSize(math.max(count * size + math.max(count - 1, 0) * gap, 1), size)

    local index = 0
    for _, slot in ipairs(slots) do
        SizeSlot(slot, size, scale)
        if slot.active then
            slot.button:ClearAllPoints()
            slot.button:SetPoint("LEFT", bar, "LEFT", index * (size + gap), 0)
            index = index + 1
        end
    end
end

-------------------------------------------------------------------------------
-- Blizzard's bar: dimmed, never Hide()
-------------------------------------------------------------------------------

local BLIZZARD_FRAMES = { "BagsBar", "MicroButtonAndBagsBar" }
local BLIZZARD_BUTTONS = {
    "MainMenuBarBackpackButton", "CharacterBag0Slot", "CharacterBag1Slot",
    "CharacterBag2Slot", "CharacterBag3Slot", "CharacterReagentBag0Slot",
    "KeyRingButton", "BagBarExpandToggle",
}

local dimmed = {}            -- frame -> true once hooked
local pendingMouseSweep = false

local function DimFrame(frame)
    if frame.SetAlpha then frame:SetAlpha(0) end
    if frame.EnableMouse then
        if InCombatLockdown() then
            pendingMouseSweep = true
        else
            pcall(frame.EnableMouse, frame, false)
        end
    end
end

local function HookDim(frame)
    if dimmed[frame] then return end
    dimmed[frame] = true
    if frame.HookScript then
        pcall(frame.HookScript, frame, "OnShow", DimFrame)
    end
    -- Blizzard fades/re-lays these out and may SetAlpha(1); keep asserting 0.
    if type(hooksecurefunc) == "function" and frame.SetAlpha then
        local busy = false
        pcall(hooksecurefunc, frame, "SetAlpha", function(self, alpha)
            if busy or alpha == 0 then return end
            busy = true
            self:SetAlpha(0)
            busy = false
        end)
    end
end

local function HideBlizzardBar()
    pendingMouseSweep = false
    for _, list in ipairs({ BLIZZARD_FRAMES, BLIZZARD_BUTTONS }) do
        for _, name in ipairs(list) do
            local frame = _G[name]
            if frame then
                DimFrame(frame)
                HookDim(frame)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Open state
-------------------------------------------------------------------------------

-- Callback from EventRegistry's ContainerFrame.OpenBag/CloseBag (Blizzard runs these
-- through securecallfunction, so our code does not taint its container logic). The
-- frame's own IsShown is accurate at callback time, so light the matching slots at
-- once and reconcile against IsBagOpen on the next tick.
local function OnContainerToggled(_, frame)
    if type(frame) == "table" and frame.MatchesBagID and frame.IsShown then
        local shown = Clean(pcall(frame.IsShown, frame)) and true or false
        EachActive(function(slot)
            local bagID = slot.kind == "keyring" and KeyringBagID() or slot.bagID
            if bagID ~= nil and Call(frame.MatchesBagID, frame, bagID) == true then
                slot.open = shown
                ApplySlotState(slot)
            end
        end)
    end
    if C_Timer and C_Timer.After then C_Timer.After(0, RefreshOpen) end
end

local function InstallOpenTracking()
    if type(EventRegistry) == "table" and EventRegistry.RegisterCallback then
        local owner = {}
        pcall(EventRegistry.RegisterCallback, EventRegistry, "ContainerFrame.OpenBag", OnContainerToggled, owner)
        pcall(EventRegistry.RegisterCallback, EventRegistry, "ContainerFrame.CloseBag", OnContainerToggled, owner)
        return
    end
    -- No EventRegistry: hook the container frames' own show/hide.
    local names = { "ContainerFrameCombinedBags" }
    for i = 1, (type(NUM_CONTAINER_FRAMES) == "number" and NUM_CONTAINER_FRAMES or 13) do
        names[#names + 1] = "ContainerFrame" .. i
    end
    for _, name in ipairs(names) do
        local frame = _G[name]
        if frame and frame.HookScript then
            local function Defer()
                if C_Timer and C_Timer.After then C_Timer.After(0, RefreshOpen) else RefreshOpen() end
            end
            pcall(frame.HookScript, frame, "OnShow", Defer)
            pcall(frame.HookScript, frame, "OnHide", Defer)
        end
    end
end

-------------------------------------------------------------------------------
-- Wiring
-------------------------------------------------------------------------------

-- The structural half: which slots exist (Show/Hide on the protected buttons), their binding
-- (SetAttribute) and their size and seat (SetSize/SetPoint on the buttons, the bar and, with no
-- deck, the fallback host). All of it is restricted in combat, so it waits for
-- PLAYER_REGEN_ENABLED (pendingStructure) and meanwhile the slots keep their last seat.
-- Everything else a refresh does is a texture or FontString write and runs in combat.
local pendingStructure = false
local function Structure()
    if InCombatLockdown() then
        pendingStructure = true
        return false
    end
    pendingStructure = false
    RefreshAvailability()
    LayoutSlots()
    return true
end

local function RefreshAll()
    Structure()
    RefreshItems()
    RefreshOpen()
    RefreshFree()
    RefreshCursor()
end

local events = CreateFrame("Frame")
local EVENT_HANDLERS = {
    PLAYER_ENTERING_WORLD = function() RefreshAll() HideBlizzardBar() end,
    BAG_UPDATE = RefreshFree,
    BAG_UPDATE_DELAYED = function() RefreshItems() RefreshFree() end,
    BAG_CONTAINER_UPDATE = function() Structure() RefreshItems() end,
    PLAYER_EQUIPMENT_CHANGED = RefreshItems,
    ITEM_LOCK_CHANGED = RefreshLocks,
    CURSOR_CHANGED = RefreshCursor,
    BAG_OPEN = RefreshOpen,
    BAG_CLOSED = RefreshOpen,
    PLAYER_REGEN_ENABLED = function()
        if pendingMouseSweep then HideBlizzardBar() end
        if pendingStructure then
            Structure()
            RefreshItems()
            RefreshOpen()
            RefreshCursor()
        end
    end,
}
for event in pairs(EVENT_HANDLERS) do
    pcall(events.RegisterEvent, events, event)
end
events:SetScript("OnEvent", function(_, event, ...)
    local handler = EVENT_HANDLERS[event]
    if handler then handler(...) end
end)

FS.Layout.OnRescale(function()
    Structure()
    EachActive(ApplySlotState)
end)

InstallOpenTracking()
HideBlizzardBar()
RefreshAll()

FS.BagBar = {
    bar = bar,
    slots = slots,
    Refresh = RefreshAll,
    Structure = Structure,
    ApplySlotState = ApplySlotState,
    HideBlizzardBar = HideBlizzardBar,
}
