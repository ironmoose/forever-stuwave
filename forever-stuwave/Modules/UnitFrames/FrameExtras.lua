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
    x.tot:SetText("> Doc Brown"); x.tot:SetShown(On(key, "tot"))
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

-- Paints `list[1..n]` (plain colours): the squares beyond n hide. While the engine layer covers this frame's squares
-- (a fight, the markers container armed: `m.eng`), the held heal over time and debuff squares stay out (the engine draws
-- those) and what is left (the missing buff square) sits after the engine's lanes.
function Extras.PaintMarkers(m, key, list, n)
    Extras.SeatMarkers(m, key)
    local engine = Extras.Engine
    local covered = m.eng and engine and engine.Covers(m.eng, "markers")
    local offset = covered and m.eng.parts.markers.lanes or 0
    for _, t in ipairs(m.tex) do t:Hide() end
    local used = 0
    for i = 1, n do
        local e = list[i]
        if e and not (covered and (e.kind == "hot" or e.kind:sub(1, 3) == "deb")) then
            used = used + 1
            local t = m.tex[used + offset]
            if t then
                t:SetColorTexture(e[1], e[2], e[3], e[4])
                t:Show()
            end
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
        if i == 2 or i == 9 or key == "party" then n = Push(out, n, hots[1][2], hots[1][3], hots[1][4], 1, "hot") end
        if i == 2 or key == "party" then
            local h2 = hots[2] or { "", 0.133, 0.878, 1 }
            n = Push(out, n, h2[2], h2[3], h2[4], 1, "hot")
        end
    end
    if key == "raid" and On(key, "mkDebuff") then
        local sample = { [6] = "Magic", [7] = "Curse", [8] = "Poison", [10] = "Disease" }
        local kind = sample[i]
        if kind and On(key, "mk" .. kind) then
            local set = shared and shared.DISPELS and shared.DISPELS.Set() or {}
            if Style.Get(key, "mkDebuffWho") == "all" or set[kind] then
                local c = Theme.DISPEL_COLORS[kind]
                n = Push(out, n, c[1], c[2], c[3], 1, "deb " .. kind:lower())
            end
        end
    end
    if key == "raid" and On(key, "mkBuff") and (i == 5 or i == 7) then
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

-------------------------------------------------------------------------------
-- Engine drawn group auras (the in combat layer)
-------------------------------------------------------------------------------
-- In combat lockdown no addon aura read works (refused or secret), so the squares, the dispel edge and the party tray
-- above can only HOLD what they showed. The engine can draw them: an AuraContainer (CustomAuraContainerTemplate, the
-- recipe the nameplates and the player buffs use) reads the unit's auras itself and draws buttons, and no aura data
-- ever enters Lua. Per group frame (party row, raid cell) there are up to three containers:
--   markers  one SLOT per wanted kind: my heal over time (candidateFilters.includeSpellIDs) and each dispel type
--            (includeDispelTypes). A slot draws one flat square in its kind's colour; the engine shows it exactly
--            while such an aura is on the unit. Squares sit in fixed lanes (hots first, then the types), so a lane
--            stays empty while its aura is absent: presence is secret, there is no compacting.
--   edge     one SLOT per dispel type I can remove: four strips round the frame in the type's colour.
--   tray     (party) one GROUP per dispel type I can remove: the aura's own icon in a ring of the type's colour,
--            flowed by the engine out from the tray origin.
-- Colours are baked when a button is built (the engine runs initializeFrame once), and every per feature choice is made
-- with the container's alpha and the slot's candidate filters, never by writing to an engine button's regions.
--
-- MODE: the engine layer is the IN COMBAT layer. Out of combat the Lua scans above draw as they always did (plain
-- reads, always right) and the containers sit at alpha 0; REGEN_DISABLED flips to the engine, REGEN_ENABLED back. So a
-- client that refuses any call here only loses the in combat layer: today's held-state behaviour is the fallback.
-- Everything is feature detected and pcall'd; containers are built, enabled and shown OUT of combat only (a group frame
-- that first exists in a fight gets its containers when it ends). UNVERIFIED in game: see debug/lanes-2026-11-25/g.md.

local Engine = {}
Extras.Engine = Engine
Engine.TEMPLATE = "CustomAuraContainerTemplate"
Engine.list = {}
Engine.fight = false
Engine.BUILD_TRIES = 3
local EDGE_PX = 2
local TRAY_GAP = 3
local TRAY_CAP_MAX = 5
local SENTINEL_TYPE, SENTINEL_ID = "FS_none", 0

-- Rank ids of the heal over time spells (an aura reports the rank id that was cast). The id the NAME resolves to
-- today is added at build time, which covers ids this list lacks.
Engine.HOT_RANKS = {
    Renew = { 139, 6074, 6075, 6076, 6077, 6078, 10927, 10928, 10929, 25315, 25221, 25222 },
    Rejuvenation = { 774, 1058, 1430, 2090, 2091, 3627, 8910, 9839, 9840, 9841, 25299, 26981, 26982 },
    Regrowth = { 8936, 8938, 8939, 8940, 8941, 9750, 9856, 9857, 9858, 26980 },
    Lifebloom = { 33763 },
    ["Earth Shield"] = { 974, 32593, 32594 },
}

local function Quiet(obj, method, ...)
    if type(obj) ~= "table" or type(obj[method]) ~= "function" then return false end
    return (pcall(obj[method], obj, ...))
end

-- InCombatLockdown, fail closed: a throwing check reads as "in combat".
local function Locked()
    if type(InCombatLockdown) ~= "function" then return true end
    local ok, v = pcall(InCombatLockdown)
    return not ok or v and true or false
end

local degraded = {}
local function Degrade(key, text)
    if degraded[key] then return end   -- LogDegradeOnce does not dedupe: this file latches its own
    degraded[key] = true
    if FS.LogDegradeOnce then pcall(FS.LogDegradeOnce, key, "|cffff4488Forever STUwave|r: " .. text) end
end

local supported
-- The client can build the container: the template exists and the option enums are there. Cached once true or false.
function Engine.Supported()
    if supported == nil then
        supported = false
        if type(CreateFrame) == "function" and type(_G.AuraContainerSortMethod) == "table"
            and type(_G.AuraContainerSortDirection) == "table" then
            local info = type(C_XMLUtil) == "table" and C_XMLUtil.GetTemplateInfo or nil
            if type(info) == "function" then
                local ok, template = pcall(info, Engine.TEMPLATE)
                supported = ok and template ~= nil and template ~= false
            end
        end
    end
    return supported
end

-- ForeverSTUwaveDB.groupAuras.mode: "engine" (default), "borrow" or "off". "engine" falls to "borrow" when the client has no
-- container template; a unit whose containers cannot be built falls to borrow for that unit (Engine.Ensure). The old
-- `engine = false` still means "off". Read at call time, but the Blizzard frames' events are only kept alive at the sweep,
-- so a change of mode takes a reload.
function Engine.Mode()
    local db = _G.ForeverSTUwaveDB
    local g = type(db) == "table" and db.groupAuras or nil
    local mode = type(g) == "table" and g.mode or nil
    if type(g) == "table" and g.engine == false then return "off" end
    if mode ~= "borrow" and mode ~= "off" then mode = "engine" end
    if mode == "engine" and not Engine.Supported() then return "borrow" end
    return mode
end

function Engine.Enabled() return Engine.Mode() == "engine" end

-- The player chose borrow in the saved mode (a failure to borrow is then worth a message; the automatic fall is quiet).
function Engine.Explicit()
    local db = _G.ForeverSTUwaveDB
    local g = type(db) == "table" and db.groupAuras or nil
    return type(g) == "table" and g.mode == "borrow"
end

local function MineSet()
    local shared = Shared()
    local ok, set = pcall(function() return shared and shared.DISPELS and shared.DISPELS.Set() or {} end)
    return ok and type(set) == "table" and set or {}
end

local function RoleOff(key)
    if not (FS.Role and FS.Role.Disabled) then return false end
    local ok, off = pcall(FS.Role.Disabled, key)
    return ok and off == true
end

-- What the switches want right now: { hots = { [name] = true }, debs = { [type] = true }, edge = { [type] = true },
-- tray = { [type] = true } } (a missing table key is off).
function Engine.Wanted(key)
    local w = { hots = {}, debs = {}, edge = {}, tray = {} }
    local mine = MineSet()
    if On(key, "mkHot") then
        for _, hot in ipairs(Extras.HOTS[PlayerClassToken() or ""] or {}) do w.hots[hot[1]] = true end
    end
    if key == "raid" and On(key, "mkDebuff") then
        local onlyMine = Style.Get(key, "mkDebuffWho") ~= "all"
        for _, kind in ipairs(Extras.DEBUFF_TYPES) do
            if On(key, "mk" .. kind) and (not onlyMine or mine[kind]) then w.debs[kind] = true end
        end
    end
    local edgeOn = key == "raid" and On(key, "dispelEdge") or key == "party" and not RoleOff("heal.dispel")
    if edgeOn then for kind in pairs(mine) do w.edge[kind] = true end end
    if key == "party" and On(key, "alerts") and On(key, "alertCleanse") and not RoleOff("heal.dispel") then
        for kind in pairs(mine) do w.tray[kind] = true end
    end
    return w
end

local function HotIds(name)
    local set = {}
    for _, id in ipairs(Engine.HOT_RANKS[name] or {}) do set[id] = true end
    local info = type(C_Spell) == "table" and C_Spell.GetSpellInfo or nil
    if type(info) == "function" then
        local ok, data = pcall(info, name)
        if ok and type(data) == "table" and not IsSecret(data) then
            local id = data.spellID
            if type(id) == "number" and not IsSecret(id) then set[id] = true end
        end
    end
    return set
end

local function SortOptions()
    local method = type(_G.AuraContainerSortMethod) == "table" and _G.AuraContainerSortMethod.Default or nil
    local direction = type(_G.AuraContainerSortDirection) == "table" and _G.AuraContainerSortDirection.Normal or nil
    return method, direction
end

local function NewContainer(host, level)
    local c = CreateFrame("AuraContainer", nil, host, Engine.TEMPLATE)
    c:SetSize(1, 1)
    c:SetFrameLevel(level)
    c:SetPoint("TOPLEFT", host, "TOPLEFT", 0, 0)
    c:SetAlpha(0)
    c:SetEnabled(false)
    c:Hide()
    return c
end

local function Colour(kind)
    local c = Theme and Theme.DISPEL_COLORS and Theme.DISPEL_COLORS[kind]
    return c or { 1, 1, 1, 1 }
end

-- A square: flat colour over the whole slot button, mouse off. Runs before the engine restricts the button.
local function InitSquare(proxy, color)
    return function(button)
        Quiet(button, "SetMouseMotionEnabled", false)
        Quiet(button, "SetMouseClickEnabled", false)
        Quiet(button, "SetHideTooltipInCombat", true)
        pcall(function() button:SetAllPoints(proxy) end)
        pcall(function()
            local t = button:CreateTexture(nil, "OVERLAY")
            t:SetAllPoints(button)
            t:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
        end)
    end
end

-- Four strips round the slot button, mouse off.
local function InitEdge(proxy, color)
    return function(button)
        Quiet(button, "SetMouseMotionEnabled", false)
        Quiet(button, "SetMouseClickEnabled", false)
        Quiet(button, "SetHideTooltipInCombat", true)
        pcall(function() button:SetAllPoints(proxy) end)
        pcall(function()
            for _, side in ipairs({ "TOP", "BOTTOM", "LEFT", "RIGHT" }) do
                local t = button:CreateTexture(nil, "OVERLAY")
                t:SetColorTexture(color[1], color[2], color[3], 1)
                if side == "TOP" or side == "BOTTOM" then
                    t:SetPoint(side .. "LEFT", button, side .. "LEFT"); t:SetPoint(side .. "RIGHT", button, side .. "RIGHT")
                    t:SetHeight(EDGE_PX)
                else
                    t:SetPoint("TOP" .. side, button, "TOP" .. side); t:SetPoint("BOTTOM" .. side, button, "BOTTOM" .. side)
                    t:SetWidth(EDGE_PX)
                end
            end
        end)
    end
end

-- A tray icon: the aura's own icon in a ring of the type's colour. The mouse stays on so the engine's own tooltip works.
local function InitTrayIcon(color, size)
    return function(button)
        Quiet(button, "SetSize", size, size)
        Quiet(button, "SetHideTooltipInCombat", true)
        pcall(function()
            local icon = button:CreateTexture(nil, "ARTWORK")
            icon:SetPoint("TOPLEFT", button, "TOPLEFT", 1, -1)
            icon:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -1, 1)
            icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
            button:SetIcon(icon)
        end)
        pcall(function()
            for _, side in ipairs({ "TOP", "BOTTOM", "LEFT", "RIGHT" }) do
                local t = button:CreateTexture(nil, "OVERLAY")
                t:SetColorTexture(color[1], color[2], color[3], 1)
                if side == "TOP" or side == "BOTTOM" then
                    t:SetPoint(side .. "LEFT", button, side .. "LEFT"); t:SetPoint(side .. "RIGHT", button, side .. "RIGHT")
                    t:SetHeight(1)
                else
                    t:SetPoint("TOP" .. side, button, "TOP" .. side); t:SetPoint("BOTTOM" .. side, button, "BOTTOM" .. side)
                    t:SetWidth(1)
                end
            end
        end)
    end
end

local function Proxy(host, level)
    local p = CreateFrame("Frame", nil, host)
    p:SetFrameLevel(level)
    p:EnableMouse(false)
    p:SetSize(1, 1)
    return p
end

local function Arm(c, unit)
    c:SetUnit(unit)
    c:SetEnabled(true)
    c:Show()
end

-- eng: { host, unit, key, level, parts = { markers, edge, tray }, tries, wanted }.
--   opts.edgeAnchor(proxy)  seats the edge host over the frame's rect (called once)
--   opts.trayOrigin         (party) a plain Frame seated where the first tray icon goes (PartyFrames.SeatTray)
--   opts.onMode(eng)        called when the in combat mode flips, so the owner can hide or show its Lua layer
function Engine.New(host, unit, key, opts)
    if not (host and unit and key) then return nil end
    opts = opts or {}
    local eng = {
        host = host, unit = unit, key = key, level = host:GetFrameLevel() or 1, parts = {}, tries = {},
        edgeAnchor = opts.edgeAnchor, trayOrigin = opts.trayOrigin, onMode = opts.onMode, down = false, owed = false,
    }
    Engine.list[#Engine.list + 1] = eng
    return eng
end

function Engine.Fighting() return Engine.fight end

-- True when a built part exists and was armed.
function Engine.Live(eng, part)
    local p = eng and eng.parts[part]
    return p ~= nil and p.armed == true
end

local function BuildMarkers(eng)
    local host, level = eng.host, eng.level + 8
    local container = NewContainer(host, level)
    local part = { container = container, slots = {}, order = {}, proxies = {}, armed = false }
    local method, direction = SortOptions()
    local function add(slotKey, filter, candidate, color, init)
        local proxy = Proxy(host, level)
        local ok = pcall(container.AddAuraSlot, container, slotKey, filter, {
            initializeFrame = init(proxy, color), candidateFilters = candidate,
            sortMethod = method, sortDirection = direction,
        })
        if not ok then error("AddAuraSlot " .. slotKey, 0) end
        local slot = { key = slotKey, proxy = proxy, candidate = candidate, off = false }
        part.slots[slotKey] = slot
        part.order[#part.order + 1] = slot
        return slot
    end
    for _, hot in ipairs(Extras.HOTS[PlayerClassToken() or ""] or {}) do
        local ids = HotIds(hot[1])
        if next(ids) then
            local s = add("hot:" .. hot[1], "HELPFUL|PLAYER", { includeSpellIDs = ids },
                { hot[2], hot[3], hot[4], 1 }, InitSquare)
            s.kind, s.name, s.ids = "hot", hot[1], ids
        end
    end
    if eng.key == "raid" then
        for _, kind in ipairs(Extras.DEBUFF_TYPES) do
            local types = { [kind] = true }
            local s = add("deb:" .. kind, "HARMFUL", { includeDispelTypes = types }, Colour(kind), InitSquare)
            s.kind, s.name, s.types = "deb", kind, types
        end
    end
    Arm(container, eng.unit)
    part.armed = true
    return part
end

local function BuildEdge(eng)
    local host, level = eng.host, eng.level + 6
    local container = NewContainer(host, level)
    local part = { container = container, slots = {}, order = {}, armed = false }
    local anchor = Proxy(host, level)
    if eng.edgeAnchor then eng.edgeAnchor(anchor) else anchor:SetAllPoints(host) end
    part.anchor = anchor
    local method, direction = SortOptions()
    for _, kind in ipairs(Extras.DEBUFF_TYPES) do
        local types = { [kind] = true }
        local ok = pcall(container.AddAuraSlot, container, "edge:" .. kind, "HARMFUL", {
            initializeFrame = InitEdge(anchor, Colour(kind)), candidateFilters = { includeDispelTypes = types },
            sortMethod = method, sortDirection = direction,
        })
        if not ok then error("AddAuraSlot edge:" .. kind, 0) end
        local slot = { key = "edge:" .. kind, kind = "deb", name = kind, types = types }
        part.slots[slot.key] = slot
        part.order[#part.order + 1] = slot
    end
    Arm(container, eng.unit)
    part.armed = true
    return part
end

local function BuildTray(eng)
    local origin = eng.trayOrigin
    if not origin then error("no tray origin", 0) end
    local level = eng.level + 3
    local container = NewContainer(eng.host, level)
    local part = { container = container, groups = {}, order = {}, armed = false }
    local size = Style.Number("party", "alertSize")
    local method, direction = SortOptions()
    local cap = math.max(1, math.min(TRAY_CAP_MAX, Style.Number("party", "alertMax")) - 1)
    for _, kind in ipairs(Extras.DEBUFF_TYPES) do
        local types = { [kind] = true }
        local ok = pcall(container.AddAuraGroup, container, "tray:" .. kind, "HARMFUL", {
            maxFrameCount = cap, sortMethod = method, sortDirection = direction,
            candidateFilters = { includeDispelTypes = types },
            initializeFrame = InitTrayIcon(Colour(kind), size),
            layout = { elementSpacing = TRAY_GAP, lineSpacing = TRAY_GAP, groupSpacing = 0, groupLineSpacing = 0,
                elementWidth = size, elementHeight = size },
        })
        if not ok then error("AddAuraGroup tray:" .. kind, 0) end
        local group = { key = "tray:" .. kind, kind = "deb", name = kind, types = types }
        part.groups[group.key] = group
        part.order[#part.order + 1] = group
    end
    part.origin = origin
    Arm(container, eng.unit)
    part.armed = true
    return part
end

local BUILDERS = { markers = BuildMarkers, edge = BuildEdge, tray = BuildTray }

-- Builds the containers the switches ask for and the client allows. Out of combat only (fail closed). Each part gets
-- Engine.BUILD_TRIES attempts; a failed one is logged once and leaves that part to the Lua layer.
function Engine.Ensure(eng)
    if not eng or Locked() then return false end
    local mode = Engine.Mode()
    if mode == "off" then return false end
    if eng.settled then return true end
    if mode == "borrow" or eng.fallback then return Extras.Borrow.Ensure(eng, Engine.Explicit()) end
    local w = Engine.Wanted(eng.key)
    local want = {
        markers = next(w.hots) ~= nil or next(w.debs) ~= nil,
        edge = next(w.edge) ~= nil,
        tray = eng.key == "party" and next(w.tray) ~= nil,
    }
    for part, wanted in pairs(want) do
        if wanted and not eng.parts[part] and (eng.tries[part] or 0) < Engine.BUILD_TRIES then
            eng.tries[part] = (eng.tries[part] or 0) + 1
            local ok, result = pcall(BUILDERS[part], eng)
            if ok then
                eng.parts[part] = result
            else
                Degrade("group_aura_engine_" .. part,
                    "the " .. part .. " aura container could not be built for group frames, "
                    .. "they keep the out of combat display (" .. tostring(result) .. ")")
            end
        end
    end
    -- Nothing could be built for a unit that wants something: its containers are given up and the Blizzard icons are borrowed.
    local anyWanted, exhausted = false, true
    for part, wanted in pairs(want) do
        if wanted then
            anyWanted = true
            if eng.parts[part] or (eng.tries[part] or 0) < Engine.BUILD_TRIES then exhausted = false end
        end
    end
    if anyWanted and exhausted and next(eng.parts) == nil then
        eng.fallback = true
        return Extras.Borrow.Ensure(eng, false)
    end
    -- Settled once every wanted part is built or out of tries: the per update step then costs one flag read.
    eng.settled = true
    for part, wanted in pairs(want) do
        if wanted and not eng.parts[part] and (eng.tries[part] or 0) < Engine.BUILD_TRIES then eng.settled = false end
    end
    Engine.Apply(eng)
    return true
end

-- The switches changed (or the dispel set did): build what is newly wanted and seat everything again. In a fight only the
-- plain parts of that run; the rest is owed to the end of it.
function Engine.Restyle(eng)
    if not eng then return end
    eng.settled = false
    if Locked() then Engine.Apply(eng) else Engine.Ensure(eng) end
end

local function SeatMarkerProxies(eng, part, w)
    local key = eng.key
    local size, corner = Style.Number(key, "mkSize"), Style.Get(key, "mkPos")
    if not CORNER_SIDE[corner] then corner = Style.Default(key, "mkPos") end
    local v, s = CORNER_VERTICAL[corner], CORNER_SIDE[corner]
    local sign = s == "RIGHT" and -1 or 1
    local y = v == "TOP" and -2 or 2
    local lane = 0
    for _, slot in ipairs(part.order) do
        local on = (slot.kind == "hot" and w.hots[slot.name]) or (slot.kind == "deb" and w.debs[slot.name]) or false
        slot.wanted = on and true or false
        if on then
            lane = lane + 1
            slot.proxy:SetSize(size, size)
            slot.proxy:ClearAllPoints()
            slot.proxy:SetPoint(v .. s, eng.host, v .. s, sign * (3 + (lane - 1) * (size + 1)), y)
        end
    end
    part.lanes = lane
end

-- Switches a slot's candidate filter between its real one and one nothing matches.
local function SetSlotWanted(container, slot, on)
    if slot.off == not on then return true end
    local candidate
    if on then
        candidate = slot.ids and { includeSpellIDs = slot.ids } or { includeDispelTypes = slot.types }
    elseif slot.ids then
        candidate = { includeSpellIDs = { [SENTINEL_ID] = true } }
    else
        candidate = { includeDispelTypes = { [SENTINEL_TYPE] = true } }
    end
    local ok = pcall(container.SetAuraSlotCandidateFilters, container, slot.key, candidate)
    if ok then slot.off = not on end
    return ok
end

local function SetGroupWanted(container, group, on)
    if group.off == not on then return true end
    local candidate = { includeDispelTypes = on and group.types or { [SENTINEL_TYPE] = true } }
    local ok = pcall(container.SetAuraGroupCandidateFilters, container, group.key, candidate)
    if ok then group.off = not on end
    return ok
end

local function SeatTray(eng, part)
    local origin = part.origin
    local side = Style.Get("party", "alertSide")
    local size = Style.Number("party", "alertSize")
    local cap = math.max(1, math.min(TRAY_CAP_MAX, Style.Number("party", "alertMax")) - 1)
    local rightSide = side == "right"
    local anchor = rightSide and "TOPLEFT" or "TOPRIGHT"
    local flow = type(_G.AnchorUtil) == "table" and _G.AnchorUtil.FlowDirection or nil
    local c = part.container
    local ok = true
    local function step(fn) if not pcall(fn) then ok = false end end
    step(function()
        c:ClearAllPoints()
        c:SetPoint(anchor, origin, anchor, 0, 0)
    end)
    if part.seat ~= (side .. size .. cap) then
        step(function()
            c:SetFlowLayoutAnchorPoint(anchor)
            c:SetFlowLayoutGrowthDirection(rightSide and (flow and flow.Right or 1) or (flow and flow.Left or -1),
                flow and flow.Down or -1)
            Quiet(c, "SetFlowLayoutMaximumLineSize", cap * (size + TRAY_GAP) + 1)
        end)
        for _, group in ipairs(part.order) do
            step(function()
                c:SetAuraGroupMaxFrameCount(group.key, cap)
                c:SetAuraGroupLayout(group.key, { elementSpacing = TRAY_GAP, lineSpacing = TRAY_GAP, groupSpacing = 0,
                    groupLineSpacing = 0, elementWidth = size, elementHeight = size })
            end)
        end
        if ok then part.seat = side .. size .. cap end
    end
    return ok
end

local function Alpha(part, a)
    if part and part.container and part.alpha ~= a then
        if Quiet(part.container, "SetAlpha", a) then part.alpha = a end
    end
end

-- Seats the proxies and filters for the current switches and sets each container's alpha for the mode. Plain frames and
-- alpha run in combat; the engine's own setters (filters, layout) are tried everywhere and, when one is refused, the
-- change is owed to REGEN_ENABLED (eng.owed).
function Engine.Apply(eng)
    if not eng then return end
    if eng.borrow then return Extras.Borrow.Apply(eng) end
    local w = Engine.Wanted(eng.key)
    eng.owed = false
    local fight = Engine.fight
    local markers, edge, tray = eng.parts.markers, eng.parts.edge, eng.parts.tray
    local anyMarker, anyEdge, anyTray = false, false, false
    if markers then
        SeatMarkerProxies(eng, markers, w)
        for _, slot in ipairs(markers.order) do
            if not SetSlotWanted(markers.container, slot, slot.wanted) then eng.owed = true end
            if slot.wanted then anyMarker = true end
        end
    end
    if edge then
        for _, slot in ipairs(edge.order) do
            local on = w.edge[slot.name] == true
            if not SetSlotWanted(edge.container, slot, on) then eng.owed = true end
            if on then anyEdge = true end
        end
    end
    if tray then
        if not SeatTray(eng, tray) then eng.owed = true end
        for _, group in ipairs(tray.order) do
            local on = w.tray[group.name] == true
            if not SetGroupWanted(tray.container, group, on) then eng.owed = true end
            if on then anyTray = true end
        end
    end
    local live = fight and not eng.down
    Alpha(markers, live and anyMarker and 1 or 0)
    Alpha(edge, live and anyEdge and 1 or 0)
    Alpha(tray, live and anyTray and 1 or 0)
end

-- The member is down (dead or offline): nothing of theirs shows in a fight.
function Engine.SetDown(eng, down)
    if not eng or eng.down == (down and true or false) then return end
    eng.down = down and true or false
    Engine.Apply(eng)
end

-- The engine layer is showing for this frame: a fight is on and the part (or any part) is armed and wanted.
function Engine.Covers(eng, part)
    if not (eng and Engine.fight) then return false end
    local p = eng.parts[part]
    return p ~= nil and p.armed == true and (p.alpha == 1)
end

local function SetFight(on)
    if Engine.fight == on then return end
    Engine.fight = on
    for _, eng in ipairs(Engine.list) do
        pcall(Engine.Apply, eng)
        if eng.onMode then pcall(eng.onMode, eng, on) end
    end
end

-------------------------------------------------------------------------------
-- Borrowed Blizzard icons (the second in combat path)
-------------------------------------------------------------------------------
-- Blizzard's compact party and raid frames still show debuffs in a fight because their code runs untainted. In "borrow"
-- mode (or for a unit whose containers could not be built) their events are left alive (the sweeps in PartyFrames and
-- RaidFrames skip UnregisterAllEvents on a frame that carries aura icons, `Borrow.Dim`; the frame itself stays alpha 0 and
-- mouse off) and ONLY the icon children (`dispelDebuffFrames`, `buffFrames`) are moved onto plain hosts of ours:
-- SetParent, ClearAllPoints and SetPoint on the icon, never on the compact frame (an Edit Mode system), and ONLY OUT OF
-- COMBAT (a move that Blizzard undoes in a fight is re-done at the end of it). The icons keep Blizzard's own drawing and
-- updating; our hosts are alpha 0 out of combat (the Lua display draws then) and alpha 1 in a fight, exactly the engine
-- layer's mode. UNVERIFIED in game: whether the compact frames exist for a party, whether they update at alpha 0, and
-- whether Blizzard re-anchors an icon in a fight (the icons would then sit where Blizzard puts them until it ends).
local Borrow = {}
Extras.Borrow = Borrow
Borrow.MAX_DISPEL, Borrow.MAX_BUFF = 4, 3

local function IsFrameList(t)
    return type(t) == "table" and t[1] ~= nil
end

-- A compact unit frame: one that carries the aura icon lists. Plain table reads only.
function Borrow.IsAuraFrame(frame)
    if type(frame) ~= "table" then return false end
    local ok, dispel, buffs = pcall(function() return frame.dispelDebuffFrames, frame.buffFrames end)
    return ok and (IsFrameList(dispel) or IsFrameList(buffs))
end

function Borrow.Active() return Engine.Mode() == "borrow" end

-- The sweep for such a frame in borrow mode: dim and switch the mouse off, but keep the events (UnregisterAllEvents is
-- what stops its icons updating). Returns false when the caller should sweep it the usual way.
function Borrow.Dim(frame)
    if not (Borrow.Active() and Borrow.IsAuraFrame(frame)) then return false end
    frame:SetAlpha(0)
    if frame.EnableMouse then frame:EnableMouse(false) end
    for _, child in ipairs({ frame:GetChildren() }) do
        if child.EnableMouse then child:EnableMouse(false) end
    end
    return true
end

local function UnitOf(frame)
    local ok, a, b = pcall(function() return frame.unit, frame.displayedUnit end)
    if not ok then return nil end
    if not IsSecret(a) and type(a) == "string" then return a end
    if not IsSecret(b) and type(b) == "string" then return b end
    return nil
end

-- The compact unit frame showing `unit`, or nil. Reads only: the party's CompactPartyFrame members and the raid's
-- CompactRaidFrameN / group members.
function Borrow.Find(unit)
    local candidates = {}
    local party = _G.CompactPartyFrame
    if type(party) == "table" and type(party.memberUnitFrames) == "table" then
        for _, f in ipairs(party.memberUnitFrames) do candidates[#candidates + 1] = f end
    end
    local raid = _G.CompactRaidFrameContainer
    if type(raid) == "table" and raid.GetChildren then
        local ok, kids = pcall(function() return { raid:GetChildren() } end)
        if ok then
            for _, child in ipairs(kids) do
                candidates[#candidates + 1] = child
                local okG, grand = pcall(function() return { child:GetChildren() } end)
                if okG then for _, g in ipairs(grand) do candidates[#candidates + 1] = g end end
            end
        end
    end
    for _, f in ipairs(candidates) do
        if Borrow.IsAuraFrame(f) and UnitOf(f) == unit then return f end
    end
    return nil
end

local function Reseat(eng)
    local b = eng.borrow
    if not b then return false end
    if Locked() then b.owed = true return false end
    local key = eng.key
    local isParty = key == "party"
    local side = isParty and Style.Get("party", "alertSide") or nil
    local dsize = isParty and Style.Number("party", "alertSize") or math.max(8, Style.Number(key, "mkSize") * 2)
    local dcap = isParty and math.max(1, math.min(TRAY_CAP_MAX, Style.Number("party", "alertMax")) - 1) or Borrow.MAX_DISPEL
    local rightSide = side == "right"
    local gap = isParty and TRAY_GAP or 1
    local ok = true
    local function step(fn) if not pcall(fn) then ok = false end end
    b.seating = true
    -- the dispel host: where the engine tray would flow (party) or along the cell's bottom edge (raid)
    step(function()
        b.dispelHost:SetSize(dcap * (dsize + gap), dsize)
        b.dispelHost:ClearAllPoints()
        if isParty and eng.trayOrigin then
            local anchor = rightSide and "TOPLEFT" or "TOPRIGHT"
            b.dispelHost:SetPoint(anchor, eng.trayOrigin, anchor, 0, 0)
        else
            b.dispelHost:SetPoint("BOTTOMLEFT", eng.host, "BOTTOMLEFT", 2, 2)
        end
    end)
    for i, icon in ipairs(b.dispel) do
        step(function()
            if i <= dcap then
                icon:SetParent(b.dispelHost)
                icon:ClearAllPoints()
                icon:SetSize(dsize, dsize)
                if isParty and not rightSide then
                    icon:SetPoint("TOPRIGHT", b.dispelHost, "TOPRIGHT", -(i - 1) * (dsize + gap), 0)
                else
                    icon:SetPoint("TOPLEFT", b.dispelHost, "TOPLEFT", (i - 1) * (dsize + gap), 0)
                end
                if icon.EnableMouse then icon:EnableMouse(false) end
            else
                icon:SetParent(b.spare)   -- beyond the cap: out of sight
            end
        end)
    end
    -- the buff host: the marker corner
    local size, corner = Style.Number(key, "mkSize") * 2, Style.Get(key, "mkPos")
    if not CORNER_SIDE[corner] then corner = Style.Default(key, "mkPos") end
    local v, sd = CORNER_VERTICAL[corner], CORNER_SIDE[corner]
    local sign = sd == "RIGHT" and -1 or 1
    step(function()
        b.buffHost:SetSize(Borrow.MAX_BUFF * (size + 1), size)
        b.buffHost:ClearAllPoints()
        b.buffHost:SetPoint(v .. sd, eng.host, v .. sd, sign * 3, v == "TOP" and -2 or 2)
    end)
    for i, icon in ipairs(b.buff) do
        step(function()
            if i <= Borrow.MAX_BUFF then
                icon:SetParent(b.buffHost)
                icon:ClearAllPoints()
                icon:SetSize(size, size)
                icon:SetPoint(v .. sd, b.buffHost, v .. sd, sign * (i - 1) * (size + 1), 0)
                if icon.EnableMouse then icon:EnableMouse(false) end
            else
                icon:SetParent(b.spare)
            end
        end)
    end
    b.seating = false
    b.lanes = math.min(#b.buff, Borrow.MAX_BUFF)
    b.owed = not ok
    return ok
end

-- Takes the compact frame's icon lists and the hosts; out of combat only. Returns true when attached.
local function Attach(eng, explicit)
    local compact = Borrow.Find(eng.unit)
    if not compact then
        if explicit then Degrade("group_aura_borrow", "no compact frame carries the aura icons for " .. tostring(eng.unit) .. " (and maybe others), group frames keep the out of combat display") end
        return false
    end
    -- the frame's events were left alive by the sweep in borrow mode; a unit that fell back from the engine woke them here
    if type(compact.IsEventRegistered) == "function" and type(compact.RegisterUnitEvent) == "function" then
        local okR, reg = pcall(compact.IsEventRegistered, compact, "UNIT_AURA")
        if okR and not reg then pcall(compact.RegisterUnitEvent, compact, "UNIT_AURA", eng.unit) end
    end
    local b = { compact = compact, dispel = {}, buff = {} }
    b.dispelHost = CreateFrame("Frame", nil, eng.host)
    b.buffHost = CreateFrame("Frame", nil, eng.host)
    b.spare = CreateFrame("Frame", nil, eng.host)
    for _, host in ipairs({ b.dispelHost, b.buffHost }) do
        host:SetFrameLevel(eng.level + 8)
        host:EnableMouse(false)
        host:SetAlpha(0)
    end
    b.spare:Hide()
    for _, icon in ipairs(compact.dispelDebuffFrames or {}) do b.dispel[#b.dispel + 1] = icon end
    for _, icon in ipairs(compact.buffFrames or {}) do b.buff[#b.buff + 1] = icon end
    eng.borrow = b
    -- stand-ins with the engine parts' shape, so the owners' fight mode (held halo, tiles and squares out, the missing buff
    -- tile seated after the tray) needs no second code path; the edge is not borrowed, the held Lua one stays
    eng.parts.tray = eng.key == "party" and { container = b.dispelHost, armed = true, alpha = 0 } or nil
    eng.parts.markers = { container = b.buffHost, armed = true, alpha = 0, lanes = 0 }
    if type(hooksecurefunc) == "function" then
        for _, icon in ipairs(b.dispel) do
            pcall(hooksecurefunc, icon, "SetPoint", function() if not b.seating then b.owed = true end end)
        end
        for _, icon in ipairs(b.buff) do
            pcall(hooksecurefunc, icon, "SetPoint", function() if not b.seating then b.owed = true end end)
        end
    end
    Reseat(eng)
    return true
end

-- Attach once (BUILD_TRIES tries), then keep it seated. `explicit` = the player chose borrow (a failure is logged).
function Borrow.Ensure(eng, explicit)
    eng.fallback = eng.fallback or not explicit
    if not eng.borrow then
        eng.tries.borrow = (eng.tries.borrow or 0) + 1
        local ok, attached = pcall(Attach, eng, explicit)
        if not ok then Degrade("group_aura_borrow_error", "borrowing the Blizzard aura icons failed (" .. tostring(attached) .. ")") end
        if not (ok and attached) and eng.tries.borrow < Engine.BUILD_TRIES then
            eng.settled = false
            return false
        end
    end
    eng.settled = true
    if eng.borrow then eng.borrow.seated = false end   -- a style change seats the icons again
    Engine.Apply(eng)
    return eng.borrow ~= nil
end

-- Seat again if Blizzard moved an icon (out of combat) and set the hosts' alpha for the mode.
function Borrow.Apply(eng)
    local b = eng.borrow
    if not b then return end
    local w = Engine.Wanted(eng.key)
    if b.owed or not b.seated then
        if Reseat(eng) then b.seated = true end
    end
    eng.owed = b.owed == true
    local live = Engine.fight and not eng.down
    local dispelOn = next(eng.key == "party" and w.tray or w.debs) ~= nil
    local buffOn = next(w.hots) ~= nil
    local function alpha(host, part, a)
        if host.alphaNow ~= a then host.alphaNow = a; pcall(host.SetAlpha, host, a) end
        if part then part.alpha = a end
    end
    alpha(b.dispelHost, eng.parts.tray, live and dispelOn and 1 or 0)
    alpha(b.buffHost, eng.parts.markers, live and buffOn and 1 or 0)
    if eng.parts.markers then eng.parts.markers.lanes = buffOn and b.lanes or 0 end
end

do   -- a reload in a fight starts in the engine mode
    local ok, v = pcall(function() return type(InCombatLockdown) == "function" and InCombatLockdown() end)
    Engine.fight = ok and v and true or false
end

local events = CreateFrame("Frame")
Engine.events = events
events:RegisterEvent("PLAYER_REGEN_DISABLED")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_REGEN_DISABLED" then
        SetFight(true)
    else
        SetFight(false)
        for _, eng in ipairs(Engine.list) do
            if eng.unit then pcall(Engine.Restyle, eng) end   -- builds what a fight kept from building, retries what was owed
        end
    end
end)
