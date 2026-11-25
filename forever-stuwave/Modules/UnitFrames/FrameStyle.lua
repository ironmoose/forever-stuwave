-- Forever STUwave: Frame style
-- The one settings shape every frame page shares: bars.<frame>.<suffix>, frame in player, target, focus, boss, party, raid,
-- pet. This file owns the defaults (each equal to what the frame draws today), the readers and writers, the change
-- subscription, the linked frame and bar heights and the bar text formats. UnitFrames.lua, PartyFrames.lua, RaidFrames.lua
-- and PetFrame.lua read their look through it, and the config pages build their rows from the same tables, so a setting is
-- described once. A value equal to its default is stored as nothing (Config.Set), so a default frame saves no keys.
--
-- Text values: "none", "percent", "number", "both" (raid adds "low"). Position values: "left", "center", "right".
-- Bar styles: "cut", "laser", "flat", "led", "slant", "chevron", "stock".

local _, FS = ...

local Config = FS.Config
local IsSecret = FS.IsSecret or function() return false end

local Style = FS.FrameStyle or {}
FS.FrameStyle = Style

Style.FRAMES = { "player", "target", "focus", "boss", "party", "raid", "pet" }

Style.LABELS = {
    player = "Player", target = "Target", focus = "Focus", boss = "Boss", party = "Party", raid = "Raid", pet = "Pet",
}

-- The bar looks STUwave already draws somewhere. Value (stored), label (shown).
Style.BAR_STYLES = {
    { "cut", "Cut corner" }, { "laser", "Laser rail" }, { "flat", "Flat" }, { "led", "LED segments" },
    { "slant", "Slant cells" }, { "chevron", "Chevron" }, { "stock", "Stock" },
}

Style.TEXT_FORMATS = { { "none", "None" }, { "percent", "Percent" }, { "number", "Number" }, { "both", "Num + %" } }
Style.RAID_TEXT_FORMATS = { { "none", "None" }, { "percent", "Percent" }, { "low", "Low only" }, { "number", "Number" } }
Style.TEXT_POSITIONS = { { "left", "Left" }, { "center", "Center" }, { "right", "Right" } }

-- Geometry the unit frames draw (UnitFrames.lua constants, repeated here so the config reads one table).
Style.UNIT = { PAD_Y = 5, NAME_ROW = 22, NAME_GAP = 3, BAR_GAP = 6, CHIP_H = 16, ICON_PAD = 2, NAME_PAD = 7 }

-- The fixed part of a frame's height and the gap between its health and power bars, for the frames whose data row does
-- not move (party: pads and name row; raid: pad and name; pet: name row and gap). Unit frames are computed (FixedHeight).
Style.FIXED = { party = { 30, 4 }, raid = { 20, 2 }, pet = { 10, 2 } }

-------------------------------------------------------------------------------
-- Defaults
-------------------------------------------------------------------------------

local COMMON = {
    w = 260, hpStyle = "cut", mpStyle = "cut", hpH = 16, mpH = 16, alpha = 100, bgAlpha = 80,
    glow = true, glowAmt = 100,
    hpFmt = "number", hpTs = 11, hpTa = "center", hpTx = 0,
    mpFmt = "number", mpTs = 11, mpTa = "center", mpTx = 0,
    name = true, nameSize = 15, nameX = 0,
    classIcon = true, iconSize = 20, iconX = 0,
    level = true, levelSize = 11, levelX = 0,
    raidMark = true, markX = 0, resting = true,
    role = true, lowTag = true,
    elite = false, tot = false, combat = false, pet = true, portrait = false, cast = false, pvp = false, leader = false,
    threat = false, threatPct = false, threatX = 0,
    mkHot = true, dispelEdge = true, mkDebuff = true, mkDebuffWho = "mine", mkMagic = true, mkCurse = true,
    mkPoison = true, mkDisease = true, mkBuff = false, mkSize = 5, mkPos = "topright",
    alerts = true, alertSide = "left", alertSize = 22, alertMax = 3, alertCleanse = true, alertBuffs = true,
    raidLook = "auto", raidFmt = "low",
}

local PER_FRAME = {
    focus = { w = 190 },
    -- Boss frames are 210 wide today (FS.Layout.boss; the prototype said 190): the default keeps today's size.
    boss = { w = 210 },
    party = {
        w = 187, hpH = 9, mpH = 9, hpStyle = "laser", mpStyle = "laser", hpFmt = "percent", mpFmt = "none",
        hpTs = 14, mpTs = 14, nameSize = 10.5, iconSize = 16, levelSize = 8.5, threat = true,
    },
    raid = {
        w = 84, hpH = 6, mpH = 2, bgAlpha = 85, hpFmt = "none", raidFmt = "low", mpFmt = "none", hpTs = 7.5, mpTs = 7.5,
        nameSize = 8.5, threat = true,
    },
    pet = {
        w = 134, hpH = 7, mpH = 7, bgAlpha = 47, hpStyle = "laser", mpStyle = "laser", hpTs = 7.5, mpTs = 7.5,
        nameSize = 9, levelSize = 7.5,
    },
}

local defaults = {}
Style.DEFAULTS = defaults

local function BgAlphaDefault()
    local theme = FS.Theme
    local bg = theme and theme.COLOR_BG
    if type(bg) == "table" and type(bg[4]) == "number" then return math.floor(bg[4] * 100 + 0.5) end
    return 80
end

for _, frame in ipairs(Style.FRAMES) do
    local set = {}
    for suffix, value in pairs(COMMON) do set[suffix] = value end
    for suffix, value in pairs(PER_FRAME[frame] or {}) do set[suffix] = value end
    if frame ~= "raid" and frame ~= "pet" then set.bgAlpha = BgAlphaDefault() end
    defaults[frame] = set
end

function Style.Key(frame, suffix)
    return "bars." .. tostring(frame) .. "." .. tostring(suffix)
end

for _, frame in ipairs(Style.FRAMES) do
    for suffix, value in pairs(defaults[frame]) do Config.RegisterDefault(Style.Key(frame, suffix), value) end
end

-- The frame the shared Style tab on Unit Frames is showing (a remembered pick, not a frame setting).
Config.RegisterDefault("bars.module", "target")
-- The pet page: the cast bar plate (PetCastBar.lua), the happiness dot (PetFrame.lua) and which pet the preview shows.
Config.RegisterDefault("pet.cast", true)
Config.RegisterDefault("pet.castShow", "always")
Config.RegisterDefault("pet.castFree", "wider")
Config.RegisterDefault("pet.castIcon", true)
Config.RegisterDefault("pet.castName", true)
Config.RegisterDefault("pet.castTimer", true)
Config.RegisterDefault("pet.happy", false)
Config.RegisterDefault("pet.previewKind", "hunter")
Config.RegisterDefault("raid.scale", 100)
Config.RegisterDefault("raid.arrange", "columns")
Config.RegisterDefault("raid.perRow", 5)
Config.RegisterDefault("raid.sort", "group")

-------------------------------------------------------------------------------
-- Reading and writing
-------------------------------------------------------------------------------

function Style.Default(frame, suffix)
    local set = defaults[frame]
    return set and set[suffix]
end

-- Style.override = { frame, suffix, value } is set by the config window for the instant it redraws a preview with one
-- setting turned on (pointing at a row); nothing else runs in that instant, so a real frame never reads it.
function Style.Get(frame, suffix)
    local o = Style.override
    if o and o.frame == frame and o.suffix == suffix then return o.value end
    return Config.Get(Style.Key(frame, suffix))
end

-- The bar looks a frame can wear. The pill bars of the unit frames are cut (today) or one of the others; the party and pet
-- bars are laser rails (today) or one of the others. FrameHelpers.SetBarLook draws them all.
Style.RAIL_FRAMES = { party = true, pet = true }
function Style.LookAvailable(value, frame)
    local rail = Style.RAIL_FRAMES[frame] == true
    if value == "cut" then return not rail end
    if value == "laser" then return rail end
    local helpers = FS.FrameHelpers
    return type(helpers) == "table" and type(helpers.SetBarLook) == "function"
end

-- The bar look a frame's setting names, applied to `bar` (nothing happens when the helper is missing).
function Style.ApplyLook(frame, bar, suffix)
    local helpers = FS.FrameHelpers
    if bar and type(helpers) == "table" and type(helpers.SetBarLook) == "function" then
        helpers.SetBarLook(bar, Style.Get(frame, suffix))
    end
end

function Style.Set(frame, suffix, value)
    return Config.Set(Style.Key(frame, suffix), value)
end

function Style.IsStored(frame, suffix)
    return Config.IsStored(Style.Key(frame, suffix))
end

function Style.Reset(frame, suffix)
    return Config.Set(Style.Key(frame, suffix), nil)
end

local function Number(frame, suffix)
    local value = Style.Get(frame, suffix)
    if type(value) ~= "number" then return Style.Default(frame, suffix) end
    return value
end
Style.Number = Number

-------------------------------------------------------------------------------
-- Change subscription: fn(suffix, new, old) for every bars.<frame>.* key that changes (a profile switch too)
-------------------------------------------------------------------------------

local subscribers = {}
local listening = false

local function Listen()
    if listening then return end
    listening = true
    Config.OnAnyChange(function(key, new, old)
        if type(key) ~= "string" then return end
        local frame, suffix = key:match("^bars%.(%a+)%.(.+)$")
        local list = frame and subscribers[frame]
        if not list then return end
        for i = 1, #list do
            local ok, err = pcall(list[i], suffix, new, old)
            if not ok and FS.Layout and FS.Layout.ForwardError then FS.Layout.ForwardError(err) end
        end
    end)
end

function Style.OnChange(frame, fn)
    if type(frame) ~= "string" or type(fn) ~= "function" then return false end
    subscribers[frame] = subscribers[frame] or {}
    table.insert(subscribers[frame], fn)
    Listen()
    return true
end

-------------------------------------------------------------------------------
-- Heights: frame height = fixed part + health + gap + power (no gap with the power bar off)
-------------------------------------------------------------------------------

-- The height of the data row of a unit frame: the biggest part on it, 22 at the defaults, 0 when nothing is shown.
function Style.RowHeight(frame)
    local u = Style.UNIT
    local shown, h = false, 0
    if Style.Get(frame, "name") then
        shown = true
        h = math.max(h, Number(frame, "nameSize") + u.NAME_PAD)
    end
    if Style.Get(frame, "classIcon") or Style.Get(frame, "portrait") then
        shown = true
        h = math.max(h, Number(frame, "iconSize") + u.ICON_PAD)
    end
    if Style.Get(frame, "level") then
        shown = true
        h = math.max(h, u.CHIP_H)
    end
    if Style.Get(frame, "raidMark") then shown = true end
    if not shown then return 0 end
    return math.max(h, u.NAME_ROW)
end

-- Fixed part of the height and the gap under the data row, for the frame.
function Style.FixedHeight(frame)
    local fixed = Style.FIXED[frame]
    if fixed then return fixed[1], fixed[2] end
    local u = Style.UNIT
    local row = Style.RowHeight(frame)
    return 2 * u.PAD_Y + row + (row > 0 and u.NAME_GAP or 0), u.BAR_GAP
end

function Style.FrameHeight(frame)
    local fixed, gap = Style.FixedHeight(frame)
    local hp, mp = Number(frame, "hpH"), Number(frame, "mpH")
    return fixed + hp + (mp > 0 and (gap + mp) or 0)
end

-- Moving Frame Height changes only the health bar; it stops at the bar's own range.
function Style.SetFrameHeight(frame, height)
    if type(height) ~= "number" then return false end
    local fixed, gap = Style.FixedHeight(frame)
    local mp = Number(frame, "mpH")
    local hp = height - fixed - (mp > 0 and (gap + mp) or 0)
    hp = math.max(2, math.min(60, math.floor(hp + 0.5)))
    return Style.Set(frame, "hpH", hp)
end

-- The slider range of Frame Height for a frame: the health bar's own 2 to 60 with the power bar off and on.
function Style.HeightRange(frame)
    local fixed = Style.FixedHeight(frame)
    local _, gap = Style.FixedHeight(frame)
    return fixed + 2, fixed + 60 + gap + 40
end

-------------------------------------------------------------------------------
-- Bar text
-------------------------------------------------------------------------------

local percentBroken = { health = false, power = false }

function Style.PercentCurve()
    local constants = _G.CurveConstants
    if type(constants) == "table" and constants.ScaleTo100 ~= nil then return constants.ScaleTo100 end
end

-- Whether Percent and Num + % can work on this client (the engine percent reads and the 0 to 100 curve).
function Style.PercentAvailable(kind)
    if kind == "power" then
        if type(_G.UnitPowerPercent) ~= "function" then return false end
    else
        if type(_G.UnitHealthPercent) ~= "function" then return false end
    end
    return Style.PercentCurve() ~= nil
end

-- The engine hands the percent back (secret or not) and it goes straight to SetFormattedText, so a secret health or power
-- is never divided, compared or formatted by Lua. Returns the number (or nil) the read gave.
local function ReadPercent(unit, kind)
    if percentBroken[kind] or not Style.PercentAvailable(kind) then return nil end
    local curve = Style.PercentCurve()
    local ok, percent
    if kind == "power" then
        ok, percent = pcall(_G.UnitPowerPercent, unit, nil, false, curve)
    else
        ok, percent = pcall(_G.UnitHealthPercent, unit, false, curve)
    end
    if ok and type(percent) == "number" then return percent end
    if not ok then percentBroken[kind] = true end
    return nil
end

-- Writes a bar's value text. fmt: "none" hides it; "number" is "cur / max" (today's text); "percent" is the engine percent;
-- "both" is the number, two spaces, then the percent. When the percent cannot be read the number shows instead.
function Style.WriteBarText(text, fmt, unit, kind, cur, max)
    if fmt == "none" then
        text:Hide()
        return
    end
    text:Show()
    if fmt == "percent" or fmt == "both" then
        local percent = ReadPercent(unit, kind)
        if percent ~= nil then
            local ok
            if fmt == "percent" then
                ok = pcall(text.SetFormattedText, text, "%.0f%%", percent)
            else
                ok = pcall(text.SetFormattedText, text, "%d / %d  %.0f%%", cur, max, percent)
            end
            if ok then return end
            percentBroken[kind] = true
        end
    end
    text:SetFormattedText("%d / %d", cur, max)
end

-- The same text for two plain numbers, for the previews in the config window (nothing is read from a unit).
function Style.TextFor(fmt, cur, max)
    if fmt == "none" then return "" end
    local percent = max > 0 and math.floor(cur / max * 100 + 0.5) or 0
    if fmt == "percent" then return ("%d%%"):format(percent) end
    if fmt == "both" then return ("%d / %d  %d%%"):format(cur, max, percent) end
    return ("%d / %d"):format(cur, max)
end

-- Seats a bar's text: size, left / center / right and a nudge in x. The default (center, 0) is today's one anchor.
function Style.SeatBarText(text, bar, size, align, offset)
    if not text then return end
    local theme = FS.Theme
    if theme and theme.ApplyMono then theme.ApplyMono(text, size) end
    offset = type(offset) == "number" and offset or 0
    text:ClearAllPoints()
    if align == "left" then
        text:SetPoint("LEFT", bar, "LEFT", 4 + offset, 0)
    elseif align == "right" then
        text:SetPoint("RIGHT", bar, "RIGHT", -4 + offset, 0)
    else
        text:SetPoint("CENTER", bar, "CENTER", offset, 0)
    end
end

-- Used by the harness and the config: a secret is never a usable setting value.
function Style.IsPlain(value)
    return not IsSecret(value)
end
