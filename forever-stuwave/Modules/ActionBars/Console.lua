-- Forever STUwave: Console
--
-- The Gunsight HUD's action bar chassis (the locked design in
-- mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html, the "Console
-- panel style": CN_* constants, cnTrace, cnBake, drawConsole). ONE plate around the 72
-- buttons, cut 14 at the TOP-LEFT and BOTTOM-RIGHT, with a stepped shoulder tab on top
-- of the right half that holds the 8 HUD keys (a later lane seats them on `FS.Console.tab`,
-- inside `FS.Console.keyArea`). No recess plate behind the buttons.
--
-- UNITS. Everything drawn is written in DESIGN px (2560 x 1440), on `Console.art`, a
-- child frame scaled by FS.Layout.Scale(): one unit there is one design px, which is one
-- physical pixel at 1440p, so a 1 texel line is a 1 pixel line and the baked textures
-- (made at 1 texel = 1 design px) land at their native size. Nine-slice margins and the
-- tab foot's 59.2 x 49.2 box therefore need no conversion. `root` and `tab` are plain UI
-- unit frames (what a key lane wants to parent to); `keyArea` is in UI units.
--
-- WHY IT IS NOT PARENTED TO THE STACK. FSActionBarStack parents secure buttons, so it is
-- protected implicitly and nothing parented to it may change in combat. The Console hangs
-- off UIParent and is only ANCHORED to the stack. Re-seating still waits for combat to
-- end, because ActionBars.lua only publishes new geometry out of combat (its single
-- source, `FS.ActionBars.geometry` + `OnGeometry`); the Console just follows it.
--
-- THE SHAPE IS NOT A NINE-SLICE. A gradient on a nine-sliced texture bands at every slice
-- boundary (it is per vertex, and the plate is nine quads), and the chassis fill is a
-- vertical gradient. So the fill is three plain gradient rects (their colours are the
-- global gradient sampled at their own top and bottom, so they join without a step) plus
-- the two 14 x 14 cut corners sampled out of console_fill_c14 with SetTexCoord. The
-- outline is the same decomposition: plain 1 texel lines and two corner blocks of
-- console_outline_c14. Decomposing it is also what makes the stepped shoulder one
-- continuous path: the chassis top line simply stops where the foot stands, so there is
-- no seam to cover. The halo is console_glow_c14 in nine pieces for the same reason: a
-- halo around the whole rectangle would light the inside of the tab. Four corner blocks
-- and four 1 D strips sampled from its middle; the tab's foot has its own texture
-- (console_tab_foot) with the rail on the 45 degree diagonal and its outside halo.
--
-- OFF SWITCH. `/fsconsole on|off`, saved in ForeverSTUwaveDB.consoleEnabled (default
-- on). Off hides this frame and ActionBars.lua brings the per-pill chrome and the 6 unit
-- pill gap back. In combat the switch is saved at once and applied when combat ends.

local _, FS = ...

local Console = {}
FS.Console = Console

if not (FS.ActionBars and FS.ActionBars.OnGeometry and FS.ActionBars.SetConsoleActive) then
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("console_noactionbars",
            "|cffff4488Forever STUwave|r: Console.lua loaded without ActionBars.lua, no Console")
    end
    return
end

local Theme = FS.Theme or {}
local PREFIX = "|cff22e0ffForever STUwave|r: "

-------------------------------------------------------------------------------
-- Constants (design px; the mockup's CN_*, DK and TAB_DW)
-------------------------------------------------------------------------------

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local TEX = {
    fill = MEDIA .. "console_fill_c14.tga",       -- 64x64 solid plate, TL + BR cut 14
    outline = MEDIA .. "console_outline_c14.tga", -- 64x64 1 texel rail on the same shape
    glow = MEDIA .. "console_glow_c14.tga",       -- 64x64 hollow halo, outline 11 texels in
    foot = MEDIA .. "console_tab_foot.tga",       -- 128x128 over 59.2 x 49.2 design units
    slant = MEDIA .. "tab_slant.tga",             -- 32x32 wedge, 45 degrees stretched square
    round = MEDIA .. "glow_round.tga",            -- soft round dot for the screws
}
Console.TEX = TEX

local C = {
    PAD = 8, MARG = 7, PT = 15, PB = 15, CUT = 14,  -- chassis paddings: sides, extra left margin, above, below
    ZX = 3, ZT = 4, ZY = 6.6,                       -- the button field grown by this places hairlines and silkscreen
    SR = 3,                                         -- screw radius
    TP = 15,                                        -- padding right of the last key, above the keys, and (perpendicular) from the cut to the first key
}
-- COUNT is the most keys the tab holds. The pitch is EVEN (key + GAP): no group gaps.
local KEY = { W = 34, H = 26, C = 6, GAP = 4, PAD = 16, SH = 18, COUNT = 8 }
local ROW_PITCH_DESIGN, BTN_DESIGN = 49.2, 36
local function KeyX(i)
    return KEY.SH + KEY.PAD + i * (KEY.W + KEY.GAP)
end
-- The Bar-matched tab box (design px, from its left foot to the chassis right edge) that holds n
-- keys: the left inset, n keys with n - 1 gaps, and the right padding. Everything about the tab
-- that depends on the key count is this one number.
local function TabBox(n)
    return KEY.SH + KEY.PAD + n * KEY.W + (n - 1) * KEY.GAP + C.TP
end
local function ClampCount(n)
    n = math.floor(tonumber(n) or KEY.COUNT)
    if n < 1 then return 1 end
    if n > KEY.COUNT then return KEY.COUNT end
    return n
end
-- The HUD keys sit as far above the first button row as the rows sit apart (the row
-- gap), measured on the border lines: key bottom = first button top - CN_VG.
C.VG = ROW_PITCH_DESIGN - BTN_DESIGN
C.KB = C.PT - C.VG                                  -- key bottom, below the chassis top line
C.TH = KEY.H - C.KB + C.TP                          -- tab height: the keys plus TP over them
-- The 45 degree cut runs parallel to the first key's top-left chamfer (KEY.C), and sits TP
-- (perpendicular) from it, the padding the keys have to the tab's top and right edges. The
-- cut is x + y = FOOT + TH (tab-local, y down from the tab top), the chamfer x + y =
-- keyX0 + TP + KEY.C, so FOOT = keyX0 + TP + KEY.C - TH - TP * sqrt 2. Negative: the foot
-- lies left of the TabBox's left foot. TH and FOOT do not depend on the key count, so the whole
-- slanted shoulder slides with TabBox(n): fewer keys, a narrower tab, the cut moving right with
-- its first key, and the perpendicular gap from the cut to that key stays TP, the same 15 as the
-- right and top padding.
C.FOOT = KEY.SH + KEY.PAD + C.TP + KEY.C - C.TH - C.TP * math.sqrt(2)
Console.C = C
Console.KEY = KEY

-- Baked texture geometry (media/generate_console_chrome.py)
local TEXN = 64
local GP = 11                  -- glow: texels between the canvas edge and the outline
local GM = 25                  -- glow nine-slice margin = GP + CUT
-- The baked halo's own description (texels; one texel is one design px): the file, its side, the texels
-- between its edge and the outline, the nine-slice margin and the straight middle band that does not vary
-- along an edge. Exported so a shoulder standing on the chassis (ClassShoulder.lua through PetDock.NewShoulder)
-- draws its halo with THIS texture and these strips, which makes it the Console's own halo profile by
-- construction instead of an approximation of it.
local GLOW = { texture = TEX.glow, size = TEXN, pad = GP, margin = GM, mid0 = 28, mid1 = 36 }
Console.GLOW = GLOW
-- How far the drawn Console (halo included) reaches past the button field to the left and
-- right, in design px. ActionBars.lua narrows the stack with it so the halo stays inside the
-- action footprint and clear of the chat terminal (it cannot read the paddings above any
-- other way: it loads first and Console.lua only owns the art).
Console.EXTENT = { left = C.PAD + C.MARG + GP, right = C.PAD + GP }
local FOOT_W, FOOT_H, FOOT_PAD = 59.2, 49.2, 10
local LINE = 1                 -- outline thickness, one texel
local SEAM = 0.5               -- the foot ends half way down the chassis top line

-- Palette
local function Tok(t, r, g, b)
    if t then return t[1], t[2], t[3] end
    return r, g, b
end
local VR, VG, VB = Tok(Theme.COLOR_BORDER, 0.659, 0.333, 0.969)   -- #a855f7 violet
local PR, PG, PB = Tok(Theme.COLOR_HEALTH, 1, 0.180, 0.592)       -- #ff2e97 pink
local MR, MG, MB = Tok(Theme.COLOR_MUTED, 0.616, 0.576, 0.769)    -- #9d93c4 muted
-- The chassis fill, top to bottom: the Deck family gradient.
local FILL_TOP = { 45 / 255, 27 / 255, 78 / 255, 0.80 }
local FILL_BOT = { 11 / 255, 6 / 255, 20 / 255, 0.88 }
local OUTLINE_ALPHA = 0.72
-- Exported so a class shoulder drawn as part of the chassis (ClassShoulder.lua) wears the SAME tint and
-- stroke alpha instead of a copy: the fill's top stop is all a shoulder above the chassis ever shows.
Console.FILL_TOP = FILL_TOP
Console.OUTLINE_ALPHA = OUTLINE_ALPHA

-------------------------------------------------------------------------------
-- Layout: pure geometry
-------------------------------------------------------------------------------

-- The key count the tab is sized for (see SetKeyCount); the default is the full set.
local keyCount = KEY.COUNT
function Console.TabWidth(n) return TabBox(ClampCount(n)) end
function Console.GetKeyCount() return keyCount end

-- The pet dock gap (see SetDockGap): { x0, x1, hx0, hx1 } in design px from the chassis left, as the
-- caller gave it (the halo pair defaults to the line pair), or nil. Compute clamps both to the
-- drawable span of the top line.
local dockGap
-- The gap patch (see SetGapPatchAlpha): the alpha its line and halo carry, 0 = the gap shows open.
local patchAlpha = 0

-- `g` is FS.ActionBars.geometry (UI units, stack-local, y down), `s` the design to
-- UI scale and `n` the key count (default: the current one). Returns the Console in DESIGN px relative to the chassis top-left (y down;
-- the tab is at negative y), plus `originX/originY`, the chassis top-left in the stack's
-- UI space.
function Console.Compute(g, s, n)
    local function d(ui) return ui / s end
    local L = {}
    L.originX = g.fieldLeft - (C.PAD + C.MARG) * s
    L.originY = g.fieldTop - C.PT * s
    local fieldW, fieldH = d(g.fieldRight - g.fieldLeft), d(g.fieldBottom - g.fieldTop)
    L.w = fieldW + C.PAD + C.MARG + C.PAD
    L.h = fieldH + C.PT + C.PB
    L.cut = C.CUT
    L.field = { x = C.PAD + C.MARG, y = C.PT, w = fieldW, h = fieldH }
    L.btn = d(g.btnSize)
    L.rowPitch = d(g.rowPitch)
    L.btnPitch = d(g.btnPitch)
    -- left edge of the first button of each half, relative to the chassis
    L.btnX = { d(g.halfX[1] + g.btnX0 - L.originX), d(g.halfX[2] + g.btnX0 - L.originX) }
    L.spineX = d(g.spineX - L.originX)
    -- the shoulder: its foot stands on the chassis top line, its right edge is the chassis right edge
    L.th = C.TH
    L.tx = L.w - (TabBox(n and ClampCount(n) or keyCount) - C.FOOT)
    -- the pet dock gap, clamped to the span the top line can be drawn on (the TL cut to the foot);
    -- a gap that is empty once clamped, or lies outside the span, is no gap at all
    if dockGap then
        local x0, x1 = math.max(dockGap[1], L.cut), math.min(dockGap[2], L.tx)
        if x1 > x0 then L.gap = { x0 = x0, x1 = x1 } end
        local h0, h1 = math.max(dockGap[3], L.cut), math.min(dockGap[4], L.tx)
        if h1 > h0 then L.haloGap = { x0 = h0, x1 = h1 } end
    end
    return L
end

-- Tab-local rect (UI units, from the tab's top-left, y down) of HUD key slot `index`
-- (0 based, left to right among the SHOWN keys). The tab frame starts at the foot, CN_FOOT in from
-- the TabBox (negative: left of it), so a slot's place does not depend on how many keys are shown.
function Console.KeyRect(index, s)
    s = s or (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
    return { x = (KeyX(index) - C.FOOT) * s, y = C.TP * s, w = KEY.W * s, h = KEY.H * s }
end

-------------------------------------------------------------------------------
-- Frames and textures
-------------------------------------------------------------------------------

local root, art, built
local buildFailed   -- Build threw once: never run it again (each run made a new FSConsole frame)
local drawn         -- the chassis was seated and shown and has not been hidden since
local seatFailed    -- the last Seat threw while nothing was drawn
local parts = { dividers = {}, ticks = {}, chevrons = {}, pips = {}, screws = {} }
Console.parts = parts

-- FS.LogDegradeOnce does not dedupe by key itself, so latch each key here.
local degraded = {}
local function Degrade(key, err)
    if degraded[key] then return end
    degraded[key] = true
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("console_" .. key, PREFIX .. "console " .. key .. ": " .. tostring(err))
    end
end

local function NewTex(layer, sub)
    return art:CreateTexture(nil, layer, nil, sub)
end

local function Solid(layer, sub, r, g, b, a)
    local t = NewTex(layer, sub)
    t:SetColorTexture(r, g, b, a)
    return t
end

local function Textured(layer, sub, path, r, g, b, a)
    local t = NewTex(layer, sub)
    t:SetTexture(path)
    t:SetVertexColor(r, g, b, a)
    return t
end

-- Paints `tex` with a vertical gradient: `bottom` and `top` are { r, g, b, a }.
-- SetGradient multiplies against the texture, so the tex is white. Falls back to a flat
-- tint of the midpoint when the API is missing or throws.
local function Gradient(tex, bottom, top)
    if tex.SetGradient and CreateColor then
        local ok = pcall(tex.SetGradient, tex, "VERTICAL",
            CreateColor(bottom[1], bottom[2], bottom[3], bottom[4]),
            CreateColor(top[1], top[2], top[3], top[4]))
        if ok then return true end
    end
    tex:SetVertexColor((bottom[1] + top[1]) / 2, (bottom[2] + top[2]) / 2,
        (bottom[3] + top[3]) / 2, (bottom[4] + top[4]) / 2)
    return false
end

-- The chassis gradient sampled at fraction f (0 top, 1 bottom).
local function FillAt(f)
    return {
        FILL_TOP[1] + (FILL_BOT[1] - FILL_TOP[1]) * f,
        FILL_TOP[2] + (FILL_BOT[2] - FILL_TOP[2]) * f,
        FILL_TOP[3] + (FILL_BOT[3] - FILL_TOP[3]) * f,
        FILL_TOP[4] + (FILL_BOT[4] - FILL_TOP[4]) * f,
    }
end

-- A gradient rect covering chassis y0..y1 of a chassis `h` tall: the colours are the
-- global gradient at its own top and bottom, so neighbouring pieces meet without a step.
local function ShadeBand(tex, y0, y1, h)
    Gradient(tex, FillAt(y1 / h), FillAt(y0 / h))
end

-- Positions in DESIGN px relative to the chassis top-left, y down (the tab is negative).
local function Place(tex, x, y, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("TOPLEFT", art, "TOPLEFT", x, -y)
    tex:SetSize(w, h)
end

local function PlaceCentre(tex, cx, cy, w, h)
    tex:ClearAllPoints()
    tex:SetPoint("CENTER", art, "TOPLEFT", cx, -cy)
    tex:SetSize(w, h)
end

local function Uv(tex, u0, u1, v0, v1)
    tex:SetTexCoord(u0, u1, v0, v1)
end

local function Rotated(tex, radians)
    if tex.SetRotation then tex:SetRotation(radians) end
end

local function Font(text, size, r, g, b, a)
    local fs = art:CreateFontString(nil, "OVERLAY")
    if Theme.ApplyMono then Theme.ApplyMono(fs, size, { r, g, b, a }) end
    fs:SetText(text)
    return fs
end

local function Build(g)
    if built then return end
    local stack = g.stack
    -- The root draws under the stack: its buttons and the pill chrome sit above it.
    root = CreateFrame("Frame", "FSConsole", UIParent)
    root:SetFrameStrata("LOW")
    root:SetFrameLevel(math.max(0, stack:GetFrameLevel() - 1))
    root:EnableMouse(false)
    Console.root = root

    art = CreateFrame("Frame", nil, root)
    art:EnableMouse(false)
    Console.art = art

    -- The HUD key lane parents to this (UI units, above the chrome).
    local tab = CreateFrame("Frame", "FSConsoleTab", root)
    tab:SetFrameLevel(art:GetFrameLevel() + 1)
    tab:EnableMouse(false)
    Console.tab = tab

    -- halo, outside the outline only (BACKGROUND -8)
    for _, k in ipairs({ "haloTL", "haloTop", "haloTop2", "gapHalo", "haloTabTop", "haloTR", "haloRight", "haloBR", "haloBottom", "haloBL", "haloLeft" }) do
        parts[k] = Textured("BACKGROUND", -8, TEX.glow, VR, VG, VB, 1)
    end

    -- fill (BACKGROUND -7): three gradient bands, the two cut corners, the tab
    for _, k in ipairs({ "fillTop", "fillMid", "fillBottom" }) do
        parts[k] = Solid("BACKGROUND", -7, 1, 1, 1, 1)
    end
    parts.fillTL = Textured("BACKGROUND", -7, TEX.fill, 1, 1, 1, 1)
    parts.fillBR = Textured("BACKGROUND", -7, TEX.fill, 1, 1, 1, 1)
    parts.tabWedge = Textured("BACKGROUND", -7, TEX.slant, FILL_TOP[1], FILL_TOP[2], FILL_TOP[3], FILL_TOP[4])
    parts.tabFill = Solid("BACKGROUND", -7, FILL_TOP[1], FILL_TOP[2], FILL_TOP[3], FILL_TOP[4])

    -- outline (BORDER): plain texel lines, two corner blocks, the foot rail
    for _, k in ipairs({ "lineTop", "lineTop2", "gapLine", "lineLeft", "lineBottom", "lineRight", "lineTabTop" }) do
        parts[k] = Solid("BORDER", 0, VR, VG, VB, OUTLINE_ALPHA)
    end
    parts.cornerTL = Textured("BORDER", 0, TEX.outline, VR, VG, VB, OUTLINE_ALPHA)
    parts.cornerBR = Textured("BORDER", 0, TEX.outline, VR, VG, VB, OUTLINE_ALPHA)
    parts.foot = Textured("BORDER", 1, TEX.foot, VR, VG, VB, 1)

    -- inside (ARTWORK): row hairlines, tick ruler, spine, pips
    for r = 1, 2 do parts.dividers[r] = Solid("ARTWORK", 0, VR, VG, VB, 0.18) end
    for r = 1, 3 do
        for half = 1, 2 do
            for i = 1, 12 do
                parts.ticks[#parts.ticks + 1] = {
                    tex = Solid("ARTWORK", 0, VR, VG, VB, 0.25), row = r, half = half, idx = i,
                }
            end
        end
    end
    parts.spine = Solid("ARTWORK", 0, VR, VG, VB, 0.35)
    for i = 1, 4 do parts.chevrons[i] = Solid("ARTWORK", 0, VR, VG, VB, 0.5) end
    for r = 1, 3 do
        if r == 1 then
            parts.pips[r] = Solid("ARTWORK", 1, PR, PG, PB, 0.7)   -- MAIN
        else
            parts.pips[r] = Solid("ARTWORK", 1, VR, VG, VB, 0.35)
        end
    end

    -- silkscreen and screws (OVERLAY)
    parts.main = Font("MAIN", 8, PR, PG, PB, 0.6)
    parts.serial = Font("FS-CNSL 06", 8, MR, MG, MB, 0.22)
    for i = 1, 2 do
        parts.screws[i] = {
            disc = Textured("OVERLAY", 0, TEX.round, VR, VG, VB, 0.5),
            slash = Solid("OVERLAY", 1, 12 / 255, 5 / 255, 28 / 255, 0.81),
        }
    end
    built = true
end

-------------------------------------------------------------------------------
-- Seating
-------------------------------------------------------------------------------

-- Places a run that may be empty: a zero (or negative) width hides the texture, a real one shows it.
local function PlaceRun(tex, x, y, w, h)
    if w > 0 then
        Place(tex, x, y, w, h)
        tex:Show()
    else
        tex:Hide()
    end
end

-- Alpha only: legal in combat, where Show, Hide and SetPoint on the anchored chassis are not.
local function ApplyPatchAlpha()
    if not built then return end
    parts.gapLine:SetAlpha(patchAlpha)
    parts.gapHalo:SetAlpha(patchAlpha)
end

local function SeatHalo(L)
    local W, H, cut, tx, th = L.w, L.h, L.cut, L.tx, L.th
    local gap = L.haloGap
    local footEnd = tx - FOOT_PAD + FOOT_W
    local mid0, mid1 = GLOW.mid0 / TEXN, GLOW.mid1 / TEXN   -- the straight middle: does not vary along the edge
    local edge0 = (TEXN - GP) / TEXN              -- the texel the outline sits on, right and bottom
    local block1 = 1 - GM / TEXN                  -- start of the far corner block
    -- corner blocks (halo around the cut corners and the square ones)
    Place(parts.haloTL, -GP, -GP, GM, GM);                 Uv(parts.haloTL, 0, GM / TEXN, 0, GM / TEXN)
    Place(parts.haloTR, W - cut, -th - GP, GM, GM);        Uv(parts.haloTR, block1, 1, 0, GM / TEXN)
    Place(parts.haloBR, W - cut, H - cut, GM, GM);         Uv(parts.haloBR, block1, 1, block1, 1)
    Place(parts.haloBL, -GP, H - cut, GM, GM);             Uv(parts.haloBL, 0, GM / TEXN, block1, 1)
    -- straight runs: left, the chassis top up to the foot, the tab top from the foot stub on, right, bottom
    Place(parts.haloLeft, -GP, cut, GP, H - 2 * cut);      Uv(parts.haloLeft, 0, GP / TEXN, mid0, mid1)
    -- (the pet dock gap splits the top run in two: [cut, hx0] and [hx1, tx], the halo's own pair, which
    -- is the line's pair unless SetDockGap was given another)
    PlaceRun(parts.haloTop, cut, -GP, (gap and gap.x0 or tx) - cut, GP)
    Uv(parts.haloTop, mid0, mid1, 0, GP / TEXN)
    PlaceRun(parts.haloTop2, gap and gap.x1 or tx, -GP, gap and tx - gap.x1 or 0, GP)
    Uv(parts.haloTop2, mid0, mid1, 0, GP / TEXN)
    -- (and the gap patch, the top halo's own strip over the gap, carries it whole when its alpha is 1)
    PlaceRun(parts.gapHalo, gap and gap.x0 or 0, -GP, gap and gap.x1 - gap.x0 or 0, GP)
    Uv(parts.gapHalo, mid0, mid1, 0, GP / TEXN)
    Place(parts.haloTabTop, footEnd, -th - GP, (W - cut) - footEnd, GP)
    Uv(parts.haloTabTop, mid0, mid1, 0, GP / TEXN)
    Place(parts.haloRight, W, -th + cut, GP, (H - cut) - (-th + cut))
    Uv(parts.haloRight, edge0, 1, mid0, mid1)
    Place(parts.haloBottom, cut, H, W - 2 * cut, GP);      Uv(parts.haloBottom, mid0, mid1, edge0, 1)
end

local function SeatFill(L)
    local W, H, cut, tx, th = L.w, L.h, L.cut, L.tx, L.th
    local c = cut / TEXN
    Place(parts.fillTop, cut, 0, W - cut, cut);            ShadeBand(parts.fillTop, 0, cut, H)
    Place(parts.fillMid, 0, cut, W, H - 2 * cut);          ShadeBand(parts.fillMid, cut, H - cut, H)
    Place(parts.fillBottom, 0, H - cut, W - cut, cut);     ShadeBand(parts.fillBottom, H - cut, H, H)
    -- the cut corners keep their flat tint: the gradient moves under 8% over 14 units
    Place(parts.fillTL, 0, 0, cut, cut)
    Uv(parts.fillTL, 0, c, 0, c)
    local tl = FillAt(cut / 2 / H)
    parts.fillTL:SetVertexColor(tl[1], tl[2], tl[3], tl[4])
    Place(parts.fillBR, W - cut, H - cut, cut, cut)
    Uv(parts.fillBR, 1 - c, 1, 1 - c, 1)
    local br = FillAt(1 - cut / 2 / H)
    parts.fillBR:SetVertexColor(br[1], br[2], br[3], br[4])
    -- the shoulder: a 45 degree wedge over the foot, then a plain rect to the right edge
    Place(parts.tabWedge, tx, -th, th, th)
    Place(parts.tabFill, tx + th, -th, W - tx - th, th)
end

local function SeatOutline(L)
    local W, H, cut, tx, th = L.w, L.h, L.cut, L.tx, L.th
    local gap = L.gap
    local c = cut / TEXN
    -- chassis: TL cut, top line up to the foot (NOTHING under the tab, and nothing in the pet dock
    -- gap: the line splits into [cut, x0] and [x1, tx]), left, bottom, BR cut
    Place(parts.cornerTL, 0, 0, cut, cut);                 Uv(parts.cornerTL, 0, c, 0, c)
    PlaceRun(parts.lineTop, cut, 0, (gap and gap.x0 or tx) - cut, LINE)
    PlaceRun(parts.lineTop2, gap and gap.x1 or tx, 0, gap and tx - gap.x1 or 0, LINE)
    PlaceRun(parts.gapLine, gap and gap.x0 or 0, 0, gap and gap.x1 - gap.x0 or 0, LINE)
    Place(parts.lineLeft, 0, cut, LINE, H - cut - LINE)
    Place(parts.lineBottom, 0, H - LINE, W - cut, LINE)
    Place(parts.cornerBR, W - cut, H - cut, cut, cut);     Uv(parts.cornerBR, 1 - c, 1, 1 - c, 1)
    -- shoulder: the foot rail (45 degrees, plus a 10 unit stub of the top edge), the top
    -- edge, and ONE right edge from the tab top down to the BR cut
    local footX = tx - FOOT_PAD
    Place(parts.foot, footX, -FOOT_H + SEAM, FOOT_W, FOOT_H)
    Place(parts.lineTabTop, footX + FOOT_W, -th, (W - LINE) - (footX + FOOT_W), LINE)
    Place(parts.lineRight, W - LINE, -th, LINE, (H - cut) + th)
end

local function SeatInside(L)
    local W, H = L.w, L.h
    local f = L.field
    -- row hairlines: mid way down each row gap, across both halves and the spine
    for r = 1, 2 do
        local y = f.y + (r - 1) * L.rowPitch + L.btn + (L.rowPitch - L.btn) / 2
        Place(parts.dividers[r], f.x - C.ZX, y - LINE / 2, f.w + 2 * C.ZX, LINE)
    end
    -- tick ruler: one at each button centre, 2 long, every 4th 4 long, just under the row
    for _, tk in ipairs(parts.ticks) do
        local x = L.btnX[tk.half] + (tk.idx - 1) * L.btnPitch + L.btn / 2
        local y = f.y + (tk.row - 1) * L.rowPitch + L.btn + 1.2
        Place(tk.tex, x - LINE / 2, y, LINE, (tk.idx % 4 == 0) and 4 or 2)
    end
    -- spine: a hairline between the halves, a small chevron at each end
    Place(parts.spine, L.spineX - LINE / 2, f.y, LINE, f.h)
    local arm = math.sqrt(3.2 * 3.2 + 3.4 * 3.4)
    local lean = math.atan2(3.2, 3.4)
    local top, bottom = f.y + 1.7, f.y + f.h - 1.7
    local ch = parts.chevrons
    PlaceCentre(ch[1], L.spineX - 1.6, top, LINE, arm);    Rotated(ch[1], -lean)
    PlaceCentre(ch[2], L.spineX + 1.6, top, LINE, arm);    Rotated(ch[2], lean)
    PlaceCentre(ch[3], L.spineX - 1.6, bottom, LINE, arm); Rotated(ch[3], lean)
    PlaceCentre(ch[4], L.spineX + 1.6, bottom, LINE, arm); Rotated(ch[4], -lean)
    -- a 3 x button pip per row, centred in the left margin
    for r = 1, 3 do
        Place(parts.pips[r], (C.PAD + C.MARG - 3) / 2, f.y + (r - 1) * L.rowPitch, 3, L.btn)
    end
    -- silkscreen. The mockup draws on the alphabetic baseline centred (by cap height) in the
    -- strip; a FontString anchors by its box, whose bottom is the descent below the baseline.
    local size = 8
    local cap, desc = 0.7 * size, 250 / 1024 * size
    local zy0 = f.y - C.ZT
    local mainBase = zy0 - (zy0 - cap) / 2
    local zy1 = f.y + f.h + C.ZY
    local serialBase = H - ((H - zy1) - cap) / 2
    parts.main:ClearAllPoints()
    parts.main:SetPoint("BOTTOMLEFT", art, "TOPLEFT", f.x, -(mainBase + desc))
    parts.serial:ClearAllPoints()
    parts.serial:SetPoint("BOTTOMLEFT", art, "TOPLEFT", 14, -(serialBase + desc))
    -- a screw in each square corner: the shoulder's top right and the chassis bottom left
    local slashLen, slashLean = math.sqrt(4.2 * 4.2 + 2.4 * 2.4), math.atan2(2.4, 4.2)
    local spots = { { W - 7.5, -L.th + 7.5 }, { 7.5, H - 7.5 } }
    for i, spot in ipairs(spots) do
        PlaceCentre(parts.screws[i].disc, spot[1], spot[2], 2 * C.SR + 2, 2 * C.SR + 2)
        PlaceCentre(parts.screws[i].slash, spot[1], spot[2], slashLen, LINE)
        Rotated(parts.screws[i].slash, slashLean)
    end
end

local function Seat(g)
    local s = g.scale or 1
    local L = Console.Compute(g, s)
    Console.layout = L

    root:ClearAllPoints()
    root:SetPoint("TOPLEFT", g.stack, "TOPLEFT", L.originX, -L.originY)
    root:SetSize(L.w * s, L.h * s)
    art:SetScale(s)
    art:ClearAllPoints()
    art:SetPoint("TOPLEFT", root, "TOPLEFT", 0, 0)
    art:SetSize(L.w, L.h)

    SeatHalo(L)
    SeatFill(L)
    SeatOutline(L)
    SeatInside(L)
    ApplyPatchAlpha()

    -- the tab: a UI unit frame over the shoulder, the key lane's parent
    local tab = Console.tab
    tab:ClearAllPoints()
    tab:SetPoint("TOPLEFT", root, "TOPLEFT", L.tx * s, L.th * s)
    tab:SetSize((TabBox(keyCount) - C.FOOT) * s, L.th * s)
    local first = Console.KeyRect(0, s)
    Console.keyArea = {
        x = first.x, y = first.y, h = first.h,
        w = (KeyX(keyCount - 1) + KEY.W - KeyX(0)) * s,
    }
end

-- ActionBars hides each pill's own chrome while its console look is applied, so a console
-- that cannot draw would leave the bars bare. Drop ActionBars' applied look back to the
-- pills. Not inside the geometry callback (that re-seats, and re-enters the subscriber
-- list mid-notification), so a frame later. The saved /fsconsole choice and `enabled` are
-- untouched: this is a fallback for this session, not a setting change. In combat
-- ActionBars holds it until regen.
-- Two causes: Build threw (permanent), or Seat threw while no chassis was on screen
-- (`seatFailed`). A seat failure while the chassis is drawn leaves it up where it was, so the
-- bars are not bare and there is nothing to fall back from. A seat failure can recover: the
-- next successful Seat (for example `/fsconsole on` after the fallback) shows the chassis and
-- clears the flag, and ActionBars hides the pill chrome again as part of that same call.
local fallbackQueued
local function FallBackToPills()
    if fallbackQueued then return end
    if not (C_Timer and C_Timer.After) then
        -- Without a timer the fallback cannot run; say so once instead of leaving bare pills unexplained.
        Degrade("fallback_timer", "C_Timer.After is missing, so the pill fallback cannot run")
        return
    end
    fallbackQueued = true
    C_Timer.After(0, function()
        fallbackQueued = false
        if (buildFailed or seatFailed) and FS.ActionBars.IsConsoleActive() then
            FS.ActionBars.SetConsoleActive(false)
        end
    end)
end

-- ActionBars.lua publishes geometry after every re-seat, always out of combat.
local seatedG   -- the geometry the chassis is drawn from right now, nil while nothing is drawn
local function OnGeometry(g)
    if buildFailed then
        drawn = false
        seatedG = nil
        if root then root:Hide() end
        if g.console then FallBackToPills() end
        return
    end
    if not (g.console and g.shown) then
        drawn = false
        seatedG = nil
        if root then root:Hide() end
        return
    end
    if not built then
        local ok, err = pcall(Build, g)
        if not ok then
            -- A half built chassis stays hidden and is never rebuilt; say so once.
            buildFailed = true
            drawn = false
            seatedG = nil
            if root then root:Hide() end
            Degrade("build", err)
            FallBackToPills()
            return
        end
    end
    local ok, err = pcall(Seat, g)
    if not ok then
        Degrade("seat", err)
        if not drawn then
            seatFailed = true
            root:Hide()
            FallBackToPills()
        end
        return
    end
    seatFailed = false
    drawn = true
    seatedG = g
    root:Show()
end

-- Sizes the shoulder tab for `n` shown HUD keys (1 to KEY.COUNT, clamped): the tab box is the left
-- inset plus the keys at the even pitch plus the 15 right padding, and the whole slanted shoulder
-- (halo, fill, wedge, foot rail, outline) re-seats on that edge. The key lane seats the keys in
-- slots with KeyRect, which does not change with the count. The chassis is anchored to the
-- protected action stack, so this is refused in combat (returns false, nothing changes and the
-- count is not recorded): the caller asks again at PLAYER_REGEN_ENABLED. Returns true when the
-- count is in force (also while the chassis is not drawn: the next geometry uses it).
function Console.SetKeyCount(n)
    if InCombatLockdown() then return false end
    n = ClampCount(n)
    if n == keyCount then return true end
    keyCount = n
    if built and seatedG then
        local ok, err = pcall(Seat, seatedG)
        if not ok then Degrade("seat_keys", err) end
    end
    return true
end

-- Opens the top outline and its halo between `x0` and `x1` (design px from the chassis left) where
-- the pet panel docks, the way the key tab omits the line under itself: the top line and the top
-- halo each split into [TL cut, x0] and [x1, foot], and the chassis fill stays whole. An optional
-- second pair `hx0, hx1` gives the HALO its own span (the pet dock lets the line run under its sides
-- but keeps the Console's glow off its own side glow); omitted or not two numbers, the halo uses
-- x0, x1. The GAP IS COVERED by the gap patch (parts.gapLine over x0..x1, parts.gapHalo over
-- hx0..hx1, see SetGapPatchAlpha): shown at alpha 1 it makes the outline unbroken, at alpha 0 the gap
-- is open. Each span is clamped to the cut-to-foot run; one that is empty once clamped, or lies
-- outside it, draws no gap (and no patch). nil, nil (or anything that is not two numbers) clears
-- it. The gap is kept and re-seated with the chassis (a key count change, a rescale, the next
-- draw), and applied at once when the chassis is drawn.
-- Same rule as SetKeyCount: the chassis is anchored to the protected action stack, so this is
-- refused in combat (returns false, nothing changes and nothing is recorded); the caller asks
-- again at PLAYER_REGEN_ENABLED. Returns true when the gap is in force.
function Console.SetDockGap(x0, x1, hx0, hx1)
    if InCombatLockdown() then return false end
    local gap
    if type(x0) == "number" and type(x1) == "number" and x0 == x0 and x1 == x1 then
        if not (type(hx0) == "number" and type(hx1) == "number" and hx0 == hx0 and hx1 == hx1) then
            hx0, hx1 = x0, x1
        end
        gap = { x0, x1, hx0, hx1 }
    end
    if (gap == nil and dockGap == nil) or (gap and dockGap and gap[1] == dockGap[1] and gap[2] == dockGap[2]
        and gap[3] == dockGap[3] and gap[4] == dockGap[4]) then
        return true
    end
    dockGap = gap
    if built and seatedG then
        local ok, err = pcall(Seat, seatedG)
        if not ok then Degrade("seat_gap", err) end
    end
    return true
end

-- The gap patch: a 1 texel line and a halo strip over exactly the dock gap, built with the top line's
-- and top halo's own recipe (colour, alpha, layer, glow strip), so at alpha 1 the top outline reads
-- as unbroken and at alpha 0 the gap is open. It is seated with the gap (a key count change, a
-- rescale, the next draw) and hidden with it, and ONLY its alpha is driven from outside: SetAlpha is
-- legal in combat, which is the point (the pet dock closes the hole the moment the pet panel goes,
-- while SetDockGap itself waits for regen). 0 to 1, clamped; remembered across reseats and before
-- the chassis exists. A non-number is refused with false and changes nothing.
function Console.SetGapPatchAlpha(a)
    if type(a) ~= "number" or a ~= a then return false end
    patchAlpha = math.max(0, math.min(1, a))
    ApplyPatchAlpha()
    return true
end

function Console.GetGapPatchAlpha()
    return patchAlpha
end

-- True while the chassis is seated and shown (and has not been hidden since): the pet panel docks
-- into its top edge only then.
function Console.IsDrawn()
    return drawn == true
end

-------------------------------------------------------------------------------
-- On / off
-------------------------------------------------------------------------------

local enabled = true

function Console.IsActive()
    return enabled
end

local function Say(msg)
    print(PREFIX .. msg)
end

function Console.SetActive(on)
    enabled = on and true or false
    ForeverSTUwaveDB = ForeverSTUwaveDB or {}
    ForeverSTUwaveDB.consoleEnabled = enabled
    local applied, why = FS.ActionBars.SetConsoleActive(enabled)
    local word = enabled and "on" or "off"
    if applied and enabled and (buildFailed or seatFailed) then
        Say("console on saved, but it failed to draw this session; the pills keep their own chrome")
    elseif applied then
        Say("console " .. word .. (enabled and "" or ", per pill chrome restored"))
    elseif why == "combat" then
        Say("console " .. word .. " saved, it switches when combat ends")
    else
        Say("console " .. word .. " saved, it applies once the action bars are up")
    end
end

SLASH_FSCONSOLE1 = "/fsconsole"
SlashCmdList["FSCONSOLE"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")
    if msg == "on" or msg == "off" then
        Console.SetActive(msg == "on")
    else
        Say("/fsconsole on | off   (currently " .. (enabled and "on" or "off") .. ")")
    end
end

FS.ActionBars.OnGeometry(OnGeometry)

-- ForeverSTUwaveDB is restored by PLAYER_LOGIN. ActionBars.lua's own PLAYER_LOGIN
-- loader is registered first, so the stack normally exists by now; if it does not (a
-- login in combat), the flag is simply held until the stack is built.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    enabled = not (type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.consoleEnabled == false)
    FS.ActionBars.SetConsoleActive(enabled)
end)
