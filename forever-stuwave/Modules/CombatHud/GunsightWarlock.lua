-- Forever STUwave: the Warlock Class Module for the Gunsight target side ("the Binding Circle")
--
-- Design mockup: mockups/gunsight-class-module-warlock-2026-11-16.html (concepts page next to it; research in the adze doc
-- "Warlock stock-UI pain points (research 2026-11-16)"). One 150 x 86 sprite px canvas, `C.SPX` image px per sprite px.
--   THE CIRCLE (left, centre 40,43): the five points of the pentagram are the soul shard sockets (a gem is lit for each shard
--   held, up to five; more shows in the number); the middle is a medallion of the demon: dark when it is gone, lit from the
--   bottom up by the demon's health when it is out, a ghost with a dashed rim when the demon is dead or not summoned. Ten
--   runes orbit; the ring colour is the cue colour.
--   THE CUE LANE (right): ONE cue at a time by priority, REAPING (a Drain Soul channel) > BINDING (a Summon cast) > BOLT (a free
--   instant Shadow Bolt, Shadow Trance) > FIRE (a free fast Soul Fire, Decimation) > SUMMON (no demon; names the demon and the
--   shard it costs) > TAP (the next Shadow Bolt cannot be paid) > DRAIN (fewer than three shards). The two proc cues carry a
--   drain bar for their 10 s window, REAPING one for the channel's ticks. Under it SOULS and the shard number at 3x.
-- It does not draw mana or DoT timers: the mana regen module and GunsightDots already do.
--
-- DATA. Shards, procs, the Drain Soul channel come from the Hud's pushed state (a plain item count, plain proc flags, the
-- channel ledger). The demon, a Summon cast, "a bolt cannot be paid" and Life Tap are `FS.WarlockState` (plain reads only,
-- all UNPROBED on this client). The demon's HEALTH is secret: `UnitHealth("pet")` and its max go only to a vertical StatusBar's
-- SetValue / SetMinMaxValues (the Priest shield technique: the lit sigil texture stretched over the bar so the engine's crop
-- is the art). It is never compared, printed or stored. Nothing here reads the player's own health or mana.
--
-- ART is baked by tools/assets/generate_warlock_circle.py (an atlas of masks and full colour sprites, five 64 x 64 lit
-- sigils, and the generated manifest WarlockArt.lua); the module tints the masks with SetVertexColor. One 30 Hz OnUpdate runs
-- while the module is shown; a tick allocates nothing (strings and positions are tables built once; the harness measures it).
--
-- Reduced motion (ForeverSTUwaveDB.reducedMotion == true): no orbiting rune head, no breathing halo, no shimmer, no comet, no
-- bolts, fire, motes or drops, no blink; the colours, the cue, the gems and the medallion still say everything.
-- Every cue and sub-part has an off switch (WarlockState.SETTINGS, shown on the Gunsight HUD page for a Warlock).

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
    TX = 84,                    -- the right lane's left edge, sprite px
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Warlock.C = C

local K = {
    violet = Hex("#a855f7"), amber = Hex("#ffb648"), pink = Hex("#ff2e97"), orange = Hex("#ff6a2e"), bolt = Hex("#c58bff"),
    white = Hex("#f3fbff"), muted = Hex("#9d93c4"), track = Hex("#2c2048"), gold = Hex("#ffd23f"), pure = { 1, 1, 1 },
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
if State.Start then State.Start() end

local SPR, SCALE, ATL = Art.sprites, Art.SCALE, Art.ATLAS
local CX, CY, R_IN = Art.CX, Art.CY, Art.R_IN
local BX, BY = CX - 15, CY - 15                      -- the medallion box's top left
local ATLAS_PATH = MEDIA .. ATL.file .. ".tga"

local function Hash(n)
    local v = sin(n * 12.9898 + 78.233) * 43758.5453
    return v - floor(v)
end
local function Round(v) return floor(v + 0.5) end

-------------------------------------------------------------------------------
-- Tables built once (a tick builds none)
-------------------------------------------------------------------------------

local SOCK_X, SOCK_Y = {}, {}
for i = 1, 5 do
    local a = Art.POINTS[i] * pi / 180
    SOCK_X[i], SOCK_Y[i] = CX + Round(cos(a) * R_IN), CY + Round(sin(a) * R_IN)
end
local RUNE_X, RUNE_Y = {}, {}
for i = 1, Art.RUNES do
    local a = Art.RUNE_ANG[i] * pi / 180
    RUNE_X[i], RUNE_Y[i] = CX + Round(cos(a) * Art.R_RUNE), CY + Round(sin(a) * Art.R_RUNE)
end
local ZAP = {}
for i = 0, Art.ZAPS - 1 do ZAP[i] = "zap" .. i end
local DIM, GHOST = {}, {}
for _, d in ipairs(Art.DEMONS) do DIM[d], GHOST[d] = "dim_" .. d, "ghost_" .. d end
local FIRE_H, FIRE_X = {}, {}
for i = 0, 9 do
    FIRE_H[i] = Hash(i * 7)
    FIRE_X[i] = cos(Hash(i * 13 + 5) * 6.28) * (6 + Hash(i) * 12)
end
local BURST_COS, BURST_SIN = {}, {}
for m = 1, 24 do
    local a = (m - 1) / 24 * 6.283
    BURST_COS[m], BURST_SIN[m] = cos(a), sin(a)
end

-- glyphs: the character's sprite and advance
local GLYPH = {}
local function GlyphName(ch)
    local map = { ["?"] = "q", ["-"] = "minus", ["+"] = "plus", ["."] = "dot" }
    return "f_" .. (map[ch] or ch)
end
for ch in pairs(Art.GLYPH_W) do GLYPH[ch] = GlyphName(ch) end
local function TextW(str, k)
    local w = 0
    for i = 1, #str do
        local ch = str:sub(i, i)
        if ch == " " then w = w + 2 * k else w = w + ((Art.GLYPH_W[ch] or 3) + 1) * k end
    end
    return w - k
end
local NUM, FULL_X = {}, {}
for n = 0, 99 do
    NUM[n] = tostring(n)
    FULL_X[n] = C.TX + TextW(NUM[n], 3) + 5
end
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

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build()
    P.epoch = 0
    -- the circle (art frame)
    P.halo = Spr(art, "BACKGROUND", 0)
    P.ringOut = Spr(art, "BACKGROUND", 1)
    P.ringIn = Spr(art, "BACKGROUND", 2)
    P.rune = {}
    for i = 1, Art.RUNES do P.rune[i] = Spr(art, "BORDER", 0) end
    P.star = Spr(art, "BORDER", 2)
    P.zapA, P.zapB = Spr(art, "ARTWORK", -2), Spr(art, "ARTWORK", -1)
    P.sock, P.gem, P.shine = {}, {}, {}
    for i = 1, 5 do
        P.sock[i] = Spr(art, "ARTWORK", 0)
        P.gem[i] = Spr(art, "ARTWORK", 1)
        P.shine[i] = Spr(art, "ARTWORK", 2)
    end
    P.dim = Spr(art, "ARTWORK", 3)
    -- the lit medallion: the engine fills it from the demon's secret health
    bar = CreateFrame("StatusBar", nil, mod)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. "warlock_sigil_bound.tga")
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar:Hide()
    P.bar = bar
    -- the rest of the medallion and every effect (top frame)
    P.rim = Spr(top, "OVERLAY", 0)
    P.ghost = Spr(top, "OVERLAY", 1)
    P.dash = Spr(top, "OVERLAY", 2)
    P.dashFx = Spr(top, "OVERLAY", 3)
    P.dashBind = Spr(top, "OVERLAY", 3)
    P.evGem = Spr(top, "OVERLAY", 4)
    P.evSpend = Spr(top, "OVERLAY", 4)
    P.trailGain, P.trailSpend = {}, {}
    for m = 1, 6 do
        P.trailGain[m] = Dot(top, "OVERLAY", 5)
        P.trailSpend[m] = Dot(top, "OVERLAY", 5)
    end
    P.comet = {}
    for i = 1, 4 do P.comet[i] = Dot(top, "OVERLAY", 5) end
    P.fire = {}
    for i = 1, 10 do P.fire[i] = Dot(top, "OVERLAY", 5) end
    P.drops = {}
    for i = 1, 4 do P.drops[i] = Spr(top, "OVERLAY", 5) end
    P.motes = {}
    for i = 1, 9 do P.motes[i] = Dot(top, "OVERLAY", 5) end
    P.burst = {}
    for m = 1, 24 do P.burst[m] = Dot(top, "OVERLAY", 6) end
    P.unknownQ = Line(top, 1, 3, "OVERLAY", 7)
    -- the right lane (art frame)
    P.word = Line(art, 7, 2, "OVERLAY", 0)
    P.note = Line(art, 14, 1, "OVERLAY", 0)
    P.name = Line(art, 10, 1, "OVERLAY", 0)
    P.souls = Line(art, 5, 1, "OVERLAY", 0)
    P.num = Line(art, 2, 3, "OVERLAY", 0)
    P.full = Line(art, 4, 1, "OVERLAY", 0)
    P.track = Dot(art, "OVERLAY", 1, 62, 2)
    P.fill = Dot(art, "OVERLAY", 2, 62, 2)
    P.sep = {}
    for i = 1, 31 do P.sep[i] = Dot(art, "OVERLAY", 1) end
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
    if bar then
        bar:ClearAllPoints()
        bar:SetPoint("TOPLEFT", mod, "TOPLEFT", S(BX), -S(BY))
        bar:SetSize(S(Art.MED_BOX), S(Art.MED_BOX))
    end
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
local barDemon
local function PaintBar(on, demon)
    if on and demon ~= barDemon then
        barDemon = demon
        bar:SetStatusBarTexture(MEDIA .. "warlock_sigil_" .. demon .. ".tga")
    end
    if not on then
        if barOn then barOn = false; bar:Hide() end
        return
    end
    if not barOn then barOn = true; bar:Show() end
    if not pcall(SetHp) then
        BarFallback()
        LogOnce("hp", "the demon's health could not be read, the medallion shows full")
    end
end

local function Paint(now)
    local st = State.Get()
    State.Tick(now)
    local R = D.reduced
    local live = not R
    local count = D.shards
    local pet = st.pet
    local demon = st.demon or "bound"
    local dcol = DEMON_COL[demon]
    local cue = ChooseCue(st, count)
    D.cue = cue

    -- ring colour
    local ring, ringA = K.violet, 0.78
    if cue then
        if cue == "summon" and count == 0 and demon ~= "imp" then ring = K.pink else ring = CUE_COL[cue] end
        ringA = 0.95
    end
    if pet == "unknown" or count == nil then ring, ringA = K.muted, 0.5 end
    local blink = 1
    if cue == "summon" and live and sin(now * 7) <= 0 then blink = 0.55 end

    -- halo and rings
    local breath = R and 0.8 or (0.7 + 0.3 * sin(now * 1.6))
    local haloA = (cue and 0.8 or 0.45) * breath * (pet == "unknown" and 0.3 or 1)
    Cell(P.halo, "halo", CX, CY, ring, haloA)
    Cell(P.ringOut, "ring_out", CX, CY, ring, ringA * blink)
    Cell(P.ringIn, "ring_in", CX, CY, ring, 0.55 * blink)

    -- runes: a bright head travels round them
    local speed = cue == "binding" and 1.2 or (cue and 0.55 or 0.22)
    for i = 1, Art.RUNES do
        local al = 0.5
        if live then
            local d = ((i - 1) - now * speed * 10) % 10
            if d > 5 then d = 10 - d end
            al = 0.32 + 0.68 * max(0, 1 - d / 2.6)
        end
        Cell(P.rune[i], "rune" .. (i - 1), RUNE_X[i], RUNE_Y[i], ring, al)
    end

    -- star and bolts
    local starA = (cue == "bolt") and 0.9 or ((count and count >= 5) and 0.8 or 0.5)
    Cell(P.star, "star", CX, CY, ring, starA)
    if cue == "bolt" and live then
        local k = floor(now * 14) % 6
        Cell(P.zapA, ZAP[k], CX, CY, K.white, 0.95)
        Cell(P.zapB, ZAP[(k + 3) % 6], CX, CY, K.bolt, 0.7)
    else
        Off(P.zapA); Off(P.zapB)
    end

    -- sockets and gems
    local unknown = count == nil
    local lit = unknown and 0 or min(count, 5)
    for i = 1, 5 do
        local x, y = SOCK_X[i], SOCK_Y[i]
        Cell(P.sock[i], unknown and "socket_q" or "socket", x, y, K.pure, 1)
        local gem, ga, sh = nil, 1, 0
        if not unknown and i <= lit then
            local pending = cue == "summon" and (COST[demon] or 1) > 0 and i == lit
            gem = "gem_violet"
            if pending and (R or sin(now * 7) > 0) then gem = "gem_amber" end
            if live and not pending then
                local s = max(0, sin(now * 1.9 + (i - 1) * 1.3))
                local s2 = s * s
                local s4 = s2 * s2
                sh = 0.5 * (s4 * s4 * s2)                  -- s^10: a short flash
            end
            if count >= 5 and cue ~= "summon" then sh = sh + 0.12 end
        elseif cue == "drain" and live and not unknown and i == lit + 1 then
            gem, ga = "gem_violet", 0.15 + 0.2 * (0.5 + 0.5 * sin(now * 3))
        end
        Cell(P.gem[i], gem, x, y, K.pure, ga)
        Cell(P.shine[i], sh > 0.025 and "gem_white" or nil, x, y, K.pure, sh)
    end

    -- gain and spend events
    local gk = D.gainAt and (now - D.gainAt) / C.GAIN_S
    if gk and not unknown and gk >= 0 and gk < 1 then
        local i = min(max(count, 1), 5)
        local x, y = SOCK_X[i], SOCK_Y[i]
        Cell(P.evGem, gk < 0.3 and "gem_white" or nil, x, y, K.pure, 1 - gk / 0.3)
        for m = 1, 6 do
            local kk = Clamp01(gk * 1.4 - (m - 1) * 0.08)
            ShowDot(P.trailGain[m], CX + (x - CX) * kk, CY + (y - CY) * kk, K.white, (1 - kk) * 0.9 + 0.1)
        end
    else
        Off(P.evGem); OffAll(P.trailGain)
    end
    local sk = D.spendAt and (now - D.spendAt) / C.SPEND_S
    if sk and not unknown and sk >= 0 and sk < 1 then
        local i = min(count, 4) + 1
        local x, y = SOCK_X[i], SOCK_Y[i]
        Cell(P.evSpend, "gem_amber", x, y, K.pure, 1 - sk)
        for m = 1, 6 do
            local kk = Clamp01(sk * 1.3 - (m - 1) * 0.06)
            local f = D.bind and kk or -kk * 0.6
            ShowDot(P.trailSpend[m], x + (CX - x) * f, y + (CY - y) * f, D.bind and K.amber or K.white, 1 - kk)
        end
        if D.bind and sk > 0.75 then Cell(P.dashBind, "med_dash", BX, BY, K.white, (1 - sk) * 3) else Off(P.dashBind) end
    else
        Off(P.evSpend); OffAll(P.trailSpend); Off(P.dashBind)
    end

    -- the medallion
    local dimN = pet == "alive" and demon or (pet == "none" and demon or "bound")
    Cell(P.dim, DIM[dimN], BX, BY, K.pure, 1)
    if pet == "alive" then
        PaintBar(true, demon)
        Cell(P.rim, "med_rim", BX, BY, dcol, 0.95)
        Off(P.ghost); Off(P.dash)
        SetLine(P.unknownQ, nil, 0, 0, K.muted, 0)
    elseif pet == "none" then
        PaintBar(false)
        Off(P.rim)
        local pulse = R and 0.9 or (0.55 + 0.45 * (0.5 + 0.5 * sin(now * 6)))
        local gc = (count == 0 and demon ~= "imp") and K.pink or K.amber
        Cell(P.ghost, GHOST[dimN], BX, BY, gc, pulse)
        Cell(P.dash, "med_dash", BX, BY, gc, pulse)
        SetLine(P.unknownQ, nil, 0, 0, K.muted, 0)
    else
        PaintBar(false)
        Off(P.rim); Off(P.ghost); Off(P.dash)
        SetLine(P.unknownQ, "?", CX - 4, CY - 7, K.muted, 0.9)
    end
    if cue == "binding" and live then
        Cell(P.dashFx, "med_dash", BX, BY, K.white, 0.9 * (1 - (now * 1.5) % 1))
    else
        Off(P.dashFx)
    end

    -- effects by cue
    if live and cue == "fire" then
        for i = 0, 9 do
            local k = (now * 0.6 + FIRE_H[i]) % 1
            ShowDot(P.fire[i + 1], CX + FIRE_X[i] * (1 - k * 0.3), CY + 12 - k * 36, (i % 3 ~= 0) and K.orange or K.gold, 1 - k)
        end
    else
        OffAll(P.fire)
    end
    if live and cue == "tap" then
        for i = 0, 3 do
            local k = (now * 0.7 + i * 0.25) % 1
            Cell(P.drops[i + 1], "drop", CX - 9 + i * 6, CY - 13 + k * 26, K.pink, sin(k * 3.14) * 0.9)
        end
    else
        OffAll(P.drops)
    end
    if live and cue == "reap" then
        for i = 0, 8 do
            local k = (now * 0.9 + i / 9) % 1
            local a = i * 0.7 + 1
            ShowDot(P.motes[i + 1], CX + sin(a + k * 6) * (20 * (1 - k)), CY - 34 + k * 30, (i % 2 ~= 0) and K.white or K.violet, 0.4 + 0.6 * k)
        end
    else
        OffAll(P.motes)
    end
    if live and (cue == "summon" or cue == "binding" or cue == nil) then
        local sp = cue == "binding" and 2.4 or (cue and 0.9 or 0.5)
        local cc = ring == K.muted and K.muted or K.white
        for i = 1, 4 do
            local a = (now * sp - (i - 1) * 0.07) * 6.283 - 1.57
            ShowDot(P.comet[i], CX + Round(cos(a) * 39), CY + Round(sin(a) * 39), cc, 0.95 - (i - 1) * 0.24)
        end
    else
        OffAll(P.comet)
    end
    local tk = st.tapAt and (now - st.tapAt) / C.TAP_S
    if tk and tk >= 0 and tk < 1 then
        local r = 16 + tk * 22
        for m = 1, 24 do
            ShowDot(P.burst[m], CX + BURST_COS[m] * r, CY + BURST_SIN[m] * r, K.pink, (1 - tk) * 0.9)
        end
    else
        OffAll(P.burst)
    end

    -- the right lane
    local X = C.TX
    local word, note, wcol, frac
    if cue == "summon" then
        word, wcol = "SUMMON", K.amber
        local cost = st.demon and (COST[st.demon] or 1) or 1
        if st.demon and cost == 0 then
            note = NOTE_SUMMON[st.demon]
        elseif count == 0 then
            note, wcol = "NO SHARD", K.pink
        else
            note = NOTE_SUMMON[st.demon or "none"]
        end
    elseif cue == "bolt" then
        word, note, wcol, frac = "BOLT", "INSTANT", K.bolt, ProcFrac(D.tranceAt, now)
    elseif cue == "fire" then
        word, note, wcol, frac = "FIRE", "FREE SOUL FIRE", K.orange, ProcFrac(D.decimAt, now)
    elseif cue == "tap" then
        word, note, wcol = "TAP", "MANA LOW", K.pink
    elseif cue == "reap" then
        word, note, wcol = "REAPING", "KEEP CASTING", K.violet
        if D.reapTicks > 0 then frac = Clamp01(D.reapDone / D.reapTicks) end
    elseif cue == "binding" then
        word, note, wcol = "BINDING", "CASTING", K.white
    elseif cue == "drain" then
        word, note, wcol = "DRAIN", "SOULS LOW", K.violet
    end
    if word then
        SetLine(P.word, word, X, 9, wcol, cue == "drain" and 0.85 or 1)
        SetLine(P.note, note, X, 28, K.white, 0.9)
        SetLine(P.name, nil, 0, 0, K.muted, 0)
        if frac then
            DotSize(P.track, 62, 2); ShowDot(P.track, X, 22, K.track, 1)
            local w = Round(62 * frac)
            if w > 0 then
                DotSize(P.fill, w, 2)
                local amber = (cue == "bolt" or cue == "fire") and frac < C.FRAC_AMBER
                ShowDot(P.fill, X, 22, amber and K.amber or wcol, 1)
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
            SetLine(P.name, DEMON_NAME[demon], X, 10, dcol, 1)
        elseif pet == "unknown" then
            SetLine(P.name, "NO READ", X, 10, K.muted, 1)
        else
            SetLine(P.name, "NO DEMON", X, 10, K.muted, 1)
        end
    end
    SetLine(P.souls, "SOULS", X, 46, K.muted, 1)
    local num = unknown and "?" or NUM[min(count, 99)]
    SetLine(P.num, num, X, 54, unknown and K.muted or (count == 0 and K.muted or K.white), 1)
    if not unknown and count > 5 then
        SetLine(P.full, "FULL", FULL_X[min(count, 99)], 56, K.violet, 0.9)
    else
        SetLine(P.full, nil, 0, 0, K.muted, 0)
    end
    if not P.sepDone or P.sepEpoch ~= P.epoch then
        P.sepDone, P.sepEpoch = true, P.epoch
        for i = 1, 31 do ShowDot(P.sep[i], X + (i - 1) * 2, 40, K.violet, 0.3) end
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
