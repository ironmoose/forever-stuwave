-- Forever STUwave: combo points on the target's nameplate
--
-- Five pips in a row under the current target's STUwave plate (Nameplates.lua), for a Rogue, and for a Druid
-- while its power is energy (Cat Form). A pip is a hard edged STUwave diamond (combo_pip_*.tga, from
-- tools/assets/generate_combo_pips.py) that lights pink with a soft glow when the count reaches it; at five every pip turns
-- gold, the same "ready" cue as the Rogue dagger fan.
--
--   * UnitPower(player, ComboPoints) may be secret, so Lua never looks at it: each pip is a StatusBar from i - 1 to i (and a
--     gold one from 4 to 5) fed the raw value, and the ENGINE decides what fills.
--   * One set of pips, built once, moved to whichever plate is the target's. FS.framesByUnit (Nameplates.lua) maps a plate unit
--     to its root; UnitIsUnit(unit, "target") is plain on this client. Our own frames only, so it is combat safe.
--   * Each pip is PIP physical px, re-sized from the plate's effective scale while shown (the engine scales plates).
--   * Setting nameplates.comboPips (on by default) turns it off.

local _, FS = ...

if not (C_NamePlate and FS.framesByUnit and FS.Config) then return end

local _, CLASS = UnitClass("player")
if CLASS ~= "ROGUE" and CLASS ~= "DRUID" then return end

local Config = FS.Config

local M = {}
FS.NameplateCombo = M

local COMBO_POWER = (Enum and Enum.PowerType and Enum.PowerType.ComboPoints) or 4
local ENERGY_POWER = (Enum and Enum.PowerType and Enum.PowerType.Energy) or 3
local COUNT = 5
local PIP, GAP = 16, 4                    -- physical px: a pip (one texel each), between pips
-- Under the plate, below the slot Nameplates.lua keeps for the target's cast bar (its gap and height, plate units), so a cast
-- never covers them. The height is the plate's own cast bar height setting (default 6, 0 to 16), read from the config.
local CAST_GAP, BELOW = 2, 3
local CAST_H_KEY, CAST_H_DEFAULT, CAST_H_MAX = "plates.castH", 6, 16
local STRATA = "HIGH"

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local REST, LIT, GLOW = MEDIA .. "combo_pip_rest.tga", MEDIA .. "combo_pip_lit.tga", MEDIA .. "combo_pip_glow.tga"
local PINK = { 1, 0x4d / 255, 0xd8 / 255 }
local GOLD = { 1, 0xd2 / 255, 0x3f / 255 }
local GLOW_A = 0.55

M.SETTING = {
    key = "nameplates.comboPips", default = true, label = "Combo points on the target",
    tip = "Five pips under the target's nameplate, pink as they build and gold at five. A Druid sees them in Cat Form.",
}
Config.RegisterDefault(M.SETTING.key, M.SETTING.default)

local host, pips
local seatedOn            -- the plate root the pips hang from
local shownPx             -- the pixel size the pips were last sized for

local function Applies()
    if CLASS == "ROGUE" then return true end
    local ok, pt = pcall(UnitPowerType, "player")
    return ok and not FS.IsSecret(pt) and pt == ENERGY_POWER
end
M.Applies = Applies

-- A pip bar: the ENGINE shows it once the count reaches hi (lo to hi, fed the raw count).
local function Bar(parent, level, tex, lo, hi, c, a, add)
    local b = CreateFrame("StatusBar", nil, parent)
    b:SetFrameLevel(parent:GetFrameLevel() + level)
    b:SetStatusBarTexture(tex)
    b:SetStatusBarColor(c[1], c[2], c[3], a)
    local t = b.GetStatusBarTexture and b:GetStatusBarTexture()
    if t then
        if add and t.SetBlendMode then t:SetBlendMode("ADD") end
        if t.SetSnapToPixelGrid then t:SetSnapToPixelGrid(true); t:SetTexelSnappingBias(0) end
    end
    b:SetMinMaxValues(lo, hi)
    b:SetValue(lo)
    return b
end

-- Each pip, back to front: its glow (ADD, twice its size, pink, gold at five), the resting diamond, the lit diamond (pink), the
-- gold one over it at five.
local function Build()
    if host then return end
    host = CreateFrame("Frame", nil, UIParent)
    if host.SetFrameStrata then pcall(host.SetFrameStrata, host, STRATA) end
    if host.SetIgnoreParentAlpha then host:SetIgnoreParentAlpha(true) end
    host:Hide()
    pips = {}
    for i = 1, COUNT do
        local p = CreateFrame("Frame", nil, host)
        p:SetFrameLevel(host:GetFrameLevel() + 2)
        p.glow = Bar(host, 1, GLOW, i - 1, i, PINK, GLOW_A, true)
        p.goldGlow = Bar(host, 1, GLOW, COUNT - 1, COUNT, GOLD, GLOW_A, true)
        p.rest = p:CreateTexture(nil, "BACKGROUND")
        p.rest:SetAllPoints(p)
        p.rest:SetTexture(REST, "CLAMP", "CLAMP", "NEAREST")
        if p.rest.SetSnapToPixelGrid then p.rest:SetSnapToPixelGrid(true); p.rest:SetTexelSnappingBias(0) end
        p.fill = Bar(p, 1, LIT, i - 1, i, PINK, 1)
        p.gold = Bar(p, 2, LIT, COUNT - 1, COUNT, GOLD, 1)
        pips[i] = p
    end
end

-- Pixel size of one physical px in the plate's units, or nil.
local function PixelSize(root)
    local factor = PixelUtil and PixelUtil.GetPixelToUIUnitFactor and PixelUtil.GetPixelToUIUnitFactor()
    local ok, eff = pcall(host.GetEffectiveScale, host)
    if ok and type(factor) == "number" and type(eff) == "number" and not FS.IsSecret(factor) and not FS.IsSecret(eff)
        and factor > 0 and eff > 0 then
        return factor / eff
    end
    return nil
end

local function CastHeight()
    local value = Config.Get(CAST_H_KEY)
    if type(value) ~= "number" or FS.IsSecret(value) or value ~= value then return CAST_H_DEFAULT end
    return math.max(0, math.min(CAST_H_MAX, math.floor(value + 0.5)))
end

local function Size()
    local px = PixelSize(seatedOn) or 1
    if px == shownPx then return end
    shownPx = px
    local pip, gap = PIP * px, GAP * px
    host:SetSize((COUNT * PIP + (COUNT - 1) * GAP) * px, pip)
    host:ClearAllPoints()
    local pad = FS.Theme and tonumber(FS.Theme.SLICE_GLOW_PAD) or 0
    host:SetPoint("TOP", seatedOn, "BOTTOM", 0, -(math.max(CAST_GAP, pad) + CastHeight() + BELOW))
    for i, p in ipairs(pips) do
        p:SetSize(pip, pip)
        p:ClearAllPoints()
        p:SetPoint("LEFT", host, "LEFT", (i - 1) * (pip + gap), 0)
        for _, b in ipairs({ p.fill, p.gold }) do b:SetAllPoints(p) end
        for _, b in ipairs({ p.glow, p.goldGlow }) do
            b:SetSize(2 * pip, 2 * pip)
            b:ClearAllPoints()
            b:SetPoint("CENTER", p, "CENTER")
        end
    end
end

local function Feed()
    if not (host and host:IsShown()) then return end
    local ok, v = pcall(UnitPower, "player", COMBO_POWER)
    if not ok or (v == nil and not FS.IsSecret(v)) then v = 0 end
    for _, p in ipairs(pips) do
        for _, b in ipairs({ p.glow, p.goldGlow, p.fill, p.gold }) do pcall(b.SetValue, b, v) end
    end
end

local function Hide()
    if host then
        host:Hide()
        host:SetScript("OnUpdate", nil)
    end
    seatedOn = nil
end

local function Hostile()
    local ok, can = pcall(UnitCanAttack, "player", "target")
    if not ok or FS.IsSecret(can) or can ~= true then return false end
    local okD, dead = pcall(UnitIsDead, "target")
    return okD and not FS.IsSecret(dead) and dead ~= true
end

local function TargetRoot()
    for unit, root in pairs(FS.framesByUnit) do
        local ok, is = pcall(UnitIsUnit, unit, "target")
        if ok and not FS.IsSecret(is) and is == true then return root end
    end
    return nil
end

-- Seats the pips on the target's plate, or hides them.
function M.Refresh()
    if Config.Get(M.SETTING.key) == false or not Applies() or not UnitExists("target") or not Hostile() then return Hide() end
    local root = TargetRoot()
    if not root then return Hide() end
    Build()
    if seatedOn ~= root then
        seatedOn = root
        shownPx = nil
        host:SetParent(root)
        if host.SetFrameStrata then pcall(host.SetFrameStrata, host, STRATA) end
    end
    Size()
    host:Show()
    host:SetScript("OnUpdate", Size)
    Feed()
end

local ev = CreateFrame("Frame")
for _, e in ipairs({ "PLAYER_TARGET_CHANGED", "NAME_PLATE_UNIT_ADDED", "NAME_PLATE_UNIT_REMOVED", "PLAYER_ENTERING_WORLD",
    "UPDATE_SHAPESHIFT_FORM" }) do
    pcall(ev.RegisterEvent, ev, e)
end
if ev.RegisterUnitEvent then
    pcall(ev.RegisterUnitEvent, ev, "UNIT_POWER_UPDATE", "player")
    pcall(ev.RegisterUnitEvent, ev, "UNIT_POWER_FREQUENT", "player")
    pcall(ev.RegisterUnitEvent, ev, "UNIT_DISPLAYPOWER", "player")
    pcall(ev.RegisterUnitEvent, ev, "UNIT_FLAGS", "target")
end

local pending = false
local function Later()
    if pending then return end
    pending = true
    local function Run()
        pending = false
        M.Refresh()
    end
    if C_Timer and C_Timer.After then C_Timer.After(0, Run) else Run() end
end

ev:SetScript("OnEvent", function(_, event, unit)
    if event == "UNIT_POWER_UPDATE" or event == "UNIT_POWER_FREQUENT" then
        if unit == "player" then Feed() end
    elseif event == "NAME_PLATE_UNIT_ADDED" or event == "NAME_PLATE_UNIT_REMOVED" or event == "UNIT_FLAGS" then
        -- Nameplates.lua fills FS.framesByUnit from the same events; run after it, next frame.
        Later()
    else
        M.Refresh()
    end
end)

Config.OnChange(M.SETTING.key, M.Refresh)
-- A new cast bar height moves the row at once: sized again for the plate it hangs from.
Config.OnChange(CAST_H_KEY, function()
    shownPx = nil
    if host and host:IsShown() then Size() end
end)
