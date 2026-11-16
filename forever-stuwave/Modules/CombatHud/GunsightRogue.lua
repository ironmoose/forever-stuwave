-- Forever STUwave: Gunsight Class Module for the Rogue: the dagger fan
--
-- The design is the design mockup "Rogue dagger fan" (2026-11-16), picked from three concepts (the fan, a lock, a long blade), on the
-- 150 x 86 sprite px canvas:
--   * THE FAN (left, the cuff at 46, 62): five throwing daggers, one per combo point. A dagger lights when the count reaches it. At five
--     the whole fan turns gold and breathes and the plaque FINISH shows (right, under the blade star). A finisher or Slice and Dice cast
--     throws the fan: a white flash and five pink streaks along the blades. Stealthed the fan goes to shadow (violet veil, violet lit
--     daggers, smoke) and the plaque says OPENER. The count is also a digit on the cuff.
--   * SLICE AND DICE (right): a four bladed star that spins while it runs (pink, amber under SND_WARN seconds), with a bar that drains
--     and the seconds above it (a "~" in front while it is an estimate). Down in combat the dashed ring round the empty star and the SND
--     header pulse amber (only when the spell is known); calm out of combat. Not learned: a muted dotted rail and ring.
--   * ENERGY (the bottom rail): the current energy as a gold rail with its number, two cost gems at what the last builder (cyan) and the
--     last finisher (pink) cost; a gem lights when the energy covers it, and at full energy the whole rail goes pale gold.
--
-- WHAT THE ENGINE DRAWS. In combat the combo count and the energy are secret: no comparison ever sees them. The five daggers, the FINISH
-- plaque and the gold overlay (a StatusBar from 4 to 5), the energy rail, the lit gems (a StatusBar from cost - 1 to cost) and the full
-- rail (from max - 1 to max) are StatusBars fed the value, so the ENGINE decides what shows. The digit and the energy number go to
-- SetFormattedText, which accepts a secret. Lua only sets the bars' ranges (plain: the max and the spell costs) and colours.
--
-- DATA. FS.RogueState (RogueState.lua) holds the own-cast ledger (Slice and Dice, the spend stamp, the builder stamp), the plain costs
-- and stealth; this file reads no aura and no secret. A cast that throws the fan is plain (a spell id), so the throw does not depend
-- on the count; how many blades fly is the last plain count, else five.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide stops the
-- OnUpdate, the events and the subscription; onShow starts them and re-reads. Plain frames only.
--
-- TICKER. One OnUpdate at C.TICK while shown (the star spins and the fan breathes). The tick allocates nothing: positions are numbers,
-- texts come from tables built once, regions are written only when a value changes.
--
-- Reduced motion (ForeverSTUwaveDB.reducedMotion == true): no breath, no recoil, no smoke, no spin (the star holds its first turn), the
-- amber blink holds steady. The thrown fan still plays, since it is the cast.
--
-- UNVERIFIED in game: every Rogue spell name and id, IsStealthed, the cost read, the NEAREST filter on the fill textures, the engine
-- crop of a StatusBar over a 128 x 64 file, and that a secret combo count and energy feed a StatusBar (the shared combo module did).

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
local Art = FS.RogueArt
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightRogue = FS.GunsightRogue or {}
local Rogue = FS.GunsightRogue

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, sin, cos, pi, max, min, abs = math.floor, math.sin, math.cos, math.pi, math.max, math.min, math.abs

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local function Mix(a, b, k)
    return { a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    FAN = { x = 6, y = 6 }, PIVOT = { x = 40, y = 56 },
    STAR = { x = 121, y = 38 },
    SND = { x = 96, y = 13, w = 50, h = 7 }, SND_HEAD_Y = 6,
    FINISH = { x = 89, y = 50 },
    RAIL = { x = 17, y = 77, w = 130, h = 7 }, NUM_RIGHT = 14,
    GEM_Y = 68,
    LABEL_SIZE = 11, CUFF_SIZE = 12, BASELINE = 5, CAP = 325 / 1024,
    SND_WARN = 4,                      -- the amber under this many seconds
    SPIN_HZ = 14, BREATH = 5,          -- star frames a second, the breath's angular rate
    THROW = 0.6, FLASH = 0.24, RECOIL = 0.09,
    STREAK = 12, STREAK_U0 = 18, STREAK_U1 = 78, STREAK_T = 0.45, SMOKE = 16,
    ENERGY_MAX = 100,                  -- the rail's max when UnitPowerMax cannot be read plain
    COLORS = {
        white = Hex("#f3fbff"), muted = Hex("#9d93c4"), amber = Hex("#ffb648"), gold = Hex("#ffd23f"), pale = Hex("#fff0a8"),
        pink = Hex("#ff5fae"), hot = Hex("#ff2e97"), cyan = Hex("#22e0ff"), fin = Hex("#ff4dd8"), violet = Hex("#a855f7"),
        veil = Hex("#a855f7"), stealthLit = Hex("#b79bff"), opener = Hex("#c9a5ff"), line = Hex("#3a2168"), lineOff = Hex("#2a1846"),
        track = Hex("#0a0416"), off = Hex("#2c2048"), notchDim = Hex("#4b2a86"), black = Hex("#000000"), pure = { 1, 1, 1 },
    },
}
C.W, C.H = C.SW * C.SPX, C.SH * C.SPX
Rogue.C = C
local K = C.COLORS
K.goldBase = Mix(K.gold, K.black, 0.18)
K.goldHi = Mix(K.gold, K.pure, 0.55)
K.pinkBase = Mix(K.pink, K.black, 0.35)
K.pinkHi = Mix(K.pink, K.pure, 0.5)
K.amberBase = Mix(K.amber, K.black, 0.35)
K.amberHi = Mix(K.amber, K.pure, 0.5)

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local IsSecret = FS.IsSecret or function() return false end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightrogue_" .. key, "|cffff4488Forever STUwave|r: gunsight rogue module: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.ATLAS) == "table") then
    LogOnce("noart", "FS.RogueArt is missing, the Rogue module is not built")
    return
end
local ATLAS, SCALE = Art.ATLAS, Art.SCALE
local ANGLES = Art.ANGLES
local COMBO_POWER = (Enum and Enum.PowerType and Enum.PowerType.ComboPoints) or 4
local ENERGY_POWER = (Enum and Enum.PowerType and Enum.PowerType.Energy) or 3
local POWER_EVENTS = { "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "UNIT_MAXPOWER" }

-- texts, built once
local SEC, SEC_EST = {}, {}
for i = 0, 60 do SEC[i], SEC_EST[i] = tostring(i), "~" .. i end

local STAR_NAME = { [0] = "star0", "star1", "star2", "star3" }

-- the streaks' px, built once: dagger j, distance u along its blade, as sprite px from the module's top left
local STREAK_X, STREAK_Y = {}, {}
for j = 1, #ANGLES do
    local a = ANGLES[j] * pi / 180
    STREAK_X[j], STREAK_Y[j] = {}, {}
    for u = 0, 100 do
        STREAK_X[j][u] = C.FAN.x + C.PIVOT.x + floor(sin(a) * u + 0.5)
        STREAK_Y[j][u] = C.FAN.y + C.PIVOT.y - floor(cos(a) * u + 0.5)
    end
end
-- the trail's colour and alpha by distance behind the head (0 = head)
local TRAIL_COL, TRAIL_A = {}, {}
for k = 0, C.STREAK - 1 do
    TRAIL_COL[k] = k < 3 and K.pure or (k < 7 and Mix(K.pink, K.pure, 0.7) or K.pink)
    TRAIL_A[k] = 0.35 + 0.65 * (C.STREAK - k) / C.STREAK
end

local Data
local mod
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc = false, false, 0
local P = {}                        -- every part, built once

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

local function Tex(parent, layer, sub, path, w, h)
    local t = parent:CreateTexture(nil, layer, nil, sub or 0)
    SetTex(t, path or FLAT)
    t.fsBase = mod
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

local function Alpha(f, a)
    if f.fsAlpha == a then return end
    f.fsAlpha = a
    f:SetAlpha(a)
end

local function Frame(parent, level)
    local f = CreateFrame("Frame", nil, parent)
    f:SetFrameLevel(mod:GetFrameLevel() + level)
    f:SetAllPoints(mod)
    f:EnableMouse(false)
    return f
end

-- A StatusBar over a file (or a flat colour) at sprite (x, y), w x h sprite px, from lo to hi; the ENGINE fills it.
local function Bar(parent, level, file, x, y, w, h, lo, hi, color)
    local bar = CreateFrame("StatusBar", nil, parent)
    bar:SetFrameLevel(mod:GetFrameLevel() + level)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(file == FLAT and FLAT or (MEDIA .. file))
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "HORIZONTAL") end
    bar:SetMinMaxValues(lo, hi)
    bar:SetValue(lo)
    if color then bar:SetStatusBarColor(color[1], color[2], color[3], color[4] or 1) end
    bar.fsBase, bar.fsBx, bar.fsBy, bar.fsW, bar.fsH = mod, x, y, w, h
    Seat(function() bar:SetSize(S(bar.fsW), S(bar.fsH)); Forget(bar); Place(bar, bar.fsBx, bar.fsBy) end)
    return bar
end

local function BarAt(bar, x, y)
    bar.fsBx, bar.fsBy = x, y
    Place(bar, x, y)
end

local function BarColor(bar, c, a)
    if bar.fsC == c and bar.fsA == a then return end
    bar.fsC, bar.fsA = c, a
    bar:SetStatusBarColor(c[1], c[2], c[3], a)
end

local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-- A label whose anchor x is cx on the module (point: LEFT, CENTER or RIGHT) and whose row top is y; size is image px.
local function Text(parent, cx, y, point, size)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs.fsSize = size or C.LABEL_SIZE
    fs:SetJustifyH(point)
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(fs.fsSize), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint(point, mod, "TOPLEFT", S(cx), -(S(y + C.BASELINE) - ui(C.CAP * fs.fsSize)))
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

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end

local function Reduced()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

-- texcoords of an atlas cell (the art's top left w x h sprite px)
local function Cell(t, name, w, h)
    local c = ATLAS[name]
    local aw, ah = Art.ATLAS_W, Art.ATLAS_H
    t:SetTexCoord(c[1] / aw, (c[1] + (w or c[3])) / aw, c[2] / ah, (c[2] + (h or c[4])) / ah)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local LEVEL = { back = 1, fan = 2, ready = 3, fx = 6, text = 8 }
local ENERGY_X = C.RAIL.x + 1
local ENERGY_W = C.RAIL.w - 2

local function BuildFan(root)
    local fx, fy = C.FAN.x, C.FAN.y
    P.dead = Tex(root.back, "ARTWORK", 0, MEDIA .. "rogue_dead.tga", Art.FAN_W, Art.FAN_H)
    Place(P.dead, fx, fy)
    P.veil = Tex(root.back, "ARTWORK", 1, MEDIA .. "rogue_flash.tga", Art.FAN_W, Art.FAN_H)
    Place(P.veil, fx, fy)
    Tint(P.veil, K.veil, 0.14)
    P.veil:Hide()
    P.lit = {}
    for i = 1, 5 do
        P.lit[i] = Bar(root.fan, 2, "rogue_lit_" .. i .. ".tga", fx, fy, Art.FAN_W, Art.FAN_H, i - 1, i)
    end
    P.readyFrame = Frame(mod, LEVEL.ready)
    P.ready = Bar(P.readyFrame, 3, "rogue_ready.tga", fx, fy, Art.FAN_W, Art.FAN_H, 4, 5)
    P.finish = Bar(P.readyFrame, 4, "rogue_finish.tga", C.FINISH.x, C.FINISH.y, Art.FINISH_W, Art.FINISH_H, 4, 5, K.gold)
    P.finishFrame = P.readyFrame
    -- the throw: the flash and the streaks
    P.fx = Frame(mod, LEVEL.fx)
    P.flash = Tex(P.fx, "OVERLAY", 0, MEDIA .. "rogue_flash.tga", Art.FAN_W, Art.FAN_H)
    Place(P.flash, fx, fy)
    Tint(P.flash, K.pure, 1)
    P.flash:Hide()
    P.streakFrame = CreateFrame("Frame", nil, P.fx)
    P.streakFrame:SetAllPoints(mod)
    P.streakFrame:EnableMouse(false)
    P.streak = {}
    for j = 1, #ANGLES do
        P.streak[j] = {}
        for k = 0, C.STREAK - 1 do
            local t = Tex(P.streakFrame, "OVERLAY", 1, FLAT, 1, 1)
            Tint(t, TRAIL_COL[k], TRAIL_A[k])
            t:Hide()
            P.streak[j][k] = t
        end
    end
    P.spark = Tex(P.fx, "OVERLAY", 2, MEDIA .. "rogue_atlas.tga", 24, 24)
    Cell(P.spark, "spark")
    Tint(P.spark, K.pure, 1)
    P.spark:Hide()
    -- smoke
    P.smokeFrame = Frame(mod, LEVEL.fx - 1)
    P.smoke = {}
    for k = 1, C.SMOKE do
        local t = Tex(P.smokeFrame, "OVERLAY", 0, FLAT, 1, 1)
        Tint(t, k % 3 == 0 and K.opener or K.violet, 1)
        t:Hide()
        P.smoke[k] = t
    end
end

local function BuildSnd(root)
    local s, st = C.SND, C.STAR
    P.sndBorder = Tex(root.back, "ARTWORK", 0, FLAT, s.w, s.h)
    Place(P.sndBorder, s.x, s.y)
    Tint(P.sndBorder, K.line, 1)
    P.sndTrack = Tex(root.back, "ARTWORK", 1, FLAT, s.w - 2, s.h - 2)
    Place(P.sndTrack, s.x + 1, s.y + 1)
    Tint(P.sndTrack, K.track, 1)
    P.sndFill = Tex(root.fan, "ARTWORK", 0, FLAT, 1, s.h - 2)
    Place(P.sndFill, s.x + 1, s.y + 1)
    P.sndFillHi = Tex(root.fan, "ARTWORK", 1, FLAT, 1, 1)
    Place(P.sndFillHi, s.x + 1, s.y + 1)
    P.sndHead = Tex(root.fan, "ARTWORK", 2, FLAT, 1, s.h - 2)
    Tint(P.sndHead, K.pure, 1)
    P.sndFill:Hide(); P.sndFillHi:Hide(); P.sndHead:Hide()
    P.dots = {}
    for k = 0, 11 do                                         -- the unlearned rail's dots
        local t = Tex(root.back, "ARTWORK", 2, FLAT, 1, 1)
        Place(t, s.x + 2 + k * 4, s.y + 3)
        Tint(t, K.off, 1)
        t:Hide()
        P.dots[k] = t
    end
    P.star = Tex(root.fan, "ARTWORK", 3, MEDIA .. "rogue_atlas.tga", Art.CELL, Art.CELL)
    Place(P.star, st.x - Art.CELL / 2, st.y - Art.CELL / 2)
    Cell(P.star, "star0")
    P.ring = Tex(root.fan, "ARTWORK", 4, MEDIA .. "rogue_atlas.tga", Art.CELL, Art.CELL)
    Place(P.ring, st.x - Art.CELL / 2, st.y - Art.CELL / 2)
    Cell(P.ring, "ring")
    P.ring:Hide()
    P.head = Text(root.text, s.x, C.SND_HEAD_Y, "LEFT")
    Label(P.head, "SND", K.muted, 1)
    P.secs = Text(root.text, s.x + s.w, C.SND_HEAD_Y, "RIGHT")
    P.opener = Text(root.text, st.x, 56, "CENTER")
    Label(P.opener, "OPENER", K.opener, 1)
    P.opener:Hide()
end

local function BuildEnergy(root)
    local r = C.RAIL
    P.railBorder = Tex(root.back, "ARTWORK", 0, FLAT, r.w, r.h)
    Place(P.railBorder, r.x, r.y)
    Tint(P.railBorder, K.line, 1)
    P.railTrack = Tex(root.back, "ARTWORK", 1, FLAT, r.w - 2, r.h - 2)
    Place(P.railTrack, r.x + 1, r.y + 1)
    Tint(P.railTrack, K.track, 1)
    local ey = r.y + 1
    P.eBase = Bar(root.fan, 2, FLAT, ENERGY_X, ey, ENERGY_W, 5, 0, C.ENERGY_MAX, K.goldBase)
    P.eLight = Bar(root.fan, 3, FLAT, ENERGY_X, ey, ENERGY_W, 2, 0, C.ENERGY_MAX, K.gold)
    P.eHi = Bar(root.fan, 4, FLAT, ENERGY_X, ey, ENERGY_W, 1, 0, C.ENERGY_MAX, K.goldHi)
    P.eFull = Bar(root.fan, 5, FLAT, ENERGY_X, ey, ENERGY_W, 5, C.ENERGY_MAX - 1, C.ENERGY_MAX, K.pale)
    P.eFull:SetAlpha(0.9)
    P.eNum = Text(root.text, C.NUM_RIGHT, r.y + 1, "RIGHT")
    Label(P.eNum, "", K.white, 1)
    P.gems = {}
    for i, def in ipairs({ { "builder", K.cyan }, { "finisher", K.fin } }) do
        local g = { key = def[1], color = def[2] }
        g.notch = Tex(root.back, "ARTWORK", 2, FLAT, 1, 5)
        Tint(g.notch, K.notchDim, 0.9)
        g.dim = Tex(root.back, "ARTWORK", 3, MEDIA .. "rogue_atlas.tga", Art.GEM, Art.GEM)
        Cell(g.dim, "gemDim", Art.GEM, Art.GEM)
        g.lit = Bar(root.fan, 4, "rogue_gem.tga", 0, C.GEM_Y, Art.GEM, Art.GEM, 0, 1, def[2])
        g.litNotch = Bar(root.fan, 3, FLAT, 0, r.y + 1, 1, 5, 0, 1, def[2])
        g.notch:Hide(); g.dim:Hide(); g.lit:Hide(); g.litNotch:Hide()
        P.gems[i] = g
    end
end

local function BuildCuff(root)
    P.number = Text(root.text, C.FAN.x + C.PIVOT.x, C.FAN.y + C.PIVOT.y - 6, "CENTER", C.CUFF_SIZE)
    Label(P.number, "", K.muted, 1)
end

-------------------------------------------------------------------------------
-- Power
-------------------------------------------------------------------------------

local V = { max = nil, builder = nil, finisher = nil, unknown = false, stealth = false, fanDy = 0 }
Rogue.V = V

-- Where a gem and its notch sit and when it lights: the notch at cost / max of the rail, the lit bar from cost - 1 to cost.
local function SeatGem(g, cost, maxv)
    if not (cost and maxv and maxv > 0 and cost <= maxv) then
        g.notch:Hide(); g.dim:Hide(); g.lit:Hide(); g.litNotch:Hide()
        g.cost = nil
        return
    end
    local nx = ENERGY_X + floor(ENERGY_W * cost / maxv + 0.5)
    g.cost = cost
    Place(g.notch, nx, C.RAIL.y + 1)
    Place(g.dim, nx - Art.GEM / 2, C.GEM_Y)
    BarAt(g.lit, nx - Art.GEM / 2, C.GEM_Y)
    BarAt(g.litNotch, nx, C.RAIL.y + 1)
    g.lit:SetMinMaxValues(cost - 1, cost)
    g.litNotch:SetMinMaxValues(cost - 1, cost)
    g.notch:Show(); g.dim:Show(); g.lit:Show(); g.litNotch:Show()
end

local function ConfigureEnergy()
    local maxv = V.max or C.ENERGY_MAX
    for _, bar in ipairs({ P.eBase, P.eLight, P.eHi }) do bar:SetMinMaxValues(0, maxv) end
    P.eFull:SetMinMaxValues(maxv - 1, maxv)
    SeatGem(P.gems[1], V.builder, maxv)
    SeatGem(P.gems[2], V.finisher, maxv)
end

local function ReadMax()
    local m
    if type(UnitPowerMax) == "function" then
        local ok, v = pcall(UnitPowerMax, "player", ENERGY_POWER)
        if ok and not IsSecret(v) and type(v) == "number" and v == v and v >= 1 then m = floor(v) end
    end
    return m
end

local function SetEnergyBars(v)
    P.eBase:SetValue(v); P.eLight:SetValue(v); P.eHi:SetValue(v); P.eFull:SetValue(v)
    for _, g in ipairs(P.gems) do
        if g.cost then g.lit:SetValue(v); g.litNotch:SetValue(v) end
    end
end

local function SetPoints(v)
    for i = 1, 5 do P.lit[i]:SetValue(v) end
    P.ready:SetValue(v)
    P.finish:SetValue(v)
end

-- The digit and the number go through SetFormattedText, which takes a secret; a plain value is clamped to what a count can be.
local function SetDigit(fs, v)
    local ok = pcall(fs.SetFormattedText, fs, "%d", v)
    if not ok then LogOnce("digit", "SetFormattedText refused a value") end
    fs.fsText = nil
end

local function ReadPower()
    if not mod then return end
    local okMax = ReadMax()
    if okMax ~= V.max then
        V.max = okMax
        ConfigureEnergy()
    end
    if type(UnitPower) ~= "function" then
        V.unknown = true
        SetPoints(0); SetEnergyBars(0)
        Label(P.number, "?", K.muted, 1)
        Label(P.eNum, "?", K.muted, 1)
        return
    end
    local okP, points = pcall(UnitPower, "player", COMBO_POWER)
    local okE, energy = pcall(UnitPower, "player", ENERGY_POWER)
    local pointsOk = okP and (IsSecret(points) or type(points) == "number")
    local energyOk = okE and (IsSecret(energy) or type(energy) == "number")
    V.unknown = not (pointsOk and energyOk)
    if pointsOk then
        SetPoints(points)
        SetDigit(P.number, points)
        if IsSecret(points) then
            TextColor(P.number, K.white, 1)
        else
            TextColor(P.number, points > 0 and K.white or K.muted, 1)
        end
    else
        SetPoints(0)
        Label(P.number, "?", K.muted, 1)
    end
    if energyOk then
        SetEnergyBars(energy)
        SetDigit(P.eNum, energy)
        TextColor(P.eNum, K.white, 1)
    else
        SetEnergyBars(0)
        Label(P.eNum, "?", K.muted, 1)
    end
end

local function ReadCosts()
    V.builder, V.finisher = Data.BuilderCost(), Data.FinisherCost()
    ConfigureEnergy()
end

-------------------------------------------------------------------------------
-- Paint (the ticker)
-------------------------------------------------------------------------------

local anim = { spendAt = nil, spendSeen = nil, thrown = 5, builderSeen = nil, recoilAt = nil }

local function SetFanDy(dy)
    if V.fanDy == dy then return end
    V.fanDy = dy
    local fy = C.FAN.y + dy
    Place(P.dead, C.FAN.x, fy)
    Place(P.veil, C.FAN.x, fy)
    Place(P.flash, C.FAN.x, fy)
    for i = 1, 5 do BarAt(P.lit[i], C.FAN.x, fy) end
    BarAt(P.ready, C.FAN.x, fy)
end

local function PaintStealth(now, reduced)
    local on = Data.Stealthed() == true
    On(P.veil, on)
    On(P.opener, on)
    On(P.smokeFrame, on)
    local tint = on and K.stealthLit or K.pure
    for i = 1, 5 do BarColor(P.lit[i], tint, 1) end
    if on then
        Alpha(P.opener, reduced and 1 or Stepped(0.65 + 0.35 * sin(now * 4)))
        if not reduced then
            for k = 1, C.SMOKE do
                local ph = (now * 7 + k * 5.3) % 46
                local x = C.FAN.x + 8 + floor((k * 13.7) % 62 + sin(now * 0.8 + k) * 3)
                local y = C.FAN.y + 52 - floor(ph)
                local t = P.smoke[k]
                Place(t, x, y)
                Alpha(t, Stepped(max(0, 0.55 - ph / 90)))
                On(t, true)
            end
        else
            for k = 1, C.SMOKE do On(P.smoke[k], false) end
        end
    end
    V.stealth = on
end

local function PaintThrow(now)
    local ts = anim.spendAt and (now - anim.spendAt) or nil
    if not ts or ts >= C.THROW then
        if anim.spendAt then
            anim.spendAt = nil
            On(P.flash, false); On(P.spark, false); On(P.streakFrame, false)
        end
        return
    end
    if ts < C.FLASH then
        Tint(P.flash, K.pure, Stepped((1 - ts / C.FLASH) * 0.9))
        On(P.flash, true)
    else
        On(P.flash, false)
    end
    On(P.streakFrame, true)
    Alpha(P.streakFrame, Stepped(max(0, 1 - ts / C.THROW)))
    local head = C.STREAK_U0 + min(1, ts / C.STREAK_T) * (C.STREAK_U1 - C.STREAK_U0)
    local h = floor(head)
    for j = 1, #ANGLES do
        local flying = j <= anim.thrown
        for k = 0, C.STREAK - 1 do
            local t = P.streak[j][k]
            local u = h - k
            if flying and u >= C.STREAK_U0 then
                Place(t, STREAK_X[j][u], STREAK_Y[j][u])
                On(t, true)
            else
                On(t, false)
            end
        end
    end
    if ts > 0.08 and ts < 0.45 then
        local mid = floor(#ANGLES / 2) + 1
        Place(P.spark, STREAK_X[mid][50] - 12, STREAK_Y[mid][50] - 12)
        Tint(P.spark, K.pure, Stepped(1 - (ts - 0.08) / 0.37))
        On(P.spark, true)
    else
        On(P.spark, false)
    end
end

local function PaintSnd(now, reduced, combat)
    local s = C.SND
    local known = Data.SndKnown()
    local learned = known ~= false
    local up, left, dur, exact = Data.Snd(now)
    local nudge = learned and known == true and not up and combat
    local low = up and left <= C.SND_WARN
    local blink = reduced and 1 or Stepped(0.55 + 0.45 * sin(now * 9))
    -- the header
    Label(P.head, "SND", not learned and K.off or (nudge and K.amber or K.muted), nudge and (reduced and 1 or Stepped(0.6 + 0.4 * sin(now * 6))) or 1)
    -- the rail's border is dimmer while unlearned
    Tint(P.sndBorder, learned and K.line or K.lineOff, 1)
    for k = 0, 11 do On(P.dots[k], not learned) end
    if up then
        local secs = floor(left + 0.999)
        if secs > 60 then secs = 60 end
        Label(P.secs, exact and SEC[secs] or SEC_EST[secs], low and K.amber or K.white, low and blink or 1)
        P.secs:Show()
        local w = floor(48 * left / dur + 0.5)
        if w < 1 then w = 1 elseif w > 48 then w = 48 end
        if P.sndFill.fsW ~= w then
            P.sndFill.fsW = w
            P.sndFill:SetSize(S(w), S(5))
            P.sndFillHi:SetSize(S(w), S(1))
            P.sndFillHi.fsW = w
        end
        local hi = low and K.amberHi or K.pinkHi
        Tint(P.sndFill, low and K.amber or K.pink, 1)
        Tint(P.sndFillHi, hi, 1)
        Place(P.sndHead, s.x + w, s.y + 1)
        On(P.sndFill, true); On(P.sndFillHi, true); On(P.sndHead, true)
        local frame = reduced and 0 or (floor(now * C.SPIN_HZ) % 4)
        if P.star.fsFrame ~= frame then
            P.star.fsFrame = frame
            Cell(P.star, STAR_NAME[frame])
        end
        Tint(P.star, low and K.amber or K.pink, 1)
        On(P.ring, false)
    else
        P.secs:Hide()
        On(P.sndFill, false); On(P.sndFillHi, false); On(P.sndHead, false)
        if P.star.fsFrame ~= "dead" then
            P.star.fsFrame = "dead"
            Cell(P.star, "starDead")
        end
        Tint(P.star, K.pure, learned and 1 or 0.3)
        On(P.ring, true)
        if nudge then
            Tint(P.ring, K.amber, reduced and 1 or Stepped(0.45 + 0.55 * Beat(now, 1.05)))
        else
            Tint(P.ring, learned and K.muted or K.muted, learned and 0.35 or 0.3)
        end
    end
end

local function PaintFan(now, reduced)
    -- the breath: the engine shows the gold overlay and the plaque only at five; Lua only moves the frame's alpha
    Alpha(P.readyFrame, reduced and 1 or Stepped(0.62 + 0.38 * Beat(now, 2 * pi / C.BREATH)))
    local dy = 0
    if not reduced and anim.recoilAt and now - anim.recoilAt < C.RECOIL then dy = 1 end
    SetFanDy(dy)
end

local function Paint(now)
    local reduced = Reduced()
    local combat = InCombat()
    local sa = Data.SpendAt()
    -- A cast is played only while it is fresh: one made while the module was hidden (Slice and Dice with no target is routine)
    -- is marked seen without a throw or a recoil when the module shows again.
    if sa and sa ~= anim.spendSeen then
        anim.spendSeen = sa
        if now - sa < C.THROW then
            anim.spendAt = now
            anim.thrown = min(5, max(1, Data.SpendPoints() or 5))
        end
    end
    local ba = Data.BuilderAt()
    if ba and ba ~= anim.builderSeen then
        anim.builderSeen = ba
        if now - ba < C.THROW then anim.recoilAt = now end
    end
    PaintFan(now, reduced)
    PaintStealth(now, reduced)
    PaintThrow(now)
    PaintSnd(now, reduced, combat)
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Data.Tick, now)
    if not ok then LogOnce("tick", err) end
    local okP, errP = pcall(Paint, now)
    if not okP then LogOnce("paint", errP) end
end

-------------------------------------------------------------------------------
-- Events and the area seams
-------------------------------------------------------------------------------

local rereadQueued = false
local function RereadNextFrame()
    if rereadQueued or not (C_Timer and C_Timer.After) then return end
    rereadQueued = true
    C_Timer.After(0, function()
        rereadQueued = false
        if subscribed then ReadPower() end
    end)
end

local function OnEvent(_, event, unit)
    if event ~= "PLAYER_TARGET_CHANGED" and not IsSecret(unit) and unit ~= nil and unit ~= "player" then return end
    ReadPower()
    if event == "PLAYER_TARGET_CHANGED" then RereadNextFrame() end
end

local function SetEvents(on)
    local FH = FS.FrameHelpers
    for _, e in ipairs(POWER_EVENTS) do
        if on then
            if FH and FH.RegisterEvent then FH.RegisterEvent(mod, e, "player") else pcall(mod.RegisterUnitEvent, mod, e, "player") end
        else
            pcall(mod.UnregisterEvent, mod, e)
        end
    end
    if on then
        if FH and FH.RegisterEvent then FH.RegisterEvent(mod, "PLAYER_TARGET_CHANGED") else pcall(mod.RegisterEvent, mod, "PLAYER_TARGET_CHANGED") end
    else
        pcall(mod.UnregisterEvent, mod, "PLAYER_TARGET_CHANGED")
    end
    mod:SetScript("OnEvent", on and OnEvent or nil)
end

local function OnChange(reason)
    if not subscribed then return end
    if reason == "cost" or reason == "learn" or reason == "change" then ReadCosts() end
end

local function SeatModule(rect)
    if type(rect) ~= "table" then return end
    local x, y, w = rect.x, rect.y, rect.w
    if type(x) ~= "number" or type(y) ~= "number" or type(w) ~= "number" then return end
    OX, OY = x + (w - C.W) / 2, y + C.DROP
    if mod then SeatAll() end
end

local function BuildModule(host)
    local Theme = FS.Theme
    if not (Theme and Theme.ApplyMono) then
        LogOnce("notheme", "Theme is missing, the Rogue module is not built")
        return nil
    end
    Data = FS.RogueState
    if not (Data and Data.Snd and Data.Subscribe) then
        LogOnce("nodata", "FS.RogueState is missing, the Rogue module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightRogue", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        local root = { back = Frame(mod, LEVEL.back), fan = Frame(mod, LEVEL.fan), text = Frame(mod, LEVEL.text) }
        BuildFan(root)
        BuildSnd(root)
        BuildEnergy(root)
        BuildCuff(root)
        ConfigureEnergy()
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Rogue.frame, Rogue.parts, Rogue.anim = mod, P, anim
    if Data.Start then Data.Start() end
    return mod
end

local function Sync(want)
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

local function OnAreaShown()
    if not mod then return end
    if not subscribed then
        subscribed = true
        Data.Subscribe(OnChange)
    end
    SetEvents(true)
    local ok, err = pcall(Data.Refresh)
    if not ok then LogOnce("refresh", err) end
    pcall(Data.NotePoints)
    ReadCosts()
    ReadPower()
    RereadNextFrame()                -- onShow runs inside the target change: UnitPower still holds the old target's points
    Paint(GetTime())
    Sync(true)
end

local function OnAreaHidden()
    if not mod then return end
    if subscribed then
        subscribed = false
        Data.Unsubscribe(OnChange)
    end
    SetEvents(false)
    Sync(false)
end

-- for the harness
Rogue._Paint, Rogue._ReadPower = Paint, ReadPower

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "ROGUE" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
