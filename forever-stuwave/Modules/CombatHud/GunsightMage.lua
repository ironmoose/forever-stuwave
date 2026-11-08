-- Forever STUwave: Gunsight Class Module for the Mage: the freeze, the stacks and the ward
--
-- The approved design is the design mockup "Mage Gunsight Module" (2026-11-07). Two watchers side by side on the mockup's
-- 150 x 86 sprite px canvas:
--   * THE SPEC PIECE (left, centred at 46, 32): it follows the talents (MageState.Spec).
--       FROST: a snowflake that is Frost Nova (bright when ready, dark and refilling from the bottom while the engine's cooldown
--         runs) with the Hagalaz rune in its small clear core, an ice crust round it while the target is Frozen from the
--         player's own Nova (the window drains clockwise, ~ marks the guess), two Fingers of Frost crystal clusters beside it, and
--         the ice spike under it (Ice Lance's cooldown, shared with Fire Blast; it shines when the target counts as Frozen or a
--         crystal is lit).
--       ARCANE: the sigil: the Eye of the Kirin Tor (shut at 0 stacks, open at 1 to 3, blazing at 4), four gems on the 18 s ring
--         (one per Arcane Blast stack; the ring never refreshes and flashes amber under 4 s), the next Blast's cost under it and a
--         Clearcasting spark.
--       FIRE: a tongue of flame that grows with Fire Vulnerability, the Kaun rune cut into its base with a molten rim, five stack
--         embers on the lower arc, the 30 s ring (each Scorch refills it), sparks off the tip and the Fire Blast comet under it.
--   * THE WARD (right, centred at 121, 31): Ice Barrier (a clear ice oval; the light inside is the absorb left, filling from the
--     bottom, a pink ring draining for the 1 minute damage buff, the oval refilling during its cooldown, amber when it may be
--     cast again in combat) or, without it, Mana Shield (a gaseous oval of arcane mist whose dense part is the absorb). Neither
--     learned: a dotted oval and L20. The label under it is the absorb left (AbbreviateNumbers) or the buff time in pink.
--
-- HOW "THERE IS LIGHT IN IT" IS DRAWN WITHOUT READING A SECRET. The absorb can never be compared, so everything that only shows
-- while the ward holds light (the lit chrome, the lit ring, the glyphs, the number) sits in one plain frame whose ALPHA is the
-- secret absorb (SetAlpha takes a secret; 0 hides it, any absorb shows it fully); it is layered over the empty and refilling
-- looks so the engine picks the right one. The light itself is a vertical StatusBar fed the secret absorb, its max the absorb
-- caught right after the player's own cast (MageState's mark). Every refill (Nova, the Lance spike, the Fire Blast comet, the
-- Ice Barrier cooldown) is a StatusBar fed the engine's cooldown duration object (ElapsedTime); a client without it shows the
-- dark look and no refill.
--
-- WHAT THE MOCKUP HAS THAT THIS BUILD DOES NOT (the client cannot do it, or not without per frame geometry):
--   * the bright row riding the Ice Barrier light's edge, and the ice glint sweep (the level is secret);
--   * the mist's slow swirl (a StatusBar cannot flip its picture): the body is still art, the vapour at its rim is a 4 frame
--     flipbook, and the ripple a hit sends through the mist is the shake and the white flash instead; no mist blow-apart;
--   * a swipe drains from the other side: a Cooldown keeps the arc from where the elapsed time ends to 12 o'clock, so the rings
--     (Frozen crust, the Arcane and Fire rings, the pink buff ring) keep their LEFT side; the art is baked as the exact mirror
--     of the mockup's. Their bright head is a 2 px marker on the moving edge;
--   * the Scorch pop does not swell the flame (the flash, the rune glow, the ring of dots and the new ember's pop stay);
--   * the Frost crust does not fall away in chips, the Ice Lance flame licks of the Fire look and the comet's loose embers are
--     not drawn, and the Ice Lance glow outline is not drawn (the mockup's dark outline covers it too); only the white flare at
--     the spike's point shines;
--   * Heating Up and Ignite are not counted (the mockup leaves them out);
--   * the labels are the house mono font, not the mockup's 3 x 5 pixel font ("~6s", not "~6S").
--
-- DATA. Everything comes from FS.MageState (MageState.lua); its ledger listens from Start() on and never stops. This file reads
-- no aura and compares no secret: secrets go straight to SetMinMaxValues / SetValue / SetAlpha / AbbreviateNumbers.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide
-- stops the OnUpdate and the subscription, onShow subscribes, refreshes and repaints. Plain frames only.
--
-- TICKER. One OnUpdate at most every C.TICK s while shown and something moves (a ready look breathes, a clock runs, a hit shakes);
-- it stops when nothing does. The tick allocates nothing: positions are numbers, texcoords and labels are written on change.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightMage = FS.GunsightMage or {}
local Mage = FS.GunsightMage

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil, sin, cos, pi, abs = math.floor, math.ceil, math.sin, math.cos, math.pi, math.abs
local IsSecret = FS.IsSecret or function() return false end

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    LABEL_Y = 74,                      -- the mockup's label row (the top of its 3 x 5 glyphs); the mono font's baseline is 5 below
    BASELINE = 5,
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    MAIN = { x = 46, y = 32 },         -- the Arcane and Fire piece centre (the mockup's MX, MY)
    FROST = { x = 40, y = 32 },        -- the Frost piece sits 6 px left to leave the Fingers crystals room
    WARD = { x = 121, y = 31 },        -- the ward centre (the mockup's SX, SY)
    COST_Y = 62,
    LABEL_SIZE = 11,
    CAP = 325 / 1024,                  -- Mononoki Bold: the line box's middle sits CAP * size above the baseline (as GunsightPriest)
    TEXT_MAX_S = 99,
    ABSORB_EVERY = 0.5,                -- s between absorb re-reads while ticking (the pings are the main path)
    COST_EVERY = 1,                    -- s between Arcane Blast cost re-reads while the Arcane piece shows
    NUDGE = 1.4, FLASH = 0.08, SHAKE = 0.12, BREAK = 0.7,
    NOVA_FLASH = 0.08, NOVA_BURST = 0.5, LANCE_FLASH = 0.1, LOW = 4, LOW_FIRE = 5,
    COMET_FRAMES = 24, COMET_FPS = 12, FLAME_FRAMES = 12, FLAME_FPS = 12, GLINT_FRAMES = 8,
    FINGERS = { { 68, 12 }, { 68, 35 } },        -- the crystal clusters' top left (11 x 11 sprite px)
    SPIKE = { x = 21, y = 64 },        -- the ice spike's (0, 0): the mockup's L0 under the Frost piece and LY
    SPIKE_BOX = { -3, -10, 40, 20 },   -- the cooling look's StatusBar box from the spike's (0, 0)
    COMET = { dx = 0 },                -- the comet cell's top left is (16 + dx, 52); dx is -6 under the Frost piece
    COMET_BOX = { 23, 52, 53, 24 },
    FLAKE_BOX = { -16, -16, 33, 33 },
    ICE_LIT = { -13, -17, 27, 35 }, ICE_CD = { -17, -17, 34, 35 }, MIST_BOX = { -15, -18, 30, 36 },
    OA = 12, OB = 17, MA = 13, MB = 18,
    BUFF_RX = 19.5, BUFF_RY = 24.5,
    GEMS = { { 0, -22 }, { 22, 0 }, { 0, 22 }, { -22, 0 } },
    CC = { x = 73, y = 14 },
    EMBER_ANGLES = { 124, 152, 180, 208, 236 },
    POP = 0.35,
    COLORS = {
        white = Hex("#ffffff"), amber = Hex("#ffb648"), muted = Hex("#9d93c4"), frostLabel = Hex("#c8faff"),
        iceLabel = Hex("#c8faff"), manaLabel = Hex("#d0c8ff"), buffLabel = Hex("#ff8ad8"), arcLabel = Hex("#e09cff"),
        fireLabel = Hex("#ffcf3a"), costCool = Hex("#c8b8ff"), costHot = Hex("#ff8ad8"), fingerMark = Hex("#9ff0ff"),
        edgeIdle = Hex("#5fd4e8"), shardBig = Hex("#d4fbff"), shardDot = Hex("#ffffff"), mote = Hex("#c8faff"),
        twinkleArm = Hex("#ffffff"), shatter = Hex("#ff5ad0"), shatterDot = Hex("#ffd0f0"), popRing = Hex("#ff8ad8"),
        ccArm = Hex("#9ff0ff"), ccBurst = Hex("#ffffff"), pupil = Hex("#ffffff"), headFrost = Hex("#ffffff"),
        headArc = Hex("#f0d0ff"), headFire = Hex("#fff3e6"), headBuff = Hex("#ffd0f0"), spikeFlare = Hex("#ffffff"),
        runeCool = Hex("#3a0614"), runeNone = Hex("#1a0410"), runeFlash = Hex("#ffffff"), runeGold = Hex("#ffcf3a"),
        rimNone = Hex("#7a2a1a"), rimHot = Hex("#ff3b1e"), rimWarm = Hex("#e0401e"), sparkA = Hex("#ffe08a"),
        sparkB = Hex("#ff5a2a"), sparkC = Hex("#c04cff"), emberHot = Hex("#fff3e6"), emberWarm = Hex("#ffcf3a"),
        emberFresh = Hex("#ffffff"), flareDot = Hex("#ffe08a"), emberPop = Hex("#ffcf3a"),
        nudge = Hex("#ffb648"), glyphLit = Hex("#ffffff"), glyphDim = Hex("#d0c8ff"), moteA = Hex("#ff8ad8"),
        moteB = Hex("#c8bcff"), starArm = Hex("#e8d8ff"), sparkHead = Hex("#ffffff"), sparkNear = Hex("#f0d0ff"),
        shardIce = Hex("#9ff0ff"), shardMana = Hex("#f0d0ff"), shardManaDot = Hex("#a855f7"), vapourTint = Hex("#ffffff"),
        wardFlash = Hex("#ffffff"), vapor = Hex("#c8faff"),
    },
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Mage.C = C
local K = C.COLORS

local SCALE = 2
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"

-- the cell maps: each is the order of the generator's list (generate_mage_*.py), checked by the harness
local FCELL = { flakeReady = 0, flakeOff = 1, flakeFlash = 2, flakeGlow = 3, haze = 4, crustDim = 5, crustIdle = 6, nova1 = 7 }
local FING = { on = 0, off = 1, glow = 2 }
local SPK = { ready = 0, off = 1, flash = 2 }
local ACELL = { ringDark = 0, eyeShut = 1, eyeOpen = 2, eyeFull = 3, glowOpen = 4, glowFull = 5, ccArms = 6, ccDiag = 7 }
local GCELL = { off = 0, on = 1, twinkle = 2, fresh = 3, pop5 = 4 }
local FIRECELL = { ringDark = 0, rune = 1, rim = 2, emberOn = 3, emberOff = 4 }
local WCELL = { buffDark = 0, buffDash = 1, iceDark = 2, edgeCd = 3, edgeEven = 4, edgeOdd = 5, spikeDark = 6, spikeMask = 7,
    upChrome = 8, iceFlash = 9, manaRingDim = 10, manaRingOff = 11, manaLocked = 12, manaCore = 13, iceCover = 14,
    manaRingMask = 15 }
local MCELL = { body = 0, vapour0 = 1, mistFlash = 5 }
local COMETCELL = { off = 24, flash = 25 }
Mage.CELL = { frost = FCELL, fingers = FING, spike = SPK, arcane = ACELL, gems = GCELL, fire = FIRECELL, ward = WCELL, mist = MCELL,
    comet = COMETCELL }

local function Atlas(file, w, h, cols, cw, ch, bw, bh, ox, oy)
    return { file = file, w = w, h = h, cols = cols, cw = cw, ch = ch, bw = bw, bh = bh, ox = ox or 32, oy = oy or ox or 32 }
end
local A = {
    frost = Atlas("mage_frost.tga", 512, 512, 4, 128, 128, 64, 64),
    glint = Atlas("mage_frost_glint.tga", 512, 256, 4, 128, 128, 64, 64),
    fingers = Atlas("mage_fingers.tga", 64, 64, 2, 32, 32, 16, 16, 2, 2),
    spike = Atlas("mage_spike.tga", 256, 128, 2, 128, 64, 64, 32, 6, 12),
    comet = Atlas("mage_comet.tga", 512, 512, 4, 128, 48, 64, 24, -16, -52),
    arcane = Atlas("mage_arcane.tga", 512, 256, 4, 128, 128, 64, 64),
    gems = Atlas("mage_arcane_gems.tga", 256, 256, 4, 64, 64, 32, 32, 16, 16),
    flame = Atlas("mage_fire_flame.tga", 1024, 512, 16, 64, 80, 32, 40, 16, 24),
    fire = Atlas("mage_fire.tga", 512, 256, 4, 128, 128, 64, 64),
    ward = Atlas("mage_ward.tga", 512, 512, 4, 128, 128, 64, 64),
    mist = Atlas("mage_ward_mist.tga", 512, 512, 4, 128, 128, 64, 64),
    glyph = Atlas("mage_ward_glyph.tga", 32, 32, 2, 16, 16, 8, 8, 4, 4),
}
Mage.A = A

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightmage_" .. key, "|cffff4488Forever STUwave|r: gunsight mage module: " .. tostring(msg))
    end
end

local Data
local mod
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc, absorbAcc, costAcc = false, false, 0, 0, 0
local P = {}                       -- every part, built once
local hitAt, breakAt = nil, nil
local abbreviateOff = false
local shownSpec, shownKind

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

local function Alpha(t, a)
    if t.fsAl == a then return end
    t.fsAl = a
    t:SetAlpha(a)
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

-- Re-seat a sprite's art point
local function SprAt(t, ax, ay)
    Place(t, ax - t.fsAtlas.ox, ay - t.fsAtlas.oy)
end

-- a flat one colour region, w x h sprite px at (x, y)
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

-- A bar's box origin moves with its piece: x, y are where the box's top left sits.
local function BarAt(bar, x, y)
    bar.fsBx, bar.fsBy = x, y
    Place(bar, x, y)
end

local function MakeSwipe(parent, level, file, cx, cy, base)
    local ok, cd = pcall(CreateFrame, "Cooldown", nil, parent)
    if not (ok and cd and cd.SetSwipeTexture and cd.SetCooldown) then return nil end
    cd:SetFrameLevel(mod:GetFrameLevel() + level)
    cd:EnableMouse(false)
    pcall(cd.SetSwipeTexture, cd, MEDIA .. file, 1, 1, 1, 1)
    if cd.SetSwipeColor then pcall(cd.SetSwipeColor, cd, 1, 1, 1, 1) end
    if cd.SetDrawEdge then pcall(cd.SetDrawEdge, cd, false) end
    if cd.SetDrawBling then pcall(cd.SetDrawBling, cd, false) end
    if cd.SetHideCountdownNumbers then pcall(cd.SetHideCountdownNumbers, cd, true) end
    if cd.SetReverse then pcall(cd.SetReverse, cd, false) end
    cd.fsBase = base or mod
    Seat(function() cd:SetSize(S(64), S(64)); Forget(cd); Place(cd, cx - 32, cy - 32) end)
    return cd
end

-- Show a swipe over [start, start + dur] (plain numbers), only writing the cooldown when it changed.
local function Swipe(cd, show, start, dur)
    On(cd, show)
    if show then
        if cd.fsStart ~= start or cd.fsDur ~= dur then
            cd.fsStart, cd.fsDur = start, dur
            pcall(cd.SetCooldown, cd, start, dur)
        end
    else
        cd.fsStart = nil
    end
end

-- a ring: the lit arc (a swipe), an optional amber twin, and a 2 px head on the sweep's moving edge. Centre cx, cy of the ring in
-- sprite px; rx, ry the head's path.
local function MakeRing(parent, level, cx, cy, file, lowFile, rx, ry, headColor, base)
    local r = { cx = cx, cy = cy, rx = rx, ry = ry }
    r.cd = MakeSwipe(parent, level, file, cx, cy, base)
    if lowFile then r.low = MakeSwipe(parent, level + 1, lowFile, cx, cy, base) end
    r.top = Frame(parent, level + 2)
    if base and base ~= mod then r.top:SetAllPoints(base) end
    r.head = Tex(r.top, "OVERLAY", 3, FLAT, 2, 2, base)
    Tint(r.head, headColor, 1)
    return r
end

local function UpdateRing(r, show, start, dur, now, low, b)
    if r.cd then Swipe(r.cd, show and not low, start, dur) end
    if r.low then
        Swipe(r.low, show and low, start, dur)
        if low then Alpha(r.low, 0.45 + 0.55 * b) end
    end
    On(r.head, show and r.cd ~= nil)
    if show and dur and dur > 0 then
        local e = (now - start) / dur
        if e < 0 then e = 0 elseif e > 1 then e = 1 end
        local a = e * 2 * pi
        Place(r.head, floor(r.cx + sin(a) * r.rx + 0.5) - 1, floor(r.cy - cos(a) * r.ry + 0.5) - 1)
    end
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- A centred label at sprite x cx, its row top at y (the mockup's glyph tops; the baseline sits C.BASELINE below).
local function Text(parent, cx, y)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("CENTER")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(C.LABEL_SIZE), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint("CENTER", mod, "TOPLEFT", S(cx), -(S(y + C.BASELINE) - ui(C.CAP * C.LABEL_SIZE)))
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
Mage.TimeLabel = TimeLabel

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end      -- 20 steps: few alpha writes
local function Round(v) return floor(v + 0.5) end

local function nz(i)
    local v = sin(i * 12.9898) * 43758.5453
    return v - floor(v)
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

-- A refill: the engine's cooldown timer into a StatusBar (the bar's texture is the lit look). Returns whether it runs. A client
-- without the elapsed time direction or the timer shows no refill.
local function Refill(bar, key, active)
    if bar.fsKey ~= key then bar.fsKey, bar.fsTimer = key, nil end
    if active and bar.fsTimer == nil then
        local obj = Data.CooldownDuration(key)
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
-- Build: the Frost piece
-------------------------------------------------------------------------------

local TIPS = { { 0, -16 }, { 11, -11 }, { 16, 0 }, { 11, 11 }, { 0, 16 }, { -11, 11 }, { -16, 0 }, { -11, -11 } }
local SHARD_SIN, SHARD_COS = {}, {}
for i = 1, 12 do
    local a = (i - 1) * pi / 6 + 0.2
    SHARD_SIN[i], SHARD_COS[i] = sin(a), cos(a)
end

local function BuildFrost()
    local fc = C.FROST
    local root = Frame(mod, 1)
    local F = { root = root }
    P.frost = F
    F.haze = Spr(root, "BACKGROUND", 0, A.frost, FCELL.haze, fc.x, fc.y)
    F.crustDim = Spr(root, "BACKGROUND", 1, A.frost, FCELL.crustDim, fc.x, fc.y)
    F.crustIdle = Spr(root, "BACKGROUND", 1, A.frost, FCELL.crustIdle, fc.x, fc.y)
    F.glow = Spr(root, "BACKGROUND", 2, A.frost, FCELL.flakeGlow, fc.x, fc.y)
    F.flake = Spr(root, "ARTWORK", 0, A.frost, FCELL.flakeOff, fc.x, fc.y)
    local bx = C.FLAKE_BOX
    F.bar = MakeBar(root, 2, "mage_flake_mid.tga", bx, true, false)
    BarAt(F.bar, fc.x + bx[1], fc.y + bx[2])
    F.crust = MakeSwipe(root, 3, "mage_crust_swipe.tga", fc.x, fc.y)
    local top = Frame(root, 4)
    F.top = top
    F.head = Flat(top, "OVERLAY", 3, 2, 2)
    Tint(F.head, K.headFrost, 1)
    F.flash = Spr(top, "ARTWORK", 0, A.frost, FCELL.flakeFlash, fc.x, fc.y)
    Tint(F.flash, K.white, 1)
    F.glint = Spr(top, "ARTWORK", 1, A.glint, 0, fc.x, fc.y)
    F.tip = Flat(top, "OVERLAY", 1, 1, 1)
    Tint(F.tip, K.white, 1)
    F.tipArms = {}
    for i = 1, 4 do F.tipArms[i] = Flat(top, "OVERLAY", 0, 1, 1) end
    F.nova = Spr(top, "ARTWORK", 2, A.frost, FCELL.nova1, fc.x, fc.y)
    F.shards = {}
    for i = 1, 12 do F.shards[i] = { big = Flat(top, "OVERLAY", 2, 2, 2), dot = Flat(top, "OVERLAY", 3, 1, 1) } end
    F.fingers = {}
    local fingerTop = Frame(root, 3)
    for i = 1, 2 do
        local p = C.FINGERS[i]
        local f = {}
        f.glow = Spr(root, "ARTWORK", 3, A.fingers, FING.glow, p[1], p[2])
        f.crystal = Spr(root, "ARTWORK", 4, A.fingers, FING.off, p[1], p[2])
        f.mote = Flat(fingerTop, "OVERLAY", 0, 1, 1)
        Tint(f.mote, K.mote, 1)
        f.twinkle = Flat(fingerTop, "OVERLAY", 1, 1, 1)
        Tint(f.twinkle, K.white, 1)
        f.burst = {}
        for j = 1, 4 do f.burst[j] = Flat(fingerTop, "OVERLAY", 2, 1, 1); Tint(f.burst[j], K.white, 1) end
        F.fingers[i] = f
    end
    F.fingerMark = Text(root, 74, C.LABEL_Y)
    F.label = Text(root, fc.x, C.LABEL_Y)
end

-------------------------------------------------------------------------------
-- Build: the marks (the ice spike and the Fire Blast comet)
-------------------------------------------------------------------------------

-- the spike's top edge row by column (generate_mage_mark.py SP_TOP), for the sparkle that runs along it
local SP_TOP = { 3, 5, 6, 6, 6, 5, 6, 6, 5, 5, 6, 5, 5, 4, 4, 5, 4, 4, 3, 3, 4, 3, 3, 2, 2, 3, 2, 2, 1, 2, 1, 1, 1, 0, 0, 0 }
local LEN = #SP_TOP
local SPUR = { { 9, -6 }, { 10, -7 }, { 11, -8 }, { 19, -5 }, { 20, -6 }, { 27, -3 }, { 28, -4 } }
local LTOP = {}
for x = 0, LEN - 1 do LTOP[#LTOP + 1] = { x, -SP_TOP[x + 1] } end
for i = 1, #SPUR do LTOP[#LTOP + 1] = SPUR[i] end
local VAPOUR_X = { 4, 12, 17, 24 }

local function BuildMarks()
    local sp, bx = C.SPIKE, C.SPIKE_BOX
    local ms = Frame(mod, 1)
    local M = { spikeRoot = ms }
    P.marks = M
    M.spike = Spr(ms, "ARTWORK", 0, A.spike, SPK.off, sp.x, sp.y)
    M.spikeBar = MakeBar(ms, 2, "mage_spike_mid.tga", bx, false, true)
    BarAt(M.spikeBar, sp.x + bx[1], sp.y + bx[2])
    local top = Frame(ms, 3)
    M.spikeFlash = Spr(top, "ARTWORK", 0, A.spike, SPK.flash, sp.x, sp.y)
    M.flare = {}
    for i = 1, 4 do M.flare[i] = Flat(top, "OVERLAY", 0, 1, 1); Tint(M.flare[i], K.spikeFlare, 1) end
    M.sparkle = Flat(top, "OVERLAY", 1, 1, 1)
    Tint(M.sparkle, K.white, 1)
    M.sparkle2 = Flat(top, "OVERLAY", 1, 1, 1)
    M.vapour = {}
    for i = 1, 4 do M.vapour[i] = { a = Flat(top, "OVERLAY", 0, 1, 1), b = Flat(top, "OVERLAY", 0, 1, 1) } end
    local mc = Frame(mod, 1)
    M.cometRoot = mc
    M.comet = Spr(mc, "ARTWORK", 0, A.comet, COMETCELL.off, 0, 0)
    local cb = C.COMET_BOX
    M.cometBar = MakeBar(mc, 2, "mage_comet_mid.tga", cb, false, false)
    local ctop = Frame(mc, 3)
    M.cometFlash = Spr(ctop, "ARTWORK", 0, A.comet, COMETCELL.flash, 0, 0)
    M.cometDX = nil
end

-- the comet's cell top left is screen (16, 52) at the main piece centre; dx moves it under the Frost piece
local function SeatComet(dx)
    local M = P.marks
    if M.cometDX == dx then return end
    M.cometDX = dx
    SprAt(M.comet, dx, 0)
    SprAt(M.cometFlash, dx, 0)
    local cb = C.COMET_BOX
    BarAt(M.cometBar, cb[1] + dx, cb[2])
end

-------------------------------------------------------------------------------
-- Build: the Arcane piece
-------------------------------------------------------------------------------

local function BuildArcane()
    local mc = C.MAIN
    local root = Frame(mod, 1)
    local R = { root = root }
    P.arcane = R
    Spr(root, "BACKGROUND", 0, A.arcane, ACELL.ringDark, mc.x, mc.y)
    R.ring = MakeRing(root, 2, mc.x, mc.y, "mage_arcane_ring.tga", "mage_arcane_ring_low.tga", 21.5, 21.5, K.headArc)
    R.glow = Spr(root, "ARTWORK", 0, A.arcane, ACELL.glowOpen, mc.x, mc.y)
    R.eye = Spr(root, "ARTWORK", 1, A.arcane, ACELL.eyeShut, mc.x, mc.y)
    local top = Frame(root, 5)
    R.pupil = Flat(top, "OVERLAY", 0, 2, 2)
    Tint(R.pupil, K.pupil, 1)
    R.tip = Flat(top, "OVERLAY", 0, 2, 2)
    Tint(R.tip, K.pupil, 1)
    Place(R.pupil, mc.x - 1, mc.y - 3)
    Place(R.tip, mc.x - 1, mc.y + 11)
    R.gems = {}
    -- the gems sit over the ring (the mockup draws them last), under the pupil and the pop layer
    local gemLayer = Frame(root, 4)
    for i = 1, 4 do
        local g = C.GEMS[i]
        local gx, gy = mc.x + g[1], mc.y + g[2]
        local t = {}
        t.base = Spr(gemLayer, "ARTWORK", 2, A.gems, GCELL.off, gx, gy)
        t.twinkle = Spr(top, "ARTWORK", 0, A.gems, GCELL.twinkle, gx, gy)
        t.fresh = Spr(top, "ARTWORK", 1, A.gems, GCELL.fresh, gx, gy)
        t.pop = Spr(top, "ARTWORK", 2, A.gems, GCELL.pop5, gx, gy)
        Tint(t.pop, K.white, 1)
        local sx, sy = (g[1] > 0 and 1 or (g[1] < 0 and -1 or 0)), (g[2] > 0 and 1 or (g[2] < 0 and -1 or 0))
        -- the pop flare: a 1 x 5 (or 5 x 1) white line from 16 to 20 px out toward the centre
        t.flare = Flat(top, "OVERLAY", 1, (sx ~= 0) and 5 or 1, (sy ~= 0) and 5 or 1)
        Tint(t.flare, K.white, 1)
        t.fx = (sx ~= 0) and (sx > 0 and mc.x + 16 or mc.x - 20) or mc.x
        t.fy = (sy ~= 0) and (sy > 0 and mc.y + 16 or mc.y - 20) or mc.y
        Place(t.flare, t.fx, t.fy)
        R.gems[i] = t
    end
    R.shatter = {}
    for i = 1, 16 do
        R.shatter[i] = { big = Flat(top, "OVERLAY", 2, 2, 1), dot = Flat(top, "OVERLAY", 3, 1, 1) }
        Tint(R.shatter[i].big, K.shatter, 1)
        Tint(R.shatter[i].dot, K.shatterDot, 1)
    end
    local cc = C.CC
    R.ccArms = Spr(top, "ARTWORK", 3, A.arcane, ACELL.ccArms, cc.x, cc.y)
    R.ccDiag = Spr(top, "ARTWORK", 3, A.arcane, ACELL.ccDiag, cc.x, cc.y)
    Tint(R.ccDiag, K.white, 1)
    R.ccCore = Flat(top, "OVERLAY", 4, 1, 1)
    Tint(R.ccCore, K.white, 1)
    Place(R.ccCore, cc.x, cc.y)
    R.ccBurst = {}
    for i = 1, 4 do R.ccBurst[i] = Flat(top, "OVERLAY", 4, 1, 1); Tint(R.ccBurst[i], K.ccBurst, 1) end
    R.cost = Text(root, mc.x, C.COST_Y)
    R.label = Text(root, mc.x, C.LABEL_Y)
end

-------------------------------------------------------------------------------
-- Build: the Fire piece
-------------------------------------------------------------------------------

local EMBERS = {}
for i, d in ipairs(C.EMBER_ANGLES) do
    local a = d * pi / 180
    EMBERS[i] = { Round(sin(a) * 17), Round(-cos(a) * 17) }
end
local NZ_A, NZ_B, NZ_C = {}, {}, {}      -- the spark hashes, one set per spark (up to 12)
for i = 0, 11 do NZ_A[i], NZ_B[i], NZ_C[i] = 0.6 + nz(i * 5.1) * 0.7, nz(i * 2.3), nz(i) end
-- the Kaun rune and its rim sit at this row (MY + KY[n]) of the flame's base, by stack count n (the mockup's ky at bob 0)
local KY = {}
for n = 0, 5 do
    local Rb = (n == 0) and 3.5 or (5.5 + n * 0.55)
    local m = Rb * 0.8
    if m < 4 then m = 4 end
    KY[n] = Round(13 - m)
end
Mage.KY = KY

local function BuildFire()
    local mc = C.MAIN
    local root = Frame(mod, 1)
    local Fi = { root = root }
    P.fire = Fi
    Spr(root, "BACKGROUND", 0, A.fire, FIRECELL.ringDark, mc.x, mc.y)
    Fi.ring = MakeRing(root, 2, mc.x, mc.y, "mage_fire_ring.tga", "mage_fire_ring_low.tga", 21, 21, K.headFire)
    Fi.flame = Spr(root, "ARTWORK", 0, A.flame, 0, mc.x, mc.y)
    Fi.rim = Spr(root, "ARTWORK", 1, A.fire, FIRECELL.rim, mc.x, mc.y)
    Fi.rune = Spr(root, "ARTWORK", 2, A.fire, FIRECELL.rune, mc.x, mc.y)
    Fi.sparks = {}
    for i = 0, 11 do Fi.sparks[i] = Flat(root, "OVERLAY", 0, 1, 1) end
    Fi.flareDots = {}
    for i = 1, 16 do Fi.flareDots[i] = Flat(root, "OVERLAY", 1, 1, 1); Tint(Fi.flareDots[i], K.flareDot, 1) end
    Fi.embers = {}
    for i = 1, 5 do
        local e = EMBERS[i]
        local t = {}
        t.socket = Spr(root, "ARTWORK", 3, A.fire, FIRECELL.emberOff, mc.x + e[1], mc.y + e[2])
        t.core = Flat(root, "OVERLAY", 2, 1, 1)
        Place(t.core, mc.x + e[1], mc.y + e[2])
        t.pop = {}
        for j = 1, 4 do t.pop[j] = Flat(root, "OVERLAY", 2, 1, 1); Tint(t.pop[j], K.emberPop, 1) end
        Fi.embers[i] = t
    end
    Fi.label = Text(root, mc.x, C.LABEL_Y)
end

-------------------------------------------------------------------------------
-- Build: the ward
-------------------------------------------------------------------------------

local GLYPH_COUNT = 6
local MOTE_X = { -6, -2, 3, 7 }
local SPARKLE_X = { -7, 6, -4, 8, -9, 3, 0 }
local SPARKLE_Y = { -10, -6, 8, 2, -2, 12, -13 }
local WSHARDS = { { -11, -14, -1.2, -0.6 }, { 11, -11, 1.3, -0.4 }, { -12, 2, -1, 0.3 }, { 12, 5, 1.1, 0.5 }, { -3, -6, -0.3, 1 },
    { 4, -17, 0.6, -1 }, { -7, 13, -0.6, 0.8 }, { 7, 15, 0.7, 0.7 }, { 0, 8, 0.1, 0.9 }, { -2, -15, -0.4, -0.9 } }
Mage.WSHARDS = WSHARDS

-- the glint and motes ride only the lit part: a frame from the light's top edge down, clipping its children
local function MakeClip(parent, bar, base, level)
    local clip = CreateFrame("Frame", nil, parent)
    clip:SetFrameLevel(mod:GetFrameLevel() + level)
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
        clip:SetAllPoints(base)
        LogOnce("noclip", "the lit motes are not clipped to the light on this client")
    end
    return clip
end

local function BuildWard()
    local wc = C.WARD
    local wf = CreateFrame("Frame", nil, mod)
    wf:SetFrameLevel(mod:GetFrameLevel() + 1)
    wf:SetSize(1, 1)
    wf:EnableMouse(false)
    Seat(function() wf:SetSize(ui(C.W), ui(C.H)); local x = wf.fsX; wf.fsX = nil; if x then P.ShakeTo(x) end end)
    local W = { root = wf }
    P.ward = W
    function P.ShakeTo(dx)
        if wf.fsX == dx then return end
        wf.fsX = dx
        wf:ClearAllPoints()
        wf:SetPoint("TOPLEFT", mod, "TOPLEFT", S(dx), 0)
    end
    P.ShakeTo(0)
    local function Sub(level)
        local f = CreateFrame("Frame", nil, wf)
        f:SetFrameLevel(mod:GetFrameLevel() + level)
        f:SetAllPoints(wf)
        f:EnableMouse(false)
        return f
    end
    -- the locked look
    W.locked = Spr(wf, "BACKGROUND", 0, A.ward, WCELL.manaLocked, wc.x, wc.y, wf)

    -- the Ice Barrier, bottom to top: buff ring, dark shell and its empty looks, the cooldown refill, then (under the absorb
    -- gate) the cover and lit chrome, the light, the flash
    local ice = Sub(1)
    W.ice = ice
    W.buffDark = Spr(ice, "BACKGROUND", 0, A.ward, WCELL.buffDark, wc.x, wc.y, wf)
    W.buffDash = Spr(ice, "BACKGROUND", 0, A.ward, WCELL.buffDash, wc.x, wc.y, wf)
    W.buffRing = MakeRing(ice, 2, wc.x, wc.y, "mage_ward_buff.tga", nil, C.BUFF_RX, C.BUFF_RY, K.headBuff, wf)
    W.iceDark = Spr(ice, "ARTWORK", 0, A.ward, WCELL.iceDark, wc.x, wc.y, wf)
    W.spikeDark = Spr(ice, "ARTWORK", 1, A.ward, WCELL.spikeDark, wc.x, wc.y, wf)
    W.spikeNudge = Spr(ice, "ARTWORK", 1, A.ward, WCELL.spikeMask, wc.x, wc.y, wf)
    W.edgeCd = Spr(ice, "ARTWORK", 2, A.ward, WCELL.edgeCd, wc.x, wc.y, wf)
    W.edgeEven = Spr(ice, "ARTWORK", 2, A.ward, WCELL.edgeEven, wc.x, wc.y, wf)
    W.edgeOdd = Spr(ice, "ARTWORK", 3, A.ward, WCELL.edgeOdd, wc.x, wc.y, wf)
    local cb = C.ICE_CD
    W.cdBar = MakeBar(ice, 3, "mage_ice_cd.tga", cb, true, false, wf)
    BarAt(W.cdBar, wc.x + cb[1], wc.y + cb[2])
    local iceGate = Sub(4)
    W.iceGate = iceGate
    W.iceCover = Spr(iceGate, "ARTWORK", 0, A.ward, WCELL.iceCover, wc.x, wc.y, wf)
    W.upChrome = Spr(iceGate, "ARTWORK", 1, A.ward, WCELL.upChrome, wc.x, wc.y, wf)
    local lb = C.ICE_LIT
    W.iceBar = MakeBar(iceGate, 5, "mage_ice_lit.tga", lb, true, false, wf)
    BarAt(W.iceBar, wc.x + lb[1], wc.y + lb[2])
    W.iceClip = MakeClip(iceGate, W.iceBar, wf, 6)
    W.iceMotes = {}
    for i = 1, 4 do W.iceMotes[i] = Flat(W.iceClip, "OVERLAY", 0, 1, 1, wf); Tint(W.iceMotes[i], K.white, 1) end
    W.flashIce = Spr(iceGate, "OVERLAY", 2, A.ward, WCELL.iceFlash, wc.x, wc.y, wf)
    Tint(W.flashIce, K.white, 1)
    W.iceLabel = Text(iceGate, wc.x, C.LABEL_Y)

    -- the Mana Shield: the dotted ring when empty, and under the absorb gate the dim ring, the thin veil, the vapour, the dense
    -- band (a StatusBar), the glyphs, the core and the motes
    local mana = Sub(1)
    W.mana = mana
    W.manaOff = Spr(mana, "BACKGROUND", 0, A.ward, WCELL.manaRingOff, wc.x, wc.y, wf)
    local mg = Sub(4)
    W.manaGate = mg
    W.manaBody = Spr(mg, "BACKGROUND", 0, A.mist, MCELL.body, wc.x, wc.y, wf)
    W.vapour = Spr(mg, "BACKGROUND", 1, A.mist, MCELL.vapour0, wc.x, wc.y, wf)
    W.manaDim = Spr(mg, "ARTWORK", 0, A.ward, WCELL.manaRingDim, wc.x, wc.y, wf)       -- the thin ring is drawn over the mist
    local mb = C.MIST_BOX
    W.mistBar = MakeBar(mg, 5, "mage_mist_dense.tga", mb, true, false, wf)
    BarAt(W.mistBar, wc.x + mb[1], wc.y + mb[2])
    W.glyphDim = {}
    for i = 1, GLYPH_COUNT do
        local g = Spr(mg, "ARTWORK", 0, A.glyph, (i - 1) % 4, wc.x, wc.y, wf)
        Tint(g, K.glyphDim, 1)
        W.glyphDim[i] = g
    end
    W.mistClip = MakeClip(mg, W.mistBar, wf, 6)
    W.glyphLit = {}
    for i = 1, GLYPH_COUNT do
        local g = Spr(W.mistClip, "ARTWORK", 0, A.glyph, (i - 1) % 4, wc.x, wc.y, wf)
        Tint(g, K.glyphLit, 1)
        W.glyphLit[i] = g
    end
    -- the top layer is a child of the gate too: the core, the sparks and the number show only while the shield holds light
    local mtop = CreateFrame("Frame", nil, mg)
    mtop:SetFrameLevel(mod:GetFrameLevel() + 7)
    mtop:SetAllPoints(wf)
    mtop:EnableMouse(false)
    W.manaTop = mtop
    W.core = Spr(mtop, "ARTWORK", 0, A.ward, WCELL.manaCore, wc.x, wc.y, wf)
    W.sparkHead = {}
    for i = 1, 3 do W.sparkHead[i] = Flat(mtop, "OVERLAY", 0, 1, 1, wf) end
    W.manaMotes = {}
    for i = 1, 5 do W.manaMotes[i] = Flat(mtop, "OVERLAY", 0, 1, 1, wf) end
    W.star = Flat(mtop, "OVERLAY", 1, 1, 1, wf)
    Tint(W.star, K.white, 1)
    W.starArms = {}
    for i = 1, 4 do W.starArms[i] = Flat(mtop, "OVERLAY", 0, 1, 1, wf); Tint(W.starArms[i], K.starArm, 1) end
    W.flashMist = Spr(mtop, "OVERLAY", 2, A.mist, MCELL.mistFlash, wc.x, wc.y, wf)
    Tint(W.flashMist, K.white, 1)
    W.manaLabel = Text(mtop, wc.x, C.LABEL_Y)

    W.shards = {}
    local sf = Sub(8)
    for i = 1, 10 do W.shards[i] = { big = Flat(sf, "OVERLAY", 3, 2, 2, wf), dot = Flat(sf, "OVERLAY", 4, 1, 1, wf) } end
    W.buffLabel = Text(mod, wc.x, C.LABEL_Y)
    W.lockLabel = Text(mod, wc.x, C.LABEL_Y)
end

-------------------------------------------------------------------------------
-- Paint: the marks
-------------------------------------------------------------------------------

-- Returns true while the mark moves.
local function PaintMarks(now, combat, kind, spec)
    local M = P.marks
    local isLance, isComet = kind == "lance", kind == "comet"
    On(M.spikeRoot, isLance)
    On(M.cometRoot, isComet)
    if not kind then return false end
    local key = isLance and "lance" or "fireblast"
    local cooling = Data.Cooling(key) == true
    local since = Data.CastAt("mark")
    local flash = since ~= nil and now - since < C.LANCE_FLASH
    local moving = cooling or flash
    if isLance then
        CellOf(M.spike, A.spike, cooling and SPK.off or SPK.ready)
        local run = Refill(M.spikeBar, key, cooling)
        On(M.spikeFlash, flash)
        local fz, fo = Data.Frozen(), Data.Fingers()
        local shine = not cooling and combat and ((fz.up and fz.expires and fz.expires > now) or fo.n > 0)
        local b = shine and Stepped(Beat(now, 0.7)) or 0
        local sp = C.SPIKE
        for i = 1, 4 do On(M.flare[i], shine) end
        if shine then
            Place(M.flare[1], sp.x - 3, sp.y); Tint(M.flare[1], K.spikeFlare, 0.5 + 0.5 * b)
            Place(M.flare[2], sp.x - 4, sp.y); Tint(M.flare[2], K.spikeFlare, 0.3 * b)
            Place(M.flare[3], sp.x - 2, sp.y - 2); Tint(M.flare[3], K.spikeFlare, 0.6 * b)
            Place(M.flare[4], sp.x - 2, sp.y + 2); Tint(M.flare[4], K.spikeFlare, 0.6 * b)
            moving = true
        end
        -- the ready spike: a sparkle running along its top and cold vapour curling up
        local ready = not cooling and not run
        On(M.sparkle, ready)
        On(M.sparkle2, ready)
        for i = 1, 4 do On(M.vapour[i].a, ready); On(M.vapour[i].b, ready) end
        if ready then
            moving = true
            local gi = floor(now / 0.12) % (#LTOP + 20)
            local q = LTOP[gi + 1]
            On(M.sparkle, q ~= nil)
            On(M.sparkle2, q ~= nil)
            if q then
                local x = sp.x + (LEN - 1) - q[1]
                Place(M.sparkle, x, sp.y + q[2])
                Place(M.sparkle2, x, sp.y + q[2] - 1)
                Tint(M.sparkle2, K.white, 0.5)
            end
            for i = 1, 4 do
                local ph = (now * 0.5 + (i - 1) * 0.25) % 1
                local bxp = VAPOUR_X[i]
                local top = -SP_TOP[bxp + 1] - 1
                local x = bxp + Round(sin(ph * 6 + (i - 1)) * 1.5)
                local y = top - Round(ph * 6)
                local v = M.vapour[i]
                Place(v.a, sp.x + (LEN - 1) - x, sp.y + y)
                Tint(v.a, K.vapor, Stepped(0.55 * (1 - ph)))
                On(v.b, ph < 0.4)
                if ph < 0.4 then
                    Place(v.b, sp.x + (LEN - 1) - (x + 1), sp.y + y)
                    Tint(v.b, K.vapor, Stepped(0.25 * (1 - ph)))
                end
            end
        end
        return moving
    end
    -- the comet
    SeatComet(spec == "FROST" and -6 or 0)
    if cooling then
        CellOf(M.comet, A.comet, COMETCELL.off)
    else
        CellOf(M.comet, A.comet, floor(now * C.COMET_FPS) % C.COMET_FRAMES)
        moving = true
    end
    Refill(M.cometBar, key, cooling)
    On(M.cometFlash, flash)
    return moving
end

-------------------------------------------------------------------------------
-- Paint: the Frost piece
-------------------------------------------------------------------------------

local function PaintFrost(now, combat)
    local F = P.frost
    local fc = C.FROST
    local novaKnown = Data.Known("nova") == true
    local cooling = novaKnown and Data.Cooling("nova") == true
    local ready = novaKnown and not cooling
    local fz = Data.Frozen()
    local frozenRem = fz.up and fz.expires and (fz.expires - now) or nil
    local frozen = frozenRem ~= nil and frozenRem > 0
    local novaAt = Data.CastAt("nova")
    local since = novaAt and (now - novaAt) or nil
    local flashing = since ~= nil and since < C.NOVA_FLASH
    local moving = cooling or frozen or (since ~= nil and since < C.NOVA_BURST)

    -- the flake: bright when ready, dark and refilling while the cooldown runs; dim when Frost Nova is not learned
    CellOf(F.flake, A.frost, ready and FCELL.flakeReady or FCELL.flakeOff)
    Alpha(F.flake, novaKnown and 1 or 0.45)
    local b = Beat(now, 2.4)
    On(F.glow, ready and combat)
    if ready and combat then Alpha(F.glow, Stepped((0.10 + 0.08 * b) / 0.18)) end
    Refill(F.bar, "nova", cooling)
    On(F.flash, flashing)

    -- the twinkle and the glint through the arms (ready only)
    On(F.tip, ready)
    for i = 1, 4 do On(F.tipArms[i], ready) end
    if ready then
        moving = true
        local i = floor(now / 0.45) % 8
        local tp = TIPS[(i * 3) % 8 + 1]
        local a = 1 - ((now % 0.45) / 0.45)
        Place(F.tip, fc.x + tp[1], fc.y + tp[2])
        local arm = Stepped(0.6 * a)
        for j = 1, 4 do
            local dx = (j == 1 and 1) or (j == 2 and -1) or 0
            local dy = (j == 3 and 1) or (j == 4 and -1) or 0
            Place(F.tipArms[j], fc.x + tp[1] + dx, fc.y + tp[2] + dy)
            Tint(F.tipArms[j], K.twinkleArm, arm)
        end
        local gp = (now % 3.4) / 0.6
        On(F.glint, gp < 1)
        if gp < 1 then CellOf(F.glint, A.glint, floor(gp * C.GLINT_FRAMES)) end
    else
        On(F.glint, false)
    end

    -- the burst: shards and the ring that flies out when Nova is cast
    local burst = since ~= nil and since < C.NOVA_BURST
    On(F.nova, burst)
    for i = 1, 12 do On(F.shards[i].big, burst); On(F.shards[i].dot, burst) end
    if burst then
        local k = since / C.NOVA_BURST
        local ring = floor(k * 6)
        if ring > 5 then ring = 5 end
        CellOf(F.nova, A.frost, FCELL.nova1 + ring)
        Alpha(F.nova, Stepped(0.7 * (1 - k)))
        local fade = Stepped(1 - k)
        local r = 8 + k * 24
        for i = 1, 12 do
            local s = F.shards[i]
            local x, y = fc.x + Round(SHARD_SIN[i] * r), fc.y + Round(-SHARD_COS[i] * r)
            Place(s.big, x, y); Place(s.dot, x, y)
            Tint(s.big, K.shardBig, fade); Tint(s.dot, K.shardDot, fade)
        end
    end

    -- the crust: the Frozen window from the player's own Nova, draining; a faint frame when idle
    On(F.crustIdle, not frozen)
    On(F.crustDim, frozen)
    On(F.haze, frozen)
    if frozen then
        Alpha(F.haze, Stepped((0.18 + 0.12 * Beat(now, 2.2)) / 0.30))
        if F.crust then Swipe(F.crust, true, fz.expires - Data.TUNING.FROZEN, Data.TUNING.FROZEN) end
        local e = (now - (fz.expires - Data.TUNING.FROZEN)) / Data.TUNING.FROZEN
        if e < 0 then e = 0 elseif e > 1 then e = 1 end
        local a = e * 2 * pi
        On(F.head, F.crust ~= nil)
        Place(F.head, fc.x + Round(sin(a) * 19.5) - 1, fc.y + Round(-cos(a) * 19.5) - 1)
        Label(F.label, TimeLabel(frozenRem, true), K.frostLabel)
    else
        if F.crust then Swipe(F.crust, false) end
        On(F.head, false)
        Label(F.label, "")
    end

    -- Fingers of Frost: two crystal clusters (the guess, "~" in combat)
    local fo = Data.Fingers()
    local show = Data.Talented()
    local sinceProc = fo.at and (now - fo.at) or nil
    for i = 1, 2 do
        local f = F.fingers[i]
        local p = C.FINGERS[i]
        local lit = show and i <= fo.n
        On(f.glow, show and lit)
        On(f.crystal, show)
        On(f.mote, lit)
        On(f.twinkle, false)
        for j = 1, 4 do On(f.burst[j], false) end
        if show then
            CellOf(f.crystal, A.fingers, lit and FING.on or FING.off)
            if lit then
                moving = true
                Alpha(f.glow, Stepped((0.18 + 0.3 * Stepped(Beat(now + (i - 1) * 0.35, 1.3))) / 0.48))
                local ph = (now * 0.6 + (i - 1) * 0.5) % 1
                Place(f.mote, p[1] + 4 + Round(sin(ph * 7)), p[2] - 1 - Round(ph * 5))
                Tint(f.mote, K.mote, Stepped(0.7 * (1 - ph)))
                local tw = floor(now / 0.5 + (i - 1)) % 3 == 0
                On(f.twinkle, tw)
                if tw then Place(f.twinkle, p[1] + 4, p[2]) end
                if sinceProc and sinceProc < 0.45 then
                    local k = sinceProc / 0.45
                    local r = Round(3 + k * 6)
                    local cx, cy = p[1] + 5, p[2] + 5
                    local a = Stepped(1 - k)
                    for j = 1, 4 do
                        local dx = (j == 3 and -r) or (j == 4 and r) or 0
                        local dy = (j == 1 and -r) or (j == 2 and r) or 0
                        On(f.burst[j], true)
                        Place(f.burst[j], cx + dx, cy + dy)
                        Tint(f.burst[j], K.ccBurst, a)
                    end
                end
            end
        end
    end
    On(F.fingerMark, show and fo.n > 0 and fo.est == true)
    if show and fo.n > 0 and fo.est == true then Label(F.fingerMark, "~", K.fingerMark) end
    return moving
end

-------------------------------------------------------------------------------
-- Paint: the Arcane piece
-------------------------------------------------------------------------------

local function PaintArcane(now, combat)
    local R = P.arcane
    local mc = C.MAIN
    local a = Data.Arcane()
    local n = a.stacks
    local full = n >= Data.TUNING.ARCANE_STACKS
    local rem = (n > 0 and a.expires) and (a.expires - now) or nil
    local low = rem ~= nil and rem > 0 and rem < C.LOW
    local b = low and Stepped(Beat(now, 0.5)) or 0
    local moving = false

    UpdateRing(R.ring, n > 0 and rem ~= nil and rem > 0, (a.expires or 0) - Data.TUNING.ARCANE_DURATION,
        Data.TUNING.ARCANE_DURATION, now, low, b)
    if low then moving = true end

    -- the Eye: shut at 0, open at 1 to 3, blazing at 4
    local pulse = full and Stepped(Beat(now, 0.8)) or 0
    CellOf(R.eye, A.arcane, n == 0 and ACELL.eyeShut or (full and ACELL.eyeFull or ACELL.eyeOpen))
    On(R.glow, n > 0)
    if n > 0 then
        CellOf(R.glow, A.arcane, full and ACELL.glowFull or ACELL.glowOpen)
        Alpha(R.glow, full and Stepped((0.15 + 0.3 * pulse) / 0.45) or 1)
    end
    On(R.pupil, full)
    On(R.tip, full)
    if full then
        moving = true
        Tint(R.pupil, K.pupil, 0.75 + 0.25 * pulse)
        Tint(R.tip, K.pupil, 0.6 + 0.4 * pulse)
    end

    -- the gems
    local popT = a.popAt and (now - a.popAt) or nil
    local pop = popT ~= nil and popT < C.POP and n > 0
    local twinkle = full and (floor(now / 0.25) % 4) or -1
    for i = 1, 4 do
        local g = R.gems[i]
        local on = i <= n
        CellOf(g.base, A.gems, on and GCELL.on or GCELL.off)
        local freshest = pop and on and i == n
        On(g.twinkle, on and twinkle == i - 1)
        On(g.fresh, freshest and popT < 0.12)
        On(g.pop, freshest)
        On(g.flare, freshest)
        if freshest then
            local k = popT / C.POP
            local r = Round(5 + k * 5)
            CellOf(g.pop, A.gems, GCELL.pop5 + (r - 5))
            Alpha(g.pop, Stepped(1 - k))
            Alpha(g.flare, Stepped(1 - k))
            moving = true
        end
    end
    if n > 0 then moving = true end                 -- the label counts and the stacks run out on the ticker

    -- the shatter at expiry
    local shT = a.shatterAt and (now - a.shatterAt) or nil
    local shatter = shT ~= nil and shT < 0.8
    for i = 1, 16 do On(R.shatter[i].big, shatter); On(R.shatter[i].dot, shatter) end
    if shatter then
        moving = true
        local k = shT / 0.8
        local fade = Stepped(1 - k)
        for gi = 1, 4 do
            local g = C.GEMS[gi]
            for j = 1, 4 do
                local vx = (j % 2 == 1) and -1 or 1
                local vy = (j <= 2) and -1 or 1
                local s = R.shatter[(gi - 1) * 4 + j]
                local x, y = mc.x + Round(g[1] + vx * k * 8), mc.y + Round(g[2] + vy * k * 5 + k * k * 12)
                Place(s.big, x, y); Place(s.dot, x, y)
                Alpha(s.big, fade); Alpha(s.dot, fade)
            end
        end
    end

    -- Clearcasting
    local cc = Data.Clearcasting()
    local spark = cc.up and true or false
    On(R.ccArms, spark); On(R.ccDiag, spark); On(R.ccCore, spark)
    for i = 1, 4 do On(R.ccBurst[i], false) end
    if spark then
        moving = true
        local cb = Stepped(Beat(now, 0.9))
        Alpha(R.ccArms, 0.55 + 0.45 * cb)
        Alpha(R.ccDiag, 0.5 * cb)
        local cT = cc.at and (now - cc.at) or nil
        if cT and cT < 0.4 then
            local k = cT / 0.4
            local r = Round(4 + k * 5)
            local x0, y0 = C.CC.x, C.CC.y
            for i = 1, 4 do
                local dx = (i == 3 and -r) or (i == 4 and r) or 0
                local dy = (i == 1 and -r) or (i == 2 and r) or 0
                On(R.ccBurst[i], true)
                Place(R.ccBurst[i], x0 + dx, y0 + dy)
                Tint(R.ccBurst[i], K.ccBurst, Stepped(1 - k))
            end
        end
    end

    -- the next Blast's cost and the time left
    local cost = Data.BlastCost()
    On(R.cost, cost ~= nil)
    if cost ~= nil then
        if R.fsCost ~= cost then R.fsCost = cost; R.fsCostText = tostring(cost) end
        Label(R.cost, R.fsCostText, cost >= Data.TUNING.COST_SOON and K.costHot or K.costCool)
    end
    if n > 0 and rem and rem > 0 then
        Label(R.label, TimeLabel(rem, a.est), low and K.amber or K.arcLabel)
    else
        Label(R.label, "")
    end
    return moving
end

-------------------------------------------------------------------------------
-- Paint: the Fire piece
-------------------------------------------------------------------------------

local function PaintFire(now, combat)
    local Fi = P.fire
    local mc = C.MAIN
    local f = Data.Fire()
    local n = f.stacks
    local rem = (n > 0 and f.expires) and (f.expires - now) or nil
    local low = rem ~= nil and rem > 0 and rem < C.LOW_FIRE
    local b = low and Stepped(Beat(now, 0.5)) or 0
    UpdateRing(Fi.ring, n > 0 and rem ~= nil and rem > 0, (f.expires or 0) - Data.TUNING.FIRE_DURATION, Data.TUNING.FIRE_DURATION,
        now, low, b)

    -- the flame: stack count n, frame f of the loop, lifted by the bob row
    local fr = floor(now * C.FLAME_FPS) % C.FLAME_FRAMES
    local bob = floor(sin(now * 1.7) + 0.5)
    CellOf(Fi.flame, A.flame, n * C.FLAME_FRAMES + fr)
    SprAt(Fi.flame, mc.x, mc.y + bob)
    local ky = mc.y + KY[n] + bob
    SprAt(Fi.rune, mc.x, ky)
    SprAt(Fi.rim, mc.x, ky)

    -- the Scorch pop: the rune glows white then gold, a ring of dots flies out, the new ember pops
    local popT = f.popAt and (now - f.popAt) or nil
    local flare = (popT ~= nil and popT < C.POP and n > 0) and (1 - popT / C.POP) or 0
    local rune = flare > 0.3 and K.runeFlash or (flare > 0 and K.runeGold or (n == 0 and K.runeNone or K.runeCool))
    Tint(Fi.rune, rune, 1)
    local bt = 0.5 + 0.5 * sin(now * 4)
    Tint(Fi.rim, n == 0 and K.rimNone or (bt > 0.5 and K.rimHot or K.rimWarm), 1)

    -- sparks off the tip
    local cnt = n == 0 and 1 or 2 + n * 2
    local H = (n == 0 and 9 or 16 + n * 2.6)
    local bottom = 13 + bob
    for i = 0, 11 do
        local s = Fi.sparks[i]
        On(s, i < cnt)
        if i < cnt then
            local ph = (now * NZ_A[i] + NZ_B[i]) % 1
            local x = Round(sin(i * 2.1 + ph * 6) * (1.5 + 3 * NZ_C[i]))
            local y = Round(bottom - H * 0.75 - ph * 12)
            Place(s, mc.x + x, mc.y + y)
            Tint(s, ph < 0.35 and K.sparkA or (ph < 0.7 and K.sparkB or K.sparkC), Stepped(1 - ph))
        end
    end
    local dotsOn = flare > 0
    for i = 1, 16 do On(Fi.flareDots[i], dotsOn) end
    if dotsOn then
        local Rb = (n == 0 and 3.5 or 5.5 + n * 0.55) + flare
        local r = Round(Rb + 2 + (1 - flare) * 6)
        for i = 1, 16 do
            local a = (i - 1) / 16 * 2 * pi
            Place(Fi.flareDots[i], mc.x + Round(cos(a) * r), mc.y + Round(bottom - Rb - 2 + sin(a) * r * 1.3))
            Tint(Fi.flareDots[i], K.flareDot, Stepped(flare * 0.7))
        end
    end

    -- the stack embers on the lower arc
    for i = 1, 5 do
        local e, t = EMBERS[i], Fi.embers[i]
        local on = i <= n
        CellOf(t.socket, A.fire, on and FIRECELL.emberOn or FIRECELL.emberOff)
        On(t.core, on)
        local fresh = on and i == n and popT ~= nil and popT < C.POP
        if on then
            local eb = Stepped(Beat(now + (i - 1) * 0.2, 1.1))
            Tint(t.core, fresh and K.emberFresh or (eb > 0.5 and K.emberHot or K.emberWarm), 1)
        end
        for j = 1, 4 do On(t.pop[j], fresh) end
        if fresh then
            local k = popT / C.POP
            local r = Round(2 + k * 4)
            local a = Stepped(1 - k)
            for j = 1, 4 do
                local dx = (j == 2 and r) or (j == 3 and -r) or 0
                local dy = (j == 1 and -r) or (j == 4 and r) or 0
                Place(t.pop[j], mc.x + e[1] + dx, mc.y + e[2] + dy)
                Tint(t.pop[j], K.emberPop, a)
            end
        end
    end
    if n > 0 and rem and rem > 0 then
        Label(Fi.label, TimeLabel(rem, f.est), low and K.amber or K.fireLabel)
    else
        Label(Fi.label, "")
    end
    return true       -- the flame always breathes
end

-------------------------------------------------------------------------------
-- Paint: the ward
-------------------------------------------------------------------------------

-- The secret absorb, straight into the setters. Never compared. The ward that is not the shown kind gets an empty bar and a
-- closed gate.
local function PaintAbsorbs()
    local W = P.ward
    local v = Data.Absorb()
    local kind = Data.WardKind()
    if v == nil or kind == nil then
        W.iceBar:SetMinMaxValues(0, 1); W.iceBar:SetValue(0)
        W.mistBar:SetMinMaxValues(0, 1); W.mistBar:SetValue(0)
        W.iceGate:SetAlpha(0); W.manaGate:SetAlpha(0)
        return
    end
    local bar, idle, gate, off, label
    if kind == "mana" then
        bar, idle, gate, off, label = W.mistBar, W.iceBar, W.manaGate, W.iceGate, W.manaLabel
    else
        bar, idle, gate, off, label = W.iceBar, W.mistBar, W.iceGate, W.manaGate, W.iceLabel
    end
    idle:SetMinMaxValues(0, 1); idle:SetValue(0)
    off:SetAlpha(0)
    bar:SetMinMaxValues(0, Data.Mark() or v)
    bar:SetValue(v)
    gate:SetAlpha(v)
    if not abbreviateOff and type(AbbreviateNumbers) == "function" then
        local ok, text = pcall(AbbreviateNumbers, v)
        if ok then ok = pcall(label.SetFormattedText, label, "%s", text) end
        if not ok then abbreviateOff = true; label:SetText(""); LogOnce("abbreviate", "the absorb number is off on this client") end
    end
end

local function ShowShards(k, kind)
    local W = P.ward
    local wc = C.WARD
    for i = 1, 10 do
        local s, v = W.shards[i], WSHARDS[i]
        if k then
            local qx = floor(wc.x + v[1] + v[3] * k * 14 + 0.5)
            local qy = floor(wc.y + v[2] + v[4] * k * 10 + k * k * 14 + 0.5)
            On(s.big, true); On(s.dot, true)
            Place(s.big, qx, qy); Place(s.dot, qx, qy)
            local a = Stepped(1 - k)
            Tint(s.big, kind == "mana" and K.shardMana or K.shardIce, a)
            Tint(s.dot, kind == "mana" and K.shardManaDot or K.shardDot, a)
        else
            On(s.big, false); On(s.dot, false)
        end
    end
end

local function PaintIce(now, combat, up, cooling, nudge)
    local W = P.ward
    local wc = C.WARD
    local buff = Data.Buff()
    local brem = buff.expires and (buff.expires - now) or nil
    local buffUp = brem ~= nil and brem > 0
    On(W.buffDark, buffUp)
    On(W.buffDash, not buffUp)
    UpdateRing(W.buffRing, buffUp, (buff.expires or 0) - Data.TUNING.BUFF_DURATION, Data.TUNING.BUFF_DURATION, now, false, 0)
    local b = nudge and Stepped(Beat(now, C.NUDGE)) or 0
    -- spikes and edge: dark, amber nudge, or the cooling refill's own edge
    On(W.spikeDark, not nudge)
    On(W.spikeNudge, nudge)
    if nudge then Tint(W.spikeNudge, K.nudge, 0.3 + 0.6 * b) end
    On(W.edgeCd, cooling)
    On(W.edgeEven, not cooling)
    On(W.edgeOdd, not cooling)
    if nudge then Tint(W.edgeOdd, K.nudge, 0.35 + 0.65 * b) else Tint(W.edgeOdd, K.edgeIdle, 0.5) end
    Refill(W.cdBar, "icebarrier", cooling)
    -- the light's life: the motes rising through it (under the clip), a hit's flash
    for i = 1, 4 do
        local ph = (now * 0.3 + (i - 1) * 0.25) % 1
        local mx, my = MOTE_X[i], Round(14 - ph * 28)
        local inside = (mx * mx) / ((C.OA - 2) * (C.OA - 2)) + (my * my) / ((C.OB - 2) * (C.OB - 2)) <= 1.04
        On(W.iceMotes[i], inside)
        if inside then
            Place(W.iceMotes[i], wc.x + mx, wc.y + my)
            Tint(W.iceMotes[i], K.white, Stepped(sin(ph * pi)))
        end
    end
    return up or cooling or nudge or buffUp
end

local function PaintMana(now, combat, up)
    local W = P.ward
    local wc = C.WARD
    local A_, B_ = C.MA, C.MB
    CellOf(W.vapour, A.mist, MCELL.vapour0 + floor(now * 4) % 4)
    -- the glyph sparks orbiting inside the rim: dim ones everywhere, lit ones under the clip of the light
    for i = 1, GLYPH_COUNT do
        local ang = now * 0.5 + (i - 1) * pi / 3
        local gx, gy = Round(sin(ang) * (A_ - 4)), Round(-cos(ang) * (B_ - 5))
        local tw = 0.55 + 0.45 * sin(now * 3 + (i - 1) * 1.7)
        SprAt(W.glyphDim[i], wc.x + gx, wc.y + gy)
        SprAt(W.glyphLit[i], wc.x + gx, wc.y + gy)
        Tint(W.glyphDim[i], K.glyphDim, Stepped(0.7 * tw))
        Tint(W.glyphLit[i], K.glyphLit, Stepped(0.95 * tw))
    end
    Alpha(W.core, Stepped((0.35 + 0.25 * Beat(now, 1.8)) / 0.6))
    -- the bright spark running round the ring
    local f = (now * 0.35) % 1
    for i = 1, 3 do
        local t = (i - 2) * 0.03
        local aa = (f + t) * 2 * pi
        local px, py = sin(aa), -cos(aa)
        local rr = 1 / math.sqrt((px / (A_ - 0.5)) ^ 2 + (py / (B_ - 0.5)) ^ 2)
        Place(W.sparkHead[i], wc.x + Round(px * rr), wc.y + Round(py * rr))
        Tint(W.sparkHead[i], i == 2 and K.sparkHead or K.sparkNear, 1)
    end
    -- motes and star sparkles
    for i = 1, 5 do
        local ph = (now * 0.4 + (i - 1) * 0.2) % 1
        local mx = Round(sin((i - 1) * 2.3 + now * 0.7) * (A_ - 6))
        local my = Round(B_ - 4 - ph * (2 * B_ - 8))
        local inside = (mx * mx) / ((A_ - 2) * (A_ - 2)) + (my * my) / ((B_ - 2) * (B_ - 2)) <= 1.04
        On(W.manaMotes[i], inside)
        if inside then
            Place(W.manaMotes[i], wc.x + mx, wc.y + my)
            Tint(W.manaMotes[i], (i - 1) % 2 == 1 and K.moteA or K.moteB, Stepped(sin(ph * pi)))
        end
    end
    local si = floor(now / 0.4) % 7
    local sa = 1 - ((now % 0.4) / 0.4)
    local sxp, syp = wc.x + SPARKLE_X[si + 1], wc.y + SPARKLE_Y[si + 1]
    Place(W.star, sxp, syp)
    Tint(W.star, K.white, Stepped(sa))
    for i = 1, 4 do
        local dx = (i == 1 and 1) or (i == 2 and -1) or 0
        local dy = (i == 3 and 1) or (i == 4 and -1) or 0
        Place(W.starArms[i], sxp + dx, syp + dy)
        Tint(W.starArms[i], K.starArm, Stepped(0.6 * sa))
    end
    return true
end

local function PaintWard(now, combat)
    local W = P.ward
    local kind = Data.WardKind()
    local ward = Data.Ward()
    local up = ward.up and true or false
    On(W.locked, kind == nil)
    On(W.ice, kind == "barrier")
    On(W.mana, kind == "mana")
    if kind == nil then
        On(W.iceGate, false); On(W.manaGate, false)
        On(W.buffLabel, false)
        On(W.lockLabel, true)
        Label(W.lockLabel, "L20", K.muted)
        P.ShakeTo(0)
        ShowShards(nil)
        return false
    end
    On(W.lockLabel, false)
    On(W.iceGate, kind == "barrier")
    On(W.manaGate, kind == "mana")
    local cooling = kind == "barrier" and Data.Cooling("icebarrier") == true
    local nudge = kind == "barrier" and combat and not up and not cooling
    local moving
    if kind == "barrier" then
        moving = PaintIce(now, combat, up, cooling, nudge)
    else
        moving = PaintMana(now, combat, up)
    end
    -- a hit shakes it and flashes it white (under the gate, so only a ward that holds light shows it)
    local sinceHit = hitAt and (now - hitAt) or nil
    On(W.flashIce, kind == "barrier" and sinceHit ~= nil and sinceHit < C.FLASH)
    On(W.flashMist, kind == "mana" and sinceHit ~= nil and sinceHit < C.FLASH)
    if sinceHit and sinceHit < C.SHAKE then
        P.ShakeTo((floor(sinceHit * 50) % 2 == 1) and 1 or -1)
    else
        P.ShakeTo(0)
    end
    local sinceBreak = breakAt and (now - breakAt) or nil
    ShowShards(sinceBreak and sinceBreak < C.BREAK and sinceBreak / C.BREAK or nil, kind)
    -- the labels: the absorb (under the gate) while the guess says there is light; else the buff time
    local buff = Data.Buff()
    local brem = buff.expires and (buff.expires - now) or nil
    local buffLabel = kind == "barrier" and not up and brem ~= nil and brem > 0
    On(W.buffLabel, buffLabel)
    if buffLabel then Label(W.buffLabel, TimeLabel(brem, true), K.buffLabel) else Label(W.buffLabel, "") end
    TextColor(W.iceLabel, K.iceLabel, 1)
    TextColor(W.manaLabel, K.manaLabel, 1)
    return moving or up or (sinceHit ~= nil and sinceHit < C.SHAKE) or (sinceBreak ~= nil and sinceBreak < C.BREAK)
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

local function ShowSpec(spec)
    if shownSpec == spec then return end
    shownSpec = spec
    On(P.frost.root, spec == "FROST")
    On(P.arcane.root, spec == "ARCANE")
    On(P.fire.root, spec == "FIRE")
end

local function PaintAll(now)
    if not mod then return end
    local combat = InCombat()
    local spec = Data.Spec()
    ShowSpec(spec)
    local moving = false
    if spec == "FROST" then moving = Run("paintfrost", PaintFrost, now, combat)
    elseif spec == "ARCANE" then moving = Run("paintarcane", PaintArcane, now, combat)
    else moving = Run("paintfire", PaintFire, now, combat) end
    local mk = Run("paintmarks", PaintMarks, now, combat, Data.MarkKind(), spec)
    local w = Run("paintward", PaintWard, now, combat)
    if P.absorbDirty then
        P.absorbDirty = false
        local ok, err = pcall(PaintAbsorbs)
        if not ok then LogOnce("absorb", err) end
    end
    P.moving = (moving or mk or w) and true or false
    if Sync then Sync() end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    absorbAcc = absorbAcc + elapsed
    costAcc = costAcc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Data.Tick, now)
    if not ok then LogOnce("tick", err) end
    if absorbAcc >= C.ABSORB_EVERY then absorbAcc = 0; P.absorbDirty = true end
    if costAcc >= C.COST_EVERY then
        costAcc = 0
        if shownSpec == "ARCANE" then pcall(Data.RefreshCost) end
    end
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
    local now = GetTime()
    if reason == "hit" then
        hitAt = now
    elseif reason == "break" then
        breakAt = now
    elseif reason == "cast" or reason == "absorb" then
        if reason == "absorb" then hitAt = nil end
    end
    P.absorbDirty = true
    if subscribed then PaintAll(now) end
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

-- The module's top left in image px, and a hook for whoever seats something over the ward (GunsightMageClick.lua's click
-- catcher): fn(OX, OY) after every seat.
local seatListeners = {}
function Mage.Origin() return OX, OY end
function Mage.OnSeat(fn)
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
        LogOnce("notheme", "Theme is missing, the Mage module is not built")
        return nil
    end
    Data = FS.MageState
    if not (Data and Data.Spec and Data.Subscribe) then
        LogOnce("nodata", "FS.MageState is missing, the Mage module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightMage", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        BuildFrost()
        BuildMarks()
        BuildArcane()
        BuildFire()
        BuildWard()
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Mage.frame, Mage.parts = mod, P
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
Mage._PaintFrost, Mage._PaintArcane, Mage._PaintFire, Mage._PaintWard, Mage._PaintMarks = PaintFrost, PaintArcane, PaintFire,
    PaintWard, PaintMarks
Mage._PaintAbsorbs, Mage._PaintAll = PaintAbsorbs, PaintAll

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "MAGE" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
