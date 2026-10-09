-- Forever STUwave: Party Frames
-- Five custom rows (player, party1-4), each its own SecureUnitButtonTemplate
-- button built the same way UnitFrames.lua builds PLAYER/TARGET -- explicit
-- secure attributes, a non-secure `visual` child for chrome, RegisterUnitWatch
-- for the four party rows. NOT SecureGroupHeaderTemplate: the healer wants a
-- fixed row order (self first) rather than raid-roster-driven reordering.
-- This is interface 16001 (a 12.0-era modern engine); every possibly-
-- missing API (role assignment, pet events) is feature-detected/pcall-guarded
-- at the call site rather than gated on a version/build check.

local _, FS = ...

-- Chrome helpers/constants shared with the other component skins live in
-- Theme.lua (loaded before this file, see the .toc); localized here for
-- call-site brevity.
local ApplyFontGeneric = FS.Theme.ApplyFontGeneric
local ApplyMono = FS.Theme.ApplyMono
local AddRoundedFill = FS.Theme.AddRoundedFill
local SkinButton = FS.Theme.SkinButton
local COLOR_BORDER = FS.Theme.COLOR_BORDER
local COLOR_BAR_TRACK = FS.Theme.COLOR_BAR_TRACK
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH
local COLOR_POWER = FS.Theme.COLOR_POWER
local COLOR_STEEL = FS.Theme.COLOR_STEEL
local COLOR_MUTED = FS.Theme.COLOR_MUTED
local FONT_MONO = FS.Theme.FONT_MONO
local FLAT_TEXTURE = FS.Theme.FLAT_TEXTURE
local GLOW_EDGE_TEXTURE = FS.Theme.GLOW_EDGE_TEXTURE
local COLOR_HEAL = FS.Theme.COLOR_HEAL
local COLOR_RED = FS.Theme.COLOR_RED
local HATCH_TEXTURE = FS.Theme.HATCH_TEXTURE

-- Shared 12.0 secret-value guard (see Theme.lua); FS is captured above.
local IsSecret = FS.IsSecret

-- Secure-frame scaffolding shared across UnitFrames/PartyFrames/CastBars/Buffs
-- (see FrameHelpers.lua); localized here for call-site brevity. Dim, not
-- hide: party member/pet frames are Edit Mode UnitFrame system members too
-- (Enum.EditModeUnitFrameSystemIndices.Party), so Hide()+HookScript would
-- taint them the same way it did BuffFrame/DebuffFrame (see Buffs.lua).
local DimBlizzardFrame = FS.FrameHelpers.DimBlizzardFrame
local SetTipSpell = FS.FrameHelpers.SetTipSpell

-- The laser rail builder and its retint/desaturate/gradient helpers live in
-- FrameHelpers.lua (shared with other modules); the party-specific sizes and
-- alphas are passed in through RAIL_POWER_SPEC / RAIL_HEALTH_SPEC below.
local CreateLaserRail = FS.FrameHelpers.CreateLaserRail
local SetLaserRailColor = FS.FrameHelpers.SetLaserRailColor
local SetLaserRailDesaturated = FS.FrameHelpers.SetLaserRailDesaturated
local SetRailGradient = FS.FrameHelpers.SetRailGradient

-------------------------------------------------------------------------------
-- Game-semantic locals (per addon CLAUDE.md: redeclare these per file, do not
-- push them onto Theme.lua)
-------------------------------------------------------------------------------

local CLASS_ICON_ATLAS = "Interface\\WorldStateFrame\\Icons-Classes"
local GetUnitName = _G["GetUnitName"]

-- Role tag letter and colour (mockup P_ROLEC): tank cyan, healer #39ff14, damage red. A role not
-- listed (NONE) hides the tag.
local ROLE_STYLE = {
    TANK    = { "T", COLOR_POWER },
    HEALER  = { "H", COLOR_HEAL },
    DAMAGER = { "D", COLOR_RED },
}

-- Keyed by the numeric UnitPowerType() return (stable across power tokens);
-- unlisted/unknown power types (including Mana, 0) use the theme's cyan
-- COLOR_POWER. The table lives in FrameHelpers so PetFrame shares it.
local POWER_COLORS = FS.FrameHelpers.POWER_COLORS

-- Dispel capability. DISPELS.CLASS maps class token -> dispel type -> { { spellId, name }, ... },
-- every spell that removes that type: the type counts only once the player KNOWS one of them
-- (a Paladin has no Magic dispel before Cleanse at 42, a Priest none before Dispel Magic).
-- Classes absent from the map have no raid dispel. Spell ids, each checked against its Wowhead
-- TBC Classic spell page (www.wowhead.com/tbc/spell=<id>):
--   Paladin Purify 1152 (Poison, Disease), Cleanse 4987 (Poison, Disease, Magic)
--   Priest  Dispel Magic 527 and 988 (Magic), Cure Disease 528, Abolish Disease 552
--   Druid   Remove Curse 2782, Cure Poison 8946, Abolish Poison 2893
--   Mage    Remove Lesser Curse 475 (called Remove Curse in later builds, same id)
--   Shaman  Cure Poison 526, Cure Disease 2870
-- The name is the fallback when a rank id is missing here: it resolves to the id the spellbook
-- holds. DISPELS.cache (the known set) is filled lazily by DISPELS.Set, defined below
-- IsKnownSpellId, and dropped by the spellbook events wired in Init.
local DISPELS = {
    CLASS = {
        PRIEST = {
            Magic   = { { 527, "Dispel Magic" }, { 988, "Dispel Magic" } },
            Disease = { { 528, "Cure Disease" }, { 552, "Abolish Disease" } },
        },
        DRUID = {
            Curse  = { { 2782, "Remove Curse" } },
            Poison = { { 8946, "Cure Poison" }, { 2893, "Abolish Poison" } },
        },
        PALADIN = {
            Magic   = { { 4987, "Cleanse" } },
            Disease = { { 1152, "Purify" }, { 4987, "Cleanse" } },
            Poison  = { { 1152, "Purify" }, { 4987, "Cleanse" } },
        },
        MAGE = {
            Curse = { { 475, "Remove Lesser Curse" } },
        },
        SHAMAN = {
            Poison  = { { 526, "Cure Poison" } },
            Disease = { { 2870, "Cure Disease" } },
        },
    },
}

-- Cleansable-but-unrecognized-type tint: used when a debuff is cleansable
-- but GetDispelColor has no color for its dispelType (e.g. an empty
-- dispelType on the RAID filter path), so the dispel halo never falls back to
-- looking untinted/clean while a debuff icon is showing.
local COLOR_CLEANSABLE_UNKNOWN = { 0.85, 0.80, 0.95, 1 }

-- The player's class token. Every class read in this file goes through here, so this is the
-- single seam a later override (e.g. an FS.PlayerClass hook) would replace; none exists yet.
-- Note PLAYER_BUFFS below is still read once at load, so an override would not retarget it.
local function PlayerClass()
    return select(2, UnitClass("player"))
end

-------------------------------------------------------------------------------
-- Layout constants. FS.Layout.party (Layout.lua) is the single source of
-- truth for the container's anchor/size; width/height are read here (module
-- load time) since MEMBER_WIDTH below depends on them, while the anchor
-- point itself is applied in Init via FS.Layout.Apply.
-------------------------------------------------------------------------------

local CONTAINER_WIDTH  = FS.Layout.party.w
local CONTAINER_HEIGHT = FS.Layout.party.h
local ROW_COUNT = 5

-- Inset of the rows from the container edge on all four sides (mock: .party padding:8px).
-- Box-matched draws no panel-level chrome; each row and pet column carries its own box.
local PANEL_PAD = 8

local ROW_GAP = 4
local ROW_HEIGHT = (CONTAINER_HEIGHT - 2 * PANEL_PAD - (ROW_COUNT - 1) * ROW_GAP) / ROW_COUNT

local PET_WIDTH   = 24
local PET_FILL_INSET = 1
local ROW_GAP_X   = 4 -- gap between the member row and its pet slot
local MEMBER_WIDTH = CONTAINER_WIDTH - (2 * PANEL_PAD) - PET_WIDTH - ROW_GAP_X

local PAD_X = 2 -- member row internal horizontal inset

local NAME_ROW_HEIGHT = 16
local NAME_GAP        = 1

-- Box-matched chrome (mockup 'bx': pRowBack, pPet, pBoxEdge), in design px = content units.
-- Member box and pet box both start BOX_TOP below the row top (under the 16 high header and its
-- 1px gap) and run to the row bottom, so the header floats above them.
local BOX_TOP        = 17
local BOX_HEIGHT     = ROW_HEIGHT - BOX_TOP
local BOX_CHAMFER    = 6
-- rgba(13,6,32) at .85, drawn by the mockup at .82: .85 x .82.
local BOX_FILL       = { 0.051, 0.024, 0.125, 0.697 }
-- Edge: AddRoundedFill/SkinButton are the cut helpers; the glow is the baked slice (4 px pad,
-- Theme.SLICE_CUT2_GLOW_PAD), so only its alpha is ours. The mockup's glow weight is .8; this is
-- the same ~.5 the pet column uses.
local BOX_GLOW_ALPHA = 0.5
-- Dead, ghost and offline rows swap the solid edge for dashes (mockup: dash 4, gap 3, alpha .7).
local BOX_DASH_SIZE  = 4
local BOX_DASH_GAP   = 3
local BOX_DASH_ALPHA = 0.7

-- The red edge layer's alpha is a Step curve over the health FRACTION (see UpdateRowLowHealth):
-- 1 at or below this, 0 above; the base edge takes the inverse so a low row's edge is red only.
-- EPSILON puts the step just past it so exactly 35% still counts.
local LOW_HP_FRACTION = 0.35
local LOW_HP_EPSILON  = 0.0005

-- Pet column box (mockup pPet 'bx'): the same BOX_TOP..row bottom span, chamfer 4, fill
-- rgba(13,6,32,.85) with the pink health fill inset PET_FILL_INSET inside it. The mockup draws
-- the box at pA(.9) while a pet exists (.85 x .9 = .765) and at pA(.5) when there is none, so the
-- placeholder keeps the full .85 and takes PET_EMPTY_ALPHA from its frame (.425).
local PET_CHAMFER    = 4
local PET_FILL       = { 0.051, 0.024, 0.125, 0.765 }
local PET_EMPTY_FILL = { 0.051, 0.024, 0.125, 0.85 }
local PET_PINK_ALPHA = 0.95  -- mockup pPetFill pA(.95)
local PET_EDGE_ALPHA = 0.85  -- cyan edge (purple when targeted) with the BOX_GLOW_ALPHA glow while a pet exists
local PET_EMPTY_ALPHA = 0.5  -- the dashed steel placeholder (fill and dashes) when there is none
local PET_DASH_SIZE  = 3
local PET_DASH_GAP   = 3
-- "PET" label above the box: mono 6.5, --muted at .8, baseline 3.5 above the box top. A
-- FontString anchors by its bottom edge, not its baseline, so the gap is that 3.5 less an
-- estimated 1.3 descender (not measured; check in game).
local PET_LABEL_SIZE  = 6.5
local PET_LABEL_ALPHA = 0.8
local PET_LABEL_GAP   = 2.2

-- Laser rail tuning, shared by the power and health rails (handed to
-- FrameHelpers.CreateLaserRail through the specs below).
local RAIL_CORE_HEIGHT = 9     -- fill and track line thickness; each rail's shell is exactly this tall
local RAIL_PAIR_GAP    = 4     -- space between the HP core's bottom edge and the mana core's top edge
-- The HP + mana pair is centered in the space under the name row (from
-- NAME_GAP below it down to the row bottom). RAIL_PAIR_TOP is the HP shell's
-- offset below the name row; the mana shell then hangs RAIL_PAIR_GAP under it.
local RAIL_PAIR_HEIGHT = 2 * RAIL_CORE_HEIGHT + RAIL_PAIR_GAP
local RAIL_PAIR_TOP    = NAME_GAP + (ROW_HEIGHT - NAME_ROW_HEIGHT - NAME_GAP - RAIL_PAIR_HEIGHT) / 2
local RAIL_BLOOM_SIZE  = 4     -- glow_edge strip thickness above and below the core
local RAIL_SPARK_SIZE  = 16    -- glow_round spark centered on the fill's leading edge
local RAIL_TRACK_ALPHA = 0.18  -- dim track alpha at its center (0 at both outer ends)
local RAIL_TAIL_ALPHA  = 0.35  -- core gradient alpha at the fill's left end (1 at the tip)
local RAIL_BLOOM_ALPHA = 0.45
local RAIL_SPARK_ALPHA = 0.9

-- Health laser rail tuning: the health rail is built from the power rail's
-- recipe (the RAIL_* values above) in class color. Only the halo is its own:
-- the static dispel glow wrapping the whole HP + mana pair (CreateDispelHalo,
-- TintHealthDispel), placed just outside the bloom (RAIL_BLOOM_SIZE).
local RAIL_HALO_SIZE = 4
local RAIL_HALO_ALPHA = 0.8

-- Incoming-heal / absorb overlays on the HP rail. Same values UnitFrames.lua
-- uses (its COLOR_HEAL_OVERLAY / COLOR_ABSORB_OVERLAY), duplicated here per the
-- addon's per-file convention so the two read the same: solid #39ff14 heal at
-- 0.92, white tint for the hatch texture whose own alpha carries the stripes.
local COLOR_HEAL_OVERLAY   = { COLOR_HEAL[1], COLOR_HEAL[2], COLOR_HEAL[3], 0.92 }
local COLOR_ABSORB_OVERLAY = { 1, 1, 1, 0.9 }
local HEAL_GLOW_WIDTH      = 6    -- small ADD glow on the heal segment's trailing edge
local HEAL_GLOW_ALPHA      = 0.6

local HP_TEXT_SIZE = 14

-- Box-matched header (mockup pClassTile / pRoleTag / pHead 'bx'), in the content host's design
-- units, measured from the header's (nameRow's) top-left. Left to right: the 16 class plate, the
-- role tag 3 right of it, the name 3 right of the tag (the SAME x whether or not the tag shows, so
-- names line up); at the right edge the LOW tag and the "LV n" text. Theme.SnapCut returns the
-- largest baked size at or below the request, from {2, 3, 4, 6}: the plate takes the mockup's 3,
-- and the tags' 4 was chosen over 3 deliberately (4 is Theme.CutSize(12), a baked size).
local HEADER = {
    TILE = 16, TILE_CHAMFER = 3, TILE_FILL = { 0.024, 0.012, 0.071, 0.85 * 0.9 }, TILE_STROKE_ALPHA = 0.85,
    TAG_W = 13, TAG_H = 12, TAG_TOP = 2, TAG_GAP = 3, TAG_CHAMFER = 4, TAG_STROKE_ALPHA = 0.9,
    TAG_FILL = { 0.051, 0.024, 0.125, 0.95 * 0.95 }, -- mockup pA(.95) x rgba(13,6,32,.95)
    NAME_GAP = 3, NAME_ALPHA = 0.95,
    -- Level text hangs 1 past the rail's right edge. The LOW tag's right edge sits LOW_GAP left of
    -- the rail edge + 1 with no level, and a further LEVEL_RESERVE (the mockup's fixed 36, room for
    -- "LV 59" with air) left of that while the level shows, so the tag never jumps between levels.
    RIGHT_EDGE = 1, LOW_W = 25, LOW_GAP = 2, LEVEL_RESERVE = 36,
}

local ROW_DEFS = {
    { unit = "player", petUnit = "pet" },
    { unit = "party1", petUnit = "partypet1" },
    { unit = "party2", petUnit = "partypet2" },
    { unit = "party3", petUnit = "partypet3" },
    { unit = "party4", petUnit = "partypet4" },
}

-- ALERTS LIVE OUTSIDE THE PANEL, 2026-09-21 (Parker's call).
--
-- Cleansable debuffs and a MISSING party buff appear in a tray just
-- outside the container's LEFT edge, level with the member's row. Two earlier
-- attempts both put them INSIDE: side columns, which cut a 162px row's health
-- bar down to 69px, and then overlaying the bar's ends, which kept the width
-- but still let row content depend on what is happening to the party.
--
-- Outside solves the real problem: the panel occupies exactly the same pixels
-- whether nobody has a debuff or everybody does, so nothing reflows and the
-- health bar is always the full width of the row. Parker: "stuff that i can
-- cleanse or fort falling off should show up outside the party bounding box by
-- the party member that way the size is always the same."
--
-- Left side, not right (moved 2026-10-03): in the Gunsight HUD the panel's right
-- edge is exactly where the left cast tape sits, so a right-hand tray stuck into
-- the cast bar. Nothing sits left of the party panel. The tray is mirrored:
-- icons right-aligned against the panel's left edge, slot 1 nearest the panel,
-- later slots stepping away from it.
local ALERT_ICON_SIZE  = 22
local ALERT_GAP        = 3
local ALERT_TRAY_INSET = 6   -- clear of the panel's border and glow
local MAX_DEBUFF_ICONS = 2
local MAX_ALERT_ICONS  = MAX_DEBUFF_ICONS + 1  -- cleansables first, then missing party buffs

-- Mirrors Buffs.lua's MAX_DEBUFF_SLOTS/MAX_BUFF_SLOTS scan bounds.
local MAX_PARTY_DEBUFF_SLOTS = 16
local MAX_PARTY_BUFF_SLOTS   = 32

-- Dim red "needs it" look (Part C missing-buff state): the buff's spell icon tinted this colour.
local MAINT_MISSING_COLOR = { 0.55, 0.12, 0.12, 0.55 }

-- Alert tile ring and glow alphas. A cleansable debuff tile wears its dispel colour at the
-- ring/glow alphas SkinButton gives a fresh tile (1 and its 0.35 default glow); a missing-buff
-- tile wears Theme.COLOR_RED, a touch under full so the ring reads as a warning rather than a
-- solid frame, with a stronger glow so it carries from across the screen. Every tile is retinted
-- on every paint, because the pool reuses a tile between the two uses.
local ALERT_RING_ALPHA = 1
local ALERT_GLOW_ALPHA = 0.35
local ALERT_RING_ALPHA_MISSING = 0.95
local ALERT_GLOW_ALPHA_MISSING = 0.5

-- Party buffs the player can provide, per class token. The tray alerts only for
-- a buff the player KNOWS (spellbook check) and has enabled, and only when the
-- unit lacks it (an up buff never alerts, whatever time it has left: Parker, "we don't have
-- to show it if it is there"). `names` is every aura name that satisfies it, from ANY caster:
-- the single-target name first, then the group version (a Prayer of Fortitude from another
-- priest covers Power Word: Fortitude).
-- `spell` is the name used for the known check and the icon. Names are ENGLISH
-- only (deriving them from spell ids is out of scope), so a non-English client
-- resolves no buff and gets no alerts. A class with no
-- entry (Warlock, ...) gets no buff alerts at all. `default` is the on/off state
-- before ForeverSTUwaveDB.partyBuffs[key] overrides it (/fsparty buff <key> on|off).
local PARTY_BUFFS = {
    PRIEST = {
        { key = "fortitude", spell = "Power Word: Fortitude", default = true,
          names = { "Power Word: Fortitude", "Prayer of Fortitude" } },
        { key = "spirit", spell = "Divine Spirit", default = true,
          names = { "Divine Spirit", "Prayer of Spirit" } },
        { key = "shadowprot", spell = "Shadow Protection", default = false,
          names = { "Shadow Protection", "Prayer of Shadow Protection" } },
    },
    MAGE = {
        { key = "intellect", spell = "Arcane Intellect", default = true,
          names = { "Arcane Intellect", "Arcane Brilliance" } },
    },
    DRUID = {
        { key = "motw", spell = "Mark of the Wild", default = true,
          names = { "Mark of the Wild", "Gift of the Wild" } },
    },
}
for _, list in pairs(PARTY_BUFFS) do
    for _, buff in ipairs(list) do
        buff.nameSet = {}
        for _, n in ipairs(buff.names) do buff.nameSet[n] = true end
    end
end
local PLAYER_BUFFS = PARTY_BUFFS[PlayerClass()]

-- Dead/ghost/offline row-state treatment (Part D). Grey, not an alert color --
-- this replaces the numeric HP reading with a plain status label, and must
-- not compete with the alert tray's red / dispel-colour cues.
local STATE_BAR_COLOR    = { 0.35, 0.35, 0.35, 1 }
local STATE_ROW_ALPHA    = 0.55
local STATE_DEAD_TEXT    = "Dead"
local STATE_GHOST_TEXT   = "Ghost"
local STATE_OFFLINE_TEXT = "Offline"

-------------------------------------------------------------------------------
-- Feature detection (module scope, checked once)
-------------------------------------------------------------------------------

-- One table, not one file-scope local per flag: the file is one Lua function with a
-- 200-local limit and parse-gate.py fails it at 190.
local HAS = {}
HAS.ROLE_API = type(UnitGroupRolesAssigned) == "function"
HAS.GET_UNIT_NAME = type(GetUnitName) == "function"
HAS.CLASS_ICON_TCOORDS = type(CLASS_ICON_TCOORDS) == "table"
HAS.UNIT_HEALTH_PERCENT = type(UnitHealthPercent) == "function"
HAS.PERCENT_CURVE_API = type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
    and type(Enum) == "table" and type(Enum.LuaCurveType) == "table"
    and Enum.LuaCurveType.Linear ~= nil

-- Mirrors UnitFrames.lua's class-color lookup (RAID_CLASS_COLORS[classFile]),
-- reused here rather than inventing a second lookup path (e.g. C_ClassColor).
HAS.RAID_CLASS_COLORS = type(RAID_CLASS_COLORS) == "table"

-- GetMaxPlayerLevel is not confirmed present on every build this addon
-- targets; feature-detected once and falls back to the current expansion's
-- level cap (60) so the level text still hides correctly at max level.
local MAX_PLAYER_LEVEL = (type(GetMaxPlayerLevel) == "function" and GetMaxPlayerLevel()) or 60

-- Range has no dedicated event, so out-of-range dimming is polled on a
-- ticker (see Init) instead of driven by UnitEvent registration. Both APIs
-- are feature-detected; if UnitInRange is absent this addon leaves every
-- row at full alpha rather than guessing at range.
HAS.UNIT_IN_RANGE = type(UnitInRange) == "function"
HAS.C_TIMER_TICKER = type(C_Timer) == "table" and type(C_Timer.NewTicker) == "function"

-- Optimistic: the "RAID" aura filter is tried first every scan (see
-- ScanDebuffs) and permanently disabled the first time it proves unreliable
-- (returns MORE results than an unfiltered HARMFUL scan, which a correctly
-- behaving subset filter never should), falling back to the dispel set (DISPELS).
HAS.RAID_FILTER = true

-- Dead/ghost/offline predicates (UpdateRowHealth, below). Per the addon's
-- secret-value audit these three are PLAIN (not on the health/power/absorbs/
-- range secret list), so they are truth-tested directly with no IsSecret
-- guard -- only their presence on this client is in question.
HAS.UNIT_IS_DEAD_OR_GHOST = type(UnitIsDeadOrGhost) == "function"
HAS.UNIT_IS_GHOST = type(UnitIsGhost) == "function"
HAS.UNIT_IS_CONNECTED = type(UnitIsConnected) == "function"

-- Incoming-heal / absorb reads for the HP rail overlays. Each missing API
-- disables its own overlay (nil in CreateHealthOverlays, no-op in the update)
-- and latch-logs once at module load; FS.LogDegradeOnce does not dedupe, so
-- this load-time branch runs exactly once per API.
HAS.INCOMING_HEALS = type(UnitGetIncomingHeals) == "function"
HAS.TOTAL_ABSORBS = type(UnitGetTotalAbsorbs) == "function"
if not HAS.INCOMING_HEALS then
    FS.LogDegradeOnce("partyframes_noincomingheals",
        "|cffff4488Forever STUwave|r: UnitGetIncomingHeals unavailable, party heal overlay disabled")
end
if not HAS.TOTAL_ABSORBS then
    FS.LogDegradeOnce("partyframes_noabsorbapi",
        "|cffff4488Forever STUwave|r: UnitGetTotalAbsorbs unavailable, party absorb overlay disabled")
end

-------------------------------------------------------------------------------
-- Range dimming: member and pet alpha are driven independently, so a member
-- in range with an out-of-range pet shows a normal member row next to a
-- dimmed pet slot, and vice versa.
-------------------------------------------------------------------------------

local RANGE_ALPHA_IN_RANGE  = 1.0
local RANGE_ALPHA_OUT_RANGE = 0.4
local RANGE_TICK_INTERVAL   = 0.2

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- Runs one update step under pcall so a single failing step cannot abort the
-- rest of the row (TryStep); ReportOnce prints a failure once per label
-- instead of once per scan. Shared factory (FrameHelpers.lua); the two
-- describe functions preserve this file's own wording for each idiom.
local TryStep, ReportOnce = FS.FrameHelpers.NewStepRunner(
    function(label) return "|cffff4488Forever STUwave|r partyframe step '" .. label .. "'" end,
    function(label) return "|cffff4488Forever STUwave|r partyframe " .. label end
)

-- Scale in the engine so secret health fractions never enter Lua arithmetic.
local function BuildHealthPercentCurve()
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Linear)
    curve:AddPoint(0, 0)
    curve:AddPoint(1, 100)
    return curve
end

local HEALTH_PERCENT_CURVE
if HAS.UNIT_HEALTH_PERCENT then
    local curves = _G["CurveConstants"]
    if type(curves) == "table" and curves.ScaleTo100 then
        HEALTH_PERCENT_CURVE = curves.ScaleTo100
    elseif HAS.PERCENT_CURVE_API then
        local ok, curve = pcall(BuildHealthPercentCurve)
        if ok then
            HEALTH_PERCENT_CURVE = curve
        else
            ReportOnce("health percent curve", curve)
        end
    end
end

local healthPercentBroken = false
local function UpdateHealthPercentText(text, unit, cur, max)
    if HEALTH_PERCENT_CURVE and not healthPercentBroken then
        local ok, percent = pcall(UnitHealthPercent, unit, false, HEALTH_PERCENT_CURVE)
        if ok then
            local formatted, err = pcall(text.SetFormattedText, text, "%.0f%%", percent)
            if formatted then
                text:Show()
                return
            end
            percent = err
        end
        healthPercentBroken = true
        ReportOnce("health percent", percent)
    end

    if not IsSecret(cur) and not IsSecret(max) and cur ~= nil and max ~= nil and max > 0 then
        text:SetFormattedText("%.0f%%", cur / max * 100)
        text:Show()
    else
        text:SetText("")
    end
end

-------------------------------------------------------------------------------
-- Bar building blocks
-------------------------------------------------------------------------------

local RAIL_POWER_SPEC = {
    coreHeight = RAIL_CORE_HEIGHT,
    bloomSize = RAIL_BLOOM_SIZE,
    sparkWidth = RAIL_SPARK_SIZE,
    sparkHeight = RAIL_SPARK_SIZE,
    tailAlpha = RAIL_TAIL_ALPHA,
    trackAlpha = RAIL_TRACK_ALPHA,
    bloomAlpha = RAIL_BLOOM_ALPHA,
    sparkAlpha = RAIL_SPARK_ALPHA,
    color = COLOR_POWER,
}

local RAIL_HEALTH_SPEC = {
    coreHeight = RAIL_CORE_HEIGHT,
    bloomSize = RAIL_BLOOM_SIZE,
    sparkWidth = RAIL_SPARK_SIZE,
    sparkHeight = RAIL_SPARK_SIZE,
    tailAlpha = RAIL_TAIL_ALPHA,
    trackAlpha = RAIL_TRACK_ALPHA,
    bloomAlpha = RAIL_BLOOM_ALPHA,
    sparkAlpha = RAIL_SPARK_ALPHA,
    color = COLOR_HEALTH,
    -- DELIBERATE exception to the addon-wide plain-Mononoki/no-outline
    -- rule (see ApplyMono): this bar's fill is class-colored, not the
    -- fixed neon pink, so a plain white number washes out on light
    -- classes (Priest, Mage, Hunter).
    styleText = function(text) ApplyFontGeneric(text, FONT_MONO, HP_TEXT_SIZE, nil, "OUTLINE") end,
}

-- The dispel halo: static full-width glow_edge strips that wrap the whole rail
-- PAIR, two faded halves per side so TintHealthDispel can fade both outer ends
-- to 0 the way the track does. The strips pin to the pair's outer cores (top
-- strips above topBar, bottom strips below bottomBar) because the rails are only
-- RAIL_PAIR_GAP apart; see the PartyFrames entry in CLAUDE.md. Same glow_edge
-- orientations as the bloom.
--
-- One halo object on one host. The host is a child of topBar's shell so the
-- row's dead / offline dimming reaches it.
-- When the bottom rail is hidden (a manaless unit), the bottom strips simply
-- wrap an invisible rail; that is acceptable, so nothing special-cases it.
-- Returns { host, left, right }, the shape TintHealthDispel reads.
local function CreateDispelHalo(topBar, bottomBar)
    local haloHost = CreateFrame("Frame", nil, topBar.shell)
    haloHost:SetPoint("TOPLEFT", topBar.shell, "TOPLEFT", 0, 0)
    haloHost:SetPoint("BOTTOMRIGHT", bottomBar.shell, "BOTTOMRIGHT", 0, 0)
    haloHost:SetFrameLevel(topBar:GetFrameLevel())
    -- stripEdge is the strip's own edge that touches its bar ("BOTTOM" for a
    -- strip above it, "TOP" for one below); leftAnchor/rightAnchor are the bar
    -- points its two ends pin to.
    local function HaloStrip(flip, bar, stripEdge, leftAnchor, rightAnchor, yOff)
        local tex = haloHost:CreateTexture(nil, "ARTWORK")
        tex:SetTexture(GLOW_EDGE_TEXTURE)
        tex:SetPoint(stripEdge .. "LEFT", bar, leftAnchor, 0, yOff)
        tex:SetPoint(stripEdge .. "RIGHT", bar, rightAnchor, 0, yOff)
        tex:SetHeight(RAIL_HALO_SIZE)
        if flip then tex:SetTexCoord(0, 1, 0, 0, 1, 1, 1, 0) end
        tex:SetBlendMode("ADD")
        return tex
    end
    local halo = {
        host = haloHost,
        left = {
            HaloStrip(true, topBar, "BOTTOM", "TOPLEFT", "TOP", RAIL_BLOOM_SIZE),
            HaloStrip(false, bottomBar, "TOP", "BOTTOMLEFT", "BOTTOM", -RAIL_BLOOM_SIZE),
        },
        right = {
            HaloStrip(true, topBar, "BOTTOM", "TOP", "TOPRIGHT", RAIL_BLOOM_SIZE),
            HaloStrip(false, bottomBar, "TOP", "BOTTOM", "BOTTOMRIGHT", -RAIL_BLOOM_SIZE),
        },
    }
    haloHost:Hide()
    return halo
end

-------------------------------------------------------------------------------
-- Aura tracking: dispellable-debuff scan + buff-maintenance scan (Parts A/B/C)
-------------------------------------------------------------------------------

-- Shows the health rail's dispel halo (the static glow wrapping the whole HP +
-- mana pair, built by CreateDispelHalo) in `color`, or hides it when `color`
-- is nil. This is the at-a-glance dispel signal; it does not follow the fill,
-- so it reads at any HP, full included. Retints only when the color changed:
-- UpdateRowAlerts runs on every UNIT_AURA.
local function TintHealthDispel(bar, color)
    local halo = bar.fsRail.halo
    if not color then
        halo.host:Hide()
        return
    end
    local r, g, b = color[1], color[2], color[3]
    if halo.r ~= r or halo.g ~= g or halo.b ~= b then
        halo.r, halo.g, halo.b = r, g, b
        -- Each half fades from 0 at its outer end to full at the center.
        for _, tex in ipairs(halo.left) do
            if not SetRailGradient(tex, r, g, b, 0, RAIL_HALO_ALPHA) then
                tex:SetVertexColor(r, g, b, RAIL_HALO_ALPHA)
            end
        end
        for _, tex in ipairs(halo.right) do
            if not SetRailGradient(tex, r, g, b, RAIL_HALO_ALPHA, 0) then
                tex:SetVertexColor(r, g, b, RAIL_HALO_ALPHA)
            end
        end
    end
    halo.host:Show()
end

-- The shared palette (FS.Theme.DISPEL_COLORS); Blizzard's DebuffTypeColor global does not
-- exist on 16001 and is not consulted.
local function GetDispelColor(dispelType)
    if not dispelType or dispelType == "" then return nil end
    return FS.Theme.DISPEL_COLORS[dispelType]
end

-- Straight-edge dashes around a w x h box with chamfer `c`, as 1px textures on `host`, one run
-- per edge from `from` to `to` along it. Returns the dash list; TintDashes colours it. Round
-- rounds all four corners, so every run starts and ends c in. Cut cuts TOP-LEFT and
-- BOTTOM-RIGHT only: LEFT starts at the cut, RIGHT ends at it, TOP starts at it, BOTTOM ends at
-- it, and the square TOP-RIGHT / BOTTOM-LEFT ends run flush (the vertical edges leave the
-- corner pixel to the horizontal ones). The chamfers themselves stay undashed. A flat white
-- texture plus vertex colour, so one tint call recolours a dash.
local function BuildDashEdge(host, w, h, c, size, gap)
    local dashes = {}
    local function dashRun(edge, from, to)
        for offset = from, to - size, size + gap do
            local dash = host:CreateTexture(nil, "BORDER")
            dash:SetTexture(FLAT_TEXTURE)
            if edge == "LEFT" or edge == "RIGHT" then
                dash:SetSize(1, size)
                dash:SetPoint("TOP" .. edge, host, "TOP" .. edge, 0, -offset)
            else
                dash:SetSize(size, 1)
                dash:SetPoint(edge .. "LEFT", host, edge .. "LEFT", offset, 0)
            end
            dashes[#dashes + 1] = dash
        end
    end
    if FS.Theme.CHROME_CORNERS == "cut" then
        dashRun("LEFT", c, h - 1)
        dashRun("RIGHT", 1, h - c)
        dashRun("TOP", c, w)
        dashRun("BOTTOM", 0, w - c)
    else
        dashRun("LEFT", c, h - c)
        dashRun("RIGHT", c, h - c)
        dashRun("TOP", c, w - c)
        dashRun("BOTTOM", c, w - c)
    end
    return dashes
end

local function TintDashes(dashes, r, g, b, a)
    for _, dash in ipairs(dashes) do dash:SetVertexColor(r, g, b, a) end
end

-- Paints the member box's edge (frame.box.edge, see BuildRowBox) from the row's state (mockup pBoxEdge; the
-- low-HP red is a separate layer above, see UpdateRowLowHealth): the dispel colour of a cleansable debuff (the
-- halo's own colour) over the target purple (Theme.COLOR_TARGET, the row's unit is the player's target) over
-- dead/ghost/offline steel over live cyan. Live is a solid ring plus glow; down swaps both for steel, purple or
-- dispel dashes. The box is never dimmed (the mockup draws it with A(), not pA(), so a down row's fill and
-- dashes stay at full strength; the dashes carry their own .7). Retints only when the look changed:
-- UpdateRowAlerts and UpdateRowHealth both call it on every update, and PLAYER_TARGET_CHANGED (Init's
-- moduleEvents) calls it for every row. The target test is re-read here each call, so a roster change that
-- re-seats who holds this token repaints too (GROUP_ROSTER_UPDATE -> UpdateAll -> UpdateRowHealth ->
-- ApplyBoxEdge). UnitIsUnit is SecretWhenUnitComparisonRestricted (secret only on an addon-restricted map): a
-- secret answer is never branched on and counts as "not the target" (the pcall also covers a client without
-- it).
local function ApplyBoxEdge(frame)
    local box = frame.box
    if not box then return end
    local down = frame.rowDown and true or false
    local isTarget = false
    if frame.unit then
        local ok, same = pcall(UnitIsUnit, "target", frame.unit)
        isTarget = ok and not IsSecret(same) and same == true
    end
    local color = frame.dispelColor or (isTarget and FS.Theme.COLOR_TARGET) or (down and COLOR_STEEL)
        or COLOR_POWER
    local r, g, b = color[1], color[2], color[3]
    if box.edgeDown == down and box.edgeR == r and box.edgeG == g and box.edgeB == b then return end
    box.edgeDown, box.edgeR, box.edgeG, box.edgeB = down, r, g, b
    local ring, glow = box.edge.fsSkin.border.ring, box.edge.fsSkin.glow
    ring:SetShown(not down)
    glow:SetShown(not down)
    box.dashHost:SetShown(down)
    if down then
        TintDashes(box.dashes, r, g, b, BOX_DASH_ALPHA)
    else
        ring:SetVertexColor(r, g, b, 1)
        glow:SetVertexColor(r, g, b, BOX_GLOW_ALPHA)
    end
end

-- The dispel colour for a row (nil = none): the health rail's halo and the box edge both read it.
local function SetRowDispel(frame, color)
    TintHealthDispel(frame.health, color)
    frame.dispelColor = color
    ApplyBoxEdge(frame)
end

-- True once a read error (the pcall path in the shared reader) has gone by since the
-- flag was last cleared. The shared reader returns nil for both "no aura at this slot"
-- and "the read threw", so the buff scan watches this to tell an empty list from an
-- unreadable unit.
local auraReadFailed = false

local function NoteAuraReadError(label, err)
    auraReadFailed = true
    return ReportOnce(label, err)
end

-- Delegates to the shared aura-slot reader (FrameHelpers.lua) and keeps only what this file
-- reads: name, icon and dispel type, plus index/filter echoed back for the alert tooltip. No expiry
-- or caster is read (an up buff never alerts, from any caster).
local function ReadAuraSlot(unit, index, filter)
    local data = FS.FrameHelpers.ReadAuraSlot(unit, index, filter, NoteAuraReadError)
    if not data then return nil end
    return {
        name = data.name,
        icon = data.icon,
        dispelType = data.dispelType,
        spellId = data.spellId,  -- may be secret; SetTipSpell drops it
        index = index,
        filter = filter,
    }
end

local function ScanHarmful(unit, filter)
    local list = {}
    for slot = 1, MAX_PARTY_DEBUFF_SLOTS do
        local aura = ReadAuraSlot(unit, slot, filter)
        if not aura then break end
        list[#list + 1] = aura
    end
    return list
end

-- Builds this member's cleansable-debuff list (Part A/B). Prefers the
-- "RAID" aura filter (pre-filtered to debuffs this player's class can
-- dispel); a RAID-filtered scan that comes back with MORE results than the
-- plain HARMFUL scan is proof the filter isn't behaving as documented on
-- this build (a subset filter can never return more), so it's disabled for
-- the rest of the session and every future call falls back to matching
-- dispelType against the player's dispel set instead.
local function ScanDebuffs(unit)
    local harmful = ScanHarmful(unit, "HARMFUL")

    -- The player's dispel set (DISPELS.Set) is the AUTHORITY, always, 2026-09-21.
    --
    -- This used to trust the "HARMFUL|RAID" filter whenever it returned no
    -- MORE rows than the plain scan, on the reasoning that a subset filter can
    -- never return more. That test has a hole big enough to drive the whole
    -- feature through: a filter that does nothing at all returns exactly the
    -- same rows, which is `equal`, which passed -- so on any client where RAID
    -- is not implemented, every debuff was labelled cleansable. Parker, on a
    -- priest: "the buffs and debuffs that are showing up i can't even cleanse".
    --
    -- The dispel type is on the aura data we already read, so there is no
    -- reason to take the filter's word for anything. RAID is now only a
    -- pre-filter that can narrow the candidate list; whatever survives it is
    -- still checked against what this class can actually remove. A client
    -- where RAID works does less scanning, and a client where it is a no-op
    -- gets the same correct answer.
    local candidates = harmful
    if HAS.RAID_FILTER then
        local raidFiltered = ScanHarmful(unit, "HARMFUL|RAID")
        if #raidFiltered < #harmful then
            candidates = raidFiltered
        elseif #raidFiltered > #harmful then
            -- A subset that is bigger than its superset is not a subset.
            HAS.RAID_FILTER = false
            ReportOnce("RAID debuff filter",
                "returned more results than plain HARMFUL scan; ignoring it")
        end
        -- Equal counts tell us nothing: either everything is cleansable, or
        -- the filter is inert. Fall through and let the class check decide.
    end

    local cleansable = {}
    local dispels = DISPELS.Set()
    if next(dispels) then
        for _, aura in ipairs(candidates) do
            if aura.dispelType and dispels[aura.dispelType] then
                cleansable[#cleansable + 1] = aura
            end
        end
    end

    return cleansable, harmful
end

-- Party buff state ---------------------------------------------------------------

-- A value only when it is plain (not secret) and of the wanted type, else nil.
local function PlainValue(v, kind)
    if v == nil or IsSecret(v) or type(v) ~= kind then return nil end
    return v
end

-- spellID, iconID of a spell by name, plain values only; nil when the name does not resolve.
local function ResolveSpell(name)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, name)
        if ok and info ~= nil and not IsSecret(info) and type(info) == "table" then
            return PlainValue(info.spellID, "number"), PlainValue(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, _, _, icon, _, _, _, id = pcall(GetSpellInfo, name)
        if ok then return PlainValue(id, "number"), PlainValue(icon, "number") end
    end
    return nil
end

-- true / false / nil (cannot tell) for "does the player know this spell id", asking every
-- spellbook API the client has (the approach HudLogic.lua's IsKnownId takes). With none of
-- them present the id already resolved by name, which in this spellbook API means known.
local function IsKnownSpellId(id)
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    local asked, sawFalse, unreadable = false, false, false
    for i = 1, 3 do
        local fn = fns[i]
        if fn then
            asked = true
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) then
                if r then return true end
                sawFalse = true
            else
                unreadable = true
            end
        end
    end
    if not asked then return true end
    if sawFalse then return false end  -- a readable "no" beats an API that raised or answered secret
    if unreadable then return nil end
    return nil
end

-- key -> { known = bool, icon = id|nil }. Only a definite answer is cached; the cache is
-- dropped when the spellbook changes (SPELLS_CHANGED and friends, wired in Init).
local buffSpellCache = {}

local function ResetBuffSpellCache()
    buffSpellCache = {}
end

local function BuffSpellState(buff)
    local hit = buffSpellCache[buff.key]
    if hit then return hit end
    local id, icon = ResolveSpell(buff.spell)
    local known = false
    if id then
        known = IsKnownSpellId(id)
        if known == nil then return { known = false, icon = icon, id = id } end  -- unreadable: ask again
    end
    local state = { known = known, icon = icon, id = id }
    buffSpellCache[buff.key] = state
    return state
end

-- true / false / nil (cannot tell) for one { id, name } dispel spell: the id first, then the id
-- the name resolves to (covers a rank id the table lacks).
local function KnowsDispelSpell(spell)
    local known = IsKnownSpellId(spell[1])
    if known ~= false then return known end
    local id = ResolveSpell(spell[2])
    if id and id ~= spell[1] then return IsKnownSpellId(id) end
    return false
end

-- The dispel types the player can remove right now: { [type] = true }, empty for a class with
-- none. Computed on first use and cached; the spellbook events drop DISPELS.cache. A type whose
-- spells could not be read (every spellbook API raised or answered secret) counts as available,
-- the class's old static behaviour, and that answer is NOT cached, so the next call asks again.
function DISPELS.Set()
    local cache = DISPELS.cache
    if cache then return cache end
    local set, settled = {}, true
    for dispelType, spells in pairs(DISPELS.CLASS[PlayerClass()] or {}) do
        local known = false
        for _, spell in ipairs(spells) do
            local answer = KnowsDispelSpell(spell)
            if answer then
                known = true
                break
            elseif answer == nil then
                known = nil
            end
        end
        if known == nil then
            settled = false
            known = true
        end
        if known then set[dispelType] = true end
    end
    if settled then DISPELS.cache = set end
    return set
end

-- Sorted "Disease/Magic" list of the types in `set`, "nothing" when empty (the /fsparty report).
function DISPELS.Describe(set)
    local t = {}
    for k in pairs(set) do t[#t + 1] = k end
    table.sort(t)
    return #t > 0 and table.concat(t, "/") or "nothing"
end

-- The tile art for a buff: the spell texture, else the spell-info icon, else a flat tile.
-- A texture the engine returned is kept on the state (dropped with it on a spellbook
-- change), so the pcall runs once per spell, and only for a buff that is actually missing.
local function BuffIcon(buff, state)
    if state.tex then return state.tex end
    local fn = C_Spell and C_Spell.GetSpellTexture
    if fn then
        local ok, tex = pcall(fn, buff.spell)
        if ok and not IsSecret(tex) and (type(tex) == "number" or type(tex) == "string") then
            state.tex = tex
            return tex
        end
    end
    return state.icon or FLAT_TEXTURE
end

-- The player's saved on/off for a buff, or nil when nothing is saved (the default applies).
local function SavedBuffValue(buff)
    local db = ForeverSTUwaveDB
    if type(db) == "table" and type(db.partyBuffs) == "table" then return db.partyBuffs[buff.key] end
    return nil
end

local function BuffEnabled(buff)
    local saved = SavedBuffValue(buff)
    if saved == nil then return buff.default end
    return saved == true
end

-- Reused across calls (UpdateRowAlerts runs on every UNIT_AURA for every row): the entry
-- tables are overwritten in place, so a caller must finish with the list before the next call.
local partyBuffEntries = {}

-- Per-unit state of every party buff the player knows and has enabled, in table order:
-- returns `list, n` where list[1..n] are { buff, state, icon, aura, reason }. `aura` is
-- a HELPFUL aura from ANY caster whose name is in buff.names (any one will do: how long it has
-- left is never read). reason: "missing", "ok" or "unreadable" (the unit has an aura whose
-- name is secret, or the aura read failed, so absence cannot be claimed; never alerts).
-- `icon` is set for "missing" only.
-- n == 0 (nothing known and enabled) costs no aura read.
local function EvaluatePartyBuffs(unit)
    local list, n = partyBuffEntries, 0
    for _, buff in ipairs(PLAYER_BUFFS or {}) do
        if BuffEnabled(buff) then
            local state = BuffSpellState(buff)
            if state.known then
                n = n + 1
                local entry = list[n]
                if not entry then
                    entry = {}
                    list[n] = entry
                end
                entry.buff, entry.state = buff, state
                entry.icon, entry.aura, entry.reason = nil, nil, nil
            end
        end
    end
    -- Drop entries beyond n so a stale scratch entry never keeps an old aura table alive.
    for i = n + 1, #list do list[i] = nil end
    if n == 0 then return list, 0 end

    local unreadable = false
    auraReadFailed = false
    for slot = 1, MAX_PARTY_BUFF_SLOTS do
        local aura = ReadAuraSlot(unit, slot, "HELPFUL")
        if not aura then
            -- nil is the end of the list, unless the read threw: then the list is unknown.
            if auraReadFailed then unreadable = true end
            break
        end
        local name = aura.name
        if IsSecret(name) then
            unreadable = true
        elseif type(name) == "string" then
            for i = 1, n do
                local entry = list[i]
                if entry.buff.nameSet[name] and not entry.aura then
                    entry.aura = aura
                end
            end
        end
    end

    for i = 1, n do
        local entry = list[i]
        if not entry.aura then
            entry.reason = unreadable and "unreadable" or "missing"
            if entry.reason == "missing" then entry.icon = BuffIcon(entry.buff, entry.state) end
        else
            entry.reason = "ok"
        end
    end
    return list, n
end

-------------------------------------------------------------------------------
-- Frame assembly
-------------------------------------------------------------------------------

-- Compact clickable pet slot: a thin vertical health bar, its own secure
-- click surface (unit = the pet token, type1=target only -- no menu, unlike
-- the member rows). RegisterUnitWatch (applied by the caller) shows/hides it
-- based on whether the pet exists. The button keeps its FULL row rect so clicks are
-- unchanged; the visuals are the Box-matched pet box (mockup pPet 'bx'), BOX_TOP below the
-- row top down to the slot bottom, with a "PET" label above it.
local function BuildPetSlot(unit, frameName, parent, placeholderParent)
    local f = CreateFrame("Button", frameName, parent, "SecureUnitButtonTemplate")
    f:SetSize(PET_WIDTH, ROW_HEIGHT)
    f:RegisterForClicks("AnyUp")
    f:SetAttribute("unit", unit)
    f:SetAttribute("*type1", "target")
    f.unit = unit

    local visual = CreateFrame("Frame", nil, f)
    visual:SetAllPoints(f)
    f.visual = visual

    local box = CreateFrame("Frame", nil, visual)
    box:SetPoint("TOPLEFT", visual, "TOPLEFT", 0, -BOX_TOP)
    box:SetPoint("BOTTOMRIGHT", visual, "BOTTOMRIGHT", 0, 0)
    -- Cut: the box fill is ONE nine-slice of the same rect and margin as the edge ring below, so
    -- fill, ring and the corner erase scale together (AddRoundedFill's unit-sized cut triangles only
    -- sit under the ring at one texel-to-pixel ratio, and this panel is scaled by Layout.Scale()).
    -- Round, or no slicing: the flat rects and triangles.
    if not (FS.Theme.AddCutSliceFill and FS.Theme.AddCutSliceFill(box, PET_FILL, PET_CHAMFER)) then
        AddRoundedFill(box, PET_FILL, PET_CHAMFER)
    end
    f.box = box

    -- The pink fill sits inside the box, above its fill.
    local health = CreateFrame("StatusBar", nil, visual)
    health:SetPoint("TOPLEFT", box, "TOPLEFT", PET_FILL_INSET, -PET_FILL_INSET)
    health:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -PET_FILL_INSET, PET_FILL_INSET)
    health:SetFrameLevel(box:GetFrameLevel() + 1)
    health:SetOrientation("VERTICAL")
    health:SetStatusBarTexture(FLAT_TEXTURE)
    health:SetStatusBarColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], PET_PINK_ALPHA)
    health:SetMinMaxValues(0, 1)
    health:SetValue(0)

    local petCornerHost
    if type(FS.Theme.AddCornerMask) == "function" then
        local corners = CreateFrame("Frame", nil, visual)
        petCornerHost = corners
        corners:SetAllPoints(health)
        corners:SetFrameLevel(health:GetFrameLevel() + FS.Theme.BAR_CORNER_MASK_LEVEL)
        -- Cut: the edge below is SkinButton at PET_CHAMFER, a NINE-SLICED ring, drawn at the
        -- engine's own texel-to-pixel ratio (about 0.75 to 0.8 px per texel), while the unit-sized
        -- AddCornerMask quads are sized in UI units, so the two only agreed at one ratio and the
        -- opaque wedge overshot the ring's inner edge (a dark triangle, live 2026-10-04, "update
        -- the corners of the fill"). So the erase is a nine-slice too: AddCutFillErase over the BOX
        -- rect (the rect the ring is sliced over) at the ring's own chamfer, trimmed to the fill
        -- rect by this host's clip, so wedge and ring scale together. Its colour is the box fill's
        -- own rgb at full alpha: PET_FILL is translucent (a scrim over the world) and an opaque
        -- erase cannot match it over every backdrop, but PET_FILL's rgb is the closest single
        -- colour (COLOR_BAR_TRACK, the old erase colour, is the box fill over pure black and reads
        -- darker than the box over any lit terrain). No clip support or no slicing: the quads below.
        -- Round: concentric radius.
        local erase
        if FS.Theme.CHROME_CORNERS == "cut" and type(FS.Theme.AddCutFillErase) == "function"
            and corners.SetClipsChildren then
            erase = FS.Theme.AddCutFillErase(corners, box, { PET_FILL[1], PET_FILL[2], PET_FILL[3], 1 }, PET_CHAMFER)
            if erase then corners:SetClipsChildren(true) end
        end
        if not erase then
            -- The baked erase triangle already allows for the 1px fill inset.
            local maskRadius = FS.Theme.CHROME_CORNERS == "cut" and PET_CHAMFER or (PET_CHAMFER - PET_FILL_INSET)
            FS.Theme.AddCornerMask(corners, health, COLOR_BAR_TRACK, maskRadius)
        end
    end
    f.health = health

    -- The edge stroke and glow get their own frame one level above the mask host: the erase
    -- quads sit on it (health + BAR_CORNER_MASK_LEVEL) and would overpaint a stroke drawn on
    -- `visual` or `box` along the diagonal. Cyan at PET_EDGE_ALPHA while a pet exists, or purple
    -- (COLOR_TARGET) when targeted (the ring and glow are the retintable cut slices SkinButton
    -- builds).
    local edge = CreateFrame("Frame", nil, visual)
    edge:SetAllPoints(box)
    edge:SetFrameLevel((petCornerHost or health):GetFrameLevel() + 1)
    SkinButton(edge, { chamfer = PET_CHAMFER, glowAlpha = BOX_GLOW_ALPHA, borderColor = COLOR_POWER })
    edge.fsSkin.border.ring:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], PET_EDGE_ALPHA)
    edge.fsSkin.glow:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], BOX_GLOW_ALPHA)
    f.edge = edge

    -- Targeted pet: the same purple as the member box (Theme.COLOR_TARGET) instead of cyan, at the
    -- pet's own alphas. A method on the slot rather than a file-scope function (the file is at
    -- Lua's 200 file-scope local limit). Run from UpdateRowPet (the pet appears or changes) and,
    -- for every row, on PLAYER_TARGET_CHANGED. UnitIsUnit is secret only on an addon-restricted
    -- map: a secret answer is never branched on and counts as not targeted. Retints only on a
    -- real change; the build-time cyan is the initial state.
    function f:ApplyTargetEdge()
        local ok, same = pcall(UnitIsUnit, "target", self.unit)
        local targeted = ok and not IsSecret(same) and same == true
        if (self.edgeTargeted or false) == targeted then return end
        self.edgeTargeted = targeted
        local color = targeted and FS.Theme.COLOR_TARGET or COLOR_POWER
        self.edge.fsSkin.border.ring:SetVertexColor(color[1], color[2], color[3], PET_EDGE_ALPHA)
        self.edge.fsSkin.glow:SetVertexColor(color[1], color[2], color[3], BOX_GLOW_ALPHA)
    end

    -- "PET", centred above the box. On the edge frame so the box glow cannot wash it; the
    -- font is set before the text (a FontString without one throws "Font not set").
    local label = edge:CreateFontString(nil, "OVERLAY")
    ApplyMono(label, PET_LABEL_SIZE, { COLOR_MUTED[1], COLOR_MUTED[2], COLOR_MUTED[3], PET_LABEL_ALPHA })
    label:SetPoint("BOTTOM", box, "TOP", 0.5, PET_LABEL_GAP)
    label:SetText("PET")
    f.petLabel = label

    -- The engine watches the clickable button; only this nonsecure sibling
    -- changes visibility to represent an empty pet column: the same box as a dashed steel
    -- outline, the whole thing (fill and dashes) at PET_EMPTY_ALPHA.
    local placeholder = CreateFrame("Frame", nil, placeholderParent)
    placeholder:SetPoint("TOPLEFT", f, "TOPLEFT", 0, -BOX_TOP)
    placeholder:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", 0, 0)
    placeholder:SetAlpha(PET_EMPTY_ALPHA)
    AddRoundedFill(placeholder, PET_EMPTY_FILL, PET_CHAMFER)
    TintDashes(BuildDashEdge(placeholder, PET_WIDTH, BOX_HEIGHT, PET_CHAMFER, PET_DASH_SIZE, PET_DASH_GAP),
        COLOR_STEEL[1], COLOR_STEEL[2], COLOR_STEEL[3], 1)
    f.placeholder = placeholder
    f:HookScript("OnShow", function() placeholder:Hide() end)
    f:HookScript("OnHide", function() placeholder:Show() end)
    placeholder:SetShown(not UnitExists(unit))

    return f
end

-- Right-side debuff icon (Part B): a plain Frame skinned via Theme.SkinButton
-- (same construction as Buffs.lua's aura buttons, which also skin a plain
-- Frame rather than a Button). Mouse is enabled so OnEnter/OnLeave can drive
-- a GameTooltip; UpdateRowAlerts sets .unit/.auraIndex/.filter before
-- showing it so the tooltip looks up the exact same aura being displayed.
local function CreateAlertIcon(parent)
    local icon = CreateFrame("Frame", nil, parent)
    icon:SetSize(ALERT_ICON_SIZE, ALERT_ICON_SIZE)
    icon:EnableMouse(true)

    -- Opaque backing. These sit over the world rather than over a frame, so
    -- without it a dark spell icon can disappear into a dark background. Round: a
    -- 1px-outset square texture. Cut: that square would poke past the ring's TOP-LEFT and
    -- BOTTOM-RIGHT cuts, so the backing is a cut fill at the ring's own chamfer
    -- (Theme.CutSizeIcon, what SkinButton picks for this size) on a child frame outset 1px
    -- and one level BELOW the icon, so it stays behind the icon art. A same-chamfer
    -- outset is a diagonal parallel to the ring's, about 1.4px out.
    local backingColor = { 0.024, 0.012, 0.071, 1 }
    if FS.Theme.CHROME_CORNERS == "cut" then
        local backing = CreateFrame("Frame", nil, icon)
        backing:SetPoint("TOPLEFT", icon, "TOPLEFT", -1, 1)
        backing:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", 1, -1)
        backing:SetFrameLevel(math.max(icon:GetFrameLevel() - 1, 0))
        AddRoundedFill(backing, backingColor, FS.Theme.CutSizeIcon(ALERT_ICON_SIZE))
    else
        local backing = icon:CreateTexture(nil, "BACKGROUND")
        backing:SetPoint("TOPLEFT", icon, "TOPLEFT", -1, 1)
        backing:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", 1, -1)
        backing:SetColorTexture(backingColor[1], backingColor[2], backingColor[3], backingColor[4])
    end

    local tex = icon:CreateTexture(nil, "ARTWORK")
    tex:SetAllPoints(icon)
    icon.tex = tex

    SkinButton(icon)

    -- Delegates to the shared aura-tooltip dispatch (FrameHelpers.lua), which
    -- also covers the HELPFUL/SetUnitBuff branch this file's own OnEnter was
    -- missing (see FrameHelpers.lua's CORRECTNESS FIX note).
    icon:SetScript("OnEnter", function(self)
        -- A missing party buff has no aura to look up: show the spell by its cached id (SetTipSpell),
        -- with the missing line under it; without one, just the "Missing: X" line.
        if self.missingText then
            GameTooltip:SetOwner(self, "ANCHOR_TOP")
            if self.fsSpellID and type(GameTooltip.SetSpellByID) == "function"
                and pcall(GameTooltip.SetSpellByID, GameTooltip, self.fsSpellID) then
                GameTooltip:AddLine(self.missingText, 1, 0.3, 0.3)
            else
                GameTooltip:SetText(self.missingText)
            end
            GameTooltip:Show()
            return
        end
        if not self.unit or not self.auraIndex then return end
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        FS.FrameHelpers.ShowAuraTooltip(self)
    end)
    icon:SetScript("OnLeave", function() GameTooltip:Hide() end)

    icon:Hide()
    return icon
end

-- Secret-safe overlay StatusBar (incoming heal / absorb shield), a child of the
-- HP rail's core bar and driven only through SetMinMaxValues/SetValue, which
-- accept secret args (the same mechanism the core fill already relies on), so
-- no cur/max fraction is ever computed in Lua. Its LEFT edge rides
-- `anchorTexture`'s RIGHT edge, a live anchor the engine repositions: the core
-- fill's texture for the first overlay, the previous overlay's fill texture to
-- chain the next (heal, then absorb). A zero value renders zero width, so a row
-- with nothing incoming looks exactly as it did before the overlays existed.
-- Port of UnitFrames.lua's CreateOverlayBar, duplicated per the addon's
-- per-file convention (that one is file-local and its health bar is not a laser
-- rail); the same KNOWN APPROXIMATION applies: the segment spans the remaining
-- gap to the bar's right edge, not the full bar width, so it under-represents
-- large heals or shields except near empty health (needing `max - cur` would be
-- illegal arithmetic on secrets).
-- Frame level bar+1: above the core fill, below the glow host (bar+2) so the HP
-- spark and bloom still read at the fill's tip, and below the text host.
local function CreateOverlayBar(bar, color, anchorTexture)
    local overlay = CreateFrame("StatusBar", nil, bar)
    overlay:SetPoint("TOP", bar, "TOP", 0, 0)
    overlay:SetPoint("BOTTOM", bar, "BOTTOM", 0, 0)
    overlay:SetPoint("LEFT", anchorTexture, "RIGHT", 0, 0)
    overlay:SetPoint("RIGHT", bar, "RIGHT", 0, 0)
    overlay:SetStatusBarTexture(FLAT_TEXTURE)
    overlay:SetStatusBarColor(color[1], color[2], color[3], color[4])
    overlay:SetMinMaxValues(0, 1)
    overlay:SetValue(0)
    overlay:SetFrameLevel(bar:GetFrameLevel() + 1)
    return overlay
end

-- Builds bar.healOverlay (with .glow) and bar.absorbOverlay on the HP rail,
-- chained health fill -> heal -> absorb. Each is skipped when its API is
-- missing; the absorb then anchors straight to the health fill.
local function CreateHealthOverlays(bar)
    local tail = bar:GetStatusBarTexture()
    if HAS.INCOMING_HEALS then
        local heal = CreateOverlayBar(bar, COLOR_HEAL_OVERLAY, tail)
        -- Small ADD glow on the heal segment's trailing edge, anchored to its
        -- own fill's RIGHT edge (a live engine anchor, no arithmetic). Shown
        -- only while a non-secret incoming > 0 (see UpdateRowOverlays), else
        -- at zero width it would sit as a smudge on the HP tip.
        local glow = heal:CreateTexture(nil, "OVERLAY")
        glow:SetTexture(FLAT_TEXTURE)
        glow:SetBlendMode("ADD")
        glow:SetSize(HEAL_GLOW_WIDTH, bar:GetHeight())
        glow:SetPoint("CENTER", heal:GetStatusBarTexture(), "RIGHT", 0, 0)
        glow:SetVertexColor(COLOR_HEAL[1], COLOR_HEAL[2], COLOR_HEAL[3], HEAL_GLOW_ALPHA)
        glow:Hide()
        heal.glow = glow
        bar.healOverlay = heal
        tail = heal:GetStatusBarTexture()
    end
    if HAS.TOTAL_ABSORBS then
        local absorb = CreateOverlayBar(bar, COLOR_ABSORB_OVERLAY, tail)
        -- Hatched stripes, same tiling idiom as UnitFrames.lua's absorb overlay.
        local tex = absorb:GetStatusBarTexture()
        tex:SetTexture(HATCH_TEXTURE, "REPEAT", "REPEAT")
        tex:SetHorizTile(true)
        tex:SetVertTile(true)
        bar.absorbOverlay = absorb
    end
end

-- The Box-matched box behind a member row's rails (mockup pRowBack 'bx'): a cut rectangle BOX_TOP
-- below the row top, the row's full width, down to the row bottom. Two frames, both children of
-- `visual` (so range dimming reaches them) and both BELOW the rails, bloom, spark, text and
-- header, which are all at visual + 1 or higher:
--   frame.box     the fill + a hidden dash host for dead/ghost/offline rows. Two levels under
--                 `visual`.
--   box.edge      the live edge (cyan ring and glow; ApplyBoxEdge retints it), its OWN frame on
--                 the same rect, one level above the fill. It is its own frame so the low-HP
--                 curve can drive FRAME alpha (frame.lowHealthBase): a SetAlpha on the ring or
--                 glow texture itself replaces the glow's BOX_GLOW_ALPHA with the curve's 1
--                 (the 2026-10-03 "double border", a full strength second line inside the
--                 glow), while a frame's alpha multiplies it.
--   frame.boxRed  the low-HP edge: a red ring and glow on the same rect, one level above the
--                 base edge, shown by alpha only (UpdateRowLowHealth). The same driver fades
--                 the base edge out as red comes in, so a low row's edge is red only; the box
--                 fill is never touched.
-- Nothing here moves a rail: the box is anchored to the row, not to the rails.
local function BuildRowBox(f, visual)
    local function seat(frame)
        frame:SetPoint("TOPLEFT", visual, "TOPLEFT", 0, -BOX_TOP)
        frame:SetPoint("TOPRIGHT", visual, "TOPRIGHT", 0, -BOX_TOP)
        frame:SetHeight(BOX_HEIGHT)
    end

    local box = CreateFrame("Frame", nil, visual)
    seat(box)
    box:SetFrameLevel(math.max(visual:GetFrameLevel() - 2, 0))
    AddRoundedFill(box, BOX_FILL, BOX_CHAMFER)
    local edge = CreateFrame("Frame", nil, visual)
    seat(edge)
    edge:SetFrameLevel(box:GetFrameLevel() + 1)
    SkinButton(edge, { chamfer = BOX_CHAMFER, glowAlpha = BOX_GLOW_ALPHA, borderColor = COLOR_POWER })
    box.edge = edge
    local dashHost = CreateFrame("Frame", nil, box)
    dashHost:SetAllPoints(box)
    dashHost:Hide()
    box.dashHost = dashHost
    box.dashes = BuildDashEdge(dashHost, MEMBER_WIDTH, BOX_HEIGHT, BOX_CHAMFER, BOX_DASH_SIZE, BOX_DASH_GAP)

    local red = CreateFrame("Frame", nil, visual)
    seat(red)
    red:SetFrameLevel(visual:GetFrameLevel())
    SkinButton(red, { chamfer = BOX_CHAMFER, glowAlpha = BOX_GLOW_ALPHA, borderColor = COLOR_RED })
    red.fsSkin.border.ring:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], 1)
    red.fsSkin.glow:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], BOX_GLOW_ALPHA)
    red:SetAlpha(0)

    f.box, f.boxRed = box, red
    -- Everything whose alpha the low-HP curve drives; BuildRowHeader appends the LOW tag.
    f.lowHealthTargets = { red }
    f.lowHealthBase = { edge }
    ApplyBoxEdge(f)
end

-- The Box-matched header of one member row, built on `nameRow` (mockup pClassTile / pRoleTag /
-- pHead 'bx'): class plate, role tag, name, "LV n" text and the LOW tag. Cut plates are a frame
-- with Theme.AddRoundedFill + Theme.SkinButton at the chosen chamfer (the same recipe as the row
-- box); the pieces are non-secure children, so showing and hiding them is safe in combat.
local function BuildCutPlate(parent, w, h, chamfer, fill, strokeColor, strokeAlpha)
    local plate = CreateFrame("Frame", nil, parent)
    plate:SetSize(w, h)
    AddRoundedFill(plate, fill, chamfer)
    SkinButton(plate, { chamfer = chamfer, borderColor = strokeColor })
    plate.fsSkin.border.ring:SetVertexColor(strokeColor[1], strokeColor[2], strokeColor[3], strokeAlpha)
    return plate
end

-- Seats the LOW tag at the header's right edge: 2 below the row top, its right edge LOW_GAP left of
-- the rail edge + 1, and a further LEVEL_RESERVE left while the "LV n" text shows (mockup pHead:
-- xr + 1 - tw - 2, tw = 36 with a level, 0 without). A plain frame, so a re-seat is safe in combat.
local function SeatLowTag(nameRow, lowTag, levelShown)
    local H = HEADER
    lowTag:SetPoint("TOPRIGHT", nameRow, "TOPRIGHT",
        H.RIGHT_EDGE - H.LOW_GAP - (levelShown and H.LEVEL_RESERVE or 0), -H.TAG_TOP)
end

local function BuildRowHeader(f, nameRow)
    local H = HEADER

    -- Class plate: dark cut plate with a cyan stroke (Box-matched strokes the tile cyan, not class
    -- colour), the real class icon inset so its square corners clear the chamfer. The icon is a
    -- texture ON the plate: a child frame draws over its parent's regions, so an icon on nameRow
    -- would sit under the plate's fill.
    local plate = BuildCutPlate(nameRow, H.TILE, H.TILE, H.TILE_CHAMFER, H.TILE_FILL, COLOR_POWER,
        H.TILE_STROKE_ALPHA)
    plate:SetPoint("TOPLEFT", nameRow, "TOPLEFT", 0, 0)
    plate.fsSkin.glow:Hide() -- the mockup strokes the tile with no glow
    local classIcon = plate:CreateTexture(nil, "ARTWORK")
    classIcon:SetTexture(CLASS_ICON_ATLAS)
    plate.icon = classIcon
    FS.FrameHelpers.SeatCutIcon(plate)
    classIcon:Hide()

    -- Role tag: cut tag holding the T/H/D letter; stroke and letter take the role colour in
    -- UpdateRowRole. Hidden with no assigned role. The name does not move for it.
    local roleTag = BuildCutPlate(nameRow, H.TAG_W, H.TAG_H, H.TAG_CHAMFER, H.TAG_FILL, COLOR_BORDER,
        H.TAG_STROKE_ALPHA)
    roleTag:SetPoint("TOPLEFT", nameRow, "TOPLEFT", H.TILE + H.TAG_GAP, -H.TAG_TOP)
    roleTag.fsSkin.glow:Hide()
    local roleLetter = roleTag:CreateFontString(nil, "OVERLAY")
    ApplyMono(roleLetter, 8.5, COLOR_BORDER)
    roleLetter:SetPoint("CENTER", roleTag, "CENTER", 0, 0)
    roleTag:Hide()

    -- "LV n", right-aligned past the rail's right edge; UpdateRowLevel shows it below max level.
    local levelText = nameRow:CreateFontString(nil, "OVERLAY")
    ApplyMono(levelText, 8.5, { COLOR_MUTED[1], COLOR_MUTED[2], COLOR_MUTED[3], 0.9 })
    levelText:SetPoint("RIGHT", nameRow, "RIGHT", H.RIGHT_EDGE, 0)
    levelText:SetJustifyH("RIGHT")
    levelText:Hide()

    -- LOW tag: red-stroked cut tag with a small red glow, revealed by ALPHA only (the low-HP
    -- driver, see UpdateRowLowHealth) so no Show/Hide ever depends on secret health. Seated by
    -- UpdateRowLevel, which knows whether the level text takes room at the right edge.
    local lowTag = BuildCutPlate(nameRow, H.LOW_W, H.TAG_H, H.TAG_CHAMFER, H.TAG_FILL, COLOR_RED, 1)
    lowTag.fsSkin.glow:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], BOX_GLOW_ALPHA)
    local lowText = lowTag:CreateFontString(nil, "OVERLAY")
    ApplyMono(lowText, 8, COLOR_RED)
    lowText:SetPoint("CENTER", lowTag, "CENTER", 0, 0)
    lowText:SetText("LOW")
    SeatLowTag(nameRow, lowTag, false)
    lowTag:SetAlpha(0)
    f.lowHealthTargets[#f.lowHealthTargets + 1] = lowTag

    -- Name: mono, class colour (UpdateRowClassColor), one line. Its right edge is anchored 3 left
    -- of the LOW tag. FontStrings have no ellipsis and overflow rather than truncate, so how an
    -- overlong name behaves here is unverified in game (it may spill toward the LV text).
    local name = nameRow:CreateFontString(nil, "OVERLAY")
    ApplyMono(name, 10.5, COLOR_BORDER)
    name:SetPoint("LEFT", nameRow, "LEFT", H.TILE + H.TAG_GAP + H.TAG_W + H.NAME_GAP, 0)
    name:SetPoint("RIGHT", lowTag, "LEFT", -H.NAME_GAP, 0)
    name:SetJustifyH("LEFT")
    -- Same fix as UnitFrames.lua's name FontString: a space-separated name
    -- otherwise wraps at the space onto a second line hidden below this
    -- narrow row.
    name:SetWordWrap(false)
    if name.SetNonSpaceWrap then name:SetNonSpaceWrap(false) end
    if name.SetMaxLines then name:SetMaxLines(1) end
    name:SetJustifyV("MIDDLE")

    f.nameRow = nameRow
    f.classPlate, f.classIcon = plate, classIcon
    f.roleTag, f.roleLetter = roleTag, roleLetter
    f.name, f.levelText = name, levelText
    f.lowTag, f.lowText = lowTag, lowText
end

-- One member row: secure click surface (attributes set explicitly, mirroring
-- UnitFrames.lua rather than relying on SecureUnitButton_OnLoad) plus a
-- non-secure `visual` child holding the name row (class plate, role tag, name,
-- LV text, LOW tag) and the health/power bars.
local function BuildPartyRow(unit, frameName, parent)
    local f = CreateFrame("Button", frameName, parent, "SecureUnitButtonTemplate")
    f:SetSize(MEMBER_WIDTH, ROW_HEIGHT)
    f:RegisterForClicks("AnyUp")
    f:SetAttribute("unit", unit)
    f:SetAttribute("*type1", "target")
    f:SetAttribute("*type2", "togglemenu")
    f.unit = unit

    local visual = CreateFrame("Frame", nil, f)
    visual:SetPoint("TOPLEFT", f, "TOPLEFT")
    visual:SetPoint("TOPRIGHT", f, "TOPRIGHT")
    visual:SetHeight(ROW_HEIGHT)
    f.visual = visual

    BuildRowBox(f, visual)

    local nameRow = CreateFrame("Frame", nil, visual)
    nameRow:SetPoint("TOPLEFT", visual, "TOPLEFT", PAD_X, 0)
    nameRow:SetPoint("TOPRIGHT", visual, "TOPRIGHT", -PAD_X, 0)
    nameRow:SetHeight(NAME_ROW_HEIGHT)

    BuildRowHeader(f, nameRow)

    local health = CreateLaserRail(visual, RAIL_HEALTH_SPEC)
    -- FULL WIDTH, 2026-09-21. This used to inset by MAINT_COLUMN_WIDTH on the
    -- left and DEBUFF_COLUMN_WIDTH on the right to give the aura icons their
    -- own columns, which left a 69px health bar in a 162px row with dead space
    -- either side. The mock has no side columns at all: `.php` is `flex:2.4`
    -- spanning the whole of `.pmain`, with the role chip ABOVE it in the name
    -- row. Parker on seeing the columns: "the hp bar is like 100px wide with a
    -- ton of empty space on either side ... the original mock was how i wanted
    -- it to look". (The icons briefly overlaid the bar's ends after this; see
    -- the ALERTS LIVE OUTSIDE THE PANEL note near ALERT_ICON_SIZE above for
    -- why that was superseded the same day.)
    health.shell:SetPoint("TOPLEFT", nameRow, "BOTTOMLEFT", 0, -RAIL_PAIR_TOP)
    health.shell:SetPoint("TOPRIGHT", nameRow, "BOTTOMRIGHT", 0, -RAIL_PAIR_TOP)
    CreateHealthOverlays(health)
    f.health = health

    -- The alert tray. Built here, ANCHORED in Init off the container's own
    -- outer edge (see Init for the full anchoring rationale). Parented to
    -- `visual` so it inherits the row's out-of-range dimming along with
    -- everything else.
    --
    -- One pool serves both alert kinds. They compete for the same few slots by
    -- urgency rather than each owning reserved space, because a row with two
    -- cleansable debuffs and a missing buff should show the debuffs.
    local alertIcons = {}
    for i = 1, MAX_ALERT_ICONS do
        local icon = CreateAlertIcon(visual)
        icon:SetFrameLevel(health:GetFrameLevel() + 1)
        alertIcons[i] = icon
    end
    f.alertIcons = alertIcons

    -- The laser rail runs the full width of health.shell, no inset.
    local power = CreateLaserRail(visual, RAIL_POWER_SPEC)
    power.shell:SetPoint("TOPLEFT", health.shell, "BOTTOMLEFT", 0, -RAIL_PAIR_GAP)
    power.shell:SetPoint("TOPRIGHT", health.shell, "BOTTOMRIGHT", 0, -RAIL_PAIR_GAP)
    f.power = power

    -- The halo wraps the pair, so it can only be built once both rails exist.
    -- It lives on the health rail's fsRail, where TintHealthDispel reads it.
    health.fsRail.halo = CreateDispelHalo(health, power)

    return f
end

-------------------------------------------------------------------------------
-- Update logic
-------------------------------------------------------------------------------

-- offline, deadOrGhost for `unit`: the two states that replace the health
-- rail's live treatment. Shared by UpdateRowClassColor and UpdateRowHealth so
-- both agree on when the rail is live.
local function RowDownState(unit)
    local offline = HAS.UNIT_IS_CONNECTED and not UnitIsConnected(unit)
    local deadOrGhost = not offline and HAS.UNIT_IS_DEAD_OR_GHOST and UnitIsDeadOrGhost(unit)
    return offline, deadOrGhost
end

-- Max health for the rail, clamped like the health fill: a secret max cannot
-- be compared, the engine handles the degenerate case itself.
local function ReadHealthMax(unit)
    local max = UnitHealthMax(unit)
    if not IsSecret(max) and max == nil then max = 0 end
    if not IsSecret(max) and max <= 0 then max = 1 end
    return max
end

-- Zeroes both HP rail overlays (dead/offline rows: the bar is emptied, so a
-- heal or shield segment would otherwise float at its left edge).
local function ClearRowOverlays(bar)
    local heal, absorb = bar.healOverlay, bar.absorbOverlay
    if heal then
        heal:SetMinMaxValues(0, 1)
        heal:SetValue(0)
        heal.glow:Hide()
    end
    if absorb then
        absorb:SetMinMaxValues(0, 1)
        absorb:SetValue(0)
    end
end

-- Drives both overlays through whitelisted engine setters only: `max` and the
-- incoming/absorb amounts are secret on every unit but "player", so they go
-- straight to SetMinMaxValues/SetValue with no comparison or arithmetic (do not
-- add an IsSecret -> hide guard here, it would blank the overlay on exactly the
-- party members). `not incoming` is a legal truth-test of a secret number (nil
-- -> false, any number -> true), not a `<= 0` compare; a failed pcall or nil
-- read just means nothing incoming.
local function UpdateRowOverlays(frame, max)
    local bar = frame.health
    local heal, absorb = bar.healOverlay, bar.absorbOverlay
    if heal then
        local ok, incoming = pcall(UnitGetIncomingHeals, frame.unit)
        if not ok or not incoming then incoming = 0 end
        heal:SetMinMaxValues(0, max)
        heal:SetValue(incoming)
        -- IsSecret first, so the `> 0` compare is never reached for a secret;
        -- the glow just stays hidden on those units.
        heal.glow:SetShown(not IsSecret(incoming) and incoming > 0)
    end
    if absorb then
        local ok, total = pcall(UnitGetTotalAbsorbs, frame.unit)
        if not ok or not total then total = 0 end
        absorb:SetMinMaxValues(0, max)
        absorb:SetValue(total)
    end
end

-- Cheap path for UNIT_HEAL_PREDICTION / UNIT_ABSORB_AMOUNT_CHANGED: refresh the
-- overlays only, leaving the rest of the row alone. A down row stays zeroed.
local function UpdateRowPrediction(frame)
    local offline, deadOrGhost = RowDownState(frame.unit)
    if offline or deadOrGhost then
        ClearRowOverlays(frame.health)
        return
    end
    UpdateRowOverlays(frame, ReadHealthMax(frame.unit))
end

-- LOW HP. Party health is SECRET in combat, so Lua never computes cur/max for this: a Step curve
-- (alpha 1 from 0 up to LOW_HP_FRACTION, 0 above) is evaluated engine-side by UnitHealthPercent
-- and its result goes straight to SetAlpha on every frame in `frame.lowHealthTargets` (the red
-- edge layer and the header's LOW tag). The inverse Step curve (0 up to the threshold, 1 above)
-- drives `frame.lowHealthBase` (the base edge FRAME, so the cyan or dispel edge does not glow under the red; a
-- frame, not its textures, so the glow keeps its own alpha); a second UnitHealthPercent call, since a secret
-- alpha cannot be inverted in Lua. Down rows: targets 0, base 1. Same pattern as FrameHelpers.UpdateCaretFull:
-- both calls pcall'd, `type()` rather than a truth-test on the possibly-secret result, and the first failure
-- latches (logged once under its own boolean, since LogDegradeOnce does not dedupe) so every later call takes
-- the fallback. SetAlpha accepting a secret is UNVERIFIED in game on 16001. Fallback, with no curve API or
-- after the latch: a plain cur/max compare, legal only when neither value is secret; a secret leaves the
-- targets hidden.
-- File scope is at Lua 5.1's 200 local limit, so the curve state lives in a do block and only
-- the driver escapes.
local UpdateRowLowHealth
do
    local HAS_STEP_CURVE_API = type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
        and type(Enum) == "table" and type(Enum.LuaCurveType) == "table"
        and Enum.LuaCurveType.Step ~= nil

    local function BuildLowHealthCurve()
        local curve = C_CurveUtil.CreateCurve()
        curve:SetType(Enum.LuaCurveType.Step)
        curve:AddPoint(0, 1)
        curve:AddPoint(LOW_HP_FRACTION + LOW_HP_EPSILON, 0)
        return curve
    end

    -- The inverse: 0 at or below the threshold, 1 above. Drives the base edge layer.
    local function BuildBaseHealthCurve()
        local curve = C_CurveUtil.CreateCurve()
        curve:SetType(Enum.LuaCurveType.Step)
        curve:AddPoint(0, 0)
        curve:AddPoint(LOW_HP_FRACTION + LOW_HP_EPSILON, 1)
        return curve
    end

    local LOW_HEALTH_CURVE, BASE_HEALTH_CURVE
    if HAS.UNIT_HEALTH_PERCENT and HAS_STEP_CURVE_API then
        local ok, curve = pcall(BuildLowHealthCurve)
        local okBase, baseCurve = pcall(BuildBaseHealthCurve)
        if ok and okBase then
            LOW_HEALTH_CURVE, BASE_HEALTH_CURVE = curve, baseCurve
        else
            ReportOnce("low health curve", ok and baseCurve or curve)
        end
    end

    local lowHealthBroken = false
    local warnedLowHealth = false

    local function SetAlphaAll(targets, alpha)
        for _, target in ipairs(targets) do
            if not pcall(target.SetAlpha, target, alpha) then return false end
        end
        return true
    end

    -- `alpha` drives the low-HP targets (red layer, LOW tag), `baseAlpha` the base edge layer.
    local function SetLowHealthAlpha(frame, alpha, baseAlpha)
        local ok = SetAlphaAll(frame.lowHealthTargets, alpha)
        return SetAlphaAll(frame.lowHealthBase, baseAlpha) and ok
    end

    -- `down` (dead, ghost, offline) hides every low-HP target and keeps the base edge (the steel
    -- dashes' host row) at 1, without reading health at all.
    function UpdateRowLowHealth(frame, down)
        if down then
            SetLowHealthAlpha(frame, 0, 1)
            return
        end
        local unit = frame.unit
        if LOW_HEALTH_CURVE and not lowHealthBroken then
            local ok, alpha = pcall(UnitHealthPercent, unit, false, LOW_HEALTH_CURVE)
            local okBase, baseAlpha = pcall(UnitHealthPercent, unit, false, BASE_HEALTH_CURVE)
            if ok and okBase and type(alpha) == "number" and type(baseAlpha) == "number"
                and SetLowHealthAlpha(frame, alpha, baseAlpha) then return end
            lowHealthBroken = true
            if not warnedLowHealth then
                warnedLowHealth = true
                FS.LogDegradeOnce("partyframes_lowhp_curve",
                    "|cffff4488Forever STUwave|r: party low-HP curve refused, falling back to a plain compare")
            end
        end
        local cur, max = UnitHealth(unit), UnitHealthMax(unit)
        local low = false  -- unknown (secret) health: red stays 0 and the base edge stays 1
        if not IsSecret(cur) and not IsSecret(max) and type(cur) == "number" and type(max) == "number"
            and max > 0 then
            low = cur / max <= LOW_HP_FRACTION
        end
        SetLowHealthAlpha(frame, low and 1 or 0, low and 0 or 1)
    end
end

local function UpdateRowHealth(frame)
    local unit = frame.unit
    local bar = frame.health

    -- Dead/ghost/offline: replace the numeric reading entirely instead of
    -- letting a corpse's low-but-nonzero health read as "critically low" or
    -- an offline member's stale cached health read as current. Both
    -- predicates are PLAIN per the secret-value audit (neither is on the
    -- health/power/absorbs/range secret list), so they are truth-tested
    -- directly; only their presence on this client is feature-detected.
    -- The rail color is applied here in both states: grey when down, the
    -- class color UpdateRowClassColor stored on the frame when live. That
    -- color is applied only once per state change (see SetLaserRailColor).
    local offline, deadOrGhost = RowDownState(unit)

    if offline or deadOrGhost then
        bar:SetMinMaxValues(0, 1)
        bar:SetValue(0)
        ClearRowOverlays(bar)
        SetLaserRailDesaturated(bar, true)
        SetLaserRailColor(bar, STATE_BAR_COLOR[1], STATE_BAR_COLOR[2], STATE_BAR_COLOR[3])
        bar.text:SetTextColor(1, 1, 1, 1)
        if offline then
            bar.text:SetText(STATE_OFFLINE_TEXT)
        elseif HAS.UNIT_IS_GHOST and UnitIsGhost(unit) then
            bar.text:SetText(STATE_GHOST_TEXT)
        else
            bar.text:SetText(STATE_DEAD_TEXT)
        end
        bar.text:Show()
        frame.name:SetAlpha(STATE_ROW_ALPHA)
        bar.shell:SetAlpha(STATE_ROW_ALPHA)
        frame.power.shell:SetAlpha(STATE_ROW_ALPHA)
        frame.classPlate:SetAlpha(STATE_ROW_ALPHA)
        frame.roleTag:SetAlpha(STATE_ROW_ALPHA)
        frame.levelText:SetAlpha(STATE_ROW_ALPHA)
        -- Bloom and spark would sit as a stray dot at the left of the
        -- emptied rail; the live path below re-shows them.
        bar.fsRail.host:SetShown(false)
        frame.rowDown = true
        ApplyBoxEdge(frame)
        UpdateRowLowHealth(frame, true)
        return
    end

    -- Clear any state treatment left over from a prior dead/offline pass
    -- before showing a live reading.
    SetLaserRailDesaturated(bar, false)
    local railColor = frame.classRailColor or COLOR_HEALTH
    SetLaserRailColor(bar, railColor[1], railColor[2], railColor[3])
    bar.fsRail.host:SetShown(true)
    frame.name:SetAlpha(1)
    bar.shell:SetAlpha(1)
    frame.power.shell:SetAlpha(1)
    frame.classPlate:SetAlpha(1)
    frame.roleTag:SetAlpha(1)
    frame.levelText:SetAlpha(1)
    frame.rowDown = false
    ApplyBoxEdge(frame)

    local cur = UnitHealth(unit)
    if not IsSecret(cur) and cur == nil then cur = 0 end
    local max = ReadHealthMax(unit)

    bar:SetMinMaxValues(0, max)
    bar:SetValue(cur)
    UpdateRowOverlays(frame, max)
    UpdateHealthPercentText(bar.text, unit, cur, max)
    UpdateRowLowHealth(frame, false)
end

local function UpdateRowPower(frame)
    local unit = frame.unit
    local max = UnitPowerMax(unit) or 0
    -- Secret max cannot be compared at all. Showing unconditionally rendered an
    -- empty "0 / 0" bar on manaless NPCs, so fall back to a plain signal:
    -- real players always have a power bar, NPCs often do not.
    local show
    if IsSecret(max) then
        show = UnitIsPlayer(unit) and true or false
    else
        show = max > 0
    end
    frame.power.shell:SetShown(show)
    if not show then return end

    local cur = UnitPower(unit) or 0
    -- Secret max (any unit but "player") cannot be compared; the engine
    -- handles the degenerate case itself, so only clamp when we may look.
    if not IsSecret(max) and max <= 0 then max = 1 end

    local bar = frame.power
    bar:SetMinMaxValues(0, max)
    bar:SetValue(cur)
    -- Bloom and spark would sit as a stray dot at the left of an empty rail.
    FS.FrameHelpers.UpdatePowerHostEmpty(bar.fsRail.host, unit)

    local powerType = UnitPowerType(unit)
    local color = POWER_COLORS[powerType] or COLOR_POWER
    SetLaserRailColor(bar, color[1], color[2], color[3])
end

-- A secret name (12.0) is returned as is: it cannot be trimmed, compared or measured, only handed
-- to SetText.
local function GetFullUnitName(unit)
    local full
    if HAS.GET_UNIT_NAME then
        full = GetUnitName(unit, true)
        if IsSecret(full) then return full end
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

-- Upper-cased only when the name is a plain string (the mockup's .toUpperCase()); a secret name
-- goes to SetText untouched.
local function UpdateRowName(frame)
    local full = GetFullUnitName(frame.unit)
    if not IsSecret(full) and type(full) == "string" then full = full:upper() end
    frame.name:SetText(full)
end

-- "LV n" below MAX_PLAYER_LEVEL, hidden at it (a max level party is the common case and the text
-- would just be noise). The LOW tag's seat depends on whether the text takes room, so re-seat it.
local function UpdateRowLevel(frame)
    local lvl = UnitLevel(frame.unit)
    local show = (lvl and lvl > 0 and lvl ~= MAX_PLAYER_LEVEL) and true or false
    frame.levelText:SetShown(show)
    if show then frame.levelText:SetText("LV " .. lvl) end
    SeatLowTag(frame.nameRow, frame.lowTag, show)
end

-- Resolves the unit's class color (player row included) and stores it on
-- `frame.classRailColor` for UpdateRowHealth's live path; applies it to the
-- rail through SetLaserRailColor (core gradient, track, bloom and spark all
-- follow) only while the unit is live, so a dead/offline rail is tinted once,
-- grey, by UpdateRowHealth instead of flip-flopping through the class color.
-- Falls back to the flat COLOR_HEALTH when the class lookup is unavailable or
-- misses -- pets never call this (kept at COLOR_HEALTH in BuildPetSlot).
local function UpdateRowClassColor(frame)
    local classFile = select(2, UnitClass(frame.unit))
    local coords = HAS.CLASS_ICON_TCOORDS and classFile and CLASS_ICON_TCOORDS[classFile]
    if coords then
        frame.classIcon:SetTexCoord(unpack(coords))
        frame.classIcon:Show()
    else
        frame.classIcon:Hide()
    end
    local classColor = HAS.RAID_CLASS_COLORS and classFile and RAID_CLASS_COLORS[classFile]
    local color = classColor and { classColor.r, classColor.g, classColor.b, 1 } or COLOR_HEALTH
    frame.classRailColor = color
    frame.name:SetTextColor(color[1], color[2], color[3], HEADER.NAME_ALPHA)
    local offline, deadOrGhost = RowDownState(frame.unit)
    if not (offline or deadOrGhost) then
        SetLaserRailColor(frame.health, color[1], color[2], color[3])
    end
end

-- The role tag: stroke and letter in the role colour, hidden with no assigned role.
local function UpdateRowRole(frame)
    local role = HAS.ROLE_API and UnitGroupRolesAssigned(frame.unit) or nil
    local style = role and ROLE_STYLE[role]
    if not style then
        frame.roleTag:Hide()
        return
    end
    local color = style[2]
    frame.roleLetter:SetText(style[1])
    frame.roleLetter:SetTextColor(color[1], color[2], color[3], 1)
    frame.roleTag.fsSkin.border.ring:SetVertexColor(color[1], color[2], color[3], HEADER.TAG_STROKE_ALPHA)
    frame.roleTag:Show()
end

local function UpdateRowPet(frame)
    local pet = frame.petFrame
    if not pet then return end
    pet:ApplyTargetEdge()
    -- The secure unit watch already hides the whole column without a pet; the label also
    -- follows the plain existence read so it can never show over an empty slot.
    local exists = UnitExists(pet.unit)
    pet.petLabel:SetShown(exists and true or false)
    if not exists then
        pet.health:SetValue(0)
        return
    end

    local cur = UnitHealth(pet.unit)
    local max = UnitHealthMax(pet.unit)
    if not IsSecret(cur) and cur == nil then cur = 0 end
    if not IsSecret(max) and max == nil then max = 0 end
    -- Secret max (any unit but "player") cannot be compared; the engine
    -- handles the degenerate case itself, so only clamp when we may look.
    if not IsSecret(max) and max <= 0 then max = 1 end
    pet.health:SetMinMaxValues(0, max)
    pet.health:SetValue(cur)
end

-- Builds this row's alert list, most urgent first, and paints it into the
-- tray outside the panel. One pass for both alert kinds, because they share
-- the slots: a row with two cleansable debuffs AND a missing buff should show
-- the debuffs, and that decision cannot be made by two functions that do not
-- know about each other.
--
-- Only called (via UpdateAuras) once the unit is confirmed to exist.
local function UpdateRowAlerts(frame)
    local unit = frame.unit

    -- Aura reads are refused under combat lockdown, and each refusal costs a
    -- long error string; five rows on a ticker was the bulk of the memory
    -- Parker watched climb. Hold whatever is already on the row instead.
    if not FS.AurasReadable() then return end

    local cleansable = ScanDebuffs(unit)

    -- The health rail's dispel halo carries the dispel colour: that is the
    -- at-a-glance signal, and it reads from across the screen where a 22px
    -- icon does not.
    if #cleansable > 0 then
        SetRowDispel(frame, GetDispelColor(cleansable[1].dispelType) or COLOR_CLEANSABLE_UNKNOWN)
    else
        SetRowDispel(frame, nil)
    end

    local alerts = {}

    -- 1. Cleansable debuffs. CLEANSABLE ONLY: this used to fall back to the
    -- first plain HARMFUL debuff when nothing was cleansable, which is worse
    -- than blank because it pulls a healer's eye to something he cannot act
    -- on. General debuff awareness, if wanted, needs its own affordance.
    for i = 1, math.min(#cleansable, MAX_DEBUFF_ICONS) do
        local aura = cleansable[i]
        alerts[#alerts + 1] = {
            texture = aura.icon,
            tint = nil,
            ring = GetDispelColor(aura.dispelType) or COLOR_CLEANSABLE_UNKNOWN,
            ringAlpha = ALERT_RING_ALPHA,
            glowAlpha = ALERT_GLOW_ALPHA,
            unit = unit,
            auraIndex = aura.index,
            filter = aura.filter,
            name = aura.name,
            spellId = aura.spellId,
        }
    end

    -- 2. Party buffs the player can provide, after the debuffs: ONLY a missing one
    -- alerts, shown as the spell's icon in the dim red look inside a red ring. A buff
    -- that is up is never an alert, whatever time it has left, and a class with no
    -- party buff (or a spell not yet learned) never reaches here. A dead, ghost
    -- or offline member cannot be buffed, so it is skipped before any aura read.
    local offline, deadOrGhost = RowDownState(unit)
    local buffs, buffCount = nil, 0
    if not offline and not deadOrGhost then buffs, buffCount = EvaluatePartyBuffs(unit) end
    for i = 1, buffCount do
        local entry = buffs[i]
        if entry.reason == "missing" then
            alerts[#alerts + 1] = {
                texture = entry.icon,
                tint = MAINT_MISSING_COLOR,
                ring = COLOR_RED,
                ringAlpha = ALERT_RING_ALPHA_MISSING,
                glowAlpha = ALERT_GLOW_ALPHA_MISSING,
                name = entry.buff.spell,
                spellId = entry.state.id,
                missingText = "Missing: " .. entry.buff.spell,
            }
        end
    end

    for i = 1, MAX_ALERT_ICONS do
        local icon = frame.alertIcons[i]
        local alert = alerts[i]
        if alert then
            icon.tex:SetTexture(alert.texture)
            local t = alert.tint
            if t then
                icon.tex:SetVertexColor(t[1], t[2], t[3], t[4] or 1)
            else
                icon.tex:SetVertexColor(1, 1, 1, 1)
            end
            -- The ring and glow are retinted on every paint: the pool hands a tile that
            -- showed a debuff to a missing buff (and back), so a stale colour would stick.
            local skin = icon.fsSkin
            local ring = alert.ring
            if skin and skin.border and skin.border.ring and skin.glow and ring then
                skin.border.ring:SetVertexColor(ring[1], ring[2], ring[3], alert.ringAlpha)
                skin.glow:SetVertexColor(ring[1], ring[2], ring[3], alert.glowAlpha)
            end
            -- A missing buff has no aura to look up (it carries missingText
            -- instead), so reset every tooltip key rather than leaving the
            -- previous alert's behind them.
            icon.unit = alert.unit
            icon.auraIndex = alert.auraIndex
            icon.filter = alert.filter
            -- The spell id and name for the in-combat tooltip; a missing or secret id clears the previous
            -- alert's, so a pooled tile never shows a stale spell.
            SetTipSpell(icon, alert.spellId, alert.name)
            icon.missingText = alert.missingText
            icon:Show()
        else
            icon:Hide()
        end
    end
end

-- Aura step (Parts A/B/C combined), wired into UpdateAll via TryStep;
-- UpdateAll itself is invoked from WireRowEvents' UNIT_AURA (and other)
-- event handlers, not called directly by them. Early-returns on a
-- nonexistent unit (e.g. an empty party slot) instead of scanning auras for it.
local function UpdateAuras(frame)
    if not UnitExists(frame.unit) then
        for _, icon in ipairs(frame.alertIcons) do icon:Hide() end
        SetRowDispel(frame, nil)
        return
    end
    UpdateRowAlerts(frame)
end

-- Out-of-range dimming, checked independently for the member and its pet.
-- Both apply alpha to their non-secure `.visual` child (not the secure
-- button itself) so member name/health/power/role/level fade together and
-- the pet's health bar fades separately. A separate pass from UpdateAll --
-- called by the Init ticker, not a TryStep here.
-- UnitInRange returns a SECRET BOOLEAN to tainted code on this client, and
-- a secret boolean is the one type tainted code may not even truth-test --
-- `inRange and A or B` throws. It fired on the range ticker, so it threw
-- ~1000 times a session. Feature-detect the engine setter that consumes a
-- secret boolean directly; if this build lacks it, leave the row at full
-- alpha (no dimming) rather than throw every tick.
local function ApplyRangeAlpha(region, inRange)
    if IsSecret(inRange) then
        if type(region.SetAlphaFromBoolean) == "function" then
            region:SetAlphaFromBoolean(inRange, RANGE_ALPHA_IN_RANGE, RANGE_ALPHA_OUT_RANGE)
        else
            region:SetAlpha(RANGE_ALPHA_IN_RANGE)
        end
        return
    end
    region:SetAlpha(inRange and RANGE_ALPHA_IN_RANGE or RANGE_ALPHA_OUT_RANGE)
end

local function UpdateRangeFor(frame)
    if not HAS.UNIT_IN_RANGE then return end

    if not UnitExists(frame.unit) then frame.visual:SetAlpha(RANGE_ALPHA_IN_RANGE); return end

    -- UnitInRange is only meaningful for OTHER group members. It returns false
    -- for "player", and false for everyone while ungrouped, which dimmed the
    -- player's own row to 40% permanently once the secret-boolean fix made the
    -- call actually take effect. You are never out of range of yourself.
    if frame.unit == "player" or not IsInGroup() then
        frame.visual:SetAlpha(RANGE_ALPHA_IN_RANGE)
        if frame.petFrame then frame.petFrame.visual:SetAlpha(RANGE_ALPHA_IN_RANGE) end
        return
    end

    ApplyRangeAlpha(frame.visual, UnitInRange(frame.unit))

    local pet = frame.petFrame
    if pet and UnitExists(pet.unit) then
        ApplyRangeAlpha(pet.visual, UnitInRange(pet.unit))
    end
end

local function UpdateAll(frame)
    if not UnitExists(frame.unit) then return end
    -- classColor before health: it stores frame.classRailColor, which
    -- UpdateRowHealth's live path applies.
    TryStep(frame, "classColor", UpdateRowClassColor)
    TryStep(frame, "health", UpdateRowHealth)
    TryStep(frame, "power", UpdateRowPower)
    TryStep(frame, "name", UpdateRowName)
    TryStep(frame, "level", UpdateRowLevel)
    TryStep(frame, "role", UpdateRowRole)
    TryStep(frame, "pet", UpdateRowPet)
    TryStep(frame, "auras", UpdateAuras)
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local SafeRegisterUnitEvent = FS.FrameHelpers.SafeRegisterUnitEvent
-- Same silent swallow the old inline pcall had (an unknown event is just absent).
local function IgnoreRegisterFailure() end

local function WireRowEvents(frame)
    local events = CreateFrame("Frame")
    events:RegisterUnitEvent("UNIT_HEALTH", frame.unit, frame.petFrame and frame.petFrame.unit or nil)
    events:RegisterUnitEvent("UNIT_MAXHEALTH", frame.unit, frame.petFrame and frame.petFrame.unit or nil)
    events:RegisterUnitEvent("UNIT_POWER_UPDATE", frame.unit)
    events:RegisterUnitEvent("UNIT_MAXPOWER", frame.unit)
    events:RegisterUnitEvent("UNIT_DISPLAYPOWER", frame.unit)
    events:RegisterUnitEvent("UNIT_NAME_UPDATE", frame.unit)
    events:RegisterUnitEvent("UNIT_PET", frame.unit)
    events:RegisterUnitEvent("UNIT_AURA", frame.unit)
    -- UNIT_CONNECTION is UNVERIFIED on this interface-16001 client (same
    -- caution as moduleEvents' PLAYER_ROLES_ASSIGNED registration in Init
    -- below); RegisterEvent/RegisterUnitEvent can throw on an unrecognized
    -- name, so it goes through pcall. Drives UpdateRowHealth's offline
    -- treatment on top of the existing health events.
    pcall(events.RegisterUnitEvent, events, "UNIT_CONNECTION", frame.unit)
    -- Drive the HP rail's heal and absorb overlays; same UNVERIFIED/pcall
    -- treatment, and only when the matching read API exists.
    if HAS.INCOMING_HEALS then
        SafeRegisterUnitEvent(events, "UNIT_HEAL_PREDICTION", frame.unit, IgnoreRegisterFailure)
    end
    if HAS.TOTAL_ABSORBS then
        SafeRegisterUnitEvent(events, "UNIT_ABSORB_AMOUNT_CHANGED", frame.unit, IgnoreRegisterFailure)
    end
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    -- Same gap as Buffs.lua, same fix: UpdateRowAlerts bails under lockdown, so
    -- every aura change during a fight is dropped. Without a re-scan when
    -- lockdown lifts, a debuff that outlives the fight leaves the cleanse slot
    -- and the health rail's dispel halo stale until the next aura change.
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:SetScript("OnEvent", function(_, event)
        if event == "UNIT_HEAL_PREDICTION" or event == "UNIT_ABSORB_AMOUNT_CHANGED" then
            if UnitExists(frame.unit) then TryStep(frame, "prediction", UpdateRowPrediction) end
            return
        end
        UpdateAll(frame)
        if event == "PLAYER_ENTERING_WORLD" then
            UpdateRangeFor(frame)
        end
    end)
    -- The regen scan above can be refused while the client still says auras are secret; this
    -- runs the same refresh once reads work (the shared retry chain, Theme.lua).
    FS.OnAurasReadable(function() UpdateAll(frame) end)
    frame.events = events
end

-------------------------------------------------------------------------------
-- Init (secure frame creation + SetAttribute + RegisterUnitWatch must run out
-- of combat)
-------------------------------------------------------------------------------

-------------------------------------------------------------------------------
-- Blizzard's own party frames
-------------------------------------------------------------------------------

-- This client (interface 16001, the 12.x engine) has no PartyMemberFrame1..4 or
-- PartyMemberFrameNPetFrame globals: looking those up found nothing and left Blizzard's
-- party frames drawn beside ours (playtest 2026-10-04). The real ones (Blizzard_UnitFrame
-- PartyFrame.lua, PartyMemberFrame.lua, CompactPartyFrame.lua):
--   PartyFrame: the Edit Mode Party system. Its pooled PartyMemberFrameTemplate members
--     (parentKey MemberFrame1..4, each with a PetFrame child) are CHILDREN of it, and a
--     GROUP_ROSTER_UPDATE / PartyFrame OnShow re-acquires them from the pool and re-runs
--     Setup, which re-registers their events.
--   CompactPartyFrame: the "raid-style party frames" variant. Generated on demand by
--     CompactRaidFrameContainer, and PARENTED TO PartyFrame (CompactPartyFrame_Generate; the
--     container's PARTY branch never reparents it). Its member and pet frames are the
--     memberUnitFrames / petUnitFrames lists.
-- Alpha multiplies down the parent chain, so dimming PartyFrame alone hides the member
-- frames, the pet frames, the party background and CompactPartyFrame, including any pool
-- frame or compact frame created later and any alpha Blizzard writes on a child (out-of-range
-- fading). The rest of the sweep is only the events and the mouse, neither of which
-- inherits: each frame is dimmed through DimBlizzardFrame (UnregisterAllEvents, its child
-- bars' events, SetAlpha(0), EnableMouse(false)).
-- Why this adds no taint: it is dim-not-hide on purpose. Nothing here calls Hide, HookScript,
-- SetScript, SetParent or hooksecurefunc, and nothing writes a field on a Blizzard table, so
-- UnitFrame_Update, CompactUnitFrame_UpdateAll and PartyFrame:Layout run exactly as they
-- would unmodified. ElvUI's 12.x path (oUF blizzard.lua handleFrame) Hides and reparents
-- PartyFrame and hooks Show on CompactPartyFrame; that is the Hide-plus-hook combination
-- the CLAUDE.md FrameHelpers entry rules out for Edit Mode systems. The raid frames
-- (CompactRaidFrameContainer, CompactRaidFrameManager) are NOT touched: this addon draws
-- five party rows and no raid frames, so the raid UI stays Blizzard's, and the manager tab
-- carries the raid markers and the ready check.
-- Alpha 0 still hit-tests and the mouse does not inherit, so every mouse-taking descendant is
-- switched off, not only the frames DimBlizzardFrame sweeps (one level of children): the pool
-- member's HealthBarContainer.HealthBar forwards OnMouseUp to the member's Click (an invisible
-- click-to-target), the PartyAuraFrameTemplate buttons under member.AuraFrameContainer and
-- PetFrame.AuraFrameContainer are mouse-enabled with OnEnter tooltips (phantom debuff
-- tooltips over empty screen), and a compact unit frame holds buttons of its own.
local MOUSE_SWEEP_DEPTH = 6

local function DisableMouseTree(frame, depth)
    if frame.EnableMouse then pcall(frame.EnableMouse, frame, false) end
    if depth > 0 and frame.GetChildren then
        for _, child in ipairs({ frame:GetChildren() }) do
            DisableMouseTree(child, depth - 1)
        end
    end
end

-- Aura buttons are made lazily (a pool Acquire after the first aura lands), so the load
-- sweep cannot see them. Only the two aura containers of each pool member are walked here,
-- which keeps the per-UNIT_AURA rerun to a handful of frames.
local function DisablePartyAuraMouse()
    local partyFrame = _G.PartyFrame
    if not partyFrame then return end
    for _, member in ipairs({ partyFrame:GetChildren() }) do
        local pet = member.PetFrame
        if pet then
            for _, container in ipairs({ member.AuraFrameContainer, pet.AuraFrameContainer }) do
                DisableMouseTree(container, 2)
            end
        end
    end
end

local function SilenceBlizzardParty()
    local partyFrame, compact = _G.PartyFrame, _G.CompactPartyFrame
    if not partyFrame and not compact then
        FS.LogDegradeOnce("partyframes_noblizzardparty",
            "ForeverSTUwave: neither PartyFrame nor CompactPartyFrame exists; "
            .. "Blizzard's party frames were not dimmed")
        return
    end
    -- One throwing frame must not abort the ones after it: each step is its own pcall and the
    -- first error is reported once at the end.
    local firstError
    local function Step(fn, ...)
        local ok, err = pcall(fn, ...)
        if not ok and not firstError then firstError = err end
    end
    local function DimUnitFrames(list)
        for _, unitFrame in ipairs(list or {}) do
            Step(DimBlizzardFrame, unitFrame)
        end
    end
    if partyFrame then
        Step(DimBlizzardFrame, partyFrame)
        -- Pool members only: a child that has a PetFrame. The sweep inside DimBlizzardFrame
        -- already switched the mouse off on each member itself (and on its direct children);
        -- this adds the member's events, its bars' events, and the pet button.
        for _, child in ipairs({ partyFrame:GetChildren() }) do
            if child.PetFrame then
                Step(DimBlizzardFrame, child)
                Step(DimBlizzardFrame, child.PetFrame)
            end
        end
        Step(DisableMouseTree, partyFrame, MOUSE_SWEEP_DEPTH)  -- includes CompactPartyFrame under it
    end
    if compact then
        Step(DimBlizzardFrame, compact)
        DimUnitFrames(compact.memberUnitFrames)
        DimUnitFrames(compact.petUnitFrames)
        Step(DisableMouseTree, compact, MOUSE_SWEEP_DEPTH)
    end
    if firstError then error(firstError, 0) end
end

-- Silence now, and again whenever Blizzard may have built or re-armed a party frame: the
-- roster (pool members re-acquired, CompactPartyFrame:RefreshMembers), entering the world
-- (frames created after our Init), an Edit Mode layout change (toggling raid-style party
-- frames generates or re-lays CompactPartyFrame). The rerun is deferred one frame so it
-- lands after Blizzard's own handlers of the same event, and skipped in combat (mouse
-- changes on protected unit buttons are forbidden then) until PLAYER_REGEN_ENABLED. The
-- pool re-uses the same member objects and nothing in Blizzard's party code calls
-- EnableMouse, so a mouse switched off once stays off across a re-acquire; only the events
-- Setup re-registers are live until the combat-pending sweep runs.
local function WatchBlizzardParty()
    local pending, queued, auraQueued = false, false, false
    local function Sweep()
        queued = false
        if InCombatLockdown() then
            pending = true
            return
        end
        pending = false
        local ok, err = pcall(SilenceBlizzardParty)
        if not ok then
            FS.LogDegradeOnce("partyframes_blizzardsweep",
                "ForeverSTUwave: dimming Blizzard's party frames failed: " .. tostring(err))
        end
    end
    local function AuraSweep()
        auraQueued = false
        if InCombatLockdown() then
            pending = true
            return
        end
        pcall(DisablePartyAuraMouse)
    end
    local function After(fn)
        if C_Timer and C_Timer.After then
            C_Timer.After(0, fn)
        else
            fn()
        end
    end
    local watcher = CreateFrame("Frame")
    -- RegisterEvent throws on an unrecognized name; EDIT_MODE_LAYOUTS_UPDATED is not
    -- confirmed on every build.
    for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "GROUP_ROSTER_UPDATE",
                             "EDIT_MODE_LAYOUTS_UPDATED", "PLAYER_REGEN_ENABLED" }) do
        pcall(watcher.RegisterEvent, watcher, event)
    end
    -- UNIT_AURA for the party and party pet units: the cheap trigger for lazily made aura
    -- buttons, coalesced to one sweep per frame.
    pcall(watcher.RegisterUnitEvent, watcher, "UNIT_AURA",
        "party1", "party2", "party3", "party4",
        "partypet1", "partypet2", "partypet3", "partypet4")
    watcher:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_REGEN_ENABLED" then
            if pending then Sweep() end
            return
        end
        if event == "UNIT_AURA" then
            if not auraQueued then
                auraQueued = true
                After(AuraSweep)
            end
            return
        end
        if queued then return end
        queued = true
        After(Sweep)
    end)
    Sweep()
end

local function Init()
    WatchBlizzardParty()

    local container = CreateFrame("Frame", "ForeverSTUwavePartyContainer", UIParent)
    FS.Layout.Apply(container, "party")

    -- WHOLE-PIXEL SEAT (live bug 2026-10-03, the right edge of a row box opened a one pixel gap
    -- between its ring and its glow). The container is 231 design px wide at x = -389 from
    -- UIParent's centre, so on a screen of even pixel width its left edge lands on a half pixel
    -- (5120x1440 with UIParent 1200 tall: 2055.5, and every row edge with it, since each design
    -- size is a whole pixel at 1440 high). The ring and the glow slice then round that half pixel
    -- in different directions. So the left and top edges are snapped to whole PHYSICAL pixels
    -- (the offsets only; the size and the CENTER anchor stay Layout's): one pixel is
    -- PixelUtil's factor (768 / physical height) over UIParent's effective scale. A screen
    -- height that is not 1440 leaves the row widths fractional (a design px is then a fraction
    -- of a pixel); that is not a tie, so the ring and the glow still round together. No
    -- GetPhysicalScreenSize, or a UIParent with no centre yet (load), keeps Layout's own seat; the
    -- rescale callback and the login event come back. The container parents secure buttons, so
    -- it is protected and is only ever re-seated out of combat (PLAYER_REGEN_ENABLED below).
    local function SeatOnWholePixels()
        if InCombatLockdown() then return end
        local entry = FS.Layout.party
        if not entry or entry.point ~= "CENTER" or entry.relPoint ~= "CENTER" then return end
        if type(GetPhysicalScreenSize) ~= "function" then return end
        local _, physH = GetPhysicalScreenSize()
        local uiScale = UIParent:GetEffectiveScale()
        local ux, uy = UIParent:GetCenter()
        if type(physH) ~= "number" or physH <= 0 or type(uiScale) ~= "number" or uiScale <= 0
            or type(ux) ~= "number" or type(uy) ~= "number" then return end
        local factor = 768 / physH
        if type(PixelUtil) == "table" and type(PixelUtil.GetPixelToUIUnitFactor) == "function" then
            factor = PixelUtil.GetPixelToUIUnitFactor()
        end
        local px = factor / uiScale  -- one physical pixel, in UIParent units
        local scale = FS.Layout.Scale()
        local w, h = entry.w * scale, entry.h * scale
        local x, y = entry.x * scale, entry.y * scale
        local left = math.floor((ux + x - w / 2) / px + 0.5) * px
        local top = math.floor((uy + y + h / 2) / px + 0.5) * px
        container:ClearAllPoints()
        container:SetPoint(entry.point, UIParent, entry.relPoint, left + w / 2 - ux, top - h / 2 - uy)
    end
    SeatOnWholePixels()

    -- Keep every child in design units while the outer frame follows Layout.
    local content = CreateFrame("Frame", nil, container)
    content:SetPoint("TOPLEFT", container, "TOPLEFT", 0, 0)
    content:SetSize(CONTAINER_WIDTH, CONTAINER_HEIGHT)
    content:SetScale(FS.Layout.Scale())

    local function RefreshContentScale()
        if InCombatLockdown() then return end
        content:SetScale(FS.Layout.Scale())
        SeatOnWholePixels() -- Layout's watcher has just re-seated the container unsnapped
    end
    FS.Layout.OnRescale(RefreshContentScale)

    -- Reapply on regen even if the shared watcher was blocked before callbacks.
    local rescaleEvents = CreateFrame("Frame")
    rescaleEvents:RegisterEvent("PLAYER_REGEN_ENABLED")
    rescaleEvents:SetScript("OnEvent", function()
        if InCombatLockdown() then return end
        FS.Layout.Apply(container, "party")
        RefreshContentScale() -- re-snaps too
    end)

    -- Box-matched has NO panel-level chrome: no scrim, border or glow around the five rows.
    -- Each member row and pet column carries its own box (BuildRowBox, BuildPetSlot); the
    -- container keeps its size and seat so the layout and the alert tray do not move.

    local rows = {}
    for i, def in ipairs(ROW_DEFS) do
        local rowY = -PANEL_PAD - ((i - 1) * (ROW_HEIGHT + ROW_GAP))

        local member = BuildPartyRow(def.unit, "ForeverSTUwavePartyRow" .. i, content)
        member:SetPoint("TOPLEFT", content, "TOPLEFT", PANEL_PAD, rowY)

        local pet = BuildPetSlot(def.petUnit, "ForeverSTUwavePartyPet" .. i, content, member.visual)
        pet:SetPoint("TOPRIGHT", content, "TOPRIGHT", -PANEL_PAD, rowY)
        member.petFrame = pet

        -- The scaled content edge matches the outer panel, keeping alerts
        -- outside and aligned with their row without changing the footprint.
        local iconY = rowY - ((ROW_HEIGHT - ALERT_ICON_SIZE) / 2)
        for slot, icon in ipairs(member.alertIcons) do
            icon:ClearAllPoints()
            if slot == 1 then
                icon:SetPoint("TOPRIGHT", content, "TOPLEFT", -ALERT_TRAY_INSET, iconY)
            else
                icon:SetPoint("RIGHT", member.alertIcons[slot - 1], "LEFT", -ALERT_GAP, 0)
            end
        end

        if def.unit == "player" then
            member:Show() -- "player" always exists; shown unconditionally, no watch needed
        else
            RegisterUnitWatch(member)
        end
        RegisterUnitWatch(pet)

        WireRowEvents(member)
        rows[i] = member
    end

    FS.partyRows = rows
    FS.partyContainer = container

    -- Roster/role changes affect every row (a party slot's occupant, or any
    -- member's assigned role) rather than a single unit token, so this lives
    -- on one module-level event frame instead of per-row WireRowEvents.
    -- PLAYER_ROLES_ASSIGNED is UNVERIFIED on this interface-16001 client;
    -- RegisterEvent can throw on an unrecognized name, so the registration is
    -- pcall-guarded.
    local moduleEvents = CreateFrame("Frame")
    moduleEvents:RegisterEvent("GROUP_ROSTER_UPDATE")
    moduleEvents:RegisterEvent("PLAYER_TARGET_CHANGED")
    pcall(moduleEvents.RegisterEvent, moduleEvents, "PLAYER_ROLES_ASSIGNED")
    local function ApplyPetTargetEdge(row)
        if row.petFrame then row.petFrame:ApplyTargetEdge() end
    end
    moduleEvents:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_TARGET_CHANGED" then
            -- Only the target purple on the member and pet box edges depends on it; no full repaint.
            for _, row in ipairs(rows) do
                TryStep(row, "target", ApplyBoxEdge)
                TryStep(row, "targetPet", ApplyPetTargetEdge)
            end
            return
        end
        for _, row in ipairs(rows) do
            UpdateAll(row)
            UpdateRangeFor(row)
        end
    end)
    FS.partyEvents = moduleEvents

    -- Whether a buff spell is known, and the dispel set, are cached; a spellbook change
    -- drops both and repaints. Event names are pcall-guarded (UNVERIFIED on this
    -- client, like PLAYER_ROLES_ASSIGNED above).
    if PLAYER_BUFFS or DISPELS.CLASS[PlayerClass()] then
        local spellEvents = CreateFrame("Frame")
        for _, event in ipairs({ "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP",
                                 "CHARACTER_POINTS_CHANGED", "PLAYER_TALENT_UPDATE" }) do
            pcall(spellEvents.RegisterEvent, spellEvents, event)
        end
        spellEvents:SetScript("OnEvent", function()
            ResetBuffSpellCache()
            DISPELS.cache = nil
            for _, row in ipairs(rows) do UpdateAll(row) end
        end)
        FS.partySpellEvents = spellEvents
    end

    for _, row in ipairs(rows) do
        UpdateAll(row)
    end

    -- C_Timer.NewTicker when available, else an OnUpdate accumulator on
    -- the container. Started once here, after the rows exist, rather than
    -- per-row.
    if HAS.UNIT_IN_RANGE then
        local function RefreshRanges()
            for _, row in ipairs(rows) do
                UpdateRangeFor(row)
            end
        end

        if HAS.C_TIMER_TICKER then
            C_Timer.NewTicker(RANGE_TICK_INTERVAL, RefreshRanges)
        else
            local elapsed = 0
            container:SetScript("OnUpdate", function(_, delta)
                elapsed = elapsed + delta
                if elapsed >= RANGE_TICK_INTERVAL then
                    elapsed = 0
                    RefreshRanges()
                end
            end)
        end

        RefreshRanges()
    end
end

-------------------------------------------------------------------------------
-- Diagnostic
-------------------------------------------------------------------------------

-- Both party-frame complaints on 2026-09-21 were about things that LOOK
-- plausible from a screenshot and can only be settled by numbers: a health bar
-- that seemed narrow, and debuff icons that turned out to be uncleansable. So
-- the numbers are one command away rather than a round trip.
SLASH_FSPARTY1 = "/fsparty"

-- /fsparty buffs: every party buff of the player's class with its known/on state.
-- /fsparty buff <key> on|off: persist an override in ForeverSTUwaveDB.partyBuffs.
local function ReportBuffTable()
    if not PLAYER_BUFFS then
        print(("  %s has no party buffs, so the tray shows no buff alerts"):format(tostring(PlayerClass())))
        return
    end
    for _, buff in ipairs(PLAYER_BUFFS) do
        local state = BuffSpellState(buff)
        local saved = SavedBuffValue(buff)
        -- "(default)" only when nothing is saved: an explicit false is the player's choice.
        print(("  %-11s %-24s %-9s %s"):format(buff.key, buff.spell,
            state.known and "known" or "not known",
            BuffEnabled(buff) and "on" or ("off" .. (saved == nil and " (default)" or ""))))
    end
end

local function SetBuffEnabled(key, value)
    for _, buff in ipairs(PLAYER_BUFFS or {}) do
        if buff.key == key then
            ForeverSTUwaveDB = ForeverSTUwaveDB or {}
            ForeverSTUwaveDB.partyBuffs = ForeverSTUwaveDB.partyBuffs or {}
            ForeverSTUwaveDB.partyBuffs[key] = value
            for _, row in ipairs(FS.partyRows or {}) do
                if UnitExists(row.unit) then UpdateRowAlerts(row) end
            end
            print(("  party buff %s (%s): %s"):format(key, buff.spell, value and "on" or "off"))
            return
        end
    end
    print(("  no party buff '%s' for %s; /fsparty buffs lists them"):format(key, tostring(PlayerClass())))
end

SlashCmdList["FSPARTY"] = function(msg)
    local cmd, key, value = tostring(msg or ""):match("^%s*(%S*)%s*(%S*)%s*(%S*)")
    if cmd == "buffs" then
        ReportBuffTable()
        return
    elseif cmd == "buff" then
        if (value == "on" or value == "off") and key ~= "" then
            SetBuffEnabled(key, value == "on")
        else
            print("  usage: /fsparty buff <key> on|off   (/fsparty buffs lists the keys)")
        end
        return
    end

    print(("|cff22e0ffForever STUwave|r party: class %s dispels %s"):format(
        tostring(PlayerClass()),
        DISPELS.Describe(DISPELS.Set())))

    local container = FS.partyContainer
    if container then
        print(("  container %.0fx%.0f   member row %d   pet %d")
            :format(container:GetWidth(), container:GetHeight(), MEMBER_WIDTH, PET_WIDTH))
    end

    for i, frame in ipairs(FS.partyRows or {}) do
        local unit = frame.unit
        local shown = frame:IsShown() and UnitExists(unit)
        if not shown then
            print(("  %d %-8s -- empty"):format(i, unit))
        else
            local hpWidth = frame.health and frame.health.shell
                and frame.health.shell:GetWidth() or -1
            local line = ("  %d %-8s %-12s hp bar %.0fpx"):format(
                i, unit, tostring(UnitName(unit)):sub(1, 12), hpWidth)

            if not FS.AurasReadable() then
                print(line .. "   auras: not readable right now (combat lockdown)")
            else
                local cleansable, harmful = ScanDebuffs(unit)
                print(("%s   %d harmful, %d CLEANSABLE"):format(line, #harmful, #cleansable))
                for _, aura in ipairs(harmful) do
                    local mine = aura.dispelType and DISPELS.Set()[aura.dispelType]
                    print(("      %s %s [%s]"):format(
                        mine and "|cff40bf40CLEANSE|r" or "|cff888888  --   |r",
                        tostring(aura.name),
                        aura.dispelType ~= "" and tostring(aura.dispelType) or "no type"))
                end

                -- Each party buff the player can provide, and WHY it is or is not alerting.
                local buffs, buffCount = EvaluatePartyBuffs(unit)
                for bi = 1, buffCount do
                    local entry = buffs[bi]
                    local spell = entry.buff.spell
                    if entry.reason == "missing" then
                        print(("      |cffff5555MISSING|r  %s [no matching buff from anyone]"):format(spell))
                    elseif entry.reason == "unreadable" then
                        print(("      |cff888888  --   |r %s [aura names are secret or the aura read failed, cannot tell]"):format(spell))
                    else
                        print(("      |cff888888  --   |r %s [%s, up, so no alert]")
                            :format(spell, tostring(entry.aura.name)))
                    end
                end
            end
        end
    end
    print("  -- means deliberately NOT alerted. Alerts show OUTSIDE the panel, to the "
        .. "left of the row: cleansable debuffs first, then party buffs you know that a member lacks. "
        .. "/fsparty buffs lists them; /fsparty buff <key> on|off toggles one.")
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
