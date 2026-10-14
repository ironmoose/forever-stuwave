-- Forever STUwave: the Shaman totem tab's hover PIECE and the tab's hover BUMP
--
-- Design reference: mockups/totem-picker-arrow-v3-2026-10-13.html, concept V1 "As drawn". Textures: tools/assets/
-- generate_totem_piece.py (every number marked "generator" below is that file's, and totembar-harness.py reads the
-- generator back and compares).
--
-- THE PIECE. While the cursor is over an element button (or the picker for it is open) a square cap piece stands
-- above the button: left and right edges flush with the button's, the bar 11 px thick, an even 2 px seam above the
-- button top, and one slanted edge, the lower left one, parallel to the button's 45 degree top left chamfer with the
-- same seam (the cut continues as a seam), ending in a small tip over the empty cut corner. It is styled like the
-- button's hover look: the hover fill, the element colour stroke, faint magenta scanlines. In it stands a bold
-- chevron pointing up (down while the picker is open), gradient from the element colour to hot magenta, with a haze
-- and a thin near white core. Dim while the cursor is on the button, full when it is on the piece itself.
--
-- WoW cannot draw the slanted edge or a gradient at run time, so the layers are baked white and tinted here:
-- the magenta share of the gradient is a second chevron texture whose alpha ramps from 0 at the arm feet to 1 at the
-- apex, layered over the element tinted one. The piece's textures are regions of the plain arrow Button
-- (TotemBar.lua), so Show, Hide, tint and texcoord are all legal in combat.
--
-- THE BUMP. While the piece is up the tab outline grows a bump around it: the Console's own stroke, fill and halo,
-- vertical walls, square top corners, 4 px shoulders (6 px on the leftmost button, where the bump's left wall meets
-- the tab's own left wall). The bump is plain textures on the shoulder art (PetDock's NewShoulder object, reached
-- through ClassShoulder.Shoulder): the stroke and halo are baked (the halo is the Console's profile), the fill is
-- flat rectangles and one cut wedge. The tab's top rail is opened under the bump through Shoulder:OpenTop, and closed
-- again when the bump goes. One bump stands at a time. Nothing here is secure and nothing waits for combat.
--
-- Loads after ClassShoulder.lua, before TotemBar.lua. Nothing here is verified in game.

local _, FS = ...

local TotemPiece = {}
FS.TotemPiece = TotemPiece

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

-- Design px relative to the element button's top left corner, y down, unless a name says art (the shoulder art's
-- own design px: x from the tab's left edge, y down from its top line).
local C = {
    BTN = 38,
    SEAM = 2,                   -- generator: the even gap between the bar and the button top
    BAR = 11,                   -- generator: the bar's thickness
    HIT_W = 38, HIT_H = 13,     -- the click area: the seam and the bar, 0 px into the button face
    -- generator: the layer canvases are 64 x 32 design px, 4 texels per px
    CANVAS_W = 64, CANVAS_H = 32,
    PIECE_ORIGIN = { -13, -21 },    -- the piece layers' canvas top left
    CHEV_ORIGIN = { -13, -23.3 },   -- the chevron layers' canvas top left (centred on the chevron, so a flip is exact)
    -- the bump (generator): walls 4 px out of the button column, 6 px on the leftmost; the right wall returns to
    -- the rail through a 45 degree foot; the bump top is RISE above the rail
    SHOULDER = 4, SHOULDER_FIRST = 6, FOOT = 6, RISE = 11,
    HALO_PAD = 11,
    -- the rail resumes this far past the right wall: the foot's end less the last stroke pixel the line runs under
    RAIL_RESUME = 5,
    WEDGE_CUT = 6,
    -- generator: the stroke atlas (256 square, 4 texels per px) and halo atlas (128 x 64, 1 texel per px); per
    -- variant { region x0, y0, x1, y1 in design px relative to the button, atlas x, y of the region's top left }
    STROKE = {
        size = 256, k = 4,
        normal = { -5, -18, 49, -4, 2, 2 },
        fire = { -7, -18, 49, 1, 2, 64 },
    },
    HALO = {
        w = 128, h = 64,
        normal = { -15, -28, 53, -6, 2, 2 },
        fire = { -17, -28, 53, 0, 2, 32 },
    },
}
TotemPiece.C = C

-- the layers of the piece, bottom to top: texture file, which canvas it sits on, draw layer and sublevel
local LAYERS = {
    { key = "fill", file = "totem_piece_fill", canvas = "piece", layer = "ARTWORK", sub = 0 },
    { key = "scan", file = "totem_piece_scan", canvas = "piece", layer = "ARTWORK", sub = 1 },
    { key = "glow", file = "totem_piece_glow", canvas = "piece", layer = "ARTWORK", sub = 2 },
    { key = "edge", file = "totem_piece_edge", canvas = "piece", layer = "ARTWORK", sub = 3 },
    { key = "hazeA", file = "totem_chev_haze", canvas = "chev", layer = "OVERLAY", sub = 0, chev = true },
    { key = "hazeB", file = "totem_chev_haze_pink", canvas = "chev", layer = "OVERLAY", sub = 1, chev = true },
    { key = "bodyA", file = "totem_chev_body", canvas = "chev", layer = "OVERLAY", sub = 2, chev = true },
    { key = "bodyB", file = "totem_chev_pink", canvas = "chev", layer = "OVERLAY", sub = 3, chev = true },
    { key = "core", file = "totem_chev_core", canvas = "chev", layer = "OVERLAY", sub = 4, chev = true },
}

-- mockup pieceSvg / neonArrow: the fill is the bg mixed toward the element colour; alphas per level
local LOOK = {
    dim = { fill = 0.1, scan = 0.11, edge = 0.6, haze = 0.32, body = 0.62, core = 0.45 },
    lit = { fill = 0.2, scan = 0.2, edge = 1, haze = 0.95, body = 1, core = 1 },
}
local CORE_COLOR = { 1, 0.957, 0.984 }      -- #fff4fb

local function Pink()
    local theme = FS.Theme
    return (theme and theme.COLOR_HEALTH) or { 1, 0.18, 0.592, 1 }     -- #ff2e97
end

local function Ground()
    local theme = FS.Theme
    return (theme and theme.COLOR_HUD_SCRIM) or { 0.051, 0.024, 0.125, 1 }     -- #0d0620
end

local function Mix(a, b, t)
    return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
end

-------------------------------------------------------------------------------
-- The piece (regions of the plain arrow Button)
-------------------------------------------------------------------------------

-- Builds the layers on `arrow` once; `color` is the element's { r, g, b }.
function TotemPiece.Attach(arrow, color)
    if arrow.fsPiece then return arrow.fsPiece end
    local piece = { color = color }
    for _, spec in ipairs(LAYERS) do
        local tex = arrow:CreateTexture(nil, spec.layer, nil, spec.sub)
        tex:SetTexture(MEDIA .. spec.file .. ".tga")
        piece[spec.key] = tex
    end
    arrow.fsPiece = piece
    TotemPiece.SetLook(arrow, false, false)
    return piece
end

-- Seats every layer: the canvases are anchored to the arrow's top left, which is the hit area's (the piece's
-- own top left corner is at the arrow's, 13 px above the button top).
function TotemPiece.Seat(arrow, scale)
    local piece = arrow.fsPiece
    if not piece then return end
    for _, spec in ipairs(LAYERS) do
        local origin = spec.canvas == "chev" and C.CHEV_ORIGIN or C.PIECE_ORIGIN
        local tex = piece[spec.key]
        tex:ClearAllPoints()
        tex:SetPoint("TOPLEFT", arrow, "TOPLEFT", origin[1] * scale, -(origin[2] + C.HIT_H) * scale)
        tex:SetSize(C.CANVAS_W * scale, C.CANVAS_H * scale)
    end
end

-- The look: `lit` is the cursor on the piece itself (or the picker open), else the dim hover; `flipped` points the
-- chevron down (the picker is open: this closes it).
function TotemPiece.SetLook(arrow, lit, flipped)
    local piece = arrow.fsPiece
    if not piece then return end
    lit, flipped = lit and true or false, flipped and true or false
    piece.lit, piece.flipped = lit, flipped
    local look = lit and LOOK.lit or LOOK.dim
    local c, pink, ground = piece.color, Pink(), Ground()
    local fr, fg, fb = Mix(ground, c, look.fill)
    piece.fill:SetVertexColor(fr, fg, fb, 1)
    piece.scan:SetVertexColor(pink[1], pink[2], pink[3], look.scan)
    piece.edge:SetVertexColor(c[1], c[2], c[3], look.edge)
    piece.glow:SetVertexColor(c[1], c[2], c[3], 1)
    if lit then piece.glow:Show() else piece.glow:Hide() end
    piece.hazeA:SetVertexColor(c[1], c[2], c[3], look.haze)
    piece.hazeB:SetVertexColor(pink[1], pink[2], pink[3], look.haze)
    piece.bodyA:SetVertexColor(c[1], c[2], c[3], look.body)
    piece.bodyB:SetVertexColor(pink[1], pink[2], pink[3], look.body)
    piece.core:SetVertexColor(CORE_COLOR[1], CORE_COLOR[2], CORE_COLOR[3], look.core)
    for _, spec in ipairs(LAYERS) do
        if spec.chev then
            if flipped then piece[spec.key]:SetTexCoord(0, 1, 1, 0) else piece[spec.key]:SetTexCoord(0, 1, 0, 1) end
        end
    end
end

-------------------------------------------------------------------------------
-- The bump (textures on the shoulder art)
-------------------------------------------------------------------------------

local bump = {}         -- shoulder, parts, col: the one bump that stands

local function ShoulderKey()
    return "shaman"
end

local function Standing()
    local cs = FS.ClassShoulder
    return cs and cs.Shoulder and cs.Shoulder(ShoulderKey()) or nil
end

-- Where the bump stands for button `col`: art design px (x from the tab's left edge), the button's left, the wall
-- x on each side, the top, and whether it is the leftmost button.
function TotemPiece.BumpRect(col)
    local cs = FS.ClassShoulder
    local k = cs and cs.C
    if not (k and type(col) == "number") then return nil end
    local left = k.PAD + (col - 1) * (k.BTN + k.GAP)
    local first = col == 1
    local wall = first and C.SHOULDER_FIRST or C.SHOULDER
    return {
        button = left, left = left - wall, right = left + C.BTN + C.SHOULDER, first = first,
        top = -C.RISE, rail = 0, buttonTop = k.PT,
    }
end

local function Put(art, tex, x, y, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", art, "TOPLEFT", x, -y)
    tex:SetSize(w, h)
end

local function MakeParts(shoulder)
    local art, normal = shoulder.art, shoulder.normal
    local parts = { shoulder = shoulder }
    local fill = shoulder.fillTint or { 0.176, 0.106, 0.306, 0.8 }
    local function flat(name)
        local tex = art:CreateTexture(nil, "BACKGROUND")
        tex:SetTexture(FS.Theme.FLAT_TEXTURE)
        tex:SetVertexColor(fill[1], fill[2], fill[3], fill[4])
        tex:Hide()
        parts[name] = tex
    end
    flat("upper")
    flat("lower")
    flat("corner")
    local wedge = art:CreateTexture(nil, "BACKGROUND")
    wedge:SetTexture(FS.Theme.FILL_CUT_TEXTURES[C.WEDGE_CUT])
    wedge:SetVertexColor(fill[1], fill[2], fill[3], fill[4])
    wedge:Hide()
    parts.wedge = wedge
    local halo = normal:CreateTexture(nil, "BACKGROUND")
    halo:SetTexture(MEDIA .. "totem_bump_halo.tga")
    halo:Hide()
    parts.halo = halo
    local stroke = normal:CreateTexture(nil, "BORDER")
    stroke:SetTexture(MEDIA .. "totem_bump_stroke.tga")
    stroke:Hide()
    parts.stroke = stroke
    return parts
end

local function Tint(parts, shoulder)
    local color = shoulder.color or (FS.Theme and FS.Theme.COLOR_BORDER) or { 0.659, 0.333, 0.969, 1 }
    parts.stroke:SetVertexColor(color[1], color[2], color[3], shoulder.strokeAlpha or 1)
    parts.halo:SetVertexColor(color[1], color[2], color[3], shoulder.haloAlpha or 1)
end

local function LowerBump()
    local parts = bump.parts
    if bump.col and parts then
        for _, key in ipairs({ "upper", "lower", "corner", "wedge", "halo", "stroke" }) do parts[key]:Hide() end
        if bump.shoulder and bump.shoulder.CloseTop then bump.shoulder:CloseTop() end
    end
    bump.col = nil
end

local function RaiseBump(col)
    local shoulder = Standing()
    local rect = TotemPiece.BumpRect(col)
    if not (shoulder and shoulder.art and shoulder.normal and shoulder.OpenTop and rect) then return end
    if bump.col == col and bump.shoulder == shoulder then return end
    LowerBump()
    if not bump.parts or bump.parts.shoulder ~= shoulder then bump.parts = MakeParts(shoulder) end
    local parts, art = bump.parts, shoulder.art
    bump.shoulder = shoulder
    local variant = rect.first and "fire" or "normal"
    local bx = rect.button
    local by = rect.buttonTop       -- the button's top, art y

    -- the fill: the bump's body down to the foot's vertex, the lower part (a half px short of the right wall, where
    -- the foot's wedge takes over, like the tab's own flare), the wedge, and on the leftmost button the corner the
    -- tab's cut corner left open
    local vertex = -C.FOOT
    Put(art, parts.upper, rect.left, rect.top, rect.right - rect.left, vertex - rect.top)
    Put(art, parts.lower, rect.left, vertex, rect.right - 0.5 - rect.left, rect.rail - vertex)
    local u = C.WEDGE_CUT / 16
    Put(art, parts.wedge, rect.right - 0.5, vertex, C.WEDGE_CUT, C.WEDGE_CUT)
    parts.wedge:SetTexCoord(u, 0, 0, u)     -- the top left cut's fill, mirrored: its solid side is the lower left
    if rect.first then
        Put(art, parts.corner, rect.left, rect.rail, C.WEDGE_CUT, C.WEDGE_CUT)
        parts.corner:Show()
    else
        parts.corner:Hide()
    end

    -- the baked stroke and halo: the region of the variant, cut from its atlas
    local function place(tex, spec, k, w, h)
        local x0, y0, x1, y1, ax, ay = spec[1], spec[2], spec[3], spec[4], spec[5], spec[6]
        Put(art, tex, bx + x0, by + y0, x1 - x0, y1 - y0)
        tex:SetTexCoord(ax / w, (ax + (x1 - x0) * k) / w, ay / h, (ay + (y1 - y0) * k) / h)
    end
    place(parts.stroke, C.STROKE[variant], C.STROKE.k, C.STROKE.size, C.STROKE.size)
    place(parts.halo, C.HALO[variant], 1, C.HALO.w, C.HALO.h)
    Tint(parts, shoulder)
    for _, key in ipairs({ "upper", "lower", "wedge", "halo", "stroke" }) do parts[key]:Show() end

    -- the rail opens from the left wall to where the foot ends (the line runs under its last pixel), its halo from
    -- a halo pad before the left wall to a pad after the right
    shoulder:OpenTop(rect.left, rect.right + C.RAIL_RESUME, rect.left - C.HALO_PAD, rect.right + C.HALO_PAD,
        rect.first)
    bump.col = col
end

-- Raises the bump around button `col` (1..6), or lowers it when `col` is the one standing. One bump at a time:
-- raising another moves it. A tab that is not standing has no bump to draw.
function TotemPiece.SetBump(col, on)
    if on then
        RaiseBump(col)
    elseif bump.col == col then
        LowerBump()
    end
end

-- The button whose bump stands, or nil.
function TotemPiece.BumpCol()
    return bump.col
end
