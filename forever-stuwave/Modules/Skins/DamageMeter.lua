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
-- WHAT IT LOOKS LIKE. The body wears the STUwave cut panel (Blizzard's background becomes our nine sliced fill, so the
-- opacity setting still drives it) under a cyan header band. Each row is the XP bar's gauge: the name and number on top
-- in Mononoki, and under them a run of leaning cells. The fill is a per class gradient, deep to hot, that the engine
-- crops to the row's value; a tile laid over it (dm_cell_tile.tga, one texel per physical pixel) cuts the fill and the
-- unlit track into cells and shades each one. The fill's leading edge burns white with a round glow, and faint cyan
-- ticks mark the quarters. The gauge layout is the same whatever bar style is picked in Blizzard's own settings.

local _, FS = ...

local Theme = FS.Theme
if not (Theme and Theme.AddPanelChrome and Theme.SLICE_FILL_TEXTURE and Theme.ApplyNineSlice) then return end
if type(hooksecurefunc) ~= "function" then return end

local FONT = Theme.FONT_MONO
local FLAT = Theme.FLAT_TEXTURE
local ACCENT = Theme.COLOR_POWER          -- cyan: band, rule, type name, ticks
local VIOLET = Theme.COLOR_BORDER or ACCENT
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
local BAND_ALPHA = 0.14
local RULE_ALPHA = 0.55
local TEXT_SIZE = 11                      -- Blizzard's own text scale setting multiplies this
local HEADER_SIZE = 11

-- The gauge, in physical pixels so the cells land on whole pixels at any UI scale.
local TILE_PX = 16                        -- dm_cell_tile.tga is 16 x 16: one cell (13 px, leaning) and its 3 px gap
local GAUGE_PX = 10                       -- the tile rows the gauge shows (the rest of the file is padding)
local GAUGE_BOTTOM = 2                    -- UI units from the row's bottom
local TEXT_TOP = 2                        -- UI units from the row's top
local TEXT_RIGHT = 3
local CELL_EMPTY = { 0.086, 0.055, 0.157, 1 }   -- the XP bar's unlit cell
local HEAD_PX = 2                         -- the white hot leading edge
local HEAD_ALPHA = 0.85
local GLOW_SIZE = 16
local GLOW_ALPHA = 0.55
local GLOW_TINT = { 0.85, 0.55, 1 }       -- the XP bar's head bloom, mixed into each class's hot end
local TICKS_AT = { 0.25, 0.5, 0.75 }
local TICK_ALPHA = 0.35

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

-- Paints the fill gradient, the leading edge and the glow from `color`, and the name pink on the player's own row.
local function PaintEntry(entry, color)
    local g = entries[entry]
    if not g then return end
    local ramp = RampFor(color)
    g.ramp = ramp
    local fill = entry.StatusBar:GetStatusBarTexture()
    if fill and fill.SetGradient and type(CreateColor) == "function" then
        local a, b = ramp[1], ramp[2]
        fill:SetVertexColor(1, 1, 1, 1)
        fill:SetGradient("HORIZONTAL", CreateColor(a[1], a[2], a[3], 1), CreateColor(b[1], b[2], b[3], 1))
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

-- The cells and the ticks follow the gauge's width, counted in physical pixels.
local function SeatCells(entry)
    local g = entries[entry]
    local bar = entry.StatusBar
    if not (g and bar and bar.GetWidth) then return end
    local ppu = PixelsPerUnit(bar)
    local w = bar:GetWidth() or 0
    if IsSecret(w) or type(w) ~= "number" then return end
    local wpx = math.floor(w * ppu + 0.5)
    if g.cells.SetTexCoord then g.cells:SetTexCoord(0, wpx / TILE_PX, 0, GAUGE_PX / TILE_PX) end
    for i, q in ipairs(TICKS_AT) do
        local t = g.ticks[i]
        t:ClearAllPoints()
        t:SetPoint("TOPLEFT", bar, "TOPLEFT", math.floor(wpx * q) / ppu, 1 / ppu)
        t:SetSize(1 / ppu, (GAUGE_PX + 2) / ppu)
    end
end

-- Blizzard's UpdateStyle (every style, icon and SetStyle change) re-anchors the bar, name and value and re-atlases the
-- recess; this runs after it and lays the row out as the gauge: name and number along the top, the gauge along the
-- bottom, from the icon's right edge when bar icons are on.
local function LayOut(entry)
    local bar = entry.StatusBar
    if not (bar and entries[entry]) then return end
    local name, value = bar.Name, bar.Value
    local ppu = PixelsPerUnit(entry)

    local left = 0
    if type(entry.GetIconAttachmentAnchor) == "function" then
        local ok, _, rel, _, x = pcall(entry.GetIconAttachmentAnchor, entry)
        if ok then
            left = type(x) == "number" and x or 0
            if rel ~= entry and type(rel) == "table" and rel.GetWidth then left = left + (rel:GetWidth() or 0) end
        end
    end

    bar:ClearAllPoints()
    bar:SetPoint("BOTTOMLEFT", entry, "BOTTOMLEFT", left, GAUGE_BOTTOM)
    bar:SetPoint("BOTTOMRIGHT", entry, "BOTTOMRIGHT", -TEXT_RIGHT, GAUGE_BOTTOM)
    bar:SetHeight(GAUGE_PX / ppu)

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
    local g = { ticks = {} }
    entries[entry] = g

    bar:SetStatusBarTexture(FLAT)
    local fill = bar:GetStatusBarTexture()

    -- the white hot leading edge and its bloom ride the fill's right edge, which the engine places from the value
    if fill then
        g.head = Edge(bar, "ARTWORK", 3, WHITE, HEAD_ALPHA)
        g.head:SetBlendMode("ADD")
        g.head:SetPoint("TOPRIGHT", fill, "TOPRIGHT")
        g.head:SetPoint("BOTTOMRIGHT", fill, "BOTTOMRIGHT")
        g.head:SetWidth(HEAD_PX / PixelsPerUnit(bar))
        Snap(g.head)
    end

    -- the cell tile over fill and track, one texel per physical pixel, repeated across the gauge
    g.cells = bar:CreateTexture(nil, "OVERLAY", nil, -6)
    g.cells:SetTexture(CELL_TILE, "REPEAT", "CLAMP", "NEAREST")
    g.cells:SetAllPoints(bar)
    Snap(g.cells)

    for i = 1, #TICKS_AT do
        local t = Edge(bar, "OVERLAY", -5, ACCENT, TICK_ALPHA)
        Snap(t)
        g.ticks[i] = t
    end

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

    -- Blizzard's own cached colour (a read; it is the RAID_CLASS_COLORS object or one of its constants)
    PaintEntry(entry, entry.statusBarColor)
    ApplyLayout(entry)
end

local function SkinEntriesOf(owner)
    if type(owner.ForEachEntryFrame) ~= "function" then return end
    pcall(owner.ForEachEntryFrame, owner, SkinEntry)
end

-------------------------------------------------------------------------------
-- Header keys
-------------------------------------------------------------------------------

local function Hold(region)
    if not region then return end
    if FS.HeldArt and FS.HeldArt.Hold then FS.HeldArt.Hold(region) elseif region.SetAlpha then region:SetAlpha(0) end
end

-- A STUwave key drawn under a Blizzard dropdown: our own frame (no mouse, so every click is still Blizzard's), a child of
-- the WINDOW one level below the dropdown, so the dropdown's own text (the session name) draws on top of it. A cut plate,
-- ring and halo in `accent`, and an optional glyph texture. Hover lifts the ring and glyph.
local function Key(window, button, accent, size, glyph, flip)
    if not (button and type(CreateFrame) == "function") then return nil end
    local key = CreateFrame("Frame", nil, window)
    if key.EnableMouse then key:EnableMouse(false) end
    if key.SetFrameLevel and button.GetFrameLevel and window.GetFrameLevel then
        local level = math.max((button:GetFrameLevel() or 1) - 1, window:GetFrameLevel() or 0)
        key:SetFrameLevel(level)
    end
    if size then
        key:SetSize(size, size)
        key:SetPoint("CENTER", button, "CENTER", 0, 0)
    else
        key:SetAllPoints(button)
    end
    local face = Theme.AddCutSliceFill and Theme.AddCutSliceFill(key, Theme.COLOR_BUTTON_INK or COLOR_BG, 3)
    local skin = Theme.SkinButton and Theme.SkinButton(key, { borderColor = accent, chamfer = 3, glowAlpha = 0.35 })
    local ring = skin and skin.border and skin.border.ring
    local mark
    if glyph then
        mark = key:CreateTexture(nil, "OVERLAY", nil, 3)
        mark:SetTexture(glyph)
        mark:SetSize(size and size - 4 or 12, size and size - 4 or 12)
        mark:SetPoint("CENTER", key, "CENTER", 0, 0)
        if flip then mark:SetTexCoord(0, 1, 1, 0) end
        mark:SetVertexColor(accent[1], accent[2], accent[3], 0.85)
    end
    local function paint(hover)
        if ring then ring:SetVertexColor(accent[1], accent[2], accent[3], hover and 1 or 0.7) end
        if mark then
            local c = hover and Mix(accent, WHITE, 0.35) or accent
            mark:SetVertexColor(c[1], c[2], c[3], hover and 1 or 0.85)
        end
    end
    paint(false)
    if type(button.HookScript) == "function" then
        pcall(button.HookScript, button, "OnEnter", function() paint(true) end)
        pcall(button.HookScript, button, "OnLeave", function() paint(false) end)
    end
    return key, face
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
            chev:SetVertexColor(ACCENT[1], ACCENT[2], ACCENT[3], 1)
        end
    end

    local session = window.SessionDropdown
    if session then
        Hold(session.Background)
        Hold(session.Arrow)
        Key(window, session, VIOLET)
    end

    local settings = window.SettingsDropdown
    if settings then
        Hold(settings.Icon)
        Key(window, settings, VIOLET, 16, GEAR)
    end

    local minimize = window.MinimizeButton
    local skins = FS.ButtonSkins
    if minimize and skins and skins.SkinCloseButton and type(CreateFrame) == "function" then
        -- the plate seats itself 5 in and 3 down from its anchor; this spot keeps it where Blizzard's button sat
        local seat = CreateFrame("Frame", nil, window)
        seat:SetSize(1, 1)
        seat:SetPoint("TOPRIGHT", window.Header or window, "TOPRIGHT", 2, -4)
        local minimized = false
        if type(window.IsMinimized) == "function" then
            local ok, m = pcall(window.IsMinimized, window)
            minimized = ok and not IsSecret(m) and m == true
        end
        skins.SkinCloseButton(minimize, { anchor = seat, glyph = minimized and "plus" or "minus" })
        if type(window.SetMinimized) == "function" and skins.SetGlyph then
            hooksecurefunc(window, "SetMinimized", function(_, isMinimized)
                skins.SetGlyph(minimize, isMinimized and "plus" or "minus")
            end)
        end
    end
end

-------------------------------------------------------------------------------
-- Windows
-------------------------------------------------------------------------------

local function SkinBody(container)
    local bg = container.Background
    if bg and bg.SetTexture then
        bg:SetTexture(Theme.SLICE_FILL_TEXTURE)
        Theme.ApplyNineSlice(bg, Theme.SLICE_MARGIN)
        bg:SetVertexColor(COLOR_BG[1], COLOR_BG[2], COLOR_BG[3], 1)
        bg:ClearAllPoints()
        bg:SetAllPoints(container)
    end
    local fill = Theme.AddPanelChrome(container, { fillColor = COLOR_BG, accent = ACCENT })
    if fill then fill:Hide() end   -- Blizzard's own background is the fill: the opacity setting keeps working
end

local function SkinHeader(window)
    local header = window.Header
    if not header then return end
    header:SetAlpha(0)
    local inset = Theme.PanelBandInset and Theme.PanelBandInset() or 3
    local band = Edge(window, "BACKGROUND", 2, ACCENT, BAND_ALPHA)
    band:SetPoint("TOPLEFT", header, "TOPLEFT", inset, -inset)
    band:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", -inset, 4)
    local rule = Edge(window, "BACKGROUND", 3, ACCENT, RULE_ALPHA)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT")
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT")
    rule:SetHeight(1)
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
