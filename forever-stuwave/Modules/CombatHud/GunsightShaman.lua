-- Forever STUwave: Gunsight Class Module for the Shaman: the totem poles
--
-- The approved design is mockups/gunsight-class-module-shaman-2026-10-08.html, Concept A "Totem Poles": poolMod(y0), pole(),
-- head() and crown(). Four carved poles (Fire the wide hero pole, then Earth, Water, Air) stand on a violet ground line. Each pole
-- is 8 blocks of its own lifetime: blocks leave from the top, so the carved head sinks toward the ground, and the last block turns
-- amber (re-drop). The block count is ceil(remaining / duration * 8). An amber re-drop band runs behind the last block row.
-- Every image px number is in the constants block with its mockup name, and gunsightshaman-harness.py re-reads them from the HTML.
--
-- DATA. Everything comes from FS.ShamanTotems (ShamanTotems.lua), which owns the client facts: whether a totem is up (the duration
-- object, since in combat every GetTotemInfo return is secret), its plain numbers when they are knowable (an out of combat read, else
-- the drop stamped from the cast event) and FAR. This file reads plain records and never touches a secret.
--
-- LOOKS of one pole (the mockup's states):
--   blocks  a totem is up and its numbers are known: lit blocks in the element colour, the last one amber, the time under the ground
--           ("22s", "4m", a "~" in front while it only comes from the cast ledger).
--   bar     up by the duration object alone (no number is knowable, for example after a /reload in combat): a StatusBar driven by
--           StatusBar:SetTimerDuration drains in place of the blocks, the head rides its top, the time reads "?". Needs the client to
--           take the remaining time direction; without it the bar stays full (the pole is still marked up).
--   down    nothing stands in an element that is open: a hollow amber dashed head and a plus sign, DROP under the ground.
--   locked  the element is not open yet (Earth 4, Fire 10, Water 20, Air 30): a dotted empty mold with its level and name.
--   far     a totem you walked away from (ShamanTotems sets it from the drop position): a ghost pole, a dashed amber head, FAR.
--
-- The shock trace along the ground and the Fire Nova ring are GunsightShamanShocks.lua's (FS.GunsightShamanShocks: Build(frame) ->
-- section, Seat(section, rect, scale), OnShow(section), OnHide(section); every call is feature detected and pcalled, the table may
-- be absent). There is no KICK tag in that lane: KICK comes from GunsightTape.lua's class neutral tag. The poles tell the section
-- where the Fire totem is through `section.SetFire(up, headY)` (up: the Fire totem stands and is not FAR; headY: the Fire head's
-- centre in image px from the rect's top), called only when one of the two changed and once more after the section's OnShow. The
-- footer row below the ground (NOVA and the right hand end of the ground line's trace) is left free for it.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide stops
-- the OnUpdate and the subscription; onShow subscribes, re-reads the totems and repaints. ShamanTotems keeps listening through
-- onHide (it only records), so a drop made while hidden is still known. Plain frames only.
--
-- TICKER. ONE OnUpdate on the module frame, throttled to TICK seconds, installed only while a totem is up and the module is shown.
-- The tick path allocates nothing: the time strings come from tables built at load, and a pole writes only what changed.
--
-- Nothing here is verified in game; the harness is a strict mock.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.G) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightShaman = FS.GunsightShaman or {}
local Shaman = FS.GunsightShaman

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil = math.floor, math.ceil

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightshaman-harness.py re-reads them from poleMod)
-------------------------------------------------------------------------------

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

-- Module coordinates are image px from the module's top left: x from 0 to W across the area's width less the inset, y from 0 at
-- the area's top (the mockup's y0). seat(rect) centres the module across rect.w, so rect.x + 7 is the mockup's x = 1220.
local C = {
    W = 188, H = 114,                         -- poleMod: ground x0 = 1220 to 1408; the module fills 114 of the area's 128
    GY = 78,                                  -- gy = y0 + 78, the ground line
    NB = 8, BP = 6, BH = 5,                   -- NB blocks of BP px pitch, BH tall
    ZONE_W = 158,                             -- rect(x0, gy - BP, x1 - x0 = 158, BP, amber, .11)
    ZONE_A = 0.11, ZONE_LINE_A = 0.55,        -- the band fill, and the dashed line above it
    ZONE_DASH = { 4, 3 },                     -- line(.., gy - BP - 1, .., amber, .55, 1, '4 3')
    GROUND_TH = 1.4, GROUND_A = 0.75,         -- line(x0, gy, 1408, gy, violet, .75, 1.4)
    MOLD_A = 0.22, MOLD_LOCKED_A = 0.28,      -- the mold's dashed stroke (violet .22), and the locked one (.28)
    MOLD_FILL_A = 0.05,                       -- the mold's fill: the element colour .05
    HEAD_H = 9, HEAD_MIX = 0.42,              -- ch(hx, hy, w, 9, 2), mix(bg, c, .42)
    HEAD_DOWN_MIX = 0.12,                     -- the DROP head: mix(bg, amber, .12)
    FIRE_RING_DY = 3,                         -- the Nova ring is centred 3 px below the head's top (GunsightShamanShocks FIRE_Y 24 = a full head)
    CROWN_UP = 3,                             -- the crown is centred 3 px above the head (ty + 3, the head starts at ty + 6)
    CROWN_FAR_MIX = 0.35,                     -- a FAR crown: mix(c, bg, .35)
    EYE_Y = 3, EYE_H = 3, EYE_A = 0.9,        -- rect(cx -+ .., hy + 3, .., 3, '#0a0416', .9)
    HEAD_GLOW_A = 0.5,                        -- the head's soft glow (the mockup's gls filter), as the Seal tile's
    OP_UP = 0.95, OP_EST = 0.72, OP_FAR = 0.42,   -- block opacity: a read, an estimate (the cast ledger), a ghost
    LABEL_Y = 19, LABEL_SIZE = 12, LABEL_HERO = 15,   -- txt(cx, gy + 19, lab, hero ? 15 : 12, white, middle)
    PLUS_BASE = 8, PLUS_SIZE = 10,            -- txt(cx, hy + 8, '+', 10, amber, middle)
    LV_Y = -26, LV_SIZE = 11, LV_A = 0.8,     -- txt(cx, gy - NB * BP / 2 - 2, 'L' + lv, 11, muted, .8)
    NM_Y = -13, NM_SIZE = 9, NM_A = 0.55,     -- txt(cx, gy - NB * BP / 2 + 11, name, 9, muted, .55)
    TICK = 0.1,                               -- seconds between OnUpdate passes
    -- the baked art (tools/assets/generate_totem_pole.py): TEX_SCALE texels per image px, PAD px of margin on a stroked piece
    TEX_SCALE = 4, PAD = 1,
    -- Mononoki Bold, as GunsightSeals.lua: the line box's middle sits CAP * size above the baseline. UNVERIFIED in game.
    CAP = 325 / 1024,
    GLOW_PAD = 4,                             -- the cut2 glow's pad (Theme.SLICE_CUT2_GLOW_PAD)
    HEAD_CUT = 2,                             -- the head's chamfer
    COLORS = {                                -- the mockup's :root tokens
        bg = Hex("#0d0620"), violet = Hex("#a855f7"), amber = Hex("#ffb648"), muted = Hex("#9d93c4"),
        white = Hex("#f3fbff"), ink = Hex("#0a0416"),
    },
    -- Pole x and width from PX = { fire: [1220, 50], earth: [1274, 32], water: [1310, 32], air: [1346, 32] } less 1220; ins is the
    -- block inset (5 for the hero pole, 3 for the others); crown scale k from generate_totem_glyphs.py (the glyph box is 16 / k px)
    POLES = {
        { key = "fire", x = 0, w = 50, ins = 5, hero = true, level = 10, name = "Fire", crownK = 1.25 },
        { key = "earth", x = 54, w = 32, ins = 3, level = 4, name = "Earth", crownK = 1.25 },
        { key = "water", x = 90, w = 32, ins = 3, level = 20, name = "Water", crownK = 1.05 },
        { key = "air", x = 126, w = 32, ins = 3, level = 30, name = "Air", crownK = 1.05 },
    },
    EYE = { hero = { off = 9, w = 5, off2 = 4 }, narrow = { off = 6, w = 3, off2 = 3 } },   -- eye offsets from the head's centre
    TEXT_MAX_S = 99,                          -- under this many seconds the label counts seconds, over it minutes
}
C.MOLD_H = C.NB * C.BP - 1                    -- rect(.., NB * BP - 1): 47
Shaman.C = C
local K, POLES = C.COLORS, C.POLES

local WHITE = { 1, 1, 1 }
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"

local function Pow2(n)
    local p = 1
    while p < n do p = p * 2 end
    return p
end

-- A baked piece: its file, the cropped art's size in texels and the canvas it sits in (top left)
local function Piece(name, w, h, stroked)
    local pad = stroked and C.PAD * 2 or 0
    local aw, ah = (w + pad) * C.TEX_SCALE, (h + pad) * C.TEX_SCALE
    return { path = MEDIA .. name .. ".tga", right = aw / Pow2(aw), bottom = ah / Pow2(ah) }
end
Shaman.Piece = Piece

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshaman_" .. key,
            "|cffff4488Forever STUwave|r: gunsight shaman module: " .. tostring(msg))
    end
end

local Totems                   -- FS.ShamanTotems, resolved at build
local mod                      -- the module frame itself, a child of the area host
local P = {}                   -- pole slot -> its parts (exposed as Shaman.parts)
local zoneParts = {}
local seats = {}               -- closures re-run by every seat(rect)
local OX, OY = 0, 0            -- the module's top left in image px, from the rect seat() last got
local subscribed = false
local ticking = false
local acc = 0
local section                  -- what GunsightShamanShocks.Build returned, if anything
local lastRect
local fireUp, fireY            -- what the section was last told about the Fire totem (nil until the first paint)

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

local function Tex(parent, layer, sub)
    return (parent or mod):CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
end

local function Solid(t, c, a)
    t:SetColorTexture(c[1], c[2], c[3], a)
end

local function Tint(t, c, a)
    t:SetVertexColor(c[1], c[2], c[3], a)
end

-- A solid rectangle from (x, y), w by h image px.
local function Rect(x, y, w, h, c, a, layer, sub)
    local t = Tex(nil, layer, sub)
    Solid(t, c, a)
    Seat(function()
        At(t, "TOPLEFT", x, y)
        t:SetSize(ui(w), ui(h))
    end)
    return t
end

-- A baked piece (white art in the top left of a power of two canvas) from (x, y), w by h image px, cropped by its texcoords.
local function Baked(piece, x, y, w, h, layer, sub)
    local t = Tex(nil, layer, sub)
    t:SetTexture(piece.path)
    t:SetTexCoord(0, piece.right, 0, piece.bottom)
    Seat(function()
        At(t, "TOPLEFT", x, y)
        t:SetSize(ui(w), ui(h))
    end)
    return t
end

local function HDashes(y, x0, x1, dash, c, a, th, layer, sub)
    local list, x = {}, x0
    while x < x1 - 1e-6 do
        list[#list + 1] = Rect(x, y - th / 2, math.min(x1, x + dash[1]) - x, th, c, a, layer, sub)
        x = x + dash[1] + dash[2]
    end
    return list
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- Text on a mockup baseline, centred at x: the line is centred C.CAP * size above the baseline.
local function Text(parent, text, size, x, baseline)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("CENTER")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(size), fs.cur)
        At(fs, "CENTER", x, baseline - C.CAP * size)
    end)
    fs:SetText(text)       -- after Seat, which sets the font: SetText on a FontString with none throws "Font not set"
    return fs
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function ElementColor(key)
    local tokens = FS.Theme and FS.Theme.COLOR_TOTEM
    local c = type(tokens) == "table" and tokens[key]
    if type(c) == "table" then return c end
    local fallback = { fire = "#ff5a3c", earth = "#a8e063", water = "#4aa8ff", air = "#e2d4ff" }
    return Hex(fallback[key])
end

local function BuildPole(slot, def)
    local p = { slot = slot, def = def, color = ElementColor(def.key), view = {} }
    local ins, x = def.ins, def.x
    local inner = def.w - 2 * ins
    local hw = def.w - 2
    p.inner, p.hw, p.cx = inner, hw, x + def.w / 2
    local top = C.GY - C.NB * C.BP

    -- the mold: the faint element fill and the dashed violet stroke
    p.moldFill = Rect(x + ins, top, inner, C.MOLD_H, p.color, C.MOLD_FILL_A, "BACKGROUND", 0)
    p.moldLine = Baked(Piece("pole_mold_" .. inner, inner, C.MOLD_H, true), x + ins - C.PAD, top - C.PAD,
        inner + 2 * C.PAD, C.MOLD_H + 2 * C.PAD, "BACKGROUND", 1)
    Tint(p.moldLine, K.violet, C.MOLD_A)

    -- the blocks, bottom up
    local block = Piece("pole_block_" .. inner, inner, C.BH, false)
    p.blocks = {}
    for i = 1, C.NB do
        p.blocks[i] = Baked(block, x + ins, C.GY - i * C.BP, inner, C.BH, "ARTWORK", 0)
        p.blocks[i]:Hide()
    end

    -- the engine timed bar, for a totem that is up with no number: it fills from the bottom of the mold
    local bar = CreateFrame("StatusBar", nil, mod)
    bar:SetFrameLevel(mod:GetFrameLevel() + 1)
    bar:SetStatusBarTexture(FLAT)
    if bar.SetOrientation then bar:SetOrientation("VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(1)
    bar:Hide()
    Seat(function()
        At(bar, "TOPLEFT", x + ins, top)
        bar:SetSize(ui(inner), ui(C.MOLD_H))
    end)
    p.bar = bar

    -- the head: a plain frame above the blocks, sunk with the pole
    local head = CreateFrame("Frame", nil, mod)
    head:SetFrameLevel(mod:GetFrameLevel() + 2)
    head:EnableMouse(false)
    p.head = head
    local base = MEDIA .. "slice_cut2_"
    local cut = C.HEAD_CUT
    local Theme = FS.Theme
    p.headFill = Theme.AddSliceTexture(head, base .. "fill_c" .. cut .. ".tga", WHITE, "BACKGROUND", 0)
    Theme.ApplyNineSlice(p.headFill, cut)
    p.headEdge = Theme.AddSliceTexture(head, base .. "outline_c" .. cut .. ".tga", WHITE, "BORDER", 0)
    Theme.ApplyNineSlice(p.headEdge, cut)
    p.headGlow = Theme.AddSliceTexture(head, base .. "glow_c" .. cut .. ".tga", WHITE, "BORDER", -1, -C.GLOW_PAD)
    Theme.ApplyNineSlice(p.headGlow, C.GLOW_PAD + cut)
    p.headGlow:SetBlendMode("ADD")
    -- the dashed stroke of the DROP and FAR heads: a baked piece with a margin, so it sits PAD px out on every side
    local dash = Piece("pole_dash_" .. hw, hw, C.HEAD_H, true)
    p.headDash = head:CreateTexture(nil, "ARTWORK", nil, 0)
    p.headDash:SetTexture(dash.path)
    p.headDash:SetTexCoord(0, dash.right, 0, dash.bottom)
    local eye = def.hero and C.EYE.hero or C.EYE.narrow
    p.eyeL = head:CreateTexture(nil, "ARTWORK", nil, 1)
    p.eyeR = head:CreateTexture(nil, "ARTWORK", nil, 1)
    Solid(p.eyeL, K.ink, C.EYE_A)
    Solid(p.eyeR, K.ink, C.EYE_A)
    p.crown = head:CreateTexture(nil, "ARTWORK", nil, 2)
    p.crown:SetTexture(MEDIA .. "totem_" .. def.key .. ".tga")
    local glyph = 16 / def.crownK                        -- the 32 texel glyph box is 16 units, one unit k per crown px
    p.plus = head:CreateFontString(nil, "OVERLAY")
    p.plus.cur = { 1, 1, 1, 1 }
    p.plus:SetJustifyH("CENTER")
    Seat(function()
        head:SetSize(ui(hw), ui(C.HEAD_H))
        p.headDash:ClearAllPoints()
        p.headDash:SetPoint("TOPLEFT", head, "TOPLEFT", -ui(C.PAD), ui(C.PAD))
        p.headDash:SetSize(ui(hw + 2 * C.PAD), ui(C.HEAD_H + 2 * C.PAD))
        p.eyeL:ClearAllPoints()
        p.eyeL:SetPoint("TOPLEFT", head, "TOPLEFT", ui(hw / 2 - eye.off), -ui(C.EYE_Y))
        p.eyeL:SetSize(ui(eye.w), ui(C.EYE_H))
        p.eyeR:ClearAllPoints()
        p.eyeR:SetPoint("TOPLEFT", head, "TOPLEFT", ui(hw / 2 + eye.off2), -ui(C.EYE_Y))
        p.eyeR:SetSize(ui(eye.w), ui(C.EYE_H))
        p.crown:ClearAllPoints()
        p.crown:SetPoint("CENTER", head, "TOP", 0, ui(C.CROWN_UP))
        p.crown:SetSize(ui(glyph), ui(glyph))
        FS.Theme.ApplyMono(p.plus, ui(C.PLUS_SIZE), p.plus.cur)
        p.plus:ClearAllPoints()
        p.plus:SetPoint("CENTER", head, "TOP", 0, -ui(C.PLUS_BASE - C.CAP * C.PLUS_SIZE))
    end)
    p.plus:SetText("+")
    TextColor(p.plus, K.amber, 1)
    head:Hide()

    -- the head sits on top of the lit blocks, or on the bar's fill (which the engine moves)
    p.seatHead = function()
        local v = p.view
        head:ClearAllPoints()
        local fill = v.mode == "bar" and p.bar.GetStatusBarTexture and p.bar:GetStatusBarTexture() or nil
        if fill then
            head:SetPoint("BOTTOM", fill, "TOP", 0, 0)
        else
            At(head, "TOPLEFT", p.cx - hw / 2, C.GY - (v.lit or 0) * C.BP - C.HEAD_H)
        end
    end
    Seat(p.seatHead)

    -- the label under the ground, and the locked pole's level and name
    local size = def.hero and C.LABEL_HERO or C.LABEL_SIZE
    p.label = Text(mod, "", size, p.cx, C.GY + C.LABEL_Y)
    p.lv = Text(mod, "L" .. def.level, C.LV_SIZE, p.cx, C.GY + C.LV_Y)
    p.nm = Text(mod, def.name, C.NM_SIZE, p.cx, C.GY + C.NM_Y)
    TextColor(p.lv, K.muted, C.LV_A)
    TextColor(p.nm, K.muted, C.NM_A)
    p.lv:Hide()
    p.nm:Hide()
    return p
end

local function BuildGround()
    -- the re-drop zone: the last block row across all poles, then the ground line itself
    zoneParts.band = Rect(0, C.GY - C.BP, C.ZONE_W, C.BP, K.amber, C.ZONE_A, "BACKGROUND", 0)
    zoneParts.dashes = HDashes(C.GY - C.BP - 1, 0, C.ZONE_W, C.ZONE_DASH, K.amber, C.ZONE_LINE_A, 1, "BACKGROUND", 1)
    zoneParts.ground = Rect(0, C.GY - C.GROUND_TH / 2, C.W, C.GROUND_TH, K.violet, C.GROUND_A, "ARTWORK", 1)
end

-------------------------------------------------------------------------------
-- Look (one pole at a time; every write is behind a compare with what the pole last wore)
-------------------------------------------------------------------------------

-- The time strings, made once: the tick path cannot format or concatenate.
local SEC, EST_SEC, MIN, EST_MIN = {}, {}, {}, {}
for i = 0, C.TEXT_MAX_S do SEC[i] = i .. "s"; EST_SEC[i] = "~" .. i .. "s" end
for i = 1, 6 do MIN[i] = i .. "m"; EST_MIN[i] = "~" .. i .. "m" end
local LABEL_DROP, LABEL_FAR, LABEL_UNKNOWN = "DROP", "FAR", "?"

-- "22s" under 100 s (a ceiling), "4m" above (a ceiling, clamped at 6); a "~" in front for an estimate.
local function TimeLabel(rem, est)
    if rem <= C.TEXT_MAX_S then
        local n = ceil(rem)
        if n < 0 then n = 0 end
        return est and EST_SEC[n] or SEC[n]
    end
    local m = ceil(rem / 60)
    if m > 6 then m = 6 end
    return est and EST_MIN[m] or MIN[m]
end
Shaman.TimeLabel = TimeLabel

local HEAD_NONE, HEAD_ON, HEAD_FAR, HEAD_DOWN = 0, 1, 2, 3

local function TimerOptions()
    local E = _G.Enum
    if type(E) ~= "table" then return nil, nil end
    local dirs, interps = E.StatusBarTimerDirection, E.StatusBarInterpolation
    local dir = type(dirs) == "table" and dirs.RemainingTime or nil
    local interp = type(interps) == "table" and interps.Immediate or nil
    return dir, interp
end

-- Drives the bar from the duration object. A client without the remaining time direction cannot drain it, so the bar rests full.
local function DriveBar(p, obj)
    local bar = p.bar
    if obj ~= nil and type(bar.SetTimerDuration) == "function" then
        local dir, interp = TimerOptions()
        if dir ~= nil and interp ~= nil then
            local ok = pcall(bar.SetTimerDuration, bar, obj, interp, dir)
            if ok then return end
        end
    end
    bar:SetValue(1)
end

local function PaintHead(p, headMode)
    local v = p.view
    if headMode == v.headMode then return end
    v.headMode = headMode
    local head, c = p.head, p.color
    if headMode == HEAD_NONE then
        head:Hide()
        return
    end
    head:Show()
    local down, ghost = headMode == HEAD_DOWN, headMode == HEAD_FAR
    local fillColor = down and Mix(K.bg, K.amber, C.HEAD_DOWN_MIX) or Mix(K.bg, c, C.HEAD_MIX)
    Tint(p.headFill, fillColor, 1)
    p.headEdge:SetShown(headMode == HEAD_ON)
    Tint(p.headEdge, c, 1)
    p.headDash:SetShown(down or ghost)
    Tint(p.headDash, K.amber, 1)
    p.headGlow:SetShown(headMode == HEAD_ON or down)
    Tint(p.headGlow, down and K.amber or c, C.HEAD_GLOW_A)
    p.eyeL:SetShown(not down)
    p.eyeR:SetShown(not down)
    p.crown:SetShown(not down)
    Tint(p.crown, ghost and Mix(c, K.bg, C.CROWN_FAR_MIX) or c, 1)
    p.plus:SetShown(down)
end

local function PaintBlocks(p, lit, amberOne, alpha)
    local v = p.view
    if lit == v.lit and amberOne == v.amberOne and alpha == v.alpha then return end
    v.lit, v.amberOne, v.alpha = lit, amberOne, alpha
    for i = 1, C.NB do
        local b = p.blocks[i]
        if i <= lit then
            Tint(b, (amberOne and i == 1) and K.amber or p.color, alpha)
            b:Show()
        else
            b:Hide()
        end
    end
end

local function PaintLabel(p, text, color, alpha)
    local v = p.view
    if text == v.text and color == v.tone then return end
    v.text, v.tone = text, color
    if text == "" then p.label:Hide(); return end
    p.label:SetText(text)
    TextColor(p.label, color, alpha)
    p.label:Show()
end

local PushFire                 -- defined with the shocks seam below

local function PaintPole(p, now)
    local st = Totems.Get(p.slot)
    local v = p.view
    local mode, lit, far, est = "locked", 0, false, false
    if st.up then
        far = st.far == true
        local n = Totems.Blocks(p.slot, now)
        if n then
            mode, lit, est = "blocks", n, st.source == "cast"
        else
            mode, est = "bar", true
        end
    elseif st.unlocked then
        mode = "down"
    end

    local text, tone, alpha = "", K.white, 1
    if mode == "blocks" then
        if far then text, tone = LABEL_FAR, K.amber
        else text, tone = TimeLabel(Totems.Remaining(p.slot, now) or 0, est), (lit == 1) and K.amber or K.white end
    elseif mode == "bar" then
        if far then text, tone = LABEL_FAR, K.amber else text, tone = LABEL_UNKNOWN, K.muted end
    elseif mode == "down" then
        text, tone = LABEL_DROP, K.amber
    end

    local modeChanged = mode ~= v.mode
    if modeChanged then
        v.mode = mode
        local locked = mode == "locked"
        p.moldFill:SetShown(not locked)
        Tint(p.moldLine, K.violet, locked and C.MOLD_LOCKED_A or C.MOLD_A)
        p.lv:SetShown(locked)
        p.nm:SetShown(locked)
        p.bar:SetShown(mode == "bar")
        if mode ~= "blocks" then PaintBlocks(p, 0, false, 1) end
    end

    if mode == "blocks" then
        PaintBlocks(p, lit, lit == 1, far and C.OP_FAR or (est and C.OP_EST or C.OP_UP))
    end
    if mode == "bar" then
        local barAlpha = far and C.OP_FAR or C.OP_EST
        if modeChanged or barAlpha ~= v.barAlpha then
            v.barAlpha = barAlpha
            local c = p.color
            p.bar:SetStatusBarColor(c[1], c[2], c[3], barAlpha)
        end
        if modeChanged or st.obj ~= v.obj then
            v.obj = st.obj
            DriveBar(p, st.obj)
        end
    else
        v.obj = nil
    end

    local headMode = HEAD_NONE
    if mode == "down" then headMode = HEAD_DOWN
    elseif mode == "blocks" or mode == "bar" then headMode = far and HEAD_FAR or HEAD_ON end
    PaintHead(p, headMode)

    if modeChanged or mode == "blocks" and v.seatedLit ~= lit then
        v.seatedLit = lit
        p.seatHead()
    end
    PaintLabel(p, text, tone, 1)

    if p.slot == 1 then
        -- the Nova ring wants a Fire totem that stands within reach, and the head's centre (a bar pole counts as a full one)
        local nb = mode == "blocks" and lit or C.NB
        PushFire(st.up == true and not far, C.GY - nb * C.BP - C.HEAD_H + C.FIRE_RING_DY)
    end
end

-------------------------------------------------------------------------------
-- Live layer
-------------------------------------------------------------------------------

local function PaintAll(now)
    for slot = 1, #POLES do
        local p = P[slot]
        local ok, err = pcall(PaintPole, p, now)
        if not ok then LogOnce("paint", err) end
    end
end

local Sync
local function OnChange(slot)
    if not subscribed then return end
    local p = P[slot]
    if p then
        local ok, err = pcall(PaintPole, p, GetTime())
        if not ok then LogOnce("paint", err) end
    end
    Sync()
end

local function DoTick(now)
    Totems.Tick(now)
    for slot = 1, #POLES do
        if Totems.Get(slot).up then PaintPole(P[slot], now) end
    end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local ok, err = pcall(DoTick, GetTime())
    if not ok then
        LogOnce("tick", err)
    end
    Sync()
end

-- The OnUpdate runs only while the module is shown and a totem stands.
function Sync()
    local want = subscribed and mod ~= nil and Totems ~= nil and Totems.AnyUp()
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

-------------------------------------------------------------------------------
-- The shock trace, the Nova ring (GunsightShamanShocks.lua): feature detected, never fatal
-------------------------------------------------------------------------------

local function Shocks(name, ...)
    local S = FS.GunsightShamanShocks
    if type(S) ~= "table" or type(S[name]) ~= "function" then return nil end
    local ok, result = pcall(S[name], ...)
    if not ok then
        LogOnce("shocks_" .. name, "GunsightShamanShocks." .. name .. " failed: " .. tostring(result))
        return nil
    end
    return result
end

-- Tells the section where the Fire totem is; a call only when either value changed, or when forced (the section's OnShow re-reads)
function PushFire(up, y, force)
    if not force and up == fireUp and y == fireY then return end
    fireUp, fireY = up, y
    if type(section) ~= "table" or type(section.SetFire) ~= "function" then return end
    local ok, err = pcall(section.SetFire, up, y)
    if not ok then LogOnce("SetFire", "GunsightShamanShocks SetFire failed: " .. tostring(err)) end
end

local function LayoutScale()
    local L = FS.Layout
    if L and type(L.Scale) == "function" then
        local ok, s = pcall(L.Scale)
        if ok and type(s) == "number" then return s end
    end
    return 1
end

-------------------------------------------------------------------------------
-- The GunsightAreas module: build, seat, onShow, onHide
-------------------------------------------------------------------------------

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y
    lastRect = rect
    if mod then
        SeatAll()
        if section then Shocks("Seat", section, rect, LayoutScale()) end
    end
end

local function BuildModule(host)
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono and Theme.AddSliceTexture and Theme.ApplyNineSlice) then
        LogOnce("notheme", "Theme is missing, the Shaman module is not built")
        return nil
    end
    Totems = FS.ShamanTotems
    if not (Totems and Totems.Get and Totems.Subscribe) then
        LogOnce("nototems", "FS.ShamanTotems is missing, the Shaman module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightShaman", host)
    Seat(function()
        At(mod, "TOPLEFT", 0, 0)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        BuildGround()
        for slot, def in ipairs(POLES) do P[slot] = BuildPole(slot, def) end
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Shaman.frame, Shaman.parts = mod, P
    Shaman.zone = zoneParts
    section = Shocks("Build", mod)
    if type(section) ~= "table" then section = nil end
    if Totems.Start then Totems.Start() end
    for slot = 1, #POLES do PaintPole(P[slot], GetTime()) end
    return mod
end

local function OnAreaShown(area)
    if not mod then return end
    if not subscribed then
        subscribed = true
        Totems.Subscribe(OnChange)
    end
    local ok, err = pcall(Totems.Refresh)
    if not ok then LogOnce("refresh", err) end
    PaintAll(GetTime())
    Sync()
    if section then
        Shocks("OnShow", section)
        if fireUp ~= nil then PushFire(fireUp, fireY, true) end
    end
end

local function OnAreaHidden(area)
    if not mod then return end
    if subscribed then
        subscribed = false
        Totems.Unsubscribe(OnChange)
    end
    Sync()
    if section then Shocks("OnHide", section) end
end

local ok, result = pcall(Areas.RegisterModule, "class", {
    classes = { "SHAMAN" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not ok or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
