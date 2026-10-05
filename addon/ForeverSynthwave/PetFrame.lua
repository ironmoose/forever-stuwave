-- Forever Synthwave: Pet Frame (the pet component's one panel: container +
-- chrome + drag/lock + visibility gate + the HP/mana block)
--
-- ONE panel, the approved console dock option C (mockups/gunsight-hud-v2-2026-10-02,
-- PE_G.dc and drawPet's dc branch): Parker, "put the pet HP and mana bar above the
-- action bar and only take up like 2/5, and leave the rest for the cast bar ... as one
-- component". TOP ROW (26 high): statusSlot (the name with plain muted "LV n" text at its
-- right end, then HP and mana stacked as two thin laser rails with their numbers) on the
-- left, castSlot (PetCastBar.lua, 198 x 26) in the rest. BOTTOM ROW: barSlot, the 10 pet
-- buttons (PetActionBar.lua) across the full interior. This file owns the shell, the
-- chrome, drag/lock, the visibility gate and the HP/mana block; the cast bar and the
-- buttons parent into the slots it exports. The chrome is still the floating panel look;
-- docking it onto the Console is a later step.
--
-- CONTAINER IS IMPLICITLY PROTECTED: barSlot parents our own
-- SecureActionButtonTemplate pet-action buttons, so `container` (their ancestor)
-- is implicitly protected too -- Show()/Hide()/SetAttribute on it throw
-- ADDON_ACTION_BLOCKED in combat, exactly as documented in PetActionBar.lua's own
-- RequestBuild comment (verified there against Wowpedia's Secure Execution and
-- Tainting article plus two real addon bug reports with the identical symptom).
-- Every geometry change (SetPoint/SetSize on the container or a slot) and every real
-- Show/Hide is therefore out of combat only, deferred to PLAYER_REGEN_ENABLED
-- (`pendingRescale`, `pendingLockApply`, `pendingReset`).
--
-- Headless check: python3 addons/petframe-harness.py (geometry against the numbers
-- parsed back out of the mockup's dc branch, at scale 1 and 0.64).

local _, FS = ...
FS.PetFrame = FS.PetFrame or {}

-------------------------------------------------------------------------------
-- Theme / geometry constants
-------------------------------------------------------------------------------

-- The panel chrome (outline, fill, halo, the red edge twin) is PetDock.lua's, in "float" or "dock"
-- mode; this file only builds the container and what sits inside it.

-- Status block chrome: laser rails built by FrameHelpers.CreateLaserRail, which
-- supplies the track, fill, bloom and spark, so only the two rail colors, the muted
-- level text color and the mono font for the text are needed here.
local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_MUTED = FS.Theme.COLOR_MUTED
local COLOR_RED = FS.Theme.COLOR_RED
local FONT_MONO = FS.Theme.FONT_MONO

-- Geometry, at DESIGN scale (2560x1440 canvas, see Layout.lua), every number the
-- mockup's option C draws (PE_G.dc: PW 348 x PH 68, TOPH 26; PE_PAD 6, PE_LW 134,
-- PE_GX 4, PE_BTN 30); each value is multiplied by FS.Layout.Scale() where it is used.
-- The panel size itself is the "petcontainer" Layout entry (348 x 68).
--
-- The panel insets are NOT square: the top inset is 5 (drawPet's `ty = 5`), the sides
-- are PAD 6 (`tx = PE_PAD`), and the bottom pad is what is left under the buttons (4).
-- Interior at design scale: 348 - 2*6 = 336 wide.
--   top row (TOP_HEIGHT 26):
--     statusSlot  STATUS_WIDTH 134 wide, at the interior's top left (name, level, rails).
--     castSlot    the other 198 (336 - 134 - GAP): anchored GAP right of statusSlot
--                 and to the interior's right edge, same top, same height (the cast
--                 bar is sized to it: 198 x 26).
--   (ROW_GAP_TOP 3: drawPet's `ty + top + 3`)
--   barSlot (BAR_HEIGHT 30): the 10 buttons. 336 is DELIBERATELY == 10 buttons *
--               30px + 9 gaps * 4px. 5 + 26 + 3 + 30 + 4 = 68, so 4 is left under it.
local INSET_TOP = 5
local INSET_SIDE = 6
local GAP = 4
local ROW_GAP_TOP = 3
local TOP_HEIGHT = 26
local STATUS_WIDTH = 134
local BAR_HEIGHT = 30

-- Frame levels above the container. The chrome (PetDock.lua: the fill and normal edge at +0, the red
-- edge twins and PetFrame's fallback red edge at +1) draws only the panel edge, but it must never rely
-- on creation order against the slots, so the three slots sit strictly above the highest chrome level.
local SLOT_LEVEL_OFFSET = 2

-- The HP/mana block (design px, scaled where used), the mockup's peStatusDc: a 9 high
-- name row (the name left, plain muted "LV n" text right, no chip), 1, a 7 high HP rail,
-- 2, a 7 high mana rail = 26 (the rails start at y + 10). The rails are
-- FrameHelpers.CreateLaserRail rails (the party recipe), NOT the mockup's pill bars: the
-- port keeps the laser rail (no new bar type), re-fitted to the mockup's 7 high bars.
-- Bloom and spark hang outside the core shell, so they take no layout space. Each rail
-- carries its value ("253 / 253") in the 7.5 pt text FrameHelpers puts above the bloom.
local NAME_ROW_HEIGHT = 9
local ROW_GAP = 1
local RAIL_CORE_HEIGHT = 7
local RAIL_PAIR_GAP = 2
local RAIL_BLOOM_SIZE = 4
local RAIL_SPARK_SIZE = 16
local NAME_PAD = 1
local NAME_LEVEL_GAP = 4
local NAME_FONT_SIZE = 9
local LEVEL_FONT_SIZE = 7.5
local VALUE_FONT_SIZE = 7.5

-- Rail tint by UnitPowerType, shared with the party frames' power rail.
local POWER_COLORS = FS.FrameHelpers.POWER_COLORS

-- LOW HP (step S7, the mockup's drawPet low state): a red pulsing edge, a red name and a red
-- HP rail. The threshold is PartyFrames' (same fraction, same epsilon past it so exactly 35%
-- still counts). The edge pulses .6 to 1 on a 1.1 s period (`.6 + .4 * pulse`), so one bounce
-- leg is half of it. The red edge ring and glow wear the party box's glow strength.
local LOW_HP_FRACTION = 0.35
local LOW_HP_EPSILON = 0.0005
local LOW_EDGE_GLOW_ALPHA = 0.5
local LOW_PULSE_TOP = 1.0
local LOW_PULSE_FLOOR = 0.6
local LOW_PULSE_LEG = 0.55

-------------------------------------------------------------------------------
-- Module state
-------------------------------------------------------------------------------

local container, castSlot, barSlot, statusSlot, dragHandle
local healthBar, powerBar, nameText, levelText, nameRow
local redHealthBar, redName
local locked = false
local docked = false   -- seated on the Console by PetDock.lua (SeatDocked); drag is off while true
local pendingLockApply = false
local pendingRescale = false
local pendingReset = false
local events

-------------------------------------------------------------------------------
-- Slot geometry
-------------------------------------------------------------------------------

-- Text sizes are design px times the scale, so a UI Scale change re-applies them with
-- the geometry. Called from ApplySlotGeometry once the status block exists.
local function ApplyStatusFonts(scale)
    ApplyFontGeneric(nameText, FONT_MONO, NAME_FONT_SIZE * scale, nil, "OUTLINE")
    ApplyMono(levelText, LEVEL_FONT_SIZE * scale, COLOR_MUTED)
    ApplyFontGeneric(healthBar.text, FONT_MONO, VALUE_FONT_SIZE * scale, nil, "OUTLINE")
    ApplyFontGeneric(powerBar.text, FONT_MONO, VALUE_FONT_SIZE * scale, nil, "OUTLINE")
    -- The low-HP twins wear the same sizes (the name and rail text in red / white).
    if redName then ApplyFontGeneric(redName, FONT_MONO, NAME_FONT_SIZE * scale, COLOR_RED, "OUTLINE") end
    if redHealthBar then
        ApplyFontGeneric(redHealthBar.text, FONT_MONO, VALUE_FONT_SIZE * scale, nil, "OUTLINE")
    end
end

-- (Re)seats the three slots and the status block from the current FS.Layout.Scale(),
-- so their literal SetSize/gap values (scaled pixels, not automatic like a plain
-- SetPoint offset) stay correct across a UI Scale change. Called once at build time
-- and again from the OnRescale callback below (never in combat, see the file header).
local function ApplySlotGeometry(scale)
    if not (container and castSlot and barSlot and statusSlot) then return end

    local insetTop = INSET_TOP * scale
    local insetSide = INSET_SIDE * scale
    local gap = GAP * scale

    -- Top row: HP/mana block at the left, cast slot in the rest, same top and height.
    statusSlot:ClearAllPoints()
    statusSlot:SetPoint("TOPLEFT", container, "TOPLEFT", insetSide, -insetTop)
    statusSlot:SetSize(STATUS_WIDTH * scale, TOP_HEIGHT * scale)

    castSlot:ClearAllPoints()
    castSlot:SetPoint("TOPLEFT", statusSlot, "TOPRIGHT", gap, 0)
    castSlot:SetPoint("TOPRIGHT", container, "TOPRIGHT", -insetSide, -insetTop)
    castSlot:SetHeight(TOP_HEIGHT * scale)

    -- Bottom row: the pet buttons under both, across the whole interior.
    local rowGap = ROW_GAP_TOP * scale
    barSlot:ClearAllPoints()
    barSlot:SetPoint("TOPLEFT", statusSlot, "BOTTOMLEFT", 0, -rowGap)
    barSlot:SetPoint("TOPRIGHT", castSlot, "BOTTOMRIGHT", 0, -rowGap)
    barSlot:SetHeight(BAR_HEIGHT * scale)

    -- Status block: the rail sizes, the name row and every gap are literal scaled-pixel
    -- values, so they are re-seated here like the slots above. Guarded separately
    -- because Build() calls ApplySlotGeometry once BEFORE the status block exists.
    if healthBar and powerBar and nameRow and levelText then
        local SetLaserRailSize = FS.FrameHelpers.SetLaserRailSize
        local nameGap = ROW_GAP * scale
        local railGap = RAIL_PAIR_GAP * scale
        SetLaserRailSize(healthBar, RAIL_CORE_HEIGHT * scale, RAIL_BLOOM_SIZE * scale,
            RAIL_SPARK_SIZE * scale, RAIL_SPARK_SIZE * scale)
        SetLaserRailSize(powerBar, RAIL_CORE_HEIGHT * scale, RAIL_BLOOM_SIZE * scale,
            RAIL_SPARK_SIZE * scale, RAIL_SPARK_SIZE * scale)
        if redHealthBar then
            SetLaserRailSize(redHealthBar, RAIL_CORE_HEIGHT * scale, RAIL_BLOOM_SIZE * scale,
                RAIL_SPARK_SIZE * scale, RAIL_SPARK_SIZE * scale)
        end

        nameRow:ClearAllPoints()
        nameRow:SetPoint("TOPLEFT", statusSlot, "TOPLEFT", 0, 0)
        nameRow:SetPoint("TOPRIGHT", statusSlot, "TOPRIGHT", 0, 0)
        nameRow:SetHeight(NAME_ROW_HEIGHT * scale)

        -- The level is plain text at the row's right edge; the name stops short of it.
        levelText:ClearAllPoints()
        levelText:SetPoint("RIGHT", nameRow, "RIGHT", 0, 0)
        nameText:ClearAllPoints()
        nameText:SetPoint("LEFT", nameRow, "LEFT", NAME_PAD * scale, 0)
        nameText:SetPoint("RIGHT", levelText, "LEFT", -NAME_LEVEL_GAP * scale, 0)
        if redName then
            redName:ClearAllPoints()
            redName:SetPoint("LEFT", nameRow, "LEFT", NAME_PAD * scale, 0)
            redName:SetPoint("RIGHT", levelText, "LEFT", -NAME_LEVEL_GAP * scale, 0)
        end

        healthBar.shell:ClearAllPoints()
        healthBar.shell:SetPoint("TOPLEFT", nameRow, "BOTTOMLEFT", 0, -nameGap)
        healthBar.shell:SetPoint("TOPRIGHT", nameRow, "BOTTOMRIGHT", 0, -nameGap)
        powerBar.shell:ClearAllPoints()
        powerBar.shell:SetPoint("TOPLEFT", healthBar.shell, "BOTTOMLEFT", 0, -railGap)
        powerBar.shell:SetPoint("TOPRIGHT", healthBar.shell, "BOTTOMRIGHT", 0, -railGap)
        if redHealthBar then
            redHealthBar.shell:ClearAllPoints()
            redHealthBar.shell:SetPoint("TOPLEFT", healthBar.shell, "TOPLEFT", 0, 0)
            redHealthBar.shell:SetPoint("TOPRIGHT", healthBar.shell, "TOPRIGHT", 0, 0)
        end

        ApplyStatusFonts(scale)
    end
end

-------------------------------------------------------------------------------
-- Drag + lock
-------------------------------------------------------------------------------

-- Persists the container's current anchor as a per-player override of the
-- design default (FS.Layout.petcontainer). Only point/relativePoint/x/y are
-- stored -- relativeTo is not, since ApplySavedPosition below always
-- re-anchors to UIParent, the same relativeTo every FS.Layout.Apply call
-- uses, so there's nothing to lose by not storing it.
local function SavePosition()
    local point, _, relativePoint, x, y = container:GetPoint()
    if not point then return end
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.petFrame = ForeverSynthwaveDB.petFrame or {}
    ForeverSynthwaveDB.petFrame.pos = { point = point, relativePoint = relativePoint, x = x, y = y }
end

-- Applied once at build time, BEFORE the container's first Show(), so a
-- saved drag position is never visibly preceded by the design default. A
-- drag position is a per-player override, so it wins over FS.Layout.Apply's
-- seat whenever one exists.
local function ApplySavedPosition()
    local saved = type(ForeverSynthwaveDB) == "table" and ForeverSynthwaveDB.petFrame
    local pos = saved and saved.pos
    if not (pos and pos.point and pos.relativePoint) then return end
    container:ClearAllPoints()
    container:SetPoint(pos.point, UIParent, pos.relativePoint, pos.x, pos.y)
end

-- Shared body for a rescale reconciliation, called from two places: the
-- OnRescale callback below (the immediate path, when not in combat) and
-- OnEvent's PLAYER_REGEN_ENABLED branch (the deferred path, when a rescale
-- landed mid-combat and had to wait -- see `pendingRescale` below).
local function ApplyRescale()
    if docked then
        -- The dock owns the anchor: Layout.lua's watcher does not know a docked container (SeatDocked
        -- drops it from its list), so the offset and the size follow the new scale from here.
        if FS.PetDock and FS.PetDock.Refresh then FS.PetDock.Refresh(true) end
        ApplySlotGeometry(FS.Layout.Scale())
        return
    end
    if container:IsShown() then
        FS.Layout.Apply(container, "petcontainer")
    end
    -- Layout.lua's own layoutWatcher already re-seated `container` to
    -- the design default via its `_applied` bookkeeping BEFORE this
    -- callback runs (see FS.Layout._applied in Layout.lua), regardless
    -- of shown state -- so any saved per-player drag position has to be
    -- re-asserted here too, unconditionally, or a UI_SCALE_CHANGED /
    -- DISPLAY_SIZE_CHANGED event silently discards it live (it would
    -- still be correct on disk, just not applied until the next
    -- /reload). Not gated on IsShown() for the same reason the stomp
    -- above isn't.
    ApplySavedPosition()
    -- Slot heights/gaps are literal scaled-pixel values, not
    -- automatic like a plain SetPoint offset, so they need their own
    -- recompute on every rescale regardless of shown state.
    ApplySlotGeometry(FS.Layout.Scale())
end

-- The only place dragHandle's EnableMouse is toggled. Gated on
-- InCombatLockdown per the file header's implicit-protection note (Phase 5
-- will make this container's Show()/Hide()/SetAttribute combat-restricted,
-- and EnableMouse on a child of an implicitly-protected frame is the same
-- restricted family) -- a toggle requested mid-combat (from SetLocked below,
-- called by the /fspet slash command) is deferred to PLAYER_REGEN_ENABLED
-- via `pendingLockApply` rather than silently dropped.
local function ApplyLockState()
    if InCombatLockdown() then
        pendingLockApply = true
        return
    end
    pendingLockApply = false
    if dragHandle then
        dragHandle:EnableMouse(not locked and not docked)
    end
end

local function SetLocked(value)
    locked = value and true or false
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.petFrame = ForeverSynthwaveDB.petFrame or {}
    ForeverSynthwaveDB.petFrame.locked = locked
    ApplyLockState()
    print(("|cff22e0ffForever STUwave|r: pet frame %s."):format(locked and "locked" or "unlocked"))
end

function FS.PetFrame.IsLocked()
    return locked
end

-- Restores the container to its design-default position (FS.Layout's own
-- "petcontainer" entry), clearing any saved per-player drag override. The
-- SetPoint FS.Layout.Apply performs is combat-restricted the moment barSlot's
-- secure pet-action buttons exist (Phase 5, same restricted family as
-- ApplyRescale/ApplyLockState above), so a reset requested mid-combat just
-- flags itself here and is re-applied for real once PLAYER_REGEN_ENABLED
-- fires, exactly like pendingLockApply/pendingRescale.
local function ApplyDefaultPosition()
    if InCombatLockdown() then
        pendingReset = true
        return
    end
    pendingReset = false
    -- Docked, the saved position is already cleared and the float seat is applied when the panel next
    -- floats (SeatFloat); re-seating now would pull it off the Console.
    if docked then return end
    FS.Layout.Apply(container, "petcontainer")
end

-- PetDock.lua's two seats (it decides, this file owns the container). Both run out of combat only:
-- the container is implicitly protected (it parents the secure pet buttons), so a SetPoint or SetSize
-- on it is blocked in combat; in combat they return false and change nothing, and PetDock asks again
-- at PLAYER_REGEN_ENABLED.
--
-- SeatDocked stands the panel on `anchor` (the Console chassis): its BOTTOMLEFT on the anchor's
-- TOPLEFT, `dx` UI units right. The container leaves Layout.lua's re-seat list, whose watcher would
-- otherwise pull it back to the float seat on every rescale (PetDock re-docks from the rescale
-- callback instead). Drag is off while docked; a saved drag position is left alone for when it floats.
function FS.PetFrame.SeatDocked(anchor, dx)
    if not (container and anchor) or InCombatLockdown() then return false end
    local seat = FS.Layout.petcontainer
    local scale = FS.Layout.Scale()
    container:ClearAllPoints()
    container:SetPoint("BOTTOMLEFT", anchor, "TOPLEFT", dx or 0, 0)
    container:SetSize(seat.w * scale, seat.h * scale)
    FS.Layout._applied[container] = nil
    docked = true
    ApplyLockState()
    return true
end

-- SeatFloat puts the panel back at its float position (the layout seat, or the saved drag position
-- over it) and Layout.lua's re-seat list, and gives the drag handle back.
function FS.PetFrame.SeatFloat()
    if not container or InCombatLockdown() then return false end
    docked = false
    FS.Layout.Apply(container, "petcontainer")
    ApplySavedPosition()
    ApplyLockState()
    return true
end

function FS.PetFrame.IsDocked()
    return docked
end

local function ResetPosition()
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.petFrame = ForeverSynthwaveDB.petFrame or {}
    ForeverSynthwaveDB.petFrame.pos = nil
    ApplyDefaultPosition()
    if pendingReset then
        print("|cff22e0ffForever STUwave|r: pet frame position reset queued; applies once combat ends.")
    else
        print("|cff22e0ffForever STUwave|r: pet frame position reset.")
    end
end

-- Mirrors ActionBars.lua's /fstaint idiom exactly: lowercase + strip
-- whitespace, dispatch on the recognized words, and print current state on
-- no/bad input rather than silently doing nothing.
SLASH_FSPET1 = "/fspet"
SlashCmdList["FSPET"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")
    if msg == "lock" then
        SetLocked(true)
    elseif msg == "unlock" then
        SetLocked(false)
    elseif msg == "reset" then
        ResetPosition()
    else
        print("|cff22e0ffForever STUwave|r: /fspet lock | unlock | reset   (currently "
            .. "|cffff2e97" .. (locked and "locked" or "unlocked") .. "|r)")
    end
end

-- A SEPARATE insecure overlay frame rather than making `container` itself
-- draggable: `container` will parent secure buttons in Phase 5 and become
-- implicitly protected, and an insecure hit-region child stays simple to
-- reason about regardless of what protection level its parent ends up at.
-- No visible texture -- invisible hit-region only, per spec (no dashes).
local function BuildDragHandle()
    dragHandle = CreateFrame("Frame", nil, container)
    dragHandle:SetAllPoints(container)
    dragHandle:RegisterForDrag("LeftButton")

    -- StartMoving/StopMovingOrSizing are themselves restricted on an
    -- implicitly-protected frame (same family as Show/Hide/SetAttribute),
    -- so both handlers gate on InCombatLockdown too, not just the mouse
    -- being disabled -- belt and suspenders against a drag that started
    -- just before combat locked down.
    dragHandle:SetScript("OnDragStart", function()
        if InCombatLockdown() or locked then return end
        container:StartMoving()
    end)
    dragHandle:SetScript("OnDragStop", function()
        if InCombatLockdown() then return end
        container:StopMovingOrSizing()
        SavePosition()
    end)

    container:SetMovable(true)
    FS.PetFrame.dragHandle = dragHandle   -- for the harness
end

-------------------------------------------------------------------------------
-- Visibility state machine
-------------------------------------------------------------------------------

-- PetHasActionBar may not exist on this client; feature-detected exactly
-- like PetActionBar.lua's own HAS_PET_HAS_ACTION_BAR. C_ActionBar.HasPetActionButtons
-- is a second, less-established fallback tried only if the first is absent,
-- before defaulting to true-if-pet-exists like PetActionBar.lua does.
local HAS_PET_HAS_ACTION_BAR = type(PetHasActionBar) == "function"
local HAS_C_ACTIONBAR_PET_BUTTONS = type(C_ActionBar) == "table"
    and type(C_ActionBar.HasPetActionButtons) == "function"

local function HasPetBar()
    if HAS_PET_HAS_ACTION_BAR then
        local ok, has = pcall(PetHasActionBar)
        if ok then return has and true or false end
    end
    if HAS_C_ACTIONBAR_PET_BUTTONS then
        local ok, has = pcall(C_ActionBar.HasPetActionButtons)
        if ok then return has and true or false end
    end
    return true
end

-- UnitIsDead/UnitIsFeignDeath's secrecy on the "pet" unit token is
-- UNVERIFIED on this client. FS.IsSecret is checked FIRST, before either
-- value is boolean-tested, per Theme.lua's own secret-value guard contract.
-- If either read comes back secret, this does NOT treat the pet as dead from
-- that read -- it falls back to false (not dead) and leans on the
-- event-driven hide (PET_BAR_UPDATE fires when a pet's actionable state
-- changes, UNIT_FLAGS fires on unit state changes including death) instead
-- of a per-call truth-test on a possibly-secret value. This is a real
-- architectural constraint, not a stylistic choice: a wrong per-call
-- truth-test on a secret throws, an uncaught throw here would abort the
-- whole visibility gate every single caller depends on.
local function IsPetDead()
    local dead = UnitIsDead("pet")
    local feign = UnitIsFeignDeath("pet")
    if FS.IsSecret(dead) or FS.IsSecret(feign) then
        return false
    end
    return (dead and true or false) or (feign and true or false)
end

local function ShouldShow()
    if not UnitExists("pet") then return false end
    if not HasPetBar() then return false end
    if IsPetDead() then return false end
    return true
end

-- The real show/hide driver, mirroring PetActionBar.lua's RequestBuild:
-- Show()/Hide() are combat-restricted the moment this container parents
-- secure buttons (Phase 5, not yet), so SetAlpha is the in-combat stand-in
-- (not itself combat-restricted), reconciled to a real Show()/Hide() on
-- PLAYER_REGEN_ENABLED. Every event handler below funnels into this one
-- gate -- Phases 4/5/6 (cast bar, action buttons, status text) hook into
-- this same gate rather than each re-deriving visibility.
local function Apply()
    if not container then return end
    local show = ShouldShow()

    if InCombatLockdown() then
        -- SetAlpha is the only call made on the container here. EnableMouse is blocked in combat too
        -- (ADDON_ACTION_BLOCKED on FSPetContainer:EnableMouse(), seen live): the container parents the
        -- secure pet buttons, so it is implicitly protected and the client refuses every restricted
        -- call on it, not only Show/Hide/SetPoint. The container needs no mouse of its own (it is
        -- switched off once at build), so the container itself swallows no world clicks while the
        -- panel waits at alpha 0 for PLAYER_REGEN_ENABLED, where the real Hide below ends it. Its
        -- children still take mouse at alpha 0: in float mode with the panel unlocked the drag handle
        -- (EnableMouse(true), see ApplyLockState) covers the rect, and the secure pet buttons are
        -- mouse-enabled at any alpha.
        container:SetAlpha(show and 1 or 0)
        -- PetDock's gap patch in the Console's top line follows the panel by ALPHA, which is legal
        -- here, so a pet dying (or summoned) in combat closes (or reopens) the hole at once.
        if FS.PetDock and FS.PetDock.SetPetShown then FS.PetDock.SetPetShown(show) end
        return
    end

    container:SetAlpha(1)
    if show then
        container:Show()
    else
        container:Hide()
    end
    -- PetDock keeps the Console's top line whole while the panel is not there (a gap patch whose alpha
    -- tracks this answer; the combat branch above reports it too) and re-docks out of combat.
    if FS.PetDock and FS.PetDock.SetPetShown then FS.PetDock.SetPetShown(show) end
end

-------------------------------------------------------------------------------
-- Native pet-bar suppression
-------------------------------------------------------------------------------

-- PetFrame.lua is the SOLE owner of Blizzard pet bar suppression
-- (PetActionBar / PetActionButton1-10 / PetActionBarButtonContainer1-10);
-- PetActionBar.lua does not suppress anything. Uses DimBlizzardFrame rather
-- than Hide()+HookScript to avoid the Edit Mode taint (see
-- FrameHelpers.DimBlizzardFrame and CLAUDE.md's FrameHelpers entry).
local function SuppressBlizzardPetBar()
    if InCombatLockdown() then return end
    if _G.PetActionBar then
        FS.FrameHelpers.DimBlizzardFrame(_G.PetActionBar)
    end
    for i = 1, 10 do
        local button = _G["PetActionButton" .. i]
        if button and button.EnableMouse then
            button:EnableMouse(false)
        end
        local buttonContainer = _G["PetActionBarButtonContainer" .. i]
        if buttonContainer and buttonContainer.EnableMouse then
            buttonContainer:EnableMouse(false)
        end
    end
end

-------------------------------------------------------------------------------
-- Status readout (Phase 4)
-------------------------------------------------------------------------------

-- Name row, health rail and power rail (FrameHelpers.CreateLaserRail) built into
-- FS.PetFrame.statusSlot, the mockup's peStatusDc: a 9 high name row (name left, plain
-- muted "LV n" text right), then a 7 high health rail and a 7 high power rail, ROW_GAP
-- and RAIL_PAIR_GAP apart. Sizes and anchors are all seated by ApplySlotGeometry (they
-- are scaled pixels); only the structure is built here.
local function BuildStatus()
    local scale = FS.Layout.Scale()
    local function StyleValueText(fontString)
        ApplyFontGeneric(fontString, FONT_MONO, VALUE_FONT_SIZE * scale, nil, "OUTLINE")
    end

    healthBar = FS.FrameHelpers.CreateLaserRail(statusSlot, {
        coreHeight = RAIL_CORE_HEIGHT * scale,
        bloomSize = RAIL_BLOOM_SIZE * scale,
        sparkWidth = RAIL_SPARK_SIZE * scale,
        sparkHeight = RAIL_SPARK_SIZE * scale,
        color = COLOR_HEALTH,
        styleText = StyleValueText,
    })

    powerBar = FS.FrameHelpers.CreateLaserRail(statusSlot, {
        coreHeight = RAIL_CORE_HEIGHT * scale,
        bloomSize = RAIL_BLOOM_SIZE * scale,
        sparkWidth = RAIL_SPARK_SIZE * scale,
        sparkHeight = RAIL_SPARK_SIZE * scale,
        color = COLOR_POWER,
        styleText = StyleValueText,
    })

    -- The name row: a plain frame across the top of the block, holding the name and the
    -- level text. The health rail hangs ROW_GAP under it (ApplySlotGeometry).
    nameRow = CreateFrame("Frame", nil, statusSlot)

    -- The level, the mockup's plain muted "LV n" text at the row's right end: no chip, no
    -- plate (the console dock draws none), set in the muted token like the party's LV text.
    levelText = nameRow:CreateFontString(nil, "OVERLAY")
    levelText:SetJustifyH("RIGHT")
    levelText:SetJustifyV("MIDDLE")
    ApplyMono(levelText, LEVEL_FONT_SIZE * scale, COLOR_MUTED)

    -- Name fills the row to the left of the level text rather than a fixed-width guess,
    -- so it never overlaps the level regardless of digit count.
    nameText = nameRow:CreateFontString(nil, "OVERLAY")
    nameText:SetJustifyH("LEFT")
    ApplyFontGeneric(nameText, FONT_MONO, NAME_FONT_SIZE * scale, nil, "OUTLINE")
    -- A space-separated pet name otherwise wraps onto a second line outside the row.
    nameText:SetWordWrap(false)
    if nameText.SetNonSpaceWrap then nameText:SetNonSpaceWrap(false) end
    if nameText.SetMaxLines then nameText:SetMaxLines(1) end
    nameText:SetJustifyV("MIDDLE")

    FS.PetFrame.healthBar = healthBar
    FS.PetFrame.powerBar = powerBar
    FS.PetFrame.nameRow = nameRow
    FS.PetFrame.nameText = nameText
    FS.PetFrame.levelText = levelText
end

-- UnitHealthMax("pet")/UnitPowerMax("pet") are SECRET on this client, exactly
-- like UnitHealth("pet")/UnitPower("pet") -- "pet" is a non-player unit, and
-- max is not exempt here despite being exempt for some other non-player
-- cases elsewhere in this addon. Confirmed in-game (2026-09-26): the prior
-- version of this function did `local max = UnitHealthMax("pet") or 0; if
-- max <= 0 then max = 1 end`, and the `<= 0` comparison threw "attempt to
-- compare local 'max' (a secret number value...)", aborting pet UI
-- construction entirely. SetMinMaxValues/SetValue both accept a secret
-- argument directly -- the sanctioned setter path this addon uses everywhere
-- a secret health/power value has to reach a StatusBar (see UnitFrames.lua's
-- UpdateHealthBar/UpdatePowerBar) -- so every value here goes straight from
-- the API call to the setter with NO intermediate `or`/comparison/arithmetic
-- of any kind: `or` boolean-tests its left operand, and `<=`/comparison also
-- throws, and both are illegal on a secret.
--
-- The same rule covers the printed numbers (option C prints both bars' "cur / max" text): the
-- two values go from the API into SetFormattedText, a sanctioned engine setter
-- (UnitFrames.lua does the identical write for the player frame), never through
-- tostring or arithmetic. It is pcall'd, and the first refusal latches the text off and
-- logs once, so a client that rejects a secret there degrades to bars with no numbers.
local valueTextBroken = false

local function WriteValueText(bar, cur, max)
    if valueTextBroken or not bar.text then return end
    if pcall(bar.text.SetFormattedText, bar.text, "%d / %d", cur, max) then return end
    valueTextBroken = true
    healthBar.text:SetText("")
    powerBar.text:SetText("")
    if redHealthBar then redHealthBar.text:SetText("") end
    FS.LogDegradeOnce("petframe_value_text",
        "|cffff4488Forever STUwave|r: pet HP/mana numbers disabled, SetFormattedText rejected the value.")
end

-------------------------------------------------------------------------------
-- Low HP (step S7): a red name, a red HP rail and a red edge
-------------------------------------------------------------------------------

-- The mockup's low state (drawPet's dc branch): a red pulsing edge, a red name, a red HP rail.
-- Pet health is SECRET in combat, so Lua never computes cur/max for this. A Step curve (alpha 1
-- from 0 up to LOW_HP_FRACTION, 0 above) is evaluated engine-side by UnitHealthPercent and its
-- result goes straight to SetAlpha on the red layer: the red name, a red twin of the HP rail
-- (a second laser rail in COLOR_RED, fed the same SetMinMaxValues/SetValue) and the red edge
-- host. The INVERSE Step curve (a second UnitHealthPercent call, since a secret alpha cannot be
-- inverted in Lua) drives the normal name, the normal HP rail and any base edge frame, so low
-- reads red only and the two layers crossfade. The pulse is an Alpha AnimationGroup on a CHILD
-- of the edge host: a child's alpha multiplies its parent's, so the pulse never fights the
-- curve. Same pattern as PartyFrames' UpdateRowLowHealth and FrameHelpers.UpdateCaretFull: both
-- calls pcall'd, `type()` rather than a truth test on the possibly-secret result, and the first
-- failure latches (logged once, since LogDegradeOnce does not dedupe) so every later call takes
-- the fallback. SetAlpha taking the secret curve result is documented but not yet seen in game: the
-- 12.1.0 API docs mark Region:SetAlpha SecretArguments="AllowedWhenTainted" with the Alpha secret
-- aspect, and the latch above is the safety net if 16001 disagrees.
--
-- Fallback, with no curve API or after the latch: a plain cur / max compare, legal ONLY when
-- neither value is secret (IsSecret first); otherwise red stays 0 and the normal layer stays 1.
-- A dismissed or dead pet forces red to 0 without reading health at all (a corpse's 0% would
-- read as critically low).
--
-- Every frame here is a non-secure child (the secure pet buttons live under barSlot, not in
-- this layer), so the alpha writes are legal in combat; `container` itself is never touched.
-- PetDock owns the final edge art: FS.PetDock.AttachLowHealth hands this layer its red edge and
-- normal edge through SetLowHealthEdge. Only a PetFrame with no PetDock (petframe-harness runs it
-- alone), or one whose PetDock attached nothing, builds the fallback edge: a ring plus glow on the
-- container rect (EnsureLowHealthEdge), one level above the container and below the slots.
local UpdatePetLowHealth, BuildLowHealth, EnsureLowHealthEdge
do
    local HAS_STEP_CURVE_API = type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
        and type(Enum) == "table" and type(Enum.LuaCurveType) == "table"
        and Enum.LuaCurveType.Step ~= nil
    local HAS_UNIT_HEALTH_PERCENT = type(UnitHealthPercent) == "function"

    -- Alpha `from` up to the threshold, `to` above it.
    local function BuildCurve(from, to)
        local curve = C_CurveUtil.CreateCurve()
        curve:SetType(Enum.LuaCurveType.Step)
        curve:AddPoint(0, from)
        curve:AddPoint(LOW_HP_FRACTION + LOW_HP_EPSILON, to)
        return curve
    end

    local LOW_CURVE, BASE_CURVE
    local lowBroken = false
    local warnedLow = false
    if HAS_UNIT_HEALTH_PERCENT and HAS_STEP_CURVE_API then
        local ok, low = pcall(BuildCurve, 1, 0)
        local okBase, base = pcall(BuildCurve, 0, 1)
        if ok and okBase then
            LOW_CURVE, BASE_CURVE = low, base
        else
            lowBroken = true  -- logged by the first update, through the same latch
        end
    end

    local edgeHost       -- the frame whose alpha is the red curve (the red edge)
    local edgeBase = {}  -- extra frames on the inverse curve (a base edge), PetDock's
    local pulseGroup     -- the AnimationGroup EnsurePulse keeps playing

    local function SetAlphaTo(target, alpha)
        return pcall(target.SetAlpha, target, alpha)
    end

    -- `low` drives the red layer, `base` the normal one. False when any setter refused.
    local function ApplyLowAlpha(low, base)
        local ok = SetAlphaTo(redName, low)
        ok = SetAlphaTo(redHealthBar.shell, low) and ok
        ok = SetAlphaTo(edgeHost, low) and ok
        ok = SetAlphaTo(nameText, base) and ok
        ok = SetAlphaTo(healthBar.shell, base) and ok
        for i = 1, #edgeBase do
            ok = SetAlphaTo(edgeBase[i], base) and ok
        end
        return ok
    end

    -- A hidden panel may stop its AnimationGroups; replay the pulse whenever the layer updates
    -- (cheap: one IsPlaying read), so it is running whenever red can show.
    local function EnsurePulse()
        if pulseGroup and not pulseGroup:IsPlaying() then
            pcall(pulseGroup.Play, pulseGroup)
        end
    end

    function UpdatePetLowHealth()
        if not (healthBar and redHealthBar and edgeHost) then return end

        -- Gone or dead: red 0, normal 1, no health read.
        if not UnitExists("pet") or IsPetDead() then
            ApplyLowAlpha(0, 1)
            return
        end
        EnsurePulse()

        if LOW_CURVE and not lowBroken then
            local ok, lowAlpha = pcall(UnitHealthPercent, "pet", false, LOW_CURVE)
            local okBase, baseAlpha = pcall(UnitHealthPercent, "pet", false, BASE_CURVE)
            if ok and okBase and type(lowAlpha) == "number" and type(baseAlpha) == "number"
                and ApplyLowAlpha(lowAlpha, baseAlpha) then
                return
            end
            lowBroken = true
        end
        if lowBroken and not warnedLow then
            warnedLow = true
            FS.LogDegradeOnce("petframe_lowhp_curve",
                "|cffff4488Forever STUwave|r: pet low-HP curve refused, falling back to a plain compare")
        end

        local cur, max = UnitHealth("pet"), UnitHealthMax("pet")
        local low = false  -- unknown (secret) health: red stays 0 and the normal layer stays 1
        if not FS.IsSecret(cur) and not FS.IsSecret(max) and type(cur) == "number"
            and type(max) == "number" and max > 0 then
            low = cur / max <= LOW_HP_FRACTION
        end
        ApplyLowAlpha(low and 1 or 0, low and 0 or 1)
    end

    local function IsAlphaFrame(frame)
        return type(frame) == "table" and type(frame.SetAlpha) == "function"
    end

    -- Hands the red edge (and the frames that fade with the inverse curve) to another owner,
    -- PetDock's final edge art. `edge` is any frame with SetAlpha; `base` is a list of such
    -- frames; `pulse` is an optional AnimationGroup kept playing. The previous edge goes to
    -- alpha 0 and hides, its base frames back to alpha 1, and the new targets are driven at
    -- once. Returns false and changes nothing for an edge that cannot take an alpha.
    function FS.PetFrame.SetLowHealthEdge(edge, base, pulse)
        if not IsAlphaFrame(edge) then return false end
        local oldEdge, oldBase, oldPulse = edgeHost, edgeBase, pulseGroup
        edgeHost, edgeBase, pulseGroup = edge, {}, nil
        for i = 1, #(base or {}) do
            if IsAlphaFrame(base[i]) then edgeBase[#edgeBase + 1] = base[i] end
        end
        if type(pulse) == "table" and type(pulse.Play) == "function" and type(pulse.IsPlaying) == "function" then
            pulseGroup = pulse
        end
        if oldPulse and oldPulse ~= pulseGroup then pcall(oldPulse.Stop, oldPulse) end
        if oldEdge and oldEdge ~= edge then
            pcall(oldEdge.SetAlpha, oldEdge, 0)
            pcall(oldEdge.Hide, oldEdge)
        end
        for i = 1, #oldBase do pcall(oldBase[i].SetAlpha, oldBase[i], 1) end
        FS.PetFrame.lowEdge = edge
        UpdatePetLowHealth()
        return true
    end

    -- Builds the red twin of the HP rail and the red name (the red edge comes from PetDock, or from
    -- EnsureLowHealthEdge). After BuildStatus (it reads statusSlot, nameRow and the normal rail);
    -- ApplySlotGeometry seats the twins afterwards.
    function BuildLowHealth()
        local scale = FS.Layout.Scale()

        redHealthBar = FS.FrameHelpers.CreateLaserRail(statusSlot, {
            coreHeight = RAIL_CORE_HEIGHT * scale,
            bloomSize = RAIL_BLOOM_SIZE * scale,
            sparkWidth = RAIL_SPARK_SIZE * scale,
            sparkHeight = RAIL_SPARK_SIZE * scale,
            color = COLOR_RED,
            styleText = function(fontString)
                ApplyFontGeneric(fontString, FONT_MONO, VALUE_FONT_SIZE * scale, nil, "OUTLINE")
            end,
        })
        redHealthBar.shell:SetAlpha(0)

        -- The red name: the same text as the name (it may be secret, so it goes straight
        -- through SetText and is never compared), same font and wrap guard, in COLOR_RED.
        redName = nameRow:CreateFontString(nil, "OVERLAY")
        redName:SetJustifyH("LEFT")
        ApplyFontGeneric(redName, FONT_MONO, NAME_FONT_SIZE * scale, COLOR_RED, "OUTLINE")
        redName:SetWordWrap(false)
        if redName.SetNonSpaceWrap then redName:SetNonSpaceWrap(false) end
        if redName.SetMaxLines then redName:SetMaxLines(1) end
        redName:SetJustifyV("MIDDLE")
        redName:SetAlpha(0)

        FS.PetFrame.redName = redName
        FS.PetFrame.redHealthBar = redHealthBar
    end

    -- The fallback red edge: host (the curve alpha) > pulse child (the Alpha animation) > ring and
    -- glow. Built only when no edge has been attached (see the comment above this block), so a
    -- PetDock that attached its own never pays for a ring it would retire at once.
    function EnsureLowHealthEdge()
        if edgeHost then return end
        edgeHost = CreateFrame("Frame", nil, container)
        edgeHost:SetAllPoints(container)
        edgeHost:SetFrameLevel(container:GetFrameLevel() + 1)
        edgeHost:SetAlpha(0)
        local pulseFrame = CreateFrame("Frame", nil, edgeHost)
        pulseFrame:SetAllPoints(edgeHost)
        FS.Theme.SkinButton(pulseFrame, {
            chamfer = FS.Theme.SLICE_CUT_MARGIN,
            glowAlpha = LOW_EDGE_GLOW_ALPHA,
            borderColor = COLOR_RED,
        })
        pulseFrame.fsSkin.border.ring:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], 1)
        pulseFrame.fsSkin.glow:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], LOW_EDGE_GLOW_ALPHA)
        local group = pulseFrame:CreateAnimationGroup()
        group:SetLooping("BOUNCE")
        local pulse = group:CreateAnimation("Alpha")
        pulse:SetFromAlpha(LOW_PULSE_TOP)
        pulse:SetToAlpha(LOW_PULSE_FLOOR)
        pulse:SetDuration(LOW_PULSE_LEG)
        pulse:SetSmoothing("IN_OUT")
        pulseGroup = group

        FS.PetFrame.lowEdge = edgeHost
        FS.PetFrame.lowEdgePulse = pulseFrame
    end
end

local function UpdateStatusHealth()
    if not healthBar then return end
    local cur, max = UnitHealth("pet"), UnitHealthMax("pet")
    healthBar:SetMinMaxValues(0, max)
    healthBar:SetValue(cur)
    WriteValueText(healthBar, cur, max)
    -- The red twin gets the very same values (a secret straight to the setters, no compare).
    if redHealthBar then
        redHealthBar:SetMinMaxValues(0, max)
        redHealthBar:SetValue(cur)
        WriteValueText(redHealthBar, cur, max)
    end
    UpdatePetLowHealth()
end

local function UpdateStatusPower()
    if not powerBar then return end
    local cur, max = UnitPower("pet"), UnitPowerMax("pet")
    powerBar:SetMinMaxValues(0, max)
    powerBar:SetValue(cur)
    WriteValueText(powerBar, cur, max)
    -- Bloom and spark would sit as a stray dot at the left of an empty rail.
    FS.FrameHelpers.UpdatePowerHostEmpty(powerBar.fsRail.host, "pet")

    -- UnitPowerType is not secret, so the table lookup is legal.
    local color = POWER_COLORS[UnitPowerType("pet")] or COLOR_POWER
    FS.FrameHelpers.SetLaserRailColor(powerBar, color[1], color[2], color[3])
end

-- A nil (uncached) name is shown as blank rather than guessed at --
-- UNIT_NAME_UPDATE re-runs this once the client resolves it, same as
-- UnitFrames.lua's own name-fixup path. The name may be secret, and `n or ""`
-- boolean-tests it (illegal on a secret), so the secret test comes first and a
-- secret goes to SetText untouched.
local function UpdateStatusName()
    if not nameText then return end
    local n = UnitName("pet")
    if FS.IsSecret(n) then
        nameText:SetText(n)
        if redName then redName:SetText(n) end
    else
        nameText:SetText(n or "")
        if redName then redName:SetText(n or "") end
    end
end

-- Mirrors UnitFrames.lua's UpdateLevel text convention ("??" for an unknown
-- level), written as "LV n". A secret level is shown blank: it can't be compared or
-- formatted.
local function UpdateStatusLevel()
    if not levelText then return end
    local lvl = UnitLevel("pet")
    if FS.IsSecret(lvl) then
        levelText:SetText("")
        return
    end
    levelText:SetText((lvl and lvl > 0) and ("LV " .. tostring(lvl)) or "LV ??")
end

local function RefreshStatus()
    UpdateStatusHealth()
    UpdateStatusPower()
    UpdateStatusName()
    UpdateStatusLevel()
end

-- The pet unit can resolve a frame after UNIT_PET/PLAYER_ENTERING_WORLD
-- fires, so those two re-run RefreshStatus once more next frame.
local HAS_C_TIMER_AFTER = type(C_Timer) == "table" and type(C_Timer.After) == "function"

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

-- UNIT_FLAGS is registered via SafeRegisterUnitEvent, so the handler still
-- explicitly guards unit == "pet" (defensive/explicit like this addon's
-- other unit-event handlers, even though RegisterUnitEvent already filters).
-- UNIT_PET is a plain RegisterEvent, NOT RegisterUnitEvent, because it fires
-- on the pet's OWNER token ("player"), not "pet" -- same as PetActionBar.lua
-- and UnitFrames.lua both already document for the identical event. Because
-- it fires on the owner token, other members' pets are ignored below.
local function OnEvent(_, event, unit)
    if event == "UNIT_PET" and unit ~= "player" then return end

    if event == "UNIT_FLAGS" then
        if unit ~= "pet" then return end
        Apply()
        -- Death and revival arrive as flags; the low-HP layer reads the same gate.
        UpdatePetLowHealth()
        return
    end

    -- Status readout (Phase 4): each of these is registered via
    -- SafeRegisterUnitEvent("pet"), so the explicit unit guard below is
    -- defensive/explicit like UNIT_FLAGS' own guard above, even though
    -- RegisterUnitEvent already filters. These update VALUES only -- the
    -- container's own visibility gate (Apply(), below) is untouched by any
    -- of them, per this phase's own scope.
    if event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then
        if unit ~= "pet" then return end
        UpdateStatusHealth()
        return
    end

    if event == "UNIT_POWER_UPDATE" or event == "UNIT_MAXPOWER" or event == "UNIT_DISPLAYPOWER" then
        if unit ~= "pet" then return end
        UpdateStatusPower()
        return
    end

    if event == "UNIT_NAME_UPDATE" then
        if unit ~= "pet" then return end
        UpdateStatusName()
        return
    end

    if event == "UNIT_LEVEL" then
        if unit ~= "pet" then return end
        UpdateStatusLevel()
        return
    end

    if event == "PLAYER_REGEN_ENABLED" then
        -- Reconciles the real Show/Hide after combat, re-applies any
        -- drag-lock toggle that happened mid-combat, and re-runs native
        -- suppression in case SuppressBlizzardPetBar's own InCombatLockdown
        -- guard skipped it earlier.
        Apply()
        RefreshStatus()
        if pendingLockApply then
            ApplyLockState()
        end
        -- Reconciles a rescale that landed mid-combat and got deferred by
        -- the OnRescale callback above, same idiom as pendingLockApply.
        if pendingRescale then
            pendingRescale = false
            ApplyRescale()
        end
        -- Reconciles a /fspet reset that landed mid-combat and got deferred,
        -- same idiom as pendingLockApply/pendingRescale.
        if pendingReset then
            ApplyDefaultPosition()
        end
        SuppressBlizzardPetBar()
        return
    end

    -- PET_BAR_UPDATE / UNIT_PET / PLAYER_CONTROL_LOST / PLAYER_CONTROL_GAINED
    -- / PLAYER_ENTERING_WORLD / SPELLS_CHANGED: all re-evaluate the same gate,
    -- and re-read the status values too. A pet at full mana fires no
    -- UNIT_POWER_UPDATE and a summon fires no UNIT_LEVEL, so without this the
    -- power bar sits empty and the level reads "??" until something changes.
    Apply()
    RefreshStatus()
    if HAS_C_TIMER_AFTER and (event == "UNIT_PET" or event == "PLAYER_ENTERING_WORLD") then
        C_Timer.After(0, RefreshStatus)
    end
end

local function RegisterEvents()
    events = CreateFrame("Frame")
    for _, event in ipairs({
        "PET_BAR_UPDATE",
        "UNIT_PET",
        "PLAYER_CONTROL_LOST",
        "PLAYER_CONTROL_GAINED",
        "PLAYER_ENTERING_WORLD",
        "PLAYER_REGEN_ENABLED",
        "SPELLS_CHANGED",
    }) do
        pcall(events.RegisterEvent, events, event)
    end
    FS.FrameHelpers.SafeRegisterUnitEvent(events, "UNIT_FLAGS", "pet", function(ev, err)
        FS.LogDegradeOnce("petframe_unitflags",
            "|cffff4488Forever STUwave|r: failed to register " .. ev
                .. " for pet frame visibility (" .. tostring(err) .. ")")
    end)

    -- Status readout (Phase 4): registered on the SAME events frame as
    -- UNIT_FLAGS above, since OnEvent already dispatches by event name --
    -- no reason for a second frame/listener.
    for _, event in ipairs({
        "UNIT_HEALTH",
        "UNIT_MAXHEALTH",
        "UNIT_POWER_UPDATE",
        "UNIT_MAXPOWER",
        "UNIT_DISPLAYPOWER",
        "UNIT_NAME_UPDATE",
        "UNIT_LEVEL",
    }) do
        FS.FrameHelpers.SafeRegisterUnitEvent(events, event, "pet", function(ev, err)
            FS.LogDegradeOnce("petframe_status_" .. ev,
                "|cffff4488Forever STUwave|r: failed to register " .. ev
                    .. " for pet status readout (" .. tostring(err) .. ")")
        end)
    end

    events:SetScript("OnEvent", OnEvent)
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

local function Build()
    container = CreateFrame("Frame", "FSPetContainer", UIParent)
    FS.Layout.Apply(container, "petcontainer")
    container:Hide()
    -- No mouse of its own, ever: it has no OnEnter or tooltip, the drag handle and the secure pet
    -- buttons (its children) take their own mouse, and EnableMouse is blocked on it in combat, so a
    -- container left mouse-enabled by its last out-of-combat Apply would swallow clicks while
    -- invisible. Only the container is mouse-off: the unlocked float drag handle and the secure pet
    -- buttons still take mouse at alpha 0.
    container:EnableMouse(false)

    -- Per-player drag override, if any, applied before the first Show().
    ApplySavedPosition()

    -- The panel chrome (outline, scrim fill, halo, the red edge twin) is PetDock.lua's. It loads
    -- after this file, so it is read at call time; its children draw below every slot.
    if FS.PetDock then FS.PetDock.Build(container) end

    -- Plain CreateFrame, no chrome/backdrop -- Phases 4/5/6 own their own
    -- slot visuals.
    castSlot = CreateFrame("Frame", nil, container)
    barSlot = CreateFrame("Frame", nil, container)
    statusSlot = CreateFrame("Frame", nil, container)
    -- Strictly above every chrome frame (SLOT_LEVEL_OFFSET); set before any child exists, so each
    -- slot's children (the rails, the cast bar, the secure pet buttons) follow it up.
    local slotLevel = container:GetFrameLevel() + SLOT_LEVEL_OFFSET
    castSlot:SetFrameLevel(slotLevel)
    barSlot:SetFrameLevel(slotLevel)
    statusSlot:SetFrameLevel(slotLevel)
    ApplySlotGeometry(FS.Layout.Scale())

    -- Runtime table fields, not file-scope locals: a later phase's module
    -- reads FS.PetFrame.barSlot etc. directly off the table at call time,
    -- never captures it into its own file-scope local -- this file loads
    -- before PetActionBar.lua per the .toc, but a future phase's module
    -- might load in any order relative to files that aren't this one, so
    -- table-field access is this addon's established safe cross-file
    -- contract (see CLAUDE.md's "Multi-file feature sharing" pattern note).
    FS.PetFrame.container = container
    FS.PetFrame.castSlot = castSlot
    FS.PetFrame.barSlot = barSlot
    FS.PetFrame.statusSlot = statusSlot

    -- Builds the name row, level text and health/power rails into statusSlot, then
    -- seats them: the first ApplySlotGeometry pass above ran before they existed, so
    -- it only placed the slots. Before BuildDragHandle (order between the two doesn't
    -- matter functionally, grouped with the other slot-content construction).
    BuildStatus()
    BuildLowHealth()
    -- The low-HP layer now exists: PetDock hands it its own red edge and normal edge
    -- (SetLowHealthEdge). With no PetDock, or one that attached nothing, the default ring is built.
    if FS.PetDock then FS.PetDock.AttachLowHealth() end
    EnsureLowHealthEdge()
    ApplySlotGeometry(FS.Layout.Scale())

    BuildDragHandle()

    local saved = type(ForeverSynthwaveDB) == "table" and ForeverSynthwaveDB.petFrame
    locked = (saved and saved.locked) and true or false
    ApplyLockState()

    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            -- Per the file header's implicit-protection note: once barSlot
            -- parents secure buttons (Phase 5), `container` becomes
            -- implicitly protected and ApplyRescale's SetPoint/SetHeight
            -- calls become combat-restricted. Rather than let a mid-combat
            -- UI_SCALE_CHANGED / DISPLAY_SIZE_CHANGED throw ADDON_ACTION_BLOCKED,
            -- defer to PLAYER_REGEN_ENABLED like ApplyLockState does above --
            -- nothing secure is parented here yet, but this file is built
            -- combat-safe from day one throughout.
            if InCombatLockdown() then
                pendingRescale = true
                return
            end
            ApplyRescale()
        end)
    end

    RegisterEvents()
    SuppressBlizzardPetBar()
    Apply()
    -- Populates the status readout once at build time, so a pet that
    -- already exists at login shows correct values immediately rather than
    -- waiting on the first UNIT_HEALTH/UNIT_POWER_UPDATE/etc. event.
    RefreshStatus()
end

-- Mirrors PetActionBar.lua's Apply(): a construction-time failure degrades
-- gracefully with no pet UI container built, rather than surfacing as an
-- uncaught addon error at PLAYER_LOGIN/PLAYER_REGEN_ENABLED.
local function Init()
    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: pet frame failed to build ("
            .. tostring(err) .. "); pet UI container not created.")
    end
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to
-- PLAYER_REGEN_ENABLED, mirroring ActionBars.lua/PetActionBar.lua's loader.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    if InCombatLockdown() then
        self:RegisterEvent("PLAYER_REGEN_ENABLED")
        self:SetScript("OnEvent", function(inner)
            inner:UnregisterEvent("PLAYER_REGEN_ENABLED")
            Init()
        end)
        return
    end
    Init()
end)
