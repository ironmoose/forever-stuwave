-- Forever STUwave: combo points on the target's nameplate
--
-- Five pips in a row off the right edge of the current target's STUwave plate (Nameplates.lua), for a Rogue, and for a Druid
-- while its power is energy (Cat Form). A pip lights pink when the count reaches it; at five every pip turns gold, the same
-- "ready" cue as the Rogue dagger fan.
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
local PIP, GAP, LEFT_GAP = 9, 2, 4        -- physical px: a pip, between pips, from the plate's right edge
local STRATA = "HIGH"

local function Hex(h)
    return tonumber(h:sub(2, 3), 16) / 255, tonumber(h:sub(4, 5), 16) / 255, tonumber(h:sub(6, 7), 16) / 255
end
local COL = {
    rim = { Hex("#120822") }, track = { Hex("#2a1d48") }, line = { Hex("#6b4fa8") },
    lit = { Hex("#ff4dd8") }, gold = { Hex("#ffd23f") },
}

M.SETTING = {
    key = "nameplates.comboPips", default = true, label = "Combo points on the target",
    tip = "Five pips beside the target's nameplate, pink as they build and gold at five. A Druid sees them in Cat Form.",
}
Config.RegisterDefault(M.SETTING.key, M.SETTING.default)

local FLAT = "Interface\\Buttons\\WHITE8X8"

local host, pips
local seatedOn            -- the plate root the pips hang from
local shownPx             -- the pixel size the pips were last sized for

local function Applies()
    if CLASS == "ROGUE" then return true end
    local ok, pt = pcall(UnitPowerType, "player")
    return ok and not FS.IsSecret(pt) and pt == ENERGY_POWER
end
M.Applies = Applies

local function Bar(parent, level, lo, hi, c)
    local b = CreateFrame("StatusBar", nil, parent)
    b:SetFrameLevel(parent:GetFrameLevel() + level)
    b:SetStatusBarTexture(FLAT)
    b:SetStatusBarColor(c[1], c[2], c[3], 1)
    b:SetMinMaxValues(lo, hi)
    b:SetValue(lo)
    return b
end

local function Build()
    if host then return end
    host = CreateFrame("Frame", nil, UIParent)
    if host.SetFrameStrata then pcall(host.SetFrameStrata, host, STRATA) end
    if host.SetIgnoreParentAlpha then host:SetIgnoreParentAlpha(true) end
    host:Hide()
    pips = {}
    for i = 1, COUNT do
        local p = CreateFrame("Frame", nil, host)
        p:SetFrameLevel(host:GetFrameLevel() + 1)
        p.rim = p:CreateTexture(nil, "BACKGROUND", nil, 0)
        p.rim:SetAllPoints(p)
        p.rim:SetColorTexture(COL.rim[1], COL.rim[2], COL.rim[3], 1)
        p.line = p:CreateTexture(nil, "BACKGROUND", nil, 1)
        p.line:SetColorTexture(COL.line[1], COL.line[2], COL.line[3], 1)
        p.track = p:CreateTexture(nil, "BACKGROUND", nil, 2)
        p.track:SetColorTexture(COL.track[1], COL.track[2], COL.track[3], 1)
        p.fill = Bar(p, 1, i - 1, i, COL.lit)
        p.gold = Bar(p, 2, COUNT - 1, COUNT, COL.gold)
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

local function Size()
    local px = PixelSize(seatedOn) or 1
    if px == shownPx then return end
    shownPx = px
    local pip, gap = PIP * px, GAP * px
    host:SetSize((COUNT * PIP + (COUNT - 1) * GAP) * px, pip)
    host:ClearAllPoints()
    host:SetPoint("LEFT", seatedOn, "RIGHT", LEFT_GAP * px, 0)
    for i, p in ipairs(pips) do
        p:SetSize(pip, pip)
        p:ClearAllPoints()
        p:SetPoint("LEFT", host, "LEFT", (i - 1) * (pip + gap), 0)
        p.line:ClearAllPoints()
        p.line:SetPoint("TOPLEFT", p, "TOPLEFT", px, -px)
        p.line:SetPoint("BOTTOMRIGHT", p, "BOTTOMRIGHT", -px, px)
        p.track:ClearAllPoints()
        p.track:SetPoint("TOPLEFT", p, "TOPLEFT", 2 * px, -2 * px)
        p.track:SetPoint("BOTTOMRIGHT", p, "BOTTOMRIGHT", -2 * px, 2 * px)
        for _, b in ipairs({ p.fill, p.gold }) do
            b:ClearAllPoints()
            b:SetPoint("TOPLEFT", p.track, "TOPLEFT")
            b:SetPoint("BOTTOMRIGHT", p.track, "BOTTOMRIGHT")
        end
    end
end

local function Feed()
    if not (host and host:IsShown()) then return end
    local ok, v = pcall(UnitPower, "player", COMBO_POWER)
    if not ok or (v == nil and not FS.IsSecret(v)) then v = 0 end
    for _, p in ipairs(pips) do
        pcall(p.fill.SetValue, p.fill, v)
        pcall(p.gold.SetValue, p.gold, v)
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
