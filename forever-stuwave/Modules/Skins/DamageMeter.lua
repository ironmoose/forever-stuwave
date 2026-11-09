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
-- glyph buttons on one centre line), both kept inside the cut corners. Rows come in two styles, picked in /fsconfig:
-- neon plates (the default: one lit class gradient bar per row with a gloss line, an edge bloom and a rim, the text on
-- it) and the ladder (the text on a top line and the XP bar's run of leaning pips under it, a pink rail on the player's
-- own row). The fill is always one vertical class gradient that the engine crops to the row's value; the ladder lays a
-- gap tile over it (dm_cell_tile.tga, one texel per physical pixel) that cuts fill and unlit track into pips. Either
-- layout holds whatever bar style is picked in Blizzard's own settings.

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
local GEAR = MEDIA .. "icon_gear.tga"
local CHEVRON = MEDIA .. "glyph_hud_chev.tga"

local MAX_WINDOWS = 8
local TEXT_SIZE = 11                      -- Blizzard's own text scale setting multiplies this
local HEADER_SIZE = 11

-- Two row styles, picked in /fsconfig (Unit Frames, Damage meter). Player: "neon plates feels better. but ladder matches
-- stuwave", so both ship and plates is the default. From the mockup of 2026-11-09 (second sheet), forms A and B.
local STYLE_SETTING = {
    key = "skins.damageMeterRows", default = "plates", label = "Rows",
    tip = "Neon plates: each row is one lit bar with the name and number on it. Ladder: the name and number on top and a run of pips under them; it reads best with the meter's Bar Height at 26 or more.",
}
local STYLES = { "plates", "ladder" }
local STYLE_TEXT = { plates = "Neon plates", ladder = "Ladder" }
local Config = FS.Config
if Config and Config.RegisterDefault then Config.RegisterDefault(STYLE_SETTING.key, STYLE_SETTING.default) end

local function ReadStyle()
    local value = Config and Config.Get and Config.Get(STYLE_SETTING.key)
    if value == "ladder" then return "ladder" end
    return "plates"
end
local style = ReadStyle()

-- Neon plates (form B), in UI units unless named _PX: the class icon at the row's left, as tall as the plate, then the
-- plate: an ink well, the class gradient fill (deep foot, hot top) with a 1 px gloss along its top and a soft white bloom
-- at its edge, a 1 px rim in the class's deep colour (pink on the player's own row), and the "1. Name" and number on it.
local PLATE_PAD = 1                       -- above and below the plate, inside the row
local PLATE_LEFT = 2
local PLATE_ICON_GAP = 3
local PLATE_RIGHT = 3
local PLATE_TEXT_PAD = 5
local PLATE_INK = { 0.039, 0.016, 0.086 } -- #0a0416
local PLATE_GLOSS_ALPHA = 0.45
local PLATE_BLOOM_PX = 4
local PLATE_BLOOM_ALPHA = 0.32
local PLATE_RIM_MIX = 0.6                 -- the rim is the class's deep colour this far toward LINE
local PLATE_NAME_MINE = { 1, 0.816, 0.918 }   -- #ffd0ea, the own row's name on a lit plate

-- Ladder (form A): the icon, name and number on a top line, a pink rail down the player's own row, and under them the XP
-- bar's run of leaning pips from the icon's left edge. The pips are physical pixels so they land on whole pixels at any
-- UI scale; their height is what the row leaves under the top line, clamped.
local LADDER_ICON = 14
local LADDER_LEFT = 5                     -- the icon's and the gauge's left edge, clear of the rail
local LADDER_TOP = 1
local LADDER_TEXT_GAP = 4
local LADDER_RAIL = 2
local TILE_PX = 16                        -- dm_cell_tile.tga is 16 x 16: one pip (11 px, leaning) and its 5 px gap
local GAUGE_MAX_PX = 10
local GAUGE_MIN_PX = 4
local GAUGE_GAP_PX = 2                    -- clear px between the top line and the pips
local GAUGE_BOTTOM = 1
local TEXT_RIGHT = 3
local SLOT_DEEP = { 0.071, 0.039, 0.133 } -- #120a22, an unlit pip's foot
local SLOT_HOT = { 0.118, 0.078, 0.212 }  -- #1e1436, its top

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

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

local windows = setmetatable({}, { __mode = "k" })
local entries = setmetatable({}, { __mode = "k" })   -- entry -> its pieces
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

-- A plain positive number, or the fallback (a size Blizzard has not laid out yet reads 0).
local function Num(v, fallback)
    if IsSecret(v) or type(v) ~= "number" or v <= 0 then return fallback end
    return v
end

local function Gradient(t, deep, hot, a)
    if not (t and t.SetGradient) or type(CreateColor) ~= "function" then return end
    t:SetGradient("VERTICAL", CreateColor(deep[1], deep[2], deep[3], a or 1), CreateColor(hot[1], hot[2], hot[3], a or 1))
end

local function Show(region, on)
    if not region then return end
    if on then region:Show() else region:Hide() end
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

-- The player's own row (a read of Blizzard's flag, behind the secret check).
local function IsMine(entry)
    local me = entry.isLocalPlayer
    return not IsSecret(me) and me == true
end

-- Paints the row from `color` for the current style. The fill is ONE vertical gradient, deep at the foot and hot at the
-- top: on a plate that is the lit bar, and in the ladder the gap tile cuts it into pips that are each a single gradient.
local function PaintEntry(entry, color)
    local g = entries[entry]
    if not g then return end
    if color ~= nil then g.color = color end
    local ramp = RampFor(g.color)
    local deep, hot = ramp[1], ramp[2]
    local mine = IsMine(entry)
    local fill = entry.StatusBar:GetStatusBarTexture()
    if fill then
        fill:SetVertexColor(1, 1, 1, 1)
        Gradient(fill, deep, hot)
    end
    if g.iconRim then
        local mid = Mix(deep, hot, 0.5)
        g.iconRim:SetColorTexture(mid[1], mid[2], mid[3], 1)
    end
    local rim = mine and PINK or Mix(deep, LINE, PLATE_RIM_MIX)
    for _, t in ipairs(g.rim) do t:SetColorTexture(rim[1], rim[2], rim[3], 1) end
    Show(g.rail, style == "ladder" and mine)

    local name = entry.StatusBar.Name
    if name and name.SetTextColor then
        local c = WHITE
        if mine then c = style == "plates" and PLATE_NAME_MINE or PINK end
        name:SetTextColor(c[1], c[2], c[3], 1)
    end
end

-------------------------------------------------------------------------------
-- Entries (one row)
-------------------------------------------------------------------------------

-- The ladder's gap tile follows the gauge, one texel per physical pixel: across its width, and the BOTTOM rows of the
-- tile for its height (so the lean stays half a px per row however tall the gauge is).
local function SeatCells(entry)
    local g = entries[entry]
    local bar = entry.StatusBar
    if not (g and bar and bar.GetWidth) or style ~= "ladder" then return end
    local ppu = PixelsPerUnit(bar)
    local w = bar:GetWidth() or 0
    if IsSecret(w) or type(w) ~= "number" then return end
    local wpx = math.floor(w * ppu + 0.5)
    local h = g.gaugePx or GAUGE_MAX_PX
    if g.cells.SetTexCoord then g.cells:SetTexCoord(0, wpx / TILE_PX, (TILE_PX - h) / TILE_PX, 1) end
end

local function IconShown(entry)
    local icon = entry.Icon
    return icon and icon.IsShown and icon:IsShown() and icon or nil
end

local function LayOutPlates(entry, g, ppu)
    local bar, name, value = entry.StatusBar, entry.StatusBar.Name, entry.StatusBar.Value
    local px = 1 / ppu
    local rowH = Num(entry.GetHeight and entry:GetHeight(), 25)
    local plateH = rowH - 2 * PLATE_PAD
    local left = PLATE_LEFT
    local icon = IconShown(entry)
    if icon then
        icon:ClearAllPoints()
        icon:SetSize(plateH, plateH)
        icon:SetPoint("LEFT", entry, "LEFT", PLATE_LEFT, 0)
        left = PLATE_LEFT + plateH + PLATE_ICON_GAP
    end

    -- the bar is the plate's inside; the ink well and the rim sit one px around it
    bar:ClearAllPoints()
    bar:SetPoint("TOPLEFT", entry, "TOPLEFT", left + px, -(PLATE_PAD + px))
    bar:SetPoint("BOTTOMRIGHT", entry, "BOTTOMRIGHT", -(PLATE_RIGHT + px), PLATE_PAD + px)

    local bg = bar.Background
    if bg then
        bg:ClearAllPoints()
        bg:SetPoint("TOPLEFT", bar, "TOPLEFT", -px, px)
        bg:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", px, -px)
        bg:SetColorTexture(PLATE_INK[1], PLATE_INK[2], PLATE_INK[3], 1)
    end
    local top, bottom, l, r = g.rim[1], g.rim[2], g.rim[3], g.rim[4]
    top:ClearAllPoints(); top:SetPoint("TOPLEFT", bar, "TOPLEFT", -px, px); top:SetPoint("TOPRIGHT", bar, "TOPRIGHT", px, px)
    top:SetHeight(px)
    bottom:ClearAllPoints(); bottom:SetPoint("BOTTOMLEFT", bar, "BOTTOMLEFT", -px, -px)
    bottom:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", px, -px); bottom:SetHeight(px)
    l:ClearAllPoints(); l:SetPoint("TOPRIGHT", bar, "TOPLEFT", 0, 0); l:SetPoint("BOTTOMRIGHT", bar, "BOTTOMLEFT", 0, 0)
    l:SetWidth(px)
    r:ClearAllPoints(); r:SetPoint("TOPLEFT", bar, "TOPRIGHT", 0, 0); r:SetPoint("BOTTOMLEFT", bar, "BOTTOMRIGHT", 0, 0)
    r:SetWidth(px)
    if g.gloss then g.gloss:SetHeight(px) end
    if g.bloom then g.bloom:SetWidth(PLATE_BLOOM_PX * px) end

    if value then
        value:ClearAllPoints()
        value:SetPoint("RIGHT", bar, "RIGHT", -PLATE_TEXT_PAD, 0)
    end
    if name then
        name:ClearAllPoints()
        name:SetPoint("LEFT", bar, "LEFT", PLATE_TEXT_PAD, 0)
        if value then name:SetPoint("RIGHT", value, "LEFT", -8, 0) end
    end
end

local function LayOutLadder(entry, g, ppu)
    local bar, name, value = entry.StatusBar, entry.StatusBar.Name, entry.StatusBar.Value
    local rowH = Num(entry.GetHeight and entry:GetHeight(), 25)
    local lineMid = LADDER_TOP + LADDER_ICON / 2
    local textLeft = LADDER_LEFT
    local icon = IconShown(entry)
    if icon then
        icon:ClearAllPoints()
        icon:SetSize(LADDER_ICON, LADDER_ICON)
        icon:SetPoint("TOPLEFT", entry, "TOPLEFT", LADDER_LEFT, -LADDER_TOP)
        textLeft = LADDER_LEFT + LADDER_ICON + LADDER_TEXT_GAP
    end

    local px = math.floor((rowH - LADDER_TOP - LADDER_ICON - GAUGE_BOTTOM) * ppu) - GAUGE_GAP_PX
    g.gaugePx = math.max(GAUGE_MIN_PX, math.min(GAUGE_MAX_PX, px))
    bar:ClearAllPoints()
    bar:SetPoint("BOTTOMLEFT", entry, "BOTTOMLEFT", LADDER_LEFT, GAUGE_BOTTOM)
    bar:SetPoint("BOTTOMRIGHT", entry, "BOTTOMRIGHT", -TEXT_RIGHT, GAUGE_BOTTOM)
    bar:SetHeight(g.gaugePx / ppu)

    local bg = bar.Background
    if bg then
        bg:ClearAllPoints()
        bg:SetAllPoints(bar)
        bg:SetColorTexture(1, 1, 1, 1)
        Gradient(bg, SLOT_DEEP, SLOT_HOT)
    end
    if g.rail then
        g.rail:ClearAllPoints()
        g.rail:SetPoint("TOPLEFT", entry, "TOPLEFT", 0, -1)
        g.rail:SetPoint("BOTTOMLEFT", entry, "BOTTOMLEFT", 0, 2)
        g.rail:SetWidth(LADDER_RAIL)
    end

    if value then
        value:ClearAllPoints()
        value:SetPoint("RIGHT", entry, "TOPRIGHT", -TEXT_RIGHT, -lineMid)
    end
    if name then
        name:ClearAllPoints()
        name:SetPoint("LEFT", entry, "TOPLEFT", textLeft, -lineMid)
        if value then name:SetPoint("RIGHT", value, "LEFT", -8, 0) end
    end
    SeatCells(entry)
end

-- Blizzard's UpdateStyle (every style, icon and SetStyle change) re-anchors the bar, name and value and re-atlases the
-- recess; this runs after it and lays the row out in the picked style, whatever bar style Blizzard's settings name.
local function LayOut(entry)
    local g = entries[entry]
    local bar = entry.StatusBar
    if not (bar and g) then return end
    local ladder = style == "ladder"
    for _, t in ipairs(g.rim) do Show(t, not ladder) end
    Show(g.gloss, not ladder)
    Show(g.bloom, not ladder)
    Show(g.cells, ladder)
    if bar.BackgroundEdge and bar.BackgroundEdge.SetColorTexture then bar.BackgroundEdge:SetColorTexture(0, 0, 0, 0) end
    local ppu = PixelsPerUnit(entry)
    if ladder then LayOutLadder(entry, g, ppu) else LayOutPlates(entry, g, ppu) end
    PaintEntry(entry)
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
    local g = { rim = {}, color = entry.statusBarColor }   -- Blizzard's own cached colour (a read)
    entries[entry] = g

    bar:SetStatusBarTexture(FLAT)
    local fill = bar:GetStatusBarTexture()

    -- plates: the rim, and the gloss and bloom that ride the fill (the engine sizes the fill from the value)
    for i = 1, 4 do g.rim[i] = Edge(bar, "OVERLAY", -2, LINE) end
    if fill then
        g.gloss = Edge(bar, "OVERLAY", -4, { 1, 1, 1 }, PLATE_GLOSS_ALPHA)
        g.gloss:SetPoint("TOPLEFT", fill, "TOPLEFT", 0, 0)
        g.gloss:SetPoint("TOPRIGHT", fill, "TOPRIGHT", 0, 0)
        g.bloom = bar:CreateTexture(nil, "OVERLAY", nil, -5)
        g.bloom:SetTexture(FLAT)
        g.bloom:SetPoint("TOPRIGHT", fill, "TOPRIGHT", 0, 0)
        g.bloom:SetPoint("BOTTOMRIGHT", fill, "BOTTOMRIGHT", 0, 0)
        if g.bloom.SetGradient and type(CreateColor) == "function" then
            g.bloom:SetGradient("HORIZONTAL", CreateColor(1, 1, 1, 0), CreateColor(1, 1, 1, PLATE_BLOOM_ALPHA))
        end
    end

    -- ladder: the gap tile over fill and track, one texel per physical pixel, and the own row's rail
    g.cells = bar:CreateTexture(nil, "OVERLAY", nil, -6)
    g.cells:SetTexture(CELL_TILE, "REPEAT", "CLAMP", "NEAREST")
    g.cells:SetAllPoints(bar)
    Snap(g.cells)
    if entry.CreateTexture then g.rail = Edge(entry, "ARTWORK", 0, PINK) end

    -- the class or spell icon gets a 1 px rim in the class colour
    local icon = entry.Icon
    if icon and icon.CreateTexture then
        local px = 1 / PixelsPerUnit(entry)
        g.iconRim = Edge(icon, "BACKGROUND", -8, LINE)
        g.iconRim:SetPoint("TOPLEFT", icon, "TOPLEFT", -px, px)
        g.iconRim:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT", px, -px)
    end

    SetFont(bar.Name, TEXT_SIZE, WHITE)
    SetFont(bar.Value, TEXT_SIZE, WHITE)

    if type(entry.UpdateStyle) == "function" then hooksecurefunc(entry, "UpdateStyle", ApplyLayout) end
    if type(entry.SetStatusBarColor) == "function" then hooksecurefunc(entry, "SetStatusBarColor", PaintEntry) end
    if type(bar.HookScript) == "function" then pcall(bar.HookScript, bar, "OnSizeChanged", function() SeatCells(entry) end) end
    if type(entry.HookScript) == "function" then pcall(entry.HookScript, entry, "OnSizeChanged", function() ApplyLayout(entry) end) end

    ApplyLayout(entry)
end

-- The style changed (the /fsconfig dropdown, or the profile at login): every skinned row is laid out again.
local function Restyle()
    style = ReadStyle()
    for entry in pairs(entries) do ApplyLayout(entry) end
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

-- The bar's height: Blizzard's header (32, the rows start under it) less the rule's row.
local function BarHeight(window)
    local h = window.Header and window.Header.GetHeight and window.Header:GetHeight() or 32
    if type(h) ~= "number" or h <= 0 then h = 32 end
    return h - BAR_INSET
end

-- The wash fills the header behind the border, stepped in along the top-left chamfer the way the panel's own inner wash
-- is (Theme.AddRoundedFill's cut pieces: a fill_cut triangle in the corner, a run beside it, a full width band under
-- them), so nothing pokes past the cut. The rule closes it one row under, between the side borders.
local function CutCorner()
    local c = Theme.SnapCut and Theme.SnapCut(Theme.SLICE_MARGIN) or 0
    local path = c > 0 and Theme.FILL_CUT_TEXTURES and Theme.FILL_CUT_TEXTURES[c]
    return c, path
end

local function SkinHeader(window)
    local header = window.Header
    if not header then return end
    header:SetAlpha(0)
    local barH = BarHeight(window)
    local c, tri = CutCorner()
    if tri then
        local corner = window:CreateTexture(nil, "BACKGROUND", nil, 2)
        corner:SetTexture(tri)
        corner:SetVertexColor(ACCENT[1], ACCENT[2], ACCENT[3], BAR_WASH)
        corner:SetSize(c, c)
        corner:SetPoint("TOPLEFT", window, "TOPLEFT", 0, 0)
        corner:SetTexCoord(0, c / 16, 0, c / 16)   -- the fill_cut pieces are baked top-left on a 16 px canvas
        local run = Edge(window, "BACKGROUND", 2, ACCENT, BAR_WASH)
        run:SetPoint("TOPLEFT", window, "TOPLEFT", c, 0)
        run:SetPoint("TOPRIGHT", window, "TOPRIGHT", 0, 0)
        run:SetHeight(c)
    else
        c = 0
    end
    local wash = Edge(window, "BACKGROUND", 2, ACCENT, BAR_WASH)
    wash:SetPoint("TOPLEFT", window, "TOPLEFT", 0, -c)
    wash:SetPoint("TOPRIGHT", window, "TOPRIGHT", 0, -c)
    wash:SetHeight(barH - c)
    local rule = Edge(window, "BACKGROUND", 3, ACCENT, BAR_RULE)
    rule:SetPoint("TOPLEFT", wash, "BOTTOMLEFT", BAR_INSET, 0)
    rule:SetPoint("TOPRIGHT", wash, "BOTTOMRIGHT", -BAR_INSET, 0)
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

-- The scrim is three tiled pieces that keep out of the two cut corners (a run beside the top-left cut, the full width
-- middle, a run beside the bottom-right cut), each sampling the same 4 px grid so the lines run on across the joins.
local function SeatScanlines(pieces, frame, c)
    local w = frame.GetWidth and frame:GetWidth() or 0
    local h = frame.GetHeight and frame:GetHeight() or 0
    if IsSecret(w) or IsSecret(h) or type(w) ~= "number" or type(h) ~= "number" or w <= 0 or h <= 0 then return end
    local T = SCANLINE_TILE
    pieces[1]:SetTexCoord(c / T, w / T, 0, c / T)
    pieces[2]:SetTexCoord(0, w / T, c / T, (h - c) / T)
    pieces[3]:SetTexCoord(0, (w - c) / T, (h - c) / T, h / T)
end

local function SkinBody(container)
    Hold(container.Background)
    Theme.AddPanelChrome(container, { fillColor = TERM_BG, accent = ACCENT })
    if Theme.AddRoundedFill then
        Theme.AddRoundedFill(container, { ACCENT[1], ACCENT[2], ACCENT[3], INNER_WASH }, Theme.SLICE_MARGIN)
    end
    local c = CutCorner()
    local pieces = {}
    for i = 1, 3 do
        local scan = container:CreateTexture(nil, "BORDER", nil, -8)
        scan:SetTexture(SCANLINE, "REPEAT", "REPEAT")
        scan:SetAlpha(SCANLINE_ALPHA)
        pieces[i] = scan
    end
    pieces[1]:SetPoint("TOPLEFT", container, "TOPLEFT", c, 0)
    pieces[1]:SetPoint("TOPRIGHT", container, "TOPRIGHT", 0, 0)
    pieces[1]:SetHeight(c)
    pieces[2]:SetPoint("TOPLEFT", container, "TOPLEFT", 0, -c)
    pieces[2]:SetPoint("BOTTOMRIGHT", container, "BOTTOMRIGHT", 0, c)
    pieces[3]:SetPoint("BOTTOMLEFT", container, "BOTTOMLEFT", 0, 0)
    pieces[3]:SetPoint("BOTTOMRIGHT", container, "BOTTOMRIGHT", -c, 0)
    pieces[3]:SetHeight(c)
    SeatScanlines(pieces, container, c)
    if type(container.HookScript) == "function" then
        pcall(container.HookScript, container, "OnSizeChanged", function(self) SeatScanlines(pieces, self, c) end)
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
watcher:SetScript("OnEvent", function()
    SkinExisting()
    Restyle()   -- the profile is loaded by now
end)
if Config and Config.OnChange then Config.OnChange(STYLE_SETTING.key, Restyle) end

local function Style() return style end

FS.DamageMeterSkin = {
    SkinWindow = SkinWindow, SkinEntry = SkinEntry, RampFor = RampFor, RAMPS = RAMPS,
    SETTING = STYLE_SETTING, STYLES = STYLES, STYLE_TEXT = STYLE_TEXT, Style = Style,
}
