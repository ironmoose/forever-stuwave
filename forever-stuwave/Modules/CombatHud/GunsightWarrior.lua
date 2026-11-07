-- Forever STUwave: Gunsight Class Module for the Warrior: the roaring helm and its rune rings
--
-- The approved design is the design mockup "Warrior Roaring Helm, rune ring" (2026-11-07). Two rings stand side by side:
--   * BATTLE SHOUT (left, rage red): an 8-bit horned helm with angry eyes and a big bushy beard, 8 rune tiles orbiting it
--     (one lap every ORBIT s). Lit runes = ceil(remaining / duration * 8); the rest go dark, so the glowing arc shrinks as it
--     turns. One rune left is amber. On a cast the helm ROARS (mouth torn open, eyes blazing, scream lines, the beard puffed out
--     and whipping, its tips stretching), the runes light round one by one and whirl fast, then ease into the drift. Between
--     shouts it BREATHES HEAVY with its mouth shut and the beard still: up on the inhale, breath puffs off the mouth on the
--     exhale. Eyes cool white hot -> red -> dim as the shout drains. Gone: the ring stops as amber dashed outlines and the helm
--     goes cold violet in the same spot with no label. CALM out of combat with no attackable target (dark eyes, dim dashes,
--     nothing moves); a NUDGE in combat or on an attackable target: amber eyes, the dashes on an amber glow pulse like a
--     missing buff tile, and an amber halo round the helm pulses with them.
--   * DEMORALIZING SHOUT (right, grim violet, smaller tiles, orbiting the other way, the same beard in violet): the time always wears a
--     "~" (timed from the player's own cast, the target's debuff cannot be read in combat). On a cast it GROWLS: the angry eyes glow
--     pink, teeth clench, the helm shudders, the beard whips like the roar's, the runes are sucked in and slam back out past the ring, and a dotted ring of
--     dread ripples out. Not learned yet: a dotted ring and L14.
--
-- UNITS. The art is drawn on a sprite grid: one sprite px is C.SPX image px (the mockup's canvas is 150 x 86 sprite px). Every
-- position is rounded to a whole sprite px before it is seated, as the mockup's canvas does. The helm frames and rune tiles are
-- baked full colour by tools/assets/generate_warrior_helm.py (2 texels per sprite px); FRAME below must match its HELM_FRAMES.
--
-- DATA. Everything comes from FS.WarriorShouts (WarriorShouts.lua): Get, Lit, Remaining, Tick, Subscribe. Its ledger listens
-- from Start() on and never stops; this file only paints. No secret is read here.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide
-- stops the OnUpdate and the subscription; onShow subscribes, refreshes and repaints. Plain frames only.
--
-- TICKER. One OnUpdate on the module frame while it is shown, at most every C.TICK s (the orbit and the breath move all the
-- time). The tick path allocates nothing: positions are numbers, texcoords and labels are written only when they change.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightWarrior = FS.GunsightWarrior or {}
local Warrior = FS.GunsightWarrior

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil, cos, sin, pi = math.floor, math.ceil, math.cos, math.sin, math.pi

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    CY = 35, LABEL_Y = 74,             -- ring centre and label line (sprite px from the top)
    ORBIT = 14,                        -- seconds per lap
    BREATH = 1.5,                      -- seconds per breath
    TICK = 1 / 30,
    ROAR = 1.2, ROAR_STEP = 0.15,      -- the roar lasts ROAR s, a frame every ROAR_STEP
    SWEEP = 0.5,                       -- the runes light round in SWEEP s
    WHIRL = 9,                         -- extra radians the whirl adds at the cast, easing out over ROAR
    GROWL = 1.1,                       -- the growl's whole length (the ripple ends there)
    NUDGE = 1.4,                       -- seconds per pulse when nudging (the HUD's missing-buff pulse)
    CALM_A = 0.5,                      -- the gone dashes' alpha when calm
    NUDGE_LO = 0.35,                   -- the nudge runes (dashes on an amber glow) pulse from this alpha to 1, the helm halo 0 to 1
    DROP = 5,                          -- image px the module sits below the area's top
    HELM_W = 32, HELM_H = 32,          -- the helm sprite (the beard flares past the helm)
    HELM_OX = 3,                       -- where the 26 px helm's own x = 0 sits in the sprite
    WHIP_STEP = 0.075,                 -- the cast beard poses (4) step this fast
    TRACK_STEP = 6,                    -- degrees between the orbit track's dots
    RIPPLE_STEP = 6,
    LABEL_SIZE = 11,                   -- image px
    CAP = 325 / 1024,                  -- Mononoki Bold: the line box's middle sits CAP * size above the baseline (as GunsightShaman)
    TEXT_MAX_S = 99,
    RINGS = {
        battle = { cx = 42, r = 27, tw = 7, th = 9, atlas = "warrior_runes_big", spin = 1 },
        demo = { cx = 112, r = 24, tw = 5, th = 7, atlas = "warrior_runes_small", spin = -1, levelText = "L14" },
    },
    COLORS = {
        track = Hex("#a855f7"), pink = Hex("#ff8098"), amber = Hex("#ffb648"), violet = Hex("#e09cff"),
        muted = Hex("#9d93c4"), yellow = Hex("#ffcf3a"), puff = Hex("#ffdce1"), ripple = Hex("#ff5ad0"),
        rippleDark = Hex("#5a148c"),
    },
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Warrior.C = C
local K = C.COLORS

-- warrior_helm.tga frame order (generate_warrior_helm.py HELM_FRAMES)
local FRAME = {
    roar1 = 0, roar2 = 1, roar3 = 2, roar4 = 3,                          -- the roar, four beard whip poses
    hot = 4, red = 5, dim = 6,
    grimHot = 7, grimRed = 8, grimDim = 9,
    growl1 = 10, growl2 = 11, growl3 = 12, growl4 = 13,                  -- the growl, the same four poses
    cold = 14, coldFlick = 15,
}
Warrior.FRAME = FRAME
-- rune atlas rows (BIG_KINDS / SMALL_KINDS)
local ROW = {
    battle = { lit = 0, lit2 = 1, amber = 2, off = 3, gone = 4, nudge = 5 },
    demo = { lit = 0, lit2 = 1, amber = 2, off = 3, gone = 4, locked = 5, nudge = 6 },
}
local ATLAS, HELM_CELL, RUNE_CELL_W, RUNE_CELL_H, SCALE = 256, 64, 24, 28, 2
local MARGIN = 2                       -- the glow margin baked round every tile, sprite px

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightwarrior_" .. key, "|cffff4488Forever STUwave|r: gunsight warrior module: " .. tostring(msg))
    end
end

local Shouts
local mod
local R = {}                   -- key -> ring parts
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc = false, false, 0
local KEYS = { "battle", "demo" }
local castAt = { battle = nil, demo = nil }
local lastSpin = { battle = 0, demo = 0 }

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

-- Seat a region's top left at sprite (x, y) inside the module, only when it moved.
local function Place(t, x, y)
    if t.fsX == x and t.fsY == y then return end
    t.fsX, t.fsY = x, y
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", mod, "TOPLEFT", S(x), -S(y))
end

local function Forget(t) t.fsX, t.fsY = nil, nil end

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

local function Dot(layer, sub, c, a, w, h)
    local t = mod:CreateTexture(nil, layer, nil, sub or 0)
    t:SetTexture(FLAT)
    t:SetVertexColor(c[1], c[2], c[3], a or 1)
    t.fsW, t.fsH = w or 1, h or 1
    Seat(function() t:SetSize(S(t.fsW), S(t.fsH)); Forget(t) end)
    return t
end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

-------------------------------------------------------------------------------
-- Labels
-------------------------------------------------------------------------------

local SEC, EST_SEC, MIN, EST_MIN = {}, {}, {}, {}
for i = 0, C.TEXT_MAX_S do SEC[i] = i .. "s"; EST_SEC[i] = "~" .. i .. "s" end
for i = 1, 9 do MIN[i] = i .. "m"; EST_MIN[i] = "~" .. i .. "m" end

local function TimeLabel(rem, est)
    if rem <= C.TEXT_MAX_S then
        local n = ceil(rem)
        if n < 0 then n = 0 end
        return est and EST_SEC[n] or SEC[n]
    end
    local m = ceil(rem / 60)
    if m > 9 then m = 9 end
    return est and EST_MIN[m] or MIN[m]
end
Warrior.TimeLabel = TimeLabel

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function BuildRing(key)
    local d = C.RINGS[key]
    local p = { key = key, def = d, runes = {}, track = {}, view = {} }

    for a = 0, 359, C.TRACK_STEP do
        local t = Dot("BACKGROUND", 0, K.track, 0.18)
        local rad = a * pi / 180
        t.fsSX, t.fsSY = floor(d.cx + cos(rad) * d.r + 0.5), floor(C.CY + sin(rad) * d.r + 0.5)
        p.track[#p.track + 1] = t
    end

    local tw, th = d.tw + 2 * MARGIN, d.th + 2 * MARGIN
    for i = 1, 8 do
        local t = mod:CreateTexture(nil, "ARTWORK", nil, 1)
        SetTex(t, MEDIA .. d.atlas .. ".tga")
        Seat(function() t:SetSize(S(tw), S(th)); Forget(t) end)
        p.runes[i] = t
    end

    local halo = mod:CreateTexture(nil, "ARTWORK", nil, 2)
    SetTex(halo, MEDIA .. "warrior_helm_glow.tga")
    Seat(function() halo:SetSize(S(C.HELM_W), S(C.HELM_H)); Forget(halo) end)
    halo:Hide()
    p.halo = halo

    local helm = mod:CreateTexture(nil, "ARTWORK", nil, 3)
    SetTex(helm, MEDIA .. "warrior_helm.tga")
    Seat(function() helm:SetSize(S(C.HELM_W), S(C.HELM_H)); Forget(helm) end)
    p.helm = helm

    if key == "battle" then
        p.lines = {}
        for i = 1, 18 do p.lines[i] = Dot("OVERLAY", 1, K.pink, 1); p.lines[i]:Hide() end
        p.puffs = {}
        for i = 1, 4 do p.puffs[i] = Dot("OVERLAY", 1, K.puff, 0.75); p.puffs[i]:Hide() end
    else
        p.ripple = {}
        for a = 0, 359, C.RIPPLE_STEP do
            local o = Dot("ARTWORK", 0, K.ripple, 0.9)
            local i = Dot("ARTWORK", 0, K.rippleDark, 0.7)
            o.fsRad, i.fsRad = a * pi / 180, (a + 3) * pi / 180
            o:Hide(); i:Hide()
            p.ripple[#p.ripple + 1] = o
            p.ripple[#p.ripple + 1] = i
        end
    end

    local fs = mod:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("CENTER")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(C.LABEL_SIZE), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint("CENTER", mod, "TOPLEFT", S(d.cx), -(S(C.LABEL_Y) - ui(C.CAP * C.LABEL_SIZE)))
    end)
    fs:SetText("")
    p.label = fs
    return p
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local function HelmFrame(p, f)
    local v = p.view
    if v.frame == f then return end
    v.frame = f
    local l, t = (f % 4) * HELM_CELL / ATLAS, floor(f / 4) * HELM_CELL / ATLAS
    p.helm:SetTexCoord(l, l + C.HELM_W * SCALE / ATLAS, t, t + C.HELM_H * SCALE / ATLAS)
end

local function RuneKind(p, i, row)
    local t = p.runes[i]
    if t.fsRow == row then return end
    t.fsRow = row
    local d = p.def
    local l, top = (i - 1) * RUNE_CELL_W / ATLAS, row * RUNE_CELL_H / ATLAS
    t:SetTexCoord(l, l + (d.tw + 2 * MARGIN) * SCALE / ATLAS, top, top + (d.th + 2 * MARGIN) * SCALE / ATLAS)
end

local function Label(p, text, c)
    local v = p.view
    if v.text ~= text then
        v.text = text
        p.label:SetText(text)
    end
    TextColor(p.label, c, 1)
end

local function HideAll(list)
    if not list then return end
    for i = 1, #list do
        local t = list[i]
        if t.fsOn ~= false then t.fsOn = false; t:Hide() end
    end
end

local function ShowDot(t, x, y, c, a)
    if t.fsOn ~= true then t.fsOn = true; t:Show() end
    Place(t, x, y)
    if t.fsA ~= a or t.fsC ~= c then
        t.fsA, t.fsC = a, c
        t:SetVertexColor(c[1], c[2], c[3], a)
    end
end

-- Growl: the runes' radius factor, the helm shake and the ripple's progress (or nil)
local IsSecret = FS.IsSecret or function() return false end

-- Gone and worth a shout: in combat, or the target is something the player can attack. A secret or failed read is "no".
local function WantsShout()
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return true end
    if type(UnitCanAttack) ~= "function" then return false end
    local ok, can = pcall(UnitCanAttack, "player", "target")
    if not ok or IsSecret(can) then return false end
    return can == true
end
Warrior.WantsShout = WantsShout

local function RuneAlpha(t, a)
    if t.fsA2 == a then return end
    t.fsA2 = a
    t:SetAlpha(a)
end

local function Growl(t)
    if not t then return 1, 0, nil end
    local k = 1
    if t < 0.22 then k = 1 - 0.45 * (t / 0.22)
    elseif t < 0.32 then k = 0.55 + 0.65 * ((t - 0.22) / 0.1)
    elseif t < 0.6 then k = 1.2 - 0.2 * ((t - 0.32) / 0.28) end
    local shake = 0
    if t < 0.7 then shake = (floor(t / 0.05) % 2 == 1) and 1 or -1 end
    local rip = nil
    if t >= 0.25 and t < C.GROWL then rip = (t - 0.25) / (C.GROWL - 0.25) end
    return k, shake, rip
end

local function PaintRing(p, now)
    local key, d = p.key, p.def
    local st = Shouts.Get(key)
    local rows = ROW[key]
    local locked = key == "demo" and not st.known
    local n = locked and 0 or Shouts.Lit(key, now)
    local since = castAt[key] and (now - castAt[key]) or nil

    -- the cast animations
    local roarK, sweep, whirl, growlT = nil, nil, 0, nil
    if key == "battle" and since and since < C.ROAR and n > 0 then
        roarK = floor(since / C.ROAR_STEP)
        if since < C.SWEEP then
            sweep = ceil(since / C.SWEEP * 8)
            if sweep < 1 then sweep = 1 end
        end
        local e = 1 - since / C.ROAR
        whirl = e * e * C.WHIRL
    elseif key == "demo" and since and since < C.GROWL and n > 0 then
        growlT = since
    end
    local gk, shake, rip = Growl(growlT)

    -- the orbit: drifts while the shout is up, stops where it is when it is gone
    local spin = lastSpin[key]
    if n > 0 then
        spin = d.spin * (now * 2 * pi / C.ORBIT) + whirl
        lastSpin[key] = spin
    else
        spin = 0
    end

    local lit = sweep or n
    local nudge = n == 0 and not locked and WantsShout()
    local goneA, beat = C.CALM_A, 0
    if nudge then
        beat = floor((0.5 + 0.5 * sin(now * 2 * pi / C.NUDGE)) * 20 + 0.5) / 20         -- 0..1 in 20 steps: few alpha writes
        goneA = C.NUDGE_LO + (1 - C.NUDGE_LO) * beat
    end
    for i = 1, 8 do
        local a = -pi / 2 + (i - 1) * pi / 4 + spin
        local rr = d.r * gk
        local x = floor(d.cx + cos(a) * rr - d.tw / 2 + 0.5)
        local y = floor(C.CY + sin(a) * rr - d.th / 2 + 0.5)
        local row
        if locked then row = rows.locked
        elseif n == 0 then row = nudge and rows.nudge or rows.gone
        elseif i > lit then row = rows.off
        elseif n == 1 and not sweep then row = rows.amber
        else row = (roarK or (growlT and growlT < 0.7)) and rows.lit2 or rows.lit end
        RuneKind(p, i, row)
        RuneAlpha(p.runes[i], (row == rows.gone or row == rows.nudge) and goneA or 1)
        Place(p.runes[i], x - MARGIN, y - MARGIN)
    end

    -- the helm
    local hx, hy = d.cx - 13, C.CY - 12
    -- the nudge's halo round the cold helm
    if nudge then
        if p.halo.fsOn ~= true then p.halo.fsOn = true; p.halo:Show() end
        RuneAlpha(p.halo, beat)
        Place(p.halo, d.cx - 13 - C.HELM_OX, C.CY - 12)
    elseif p.halo.fsOn ~= false then
        p.halo.fsOn = false
        p.halo:Hide()
    end

    if locked then
        p.helm:Hide()
    else
        p.helm:Show()
        local f
        if n == 0 then
            f = nudge and FRAME.coldFlick or FRAME.cold    -- amber eyes, steady, only when a shout is wanted; never sinks
        elseif key == "battle" then
            local frac = (Shouts.Remaining(key, now) or 0) / (st.duration or 1)
            local eye = frac > 0.66 and "hot" or (frac > 0.25 and "red" or "dim")
            if n == 1 then eye = "dim" end
            if roarK then
                f = FRAME.roar1 + floor(since / C.WHIP_STEP) % 4
                hy = hy - ((roarK % 2 == 1) and 1 or 0)
            else
                -- the beard holds still between shouts; the breath is the lift and the puffs
                local ph = (now % C.BREATH) / C.BREATH
                f = FRAME[eye]
                if ph > 0.15 and ph < 0.55 then hy = hy - 1 end
            end
        else
            local frac = (Shouts.Remaining(key, now) or 0) / (st.duration or 1)
            if growlT and growlT < 0.9 then f = FRAME.growl1 + floor(growlT / C.WHIP_STEP) % 4
            elseif n == 1 or frac <= 0.25 then f = FRAME.grimDim
            elseif frac > 0.66 then f = FRAME.grimHot
            else f = FRAME.grimRed end
            hx = hx + shake
        end
        HelmFrame(p, f)
        Place(p.helm, hx - C.HELM_OX, hy)
    end

    -- the battle shout's scream lines and breath puffs
    if p.lines then
        if roarK then
            local k = roarK % 3
            local dd = 2 + k * 2
            local c = (k % 2 == 1) and K.yellow or K.pink
            local j = 0
            for dy = -1, 1 do
                for s = 0, 2 do
                    local py = hy + 16 + dy * (dd + s)
                    j = j + 1; ShowDot(p.lines[j], hx + 4 - dd - s, py, c, 1)
                    j = j + 1; ShowDot(p.lines[j], hx + 21 + dd + s, py, c, 1)
                end
            end
        else
            HideAll(p.lines)
        end
        local ph = (now % C.BREATH) / C.BREATH
        if n > 0 and not roarK and ph >= 0.55 then
            local puff = (ph - 0.55) / 0.45
            local a, dd = (1 - puff) * 0.75, floor(puff * 4 + 0.5)
            local y1, y2 = hy + 17 - floor(puff * 2 + 0.5), hy + 16 - floor(puff * 3 + 0.5)
            ShowDot(p.puffs[1], hx + 4 - dd, y1, K.puff, a)
            ShowDot(p.puffs[2], hx + 21 + dd, y1, K.puff, a)
            if puff > 0.3 then
                ShowDot(p.puffs[3], hx + 3 - dd, y2, K.puff, a)
                ShowDot(p.puffs[4], hx + 22 + dd, y2, K.puff, a)
            else
                for i = 3, 4 do
                    local t = p.puffs[i]
                    if t.fsOn ~= false then t.fsOn = false; t:Hide() end
                end
            end
        else
            HideAll(p.puffs)
        end
    end

    -- the demoralizing shout's ripple of dread
    if p.ripple then
        if rip then
            local rr, al = 8 + rip * (d.r + 14), (1 - rip) * 0.9
            for i = 1, #p.ripple do
                local t = p.ripple[i]
                local inner = i % 2 == 0
                local r2 = inner and rr - 1 or rr
                ShowDot(t, floor(d.cx + cos(t.fsRad) * r2 + 0.5), floor(C.CY + sin(t.fsRad) * r2 + 0.5),
                    inner and K.rippleDark or K.ripple, inner and al * 0.8 or al)
            end
        else
            HideAll(p.ripple)
        end
    end

    -- the label
    if locked then
        Label(p, d.levelText, K.muted)
    elseif n == 0 then
        Label(p, "", K.violet)                         -- gone: no label, the cold helm and the dashed ring say it
    else
        local est = key == "demo" or st.source == "cast"
        local c = (n == 1) and K.amber or (key == "battle" and K.pink or K.violet)
        Label(p, TimeLabel(Shouts.Remaining(key, now) or 0, est), c)
    end
end

local function PaintAll(now)
    for _, key in ipairs(KEYS) do
        local p = R[key]
        if p then
            local ok, err = pcall(PaintRing, p, now)
            if not ok then LogOnce("paint", err) end
        end
    end
end

local function SeatTrack()
    for _, key in ipairs(KEYS) do
        local p = R[key]
        if p then
            for i = 1, #p.track do
                local t = p.track[i]
                Forget(t)
                Place(t, t.fsSX, t.fsSY)
            end
        end
    end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Shouts.Tick, now)
    if not ok then LogOnce("tick", err) end
    PaintAll(now)
end

local function Sync()
    local want = subscribed and mod ~= nil
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

local function OnChange(key, reason)
    if reason == "cast" then castAt[key] = GetTime() end
    if subscribed then PaintAll(GetTime()) end
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

-- The module's top left in image px, and a listener hook for whoever seats something over the helms (GunsightWarriorClick.lua's
-- click catchers): fn(OX, OY) after every seat.
local seatListeners = {}
function Warrior.Origin() return OX, OY end
function Warrior.OnSeat(fn)
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
        SeatTrack()
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
        LogOnce("notheme", "Theme is missing, the Warrior module is not built")
        return nil
    end
    Shouts = FS.WarriorShouts
    if not (Shouts and Shouts.Get and Shouts.Subscribe) then
        LogOnce("noshouts", "FS.WarriorShouts is missing, the Warrior module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightWarrior", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    local ok, err = pcall(function()
        R.battle = BuildRing("battle")
        R.demo = BuildRing("demo")
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        R = {}
        return nil
    end
    Warrior.frame, Warrior.rings = mod, R
    if Shouts.Start then Shouts.Start() end
    SeatTrack()
    PaintAll(GetTime())
    return mod
end

local function OnAreaShown()
    if not mod then return end
    if not subscribed then
        subscribed = true
        Shouts.Subscribe(OnChange)
    end
    local ok, err = pcall(Shouts.Refresh)
    if not ok then LogOnce("refresh", err) end
    PaintAll(GetTime())
    Sync()
end

local function OnAreaHidden()
    if not mod then return end
    if subscribed then
        subscribed = false
        Shouts.Unsubscribe(OnChange)
    end
    Sync()
end

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "WARRIOR" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
