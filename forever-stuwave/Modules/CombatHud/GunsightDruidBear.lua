-- Forever STUwave: the Druid's BEAR form look (registered with FS.GunsightDruid.RegisterForm("bear", ...))
--
-- THE ROAR. In Bear form the class slot is a Demoralizing Roar tracker, the design mockup "Druid Roar Bear Animated" (2026-11-17,
-- candidate 1): a roaring bear head with an animated jaw (a snarl that breathes, a full roar on the cast), eyes that glow and flare
-- white on the roar, a head that lunges 3 px and bobs, a floating storm aura behind it with an ordered dither ragged edge (no box)
-- and lightning that forks through it on the roar, and five sound arcs a side as the timer: ten arcs of 3 s each, the outer ones
-- go first, amber for the last 5 s. Down in combat the bear shuts its mouth, greys and dims, the cloud stands still and ROAR
-- pulses amber; down out of combat it rests dim with no cloud. A roar not learned draws nothing of this.
--
-- THE THORNS CORNER. Thorns runs out while you grind in a form, so a small ring of ten thorn segments sits in the top left corner
-- (design mockup "Druid Gunsight Module: One Layout Per Form", 2026-11-16): a segment goes dark for every minute that has run
-- out, the last minute is amber and pulses, the time is under it ("~" before a ledger time), and gone out of combat only a dashed
-- amber ring and THORNS. In combat a missing Thorns, or one nothing is known about, draws nothing; not learned draws nothing.
--
-- ART. tools/assets/generate_druid_bear.py bakes one atlas (druid_bear_1.tga, one texel per sprite px) and the manifest
-- FS.DruidBearArt (DruidBearArt.lua; never edit it by hand). The big pixel fields are sprites (the 24 frame cloud loop and its
-- flash overlays, the bolts, the halo, the ten arcs in three layers, the 18 shock ring steps, the head frames, the Thorns segments);
-- everything else is live here: every eye pixel, the arcs' state, the head's frame, lunge and bob, the shake, the labels. White
-- masks are tinted here, the rest keep their baked colours.
--
-- UNITS. One sprite px is spx image px (1.25) on the 150 x 86 canvas the Druid module hands over; every position is a whole sprite
-- px. The head frame is the module's own frame, moved as one (the eyes ride on it); the halo, arcs, head and rings share one
-- shaker frame; the cloud, the lightning, the Thorns corner and the labels do not shake.
--
-- DATA. Demoralizing Roar is on the enemies round the player, which an addon cannot read in combat, so the clock is the player's own
-- cast ledger: UNIT_SPELLCAST_SUCCEEDED matched by spell NAME (any rank), 30 s, shown with "~" (the Warrior's Demoralizing Shout
-- is the same). Out of combat, while FS.AurasReadable(), the target's debuff by name is read once a second while the ledger says
-- it is up: a plain expiry replaces the estimate (no "~"), a readable "not there" ends it. A secret answer says nothing.
-- Thorns is State.Thorns (DruidState.lua). Nothing here reads a number that can be secret; every value is checked first.
--
-- VISIBILITY. The Druid module's host hides with no target, so this look follows it; show() and hide() are the form switch. The
-- ledger listens from the first build on and never stops (a roar cast while the host is hidden cannot be read back).
--
-- TICK. The Druid module paints this at 30 Hz while it is shown. A paint allocates nothing: strings are built at load, colours are
-- shared tables, a region is written only when its sprite, place or colour changes.
--
-- Reduced motion (data.reduced): no shake, lunge, bob, breath, flash, lightning, shock rings, wave, flicker or pulses; the jaw
-- still opens on the cast and the arcs, label and amber still say the time.

local _, FS = ...

local Druid = FS.GunsightDruid
local Gunsight = FS.Gunsight
local Art = FS.DruidBearArt
local State = FS.DruidState
if not (type(Druid) == "table" and Druid.RegisterForm) then return end
if not (Gunsight and Gunsight.ui) then return end

FS.GunsightDruidBear = FS.GunsightDruidBear or {}
local Bear = FS.GunsightDruidBear

local floor, ceil, min, max, sin, cos, abs, pi = math.floor, math.ceil, math.min, math.max, math.sin, math.cos, math.abs, math.pi
local IsSecret = FS.IsSecret or function() return false end

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SW = 150, SH = 86,                -- the canvas, sprite px
    CX = 75,
    HCY = 34,                         -- the head's centre row on the page (CY - 2)
    HX = 43,                          -- the head's left (CX - 32)
    HEAD = 64,
    ROAR_S = 30,                      -- Demoralizing Roar lasts 30 s on every rank
    PIECE_S = 3,                      -- seconds one arc stands for
    WARN_S = 5,                       -- amber for the last seconds
    ROAR_LEN = 1.02,                  -- seconds of the roar's jaw frames
    SHAKE_S = 0.4, RINGS_S = 0.6,
    FLASH_S = 0.6, FLICKER_EVERY = 5.3, FLICKER_S = 0.25,
    READ_EVERY = 1,                   -- seconds between the out of combat target reads
    READ_AFTER = 0.3,                 -- seconds after our own cast before the first read
    ABSENT_GRACE = 1.5,               -- a readable "not on the target" ends the ledger only this long after the cast
    NUM_X = 119, NUM_Y = 74.5,        -- the seconds, centred (the page: x CX + 44, glyph rows 72 to 76)
    NUM_PX = 9,
    WORD_X = 75, WORD_Y = 80.5,       -- ROAR, centred
    WORD_PX = 9,
    TH_LABEL_X = 12, TH_LABEL_Y = 28, TH_PX = 8, TH_WORD_PX = 6.5,
    TH_LOW = 60,                      -- the last minute is amber
    TH_SEGMENTS = 10,
}
Bear.C = C

local K = {
    roar = Hex("#ff6a2a"), roarh = Hex("#ffc890"), amber = Hex("#ffb648"), amberh = Hex("#ffe0a0"),
    pink = Hex("#ff3aa0"), eye = Hex("#ff4ab8"), white = { 1, 1, 1 }, pure = { 1, 1, 1 },
    num = Hex("#c8b8ff"), shadow = Hex("#04040c"), thText = Hex("#f3fbff"),
}
Bear.COLORS = K

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "druidbear_" .. key, "|cffff4488Forever STUwave|r: druid bear: " .. tostring(msg))
    end
end

if not (type(Art) == "table" and type(Art.sprites) == "table" and Art.FILE) then
    LogOnce("noart", "FS.DruidBearArt is missing, the Bear look is not registered")
    return
end
local SPR = Art.sprites
local FRAMES, STEPS = Art.AURA_FRAMES, Art.RING_STEPS
local LOOP = Art.AURA_LOOP

-- every sprite name the paint uses, built once so a paint never concatenates
local NAME = { aura = {}, light = { [35] = {}, [121] = {} }, bolt = { [35] = "bolt35", [121] = "bolt121" }, arc = {}, ring = {},
    thLive = {}, thAmber = {}, thDry = {}, head = {} }
for f = 0, FRAMES - 1 do
    NAME.aura[f] = "aura_" .. f
    NAME.light[35][f] = "light35_" .. f
    NAME.light[121][f] = "light121_" .. f
end
for p = 0, 9 do NAME.arc[p] = { a = "arc_" .. p .. "_a", b = "arc_" .. p .. "_b", c = "arc_" .. p .. "_c" } end
for i = 0, STEPS - 1 do NAME.ring[i] = "ring_" .. i end
for i = 0, C.TH_SEGMENTS - 1 do
    NAME.thLive[i], NAME.thAmber[i], NAME.thDry[i] = "th_seg_" .. i .. "_live", "th_seg_" .. i .. "_amber", "th_seg_" .. i .. "_dry"
end
for _, n in ipairs({ "open", "mid", "rest", "k11", "k12", "k13", "dim_combat", "dim_ooc" }) do NAME.head[n] = "head_" .. n end
Bear.NAME = NAME

-- the time labels, every string built once: NUM[est][n] for the Roar, TH[est][unit][n] for Thorns
local NUM = { [false] = {}, [true] = {} }
for n = 0, C.ROAR_S + 1 do NUM[false][n], NUM[true][n] = tostring(n), "~" .. n end
local TH = { [false] = { M = {}, S = {} }, [true] = { M = {}, S = {} } }
for _, e in ipairs({ false, true }) do
    for n = 0, 99 do
        TH[e].M[n] = (e and "~" or "") .. n .. "M"
        TH[e].S[n] = (e and "~" or "") .. n .. "S"
    end
end

-------------------------------------------------------------------------------
-- The Demoralizing Roar ledger
-------------------------------------------------------------------------------

local ROAR_NAME = "Demoralizing Roar"
local roar = { known = nil, castAt = nil, expires = nil, est = true, nextRead = 0 }
local thornsKnown = nil
local started = false
local nameCache = {}

local function Plain(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

local function SpellNameOf(id)
    if type(id) ~= "number" or IsSecret(id) then return nil end
    local hit = nameCache[id]
    if hit then return hit end
    local name
    if C_Spell and C_Spell.GetSpellName then
        local ok, n = pcall(C_Spell.GetSpellName, id)
        if ok then name = Plain(n, "string") end
    end
    if not name and GetSpellInfo then
        local ok, n = pcall(GetSpellInfo, id)
        if ok then name = Plain(n, "string") end
    end
    if name then nameCache[id] = name end
    return name
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() == true
end

-- true / false / nil (cannot tell): does the player know Demoralizing Roar. Only read out of combat; an unreadable book keeps what
-- we knew (a refused read must never forget a spell).
local function ReadKnown()
    if InCombat() then return end
    local FH = FS.FrameHelpers
    if FH and FH.ResolveSpell and FH.IsKnownSpellId then
        local id = FH.ResolveSpell(ROAR_NAME)
        local k
        if not id then k = false else k = FH.IsKnownSpellId(id, false) and true or false end
        if k == false and roar.known == true and roar.castAt then return end   -- we have cast it: it is known
        roar.known = k
    end
    if State and State.Known then
        local t = State.Known("thorns")
        if t ~= nil then thornsKnown = t end
    end
end

-- seconds left (0 when down) and whether it is a ledger estimate
function Bear.RoarLeft(now)
    local r = roar
    if r.expires == nil then return 0, true end
    local left = r.expires - now
    if left <= 0 then return 0, true end
    if left > C.ROAR_S then left = C.ROAR_S end
    return left, r.est
end

function Bear.RoarCastAt() return roar.castAt end
function Bear.RoarKnown() return roar.known end
function Bear.ThornsKnown() return thornsKnown end

local function OnCast(spellID)
    local name = SpellNameOf(spellID)
    if name ~= ROAR_NAME then return end
    local now = GetTime()
    roar.castAt, roar.expires, roar.est, roar.known = now, now + C.ROAR_S, true, true
    roar.nextRead = now + C.READ_AFTER
end

-- Out of combat and readable: the target's own debuff (a plain expiry is exact), or readably absent
local function ReadAura(now)
    roar.nextRead = now + C.READ_EVERY
    if roar.expires == nil or roar.expires <= now then return end
    if InCombat() or not (FS.AurasReadable and FS.AurasReadable()) then return end
    if type(UnitExists) ~= "function" or type(UnitCanAttack) ~= "function" then return end
    local ex, atk = UnitExists("target"), UnitCanAttack("player", "target")
    if IsSecret(ex) or IsSecret(atk) or not ex or not atk then return end
    local byName = C_UnitAuras and C_UnitAuras.GetAuraDataBySpellName
    if type(byName) ~= "function" then return end
    local ok, aura = pcall(byName, "target", ROAR_NAME, "HARMFUL")
    if not ok or IsSecret(aura) then return end
    if type(aura) == "table" then
        local e = Plain(aura.expirationTime, "number")
        if e and e > 0 then roar.expires, roar.est = e, false end
    elseif aura == nil and roar.castAt and now - roar.castAt > C.ABSENT_GRACE then
        roar.expires = nil
    end
end

local EVENTS = { "PLAYER_ENTERING_WORLD", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_REGEN_ENABLED",
    "PLAYER_TARGET_CHANGED" }

function Bear.Start()
    if started then return end
    started = true
    local frame = CreateFrame("Frame")
    frame:SetScript("OnEvent", function(_, event, _, _, spellID)
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            local ok, err = pcall(OnCast, spellID)
            if not ok then LogOnce("cast", err) end
        elseif event == "PLAYER_TARGET_CHANGED" then
            roar.nextRead = 0
        else
            if event == "PLAYER_REGEN_ENABLED" then roar.nextRead = 0 end
            local ok, err = pcall(ReadKnown)
            if not ok then LogOnce("known", err) end
        end
    end)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then
        FH.RegisterEvent(frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        for _, e in ipairs(EVENTS) do FH.RegisterEvent(frame, e) end
    else
        pcall(frame.RegisterUnitEvent, frame, "UNIT_SPELLCAST_SUCCEEDED", "player")
        for _, e in ipairs(EVENTS) do pcall(frame.RegisterEvent, frame, e) end
    end
    pcall(ReadKnown)
end

-------------------------------------------------------------------------------
-- Regions
-------------------------------------------------------------------------------

local SPX = 1.25
local seats = {}
local P = {}
local roarRegs, thRegs = {}, {}
local root, shk, headF, ringF, txtF

local function S(v) return Gunsight.ui(v * SPX) end
local function Round(v) return floor(v + 0.5) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end

local function Seat(fn)
    seats[#seats + 1] = fn
    fn()
end

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

local function On(t) if t.fsOn ~= true then t.fsOn = true; t:Show() end end
local function Off(t) if t.fsOn ~= false then t.fsOn = false; t:Hide() end end

local function Tint(t, c, a)
    local r, g, b = c[1], c[2], c[3]
    if t.fsR == r and t.fsG == g and t.fsB == b and t.fsA == a then return end
    t.fsR, t.fsG, t.fsB, t.fsA = r, g, b, a
    t:SetVertexColor(r, g, b, a)
end

local function Place(t, x, y)
    if t.fsX == x and t.fsY == y then return end
    t.fsX, t.fsY = x, y
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", t.fsHost, "TOPLEFT", S(x), -S(y))
end

-- an atlas sprite region on `host`
local function NewSprite(group, host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost = host
    t:Hide()
    t.fsOn = false
    SetTex(t, MEDIA .. Art.FILE .. ".tga")
    Seat(function() t.fsName, t.fsX = nil, nil end)
    group[#group + 1] = t
    return t
end

-- a flat one sprite px region on `host`
local function NewDot(group, host, layer, sub)
    local t = host:CreateTexture(nil, layer, nil, sub or 0)
    t.fsHost = host
    t:SetTexture(FLAT)
    t:Hide()
    t.fsOn = false
    Seat(function() t:SetSize(S(1), S(1)); t.fsX = nil end)
    group[#group + 1] = t
    return t
end

-- show sprite `name` with its baked canvas origin moved by (dx, dy)
local function Sprite(t, name, dx, dy, c, a)
    local s = SPR[name]
    if not s or a <= 0 then Off(t); return end
    if t.fsName ~= name then
        t.fsName = name
        local aw, ah = Art.AW, Art.AH
        t:SetTexCoord(s[1] / aw, (s[1] + s[3]) / aw, s[2] / ah, (s[2] + s[4]) / ah)
        t:SetSize(S(s[3]), S(s[4]))
        t.fsX = nil
    end
    On(t)
    Place(t, s[5] + dx, s[6] + dy)
    Tint(t, c, a)
end

local function Dot(t, x, y, c, a)
    if a <= 0 then Off(t); return end
    On(t)
    Place(t, x, y)
    Tint(t, c, a)
end

local function NewText(group, px, name)
    local fs = txtF:CreateFontString(nil, "OVERLAY")
    fs.fsPx, fs.fsCol, fs.fsA = px, K.num, 1
    fs:Hide()
    fs.fsOn = false
    Seat(function()
        local T = FS.Theme
        if T and T.ApplyMono then T.ApplyMono(fs, S(fs.fsPx), { fs.fsCol[1], fs.fsCol[2], fs.fsCol[3], fs.fsA }) end
        -- a dark edge, as the page draws one round every glyph: over the cloud and over the world both stay readable
        if fs.SetShadowColor then fs:SetShadowColor(K.shadow[1], K.shadow[2], K.shadow[3], 1) end
        if fs.SetShadowOffset then fs:SetShadowOffset(S(1), -S(1)) end
        fs.fsX = nil
    end)
    group[#group + 1] = fs
    return fs
end

local function TextAt(fs, x, y)
    if fs.fsX == x and fs.fsY == y then return end
    fs.fsX, fs.fsY = x, y
    fs:ClearAllPoints()
    fs:SetPoint("CENTER", root, "TOPLEFT", S(x), -S(y))
end

local function TextColor(fs, c, a)
    if fs.fsCol == c and fs.fsA == a then return end
    fs.fsCol, fs.fsA = c, a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

local function TextWord(fs, word)
    if fs.fsWord == word then return end
    fs.fsWord = word
    fs:SetText(word)
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local EYE_X = { 23, 40 }
local EYE_Y = 13

local function Build(parent)
    root = CreateFrame("Frame", "ForeverSTUwaveDruidBear", parent)
    root:SetAllPoints(parent)
    local lvl = parent:GetFrameLevel()
    pcall(root.SetFrameLevel, root, lvl + 3)

    -- the cloud, its flash and its bolts: BACKGROUND of the root, never shaken
    P.aura = NewSprite(roarRegs, root, "BACKGROUND", 0)
    P.light = NewSprite(roarRegs, root, "BACKGROUND", 1)
    P.bolt = NewSprite(roarRegs, root, "BACKGROUND", 2)

    -- the shaker: the halo, the arcs, the head and the shock rings
    shk = CreateFrame("Frame", nil, root)
    pcall(shk.SetFrameLevel, shk, lvl + 4)
    Seat(function()
        shk:ClearAllPoints()
        shk:SetPoint("TOPLEFT", root, "TOPLEFT", S(shk.fsDX or 0), -S(shk.fsDY or 0))
        shk:SetSize(S(C.SW), S(C.SH))
    end)
    P.halo = NewSprite(roarRegs, shk, "ARTWORK", 0)
    P.arcA, P.arcB, P.arcC = {}, {}, {}
    for p = 0, 9 do
        P.arcA[p] = NewSprite(roarRegs, shk, "ARTWORK", 1)
        P.arcB[p] = NewSprite(roarRegs, shk, "ARTWORK", 2)
        P.arcC[p] = NewSprite(roarRegs, shk, "ARTWORK", 3)
    end

    headF = CreateFrame("Frame", nil, shk)
    pcall(headF.SetFrameLevel, headF, lvl + 5)
    Seat(function()
        headF:ClearAllPoints()
        headF:SetPoint("TOPLEFT", shk, "TOPLEFT", S(headF.fsX or C.HX), -S(headF.fsY or 3))
        headF:SetSize(S(C.HEAD), S(C.HEAD))
    end)
    P.head = NewSprite(roarRegs, headF, "ARTWORK", 0)
    -- the eyes: per eye two side glows, the centre, and four streaks a side, flat px riding on the head frame
    P.eye = { { side = {}, streak = {} }, { side = {}, streak = {} } }
    for e = 1, 2 do
        local E = P.eye[e]
        E.side[1] = NewDot(roarRegs, headF, "OVERLAY", 0)
        E.side[2] = NewDot(roarRegs, headF, "OVERLAY", 0)
        E.centre = NewDot(roarRegs, headF, "OVERLAY", 1)
        for i = 1, 4 do
            E.streak[i] = { NewDot(roarRegs, headF, "OVERLAY", 2), NewDot(roarRegs, headF, "OVERLAY", 2) }
        end
    end

    ringF = CreateFrame("Frame", nil, shk)
    pcall(ringF.SetFrameLevel, ringF, lvl + 6)
    ringF:SetAllPoints(shk)
    P.ring = {}
    for s = 1, 3 do P.ring[s] = NewSprite(roarRegs, ringF, "ARTWORK", 0) end

    -- the Thorns corner (no shake) and the labels
    P.thSeg = {}
    for i = 0, C.TH_SEGMENTS - 1 do P.thSeg[i + 1] = NewSprite(thRegs, root, "ARTWORK", 0) end
    P.thGhost = NewSprite(thRegs, root, "ARTWORK", 1)

    txtF = CreateFrame("Frame", nil, root)
    pcall(txtF.SetFrameLevel, txtF, lvl + 8)
    txtF:SetAllPoints(root)
    P.num = NewText(roarRegs, C.NUM_PX)
    P.word = NewText(roarRegs, C.WORD_PX)
    P.thText = NewText(thRegs, C.TH_PX)
    P.thWord = NewText(thRegs, C.TH_WORD_PX)
    return root
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

local roarOn, thOn = false, false
local lastKnownRead = 0

local function HideGroup(list)
    for i = 1, #list do Off(list[i]) end
end

-- how much of arc p (0 goes first) is left: 1 full, 0 gone; ten arcs of 3 s
local function Frac(left, p)
    local hi, lo = C.ROAR_S - C.PIECE_S * p, C.ROAR_S - C.PIECE_S - C.PIECE_S * p
    if left >= hi then return 1 elseif left <= lo then return 0 end
    return (left - lo) / C.PIECE_S
end

local function PaintEyes(hx, hy, ca, low, red, now, down, combat)
    for e = 1, 2 do
        local E, ex = P.eye[e], EYE_X[e]
        if down then
            HideGroup(E.side)
            for i = 1, 4 do Off(E.streak[i][1]); Off(E.streak[i][2]) end
            if combat then
                local pu = 0.5 + 0.5 * sin(now * 6)
                Dot(E.centre, ex, EYE_Y, K.amber, Stepped(0.4 + 0.5 * pu))
            else
                Off(E.centre)
            end
        else
            local fl = (not red and ca < C.SHAKE_S) and 1 - ca / C.SHAKE_S or 0
            local pu = red and 0.5 or (0.5 + 0.5 * sin(now * 3))
            local ec = low and K.amber or K.eye
            -- the side glows are dithered: they draw on the even pixels of the page's canvas only
            local drawn = (hx + ex - 1 + hy + EYE_Y) % 2 == 0
            local sa = Stepped(0.35 + 0.3 * pu)
            if drawn then
                Dot(E.side[1], ex - 1, EYE_Y, ec, sa)
                Dot(E.side[2], ex + 1, EYE_Y, ec, sa)
            else
                Off(E.side[1]); Off(E.side[2])
            end
            Dot(E.centre, ex, EYE_Y, fl > 0.3 and K.white or ec, Stepped(0.7 + 0.3 * pu))
            for i = 1, 4 do
                if fl > 0 then
                    local a = Stepped(fl * (1 - i / 5))
                    Dot(E.streak[i][1], ex - i, EYE_Y, K.white, a)
                    Dot(E.streak[i][2], ex + i, EYE_Y, K.white, a)
                else
                    Off(E.streak[i][1]); Off(E.streak[i][2])
                end
            end
        end
    end
end

local function PaintRoar(now, combat, red)
    local left, est = Bear.RoarLeft(now)
    local down = left <= 0
    local low = left > 0 and left <= C.WARN_S
    local castAt = roar.castAt
    local ca = castAt and (now - castAt) or 99
    if ca < 0 then ca = 99 end
    roarOn = true

    -- the cloud: still when the roar is down, gone out of combat
    local flash, bolt = 0, nil
    if not down and not red then
        if ca < C.FLASH_S then
            flash = ca < 0.08 and 1 or max(0, 1 - (ca - 0.08) / 0.5)
            bolt = 35
        else
            local ph = now % C.FLICKER_EVERY
            if ph < C.FLICKER_S then
                flash = 0.5 * (1 - ph / C.FLICKER_S) * (sin(ph * 80) > 0 and 1 or 0.4)
                bolt = 121
            end
        end
    end
    if down and not combat then
        Off(P.aura); Off(P.light); Off(P.bolt)
    else
        local f = 0
        if not down and not red then
            f = floor((now % LOOP) / LOOP * FRAMES)
            if f >= FRAMES then f = FRAMES - 1 end
        end
        Sprite(P.aura, NAME.aura[f], 0, 0, K.pure, 1)
        if flash > 0 and bolt then
            Sprite(P.light, NAME.light[bolt][f], 0, 0, K.pure, Stepped(flash))
            if flash > 0.15 then Sprite(P.bolt, NAME.bolt[bolt], 0, 0, K.pure, Stepped(flash)) else Off(P.bolt) end
        else
            Off(P.light); Off(P.bolt)
        end
    end

    -- the shake: the roar jolts the module for 0.4 s
    local sx, sy = 0, 0
    if not red and ca < C.SHAKE_S then
        local d = 1 - ca / C.SHAKE_S
        sx, sy = Round(sin(ca * 90) * 2.2 * d), Round(cos(ca * 70) * 1.6 * d)
    end
    if shk.fsDX ~= sx or shk.fsDY ~= sy then
        shk.fsDX, shk.fsDY = sx, sy
        shk:ClearAllPoints()
        shk:SetPoint("TOPLEFT", root, "TOPLEFT", S(sx), -S(sy))
    end

    -- the halo behind the head
    if down then
        Off(P.halo)
    else
        local br = red and 0.6 or (0.6 + 0.25 * sin(now * 2.2))
        local a = 0.2 * br + ((not red and ca < 0.5) and (1 - ca / 0.5) * 0.4 or 0)
        Sprite(P.halo, "halo", 0, 0, low and K.amber or K.pink, Stepped(a))
    end

    -- the ten sound arcs
    for p = 0, 9 do
        local A, B, Cc = P.arcA[p], P.arcB[p], P.arcC[p]
        local lit = down and 0 or Frac(left, p)
        local ring = floor((9 - p) / 2)
        if lit <= 0 or ca < 0.2 + ring * 0.08 then
            Off(A); Off(B); Off(Cc)
        else
            local wave = red and 0 or (0.5 + 0.5 * sin(now * 7 - ring * 1.2))
            local fl = (not red and lit < 0.35) and (sin(now * 30) > 0 and 1 or 0.4) or 1
            local c1 = low and K.amber or K.roar
            local c2 = low and K.amberh or K.roarh
            local names = NAME.arc[p]
            Sprite(A, names.a, 0, 0, c1, fl)
            Sprite(B, names.b, 0, 0, wave > 0.6 and c2 or c1, fl)
            Sprite(Cc, names.c, 0, 0, K.pure, fl)
        end
    end

    -- the head: the jaw frame, the lunge and the bob
    local fr, lift = "rest", 0
    if down then
        fr = combat and "dim_combat" or "dim_ooc"
    else
        if ca < 0.05 then fr = "mid"
        elseif ca < 0.9 then fr = "open"
        elseif ca < C.ROAR_LEN then fr = "mid" end
        if fr == "rest" and not red then
            local b = sin(now * 2.2)
            fr = b > 0.75 and "k11" or b > 0.25 and "k12" or b > -0.25 and "k13" or "rest"
        end
        if red then lift = 0
        elseif ca < 0.08 then lift = -3 * ca / 0.08
        elseif ca < 0.5 then lift = -3 * (1 - (ca - 0.08) / 0.42)
        else lift = sin(now * 2.2) > 0.3 and -1 or 0 end
    end
    local hx, hy = C.HX, Round(C.HCY - 31 + lift)
    if headF.fsX ~= hx or headF.fsY ~= hy then
        headF.fsX, headF.fsY = hx, hy
        headF:ClearAllPoints()
        headF:SetPoint("TOPLEFT", shk, "TOPLEFT", S(hx), -S(hy))
    end
    Sprite(P.head, NAME.head[fr], 0, 0, K.pure, 1)
    PaintEyes(hx, hy, ca, low, red, now, down, combat)

    -- the shock rings of the roar
    for s = 0, 2 do
        local t = P.ring[s + 1]
        local kk = (ca - s * 0.1) / C.RINGS_S
        if red or down or kk <= 0 or kk >= 1 then
            Off(t)
        else
            local i = floor(kk * STEPS)
            if i >= STEPS then i = STEPS - 1 end
            Sprite(t, NAME.ring[i], 0, 0, s == 0 and K.white or K.roar, 1)
        end
    end

    -- the labels: the seconds when it runs, ROAR when it is down in combat
    if down then
        Off(P.num)
        if combat then
            On(P.word)
            TextWord(P.word, "ROAR")
            TextColor(P.word, K.amber, Stepped(red and 1 or (0.55 + 0.45 * sin(now * 6))))
            TextAt(P.word, C.WORD_X, C.WORD_Y)
        else
            Off(P.word)
        end
    else
        Off(P.word)
        On(P.num)
        local n = ceil(left)
        if n > C.ROAR_S + 1 then n = C.ROAR_S + 1 end
        TextWord(P.num, NUM[est and true or false][n])
        TextColor(P.num, low and K.amber or K.num, 1)
        TextAt(P.num, C.NUM_X, C.NUM_Y)
    end
end

local function HideRoar()
    if not roarOn then return end
    roarOn = false
    HideGroup(roarRegs)
end

local function PaintThorns(now, combat, red)
    local mode, left, est = State.Thorns(now)
    if mode == "up" and type(left) == "number" and left > 0 then
        thOn = true
        local len = State.TUNING and State.TUNING.THORNS_SECONDS or 600
        local low = left < C.TH_LOW
        local lit = ceil(left / len * C.TH_SEGMENTS)
        if lit > C.TH_SEGMENTS then lit = C.TH_SEGMENTS elseif lit < 1 then lit = 1 end
        local pulse = (low and not red) and Stepped(0.55 + 0.45 * abs(sin(now * pi / 0.7))) or 1
        for i = 0, C.TH_SEGMENTS - 1 do
            local on = i < lit
            Sprite(P.thSeg[i + 1], on and (low and NAME.thAmber[i] or NAME.thLive[i]) or NAME.thDry[i], 0, 0, K.pure, on and pulse or 1)
        end
        Off(P.thGhost)
        local n = low and ceil(left) or ceil(left / 60)
        if n > 99 then n = 99 elseif n < 0 then n = 0 end
        Off(P.thWord)
        On(P.thText)
        TextWord(P.thText, TH[est and true or false][low and "S" or "M"][n])
        TextColor(P.thText, low and K.amber or K.thText, pulse)
        TextAt(P.thText, C.TH_LABEL_X, C.TH_LABEL_Y)
    elseif mode == "gone" and not combat and thornsKnown == true then
        thOn = true
        for i = 1, C.TH_SEGMENTS do Off(P.thSeg[i]) end
        local a = red and 0.7 or Stepped(0.55 + 0.35 * sin(now * 3))
        Sprite(P.thGhost, "th_ghost", 0, 0, K.pure, a)
        Off(P.thText)
        On(P.thWord)
        TextWord(P.thWord, "THORNS")
        TextColor(P.thWord, K.amber, a)
        TextAt(P.thWord, C.TH_LABEL_X, C.TH_LABEL_Y)
    elseif thOn then
        thOn = false
        HideGroup(thRegs)
    end
end

local function Paint(now, data)
    if not root then return end
    local red = data and data.reduced == true
    local combat = InCombat()
    -- the spellbook is read again about every 30 s while shown, out of combat, besides its events
    if now - lastKnownRead >= 30 then
        lastKnownRead = now
        ReadKnown()
    end
    if roar.known ~= false then
        if now >= roar.nextRead then ReadAura(now) end
        PaintRoar(now, combat, red)
    else
        HideRoar()
    end
    PaintThorns(now, combat, red)
end
Bear.Paint = Paint

-------------------------------------------------------------------------------
-- The registered look
-------------------------------------------------------------------------------

local spec = {}

function spec.build(parent)
    if root then return root end
    Bear.Start()
    local ok, err = pcall(Build, parent)
    if not ok then
        LogOnce("build", err)
        return nil
    end
    Bear.frame, Bear.parts = root, P
    return root
end

function spec.seat(_, _, spx)
    if type(spx) == "number" and spx > 0 then SPX = spx end
    for i = 1, #seats do
        local ok, err = pcall(seats[i])
        if not ok then LogOnce("seat", err) end
    end
end

function spec.paint(now, data)
    local ok, err = pcall(Paint, now, data)
    if not ok then LogOnce("paint", err) end
end

function spec.show()
    if not root then return end
    root:Show()
    lastKnownRead = GetTime()
    pcall(ReadKnown)
    roar.nextRead = 0
end

function spec.hide()
    if not root then return end
    root:Hide()
end

Druid.RegisterForm("bear", spec)
