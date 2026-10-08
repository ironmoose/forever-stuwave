-- Forever STUwave: Target/Focus Auras
-- Custom TARGET and FOCUS buff/debuff aura display, parametrized over unit
-- token (BuildAuraDisplay) rather than two divergent copies of this file.
-- Built like Buffs.lua's PLAYER aura display (icon pool, Theme chrome,
-- event-driven refresh) but neither target nor focus has a Blizzard aura
-- frame of its own on this client to hide -- there is nothing to reskin,
-- only a gap to fill. Debuffs get visual priority (closest to the panel,
-- own-cast tint) per Parker's ask: "I want to see my own dots on the target."

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local ApplyMono = FS.Theme.ApplyMono
local SkinButton = FS.Theme.SkinButton
local SetAuraLabel = FS.FrameHelpers.SetAuraLabel
local COLOR_BORDER = FS.Theme.COLOR_BORDER

-- Own-cast debuff tint. Not a canonical design token (mirrors Buffs.lua's own
-- local COLOR_BORDER_EXPIRING) -- Theme.COLOR_POWER is this addon's cyan
-- power-bar color, not pink, so this reuses UnitFrames.lua's local pink
-- (COLOR_CARET_POWER, #ff4dd8) value instead of a mismatched token.
local COLOR_OWN_CAST = { 1, 0.302, 0.847, 1 } -- #ff4dd8

-------------------------------------------------------------------------------
-- Layout constants
-------------------------------------------------------------------------------

local ICON_SIZE = 24
local ICON_SPACING = 4
local COLS = 9 -- 9*24 + 8*4 = 248, fits UnitFrames.lua's PANEL_WIDTH (260)
local ROWS_VISIBLE = 2 -- broad-strokes container sizing; see BuildAuraDisplay
local CONTAINER_HEIGHT = ROWS_VISIBLE * (ICON_SIZE + ICON_SPACING)
local CONTAINER_GAP = 4 -- gap below the panel, and between debuff/buff blocks

local MAX_BUFF_SLOTS = 32
local MAX_DEBUFF_SLOTS = 16

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- Prints a failure message once per label instead of once per aura/event.
-- Shared plumbing lives in FrameHelpers.lua (FS.FrameHelpers.NewStepRunner);
-- this file keeps its own message wording (dup convention, see
-- FrameHelpers.lua's header on why these wrappers are duplicated per file).
local _, ReportOnce = FS.FrameHelpers.NewStepRunner(function(label)
    return "ForeverSTUwave targetauras: " .. label
end)

local function ReportRegisterFailure(event, err)
    ReportOnce("register " .. event, err)
end

local function SafeRegisterUnitEvent(events, event, unit)
    FS.FrameHelpers.SafeRegisterUnitEvent(events, event, unit, ReportRegisterFailure)
end

-- Recolors a SkinButton border. Dup of Buffs.lua's TintAuraBorder (per-file
-- helper duplication convention, see FrameHelpers.lua's header).
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

-- Short duration label. Dup of Buffs.lua's FormatDuration (same per-file
-- duplication convention).
local function FormatDuration(remaining)
    if remaining > 3600 then
        return string.format("%dh", math.floor(remaining / 3600))
    elseif remaining > 60 then
        return string.format("%dm", math.floor(remaining / 60))
    else
        return string.format("%ds", math.floor(remaining))
    end
end

-- Seconds left on an aura, or nil when that cannot be answered: no expiry
-- recorded (a permanent buff) or a secret value arithmetic can't touch.
-- Reads this file's own aura shape (`expirationTime`, as returned by
-- FS.FrameHelpers.ReadAuraSlot).
-- nil means "draw no countdown", never a guess at a value we can't read.
local function SecondsRemaining(aura)
    local expiration = aura and aura.expirationTime
    if not expiration or expiration == 0 then return nil end
    if FS.IsSecret and FS.IsSecret(expiration) then return nil end
    local now = GetTime and GetTime()
    if not now then return nil end
    return expiration - now
end

-------------------------------------------------------------------------------
-- Aura reading
-------------------------------------------------------------------------------

local function ReadAuraSlot(unit, index, filter)
    return FS.FrameHelpers.ReadAuraSlot(unit, index, filter, ReportOnce)
end

-------------------------------------------------------------------------------
-- Button pool
-------------------------------------------------------------------------------

-- A hidden target frame leaves its aura icons mouse-live but invisible, so they show no tooltip.
local function AuraButton_OnEnter(self)
    if FS.UnitFrames and FS.UnitFrames.IsHidden(self.unit) then return end
    GameTooltip:SetOwner(self, "ANCHOR_TOPLEFT")
    FS.FrameHelpers.ShowAuraTooltip(self)
end

local function AuraButton_OnLeave()
    GameTooltip:Hide()
end

-- Icon + count + duration, skinned once via Theme.SkinButton and reused
-- across refreshes (acquired/released from a pool below), same construction
-- as Buffs.lua's CreateAuraButton.
local function CreateAuraButton(parent)
    local button = CreateFrame("Frame", nil, parent)
    button:SetSize(ICON_SIZE, ICON_SIZE)
    button:EnableMouse(true)
    button:SetScript("OnEnter", AuraButton_OnEnter)
    button:SetScript("OnLeave", AuraButton_OnLeave)

    -- Seated by FS.FrameHelpers.SeatAuraTile right after SkinButton below, once the
    -- chamfer is known (Theme.CutSizeIcon(ICON_SIZE), 4 for the 24 tile): plate behind,
    -- icon inset ceil(c / 2) and cropped, label plates.
    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(button)
    button.icon = icon

    local count = button:CreateFontString(nil, "OVERLAY")
    -- Re-anchored to the seated icon, with a dark plate, by SeatAuraTile below.
    ApplyMono(count, 9)
    button.count = count

    local duration = button:CreateFontString(nil, "OVERLAY")
    ApplyMono(duration, 8)
    button.duration = duration

    SkinButton(button, { count = count })
    FS.FrameHelpers.SeatAuraTile(button)
    button.fsBaseColor = COLOR_BORDER
    button.unit = nil
    button.filter = nil
    button.auraIndex = nil
    button.fsName = nil

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

-- Grid anchored to `parent`'s TOPLEFT, growing right within a row then down.
local function PositionButton(button, index, parent)
    local col = index % COLS
    local row = math.floor(index / COLS)
    button:ClearAllPoints()
    button:SetPoint("TOPLEFT", parent, "TOPLEFT",
        col * (ICON_SIZE + ICON_SPACING), -(row * (ICON_SIZE + ICON_SPACING)))
end

-------------------------------------------------------------------------------
-- Per-unit display state
-------------------------------------------------------------------------------

-- Keyed by unit token ("target"/"focus"); each display owns its own
-- containers/pools/counts so scanning one unit never touches the other's
-- icons. One parametrized builder (BuildAuraDisplay) rather than two
-- divergent copies of this whole file.
local displays = {}

-- debuffContainer is sized DYNAMICALLY to its actual active-debuff row count
-- (collapsing to a ~1px floor at zero debuffs) so it doesn't reserve a big
-- fixed block of dead space above buffContainer when the target has few or
-- no debuffs -- see the CLAUDE.md TargetAuras.lua entry for the full "target
-- buffs sat way too far down" root cause. A nonzero floor, not SetHeight(0),
-- since SetHeight(0)'s effect on a still-anchored child (buffContainer, below)
-- is UNVERIFIED in-game on this client.
local function DebuffContainerHeight(activeDebuffCount)
    if not activeDebuffCount or activeDebuffCount <= 0 then
        return 1
    end
    local rows = math.ceil(activeDebuffCount / COLS)
    return rows * (ICON_SIZE + ICON_SPACING)
end

-- Debuffs anchor directly off the panel's `.visual` bottom edge (closest to
-- the frame -- Parker's ask for visual priority on his own dots); buffs sit
-- below that. debuffContainer's height is measured from the live debuff row
-- count (DebuffContainerHeight, above); buffContainer keeps a fixed
-- broad-strokes height (ROWS_VISIBLE rows) and simply follows debuffContainer's
-- own BOTTOM edge, so it no longer sits behind a big reserved dead-space block
-- when there are few or no debuffs. Icons beyond buffContainer's nominal box
-- are still positioned but not clipped. Parker will retune spacing/rows in-game.
local function BuildAuraDisplay(unit, frame)
    local display = {
        unit = unit,
        buffPool = {},
        debuffPool = {},
        activeBuffCount = 0,
        activeDebuffCount = 0,
    }

    local debuffContainer = CreateFrame("Frame", nil, frame.visual)
    debuffContainer:SetPoint("TOPLEFT", frame.visual, "BOTTOMLEFT", 0, -CONTAINER_GAP)
    debuffContainer:SetPoint("TOPRIGHT", frame.visual, "BOTTOMRIGHT", 0, -CONTAINER_GAP)
    debuffContainer:SetHeight(DebuffContainerHeight(0))

    local buffContainer = CreateFrame("Frame", nil, frame.visual)
    buffContainer:SetPoint("TOPLEFT", debuffContainer, "BOTTOMLEFT", 0, -CONTAINER_GAP)
    buffContainer:SetPoint("TOPRIGHT", debuffContainer, "BOTTOMRIGHT", 0, -CONTAINER_GAP)
    buffContainer:SetHeight(CONTAINER_HEIGHT)

    display.debuffContainer = debuffContainer
    display.buffContainer = buffContainer

    displays[unit] = display
    return display
end

-------------------------------------------------------------------------------
-- Refresh
-------------------------------------------------------------------------------

local function ApplyAuraData(button, aura, unit, filter, index, isDebuff)
    button.icon:SetTexture(aura.icon)
    if aura.count and aura.count > 1 then
        SetAuraLabel(button.count, aura.count)
        button.count:Show()
    else
        SetAuraLabel(button.count, nil)
        button.count:Hide()
    end

    -- Tooltip lookup fields: `index` is the same slot the aura was just read
    -- from (RefreshCategory breaks on the first missing slot), matching what
    -- SetUnitAura/SetUnitDebuff/SetUnitBuff expect.
    button.unit = unit
    button.filter = filter
    button.auraIndex = index
    button.fsName = aura.name

    local remaining = SecondsRemaining(aura)
    if remaining and remaining > 0 then
        SetAuraLabel(button.duration, FormatDuration(remaining))
    else
        SetAuraLabel(button.duration, nil)
    end

    -- `caster` is a plain string field, not a secret value (PartyFrames.lua's
    -- FindPlayerCastBuff already compares it the same way), so this
    -- comparison is legal without an IsSecret guard.
    local baseColor = COLOR_BORDER
    if isDebuff and aura.caster == "player" then
        baseColor = COLOR_OWN_CAST
    end
    button.fsBaseColor = baseColor
    TintAuraBorder(button.fsSkin, baseColor)
end

local function RefreshCategory(pool, unit, filter, maxSlots, parent, isDebuff)
    local shown = 0
    for slot = 1, maxSlots do
        local aura = ReadAuraSlot(unit, slot, filter)
        if not aura then break end
        shown = shown + 1
        local button = AcquireButton(pool, parent, shown)
        ApplyAuraData(button, aura, unit, filter, slot, isDebuff)
        PositionButton(button, shown - 1, parent)
        button:Show()
    end
    ReleaseUnused(pool, shown + 1)
    return shown
end

local function ReleaseAll(display)
    ReleaseUnused(display.debuffPool, 1)
    ReleaseUnused(display.buffPool, 1)
    display.activeDebuffCount = 0
    display.activeBuffCount = 0
    display.debuffContainer:SetHeight(DebuffContainerHeight(0))
end

local function RefreshDisplay(display)
    local unit = display.unit
    if not UnitExists(unit) then
        ReleaseAll(display)
        return
    end

    -- Aura reads are REFUSED (not secret -- refused, with an error) under
    -- combat lockdown. Bailing keeps whatever is already displayed rather
    -- than clearing/repositioning on a refusal -- see Buffs.lua's
    -- RefreshAurasEvent comment for the 9.2MB leak this gate avoids.
    if not FS.AurasReadable() then return end

    -- Debuffs first: Parker's ask is to see his own dots on the target, so
    -- the debuff container (closest to the panel) is populated before buffs.
    local debuffOk, debuffCountOrErr = pcall(
        RefreshCategory, display.debuffPool, unit, "HARMFUL", MAX_DEBUFF_SLOTS, display.debuffContainer, true
    )
    if debuffOk then
        display.activeDebuffCount = debuffCountOrErr
        display.debuffContainer:SetHeight(DebuffContainerHeight(display.activeDebuffCount))
    else
        ReportOnce("refresh debuffs (" .. unit .. ")", debuffCountOrErr)
    end

    local buffOk, buffCountOrErr = pcall(
        RefreshCategory, display.buffPool, unit, "HELPFUL", MAX_BUFF_SLOTS, display.buffContainer, false
    )
    if buffOk then
        display.activeBuffCount = buffCountOrErr
    else
        ReportOnce("refresh buffs (" .. unit .. ")", buffCountOrErr)
    end
end

-------------------------------------------------------------------------------
-- Init (event-driven only -- no OnUpdate/ticker anywhere in this file; a
-- ticker-driven aura scan under combat lockdown caused a 9.2MB leak on
-- 2026-09-20, see Buffs.lua's RefreshAurasEvent comment. Duration text is
-- therefore static between UNIT_AURA events, an accepted broad-strokes
-- limitation.)
-------------------------------------------------------------------------------

local function Init()
    -- UnitFrames.lua's .toc load order guarantees FS.target/FS.focus are
    -- already set by the time this runs, except a rare in-combat-reload race
    -- (this file's own combat defer below, racing UnitFrames.lua's). Bail
    -- loudly instead of throwing on a nil frame.
    if not FS.target or not FS.focus then
        FS.LogDegradeOnce("targetauras_nounits",
            "|cffff4488Forever STUwave|r targetauras: FS.target/FS.focus not set at init, skipping")
        return
    end

    BuildAuraDisplay("target", FS.target)
    BuildAuraDisplay("focus", FS.focus)

    local targetEvents = CreateFrame("Frame")
    SafeRegisterUnitEvent(targetEvents, "UNIT_AURA", "target")
    targetEvents:RegisterEvent("PLAYER_TARGET_CHANGED")
    targetEvents:SetScript("OnEvent", function()
        local ok, err = pcall(RefreshDisplay, displays.target)
        if not ok then ReportOnce("refresh target", err) end
    end)

    local focusEvents = CreateFrame("Frame")
    SafeRegisterUnitEvent(focusEvents, "UNIT_AURA", "focus")
    focusEvents:RegisterEvent("PLAYER_FOCUS_CHANGED")
    focusEvents:SetScript("OnEvent", function()
        local ok, err = pcall(RefreshDisplay, displays.focus)
        if not ok then ReportOnce("refresh focus", err) end
    end)

    -- The one event that makes the combat gate survivable (mirrors
    -- Buffs.lua's PLAYER_REGEN_ENABLED registration comment): without a scan
    -- at the moment lockdown lifts, a dot applied in combat and still running
    -- afterwards is never drawn at all, not until some later, unrelated
    -- UNIT_AURA happens to fire. Refreshes BOTH units.
    local function RefreshBoth()
        local ok, err = pcall(RefreshDisplay, displays.target)
        if not ok then ReportOnce("refresh target", err) end
        ok, err = pcall(RefreshDisplay, displays.focus)
        if not ok then ReportOnce("refresh focus", err) end
    end
    local regenEvents = CreateFrame("Frame")
    regenEvents:RegisterEvent("PLAYER_REGEN_ENABLED")
    regenEvents:SetScript("OnEvent", RefreshBoth)
    -- The scan above is refused while the client still says auras are secret: the shared retry
    -- chain (Theme.lua) runs it again once reads work.
    FS.OnAurasReadable(RefreshBoth)

    local ok, err = pcall(RefreshDisplay, displays.target)
    if not ok then ReportOnce("refresh target", err) end
    ok, err = pcall(RefreshDisplay, displays.focus)
    if not ok then ReportOnce("refresh focus", err) end
end

if InCombatLockdown() then
    local regen = CreateFrame("Frame")
    regen:RegisterEvent("PLAYER_REGEN_ENABLED")
    regen:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_REGEN_ENABLED")
        Init()
    end)
else
    Init()
end
