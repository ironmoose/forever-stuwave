-- Forever Synthwave
-- Neon synthwave-styled nameplate health bars, standalone (no oUF/ElvUI dependency).

local _, FS = ...

-- Old clients may lack the nameplate API entirely; bail out cleanly instead of erroring.
if not C_NamePlate then return end

-------------------------------------------------------------------------------
-- Constants
-------------------------------------------------------------------------------

local BAR_WIDTH = 130
local BAR_HEIGHT = 14
local PLATE_OUTER_PAD = 2
local POWER_BAR_HEIGHT = 5
local POWER_BAR_GAP = 1
local CAST_BAR_HEIGHT = 6
local CAST_BAR_GAP = 2
local CAST_NAME_FONT_SIZE = 9
local RAID_MARKER_SIZE = 25
local RAID_MARKER_GAP = 3
local QUEST_ICON_SIZE = 22
local QUEST_ICON_GAP = 4

-- Aura row. Each plate carries ONE AuraContainer (the engine reads and draws the
-- auras, so no aura data ever enters addon Lua and the row works in combat; the
-- Plater design). Two groups share its flow layout, "own" first: the player's own
-- debuffs (the DoT row, pink border) and everyone else's (violet border).
-- Parker, 2026-10-02: "the dots and debuffs are not showing up on the nameplates".
-- Blizzard's own AurasFrame cannot be borrowed: HideBlizzardPlate hides its
-- UnitFrame and the reparent path threw "Can't measure restricted regions".
local AURA_ICON_SIZE = 18
local AURA_ICON_GAP = 2
-- Both rows sit this far above the health bar's top edge.
local AURA_ROW_Y = 2
local AURA_CONTAINER_TEMPLATE = "CustomAuraContainerTemplate"
local AURA_GROUP_OWN = "own"
local AURA_GROUP_OTHER = "other"
local AURA_FILTER_OWN = "HARMFUL|PLAYER"
local AURA_FILTER_OTHER = "HARMFUL|!PLAYER"
local AURA_OWN_MAX = 5
local AURA_OTHER_MAX = 3
-- The flow wraps upward after this many icons, so eight never run past the bar.
local AURA_ROW_WRAP = 6
local AURA_ROW_LINE_SIZE = AURA_ROW_WRAP * (AURA_ICON_SIZE + AURA_ICON_GAP) + 1
-- Levels above root so the row draws over the plate chrome.
local AURA_LEVEL_BOOST = 5
-- Idle containers kept ready. They are built out of combat (PLAYER_ENTERING_WORLD,
-- topped up on PLAYER_REGEN_ENABLED), AURA_POOL_BATCH per step, so a pull never
-- has to build one; in combat one is built only when the pool is empty. Each
-- container builds a 10-button batch per group (about 20 buttons), so the target
-- stays small: eight covers a normal pull and an empty pool just builds one.
local AURA_POOL_TARGET = 8
local AURA_POOL_BATCH = 4
-- Consecutive failed builds before the container path is given up for the session
-- (the fallback custom row takes over).
local AURA_BUILD_FAIL_LIMIT = 3
-- Attach failures a container may have before it is parked as broken.
local AURA_ATTACH_FAIL_LIMIT = 2
-- AnchorUtil.FlowDirection's real values, used only if the table is missing.
local AURA_FLOW_LEFT, AURA_FLOW_UP = -1, 1
-- Fallback row (a client without CustomAuraContainerTemplate): AURA_ICON_MAX
-- custom icons off the same corner, fed by a "HARMFUL" scan out of combat only.
-- Own-cast auras are told apart by `caster == "player"` (the PLAYER sub-filter
-- is unreliable on that path).
local AURA_ICON_MAX = 5
local AURA_QUERY_FILTER = "HARMFUL"

-- Enum.PowerType.Mana if it exists, else 0 -- both are the plain numeric mana
-- constant on every client that has shipped it, so feature-detecting instead
-- of hardcoding costs nothing and matches this file's other Enum reads.
local POWER_TYPE_MANA = (Enum and Enum.PowerType and Enum.PowerType.Mana) or 0

-- Same feature-detect pattern as POWER_TYPE_MANA above, for the two other
-- power types the plate's power strip now shows (Dispatch 3: mana-only ->
-- mana/energy/rage).
local POWER_TYPE_RAGE = (Enum and Enum.PowerType and Enum.PowerType.Rage) or 1
local POWER_TYPE_ENERGY = (Enum and Enum.PowerType and Enum.PowerType.Energy) or 3

local COLOR_TEXT = { 0.886, 0.910, 0.941, 1 }        -- #E2E8F0, no Theme equivalent
local COLOR_BAR_SOLID = { 0.486, 0.227, 0.929, 1 }   -- #7C3AED, flat default fill before a unit resolves
local COLOR_BAR_TAPPED = { 0.42, 0.42, 0.45, 1 }     -- tapped by someone else: no credit for you

-- Power strip fill colors, keyed by numeric power type via GetPowerTypeColors
-- below. Mana reuses FS.Theme.COLOR_POWER (the existing cyan token, applied
-- at runtime -- see GetPowerTypeColors' own comment); rage/energy are new,
-- addon-local colors (Parker's design call, not new Theme.lua tokens --
-- PartyFrames.lua's own POWER_COLORS table is a DIFFERENT palette by design,
-- not reused here).
local COLOR_POWER_RAGE = { 1, 0.302, 0.302, 1 }    -- #ff4d4d
local COLOR_POWER_ENERGY = { 1, 0.882, 0.302, 1 }  -- #ffe14d

-- Reaction fill colors (HUD mockup): hostile reuses the canonical Theme
-- token; neutral/friendly stay local per Theme.lua's own "game-semantic
-- values stay local to their module" rule (UnitFrames.lua's GetReactionColor
-- is the precedent -- its neutral/hostile hexes differ from these, since this
-- is a separate palette for the nameplate mockup, not a shared token).
local COLOR_REACTION_NEUTRAL = { 1, 0.714, 0.282, 1 }  -- #ffb648
local COLOR_REACTION_FRIEND  = { 0.224, 1, 0.078, 1 }  -- #39ff14

-- Quest marker tint: amber, same hex as COLOR_REACTION_NEUTRAL above -- aliased
-- rather than duplicated so the two stay one source of truth for the color,
-- even though "quest indicator" and "neutral reaction" are different concepts
-- that happen to share a hue. Do NOT add a Theme.lua token for this.
local COLOR_QUEST_AMBER = COLOR_REACTION_NEUTRAL

-- Name-text reaction palette (Parker's literal design call): white/yellow/red,
-- a DELIBERATELY separate hue set from the green/amber/red palette above, which
-- colors the health BAR FILL for the same three reaction buckets. Two
-- different visual signals sharing one hue per bucket would read as the same
-- signal twice; distinct hues keep "what color is the bar" and "what color is
-- the name" answerable independently at a glance.
local COLOR_NAME_HOSTILE = { 1, 0.15, 0.15, 1 }
local COLOR_NAME_NEUTRAL = { 1, 0.9, 0.1, 1 }
local COLOR_NAME_FRIENDLY = { 1, 1, 1, 1 }

-- Engagement/threat palette (Parker's design call): for an ATTACKABLE unit
-- that is on a threat table, both the health-bar fill and the name text use
-- one of these two so the two read as the same color -- see
-- GetEngagementColor below. A unit with no threat yet (not engaged) has no
-- entry here: it keeps its reaction color (yellow/amber neutral, red/hostile
-- pink hostile) until a fight starts. Kept as distinct semantic constants
-- from COLOR_REACTION_NEUTRAL/Theme.COLOR_HEALTH even though the hexes match
-- (neutral shares the reaction palette's amber, aggro shares Theme's hot-pink
-- health color): this pair names "how much threat this mob has on me" rather
-- than "what this bar's static hostility color is", and the two ideas should
-- stay free to diverge later.
local COLOR_ENGAGEMENT_NEUTRAL = { 1, 0.714, 0.282, 1 }      -- #ffb648, on someone else's threat table
local COLOR_ENGAGEMENT_AGGRO = { 1, 0.180, 0.592, 1 }        -- #ff2e97, tanking/high on the table

-- Gradient fill: darkened-left-to-full-right (HUD mockup). Multiplier chosen
-- to keep the dark stop visibly tinted rather than reading near-black.
local FILL_GRADIENT_DARK_SCALE = 0.55

-- Outer-glow alpha for the two hostility states UpdateGlowState toggles
-- between: violet at rest (matches SkinPanel's own default), hot pink and a
-- touch brighter when the unit is attackable, so it reads as a warning.
local GLOW_ALPHA_DEFAULT = 0.30
local GLOW_ALPHA_HOSTILE = 0.45

-- Target emphasis: the plate UnitIsUnit(unit, "target") gets a hotter
-- glow than GLOW_ALPHA_HOSTILE/GLOW_ALPHA_DEFAULT above, on top of the same
-- hostility hue. Every OTHER plate dims to ALPHA_NONTARGET_DIM while the
-- player has any target at all; no target means no dimming.
local GLOW_ALPHA_TARGET_HOSTILE = 0.85
local GLOW_ALPHA_TARGET_DEFAULT = 0.65
local ALPHA_NONTARGET_DIM = 0.75

local FONT_SIZE = 10
local FONT_FLAGS = "OUTLINE"

-- Nameplate cast bar. CHANNEL_UPDATE/DELAYED restart the same bar (a
-- channel tick or a pushback edits the existing cast rather than starting a
-- new one); INTERRUPTIBLE/NOT_INTERRUPTIBLE carry no timing, only the
-- interruptible-state flip. Mirrors CastBars.lua's own CAST_EVENTS list plus
-- the two interruptible events that file doesn't need (its player/target
-- bars aren't casts on enemies, so the not-interruptible case never arises there).
local CAST_EVENTS = {
    "UNIT_SPELLCAST_START",
    "UNIT_SPELLCAST_STOP",
    "UNIT_SPELLCAST_FAILED",
    "UNIT_SPELLCAST_INTERRUPTED",
    "UNIT_SPELLCAST_DELAYED",
    "UNIT_SPELLCAST_CHANNEL_START",
    "UNIT_SPELLCAST_CHANNEL_STOP",
    "UNIT_SPELLCAST_CHANNEL_UPDATE",
    "UNIT_SPELLCAST_INTERRUPTIBLE",
    "UNIT_SPELLCAST_NOT_INTERRUPTIBLE",
}

-- UnitCastingDuration/UnitChannelDuration are plain Blizzard globals, not
-- FS.Theme fields, so (unlike the rest of this file) this is safe to read at
-- file scope despite loading before Theme.lua.
local HAS_PLATE_CAST_DURATION = type(UnitCastingDuration) == "function"
    and type(UnitChannelDuration) == "function"

-- Raid target marker (skull/cross/etc.). Both are plain Blizzard globals on
-- 16001 (confirmed against the API dump), but feature-detected anyway per
-- this file's other Enum/API reads rather than assumed permanent.
local HAS_GET_RAID_TARGET_INDEX = type(GetRaidTargetIndex) == "function"
local HAS_RAID_TARGET_TEXTURE_SETTER = type(SetRaidTargetIconTexture) == "function"

-- RAID_CLASS_COLORS is a plain Blizzard global, feature-detected rather than
-- assumed permanent per this file's other Enum/API reads -- mirrors
-- UnitFrames.lua's own HAS_RAID_CLASS_COLORS local of the same name.
local HAS_RAID_CLASS_COLORS = type(RAID_CLASS_COLORS) == "table"

-- GetUnitName(unit, true) is the call that yields a Forever character's
-- "First Surname"; UnitName returns the first name only. Feature-detected,
-- mirroring UnitFrames.lua's own HAS_GET_UNIT_NAME local of the same name.
local HAS_GET_UNIT_NAME = type(GetUnitName) == "function"

-- Quest objective indicator. C_QuestLog.IsUnitOnQuest(unit, questID) has been
-- the documented per-unit quest-relevance API since Patch 9.0.1 (Shadowlands
-- moved the legacy global IsUnitOnQuest(questLogIndex, unit) -- note the
-- swapped argument order -- onto this namespaced call). Feature-detected as a
-- trio since the scan needs all three: GetNumQuestLogEntries to bound the
-- loop, GetInfo to resolve each entry's questID, IsUnitOnQuest to test it.
local HAS_QUEST_LOG_API = C_QuestLog
    and type(C_QuestLog.GetNumQuestLogEntries) == "function"
    and type(C_QuestLog.GetInfo) == "function"
    and type(C_QuestLog.IsUnitOnQuest) == "function"

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

FS.framesByUnit = {}  -- unit token -> our custom plate frame currently in use
FS.platesByUnit = {}  -- unit token -> Blizzard C_NamePlate frame it's attached to
FS.freePool = {}      -- array of custom plate frames available for reuse

-------------------------------------------------------------------------------
-- Frame construction helpers
-------------------------------------------------------------------------------

-- AddSliceTexture only ever creates textures on the frame it's given; it
-- neither reads nor requires backdrop APIs, so a plain Frame is enough here.
local function CreatePlateRootFrame()
    return CreateFrame("Frame", nil, UIParent)
end

-- Panel chrome through the shared Theme.AddPanelChrome (nine-sliced fill, an
-- additive glow, then a 1px border; two-corner cut, TOP-LEFT and BOTTOM-RIGHT,
-- under Theme.CHROME_CORNERS == "cut"). root.fsGlow/root.fsBorder are kept for
-- UpdateGlowState to retint later -- the glow starts violet (GLOW_ALPHA_DEFAULT)
-- matching the static border, and turns hot pink when the unit becomes
-- attackable. The fill keeps COLOR_BG's own 0.80 alpha (AddPanelChrome only
-- defaults to 0.92 when the colour carries none).
local function ApplyBackdrop(root)
    local _, glow, border = FS.Theme.AddPanelChrome(root, {
        accent = FS.Theme.COLOR_BORDER,
        glowAlpha = GLOW_ALPHA_DEFAULT,
    })
    root.fsGlow = glow
    root.fsBorder = border
end

-- Font fallback: the Mononoki file lives in a different addon's folder, so it may not
-- be installed; SetFont's boolean return tells us whether it actually loaded.
local function ApplyFont(fontString, size)
    local ok = fontString:SetFont(FS.Theme.FONT_MONO, size, FONT_FLAGS)
    if not ok then
        local defaultFont, defaultSize = GameFontNormal:GetFont()
        fontString:SetFont(defaultFont or "Fonts\\FRIZQT__.TTF", size or defaultSize, FONT_FLAGS)
    end
end

-- Flat chrome for the cast bar: opaque track behind the fill plus a 1px
-- hairline border (the flat chrome CastBars.lua used before its chamfered
-- bars) -- NOT nine-sliced and NOT CreatePillBar, since this bar sits
-- outside the plate's nine-slice chrome entirely (see CreatePlateFrame). Kept
-- as its own copy rather than a FrameHelpers export: the plan surface for
-- this pass is ForeverSynthwave.lua/Theme.lua only.
local function AddCastBarChrome(bar)
    local track = bar:CreateTexture(nil, "BACKGROUND")
    track:SetAllPoints(bar)
    track:SetColorTexture(FS.Theme.COLOR_BAR_TRACK[1], FS.Theme.COLOR_BAR_TRACK[2], FS.Theme.COLOR_BAR_TRACK[3], 1)

    local bc = FS.Theme.COLOR_BAR_BORDER
    local bt = bar:CreateTexture(nil, "OVERLAY"); bt:SetPoint("TOPLEFT"); bt:SetPoint("TOPRIGHT"); bt:SetHeight(1); bt:SetColorTexture(bc[1], bc[2], bc[3], 1)
    local bb = bar:CreateTexture(nil, "OVERLAY"); bb:SetPoint("BOTTOMLEFT"); bb:SetPoint("BOTTOMRIGHT"); bb:SetHeight(1); bb:SetColorTexture(bc[1], bc[2], bc[3], 1)
    local bl = bar:CreateTexture(nil, "OVERLAY"); bl:SetPoint("TOPLEFT"); bl:SetPoint("BOTTOMLEFT"); bl:SetWidth(1); bl:SetColorTexture(bc[1], bc[2], bc[3], 1)
    local br = bar:CreateTexture(nil, "OVERLAY"); br:SetPoint("TOPRIGHT"); br:SetPoint("BOTTOMRIGHT"); br:SetWidth(1); br:SetColorTexture(bc[1], bc[2], bc[3], 1)
end

-- Mirrors CastBars.lua's CleanSpellName: trims a trailing "No Text" subtext
-- rank so generic casts ("Opening - No Text") show just the verb. Kept as its
-- own copy for the same plan-surface reason as AddCastBarChrome above.
local function CleanPlateCastName(name)
    if type(name) ~= "string" then return "" end

    -- UnitCastingInfo/UnitChannelInfo hand back a PLAIN name for a unit we
    -- control and a SECRET one otherwise; a method call is an index
    -- (name:find desugars to name.find), and indexing a secret is forbidden,
    -- so every string method is unavailable here. Hand it straight to
    -- SetText, which is whitelisted for secrets, and skip the trim.
    if FS.IsSecret(name) then return name end

    local cut = name:find("No Text", 1, true)
    if not cut then return name end

    local trimmed = name:sub(1, cut - 1)
    trimmed = trimmed:gsub("[%s%-]+$", "")
    if trimmed ~= "" then return trimmed end
    return name
end

-- Flat placeholder painted once at frame construction, before any unit is
-- known; UpdateFillColor (via ApplyFillColor) overwrites it as soon as the
-- frame acquires a unit in OnNamePlateAdded, so this is never seen mid-fight.
local function ApplyDefaultFill(root)
    local texture = root.barTexture
    if not texture then return end

    texture:SetVertexColor(unpack(COLOR_BAR_SOLID))
end

-- Reaction/tap-denied fill: a HORIZONTAL gradient from a darkened base to the
-- full color (HUD mockup), same SetGradient call form as XPBar.lua/
-- DataBar.lua's own fills -- Texture:SetGradientAlpha does not exist on this
-- client, only SetGradient does, so the two are feature-detected together.
-- Cached per plate by color-table identity (reset on acquire, see
-- AcquireFrame) so re-resolving to the same color skips the call.
local function ApplyFillColor(root, color)
    if not color then return end
    if root.fillColor == color then return end
    root.fillColor = color

    local texture = root.barTexture
    if not texture then return end

    if texture.SetGradient and CreateColor then
        texture:SetGradient("HORIZONTAL",
            CreateColor(color[1] * FILL_GRADIENT_DARK_SCALE, color[2] * FILL_GRADIENT_DARK_SCALE,
                color[3] * FILL_GRADIENT_DARK_SCALE, 1),
            CreateColor(color[1], color[2], color[3], 1))
    else
        texture:SetVertexColor(color[1], color[2], color[3], 1)
    end

end

-- Power strip fill: flat (no gradient, unlike ApplyFillColor above), one of
-- GetPowerTypeColors' three entries. Cached by color-table identity exactly
-- like ApplyFillColor's root.fillColor cache, via root.powerFillColor
-- instead -- reset to nil on AcquireFrame (see below) so a reused pooled
-- plate re-applies rather than skipping on a stale match left by the
-- PREVIOUS occupant's power type.
local function ApplyPowerFillColor(root, color)
    if not color then return end
    if root.powerFillColor == color then return end
    root.powerFillColor = color

    local powerBar = root.powerBar
    if not powerBar then return end

    powerBar:GetStatusBarTexture():SetVertexColor(color[1], color[2], color[3], color[4] or 1)
end

-- UnitReaction(unit, "player")'s secrecy on this client is UNVERIFIED (the
-- recon audit call that would confirm it failed to run -- see Diagnostics.lua
-- item 5). FS.IsSecret is checked BEFORE any nil/number check: per the
-- secret-values skill, `r == nil` is itself an illegal comparison if `r`
-- turns out to be a secret, so the secrecy test has to come first, not the
-- nil test. Never returns nil: a secret or unavailable reaction falls back
-- to the same flat default ApplyDefaultFill paints, so a reacquired pooled
-- plate always gets a fresh, correct color instead of silently keeping the
-- PREVIOUS occupant's gradient (ApplyFillColor no-ops on a nil color).
local function GetReactionColor(unit)
    local reaction = UnitReaction(unit, "player")
    if FS.IsSecret(reaction) then return COLOR_BAR_SOLID end
    if reaction == nil then return COLOR_BAR_SOLID end

    if reaction >= 5 then
        return COLOR_REACTION_FRIEND
    elseif reaction == 4 then
        return COLOR_REACTION_NEUTRAL
    else
        return FS.Theme.COLOR_HEALTH
    end
end

-- Same UnitReaction argument order and IsSecret-first/nil-second guard as
-- GetReactionColor above (see its comment for the full secrecy-order
-- rationale) -- this sibling returns the white/yellow/red NAME palette
-- instead of the fill palette. Never returns nil, for the same reacquired-
-- pooled-plate reason: SetTextColor must always get a real color, never
-- silently keep the previous occupant's.
local function GetNameReactionColor(unit)
    local reaction = UnitReaction(unit, "player")
    if FS.IsSecret(reaction) then return COLOR_NAME_FRIENDLY end
    if reaction == nil then return COLOR_NAME_FRIENDLY end

    if reaction >= 5 then
        return COLOR_NAME_FRIENDLY
    elseif reaction == 4 then
        return COLOR_NAME_NEUTRAL
    else
        return COLOR_NAME_HOSTILE
    end
end

-- Threat/engagement color for an attackable unit, shared by the fill
-- (UpdateFillColor) and name (UpdateName) paths so the two match on a mob
-- once it is engaged -- Parker's ask. UnitCanAttack/UnitThreatSituation's
-- secrecy on a nameplate unit token is UNVERIFIED on this client, so both are
-- FS.IsSecret-guarded before any truth-test/nil-check, same secrecy-first-
-- then-nil ordering as GetReactionColor's own comment above. Argument order
-- ("player", unit) matches Diagnostics.lua's /fsrecon threat probe.
-- reactionFn picks the fallback palette (defaults to GetReactionColor, the
-- fill palette; UpdateName passes GetNameReactionColor so the name keeps its
-- own white/yellow/red palette). The fallback is used when the unit is not
-- attackable, when it is not on any threat table yet (situation nil, the
-- untouched-mob case, which must read as its reaction color rather than a
-- neutral grey), and when the situation is secret or unexpected. Only a real
-- situation of 0/1 (on someone else's table) or >= 2 (tanking/high) paints an
-- engagement color. Never nil, since reactionFn itself never returns nil.
local function GetEngagementColor(unit, reactionFn)
    reactionFn = reactionFn or GetReactionColor

    local attackable = UnitCanAttack("player", unit)
    if FS.IsSecret(attackable) then return reactionFn(unit) end
    if not attackable then return reactionFn(unit) end

    local situation = UnitThreatSituation("player", unit)
    if FS.IsSecret(situation) then return reactionFn(unit) end
    if situation == nil then return reactionFn(unit) end

    if situation >= 2 then
        return COLOR_ENGAGEMENT_AGGRO
    elseif situation == 0 or situation == 1 then
        return COLOR_ENGAGEMENT_NEUTRAL
    end
    return reactionFn(unit)
end

-------------------------------------------------------------------------------
-- Fallback aura icons (Dispatch 4), used only when the aura container template
-- is missing: a fixed pool of AURA_ICON_MAX small real spell icons, cloned from
-- TargetAuras.lua's aura-icon construction and simplified for a nameplate dot
-- row -- no tooltip (OnEnter/OnLeave), no per-filter container, just icon +
-- tintable border + stack count.
-------------------------------------------------------------------------------

-- True when this client ships the aura container template. Decided once at load
-- (a plain Blizzard global, safe before Theme.lua): the container path and the
-- fallback custom row are mutually exclusive, and the fallback's UNIT_AURA
-- registration below depends on the answer.
local function DetectAuraContainers()
    local info = _G.C_XMLUtil and _G.C_XMLUtil.GetTemplateInfo
    if type(info) ~= "function" then return false end
    local ok, result = pcall(info, AURA_CONTAINER_TEMPLATE)
    return ok and result ~= nil and result ~= false
end
local USE_AURA_CONTAINERS = DetectAuraContainers()
-- Set (never cleared) when container builds keep failing: from then on the plates
-- use the fallback custom row, built lazily (EnsureAuraIcons).
local auraContainersGaveUp = false
local function AuraContainersActive()
    return USE_AURA_CONTAINERS and not auraContainersGaveUp
end

-- Prints a failure message once per label instead of once per aura/event.
-- Shared plumbing lives in FrameHelpers.lua (FS.FrameHelpers.NewStepRunner);
-- this file keeps its own message wording, same per-file duplication
-- convention TargetAuras.lua/Buffs.lua/PartyFrames.lua each follow.
-- Built lazily on first use, not at file scope: this file loads FIRST in the
-- .toc, before FrameHelpers.lua, so FS.FrameHelpers isn't populated yet at
-- file-load time -- same constraint GetPowerTypeColors (below) is already
-- under.
local ReportOnce
local function EnsureReportOnce()
    if not ReportOnce then
        _, ReportOnce = FS.FrameHelpers.NewStepRunner(function(label)
            return "ForeverSynthwave nameplates: " .. label
        end)
    end
    return ReportOnce
end

local function ReadAuraSlot(unit, index, filter)
    return FS.FrameHelpers.ReadAuraSlot(unit, index, filter, EnsureReportOnce())
end

-- Recolors an aura icon's SkinButton border. Dup of TargetAuras.lua's
-- TintAuraBorder (per-file helper duplication convention, see
-- FrameHelpers.lua's header).
local function TintAuraIconBorder(skin, color)
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

-- Engine countdown font for the aura dots' Cooldown frames: one shared font
-- object, built lazily on the first icon (FS.Theme is not loaded at file
-- scope) and handed to Cooldown:SetCountdownFont by global name. Falls back
-- to the stock font when the bundled mono file does not load, same as
-- ApplyFont. Size matches the 8pt stack count; the icon is only
-- AURA_ICON_SIZE wide.
local AURA_COUNTDOWN_FONT = "FSPlateAuraCountdownFont"
local AURA_COUNTDOWN_SIZE = 8
local auraCountdownFontReady

local function EnsureAuraCountdownFont()
    if auraCountdownFontReady ~= nil then return auraCountdownFontReady end
    auraCountdownFontReady = false
    if type(CreateFont) ~= "function" then return false end
    local ok, fontObject = pcall(CreateFont, AURA_COUNTDOWN_FONT)
    if not ok or not fontObject then return false end
    local set = pcall(function()
        if not fontObject:SetFont(FS.Theme.FONT_MONO, AURA_COUNTDOWN_SIZE, FONT_FLAGS) then
            fontObject:SetFont("Fonts\\FRIZQT__.TTF", AURA_COUNTDOWN_SIZE, FONT_FLAGS)
        end
    end)
    auraCountdownFontReady = set and true or false
    return auraCountdownFontReady
end

-- Engine-driven countdown: the Cooldown frame keeps sweeping and counting on
-- its own once SetCooldown is called, so the timer stays live through combat
-- even though aura reads (and so ApplyAuraIcon) are refused there. A Lua
-- ticker would freeze at the last out-of-combat read instead.
local function InsetAuraCooldown(cd)
    -- Inset 1px so the sweep does not tint the SkinButton border ring.
    local parent = cd:GetParent()
    cd:ClearAllPoints()
    cd:SetPoint("TOPLEFT", parent, "TOPLEFT", 1, -1)
    cd:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", -1, 1)
end

local function StyleAuraCooldown(cd)
    InsetAuraCooldown(cd)
    if cd.SetReverse then cd:SetReverse(true) end
    if cd.SetDrawEdge then cd:SetDrawEdge(false) end
    if cd.SetDrawBling then cd:SetDrawBling(false) end
    if cd.SetHideCountdownNumbers then cd:SetHideCountdownNumbers(false) end
    if cd.SetCountdownFont and EnsureAuraCountdownFont() then
        cd:SetCountdownFont(AURA_COUNTDOWN_FONT)
    elseif cd.GetRegions then
        -- No SetCountdownFont: restyle the template's own countdown FontString.
        for _, region in ipairs({ cd:GetRegions() }) do
            if region.GetObjectType and region:GetObjectType() == "FontString" then
                ApplyFont(region, AURA_COUNTDOWN_SIZE)
            end
        end
    end
end

local function ClearAuraCooldown(button)
    local cd = button.cooldown
    if not cd then return end
    if cd.Clear then cd:Clear() else cd:Hide() end
end

-- Icon + stack count, skinned once via Theme.SkinButton (same idempotent
-- border/glow overlay TargetAuras.lua's CreateAuraButton uses). Initial
-- border color is irrelevant -- UpdateAuraIcons retints every shown icon on
-- every refresh -- but SkinButton requires one at construction time.
local function CreateAuraIcon(parent)
    local button = CreateFrame("Frame", nil, parent)
    button:SetSize(AURA_ICON_SIZE, AURA_ICON_SIZE)

    local icon = button:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(button)
    button.icon = icon

    -- Cooldown sweep + countdown above the icon texture. Feature-detected:
    -- the template is tried first, then a bare Cooldown frame, and the icon
    -- simply has no timer if neither builds.
    local okCd, cd = pcall(CreateFrame, "Cooldown", nil, button, "CooldownFrameTemplate")
    if not okCd or not cd then
        okCd, cd = pcall(CreateFrame, "Cooldown", nil, button)
    end
    if okCd and cd then
        if not pcall(StyleAuraCooldown, cd) then
            InsetAuraCooldown(cd)
        end
        button.cooldown = cd
    end

    -- Stack count on its own host frame one level above the Cooldown, so the
    -- centered countdown numbers and the sweep never cover it.
    local countHost = CreateFrame("Frame", nil, button)
    countHost:SetAllPoints(button)
    countHost:SetFrameLevel((cd and cd:GetFrameLevel() or button:GetFrameLevel()) + 1)
    local count = countHost:CreateFontString(nil, "OVERLAY")
    count:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -1, 1)
    ApplyFont(count, 8)
    button.count = count

    FS.Theme.SkinButton(button, { count = count, borderColor = FS.Theme.COLOR_BORDER })

    button:Hide()
    return button
end

-- Opaque track-colored erase quads round a StatusBar fill's corners (MaskTexture
-- does not clip on this client). The host sits at bar + BAR_CORNER_MASK_LEVEL
-- so it clears the caret host (bar+2) and clips its children, which keeps the
-- quads from spilling past the bar's left edge. Parented to the bar so the
-- mask follows the bar's Show/Hide.
--
-- Cut corners ("cut"): the plate chrome is cut TOP-LEFT and BOTTOM-RIGHT at
-- SLICE_MARGIN (6), and the fill sits BAR_FILL_INSET inside it. The anti_cut
-- piece of the SAME chamfer already bakes its leg as c - 0.586 for that 1px
-- inset, so its diagonal lands parallel, 1px inside the plate's cut: the fill
-- chamfer is the chrome's (6), NOT chrome minus inset (that would leave fill
-- showing past the plate cut). It is not capped by the bar's height: the 5px
-- power strip still needs the 6 leg, and its quad overhangs the bar by one
-- row at ~8% coverage. `bottomOnly` (the power strip) hides the TOP-LEFT erase
-- quad: the strip hangs flush under the health bar, so its TOP-LEFT is never a
-- plate corner.
--
-- The cut is a FIXED shape: only the two static quads at the BAR's corners are
-- drawn, and the fill is clipped by them, so its right end is square at every
-- level and takes the chamfer only when it reaches the end of the bar. There is
-- deliberately NO leading-edge quad under "cut" (Parker, playtest 2026-10-04:
-- "when the HP is dropping it has the line and the corner"): a quad riding the
-- fill's right edge (Theme.AddLeadingEdgeCorners) is right for a rounded pill
-- end, but here it carved a travelling bottom-right notch into the fill and
-- into the caret line at every mid-bar level, and at full HP it drew a second,
-- doubly opaque copy of the static BOTTOM-RIGHT quad. Round keeps it.
local function AddRoundedFillMask(bar, fillHeight, bottomOnly)
    local theme = FS.Theme
    local cut = theme.CHROME_CORNERS == "cut"
    local radius
    if cut then
        radius = theme.SnapCut(theme.SLICE_MARGIN)
    else
        -- Capped at the chrome's own corner radius minus the inset so the fill
        -- stays concentric with the border; a rounder fill leaves dark track gaps.
        radius = math.max(1, math.min(fillHeight / 2, theme.SLICE_MARGIN - theme.BAR_FILL_INSET))
    end
    local cornerMask = CreateFrame("Frame", nil, bar)
    cornerMask:SetAllPoints(bar)
    cornerMask:SetFrameLevel(bar:GetFrameLevel() + theme.BAR_CORNER_MASK_LEVEL)
    if cornerMask.SetClipsChildren then
        cornerMask:SetClipsChildren(true)
    end
    local fillCorners = theme.AddFillCorners(cornerMask, bar, theme.COLOR_BAR_TRACK, radius)
    if not cut then
        theme.AddLeadingEdgeCorners(cornerMask, bar, theme.COLOR_BAR_TRACK, radius)
    end
    bar.fsFillCorners = fillCorners
    bar.fsFillBottomOnly = bottomOnly
    if cut and bottomOnly and type(fillCorners) == "table" and type(fillCorners.quads) == "table" then
        for _, quad in ipairs(fillCorners.quads) do
            if quad.fsCutCorner == "TOPLEFT" then quad:Hide() end
        end
    end
    return cornerMask
end

-- The plate stroke is a nine-slice, drawn at SLICE_MARGIN texels with ONE texel per
-- physical SCREEN pixel, while the erase wedges are quads sized in the plate's own
-- units. At a plate scale above one pixel per unit the wedge therefore outgrows the
-- stroke's chamfer and leaves a dark wedge between border and fill at the cut corners
-- (playtest 2026-10-04, full HP: stroke chamfer 5 px, fill cut 7.5 px at 1.44 px per
-- unit: "a missing corner of the bar"). Size the wedge to the stroke's chamfer in
-- units instead: SLICE_MARGIN pixels, snapped to the baked set. Pixel size in the
-- frame's units is PixelUtil's factor over the frame's effective scale (ChevronCastBar's
-- rule); a missing API or an odd answer keeps the unscaled SLICE_MARGIN, the old look.
-- UNVERIFIED in game: the one-texel-per-pixel reading comes from one screenshot.
-- Returns the pixel size in the plate's units (factor / effective scale), or nil when
-- either answer is missing, secret or not a positive number.
local function PlatePixelSize(root)
    local factor = PixelUtil and PixelUtil.GetPixelToUIUnitFactor and PixelUtil.GetPixelToUIUnitFactor()
    local okScale, eff = pcall(root.GetEffectiveScale, root)
    if okScale and type(factor) == "number" and type(eff) == "number"
        and not FS.IsSecret(factor) and not FS.IsSecret(eff) and factor > 0 and eff > 0 then
        return factor / eff, factor, eff
    end
    return nil
end

local function PlateFillCut(root)
    local theme = FS.Theme
    local pixel = PlatePixelSize(root)
    if pixel then
        return theme.SnapCut(theme.SLICE_MARGIN * pixel)
    end
    return theme.SnapCut(theme.SLICE_MARGIN)
end

-- Re-fits both fills' static erase quads when the plate's pixel scale changed (target
-- selection scales a plate). Cut chrome only; the power strip keeps its TOP-LEFT quad hidden.
local function FitPlateFillCuts(root)
    if FS.Theme.CHROME_CORNERS ~= "cut" then return end
    local c = PlateFillCut(root)
    if c == root.fsFillCut then return end
    for _, bar in ipairs({ root.healthBar, root.powerBar }) do
        local handle = bar.fsFillCorners
        if type(handle) == "table" and handle.SetRadius then
            handle.SetRadius(c)
            if bar.fsFillBottomOnly and c > 0 then
                for _, quad in ipairs(handle.quads) do
                    if quad.fsCutCorner == "TOPLEFT" then quad:Hide() end
                end
            end
        end
    end
    -- Recorded only after the whole loop ran: a throw above leaves the old value, so the
    -- next UpdateGlowState retries instead of treating a half-applied fit as done.
    root.fsFillCut = c
end

-- Every live plate. The plate's pixel size changes without any unit event: a UI scale or
-- display change, and the engine's own plate-scale CVars (selected, global, min, max, larger)
-- applied to a plate AFTER our target-changed handler ran, hence the deferred second pass.
local PLATE_SCALE_CVARS = {
    nameplateselectedscale = true, nameplateglobalscale = true, nameplateminscale = true,
    nameplatemaxscale = true, nameplatelargerscale = true, nameplatescale = true,
}
local function RefitAllPlates()
    for _, root in pairs(FS.framesByUnit) do
        FitPlateFillCuts(root)
    end
end
-- One-frame-later refit for the engine applying plate scale after our handler. Coalesced:
-- a pending timer already covers every live plate, so triggers during that frame add none.
local refitPending = false
local function RefitAllPlatesDeferred()
    if refitPending then return end
    if type(C_Timer) == "table" and type(C_Timer.After) == "function" then
        C_Timer.After(0, function()
            refitPending = false
            RefitAllPlates()
        end)
        -- After the call: a throwing After must not leave the flag stuck. The callback runs a
        -- frame later, so it cannot clear the flag before this line sets it.
        refitPending = true
    end
end
local function RefitAllPlatesSoon()
    RefitAllPlates()
    RefitAllPlatesDeferred()
end

-- The erase quads sit ABOVE the plate's border (they are children of the
-- bars), and the 1px-inset fill rect overlaps the diagonal stroke, so the track
-- colour would paint a dark gap over it. Re-host the SAME border texture
-- (root.fsBorder, so the retint in UpdateGlowState still reaches it) on a
-- frame above both masks. Region:SetParent keeps the root anchors. Pcall'd
-- like every engine call here; a refusal just leaves the stroke where it was.
-- LogDegradeOnce does not dedupe by key, so latch here.
local strokeRaiseWarned = false
local function RaisePlateStroke(root)
    local theme = FS.Theme
    if theme.CHROME_CORNERS ~= "cut" or not root.fsBorder then return end
    local strokeHost = CreateFrame("Frame", nil, root)
    strokeHost:SetAllPoints(root)
    local level = math.max(root.healthBar:GetFrameLevel(), root.powerBar:GetFrameLevel())
        + theme.BAR_CORNER_MASK_LEVEL + 1
    strokeHost:SetFrameLevel(level)
    if not pcall(root.fsBorder.SetParent, root.fsBorder, strokeHost) and not strokeRaiseWarned then
        strokeRaiseWarned = true
        FS.LogDegradeOnce("nameplate_stroke_reparent",
            "|cffff4488ForeverSynthwave|r: nameplate stroke re-host refused, the plate border may sit under the corner masks")
    end
end

-- Root anchoring, shared by every acquire (a pooled root changes plate, and
-- ClearAllPoints wipes both of its anchors). TOP-anchored, not CENTER: a
-- CENTER anchor would move root's top whenever its height changes, so the
-- power strip appearing would jog the health bar and name. Offset up by half
-- the BASE height so TOP lands exactly where CENTER used to at base height.
-- The BOTTOM is derived, not set: it follows the hidden "sizer" StatusBar
-- built in CreatePlateFrame, so root's height tracks the unit's power pool
-- without Lua ever reading the secret max. The sizer hangs off the PLATE (its
-- TOP at root's base bottom), never off root, so root -> sizer texture ->
-- sizer -> plate has no anchor cycle.
local function AnchorPlateRoot(root, plate)
    root:ClearAllPoints()
    root.fsSizer:ClearAllPoints()
    root.fsSizer:SetPoint("TOP", plate, "CENTER", 0, -root.baseHeight / 2)
    root:SetPoint("TOP", plate, "CENTER", 0, root.baseHeight / 2)
    root:SetPoint("BOTTOM", root.fsSizerAnchor, "BOTTOM")
end

-- Once-per-session latches for the two sizer degrade logs (LogDegradeOnce does
-- not dedupe by key, so each caller latches its own boolean).
local sizerSetValueWarned = false
local sizerNoReverseWarned = false

-- Fallback aura dots: a pool of AURA_ICON_MAX icons at the RIGHT end of the
-- name row. Anchored off healthBar's own fixed TOPRIGHT corner -- NOT
-- nameText's variable width, which grows/shrinks with the unit's name --
-- at the same vertical level nameText's own anchor above uses (the
-- identical +2 y-offset off healthBar's TOP edge). Icon 1 sits at the
-- right end; 2..5 grow leftward off the previous icon's own LEFT edge.
-- Built once per POOLED frame like raidMarker/questIcon, never per-acquire;
-- ReleaseFrame hides all AURA_ICON_MAX of them. Fallback row only (no aura
-- container template, or the container path was given up); otherwise the
-- plate's AuraContainer (AttachAuraContainer) is the row and root.auraIcons
-- stays nil. Idempotent.
local function EnsureAuraIcons(root)
    if root.auraIcons then return end
    local icons = {}
    local prevAuraIcon
    for i = 1, AURA_ICON_MAX do
        local auraIcon = CreateAuraIcon(root)
        if i == 1 then
            auraIcon:SetPoint("BOTTOMRIGHT", root.healthBar, "TOPRIGHT", 0, AURA_ROW_Y)
        else
            auraIcon:SetPoint("RIGHT", prevAuraIcon, "LEFT", -AURA_ICON_GAP, 0)
        end
        icons[i] = auraIcon
        prevAuraIcon = auraIcon
    end
    root.auraIcons = icons
end

local function CreatePlateFrame()
    local root = CreatePlateRootFrame()
    -- Inset the fill from the root so the rounded chrome's border/glow has
    -- somewhere to show: a flush child StatusBar would composite above
    -- root's own regions and hide it (see Theme.lua's pill-bar pattern note).
    local inset = FS.Theme.BAR_FILL_INSET
    -- The plate's outer size is fixed by PLATE_OUTER_PAD, not by the inset, so
    -- a thinner inset grows the fill instead of shrinking the plate.
    local fillWidth = BAR_WIDTH + 2 * (PLATE_OUTER_PAD - inset)
    local fillHeight = BAR_HEIGHT + 2 * (PLATE_OUTER_PAD - inset)
    -- baseHeight is the collapsed (no power bar) height, used for the anchor
    -- math in AnchorPlateRoot. Root's real height comes from its TOP and BOTTOM
    -- anchors (only the width is set here): UpdatePower feeds the unit's power
    -- max into the sizer below, which grows root by POWER_BAR_HEIGHT +
    -- POWER_BAR_GAP when the unit has a power pool and leaves it at baseHeight
    -- when it has none (a no-mana NPC reports power type mana with max 0).
    root.baseHeight = BAR_HEIGHT + 2 * PLATE_OUTER_PAD
    root:SetWidth(BAR_WIDTH + 2 * PLATE_OUTER_PAD)
    root:SetFrameStrata("LOW")
    ApplyBackdrop(root)

    -- Sizer: an invisible VERTICAL StatusBar whose fill only exists so the
    -- engine can turn the SECRET power max into layout. UpdatePower does
    -- sizer:SetValue(UnitPowerMax(...)), which clamps into 0..1: max 0 (no
    -- power pool) is empty, any real pool is full. Lua never sees the number.
    -- It is POWER_BAR_HEIGHT + POWER_BAR_GAP tall with its TOP at root's base
    -- bottom (AnchorPlateRoot) and fills TOP-DOWN (SetReverseFill), so the
    -- fill texture's BOTTOM sits at the base bottom when empty and one strip
    -- lower when full. Root's BOTTOM anchors to that texture BOTTOM: base
    -- height at value 0, base + strip at value 1. A rect at exactly value 0 is
    -- not guaranteed for this vertical reverse-fill bar, which is why the range
    -- floor below is -0.001: it keeps a sub-pixel nonzero fill when empty.
    -- Without SetReverseFill the fill would grow bottom-up and invert the
    -- result (a manaless plate would grow), so root BOTTOM then anchors to the
    -- sizer FRAME's bottom instead: always grown, the pre-sizer behavior.
    local sizer = CreateFrame("StatusBar", nil, root)
    sizer:SetOrientation("VERTICAL")
    sizer:SetSize(1, POWER_BAR_HEIGHT + POWER_BAR_GAP)
    sizer:SetStatusBarTexture(FS.Theme.FLAT_TEXTURE)
    sizer:GetStatusBarTexture():SetVertexColor(0, 0, 0, 0)
    sizer:SetAlpha(0)
    -- Lower bound is a hair below 0 so an empty pool (max 0, or the SetValue(0)
    -- resets) still leaves the fill a sub-pixel nonzero height: the texture
    -- never has zero size, so the BOTTOM anchor always resolves. Real pools
    -- (max >= 1) clamp to full, so they are unaffected.
    sizer:SetMinMaxValues(-0.001, 1)
    sizer:SetValue(0)
    root.fsSizer = sizer
    if type(sizer.SetReverseFill) == "function" and pcall(sizer.SetReverseFill, sizer, true) then
        root.fsSizerAnchor = sizer:GetStatusBarTexture()
    else
        root.fsSizerAnchor = sizer
        if not sizerNoReverseWarned then
            sizerNoReverseWarned = true
            FS.LogDegradeOnce("plate_sizer_noreverse",
                "|cffff4488ForeverSynthwave|r: StatusBar:SetReverseFill unavailable, nameplates always reserve the power strip")
        end
    end

    local healthBar = CreateFrame("StatusBar", nil, root)
    healthBar:SetSize(fillWidth, fillHeight)
    healthBar:SetPoint("TOPLEFT", root, "TOPLEFT", inset, -inset)
    healthBar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    healthBar:SetMinMaxValues(0, 1)
    healthBar:SetValue(1)
    root.healthBar = healthBar
    root.barTexture = healthBar:GetStatusBarTexture()
    ApplyDefaultFill(root)

    -- Pulsing leading-edge caret, shared with UnitFrames/PartyFrames' health
    -- bars (FrameHelpers.lua) -- a 3px colored line (health green, via the
    -- FS.Theme.COLOR_CARET_HEALTH color argument this call passes) with a
    -- gentle alpha pulse. CreatePlateFrame only runs when the pool is empty (see
    -- AcquireFrame), so this builds the caret once per POOLED frame, not
    -- once per acquire. Safe to read FS.FrameHelpers/FS.Theme here despite
    -- this file loading first in the .toc: this function only ever runs at
    -- runtime (from NAME_PLATE_UNIT_ADDED), by which point every file has
    -- loaded. No power bar on nameplates anyway, so there's only ever the
    -- one caret to build.
    healthBar.caret = FS.FrameHelpers.CreateCaret(healthBar, FS.Theme.COLOR_CARET_HEALTH)

    -- Rounds the fill at both ends at every fill level: static erase quads for
    -- the left corners plus engine-anchored ones that follow the fill's right
    -- edge. The radius is capped concentric with the chrome inside the helper.
    AddRoundedFillMask(healthBar, fillHeight)

    -- Power strip: hidden until UpdatePower resolves the unit's power type.
    -- Full health-bar width, directly below it inside the plate chrome.
    -- Flat fill, colored by power type (mana/rage/energy, see
    -- GetPowerTypeColors/ApplyPowerFillColor) -- unlike the health bar there
    -- is no reaction/tap-denied recolor here, only the power-type color.
    -- Painted mana-cyan here as the initial placeholder, same reasoning as
    -- ApplyDefaultFill's health placeholder: UpdatePower repaints it via
    -- ApplyPowerFillColor as soon as the frame acquires a unit, so this is
    -- never seen mid-fight.
    local powerBar = CreateFrame("StatusBar", nil, root)
    powerBar:SetSize(fillWidth, POWER_BAR_HEIGHT)
    powerBar:SetPoint("TOPLEFT", healthBar, "BOTTOMLEFT", 0, -POWER_BAR_GAP)
    powerBar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    powerBar:SetMinMaxValues(0, 1)
    powerBar:SetValue(1)
    powerBar:GetStatusBarTexture():SetVertexColor(unpack(FS.Theme.COLOR_POWER))
    powerBar:Hide()
    root.powerBar = powerBar

    powerBar.caret = FS.FrameHelpers.CreateCaret(powerBar, FS.Theme.COLOR_CARET_POWER)

    AddRoundedFillMask(powerBar, POWER_BAR_HEIGHT, true)
    RaisePlateStroke(root)

    local nameText = root:CreateFontString(nil, "OVERLAY")
    ApplyFont(nameText, FONT_SIZE)
    nameText:SetTextColor(unpack(COLOR_TEXT))
    -- Left-aligned off the health bar's own LEFT edge (Parker's ask), not
    -- centered -- a long name then grows rightward instead of shifting the
    -- whole label off-center over the bar.
    nameText:SetPoint("BOTTOMLEFT", healthBar, "TOPLEFT", 0, 2)
    nameText:SetJustifyH("LEFT")
    root.nameText = nameText

    -- Raid target marker: centered above the name (locked design spec). Built
    -- here, AFTER nameText exists, so it can anchor off it -- anchoring to the
    -- name rather than root/healthBar means it tracks the name label's own
    -- position (which is itself left-aligned off healthBar). Hidden until
    -- UpdateRaidMarker resolves a live index.
    local raidMarker = root:CreateTexture(nil, "OVERLAY")
    raidMarker:SetSize(RAID_MARKER_SIZE, RAID_MARKER_SIZE)
    raidMarker:SetPoint("BOTTOM", nameText, "TOP", 0, RAID_MARKER_GAP)
    raidMarker:SetTexture("Interface\\TargetingFrame\\UI-RaidTargetingIcons")
    raidMarker:Hide()
    root.raidMarker = raidMarker

    -- Quest objective indicator: a small "!" anchored off nameText's own LEFT
    -- edge (not root's) -- nameText auto-sizes around a single-point anchor, so
    -- anchoring here tracks it correctly regardless of name length. Hidden until
    -- UpdateQuestIcon resolves the unit's quest relevance.
    local questIcon = root:CreateTexture(nil, "OVERLAY")
    questIcon:SetSize(QUEST_ICON_SIZE, QUEST_ICON_SIZE)
    questIcon:SetPoint("RIGHT", nameText, "LEFT", -QUEST_ICON_GAP, 0)
    questIcon:SetTexture("Interface\\GossipFrame\\AvailableQuestIcon")
    questIcon:SetVertexColor(COLOR_QUEST_AMBER[1], COLOR_QUEST_AMBER[2], COLOR_QUEST_AMBER[3], COLOR_QUEST_AMBER[4] or 1)
    questIcon:Hide()
    root.questIcon = questIcon

    -- Fallback aura dots (EnsureAuraIcons): only without the container path. A
    -- plate built before the container path was given up gets its row lazily.
    if not AuraContainersActive() then EnsureAuraIcons(root) end

    -- Cast bar: seated BELOW root, OUTSIDE the nine-slice chrome, so
    -- showing/hiding or resizing it (it never resizes) can't touch root's own
    -- height the way the mana bar above deliberately does. Anchored off
    -- root's own edges (not healthBar's) inset by `inset` on each side so its
    -- width matches healthBar exactly despite anchoring to the wider root.
    -- Flat track/border chrome (AddCastBarChrome), not nine-sliced and not a
    -- pill bar -- this frame has no shell to round against. The gap clamps up
    -- to Theme.SLICE_GLOW_PAD (read at runtime, this file loads before Theme)
    -- so the plate's own outer glow, which extends past root by that much,
    -- can't bleed onto the cast bar.
    local castBarGap = math.max(CAST_BAR_GAP, FS.Theme.SLICE_GLOW_PAD)
    local castBar = CreateFrame("StatusBar", nil, root)
    castBar:SetPoint("TOPLEFT", root, "BOTTOMLEFT", inset, -castBarGap)
    castBar:SetPoint("TOPRIGHT", root, "BOTTOMRIGHT", -inset, -castBarGap)
    castBar:SetHeight(CAST_BAR_HEIGHT)
    castBar:SetStatusBarTexture(FS.Theme.FLAT_TEXTURE)
    castBar:SetStatusBarColor(FS.Theme.COLOR_CAST_INTERRUPTIBLE[1], FS.Theme.COLOR_CAST_INTERRUPTIBLE[2],
        FS.Theme.COLOR_CAST_INTERRUPTIBLE[3], 1)
    castBar:SetMinMaxValues(0, 1)
    castBar:SetValue(0)
    AddCastBarChrome(castBar)
    castBar:Hide() -- shown only while a cast/channel is active, like CastBars.lua

    -- Shield overlay: tints over the fill to signal "can't interrupt this",
    -- alpha 0 (invisible) until a cast actually seeds/flips that state. Inset
    -- 1px from castBar's own edges so it never paints over AddCastBarChrome's
    -- hairline border when shown.
    local shield = castBar:CreateTexture(nil, "OVERLAY", nil, 1)
    shield:SetPoint("TOPLEFT", castBar, "TOPLEFT", 1, -1)
    shield:SetPoint("BOTTOMRIGHT", castBar, "BOTTOMRIGHT", -1, 1)
    shield:SetColorTexture(1, 1, 1, 1)
    shield:SetVertexColor(FS.Theme.COLOR_CAST_NO_INTERRUPT[1], FS.Theme.COLOR_CAST_NO_INTERRUPT[2],
        FS.Theme.COLOR_CAST_NO_INTERRUPT[3], 1)
    shield:SetAlpha(0)
    castBar.shield = shield

    local castNameText = castBar:CreateFontString(nil, "OVERLAY")
    ApplyFont(castNameText, CAST_NAME_FONT_SIZE)
    castNameText:SetTextColor(unpack(COLOR_TEXT))
    castNameText:SetJustifyH("LEFT")
    castNameText:SetPoint("LEFT", castBar, "LEFT", 2, 0)
    castNameText:SetPoint("RIGHT", castBar, "RIGHT", -2, 0)
    castBar.nameText = castNameText

    root.castBar = castBar

    return root
end

-------------------------------------------------------------------------------
-- Aura containers (one AuraContainer per plate)
-------------------------------------------------------------------------------
-- The engine reads the auras and builds the icons, so no aura data ever enters
-- addon Lua and the row works in combat, where every addon aura read is refused
-- or returns secrets. Modelled on Plater_Auras.lua (createAuraContainers,
-- initAuraFrame, CreateOrUpdateAuraContainers) and FSProbe.lua's BuildContainer.
-- What was actually run on this client (WoW Forever 1.60.1): FSProbe built its
-- container OUT of combat, and only SetUnit, SetEnabled(true), Show and a retarget
-- ran in combat. UNVERIFIED in game: nameplate unit tokens, creating a container
-- in combat, and SetParent / ClearAllPoints / SetPoint / SetFrameLevel on one.
--
--  * Both groups are added ONCE, when the container is built, never retinted or
--    re-filtered afterwards: each group's border colour is baked into its
--    initializeFrame.
--  * initializeFrame runs when the engine builds a button, before it turns
--    restricted. Everything is set up there, each step pcall'd on its own, mouse
--    off first.
--  * Containers are pooled apart from the plate frames, built out of combat
--    (TopUpAuraPool) and handed out by NAME_PLATE_UNIT_ADDED. A plate with no
--    container is retried when combat ends (RetryBareAuraPlates), and has no
--    row until then (WarnAuraContainer logs it once).
--  * AuraContainer:SetUnit does nothing when the token is unchanged, and a
--    pooled container keeps the token it last had (fsUnit), so a plate that
--    reuses the same token skips SetUnit; SetEnabled(true) and Show rebuild the
--    auras on their own (Blizzard_AuraContainer.lua: SetEnabled on a change and
--    OnShow_Intrinsic both call UpdateAllAuras). A container still enabled and
--    shown when it is handed out is rescanned by hand.
--  * A build that fails after CreateFrame keeps its frame in `brokenContainers`
--    (a frame cannot be destroyed) and is never pooled. AURA_BUILD_FAIL_LIMIT
--    consecutive failures give the container path up for the session: the
--    fallback custom row (EnsureAuraIcons) takes over, and logs once. So do
--    AURA_BUILD_FAIL_LIMIT consecutive out-of-combat attach failures
--    (auraAttachFailures; a lockdown refusal is not a fault: it neither counts
--    nor resets the count, only a successful attach resets it).

local auraPool = {}
local auraPoolTopUpPending = false
-- Frames whose build or attach failed. Never pooled, never handed out.
local brokenContainers = {}
local auraBuildFailures = 0
-- Consecutive out-of-combat attach failures (a real SetParent or SetUnit fault).
-- A failure in combat never counts and never resets the count; only a successful
-- attach does. The AURA_BUILD_FAIL_LIMIT-th consecutive out-of-combat attach
-- failure gives up.
local auraAttachFailures = 0
-- An attach was refused in this fight: do not build more containers until the
-- fight ends, or every plate add would leave another one behind.
local auraAttachRefusedInCombat = false
-- LogDegradeOnce does not dedupe, so this file latches its own warnings.
local auraContainerWarned = false
local auraGiveUpWarned = false
-- Set after eventFrame exists (end of file): starts the fallback row's UNIT_AURA.
local EngageAuraFallback

-- InCombatLockdown, fail closed: a throwing check reads as "in combat".
local function InCombatSafe()
    local ok, inCombat = pcall(InCombatLockdown)
    return not ok or inCombat and true or false
end

local function WarnAuraContainer(err)
    if auraContainerWarned then return end
    auraContainerWarned = true
    FS.LogDegradeOnce("plate_aura_container",
        "|cffff4488ForeverSynthwave|r: nameplate aura container unavailable, some plates have no debuff row ("
        .. tostring(err) .. ")")
end

-- Gives the container path up for the session and moves every plate to the
-- fallback custom row (out of combat reads only).
local function GiveUpAuraContainers(err)
    if auraContainersGaveUp then return end
    auraContainersGaveUp = true
    if not auraGiveUpWarned then
        auraGiveUpWarned = true
        FS.LogDegradeOnce("plate_aura_container_giveup",
            "|cffff4488ForeverSynthwave|r: nameplate aura container failed " .. AURA_BUILD_FAIL_LIMIT
            .. " times, using the fallback debuff row (out of combat only) (" .. tostring(err) .. ")")
    end
    if EngageAuraFallback then EngageAuraFallback() end
end

-- obj:method(...) when the method exists, any error swallowed. True unless the
-- method existed and threw (a missing method is not a failure), so one refusing
-- setter never stops the next call.
local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

-- Flat 1px border for when Theme.SkinButton does not work on an aura button.
local function AddSimpleAuraBorder(button, color)
    local r, g, b, a = color[1], color[2], color[3], color[4] or 1
    local function edge(p1, p2, w, h)
        local t = button:CreateTexture(nil, "OVERLAY")
        t:SetColorTexture(r, g, b, a)
        t:SetPoint(p1, button, p1)
        t:SetPoint(p2, button, p2)
        if w then t:SetWidth(w) end
        if h then t:SetHeight(h) end
    end
    edge("TOPLEFT", "TOPRIGHT", nil, 1)
    edge("BOTTOMLEFT", "BOTTOMRIGHT", nil, 1)
    edge("TOPLEFT", "BOTTOMLEFT", 1, nil)
    edge("TOPRIGHT", "BOTTOMRIGHT", 1, nil)
end

-- initializeFrame body. `getColor` returns the group's border colour table.
local function InitAuraButton(button, getColor)
    -- First, before the button can turn restricted: the icons must never take
    -- clicks or show tooltips in a fight (Plater_Auras.lua does the same).
    Quiet(button, "SetMouseMotionEnabled", false)
    Quiet(button, "SetMouseClickEnabled", false)
    Quiet(button, "SetHideTooltipInCombat", true)

    pcall(function()
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetAllPoints(button)
        button:SetIcon(icon)
    end)

    -- Sweep only: the countdown numbers are the duration text below. Inset 1px so
    -- the sweep does not tint the border ring.
    local cooldown
    pcall(function()
        cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        Quiet(cooldown, "EnableMouse", false)
        Quiet(cooldown, "EnableMouseMotion", false)
        Quiet(cooldown, "SetPoint", "TOPLEFT", button, "TOPLEFT", 1, -1)
        Quiet(cooldown, "SetPoint", "BOTTOMRIGHT", button, "BOTTOMRIGHT", -1, 1)
        Quiet(cooldown, "SetHideCountdownNumbers", true)
        Quiet(cooldown, "SetDrawEdge", false)
        Quiet(cooldown, "SetDrawBling", false)
        Quiet(cooldown, "SetReverse", true)
        button:SetDurationCooldown(cooldown)
    end)

    pcall(function()
        local text = (cooldown or button):CreateFontString(nil, "OVERLAY")
        ApplyFont(text, AURA_COUNTDOWN_SIZE)
        text:SetPoint("CENTER", button, "CENTER", 0, 0)
        button:SetDurationText(text, {})
    end)

    -- Stack count on its own host one level above the Cooldown, so the sweep and
    -- the duration text never cover it.
    local count
    pcall(function()
        local host = CreateFrame("Frame", nil, button)
        host:SetAllPoints(button)
        Quiet(host, "EnableMouse", false)
        host:SetFrameLevel((cooldown and cooldown:GetFrameLevel() or button:GetFrameLevel()) + 1)
        count = host:CreateFontString(nil, "OVERLAY")
        count:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -1, 1)
        ApplyFont(count, AURA_COUNTDOWN_SIZE)
        button:SetApplicationCount(count)
    end)

    local okColor, color = pcall(getColor)
    if okColor and type(color) == "table" then
        -- The engine-built button is not sized yet (SetSize is last, below), so SkinButton
        -- cannot read a height; hand it the 18px icon chamfer instead of its c = 6 fallback.
        local skinOpts = { count = count, borderColor = color, chamfer = FS.Theme.CutSizeIcon(AURA_ICON_SIZE) }
        if not pcall(FS.Theme.SkinButton, button, skinOpts) then
            pcall(AddSimpleAuraBorder, button, color)
        end
    end

    Quiet(button, "SetSize", AURA_ICON_SIZE, AURA_ICON_SIZE)
end

-- Own debuffs wear Theme.COLOR_HEALTH's pink, everyone else's COLOR_BORDER's
-- violet (D4 locked spec, deliberately NOT TargetAuras.lua's local pink).
local function OwnBorderColor() return FS.Theme.COLOR_HEALTH end
local function OtherBorderColor() return FS.Theme.COLOR_BORDER end

local function NewAuraLayout()
    return {
        elementSpacing = AURA_ICON_GAP,
        lineSpacing = AURA_ICON_GAP,
        groupLineSpacing = AURA_ICON_GAP,
        elementWidth = AURA_ICON_SIZE,
        elementHeight = AURA_ICON_SIZE,
    }
end

-- Builds one container, groups and flow included, disabled and hidden. Raises on
-- failure; callers pcall it. A frame that was created before the failure is parked
-- in brokenContainers, never lost to the garbage and never pooled.
local function CreateAuraContainer()
    local container = CreateFrame("AuraContainer", nil, UIParent, AURA_CONTAINER_TEMPLATE)
    local ok, err = pcall(function()
        container:SetSize(1, 1)
        local sortMethod = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
        local sortDirection = type(_G.AuraContainerSortDirection) == "table"
            and _G.AuraContainerSortDirection.Normal or nil
        local function addGroup(name, filter, max, getColor)
            container:AddAuraGroup(name, filter, {
                maxFrameCount = max,
                sortMethod = sortMethod,
                sortDirection = sortDirection,
                initializeFrame = function(button) InitAuraButton(button, getColor) end,
                layout = NewAuraLayout(),
            })
        end
        addGroup(AURA_GROUP_OWN, AURA_FILTER_OWN, AURA_OWN_MAX, OwnBorderColor)
        addGroup(AURA_GROUP_OTHER, AURA_FILTER_OTHER, AURA_OTHER_MAX, OtherBorderColor)

        local flow = type(_G.AnchorUtil) == "table" and _G.AnchorUtil.FlowDirection or nil
        container:SetFlowLayoutAnchorPoint("BOTTOMRIGHT")
        container:SetFlowLayoutGrowthDirection((flow and flow.Left) or AURA_FLOW_LEFT, (flow and flow.Up) or AURA_FLOW_UP)
        Quiet(container, "SetFlowLayoutMaximumLineSize", AURA_ROW_LINE_SIZE)
        container:SetEnabled(false)
        container:Hide()
    end)
    if not ok then
        Quiet(container, "SetEnabled", false)
        Quiet(container, "Hide")
        brokenContainers[#brokenContainers + 1] = container
        error(err, 0)
    end
    return container
end

-- One build attempt, counted: a success clears the failure count, the
-- AURA_BUILD_FAIL_LIMIT-th consecutive build failure gives the container path up. Returns
-- the container, or nil after a failure.
local function BuildAuraContainer()
    if auraContainersGaveUp then return nil end
    local ok, result = pcall(CreateAuraContainer)
    if ok then
        auraBuildFailures = 0
        return result
    end
    auraBuildFailures = auraBuildFailures + 1
    WarnAuraContainer(result)
    if auraBuildFailures >= AURA_BUILD_FAIL_LIMIT then GiveUpAuraContainers(result) end
    return nil
end

-- Out of combat only, AURA_POOL_BATCH containers per step (the rest follow on a
-- zero-delay timer), until AURA_POOL_TARGET idle ones are waiting. Runs from
-- PLAYER_ENTERING_WORLD and PLAYER_REGEN_ENABLED.
local function TopUpAuraPool()
    if not AuraContainersActive() or InCombatSafe() then return end
    local batched = type(C_Timer) == "table" and type(C_Timer.After) == "function"
    local made = 0
    while #auraPool < AURA_POOL_TARGET do
        if batched and made >= AURA_POOL_BATCH then
            if not auraPoolTopUpPending then
                auraPoolTopUpPending = true
                C_Timer.After(0, function()
                    auraPoolTopUpPending = false
                    TopUpAuraPool()
                end)
            end
            return
        end
        local container = BuildAuraContainer()
        if not container then return end
        auraPool[#auraPool + 1] = container
        made = made + 1
    end
end

-- A pooled container, else (pool empty, even in combat) a new one under pcall.
-- No new build in a fight where an attach was already refused.
local function TakeAuraContainer()
    local container = table.remove(auraPool)
    if container then return container end
    if auraAttachRefusedInCombat and InCombatSafe() then return nil end
    return BuildAuraContainer()
end

-- Every step is separate: one refusing call must not strand the container on a
-- released plate. The container keeps its unit token (fsUnit) for the next
-- AttachAuraContainer. `failed` (an attach that threw) sends it to the BACK of
-- the pool, so the next plate does not pick the same one up, and parks it in
-- brokenContainers when it has failed AURA_ATTACH_FAIL_LIMIT times.
local function ReleaseAuraContainer(root, failed)
    local container = root.auraContainer
    if not container then return end
    root.auraContainer = nil
    Quiet(container, "SetEnabled", false)
    Quiet(container, "Hide")
    Quiet(container, "ClearAllPoints")
    Quiet(container, "SetParent", nil)
    if not failed then
        auraPool[#auraPool + 1] = container
        return
    end
    container.fsAttachFails = (container.fsAttachFails or 0) + 1
    if container.fsAttachFails >= AURA_ATTACH_FAIL_LIMIT then
        brokenContainers[#brokenContainers + 1] = container
    else
        table.insert(auraPool, 1, container)
    end
end

local function AttachAuraContainer(root, unit)
    if not USE_AURA_CONTAINERS then return end
    if auraContainersGaveUp then
        EnsureAuraIcons(root)
        return
    end
    local container = TakeAuraContainer()
    -- nil: no container this time. A build failure that gave the path up has
    -- already moved this plate (already in framesByUnit) to the fallback row.
    if not container then return end
    root.auraContainer = container
    local okLive, enabled, shown = pcall(function() return container:IsEnabled(), container:IsShown() end)
    local wasLive = okLive and enabled == true and shown == true
    local ok, err = pcall(function()
        container:SetParent(root)
        container:ClearAllPoints()
        container:SetPoint("BOTTOMRIGHT", root.healthBar, "TOPRIGHT", 0, AURA_ROW_Y)
        Quiet(container, "SetFrameLevel", root:GetFrameLevel() + AURA_LEVEL_BOOST)
        container:SetEnabled(true)
        if container.fsUnit ~= unit then
            container:SetUnit(unit)
            container.fsUnit = unit
        elseif wasLive then
            -- SetUnit is a no-op for an unchanged token and SetEnabled/Show did
            -- nothing on a container that was already live: re-scan by hand.
            Quiet(container, "UpdateAllAuras")
        end
        container:Show()
    end)
    if ok then
        container.fsAttachFails = nil
        auraAttachFailures = 0
    else
        container.fsUnit = nil
        local inCombat = InCombatSafe()
        if inCombat then
            auraAttachRefusedInCombat = true
        else
            auraAttachFailures = auraAttachFailures + 1
        end
        ReleaseAuraContainer(root, true)
        WarnAuraContainer(err)
        -- A fault that persists out of combat would burn a container per attempt
        -- for the whole session: after AURA_BUILD_FAIL_LIMIT consecutive
        -- out-of-combat attach failures, give up.
        if auraAttachFailures >= AURA_BUILD_FAIL_LIMIT then GiveUpAuraContainers(err) end
    end
end

-- PLAYER_REGEN_ENABLED: every live plate that was refused a container in the
-- fight (no container, no fallback row) gets one more attach. The same counters
-- apply: a failure out of combat counts toward the give-up limit, and once the
-- path is given up (the plates already hold the fallback row) nothing is tried.
-- The in-loop `if not AuraContainersActive() then return end` guard and the
-- `not root.auraIcons` check are defensive and cheap: after a give-up, every
-- bare plate already has a fallback row, and AttachAuraContainer self-guards.
-- They only avoid wasted iterations, not load-bearing.
local function RetryBareAuraPlates()
    for unit, root in pairs(FS.framesByUnit) do
        if not AuraContainersActive() then return end
        if not root.auraContainer and not root.auraIcons then
            AttachAuraContainer(root, unit)
        end
    end
end

-------------------------------------------------------------------------------
-- Pool management
-------------------------------------------------------------------------------

local function AcquireFrame()
    local frame = table.remove(FS.freePool)
    if not frame then
        frame = CreatePlateFrame()
    end
    -- Reset the fill-color cache so the next UpdateFillColor call re-applies
    -- rather than skipping on a stale match left by the plate's PREVIOUS unit.
    frame.fillColor = nil
    -- (No fsFillCut reset: it mirrors the persistent wedge quads, so a pooled plate
    -- landing on another pixel scale is re-fitted by UpdateGlowState's own compare.)
    -- Same reset for the power strip's fill-color cache: without this, a
    -- reacquired pooled plate could keep the PREVIOUS occupant's power color
    -- (e.g. rogue energy yellow -> warlock mana cyan keeps yellow) until a
    -- later UpdatePower call happens to resolve a DIFFERENT color.
    frame.powerFillColor = nil
    -- Same reset for the cached power-TYPE index UpdatePowerValue reads:
    -- without this, a reacquired pooled plate could feed a UNIT_POWER_UPDATE
    -- for the NEW occupant into UnitPower(unit, <previous occupant's power
    -- type>) in the gap between acquire and the new unit's own UpdatePower
    -- call.
    frame.powerType = nil
    -- Sizer back to empty so a reused plate doesn't inherit the previous
    -- unit's height; UpdatePower sets it for the new unit.
    frame.fsSizer:SetValue(0)
    return frame
end

local function ReleaseFrame(unit)
    local frame = FS.framesByUnit[unit]
    if not frame then return end

    -- The aura container goes back to its own pool (disabled, hidden,
    -- unparented), so it is never left on a released frame.
    ReleaseAuraContainer(frame)
    frame:Hide()
    frame:ClearAllPoints()
    frame.unit = nil
    -- Reset the power bar so a reused plate doesn't flash the previous
    -- occupant's power reading before UpdatePower resolves the new unit.
    frame.powerBar:Hide()
    frame.powerBar:SetAlpha(1)
    frame.fsSizer:SetValue(0)
    -- Reset target emphasis so a pooled plate doesn't carry the
    -- previous occupant's dim/highlight until its own UpdateGlowState runs.
    frame:SetAlpha(1)
    frame.fsBorder:SetVertexColor(FS.Theme.COLOR_BORDER[1], FS.Theme.COLOR_BORDER[2],
        FS.Theme.COLOR_BORDER[3], FS.Theme.COLOR_BORDER[4] or 1)
    -- Reset the cast bar so a reused plate doesn't carry the previous
    -- occupant's cast/shield state into its next acquire.
    frame.castActive = false
    frame.castBar:Hide()
    frame.castBar.shield:SetAlpha(0)
    -- Reset the raid marker so a reused plate doesn't flash the previous
    -- occupant's icon before UpdateRaidMarker resolves the new unit.
    frame.raidMarker:Hide()
    -- Reset the quest icon so a reused plate doesn't flash the previous
    -- occupant's marker before UpdateQuestIcon resolves the new unit.
    frame.questIcon:Hide()
    -- Fallback row only: reset the aura dots so a reused plate can't show the
    -- previous occupant's auras before UpdateAuraIcons resolves the new unit.
    if frame.auraIcons then
        for _, auraIcon in ipairs(frame.auraIcons) do
            ClearAuraCooldown(auraIcon)
            auraIcon:Hide()
        end
    end
    FS.framesByUnit[unit] = nil
    table.insert(FS.freePool, frame)
end

-------------------------------------------------------------------------------
-- Per-unit updates
-------------------------------------------------------------------------------

local function HideBlizzardPlate(plate)
    if plate and plate.UnitFrame then
        plate.UnitFrame:Hide()
    end
end

local function UpdateHealth(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    local health = UnitHealth(unit)
    local maxHealth = UnitHealthMax(unit)
    -- `maxHealth > 0` threw here: nameplate max health is a secret number.
    -- The nil-guards below are truth-tests, which ARE legal on non-boolean
    -- secrets, and both setters accept secret numbers -- so dropping the
    -- comparison keeps this fully working rather than degrading it.
    if health and maxHealth then
        root.healthBar:SetMinMaxValues(0, maxHealth)
        root.healthBar:SetValue(health)
    end
    FS.FrameHelpers.UpdateCaretFull(root.healthBar.caret, unit, "health")

    -- Blizzard re-shows its own UnitFrame on plate updates; keep re-hiding it.
    HideBlizzardPlate(FS.platesByUnit[unit])
end

-- Power-type -> fill color, keyed by the numeric power type (POWER_TYPE_MANA/
-- RAGE/ENERGY). Built lazily on first call rather than at file scope: this
-- file loads FIRST in the .toc, before Theme.lua (see the file header), so
-- FS.Theme.COLOR_POWER isn't populated yet at file-load time -- every
-- FS.Theme.* read has to happen at runtime, same constraint CreatePlateFrame
-- is already under. Cached after the first build since none of these three
-- entries ever change at runtime.
local powerTypeColors
local function GetPowerTypeColors()
    if not powerTypeColors then
        powerTypeColors = {
            [POWER_TYPE_MANA] = FS.Theme.COLOR_POWER,
            [POWER_TYPE_RAGE] = COLOR_POWER_RAGE,
            [POWER_TYPE_ENERGY] = COLOR_POWER_ENERGY,
        }
    end
    return powerTypeColors
end

-- Gate/resize: show the strip and grow the plate for a mana/rage/energy user
-- WITH a power pool, hide and collapse it back otherwise (Dispatch 3: was
-- mana-only). UnitPowerType(unit) is a plain, comparable number on this client
-- (unlike health/power), so a direct table lookup is legal, but a no-mana NPC
-- still reports type mana with max 0 and the max is secret, so the grow/
-- collapse is delegated to root.fsSizer (see CreatePlateFrame), which takes
-- the raw max. Called on NAME_PLATE_UNIT_ADDED and on
-- UNIT_MAXPOWER/UNIT_DISPLAYPOWER only -- kept off UNIT_POWER_UPDATE's hot
-- path, see UpdatePowerValue below.
local function UpdatePower(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    local powerType = UnitPowerType(unit)
    local color = GetPowerTypeColors()[powerType]
    if color then
        root.powerBar:Show()
        ApplyPowerFillColor(root, color)
        -- Cached for UpdatePowerValue below, which has no powerType of its
        -- own in scope (its UNIT_POWER_UPDATE trigger carries no power-type
        -- info) -- without this it would have to hardcode an index the way
        -- the bug below did.
        root.powerType = powerType

        -- Secret on non-player units; nil-guarded together, mirrors
        -- UpdateHealth's health/maxHealth handling above. `powerType`, not a
        -- hardcoded mana index -- this gate now also admits rage/energy (see
        -- GetPowerTypeColors above), so index 0 would read the WRONG pool
        -- (always mana) on those two.
        local power = UnitPower(unit, powerType)
        local maxPower = UnitPowerMax(unit, powerType)
        if power and maxPower then
            root.powerBar:SetMinMaxValues(0, maxPower)
            root.powerBar:SetValue(power)
        end
        -- Straight into the sizer (clamps to 0..1): max 0 collapses root to
        -- baseHeight, a real pool grows it. IsSecret is checked FIRST: nil is
        -- not secret, but comparing a secret to nil is illegal. A nil max has
        -- no pool, so collapse without a log. Any non-nil value the setter
        -- refuses reserves the strip (old always-grow behavior) and logs once
        -- per session.
        if not FS.IsSecret(maxPower) and maxPower == nil then
            root.fsSizer:SetValue(0)
        elseif not pcall(root.fsSizer.SetValue, root.fsSizer, maxPower) then
            root.fsSizer:SetValue(1)
            if not sizerSetValueWarned then
                sizerSetValueWarned = true
                FS.LogDegradeOnce("plate_sizer_setvalue",
                    "|cffff4488ForeverSynthwave|r: nameplate sizer refused the power max, always reserving the power strip")
            end
        end
        FS.FrameHelpers.UpdatePowerHostEmpty(root.powerBar, unit)
        FS.FrameHelpers.UpdateCaretFull(root.powerBar.caret, unit, "power")
    else
        root.powerBar:Hide()
        root.fsSizer:SetValue(0)
    end
end

-- UNIT_POWER_UPDATE's own handler: cheap on purpose, since it fires often.
-- No gate/resize here -- only SetValue, and only while the bar is already
-- shown (a hidden bar's unit isn't a mana/rage/energy user, so there is
-- nothing to update). Reads root.powerType, the value UpdatePower cached the
-- last time it resolved this unit's power type -- this handler has no fresh
-- UnitPowerType call of its own, since UNIT_POWER_UPDATE carries no
-- power-type info and re-querying it on every tick would defeat the point of
-- keeping this handler cheap. Falls back to POWER_TYPE_MANA only for a plate
-- whose UpdatePower somehow never ran (shouldn't happen -- NAME_PLATE_UNIT_ADDED
-- always calls it first).
local function UpdatePowerValue(unit)
    local root = FS.framesByUnit[unit]
    if not root or not root.powerBar:IsShown() then return end

    local powerType = root.powerType or POWER_TYPE_MANA
    local power = UnitPower(unit, powerType)
    if power then
        root.powerBar:SetValue(power)
    end
    FS.FrameHelpers.UpdatePowerHostEmpty(root.powerBar, unit)
    FS.FrameHelpers.UpdateCaretFull(root.powerBar.caret, unit, "power")
end

-- Fill color, precedence tap-denied > engagement (see GetEngagementColor
-- above). UnitIsTapDenied is NOT secret and is freely comparable on this
-- client, so this branch needs no secret-value guard; desaturated grey reads
-- as "not yours" without competing with the engagement/reaction colors.
-- GetEngagementColor itself falls back to GetReactionColor for a
-- not-attackable or not-yet-engaged unit, so an untouched mob's fill shows
-- its reaction color (amber neutral, hostile pink) until threat starts.
local function UpdateFillColor(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    local denied = false
    local ok = pcall(function() denied = UnitIsTapDenied(unit) and true or false end)
    root.tapDenied = ok and denied

    if root.tapDenied then
        ApplyFillColor(root, COLOR_BAR_TAPPED)
    else
        ApplyFillColor(root, GetEngagementColor(unit))
    end
end

-- GetRaidTargetIndex returns a plain number historically, but FS.IsSecret is
-- checked first anyway (same ordering as GetReactionColor above) since a
-- truth-test on a secret is illegal even where the value is expected to be
-- plain. Either API missing degrades to a hidden marker, not a texcoord guess.
local function UpdateRaidMarker(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    if not HAS_GET_RAID_TARGET_INDEX or not HAS_RAID_TARGET_TEXTURE_SETTER then
        root.raidMarker:Hide()
        return
    end

    local index = GetRaidTargetIndex(unit)
    if FS.IsSecret(index) then
        root.raidMarker:Hide()
        return
    end
    if not index then
        root.raidMarker:Hide()
        return
    end

    SetRaidTargetIconTexture(root.raidMarker, index)
    root.raidMarker:Show()
end

-- Whether the client's own nameplateNotSelectedAlpha CVar is already dimming
-- non-target plates, so ALPHA_NONTARGET_DIM below doesn't compound with it.
-- UNVERIFIED in-game whether this CVar exists or affects default nameplates
-- on this client. Feature-detected (C_CVar.GetCVar, else the legacy global
-- GetCVar) and pcall'd, since an unknown CVar name errors on some clients
-- rather than returning nil. Cached rather than read per-plate; refreshed by
-- RefreshEngineDimCache below.
local engineDimsNonTarget = false

local function RefreshEngineDimCache()
    local getter = (C_CVar and C_CVar.GetCVar) or GetCVar
    if not getter then
        engineDimsNonTarget = false
        return
    end

    local ok, value = pcall(getter, "nameplateNotSelectedAlpha")
    local alpha = ok and tonumber(value) or nil
    engineDimsNonTarget = alpha ~= nil and alpha < 1
end

-- Folds hue (hostility), target emphasis (glow alpha + border accent) and
-- non-target dim (root alpha) into one pass so a plate's target-vs-hostile
-- state can never disagree between the three. UnitIsUnit(unit, "target") is a
-- plain boolean on this client, unlike UnitReaction -- no secret-value guard
-- needed here.
local function UpdateGlowState(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end
    FitPlateFillCuts(root)

    -- UnitCanAttack's secrecy on a nameplate unit token is UNVERIFIED on this
    -- client, so its result is FS.IsSecret-guarded before the truth-test, same
    -- ordering as GetReactionColor/UpdateName elsewhere in this file. A secret
    -- result degrades to "not attackable" rather than erroring.
    local attackable = UnitCanAttack("player", unit)
    local hostile = not FS.IsSecret(attackable) and attackable and not UnitIsDead(unit)
    local isTarget = UnitIsUnit(unit, "target")

    local color, alpha
    if hostile then
        color = FS.Theme.COLOR_HEALTH
        alpha = isTarget and GLOW_ALPHA_TARGET_HOSTILE or GLOW_ALPHA_HOSTILE
    else
        color = FS.Theme.COLOR_BORDER
        alpha = isTarget and GLOW_ALPHA_TARGET_DEFAULT or GLOW_ALPHA_DEFAULT
    end
    root.fsGlow:SetVertexColor(color[1], color[2], color[3], alpha)

    -- Border accent: light cyan on the target plate (reuses the existing
    -- COLOR_POWER token, #22e0ff -- no new hex), default violet otherwise.
    local borderColor = isTarget and FS.Theme.COLOR_POWER or FS.Theme.COLOR_BORDER
    root.fsBorder:SetVertexColor(borderColor[1], borderColor[2], borderColor[3], borderColor[4] or 1)

    -- Non-target dim: every plate but the target drops to ALPHA_NONTARGET_DIM,
    -- unless the engine's own nameplateNotSelectedAlpha CVar is already doing
    -- it (engineDimsNonTarget) -- stacking both would compound the dim. No
    -- target at all means no dimming from us either way.
    if isTarget or not UnitExists("target") or engineDimsNonTarget then
        root:SetAlpha(1)
    else
        root:SetAlpha(ALPHA_NONTARGET_DIM)
    end
end

-- Level prefix for the nameplate name, coloured by difficulty so an out-of-depth
-- mob is obvious before you pull it. UnitLevel/UnitClassification are plain
-- (non-secret) on this client, so ordinary comparisons are fine here.
--
-- Level -1 means "cannot determine", which the game shows as a skull; that is
-- exactly the case worth shouting about, so it renders as a red "??".
local ELITE_SUFFIX = {
    elite = "+",
    rareelite = "R+",
    rare = "R",
    worldboss = "B",
}

local function BuildLevelPrefix(unit)
    local level = UnitLevel(unit)
    if not level then return "" end

    local text
    if level < 0 then
        text = "??"
    else
        text = tostring(level)
    end

    local classification = UnitClassification(unit)
    if classification then
        text = text .. (ELITE_SUFFIX[classification] or "")
    end

    -- Difficulty tint: red/orange/yellow/green/grey relative to the player.
    local r, g, b = 1, 0.82, 0
    if level < 0 then
        r, g, b = 1, 0.1, 0.1
    else
        local ok, color = pcall(GetCreatureDifficultyColor, level)
        if ok and color and color.r then
            r, g, b = color.r, color.g, color.b
        end
    end

    return string.format("|cff%02x%02x%02x%s|r ", r * 255, g * 255, b * 255, text)
end

-- Full name (first + surname) for the plate; mirrors UnitFrames.lua's
-- GetFullUnitName, falling back to UnitName and never returning nil. A secret
-- result is returned untouched, since a string method or truth-test on it is
-- forbidden and SetText accepts it.
local function GetPlateUnitName(unit)
    local full
    if HAS_GET_UNIT_NAME then
        full = GetUnitName(unit, true)
        if FS.IsSecret(full) then return full end
        if type(full) == "string" then
            full = full:gsub("[%s%-]+$", "")
        end
    end
    if not full or full == "" then
        full = UnitName(unit)
        if FS.IsSecret(full) then return full end
        full = full or ""
    end
    return full
end

-- Name color fallback chain: player class color first, else -- for an
-- attackable non-player unit -- the engagement/threat color (GetEngagementColor
-- above, falling back to the name reaction palette while unengaged), else the
-- existing white/yellow/red reaction palette (GetNameReactionColor).
-- UnitIsPlayer/UnitClass/UnitCanAttack's secrecy on a nameplate unit token is
-- UNVERIFIED on this client, so all three are FS.IsSecret-guarded before any
-- truth-test/nil-check on their result, same secrecy-first-then-nil-check
-- order GetReactionColor's own comment explains -- a secret
-- isPlayer/classFile/attackable falls through to the next link in the chain
-- rather than erroring or leaving color unset. GetEngagementColor and
-- GetNameReactionColor never return nil, so every branch below reaches a
-- real color before SetTextColor.
local function UpdateName(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    local name = GetPlateUnitName(unit)

    -- A secret name cannot be concatenated, so it skips the level prefix and
    -- goes straight to SetText, which accepts secrets.
    if FS.IsSecret(name) then
        root.nameText:SetText(name)
    else
        -- Other players show a level too, but their classification is meaningless.
        local ok, prefix = pcall(BuildLevelPrefix, unit)
        if ok and prefix then
            root.nameText:SetText(prefix .. name)
        else
            root.nameText:SetText(name)
        end
    end

    local color
    local isPlayer = UnitIsPlayer(unit)
    if not FS.IsSecret(isPlayer) and isPlayer then
        local classFile = select(2, UnitClass(unit))
        if not FS.IsSecret(classFile) then
            local cc = HAS_RAID_CLASS_COLORS and classFile and RAID_CLASS_COLORS[classFile]
            if cc then
                color = { cc.r, cc.g, cc.b }
            end
        end
    end

    if not color then
        -- Checked here so a non-attackable unit goes straight to the name
        -- palette; for an attackable one, GetNameReactionColor is passed as
        -- the engagement fallback so an unengaged mob's name reads yellow/red
        -- (the NAME palette) rather than the fill palette.
        local attackable = UnitCanAttack("player", unit)
        if not FS.IsSecret(attackable) and attackable then
            color = GetEngagementColor(unit, GetNameReactionColor)
        else
            color = GetNameReactionColor(unit)
        end
    end
    root.nameText:SetTextColor(color[1], color[2], color[3])
end

-- Quest objective indicator: shown when the plate's unit is relevant to any
-- quest in the player's own quest log. No cleaner single-call "is this unit a
-- quest objective" API exists, so this scans the quest log (typically well
-- under 30 entries) rather than tooltip-scan the unit. IsUnitOnQuest's
-- secrecy on a nameplate unit token is UNVERIFIED on this client, so its
-- boolean return is FS.IsSecret-guarded before any truth-test, same ordering
-- as UpdateRaidMarker's index read above. Missing API degrades to a
-- permanently-hidden icon, not a guess.
local function UpdateQuestIcon(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    if not HAS_QUEST_LOG_API then
        root.questIcon:Hide()
        return
    end

    local onQuest = false
    pcall(function()
        local numShown = C_QuestLog.GetNumQuestLogEntries()
        for i = 1, numShown do
            local info = C_QuestLog.GetInfo(i)
            if info and not info.isHeader then
                local isOnQuest = C_QuestLog.IsUnitOnQuest(unit, info.questID)
                if not FS.IsSecret(isOnQuest) and isOnQuest then
                    onQuest = true
                    break
                end
            end
        end
    end)

    if onQuest then
        root.questIcon:Show()
    else
        root.questIcon:Hide()
    end
end

-------------------------------------------------------------------------------
-- Aura dots
-------------------------------------------------------------------------------

-- Own-cast auras (`aura.caster == "player"`, a plain string field, not
-- secret -- TargetAuras.lua's ApplyAuraData already compares it the same way
-- without an IsSecret guard) get Theme.COLOR_HEALTH's pink border; everyone
-- else's get Theme.COLOR_BORDER's violet -- D4 locked spec, deliberately NOT
-- TargetAuras.lua's own local COLOR_OWN_CAST (#ff4dd8), a different pink.
local function ApplyAuraIcon(button, aura)
    button.icon:SetTexture(aura.icon)
    if aura.count and aura.count > 1 then
        button.count:SetText(aura.count)
        button.count:Show()
    else
        button.count:SetText("")
        button.count:Hide()
    end

    -- Both fields are checked for secrecy BEFORE any truth test or comparison;
    -- a secret just clears the sweep.
    local duration, expiration = aura.duration, aura.expirationTime
    if button.cooldown
        and not FS.IsSecret(duration) and not FS.IsSecret(expiration)
        and duration and expiration and duration > 0 then
        button.cooldown:SetCooldown(expiration - duration, duration)
        button.cooldown:Show()
    else
        ClearAuraCooldown(button)
    end

    local color = (aura.caster == "player") and FS.Theme.COLOR_HEALTH or FS.Theme.COLOR_BORDER
    TintAuraIconBorder(button.fsSkin, color)
    button:Show()
end

-- Fallback row only (root.auraIcons exists only without the aura container
-- template; the container path never calls any aura API). A broad HARMFUL query
-- capped at AURA_ICON_MAX. Aura slots are contiguous in index order (every other
-- aura scan in this addon relies on the same assumption -- see TargetAuras.lua's
-- RefreshCategory), so the loop can simply stop at the first missing slot.
--
-- Combat-lockdown gated the same way TargetAuras.lua's RefreshDisplay is:
-- aura reads are REFUSED (not secret -- refused, with an error) under combat
-- lockdown, so this bails BEFORE touching any icon, leaving whatever is
-- already displayed rather than clearing it. See Buffs.lua's
-- RefreshAurasEvent comment and Theme.lua's FS.AurasReadable comment for the
-- 9.2MB leak that scanning under refusal caused (every refused call still
-- builds its refusal string), and CLAUDE.md's TargetAuras.lua entry for the
-- rule. Returning here, rather than clearing the pool, also keeps the last
-- display up through a fight.
local function UpdateAuraIcons(unit)
    local root = FS.framesByUnit[unit]
    if not root or not root.auraIcons then return end

    if not FS.AurasReadable() then return end

    local shown = 0
    for slot = 1, AURA_ICON_MAX do
        local aura = ReadAuraSlot(unit, slot, AURA_QUERY_FILTER)
        if not aura then break end
        shown = shown + 1
        ApplyAuraIcon(root.auraIcons[shown], aura)
    end
    for i = shown + 1, AURA_ICON_MAX do
        ClearAuraCooldown(root.auraIcons[i])
        root.auraIcons[i]:Hide()
    end
end

-------------------------------------------------------------------------------
-- Cast bar
-------------------------------------------------------------------------------

-- Normalizes UnitCastingInfo/UnitChannelInfo into one shape, plus the
-- not-interruptible flag CastBars.lua's own GetCastInfo doesn't need.
-- Position is UNVERIFIED on 16001 (return #8 for a cast, #7 for a channel,
-- per the documented signature); captured as an opaque value and never
-- compared or truth-tested here -- see ApplyCastInterruptible.
local function GetPlateCastInfo(unit)
    local name, _, texture, startMS, endMS, _, _, notInterruptible = UnitCastingInfo(unit)
    if name then
        return { name = name, texture = texture, startMS = startMS, endMS = endMS,
            channeling = false, notInterruptible = notInterruptible }
    end

    name, _, texture, startMS, endMS, _, notInterruptible = UnitChannelInfo(unit)
    if name then
        return { name = name, texture = texture, startMS = startMS, endMS = endMS,
            channeling = true, notInterruptible = notInterruptible }
    end

    return nil
end

-- The ONLY sanctioned secret-boolean consumer is SetAlphaFromBoolean (see the
-- wow-addon-secret-values skill); NEVER branch on `notInterruptible` itself,
-- since it may be a secret boolean and a truth-test on one throws. type() is
-- legal on a secret, so it gates the call without inspecting the value.
local function ApplyCastInterruptible(bar, notInterruptible)
    if type(notInterruptible) == "boolean" then
        if type(bar.shield.SetAlphaFromBoolean) == "function" then
            bar.shield:SetAlphaFromBoolean(notInterruptible, 1, 0)
        end
        return
    end
    bar.shield:SetAlpha(0)
end

local function StopPlateCast(root)
    root.castActive = false
    root.castBar:Hide()
end

local function StartPlateCast(root, info)
    root.castActive = true

    -- Engine-timed fill only, no OnUpdate: hand the duration object to the
    -- bar and let the engine animate it. UnitCastingDuration/UnitChannelDuration
    -- are feature-detected as a pair (HAS_PLATE_CAST_DURATION). Channels get
    -- the SAME single-arg SetTimerDuration call as a cast -- this client's
    -- StatusBar has no reverse-fill variant, so a channel fills up like a
    -- cast rather than draining down, mirroring CastBars.lua's own limitation.
    local duration
    if HAS_PLATE_CAST_DURATION then
        local ok, d = pcall(info.channeling and UnitChannelDuration or UnitCastingDuration, root.unit)
        if ok then duration = d end
    end

    if duration and type(root.castBar.SetTimerDuration) == "function" then
        pcall(function() root.castBar:SetTimerDuration(duration) end)
    else
        -- No duration-object support on this client: static full bar rather
        -- than throw trying to compute a fraction from secret timing.
        root.castBar:SetMinMaxValues(0, 1)
        root.castBar:SetValue(1)
    end

    root.castBar.nameText:SetText(CleanPlateCastName(info.name))
    ApplyCastInterruptible(root.castBar, info.notInterruptible)
    root.castBar:Show()
end

local function RefreshPlateCast(unit)
    local root = FS.framesByUnit[unit]
    if not root then return end

    if not UnitExists(unit) then
        StopPlateCast(root)
        return
    end

    local info = GetPlateCastInfo(unit)
    if not info then
        StopPlateCast(root)
        return
    end

    StartPlateCast(root, info)
end

-------------------------------------------------------------------------------
-- Nameplate lifecycle
-------------------------------------------------------------------------------

-- UnitFrames whose Show is already hooked. Weak-keyed side table instead of a
-- field on Blizzard's frame (addon code is tainted; never write onto it).
local showHookedUnitFrames = setmetatable({}, { __mode = "k" })

local function OnNamePlateAdded(unit)
    -- Guard against ADDED firing twice for the same unit token without an
    -- intervening REMOVED; without this the previously-acquired frame would
    -- never be returned to the pool.
    if FS.framesByUnit[unit] then
        ReleaseFrame(unit)
    end

    local plate = C_NamePlate.GetNamePlateForUnit(unit)
    if not plate then return end

    HideBlizzardPlate(plate)

    -- Blizzard re-Shows its CompactUnitFrame on aura/cast/threat updates far more
    -- often than our reactive HideBlizzardPlate calls run, causing a visible
    -- flicker. Hook Show once per physical plate object (Blizzard reuses a small
    -- pool of these) so it can never come back up.
    if plate.UnitFrame and not showHookedUnitFrames[plate.UnitFrame] then
        hooksecurefunc(plate.UnitFrame, "Show", plate.UnitFrame.Hide)
        showHookedUnitFrames[plate.UnitFrame] = true
    end

    local root = AcquireFrame()
    root.unit = unit
    root:SetParent(plate)
    -- TOP + sizer-derived BOTTOM, see AnchorPlateRoot. UpdatePower's height
    -- changes only ever extend the bottom.
    AnchorPlateRoot(root, plate)
    root:Show()

    FS.framesByUnit[unit] = root
    FS.platesByUnit[unit] = plate

    -- After root's own anchoring: the aura container hangs off root.healthBar.
    AttachAuraContainer(root, unit)

    RefreshEngineDimCache()
    UpdateHealth(unit)
    UpdatePower(unit)
    UpdateFillColor(unit)
    UpdateGlowState(unit)
    UpdateRaidMarker(unit)
    UpdateName(unit)
    UpdateQuestIcon(unit)
    UpdateAuraIcons(unit)
    -- Seed the cast bar in case the plate appeared mid-cast.
    RefreshPlateCast(unit)
    -- A plate for the already-targeted unit can get its selected scale from the engine after
    -- this event: fit once more a frame later (the immediate fit ran in UpdateGlowState).
    RefitAllPlatesDeferred()
end

local function OnNamePlateRemoved(unit)
    ReleaseFrame(unit)
    FS.platesByUnit[unit] = nil
end

-------------------------------------------------------------------------------
-- Event handling
-------------------------------------------------------------------------------

local eventFrame = CreateFrame("Frame")

-- Guarded per-event: a missing event name on some client build must not abort
-- the whole registration block (mirrors StanceBar.lua/ActionBars.lua's own
-- RegisterEvents loop).
for _, event in ipairs({
    "NAME_PLATE_UNIT_ADDED",
    "NAME_PLATE_UNIT_REMOVED",
    "UNIT_HEALTH",
    "UNIT_MAXHEALTH",
    "UNIT_FACTION",
    "UNIT_FLAGS",
    "UNIT_POWER_UPDATE",
    "UNIT_MAXPOWER",
    "UNIT_DISPLAYPOWER",
    "PLAYER_TARGET_CHANGED",
    "RAID_TARGET_UPDATE",
    "QUEST_LOG_UPDATE",
    "QUEST_WATCH_UPDATE",
    "CVAR_UPDATE",
    -- The plate's pixel size (fill cut wedges, FitPlateFillCuts) follows these.
    "UI_SCALE_CHANGED",
    "DISPLAY_SIZE_CHANGED",
    -- Aura container pool prefill (TopUpAuraPool).
    "PLAYER_ENTERING_WORLD",
    "UNIT_THREAT_LIST_UPDATE",
    "UNIT_THREAT_SITUATION_UPDATE",
    -- Pool top-up after combat (container path), or the fallback row's rescan:
    -- aura reads are refused under combat lockdown (FS.AurasReadable), so a dot
    -- applied in combat and still running afterward is otherwise never drawn --
    -- mirrors TargetAuras.lua's own PLAYER_REGEN_ENABLED registration.
    "PLAYER_REGEN_ENABLED",
}) do
    pcall(eventFrame.RegisterEvent, eventFrame, event)
end

-- The aura container updates itself (engine-side), so UNIT_AURA, which fires for
-- every unit all the time, is only worth listening to for the fallback row: from
-- load without the template, or from the moment the container path is given up
-- (EngageAuraFallback, called by GiveUpAuraContainers).
if not USE_AURA_CONTAINERS then
    pcall(eventFrame.RegisterEvent, eventFrame, "UNIT_AURA")
end

-- The fallback row's regen rescan (the handler below) is refused while the client still says
-- auras are secret; the shared retry chain (Theme.lua) runs it again once reads work. The
-- container path draws engine-side and has nothing to rescan. This file loads BEFORE Theme.lua
-- (.toc), so FS.OnAurasReadable does not exist at file scope: it is registered once, from the
-- PLAYER_ENTERING_WORLD handler, which cannot run before every file has loaded.
local aurasReadableRegistered = false
local function RegisterAurasReadable()
    if aurasReadableRegistered then return end
    aurasReadableRegistered = true
    FS.OnAurasReadable(function()
        if AuraContainersActive() then return end
        for otherUnit in pairs(FS.framesByUnit) do
            UpdateAuraIcons(otherUnit)
        end
    end)
end

-- The container path was given up at runtime: register UNIT_AURA and give every
-- live plate that has no container its fallback row, scanned at once.
EngageAuraFallback = function()
    pcall(eventFrame.RegisterEvent, eventFrame, "UNIT_AURA")
    for unit, root in pairs(FS.framesByUnit) do
        if not root.auraContainer then
            EnsureAuraIcons(root)
            UpdateAuraIcons(unit)
        end
    end
end

-- Cast bar events, same guarded registration as above; kept as its own
-- loop over CAST_EVENTS rather than folded into the list above, since that
-- table is declared up in Constants alongside the rest of the cast-bar setup.
for _, event in ipairs(CAST_EVENTS) do
    pcall(eventFrame.RegisterEvent, eventFrame, event)
end

eventFrame:SetScript("OnEvent", function(_, event, unit)
    -- PLAYER_TARGET_CHANGED carries no unit argument, so it has to be
    -- dispatched before the unit-based lookup below: targeting changes
    -- emphasis on both the old and new target plate, and dims/undims every
    -- other live plate at once.
    if event == "PLAYER_TARGET_CHANGED" then
        RefreshEngineDimCache()
        for otherUnit in pairs(FS.framesByUnit) do
            UpdateGlowState(otherUnit)
        end
        -- The engine may apply the selected-plate scale after this handler: fit once more.
        RefitAllPlatesDeferred()
        return
    end

    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
        RefitAllPlatesSoon()
        return
    end

    -- RAID_TARGET_UPDATE also carries no unit argument, dispatched the same
    -- way: a marker placed/cleared on any unit fires it for every plate at once.
    if event == "RAID_TARGET_UPDATE" then
        for otherUnit in pairs(FS.framesByUnit) do
            UpdateRaidMarker(otherUnit)
        end
        return
    end

    -- QUEST_LOG_UPDATE/QUEST_WATCH_UPDATE carry no unit argument either
    -- (accepting/completing/abandoning a quest, or toggling its watch, changes
    -- which units are quest-relevant addon-wide) -- refresh every live plate's
    -- quest icon the same unitless way as the two events above.
    if event == "QUEST_LOG_UPDATE" or event == "QUEST_WATCH_UPDATE" then
        for otherUnit in pairs(FS.framesByUnit) do
            UpdateQuestIcon(otherUnit)
        end
        return
    end

    -- PLAYER_ENTERING_WORLD carries no unit argument either: it prefills
    -- the aura container pool (a no-op without the template, or in combat) and, once,
    -- registers the fallback row's readable callback (Theme.lua is loaded by now).
    if event == "PLAYER_ENTERING_WORLD" then
        TopUpAuraPool()
        RegisterAurasReadable()
        return
    end

    -- PLAYER_REGEN_ENABLED also carries no unit argument. With containers it
    -- tops the pool back up (an empty pool in combat had to build one under
    -- pcall) and gives every plate that was refused a container in the fight
    -- another attach (RetryBareAuraPlates); with the fallback row it
    -- refreshes the dots on every live plate when lockdown lifts, same
    -- reasoning as TargetAuras.lua's own handler:
    -- without it an aura applied in combat and still running afterward would
    -- never be drawn until some later, unrelated UNIT_AURA fires.
    if event == "PLAYER_REGEN_ENABLED" then
        auraAttachRefusedInCombat = false
        if AuraContainersActive() then
            TopUpAuraPool()
            RetryBareAuraPlates()
        else
            for otherUnit in pairs(FS.framesByUnit) do
                UpdateAuraIcons(otherUnit)
            end
        end
        return
    end

    if not unit then return end

    if event == "NAME_PLATE_UNIT_ADDED" then
        OnNamePlateAdded(unit)
    elseif event == "NAME_PLATE_UNIT_REMOVED" then
        OnNamePlateRemoved(unit)
    elseif event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH"
        or event == "UNIT_FACTION" or event == "UNIT_FLAGS" then
        if unit == "player" and (event == "UNIT_FACTION" or event == "UNIT_FLAGS") then
            -- Fires on the player's own token (duel start, PvP flag toggle),
            -- which flips UnitCanAttack for every plate at once but has no
            -- plate of its own -- refresh every live plate instead of just this unit.
            for otherUnit in pairs(FS.framesByUnit) do
                UpdateHealth(otherUnit)
                UpdateFillColor(otherUnit)
                UpdateGlowState(otherUnit)
                UpdateName(otherUnit)
                UpdateQuestIcon(otherUnit)
            end
        elseif FS.framesByUnit[unit] then
            UpdateHealth(unit)
            UpdateFillColor(unit)
            UpdateGlowState(unit)
            UpdateName(unit)
            UpdateQuestIcon(unit)
        end
    elseif event == "UNIT_THREAT_LIST_UPDATE" or event == "UNIT_THREAT_SITUATION_UPDATE" then
        -- Carries a unit arg like UNIT_HEALTH (no "player"-token case to
        -- special-case here) -- refresh the fill and name so engagement color
        -- follows threat as it shifts, e.g. pulling aggro off the tank.
        if FS.framesByUnit[unit] then
            UpdateFillColor(unit)
            UpdateName(unit)
        end
    elseif event == "UNIT_AURA" then
        if FS.framesByUnit[unit] then
            UpdateAuraIcons(unit)
        end
    elseif event == "UNIT_POWER_UPDATE" then
        UpdatePowerValue(unit)
    elseif event == "UNIT_MAXPOWER" or event == "UNIT_DISPLAYPOWER" then
        UpdatePower(unit)
    elseif event == "UNIT_SPELLCAST_START" or event == "UNIT_SPELLCAST_CHANNEL_START"
        or event == "UNIT_SPELLCAST_DELAYED" or event == "UNIT_SPELLCAST_CHANNEL_UPDATE" then
        -- Cheap no-op via FS.framesByUnit for a unit without a plate; a cast
        -- on some other tracked unit (e.g. "player") has no plate frame to update.
        if FS.framesByUnit[unit] then
            RefreshPlateCast(unit)
        end
    elseif event == "UNIT_SPELLCAST_STOP" or event == "UNIT_SPELLCAST_FAILED"
        or event == "UNIT_SPELLCAST_INTERRUPTED" or event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        -- Re-query via RefreshPlateCast rather than hiding unconditionally: a
        -- stale STOP delivered after the next cast's START would otherwise
        -- hide a cast that is actually still live. RefreshPlateCast already
        -- hides when UnitCastingInfo/UnitChannelInfo find nothing, same as
        -- CastBars.lua's own RefreshCast.
        if FS.framesByUnit[unit] then
            RefreshPlateCast(unit)
        end
    elseif event == "UNIT_SPELLCAST_INTERRUPTIBLE" or event == "UNIT_SPELLCAST_NOT_INTERRUPTIBLE" then
        -- Plain event-name logic, not a value read -- the event ITSELF carries
        -- the interruptible state, so there is nothing secret to guard here.
        local root = FS.framesByUnit[unit]
        if root then
            root.castBar.shield:SetAlpha(event == "UNIT_SPELLCAST_NOT_INTERRUPTIBLE" and 1 or 0)
        end
    elseif event == "CVAR_UPDATE" then
        -- CVAR_UPDATE's second arg is the CVar name, not a unit token -- reuses
        -- the `unit` param purely because this handler is shared. Filtered so
        -- an unrelated CVar change doesn't force a full-plate refresh.
        local cvarName = unit and unit:lower()
        if cvarName == "nameplatenotselectedalpha" then
            RefreshEngineDimCache()
            for otherUnit in pairs(FS.framesByUnit) do
                UpdateGlowState(otherUnit)
            end
        elseif cvarName and PLATE_SCALE_CVARS[cvarName] then
            RefitAllPlatesSoon()
        end
    end
end)

-- /fsplate: reads back the numbers behind FitPlateFillCuts for the target plate and one
-- non-target plate, so the one-texel-per-physical-pixel reading of the plate stroke can be
-- confirmed in game: if the border's chamfer on screen is about SLICE_MARGIN pixels, the
-- assumption holds. Read-only; every value is a plain number or "n/a".
SLASH_FSPLATE1 = "/fsplate"
SlashCmdList["FSPLATE"] = function()
    local theme = FS.Theme
    local function num(v)
        if type(v) == "number" and not FS.IsSecret(v) then return string.format("%.3f", v) end
        return "n/a"
    end
    local function line(label, root)
        local pixel, factor, eff = PlatePixelSize(root)
        print(string.format("synthwave://plate %s effScale=%s pxFactor=%s unitsPerPixel=%s strokeChamferUnits=%s wedge=%s",
            label, num(eff), num(factor), num(pixel),
            pixel and num(theme.SLICE_MARGIN * pixel) or "n/a", tostring(root.fsFillCut or "unfitted")))
    end
    local physical = "n/a"
    if type(GetPhysicalScreenSize) == "function" then
        local ok, _, h = pcall(GetPhysicalScreenSize)
        if ok then physical = num(h) end
    end
    print(string.format("synthwave://plate SLICE_MARGIN=%s physicalHeight=%s UIParentEffScale=%s",
        tostring(theme.SLICE_MARGIN), physical, num(UIParent and UIParent:GetEffectiveScale())))
    local shownTarget, shownOther
    for unit, root in pairs(FS.framesByUnit) do
        local okT, isTarget = pcall(UnitIsUnit, unit, "target")
        isTarget = okT and not FS.IsSecret(isTarget) and isTarget
        if isTarget and not shownTarget then
            shownTarget = true
            line("target " .. unit, root)
        elseif not isTarget and not shownOther then
            shownOther = true
            line("other " .. unit, root)
        end
    end
    if not shownTarget then print("synthwave://plate no target plate is up") end
    if not shownOther then print("synthwave://plate no non-target plate is up") end
end
