-- Forever STUwave: Raid Frames
-- The raid grid: forty of our own SecureUnitButtonTemplate buttons, raid1..raid40, each built once at Init the way
-- PartyFrames.lua builds a row (explicit secure attributes, a non-secure `visual` child for every piece of chrome,
-- RegisterUnitWatch). No SecureGroupHeaderTemplate, no secure snippets and no state driver: the grid is laid out from
-- Lua, and only out of combat. Two looks from the raid frames design study (2026-11-09): A, mini boxes (the party row
-- shrunk to a cell), at ten members or fewer, and C, tiles that fill bottom up, at eleven or more. Each raid subgroup
-- with members is one column, the player's own group first.
-- In a raid the party rows hide and the grid shows; outside a raid the grid hides and the party rows are untouched. The
-- grid is never anchored to the party frames: each raid size (5, 10, 15, 20, 25, 40) has its own layout entry
-- (raid5 .. raid40, Layout.lua) with its own saved seat, and the grid sits at the seat of the smallest size that fits
-- the roster (1 to 5 members use raid5, 6 to 10 raid10, and so on), re-seated out of combat only. While the layout editor
-- is on, a preview grid of plain frames (see "Editor preview" below) shows at the seat of the size the player picked, in
-- every size, so each layout can be placed without a raid. Its own switch, "raid.shown", is apart from the party switch.
-- While it is on, Blizzard's raid frames are dimmed the dim-not-hide way; while it is off they are never touched.
-- Health, power, range and names can be secret here (12.0): every one goes only to engine setters, SetText or
-- SetAlphaFromBoolean, through the same pieces the party rows use (FS.PartyFrames.shared).

local _, FS = ...

local Shared = FS.PartyFrames and FS.PartyFrames.shared
if not Shared then
    FS.LogDegradeOnce("raidframes_noparty",
        "|cffff4488Forever STUwave|r: the party frames did not load, so the raid frames are off")
    return
end

local Theme = FS.Theme
local Style = FS.FrameStyle
local IsSecret = FS.IsSecret
local Extras = FS.FrameExtras
local DimBlizzardFrame = FS.FrameHelpers.DimBlizzardFrame
local CreateLaserRail = FS.FrameHelpers.CreateLaserRail
local SetLaserRailColor = FS.FrameHelpers.SetLaserRailColor
local SetLaserRailDesaturated = FS.FrameHelpers.SetLaserRailDesaturated

local UpdateRowLowHealth = Shared.UpdateRowLowHealth
local UpdateHealthPercentText = Shared.UpdateHealthPercentText
local RowDownState = Shared.RowDownState
local ReadHealthMax = Shared.ReadHealthMax
local ScanDebuffs = Shared.ScanDebuffs
local GetDispelColor = Shared.GetDispelColor
local BuildDashEdge = Shared.BuildDashEdge
local TintDashes = Shared.TintDashes
local ApplyRangeAlpha = Shared.ApplyRangeAlpha
local DisableMouseTree = Shared.DisableMouseTree
local ROLE_STYLE = Shared.ROLE_STYLE
local POWER_COLORS = Shared.POWER_COLORS
local DISPELS = Shared.DISPELS

local COLOR_POWER = Theme.COLOR_POWER    -- the cyan edge
local COLOR_RED = Theme.COLOR_RED        -- the low health edge and percent
local COLOR_STEEL = Theme.COLOR_STEEL    -- dead and offline
local COLOR_HEALTH = Theme.COLOR_HEALTH  -- pink: the own cell tick, the own group label, the class colour fallback
local COLOR_BORDER = Theme.COLOR_BORDER  -- violet: the other group labels
local COLOR_WHITE = { 1, 1, 1, 1 }
local FLAT_TEXTURE = Theme.FLAT_TEXTURE
local STATE_BAR_COLOR = Shared.STATE_BAR_COLOR
local STATE_ALPHA = Shared.STATE_ROW_ALPHA

-------------------------------------------------------------------------------
-- Sizes (the design study's A and C spec objects; design px, the grid's content frame is scaled by Layout)
-------------------------------------------------------------------------------

local RAID_SIZE = 40
local SEAT_SIZES = { 5, 10, 15, 20, 25, 40 }   -- the raid sizes with a layout entry each (raid5 .. raid40) and a preview
local GROUP_COUNT = 8
local GROUP_SIZE = 5
local SMALL_RAID = 10       -- look A at this many members or fewer, look C above
local CHAMFER = 4           -- both looks; the cut ring, fill, erase and dashes all use it
local DASH_SIZE, DASH_GAP = 3, 2
local DASH_ALPHA = 0.7 * STATE_ALPHA  -- the study's .7 stroke, under the down cell's .55
local LABEL_SIZE, LABEL_ALPHA, LABEL_X, LABEL_Y = 8, 0.85, 2, -5
local TICK_WIDTH, TICK_X = 2, -3
local TICK_GLOW_WIDTH, TICK_GLOW_ALPHA = 6, 0.3
local NAME_ALPHA_A = 0.95
local RELOAD_LINE = "Reload to restore the game's raid frames"

-- Edge strength: `ring` and `glow` alphas. A debuff the player can remove lights the edge in its dispel colour at
-- EDGE_LIT; the idle cyan is each look's own (A keeps the party box's full edge with a softer glow, C stays dim with
-- no glow until something needs the player).
local EDGE_LIT = { ring = 1, glow = 0.5 }

-- The near-black cell inks: A rgba(13,6,32,.85), C rgba(6,3,18,.92) drawn at .9.
local LOOKS = {
    A = { w = 84, h = 30, gx = 4, gy = 3, hdr = 12, tickInset = 4,
          fill = { 13 / 255, 6 / 255, 32 / 255, 0.85 }, idle = { ring = 1, glow = 0.35 } },
    C = { w = 58, h = 40, gx = 3, gy = 3, hdr = 12, tickInset = 5,
          fill = { 6 / 255, 3 / 255, 18 / 255, 0.92 * 0.9 }, idle = { ring = 0.55, glow = 0 } },
}

-- The party's laser rail recipe at cell size (the study's rail(): track .18, core .35 tail to 1, a 2 bloom at .4, a
-- small spark at .9), and the mana line under it, which draws no bloom or spark.
local RAIL_HEALTH = { coreHeight = 6, bloomSize = 2, sparkWidth = 10, sparkHeight = 10, tailAlpha = 0.35,
                      trackAlpha = 0.18, bloomAlpha = 0.4, sparkAlpha = 0.9, color = COLOR_HEALTH }
local RAIL_MANA = { coreHeight = 2, bloomSize = 1, sparkWidth = 4, sparkHeight = 4, tailAlpha = 0.35,
                    trackAlpha = 0.18, bloomAlpha = 0, sparkAlpha = 0, color = COLOR_POWER }

-- Look C's fill gradient: the deep foot is the class colour mixed 35% into #0d0620, the hot top the class colour.
local GRADIENT_INK = { 13 / 255, 6 / 255, 32 / 255 }
local GRADIENT_MIX = 0.35
local GRADIENT_ALPHA = 0.85
local GLOSS_ALPHA = 0.6

local HAS = {
    ROSTER = type(GetRaidRosterInfo) == "function",
    MEMBERS = type(GetNumGroupMembers) == "function",
    ROLE_API = type(UnitGroupRolesAssigned) == "function",
    UNIT_IN_RANGE = type(UnitInRange) == "function",
    TICKER = type(C_Timer) == "table" and type(C_Timer.NewTicker) == "function",
}

local TryStep = FS.FrameHelpers.NewStepRunner(
    function(label) return "|cffff4488Forever STUwave|r raidframe step '" .. label .. "'" end)

-------------------------------------------------------------------------------
-- Module state and the switch
-------------------------------------------------------------------------------

local RaidFrames = { CONFIG_KEY = "raid.shown" }
FS.RaidFrames = RaidFrames
FS.Config.RegisterDefault(RaidFrames.CONFIG_KEY, true)

-- `look` is "A", "C" or nil while the grid is down; `n` the members shown; `columns` the subgroup of each column,
-- left to right; `groups[g]` the raid indices in group g, by roster order.
local state = { look = nil, n = 0, columns = {}, groups = {}, playerIndex = nil, playerGroup = nil }
for g = 1, GROUP_COUNT do state.groups[g] = {} end
RaidFrames.state = state

-- started: PLAYER_LOGIN has gone by, so FS.Config answers the saved switch (nothing touches Blizzard's frames
-- before). owed: a reflow waits for PLAYER_REGEN_ENABLED. active: the grid is up.
local flags = { started = false, owed = false, queued = false, active = false }

-- dimmed: Blizzard's raid frames were dimmed this session (their events cannot be given back without a reload).
local blizz = { dimmed = false, pending = false, queued = false, reported = false }

local cells, labels = {}, {}
local container, content

function RaidFrames.IsShown()
    return FS.Config.Get(RaidFrames.CONFIG_KEY) == true
end

function RaidFrames.SetShown(on)
    return FS.Config.Set(RaidFrames.CONFIG_KEY, on and true or false)
end

function RaidFrames.IsActive()
    return flags.active
end

-- The config row's reload prompt: the switch applies live, but once Blizzard's raid frames were dimmed only a reload
-- gives them their events back.
function RaidFrames.NeedsReload()
    if blizz.dimmed and not RaidFrames.IsShown() then return RELOAD_LINE end
    return nil
end

local function After(fn)
    if type(C_Timer) == "table" and type(C_Timer.After) == "function" then
        C_Timer.After(0, fn)
    else
        fn()
    end
end

-------------------------------------------------------------------------------
-- Cell chrome
-------------------------------------------------------------------------------

local classColors = {}

-- The colour of a class token (PlainClassFile's rule, UnitFrames.lua): a secret or missing token is the flat pink.
local function ClassColorOf(classFile)
    if IsSecret(classFile) or type(classFile) ~= "string" then return COLOR_HEALTH end
    local cached = classColors[classFile]
    if cached then return cached end
    local c = type(RAID_CLASS_COLORS) == "table" and RAID_CLASS_COLORS[classFile]
    if not c then return COLOR_HEALTH end
    cached = { c.r, c.g, c.b, 1 }
    classColors[classFile] = cached
    return cached
end

local function ClassColor(unit)
    local _, classFile = UnitClass(unit)
    return ClassColorOf(classFile)
end

local function SetColor(text, color, alpha)
    text:SetTextColor(color[1], color[2], color[3], alpha or color[4] or 1)
end

-- The base edge (cyan or the dispel colour), the red low health layer above it and a hidden host for the down
-- dashes, all on `frame`'s rect. The low health curve drives the two edge FRAMES' alpha (UpdateRowLowHealth), so
-- the glow keeps its own alpha; the dashes are built the first time the cell goes down.
local function BuildEdges(parts, frame, level)
    local edge = CreateFrame("Frame", nil, frame)
    edge:SetAllPoints(frame)
    edge:SetFrameLevel(level)
    Theme.SkinButton(edge, { chamfer = CHAMFER, glowAlpha = EDGE_LIT.glow, borderColor = COLOR_POWER })
    local red = CreateFrame("Frame", nil, frame)
    red:SetAllPoints(frame)
    red:SetFrameLevel(level + 1)
    Theme.SkinButton(red, { chamfer = CHAMFER, glowAlpha = EDGE_LIT.glow, borderColor = COLOR_RED })
    red.fsSkin.border.ring:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], EDGE_LIT.ring)
    red.fsSkin.glow:SetVertexColor(COLOR_RED[1], COLOR_RED[2], COLOR_RED[3], EDGE_LIT.glow)
    red:SetAlpha(0)
    local dashHost = CreateFrame("Frame", nil, frame)
    dashHost:SetAllPoints(frame)
    dashHost:SetFrameLevel(level)
    dashHost:Hide()
    parts.edge, parts.red, parts.dashHost = edge, red, dashHost
    -- The aggro ring: pink or amber, one level above the red low health layer; the share of the mob's threat sits in it.
    if Extras and Extras.BuildGroupAggro then
        local ring = CreateFrame("Frame", nil, frame)
        ring:SetAllPoints(frame)
        ring:SetFrameLevel(level + 2)
        parts.aggro = Extras.BuildGroupAggro(ring, CHAMFER)
    end
end

local function BuildFill(frame, color)
    if not (Theme.AddCutSliceFill and Theme.AddCutSliceFill(frame, color, CHAMFER)) then
        Theme.AddRoundedFill(frame, color, CHAMFER)
    end
end

-- The fill of a look, kept so Background opacity can draw it again at another opacity (FrameExtras.NewFill).
local function NewCellFill(frame, color)
    if Extras and Extras.NewFill then return Extras.NewFill(frame, BuildFill, color) end
    BuildFill(frame, color)
    return nil
end

-- The own cell tick: 2 wide, pink, down the cell's left side just outside it, with a soft halo.
local function BuildTick(parts, frame, spec)
    local tick = frame:CreateTexture(nil, "OVERLAY")
    tick:SetTexture(FLAT_TEXTURE)
    tick:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 1)
    tick:SetSize(TICK_WIDTH, spec.h - 2 * spec.tickInset)
    tick:SetPoint("TOPLEFT", frame, "TOPLEFT", TICK_X, -spec.tickInset)
    tick:Hide()
    local halo = frame:CreateTexture(nil, "ARTWORK")
    halo:SetTexture(FLAT_TEXTURE)
    halo:SetBlendMode("ADD")
    halo:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], TICK_GLOW_ALPHA)
    halo:SetSize(TICK_GLOW_WIDTH, spec.h - 2 * spec.tickInset)
    halo:SetPoint("CENTER", tick, "CENTER", 0, 0)
    halo:Hide()
    parts.tick, parts.tickHalo = tick, halo
end

local function NewText(host)
    local text = host:CreateFontString(nil, "OVERLAY")
    text:SetWordWrap(false)
    return text
end

-- Look A, mini boxes: the cut box with its edge, the role letter and the name in the class colour on top (DEAD, OFF
-- or the low health percent at the right), then the health rail with the mana line under it.
local function BuildLookA(cell)
    local spec = LOOKS.A
    local frame = CreateFrame("Frame", nil, cell.visual)
    frame:SetAllPoints(cell.visual)
    local base = frame:GetFrameLevel()
    local parts = { look = "A", spec = spec, frame = frame }
    parts.fill = NewCellFill(frame, spec.fill)
    BuildEdges(parts, frame, base + 1)

    local health = CreateLaserRail(frame, RAIL_HEALTH)
    health.shell:SetPoint("TOPLEFT", frame, "TOPLEFT", 4, -15)
    health.shell:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -4, -15)
    local mana = CreateLaserRail(frame, RAIL_MANA)
    mana.shell:SetPoint("TOPLEFT", frame, "TOPLEFT", 4, -23)
    mana.shell:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -4, -23)
    mana.fsRail.host:Hide()

    local host = CreateFrame("Frame", nil, frame)
    host:SetAllPoints(frame)
    host:SetFrameLevel(base + 8)
    local role, name, stateText, pct = NewText(host), NewText(host), NewText(host), NewText(host)
    Theme.ApplyMono(role, 7)
    role:SetPoint("LEFT", frame, "TOPLEFT", 5, -7.5)
    Theme.ApplyMono(name, 8.5)
    name:SetPoint("LEFT", frame, "TOPLEFT", 13, -7.5)
    name:SetPoint("RIGHT", frame, "TOPRIGHT", -24, -7.5)
    name:SetJustifyH("LEFT")
    Theme.ApplyMono(stateText, 7.5, COLOR_STEEL)
    stateText:SetPoint("RIGHT", frame, "TOPRIGHT", -5, -7.5)
    stateText:SetJustifyH("RIGHT")
    SetColor(stateText, COLOR_STEEL)
    stateText:Hide()
    Theme.ApplyMono(pct, 7.5, COLOR_RED)
    pct:SetPoint("RIGHT", frame, "TOPRIGHT", -5, -7.5)
    pct:SetJustifyH("RIGHT")
    SetColor(pct, COLOR_RED)
    pct:SetAlpha(0)
    -- the health text of the Text setting when it shows at every health (Percent, Number); the red one above is the
    -- low health layer and covers it at 35% or less
    local fmt = NewText(host)
    Theme.ApplyMono(fmt, 7.5, COLOR_WHITE)
    fmt:SetPoint("RIGHT", frame, "TOPRIGHT", -5, -7.5)
    fmt:SetJustifyH("RIGHT")
    SetColor(fmt, COLOR_WHITE, 0.9)
    fmt:Hide()
    parts.fmt = fmt
    if Extras and Extras.BuildMarkers then parts.markers = Extras.BuildMarkers(frame, base + 9, frame) end
    if parts.aggro then Extras.SeatGroupAggro(parts.aggro, "raid", "RIGHT", "TOPRIGHT", -26, -7.5) end

    BuildTick(parts, frame, spec)
    parts.health, parts.mana = health, mana
    parts.role, parts.name, parts.state, parts.pct = role, name, stateText, pct
    parts.lowTargets, parts.lowBase = { parts.red, pct }, { parts.edge }
    parts.dimmed = { role, name, stateText, health.shell, mana.shell }
    return parts
end

-- Look C, tiles: health fills bottom up inside the tile (a vertical bar inset 1 at the sides, 2 at the top and 3 at
-- the foot, its corners erased at the tile's chamfer the way the party pet column is), a 1 high gloss on the fill's
-- top edge, the mana hairline in the 3 px under it, the name centred in white and the state or low percent below it.
local function BuildLookC(cell)
    local spec = LOOKS.C
    local frame = CreateFrame("Frame", nil, cell.visual)
    frame:SetAllPoints(cell.visual)
    local base = frame:GetFrameLevel()
    local parts = { look = "C", spec = spec, frame = frame }
    parts.fill = NewCellFill(frame, spec.fill)

    local health = CreateFrame("StatusBar", nil, frame)
    health:SetPoint("TOPLEFT", frame, "TOPLEFT", 1, -2)
    health:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", -1, 3)
    health:SetFrameLevel(base + 1)
    health:SetOrientation("VERTICAL")
    health:SetStatusBarTexture(FLAT_TEXTURE)
    health:SetMinMaxValues(0, 1)
    health:SetValue(0)
    local fill = health:GetStatusBarTexture()
    local gloss = health:CreateTexture(nil, "OVERLAY")
    gloss:SetTexture(FLAT_TEXTURE)
    gloss:SetVertexColor(1, 1, 1, GLOSS_ALPHA)
    gloss:SetPoint("TOPLEFT", fill, "TOPLEFT", 0, 0)
    gloss:SetPoint("TOPRIGHT", fill, "TOPRIGHT", 0, 0)
    gloss:SetHeight(1)

    -- The fill is square; the erase (a nine-slice over the tile's own rect at the ring's chamfer, clipped to the
    -- fill) takes its TOP-LEFT and BOTTOM-RIGHT corners off under the ring. Its colour is the tile ink's rgb.
    local corners = CreateFrame("Frame", nil, frame)
    corners:SetAllPoints(health)
    corners:SetFrameLevel(base + 2)
    local ink = { spec.fill[1], spec.fill[2], spec.fill[3], 1 }
    local erase
    if Theme.CHROME_CORNERS == "cut" and type(Theme.AddCutFillErase) == "function" and corners.SetClipsChildren then
        erase = Theme.AddCutFillErase(corners, frame, ink, CHAMFER)
        if erase then corners:SetClipsChildren(true) end
    end
    if not erase and type(Theme.AddCornerMask) == "function" then
        Theme.AddCornerMask(corners, health, ink, Theme.CHROME_CORNERS == "cut" and CHAMFER or CHAMFER - 1)
    end

    local mana = CreateFrame("StatusBar", nil, frame)
    mana:SetPoint("TOPLEFT", frame, "TOPLEFT", 3, -(spec.h - 3))
    mana:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -3, -(spec.h - 3))
    mana:SetHeight(1.5)
    mana:SetFrameLevel(base + 1)
    mana:SetStatusBarTexture(FLAT_TEXTURE)
    mana:SetMinMaxValues(0, 1)
    mana:SetValue(0)

    BuildEdges(parts, frame, base + 3)

    local host = CreateFrame("Frame", nil, frame)
    host:SetAllPoints(frame)
    host:SetFrameLevel(base + 6)
    local role, name, stateText, pct = NewText(host), NewText(host), NewText(host), NewText(host)
    Theme.ApplyFontGeneric(role, Theme.FONT_MONO, 7, nil, "OUTLINE")
    role:SetPoint("LEFT", frame, "TOPLEFT", 6, -8.5)
    Theme.ApplyFontGeneric(name, Theme.FONT_ORBITRON, 9, COLOR_WHITE, "OUTLINE")
    name:SetPoint("LEFT", frame, "TOPLEFT", 3, -14)
    name:SetPoint("RIGHT", frame, "TOPRIGHT", -3, -14)
    name:SetJustifyH("CENTER")
    Theme.ApplyFontGeneric(stateText, Theme.FONT_MONO, 7.5, COLOR_STEEL, "OUTLINE")
    stateText:SetPoint("CENTER", frame, "TOP", 0, -25.5)
    SetColor(stateText, COLOR_STEEL)
    stateText:Hide()
    Theme.ApplyFontGeneric(pct, Theme.FONT_MONO, 7.5, COLOR_RED, "OUTLINE")
    pct:SetPoint("CENTER", frame, "TOP", 0, -25.5)
    SetColor(pct, COLOR_RED)
    pct:SetAlpha(0)
    local fmt = NewText(host)
    Theme.ApplyFontGeneric(fmt, Theme.FONT_MONO, 7.5, COLOR_WHITE, "OUTLINE")
    fmt:SetPoint("CENTER", frame, "TOP", 0, -25.5)
    SetColor(fmt, COLOR_WHITE, 0.9)
    fmt:Hide()
    parts.fmt = fmt
    if Extras and Extras.BuildMarkers then parts.markers = Extras.BuildMarkers(frame, base + 7, frame) end
    if parts.aggro then Extras.SeatGroupAggro(parts.aggro, "raid", "BOTTOM", "BOTTOM", 0, 3) end

    BuildTick(parts, frame, spec)
    parts.health, parts.gloss, parts.corners, parts.mana = health, gloss, corners, mana
    parts.role, parts.name, parts.state, parts.pct = role, name, stateText, pct
    parts.lowTargets, parts.lowBase = { parts.red, pct }, { parts.edge }
    parts.dimmed = { role, name, stateText }
    return parts
end

local BUILDERS = { A = BuildLookA, C = BuildLookC }

-------------------------------------------------------------------------------
-- Cell updates (each takes the cell; the active look's pieces are cell.parts)
-------------------------------------------------------------------------------

-- Down (dead or offline) wins, then a debuff the player can remove, then the idle cyan. Live is the ring and glow at
-- the look's strength; down swaps both for steel dashes. Retints only when the look of it changed: every health and
-- aura event calls this.
local function ApplyEdge(cell)
    local parts = cell.parts
    local down = cell.down and true or false
    local lit = cell.dispelColor
    local color = (down and COLOR_STEEL) or lit or COLOR_POWER
    if parts.edgeDown == down and parts.edgeColor == color then return end
    parts.edgeDown, parts.edgeColor = down, color
    local ring, glow = parts.edge.fsSkin.border.ring, parts.edge.fsSkin.glow
    ring:SetShown(not down)
    parts.dashHost:SetShown(down)
    if down then
        glow:Hide()
        local spec = parts.eff or parts.spec
        local sizeKey = spec.w .. "x" .. spec.h
        if parts.dashKey ~= sizeKey then
            -- one dash run per cell size: a width or height change draws its own, the old runs stay hidden
            parts.dashSets = parts.dashSets or {}
            for _, run in pairs(parts.dashSets) do for _, d in ipairs(run) do d:Hide() end end
            local run = parts.dashSets[sizeKey]
            if not run then
                run = BuildDashEdge(parts.dashHost, spec.w, spec.h, CHAMFER, DASH_SIZE, DASH_GAP)
                parts.dashSets[sizeKey] = run
            end
            for _, d in ipairs(run) do d:Show() end
            parts.dashes, parts.dashKey = run, sizeKey
        end
        TintDashes(parts.dashes, color[1], color[2], color[3], DASH_ALPHA)
        return
    end
    local strength = lit and EDGE_LIT or parts.spec.idle
    ring:SetVertexColor(color[1], color[2], color[3], strength.ring)
    glow:SetVertexColor(color[1], color[2], color[3], strength.glow)
    glow:SetShown(strength.glow > 0)
end

-- The name colour: steel when down, else the class colour (A) or white (C).
local function PaintName(cell)
    local parts = cell.parts
    if cell.down then
        SetColor(parts.name, COLOR_STEEL, parts.look == "A" and NAME_ALPHA_A or 1)
    elseif parts.look == "A" then
        SetColor(parts.name, cell.classColor or COLOR_HEALTH, NAME_ALPHA_A)
    else
        SetColor(parts.name, COLOR_WHITE)
    end
end

-- Look C's fill gradient for `color`, set once per colour; SetGradient is feature dependent, so a refusal takes the
-- flat class colour instead.
local function PaintTileFill(parts, color)
    if parts.fillColor == color then return end
    parts.fillColor = color
    local fill = parts.health:GetStatusBarTexture()
    local r, g, b = color[1], color[2], color[3]
    local keep = 1 - GRADIENT_MIX
    local ok = type(CreateColor) == "function" and fill.SetGradient and pcall(fill.SetGradient, fill, "VERTICAL",
        CreateColor(GRADIENT_INK[1] * keep + r * GRADIENT_MIX, GRADIENT_INK[2] * keep + g * GRADIENT_MIX,
            GRADIENT_INK[3] * keep + b * GRADIENT_MIX, GRADIENT_ALPHA),
        CreateColor(r, g, b, GRADIENT_ALPHA))
    if not ok then parts.health:SetStatusBarColor(r, g, b, GRADIENT_ALPHA) end
end

-- The paint half of every step below takes plain values and no unit, so the editor preview (further down) draws a fake
-- member through the very same code the real cells use.
local function PaintClass(cell, color)
    local parts = cell.parts
    cell.classColor = color
    PaintName(cell)
    if cell.down then return end
    if parts.look == "A" then
        SetLaserRailColor(parts.health, color[1], color[2], color[3])
    else
        PaintTileFill(parts, color)
    end
end

local function UpdateClass(cell)
    PaintClass(cell, ClassColor(cell.unit))
end

-- The cell's look for its state, down (dead or offline) or live; the values and the edge come after. Returns down.
local function PaintHealthState(cell, offline, dead)
    local parts = cell.parts
    local down = (offline or dead) and true or false
    cell.down = down
    local health = parts.health
    local a = parts.look == "A"
    local alpha = down and STATE_ALPHA or 1
    for _, region in ipairs(parts.dimmed) do region:SetAlpha(alpha) end
    if down then
        health:SetMinMaxValues(0, 1)
        health:SetValue(0)
        if a then
            SetLaserRailDesaturated(health, true)
            SetLaserRailColor(health, STATE_BAR_COLOR[1], STATE_BAR_COLOR[2], STATE_BAR_COLOR[3])
            health.fsRail.host:Hide()
        else
            health:Hide()
            parts.corners:Hide()   -- the erase is opaque ink and would show with no fill under it
            parts.mana:Hide()
        end
        parts.state:SetText(offline and "OFF" or "DEAD")
        parts.state:Show()
    else
        parts.state:Hide()
        local color = cell.classColor or COLOR_HEALTH
        if a then
            SetLaserRailDesaturated(health, false)
            SetLaserRailColor(health, color[1], color[2], color[3])
            health.fsRail.host:Show()
        else
            PaintTileFill(parts, color)
            health:Show()
            parts.corners:Show()
            parts.mana:Show()
        end
    end
    return down
end

local function UpdateHealth(cell)
    local parts = cell.parts
    local unit = cell.unit
    local offline, dead = RowDownState(unit)
    local down = PaintHealthState(cell, offline, dead)
    if not down then
        local cur = UnitHealth(unit)
        if not IsSecret(cur) and cur == nil then cur = 0 end
        local max = ReadHealthMax(unit)
        parts.health:SetMinMaxValues(0, max)
        parts.health:SetValue(cur)
        local fmt = Style and Style.Get("raid", "raidFmt") or "low"
        if fmt == "number" then
            parts.pct:SetFormattedText("%d", cur)
            parts.pct:Show()
        else
            UpdateHealthPercentText(parts.pct, unit, cur, max)
        end
        if fmt == "none" then parts.pct:Hide() end
        if parts.fmt then
            if fmt == "percent" then
                UpdateHealthPercentText(parts.fmt, unit, cur, max)
            elseif fmt == "number" then
                parts.fmt:SetFormattedText("%d", cur)
                parts.fmt:Show()
            else
                parts.fmt:Hide()
            end
        end
    elseif parts.fmt then
        parts.fmt:Hide()
    end
    PaintName(cell)
    UpdateRowLowHealth(cell, down)
    ApplyEdge(cell)
end

local function PaintPower(cell, cur, max, powerType)
    local parts = cell.parts
    local mana = parts.mana
    mana:SetMinMaxValues(0, max)
    mana:SetValue(cur)
    local color = (not IsSecret(powerType) and POWER_COLORS[powerType]) or COLOR_POWER
    if parts.look == "A" then
        SetLaserRailColor(mana, color[1], color[2], color[3])
    else
        mana:SetStatusBarColor(color[1], color[2], color[3], 1)
    end
end

-- Raid members are players, so the mana line always shows; a secret max goes straight to the setter.
local function UpdatePower(cell)
    local unit = cell.unit
    local max = UnitPowerMax(unit)
    if not IsSecret(max) and (type(max) ~= "number" or max <= 0) then max = 1 end
    local cur = UnitPower(unit)
    if not IsSecret(cur) and type(cur) ~= "number" then cur = 0 end
    PaintPower(cell, cur, max, UnitPowerType(unit))
end

-- The first name only (UnitName; the cell is too small for a surname), upper-cased in look A when it is a plain
-- string. A secret name goes to SetText untouched, and the font string truncates it.
local function PaintNameText(parts, name)
    if IsSecret(name) then
        parts.name:SetText(name)
    elseif type(name) ~= "string" then
        parts.name:SetText("")
    else
        parts.name:SetText(parts.look == "A" and name:upper() or name)
    end
end

local function UpdateName(cell)
    PaintNameText(cell.parts, UnitName(cell.unit))
end

local function PaintRole(parts, role)
    local style = not IsSecret(role) and role and ROLE_STYLE[role]
    if Style and not Style.Get("raid", "role") then style = nil end
    if not style then
        parts.role:Hide()
        return
    end
    parts.role:SetText(style[1])
    SetColor(parts.role, style[2])
    parts.role:Show()
end

local function UpdateRole(cell)
    PaintRole(cell.parts, HAS.ROLE_API and UnitGroupRolesAssigned(cell.unit) or nil)
end

-- Event driven only (UNIT_AURA, the regen rescan and FS.OnAurasReadable), never on a ticker, and never under lockdown:
-- a refused read leaks, so the last known edge holds through the fight.
local function UpdateAuras(cell)
    if not FS.AurasReadable() then return end
    local cleansable, harmful = ScanDebuffs(cell.unit)
    local color = nil
    if #cleansable > 0 then
        color = GetDispelColor(cleansable[1].dispelType) or Shared.COLOR_CLEANSABLE_UNKNOWN
    end
    -- the debuff the player can remove lights the edge (Debuff border); the colour is kept so the switch can follow
    cell.dispelRaw = color
    cell.dispelColor = (not Style or Style.Get("raid", "dispelEdge") == true) and color or nil
    ApplyEdge(cell)
    local parts = cell.parts
    if parts.markers then
        local offline, dead = RowDownState(cell.unit)
        if offline or dead then
            Extras.PaintMarkers(parts.markers, "raid", parts.markers.list, 0)
        else
            Extras.UpdateMarkers(parts.markers, cell.unit, "raid", harmful)
        end
    end
end

local function UpdateAll(cell)
    if not cell.parts or not UnitExists(cell.unit) then return end
    TryStep(cell, "class", UpdateClass)
    TryStep(cell, "health", UpdateHealth)
    TryStep(cell, "power", UpdatePower)
    TryStep(cell, "name", UpdateName)
    TryStep(cell, "role", UpdateRole)
    TryStep(cell, "auras", UpdateAuras)
    if Extras and Extras.UpdateGroupRow then TryStep(cell, "aggro", Extras.UpdateGroupRow) end
end

local function ShowTick(cell, on)
    local parts = cell.parts
    if not parts then return end
    parts.tick:SetShown(on)
    parts.tickHalo:SetShown(on)
end

-------------------------------------------------------------------------------
-- Roster
-------------------------------------------------------------------------------

local function RosterSize()
    local n = HAS.MEMBERS and GetNumGroupMembers() or 0
    if IsSecret(n) or type(n) ~= "number" then return 0 end
    return math.max(0, math.min(n, RAID_SIZE))
end

-- The subgroup of raid index `i`: GetRaidRosterInfo's third return when it is a plain 1..8, else the roster order
-- (ceil(i / 5)). A secret is never compared.
local function Subgroup(i)
    if HAS.ROSTER then
        local ok, _, _, sub = pcall(GetRaidRosterInfo, i)
        if ok and not IsSecret(sub) and type(sub) == "number" and sub >= 1 and sub <= GROUP_COUNT
            and sub == math.floor(sub) then
            return sub
        end
    end
    return math.min(math.ceil(i / GROUP_SIZE), GROUP_COUNT)
end

-- The player's raid index: UnitInRaid("player") when it is a plain index (it is secret where unit identity is
-- restricted), else the first raid token UnitIsUnit plainly calls the player, else nil.
local function PlayerIndex(n)
    local ok, index = pcall(UnitInRaid, "player")
    if ok and not IsSecret(index) and type(index) == "number" and index >= 1 and index <= n then return index end
    for i = 1, n do
        local okSame, same = pcall(UnitIsUnit, "raid" .. i, "player")
        if okSame and not IsSecret(same) and same == true then return i end
    end
    return nil
end

local function ReadRoster(n)
    local groups = state.groups
    for g = 1, GROUP_COUNT do
        local list = groups[g]
        for k = #list, 1, -1 do list[k] = nil end
    end
    local subgroupOf = {}
    for i = 1, n do
        local g = Subgroup(i)
        subgroupOf[i] = g
        local list = groups[g]
        list[#list + 1] = i
    end
    state.n = n
    state.playerIndex = PlayerIndex(n)
    state.playerGroup = state.playerIndex and subgroupOf[state.playerIndex] or nil
    local columns = state.columns
    for k = #columns, 1, -1 do columns[k] = nil end
    if state.playerGroup then columns[1] = state.playerGroup end
    for g = 1, GROUP_COUNT do
        if g ~= state.playerGroup and #groups[g] > 0 then columns[#columns + 1] = g end
    end
end

-------------------------------------------------------------------------------
-- Layout (out of combat only: the container, the content frame and every cell are protected)
-------------------------------------------------------------------------------

-- The raid's own style settings (FrameStyle.lua, frame "raid"). A default raid reads LOOKS as it always did; a stored
-- width gives a copy of the look's spec with that width (look C keeps its ratio to look A).
local specCache = {}
local function EffSpec(spec)
    if spec.eff then return spec end
    if not (Style and (Style.IsStored("raid", "w") or Style.IsStored("raid", "hpH") or Style.IsStored("raid", "mpH"))) then
        return spec
    end
    local tiles = spec == LOOKS.C
    local w, h = Style.Number("raid", "w"), Style.FrameHeight("raid")
    local wantW = tiles and math.floor(w * LOOKS.C.w / LOOKS.A.w + 0.5) or w
    local wantH = tiles and math.floor(h * LOOKS.C.h / LOOKS.A.h + 0.5) or h
    local hit = specCache[spec]
    if hit and hit.w == wantW and hit.h == wantH then return hit end
    local copy = {}
    for k, v in pairs(spec) do copy[k] = v end
    copy.w, copy.h, copy.eff = wantW, wantH, true
    specCache[spec] = copy
    return copy
end

-- What the raid's style settings change on one built cell: its opacity and the name size of both looks. Plain regions
-- only, so it runs in combat too.
local function ScaleText(region, want)
    if not (region and region.GetFont) then return end
    local font, size, flags = region:GetFont()
    if font and type(size) == "number" then
        region.baseSize = region.baseSize or size
        if want ~= size then region:SetFont(font, want, flags) end
    end
end

-- A rail's core thickness: the shell, the bar and both track halves.
local function SetRailCore(bar, core)
    bar.shell:SetHeight(core)
    bar:SetHeight(core)
    local rail = bar.fsRail
    if rail then
        rail.trackLeft:SetHeight(core)
        rail.trackRight:SetHeight(core)
    end
end

local function ApplyCellStyle(cell)
    if not Style then return end
    cell:SetAlpha(Style.Number("raid", "alpha") / 100)
    local ratio = Style.Number("raid", "nameSize") / 8.5
    local hp, mp = Style.Number("raid", "hpH"), Style.Number("raid", "mpH")
    local bg = Style.Number("raid", "bgAlpha") / Style.Default("raid", "bgAlpha")
    for id, parts in pairs(cell.looks or {}) do
        local name = parts.name
        if name and name.GetFont then
            local font, size, flags = name:GetFont()
            if font and type(size) == "number" then
                parts.nameBase = parts.nameBase or size
                if parts.nameBase * ratio ~= size then name:SetFont(font, parts.nameBase * ratio, flags) end
            end
        end
        -- the health text (Text size) follows its own setting, 7.5 today
        local ts = Style.Number("raid", "hpTs")
        ScaleText(parts.pct, ts)
        ScaleText(parts.fmt, ts)
        -- the bar heights and the cell size they make (the secure size itself is SeatCell's, out of combat)
        local eff = EffSpec(parts.spec)
        parts.eff = eff
        local sig = hp .. ":" .. mp .. ":" .. eff.w .. ":" .. eff.h
        if parts.geomSig ~= sig then
            parts.geomSig = sig
            if id == "A" then
                SetRailCore(parts.health, hp)
                parts.mana.shell:ClearAllPoints()
                parts.mana.shell:SetPoint("TOPLEFT", parts.frame, "TOPLEFT", 4, -(15 + hp + 2))
                parts.mana.shell:SetPoint("TOPRIGHT", parts.frame, "TOPRIGHT", -4, -(15 + hp + 2))
                if mp > 0 then SetRailCore(parts.mana, mp) end
                parts.mana.shell:SetShown(mp > 0)
            else
                parts.mana:SetHeight(math.min(4, mp * 0.75))
                parts.mana:SetShown(mp > 0 and not cell.down)
                parts.mana:ClearAllPoints()
                parts.mana:SetPoint("TOPLEFT", parts.frame, "TOPLEFT", 3, -(eff.h - 3))
                parts.mana:SetPoint("TOPRIGHT", parts.frame, "TOPRIGHT", -3, -(eff.h - 3))
            end
            local tickH = eff.h - 2 * eff.tickInset
            parts.tick:SetSize(TICK_WIDTH, tickH)
            parts.tickHalo:SetSize(TICK_GLOW_WIDTH, tickH)
            parts.edgeDown = nil   -- a down cell's dashes are drawn for the new size
            if cell.parts == parts then ApplyEdge(cell) end
        end
        if parts.fill then parts.fill.Set(parts.fill.base * bg) end
        if parts.markers and Extras then
            Extras.Rehold(parts.markers, "raid")
            Extras.PaintMarkers(parts.markers, "raid", parts.markers.list, parts.markers.shown)
        end
        if parts.aggro then
            Extras.SeatGroupAggro(parts.aggro, "raid", id == "A" and "RIGHT" or "BOTTOM", id == "A" and "TOPRIGHT" or "BOTTOM",
                id == "A" and -26 or 0, id == "A" and -7.5 or 3)
            if not Style.Get("raid", "threat") then parts.aggro.ring:Hide(); parts.aggro.pct:Hide() end
        end
    end
    -- the Debuff border switch: the colour the last read found shows or goes
    local want = Style.Get("raid", "dispelEdge") == true and cell.dispelRaw or nil
    if cell.dispelColor ~= want then
        cell.dispelColor = want
        if cell.parts then ApplyEdge(cell) end
    end
end

-- Gives one cell a look, building its pieces the first time. A cell holds both looks and shows one.
local function LookCell(cell, id)
    local parts = cell.looks[id]
    if not parts then
        parts = BUILDERS[id](cell)
        cell.looks[id] = parts
    end
    for other, otherParts in pairs(cell.looks) do otherParts.frame:SetShown(other == id) end
    cell.parts = parts
    cell.groupAggro, cell.groupKey = parts.aggro, "raid"
    cell.lowHealthTargets, cell.lowHealthBase = parts.lowTargets, parts.lowBase
    ApplyCellStyle(cell)
end

local function UseLook(id)
    if state.look == id then return end
    for _, cell in ipairs(cells) do LookCell(cell, id) end
    state.look = id
end

-- The look a roster of n draws: Auto is mini boxes up to SMALL_RAID and tiles above; the setting can force either.
local function LookIdFor(n)
    local pick = Style and Style.Get("raid", "raidLook") or "auto"
    if pick == "boxes" then return "A" end
    if pick == "tiles" then return "C" end
    return n <= SMALL_RAID and "A" or "C"
end

local function RaidScale()
    local pct = tonumber(FS.Config.Get("raid.scale")) or 100
    return FS.Layout.Scale() * pct / 100
end

local function SeatCell(host, cell, spec, column, row)
    spec = EffSpec(spec)
    cell:ClearAllPoints()
    cell:SetPoint("TOPLEFT", host, "TOPLEFT", column * (spec.w + spec.gx), -(spec.hdr + row * (spec.h + spec.gy)))
    cell:SetSize(spec.w, spec.h)
end

local SORT_ROLE = { TANK = 1, HEALER = 2, DAMAGER = 3 }

-- Member indexes 1..n in the order the Sort setting names. infoOf(i) answers { class, role, name } as plain values.
local function SortedMembers(n, infoOf)
    local list = {}
    for i = 1, n do list[i] = i end
    local by = FS.Config.Get("raid.sort") or "group"
    if by == "group" or not infoOf then return list end
    local function key(i)
        local m = infoOf(i) or {}
        if by == "role" then return SORT_ROLE[m.role] or 4 end
        if by == "class" then return type(m.class) == "string" and m.class or "~" end
        return type(m.name) == "string" and m.name:lower() or "~"
    end
    table.sort(list, function(a, b)
        local ka, kb = key(a), key(b)
        if ka ~= kb then return ka < kb end
        return a < b
    end)
    return list
end

-- Lays out one grid (`grid` holds its cells, labels, content and container: the real one or the editor preview's):
-- one column per group in `columns`, five cells down (Arrange: Group columns), or rows of Frames per row in Sort order
-- (Arrange: Grid); the cells past the roster are parked in further columns to the right, five down, so a member who
-- joins in combat (the unit watch shows the cell, nothing may move it) never lands on a member's cell. The grid is sized
-- from the cells it shows.
local function PlaceGrid(grid, spec, columns, groups, playerGroup, infoOf)
    local host, gridCells, gridLabels = grid.content, grid.cells, grid.labels
    local eff = EffSpec(spec)
    local placed, rows = {}, 0
    local count, wide = 0, 0
    if FS.Config.Get("raid.arrange") == "grid" then
        local n = 0
        for _, group in ipairs(columns) do n = n + #groups[group] end
        local perRow = math.max(1, (tonumber(FS.Config.Get("raid.perRow")) or 5))
        local order = SortedMembers(n, infoOf)
        local bare = {}   -- no group labels, so no header gap
        for k, v in pairs(eff) do bare[k] = v end
        bare.hdr, bare.eff = 0, true
        for k, index in ipairs(order) do
            SeatCell(host, gridCells[index], bare, (k - 1) % perRow, math.floor((k - 1) / perRow))
            placed[index] = true
        end
        for k = 1, GROUP_COUNT do gridLabels[k]:Hide() end
        count = math.min(perRow, math.max(n, 1))
        rows = math.ceil(n / perRow)
        wide = math.max(count, 1)
        local spare = 0
        for i = 1, RAID_SIZE do
            if not placed[i] then
                SeatCell(host, gridCells[i], bare, perRow + math.floor(spare / GROUP_SIZE), spare % GROUP_SIZE)
                spare = spare + 1
            end
        end
        local w = wide * eff.w + math.max(wide - 1, 0) * eff.gx
        local h = rows * eff.h + math.max(rows - 1, 0) * eff.gy
        local scale = RaidScale()
        host:SetScale(scale)
        host:SetSize(w, h)
        grid.container:SetSize(w * scale, h * scale)
        return w, h
    end
    for k, group in ipairs(columns) do
        local members = groups[group]
        for row, index in ipairs(members) do
            SeatCell(host, gridCells[index], spec, k - 1, row - 1)
            placed[index] = true
        end
        rows = math.max(rows, #members)
        local label = gridLabels[k]
        label:ClearAllPoints()
        label:SetPoint("LEFT", host, "TOPLEFT", (k - 1) * (eff.w + eff.gx) + LABEL_X, LABEL_Y)
        label:SetText("G" .. group)
        SetColor(label, group == playerGroup and COLOR_HEALTH or COLOR_BORDER, LABEL_ALPHA)
        label:Show()
    end
    for k = #columns + 1, GROUP_COUNT do gridLabels[k]:Hide() end
    count = #columns
    local spare = 0
    for i = 1, RAID_SIZE do
        if not placed[i] then
            SeatCell(host, gridCells[i], spec, count + math.floor(spare / GROUP_SIZE), spare % GROUP_SIZE)
            spare = spare + 1
        end
    end
    local w = count * eff.w + math.max(count - 1, 0) * eff.gx
    local h = eff.hdr + rows * eff.h + math.max(rows - 1, 0) * eff.gy
    local scale = RaidScale()
    host:SetScale(scale)
    host:SetSize(w, h)
    grid.container:SetSize(w * scale, h * scale)
    return w, h
end

local realGrid = { cells = cells, labels = labels }   -- content and container are set at Init

-- { class, role, name } of raid member i as plain values (the Sort setting reads them); a secret or missing answer is nil.
local function RosterInfo(i)
    if not HAS.ROSTER then return nil end
    local ok, name, _, _, _, _, classFile, _, _, _, _, _, role = pcall(GetRaidRosterInfo, i)
    if not ok then return nil end
    local function plain(v) if IsSecret(v) or type(v) ~= "string" then return nil end return v end
    return { name = plain(name), class = plain(classFile), role = plain(role) }
end

local function Place()
    PlaceGrid(realGrid, LOOKS[state.look], state.columns, state.groups, state.playerGroup, RosterInfo)
end

-- The layout entry of the smallest size that fits `n` members: 1 to 5 raid5, 6 to 10 raid10, ... 26 to 40 raid40. Nobody
-- reads as the first size and more than forty as the last.
local function SeatIdFor(n)
    for _, size in ipairs(SEAT_SIZES) do
        if type(n) == "number" and n <= size then return "raid" .. size end
    end
    return "raid" .. SEAT_SIZES[#SEAT_SIZES]
end
RaidFrames.SeatId = SeatIdFor

-- A seat's top left on a whole physical pixel, as the party container does (PartyFrames.lua, SeatOnWholePixels), so the
-- cells' ring and glow round together. The raid entries are TOPLEFT against the screen centre; a client with no pixel
-- API, or a UIParent with no centre yet, keeps Layout's own seat.
local function SnapSeat(frame, id)
    local entry = FS.Layout[id]
    if type(entry) ~= "table" or type(GetPhysicalScreenSize) ~= "function" then return end
    local _, physH = GetPhysicalScreenSize()
    local uiScale = UIParent:GetEffectiveScale()
    local ux, uy = UIParent:GetCenter()
    if type(physH) ~= "number" or physH <= 0 or type(uiScale) ~= "number" or uiScale <= 0
        or type(ux) ~= "number" or type(uy) ~= "number" then return end
    local factor = 768 / physH
    if type(PixelUtil) == "table" and type(PixelUtil.GetPixelToUIUnitFactor) == "function" then
        factor = PixelUtil.GetPixelToUIUnitFactor()
    end
    local px = factor / uiScale   -- one physical pixel, in UIParent units
    local scale = FS.Layout.Scale()
    local left = math.floor((ux + entry.x * scale) / px + 0.5) * px
    local top = math.floor((uy + entry.y * scale) / px + 0.5) * px
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", UIParent, "CENTER", left - ux, top - uy)
end

-- Seats `frame` (the grid or the editor's preview) from layout entry `id`, then on a whole pixel. The entry is
-- registered for Layout's rescale re-seat, which holds a protected frame back in combat.
local function SeatGrid(frame, id)
    FS.Layout.Apply(frame, id)
    SnapSeat(frame, id)
end

-- The real grid sits at the seat of the size its roster fills (state.n).
local function Seat()
    SeatGrid(container, SeatIdFor(state.n))
end

-- Contents only (no protected call): every member cell, the own cell tick and the range.
local RefreshRanges
local function RefreshCells()
    for i = 1, state.n do UpdateAll(cells[i]) end
    for i, cell in ipairs(cells) do ShowTick(cell, i == state.playerIndex) end
    RefreshRanges()
end

local function SetPartySuppressed(on)
    local party = FS.PartyFrames
    if party and party.SetSuppressed then party.SetSuppressed(on) end
end

-- Puts the grid in step with the roster and the switch. In combat only the contents of the cells already up are
-- refreshed (a token that changed hands repaints) and the rest is owed to PLAYER_REGEN_ENABLED.
local function Reflow()
    flags.queued = false
    if not container then return end
    if InCombatLockdown() then
        flags.owed = true
        if flags.active then
            local n = RosterSize()
            state.n = n
            state.playerIndex = PlayerIndex(n)
            RefreshCells()
        end
        return
    end
    flags.owed = false
    local n = RosterSize()
    local want = flags.started and RaidFrames.IsShown() and type(IsInRaid) == "function" and IsInRaid() and n > 0
    want = want and true or false
    SetPartySuppressed(want)
    if not want then
        flags.active = false
        state.n = 0
        container:Hide()
        return
    end
    UseLook(LookIdFor(n))
    ReadRoster(n)
    Place()
    Seat()
    container:Show()
    flags.active = true
    RefreshCells()
end

local function QueueReflow()
    if flags.queued then return end
    flags.queued = true
    After(Reflow)
end

function RefreshRanges()
    if not flags.active or not HAS.UNIT_IN_RANGE then return end
    for i = 1, state.n do
        local cell = cells[i]
        if i == state.playerIndex or not UnitExists(cell.unit) then
            cell.visual:SetAlpha(Shared.RANGE_ALPHA_IN_RANGE)
        else
            ApplyRangeAlpha(cell.visual, UnitInRange(cell.unit))
        end
    end
end

-------------------------------------------------------------------------------
-- Editor preview (the layout editor shows it; LayoutEdit.lua)
-------------------------------------------------------------------------------

-- While the layout editor is on, a grid of plain frames sits at the seat of the size being previewed so the player can
-- place each raid layout and swap between sizes without a raid. It is built from the same look builders and painted by the same functions as the
-- real cells, but from fake members and plain numbers: no secure frame, no unit token, no secret value. In a real raid
-- it stands in for the real grid, which stays up and current under it with its alpha at 0 (an alpha is all that is
-- written to it, so combat starting while the preview is up changes nothing protected). Out of combat only.
local Preview = { KEY = "raid.previewSize", SIZES = SEAT_SIZES }
RaidFrames.Preview = Preview
FS.Config.RegisterDefault(Preview.KEY, 10)

local PREVIEW_DEFAULT = 10
-- cells, labels, content, container fill in at the first Show; shown, size, look, columns, groups are the live state.
local pv = { grid = { cells = {}, labels = {} }, listeners = {}, shown = false, columns = {}, groups = {} }
for g = 1, GROUP_COUNT do pv.groups[g] = {} end
FS.raidPreview = pv

-- Forty fake members, five to a group, as { class, role }; member 1 is the player (their own class and role). The
-- names are first names only, as UnitName answers them, and none is a real player's.
local PREVIEW_CAST = {
    { nil, nil },             { "PRIEST", "HEALER" },   { "WARRIOR", "TANK" },    { "MAGE", "DAMAGER" },    { "ROGUE", "DAMAGER" },
    { "PALADIN", "TANK" },    { "DRUID", "HEALER" },    { "HUNTER", "DAMAGER" },  { "WARLOCK", "DAMAGER" }, { "SHAMAN", "HEALER" },
    { "WARRIOR", "TANK" },    { "PRIEST", "HEALER" },   { "MAGE", "DAMAGER" },    { "ROGUE", "DAMAGER" },   { "WARLOCK", "DAMAGER" },
    { "DRUID", "HEALER" },    { "HUNTER", "DAMAGER" },  { "SHAMAN", "DAMAGER" },  { "MAGE", "DAMAGER" },    { "PALADIN", "HEALER" },
    { "WARRIOR", "DAMAGER" }, { "ROGUE", "DAMAGER" },   { "PRIEST", "HEALER" },   { "WARLOCK", "DAMAGER" }, { "HUNTER", "DAMAGER" },
    { "SHAMAN", "HEALER" },   { "MAGE", "DAMAGER" },    { "DRUID", "DAMAGER" },   { "ROGUE", "DAMAGER" },   { "PALADIN", "DAMAGER" },
    { "HUNTER", "DAMAGER" },  { "WARLOCK", "DAMAGER" }, { "PRIEST", "HEALER" },   { "WARRIOR", "TANK" },    { "MAGE", "DAMAGER" },
    { "ROGUE", "DAMAGER" },   { "DRUID", "HEALER" },    { "SHAMAN", "DAMAGER" },  { "HUNTER", "DAMAGER" },  { "WARLOCK", "DAMAGER" },
}
local PREVIEW_NAMES = {
    "Aldric", "Brenna", "Corvin", "Dalia", "Edric", "Fenna", "Garrick", "Hilda", "Ivor", "Jorun",
    "Kaela", "Lorcan", "Mirela", "Nolan", "Orsa", "Pavel", "Quill", "Rhona", "Soren", "Talia",
    "Ulric", "Vesna", "Wynn", "Xander", "Yara", "Zephyr", "Bram", "Cato", "Dena", "Elric",
    "Faye", "Gwen", "Holt", "Isla", "Jory", "Kane", "Lena", "Moss", "Nyx", "Orin",
}
-- Health fractions in a repeating spread, with a few members who show each state a real cell can wear: at or under 35%
-- (the red edge and the percent; exactly 35% counts), dead, offline, out of range. The first five already carry one of
-- each, so even the smallest size shows them all.
local PREVIEW_HEALTH = { 1, 0.92, 0.78, 0.64, 0.85, 0.97, 0.55, 0.72 }
local PREVIEW_STATES = {
    [2] = { hp = 0.28 }, [3] = { state = "dead" }, [4] = { state = "offline" }, [5] = { far = true },
    [9] = { hp = 0.35 }, [13] = { state = "dead" }, [14] = { hp = 0.12 }, [18] = { far = true },
    [22] = { state = "offline" }, [27] = { hp = 0.31 }, [33] = { far = true }, [36] = { state = "dead" },
}
local PREVIEW_POWER = { WARRIOR = 1, ROGUE = 3 }   -- rage and energy; every other class has mana

-- Sample debuff types, markers and aggro for the Style tab's raid (member index -> value).
local PREVIEW_DEBUFFS = { [6] = "Magic", [8] = "Poison" }
local PREVIEW_MARKS = {}
local PREVIEW_AGGRO = { [2] = { "pink", "100%" }, [10] = { "amber", "71%" }, [1] = { "amber", "38%" } }

-- Member `i` as plain values. The player's own class and name come from the player; a secret or missing answer is the
-- first of the list.
local function PreviewMember(i)
    local cast = PREVIEW_CAST[i]
    local class, role, name = cast[1], cast[2], PREVIEW_NAMES[i]
    if i == 1 then
        local classFile = Shared.PlayerClass()
        class = (not IsSecret(classFile) and type(classFile) == "string") and classFile or "SHAMAN"
        local playerRole = HAS.ROLE_API and UnitGroupRolesAssigned("player") or nil
        role = (not IsSecret(playerRole) and ROLE_STYLE[playerRole] and playerRole) or "DAMAGER"
        local own = UnitName("player")
        if not IsSecret(own) and type(own) == "string" and own ~= "" then name = own end
    end
    local special = PREVIEW_STATES[i] or {}
    return {
        class = class, role = role, name = name,
        hp = special.hp or PREVIEW_HEALTH[(i - 1) % #PREVIEW_HEALTH + 1],
        state = special.state or "live", far = special.far == true,
        powerType = PREVIEW_POWER[class] or 0, power = 0.35 + 0.65 * ((i * 7) % 10) / 9,
    }
end

-- Paints preview cell `i` through the same paint functions a real cell uses, in the same order as UpdateAll.
local function PaintPreviewCell(cell, i, ownIndex)
    local m = PreviewMember(i)
    local parts = cell.parts
    PaintClass(cell, ClassColorOf(m.class))
    local down = PaintHealthState(cell, m.state == "offline", m.state == "dead")
    if not down then
        parts.health:SetMinMaxValues(0, 1000)
        parts.health:SetValue(m.hp * 1000)
        local fmt = Style and Style.Get("raid", "raidFmt") or "low"
        local amount = math.floor(m.hp * 1427 + 0.5)
        if fmt == "number" then parts.pct:SetFormattedText("%d", amount) else parts.pct:SetFormattedText("%.0f%%", m.hp * 100) end
        parts.pct:SetShown(fmt ~= "none")
        if parts.fmt then
            if fmt == "percent" then parts.fmt:SetFormattedText("%.0f%%", m.hp * 100); parts.fmt:Show()
            elseif fmt == "number" then parts.fmt:SetFormattedText("%d", amount); parts.fmt:Show()
            else parts.fmt:Hide() end
        end
    elseif parts.fmt then
        parts.fmt:Hide()
    end
    -- The plain-number twin of UpdateRowLowHealth: the red layer and the percent at or under the threshold, else the
    -- base edge; a down cell shows neither red nor percent.
    local low = not down and m.hp <= Shared.LOW_HP_FRACTION
    for _, target in ipairs(cell.lowHealthTargets) do target:SetAlpha(low and 1 or 0) end
    for _, target in ipairs(cell.lowHealthBase) do target:SetAlpha(low and 0 or 1) end
    PaintName(cell)
    -- sample debuffs: the edge takes the colour of one the player can remove (the Debuff border switch)
    local sampleType = PREVIEW_DEBUFFS[i]
    cell.dispelRaw = sampleType and GetDispelColor(sampleType) or nil
    cell.dispelColor = (not Style or Style.Get("raid", "dispelEdge") == true) and cell.dispelRaw or nil
    ApplyEdge(cell)
    if Extras then
        if parts.markers then
            local n = Extras.PreviewList(PREVIEW_MARKS, "raid", i)
            Extras.PaintMarkers(parts.markers, "raid", PREVIEW_MARKS, n)
        end
        local aggro = PREVIEW_AGGRO[i]
        Extras.PreviewGroupAggro(parts.aggro, "raid", aggro and aggro[1], aggro and aggro[2])
    end
    PaintPower(cell, m.power * 100, 100, m.powerType)
    PaintNameText(parts, m.name)
    PaintRole(parts, m.role)
    ApplyRangeAlpha(cell.visual, not m.far)
    ShowTick(cell, i == ownIndex)
end

local function NewPreviewCell(host)
    local cell = CreateFrame("Frame", nil, host)
    cell:SetSize(LOOKS.A.w, LOOKS.A.h)
    cell.looks = {}
    local visual = CreateFrame("Frame", nil, cell)
    visual:SetAllPoints(cell)
    cell.visual = visual
    return cell
end

local function BuildPreview()
    if pv.container then return end
    local frame = CreateFrame("Frame", "ForeverSTUwaveRaidPreview", UIParent)
    frame:SetFrameStrata("HIGH")   -- over the party rows if a seat is moved onto them; the editor's handles are above
    frame:SetSize(1, 1)
    local host = CreateFrame("Frame", nil, frame)
    host:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    host:SetScale(FS.Layout.Scale())
    local grid = pv.grid
    grid.content, grid.container = host, frame
    for k = 1, GROUP_COUNT do
        local label = host:CreateFontString(nil, "OVERLAY")
        Theme.ApplyFontGeneric(label, Theme.FONT_ORBITRON, LABEL_SIZE, COLOR_BORDER, "")
        label:SetWordWrap(false)
        label:Hide()
        grid.labels[k] = label
    end
    for i = 1, RAID_SIZE do grid.cells[i] = NewPreviewCell(host) end
    frame:Hide()
    pv.container, pv.content, pv.cells, pv.labels = frame, host, grid.cells, grid.labels
end

local function PreviewNotify()
    for _, fn in ipairs(pv.listeners) do pcall(fn) end
end

-- The size to draw: the saved one when it is one of SIZES, else the default.
function Preview.Size()
    local value = FS.Config.Get(Preview.KEY)
    for _, size in ipairs(Preview.SIZES) do
        if value == size then return size end
    end
    return PREVIEW_DEFAULT
end

-- Re-draws the preview for its size: the look, the group columns, the cells' contents. Hidden cells are left alone.
local function PreviewDraw()
    local n = Preview.Size()
    local id = LookIdFor(n)
    local groups, columns = pv.groups, pv.columns
    for g = 1, GROUP_COUNT do
        for k = #groups[g], 1, -1 do groups[g][k] = nil end
    end
    for k = #columns, 1, -1 do columns[k] = nil end
    for i = 1, n do
        local list = groups[math.floor((i - 1) / GROUP_SIZE) + 1]
        list[#list + 1] = i
    end
    for g = 1, GROUP_COUNT do
        if #groups[g] > 0 then columns[#columns + 1] = g end
    end
    -- The player is member 1, in group 1, the first column.
    PlaceGrid(pv.grid, LOOKS[id], columns, groups, 1, PreviewMember)
    for i = 1, RAID_SIZE do
        local cell = pv.cells[i]
        cell:SetShown(i <= n)
        if i <= n then
            if not (cell.parts and cell.parts.look == id) then LookCell(cell, id) end
            PaintPreviewCell(cell, i, 1)
        end
    end
    pv.size, pv.look = n, id
    SeatGrid(pv.container, Preview.SeatId())
end

-- The layout entry the preview sits at, and the editor's handle moves: one per size ("raid25").
function Preview.SeatId()
    return "raid" .. Preview.Size()
end

function Preview.IsShown()
    return pv.shown
end

function Preview.Look()
    return pv.shown and pv.look or nil
end

-- The preview's top left and size in UIParent units (top left from the screen's bottom left, as GetLeft and GetTop
-- answer), or nil while it is down or has no rect yet.
function Preview.Rect()
    if not pv.shown then return nil end
    local frame = pv.container
    local left, top, width, height = frame:GetLeft(), frame:GetTop(), frame:GetWidth(), frame:GetHeight()
    if type(left) ~= "number" or type(top) ~= "number" or type(width) ~= "number" or type(height) ~= "number" then
        return nil
    end
    return left, top, width, height
end

-- fn() runs after the preview was shown, resized or re-seated (never for a hide), so the editor's handle can follow.
function Preview.OnChange(fn)
    if type(fn) == "function" then pv.listeners[#pv.listeners + 1] = fn end
end

-- False in combat (nothing of the preview runs there), else true once it is up.
function Preview.Show()
    if InCombatLockdown() then return false end
    BuildPreview()
    PreviewDraw()
    pv.container:Show()
    pv.shown = true
    if container then container:SetAlpha(0) end   -- alpha only: the real grid's Show, Hide and anchors are protected
    PreviewNotify()
    return true
end

function Preview.Hide()
    if not pv.shown then return end
    pv.shown = false
    pv.container:Hide()
    if container then container:SetAlpha(1) end
end

-- Saves the size (the same setting the config page edits); the OnChange hook below re-draws a shown preview.
function Preview.SetSize(n)
    for _, size in ipairs(Preview.SIZES) do
        if n == size then return FS.Config.Set(Preview.KEY, size) == true end
    end
    return false
end

-- After a seat change or a rescale: the preview follows its size's entry like the real grid.
function Preview.Reseat()
    if not pv.shown or InCombatLockdown() then return end
    PreviewDraw()
    PreviewNotify()
end

-- A small raid for the config window's Style tab: the real cells and looks (LookCell, PlaceGrid, PaintPreviewCell) on fake
-- members, drawn for the picked layout size (at most two groups of it). Returns { frame, Restyle }.
local STYLE_PREVIEW_MEMBERS = 10
function RaidFrames.NewStylePreview(parent)
    local frame = CreateFrame("Frame", nil, parent)
    frame:SetSize(1, 1)
    local host = CreateFrame("Frame", nil, frame)
    host:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    local grid = { cells = {}, labels = {}, content = host, container = frame }
    for k = 1, GROUP_COUNT do
        local label = host:CreateFontString(nil, "OVERLAY")
        Theme.ApplyFontGeneric(label, Theme.FONT_ORBITRON, LABEL_SIZE, COLOR_BORDER, "")
        label:SetWordWrap(false)
        label:Hide()
        grid.labels[k] = label
    end
    for i = 1, RAID_SIZE do grid.cells[i] = NewPreviewCell(host) end
    local groups, columns = {}, {}
    for g = 1, GROUP_COUNT do groups[g] = {} end
    local function Restyle()
        local n = Preview.Size()
        local shown = math.min(n, STYLE_PREVIEW_MEMBERS)
        local id = LookIdFor(n)
        for g = 1, GROUP_COUNT do for k = #groups[g], 1, -1 do groups[g][k] = nil end end
        for k = #columns, 1, -1 do columns[k] = nil end
        for i = 1, shown do
            local list = groups[math.floor((i - 1) / GROUP_SIZE) + 1]
            list[#list + 1] = i
        end
        for g = 1, GROUP_COUNT do if #groups[g] > 0 then columns[#columns + 1] = g end end
        PlaceGrid(grid, LOOKS[id], columns, groups, 1, PreviewMember)
        for i = 1, RAID_SIZE do
            local cell = grid.cells[i]
            cell:SetShown(i <= shown)
            if i <= shown then
                if not (cell.parts and cell.parts.look == id) then LookCell(cell, id) end
                ApplyCellStyle(cell)
                PaintPreviewCell(cell, i, 1)
            end
        end
    end
    return { frame = frame, Restyle = Restyle }
end

FS.Config.OnChange(Preview.KEY, function()
    if pv.shown and not InCombatLockdown() then
        PreviewDraw()
        PreviewNotify()
    end
end)

-------------------------------------------------------------------------------
-- Blizzard's raid frames
-------------------------------------------------------------------------------

-- CompactRaidFrameContainer (an Edit Mode system) holds the flow unit frames "CompactRaidFrameN" it makes lazily and
-- the group frames "CompactRaidGroupN" (CompactRaidGroup.lua), whose members are their children. Dim, never hide,
-- exactly as PartyFrames dims PartyFrame: DimBlizzardFrame (its events, its child bars' events, alpha 0, mouse off)
-- on the container, its children and theirs, then the mouse off on every descendant (alpha 0 still hit-tests and the
-- mouse does not inherit). Nothing here calls Hide, HookScript, SetScript, SetParent or hooksecurefunc, and nothing
-- writes a Blizzard table, so no taint. The manager tab (CompactRaidFrameManager) is PartyFrames': given back in a
-- raid. Its own handlers still call the container's TryUpdate, so new unit frames appear after a roster change; the
-- sweep runs again one frame after the roster, enter-world and Edit Mode layout events, out of combat only.
local function SilenceBlizzardRaid()
    local blizzard = _G.CompactRaidFrameContainer
    if not blizzard then return end
    blizz.dimmed = true
    local firstError
    local function Step(fn, ...)
        local ok, err = pcall(fn, ...)
        if not ok and not firstError then firstError = err end
    end
    Step(DimBlizzardFrame, blizzard)
    for _, child in ipairs({ blizzard:GetChildren() }) do
        Step(DimBlizzardFrame, child)
        for _, grandchild in ipairs({ child:GetChildren() }) do Step(DimBlizzardFrame, grandchild) end
    end
    Step(DisableMouseTree, blizzard, Shared.MOUSE_SWEEP_DEPTH)
    if firstError then error(firstError, 0) end
end

local function Sweep()
    blizz.queued = false
    if not (flags.started and RaidFrames.IsShown()) then return end
    if InCombatLockdown() then
        blizz.pending = true
        return
    end
    blizz.pending = false
    local ok, err = pcall(SilenceBlizzardRaid)
    if not ok then
        if blizz.reported then return end
        blizz.reported = true   -- LogDegradeOnce prints on every call; the sweep reruns on every roster change
        FS.LogDegradeOnce("raidframes_blizzardsweep",
            "|cffff4488Forever STUwave|r: dimming the game's raid frames failed: " .. tostring(err))
    end
end

local function QueueSweep()
    if blizz.queued then return end
    blizz.queued = true
    After(Sweep)
end

-- The switch applies live: a reflow shows or hides the grid and gives the party rows their place back, and the
-- sweep dims Blizzard's raid frames the first time the switch is on.
FS.Config.OnChange(RaidFrames.CONFIG_KEY, function()
    QueueReflow()
    QueueSweep()
end)

-- PLAYER_LOGIN: FS.Config has resolved the character's profile (its loader registered first), so the saved switch is
-- known; nothing touched Blizzard's frames before this.
do
    local login = CreateFrame("Frame")
    login:RegisterEvent("PLAYER_LOGIN")
    login:SetScript("OnEvent", function()
        flags.started = true
        QueueReflow()
        QueueSweep()
    end)
end

-------------------------------------------------------------------------------
-- Init (secure frame creation, SetAttribute and RegisterUnitWatch run out of combat)
-------------------------------------------------------------------------------

local CELL_EVENTS = { "UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_CONNECTION", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER",
                      "UNIT_DISPLAYPOWER", "UNIT_AURA", "UNIT_NAME_UPDATE", "UNIT_THREAT_SITUATION_UPDATE",
                      "UNIT_THREAT_LIST_UPDATE" }
local CELL_STEPS = {
    UNIT_HEALTH = { "health", UpdateHealth },
    UNIT_MAXHEALTH = { "health", UpdateHealth },
    UNIT_CONNECTION = { "health", UpdateHealth },
    UNIT_POWER_UPDATE = { "power", UpdatePower },
    UNIT_MAXPOWER = { "power", UpdatePower },
    UNIT_DISPLAYPOWER = { "power", UpdatePower },
    UNIT_AURA = { "auras", UpdateAuras },
    UNIT_THREAT_SITUATION_UPDATE = { "aggro", function(cell) if Extras then Extras.UpdateGroupRow(cell) end end },
    UNIT_THREAT_LIST_UPDATE = { "aggro", function(cell) if Extras then Extras.UpdateGroupRow(cell) end end },
}

local function OnCellEvent(events, event)
    local cell = events.cell
    if not flags.active or not cell.parts or not UnitExists(cell.unit) then return end
    if event == "UNIT_NAME_UPDATE" then
        TryStep(cell, "name", UpdateName)
        TryStep(cell, "class", UpdateClass)
        return
    end
    local step = CELL_STEPS[event]
    if step then TryStep(cell, step[1], step[2]) end
end

local function BuildCell(i)
    local unit = "raid" .. i
    local cell = CreateFrame("Button", "ForeverSTUwaveRaidCell" .. i, content, "SecureUnitButtonTemplate")
    cell:SetSize(LOOKS.A.w, LOOKS.A.h)
    cell:RegisterForClicks("AnyUp")
    cell:SetAttribute("unit", unit)
    cell:SetAttribute("*type1", "target")
    cell:SetAttribute("*type2", "togglemenu")
    cell.unit = unit
    cell.looks = {}
    local visual = CreateFrame("Frame", nil, cell)
    visual:SetAllPoints(cell)
    cell.visual = visual
    RegisterUnitWatch(cell)
    -- Unit events for this token only; a name this client does not know is skipped quietly.
    local events = CreateFrame("Frame")
    events.cell = cell
    FS.FrameHelpers.RegisterEvents(events, CELL_EVENTS, unit)
    events:SetScript("OnEvent", OnCellEvent)
    cell.events = events
    return cell
end

local function RescanAuras()
    if not flags.active then return end
    for i = 1, state.n do
        local cell = cells[i]
        if cell.parts and UnitExists(cell.unit) then TryStep(cell, "auras", UpdateAuras) end
    end
end

local function Init()
    container = CreateFrame("Frame", "ForeverSTUwaveRaidContainer", UIParent)
    container:SetSize(1, 1)
    content = CreateFrame("Frame", nil, container)
    content:SetPoint("TOPLEFT", container, "TOPLEFT", 0, 0)
    content:SetScale(FS.Layout.Scale())
    for k = 1, GROUP_COUNT do
        local label = content:CreateFontString(nil, "OVERLAY")
        Theme.ApplyFontGeneric(label, Theme.FONT_ORBITRON, LABEL_SIZE, COLOR_BORDER, "")
        label:SetWordWrap(false)
        label:Hide()
        labels[k] = label
    end
    for i = 1, RAID_SIZE do cells[i] = BuildCell(i) end
    container:Hide()
    realGrid.content, realGrid.container = content, container
    FS.raidContainer, FS.raidContent, FS.raidCells, FS.raidLabels = container, content, cells, labels

    local events = CreateFrame("Frame")
    for _, event in ipairs({ "GROUP_ROSTER_UPDATE", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED",
                             "PLAYER_REGEN_DISABLED", "PLAYER_TARGET_CHANGED" }) do
        events:RegisterEvent(event)
    end
    -- Not confirmed on every build; RegisterEvent throws on a name the client does not know.
    FS.FrameHelpers.RegisterEvents(events, { "PLAYER_ROLES_ASSIGNED", "EDIT_MODE_LAYOUTS_UPDATED" })
    events:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_REGEN_DISABLED" then
            Preview.Hide()   -- nothing protected: its own frames and the real grid's alpha
        elseif event == "PLAYER_REGEN_ENABLED" then
            local reflowed = flags.owed
            if flags.owed then Reflow() end
            if blizz.pending then Sweep() end
            -- Every UNIT_AURA in the fight was held back; the reflow above already scanned.
            if not reflowed then RescanAuras() end
        elseif event == "PLAYER_TARGET_CHANGED" then
            -- the Aggro % reads each member's share on the new target
            if flags.active and Extras and Style and Style.Get("raid", "threatPct") then
                for i = 1, state.n do
                    local cell = cells[i]
                    if cell.parts and UnitExists(cell.unit) then TryStep(cell, "aggro", Extras.UpdateGroupRow) end
                end
            end
        elseif event == "PLAYER_ROLES_ASSIGNED" then
            if flags.active then
                for i = 1, state.n do
                    if cells[i].parts then TryStep(cells[i], "role", UpdateRole) end
                end
            end
        elseif event == "EDIT_MODE_LAYOUTS_UPDATED" then
            QueueSweep()
        else
            QueueReflow()
            QueueSweep()
        end
    end)
    FS.raidEvents = events

    -- The regen rescan can find the aura gate still shut for a moment; the shared retry chain runs it again.
    FS.OnAurasReadable(RescanAuras)

    -- The dispel set is cached in PartyFrames (DISPELS.cache); a spellbook change drops it and rescans.
    if DISPELS.CLASS[Shared.PlayerClass()] then
        local spellEvents = CreateFrame("Frame")
        FS.FrameHelpers.RegisterEvents(spellEvents, Shared.SPELL_EVENTS)
        spellEvents:SetScript("OnEvent", function()
            DISPELS.cache = nil
            RescanAuras()
        end)
    end

    -- A UI scale or display change, or a move or reset of a raid seat (the editor), re-seats the grid through Layout's
    -- re-seat list; this puts it on its pixel again at once out of combat, so it does not show at the unsnapped seat
    -- Layout just wrote, and in step with the roster's size.
    if Style then
        local function Restyle(suffix)
            -- the health text format and the aggro ring read the unit again; markers read its auras
            local readsHealth = suffix == "raidFmt"
            local readsThreat = type(suffix) == "string" and suffix:sub(1, 6) == "threat"
            local readsAuras = type(suffix) == "string" and (suffix:sub(1, 2) == "mk" or suffix == "dispelEdge")
            for _, cell in ipairs(cells) do
                ApplyCellStyle(cell)
                if flags.active and cell.parts and UnitExists(cell.unit) then
                    if readsHealth then TryStep(cell, "health", UpdateHealth) end
                    if readsThreat and Extras and Extras.UpdateGroupRow then TryStep(cell, "aggro", Extras.UpdateGroupRow) end
                end
            end
            for _, cell in ipairs(pv.cells or {}) do ApplyCellStyle(cell) end
            QueueReflow()
            Preview.Reseat()
            -- markers read auras: only while the client allows it, else the old squares hold until the fight ends
            if readsAuras and FS.AurasReadable() then RescanAuras() end
        end
        Style.OnChange("raid", Restyle)
        -- the layout settings are raid.* keys, not bars.raid.*
        for _, key in ipairs({ "raid.scale", "raid.arrange", "raid.perRow", "raid.sort" }) do FS.Config.OnChange(key, Restyle) end
    end

    FS.Layout.OnRescale(function()
        if flags.active then
            if not InCombatLockdown() then Seat() end
            QueueReflow()
        end
        Preview.Reseat()
    end)

    -- One shared range ticker for all forty cells (no per-frame OnUpdate); it does nothing while the grid is down.
    if HAS.UNIT_IN_RANGE then
        if HAS.TICKER then
            C_Timer.NewTicker(Shared.RANGE_TICK_INTERVAL, RefreshRanges)
        else
            local elapsed = 0
            container:SetScript("OnUpdate", function(_, delta)
                elapsed = elapsed + delta
                if elapsed >= Shared.RANGE_TICK_INTERVAL then
                    elapsed = 0
                    RefreshRanges()
                end
            end)
        end
    end

    if flags.started then
        QueueReflow()
        QueueSweep()
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
