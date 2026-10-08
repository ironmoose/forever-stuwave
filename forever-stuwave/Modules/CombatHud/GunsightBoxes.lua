-- Forever STUwave: Gunsight cast info boxes (the boxes of pieces "you" and "tgt").
--
-- The two info boxes of the Gunsight HUD (mockups/gunsight-hud-v2-2026-10-02/
-- gunsight-hud-v2-2026-10-02.html, infoBox and castIcon, drawn by drawYour on BOXL and drawTarget on
-- BOXR): a 114 x 56 chamfered plate above each tape with a small caps header, two lines of text and a
-- 28 square spell icon tile on its inner side.
--
--   yours   header the character name (cyan, YOU as the fallback); line 1 the spell name (white, 14 image px,
--           shrunk to fit), line 2 the timer "0.9 / 2.5" (cyan, 18); the icon tile to the RIGHT of the
--           box; the channel tick counter "n/T" / "CUT" in the header row at the box's right end (not in
--           the mockup: the mockup has no counter, this is where the Stack A tab's counter now lives)
--   target  no header (the mockup drops the TARGET label); line 1 the unit name (white while it casts, muted between casts, 14),
--           an HP rule and a power rule under it (below), a divider, line 2 the spell name (14, the
--           mockup's fs2; yours stays 18); the icon tile to the LEFT of the box, only while
--           a cast is live; NO timer (target cast timing is secret, the mockup draws none). The box
--           edge, line 2, divider and tile edge are pink while the cast can be kicked and
--           steel while it cannot (flag through SetAlphaFromBoolean, see below)
--
-- NO STATE MACHINE HERE. CastBars.lua owns every cast rule. A box exposes the MEMBERS its bar table
-- needs (box.members = { icon, timer, tabName, tabTicks }) and GunsightTape.lua puts them into the
-- bar table it hands to FS.CastBars.SetView, so CastBars keeps writing through its existing paths
-- (S.icon:SetTexture, S.tabName:SetText, S.timer:SetFormattedText / SetText, S.tabTicks) and this file
-- reads no cast data, runs no OnUpdate and listens to one event pair (the target's unit name).
-- Three of the four members are small sink objects with the FontString / Texture methods CastBars
-- calls; a write that is a PLAIN empty string means "idle" (CastBars's GoIdle), anything else "live":
--   tabName   forwards to the FontString(s), shrinks plain text that is wider than the box, never
--             measures a secret (a fixed smaller size and a fixed width instead: the text clips),
--             and flips line 1's colour between live (white) and muted
--   timer     forwards, and at idle blanks line 2 (no "0.0 / total"); the target's is a null sink
--   icon      forwards, dims the player's tile at idle and hides the target's
-- A secret (spell name, unit name, flag, texture) only ever reaches SetText / SetTexture /
-- SetAlphaFromBoolean: it is type-checked (legal) and never compared, concatenated, measured or
-- upper-cased. The flag colouring needs no member of its own: the box adds its two colour frames
-- (box.fb.pink / box.fb.steel) to the lists the tape's shield stand-in drives.
--
-- VISIBILITY. YOUR box exists only while you cast: it is built hidden, a plain empty write through the name
-- sink (CastBars' GoIdle) hides the WHOLE box (plate, header, both lines, tile, tick counter), any other
-- name write shows it (a secret name included: the decision is the write path, a secret is never read), and
-- the INTERRUPTED look shows it and keeps it up until the next write clears it. THE TARGET's box is shown
-- only while the player has a target (FS.HasTarget, Theme.lua: a secret or unreadable UnitExists keeps it
-- shown), re-read on PLAYER_TARGET_CHANGED and PLAYER_ENTERING_WORLD; its cast state is untouched, only the
-- visuals hide. Both rules are Show/Hide of the box frame (a plain addon frame, never protected, no secure
-- child), legal in combat, and a rescale never calls Show. The piece toggles are independent: they fade the
-- tape piece frame above the box.
--
-- HEADER. Yours reads the character's name, `UnitName("player")` upper-cased and shrunk to fit the header
-- width (the box minus C.HEAD_RESERVE kept for the tick counter), falling back to YOU for nil, "Unknown", an
-- empty string or a secret; refreshed on PLAYER_LOGIN / PLAYER_ENTERING_WORLD because the name is not always
-- ready at build. The target's box has no header at all (no FontString, in any tone copy).
--
-- TARGET BARS (mockup option B "Underline", drawTargetBars / tbBarH). The target frame grows UP by C.TGT_GROW
-- (8 image px) above boxR so two thin rules fit under the unit name: HP (3 high) and power (2 high, one px
-- below), as wide as the name (at least 24 image px; a secret name has no measurable width, so the full text
-- width). The divider, line 2 and the icon tile keep their old screen seats; line 1 rides the
-- new top. A rail is a track in the bar colour (alpha .2), a StatusBar fill with a horizontal alpha gradient
-- (.35 to 1, flat colour if SetGradient is missing or refused) and a 1.5 px tip anchored to the fill
-- texture's RIGHT edge, so no fraction is ever computed. UnitHealth / UnitHealthMax / UnitPower / UnitPowerMax
-- go straight to SetMinMaxValues / SetValue (secret in combat, never compared). LOW HP is a red twin of the
-- HP rail: UnitHealthPercent("target", false, curve) with a Step curve (1 from 0 to TB_LOW, 0 above) goes
-- straight to SetAlpha on the red rail and the inverse curve on the green one (the PartyFrames / PetFrame
-- pattern; the first failure latches and logs once, then a plain cur / max compare when neither value is
-- secret, else red stays down). Power takes its colour from UnitPowerType (plain): mana cyan, rage, focus,
-- energy gold; an unlisted type reads as mana; no power (a plain max of 0, or no type) hides the rule, a
-- secret max keeps it. The events (UNIT_HEALTH, UNIT_MAXHEALTH, UNIT_POWER_UPDATE, UNIT_MAXPOWER,
-- UNIT_DISPLAYPOWER, registered for "target" on a listener frame of their own) and the target / world events
-- of the name listener refresh them; no OnUpdate. GunsightTape's KICK tag is seated off boxR and rides the
-- box top in the mockup, so it needs C.TGT_GROW more rise (see the tape file).
--
-- TARGET BAR SETTINGS. The rail heights, the rail width and the value numbers beside them are FS.Config keys
-- (SETTINGS, edited in the config window); a change applies live, in combat too (plain frames), through
-- Config.OnChange, coalesced to one apply per box on the next frame, and a profile switch moves them too. One slider px is
-- C.BAR_PX image px: the resource default (4) is the 2 image px rail above, the health default (11) a taller 5.5, and the
-- width setting is scaled by C.BAR_WIDTH_SCALE (its 100% is 1.2 x the name). The numbers are off until a player turns them on.
-- UNVERIFIED IN GAME: where the numbers stand, and UnitPowerPercent with the ScaleTo100 curve.
--
-- AT REST (when a box is shown but idle: the target's only): the plate and steel edge, the unit's name muted,
-- no spell and no tile.
--
-- STRUCTURE (one build per box, Layout re-seats and re-sizes on FS.Layout.OnRescale, nothing is created
-- again): box.frame (child of the tape's piece frame, so the `you` / `tgt` piece toggles fade it;
-- filling anchors.boxL / boxR) holds the plate, line 1, the tick counter, one TONE frame per colour
-- (edge stroke, header, line 2, the target's divider) and the icon TILE (plate, icon, one tile-tone
-- frame per colour with the tile edge). A tone is a frame so SetAlphaFromBoolean lands on a frame, as
-- it already does for the tape's own layers. Plain frames only, nothing protected.
--
-- UNVERIFIED IN GAME (needs an eyeball): the target bars (SetGradient on a StatusBar fill texture, the tip riding
-- that fill at a value of 0, SetAlpha taking the secret curve result, the rules against line one's descenders),
-- the text baselines (C.DESCENT is an estimate of the font's
-- descent, as GunsightFrame's LABEL_DESCENT), line 2's clip for a secret name (the text is cut at
-- the width, or overflows if the client does not clip), the chamfer (baked 6, the mockup 8 image px),
-- the box edge without the mockup's glow halo, the tick counter in the header row, the "0.9 / 2.5"
-- timer with its muted " / total" (CastBars' colour escape; the mockup colours the whole line), and
-- the target's idle look, the INTERRUPTED red and flicker timing against the mockup's (the box edge snaps to red
-- where the mockup eases over .22 s; the timer's muted " / total" stays muted).
--
-- INTERRUPTED. CastBars calls bar.onVerdict(bar, "interrupt") (pcall'd, view bars only) after it froze the
-- readout; members.onVerdict shows the mockup's outage look: plain "INTERRUPTED" on line one in red, a
-- third (red) tone frame in place of the pink / steel / cyan one (box edge, header, line 2, divider, tile
-- edge; NOT in the box.fb lists the flag drives), the player's icon dimmed and gray, and the box alpha
-- flickering through ONE Alpha AnimationGroup (no OnUpdate). ANY later write through the name / timer
-- sinks (GoIdle, the next cast; the target's timer is a null sink, so only its name sink) drops it and
-- stops the flicker. A success has no look in the box (the
-- mockup's hold only pops the timer's colour), so CastBars sends no "succeed".
--
-- FONTS. Every FontString gets its font (ApplyMono at the base size) at creation: SetText on one without
-- a font throws "Font not set", which would land in pcall(BuildBox) and silently drop the box.

local addonName, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" or type(Gunsight.OnReady) ~= "function" then return end

local GunsightBoxes = {}
FS.GunsightBoxes = GunsightBoxes

local G = Gunsight.G
local ui = Gunsight.ui
local NAME = "ForeverSTUwaveGunsightBox_"
local IsSecret = FS.IsSecret or function() return false end

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightboxes-harness.py re-reads every one from the HTML)
-------------------------------------------------------------------------------

local C = {
    CHAMFER = 8,                                     -- chamfer(b.x, b.y, b.w, b.h, 8) (the baked cut is 6)
    FILL = { 13 / 255, 6 / 255, 32 / 255, 0.85 * 0.82 },  -- rgba(13,6,32,.85) under A(.82)
    STROKE_A = 1,                                    -- A(a), a = 1
    PAD = 7,                                         -- text x = b.x + 7, wmax = b.w - 14
    L1_SIZE = 14, L1_Y = 23,                         -- fs = o.fs1 || 14, text(l1, b.x + 7, b.y + 23, ...)
    L2_SIZE = 18, L2_Y = 45,                         -- f2 = o.fs2 || 18 (your timer), text(l2, b.x + 7, b.y + 45, ...)
    TGT_L2_SIZE = 14,                                -- the target call passes fs2: 14 (its spell line)
    TGT_GROW = 8,                                    -- tbBox() 'b': y: BOXR.y - 8, h: BOXR.h + 8 (grows UP)
    -- target bars, option B (drawTargetBars, tbBarH)
    TB_X = 7, TB_MIN_W = 24,                         -- x = BR.x + 7, w = max(24, name width)
    TB_HP_Y = 26, TB_HP_H = 3,                       -- tbBarH(x, y = BR.y + 26, w, 3, ...); the mockup's, no longer the default
    TB_PW_Y = 30, TB_PW_H = 2,                       -- tbBarH(x, y + 4, w, 2, ...); the rails draw SETTINGS * BAR_PX
    TB_TRACK_A = 0.2, TB_TAIL_A = 0.35,              -- rgba(col, .2) track; fill gradient rgba(col, .35) to rgba(col, 1)
    TB_TIP_W = 1.5, TB_TIP_A = 0.9, TB_TIP_MIX = 0.55,  -- fillRect(x + fw - 1.5, y, 1.5, h) in mix(col, white, .55) at A(.9)
    TB_LOW = 0.35, LOW_EPSILON = 0.0005,             -- TB_LOW; PartyFrames' LOW_HP_EPSILON
    -- target bar settings and numbers (not in the mockup; the config window mockup has the controls)
    BAR_PX = 0.5,                                    -- image px per slider px: its 4 is the 2 above (the health default is 11)
    BAR_WIDTH_SCALE = 1.2,                           -- the width setting's 100% is the look the old 120% gave (Parker, in game)
    NUM_SIZE = 9, NUM_GAP = 5, NUM_LINE = 1,         -- number type size, gap past the box edge, gap between lines
    POWER_KEYS = { [0] = "mana", [1] = "rage", [2] = "focus", [3] = "energy" },  -- UnitPowerType -> TB_PC key
    BAR_EVENTS = { "UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER", "UNIT_DISPLAYPOWER" },
    DIV_Y = 29, DIV_A = 0.4,                         -- hline(b.y + 29, b.x + 7, b.x + b.w - 7, ..., .4 * a)
    HEAD_SIZE = 11, HEAD_DY = 14, HEAD_A = 0.9,      -- header(s, x, BOX.y - 14, col, .9), text size 11
    HEAD_RESERVE = 26,                               -- image px kept at the header's right end for the tick
                                                     -- counter (not in the mockup)
    CI = 28, CIC = 5, CIG = 6,                       -- castIcon: tile size, chamfer, gap to the box
    CI_FILL_A = 0.9 * 0.85, CI_STROKE_A = 0.9,       -- A(.85 * a) rgba(13,6,32,.9); A(.9 * a) stroke
    ICON_CROP = 0.08,                                -- ICON_CROP, per side
    IDLE_ICON_A = 0.45,                              -- (idle ? .45 : 1) * flick
    DESCENT = 0.22,                                  -- em from a baseline to the bottom of its line (estimate)
    SECRET_L2_SIZE = 14,                             -- line 2's image px for a secret name (never measured)
    MIN_FONT = 6,                                    -- smallest size a fit may pick
    -- INTERRUPTED look (drawYour, st.mode == 'outage'): the flicker steps of the box alpha, 0.05 s each
    -- ((st.tau - .2) / .35 * 7 over [.5, 1, .35, .85, .3, .7, .45]) after a 0.2 s delay, then back to 1.
    FLICK_DELAY = 0.2, FLICK_STEP = 0.05,
    FLICK = { 0.5, 1, 0.35, 0.85, 0.3, 0.7, 0.45 },
}
C.TB_GAP = C.TB_PW_Y - C.TB_HP_Y - C.TB_HP_H       -- the one image px between the two rules
GunsightBoxes.C = C

local BG = { 13 / 255, 6 / 255, 32 / 255, 1 }          -- --bg #0d0620
local colors = {
    cyan = (FS.Theme and FS.Theme.COLOR_POWER) or { 0.133, 0.878, 1, 1 },        -- --cyan #22e0ff
    pink = (FS.Theme and FS.Theme.COLOR_HEALTH) or { 1, 0.18, 0.592, 1 },        -- --pink #ff2e97
    steel = (FS.Theme and FS.Theme.COLOR_STEEL) or { 0.5529, 0.5765, 0.651, 1 }, -- --steel #8d93a6
    red = (FS.Theme and FS.Theme.COLOR_RED) or { 1, 0.2314, 0.3059, 1 },         -- --red #ff3b4e (K.red)
    white = { 0xf3 / 255, 0xfb / 255, 1, 1 },                                    -- --white #f3fbff
    muted = { 0x9d / 255, 0x93 / 255, 0xc4 / 255, 1 },                           -- --muted #9d93c4
    bg = BG,
    green = (FS.Theme and FS.Theme.COLOR_HEAL) or { 0.224, 1, 0.078, 1 },        -- TB_HP #39ff14
    gold = (FS.Theme and FS.Theme.COLOR_GOLD) or { 1, 0.8235, 0.2471, 1 },       -- K.gold #ffd23f (energy)
    rage = { 0xc4 / 255, 0x1f / 255, 0x3b / 255, 1 },                            -- TB_PC.rage #c41f3b
    focus = { 1, 0x80 / 255, 0x40 / 255, 1 },                                    -- TB_PC.focus #ff8040
}
GunsightBoxes.colors = colors

-------------------------------------------------------------------------------
-- Settings (FS.Config keys, profile aware; ranges and defaults are the config window mockup's)
-------------------------------------------------------------------------------

local Config = FS.Config
local KEY = "gunsight.targetBars."
local SETTINGS = {
    hpHeight = { key = KEY .. "hpHeight", default = 11, min = 2, max = 12, step = 1 },
    powerHeight = { key = KEY .. "powerHeight", default = 4, min = 2, max = 12, step = 1 },
    width = { key = KEY .. "width", default = 100, min = 50, max = 150, step = 5 },
    numbers = { key = KEY .. "numbers", default = false },
    numberFormat = { key = KEY .. "numberFormat", default = "both" },
}
GunsightBoxes.SETTINGS = SETTINGS
GunsightBoxes.NUMBER_FORMATS = {
    { value = "current", text = "Current" },
    { value = "both", text = "Current / max" },
    { value = "percent", text = "Percent" },
}
for _, def in pairs(SETTINGS) do Config.RegisterDefault(def.key, def.default) end

-- Marks a profile whose stored width was converted off the old scale (whose 120 is today's 100), per profile.
local WIDTH_MIGRATED = { key = KEY .. "widthMigrated", default = false }
GunsightBoxes.WIDTH_MIGRATED = WIDTH_MIGRATED
Config.RegisterDefault(WIDTH_MIGRATED.key, WIDTH_MIGRATED.default)

-- Converts the ACTIVE profile's stored width once (old v becomes v / BAR_WIDTH_SCALE, rounded to the step, clamped);
-- an unstored width stays unstored. Runs at load, on a width read and when the flag changes (a switch, copy or reset), so
-- every profile converts when it first becomes active; a width write alone must never trigger it.
local migrating = false
local function MigrateWidth()
    if migrating or Config.Get(WIDTH_MIGRATED.key) == true then return end
    migrating = true
    local def = SETTINGS.width
    local v = Config.Get(def.key)
    local done = true
    if Config.IsStored(def.key) and type(v) == "number" and v == v then
        local scaled = math.floor(v / C.BAR_WIDTH_SCALE / def.step + 0.5) * def.step
        done = Config.Set(def.key, math.min(def.max, math.max(def.min, scaled)))
    end
    if done then Config.Set(WIDTH_MIGRATED.key, true) end
    migrating = false
end
Config.OnChange(WIDTH_MIGRATED.key, MigrateWidth)

-- Convert the active profile as soon as the saved variables are in (and again after the login profile resolve), so the
-- read in Setting is only a backstop and no width written later can be taken for an old one.
local migrator = CreateFrame("Frame")
migrator:RegisterEvent("ADDON_LOADED")
migrator:RegisterEvent("PLAYER_LOGIN")
migrator:SetScript("OnEvent", function(_, event, name)
    if event == "PLAYER_LOGIN" or name == addonName then MigrateWidth() end
end)

-- A number setting clamped into its range; anything else (a string, NaN) reads as the default.
local function Setting(def)
    if def == SETTINGS.width then MigrateWidth() end
    local v = Config.Get(def.key)
    if type(v) ~= "number" or v ~= v then return def.default end
    return math.min(def.max, math.max(def.min, v))
end

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local function HasMethod(obj, name)
    return obj ~= nil and type(obj[name]) == "function"
end

local function FillParent(frame, parent)
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, 0)
    frame:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", 0, 0)
end

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
end

local function Paint(fs, color)
    fs:SetTextColor(color[1], color[2], color[3], color[4] or 1)
end

local function FontSize(imagePx)
    return math.max(C.MIN_FONT, math.floor(ui(imagePx) + 0.5))
end

-- Colour with a different alpha, for a texture's vertex colour.
local function WithAlpha(color, a)
    return { color[1], color[2], color[3], a }
end

-- A plain, non-secret empty string: the only write that means "idle". Never compares a secret.
local function IsPlainEmpty(v)
    if IsSecret(v) then return false end
    return v == nil or v == ""
end

-------------------------------------------------------------------------------
-- Text lines: one or two FontStrings (one per colour) that carry the same text and fit together
-------------------------------------------------------------------------------

-- line = { fonts, baseImg / secretImg (image px), wmax (UI units), size (applied), text (last PLAIN
-- text or nil), secretNow (the text now shown is a secret), colors (one per FontString) }
local function NewLine(fonts, baseImg, secretImg)
    return { fonts = fonts, baseImg = baseImg, secretImg = secretImg, colors = {}, size = nil, text = nil, secretNow = false }
end

local function ApplySize(line, size)
    if line.size == size then return end
    line.size = size
    for i, fs in ipairs(line.fonts) do
        FS.Theme.ApplyMono(fs, size, line.colors[i] or colors.white)
        Paint(fs, line.colors[i] or colors.white)
    end
end

local function SetLineColor(line, i, color)
    line.colors[i] = color
    Paint(line.fonts[i], color)
end

-- Picks the size for the text now in the line's FontStrings. A plain string is measured (at the
-- size it is drawn at, scaled back to the base) and shrunk to fit wmax; a secret is NEVER measured
-- (GetStringWidth on a secret is not allowed) and gets the fixed smaller size, its width fixed so it
-- clips instead of overflowing.
local function FitLine(line, text)
    local base = FontSize(line.baseImg)
    local size = base
    line.secretNow = false
    if IsSecret(text) then
        line.text = nil
        line.secretNow = true
        if line.secretImg then size = FontSize(line.secretImg) end
    elseif type(text) == "string" and text ~= "" then
        line.text = text
        local fs = line.fonts[1]
        local ok, w = pcall(fs.GetStringWidth, fs)
        if ok and type(w) == "number" and not IsSecret(w) and w > 0 and line.size and line.size > 0 then
            local atBase = w * base / line.size
            if atBase > line.wmax then
                size = math.max(C.MIN_FONT, math.floor(base * line.wmax / atBase))
            end
        end
    else
        line.text = nil
    end
    ApplySize(line, size)
end

-- A rescale re-runs the fit for the text the line holds (a secret keeps its fixed size).
local function RefitLine(line)
    if line.secretNow then
        ApplySize(line, FontSize(line.secretImg or line.baseImg))
    else
        FitLine(line, line.text or "")
    end
end

-- Writes `text` into every FontString of the line (errors propagate like a plain FontString's) and fits.
local function WriteLine(line, text)
    for _, fs in ipairs(line.fonts) do fs:SetText(text) end
    FitLine(line, text)
end

-------------------------------------------------------------------------------
-- Build pieces
-------------------------------------------------------------------------------

local function SolidTexture(parent, color, alpha, layer)
    local tex = parent:CreateTexture(nil, layer or "ARTWORK")
    tex:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    Crisp(tex)
    return tex
end

-- A FontString with its font already set: the client throws "Font not set" for SetText on one that has
-- none, and the throw would land in pcall(BuildBox) and silently drop the box. Every FontString this file
-- makes gets the mono font at its base size here, before anything is written to it.
local function NewFont(parent, imagePx, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(fs, FontSize(imagePx), color or colors.white)
    fs:SetJustifyH("LEFT")
    if HasMethod(fs, "SetJustifyV") then fs:SetJustifyV("BOTTOM") end
    fs:SetWordWrap(false)
    if HasMethod(fs, "SetMaxLines") then fs:SetMaxLines(1) end
    if HasMethod(fs, "SetNonSpaceWrap") then fs:SetNonSpaceWrap(false) end
    fs:SetText("")
    return fs
end

-- The state of a box's two looks. Colour flips only on a real change.
local function SetNameLive(box, live)
    if box.nameLive == live then return end
    box.nameLive = live
    SetLineColor(box.lineOne, 1, live and colors.white or colors.muted)
end

local function SetTimerLive(box, live)
    if box.timerLive == live then return end
    box.timerLive = live
    SetLineColor(box.lineTwo, 1, live and colors.cyan or colors.muted)
end

local function SetTileLive(box, live)
    if box.isTarget then
        box.tile:SetShown(live)
    else
        box.tile:SetAlpha(live and 1 or C.IDLE_ICON_A)
        -- the mockup's idle tile is a gray flag as well as dimmed
        if HasMethod(box.icon, "SetDesaturated") then box.icon:SetDesaturated(not live) end
    end
end

-- Show / Hide of the whole box. The box frame is a plain child of the tape piece frame: legal in combat.
local function SetBoxShown(box, on)
    if box.retired then return end
    box.frame:SetShown(on and true or false)
end

-- The target's box follows the target alone.
local function RefreshTargetShown(box)
    SetBoxShown(box, FS.HasTarget())
end

-------------------------------------------------------------------------------
-- Your header: the character's name
-------------------------------------------------------------------------------

-- The player's full name when it is real: nil for a missing name, an empty string, "Unknown" (the client's
-- placeholder very early on) and a secret (never inspected past IsSecret).
local function ReadPlayerName()
    -- The full name (first + surname, this server has surnames): FS.GetFullUnitName, read at call time, else UnitName.
    local name
    if type(FS.GetFullUnitName) == "function" then
        name = FS.GetFullUnitName("player")
    elseif type(UnitName) == "function" then
        name = UnitName("player")
    else
        return nil
    end
    if IsSecret(name) or type(name) ~= "string" or name == "" then return nil end
    if name == "Unknown" or name == _G.UNKNOWNOBJECT then return nil end
    return name
end

local function RefreshPlayerName(box)
    if box.retired or box.isTarget or not box.headLine then return end
    local name = ReadPlayerName()
    WriteLine(box.headLine, name and name:upper() or "YOU")
end

-------------------------------------------------------------------------------
-- The target's HP and power rules (option B, see the header)
-------------------------------------------------------------------------------

-- State and helpers hang off one table: the file is well clear of the file-scope local limit, but this keeps
-- it that way.
local Bars = {
    gradientBroken = false, warnedGradient = false, tipBroken = false, warnedTip = false,
    textBroken = false, pending = {}, dirty = {},
    percent = { health = { broken = false }, power = { broken = false } },
}
local FLAT_TEXTURE = (FS.Theme and FS.Theme.FLAT_TEXTURE) or "Interface\\Buttons\\WHITE8x8"

local function Logged(key, msg)
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, msg) end
end

-- A colour moved toward white by t (mix(col, '#ffffff', t)).
local function TowardWhite(color, t)
    return { color[1] + (1 - color[1]) * t, color[2] + (1 - color[2]) * t, color[3] + (1 - color[3]) * t }
end

-- The fill: a horizontal alpha gradient on the StatusBar's fill texture (the tail alpha up to 1 at the tip),
-- a flat colour when SetGradient is missing or refuses. The first refusal latches (every rail then takes the
-- flat colour) and is logged once, since LogDegradeOnce does not dedupe.
function Bars.PaintFill(rail, color)
    local fill = rail.fill
    if not Bars.gradientBroken and HasMethod(fill, "SetGradient") and type(CreateColor) == "function" then
        local ok = pcall(fill.SetGradient, fill, "HORIZONTAL",
            CreateColor(color[1], color[2], color[3], C.TB_TAIL_A), CreateColor(color[1], color[2], color[3], 1))
        if ok then return end
        Bars.gradientBroken = true
    end
    if Bars.gradientBroken and not Bars.warnedGradient then
        Bars.warnedGradient = true
        Logged("gunsightboxes_target_gradient",
            "|cffff4488Forever STUwave|r: target bar SetGradient refused, using a flat colour")
    end
    rail.sb:SetStatusBarColor(color[1], color[2], color[3], 1)
end

-- Track, fill and tip in one colour. Cached on the colour table last applied (a steady bar retints nothing).
function Bars.Tint(rail, color)
    if rail.color == color then return end
    rail.color = color
    rail.track:SetColorTexture(color[1], color[2], color[3], C.TB_TRACK_A)
    local tip = TowardWhite(color, C.TB_TIP_MIX)
    rail.tip:SetColorTexture(tip[1], tip[2], tip[3], C.TB_TIP_A)
    Bars.PaintFill(rail, color)
end

-- One rail: a host frame (its alpha is the whole rail's, which is what the low-HP curve drives) holding the
-- track, the StatusBar and the tip. The tip is anchored to the fill texture's RIGHT edge: the engine moves it
-- with the fill, and no fraction of a possibly secret value is ever computed.
function Bars.NewRail(parent, color)
    local host = CreateFrame("Frame", nil, parent)
    local sb = CreateFrame("StatusBar", nil, host)
    FillParent(sb, host)
    sb:SetStatusBarTexture(FLAT_TEXTURE)
    sb:SetMinMaxValues(0, 1)
    sb:SetValue(0)
    local track = host:CreateTexture(nil, "BACKGROUND")
    track:SetTexture(FLAT_TEXTURE)
    FillParent(track, host)
    Crisp(track)
    local fill = sb:GetStatusBarTexture()
    local tip = sb:CreateTexture(nil, "OVERLAY")
    tip:SetTexture(FLAT_TEXTURE)
    tip:SetPoint("TOPRIGHT", fill, "TOPRIGHT", 0, 0)
    tip:SetPoint("BOTTOMRIGHT", fill, "BOTTOMRIGHT", 0, 0)
    Crisp(tip)
    local rail = { host = host, sb = sb, fill = fill, track = track, tip = tip }
    Bars.Tint(rail, color)
    return rail
end

-- A Step curve: `from` up to `at`, `to` from there on (the PartyFrames / PetFrame / FrameHelpers shape).
function Bars.NewStep(at, from, to)
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Step)
    curve:AddPoint(0, from)
    curve:AddPoint(at, to)
    return curve
end

-- Built with the box, before the listeners. The red twin starts at alpha 0 and the green rail at 1.
function Bars.Build(box)
    local b = {}
    b.frame = CreateFrame("Frame", nil, box.frame)
    FillParent(b.frame, box.frame)
    b.hp = { green = Bars.NewRail(b.frame, colors.green), red = Bars.NewRail(b.frame, colors.red) }
    b.hp.red.host:SetAlpha(0)
    b.power = Bars.NewRail(b.frame, colors.cyan)
    b.powerShown = true
    b.hpText = NewFont(b.frame, C.NUM_SIZE, colors.white)       -- the value numbers, off until a player asks
    b.powerText = NewFont(b.frame, C.NUM_SIZE, colors.white)
    b.hpText:Hide()
    b.powerText:Hide()
    b.numbers, b.mode = false, SETTINGS.numberFormat.default
    if type(UnitHealthPercent) == "function" and type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
        and type(Enum) == "table" and type(Enum.LuaCurveType) == "table" and Enum.LuaCurveType.Step ~= nil then
        local atLow = C.TB_LOW + C.LOW_EPSILON
        local okLow, low = pcall(Bars.NewStep, atLow, 1, 0)
        local okBase, base = pcall(Bars.NewStep, atLow, 0, 1)
        if okLow and okBase then
            b.lowCurve, b.baseCurve = low, base
        else
            b.lowBroken = true                       -- logged by the first update, through the same latch
        end
        -- The tip hides at an empty bar the way FrameHelpers hides a caret: alpha 0 at a 0 fraction, 1 above.
        local okEmpty, empty = pcall(Bars.NewStep, C.LOW_EPSILON, 0, 1)
        if okEmpty then b.emptyCurve = empty end
    end
    box.bars = b
end

-- Width of the rules: the unit name as drawn (at least 24 image px), or the full text width when the name
-- is secret. Measured only from a plain string (the name sinks never measure a secret). While the
-- INTERRUPTED look owns line one, the width of the name stays.
function Bars.Measure(box)
    local line = box.lineOne
    if box.verdict then return end
    box.nameSecret = line.secretNow
    if line.secretNow then return end
    box.nameImg = 0
    if line.text then
        local fs = line.fonts[1]
        local ok, w = pcall(fs.GetStringWidth, fs)
        if ok and type(w) == "number" and not IsSecret(w) and w > 0 then box.nameImg = w / ui(1) end
    end
end

function Bars.SeatRail(box, rail, y, h, w)
    local k = ui(1)
    rail.host:ClearAllPoints()
    rail.host:SetPoint("TOPLEFT", box.frame, "TOPLEFT", C.TB_X * k, -y * k)
    rail.host:SetSize(w, h * k)
    rail.tip:SetWidth(C.TB_TIP_W * k)
end

-- The numbers stand past the box's outer edge: `base` is the baseline's image px below the box top.
function Bars.SeatText(box, fs, base)
    local k = ui(1)
    FS.Theme.ApplyMono(fs, FontSize(C.NUM_SIZE), colors.white)
    fs:ClearAllPoints()
    fs:SetPoint("BOTTOMLEFT", box.frame, "TOPRIGHT", C.NUM_GAP * k, -(base + C.NUM_SIZE * C.DESCENT) * k)
end

-- Rail heights in image px. The power rule's bottom edge stops one px above the divider: it shrinks first, then the
-- health rule gives way, but the power rule never goes below its minimum.
function Bars.Heights()
    local pwMin = SETTINGS.powerHeight.min * C.BAR_PX
    local room = C.DIV_Y + C.TGT_GROW - 1 - C.TB_HP_Y - C.TB_GAP
    local hpH = math.min(Setting(SETTINGS.hpHeight) * C.BAR_PX, room - pwMin)
    return hpH, math.min(Setting(SETTINGS.powerHeight) * C.BAR_PX, room - hpH)
end

function Bars.Seat(box)
    local b = box.bars
    local k = ui(1)
    local wmax = (box.geom.w - 2 * C.PAD) * k
    local w = wmax
    if not box.nameSecret then w = math.min(wmax, math.max(C.TB_MIN_W * k, (box.nameImg or 0) * k)) end
    w = math.min(wmax, w * (Setting(SETTINGS.width) / 100) * C.BAR_WIDTH_SCALE)
    local hpH, pwH = Bars.Heights()
    Bars.SeatRail(box, b.hp.green, C.TB_HP_Y, hpH, w)
    Bars.SeatRail(box, b.hp.red, C.TB_HP_Y, hpH, w)
    Bars.SeatRail(box, b.power, C.TB_HP_Y + hpH + C.TB_GAP, pwH, w)
    Bars.SeatText(box, b.hpText, C.TB_HP_Y + hpH)
    Bars.SeatText(box, b.powerText, C.TB_HP_Y + hpH + C.NUM_SIZE + C.NUM_LINE)
end

-- cur and max go straight to the setters (either may be secret); a setter that refuses is not an error here.
function Bars.SetBar(sb, cur, max)
    pcall(sb.SetMinMaxValues, sb, 0, max)
    pcall(sb.SetValue, sb, cur)
end

-- `red` drives the red twin, `green` the normal rail (numbers, or a secret curve result). False when a setter
-- refused.
function Bars.SetLowAlphas(b, red, green)
    local okRed = pcall(b.hp.red.host.SetAlpha, b.hp.red.host, red)
    local okGreen = pcall(b.hp.green.host.SetAlpha, b.hp.green.host, green)
    return okRed and okGreen
end

-- Both HP tips take the empty-curve alpha. No curve, or a refusal (logged once, latched), leaves them visible.
function Bars.UpdateHealthTips(b)
    if not b.emptyCurve or Bars.tipBroken then return end
    local ok, alpha = pcall(UnitHealthPercent, "target", false, b.emptyCurve)
    local green, red = b.hp.green.tip, b.hp.red.tip
    if ok and type(alpha) == "number" and pcall(green.SetAlpha, green, alpha) and pcall(red.SetAlpha, red, alpha) then
        return
    end
    Bars.tipBroken = true
    if not Bars.warnedTip then
        Bars.warnedTip = true
        Logged("gunsightboxes_target_tip",
            "|cffff4488Forever STUwave|r: target bar tip empty-hide refused, leaving the tip visible")
    end
    pcall(green.SetAlpha, green, 1)
    pcall(red.SetAlpha, red, 1)
end

-- A Linear 0..1 -> 0..100 curve for the percent text, built the first time percent is shown. The client's own
-- ScaleTo100 is used when it has one.
function Bars.NewScaleTo100()
    local curve = C_CurveUtil.CreateCurve()
    curve:SetType(Enum.LuaCurveType.Linear)
    curve:AddPoint(0, 0)
    curve:AddPoint(1, 100)
    return curve
end

function Bars.PercentCurve()
    if Bars.percentCurve ~= nil then return Bars.percentCurve or nil end
    Bars.percentCurve = false
    local constants = _G.CurveConstants
    if type(constants) == "table" and constants.ScaleTo100 ~= nil then
        Bars.percentCurve = constants.ScaleTo100
    elseif type(C_CurveUtil) == "table" and type(C_CurveUtil.CreateCurve) == "function"
        and type(Enum) == "table" and type(Enum.LuaCurveType) == "table" and Enum.LuaCurveType.Linear ~= nil then
        local ok, curve = pcall(Bars.NewScaleTo100)
        if ok then Bars.percentCurve = curve end
    end
    return Bars.percentCurve or nil
end

-- The engine hands back the percent (secret or not) and it goes straight to SetFormattedText, so a secret health
-- or power is never divided. A throw or a refused setter latches that kind and logs once; the plain cur / max division
-- then runs only for two plain numbers, else the text stays blank.
function Bars.WritePercent(fs, kind, cur, max)
    local state = Bars.percent[kind]
    local read = kind == "health" and UnitHealthPercent or UnitPowerPercent
    local curve = (not state.broken and type(read) == "function") and Bars.PercentCurve() or nil
    if curve then
        local ok, percent
        if kind == "health" then
            ok, percent = pcall(read, "target", false, curve)
        else
            ok, percent = pcall(read, "target", nil, false, curve)
        end
        if ok and type(percent) ~= "number" then            -- no percent this tick: blank, and try again next time
            fs:SetText("")
            return
        end
        if ok and pcall(fs.SetFormattedText, fs, "%.0f%%", percent) then return end
        state.broken = true                                 -- a throw or a refused setter latches this kind
        Logged("gunsightboxes_target_" .. kind .. "_percent",
            "|cffff4488Forever STUwave|r: target " .. kind .. " percent refused, using a plain compare")
    end
    if not IsSecret(cur) and not IsSecret(max) and max > 0 then
        fs:SetFormattedText("%.0f%%", cur / max * 100)
    else
        fs:SetText("")
    end
end

-- One rail's number. cur and max go straight to SetFormattedText (either may be secret: type() is legal on one, and
-- nothing here compares, adds or divides it). The first refusal latches the numbers off for the session and logs once.
function Bars.WriteValue(b, fs, kind, cur, max)
    if Bars.textBroken then return end
    local mode = b.mode
    if type(cur) ~= "number" or (mode ~= "current" and type(max) ~= "number") then
        fs:SetText("")
        return
    end
    if mode == "percent" then
        Bars.WritePercent(fs, kind, cur, max)
        return
    end
    local ok
    if mode == "current" then
        ok = pcall(fs.SetFormattedText, fs, "%d", cur)
    else
        ok = pcall(fs.SetFormattedText, fs, "%d / %d", cur, max)
    end
    if ok then return end
    Bars.textBroken = true
    b.hpText:SetText("")
    b.powerText:SetText("")
    Logged("gunsightboxes_target_numbers",
        "|cffff4488Forever STUwave|r: target bar numbers disabled, SetFormattedText rejected the value")
end

function Bars.UpdateHealth(box)
    local b = box.bars
    local cur, max = UnitHealth("target"), UnitHealthMax("target")
    Bars.SetBar(b.hp.green.sb, cur, max)
    Bars.SetBar(b.hp.red.sb, cur, max)
    if b.numbers then Bars.WriteValue(b, b.hpText, "health", cur, max) end
    Bars.UpdateHealthTips(b)
    if b.lowCurve and not b.lowBroken then
        local okLow, low = pcall(UnitHealthPercent, "target", false, b.lowCurve)
        local okBase, base = pcall(UnitHealthPercent, "target", false, b.baseCurve)
        if okLow and okBase and type(low) == "number" and type(base) == "number" and Bars.SetLowAlphas(b, low, base) then
            return
        end
        b.lowBroken = true
    end
    if b.lowBroken and not b.warnedLow then
        b.warnedLow = true
        Logged("gunsightboxes_target_lowhp",
            "|cffff4488Forever STUwave|r: target low-HP curve refused, falling back to a plain compare")
    end
    -- Unknown (secret) health: red stays down and the normal rail up.
    local low = false
    if not IsSecret(cur) and not IsSecret(max) and type(cur) == "number" and type(max) == "number" and max > 0 then
        low = cur / max <= C.TB_LOW
    end
    Bars.SetLowAlphas(b, low and 1 or 0, low and 0 or 1)
end

-- The power colour for UnitPowerType (a plain number): the palette's, mana for an unlisted type, nil (no rule)
-- for a missing or negative one. A secret type reads as mana.
function Bars.PowerColor(ptype)
    if IsSecret(ptype) then return colors.cyan end
    if type(ptype) ~= "number" or ptype < 0 then return nil end
    local key = C.POWER_KEYS[ptype]
    if key == "rage" then return colors.rage end
    if key == "focus" then return colors.focus end
    if key == "energy" then return colors.gold end
    return colors.cyan
end

function Bars.UpdatePower(box)
    local b = box.bars
    local rail = b.power
    local show = false
    local max
    if type(UnitPower) == "function" and type(UnitPowerMax) == "function" and type(UnitPowerType) == "function" then
        local color = Bars.PowerColor((UnitPowerType("target")))
        max = UnitPowerMax("target")
        -- No power: a plain max of 0 (a secret max keeps the rule).
        show = color ~= nil and (IsSecret(max) or (max ~= nil and max ~= 0))
        if show then Bars.Tint(rail, color) end
    end
    if show ~= b.powerShown then
        b.powerShown = show
        rail.host:SetShown(show)
        b.powerText:SetShown(show and b.numbers)
    end
    if show then
        local cur = UnitPower("target")
        Bars.SetBar(rail.sb, cur, max)
        if b.numbers then Bars.WriteValue(b, b.powerText, "power", cur, max) end
        -- The power tip hides at empty power through FrameHelpers' shared helper (its own curve, latch and log).
        local helpers = FS.FrameHelpers
        if type(helpers) == "table" and type(helpers.UpdatePowerHostEmpty) == "function" then
            pcall(helpers.UpdatePowerHostEmpty, rail.tip, "target")
        end
    end
end

-- Runs a bar update so that a throw (a bad API on this client) never reaches the box build or a handler that
-- also refreshes the unit name. The first failure is logged; the bars just stay as they were.
function Bars.Guard(fn, ...)
    local ok, err = pcall(fn, ...)
    if ok then return end
    if not Bars.warnedThrow then
        Bars.warnedThrow = true
        Logged("gunsightboxes_target_bars",
            "|cffff4488Forever STUwave|r: target bars update failed: " .. tostring(err))
    end
end

-- Everything, for the target / world events and the build. Nothing is read without a target.
function Bars.Refresh(box)
    if box.retired or not box.bars or not FS.HasTarget() then return end
    if type(UnitHealth) == "function" and type(UnitHealthMax) == "function" then Bars.UpdateHealth(box) end
    Bars.UpdatePower(box)
end

-- Reads the settings and re-seats, re-sizes and re-reads the bars: at build and on a setting change.
function Bars.ApplyConfig(box)
    local b = box.bars
    if box.retired or not b then return end
    b.numbers = Config.Get(SETTINGS.numbers.key) == true
    local mode = Config.Get(SETTINGS.numberFormat.key)
    b.mode = (mode == "current" or mode == "both" or mode == "percent") and mode or SETTINGS.numberFormat.default
    Bars.Seat(box)
    b.hpText:SetShown(b.numbers)
    b.powerText:SetShown(b.numbers and b.powerShown)
    if not b.numbers then
        b.hpText:SetText("")
        b.powerText:SetText("")
    end
    Bars.Refresh(box)
end

-- Defensive: none of the bar frames is protected today, so a change applies at once even in combat. This parks it
-- for PLAYER_REGEN_ENABLED if one ever is.
function Bars.Locked(box)
    if type(InCombatLockdown) ~= "function" or not InCombatLockdown() then return false end
    local b = box.bars
    for _, frame in ipairs({ box.frame, b.frame, b.hp.green.host, b.hp.red.host, b.power.host }) do
        if HasMethod(frame, "IsProtected") and frame:IsProtected() then return true end
    end
    return false
end

function Bars.Apply(box)
    if box.retired or not box.bars then return end
    if Bars.Locked(box) then
        Bars.pending[box] = true
        if not Bars.regen then
            local regen = CreateFrame("Frame")
            regen:RegisterEvent("PLAYER_REGEN_ENABLED")
            regen:SetScript("OnEvent", function()
                local parked = {}
                for parkedBox in pairs(Bars.pending) do parked[#parked + 1] = parkedBox end
                Bars.pending = {}
                for _, parkedBox in ipairs(parked) do Bars.Apply(parkedBox) end
            end)
            Bars.regen = regen
        end
        return
    end
    Bars.Guard(Bars.ApplyConfig, box)
end

-- Applies every box a setting change marked dirty: one Seat and one Refresh per box, however many keys changed
-- (a profile switch changes all five). The OnUpdate exists only between the first change and this flush.
function Bars.Flush()
    if Bars.flusher then Bars.flusher:SetScript("OnUpdate", nil) end
    local dirty = Bars.dirty
    Bars.dirty = {}
    for box in pairs(dirty) do Bars.Apply(box) end
end
GunsightBoxes.Flush = Bars.Flush

function Bars.Request(box)
    if box.retired or not box.bars then return end
    Bars.dirty[box] = true
    Bars.flusher = Bars.flusher or CreateFrame("Frame")
    Bars.flusher:SetScript("OnUpdate", Bars.Flush)
end

local liveBoxes = setmetatable({}, { __mode = "k" })
local function OnSettingChanged()
    for box in pairs(liveBoxes) do Bars.Request(box) end
end
for _, def in pairs(SETTINGS) do Config.OnChange(def.key, OnSettingChanged) end

function Bars.OnEvent(box, event, unit)
    if box.retired or not box.bars or not FS.HasTarget() then return end
    -- The unfiltered RegisterEvent fallback hears every unit: only the target's reach the bars.
    if not IsSecret(unit) and type(unit) == "string" and unit ~= "target" then return end
    if event == "UNIT_HEALTH" or event == "UNIT_MAXHEALTH" then
        if type(UnitHealth) == "function" and type(UnitHealthMax) == "function" then Bars.UpdateHealth(box) end
    else
        Bars.UpdatePower(box)
    end
end

-------------------------------------------------------------------------------
-- The target's unit name (line 1): the only text a box reads itself
-------------------------------------------------------------------------------

local function ReadTargetName()
    local exists = UnitExists and UnitExists("target")
    if not IsSecret(exists) and not exists then return "" end
    local name
    if type(FS.GetFullUnitName) == "function" then
        name = FS.GetFullUnitName("target")
    elseif UnitName then
        name = UnitName("target")
    end
    return name
end

-- Skipped while the INTERRUPTED look is up (it owns line one); ClearVerdict refreshes the name after.
local function RefreshTargetName(box)
    if box.retired or box.verdict then return end
    local name = ReadTargetName()
    if IsSecret(name) then
        WriteLine(box.lineOne, name)                 -- SetText only; never upper-cased
    elseif type(name) == "string" then
        WriteLine(box.lineOne, name:upper())
    else
        WriteLine(box.lineOne, "")
    end
    if box.bars then
        Bars.Measure(box)
        Bars.Seat(box)
    end
end

-- Takes the unit-name listener down: events unregistered and the handler dropped. Shared by every path that
-- abandons a box (a failing build step, a failing rescale registration, Retire), so none of them can leave
-- one live. Safe on a box that never had one.
local function Unlisten(box)
    for _, events in ipairs({ box.events or false, box.barEvents or false }) do
        if events then
            events:UnregisterAllEvents()
            events:SetScript("OnEvent", nil)
        end
    end
end

-------------------------------------------------------------------------------
-- The INTERRUPTED look (mockup drawYour, outage): plain "INTERRUPTED" on line one, the box edge, header,
-- line 2 and tile edge in red (a third tone frame, NOT in the pink / steel lists the interruptible flag
-- drives), the box alpha flickering through one Alpha AnimationGroup. CastBars tells the box through the
-- bar table's onVerdict; a later write through the name sink (GoIdle, the next cast) drops it, and for YOUR box
-- through the timer sink too (the target's timer is a null sink, see BuildMembers).
-------------------------------------------------------------------------------

local function ClearVerdict(box)
    if not box.verdict then return end
    box.verdict = false
    if box.flicker then box.flicker:Stop() end
    for key, tone in pairs(box.tones) do tone:SetShown(key ~= "red") end
    for key, tone in pairs(box.tileTones) do tone:SetShown(key ~= "red") end
    SetLineColor(box.lineOne, 1, box.nameLive and colors.white or colors.muted)
    if box.isTarget then RefreshTargetName(box) end      -- line one is the unit name again
end

local function ShowVerdict(box)
    if box.retired then return end                       -- a stale bar table can still call the hook
    box.verdict = true
    if not box.isTarget then SetBoxShown(box, true) end   -- the look is shown even over a hidden idle box
    for key, tone in pairs(box.tones) do tone:SetShown(key == "red") end
    for key, tone in pairs(box.tileTones) do tone:SetShown(key == "red") end
    WriteLine(box.lineOne, "INTERRUPTED")
    SetLineColor(box.lineOne, 1, colors.red)
    if not box.isTarget then SetTileLive(box, false) end  -- the mockup dims the icon of an interrupted cast
    if box.flicker then
        box.flicker:Stop()
        box.flicker:Play()
    end
end

-- The members CastBars writes to (see the header).
local function BuildMembers(box)
    local members = {}

    -- tabName: line 1 for yours, line 2 (both colour copies) for the target.
    local nameLine = box.isTarget and box.lineTwo or box.lineOne
    local name = {}
    function name.SetText(_, text)
        if box.retired then return end                   -- a stale bar table can still write the sink
        ClearVerdict(box)
        WriteLine(nameLine, text)                        -- at rest (a plain "") the line is blank, no stale spell
        SetNameLive(box, not IsPlainEmpty(text))
        -- Yours: the idle write hides the whole box, any other write (a secret name too) shows it.
        if not box.isTarget then SetBoxShown(box, not IsPlainEmpty(text)) end
    end
    function name.GetStringWidth()
        return nameLine.fonts[1]:GetStringWidth()
    end
    members.tabName = name

    -- timer: yours is the line 2 FontString, the target's goes nowhere.
    local timer = {}
    if box.isTarget then
        -- A true null sink. It does not clear the INTERRUPTED look: every path that writes the timer
        -- (GoIdle, the next cast's start) writes the name sink in the same call, and that one clears it.
        function timer.SetText() end
        function timer.SetFormattedText() end
    else
        -- Line 2 has one FontString per colour (the base and the red copy): every one carries the text.
        local fonts = box.lineTwo.fonts
        function timer.SetText(_, text)
            if box.retired then return end               -- a stale bar table can still write the sink
            ClearVerdict(box)
            if IsPlainEmpty(text) then
                for _, fs in ipairs(fonts) do fs:SetText("") end   -- at rest the timer line is blank
                SetTimerLive(box, false)
            else
                for _, fs in ipairs(fonts) do fs:SetText(text) end
                SetTimerLive(box, true)
            end
        end
        function timer.SetFormattedText(_, fmt, ...)
            if box.retired then return end               -- a stale bar table can still write the sink
            ClearVerdict(box)
            for _, fs in ipairs(fonts) do fs:SetFormattedText(fmt, ...) end
            SetTimerLive(box, true)
        end
    end
    members.timer = timer

    -- icon: forwards to the texture; a nil texture is the idle write (type() is legal on a secret).
    local icon = {}
    function icon.SetTexture(_, tex)
        if box.retired then return end                   -- a stale bar table can still write the sink
        box.icon:SetTexture(tex)
        SetTileLive(box, type(tex) ~= "nil")
    end
    members.icon = icon

    members.tabTicks = box.ticks

    -- CastBars calls this (pcall'd) with "interrupt" after it froze the readout. Only the interrupt has a
    -- look in the mockup's box; a success has none, so CastBars never sends one.
    function members.onVerdict(_, kind)
        if kind == "interrupt" then ShowVerdict(box) end
    end
    return members
end

-- One colour's frame of the box: edge, header (yours only), line 2 and (target) the divider.
local function BuildTone(box, key, color)
    local Theme = FS.Theme
    local tone = CreateFrame("Frame", nil, box.frame)
    FillParent(tone, box.frame)
    box.tones[key] = tone
    box.stroke[key] = Theme.AddCut2Texture(tone, Theme.SLICE_CUT2_OUTLINE_TEXTURE, WithAlpha(color, C.STROKE_A), "BORDER")
    if not box.isTarget then                                     -- the target's box carries no header label
        local head = tone:CreateFontString(nil, "OVERLAY")
        FS.Theme.ApplyMono(head, FontSize(C.HEAD_SIZE), color)   -- a font before the first SetText
        head:SetText("YOU")
        head:SetAlpha(C.HEAD_A)
        box.head[key] = head
        box.headFonts[#box.headFonts + 1] = head
    end
    local l2 = NewFont(tone, box.l2Size, color)
    box.l2[key] = l2
    if box.isTarget then
        box.divider[key] = SolidTexture(tone, color, C.DIV_A)
    end
    if key == "red" then tone:Hide() end                         -- only while INTERRUPTED shows
    return tone
end

-- The tile's own colour frame: its edge.
local function BuildTileTone(box, key, color)
    local Theme = FS.Theme
    local tone = CreateFrame("Frame", nil, box.tile)
    FillParent(tone, box.tile)
    box.tileTones[key] = tone
    Theme.AddCut2Texture(tone, Theme.SLICE_CUT2_OUTLINE_TEXTURE, WithAlpha(color, C.CI_STROKE_A), "BORDER")
    if key == "red" then tone:Hide() end
    return tone
end

-------------------------------------------------------------------------------
-- Layout (build and every rescale: re-seats and re-sizes, creates nothing)
-------------------------------------------------------------------------------

local function SeatBottom(fs, point, rel, relPoint, x, y)
    fs:ClearAllPoints()
    fs:SetPoint(point, rel, relPoint, x, y)
end

-- The frame fills its anchor; the target's box also grows UP by box.grow image px (the bars' room), so its
-- top edge sits above the anchor's and everything seated from the top rides it.
local function SeatFrame(box)
    local frame, anchor = box.frame, box.anchor
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", anchor, "TOPLEFT", 0, box.grow * ui(1))
    frame:SetPoint("BOTTOMRIGHT", anchor, "BOTTOMRIGHT", 0, 0)
end

local function Layout(box)
    local k = ui(1)
    local g = box.geom
    local frame = box.frame
    local grow = box.grow
    if grow > 0 then SeatFrame(box) end
    local wmax = (g.w - 2 * C.PAD) * k
    local left = not box.isTarget

    -- Line 1 and line 2: baseline at the mockup's y, left at the padding.
    box.lineOne.wmax, box.lineTwo.wmax = wmax, wmax
    box.l1:SetWidth(wmax)
    SeatBottom(box.l1, "BOTTOMLEFT", frame, "TOPLEFT", C.PAD * k, -(C.L1_Y + C.L1_SIZE * C.DESCENT) * k)
    for _, fs in pairs(box.l2) do
        fs:SetWidth(wmax)
        SeatBottom(fs, "BOTTOMLEFT", frame, "TOPLEFT", C.PAD * k, -(C.L2_Y + grow + box.l2Size * C.DESCENT) * k)
    end

    -- Header row: your box's name at its outer (left) end, the tick counter at the other. The name is sized
    -- and fitted through box.headLine below (it varies); the target box has no header.
    local headY = (C.HEAD_DY - C.HEAD_SIZE * C.DESCENT) * k
    local headSize = FontSize(C.HEAD_SIZE)
    for _, fs in pairs(box.head) do
        SeatBottom(fs, "BOTTOMLEFT", frame, "TOPLEFT", 0, headY)
    end
    FS.Theme.ApplyMono(box.ticks, headSize, colors.white)
    if left then
        SeatBottom(box.ticks, "BOTTOMRIGHT", frame, "TOPRIGHT", 0, headY)
    else
        SeatBottom(box.ticks, "BOTTOMLEFT", frame, "TOPLEFT", 0, headY)
    end

    -- Target divider: one line, padded.
    for _, d in pairs(box.divider) do
        d:ClearAllPoints()
        d:SetPoint("TOPLEFT", frame, "TOPLEFT", C.PAD * k, -(C.DIV_Y + grow) * k)
        d:SetSize((g.w - 2 * C.PAD) * k, k)
    end

    -- Icon tile: on the box's inner side, centred on its height.
    local tile = box.tile
    tile:ClearAllPoints()
    local y = -((g.h - C.CI) / 2 + grow) * k
    if left then
        tile:SetPoint("TOPLEFT", frame, "TOPRIGHT", C.CIG * k, y)
    else
        tile:SetPoint("TOPRIGHT", frame, "TOPLEFT", -C.CIG * k, y)
    end
    tile:SetSize(C.CI * k, C.CI * k)
    local ins = math.max(1, math.ceil(C.CIC / 2)) * k
    box.icon:ClearAllPoints()
    box.icon:SetPoint("TOPLEFT", tile, "TOPLEFT", ins, -ins)
    box.icon:SetPoint("BOTTOMRIGHT", tile, "BOTTOMRIGHT", -ins, ins)

    -- Type sizes: the line fits run again for the text they hold; the line colours survive.
    -- (Yours line 2 is the timer, whose numbers may be secret: it never holds a plain text, so it keeps
    -- line 2's size.)
    -- The fonts go back to the new base size first, so the fit measures the text at the base size (a plain
    -- name that no longer fits after a rescale shrinks again at once, and one that now fits grows back at
    -- once, not at its next write). line.size always holds the size last applied, so ApplySize's early
    -- return only skips a font that is already there.
    if box.headLine then box.headLine.wmax = (g.w - C.HEAD_RESERVE) * k end
    for _, line in ipairs({ box.lineOne, box.lineTwo, box.headLine }) do
        ApplySize(line, FontSize(line.baseImg))
        RefitLine(line)
    end
    if box.bars then
        Bars.Measure(box)
        Bars.Seat(box)
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

-- The flicker: a delay at alpha 1, then the mockup's seven steps as flat Alpha animations in order, one
-- group on the box frame (no OnUpdate). The group ends back at the frame's own alpha, the mockup's flick 1.
-- nil when the client has no animation groups (the red look then shows without the flicker).
local function BuildFlicker(frame)
    if not HasMethod(frame, "CreateAnimationGroup") then return nil end
    local group = frame:CreateAnimationGroup()
    local order = 0
    local function step(alpha, seconds)
        order = order + 1
        local a = group:CreateAnimation("Alpha")
        a:SetOrder(order)
        a:SetDuration(seconds)
        a:SetFromAlpha(alpha)
        a:SetToAlpha(alpha)
    end
    step(1, C.FLICK_DELAY)
    for _, alpha in ipairs(C.FLICK) do step(alpha, C.FLICK_STEP) end
    return group
end

local function BuildBox(spec)
    local Theme = FS.Theme
    local isTarget = spec.isTarget and true or false
    local box = {
        key = spec.key, anchor = spec.anchor, isTarget = isTarget,
        geom = isTarget and G.BOXR or G.BOXL,
        tones = {}, tileTones = {}, stroke = {}, head = {}, l2 = {}, divider = {},
        toneColors = {}, fb = { pink = {}, steel = {} }, headFonts = {},
        grow = isTarget and C.TGT_GROW or 0, l2Size = isTarget and C.TGT_L2_SIZE or C.L2_SIZE,
    }

    local frame = CreateFrame("Frame", NAME .. spec.key, spec.parent)
    box.frame = frame
    FillParent(frame, spec.anchor)
    if box.grow > 0 then SeatFrame(box) end
    spec.built[#spec.built + 1] = frame

    -- Plate and line 1 (shared by the colours).
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_FILL_TEXTURE, C.FILL, "BACKGROUND", 0)
    box.l1 = NewFont(frame, C.L1_SIZE, colors.muted)
    box.ticks = frame:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(box.ticks, FontSize(C.HEAD_SIZE), colors.white)
    box.ticks:SetText("")
    box.ticks:Hide()
    -- The bars frame is a child of the box (level +1, like the tone frames); its rail hosts sit at +2 and the
    -- StatusBars at +3, so the rails draw above the tone frames' art, and line 1 (a region of the box frame) under
    -- them. The geometry keeps them apart: the rules start at y 26, line 1's baseline is at 23.
    if isTarget then Bars.Build(box) end

    -- The icon tile (shared plate and icon, then one edge frame per colour).
    local tile = CreateFrame("Frame", nil, frame)
    box.tile = tile
    Theme.AddCut2Texture(tile, Theme.SLICE_CUT2_FILL_TEXTURE, WithAlpha(BG, C.CI_FILL_A), "BACKGROUND", 0)
    box.icon = tile:CreateTexture(nil, "ARTWORK")
    box.icon:SetTexCoord(C.ICON_CROP, 1 - C.ICON_CROP, C.ICON_CROP, 1 - C.ICON_CROP)

    -- The colour frames.
    local tones = isTarget and { { "pink", colors.pink }, { "steel", colors.steel }, { "red", colors.red } }
        or { { "base", colors.cyan }, { "red", colors.red } }
    for _, t in ipairs(tones) do
        local key, color = t[1], t[2]
        box.toneColors[key] = color
        local tone = BuildTone(box, key, color)
        local tileTone = BuildTileTone(box, key, color)
        if key == "pink" or key == "steel" then
            local list = box.fb[key]
            list[#list + 1] = tone
            list[#list + 1] = tileTone
        end
    end

    -- Lines. Line 1 has one FontString; line 2 one per colour. A line's colours: line 1 muted until
    -- a cast, line 2 in its colour (the player's timer flips between cyan and muted).
    box.lineOne = NewLine({ box.l1 }, C.L1_SIZE)
    box.lineOne.colors[1] = colors.muted
    local twoFonts, i = {}, 0
    for _, t in ipairs(tones) do
        i = i + 1
        twoFonts[i] = box.l2[t[1]]
    end
    box.lineTwo = NewLine(twoFonts, box.l2Size, isTarget and C.SECRET_L2_SIZE or nil)
    i = 0
    for _, t in ipairs(tones) do
        i = i + 1
        box.lineTwo.colors[i] = (t[1] == "red" and colors.red) or (isTarget and t[2] or colors.muted)
    end
    box.nameLive, box.timerLive = false, false
    if not isTarget then
        -- Yours: the header is the character's name, fitted like the other plain text (one FontString per tone).
        box.headLine = NewLine(box.headFonts, C.HEAD_SIZE)
        local i2 = 0
        for _, t in ipairs(tones) do
            i2 = i2 + 1
            box.headLine.colors[i2] = t[2]
        end
    end
    box.flicker = BuildFlicker(frame)

    box.members = BuildMembers(box)
    box.regions = {
        icon = box.icon, ticks = box.ticks,
        name = isTarget and box.l2.pink or box.l1,
        timer = (not isTarget) and box.l2.base or nil,
    }

    -- Rest look: the target has no tile between casts, yours a dimmed empty one.
    SetTileLive(box, false)
    Layout(box)

    if isTarget then
        RefreshTargetName(box)
        RefreshTargetShown(box)
        Bars.Guard(Bars.ApplyConfig, box)
    else
        RefreshPlayerName(box)
        frame:Hide()                                 -- yours exists only while a cast is live
    end

    -- The unit-name listener is the second to last step: a build that throws earlier never leaves it live on a box
    -- that was hidden, and one that fails inside this step unregisters what it had registered. (A box that built
    -- whole and is dropped later by its caller goes through GunsightBoxes.Retire.)
    local events = CreateFrame("Frame", nil, frame)
    box.events = events
    local okEvents, errEvents = pcall(function()
        if isTarget then
            events:RegisterEvent("PLAYER_TARGET_CHANGED")
            events:RegisterEvent("PLAYER_ENTERING_WORLD")        -- as the tape, the dots and the horizon re-read it
            if not pcall(events.RegisterUnitEvent, events, "UNIT_NAME_UPDATE", "target") then
                events:RegisterEvent("UNIT_NAME_UPDATE")
            end
            events:SetScript("OnEvent", function()
                RefreshTargetName(box)
                RefreshTargetShown(box)
                Bars.Guard(Bars.Refresh, box)
            end)
            -- The bar events get a frame of their own: RegisterUnitEvent's whitelist is frame-wide, and the
            -- listener above also takes events that are not for "target".
            local barEvents = CreateFrame("Frame", nil, frame)
            box.barEvents = barEvents
            for _, event in ipairs(C.BAR_EVENTS) do
                if not pcall(barEvents.RegisterUnitEvent, barEvents, event, "target") then
                    barEvents:RegisterEvent(event)
                end
            end
            barEvents:SetScript("OnEvent", function(_, event, unit) Bars.Guard(Bars.OnEvent, box, event, unit) end)
        else
            -- the character name is not always ready at build
            events:RegisterEvent("PLAYER_LOGIN")
            events:RegisterEvent("PLAYER_ENTERING_WORLD")
            events:SetScript("OnEvent", function() RefreshPlayerName(box) end)
        end
    end)
    if not okEvents then
        Unlisten(box)
        error(errEvents, 0)
    end

    -- The rescale callback is the LAST step, so a box dropped by a failure above never keeps a Layout
    -- callback (a registered callback cannot be removed). If registering itself throws, the listener
    -- goes down with the box. A box retired later keeps the callback but it does nothing (box.retired).
    if FS.Layout and FS.Layout.OnRescale then
        local okRescale, errRescale = pcall(FS.Layout.OnRescale, function()
            if not box.retired then Layout(box) end
        end)
        if not okRescale then
            Unlisten(box)
            error(errRescale, 0)
        end
    end
    if isTarget then liveBoxes[box] = true end
    return box
end

-- Takes a built box out of service for a caller that drops it after Build returned (GunsightTape, when a later
-- build step fails): hidden, the unit-name listener down, the flicker stopped, and the rescale callback (which
-- Layout.OnRescale cannot unregister) turned into a no-op by the retired flag. Idempotent, never throws.
function GunsightBoxes.Retire(box)
    if type(box) ~= "table" or box.retired then return end
    box.retired = true
    pcall(Unlisten, box)
    if box.flicker then pcall(box.flicker.Stop, box.flicker) end
    if box.frame then pcall(box.frame.Hide, box.frame) end
end

-- Builds one box. spec = { key, parent (the tape's piece frame), anchor (boxL / boxR), isTarget }.
-- Returns the box, or nil and a reason (whatever was built is hidden; nothing is registered).
function GunsightBoxes.Build(spec)
    if type(spec) ~= "table" or not spec.parent or not spec.anchor or not spec.key then
        return nil, "bad spec"
    end
    spec = { key = spec.key, parent = spec.parent, anchor = spec.anchor, isTarget = spec.isTarget, built = {} }
    local ok, box = pcall(BuildBox, spec)
    if ok then return box end
    for _, frame in ipairs(spec.built) do frame:Hide() end
    return nil, tostring(box)
end
