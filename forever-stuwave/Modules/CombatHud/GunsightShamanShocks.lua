-- Forever STUwave: Gunsight Shaman Class Module, lane 2: the SHOCK DISC and the FIRE NOVA FLAME DISC.
--
-- The approved design is the design mockup "Shaman Shock Tracker Polish" (2026-11-07) on top of Concept A "Totem Poles": the
-- shared Earth / Flame / Frost Shock cooldown is a carved rune disc on the right of the poles with a Sowilo pixel bolt in it. The
-- rim refills clockwise and the bolt charges from its tip up as the cooldown runs (both drawn by the ENGINE from the cooldown),
-- the label under the disc says RDY or the seconds, and a ready shock breathes (a stepped halo, a shimmer down the bolt, a crackle
-- arc and tip sparks). A shock cast flashes white, throws eight sparks and drains the rim and bolt fast; the cooldown ending
-- flashes again with an expanding ring and a white label. The old zig-zag line under the poles is gone. Under the shock disc
-- stands its twin in fire, the Fire Nova flame disc of the design mockup "Shaman Nova Tracker" (2026-11-08, form A): the same
-- build with a smaller radius and a pixel flame for the glyph (it replaces the cyan ring over the Fire totem's head and the NOVA
-- footer tag). There is no Earth Shock KICK tag here: KICK comes from GunsightTape.lua's class neutral tag on the target box.
-- GunsightShaman.lua owns the module frame and the totem poles and calls this file:
--
--   FS.GunsightShamanShocks = { Build(frame) -> section, Seat(section, rect, scale), OnShow(section), OnHide(section) }
--
-- `frame` is the class module frame (a child of the area host), `rect` the module rect in image px { x, y, w, h } (every piece
-- sits at the mockup's offset from rect.x and rect.y, so either area works), `scale` is unused (ui() carries it). Nothing here
-- is built at file load. The poles tell the section whether the Fire totem stands through a function that lives on the SECTION,
-- not on the table:
--
--   section.SetFire(up, headY)   up: true (the Fire totem stands), false (it is gone: no flame disc), nil (not known, the
--                                default: a Fire Nova that reads unusable for a reason other than mana counts as "no totem");
--                                headY is accepted and ignored (the old ring rode the Fire head, the flame disc stands in the
--                                right column and does not move)
--
-- THE SHOCK. Earth, Flame and Frost Shock share one cooldown (6 s), so one record answers for all three. READY comes from the
-- cooldown's plain isActive (plain in combat, probe 2026-10-01): false is ready, whatever else; a plain isOnGCD or a cooldown no
-- longer than the global one is ready too. The seconds are secret in combat. Out of combat the label is the plain start and
-- duration. In combat it is an ESTIMATE ("~") from our own last cast (UNIT_SPELLCAST_SUCCEEDED of the player, any rank, matched by
-- name, kept on through OnHide because a cast while hidden cannot be re-read), exactly the rule HudLogic's CooldownState uses:
-- with isActive true and the timing secret the ledger decides, ready unless its cast plus the learned cooldown length is still
-- ahead; a cast the ledger never saw reads ready (it fails toward suggesting the spell). A secret isActive is UNKNOWN: a muted
-- outline bolt and "?", no charge, never a guess. THE REFILL IS THE ENGINE'S: C_Spell.GetSpellCooldownDuration gives one duration
-- object (secret-bearing in combat) and it goes, untouched, into the bolt's vertical StatusBar:SetTimerDuration and the rim's
-- Cooldown:SetCooldownFromDurationObject (reversed, so the swipe shows the elapsed arc growing clockwise); without those APIs the
-- same plain or estimated timing feeds SetValue and SetCooldown. No secret is ever compared or computed on. Three things are
-- drawn from our own clock instead, because the engine has no draw for them: the cast drain (0.3 s after our own shock cast, a
-- plain StatusBar value and a mirrored rim art on a plain SetCooldown), the sparks and rings of the beats, and the spark riding
-- the rim front (only from a plain or estimated end time, so in combat it follows the ledger's guess, not the engine's draw).
--
-- WHAT DIFFERS FROM THE MOCKUP, ON PURPOSE. The bolt's StatusBar box is 16 x 32 px (a power of two file at two texels a px) and
-- the bolt's 24 rows sit in its middle: the fill starts 4 px above the box bottom and ends 4 px below its top, so the engine's
-- crop reaches the first bolt row after an eighth of the cooldown and the last after seven eighths (a plain value is mapped
-- exactly). During the 0.1 s cast flash the whole bolt goes white (the mockup keeps its unlit rows dark). The lit rim sits over
-- the dim rim, so 5 % of the dim violet shows through where the mockup replaces it.
-- The flame disc differs the same way: its StatusBar box is 16 x 16 px and the flame's 13 rows sit in it with 1 px above and 2
-- below, so the fill edge climbs 12 px while the share runs 0 to 1 and the engine's crop is continuous where the mockup lights
-- whole rows (the top row is never lit before the ready look, as in the mockup); the hot seam is a 0.96 px strip hung under the
-- fill's edge where the mockup recolours the rows within .08 of the share; the 0.3 s drain after a cast plays as the left-right
-- mirror of the mockup's, colours included (a Cooldown swipe keeps the arc from the elapsed angle to 12 o'clock, so the art is
-- baked mirrored); the ember positions use the module's sine hash.
--
-- FIRE NOVA. The flame disc needs the spell in the book (resolved by name, ids as a fallback, IsPlayerSpell and its siblings) and a
-- Fire totem standing, then the same cooldown reading with a 10 s ledger; with either missing nothing of it is drawn. It is the
-- shock disc's build with its own descriptor (NOVA_D): the rim and a pixel flame refill from the same duration object, the flame
-- climbing from its base to a hot seam at the fill's edge; ready it breathes amber to white, its tips flicker and embers drift up;
-- a cast flashes white, throws a ring of fire (two stepped rings) and drains the flame fast; the cooldown ending throws a smaller
-- ring. The label is RDY (amber, white for the first 0.3 s of the ready beat), the seconds in white ("~" for the in-combat
-- estimate, the shock label's format) or a muted "?". It cannot know whether an enemy is within 10 yd of the totem: the disc is
-- advice, not a guarantee.
--
-- EVENTS AND TICKER. The cast ledger listens from Build on and stays on through OnHide (it only records). Everything else
-- listens from OnShow to OnHide: SPELL_UPDATE_COOLDOWN and SPELL_UPDATE_USABLE, the spellbook events and PLAYER_REGEN_*. Nothing
-- here reads the target. One OnUpdate (30 Hz) runs while a shock is ready (it breathes) or charging, or a shown Fire Nova is ready
-- or charging, and stops itself otherwise; the cooldowns are re-read from it every tenth of a second. The per frame path allocates
-- nothing on the addon side: the time strings come from tables built at load, every texture, colour, alpha and anchor is written
-- only when it changes, and the sparks, embers and rings are pools of flat 1 px textures built once. Plain frames only, nothing
-- secure.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.ui and Gunsight.Point) then return end

local ui, Point = Gunsight.ui, Gunsight.Point
local IsSecret = FS.IsSecret or function() return false end

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FLAT = "Interface\\Buttons\\WHITE8x8"
local floor, sin, cos, pi, abs = math.floor, math.sin, math.cos, math.pi, math.abs

-------------------------------------------------------------------------------
-- Constants (image px from the module rect's top left; the harness re-reads the mockup's numbers)
-------------------------------------------------------------------------------

local function Hex(h)
    return { tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255 }
end

local C = {
    GY = 78,                                            -- poleMod: gy = y0 + 78, the ground line the poles stand on
    W = 202, H = 128,                                   -- the mockup's canvas: the sparks and rings are clipped to it
    SCX = 183, SCY = 42, SR = 14,                       -- the rune disc: its centre corner (GY - 36) and radius
    CELL = 32, HALO = 64,                               -- px of a cell of shaman_disc.tga and of shaman_disc_halo.tga
    BOLT_X = -8, BOLT_Y = -16, BOLT_W = 16, BOLT_H = 32,-- the bolt StatusBar's box from the disc centre (shaman_bolt_lit.tga: 32 x 64 texels)
    BOLT_TOP = -12, BOLT_BOT = 12, BOLT_SPAN = 25,      -- the bolt's top row, its tip's bottom edge, and the mockup's fill scale H
    SEAM = 1.25,                                        -- px of white under the fill's edge: abs(rowF - p) < .05 of 25
    LABEL_X = 183, LABEL_BASE = 68, LABEL_SIZE = 12,    -- txt(183, SCY + SR + 12, 'RDY' | seconds, 12, middle)
    DRAIN = 0.3, CAST_FLASH = 0.1, CAST_BURST = 0.5,    -- seconds after our own shock cast: the fast drain, the white flash, the sparks
    RDY_BEAT = 0.6, RDY_FLASH = 0.14, RDY_LABEL = 0.3, RDY_RING_FROM = 0.1,   -- seconds after the cooldown ended
    BREATH = 1.6, SHIMMER = 22, SHIMMER_SPAN = 34, CRACKLE = 10,   -- the ready breath period; rows a second and the span; arcs a second
    SHOCK_CD = 6, NOVA_CD = 10, GCD_WINDOW = 1.6,       -- seconds: the shared shock cooldown, Fire Nova's, the longest global cooldown
    TICK = 0.1, ANIM = 1 / 30,                          -- the cooldown re-read period; the animation's
    -- Mononoki Bold: the line box's middle sits 325 / 1024 of the size above the baseline (GunsightSeals.lua's CAP)
    CAP = 325 / 1024,
    -- the mockup palette of the pieces that are not theme tokens
    FX_WHITE = Hex("#f3fbff"),

    -- THE FIRE NOVA FLAME DISC (design mockup "Shaman Nova Tracker", form A; every number is drawSun's or the constants above it)
    NCX = 183, NCY = 102, NR = 12,                      -- the disc's centre corner (GY + 24) and radius: under the shock disc, 60 px below it
    NBOX_X = -8, NBOX_Y = -8, NBOX_W = 16, NBOX_H = 16, -- the flame StatusBar's box from the disc centre (nova_flame_lit.tga: 32 x 32 texels)
    NFLAME_TOP = -7, NFLAME_BOT = 5, NSPAN = 12,        -- the flame's top row, its base row, and the mockup's fill scale (rows - 1)
    NSEAM = 0.96,                                       -- px of hot flame under the fill's edge: abs(rowF - p) < .08 of the 12 row scale
    NLABEL_DY = 11, NLABEL_SIZE = 11,                   -- txt(NCX, NCY + NR + 11, 'RDY' | seconds, 11, middle)
    NDRAIN = 0.3, NCAST_FLASH = 0.1, NCAST_BEAT = 0.6,  -- seconds after our own Fire Nova cast: the fast drain, the white flash, the fire ring
    NCAST_GROW = 26, NCAST_GAP = 1.5, NCAST_A = 0.95, NCAST_A2 = 0.6,   -- the ring's growth in px, the inner ring's step in, the two alphas
    NRDY_BEAT = 0.6, NRDY_FLASH = 0.14, NRDY_LABEL = 0.3, NRDY_RING_FROM = 0.1, NRDY_RING_SPAN = 0.5,   -- seconds after the cooldown ended
    NRDY_GROW = 14, NRDY_RING_A = 0.9,                  -- the smaller ready ring: growth in px, alpha
    NRING_PX = 80,                                      -- px in a stepped ring
    NBREATH = 1.8, NFLICK_RATE = 8, NFLICK_PHASES = 3,  -- the ready breath period; the tips' step clock: steps a second, phases
    NEMBERS = 3, NEMBER_RATE = 0.7, NEMBER_X = 8, NEMBER_W = 16, NEMBER_DY = 1, NEMBER_RISE = 14, NEMBER_SPLIT = 0.5,   -- the drifting embers
    NEMBER_SEED = 13, NEMBER_SEED2 = 7,                 -- the hash's two multipliers (the mockup's own hash is not reproducible in Lua)
    NSPARK_IN = 0.9,                                    -- the rim spark sits this far inside the radius
    NHALO1 = 0.10, NHALO1_B = 0.16, NHALO2 = 0.04, NHALO2_B = 0.08,   -- the stepped halos' alpha: base + breath * b
    NWASH = 0.08, NWASH_B = 0.07, NFLASH_WASH = 0.8,    -- the plate's ready wash, and the flash's
    NRIM_A = 0.95, NRIM_BREATH = 0.3, NRIM_MIX = 0.9,   -- the lit rim's alpha; its amber to hot white mix: max(0, b - .3) * .9
    FIRE = Hex("#ff5a3c"), AMBER = Hex("#ffb648"), HOT = Hex("#fff1d0"),
}
C.BOLT_PAD = (C.BOLT_Y + C.BOLT_H) - C.BOLT_BOT          -- px between the box bottom and the tip's bottom edge (4)
C.NPAD = (C.NBOX_Y + C.NBOX_H) - (C.NFLAME_BOT + 1)      -- px between the flame box's bottom and the flame's base row (2)

-- the cells of shaman_disc.tga, in the generator's order (generate_shaman_disc.py DISC_CELLS; the harness checks)
local DISC_CELL = { disc = 0, mask = 1, dots = 2, rimDim = 3, rimLit = 4, notches = 5, outline = 6, boltEmpty = 7, boltReady = 8,
    boltMuted = 9, boltWhite = 10, boltInner = 11 }

-- the cells of nova_disc.tga, in the generator's order (generate_nova_disc.py DISC_CELLS; the harness checks): 4 x 4 cells, the
-- last two spare. The three flick cells are the flame's amber tips, one per phase of the ready step cycle.
local NOVA_CELL = { disc = 0, mask = 1, rimDim = 2, rimLit = 3, notches = 4, flameEmpty = 5, flameMuted = 6, flameReady = 7,
    flick0 = 8, flick1 = 9, flick2 = 10, flameWhite = 11, halo1 = 12, halo2 = 13 }

-- Spells by NAME first (a name answers with the player's own rank), ids only as a fallback. Earth Shock rank 1 is 8042; the
-- others are the classic rank 1 ids and Fire Nova's published id, all only tried when the name does not resolve.
local GROUPS = {
    shock = { cd = C.SHOCK_CD, members = {
        { name = "Earth Shock", ids = { 8042 } },
        { name = "Flame Shock", ids = { 8050 } },
        { name = "Frost Shock", ids = { 8056 } },
    } },
    nova = { cd = C.NOVA_CD, members = {
        { name = "Fire Nova", ids = { 408341 } },
    } },
}

-- "4s" above 3 s, "2.2s" under it (the mockup's fmt), and the same with a "~" for an estimate; built once, the tick only indexes
local SECS, EST_SECS, TENTHS, EST_TENTHS = {}, {}, {}, {}
for i = 0, 99 do
    SECS[i] = i .. "s"
    EST_SECS[i] = "~" .. i .. "s"
end
for i = 0, 30 do
    TENTHS[i] = string.format("%.1fs", i / 10)
    EST_TENTHS[i] = "~" .. TENTHS[i]
end

local function FormatRemaining(rem, est)
    if rem < 3 then
        local i = floor(rem * 10 + 0.5)
        if i < 0 then i = 0 end
        return est and EST_TENTHS[i] or TENTHS[i]
    end
    local i = floor(rem + 0.5)
    if i > 99 then i = 99 end
    return est and EST_SECS[i] or SECS[i]
end

-- the beats' directions, built once: eight sparks round the shock disc, 72 points of its expanding ring, and the 80 points of the
-- flame disc's stepped rings (the same angles as the mockup's stepRing)
local BURST_COS, BURST_SIN, RING_COS, RING_SIN, NRING_COS, NRING_SIN = {}, {}, {}, {}, {}, {}
for i = 1, 8 do
    local a = (i - 1) / 8 * pi * 2 + 0.2
    BURST_COS[i], BURST_SIN[i] = cos(a), sin(a)
end
for i = 1, 72 do
    local a = (i - 1) / 72 * pi * 2
    RING_COS[i], RING_SIN[i] = cos(a), sin(a)
end
for i = 1, C.NRING_PX do
    local a = (i - 1) / C.NRING_PX * 2 * pi
    NRING_COS[i], NRING_SIN[i] = cos(a), sin(a)
end

-- the mockup's own hash is not reproducible in Lua: a sine hash gives the same look (a different but equally random roll)
local function Hash(i)
    local v = sin(i * 12.9898) * 43758.5453
    return v - floor(v)
end

local function Beat(t, period) return 0.5 + 0.5 * sin(t * 2 * pi / period) end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshamanshocks_" .. key, "|cffff4488Forever STUwave|r: gunsight shaman shocks: " .. tostring(msg))
    end
end

-------------------------------------------------------------------------------
-- Secret safe reads
-------------------------------------------------------------------------------

-- v when it is plain and of that type, else nil. A false boolean comes back as false.
local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

local function SpellIdByName(name)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, name)
        if ok and type(info) == "table" and not IsSecret(info) then return PlainOf(info.spellID, "number") end
        return nil
    end
    if GetSpellInfo then
        local ok, _, _, _, _, _, _, id = pcall(GetSpellInfo, name)
        if ok then return PlainOf(id, "number") end
    end
    return nil
end

local nameCache = {}
local function SpellNameOf(id)
    local hit = nameCache[id]
    if hit then return hit end
    local name
    if C_Spell and C_Spell.GetSpellName then
        local ok, n = pcall(C_Spell.GetSpellName, id)
        if ok then name = PlainOf(n, "string") end
    end
    if not name and C_Spell and C_Spell.GetSpellInfo then
        local ok, info = pcall(C_Spell.GetSpellInfo, id)
        if ok and type(info) == "table" and not IsSecret(info) then name = PlainOf(info.name, "string") end
    end
    if name then nameCache[id] = name end
    return name
end

-- true / false / nil (cannot tell) for "does the player know this spell id", over the three book APIs a client may have
local function KnownFn(i)
    if i == 1 then return IsPlayerSpell end
    if i == 2 then return IsSpellKnown end
    return C_SpellBook and C_SpellBook.IsSpellKnown
end

local function IsKnownId(id)
    local sawFalse, unreadable = false, false
    for i = 1, 3 do
        local fn = KnownFn(i)
        if fn then
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) then
                if r then return true end
                sawFalse = true
            else
                unreadable = true
            end
        end
    end
    if unreadable then return nil end
    if sawFalse then return false end
    return nil
end

-- isActive, isOnGCD, startTime, duration of a spell's cooldown, each plain or nil. Nothing at all (no API, a throw) is four nils.
local function ReadCooldown(id)
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if fn then
        local ok, cd = pcall(fn, id)
        if not ok or type(cd) ~= "table" or IsSecret(cd) then return nil end
        return PlainOf(cd.isActive, "boolean"), PlainOf(cd.isOnGCD, "boolean"), PlainOf(cd.startTime, "number"), PlainOf(cd.duration, "number")
    end
    if GetSpellCooldown then
        local ok, start, dur = pcall(GetSpellCooldown, id)
        start, dur = PlainOf(start, "number"), PlainOf(dur, "number")
        if ok and start and dur then return dur > 0, nil, start, dur end
    end
    return nil
end

-------------------------------------------------------------------------------
-- The spellbook and the cooldown ledger
-------------------------------------------------------------------------------

-- Resolves every member of a group: its id (the player's rank by name, else a fallback id) and whether it is known. A group is
-- known when any member is; its id (the one asked for the shared cooldown) is the first known member's.
local function ResolveGroup(g)
    g.known, g.id = false, nil
    for _, m in ipairs(g.members) do
        m.id, m.known, m.localName = nil, false, nil
        local id = SpellIdByName(m.name)
        if id and IsKnownId(id) == true then
            m.id, m.known = id, true
        else
            for _, fid in ipairs(m.ids) do
                if IsKnownId(fid) == true then m.id, m.known = fid, true; break end
            end
        end
        if m.known then
            m.localName = SpellNameOf(m.id)
            if not g.known then g.known, g.id = true, m.id end
        end
    end
end

-- Fills g.mode ("none" not known, "ready", "charging", "unknown"), g.rem (plain seconds left, charging only), g.endsAt (the
-- plain or estimated GetTime the cooldown ends, charging only: the label, the spark and a plain fill count against it between
-- reads), g.est (the seconds come from the cast ledger) and g.span (the cooldown's own length).
local function ReadGroup(g, now)
    g.rem, g.est, g.endsAt = nil, false, nil
    if not g.known then g.mode = "none"; return end
    local active, onGcd, start, dur = ReadCooldown(g.id)
    if active == nil then g.mode = "unknown"; return end
    if active == false then g.mode, g.plainEnd = "ready", nil; return end
    if onGcd == true then g.mode = "ready"; return end
    if start and dur and dur > 0 then
        if dur <= C.GCD_WINDOW then g.mode, g.plainEnd = "ready", nil; return end
        -- the length is learned only from a cooldown that began at our own cast (a lockout or a shared start says nothing)
        if g.lastAt and math.abs(start - g.lastAt) <= C.GCD_WINDOW then g.len = dur end
        g.plainEnd = start + dur
        local rem = start + dur - now
        if rem <= 0 then g.mode = "ready"; return end
        g.mode, g.rem, g.span, g.endsAt = "charging", rem, dur, start + dur
        return
    end
    -- isActive true and the timing secret: the ledger decides (see the header)
    local ends = g.plainEnd
    local last = g.lastAt
    if last and now >= last then
        local e = last + g.len
        if not ends or e > ends then ends = e end
    end
    if ends and now < ends then
        g.mode, g.rem, g.est, g.span, g.endsAt = "charging", ends - now, true, g.len, ends
    else
        g.mode = "ready"
    end
end

-------------------------------------------------------------------------------
-- Drawing helpers
-------------------------------------------------------------------------------

local function Tok(name, fallback)
    local T = FS.Theme
    local v = T and T[name]
    if type(v) == "table" then return v end
    return fallback
end

-- A part shown or hidden only when its answer changes
local function SetOn(region, on)
    on = on and true or false
    if region.fsOn ~= on then
        region.fsOn = on
        region:SetShown(on)
    end
end

local function Tint(tex, c, a)
    local v = tex.fsTint
    if not v then v = { false, false, false, false }; tex.fsTint = v end
    if v[1] ~= c or v[4] ~= a then
        v[1], v[4] = c, a
        tex:SetVertexColor(c[1], c[2], c[3], a)
    end
end

-- the same with plain numbers (the breathing and the flash mix their colours): written only when a channel changed
local function TintRGB(tex, r, g, b, a)
    local v = tex.fsRGB
    if not v then v = { -1, -1, -1, -1 }; tex.fsRGB = v end
    if v[1] ~= r or v[2] ~= g or v[3] ~= b or v[4] ~= a then
        v[1], v[2], v[3], v[4] = r, g, b, a
        tex:SetVertexColor(r, g, b, a)
    end
end

local function SetAlphaOf(region, a)
    if region.fsAl ~= a then
        region.fsAl = a
        region:SetAlpha(a)
    end
end

local function TextTint(fs, c, a)
    if fs.fsC ~= c or fs.fsA ~= a then
        fs.fsC, fs.fsA = c, a
        fs:SetTextColor(c[1], c[2], c[3], a)
    end
end

-- Theme.ApplyMono resets a font string's colour: the font is set again at every seat, so the colour worn is put back after it
local function SeatFont(fs, size, fallback)
    local c = fs.fsC or fallback
    FS.Theme.ApplyMono(fs, ui(size), c)
    fs:SetTextColor(c[1], c[2], c[3], fs.fsA or 1)
end

local function SetLabel(fs, text)
    if fs.fsText ~= text then
        fs.fsText = text
        fs:SetText(text)
    end
end

-- A baked pixel art texture: nearest neighbour, so a px stays a hard square at any scale
local function NewPix(parent, layer, sub, path)
    local t = parent:CreateTexture(nil, layer, nil, sub)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
    t:Hide()
    t.fsOn = false
    return t
end

local function NewText(parent, size, justify, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.fsSize, fs.fsJustify = size, justify
    FS.Theme.ApplyMono(fs, ui(size), color)
    fs:SetJustifyH(justify)
    fs:SetText("")
    fs:Hide()
    fs.fsOn = false
    return fs
end

local function At(s, region, anchor, x, y)
    Point(region, anchor, s.ox + x, s.oy + y)
end

-- A part with a fixed place: its top left (x, y) and size (w, h) in image px from the rect, seated by SeatSection
local function Part(s, r, x, y, w, h)
    r.fsX, r.fsY, r.fsW, r.fsH = x, y, w, h
    s.parts[#s.parts + 1] = r
    return r
end

-- A part that moves: a flat 1 px texture from the pools. Placed (top left in image px from the rect) only when it moved.
local function PlaceTo(s, r, x, y)
    if r.fsX ~= x or r.fsY ~= y then
        r.fsX, r.fsY = x, y
        At(s, r, "TOPLEFT", x, y)
    end
end

local function NewFlat(s, parent, layer, sub, c, shown)
    local t = NewPix(parent, layer, sub, FLAT)
    t:SetVertexColor(c[1], c[2], c[3], 1)
    t.fsX, t.fsY, t.fsAl = false, false, false         -- the fields exist from the start: the first beat adds no key to a table
    s.pool[#s.pool + 1] = t
    if shown then t.fsOn = true; t:Show() end
    return t
end

-- A disc's descriptor: the two discs (the shock's rune disc, Fire Nova's flame disc) are one build with different numbers. cx, cy
-- the centre corner in image px from the rect, file / cells the atlas of 4 x 4 cells (64 texels, 32 px, the centre in the middle)
-- and its name -> index map, barFile and bx, by, bw, bh the vertical StatusBar's art and box from the centre, rim / mirror the
-- two ring arts (the engine's refill and the cast drain), sparkR the rim spark's radius, drain the cast drain's seconds and frac
-- the bar's fill fraction for a share of the cooldown. Filled in below, after the fractions.
local SHOCK_D, NOVA_D

-- a cell of a disc's atlas, 32 px square with the disc's centre in its middle
local function NewCell(s, parent, layer, sub, name, d)
    local t = NewPix(parent, layer, sub, MEDIA .. d.file)
    local i = d.cells[name]
    local l, top = (i % 4) * 0.25, floor(i / 4) * 0.25
    t:SetTexCoord(l, l + 0.25, top, top + 0.25)
    return Part(s, t, d.cx - C.CELL / 2, d.cy - C.CELL / 2, C.CELL, C.CELL)
end

-- a plain frame that fills the holder at a level above it (a frame with no rect draws nothing on this client)
local function NewLayer(s, parent, level)
    local f = CreateFrame("Frame", nil, parent)
    f:SetAllPoints(parent)
    f:SetFrameLevel(s.level + level)
    f:EnableMouse(false)
    return f
end

-- a frame that clips its children to its rect (the sparks to the canvas, the shimmer to one row); silently unclipped on a client
-- without the call
local function Clips(f)
    if f.SetClipsChildren then pcall(f.SetClipsChildren, f, true) end
end

local function NewBar(s, parent, level, d)
    local bar = CreateFrame("StatusBar", nil, parent)
    bar:SetFrameLevel(s.level + level)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. d.barFile)
    if bar.SetOrientation then pcall(bar.SetOrientation, bar, "VERTICAL") end
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar:Hide()
    bar.fsOn = false
    return Part(s, bar, d.cx + d.bx, d.cy + d.by, d.bw, d.bh)
end

-- the rim: a Cooldown whose swipe is the ring art; nil on a client without the frame type
local function NewSwipe(s, parent, level, file, reverse, d)
    local ok, cd = pcall(CreateFrame, "Cooldown", nil, parent)
    if not (ok and cd and cd.SetSwipeTexture and cd.SetCooldown) then return nil end
    cd:SetFrameLevel(s.level + level)
    cd:EnableMouse(false)
    pcall(cd.SetSwipeTexture, cd, MEDIA .. file, 1, 1, 1, 1)
    if cd.SetSwipeColor then pcall(cd.SetSwipeColor, cd, 1, 1, 1, 1) end
    if cd.SetDrawEdge then pcall(cd.SetDrawEdge, cd, false) end
    if cd.SetDrawBling then pcall(cd.SetDrawBling, cd, false) end
    if cd.SetHideCountdownNumbers then pcall(cd.SetHideCountdownNumbers, cd, true) end
    if cd.SetReverse then pcall(cd.SetReverse, cd, reverse) end
    cd:Hide()
    cd.fsOn = false
    return Part(s, cd, d.cx - C.CELL / 2, d.cy - C.CELL / 2, C.CELL, C.CELL)
end

-------------------------------------------------------------------------------
-- Painting (each write only on a change)
-------------------------------------------------------------------------------

-- The engine's refill: one duration object into the bolt's StatusBar and the rim's Cooldown. Returns whether the bar took it
-- (then nothing else feeds the bar); the rim falls back to a plain start and length when it could not be fed. `f` holds the
-- disc's parts (the section itself for the shock disc, section.fd for the flame disc).
local function StartTimer(f, g)
    local rim, bar = f.rimFill, f.bar
    local fed = false
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    local obj
    if fn and g.id then
        local ok, o = pcall(fn, g.id)
        if ok then obj = o end
    end
    local barOk = false
    if obj ~= nil then
        local E = _G.Enum
        local interp = E and E.StatusBarInterpolation and E.StatusBarInterpolation.Immediate
        local dir = E and E.StatusBarTimerDirection and E.StatusBarTimerDirection.ElapsedTime
        barOk = bar.SetTimerDuration ~= nil and (pcall(bar.SetTimerDuration, bar, obj, interp, dir)) or false
        if rim and rim.SetCooldownFromDurationObject then
            fed = (pcall(rim.SetCooldownFromDurationObject, rim, obj)) or false
        end
    end
    if rim and not fed and g.span and g.endsAt then
        pcall(rim.SetCooldown, rim, g.endsAt - g.span, g.span)
    end
    return barOk
end

-- the share of the shock's cooldown spent, 0 to 1, from a plain or estimated end time
local function SpentShare(g, now)
    local span = g.span
    if not (span and span > 0 and g.endsAt) then return 0 end
    local p = 1 - (g.endsAt - now) / span
    if p < 0 then return 0 elseif p > 1 then return 1 end
    return p
end

-- the box fraction of the bolt StatusBar whose top edge sits at share p of the mockup's fill scale
local function BoltFraction(p)
    return (C.BOLT_PAD + C.BOLT_SPAN * p) / C.BOLT_H
end

-- the same for the flame's StatusBar: the base row sits NPAD px above the box bottom, and the mockup lights its 13 rows over the
-- 12 steps of rowF, so the fill edge climbs NSPAN px while the share runs from 0 to 1
local function NovaFraction(p)
    return (C.NPAD + C.NSPAN * p) / C.NBOX_H
end

SHOCK_D = { cx = C.SCX, cy = C.SCY, file = "shaman_disc.tga", cells = DISC_CELL, barFile = "shaman_bolt_lit.tga",
    bx = C.BOLT_X, by = C.BOLT_Y, bw = C.BOLT_W, bh = C.BOLT_H, rim = "shaman_disc_rim.tga", mirror = "shaman_disc_rim_mirror.tga",
    sparkR = C.SR - 0.9, drain = C.DRAIN, frac = BoltFraction }
NOVA_D = { cx = C.NCX, cy = C.NCY, file = "nova_disc.tga", cells = NOVA_CELL, barFile = "nova_flame_lit.tga",
    bx = C.NBOX_X, by = C.NBOX_Y, bw = C.NBOX_W, bh = C.NBOX_H, rim = "nova_disc_rim.tga", mirror = "nova_disc_rim_mirror.tga",
    sparkR = C.NR - C.NSPARK_IN, drain = C.NDRAIN, frac = NovaFraction }

local function PaintDisc(s, known, unk, ready, flash, h)
    local K = s.colors
    local c, w = K.cyan, C.FX_WHITE
    SetOn(s.disc, known); SetOn(s.dots, known); SetOn(s.rimDim, known); SetOn(s.notches, known); SetOn(s.outline, known)
    SetOn(s.halo1, ready); SetOn(s.halo2, ready)
    if ready then
        TintRGB(s.halo1, c[1], c[2], c[3], 0.10 + h * 0.16)
        TintRGB(s.halo2, c[1], c[2], c[3], 0.04 + h * 0.08)
    end
    -- the plate's wash: the flash is the mockup's two mixes folded into one overlay (cyan .7, then white .25 = .775 of one colour)
    if flash then
        local f = s.flashRGB
        TintRGB(s.tint, f[1], f[2], f[3], 0.775)
    elseif ready then
        TintRGB(s.tint, c[1], c[2], c[3], 0.07 + h * 0.08)
    end
    SetOn(s.tint, flash or ready)
    -- the lit rim over the whole ring: white at the flash, cyan to white with the breath when ready
    if flash then
        TintRGB(s.rimLit, w[1], w[2], w[3], 0.95)
    elseif ready then
        local t = (h - 0.35) * 0.8
        if t < 0 then t = 0 end
        TintRGB(s.rimLit, c[1] + (w[1] - c[1]) * t, c[2] + (w[2] - c[2]) * t, c[3] + (w[3] - c[3]) * t, 0.95)
    end
    SetOn(s.rimLit, flash or ready)
    -- the bolt's body: empty plate while charging, ready cyan, muted outline when unknown, white at a flash
    SetOn(s.boltEmpty, known and not unk and not ready)
    SetOn(s.boltMuted, unk)
    SetOn(s.boltReady, ready)
    SetOn(s.flashBolt, flash)
end

-- The refill (engine drawn) and the cast drain (our clock). `f` holds the disc's parts and its running state, `d` is its descriptor.
local function PaintFill(s, f, d, now, g, run, casting, sc, restart)
    if run ~= f.running then f.running = run; restart = true end
    SetOn(f.bar, run); SetOn(f.seam, run)
    if f.rimFill then SetOn(f.rimFill, run) end
    if run then
        if restart or f.barTimer == nil then f.barTimer = StartTimer(f, g) end
        local p = SpentShare(g, now)
        if not f.barTimer then
            local v = d.frac(p)
            if not f.barValue or abs(v - f.barValue) > 0.002 then
                f.barValue = v
                f.bar:SetValue(v)
            end
        end
        if p > 0 and p < 1 then               -- the spark on the rim front: the mockup's px for the share (Math.round(v - .5) = floor(v))
            local ang = p * pi * 2
            local R = d.sparkR
            PlaceTo(s, f.spark, d.cx + floor(sin(ang) * R), d.cy + floor(-cos(ang) * R))
            SetOn(f.spark, true)
        else
            SetOn(f.spark, false)
        end
    else
        f.barTimer = nil
        SetOn(f.spark, false)
    end
    if casting ~= f.draining then f.draining = casting; f.drainStart = nil end
    SetOn(f.drain, casting)
    if f.rimDrain then SetOn(f.rimDrain, casting) end
    if casting then
        if f.rimDrain and f.drainStart ~= g.lastAt then
            f.drainStart = g.lastAt
            pcall(f.rimDrain.SetCooldown, f.rimDrain, g.lastAt, d.drain)
        end
        local v = d.frac(1 - sc / d.drain)
        if not f.drainValue or abs(v - f.drainValue) > 0.002 then
            f.drainValue = v
            f.drain:SetValue(v)
        end
    end
end

-- The ready shimmer and crackle, the cast sparks, the cooldown's expanding ring
local function PaintFx(s, now, ready, burst, sc, ringOn, sr)
    SetOn(s.shimA, ready); SetOn(s.shimB, ready)
    if ready then
        local ry = C.BOLT_TOP - 4 + floor((now * C.SHIMMER) % C.SHIMMER_SPAN)
        if s.shimRy ~= ry then
            s.shimRy = ry
            At(s, s.shimA, "TOPLEFT", C.SCX - C.CELL / 2, C.SCY + ry)
            At(s, s.shimB, "TOPLEFT", C.SCX - C.CELL / 2, C.SCY + ry - 1)
        end
        local n = floor(now * C.CRACKLE)          -- arcs and tip sparks change ten times a second
        if s.crackN ~= n then
            s.crackN = n
            local crack = s.crack
            for k = 0, 1 do
                local on = Hash(n * 3 + k + 21) < 0.34
                local a = Hash(n * 7 + k + 31) * pi * 2
                local x, y = C.SCX + cos(a) * (C.SR + 1), C.SCY + sin(a) * (C.SR + 1)
                for i = 0, 2 do
                    local px = crack[k * 3 + i + 1]
                    SetOn(px, on)
                    if on then PlaceTo(s, px, floor(x + 0.5), floor(y + 0.5)) end
                    a = a + (Hash(n * 11 + k * 5 + i) - 0.5) * 1.1
                    x, y = x + cos(a) * 1.7, y + sin(a) * 1.7
                end
            end
            local t1, t2 = s.tips[1], s.tips[2]
            PlaceTo(s, t1, C.SCX - 6 + floor(Hash(n + 41) * 3), C.SCY - 13)
            SetAlphaOf(t1, Hash(n + 43) < 0.5 and 1 or 0.4)
            PlaceTo(s, t2, C.SCX + 1 + floor(Hash(n + 47) * 3), C.SCY + 13)
            SetAlphaOf(t2, Hash(n + 49) < 0.5 and 1 or 0.4)
        end
        SetOn(s.tips[1], true); SetOn(s.tips[2], true)
    elseif s.crackN ~= nil then
        s.crackN = nil
        for i = 1, 6 do SetOn(s.crack[i], false) end
        SetOn(s.tips[1], false); SetOn(s.tips[2], false)
    end
    -- the cast: eight sparks of three px stepping outward and fading
    if burst then
        local d = C.SR + 1 + sc * 40
        local fade = 1 - sc / C.CAST_BURST
        for i = 1, 8 do
            for j = 0, 2 do
                local px = s.burst[(i - 1) * 3 + j + 1]
                local dd = d - j * 2
                PlaceTo(s, px, floor(C.SCX + BURST_COS[i] * dd + 0.5), floor(C.SCY + BURST_SIN[i] * dd + 0.5))
                SetAlphaOf(px, fade * (1 - j * 0.3))
                SetOn(px, true)
            end
        end
        s.burstOn = true
    elseif s.burstOn then
        s.burstOn = false
        for i = 1, 24 do SetOn(s.burst[i], false) end
    end
    -- the ready beat: a stepped ring, alternating cyan and white, growing and fading
    SetOn(s.ringG, ringOn)
    if ringOn then
        local k = (sr - C.RDY_RING_FROM) / (C.RDY_BEAT - C.RDY_RING_FROM)
        local r = C.SR + 1 + k * 18
        SetAlphaOf(s.ringG, (1 - k) * 0.9)
        for i = 1, 72 do
            PlaceTo(s, s.rdyRing[i], floor(C.SCX + RING_COS[i] * r), floor(C.SCY + RING_SIN[i] * r))
        end
    end
end

local function PaintLabel(s, g, known, unk, ready, now, rdyBeat, sr)
    local K = s.colors
    SetOn(s.label, known)
    if not known then return end
    if unk then
        SetLabel(s.label, "?")
        TextTint(s.label, K.muted, 1)
    elseif ready then
        SetLabel(s.label, "RDY")
        TextTint(s.label, (rdyBeat and sr < C.RDY_LABEL) and K.white or K.cyan, 1)
    else
        local rem = g.endsAt and (g.endsAt - now) or g.rem or 0
        SetLabel(s.label, FormatRemaining(rem, g.est))
        TextTint(s.label, K.white, 1)
    end
end

local function PaintShock(s, now, restart)
    local g = s.shock
    local mode = g.mode
    local known, unk, ready, charging = mode ~= "none", mode == "unknown", mode == "ready", mode == "charging"
    if s.prevMode ~= mode then
        if ready and s.prevMode == "charging" then s.rdyAt = now end          -- the cooldown just ended while we watched
        s.prevMode = mode
    end
    -- the beats run on our own clock: the player's cast ledger, and the moment a charge ran out
    local sc, sr = 99, 99
    if known and not unk and g.lastAt and now >= g.lastAt then sc = now - g.lastAt end
    if ready and s.rdyAt and now >= s.rdyAt then sr = now - s.rdyAt end
    local casting = charging and sc < C.DRAIN
    local rdyBeat = ready and sr < C.RDY_BEAT
    local flash = (rdyBeat and sr < C.RDY_FLASH) or (known and not unk and sc < C.CAST_FLASH)
    local burst = known and not unk and sc < C.CAST_BURST
    local h = 0
    if ready then h = floor(Beat(now, C.BREATH) * 20) / 20 end
    PaintDisc(s, known, unk, ready, flash, h)
    PaintFill(s, s, SHOCK_D, now, g, charging and not casting, casting, sc, restart)
    PaintFx(s, now, ready, burst, sc, rdyBeat and sr >= C.RDY_RING_FROM, sr)
    PaintLabel(s, g, known, unk, ready, now, rdyBeat, sr)
end

-- Whether a Fire totem stands: what the poles said, else Fire Nova's own usability (a mana shortfall is not a missing totem).
local function FireUp(s)
    if s.fireUp ~= nil then return s.fireUp end
    local g = s.nova
    local fn = C_Spell and C_Spell.IsSpellUsable
    if not (fn and g.id) then return true end
    local ok, usable, noMana = pcall(fn, g.id)
    if not ok or IsSecret(usable) or IsSecret(noMana) then return true end
    if usable == false and noMana ~= true then return false end
    return true
end

-------------------------------------------------------------------------------
-- The Fire Nova flame disc (the shock disc's twin: smaller, in fire, a pixel flame for the glyph)
-------------------------------------------------------------------------------

-- Everything off, and the state that only means something while it is drawn forgotten: a disc that comes back (the Fire totem is
-- up again, the view is shown again) has no beat for what it did not see, and its engine timer is fed again.
local function HideNova(f)
    local list = f.regions
    for i = 1, #list do SetOn(list[i], false) end
    f.prevMode, f.rdyAt = nil, nil
    f.running, f.barTimer, f.draining, f.drainStart, f.drainValue, f.barValue = nil, nil, nil, nil, nil, nil
end

-- The plate, the washes, the rim's lit look, the flame's bodies and the flickering tips
local function PaintNovaDisc(f, now, ready, unk, flash, h)
    local A, F, W = C.AMBER, C.FIRE, C.HOT
    SetOn(f.disc, true); SetOn(f.rimDim, true); SetOn(f.notches, true)
    SetOn(f.halo1, ready); SetOn(f.halo2, ready)
    if ready then
        TintRGB(f.halo1, A[1], A[2], A[3], C.NHALO1 + h * C.NHALO1_B)
        TintRGB(f.halo2, F[1], F[2], F[3], C.NHALO2 + h * C.NHALO2_B)
    end
    -- the plate's wash: hot white at the flash, fire red breathing when ready (an overlay, the mockup mixes the plate's colour)
    if flash then
        TintRGB(f.tint, W[1], W[2], W[3], C.NFLASH_WASH)
    elseif ready then
        TintRGB(f.tint, F[1], F[2], F[3], C.NWASH + h * C.NWASH_B)
    end
    SetOn(f.tint, flash or ready)
    -- the lit rim over the whole ring: hot white at the flash, amber to hot white with the breath when ready
    if flash then
        TintRGB(f.rimLit, W[1], W[2], W[3], C.NRIM_A)
    elseif ready then
        local t = (h - C.NRIM_BREATH) * C.NRIM_MIX
        if t < 0 then t = 0 end
        TintRGB(f.rimLit, A[1] + (W[1] - A[1]) * t, A[2] + (W[2] - A[2]) * t, A[3] + (W[3] - A[3]) * t, C.NRIM_A)
    end
    SetOn(f.rimLit, flash or ready)
    -- the flame: dark while charging (the engine's lit flame climbs over it), ready, muted when unknown, hot white at a flash
    SetOn(f.flameEmpty, not unk and not ready)
    SetOn(f.flameMuted, unk)
    SetOn(f.flameReady, ready)
    SetOn(f.flameWhite, flash)
    -- the tips flicker: one of three overlays, stepping a few times a second
    local fl = floor(now * C.NFLICK_RATE) % C.NFLICK_PHASES
    for p = 1, C.NFLICK_PHASES do SetOn(f.flick[p], ready and p - 1 == fl) end
end

-- The drifting embers, the fire ring a cast throws and the smaller ring of the cooldown's end (rings: 80 px, two stepped alternating
-- colours, growing and fading; each is a frame carrying the alpha)
local function PaintNovaFx(s, f, now, ready, castOn, sc, readyOn, sr)
    for k = 0, C.NEMBERS - 1 do
        local px = f.embers[k + 1]
        SetOn(px, ready)
        if ready then
            local t = now * C.NEMBER_RATE + k / 3
            local ph = t % 1
            PlaceTo(s, px, C.NCX - C.NEMBER_X + floor(Hash(k * C.NEMBER_SEED + floor(t) * C.NEMBER_SEED2) * C.NEMBER_W),
                C.NCY - C.NR - C.NEMBER_DY - floor(ph * C.NEMBER_RISE))
            SetAlphaOf(px, 1 - ph)
            Tint(px, ph < C.NEMBER_SPLIT and C.AMBER or C.FIRE, 1)
        end
    end
    SetOn(f.castA, castOn); SetOn(f.castB, castOn)
    if castOn then
        local k = sc / C.NCAST_BEAT
        local r = C.NR + 1 + k * C.NCAST_GROW
        local r2 = r - C.NCAST_GAP
        SetAlphaOf(f.castA, (1 - k) * C.NCAST_A)
        SetAlphaOf(f.castB, (1 - k) * C.NCAST_A2)
        local pa, pb = f.castPxA, f.castPxB
        for i = 1, C.NRING_PX do
            local co, si = NRING_COS[i], NRING_SIN[i]
            PlaceTo(s, pa[i], floor(C.NCX + co * r), floor(C.NCY + si * r))
            PlaceTo(s, pb[i], floor(C.NCX + co * r2), floor(C.NCY + si * r2))
        end
    end
    SetOn(f.readyG, readyOn)
    if readyOn then
        local k = (sr - C.NRDY_RING_FROM) / C.NRDY_RING_SPAN
        local r = C.NR + 1 + k * C.NRDY_GROW
        SetAlphaOf(f.readyG, (1 - k) * C.NRDY_RING_A)
        local pr = f.readyPx
        for i = 1, C.NRING_PX do
            PlaceTo(s, pr[i], floor(C.NCX + NRING_COS[i] * r), floor(C.NCY + NRING_SIN[i] * r))
        end
    end
end

-- RDY (amber, hot white for the first moments of the ready beat), the seconds in white ("~" for an estimate), "?" muted
local function PaintNovaLabel(s, f, g, unk, ready, now, rdyBeat, sr)
    local K, fs = s.colors, f.label
    SetOn(fs, true)
    if unk then
        SetLabel(fs, "?")
        TextTint(fs, K.muted, 1)
    elseif ready then
        SetLabel(fs, "RDY")
        TextTint(fs, (rdyBeat and sr < C.NRDY_LABEL) and C.HOT or C.AMBER, 1)
    else
        local rem = g.endsAt and (g.endsAt - now) or g.rem or 0
        SetLabel(fs, FormatRemaining(rem, g.est))
        TextTint(fs, K.white, 1)
    end
end

-- `fresh` re-reads whether the disc may show (the poles' word, else Fire Nova's usability: a call to the client, so only with the
-- cooldown's tenth of a second); the frames between only animate
local function PaintNova(s, now, fresh, restart)
    local f, g = s.fd, s.nova
    if fresh then f.show = g.known and FireUp(s) end
    if not f.show then
        if f.on then f.on = false; HideNova(f) end
        return
    end
    f.on = true
    local mode = g.mode
    local unk, ready, charging = mode == "unknown", mode == "ready", mode == "charging"
    if f.prevMode ~= mode then
        if ready and f.prevMode == "charging" then f.rdyAt = now end         -- the cooldown just ended while we watched
        f.prevMode = mode
    end
    -- the beats run on our own clock: the player's cast ledger, and the moment a charge ran out
    local sc, sr = 99, 99
    if not unk and g.lastAt and now >= g.lastAt then sc = now - g.lastAt end
    if ready and f.rdyAt and now >= f.rdyAt then sr = now - f.rdyAt end
    local casting = charging and sc < C.NDRAIN
    local rdyBeat = ready and sr < C.NRDY_BEAT
    local flash = (rdyBeat and sr < C.NRDY_FLASH) or (not unk and sc < C.NCAST_FLASH)
    local h = 0
    if ready then h = floor(Beat(now, C.NBREATH) * 20) / 20 end
    PaintNovaDisc(f, now, ready, unk, flash, h)
    PaintFill(s, f, NOVA_D, now, g, charging and not casting, casting, sc, restart)
    PaintNovaFx(s, f, now, ready, not unk and sc < C.NCAST_BEAT, sc, rdyBeat and sr >= C.NRDY_RING_FROM, sr)
    PaintNovaLabel(s, f, g, unk, ready, now, rdyBeat, sr)
end

-------------------------------------------------------------------------------
-- The live layer
-------------------------------------------------------------------------------

local Sync

local function Refresh(s, now, restart)
    now = now or GetTime()
    ReadGroup(s.shock, now)
    ReadGroup(s.nova, now)
    PaintShock(s, now, restart)
    PaintNova(s, now, true, restart)
    Sync(s)
end

-- a ready shock breathes and a charging one counts down; so does a ready Fire Nova (while its disc shows) and a charging one
local function NeedsTick(s)
    local m = s.shock.mode
    if m == "ready" or m == "charging" then return true end
    m = s.nova.mode
    return s.fd.show == true and (m == "ready" or m == "charging")
end

-- the frames between two reads: both discs animate from the last read
local function PaintAnim(s, now)
    PaintShock(s, now, false)
    PaintNova(s, now, false, false)
end

local function Tick(frame)
    local s = frame.fsSection
    if not (s and s.live) then return end
    local now = GetTime()
    if now - s.lastAnim < C.ANIM then return end
    s.lastAnim = now
    local ok, err
    if now - s.lastRead >= C.TICK then
        s.lastRead = now
        ok, err = pcall(Refresh, s, now, false)
    else
        ok, err = pcall(PaintAnim, s, now)
    end
    if not ok then
        LogOnce("tick", "tick failed: " .. tostring(err))
        s.holder:SetScript("OnUpdate", nil)
        s.ticking = false
    end
end

Sync = function(s)
    local need = s.live and NeedsTick(s)
    if need and not s.ticking then
        s.ticking, s.lastAnim, s.lastRead = true, GetTime(), GetTime()
        s.holder:SetScript("OnUpdate", Tick)
    elseif not need and s.ticking then
        s.ticking = false
        s.holder:SetScript("OnUpdate", nil)
    end
end

local function ResolveAll(s)
    ResolveGroup(s.shock)
    ResolveGroup(s.nova)
end

local function Reread(s, restart)
    if not s.live then return end
    local ok, err = pcall(Refresh, s, nil, restart)
    if not ok then LogOnce("refresh", "refresh failed: " .. tostring(err)) end
end

local BOOK_EVENTS = { SPELLS_CHANGED = true, LEARNED_SPELL_IN_SKILL_LINE = true, PLAYER_LEVEL_UP = true }
local COOLDOWN_EVENTS = { SPELL_UPDATE_COOLDOWN = true, SPELL_UPDATE_USABLE = true, PLAYER_REGEN_ENABLED = true, PLAYER_REGEN_DISABLED = true }

local function OnViewEvent(s, event)
    if not s.live then return end
    if BOOK_EVENTS[event] then
        ResolveAll(s)
        Reread(s, true)
    elseif COOLDOWN_EVENTS[event] then
        Reread(s, true)
    end
end

-- The player's own casts: any rank of a shock starts the shared cooldown, a Fire Nova its own. A ledger only, kept on through OnHide.
local function OnOwnCast(s, _, _, _, spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local name = SpellNameOf(spellID)
    if not name then return end
    local now = GetTime()
    local hit = false
    for i = 1, 2 do
        local g = i == 1 and s.shock or s.nova
        for _, m in ipairs(g.members) do
            if m.name == name or (m.localName and m.localName == name) then g.lastAt, hit = now, true end
        end
    end
    if hit and s.live then Reread(s, true) end
end

local VIEW_EVENTS = {
    "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP",
    "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED",
}

-- A client refuses an event it does not know: FrameHelpers skips it and records it in the saved variables, no chat line
local function SetViewEvents(s, on)
    local ev = s.events
    if on then
        FS.FrameHelpers.RegisterEvents(ev, VIEW_EVENTS)
    else
        for _, e in ipairs(VIEW_EVENTS) do pcall(ev.UnregisterEvent, ev, e) end
    end
end

-------------------------------------------------------------------------------
-- Build, Seat, OnShow, OnHide
-------------------------------------------------------------------------------

local function NewGroups()
    local list = {}
    for key, def in pairs(GROUPS) do
        local g = { cd = def.cd, len = def.cd, mode = "none", members = {} }
        for i, m in ipairs(def.members) do g.members[i] = { name = m.name, ids = m.ids } end
        list[key] = g
    end
    return list
end

-- A frame that clips its children to one row of the bolt (the shimmer) or to the strip under the fill's edge (the seam), holding a
-- full white cell of the bolt: only the part inside the frame shows, so the row follows the frame.
local function NewClip(s, parent, level, cell, d)
    local clip = CreateFrame("Frame", nil, parent)
    clip:SetFrameLevel(s.level + level)
    clip:EnableMouse(false)
    Clips(clip)
    clip:Hide()
    clip.fsOn = false
    local t = NewCell(s, clip, "ARTWORK", 0, cell, d)
    t.fsOn = true
    t:Show()
    return clip, t
end

local function BuildDisc(s, holder, K)
    local cy, w = K.cyan, C.FX_WHITE
    -- the plate, in the holder: stepped halos, the carved disc, the washes, the dotted ring and the dim rim
    local function halo(i)
        local t = NewPix(holder, "BACKGROUND", i == 0 and 1 or 0, MEDIA .. "shaman_disc_halo.tga")
        t:SetTexCoord(i * 0.5, i * 0.5 + 0.5, 0, 1)
        return Part(s, t, C.SCX - C.HALO / 2, C.SCY - C.HALO / 2, C.HALO, C.HALO)
    end
    s.halo2, s.halo1 = halo(1), halo(0)
    s.disc = NewCell(s, holder, "ARTWORK", 0, "disc", SHOCK_D)
    s.tint = NewCell(s, holder, "ARTWORK", 1, "mask", SHOCK_D)
    s.dots = NewCell(s, holder, "ARTWORK", 2, "dots", SHOCK_D)
    s.rimDim = NewCell(s, holder, "ARTWORK", 3, "rimDim", SHOCK_D)
    -- the engine's rim: a clockwise refill, and the mirrored art that drains clockwise from 12 o'clock after a cast
    s.rimFill = NewSwipe(s, holder, 1, SHOCK_D.rim, true, SHOCK_D)
    s.rimDrain = NewSwipe(s, holder, 1, SHOCK_D.mirror, false, SHOCK_D)
    -- the lit rim, the carved notches, the spark, and the bolt's outline and bodies
    local top = NewLayer(s, holder, 2)
    s.rimLit = NewCell(s, top, "ARTWORK", 0, "rimLit", SHOCK_D)
    s.notches = NewCell(s, top, "ARTWORK", 1, "notches", SHOCK_D)
    s.spark = NewFlat(s, top, "ARTWORK", 2, w)
    s.outline = NewCell(s, top, "ARTWORK", 3, "outline", SHOCK_D)
    s.boltEmpty = NewCell(s, top, "ARTWORK", 4, "boltEmpty", SHOCK_D)
    s.boltMuted = NewCell(s, top, "ARTWORK", 4, "boltMuted", SHOCK_D)
    s.boltReady = NewCell(s, top, "ARTWORK", 4, "boltReady", SHOCK_D)
    -- the bolt's refill (engine) and its cast drain (plain), vertical bars from the bottom
    s.bar = NewBar(s, holder, 3, SHOCK_D)
    s.drain = NewBar(s, holder, 3, SHOCK_D)
    -- over the bars: the white flash and the clipped rows (shimmer, seam)
    local fx = NewLayer(s, holder, 4)
    s.flashBolt = NewCell(s, fx, "ARTWORK", 0, "boltWhite", SHOCK_D)
    s.rows = {}
    local clip, tex
    s.shimA, tex = NewClip(s, fx, 5, "boltWhite", SHOCK_D)
    s.rows[#s.rows + 1] = s.shimA
    s.shimB, tex = NewClip(s, fx, 5, "boltInner", SHOCK_D)
    tex:SetVertexColor(cy[1] + (w[1] - cy[1]) * 0.7, cy[2] + (w[2] - cy[2]) * 0.7, cy[3] + (w[3] - cy[3]) * 0.7, 1)
    s.rows[#s.rows + 1] = s.shimB
    s.seam, clip = NewClip(s, fx, 5, "boltWhite", SHOCK_D)
    -- the sparks: pools of flat 1 px textures in a frame clipped to the mockup's canvas
    local canvas = CreateFrame("Frame", nil, holder)
    canvas:SetFrameLevel(s.level + 6)
    canvas:EnableMouse(false)
    Clips(canvas)
    Part(s, canvas, 0, 0, C.W, C.H)
    s.canvas = canvas
    s.crack, s.tips, s.burst, s.rdyRing = {}, {}, {}, {}
    for k = 0, 1 do
        for i = 0, 2 do
            local px = NewFlat(s, canvas, "ARTWORK", 0, i == 0 and w or cy)
            px:SetAlpha(0.95 - i * 0.2)
            px.fsAl = 0.95 - i * 0.2
            s.crack[k * 3 + i + 1] = px
        end
    end
    s.tips[1] = NewFlat(s, canvas, "ARTWORK", 1, w)
    s.tips[2] = NewFlat(s, canvas, "ARTWORK", 1, cy)
    for i = 1, 8 do
        for j = 0, 2 do s.burst[(i - 1) * 3 + j + 1] = NewFlat(s, canvas, "ARTWORK", 2, j == 0 and w or cy) end
    end
    local ringG = CreateFrame("Frame", nil, canvas)
    ringG:SetAllPoints(canvas)
    ringG:SetFrameLevel(s.level + 7)
    ringG:EnableMouse(false)
    ringG:Hide()
    ringG.fsOn = false
    s.ringG = ringG
    for i = 1, 72 do
        s.rdyRing[i] = NewFlat(s, ringG, "ARTWORK", 0, (i % 2 == 1) and w or cy, true)
    end
end

-- The flame disc's parts (all in section.fd): the plate, the engine's rim and flame fills, the cast drain, the flame's looks, the
-- seam under the fill's edge, the embers, three stepped rings and the label. `regions` lists everything that is shown or hidden as
-- a whole, so the disc can go dark in one loop.
local function BuildNova(s, holder, K, textF)
    local d = NOVA_D
    local f = { show = false, on = false, regions = {}, flick = {}, embers = {}, castPxA = {}, castPxB = {}, readyPx = {} }
    s.fd = f
    local reg = f.regions
    local function track(r) reg[#reg + 1] = r; return r end
    -- the plate, in the holder: stepped halos, the carved disc, the wash and the dim rim
    f.halo2 = track(NewCell(s, holder, "BACKGROUND", 0, "halo2", d))
    f.halo1 = track(NewCell(s, holder, "BACKGROUND", 1, "halo1", d))
    f.disc = track(NewCell(s, holder, "ARTWORK", 0, "disc", d))
    f.tint = track(NewCell(s, holder, "ARTWORK", 1, "mask", d))
    f.rimDim = track(NewCell(s, holder, "ARTWORK", 2, "rimDim", d))
    -- the engine's rim: a clockwise refill, and the mirrored art that drains clockwise from 12 o'clock after a cast
    f.rimFill = track(NewSwipe(s, holder, 1, d.rim, true, d))
    f.rimDrain = track(NewSwipe(s, holder, 1, d.mirror, false, d))
    -- the lit rim, the carved notches, the spark and the flame's bodies and tips
    local top = NewLayer(s, holder, 2)
    f.rimLit = track(NewCell(s, top, "ARTWORK", 0, "rimLit", d))
    f.notches = track(NewCell(s, top, "ARTWORK", 1, "notches", d))
    f.spark = track(NewFlat(s, top, "ARTWORK", 2, C.HOT))
    f.flameEmpty = track(NewCell(s, top, "ARTWORK", 3, "flameEmpty", d))
    f.flameMuted = track(NewCell(s, top, "ARTWORK", 4, "flameMuted", d))
    f.flameReady = track(NewCell(s, top, "ARTWORK", 4, "flameReady", d))
    for p = 1, C.NFLICK_PHASES do f.flick[p] = track(NewCell(s, top, "ARTWORK", 5, "flick" .. (p - 1), d)) end
    -- the flame's refill (engine) and its cast drain (plain), vertical bars from the base
    f.bar = track(NewBar(s, holder, 3, d))
    f.drain = track(NewBar(s, holder, 3, d))
    -- over the bars: the white flash and the seam, a clipped strip of the hot flame hung from the fill's edge
    local fx = NewLayer(s, holder, 4)
    f.flameWhite = track(NewCell(s, fx, "ARTWORK", 0, "flameWhite", d))
    f.seam = track(NewClip(s, fx, 5, "flameWhite", d))
    -- embers, and the stepped rings, in the clipped canvas (the ring a cast throws runs past the mockup's edge)
    local canvas = s.canvas
    for k = 1, C.NEMBERS do f.embers[k] = track(NewFlat(s, canvas, "ARTWORK", 3, C.AMBER)) end
    local function ring(list, c1, c2)
        local g = CreateFrame("Frame", nil, canvas)
        g:SetAllPoints(canvas)
        g:SetFrameLevel(s.level + 7)
        g:EnableMouse(false)
        g:Hide()
        g.fsOn = false
        for i = 1, C.NRING_PX do list[i] = NewFlat(s, g, "ARTWORK", 0, (i % 2 == 1) and c2 or c1, true) end   -- stepRing: even steps c2
        return track(g)
    end
    f.castA = ring(f.castPxA, C.FIRE, C.AMBER)
    f.castB = ring(f.castPxB, C.HOT, C.AMBER)
    f.readyG = ring(f.readyPx, C.AMBER, C.HOT)
    f.label = track(NewText(textF, C.NLABEL_SIZE, "CENTER", K.white))
end

local function BuildSection(frame)
    local s = { ox = 0, oy = 0, live = false, ticking = false, lastRead = 0, lastAnim = 0, groups = NewGroups(), fireUp = nil,
        parts = {}, pool = {} }
    s.shock, s.nova = s.groups.shock, s.groups.nova
    s.colors = {
        cyan = Tok("COLOR_POWER", { 0.133, 0.878, 1, 1 }),
        muted = Tok("COLOR_MUTED", { 0.6157, 0.5765, 0.7686, 1 }), white = Tok("COLOR_TEXT_WHITE", { 1, 1, 1, 1 }),
        violet = Tok("COLOR_BORDER", { 0.659, 0.333, 0.969, 1 }), scrim = Tok("COLOR_HUD_SCRIM", { 0.051, 0.024, 0.125, 1 }),
    }
    local K = s.colors
    local cy, wh = K.cyan, C.FX_WHITE
    -- the flash wash: cyan at .7 and then white at .25 over the plate is .775 of one colour (.525 cyan + .25 white) / .775
    s.flashRGB = { (0.525 * cy[1] + 0.25 * wh[1]) / 0.775, (0.525 * cy[2] + 0.25 * wh[2]) / 0.775, (0.525 * cy[3] + 0.25 * wh[3]) / 0.775 }

    local holder = CreateFrame("Frame", nil, frame)
    holder:SetAllPoints(frame)
    holder:EnableMouse(false)
    holder.fsSection = s
    s.holder = holder
    s.level = holder:GetFrameLevel()

    BuildDisc(s, holder, K)

    -- the label under the disc, on the top frame so the beats never cover it
    local textF = NewLayer(s, holder, 8)
    s.label = NewText(textF, C.LABEL_SIZE, "CENTER", K.white)

    -- Fire Nova: the flame disc under the shock disc, its label on the same top frame
    BuildNova(s, holder, K, textF)

    -- the view events (off until OnShow) and the player's cast ledger (on from here)
    local ev = CreateFrame("Frame", nil, holder)
    ev:SetScript("OnEvent", function(_, event) OnViewEvent(s, event) end)
    s.events = ev
    local rec = CreateFrame("Frame", nil, holder)
    rec:SetScript("OnEvent", function(_, event, ...) OnOwnCast(s, event, ...) end)
    FS.FrameHelpers.RegisterEvent(rec, "UNIT_SPELLCAST_SUCCEEDED", "player")     -- a refusal is recorded, never printed
    s.recorder = rec

    -- the poles' word on the Fire totem; the old ring rode the Fire head, so the head's place (a second argument) is ignored
    s.SetFire = function(up)
        if up == nil or up == true or up == false then s.fireUp = up end
        if s.live then Reread(s, false) end
    end
    s.built = true
    return s
end

-- Hangs a seam clip from the top edge of a bar's fill texture (two anchors and a height); false when the bar has no fill texture
local function HangSeam(seam, bar, height)
    local fill = bar.GetStatusBarTexture and bar:GetStatusBarTexture()
    if not fill then return false end
    seam:ClearAllPoints()
    seam:SetPoint("TOPLEFT", fill, "TOPLEFT", 0, 0)
    seam:SetPoint("TOPRIGHT", fill, "TOPRIGHT", 0, 0)
    seam:SetHeight(height)
    return true
end

local function SeatSection(s, rect)
    s.ox, s.oy = rect.x, rect.y
    local k = ui(1)
    -- every fixed part: the disc's cells and halos, the rim's cooldowns, the bolt's bars, the canvas the sparks are clipped to
    for i = 1, #s.parts do
        local r = s.parts[i]
        At(s, r, "TOPLEFT", r.fsX, r.fsY)
        r:SetSize(r.fsW * k, r.fsH * k)
    end
    -- the moving px forget where they were (their anchors are from the old origin): the next paint places them
    for i = 1, #s.pool do
        local r = s.pool[i]
        r:SetSize(k, k)
        r.fsX, r.fsY = false, false
    end
    s.shimRy, s.crackN = nil, nil
    for i = 1, #s.rows do s.rows[i]:SetSize(C.CELL * k, k) end
    -- each seam hangs from its fill's top edge and is a little over a px tall
    s.noSeam = not HangSeam(s.seam, s.bar, C.SEAM * k)
    s.fd.noSeam = not HangSeam(s.fd.seam, s.fd.bar, C.NSEAM * k)
    if s.noSeam or s.fd.noSeam then LogOnce("noseam", "a fill has no texture to hang its seam from") end
    SeatFont(s.label, C.LABEL_SIZE, s.colors.white)
    At(s, s.label, "CENTER", C.LABEL_X, C.LABEL_BASE - C.CAP * C.LABEL_SIZE)
    SeatFont(s.fd.label, C.NLABEL_SIZE, s.colors.white)
    At(s, s.fd.label, "CENTER", C.NCX, C.NCY + C.NR + C.NLABEL_DY - C.CAP * C.NLABEL_SIZE)
    if s.live then PaintAnim(s, GetTime()) end
end

local Shocks = {}
FS.GunsightShamanShocks = Shocks

function Shocks.Build(frame)
    local ok, result = pcall(BuildSection, frame)
    if ok then return result end
    LogOnce("build", "build failed: " .. tostring(result))
    return { built = false }
end

function Shocks.Seat(s, rect, scale)
    if type(s) ~= "table" or not s.built then return end
    if type(rect) ~= "table" or type(rect.x) ~= "number" or type(rect.y) ~= "number" or IsSecret(rect.x) or IsSecret(rect.y) then return end
    local ok, err = pcall(SeatSection, s, rect)
    if not ok then LogOnce("seat", "seat failed: " .. tostring(err)) end
end

function Shocks.OnShow(s)
    if type(s) ~= "table" or not s.built then return end
    s.live = true
    ResolveAll(s)
    s.prevMode, s.running, s.barTimer, s.rdyAt = nil, nil, nil, nil     -- no beat for what happened while hidden
    s.fd.prevMode, s.fd.running, s.fd.barTimer, s.fd.rdyAt = nil, nil, nil, nil
    SetViewEvents(s, true)
    Reread(s, true)
end

function Shocks.OnHide(s)
    if type(s) ~= "table" or not s.built then return end
    s.live = false
    SetViewEvents(s, false)
    if s.ticking then
        s.ticking = false
        s.holder:SetScript("OnUpdate", nil)
    end
end
