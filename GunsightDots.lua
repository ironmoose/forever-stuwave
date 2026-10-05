-- Forever Synthwave: Gunsight DoT time scale (piece key "dot").
--
-- The enemy side of the Gunsight HUD (mockups/gunsight-hud-v2-2026-10-02/
-- gunsight-hud-v2-2026-10-02.html, drawDots): a 0 to 30 second altitude axis, an amber refresh
-- band for the last 3 seconds, four dashed lane guides, and one cut-corner chip per DoT that
-- slides down the scale toward the band like a note on a rhythm game highway. Recast it when it
-- lands. gunsight-harness.py parses the mockup constants for Gunsight.lua; gunsightdots-harness.py
-- does the same for the numbers below, so a mockup edit fails there instead of drifting.
--
-- DATA. The HudLogic DoT ledger is the only combat-safe source (aura timers are secret in combat,
-- and this file never reads an aura): each row of FS.Hud.GetState() that belongs to a DoT of the
-- class profile carries `remaining`, `expiresAt` (an absolute GetTime) and `duration`. A DoT row
-- whose fields are all nil is UNKNOWN and draws nothing; `remaining == 0` (or an expiry in the
-- past) is ABSENT and draws a dim hollow chip resting at 0. Lanes follow the profile's own row
-- order, at most four, so a priest gets two and a warlock four.
--
-- LOCKED LOOK, with one rule on top (Parker, 2026-10-03): the absent chip is the mockup's dim hollow
-- "DoT not on the target, recast it" cue, and it shows ONLY while the player is in combat. Parker:
-- "dim recast, it i am not in combat it should hide." Out of combat an absent chip is hidden (its look
-- stays seated, only its visibility goes), a live ticking chip is never touched by this, and the scale
-- gate (FS.TargetTakesDots) is unchanged.
--
-- "IN COMBAT" is a file-local flag driven by the events, not a live InCombatLockdown() read. Nothing in this
-- repo or the Blizzard UI source settles whether InCombatLockdown() is already true inside the
-- PLAYER_REGEN_DISABLED handler (it is widely documented as still false there: the event fires just before
-- lockdown begins, which is why secure work is still legal in it; CombatHud.lua says HudLogic's
-- UnitAffectingCombat flips "a beat before" lockdown too), and Blizzard's own LowHealthFrame keeps a flag set
-- from these two events rather than reading the API (LowHealthFrame.lua:24-25 registers them, :34-37 hands
-- them to SetInCombat, :172-180 stores self.inCombat). So the flag is the rule and it holds under either
-- ordering: PLAYER_REGEN_DISABLED sets it true, PLAYER_REGEN_ENABLED sets it false, and each re-evaluates the
-- absent chips at once instead of waiting for a Hud push. The flag is seeded at build and on
-- PLAYER_ENTERING_WORLD (a /reload or a zoning mid-fight fires no REGEN event) from InCombatLockdown() OR
-- UnitAffectingCombat("player"), each pcall'd and secret-guarded; it reads as out of combat only when BOTH
-- answers are plain false; a throwing, secret or missing answer reads as in combat, so the cue is never hidden
-- on a guess.
-- It is NOT OR-ed with a live InCombatLockdown() on read: that would keep the cue up through a
-- PLAYER_REGEN_ENABLED dispatch if lockdown lifted a beat after the event.
-- One-way self-heal: a missed PLAYER_REGEN_ENABLED would leave the flag true until the next pull, so a Hud push
-- whose state.inCombat (HudLogic's InCombatLockdown() alone, fail closed) is plainly false while the flag is
-- true re-runs the seed, and the flag clears only if BOTH APIs then read plainly false (lockdown alone can lag
-- UnitAffectingCombat). The Hud never sets the flag true: REGEN_DISABLED and the seed own "true".
--
-- MOTION. Hud pushes are coarse (once a second), so a chip is placed from expiresAt - GetTime()
-- by ONE OnUpdate on the piece frame, installed only while at least one chip is live and cleared
-- the moment the last one expires. Nothing is allocated per frame and a steady chip writes
-- nothing. A chip that runs out turns into the absent chip by itself, because the ledger pushes
-- nothing at an expiry (Signature floors `remaining`).
--
-- CHIP. The 24 image px square is built the way the action buttons are: a dark plate behind the
-- icon, the icon seated inside the cut by FrameHelpers.SeatAuraTile, the cut ring over it
-- (Theme.SkinButton, violet; amber with a pulsing glow inside the band). Masks do not clip on
-- this client, so unlike the mockup (icon clipped to the cut, edge to edge) the icon is inset
-- ceil(chamfer / 2) like every other tile, which keeps its square corners under the stroke.
-- A white cut-shaped pop flashes for 0.35 s when the DoT is (re)applied.
--
-- TARGET LAYER. With no target the whole scale hides ("if no target ... hide ... dot timers"). The same goes
-- for a target no DoT of ours can be on: a friendly or otherwise unattackable unit, and a dead one. The ledger
-- cannot say either (it reads a GUID it never saw as "absent", and nothing tells it a corpse took its DoTs
-- with it), so without this a dim hollow chip rested at 0 under a friendly target and a corpse's chip slid
-- down and then sat there ("a dot stays"). That is a SEPARATE layer from the piece toggle (Gunsight.SetPiece
-- is the user's on/off setting and drives the console key LED, so it is never used for this): `gate`, a plain
-- child of the piece frame (at the piece frame's own level, so `content` keeps the stacking it had there) that
-- holds `content`, is shown while the target can carry our DoTs and hidden while not, driven by
-- PLAYER_TARGET_CHANGED and PLAYER_ENTERING_WORLD (and read once at build) plus UNIT_HEALTH, UNIT_FLAGS and
-- UNIT_FACTION for the target only (death, a duel or mind control changes the answer with no target change).
-- A visible chip therefore needs the piece ON and such a target. The target rule is FS.TargetTakesDots (Theme.lua,
-- shared with the horizon's dot segment in GunsightFrame): FS.HasTarget plus plain UnitIsDeadOrGhost / UnitCanAttack
-- answers; a secret, throwing or missing answer reads as "can take a DoT" and keeps the scale shown, like HasTarget.
-- Show/Hide of the gate is legal in combat (a plain addon frame, nothing protected parented under it) and it
-- adds no OnUpdate. The Hud ledger keeps running while the gate is hidden, only the visuals go.
--
-- Not drawn on purpose: the mockup's "PENDING PROBE" tag (decided), and the horizon segment
-- that leads into this scale, which belongs to the frame lane.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.RegisterPiece) then return end

FS.GunsightDots = FS.GunsightDots or {}
local Dots = FS.GunsightDots

local G = Gunsight.G
local ui, Point = Gunsight.ui, Gunsight.Point

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightdots-harness.py re-reads them from drawDots)
-------------------------------------------------------------------------------

local TOP, BOT, DOT_AX, DOT_END, LANE, CX, CY = G.TOP, G.BOT, G.DOT_AX, G.DOT_END, G.LANE, G.CX, G.CY

local D = {
    CHS = 24,                  -- CHS: the chip is a 24 image px square
    MAX_S = 30,                -- secY: the scale runs 0 to 30 s
    BAND_S = 3,                -- yb = secY(3): the refresh band
    BAND_FILL = 0.16,          -- band fill alpha
    AX_UP = 4, AX_DN = 4,      -- axis runs from TOP - 4 to BOT + 4
    HDR_Y = 488,               -- header('DOT TIME', DOT_AX, 488)
    MAJ = 5,                   -- a long tick and a label every 5 s
    MAJ_LEN = 10, MIN_LEN = 5, -- tick lengths
    LABEL_DX = 6,              -- labels at DOT_AX + 6
    REFRESH_DX = 14,           -- REFRESH label at DOT_END + 14
    POP_S = 0.35, POP_A = 0.8, -- pop: 0.35 s, white at .8 fading out
    GUIDE_DASH = { 2, 6 },     -- lane guide dash and gap
    BAND_DASH = { 5, 4 },      -- band top line dash and gap
    MAX_LANES = #LANE,
    COLORS = {                 -- the mockup's :root tokens
        violet = { 168 / 255, 85 / 255, 247 / 255 },    -- #a855f7 --violet
        amber = { 255 / 255, 182 / 255, 72 / 255 },     -- #ffb648 --amber
        fg = { 233 / 255, 226 / 255, 255 / 255 },       -- #e9e2ff --fg
        muted = { 157 / 255, 147 / 255, 196 / 255 },    -- #9d93c4 --muted
        white = { 243 / 255, 251 / 255, 255 / 255 },    -- #f3fbff --white
    },
}
Dots.D = D
local K = D.COLORS

local CHP = D.CHS / 2
local LINE = G.LINE or 1.3             -- hairline weight in image px (the mockup's LW is about 1.9)
local RAIL_CORE, RAIL_GLOW, DOT_BLOOM = 2.6, 7, 9
local REAPPLY_EPS = 0.5                -- an expiry this much later than the last one is a reapply
local FRESH_EPS = 0.5                  -- on a new target, a row this close to its full duration was applied just now
local GLOW_BASE, GLOW_BAND = 0.25, 0.45
local MEDIA = "Interface\\AddOns\\ForeverSynthwave\\media\\"
local GLOW_ROUND = MEDIA .. "glow_round.tga"
local ABBR = {
    corruption = "CO", bane_agony = "CA", bane_doom = "CD", immolate = "IM", siphon = "SL",
    sw_pain = "SW", dplague = "DP", wrack = "WR",
}

local function SecY(s)
    return BOT - s / D.MAX_S * (BOT - TOP)
end

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end
local ABSENT_RING = Mix(K.muted, { 1, 1, 1 }, 0.25)       -- mix(K.muted, '#ffffff', .25)
local WARM_PLATE = { 1, 0.88, 0.7 }                       -- the plate warms inside the band

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightdots_" .. key,
            "|cffff4488ForeverSynthwave|r: gunsight dots: " .. tostring(msg))
    end
end

local built, pieceOn, ticking, subscribed = false, false, false, false
local gateOn                   -- the last answer written to the gate (nil until the first read)
local lastEpoch                -- state.targetEpoch of the last push (a plain integer, or nil)
local frame, content, gate
local chips = {}
local parts = {}
local seats = {}           -- closures re-run by every rescale

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

-- A plain finite number or nil: a secret, a string or a NaN reads as unknown.
local function Num(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v then return nil end
    return v
end

-- True while the player is in combat: the event-driven flag from the header. The initial true is only a
-- placeholder: BuildAll calls SeedCombat before the event frame exists, and a chip is built in mode "off" (it
-- reads the flag only once a push makes it absent), so the seed always overwrites it before any paint.
local inCombat = true
local function InCombat() return inCombat end

-- One boolean answer: true, false, or nil when it throws, is secret or the API is missing.
local function ReadCombat(fn, ...)
    local ok, r = pcall(fn, ...)
    if not ok or (FS.IsSecret and FS.IsSecret(r)) then return nil end
    return r and true or false
end

-- Re-read the flag from the API. Either API answering true is in combat (they flip a beat apart); it is out of
-- combat only when both plainly answer false.
local function SeedCombat()
    local lock = ReadCombat(InCombatLockdown)
    local aff = ReadCombat(UnitAffectingCombat, "player")
    inCombat = not (lock == false and aff == false)
end

-------------------------------------------------------------------------------
-- Static scale
-------------------------------------------------------------------------------

local function Tex(layer, sub)
    return content:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
end

-- A horizontal line from x0 to x1 (image px) centred on y, `th` image px thick.
local function HLine(y, x0, x1, c, a, th, layer, sub)
    local t = Tex(layer, sub)
    t:SetColorTexture(c[1], c[2], c[3], a)
    Seat(function()
        Point(t, "LEFT", x0, y)
        t:SetSize(ui(x1 - x0), ui(th))
    end)
    return t
end

-- A vertical line at x from y0 down to y1.
local function VLine(x, y0, y1, c, a, th, layer, sub)
    local t = Tex(layer, sub)
    t:SetColorTexture(c[1], c[2], c[3], a)
    Seat(function()
        Point(t, "TOP", x, y0)
        t:SetSize(ui(th), ui(y1 - y0))
    end)
    return t
end

local function HDashes(y, x0, x1, dash, c, a, th)
    local list, x = {}, x0
    while x < x1 - 1e-6 do
        list[#list + 1] = HLine(y, x, math.min(x1, x + dash[1]), c, a, th)
        x = x + dash[1] + dash[2]
    end
    return list
end

local function VDashes(x, y0, y1, dash, c, a, th)
    local list, y = {}, y0
    while y < y1 - 1e-6 do
        list[#list + 1] = VLine(x, y, math.min(y1, y + dash[1]), c, a, th)
        y = y + dash[1] + dash[2]
    end
    return list
end

-- A text region seated by `anchor` at an image coordinate, restyled at every rescale.
local function Label(text, size, c, a, anchor, x, y, layer)
    local fs = content:CreateFontString(nil, layer or "ARTWORK")
    fs:SetJustifyH("LEFT")
    Seat(function()
        FS.Theme.ApplyMono(fs, ui(size), { c[1], c[2], c[3], a })
        Point(fs, anchor, x, y)
    end)
    -- After Seat, which runs once at once and so sets the font: SetText on a FontString with none throws "Font not set".
    fs:SetText(text)
    return fs
end

local function BuildScale()
    local yb = SecY(D.BAND_S)

    -- refresh band: fill, dashed top line, solid bottom line with a faint bloom under it
    local band = Tex("BACKGROUND")
    band:SetColorTexture(K.amber[1], K.amber[2], K.amber[3], D.BAND_FILL)
    Seat(function()
        Point(band, "TOPLEFT", DOT_AX, yb)
        band:SetSize(ui(DOT_END - DOT_AX), ui(BOT - yb))
    end)
    parts.band = band
    parts.bandTop = HDashes(yb, DOT_AX, DOT_END, D.BAND_DASH, K.amber, 0.75, LINE)
    parts.bandGlow = HLine(BOT, DOT_AX, DOT_END, K.amber, 0.2, LINE * 4)
    parts.bandBottom = HLine(BOT, DOT_AX, DOT_END, K.amber, 0.95, LINE * 1.3)

    -- the REFRESH label runs bottom to top in the mockup; Lua cannot rotate text, so it is stacked
    -- upright letters centred on the band, top to bottom
    parts.refresh = {}
    local word = "REFRESH"
    local pitch = 7.5
    for i = 1, #word do
        local dy = (i - (#word + 1) / 2) * pitch
        parts.refresh[i] = Label(word:sub(i, i), 10, K.amber, 0.8, "CENTER", DOT_END + D.REFRESH_DX, (yb + BOT) / 2 + dy)
    end

    -- lane guides
    parts.guides = {}
    for lane = 1, D.MAX_LANES do
        parts.guides[lane] = VDashes(LANE[lane], TOP, BOT, D.GUIDE_DASH, K.violet, 0.2, LINE)
    end

    -- axis, ticks and labels
    parts.axis = VLine(DOT_AX, TOP - D.AX_UP, BOT + D.AX_DN, K.violet, 0.85, LINE)
    parts.ticks, parts.labels = {}, {}
    for s = 0, D.MAX_S do
        local y = SecY(s)
        local maj = s % D.MAJ == 0
        local len = maj and D.MAJ_LEN or D.MIN_LEN
        parts.ticks[s + 1] = HLine(y, DOT_AX - len, DOT_AX, K.violet, 0.7, LINE)
        if maj then
            parts.labels[s] = Label(tostring(s), 12, K.fg, 0.9, "LEFT", DOT_AX + D.LABEL_DX, y)
        end
    end

    parts.header = Label("DOT TIME", 11, K.violet, 0.9, "BOTTOMLEFT", DOT_AX, D.HDR_Y + 2.5)
end

-------------------------------------------------------------------------------
-- Chips
-------------------------------------------------------------------------------

local function Gradient(tex, c, aBottom, aTop)
    if tex.SetGradient and CreateColor then
        tex:SetColorTexture(1, 1, 1, 1)
        tex:SetGradient("VERTICAL", CreateColor(c[1], c[2], c[3], aBottom), CreateColor(c[1], c[2], c[3], aTop))
    else
        tex:SetColorTexture(c[1], c[2], c[3], aTop)
    end
end

local function Desaturate(tex, on)
    if tex.SetDesaturated then
        tex:SetDesaturated(on)
        tex:SetVertexColor(1, 1, 1, 1)
    elseif on then
        tex:SetVertexColor(0.55, 0.55, 0.55, 1)
    else
        tex:SetVertexColor(1, 1, 1, 1)
    end
end

local function SetRailColor(chip, name)
    if chip.railColor == name then return end
    chip.railColor = name
    local c = name == "amber" and K.amber or K.violet
    Gradient(chip.rail, c, 0.35, 1)
    Gradient(chip.railGlow, c, 0.35 * 0.22, 0.22)
    local w = Mix(c, { 1, 1, 1 }, 0.5)             -- mix(col, '#ffffff', .5)
    chip.dot:SetVertexColor(w[1], w[2], w[3], 1)
end

local function HideRail(chip)
    chip.rail:Hide(); chip.railGlow:Hide(); chip.dot:Hide()
end

local function HidePop(chip)
    chip.popAt = nil
    chip.pop:Hide()
end

-- The static look of a chip: mode ("off", "absent", "live") and, when live, the band.
local function ApplyLook(chip)
    local f = chip.frame
    if chip.mode == "off" then
        f:Hide(); HideRail(chip); HidePop(chip)
        return
    end
    local skin = f.fsSkin
    if chip.mode == "absent" then
        -- the recast cue shows only in combat (see the header); out of combat the look stays seated, hidden.
        -- Written only on a change.
        local want = InCombat()
        if f:IsShown() ~= want then f:SetShown(want) end
        -- a dim hollow chip resting at 0: grey desaturated icon, grey ring, no glow, no rail
        Desaturate(f.icon, true)
        f.icon:SetAlpha(0.5)
        if chip.plate then chip.plate:SetAlpha(0.7); chip.plate:SetVertexColor(1, 1, 1, 1) end
        skin.border.ring:SetVertexColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0.9)
        skin.glow:SetVertexColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0)
        chip.label:SetTextColor(ABSENT_RING[1], ABSENT_RING[2], ABSENT_RING[3], 0.9)
        HideRail(chip); HidePop(chip)
        chip.railColor = nil
        return
    end
    f:Show()
    local c = chip.band and K.amber or K.violet
    Desaturate(f.icon, false)
    f.icon:SetAlpha(1)
    if chip.plate then
        local p = chip.band and WARM_PLATE or { 1, 1, 1 }
        chip.plate:SetAlpha(1)
        chip.plate:SetVertexColor(p[1], p[2], p[3], 1)
    end
    skin.border.ring:SetVertexColor(c[1], c[2], c[3], 1)
    skin.glow:SetVertexColor(c[1], c[2], c[3], chip.band and GLOW_BAND or GLOW_BASE)
    local t = chip.band and K.amber or K.white
    chip.label:SetTextColor(t[1], t[2], t[3], 1)
    SetRailColor(chip, chip.band and "amber" or "violet")
end

-- Seats the chip, its rail and the rail's end dot for `rem` seconds left (0 = resting at 0).
local function Place(chip, rem)
    local y = SecY(math.min(math.max(rem, 0), D.MAX_S))
    if chip.y and math.abs(chip.y - y) < 0.02 then return end
    chip.y = y
    local k = ui(1)
    local dx = (chip.x - CX) * k
    chip.frame:SetPoint("CENTER", Gunsight.root, "CENTER", dx, -(y - CY) * k)
    if chip.mode ~= "live" then return end
    -- the rail runs from the chip's lower edge down to 0; inside the last 1.5 s the chip already
    -- covers it, and the dot stays on the chip's lower edge, like the mockup's
    local yt = math.min(BOT, y + CHP)
    chip.dot:SetPoint("CENTER", Gunsight.root, "CENTER", dx, -(yt - CY) * k)
    chip.dot:Show()
    if BOT - yt > 0.5 then
        chip.rail:SetHeight((BOT - yt) * k)
        chip.railGlow:SetHeight((BOT - yt) * k)
        chip.rail:Show(); chip.railGlow:Show()
    else
        chip.rail:Hide(); chip.railGlow:Hide()
    end
end

local function BuildChip(i)
    local Theme, FH = FS.Theme, FS.FrameHelpers
    local chip = { index = i, mode = "off", x = LANE[i] }

    local f = CreateFrame("Frame", nil, content)
    f:SetFrameLevel(content:GetFrameLevel() + 2)
    f:EnableMouse(false)
    f:SetSize(ui(D.CHS), ui(D.CHS))          -- sized first: the chamfer comes from the height
    local icon = f:CreateTexture(nil, "ARTWORK")
    icon:SetAllPoints(f)
    f.icon = icon
    Theme.SkinButton(f, { borderColor = K.violet })
    local seat = FH and (FH.SeatAuraTile or FH.SeatCutIcon)
    if seat then seat(f) else LogOnce("noseat", "FrameHelpers.SeatAuraTile is missing, the icon is not seated inside the cut") end
    chip.frame, chip.plate = f, f.fsAuraPlate

    -- the white pop, cut like the chip so no square corner shows
    local c = (f.fsSkin and f.fsSkin.chamfer) or 6
    local path = c == 6 and Theme.SLICE_CUT2_FILL_TEXTURE or (MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
    chip.pop = Theme.AddSliceTexture(f, path, { K.white[1], K.white[2], K.white[3], 0 }, "OVERLAY", 2)
    Theme.ApplyNineSlice(chip.pop, c)
    chip.pop:Hide()

    -- the abbreviation shows only when the spell has no icon
    chip.label = f:CreateFontString(nil, "OVERLAY")
    chip.label:SetPoint("CENTER", f, "CENTER", 0, 0)
    chip.label:Hide()

    -- the rail from the chip down to 0 (a wide faint copy under a narrow core) and its end dot
    chip.railGlow = Tex("ARTWORK", 1)
    chip.rail = Tex("ARTWORK", 2)
    chip.dot = Tex("ARTWORK", 3)
    chip.dot:SetTexture(GLOW_ROUND)
    chip.dot:SetBlendMode("ADD")
    HideRail(chip)

    Seat(function()
        f:SetSize(ui(D.CHS), ui(D.CHS))
        Theme.ApplyMono(chip.label, ui(12.5), { 1, 1, 1, 1 })
        chip.rail:SetWidth(ui(RAIL_CORE))
        chip.railGlow:SetWidth(ui(RAIL_GLOW))
        chip.dot:SetSize(ui(DOT_BLOOM), ui(DOT_BLOOM))
        Point(chip.rail, "BOTTOM", chip.x, BOT)
        Point(chip.railGlow, "BOTTOM", chip.x, BOT)
        chip.y = nil
        if chip.mode == "live" then
            Place(chip, chip.expiresAt - GetTime())
        elseif chip.mode == "absent" then
            Place(chip, 0)
        end
    end)
    ApplyLook(chip)
    return chip
end

-------------------------------------------------------------------------------
-- Motion
-------------------------------------------------------------------------------

local function StopTicking()
    if ticking then
        ticking = false
        frame:SetScript("OnUpdate", nil)
    end
end

local function Step()
    local now = GetTime()
    local live = 0
    for i = 1, #chips do
        local chip = chips[i]
        if chip.mode == "live" then
            local rem = chip.expiresAt - now
            if rem <= 0 then
                -- ran out: the ledger pushes nothing at an expiry, so turn into the absent chip here
                chip.mode = "absent"
                ApplyLook(chip)
                chip.y = nil
                Place(chip, 0)
            else
                live = live + 1
                local band = rem <= D.BAND_S
                if band ~= chip.band then
                    chip.band = band
                    ApplyLook(chip)
                end
                Place(chip, rem)
                if band then
                    local c = K.amber
                    local pl = 0.5 + 0.5 * math.sin(now * 9)
                    chip.frame.fsSkin.glow:SetVertexColor(c[1], c[2], c[3], math.min(1, GLOW_BAND * (0.55 + 0.6 * pl)))
                end
                if chip.popAt then
                    local age = now - chip.popAt
                    if age >= D.POP_S then
                        HidePop(chip)
                    else
                        chip.pop:SetVertexColor(K.white[1], K.white[2], K.white[3], D.POP_A * (1 - age / D.POP_S))
                    end
                end
            end
        end
    end
    if live == 0 then StopTicking() end
end

local function StartTicking()
    if not ticking and pieceOn then
        ticking = true
        frame:SetScript("OnUpdate", Step)
    end
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local function Abbreviation(key)
    return ABBR[key] or string.upper(string.sub(tostring(key), 1, 2))
end

-- One row of the Hud state into one chip. A nil row is an unused lane. `newTarget` is true when
-- this push follows a target switch: a DoT that shows up live on the new target was not applied
-- by us just now, so it is placed without the pop, unless the row is a fresh apply (a Tab and an
-- instant cast inside one Hud tick arrive together as absent to live in one new-epoch push).
local function UpdateChip(chip, e, now, newTarget)
    local prevMode, prevExpires = chip.mode, chip.expiresAt
    local remaining = e and Num(e.remaining)
    if not remaining then
        -- key and iconId are cleared, not copied from the row: an off chip seats no icon or label, so
        -- the live branch must always reseat (a nil icon would otherwise compare equal to the cache)
        chip.mode, chip.key, chip.iconId, chip.expiresAt = "off", nil, nil, nil
        if prevMode ~= "off" then ApplyLook(chip) end
        return
    end

    -- icon and abbreviation follow the row
    if chip.key ~= e.key or chip.iconId ~= e.icon then
        chip.key, chip.iconId = e.key, e.icon
        if e.icon ~= nil then
            chip.frame.icon:SetTexture(e.icon)
            chip.frame.icon:Show()
            chip.label:Hide()
        else
            chip.frame.icon:Hide()
            chip.label:SetText(Abbreviation(e.key))
            chip.label:Show()
        end
    end

    local expiresAt = Num(e.expiresAt)
    if not expiresAt and remaining > 0 then expiresAt = now + remaining end
    if expiresAt and expiresAt > now then
        chip.mode, chip.expiresAt = "live", expiresAt
        chip.band = expiresAt - now <= D.BAND_S
        if newTarget then
            local duration = Num(e.duration)
            if duration and remaining >= duration - FRESH_EPS then
                chip.popAt = now             -- applied within the last half second: a genuine apply
            else
                HidePop(chip)                -- the old target's flash does not follow the switch
            end
        elseif prevMode == "absent" or (prevMode == "live" and expiresAt > prevExpires + REAPPLY_EPS) then
            chip.popAt = now
        end
        ApplyLook(chip)
        chip.y = nil
        Place(chip, expiresAt - now)
        if chip.popAt == now then
            chip.pop:SetVertexColor(K.white[1], K.white[2], K.white[3], D.POP_A)
            chip.pop:Show()
        end
    else
        chip.mode, chip.expiresAt = "absent", nil
        ApplyLook(chip)
        chip.y = nil
        Place(chip, 0)
    end
end

-- A chip whose update threw: off and hidden, never left showing whatever it showed before. The key and icon
-- are cleared so the next good row reseats them.
local function DropChip(chip)
    chip.mode, chip.key, chip.iconId, chip.expiresAt = "off", nil, nil, nil
    pcall(ApplyLook, chip)
    pcall(chip.frame.Hide, chip.frame)
end

-- PLAYER_REGEN_DISABLED / PLAYER_REGEN_ENABLED / a re-seed: the absent chips follow the combat flag at once.
-- Live chips are not touched; a chip is written only when its visibility changes.
local function SyncAbsentChips()
    local want = InCombat()
    for i = 1, #chips do
        local f = chips[i].frame
        if chips[i].mode == "absent" and f:IsShown() ~= want then f:SetShown(want) end
    end
end

-- A Hud push with a plainly false state.inCombat while the flag is true: re-seed from both APIs and, if they
-- agree it is over, clear the flag and hide the absent chips. One way only, never sets the flag true.
local function HealCombat(state)
    if not inCombat or type(state) ~= "table" then return end
    local v = state.inCombat
    if FS.IsSecret and FS.IsSecret(v) then return end
    if v ~= false then return end
    SeedCombat()
    if not inCombat then SyncAbsentChips() end
end

local function Apply(state)
    HealCombat(state)
    local profile = FS.Hud and FS.Hud.GetProfile and FS.Hud.GetProfile()
    local dots = profile and profile.dots
    local lanes = {}
    if dots and type(state) == "table" and state.active and type(state.row) == "table" then
        for _, e in ipairs(state.row) do
            if type(e) == "table" and dots[e.key] and #lanes < D.MAX_LANES then lanes[#lanes + 1] = e end
        end
    end
    if #lanes > 0 then content:Show() else content:Hide() end

    -- state.targetEpoch changes on every target switch (HudLogic exports the integer only)
    local epoch = type(state) == "table" and Num(state.targetEpoch) or nil
    local newTarget = epoch ~= lastEpoch
    lastEpoch = epoch

    local now = GetTime()
    local live = false
    for i = 1, #chips do
        -- one pcall per chip: a throw in chip i must not skip chips i + 1.. (they would keep a stale icon)
        local ok, err = pcall(UpdateChip, chips[i], lanes[i], now, newTarget)
        if not ok then
            LogOnce("state", err)
            DropChip(chips[i])
        end
        if chips[i].mode == "live" then live = true end
    end
    if live then StartTicking() else StopTicking() end
end

local function OnState(state)
    if not pieceOn then return end
    local ok, err = pcall(Apply, state)
    if not ok then LogOnce("state", err) end
end

-------------------------------------------------------------------------------
-- Piece hooks and build
-------------------------------------------------------------------------------

local function OnPieceShow()
    pieceOn = true
    local Hud = FS.Hud
    if not (Hud and Hud.Subscribe) then
        LogOnce("nohud", "FS.Hud is missing, the DoT scale has no data")
        return
    end
    if not subscribed then
        subscribed = true
        Hud.Subscribe(OnState)             -- pushes the current state at once
    end
end

local function OnPieceHide()
    pieceOn = false
    if subscribed and FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnState) end
    subscribed = false
    lastEpoch = nil
    StopTicking()
    -- forget the chips so the next show repaints cleanly and a stale expiry cannot read as a reapply
    for i = 1, #chips do
        chips[i].mode, chips[i].expiresAt = "off", nil
        ApplyLook(chips[i])
    end
end

local function RefreshTargetLayer()
    if not gate then return end
    local want = FS.TargetTakesDots()
    if want ~= gateOn then
        gateOn = want
        gate:SetShown(want)
    end
end

local function BuildAll()
    frame = CreateFrame("Frame", "ForeverSynthwaveGunsightDots", Gunsight.root)
    frame:SetSize(1, 1)
    frame:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    gate = CreateFrame("Frame", nil, frame)
    gate:SetSize(1, 1)
    gate:SetPoint("CENTER", frame, "CENTER", 0, 0)
    gate:SetFrameLevel(frame:GetFrameLevel())     -- no extra level: the content keeps the stacking it had on the piece
    content = CreateFrame("Frame", nil, gate)
    content:SetSize(1, 1)
    content:SetPoint("CENTER", gate, "CENTER", 0, 0)
    content:Hide()                         -- shown once a state has a DoT lane

    BuildScale()
    for i = 1, D.MAX_LANES do chips[i] = BuildChip(i) end

    Dots.frame, Dots.gate, Dots.content, Dots.chips, Dots.parts = frame, gate, content, chips, parts

    RefreshTargetLayer()
    SeedCombat()
    local events = CreateFrame("Frame", nil, frame)
    events:RegisterEvent("PLAYER_TARGET_CHANGED")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:RegisterEvent("PLAYER_REGEN_DISABLED")     -- the absent (recast) chips show only in combat
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:SetScript("OnEvent", function(_, event)
        if event == "PLAYER_REGEN_DISABLED" then
            inCombat = true                 -- the event itself, not InCombatLockdown(): it may still read false here
            SyncAbsentChips()
        elseif event == "PLAYER_REGEN_ENABLED" then
            inCombat = false
            SyncAbsentChips()
        else
            if event == "PLAYER_ENTERING_WORLD" then SeedCombat(); SyncAbsentChips() end
            RefreshTargetLayer()
        end
    end)
    -- death, a duel and mind control change the answer with no target change; one frame, the target only
    local unitEvents = CreateFrame("Frame", nil, frame)
    for _, name in ipairs({ "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }) do
        if unitEvents.RegisterUnitEvent then pcall(unitEvents.RegisterUnitEvent, unitEvents, name, "target") end
    end
    unitEvents:SetScript("OnEvent", RefreshTargetLayer)
end

local function Build()
    if built then return end
    built = true
    if not Gunsight.IsEnabled() then return end
    local Theme, FH = FS.Theme, FS.FrameHelpers
    if not (Theme and Theme.SkinButton and Theme.ApplyMono and Theme.AddSliceTexture and Theme.ApplyNineSlice and FH) then
        LogOnce("notheme", "Theme or FrameHelpers is missing, the DoT scale is not built")
        return
    end
    local ok, err = pcall(BuildAll)
    if not ok then
        LogOnce("build", err)
        if frame then frame:Hide() end
        return
    end
    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(SeatAll) end
    Gunsight.RegisterPiece("dot", { frame = frame, onShow = OnPieceShow, onHide = OnPieceHide })
end

Gunsight.OnReady(Build)
