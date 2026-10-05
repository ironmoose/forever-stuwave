-- Forever Synthwave: XP bar
--
-- SEGMENTED and DOCKED, on Parker's call ("segmented sounds cool. can we do
-- something so it like is docked to the databar and looks like it is apart").
--
-- The previous version was a 1000px bar floating on its own above the data bar,
-- carrying full panel chrome -- fill, border rails, corner pieces -- on a 13px
-- tall element. That is why its corners kept looking wrong through several
-- rounds: there is no room for a corner at that height, and two stacked bars
-- each with their own chrome read as clutter rather than as a console.
--
-- So it now spans the full screen width like the data bar, sits flush on top of
-- it with no gap, and draws only a TOP rail: the data bar's existing top rail
-- becomes the divider between the two halves. One console strip, split.
--
-- The fill is discrete cells rather than a continuous bar, which is what makes
-- it read as a gauge instead of a second progress bar, and gives the rested
-- range somewhere to live without a second colour fighting the first.
--
-- UnitXP/UnitXPMax are NOT secret on this client and ARE comparable -- checked
-- against the 2026-09-19 secret audit (both rows read `secret=false
-- comparable=true`) -- so the fraction can be computed here directly. Worth
-- stating because the equivalent health values ARE secret, and assuming the
-- same of XP would have meant building this the hard way for no reason.

local _, FS = ...

local FLAT_TEXTURE = FS.Theme.FLAT_TEXTURE
local COLOR_POWER = FS.Theme.COLOR_POWER

-- Mockup values, converted to 0-1.
local TRACK_FILL  = { 0.024, 0.012, 0.071, 0.90 } -- rgba(6,3,18,.9)
local RAIL_COLOR  = { 0.133, 0.878, 1, 0.8 }      -- matches the data bar's rails
local CELL_EMPTY  = { 0.086, 0.055, 0.157, 1 }    -- unlit cell
-- The ramp across the bar. It used to run #7c3aed -> #a855f7, which is two
-- shades of the same violet -- that is why Parker called it plain purple: the
-- bar had no colour journey at all, only a slight lightening nobody can see
-- across 2500 pixels.
--
-- Now it walks the theme's full range, violet through to the magenta the MAIN
-- action bar uses, so how far along a level you are is legible from the HUE
-- alone before you read a single number.
local FILL_STOPS = {
    { 0.486, 0.227, 0.929 },   -- #7c3aed violet
    { 0.659, 0.333, 0.969 },   -- #a855f7 light violet
    { 1.000, 0.180, 0.592 },   -- #ff2e97 magenta
}
-- Rested cells run ahead of the lit ones in cyan, so "how much bonus is banked"
-- is readable at a glance without a second bar or a wash over the fill.
local RESTED_COLOR = { 0.133, 0.878, 1, 0.55 }

local BAR_HEIGHT = 12

-------------------------------------------------------------------------------
-- Pip variants (/fsxp)
-------------------------------------------------------------------------------
-- Parker's verdict on the segmented bar was "not there yet", and every
-- candidate on the table changes how a pip READS rather than what it measures.
-- Comparing them by editing a constant costs a reload per guess, which is the
-- real reason this stalled -- so they ship together and switch live.
--
-- A variant is a set of PROFILE HOOKS, not a pile of booleans: the looks differ
-- in cell count, width, height, texture, colour model and motion, and a flag per
-- difference would not survive the next idea.
--
--   cells         how many of the MAX_CELLS textures this look uses
--   texture       CELL_TEXTURE (leaning) or FLAT_TEXTURE (plain rectangle)
--   gap           pixels between cells
--   widthProfile  f(i, n) -> relative weight; widths are normalised to the bar
--   heightProfile f(i, n) -> 0..1 of the cell height
--   flat          true skips the per-pip vertical gradient (LCARS is flat by
--                 rule, and shading is what makes a flat style read generic)
--   colorMode     "ramp" (violet->magenta across the lit run), "zone" (discrete
--                 bands like a VU meter) or "ribbon" (cools behind the head)
--   trail         cells behind the head that fade, for a visible wake
--   chase         { speed, width } a travelling highlight, ENGINE-SIDE
--   sweep         true makes the chase bounce back and forth instead of looping
--   trace         a thin line linking the cells, lit to the head
--   caps          bright top and bottom edge on each lit cell
--   bands         horizontal slices cut across the whole bar, thickening down
--
-- Parker's brief for this batch: the bar spreads across the whole screen over
-- hours, so the interesting part is the LEADING EDGE and the motion, not the
-- static shape of one cell. Most of these are about what the sweep does.
local MAX_CELLS = 80

local function SpectrumHeight(i, _)
    -- Deterministic, not random: the profile has to be identical every login or
    -- the bar visibly reshuffles on reload. Two out-of-phase sines beat math
    -- .random for that, and read as a frozen EQ rather than noise.
    local a = math.sin(i * 1.7) * 0.5 + 0.5
    local b = math.sin(i * 0.43 + 2.1) * 0.5 + 0.5
    return 0.45 + 0.55 * (a * 0.6 + b * 0.4)
end

local function BarcodeWidth(i, _)
    -- A repeating 7-step pattern of thick and thin, so it reads as encoded data
    -- rather than measurement. Prime-length so it does not line up with the
    -- milestone every 10.
    local pattern = { 1, 0.45, 0.45, 1.6, 0.45, 1, 0.7 }
    return pattern[(i - 1) % #pattern + 1]
end

local VARIANTS = {
    {
        key = "flat", label = "flat (as shipped)",
        note = "bare unlit cells, no top edge",
        barHeight = BAR_HEIGHT,
    },
    {
        key = "slots", label = "slots",
        note = "unlit cells outlined so the empty run reads as slots, every 10th brighter",
        barHeight = BAR_HEIGHT, slotOutline = true, milestoneEvery = 10,
    },
    {
        key = "specular", label = "specular",
        note = "taller, bright top edge on lit cells",
        barHeight = 16, specular = true,
    },
    {
        key = "ribbon", label = "light ribbon (Tron)",
        note = "gaps almost closed, so the lit run is one continuous beam being "
            .. "drawn, white-hot at the head and cooling behind it",
        barHeight = BAR_HEIGHT, gap = 1, texture = FLAT_TEXTURE,
        flat = true, colorMode = "ribbon",
    },
    {
        key = "comet", label = "comet",
        note = "a decaying wake behind the head, so there is visible motion even "
            .. "when the bar has not moved in an hour",
        barHeight = BAR_HEIGHT, trail = 10,
    },
    {
        key = "runway", label = "runway lights",
        note = "a highlight chases along the lit run on a loop; the bar always "
            .. "reads as powered even when XP is static",
        barHeight = BAR_HEIGHT, chase = { speed = 260, width = 90 },
    },
    {
        key = "cylon", label = "cylon sweep",
        note = "the same highlight, bouncing back and forth like KITT's voice box",
        barHeight = BAR_HEIGHT, chase = { speed = 420, width = 130 }, sweep = true,
    },
    {
        key = "eq", label = "spectrum analyser",
        note = "pips at fixed uneven heights like a frozen stereo EQ; kills the "
            .. "progress-bar read completely",
        barHeight = 18, heightProfile = SpectrumHeight,
    },
    {
        key = "caps", label = "capacitor bank",
        note = "fewer, fatter blocks with bright top and bottom caps, like a row "
            .. "of cells charging",
        barHeight = 16, cells = 28, gap = 6, texture = FLAT_TEXTURE,
        flat = true, caps = true, colorMode = "zone",
    },
    {
        key = "barcode", label = "barcode",
        note = "irregular widths in a repeating pattern, so it reads as encoded "
            .. "data rather than a measurement",
        barHeight = BAR_HEIGHT, texture = FLAT_TEXTURE, gap = 2,
        widthProfile = BarcodeWidth, flat = true,
    },
    {
        key = "circuit", label = "circuit trace",
        note = "square pads joined by a thin trace that lights up ahead of them, "
            .. "so current visibly flows into the next pad",
        barHeight = 14, cells = 40, gap = 8, texture = FLAT_TEXTURE,
        flat = true, trace = true, heightProfile = function() return 0.55 end,
    },
    {
        key = "sun", label = "synthwave sun",
        note = "horizontal slices cut across the bar, thickening toward the "
            .. "bottom like the sun over the grid",
        barHeight = 20, texture = FLAT_TEXTURE, gap = 1, flat = true, bands = true,
    },
    {
        key = "perspective", label = "perspective run",
        note = "cells lean harder and compress toward the right, so the row "
            .. "recedes toward a vanishing point",
        barHeight = 16,
        widthProfile = function(i, n) return 1.6 - 1.1 * ((i - 1) / math.max(n - 1, 1)) end,
        heightProfile = function(i, n) return 1 - 0.35 * ((i - 1) / math.max(n - 1, 1)) end,
    },
}

-- Exposed for the headless harness (addons/xpbar-harness.py) and for /dump
-- in game. Read-only by convention; SetVariant and the login restore write activeVariant;
-- those two and Replay write appliedVariant.
FS.xpVariants = VARIANTS

-- activeVariant is the CHOSEN look (saved, listed by /fsxp). appliedVariant is the look
-- whose layout is on the bar right now, and is what V() (every render and layout) reads:
-- they differ only between a /fsxp in combat and the PLAYER_REGEN_ENABLED (or the next
-- out-of-combat PLAYER_ENTERING_WORLD) that applies it.
local activeVariant = 1
local appliedVariant = 1
local function V() return VARIANTS[appliedVariant] or VARIANTS[1] end

-- Faint violet for the unlit slot outline; brighter on a milestone cell.
local SLOT_OUTLINE      = { 0.42, 0.24, 0.72, 0.55 }
local SLOT_OUTLINE_MILE = { 0.58, 0.38, 0.98, 0.90 }
-- The specular edge is additive, so it reads as light on top of whatever
-- colour the ramp put underneath rather than as a grey line.
local SPECULAR_COLOR    = { 1, 0.95, 1, 0.70 }
local SPECULAR_HEIGHT   = 2
local CAP_HEIGHT        = 2      -- capacitor bank: bright top/bottom edge
local TRACE_HEIGHT      = 2      -- circuit trace: the wire linking the pads
-- A level-up lights the whole row at once, and eighty staggered animations read
-- as a mess rather than a flourish. Cap the cascade at a visible burst.
local CASCADE_MAX       = 14
-- Eighty narrow cells rather than fifty wide ones. Fifty across a 2560 screen
-- is a 48px slab each, which reads as a progress bar however it is coloured --
-- Parker's word for the first pass was "boring". Eighty gives a dense run of
-- slashes instead.
local CELL_COUNT = MAX_CELLS   -- textures built; a variant may use fewer
local CELL_GAP = 3
local EDGE_PAD = 2       -- inset from the screen edges, so end cells are not clipped

-- The cells are leaning parallelograms, not rectangles. SetColorTexture can
-- only make a rectangle, so the shape comes from a texture and the colour from
-- SetVertexColor. That one change is what turns this from a progress bar into
-- an arcade power meter.
local CELL_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\cell_slant.tga"

-- The head bloom is a ROUND radial, and that is deliberate after trying the
-- alternative. A slanted, pip-shaped bloom scaled up read as a blowout that
-- swallowed its neighbours -- Parker: "the glow is insane on the leading pip",
-- then "the original glow was perfect". A soft circle at the leading edge
-- reads as a light source; the pip shape at that size reads as a giant pip.
--
-- media/cell_slant_glow.tga is kept on disk: it is the right texture if a
-- pip-shaped halo is ever wanted again, and regenerating it is not free.
local GLOW_ROUND_TEXTURE = "Interface\\AddOns\\ForeverSynthwave\\media\\glow_round.tga"

-- Three separate glows, because one flat wash reads as a lighter colour rather
-- than as light:
--   BLEED  a soft halo above and below the whole lit run
--   HEAD   a radial bloom riding the leading cell, pulsing
--   the head cell itself, near-white and additively doubled
local HEAD_COLOR = { 1, 0.92, 1, 1 }
-- Exactly the first version's numbers. Per-pip halos were tried in between and
-- removed on Parker's call: eighty overlapping ADD glows made the run read as
-- one smeared bar of light and buried the slashes that give it its shape. The
-- pips carry their own interest through colour and shading instead -- see
-- FILL_STOPS and ShadePip -- which is what "they need some love, not more
-- glows" meant.
local HEAD_GLOW_COLOR = { 0.85, 0.55, 1 }
local HEAD_GLOW_SIZE = 34
local HEAD_GLOW_ALPHA = 0.75
local TICK_COLOR = { 0.133, 0.878, 1, 0.35 }
local TICKS_AT = { 0.25, 0.50, 0.75 }

local bar

-- COMBAT. The control deck (Deck.lua) is anchored to this bar and its bag slots are
-- SecureActionButtonTemplate buttons, which makes the bar RESTRICTED in combat: a frame
-- that a protected frame depends on (as an ancestor or as an anchor target) cannot be
-- shown, hidden, resized or re-anchored then (ADDON_ACTION_BLOCKED). Geometry (the bar
-- size and the cell layout that follows from it) and the bar's own shown state are
-- therefore applied out of combat only; a change that arrives in combat sets this flag
-- and PLAYER_REGEN_ENABLED replays it (EnsureCellExtras, LayoutCells, Refresh) at the
-- state current THEN. Recolouring the cell textures (Refresh) stays live in combat.
-- Replay order against DataBar.lua and Deck.lua does not matter: the bar is anchored to
-- the data bar and the deck chassis to the bar, and the engine resolves anchors lazily,
-- so whichever of the three replays first, the stack seats the same once all have.
local pendingReplay = false

-------------------------------------------------------------------------------
-- Blizzard's bars
-------------------------------------------------------------------------------

-- StatusTrackingBarManager owns both containers on this client (all three names
-- confirmed in the 16001 globals dump). Hiding the manager takes the lot.
local function HideBlizzardBars()
    for _, name in ipairs({
        "StatusTrackingBarManager",
        "MainStatusTrackingBarContainer",
        "SecondaryStatusTrackingBarContainer",
    }) do
        local frame = _G[name]
        if frame and frame.Hide then
            pcall(function()
                frame:UnregisterAllEvents()
                frame:Hide()

                -- A one-shot Hide does NOT stick: a UIParent-children probe
                -- showed StatusTrackingBarManager shown again (1192x17) after
                -- we had hidden it, because Blizzard's own layout code calls
                -- Show() on it later. Hook OnShow and put it straight back.
                -- Guarded by a flag so a re-run never stacks hooks.
                if not frame.fsHideHooked then
                    frame:HookScript("OnShow", function(self) self:Hide() end)
                    frame.fsHideHooked = true
                end
            end)
        end
    end
end

-------------------------------------------------------------------------------
-- Data
-------------------------------------------------------------------------------

local function AtMaxLevel()
    local max = GetMaxPlayerLevel and GetMaxPlayerLevel()
    return max and UnitLevel("player") >= max
end

-- Colour of cell `index` (1-based) given how many cells are lit and how far the
-- rested bonus reaches. Kept separate from Refresh so the rules read as rules.
-- Gives one pip its body colour as a vertical gradient rather than a flat tone:
-- brighter along the top edge, falling away toward the bottom. That is the
-- "some love" the pips were missing -- a flat fill has no form, and at this
-- size a gradient is the only shading that survives.
--
-- SetGradient multiplies against the texture, so the pip's slanted alpha is
-- preserved. Feature-detected: without it, a flat tint is the honest fallback.
local function ShadePip(texture, r, g, b, a)
    if texture.SetGradient and CreateColor then
        texture:SetGradient("VERTICAL",
            CreateColor(r * 0.42, g * 0.42, b * 0.42, a),
            CreateColor(math.min(r * 1.3, 1), math.min(g * 1.3, 1), math.min(b * 1.3, 1), a))
    else
        texture:SetVertexColor(r, g, b, a)
    end
end


-- Thousands separators where the client offers them; plain digits otherwise.
local function Commify(value)
    if BreakUpLargeNumbers then
        local ok, text = pcall(BreakUpLargeNumbers, value)
        if ok and text then return text end
    end
    return tostring(value)
end

-------------------------------------------------------------------------------
-- Tooltip
-------------------------------------------------------------------------------

-- OUR tooltip, not GameTooltip. Parker: "it should be a synthwave looking
-- tooltip" -- and GameTooltip would have been the wrong dependency anyway,
-- since Tooltip.lua's skin of it is still a first pass and anything we do here
-- would inherit whatever that is doing on the day.
--
-- Chrome comes from the nine-slice primitives added tonight (slice_fill /
-- slice_border / slice_glow) rather than AddRoundedFill + AddGradientBorder:
-- those composite a panel from rails and corner quads, which is exactly the
-- construction that left seams on the action buttons and stray arcs on the
-- data bar. One texture each cannot.
--
-- The header borrows the chat terminal's language ("synthwave://general") so
-- the two read as the same machine.
local TIP_PAD_X = 12
local TIP_PAD_Y = 9
local TIP_HEADER_H = 16
local TIP_LINE_H = 15
local TIP_BG = { 0.027, 0.012, 0.102, 0.95 }   -- the chat terminal's ground
local TIP_MUTED = { 0.60, 0.56, 0.72, 1 }

local tooltip

local function BuildTooltip()
    if tooltip then return tooltip end

    tooltip = CreateFrame("Frame", "ForeverSynthwaveXPTooltip", UIParent)
    tooltip:SetFrameStrata("TOOLTIP")
    tooltip:Hide()

    FS.Theme.AddSliceTexture(tooltip, FS.Theme.SLICE_FILL_TEXTURE, TIP_BG, "BACKGROUND", -2)

    local glow = FS.Theme.AddSliceTexture(
        tooltip, FS.Theme.SLICE_GLOW_TEXTURE,
        { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.30 },
        "BACKGROUND", -1, -FS.Theme.SLICE_GLOW_PAD)
    FS.Theme.ApplyNineSlice(glow, FS.Theme.SLICE_GLOW_MARGIN)
    glow:SetBlendMode("ADD")

    FS.Theme.AddSliceTexture(
        tooltip, FS.Theme.SLICE_BORDER_TEXTURE,
        { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1 }, "BORDER", 0)

    -- Header strip: a tinted band with the two status dots, same as the chat
    -- terminal's title bar.
    local band = tooltip:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.08)
    local bandInset = FS.Theme.PanelBandInset()
    band:SetPoint("TOPLEFT", tooltip, "TOPLEFT", bandInset, -bandInset)
    band:SetPoint("TOPRIGHT", tooltip, "TOPRIGHT", -bandInset, -bandInset)
    band:SetHeight(TIP_HEADER_H)

    local rule = tooltip:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.30)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    local title = tooltip:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(title, 9, COLOR_POWER)
    title:SetPoint("LEFT", band, "LEFT", 8, 0)
    title:SetText("synthwave://xp")

    tooltip.lines = {}
    for i = 1, 4 do
        local line = tooltip:CreateFontString(nil, "OVERLAY")
        FS.Theme.ApplyMono(line, 11)
        line:SetPoint("TOPLEFT", tooltip, "TOPLEFT",
            TIP_PAD_X, -(TIP_HEADER_H + TIP_PAD_Y + (i - 1) * TIP_LINE_H))
        line:SetJustifyH("LEFT")
        tooltip.lines[i] = line
    end

    return tooltip
end

-- Centres the tooltip horizontally on the CURSOR while keeping it above the
-- bar vertically.
--
-- Not "ANCHOR_CURSOR": the bar sits on the bottom edge of the screen, so a
-- true cursor anchor would open downward, off-screen, and get flipped
-- somewhere unpredictable. Pinning the bottom edge to the bar's top keeps it
-- rising into the screen while still tracking the pip being pointed at.
--
-- GetCursorPosition reports in screen pixels, so it has to be divided by the
-- effective scale to land in the UI units SetPoint expects; skipping that step
-- puts the tooltip wildly off on any scale but 1.
local function SeatTooltipAtCursor(tip, bar_)
    local x = GetCursorPosition()
    local scale = UIParent:GetEffectiveScale()
    if scale and scale > 0 then x = x / scale end

    tip:ClearAllPoints()
    tip:SetPoint("BOTTOM", UIParent, "BOTTOMLEFT", x, (bar_:GetTop() or 0) + 10)
end

local function ShowTooltip(self)
    if AtMaxLevel() then return end

    local current = UnitXP("player") or 0
    local maximum = UnitXPMax("player") or 0
    if maximum <= 0 then return end

    local tip = BuildTooltip()
    local rested = (GetXPExhaustion and GetXPExhaustion()) or 0

    local rows = {
        { ("LEVEL %d"):format(UnitLevel("player") or 0), COLOR_POWER },
        { ("%s / %s"):format(Commify(current), Commify(maximum)), { 1, 1, 1, 1 } },
        { ("%.1f%% -- %s to go"):format(current / maximum * 100,
            Commify(maximum - current)), TIP_MUTED },
    }
    if rested > 0 then
        rows[#rows + 1] = {
            ("RESTED %s (+%.0f%%)"):format(Commify(rested), rested / maximum * 100),
            RESTED_COLOR,
        }
    end

    -- Sized to its content: the rested row comes and goes, and a fixed height
    -- would leave a gap most of the time.
    local widest = 0
    for i, line in ipairs(tip.lines) do
        local row = rows[i]
        if row then
            line:SetText(row[1])
            line:SetTextColor(row[2][1], row[2][2], row[2][3], row[2][4] or 1)
            line:Show()
            widest = math.max(widest, line:GetStringWidth())
        else
            line:Hide()
        end
    end

    tip:SetSize(widest + TIP_PAD_X * 2,
                TIP_HEADER_H + TIP_PAD_Y * 2 + #rows * TIP_LINE_H)

    tip:SetClampedToScreen(true)
    SeatTooltipAtCursor(tip, self)
    tip:Show()

    -- Follow the cursor along the bar. Only runs while hovering, and only
    -- moves a frame, so there is nothing to throttle -- the alternative,
    -- placing it once on enter, leaves it stranded as soon as you slide along
    -- an 80-pip strip.
    self:SetScript("OnUpdate", function(bar_)
        SeatTooltipAtCursor(tip, bar_)
    end)
end

local function HideTooltip(self)
    if tooltip then tooltip:Hide() end
    if self and self.SetScript then self:SetScript("OnUpdate", nil) end
end

-- Cell geometry lives here rather than being duplicated in Build and Rescale,
-- because a variant can change the bar HEIGHT, the cell COUNT, the widths and
-- the texture, and two copies of this drifted apart once already.
local function LayoutCells(initial)
    if not bar or not bar.cells then return end
    -- `initial` is Build's first layout of a brand-new frame nothing depends on yet.
    if not initial and InCombatLockdown() then
        pendingReplay = true
        return
    end

    local screenWidth = UIParent:GetWidth()
    if not screenWidth or screenWidth <= 0 then
        screenWidth = GetScreenWidth() or 1024
    end

    local v = V()
    local n = v.cells or MAX_CELLS
    local gap = v.gap or CELL_GAP
    local texture = v.texture or CELL_TEXTURE
    bar:SetSize(screenWidth, v.barHeight)

    -- Widths come from a WEIGHT profile normalised to the usable width, so a
    -- variant varies cell width without knowing the screen size. Uniform
    -- weights reduce to the original even spacing.
    local weights, total = {}, 0
    for i = 1, n do
        local w = (v.widthProfile and v.widthProfile(i, n)) or 1
        weights[i] = w
        total = total + w
    end

    local usable = screenWidth - EDGE_PAD * 2 - gap * (n - 1)
    local unit = usable / math.max(total, 0.0001)
    local cellHeight = v.barHeight - 4

    bar.cellCentre = bar.cellCentre or {}
    local x = EDGE_PAD

    for index, cell in ipairs(bar.cells) do
        if index > n then
            -- Unused by this variant. Hidden rather than destroyed: textures
            -- cannot be freed, and a later variant may want them back.
            cell:Hide()
            if cell.slot then cell.slot:Hide() end
            if cell.spec then cell.spec:Hide() end
            if cell.capTop then cell.capTop:Hide() cell.capBottom:Hide() end
        else
            local w = weights[index] * unit
            local h = cellHeight * ((v.heightProfile and v.heightProfile(index, n)) or 1)

            cell:Show()
            cell:SetTexture(texture)
            cell:SetSize(w, h)
            cell:ClearAllPoints()
            cell:SetPoint("LEFT", bar, "LEFT", x, 0)

            bar.cellCentre[index] = x + w * 0.5

            if cell.slot then
                cell.slot:SetTexture(texture)
                cell.slot:SetSize(w + 2, h + 2)
                cell.slot:ClearAllPoints()
                cell.slot:SetPoint("CENTER", cell, "CENTER", 0, 0)
            end
            if cell.spec then
                cell.spec:SetSize(w, SPECULAR_HEIGHT)
                cell.spec:ClearAllPoints()
                cell.spec:SetPoint("TOP", cell, "TOP", 0, 0)
            end
            if cell.capTop then
                cell.capTop:SetSize(w, CAP_HEIGHT)
                cell.capTop:ClearAllPoints()
                cell.capTop:SetPoint("TOP", cell, "TOP", 0, 0)
                cell.capBottom:SetSize(w, CAP_HEIGHT)
                cell.capBottom:ClearAllPoints()
                cell.capBottom:SetPoint("BOTTOM", cell, "BOTTOM", 0, 0)
            end

            x = x + w + gap
        end
    end

    bar.rowLeft = EDGE_PAD
    bar.rowRight = x - gap

    -- The trace is ONE line behind the whole row, not one per gap: forty extra
    -- textures to draw something that is visually a single wire.
    if bar.trace then
        bar.trace:ClearAllPoints()
        bar.trace:SetPoint("LEFT", bar, "LEFT", EDGE_PAD, 0)
        bar.trace:SetHeight(TRACE_HEIGHT)
        bar.trace:SetWidth(math.max(bar.rowRight - bar.rowLeft, 1))
        bar.traceLit:ClearAllPoints()
        bar.traceLit:SetPoint("LEFT", bar, "LEFT", EDGE_PAD, 0)
        bar.traceLit:SetHeight(TRACE_HEIGHT)
    end

    -- Sun bands: slices cut ACROSS the bar in the track colour, thickening
    -- toward the bottom. Drawn over the cells, so they subtract from whatever
    -- the cells painted rather than needing per-cell cooperation.
    if bar.bands then
        local y = 0
        for i, band in ipairs(bar.bands) do
            local thickness = 1 + (i - 1) * 0.9
            y = y + thickness + (v.barHeight / (#bar.bands + 1)) * 0.55
            band:ClearAllPoints()
            band:SetPoint("TOPLEFT", bar, "TOPLEFT", 0, -y)
            band:SetPoint("TOPRIGHT", bar, "TOPRIGHT", 0, -y)
            band:SetHeight(thickness)
        end
    end

    for _, tick in ipairs(bar.ticks or {}) do
        tick.texture:SetSize(1, v.barHeight)
        tick.texture:ClearAllPoints()
        tick.texture:SetPoint("LEFT", bar, "LEFT", screenWidth * tick.at, 0)
    end
end

-- Extras are created on FIRST USE, not at build: most variants need none of
-- them, and 80 cells times several textures is a lot of regions to carry for a
-- look that may never be chosen. The nine-slice pass on the action buttons cut
-- region counts for exactly this reason.
local function EnsureCellExtras()
    if not bar or not bar.cells then return end
    local v = V()

    if v.slotOutline or v.specular or v.caps then
        for _, cell in ipairs(bar.cells) do
            if v.slotOutline and not cell.slot then
                local slot = bar:CreateTexture(nil, "BACKGROUND", nil, 1)
                slot:SetTexture(CELL_TEXTURE)
                cell.slot = slot
            end
            if v.specular and not cell.spec then
                local spec = bar:CreateTexture(nil, "ARTWORK", nil, 1)
                spec:SetTexture(CELL_TEXTURE)
                spec:SetBlendMode("ADD")
                cell.spec = spec
            end
            if v.caps and not cell.capTop then
                cell.capTop = bar:CreateTexture(nil, "ARTWORK", nil, 1)
                cell.capTop:SetTexture(FLAT_TEXTURE)
                cell.capTop:SetBlendMode("ADD")
                cell.capBottom = bar:CreateTexture(nil, "ARTWORK", nil, 1)
                cell.capBottom:SetTexture(FLAT_TEXTURE)
                cell.capBottom:SetBlendMode("ADD")
            end
        end
    end

    if v.trace and not bar.trace then
        bar.trace = bar:CreateTexture(nil, "BACKGROUND", nil, 2)
        bar.trace:SetTexture(FLAT_TEXTURE)
        bar.traceLit = bar:CreateTexture(nil, "BACKGROUND", nil, 3)
        bar.traceLit:SetTexture(FLAT_TEXTURE)
    end

    if v.bands and not bar.bands then
        bar.bands = {}
        for i = 1, 5 do
            local band = bar:CreateTexture(nil, "OVERLAY", nil, 2)
            band:SetColorTexture(TRACK_FILL[1], TRACK_FILL[2], TRACK_FILL[3], 1)
            bar.bands[i] = band
        end
    end

    -- ONE travelling highlight, moved by an engine-side Translation, rather
    -- than recolouring eighty textures every frame. The chase looks the same
    -- and costs nothing in Lua.
    if v.chase and not bar.chase then
        bar.chase = bar:CreateTexture(nil, "OVERLAY", nil, 1)
        bar.chase:SetTexture(GLOW_ROUND_TEXTURE)
        bar.chase:SetBlendMode("ADD")
        bar.chaseAnim = bar.chase:CreateAnimationGroup()
        bar.chaseMove = bar.chaseAnim:CreateAnimation("Translation")
        bar.chaseMove:SetOrder(1)
    end
end

-- Colour of one cell. The variant picks the MODEL; the models are shared, so a
-- new look does not mean a new colour function.
local function CellColorFor(v, index, litCells, restedCells, _)
    local mode = v.colorMode or "ramp"

    if index == litCells and litCells > 0 then
        -- The head. Deliberately near-white rather than a brighter violet:
        -- against a violet run, only a hue shift reads as "this is the front".
        return HEAD_COLOR[1], HEAD_COLOR[2], HEAD_COLOR[3], 1
    end

    if index <= litCells then
        if mode == "zone" then
            -- Discrete bands rather than a smooth ramp, the way a VU meter or
            -- an LED bar-graph actually worked. The zones are fractions of the
            -- LIT RUN, so all three are visible at any amount of XP.
            local t = index / math.max(litCells, 1)
            local stop = FILL_STOPS[3]
            if t < 0.6 then
                stop = FILL_STOPS[1]
            elseif t < 0.85 then
                stop = FILL_STOPS[2]
            end
            return stop[1], stop[2], stop[3], 1
        end

        if mode == "ribbon" then
            -- Cools BEHIND the head: hottest at the front, settling to the base
            -- violet over the last stretch, so the run reads as a beam being
            -- drawn rather than a row of cells being filled.
            local behind = litCells - index
            local t = math.min(behind / 18, 1)
            local hot, cool = FILL_STOPS[3], FILL_STOPS[1]
            return hot[1] + (cool[1] - hot[1]) * t,
                   hot[2] + (cool[2] - hot[2]) * t,
                   hot[3] + (cool[3] - hot[3]) * t, 1
        end

        -- "ramp": violet -> magenta across the LIT RUN, not the whole bar. At
        -- 43% of a level you would otherwise only ever reach the violet third
        -- and never see the magenta at all.
        local t = (index - 1) / math.max(litCells - 1, 1)
        local span = t * (#FILL_STOPS - 1)
        local low = math.min(math.floor(span) + 1, #FILL_STOPS - 1)
        local blend = span - (low - 1)
        local a, b = FILL_STOPS[low], FILL_STOPS[low + 1]
        local r = a[1] + (b[1] - a[1]) * blend
        local g = a[2] + (b[2] - a[2]) * blend
        local bl = a[3] + (b[3] - a[3]) * blend

        -- A comet wake: the cells just behind the head stay brighter and fade
        -- back into the run, so there is motion to look at on a bar that may
        -- not move again for an hour.
        if v.trail then
            local behind = litCells - index
            if behind <= v.trail then
                local boost = 1 + 0.9 * (1 - behind / v.trail)
                r = math.min(r * boost, 1)
                g = math.min(g * boost, 1)
                bl = math.min(bl * boost, 1)
            end
        end
        return r, g, bl, 1
    end

    if index <= restedCells then
        return RESTED_COLOR[1], RESTED_COLOR[2], RESTED_COLOR[3], RESTED_COLOR[4]
    end
    return CELL_EMPTY[1], CELL_EMPTY[2], CELL_EMPTY[3], CELL_EMPTY[4]
end

-- Restarts the travelling highlight over the current lit run. Called only when
-- the run CHANGES, never per frame.
local function UpdateChase(v, litCells)
    if not bar.chase then return end
    if not v.chase or litCells < 2 then
        bar.chase:Hide()
        if bar.chaseAnim then bar.chaseAnim:Stop() end
        return
    end

    local from = bar.cellCentre[1] or EDGE_PAD
    local to = bar.cellCentre[litCells] or from
    local distance = math.max(to - from, 1)

    bar.chase:Show()
    bar.chase:SetSize(v.chase.width, v.barHeight * 2.2)
    bar.chase:SetVertexColor(HEAD_GLOW_COLOR[1], HEAD_GLOW_COLOR[2], HEAD_GLOW_COLOR[3], 0.55)
    bar.chase:ClearAllPoints()
    bar.chase:SetPoint("CENTER", bar, "LEFT", from, 0)

    bar.chaseAnim:Stop()
    bar.chaseAnim:SetLooping(v.sweep and "BOUNCE" or "REPEAT")
    bar.chaseMove:SetOffset(distance, 0)
    bar.chaseMove:SetDuration(math.max(distance / v.chase.speed, 0.25))
    bar.chaseAnim:Play()
end

local lastLit = 0

local function Refresh()
    if not bar then return end

    -- Nothing to track at max level (or with XP switched off), so collapse
    -- rather than show a permanently full or empty bar. Show/Hide only when the
    -- state actually differs (this runs on every XP event, kills in combat
    -- included), and a needed change in combat waits for PLAYER_REGEN_ENABLED
    -- because the bar is restricted then (see pendingReplay).
    local wantShown = not (AtMaxLevel() or (IsXPUserDisabled and IsXPUserDisabled()))
    if (bar:IsShown() and true or false) ~= wantShown then
        if InCombatLockdown() then
            pendingReplay = true
            return
        end
        if wantShown then bar:Show() else bar:Hide() end
    end
    if not wantShown then return end

    local current = UnitXP("player") or 0
    local maximum = UnitXPMax("player") or 0
    if maximum <= 0 then maximum = 1 end

    local v = V()
    local n = v.cells or MAX_CELLS

    local fraction = current / maximum
    local litCells = math.floor(fraction * n + 0.0001)

    local rested = (GetXPExhaustion and GetXPExhaustion()) or 0
    local restedCells = litCells
    if rested > 0 then
        restedCells = math.min(math.ceil((current + rested) / maximum * n), n)
    end

    for index = 1, n do
        local cell = bar.cells[index]
        if cell then
            local r, g, b, a = CellColorFor(v, index, litCells, restedCells, n)
            cell.tintR, cell.tintG, cell.tintB, cell.tintA = r, g, b, a
            if v.flat then
                cell:SetVertexColor(r, g, b, a)
            else
                ShadePip(cell, r, g, b, a)
            end

            local lit = index <= litCells

            -- Outline only the UNLIT cells: once a cell is lit its own colour
            -- is the shape, and an outline under it just muddies the ramp.
            if cell.slot then
                if v.slotOutline and not lit then
                    local c = SLOT_OUTLINE
                    if v.milestoneEvery and index % v.milestoneEvery == 0 then
                        c = SLOT_OUTLINE_MILE
                    end
                    cell.slot:SetVertexColor(c[1], c[2], c[3], c[4])
                    cell.slot:Show()
                else
                    cell.slot:Hide()
                end
            end

            -- Specular is the mirror: only on LIT cells, where there is
            -- something for the highlight to be a highlight OF.
            if cell.spec then
                if v.specular and lit then
                    cell.spec:SetVertexColor(SPECULAR_COLOR[1], SPECULAR_COLOR[2],
                                             SPECULAR_COLOR[3], SPECULAR_COLOR[4])
                    cell.spec:Show()
                else
                    cell.spec:Hide()
                end
            end

            if cell.capTop then
                if v.caps and lit then
                    cell.capTop:SetVertexColor(1, 1, 1, 0.55)
                    cell.capBottom:SetVertexColor(1, 1, 1, 0.35)
                    cell.capTop:Show()
                    cell.capBottom:Show()
                else
                    cell.capTop:Hide()
                    cell.capBottom:Hide()
                end
            end
        end
    end

    if bar.trace then
        if v.trace then
            bar.trace:SetVertexColor(CELL_EMPTY[1] * 1.6, CELL_EMPTY[2] * 1.6,
                                     CELL_EMPTY[3] * 1.6, 0.9)
            bar.trace:Show()
            -- The lit half of the wire runs one cell PAST the head, so current
            -- reads as flowing INTO the next pad rather than stopping short.
            local reach = bar.cellCentre[math.min(litCells + 1, n)]
            bar.traceLit:SetVertexColor(FILL_STOPS[3][1], FILL_STOPS[3][2],
                                        FILL_STOPS[3][3], 0.95)
            bar.traceLit:SetWidth(math.max((reach or EDGE_PAD) - EDGE_PAD, 1))
            bar.traceLit:SetShown(litCells > 0)
        else
            bar.trace:Hide()
            bar.traceLit:Hide()
        end
    end

    if bar.bands then
        local want = v.bands and true or false
        for _, band in ipairs(bar.bands) do band:SetShown(want) end
    end

    local head = litCells > 0 and bar.cells[litCells] or nil
    if head then
        bar.headGlow:ClearAllPoints()
        bar.headGlow:SetPoint("CENTER", head, "CENTER", 0, 0)
        bar.headGlow:Show()
        if bar.pulse then bar.pulse:Play() end
    else
        bar.headGlow:Hide()
        if bar.pulse then bar.pulse:Stop() end
    end

    UpdateChase(v, litCells)

    -- The gain moment is the only time anyone LOOKS at this bar on purpose, so
    -- newly lit cells CASCADE in rather than popping. Engine-side alpha ramps
    -- on only the cells that actually changed, staggered by position. Capped,
    -- because a level-up lights the whole row at once and eighty staggered
    -- animations would read as a mess rather than a flourish.
    if litCells > lastLit and lastLit > 0 then
        for index = lastLit + 1, math.min(litCells, lastLit + CASCADE_MAX) do
            local cell = bar.cells[index]
            if cell then
                if not cell.cascade and cell.CreateAnimationGroup then
                    local fade = cell:CreateAnimationGroup()
                    local up = fade:CreateAnimation("Alpha")
                    up:SetFromAlpha(0)
                    up:SetToAlpha(1)
                    up:SetDuration(0.22)
                    up:SetOrder(1)
                    -- The engine's own Alpha animation leaves a SetGradient tint
                    -- un-reasserted once it finishes, so the cell settles on the
                    -- texture's native white. Re-tint from the cell's OWN stored
                    -- values (not values closed over here) since this group is
                    -- reused across future cascades, and re-check flat-ness since
                    -- /fsxp can switch variants live between cascades.
                    up:SetScript("OnFinished", function()
                        if cell.tintR then
                            if V().flat then
                                cell:SetVertexColor(cell.tintR, cell.tintG, cell.tintB, cell.tintA)
                            else
                                ShadePip(cell, cell.tintR, cell.tintG, cell.tintB, cell.tintA)
                            end
                        end
                    end)
                    cell.cascade = fade
                    cell.cascadeUp = up
                end
                if cell.cascade then
                    cell.cascade:Stop()
                    cell.cascadeUp:SetStartDelay(0.045 * (index - lastLit))
                    cell.cascade:Play()
                end
            end
        end
    end
    lastLit = litCells
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build()
    if bar then return bar end

    bar = CreateFrame("Frame", "ForeverSynthwaveXPBar", UIParent)

    -- Width is taken LIVE, not cached at load: UIParent is not fully sized
    -- during addon load (a region dump caught the data bar at 1377 wide on a
    -- 2151-wide screen), which is the same trap the rest of the layout hits.
    local screenWidth = UIParent:GetWidth()
    if not screenWidth or screenWidth <= 0 then
        screenWidth = GetScreenWidth() or 1024
    end
    bar:SetSize(screenWidth, V().barHeight)

    -- DOCKED: flush on top of the data bar, no gap. Falls back to the screen
    -- bottom offset by the data bar's height if that frame is not up yet --
    -- DataBar.lua loads first in the .toc and builds on the same event, so in
    -- practice the anchor is available.
    if FS.dataBar then
        bar:SetPoint("BOTTOM", FS.dataBar, "TOP", 0, 0)
    else
        bar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 20)
    end

    -- Matches the data bar so the two halves sit in one strata and one look.
    bar:SetFrameStrata("HIGH")

    local ground = bar:CreateTexture(nil, "BACKGROUND")
    ground:SetAllPoints(bar)
    ground:SetColorTexture(TRACK_FILL[1], TRACK_FILL[2], TRACK_FILL[3], TRACK_FILL[4])

    -- TOP rail only. The data bar already draws a rail along its own top edge,
    -- and that line now serves as the divider between the two halves -- drawing
    -- a second one here would double it.
    local rail = bar:CreateTexture(nil, "BORDER")
    rail:SetColorTexture(RAIL_COLOR[1], RAIL_COLOR[2], RAIL_COLOR[3], RAIL_COLOR[4])
    rail:SetPoint("TOPLEFT", bar, "TOPLEFT", 0, 0)
    rail:SetPoint("TOPRIGHT", bar, "TOPRIGHT", 0, 0)
    rail:SetHeight(1)

    -- Cells. Created once and recoloured on refresh -- nothing is created,
    -- destroyed or re-anchored per update.
    -- Created here, SIZED AND SEATED by LayoutCells at the end of Build. A
    -- variant can change the bar height, so geometry has to live in one place
    -- that a live switch can re-run.
    bar.cells = {}
    for index = 1, CELL_COUNT do
        local cell = bar:CreateTexture(nil, "ARTWORK")
        cell:SetTexture(CELL_TEXTURE)
        cell:SetVertexColor(CELL_EMPTY[1], CELL_EMPTY[2], CELL_EMPTY[3], 1)
        bar.cells[index] = cell
    end

    -- The bloom riding the leading pip: the same slanted shape, just larger and
    -- brighter. On OVERLAY rather than tucked under like the per-pip halos, so
    -- it spills over the pip itself and past the rails into the data bar below.
    local headGlow = bar:CreateTexture(nil, "OVERLAY")
    headGlow:SetTexture(GLOW_ROUND_TEXTURE)
    headGlow:SetBlendMode("ADD")
    headGlow:SetVertexColor(HEAD_GLOW_COLOR[1], HEAD_GLOW_COLOR[2], HEAD_GLOW_COLOR[3],
                            HEAD_GLOW_ALPHA)
    headGlow:SetSize(HEAD_GLOW_SIZE, HEAD_GLOW_SIZE)
    headGlow:Hide()
    bar.headGlow = headGlow

    -- Breathing, not blinking: a smooth alpha ramp up and back. Engine-side, so
    -- nothing runs per frame in Lua for an effect that is always on screen.
    local pulse = headGlow.CreateAnimationGroup and headGlow:CreateAnimationGroup()
    if pulse then
        pulse:SetLooping("REPEAT")
        local up = pulse:CreateAnimation("Alpha")
        up:SetFromAlpha(0.35); up:SetToAlpha(1); up:SetDuration(0.9); up:SetOrder(1)
        local down = pulse:CreateAnimation("Alpha")
        down:SetFromAlpha(1); down:SetToAlpha(0.35); down:SetDuration(0.9); down:SetOrder(2)
        bar.pulse = pulse
    end

    -- Quarter marks. Above the cells so they stay readable once the bar fills
    -- past them, and kept faint -- they are orientation, not data.
    bar.ticks = {}
    for _, at in ipairs(TICKS_AT) do
        local tick = bar:CreateTexture(nil, "OVERLAY")
        tick:SetColorTexture(TICK_COLOR[1], TICK_COLOR[2], TICK_COLOR[3], TICK_COLOR[4])
        tick:SetSize(1, BAR_HEIGHT)
        tick:SetPoint("LEFT", bar, "LEFT", screenWidth * at, 0)
        bar.ticks[#bar.ticks + 1] = { texture = tick, at = at }
    end

    -- HOVER, not a permanent readout. Parker: "the xp bar doesn't show any
    -- numbers unless i mouse over a pip then it can do like a tooltip" -- so
    -- the bar is pure shape at rest and the figures live in the tooltip.
    --
    -- The whole strip is the hover target rather than individual pips: pips are
    -- Textures, and a Texture cannot receive mouse events. Making each one a
    -- Frame instead would mean eighty frames to serve a tooltip that says the
    -- same thing wherever you point it.
    --
    -- SetPropagateMouseClicks keeps a full-width mouse-enabled strip from
    -- swallowing clicks meant for the world behind it. It is flagged protected,
    -- which restricts Blizzard-owned frames rather than one we made ourselves,
    -- but it is guarded anyway: losing click-through is a far smaller problem
    -- than erroring at load.
    bar:EnableMouse(true)
    if bar.SetPropagateMouseClicks then
        pcall(bar.SetPropagateMouseClicks, bar, true)
    end

    bar:SetScript("OnEnter", ShowTooltip)
    bar:SetScript("OnLeave", HideTooltip)

    EnsureCellExtras()
    LayoutCells(true)

    return bar
end

-- Re-seats and re-sizes everything for a new screen width. The cells are
-- absolutely positioned, so a resize has to move each one; anchoring them to
-- each other instead would ripple rounding error along the row.
local function Rescale()
    if not bar then return end
    if InCombatLockdown() then
        pendingReplay = true
        return
    end
    LayoutCells()
    Refresh()
end

-- PLAYER_REGEN_ENABLED: whatever was held back in combat (a rescale, a variant switch, a
-- show/hide) lands now, from the state current now. PLAYER_ENTERING_WORLD calls it too
-- when a change is still pending out of combat.
local function Replay()
    if not pendingReplay then return end
    pendingReplay = false
    appliedVariant = activeVariant
    EnsureCellExtras()
    LayoutCells()
    Refresh()
end

-- Live variant switch. Rebuilding the frame is not an option (frames cannot be
-- destroyed), and it is not needed: every difference between the variants is
-- geometry plus which extra textures are shown, both of which re-run cheaply.
local function SetVariant(index, announce)
    index = tonumber(index)
    if not index or not VARIANTS[index] then return false end

    activeVariant = index
    ForeverSynthwaveDB = ForeverSynthwaveDB or {}
    ForeverSynthwaveDB.xpVariant = index

    -- A variant changes the bar height and the cell count, which is geometry on a
    -- frame that is restricted in combat: choose and save it now, apply it at regen.
    -- appliedVariant (what rendering reads) follows only when the layout does, so an
    -- XP event in combat never draws the new look over the old geometry.
    local inCombat = InCombatLockdown()
    if inCombat then
        pendingReplay = true
    else
        appliedVariant = index
        EnsureCellExtras()
        LayoutCells()
        Refresh()
    end

    if announce then
        local v = VARIANTS[index]
        print(("|cff22e0ffForeverSynthwave|r: XP pips -> |cffff2e97%d %s|r  (%s)%s")
            :format(index, v.label, v.note, inCombat and " -- applies after combat" or ""))
    end
    return true
end

SLASH_FSXP1 = "/fsxp"
SlashCmdList["FSXP"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")
    if not SetVariant(msg, true) then
        -- Thirteen looks is too many to dump with full descriptions every time,
        -- so the list is labels only and the ACTIVE one gets its note. /fsxp n
        -- prints that variant's note when you land on it anyway.
        print("|cff22e0ffForeverSynthwave|r: /fsxp <1-" .. #VARIANTS
            .. "> switches the XP bar look live.")
        local line = {}
        for i, v in ipairs(VARIANTS) do
            line[#line + 1] = ("%s%d %s|r"):format(
                i == activeVariant and "|cffff2e97" or "|cffaaaaaa", i, v.label)
            if #line == 3 then
                print("  " .. table.concat(line, "   "))
                line = {}
            end
        end
        if #line > 0 then print("  " .. table.concat(line, "   ")) end
        local chosen = VARIANTS[activeVariant]
        print(("  now: |cffff2e97%s|r -- %s"):format(chosen.label, chosen.note))
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local events = CreateFrame("Frame")

-- Deferred to PLAYER_LOGIN for the same reason the action bars are: UIParent is
-- not fully sized during addon load, so anything seated at file scope lands at
-- roughly 64% of its intended size (see Theme.lua's FS.Layout notes).
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(self, event)
    if event == "PLAYER_LOGIN" then
        HideBlizzardBars()

        -- Restore the chosen variant BEFORE the first Build, so the bar is laid
        -- out once at the right height rather than built flat and resized.
        -- ForeverSynthwaveDB is the account-wide store, which is the only one
        -- this client actually restores -- see the .toc header.
        local saved = type(ForeverSynthwaveDB) == "table" and ForeverSynthwaveDB.xpVariant
        if type(saved) == "number" and VARIANTS[saved] then
            activeVariant = saved
            appliedVariant = saved
        end

        if not Build() then return end

        for _, e in ipairs({
            "PLAYER_XP_UPDATE",
            "PLAYER_LEVEL_UP",
            "UPDATE_EXHAUSTION",
            "PLAYER_ENTERING_WORLD",
            "DISABLE_XP_GAIN",
            "ENABLE_XP_GAIN",
            "PLAYER_REGEN_ENABLED",
        }) do
            pcall(self.RegisterEvent, self, e)
        end

        if FS.Layout.OnRescale then
            FS.Layout.OnRescale(Rescale)
        end
    elseif event == "PLAYER_REGEN_ENABLED" then
        Replay()
        return
    elseif event == "PLAYER_ENTERING_WORLD" and pendingReplay and not InCombatLockdown() then
        -- A regen that never arrived (zone change or death across a fight) must not
        -- strand a held-back change: the next world entry out of combat applies it.
        Replay()
        return
    end

    Refresh()
end)
