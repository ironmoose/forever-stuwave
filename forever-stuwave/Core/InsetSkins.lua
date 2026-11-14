-- Forever STUwave: InsetSkins
-- The inner inset and the section header plate of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 7).
--
-- An inset is the well a window keeps its content in (InsetFrameTemplate: the marble Bg and the bevelled NineSlice child). Skinned
-- it is an ink face with a 1 px #2a1846 edge and a chamfer at the bottom right only (8 asked, the baked 6 drawn: the set is 2, 3, 4
-- and 6), a violet scanline every 4 px from row 3 at 5 %, and cyan register marks at the top left, top right and bottom left, 4 in
-- with 4 long arms at 35 %. The top left stays square so a plate docked on top of it keeps its own cut as the module's one corner.
--
-- A plate is the lid of the cartridge: 24 tall, a chamfer at the top left only, a 1 px violet edge on the #1a0d2c band, a 3 x 12 pink
-- LED that breathes, the caption in cyan mono 11, chips right-aligned (20 tall, cut 4, 4 apart, 6 in) and a violet glint that
-- crosses it every 3.6 s. The plate is an opt-in helper: it needs a strip of room above an inset that a stock window does not
-- keep, so nothing mounts one yet (InsetSkins.Plate(parent, opts) returns it; the window that has the room anchors plate.frame).
--
-- Skin only. A stock inset keeps its rect, its scripts and its children: its Bg and NineSlice are held at alpha 0 (FS.HeldArt, and
-- Kit.HoldFrame for the frame), what we draw is regions of the inset itself on the BACKGROUND and BORDER layers (so every stock
-- child, text and icon draws over it), and we follow it by post-hooks (OnSizeChanged, OnShow). A frame met in combat is skinned
-- when combat ends.
--
-- Told by shape, never by name: a Frame keyed layoutType = "InsetFrameTemplate" that has the Bg and the NineSlice, at least INSET_MIN
-- pixels each way. A window frame has a Bg and a NineSlice too, but its layoutType is its own. An inset whose art something else
-- already holds or hides (Theme.StripBlizzardChrome hides the named ones, GroupKit.HoldInset zeroes them) is that skin's and is left
-- alone. The sweep walks on into an inset: its buttons and boxes are skinned in the same pass.
--
-- Left out: InsetFrameTemplate2, 3 and 4 (loose border textures with no shared Bg and NineSlice to tell them by), the level 2 caption
-- with a rule (a window's own FontStrings), the letter spacing of the plate caption (the client's fonts cannot space letters), and
-- the chamfer of 8 (the baked set stops at 6). The plate's glint reuses the item slot's baked band, a little shallower than the
-- mockup's 8 wide slant.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_CTRL_BAND) then return end

local InsetSkins = {}
FS.InsetSkins = InsetSkins

local K = FS.Layout.Controls
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local SCANLINE, GLINT = MEDIA .. "ctl_scanline.tga", MEDIA .. "ctl_glint.tga"
local CANVAS = 16      -- the baked cut pieces' canvas, in texels
local SCAN_TILE = 4    -- the scanline tile, in texels

local C = {
    ink = Theme.COLOR_CTRL_INK, edge = Theme.COLOR_CTRL_DISEDGE, band = Theme.COLOR_CTRL_BAND, violet = Theme.COLOR_BORDER,
    cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH,
}

local parts = setmetatable({}, { __mode = "k" }) -- inset -> what we drew on it
local plates = setmetatable({}, { __mode = "k" }) -- plate frame -> its record

local function IsTable(v) return type(v) == "table" end

-- The chamfer actually drawn for a requested one: the baked size at or under it, 0 (square) when the corners are round.
local function Chamfer(requested)
    if Theme.CHROME_CORNERS ~= "cut" then return 0 end
    return Theme.SnapCut(requested)
end

-------------------------------------------------------------------------------
-- A cut rectangle: a face and a 1 px edge, a chamfer at the top left and / or the bottom right
-------------------------------------------------------------------------------

local PIECES = { tl = true, br = true }

local function Run(host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub)
    t:SetColorTexture(1, 1, 1, 1)
    Kit.Snap(t)
    return t
end

-- A baked cut piece: the top left corner of its canvas, turned to the bottom right by flipping both axes.
local function Piece(host, layer, sub, path, corner, c)
    local t = host:CreateTexture(nil, layer, nil, sub)
    t:SetTexture(path)
    local k = c / CANVAS
    if corner == "tl" then t:SetTexCoord(0, k, 0, k) else t:SetTexCoord(k, 0, k, 0) end
    Kit.Snap(t)
    return t
end

-- The face is up to three runs (the top run beside a top left cut, the middle, the bottom run beside a bottom right cut) and a baked
-- corner piece at each cut; they tile without overlap, so a translucent face keeps one alpha. The edge is four runs that never
-- overlap and a baked diagonal at each cut.
local function BuildShape(host, tl, br, fillLayer, fillSub, edgeLayer, edgeSub)
    local s = { tl = tl, br = br, fill = {}, edge = {} }
    s.fill.mid = Run(host, fillLayer, fillSub)
    if tl > 0 then
        s.fill.top = Run(host, fillLayer, fillSub)
        s.fill.tl = Piece(host, fillLayer, fillSub, Theme.FILL_CUT_TEXTURES[tl], "tl", tl)
    end
    if br > 0 then
        s.fill.low = Run(host, fillLayer, fillSub)
        s.fill.br = Piece(host, fillLayer, fillSub, Theme.FILL_CUT_TEXTURES[br], "br", br)
    end
    for _, key in ipairs({ "top", "right", "bottom", "left" }) do s.edge[key] = Run(host, edgeLayer, edgeSub) end
    if tl > 0 then s.edge.tl = Piece(host, edgeLayer, edgeSub, Theme.BORDER_CUT_TEXTURES[tl][1], "tl", tl) end
    if br > 0 then s.edge.br = Piece(host, edgeLayer, edgeSub, Theme.BORDER_CUT_TEXTURES[br][1], "br", br) end
    return s
end

-- Lays the shape out over w x h physical pixels of `host`.
local function SeatShape(s, host, w, h)
    local tl, br, f, e = s.tl, s.br, s.fill, s.edge
    if tl > 0 then
        Kit.Place(f.top, host, tl, 0, w - tl, tl)
        Kit.Place(f.tl, host, 0, 0, tl, tl)
    end
    Kit.Place(f.mid, host, 0, tl, w, h - tl - br)
    if br > 0 then
        Kit.Place(f.low, host, 0, h - br, w - br, br)
        Kit.Place(f.br, host, w - br, h - br, br, br)
    end
    -- the top right pixel is the right edge's, the top left one the top edge's (or the cut's), the bottom left one the bottom edge's
    Kit.Place(e.top, host, tl, 0, w - 1 - tl, 1)
    Kit.Place(e.right, host, w - 1, 0, 1, h - br)
    Kit.Place(e.bottom, host, 0, h - 1, w - br - (br == 0 and 1 or 0), 1)
    local top = math.max(tl, 1)
    Kit.Place(e.left, host, 0, top, 1, h - 1 - top)
    if tl > 0 then Kit.Place(e.tl, host, 0, 0, tl, tl) end
    if br > 0 then Kit.Place(e.br, host, w - br, h - br, br, br) end
end

local function Tint(t, piece, color, alpha)
    local a = alpha or color[4] or 1
    if piece then t:SetVertexColor(color[1], color[2], color[3], a) else t:SetColorTexture(color[1], color[2], color[3], a) end
end

local function PaintShape(s, fill, fillAlpha, edge, edgeAlpha)
    for key, t in pairs(s.fill) do Tint(t, PIECES[key], fill, fillAlpha) end
    for key, t in pairs(s.edge) do Tint(t, PIECES[key], edge, edgeAlpha) end
end

-------------------------------------------------------------------------------
-- Inset
-------------------------------------------------------------------------------

-- True for a stock inset that nothing else owns.
function InsetSkins.IsInset(frame)
    if Kit.TypeOf(frame) ~= "Frame" or frame.layoutType ~= "InsetFrameTemplate" then return false end
    local bg, bevel = frame.Bg, frame.NineSlice
    if not (IsTable(bg) and IsTable(bevel)) then return false end
    local w, h = Kit.SizePx(frame)
    if w and (w < K.INSET_MIN or h < K.INSET_MIN) then return false end
    if parts[frame] then return true end
    for _, art in ipairs({ bg, bevel }) do
        if Kit.Plain(Kit.Try(art.GetAlpha, art)) == 0 or Kit.Plain(Kit.Try(art.IsShown, art)) == false then return false end
    end
    return true
end

function InsetSkins.Parts(frame) return parts[frame] end

-- Tiles the scanline texture over (x, y, w, h) pixels of the inset, one texel a pixel, from the inset's own top left, so the lines
-- of two runs line up and the first falls on row 3.
local function SeatScan(t, frame, x, y, w, h)
    Kit.Place(t, frame, x, y, w, h)
    t:SetTexCoord(x / SCAN_TILE, (x + w) / SCAN_TILE, y / SCAN_TILE, (y + h) / SCAN_TILE)
end

local function Layout(frame)
    local p = parts[frame]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(frame)
    if not w then return end
    p.w, p.h = w, h
    SeatShape(p.shape, frame, w, h)
    local c = p.c
    if c > 0 then
        SeatScan(p.scan.main, frame, 1, 1, w - 2, h - c - 1)
        SeatScan(p.scan.low, frame, 1, h - c, w - c - 1, c - 1)
        p.scan.low:Show()
    else
        SeatScan(p.scan.main, frame, 1, 1, w - 2, h - 2)
        p.scan.low:Hide()
    end
    local m, arm = K.INSET_MARK_IN, K.INSET_MARK_ARM
    local right, bottom = w - 1 - m, h - 1 - m
    Kit.Move(p.marks.tl.h, m, m, arm, 1);                 Kit.Move(p.marks.tl.v, m, m + 1, 1, arm - 1)
    Kit.Move(p.marks.tr.h, right - (arm - 1), m, arm, 1); Kit.Move(p.marks.tr.v, right, m + 1, 1, arm - 1)
    Kit.Move(p.marks.bl.h, m, bottom, arm, 1);            Kit.Move(p.marks.bl.v, m, bottom - (arm - 1), 1, arm - 1)
end

Kit.OnReseat(function()
    for frame in pairs(parts) do Layout(frame) end
end)

local function Build(frame)
    local c = Chamfer(K.INSET_CUT)
    local p = { c = c, w = 0, h = 0 }
    parts[frame] = p -- marked first, so a failure part way is not retried into a second set of layers

    Kit.HoldFrame(frame.NineSlice)
    HeldArt.Hold(frame.Bg)

    p.shape = BuildShape(frame, 0, c, "BACKGROUND", -6, "BORDER", 0)
    p.fill, p.edge = p.shape.fill, p.shape.edge
    PaintShape(p.shape, C.ink, 1, C.edge, 1)

    p.scan = {}
    for _, key in ipairs({ "main", "low" }) do
        local t = frame:CreateTexture(nil, "BACKGROUND", nil, -4)
        t:SetTexture(SCANLINE, "REPEAT", "REPEAT")
        t:SetVertexColor(C.violet[1], C.violet[2], C.violet[3], K.INSET_SCAN_ALPHA)
        Kit.Snap(t)
        Kit.Place(t, frame, 0, 0, 1, 1)
        p.scan[key] = t
    end

    p.marks = {}
    for _, corner in ipairs({ "tl", "tr", "bl" }) do
        p.marks[corner] = {
            h = Kit.Rect(frame, 0, 0, 1, 1, C.cyan, K.INSET_MARK_ALPHA, "BORDER", 1),
            v = Kit.Rect(frame, 0, 0, 1, 1, C.cyan, K.INSET_MARK_ALPHA, "BORDER", 1),
        }
    end
    p.built = true

    Kit.HookScript(frame, "OnSizeChanged", function() Layout(frame) end)
    Kit.HookScript(frame, "OnShow", function() Layout(frame) end)
    Layout(frame)
    Kit.Later(function() Layout(frame) end)
end

-- Skins one stock inset. Idempotent; returns true when it skinned now. An inset met in combat is skinned when combat ends.
function InsetSkins.Skin(frame)
    if type(frame) ~= "table" or parts[frame] or not InsetSkins.IsInset(frame) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() InsetSkins.Skin(frame) end)
        return false
    end
    local ok, err = pcall(Build, frame)
    if not ok then Kit.Fail("inset", err) end
    return ok and parts[frame] ~= nil
end

Kit.Register("inset", {
    match = function(frame) return parts[frame] ~= nil or InsetSkins.IsInset(frame) end,
    skin = InsetSkins.Skin, parts = InsetSkins.Parts,
    into = false, -- an inset holds the window's own buttons and boxes: the sweep walks on into it
})

-------------------------------------------------------------------------------
-- Section header plate
-------------------------------------------------------------------------------

-- Where the glint's band is, in pixels right of the plate's left edge, `elapsed` seconds into its loop: a straight run from
-- PLATE_GLINT_FROM to PLATE_GLINT_PAST beyond `width`, every PLATE_GLINT_PERIOD seconds (the mockup's CSS `linear`).
function InsetSkins.PlateGlintOffset(elapsed, width)
    local p = (elapsed % K.PLATE_GLINT_PERIOD) / K.PLATE_GLINT_PERIOD
    return K.PLATE_GLINT_FROM + (width + K.PLATE_GLINT_PAST - K.PLATE_GLINT_FROM) * p
end

-- A chip is as wide as its text at the tag's character width plus the pad, rounded up to the tag's step.
local function ChipWidth(text)
    return math.ceil((#text * K.TAG_CHAR + K.CHIP_PAD) / K.TAG_ROUND - 1e-9) * K.TAG_ROUND
end

local function MakeChip(plate)
    local frame = CreateFrame("Frame", nil, plate.frame)
    Kit.Place(frame, plate.frame, 0, K.PLATE_CHIP_Y, K.CHIP_PAD * 2, K.CHIP_H)
    local chip = { frame = frame }
    chip.plate = Kit.Plate(frame, K.CHIP_CUT, K.CHIP_PAD * 2, K.CHIP_H)
    chip.label = Kit.Label(frame, "", K.CHIP_TEXT, C.cyan, "OVERLAY")
    Kit.Place(chip.label, frame, K.CHIP_PAD, K.CHIP_TEXT_Y, nil, nil, "CENTER", "TOPLEFT")
    return chip
end

-- The chips right to left from PLATE_CHIP_RIGHT in, PLATE_CHIP_GAP apart.
local function LayoutChips(plate)
    local w = plate.w
    if not w then return end
    local x = w - K.PLATE_CHIP_RIGHT
    local list = plate.chipList or {}
    for i = #list, 1, -1 do
        local chip = plate.chips[i]
        if not chip then
            chip = MakeChip(plate)
            plate.chips[i] = chip
        end
        local text, color = list[i][1], list[i][2] or C.cyan
        local cw = ChipWidth(text)
        x = x - cw
        Kit.Move(chip.frame, x, K.PLATE_CHIP_Y, cw, K.CHIP_H)
        Kit.Move(chip.label, cw / 2, K.CHIP_TEXT_Y)
        Kit.Place(chip.plate.fill, chip.frame, 0, 0, cw, K.CHIP_H)
        Kit.Place(chip.plate.ring, chip.frame, 0, 0, cw, K.CHIP_H)
        if chip.plate.ring2 then Kit.Place(chip.plate.ring2, chip.frame, 1, 1, cw - 2, K.CHIP_H - 2) end
        chip.label:SetText(text)
        Kit.Recolor(chip.label, color)
        Kit.PaintPlate(chip.plate, C.ink, 1, color, 1, 1)
        chip.frame:Show()
        x = x - K.PLATE_CHIP_GAP
    end
    for i = #list + 1, #plate.chips do plate.chips[i].frame:Hide() end
end

local function LayoutPlate(plate)
    local w, h = Kit.SizePx(plate.frame)
    if not w then return end
    plate.w, plate.h = w, h
    SeatShape(plate.shape, plate.frame, w, h)
    Kit.Move(plate.glint, 1, 1, w - 2, h - 2)
    LayoutChips(plate)
end

Kit.OnReseat(function()
    for _, plate in pairs(plates) do LayoutPlate(plate) end
end)

local function AnimateGlint(plate)
    local sheet = K.SLOT_GLINT_SHEET
    Kit.Animate(plate.frame, "glint", function(_, elapsed)
        local w = plate.w
        if not w then return end
        local t = InsetSkins.PlateGlintOffset(elapsed, w)
        plate.glintAt = t
        local iw, ih = w - 2, plate.h - 2
        if t + K.SLOT_GLINT_BAND <= 0 or t >= iw then
            plate.glint:Hide()
            return
        end
        plate.glint:SetTexCoord(-t / sheet, (iw - t) / sheet, 0, ih / sheet)
        plate.glint:Show()
    end)
end

-- Builds a section header plate as a frame of its own under `parent` and returns its record { frame, label, led, glint, chips }.
-- opts: text (the caption), chips ({ { text, color }, ... } right to left as read), width (physical pixels, sets the frame's width)
-- and x, y (physical pixels from the parent's top left, seats the plate there). With no x and y the caller anchors plate.frame.
function InsetSkins.Plate(parent, opts)
    opts = opts or {}
    local frame = CreateFrame("Frame", nil, parent)
    local plate = { frame = frame, chips = {}, chipList = opts.chips }
    plates[frame] = plate
    local c = Chamfer(K.PLATE_CUT)
    plate.shape = BuildShape(frame, c, 0, "BACKGROUND", -6, "BORDER", 0)
    plate.fill, plate.edge = plate.shape.fill, plate.shape.edge
    PaintShape(plate.shape, C.band, 1, C.violet, 1)

    plate.glint = Kit.Glyph(frame, GLINT, 1, 1, 1, 1, C.violet, K.PLATE_GLINT_ALPHA, "ARTWORK", 0)
    plate.glint:Hide()
    plate.led = Kit.Rect(frame, K.PLATE_LED_X, K.PLATE_LED_Y, K.PLATE_LED_W, K.PLATE_LED_H, C.pink, 1, "ARTWORK", 1)
    plate.label = Kit.Label(frame, opts.text or "", K.PLATE_TEXT, C.cyan, "OVERLAY")
    Kit.Place(plate.label, frame, K.PLATE_TEXT_X, K.PLATE_TEXT_Y, nil, nil, "LEFT", "TOPLEFT")

    if opts.x and opts.y then
        Kit.Place(frame, parent, opts.x, opts.y, opts.width or 1, K.PLATE_H)
    elseif opts.width then
        local ppu = Kit.Ppu(parent)
        frame:SetSize(opts.width / ppu, K.PLATE_H / ppu)
    end
    Kit.HookScript(frame, "OnSizeChanged", function() LayoutPlate(plate) end)
    LayoutPlate(plate)

    Kit.Animate(frame, "led", function(_, elapsed)
        plate.led:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
    end)
    AnimateGlint(plate)
    return plate
end

function InsetSkins.SetText(plate, text)
    if type(plate) == "table" and plate.label then plate.label:SetText(text or "") end
end

-- Replaces the chips ({ { text, color }, ... }; nil or {} clears them).
function InsetSkins.SetChips(plate, chips)
    if type(plate) ~= "table" or not plate.frame then return end
    plate.chipList = chips
    LayoutChips(plate)
end
