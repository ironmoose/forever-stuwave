-- Forever STUwave: the Warlock Class Module for the Gunsight target side ("the Grimoire")
--
-- Design: the concept "The Grimoire" (2026-11-20, picked over the Soul Jar and the Crowned Skull; concept page
-- debug/warlock-concepts-2026-11-20.html, decision in the adze doc of that date). One 150 x 86 sprite px canvas, `C.SPX`
-- image px per sprite px.
--   THE BOOK (left, top left BX,BY): the demon's pact book. Its cover lights from the bottom with the demon's health over the
--   dark book; with no demon (or a dead one) it is dark with an amber outline and a slow smoke (pink when the Summon
--   cannot be paid), shaking on SUMMON. The cover gem and the eyes take the cue colour, else the demon's colour. The book
--   acts the cue out: lightning from the horns into the gem (BOLT), the pages burn (FIRE), blood drips from the bottom and a
--   pink ring bursts on the tap (TAP), the book lifts and souls stream into the gem (REAPING), the book lifts on a fel rune
--   ring (BINDING). Unreadable: a grey book and a "?".
--   THE LANE (right, from C.TX): ONE cue word by priority, REAPING (a Drain Soul channel) > BINDING (a Summon cast) > BOLT
--   (Shadow Trance) > FIRE (Decimation) > SUMMON (with its note: the demon and its shard, IMP FREE, NO SHARD) > TAP (the next
--   Shadow Bolt cannot be paid) > DRAIN (fewer than three shards); calm shows the demon's name. BOLT and FIRE carry a drain
--   bar for their 10 s window, REAPING one for the channel's ticks. Under it five soul crystals, one per shard, "+N" past five.
-- It does not draw mana or DoT timers: the mana regen module and GunsightDots already do.
--
-- DATA. Shards, procs, the Drain Soul channel come from the Hud's pushed state (a plain item count, plain proc flags, the
-- channel ledger). The demon, a Summon cast, "a bolt cannot be paid" and Life Tap are `FS.WarlockState` (plain reads only,
-- all UNPROBED on this client). The demon's HEALTH is secret: `UnitHealth("pet")` and its max go only to a vertical StatusBar's
-- SetValue / SetMinMaxValues (the Priest shield technique: the lit book texture stretched over the bar so the engine's crop
-- is the art). It is never compared, printed or stored. Nothing here reads the player's own health or mana.
--
-- ART is baked by tools/assets/generate_warlock_grimoire.py (an atlas of the book's looks, crystals, effects and the font, the
-- lit book for the bar, and the generated manifest WarlockArt.lua); the module tints the masks with SetVertexColor. One 30 Hz
-- OnUpdate runs while the module is shown; a tick allocates nothing (strings and positions are tables built once; the
-- harness measures it).
--
-- Reduced motion (ForeverSTUwaveDB.reducedMotion == true): no breathing halo, shimmer, shake, lift, blink, bolts, flames,
-- drops, souls or sparks; the rune ring stands still. The colours, the cue word, the crystals and the book still say
-- everything. Every cue and sub-part has an off switch (WarlockState.SETTINGS, shown on the Gunsight HUD page for a Warlock).

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Art = FS.WarlockArt
local State = FS.WarlockState
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightWarlock = FS.GunsightWarlock or {}
local Warlock = FS.GunsightWarlock

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, max, min, sin, cos, pi = math.floor, math.max, math.min, math.sin, math.cos, math.pi

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

-- every tunable number, with its source
local C = {
    SPX = 1.25,                 -- image px per sprite px (the Paladin module's)
    SW = 150, SH = 86,          -- the canvas in sprite px
    DROP = 5,                   -- image px the module sits below the area's top (the Paladin module's)
    TICK = 1 / 30,
    PROC_S = 10,                -- Shadow Trance and Decimation last 10 s (Wowhead Forever spell pages 17941 and 440873)
    LOW_SHARDS = 3,             -- DRAIN shows below this many shards (the Hud profile's drain_soul rule: shardsAtLeast 3)
    FRAC_AMBER = 0.2,           -- a proc's last fifth of its window is amber
    GAIN_S = 0.7, SPEND_S = 0.6, TAP_S = 0.7,   -- the event animations, seconds
    TX = 66,                    -- the right lane's left edge, sprite px
    BX = 10, BY = 14,           -- the book's top left, sprite px
    CRY_Y = 46, CRY_GAP = 15,   -- the crystal row: top, and the step from one crystal to the next
    BAR_W = 60,                 -- the cue's drain bar, sprite px
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Warlock.C = C

local K = {
    violet = Hex("#a855f7"), amber = Hex("#ffb648"), pink = Hex("#ff2e97"), orange = Hex("#ff6a2e"), bolt = Hex("#c58bff"),
    white = Hex("#f3fbff"), muted = Hex("#9d93c4"), track = Hex("#2c2048"), gold = Hex("#ffd23f"), pure = { 1, 1, 1 },
    fel = Hex("#39ff14"), ember = Hex("#a0201a"),
}
Warlock.COLORS = K
local DEMON_COL = {
    imp = Hex("#ff6a2e"), voidwalker = Hex("#a855f7"), sayaad = Hex("#ff2e97"), felhunter = Hex("#39ff14"), bound = Hex("#a855f7"),
}
local DEMON_NAME = { imp = "IMP", voidwalker = "VOIDWALKER", sayaad = "SAYAAD", felhunter = "FELHUNTER", bound = "DEMON" }
local CUE_COL = {
    summon = K.amber, bolt = K.bolt, fire = K.orange, tap = K.pink, drain = K.violet, reap = K.violet, binding = K.white,
}
local COST = State and State.COST or { imp = 0, voidwalker = 1, sayaad = 1, felhunter = 1 }

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local IsSecret = FS.IsSecret or function() return false end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightwarlock_" .. key, "|cffff4488Forever STUwave|r: gunsight warlock: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.sprites) == "table") then
    LogOnce("noart", "FS.WarlockArt is missing, the Warlock module is not built")
    return
end
if not (type(State) == "table" and State.Get) then
    LogOnce("nostate", "FS.WarlockState is missing, the Warlock module is not built")
    return
end
-- The ledger listens from load (a cast before the first target still counts), but only on a Warlock: any other class would
-- carry its events and spell book reads for the whole session for nothing.
do
    local okC, _, token = pcall(UnitClass, "player")
    if okC and not (FS.IsSecret and FS.IsSecret(token)) and token == "WARLOCK" and State.Start then State.Start() end
end

local SPR, SCALE, ATL = Art.sprites, Art.SCALE, Art.ATLAS
local ATLAS_PATH = MEDIA .. ATL.file .. ".tga"
local LIT_PATH = MEDIA .. Art.LIT .. ".tga"
local BX, BY = C.BX, C.BY
local BCX = BX + floor(Art.BOOK_W / 2)               -- the book's centre column and row
local BCY = BY + floor(Art.BOOK_H / 2)

local function Hash(n)
    local v = sin(n * 12.9898 + 78.233) * 43758.5453
    return v - floor(v)
end
local function Round(v) return floor(v + 0.5) end

-------------------------------------------------------------------------------
-- Tables built once (a tick builds none)
-------------------------------------------------------------------------------

local ZAP, RING = {}, {}
for i = 0, Art.ZAPS - 1 do ZAP[i] = "zap" .. i end
for i = 0, Art.RING_FRAMES - 1 do RING[i] = "ring" .. i end
local N_FIRE = 30
local FIRE_H, FIRE_X = {}, {}
for i = 0, N_FIRE - 1 do
    FIRE_H[i] = Hash(i * 7)
    FIRE_X[i] = (Hash(i * 13) - 0.5) * 40
end
local N_WISP = 10
local WISP_H, WISP_X = {}, {}
for i = 0, N_WISP - 1 do
    WISP_H[i] = Hash(i * 5 + 3)
    WISP_X[i] = (Hash(i * 11 + 1) - 0.5) * 34
end
local SPARK_X = {}
for i = 0, 9 do SPARK_X[i] = (Hash(i) - 0.5) * 40 end
local BURST_COS, BURST_SIN = {}, {}
for m = 1, 24 do
    local a = (m - 1) / 24 * 6.283
    BURST_COS[m], BURST_SIN[m] = cos(a), sin(a)
end
local GAIN_COS, GAIN_SIN = {}, {}
for m = 1, 16 do
    local a = (m - 1) / 16 * 6.283
    GAIN_COS[m], GAIN_SIN[m] = cos(a), sin(a)
end
local SPARK8_COS, SPARK8_SIN = {}, {}
for m = 1, 8 do
    local a = (m - 1) / 8 * 6.283
    SPARK8_COS[m], SPARK8_SIN[m] = cos(a), sin(a)
end
local CRY_X = {}
for i = 1, 5 do CRY_X[i] = C.TX + (i - 1) * C.CRY_GAP end
local CRY_CX, CRY_CY = floor(Art.CRY_W / 2), floor(Art.CRY_H / 2)

-- glyphs: the character's sprite and advance
local GLYPH = {}
local function GlyphName(ch)
    local map = { ["?"] = "q", ["-"] = "minus", ["+"] = "plus", ["."] = "dot" }
    return "f_" .. (map[ch] or ch)
end
for ch in pairs(Art.GLYPH_W) do GLYPH[ch] = GlyphName(ch) end
local MORE = {}
for n = 6, 99 do MORE[n] = "+" .. (n - 5) end
local NOTE_SUMMON = { none = "A DEMON -1" }
for d, name in pairs(DEMON_NAME) do
    NOTE_SUMMON[d] = (COST[d] or 1) == 0 and (name .. " FREE") or (name .. " -1")
end

-------------------------------------------------------------------------------
-- Frames and regions
-------------------------------------------------------------------------------

local mod, art, top, bar
local P = {}
local regions = {}                       -- every texture, for the rescale
local OX, OY = 0, 0
local subscribed, ticking, acc = false, false, 0

local function S(v) return ui(v * C.SPX) end

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
    if a > 1 then a = 1 end
    local r, g, b = c[1], c[2], c[3]
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

-- an atlas sprite region
local function Spr(host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost, t.fsOn, t.fsK = host, false, 1
    SetTex(t, ATLAS_PATH)
    t:Hide()
    regions[#regions + 1] = t
    return t
end

-- a flat square region of w x h sprite px
local function Dot(host, layer, sub, w, h)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost, t.fsOn, t.fsW, t.fsH, t.fsDot = host, false, w or 1, h or 1, true
    t:SetTexture(FLAT)
    t:Hide()
    regions[#regions + 1] = t
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
    Place(t, Round(x), Round(y))
    Tint(t, c, a)
end

-- sprite `name` (scale k) with its origin at sprite px (x, y)
local function Cell(t, name, x, y, c, a, k)
    local s = name and SPR[name]
    if not s or a <= 0 then Off(t); return end
    k = k or 1
    if t.fsName ~= name or t.fsK ~= k then
        t.fsName, t.fsK = name, k
        local aw, ah = ATL.w, ATL.h
        t:SetTexCoord(s[1] / aw, (s[1] + s[3] * SCALE) / aw, s[2] / ah, (s[2] + s[4] * SCALE) / ah)
        t:SetSize(S(s[3] * k), S(s[4] * k))
    end
    On(t)
    Place(t, Round(x) - s[5] * k, Round(y) - s[6] * k)
    Tint(t, c, a)
end

local function OffAll(list)
    for i = 1, #list do Off(list[i]) end
end

-- a text line of baked glyphs: n regions at scale k
local function Line(host, n, k, layer, sub)
    local l = { n = n, k = k }
    for i = 1, n do l[i] = Spr(host, layer or "OVERLAY", sub or 4) end
    return l
end

local function SetLine(l, str, x, y, c, a)
    if str == nil or a <= 0 then
        if l.str ~= false then l.str = false; OffAll(l) end
        return
    end
    if l.str == str and l.x == x and l.y == y and l.c == c and l.a == a and l.seatEpoch == P.epoch then return end
    l.str, l.x, l.y, l.c, l.a, l.seatEpoch = str, x, y, c, a, P.epoch
    l.blinkA = nil
    local k, cx, n = l.k, x, 0
    for i = 1, #str do
        local ch = str:sub(i, i)
        if ch == " " then
            cx = cx + 2 * k
        else
            n = n + 1
            local t = l[n]
            if not t then break end
            local name = GLYPH[ch]
            t.fsName = nil                   -- force the texcoord and size (the glyph may have changed)
            Cell(t, name, cx, y, c, a, k)
            cx = cx + ((Art.GLYPH_W[ch] or 3) + 1) * k
        end
    end
    for i = n + 1, l.n do Off(l[i]) end
end

-- the alpha of a laid out line, without laying it out again (a blink)
local function LineAlpha(l, a)
    if l.str == false or l.str == nil or l.blinkA == a then return end
    l.blinkA = a
    for i = 1, l.n do
        local t = l[i]
        if t.fsOn then Tint(t, l.c, a) end
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build()
    P.epoch = 0
    -- under the book (art frame)
    P.halo = Spr(art, "BACKGROUND", 0)
    P.shadow = Spr(art, "BACKGROUND", 1)
    P.ring = Spr(art, "BACKGROUND", 2)
    P.dim = Spr(art, "ARTWORK", 0)
    -- the lit book: the engine fills it from the demon's secret health
    bar = CreateFrame("StatusBar", nil, mod)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(LIT_PATH)
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar:Hide()
    P.bar = bar
    -- over the book (top frame)
    P.rim = Spr(top, "ARTWORK", 1)
    P.flash = Spr(top, "ARTWORK", 2)
    P.coverGem = Spr(top, "ARTWORK", 3)
    P.eye = { Dot(top, "ARTWORK", 4, 2, 1), Dot(top, "ARTWORK", 4, 2, 1) }
    P.zapA, P.zapB = Spr(top, "OVERLAY", 0), Spr(top, "OVERLAY", 1)
    P.unknownQ = Line(top, 1, 3, "OVERLAY", 2)
    P.fire = {}
    for i = 1, N_FIRE do P.fire[i] = Dot(top, "OVERLAY", 3) end
    P.drops = {}
    for i = 1, 3 do P.drops[i] = Spr(top, "OVERLAY", 3) end
    P.motes = {}
    for i = 1, 9 do P.motes[i] = Dot(top, "OVERLAY", 3) end
    P.wisps = {}
    for i = 1, N_WISP do P.wisps[i] = Dot(top, "OVERLAY", 3) end
    P.sparks = {}
    for i = 1, 10 do P.sparks[i] = Dot(top, "OVERLAY", 3) end
    P.burst = {}
    for m = 1, 24 do P.burst[m] = Dot(top, "OVERLAY", 6) end
    -- the soul crystals (art frame) and their events (top frame)
    P.sock, P.gem, P.shine = {}, {}, {}
    for i = 1, 5 do
        P.sock[i] = Spr(art, "ARTWORK", 1)
        P.gem[i] = Spr(art, "ARTWORK", 2)
        P.shine[i] = Spr(art, "ARTWORK", 3)
    end
    P.evGem = Spr(top, "OVERLAY", 4)
    P.evSpend = Spr(top, "OVERLAY", 4)
    P.gainRing, P.trailSpend = {}, {}
    for m = 1, 16 do P.gainRing[m] = Dot(top, "OVERLAY", 5) end
    for m = 1, 8 do P.trailSpend[m] = Dot(top, "OVERLAY", 5) end
    -- the lane (art frame)
    P.word = Line(art, 7, 2, "OVERLAY", 0)
    P.note = Line(art, 14, 1, "OVERLAY", 0)
    P.name = Line(art, 10, 1, "OVERLAY", 0)
    P.more = Line(art, 3, 1, "OVERLAY", 0)
    P.track = Dot(art, "OVERLAY", 1, C.BAR_W, 2)
    P.fill = Dot(art, "OVERLAY", 2, C.BAR_W, 2)
    P.ready = true
end

-- Rescale, re-seat: every region forgets its cached geometry
local function SeatRegions()
    P.epoch = (P.epoch or 0) + 1
    for i = 1, #regions do
        local t = regions[i]
        t.fsX, t.fsY, t.fsName = nil, nil, nil
        if t.fsDot then t:SetSize(S(t.fsW), S(t.fsH)) end
    end
    P.barX, P.barY = nil, nil
    if bar then bar:SetSize(S(Art.BOX), S(Art.BOX)) end
end

-- the bar's box sits round the book at (x, y), the book's top left in sprite px
local function SeatBar(x, y)
    if P.barX == x and P.barY == y then return end
    P.barX, P.barY = x, y
    bar:ClearAllPoints()
    bar:SetPoint("TOPLEFT", mod, "TOPLEFT", S(x - Art.BOX_X), -S(y - Art.BOX_Y))
end

-------------------------------------------------------------------------------
-- Data (the Hud's pushed state; the demon and Life Tap are WarlockState)
-------------------------------------------------------------------------------

local D = {
    shards = nil, tranceAt = nil, decimAt = nil, reap = false, reapDone = 0, reapTicks = 0,
    gainAt = nil, spendAt = nil, bind = false, reduced = false, cue = nil,
}
Warlock.D = D

local function Num(v)
    if type(v) ~= "number" or IsSecret(v) then return nil end
    return v
end

local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

local function ProcActive(p)
    return p.active == true
end

local function OnState(state)
    if type(state) ~= "table" then return end
    local now = GetTime()
    local n = Num(state.shards)
    local was = D.shards
    if n and was then
        if n > was then
            D.gainAt = now
        elseif n < was then
            D.spendAt = now
            local st = State.Get()
            D.bind = st.casting == true or (st.summonAt ~= nil and now - st.summonAt < State.TUNING.SUMMON_GRACE)
        end
    end
    D.shards = n
    local trance, decim = false, false
    local procs = state.procs
    if type(procs) == "table" then
        for i = 1, #procs do
            local p = procs[i]
            if type(p) == "table" and not IsSecret(p.key) then
                if p.key == "shadow_trance" and ProcActive(p) then trance = true end
                if p.key == "decimation" and ProcActive(p) then decim = true end
            end
        end
    end
    if trance then D.tranceAt = D.tranceAt or now else D.tranceAt = nil end
    if decim then D.decimAt = D.decimAt or now else D.decimAt = nil end
    local ch = state.channel
    if type(ch) == "table" and not IsSecret(ch.key) and ch.key == "drain_soul" then
        D.reap, D.reapDone, D.reapTicks = true, Num(ch.done) or 0, Num(ch.ticks) or 0
    else
        D.reap = false
    end
    D.reduced = ReducedMotion()
end
Warlock.OnState = OnState

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function Clamp01(v)
    if v < 0 then return 0 end
    if v > 1 then return 1 end
    return v
end

local function ProcFrac(at, now)
    return Clamp01(1 - (now - at) / C.PROC_S)
end

-- The one cue, by priority. Returns the cue name or nil.
local function ChooseCue(st, count)
    if st.dead then return nil end
    if D.reap and State.Cue("drain") then return "reap" end
    if st.casting and State.Cue("summon") then return "binding" end
    if State.Cue("procs") then
        if D.tranceAt then return "bolt" end
        if D.decimAt then return "fire" end
    end
    if st.pet == "none" and State.Cue("summon") then return "summon" end
    if st.noMana == true and st.tapKnown and State.Cue("tap") then return "tap" end
    if count and count < C.LOW_SHARDS and st.drainKnown and State.Cue("drain") then return "drain" end
    return nil
end

local function SetHp()
    local m = UnitHealthMax("pet")
    local v = UnitHealth("pet")
    bar:SetMinMaxValues(0, m)
    bar:SetValue(v)
end

local function BarFallback()
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(1)
end

local barOn = false
local function PaintBar(on, x, y)
    if not on then
        if barOn then barOn = false; bar:Hide() end
        return
    end
    SeatBar(x, y)
    if not barOn then barOn = true; bar:Show() end
    if not pcall(SetHp) then
        BarFallback()
        LogOnce("hp", "the demon's health could not be read, the book shows full")
    end
end

local function Paint(now)
    local st = State.Get()
    State.Tick(now)
    local R = D.reduced
    local live = not R
    local count = D.shards
    local unknown = count == nil
    local pet = st.pet
    local demon = st.demon
    local dcol = demon and DEMON_COL[demon] or K.violet
    local cost = (demon and COST[demon]) or 1
    local cue = ChooseCue(st, count)
    D.cue = cue
    local warn = (count == 0 and cost > 0) and K.pink or K.amber
    local ccol = cue and (cue == "summon" and warn or CUE_COL[cue]) or nil

    -- the book's place: it shakes on SUMMON and lifts while a Summon or Drain Soul is cast
    local dx, dy = 0, 0
    if live and cue == "summon" and sin(now * 40) > 0.6 then dx = 1 end
    if live and (cue == "binding" or cue == "reap") then dy = -Round(1 + sin(now * 2)) end
    local bx, by = BX + dx, BY + dy

    -- halo, shadow, rune ring
    local hcol = ccol or (pet == "alive" and dcol or K.muted)
    if unknown and pet == "unknown" then hcol = K.muted end
    local breath = R and 0.8 or (0.7 + 0.3 * sin(now * 1.6))
    Cell(P.halo, "halo", BCX, BCY, hcol, (cue and 0.8 or 0.45) * breath * (pet == "unknown" and 0.3 or 1))
    Cell(P.shadow, "shadow", BCX, BY + Art.BOOK_H + 2, K.pure, 1)
    if cue == "binding" then
        Cell(P.ring, RING[live and floor(now * 8) % Art.RING_FRAMES or 0], BCX, BY + Art.BOOK_H + 1, K.fel, 0.9)
    else
        Off(P.ring)
    end

    -- the book
    local pulse = R and 0.9 or (0.55 + 0.45 * (0.5 + 0.5 * sin(now * 6)))
    if pet == "alive" then
        Cell(P.dim, "book_dark", bx, by, K.pure, 1)
        PaintBar(true, bx, by)
        Off(P.rim)
        SetLine(P.unknownQ, nil, 0, 0, K.muted, 0)
    elseif pet == "none" then
        Cell(P.dim, "book_dark", bx, by, K.pure, 1)
        PaintBar(false)
        Cell(P.rim, "book_rim", bx, by, warn, cue == "summon" and pulse or 0.4)
        SetLine(P.unknownQ, nil, 0, 0, K.muted, 0)
    else
        Cell(P.dim, "book_grey", bx, by, K.pure, 1)
        PaintBar(false)
        Off(P.rim)
        SetLine(P.unknownQ, "?", BCX - 4, by + 24, K.muted, 0.9)
    end
    if live and cue == "bolt" then
        Cell(P.flash, "book_white", bx, by, K.bolt, 0.25 + 0.15 * sin(now * 20))
    else
        Off(P.flash)
    end
    -- the cover gem and the eyes: the cue colour, else the demon's
    local gcol = ccol or (pet == "alive" and dcol or nil)
    if gcol then
        local f = R and 1 or (0.7 + 0.3 * sin(now * 3))
        Cell(P.coverGem, "book_gem", bx, by, gcol, 0.6 * f)
        ShowDot(P.eye[1], bx + Art.EYE1_X, by + Art.EYE_Y, gcol, f)
        ShowDot(P.eye[2], bx + Art.EYE2_X, by + Art.EYE_Y, gcol, f)
    else
        Off(P.coverGem); Off(P.eye[1]); Off(P.eye[2])
    end

    -- effects by cue
    if live and cue == "bolt" then
        local k = floor(now * 12) % Art.ZAPS
        Cell(P.zapA, ZAP[k], bx, by, K.white, 0.95)
        Cell(P.zapB, ZAP[(k + 3) % Art.ZAPS], bx, by, K.bolt, 0.8)
    else
        Off(P.zapA); Off(P.zapB)
    end
    if live and cue == "fire" then
        for i = 0, N_FIRE - 1 do
            local k = (now * 1.4 + FIRE_H[i]) % 1
            local t = P.fire[i + 1]
            local big = k < 0.4 and 2 or 1
            DotSize(t, big, big)
            local col = k < 0.3 and K.gold or (k < 0.65 and K.orange or K.ember)
            ShowDot(t, BCX + FIRE_X[i] * (1 - k * 0.5) + sin(now * 6 + i) * 1.2, by + 6 - k * 18, col, 1 - k)
        end
    else
        OffAll(P.fire)
    end
    if live and cue == "tap" then
        for i = 0, 2 do
            local k = (now * 0.9 + i / 3) % 1
            Cell(P.drops[i + 1], "drop", bx + 12 + i * 11, by + Art.BOOK_H + k * 14, K.pure, sin(k * pi) * 0.95)
        end
    else
        OffAll(P.drops)
    end
    if live and cue == "reap" then
        local tx, ty = bx + Art.GEM_X, by + Art.GEM_Y
        for i = 0, 8 do
            local k = (now * 0.8 + i / 9) % 1
            local s = sin(k * pi)
            ShowDot(P.motes[i + 1], 80 + (tx - 80) * k + sin(k * 9 + i) * 4 * s, 8 + (ty - 8) * k + cos(k * 7 + i * 2) * 5 * s,
                (i % 2 ~= 0) and K.white or K.violet, 0.35 + 0.65 * k)
        end
    else
        OffAll(P.motes)
    end
    -- no demon: a slow smoke drifts up off the closed book
    if live and pet == "none" and cue ~= "binding" then
        for i = 0, N_WISP - 1 do
            local k = (now * 0.35 + WISP_H[i]) % 1
            local t = P.wisps[i + 1]
            local big = k < 0.5 and 2 or 1
            DotSize(t, big, big)
            ShowDot(t, BCX + WISP_X[i] + sin(now * 1.3 + i * 1.7) * 3 * k, by + 4 - k * 26,
                (i % 3 == 0) and warn or K.violet, sin(k * pi) * 0.7)
        end
    else
        OffAll(P.wisps)
    end
    if live and cue == "binding" then
        for i = 0, 9 do
            local k = (now * 0.9 + i / 10) % 1
            ShowDot(P.sparks[i + 1], BCX + SPARK_X[i], BY + Art.BOOK_H - k * 30, (i % 2 ~= 0) and K.fel or K.white, 1 - k)
        end
    else
        OffAll(P.sparks)
    end
    local tk = st.tapAt and (now - st.tapAt) / C.TAP_S
    if tk and tk >= 0 and tk < 1 then
        local r = 14 + tk * 22
        for m = 1, 24 do
            ShowDot(P.burst[m], BCX + BURST_COS[m] * r, BCY + BURST_SIN[m] * r, K.pink, (1 - tk) * 0.9)
        end
    else
        OffAll(P.burst)
    end

    -- the soul crystals
    local lit = unknown and 0 or min(count, 5)
    local pendingOn = cue == "summon" and cost > 0
    for i = 1, 5 do
        local x, y = CRY_X[i], C.CRY_Y
        Cell(P.sock[i], unknown and "crys_q" or "crys_empty", x, y, K.pure, 1)
        local gem, ga, sh = nil, 1, 0
        if not unknown and i <= lit then
            local pending = pendingOn and i == lit
            gem = "crys_lit"
            if pending and (R or sin(now * 7) > 0) then gem = "crys_amber" end
            if live and not pending then
                local s = max(0, sin(now * 1.9 + (i - 1) * 1.3))
                local s2 = s * s
                local s4 = s2 * s2
                sh = 0.6 * (s4 * s4 * s2)                  -- s^10: a short flash
            end
            if count >= 5 and cue ~= "summon" then sh = sh + 0.12 end
        elseif cue == "drain" and live and not unknown and i == lit + 1 then
            gem, ga = "crys_lit", 0.15 + 0.25 * (0.5 + 0.5 * sin(now * 3))
        end
        Cell(P.gem[i], gem, x, y, K.pure, ga)
        Cell(P.shine[i], sh > 0.03 and "crys_white" or nil, x, y, K.pure, sh)
    end
    if not unknown and count > 5 then
        SetLine(P.more, MORE[min(count, 99)], C.TX + 5 * C.CRY_GAP, C.CRY_Y + 4, K.violet, 1)
    else
        SetLine(P.more, nil, 0, 0, K.muted, 0)
    end

    -- gain and spend events
    local gk = D.gainAt and (now - D.gainAt) / C.GAIN_S
    if gk and not unknown and gk >= 0 and gk < 1 then
        local i = min(max(count, 1), 5)
        local cx, cy = CRY_X[i] + CRY_CX, C.CRY_Y + CRY_CY
        Cell(P.evGem, gk < 0.35 and "crys_white" or nil, CRY_X[i], C.CRY_Y, K.pure, 1 - gk / 0.35)
        local r = 3 + gk * 10
        for m = 1, 16 do ShowDot(P.gainRing[m], cx + GAIN_COS[m] * r, cy + GAIN_SIN[m] * r, K.white, (1 - gk) * 0.8) end
    else
        Off(P.evGem); OffAll(P.gainRing)
    end
    local sk = D.spendAt and (now - D.spendAt) / C.SPEND_S
    if sk and not unknown and sk >= 0 and sk < 1 then
        local i = min(count, 4) + 1
        local cx, cy = CRY_X[i] + CRY_CX, C.CRY_Y + CRY_CY
        Cell(P.evSpend, "crys_amber", CRY_X[i], C.CRY_Y, K.pure, 1 - sk)
        if D.bind then
            -- a Summon spend: the soul flies into the book's gem
            local gx, gy = bx + Art.GEM_X, by + Art.GEM_Y
            for m = 1, 8 do
                local kk = Clamp01(sk * 1.3 - (m - 1) * 0.06)
                ShowDot(P.trailSpend[m], cx + (gx - cx) * kk, cy + (gy - cy) * kk, K.amber, 1 - kk)
            end
        else
            for m = 1, 8 do
                ShowDot(P.trailSpend[m], cx + SPARK8_COS[m] * sk * 9, cy + SPARK8_SIN[m] * sk * 9 - sk * 4,
                    (m % 2 == 0) and K.amber or K.white, 1 - sk)
            end
        end
    else
        Off(P.evSpend); OffAll(P.trailSpend)
    end

    -- the lane
    local X = C.TX
    local word, note, frac
    if cue == "summon" then
        word = "SUMMON"
        if demon and cost == 0 then
            note = NOTE_SUMMON[demon]
        elseif count == 0 then
            note = "NO SHARD"
        else
            note = NOTE_SUMMON[demon or "none"]
        end
    elseif cue == "bolt" then
        word, frac = "BOLT", ProcFrac(D.tranceAt, now)
    elseif cue == "fire" then
        word, frac = "FIRE", ProcFrac(D.decimAt, now)
    elseif cue == "tap" then
        word = "TAP"
    elseif cue == "reap" then
        word = "REAPING"
        if D.reapTicks > 0 then frac = Clamp01(D.reapDone / D.reapTicks) end
    elseif cue == "binding" then
        word = "BINDING"
    elseif cue == "drain" then
        word = "DRAIN"
    end
    if word then
        SetLine(P.word, word, X, 10, ccol, cue == "drain" and 0.85 or 1)
        if cue == "summon" then
            LineAlpha(P.word, (live and sin(now * 7) <= 0) and 0.6 or 1)
        else
            P.word.blinkA = nil
        end
        SetLine(P.note, note, X, 28, K.white, 0.9)
        SetLine(P.name, nil, 0, 0, K.muted, 0)
        if frac then
            ShowDot(P.track, X, 22, K.track, 1)
            local w = Round(C.BAR_W * frac)
            if w > 0 then
                DotSize(P.fill, w, 2)
                local amber = (cue == "bolt" or cue == "fire") and frac < C.FRAC_AMBER
                ShowDot(P.fill, X, 22, amber and K.amber or ccol, 1)
            else
                Off(P.fill)
            end
        else
            Off(P.track); Off(P.fill)
        end
    else
        SetLine(P.word, nil, 0, 0, K.muted, 0)
        SetLine(P.note, nil, 0, 0, K.muted, 0)
        Off(P.track); Off(P.fill)
        if pet == "alive" then
            SetLine(P.name, DEMON_NAME[demon or "bound"], X, 13, dcol, 1)
        elseif pet == "unknown" then
            SetLine(P.name, "NO READ", X, 13, K.muted, 1)
        else
            SetLine(P.name, "NO DEMON", X, 13, K.muted, 1)
        end
    end
end

local function SafePaint(now)
    if not P.ready then return end
    local ok, err = pcall(Paint, now)
    if not ok then LogOnce("paint", err) end
end
Warlock.Paint = SafePaint

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

function Warlock.Origin() return OX, OY end

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y + C.DROP
    if mod then
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
        art:SetSize(ui(C.W), ui(C.H))
        top:SetAllPoints(mod)
        SeatRegions()
        if subscribed then SafePaint(GetTime()) end
    end
end

local function OnWarlockState()
    if subscribed then SafePaint(GetTime()) end
end

local function BuildModule(host)
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightWarlock", host)
    art = CreateFrame("Frame", nil, mod)
    top = CreateFrame("Frame", nil, mod)
    local base = mod.GetFrameLevel and mod:GetFrameLevel() or 1
    pcall(function()
        art:SetFrameLevel(base + 1)
        top:SetFrameLevel(base + 3)
    end)
    Point(mod, "TOPLEFT", OX, OY)
    mod:SetSize(ui(C.W), ui(C.H))
    art:SetPoint("TOPLEFT", mod, "TOPLEFT", 0, 0)
    art:SetSize(ui(C.W), ui(C.H))
    top:SetAllPoints(mod)
    local ok, err = pcall(Build)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod, art, top, bar = nil, nil, nil, nil
        P = {}
        return nil
    end
    pcall(function() bar:SetFrameLevel(base + 2) end)
    SeatRegions()
    Warlock.frame, Warlock.parts = mod, P
    SafePaint(GetTime())
    return mod
end

local function OnAreaShown()
    if not mod then return end
    State.Refresh()
    D.reduced = ReducedMotion()
    if not subscribed then
        local Hud = FS.Hud
        if not (Hud and Hud.Subscribe) then
            LogOnce("nohud", "FS.Hud is missing, the Warlock module has no shard data")
        else
            subscribed = true
            State.Subscribe(OnWarlockState)
            Hud.Subscribe(OnState)                  -- pushes the current state at once
        end
    end
    SafePaint(GetTime())
    Sync()
end

local function OnAreaHidden()
    if not mod then return end
    D.shards = nil      -- the first push after the next show has nothing to compare with, so no stale gain or spend plays
    if subscribed then
        subscribed = false
        State.Unsubscribe(OnWarlockState)
        if FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnState) end
    end
    Sync()
end

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "WARLOCK" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
