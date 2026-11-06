-- Forever STUwave: LossOfControl
-- The stun / fear / silence alert in the middle of the screen, as the Gunsight "jam" (design: the loss of control
-- mockup, concept B, 2026-11-05). The Gunsight target brackets close on a big spell icon; an octagon well holds the
-- icon, and a ring of sixteen glowing ticks around it goes dark tick by tick as the effect runs out. The word
-- ("Stunned") and the seconds sit on a cut plate under it, with two crosshair lines off the brackets.
--
-- LossOfControlFrame (Blizzard_FrameXML/LossOfControlFrame.xml) keeps driving its own regions: the Icon and its
-- Cooldown sweep, AbilityName and TimeLeft (NumberText + SecondsText). We hold its smoke and red rails at alpha 0,
-- restyle the fonts and re-seat those regions into the jam's layout; the mixin re-anchors them each time it sets up
-- a display, so the seat is re-applied after SetUpDisplay and checked on every paint. Everything we draw lives on our
-- own child frame one level below it, so the icon and text draw on top.
--
-- It is an Edit Mode system frame, so nothing is written to it as a Lua field; what we track lives in this file.
-- The ring needs the effect's start and duration (C_LossOfControl); when the client gives none, or gives them as
-- secret values, every tick stays lit and Blizzard's icon sweep alone shows the time. The colour follows the
-- effect type when it is plain: pink stun, violet fear, cyan silence or pacify, amber root or disarm.
--
-- Plain frames and textures only, so legal in combat.

local _, FS = ...

local Theme = FS.Theme
local LOC = {}
FS.LossOfControl = LOC

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local SNAP_KEY = "hud.locSnap"
LOC.SNAP_SETTING = {
    label = "Stun alert snap in",
    key = SNAP_KEY,
    tip = "The brackets of the stun, fear and silence alert snap closed when it appears.",
}
if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(SNAP_KEY, true) end

-- Frame units, from the alert frame's centre (y up). The mockup's scene, centred on the icon.
local G = {
    ICON_Y = 24, ICON = 42, WELL = 54,
    RING_R = 39.5, TICKS = 16, TICK_BOX = 16,
    BOX_W = 116, BOX_H = 92, ARM = 14, ARM_T = 2,
    HAIR = 16, HAIR_IN = 6,
    PLATE_W = 160, PLATE_H = 40, PLATE_GAP = 52,     -- plate top this far under the icon centre
    WORD_PX = 17, TIME_PX = 11,
}

local IsSecret = FS.IsSecret or function() return false end

local function TypeColor(locType)
    if type(locType) ~= "string" or IsSecret(locType) then return Theme.COLOR_HEALTH end
    if locType:find("FEAR") then return Theme.COLOR_BORDER end
    if locType:find("SILENCE") or locType:find("PACIFY") or locType == "SCHOOL_INTERRUPT" then return Theme.COLOR_POWER end
    if locType == "ROOT" or locType == "DISARM" then return Theme.COLOR_AMBER end
    return Theme.COLOR_HEALTH
end
LOC.TypeColor = TypeColor

-- The first active effect: type, start, duration, each nil when the client does not say or says it as a secret.
local function ActiveEffect()
    local api = _G.C_LossOfControl
    local get = api and (api.GetActiveLossOfControlData or api.GetActiveLossOfControlDataByUnit)
    if type(get) ~= "function" then return nil end
    local ok, data
    if api.GetActiveLossOfControlData then
        ok, data = pcall(api.GetActiveLossOfControlData, 1)
    else
        ok, data = pcall(api.GetActiveLossOfControlDataByUnit, "player", 1)
    end
    if not ok or type(data) ~= "table" then return nil end
    local function plain(v) if type(v) == "number" and not IsSecret(v) then return v end end
    local locType = data.locType
    if IsSecret(locType) then locType = nil end
    return locType, plain(data.startTime), plain(data.duration)
end

-- Ticks still lit for `left` of `duration` seconds: all sixteen when the time is unknown.
function LOC.LitTicks(left, duration)
    if not (left and duration) or duration <= 0 then return G.TICKS end
    local f = math.max(0, math.min(1, left / duration))
    return math.ceil(f * G.TICKS - 1e-9)
end

local frame, plate
local parts = {}

local function Flat(parent, layer, sub)
    local t = parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0)
    t:SetColorTexture(1, 1, 1, 1)
    if t.SetSnapToPixelGrid then pcall(t.SetSnapToPixelGrid, t, true) end
    if t.SetTexelSnappingBias then pcall(t.SetTexelSnappingBias, t, 0) end
    return t
end

local function Tint(t, c, a) t:SetVertexColor(c[1], c[2], c[3], a or 1) end

local function Region(...)
    local o = frame
    for i = 1, select("#", ...) do
        if type(o) ~= "table" then return nil end
        o = o[select(i, ...)]
    end
    return o
end

-- The time row ("1.2" then "seconds") is centred as a PAIR under the plate: the number's left edge sits half the
-- pair's width left of centre. Pinning the number's right edge to the centre instead left the long "seconds" word
-- hanging off to the right, the whole row visibly off centre (player, 2026-11-05). Widths are measured each tick
-- (the number changes length: "10", "9.8", "1.2") and the row is moved only when the width changed. An unmeasurable
-- width (secret or missing) falls back to the number alone centred.
local TIME_GAP = 4
local seatedTimeW
local SeatTime

local function PlainW(fs)
    if not (fs and fs.GetStringWidth) then return nil end
    local ok, w = pcall(fs.GetStringWidth, fs)
    if ok and type(w) == "number" and not FS.IsSecret(w) then return w end
    return nil
end

SeatTime = function()
    local number, seconds = Region("TimeLeft", "NumberText"), Region("TimeLeft", "SecondsText")
    if not (number and number.ClearAllPoints) then return end
    local nw, sw = PlainW(number), PlainW(seconds)
    local total = (nw and sw) and (nw + TIME_GAP + sw) or -1
    if total == seatedTimeW then return end
    seatedTimeW = total
    local y = G.ICON_Y - G.PLATE_GAP - G.PLATE_H / 2 - 10
    number:ClearAllPoints()
    if total >= 0 then
        number:SetPoint("LEFT", frame, "CENTER", math.floor(-total / 2 + 0.5), y)
    else
        number:SetPoint("CENTER", frame, "CENTER", 0, y)
    end
    if seconds and seconds.ClearAllPoints then
        seconds:ClearAllPoints()
        seconds:SetPoint("LEFT", number, "RIGHT", TIME_GAP, 0)
    end
end

-- Puts Blizzard's icon and text into the jam's layout. The mixin's own anchors are replaced every time.
local function Seat()
    local icon = frame.Icon
    if icon and icon.ClearAllPoints then
        icon:ClearAllPoints()
        icon:SetPoint("CENTER", frame, "CENTER", 0, G.ICON_Y)
        icon:SetSize(G.ICON, G.ICON)
    end
    local plateMid = G.ICON_Y - G.PLATE_GAP - G.PLATE_H / 2
    local name = frame.AbilityName
    if name and name.ClearAllPoints then
        name:ClearAllPoints()
        name:SetPoint("CENTER", frame, "CENTER", 0, plateMid + 6)
        if name.SetJustifyH then name:SetJustifyH("CENTER") end
    end
    seatedTimeW = nil
    SeatTime()
end

local function Seated()
    local icon = frame.Icon
    if not (icon and icon.GetPoint) then return true end
    local ok, point, rel, _, x, y = pcall(icon.GetPoint, icon, 1)
    if not (ok and point == "CENTER" and rel == frame and x == 0 and y == G.ICON_Y) then return false end
    -- The mixin moves the word with its own centre offset too (SetPoint without ClearAllPoints).
    local name = frame.AbilityName
    if not (name and name.GetPoint) then return true end
    local okName, _, _, _, nx = pcall(name.GetPoint, name, 1)
    return okName and nx == 0
end

local function Build()
    plate = CreateFrame("Frame", nil, frame)
    plate:SetFrameStrata(frame:GetFrameStrata())
    plate:SetFrameLevel(math.max(0, frame:GetFrameLevel() - 1))
    plate:SetPoint("CENTER", frame, "CENTER", 0, 0)
    plate:SetSize(G.BOX_W + 2 * G.HAIR, G.BOX_H + 120)
    plate:EnableMouse(false)

    -- the brackets and crosshairs on their own frame, so the snap in can scale them alone
    local box = CreateFrame("Frame", nil, plate)
    box:SetPoint("CENTER", frame, "CENTER", 0, G.ICON_Y)
    box:SetSize(G.BOX_W, G.BOX_H)
    parts.box = box
    parts.arms = {}
    local hw, hh, a, t = G.BOX_W / 2, G.BOX_H / 2, G.ARM, G.ARM_T
    for _, c in ipairs({ { -1, 1 }, { 1, 1 }, { -1, -1 }, { 1, -1 } }) do
        local sx, sy = c[1], c[2]
        local across = Flat(box, "ARTWORK", 1)
        across:SetSize(a, t)
        across:SetPoint("CENTER", box, "CENTER", sx * (hw - a / 2), sy * (hh - t / 2))
        local down = Flat(box, "ARTWORK", 1)
        down:SetSize(t, a)
        down:SetPoint("CENTER", box, "CENTER", sx * (hw - t / 2), sy * (hh - a / 2))
        parts.arms[#parts.arms + 1] = across
        parts.arms[#parts.arms + 1] = down
    end
    parts.hairs = {}
    for _, sx in ipairs({ -1, 1 }) do
        local hair = Flat(box, "ARTWORK", 1)
        hair:SetSize(G.HAIR, 1)
        hair:SetPoint("CENTER", box, "CENTER", sx * (hw + G.HAIR / 2 - G.HAIR_IN), 0)
        parts.hairs[#parts.hairs + 1] = hair
    end

    -- the octagon well under the icon
    local well = CreateFrame("Frame", nil, plate)
    well:SetPoint("CENTER", frame, "CENTER", 0, G.ICON_Y)
    well:SetSize(G.WELL, G.WELL)
    parts.wellFill = Theme.AddSliceTexture(well, Theme.SLICE_CUT_FILL_TEXTURE, Theme.COLOR_BAR_TRACK, "BACKGROUND", 1)
    Theme.ApplyNineSlice(parts.wellFill, Theme.SLICE_CUT_MARGIN)
    parts.wellRing = Theme.AddCutCornerOutline(well, Theme.COLOR_HEALTH, "BORDER", 1)

    -- the ring: sixteen copies of one glowing tick, turned into place, tick 0 at the top, clockwise
    parts.ticks = {}
    for i = 0, G.TICKS - 1 do
        local an = i / G.TICKS * 2 * math.pi
        local tick = plate:CreateTexture(nil, "ARTWORK", nil, 2)
        tick:SetTexture(MEDIA .. "loc_tick.tga")
        tick:SetSize(G.TICK_BOX, G.TICK_BOX)
        tick:SetPoint("CENTER", frame, "CENTER", G.RING_R * math.sin(an), G.ICON_Y + G.RING_R * math.cos(an))
        if tick.SetRotation then tick:SetRotation(-an) end
        parts.ticks[i + 1] = tick
    end

    -- the plate under it for the word and the seconds
    local under = CreateFrame("Frame", nil, plate)
    under:SetPoint("TOP", frame, "CENTER", 0, G.ICON_Y - G.PLATE_GAP)
    under:SetSize(G.PLATE_W, G.PLATE_H)
    parts.glow = Theme.AddCut2Texture(under, Theme.SLICE_CUT2_GLOW_TEXTURE, Theme.COLOR_HEALTH, "BACKGROUND", -8,
        -Theme.SLICE_CUT2_GLOW_PAD)
    parts.fill = Theme.AddCut2Texture(under, Theme.SLICE_CUT2_FILL_TEXTURE, { 0.071, 0.039, 0.141, 0.92 }, "BACKGROUND", -6)
    parts.edge = Theme.AddCut2Texture(under, Theme.SLICE_CUT2_OUTLINE_TEXTURE, Theme.COLOR_HEALTH, "BORDER", 0)

    -- the snap in: the brackets come in from 1.25x and fade up, once per appearance
    if box.CreateAnimationGroup then
        local ag = box:CreateAnimationGroup()
        local scale = ag:CreateAnimation("Scale")
        if scale.SetScaleFrom then scale:SetScaleFrom(1.25, 1.25); scale:SetScaleTo(1, 1) end
        scale:SetDuration(0.14)
        if scale.SetSmoothing then scale:SetSmoothing("OUT") end
        local fade = ag:CreateAnimation("Alpha")
        fade:SetFromAlpha(0.2); fade:SetToAlpha(1); fade:SetDuration(0.14)
        parts.snap = ag
    end
end

local effect = {}

local function Paint()
    if not plate then return end
    local col = TypeColor(effect.locType)
    if parts.col ~= col then
        parts.col = col
        for _, arm in ipairs(parts.arms) do Tint(arm, col, 1) end
        for _, hair in ipairs(parts.hairs) do Tint(hair, col, 0.7) end
        Tint(parts.wellRing, col, 1)
        Tint(parts.glow, col, 0.35)
        Tint(parts.edge, col, 0.7)
        local name = frame.AbilityName
        local number, seconds = Region("TimeLeft", "NumberText"), Region("TimeLeft", "SecondsText")
        if number and number.SetTextColor then number:SetTextColor(col[1], col[2], col[3]) end
        if seconds and seconds.SetTextColor then seconds:SetTextColor(col[1], col[2], col[3], 0.75) end
        if name and name.SetTextColor then name:SetTextColor(1, 1, 1) end
    end
    local left = effect.start and effect.duration and (effect.start + effect.duration - GetTime()) or nil
    local lit = LOC.LitTicks(left, effect.duration)
    if parts.lit ~= lit then
        parts.lit = lit
        local dim = Theme.COLOR_BORDER
        for i, tick in ipairs(parts.ticks) do
            if i <= lit then Tint(tick, col, 1) else Tint(tick, dim, 0.25) end
        end
    end
end

local function Refresh()
    effect.locType, effect.start, effect.duration = ActiveEffect()
    parts.col, parts.lit = nil, nil
    Seat()
    Paint()
end

local function SnapOn()
    if not (FS.Config and FS.Config.Get) then return true end
    local ok, v = pcall(FS.Config.Get, SNAP_KEY)
    return not ok or v ~= false
end

function LOC.Apply()
    frame = _G.LossOfControlFrame
    if type(frame) ~= "table" or plate or type(frame.CreateTexture) ~= "function" then return end
    for _, key in ipairs({ "blackBg", "RedLineTop", "RedLineBottom" }) do
        local region = frame[key]
        if region and region.SetAlpha then
            region:SetAlpha(0)
            if region.SetAlpha and hooksecurefunc then
                local zeroing = false
                hooksecurefunc(region, "SetAlpha", function(self)
                    if zeroing then return end
                    zeroing = true; self:SetAlpha(0); zeroing = false
                end)
            end
        end
    end
    if frame.Icon and frame.Icon.SetTexCoord then frame.Icon:SetTexCoord(0.08, 0.92, 0.08, 0.92) end

    local name = frame.AbilityName
    if name and name.SetFont then Theme.ApplyFontGeneric(name, Theme.FONT_ORBITRON, G.WORD_PX, Theme.COLOR_TEXT_WHITE, "") end
    local number, seconds = Region("TimeLeft", "NumberText"), Region("TimeLeft", "SecondsText")
    if number and number.SetFont then Theme.ApplyMono(number, G.TIME_PX, Theme.COLOR_HEALTH) end
    if seconds and seconds.SetFont then Theme.ApplyMono(seconds, G.TIME_PX, Theme.COLOR_HEALTH) end

    Build()
    Refresh()

    if type(frame.SetUpDisplay) == "function" and hooksecurefunc then
        hooksecurefunc(frame, "SetUpDisplay", function()
            Refresh()
            if parts.snap and SnapOn() then parts.snap:Stop(); parts.snap:Play() end
        end)
    end
    if frame.HookScript then
        frame:HookScript("OnShow", function()
            Refresh()
            if parts.snap and SnapOn() then parts.snap:Stop(); parts.snap:Play() end
        end)
    end
    local acc = 0
    plate:SetScript("OnUpdate", function(_, elapsed)
        acc = acc + elapsed
        if acc < 0.05 then return end
        acc = 0
        if not Seated() then Seat() else SeatTime() end
        Paint()
    end)
end

local function SafeApply()
    local ok, err = pcall(LOC.Apply)
    if not ok and FS.LogDegradeOnce then FS.LogDegradeOnce("losscontrol", "Loss of control alert: " .. tostring(err)) end
end

if InCombatLockdown() then
    local regen = CreateFrame("Frame")
    regen:RegisterEvent("PLAYER_REGEN_ENABLED")
    regen:SetScript("OnEvent", function(self)
        self:UnregisterEvent("PLAYER_REGEN_ENABLED")
        SafeApply()
    end)
else
    SafeApply()
end
