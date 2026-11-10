-- Forever STUwave: Gunsight Class Module for the Priest: the shield and Prayer of Mending
--
-- The approved design is the design mockup "Priest shield and mending" (2026-11-07), palette BIFROST FROST, rune C, no halo.
-- Two watchers side by side on the mockup's 150 x 86 sprite px canvas:
--   * THE SHIELD (left): a round Viking shield (2 px rim, iron band with 8 rivets, planks in ice cyan / teal quarters, a
--     midnight blue boss carrying the protection rune). It watches the friendly target, else the player (an enemy never carries
--     our shield). The absorb left is LIGHT filling the shield from the bottom: a vertical StatusBar the engine fills from the
--     secret UnitGetTotalAbsorbs, its max the absorb caught right after the player's own cast (PriestShields' mark). While it
--     holds light: an ice rim, the rune burning white, a frost aura and 8 rays breathing, a glint sweep and rising motes; a hit
--     flashes it white and shakes it 1 px. The RIM says if you may shield again: violet and draining while Weakened Soul runs
--     (15 s), dim teal while the 4 s cooldown runs, ice cyan when clear. Empty and clear: a still GHOST out of combat (the off
--     state mockup, 2026-11-10, option C: a faint wash the ground shows through, thin rings for the band and the boss, rivet
--     dots, a solid thin rim, the rune in ice cyan), an amber dashed pulse with a glow in combat ("shield them"). Not learned:
--     a dotted rim and L6. The label under it is the absorb left (AbbreviateNumbers) or the Weakened Soul time in violet.
--   * PRAYER OF MENDING (right): 5 beads on an arc round a 2x heart (lit = heals left), a 5 seat party strip (seat 1 is the
--     player, then party1-4; class colour strip, a "you" tick), the holder's seat framed gold with a small heart, a spark when a
--     plain read sees it jump, the 30 s jump timer bar and its label, the heart shaded from the top while the 10 s cooldown
--     runs, L40 before it is learned. The seats also carry the player's OTHER shields: frost light filling the seat from the
--     bottom (that member's absorb, engine drawn) and a violet line draining along its top (their Weakened Soul from our cast).
--
-- HOW "THERE IS LIGHT IN IT" IS DRAWN WITHOUT READING A SECRET. The absorb can never be compared, so everything that only shows
-- while the shield holds light (the ice rim, the white rune, aura, rays, glint, motes, flash, the number) sits in one plain frame
-- whose ALPHA is the secret absorb (SetAlpha takes a secret; 0 hides it, any absorb shows it fully). That frame is layered over
-- the empty looks (ghost or dashed rim, state rune) and under the cooldown and Weakened Soul rims, so the engine picks the right rim and
-- rune. The plain "up" guess (PriestShields: aura out of combat, the cast ledger in combat) only chooses the label and whether
-- the empty look may nudge.
--
-- WHAT THE MOCKUP HAS THAT THIS BUILD DOES NOT (the client cannot do it, or not without per frame geometry):
--   * the bright top rows that ride the light's edge (the fill level is secret; the lit texture carries them at full only);
--   * the Weakened Soul rim drains from the other end: a Cooldown swipe keeps the arc from where the elapsed time ends to 12
--     o'clock, the mockup keeps it from 12 o'clock on; and its bright head pixel is gone;
--   * break shards only for a break a plain read sees (out of combat); in combat a break is not knowable;
--   * the seat light has no bright top rows either (a flat frost fill);
--   * the label is the house mono font, not the mockup's 3 x 5 pixel font ("~6s", not "~6S").
--
-- DATA. Everything comes from FS.PriestShields (PriestShields.lua); its ledger listens from Start() on and never stops. This
-- file reads no aura and compares no secret: secrets go straight to SetMinMaxValues / SetValue / SetAlpha / AbbreviateNumbers.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide
-- stops the OnUpdate and the subscription; onShow subscribes, refreshes and repaints. Plain frames only.
--
-- TICKER. One OnUpdate at most every C.TICK s while shown and something moves (light, a clock, a nudge, a hit, a jump); it
-- stops when nothing does. The tick allocates nothing: positions are numbers, texcoords and labels are written on change.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightPriest = FS.GunsightPriest or {}
local Priest = FS.GunsightPriest

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil, sin, cos, pi = math.floor, math.ceil, math.sin, math.cos, math.pi
local IsSecret = FS.IsSecret or function() return false end

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    LABEL_Y = 74,
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    SHIELD = { cx = 38, cy = 36, r = 27 },
    BOX = 64, CENTER = 32,             -- the shield art's sprite box and the shield centre in it (generate_priest_shield.py)
    RAYS_BOX = 80, RAYS_CENTER = 40,
    LIT = { x = -27, y = -26, w = 55, h = 53 },   -- the lit interior the StatusBar covers, sprite px from the shield centre
    PM = { cx = 114, cy = 27, r = 24, seatY = 47, seatX = { 88, 101, 114, 127, 140 } },
    BREATH = 2.6, NUDGE = 1.4, HEART_PULSE = 1.0,
    GLINT_EVERY = 3.2, GLINT_LEN = 0.6, GLINT_FRAMES = 8,
    MOTE_X = { -16, -6, 4, 13, 20 }, MOTE_SPEED = 0.35,
    FLASH = 0.08, SHAKE = 0.12, BREAK = 0.7, JUMP = 0.45,
    LABEL_SIZE = 11,
    CAP = 325 / 1024,                  -- Mononoki Bold: the line box's middle sits CAP * size above the baseline (as GunsightWarrior)
    TEXT_MAX_S = 99,
    ABSORB_EVERY = 0.5,                -- s between absorb re-reads while ticking (the pings are the main path)
    COLORS = {
        violet = Hex("#c04cff"), violetLabel = Hex("#e09cff"), amber = Hex("#ffb648"), muted = Hex("#9d93c4"),
        rimClear = Hex("#5fd4e8"), cdOuter = Hex("#2a5a6a"), runeLine = Hex("#061a2c"), white = Hex("#ffffff"),
        label = Hex("#c8faff"), shard = Hex("#a0f4ff"), aura = Hex("#a0f4ff"), litBody = Hex("#9ff0ff"),
        gold = Hex("#ffd36a"), goldLabel = Hex("#ffe9a8"), seatEdge = Hex("#3a2c5c"), seatBg = Hex("#120a22"),
        pink = Hex("#ff5d8f"), sparkCore = Hex("#ffc2d6"), you = Hex("#f3fbff"), barBg = Hex("#1c1230"),
        chainOut = Hex("#8a6a30"), chainOff = Hex("#2a1a44"),
    },
    SEAT_CLASS = { Hex("#f3fbff"), Hex("#c79c6e"), Hex("#ff7d0a"), Hex("#0070de"), Hex("#69ccf0") },   -- mockup fallbacks
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Priest.C = C
local K = C.COLORS

-- priest_shield.tga cells (generate_priest_shield.py SHIELD_CELLS) and priest_mending.tga cells (MENDING_CELLS)
local CELL = { dark = 0, rimClear = 1, rimCd = 2, rimWsDark = 3, rimDash = 4, rune = 5, runeLine = 6, flash = 7, aura = 8,
    halo = 9, ghost = 10, ghostRim = 11 }
local MCELL = { beadLit = 0, beadOff = 1, beadDash = 2, heartSmall = 3, heartLit = 4, heartOff = 5, heartAmber = 6,
    heartLocked = 7, heartGlow = 8 }
Priest.CELL, Priest.MCELL = CELL, MCELL
local SCALE = 2

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local HEART = { ".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..." }

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightpriest_" .. key, "|cffff4488Forever STUwave|r: gunsight priest module: " .. tostring(msg))
    end
end

local Data
local mod
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc, absorbAcc = false, false, 0, 0
local P = {}                       -- every part, built once
local hitAt, breakAt, castAt = nil, nil, nil
local abbreviateOff = false

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

-- sprite px -> UI units
local function S(v) return ui(v * C.SPX) end

-- Seat a region's top left at sprite (x, y) from its base frame's top left, only when it moved.
local function Place(t, x, y)
    if t.fsX == x and t.fsY == y then return end
    t.fsX, t.fsY = x, y
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", t.fsBase, "TOPLEFT", S(x), -S(y))
end

local function Forget(t) t.fsX, t.fsY = nil, nil end

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

-- A texture under `parent`, placed against `base` (the module frame unless given), w x h sprite px.
local function Tex(parent, layer, sub, path, w, h, base)
    local t = parent:CreateTexture(nil, layer, nil, sub or 0)
    SetTex(t, path or FLAT)
    t.fsBase = base or mod
    t.fsW, t.fsH = w or 1, h or 1
    Seat(function() t:SetSize(S(t.fsW), S(t.fsH)); local x, y = t.fsX, t.fsY; Forget(t); if x then Place(t, x, y) end end)
    return t
end

local function Size(t, w, h)
    if t.fsW == w and t.fsH == h then return end
    t.fsW, t.fsH = w, h
    t:SetSize(S(w), S(h))
end

local function Tint(t, c, a)
    if t.fsC == c and t.fsA == a then return end
    t.fsC, t.fsA = c, a
    t:SetVertexColor(c[1], c[2], c[3], a)
end

local function On(t, on)
    on = on and true or false
    if t.fsOn == on then return end
    t.fsOn = on
    if on then t:Show() else t:Hide() end
end

local function Alpha(t, a)
    if t.fsAl == a then return end
    t.fsAl = a
    t:SetAlpha(a)
end

-- texcoords of cell i of an atlas: cols across, `cell` texels square, the art w x h sprite px from the cell's top left
local function Cell(t, i, atlasW, atlasH, cols, cell, w, h)
    if t.fsCell == i then return end
    t.fsCell = i
    local l, top = (i % cols) * cell / atlasW, floor(i / cols) * cell / atlasH
    t:SetTexCoord(l, l + w * SCALE / atlasW, top, top + h * SCALE / atlasH)
end
local function ShieldCell(t, i) Cell(t, i, 512, 512, 4, 128, C.BOX, C.BOX) end
local function MendCell(t, i, w, h) Cell(t, i, 256, 256, 4, 64, w, h) end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

local function Text(parent, cx)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("CENTER")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(C.LABEL_SIZE), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint("CENTER", mod, "TOPLEFT", S(cx), -(S(C.LABEL_Y) - ui(C.CAP * C.LABEL_SIZE)))
    end)
    fs:SetText("")
    return fs
end

local function Label(fs, text, c)
    if fs.fsText ~= text then
        fs.fsText = text
        fs:SetText(text)
    end
    if c then TextColor(fs, c, 1) end
end

local SEC, EST_SEC = {}, {}
for i = 0, C.TEXT_MAX_S do SEC[i] = i .. "s"; EST_SEC[i] = "~" .. i .. "s" end
local function TimeLabel(rem, est)
    local n = ceil(rem)
    if n < 0 then n = 0 elseif n > C.TEXT_MAX_S then n = C.TEXT_MAX_S end
    return est and EST_SEC[n] or SEC[n]
end
Priest.TimeLabel = TimeLabel

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end      -- 20 steps: few alpha writes

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local function Frame(parent, level)
    local f = CreateFrame("Frame", nil, parent)
    f:SetFrameLevel(mod:GetFrameLevel() + level)
    f:SetAllPoints(mod)
    f:EnableMouse(false)
    return f
end

-------------------------------------------------------------------------------
-- Build: the shield
-------------------------------------------------------------------------------

local function BuildShield()
    local sc = C.SHIELD
    local bx, by = sc.cx - C.CENTER, sc.cy - C.CENTER
    -- the shield frame moves 1 px on a hit (the shake); every shield part is placed against it
    local sf = CreateFrame("Frame", nil, mod)
    sf:SetFrameLevel(mod:GetFrameLevel() + 1)
    sf:SetSize(1, 1)
    sf:EnableMouse(false)
    Seat(function() sf:SetSize(ui(C.W), ui(C.H)); local x = sf.fsX; sf.fsX = nil; if x then P.ShakeTo(x) end end)
    P.sf = sf
    function P.ShakeTo(dx)
        if sf.fsX == dx then return end
        sf.fsX = dx
        sf:ClearAllPoints()
        sf:SetPoint("TOPLEFT", mod, "TOPLEFT", S(dx), 0)
    end
    P.ShakeTo(0)

    local function ShieldTex(parent, layer, sub, cell)
        local t = Tex(parent, layer, sub, MEDIA .. "priest_shield.tga", C.BOX, C.BOX, sf)
        ShieldCell(t, cell)
        Place(t, bx, by)
        return t
    end

    -- the empty looks
    P.halo = ShieldTex(sf, "BACKGROUND", 1, CELL.halo)
    Tint(P.halo, K.white, 1)
    P.body = ShieldTex(sf, "BACKGROUND", 2, CELL.dark)
    P.stateRim = ShieldTex(sf, "ARTWORK", 1, CELL.rimDash)
    P.stateLine = ShieldTex(sf, "ARTWORK", 2, CELL.runeLine)
    P.stateRune = ShieldTex(sf, "ARTWORK", 3, CELL.rune)

    -- the light: the engine fills it from the secret absorb
    local bar = CreateFrame("StatusBar", nil, sf)
    bar:SetFrameLevel(mod:GetFrameLevel() + 2)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. "priest_shield_lit.tga")
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar.fsBase = sf
    Seat(function() bar:SetSize(S(C.LIT.w), S(C.LIT.h)); Forget(bar); Place(bar, sc.cx + C.LIT.x, sc.cy + C.LIT.y) end)
    P.bar = bar

    -- everything that shows only while the shield holds light: its alpha is the secret absorb
    local gate = CreateFrame("Frame", nil, sf)
    gate:SetFrameLevel(mod:GetFrameLevel() + 3)
    gate:SetAllPoints(sf)
    gate:EnableMouse(false)
    P.gate = gate
    P.aura = ShieldTex(gate, "BACKGROUND", 0, CELL.aura)
    P.rays = Tex(gate, "BACKGROUND", 1, MEDIA .. "priest_shield_rays.tga", C.RAYS_BOX, C.RAYS_BOX, sf)
    P.rays:SetTexCoord(0, C.RAYS_BOX * SCALE / 256, 0, C.RAYS_BOX * SCALE / 256)
    Place(P.rays, sc.cx - C.RAYS_CENTER, sc.cy - C.RAYS_CENTER)
    P.clearRim = ShieldTex(gate, "ARTWORK", 1, CELL.rimClear)
    P.upLine = ShieldTex(gate, "ARTWORK", 2, CELL.runeLine)
    Tint(P.upLine, K.runeLine, 1)
    P.upRune = ShieldTex(gate, "ARTWORK", 3, CELL.rune)
    Tint(P.upRune, K.white, 1)

    -- the glint and the motes ride only the lit part: a frame from the light's top edge down, clipping its children
    local clip = CreateFrame("Frame", nil, gate)
    clip:SetFrameLevel(mod:GetFrameLevel() + 3)
    clip:EnableMouse(false)
    local fill = bar.GetStatusBarTexture and bar:GetStatusBarTexture()
    local clipped = false
    if fill and clip.SetClipsChildren then
        clipped = pcall(function()
            clip:SetPoint("TOP", fill, "TOP", 0, 0)
            clip:SetPoint("BOTTOMLEFT", bar, "BOTTOMLEFT", 0, 0)
            clip:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
            clip:SetClipsChildren(true)
        end)
    end
    if not clipped then
        clip:ClearAllPoints()
        clip:SetAllPoints(sf)
        LogOnce("noclip", "the glint is not clipped to the light on this client")
    end
    P.clip = clip
    P.glint = Tex(clip, "ARTWORK", 4, MEDIA .. "priest_shield_glint.tga", C.BOX, C.BOX, sf)
    Place(P.glint, bx, by)
    P.motes = {}
    for i = 1, 5 do
        local m = { core = Tex(clip, "OVERLAY", 1, FLAT, 1, 1, sf), arms = {} }
        for a = 1, 4 do m.arms[a] = Tex(clip, "OVERLAY", 0, FLAT, 1, 1, sf) end
        P.motes[i] = m
    end
    P.flash = ShieldTex(gate, "OVERLAY", 2, CELL.flash)
    Tint(P.flash, K.white, 1)
    P.absorbLabel = Text(gate, sc.cx)

    -- the rims that win over the light: the cooldown and Weakened Soul
    local top = CreateFrame("Frame", nil, sf)
    top:SetFrameLevel(mod:GetFrameLevel() + 4)
    top:SetAllPoints(sf)
    top:EnableMouse(false)
    P.top = top
    P.cdRim = ShieldTex(top, "ARTWORK", 0, CELL.rimCd)
    P.wsDark = ShieldTex(top, "ARTWORK", 1, CELL.rimWsDark)
    local okCd, cd = pcall(CreateFrame, "Cooldown", nil, top)
    if okCd and cd and cd.SetSwipeTexture and cd.SetCooldown then
        cd:SetFrameLevel(mod:GetFrameLevel() + 5)
        cd:EnableMouse(false)
        pcall(cd.SetSwipeTexture, cd, MEDIA .. "priest_shield_ws.tga", 1, 1, 1, 1)
        if cd.SetSwipeColor then pcall(cd.SetSwipeColor, cd, 1, 1, 1, 1) end
        if cd.SetDrawEdge then pcall(cd.SetDrawEdge, cd, false) end
        if cd.SetDrawBling then pcall(cd.SetDrawBling, cd, false) end
        if cd.SetHideCountdownNumbers then pcall(cd.SetHideCountdownNumbers, cd, true) end
        if cd.SetReverse then pcall(cd.SetReverse, cd, false) end
        cd.fsBase = sf
        Seat(function() cd:SetSize(S(C.BOX), S(C.BOX)); Forget(cd); Place(cd, bx, by) end)
        P.wsCd = cd
    else
        -- no Cooldown widget: a static violet rim for the whole lock
        P.wsStatic = Tex(top, "ARTWORK", 2, MEDIA .. "priest_shield_ws.tga", C.BOX, C.BOX, sf)
        Place(P.wsStatic, bx, by)
        LogOnce("nocooldown", "the Weakened Soul rim does not drain on this client")
    end

    P.shards = {}
    for i = 1, 8 do
        local s = { big = Tex(sf, "OVERLAY", 3, FLAT, 2, 2, sf), dot = Tex(sf, "OVERLAY", 4, FLAT, 1, 1, sf) }
        P.shards[i] = s
    end
    P.wsLabel = Text(mod, sc.cx)
end

-------------------------------------------------------------------------------
-- Build: Prayer of Mending
-------------------------------------------------------------------------------

local function BeadPos(i)
    local a = pi * (1.1 + (i - 1) * 0.2)
    local pm = C.PM
    return floor(pm.cx + cos(a) * pm.r + 0.5), floor(pm.cy + sin(a) * pm.r + 0.5)
end
Priest.BeadPos = BeadPos

local function BuildMending()
    local pm = C.PM
    local mf = Frame(mod, 1)
    P.mf = mf
    local HX, HY = pm.cx - 7, pm.cy - 6
    P.chain, P.beads, P.lockDots = {}, {}, {}
    for i = 1, 4 do
        local x1, y1 = BeadPos(i)
        local x2, y2 = BeadPos(i + 1)
        local t = Tex(mf, "ARTWORK", 0, FLAT, 1, 1)
        Place(t, floor((x1 + x2) / 2 + 0.5), floor((y1 + y2) / 2 + 0.5))
        P.chain[i] = t
    end
    for i = 1, 5 do
        local x, y = BeadPos(i)
        local t = Tex(mf, "ARTWORK", 1, MEDIA .. "priest_mending.tga", 7, 7)
        Place(t, x - 3, y - 3)
        P.beads[i] = t
        for d = 1, 2 do
            local dot = Tex(mf, "ARTWORK", 1, FLAT, 1, 1)
            Tint(dot, K.muted, 0.4)
            Place(dot, x, y + (d == 1 and -1 or 1))
            P.lockDots[#P.lockDots + 1] = dot
        end
    end
    P.heartGlow = Tex(mf, "BACKGROUND", 0, MEDIA .. "priest_mending.tga", 18, 15)
    MendCell(P.heartGlow, MCELL.heartGlow, 18, 15)
    Place(P.heartGlow, HX - 2, HY - 1)
    P.heart = Tex(mf, "ARTWORK", 2, MEDIA .. "priest_mending.tga", 14, 12)
    Place(P.heart, HX, HY)
    local cdBar = CreateFrame("StatusBar", nil, mf)
    cdBar:SetFrameLevel(mod:GetFrameLevel() + 3)
    cdBar:EnableMouse(false)
    cdBar:SetStatusBarTexture(MEDIA .. "priest_heart_cd.tga")
    if cdBar.SetOrientation then pcall(cdBar.SetOrientation, cdBar, "VERTICAL") end
    if cdBar.SetReverseFill then pcall(cdBar.SetReverseFill, cdBar, true) end      -- the shade hangs from the top
    cdBar:SetMinMaxValues(0, 1)
    cdBar:SetValue(0)
    cdBar.fsBase = mod
    Seat(function() cdBar:SetSize(S(14), S(12)); Forget(cdBar); Place(cdBar, HX, HY) end)
    P.cdBar = cdBar

    P.seats = {}
    for i = 1, 5 do
        local sx, y = pm.seatX[i], pm.seatY
        local s = {}
        s.glow1 = Tex(mf, "BACKGROUND", 1, FLAT, 15, 14); Place(s.glow1, sx - 7, y - 1); Tint(s.glow1, K.gold, 0.22)
        s.glow2 = Tex(mf, "BACKGROUND", 1, FLAT, 13, 16); Place(s.glow2, sx - 6, y - 2); Tint(s.glow2, K.gold, 0.22)
        s.bg = Tex(mf, "BACKGROUND", 2, FLAT, 13, 12); Place(s.bg, sx - 6, y); Tint(s.bg, K.seatBg, 1)
        local bar = CreateFrame("StatusBar", nil, mf)
        bar:SetFrameLevel(mod:GetFrameLevel() + 2)
        bar:EnableMouse(false)
        bar:SetStatusBarTexture(FLAT)
        bar:SetStatusBarColor(K.litBody[1], K.litBody[2], K.litBody[3], 1)
        if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
        bar:SetMinMaxValues(0, 1)
        bar:SetValue(0)
        bar.fsBase = mod
        Seat(function() bar:SetSize(S(11), S(8)); Forget(bar); Place(bar, sx - 5, y + 1) end)
        s.bar = bar
        local over = Frame(mf, 3)
        s.over = over
        local sides = Frame(over, 4)
        s.sides = sides
        s.side1 = Tex(sides, "ARTWORK", 0, FLAT, 1, 10); Place(s.side1, sx - 7, y + 1); Tint(s.side1, K.aura, 0.3)
        s.side2 = Tex(sides, "ARTWORK", 0, FLAT, 1, 10); Place(s.side2, sx + 7, y + 1); Tint(s.side2, K.aura, 0.3)
        s.edges = {
            Tex(over, "ARTWORK", 1, FLAT, 13, 1), Tex(over, "ARTWORK", 1, FLAT, 13, 1),
            Tex(over, "ARTWORK", 1, FLAT, 1, 12), Tex(over, "ARTWORK", 1, FLAT, 1, 12),
        }
        Place(s.edges[1], sx - 6, y); Place(s.edges[2], sx - 6, y + 11)
        Place(s.edges[3], sx - 6, y); Place(s.edges[4], sx + 6, y)
        s.ws = Tex(over, "ARTWORK", 2, FLAT, 13, 2); Place(s.ws, sx - 6, y - 1); Tint(s.ws, K.violet, 1)
        s.strip = Tex(over, "ARTWORK", 2, FLAT, 11, 1); Place(s.strip, sx - 5, y + 9)
        s.heart = Tex(over, "ARTWORK", 3, MEDIA .. "priest_mending.tga", 7, 6)
        MendCell(s.heart, MCELL.heartSmall, 7, 6)
        Place(s.heart, sx - 3, y + 2)
        P.seats[i] = s
    end
    local over = Frame(mf, 4)
    P.you = Tex(over, "ARTWORK", 0, FLAT, 5, 1); Place(P.you, pm.seatX[1] - 2, pm.seatY - 3); Tint(P.you, K.you, 0.6)
    P.sparkGlow = Tex(over, "OVERLAY", 0, FLAT, 3, 3); Tint(P.sparkGlow, K.pink, 0.45)
    P.sparkCore = Tex(over, "OVERLAY", 1, FLAT, 1, 1); Tint(P.sparkCore, K.sparkCore, 1)
    local bx = pm.seatX[1] - 6
    P.barW = pm.seatX[5] + 6 - bx + 1
    P.timerBg = Tex(mf, "ARTWORK", 0, FLAT, P.barW, 2); Place(P.timerBg, bx, pm.seatY + 15); Tint(P.timerBg, K.barBg, 1)
    P.timerFill = Tex(mf, "ARTWORK", 1, FLAT, P.barW, 2); Place(P.timerFill, bx, pm.seatY + 15)
    P.pomLabel = Text(mod, pm.cx)
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

-- The secret absorb of the watched unit and of each seat, straight into the setters. Never compared.
local function PaintAbsorbs()
    local unit = Data.Watched()
    local v = Data.Absorb(unit)
    local mark = Data.Mark(unit)
    local bar, gate = P.bar, P.gate
    if v == nil then
        bar:SetMinMaxValues(0, 1); bar:SetValue(0); gate:SetAlpha(0)
    else
        bar:SetMinMaxValues(0, mark or v)
        bar:SetValue(v)
        gate:SetAlpha(v)
        if not abbreviateOff and type(AbbreviateNumbers) == "function" then
            local fs = P.absorbLabel
            local ok, text = pcall(AbbreviateNumbers, v)
            if ok then ok = pcall(fs.SetFormattedText, fs, "%s", text) end
            if not ok then abbreviateOff = true; fs:SetText(""); LogOnce("abbreviate", "the absorb number is off on this client") end
        end
    end
    for i = 1, 5 do
        local s = P.seats[i]
        local u = Data.SeatUnit(i)
        local a = s.fsMine and Data.Absorb(u) or nil
        if a == nil then
            s.bar:SetMinMaxValues(0, 1); s.bar:SetValue(0); s.sides:SetAlpha(0)
        else
            s.bar:SetMinMaxValues(0, Data.Mark(u) or a)
            s.bar:SetValue(a)
            s.sides:SetAlpha(a)
        end
    end
end

local function ShowShards(k)
    local sc = C.SHIELD
    local V = Priest.SHARDS
    for i = 1, 8 do
        local s, v = P.shards[i], V[i]
        if k then
            local qx = floor(sc.cx + v[1] + v[3] * k * 18 + 0.5)
            local qy = floor(sc.cy + v[2] + v[4] * k * 12 + k * k * 14 + 0.5)
            On(s.big, true); On(s.dot, true)
            Place(s.big, qx, qy); Place(s.dot, qx, qy)
            local a = Stepped(1 - k)
            Tint(s.big, K.shard, a); Tint(s.dot, K.white, a)
        else
            On(s.big, false); On(s.dot, false)
        end
    end
end
Priest.SHARDS = { { -16, -14, -1.2, -0.6 }, { 15, -10, 1.3, -0.4 }, { -12, 4, -1, 0.3 }, { 12, 6, 1.1, 0.5 },
    { -3, -4, -0.3, 1 }, { 6, -16, 0.6, -1 }, { -8, 14, -0.6, 0.8 }, { 9, 18, 0.7, 0.7 } }

local function InDisc(x, y, r) return x * x + y * y <= r * r + r * 0.8 end

-- Returns true while something on the shield moves.
local function PaintShield(now, combat)
    local sc = C.SHIELD
    if not Data.ShieldKnown() then
        On(P.halo, false); On(P.body, false); On(P.stateLine, false)
        On(P.bar, false); On(P.gate, false); On(P.top, false)
        ShieldCell(P.stateRim, CELL.rimDash)
        On(P.stateRim, true); Tint(P.stateRim, K.muted, 0.4)
        On(P.stateRune, true); Tint(P.stateRune, K.muted, 0.22)
        ShowShards(nil)
        P.ShakeTo(0)
        Label(P.wsLabel, "L6", K.muted)
        return false
    end
    On(P.body, true); On(P.bar, true); On(P.gate, true); On(P.top, true)

    local unit = Data.Watched()
    local r = Data.Shield(unit)
    local up = r and r.up or false
    local wsRem = r and r.ws and r.wsExpires and (r.wsExpires - now) or nil
    local ws = wsRem ~= nil and wsRem > 0
    local cd = Data.ShieldCooling() == true
    local nudge = combat and not ws and not up and not cd
    local calm = not combat and not ws and not up and not cd
    local b = nudge and Stepped(Beat(now, C.NUDGE)) or 0

    -- the empty looks (the light, when there is any, covers them). Calm is the GHOST (design mockup "Priest shield, off state",
    -- option C): its own cells, colours baked, so the region is not tinted; every other empty look keeps the dark shield and the
    -- tinted dashed rim.
    ShieldCell(P.body, calm and CELL.ghost or CELL.dark)
    ShieldCell(P.stateRim, calm and CELL.ghostRim or CELL.rimDash)
    On(P.stateRim, not ws and not cd)
    if calm then Tint(P.stateRim, K.white, 1)
    elseif nudge then Tint(P.stateRim, K.amber, 0.35 + 0.65 * b)
    else Tint(P.stateRim, K.rimClear, 0.45) end
    On(P.halo, nudge)
    if nudge then Alpha(P.halo, b) end
    On(P.stateRune, true)
    if ws then Tint(P.stateRune, K.violet, 1)
    elseif nudge then Tint(P.stateRune, K.amber, 0.45 + 0.55 * b)
    elseif cd then Tint(P.stateRune, K.cdOuter, 1)
    elseif calm then Tint(P.stateRune, K.rimClear, 0.7)
    else Tint(P.stateRune, K.rimClear, 1) end
    On(P.stateLine, ws or not (calm or cd))
    if ws then Tint(P.stateLine, K.violet, 0.25) else Tint(P.stateLine, K.rimClear, 0.22) end

    -- the rims over the light
    On(P.cdRim, cd and not ws)
    On(P.wsDark, ws)
    if P.wsCd then
        On(P.wsCd, ws)
        if ws then
            local dur = r.wsDuration or 15
            local start = r.wsExpires - dur
            if P.wsCd.fsStart ~= start or P.wsCd.fsDur ~= dur then
                P.wsCd.fsStart, P.wsCd.fsDur = start, dur
                pcall(P.wsCd.SetCooldown, P.wsCd, start, dur)
            end
        else
            P.wsCd.fsStart = nil
        end
    elseif P.wsStatic then
        On(P.wsStatic, ws)
    end

    -- the light's life: breathing aura and rays, the glint, the motes, a hit's flash and shake (all under the absorb gate)
    local br = Stepped(0.6 + 0.4 * Beat(now, C.BREATH))
    Alpha(P.aura, br); Alpha(P.rays, br)
    local gp = (now % C.GLINT_EVERY) / C.GLINT_LEN
    if gp < 1 then
        On(P.glint, true)
        local f = floor(gp * C.GLINT_FRAMES)
        Cell(P.glint, f, 512, 256, 4, 128, C.BOX, C.BOX)
    else
        On(P.glint, false)
    end
    local R = sc.r
    for i = 1, 5 do
        local m = P.motes[i]
        local ph = (now * C.MOTE_SPEED + (i - 1) * 0.2) % 1
        local mx, my = C.MOTE_X[i], floor(R - 6 - ph * (2 * R - 4) + 0.5)
        local a = Stepped(sin(ph * pi))
        local inside = InDisc(mx, my, R - 2)
        On(m.core, inside)
        if inside then
            Place(m.core, sc.cx + mx, sc.cy + my)
            Tint(m.core, K.white, a)
        end
        local arms = inside and a > 0.6
        for j = 1, 4 do
            local t = m.arms[j]
            On(t, arms)
            if arms then
                local dx = (j == 1 and -1) or (j == 2 and 1) or 0
                local dy = (j == 3 and -1) or (j == 4 and 1) or 0
                Place(t, sc.cx + mx + dx, sc.cy + my + dy)
                Tint(t, K.white, Stepped(0.4 * a))
            end
        end
    end
    local sinceHit = hitAt and (now - hitAt) or nil
    On(P.flash, sinceHit ~= nil and sinceHit < C.FLASH)
    if sinceHit and sinceHit < C.SHAKE then
        P.ShakeTo((floor(sinceHit * 50) % 2 == 1) and 1 or -1)
    else
        P.ShakeTo(0)
    end
    local sinceBreak = breakAt and (now - breakAt) or nil
    ShowShards(sinceBreak and sinceBreak < C.BREAK and sinceBreak / C.BREAK or nil)

    -- the label: the absorb while the guess says there is light, else the lock's time
    local wsLabel = ws and not up
    On(P.absorbLabel, not wsLabel)
    if wsLabel then Label(P.wsLabel, TimeLabel(wsRem, r.wsEst), K.violetLabel) else Label(P.wsLabel, "") end
    TextColor(P.absorbLabel, K.label, 1)

    return up or ws or cd or nudge or (sinceHit ~= nil and sinceHit < C.SHAKE)
        or (sinceBreak ~= nil and sinceBreak < C.BREAK) or (castAt ~= nil and now - castAt < 1)
end

local CLASS_COLORS = _G.RAID_CLASS_COLORS
local function SeatColor(i, unit)
    local exists = unit == "player"
    if not exists and type(UnitExists) == "function" then
        local ok, e = pcall(UnitExists, unit)
        exists = ok and not IsSecret(e) and e and true or false
    end
    if not exists then return nil end
    local token
    if type(UnitClass) == "function" then
        local ok, _, t = pcall(UnitClass, unit)
        if ok and not IsSecret(t) and type(t) == "string" then token = t end
    end
    local c = token and type(CLASS_COLORS) == "table" and CLASS_COLORS[token]
    if type(c) == "table" and type(c.r) == "number" then
        local cache = P.classCache[i]
        if cache[1] ~= c.r or cache[2] ~= c.g or cache[3] ~= c.b then cache[1], cache[2], cache[3] = c.r, c.g, c.b end
        return cache
    end
    return C.SEAT_CLASS[i]
end

local function PaintMending(now, combat)
    local m = Data.Mending()
    local locked = not m.known
    On(P.heart, true)
    for i = 1, #P.lockDots do On(P.lockDots[i], locked) end
    if locked then
        MendCell(P.heart, MCELL.heartLocked, 14, 12)
        Alpha(P.heart, 1)
        On(P.heartGlow, false); On(P.cdBar, false)
        for i = 1, 4 do On(P.chain[i], false) end
        for i = 1, 5 do On(P.beads[i], false) end
        for i = 1, 5 do
            local s = P.seats[i]
            On(s.glow1, false); On(s.glow2, false); On(s.bg, false); On(s.bar, false); On(s.over, false)
            s.fsMine = false
        end
        On(P.you, false); On(P.sparkGlow, false); On(P.sparkCore, false); On(P.timerBg, false); On(P.timerFill, false)
        Label(P.pomLabel, "L40", K.muted)
        return false
    end
    local out = m.out and true or false
    local cooling = Data.MendingCooling() == true
    local nudge = combat and not out and not cooling
    local b = Stepped(Beat(now, C.NUDGE))
    for i = 1, 4 do On(P.chain[i], true); Tint(P.chain[i], out and K.chainOut or K.chainOff, 1) end
    local charges = m.charges or 0
    for i = 1, 5 do
        On(P.beads[i], true)
        local cell = out and (i <= charges and MCELL.beadLit or MCELL.beadOff) or (nudge and MCELL.beadDash or MCELL.beadOff)
        MendCell(P.beads[i], cell, 7, 7)
    end
    if out then
        MendCell(P.heart, MCELL.heartLit, 14, 12); Alpha(P.heart, 1)
        On(P.heartGlow, true); Tint(P.heartGlow, K.pink, Stepped(0.16 + 0.14 * Beat(now, C.HEART_PULSE)))
    elseif nudge then
        MendCell(P.heart, MCELL.heartAmber, 14, 12); Alpha(P.heart, 0.4 + 0.6 * b)
        On(P.heartGlow, true); Tint(P.heartGlow, K.amber, Stepped(0.28 * b))
    else
        MendCell(P.heart, MCELL.heartOff, 14, 12); Alpha(P.heart, 1)
        On(P.heartGlow, false)
    end
    -- the cooldown shade: the engine's timer, from the duration object; a client without one shows no shade
    local shade = not out and cooling
    if shade and not P.cdBar.fsTimer then
        local obj = Data.MendingCooldownDuration()
        local E = _G.Enum
        local dir = E and E.StatusBarTimerDirection and E.StatusBarTimerDirection.RemainingTime
        local interp = E and E.StatusBarInterpolation and E.StatusBarInterpolation.Immediate
        P.cdBar.fsTimer = obj ~= nil and P.cdBar.SetTimerDuration ~= nil
            and pcall(P.cdBar.SetTimerDuration, P.cdBar, obj, interp, dir) or false
    elseif not shade then
        P.cdBar.fsTimer = nil
    end
    On(P.cdBar, shade and P.cdBar.fsTimer == true)

    -- the party strip
    for i = 1, 5 do
        local s = P.seats[i]
        local unit = Data.SeatUnit(i)
        local hold = out and m.holder == i
        On(s.bg, true); On(s.over, true)
        On(s.glow1, hold); On(s.glow2, hold)
        local edge = hold and K.gold or K.seatEdge
        for j = 1, 4 do Tint(s.edges[j], edge, 1) end
        local cc = SeatColor(i, unit)
        On(s.strip, true)
        Tint(s.strip, cc or K.seatEdge, hold and 1 or 0.5)
        On(s.heart, hold)
        local r = cc and Data.Shield(unit) or nil
        local mine = r and r.up and r.mine or false
        if s.fsMine ~= mine then s.fsMine = mine; P.absorbDirty = true end
        On(s.bar, mine); On(s.sides, mine)
        local wsRem = r and r.ws and r.wsMine and r.wsExpires and (r.wsExpires - now) or nil
        if wsRem and wsRem > 0 then
            On(s.ws, true)
            local n = ceil(13 * wsRem / 15)
            if n > 13 then n = 13 end
            Size(s.ws, n, 2)
        else
            On(s.ws, false)
        end
    end
    On(P.you, true)

    -- the jump spark
    local sinceJump = m.jumpAt and (now - m.jumpAt) or nil
    if sinceJump and sinceJump < C.JUMP and m.from and m.holder then
        local k = sinceJump / C.JUMP
        local x1, x2 = C.PM.seatX[m.from], C.PM.seatX[m.holder]
        local x = floor(x1 + (x2 - x1) * k + 0.5)
        local y = floor(C.PM.seatY + 5 - sin(k * pi) * 16 + 0.5)
        On(P.sparkGlow, true); On(P.sparkCore, true)
        Place(P.sparkGlow, x - 1, y - 1); Place(P.sparkCore, x, y)
    else
        On(P.sparkGlow, false); On(P.sparkCore, false)
        sinceJump = nil
    end

    -- the jump timer
    On(P.timerBg, true)
    local rem = out and m.expires and (m.expires - now) or nil
    if rem and rem > 0 then
        local w = floor(P.barW * rem / 30 + 0.5)
        if w > P.barW then w = P.barW end
        On(P.timerFill, w > 0)
        if w > 0 then Size(P.timerFill, w, 2) end
        Tint(P.timerFill, rem < 6 and K.amber or K.gold, 1)
        Label(P.pomLabel, TimeLabel(rem, m.est), rem < 6 and K.amber or K.goldLabel)
    else
        On(P.timerFill, false)
        Label(P.pomLabel, "")
    end
    return out or nudge or cooling or sinceJump ~= nil
end

local Sync
local function PaintAll(now)
    if not mod then return end
    local combat = InCombat()
    local ok1, a = pcall(PaintShield, now, combat)
    if not ok1 then LogOnce("paintshield", a); a = false end
    local ok2, b = pcall(PaintMending, now, combat)
    if not ok2 then LogOnce("paintmending", b); b = false end
    if P.absorbDirty then
        P.absorbDirty = false
        local ok, err = pcall(PaintAbsorbs)
        if not ok then LogOnce("absorb", err) end
    end
    P.moving = (a or b) and true or false
    if Sync then Sync() end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    absorbAcc = absorbAcc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Data.Tick, now)
    if not ok then LogOnce("tick", err) end
    if absorbAcc >= C.ABSORB_EVERY then absorbAcc = 0; P.absorbDirty = true end
    PaintAll(now)
end

Sync = function()
    local want = subscribed and mod ~= nil and P.moving == true
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

local function OnChange(reason, unit)
    local now = GetTime()
    if reason == "hit" and unit and type(UnitIsUnit) == "function" then
        local ok, same = pcall(UnitIsUnit, unit, Data.Watched())
        if ok and not IsSecret(same) and same and not (castAt and now - castAt < 0.3) then hitAt = now end
    elseif reason == "break" and unit then
        local ok, same = pcall(UnitIsUnit, unit, Data.Watched())
        if ok and not IsSecret(same) and same then breakAt = now end
    elseif reason == "cast" then
        castAt = now
    end
    P.absorbDirty = true
    if subscribed then PaintAll(now) end
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

-- The module's top left in image px, and a hook for whoever seats something over the shield (GunsightPriestClick.lua's click
-- catcher): fn(OX, OY) after every seat.
local seatListeners = {}
function Priest.Origin() return OX, OY end
function Priest.OnSeat(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #seatListeners do if seatListeners[i] == fn then return end end
    seatListeners[#seatListeners + 1] = fn
end

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y + C.DROP
    if mod then
        SeatAll()
        if subscribed then PaintAll(GetTime()) end
        for i = 1, #seatListeners do
            local ok, err = pcall(seatListeners[i], OX, OY)
            if not ok then LogOnce("seatlistener", err) end
        end
    end
end

local function BuildModule(host)
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono) then
        LogOnce("notheme", "Theme is missing, the Priest module is not built")
        return nil
    end
    Data = FS.PriestShields
    if not (Data and Data.Watched and Data.Subscribe) then
        LogOnce("nodata", "FS.PriestShields is missing, the Priest module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightPriest", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    P.classCache = { {}, {}, {}, {}, {} }
    local ok, err = pcall(function()
        BuildShield()
        BuildMending()
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Priest.frame, Priest.parts = mod, P
    if Data.Start then Data.Start() end
    P.absorbDirty = true
    PaintAll(GetTime())
    return mod
end

local function OnAreaShown()
    if not mod then return end
    if not subscribed then
        subscribed = true
        Data.Subscribe(OnChange)
    end
    local ok, err = pcall(Data.Refresh)
    if not ok then LogOnce("refresh", err) end
    P.absorbDirty = true
    PaintAll(GetTime())
    Sync()
end

local function OnAreaHidden()
    if not mod then return end
    if subscribed then
        subscribed = false
        Data.Unsubscribe(OnChange)
    end
    Sync()
end

-- for the harness
Priest._PaintShield, Priest._PaintMending, Priest._PaintAbsorbs = PaintShield, PaintMending, PaintAbsorbs

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "PRIEST" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
