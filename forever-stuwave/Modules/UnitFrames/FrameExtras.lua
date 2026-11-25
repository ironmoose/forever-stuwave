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

-------------------------------------------------------------------------------
-- Group frames (party rows and raid cells): corner markers and aggro
-------------------------------------------------------------------------------
-- Everything below is drawn on plain regions of the row's non-secure child, so a style change applies in combat.
-- Aura reads are refused under combat lockdown on this client: the callers read only while FS.AurasReadable(), so
-- the markers hold what they showed when the fight began and refresh when it ends (PLAYER_REGEN_ENABLED).

local MARKER_MAX = 8
Extras.MARKER_MAX = MARKER_MAX
local MISSING_BUFF = { 1, 0.231, 0.306, 0.55 }   -- #ff3b4e at .55: a buff they are missing
Extras.DEBUFF_TYPES = { "Magic", "Curse", "Poison", "Disease" }

-- The heal over time spells a class casts, by aura name, each with its own marker colour (the aura is read from a
-- HELPFUL list and kept only when it is the player's own).
Extras.HOTS = {
    PRIEST = { { "Renew", 0.224, 1, 0.078 } },
    DRUID = { { "Rejuvenation", 1, 0.180, 0.592 }, { "Regrowth", 0.133, 0.878, 1 }, { "Lifebloom", 1, 0.7137, 0.2824 } },
    SHAMAN = { { "Earth Shield", 0.133, 0.878, 1 } },
}

local function PlayerClassToken()
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not IsSecret(token) and type(token) == "string" then return token end
    return nil
end

local function Shared() return FS.PartyFrames and FS.PartyFrames.shared end

local function Push(out, n, r, g, b, a, kind)
    n = n + 1
    local e = out[n]
    if not e then e = {}; out[n] = e end
    e[1], e[2], e[3], e[4], e.kind = r, g, b, a, kind
    return n
end

local function NoReport() end

-- Fills `out` with the markers a unit shows (entries { r, g, b, a, kind }) and returns how many. `harmful` is the
-- unit's HARMFUL aura list the caller already scanned (aura.dispelType), or nil. A secret name, type or caster is
-- never compared; it just draws nothing.
function Extras.ReadMarkers(out, unit, key, harmful)
    local n = 0
    local shared = Shared()
    if On(key, "mkHot") then
        local hots = Extras.HOTS[PlayerClassToken() or ""]
        local read = FS.FrameHelpers and FS.FrameHelpers.ReadAuraSlot
        if hots and read then
            local seen = {}
            for slot = 1, 32 do
                local aura = read(unit, slot, "HELPFUL|PLAYER", NoReport)
                if not aura then break end
                local name, caster = aura.name, aura.caster
                if not IsSecret(name) and type(name) == "string" and not seen[name]
                    and (caster == nil or IsSecret(caster) or caster == "player") then
                    for _, hot in ipairs(hots) do
                        if hot[1] == name then
                            seen[name] = true
                            if n < MARKER_MAX then n = Push(out, n, hot[2], hot[3], hot[4], 1, "hot") end
                        end
                    end
                end
            end
        end
    end
    if key == "raid" and On(key, "mkDebuff") and harmful and shared then
        local mine = Style.Get(key, "mkDebuffWho") ~= "all"
        local set = shared.DISPELS and shared.DISPELS.Set() or {}
        local colors = Theme and Theme.DISPEL_COLORS or {}
        for _, kind in ipairs(Extras.DEBUFF_TYPES) do
            if On(key, "mk" .. kind) and (not mine or set[kind]) then
                for _, aura in ipairs(harmful) do
                    local t = aura.dispelType
                    if not IsSecret(t) and t == kind then
                        local c = colors[kind] or { 1, 1, 1, 1 }
                        if n < MARKER_MAX then n = Push(out, n, c[1], c[2], c[3], 1, "deb " .. kind:lower()) end
                        break
                    end
                end
            end
        end
    end
    if key == "raid" and On(key, "mkBuff") and shared and shared.EvaluatePartyBuffs then
        local list, count = shared.EvaluatePartyBuffs(unit)
        for i = 1, count do
            if list[i].reason == "missing" and n < MARKER_MAX then
                n = Push(out, n, MISSING_BUFF[1], MISSING_BUFF[2], MISSING_BUFF[3], MISSING_BUFF[4], "buff")
            end
        end
    end
    for i = n + 1, #out do out[i] = nil end
    return n
end

-- A row of squares in one corner of `parent`, built once.
function Extras.BuildMarkers(parent, level, anchor)
    local host = CreateFrame("Frame", nil, parent)
    host:SetAllPoints(anchor or parent)
    if level then host:SetFrameLevel(level) end
    local m = { host = host, tex = {}, list = {}, shown = 0 }
    for i = 1, MARKER_MAX do
        local t = host:CreateTexture(nil, "OVERLAY")
        t:SetColorTexture(1, 1, 1, 1)
        t:Hide()
        m.tex[i] = t
    end
    return m
end

local CORNER_VERTICAL = { topleft = "TOP", topright = "TOP", bottomleft = "BOTTOM", bottomright = "BOTTOM" }
local CORNER_SIDE = { topleft = "LEFT", topright = "RIGHT", bottomleft = "LEFT", bottomright = "RIGHT" }

-- Sizes and seats the squares for the frame's marker size and corner.
function Extras.SeatMarkers(m, key)
    local size, corner = Style.Number(key, "mkSize"), Style.Get(key, "mkPos")
    if not CORNER_SIDE[corner] then corner = Style.Default(key, "mkPos") end
    if m.seatSize == size and m.seatCorner == corner then return end
    m.seatSize, m.seatCorner = size, corner
    local v, s = CORNER_VERTICAL[corner], CORNER_SIDE[corner]
    local sign = s == "RIGHT" and -1 or 1
    local y = v == "TOP" and -2 or 2
    for i, t in ipairs(m.tex) do
        t:SetSize(size, size)
        t:ClearAllPoints()
        t:SetPoint(v .. s, m.host, v .. s, sign * (3 + (i - 1) * (size + 1)), y)
    end
end

-- Paints `list[1..n]` (plain colours): the squares beyond n hide.
function Extras.PaintMarkers(m, key, list, n)
    Extras.SeatMarkers(m, key)
    for i, t in ipairs(m.tex) do
        local e = i <= n and list[i] or nil
        if e then
            t:SetColorTexture(e[1], e[2], e[3], e[4])
            t:Show()
        else
            t:Hide()
        end
    end
    m.shown = n
end

-- True when the switches say a held marker of this kind still shows.
local function KindOn(key, kind)
    if kind == "hot" then return On(key, "mkHot") end
    if kind == "buff" then return On(key, "mkBuff") end
    local type_ = kind:match("^deb (%a+)$")
    if type_ then return On(key, "mkDebuff") and On(key, "mk" .. type_:sub(1, 1):upper() .. type_:sub(2)) end
    return true
end

-- A switch turned off in a fight takes its held markers out; nothing is read.
function Extras.Rehold(m, key)
    local n = 0
    for i = 1, m.shown do
        local e = m.list[i]
        if e and KindOn(key, e.kind) then
            n = n + 1
            if n ~= i then
                local keep = m.list[n]
                m.list[n] = e
                m.list[i] = keep
            end
        end
    end
    m.shown = n
end

-- Reads a unit's markers and paints them; false when the read is refused (the old squares stay as they were).
function Extras.UpdateMarkers(m, unit, key, harmful)
    if not m then return false end
    if not (FS.AurasReadable and FS.AurasReadable()) then return false end
    local n = Extras.ReadMarkers(m.list, unit, key, harmful)
    Extras.PaintMarkers(m, key, m.list, n)
    return true
end

-- Sample markers for a preview member `i` (1 is the player), through the same switches and colours the live read uses.
function Extras.PreviewList(out, key, i)
    local n = 0
    local shared = Shared()
    if On(key, "mkHot") then
        local hots = Extras.HOTS[PlayerClassToken() or ""] or Extras.HOTS.PRIEST
        if i == 2 or i == 8 or key == "party" then n = Push(out, n, hots[1][2], hots[1][3], hots[1][4], 1, "hot") end
        if i == 2 or key == "party" then
            local h2 = hots[2] or { "", 0.133, 0.878, 1 }
            n = Push(out, n, h2[2], h2[3], h2[4], 1, "hot")
        end
    end
    if key == "raid" and On(key, "mkDebuff") then
        local sample = { [3] = "Magic", [6] = "Curse", [5] = "Poison", [7] = "Disease" }
        local kind = sample[i]
        if kind and On(key, "mk" .. kind) then
            local set = shared and shared.DISPELS and shared.DISPELS.Set() or {}
            if Style.Get(key, "mkDebuffWho") == "all" or set[kind] then
                local c = Theme.DISPEL_COLORS[kind]
                n = Push(out, n, c[1], c[2], c[3], 1, "deb " .. kind:lower())
            end
        end
    end
    if key == "raid" and On(key, "mkBuff") and (i == 4 or i == 7) then
        n = Push(out, n, MISSING_BUFF[1], MISSING_BUFF[2], MISSING_BUFF[3], MISSING_BUFF[4], "buff")
    end
    for k = n + 1, #out do out[k] = nil end
    return n
end

-- A fill whose opacity can change: `build(panel, color)` draws the fill (Theme.AddRoundedFill, AddCutSliceFill ...); the
-- default set is drawn at once, other opacities are drawn the first time they are asked for and then kept, so dragging a
-- slider builds one set per step and never one per frame. Returns { Set = fn(alpha) } (alpha is the fill's own).
function Extras.NewFill(panel, build, color)
    local fill = { sets = {}, shown = nil }
    local function Draw(alpha)
        local list = {}
        local own = rawget(panel, "CreateTexture")
        local create = panel.CreateTexture
        panel.CreateTexture = function(self, ...)
            local t = create(self, ...)
            list[#list + 1] = t
            return t
        end
        local ok, err = pcall(build, panel, { color[1], color[2], color[3], alpha })
        panel.CreateTexture = own
        if not ok then error(err, 0) end
        -- a texture the builder itself hid (a nine slice that did not load) stays hidden
        local kept = {}
        for _, t in ipairs(list) do
            if type(t.IsShown) ~= "function" or t:IsShown() then kept[#kept + 1] = t end
        end
        return kept
    end
    local key0 = math.floor((color[4] or 1) * 1000 + 0.5)
    fill.sets[key0] = Draw(color[4] or 1)
    fill.shown = key0
    fill.base = color[4] or 1
    function fill.Set(alpha)
        alpha = math.max(0, math.min(1, alpha))
        local key = math.floor(alpha * 1000 + 0.5)
        if key == fill.shown then return end
        for _, t in ipairs(fill.sets[fill.shown] or {}) do t:Hide() end
        local set = fill.sets[key]
        if not set then set = Draw(alpha); fill.sets[key] = set end
        for _, t in ipairs(set) do t:Show() end
        fill.shown = key
    end
    return fill
end

-- The aggro ring of a group frame: a skinned cut ring on `ring` (a frame seated on the box or cell by the caller, one
-- level above its edge), pink when a mob is on them, amber when they are close to it, and the share of the mob's threat.
function Extras.BuildGroupAggro(ring, chamfer)
    local a = { ring = ring }
    if Theme and Theme.SkinButton then
        Theme.SkinButton(ring, { chamfer = chamfer, glowAlpha = 0.5, borderColor = PINK })
    end
    ring:Hide()
    a.pct = Text(ring, 8, 1, 1, 1)
    a.pct:Hide()
    return a
end

local function Tone(a, color)
    local skin = a.ring.fsSkin
    if skin and skin.border and skin.border.ring then skin.border.ring:SetVertexColor(color[1], color[2], color[3], 1) end
    if skin and skin.glow then skin.glow:SetVertexColor(color[1], color[2], color[3], 0.5) end
    a.pct:SetTextColor(color[1], color[2], color[3], 1)
end

-- Seats the percent text in the frame's corner and nudges it by the Aggro % offset.
function Extras.SeatGroupAggro(a, key, point, rel, x, y)
    a.pct:ClearAllPoints()
    a.pct:SetPoint(point, a.ring, rel, x + Style.Number(key, "threatX"), y)
end

-- Reads a group member's threat and paints the ring and the percent. Feature detected and secret guarded: a client that
-- hides the numbers draws nothing, and no number is ever compared before IsSecret has said it is plain.
function Extras.UpdateGroupAggro(a, unit, key)
    if not a then return end
    if not On(key, "threat") or type(UnitThreatSituation) ~= "function" then a.ring:Hide(); a.pct:Hide(); return end
    local status
    local ok, s = pcall(UnitThreatSituation, unit)
    if ok and not IsSecret(s) and type(s) == "number" then status = s end
    local pct
    if type(UnitDetailedThreatSituation) == "function" then
        local okd, _, _, scaled = pcall(UnitDetailedThreatSituation, unit, "target")
        if okd and not IsSecret(scaled) and type(scaled) == "number" then pct = scaled end
    end
    if status == nil and pct == nil then a.ring:Hide(); a.pct:Hide(); return end
    if status and status >= 2 then Tone(a, PINK)
    elseif (status == 1) or (pct and pct >= Extras.NEAR) then Tone(a, AMBER)
    else a.ring:Hide(); a.pct:Hide(); return end
    a.ring:Show()
    if On(key, "threatPct") and pct then
        a.pct:SetFormattedText("%d%%", math.floor(pct + 0.5)); a.pct:Show()
    else
        a.pct:Hide()
    end
end

-- A sample ring and percent for the Style tab previews. kind: "pink" (a mob is on them), "amber" (close: only the share
-- shows) or nil (nothing).
function Extras.PreviewGroupAggro(a, key, kind, text)
    if not a then return end
    if kind and On(key, "threat") then
        Tone(a, kind == "pink" and PINK or AMBER)
        a.ring:SetShown(kind == "pink")
        if On(key, "threatPct") then a.pct:SetText(text or "100%"); a.pct:Show() else a.pct:Hide() end
    else
        a.ring:Hide(); a.pct:Hide()
    end
end

-- The step a group frame runs on a threat event or a full refresh: f.groupAggro (the ring), f.groupKey ("party" or "raid"),
-- f.unit. A frame with no ring built (the style module missing) does nothing.
function Extras.UpdateGroupRow(f)
    local a = f.groupAggro
    if not a or not f.groupKey then return end
    Extras.UpdateGroupAggro(a, f.unit, f.groupKey)
end
