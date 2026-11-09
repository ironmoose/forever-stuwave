-- Forever STUwave: Damage Meter
-- SKIN ONLY. Blizzard's built-in damage meter (Blizzard_DamageMeter): the DamageMeter owner frame makes one
-- DamageMeterSessionWindow<N> per meter window (DamageMeter:SetupSessionWindow). Each window has a 32 px header
-- texture (`Header`), the session timer, the meter type dropdown (`DamageMeterTypeDropdown`, its `Arrow` and
-- `TypeName`), the session dropdown (`SessionDropdown`, its `Background`, `Arrow` and `SessionName`), the settings
-- dropdown (`SettingsDropdown.Icon`), the minimize button, and a `MinimizeContainer` (the body, hidden while
-- minimized) with the background (`MinimizeContainer.Background`, whose alpha is the player's own background opacity
-- setting), the scroll box of entries, the pinned local player entry and the source window (the per spell breakdown).
--
-- Player: "we also need to skin the damage meters", then "can we pull from the xp bar and make it that way?" and
-- "can we do a gradient for each class kind of like how we have a gradient for xp?". Design study: the damage meter
-- mockup of 2026-11-09, form D (approved). Every name is feature-detected from the 12.1 reference source, so a client
-- whose meter differs keeps the stock look rather than erroring.
--
-- TAINT. In combat the meter's values are secret and Blizzard's own code handles them, so nothing here writes a
-- field on a Blizzard table or registers a callback in one of its registries. Every reach in is hooksecurefunc on an
-- instance method (SetupSessionWindow, SetupEntry, Refresh, UpdateStyle, SetStatusBarColor, SetMinimized), HookScript,
-- and region level work (textures, fonts, colours, anchors) on regions Blizzard already made. Fields are only READ
-- (the colour Blizzard cached, isLocalPlayer), each behind a secret check. Our own state lives in weak tables keyed by
-- the Blizzard object.
--
-- WHAT IT LOOKS LIKE. The chat terminal ("make it look as good as our chat window does"): its body (near black fill,
-- cyan border glow, faint inner wash, scanlines) and its term bar for a header (a full width cyan wash and rule, flat
-- glyph buttons on one centre line). Each row is the XP bar's gauge: the name and number on top in Mononoki, and under
-- them a run of leaning pips. The fill is one vertical class gradient (deep foot, hot top) that the engine crops to the
-- row's value; a gap tile laid over it (dm_cell_tile.tga, one texel per physical pixel) cuts fill and unlit track into
-- pips, so each pip is a single gradient, with a round glow at the fill's edge. The gauge layout is the same whatever bar
-- style is picked in Blizzard's own settings, and its height follows the row height.

local _, FS = ...

local Theme = FS.Theme
if not (Theme and Theme.AddPanelChrome and Theme.SLICE_FILL_TEXTURE and Theme.ApplyNineSlice) then return end
if type(hooksecurefunc) ~= "function" then return end

local FONT = Theme.FONT_MONO
local FLAT = Theme.FLAT_TEXTURE
local ACCENT = Theme.COLOR_POWER          -- cyan: band, rule, type name, ticks
local PINK = Theme.COLOR_HEALTH or ACCENT
local COLOR_BG = Theme.COLOR_BG
local LINE = Theme.COLOR_BAR_BORDER
local MUTED = Theme.COLOR_MUTED
local WHITE = Theme.COLOR_TEXT_WHITE
local IsSecret = FS.IsSecret or function() return false end

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local CELL_TILE = MEDIA .. "dm_cell_tile.tga"
local GLOW_ROUND = MEDIA .. "glow_round.tga"
local GEAR = MEDIA .. "icon_gear.tga"
local CHEVRON = MEDIA .. "glyph_hud_chev.tga"

local MAX_WINDOWS = 8
local TEXT_SIZE = 11                      -- Blizzard's own text scale setting multiplies this
local HEADER_SIZE = 11

-- The gauge, in physical pixels so the pips land on whole pixels at any UI scale. Its height follows the row: what is
-- left under the text, between GAUGE_MIN_PX and GAUGE_MAX_PX (Blizzard's Bar Height setting makes rows taller).
local TILE_PX = 16                        -- dm_cell_tile.tga is 16 x 16: one pip (11 px, leaning) and its 5 px gap
local GAUGE_MAX_PX = 10
local GAUGE_MIN_PX = 6
local TEXT_GAUGE_GAP_PX = 2               -- clear px between the text's foot and the gauge
local GAUGE_BOTTOM = 1                    -- UI units from the row's bottom
local TEXT_TOP = 1                        -- UI units from the row's top
local TEXT_RIGHT = 3
local ICON_GAP = 4                        -- UI units between the class icon and the gauge and name
local CELL_EMPTY = { 0.086, 0.055, 0.157, 1 }   -- the XP bar's unlit cell
local GLOW_SIZE = 14
local GLOW_ALPHA = 0.45
local GLOW_TINT = { 0.85, 0.55, 1 }       -- the XP bar's head bloom, mixed into each class's hot end

-- Per class ramps, deep to hot, each passing through the class colour (the XP bar runs violet to magenta the same way).
-- From the mockup's RAMPS.
local function Hex(h)
    return { tonumber(h:sub(1, 2), 16) / 255, tonumber(h:sub(3, 4), 16) / 255, tonumber(h:sub(5, 6), 16) / 255 }
end
local RAMPS = {
    WARRIOR = { Hex("b0601c"), Hex("ffe0a0") },
    PALADIN = { Hex("d0308a"), Hex("ffd0ee") },
    HUNTER  = { Hex("3c9a1e"), Hex("f0ffa8") },
    ROGUE   = { Hex("e09a00"), Hex("fffcc0") },
    PRIEST  = { Hex("8890c8"), Hex("ffffff") },
    SHAMAN  = { Hex("2040ff"), Hex("40e8ff") },
    MAGE    = { Hex("1a80e0"), Hex("c8faff") },
    WARLOCK = { Hex("6a2cf0"), Hex("e0d0ff") },
    DRUID   = { Hex("e04008"), Hex("ffd050") },
}
local DEFAULT_RAMP = { Hex("7c3aed"), Hex("ff2e97") }  -- the XP bar's own ramp, for a colour we cannot read

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local windows = setmetatable({}, { __mode = "k" })
local entries = setmetatable({}, { __mode = "k" })   -- entry -> its gauge pieces
local classOf                                         -- RAID_CLASS_COLORS colour object -> class token, built on first use

local function SetFont(fs, size, color)
    if not (fs and fs.SetFont) then return end
    if Theme.SetFontChecked then
        Theme.SetFontChecked(fs, FONT, size, "OUTLINE")
    else
        fs:SetFont(FONT, size, "OUTLINE")
    end
    if color and fs.SetTextColor then fs:SetTextColor(color[1], color[2], color[3], color[4] or 1) end
end

local function Edge(parent, layer, sub, color, a)
    local t = parent:CreateTexture(nil, layer, nil, sub)
    t:SetColorTexture(color[1], color[2], color[3], a or 1)
    return t
end

local function Snap(t)
    if t and t.SetSnapToPixelGrid then
        pcall(t.SetSnapToPixelGrid, t, true)
        if t.SetTexelSnappingBias then pcall(t.SetTexelSnappingBias, t, 0) end
    end
end

local function PixelsPerUnit(frame)
    local helpers = FS.FrameHelpers
    local ppu = helpers and helpers.PixelsPerUnit and helpers.PixelsPerUnit(frame)
    if type(ppu) == "number" and ppu > 0 then return ppu end
    return 1
end

-------------------------------------------------------------------------------
-- Class ramps
-------------------------------------------------------------------------------

-- The ramp for the colour object Blizzard handed SetStatusBarColor: a class colour is RAID_CLASS_COLORS[token] itself,
-- so it is found by identity; any other colour (creature, ally, enemy, the default) gets a ramp built from its own RGB.
local function RampFor(color)
    if type(color) ~= "table" then return DEFAULT_RAMP end
    if not classOf and type(RAID_CLASS_COLORS) == "table" then
        classOf = setmetatable({}, { __mode = "k" })
        for token, c in pairs(RAID_CLASS_COLORS) do
            if type(c) == "table" then classOf[c] = token end
        end
    end
    local token = classOf and classOf[color]
    if token and RAMPS[token] then return RAMPS[token] end
    if type(color.GetRGB) ~= "function" then return DEFAULT_RAMP end
    local ok, r, g, b = pcall(color.GetRGB, color)
    if not ok or IsSecret(r) or IsSecret(g) or IsSecret(b) or type(r) ~= "number" then return DEFAULT_RAMP end
    local base = { r, g, b }
    return { Mix(base, { 0, 0, 0 }, 0.35), Mix(base, { 1, 1, 1 }, 0.55) }
end

-- Paints the fill, the glow and the name from `color`. The fill is ONE vertical gradient, deep at the foot and hot at the
-- top, so the gap tile cuts it into pips that are each a single gradient (the XP bar's shaded pips); the name is pink on
-- the player's own row.
local function PaintEntry(entry, color)
    local g = entries[entry]
    if not g then return end
    local ramp = RampFor(color)
    g.ramp = ramp
    local fill = entry.StatusBar:GetStatusBarTexture()
    if fill and fill.SetGradient and type(CreateColor) == "function" then
        local a, b = ramp[1], ramp[2]
        fill:SetVertexColor(1, 1, 1, 1)
        fill:SetGradient("VERTICAL", CreateColor(a[1], a[2], a[3], 1), CreateColor(b[1], b[2], b[3], 1))
    end
    local hot = ramp[2]
    if g.glow then
        local t = Mix(hot, GLOW_TINT, 0.3)
        g.glow:SetVertexColor(t[1], t[2], t[3], GLOW_ALPHA)
    end
    local me = entry.isLocalPlayer
    local name = entry.StatusBar.Name
    if name and name.SetTextColor then
        local mine = not IsSecret(me) and me == true
        local c = mine and PINK or WHITE
        name:SetTextColor(c[1], c[2], c[3], 1)
    end
end

-------------------------------------------------------------------------------
-- Entries (one gauge row)
-------------------------------------------------------------------------------

-- The gap tile follows the gauge, one texel per physical pixel: across its width, and the BOTTOM rows of the tile for
-- its height (so the lean stays half a px per row however tall the gauge is).
local function SeatCells(entry)
    local g = entries[entry]
    local bar = entry.StatusBar
    if not (g and bar and bar.GetWidth) then return end
    local ppu = PixelsPerUnit(bar)
    local w = bar:GetWidth() or 0
    if IsSecret(w) or type(w) ~= "number" then return end
    local wpx = math.floor(w * ppu + 0.5)
    local h = g.gaugePx or GAUGE_MAX_PX
    if g.cells.SetTexCoord then g.cells:SetTexCoord(0, wpx / TILE_PX, (TILE_PX - h) / TILE_PX, 1) end
end

-- The gauge's height in physical px: the row's height less the text and the margins, clamped.
local function GaugePx(entry, name, ppu)
    local rowH = entry.GetHeight and entry:GetHeight() or 0
    if IsSecret(rowH) or type(rowH) ~= "number" or rowH <= 0 then return GAUGE_MAX_PX end
    local textH = 0
    if name and name.GetStringHeight then
        local ok, v = pcall(name.GetStringHeight, name)
        if ok and type(v) == "number" and not IsSecret(v) then textH = v end
    end
    if textH <= 0 then textH = TEXT_SIZE end
    local px = math.floor((rowH - TEXT_TOP - GAUGE_BOTTOM - textH) * ppu) - TEXT_GAUGE_GAP_PX
    return math.max(GAUGE_MIN_PX, math.min(GAUGE_MAX_PX, px))
end

-- Blizzard's UpdateStyle (every style, icon and SetStyle change) re-anchors the bar, name and value and re-atlases the
-- recess; this runs after it and lays the row out as the gauge: name and number along the top, the gauge along the
-- bottom, from the icon's right edge when bar icons are on.
local function LayOut(entry)
    local bar = entry.StatusBar
    if not (bar and entries[entry]) then return end
    local name, value = bar.Name, bar.Value
    local ppu = PixelsPerUnit(entry)

    -- Past the class icon when Blizzard shows one. Its frame has a fixed 24 x 24 size in the template; the texture
    -- GetIconAttachmentAnchor names reads 0 wide before the first layout pass, which put the gauge under the icon.
    local left = 0
    local icon = entry.Icon
    if icon and icon.IsShown and icon:IsShown() then
        local w = icon.GetWidth and icon:GetWidth() or 0
        if IsSecret(w) or type(w) ~= "number" or w <= 0 then w = 24 end
        left = w + ICON_GAP
    end

    local g = entries[entry]
    g.gaugePx = GaugePx(entry, name, ppu)
    bar:ClearAllPoints()
    bar:SetPoint("BOTTOMLEFT", entry, "BOTTOMLEFT", left, GAUGE_BOTTOM)
    bar:SetPoint("BOTTOMRIGHT", entry, "BOTTOMRIGHT", -TEXT_RIGHT, GAUGE_BOTTOM)
    bar:SetHeight(g.gaugePx / ppu)

    if value then
        value:ClearAllPoints()
        value:SetPoint("TOPRIGHT", entry, "TOPRIGHT", -TEXT_RIGHT, -TEXT_TOP)
    end
    if name then
        name:ClearAllPoints()
        name:SetPoint("TOPLEFT", entry, "TOPLEFT", left + 1, -TEXT_TOP)
        if value then name:SetPoint("RIGHT", value, "LEFT", -8, 0) end
    end

    local bg, edge = bar.Background, bar.BackgroundEdge
    if bg then
        bg:ClearAllPoints()
        bg:SetAllPoints(bar)
        if bg.SetColorTexture then bg:SetColorTexture(CELL_EMPTY[1], CELL_EMPTY[2], CELL_EMPTY[3], CELL_EMPTY[4]) end
    end
    if edge and edge.SetColorTexture then edge:SetColorTexture(0, 0, 0, 0) end

    SeatCells(entry)
end

-- A throw in the layout is reported (FS's error log keeps it) but never stops the hooks or the rest of the skin.
local function ApplyLayout(entry)
    local ok, err = pcall(LayOut, entry)
    if not ok and type(geterrorhandler) == "function" then geterrorhandler()(err) end
end

local function SkinEntry(entry)
    if not entry or entries[entry] then return end
    local bar = entry.StatusBar
    if not (bar and bar.SetStatusBarTexture and bar.GetStatusBarTexture and bar.CreateTexture) then return end
    local g = {}
    entries[entry] = g

    bar:SetStatusBarTexture(FLAT)
    local fill = bar:GetStatusBarTexture()

    -- the gap tile over fill and track, one texel per physical pixel, repeated across the gauge
    g.cells = bar:CreateTexture(nil, "OVERLAY", nil, -6)
    g.cells:SetTexture(CELL_TILE, "REPEAT", "CLAMP", "NEAREST")
    g.cells:SetAllPoints(bar)
    Snap(g.cells)

    -- the bloom rides the fill's right edge, which the engine places from the value
    if fill then
        g.glow = bar:CreateTexture(nil, "OVERLAY", nil, -4)
        g.glow:SetTexture(GLOW_ROUND)
        g.glow:SetBlendMode("ADD")
        g.glow:SetSize(GLOW_SIZE, GLOW_SIZE)
        g.glow:SetPoint("CENTER", fill, "RIGHT", 0, 0)
    end

    -- the class or spell icon gets a 1 px frame
    local icon = entry.Icon
    if icon and icon.CreateTexture then
        local frame = Edge(icon, "BACKGROUND", -8, LINE)
        frame:SetPoint("TOPLEFT", icon, "TOPLEFT", -1, 1)
        frame:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", 1, -1)
    end

    SetFont(bar.Name, TEXT_SIZE, WHITE)
    SetFont(bar.Value, TEXT_SIZE, WHITE)

    if type(entry.UpdateStyle) == "function" then hooksecurefunc(entry, "UpdateStyle", ApplyLayout) end
    if type(entry.SetStatusBarColor) == "function" then hooksecurefunc(entry, "SetStatusBarColor", PaintEntry) end
    if type(bar.HookScript) == "function" then pcall(bar.HookScript, bar, "OnSizeChanged", function() SeatCells(entry) end) end
    if type(entry.HookScript) == "function" then pcall(entry.HookScript, entry, "OnSizeChanged", function() ApplyLayout(entry) end) end

    -- Blizzard's own cached colour (a read; it is the RAID_CLASS_COLORS object or one of its constants)
    PaintEntry(entry, entry.statusBarColor)
    ApplyLayout(entry)
end

local function SkinEntriesOf(owner)
    if type(owner.ForEachEntryFrame) ~= "function" then return end
    pcall(owner.ForEachEntryFrame, owner, SkinEntry)
end

-------------------------------------------------------------------------------
-- Title bar (the chat terminal's term bar)
-------------------------------------------------------------------------------

-- Player: "make it look as good as our chat window does". So the header IS the chat window's term bar
-- (ChatTermBar.lua): a cyan wash and a brighter bottom rule, one unit inside the border, the full width, and quiet flat
-- glyphs (no plates) that come up to full alpha under the mouse; pink for minimise, cyan for the rest.
local BAR_WASH = 0.08                      -- the chat term bar's wash and rule
local BAR_RULE = 0.30
local BAR_INSET = 1
local GLYPH_SIZE = 16                      -- the chat title buttons
local GLYPH_GAP = 4
local GLYPH_ALPHA = 0.85
local GLYPH_ALPHA_HOVER = 1.00
local GLYPH_PAD_R = 6                      -- the minimise glyph's gap from the right border
local ICON_MINIMIZE = MEDIA .. "icon_minimize.tga"
local ICON_MAXIMIZE = MEDIA .. "icon_maximize.tga"
local GREEN = { 0.22, 1, 0.08, 1 }         -- the chat term bar's restore green

local function Hold(region)
    if not region then return end
    if FS.HeldArt and FS.HeldArt.Hold then FS.HeldArt.Hold(region) elseif region.SetAlpha then region:SetAlpha(0) end
end

-- A flat glyph on a Blizzard button (a texture region on it: no field written), idle at GLYPH_ALPHA, full on hover.
local function Glyph(button, texture, color, flip)
    local t = button:CreateTexture(nil, "OVERLAY", nil, 3)
    t:SetTexture(texture)
    t:SetSize(GLYPH_SIZE, GLYPH_SIZE)
    t:SetPoint("CENTER", button, "CENTER", 0, 0)
    if flip then t:SetTexCoord(0, 1, 1, 0) end
    local state = { color = color, hover = false }
    local function paint()
        local c = state.color
        t:SetVertexColor(c[1], c[2], c[3], state.hover and GLYPH_ALPHA_HOVER or GLYPH_ALPHA)
    end
    paint()
    if type(button.HookScript) == "function" then
        pcall(button.HookScript, button, "OnEnter", function() state.hover = true; paint() end)
        pcall(button.HookScript, button, "OnLeave", function() state.hover = false; paint() end)
    end
    return t, state, paint
end

-- The bar's height: Blizzard's header (32, the rows start under it) less the inset.
local function BarHeight(window)
    local h = window.Header and window.Header.GetHeight and window.Header:GetHeight() or 32
    if type(h) ~= "number" or h <= 0 then h = 32 end
    return h - BAR_INSET
end

local function SkinHeader(window)
    local header = window.Header
    if not header then return end
    header:SetAlpha(0)
    local barH = BarHeight(window)
    local wash = Edge(window, "BACKGROUND", 2, ACCENT, BAR_WASH)
    wash:SetPoint("TOPLEFT", window, "TOPLEFT", BAR_INSET, -BAR_INSET)
    wash:SetPoint("TOPRIGHT", window, "TOPRIGHT", -BAR_INSET, -BAR_INSET)
    wash:SetHeight(barH)
    local rule = Edge(window, "BACKGROUND", 3, ACCENT, BAR_RULE)
    rule:SetPoint("BOTTOMLEFT", wash, "BOTTOMLEFT")
    rule:SetPoint("BOTTOMRIGHT", wash, "BOTTOMRIGHT")
    rule:SetHeight(1)
end

-- Seats the three right hand controls on one centre line, the bar's, minimise against the right border and each next
-- one GLYPH_GAP to its left. Blizzard only ever sets the session dropdown's WIDTH after this (its name length), so the
-- anchors hold. Anchors and sizes on Blizzard's own (unprotected) buttons; no field is written.
local function SeatHeaderButtons(window)
    local cy = -(BAR_INSET + BarHeight(window) / 2)
    local minimize, settings, session = window.MinimizeButton, window.SettingsDropdown, window.SessionDropdown
    local right = nil
    if minimize then
        minimize:ClearAllPoints()
        minimize:SetSize(GLYPH_SIZE, GLYPH_SIZE)
        minimize:SetPoint("CENTER", window, "TOPRIGHT", -(GLYPH_PAD_R + GLYPH_SIZE / 2), cy)
        right = minimize
    end
    if settings then
        settings:ClearAllPoints()
        settings:SetSize(GLYPH_SIZE, GLYPH_SIZE)
        if right then
            settings:SetPoint("RIGHT", right, "LEFT", -GLYPH_GAP, 0)
        else
            settings:SetPoint("CENTER", window, "TOPRIGHT", -(GLYPH_PAD_R + GLYPH_SIZE / 2), cy)
        end
        right = settings
    end
    if session and right then
        session:ClearAllPoints()
        session:SetHeight(GLYPH_SIZE)
        session:SetPoint("RIGHT", right, "LEFT", -GLYPH_GAP * 2, 0)
    end
end

local function SkinHeaderButtons(window)
    local typeDropdown = window.DamageMeterTypeDropdown
    if typeDropdown then
        Hold(typeDropdown.Arrow)
        if typeDropdown.Arrow and typeDropdown.CreateTexture then
            local chev = typeDropdown:CreateTexture(nil, "OVERLAY", nil, 3)
            chev:SetTexture(CHEVRON)
            chev:SetTexCoord(0, 1, 1, 0)   -- the file points up
            chev:SetSize(14, 14)
            chev:SetPoint("CENTER", typeDropdown.Arrow, "CENTER", 0, 2)
            chev:SetVertexColor(ACCENT[1], ACCENT[2], ACCENT[3], GLYPH_ALPHA)
        end
    end

    local session = window.SessionDropdown
    if session then
        Hold(session.Background)
        Hold(session.Arrow)
    end

    local settings = window.SettingsDropdown
    if settings and settings.CreateTexture then
        Hold(settings.Icon)
        Glyph(settings, GEAR, ACCENT)
    end

    local minimize = window.MinimizeButton
    if minimize and minimize.CreateTexture then
        if FS.HeldArt and FS.HeldArt.HoldButton then FS.HeldArt.HoldButton(minimize) end
        local minimized = false
        if type(window.IsMinimized) == "function" then
            local ok, m = pcall(window.IsMinimized, window)
            minimized = ok and not IsSecret(m) and m == true
        end
        local tex, state, paint = Glyph(minimize, ICON_MINIMIZE, PINK)
        -- minimised, it reads as restore: the chat bar's maximise glyph in its green
        local function follow(isMinimized)
            tex:SetTexture(isMinimized and ICON_MAXIMIZE or ICON_MINIMIZE)
            state.color = isMinimized and GREEN or PINK
            paint()
        end
        follow(minimized)
        if type(window.SetMinimized) == "function" then
            hooksecurefunc(window, "SetMinimized", function(_, isMinimized) follow(isMinimized and true or false) end)
        end
    end

    SeatHeaderButtons(window)
end

-------------------------------------------------------------------------------
-- Windows
-------------------------------------------------------------------------------

-- The body is the chat terminal's: its near black fill and cyan border glow (the panel chrome), the faint inner cyan
-- wash, and the scanline scrim tiled one texel per 4 px. Blizzard's own background (the opacity setting's) is held.
local TERM_BG = { 0.027, 0.012, 0.102, 0.85 }
local INNER_WASH = 0.04
local SCANLINE = MEDIA .. "scanline.tga"
local SCANLINE_ALPHA = 0.4
local SCANLINE_TILE = 4

local function SeatScanline(scan, frame)
    local w = frame.GetWidth and frame:GetWidth() or 0
    local h = frame.GetHeight and frame:GetHeight() or 0
    if type(w) ~= "number" or type(h) ~= "number" or w <= 0 or h <= 0 then return end
    scan:SetTexCoord(0, w / SCANLINE_TILE, 0, h / SCANLINE_TILE)
end

local function SkinBody(container)
    Hold(container.Background)
    Theme.AddPanelChrome(container, { fillColor = TERM_BG, accent = ACCENT })
    if Theme.AddRoundedFill then
        Theme.AddRoundedFill(container, { ACCENT[1], ACCENT[2], ACCENT[3], INNER_WASH }, Theme.SLICE_MARGIN)
    end
    local scan = container:CreateTexture(nil, "BORDER", nil, -8)
    scan:SetTexture(SCANLINE, "REPEAT", "REPEAT")
    scan:SetPoint("TOPLEFT", container, "TOPLEFT", BAR_INSET, -BAR_INSET)
    scan:SetPoint("BOTTOMRIGHT", container, "BOTTOMRIGHT", -BAR_INSET, BAR_INSET)
    scan:SetAlpha(SCANLINE_ALPHA)
    SeatScanline(scan, container)
    if type(container.HookScript) == "function" then
        pcall(container.HookScript, container, "OnSizeChanged", function(self) SeatScanline(scan, self) end)
    end
end

local function SkinSourceWindow(source)
    if not source or windows[source] then return end
    windows[source] = true
    local bg = source.Background
    if bg and bg.SetTexture then
        bg:SetTexture(Theme.SLICE_FILL_TEXTURE)
        Theme.ApplyNineSlice(bg, Theme.SLICE_MARGIN)
        bg:SetVertexColor(COLOR_BG[1], COLOR_BG[2], COLOR_BG[3], 1)
    end
    local fill = Theme.AddPanelChrome(source, { fillColor = COLOR_BG, accent = ACCENT })
    if fill then fill:Hide() end
    SkinEntriesOf(source)
    if type(source.Refresh) == "function" then
        hooksecurefunc(source, "Refresh", function(self) SkinEntriesOf(self) end)
    end
end

local function SkinWindow(window)
    if not window or windows[window] then return end
    windows[window] = true

    local container = window.MinimizeContainer
    if container then
        SkinBody(container)
        SetFont(container.NotActive, HEADER_SIZE, MUTED)
        SkinEntry(container.LocalPlayerEntry)
        SkinSourceWindow(container.SourceWindow)
    end
    SkinHeader(window)
    SkinHeaderButtons(window)

    SetFont(window.SessionTimer, HEADER_SIZE, Theme.COLOR_AMBER or WHITE)
    local typeDropdown = window.DamageMeterTypeDropdown
    if typeDropdown then SetFont(typeDropdown.TypeName, HEADER_SIZE + 1, ACCENT) end
    local session = window.SessionDropdown
    if session then SetFont(session.SessionName, HEADER_SIZE, WHITE) end

    SkinEntriesOf(window)
    if type(window.SetupEntry) == "function" then
        hooksecurefunc(window, "SetupEntry", function(_, frame) SkinEntry(frame) end)
    end
end

local function SkinExisting()
    for i = 1, MAX_WINDOWS do
        local window = _G["DamageMeterSessionWindow" .. i]
        if window then SkinWindow(window) end
    end
end

local owner = _G.DamageMeter
if type(owner) == "table" and type(owner.SetupSessionWindow) == "function" then
    hooksecurefunc(owner, "SetupSessionWindow", function(_, _, windowData)
        local window = type(windowData) == "table" and windowData.sessionWindow
        if window then SkinWindow(window) end
    end)
end
SkinExisting()

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:SetScript("OnEvent", SkinExisting)

FS.DamageMeterSkin = { SkinWindow = SkinWindow, SkinEntry = SkinEntry, RampFor = RampFor, RAMPS = RAMPS }
