-- Forever STUwave: Unit Frames
-- Custom PLAYER, TARGET, FOCUS, and five BOSS unit frames built on
-- SecureUnitButtonTemplate, replacing Blizzard's default frames rather than
-- recoloring them. There is no custom pet frame here; the pet UI lives in
-- PetFrame.lua/PetActionBar.lua/PetCastBar.lua.
-- This is interface 16001 (a 12.0-era modern engine), so most C_*
-- namespaces exist; every possibly-missing API is feature-detected at the
-- call site rather than gated on a version/build check.
--
-- DEFERRED (not built this pass):
--   - rounded corners (needs a proper 9-slice backdrop, next cycle)
--   - the CRT scanline overlay
-- Both frames are fully usable without them.

local _, FS = ...

-- Chrome helpers/constants shared with future component skins live in
-- Theme.lua (loaded immediately before this file, see the .toc); localized
-- here for call-site brevity.
local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local AddOuterGlow = FS.Theme.AddOuterGlow
local AddRoundedFill = FS.Theme.AddRoundedFill
local AddGradientBorder = FS.Theme.AddGradientBorder
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE
local PANEL_RADIUS = FS.Theme.PANEL_RADIUS
local COLOR_BG = FS.Theme.COLOR_BG
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_BAR_BORDER = FS.Theme.COLOR_BAR_BORDER
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_HEAL = FS.Theme.COLOR_HEAL
local FONT_ORBITRON = FS.Theme.FONT_ORBITRON
local FLAT_TEXTURE = FS.Theme.FLAT_TEXTURE
local HATCH_TEXTURE = FS.Theme.HATCH_TEXTURE
local COLOR_CARET_HEALTH = FS.Theme.COLOR_CARET_HEALTH
local COLOR_CARET_POWER = FS.Theme.COLOR_CARET_POWER

-- Dim a Blizzard default frame that is also an Edit Mode system the
-- sanctioned way: kill its events, alpha it to 0, disable its mouse. Must
-- run out of combat. Shared implementation lives in FrameHelpers.lua
-- (FS.FrameHelpers).
local DimBlizzardFrame = FS.FrameHelpers.DimBlizzardFrame

-------------------------------------------------------------------------------
-- Palette (locked mockup values)
-------------------------------------------------------------------------------

local COLOR_REACTION_FRIEND  = { 0.224, 1, 0.078, 1 }        -- #39ff14
local COLOR_REACTION_NEUTRAL = { 0.918, 1, 0, 1 }            -- #eaff00
local COLOR_REACTION_HOSTILE = { 1, 0.027, 0.227, 1 }        -- #ff073a
-- Solid bright green (was translucent 0.35) per Parker's in-game review:
-- "incoming heals work and shields work but the art is not like the mockup."
-- COLOR_HEAL is the same #39ff14 the mockup's --green uses.
local COLOR_HEAL_OVERLAY     = { COLOR_HEAL[1], COLOR_HEAL[2], COLOR_HEAL[3], 0.92 }
-- White tint for the absorb overlay's hatch texture (see health.absorbOverlay
-- construction below): the texture's own alpha carries the diagonal-stripe
-- pattern, this just keeps the stripes bright rather than flat-tinting a
-- solid rectangle the way the old translucent-white shield did.
local COLOR_ABSORB_OVERLAY   = { 1, 1, 1, 0.9 }

-- Dead/ghost/offline state treatment (UpdateHealthBar). Grey, not an alert
-- color; mirrors PartyFrames.lua's own STATE_* constants so a dead/offline
-- target and a dead/offline party row read the same way. Kept local per this
-- addon's "game-semantic values stay local to their module" pattern rather
-- than promoted to Theme.lua.
local STATE_BAR_COLOR    = { 0.35, 0.35, 0.35, 1 }
local STATE_ROW_ALPHA    = 0.55
local STATE_DEAD_TEXT    = "Dead"
local STATE_GHOST_TEXT   = "Ghost"
local STATE_OFFLINE_TEXT = "Offline"

local GLOW_TEXTURE      = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\glow_round.tga"

-- Square 256x256 class-icon atlas. CLASS_ICON_TCOORDS is cut for this square
-- sheet, not the circular "UI-Classes-Circles" atlas -- that one rendered the
-- icon as a circle regardless of the tcoord crop. Confirmed in-game on interface 16001.
local CLASS_ICON_ATLAS = "Interface\\WorldStateFrame\\Icons-Classes"

-------------------------------------------------------------------------------
-- Layout constants
-------------------------------------------------------------------------------

local PANEL_WIDTH     = 260
local PAD_X            = 6 -- mock: .frame padding 5px 6px (horizontal)
local PAD_Y            = 5 -- (vertical)
local BORDER_THICK     = 2
local NAME_ROW_HEIGHT  = 22
local HEALTH_HEIGHT    = 16
local POWER_HEIGHT     = 16 -- same as health per the locked design; paired with the 11pt bar font below (was 14/14) -- a 16px bar reads fine at 11pt, it was only cramped at 14pt
local NAME_GAP         = 3 -- mock: .namerow margin-bottom (name row -> first bar)
local BAR_GAP          = 6 -- mock: .bars gap (between the two bars)
local PANEL_HEIGHT     = PAD_Y * 2 + NAME_ROW_HEIGHT + NAME_GAP + HEALTH_HEIGHT + BAR_GAP + POWER_HEIGHT
local PANEL_HEIGHT_NO_POWER = PANEL_HEIGHT - POWER_HEIGHT - BAR_GAP -- power bar hidden (unit has no power type)

-------------------------------------------------------------------------------
-- Feature detection (module scope, checked once)
-------------------------------------------------------------------------------

local HAS_INCOMING_HEALS = type(UnitGetIncomingHeals) == "function"
local HAS_TOTAL_ABSORBS = type(UnitGetTotalAbsorbs) == "function"
local HAS_CLASS_ICON_TCOORDS = type(CLASS_ICON_TCOORDS) == "table"
local HAS_RAID_CLASS_COLORS  = type(RAID_CLASS_COLORS) == "table"
local HAS_C_TIMER = type(C_Timer) == "table" and type(C_Timer.After) == "function"
local HAS_GET_UNIT_NAME = type(GetUnitName) == "function"
local unitHasPowerType = _G["UnitHasPowerType"]
local HAS_UNIT_HAS_POWER_TYPE = type(unitHasPowerType) == "function"
local POWER_TYPE_MANA = (Enum and Enum.PowerType and Enum.PowerType.Mana) or 0

-- Raid-target-marker feature detection (UpdateRaidMarker, below). Same pair
-- Nameplates.lua's nameplate raid marker already checks.
local HAS_GET_RAID_TARGET_INDEX = type(GetRaidTargetIndex) == "function"
local HAS_RAID_TARGET_TEXTURE_SETTER = type(SetRaidTargetIconTexture) == "function"

-- Warned once per session (mirrors StanceBar.lua's warnedNoCooldownApi
-- pattern), not once per frame built: five-plus unit frames share this flag
-- so a missing UnitGetTotalAbsorbs prints exactly one chat line, not one per
-- frame constructed.
local warnedNoTotalAbsorbs = false

-- Dead/ghost/offline predicates (UpdateHealthBar, below, via
-- IsUnitOffline/IsUnitDeadOrGhost/IsUnitGhost). Mirrors PartyFrames.lua's own
-- feature-detection comment: the out-of-combat secret-value audit found
-- these three PLAIN (not on the health/power/absorbs/range secret list) for
-- player/target/pet, but in-combat secrecy is UNVERIFIED here, so every call
-- site still runs the result through FS.IsSecret before truth-testing it
-- rather than trusting the audit alone.
local HAS_UNIT_IS_DEAD_OR_GHOST = type(UnitIsDeadOrGhost) == "function"
local HAS_UNIT_IS_GHOST = type(UnitIsGhost) == "function"
local HAS_UNIT_IS_CONNECTED = type(UnitIsConnected) == "function"

-- Bounded one-shot retry for UpdateWatchedUnitName's uncached-name case (see
-- below): 0.2s is generous enough for the server round trip that resolves an
-- uncached player's name. The budget is keyed to the unit's GUID, not the
-- frame, so a re-target inside the delay starts a fresh budget for the new
-- unit instead of colliding with the old one's in-flight timer.
local NAME_RETRY_DELAY = 0.2
local NAME_RETRY_MAX_ATTEMPTS = 3

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local function Colorize(text, r, g, b)
    return string.format("|cff%02x%02x%02x%s|r",
        math.floor(r * 255 + 0.5), math.floor(g * 255 + 0.5), math.floor(b * 255 + 0.5), text)
end

local function ApplyOrbitron(fontString, size, color)
    ApplyFontGeneric(fontString, FONT_ORBITRON, size, color)
end

-- Radial glow primitive for small ROUND elements only (class icon, level
-- badge) -- a glow_round.tga texture, ADD blend, tinted (r,g,b,alpha),
-- anchored to `region` inset NEGATIVE by `inset` on all sides so it blooms
-- OUTSIDE the region rather than over it. The panel's own outward glow and
-- the bars use different mechanisms (see AddOuterGlow; bars have no glow at
-- all) since a stretched radial texture reads as a rectangular box on
-- anything wider or taller than it is round.
-- `region` may be a Frame-like object (StatusBar/Frame/Button -- anything
-- that can own a texture) or a plain Texture/FontString region (which can't
-- own a texture itself), in which case the glow is created on its parent and
-- anchored to the region's own edges.
local function AddSoftGlow(region, r, g, b, alpha, inset)
    local owner = region.CreateTexture and region or region:GetParent()
    local glow = owner:CreateTexture(nil, "BACKGROUND")
    glow:SetTexture(GLOW_TEXTURE)
    glow:SetPoint("TOPLEFT", region, "TOPLEFT", -inset, inset)
    glow:SetPoint("BOTTOMRIGHT", region, "BOTTOMRIGHT", inset, -inset)
    glow:SetBlendMode("ADD")
    glow:SetVertexColor(r, g, b, alpha)
    return glow
end

-------------------------------------------------------------------------------
-- Bar building blocks
-------------------------------------------------------------------------------

-- SetDesaturated is a Texture method, not a global, so this is a per-call
-- existence check rather than a module-level HAS_ flag (same caution as
-- PartyFrames.lua's own copy of this helper).
local function SetBarDesaturated(bar, desaturated)
    local tex = bar:GetStatusBarTexture()
    if tex and tex.SetDesaturated then
        tex:SetDesaturated(desaturated)
    end
end

-- Outer bar shell: cut-corner (TOP-LEFT and BOTTOM-RIGHT; round under the A/B
-- flag) track/border/glow chrome at Theme.CutSize(height). Delegates to the
-- shared pill-bar builder in FrameHelpers.lua (FS.FrameHelpers.CreatePillBar).
local function CreateStatBar(parent, height, color, fontSize)
    return FS.FrameHelpers.CreatePillBar(parent, {
        height = height,
        fillColor = color,
        borderColor = COLOR_BAR_BORDER,
        styleText = function(text) ApplyMono(text, fontSize or 14) end,
    })
end

-- Pulsing leading-edge caret: a 3px colored line (health green, power pink,
-- via the color argument passed to the shared builder), full bar height,
-- with a gentle alpha pulse and no glow. Rides
-- bar:GetStatusBarTexture()'s RIGHT edge, which the engine repositions from
-- the (secret) value, so no cur/max fraction is ever computed here. The one
-- tradeoff: at full value the caret sits at the far-right edge instead of
-- hiding (UpdateCaretFull below papers over this by hiding it outright at
-- 100%), which is cosmetic and secret-safe. Delegates to the shared builder
-- in FrameHelpers.lua (FS.FrameHelpers.CreateCaret), which also documents the
-- bar+2 host-frame-level reasoning.
local CreateCaret = FS.FrameHelpers.CreateCaret

-- Shared 12.0 secret-value guard (see Theme.lua); FS is captured above.
local IsSecret = FS.IsSecret

-- Secret-safe overlay bar (incoming heal / absorb shield): a StatusBar CHILD
-- of the health bar, driven only through whitelisted engine setters
-- (SetMinMaxValues/SetValue accept secret args -- the same mechanism the
-- health bar's own fill already relies on in UpdateHealthBar below), so it
-- renders correctly even though `max`/the overlay's own value are secret on
-- every unit but "player". No cur/max fraction is ever computed in Lua: its
-- LEFT edge rides `anchorTexture`'s RIGHT edge, a LIVE frame-relative anchor
-- that the engine repositions on its own -- exactly the technique CreateCaret
-- above already uses for the caret's position. `anchorTexture` is the health
-- bar's own fill texture for the first overlay in the chain (heal), or the
-- PREVIOUS overlay's fill texture to chain a second one after it (absorb
-- after heal), so multiple overlays stack left-to-right automatically and
-- each collapses to nothing when its own value is 0 -- no Hide()/Show()
-- toggling needed, the engine renders a zero-value StatusBar as zero width.
-- KNOWN APPROXIMATION, not pixel-accurate: because the overlay's own width is
-- the REMAINING gap (bar's right edge minus the previous fill's right edge),
-- not the bar's full width, its rendered fill is `remainingGap * value/max`,
-- not the geometrically "correct" `fullBarWidth * value/max` a Blizzard
-- heal-prediction bar shows. Computing the correct version needs `max - cur`,
-- which is illegal arithmetic on two secret values, so this trades pixel
-- accuracy for legality: the segment is always contained within the
-- remaining space and grows monotonically with the incoming/absorb amount,
-- but under-represents large heals/shields except near empty health. Needs
-- an in-game pass with a known heal amount at partial health to judge
-- whether this approximation reads well enough, or whether a full-width
-- overlay + Frame:SetClipsChildren (if it clips correctly on THIS client --
-- unverified, and this addon has already found one nominally-present API,
-- masking, that silently does not clip on this client) is worth trying next.
local function CreateOverlayBar(bar, color, anchorTexture)
    local overlay = CreateFrame("StatusBar", nil, bar)
    overlay:SetPoint("TOP", bar, "TOP", 0, 0)
    overlay:SetPoint("BOTTOM", bar, "BOTTOM", 0, 0)
    overlay:SetPoint("LEFT", anchorTexture, "RIGHT", 0, 0)
    overlay:SetPoint("RIGHT", bar, "RIGHT", 0, 0)
    overlay:SetStatusBarTexture(FLAT_TEXTURE)
    overlay:SetStatusBarColor(color[1], color[2], color[3], color[4] or 0.35)
    overlay:SetMinMaxValues(0, 1)
    overlay:SetValue(0)
    overlay:SetFrameLevel(bar:GetFrameLevel() + 1)
    return overlay
end

-------------------------------------------------------------------------------
-- Name row building blocks
-------------------------------------------------------------------------------

local LEVEL_BADGE_MIN_WIDTH = 26
local LEVEL_BADGE_PAD = 10

-- Sized for this file's 22px-tall inline nameRow -- deliberately NOT
-- Nameplates.lua's own RAID_MARKER_SIZE (25), which is sized for that
-- file's vertically-stacked nameplate layout. Game-semantic values stay
-- local to their module (see this file's other such constants).
local RAID_MARKER_SIZE = 16

-- Same cut chrome as the panel, sized down for the small chip, with a
-- stronger drop-shadow on the number than the shared default so it reads as
-- glowing at this small size. Delegates to FrameHelpers.lua's
-- FS.FrameHelpers.CreateLevelChip.
local function CreateLevelBadge(parent)
    return FS.FrameHelpers.CreateLevelChip(parent, {
        width = LEVEL_BADGE_MIN_WIDTH,
        height = 16,
        shadowOffset = { 1.5, -1.5 },
    })
end

-- Borderless class icon with a soft radial glow_round.tga halo behind it
-- (tinted per-class in UpdateClassIcon). Replaces an earlier flat ADD-blended
-- color square, which rendered as an ugly hard-edged box for white-ish class
-- colors (Priest).
local function CreateClassIcon(parent, size)
    local icon = parent:CreateTexture(nil, "ARTWORK", nil, 1)
    icon:SetSize(size, size)
    icon:SetTexture(CLASS_ICON_ATLAS)

    local glow = AddSoftGlow(icon, 1, 1, 1, 0.45, 3) -- color patched per-class in UpdateClassIcon

    return icon, glow
end

-------------------------------------------------------------------------------
-- Frame assembly
-------------------------------------------------------------------------------

local function BuildUnitFrame(unitToken, frameName, mirrored)
    -- Secure click surface. Attributes set explicitly rather than relying on
    -- SecureUnitButton_OnLoad, whose internal attribute names differ by
    -- client version. Must run out of combat (enforced by the caller).
    local f = CreateFrame("Button", frameName, UIParent, "SecureUnitButtonTemplate")
    f:SetSize(PANEL_WIDTH, PANEL_HEIGHT)
    f:RegisterForClicks("AnyUp")
    f:SetAttribute("unit", unitToken)
    f:SetAttribute("*type1", "target")
    f:SetAttribute("*type2", "togglemenu")

    f.unit = unitToken
    f.isPlayer = (unitToken == "player")

    -- Everything drawable lives on this non-secure child so it keeps updating
    -- in combat; only the click/target attributes above are protected. Its
    -- top and width track the secure button, but its HEIGHT is driven
    -- directly (see SetPanelHeight) rather than SetAllPoints(f): the secure
    -- button's resize is combat-deferred, and pinning the visuals to it would
    -- leave the border/glow at the old height (with an empty gap) until combat
    -- ended. A non-secure frame can resize in combat, so the chrome tracks it
    -- and always matches the visible frame height.
    local visual = CreateFrame("Frame", nil, f)
    visual:SetPoint("TOPLEFT", f, "TOPLEFT")
    visual:SetPoint("TOPRIGHT", f, "TOPRIGHT")
    visual:SetHeight(PANEL_HEIGHT)
    f.visual = visual

    -- Whole-panel outward glow, tinted border-purple, following the border
    -- only (CSS box-shadow style) via AddOuterGlow -- unlike the old
    -- AddSoftGlow approach, the four strips sit entirely OUTSIDE the panel,
    -- so there is no interior fill for the bg below to hide; called before
    -- the bg purely for creation-order consistency with the rest of this
    -- function.
    AddOuterGlow(visual, COLOR_BORDER[1], COLOR_BORDER[2], COLOR_BORDER[3], 8, 0.38, PANEL_RADIUS)

    -- Cut-rect fill (flat rects + two corner triangles; discs under "round"). Not a
    -- MaskTexture: masking is unavailable on this client (confirmed in-game).
    AddRoundedFill(visual, COLOR_BG, PANEL_RADIUS)
    AddGradientBorder(visual, COLOR_BORDER, BORDER_THICK)

    -- Name row.
    local nameRow = CreateFrame("Frame", nil, visual)
    nameRow:SetPoint("TOPLEFT", visual, "TOPLEFT", PAD_X, -PAD_Y)
    nameRow:SetPoint("TOPRIGHT", visual, "TOPRIGHT", -PAD_X, -PAD_Y)
    nameRow:SetHeight(NAME_ROW_HEIGHT)

    local icon, glow = CreateClassIcon(nameRow, NAME_ROW_HEIGHT - 2)
    local badge = CreateLevelBadge(nameRow)
    local name = nameRow:CreateFontString(nil, "OVERLAY")
    ApplyOrbitron(name, 15)
    -- A space-separated name (this server allows them, e.g. "Father Stu")
    -- otherwise wraps at the space; the second line then renders under
    -- nameRow, hidden behind the health bar drawn after it. No word wrap on
    -- a single-line name row.
    name:SetWordWrap(false)
    if name.SetNonSpaceWrap then name:SetNonSpaceWrap(false) end
    if name.SetMaxLines then name:SetMaxLines(1) end
    name:SetJustifyV("MIDDLE")

    -- Raid-target-marker star, inline between the class icon and the name
    -- (locked mockup layout). Built/hidden here unconditionally on every
    -- BuildUnitFrame call, same as the rest of this file's per-frame visuals;
    -- UpdateRaidMarker (below) handles feature-detection and show/hide.
    local raidMarker = nameRow:CreateTexture(nil, "OVERLAY")
    raidMarker:SetSize(RAID_MARKER_SIZE, RAID_MARKER_SIZE)
    raidMarker:SetTexture("Interface\\TargetingFrame\\UI-RaidTargetingIcons")
    raidMarker:Hide()
    f.raidMarker = raidMarker

    if mirrored then
        -- TARGET: [level badge] .... [name, right-aligned] [raid marker] [class icon]
        badge:SetPoint("LEFT", nameRow, "LEFT", 0, 0)
        icon:SetPoint("RIGHT", nameRow, "RIGHT", 0, 0)
        raidMarker:SetPoint("RIGHT", icon, "LEFT", -4, 0)
        name:SetPoint("RIGHT", raidMarker, "LEFT", -4, 0)
        name:SetPoint("LEFT", badge, "RIGHT", 6, 0)
        name:SetJustifyH("RIGHT")
    else
        -- PLAYER: [class icon] [raid marker] [name] .... [level badge]
        icon:SetPoint("LEFT", nameRow, "LEFT", 0, 0)
        badge:SetPoint("RIGHT", nameRow, "RIGHT", 0, 0)
        raidMarker:SetPoint("LEFT", icon, "RIGHT", 4, 0)
        name:SetPoint("LEFT", raidMarker, "RIGHT", 4, 0)
        name:SetPoint("RIGHT", badge, "LEFT", -6, 0)
        name:SetJustifyH("LEFT")
    end

    f.classIcon, f.classGlow = icon, glow
    f.levelBadge, f.levelText = badge, badge.text
    f.name = name

    -- Resting indicator (player only), anchored at the class icon's own
    -- top-left corner so it sits inside/at the icon's bounds rather than
    -- overflowing toward the panel corner.
    if f.isPlayer then
        local resting = nameRow:CreateTexture(nil, "OVERLAY", nil, 2)
        resting:SetSize(14, 14)
        resting:SetTexture("Interface\\CharacterFrame\\UI-StateIcon")
        resting:SetTexCoord(0, 0.5, 0, 0.5) -- "Zzz" resting quadrant of the state-icon sheet
        resting:SetPoint("CENTER", icon, "TOPLEFT", 2, -2)
        resting:Hide()
        f.restingIcon = resting
    end

    -- Health bar (both bars fill left-to-right regardless of name-row mirroring).
    local health = CreateStatBar(visual, HEALTH_HEIGHT, COLOR_HEALTH, 11)
    health.shell:SetPoint("TOPLEFT", nameRow, "BOTTOMLEFT", 0, -NAME_GAP)
    health.shell:SetPoint("TOPRIGHT", nameRow, "BOTTOMRIGHT", 0, -NAME_GAP)
    -- Chained overlay bars: heal rides the health fill's own edge, absorb
    -- rides heal's edge, so they stack left-to-right with zero arithmetic on
    -- the secret cur/max/incoming/absorb values -- see CreateOverlayBar above
    -- and UpdateHealOverlay/UpdateAbsorbOverlay below.
    health.healOverlay = CreateOverlayBar(health, COLOR_HEAL_OVERLAY, health:GetStatusBarTexture())

    -- Slight glow on the heal segment's trailing edge (mockup:
    -- `box-shadow:0 0 5px -1px var(--green)`, a small soft rim, not a big
    -- blur). Anchored to the overlay's own fill texture's RIGHT edge -- a
    -- LIVE anchor the engine repositions from the (secret) incoming-heal
    -- value, same technique CreateCaret/CreateOverlayBar's own anchoring
    -- already uses -- so this needs no arithmetic on incoming/max either.
    -- Static (no animation): this is a fill, not a caret.
    local healGlow = health.healOverlay:CreateTexture(nil, "OVERLAY")
    healGlow:SetTexture(FLAT_TEXTURE)
    healGlow:SetBlendMode("ADD")
    healGlow:SetSize(6, health:GetHeight())
    healGlow:ClearAllPoints()
    healGlow:SetPoint("CENTER", health.healOverlay:GetStatusBarTexture(), "RIGHT", 0, 0)
    healGlow:SetVertexColor(COLOR_HEAL[1], COLOR_HEAL[2], COLOR_HEAL[3], 0.6)
    health.healOverlay.glow = healGlow

    if HAS_TOTAL_ABSORBS then
        health.absorbOverlay = CreateOverlayBar(health, COLOR_ABSORB_OVERLAY, health.healOverlay:GetStatusBarTexture())

        -- Hatched diagonal stripes instead of a flat tint (Parker's mockup
        -- review: "HATCHED DIAGONAL STRIPES (light gray/white stripes on
        -- transparent, roughly 45 degrees, about 3-4px period)"). Overrides
        -- CreateOverlayBar's own FLAT_TEXTURE fill with the smallest
        -- possible change -- calling SetTexture/SetHorizTile/SetVertTile on
        -- the already-built StatusBar's fill texture -- rather than touching
        -- CreateOverlayBar itself, since the heal overlay above deliberately
        -- stays on the flat texture. This changes only the FILL TEXTURE the
        -- StatusBar paints with; the overlay's width/position still comes
        -- entirely from CreateOverlayBar's live frame-relative anchors plus
        -- UpdateAbsorbOverlay's SetMinMaxValues/SetValue on the raw secret
        -- max/absorb values (see CreateOverlayBar's comment above) -- no
        -- arithmetic on max/absorb/cur was added here.
        --
        -- Tiling idiom matches Theme.lua's scanline overlay
        -- (SetTexture(path, "REPEAT", "REPEAT") + SetHorizTile/SetVertTile).
        -- UNVERIFIED in-game whether a StatusBar's fill texture tiles the
        -- same way a plain Texture region does -- no in-game visual check
        -- possible from this authoring pass.
        local absorbTex = health.absorbOverlay:GetStatusBarTexture()
        absorbTex:SetTexture(HATCH_TEXTURE, "REPEAT", "REPEAT")
        absorbTex:SetHorizTile(true)
        absorbTex:SetVertTile(true)
    elseif not warnedNoTotalAbsorbs then
        warnedNoTotalAbsorbs = true
        FS.LogDegradeOnce("unitframes_noabsorbapi",
            "|cffff4488Forever STUwave|r: UnitGetTotalAbsorbs unavailable, absorb overlay disabled")
    end
    health.caret = CreateCaret(health, COLOR_CARET_HEALTH)
    f.health = health

    -- Power bar.
    local power = CreateStatBar(visual, POWER_HEIGHT, COLOR_POWER, 11)
    power.shell:SetPoint("TOPLEFT", health.shell, "BOTTOMLEFT", 0, -BAR_GAP)
    power.shell:SetPoint("TOPRIGHT", health.shell, "BOTTOMRIGHT", 0, -BAR_GAP)
    power.caret = CreateCaret(power, COLOR_CARET_POWER)
    f.power = power

    return f
end

-------------------------------------------------------------------------------
-- Update logic
-------------------------------------------------------------------------------

-- Drives the incoming-heal overlay entirely through whitelisted engine
-- setters. Do NOT reintroduce an IsSecret(...) -> hide guard here: `max` and
-- `incoming` are secret for every unit but "player", so that guard is what
-- structurally blanked this overlay on exactly target/focus before. Instead
-- hand both straight to SetMinMaxValues/SetValue, which accept secret args,
-- and let CreateOverlayBar's anchor do the positioning -- see its comment.
local function UpdateHealOverlay(frame, max)
    local overlay = frame.health.healOverlay
    if not HAS_INCOMING_HEALS then return end

    local ok, incoming = pcall(UnitGetIncomingHeals, frame.unit)
    -- `not incoming` is a legal truth-test of a non-boolean secret (nil ->
    -- false, any number including a secret 0 -> true); it is NOT a `<= 0`
    -- comparison, which would throw on a secret. A failed pcall or a nil
    -- read both just mean "nothing incoming" -> plain 0.
    if not ok or not incoming then incoming = 0 end

    overlay:SetMinMaxValues(0, max)
    overlay:SetValue(incoming)

    -- Trailing-edge glow: only meaningful while a heal is actually inbound.
    -- At incoming == 0 (the common no-heal-in-flight state) the overlay's
    -- fill has zero width, so the glow -- anchored to that fill's own RIGHT
    -- edge -- sits right at the health bar's own leading edge as a
    -- permanent smudge if left unconditionally shown. `incoming` is secret
    -- for every unit but "player" (see the comment above this function), so
    -- IsSecret is checked FIRST, short-circuiting before the `> 0` compare
    -- -- identical order/idiom to this file's own max-clamp above (`not
    -- IsSecret(max) and max <= 0`). When incoming IS secret, `and` never
    -- evaluates the comparison, so nothing illegal is attempted; the glow
    -- just defaults to hidden on those units rather than risk resurrecting
    -- the always-on smudge this finding is fixing.
    overlay.glow:SetShown(not IsSecret(incoming) and incoming > 0)
end

-- Same shape as UpdateHealOverlay, for the absorb-shield overlay. `overlay`
-- is nil (and this is a no-op) whenever HAS_TOTAL_ABSORBS was false at frame
-- construction, so this function needs no feature-detect of its own.
local function UpdateAbsorbOverlay(frame, max)
    local overlay = frame.health.absorbOverlay
    if not overlay then return end

    local ok, absorb = pcall(UnitGetTotalAbsorbs, frame.unit)
    if not ok or not absorb then absorb = 0 end

    overlay:SetMinMaxValues(0, max)
    overlay:SetValue(absorb)
end

-- Secret-safe dead/ghost/offline predicates consumed by UpdateHealthBar
-- below. Each wraps its raw engine call in an FS.IsSecret check BEFORE any
-- truth-test -- boolean-testing a secret throws -- and treats a secret
-- return as "not dead/ghost/offline" (falls through to a normal live
-- display) rather than assuming the out-of-combat audit holds in combat too.
local function IsUnitOffline(unit)
    if not HAS_UNIT_IS_CONNECTED then return false end
    local connected = UnitIsConnected(unit)
    if IsSecret(connected) then return false end
    return not connected
end

local function IsUnitDeadOrGhost(unit)
    if not HAS_UNIT_IS_DEAD_OR_GHOST then return false end
    local deadOrGhost = UnitIsDeadOrGhost(unit)
    if IsSecret(deadOrGhost) then return false end
    return deadOrGhost
end

local function IsUnitGhost(unit)
    if not HAS_UNIT_IS_GHOST then return false end
    local ghost = UnitIsGhost(unit)
    if IsSecret(ghost) then return false end
    return ghost
end

local function UpdateHealthBar(frame)
    local unit = frame.unit
    local bar = frame.health

    -- Dead/ghost/offline: replace the numeric reading entirely instead of
    -- letting a corpse's low-but-nonzero health read as "critically low" or
    -- an offline unit's stale cached health read as current. Mirrors
    -- PartyFrames.lua's UpdateRowHealth. Falls out for every frame this
    -- function serves (player/target/focus/pet/boss1-5) for free, since they
    -- all share this one UpdateHealthBar rather than PartyFrames' per-row copy.
    local offline = IsUnitOffline(unit)
    local deadOrGhost = not offline and IsUnitDeadOrGhost(unit)

    if offline or deadOrGhost then
        bar:SetMinMaxValues(0, 1)
        bar:SetValue(0)
        -- cornerMask hosts the track-colored erase quads that round the fill's
        -- corners, which have nothing to round on an emptied bar. Hide it here
        -- and restore it on the next live update below.
        if bar.cornerMask then bar.cornerMask:Hide() end
        SetBarDesaturated(bar, true)
        bar:SetStatusBarColor(STATE_BAR_COLOR[1], STATE_BAR_COLOR[2], STATE_BAR_COLOR[3], STATE_BAR_COLOR[4])
        bar.text:SetTextColor(1, 1, 1, 1)
        if offline then
            bar.text:SetText(STATE_OFFLINE_TEXT)
        elseif IsUnitGhost(unit) then
            bar.text:SetText(STATE_GHOST_TEXT)
        else
            bar.text:SetText(STATE_DEAD_TEXT)
        end
        bar.text:Show()
        frame.name:SetAlpha(STATE_ROW_ALPHA)
        bar.shell:SetAlpha(STATE_ROW_ALPHA)
        frame.power.shell:SetAlpha(STATE_ROW_ALPHA)
        frame.classIcon:SetAlpha(STATE_ROW_ALPHA)
        frame.classGlow:SetAlpha(STATE_ROW_ALPHA)
        frame.levelBadge:SetAlpha(STATE_ROW_ALPHA)
        -- Hide the caret directly instead of routing through
        -- FS.FrameHelpers.UpdateCaretFull: that helper only hides the caret
        -- at a FULL bar (its step curve reads 100% health as "hide"), so on
        -- a bar forced to 0 here it would stay visible and pulse over the
        -- state text. host:SetShown(false) is the same mechanism
        -- UpdateCaretFull uses internally, just driven directly.
        -- caretStateHidden marks that THIS branch is what hid it, so the live
        -- path below re-shows it only on the transition back out of this
        -- state (see that comment for why an unconditional re-show is wrong).
        if bar.caret and bar.caret.host then bar.caret.host:SetShown(false) end
        bar.caretStateHidden = true
        return
    end

    -- Clear any state treatment left over from a prior dead/offline pass
    -- before showing a live reading (mirrors PartyFrames.lua). Unlike
    -- PartyFrames' health bar (which is class-colored every UpdateAll pass by
    -- a separate function, so a stale STATE_BAR_COLOR gets overwritten for
    -- free), this file's health bar color is fixed at construction and never
    -- reassigned elsewhere, so it has to be explicitly restored here.
    SetBarDesaturated(bar, false)
    if bar.cornerMask then bar.cornerMask:Show() end
    bar:SetStatusBarColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], COLOR_HEALTH[4] or 1)
    frame.name:SetAlpha(1)
    bar.shell:SetAlpha(1)
    frame.power.shell:SetAlpha(1)
    frame.classIcon:SetAlpha(1)
    frame.classGlow:SetAlpha(1)
    frame.levelBadge:SetAlpha(1)

    local cur = UnitHealth(unit) or 0
    local max = UnitHealthMax(unit) or 0
    -- Secret max (any unit but "player") cannot be compared; the engine
    -- handles the degenerate case itself, so only clamp when we may look.
    if not IsSecret(max) and max <= 0 then max = 1 end

    bar:SetMinMaxValues(0, max)
    bar:SetValue(cur)
    bar.text:SetFormattedText("%d / %d", cur, max)
    UpdateHealOverlay(frame, max)
    UpdateAbsorbOverlay(frame, max)
    -- FS.FrameHelpers.UpdateCaretFull's normal (curve) path only calls
    -- host:SetAlpha, never host:SetShown(true) -- so a caret hidden directly
    -- by the dead/offline branch above needs an explicit re-show, or it stays
    -- invisible forever after a resurrection/reconnect. Gated on
    -- bar.caretStateHidden (set only by that branch) rather than run
    -- unconditionally every UpdateAll pass: UpdateCaretFull's OWN fallback
    -- path (curve API absent/broken) legitimately calls host:SetShown(false)
    -- at a full bar every tick, and an unconditional SetShown(true) right
    -- before that call would fight it -- shown, then immediately hidden
    -- again, every single tick the bar sits at 100%, replaying the pulse
    -- animation each time for nothing. Re-showing only on the
    -- state-to-live TRANSITION avoids that churn.
    if bar.caretStateHidden then
        bar.caretStateHidden = nil
        if bar.caret and bar.caret.host then bar.caret.host:SetShown(true) end
    end
    FS.FrameHelpers.UpdateCaretFull(bar.caret, unit, "health")
end

-- Drives BOTH the visible panel and the secure click region to the height
-- that matches the power-bar visibility. The non-secure `visual` (which every
-- chrome region -- bg, border rails, outer glow, grid -- anchors to) is
-- resized immediately, even in combat, so the border and halo always match
-- the frame. Resizing the secure button itself isn't on the KB's enumerated
-- blocked-in-combat list, but out of caution that half defers to
-- PLAYER_REGEN_ENABLED if combat is active rather than risk it; a slightly
-- tall click region until combat ends is harmless.
local function SetPanelHeight(frame, showPower)
    local targetHeight = showPower and PANEL_HEIGHT or PANEL_HEIGHT_NO_POWER

    if frame.visual:GetHeight() ~= targetHeight then
        frame.visual:SetHeight(targetHeight)
    end

    if frame:GetHeight() == targetHeight then return end

    local function apply()
        frame:SetHeight(targetHeight)
    end

    if InCombatLockdown() then
        if not frame.pendingHeightFix then
            frame.pendingHeightFix = true
            local regen = CreateFrame("Frame")
            regen:RegisterEvent("PLAYER_REGEN_ENABLED")
            regen:SetScript("OnEvent", function(self)
                self:UnregisterEvent("PLAYER_REGEN_ENABLED")
                frame.pendingHeightFix = false
                apply()
            end)
        end
    else
        apply()
    end
end

local function UpdatePowerVisibility(frame)
    local unit = frame.unit
    local max = UnitPowerMax(unit) or 0
    -- Secret max cannot be compared. UnitIsPlayer alone hid mana-bearing NPCs
    -- such as the reported Darkeye Bonecaster. UnitPowerType is comparable on
    -- this client; UnitHasPowerType supplies an additional power-presence
    -- signal. Whether it filters every manaless default-Mana NPC still needs
    -- a live check on this client.
    local show
    if IsSecret(max) then
        show = UnitIsPlayer(unit) and true or false
        if not show then
            local powerType = UnitPowerType(unit)
            if not IsSecret(powerType) and powerType == POWER_TYPE_MANA then
                if HAS_UNIT_HAS_POWER_TYPE then
                    local hasMana = unitHasPowerType(unit, POWER_TYPE_MANA)
                    show = not IsSecret(hasMana) and hasMana
                else
                    show = true
                end
            end
        end
    else
        show = max > 0
    end
    -- Toggle the pill shell, not just the inner fill bar: the shell carries
    -- the cut track/border/glow chrome, so hiding only the fill would
    -- leave an empty bar outline floating in the collapsed panel space.
    if frame.power.shell:IsShown() ~= show then
        frame.power.shell:SetShown(show)
    end
    SetPanelHeight(frame, show)
end

local function UpdatePowerBar(frame)
    UpdatePowerVisibility(frame)
    if not frame.power.shell:IsShown() then return end

    local unit = frame.unit
    local bar = frame.power
    local cur = UnitPower(unit) or 0
    local max = UnitPowerMax(unit) or 0
    -- Secret max (any unit but "player") cannot be compared; the engine
    -- handles the degenerate case itself, so only clamp when we may look.
    if not IsSecret(max) and max <= 0 then max = 1 end

    bar:SetMinMaxValues(0, max)
    bar:SetValue(cur)
    bar.text:SetFormattedText("%d / %d", cur, max)

    -- Dead/offline: mirrors UpdateHealthBar's own caret handling above. A
    -- static caret sitting at the bar's 0% edge (e.g. a warrior's rage,
    -- which genuinely resets to 0 on death) still reads as a live readout
    -- over a row UpdateHealthBar has already dimmed and stamped
    -- Dead/Ghost/Offline.
    -- FS.FrameHelpers.UpdateCaretFull only auto-hides at a FULL bar, so it
    -- can't cover this end either -- hidden/shown directly instead, same as
    -- the health caret, and the re-show below is gated on bar.caretStateHidden
    -- (set only here) for the same reason UpdateHealthBar's is: an
    -- unconditional re-show every tick would fight UpdateCaretFull's own
    -- fallback-path full-bar hide.
    local offline = IsUnitOffline(unit)
    local deadOrGhost = not offline and IsUnitDeadOrGhost(unit)
    if offline or deadOrGhost then
        if bar.caret and bar.caret.host then bar.caret.host:SetShown(false) end
        bar.caretStateHidden = true
        return
    end
    if bar.caretStateHidden then
        bar.caretStateHidden = nil
        if bar.caret and bar.caret.host then bar.caret.host:SetShown(true) end
    end
    FS.FrameHelpers.UpdateCaretFull(bar.caret, unit, "power")
end

-- Full name (first + surname) resolver. Measured in-game on this Forever
-- server: UnitName(unit) returns first name only (e.g. "Father"), while
-- GetUnitName(unit, true) returns "First Surname" (e.g. "Father Stu") --
-- Forever delivers the surname the way a realm suffix normally comes
-- through, and this is the call that yields it. Feature-detected since
-- GetUnitName's boolean-realm-suffix argument form is not guaranteed on
-- every client; falls back to UnitName(unit) and never returns nil.
local function GetFullUnitName(unit)
    local full
    if HAS_GET_UNIT_NAME then
        full = GetUnitName(unit, true)
        -- A secret result is returned untouched: only SetText may consume it.
        if IsSecret(full) then return full end
        -- Strip a stray trailing separator/space GetUnitName can leave
        -- when there is no realm/surname to append.
        if type(full) == "string" then
            full = full:gsub("[%s%-]+$", "")
        end
    end
    if not full or full == "" then
        full = UnitName(unit)
        if IsSecret(full) then return full end
        full = full or ""
    end
    return full
end
FS.GetFullUnitName = GetFullUnitName

local function UpdatePlayerName(frame)
    local name = GetFullUnitName("player")
    if IsSecret(name) then
        frame.name:SetText(name)
        return
    end
    -- Tint only the surname (last space-separated word) cyan; the rest keeps
    -- the FontString's own white color.
    local prefix, surname = name:match("^(.-)%s+(%S+)$")
    if prefix and surname and prefix ~= "" then
        frame.name:SetText(prefix .. " " .. Colorize(surname, COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3]))
    else
        frame.name:SetText(name)
    end
end

local function GetReactionColor(unit)
    if not UnitReaction then return COLOR_TEXT_WHITE end
    local reaction = UnitReaction("player", unit)
    if not reaction then return COLOR_TEXT_WHITE end
    if reaction >= 5 then
        return COLOR_REACTION_FRIEND
    elseif reaction == 4 then
        return COLOR_REACTION_NEUTRAL
    else
        return COLOR_REACTION_HOSTILE
    end
end

-- Runs one update step under pcall so a single failing step (e.g. an API that
-- differs on this client) cannot abort the rest of the frame, and prints which
-- step failed plus the error so the cause is visible in-game. Shared plumbing
-- lives in FrameHelpers.lua (FS.FrameHelpers.NewStepRunner); this file keeps
-- its own message wording. Declared here (ahead of UpdateAll's own use)
-- because UpdateWatchedUnitName's retry below also needs it in scope.
local TryStep = FS.FrameHelpers.NewStepRunner(function(label)
    return "|cffff4488Forever STUwave|r step '" .. label .. "'"
end)

-- Resolves a watched unit's name color: class color for players, else reaction color.
local function ResolveWatchedNameColor(unit)
    if UnitIsPlayer(unit) then
        local classFile = select(2, UnitClass(unit))
        local classColor = HAS_RAID_CLASS_COLORS and classFile and RAID_CLASS_COLORS[classFile]
        if classColor then
            return { classColor.r, classColor.g, classColor.b }
        end
    end
    return GetReactionColor(unit)
end

local function UpdateWatchedUnitName(frame, retryCount)
    local unit = frame.unit
    local name = GetFullUnitName(unit)

    -- A secret name cannot be colorized by string escape, so it takes the
    -- same color through SetTextColor and skips the empty-name retry. The
    -- text is set first so a secret class/reaction read cannot leave a stale name.
    if IsSecret(name) then
        frame.name:SetText(name)
        pcall(function()
            local color = ResolveWatchedNameColor(unit)
            frame.name:SetTextColor(color[1], color[2], color[3])
        end)
        return
    end

    if not name or name == "" then
        if HAS_C_TIMER then
            -- UnitGUID is plain (not secret) on this client, so it's safe to
            -- compare directly -- used as the retry's identity key rather
            -- than the frame, since frame.unit is a fixed TOKEN ("target")
            -- that silently starts meaning a different player on re-target.
            local guid = UnitGUID(unit)
            local samePending = frame.namePendingRetry and frame.namePendingGUID == guid
            if not samePending then
                retryCount = retryCount or 0
                if retryCount < NAME_RETRY_MAX_ATTEMPTS then
                    frame.namePendingRetry = true
                    frame.namePendingGUID = guid
                    C_Timer.After(NAME_RETRY_DELAY, function()
                        -- Release our own pending slot first, but only if a
                        -- newer schedule hasn't already claimed it (re-target
                        -- overwrites namePendingGUID); this runs even when
                        -- the unit is now gone, so a cleared target doesn't
                        -- leave the slot stuck pending forever.
                        if frame.namePendingGUID == guid then
                            frame.namePendingRetry = false
                            frame.namePendingGUID = nil
                        end
                        if UnitGUID(frame.unit) ~= guid then return end
                        if UnitExists(frame.unit) then
                            TryStep(frame, "name-retry", function(f)
                                UpdateWatchedUnitName(f, retryCount + 1)
                            end)
                        end
                    end)
                end
            end
        end
        name = ""
    end

    local color = ResolveWatchedNameColor(unit)
    frame.name:SetText(Colorize(name, color[1], color[2], color[3]))
end

local function UpdateLevel(frame)
    local lvl = UnitLevel(frame.unit)
    local text = (lvl and lvl > 0) and tostring(lvl) or "??"
    frame.levelText:SetText(text)
    -- Symmetric padding around the text so the chip always fits its content
    -- instead of clipping/off-centering at wider values (e.g. "66").
    local width = frame.levelText:GetStringWidth() + LEVEL_BADGE_PAD
    frame.levelBadge:SetWidth(math.max(LEVEL_BADGE_MIN_WIDTH, width))
end

local function UpdateResting(frame)
    local icon = frame.restingIcon
    if not icon then return end
    local resting = (IsResting and IsResting()) or false
    icon:SetShown(resting)
end

local function UpdateClassIcon(frame)
    local unit = frame.unit
    -- Player: always its own class. Target/focus: only for player units,
    -- hidden for creatures.
    local show = frame.isPlayer or UnitIsPlayer(unit)
    if not show then
        frame.classIcon:Hide()
        frame.classGlow:Hide()
        return
    end

    local classFile = select(2, UnitClass(unit))
    if HAS_CLASS_ICON_TCOORDS and classFile and CLASS_ICON_TCOORDS[classFile] then
        frame.classIcon:SetTexCoord(unpack(CLASS_ICON_TCOORDS[classFile]))
    else
        frame.classIcon:SetTexCoord(0, 1, 0, 1)
    end

    local classColor = HAS_RAID_CLASS_COLORS and classFile and RAID_CLASS_COLORS[classFile]
    if classColor then
        frame.classGlow:SetVertexColor(classColor.r, classColor.g, classColor.b, 0.45)
    else
        frame.classGlow:SetVertexColor(COLOR_BORDER[1], COLOR_BORDER[2], COLOR_BORDER[3], 0.45)
    end

    frame.classIcon:Show()
    frame.classGlow:Show()
end

-- GetRaidTargetIndex returns a plain number historically, but FS.IsSecret is
-- checked first anyway (same ordering as this file's other secret-guarded
-- reads) since a truth-test on a secret is illegal even where the value is
-- expected to be plain. Either API missing degrades to a hidden marker, not
-- a texcoord guess. Ported from Nameplates.lua's UpdateRaidMarker.
local function UpdateRaidMarker(frame)
    local marker = frame.raidMarker
    if not marker then return end

    if not HAS_GET_RAID_TARGET_INDEX or not HAS_RAID_TARGET_TEXTURE_SETTER then
        marker:Hide()
        return
    end

    local index = GetRaidTargetIndex(frame.unit)
    if IsSecret(index) or not index then
        marker:Hide()
        return
    end

    SetRaidTargetIconTexture(marker, index)
    marker:Show()
end

local function UpdateAll(frame)
    if not UnitExists(frame.unit) then return end
    TryStep(frame, "health", UpdateHealthBar)
    TryStep(frame, "power", UpdatePowerBar)
    TryStep(frame, "name", frame.isPlayer and UpdatePlayerName or UpdateWatchedUnitName)
    TryStep(frame, "level", UpdateLevel)
    TryStep(frame, "classIcon", UpdateClassIcon)
    TryStep(frame, "raidMarker", UpdateRaidMarker)
    TryStep(frame, "resting", UpdateResting)
end

-------------------------------------------------------------------------------
-- Name refresh watcher (uncached-name repair)
-------------------------------------------------------------------------------

-- WireEvents (below) registers UNIT_NAME_UPDATE UNIT-FILTERED on each frame's
-- own token, which only fires when the server resolves that EXACT token; for
-- an uncached stranger just targeted, resolution often arrives under a
-- DIFFERENT token (e.g. a nameplate unit), so the filtered registration never
-- sees it and the name stays blank until re-target. This second, UNFILTERED
-- listener (plain RegisterEvent) catches every UNIT_NAME_UPDATE regardless of
-- token and re-runs the cheap name step (UnitName + SetText) for whichever
-- watched frames currently have a unit. A single shared frame avoids
-- disturbing WireEvents' per-frame filtered registration of this same event
-- -- RegisterEvent and RegisterUnitEvent for the SAME event on the SAME frame
-- would conflict, which a separate frame sidesteps.
local nameWatchFrames = {}

local function RefreshWatchedNames()
    for _, frame in ipairs(nameWatchFrames) do
        if UnitExists(frame.unit) then
            TryStep(frame, "name", UpdateWatchedUnitName)
        end
    end
end

local nameWatcher = CreateFrame("Frame")
nameWatcher:RegisterEvent("UNIT_NAME_UPDATE")
nameWatcher:SetScript("OnEvent", RefreshWatchedNames)

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local function WireEvents(frame)
    local events = CreateFrame("Frame")
    events:RegisterUnitEvent("UNIT_HEALTH", frame.unit)
    events:RegisterUnitEvent("UNIT_MAXHEALTH", frame.unit)
    events:RegisterUnitEvent("UNIT_POWER_UPDATE", frame.unit)
    events:RegisterUnitEvent("UNIT_MAXPOWER", frame.unit)
    events:RegisterUnitEvent("UNIT_DISPLAYPOWER", frame.unit)
    events:RegisterUnitEvent("UNIT_NAME_UPDATE", frame.unit)
    events:RegisterUnitEvent("UNIT_LEVEL", frame.unit)
    events:RegisterUnitEvent("UNIT_FACTION", frame.unit)
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:RegisterEvent("RAID_TARGET_UPDATE")
    if frame.unit == "target" then
        events:RegisterEvent("PLAYER_TARGET_CHANGED")
    elseif frame.unit == "focus" then
        events:RegisterEvent("PLAYER_FOCUS_CHANGED")
    elseif frame.unit:match("^boss%d$") then
        -- Neither INSTANCE_ENCOUNTER_ENGAGE_UNIT nor UNIT_TARGETABLE_CHANGED
        -- carries a boss unit token as arg1 (the former fires once for the
        -- whole encounter engage, the latter for whatever unit's targetability
        -- flipped), so RegisterUnitEvent(frame.unit) can't be used -- these
        -- ride plain RegisterEvent instead. This is wired PER-FRAME (each of
        -- the 5 boss frames' own event object
        -- registers both events and re-runs UpdateAll(frame) for its OWN
        -- unit) rather than through one shared listener that loops over all
        -- five boss frames: a per-frame registration needs no new shared
        -- refresh function and slots into this same if/elseif dispatch with a
        -- single added branch, whereas a shared listener would need its own
        -- separate wiring path outside it. The cost -- 5 handlers firing per
        -- encounter-engage event instead of 1 -- is negligible next to that.
        events:RegisterEvent("INSTANCE_ENCOUNTER_ENGAGE_UNIT")
        events:RegisterEvent("UNIT_TARGETABLE_CHANGED")
    else
        events:RegisterEvent("PLAYER_UPDATE_RESTING")
        -- Backstops the shared UNIT_HEALTH registration above for the
        -- player's own dead/ghost state: release-to-graveyard and
        -- resurrection can each land without a UNIT_HEALTH fire in between,
        -- so only the player's own frame (this is the only unit token that
        -- reaches this else branch) needs these two on top of it.
        events:RegisterEvent("PLAYER_ALIVE")
        events:RegisterEvent("PLAYER_UNGHOST")
    end
    -- Drives the incoming-heal overlay; UNVERIFIED whether UNIT_HEAL_PREDICTION
    -- is present on this interface-16001 client, so RegisterUnitEvent (which
    -- can throw on an unrecognized event name) is pcall-guarded rather than
    -- assumed safe.
    pcall(events.RegisterUnitEvent, events, "UNIT_HEAL_PREDICTION", frame.unit)
    -- Drives the absorb overlay; same UNVERIFIED/pcall-guarded treatment --
    -- this event's presence on this client is unconfirmed too.
    pcall(events.RegisterUnitEvent, events, "UNIT_ABSORB_AMOUNT_CHANGED", frame.unit)
    -- Drives the offline state (UpdateHealthBar's IsUnitOffline); UNVERIFIED
    -- whether UNIT_CONNECTION is present on this interface-16001 client, so
    -- pcall-guarded like the two registrations above.
    pcall(events.RegisterUnitEvent, events, "UNIT_CONNECTION", frame.unit)
    events:SetScript("OnEvent", function()
        UpdateAll(frame)
    end)
    frame.events = events
end

-------------------------------------------------------------------------------
-- Init (secure frame creation + SetAttribute must run out of combat)
-------------------------------------------------------------------------------

local function Init()
    -- Dim, not hide: Player/Target/Focus/boss are all Edit Mode
    -- UnitFrame system members (retail's Enum.EditModeUnitFrameSystemIndices)
    -- and Hide()+OnShow-hook taints their secure Update path, the same class
    -- of bug Buffs.lua's BuffFrame/DebuffFrame fix addressed. See CLAUDE.md's
    -- Buffs.lua/FrameHelpers.lua entries (2026-09-25).
    DimBlizzardFrame(PlayerFrame)
    DimBlizzardFrame(TargetFrame)
    if FocusFrame then
        DimBlizzardFrame(FocusFrame) -- not confirmed present on every 16001 build
    end
    if PetFrame then
        DimBlizzardFrame(PetFrame) -- not confirmed present on every 16001 build
    end
    for i = 1, 5 do
        local bossFrame = _G["Boss" .. i .. "TargetFrame"]
        if bossFrame then
            DimBlizzardFrame(bossFrame) -- not confirmed present on every 16001 build
        end
    end

    local player = BuildUnitFrame("player", "ForeverSTUwavePlayerFrame", false)
    FS.Layout.Apply(player, "player")
    player:Show() -- "player" always exists; shown unconditionally, no watch needed

    local target = BuildUnitFrame("target", "ForeverSTUwaveTargetFrame", true)
    FS.Layout.Apply(target, "target")
    RegisterUnitWatch(target) -- shows/hides securely based on whether "target" exists

    -- Focus sits at its own design position (FS.Layout.focus), away from the
    -- player/target corner, and seats from the layout table like they do.
    local focus = BuildUnitFrame("focus", "ForeverSTUwaveFocusFrame", true)
    FS.Layout.Apply(focus, "focus")
    RegisterUnitWatch(focus) -- shows/hides securely based on whether "focus" exists

    -- Boss frames have no on-screen neighbor either (see focus above), so
    -- boss[1] seats from FS.Layout.boss the same way; boss[2..5] then stack
    -- directly below it rather than each getting their own layout entry,
    -- since FS.Layout.boss's 210 height is sized for the whole 5-frame stack,
    -- not a single frame.
    local BOSS_STACK_GAP = 8 -- small vertical gap between stacked boss frames, same order of magnitude as BAR_GAP (6px)

    local boss = {}
    for i = 1, 5 do
        boss[i] = BuildUnitFrame("boss" .. i, "ForeverSTUwaveBoss" .. i .. "Frame", true)
    end
    FS.Layout.Apply(boss[1], "boss")
    for i = 2, 5 do
        -- Anchored to the frame ABOVE by point, not by a fixed SetSize: this
        -- keeps every slot's width locked to boss[1]'s (which FS.Layout.Apply
        -- sized from the "boss" entry) through UI Scale changes too, since
        -- Layout's rescale watcher only re-Applies boss[1] -- boss[2..5] just
        -- follow its edges automatically, the same way `visual` tracks `f` in
        -- BuildUnitFrame.
        -- Anchor to `.visual`, not the frame itself: boss[1]'s outer secure
        -- button is still sized 210 (FS.Layout.boss, a placeholder for the
        -- whole 5-frame stack) until SetPanelHeight corrects it on the first
        -- UpdateAll, and that correction is deferred across combat lockdown --
        -- exactly while boss frames are populating. `.visual` always reflects
        -- the true rendered panel height, so anchoring to it avoids a
        -- fight-long gap between rows.
        boss[i]:ClearAllPoints()
        boss[i]:SetPoint("TOPLEFT", boss[i - 1].visual, "BOTTOMLEFT", 0, -BOSS_STACK_GAP)
        boss[i]:SetPoint("TOPRIGHT", boss[i - 1].visual, "BOTTOMRIGHT", 0, -BOSS_STACK_GAP)
    end
    for i = 1, 5 do
        RegisterUnitWatch(boss[i]) -- shows/hides securely based on whether "bossN" exists
    end

    WireEvents(player)
    WireEvents(target)
    WireEvents(focus)
    for i = 1, 5 do
        WireEvents(boss[i])
    end

    FS.player, FS.target, FS.focus = player, target, focus
    FS.boss = boss

    -- Frames that resolve their name via UpdateWatchedUnitName (every
    -- non-player frame) feed the unfiltered UNIT_NAME_UPDATE watcher above.
    nameWatchFrames[#nameWatchFrames + 1] = target
    nameWatchFrames[#nameWatchFrames + 1] = focus
    for i = 1, 5 do
        nameWatchFrames[#nameWatchFrames + 1] = boss[i]
    end

    UpdateAll(player)
    if UnitExists("target") then UpdateAll(target) end
    if UnitExists("focus") then UpdateAll(focus) end
    for i = 1, 5 do
        if UnitExists(boss[i].unit) then UpdateAll(boss[i]) end
    end
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
