-- Forever STUwave: five second rule tab
--
-- A second shoulder on the Console chassis for every class whose power is mana (mockups/five-second-rule-module-2026-10-14.html,
-- concept C, CELLS): 2 columns x 1 row (92.8 x 49 design px), the chrome of the Shaman buff tab (BuffTab.lua), seated after the
-- class's own tab when it has one and in its place otherwise (ClassShoulder.lua owns the seat). It is a player side cue, always
-- there, not gated on a target, and display only: no click, no binding. Two 38 px tiles:
--
--   * CELLS: five cells. A mana spend starts a five second window; the cells are amber and drain one a second right to left
--     (the current cell part full), the text counts in tenths behind a "~" and says SUSPENDED in the tooltip. At 0.0 the cells
--     turn cyan and the word is REGEN, the rim flashes once (the pulse), a short sound plays if the player turned it on, and a
--     few seconds later the tile fades to its dim idle look.
--   * RATE: mana per second and a retention chip. The pair GetPowerRegen returns is plain out of combat only, so it is read
--     out of combat and kept; the underline is dashed while the numbers on show are the kept ones. The casting rate shows
--     while the window runs, the full rate otherwise. The chip is the percent of the full rate that casting keeps (a
--     talent such as Meditation), cyan when above 0, a hollow "0%" otherwise.
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
-- Nothing here is protected: the host and both tiles are plain frames, so building, the paint, the master toggle and the Druid
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
    TICK_FAST = 0.1, TICK_SLOW = 0.5,
    -- the tile numbers are BuffTab's (the same chrome), design px
    BTN = 38, GAP = 4.8, PAD = 6, PT = 6, PB = 5, COLS = 2,
    CELLS = 5, CELL_X = 4, CELL_PITCH = 6.5, CELL_Y = 6, CELL_W = 4, CELL_H = 12,
    CHIP_W = 22, CHIP_H = 15, CHIP_TOP = 5, CHIP_C = 3, GLOW_PAD = 3,
    CODE_PX = 10, TEXT_PX = 11, REGEN_PX = 10, RATE_PX = 10, RATE_LONG_PX = 9,
    MIN_PX = 6, TEXT_INSET = 3, ADVANCE = 0.5615, TEXT_Y = 27,
    IDLE_CELL_ALPHA = 0.4,
    host = nil, cells = nil, rate = nil,
    built = false,
    seated = false,
    pendingSync = false,
    warned = {},
}
Tab.FT = FT

-- Settings: read by the config window at page build, each explained there by its `tip` (a ? icon), never by a helper line.
local SETTINGS = {
    enabled = {
        key = "fivesecond.enabled", default = true, label = "Five second rule tab",
        tip = "A tab on the Console that counts the five seconds after you spend mana, when your regen is suspended, "
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
    L.endsAt, L.resumed, L.channel, L.pulseAt = nil, false, false, nil
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
    if Setting(SETTINGS.pulse) then
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
    FT.active = phase == "susp" or pulse > 0 or (phase == "res" and fade < 1)
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
            add("Five second rule", amber)
            add(string.format("About %.1f s until regen resumes.", math.max(0, v.t)), white, true)
        else
            add("Five second rule", cyan)
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
    add(string.format("%s per second now, %s once the rule ends.", v.rateText, rate.baseText), white, true)
    if v.cached then add("Read out of combat, kept while you fight.", muted, true) end
    if v.ret then add(string.format("You keep %d%% of it while you cast.", v.ret), muted, true) end
    return lines
end

-- `refresh`: the tile already owns the tooltip, so only its lines are rewritten (no new SetOwner, which would clear and
-- re-place it every tick); a client without ClearLines anchors again.
local function ShowTooltip(tile, refresh)
    local tip = GameTooltip
    if not tip then return end
    local lines = Tab.TipLines(tile.fsKey)
    if refresh and type(tip.ClearLines) == "function" then
        tip:ClearLines()
    else
        FH.AnchorTooltip(tile)
    end
    for _, line in ipairs(lines) do
        local c = line[2]
        tip:AddLine(line[1], c[1], c[2], c[3], line[3])
    end
    tip:Show()
end

local function TipIsOurs(tile)
    local tip = GameTooltip
    if not (tip and tile.fsHover) then return false end
    if type(tip.IsOwned) == "function" then return tip:IsOwned(tile) and true or false end
    if type(tip.GetOwner) == "function" then return tip:GetOwner() == tile end
    return true
end

-------------------------------------------------------------------------------
-- Painting (texture and font writes only)
-------------------------------------------------------------------------------

local BG = { 13 / 255, 6 / 255, 32 / 255 }                 -- #0d0620
local GAP_FILL = { 0x1a / 255, 0x0f / 255, 0x2e / 255 }    -- #1a0f2e the dashes of the cached underline

local function Lerp(a, b, t)
    return a + (b - a) * t
end

-- Moves `a` toward `b` by t and writes it to a texture (or a font string) with the alpha.
local function Tint(region, a, b, t, alpha)
    region:SetVertexColor(Lerp(a[1], b[1], t), Lerp(a[2], b[2], t), Lerp(a[3], b[3], t), alpha)
end

local function TintText(region, a, b, t, alpha)
    region:SetTextColor(Lerp(a[1], b[1], t), Lerp(a[2], b[2], t), Lerp(a[3], b[3], t), alpha)
end

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

local function Hex(c)
    return string.format("|cff%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5),
        math.floor(c[3] * 255 + 0.5))
end

-- The rim: the border ring and its glow, lit cyan under the mouse.
local function PaintRim(tile, color, colorA, glowColor, glowA)
    local skin = tile.fsSkin
    local cyan = FS.Theme.COLOR_POWER
    if tile.fsHover then
        color, colorA, glowColor, glowA = cyan, 1, cyan, math.max(glowA, 0.6)
    end
    if skin and skin.border and skin.border.ring then
        skin.border.ring:SetVertexColor(color[1], color[2], color[3], colorA)
    end
    if skin and skin.glow then
        skin.glow:SetVertexColor(glowColor[1], glowColor[2], glowColor[3], glowA)
    end
end

local scratch = { 0, 0, 0 }

local function PaintCells(tile)
    local T = FS.Theme
    local amber, cyan, muted = T.COLOR_AMBER, T.COLOR_POWER, T.COLOR_MUTED
    local violet = T.COLOR_BORDER
    local v = view
    local susp = v.phase == "susp"
    local f = susp and 1 or v.fade
    local hover = tile.fsHover and true or false
    local tenths = susp and math.floor(v.t * 10 + 0.5) or -1
    local fq, pq = math.floor(f * 20 + 0.5), math.floor(v.pulse * 20 + 0.5)
    if tile.fsSig and tile.fsPhase == v.phase and tile.fsTenths == tenths and tile.fsFq == fq and tile.fsPq == pq
        and tile.fsHov == hover then
        return
    end
    tile.fsSig, tile.fsPhase, tile.fsTenths, tile.fsFq, tile.fsPq, tile.fsHov = true, v.phase, tenths, fq, pq, hover

    local h = FT.CELL_H * Scale()
    local cellA = FT.IDLE_CELL_ALPHA + (1 - FT.IDLE_CELL_ALPHA) * f
    for i, cell in ipairs(tile.fsCells) do
        local a = susp and math.max(0, math.min(1, v.t - (i - 1))) or 1
        if a > 0 then
            cell.fill:SetHeight(h * a)
            cell.fill:Show()
        else
            cell.fill:Hide()
        end
        local c = susp and amber or cyan
        cell.fill:SetVertexColor(c[1], c[2], c[3], susp and 1 or cellA)
    end

    local glowA, ringA = 0, 0.35
    if susp then
        scratch[1], scratch[2], scratch[3] = Lerp(BG[1], amber[1], 0.09), Lerp(BG[2], amber[2], 0.09), Lerp(BG[3], amber[3], 0.09)
        tile.fsPlate:SetVertexColor(scratch[1], scratch[2], scratch[3], 0.9)
        PaintRim(tile, amber, 0.65, amber, 0)
        tile.fsLine:SetVertexColor(amber[1], amber[2], amber[3], 0.9)
        SetText(tile.fsText, FT.TEXT_PX, Hex(amber) .. "~|r" .. string.format("%.1f", math.max(0, v.t)))
        tile.fsText:SetTextColor(1, 1, 1, 1)
    else
        -- idle (f = 0) to the regen look (f = 1)
        scratch[1], scratch[2], scratch[3] = Lerp(BG[1], Lerp(BG[1], cyan[1], 0.1), f), Lerp(BG[2], Lerp(BG[2], cyan[2], 0.1), f),
            Lerp(BG[3], Lerp(BG[3], cyan[3], 0.1), f)
        tile.fsPlate:SetVertexColor(scratch[1], scratch[2], scratch[3], Lerp(0.72, 0.9, f))
        ringA = Lerp(0.35, 1, f)
        glowA = 0.35 * f + 0.65 * v.pulse
        scratch[1], scratch[2], scratch[3] = Lerp(violet[1], cyan[1], f), Lerp(violet[2], cyan[2], f), Lerp(violet[3], cyan[3], f)
        PaintRim(tile, scratch, ringA, cyan, glowA)
        Tint(tile.fsLine, muted, cyan, f, Lerp(0.5, 0.9, f))
        local size = FitPx("REGEN", FT.REGEN_PX, FT.BTN - 2 * FT.TEXT_INSET)
        SetText(tile.fsText, size, "REGEN")
        TintText(tile.fsText, muted, cyan, f, Lerp(0.75, 1, f))
    end
end

local HOLLOW_MIX = 0.25

local function PaintRate(tile)
    local T = FS.Theme
    local cyan, muted, white = T.COLOR_POWER, T.COLOR_MUTED, T.COLOR_TEXT_WHITE
    local violet = T.COLOR_BORDER
    local v = view
    local hover = tile.fsHover and true or false
    local act = v.phase == "susp" and 1 or v.fade
    local aq = math.floor(act * 20 + 0.5)
    local hasRate = v.rateText ~= nil
    if tile.fsSig and tile.fsRate == v.rateText and tile.fsCached == v.cached and tile.fsRet == v.ret
        and tile.fsAq == aq and tile.fsHov == hover and tile.fsHas == hasRate then
        return
    end
    tile.fsSig, tile.fsRate, tile.fsCached, tile.fsRet, tile.fsAq, tile.fsHov, tile.fsHas =
        true, v.rateText, v.cached, v.ret, aq, hover, hasRate

    tile.fsPlate:SetVertexColor(BG[1], BG[2], BG[3], 0.72)
    PaintRim(tile, violet, 0.35, violet, 0)

    local chip = tile.fsChip
    if v.ret then
        chip.fill:SetVertexColor(Lerp(BG[1], cyan[1], 0.3), Lerp(BG[2], cyan[2], 0.3), Lerp(BG[3], cyan[3], 0.3), 1)
        chip.ring:SetVertexColor(cyan[1], cyan[2], cyan[3], 1)
        chip.glow:SetVertexColor(cyan[1], cyan[2], cyan[3], 0.35)
        chip.code:SetTextColor(white[1], white[2], white[3], 1)
        SetText(chip.code, FitPx(v.ret .. "%", FT.CODE_PX, FT.CHIP_W - 2), v.ret .. "%")
    else
        local r, g, b = Lerp(muted[1], 1, HOLLOW_MIX), Lerp(muted[2], 1, HOLLOW_MIX), Lerp(muted[3], 1, HOLLOW_MIX)
        chip.fill:SetVertexColor(BG[1], BG[2], BG[3], 0.7)
        chip.ring:SetVertexColor(r, g, b, 1)
        chip.glow:SetVertexColor(r, g, b, 0)
        chip.code:SetTextColor(r, g, b, 1)
        SetText(chip.code, FitPx("0%", FT.CODE_PX, FT.CHIP_W - 2), "0%")
    end

    local text = hasRate and (v.rateText .. "/s") or "--"
    local base = (hasRate and #v.rateText >= 4) and FT.RATE_LONG_PX or FT.RATE_PX
    SetText(tile.fsText, FitPx(text, base, FT.BTN - 2 * FT.TEXT_INSET), text)
    tile.fsText:SetTextColor(white[1], white[2], white[3], Lerp(0.8, 1, act))
    tile.fsLine:SetVertexColor(cyan[1], cyan[2], cyan[3], Lerp(0.5, 0.9, act))
    local dashed = v.cached and 1 or 0
    for _, dash in ipairs(tile.fsDashes) do dash:SetAlpha(dashed) end
end

function Tab.Paint()
    if not FT.built then return end
    PaintCells(FT.cells)
    PaintRate(FT.rate)
    for _, tile in ipairs(FT.tiles) do
        if TipIsOurs(tile) then ShowTooltip(tile, true) end
    end
end

-------------------------------------------------------------------------------
-- The tiles
-------------------------------------------------------------------------------

local function NewText(parent, px)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(fs, px, FS.Theme.COLOR_TEXT_WHITE)
    fs.fsPx = px
    return fs
end

-- Runs once per tile, from Build and again on every re-seat. Everything that creates a region or hook is guarded so a
-- throw partway is finished by the next Build.
local function StyleTile(tile, scale)
    local T = FS.Theme
    local s = scale
    tile:SetSize(FT.BTN * s, FT.BTN * s)

    if not tile.fsPlate then
        tile.fsPlate = T.AddCut2Texture(tile, T.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    T.SkinCutButton(tile, { borderColor = T.COLOR_BORDER, glowAlpha = 0 })

    if not tile.fsHooked then
        tile.fsHooked = true
        tile:EnableMouse(true)
        tile:SetScript("OnEnter", function(self)
            self.fsHover = true
            self.fsSig = nil
            Tab.Paint()
            ShowTooltip(self)
        end)
        tile:SetScript("OnLeave", function(self)
            self.fsHover = nil
            self.fsSig = nil
            Tab.Paint()
            GameTooltip:Hide()
        end)
    end

    if not tile.fsFace then
        local face = CreateFrame("Frame", nil, tile)
        face:SetAllPoints(tile)
        face:EnableMouse(false)
        tile.fsFace = face

        tile.fsText = NewText(face, FT.TEXT_PX)
        tile.fsText:SetJustifyH("CENTER")
        tile.fsLine = face:CreateTexture(nil, "OVERLAY", nil, 2)
        tile.fsLine:SetColorTexture(1, 1, 1, 1)

        if tile.fsKey == "cells" then
            local v = T.COLOR_BORDER
            tile.fsCells = {}
            for i = 1, FT.CELLS do
                local cell = { edges = {} }
                for k = 1, 4 do
                    local edge = face:CreateTexture(nil, "ARTWORK", nil, 0)
                    edge:SetColorTexture(v[1], v[2], v[3], 0.5)
                    cell.edges[k] = edge
                end
                cell.fill = face:CreateTexture(nil, "ARTWORK", nil, 1)
                cell.fill:SetColorTexture(1, 1, 1, 1)
                tile.fsCells[i] = cell
            end
        else
            local c = FT.CHIP_C
            local ringPath, glowPath = MEDIA .. "slice_cut2_outline_c3.tga", MEDIA .. "slice_cut2_glow_c3.tga"
            if T.Cut2ButtonSet then
                local ok, ring, glow, used = pcall(T.Cut2ButtonSet, FT.CHIP_C)
                if ok and type(ring) == "string" and type(glow) == "string" then
                    ringPath, glowPath, c = ring, glow, used or c
                end
            end
            local chip = {}
            chip.glow = face:CreateTexture(nil, "BACKGROUND", nil, 0)
            chip.glow:SetTexture(glowPath)
            T.ApplyNineSlice(chip.glow, (T.SLICE_CUT2_GLOW_PAD or 4) + c)
            chip.glow:SetBlendMode("ADD")
            chip.fill = face:CreateTexture(nil, "BACKGROUND", nil, 1)
            chip.fill:SetTexture(MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
            T.ApplyNineSlice(chip.fill, c)
            chip.ring = face:CreateTexture(nil, "ARTWORK", nil, 0)
            chip.ring:SetTexture(ringPath)
            T.ApplyNineSlice(chip.ring, c)
            chip.code = NewText(face, FT.CODE_PX)
            chip.code:SetJustifyH("CENTER")
            tile.fsChip = chip
            tile.fsDashes = {}
            for i = 1, 4 do
                local dash = face:CreateTexture(nil, "OVERLAY", nil, 3)
                dash:SetColorTexture(GAP_FILL[1], GAP_FILL[2], GAP_FILL[3], 1)
                dash:SetAlpha(0)
                tile.fsDashes[i] = dash
            end
        end
    end

    tile.fsText:ClearAllPoints()
    tile.fsText:SetPoint("CENTER", tile, "TOP", 0, -FT.TEXT_Y * s)
    tile.fsLine:ClearAllPoints()
    tile.fsLine:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", 5 * s, 3 * s)
    tile.fsLine:SetPoint("BOTTOMRIGHT", tile, "BOTTOMRIGHT", -5 * s, 3 * s)
    tile.fsLine:SetHeight(2 * s)

    if tile.fsCells then
        local w, h, t = FT.CELL_W * s, FT.CELL_H * s, 1 * s
        local bottom = (FT.BTN - FT.CELL_Y - FT.CELL_H) * s
        for i, cell in ipairs(tile.fsCells) do
            local x = (FT.CELL_X + (i - 1) * FT.CELL_PITCH) * s
            local top, under, left, right = cell.edges[1], cell.edges[2], cell.edges[3], cell.edges[4]
            top:ClearAllPoints()
            top:SetPoint("TOPLEFT", tile, "TOPLEFT", x, -FT.CELL_Y * s)
            top:SetSize(w, t)
            under:ClearAllPoints()
            under:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", x, bottom)
            under:SetSize(w, t)
            left:ClearAllPoints()
            left:SetPoint("TOPLEFT", tile, "TOPLEFT", x, -FT.CELL_Y * s)
            left:SetSize(t, h)
            right:ClearAllPoints()
            right:SetPoint("TOPLEFT", tile, "TOPLEFT", x + w - t, -FT.CELL_Y * s)
            right:SetSize(t, h)
            cell.fill:ClearAllPoints()
            cell.fill:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", x, bottom)
            cell.fill:SetWidth(w)
            cell.fill:SetHeight(h)
        end
    else
        local chip = tile.fsChip
        local x = (FT.BTN - FT.CHIP_W) / 2 * s
        for _, tex in ipairs({ chip.fill, chip.ring }) do
            tex:ClearAllPoints()
            tex:SetPoint("TOPLEFT", tile, "TOPLEFT", x, -FT.CHIP_TOP * s)
            tex:SetSize(FT.CHIP_W * s, FT.CHIP_H * s)
        end
        chip.glow:ClearAllPoints()
        chip.glow:SetPoint("TOPLEFT", tile, "TOPLEFT", x - FT.GLOW_PAD * s, (-FT.CHIP_TOP + FT.GLOW_PAD) * s)
        chip.glow:SetSize((FT.CHIP_W + 2 * FT.GLOW_PAD) * s, (FT.CHIP_H + 2 * FT.GLOW_PAD) * s)
        chip.code:ClearAllPoints()
        chip.code:SetPoint("CENTER", chip.fill, "CENTER", 0, -0.5 * s)
        for i, dash in ipairs(tile.fsDashes) do
            dash:ClearAllPoints()
            dash:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", (5 + 4 + (i - 1) * 6) * s, 3 * s)
            dash:SetSize(2 * s, 2 * s)
        end
    end
    tile.fsSig = nil        -- sizes and points were rewritten: paint again (fonts are never scaled)
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

-- Where tile `col` (1..2) stands on the host.
function Tab.SlotPoint(col)
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.SlotPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, FT.host, 1, col, FT.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s, pitch = Scale(), FT.BTN + FT.GAP
    return "BOTTOMLEFT", FT.host, "BOTTOMLEFT", (FT.PAD + (col - 1) * pitch) * s, FT.PB * s
end

local function ApplyVisibility()
    local host = FT.host
    if not host then return end
    local want = FT.seated and Tab.Shown() or false
    host:SetShown(want)
    if want then Tab.Update() Tab.Paint() end
end
Tab.ApplyVisibility = ApplyVisibility

local function SeatTiles()
    local s = Scale()
    FT.host:SetSize((2 * FT.PAD + FT.COLS * FT.BTN + (FT.COLS - 1) * FT.GAP) * s, (FT.PT + FT.BTN + FT.PB) * s)
    for i, tile in ipairs(FT.tiles) do
        StyleTile(tile, s)
        tile:ClearAllPoints()
        tile:SetPoint(Tab.SlotPoint(i))
    end
end

local function SeatHost()
    local host = FT.host
    local point, rel, relPoint, x, y = Tab.HostPoint()
    if not point then
        FT.seated = false
        host:Hide()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    FT.seated = true
    ApplyVisibility()
end

-- The seat steps. The tiles are plain frames on a plain host, so styling and sizing them is legal in combat and happens at
-- once; the host's anchor onto the Console waits for PLAYER_REGEN_ENABLED like everything on the chassis. Each step is its own
-- pcall so one failure cannot stop the next.
local function Sync()
    if not FT.built then return end
    local ok, err = pcall(SeatTiles)
    if not ok then WarnOnce("fivesecond_sync", "five second rule tab update failed (" .. tostring(err) .. ")") end
    if InCombatLockdown() then
        FT.pendingSync = true
        return
    end
    FT.pendingSync = false
    ok, err = pcall(SeatHost)
    if not ok then WarnOnce("fivesecond_sync", "five second rule tab update failed (" .. tostring(err) .. ")") end
end
Tab.Sync = Sync

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    FT.host = CreateFrame("Frame", "FSFiveSecondTab", UIParent)
    FT.host:SetFrameStrata("LOW")
    FT.host:Hide()
    FT.cells = CreateFrame("Frame", "FSFiveSecondCells", FT.host)
    FT.cells.fsKey = "cells"
    FT.rate = CreateFrame("Frame", "FSFiveSecondRate", FT.host)
    FT.rate.fsKey = "rate"
    FT.tiles = { FT.cells, FT.rate }
    FT.built = true
end

local function Refresh()
    Tab.Update()
    if FT.host and FT.host:IsShown() then Tab.Paint() end
end

-- One pass about every tenth of a second while the window runs or a flash is dying, every half second otherwise. A plain
-- frame, nothing protected.
local function Tick(self, dt)
    self.fsElapsed = (self.fsElapsed or 0) + dt
    if self.fsElapsed < (FT.active and FT.TICK_FAST or FT.TICK_SLOW) then return end
    self.fsElapsed = 0
    local ok, err = pcall(Refresh)
    if not ok then WarnOnce("fivesecond_tick", "five second rule tab repaint failed (" .. tostring(err) .. ")") end
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
        print("|cff22e0ffForever STUwave|r: five second rule tab failed to build (" .. tostring(err) .. ")")
        return
    end

    -- Listeners start only now that the tiles exist (a failed or non-mana build leaves none running).
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

    local ticker = CreateFrame("Frame", "FSFiveSecondTicker")
    ticker:SetScript("OnUpdate", Tick)

    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SETTINGS.enabled.key, function()
            ApplyVisibility()
            if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
        end)
    end
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
