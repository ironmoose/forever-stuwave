-- Forever STUwave: five second rule tab
--
-- A second shoulder on the Console chassis for every class whose power is mana (mockups/five-second-rule-compact-2026-10-14.html,
-- the D2 face with the LED readout and digit option B): one 92.8 x 49 design px face with no name labels, the chrome of the
-- Shaman buff tab (BuffTab.lua), seated after the class's own tab when it has one and in its place otherwise (ClassShoulder.lua
-- owns the seat). It is a player side cue, always there, not gated on a target, and display only: no click, no binding. Two
-- hover zones, one tooltip each:
--
--   * CELLS (hero tile and gauge): a 14 segment LED readout, our own art (Media/Textures/led_segments.tga, one texture per
--     segment, lit or unlit by SetVertexColor, with a blurred copy of the segment under each lit one), and a ten segment gauge under it. A mana spend starts a five second window; the
--     gauge is amber and drains one segment every half second right to left, the readout counts in tenths behind a LED tilde and
--     says SUSPENDED in the tooltip. At 0.0 the held digits turn cyan, a band sweeps the face once and each cell flips from digit to
--     the word REGEN under it, the rim flashes once (the pulse), a short sound plays if the player turned it on, and a few seconds
--     later the face fades to its dim idle look.
--   * RATE (the bottom line): mana per second with a coloured bar under it and a retention chip. The pair GetPowerRegen returns is
--     plain out of combat only, so it is read out of combat and kept; the bar is dashed while the numbers on show are the kept
--     ones. The casting rate shows while the window runs, the full rate otherwise. The chip is the percent of the full rate that
--     casting keeps (a talent such as Meditation), cyan when above 0, a hollow "0%" otherwise, "--" with no reading.
--
-- Motion (the SETTINGS under `motion`, each with its own switch) is a pure function of the ledger and the clock, Motion() below:
-- the cast flash, the digit dip and warm last second, the whole second pulse, the gauge flicker, the regen sweep, the tick pulse,
-- the idle glow and the kept rate stutter. The quick ones (flash, sweep, count) run the ticker every frame, the slow ones at
-- TICK_AMBIENT. The idle glow is the exception: it is two Alpha AnimationGroups on the rim's ring and glow textures, so a
-- tab at rest has no ticker work (half second passes) and a hidden tab has no ticker at all. At most one strong motion plays
-- at a time; the rest are faint.
--
-- Crisp: every size and offset is a whole count of physical pixels (the design px times the scale, rounded edge by edge), the
-- LED art is drawn one texel to a pixel and never scaled fractionally, the textures snap to the pixel grid with no texel bias
-- where the client has the calls, and the glow is its own texture behind the shapes.
--
-- Client facts it stands on (research 2026-10-14, Forever 1.60.1) and its limits. All of it is an ESTIMATE from the player's own
-- casts, which the tooltip says:
--   * UNIT_SPELLCAST_SUCCEEDED for "player" has plain arguments and C_Spell.GetSpellPowerCost is a plain static table, so a
--     cast is a spend when it lists a type 0 (mana) cost above 0. Mana itself is NEVER read (UnitPower on mana is always
--     secret): there is no tick, no "full in N s", no low mana warning. A cost that cannot be read plainly starts nothing.
--   * A free cast that only an aura makes (a Clearcasting proc) is invisible in combat, so it can overstate the window. Free
--     casts the player causes themselves (Inner Focus, Nature's Swiftness) are not tracked either.
--   * CHANNELS ARE UNVERIFIED on Forever. The default is the conservative one: a channel that costs mana holds the window at
--     the full five seconds until it ends, then the five seconds run from the end (UNIT_SPELLCAST_CHANNEL_STOP, or UnitChannelInfo
--     saying nothing is channeling, which backs the event up). Cancelled and interrupted casts send no SUCCEEDED and start
--     nothing; whether Forever charges mana for them is unverified.
--   * GetPowerRegen is secret in combat. The kept numbers go stale if gear or buffs change during a fight and are read again
--     the first time the API answers plainly. Buff driven regen (Blessing of Wisdom) is not in the API's numbers at all. The
--     retention percent is casting/full from that pair, so 0.001 (the game's floor) reads as 0% and a few MP5 as 3%.
--   * A Druid shows the tab in a mana form only (UnitPowerType, read when the form changes); an unreadable answer shows it. The
--     window keeps counting while the tab is hidden. The shoulder art follows at the next Refresh, out of combat.
--   * The sound is SOUNDKIT.TELL_MESSAGE (a guess for this client), feature detected and off by default.
--
-- Nothing here is protected: the host and its zones are plain frames, so building, the paint, the master toggle and the Druid
-- hide are legal in combat. Only the seat (SetPoint onto the Console, which ClassShoulder.lua parks in combat) waits for
-- PLAYER_REGEN_ENABLED. Loads after BuffTab.lua and before ConfigWindow.lua (which reads SETTINGS at page build). Nothing here
-- is verified in game.

local _, FS = ...

local Tab = {}
FS.FiveSecondTab = Tab

local FH = FS.FrameHelpers
local IsSecret = FS.IsSecret
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local FT = {
    KEY = "fivesecond",             -- ClassShoulder's name for this shoulder
    CLASSES = {
        PRIEST = true, MAGE = true, WARLOCK = true, HUNTER = true, DRUID = true, SHAMAN = true, PALADIN = true,
    },
    WINDOW = 5,                     -- seconds of suspended regen after a mana spend
    HOLD = 3,                       -- seconds the REGEN look is held at full strength
    FADE = 1,                       -- seconds it then takes to reach the idle look
    PULSE_TIME = 0.9,               -- seconds the rim flash takes to die away
    LATE = 1.5,                     -- a regen seen later than this after its end makes no pulse and no sound
    CHANNEL_GRACE = 1,              -- seconds after a channel starts before UnitChannelInfo is trusted to say it ended
    READ_EVERY = 1,                 -- seconds between GetPowerRegen reads (a plain answer only out of combat)
    TICK_SLOW = 0.5, TICK_AMBIENT = 0.05,
    -- The face in design px, from the host's top left (the page's D2 numbers). The host is the buff tab's size.
    HOST_W = 92.8, HOST_H = 49,
    HERO = { x = 6, y = 6, w = 81, h = 16 },    -- the tile the readout sits in (chamfer 6)
    FACE_H = 37,                                 -- the clipped wash of the cast flash: x 6..87, y 6..43
    LED_CX = 46,                                 -- the readout is centred here, vertically on the hero tile
    CELL_W = 10, CELL_H = 12, ATLAS = 64,        -- a cell in texels, the atlas side
    COUNT_W = 34, WORD_W = 58,                   -- tilde 8 + 2 + digit 10 + dot 4 + digit 10; five cells and four gaps of 2
    WORD_X = 17,                                 -- the word's left, so the cell centres are 22, 34, 46, 58, 70
    DIGIT_X = { tilde0 = 29, tilde = 33, d1 = 44, dot = 51, d2 = 58 },  -- the counting group's part centres (sweep tests)
    GAUGE_N = 10, GAUGE_WELL = { x = 6, w = 81 }, GAUGE_Y = 24, GAUGE_H = 5,
    GAUGE_X = 7, GAUGE_PITCH = 8, GAUGE_SEG_W = 7, GAUGE_SEG_Y = 25, GAUGE_SEG_H = 3,
    GAUGE_OFF = 0.22, GAUGE_IDLE = 0.3, GAUGE_BREATH_LO = 0.24, GAUGE_BREATH_HI = 0.38,
    RATE_ZONE_Y = 30, RATE_X = 8, RATE_BASE = 39, RATE_BAR_Y = 41, RATE_ROOM = 35,
    DASH_PITCH = 5, DASH_ON = 3, DASHES = 9,
    CHIP = { x = 57, y = 31, w = 30, h = 12 }, CHIP_C = 3, GLOW_PAD = 3, CHIP_ROOM = 28, CHIP_IDLE_TEXT = 0.65,
    -- The rim chrome in one place: the ring and glow alphas per state. Idle is the quiet violet ring; suspended is amber; regen
    -- is cyan, its glow flaring once on top (the pulse); the idle glow breathes on top of the quiet look.
    CHROME = {
        idleRing = 0.4, idleGlow = 0,
        suspRing = 0.7, suspGlow = 0,
        regenRing = 1, regenGlow = 0.45, flareGlow = 0.5,
        breathRing = 0.3, breathRingSwing = 0.3, breathGlow = 0.45,
        hoverGlow = 0.6,            -- the floor of the glow under the mouse (the ring is full cyan)
        chipGlow = 0.4, chipTick = 0.4,
    },
    IDLE_ALPHA = 0.72,              -- the dim look of the whole face at rest
    -- the LED look
    GHOST_COUNT = 0.07, GHOST_LIFT = 0.06, GHOST_RES = 0.08, GHOST_IDLE = 0.05, WORD_IDLE = 0.55,
    GLOW_STEADY = 0.5, GLOW_PULSE = 0.6,
    -- the glow is a soft copy under each lit piece, never a block behind the readout: led_segment_glow.tga is the segment atlas
    -- blurred (a cell's glow is the 14 x 16 texel rect two texels past the cell, a tilde bar or the dot's the 6 x 6 one),
    -- and led_glow.tga is the soft box stretched over a gauge segment plus GAUGE_GLOW_PAD design px on every side
    SEG_GLOW_PAD = 2, SEG_GLOW_W = 14, SEG_GLOW_H = 16, BLOCK_GLOW = 6, BLOCK_SLOT = 14, GAUGE_GLOW_PAD = 3,
    -- the motion, seconds unless noted
    FLASH_TIME = 0.5, FLASH_ALPHA = 0.3,
    DIP_TIME = 0.035, DIP_DEPTH = 0.22,
    PULSE_SECOND = 0.28, PULSE_RISE = 0.03,
    FLICK_TIME = 0.3,
    SWEEP_TIME = 1,
    TICK_FIRST = 1.5, TICK_EVERY = 2, TICK_TIME = 0.5,
    BREATH_TIME = 3.9,
    GLITCH_MS = 320, GLITCH_EVERY_MS = 2400,
    FX_NAMES = { "flash", "digits", "wpulse", "drop", "sweep", "tick", "breath", "glitch" },
    CODE_PX = 10, RATE_PX = 11, RATE_LONG_PX = 9,
    MIN_PX = 6, ADVANCE = 0.5615,
    host = nil, cells = nil, rate = nil,
    built = false,
    seated = false,
    pendingSync = false,
    switchesDirty = true,
    sigCells = {}, sigRate = {},
    warned = {},
}
Tab.FT = FT

-- Settings: read by the config window at page build, each explained there by its `tip` (a ? icon), never by a helper line.
local SETTINGS = {
    enabled = {
        key = "fivesecond.enabled", default = true, label = "Mana regen module",
        tip = "A tab on the Console that counts the seconds after you spend mana, while your regen is suspended, "
            .. "and shows your mana per second. Off hides it.",
    },
    pulse = {
        key = "fivesecond.pulse", default = true, label = "Regen pulse",
        tip = "Flashes the tab once when your regen resumes.",
    },
    sound = {
        key = "fivesecond.sound", default = false, label = "Regen sound",
        tip = "Plays a short sound when your regen resumes.",
    },
    -- the motion: a master and one switch for each effect (labels and tips as the page's list)
    motion = {
        key = "fivesecond.motion", default = true, label = "Animate the tab",
        tip = "Turns all motion on the tab on or off. Off keeps the tab still: only its colours and numbers change.",
    },
    flash = {
        key = "fivesecond.fx.flash", default = true, label = "Cast flash",
        tip = "A brief flash across the tab when you spend mana.",
    },
    digits = {
        key = "fivesecond.fx.digits", default = true, label = "LED digit motion",
        tip = "Digit motion: a short flash or fade as the digits change.",
    },
    wpulse = {
        key = "fivesecond.fx.wpulse", default = true, label = "Whole second pulse",
        tip = "Whole second pulse: the countdown flashes as each second passes.",
    },
    drop = {
        key = "fivesecond.fx.drop", default = true, label = "Gauge flicker",
        tip = "The gauge segment that just emptied flickers once.",
    },
    sweep = {
        key = "fivesecond.fx.sweep", default = true, label = "Regen sweep",
        tip = "A bright sweep crosses the gauge and the readout when your regen resumes.",
    },
    tick = {
        key = "fivesecond.fx.tick", default = true, label = "Regen tick pulse",
        tip = "A short pulse on the rate every two seconds while regen runs. It is a timer, not a reading of your mana.",
    },
    breath = {
        key = "fivesecond.fx.breath", default = true, label = "Idle glow",
        tip = "The tab glows softly while it waits.",
    },
    glitch = {
        key = "fivesecond.fx.glitch", default = true, label = "Kept and unreadable stutter",
        tip = "The rate stutters now and then while it shows a number kept from before the fight, or none at all.",
    },
}
Tab.SETTINGS = SETTINGS
if FS.Config and FS.Config.RegisterDefault then
    for _, def in pairs(SETTINGS) do FS.Config.RegisterDefault(def.key, def.default) end
end

local function Setting(def)
    local config = FS.Config
    if config and config.Get then
        local value = config.Get(def.key)
        if type(value) == "boolean" then return value end
    end
    return def.default
end

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- One chat line per distinct problem, once per session (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if FT.warned[key] then return end
    FT.warned[key] = true
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text) end
end

-- The player's class token, or nil when it cannot be read plainly.
local function PlayerClass()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) or type(token) ~= "string" then return nil end
    return token
end

local function PlainNumber(v)
    if IsSecret(v) then return nil end
    if type(v) == "number" then return v end
    return nil
end

-------------------------------------------------------------------------------
-- Who gets it
-------------------------------------------------------------------------------

-- true for a class whose power is mana.
function Tab.Applies()
    local token = PlayerClass()
    return token ~= nil and FT.CLASSES[token] == true
end

-- A Druid in cat or bear form (or any form whose power is not mana) hides the cue. nil is "cannot tell", which shows it.
local function ManaForm()
    if PlayerClass() ~= "DRUID" then return true end
    if type(UnitPowerType) ~= "function" then return true end
    local ok, powerType, token = pcall(UnitPowerType, "player")
    if not ok or IsSecret(powerType) or IsSecret(token) then return true end
    if type(powerType) == "number" then return powerType == 0 end
    if type(token) == "string" then return token == "MANA" end
    return true
end

local function RefreshForm()
    FT.manaForm = ManaForm()
end

-- true while the tab should be seen: a mana class, the master toggle on, and not a Druid form without mana.
function Tab.Shown()
    if not Tab.Applies() then return false end
    if not Setting(SETTINGS.enabled) then return false end
    if FT.manaForm == nil then RefreshForm() end
    return FT.manaForm ~= false
end

-- true once this tab is built: ClassShoulder.lua then stands its block.
function Tab.OwnsShoulder()
    return FT.built and Tab.Shown() or false
end

-------------------------------------------------------------------------------
-- The ledger: when the five seconds started and ended
-------------------------------------------------------------------------------

local L = {
    endsAt = nil,       -- GetTime() when regen resumes
    resumed = false,    -- the end has been seen (the pulse and the sound are spent)
    channel = false,    -- a mana channel is in progress: the window is held open
    channelAt = 0,
    pulseAt = nil,      -- GetTime() the rim flash started
    startAt = nil,      -- GetTime() the window was last started (the cast flash)
}
local view = {
    phase = "idle",     -- "idle" | "susp" | "res"
    t = 0,              -- seconds until regen (while "susp")
    fade = 0,           -- 1 while the window runs and while REGEN is held, down to 0 at the idle look
    pulse = 0,          -- 1 at the pulse start down to 0
    pulses = 0, sounds = 0,
    base = nil, casting = nil, ret = nil,
    rate = nil,         -- the number on show (casting while "susp", base otherwise)
    rateText = nil,     -- "12.4" or nil
    cached = false,
}

local rate = {
    base = nil, casting = nil, live = false, baseText = nil, castText = nil, retPct = nil, nextRead = 0,
}

local function Now()
    return GetTime()
end

-- true: the spell spends mana; false: it plainly does not (no cost, another power, a zero cost); nil: cannot be told.
-- An entry whose fields are secret could hide the mana one, so it makes the whole answer nil.
local function SpendsMana(spellID)
    local api = _G.C_Spell
    if type(api) ~= "table" or type(api.GetSpellPowerCost) ~= "function" then return nil end
    local ok, costs = pcall(api.GetSpellPowerCost, spellID)
    if not ok or IsSecret(costs) then return nil end
    if costs == nil then return false end
    if type(costs) ~= "table" then return nil end
    local mana = (_G.Enum and Enum.PowerType and Enum.PowerType.Mana) or 0
    local spends = false
    for i = 1, #costs do
        local entry = costs[i]
        if IsSecret(entry) or type(entry) ~= "table" then return nil end
        local kind, cost, perSecond = entry.type, entry.cost, entry.costPerSec
        if IsSecret(kind) or IsSecret(cost) or IsSecret(perSecond) then return nil end
        if kind == mana then
            if type(cost) == "number" and cost > 0 then spends = true end
            if type(perSecond) == "number" and perSecond > 0 then spends = true end
        end
    end
    return spends
end

-- nil when it cannot be told, else whether the player is channeling.
local function ChannelActive()
    if type(UnitChannelInfo) ~= "function" then return nil end
    local ok, name = pcall(UnitChannelInfo, "player")
    if not ok or IsSecret(name) then return nil end
    return name ~= nil
end

local function StartWindow(now)
    FT.fast = true          -- the ticker runs every frame from the next one, not from its next slow pass
    L.startAt = now
    L.endsAt = now + FT.WINDOW
    L.resumed = false
    L.pulseAt = nil
end

-- A spell the player finished casting (or an instant): a mana spend restarts the full window.
function Tab.OnCast(spellID, now)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    if SpendsMana(spellID) ~= true then return end
    StartWindow(now or Now())
end

function Tab.OnChannelStart(spellID, now)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    if SpendsMana(spellID) ~= true then return end
    now = now or Now()
    StartWindow(now)
    L.channel, L.channelAt = true, now
end

function Tab.OnChannelStop(now)
    if not L.channel then return end
    L.channel = false
    StartWindow(now or Now())
end

function Tab.Reset()
    L.endsAt, L.resumed, L.channel, L.pulseAt, L.startAt = nil, false, false, nil, nil
end

local function Chime()
    if type(PlaySound) ~= "function" then return end
    local kit = _G.SOUNDKIT
    local id = type(kit) == "table" and kit.TELL_MESSAGE or nil
    if type(id) ~= "number" then return end
    pcall(PlaySound, id)
end

-- Regen came back: one pulse and one sound, when the tab is up and the end was not missed.
local function RegenBegan(now)
    L.resumed = true
    if not (FT.host and FT.host:IsShown()) then return end
    if now - L.endsAt > FT.LATE then return end
    -- a pulse is motion: with the master off there is nothing to see, so none is started or counted
    if Setting(SETTINGS.pulse) and Setting(SETTINGS.motion) then
        L.pulseAt = now
        view.pulses = view.pulses + 1
    end
    if Setting(SETTINGS.sound) then
        view.sounds = view.sounds + 1
        Chime()
    end
end

-- Reads the regen pair. A secret, missing or odd answer keeps what was kept and marks the numbers as kept.
local function ReadRegen()
    local fn = _G.GetPowerRegen
    if type(fn) ~= "function" then rate.live = false return end
    local ok, base, casting = pcall(fn)
    if not ok then rate.live = false return end
    base, casting = PlainNumber(base), PlainNumber(casting)
    if not base or not casting or base < 0 or casting < 0 then rate.live = false return end
    rate.live = true
    if base ~= rate.base or casting ~= rate.casting then
        rate.base, rate.casting = base, casting
        rate.baseText = string.format("%.1f", base)
        rate.castText = string.format("%.1f", casting)
        local pct = base > 0 and math.floor(casting / base * 100 + 0.5) or 0
        rate.retPct = pct >= 1 and pct or nil
    end
end

local Motion     -- the motion model below (defined after the view it reads)

-- Brings the ledger to `now` (a spend, an end, a fade) and the view with it. Idempotent for one `now`.
function Tab.Update(now)
    now = now or Now()
    if L.channel and now - L.channelAt > FT.CHANNEL_GRACE and ChannelActive() == false then
        L.channel = false
        StartWindow(now)
    end
    local phase, t, fade = "idle", 0, 0
    local endsAt = L.endsAt
    if endsAt then
        if L.channel then
            phase, t, fade = "susp", FT.WINDOW, 1
        elseif now < endsAt then
            phase, t, fade = "susp", endsAt - now, 1
        else
            if not L.resumed then RegenBegan(now) end
            local since = now - endsAt
            if since < FT.HOLD then
                phase, fade = "res", 1
            elseif since < FT.HOLD + FT.FADE then
                phase, fade = "res", 1 - (since - FT.HOLD) / FT.FADE
            else
                L.endsAt, L.pulseAt = nil, nil
            end
        end
    end
    local pulse = 0
    if L.pulseAt then
        pulse = 1 - (now - L.pulseAt) / FT.PULSE_TIME
        if pulse <= 0 then pulse, L.pulseAt = 0, nil end
    end
    if now >= rate.nextRead then
        rate.nextRead = now + FT.READ_EVERY
        ReadRegen()
    end
    view.phase, view.t, view.fade, view.pulse = phase, t, fade, pulse
    view.base, view.casting, view.ret = rate.base, rate.casting, rate.retPct
    view.cached = rate.base ~= nil and not rate.live
    if phase == "susp" then
        view.rate, view.rateText = rate.casting, rate.castText
    else
        view.rate, view.rateText = rate.base, rate.baseText
    end
    Motion(now)
    return view
end

function Tab.View()
    return view
end

-------------------------------------------------------------------------------
-- Tooltips
-------------------------------------------------------------------------------

local function Colors()
    local T = FS.Theme
    return T.COLOR_AMBER, T.COLOR_POWER, T.COLOR_MUTED
end

-- The tooltip as lines { text, color, wrap }; pure data from the view, which the harness reads.
function Tab.TipLines(which)
    local amber, cyan, muted = Colors()
    local white = { 1, 1, 1 }
    local lines = {}
    local function add(text, color, wrap) lines[#lines + 1] = { text, color, wrap } end
    local v = view
    if which == "cells" then
        if v.phase == "susp" then
            add("Mana regen", amber)
            add(string.format("About %.1f s until regen resumes.", math.max(0, v.t)), white, true)
        else
            add("Mana regen", cyan)
            add("Regen is running.", white, true)
        end
        add("Estimate from your own casts. Free casts are not seen.", muted, true)
        return lines
    end
    if v.base == nil then
        add("Mana regen", muted)
        add("The regen rate cannot be read yet.", white, true)
        return lines
    end
    add("Mana regen", cyan)
    add(string.format("%s per second now, %s once regen resumes.", v.rateText, rate.baseText), white, true)
    if v.cached then add("Read out of combat, kept while you fight.", muted, true) end
    if v.ret then add(string.format("You keep %d%% of it while you cast.", v.ret), muted, true) end
    return lines
end

-- `refresh`: the zone already owns the tooltip, so only its lines are rewritten (no new SetOwner, which would clear and
-- re-place it every tick); a client without ClearLines anchors again.
local function ShowTooltip(zone, refresh)
    local tip = GameTooltip
    if not tip then return end
    local lines = Tab.TipLines(zone.fsKey)
    if refresh and type(tip.ClearLines) == "function" then
        tip:ClearLines()
    else
        FH.AnchorTooltip(zone)
    end
    for _, line in ipairs(lines) do
        local c = line[2]
        tip:AddLine(line[1], c[1], c[2], c[3], line[3])
    end
    tip:Show()
end

local function TipIsOurs(zone)
    local tip = GameTooltip
    if not (tip and zone.fsHover) then return false end
    if type(tip.IsOwned) == "function" then return tip:IsOwned(zone) and true or false end
    if type(tip.GetOwner) == "function" then return tip:GetOwner() == zone end
    return true
end

-------------------------------------------------------------------------------
-- Motion: pure functions of the ledger and the clock
-------------------------------------------------------------------------------

-- The motion switches as last read: on.<name> is true when the master AND that switch are on. Re-read when any of them
-- changes (Apply registers the callbacks); a client without Config.OnChange re-reads every pass.
local on = { master = true }

local function ReadSwitches()
    local master = Setting(SETTINGS.motion)
    on.master = master
    for _, name in ipairs(FT.FX_NAMES) do
        on[name] = master and Setting(SETTINGS[name])
    end
    FT.switchesDirty = not FT.watching
end

-- What moves right now, from the view and the clock; Tab.Update fills it. 0 / false / nil mean "nothing moves".
local fx = {
    flash = 0,          -- 1 at a cast down to 0 over FLASH_TIME: the white wash over the face
    dip = false,        -- the first DIP_TIME of every new tenth: the lit segments dim a little
    warm = 0,           -- 0..1 over the last second of the count: amber through white toward cyan
    zp = 0,             -- the whole second pulse, 0..1, at 4.0 3.0 2.0 1.0
    dropSeg = 0,        -- the gauge segment (1 based) that just emptied and flickers, 0 for none
    dropA = 0,          -- its flicker alpha
    pp = 1,             -- the regen sweep position 0..1 (1 when it is over or switched off)
    flare = 0,          -- 0..1..0 over the pulse: the rim glow at REGEN
    tick = 0,           -- 1 at a mana tick estimate down to 0 over TICK_TIME
    breathing = false,  -- the idle glow is on (its AnimationGroups play); the animation, not Motion, moves it
    glitchA = 1, glitchDx = 0,
}
Tab.Fx = function() return fx end

local function Clamp01(v)
    if v < 0 then return 0 end
    if v > 1 then return 1 end
    return v
end

-- The dying flicker of a segment that just emptied: age in seconds.
local function Flick(age)
    if age < 0 or age > FT.FLICK_TIME then return 0 end
    return (1 - age / FT.FLICK_TIME) * (0.55 + 0.45 * math.sin(age * 110))
end

Motion = function(now)
    if FT.switchesDirty then ReadSwitches() end
    local v = view
    local susp = v.phase == "susp"
    local t = v.t
    local flash, dip, warm, zp, dropSeg, dropA = 0, false, 0, 0, 0, 0
    if susp then
        if on.flash and L.startAt then
            local age = now - L.startAt
            if age >= 0 and age < FT.FLASH_TIME then flash = 1 - age / FT.FLASH_TIME end
        end
        -- the digit motion never runs under the cast flash
        if on.digits and flash <= 0 and t <= FT.WINDOW - 0.05 then
            local tenths = math.floor(t * 10 + 0.5)
            local age = tenths * 0.1 + 0.05 - t
            dip = age >= 0 and age < FT.DIP_TIME
            if t < 1 then warm = Clamp01(1 - t) end
        end
        if on.wpulse then
            local k = math.ceil(t - 0.05)
            local age = k + 0.05 - t
            if k >= 1 and k <= FT.WINDOW - 1 and age >= 0 and age < FT.PULSE_SECOND then
                zp = age < FT.PULSE_RISE and age / FT.PULSE_RISE
                    or (1 - (age - FT.PULSE_RISE) / (FT.PULSE_SECOND - FT.PULSE_RISE)) ^ 1.5
            end
        end
        if on.drop and t > 0.3 then
            local lit = t / FT.WINDOW * FT.GAUGE_N
            local jd = math.ceil(lit)
            local fl = Flick((jd - lit) * (FT.WINDOW / FT.GAUGE_N)) * (1 - zp)
            if fl > 0 and jd >= 1 and jd < FT.GAUGE_N then dropSeg, dropA = jd + 1, 0.9 * fl end
        end
    end
    local pp, tick = 1, 0
    local endsAt = L.endsAt
    if v.phase == "res" and endsAt then
        local since = now - endsAt
        if on.sweep and since < FT.SWEEP_TIME then pp = Clamp01(since / FT.SWEEP_TIME) end
        if on.tick then
            local into = since - FT.TICK_FIRST
            if into >= 0 then
                local age = into % FT.TICK_EVERY
                if age < FT.TICK_TIME then tick = 1 - age / FT.TICK_TIME end
            end
        end
    end
    local flare = 0
    if on.master and v.pulse > 0 then flare = math.sin(math.pi * (1 - v.pulse)) end
    local shown = FT.host ~= nil and FT.host:IsVisible()   -- not IsShown: hiding the whole interface stops it too
    local breathing = shown and on.breath and v.phase == "idle"
    local glitchA, glitchDx, glitchSoon = 1, 0, false
    if on.glitch and not susp and pp >= 1 and (v.cached or v.base == nil) then
        local gp = (now * 1000) % FT.GLITCH_EVERY_MS
        if gp < FT.GLITCH_MS then
            glitchA = 0.35 + 0.65 * math.abs(math.sin(gp * 0.09))
            glitchDx = math.sin(gp * 0.5) > 0 and 1 or -1
        end
        -- the faster ticker is wanted only from the slow pass before the window to the end of it
        glitchSoon = gp < FT.GLITCH_MS or gp >= FT.GLITCH_EVERY_MS - FT.TICK_SLOW * 1000
    end
    fx.flash, fx.dip, fx.warm, fx.zp, fx.dropSeg, fx.dropA = flash, dip, warm, zp, dropSeg, dropA
    fx.pp, fx.flare, fx.tick, fx.breathing, fx.glitchA, fx.glitchDx = pp, flare, tick, breathing, glitchA, glitchDx
    -- the ticker runs every frame while something quick moves, at TICK_AMBIENT while a short slow one does, and not at all
    -- while the tab is hidden; the idle glow needs none of it (an animation)
    FT.fast = shown and (susp or (on.master and v.pulse > 0) or pp < 1 or flash > 0)
    FT.ambient = shown and (FT.fast or tick > 0 or v.phase == "res" or glitchSoon)
end

-------------------------------------------------------------------------------
-- LED art: fourteen segments a cell, from the led_segments atlas
-------------------------------------------------------------------------------

-- The atlas slot order (generate_led_segments.py SEGMENT_ORDER): slot n is column n % 4, row n // 4 of 16 x 16 texels in a
-- 64 x 64 image; a cell is 10 x 12 texels in the slot's top-left corner.
local SEGMENT_ORDER = { "a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m" }
Tab.SEGMENT_ORDER = SEGMENT_ORDER

-- Which segments each character lights (the page's SEG14 table).
local GLYPH_TEXT = {
    ["0"] = "a b c d e f", ["1"] = "b c", ["2"] = "a b g1 g2 e d", ["3"] = "a b c d g1 g2", ["4"] = "f b g1 g2 c",
    ["5"] = "a f g1 g2 c d", ["6"] = "a f e d c g1 g2", ["7"] = "a b c", ["8"] = "a b c d e f g1 g2",
    ["9"] = "a b c d f g1 g2", R = "a b f e g1 g2 m", E = "a f e d g1 g2", G = "a f e d c g2", N = "f e b c h m",
}
Tab.GLYPH_TEXT = GLYPH_TEXT

local GLYPH = {}
do
    local index = {}
    for n, name in ipairs(SEGMENT_ORDER) do index[name] = n end
    for ch, text in pairs(GLYPH_TEXT) do
        local lit = {}
        for name in text:gmatch("%S+") do lit[index[name]] = true end
        GLYPH[ch] = lit
    end
end

-- The tilde of the estimate mark: four 2 x 2 bars, (x, y) in texels from the readout's left and top.
local TILDE = { { 0, 5 }, { 2, 4 }, { 4, 6 }, { 6, 5 } }

local scratch = { 0, 0, 0 }

local function Lerp(a, b, t)
    return a + (b - a) * t
end

local function Mix(a, b, t)
    return Lerp(a[1], b[1], t), Lerp(a[2], b[2], t), Lerp(a[3], b[3], t)
end

-- Moves `a` toward `b` by t and writes it to a texture (or a font string) with the alpha.
local function Tint(region, a, b, t, alpha)
    region:SetVertexColor(Lerp(a[1], b[1], t), Lerp(a[2], b[2], t), Lerp(a[3], b[3], t), alpha)
end

local function TintText(region, a, b, t, alpha)
    region:SetTextColor(Lerp(a[1], b[1], t), Lerp(a[2], b[2], t), Lerp(a[3], b[3], t), alpha)
end

-- One cell's 14 textures: the lit ones of `ch` (nil for none) take the lit colour, the others the ghost colour. `glow` is the
-- alpha of the soft copy under each lit segment (0 for none); an unlit segment never glows.
local function PaintCell(cell, ch, lr, lg, lb, la, gr, gg, gb, ga, glow)
    if cell.ch == ch and cell.lr == lr and cell.lg == lg and cell.lb == lb and cell.la == la
        and cell.gr == gr and cell.gg == gg and cell.gb == gb and cell.ga == ga and cell.glow == glow then
        return
    end
    cell.ch, cell.lr, cell.lg, cell.lb, cell.la, cell.gr, cell.gg, cell.gb, cell.ga = ch, lr, lg, lb, la, gr, gg, gb, ga
    cell.glow = glow
    local lit = ch and GLYPH[ch]
    local seg, gl = cell.seg, cell.gl
    for n = 1, #SEGMENT_ORDER do
        if lit and lit[n] then
            seg[n]:SetVertexColor(lr, lg, lb, la)
            gl[n]:SetVertexColor(lr, lg, lb, glow * la)
        else
            seg[n]:SetVertexColor(gr, gg, gb, ga)
            gl[n]:SetVertexColor(lr, lg, lb, 0)
        end
    end
end

-- Shows or hides a region only when it is not already so (a repaint touches the same pieces every frame).
local function ShowIf(region, want)
    if region:IsShown() ~= want then region:SetShown(want) end
end

local function ShowCell(cell, want)
    ShowIf(cell.frame, want)
end

-------------------------------------------------------------------------------
-- Painting (texture and font writes only)
-------------------------------------------------------------------------------

local BG = { 13 / 255, 6 / 255, 32 / 255 }                 -- #0d0620
local REC = { 6 / 255, 2 / 255, 16 / 255 }                 -- #060210 the gauge well
local STALE = { 0xb9 / 255, 0xae / 255, 0xe0 / 255 }       -- #b9aee0 the kept rate
local WHITE = { 1, 1, 1 }

-- The font size for `text`: `px`, or smaller so the string stays inside `room` design px at the current scale; whole and half
-- pixels only (rounded down), never below FT.MIN_PX.
local function FitPx(text, px, room)
    local n = type(text) == "string" and #text or 0
    if n == 0 then return px end
    local fit = math.floor(room * Scale() / (n * FT.ADVANCE) * 2) / 2
    return math.max(math.min(fit, px), FT.MIN_PX)
end

local function SetText(fs, px, text)
    if fs.fsPx ~= px then
        fs.fsPx = px
        FS.Theme.ApplyMono(fs, px, FS.Theme.COLOR_TEXT_WHITE)
    end
    if fs.fsShown ~= text then
        fs.fsShown = text
        fs:SetText(text)
    end
end

-- The idle glow: two looping Alpha AnimationGroups, one on the rim's ring and one on its glow, so the client moves them and the
-- addon spends nothing per frame. SetFromAlpha / SetToAlpha take a normalized alpha in the space of the region's own alpha
-- (SetAlpha / GetAlpha), not a multiplier of it: Blizzard_NamePlateUnitFrame.lua:455-471 and Blizzard_ClassPowerBar
-- (Mainline/ClassPowerBar.lua:104-126) fade "from the current alpha value" with SetFromAlpha(region:GetAlpha()), and
-- Blizzard_NamePlates.xml:374-378 states them as plain 0 and 1 (SimpleAnimAlphaAPIDocumentation.lua:20-58 types them
-- normalizedAlpha). The region alpha is never set here (it stays 1), and the vertex colour alpha multiplies it as usual, so the
-- paint leaves each region at its brightest vertex alpha and the animation swings the region alpha between `lo` and 1: the
-- mockup's ring 0.3 to 0.6 (vertex 0.6, lo 0.5), glow 0 to 0.45 (vertex 0.45, lo 0) and gauge 0.24 to 0.38 over BREATH_TIME.
-- The two steps meet end to end (lo to 1, 1 to lo), so the REPEAT loop has no jump; IN_OUT smoothing stands for its cosine.
local function BreathGroup(region, lo)
    if not region.CreateAnimationGroup then return nil end
    local group = region:CreateAnimationGroup()
    group:SetLooping("REPEAT")
    local half = FT.BREATH_TIME / 2
    local up = group:CreateAnimation("Alpha")
    up:SetFromAlpha(lo)
    up:SetToAlpha(1)
    up:SetDuration(half)
    up:SetOrder(1)
    if up.SetSmoothing then up:SetSmoothing("IN_OUT") end
    local down = group:CreateAnimation("Alpha")
    down:SetFromAlpha(1)
    down:SetToAlpha(lo)
    down:SetDuration(half)
    down:SetOrder(2)
    if down.SetSmoothing then down:SetSmoothing("IN_OUT") end
    return group
end

-- Built once the rim and the gauge both exist. `groups` are the rim's two; `gauge` is one per gauge segment, which breathes
-- from 0.24 to 0.38 (the segments are textures of their own).
local function BuildBreath()
    local hero, gauge = FT.hero, FT.gauge
    local skin = hero and hero.fsSkin
    if FT.breath then return end
    if not (skin and skin.border and skin.border.ring and skin.glow and gauge) then
        WarnOnce("fivesecond_breath", "mana regen module idle glow unavailable (the rim or the gauge is missing)")
        return
    end
    local C = FT.CHROME
    local B = { ring = skin.border.ring, glow = skin.glow, groups = {}, gauge = {}, on = false, gaugeOn = false }
    if not (B.ring.CreateAnimationGroup and B.glow.CreateAnimationGroup) then
        WarnOnce("fivesecond_breath", "mana regen module idle glow unavailable (no animation groups)")
        return
    end
    B.groups[1] = BreathGroup(B.ring, C.breathRing / (C.breathRing + C.breathRingSwing))
    B.groups[2] = BreathGroup(B.glow, 0)
    for i = 1, FT.GAUGE_N do
        B.gauge[i] = BreathGroup(gauge.seg[i], FT.GAUGE_BREATH_LO / FT.GAUGE_BREATH_HI)
    end
    FT.breath = B
end

local function Switch(groups, want)
    for _, group in ipairs(groups) do
        if want then group:Play() else group:Stop() end
    end
end

-- Plays or stops the idle glow: the rim (stopped under the mouse, whose ring is steady) and the gauge segments apart; a stop
-- puts the regions back at full alpha.
local function SetBreath(rim, gauge)
    local B = FT.breath
    if not B then return end
    if B.on ~= rim then
        B.on = rim
        Switch(B.groups, rim)
        if not rim then
            B.ring:SetAlpha(1)
            B.glow:SetAlpha(1)
        end
    end
    if B.gaugeOn ~= gauge then
        B.gaugeOn = gauge
        Switch(B.gauge, gauge)
        if not gauge then
            for i = 1, #B.gauge do FT.gauge.seg[i]:SetAlpha(1) end
        end
    end
end

-- The rim: the border ring and its glow, lit cyan under the mouse.
local function PaintRim(tile, hover, color, colorA, glowColor, glowA)
    local skin = tile.fsSkin
    local cyan = FS.Theme.COLOR_POWER
    if hover then
        color, colorA, glowColor, glowA = cyan, 1, cyan, math.max(glowA, FT.CHROME.hoverGlow)
    end
    if skin and skin.border and skin.border.ring then
        skin.border.ring:SetVertexColor(color[1], color[2], color[3], colorA)
    end
    if skin and skin.glow then
        skin.glow:SetVertexColor(glowColor[1], glowColor[2], glowColor[3], glowA)
    end
end

local function Q20(v)
    return math.floor(v * 20 + 0.5)
end

-- A quick effect repaints when its value moves by a hundredth (an alpha step nobody can see).
local function Q100(v)
    return math.floor(v * 100 + 0.5)
end

-- The readout while the window runs (susp), or the held digits under the sweep: which cells show and what they spell.
local DIGITS = { [0] = "0", "1", "2", "3", "4", "5", "6", "7", "8", "9" }

local function PaintCount(led, col, lc, litA, ghostA, zp, held, bx, glow)
    local cr, cg, cb = col[1], col[2], col[3]
    local lr, lg, lb = lc[1], lc[2], lc[3]
    local flashK = 0.85 * zp
    lr, lg, lb = Lerp(lr, 1, flashK), Lerp(lg, 1, flashK), Lerp(lb, 1, flashK)
    local ch1, ch2 = "0", "0"
    if not held then
        local tenths = math.floor(view.t * 10 + 0.5)
        ch1, ch2 = DIGITS[math.floor(tenths / 10) % 10], DIGITS[tenths % 10]
    end
    -- band x of -1 shows everything; else a part shows while the band has not passed its centre
    local k = held and bx or -1e9
    local D = FT.DIGIT_X
    local showTilde, showD1, showDot, showD2 = D.tilde > k, D.d1 > k, D.dot > k, D.d2 > k
    for i = 1, 4 do
        local bar = led.tilde[i]
        ShowIf(bar, showTilde)
        bar:SetVertexColor(lr, lg, lb, 1)
        ShowIf(led.tildeGl[i], showTilde)
        led.tildeGl[i]:SetVertexColor(lr, lg, lb, glow)
    end
    ShowIf(led.dot, showDot)
    led.dot:SetVertexColor(lr, lg, lb, 1)
    ShowIf(led.dotGl, showDot)
    led.dotGl:SetVertexColor(lr, lg, lb, glow)
    ShowCell(led.d1, showD1)
    ShowCell(led.d2, showD2)
    PaintCell(led.d1, ch1, lr, lg, lb, 1, cr, cg, cb, ghostA, glow)
    PaintCell(led.d2, ch2, lr, lg, lb, litA, cr, cg, cb, ghostA, glow)
    return lr, lg, lb
end

local WORD = { "R", "E", "G", "E", "N" }
local wordColor = { 0, 0, 0 }

local function PaintCells(zone)
    local T = FS.Theme
    local amber, cyan, muted, violet = T.COLOR_AMBER, T.COLOR_POWER, T.COLOR_MUTED, T.COLOR_BORDER
    local v = view
    local susp = v.phase == "susp"
    local f = susp and 1 or v.fade
    local hover = zone.fsHover and true or false
    local tenths = susp and math.floor(v.t * 10 + 0.5) or -1
    local fq, pq = Q20(f), Q20(v.pulse)
    local flashQ, zpQ, warmQ, dropQ = Q100(fx.flash), Q100(fx.zp), Q100(fx.warm), Q100(fx.dropA)
    -- the sweep band moves a design px at a time; the glow flares in hundredths; the idle glow is on or off
    local ppQ, breathQ, flareQ = math.floor(fx.pp * FT.HERO.w + 0.5), fx.breathing and 1 or 0, Q100(fx.flare)
    local K = FT.sigCells
    if K.on and K.phase == v.phase and K.tenths == tenths and K.fq == fq and K.pq == pq and K.hover == hover
        and K.flash == flashQ and K.zp == zpQ and K.warm == warmQ and K.drop == dropQ and K.dropSeg == fx.dropSeg
        and K.pp == ppQ and K.breath == breathQ and K.flare == flareQ and K.dip == fx.dip and K.sweeping == (fx.pp < 1) then
        return
    end
    K.on, K.phase, K.tenths, K.fq, K.pq, K.hover = true, v.phase, tenths, fq, pq, hover
    K.flash, K.zp, K.warm, K.drop, K.dropSeg, K.pp, K.breath, K.flare, K.dip, K.sweeping =
        flashQ, zpQ, warmQ, dropQ, fx.dropSeg, ppQ, breathQ, flareQ, fx.dip, fx.pp < 1

    local led = FT.led
    local hero = FT.hero
    local C = FT.CHROME
    local b = fx.breathing
    local zp = fx.zp
    local sweeping = fx.pp < 1
    local bx = FT.HERO.x + ppQ                          -- the sweep band, design px from the host's left

    -- the hero tile: plate, rim, glow
    if susp then
        local r, g, bl = Mix(BG, amber, 0.09)
        hero.fsPlate:SetVertexColor(r, g, bl, 0.9)
        PaintRim(hero, hover, amber, C.suspRing, amber, C.suspGlow)
    else
        local r, g, bl = Mix(BG, cyan, 0.1 * f)
        hero.fsPlate:SetVertexColor(r, g, bl, Lerp(0.72, 0.9, f))
        -- the idle glow paints its brightest alpha; the animation dims it by its region alpha down to breathRing / the dark
        local ringA = Lerp(b and (C.breathRing + C.breathRingSwing) or C.idleRing, C.regenRing, f)
        local glowA = C.regenGlow * f + C.flareGlow * fx.flare + (1 - f) * (b and C.breathGlow or 0)
        scratch[1], scratch[2], scratch[3] = Mix(violet, cyan, f)
        PaintRim(hero, hover, scratch, ringA, scratch, glowA)
    end
    SetBreath(b and not hover and true or false, b and true or false)

    -- the LED readout
    local ghostA, litA
    if susp then
        local col = amber
        local lc = col
        if fx.warm > 0 then
            local w = fx.warm
            local hr, hg, hb = Mix(amber, WHITE, 0.8)
            if w < 0.5 then
                scratch[1], scratch[2], scratch[3] = Lerp(amber[1], hr, w * 2), Lerp(amber[2], hg, w * 2), Lerp(amber[3], hb, w * 2)
            else
                scratch[1], scratch[2], scratch[3] = Lerp(hr, cyan[1], (w - 0.5) * 2), Lerp(hg, cyan[2], (w - 0.5) * 2),
                    Lerp(hb, cyan[3], (w - 0.5) * 2)
            end
            lc = scratch
        end
        ghostA = FT.GHOST_COUNT + FT.GHOST_LIFT * zp
        litA = fx.dip and (1 - FT.DIP_DEPTH) or 1
        for i = 1, 5 do ShowCell(led.word[i], false) end
        -- the soft copy under the lit segments, brighter at the whole second pulse
        PaintCount(led, col, lc, litA, ghostA, zp, false, 0, math.min(1, FT.GLOW_STEADY + FT.GLOW_PULSE * zp))
    else
        local col = wordColor
        col[1], col[2], col[3] = Mix(muted, cyan, f)
        litA = Lerp(FT.WORD_IDLE, 1, f)
        ghostA = Lerp(FT.GHOST_IDLE, FT.GHOST_RES, f)
        -- the held countdown digits, cyan, until the band has passed each one
        local held = sweeping and on.digits
        if held then
            PaintCount(led, cyan, cyan, 1, ghostA, 0, true, bx, FT.GLOW_STEADY)
        else
            ShowCell(led.d1, false)
            ShowCell(led.d2, false)
            for i = 1, 4 do
                ShowIf(led.tilde[i], false)
                ShowIf(led.tildeGl[i], false)
            end
            ShowIf(led.dot, false)
            ShowIf(led.dotGl, false)
        end
        local W = FT.WORD_X
        for i = 1, 5 do
            local cell = led.word[i]
            ShowCell(cell, true)
            local cx = W + (i - 1) * 12 + 5
            local masked = held and cx > bx
            local hot = 0
            if held and not masked then
                local dx = math.abs(cx - bx)
                if dx < 9 then hot = 0.8 * (1 - dx / 9) end
            end
            local lr, lg, lb = Lerp(col[1], 1, hot), Lerp(col[2], 1, hot), Lerp(col[3], 1, hot)
            PaintCell(cell, (not masked) and WORD[i] or nil, lr, lg, lb, litA, col[1], col[2], col[3], ghostA, FT.GLOW_STEADY * f)
        end
    end

    -- the gauge: each segment has a soft halo of its own colour and alpha under it (none at rest, fading in with the look)
    local n = FT.GAUGE_N
    local lit = susp and Clamp01(v.t / FT.WINDOW) * n or 0
    local halo = f
    local gauge = FT.gauge
    for i = 1, n do
        local seg, gl = gauge.seg[i], gauge.gl[i]
        local r, g, bl, a
        if susp then
            local ai = Clamp01(lit - (i - 1))
            if i == fx.dropSeg then
                r, g, bl, a = amber[1], amber[2], amber[3], math.max(FT.GAUGE_OFF, fx.dropA)
            elseif ai > 0 then
                r, g, bl, a = amber[1], amber[2], amber[3], 0.45 + 0.55 * ai
            else
                r, g, bl, a = violet[1], violet[2], violet[3], FT.GAUGE_OFF
            end
        else
            local x = FT.GAUGE_X + (i - 1) * FT.GAUGE_PITCH + FT.GAUGE_SEG_W / 2
            if sweeping and math.abs(x - bx) < 9 then
                r, g, bl, a = 1, 1, 1, 0.95
            else
                r, g, bl, a = cyan[1], cyan[2], cyan[3], Lerp(b and FT.GAUGE_BREATH_HI or FT.GAUGE_IDLE, 0.85, f)
            end
        end
        seg:SetVertexColor(r, g, bl, a)
        gl:SetVertexColor(r, g, bl, a * halo)
    end

    FT.cells:SetAlpha(Lerp(FT.IDLE_ALPHA, 1, f))
    FT.fxFlash:SetVertexColor(1, 1, 1, FT.FLASH_ALPHA * fx.flash)
end

local HOLLOW_MIX = 0.25

local function PaintRate(zone)
    local T = FS.Theme
    local cyan, muted, violet = T.COLOR_POWER, T.COLOR_MUTED, T.COLOR_BORDER
    local v = view
    local hover = zone.fsHover and true or false
    local idle = v.phase == "idle"
    local act = v.phase == "susp" and 1 or v.fade
    local hasRate = v.rateText ~= nil
    local kept = hasRate and v.cached
    local aq, tq, gq = Q20(act), Q100(fx.tick), Q100(fx.glitchA)
    local K = FT.sigRate
    if K.on and K.rate == v.rateText and K.cached == v.cached and K.ret == v.ret and K.aq == aq and K.hover == hover
        and K.has == hasRate and K.tq == tq and K.gq == gq and K.gdx == fx.glitchDx and K.idle == idle then
        return
    end
    K.on, K.rate, K.cached, K.ret, K.aq, K.hover, K.has, K.tq, K.gq, K.gdx, K.idle =
        true, v.rateText, v.cached, v.ret, aq, hover, hasRate, tq, gq, fx.glitchDx, idle

    local gA, gDx = fx.glitchA, fx.glitchDx
    local text = hasRate and (v.rateText .. "/s") or "--"
    local base = (hasRate and #v.rateText >= 4) and FT.RATE_LONG_PX or FT.RATE_PX
    local size = FitPx(text, base, FT.RATE_ROOM)
    local fs = FT.rateText
    SetText(fs, size, text)
    local color = kept and STALE or ((not hasRate or idle) and muted or WHITE)
    fs:SetTextColor(color[1], color[2], color[3], gA)
    -- seat: left aligned at the bar's left, centre line a third of the size above the baseline, whole pixels
    local s, px = Scale(), FT.px
    local cy = math.floor((FT.RATE_BASE - size * 0.36) + 0.5)
    if fs.fsX ~= gDx or fs.fsY ~= cy then
        fs.fsX, fs.fsY = gDx, cy
        fs:ClearAllPoints()
        fs:SetPoint("LEFT", FT.host, "TOPLEFT", FT.Snap(FT.RATE_X) + gDx * px, -FT.Snap(cy))
    end

    -- the bar under it: solid, dashed while the numbers are the kept ones, plain muted when there is no reading
    local widthUI = #text * size * FT.ADVANCE
    local wd = math.floor(widthUI / s + 0.5)         -- design px, whole (the page rounds it the same way)
    local bar = FT.rateBar
    local pk = (not kept and hasRate and fx.tick > 0.5) and 1 or 0
    if kept then
        ShowIf(bar.solid, false)
        ShowIf(bar.hi, false)
        local count = math.min(#bar.dash, math.ceil(wd / FT.DASH_PITCH))
        for i, dash in ipairs(bar.dash) do
            if i <= count then
                local x = (i - 1) * FT.DASH_PITCH
                FT.Place(dash, FT.RATE_X + x, FT.RATE_BAR_Y, math.min(FT.DASH_ON, wd - x), 2)
                dash:SetVertexColor(STALE[1], STALE[2], STALE[3], 0.9)
                ShowIf(dash, true)
            else
                ShowIf(dash, false)
            end
        end
    else
        for _, dash in ipairs(bar.dash) do ShowIf(dash, false) end
        FT.Place(bar.solid, FT.RATE_X, FT.RATE_BAR_Y - pk, wd, 2 + 2 * pk)
        ShowIf(bar.solid, true)
        if not hasRate then
            bar.solid:SetVertexColor(muted[1], muted[2], muted[3], 0.7)
        else
            local r, g, b = Mix(muted, cyan, act)
            bar.solid:SetVertexColor(r, g, b, Lerp(0.45, 0.95, act))
        end
        if pk > 0 then
            FT.Place(bar.hi, FT.RATE_X, FT.RATE_BAR_Y - pk, wd, 2 + 2 * pk)
            bar.hi:SetVertexColor(1, 1, 1, 0.5)
            ShowIf(bar.hi, true)
        else
            ShowIf(bar.hi, false)
        end
    end

    -- the retention chip
    local chip = FT.chip
    local tk = fx.tick
    local ret = v.ret
    local codeColor
    if ret then
        chip.fill:SetVertexColor(Lerp(BG[1], cyan[1], 0.3), Lerp(BG[2], cyan[2], 0.3), Lerp(BG[3], cyan[3], 0.3), 1)
        chip.ring:SetVertexColor(cyan[1], cyan[2], cyan[3], 1)
        chip.glow:SetVertexColor(cyan[1], cyan[2], cyan[3], FT.CHROME.chipGlow + FT.CHROME.chipTick * tk)
        codeColor = WHITE
        SetText(chip.code, FitPx(ret .. "%", FT.CODE_PX, FT.CHIP_ROOM), ret .. "%")
    else
        local r, g, b = Lerp(muted[1], 1, HOLLOW_MIX), Lerp(muted[2], 1, HOLLOW_MIX), Lerp(muted[3], 1, HOLLOW_MIX)
        chip.fill:SetVertexColor(BG[1], BG[2], BG[3], 0.75)
        if tk > 0 then
            chip.ring:SetVertexColor(cyan[1], cyan[2], cyan[3], 0.5 + 0.5 * tk)
        else
            chip.ring:SetVertexColor(r, g, b, idle and 0.5 or 0.9)
        end
        chip.glow:SetVertexColor(r, g, b, 0)
        scratch[1], scratch[2], scratch[3] = r, g, b
        codeColor = scratch
        local code = hasRate and "0%" or "--"
        SetText(chip.code, FitPx(code, FT.CODE_PX, FT.CHIP_ROOM), code)
    end
    chip.code:SetTextColor(codeColor[1], codeColor[2], codeColor[3], (idle and FT.CHIP_IDLE_TEXT or 1) * gA)
    if chip.code.fsX ~= gDx then
        chip.code.fsX = gDx
        chip.code:ClearAllPoints()
        chip.code:SetPoint("CENTER", chip.fill, "CENTER", gDx * px, 0)
    end
    if hover then
        chip.ring:SetVertexColor(cyan[1], cyan[2], cyan[3], 1)
    end
    FT.rate:SetAlpha(Lerp(FT.IDLE_ALPHA, 1, act))
end

function Tab.Paint()
    if not FT.built or not FT.led then return end
    PaintCells(FT.cells)
    PaintRate(FT.rate)
    for _, zone in ipairs(FT.tiles) do
        if TipIsOurs(zone) then ShowTooltip(zone, true) end
    end
end

-------------------------------------------------------------------------------
-- The face
-------------------------------------------------------------------------------

local function NewText(parent, px)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(fs, px, FS.Theme.COLOR_TEXT_WHITE)
    fs.fsPx = px
    return fs
end

-- Pixel crisp: a texture snapped to the pixel grid with no texel bias, where the client has the calls (GunsightFrame.lua).
local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
    return tex
end

local function FlatTexture(parent, layer, sub)
    local tex = Crisp(parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0))
    tex:SetColorTexture(1, 1, 1, 1)
    return tex
end

-- UI units per physical pixel (PixelUtil's factor over the host's effective scale), or nil when the client will not say.
local function PixelUnit()
    local factor
    local pixelUtil, physical = _G.PixelUtil, _G.GetPhysicalScreenSize
    if type(pixelUtil) == "table" and type(pixelUtil.GetPixelToUIUnitFactor) == "function" then
        local ok, v = pcall(pixelUtil.GetPixelToUIUnitFactor)
        if ok then factor = v end
    elseif type(physical) == "function" then
        local ok, _, h = pcall(physical)
        if ok and type(h) == "number" and not IsSecret(h) and h > 0 then factor = 768 / h end
    end
    if type(factor) ~= "number" or IsSecret(factor) or factor ~= factor or factor <= 0 or factor == math.huge then return nil end
    local scale = 1
    local host = FT.host
    if host and host.GetEffectiveScale then
        local ok, v = pcall(host.GetEffectiveScale, host)
        if ok and type(v) == "number" and not IsSecret(v) and v > 0 and v < math.huge then scale = v end
    end
    return factor / scale
end

-- The grid for this scale: px UI units a physical pixel; n physical pixels a texel of the LED art (a whole number, so the
-- art is never scaled fractionally), the nearest to a design px that still leaves the ring clear of the hero tile; u = n * px
-- the UI units of one texel. The Layout scale is the UI height over 1440, so a design px is physical height / 1440 pixels
-- whatever the UI scale slider says: one on a 1440 screen (px = the scale, n = 1), 1.5 on 2160 (n = 1: two would fill the tile).
local function SeatGrid()
    local s = Scale()
    local px = PixelUnit() or s
    FT.s, FT.px = s, px
    local ratio = s / px
    local fit = math.floor((FT.HERO.h * ratio - 2) / FT.CELL_H)
    FT.n = math.max(1, math.min(math.floor(ratio + 0.5), fit))
    FT.u = FT.n * px
end

-- `d` design px as a whole count of physical pixels.
local function PixelsOf(d)
    return math.floor(d * FT.s / FT.px + 0.5)
end

function FT.Snap(d)
    return PixelsOf(d) * FT.px
end

-- Seats `region` over the design rect (x, y from the host's top left, w, h), edge by edge on whole pixels so neighbours
-- keep their joint.
function FT.Place(region, x, y, w, h)
    local px = FT.px
    local l, t = PixelsOf(x), PixelsOf(y)
    local r, b = PixelsOf(x + w), PixelsOf(y + h)
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", FT.host, "TOPLEFT", l * px, -t * px)
    region:SetSize((r - l) * px, (b - t) * px)
end
local Place = FT.Place

-- Seats `region` at a whole pixel count (x, y: pixels from the host's top left) with a size in pixels.
local function PlacePx(region, x, y, w, h)
    local px = FT.px
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", FT.host, "TOPLEFT", x * px, -y * px)
    region:SetSize(w * px, h * px)
end

local function NewCell(parent, level)
    local frame = CreateFrame("Frame", nil, parent)
    frame:EnableMouse(false)
    frame:SetFrameLevel(level)
    local cell = { frame = frame, seg = {}, gl = {} }
    for n = 1, #SEGMENT_ORDER do
        local l, t = ((n - 1) % 4) * 0.25, math.floor((n - 1) / 4) * 0.25
        -- the soft copy first (ADD, under the segment), cut from the blurred atlas: the cell plus two texels on every side
        local gl = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 0))
        gl:SetTexture(MEDIA .. "led_segment_glow.tga")
        gl:SetBlendMode("ADD")
        gl:SetTexCoord(l, l + FT.SEG_GLOW_W / FT.ATLAS, t, t + FT.SEG_GLOW_H / FT.ATLAS)
        gl:SetVertexColor(1, 1, 1, 0)
        cell.gl[n] = gl
        local tex = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 1))
        tex:SetTexture(MEDIA .. "led_segments.tga")
        tex:SetTexCoord(l, l + FT.CELL_W / FT.ATLAS, t, t + FT.CELL_H / FT.ATLAS)
        cell.seg[n] = tex
    end
    return cell
end

-- Creates every region of the face once; a throw partway is finished by the next Build (each group is guarded).
local function BuildFace()
    local T = FS.Theme
    local host = FT.host
    local cells, rateZone = FT.cells, FT.rate
    if not FT.hero then
        local hero = CreateFrame("Frame", nil, cells)
        hero:EnableMouse(false)
        hero.fsPlate = T.AddCut2Texture(hero, T.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
        T.SkinCutButton(hero, { borderColor = T.COLOR_BORDER, glowAlpha = FT.CHROME.idleGlow })
        FT.hero = hero
    end
    if not FT.gauge then
        local body = CreateFrame("Frame", nil, cells)
        body:EnableMouse(false)
        body:SetFrameLevel(cells:GetFrameLevel() + 3)
        local g = { frame = body, seg = {}, line = {} }
        g.gl = {}
        g.plate = FlatTexture(body, "BACKGROUND", 2)
        g.plate:SetVertexColor(REC[1], REC[2], REC[3], 0.9)
        for k = 1, 4 do
            g.line[k] = FlatTexture(body, "BORDER", 0)
            local v = T.COLOR_BORDER
            g.line[k]:SetVertexColor(v[1], v[2], v[3], 0.4)
        end
        for i = 1, FT.GAUGE_N do
            local gl = Crisp(body:CreateTexture(nil, "ARTWORK", nil, -1))
            gl:SetTexture(MEDIA .. "led_glow.tga")
            gl:SetBlendMode("ADD")
            gl:SetVertexColor(1, 1, 1, 0)
            g.gl[i] = gl
            g.seg[i] = FlatTexture(body, "ARTWORK", 0)
        end
        FT.gauge = g
        FT.body = body
    end
    BuildBreath()
    if not FT.led then
        local body = FT.body
        local led = { word = {}, tilde = {} }
        -- the glow of the tilde bars and the dot: the blurred 2 x 2 block, one texture each, under the flat piece
        local function BlockGlow()
            local gl = Crisp(body:CreateTexture(nil, "ARTWORK", nil, 0))
            gl:SetTexture(MEDIA .. "led_segment_glow.tga")
            gl:SetBlendMode("ADD")
            local l, t = (FT.BLOCK_SLOT % 4) * 0.25, math.floor(FT.BLOCK_SLOT / 4) * 0.25
            gl:SetTexCoord(l, l + FT.BLOCK_GLOW / FT.ATLAS, t, t + FT.BLOCK_GLOW / FT.ATLAS)
            gl:SetVertexColor(1, 1, 1, 0)
            return gl
        end
        led.tildeGl = {}
        for i = 1, 4 do led.tildeGl[i] = BlockGlow() end
        led.dotGl = BlockGlow()
        local level = body:GetFrameLevel() + 1
        led.d1, led.d2 = NewCell(body, level), NewCell(body, level)
        for i = 1, 5 do led.word[i] = NewCell(body, level) end
        led.cells = { led.d1, led.d2, led.word[1], led.word[2], led.word[3], led.word[4], led.word[5] }
        for i = 1, 4 do led.tilde[i] = FlatTexture(body, "ARTWORK", 1) end
        led.dot = FlatTexture(body, "ARTWORK", 1)
        FT.led = led
    end
    if not FT.fxFrame then
        local frame = CreateFrame("Frame", nil, host)
        frame:EnableMouse(false)
        frame:SetClipsChildren(true)
        frame:SetFrameLevel(host:GetFrameLevel() + 8)
        FT.fxFrame = frame
        FT.fxFlash = FlatTexture(frame, "OVERLAY", 7)
        FT.fxFlash:SetAllPoints(frame)
        FT.fxFlash:SetVertexColor(1, 1, 1, 0)
    end
    if not FT.chip then
        local c = FT.CHIP_C
        local ringPath, glowPath = MEDIA .. "slice_cut2_outline_c3.tga", MEDIA .. "slice_cut2_glow_c3.tga"
        if T.Cut2ButtonSet then
            local ok, ring, glow, used = pcall(T.Cut2ButtonSet, FT.CHIP_C)
            if ok and type(ring) == "string" and type(glow) == "string" then
                ringPath, glowPath, c = ring, glow, used or c
            end
        end
        local chip = {}
        chip.glow = rateZone:CreateTexture(nil, "BACKGROUND", nil, 0)
        chip.glow:SetTexture(glowPath)
        T.ApplyNineSlice(chip.glow, (T.SLICE_CUT2_GLOW_PAD or 4) + c)
        chip.glow:SetBlendMode("ADD")
        chip.fill = rateZone:CreateTexture(nil, "BACKGROUND", nil, 1)
        chip.fill:SetTexture(MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
        T.ApplyNineSlice(chip.fill, c)
        chip.ring = rateZone:CreateTexture(nil, "ARTWORK", nil, 0)
        chip.ring:SetTexture(ringPath)
        T.ApplyNineSlice(chip.ring, c)
        chip.code = NewText(rateZone, FT.CODE_PX)
        chip.code:SetJustifyH("CENTER")
        FT.chip = chip
    end
    if not FT.rateBar then
        local bar = { dash = {} }
        bar.solid = FlatTexture(rateZone, "OVERLAY", 1)
        bar.hi = FlatTexture(rateZone, "OVERLAY", 2)
        bar.hi:Hide()
        for i = 1, FT.DASHES do
            bar.dash[i] = FlatTexture(rateZone, "OVERLAY", 1)
            bar.dash[i]:Hide()
        end
        FT.rateBar = bar
    end
    if not FT.rateText then
        FT.rateText = NewText(rateZone, FT.RATE_PX)
        FT.rateText:SetJustifyH("LEFT")
    end
end

-- Runs from Build and again on every re-seat: sizes and points only, on whole pixels.
local function LayoutFace()
    local s = Scale()
    SeatGrid()
    local px, n, u = FT.px, FT.n, FT.u
    local H = FT.HERO
    FT.host:SetSize(FT.HOST_W * s, FT.HOST_H * s)

    Place(FT.cells, H.x, H.y, H.w, FT.GAUGE_Y + FT.GAUGE_H - H.y)
    Place(FT.rate, H.x, FT.RATE_ZONE_Y, H.w, FT.CHIP.y + FT.CHIP.h - FT.RATE_ZONE_Y)
    Place(FT.fxFrame, H.x, H.y, H.w, FT.FACE_H)
    Place(FT.hero, H.x, H.y, H.w, H.h)
    FT.cells.fsSig = nil
    FT.sigCells.on = nil
    FT.sigRate.on = nil

    -- the gauge: the well, its outline, ten segments
    local G = FT.gauge
    Place(G.plate, FT.GAUGE_WELL.x, FT.GAUGE_Y, FT.GAUGE_WELL.w, FT.GAUGE_H)
    local wx, wy, ww, wh = FT.GAUGE_WELL.x, FT.GAUGE_Y, FT.GAUGE_WELL.w, FT.GAUGE_H
    Place(G.line[1], wx, wy, ww, 1)
    Place(G.line[2], wx, wy + wh - 1, ww, 1)
    Place(G.line[3], wx, wy + 1, 1, wh - 2)
    Place(G.line[4], wx + ww - 1, wy + 1, 1, wh - 2)
    for i = 1, FT.GAUGE_N do
        Place(G.seg[i], FT.GAUGE_X + (i - 1) * FT.GAUGE_PITCH, FT.GAUGE_SEG_Y, FT.GAUGE_SEG_W, FT.GAUGE_SEG_H)
    end
    local gp = FT.GAUGE_GLOW_PAD
    for i = 1, FT.GAUGE_N do
        Place(G.gl[i], FT.GAUGE_X + (i - 1) * FT.GAUGE_PITCH - gp, FT.GAUGE_SEG_Y - gp, FT.GAUGE_SEG_W + 2 * gp, FT.GAUGE_SEG_H + 2 * gp)
    end

    -- the readout: the counting group (tilde, two digits, a dot) and the word are both centred on the hero tile; every
    -- number below is a whole count of physical pixels, one texel being n of them
    local led = FT.led
    local centre = PixelsOf(FT.LED_CX)
    local rowPx = PixelsOf(H.y + H.h / 2) - math.floor(FT.CELL_H * n / 2)
    local wordPx = centre - math.floor(FT.WORD_W * n / 2)
    local countPx = centre - math.floor(FT.COUNT_W * n / 2)
    local gm, bg = FT.SEG_GLOW_PAD * n, FT.BLOCK_GLOW * n
    for i, bar in ipairs(led.tilde) do
        local bx, by = countPx + TILDE[i][1] * n, rowPx + TILDE[i][2] * n
        PlacePx(bar, bx, by, 2 * n, 2 * n)
        PlacePx(led.tildeGl[i], bx - gm, by - gm, bg, bg)
    end
    PlacePx(led.dot, countPx + 21 * n, rowPx + 10 * n, 2 * n, 2 * n)
    PlacePx(led.dotGl, countPx + 21 * n - gm, rowPx + 10 * n - gm, bg, bg)
    PlacePx(led.d1.frame, countPx + 10 * n, rowPx, FT.CELL_W * n, FT.CELL_H * n)
    PlacePx(led.d2.frame, countPx + 24 * n, rowPx, FT.CELL_W * n, FT.CELL_H * n)
    for i = 1, 5 do PlacePx(led.word[i].frame, wordPx + (i - 1) * 12 * n, rowPx, FT.CELL_W * n, FT.CELL_H * n) end
    for _, cell in ipairs(led.cells) do
        for _, tex in ipairs(cell.seg) do
            tex:ClearAllPoints()
            tex:SetAllPoints(cell.frame)
        end
        -- the glow rect: the cell plus two texels on every side, so 14 x 16 texels from two texels up and left
        for _, gl in ipairs(cell.gl) do
            gl:ClearAllPoints()
            gl:SetPoint("TOPLEFT", cell.frame, "TOPLEFT", -gm * px, gm * px)
            gl:SetSize(FT.SEG_GLOW_W * n * px, FT.SEG_GLOW_H * n * px)
        end
        cell.ch = nil
    end

    -- the rate line and the chip
    FT.rateText.fsX = nil
    local C = FT.CHIP
    Place(FT.chip.fill, C.x, C.y, C.w, C.h)
    Place(FT.chip.ring, C.x, C.y, C.w, C.h)
    local cgp = FT.GLOW_PAD
    Place(FT.chip.glow, C.x - cgp, C.y - cgp, C.w + 2 * cgp, C.h + 2 * cgp)
    FT.chip.code.fsX = nil
    FT.rateBar.solid:ClearAllPoints()
    FT.rateBar.solid:SetSize(1, 1)
end

-- The hover, tooltip and hide hooks of a zone.
local function HookZone(zone)
    if zone.fsHooked then return end
    zone.fsHooked = true
    zone:EnableMouse(true)
    zone:SetScript("OnEnter", function(self)
        self.fsHover = true
        FT.sigCells.on, FT.sigRate.on = nil, nil
        Tab.Paint()
        ShowTooltip(self)
    end)
    zone:SetScript("OnLeave", function(self)
        self.fsHover = nil
        FT.sigCells.on, FT.sigRate.on = nil, nil
        Tab.Paint()
        GameTooltip:Hide()
    end)
    -- a hidden host (a Druid form change, the master toggle) sends no OnLeave: forget the hover, and hide the tooltip
    -- only while it is this zone's
    zone:SetScript("OnHide", function(self)
        local ours = TipIsOurs(self)
        self.fsHover = nil
        FT.sigCells.on, FT.sigRate.on = nil, nil
        if ours then GameTooltip:Hide() end
    end)
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

-- Where the host stands: the SetPoint arguments from the shoulder ClassShoulder.lua stands for it, or nil for no seat (no
-- Console, a failed shoulder: the host then hides).
function Tab.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint, FT.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    return nil
end

-- Shows or hides the host. The ticker frame is its child (a hidden frame gets no OnUpdate) and the idle glow stops with it.
local function ShowHost(want)
    local host = FT.host
    host:SetShown(want)
    if not want then
        SetBreath(false, false)
        FT.sigCells.on = nil
        FT.fast, FT.ambient = false, false
    end
end

local function ApplyVisibility()
    local host = FT.host
    if not host then return end
    local want = FT.seated and Tab.Shown() or false
    ShowHost(want)
    if want then Tab.Update() Tab.Paint() end
end
Tab.ApplyVisibility = ApplyVisibility

local function SeatHost()
    local host = FT.host
    local point, rel, relPoint, x, y = Tab.HostPoint()
    if not point then
        FT.seated = false
        ShowHost(false)
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    FT.seated = true
    ApplyVisibility()
end

-- The seat steps. The face is plain frames on a plain host, so sizing it is legal in combat and happens at once; the host's
-- anchor onto the Console waits for PLAYER_REGEN_ENABLED like everything on the chassis. Each step is its own pcall so one
-- failure cannot stop the next.
local function Sync()
    if not FT.built then return end
    local ok, err = pcall(LayoutFace)
    if not ok then WarnOnce("fivesecond_sync", "mana regen module update failed (" .. tostring(err) .. ")") end
    if InCombatLockdown() then
        FT.pendingSync = true
        return
    end
    FT.pendingSync = false
    ok, err = pcall(SeatHost)
    if not ok then WarnOnce("fivesecond_sync", "mana regen module update failed (" .. tostring(err) .. ")") end
end
Tab.Sync = Sync

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    if not FT.host then
        FT.host = CreateFrame("Frame", "FSFiveSecondTab", UIParent)
        FT.host:SetFrameStrata("LOW")
        FT.host:Hide()
    end
    if not FT.cells then
        FT.cells = CreateFrame("Frame", "FSFiveSecondCells", FT.host)
        FT.cells.fsKey = "cells"
    end
    if not FT.rate then
        FT.rate = CreateFrame("Frame", "FSFiveSecondRate", FT.host)
        FT.rate.fsKey = "rate"
    end
    FT.tiles = { FT.cells, FT.rate }
    SeatGrid()
    BuildFace()
    for _, zone in ipairs(FT.tiles) do HookZone(zone) end
    FT.built = true
end

local function Refresh()
    Tab.Update()
    if FT.host and FT.host:IsShown() then Tab.Paint() end
end

-- One pass every frame while the count runs or a flash dies, at TICK_AMBIENT while a short slow motion plays, every half second
-- otherwise; the frame is a child of the tab, hidden with it. A plain frame, nothing protected.
local function Tick(self, dt)
    self.fsElapsed = (self.fsElapsed or 0) + dt
    local every = FT.fast and 0 or (FT.ambient and FT.TICK_AMBIENT or FT.TICK_SLOW)
    if self.fsElapsed < every then return end
    self.fsElapsed = 0
    local ok, err = pcall(Refresh)
    if not ok then WarnOnce("fivesecond_tick", "mana regen module repaint failed (" .. tostring(err) .. ")") end
end

local function OnEvent(_, event, unit, _, spellID)
    if event == "UNIT_SPELLCAST_SUCCEEDED" or event == "UNIT_SPELLCAST_CHANNEL_START"
        or event == "UNIT_SPELLCAST_CHANNEL_STOP" then
        if IsSecret(unit) or unit ~= "player" then return end
        if event == "UNIT_SPELLCAST_SUCCEEDED" then
            Tab.OnCast(spellID)
        elseif event == "UNIT_SPELLCAST_CHANNEL_START" then
            Tab.OnChannelStart(spellID)
        else
            Tab.OnChannelStop()
        end
    elseif event == "UNIT_DISPLAYPOWER" or event == "UPDATE_SHAPESHIFT_FORM" then
        if event == "UNIT_DISPLAYPOWER" and (IsSecret(unit) or unit ~= "player") then return end
        RefreshForm()
        ApplyVisibility()
        if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
    elseif event == "PLAYER_DEAD" then
        Tab.Reset()
    elseif event == "PLAYER_ENTERING_WORLD" then
        Tab.Reset()
        rate.nextRead = 0
        RefreshForm()
        ApplyVisibility()
    elseif event == "PLAYER_REGEN_DISABLED" then
        rate.live = false
    elseif event == "PLAYER_REGEN_ENABLED" then
        rate.nextRead = 0
        if FT.pendingSync then Sync() end
        Refresh()
    end
end

local function Apply()
    if not Tab.Applies() then return end
    if not (FS.Theme and FH and FS.Layout) then return end

    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: mana regen module failed to build (" .. tostring(err) .. ")")
        return
    end

    -- Listeners start only now that the face exists (a failed or non-mana build leaves none running).
    local events = CreateFrame("Frame")
    local function reg(event, unitOnly)
        local registered
        if unitOnly then
            registered = pcall(events.RegisterUnitEvent, events, event, "player")
        end
        if not registered then pcall(events.RegisterEvent, events, event) end
    end
    reg("UNIT_SPELLCAST_SUCCEEDED", true)
    reg("UNIT_SPELLCAST_CHANNEL_START", true)
    reg("UNIT_SPELLCAST_CHANNEL_STOP", true)
    if PlayerClass() == "DRUID" then
        reg("UNIT_DISPLAYPOWER", true)
        reg("UPDATE_SHAPESHIFT_FORM")
    end
    for _, event in ipairs({ "PLAYER_DEAD", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED" }) do
        reg(event)
    end
    events:SetScript("OnEvent", OnEvent)

    -- a child of the host, so a hidden tab or a hidden interface (Alt+Z) is a hidden ticker: no OnUpdate at all
    local ticker = CreateFrame("Frame", "FSFiveSecondTicker", FT.host)
    ticker:SetScript("OnUpdate", Tick)
    FT.ticker = ticker

    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SETTINGS.enabled.key, function()
            ApplyVisibility()
            if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
        end)
        -- a motion switch: read them again and repaint at once
        FT.watching = true
        local function motionChanged()
            FT.switchesDirty = true
            FT.sigCells.on, FT.sigRate.on = nil, nil
            if FT.host and FT.host:IsShown() then Refresh() end
        end
        FS.Config.OnChange(SETTINGS.motion.key, motionChanged)
        FS.Config.OnChange(SETTINGS.pulse.key, motionChanged)
        for _, name in ipairs(FT.FX_NAMES) do FS.Config.OnChange(SETTINGS[name].key, motionChanged) end
    end
    FT.switchesDirty = true
    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end

    RefreshForm()
    Tab.Update()
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("fivesecond_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end
    Sync()
end

-- Built at PLAYER_LOGIN, in combat too: nothing here is protected, and the seat waits for regen inside Sync.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    Apply()
end)
