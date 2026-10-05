-- Forever STUwave: Buffs
-- PLAYER buff/debuff/weapon-enchant display. Two containers (buffs, debuffs) of
-- engine-drawn auras: an AuraContainer per block, unit "player", HELPFUL and HARMFUL,
-- so the engine reads and draws the auras and no aura data ever enters addon Lua.
-- That is what makes the row work IN COMBAT, where every addon aura read is refused
-- and the old pooled row froze or emptied (Parker, 2026-10-04: "not being able to see
-- your buffs in combat sucks"). The look is the approved cut-corner tile, built in
-- each group's initializeFrame (see BuildFace).
--
-- Two other pieces ride along:
--  * A plain-value SNAPSHOT of the player's auras, read OUT of combat (when
--    FS.AurasReadable() says so), refreshed on UNIT_AURA, frozen once lockdown starts
--    and refreshed again at PLAYER_REGEN_ENABLED. Exported as FS.PlayerAuras for any
--    logic that needs readable data. Nothing in combat reads, compares or truth-tests
--    an aura value.
--  * The OLD custom row (plain frames + Theme chrome, drawn from that snapshot) as the
--    fallback when AuraContainer is missing or fails to build, logged once through
--    FS.LogDegradeOnce.
--
-- Weapon enchants are the container's own item enchantments (placed after the aura
-- groups, on a new line) when the client has them; otherwise the old polled enchant
-- buttons are kept. BuffFrame/DebuffFrame/TemporaryEnchantFrame are dimmed, not hidden.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local ApplyMono = FS.Theme.ApplyMono
local SkinButton = FS.Theme.SkinButton
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE
local DimBlizzardFrame = FS.FrameHelpers.DimBlizzardFrame
local SetAuraLabel = FS.FrameHelpers.SetAuraLabel

-- Component-specific logic color, not a canonical design token (mirrors how
-- UnitFrames.lua keeps its reaction/caret colors local rather than in Theme).
local COLOR_BORDER_EXPIRING = { 0.925, 0.286, 0.600, 1 } -- #EC4899

-- The dark plate behind a count / duration label: FrameHelpers' LABEL_PLATE
-- (the action button keybind plate, rgba(6,3,18,.78)), which is file-local there.
local COLOR_LABEL_PLATE = { 0.024, 0.012, 0.071, 0.78 }

-------------------------------------------------------------------------------
-- Layout constants
-------------------------------------------------------------------------------

local ICON_SIZE = 32
local ICON_SPACING = 4
-- Chamfer 4 rather than the 6 CutSizeIcon picks for 32: the icon inset is ceil(c / 2), so
-- the icon fills 28 of 32 units (26 at c = 6) and the tile reads as a filled icon.
local TILE_CHAMFER = 4
local COUNT_FONT_SIZE = 10
local DURATION_FONT_SIZE = 9
-- Row widths come from the mockup's own `cols` per section (layout-v2.json):
-- the buff block is 10 wide, the debuff block 8. They are separate blocks with
-- separate anchors there, so they get separate counts here too.
local BUFF_COLS = 10
local DEBUFF_COLS = 8
-- A flow line is `cols` tiles each followed by its spacing. One unit of slack on top keeps the
-- last tile on the line whichever way the engine compares line length to the maximum (strict or
-- not is unverifiable) and however a float lands on that edge, while one more tile still cannot
-- fit: the line wraps at the same tile count as the old row.
local LINE_SLACK = 1

-- Used only when FS.Layout.buffs is unavailable (see ApplyContainerLayout).
-- Clears the minimap's default top-right footprint (FS.Layout.minimap,
-- Theme.lua) instead of the previous -20,-20 corner anchor, which overlapped
-- it. TUNE: Parker may want this adjusted once FS.Layout.buffs is verified
-- in-game.
local FALLBACK_ANCHOR_X = -20
local FALLBACK_ANCHOR_Y = -280
local FALLBACK_WIDTH = 200
local FALLBACK_HEIGHT = 200

local MAX_BUFF_SLOTS = 32
local MAX_DEBUFF_SLOTS = 16

local EXPIRING_THRESHOLD = 120 -- seconds remaining before the duration text tints pink
local REFRESH_THROTTLE = 0.5   -- seconds between tint/weapon-enchant polls (legacy paths only)

local UNIT = "player"
local FILTER_BUFFS = "HELPFUL"
local FILTER_DEBUFFS = "HARMFUL"

-- Engine containers
local AURA_CONTAINER_TEMPLATE = "CustomAuraContainerTemplate"
local FLOW_LEFT = -1 -- AnchorUtil.FlowDirection.Left / .Down when the table is missing
local FLOW_DOWN = -1
local CANCEL_ON_UP = "RightButtonUp"
local CANCEL_ON_DOWN = "RightButtonDown"
local TOOLTIP_ANCHOR = "ANCHOR_TOPLEFT"
local GROUP_BUFFS = "buffs"
local GROUP_DEBUFF_PREFIX = "debuff_"
local GROUP_DEBUFF_OTHER = "debuff_other"
-- The debuff row is one HARMFUL group per dispel type plus one for everything else, so each
-- group's border colour is baked into its initializeFrame (never retinted, never read from
-- aura data). The groups partition every dispel name.
local DEBUFF_DISPEL_TYPES = { "Magic", "Curse", "Disease", "Poison" }
-- Ring colour per dispel type comes from FS.Theme.DISPEL_COLORS (the DebuffTypeColor global does
-- not exist on 16001, so there is nothing to read it from), baked into each group. Anything
-- else (no dispel type, Bleed, Enrage) keeps the violet ring the row has always worn here.

-------------------------------------------------------------------------------
-- Feature detection (module scope, checked once)
-------------------------------------------------------------------------------

local HAS_WEAPON_ENCHANT = type(GetWeaponEnchantInfo) == "function"

-- Tooltip setters (mirrors PartyFrames.lua's own aura-tooltip feature detection).
local HAS_TOOLTIP_SETINVENTORYITEM = type(GameTooltip) == "table" and type(GameTooltip.SetInventoryItem) == "function"

-------------------------------------------------------------------------------
-- Module state
-------------------------------------------------------------------------------

local container
local debuffContainer
local buffPool, debuffPool, enchantPool = {}, {}, {}
local activeBuffCount, activeDebuffCount, activeEnchantCount = 0, 0, 0

-- One table for the engine-display state, so the file stays well under Lua's local limit.
--   engine          the engine containers are live (FS.buffsAuraContainer / FS.debuffsAuraContainer)
--   nativeMainHand  the buff container carries the main hand enchantment itself
--   nativeOffHand   the same for the off hand (a failure part way can leave one of the two)
--   legacyEnchants  the polled enchant buttons draw the slots that are not native
--   warned          the fallback was logged (LogDegradeOnce does not dedupe)
--   enchantWarned   the native enchantment failure was logged (same reason)
--   durationColor   the duration text colour option: nil = not built yet, false = unavailable
--   parked          containers a failed build left behind (a frame cannot be destroyed)
local state = {
    engine = false, nativeMainHand = false, nativeOffHand = false, legacyEnchants = false,
    warned = false, enchantWarned = false, parked = {},
}

-- The out-of-combat snapshot (plain values only, see RefreshSnapshot).
local snapshot = { buffs = {}, debuffs = {} }
local readFailed = false

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- Prints a failure message once per label instead of once per aura/tick, so an
-- API mismatch is visible in chat without spamming it every 0.5s. Shared
-- plumbing lives in FrameHelpers.lua (FS.FrameHelpers.NewStepRunner) -- Buffs
-- only needs the ReportOnce half, not the RunStep half (this file has no
-- TryStep-style pcall wrapper).
local _, ReportOnce = FS.FrameHelpers.NewStepRunner(function(label)
    return "ForeverSTUwave buffs: " .. label
end)

-- RegisterUnitEvent throws on an event name the client doesn't recognize;
-- pcall-guarded so a missing event can't stop the rest of init. Shared
-- plumbing lives in FrameHelpers.lua (FS.FrameHelpers.SafeRegisterUnitEvent).
local function ReportRegisterFailure(event, err)
    ReportOnce("register " .. event, err)
end

local function SafeRegisterUnitEvent(events, event, unit)
    FS.FrameHelpers.SafeRegisterUnitEvent(events, event, unit, ReportRegisterFailure)
end

-- obj:method(...) when the method exists, any error swallowed. True unless the
-- method existed and threw (a missing method is not a failure), so one refusing
-- setter never stops the next call. Same idiom as Nameplates.lua's nameplate row.
local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

-- True while the player is in combat by either test: UnitAffectingCombat flips a beat before
-- lockdown starts. A missing, throwing or secret answer reads as "not in combat" (this only
-- decides whether to SKIP a scan; the FS.AurasReadable gate still guards every read).
local function InCombatNow()
    local ok, locked = pcall(InCombatLockdown)
    if ok and not FS.IsSecret(locked) and locked then return true end
    if type(UnitAffectingCombat) ~= "function" then return false end
    local okAffecting, affecting = pcall(UnitAffectingCombat, UNIT)
    return okAffecting and not FS.IsSecret(affecting) and affecting == true
end

-- Recolors a SkinButton border: flat color textures (top/bottom/left/right,
-- tagged region.fsFlat = true by Theme.SkinButton) take SetColorTexture, the
-- corner arc file textures (fsFlat falsy) take SetVertexColor. `pairs` covers
-- both the string-keyed edges and the numeric-keyed corner arcs
-- Theme.SkinButton appends to the same table. (Legacy row only.)
local function TintAuraBorder(skin, color)
    if not skin or not skin.border then return end
    local r, g, b, a = color[1], color[2], color[3], color[4] or 1
    for _, region in pairs(skin.border) do
        if region.fsFlat then
            region:SetColorTexture(r, g, b, a)
        else
            region:SetVertexColor(r, g, b, a)
        end
    end
end

-- Renders a remaining-duration timer as a short label instead of a raw
-- seconds count (e.g. "2889"), which was illegible at the icon's small font
-- size. Thresholds and letter suffixes per the layout brief: hours above an
-- hour, minutes above a minute, seconds at or under a minute. (Legacy row only:
-- the engine formats its own duration text.)
local function FormatDuration(remaining)
    if remaining > 3600 then
        return string.format("%dh", math.floor(remaining / 3600))
    elseif remaining > 60 then
        return string.format("%dm", math.floor(remaining / 60))
    else
        return string.format("%ds", math.floor(remaining))
    end
end

-------------------------------------------------------------------------------
-- Out-of-combat snapshot (plain values only)
-------------------------------------------------------------------------------

-- Aura reads are REFUSED under combat lockdown (and may hand back secret fields even
-- outside it), so this is the only place the row's data is ever read: out of combat,
-- gated on FS.AurasReadable(), every field cleaned to a plain value before it is stored.
-- A secret string is stored as nil and a secret number as 0, never compared or kept.
-- The snapshot freezes at lockdown by simply not being refreshed: the one extra read at
-- PLAYER_REGEN_DISABLED lands in the instant before lockdown (readable, see Theme.lua).

local function ReportReadFailure(label, err)
    readFailed = true
    ReportOnce(label, err)
end

local function CleanText(v)
    if FS.IsSecret(v) then return nil end
    if type(v) == "string" then return v end
    return nil
end

local function CleanIcon(v)
    if FS.IsSecret(v) then return nil end
    if type(v) == "string" or type(v) == "number" then return v end
    return nil
end

local function CleanNumber(v)
    if FS.IsSecret(v) then return 0 end
    if type(v) == "number" then return v end
    return 0
end

-- The list for one filter, or nil when a read failed (the caller then keeps the old list:
-- a throwing read looks like an end of list, and must not empty the display).
local function ScanAuras(filter, maxSlots)
    local list = {}
    readFailed = false
    for slot = 1, maxSlots do
        local data = FS.FrameHelpers.ReadAuraSlot(UNIT, slot, filter, ReportReadFailure)
        if not data then break end
        list[#list + 1] = {
            name = CleanText(data.name),
            icon = CleanIcon(data.icon),
            count = CleanNumber(data.count),
            dispelType = CleanText(data.dispelType),
            duration = CleanNumber(data.duration),
            expirationTime = CleanNumber(data.expirationTime),
        }
    end
    if readFailed then return nil end
    return list
end

-- True when a list was replaced. Does nothing (and reads nothing) while auras are secret.
local function RefreshSnapshot()
    if not FS.AurasReadable() then return false end
    local changed = false
    local buffs = ScanAuras(FILTER_BUFFS, MAX_BUFF_SLOTS)
    if buffs then
        snapshot.buffs = buffs
        changed = true
    end
    local debuffs = ScanAuras(FILTER_DEBUFFS, MAX_DEBUFF_SLOTS)
    if debuffs then
        snapshot.debuffs = debuffs
        changed = true
    end
    return changed
end

-- Rows the buff block uses, from the last readable snapshot: where the legacy enchant
-- buttons start below it.
local function SnapshotBuffRows()
    return math.ceil(#snapshot.buffs / BUFF_COLS)
end

FS.PlayerAuras = {
    -- { buffs = { {name, icon, count, dispelType, duration, expirationTime}, ... }, debuffs = ... }
    -- Plain values only, in aura slot order. Read-only by convention; replaced, never mutated.
    Get = function() return snapshot end,
    -- True while the snapshot cannot refresh (auras are secret): what it holds is as of
    -- the last readable moment.
    IsFrozen = function() return not FS.AurasReadable() end,
    -- True when the engine containers draw the row (false: the legacy row is drawn).
    IsEngineDrawn = function() return state.engine end,
}

-------------------------------------------------------------------------------
-- Engine-drawn tiles (AuraContainer buttons)
-------------------------------------------------------------------------------

-- The engine writes display fields onto its button (button.icon is an engine field), so the
-- tile is built on a plain child "face" frame: the cut-corner chrome, icon, count and duration
-- live there, and the engine is handed the face's own icon and fonts. The button keeps its
-- mouse, so the engine's tooltip and right-click cancel work.

-- Own count/duration label with a dark plate hugging the text. The engine writes these texts, so
-- there is no show/hide step: the plate has no horizontal padding and collapses to nothing while
-- its label is empty (FrameHelpers.SeatAuraTile's plates are hidden until Lua gives the label text).
local function SeatFaceLabel(face, fontString, anchor, x, y)
    fontString:ClearAllPoints()
    fontString:SetPoint(anchor, face.icon, anchor, x, y)
    fontString:SetDrawLayer("OVERLAY", 4)
    local plate = face:CreateTexture(nil, "OVERLAY", nil, 3)
    plate:SetColorTexture(COLOR_LABEL_PLATE[1], COLOR_LABEL_PLATE[2], COLOR_LABEL_PLATE[3], COLOR_LABEL_PLATE[4])
    plate:SetPoint("TOPLEFT", fontString, "TOPLEFT", 0, 0)
    plate:SetPoint("BOTTOMRIGHT", fontString, "BOTTOMRIGHT", 0, 0)
    fontString.fsPlate = plate
end

-- Pink under two minutes, white above: a Step colour curve on the remaining duration, built
-- once and shared. nil when the client has no colour curve API (the text then stays white).
local function GetDurationTextColor()
    if state.durationColor ~= nil then return state.durationColor or nil end
    state.durationColor = false
    local hasApi = type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateColorCurve) == "function"
        and type(CreateColor) == "function" and type(Enum) == "table"
        and type(Enum.LuaCurveType) == "table" and type(Enum.DurationTextBindingProperty) == "table"
    if not hasApi then return nil end
    local ok, option = pcall(function()
        local curve = C_CurveUtil.CreateColorCurve()
        curve:SetType(Enum.LuaCurveType.Step)
        curve:AddPoint(0, CreateColor(COLOR_BORDER_EXPIRING[1], COLOR_BORDER_EXPIRING[2], COLOR_BORDER_EXPIRING[3], 1))
        curve:AddPoint(EXPIRING_THRESHOLD,
            CreateColor(COLOR_TEXT_WHITE[1], COLOR_TEXT_WHITE[2], COLOR_TEXT_WHITE[3], 1))
        return { curve = curve, property = Enum.DurationTextBindingProperty.RemainingDuration }
    end)
    if ok then
        state.durationColor = option
        return option
    end
    ReportOnce("duration colour curve", option)
    return nil
end

-- Hands the duration FontString to the engine with the tint option; an engine that refuses the
-- option gets the plain text instead.
local function BindDurationText(button, fontString)
    local color = GetDurationTextColor()
    if color and Quiet(button, "SetDurationText", fontString, { textColor = color }) then return end
    Quiet(button, "SetDurationText", fontString, {})
end

-- Right click cancels on key release, or on key press when the client binds actions on key down
-- (the ActionButtonUseKeyDown CVar, the same switch the action buttons follow). The mechanism
-- differs on purpose: an action button registers AnyUp and AnyDown and lets the secure click
-- handler pick the edge from the CVar, while the engine's aura button takes the edge as ONE token
-- (registering both would cancel on both edges). Read when the button is built, so a CVar change
-- reaches buttons the engine builds afterwards, not the ones already on screen.
local function CancelAuraToken()
    local get = (type(C_CVar) == "table" and C_CVar.GetCVarBool) or GetCVarBool
    if type(get) == "function" then
        local ok, down = pcall(get, "ActionButtonUseKeyDown")
        if ok and down == true then return CANCEL_ON_DOWN end
    end
    return CANCEL_ON_UP
end

-- The face: cut-corner ring in `borderColor`, plate and inset cropped icon (SeatAuraTile), and
-- the two label plates. Raises on a failure it cannot work around; the caller pcalls it.
local function BuildFace(button, borderColor)
    local face = CreateFrame("Frame", nil, button)
    face:SetAllPoints(button)
    Quiet(face, "EnableMouse", false)

    local icon = face:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(face)
    face.icon = icon

    local okSkin, errSkin = pcall(SkinButton, face, { borderColor = borderColor, chamfer = TILE_CHAMFER })
    if not okSkin then ReportOnce("skin aura tile", errSkin) end
    -- Before count/duration exist on the face: SeatAuraTile would add its own show/hide plates,
    -- which never show here because the engine writes the text.
    local okSeat, errSeat = pcall(FS.FrameHelpers.SeatAuraTile, face)
    if not okSeat then ReportOnce("seat aura tile", errSeat) end

    local count = face:CreateFontString(nil, "OVERLAY")
    ApplyMono(count, COUNT_FONT_SIZE)
    SeatFaceLabel(face, count, "TOPRIGHT", -3, -1)
    face.count = count

    local duration = face:CreateFontString(nil, "OVERLAY")
    ApplyMono(duration, DURATION_FONT_SIZE)
    SeatFaceLabel(face, duration, "BOTTOMRIGHT", -3, 1)
    face.duration = duration

    return face
end

-- initializeFrame body. Runs when the engine builds a button, before it turns restricted, so all
-- the setup is here, each step on its own so a missing or throwing method never stops the next.
-- The button's mouse is left on: the engine's tooltip and right-click cancel need it.
local function InitEngineButton(button, borderColor)
    Quiet(button, "SetSize", ICON_SIZE, ICON_SIZE)

    local okFace, face = pcall(BuildFace, button, borderColor)
    if okFace then
        Quiet(button, "SetIcon", face.icon)
        Quiet(button, "SetApplicationCount", face.count)
        BindDurationText(button, face.duration)
    else
        ReportOnce("build aura tile", face)
    end

    Quiet(button, "SetCancelAuraButtons", CancelAuraToken())
    Quiet(button, "SetTooltipAnchorPoint", TOOLTIP_ANCHOR)
end

-- Border colour table for a dispel type; violet for anything without a baked colour.
local function DispelBorderColor(dispelType)
    return FS.Theme.DISPEL_COLORS[dispelType] or COLOR_BORDER
end

-- Even 4 unit gaps everywhere: elementSpacing and lineSpacing are the gaps, and the two group
-- spacings add nothing on top of them, so a group boundary looks like any other gap.
-- UNVERIFIED in game (the flow layout is engine code): if a boundary shows a doubled or a missing
-- gap, these two are the knobs.
local function NewGroupLayout()
    return {
        elementSpacing = ICON_SPACING,
        lineSpacing = ICON_SPACING,
        groupSpacing = 0,
        groupLineSpacing = 0,
        elementWidth = ICON_SIZE,
        elementHeight = ICON_SIZE,
    }
end

local function AddGroup(auras, name, filter, maxCount, candidateFilters, borderColor)
    local sortMethod = type(AuraContainerSortMethod) == "table" and AuraContainerSortMethod.Default or nil
    local sortDirection = type(AuraContainerSortDirection) == "table" and AuraContainerSortDirection.Normal or nil
    auras:AddAuraGroup(name, filter, {
        maxFrameCount = maxCount,
        sortMethod = sortMethod,
        sortDirection = sortDirection,
        candidateFilters = candidateFilters,
        initializeFrame = function(button) InitEngineButton(button, borderColor) end,
        layout = NewGroupLayout(),
    })
end

-- Weapon enchants as the container's own item enchantments, after the aura groups, on a new line
-- (where the legacy enchant buttons sat). False when the client has no such API. Raises on a
-- failure; the caller contains it. The layout goes first, so a failure there adds nothing.
local function AddNativeEnchants(auras)
    if type(auras.AddItemEnchantment) ~= "function" or type(auras.SetItemEnchantmentLayout) ~= "function"
        or type(AuraContainerItemEnchantmentSlot) ~= "table" then
        return false
    end
    local layout = NewGroupLayout()
    if type(CustomAuraContainerItemEnchantmentPlacement) == "table" then
        layout.placement = CustomAuraContainerItemEnchantmentPlacement.AfterAuraGroups
    end
    layout.forceNewLine = true
    auras:SetItemEnchantmentLayout(layout)
    local options = { initializeFrame = function(button) InitEngineButton(button, COLOR_BORDER) end }
    -- Each slot is marked native the moment the engine has it, so a failure part way leaves
    -- exactly the slots that did not get in to the polled buttons (no duplicate, no gap).
    auras:AddItemEnchantment(AuraContainerItemEnchantmentSlot.MainHand, options)
    state.nativeMainHand = true
    auras:AddItemEnchantment(AuraContainerItemEnchantmentSlot.OffHand, options)
    state.nativeOffHand = true
    return true
end

-- The enchantments are an extra: a failure here must not cost the buffs and debuffs the engine
-- path. Logged once. The slots the engine did not take stay with the polled enchant buttons.
local function TryAddNativeEnchants(auras)
    state.nativeMainHand, state.nativeOffHand = false, false
    local ok, err = pcall(AddNativeEnchants, auras)
    if ok then return end
    if not state.enchantWarned then
        state.enchantWarned = true
        FS.LogDegradeOnce("buffs_native_enchants",
            "|cffff4488Forever STUwave|r: weapon enchant icons are not engine drawn ("
            .. tostring(err) .. ")")
    end
end

-- One container for `holder`: unit "player", anchored to the holder's top right, flowing left
-- then down, wrapping after `cols` tiles. Built disabled and hidden; the caller enables it.
local function NewAuraContainer(holder, cols, created)
    local auras = CreateFrame("AuraContainer", nil, holder, AURA_CONTAINER_TEMPLATE)
    created[#created + 1] = auras
    local flow = type(AnchorUtil) == "table" and AnchorUtil.FlowDirection or nil
    auras:SetSize(1, 1)
    auras:SetPoint("TOPRIGHT", holder, "TOPRIGHT", 0, 0)
    auras:SetFlowLayoutAnchorPoint("TOPRIGHT")
    auras:SetFlowLayoutGrowthDirection((flow and flow.Left) or FLOW_LEFT, (flow and flow.Down) or FLOW_DOWN)
    Quiet(auras, "SetFlowLayoutMaximumLineSize", cols * (ICON_SIZE + ICON_SPACING) + LINE_SLACK)
    return auras
end

-- Builds both containers and starts them. Returns the pair, or nil and the error, with every
-- frame that was created parked (disabled, hidden) so a half-built one never draws.
local function BuildEngineContainers()
    local info = type(C_XMLUtil) == "table" and C_XMLUtil.GetTemplateInfo or nil
    local okInfo, template = false, nil
    if type(info) == "function" then okInfo, template = pcall(info, AURA_CONTAINER_TEMPLATE) end
    if not okInfo or not template then return nil, "the " .. AURA_CONTAINER_TEMPLATE .. " template is missing" end

    local created = {}
    local ok, buffs, debuffs = pcall(function()
        local b = NewAuraContainer(container, BUFF_COLS, created)
        AddGroup(b, GROUP_BUFFS, FILTER_BUFFS, MAX_BUFF_SLOTS, nil, COLOR_BORDER)
        TryAddNativeEnchants(b)

        local d = NewAuraContainer(debuffContainer, DEBUFF_COLS, created)
        local excluded = {}
        for _, dispel in ipairs(DEBUFF_DISPEL_TYPES) do
            excluded[dispel] = true
            AddGroup(d, GROUP_DEBUFF_PREFIX .. dispel, FILTER_DEBUFFS, MAX_DEBUFF_SLOTS,
                { includeDispelTypes = { [dispel] = true } }, DispelBorderColor(dispel))
        end
        AddGroup(d, GROUP_DEBUFF_OTHER, FILTER_DEBUFFS, MAX_DEBUFF_SLOTS,
            { excludeDispelTypes = excluded }, DispelBorderColor(nil))

        for _, auras in ipairs(created) do
            auras:SetUnit(UNIT)
            auras:SetEnabled(true)
            auras:Show()
        end
        return b, d
    end)
    if ok then return { buffs = buffs, debuffs = debuffs } end

    state.nativeMainHand, state.nativeOffHand = false, false
    for _, auras in ipairs(created) do
        Quiet(auras, "SetEnabled", false)
        Quiet(auras, "Hide")
        state.parked[#state.parked + 1] = auras
    end
    return nil, buffs
end

-------------------------------------------------------------------------------
-- Legacy row: button pool (fallback only)
-------------------------------------------------------------------------------

-- Mouseover tooltip: dispatch lives in FrameHelpers.lua's ShowAuraTooltip
-- (SetUnitAura tried first, falling back to the filter-specific
-- SetUnitBuff/SetUnitDebuff, plus the lockdown fallback showing the cached
-- self.fsName). Weapon-enchant buttons have no aura index, so they fall
-- through to the enchantFallback below, which tries SetInventoryItem on the
-- enchanted slot instead (mirrors PartyFrames.lua's debuff-icon tooltip).
local function AuraButton_OnEnter(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOPLEFT")
    FS.FrameHelpers.ShowAuraTooltip(self, function(s)
        if s.enchantSlotId and HAS_TOOLTIP_SETINVENTORYITEM then
            return pcall(GameTooltip.SetInventoryItem, GameTooltip, UNIT, s.enchantSlotId)
        end
        return false
    end)
end

local function AuraButton_OnLeave()
    GameTooltip:Hide()
end

-- Icon + count + duration, skinned once via Theme.SkinButton and reused across
-- refreshes (acquired/released from a pool below) rather than
-- created/destroyed per update.
local function CreateAuraButton(parent)
    local button = CreateFrame("Frame", nil, parent)
    button:SetSize(ICON_SIZE, ICON_SIZE)
    button:EnableMouse(true)
    button:SetScript("OnEnter", AuraButton_OnEnter)
    button:SetScript("OnLeave", AuraButton_OnLeave)

    -- Seated by FS.FrameHelpers.SeatAuraTile right after SkinButton below, once the
    -- chamfer is known: plate behind, icon inset ceil(c / 2) and cropped, label plates.
    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(button)
    button.icon = icon

    local count = button:CreateFontString(nil, "OVERLAY")
    -- Re-anchored to the seated icon, with a dark plate, by SeatAuraTile below.
    -- A FontString with no font has height 0, and SetText on it throws
    -- "Invalid font height (0.000000)". `duration` below got a font; this
    -- one was missed.
    ApplyMono(count, COUNT_FONT_SIZE)
    button.count = count

    local duration = button:CreateFontString(nil, "OVERLAY")
    -- Bottom-right corner (mirrors `count`'s top-right placement) rather than
    -- bottom-center: keeps the short formatted label clear of the icon art's
    -- visual center. SeatAuraTile below anchors it there and puts a dark plate behind it.
    ApplyMono(duration, DURATION_FONT_SIZE)
    button.duration = duration

    SkinButton(button, { count = count, chamfer = TILE_CHAMFER })
    FS.FrameHelpers.SeatAuraTile(button)
    button.fsBaseColor = COLOR_BORDER
    button.fsHasCountdown = false
    button.auraIndex = nil
    button.filter = nil
    button.enchantSlotId = nil

    button:Hide()
    return button
end

local function AcquireButton(pool, parent, index)
    local button = pool[index]
    if not button then
        button = CreateAuraButton(parent)
        pool[index] = button
    end
    return button
end

local function ReleaseUnused(pool, fromIndex)
    for i = fromIndex, #pool do
        pool[i]:Hide()
    end
end

-------------------------------------------------------------------------------
-- Layout
-------------------------------------------------------------------------------

-- Seats the container at its canonical anchor (FS.Layout.buffs, Theme.lua),
-- same idiom as Minimap.lua/PartyFrames.lua. Falls back to a top-right
-- anchor clear of the minimap if FS.Layout.buffs isn't available.
local function ApplyContainerLayout()
    if FS.Layout and FS.Layout.Apply and FS.Layout.buffs then
        FS.Layout.Apply(container, "buffs")
    else
        container:ClearAllPoints()
        container:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", FALLBACK_ANCHOR_X, FALLBACK_ANCHOR_Y)
        container:SetSize(FALLBACK_WIDTH, FALLBACK_HEIGHT)
    end

    -- Debuffs are their OWN anchored block in the mockup, not extra rows under
    -- the buffs. FS.Layout.debuffs has existed in Theme.lua the whole time and
    -- was simply never consumed, which is why they came out stacked directly
    -- beneath the buff row instead of down and to the right where the mock puts
    -- them. The fallback keeps the old stacked behaviour rather than inventing
    -- a second guessed corner anchor.
    if FS.Layout and FS.Layout.Apply and FS.Layout.debuffs then
        FS.Layout.Apply(debuffContainer, "debuffs")
    else
        debuffContainer:ClearAllPoints()
        debuffContainer:SetPoint("TOPRIGHT", container, "BOTTOMRIGHT", 0, -ICON_SPACING)
        debuffContainer:SetSize(FALLBACK_WIDTH, FALLBACK_HEIGHT)
    end
end

-- Grid anchored to `parent`'s TOPRIGHT, growing left within a row then down.
-- `rowOffset` still shifts a category below the rows already used by one that
-- shares its parent, which after the split is only the weapon enchants sitting
-- under the buffs.
local function PositionButton(button, index, rowOffset, parent, cols)
    local col = index % cols
    local row = math.floor(index / cols) + rowOffset
    button:ClearAllPoints()
    button:SetPoint("TOPRIGHT", parent, "TOPRIGHT",
        -(col * (ICON_SIZE + ICON_SPACING)), -(row * (ICON_SIZE + ICON_SPACING)))
end

-------------------------------------------------------------------------------
-- Legacy row: buff / debuff drawing from the snapshot
-------------------------------------------------------------------------------

local function ApplyAuraData(button, aura, unit, filter, index)
    button.icon:SetTexture(aura.icon)
    if aura.count and aura.count > 1 then
        SetAuraLabel(button.count, aura.count)
        button.count:Show()
    else
        SetAuraLabel(button.count, nil)
        button.count:Hide()
    end

    button.fsExpiration = aura.expirationTime
    button.fsHasCountdown = (aura.duration or 0) > 0
    -- Kept for the lockdown tooltip below. A plain value: the snapshot holds nothing else.
    button.fsName = aura.name

    -- Tooltip lookup fields: `index` is the aura's position in the snapshot, which is its slot
    -- (ScanAuras stops at the first missing slot, so it never skips one), matching what
    -- SetUnitAura/SetUnitBuff/SetUnitDebuff expect.
    button.unit = unit
    button.filter = filter
    button.auraIndex = index
    button.enchantSlotId = nil

    button.fsBaseColor = (filter == FILTER_DEBUFFS) and DispelBorderColor(aura.dispelType) or COLOR_BORDER
end

local function DrawLegacyCategory(pool, list, filter, rowOffset, parent, cols)
    for i, aura in ipairs(list) do
        local button = AcquireButton(pool, parent, i)
        ApplyAuraData(button, aura, UNIT, filter, i)
        PositionButton(button, i - 1, rowOffset, parent, cols)
        button:Show()
    end
    ReleaseUnused(pool, #list + 1)
    return #list
end

local function DrawLegacyRows()
    local buffOk, buffCountOrErr = pcall(
        DrawLegacyCategory, buffPool, snapshot.buffs, FILTER_BUFFS, 0, container, BUFF_COLS
    )
    if buffOk then
        activeBuffCount = buffCountOrErr
    else
        ReportOnce("draw buffs", buffCountOrErr)
    end

    local debuffOk, debuffCountOrErr = pcall(
        DrawLegacyCategory, debuffPool, snapshot.debuffs, FILTER_DEBUFFS, 0, debuffContainer, DEBUFF_COLS
    )
    if debuffOk then
        activeDebuffCount = debuffCountOrErr
    else
        ReportOnce("draw debuffs", debuffCountOrErr)
    end
end

-------------------------------------------------------------------------------
-- Weapon enchants (legacy polled buttons: no native item enchantments)
-------------------------------------------------------------------------------

-- GetWeaponEnchantInfo only exposes remaining time, not total duration, so
-- expirationTime is derived fresh from "now" each poll. Only main-hand/
-- off-hand are read (ranged enchants aren't exposed by this API shape).
local function ReadEnchantSlot(hasEnchant, remainingMS, charges, invSlotName)
    if not hasEnchant then return nil end
    local slotId = GetInventorySlotInfo(invSlotName)
    local icon = slotId and GetInventoryItemTexture(UNIT, slotId)
    return {
        icon = icon,
        count = (charges and charges > 0) and charges or 0,
        expirationTime = GetTime() + (remainingMS or 0) / 1000,
        slotId = slotId,
    }
end

local function RefreshWeaponEnchants(rowOffset)
    if not HAS_WEAPON_ENCHANT then return 0 end

    local hasMain, mainMS, mainCharges, _, hasOff, offMS, offCharges = GetWeaponEnchantInfo()

    -- Only the slots the engine does not draw are polled, but a native one still holds its place
    -- in the line: the polled off hand sits after an enchanted native main hand, never on it.
    local slots, taken = {}, 0
    local main = ReadEnchantSlot(hasMain, mainMS, mainCharges, "MainHandSlot")
    if main then
        taken = taken + 1
        if not state.nativeMainHand then main.index = taken; slots[#slots + 1] = main end
    end
    local off = ReadEnchantSlot(hasOff, offMS, offCharges, "SecondaryHandSlot")
    if off then
        taken = taken + 1
        if not state.nativeOffHand then off.index = taken; slots[#slots + 1] = off end
    end

    for i, data in ipairs(slots) do
        local button = AcquireButton(enchantPool, container, i)
        button.icon:SetTexture(data.icon)
        if data.count > 1 then
            SetAuraLabel(button.count, data.count)
            button.count:Show()
        else
            SetAuraLabel(button.count, nil)
            button.count:Hide()
        end
        button.fsExpiration = data.expirationTime
        button.fsHasCountdown = true
        button.fsBaseColor = COLOR_BORDER
        button.unit = nil
        button.filter = nil
        button.auraIndex = nil
        button.enchantSlotId = data.slotId
        PositionButton(button, data.index - 1, rowOffset, container, BUFF_COLS)
        button:Show()
    end

    ReleaseUnused(enchantPool, #slots + 1)
    return #slots
end

-------------------------------------------------------------------------------
-- Legacy row: expiring tint / duration text
-------------------------------------------------------------------------------

local function RefreshExpiringTint(pool, count)
    local now = GetTime()
    for i = 1, count do
        local button = pool[i]
        if button then
            local remaining = button.fsHasCountdown and (button.fsExpiration - now) or nil
            if remaining and remaining > 0 then
                SetAuraLabel(button.duration, FormatDuration(remaining))
                TintAuraBorder(
                    button.fsSkin,
                    remaining <= EXPIRING_THRESHOLD and COLOR_BORDER_EXPIRING or button.fsBaseColor
                )
            else
                SetAuraLabel(button.duration, nil)
                TintAuraBorder(button.fsSkin, button.fsBaseColor)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Orchestration
-------------------------------------------------------------------------------

-- The legacy paths' poll: weapon enchants have no update event, so they are re-polled here
-- (called after every aura event and on the throttled tick); the legacy row's countdown text and
-- expiring tint are derived from stored expiry. With the engine containers and native item
-- enchantments there is nothing to poll and this never runs.
local function TickRefresh()
    if state.legacyEnchants then
        -- Enchants share the BUFF block, so they clear the buff rows only. The offset comes from
        -- the snapshot, which is the last readable count (the engine draws the live row).
        local ok, countOrErr = pcall(RefreshWeaponEnchants, SnapshotBuffRows())
        if ok then
            activeEnchantCount = countOrErr
        else
            ReportOnce("refresh weapon enchants", countOrErr)
        end
    end

    local tintOk, tintErr = pcall(function()
        if not state.engine then
            RefreshExpiringTint(buffPool, activeBuffCount)
            RefreshExpiringTint(debuffPool, activeDebuffCount)
        end
        if state.legacyEnchants then
            RefreshExpiringTint(enchantPool, activeEnchantCount)
        end
    end)
    if not tintOk then
        ReportOnce("tint tick", tintErr)
    end
end

-- Every aura event (and the login seed): refresh the snapshot while it can be read, redraw the
-- legacy row from it when it changed, run the poll. In combat the snapshot is not touched, so
-- the engine containers (which do not need it) are not touched either. Returns whether the
-- snapshot changed.
local function RefreshAurasEvent(event)
    if not UnitExists(UNIT) then return false end

    -- Engine mode draws from the containers and nothing reads the snapshot in a fight, so the
    -- per-UNIT_AURA scan is pure cost there; the retry after combat refreshes it. The scan at
    -- PLAYER_REGEN_DISABLED still runs: it is the last read before lockdown.
    if event == "UNIT_AURA" and state.engine and InCombatNow() then return false end

    local changed = RefreshSnapshot()
    if not state.engine and changed then
        DrawLegacyRows()
    end
    if not state.engine or state.legacyEnchants then
        TickRefresh()
    end
    return changed
end

local function OnAuraEvent(event)
    local ok, err = pcall(RefreshAurasEvent, event)
    if not ok then
        ReportOnce("refresh", err)
    end
end

-------------------------------------------------------------------------------
-- Init (non-secure frames only; no combat defer needed)
-------------------------------------------------------------------------------

local function Init()
    -- Dim, not hide: these three are Edit Mode systems and Hide()+OnShow-hook
    -- taints their secure Update path on re-anchor (level-up). See CLAUDE.md's
    -- Buffs.lua/FrameHelpers.lua entries (2026-09-25).
    DimBlizzardFrame(BuffFrame)
    DimBlizzardFrame(DebuffFrame)
    -- Read through _G: the frame is absent on some clients (lua-lint med).
    DimBlizzardFrame(_G["TemporaryEnchantFrame"])

    container = CreateFrame("Frame", "ForeverSTUwaveBuffsContainer", UIParent)
    debuffContainer = CreateFrame("Frame", "ForeverSTUwaveDebuffsContainer", UIParent)
    ApplyContainerLayout()

    local engineContainers, engineErr = BuildEngineContainers()
    if engineContainers then
        state.engine = true
        FS.buffsAuraContainer = engineContainers.buffs
        FS.debuffsAuraContainer = engineContainers.debuffs
    elseif not state.warned then
        state.warned = true
        FS.LogDegradeOnce("buffs_aura_container",
            "|cffff4488Forever STUwave|r: player aura containers unavailable, buffs and debuffs freeze in combat ("
            .. tostring(engineErr) .. ")")
    end
    state.legacyEnchants = HAS_WEAPON_ENCHANT and not (state.nativeMainHand and state.nativeOffHand)

    local events = CreateFrame("Frame")
    SafeRegisterUnitEvent(events, "UNIT_AURA", UNIT)
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    -- The snapshot has to be taken again the moment lockdown lifts: UNIT_AURA fires on a CHANGE
    -- and is ignored (nothing is read) during a fight, so without this the legacy row, and the
    -- snapshot FS.PlayerAuras hands out, would miss everything that changed in combat until some
    -- later unrelated aura change.
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    -- One last read at the instant combat starts: the player is in combat but not yet locked
    -- down, so auras still read (Theme.lua's FS.AurasReadable comment). Skipped by the gate
    -- when the client already says they are secret.
    events:RegisterEvent("PLAYER_REGEN_DISABLED")
    events:SetScript("OnEvent", function(_, event)
        OnAuraEvent(event)
    end)
    -- A regen whose read was refused (the client can still say "secret" for a moment) gets the
    -- shared retry chain in Theme.lua; this runs once reads work again. The chain is not tied to
    -- the handler above, so a refresh that throws at regen does not cost the retry.
    FS.OnAurasReadable(function() OnAuraEvent("retry") end)

    if not state.engine or state.legacyEnchants then
        local tickFrame = CreateFrame("Frame")
        local elapsedSinceTick = 0
        tickFrame:SetScript("OnUpdate", function(_, elapsed)
            elapsedSinceTick = elapsedSinceTick + elapsed
            if elapsedSinceTick < REFRESH_THROTTLE then return end
            elapsedSinceTick = 0
            TickRefresh()
        end)
    end

    FS.buffsContainer = container
    FS.debuffsContainer = debuffContainer

    local ok, err = pcall(RefreshAurasEvent, "init")
    if not ok then
        ReportOnce("refresh", err)
    end
end

Init()
