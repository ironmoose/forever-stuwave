-- Forever STUwave: the Druid's CAT form look (registered with FS.GunsightDruid.RegisterForm("cat", ...))
--
-- THE HIDE. In Cat form the class slot is the combo point tracker, the design mockup "Druid Hide Rake" (2026-11-17): a stretched
-- animal hide with five healed scars, one slot a point. Each point is raked in live by a whole lion paw (the approved paw of the
-- still "Lion Paw", 2026-11-17: splayed toes, dewclaw, hooked claws, wrist, strand fur, a ragged dark fringe) that swoops in with
-- afterimages, bites in at the top of the slot, drags down the cut with leather bits flying, and flicks out; the gash tears open
-- under the claw, flares white hot, curls its lips and runs blood (spatter, beads, drips, now and then a drop). At five points the
-- gashes burn gold with embers rising and FINISH breathing under them. The finisher (Ferocious Bite, Rip) hits like the Paladin's
-- Judgement: the paw rears back with red light gathering, swipes across with afterimages and four claw streaks, freezes on impact, a
-- white then red flash, a hard shake, a shockwave, a blood burst, four rake scars glowing across the hide while the spent gashes
-- cool and close. The count under the hide has a dark outline; none at zero. In the top left corner a small Thorns ring (the design
-- page "One Layout Per Form", 2026-11-16: ten thorns, one a minute) because Thorns runs out while you grind in a form.
--
-- ART. tools/assets/generate_druid_cat.py bakes one atlas (druid_cat_art.tga: the hide, the paw in its looks, halos, torn gash
-- stages, the swipe streaks, the rake scars, the Thorns ring masks), one file per lit gash (druid_cat_gash_1 to 5), the five gold
-- gashes (druid_cat_gold) and the FINISH plaque (druid_cat_finish), two texels per sprite px, and the manifest FS.DruidCatArt
-- (DruidCatArt.lua, never edited by hand). White masks (the Thorns ring, the red tint of the windup paw, the halos) are tinted here.
--
-- WHAT THE ENGINE DRAWS. In combat the combo count is a SECRET value: no comparison, no arithmetic, no table key, ever. So the count
-- is only ever handed to the engine: each lit gash is a StatusBar over its own file with the range (i - 1, i), the gold gashes and
-- the FINISH plaque are bars from 4 to 5, the embers and the falling drop of each slot are one px bars of the same ranges, the
-- number is SetFormattedText (the format "%.0d" prints nothing for zero; "%d" if the client refuses it). The rake needs the SLOT of
-- the newest gash, which a secret count cannot say: an invisible bar from 0 to 5 over the five columns is fed the count and the
-- paw, the torn gash and the leather bits are anchored to the right edge of its fill (the engine moves it), their offsets being the
-- newest column's. With a plain count (out of combat) the slot is known and they are placed here instead.
--
-- WHAT TRIGGERS THE MOTION. Only plain information: the player's own UNIT_SPELLCAST_SUCCEEDED by spell NAME (a builder: Claw, Rake,
-- Shred, Mangle, Ravage, Pounce; a finisher: Rip, Ferocious Bite, Maim) paired with the combo power event that follows it (or
-- came just before it), and, with a plain count, a rise out of combat. A secret count still lights every gash through the engine
-- and the rake plays on the paired builder cast. The gash bars are fed the NEW count only when the claw has opened it (the old
-- value is held for DRAG s), and on a finisher the old count is held until the impact and the gashes cool for COOL s after it.
--
-- DATA. State.Thorns(now) and State.Known("thorns") (DruidState.lua). Thorns not learned draws nothing; in combat a missing
-- Thorns draws nothing; out of combat a dashed amber ring and THORNS.
--
-- UNITS AND TICK. One sprite px is spx image px on the 150 x 86 canvas the Druid module hands over; every position is a whole sprite
-- px. The Druid module paints this at 30 Hz while it is shown. A paint allocates nothing: strings are built at load, colours are
-- numbers, a region is written only when its sprite, place or colour changes. The events are registered on show and dropped on hide.
--
-- Reduced motion (data.reduced): no paw, no finisher ceremony, no shake, flash, embers, drops or pulses; the gashes, the gold, FINISH
-- and the number still say the count.

local _, FS = ...

local Druid = FS.GunsightDruid
local Gunsight = FS.Gunsight
local Art = FS.DruidCatArt
local State = FS.DruidState
if not (type(Druid) == "table" and Druid.RegisterForm) then return end
if not (Gunsight and Gunsight.ui) then return end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightdruidcat_" .. key, "|cffff4488Forever STUwave|r: gunsight druid cat: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.SPR) == "table" and type(Art.GASH) == "table" and type(Art.GOLD) == "table"
    and type(Art.FINISH) == "table" and type(Art.BURST) == "table") then
    LogOnce("noart", "FS.DruidCatArt is missing, the Cat look is not built")
    return
end
if not (type(State) == "table" and State.Thorns) then
    LogOnce("nostate", "FS.DruidState is missing, the Cat look is not built")
    return
end

FS.GunsightDruidCat = FS.GunsightDruidCat or {}
local Cat = FS.GunsightDruidCat

local ui = Gunsight.ui
local floor, ceil, max, min, sin, cos, abs, pi = math.floor, math.ceil, math.max, math.min, math.sin, math.cos, math.abs, math.pi
local IsSecret = FS.IsSecret or function() return false end

local SPR, SCALE = Art.SPR, Art.SCALE
local HX, HY = Art.HX, Art.HY
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local ATLAS_FILE = MEDIA .. Art.ATLAS .. ".tga"

local C = {
    SW = Art.W, SH = Art.H,
    -- the rake (seconds from the builder cast)
    SWOOP = 0.12, DRAG = 0.32, FLICK = 0.45, FLARE = 0.5, RAKE_LEN = 0.6, SETTLE_DROPS = 1.2,
    -- the finisher: windup until WIND, swipe until IMP; after the impact the shake, flash, shockwave, burst, scars and the cooling
    WIND = 0.12, IMP = 0.24, SHAKE_FROM = 0.06, SHAKE_TO = 0.7, FLASH_W = 0.05, FLASH_R = 0.5,
    SHOCK = 0.55, BURST = 0.9, SCAR_FROM = 0.06, SCAR_LEN = 1.1, COOL = 1.5,
    PAIR = 0.5,                        -- s a builder cast waits for the combo event that is its point
    PAIR_BEFORE = 0.25,                -- s the combo event may come before the cast event that is its point
    REREAD = 2,                        -- paints after a target change or a show that re-read the count (the old target's is still there)
    POLL = 2,                          -- s between the Thorns learned reads
    TH_LEN = 600, TH_LOW = 60,
    SLOT_COLS = 5,
    DIGIT_PX = 8, TH_TIME_PX = 6, TH_WORD_PX = 5,
    EMBERS = 7, SHOCK_N = 90, BITS = 6, DRIFT = 5,
}
Cat.C = C

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end
local function Mix(a, b, k) return { a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k, a[3] + (b[3] - a[3]) * k } end

local K = {
    white = { 1, 1, 1 }, hot = Hex("#ff2040"), halo = Hex("#ff1030"), gold = Hex("#ffd23f"), ember = Hex("#fff4b0"),
    amber = Hex("#ffb648"), muted = Hex("#9d93c4"), thorn = Hex("#5fd35a"), line = Hex("#3a2168"), out = Hex("#0a0414"),
    tan = Hex("#d2a06a"), fur = Hex("#7a5230"),
    bloodLt = Hex("#d8202e"), bloodMd = Hex("#a01020"), bloodDk = Hex("#5a0610"),
}
K.thornTip, K.amberTip, K.pulseWhite = Mix(K.thorn, K.white, 0.4), Mix(K.amber, K.white, 0.4), K.white
Cat.COLORS = K

-- what a cast name does (lower case, any rank); the names are the truth on Forever, ids are not probed
local KIND = {
    ["claw"] = "build", ["rake"] = "build", ["shred"] = "build", ["mangle"] = "build", ["mangle (cat)"] = "build",
    ["ravage"] = "build", ["pounce"] = "build",
    ["rip"] = "spend", ["ferocious bite"] = "spend", ["maim"] = "spend",
}
Cat.KIND = KIND

-- sprite names, built at load so the paint never concatenates
local TEAR = { "tear1", "tear2", "tear3", "tear4" }
local SEG, TIP = {}, {}
for i = 0, 9 do SEG[i], TIP[i] = "thr" .. i, "tht" .. i end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local P = {}
local V = {
    spx = 1.25,
    live = nil, liveAt = -99, batchAt = nil, batchUsed = false, prev = nil, plainN = nil, plainPrev = nil,
    held = nil, holdGash = nil, holdRest = nil,
    buildAt = nil, rakeAt = nil, rakeSlot = nil, spendAt = nil, targetAt = -99,
    reread = 0, red = false,
    digitFmt = "%.0d", thKnown = nil, thPoll = 0,
    shakeX = 0, shakeY = 0,
}
Cat.state, Cat.parts = V, P

local f, sh, bf, fx, fxPaw, fxHit, top, lab
local seats = {}
local mark, markFill
local spellNames = {}

local function Seat(fn)
    seats[#seats + 1] = fn
    fn()
end

local function S(v) return ui(v * V.spx) end
local function Round(v) return floor(v + 0.5) end
local function Clamp01(v) if v < 0 then return 0 elseif v > 1 then return 1 end return v end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end

local function Reduced()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

-- a whole count at or above 0, or nil (a secret, a string, a NaN)
local function PlainOf(v)
    if v == nil or IsSecret(v) or type(v) ~= "number" or v ~= v or v < 0 then return nil end
    return floor(v)
end

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

local function Tint(t, c, a)
    local r, g, b = c[1], c[2], c[3]
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

local function TintRGB(t, r, g, b, a)
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

-- where `t` sits: its TOPLEFT at canvas (x, y) of its base frame, or (mark = true) at (x, y) from the top right of the marker fill
local function Place(t, x, y)
    if t.fsX == x and t.fsY == y and t.fsMark == false then return end
    t.fsX, t.fsY, t.fsMark = x, y, false
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", t.fsBase, "TOPLEFT", S(x), -S(y))
end

local function PlaceMark(t, dx, dy)
    if t.fsX == dx and t.fsY == dy and t.fsMark == true then return end
    t.fsX, t.fsY, t.fsMark = dx, dy, true
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", markFill, "TOPRIGHT", S(dx), -S(dy))
end

-- an atlas sprite on `host`
local function Spr(host, layer, sub, base)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsBase = base
    t:Hide()
    t.fsOn = false
    SetTex(t, ATLAS_FILE)
    Seat(function() t.fsX, t.fsY, t.fsName = nil, nil, nil end)
    return t
end

-- a flat px region, w x h sprite px
local function Dot(host, layer, sub, base)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsBase = base
    t:SetTexture(FLAT)
    t:Hide()
    t.fsOn = false
    t.fsW, t.fsH = 1, 1
    Seat(function() t:SetSize(S(t.fsW), S(t.fsH)); t.fsX, t.fsY = nil, nil end)
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

-- sprite `name` with its anchor at canvas (x, y)
local function Sprite(t, name, x, y, c, a)
    if a <= 0 then Off(t); return end
    local s = SetSprite(t, name)
    if not s then Off(t); return end
    On(t)
    Place(t, x - s[5], y - s[6])
    Tint(t, c, a)
end

-- sprite `name` with its anchor at slot-local (dx, dy); `slot` is the newest gash's column when known (plain), else the marker's
local function SlotSprite(t, name, dx, dy, c, a)
    if a <= 0 then Off(t); return end
    local s = SetSprite(t, name)
    if not s then Off(t); return end
    On(t)
    local slot = V.rakeSlot
    if slot then Place(t, Art.SLOT_X0 + Art.SLOT_DX * slot + dx - s[5], Art.SLOT_Y0 + slot % 2 + dy - s[6])
    else PlaceMark(t, dx - 6 - s[5], dy - s[6]) end
    Tint(t, c, a)
end

local function DotAt(t, x, y, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    Place(t, x, y)
    Tint(t, c, a)
end

local function SlotDot(t, dx, dy, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    local slot = V.rakeSlot
    if slot then Place(t, Art.SLOT_X0 + Art.SLOT_DX * slot + dx, Art.SLOT_Y0 + slot % 2 + dy)
    else PlaceMark(t, dx - 6, dy) end
    Tint(t, c, a)
end

-- a StatusBar over a baked file (or a flat colour) with its top left at canvas (x, y), w x h sprite px, from lo to hi; the ENGINE fills it
local function Bar(parent, base, level, file, x, y, w, h, lo, hi)
    local bar = CreateFrame("StatusBar", nil, parent)
    pcall(function() bar:SetFrameLevel(parent:GetFrameLevel() + level) end)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(file and (MEDIA .. file .. ".tga") or FLAT)
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "HORIZONTAL") end
    bar:SetMinMaxValues(lo, hi)
    bar:SetValue(lo)
    bar.fsBase, bar.fsOn = base, true
    bar.fsBx, bar.fsBy, bar.fsBw, bar.fsBh = x, y, w, h
    Seat(function() bar:SetSize(S(bar.fsBw), S(bar.fsBh)); bar.fsX, bar.fsY = nil, nil; Place(bar, bar.fsBx, bar.fsBy) end)
    return bar
end

local function BarColor(bar, r, g, b, a)
    if bar.fsR == r and bar.fsG == g and bar.fsB == b and bar.fsA == a then return end
    bar.fsR, bar.fsG, bar.fsB, bar.fsA = r, g, b, a
    bar:SetStatusBarColor(r, g, b, a)
end

local function BarAt(bar, x, y)
    bar.fsBx, bar.fsBy = x, y
    Place(bar, x, y)
end

local function BarOn(bar, on)
    if bar.fsOn == on then return end
    bar.fsOn = on
    if on then bar:Show() else bar:Hide() end
end

local function BarAlpha(bar, a)
    if bar.fsAlpha == a then return end
    bar.fsAlpha = a
    bar:SetAlpha(a)
end

local function Text(host, size, shown)
    local fs = host:CreateFontString(nil, "OVERLAY")
    fs.fsPx, fs.fsAlign = size, "CENTER"
    fs.fsCol = K.muted
    fs.fsOn = shown == true
    if shown then fs:Show() else fs:Hide() end
    Seat(function()
        local T = FS.Theme
        if T and T.ApplyMono then T.ApplyMono(fs, S(fs.fsPx), { fs.fsCol[1], fs.fsCol[2], fs.fsCol[3], 1 }) end
        fs.fsX, fs.fsR = nil, nil
    end)
    return fs
end

local function TextAt(fs, base, x, y)
    if fs.fsX == x and fs.fsY == y then return end
    fs.fsX, fs.fsY = x, y
    fs:ClearAllPoints()
    fs:SetPoint(fs.fsAlign, base, "TOPLEFT", S(x), -S(y))
end

local function TextColor(fs, c, a)
    local r, g, b = c[1], c[2], c[3]
    if fs.fsR == r and fs.fsG == g and fs.fsB == b and fs.fsA == a then return end
    fs.fsR, fs.fsG, fs.fsB, fs.fsA = r, g, b, a
    fs:SetTextColor(r, g, b, a)
end

local function TextWord(fs, word)
    if fs.fsWord == word then return end
    fs.fsWord = word
    fs:SetText(word)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local OUTLINE = { { -1, 0 }, { 1, 0 }, { 0, -1 }, { 0, 1 }, { -1, -1 }, { 1, -1 }, { -1, 1 }, { 1, 1 } }

local function Build(parent)
    f = CreateFrame("Frame", nil, parent)
    Cat.frame = f
    f:EnableMouse(false)
    f:SetAllPoints(parent)
    local base = 0
    if f.GetFrameLevel and parent.GetFrameLevel then base = parent:GetFrameLevel() + 1; pcall(f.SetFrameLevel, f, base) end
    if f.SetClipsChildren then pcall(f.SetClipsChildren, f, true) end

    local function Layer(parentFrame, level)
        local fr = CreateFrame("Frame", nil, parentFrame)
        fr:EnableMouse(false)
        pcall(fr.SetFrameLevel, fr, base + level)
        return fr
    end
    -- the shaker holds everything the hit shakes: the hide, the gashes, the paw; the corner and the count stand still
    -- levels are absolute from the form frame and spaced out: the engine bars sit a few above bf, the paw above every bar, the count above the flash
    sh = Layer(f, 1)
    bf, fx, fxPaw, fxHit = Layer(sh, 2), Layer(sh, 12), Layer(sh, 22), Layer(sh, 32)
    top = Layer(f, 42)
    lab = Layer(top, 43)
    Seat(function()
        f.fsSeated = true
        sh:ClearAllPoints()
        sh:SetPoint("TOPLEFT", f, "TOPLEFT", S(V.shakeX), -S(V.shakeY))
        sh:SetSize(S(C.SW), S(C.SH))
        top:ClearAllPoints()
        top:SetPoint("TOPLEFT", f, "TOPLEFT", 0, 0)
        top:SetSize(S(C.SW), S(C.SH))
        for _, fr in ipairs({ bf, fx, fxPaw, fxHit }) do
            fr:ClearAllPoints()
            fr:SetAllPoints(sh)
        end
        lab:ClearAllPoints()
        lab:SetAllPoints(top)
    end)

    -- the hide, its torn gash stages and the flare of a fresh cut
    P.hide = Spr(sh, "BACKGROUND", 0, sh)
    P.tear, P.flare = Spr(fx, "ARTWORK", 0, sh), Spr(fx, "ARTWORK", 1, sh)
    P.scarC, P.scarE = Spr(fxHit, "ARTWORK", 1, sh), Spr(fxHit, "ARTWORK", 0, sh)

    -- the engine drawn part: a lit gash a slot (the count reaches i), the five gold gashes at five, the marker the paw rides
    P.gash = {}
    for i, g in ipairs(Art.GASH) do
        P.gash[i] = Bar(bf, sh, 1, g.file, g.x, g.y, g.w, g.h, i - 1, i)
    end
    -- the cooled gash of each slot: the finisher's cooling fades the lit gash into it (a dark cut with a cream lip)
    P.cool = {}
    for i, g in ipairs(Art.COOL) do
        P.cool[i] = Bar(bf, sh, 1, g.file, g.x, g.y, g.w, g.h, i - 1, i)
        BarOn(P.cool[i], false)
    end
    local G = Art.GOLD
    P.gold = Bar(bf, sh, 2, G.file, G.x, G.y, G.w, G.h, 4, 5)
    local colX = Art.SLOT_X0 - Art.SLOT_DX / 2
    mark = Bar(bf, sh, 0, nil, colX, Art.SLOT_Y0, Art.SLOT_DX * C.SLOT_COLS, 1, 0, C.SLOT_COLS)
    BarColor(mark, 1, 1, 1, 0)
    markFill = mark:GetStatusBarTexture()
    P.mark = mark
    -- a drop that lets go of a slot's first drip: two px, only on a lit slot
    P.dropA, P.dropB = {}, {}
    for i, g in ipairs(Art.GASH) do
        P.dropA[i] = Bar(bf, sh, 3, nil, g.dropX, g.dropY, 1, 1, i - 1, i)
        P.dropB[i] = Bar(bf, sh, 3, nil, g.dropX, g.dropY + 1, 1, 1, i - 1, i)
        BarColor(P.dropA[i], K.bloodLt[1], K.bloodLt[2], K.bloodLt[3], 1)
        BarColor(P.dropB[i], K.bloodMd[1], K.bloodMd[2], K.bloodMd[3], 1)
        BarOn(P.dropA[i], false)
        BarOn(P.dropB[i], false)
    end
    -- embers rising off the gold gashes
    P.ember = {}
    for i = 1, C.EMBERS do
        P.ember[i] = Bar(bf, sh, 4, nil, 0, 0, 1, 1, 4, 5)
        local c = (i % 2 == 1) and K.gold or K.ember
        BarColor(P.ember[i], c[1], c[2], c[3], 1)
        BarOn(P.ember[i], false)
    end

    -- the paw and its afterimages, the windup mask, the halo, the streaks
    P.paw = Spr(fxPaw, "ARTWORK", 0, sh)
    P.mask = Spr(fxPaw, "ARTWORK", 1, sh)
    P.ghost = { Spr(fxPaw, "ARTWORK", 2, sh), Spr(fxPaw, "ARTWORK", 3, sh), Spr(fxPaw, "ARTWORK", 4, sh) }
    P.halo = Spr(fxPaw, "BACKGROUND", 0, sh)
    P.comet = Spr(fxPaw, "BACKGROUND", 1, sh)

    -- flung bits, blood and sparks of the rake; the shockwave and the blood burst of the hit
    P.bit, P.drift, P.fBlood, P.fWhite = {}, {}, {}, {}
    for i = 1, C.BITS do P.bit[i] = Dot(fxHit, "OVERLAY", 0, sh) end
    for i = 1, C.DRIFT do P.drift[i] = Dot(fxHit, "OVERLAY", 1, sh) end
    for i = 1, 4 do P.fBlood[i], P.fWhite[i] = Dot(fxHit, "OVERLAY", 2, sh), Dot(fxHit, "OVERLAY", 3, sh) end
    P.shock = {}
    for i = 1, C.SHOCK_N do P.shock[i] = Dot(fxHit, "OVERLAY", 4, sh) end
    P.burst, P.burstD = {}, {}
    for i = 1, #Art.BURST do
        P.burst[i] = Dot(fxHit, "OVERLAY", 5, sh)
        if Art.BURST[i][5] == 1 then P.burstD[i] = Dot(fxHit, "OVERLAY", 5, sh) end
    end

    -- the flash (white, then red) over everything but the count
    P.flashW, P.flashR = Dot(top, "OVERLAY", 2, top), Dot(top, "OVERLAY", 3, top)
    for _, t in ipairs({ P.flashW, P.flashR }) do
        t.fsW, t.fsH = C.SW, C.SH
        t:SetSize(S(C.SW), S(C.SH))
    end

    -- the FINISH plaque (engine: 4 to 5) and the count with its dark outline (engine text)
    local F = Art.FINISH
    P.finish = Bar(lab, top, 1, F.file, F.x, F.y, F.w, F.h, 4, 5)
    P.rim = {}
    for i = 1, #OUTLINE do
        local fs = Text(lab, C.DIGIT_PX, true)
        fs.fsCol = K.out
        P.rim[i] = fs
    end
    P.digit = Text(lab, C.DIGIT_PX, true)
    Seat(function()
        local cx, cy = HX, Art.LABEL_CY
        for i = 1, #OUTLINE do
            local fs = P.rim[i]
            fs.fsX = nil
            TextAt(fs, top, cx + OUTLINE[i][1], cy + OUTLINE[i][2])
            TextColor(fs, K.out, 1)
        end
        P.digit.fsX = nil
        TextAt(P.digit, top, cx, cy)
        TextColor(P.digit, K.muted, 1)
    end)

    -- the Thorns corner: ten ring segments and their tips (white masks, tinted), the dashed ring of a gone Thorns, the time
    P.thSeg, P.thTip = {}, {}
    for i = 0, 9 do
        P.thSeg[i] = Spr(top, "ARTWORK", 0, top)
        P.thTip[i] = Spr(top, "ARTWORK", 1, top)
    end
    P.thGone = Spr(top, "ARTWORK", 2, top)
    P.thTime = Text(top, C.TH_TIME_PX)
    P.thWord = Text(top, C.TH_WORD_PX)
    return f
end

-------------------------------------------------------------------------------
-- The count: read, held, handed to the engine
-------------------------------------------------------------------------------

local COMBO = (_G.Enum and _G.Enum.PowerType and _G.Enum.PowerType.ComboPoints) or 4

local function ReadCombo()
    if type(UnitPower) ~= "function" then return nil end
    local ok, c = pcall(UnitPower, "player", COMBO)
    if not ok then return nil end
    if IsSecret(c) then return c end
    if type(c) ~= "number" or c ~= c then return nil end
    return c
end

-- the count as text: nothing at zero ("%.0d"); the engine formats it, so a secret is fine
local function SetDigit(c)
    local fmt = V.digitFmt
    local ok = pcall(P.digit.SetFormattedText, P.digit, fmt, c)
    if not ok and fmt ~= "%d" then
        V.digitFmt = "%d"
        fmt = "%d"
        ok = pcall(P.digit.SetFormattedText, P.digit, fmt, c)
    end
    if not ok then LogOnce("digit", "SetFormattedText refused a value") return end
    for i = 1, #OUTLINE do pcall(P.rim[i].SetFormattedText, P.rim[i], fmt, c) end
end

local function ApplyGash(c)
    for i = 1, #P.gash do P.gash[i]:SetValue(c); P.cool[i]:SetValue(c) end
end

local function ApplyRest(c)
    P.gold:SetValue(c)
    P.finish:SetValue(c)
    for i = 1, C.EMBERS do P.ember[i]:SetValue(c) end
    for i = 1, #P.dropA do P.dropA[i]:SetValue(c); P.dropB[i]:SetValue(c) end
    SetDigit(c)
end

local function Apply()
    local c = V.live
    if c == nil then c = 0 end
    if not V.holdGash then ApplyGash(c) end
    if not V.holdRest then ApplyRest(c) end
    mark:SetValue(c)
end

-- the count as the engine has it now, with no pairing and no gain test (a show, a target change)
local function Reread()
    local c = ReadCombo()
    if c == nil then c = 0 end
    V.live, V.liveAt = c, GetTime()
    V.plainN = PlainOf(c)
    V.batchAt = nil
    Apply()
end

local function Gained()
    local a, b = V.plainN, V.plainPrev
    if a ~= nil and b ~= nil then return a > b end
    return true
end

local function StartRake(now)
    if Reduced() or not V.prev then return end
    V.rakeAt, V.buildAt, V.batchUsed = now, nil, true
    local n = V.plainN
    V.rakeSlot = (n and n >= 1) and (min(n, C.SLOT_COLS) - 1) or nil
    V.held = V.prev
    V.holdGash, V.holdRest = now + C.DRAG, now + C.DRAG
    ApplyGash(V.held)
    ApplyRest(V.held)
end

local function StartSpend(now)
    if Reduced() then return end
    V.spendAt, V.rakeAt, V.buildAt = now, nil, nil
    local held = V.live
    if V.batchAt and now - V.batchAt <= C.PAIR_BEFORE and V.prev ~= nil then held = V.prev end
    if held == nil then held = 0 end
    V.held = held
    V.holdRest, V.holdGash = now + C.IMP, now + C.IMP + C.COOL
    ApplyGash(held)
    ApplyRest(held)
end

local function OnCombo()
    local now = GetTime()
    local c = ReadCombo()
    if c == nil then return end
    if not V.batchAt or now - V.liveAt > 0.05 then         -- a new change (a pair of events carries one)
        V.batchAt, V.batchUsed = now, false
        V.prev, V.plainPrev = V.live, V.plainN
        if V.prev == nil then V.prev = 0 end
    end
    V.live, V.liveAt = c, now
    V.plainN = PlainOf(c)
    if not V.batchUsed then
        if V.buildAt and now - V.buildAt <= C.PAIR and Gained() then
            StartRake(now)
        elseif V.plainN ~= nil and V.plainPrev ~= nil and V.plainN > V.plainPrev and now - V.targetAt > 0.3
            and not (V.rakeAt and now - V.rakeAt < C.RAKE_LEN) and not V.spendAt then
            StartRake(now)
        end
    end
    Apply()
end

local function SpellKind(id)
    if type(id) ~= "number" or IsSecret(id) then return nil end
    local hit = spellNames[id]
    if hit ~= nil then return hit or nil end
    local name
    if C_Spell and C_Spell.GetSpellName then
        local ok, n = pcall(C_Spell.GetSpellName, id)
        if ok and not IsSecret(n) and type(n) == "string" then name = n end
    end
    if not name and GetSpellInfo then
        local ok, n = pcall(GetSpellInfo, id)
        if ok and not IsSecret(n) and type(n) == "string" then name = n end
    end
    local kind = name and KIND[string.lower(name)] or false
    spellNames[id] = kind
    return kind or nil
end

local function OnCast(id)
    local kind = SpellKind(id)
    if not kind then return end
    local now = GetTime()
    if kind == "spend" then StartSpend(now) return end
    if V.batchAt and now - V.batchAt <= C.PAIR_BEFORE then      -- the point came just before the cast: this cast is its builder
        if not V.batchUsed and Gained() then StartRake(now) end
        return
    end
    V.buildAt = now
end

local function OnEvent(_, event, a, b, c3)
    if event == "UNIT_SPELLCAST_SUCCEEDED" then OnCast(c3) return end
    if event == "PLAYER_TARGET_CHANGED" then
        V.targetAt = GetTime()
        Reread()
        V.reread = C.REREAD
        return
    end
    if a ~= nil and not IsSecret(a) and a ~= "player" then return end
    if b ~= nil and not IsSecret(b) and b ~= "COMBO_POINTS" then return end
    OnCombo()
end

local EVENTS = { "UNIT_POWER_UPDATE", "UNIT_POWER_FREQUENT", "UNIT_SPELLCAST_SUCCEEDED", "PLAYER_TARGET_CHANGED" }

local function SetEvents(on)
    local FH = FS.FrameHelpers
    for _, e in ipairs(EVENTS) do
        if on then
            local unit = e ~= "PLAYER_TARGET_CHANGED" and "player" or nil
            if FH and FH.RegisterEvent then FH.RegisterEvent(f, e, unit)
            elseif unit then pcall(f.RegisterUnitEvent, f, e, unit)
            else pcall(f.RegisterEvent, f, e) end
        else
            pcall(f.UnregisterEvent, f, e)
        end
    end
    f:SetScript("OnEvent", on and OnEvent or nil)
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function Shake(sx, sy)
    if V.shakeX == sx and V.shakeY == sy then return end
    V.shakeX, V.shakeY = sx, sy
    sh:ClearAllPoints()
    sh:SetPoint("TOPLEFT", f, "TOPLEFT", S(sx), -S(sy))
end

local function HideAll(list)
    for i = 1, #list do Off(list[i]) end
end

local function RakeOff()
    Off(P.tear); Off(P.flare)
    HideAll(P.bit); HideAll(P.drift); HideAll(P.fBlood); HideAll(P.fWhite)
end

local function PawOff()
    Off(P.paw); Off(P.mask); Off(P.halo); Off(P.comet)
    HideAll(P.ghost)
end

local function HitOff()
    Off(P.scarC); Off(P.scarE)
    HideAll(P.shock); HideAll(P.burst)
    for i = 1, #P.burst do if P.burstD[i] then Off(P.burstD[i]) end end
    Off(P.flashW); Off(P.flashR)
end

-- the rake of one slot, a seconds after the cast; returns the mini shake offset
local function PaintRake(now, a)
    local row = V.rakeSlot and (V.rakeSlot + 1) or 3
    local bits, drift = Art.BITS[row], Art.DRIFT[row]
    local sx = 0
    Off(P.tear); Off(P.flare)
    if a < C.SWOOP then                                              -- the paw swoops in with afterimages
        local e = a / C.SWOOP
        for j = 0, 2 do
            local ee = max(0, e - j * 0.18)
            local x, y = Round(3 + 16 * (1 - ee)), Round(-14 * (1 - ee))
            if j == 0 then SlotSprite(P.paw, "paw105", x, y, K.white, 1)
            else SlotSprite(P.ghost[j], "paw105g", x, y, K.white, j == 1 and 0.3 or 0.15) end
        end
        HideAll(P.bit)
        Off(P.fBlood[1]); Off(P.fBlood[2]); Off(P.fBlood[3]); Off(P.fBlood[4])
        Off(P.fWhite[1]); Off(P.fWhite[2]); Off(P.fWhite[3]); Off(P.fWhite[4])
    elseif a < C.DRAG then                                           -- the claw bites in and drags down the cut
        local p = (a - C.SWOOP) / (C.DRAG - C.SWOOP)
        local x, y = Round(3 - 6 * p), Round(33 * p)
        SlotSprite(P.paw, p > 0.3 and "paw105b" or "paw105", x, y, K.white, 1)
        for j = 1, 3 do Off(P.ghost[j]) end
        for j = 0, C.BITS - 1 do
            local s = bits[j + 1]
            SlotDot(P.bit[j + 1], Round(x + ((j % 2 == 1) and 1 or -1) * (2 + s * 6 * p)), Round(y - 2 - s * 5),
                (j % 3 ~= 0) and K.tan or K.bloodLt, 0.9)
        end
        local si = floor(p * 4) + 1
        if si > 4 then si = 4 end
        SlotSprite(P.tear, TEAR[si], 0, 0, K.white, 1)
        sx = (a > C.SWOOP and a < 0.3) and Round(sin(a * 120) * 0.8) or 0
    elseif a < C.FLICK then                                          -- the paw flicks away, blood trailing
        local e = (a - C.DRAG) / (C.FLICK - C.DRAG)
        local x, y = Round(-3 - 4 * e), Round(33 + 6 * e)
        SlotSprite(P.paw, "paw105b", x, y, K.white, 1 - e)
        HideAll(P.bit)
        for j = 0, 3 do
            SlotDot(P.fBlood[j + 1], Round(-3 - 4 * e - j * 2), Round(33 + 6 * e + 2 + j), K.bloodLt, 1 - e)
        end
        for j = 1, 4 do
            SlotDot(P.fWhite[j], Round(-3 - 4 * e + j * 0.4), Round(33 + 6 * e - j * 1.6), K.white, (1 - e) * 0.6)
        end
        if a < 0.3 then sx = Round(sin(a * 120) * 0.8) end
    else
        Off(P.paw)
        HideAll(P.bit)
        HideAll(P.fBlood); HideAll(P.fWhite)
    end
    if a > C.DRAG and a < C.FLARE then                               -- the cut flares white hot
        SlotSprite(P.flare, "flare", 0, 17, K.white, (C.FLARE - a) * 0.9)
    end
    local age = a - 0.2                                              -- bits of fur and leather drifting down
    for j = 0, C.DRIFT - 1 do
        if age < 0 then Off(P.drift[j + 1])
        else
            local s = drift[j + 1]
            SlotDot(P.drift[j + 1], Round(3 + (s - 0.5) * 14 + sin(age * 6 + j) * 2), Round(11 + j * 3 + age * age * 30),
                (j % 2 == 1) and K.fur or K.tan, Clamp01(1 - age / 0.4))
        end
    end
    return sx
end

local function RakeEnded()
    V.rakeAt = nil
    Off(P.paw)
    for j = 1, 3 do Off(P.ghost[j]) end
    RakeOff()
end

-- the finisher, sp seconds after the cast; returns the shake offset and the cooling heat (nil before the impact)
local function PaintSpend(now, sp)
    local sx, sy, cool = 0, 0, nil
    local ia = sp - C.IMP
    if sp < C.WIND then                                              -- windup: it rears back, red light gathers
        local e = sp / C.WIND
        local r = 14 + 6 * e
        Sprite(P.halo, r < 15.5 and "halo14" or (r < 18.5 and "halo17" or "halo20"), Round(HX + 30 + e * 4), Round(HY - 30 - e * 4), K.halo, 0.25 + e * 0.35)
        Sprite(P.paw, "paw13", Round(HX + 26 + e * 4), Round(HY + 2 - e * 6), K.white, 1)
        Sprite(P.mask, "paw13m", Round(HX + 26 + e * 4), Round(HY + 2 - e * 6), K.hot, e * 0.35)
        Off(P.comet)
        for j = 1, 3 do Off(P.ghost[j]) end
    elseif sp < C.IMP then                                           -- the swipe: afterimages, four claw streaks, the paw
        local e = (sp - C.WIND) / (C.IMP - C.WIND)
        Off(P.halo); Off(P.mask)
        for j = 3, 1, -1 do
            local ee = max(0, e - j * 0.2)
            Sprite(P.ghost[j], "paw13gr", Round(HX + 30 - 58 * ee), Round(HY - 4 + 28 * ee), K.white, 0.18 * (4 - j))
        end
        local L = Art.LINES[1]
        Sprite(P.comet, "streak", Round(L[1] + (L[3] - L[1]) * e), Round(L[2] + (L[4] - L[2]) * e), K.white, 1)
        Sprite(P.paw, "paw13b", Round(HX + 30 - 58 * e), Round(HY - 4 + 28 * e), K.white, 1)
    else
        Off(P.halo); Off(P.mask); Off(P.comet)
        for j = 1, 3 do Off(P.ghost[j]) end
        if ia < 0.06 then Sprite(P.paw, "paw13b", HX - 28, HY + 24, K.white, 1)   -- the freeze on impact
        else Off(P.paw) end
    end
    if ia < 0 then
        Off(P.scarC); Off(P.scarE)
        HideAll(P.shock); HideAll(P.burst)
        for i = 1, #P.burst do if P.burstD[i] then Off(P.burstD[i]) end end
        Off(P.flashW); Off(P.flashR)
        return 0, 0, nil
    end
    -- the impact
    if ia >= C.SHAKE_FROM and ia < C.SHAKE_TO then
        local d = 1 - (ia - C.SHAKE_FROM) / (C.SHAKE_TO - C.SHAKE_FROM)
        sx, sy = Round(sin(ia * 95) * 3.2 * d), Round(cos(ia * 71) * 2.2 * d)
    end
    local k2 = Clamp01(1 - (ia - C.SCAR_FROM) / C.SCAR_LEN)          -- four rake scars glowing across the hide
    if k2 <= 0 then Off(P.scarC); Off(P.scarE)
    else
        Sprite(P.scarC, "scarc", 0, 0, k2 > 0.6 and K.white or K.hot, k2)
        Sprite(P.scarE, "scare", 0, 0, K.white, k2)
    end
    if ia < C.SHOCK then                                             -- the shockwave
        local r = 4 + ia * 90
        local a = (1 - ia / C.SHOCK) * 0.9
        for t = 0, C.SHOCK_N - 1 do
            local a2 = t / C.SHOCK_N * 2 * pi
            local x, y = Round(HX + cos(a2) * r), Round(HY + sin(a2) * r * 0.7)
            if (x + y) % 2 == 0 and x >= 0 and y >= 0 and x < C.SW and y < C.SH then DotAt(P.shock[t + 1], x, y, K.hot, a)
            else Off(P.shock[t + 1]) end
        end
    else
        HideAll(P.shock)
    end
    if ia < C.BURST then                                             -- the blood burst
        local a = 1 - ia / C.BURST
        local fall = ia * ia * 40
        for j = 1, #Art.BURST do
            local B = Art.BURST[j]
            local d = ia * B[3]
            local x, y = Round(HX + B[1] * d), Round(HY + B[2] * d * 0.7 + fall)
            if x >= 0 and y >= 0 and x < C.SW and y < C.SH then DotAt(P.burst[j], x, y, B[4] == 1 and K.bloodMd or K.bloodLt, a)
            else Off(P.burst[j]) end
            local dk = P.burstD[j]
            if dk then
                if x + 1 < C.SW and y >= 0 and y < C.SH and x + 1 >= 0 then DotAt(dk, x + 1, y, K.bloodDk, a) else Off(dk) end
            end
        end
    else
        HideAll(P.burst)
        for i = 1, #P.burst do if P.burstD[i] then Off(P.burstD[i]) end end
    end
    if ia < C.FLASH_R then                                           -- the flash: white, then red
        if ia < C.FLASH_W then On(P.flashW); Place(P.flashW, 0, 0); TintRGB(P.flashW, 1, 1, 1, 0.85) else Off(P.flashW) end
        On(P.flashR)
        Place(P.flashR, 0, 0)
        TintRGB(P.flashR, K.halo[1], K.halo[2], K.halo[3], Stepped(0.55 * (1 - ia / C.FLASH_R)))
    else
        Off(P.flashW); Off(P.flashR)
    end
    if ia < C.COOL then cool = ia / C.COOL end
    return sx, sy, cool
end

local function SpendEnded()
    V.spendAt = nil
    PawOff()
    HitOff()
end

-- the gashes: a slow flicker while lit; cooling after a finisher
local function PaintGashes(now, cool)
    for i = 1, #P.gash do
        local bar, cb = P.gash[i], P.cool[i]
        local v, a
        if cool then
            -- the cooled gash (dark cut, cream lip) fades in over the lit one, which is the page's heat 1 - 1.6 c mixed toward dark
            -- (the same blend), gone by cool 0.62; the lit gash's wider lip lets go a little after
            local heat = max(0, 1 - cool * 1.6)
            v = 0.9
            a = cool < 0.62 and 1 or Stepped(max(0, 1 - (cool - 0.62) / 0.13))
            local ca = 1 - heat
            if cool > 0.8 then ca = (1 - cool) / 0.2 end
            BarOn(cb, true)
            BarColor(cb, 1, 1, 1, Stepped(max(0, ca)))
        elseif V.red then v, a = 0.9, 1; BarOn(cb, false)
        else v, a = Stepped(0.8 + 0.2 * (sin(now * 2 + i - 1) * 0.5 + 0.5)), 1; BarOn(cb, false) end
        BarColor(bar, v, v, v, a)
    end
end

local function PaintGold(now)
    local v = V.red and 0.9 or Stepped(0.8 + 0.2 * (0.5 + 0.5 * sin(now * 3.2)))
    BarColor(P.gold, v, v, v, 1)
    -- the word breathes by brightness, not alpha: the plaque's dark backing stays solid over the count beneath it
    local w = V.red and 1 or Stepped(0.75 + 0.25 * sin(now * 4))
    BarColor(P.finish, w, w, w, 1)
end

local function PaintEmbers(now)
    for i = 1, C.EMBERS do
        local bar = P.ember[i]
        if V.red then BarOn(bar, false)
        else
            local ph = (now * 0.6 + (i - 1) / C.EMBERS) % 1
            BarOn(bar, true)
            BarAt(bar, Round(HX - 24 + ((i - 1) % 5) * 12 + sin(now * 2 + (i - 1)) * 3), Round(HY + 12 - ph * 42))
            BarAlpha(bar, Stepped((1 - ph) * 0.85))
        end
    end
end

-- a drop that lets go of a slot's first drip and falls, a little time after the slot was cut
local function PaintDrops(now)
    local settled = not (V.rakeAt and now - V.rakeAt < C.SETTLE_DROPS) and not V.spendAt
    for i, g in ipairs(Art.GASH) do
        local A, B = P.dropA[i], P.dropB[i]
        local ph = ((now + (i - 1) * 0.7) % g.per) / g.per
        local dy = g.drip + 2 + ph * ph * 160
        if V.red or not settled or ph >= 0.35 or dy >= 30 then
            BarOn(A, false); BarOn(B, false)
        else
            local al = Stepped(1 - ph * 2)
            BarOn(A, true); BarOn(B, true)
            BarAt(A, g.dropX, g.dropY + Round(dy)); BarAt(B, g.dropX, g.dropY + Round(dy) + 1)
            BarAlpha(A, al); BarAlpha(B, al)
        end
    end
end

-- the Thorns corner
local LABELS = { [false] = { m = {}, s = {} }, [true] = { m = {}, s = {} } }
for _, e in ipairs({ false, true }) do
    for n = 0, 99 do
        LABELS[e].m[n] = (e and "~" or "") .. n .. "m"
        LABELS[e].s[n] = (e and "~" or "") .. n .. "s"
    end
end

local function ThornsOff()
    for i = 0, 9 do Off(P.thSeg[i]); Off(P.thTip[i]) end
    Off(P.thGone); Off(P.thTime); Off(P.thWord)
end

local function PaintThorns(now)
    if V.thKnown == false then ThornsOff() return end
    local mode, left, est = State.Thorns(now)
    local red = V.red
    if mode ~= "up" then
        local combat = type(InCombatLockdown) == "function" and InCombatLockdown() == true
        for i = 0, 9 do Off(P.thSeg[i]); Off(P.thTip[i]) end
        Off(P.thTime)
        if mode == "gone" and not combat and V.thKnown == true then
            local a = red and 0.7 or (0.55 + 0.45 * abs(sin(now * pi / 0.9)))
            Sprite(P.thGone, "thgone", 0, 0, K.amber, Stepped(a))
            On(P.thWord)
            TextWord(P.thWord, "THORNS")
            TextAt(P.thWord, top, 12, 26)
            TextColor(P.thWord, K.amber, Stepped(a))
        else
            Off(P.thGone); Off(P.thWord)
        end
        return
    end
    Off(P.thGone); Off(P.thWord)
    local low = left < C.TH_LOW
    local pulse = (low and not red) and Stepped(0.55 + 0.45 * abs(sin(now * pi / 0.7))) or 1
    local lit = ceil(left / C.TH_LEN * 10)
    local col, tip = low and K.amber or K.thorn, low and K.amberTip or K.thornTip
    for i = 0, 9 do
        local on = i < lit
        if on then
            Sprite(P.thSeg[i], SEG[i], 0, 0, col, pulse); Sprite(P.thTip[i], TIP[i], 0, 0, tip, pulse)
        else
            Sprite(P.thSeg[i], SEG[i], 0, 0, K.line, 1); Sprite(P.thTip[i], TIP[i], 0, 0, K.line, 1)
        end
    end
    local n = low and ceil(left) or ceil(left / 60)
    if n > 99 then n = 99 elseif n < 0 then n = 0 end
    On(P.thTime)
    TextWord(P.thTime, LABELS[est and true or false][low and "s" or "m"][n])
    TextAt(P.thTime, top, 12, 12)
    TextColor(P.thTime, low and K.amber or K.white, pulse)
end

local function Paint(now, data)
    if not f then return end
    V.red = data and data.reduced == true or false
    if V.reread > 0 then V.reread = V.reread - 1; Reread() end
    if V.holdGash and now >= V.holdGash then V.holdGash = nil; Apply() end
    if V.holdRest and now >= V.holdRest then V.holdRest = nil; Apply() end
    if V.thPoll <= now then
        V.thPoll = now + C.POLL
        local ok, k = pcall(State.Known, "thorns")
        if ok then V.thKnown = k else V.thKnown = nil end
    end

    local sx, sy, cool = 0, 0, nil
    if V.spendAt then
        local sp = now - V.spendAt
        if sp >= C.IMP + C.COOL then SpendEnded()
        else
            RakeEnded()
            sx, sy, cool = PaintSpend(now, sp)
        end
    elseif V.rakeAt then
        local a = now - V.rakeAt
        if a >= C.RAKE_LEN then RakeEnded()
        else sx = PaintRake(now, a) end
    end
    Shake(V.red and 0 or sx, V.red and 0 or sy)
    PaintGashes(now, cool)
    PaintGold(now)
    PaintEmbers(now)
    PaintDrops(now)
    PaintThorns(now)
end

-------------------------------------------------------------------------------
-- The form seams
-------------------------------------------------------------------------------

local function OnShow()
    SetEvents(true)
    Reread()
    V.reread = C.REREAD
end

local function OnHide()
    SetEvents(false)
    V.holdGash, V.holdRest, V.buildAt = nil, nil, nil
    V.rakeAt, V.spendAt = nil, nil
    if P.paw then
        RakeEnded(); PawOff(); HitOff()
        Shake(0, 0)
        Apply()
    end
end

local spec = {
    build = function(parent)
        Build(parent)
        f:SetScript("OnShow", OnShow)
        f:SetScript("OnHide", OnHide)
        Seat(function() P.hide.fsName, P.hide.fsX = nil, nil; Sprite(P.hide, "hide", 0, 0, K.white, 1) end)
        return f
    end,
    seat = function(_, _, spx)
        if type(spx) == "number" and spx > 0 then V.spx = spx end
        for i = 1, #seats do
            local ok, err = pcall(seats[i])
            if not ok then LogOnce("seat", err) end
        end
    end,
    paint = function(now, data)
        local ok, err = pcall(Paint, now, data)
        if not ok then LogOnce("paint", err) end
    end,
    show = function() if f then f:Show() end end,
    hide = function() if f then f:Hide() end end,
}
Cat.spec, Cat.Paint = spec, Paint

Druid.RegisterForm("cat", spec)
