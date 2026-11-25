-- Forever STUwave: Frame extras and aggro
-- The pieces a unit frame can wear beyond its bars and data row: elite or rare mark, target of target, combat icon,
-- portrait, cast bar on the frame, PvP flag, group leader crown, and the aggro border and percent. Each is a plain
-- region on the frame's non-secure child, so all of it updates in combat. Settings are bars.<frame>.<suffix>
-- (FrameStyle.lua); a piece with its switch off is never built to show. Every reading goes through FS.IsSecret first.
--
-- Pending the owner's review in game: other units' cast timing (may be secret), threat numbers (read live), and
-- the portrait call on a plain frame.

local _, FS = ...

local Style = FS.FrameStyle
if not Style then return end

local IsSecret = FS.IsSecret or function() return false end
local Extras = {}
FS.FrameExtras = Extras

local Theme = FS.Theme
local PINK = { 1, 0.180, 0.592 }     -- #ff2e97: it has aggro
local AMBER = { 1, 0.7137, 0.2824 }  -- #ffb648: close to the top of the threat list
Extras.PINK, Extras.AMBER = PINK, AMBER
Extras.NEAR = 80                     -- scaled threat at or above this reads as "close"

local FONT = Theme and Theme.FONT_ORBITRON or "Fonts\\FRIZQT__.TTF"
local EDGE = 2

local function On(key, suffix) return Style.Get(key, suffix) == true end

local function Text(parent, size, r, g, b)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    local ok = pcall(fs.SetFont, fs, FONT, size, "")
    if not ok then pcall(fs.SetFont, fs, "Fonts\\FRIZQT__.TTF", size, "") end
    fs:SetTextColor(r or 1, g or 1, b or 1, 1)
    return fs
end

function Extras.Build(f)
    local visual, row = f.visual, f.nameRow
    local x = {}
    f.extras = x

    x.elite = row:CreateTexture(nil, "OVERLAY", nil, 3); x.elite:Hide()
    x.combat = row:CreateTexture(nil, "OVERLAY", nil, 3)
    x.combat:SetTexture("Interface\\CharacterFrame\\UI-StateIcon")
    x.combat:SetTexCoord(0.5, 1, 0, 0.49); x.combat:SetSize(14, 14); x.combat:Hide()
    x.pvp = Text(row, 8, 1, 0.23, 0.31); x.pvp:SetText("PVP"); x.pvp:Hide()
    x.leader = row:CreateTexture(nil, "OVERLAY", nil, 3)
    x.leader:SetTexture("Interface\\GroupFrame\\UI-Group-LeaderIcon"); x.leader:SetSize(14, 14); x.leader:Hide()
    x.portrait = row:CreateTexture(nil, "OVERLAY", nil, 1); x.portrait:Hide()

    x.tot = Text(visual, 10, 0.78, 0.74, 0.86)
    x.tot:SetPoint("TOP", visual, "BOTTOM", 0, -3); x.tot:Hide()

    local cast = CreateFrame("StatusBar", nil, visual)
    cast:SetStatusBarTexture(Theme and Theme.FLAT_TEXTURE or "Interface\\Buttons\\WHITE8X8")
    cast:SetStatusBarColor(AMBER[1], AMBER[2], AMBER[3], 1)
    cast:SetHeight(4)
    cast:SetPoint("TOPLEFT", visual, "BOTTOMLEFT", 6, -3)
    cast:SetPoint("TOPRIGHT", visual, "BOTTOMRIGHT", -6, -3)
    cast:SetMinMaxValues(0, 1); cast:SetValue(0)
    cast.name = Text(cast, 9, 1, 1, 1)
    cast.name:SetPoint("TOPLEFT", cast, "BOTTOMLEFT", 0, -1)
    cast:Hide()
    x.cast = cast

    local threat = CreateFrame("Frame", nil, visual)
    threat:SetAllPoints(visual)
    threat:SetFrameLevel(visual:GetFrameLevel() + 6)
    x.edges = {}
    for i, anchor in ipairs({ "TOP", "BOTTOM", "LEFT", "RIGHT" }) do
        local t = threat:CreateTexture(nil, "OVERLAY")
        t:SetColorTexture(1, 1, 1, 1)
        if anchor == "TOP" or anchor == "BOTTOM" then
            t:SetPoint(anchor .. "LEFT", threat, anchor .. "LEFT"); t:SetPoint(anchor .. "RIGHT", threat, anchor .. "RIGHT")
            t:SetHeight(EDGE)
        else
            t:SetPoint("TOP" .. anchor, threat, "TOP" .. anchor); t:SetPoint("BOTTOM" .. anchor, threat, "BOTTOM" .. anchor)
            t:SetWidth(EDGE)
        end
        x.edges[i] = t
    end
    threat:Hide()
    x.threat = threat
    x.pct = Text(threat, 10, 1, 1, 1)
    x.pct:Hide()
    return x
end

local function Tint(x, color)
    for _, e in ipairs(x.edges) do e:SetVertexColor(color[1], color[2], color[3], 1) end
    x.pct:SetTextColor(color[1], color[2], color[3], 1)
end

-- Places the small marks on the name row's far end (opposite the class icon) in a chain, and the percent in the corner.
function Extras.Seat(f)
    local x, key = f.extras, f.styleKey
    if not x then return end
    local badge, row = f.levelBadge, f.nameRow
    local mirrored = f.mirrored
    local prev, gap = nil, 4
    local function Place(piece, w)
        piece:ClearAllPoints()
        if not prev then
            if mirrored then
                if Style.Get(key, "level") then piece:SetPoint("LEFT", badge, "RIGHT", gap, 0) else piece:SetPoint("LEFT", row, "LEFT", 0, 0) end
            else
                if Style.Get(key, "level") then piece:SetPoint("RIGHT", badge, "LEFT", -gap, 0) else piece:SetPoint("RIGHT", row, "RIGHT", 0, 0) end
            end
        elseif mirrored then
            piece:SetPoint("LEFT", prev, "RIGHT", gap, 0)
        else
            piece:SetPoint("RIGHT", prev, "LEFT", -gap, 0)
        end
        prev = piece
    end
    for _, name in ipairs({ "combat", "pvp", "leader" }) do
        if On(key, name) then Place(x[name]) end
    end

    local icon = f.classIcon
    x.portrait:ClearAllPoints()
    x.portrait:SetPoint("TOPLEFT", icon, "TOPLEFT")
    x.portrait:SetPoint("BOTTOMRIGHT", icon, "BOTTOMRIGHT")
    x.elite:ClearAllPoints()
    x.elite:SetPoint("CENTER", badge, "TOPRIGHT", 0, 0)

    x.pct:ClearAllPoints()
    x.pct:SetPoint("BOTTOMRIGHT", f.visual, "TOPRIGHT", Style.Number(key, "threatX"), 2)
end

local function Classification(unit)
    local ok, class = pcall(UnitClassification, unit)
    if not ok or IsSecret(class) or type(class) ~= "string" then return nil end
    local tags = FS.GunsightTags and FS.GunsightTags.C and FS.GunsightTags.C.ICONS
    return tags and tags[class] and class or nil
end

local function PaintElite(x, kind)
    local tags = FS.GunsightTags and FS.GunsightTags.C and FS.GunsightTags.C.ICONS
    local spec = kind and tags and tags[kind]
    if not (spec and Theme and Theme[spec.tex]) then x.elite:Hide(); return end
    x.elite:SetTexture(Theme[spec.tex])
    local tint = spec.tint and Theme[spec.tint] or { 1, 1, 1, 1 }
    x.elite:SetVertexColor(tint[1], tint[2], tint[3], tint[4] or 1)
    x.elite:SetSize(spec.size, spec.size)
    x.elite:Show()
end

-- What the live unit shows for the switches that are on.
local function CastNow(f, x)
    local unit = f.unit
    local on = false
    if type(UnitCastingInfo) == "function" then
        local ok, name, _, _, startMS, endMS = pcall(UnitCastingInfo, unit)
        if ok and name then
            on = true
            x.cast.name:SetText(name)
            if not IsSecret(startMS) and not IsSecret(endMS) and type(startMS) == "number" and type(endMS) == "number" then
                x.cast:SetMinMaxValues(startMS, endMS)
                x.cast:SetValue(GetTime() * 1000)
                x.cast.timed = true
            else
                x.cast:SetMinMaxValues(0, 1); x.cast:SetValue(1)   -- the timing is hidden: a full bar with the spell name
                x.cast.timed = false
            end
        end
    end
    x.cast:SetShown(on)
    return on
end

local function ThreatNow(f, x, key)
    local unit = f.unit
    local status, pct = nil, nil
    if key == "player" then
        if type(UnitThreatSituation) == "function" then
            local ok, s = pcall(UnitThreatSituation, "player")
            if ok and not IsSecret(s) and type(s) == "number" then status = s end
        end
        if status and status >= 2 then Tint(x, PINK); x.threat:Show() else x.threat:Hide() end
        x.pct:Hide()
        return
    end
    if type(UnitDetailedThreatSituation) == "function" and UnitExists(unit) then
        local ok, tanking, s, scaled = pcall(UnitDetailedThreatSituation, "player", unit)
        if ok and not IsSecret(s) and type(s) == "number" then
            status = s
            if not IsSecret(scaled) and type(scaled) == "number" then pct = scaled end
        end
    end
    if status == nil then x.threat:Hide(); return end
    if status >= 3 then Tint(x, PINK)
    elseif pct and pct >= Extras.NEAR then Tint(x, AMBER)
    else x.threat:Hide(); return end
    x.threat:Show()
    if On(key, "threatPct") and pct then
        x.pct:SetFormattedText("%d%%", math.floor(pct + 0.5)); x.pct:Show()
    else
        x.pct:Hide()
    end
end

function Extras.Update(f)
    local x, key = f.extras, f.styleKey
    if not x or f.preview then return end
    local unit = f.unit
    if On(key, "elite") then PaintElite(x, Classification(unit)) else x.elite:Hide() end
    if On(key, "combat") then x.combat:SetShown(type(UnitAffectingCombat) == "function" and UnitAffectingCombat(unit) == true) else x.combat:Hide() end
    if On(key, "pvp") then
        local flagged = type(UnitIsPVP) == "function" and UnitIsPVP(unit)
        x.pvp:SetShown(not IsSecret(flagged) and flagged == true)
    else x.pvp:Hide() end
    if On(key, "leader") then
        local lead = type(UnitIsGroupLeader) == "function" and UnitIsGroupLeader(unit)
        x.leader:SetShown(not IsSecret(lead) and lead == true)
    else x.leader:Hide() end
    if On(key, "portrait") then
        if type(SetPortraitTexture) == "function" then pcall(SetPortraitTexture, x.portrait, unit) end
        x.portrait:Show(); f.classIcon:Hide(); if f.classGlow then f.classGlow:Hide() end
    else x.portrait:Hide() end
    if On(key, "tot") and UnitExists(unit .. "target") then
        local ok, name = pcall(UnitName, unit .. "target")
        if ok and name then x.tot:SetText("> " .. (IsSecret(name) and "?" or name)); x.tot:Show() else x.tot:Hide() end
    else x.tot:Hide() end
    if On(key, "cast") then CastNow(f, x) else x.cast:Hide() end
    if On(key, "threat") then ThreatNow(f, x, key) else x.threat:Hide() end
end

-- Per-frame events: casts, threat, combat, flags. Run in combat; the pieces are plain regions.
function Extras.Wire(f)
    local x = f.extras
    if not x then return end
    local ev = CreateFrame("Frame")
    local unit = f.unit
    for _, e in ipairs({
        "UNIT_SPELLCAST_START", "UNIT_SPELLCAST_STOP", "UNIT_SPELLCAST_FAILED", "UNIT_SPELLCAST_INTERRUPTED",
        "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_CHANNEL_STOP", "UNIT_THREAT_LIST_UPDATE",
        "UNIT_THREAT_SITUATION_UPDATE", "UNIT_TARGET", "UNIT_PORTRAIT_UPDATE", "UNIT_FLAGS",
    }) do pcall(ev.RegisterUnitEvent, ev, e, unit) end
    for _, e in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "PARTY_LEADER_CHANGED", "PLAYER_TARGET_CHANGED", "PLAYER_FOCUS_CHANGED" }) do
        pcall(ev.RegisterEvent, ev, e)
    end
    ev:SetScript("OnUpdate", nil)
    ev:SetScript("OnEvent", function() if UnitExists(unit) then Extras.Update(f) end end)
    -- a timed cast bar advances on its own clock while it shows
    x.cast:SetScript("OnUpdate", function(bar)
        if bar.timed then bar:SetValue(GetTime() * 1000) end
    end)
    f.extrasEvents = ev
end

-- Sample state for the Style tab: every switched-on piece drawn as it would look.
function Extras.Preview(f)
    local x, key = f.extras, f.styleKey
    if not x then return end
    PaintElite(x, On(key, "elite") and "elite" or nil)
    x.combat:SetShown(On(key, "combat"))
    x.pvp:SetShown(On(key, "pvp"))
    x.leader:SetShown(On(key, "leader"))
    if On(key, "portrait") then
        x.portrait:SetTexture("Interface\\CharacterFrame\\TemporaryPortrait"); x.portrait:Show()
        f.classIcon:Hide(); if f.classGlow then f.classGlow:Hide() end
    else x.portrait:Hide() end
    x.tot:SetText("> Stu Shockalaka"); x.tot:SetShown(On(key, "tot"))
    x.cast.name:SetText("Lightning Bolt"); x.cast:SetMinMaxValues(0, 1); x.cast:SetValue(0.6); x.cast.timed = false
    x.cast:SetShown(On(key, "cast"))
    if On(key, "threat") then
        Tint(x, key == "player" and PINK or AMBER)
        x.threat:Show()
        if key ~= "player" and On(key, "threatPct") then x.pct:SetText("87%"); x.pct:Show() else x.pct:Hide() end
    else x.threat:Hide() end
end
