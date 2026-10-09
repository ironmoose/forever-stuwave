-- Forever STUwave: Gunsight Seal module, the Paladin's class module for one half height area (upper or lower).
--
-- The approved design is mockups/gunsight-modules-concepts-v7-2026-10-08.html, sealModule(y0): the seal tile with its name and
-- "SEAL ACTIVE", the time left large, a 188 px drain bar (0 to 30 s left to right, an amber RESEAL band on the 0 to 3 s end,
-- ticks and 0 / 15 / 30 numbers) and the Judgement row (a J chip, a 0 to 40 s bar, the time on the target). Every image px number
-- is in the constants block with its mockup name, and gunsightseals-harness.py re-reads them from the HTML.
--
-- GunsightAreas.lua owns the upper and lower area frames and calls this module back: build(host) once, seat(rect) with the area's
-- image px rect (again on every rescale, and when the player moves the module to the other area), onShow(area) and onHide(area).
-- The module draws from the rect it was last given, so it works in either area, and it follows the Hud only while an area shows it.
--
-- STATE. Three looks from FS.Hud's state.seal: a known seal (its key maps to a seal id: sor righteousness, sotc crusader, sofu fury,
-- soc command, sol light, sow wisdom, soj justice) in its colour; false (no seal) is NO SEAL in red; nil, a secret or an unmapped
-- key is UNKNOWN, a dim violet tile that guesses nothing. A known seal under 3 s left is the reseal warning: the fill, the time
-- and the caption go amber and the band breathes. The Judgement row follows the TARGET's debuff (state.judged) in the look's colour.
--
-- TICKER. ONE OnUpdate on the module frame, installed only while the module is subscribed AND something moves (a timed seal, a
-- debuff on the target, the NO SEAL pulse in combat) and cleared the moment nothing does. The per frame path (Tick and what it
-- calls) allocates nothing: no table, closure, concatenation or format; the time strings come from tables built at load.
--
-- Reduced motion (ForeverSTUwaveDB.reducedMotion == true, read at each Hud push) holds the pulse steady; the bars and the
-- countdown still move. Nothing is built at file load: build runs only when GunsightAreas asks for the module.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.ui and Gunsight.Point) then return end

FS.GunsightSeals = FS.GunsightSeals or {}
local Seals = FS.GunsightSeals

local G = Gunsight.G
local ui, Point = Gunsight.ui, Gunsight.Point

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightseals-harness.py re-reads them from sealModule)
-------------------------------------------------------------------------------

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

-- Module coordinates are image px from the module's top left: x from 0 to W across the area's width less the inset, y from 0
-- at the area's top (the mockup's y0). seat(rect) centres the module across rect.w, so rect.x + 7 is the mockup's x = 1220.
local C = {
    W = 188, H = 114,                         -- sealModule: w = 188; the module fills 114 of the area's 128
    TILE = 28, TILE_Y = 6, TILE_CUT = 5,      -- ch(x, y0 + 6, 28, 28, 5); the baked cut is 6
    TILE_MIX = 0.3, TILE_EDGE_W = 1.4,        -- mix(bg, col, .3) fill, stroke-width 1.4
    AB_X = 14, AB_Y = 25, AB_SIZE = 12,       -- txt(x + 14, y0 + 25, 'SV', 12, white, middle)
    NAME_X = 36, NAME_Y = 19, NAME_SIZE = 12, -- txt(x + 36, y0 + 19, 'VENGEANCE', 12, white)
    CAP_Y = 31, CAP_SIZE = 10,                -- txt(x + 36, y0 + 31, 'SEAL ACTIVE', 10, muted)
    TIME_Y = 27, TIME_SIZE = 20,              -- txt(x + w, y0 + 27, seal + 's', 20, col, end)
    BAR_Y = 44, BAR_H = 12, MAX_S = 30,       -- by = y0 + 44, bh = 12, bw = w * (30 / 30)
    TRACK_A = 0.9, FILL_A = 0.9,              -- rect '#0a0416' .9, rect col .9
    BAND_S = 3, BAND_A = 0.28,                -- bw * 3 / 30 wide, amber .28
    TIP_W = 2, TIP_PAD = 2, TIP_A = 0.95,     -- rect(.. - 2, by - 2, 2, bh + 4, '#ffffff', .95)
    OUT_A = 0.6,                              -- stroke-opacity .6
    CUT_PAD = 3, CUT_A = 0.85, CUT_DASH = { 3, 2 },   -- line(.., by - 3, .., by + bh + 3, amber, .85, 1, '3 2')
    TICKS = 6, TICK_LONG = 5, TICK_SHORT = 3, TICK_A = 0.7,   -- i = 0 .. 6: by + bh + (i % 2 === 0 ? 5 : 3), violet .7
    LABEL_Y = 16, LABEL_SIZE = 10, LABEL_A = 0.85,    -- txt(.., by + bh + 16, String(v), 10, fg, .85)
    LABELS = { 0, 15, 30 },
    RESEAL_DX = 30, RESEAL_SIZE = 10, RESEAL_A = 0.9, -- txt(bx + bw * 3 / 30 + 30, .., 'RESEAL', 10, amber, .9)
    J_Y = 90, J_SIZE = 20, J_CUT = 4,         -- jy = y0 + 90; ch(x, jy, 20, 20, 4)
    J_MIX = 0.4, J_PLATE = "#d9a521", J_EDGE_W = 1.2,   -- mix(bg, '#d9a521', .4) fill, stroke-width 1.2
    J_LETTER_Y = 14, J_LETTER_SIZE = 12,      -- <text x + 10, jy + 14, 12, white>J</text>
    JBAR_X = 30, JBAR_DY = 7, JBAR_SHRINK = 72, JBAR_H = 5,   -- rect(x + 30, jy + 7, w - 72, 5, col, .2)
    JBAR_TRACK_A = 0.2, JMAX_S = 40,          -- rect(.. jud / 40 ..)
    JTIME_Y = 15, JTIME_SIZE = 13,            -- txt(x + w, jy + 15, jud + 's', 13, white, end)
    -- not in v7: the carried over look states (the v2 chamber's numbers)
    FILL_MIN = 0.05,                          -- the drain shows for more than .05 s left
    COUNT_FROM = 5,                           -- whole seconds above 5, tenths from 5 down
    TILE_GLOW_A = 0.5,                        -- the tile edge's soft glow (the mockup's gls filter)
    PULSE_S = 1.4, NO_U = 0.5,                -- u = .5 - .5 * cos(PI * clock / 1.4); NO_U is its resting mean
    BAND_PL_FREQ = 9, BAND_PL = 0.2,          -- the band breathes with the clock under 3 s: BAND_A + .2 * (.5 + .5 * sin(clock * 9))
    RESEAL_IN0 = 0.55, RESEAL_IN1 = 0.45,     -- RESEAL under 3 s: .55 + .45 * u
    NO_EDGE_A0 = 0.35, NO_EDGE_A1 = 0.65,     -- the NO SEAL tile edge: .35 + .65 * u
    NO_NAME_A0 = 0.5, NO_NAME_A1 = 0.5,       -- the NO SEAL name: .5 + .5 * u
    UNKNOWN_EDGE_A = 0.55,
    ICON_TEXCOORD = { 0.07, 0.93, 0.07, 0.93 },   -- not in v7 (its letter chips stand for icons): the icon inside the cut frame, border cropped
    TRACK = "#0a0416", ABSENT_A = 0.45,       -- the track colour; the chip's alpha with no debuff on the target
    FILL_STEP = 0.25,                         -- not in the mockup: bar widths snap to a quarter screen pixel
    CAP_TEXT = "SEAL ACTIVE", CAP_EXPIRING = "EXPIRING", CAP_NONE = "CAST A SEAL",
    NAME_NONE = "NO SEAL", NOT_JUDGED = "NOT JUDGED", NO_DEBUFF = "NO DEBUFF",
    JEMPTY_X = 34, JEMPTY_SIZE = 10, JEMPTY_A = 0.8,
    -- Mononoki Bold, read from the font file (the harness re-reads it): the line box runs from the hhea ascender (900) to the
    -- descender (-250) of 1024 units, so its middle sits 325 / 1024 of the size above the baseline. UNVERIFIED in game.
    CAP = 325 / 1024,
    COLORS = {                                -- the mockup's :root tokens
        bg = Hex("#0d0620"), fg = Hex("#e9e2ff"), violet = Hex("#a855f7"), amber = Hex("#ffb648"),
        red = Hex("#ff3b4e"), steel = Hex("#8d93a6"), muted = Hex("#9d93c4"), white = Hex("#f3fbff"),
    },
    -- SEALS: n the name, ab the tile letters, c the colour, deb the Judgement debuff seconds (0 = none)
    SEALS = {
        righteousness = { n = "RIGHTEOUSNESS", ab = "RI", c = Hex("#ffd23f"), deb = 0 },
        crusader = { n = "CRUSADER", ab = "CR", c = Hex("#ff9a2e"), deb = 40 },
        fury = { n = "FURY", ab = "FU", c = Hex("#ff3b4e"), deb = 0 },
        command = { n = "COMMAND", ab = "CO", c = Hex("#b565ff"), deb = 0 },
        light = { n = "LIGHT", ab = "LI", c = Hex("#f3fbff"), deb = 40 },
        wisdom = { n = "WISDOM", ab = "WI", c = Hex("#4da3ff"), deb = 40 },
        justice = { n = "JUSTICE", ab = "JU", c = Hex("#c9d3e6"), deb = 10 },
    },
}
C.JBAR_W = C.W - C.JBAR_SHRINK
Seals.C = C
local K, SEALS = C.COLORS, C.SEALS

-- HudSpells seal key (the profile's `seals.order`, HudLogic state.seal.key) to the seal id.
local KEY_ID = {
    sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command",
    sol = "light", sow = "wisdom", soj = "justice",
}

local WHITE = { 1, 1, 1 }
-- Hairline weight in image px: the DoT scale's own, so the classes that share an area match. The mockup's 1 px strokes are
-- 1 image px; UNVERIFIED in game next to the baked tile edge.
local LINE = G.LINE or 1.3
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightseals_" .. key,
            "|cffff4488Forever STUwave|r: gunsight seals: " .. tostring(msg))
    end
end

local subscribed = false
local mod                      -- the module frame itself, a child of the area host
local P = {}                   -- the named parts (exposed as Seals.parts)
local seats = {}               -- closures re-run by every seat(rect)
local OX, OY = 0, 0            -- the module's top left in image px, from the rect seat() last got
local mode, sealId             -- the look last painted: "seal" | "none" | "unknown", and the seal id for "seal"
local inCombat = false         -- the combat flag the NO SEAL look last painted (false for every other look)
local laneCol = false          -- the colour the Judgement row last painted a debuff in, nil for the empty row, false before the first paint

-- The live layer's state: the Hud's plain times and what the moving parts last wore, so a frame writes only what changed.
-- Paint resets the caches, so the first frame after a repaint writes everything.
local L = {
    col = nil,                 -- the colour of the look painted
    expiresAt = nil,           -- the seal's plain GetTime expiry, nil when absent or unreadable
    combat = false,            -- the Hud's combat flag as of the last push (any look)
    warn = false,              -- the reseal warning is worn
    fillShown = false, fillW = nil,                 -- the drain: shown, and its width in image px
    timeText = nil, timeShown = false,              -- the time text worn, and whether it is up
    fillQ = nil,                                    -- bar widths snap to this many image px (nil: exact)
    reduced = false,                                -- ForeverSTUwaveDB.reducedMotion as of the last Paint
    jExp = nil,                                     -- the target's Judgement debuff: plain expiresAt, nil when none or unreadable
    jW = nil, jFillShown = false,                   -- the Judgement bar's width in image px, and whether it is up
    jText = nil,                                    -- the Judgement time text worn
    sealIcon = false, jIcon = false,                -- the tile and chip wear their spell icon (else their letters)
    jDead = false,                                  -- the row is empty only because the target is dead: a health event may relight it
    laneText = "",                                  -- the empty row label the look gives (NOT JUDGED, NO DEBUFF or none)
    broken = false,            -- a frame threw: the ticker stays off until the next push
}
local ticking = false          -- the module's OnUpdate is installed
local Sync                     -- forward: Tick stops itself through it

local function Seat(fn)
    seats[#seats + 1] = fn
    fn()
end

local function SeatAll()
    for i = 1, #seats do
        local ok, err = pcall(seats[i])
        if not ok then LogOnce("seat", err) end
    end
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

-------------------------------------------------------------------------------
-- Drawing helpers (module coordinates, seated through Gunsight.Point from the rect origin)
-------------------------------------------------------------------------------

local function At(region, anchor, x, y)
    Point(region, anchor, OX + x, OY + y)
end

local function Tex(layer, sub)
    return mod:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
end

local function Solid(t, c, a)
    t:SetColorTexture(c[1], c[2], c[3], a)
end

-- A solid rectangle from (x, y), w by h image px.
local function Rect(x, y, w, h, c, a, layer, sub)
    local t = Tex(layer, sub)
    Solid(t, c, a)
    Seat(function()
        At(t, "TOPLEFT", x, y)
        t:SetSize(ui(w), ui(h))
    end)
    return t
end

-- A horizontal line from x0 to x1 centred on y, and a vertical one at x from y0 to y1, `th` image px thick.
local function HLine(y, x0, x1, c, a, th, layer, sub)
    return Rect(x0, y - th / 2, x1 - x0, th, c, a, layer, sub)
end
local function VLine(x, y0, y1, c, a, th, layer, sub)
    return Rect(x - th / 2, y0, th, y1 - y0, c, a, layer, sub)
end

local function VDashes(x, y0, y1, dash, c, a, th, layer, sub)
    local list, y = {}, y0
    while y < y1 - 1e-6 do
        list[#list + 1] = VLine(x, y, math.min(y1, y + dash[1]), c, a, th, layer, sub)
        y = y + dash[1] + dash[2]
    end
    return list
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- Text on a mockup baseline: `anchor` is "LEFT", "CENTER" or "RIGHT" (the mockup's start, middle, end); the line is centred
-- C.CAP * size above the baseline.
local function Text(parent, text, size, anchor, x, baseline)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH(anchor)
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(size), fs.cur)
        At(fs, anchor, x, baseline - C.CAP * size)
    end)
    -- After Seat, which runs once at once and so sets the font: SetText on a FontString with none throws "Font not set".
    fs:SetText(text)
    return fs
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

-- The tile and the Judgement chip show a tooltip only while the Gunsight is the display and the module is on an area.
local function TipGate() return Gunsight.IsActive() and subscribed end

-- A chamfered plate on its own small frame: fill and outline slices (and the tile's soft glow) over a square of `size` image px,
-- with a hidden icon inside the cut.
local function Plate(x, y, size, cut, fillPath, outlinePath, withGlow)
    local Theme = FS.Theme
    local f = CreateFrame("Frame", nil, mod)
    f:SetFrameLevel(mod:GetFrameLevel() + 1)
    f:EnableMouse(false)
    -- Hover only (clicks pass through the centre HUD); Apply sets the spell each push.
    if FS.FrameHelpers and FS.FrameHelpers.AttachSpellTooltip then FS.FrameHelpers.AttachSpellTooltip(f, { gate = TipGate }) end
    Seat(function()
        At(f, "TOPLEFT", x, y)
        f:SetSize(ui(size), ui(size))
    end)
    f.plate = Theme.AddSliceTexture(f, fillPath, WHITE, "BACKGROUND", 0)
    Theme.ApplyNineSlice(f.plate, cut)
    f.edge = Theme.AddSliceTexture(f, outlinePath, WHITE, "BORDER", 0)
    Theme.ApplyNineSlice(f.edge, cut)
    -- the icon sits inside the cut frame, inset half the cut so its corners land on the chamfer line
    local inset = math.ceil(cut / 2)
    f.icon = f:CreateTexture(nil, "ARTWORK", nil, 0)
    f.icon:SetTexCoord(C.ICON_TEXCOORD[1], C.ICON_TEXCOORD[2], C.ICON_TEXCOORD[3], C.ICON_TEXCOORD[4])
    f.icon:Hide()
    Seat(function()
        f.icon:ClearAllPoints()
        f.icon:SetPoint("TOPLEFT", f, "TOPLEFT", ui(inset), -ui(inset))
        f.icon:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -ui(inset), ui(inset))
    end)
    if withGlow then
        f.glow = Theme.AddSliceTexture(f, Theme.SLICE_GLOW_TEXTURE, WHITE, "BORDER", -1, -Theme.SLICE_GLOW_PAD)
        Theme.ApplyNineSlice(f.glow, Theme.SLICE_GLOW_MARGIN)
        f.glow:SetBlendMode("ADD")
    end
    return f
end

-- UI units per physical pixel at the root's effective scale, or nil when the client will not say (GunsightFrame's PixelUnit).
local function PixelUnit()
    local factor
    local pixelUtil, physical = _G.PixelUtil, _G.GetPhysicalScreenSize
    if type(pixelUtil) == "table" and type(pixelUtil.GetPixelToUIUnitFactor) == "function" then
        local ok, v = pcall(pixelUtil.GetPixelToUIUnitFactor)
        if ok then factor = v end
    elseif type(physical) == "function" then
        local ok, _, h = pcall(physical)
        if ok and type(h) == "number" and not (FS.IsSecret and FS.IsSecret(h)) and h > 0 then factor = 768 / h end
    end
    -- a plain, finite, positive number or nothing (a NaN or an infinity would poison every width written after it)
    if type(factor) ~= "number" or (FS.IsSecret and FS.IsSecret(factor)) or factor ~= factor or factor <= 0 or factor == math.huge then return nil end
    local scale = 1
    local root = Gunsight.root
    if root and root.GetEffectiveScale then
        local ok, v = pcall(root.GetEffectiveScale, root)
        if ok and type(v) == "number" and not (FS.IsSecret and FS.IsSecret(v)) and v > 0 and v < math.huge then scale = v end
    end
    return factor / scale
end

-- How many image px a quarter screen pixel is at the current scale (nil: the client will not say, the width stays exact).
local function SeatFillStep()
    L.fillQ = nil
    local px = PixelUnit()
    if not px then return end
    local one = ui(1)
    if type(one) == "number" and one > 0 and one < math.huge then L.fillQ = C.FILL_STEP * px / one end
end

local function BuildTile()
    P.tile = Plate(0, C.TILE_Y, C.TILE, FS.Theme.SLICE_CUT_MARGIN, FS.Theme.SLICE_CUT2_FILL_TEXTURE,
        FS.Theme.SLICE_CUT2_OUTLINE_TEXTURE, true)
    P.ab = Text(P.tile, "", C.AB_SIZE, "CENTER", C.AB_X, C.AB_Y)
    P.name = Text(mod, "", C.NAME_SIZE, "LEFT", C.NAME_X, C.NAME_Y)
    P.cap = Text(mod, "", C.CAP_SIZE, "LEFT", C.NAME_X, C.CAP_Y)
    P.time = Text(mod, "", C.TIME_SIZE, "RIGHT", C.W, C.TIME_Y)
    TextColor(P.ab, K.white, 1)
    TextColor(P.name, K.white, 1)
    TextColor(P.cap, K.muted, 1)
end

local function BuildBar()
    local by, bh, bw = C.BAR_Y, C.BAR_H, C.W
    P.track = Rect(0, by, bw, bh, Hex(C.TRACK), C.TRACK_A, "BACKGROUND", 0)
    local bandW = bw * C.BAND_S / C.MAX_S
    P.band = Rect(0, by, bandW, bh, K.amber, C.BAND_A, "BACKGROUND", 1)
    -- The drain grows from the left by SetWidth alone; the white tip rides its right edge by anchor, so a frame writes the fill
    -- width and nothing else.
    P.fill = Tex("ARTWORK", 0)
    P.fill:SetColorTexture(1, 1, 1, C.FILL_A)
    Seat(SeatFillStep)
    Seat(function()
        At(P.fill, "TOPLEFT", 0, by)
        P.fill:SetSize(ui(L.fillW or 0), ui(bh))
    end)
    P.tip = Tex("ARTWORK", 1)
    Solid(P.tip, WHITE, C.TIP_A)
    Seat(function()
        P.tip:ClearAllPoints()
        P.tip:SetPoint("RIGHT", P.fill, "RIGHT")
        P.tip:SetSize(ui(C.TIP_W), ui(bh + 2 * C.TIP_PAD))
    end)
    -- strokeRect: four lines centred on the rect's edges
    P.outline = {
        HLine(by, -LINE / 2, bw + LINE / 2, WHITE, C.OUT_A, LINE, "ARTWORK", 2),
        HLine(by + bh, -LINE / 2, bw + LINE / 2, WHITE, C.OUT_A, LINE, "ARTWORK", 2),
        VLine(0, by, by + bh, WHITE, C.OUT_A, LINE, "ARTWORK", 2),
        VLine(bw, by, by + bh, WHITE, C.OUT_A, LINE, "ARTWORK", 2),
    }
    P.cut = VDashes(bandW, by - C.CUT_PAD, by + bh + C.CUT_PAD, C.CUT_DASH, K.amber, C.CUT_A, LINE, "ARTWORK", 3)
    P.ticks = {}
    for i = 0, C.TICKS do
        local x = bw * i / C.TICKS
        local len = i % 2 == 0 and C.TICK_LONG or C.TICK_SHORT
        P.ticks[i + 1] = VLine(x, by + bh, by + bh + len, K.violet, C.TICK_A, LINE, "ARTWORK", 3)
    end
    P.labels = {}
    for i, v in ipairs(C.LABELS) do
        local anchor = v == 0 and "LEFT" or (v == C.MAX_S and "RIGHT" or "CENTER")
        P.labels[i] = Text(mod, tostring(v), C.LABEL_SIZE, anchor, bw * v / C.MAX_S, by + bh + C.LABEL_Y)
        TextColor(P.labels[i], K.fg, C.LABEL_A)
    end
    P.reseal = Text(mod, "RESEAL", C.RESEAL_SIZE, "CENTER", bandW + C.RESEAL_DX, by + bh + C.LABEL_Y)
    TextColor(P.reseal, K.amber, C.RESEAL_A)
end

local function BuildJudgement()
    local jy = C.J_Y
    local plate = Hex(C.J_PLATE)
    local cut = C.J_CUT
    local base = MEDIA .. "slice_cut2_"
    P.chip = Plate(0, jy, C.J_SIZE, cut, base .. "fill_c" .. cut .. ".tga", base .. "outline_c" .. cut .. ".tga", false)
    local pc = Mix(K.bg, plate, C.J_MIX)
    P.chip.plate:SetVertexColor(pc[1], pc[2], pc[3], 1)
    P.jLetter = Text(P.chip, "J", C.J_LETTER_SIZE, "CENTER", C.J_SIZE / 2, jy + C.J_LETTER_Y)
    TextColor(P.jLetter, K.white, 1)
    P.jTrack = Rect(C.JBAR_X, jy + C.JBAR_DY, C.JBAR_W, C.JBAR_H, K.steel, C.JBAR_TRACK_A, "ARTWORK", 0)
    P.jFill = Tex("ARTWORK", 1)
    P.jFill:SetColorTexture(1, 1, 1, 1)
    P.jFill:Hide()
    Seat(function()
        At(P.jFill, "TOPLEFT", C.JBAR_X, jy + C.JBAR_DY)
        P.jFill:SetSize(ui(L.jW or 0), ui(C.JBAR_H))
    end)
    P.jTime = Text(mod, "", C.JTIME_SIZE, "RIGHT", C.W, jy + C.JTIME_Y)
    TextColor(P.jTime, K.white, 1)
    P.jEmpty = Text(mod, "", C.JEMPTY_SIZE, "LEFT", C.JEMPTY_X, jy + C.JTIME_Y)
    TextColor(P.jEmpty, K.muted, C.JEMPTY_A)
end

-------------------------------------------------------------------------------
-- Look
-------------------------------------------------------------------------------

local function ShowAll(list, on)
    for i = 1, #list do list[i]:SetShown(on) end
end

local function DrainParts() return { P.fill, P.tip, P.time } end

-- A text region's alpha and colour, in place: the colour lives on fs.cur (Theme.ApplyMono resets from it at a rescale).
local function TextAlpha(fs, a)
    local cur = fs.cur
    cur[4] = a
    fs:SetTextColor(cur[1], cur[2], cur[3], a)
end

local function PaintText(fs, c, a)
    local cur = fs.cur
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

local function Tint(t, c, a)
    t:SetVertexColor(c[1], c[2], c[3], a)
end

-- Paints a look at rest (no pulse, nothing moving) and resets what the live layer has worn, so the first frame after a repaint
-- writes everything again. The drain starts hidden: the live layer shows it when it reads a time.
local function Paint(newMode, id, combat, reduce)
    local no, known = newMode == "none", newMode == "seal"
    local sl = known and SEALS[id] or nil
    local col = known and sl.c or (no and K.red or K.violet)
    local pu = reduce and 1 or C.NO_U             -- reduced motion holds the pulse at u = 1

    L.col = col
    L.warn = false
    L.fillShown, L.fillW, L.timeShown, L.timeText = false, nil, false, nil

    -- tile
    local tile = P.tile
    local plateC = Mix(K.bg, col, C.TILE_MIX)
    tile.plate:SetVertexColor(plateC[1], plateC[2], plateC[3], 1)
    local edgeA = known and 1 or (no and (C.NO_EDGE_A0 + C.NO_EDGE_A1 * pu) or C.UNKNOWN_EDGE_A)
    Tint(tile.edge, col, edgeA)
    Tint(tile.glow, col, C.TILE_GLOW_A * edgeA)
    tile.glow:SetShown(known or no)
    P.ab:SetText(known and sl.ab or (no and "--" or ""))
    P.ab:SetShown(known or no)
    tile.icon:Hide()
    L.sealIcon = false
    TextColor(P.ab, no and K.red or K.white, 1)
    P.name:SetText(known and sl.n or (no and C.NAME_NONE or ""))
    TextColor(P.name, no and K.red or K.white, no and (C.NO_NAME_A0 + C.NO_NAME_A1 * pu) or 1)
    P.cap:SetText(known and C.CAP_TEXT or (no and C.CAP_NONE or ""))
    TextColor(P.cap, no and combat and K.red or K.muted, no and combat and 0.8 or 1)

    -- the bar: the track and the amber band stay, the drain and the time wait for a reading; with no seal the outline is steel
    local oc = known and col or (no and K.steel or K.violet)
    for _, t in ipairs(P.outline) do Solid(t, oc, C.OUT_A) end
    Solid(P.band, K.amber, C.BAND_A)
    TextColor(P.reseal, K.amber, C.RESEAL_A)
    ShowAll(DrainParts(), false)
    if known then Solid(P.fill, col, C.FILL_A) end
    if no then
        PaintText(P.time, K.muted, 0.4)
        P.time:SetText("--")
        P.time:Show()
    else
        TextColor(P.time, col, 1)
    end

    -- the Judgement row's empty label follows the look; a debuff on the target takes the row, so the label waits for it to clear
    L.laneText = known and (sl.deb > 0 and C.NOT_JUDGED or C.NO_DEBUFF) or ""
    P.jEmpty:SetText(laneCol and "" or L.laneText)
    mode, sealId, inCombat, L.reduced = newMode, id, combat, reduce
end

-------------------------------------------------------------------------------
-- Live layer (every function from Pulse to Tick is on the per frame path)
-------------------------------------------------------------------------------

local floor, ceil, sin, cos, pi, huge = math.floor, math.ceil, math.sin, math.cos, math.pi, math.huge

-- The time strings, made once: the per frame path cannot format or concatenate. Whole seconds 0 to 40, tenths 0.0 to 5.0.
local WHOLE, TENTHS = {}, {}
for i = 0, C.JMAX_S do WHOLE[i] = i .. "s" end
for i = 0, C.COUNT_FROM * 10 do TENTHS[i] = string.format("%d.%ds", floor(i / 10), i % 10) end

-- A time from the Hud as a plain finite number, or nil: a secret (the guard first), a string, NaN and infinity read as unknown.
local function Plain(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v or v == huge or v == -huge then return nil end
    return v
end

-- u = .5 - .5 * cos(PI * clock / 1.4)
local function Pulse(t)
    return 0.5 - 0.5 * cos(pi * t / C.PULSE_S)
end

-- Whole seconds above 5 (a ceiling, clamped at 30), tenths from 5 down.
local function TimeText(rem)
    if rem > C.COUNT_FROM then
        local n = ceil(rem)
        if n > C.MAX_S then n = C.MAX_S end
        return WHOLE[n]
    end
    return TENTHS[floor(rem * 10 + 0.5)] or TENTHS[0]
end

-- A bar width in image px for `rem` seconds of `max`, pinned at the full bar (a reconcile can report a longer duration) and snapped
-- to L.fillQ, a quarter screen pixel, so a steady drain writes only when a pixel quarter changes.
local function BarWidth(rem, max, full)
    local w = rem * full / max
    local q = L.fillQ
    if q then w = floor(w / q + 0.5) * q end
    if w > full then w = full end
    return w
end

-- The RESEAL cue (under 3 s): the band breathes with the clock every frame in it; the fill, the time and the caption go amber once
-- on the way in and back once on the way out.
local function SetWarn(on, now)
    if on and not L.reduced then
        local pl = 0.5 + 0.5 * sin(now * C.BAND_PL_FREQ)
        P.band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], C.BAND_A + C.BAND_PL * pl)
        TextAlpha(P.reseal, C.RESEAL_IN0 + C.RESEAL_IN1 * Pulse(now))
    end
    if on == L.warn then return end
    L.warn = on
    local c = on and K.amber or L.col
    Solid(P.fill, c, C.FILL_A)
    PaintText(P.time, c, 1)
    if on then
        P.cap:SetText(C.CAP_EXPIRING)
        PaintText(P.cap, K.amber, 1)
    else
        P.cap:SetText(C.CAP_TEXT)
        PaintText(P.cap, K.muted, 1)
        P.band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], C.BAND_A)
        TextAlpha(P.reseal, C.RESEAL_A)
    end
    if on and L.reduced then
        -- no breathing: the band rests at its base, RESEAL holds .55 + .45 * 1, both written once on the way in
        P.band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], C.BAND_A)
        TextAlpha(P.reseal, C.RESEAL_IN0 + C.RESEAL_IN1)
    end
end

-- The NO SEAL pulse (u): the tile edge .35 + .65 * u and its glow, the name .5 + .5 * u.
local function ApplyNoSeal(u)
    local a = C.NO_EDGE_A0 + C.NO_EDGE_A1 * u
    local tile = P.tile
    Tint(tile.edge, K.red, a)
    Tint(tile.glow, K.red, C.TILE_GLOW_A * a)
    TextAlpha(P.name, C.NO_NAME_A0 + C.NO_NAME_A1 * u)
end

-- The drain: width remaining / 30 s of the bar, shown for more than .05 s; the time shows for any readable time (the tube
-- gate is the fill's alone). The tip rides the fill's right edge by anchor. No time hides all three.
local function ApplyBar(rem)
    if rem and rem > C.FILL_MIN then
        local w = BarWidth(rem, C.MAX_S, C.W)
        if not L.fillShown then
            L.fillShown = true
            P.fill:Show()
            P.tip:Show()
        end
        if w ~= L.fillW then
            L.fillW = w
            P.fill:SetWidth(ui(w))
        end
    elseif L.fillShown then
        L.fillShown = false
        P.fill:Hide()
        P.tip:Hide()
    end
    if rem then
        local text = TimeText(rem)
        if text ~= L.timeText then
            L.timeText = text
            P.time:SetText(text)
        end
        if not L.timeShown then
            L.timeShown = true
            P.time:Show()
        end
    elseif L.timeShown then
        L.timeShown = false
        P.time:Hide()
    end
end

-- The Judgement row follows the TARGET's debuff in state.judged, in the look's colour; LaneLook repaints it only on a change.

-- Is `key` (a ledger seal key) one a Judgement debuff can be cast under? Righteousness, Fury and Command carry none (deb 0), an
-- unmapped key or a non string one is nothing, a secret is never indexed.
local function KeyHasDebuff(key)
    if FS.IsSecret and FS.IsSecret(key) then return false end
    local id = KEY_ID[key]
    return id ~= nil and SEALS[id].deb > 0
end

-- The target's Judgement debuff from a Hud state: true with the plain expiresAt, or nil when there is none or it cannot be read
-- (false and nil both draw the empty row).
local function JudgedOf(state)
    if FS.IsSecret and FS.IsSecret(state) then return nil end
    if type(state) ~= "table" then return nil end
    local jd = state.judged
    if FS.IsSecret and FS.IsSecret(jd) then return nil end
    if type(jd) ~= "table" then return nil end
    if not KeyHasDebuff(jd.key) then return nil end
    return true, Plain(jd.expiresAt)
end

-- The current target's debuff straight from FS.Hud.GetJudgement: true with an absolute expiresAt, or nil for none, unknown, a
-- missing or throwing Hud and anything unreadable.
local function ReadJudgement(now)
    local Hud = FS.Hud
    local fn = type(Hud) == "table" and Hud.GetJudgement
    local ok, j = pcall(fn)
    if not ok then return nil end
    if FS.IsSecret and FS.IsSecret(j) then return nil end
    if type(j) ~= "table" then return nil end
    if not KeyHasDebuff(j.key) then return nil end
    local rem = Plain(j.remaining)
    if not rem then return nil end
    return true, now + rem
end

-- Is the target plainly dead? A secret, a missing API, a throw or an odd answer reads as alive (the row is emptied only on a
-- plain yes; the legacy API answers 1).
local function TargetDead()
    local ok, v = pcall(UnitIsDead, "target")
    if not ok then return false end
    if FS.IsSecret and FS.IsSecret(v) then return false end
    return v == true or v == 1
end

-- The row's look in colour `col` (nil: the empty row): the chip, track and fill in the colour, or the chip dimmed with the empty
-- label. The look latches (laneCol) only after every write succeeded, so a throw is retried by the next push.
local function LaneLook(col)
    if col == laneCol then return end
    local on = col ~= nil
    local c = col or K.steel
    L.jW, L.jFillShown, L.jText = nil, false, nil
    P.jFill:Hide()
    P.jTime:Hide()
    Solid(P.jTrack, c, C.JBAR_TRACK_A)
    Tint(P.chip.edge, c, 1)
    P.chip:SetAlpha(on and 1 or C.ABSENT_A)
    P.jEmpty:SetText(on and "" or L.laneText)
    if on then P.jFill:SetColorTexture(col[1], col[2], col[3], 1) end
    laneCol = col
end

-- The row for `rem` seconds left on the target: the bar's width against the 0 to 40 s axis (a longer debuff pins at full) and the
-- time. Both are written only when they change.
local function ApplyJudgeBar(rem)
    local w = BarWidth(rem, C.JMAX_S, C.JBAR_W)
    if w ~= L.jW then
        L.jW = w
        P.jFill:SetWidth(ui(w))
    end
    local show = w > 0
    if show ~= L.jFillShown then
        L.jFillShown = show
        P.jFill:SetShown(show)
    end
    local n = ceil(rem)
    if n > C.JMAX_S then n = C.JMAX_S end
    local text = WHOLE[n]
    if text ~= L.jText then
        L.jText = text
        P.jTime:SetText(text)
        P.jTime:Show()
    end
end

-- The debuff ran out before the Hud said so: the row empties at once (the Hud's late push for it, judged false, repaints nothing).
local function ExpireJudged()
    L.jExp = nil
    LaneLook(nil)
end

local function LiveJudged(now)
    local ea = L.jExp
    if not ea then return end
    local rem = ea - now
    if rem <= 0 then
        ExpireJudged()
        return
    end
    ApplyJudgeBar(rem)
end

local function LiveNone(now)
    if L.combat and not L.reduced then ApplyNoSeal(Pulse(now)) end
end

-- The seal ran out: flip to NO SEAL at once, wearing the last push's combat flag; the Hud's own push for the expiry (within
-- 0.2 s) then repaints nothing.
local function Expire()
    Paint("none", nil, L.combat, L.reduced)
    LaneLook(L.jExp and L.col or nil)           -- a debuff on the target follows the look's colour to red at once
end

local function LiveSeal(now)
    local ea = L.expiresAt
    local rem = nil
    if ea then
        rem = ea - now
        if rem <= 0 then
            Expire()
            LiveNone(now)
            return
        end
    end
    SetWarn(rem ~= nil and rem <= C.BAND_S, now)
    ApplyBar(rem)
end

local function Live(now)
    if mode == "seal" then
        LiveSeal(now)
    elseif mode == "none" then
        LiveNone(now)
    end
    LiveJudged(now)
end

-- Does anything move? A debuff on the target (its bar drains), a timed seal, the NO SEAL pulse in combat. Reduced motion drops
-- the pulse; the drains and the countdown still move.
local function Animating()
    if L.broken then return false end
    if L.jExp then return true end
    if mode == "seal" then return L.expiresAt ~= nil end
    return mode == "none" and L.combat and not L.reduced
end

-- The module's one OnUpdate. A throw stops the ticker (logged once) until the next push.
local function Tick()
    local now = GetTime()
    local ok, err = pcall(Live, now)
    if not ok then
        LogOnce("tick", err)
        L.broken = true
    end
    if not Animating() then Sync() end
end

-- Install the OnUpdate when something moves and the module is subscribed, clear it the moment nothing does.
function Sync()
    local want = false
    if subscribed and mod and Animating() then want = true end
    if want == ticking then return end
    ticking = want
    if want then
        mod:SetScript("OnUpdate", Tick)
    else
        mod:SetScript("OnUpdate", nil)
    end
end

Seals.Pulse, Seals.TimeText = Pulse, TimeText

-- ForeverSTUwaveDB.reducedMotion == true, the flag ConsoleKeys.lua reads (only an exact true counts). Read at each Hud push.
local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

-- A plain string key from our own ledger, mapped to a seal id; anything else is nil.
local function SealIdOf(seal)
    if type(seal) ~= "table" then return nil end
    local key = seal.key
    if FS.IsSecret and FS.IsSecret(key) then return nil end
    if type(key) ~= "string" then return nil end
    return KEY_ID[key]
end

-- The Hud's plain combat boolean; a secret, a non boolean or a missing flag is not combat (the guard comes first, a secret is
-- never compared).
local function CombatOf(state)
    local flag = state.inCombat
    if FS.IsSecret and FS.IsSecret(flag) then return false end
    return flag == true
end

-- mode, seal id, in combat. Only the NO SEAL look reads the combat flag, so no other look repaints when combat changes.
local function Resolve(state)
    if FS.IsSecret and FS.IsSecret(state) then return "unknown" end
    if type(state) ~= "table" then return "unknown" end
    local seal = state.seal
    if FS.IsSecret and FS.IsSecret(seal) then return "unknown" end
    if seal == false then return "none", nil, CombatOf(state) end
    local id = SealIdOf(seal)
    if id then return "seal", id end
    return "unknown"
end

-- One texture answer as a plain usable value: a positive finite number (a file id) or a non empty string, else nil.
local function ReadTexture(fn, id)
    local ok, tex = pcall(fn, id)
    if not ok then return nil end
    if FS.IsSecret and FS.IsSecret(tex) then return nil end
    if type(tex) == "number" and tex > 0 and tex < huge then return tex end
    if type(tex) == "string" and tex ~= "" then return tex end
    return nil
end

-- A spell's icon texture from its plain id, through C_Spell.GetSpellTexture or the legacy global; nil when the client will not say.
local function SpellIcon(id)
    if type(id) ~= "number" or id ~= id or id <= 0 or id == huge then return nil end
    local tex
    local modern = C_Spell and C_Spell.GetSpellTexture
    if type(modern) == "function" then tex = ReadTexture(modern, id) end
    if tex == nil and type(GetSpellTexture) == "function" then tex = ReadTexture(GetSpellTexture, id) end
    return tex
end

-- The Judgement spell id comes from the Hud's own spell table.
local function JudgeSpellId()
    local spells = FS.HudSpells
    local def = type(spells) == "table" and spells.jd
    local ids = type(def) == "table" and def.ids
    return type(ids) == "table" and ids[1] or nil
end

-- The first name of a HudSpells entry (the spell's own name, for the tooltip's combat fallback), or nil.
local function SpellName(key)
    local spells = FS.HudSpells
    local def = type(spells) == "table" and spells[key]
    local names = type(def) == "table" and def.names
    return type(names) == "table" and names[1] or nil
end

-- A plate wears its spell icon and hides its letters, or shows the letters when no icon is readable. Applies only on a push, so a
-- late client answer replaces the letters at the next one.
local function WearIcon(plate, letters, tex)
    if not tex then return false end
    plate.icon:SetTexture(tex)
    plate.icon:Show()
    letters:Hide()
    return true
end

-- One push: read the plain times, repaint if the look changed, then let the live layer write what moves. The look latches only
-- after Paint succeeded, so a throwing repaint is retried by the next push.
local function Apply(state)
    local newMode, id = Resolve(state)
    local reduce = ReducedMotion()
    local seal = newMode == "seal" and state.seal or nil
    L.broken = false
    L.combat = newMode ~= "unknown" and CombatOf(state) or false
    L.expiresAt = seal and Plain(seal.expiresAt) or nil
    if L.expiresAt and L.expiresAt - GetTime() <= 0 then
        newMode, id = "none", nil
    end
    local jid, jexp = JudgedOf(state)
    local dead = jid and TargetDead() or false                    -- a corpse carries no debuff row
    if dead then jexp = nil end
    L.jDead = dead
    L.jExp = jexp
    local combat = newMode == "none" and L.combat or false
    if newMode ~= mode or id ~= sealId or combat ~= inCombat or reduce ~= L.reduced then
        Paint(newMode, id, combat, reduce)
    end
    LaneLook(L.jExp and L.col or nil)
    if newMode == "seal" and not L.sealIcon then L.sealIcon = WearIcon(P.tile, P.ab, SpellIcon(Plain(seal.id))) end
    if not L.jIcon then L.jIcon = WearIcon(P.chip, P.jLetter, SpellIcon(JudgeSpellId())) end
    local FH = FS.FrameHelpers
    if FH and FH.SetTipSpell then
        -- Plain id or nothing (a secret falls back to the HudSpells name); NO SEAL and unknown have no spell to show.
        if newMode == "seal" then FH.SetTipSpell(P.tile, seal.id, SpellName(seal.key)) else FH.SetTipSpell(P.tile, nil, nil) end
        FH.SetTipSpell(P.chip, JudgeSpellId(), SpellName("jd"))
    end
    Live(GetTime())
    Sync()
end

local function OnState(state)
    if not subscribed then return end          -- a stale push after the module was hidden
    local ok, err = pcall(Apply, state)
    if not ok then LogOnce("state", err) end
end

-- Between Hud pushes (0.2 s apart) a retarget reads the Hud's own judgement at once, so the old target's bar never lingers; the
-- push that follows takes over. A dead target keeps its ledger entry, so UNIT_HEALTH empties the row (L.jDead) and relights it
-- on a resurrection.
-- The target's debuff straight from the Hud, only when the target GUID is plain: a secret GUID may mean the Hud has not seen the
-- retarget yet, so the row stays empty until the push. Returns the absolute expiresAt or nil.
local function ReadTarget(now)
    local ok, guid = pcall(UnitGUID, "target")
    if not ok or (FS.IsSecret and FS.IsSecret(guid)) then return nil end
    local _, e = ReadJudgement(now)
    return e
end

local function TargetMoved(event)
    local now = GetTime()
    local changed, dead = false, nil
    if event == "PLAYER_TARGET_CHANGED" then
        L.jExp = ReadTarget(now)
        changed = true
    elseif L.jDead then
        -- empty only because the target was dead: a resurrection relights it from the Hud's own read
        if TargetDead() then return end
        dead = false
        L.jExp = ReadTarget(now)
        changed = true
    end
    if L.jExp then
        if dead == nil then dead = TargetDead() end
        if dead then L.jExp = nil; changed = true end
    end
    L.jDead = dead or false
    if not changed then return end
    L.broken = false
    LaneLook(L.jExp and L.col or nil)
    Live(now)
    Sync()
end

local function OnTargetEvent(_, event)
    local ok, err = pcall(TargetMoved, event)
    if not ok then LogOnce("target", err) end
end

-- One frame on the module for the target change and the target's health. It is built bare and listens only while subscribed:
-- Subscribe registers, Unsubscribe unregisters.
local function BuildEvents()
    local f = CreateFrame("Frame", nil, mod)
    f:SetScript("OnEvent", OnTargetEvent)
    P.events = f
end

-- Only reached with the module built (Subscribe and Unsubscribe run from onShow and onHide after the build).
local function ListenTarget(on)
    local f = P.events
    if on then
        f:RegisterEvent("PLAYER_TARGET_CHANGED")
        pcall(f.RegisterUnitEvent, f, "UNIT_HEALTH", "target")      -- a client without the unit filter just gets no health event
    else
        f:UnregisterEvent("PLAYER_TARGET_CHANGED")
        f:UnregisterEvent("UNIT_HEALTH")
    end
end

-------------------------------------------------------------------------------
-- The GunsightAreas module: build, seat, onShow, onHide
-------------------------------------------------------------------------------

local function Subscribe()
    if subscribed or not mod then return end
    local Hud = FS.Hud
    if not (Hud and Hud.Subscribe) then
        LogOnce("nohud", "FS.Hud is missing, the Seal module has no data")
        return
    end
    subscribed = true
    Hud.Subscribe(OnState)                     -- pushes the current state at once
    local ok, err = pcall(ListenTarget, true)  -- the row works from pushes alone if the events cannot be had
    if not ok then LogOnce("listen", err) end
end

local function Unsubscribe()
    if not mod then return end
    if subscribed and FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnState) end
    subscribed = false
    ListenTarget(false)
    Sync()
end

-- The area hands the module its rect in image px; the module sits centred across rect.w from the rect's top.
local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y
    if mod then SeatAll() end
end

local function BuildModule(host)
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono and Theme.AddSliceTexture and Theme.ApplyNineSlice and Theme.SLICE_GLOW_TEXTURE
            and Theme.SLICE_CUT2_FILL_TEXTURE and Theme.SLICE_CUT2_OUTLINE_TEXTURE) then
        LogOnce("notheme", "Theme is missing, the Seal module is not built")
        return nil
    end
    if mod then return mod end
    laneCol = false
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightSeals", host)
    Seat(function()
        At(mod, "TOPLEFT", 0, 0)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        BuildTile()
        BuildBar()
        BuildJudgement()
        BuildEvents()
        Paint("unknown", nil, false, false)
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        return nil
    end
    Seals.frame, Seals.parts = mod, P
    return mod
end

local function OnAreaShown()
    Subscribe()
end

local function OnAreaHidden()
    Unsubscribe()
end

function Seals.Mode() return mode, sealId end

if FS.GunsightAreas and FS.GunsightAreas.RegisterModule then
    FS.GunsightAreas.RegisterModule("class", {
        classes = { "PALADIN" },
        build = BuildModule,
        seat = SeatModule,
        onShow = OnAreaShown,
        onHide = OnAreaHidden,
    })
end
