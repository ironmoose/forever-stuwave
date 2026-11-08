-- Forever STUwave: Gunsight Class Module for the Hunter: the lock-on range scope and the traps
--
-- The approved design is the design mockup "Hunter Lock-on and Traps" (2026-11-07), design "D radar", on its 150 x 86 sprite
-- px canvas:
--   * THE SCOPE (left, centred at 38, 37): you are the centre dot and the rings are four range states, never yards (melee,
--     dead zone, shooting range, too far), told by FS.HunterState from Raptor Strike and Auto Shot range checks. A skull sits
--     on the ring the target is in at a fixed angle and slides between rings (0.3 s). The rim is the shot timer: it fills cyan
--     over the shot cycle and counts the seconds you may still walk in the label; the last 0.5 s of the cycle is always drawn
--     dim gold with a bright gold plant line (and tick marks at whole seconds); crossing it flashes white, the fill turns gold
--     and runs to 12 o'clock, four brackets snap in round the skull, a gold aim line draws from you to it and the label says
--     PLANT. The shot is an arrow down the line with a burst. Moving in the wind-up turns the rim pink, shakes the brackets
--     apart and counts the delay (+0.3); a shot that fired late shows +1.0 for 1.5 s. Out of range a due shot is HELD: the rim
--     is striped in the range colour, the brackets hold open, the label names the zone (DEAD ZONE, MELEE, FAR). A melee swing
--     that resets the shot flashes the rim pink and says RESET (switchable in HunterState.TUNING). Auto Shot off in combat
--     in shooting range is a dashed amber rim and AUTO. Low ammo shows a quiver and the count bottom left (the threshold is the
--     setting gunsight.hunter.ammowarn, default 60; 0 shows only NO AMMO).
--   * THE TRAPS (right, the jaws centred at 113, 22): every trap shares one 30 s cooldown. The jaws lie open with a soft glow
--     and READY while it is up, snap shut in a white flash with SET on a trap cast and then light back up from the bottom as
--     it refills (the engine draws it, there is no number). Under the jaws two ledger slots, a fire slot (Immolation,
--     Explosive) and a frost slot (Freezing, Frost), each a minute bar with "~N" counted from the player's own trap cast.
--
-- WHAT THIS BUILD DOES DIFFERENTLY FROM THE MOCKUP
--   * The trap refill is a StatusBar (the file equals its box, a vertical bar crops bottom up): the box is the twelve arc rows
--     with three spare rows over them and one under, so the lit rows are within one row of the mockup's all the way (it
--     lights the base row at the very start, the bar starts a row later).
--   * Labels are the house mono font, not the mockup's 3 x 5 pixel font.
--   * A shut-in-range lock-on is not drawn out of shooting range: the mockup lets the brackets snap in at any range, here
--     they stay open outside it (a held shot is the open pink / orange / grey brackets).
--   * Auto Shot off but not in combat with it in range (and in melee) is not a mockup state: the scope shows the range and the
--     skull with an empty rim and no seconds label.
--
-- DATA. Everything comes from FS.HunterState (HunterState.lua); its ledger listens from Start() on and never stops. This file
-- reads no aura and no secret: the shot clock, range, ammo and movement are plain reads made there, and the trap refill is the
-- engine's duration object into StatusBar:SetTimerDuration.
--
-- THE RIM is a pool of flat 1 x 1 sprite px (the mockup's own px ring), recoloured only when a px changes. The plant zone, the
-- plant line and the whole second ticks are laid out again when the cycle length changes (haste), the white spark that rides
-- the fill's edge is looked up in a list of the ring px sorted by angle. The two whole ring flashes (crossing the plant line,
-- a reset) are baked.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide
-- stops the OnUpdate and the subscription, onShow subscribes, refreshes and repaints. Plain frames only.
--
-- TICKER. One OnUpdate at most every C.TICK s while shown and something moves (the shot clock, the amber nudge, the ready
-- glow, a trap slot, a flash); it stops when nothing does. The tick allocates nothing: positions are numbers, texcoords and
-- labels are written on change and every number is a lookup in a table built once.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightHunter = FS.GunsightHunter or {}
local Hunter = FS.GunsightHunter

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil, sin, cos, pi, abs, sqrt, max, min = math.floor, math.ceil, math.sin, math.cos, math.pi, math.abs, math.sqrt, math.max,
    math.min
local atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
local TAU = 2 * pi

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    LABEL_Y = 76,                      -- the top of the mockup's 3 x 5 glyphs (its label row 74 plus 2); the mono baseline is BASELINE below
    BASELINE = 5,
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    SCOPE = { x = 38, y = 37 },        -- the scope's centre (the mockup's C)
    RIM0 = 31.5, RIM1 = 34.2, EDGE = 35.5,
    BAND_R = { melee = 4.5, dead = 10, ranged = 19, far = 28 }, SK = 0.62,   -- the skull's radius per range, angle from straight up
    SLIDE = 0.3,                       -- s the skull takes between two rings
    TRAP = { x = 113, y = 22 },        -- the open jaws' centre (the mockup's TC)
    SHUT = { 97, 17, 32, 16 },         -- the shut jaws' box: x, y, w, h in sprite px
    LIT = { 97, 15, 32, 16 },          -- the lit arcs' box: three spare rows above the arcs, one under (the base plate is the dark art's)
    SLOTS = { fire = { x = 82, y = 46 }, frost = { x = 82, y = 60 } },
    LABEL_SIZE = 11,
    CAP = 325 / 1024,                  -- Mononoki Bold: the line box's middle sits CAP * size above the baseline (as GunsightMage)
    NUDGE = 1.4, GLOW = 1.6, WIND = 0.35, LATE = 0.5,
    FLASH = 0.15, RESET_FLASH = 0.35, RESET_LABEL = 1.0, LATE_SHOW = 1.5, FREE_HOLD = 0.5,
    SNAP = 0.15, SNAP_HOLD = 0.4, SET_LABEL = 0.8, FRESH = 0.4,
    SPARKS = 24, MARKS = 32, TICKS = 24, DOTS = 32,
    CYCLE_SLACK = 0.01,                -- s a cycle may drift before the plant zone is laid out again
    COLORS = {
        white = Hex("#ffffff"), free = Hex("#22e0ff"), freeHi = Hex("#b8f6ff"), plant = Hex("#ffd36a"), plantHi = Hex("#fff1b8"),
        plantLo = Hex("#4a3a12"), outerLo = Hex("#8a6a20"), pink = Hex("#ff2e97"), pinkHi = Hex("#ff9ccc"), melee = Hex("#ff6a2a"),
        meleeHi = Hex("#ffb48a"), amber = Hex("#ffb648"), muted = Hex("#9d93c4"), dim = Hex("#3a2c5c"), mint = Hex("#4dffb4"),
        mintHi = Hex("#c8ffe6"), rimBase = Hex("#1a1028"), tick = Hex("#5a4a88"), lineCalm = Hex("#22183a"), skull = Hex("#ffc2d6"),
        farLabel = Hex("#b8aee0"), youBack = Hex("#0a0416"), black = Hex("#000000"), slotCalm = Hex("#2a1f44"),
        borderCalm = Hex("#241838"), flame = Hex("#ff6a2a"), flameHi = Hex("#ffb48a"), flake = Hex("#7ad8ff"), flakeHi = Hex("#d8f6ff"),
    },
}
C.BAR_W, C.BAR_H = 40, 6
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Hunter.C = C
local K = C.COLORS
local RANGE_COL = { ranged = K.free, dead = K.pink, melee = K.melee, far = K.muted }
local ZONE_ORDER = { "melee", "dead", "ranged", "far" }
-- ring line i separates INNER[i] from OUTER[i] (the outer edge has no outside)
local LINE_INNER = { "melee", "dead", "ranged", "far" }
local LINE_OUTER = { "dead", "ranged", "far", false }
local LINE_CELLS = { "line75", "line125", "line255", "line305" }

-- frame levels above the module frame: the mockup's draw order (zones, rim, what rides the rim, you, the lock-on, the skull, the
-- release), the trap bar over the trap frame, and the flashes and labels over everything
local LEVEL = { zones = 1, rim = 2, marks = 3, top = 4, you = 5, lock = 6, skull = 7, fx = 8, bar = 3, upper = 9 }

local SCALE = 2
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"

-- the cell maps: each is the order of the generator's list (generate_hunter_*.py), checked by the harness
local ZCELL = { unlitMelee = 0, unlitDead = 1, unlitRanged = 2, unlitFar = 3, litMelee = 4, litDead = 5, litRanged = 6, litFar = 7,
    line75 = 8, line125 = 9, line255 = 10, line305 = 11, cross = 12 }
local RCELL = { flashRing = 0, resetRing = 1, divider = 2 }
local SCELL = { skullBody = 0, skullDark = 1, skullHalo = 2, strikeDead = 3, clawsMelee = 4, ring5 = 5, ring7 = 6, bracketTL = 7,
    bracketTR = 8, bracketBL = 9, bracketBR = 10, quiver = 11, flameX = 12, flameO = 13, flameOff = 14, flakeX = 15, flakeO = 16,
    flakeOff = 17 }
local TCELL = { open = 0, glow = 1, shutDark = 2, shutWhite = 3, slotBorder = 4, slotInner = 5 }
Hunter.CELL = { zones = ZCELL, rings = RCELL, sprites = SCELL, trap = TCELL }

local function Atlas(file, w, h, cols, cw, ch, bw, bh, ox, oy)
    return { file = file, w = w, h = h, cols = cols, cw = cw, ch = ch, bw = bw, bh = bh, ox = ox or 32, oy = oy or ox or 32 }
end
local A = {
    zones = Atlas("hunter_zones.tga", 512, 512, 4, 128, 128, 64, 64, 32, 32),
    rings = Atlas("hunter_rings.tga", 512, 512, 3, 160, 160, 80, 80, 40, 40),
    sprites = Atlas("hunter_sprites.tga", 256, 512, 4, 64, 64, 32, 32, 16, 16),
    trapOpen = Atlas("hunter_trap.tga", 512, 256, 4, 128, 64, 64, 32, 32, 16),
    trapBox = Atlas("hunter_trap.tga", 512, 256, 4, 128, 64, 32, 16, 0, 0),
    trapSlot = Atlas("hunter_trap.tga", 512, 256, 4, 128, 64, 42, 8, 0, 0),
}
Hunter.A = A

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsighthunter_" .. key, "|cffff4488Forever STUwave|r: gunsight hunter module: " .. tostring(msg))
    end
end

local Data
local mod
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc = false, false, 0
local P = {}                       -- every part, built once
local V = {}                       -- what the current paint shows, gathered once a paint and reused
local WU = 0.5

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

local function Size(t, w, h)
    if t.fsW == w and t.fsH == h then return end
    t.fsW, t.fsH = w, h
    t:SetSize(S(w), S(h))
end

-- texcoords of cell i of an atlas: the art is the cell's top left bw x bh sprite px
local function CellOf(t, a, i)
    if t.fsCell == i then return end
    t.fsCell = i
    local l, top = (i % a.cols) * a.cw / a.w, floor(i / a.cols) * a.ch / a.h
    t:SetTexCoord(l, l + a.bw * SCALE / a.w, top, top + a.bh * SCALE / a.h)
end

-- A cell sprite whose art point (a.ox, a.oy) sits at sprite (ax, ay).
local function Spr(parent, layer, sub, a, cell, ax, ay, base)
    local t = Tex(parent, layer, sub, MEDIA .. a.file, a.bw, a.bh, base)
    t.fsAtlas = a
    CellOf(t, a, cell)
    Place(t, ax - a.ox, ay - a.oy)
    return t
end

local function SprAt(t, ax, ay)
    Place(t, ax - t.fsAtlas.ox, ay - t.fsAtlas.oy)
end

local function Flat(parent, layer, sub, w, h, base)
    return Tex(parent, layer, sub, FLAT, w, h, base)
end

local function Frame(parent, level, all)
    local f = CreateFrame("Frame", nil, parent)
    f:SetFrameLevel(mod:GetFrameLevel() + level)
    f:SetAllPoints(all or mod)
    f:EnableMouse(false)
    return f
end

local function MakeBar(parent, level, file, box, vertical, reverse, base)
    local bar = CreateFrame("StatusBar", nil, parent)
    bar:SetFrameLevel(mod:GetFrameLevel() + level)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. file)
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, vertical and "VERTICAL" or "HORIZONTAL") end
    if reverse and bar.SetReverseFill then pcall(bar.SetReverseFill, bar, true) end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar.fsBase = base or mod
    bar.fsBox = box
    Seat(function() bar:SetSize(S(box[3]), S(box[4])); Forget(bar); Place(bar, bar.fsBx, bar.fsBy) end)
    return bar
end

local function BarAt(bar, x, y)
    bar.fsBx, bar.fsBy = x, y
    Place(bar, x, y)
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- A label at sprite x cx (centred, or its left edge), its row top at y (the mockup's glyph tops; the baseline sits C.BASELINE below).
local function Text(parent, cx, y, left)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    local point = left and "LEFT" or "CENTER"
    fs:SetJustifyH(point)
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(C.LABEL_SIZE), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint(point, mod, "TOPLEFT", S(cx), -(S(y + C.BASELINE) - ui(C.CAP * C.LABEL_SIZE)))
    end)
    fs:SetText("")
    return fs
end

local function Label(fs, text, c, a)
    if fs.fsText ~= text then
        fs.fsText = text
        fs:SetText(text)
    end
    if c then TextColor(fs, c, a or 1) end
end

-- every number the labels show comes from these tables, built once
local TENTHS, PLUS_TENTHS, TRAP_SEC = {}, {}, {}
for i = 0, 99 do
    local s = floor(i / 10) .. "." .. (i % 10)
    TENTHS[i], PLUS_TENTHS[i] = s, "+" .. s
end
for i = 0, 60 do TRAP_SEC[i] = "~" .. i end
local function Tenths(v, tbl)
    local i = floor(v * 10 + 0.5)
    if i < 0 then i = 0 elseif i > 99 then i = 99 end
    return tbl[i]
end
Hunter.TENTHS, Hunter.PLUS_TENTHS = TENTHS, PLUS_TENTHS

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end      -- 20 steps: few alpha writes
local function Round(v) return floor(v + 0.5) end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

-- The refill of the shared trap cooldown: the engine's timer into a StatusBar (the bar's texture is the lit look). Returns whether
-- it runs. A client without the elapsed time direction or the timer shows no refill.
local function RefillTrap(bar, active)
    if active and bar.fsTimer == nil then
        local obj = Data.TrapDuration()
        local E = _G.Enum
        local dirs = E and E.StatusBarTimerDirection
        local dir = dirs and dirs.ElapsedTime
        local interp = E and E.StatusBarInterpolation and E.StatusBarInterpolation.Immediate
        bar.fsTimer = obj ~= nil and dir ~= nil and bar.SetTimerDuration ~= nil
            and pcall(bar.SetTimerDuration, bar, obj, interp, dir) or false
    elseif not active then
        bar.fsTimer = nil
    end
    local run = active and bar.fsTimer == true
    On(bar, run)
    return run
end

-------------------------------------------------------------------------------
-- Build: the scope
-------------------------------------------------------------------------------

local function BuildZones(root)
    local Z = {}
    P.zones = Z
    local c = C.SCOPE
    Z.unlit, Z.lit, Z.line = {}, {}, {}
    for i = 1, 4 do
        local band = ZONE_ORDER[i]
        local cap = band:sub(1, 1):upper() .. band:sub(2)
        Z.unlit[band] = Spr(root, "BACKGROUND", 0, A.zones, ZCELL["unlit" .. cap], c.x, c.y)
        Z.lit[band] = Spr(root, "BACKGROUND", 0, A.zones, ZCELL["lit" .. cap], c.x, c.y)
        On(Z.lit[band], false)
        Z.line[i] = Spr(root, "BACKGROUND", 1, A.zones, ZCELL[LINE_CELLS[i]], c.x, c.y)
    end
    Z.cross = Spr(root, "BACKGROUND", 2, A.zones, ZCELL.cross, c.x, c.y)
end

-- the rim: one flat 1 x 1 sprite px for every px of the mockup's ring, and the pools of the things that ride it
local function BuildRim(root)
    local R = { px = {}, n = 0 }
    P.rim = R
    local cx, cy = C.SCOPE.x, C.SCOPE.y
    local px, n = R.px, 0
    local sorted = {}
    R.sx, R.sy, R.sa = {}, {}, {}
    for y = 0, C.SH - 1 do
        for x = 0, C.SW - 1 do
            local dx, dy = x - cx, y - cy
            local d = sqrt(dx * dx + dy * dy)
            if d <= C.EDGE then
                local a = atan2(dx, -dy)
                if a < 0 then a = a + TAU end
                if d >= C.RIM0 and d <= C.RIM1 then
                    n = n + 1
                    local t = Flat(root, "ARTWORK", 0, 1, 1)
                    Place(t, x, y)
                    px[n] = { t = t, a = a, outer = d > C.RIM1 - 1, seg = floor(a / (TAU / 24)), sec = floor(a * 20),
                        dith = (x + y) % 2 == 0 }
                end
                if d >= C.RIM0 - 0.5 and d <= C.RIM1 + 0.5 then sorted[#sorted + 1] = { x = x, y = y, a = a } end
            end
        end
    end
    R.n = n
    table.sort(sorted, function(p, q) return p.a < q.a end)
    R.sn = #sorted
    for i = 1, R.sn do R.sx[i], R.sy[i], R.sa[i] = sorted[i].x, sorted[i].y, sorted[i].a end
    -- the tick marks, the plant line (laid out by LayoutCycle) and the spark
    R.marks = Frame(root, LEVEL.marks)
    R.ticks, R.line = {}, {}
    for i = 1, C.TICKS do
        R.ticks[i] = Flat(R.marks, "ARTWORK", 1, 1, 1)
        Tint(R.ticks[i], K.tick, 1)
        On(R.ticks[i], false)
    end
    for i = 1, C.MARKS do
        R.line[i] = Flat(R.marks, "ARTWORK", 2, 1, 1)
        On(R.line[i], false)
    end
    R.top = Frame(root, LEVEL.top)
    R.flash = Spr(R.top, "OVERLAY", 0, A.rings, RCELL.flashRing, cx, cy)
    R.spark = {}
    for i = 1, C.SPARKS do
        R.spark[i] = Flat(R.top, "OVERLAY", 1, 1, 1)
        Tint(R.spark[i], K.white, 1)
        On(R.spark[i], false)
    end
    R.reset = Spr(R.top, "OVERLAY", 2, A.rings, RCELL.resetRing, cx, cy)
    Tint(R.flash, K.white, 1)
    Tint(R.reset, K.pink, 1)
    On(R.flash, false)
    On(R.reset, false)
    R.sparkShown, R.tickShown, R.lineShown = 0, 0, 0
end

local function BuildYou(root)
    local Y = {}
    P.you = Y
    local c = C.SCOPE
    Y.back = Flat(root, "ARTWORK", 0, 7, 7)
    Place(Y.back, c.x - 3, c.y - 3)
    Tint(Y.back, K.youBack, 1)
    Y.dot = Flat(root, "ARTWORK", 1, 3, 3)
    Place(Y.dot, c.x - 1, c.y - 1)
    Y.feetL = Flat(root, "ARTWORK", 1, 2, 1)
    Y.feetR = Flat(root, "ARTWORK", 1, 2, 1)
end

local function BuildLock(root)
    local L = {}
    P.lock = L
    L.br = {
        TL = Spr(root, "OVERLAY", 0, A.sprites, SCELL.bracketTL, 0, 0), TR = Spr(root, "OVERLAY", 0, A.sprites, SCELL.bracketTR, 0, 0),
        BL = Spr(root, "OVERLAY", 0, A.sprites, SCELL.bracketBL, 0, 0), BR = Spr(root, "OVERLAY", 0, A.sprites, SCELL.bracketBR, 0, 0),
    }
    -- the mockup draws a bracket's corner px twice (once for each arm), which doubles its alpha when the bracket is translucent
    L.corner = {}
    for name in pairs(L.br) do
        L.corner[name] = Flat(root, "OVERLAY", 0, 1, 1)
        On(L.corner[name], false)
    end
    L.dots = {}
    for i = 1, C.DOTS do
        L.dots[i] = Flat(root, "OVERLAY", 1, 1, 1)
        On(L.dots[i], false)
    end
    L.dotsShown = 0
end

local function BuildSkull(root)
    local Sk = {}
    P.skull = Sk
    Sk.halo = Spr(root, "ARTWORK", 0, A.sprites, SCELL.skullHalo, 0, 0)
    Sk.body = Spr(root, "ARTWORK", 1, A.sprites, SCELL.skullBody, 0, 0)
    Sk.dark = Spr(root, "ARTWORK", 2, A.sprites, SCELL.skullDark, 0, 0)
    Sk.strike = Spr(root, "ARTWORK", 3, A.sprites, SCELL.strikeDead, 0, 0)
    Sk.claws = Spr(root, "ARTWORK", 3, A.sprites, SCELL.clawsMelee, 0, 0)
    Tint(Sk.strike, K.pinkHi, 1)
    Tint(Sk.claws, K.meleeHi, 1)
    On(Sk.strike, false)
    On(Sk.claws, false)
end

local DIRS = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 1, 1 }, { -1, -1 }, { 1, -1 }, { -1, 1 } }

local function BuildFx(root)
    local F = {}
    P.fx = F
    F.trail = {}
    for i = 0, 8 do
        F.trail[i] = Flat(root, "OVERLAY", 0, 1, 1)
        On(F.trail[i], false)
    end
    F.plusH = Flat(root, "OVERLAY", 1, 3, 1)
    F.plusV = Flat(root, "OVERLAY", 1, 1, 3)
    Tint(F.plusH, K.white, 1)
    Tint(F.plusV, K.white, 1)
    On(F.plusH, false)
    On(F.plusV, false)
    F.ring5 = Spr(root, "OVERLAY", 2, A.sprites, SCELL.ring5, 0, 0)
    F.ring7 = Spr(root, "OVERLAY", 2, A.sprites, SCELL.ring7, 0, 0)
    Tint(F.ring5, K.white, 1)
    Tint(F.ring7, K.white, 1)
    On(F.ring5, false)
    On(F.ring7, false)
    F.sparks = {}
    for i = 1, 8 do
        F.sparks[i] = Flat(root, "OVERLAY", 3, 1, 1)
        On(F.sparks[i], false)
    end
    F.shown = false
end

local function BuildLabels(root)
    local Lb = {}
    P.labels = Lb
    Lb.main = Text(root, C.SCOPE.x, C.LABEL_Y)
    Lb.quiver = Spr(root, "ARTWORK", 0, A.sprites, SCELL.quiver, 4, C.LABEL_Y - 1)
    On(Lb.quiver, false)
    Lb.ammo = Text(root, 11, C.LABEL_Y, true)
end

-------------------------------------------------------------------------------
-- Build: the traps
-------------------------------------------------------------------------------

local function BuildTraps(root, upper)
    local T = {}
    P.trap = T
    local tc, sb = C.TRAP, C.SHUT
    T.divider = Spr(root, "BACKGROUND", 0, A.rings, RCELL.divider, C.SCOPE.x, C.SCOPE.y)
    T.open = Spr(root, "ARTWORK", 0, A.trapOpen, TCELL.open, tc.x, tc.y)
    T.glow = Spr(root, "ARTWORK", 1, A.trapOpen, TCELL.glow, tc.x, tc.y)
    Tint(T.glow, K.mint, 0.1)
    T.dark = Spr(root, "ARTWORK", 0, A.trapBox, TCELL.shutDark, sb[1], sb[2])
    T.lit = MakeBar(root, LEVEL.bar, "hunter_trap_lit.tga", C.LIT, true, false)
    BarAt(T.lit, C.LIT[1], C.LIT[2])
    T.white = Spr(upper, "ARTWORK", 0, A.trapBox, TCELL.shutWhite, sb[1], sb[2])
    On(T.dark, false)
    On(T.lit, false)
    On(T.white, false)
    On(T.glow, false)
    T.dim = Flat(upper, "ARTWORK", 1, 68, 34)
    Place(T.dim, 80, 4)
    Tint(T.dim, K.youBack, 0.55)
    On(T.dim, false)
    T.label = Text(upper, tc.x, 36)
    T.slots = {}
    for _, kind in ipairs({ "fire", "frost" }) do
        local sl = C.SLOTS[kind]
        local Sl = { kind = kind }
        T.slots[kind] = Sl
        local x, y = sl.x, sl.y
        local fx = kind == "fire" and "flame" or "flake"
        Sl.iconX = Spr(root, "ARTWORK", 1, A.sprites, SCELL[fx .. "X"], x, y)
        Sl.iconO = Spr(root, "ARTWORK", 2, A.sprites, SCELL[fx .. "O"], x, y)
        Sl.iconOff = Spr(root, "ARTWORK", 1, A.sprites, SCELL[fx .. "Off"], x, y)
        Sl.border = Spr(root, "ARTWORK", 0, A.trapSlot, TCELL.slotBorder, x + 23, y)
        Sl.inner = Spr(root, "ARTWORK", 1, A.trapSlot, TCELL.slotInner, x + 23, y)
        Sl.fill = Flat(root, "ARTWORK", 2, C.BAR_W, C.BAR_H)
        Sl.hi = Flat(root, "ARTWORK", 3, C.BAR_W, 1)
        Sl.shade = Flat(root, "ARTWORK", 3, C.BAR_W, 1)
        Place(Sl.fill, x + 24, y + 1)
        Place(Sl.hi, x + 24, y + 1)
        Place(Sl.shade, x + 24, y + C.BAR_H)
        Tint(Sl.shade, K.black, 0.3)
        Sl.flash = Flat(upper, "OVERLAY", 2, 9, 10)
        Place(Sl.flash, x - 1, y - 1)
        Tint(Sl.flash, K.white, 1)
        On(Sl.flash, false)
        Sl.label = Text(upper, x + 9, y + 2, true)
        Sl.col = kind == "fire" and K.flame or K.flake
        Sl.hiCol = kind == "fire" and K.flameHi or K.flakeHi
        Sl.n = -1
    end
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function PaintPx(px, c, a)
    if px.c == c and px.al == a then return end
    px.c, px.al = c, a
    px.t:SetVertexColor(c[1], c[2], c[3], a)
end

-- the whole second ticks and the plant line, for a cycle of `cycle` s. The scan runs only when the cycle changes.
local function LayoutCycle(cycle)
    local R = P.rim
    if R.laidCycle and abs(R.laidCycle - cycle) < C.CYCLE_SLACK then return end
    R.laidCycle = cycle
    local cx, cy = C.SCOPE.x, C.SCOPE.y
    local pa = TAU * (cycle - WU) / cycle
    local nt, nl = 0, 0
    local lastTick = ceil(cycle) - 1
    for y = max(0, cy - 37), min(C.SH - 1, cy + 37) do
        for x = max(0, cx - 37), min(C.SW - 1, cx + 37) do
            local dx, dy = x - cx, y - cy
            local d = sqrt(dx * dx + dy * dy)
            if d <= C.EDGE then
                local a = atan2(dx, -dy)
                if a < 0 then a = a + TAU end
                if d >= C.RIM0 - 2 and d <= C.RIM1 + 2 and abs(a - pa) < 0.045 and nl < C.MARKS then
                    nl = nl + 1
                    Place(R.line[nl], x, y)
                    On(R.line[nl], true)
                end
                if d > C.RIM1 and d < C.RIM1 + 1 then
                    for k = 1, lastTick do
                        if abs(a - TAU * k / cycle) < 0.03 and nt < C.TICKS then
                            nt = nt + 1
                            Place(R.ticks[nt], x, y)
                            On(R.ticks[nt], true)
                            break
                        end
                    end
                end
            end
        end
    end
    for i = nl + 1, R.lineShown do On(R.line[i], false) end
    for i = nt + 1, R.tickShown do On(R.ticks[i], false) end
    R.lineShown, R.tickShown = nl, nt
    R.plantAngle = pa
end

local function PaintZones(v)
    local Z = P.zones
    local calm = v.zoneCalm
    for i = 1, 4 do
        local band = ZONE_ORDER[i]
        local lit = (not calm) and v.range == band
        On(Z.lit[band], lit)
        On(Z.unlit[band], not lit)
        local inner, outer = LINE_INNER[i], LINE_OUTER[i]
        if not calm and (v.range == inner or v.range == outer) then Tint(Z.line[i], RANGE_COL[v.range], 0.8)
        else Tint(Z.line[i], calm and K.lineCalm or K.dim, 1) end
    end
    On(Z.cross, not calm)
end

local function PaintRim(v, now)
    local R = P.rim
    local px, n = R.px, R.n
    local mode = v.mode
    local A_ = TAU * v.fill
    if mode == "calm" then
        for i = 1, n do PaintPx(px[i], K.rimBase, 1) end
    elseif mode == "nudge" then
        local al = 0.35 + 0.65 * v.nb
        for i = 1, n do
            local p = px[i]
            if p.seg % 2 == 1 then PaintPx(p, K.amber, al) else PaintPx(p, K.rimBase, 1) end
        end
    elseif v.held then
        local hc = RANGE_COL[v.held]
        local ph = floor(now * 8)
        for i = 1, n do
            local p = px[i]
            PaintPx(p, hc, (p.sec + ph) % 2 == 1 and 0.9 or 0.3)
        end
    elseif v.lateMove then
        local al = 0.5 + 0.5 * Stepped(Beat(now, C.LATE))
        for i = 1, n do PaintPx(px[i], K.pink, al) end
    else
        local pa = TAU * v.plantF
        local near = pa - TAU * 0.05
        local wind = v.wind
        local wa = 0.75 + 0.25 * Stepped(Beat(now, C.WIND))
        for i = 1, n do
            local p = px[i]
            local a = p.a
            if wind and a < A_ then
                if p.outer then PaintPx(p, K.plantHi, 1) else PaintPx(p, K.plant, wa) end
            elseif a < A_ then
                PaintPx(p, p.outer and K.freeHi or K.free, 1)
            elseif a >= pa then
                PaintPx(p, p.outer and K.outerLo or K.plantLo, 1)
            elseif a >= near and p.dith then
                PaintPx(p, K.plantLo, 1)
            else
                PaintPx(p, K.rimBase, 1)
            end
        end
    end
    -- the things on the rim: only while the shot clock is told (not calm, not the amber nudge, not held)
    local extras = mode == "run" and not v.held
    On(R.marks, extras)
    if extras then
        LayoutCycle(v.cycle)
        local lineWind = v.wind and true or false
        if R.lineWind ~= lineWind then
            R.lineWind = lineWind
            for i = 1, C.MARKS do Tint(R.line[i], lineWind and K.white or K.plant, 1) end
        end
    end
    -- crossing the plant line: one flash round the whole scope
    local since = (v.fill - v.plantF) * v.cycle
    local flash = extras and v.wind and v.late == 0 and since >= 0 and since < C.FLASH
    On(R.flash, flash)
    if flash then Tint(R.flash, K.white, Stepped(0.9 * (1 - since / C.FLASH))) end
    -- the spark on the fill's edge
    local shown = 0
    if extras and v.fill > 0 and v.fill < 1 then
        local sa, sn = R.sa, R.sn
        local lo, hi = 1, sn + 1
        local low = A_ - 0.05
        while lo < hi do
            local mid = floor((lo + hi) / 2)
            if sa[mid] > low then hi = mid else lo = mid + 1 end
        end
        local top = A_ + 0.05
        local i = lo
        while i <= sn and sa[i] < top and shown < C.SPARKS do
            shown = shown + 1
            Place(R.spark[shown], R.sx[i], R.sy[i])
            On(R.spark[shown], true)
            i = i + 1
        end
    end
    for i = shown + 1, R.sparkShown do On(R.spark[i], false) end
    R.sparkShown = shown
    local resetOn = extras and v.resetT ~= nil and v.resetT < C.RESET_FLASH
    On(R.reset, resetOn)
    if resetOn then Tint(R.reset, K.pink, Stepped(0.85 * (1 - v.resetT / C.RESET_FLASH))) end
end

local function PaintYou(v, now)
    local Y = P.you
    local c = C.SCOPE
    local calm = v.zoneCalm
    local yc
    if calm then yc = K.dim
    elseif v.mode == "nudge" then Tint(Y.dot, K.amber, 0.4 + 0.6 * v.nb); yc = nil
    elseif v.k ~= nil then yc = K.plantHi
    elseif v.lateMove then yc = K.pink
    else yc = K.freeHi end
    if yc then Tint(Y.dot, yc, 1) end
    local feet = (not calm) and v.mode == "run"
    On(Y.feetL, feet)
    On(Y.feetR, feet)
    if feet then
        if v.k ~= nil then
            Size(Y.feetL, 2, 1); Size(Y.feetR, 2, 1)
            Place(Y.feetL, c.x - 3, c.y + 3); Place(Y.feetR, c.x + 2, c.y + 3)
            Tint(Y.feetL, K.plantHi, 1); Tint(Y.feetR, K.plantHi, 1)
        else
            local mv = v.moving or v.lateMove
            local st = mv and floor(now * 6) % 2 or 0
            Size(Y.feetL, 1, 1); Size(Y.feetR, 1, 1)
            Place(Y.feetL, c.x - 2, c.y + 2 + st); Place(Y.feetR, c.x + 2, c.y + 3 - st)
            local fc = v.lateMove and K.pink or K.free
            Tint(Y.feetL, fc, 1); Tint(Y.feetR, fc, 1)
        end
    end
end

local function SkullPos(v)
    local r = C.BAND_R[v.range] or C.BAND_R.ranged
    if v.rangeFrom and v.rangeK < 1 then
        local a = C.BAND_R[v.rangeFrom]
        r = a + (r - a) * v.rangeK
    end
    return Round(C.SCOPE.x + r * sin(C.SK)), Round(C.SCOPE.y - r * cos(C.SK))
end

local function HideLock(L)
    for _, b in pairs(L.br) do On(b, false) end
    for _, c in pairs(L.corner) do On(c, false) end
    for i = 1, L.dotsShown do On(L.dots[i], false) end
    L.dotsShown = 0
end

local SIGNS = { TL = { -1, -1 }, TR = { 1, -1 }, BL = { -1, 1 }, BR = { 1, 1 } }

local function PaintLock(v, now, px_, py_)
    local L = P.lock
    if v.mode ~= "run" then HideLock(L) return end
    local k = v.k
    local size, col, al
    if v.held then size, col, al = 11, RANGE_COL[v.held], 1
    elseif v.lateMove then size, col, al = 9 + ((floor(now * 12) % 2 == 1) and 2 or 0), K.pink, 1
    elseif k == nil then
        if v.releaseT ~= nil and v.releaseT < C.FREE_HOLD then HideLock(L) return end
        size, col, al = 12, K.free, 0.45
    else
        size = Round(12 - 6 * k)
        col, al = k >= 0.98 and K.white or K.plant, 1
    end
    for name, b in pairs(L.br) do
        local sg = SIGNS[name]
        On(b, true)
        SprAt(b, px_ + sg[1] * size, py_ + sg[2] * size)
        Tint(b, col, al)
        local c = L.corner[name]
        On(c, true)
        Place(c, px_ + sg[1] * size, py_ + sg[2] * size)
        Tint(c, col, al)
    end
    -- the aim line from you to the skull
    local cx, cy = C.SCOPE.x, C.SCOPE.y
    local dx, dy = px_ - cx, py_ - cy
    local n = max(abs(dx), abs(dy))
    local shown = 0
    local solid = k ~= nil and not v.lateMove and not v.held
    for j = 1, C.DOTS do
        local i = j + 2
        if i >= n - 4 then break end
        local d = L.dots[j]
        local show, dc, da
        if solid then show, dc, da = i / n <= max(0.15, k), K.plantHi, 1
        elseif v.lateMove then show, dc, da = i % 2 == 1, K.pink, 0.8
        else show, dc, da = i % 3 == 0, K.free, 0.4 end
        On(d, show)
        if show then
            Place(d, Round(cx + dx * i / n), Round(cy + dy * i / n))
            Tint(d, dc, da)
        end
        shown = j
    end
    for j = shown + 1, L.dotsShown do On(L.dots[j], false) end
    L.dotsShown = shown
end

local function PaintSkull(v, now, px_, py_)
    local Sk = P.skull
    local bob = (floor(now * 2) % 2 == 1) and 0 or -1
    SprAt(Sk.halo, px_, py_ + bob)
    SprAt(Sk.body, px_, py_ + bob)
    SprAt(Sk.dark, px_, py_ + bob)
    Tint(Sk.body, v.range == "ranged" and K.skull or RANGE_COL[v.range], v.range == "far" and 0.55 or 1)
    local run = v.mode == "run"
    On(Sk.strike, run and v.range == "dead")
    On(Sk.claws, run and v.range == "melee")
    SprAt(Sk.strike, px_, py_)
    SprAt(Sk.claws, px_, py_)
end

local function HideFx(F)
    if not F.shown then return end
    F.shown = false
    for i = 0, 8 do On(F.trail[i], false) end
    On(F.plusH, false)
    On(F.plusV, false)
    On(F.ring5, false)
    On(F.ring7, false)
    for i = 1, 8 do On(F.sparks[i], false) end
end

local function PaintFx(v, now, px_, py_)
    local F = P.fx
    local rt = v.releaseT
    if rt == nil or rt >= 0.15 + 0.35 then HideFx(F) return false end
    F.shown = true
    local cx, cy = C.SCOPE.x, C.SCOPE.y
    if rt < 0.15 then
        local k = rt / 0.15
        for i = 0, 8 do
            local kk = max(0, k - i * 0.06)
            local x, y = Round(cx + (px_ - cx) * kk), Round(cy + (py_ - cy) * kk)
            local t = F.trail[i]
            On(t, true)
            Place(t, x, y)
            if i == 0 then
                Tint(t, K.white, 1)
                On(F.plusH, true); On(F.plusV, true)
                Place(F.plusH, x - 1, y); Place(F.plusV, x, y - 1)
            else
                Tint(t, K.freeHi, Stepped((1 - i / 9) * 0.85))
            end
        end
    else
        for i = 0, 8 do On(F.trail[i], false) end
        On(F.plusH, false); On(F.plusV, false)
    end
    local k = (rt - 0.15) / 0.35
    if k >= 0 and k < 1 then
        local ring = k < 0.4 and F.ring5 or F.ring7
        On(F.ring5, ring == F.ring5)
        On(F.ring7, ring == F.ring7)
        SprAt(ring, px_, py_)
        Tint(ring, K.white, Stepped(0.85 * (1 - k)))
        local r = Round(3 + k * 6)
        for i = 1, 8 do
            local s = F.sparks[i]
            On(s, true)
            Place(s, px_ + DIRS[i][1] * r, py_ + DIRS[i][2] * r)
            Tint(s, i <= 4 and K.white or K.pinkHi, Stepped(1 - k))
        end
    else
        On(F.ring5, false); On(F.ring7, false)
        for i = 1, 8 do On(F.sparks[i], false) end
    end
    return true
end

-- the label under the scope: one line by the mockup's order of precedence
local function PaintLabel(v, now)
    local Lb = P.labels
    local text, col, al = "", K.freeHi, 1
    if v.mode == "calm" then
        text = ""
    elseif v.mode == "nudge" then text, col, al = "AUTO", K.amber, 0.35 + 0.65 * v.nb
    elseif v.ammo == 0 then text, col = "NO AMMO", K.pink
    elseif v.resetT ~= nil and v.resetT < C.RESET_LABEL then text, col = "RESET", K.pink
    elseif v.lateShow ~= nil then text, col = Tenths(v.lateShow, PLUS_TENTHS), K.pink
    elseif v.held or (v.range ~= nil and v.range ~= "ranged") then
        local zone = v.held or v.range
        text = zone == "dead" and "DEAD ZONE" or zone == "melee" and "MELEE" or "FAR"
        col = zone == "far" and K.farLabel or RANGE_COL[zone]
    elseif v.late > 0 then text, col = Tenths(v.late, PLUS_TENTHS), K.pinkHi
    elseif v.idle then text = ""
    elseif v.plant then text, col = "PLANT", K.plantHi
    else text, col = Tenths(max(0, v.moveLeft), TENTHS), K.freeHi end
    Label(Lb.main, text, col, al)
    local showAmmo = v.mode ~= "calm" and v.ammo ~= nil and v.ammo <= v.warn
    On(Lb.quiver, showAmmo)
    if showAmmo then
        local ac = v.ammo == 0 and K.pink or K.amber
        Tint(Lb.quiver, ac, 1)
        if Lb.ammoShown ~= v.ammo then Lb.ammoShown, Lb.ammoText = v.ammo, tostring(v.ammo) end
        Label(Lb.ammo, Lb.ammoText, ac, 1)
        On(Lb.ammo, true)
    else
        On(Lb.ammo, false)
    end
end

local function PaintSlot(Sl, fam, now, calm)
    local left = fam.up and (fam.expires - now) or 0
    local on = fam.up and left > 0 and not calm
    On(Sl.iconX, on)
    On(Sl.iconO, on)
    On(Sl.iconOff, not on)
    if on then
        Tint(Sl.iconX, Sl.col, 1)
        Tint(Sl.iconO, Sl.hiCol, 1)
    else
        Tint(Sl.iconOff, calm and K.slotCalm or K.dim, 1)
    end
    Tint(Sl.border, calm and K.borderCalm or K.dim, 1)
    On(Sl.fill, on)
    On(Sl.hi, on)
    On(Sl.shade, on)
    On(Sl.label, on)
    local fresh = on and fam.at and (now - fam.at) or nil
    local flash = fresh ~= nil and fresh < C.FRESH
    On(Sl.flash, flash)
    if flash then Tint(Sl.flash, K.white, Stepped(0.8 * (1 - fresh / C.FRESH))) end
    if on then
        local life = Data.TUNING.TRAP_LIFE
        local frac = left / life
        if frac > 1 then frac = 1 end
        local n = Round(C.BAR_W * frac)
        if Sl.n ~= n then
            Sl.n = n
            if n > 0 then
                Size(Sl.fill, n, C.BAR_H); Size(Sl.hi, n, 1); Size(Sl.shade, n, 1)
            end
        end
        On(Sl.fill, n > 0); On(Sl.hi, n > 0); On(Sl.shade, n > 0)
        Tint(Sl.fill, Sl.col, 1)
        Tint(Sl.hi, Sl.hiCol, 1)
        local sec = ceil(left)
        if sec > 60 then sec = 60 end
        Label(Sl.label, TRAP_SEC[sec], Sl.hiCol, 1)
    end
    return on or flash
end

local function PaintTraps(v, now)
    local T = P.trap
    local calm = v.mode == "calm"
    local learned = Data.TrapKey() ~= nil
    local cooling = Data.TrapCooling()
    local castAt = Data.TrapCastAt()
    local since = castAt and (now - castAt) or nil
    local snapping = since ~= nil and since < C.SNAP
    local held = since ~= nil and since < C.SNAP_HOLD
    local shut = learned and (cooling == true or held)
    local ready = learned and cooling == false and not held
    On(T.open, not shut)
    On(T.glow, ready and not calm)
    if ready and not calm then Tint(T.glow, K.mint, 0.1 + 0.08 * Stepped(Beat(now, C.GLOW))) end
    On(T.dark, shut and not snapping)
    On(T.white, shut and snapping)
    RefillTrap(T.lit, shut and not snapping and cooling == true)
    On(T.dim, calm or not learned)
    local text, col = "", K.mintHi
    if since ~= nil and since < C.SET_LABEL then text, col = "SET", K.white
    elseif ready and not calm then text = "READY" end
    Label(T.label, text, col, 1)
    local a = PaintSlot(T.slots.fire, Data.Traps().fire, now, calm)
    local b = PaintSlot(T.slots.frost, Data.Traps().frost, now, calm)
    return (ready and not calm) or a or b or (since ~= nil and since < C.SET_LABEL)
end

-------------------------------------------------------------------------------
-- Gather: what the scope shows right now
-------------------------------------------------------------------------------

local function Gather(now, combat)
    local v = V
    local shot = Data.Shot()
    local cycle = shot.cycle
    v.cycle = cycle
    v.plantF = (cycle - WU) / cycle
    local auto = Data.AutoOn(now)
    local calm = (not combat) and not auto
    local rng = (not calm) and Data.Range(now) or nil
    v.range = rng
    local mode = "run"
    if calm then mode = "calm"
    elseif combat and not auto and rng == "ranged" then mode = "nudge" end
    v.mode = mode
    v.zoneCalm = calm or rng == nil
    v.nb = Stepped(Beat(now, C.NUDGE))
    -- the skull slides between rings
    if rng ~= P.rangeNow then
        P.rangePrev, P.rangeNow, P.rangeAt = P.rangeNow, rng, now
    end
    v.rangeFrom = (rng ~= nil and P.rangePrev ~= nil and P.rangePrev ~= rng) and P.rangePrev or nil
    v.rangeK = P.rangeAt and (now - P.rangeAt) / C.SLIDE or 1
    local autoRun = mode == "run" and auto
    v.idle = mode == "run" and not auto
    local fill = autoRun and Data.Fill(now) or 0
    local late = autoRun and Data.Late(now) or 0
    local inRange = rng == nil or rng == "ranged"
    local held = nil
    if autoRun and fill >= 1 and not inRange then held, late = rng, 0 end
    v.held, v.fill, v.late = held, fill, late
    local moving = autoRun and Data.Moving() == true or false
    v.moving = moving
    local wind = autoRun and (fill >= v.plantF or late > 0) or false
    v.wind = wind
    v.lateMove = wind and moving and inRange and not held
    v.plant = autoRun and fill >= v.plantF and not v.lateMove and inRange and not held
    local k = nil
    if mode == "run" and not held then
        if late > 0 then
            if not v.lateMove then k = min(1, 0.5 + late) end
        elseif autoRun and inRange and fill >= v.plantF then
            k = min(1, (fill - v.plantF) / (1 - v.plantF))
        end
    end
    v.k = k
    v.moveLeft = (cycle - WU) - fill * cycle
    v.lateShow = (shot.lateAmt ~= nil and shot.firedAt ~= nil and now - shot.firedAt < C.LATE_SHOW) and shot.lateAmt or nil
    v.resetT = (shot.resetAt ~= nil) and (now - shot.resetAt) or nil
    v.releaseT = (shot.firedAt ~= nil) and (now - shot.firedAt) or nil
    v.ammo, v.warn = Data.Ammo(), Data.AmmoWarn()
    return v
end

-------------------------------------------------------------------------------
-- Paint: everything
-------------------------------------------------------------------------------

local Sync
local function Run(tag, fn, ...)
    local ok, r = pcall(fn, ...)
    if not ok then LogOnce(tag, r); return false end
    return r and true or false
end

local function PaintScope(now, combat)
    local v = Gather(now, combat)
    PaintZones(v)
    PaintRim(v, now)
    PaintYou(v, now)
    local px_, py_ = SkullPos(v)
    local calm = v.zoneCalm
    On(P.skull.halo, not calm)
    On(P.skull.body, not calm)
    On(P.skull.dark, not calm)
    if calm then
        On(P.skull.strike, false)
        On(P.skull.claws, false)
        HideLock(P.lock)
        HideFx(P.fx)
    else
        PaintSkull(v, now, px_, py_)
        PaintLock(v, now, px_, py_)
        PaintFx(v, now, px_, py_)
    end
    PaintLabel(v, now)
    return v.mode ~= "calm" or (v.rangeFrom ~= nil and v.rangeK < 1)
end

local function PaintAll(now)
    if not mod then return end
    local combat = InCombat()
    local scope = Run("paintscope", PaintScope, now, combat)
    local moving = scope
    local ok, r = pcall(PaintTraps, V, now)
    if ok then moving = moving or r else LogOnce("painttraps", r) end
    P.moving = moving and true or false
    if Sync then Sync() end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Data.Tick, now)
    if not ok then LogOnce("tick", err) end
    PaintAll(now)
end

Sync = function()
    local want = subscribed and mod ~= nil and P.moving == true
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

local function OnChange(reason)
    if subscribed then PaintAll(GetTime()) end
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y + C.DROP
    if mod then
        SeatAll()
        if subscribed then PaintAll(GetTime()) end
    end
end

local function BuildModule(host)
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono) then
        LogOnce("notheme", "Theme is missing, the Hunter module is not built")
        return nil
    end
    Data = FS.HunterState
    if not (Data and Data.Shot and Data.Subscribe) then
        LogOnce("nodata", "FS.HunterState is missing, the Hunter module has no data")
        return nil
    end
    if mod then return mod end
    WU = Data.TUNING.WINDUP
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightHunter", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        local zones = Frame(mod, LEVEL.zones)
        local rim = Frame(mod, LEVEL.rim)
        local you = Frame(mod, LEVEL.you)
        local lock = Frame(mod, LEVEL.lock)
        local skull = Frame(mod, LEVEL.skull)
        local fx = Frame(mod, LEVEL.fx)
        local traps = Frame(mod, LEVEL.rim)
        local upper = Frame(mod, LEVEL.upper)
        local labels = Frame(mod, LEVEL.upper)
        BuildZones(zones)
        BuildRim(rim)
        BuildYou(you)
        BuildLock(lock)
        BuildSkull(skull)
        BuildFx(fx)
        BuildTraps(traps, upper)
        BuildLabels(labels)
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Hunter.frame, Hunter.parts, Hunter.state = mod, P, V
    if Data.Start then Data.Start() end
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
Hunter._PaintAll, Hunter._PaintTraps, Hunter._Gather = PaintAll, PaintTraps, Gather

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "HUNTER" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
