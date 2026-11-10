-- Forever STUwave: Gunsight Class Module for the Priest: the shield, and the right side (the medallions or Prayer of Mending)
--
-- The approved design is the design mockup "Priest shield and mending" (2026-11-07), palette BIFROST FROST, rune C, no halo, and
-- for the right side the mockup "Priest right slot" (2026-11-10), variant A. Two watchers side by side on the mockup's 150 x 86
-- sprite px canvas:
--   * THE SHIELD (left): a round Viking shield (2 px rim, iron band with 8 rivets, planks in ice cyan / teal quarters, a
--     midnight blue boss carrying the protection rune). It watches the friendly target, else the player (an enemy never carries
--     our shield). The absorb left is LIGHT filling the shield from the bottom: a vertical StatusBar the engine fills from the
--     secret UnitGetTotalAbsorbs, its max the absorb caught right after the player's own cast (PriestShields' mark). While it
--     holds light: an ice rim, the rune burning white, a frost aura and 8 rays breathing, a glint sweep and rising motes; a hit
--     flashes it white and shakes it 1 px. The RIM says if you may shield again: violet and draining while Weakened Soul runs
--     (15 s), dim teal while the 4 s cooldown runs, ice cyan when clear. Empty and clear: a still GHOST out of combat (the off
--     state mockup, 2026-11-10, option C: a faint wash the ground shows through, thin rings for the band and the boss, rivet
--     dots, a solid thin rim, the rune in ice cyan), an amber dashed pulse with a glow in combat ("shield them"). Not learned:
--     a dotted rim and L6. The label under it is the absorb left (AbbreviateNumbers) or the Weakened Soul time in violet.
--   * THE RIGHT SIDE, one of three looks, chosen by the setting "Right side shows" (PriestRight.lua: Auto, Spirit Tap + Inner
--     Fire, Prayer of Mending, Off; a change waits for the end of a fight):
--       - MEDALLIONS (the default while leveling): two round medallions, the shield's art language, 35 px wide rings on one
--         centre pixel. SPIRIT TAP above (a plain skull, spirit green), INNER FIRE below (a flame shield, gold), the engine's
--         own number to the right of each (Spirit Tap's time left, Inner Fire's charges). See "THE MEDALLIONS" below.
--       - PRAYER OF MENDING: 5 beads on an arc round a 2x heart (lit = heals left), a 5 seat party strip (seat 1 is the
--         player, then party1-4; class colour strip, a "you" tick), the holder's seat framed gold with a small heart, a spark
--         when a plain read sees it jump, the 30 s jump timer bar and its label, the heart shaded from the top while the 10 s
--         cooldown runs, L40 before it is learned. The seats also carry the player's OTHER shields: frost light filling the
--         seat from the bottom (that member's absorb, engine drawn) and a violet line draining along its top (their Weakened
--         Soul from our cast).
--       - OFF: nothing on the right.
--
-- HOW "THERE IS LIGHT IN IT" IS DRAWN WITHOUT READING A SECRET. The absorb can never be compared, so everything that only shows
-- while the shield holds light (the ice rim, the white rune, aura, rays, glint, motes, flash, the number) sits in one plain frame
-- whose ALPHA is the secret absorb (SetAlpha takes a secret; 0 hides it, any absorb shows it fully). That frame is layered over
-- the empty looks (ghost or dashed rim, state rune) and under the cooldown and Weakened Soul rims, so the engine picks the right rim and
-- rune. The plain "up" guess (PriestShields: aura out of combat, the cast ledger in combat) only chooses the label and whether
-- the empty look may nudge.
--
-- THE MEDALLIONS (the same idea for a buff: the engine knows, Lua does not). Two layers on each medallion:
--   * BASE (ours, plain regions, always drawn, writable in combat): the calm look (the ghost wash and the dim glyph), or for Inner
--     Fire the amber nudge (the dark body, amber dashes, the amber glyph and halo, breathing) while the reminder is on, or the
--     locked look (a dotted rim and a dotted glyph: Spirit Tap not talented, Inner Fire not learned, with L12 beside it).
--   * COVER (the lit look, children of an ENGINE aura slot): the dark body, the lit rim, the glyph in full colour, a breathing
--     halo (Spirit Tap also a breathing glow ring), and the engine's number. The slot comes from one AuraContainer per medallion
--     (template CustomAuraContainerTemplate, unit "player", an AddAuraSlot on HELPFUL with candidateFilters.includeSpellIDs: the
--     spell's rank ids, PriestRight.Ids), built the way Modules/ActionBars/BuffTab.lua builds its shield slot: the engine shows
--     the slot, and so the cover, only while the aura is on the player, and draws the number (SetDurationText for Spirit Tap,
--     SetApplicationCount for Inner Fire) from the secret value, so no Lua ever reads it, compares it or does arithmetic on it.
--     The slot sits on a plain anchor frame of ours; every cover region is anchored to that anchor, written once (out of
--     combat) and left alone, so the lit look is static in combat (no kill flash, no per hit change; the breathing is a looping
--     AnimationGroup). Spirit Tap's "pull now" cue is a plain amber glow ring above it, from the kill ledger (PriestRight:
--     PARTY_KILL with the player as the attacker, and a plain read that Spirit Tap is up), out of combat only.
--   The engine route runs only on PROOF, exactly as BuffTab's does: built, enabled and shown out of combat only (one counted
--   attempt per out of combat pass, 3 in a row give it up, one uncounted retry 10 s after a failure from the 1 s tick), the slot
--   read back against the anchor BEFORE anything re-seats it (a slot that is off the anchor is put back and is not live until
--   the next pass; one that cannot be read, or was built in combat, is unproven; an idle slot, with no aura to locate, keeps
--   the proof it has), the container hidden (alpha 0) until it is live, a rebuild only when an id never seen before appears (3
--   a session, then a line says to /reload), and the state line in ForeverSTUwaveDB.gunsightPriestRight.line (on disk after a
--   /reload). While a medallion is not live the BASE says only what a plain read says, out of combat: the lit look drawn by
--   plain regions without a number when Spirit Tap or Inner Fire is up, the nudge when Inner Fire is readably absent, calm
--   otherwise; in combat it is calm, never a stale claim. UNVERIFIED in game: the slot rendering and its placement, the layering,
--   whether the engine draws the Inner Fire count and the Spirit Tap time at all, and the rank ids.
--
-- WHAT THE MOCKUP HAS THAT THIS BUILD DOES NOT (the client cannot do it, or not without per frame geometry):
--   * the bright top rows that ride the light's edge (the fill level is secret; the lit texture carries them at full only);
--   * the Weakened Soul rim drains from the other end: a Cooldown swipe keeps the arc from where the elapsed time ends to 12
--     o'clock, the mockup keeps it from 12 o'clock on; and its bright head pixel is gone;
--   * break shards only for a break a plain read sees (out of combat); in combat a break is not knowable;
--   * the seat light has no bright top rows either (a flat frost fill);
--   * the label is the house mono font, not the mockup's 3 x 5 pixel font ("~6s", not "~6S");
--   * the medallions: no white flash of the glyph on a kill (the cover is static in combat), no glow ring in the Inner Fire
--     nudge (the cover could not hide it again when the buff is up), and none of the optional out of combat extras (the drain
--     ring, the low Inner Fire look): they need a swipe texture per ring or a texture per segment and cannot show in combat.
--
-- DATA. The shield comes from FS.PriestShields (PriestShields.lua); its ledger listens from Start() on and never stops. The right
-- side comes from FS.PriestRight (PriestRight.lua: the setting, the group, the spells, the kill ledger). This file reads no aura
-- and compares no secret: secrets go straight to SetMinMaxValues / SetValue / SetAlpha / AbbreviateNumbers.
--
-- VISIBILITY. A class module: the host hides with no target and onHide / onShow fire on that edge (GunsightAreas.lua). onHide
-- stops the OnUpdate and the subscriptions; onShow subscribes, refreshes and repaints. Plain frames only.
--
-- TICKER. One OnUpdate at most every C.TICK s while shown and something moves (light, a clock, a nudge, a hit, a jump, the cue);
-- it stops when nothing does. The tick allocates nothing: positions are numbers, texcoords and labels are written on change.
-- A 1 s C_Timer chain (alive while the module is shown) does the engine's out of combat proof and retry.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point) then return end
if not (Areas and Areas.RegisterModule) then return end

FS.GunsightPriest = FS.GunsightPriest or {}
local Priest = FS.GunsightPriest

local ui, Point = Gunsight.ui, Gunsight.Point
local floor, ceil, sin, cos, pi = math.floor, math.ceil, math.sin, math.cos, math.pi
local IsSecret = FS.IsSecret or function() return false end

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    SPX = 1.25,                        -- image px per sprite px
    SW = 150, SH = 86,                 -- the mockup canvas in sprite px
    LABEL_Y = 74,
    DROP = 5,                          -- image px the module sits below the area's top
    TICK = 1 / 30,
    SHIELD = { cx = 38, cy = 36, r = 27 },
    BOX = 64, CENTER = 32,             -- the shield art's sprite box and the shield centre in it (generate_priest_shield.py)
    RAYS_BOX = 80, RAYS_CENTER = 40,
    LIT = { x = -27, y = -26, w = 55, h = 53 },   -- the lit interior the StatusBar covers, sprite px from the shield centre
    PM = { cx = 114, cy = 27, r = 24, seatY = 47, seatX = { 88, 101, 114, 127, 140 } },
    MED = { cx = 96, nx = 132, BOX = 40, CENTER = 20 },   -- the medallions' centre pixel column, the number's centre, the art box
    NUM_SIZE = 18, NUM_LIFT = 0.035,   -- the engine's number: image px (digits 10 sprite px tall), and Mononoki's digit centre in em
    ENGINE = { TEMPLATE = "CustomAuraContainerTemplate", LEVEL = 6, UNREADABLE_TICKS = 5, REBUILDS = 3, RETRY = 10, LIMIT = 3,
        EVERY = 1 },
    MED_BREATH = 1.6,
    BREATH = 2.6, NUDGE = 1.4, HEART_PULSE = 1.0,
    GLINT_EVERY = 3.2, GLINT_LEN = 0.6, GLINT_FRAMES = 8,
    MOTE_X = { -16, -6, 4, 13, 20 }, MOTE_SPEED = 0.35,
    FLASH = 0.08, SHAKE = 0.12, BREAK = 0.7, JUMP = 0.45,
    LABEL_SIZE = 11,
    CAP = 325 / 1024,                  -- Mononoki Bold: the line box's middle sits CAP * size above the baseline (as GunsightWarrior)
    TEXT_MAX_S = 99,
    ABSORB_EVERY = 0.5,                -- s between absorb re-reads while ticking (the pings are the main path)
    COLORS = {
        violet = Hex("#c04cff"), violetLabel = Hex("#e09cff"), amber = Hex("#ffb648"), muted = Hex("#9d93c4"),
        rimClear = Hex("#5fd4e8"), cdOuter = Hex("#2a5a6a"), runeLine = Hex("#061a2c"), white = Hex("#ffffff"),
        label = Hex("#c8faff"), shard = Hex("#a0f4ff"), aura = Hex("#a0f4ff"), litBody = Hex("#9ff0ff"),
        gold = Hex("#ffd36a"), goldLabel = Hex("#ffe9a8"), seatEdge = Hex("#3a2c5c"), seatBg = Hex("#120a22"),
        pink = Hex("#ff5d8f"), sparkCore = Hex("#ffc2d6"), you = Hex("#f3fbff"), barBg = Hex("#1c1230"),
        chainOut = Hex("#8a6a30"), chainOff = Hex("#2a1a44"),
        spGlow = Hex("#2dff8a"), spRim = Hex("#3ee88a"), spRimIn = Hex("#8affc0"), spNum = Hex("#c8ffe0"),
        ifGlow = Hex("#ffd23f"), ifRim = Hex("#ffd23f"), ifRimIn = Hex("#ffe88a"), ifNum = Hex("#fff0b0"),
    },
    SEAT_CLASS = { Hex("#f3fbff"), Hex("#c79c6e"), Hex("#ff7d0a"), Hex("#0070de"), Hex("#69ccf0") },   -- mockup fallbacks
}
C.W = C.SW * C.SPX
C.H = C.SH * C.SPX
Priest.C = C
local K = C.COLORS

-- priest_shield.tga cells (generate_priest_shield.py SHIELD_CELLS) and priest_mending.tga cells (MENDING_CELLS)
local CELL = { dark = 0, rimClear = 1, rimCd = 2, rimWsDark = 3, rimDash = 4, rune = 5, runeLine = 6, flash = 7, aura = 8,
    halo = 9, ghost = 10, ghostRim = 11 }
local MCELL = { beadLit = 0, beadOff = 1, beadDash = 2, heartSmall = 3, heartLit = 4, heartOff = 5, heartAmber = 6,
    heartLocked = 7, heartGlow = 8 }
-- priest_medallion.tga cells (generate_priest_shield.py MEDALLION_CELLS): 6 across, 80 texels, the art box 40 sprite px
local MEDCELL = { ghost = 0, body = 1, rimOuter = 2, rimInner = 3, dash = 4, glow = 5, skullLit = 6, skullDim = 7, skullDots = 8,
    skullHalo = 9, shieldLit = 10, shieldAmber = 11, shieldDim = 12, shieldDots = 13, shieldHalo = 14 }
Priest.CELL, Priest.MCELL, Priest.MEDCELL = CELL, MCELL, MEDCELL
local SCALE = 2

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local HEART = { ".XX.XX.", "XXXXXXX", "XXXXXXX", ".XXXXX.", "..XXX..", "...X..." }

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightpriest_" .. key, "|cffff4488Forever STUwave|r: gunsight priest module: " .. tostring(msg))
    end
end

local Data, Right
local mod
local seats = {}
local OX, OY = 0, 0
local subscribed, ticking, acc, absorbAcc = false, false, 0, 0
local P = {}                       -- every part, built once
local hitAt, breakAt, castAt = nil, nil, nil
local abbreviateOff = false

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

local function Size(t, w, h)
    if t.fsW == w and t.fsH == h then return end
    t.fsW, t.fsH = w, h
    t:SetSize(S(w), S(h))
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

-- texcoords of cell i of an atlas: cols across, `cell` texels square, the art w x h sprite px from the cell's top left
local function CellRect(i, atlasW, atlasH, cols, cell, w, h)
    local l, top = (i % cols) * cell / atlasW, floor(i / cols) * cell / atlasH
    return l, l + w * SCALE / atlasW, top, top + h * SCALE / atlasH
end
local function Cell(t, i, atlasW, atlasH, cols, cell, w, h)
    if t.fsCell == i then return end
    t.fsCell = i
    t:SetTexCoord(CellRect(i, atlasW, atlasH, cols, cell, w, h))
end
local function ShieldCell(t, i) Cell(t, i, 512, 512, 4, 128, C.BOX, C.BOX) end
local function MendCell(t, i, w, h) Cell(t, i, 256, 256, 4, 64, w, h) end
local function MedCell(t, i) Cell(t, i, 512, 256, 6, 80, C.MED.BOX, C.MED.BOX) end

-- The colour of a text region lives on the region (`cur`), because Theme.ApplyMono resets it at every rescale.
local function TextColor(fs, c, a)
    local cur = fs.cur
    if cur[1] == c[1] and cur[2] == c[2] and cur[3] == c[3] and cur[4] == a then return end
    cur[1], cur[2], cur[3], cur[4] = c[1], c[2], c[3], a
    fs:SetTextColor(c[1], c[2], c[3], a)
end

local function Text(parent, cx)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.cur = { 1, 1, 1, 1 }
    fs:SetJustifyH("CENTER")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(C.LABEL_SIZE), fs.cur)
        fs:ClearAllPoints()
        fs:SetPoint("CENTER", mod, "TOPLEFT", S(cx), -(S(C.LABEL_Y) - ui(C.CAP * C.LABEL_SIZE)))
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
Priest.TimeLabel = TimeLabel

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end
local function Stepped(v) return floor(v * 20 + 0.5) / 20 end      -- 20 steps: few alpha writes

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
end

local function Frame(parent, level)
    local f = CreateFrame("Frame", nil, parent)
    f:SetFrameLevel(mod:GetFrameLevel() + level)
    f:SetAllPoints(mod)
    f:EnableMouse(false)
    return f
end

-------------------------------------------------------------------------------
-- Build: the shield
-------------------------------------------------------------------------------

local function BuildShield()
    local sc = C.SHIELD
    local bx, by = sc.cx - C.CENTER, sc.cy - C.CENTER
    -- the shield frame moves 1 px on a hit (the shake); every shield part is placed against it
    local sf = CreateFrame("Frame", nil, mod)
    sf:SetFrameLevel(mod:GetFrameLevel() + 1)
    sf:SetSize(1, 1)
    sf:EnableMouse(false)
    Seat(function() sf:SetSize(ui(C.W), ui(C.H)); local x = sf.fsX; sf.fsX = nil; if x then P.ShakeTo(x) end end)
    P.sf = sf
    function P.ShakeTo(dx)
        if sf.fsX == dx then return end
        sf.fsX = dx
        sf:ClearAllPoints()
        sf:SetPoint("TOPLEFT", mod, "TOPLEFT", S(dx), 0)
    end
    P.ShakeTo(0)

    local function ShieldTex(parent, layer, sub, cell)
        local t = Tex(parent, layer, sub, MEDIA .. "priest_shield.tga", C.BOX, C.BOX, sf)
        ShieldCell(t, cell)
        Place(t, bx, by)
        return t
    end

    -- the empty looks
    P.halo = ShieldTex(sf, "BACKGROUND", 1, CELL.halo)
    Tint(P.halo, K.white, 1)
    P.body = ShieldTex(sf, "BACKGROUND", 2, CELL.dark)
    P.stateRim = ShieldTex(sf, "ARTWORK", 1, CELL.rimDash)
    P.stateLine = ShieldTex(sf, "ARTWORK", 2, CELL.runeLine)
    P.stateRune = ShieldTex(sf, "ARTWORK", 3, CELL.rune)

    -- the light: the engine fills it from the secret absorb
    local bar = CreateFrame("StatusBar", nil, sf)
    bar:SetFrameLevel(mod:GetFrameLevel() + 2)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. "priest_shield_lit.tga")
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar.fsBase = sf
    Seat(function() bar:SetSize(S(C.LIT.w), S(C.LIT.h)); Forget(bar); Place(bar, sc.cx + C.LIT.x, sc.cy + C.LIT.y) end)
    P.bar = bar

    -- everything that shows only while the shield holds light: its alpha is the secret absorb
    local gate = CreateFrame("Frame", nil, sf)
    gate:SetFrameLevel(mod:GetFrameLevel() + 3)
    gate:SetAllPoints(sf)
    gate:EnableMouse(false)
    P.gate = gate
    P.aura = ShieldTex(gate, "BACKGROUND", 0, CELL.aura)
    P.rays = Tex(gate, "BACKGROUND", 1, MEDIA .. "priest_shield_rays.tga", C.RAYS_BOX, C.RAYS_BOX, sf)
    P.rays:SetTexCoord(0, C.RAYS_BOX * SCALE / 256, 0, C.RAYS_BOX * SCALE / 256)
    Place(P.rays, sc.cx - C.RAYS_CENTER, sc.cy - C.RAYS_CENTER)
    P.clearRim = ShieldTex(gate, "ARTWORK", 1, CELL.rimClear)
    P.upLine = ShieldTex(gate, "ARTWORK", 2, CELL.runeLine)
    Tint(P.upLine, K.runeLine, 1)
    P.upRune = ShieldTex(gate, "ARTWORK", 3, CELL.rune)
    Tint(P.upRune, K.white, 1)

    -- the glint and the motes ride only the lit part: a frame from the light's top edge down, clipping its children
    local clip = CreateFrame("Frame", nil, gate)
    clip:SetFrameLevel(mod:GetFrameLevel() + 3)
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
        clip:SetAllPoints(sf)
        LogOnce("noclip", "the glint is not clipped to the light on this client")
    end
    P.clip = clip
    P.glint = Tex(clip, "ARTWORK", 4, MEDIA .. "priest_shield_glint.tga", C.BOX, C.BOX, sf)
    Place(P.glint, bx, by)
    P.motes = {}
    for i = 1, 5 do
        local m = { core = Tex(clip, "OVERLAY", 1, FLAT, 1, 1, sf), arms = {} }
        for a = 1, 4 do m.arms[a] = Tex(clip, "OVERLAY", 0, FLAT, 1, 1, sf) end
        P.motes[i] = m
    end
    P.flash = ShieldTex(gate, "OVERLAY", 2, CELL.flash)
    Tint(P.flash, K.white, 1)
    P.absorbLabel = Text(gate, sc.cx)

    -- the rims that win over the light: the cooldown and Weakened Soul
    local top = CreateFrame("Frame", nil, sf)
    top:SetFrameLevel(mod:GetFrameLevel() + 4)
    top:SetAllPoints(sf)
    top:EnableMouse(false)
    P.top = top
    P.cdRim = ShieldTex(top, "ARTWORK", 0, CELL.rimCd)
    P.wsDark = ShieldTex(top, "ARTWORK", 1, CELL.rimWsDark)
    local okCd, cd = pcall(CreateFrame, "Cooldown", nil, top)
    if okCd and cd and cd.SetSwipeTexture and cd.SetCooldown then
        cd:SetFrameLevel(mod:GetFrameLevel() + 5)
        cd:EnableMouse(false)
        pcall(cd.SetSwipeTexture, cd, MEDIA .. "priest_shield_ws.tga", 1, 1, 1, 1)
        if cd.SetSwipeColor then pcall(cd.SetSwipeColor, cd, 1, 1, 1, 1) end
        if cd.SetDrawEdge then pcall(cd.SetDrawEdge, cd, false) end
        if cd.SetDrawBling then pcall(cd.SetDrawBling, cd, false) end
        if cd.SetHideCountdownNumbers then pcall(cd.SetHideCountdownNumbers, cd, true) end
        if cd.SetReverse then pcall(cd.SetReverse, cd, false) end
        cd.fsBase = sf
        Seat(function() cd:SetSize(S(C.BOX), S(C.BOX)); Forget(cd); Place(cd, bx, by) end)
        P.wsCd = cd
    else
        -- no Cooldown widget: a static violet rim for the whole lock
        P.wsStatic = Tex(top, "ARTWORK", 2, MEDIA .. "priest_shield_ws.tga", C.BOX, C.BOX, sf)
        Place(P.wsStatic, bx, by)
        LogOnce("nocooldown", "the Weakened Soul rim does not drain on this client")
    end

    P.shards = {}
    for i = 1, 8 do
        local s = { big = Tex(sf, "OVERLAY", 3, FLAT, 2, 2, sf), dot = Tex(sf, "OVERLAY", 4, FLAT, 1, 1, sf) }
        P.shards[i] = s
    end
    P.wsLabel = Text(mod, sc.cx)
end

-------------------------------------------------------------------------------
-- Build: Prayer of Mending
-------------------------------------------------------------------------------

local function BeadPos(i)
    local a = pi * (1.1 + (i - 1) * 0.2)
    local pm = C.PM
    return floor(pm.cx + cos(a) * pm.r + 0.5), floor(pm.cy + sin(a) * pm.r + 0.5)
end
Priest.BeadPos = BeadPos

local function BuildMending()
    local pm = C.PM
    local mf = Frame(mod, 1)
    P.mf = mf
    local HX, HY = pm.cx - 7, pm.cy - 6
    P.chain, P.beads, P.lockDots = {}, {}, {}
    for i = 1, 4 do
        local x1, y1 = BeadPos(i)
        local x2, y2 = BeadPos(i + 1)
        local t = Tex(mf, "ARTWORK", 0, FLAT, 1, 1)
        Place(t, floor((x1 + x2) / 2 + 0.5), floor((y1 + y2) / 2 + 0.5))
        P.chain[i] = t
    end
    for i = 1, 5 do
        local x, y = BeadPos(i)
        local t = Tex(mf, "ARTWORK", 1, MEDIA .. "priest_mending.tga", 7, 7)
        Place(t, x - 3, y - 3)
        P.beads[i] = t
        for d = 1, 2 do
            local dot = Tex(mf, "ARTWORK", 1, FLAT, 1, 1)
            Tint(dot, K.muted, 0.4)
            Place(dot, x, y + (d == 1 and -1 or 1))
            P.lockDots[#P.lockDots + 1] = dot
        end
    end
    P.heartGlow = Tex(mf, "BACKGROUND", 0, MEDIA .. "priest_mending.tga", 18, 15)
    MendCell(P.heartGlow, MCELL.heartGlow, 18, 15)
    Place(P.heartGlow, HX - 2, HY - 1)
    P.heart = Tex(mf, "ARTWORK", 2, MEDIA .. "priest_mending.tga", 14, 12)
    Place(P.heart, HX, HY)
    local cdBar = CreateFrame("StatusBar", nil, mf)
    cdBar:SetFrameLevel(mod:GetFrameLevel() + 3)
    cdBar:EnableMouse(false)
    cdBar:SetStatusBarTexture(MEDIA .. "priest_heart_cd.tga")
    if cdBar.SetOrientation then pcall(cdBar.SetOrientation, cdBar, "VERTICAL") end
    if cdBar.SetReverseFill then pcall(cdBar.SetReverseFill, cdBar, true) end      -- the shade hangs from the top
    cdBar:SetMinMaxValues(0, 1)
    cdBar:SetValue(0)
    cdBar.fsBase = mod
    Seat(function() cdBar:SetSize(S(14), S(12)); Forget(cdBar); Place(cdBar, HX, HY) end)
    P.cdBar = cdBar

    P.seats = {}
    for i = 1, 5 do
        local sx, y = pm.seatX[i], pm.seatY
        local s = {}
        s.glow1 = Tex(mf, "BACKGROUND", 1, FLAT, 15, 14); Place(s.glow1, sx - 7, y - 1); Tint(s.glow1, K.gold, 0.22)
        s.glow2 = Tex(mf, "BACKGROUND", 1, FLAT, 13, 16); Place(s.glow2, sx - 6, y - 2); Tint(s.glow2, K.gold, 0.22)
        s.bg = Tex(mf, "BACKGROUND", 2, FLAT, 13, 12); Place(s.bg, sx - 6, y); Tint(s.bg, K.seatBg, 1)
        local bar = CreateFrame("StatusBar", nil, mf)
        bar:SetFrameLevel(mod:GetFrameLevel() + 2)
        bar:EnableMouse(false)
        bar:SetStatusBarTexture(FLAT)
        bar:SetStatusBarColor(K.litBody[1], K.litBody[2], K.litBody[3], 1)
        if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
        bar:SetMinMaxValues(0, 1)
        bar:SetValue(0)
        bar.fsBase = mod
        Seat(function() bar:SetSize(S(11), S(8)); Forget(bar); Place(bar, sx - 5, y + 1) end)
        s.bar = bar
        local over = Frame(mf, 3)
        s.over = over
        local sides = Frame(over, 4)
        s.sides = sides
        s.side1 = Tex(sides, "ARTWORK", 0, FLAT, 1, 10); Place(s.side1, sx - 7, y + 1); Tint(s.side1, K.aura, 0.3)
        s.side2 = Tex(sides, "ARTWORK", 0, FLAT, 1, 10); Place(s.side2, sx + 7, y + 1); Tint(s.side2, K.aura, 0.3)
        s.edges = {
            Tex(over, "ARTWORK", 1, FLAT, 13, 1), Tex(over, "ARTWORK", 1, FLAT, 13, 1),
            Tex(over, "ARTWORK", 1, FLAT, 1, 12), Tex(over, "ARTWORK", 1, FLAT, 1, 12),
        }
        Place(s.edges[1], sx - 6, y); Place(s.edges[2], sx - 6, y + 11)
        Place(s.edges[3], sx - 6, y); Place(s.edges[4], sx + 6, y)
        s.ws = Tex(over, "ARTWORK", 2, FLAT, 13, 2); Place(s.ws, sx - 6, y - 1); Tint(s.ws, K.violet, 1)
        s.strip = Tex(over, "ARTWORK", 2, FLAT, 11, 1); Place(s.strip, sx - 5, y + 9)
        s.heart = Tex(over, "ARTWORK", 3, MEDIA .. "priest_mending.tga", 7, 6)
        MendCell(s.heart, MCELL.heartSmall, 7, 6)
        Place(s.heart, sx - 3, y + 2)
        P.seats[i] = s
    end
    local over = Frame(mf, 4)
    P.you = Tex(over, "ARTWORK", 0, FLAT, 5, 1); Place(P.you, pm.seatX[1] - 2, pm.seatY - 3); Tint(P.you, K.you, 0.6)
    P.sparkGlow = Tex(over, "OVERLAY", 0, FLAT, 3, 3); Tint(P.sparkGlow, K.pink, 0.45)
    P.sparkCore = Tex(over, "OVERLAY", 1, FLAT, 1, 1); Tint(P.sparkCore, K.sparkCore, 1)
    local bx = pm.seatX[1] - 6
    P.barW = pm.seatX[5] + 6 - bx + 1
    P.timerBg = Tex(mf, "ARTWORK", 0, FLAT, P.barW, 2); Place(P.timerBg, bx, pm.seatY + 15); Tint(P.timerBg, K.barBg, 1)
    P.timerFill = Tex(mf, "ARTWORK", 1, FLAT, P.barW, 2); Place(P.timerFill, bx, pm.seatY + 15)
    P.pomLabel = Text(mod, pm.cx)
end

-------------------------------------------------------------------------------
-- Build: the right side's two medallions (Spirit Tap above, Inner Fire below)
-------------------------------------------------------------------------------

local ATLAS = MEDIA .. "priest_medallion.tga"

-- Per medallion: where it stands, its glyph cells, its colours, and the engine text beside it (`text`: the time left or the
-- charges). `nudges`: the amber reminder. `glow`: a glow ring in the lit look. `haloBreath`: seconds of the halo's breath.
local MEDS = {
    { key = "spirit", y = 21, lit = "skullLit", dim = "skullDim", dots = "skullDots", halo = "skullHalo",
      glow = true, glowC = K.spGlow, rim = K.spRim, rimIn = K.spRimIn, num = K.spNum, text = "duration", haloBreath = 1.0 },
    { key = "fire", y = 63, lit = "shieldLit", dim = "shieldDim", dots = "shieldDots", halo = "shieldHalo", amber = "shieldAmber",
      nudges = true, glowC = K.ifGlow, rim = K.ifRim, rimIn = K.ifRimIn, num = K.ifNum, text = "count", haloBreath = 0.9 },
}
Priest.MEDS = MEDS

local function BuildMedallions()
    local md = C.MED
    local rf = Frame(mod, 1)
    P.rf = rf
    P.meds = {}
    for i, def in ipairs(MEDS) do
        local m = { def = def, key = def.key, st = { armed = false, failures = 0, gaveUp = false, rebuilds = 0, live = false } }
        local bx, by = md.cx - md.CENTER, def.y - md.CENTER
        -- the anchor: a plain frame on the medallion's art box. The engine slot sits on it and the cover is drawn on it.
        local anc = CreateFrame("Frame", nil, rf)
        anc:SetFrameLevel(mod:GetFrameLevel() + 2)
        anc:EnableMouse(false)
        anc.fsBase = mod
        Seat(function() anc:SetSize(S(md.BOX), S(md.BOX)); Forget(anc); Place(anc, bx, by) end)
        m.anc = anc
        -- the centre of the number: a 1 x 1 plain frame the engine text and the L12 label hang on
        local numAnc = CreateFrame("Frame", nil, rf)
        numAnc:SetSize(1, 1)
        numAnc:EnableMouse(false)
        Seat(function()
            numAnc:ClearAllPoints()
            numAnc:SetPoint("CENTER", mod, "TOPLEFT", S(md.nx), -(S(def.y) + ui(C.NUM_LIFT * C.NUM_SIZE)))
        end)
        m.numAnc = numAnc
        local function MT(layer, sub)
            local t = Tex(rf, layer, sub, ATLAS, md.BOX, md.BOX)
            Place(t, bx, by)
            return t
        end
        m.glow = MT("BACKGROUND", 0)
        m.face = MT("ARTWORK", 0)
        m.rim = MT("ARTWORK", 1)
        m.rimIn = MT("ARTWORK", 2)
        m.halo = MT("ARTWORK", 3)
        m.glyph = MT("ARTWORK", 4)
        for _, t in ipairs({ m.glow, m.face, m.rim, m.rimIn, m.halo, m.glyph }) do On(t, false) end
        if def.key == "fire" then
            local lock = rf:CreateFontString(nil, "OVERLAY")
            lock.cur = { 1, 1, 1, 1 }
            lock:SetJustifyH("CENTER")
            Seat(function()
                FS.Theme.ApplyMono(lock, ui(C.NUM_SIZE), lock.cur)
                lock:ClearAllPoints()
                lock:SetPoint("CENTER", numAnc, "CENTER", 0, 0)
            end)
            lock:SetText("")
            m.lock = lock
        end
        P.meds[i] = m
    end
    -- the pull now cue: an amber glow ring over Spirit Tap's cover (a plain frame above the container)
    local spirit = P.meds[1]
    local cf = Frame(rf, 9)
    P.cueFrame = cf
    P.cueGlow = Tex(cf, "OVERLAY", 0, ATLAS, md.BOX, md.BOX)
    MedCell(P.cueGlow, MEDCELL.glow)
    Place(P.cueGlow, md.cx - md.CENTER, spirit.def.y - md.CENTER)
    Tint(P.cueGlow, K.amber, 0)
    On(P.cueGlow, false)
end

-------------------------------------------------------------------------------
-- Paint
-------------------------------------------------------------------------------

-- The secret absorb of the watched unit and of each seat, straight into the setters. Never compared.
local function PaintAbsorbs()
    local unit = Data.Watched()
    local v = Data.Absorb(unit)
    local mark = Data.Mark(unit)
    local bar, gate = P.bar, P.gate
    if v == nil then
        bar:SetMinMaxValues(0, 1); bar:SetValue(0); gate:SetAlpha(0)
    else
        bar:SetMinMaxValues(0, mark or v)
        bar:SetValue(v)
        gate:SetAlpha(v)
        if not abbreviateOff and type(AbbreviateNumbers) == "function" then
            local fs = P.absorbLabel
            local ok, text = pcall(AbbreviateNumbers, v)
            if ok then ok = pcall(fs.SetFormattedText, fs, "%s", text) end
            if not ok then abbreviateOff = true; fs:SetText(""); LogOnce("abbreviate", "the absorb number is off on this client") end
        end
    end
    if P.mode ~= "pom" then return end
    for i = 1, 5 do
        local s = P.seats[i]
        local u = Data.SeatUnit(i)
        local a = s.fsMine and Data.Absorb(u) or nil
        if a == nil then
            s.bar:SetMinMaxValues(0, 1); s.bar:SetValue(0); s.sides:SetAlpha(0)
        else
            s.bar:SetMinMaxValues(0, Data.Mark(u) or a)
            s.bar:SetValue(a)
            s.sides:SetAlpha(a)
        end
    end
end

local function ShowShards(k)
    local sc = C.SHIELD
    local V = Priest.SHARDS
    for i = 1, 8 do
        local s, v = P.shards[i], V[i]
        if k then
            local qx = floor(sc.cx + v[1] + v[3] * k * 18 + 0.5)
            local qy = floor(sc.cy + v[2] + v[4] * k * 12 + k * k * 14 + 0.5)
            On(s.big, true); On(s.dot, true)
            Place(s.big, qx, qy); Place(s.dot, qx, qy)
            local a = Stepped(1 - k)
            Tint(s.big, K.shard, a); Tint(s.dot, K.white, a)
        else
            On(s.big, false); On(s.dot, false)
        end
    end
end
Priest.SHARDS = { { -16, -14, -1.2, -0.6 }, { 15, -10, 1.3, -0.4 }, { -12, 4, -1, 0.3 }, { 12, 6, 1.1, 0.5 },
    { -3, -4, -0.3, 1 }, { 6, -16, 0.6, -1 }, { -8, 14, -0.6, 0.8 }, { 9, 18, 0.7, 0.7 } }

local function InDisc(x, y, r) return x * x + y * y <= r * r + r * 0.8 end

-- Returns true while something on the shield moves.
local function PaintShield(now, combat)
    local sc = C.SHIELD
    if not Data.ShieldKnown() then
        On(P.halo, false); On(P.body, false); On(P.stateLine, false)
        On(P.bar, false); On(P.gate, false); On(P.top, false)
        ShieldCell(P.stateRim, CELL.rimDash)
        On(P.stateRim, true); Tint(P.stateRim, K.muted, 0.4)
        On(P.stateRune, true); Tint(P.stateRune, K.muted, 0.22)
        ShowShards(nil)
        P.ShakeTo(0)
        Label(P.wsLabel, "L6", K.muted)
        return false
    end
    On(P.body, true); On(P.bar, true); On(P.gate, true); On(P.top, true)

    local unit = Data.Watched()
    local r = Data.Shield(unit)
    local up = r and r.up or false
    local wsRem = r and r.ws and r.wsExpires and (r.wsExpires - now) or nil
    local ws = wsRem ~= nil and wsRem > 0
    local cd = Data.ShieldCooling() == true
    local nudge = combat and not ws and not up and not cd
    local calm = not combat and not ws and not up and not cd
    local b = nudge and Stepped(Beat(now, C.NUDGE)) or 0

    -- the empty looks (the light, when there is any, covers them). Calm is the GHOST (design mockup "Priest shield, off state",
    -- option C): its own cells, colours baked, so the region is not tinted; every other empty look keeps the dark shield and the
    -- tinted dashed rim.
    ShieldCell(P.body, calm and CELL.ghost or CELL.dark)
    ShieldCell(P.stateRim, calm and CELL.ghostRim or CELL.rimDash)
    On(P.stateRim, not ws and not cd)
    if calm then Tint(P.stateRim, K.white, 1)
    elseif nudge then Tint(P.stateRim, K.amber, 0.35 + 0.65 * b)
    else Tint(P.stateRim, K.rimClear, 0.45) end
    On(P.halo, nudge)
    if nudge then Alpha(P.halo, b) end
    On(P.stateRune, true)
    if ws then Tint(P.stateRune, K.violet, 1)
    elseif nudge then Tint(P.stateRune, K.amber, 0.45 + 0.55 * b)
    elseif cd then Tint(P.stateRune, K.cdOuter, 1)
    elseif calm then Tint(P.stateRune, K.rimClear, 0.7)
    else Tint(P.stateRune, K.rimClear, 1) end
    On(P.stateLine, ws or not (calm or cd))
    if ws then Tint(P.stateLine, K.violet, 0.25) else Tint(P.stateLine, K.rimClear, 0.22) end

    -- the rims over the light
    On(P.cdRim, cd and not ws)
    On(P.wsDark, ws)
    if P.wsCd then
        On(P.wsCd, ws)
        if ws then
            local dur = r.wsDuration or 15
            local start = r.wsExpires - dur
            if P.wsCd.fsStart ~= start or P.wsCd.fsDur ~= dur then
                P.wsCd.fsStart, P.wsCd.fsDur = start, dur
                pcall(P.wsCd.SetCooldown, P.wsCd, start, dur)
            end
        else
            P.wsCd.fsStart = nil
        end
    elseif P.wsStatic then
        On(P.wsStatic, ws)
    end

    -- the light's life: breathing aura and rays, the glint, the motes, a hit's flash and shake (all under the absorb gate)
    local br = Stepped(0.6 + 0.4 * Beat(now, C.BREATH))
    Alpha(P.aura, br); Alpha(P.rays, br)
    local gp = (now % C.GLINT_EVERY) / C.GLINT_LEN
    if gp < 1 then
        On(P.glint, true)
        local f = floor(gp * C.GLINT_FRAMES)
        Cell(P.glint, f, 512, 256, 4, 128, C.BOX, C.BOX)
    else
        On(P.glint, false)
    end
    local R = sc.r
    for i = 1, 5 do
        local m = P.motes[i]
        local ph = (now * C.MOTE_SPEED + (i - 1) * 0.2) % 1
        local mx, my = C.MOTE_X[i], floor(R - 6 - ph * (2 * R - 4) + 0.5)
        local a = Stepped(sin(ph * pi))
        local inside = InDisc(mx, my, R - 2)
        On(m.core, inside)
        if inside then
            Place(m.core, sc.cx + mx, sc.cy + my)
            Tint(m.core, K.white, a)
        end
        local arms = inside and a > 0.6
        for j = 1, 4 do
            local t = m.arms[j]
            On(t, arms)
            if arms then
                local dx = (j == 1 and -1) or (j == 2 and 1) or 0
                local dy = (j == 3 and -1) or (j == 4 and 1) or 0
                Place(t, sc.cx + mx + dx, sc.cy + my + dy)
                Tint(t, K.white, Stepped(0.4 * a))
            end
        end
    end
    local sinceHit = hitAt and (now - hitAt) or nil
    On(P.flash, sinceHit ~= nil and sinceHit < C.FLASH)
    if sinceHit and sinceHit < C.SHAKE then
        P.ShakeTo((floor(sinceHit * 50) % 2 == 1) and 1 or -1)
    else
        P.ShakeTo(0)
    end
    local sinceBreak = breakAt and (now - breakAt) or nil
    ShowShards(sinceBreak and sinceBreak < C.BREAK and sinceBreak / C.BREAK or nil)

    -- the label: the absorb while the guess says there is light, else the lock's time
    local wsLabel = ws and not up
    On(P.absorbLabel, not wsLabel)
    if wsLabel then Label(P.wsLabel, TimeLabel(wsRem, r.wsEst), K.violetLabel) else Label(P.wsLabel, "") end
    TextColor(P.absorbLabel, K.label, 1)

    return up or ws or cd or nudge or (sinceHit ~= nil and sinceHit < C.SHAKE)
        or (sinceBreak ~= nil and sinceBreak < C.BREAK) or (castAt ~= nil and now - castAt < 1)
end

local CLASS_COLORS = _G.RAID_CLASS_COLORS
local function SeatColor(i, unit)
    local exists = unit == "player"
    if not exists and type(UnitExists) == "function" then
        local ok, e = pcall(UnitExists, unit)
        exists = ok and not IsSecret(e) and e and true or false
    end
    if not exists then return nil end
    local token
    if type(UnitClass) == "function" then
        local ok, _, t = pcall(UnitClass, unit)
        if ok and not IsSecret(t) and type(t) == "string" then token = t end
    end
    local c = token and type(CLASS_COLORS) == "table" and CLASS_COLORS[token]
    if type(c) == "table" and type(c.r) == "number" then
        local cache = P.classCache[i]
        if cache[1] ~= c.r or cache[2] ~= c.g or cache[3] ~= c.b then cache[1], cache[2], cache[3] = c.r, c.g, c.b end
        return cache
    end
    return C.SEAT_CLASS[i]
end

local function PaintMending(now, combat)
    local m = Data.Mending()
    local locked = not m.known
    On(P.heart, true)
    for i = 1, #P.lockDots do On(P.lockDots[i], locked) end
    if locked then
        MendCell(P.heart, MCELL.heartLocked, 14, 12)
        Alpha(P.heart, 1)
        On(P.heartGlow, false); On(P.cdBar, false)
        for i = 1, 4 do On(P.chain[i], false) end
        for i = 1, 5 do On(P.beads[i], false) end
        for i = 1, 5 do
            local s = P.seats[i]
            On(s.glow1, false); On(s.glow2, false); On(s.bg, false); On(s.bar, false); On(s.over, false)
            s.fsMine = false
        end
        On(P.you, false); On(P.sparkGlow, false); On(P.sparkCore, false); On(P.timerBg, false); On(P.timerFill, false)
        Label(P.pomLabel, "L40", K.muted)
        return false
    end
    local out = m.out and true or false
    local cooling = Data.MendingCooling() == true
    local nudge = combat and not out and not cooling
    local b = Stepped(Beat(now, C.NUDGE))
    for i = 1, 4 do On(P.chain[i], true); Tint(P.chain[i], out and K.chainOut or K.chainOff, 1) end
    local charges = m.charges or 0
    for i = 1, 5 do
        On(P.beads[i], true)
        local cell = out and (i <= charges and MCELL.beadLit or MCELL.beadOff) or (nudge and MCELL.beadDash or MCELL.beadOff)
        MendCell(P.beads[i], cell, 7, 7)
    end
    if out then
        MendCell(P.heart, MCELL.heartLit, 14, 12); Alpha(P.heart, 1)
        On(P.heartGlow, true); Tint(P.heartGlow, K.pink, Stepped(0.16 + 0.14 * Beat(now, C.HEART_PULSE)))
    elseif nudge then
        MendCell(P.heart, MCELL.heartAmber, 14, 12); Alpha(P.heart, 0.4 + 0.6 * b)
        On(P.heartGlow, true); Tint(P.heartGlow, K.amber, Stepped(0.28 * b))
    else
        MendCell(P.heart, MCELL.heartOff, 14, 12); Alpha(P.heart, 1)
        On(P.heartGlow, false)
    end
    -- the cooldown shade: the engine's timer, from the duration object; a client without one shows no shade
    local shade = not out and cooling
    if shade and not P.cdBar.fsTimer then
        local obj = Data.MendingCooldownDuration()
        local E = _G.Enum
        local dir = E and E.StatusBarTimerDirection and E.StatusBarTimerDirection.RemainingTime
        local interp = E and E.StatusBarInterpolation and E.StatusBarInterpolation.Immediate
        P.cdBar.fsTimer = obj ~= nil and P.cdBar.SetTimerDuration ~= nil
            and pcall(P.cdBar.SetTimerDuration, P.cdBar, obj, interp, dir) or false
    elseif not shade then
        P.cdBar.fsTimer = nil
    end
    On(P.cdBar, shade and P.cdBar.fsTimer == true)

    -- the party strip
    for i = 1, 5 do
        local s = P.seats[i]
        local unit = Data.SeatUnit(i)
        local hold = out and m.holder == i
        On(s.bg, true); On(s.over, true)
        On(s.glow1, hold); On(s.glow2, hold)
        local edge = hold and K.gold or K.seatEdge
        for j = 1, 4 do Tint(s.edges[j], edge, 1) end
        local cc = SeatColor(i, unit)
        On(s.strip, true)
        Tint(s.strip, cc or K.seatEdge, hold and 1 or 0.5)
        On(s.heart, hold)
        local r = cc and Data.Shield(unit) or nil
        local mine = r and r.up and r.mine or false
        if s.fsMine ~= mine then s.fsMine = mine; P.absorbDirty = true end
        On(s.bar, mine); On(s.sides, mine)
        local wsRem = r and r.ws and r.wsMine and r.wsExpires and (r.wsExpires - now) or nil
        if wsRem and wsRem > 0 then
            On(s.ws, true)
            local n = ceil(13 * wsRem / 15)
            if n > 13 then n = 13 end
            Size(s.ws, n, 2)
        else
            On(s.ws, false)
        end
    end
    On(P.you, true)

    -- the jump spark
    local sinceJump = m.jumpAt and (now - m.jumpAt) or nil
    if sinceJump and sinceJump < C.JUMP and m.from and m.holder then
        local k = sinceJump / C.JUMP
        local x1, x2 = C.PM.seatX[m.from], C.PM.seatX[m.holder]
        local x = floor(x1 + (x2 - x1) * k + 0.5)
        local y = floor(C.PM.seatY + 5 - sin(k * pi) * 16 + 0.5)
        On(P.sparkGlow, true); On(P.sparkCore, true)
        Place(P.sparkGlow, x - 1, y - 1); Place(P.sparkCore, x, y)
    else
        On(P.sparkGlow, false); On(P.sparkCore, false)
        sinceJump = nil
    end

    -- the jump timer
    On(P.timerBg, true)
    local rem = out and m.expires and (m.expires - now) or nil
    if rem and rem > 0 then
        local w = floor(P.barW * rem / 30 + 0.5)
        if w > P.barW then w = P.barW end
        On(P.timerFill, w > 0)
        if w > 0 then Size(P.timerFill, w, 2) end
        Tint(P.timerFill, rem < 6 and K.amber or K.gold, 1)
        Label(P.pomLabel, TimeLabel(rem, m.est), rem < 6 and K.amber or K.goldLabel)
    else
        On(P.timerFill, false)
        Label(P.pomLabel, "")
    end
    return out or nudge or cooling or sinceJump ~= nil
end

-- The base of one medallion: "calm", "nudge" (Inner Fire missing), "lit" (the plain look, without the engine's number, for a
-- medallion whose engine slot is not live) or "locked". The regions are plain; this runs in combat too. Colours that are baked
-- into a cell are drawn untinted (white at alpha 1).
local function PaintMedBase(m, look, b)
    local def, face, glow, rim, rimIn, halo, glyph = m.def, m.face, m.glow, m.rim, m.rimIn, m.halo, m.glyph
    if look == "locked" then
        On(face, false); On(glow, false); On(rimIn, false); On(halo, false)
        MedCell(rim, MEDCELL.dash); On(rim, true); Tint(rim, K.muted, 0.4)
        MedCell(glyph, MEDCELL[def.dots]); On(glyph, true); Tint(glyph, K.white, 1); Alpha(glyph, 1)
    elseif look == "nudge" then
        MedCell(face, MEDCELL.body); On(face, true); Tint(face, K.white, 1)
        On(glow, false); On(rimIn, false)
        MedCell(rim, MEDCELL.dash); On(rim, true); Tint(rim, K.amber, 0.35 + 0.65 * b)
        MedCell(halo, MEDCELL[def.halo]); On(halo, true); Tint(halo, K.amber, 0.22 * b)
        MedCell(glyph, MEDCELL[def.amber]); On(glyph, true); Tint(glyph, K.white, 1); Alpha(glyph, 0.4 + 0.6 * b)
    elseif look == "lit" then
        MedCell(face, MEDCELL.body); On(face, true); Tint(face, K.white, 1)
        MedCell(rim, MEDCELL.rimOuter); On(rim, true); Tint(rim, def.rim, 1)
        MedCell(rimIn, MEDCELL.rimInner); On(rimIn, true); Tint(rimIn, def.rimIn, 1)
        if def.glow then
            MedCell(glow, MEDCELL.glow); On(glow, true); Tint(glow, def.glowC, 0.4)
        else
            On(glow, false)
        end
        MedCell(halo, MEDCELL[def.halo]); On(halo, true); Tint(halo, def.glowC, 0.19)
        MedCell(glyph, MEDCELL[def.lit]); On(glyph, true); Tint(glyph, K.white, 1); Alpha(glyph, 1)
    else
        MedCell(face, MEDCELL.ghost); On(face, true); Tint(face, K.white, 1)
        On(glow, false); On(rim, false); On(rimIn, false); On(halo, false)
        MedCell(glyph, MEDCELL[def.dim]); On(glyph, true); Tint(glyph, K.white, 1); Alpha(glyph, 1)
    end
end

-- Returns true while something on the medallions moves (the nudge, the cue).
local function PaintMedallions(now)
    local b = Stepped(Beat(now, C.NUDGE))
    local remind = Right.Remind()
    local moving = false
    for i = 1, #P.meds do
        local m = P.meds[i]
        local key = m.key
        local plain = Right.PlainUp(key)                 -- nil in combat: nothing is read there
        local look
        if not Right.Known(key) then look = "locked"
        elseif m.st.live then look = (m.def.nudges and remind and plain ~= true) and "nudge" or "calm"
        elseif plain == true then look = "lit"
        elseif plain == false and m.def.nudges and remind then look = "nudge"
        else look = "calm" end
        PaintMedBase(m, look, b)
        if look == "nudge" then moving = true end
        if m.lock then Label(m.lock, look == "locked" and ("L" .. Right.DEFS.fire.level) or "", K.muted) end
    end
    local cue = Right.Cue(now)
    On(P.cueGlow, cue)
    if cue then
        Tint(P.cueGlow, K.amber, 0.9 * (0.35 + 0.65 * Stepped(Beat(now, C.MED_BREATH))))
        moving = true
    end
    return moving
end

-- Shows the right side's look: the mending parts, the medallions, or nothing.
local function ApplyMode(mode)
    if P.mode == mode or not P.rf then return end
    P.mode = mode
    On(P.mf, mode == "pom")
    On(P.pomLabel, mode == "pom")
    On(P.rf, mode == "medallions")
    P.absorbDirty = true
end

local function RightMode()
    return Right and Right.Mode and Right.Mode() or "pom"
end

local Sync
local function PaintAll(now)
    if not mod then return end
    local combat = InCombat()
    local mode = RightMode()
    ApplyMode(mode)
    local ok1, a = pcall(PaintShield, now, combat)
    if not ok1 then LogOnce("paintshield", a); a = false end
    local b = false
    if mode == "pom" then
        local ok2, v = pcall(PaintMending, now, combat)
        if not ok2 then LogOnce("paintmending", v) else b = v end
    elseif mode == "medallions" then
        local ok2, v = pcall(PaintMedallions, now)
        if not ok2 then LogOnce("paintmedallions", v) else b = v end
    end
    if P.absorbDirty then
        P.absorbDirty = false
        local ok, err = pcall(PaintAbsorbs)
        if not ok then LogOnce("absorb", err) end
    end
    P.moving = (a or b) and true or false
    if Sync then Sync() end
end

local function Tick(_, elapsed)
    acc = acc + elapsed
    absorbAcc = absorbAcc + elapsed
    if acc < C.TICK then return end
    acc = 0
    local now = GetTime()
    local ok, err = pcall(Data.Tick, now)
    if not ok then LogOnce("tick", err) end
    if absorbAcc >= C.ABSORB_EVERY then absorbAcc = 0; P.absorbDirty = true end
    PaintAll(now)
end

Sync = function()
    local want = subscribed and mod ~= nil and P.moving == true
    if want == ticking then return end
    ticking = want
    acc = 0
    mod:SetScript("OnUpdate", want and Tick or nil)
end

-------------------------------------------------------------------------------
-- The engine drawn cover of the medallions (UNVERIFIED live), the way BuffTab.lua draws its shield slot
-------------------------------------------------------------------------------

local EG = C.ENGINE
local engineTemplateOk
local parked = {}

local function Quiet(obj, method, ...)
    local okGet, fn = pcall(function() return obj[method] end)
    if okGet and type(fn) == "function" then return (pcall(fn, obj, ...)) end
    return true
end

local function EngineTemplate()
    if engineTemplateOk ~= nil then return engineTemplateOk end
    local info = C_XMLUtil and C_XMLUtil.GetTemplateInfo
    local ok = false
    if type(info) == "function" then
        local good, result = pcall(info, EG.TEMPLATE)
        ok = good and result ~= nil and result ~= false
    end
    engineTemplateOk = ok
    return ok
end

-- true when the container reads back in the wanted state; a blocked call raises nothing, so only a readback proves it.
local function ContainerIs(container, live)
    local ok, isShown = pcall(container.IsShown, container)
    if ok and not IsSecret(isShown) and (isShown and true or false) ~= live then return false end
    local okFn, fn = pcall(function() return container.IsEnabled end)
    if okFn and type(fn) == "function" then
        local okE, enabled = pcall(fn, container)
        if okE and not IsSecret(enabled) and (enabled and true or false) ~= live then return false end
    end
    return true
end

local function Rect(region)
    local okL, left = pcall(region.GetLeft, region)
    local okT, top = pcall(region.GetTop, region)
    local okR, right = pcall(region.GetRight, region)
    local okB, bottom = pcall(region.GetBottom, region)
    if okL and okT and okR and okB and type(left) == "number" and type(top) == "number" and type(right) == "number"
        and type(bottom) == "number" and not IsSecret(left) and not IsSecret(top) and not IsSecret(right)
        and not IsSecret(bottom) then
        return left, top, right, bottom
    end
    return nil
end

-- true when `slot` stands on `anchor` (all four edges), false when it stands elsewhere, nil when either cannot be read.
local function Placed(slot, anchor)
    local sl, st, sr, sb = Rect(slot)
    local al, at, ar, ab = Rect(anchor)
    if not (sl and al) then return nil end
    return math.abs(al - sl) <= 1.5 and math.abs(at - st) <= 1.5 and math.abs(ar - sr) <= 1.5 and math.abs(ab - sb) <= 1.5
end

-- true when `slot` is hidden (the engine hides a slot with no aura). An unreadable answer is "not hidden".
local function Hidden(slot)
    local ok, shown = pcall(slot.IsShown, slot)
    return ok and not IsSecret(shown) and shown == false
end

-- true when `slot` has no size, width and height both plain 0: it draws nothing.
local function Collapsed(slot)
    local okW, w = pcall(slot.GetWidth, slot)
    local okH, h = pcall(slot.GetHeight, slot)
    return okW and okH and type(w) == "number" and type(h) == "number" and not IsSecret(w) and not IsSecret(h)
        and w == 0 and h == 0
end

local function GuardMouse(slot)
    local function MouseOn(method)
        local ok, fn = pcall(function() return slot[method] end)
        if not (ok and type(fn) == "function") then return false end
        local okCall, answer = pcall(fn, slot)
        return okCall and not IsSecret(answer) and answer == true
    end
    if not (MouseOn("IsMouseClickEnabled") or MouseOn("IsMouseMotionEnabled")) then return end
    LogOnce("engine_mouse", "a medallion slot has the mouse on; it is switched off")
    Quiet(slot, "SetMouseClickEnabled", false)
    Quiet(slot, "SetMouseMotionEnabled", false)
end

-- One plain boolean answer of `slot` to `method`, or nil and why not: "error", "secret", "type:<type>" or "missing".
local function PlainBoolean(slot, method)
    local call = slot[method]
    if type(call) ~= "function" then return nil, "missing" end
    local ok, v = pcall(call, slot)
    if not ok then return nil, "error" end
    if IsSecret(v) then return nil, "secret" end
    if type(v) ~= "boolean" then return nil, "type:" .. type(v) end
    return v
end

-- What a slot shows right now, for the state line (out of combat only, plain values only).
local function ReadPart(part)
    local slot = part.slot
    local shown, why = PlainBoolean(slot, "IsShown")
    if shown == nil then
        local visible, why2 = PlainBoolean(slot, "IsVisible")
        if visible ~= nil then shown = visible else why = why .. "/" .. why2 end
    end
    part.shownCode = shown == nil and 0 or (shown and 2 or 1)
    part.shownWhy = shown == nil and why or nil
    local okW, w = pcall(slot.GetWidth, slot)
    local okH, h = pcall(slot.GetHeight, slot)
    part.w = (okW and type(w) == "number" and not IsSecret(w)) and floor(w + 0.5) or 0
    part.h = (okH and type(h) == "number" and not IsSecret(h)) and floor(h + 0.5) or 0
end

-- A looping breath on `region`: the vertex alpha is the brightest, the animation swings the region alpha between `lo` and 1 over
-- `period` s (the two steps meet end to end, so the loop has no jump). nil when the client has no animation groups.
local function Breath(region, lo, period)
    if not region.CreateAnimationGroup then return nil end
    local ok, group = pcall(function()
        local g = region:CreateAnimationGroup()
        g:SetLooping("REPEAT")
        local up = g:CreateAnimation("Alpha")
        up:SetFromAlpha(lo); up:SetToAlpha(1); up:SetDuration(period / 2); up:SetOrder(1)
        if up.SetSmoothing then up:SetSmoothing("IN_OUT") end
        local down = g:CreateAnimation("Alpha")
        down:SetFromAlpha(1); down:SetToAlpha(lo); down:SetDuration(period / 2); down:SetOrder(2)
        if down.SetSmoothing then down:SetSmoothing("IN_OUT") end
        g:Play()
        return g
    end)
    return ok and group or nil
end

-- The lit look of a medallion, drawn by the slot frame (a child of the slot, so the engine shows and hides it with the slot).
-- Every region is anchored to the medallion's own anchor frame, written once here and never again. Built in initializeFrame.
local function CoverSlot(m, part)
    local slot, def, anc = part.slot, m.def, m.anc
    local function Layer(layer, sub, cell, c, a)
        local t = slot:CreateTexture(nil, layer, nil, sub)
        SetTex(t, ATLAS)
        t:SetTexCoord(CellRect(cell, 512, 256, 6, 80, C.MED.BOX, C.MED.BOX))
        t:SetAllPoints(anc)
        t:SetVertexColor(c[1], c[2], c[3], a)
        return t
    end
    part.cover = {}
    local function Add(t) part.cover[#part.cover + 1] = t; return t end
    if def.glow then
        local g = Add(Layer("BACKGROUND", 0, MEDCELL.glow, def.glowC, 0.5))
        if not Breath(g, 0.6, C.MED_BREATH) then g:SetVertexColor(def.glowC[1], def.glowC[2], def.glowC[3], 0.4) end
    end
    Add(Layer("ARTWORK", 0, MEDCELL.body, K.white, 1))
    Add(Layer("ARTWORK", 1, MEDCELL.rimOuter, def.rim, 1))
    Add(Layer("ARTWORK", 2, MEDCELL.rimInner, def.rimIn, 1))
    local h = Add(Layer("ARTWORK", 3, MEDCELL[def.halo], def.glowC, 0.24))
    if not Breath(h, 0.583, def.haloBreath) then h:SetVertexColor(def.glowC[1], def.glowC[2], def.glowC[3], 0.19) end
    Add(Layer("ARTWORK", 4, MEDCELL[def.lit], K.white, 1))
end

-- The number: the engine's own text for the aura, in the house mono font, centred beside the medallion. Seated again out of
-- combat when the scale changes.
local function SeatPart(m, part)
    local num = part.num
    if not num then return end
    pcall(function()
        FS.Theme.ApplyMono(num, ui(C.NUM_SIZE), num.cur)
        num:ClearAllPoints()
        num:SetPoint("CENTER", m.numAnc, "CENTER", 0, 0)
    end)
end

-- The slot's frame, built by the engine (at AddAuraSlot, or later, when it first needs one): no mouse, seated on the anchor, the
-- cover and the number. Each step on its own, so a missing method stops nothing. It registers its part on the medallion.
local function InitSlot(m)
    local eng = m.eng                                  -- captured at add time: the one this slot was declared on
    return function(slot)
        Quiet(slot, "SetMouseMotionEnabled", false)
        Quiet(slot, "SetMouseClickEnabled", false)
        Quiet(slot, "SetHideTooltipInCombat", true)
        if m.eng ~= eng then return end                -- a parked container's late frame is not this medallion's
        local part = { slot = slot, ok = false }
        eng.parts[#eng.parts + 1] = part
        eng.bad = true                                 -- UNPROVEN until a proof pass out of combat has read it
        pcall(slot.SetAllPoints, slot, m.anc)
        pcall(CoverSlot, m, part)
        pcall(function()
            local num = slot:CreateFontString(nil, "OVERLAY")
            num.cur = { m.def.num[1], m.def.num[2], m.def.num[3], 1 }
            num:SetJustifyH("CENTER")
            if m.def.text == "duration" then slot:SetDurationText(num, {}) else slot:SetApplicationCount(num) end
            part.num = num
            SeatPart(m, part)
        end)
    end
end

local function SortOptions()
    local method = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local direction = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    return method, direction
end

local function ParkContainer(container)
    Quiet(container, "SetEnabled", false)
    Quiet(container, "Hide")
    Quiet(container, "SetAlpha", 0)
    parked[#parked + 1] = container
end

-- Builds the medallion's container with its one slot, out of combat. Returns the container and the id set it covers. Any failure
-- parks the container (a frame cannot be destroyed) before raising.
local function BuildContainer(m)
    local container = CreateFrame("AuraContainer", nil, P.rf, EG.TEMPLATE)
    local ids
    m.eng = { declared = 0, parts = {}, bad = true }
    local ok, err = pcall(function()
        container:SetSize(1, 1)
        container:SetPoint("CENTER", m.anc, "CENTER", 0, 0)
        container:SetFrameLevel(mod:GetFrameLevel() + EG.LEVEL)
        container:SetUnit("player")
        container:SetAlpha(0)
        ids = Right.Ids(m.key)
        local method, direction = SortOptions()
        container:AddAuraSlot(m.key, "HELPFUL", {
            initializeFrame = InitSlot(m),
            candidateFilters = { includeSpellIDs = ids },
            sortMethod = method,
            sortDirection = direction,
        })
        m.eng.declared = 1
        container:SetEnabled(true)
        container:Show()
    end)
    if not ok then
        ParkContainer(container)
        m.eng = nil
        error(err, 0)
    end
    return container, ids
end

-- The PROOF pass, out of combat only: the slot read against the anchor BEFORE anything is written. A slot found off the anchor is
-- put back (the medallion is not live until the next pass reads it right); one that cannot be read is unproven, except that an
-- IDLE slot (hidden, or with no size, or the aura readably absent: nothing to draw or to locate) keeps the proof it has. A
-- medallion none of whose slots was ever seen on its anchor stays unproven. Allocation free when nothing is wrong.
local function ProveEngine(m)
    local eng = m.eng
    if not eng then return end
    local bad, anyOk, skipped = false, false, false
    local down = Right.PlainUp(m.key) == false or not Right.Known(m.key)
    for _, part in ipairs(eng.parts) do
        ReadPart(part)
        local placed = Placed(part.slot, m.anc)
        local idle = placed == nil and (down or Hidden(part.slot) or Collapsed(part.slot))
        if idle and part.ok then
            part.nils = 0                                  -- keeps its last proof
        else
            part.ok = placed == true
            if idle then
                part.nils = 0                              -- unproven, but nothing is there to be mislaid or to draw
            elseif placed == nil then
                part.nils = (part.nils or 0) + 1
                if part.nils >= EG.UNREADABLE_TICKS then
                    LogOnce("engine_unreadable", "a medallion slot cannot be located; it keeps the plain look")
                end
            else
                part.nils = 0
            end
            if not part.ok and idle then
                skipped = true
            elseif not part.ok then
                bad = true
                if placed == false then
                    LogOnce("engine_layout", "a medallion slot is not on its anchor; it is put back")
                    pcall(part.slot.SetAllPoints, part.slot, m.anc)
                end
            end
        end
    end
    for _, part in ipairs(eng.parts) do
        if part.ok then anyOk = true end
    end
    if (skipped or #eng.parts == 0) and not anyOk then bad = true end
    eng.bad = bad
end

-- Re-seats the numbers for the current scale, reads the mouse back, then proves the positions. Out of combat only.
local function SeatEngine(m)
    local eng = m.eng
    if not eng then return end
    for _, part in ipairs(eng.parts) do
        SeatPart(m, part)
        GuardMouse(part.slot)
    end
    ProveEngine(m)
end

-- true when an id of `ids` was never covered by a container of this medallion before.
local function HasNewId(m, ids)
    local seen = m.st.seenIds
    if not seen then return true end
    for id in pairs(ids) do
        if not seen[id] then return true end
    end
    return false
end

-- Whether the medallion is live: its container armed and its slot proven. The container is visible (alpha 1) only then: an
-- unproven slot must not draw a stray cover over the plain look. The only write that combat could also make, but nothing here is
-- called in combat. Returns true when the answer changed.
local function SyncLive(m)
    local st = m.st
    local live = st.container ~= nil and st.armed and m.eng ~= nil and not m.eng.bad and not st.gaveUp
    if st.container then
        local want = live and 1 or 0
        if st.alpha ~= want and Quiet(st.container, "SetAlpha", want) then st.alpha = want end
    end
    if st.live == live then return false end
    st.live = live
    return true
end

-- Out of combat: builds the medallion's container once (when the spell is known), arms it again when it reads back off, rebuilds it
-- when the id set grew. `retry` is the tick's one uncounted second attempt after a failed build. Combat does none of it.
local function EnsureEngine(m, retry)
    local st = m.st
    if st.gaveUp or not P.rf or InCombat() then return end
    local container = st.container
    if container then
        local rebuild = false
        if HasNewId(m, Right.Ids(m.key)) then
            if st.rebuilds < EG.REBUILDS then
                rebuild = true
            else
                LogOnce("engine_cap", "a new rank appeared; /reload to cover it")
            end
        end
        if not rebuild then
            if not ContainerIs(container, true) then
                Quiet(container, "SetUnit", "player")
                Quiet(container, "SetEnabled", true)
                Quiet(container, "Show")
                st.alpha = nil
            end
            st.armed = ContainerIs(container, true)
            return
        end
        st.rebuilds = st.rebuilds + 1
        ParkContainer(container)
        st.container, st.armed, st.alpha, m.eng = nil, false, nil, nil
    end
    if not Right.Known(m.key) then return end
    if st.passTried and not retry then return end
    if not EngineTemplate() then
        LogOnce("engine_template", "this client has no " .. EG.TEMPLATE .. "; the medallions show no engine state")
        st.gaveUp = true
        return
    end
    local ok, result, ids = pcall(BuildContainer, m)
    if ok then
        st.failures, st.retryAt = 0, nil
        st.container, st.alpha = result, 0
        st.seenIds = st.seenIds or {}
        for id in pairs(ids) do st.seenIds[id] = true end
        st.armed = ContainerIs(result, true)
        return
    end
    LogOnce("engine_build", "the medallion state could not be built (" .. tostring(result) .. ")")
    if retry then return end               -- the extra attempt costs nothing and is not repeated
    st.passTried = true                    -- one counted attempt per out of combat pass; regen starts the next
    st.failures = st.failures + 1
    st.retryAt = GetTime() + EG.RETRY
    if st.failures >= EG.LIMIT then st.gaveUp = true end
end

-- The state of the engine route for the live test, in ForeverSTUwaveDB.gunsightPriestRight (on disk after a /reload or a logout):
-- `line` is the one readable line. Rewritten only when something it shows changed (a numeric signature is compared first).
-- A plain whole number or "secret" for a value that is not one: nothing in the line is formatted from a raw value.
local function Plain(v)
    if IsSecret(v) then return "secret" end
    if type(v) ~= "number" or v ~= v or v == math.huge or v == -math.huge then return "?" end
    return tostring(floor(v + 0.5))
end

local function Num(v)
    if type(v) ~= "number" or IsSecret(v) or v ~= v or v == math.huge or v == -math.huge then return 0 end
    return v
end

local function CodeText(v, no, yes)
    if IsSecret(v) then return "secret" end
    if v == 2 then return yes end
    if v == 1 then return no end
    return "?"
end

local function WriteStatus()
    if not P.meds then return end
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" or (FS.Config and type(FS.Config.IsReadOnly) == "function" and FS.Config.IsReadOnly()) then return end
    local sig = InCombat() and 8 or 0
    local text = { "mode=" .. tostring(P.mode) }
    for _, m in ipairs(P.meds) do
        local st, eng = m.st, m.eng
        sig = (sig * 31 + (st.armed and 1 or 0) + (st.gaveUp and 2 or 0) + (st.retryAt and 4 or 0) + (st.live and 16 or 0)
            + (st.alpha or 2) * 32 + st.rebuilds * 128 + st.failures * 1024) % 2147483647
        local detail = {}
        if eng then
            sig = (sig * 31 + #eng.parts * 7 + (eng.bad and 1 or 0)) % 2147483647
            for n, part in ipairs(eng.parts) do
                sig = (sig * 31 + Num(part.shownCode) * 5 + Num(part.w) * 3 + Num(part.h) + (part.ok and 3 or 0)
                    + Num(part.nils) * 13 + (part.shownWhy and #part.shownWhy or 0) * 37 + (part.cover and #part.cover or 0) * 19
                    + (part.num and 23 or 0)) % 2147483647
                detail[#detail + 1] = string.format("slot%d shown=%s %sx%s ok=%s cover=%s number=%s", n,
                    CodeText(part.shownCode, "false", "true") .. (part.shownWhy and ("(" .. part.shownWhy .. ")") or ""),
                    Plain(part.w), Plain(part.h), tostring(part.ok == true), Plain(part.cover and #part.cover or 0),
                    tostring(part.num ~= nil))
            end
        end
        text[#text + 1] = string.format("%s known=%s armed=%s live=%s alpha=%s failures=%s rebuilds=%s gaveUp=%s%s", m.key,
            tostring(Right.Known(m.key)), tostring(st.armed), tostring(st.live), tostring(st.alpha), Plain(st.failures),
            Plain(st.rebuilds), tostring(st.gaveUp), #detail > 0 and (" [" .. table.concat(detail, "; ") .. "]") or "")
    end
    local saved = db.gunsightPriestRight
    if type(saved) == "table" and saved.sig == sig and saved == P.status then return end   -- a corrupt value is replaced
    saved = { sig = sig, line = table.concat(text, " | ") }
    db.gunsightPriestRight = saved
    P.status = saved
end

local function SaveStatus()
    local ok, err = pcall(WriteStatus)
    if not ok then LogOnce("status", "the right side state line could not be saved: " .. tostring(err)) end
end

-- Out of combat: ensures, seats and proves both medallions (the right side's own events, the module's seat, regen).
local function EnsureEngines()
    if InCombat() or not P.meds or RightMode() ~= "medallions" then return false end
    local changed = false
    for _, m in ipairs(P.meds) do
        EnsureEngine(m, false)
        if m.st.container then SeatEngine(m) end
        if SyncLive(m) then changed = true end
    end
    SaveStatus()
    return changed
end

-- The 1 s tick, out of combat only: the one uncounted retry of a failed build, and the proof pass.
local function EngineTick()
    if InCombat() or not P.meds or RightMode() ~= "medallions" then return end
    local changed = false
    for _, m in ipairs(P.meds) do
        local st = m.st
        local at = st.retryAt
        if at and not st.container and GetTime() >= at then
            st.retryAt = nil
            EnsureEngine(m, true)
            if st.container then SeatEngine(m) end
        elseif st.container then
            ProveEngine(m)
        end
        if SyncLive(m) then changed = true end
    end
    SaveStatus()
    if changed then PaintAll(GetTime()) end
end

-- The 1 s tick while the module is shown: a chain of C_Timer.After calls (no OnUpdate frame: the module's own ticker stops when
-- nothing moves, and the proof must go on). It ends by itself when the module is hidden and picks up again on the next show.
local function ArmEngineTimer()
    if P.timerOn or not (C_Timer and C_Timer.After) then return end
    P.timerOn = true
    local function Step()
        if not subscribed then
            P.timerOn = false
            return
        end
        local ok, err = pcall(EngineTick)
        if not ok then LogOnce("enginetick", err) end
        C_Timer.After(EG.EVERY, Step)
    end
    C_Timer.After(EG.EVERY, Step)
end

local function OnChange(reason, unit)
    local now = GetTime()
    if reason == "hit" and unit and type(UnitIsUnit) == "function" then
        local ok, same = pcall(UnitIsUnit, unit, Data.Watched())
        if ok and not IsSecret(same) and same and not (castAt and now - castAt < 0.3) then hitAt = now end
    elseif reason == "break" and unit then
        local ok, same = pcall(UnitIsUnit, unit, Data.Watched())
        if ok and not IsSecret(same) and same then breakAt = now end
    elseif reason == "cast" then
        castAt = now
    end
    P.absorbDirty = true
    if subscribed then PaintAll(now) end
end

-- The right side's own changes (the setting, the group, a spell learned, an aura on or off, a kill, the end of a fight): out of
-- combat the engine route is ensured and proven again, then everything is repainted. In combat only the plain regions are written.
local function OnRightChange(reason)
    if not mod then return end
    if reason == "combat" and not InCombat() and P.meds then
        for _, m in ipairs(P.meds) do m.st.passTried = false end      -- a new out of combat pass may try a failed build again
    end
    EnsureEngines()
    P.absorbDirty = true
    if subscribed then PaintAll(GetTime()) end
end

-------------------------------------------------------------------------------
-- Area seams
-------------------------------------------------------------------------------

-- The module's top left in image px, and a hook for whoever seats something over the shield (GunsightPriestClick.lua's click
-- catcher): fn(OX, OY) after every seat.
local seatListeners = {}
function Priest.Origin() return OX, OY end
function Priest.OnSeat(fn)
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
        if not InCombat() and P.meds then          -- the engine slots' texts are seated out of combat only (regen does it)
            for _, m in ipairs(P.meds) do SeatEngine(m) end
        end
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
        LogOnce("notheme", "Theme is missing, the Priest module is not built")
        return nil
    end
    Data = FS.PriestShields
    Right = FS.PriestRight
    if not (Data and Data.Watched and Data.Subscribe) then
        LogOnce("nodata", "FS.PriestShields is missing, the Priest module has no data")
        return nil
    end
    if mod then return mod end
    mod = CreateFrame("Frame", "ForeverSTUwaveGunsightPriest", host)
    Seat(function()
        Point(mod, "TOPLEFT", OX, OY)
        mod:SetSize(ui(C.W), ui(C.H))
    end)
    P.classCache = { {}, {}, {}, {}, {} }
    local ok, err = pcall(function()
        BuildShield()
        BuildMending()
        if Right then BuildMedallions() end
    end)
    if not ok then
        LogOnce("build", err)
        mod:Hide()
        mod = nil
        seats = {}
        P = {}
        return nil
    end
    Priest.frame, Priest.parts = mod, P
    if Data.Start then Data.Start() end
    if Right and Right.Start then Right.Start() end
    P.absorbDirty = true
    EnsureEngines()
    PaintAll(GetTime())
    return mod
end

local function OnAreaShown()
    if not mod then return end
    if not subscribed then
        subscribed = true
        Data.Subscribe(OnChange)
        if Right and Right.Subscribe then Right.Subscribe(OnRightChange) end
    end
    local ok, err = pcall(Data.Refresh)
    if not ok then LogOnce("refresh", err) end
    P.absorbDirty = true
    EnsureEngines()
    ArmEngineTimer()
    PaintAll(GetTime())
    Sync()
end

local function OnAreaHidden()
    if not mod then return end
    if subscribed then
        subscribed = false
        Data.Unsubscribe(OnChange)
        if Right and Right.Unsubscribe then Right.Unsubscribe(OnRightChange) end
    end
    Sync()
end

-- for the harness
Priest._PaintShield, Priest._PaintMending, Priest._PaintAbsorbs = PaintShield, PaintMending, PaintAbsorbs
Priest._PaintMedallions, Priest._EngineTick, Priest._EnsureEngines = PaintMedallions, EngineTick, EnsureEngines

local okReg, result = pcall(Areas.RegisterModule, "class", {
    classes = { "PRIEST" },
    build = BuildModule, seat = SeatModule, onShow = OnAreaShown, onHide = OnAreaHidden,
})
if not okReg or not result then
    LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")")
end
