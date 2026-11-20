-- Forever STUwave: the Druid's CASTER form HoT flower (registered with FS.GunsightDruid.RegisterForm("caster", ...))
--
-- THE FLOWER. In caster form (the kinds "moon" and "tree") the class slot already shows the Thorns Bramble Wreath, which this
-- file leaves exactly as it is (GunsightDruid.lua paints it and its label). Over the wreath, centred on the wreath's centre, sits
-- a 46 x 46 sprite px pixel art flower that is the player's two heals over time on the current target:
--   * the ROSE in the middle is Rejuvenation (12 s, four heals, one every 3 s after the cast). Up: a clockwise SWEEP, the Thorns
--     wreath's own language. The part of the rose that is still lit is hot pink and is the fraction of the time left; the elapsed
--     part is a dark grey wedge (0.35 bright) that starts at 12 o'clock and grows clockwise, the right half grey at 6 s left, all of
--     it at the end, measured about the rose's own centre. It is baked in steps of half a second (24, the frames rose_w0 to
--     rose_w24), so every px stays crisp. A white flash for the first 0.5 s after the cast; on each heal a bright pulse and a small
--     burst of sparkle px outward over 0.7 s; the last 3 s it pulses amber, the flash, the pulse and the amber on the lit part only
--     (a lit mask baked for every frame, rose_m0 to rose_m23). A soft pink added glow sits behind it (amber in the last 3 s). Not
--     up: desaturated and dimmed to about half.
--   * the seven PETALS are Regrowth (21 s, seven heals, one every 3 s; petal 1 first, lower left, over the top, to lower right).
--     When heal i lands petal i wilts in place (desaturated, dark, 0.35) and a copy of it falls: it drifts down about 40 sprite
--     px with a little sway, turns and fades over 1.4 s. A cast flashes every petal toward white for 0.5 s and restores them (the
--     time left starts again). The last 3 s the live petals pulse amber. Not up, or not learned: all petals grey and dim, still
--     drawn. A soft teal glow sits behind the flower while Regrowth is up.
--   * the BASE (the cup round the rose, the leaves and stem) is Regrowth's too: lit while Regrowth is up, dimmed and greyed
--     otherwise, so nothing teal is lit for Rejuvenation.
-- TEXT is mono (the Thorns label's face and size, Druid.C.TH_LABEL_PX), at whole sprite px: the Rejuvenation seconds left of the
-- wreath (pink, amber at 3 s or less), the Regrowth seconds right of it (teal, the same amber), nothing for a HoT that is not up;
-- the target name top left (ON YOU in muted violet, a friend's name in leaf green), only while at least one HoT is up.
--
-- DATA. State.Hot(key, now) (DruidState.lua) is the seconds left of our OWN Rejuvenation or Regrowth on the current target's
-- name, a ledger of our casts and never a secret, so every heal and every look here is a function of elapsed = length - left:
-- heal i has landed once elapsed reaches 3 i, and a recast puts the elapsed time back to zero. State.Known("regrow") says the
-- spell is learned (polled every few seconds). The heal that lands exactly when a HoT runs out is the ledger's end: the rose's
-- fourth is not drawn (the rose is grey by then), the seventh petal's copy falls from the grey flower (the paint remembers that
-- Regrowth had under half a second left when it was last seen). Nothing here reads an aura, a power or a count; no value is
-- secret, none is compared.
--
-- ART. tools/assets/generate_druid_flower.py bakes druid_flower_art.tga (the layers as drawn, the same desaturated, white
-- silhouettes of the petals the module tints for the flash and the amber, each falling petal baked in 16 clockwise turns, and the
-- rose's 25 countdown frames with their 24 lit masks) and druid_flower_glow.tga (a soft white falloff), and the manifest FS.DruidFlowerArt
-- (DruidFlowerArt.lua, never edited by hand). Art layers keep the flower canvas, so they stack where they were cut.
--
-- UNITS AND TICK. One sprite px is spx image px on the 150 x 86 canvas the Druid module hands over; every position is a whole
-- sprite px. The Druid module calls paint at 30 Hz while the caster is shown. A paint allocates nothing: strings and sparkle
-- angles are built at load, colours are numbers, and a region is written only when its sprite, place, colour or alpha changes (the
-- rose's frame is picked from the plain ledger fraction left / length, and its texcoords are written only when the step changes). With
-- no HoT up the whole flower is painted once and left alone. No events are registered here.
--
-- Reduced motion (data.reduced): no flash, no heal pulse, no sparkles, no falling petal, no amber pulse (a steady amber); the
-- wilted petals, the colours, the glows and the numbers still say the state.

local _, FS = ...

local Druid = FS.GunsightDruid
local Gunsight = FS.Gunsight
local Art = FS.DruidFlowerArt
local State = FS.DruidState
if not (type(Druid) == "table" and Druid.RegisterForm) then return end
if not (Gunsight and Gunsight.ui) then return end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightdruidflower_" .. key, "|cffff4488Forever STUwave|r: gunsight druid flower: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.SPR) == "table" and type(Art.PETAL) == "table" and type(Art.ROSE) == "table"
    and type(Art.ROSE_STEPS) == "number" and Art.ROSE_STEPS >= 1) then
    LogOnce("noart", "FS.DruidFlowerArt is missing, the HoT flower is not built")
    return
end
if not (type(State) == "table" and State.Hot and State.Known) then
    LogOnce("nostate", "FS.DruidState is missing, the HoT flower is not built")
    return
end

FS.GunsightDruidFlower = FS.GunsightDruidFlower or {}
local Flower = FS.GunsightDruidFlower

local ui = Gunsight.ui
local floor, ceil, min, sin, cos, pi = math.floor, math.ceil, math.min, math.sin, math.cos, math.pi
local IsSecret = FS.IsSecret or function() return false end
local TAU = 2 * pi

local SPR, SCALE = Art.SPR, Art.SCALE
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local ATLAS_FILE = MEDIA .. Art.ATLAS .. ".tga"
local GLOW_FILE = MEDIA .. Art.GLOW .. ".tga"
local TUNING = State.TUNING or {}
local N = Art.PETALS
local RS = Art.ROSE_STEPS                 -- the rose's countdown steps: frame 0 is all lit, frame RS all grey

local C = {
    SW = Art.W, SH = Art.H,
    REJ_LEN = TUNING.REJUV_SECONDS or 12, REG_LEN = TUNING.REGROWTH_SECONDS or 21,
    TICK = 3,                          -- s between the heals of both spells
    WARN = 3,                          -- amber for the last seconds
    FLASH = 0.5, PULSE = 0.7, FALL = 1.4, FALL_DROP = 40,
    SPARKS = 10, SPARK_R0 = 3, SPARK_SPREAD = 11,
    DIM = 0.5, WILT = 0.35,
    POLL = 2,                          -- s between the Regrowth learned reads
    END_GRACE = 0.5,                   -- Regrowth seen with this little left (and gone now) ran out: its last heal lands
    TEXT_PX = (type(Druid.C) == "table" and Druid.C.TH_LABEL_PX) or 10,    -- the Thorns label's size (sprite px)
    REJ_X = 27, REJ_Y = 30, REG_X = 123, REG_Y = 30, NAME_X = 3, NAME_Y = 2, NAME_MAX = 10,
    GLOW_ROSE = 40, GLOW_FLOWER = 64,  -- the glows' sizes (sprite px)
    SPIN = Art.SPIN or 16,             -- baked turns of a falling petal over one full turn
    TURNS = 1,                         -- full turns a petal makes while it falls
}
Flower.C = C

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local K = {
    white = { 1, 1, 1 }, pink = Hex("#ff3ea5"), amber = Hex("#ffb020"), teal = Hex("#22d3ee"),
    pinkText = Hex("#ff5cb8"), tealText = Hex("#4fe0f0"), leaf = Hex("#7dff6a"), muted = Hex("#9d93c4"), spark = Hex("#ffc2ec"),
    dim = { C.DIM, C.DIM, C.DIM }, wilt = { C.WILT, C.WILT, C.WILT },
}
Flower.COLORS = K

-- sprite names, built at load so the paint never concatenates; the texts of the seconds likewise
local PN, PG, PM, FN = {}, {}, {}, {}
for i = 1, N do
    PN[i], PG[i], PM[i], FN[i] = "petal" .. i, "petal_g" .. i, "petal_m" .. i, {}
    for s = 0, C.SPIN - 1 do FN[i][s] = "fall" .. i .. "_" .. s end
end
local RW, RM = {}, {}                  -- the rose's frames and lit masks by step
for j = 0, RS do RW[j] = "rose_w" .. j end
for j = 0, RS - 1 do RM[j] = "rose_m" .. j end
local SECS = {}
for n = 0, 99 do SECS[n] = tostring(n) end
local SPARK_COS, SPARK_SIN = {}, {}
for j = 1, C.SPARKS do
    local a = (j - 1) / C.SPARKS * TAU + 0.35
    SPARK_COS[j], SPARK_SIN[j] = cos(a), sin(a)
end
local ON_YOU = "ON YOU"

local P = {}
local V = {
    spx = 1.25, regKnown = nil, poll = -99, idle = false,
    nameRaw = nil, nameShown = nil,
    regLeft = nil, regSeen = 0, finale = nil,
}
Flower.state, Flower.parts = V, P

local f, txt
local seats = {}

local function Seat(fn)
    seats[#seats + 1] = fn
    fn()
end

local function S(v) return ui(v * V.spx) end
local function Round(v) return floor(v + 0.5) end
local function Clamp01(v) if v < 0 then return 0 elseif v > 1 then return 1 end return v end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end

-------------------------------------------------------------------------------
-- Regions
-------------------------------------------------------------------------------

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

local function On(t)
    if t.fsOn ~= true then t.fsOn = true; t:Show() end
end

local function Off(t)
    if t.fsOn ~= false then t.fsOn = false; t:Hide() end
end

local function TintRGB(t, r, g, b, a)
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

local function Place(t, x, y)
    if t.fsX == x and t.fsY == y then return end
    t.fsX, t.fsY = x, y
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", f, "TOPLEFT", S(x), -S(y))
end

-- an atlas sprite on `host`
local function Spr(host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t:Hide()
    t.fsOn = false
    SetTex(t, ATLAS_FILE)
    Seat(function() t.fsX, t.fsY, t.fsName = nil, nil, nil end)
    return t
end

-- a flat px region
local function Dot(host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t:SetTexture(FLAT)
    t:Hide()
    t.fsOn = false
    Seat(function() t:SetSize(S(1), S(1)); t.fsX, t.fsY = nil, nil end)
    return t
end

-- a soft glow: the baked falloff, added to what is behind it, `w` sprite px square and centred at (cx, cy)
local function Glow(host, layer, sub, w, cx, cy)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t:SetTexture(GLOW_FILE)
    if t.SetBlendMode then pcall(t.SetBlendMode, t, "ADD") end
    t:Hide()
    t.fsOn = false
    t.fsGx, t.fsGy = cx - w / 2, cy - w / 2
    Seat(function() t:SetSize(S(w), S(w)); t.fsX, t.fsY = nil, nil end)
    return t
end

local function SetSprite(t, name)
    local s = SPR[name]
    if not s then return nil end
    if t.fsName ~= name then
        t.fsName = name
        local w, h = s[3], s[4]
        local aw, ah = Art.ATLAS_W, Art.ATLAS_H
        t:SetTexCoord(s[1] / aw, (s[1] + w * SCALE) / aw, s[2] / ah, (s[2] + h * SCALE) / ah)
        t:SetSize(S(w), S(h))
        t.fsX = nil
    end
    return s
end

-- sprite `name` with its anchor at canvas (x, y); the art layers keep the flower canvas, so (FX, FY) is where they were cut
local function Sprite(t, name, x, y, c, a)
    if a <= 0 then Off(t); return end
    local s = SetSprite(t, name)
    if not s then Off(t); return end
    On(t)
    Place(t, x - s[5], y - s[6])
    TintRGB(t, c[1], c[2], c[3], a)
end

local function DotAt(t, x, y, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    Place(t, x, y)
    TintRGB(t, c[1], c[2], c[3], a)
end

local function GlowAt(t, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    Place(t, Round(t.fsGx), Round(t.fsGy))
    TintRGB(t, c[1], c[2], c[3], a)
end

local function Text(host, align)
    local fs = host:CreateFontString(nil, "OVERLAY")
    fs.fsAlign = align
    fs.fsCol = K.muted
    fs.fsOn = false
    fs:Hide()
    Seat(function()
        local T = FS.Theme
        if T and T.ApplyMono then T.ApplyMono(fs, S(C.TEXT_PX), { fs.fsCol[1], fs.fsCol[2], fs.fsCol[3], 1 }) end
        fs.fsX, fs.fsR, fs.fsPlaced = nil, nil, nil
    end)
    return fs
end

local function TextAt(fs, x, y)
    if fs.fsX == x and fs.fsY == y then return end
    fs.fsX, fs.fsY = x, y
    fs:ClearAllPoints()
    fs:SetPoint(fs.fsAlign, f, "TOPLEFT", S(x), -S(y))
end

local function TextColor(fs, c)
    local r, g, b = c[1], c[2], c[3]
    if fs.fsR == r and fs.fsG == g and fs.fsB == b then return end
    fs.fsR, fs.fsG, fs.fsB = r, g, b
    fs:SetTextColor(r, g, b, 1)
end

local function TextWord(fs, word)
    if fs.fsWord == word then return end
    fs.fsWord = word
    fs:SetText(word)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Build(parent)
    f = CreateFrame("Frame", nil, parent)
    Flower.frame = f
    f:EnableMouse(false)
    f:SetAllPoints(parent)
    -- above everything the wreath draws (the Druid module's art, bars and top frames sit at its level + 0, 1 and 2)
    local base = 3
    if f.GetFrameLevel and parent.GetFrameLevel then base = parent:GetFrameLevel() + 3 end
    pcall(f.SetFrameLevel, f, base)
    txt = CreateFrame("Frame", nil, f)
    txt:EnableMouse(false)
    txt:SetAllPoints(f)
    pcall(txt.SetFrameLevel, txt, base + 1)

    local rcx, rcy = Art.FX + Art.ROSE[1], Art.FY + Art.ROSE[2]
    local fcx, fcy = Art.FX + Art.SIZE / 2, Art.FY + Art.SIZE / 2
    P.glowFlower = Glow(f, "BACKGROUND", -2, C.GLOW_FLOWER, fcx, fcy)
    P.glowRose = Glow(f, "BACKGROUND", -1, C.GLOW_ROSE, rcx, rcy)
    P.base = Spr(f, "ARTWORK", 0)
    P.petal, P.petalM = {}, {}
    for i = 1, N do
        P.petal[i] = Spr(f, "ARTWORK", 1)
        P.petalM[i] = Spr(f, "ARTWORK", 2)
    end
    P.rose, P.roseM = Spr(f, "ARTWORK", 3), Spr(f, "ARTWORK", 4)
    P.fall = Spr(f, "OVERLAY", 0)
    P.spark = {}
    for j = 1, C.SPARKS do P.spark[j] = Dot(f, "OVERLAY", 1) end

    P.rejT, P.regT, P.name = Text(txt, "CENTER"), Text(txt, "CENTER"), Text(txt, "TOPLEFT")
    return f
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function SparksOff()
    for j = 1, C.SPARKS do Off(P.spark[j]) end
end

-- the burst of a heal, q 0 to 1 over C.PULSE, outward from the rose's centre
local function Sparks(q)
    local cx, cy = Art.FX + Art.ROSE[1], Art.FY + Art.ROSE[2]
    local a = Stepped(1 - q)
    for j = 1, C.SPARKS do
        local r = C.SPARK_R0 + q * C.SPARK_SPREAD * (1 + ((j - 1) % 3) * 0.3)
        DotAt(P.spark[j], Round(cx + SPARK_COS[j] * r), Round(cy + SPARK_SIN[j] * r), (j % 2 == 1) and K.spark or K.white, a)
    end
end

-- the heals that have landed after `el` s, at most `cap`, and the seconds since the last one (99 before the first)
local function Heals(el, cap)
    local done = floor(el / C.TICK + 1e-6)
    if done > cap then done = cap end
    if done < 1 then return 0, 99 end
    return done, el - done * C.TICK
end

local function PaintIdle()
    local x, y = Art.FX, Art.FY
    Sprite(P.base, "base_g", x, y, K.dim, 1)
    Sprite(P.rose, "rose_g", x, y, K.dim, 1)
    Off(P.roseM)
    for i = 1, N do Sprite(P.petal[i], PG[i], x, y, K.dim, 1); Off(P.petalM[i]) end
    Off(P.glowRose); Off(P.glowFlower)
    SparksOff()
    Off(P.rejT); Off(P.regT); Off(P.name)
end

-- the rose's countdown step for `left` seconds of Rejuvenation: the nearest of RS steps of the plain ledger fraction, 0 just
-- cast (all lit) to RS at the end (all grey)
local function RoseStep(left)
    return floor((1 - Clamp01(left / C.REJ_LEN)) * RS + 0.5)
end

-- Rejuvenation: the rose, a clockwise sweep that greys the part of the time that has gone
local function PaintRose(now, left, red)
    local x, y = Art.FX, Art.FY
    local el = C.REJ_LEN - left
    if el < 0 then el = 0 end
    local k = Clamp01(left / C.REJ_LEN)
    local step = RoseStep(left)
    Sprite(P.rose, RW[step], x, y, K.white, 1)          -- the pink and the grey are baked: the tint stays white
    local _, since = Heals(el, 4)
    local pulse = (not red and since < C.PULSE) and (1 - since / C.PULSE) or 0
    local flash = (not red and el < C.FLASH) and (1 - el / C.FLASH) or 0
    local low = left <= C.WARN
    local lit = RM[step]                                -- the lit part of this frame; nothing is lit at the last one
    if lit and flash > 0 then
        Sprite(P.roseM, lit, x, y, K.white, Stepped(0.9 * flash))
    elseif lit and pulse > 0 then
        Sprite(P.roseM, lit, x, y, K.white, Stepped(0.55 * pulse))
    elseif lit and low then
        Sprite(P.roseM, lit, x, y, K.amber, red and 0.45 or Stepped(0.3 + 0.3 * (0.5 + 0.5 * sin(now * 8))))
    else
        Off(P.roseM)
    end
    if pulse > 0 then Sparks(since / C.PULSE) else SparksOff() end
    GlowAt(P.glowRose, low and K.amber or K.pink, Stepped(0.2 + 0.3 * k + 0.25 * pulse))
end

-- the petal that fell on heal `i`, `age` s after it landed
local function PaintFall(i, age)
    local q = age / C.FALL
    local c = Art.PETAL[i]
    local x = Round(Art.FX + c[1] + sin(q * 7 + i) * 3 * q)
    local y = Round(Art.FY + c[2] + q * q * (C.FALL_DROP - 10) + q * 10)
    local turn = floor((i * 3 + q * C.TURNS * C.SPIN) % C.SPIN)          -- clockwise, each petal starts at its own turn
    Sprite(P.fall, FN[i][turn], x, y, K.wilt, Stepped(1 - q))
end

-- the seventh petal's fall once the ledger has dropped Regrowth: true while it plays
local function Finale(now)
    local at = V.finale
    if at == nil then return false end
    local age = now - at
    if age < 0 or age >= C.FALL then V.finale = nil; return false end
    PaintFall(N, age)
    return true
end

-- Regrowth: the seven petals
local function PaintPetals(now, left, red)
    local x, y = Art.FX, Art.FY
    if left == nil then
        for i = 1, N do Sprite(P.petal[i], PG[i], x, y, K.dim, 1); Off(P.petalM[i]) end
        if not Finale(now) then Off(P.fall) end
        Off(P.glowFlower)
        return
    end
    local el = C.REG_LEN - left
    if el < 0 then el = 0 end
    local k = Clamp01(left / C.REG_LEN)
    local done, since = Heals(el, N)
    local flash = (not red and el < C.FLASH) and (1 - el / C.FLASH) or 0
    local low = left <= C.WARN
    local amberA = red and 0.45 or Stepped(0.3 + 0.3 * (0.5 + 0.5 * sin(now * 8)))
    for i = 1, N do
        if i <= done then
            Sprite(P.petal[i], PG[i], x, y, K.wilt, 1)
            Off(P.petalM[i])
        else
            Sprite(P.petal[i], PN[i], x, y, K.white, 1)
            if flash > 0 then Sprite(P.petalM[i], PM[i], x, y, K.white, Stepped(0.9 * flash))
            elseif low then Sprite(P.petalM[i], PM[i], x, y, K.amber, amberA)
            else Off(P.petalM[i]) end
        end
    end
    if done >= 1 and not red and since < C.FALL then PaintFall(done, since) else Off(P.fall) end
    GlowAt(P.glowFlower, K.teal, Stepped(0.15 + 0.25 * k))
end

local function Secs(left)
    local n = ceil(left)
    if n > 99 then n = 99 elseif n < 0 then n = 0 end
    return SECS[n]
end

-- cut at `C.NAME_MAX` bytes without splitting a multi byte letter, upper case like ON YOU
local function Shorten(name)
    local s = string.upper(name)
    if #s <= C.NAME_MAX then return s end
    local cut = C.NAME_MAX
    while cut > 1 do
        local b = string.byte(s, cut + 1)
        if b and b >= 0x80 and b < 0xC0 then cut = cut - 1 else break end
    end
    return string.sub(s, 1, cut)
end

-- the friend targeted, as plain text, or nil
local function FriendName()
    if type(UnitName) ~= "function" then return nil end
    local ok, n = pcall(UnitName, "target")
    if not ok or IsSecret(n) or type(n) ~= "string" or n == "" then return nil end
    return n
end

local function PaintText(rl, gl, data)
    if rl ~= nil then
        On(P.rejT); TextWord(P.rejT, Secs(rl)); TextColor(P.rejT, rl <= C.WARN and K.amber or K.pinkText); TextAt(P.rejT, C.REJ_X, C.REJ_Y)
    else Off(P.rejT) end
    if gl ~= nil then
        On(P.regT); TextWord(P.regT, Secs(gl)); TextColor(P.regT, gl <= C.WARN and K.amber or K.tealText); TextAt(P.regT, C.REG_X, C.REG_Y)
    else Off(P.regT) end
    -- the name: ON YOU when the HoTs follow you, the friend's name when a friend is targeted
    local word, col = ON_YOU, K.muted
    if data and data.kind == "tree" then
        local n = FriendName()
        if n then
            if n ~= V.nameRaw then V.nameRaw, V.nameShown = n, Shorten(n) end
            word, col = V.nameShown, K.leaf
        else
            word = nil
        end
    end
    if word then
        On(P.name); TextWord(P.name, word); TextColor(P.name, col); TextAt(P.name, C.NAME_X, C.NAME_Y)
    else Off(P.name) end
end

local function Paint(now, data)
    if not f then return end
    local red = data and data.reduced == true or false
    if V.poll <= now then
        V.poll = now + C.POLL
        local ok, k = pcall(State.Known, "regrow")
        if ok then V.regKnown = k else V.regKnown = nil end
    end
    local rl, gl = State.Hot("rejuv", now), State.Hot("regrow", now)
    if rl ~= nil and rl > C.REJ_LEN then rl = C.REJ_LEN end
    if gl ~= nil and (V.regKnown == false) then gl = nil end
    if gl ~= nil and gl > C.REG_LEN then gl = C.REG_LEN end
    -- the last heal: Regrowth seen in its final moments and gone now ran out (a target change or a long gap is not that)
    if gl ~= nil then
        V.regLeft, V.regSeen, V.finale = gl, now, nil
    elseif V.regLeft ~= nil then
        if V.regLeft <= C.END_GRACE and now - V.regSeen <= C.END_GRACE and not red then V.finale = now end
        V.regLeft = nil
    end
    if rl == nil and gl == nil then
        if Finale(now) then                     -- the seventh petal still falls
            V.idle = false
            PaintIdle()
            return
        end
        if V.idle then return end               -- nothing is up and nothing moves: the grey flower is already drawn
        V.idle = true
        PaintIdle()
        Off(P.fall)
        return
    end
    V.idle = false
    local x, y = Art.FX, Art.FY
    -- the base (the cup round the rose and the leaves) is Regrowth's, like the petals: lit only while Regrowth is up
    if gl ~= nil then Sprite(P.base, "base", x, y, K.white, 1) else Sprite(P.base, "base_g", x, y, K.dim, 1) end
    if rl ~= nil then PaintRose(now, rl, red)
    else
        Sprite(P.rose, "rose_g", x, y, K.dim, 1)
        Off(P.roseM); Off(P.glowRose)
        SparksOff()
    end
    PaintPetals(now, gl, red)
    PaintText(rl, gl, data)
end

-------------------------------------------------------------------------------
-- The form seams
-------------------------------------------------------------------------------

local spec = {
    build = function(parent)
        Build(parent)
        return f
    end,
    seat = function(_, _, spx)
        if type(spx) == "number" and spx > 0 then V.spx = spx end
        V.idle = false
        for i = 1, #seats do
            local ok, err = pcall(seats[i])
            if not ok then LogOnce("seat", err) end
        end
    end,
    paint = function(now, data)
        local ok, err = pcall(Paint, now, data)
        if not ok then LogOnce("paint", err) end
    end,
    show = function() if f then V.idle = false; f:Show() end end,
    hide = function() if f then f:Hide() end end,
}
Flower.spec, Flower.Paint = spec, Paint

Druid.RegisterForm("caster", spec)
