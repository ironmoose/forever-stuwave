-- PetDock.lua: the pet panel's CHROME (fill, stroke, halo, and the red low-HP edge twin) in two
-- modes, split out of PetFrame.lua (step S6 of the pet console dock port).
--
--   "float" (what a build with no drawn Console shows): the closed cut box PetFrame drew itself
--     before this file existed, the same two AddCut2Texture calls (the nine-sliced outline in
--     COLOR_POWER, the nine-sliced COLOR_HUD_SCRIM fill), pixel identical.
--   "dock": the open shoulder of the approved Gunsight mockup, option C (drawPet's dc branch,
--     peTrace with open = true). Top-left cut 6, a straight left side, the right foot flaring 10 px
--     at 45 degrees, the BOTTOM OPEN (the Console chassis closes it: no stroke, no halo), the fill
--     running 1.2 below the stroke so it merges into the chassis.
--
-- WHAT THE DOCK IS MADE OF (design px, art-local, y down, 1 unit = 1 design px because the art
-- frame is scaled by FS.Layout.Scale(), like Console.lua's art):
--   fill    COLOR_HUD_SCRIM, flat rects plus the baked TL c6 cut piece, and for the flare the
--           media/tab_slant.tga wedge flipped horizontally (solid bottom left, a "\" hypotenuse):
--           CastBars.lua's trick for a leaning edge, since a rect cannot lean.
--   stroke  Console.lua's recipe: plain 1 texel lines (top, left, right) plus the baked TL c6
--           corner piece (Theme.BORDER_CUT_TEXTURES[6][1]); the flare band is its own baked piece
--           (media/pet_dock_flare_line.tga). The literal "stroke wedge under the fill wedge" of
--           CastBars.lua does not work here: that fill is translucent, so a solid violet wedge under
--           it would tint the whole triangle. Baking just the 1 px band avoids that.
--   halo    DECOMPOSED strips, never a nine-slice (a nine-slice would light the open bottom and
--           the interior): glow_edge.tga along the top, left and right runs, glow_corner.tga at the
--           top right, glow_corner_cut.tga at the top left, and media/pet_dock_flare_glow.tga for the
--           last C.REACH px of the right run plus the flare (a 45 degree edge cannot be a strip).
--           Nothing is drawn below y = H. (A shoulder built with opts.chassis, the Paladin's, draws
--           the Console's OWN baked halo instead, plus media/shoulder_glow.tga for the three places
--           that texture cannot draw; see BuildChassisHalo.)
-- The two baked pieces come from media/generate_pet_dock_flare.py; every number it uses is in the C
-- table below and petdock-harness.py rasterizes the REAL files against the mockup.
--
-- SetMode only Shows and Hides non-secure CHILD frames of the pet container. The container is
-- implicitly protected (it parents the secure pet buttons: no Show, Hide, SetPoint or SetSize in
-- combat), so this file never calls any method on it: it only parents frames to it.
--
-- DOCKING (S8): Refresh decides between the two. While Console.IsDrawn() the panel is DOCKED: the
-- container's BOTTOMLEFT on FSConsole's TOPLEFT at (DOCK_X * scale, 0) (FS.PetFrame.SeatDocked, which
-- owns the container), the dock chrome, and the Console's top outline and halo opened under the panel
-- and its flare (Console.SetDockGap) for as long as the panel is docked, with a gap patch whose ALPHA
-- (Console.SetGapPatchAlpha, legal in combat) closes the hole whenever the panel is not visible. Otherwise (/fsconsole off, the
-- Console style off, /fsbars blizz, a build with no Console, or a dock chrome that failed to build)
-- it FLOATS: back on UIParent at its float seat (FS.PetFrame.SeatFloat), the closed float chrome, the
-- gap closed. Everything that touches the protected container or the Console's frames waits for
-- PLAYER_REGEN_ENABLED in combat (pendingDock); the Console is never anchored to the pet (the pet
-- anchors to the Console, one way). Refresh runs from FS.ActionBars.OnGeometry (every Console
-- seat, toggle and /fsbars switch, the Console's own callback having run first), from the pet
-- panel's visibility gate (SetPetShown), from PetFrame's rescale and at regen.
--
-- LOW HP (S7): the pet's health is secret in combat, so the low look is driven by ALPHA through
-- FS.PetFrame.SetLowHealthEdge(redEdge, { normalEdge }, pulseGroup): the red edge host takes the
-- Step curve's alpha, the normal edge frame the inverse, so a low pet shows red only (no cyan or
-- violet showing through the pulse trough). Each mode has its own red twin (same geometry, in
-- COLOR_RED); SetMode hands PetFrame the active mode's pair. PetFrame calls
-- FS.PetDock.AttachLowHealth() right after it builds the low-HP layer.
-- FS.PetDock.edge is the active mode's { host, pulseFrame, group, normal, base } hook;
-- FS.PetDock.edges.<mode> are both.
--
-- PetDock.NewShoulder(parent, W, H[, opts]) is the dock chrome as a REUSABLE constructor: the open
-- shoulder at any W x H (the pet panel's 348 x 68, the Paladin's 306.8 x 91.8 seal and aura block, which
-- the mockup's lsLive draws with this very recipe). The pet dock builds through it at its own size, so
-- there is one code path. See the Shoulder section below for the object it returns. With opts.chassis the
-- shoulder is drawn as part of the Console's chassis (its fill tint, its stroke alpha and its own baked halo,
-- Console.GLOW) and GapSpan reports the halo it really draws.
--
-- Headless check: python3 addons/petdock-harness.py

local _, FS = ...
FS.PetDock = FS.PetDock or {}
local PetDock = FS.PetDock

local Theme = FS.Theme

-------------------------------------------------------------------------------
-- Constants (design px). The mockup names are in the comments; the harness parses them back out
-- of the mockup HTML, so a mockup move fails there.
-------------------------------------------------------------------------------

local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
local FLARE_LINE_TEXTURE = MEDIA .. "pet_dock_flare_line.tga"
local FLARE_GLOW_TEXTURE = MEDIA .. "pet_dock_flare_glow.tga"
local WEDGE_TEXTURE = MEDIA .. "tab_slant.tga"
local SHOULDER_GLOW_TEXTURE = MEDIA .. "shoulder_glow.tga"

local C = {
    W = 348,             -- PE_G.dc.W, replaced at build by FS.Layout.petcontainer.w
    H = 68,              -- PE_G.dc.H, replaced at build by FS.Layout.petcontainer.h
    CUT = 6,             -- peTrace's c: the top-left cut
    FLARE = 10,          -- drawPet's f: the right foot's flare
    FILL_OVER = 1.2,     -- the fill polygon's overrun below the stroke (H + 1.2)
    -- Docked: the dock's left edge, design px right of the Console chassis' left edge (the mockup's
    -- PE_X less the chassis left, drawPet's open branch; the harness derives it). The Console's top
    -- line opens from DOCK_X + LINE to DOCK_X + W + FLARE - FOOT_UNDER: the line runs UNDER the
    -- straight left side (one px: the side's own column) and UNDER the flare's foot (its last stroke
    -- pixel is at W + FLARE - 1), so the vertical and the diagonal each land on a line pixel with no
    -- notch at the corner. The harness works the physical pixels out (petdock-harness junction checks).
    DOCK_X = 24,
    FOOT_UNDER = 1,
    LINE = 1,            -- the stroke is 1 texel, like Console.lua's (LINE)
    REACH = 7,           -- the mockup HALO table's widest radius
    STROKE_ALPHA = 0.9,  -- A(.9) on the stroke
    -- The red twin's stroke: the mockup's low stroke is A(.6 + .4 * pulse), which PEAKS at 1.0. The
    -- twin's Alpha animation (PULSE_TOP down to PULSE_FLOOR) multiplies this vertex alpha, so it
    -- must be 1.0 for the stroke to reach the mockup's peak (the normal stroke stays at .9).
    LOW_STROKE_ALPHA = 1.0,
    HALO_ALPHA = 0.76,   -- the HALO table's stacked alpha (.585) x the pet panel's glow factor 1.3
    -- Mirrors PetFrame.lua's LOW_PULSE_* and LOW_EDGE_GLOW_ALPHA (the harness compares them).
    PULSE_TOP = 1.0,
    PULSE_FLOOR = 0.6,
    PULSE_LEG = 0.55,
    LOW_GLOW_ALPHA = 0.5,
    -- The baked pieces: a 128 canvas with the piece at its top left, k texels per design px.
    CANVAS = 128,
    LINE_K = 10,         -- pet_dock_flare_line.tga
    GLOW_K = 7,          -- pet_dock_flare_glow.tga
    CUT_CANVAS = 16,     -- Theme's cut pieces: a 16 canvas, the piece at the top left
    -- media/shoulder_glow.tga (media/generate_shoulder_glow.py): the three pieces of a chassis shoulder's halo
    -- that the Console's own glow texture cannot draw, baked with the Console's stepped profile, one texel per
    -- design px. Rects are { x, y, w, h } texels of the 64 canvas, the piece itself (the 2 texel margin around
    -- it is more of the same field, for the bilinear filter). TL is the halo around the top left cut (CUT) and
    -- its two arms, GLOW_PAD + CUT square; FLARE is the last stretch of the right side, the vertex and the foot
    -- out to where it stops outshining the chassis line (15 wide: the foot ends 10.2 out and its diagonal
    -- still beats the line above it for 0.41 x the 9.5 px reach more), ABOVE px of the side above the
    -- vertex; BL is the concave corner where the left
    -- side meets the chassis top line. PAD is the Console glow's texels from its edge to the outline (the
    -- generator's GLOW_PAD): a Console glow with another pad does not match these pieces.
    SHOULDER_GLOW = {
        CANVAS = 64,
        PAD = 11,
        ABOVE = 12,
        TL = { 2, 2, 17, 17 },
        FLARE = { 26, 2, 15, 22 },
        BL = { 48, 2, 11, 11 },
    },
}
PetDock.C = C

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local container
local built = false
local lowReady = false          -- PetFrame built its low-HP layer
local mode = "float"
local pendingScale = false
local pendingDock = false          -- a Refresh waits for regen (combat, or the Console refused the gap)
local petShown = false             -- the pet panel's visibility gate says shown (PetFrame.Apply)
local gapOpen = false              -- the Console's top line is open under the docked panel (SetDockGap)
local gapOwner = nil               -- another owner (a class shoulder) holds the Console's gap: this file leaves it alone
local gapReclaimed = false         -- the gap came back in combat: the owner's span still stands until the regen Refresh

local dockShoulder              -- the NewShoulder object the pet's dock chrome is (nil when the dock failed to build)
local frames = {}               -- frames.float, frames.dock: the chrome roots (the only things Shown / Hidden)
local edges = {}                -- edges.float, edges.dock: { host, pulseFrame, group, normal, base }
local function NewDockParts()
    return { fill = {}, stroke = {}, halo = {}, red = { stroke = {}, halo = {} } }
end
local parts = {                 -- texture handles, for the harness and the retint hook
    float = {},
    dock = NewDockParts(),
}
PetDock.frames, PetDock.edges, PetDock.parts = frames, edges, parts

-------------------------------------------------------------------------------
-- Helpers
-------------------------------------------------------------------------------

-- Seats a texture at design px (x, y down) of `art`, w x h.
local function Place(art, tex, x, y, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", art, "TOPLEFT", x, -y)
    tex:SetSize(w, h)
end

local function NewTexture(frame, layer, texture, blend)
    local tex = frame:CreateTexture(nil, layer)
    tex:SetTexture(texture)
    if blend then tex:SetBlendMode(blend) end
    return tex
end

-- A plain frame filling `parent`, at an explicit level (a chrome frame must not take the child
-- default of parent + 1 at the roots: the slots sit strictly higher by frame level, SLOT_LEVEL_OFFSET = 2).
local function NewLayer(parent, level)
    local frame = CreateFrame("Frame", nil, parent)
    frame:SetAllPoints(parent)
    frame:SetFrameLevel(level)
    return frame
end

-- The pulse of the red edge: the mockup's .6 + .4 * pulse on a 1.1 s period, as a bouncing Alpha
-- animation on a CHILD of the curve driven host, so the two alphas multiply.
local function NewPulse(frame)
    local group = frame:CreateAnimationGroup()
    group:SetLooping("BOUNCE")
    local pulse = group:CreateAnimation("Alpha")
    pulse:SetFromAlpha(C.PULSE_TOP)
    pulse:SetToAlpha(C.PULSE_FLOOR)
    pulse:SetDuration(C.PULSE_LEG)
    pulse:SetSmoothing("IN_OUT")
    return group
end

local function Tint(tex, color, alpha)
    tex:SetVertexColor(color[1], color[2], color[3], alpha)
end

-------------------------------------------------------------------------------
-- Dock chrome
-------------------------------------------------------------------------------

-- Texcoord of a baked cut piece sitting at the top left of its 16 canvas.
local function CutPieceCoord(c)
    local u = c / C.CUT_CANVAS
    return 0, u, 0, u
end

-- The fill: scrim flat rects plus the baked TL cut piece, and the flipped tab_slant wedge for
-- the flare. The wedge's hypotenuse lies on the stroke's centreline.
-- With `chassis` (a shoulder drawn as part of the Console's chassis, see NewShoulder) the fill wears the
-- chassis' own tint and does NOT overrun into the Console's line row: the chassis fill already covers it,
-- and a second translucent layer there would double the alpha.
local function BuildDockFill(art, W, H, list, chassis)
    local c, f = C.CUT, C.FLARE
    local over = chassis and 0 or C.FILL_OVER
    local fx = W - C.LINE / 2          -- where the flare's centreline leaves the right line
    local scrim = chassis and chassis.fill or Theme.COLOR_HUD_SCRIM
    local function piece(texture, x, y, w, h, l, r, t, b)
        local tex = NewTexture(art, "BACKGROUND", texture)
        Tint(tex, scrim, scrim[4])
        if l then tex:SetTexCoord(l, r, t, b) end
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
        return tex
    end
    piece(Theme.FILL_CUT_TEXTURES[c], 0, 0, c, c, CutPieceCoord(c))
    piece(Theme.FLAT_TEXTURE, c, 0, W - c, c)
    piece(Theme.FLAT_TEXTURE, 0, c, W, H - f - c)
    piece(Theme.FLAT_TEXTURE, 0, H - f, fx, f)
    -- The wedge rect stops at H but keeps the committed mapping of the WHOLE flipped texture across
    -- f + over (so the diagonal's anti-alias band and the hypotenuse are exactly as approved): the
    -- texcoords crop the overrun part instead of squeezing the texture into f.
    local whole = f + over
    piece(WEDGE_TEXTURE, fx, H - f, f, f, 1, 1 - f / whole, 0, f / whole)
    -- The overrun into the Console's top line row covers ONLY the open part of that row, between the
    -- two line pixels that run under the panel (the left side's column and the foot's last pixel): the
    -- translucent scrim over a lit line pixel would dim it to about half and read as the notch again.
    if over > 0 then
        piece(Theme.FLAT_TEXTURE, C.LINE, H, W + f - C.FOOT_UNDER - C.LINE, over)
    end
end

-- The stroke: 1 texel lines, the baked TL corner, the baked flare band. Built into `frame`.
local function BuildDockStroke(art, W, H, frame, color, list, alpha)
    local c, f, line = C.CUT, C.FLARE, C.LINE
    local function piece(texture, x, y, w, h, l, r, t, b)
        local tex = NewTexture(frame, "BORDER", texture)
        Tint(tex, color, alpha)
        if l then tex:SetTexCoord(l, r, t, b) end
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
    end
    piece(Theme.BORDER_CUT_TEXTURES[c][1], 0, 0, c, c, CutPieceCoord(c))
    piece(Theme.FLAT_TEXTURE, c, 0, W - c, line)                 -- top
    piece(Theme.FLAT_TEXTURE, 0, c, line, H - c)                 -- left
    piece(Theme.FLAT_TEXTURE, W - line, 0, line, H - f)          -- right, down to the flare
    -- The flare band: 12 x 10 px from (W - 2, H - f), a 1 px stroke along (W - .5, H - f) to the foot.
    local bandW = f + 2
    piece(FLARE_LINE_TEXTURE, W - 2, H - f, bandW, f,
        0, bandW * C.LINE_K / C.CANVAS, 0, f * C.LINE_K / C.CANVAS)
end

-- The halo: strips only, nothing below y = H. Built into `frame`.
local function BuildDockHalo(art, W, H, frame, color, list, alpha)
    local c, f, r = C.CUT, C.FLARE, C.REACH
    alpha = alpha or C.HALO_ALPHA
    local function piece(texture, x, y, w, h, ...)
        local tex = NewTexture(frame, "BACKGROUND", texture, "ADD")
        Tint(tex, color, alpha)
        tex:SetTexCoord(...)
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
    end
    -- The same orientations Theme.AddOuterGlow gives its strips: the bright end faces the stroke.
    piece(Theme.GLOW_CORNER_CUT_TEXTURE, -r, -r, c + r, c + r, 0, 1, 0, 1)                 -- around the TL cut
    piece(Theme.GLOW_EDGE_TEXTURE, c, -r, W - c, r, 0, 1, 0, 0, 1, 1, 1, 0)               -- top
    piece(Theme.GLOW_CORNER_TEXTURE, W, -r, r, r, 0.5, 0, 0.5, 0.5, 1, 0, 1, 0.5)         -- the square TR corner
    piece(Theme.GLOW_EDGE_TEXTURE, W, 0, r, H - f - r, 0, 0, 0, 0, 0, 1, 0, 1)            -- right, down to the flare zone
    local zone = f + r
    local u = zone * C.GLOW_K / C.CANVAS
    piece(FLARE_GLOW_TEXTURE, W, H - f - r, zone, zone, 0, u, 0, u)                         -- the vertex and the flare
    piece(Theme.GLOW_EDGE_TEXTURE, -r, c, r, H - c, 0, 1, 0, 1, 0, 0, 0, 0)               -- left
end

-- The halo of a shoulder that is part of the Console's chassis: the Console's OWN baked halo, strip for strip,
-- so the stepped profile (the mockup's four nested strokes composited, .546 at the edge down to nothing by 10 px)
-- is the Console's by construction. `halo` is Console.GLOW { texture, size, pad, margin, mid0, mid1 }; the
-- straight runs and the square top right corner take the UV windows Console.lua's SeatHalo gives its own, and
-- the three places that texture cannot draw (the top left cut 6, the vertex and the 45 degree foot, the concave
-- corner where the left side meets the chassis top) come from media/shoulder_glow.tga. Seven source-over pieces
-- that tile exactly (a second layer anywhere would composite twice), vertex alpha `alpha` (1 = the Console's):
--   TL (atlas)   x -pad..cut,        y -pad..cut             top left cut and its arms
--   top          x cut..W-(m-pad),   y -pad..0               Console strip
--   TR           x W-(m-pad)..W+pad, y -pad..m-pad           Console block, the square corner
--   right        x W..W+pad,         y m-pad..H-f-ABOVE      Console strip
--   FLARE (atlas) x W..W+15,         y H-f-ABOVE..H          vertex, foot, out to where the line takes over
--   left         x -pad..0,          y cut..H-pad            Console strip
--   BL (atlas)   x -pad..0,          y H-pad..H              concave corner
-- Nothing is drawn below y = H (the chassis closes the bottom).
local function BuildChassisHalo(art, W, H, frame, color, list, alpha, halo)
    local c, f, g = C.CUT, C.FLARE, halo.pad
    local n, m, mid0, mid1 = halo.size, halo.margin, halo.mid0 / halo.size, halo.mid1 / halo.size
    local atlas = C.SHOULDER_GLOW
    local function piece(texture, x, y, w, h, l, r, t, b)
        local tex = NewTexture(frame, "BACKGROUND", texture)
        Tint(tex, color, alpha)
        tex:SetTexCoord(l, r, t, b)
        Place(art, tex, x, y, w, h)
        list[#list + 1] = tex
    end
    local function cell(rect)
        local k = atlas.CANVAS
        return rect[1] / k, (rect[1] + rect[3]) / k, rect[2] / k, (rect[2] + rect[4]) / k
    end
    local corner = m - g                 -- how far the square corner block reaches in from the outline
    local sideEnd = H - f - atlas.ABOVE  -- where the right strip hands over to the flare piece
    piece(SHOULDER_GLOW_TEXTURE, -g, -g, g + c, g + c, cell(atlas.TL))
    piece(halo.texture, c, -g, W - corner - c, g, mid0, mid1, 0, g / n)
    piece(halo.texture, W - corner, -g, m, m, 1 - m / n, 1, 0, m / n)
    piece(halo.texture, W, corner, g, sideEnd - corner, 1 - g / n, 1, mid0, mid1)
    piece(SHOULDER_GLOW_TEXTURE, W, sideEnd, atlas.FLARE[3], atlas.FLARE[4], cell(atlas.FLARE))
    piece(halo.texture, -g, c, g, H - g - c, 0, g / n, mid0, mid1)
    piece(SHOULDER_GLOW_TEXTURE, -g, H - g, g, g, cell(atlas.BL))
end

local function FillEdge(art, W, H, frame, color, strokeList, haloList, strokeAlpha, haloAlpha, chassisHalo)
    if chassisHalo then
        BuildChassisHalo(art, W, H, frame, color, haloList, haloAlpha, chassisHalo)
    else
        BuildDockHalo(art, W, H, frame, color, haloList, haloAlpha)
    end
    BuildDockStroke(art, W, H, frame, color, strokeList, strokeAlpha)
end

-------------------------------------------------------------------------------
-- The shoulder: the dock chrome as a constructor
-------------------------------------------------------------------------------

-- The Console's top gap for a shoulder whose left edge is `dockX` design px right of the chassis left and
-- whose width is `W`, as SetDockGap's four arguments (console-local design px): the LINE's span runs
-- under the straight left side and under the flare's foot (see C.DOCK_X), the HALO's span is the approved
-- one, a pixel OUTSIDE both (the Console's glow stays out of the columns the shoulder's own side glow and
-- flare glow already shine in: the line may run under the shoulder, the glow may not). `haloPad` is how far the
-- shoulder's own halo reaches left of its side and `haloOut` right of it (a chassis shoulder draws the Console's
-- own halo there: GLOW_PAD px left, the FLARE piece's width right; the pet dock's strips start a pixel out each
-- side): the Console's glow must end where that begins.
local function SpanFor(dockX, W, haloPad, haloOut)
    return dockX + C.LINE, dockX + W + C.FLARE - C.FOOT_UNDER,
        dockX - (haloPad or C.LINE), dockX + W + (haloOut or C.FLARE + C.LINE)
end

local ANCHOR_POINTS = {
    TOPLEFT = true, TOP = true, TOPRIGHT = true, LEFT = true, CENTER = true, RIGHT = true,
    BOTTOMLEFT = true, BOTTOM = true, BOTTOMRIGHT = true,
}

-- (No `v == v` term: NaN fails both comparisons against infinity anyway.)
local function IsFinite(v)
    return type(v) == "number" and v > -math.huge and v < math.huge
end

-- What a shoulder is made of, so a caller can reach it: art (the scaled frame, 1 unit = 1 design px, a
-- non-secure child of `parent`), W and H, the texture lists fill / stroke / halo, normal (the frame the
-- violet edge is drawn on, so a curve can fade it) and, only with opts.red, red = { host (the frame a curve
-- drives the alpha of, starts at 0), pulseFrame (its child, which the pulse animates), group (the pulse's
-- AnimationGroup, not started), stroke, halo } (the same geometry in COLOR_RED).
local Shoulder = {}
Shoulder.__index = Shoulder

-- Re-anchors the art: `point` of the art on `relPoint` of `relTo` at (x, y), design px of the art's own scale
-- space (the offsets are in the ART's units, so they scale with it). No arguments seat it back on the
-- parent's top left, where it is built. False (and the previous anchors stay) for a bad point or number, or
-- when the client refuses the anchor (a circular dependency, say): the old anchors are put back.
-- COMBAT: legal only while NO secure frame is anchored to the art (a secure child or anchor target makes it
-- restricted, and ClearAllPoints / SetPoint / SetScale / SetFrameLevel are then refused in combat; SetAlpha
-- never is). The pet dock and the Paladin shoulder hold none; a caller that anchors secure frames to `art`
-- seats it out of combat only.
function Shoulder:Seat(point, relTo, relPoint, x, y)
    if point == nil then point = "TOPLEFT" end
    if relTo == nil then relTo = self.parent end
    if relPoint == nil then relPoint = point end
    if x == nil then x = 0 end
    if y == nil then y = 0 end
    if not (ANCHOR_POINTS[point] and ANCHOR_POINTS[relPoint] and type(relTo) == "table"
        and IsFinite(x) and IsFinite(y)) then
        return false
    end
    local art = self.art
    local saved = {}
    local counted, n = pcall(art.GetNumPoints, art)
    if counted and type(n) == "number" then
        for i = 1, n do
            local got, p, rel, rp, px, py = pcall(art.GetPoint, art, i)
            if got and p then saved[#saved + 1] = { p, rel, rp, px, py } end
        end
    end
    local seated = pcall(function()
        art:ClearAllPoints()
        art:SetPoint(point, relTo, relPoint, x, y)
    end)
    if seated then return true end
    for _, a in ipairs(saved) do pcall(art.SetPoint, art, a[1], a[2], a[3], a[4], a[5]) end
    return false
end

-- The art's scale: `scale`, or FS.Layout.Scale() with no argument. False for a scale that is not a
-- positive number. It also re-reads the parent's frame level and puts the art and its layers back on it (the
-- level is read once at build, so a parent that was re-levelled since would otherwise leave the chrome
-- behind). Build after the host's level is final where you can; same COMBAT rule as Seat.
function Shoulder:Rescale(scale)
    if scale == nil then scale = FS.Layout.Scale() end
    if not (IsFinite(scale) and scale > 0) then return false end
    self.art:SetScale(scale)
    local got, level = pcall(self.parent.GetFrameLevel, self.parent)
    if got and IsFinite(level) then
        self.art:SetFrameLevel(level)
        self.normal:SetFrameLevel(level)
        if self.red then
            self.red.host:SetFrameLevel(level + 1)
            self.red.pulseFrame:SetFrameLevel(level + 1)
        end
    end
    return true
end

-- The whole shoulder's alpha, 0 to 1. Alpha is legal in combat. False for anything else.
function Shoulder:SetAlpha(alpha)
    if not (IsFinite(alpha) and alpha >= 0 and alpha <= 1) then return false end
    self.art:SetAlpha(alpha)
    return true
end

-- The Console gap for a shoulder standing `dockX` design px in from the chassis left: line x0, line x1, halo
-- x0, halo x1 (SpanFor). Nothing for a dockX that is not a number.
function Shoulder:GapSpan(dockX)
    if not IsFinite(dockX) then return nil end
    return SpanFor(dockX, self.W, self.haloPad, self.haloOut)
end

-- Retints the NORMAL edge (the red twin is never retinted): r, g, b of `color`, the stroke at strokeAlpha and
-- the halo at haloAlpha (default the mockup's). False for a colour that is not three numbers or an alpha that
-- is not a number.
function Shoulder:SetEdge(color, strokeAlpha, haloAlpha)
    if type(color) ~= "table" or type(color[1]) ~= "number" or type(color[2]) ~= "number"
        or type(color[3]) ~= "number" then
        return false
    end
    if (strokeAlpha ~= nil and type(strokeAlpha) ~= "number") or (haloAlpha ~= nil and type(haloAlpha) ~= "number") then
        return false
    end
    strokeAlpha, haloAlpha = strokeAlpha or self.strokeAlpha, haloAlpha or self.haloAlpha
    for _, tex in ipairs(self.stroke) do Tint(tex, color, strokeAlpha) end
    for _, tex in ipairs(self.halo) do Tint(tex, color, haloAlpha) end
    return true
end

-- opts.chassis = { fill = { r, g, b, a }, strokeAlpha, haloAlpha, halo } -> the validated copy, or nil. A
-- shoulder the Console's chassis outline carries (the mockup's default Console style) is not the pet panel: it
-- wears the chassis fill tint, the chassis stroke alpha, and the CONSOLE'S OWN halo (`halo` = Console.GLOW, the
-- baked texture and its strip windows; `haloAlpha` is a vertex alpha multiplier on that profile, 1 = the
-- Console's), and has no fill overrun.
local function ReadHalo(halo)
    if type(halo) ~= "table" or type(halo.texture) ~= "string" or halo.texture == "" then return nil end
    local size, pad, margin, mid0, mid1 = halo.size, halo.pad, halo.margin, halo.mid0, halo.mid1
    if not (IsFinite(size) and IsFinite(pad) and IsFinite(margin) and IsFinite(mid0) and IsFinite(mid1)) then
        return nil
    end
    -- a side of the baked square, an outline pad that is the atlas' own, a corner block wider than the pad and
    -- narrower than the texture, a straight middle band inside the texture
    if not (size > 0 and pad == C.SHOULDER_GLOW.PAD and margin > pad and margin < size
        and mid0 >= 0 and mid0 < mid1 and mid1 <= size) then
        return nil
    end
    return { texture = halo.texture, size = size, pad = pad, margin = margin, mid0 = mid0, mid1 = mid1 }
end

local function ReadChassis(chassis)
    if type(chassis) ~= "table" or type(chassis.fill) ~= "table" then return nil end
    local fill = {}
    for i = 1, 4 do
        local v = chassis.fill[i]
        if not (IsFinite(v) and v >= 0 and v <= 1) then return nil end
        fill[i] = v
    end
    local stroke, halo = chassis.strokeAlpha, chassis.haloAlpha
    if not (IsFinite(stroke) and stroke >= 0 and stroke <= 1 and IsFinite(halo) and halo >= 0 and halo <= 1) then
        return nil
    end
    local look = ReadHalo(chassis.halo)
    if not look then return nil end
    return { fill = fill, strokeAlpha = stroke, haloAlpha = halo, halo = look }
end

-- Builds a shoulder of W x H design px as a child of `parent`, on `parent`'s frame level, top left on the
-- parent's top left, scaled by FS.Layout.Scale(). opts.red = true adds the red low-HP twin (the pet panel
-- only; the mockup's shoulders have no low state). Returns the object, or nil and a reason for a bad
-- argument (a parent that is not a frame, a W or H not above C.CUT + C.FLARE, opts that is not a table);
-- builds nothing then. opts.chassis (see ReadChassis; a bad value is a bad argument) draws it as part of the
-- Console chassis instead of the pet panel's recipe. A throw while building hides the half built art frame (a child of `parent`, which
-- may be protected: build out of combat) and is rethrown as it was, so the caller decides what to log.
-- COMBAT: Seat, Rescale and every method that anchors, scales or re-levels the art are legal in combat only
-- while no secure frame is anchored to (or parented under) the art; SetAlpha always is. The parent's frame
-- level is read here, at build: create the shoulder after its host's level is final (Rescale re-reads it).
function PetDock.NewShoulder(parent, W, H, opts)
    if type(parent) ~= "table" or type(parent.GetFrameLevel) ~= "function" then
        return nil, "NewShoulder needs a parent frame"
    end
    local least = C.CUT + C.FLARE
    if not (IsFinite(W) and IsFinite(H) and W > least and H > least) then
        return nil, "NewShoulder needs a width and a height above " .. least
    end
    if opts ~= nil and type(opts) ~= "table" then
        return nil, "NewShoulder needs opts to be a table"
    end

    local chassis
    if opts ~= nil and opts.chassis ~= nil then
        chassis = ReadChassis(opts.chassis)
        if not chassis then
            return nil, "NewShoulder needs opts.chassis to be { fill = { r, g, b, a }, strokeAlpha, haloAlpha, "
                .. "halo = Console.GLOW }"
        end
        -- the Console's halo strips and the baked corner pieces tile only on a block big enough to hold them
        local across = chassis.halo.margin - chassis.halo.pad
        if W <= C.CUT + across or H <= C.FLARE + C.SHOULDER_GLOW.ABOVE + across then
            return nil, "NewShoulder needs a larger block for the Console's halo"
        end
    end

    local shoulder = setmetatable({ parent = parent, W = W, H = H, fill = {}, stroke = {}, halo = {},
        strokeAlpha = chassis and chassis.strokeAlpha or C.STROKE_ALPHA,
        haloAlpha = chassis and chassis.haloAlpha or C.HALO_ALPHA,
        haloPad = chassis and chassis.halo.pad or nil,
        haloOut = chassis and C.SHOULDER_GLOW.FLARE[3] or nil }, Shoulder)
    local level = parent:GetFrameLevel()
    local art = CreateFrame("Frame", nil, parent)
    shoulder.art = art
    local ok, err = pcall(function()
        art:SetFrameLevel(level)
        art:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, 0)
        art:SetSize(W, H)
        art:SetScale(FS.Layout.Scale())
        BuildDockFill(art, W, H, shoulder.fill, chassis)

        -- The normal edge (violet, the mockup's `col`), one frame so the inverse curve can fade it.
        local normal = NewLayer(art, level)
        shoulder.normal = normal
        FillEdge(art, W, H, normal, Theme.COLOR_BORDER, shoulder.stroke, shoulder.halo,
            shoulder.strokeAlpha, shoulder.haloAlpha, chassis and chassis.halo or nil)

        if opts and opts.red == true then
            -- The red twin: host (the curve alpha) > pulse child (the Alpha animation) > the same geometry in red.
            local red = { stroke = {}, halo = {} }
            red.host = NewLayer(art, level + 1)
            red.host:SetAlpha(0)
            red.pulseFrame = NewLayer(red.host, level + 1)
            FillEdge(art, W, H, red.pulseFrame, Theme.COLOR_RED, red.stroke, red.halo, C.LOW_STROKE_ALPHA)
            red.group = NewPulse(red.pulseFrame)
            shoulder.red = red
        end
    end)
    if not ok then
        pcall(art.Hide, art)
        error(err, 0)
    end
    return shoulder
end

-- The pet's dock chrome IS a shoulder at the panel's own size (ONE code path with every other shoulder):
-- the module's public tables are that object's parts.
local function BuildDock()
    local shoulder, why = PetDock.NewShoulder(container, C.W, C.H, { red = true })
    if not shoulder then error(why, 0) end
    dockShoulder = shoulder
    frames.dock = shoulder.art
    parts.dock = {
        fill = shoulder.fill, stroke = shoulder.stroke, halo = shoulder.halo,
        red = { stroke = shoulder.red.stroke, halo = shoulder.red.halo },
    }
    edges.dock = { host = shoulder.red.host, pulseFrame = shoulder.red.pulseFrame, group = shoulder.red.group,
        normal = shoulder.normal, base = { shoulder.normal } }
end

-- The dock chrome is built in its OWN pcall, so a throw in the unused dock art can never take the
-- approved default float look (or the rest of the pet UI) down with it: PetFrame calls Build inside
-- its own pcall, and one throw here used to abort the whole container. A failure is logged once, the
-- half built art is hidden and forgotten, and the panel stays in "float" (SetMode("dock") then
-- refuses). Built eagerly rather than lazily on the first SetMode("dock"): Build runs out of combat
-- (PetFrame defers its init to PLAYER_REGEN_ENABLED), and everything that parents to the protected
-- container has to happen there.
local function TryBuildDock()
    local ok, err = pcall(BuildDock)
    if ok then return true end
    if frames.dock then pcall(frames.dock.Hide, frames.dock) end   -- the art is a child of the container
    dockShoulder, frames.dock, edges.dock = nil, nil, nil
    parts.dock = NewDockParts()
    FS.LogDegradeOnce("petdock_dock_build",
        "|cffff4488Forever STUwave|r: pet dock chrome failed to build (" .. tostring(err)
            .. "); the floating pet panel is used instead.")
    return false
end

-------------------------------------------------------------------------------
-- Float chrome: exactly what PetFrame built before the move
-------------------------------------------------------------------------------

local function BuildFloat()
    local level = container:GetFrameLevel()
    local root = NewLayer(container, level)
    frames.float = root

    -- The outline on its own frame so the inverse curve can fade it; it draws below every slot.
    local outline = NewLayer(root, level)
    parts.float.outline = Theme.AddCut2Texture(outline, Theme.SLICE_CUT2_OUTLINE_TEXTURE, Theme.COLOR_POWER, "BORDER")

    -- Dark interior fill: a nine-sliced chamfer texture at inset 0 so it meets the stroke flush,
    -- BACKGROUND, behind every slot. COLOR_HUD_SCRIM is the Gunsight panel fill.
    parts.float.fill = Theme.AddCut2Texture(root, Theme.SLICE_CUT2_FILL_TEXTURE, Theme.COLOR_HUD_SCRIM,
        "BACKGROUND", nil, 0)

    -- The red twin: PetFrame's own default recipe (ring plus glow on the panel rect).
    local host = NewLayer(root, level + 1)
    host:SetAlpha(0)
    local pulseFrame = NewLayer(host, level + 1)
    Theme.SkinButton(pulseFrame, {
        chamfer = Theme.SLICE_CUT_MARGIN,
        glowAlpha = C.LOW_GLOW_ALPHA,
        borderColor = Theme.COLOR_RED,
    })
    local skin = pulseFrame.fsSkin
    if skin then
        local red = Theme.COLOR_RED
        skin.border.ring:SetVertexColor(red[1], red[2], red[3], 1)
        skin.glow:SetVertexColor(red[1], red[2], red[3], C.LOW_GLOW_ALPHA)
    end
    edges.float = { host = host, pulseFrame = pulseFrame, group = NewPulse(pulseFrame), normal = outline,
        base = { outline } }
end

-------------------------------------------------------------------------------
-- Mode
-------------------------------------------------------------------------------

-- Hands PetFrame the active mode's red edge and normal edge (the low-HP layer drives their alphas).
-- SetLowHealthEdge hides the previous red host, so the new one is shown first.
local function AttachLow()
    local petFrame = FS.PetFrame
    if not (lowReady and built and petFrame and petFrame.SetLowHealthEdge) then return end
    local edge = edges[mode]
    edge.host:Show()
    if petFrame.SetLowHealthEdge(edge.host, edge.base, edge.group) then
        petFrame.lowEdgePulse = edge.pulseFrame
    end
end

local function Apply()
    local other = mode == "dock" and "float" or "dock"
    frames[mode]:Show()
    if frames[other] then frames[other]:Hide() end   -- no dock frame when the dock build failed
    PetDock.edge = edges[mode]
    AttachLow()
end

-- "dock" or "float". Remembers the mode before the panel is built and applies it then. Only Shows and
-- Hides this file's own non-secure frames, so it is legal in combat; the container is never touched.
-- False (and nothing changes) for any other value, and for "dock" once the dock chrome failed to build
-- (the floating panel stays).
function PetDock.SetMode(newMode)
    if newMode ~= "dock" and newMode ~= "float" then return false end
    if newMode == "dock" and built and not frames.dock then return false end
    mode = newMode
    if built then Apply() end
    return true
end

function PetDock.GetMode()
    return mode
end

-- Returns true only after Build when the dock chrome built successfully.
function PetDock.HasDock()
    return frames.dock ~= nil
end

-------------------------------------------------------------------------------
-- Docking onto the Console
-------------------------------------------------------------------------------

-- The Console, only when this build has the whole API this file uses (IsDrawn, SetDockGap,
-- SetGapPatchAlpha, the root frame) and the chassis is drawn right now. Feature-detected: a missing Console or ActionBars file
-- leaves the panel floating.
local function DrawnConsole()
    local console = FS.Console
    if type(console) ~= "table" or type(console.IsDrawn) ~= "function"
        or type(console.SetDockGap) ~= "function" or type(console.SetGapPatchAlpha) ~= "function" then
        return nil
    end
    local ok, drawn = pcall(console.IsDrawn)
    if ok and drawn == true and console.root then return console end
    return nil
end

local function CanSeat(pet)
    return type(pet) == "table" and pet.SeatDocked and pet.SeatFloat and pet.IsDocked
end

-- The Console's top gap for the docked pet panel, console-local design px, as SetDockGap's four
-- arguments (SpanFor, at the dock's offset and the panel's width). PetDock.GapSpan is read by the harness.
local function GapSpan()
    return SpanFor(C.DOCK_X, C.W)
end
PetDock.GapSpan = GapSpan

-- The Console's gap patch (a line and halo over the gap, the top line's own recipe) closes the hole by
-- ALPHA while the pet panel is not visible. Alpha is legal in combat, so this runs from SetPetShown in
-- combat too. Cosmetic: a throw is logged once and never undocks the panel.
local warnedPatch = false
local function ApplyPatch()
    if gapOwner ~= nil or gapReclaimed then return end   -- a class shoulder holds (or, until regen, still has) the gap: its line stays open
    local api = FS.Console
    if type(api) ~= "table" or type(api.SetGapPatchAlpha) ~= "function" then return end
    local ok, err = pcall(api.SetGapPatchAlpha, petShown and 0 or 1)
    if not ok and not warnedPatch then
        warnedPatch = true
        FS.LogDegradeOnce("petdock_gap_patch",
            "|cffff4488Forever STUwave|r: closing the Console line under the pet panel failed (" .. tostring(err) .. ").")
    end
end

-- Docks the panel while the Console is drawn, floats it otherwise, and keeps the Console's top line
-- open (gap plus patch) exactly while the panel is docked. `force` re-seats a docked panel even when nothing
-- changed (a rescale moved the offset and the size). In combat (the container is protected, and the
-- Console refuses SetDockGap there) nothing is touched: pendingDock replays it at regen. Returns
-- true when it ran. A dock chrome that failed to build means float forever (no Refresh at all).
local function RefreshBody(force)
    if not (built and frames.dock) then return false end
    if InCombatLockdown() then
        pendingDock = true
        return false
    end
    local pet = FS.PetFrame
    if not CanSeat(pet) then return false end
    pendingDock = false
    if gapReclaimed then
        gapReclaimed = false
        gapOpen = true   -- what the Console holds is the old owner's span: ask again, or close it
    end

    local console = DrawnConsole()
    local wantGap = false
    if console then
        if force or not pet.IsDocked() then
            if not pet.SeatDocked(console.root, C.DOCK_X * FS.Layout.Scale()) then
                pendingDock = true
                return false
            end
        end
        if mode ~= "dock" then PetDock.SetMode("dock") end
        wantGap = true
    else
        -- Only an actual undock changes the chrome: a mode a caller picked with no Console to dock
        -- onto (SetMode before the build, say) is theirs and stays.
        if pet.IsDocked() then
            if not pet.SeatFloat() then
                pendingDock = true
                return false
            end
            PetDock.SetMode("float")
        end
    end

    -- The Console's top line: nil, nil closes it. Asked of whatever Console exists (the one that was
    -- drawn a moment ago may have just hidden), only when the wish changed or a forced re-dock.
    local api = FS.Console
    if gapOwner == nil and type(api) == "table" and type(api.SetDockGap) == "function"
        and (wantGap ~= gapOpen or (force and wantGap)) then
        local ok
        if wantGap then
            ok = api.SetDockGap(GapSpan())
        else
            ok = api.SetDockGap(nil, nil)
        end
        if ok then
            gapOpen = wantGap
        else
            pendingDock = true
        end
    end
    if wantGap then ApplyPatch() end
    return true
end

-- Refresh runs from event handlers nothing else guards (the regen replay, SetPetShown, PetFrame's
-- ApplyRescale), and SeatDocked clears the container's points before it anchors, so a throw partway
-- would leave the panel unseated. A throw falls back to the float seat: the container re-seated by
-- SeatFloat, float chrome, the Console's top line closed. The error is run through xpcall so the
-- chained error handler (ErrorLog.lua: /fserr, /fsbug) still gets it with its stack, EVERY time; the
-- chat line is once per distinct message (FS.LogDegradeOnce does not dedupe), capped, so a second
-- different failure is not hidden behind the first. A float seat that did not land keeps pendingDock
-- set, so the next trigger (regen) tries again instead of leaving the panel unseated for good, and
-- the line says so.
local REFRESH_LOG_MAX = 3
local refreshLogged, refreshLoggedCount = {}, 0

local function ForwardError(err)
    local ok, handler = pcall(geterrorhandler)
    if ok and type(handler) == "function" then pcall(handler, err) end
    return err
end

local function LogRefreshFailure(err, floatErr)
    local key = tostring(err)
    if refreshLogged[key] or refreshLoggedCount >= REFRESH_LOG_MAX then return end
    refreshLogged[key] = true
    refreshLoggedCount = refreshLoggedCount + 1
    local tail
    if floatErr == nil then
        tail = "); the floating pet panel is used instead."
    else
        tail = "); the float seat failed too (" .. tostring(floatErr) .. "), retrying at the next trigger."
    end
    FS.LogDegradeOnce("petdock_dock_refresh",
        "|cffff4488Forever STUwave|r: docking the pet panel failed (" .. key .. tail)
end

function PetDock.Refresh(force)
    local ok, ran = xpcall(function() return RefreshBody(force) end, ForwardError)
    if ok then return ran end

    local pet = FS.PetFrame
    local landed, floatErr = false, "no float seat"
    if type(pet) == "table" and pet.SeatFloat then
        local called, result = xpcall(pet.SeatFloat, ForwardError)
        if called and result == true then
            landed, floatErr = true, nil
        elseif not called then
            floatErr = result
        else
            floatErr = "refused"
        end
    end
    pendingDock = not landed
    if landed then pcall(PetDock.SetMode, "float") end
    local api = FS.Console
    if gapOwner ~= nil then
        -- the gap is another owner's: leave it as it is
    elseif type(api) == "table" and type(api.SetDockGap) == "function" then
        local closed, done = pcall(api.SetDockGap, nil, nil)
        gapOpen = not (closed and done)
    else
        gapOpen = false
    end
    LogRefreshFailure(ran, floatErr)
    return false
end

-- SINGLE OWNER of the Console's gap. PetFrame builds for every class and this file docks the (hidden) panel
-- of a pet-less class too, so by default this file holds the gap [25, 381] and drives the patch. A class
-- module that draws its own shoulder on the Console (the Paladin's) calls YieldGap(owner) first (owner: a
-- non-empty string or a table), then sets ITS gap with Console.SetDockGap; while it holds the gap this file
-- calls neither SetDockGap nor SetGapPatchAlpha, on any path (Refresh, a rescale, SetPetShown in combat, the
-- throwing-refresh fallback), though the panel itself still docks and floats as before. YieldGap leaves the
-- patch OPEN (alpha 0), so the owner's gap shows as open. False for a bad owner or when another owner holds it.
-- ReclaimGap(owner) (only the holder) hands it back: the next Refresh closes or re-opens the pet gap as the
-- Console and the pet ask (in combat it waits for regen: the owner's span stays, and no patch alpha is
-- written over it, until then). The owner should close its own gap (SetDockGap(nil, nil)) first when it does
-- not want it left standing. CALL YieldGap OUT OF COMBAT: the owner's SetDockGap is refused in combat, so a
-- yield made in combat leaves this file's old pet gap [25, 381] standing with the patch open (alpha 0, which
-- is legal in combat) until the owner sets its own at regen.
function PetDock.YieldGap(owner)
    local kind = type(owner)
    if not ((kind == "string" and owner ~= "") or kind == "table") then return false end
    if gapOwner ~= nil and gapOwner ~= owner then return false end
    gapOwner = owner
    local api = FS.Console
    if type(api) == "table" and type(api.SetGapPatchAlpha) == "function" then pcall(api.SetGapPatchAlpha, 0) end
    return true
end

function PetDock.ReclaimGap(owner)
    if gapOwner == nil or owner ~= gapOwner then return false end
    gapOwner = nil
    gapReclaimed = true   -- the next Refresh that runs (now, or at regen in combat) re-asks the Console or closes the old span
    PetDock.Refresh(true)
    return true
end

-- PetFrame.Apply calls this with the visibility gate's answer, in combat too. The patch alpha is
-- written at once (legal in combat), so a pet dying in combat closes the hole in the Console's top line
-- immediately and a re-summon reopens it; a class with no pet keeps the panel docked and hidden and the
-- line unbroken. Out of combat it also runs Refresh; in combat nothing protected is touched (the
-- regen watcher and PetFrame's own regen Apply reconcile).
function PetDock.SetPetShown(show)
    petShown = show and true or false
    if InCombatLockdown() then
        if gapOpen then ApplyPatch() end
        return
    end
    PetDock.Refresh()
end

-------------------------------------------------------------------------------
-- Retint hook for the NORMAL edge (the red twins are never retinted)
-------------------------------------------------------------------------------

local function TintNormal(color, strokeAlpha, haloAlpha, floatColor, floatAlpha)
    if dockShoulder then dockShoulder:SetEdge(color, strokeAlpha, haloAlpha) end
    if parts.float.outline then
        Tint(parts.float.outline, floatColor, floatAlpha)
    end
end

-- r, g, b of the normal edge; the optional alphas default to the mockup's stroke and halo (the float
-- outline's alpha stays 1 unless a stroke alpha is given). False (and nothing tinted) for a non-number colour
-- or a non-number alpha.
function PetDock.SetEdgeColor(r, g, b, strokeAlpha, haloAlpha)
    if type(r) ~= "number" or type(g) ~= "number" or type(b) ~= "number" then return false end
    if (strokeAlpha ~= nil and type(strokeAlpha) ~= "number") or (haloAlpha ~= nil and type(haloAlpha) ~= "number") then
        return false   -- before anything is tinted: the dock and the float outline never disagree
    end
    if not built then return false end
    local color = { r, g, b }
    TintNormal(color, strokeAlpha or C.STROKE_ALPHA, haloAlpha or C.HALO_ALPHA, color, strokeAlpha or 1)
    return true
end

-- Back to the violet dock edge and the cyan float outline.
function PetDock.ResetEdgeColor()
    if not built then return false end
    local power = Theme.COLOR_POWER
    TintNormal(Theme.COLOR_BORDER, C.STROKE_ALPHA, C.HALO_ALPHA, power, power[4] or 1)
    return true
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

-- PetFrame.Build calls this where it used to build the chrome, right after the container exists.
function PetDock.Build(frame)
    if built then return end
    container = frame
    local layout = FS.Layout and FS.Layout.petcontainer
    if type(layout) == "table" and type(layout.w) == "number" and type(layout.h) == "number" then
        C.W, C.H = layout.w, layout.h
    end
    BuildFloat()
    TryBuildDock()
    if not frames.dock then mode = "float" end   -- a "dock" remembered before the build cannot be honoured
    built = true
    Apply()
    if not frames.dock then return end           -- nothing to rescale

    -- The dock art is scaled by the layout scale. A rescale in combat waits for regen, like the
    -- container's own (the chrome frames are non-secure, but the container they hang from is not,
    -- and the two must agree).
    local function Rescale()
        pendingScale = false
        dockShoulder:Rescale()
    end
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            if InCombatLockdown() then
                pendingScale = true
                return
            end
            Rescale()
        end)
    end
    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("PLAYER_REGEN_ENABLED")
    watcher:SetScript("OnEvent", function()
        if pendingScale and not InCombatLockdown() then Rescale() end
        if pendingDock and not InCombatLockdown() then PetDock.Refresh(true) end
    end)

    -- Dock now if the Console is already drawn; every later Console seat, toggle and /fsbars switch
    -- comes through OnGeometry (replayed at once when a seat already happened, so load order is
    -- free). Only after the dock chrome built: without it the panel stays floating.
    if FS.ActionBars and type(FS.ActionBars.OnGeometry) == "function" then
        FS.ActionBars.OnGeometry(function() PetDock.Refresh() end)
    end
    PetDock.Refresh()
end

-- PetFrame calls this right after BuildLowHealth(): from then on SetMode keeps the low-HP layer
-- pointed at the active mode's edge.
function PetDock.AttachLowHealth()
    lowReady = true
    AttachLow()
end
