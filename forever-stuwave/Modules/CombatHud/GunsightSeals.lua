-- Forever STUwave: Gunsight Class Module for the Paladin: the wax seal and the Judgement hammer
--
-- The approved design is the design mockup "Paladin seal and hammer" (2026-11-10, idea 1 SLAM, hammer A, the seal set locked
-- the same day). Two pieces stand side by side on the 150 x 86 sprite canvas:
--   * THE SEAL (left): a lumpy wax seal in the active seal's colour with the seal's emblem pressed in. The wax is the seal's
--     bar: its colour drains from the top down as the seal runs out (a bright line marks the level), the time sits under it,
--     and under 3 s an amber crack flickers across it. No seal: an amber dashed ring that pulses in combat (steady out of it)
--     inside a dark one, three amber dashes for the time. Unknown (nothing readable yet): the dark rings only.
--   * THE HAMMER (right): a stone, gold and blue warhammer that IS the Judgement cooldown bar. It fills with the seal's colour
--     from the pommel up over the cooldown (each material keeps its look; the unfilled part is cold, dim steel), a bright line
--     at the level. While it charges it is held raised in a soft dithered column of light that brightens as it fills, with a
--     halo and a few motes drifting up. Ready: one ring of light, then the halo and the outline breathe, the hammer bobs and
--     a glint crosses the head every couple of seconds. On our own Judgement (the bonk, slowed 1.8x) the light flares, the
--     hammer winds up and swings face first into the ground with afterimages; on impact a white flash, a pillar of light,
--     rays, two shockwaves, glowing cracks, debris and a module shake, and the seal rings. It sits planted and spent, rises
--     back up and recharges from the pommel. A Judgement debuff on the target is a rune burnt into the ground with a ring
--     that drains over its length (Crusader, Light, Wisdom 40 s, Justice 10 s); a damage seal's rune flares and fades.
--
-- UNITS. One sprite px is C.SPX image px; every position is a whole sprite px, as the mockup's canvas. The art is baked by
-- tools/assets/generate_paladin_seal.py into three atlases; FS.PaladinArt (PaladinArt.lua, generated) holds every sprite's
-- rect and origin and the angle tables. Colours that are the seal's are white masks tinted here: a filled hammer px is the
-- baked "filled" body with the tint mask over it in the seal colour at Art.TINT_A, which is the mockup's
-- mix(mix(base, seal, .2), white, .05). The upright and the planted (90 degree) hammer crop their layers at the fill row;
-- the rise frames carry the fill the mockup has at that moment; the wind-up and swing frames are full (or cold, no seal).
--
-- DATA. FS.Hud's pushed state only (no secret is read here): state.seal (key, expiresAt, duration; false none, nil unknown),
-- state.judgeAt (GetTime of our own last Judgement cast, a plain ledger stamp) and state.judged (the target's Judgement
-- debuff: key, expiresAt, duration). The cooldown is judgeAt + HudSpells.jd.cooldown (10 s on Forever, measured); a new
-- judgeAt is the bonk, and the seal it was cast under colours the blow (Judgement does not consume the seal). Every value
-- is type checked and secret guarded before use.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onShow
-- subscribes to the Hud and starts the ticker; onHide stops both. Plain frames only.
--
-- TICKER. One OnUpdate on the module frame while it is shown, at most every C.TICK s (the light and the breath always move).
-- The tick path allocates nothing: colours are numbers, sprite rects and tints are written only when they change.
--
-- Reduced motion (ForeverSTUwaveDB.reducedMotion == true): no shake, no white flash, no bob, no glint, no motes; the breath
-- and the no-seal pulse hold steady. The slam itself still plays, since it is the Judgement.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Art = FS.PaladinArt
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightSeals = FS.GunsightSeals or {}
local Seals = FS.GunsightSeals

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, max, min, abs, cos, sin, pi = math.floor, math.max, math.min, math.abs, math.cos, math.sin, math.pi

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local function Mix(a, b, k)
    return { a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px (the Warrior module's)
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    LX = 42, SEAL_Y = 36, WAX_R = 15,  -- the seal's centre and radius
    HX = 108, GROUND = 66, LABEL_Y = 74,
    SEAL_S = 30,                       -- a seal's length when the push carries none
    WARN_S = 3,                        -- the amber crack under this many seconds left
    COOLDOWN = 10,                     -- Judgement's cooldown when HudSpells has none
    -- the slam, in the mockup's "s" units (game seconds / SLOW)
    SLOW = 1.8, WIND = 0.15, HIT = 0.23, STOP = 0.31, RISE0 = 1.1, RISE1 = 1.5,
    BURST = 1,                         -- seconds the ready ring takes to open
    MOTES = 6, DEBRIS = 18,
}
C.GX, C.GY = C.HX - 12, C.GROUND - 19   -- where the hammer's grip lands
C.HY = C.GY - 25                         -- the raised head's centre
C.IX = C.GX + 25                         -- where the face lands
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Seals.C = C

local COL = {
    righteousness = Hex("#c9d3e6"), crusader = Hex("#ff9a2e"), fury = Hex("#ff6a1a"), command = Hex("#b565ff"),
    justice = Hex("#ffd23f"), light = Hex("#fff0c0"), wisdom = Hex("#4da3ff"),
}
local K = {
    amber = Hex("#ffb648"), white = Hex("#f3fbff"), pure = { 1, 1, 1 }, muted = Hex("#9d93c4"), off = Hex("#2c2048"),
    out = Hex("#120822"), ground = Hex("#2a1d48"), debris = Hex("#6b5a8a"), embDark = Hex("#5a4416"),
}
Seals.COLORS, Seals.SEAL_COLORS = K, COL
-- per seal: the light (cl), the level line (edge), the ready emblem, the crack light
local LIGHT, EDGE, EMB_READY, CRACK_LIGHT = {}, {}, {}, {}
for id, c in pairs(COL) do
    LIGHT[id] = Mix(c, K.pure, 0.55)
    EDGE[id] = Mix(c, K.pure, 0.85)
    EMB_READY[id] = Mix(c, K.pure, 0.45)
    CRACK_LIGHT[id] = Mix(c, K.pure, 0.6)
end

-- HudSpells seal key (the profile's seals.order, HudLogic state.seal.key) to the seal id.
local KEY_ID = {
    sor = "righteousness", sotc = "crusader", sofu = "fury", soc = "command",
    sol = "light", sow = "wisdom", soj = "justice",
}
Seals.KEY_ID = KEY_ID

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local IsSecret = FS.IsSecret or function() return false end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightseals_" .. key, "|cffff4488Forever STUwave|r: gunsight seals: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.sprites) == "table") then
    LogOnce("noart", "FS.PaladinArt is missing, the Paladin module is not built")
    return
end
local SPR, ATL, SCALE = Art.sprites, Art.ATLAS, Art.SCALE
local HH, PIVY, COL90 = Art.HH, Art.PIVY, Art.COL90
local STAND_UP, STAND_SIDE                -- the upright and the 90 degree frame's index in Art.STAND
for i = 1, #Art.STAND do
    if abs(Art.STAND[i]) < 1e-6 then STAND_UP = i end
    if abs(Art.STAND[i] - pi / 2) < 1e-4 then STAND_SIDE = i end
end

-- Sprite names, built at load so the tick never concatenates.
local NAME = { stand = {}, rise = {}, glint = {}, pillarCore = {}, pillarSide = {}, raysWhite = {}, raysSeal = {}, shock = {},
    digit = {}, wax = { full = {}, drain = {}, line = {} }, rune = {} }
for i = 1, #Art.STAND do
    local p = "stand" .. (i - 1) .. "_"
    local e = {}
    for id in pairs(COL) do e[id] = p .. "emb_" .. Art.SHAPE[id] end
    NAME.stand[i] = { cold = p .. "cold", filled = p .. "filled", mask = p .. "mask", outline = p .. "outline", emb = e }
end
for i = 1, #Art.RISE do
    local p = "rise" .. (i - 1) .. "_"
    local e = {}
    for id in pairs(COL) do e[id] = p .. "emb_" .. Art.SHAPE[id] end
    NAME.rise[i] = { coldout = p .. "coldout", coldrest = p .. "coldrest", filled = p .. "filled", mask = p .. "mask",
        edge = p .. "edge", emb = e }
end
for _, b in ipairs(Art.GLINT) do NAME.glint[b] = "glint_" .. b end
for _, w in ipairs(Art.PILLAR) do NAME.pillarCore[w] = "pillar" .. w .. "_core"; NAME.pillarSide[w] = "pillar" .. w .. "_side" end
for i = 1, #Art.RAY_K do NAME.raysWhite[i] = "rays" .. (i - 1) .. "_white"; NAME.raysSeal[i] = "rays" .. (i - 1) .. "_seal" end
for r = Art.SHOCK_MIN, Art.SHOCK_MAX do NAME.shock[r] = "shock" .. r end
for d = 0, 9 do NAME.digit[d] = "digit_" .. d end
NAME.digit.S = "digit_S"
for id in pairs(COL) do
    NAME.wax.full[id], NAME.wax.drain[id], NAME.wax.line[id] = "wax_full_" .. id, "wax_drain_" .. id, "wax_line_" .. id
    NAME.rune[id] = "rune_" .. Art.SHAPE[id]
end
Seals.NAME = NAME

-------------------------------------------------------------------------------
-- State (from the Hud pushes; the tick reads only these)
-------------------------------------------------------------------------------

local D = {
    sealMode = "unknown",             -- "seal", "none" or "unknown"
    seal = nil, sealExp = nil, sealDur = C.SEAL_S,
    judgeAt = nil, judgeKey = nil,    -- our last Judgement and the seal it was cast under
    debKey = nil, debExp = nil, debDur = nil,
    inCombat = false, reduced = false,
}
Seals.data = D

local mod, art, top
local P = {}
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc = false, false, 0

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

local function S(v) return ui(v * C.SPX) end

-------------------------------------------------------------------------------
-- Regions
-------------------------------------------------------------------------------

local function Place(t, x, y)
    if t.fsX == x and t.fsY == y then return end
    t.fsX, t.fsY = x, y
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", t.fsHost, "TOPLEFT", S(x), -S(y))
end

local function On(t)
    if t.fsOn ~= true then t.fsOn = true; t:Show() end
end

local function Off(t)
    if t.fsOn ~= false then t.fsOn = false; t:Hide() end
end

local function Tint(t, c, a)
    local r, g, b = c[1], c[2], c[3]
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

-- A sprite region: an atlas texture on `host` (art, or top for the flash).
local function Spr(layer, sub, host)
    host = host or art
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost = host
    t:Hide()
    t.fsOn = false
    Seat(function() t.fsX, t.fsY, t.fsName = nil, nil, nil end)   -- a rescale rewrites the size
    return t
end

-- A flat square region (one sprite px unless sized).
local function Dot(layer, sub, host)
    host = host or art
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost = host
    t:SetTexture(FLAT)
    t:Hide()
    t.fsOn = false
    t.fsW, t.fsH = 1, 1
    Seat(function() t:SetSize(S(t.fsW), S(t.fsH)); t.fsX, t.fsY = nil, nil end)
    return t
end

local function DotSize(t, w, h)
    if t.fsW == w and t.fsH == h then return end
    t.fsW, t.fsH = w, h
    t:SetSize(S(w), S(h))
end

local function ShowDot(t, x, y, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    Place(t, x, y)
    Tint(t, c, a)
end

local function HideList(list, from)
    for i = from or 1, #list do Off(list[i]) end
end

local function Dots(n, layer, sub)
    local list = {}
    for i = 1, n do list[i] = Dot(layer, sub) end
    return list
end

-- Show sprite `name` with its origin at sprite (x, y), only its columns [c0, c1) and rows [r0, r1) (sprite px from the
-- sprite's top left; nil = the whole span). An empty crop hides it. `stretchH` sizes it that many sprite px tall instead.
local function Sprite(t, name, x, y, c, a, c0, c1, r0, r1, stretchH)
    local s = name and SPR[name]
    if not s or a <= 0 then Off(t); return end
    local w, h = s[4], s[5]
    c0, c1, r0, r1 = max(c0 or 0, 0), min(c1 or w, w), max(r0 or 0, 0), min(r1 or h, h)
    if c1 <= c0 or r1 <= r0 then Off(t); return end
    local atlas = ATL[s[1]]
    if t.fsAtlas ~= s[1] then
        t.fsAtlas = s[1]
        SetTex(t, MEDIA .. atlas.file .. ".tga")
    end
    if t.fsName ~= name or t.fsC0 ~= c0 or t.fsC1 ~= c1 or t.fsR0 ~= r0 or t.fsR1 ~= r1 or t.fsCrop ~= stretchH then
        t.fsName, t.fsC0, t.fsC1, t.fsR0, t.fsR1, t.fsCrop = name, c0, c1, r0, r1, stretchH
        local aw, ah = atlas.w, atlas.h
        t:SetTexCoord((s[2] + c0 * SCALE) / aw, (s[2] + c1 * SCALE) / aw, (s[3] + r0 * SCALE) / ah, (s[3] + r1 * SCALE) / ah)
        t:SetSize(S(c1 - c0), S(stretchH or (r1 - r0)))
    end
    On(t)
    Place(t, x - s[6] + c0, y - s[7] + (stretchH and 0 or r0))
    Tint(t, c, a)
end

-- A hammer layer cropped to the hammer rows [j0, j1) (hammer px 0..56), for the upright frame (rows) or the 90 degree frame
-- (columns: row j lands at column COL90 - j from the grip). Other frames are shown whole or not at all.
local function HammerRows(t, name, x, y, c, a, j0, j1, frame)
    local s = SPR[name]
    if not s or j1 <= j0 then Off(t); return end
    if frame == STAND_UP then
        Sprite(t, name, x, y, c, a, nil, nil, j0 - PIVY + s[7], j1 - PIVY + s[7])
    elseif frame == STAND_SIDE then
        Sprite(t, name, x, y, c, a, s[6] + COL90 - j1 + 1, s[6] + COL90 - j0 + 1, nil, nil)
    elseif j0 <= 0 and j1 >= HH then
        Sprite(t, name, x, y, c, a)
    else
        Off(t)
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Label()
    local l = { x = 0 }
    for i = 1, 3 do l[i] = Spr("OVERLAY", 6) end
    return l
end

local function Build()
    -- the seal side
    P.waxDrain = Spr("ARTWORK", -8)
    P.waxLine = Spr("ARTWORK", -8)
    P.waxFull = Spr("ARTWORK", -8)
    P.waxCrack = Spr("ARTWORK", -7)
    P.sealRing = Dots(48, "OVERLAY", 5)
    P.dashIn = Dots(32, "ARTWORK", -8)
    P.dashOut = Dots(32, "ARTWORK", -8)
    P.dashLabel = Dots(3, "OVERLAY", 6)
    for i = 1, 3 do DotSize(P.dashLabel[i], 3, 1) end
    P.sealLabel = Label()
    -- the ground and what burns into it
    P.ground = Dot("BACKGROUND", 0)
    DotSize(P.ground, 52, 1)
    P.cracksOdd = Spr("BACKGROUND", 1)
    P.cracksEven = Spr("BACKGROUND", 1)
    P.runeRing = Dots(48, "BACKGROUND", 2)
    P.runeEmb = Spr("BACKGROUND", 2)
    P.runeFlash = Dot("BACKGROUND", 3)
    DotSize(P.runeFlash, 35, 11)
    -- the light
    P.column = Spr("BORDER", 0)
    P.pool = Spr("BORDER", 0)
    P.halo = Spr("BORDER", 1)
    P.motes = Dots(C.MOTES, "BORDER", 2)
    -- the hammer
    P.after = {}
    for q = 1, 3 do P.after[q] = { mask = Spr("ARTWORK", -6), outline = Spr("ARTWORK", -5) } end
    P.cold = Spr("ARTWORK", -2)
    P.rest = Spr("ARTWORK", -2)
    P.filled = Spr("ARTWORK", -1)
    P.tint = Spr("ARTWORK", 0)
    P.edge = Spr("ARTWORK", 1)
    P.glint = Spr("ARTWORK", 2)
    P.embLit = Spr("ARTWORK", 3)
    P.embDark = Spr("ARTWORK", 3)
    P.outline = Spr("ARTWORK", 3)
    P.whiteout = Spr("ARTWORK", 4)
    -- the impact
    P.pillarSide = Spr("OVERLAY", 0)
    P.pillarCore = Spr("OVERLAY", 1)
    P.raysSeal = Spr("OVERLAY", 2)
    P.raysWhite = Spr("OVERLAY", 2)
    P.shockA = Spr("OVERLAY", 3)
    P.shockB = Spr("OVERLAY", 3)
    P.debris = Dots(C.DEBRIS, "OVERLAY", 4)
    P.burst = Dots(32, "OVERLAY", 4)
    P.cdLabel = Label()
    -- the hit flash, over everything and outside the shake
    P.flash = Dot("OVERLAY", 7, top)
    DotSize(P.flash, C.SW, C.SH)
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function Round(v) return floor(v + 0.5) end

-- The 3 x 5 pixel digits: `n` then S, centred on cx at y (n under 100).
local function PaintLabel(l, n, cx, y, c)
    if not n then
        for i = 1, 3 do Off(l[i]) end
        return
    end
    if n > 99 then n = 99 end
    if n < 0 then n = 0 end
    local len = n >= 10 and 3 or 2
    local x = Round(cx - (len * 4 - 1) / 2)
    if len == 3 then
        Sprite(l[1], NAME.digit[floor(n / 10)], x, y, c, 1)
        Sprite(l[2], NAME.digit[n % 10], x + 4, y, c, 1)
        Sprite(l[3], NAME.digit.S, x + 8, y, c, 1)
    else
        Sprite(l[1], NAME.digit[n], x, y, c, 1)
        Sprite(l[2], NAME.digit.S, x + 4, y, c, 1)
        Off(l[3])
    end
end

local function Ceil(v) return -floor(-v) end

-- the cooldown length: HudSpells' own, else C.COOLDOWN
local function Cooldown()
    local spells = FS.HudSpells
    local def = type(spells) == "table" and spells.jd
    local cd = type(def) == "table" and def.cooldown
    if type(cd) == "number" and not IsSecret(cd) and cd > 0 then return cd end
    return C.COOLDOWN
end

local BREATH = { 0, 0, 0 }              -- scratch colours the tick fills in place
local OUTLINE = { 0, 0, 0 }

local function MixInto(out, a, b, k)
    out[1], out[2], out[3] = a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k
    return out
end

local function DashedRing(list, cx, cy, r, c, a)
    local j = 0
    for i = 0, 47 do
        if i % 3 ~= 2 then
            j = j + 1
            local ang = i / 48 * pi * 2
            ShowDot(list[j], cx + Round(cos(ang) * r), cy + Round(sin(ang) * r), c, a)
        end
    end
end

-- id: the seal that is up now (nil: none, unknown, or past its expiry, which reads as none until the Hud says so)
local function PaintSeal(now, id, flashRing)
    local D = D
    if id then
        local left = max(0, (D.sealExp or now) - now)
        local level = left / D.sealDur
        if level > 1 then level = 1 end
        local x, y = C.LX, C.SEAL_Y
        local line = Round(C.WAX_R + 2 - (2 * C.WAX_R + 4) * level)       -- the level line, rows from the centre
        local s0 = SPR[NAME.wax.full[id]]
        local top = s0 and s0[7] or 0                                       -- the sprite's rows start this far above y
        Sprite(P.waxDrain, NAME.wax.drain[id], x, y, K.pure, 1, nil, nil, nil, line + top)
        Sprite(P.waxLine, NAME.wax.line[id], x, y, K.pure, 1, nil, nil, line + top, line + top + 1)
        Sprite(P.waxFull, NAME.wax.full[id], x, y, K.pure, 1, nil, nil, line + top + 1, nil)
        local warn = left < C.WARN_S
        if warn then
            local crack = D.reduced and 0.8 or (0.6 + 0.4 * sin(now * 14))
            Sprite(P.waxCrack, "wax_crack", x, y, K.pure, crack)
        else
            Off(P.waxCrack)
        end
        if flashRing > 0 then
            for i = 1, 48 do
                local ang = (i - 1) / 48 * pi * 2
                local r = 17 + (1 - flashRing) * 10
                ShowDot(P.sealRing[i], Round(x + cos(ang) * r), Round(y + sin(ang) * r), K.white, flashRing)
            end
        else
            HideList(P.sealRing)
        end
        PaintLabel(P.sealLabel, Ceil(left), x, C.LABEL_Y, warn and K.amber or COL[id])
        HideList(P.dashIn); HideList(P.dashOut); HideList(P.dashLabel)
        return
    end
    Off(P.waxDrain); Off(P.waxLine); Off(P.waxFull); Off(P.waxCrack)
    HideList(P.sealRing)
    PaintLabel(P.sealLabel, nil)
    if D.sealMode ~= "unknown" then
        local a = 0.5
        if D.inCombat and not D.reduced then a = 0.35 + 0.65 * (sin(now * 4) + 1) / 2 end
        DashedRing(P.dashIn, C.LX, C.SEAL_Y, C.WAX_R, K.amber, a)
        DashedRing(P.dashOut, C.LX, C.SEAL_Y, 22, K.off, 1)
        for i = 1, 3 do ShowDot(P.dashLabel[i], C.LX - 7 + (i - 1) * 5, C.LABEL_Y + 2, K.amber, a) end
    else
        DashedRing(P.dashIn, C.LX, C.SEAL_Y, C.WAX_R, K.muted, 0.35)
        DashedRing(P.dashOut, C.LX, C.SEAL_Y, 22, K.off, 1)
        HideList(P.dashLabel)
    end
end

-- The rune burnt into the ground at the impact point (groundRune): the target's debuff with its draining ring, or a damage
-- seal's flare for 2 s after the blow.
local function PaintRune(now, sinceHit)
    local key, a, frac = nil, 0, 1
    local D = D
    if D.debKey and D.debExp and D.debExp > now then
        key, a = D.debKey, 1
        frac = (D.debExp - now) / (D.debDur or 40)
        if frac > 1 then frac = 1 end
    elseif D.judgeKey and sinceHit and sinceHit >= 0 and sinceHit < 2 then
        key = D.judgeKey
        a = sinceHit < 0.6 and 1 or 1 - (sinceHit - 0.6) / 1.4
    end
    if not key or a <= 0 then
        HideList(P.runeRing); Off(P.runeEmb); Off(P.runeFlash)
        return
    end
    local c = COL[key]
    for i = 1, 48 do
        local ang = (i - 1) / 48 * pi * 2 - pi / 2
        ShowDot(P.runeRing[i], Round(C.IX + cos(ang) * 16), Round(C.GROUND + sin(ang) * 4), (i - 1) / 48 < frac and c or K.off, a)
    end
    Sprite(P.runeEmb, NAME.rune[key], C.IX, C.GROUND, c, a * 0.9)
    if sinceHit and sinceHit >= 0 and sinceHit < 0.5 then
        ShowDot(P.runeFlash, C.IX - 17, C.GROUND - 5, c, (1 - sinceHit / 0.5) * 0.45)
    else
        Off(P.runeFlash)
    end
end

local function NearestStand(ang)
    local best, bd = 1, 1e9
    for i = 1, #Art.STAND do
        local d = abs(Art.STAND[i] - ang)
        if d < bd then best, bd = i, d end
    end
    return best
end

local function HideHammer()
    Off(P.cold); Off(P.rest); Off(P.filled); Off(P.tint); Off(P.edge); Off(P.glint)
    Off(P.embLit); Off(P.embDark); Off(P.outline); Off(P.whiteout)
end

-- The hammer on a STAND frame: the cold part above the fill row, the filled part (and its tint) below, the edge line on it,
-- the emblem lit below and dark above, the outline, the glint and the impact whiteout.
local function PaintStand(f, x, y, id, fillRow, ready, outlineC, flash, glintBand)
    local n = NAME.stand[f]
    Off(P.rest)
    HammerRows(P.cold, n.cold, x, y, K.pure, 1, 0, fillRow, f)
    if id then
        HammerRows(P.filled, n.filled, x, y, K.pure, 1, fillRow + 1, HH, f)
        HammerRows(P.tint, n.mask, x, y, COL[id], Art.TINT_A, fillRow + 1, HH, f)
        HammerRows(P.edge, n.mask, x, y, EDGE[id], 1, fillRow, fillRow + 1, f)
        local emb = n.emb[id]
        HammerRows(P.embLit, emb, x, y, flash > 0 and K.white or (ready and EMB_READY[id] or COL[id]), 1, fillRow + 1, HH, f)
        HammerRows(P.embDark, emb, x, y, flash > 0 and K.white or K.embDark, 1, 0, fillRow + 1, f)
    else
        Off(P.filled); Off(P.tint); Off(P.edge); Off(P.embLit); Off(P.embDark)
    end
    Sprite(P.outline, n.outline, x, y, outlineC, 1)
    if glintBand and NAME.glint[glintBand] then
        Sprite(P.glint, NAME.glint[glintBand], x, y, K.pure, 1)
    else
        Off(P.glint)
    end
    if flash > 0 then Sprite(P.whiteout, n.mask, x, y, K.pure, flash) else Off(P.whiteout) end
end

-- The hammer on a RISE frame: its fill is baked in (the cooldown is short of the emblem, which stays dark).
local function PaintRise(r, x, y, id)
    local n = NAME.rise[r]
    Sprite(P.cold, n.coldout, x, y, K.pure, 1)
    Off(P.outline); Off(P.glint); Off(P.whiteout); Off(P.embLit)
    if id then
        Off(P.rest)
        Sprite(P.filled, n.filled, x, y, K.pure, 1)
        Sprite(P.tint, n.mask, x, y, COL[id], Art.TINT_A)
        Sprite(P.edge, n.edge, x, y, EDGE[id], 1)
        Sprite(P.embDark, n.emb[id], x, y, K.embDark, 1)
    else
        Sprite(P.rest, n.coldrest, x, y, K.pure, 1)
        Off(P.filled); Off(P.tint); Off(P.edge); Off(P.embDark)
    end
end

local function Paint(now)
    if not mod then return end
    local D = D
    local cdLen = Cooldown()
    local id = D.sealMode == "seal" and D.seal or nil
    if id and D.sealExp and D.sealExp <= now then id = nil end
    local since = D.judgeAt and (now - D.judgeAt) or nil
    local judged = since ~= nil and since >= 0
    local cd = judged and max(0, cdLen - since) or 0
    local ready = id ~= nil and cd <= 0
    local charge = id and (ready and 1 or max(0, 1 - cd / cdLen)) or 0
    local s = judged and since / C.SLOW or 1e9
    local hitK = (judged and s >= C.HIT) and (s - C.HIT) or nil       -- s units since the blow landed
    local jKey = (judged and D.judgeKey) or id or "righteousness"
    local hKey = id or jKey
    local jc = COL[jKey]
    local cl = LIGHT[id or jKey]
    local reduced = D.reduced
    local breath = reduced and 0 or sin(now * 1.6)

    -- the shake (the flash stays outside it)
    local sx, sy = 0, 0
    if hitK and hitK < 0.5 and not reduced then
        local k = 1 - hitK / 0.5
        sx, sy = Round(sin(s * 95) * 3 * k), Round(cos(s * 80) * 2 * k)
    end
    if art.fsSX ~= sx or art.fsSY ~= sy then
        art.fsSX, art.fsSY = sx, sy
        art:ClearAllPoints()
        art:SetPoint("TOPLEFT", mod, "TOPLEFT", S(sx), -S(sy))
    end

    PaintSeal(now, id, (id and hitK and hitK < 0.45) and (1 - hitK / 0.45) or 0)

    Place(P.ground, C.HX - 26, C.GROUND)
    On(P.ground)
    Tint(P.ground, K.ground, 1)

    -- the glowing cracks
    if hitK and hitK < 1.8 then
        local k = hitK / 1.8
        local a = k < 0.15 and 1 or 1 - (k - 0.15) / 0.85
        Sprite(P.cracksOdd, "cracks_odd", C.IX, C.GROUND, jc, a)
        Sprite(P.cracksEven, "cracks_even", C.IX, C.GROUND, CRACK_LIGHT[jKey], a)
    else
        Off(P.cracksOdd); Off(P.cracksEven)
    end
    PaintRune(now, hitK)

    -- the pose
    local ang, bob, lift = 0, 0, 0
    if s < C.WIND then
        local k = s / C.WIND
        ang, lift = -0.35 * k * (2 - k), 3 * k
    elseif s < C.HIT then
        local k = (s - C.WIND) / (C.HIT - C.WIND)
        ang, lift = -0.35 + (pi / 2 + 0.35) * k * k, 3 * (1 - k)
    elseif s < C.RISE0 then
        ang = pi / 2
    end
    if ready and not reduced then bob = Round(breath) end
    local raised = id ~= nil and s >= C.RISE1
    local hx, hy = C.GX, C.HY

    -- the light: a soft column from above, brighter as it charges; it flares during the wind-up
    local flare = s < C.HIT and s / C.HIT or 0
    if raised or flare > 0 then
        local k = ready and 1 or max(charge, flare)
        local a = (0.08 + 0.27 * k * k) * (ready and (0.85 + 0.15 * breath) or 1) * (flare > 0 and 1.6 or 1)
        Sprite(P.column, "column", hx, 0, cl, min(1, a))
        Sprite(P.pool, "column_pool", hx, C.GROUND, cl, min(1, a * 1.4))
    else
        Off(P.column); Off(P.pool)
    end
    if raised then
        local a = ready and (0.35 + 0.15 * breath) or 0.25 * charge * charge
        Sprite(P.halo, "halo", hx, hy + bob, cl, a)
        local n = reduced and 0 or (ready and 6 or 2 + Round(charge * 4))
        for i = 1, C.MOTES do
            local t = P.motes[i]
            if i <= n then
                local i0 = i - 1
                local life = (now * 0.12 + i0 * 0.173) % 1
                local x = hx + ((i0 * 37) % 34) - 17 + Round(sin(now * 0.8 + i0) * 1.5)
                local y = hy + 24 - life * 44
                ShowDot(t, Round(x), Round(y), cl, sin(life * pi) * (ready and 0.9 or 0.4 + 0.5 * charge))
            else
                Off(t)
            end
        end
    else
        Off(P.halo)
        HideList(P.motes)
    end

    -- the hammer: full charge until the blow lands
    local hid, hReady, hFill
    if judged and s < C.HIT then
        hid, hReady = id, id ~= nil
    else
        hid, hReady = id, ready
    end
    if not hid then hFill = HH
    elseif hReady then hFill = -1
    else hFill = Round(Art.BOTTOM_ROW + 1 - (Art.BOTTOM_ROW - Art.TOP_ROW + 1) * ((judged and s < C.HIT) and 1 or charge)) end
    local outlineC = hReady and MixInto(OUTLINE, K.out, COL[hKey], 0.35 + 0.25 * breath) or K.out

    -- afterimages on the swing
    for q = 1, 3 do
        local A = P.after[q]
        if s >= C.WIND and s < C.HIT + 0.06 then
            local kk = (s - q * 0.025 - C.WIND) / (C.HIT - C.WIND)
            if kk < 0 then kk = 0 elseif kk > 1 then kk = 1 end
            local f = NearestStand(-0.35 + (pi / 2 + 0.35) * kk * kk)
            local a = 0.18 * (4 - q) / 3
            local y = Round(C.GY - lift)
            Sprite(A.mask, NAME.stand[f].mask, hx, y, K.pure, a)
            Sprite(A.outline, NAME.stand[f].outline, hx, y, outlineC, a)
        else
            Off(A.mask); Off(A.outline)
        end
    end

    local flash = 0
    if s >= C.HIT and s < C.STOP + 0.1 then flash = 1 - max(0, s - C.STOP) / 0.1 end
    local x, y = hx, Round(C.GY + bob - lift)
    if s >= C.RISE0 and s < C.RISE1 then
        local k = (s - C.RISE0) / (C.RISE1 - C.RISE0)
        local r = floor(k * #Art.RISE) + 1
        if r > #Art.RISE then r = #Art.RISE end
        PaintRise(r, x, y, hid)
    else
        local f = NearestStand(ang)
        local band
        if hReady and f == STAND_UP and not reduced then
            local ph = (now * 0.45) % 1
            if ph < 0.35 then band = Round(-10 + ph / 0.35 * 62) end
        end
        PaintStand(f, x, y, hid, hFill, hReady, outlineC, flash, band)
    end

    -- the impact
    if hitK and hitK < 1.2 then
        local k = hitK
        if k < 0.3 then
            local a = 1 - k / 0.3
            local w = Round(7 * (1 - k / 0.3)) + 2
            Sprite(P.pillarSide, NAME.pillarSide[w], C.IX, 0, jc, a, nil, nil, nil, nil, C.GROUND)
            Sprite(P.pillarCore, NAME.pillarCore[w], C.IX, 0, K.white, a, nil, nil, nil, nil, C.GROUND)
        else
            Off(P.pillarSide); Off(P.pillarCore)
        end
        if k < 0.35 then
            local a = 1 - k / 0.35
            local i = Round(k / 0.035) + 1
            if i > #Art.RAY_K then i = #Art.RAY_K end
            Sprite(P.raysWhite, NAME.raysWhite[i], C.IX, C.GROUND, K.white, a)
            Sprite(P.raysSeal, NAME.raysSeal[i], C.IX, C.GROUND, jc, a)
        else
            Off(P.raysWhite); Off(P.raysSeal)
        end
        local kk = k
        if kk > 0 and kk < 0.6 then
            local R = Round(8 + kk * 70)
            if R > Art.SHOCK_MAX then R = Art.SHOCK_MAX end
            Sprite(P.shockA, NAME.shock[R], C.IX, C.GROUND, K.white, 1 - kk / 0.6)
        else
            Off(P.shockA)
        end
        kk = k - 0.08
        if kk > 0 and kk < 0.6 then
            local R = Round(8 + kk * 55)
            if R > Art.SHOCK_MAX then R = Art.SHOCK_MAX end
            Sprite(P.shockB, NAME.shock[R], C.IX, C.GROUND, jc, 1 - kk / 0.6)
        else
            Off(P.shockB)
        end
        for i = 1, C.DEBRIS do
            local t = P.debris[i]
            local i0 = i - 1
            if k < 1 then
                local an = -pi * (0.08 + 0.84 * ((i0 * 7) % 18) / 17)
                local v = 30 + ((i0 * 13) % 9) * 6
                local dx, dy = C.IX + cos(an) * v * k, C.GROUND - 2 + sin(an) * v * k + 60 * k * k
                if dy > C.GROUND then
                    Off(t)
                else
                    local big = i0 % 4 == 0 and 2 or 1
                    DotSize(t, big, big)
                    ShowDot(t, Round(dx), Round(dy), i0 % 3 == 0 and K.white or (i0 % 3 == 1 and jc or K.debris), 1 - k)
                end
            else
                Off(t)
            end
        end
    else
        Off(P.pillarSide); Off(P.pillarCore); Off(P.raysWhite); Off(P.raysSeal); Off(P.shockA); Off(P.shockB)
        HideList(P.debris)
    end

    -- the ready ring opening once the cooldown is done
    if id and since and since >= cdLen and since < cdLen + C.BURST then
        local k = (since - cdLen) / C.BURST
        local j = 0
        for i = 0, 63, 2 do
            j = j + 1
            local an = i / 64 * pi * 2
            ShowDot(P.burst[j], Round(hx + cos(an) * (18 + k * 14)), Round(hy + sin(an) * (18 + k * 14)), cl, (1 - k) * 0.8)
        end
    else
        HideList(P.burst)
    end

    PaintLabel(P.cdLabel, cd > 0 and Ceil(cd) or nil, C.HX, C.LABEL_Y, K.muted)

    -- the hit flash
    if hitK and hitK < 0.12 and not reduced then
        ShowDot(P.flash, 0, 0, K.white, 0.55 * (1 - hitK / 0.12))
    else
        Off(P.flash)
    end
end
Seals.Paint = Paint

local function SafePaint(now)
    local ok, err = pcall(Paint, now)
    if not ok then LogOnce("paint", err) end
end

-------------------------------------------------------------------------------
-- Data
-------------------------------------------------------------------------------

local function Num(v)
    if type(v) ~= "number" or IsSecret(v) then return nil end
    return v
end

local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

local function OnState(state)
    if type(state) ~= "table" then return end
    local D = D
    local seal = state.seal
    if type(seal) == "table" then
        local key = seal.key
        local id = type(key) == "string" and not IsSecret(key) and KEY_ID[key] or nil
        if id then
            D.sealMode, D.seal = "seal", id
            D.sealExp = Num(seal.expiresAt)
            local dur = Num(seal.duration)
            D.sealDur = (dur and dur > 0) and dur or C.SEAL_S
            if not D.sealExp then D.sealMode, D.seal = "unknown", nil end
        else
            D.sealMode, D.seal = "unknown", nil
        end
    elseif seal == false then
        D.sealMode, D.seal = "none", nil
    else
        D.sealMode, D.seal = "unknown", nil
    end
    local at = Num(state.judgeAt)
    if at ~= D.judgeAt then
        D.judgeAt = at
        D.judgeKey = at and D.seal or nil         -- Judgement does not consume the seal: the one up now is the one it rode
    end
    local jd = state.judged
    if type(jd) == "table" then
        local key = jd.key
        D.debKey = type(key) == "string" and not IsSecret(key) and KEY_ID[key] or nil
        D.debExp, D.debDur = Num(jd.expiresAt), Num(jd.duration)
        if not (D.debExp and D.debDur and D.debDur > 0) then D.debKey = nil end
    else
        D.debKey, D.debExp, D.debDur = nil, nil, nil
    end
    D.inCombat = state.inCombat == true
    D.reduced = ReducedMotion()
    if subscribed then SafePaint(GetTime()) end
end
Seals.OnState = OnState

local function Tick(_, elapsed)
    acc = acc + elapsed
    if acc < C.TICK then return end
    acc = 0
    SafePaint(GetTime())
end

local function Sync()
    local want = subscribed and mod ~= nil
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

function Seals.Origin() return OX, OY end

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y + C.DROP
    if mod then
        SeatAll()
        art.fsSX, art.fsSY = nil, nil
        if subscribed then SafePaint(GetTime()) end
    end
end

local function BuildModule(host)
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightSeals", host)
    art = CreateFrame("Frame", nil, mod)
    top = CreateFrame("Frame", nil, mod)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
        art:SetSize(ui(C.W), ui(C.H))
        top:SetAllPoints(mod)
        art.fsSX, art.fsSY = nil, nil
    end)
    if top.SetFrameLevel and mod.GetFrameLevel then
        local ok = pcall(function() top:SetFrameLevel(mod:GetFrameLevel() + 3) end)
        if not ok then LogOnce("level", "the flash frame level could not be set") end
    end
    local ok, err = pcall(Build)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod, art, top = nil, nil, nil
        seats, P = {}, {}
        return nil
    end
    Seals.frame, Seals.parts = mod, P
    SafePaint(GetTime())
    return mod
end

local function OnAreaShown()
    if not mod then return end
    if not subscribed then
        local Hud = FS.Hud
        if not (Hud and Hud.Subscribe) then
            LogOnce("nohud", "FS.Hud is missing, the Paladin module has no data")
        else
            subscribed = true
            Hud.Subscribe(OnState)                  -- pushes the current state at once
        end
    end
    SafePaint(GetTime())
    Sync()
end

local function OnAreaHidden()
    if not mod then return end
    if subscribed then
        subscribed = false
        if FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnState) end
    end
    Sync()
end

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "PALADIN" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
