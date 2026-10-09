-- Forever STUwave: Gunsight Target debuffs modules, Horizontal ("debuffsH") and Vertical ("debuffsV").
-- Both draw FS.TargetDebuffs inside one target side area (mockups/gunsight-modules-concepts-v7-2026-10-08.html,
-- dotsH and dotsV): rows of icon, time and drain bar, or the 0 to 30 s axis compressed to 112 px with a chip per debuff.
-- gunsightdots-harness.py parses the mockup for the numbers below, so a mockup edit fails there instead of drifting.
--
-- ABSENT CUE (Parker, 2026-10-03): the dim recast row or chip shows ONLY in combat; out of combat it is hidden and a
-- live one is never touched. "In combat" is a file-local flag driven by PLAYER_REGEN_DISABLED / PLAYER_REGEN_ENABLED
-- and seeded from InCombatLockdown() OR UnitAffectingCombat(), because lockdown can still read false inside the
-- REGEN_DISABLED dispatch; a throwing or secret answer reads as in combat so the cue is never hidden on a guess.
-- A list push that finds both APIs plainly false clears a stuck flag (a missed REGEN_ENABLED), and never sets it.
--
-- MOTION: one OnUpdate per module, installed only while a row is live, places everything from expires - GetTime()
-- and allocates nothing. A row that runs out turns absent by itself, since the service pushes nothing at an expiry.
--
-- CHIP: a dark plate, the icon seated inside the cut by FrameHelpers.SeatAuraTile, the cut ring over it (violet,
-- amber inside the 3 s band), and a white pop for 0.35 s when the debuff is (re)applied. Masks do not clip on this
-- client, so the icon is inset like every other tile. The target gate belongs to GunsightAreas, not to this file.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.ui and Gunsight.Point) then return end

FS.GunsightDots = FS.GunsightDots or {}
local Dots = FS.GunsightDots

local G = Gunsight.G
local ui, Point = Gunsight.ui, Gunsight.Point
local CX, CY = G.CX, G.CY

-------------------------------------------------------------------------------
-- Constants (mockup names in the comments; gunsightdots-harness.py re-reads them from the v7 mockup)
-------------------------------------------------------------------------------

local K = {
    violet = { 168 / 255, 85 / 255, 247 / 255 },    -- #a855f7
    amber = { 255 / 255, 182 / 255, 72 / 255 },     -- #ffb648
    fg = { 233 / 255, 226 / 255, 255 / 255 },       -- #e9e2ff
    muted = { 157 / 255, 147 / 255, 196 / 255 },    -- #9d93c4
    white = { 243 / 255, 251 / 255, 255 / 255 },    -- #f3fbff
}

-- Shared by both views. The default rect is the upper area, used until seat() hands over the real one.
local D = {
    MAX_S = 30,                -- the drain and the axis run 0 to 30 s
    BAND_S = 3,                -- amber at 3 s or less
    POP_S = 0.35, POP_A = 0.8, -- pop: 0.35 s, white at .8 fading out
    COLORS = K,
    RECT = { x = 1213, y = 500, w = 202, h = 128 },
}

-- Horizontal rows (dotsH). Offsets are from the area rect; the upper area starts its rows 8 px down, the lower 2 px up.
local H = {
    PITCH = 24.4,                       -- PITCH = (TBOT - TOP) / 10
    MAX_ROWS = 5,
    TOP_UPPER = 8, TOP_LOWER = -2,      -- TOP - 500, HZ - 632
    CHIP = 20, CHIP_DX = 7,             -- chipIcon(1220, cy - 10, 20)
    TIME_DX = 33, TIME_SIZE = 13,       -- txt(1246, cy + 4.5, ..., 13)
    TENTHS_S = 3,                       -- d.rem < 3 shows tenths
    BAR_DX = 61, BAR_W = 52, BAR_H = 4, -- rect(1274, cy - 2, 52, 4)
    BAR_BG_A = 0.2, ABSENT_BAR_A = 0.18, ABSENT_TEXT_A = 0.7,
    STACK_DX = 119, STACK_SIZE = 11,    -- txt(1332, cy + 4, 'x' + n, 11)
    SEP_W = 131, SEP_A = 0.12, SEP_HZ_A = 0.55,   -- line(1213, ty, 1344, ty)
    TICK_DX = -9, TICK_A = 0.45,        -- line(1204, ty, 1213, ty)
}

-- Vertical axis (dotsV): the DoT time axis compressed into one area, 3.7 px a second.
local V = {
    LANES = 4,
    AXT_DY = 4, AXB_DY = 116,           -- AXT = 504, AXB = 616 for the area at y 500
    SPAN = 112,                         -- AXB - AXT
    AX_DX = 7, END_DX = 155,            -- AX = 1220 (26 px right of the target cast bar), END = 1368
    LANE_DX = { 51, 80, 109, 138 },     -- LANE - 19
    AX_UP = 4, AX_DN = 4,               -- axis runs AXT - 4 to AXB + 4
    HDR_DX = 171, HDR_DY = -3, HDR_SIZE = 10, HDR_ALPHA = 0.9,   -- the TARGET DEBUFFS header; GunsightClass reads these two
    MAJ = 5, MAJ_LEN = 10, MIN_LEN = 5, -- a long tick and a label every 5 s
    LABEL_DX = 14, LABEL_SIZE = 11,
    REFRESH_DX = 13, REFRESH_SIZE = 9,
    BAND_FILL = 0.16, GUIDE_A = 0.3,
    GUIDE_DASH = { 2, 6 }, BAND_DASH = { 5, 4 },
    CHIP = 24,
}
V.PX_PER_S = V.SPAN / D.MAX_S

Dots.D, Dots.H, Dots.V = D, H, V

local LINE = G.LINE or 1.3
local RAIL_CORE, RAIL_GLOW, DOT_BLOOM = 2.6, 7, 9
local REAPPLY_EPS = 0.5                -- an expiry this much later than the last one is a reapply
local FRESH_EPS = 0.5                  -- on a new target, a row this close to its full duration was applied just now
local GLOW_BASE, GLOW_BAND = 0.25, 0.45
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local GLOW_ROUND = MEDIA .. "glow_round.tga"

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end
local ABSENT_RING = Mix(K.muted, { 1, 1, 1 }, 0.25)
local BAR_COLOR = Mix(K.violet, { 1, 1, 1 }, 0.25)
local WARM_PLATE = { 1, 0.88, 0.7 }
local PLAIN_PLATE = { 1, 1, 1 }

-------------------------------------------------------------------------------
-- State shared by both modules
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightdots_" .. key,
            "|cffff4488Forever STUwave|r: gunsight debuffs: " .. tostring(msg))
    end
end

-- A plain finite number or nil: a secret, a string or a NaN reads as unknown.
local function Num(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v then return nil end
    return v
end

local function PlainString(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "string" then return nil end
    return v
end

local modules = {}             -- id -> module, in build order (iterate with pairs: two entries)
local inCombat = true          -- placeholder: SeedCombat runs before any paint
local sharedBuilt = false

local function ReadCombat(fn, ...)
    local ok, r = pcall(fn, ...)
    if not ok or (FS.IsSecret and FS.IsSecret(r)) then return nil end
    return r and true or false
end

-- Out of combat only when BOTH APIs plainly answer false.
local function SeedCombat()
    local lock = ReadCombat(InCombatLockdown)
    local aff = ReadCombat(UnitAffectingCombat, "player")
    inCombat = not (lock == false and aff == false)
end

local function SetRowShown(row, on)
    if row.frame:IsShown() ~= on then row.frame:SetShown(on) end
end

local function SyncAbsent()
    for _, m in pairs(modules) do
        for i = 1, #m.rows do
            if m.rows[i].mode == "absent" then SetRowShown(m.rows[i], inCombat) end
        end
    end
end

local function HealCombat()
    if not inCombat then return end
    SeedCombat()
    if not inCombat then SyncAbsent() end
end

-------------------------------------------------------------------------------
-- Time text, built once so a steady frame allocates nothing
-------------------------------------------------------------------------------

local TENTHS, SECONDS, MINUTES = {}, {}, {}
for i = 0, D.MAX_S do TENTHS[i] = string.format("%.1fs", i / 10) end
for i = 0, 99 do SECONDS[i] = i .. "s" end
for i = 1, 60 do MINUTES[i] = i .. "m" end

local function FormatTime(rem)
    if rem < H.TENTHS_S then return TENTHS[math.floor(rem * 10 + 0.5)] end
    if rem < 99.5 then return SECONDS[math.floor(rem + 0.5)] end
    local m = math.floor(rem / 60 + 0.5)
    if m > 60 then m = 60 end
    return MINUTES[m]
end

-------------------------------------------------------------------------------
-- Module plumbing
-------------------------------------------------------------------------------

local function NewModule(id, kind)
    return { id = id, kind = kind, rows = {}, seats = {}, src = {}, rect = { x = D.RECT.x, y = D.RECT.y, w = D.RECT.w, h = D.RECT.h },
        parts = {} }
end

local function Seat(m, fn)
    m.seats[#m.seats + 1] = fn
    fn()
end

local function SeatAll(m)
    for i = 1, #m.seats do
        local ok, err = pcall(m.seats[i])
        if not ok then LogOnce("seat", err) end
    end
end

local function Tex(m, layer, sub)
    return m.body:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
end

local function Label(m, parent, size, c, a)
    local fs = (parent or m.body):CreateFontString(nil, "ARTWORK")
    fs:SetJustifyH("LEFT")
    Seat(m, function() FS.Theme.ApplyMono(fs, ui(size), { c[1], c[2], c[3], a }) end)
    return fs
end

-------------------------------------------------------------------------------
-- Chip (shared look)
-------------------------------------------------------------------------------

local function Gradient(tex, c, aBottom, aTop)
    if tex.SetGradient and CreateColor then
        tex:SetColorTexture(1, 1, 1, 1)
        tex:SetGradient("VERTICAL", CreateColor(c[1], c[2], c[3], aBottom), CreateColor(c[1], c[2], c[3], aTop))
    else
        tex:SetColorTexture(c[1], c[2], c[3], aTop)
    end
end

local function Desaturate(tex, on)
    if tex.SetDesaturated then
        tex:SetDesaturated(on)
        tex:SetVertexColor(1, 1, 1, 1)
    elseif on then
        tex:SetVertexColor(0.55, 0.55, 0.55, 1)
    else
        tex:SetVertexColor(1, 1, 1, 1)
    end
end

local function HidePop(chip)
    chip.popAt = nil
    chip.pop:Hide()
end

-- A chip's tooltip shows only while the Gunsight is the display: in combat a switched-off HUD only fades, and its hidden chips
-- would still answer a hover.
local function TipGate() return Gunsight.IsActive() end

local function BuildChip(m, parent, size, level)
    local Theme, FH = FS.Theme, FS.FrameHelpers
    local chip = {}
    local f = CreateFrame("Frame", nil, parent)
    f:SetFrameLevel(level)
    f:EnableMouse(false)
    -- Hover only (clicks pass through the centre HUD); the spell comes from UpdateRow.
    if FH and FH.AttachSpellTooltip then FH.AttachSpellTooltip(f, { gate = TipGate }) end
    f:SetSize(ui(size), ui(size))          -- sized first: the chamfer comes from the height
    local icon = f:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(f)
    f.icon = icon
    Theme.SkinButton(f, { borderColor = K.violet })
    local seat = FH and (FH.SeatAuraTile or FH.SeatCutIcon)
    if seat then seat(f) else LogOnce("noseat", "FrameHelpers.SeatAuraTile is missing, the icon is not seated inside the cut") end
    chip.frame, chip.plate = f, f.fsAuraPlate

    local c = (f.fsSkin and f.fsSkin.chamfer) or 6
    local path = c == 6 and Theme.SLICE_CUT2_FILL_TEXTURE or (MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
    chip.pop = Theme.AddSliceTexture(f, path, { K.white[1], K.white[2], K.white[3], 0 }, "OVERLAY", 2)
    Theme.ApplyNineSlice(chip.pop, c)
    chip.pop:Hide()

    -- the abbreviation shows only when the spell has no icon
    chip.label = f:CreateFontString(nil, "OVERLAY")
    chip.label:SetPoint("CENTER", f, "CENTER", 0, 0)
    chip.label:Hide()
    Seat(m, function()
        f:SetSize(ui(size), ui(size))
        Theme.ApplyMono(chip.label, ui(size * 0.52), { 1, 1, 1, 1 })
    end)
    return chip
end

-- The chip's static look for a row mode ("absent", "live" or "unknown") and the band.
local function ChipLook(chip, mode, band)
    local f, skin = chip.frame, chip.frame.fsSkin
    if mode == "absent" then
        Desaturate(f.icon, true)
        f.icon:SetAlpha(0.5)
        if chip.plate then chip.plate:SetAlpha(0.7); chip.plate:SetVertexColor(1, 1, 1, 1) end
        skin.border.ring:SetVertexColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0.9)
        skin.glow:SetVertexColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0)
        chip.label:SetTextColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0.9)
        HidePop(chip)
        return
    end
    local c = band and K.amber or K.violet
    Desaturate(f.icon, false)
    f.icon:SetAlpha(1)
    if chip.plate then
        local p = band and WARM_PLATE or PLAIN_PLATE
        chip.plate:SetAlpha(1)
        chip.plate:SetVertexColor(p[1], p[2], p[3], 1)
    end
    skin.border.ring:SetVertexColor(c[1], c[2], c[3], 1)
    skin.glow:SetVertexColor(c[1], c[2], c[3], band and GLOW_BAND or GLOW_BASE)
    local t = band and K.amber or K.white
    chip.label:SetTextColor(t[1], t[2], t[3], 1)
end

local function SetChipIcon(chip, e)
    local icon = e.icon
    if icon ~= nil and not (FS.IsSecret and FS.IsSecret(icon)) and (type(icon) == "number" or type(icon) == "string") then
        chip.frame.icon:SetTexture(icon)
        chip.frame.icon:Show()
        chip.label:Hide()
    else
        chip.frame.icon:Hide()
        chip.label:SetText(string.upper(string.sub(PlainString(e.name) or "?", 1, 2)))
        chip.label:Show()
    end
end

-- The pop flashes, then fades by itself from Step.
local function StartPop(chip, now)
    chip.popAt = now
    chip.pop:SetVertexColor(K.white[1], K.white[2], K.white[3], D.POP_A)
    chip.pop:Show()
end

local function StepPop(chip, now)
    if not chip.popAt then return end
    local age = now - chip.popAt
    if age >= D.POP_S then
        HidePop(chip)
    else
        chip.pop:SetVertexColor(K.white[1], K.white[2], K.white[3], D.POP_A * (1 - age / D.POP_S))
    end
end

local function PulseGlow(chip, now)
    local c = K.amber
    local pl = 0.5 + 0.5 * math.sin(now * 9)
    chip.frame.fsSkin.glow:SetVertexColor(c[1], c[2], c[3], math.min(1, GLOW_BAND * (0.55 + 0.6 * pl)))
end

-------------------------------------------------------------------------------
-- Horizontal rows
-------------------------------------------------------------------------------

local function RowTop(m) return m.rect.y + (m.rect.y >= CY and H.TOP_LOWER or H.TOP_UPPER) end

-- The text, bar and chip colours of one row for its mode and band.
local function LookH(row)
    local mode, band = row.mode, row.band
    if mode == "off" then return end
    ChipLook(row.chip, mode, band)
    local bg, fg, tc, ta = BAR_COLOR, BAR_COLOR, K.white, 1
    if mode == "absent" then
        bg, tc, ta = K.muted, K.muted, H.ABSENT_TEXT_A
        row.fillTex:Hide()
        row.barBg:SetColorTexture(bg[1], bg[2], bg[3], H.ABSENT_BAR_A)
        row.barBg:Show()
    else
        if band then bg, fg, tc = K.amber, K.amber, K.amber end
        if mode == "unknown" then tc = K.fg end
        row.barBg:SetColorTexture(bg[1], bg[2], bg[3], H.BAR_BG_A)
        row.fillTex:SetColorTexture(fg[1], fg[2], fg[3], 1)
        row.fillTex:SetShown(mode == "live")
        row.barBg:SetShown(mode == "live")
    end
    row.time:SetTextColor(tc[1], tc[2], tc[3], ta)
    if mode == "live" or mode == "unknown" then
        row.stack:SetTextColor(K.white[1], K.white[2], K.white[3], 1)
    end
end

local function SetTime(row, s)
    if row.timeText ~= s then
        row.timeText = s
        row.time:SetText(s)
    end
end

-- Seats the time text and the drain fill for `rem` seconds left.
local function PaintH(row, rem)
    SetTime(row, FormatTime(rem))
    local w = H.BAR_W * math.min(rem, D.MAX_S) / D.MAX_S
    if not row.fill or math.abs(row.fill - w) >= 0.02 then
        row.fill = w
        row.fillTex:SetWidth(ui(w))
    end
end

-- An absent row reads "--" over its dim track; a row whose duration nobody knows reads "?" with no track at all
-- (an empty bar would claim a drained debuff).
local function ParkH(row)
    SetTime(row, row.mode == "unknown" and "?" or "--")
    row.fill = nil
end

local function BuildRowH(m, i)
    local rf = CreateFrame("Frame", nil, m.body)
    rf:SetFrameLevel(m.body:GetFrameLevel() + 1)
    rf:EnableMouse(false)
    local row = { index = i, mode = "off", frame = rf }
    row.chip = BuildChip(m, rf, H.CHIP, rf:GetFrameLevel() + 1)
    row.time = Label(m, rf, H.TIME_SIZE, K.white, 1)
    row.stack = Label(m, rf, H.STACK_SIZE, K.white, 1)
    row.barBg = rf:CreateTexture(nil, "ARTWORK", nil, 0)
    row.fillTex = rf:CreateTexture(nil, "ARTWORK", nil, 1)
    row.barBg:SetColorTexture(BAR_COLOR[1], BAR_COLOR[2], BAR_COLOR[3], H.BAR_BG_A)
    row.fillTex:SetColorTexture(BAR_COLOR[1], BAR_COLOR[2], BAR_COLOR[3], 1)
    row.time:SetText("--")
    row.stack:SetText("")
    rf:Hide()
    Seat(m, function()
        local x = m.rect.x
        local cy = RowTop(m) + H.PITCH * (i - 0.5)
        Point(row.chip.frame, "CENTER", x + H.CHIP_DX + H.CHIP / 2, cy)
        Point(row.time, "LEFT", x + H.TIME_DX, cy)
        Point(row.stack, "LEFT", x + H.STACK_DX, cy)
        Point(row.barBg, "LEFT", x + H.BAR_DX, cy)
        row.barBg:SetSize(ui(H.BAR_W), ui(H.BAR_H))
        Point(row.fillTex, "LEFT", x + H.BAR_DX, cy)
        row.fillTex:SetSize(ui(row.fill or 0), ui(H.BAR_H))
        if row.mode ~= "off" then LookH(row) end
    end)
    return row
end

local function BuildChromeH(m)
    -- the ruler: one faint rule per row bottom (plus the top of the upper area) and a pink tick before each
    local rules, ticks = {}, {}
    for j = 0, H.MAX_ROWS do
        local t = Tex(m, "BACKGROUND")
        rules[j] = t
        if j >= 1 then
            local k = Tex(m, "BACKGROUND")
            k:SetColorTexture(1, 0.18, 0.59, H.TICK_A)
            ticks[j] = k
        end
    end
    m.parts.rules, m.parts.ticks = rules, ticks
    Seat(m, function()
        local upper = m.rect.y < CY
        local top = RowTop(m)
        for j = 0, H.MAX_ROWS do
            local y = top + H.PITCH * j
            local t = rules[j]
            local a = (upper and j == H.MAX_ROWS) and H.SEP_HZ_A or H.SEP_A
            t:SetColorTexture(K.violet[1], K.violet[2], K.violet[3], a)
            t:SetShown(upper or j >= 1)
            Point(t, "LEFT", m.rect.x, y)
            t:SetSize(ui(H.SEP_W), ui(1))
            if ticks[j] then
                Point(ticks[j], "LEFT", m.rect.x + H.TICK_DX, y)
                ticks[j]:SetSize(ui(-H.TICK_DX), ui(1))
            end
        end
    end)
end

-------------------------------------------------------------------------------
-- Vertical axis
-------------------------------------------------------------------------------

local function AxisBottom(m) return m.rect.y + V.AXB_DY end

local function SecY(m, s)
    return AxisBottom(m) - math.min(math.max(s, 0), D.MAX_S) * V.PX_PER_S
end

-- A static line whose position is relative to the area rect: x0, x1 and y are offsets.
local function RelH(m, y, x0, x1, c, a, th, layer, sub)
    local t = Tex(m, layer, sub)
    t:SetColorTexture(c[1], c[2], c[3], a)
    Seat(m, function()
        Point(t, "LEFT", m.rect.x + x0, m.rect.y + y)
        t:SetSize(ui(x1 - x0), ui(th))
    end)
    return t
end

local function RelV(m, x, y0, y1, c, a, th, layer, sub)
    local t = Tex(m, layer, sub)
    t:SetColorTexture(c[1], c[2], c[3], a)
    Seat(m, function()
        Point(t, "TOP", m.rect.x + x, m.rect.y + y0)
        t:SetSize(ui(th), ui(y1 - y0))
    end)
    return t
end

local function RelLabel(m, text, size, c, a, anchor, x, y)
    local fs = Label(m, nil, size, c, a)
    Seat(m, function() Point(fs, anchor, m.rect.x + x, m.rect.y + y) end)
    fs:SetText(text)
    return fs
end

local function BuildScaleV(m)
    local P = m.parts
    local axt, axb = V.AXT_DY, V.AXB_DY
    local function dy(s) return axb - s * V.PX_PER_S end
    local yb = dy(D.BAND_S)
    local ax, e = V.AX_DX, V.END_DX

    local band = Tex(m, "BACKGROUND")
    band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], V.BAND_FILL)
    Seat(m, function()
        Point(band, "TOPLEFT", m.rect.x + ax, m.rect.y + yb)
        band:SetSize(ui(e - ax), ui(axb - yb))
    end)
    P.band = band
    P.bandTop = {}
    local x = ax
    while x < e - 1e-6 do
        P.bandTop[#P.bandTop + 1] = RelH(m, yb, x, math.min(e, x + V.BAND_DASH[1]), K.amber, 0.75, LINE)
        x = x + V.BAND_DASH[1] + V.BAND_DASH[2]
    end
    P.bandBottom = RelH(m, axb, ax, e, K.amber, 0.95, LINE * 1.3)

    -- the REFRESH label runs bottom to top in the mockup; Lua cannot rotate text, so it is stacked upright letters
    P.refresh = {}
    local word, pitch = "REFRESH", 6.5
    for i = 1, #word do
        P.refresh[i] = RelLabel(m, word:sub(i, i), V.REFRESH_SIZE, K.amber, 0.8, "CENTER", e + V.REFRESH_DX,
            (yb + axb) / 2 + (i - (#word + 1) / 2) * pitch)
    end

    P.guides = {}
    for lane = 1, V.LANES do
        P.guides[lane] = {}
        local y = axt
        while y < axb - 1e-6 do
            P.guides[lane][#P.guides[lane] + 1] = RelV(m, V.LANE_DX[lane], y, math.min(axb, y + V.GUIDE_DASH[1]), K.violet, V.GUIDE_A, LINE)
            y = y + V.GUIDE_DASH[1] + V.GUIDE_DASH[2]
        end
    end

    P.axis = RelV(m, ax, axt - V.AX_UP, axb + V.AX_DN, K.violet, 0.85, LINE)
    P.ticks, P.labels = {}, {}
    for s = 0, D.MAX_S do
        local maj = s % V.MAJ == 0
        local len = maj and V.MAJ_LEN or V.MIN_LEN
        P.ticks[s + 1] = RelH(m, dy(s), ax, ax + len, K.violet, maj and 0.7 or 0.45, LINE)
        if maj then P.labels[s] = RelLabel(m, tostring(s), V.LABEL_SIZE, K.fg, 0.9, "LEFT", ax + V.LABEL_DX, dy(s)) end
    end

    local hdr = Label(m, nil, V.HDR_SIZE, K.violet, V.HDR_ALPHA)
    hdr:SetJustifyH("RIGHT")
    Seat(m, function() Point(hdr, "BOTTOMRIGHT", m.rect.x + V.HDR_DX, m.rect.y + V.HDR_DY + 2.5) end)
    hdr:SetText("TARGET DEBUFFS")
    P.header = hdr
end

-- Seats the chip, its rail and the rail's end dot for `rem` seconds left (0 = resting at 0).
local function PlaceV(m, row, rem)
    local y = SecY(m, rem)
    if row.y and math.abs(row.y - y) < 0.02 then return end
    row.y = y
    local k = ui(1)
    local dx = (row.x - CX) * k
    row.frame:SetPoint("CENTER", Gunsight.root, "CENTER", dx, -(y - CY) * k)
    if row.mode ~= "live" then return end
    -- the rail runs from the chip's lower edge down to 0; inside the last 1.5 s the chip already covers it
    local axb = AxisBottom(m)
    local yt = math.min(axb, y + V.CHIP / 2)
    row.dot:SetPoint("CENTER", Gunsight.root, "CENTER", dx, -(yt - CY) * k)
    row.dot:Show()
    if axb - yt > 0.5 then
        row.rail:SetHeight((axb - yt) * k)
        row.railGlow:SetHeight((axb - yt) * k)
        row.rail:Show(); row.railGlow:Show()
    else
        row.rail:Hide(); row.railGlow:Hide()
    end
end

local function HideRail(row)
    row.rail:Hide(); row.railGlow:Hide(); row.dot:Hide()
end

local function SetRailColor(row, name)
    if row.railColor == name then return end
    row.railColor = name
    local c = name == "amber" and K.amber or K.violet
    Gradient(row.rail, c, 0.35, 1)
    Gradient(row.railGlow, c, 0.35 * 0.22, 0.22)
    local w = Mix(c, { 1, 1, 1 }, 0.5)
    row.dot:SetVertexColor(w[1], w[2], w[3], 1)
end

local function LookV(row)
    local mode = row.mode
    if mode == "off" then return end
    ChipLook(row.chip, mode, row.band)
    if mode == "absent" then
        HideRail(row)
        row.railColor = nil
    else
        SetRailColor(row, row.band and "amber" or "violet")
    end
end

local function BuildRowV(m, i)
    local chip = BuildChip(m, m.body, V.CHIP, m.body:GetFrameLevel() + 2)
    local row = { index = i, mode = "off", frame = chip.frame, chip = chip }
    chip.frame:Hide()
    row.railGlow = Tex(m, "ARTWORK", 1)
    row.rail = Tex(m, "ARTWORK", 2)
    row.dot = Tex(m, "ARTWORK", 3)
    row.dot:SetTexture(GLOW_ROUND)
    row.dot:SetBlendMode("ADD")
    HideRail(row)
    Seat(m, function()
        row.x = m.rect.x + V.LANE_DX[i]
        row.rail:SetWidth(ui(RAIL_CORE))
        row.railGlow:SetWidth(ui(RAIL_GLOW))
        row.dot:SetSize(ui(DOT_BLOOM), ui(DOT_BLOOM))
        Point(row.rail, "BOTTOM", row.x, AxisBottom(m))
        Point(row.railGlow, "BOTTOM", row.x, AxisBottom(m))
        row.y = nil
        if row.mode == "live" then
            PlaceV(m, row, row.expires - GetTime())
        elseif row.mode == "absent" then
            PlaceV(m, row, 0)
        end
    end)
    return row
end

-------------------------------------------------------------------------------
-- Motion
-------------------------------------------------------------------------------

local function StopTicking(m)
    if m.ticking then
        m.ticking = false
        m.frame:SetScript("OnUpdate", nil)
    end
end

local function StartTicking(m)
    if not m.ticking and m.active then
        m.ticking = true
        m.frame:SetScript("OnUpdate", m.step)
    end
end

local function ToAbsent(m, row)
    row.mode, row.expires, row.band = "absent", nil, false
    if m.kind == "H" then
        ParkH(row)
        LookH(row)
    else
        LookV(row)
        row.y = nil
        PlaceV(m, row, 0)
    end
    SetRowShown(row, inCombat)
end

local function StepRow(m, row, now)
    local rem = row.expires - now
    if rem <= 0 then
        ToAbsent(m, row)
        return false
    end
    local band = rem <= D.BAND_S
    if band ~= row.band then
        row.band = band
        if m.kind == "H" then LookH(row) else LookV(row) end
    end
    if m.kind == "H" then PaintH(row, rem) else PlaceV(m, row, rem) end
    if band then PulseGlow(row.chip, now) end
    StepPop(row.chip, now)
    return true
end

local function MakeStep(m)
    return function()
        local now = GetTime()
        local live = 0
        for i = 1, #m.rows do
            local row = m.rows[i]
            if row.mode == "live" and StepRow(m, row, now) then live = live + 1 end
        end
        if live == 0 then StopTicking(m) end
    end
end

-------------------------------------------------------------------------------
-- List to rows
-------------------------------------------------------------------------------

local function ClearRow(m, row)
    row.mode, row.key, row.iconId, row.expires, row.band, row.count = "off", nil, nil, nil, false, nil
    row.fill, row.timeText = nil, nil
    HidePop(row.chip)
    if m.kind == "V" then HideRail(row); row.railColor = nil end
    row.frame:Hide()
end

-- One entry into one row. A nil entry is an unused row.
local function UpdateRow(m, row, e, now, newTarget)
    if not e then
        if row.mode ~= "off" then ClearRow(m, row) end
        return
    end
    local name = PlainString(e.name)
    if not name then
        if row.mode ~= "off" then ClearRow(m, row) end
        return
    end
    local prevMode, prevExpires = row.mode, row.expires
    if row.key ~= name then
        prevMode, prevExpires = "off", nil
        HidePop(row.chip)                -- a flash belongs to the debuff that earned it
    end
    if row.key ~= name or row.iconId ~= e.icon then
        row.key, row.iconId = name, e.icon
        SetChipIcon(row.chip, e)
    end
    -- Every push, not only on a new debuff: the id is a plain number or nothing (a secret falls back to the name).
    if FS.FrameHelpers and FS.FrameHelpers.SetTipSpell then FS.FrameHelpers.SetTipSpell(row.chip.frame, e.id, name) end

    local raw = e.expires
    local mode, expires
    if FS.IsSecret and FS.IsSecret(raw) then
        mode = "off"
    elseif raw == nil then
        mode = "unknown"
    else
        expires = Num(raw)
        if not expires then mode = "off" elseif expires > now then mode = "live" else mode = "absent" end
    end
    if mode == "off" then
        if row.mode ~= "off" then ClearRow(m, row) end
        return
    end

    row.mode, row.expires = mode, expires
    row.band = mode == "live" and expires - now <= D.BAND_S
    if mode == "live" then
        if newTarget then
            local duration = Num(e.duration)
            if duration and expires - now >= duration - FRESH_EPS then
                StartPop(row.chip, now)                  -- applied within the last half second: a genuine apply
            else
                HidePop(row.chip)                        -- the old target's flash does not follow the switch
            end
        elseif prevMode == "absent" or (prevMode == "live" and expires > prevExpires + REAPPLY_EPS) then
            StartPop(row.chip, now)
        end
    else
        HidePop(row.chip)
    end

    if m.kind == "H" then
        local count = Num(e.count) or 1
        if row.count ~= count then
            row.count = count
            row.stack:SetText(count > 1 and ("x" .. count) or "")
        end
        LookH(row)
        if mode == "live" then
            row.fill, row.timeText = nil, nil
            PaintH(row, expires - now)
        else
            ParkH(row)
        end
    else
        LookV(row)
        row.y = nil
        PlaceV(m, row, mode == "live" and expires - now or 0)
    end
    SetRowShown(row, mode ~= "absent" or inCombat)
end

-- The vertical axis cannot place an entry with no expiry, so those are skipped.
local function KnownExpiry(e)
    local raw = type(e) == "table" and e.expires
    if raw == nil or raw == false then return false end
    if FS.IsSecret and FS.IsSecret(raw) then return false end
    return true
end

local function Gather(m, list)
    local src, n = m.src, 0
    for i = 1, #list do
        local e = list[i]
        if n < #m.rows and type(e) == "table" and (m.kind == "H" or KnownExpiry(e)) then
            n = n + 1
            src[n] = e
        end
    end
    for i = n + 1, #src do src[i] = nil end
end

local function DropRow(m, row)
    row.mode, row.key, row.iconId, row.expires = "off", nil, nil, nil
    pcall(row.frame.Hide, row.frame)
end

local function Update(m, list, epoch)
    HealCombat()
    local newTarget = epoch ~= m.lastEpoch
    m.lastEpoch = epoch
    Gather(m, type(list) == "table" and list or {})
    local now = GetTime()
    local used, live = 0, false
    for i = 1, #m.rows do
        local row = m.rows[i]
        local ok, err = pcall(UpdateRow, m, row, m.src[i], now, newTarget)
        if not ok then
            LogOnce("state", err)
            DropRow(m, row)
        end
        if row.mode ~= "off" then used = used + 1 end
        if row.mode == "live" then live = true end
    end
    m.body:SetShown(used > 0)
    if live then StartTicking(m) else StopTicking(m) end
end

-------------------------------------------------------------------------------
-- Module build and hooks
-------------------------------------------------------------------------------

local function EnsureShared()
    if sharedBuilt then return end
    sharedBuilt = true
    SeedCombat()
    local events = CreateFrame("Frame", nil, Gunsight.root)
    events:RegisterEvent("PLAYER_REGEN_DISABLED")     -- the absent cue shows only in combat
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_REGEN_DISABLED" then
            inCombat = true                 -- the event itself: InCombatLockdown() may still read false here
        elseif event == "PLAYER_REGEN_ENABLED" then
            inCombat = false
        else
            SeedCombat()
        end
        SyncAbsent()
    end)
end

local function BuildModule(m, host)
    local Theme, FH = FS.Theme, FS.FrameHelpers
    if not (Theme and Theme.SkinButton and Theme.ApplyMono and Theme.AddSliceTexture and Theme.ApplyNineSlice and FH) then
        error("Theme or FrameHelpers is missing")
    end
    EnsureShared()
    m.frame = CreateFrame("Frame", m.kind == "H" and "ForeverSTUwaveGunsightDebuffsH" or "ForeverSTUwaveGunsightDebuffsV", host)
    m.frame:SetSize(1, 1)
    m.frame:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    m.body = CreateFrame("Frame", nil, m.frame)
    m.body:SetSize(1, 1)
    m.body:SetPoint("CENTER", m.frame, "CENTER", 0, 0)
    m.body:Hide()                                    -- shown once a list has a row
    if m.kind == "H" then
        BuildChromeH(m)
        for i = 1, H.MAX_ROWS do m.rows[i] = BuildRowH(m, i) end
    else
        BuildScaleV(m)
        for i = 1, V.LANES do m.rows[i] = BuildRowV(m, i) end
    end
    m.step = MakeStep(m)
    m.built = true
    modules[m.id] = m
    return m.frame
end

local function ModuleSpec(m)
    return {
        build = function(host) return BuildModule(m, host) end,
        seat = function(rect)
            m.rect.x, m.rect.y, m.rect.w, m.rect.h = rect.x, rect.y, rect.w, rect.h
            SeatAll(m)
        end,
        onShow = function(area)
            m.active, m.area = true, area
            local TD = FS.TargetDebuffs
            if not (TD and TD.Subscribe) then
                LogOnce("nodata", "FS.TargetDebuffs is missing, the target debuffs have no data")
                return
            end
            if not m.subscribed then
                m.subscribed = true
                TD.Subscribe(m.onList)             -- pushes the current list at once
            end
        end,
        onHide = function()
            m.active, m.area = false, nil
            if m.subscribed and FS.TargetDebuffs then FS.TargetDebuffs.Unsubscribe(m.onList) end
            m.subscribed = false
            m.lastEpoch = nil
            StopTicking(m)
            for i = 1, #m.rows do ClearRow(m, m.rows[i]) end
            m.body:Hide()
        end,
    }
end

local function Register(id, kind)
    local m = NewModule(id, kind)
    m.onList = function(list, epoch)
        if not m.active then return end
        local ok, err = pcall(Update, m, list, epoch)
        if not ok then LogOnce("state", err) end
    end
    Dots.modules = Dots.modules or {}
    Dots.modules[id] = m
    return FS.GunsightAreas.RegisterModule(id, ModuleSpec(m))
end

if FS.GunsightAreas and FS.GunsightAreas.RegisterModule then
    local okH = Register("debuffsH", "H")
    local okV = Register("debuffsV", "V")
    Dots.registered = okH and okV and true or false
end
