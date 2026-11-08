-- Forever STUwave: QuestTimer
-- A quest timer of our own, hung under the minimap's chassis like a drawer of the minimap (design: the quest timer
-- mockup, form A "drawer rows", 2026-11-05). The chassis is the control bezel and, flush under it, the coords and clock row
-- (Minimap.fsReadoutRow); the drawer seats under that row, or under the bezel when the minimap built no row. Blizzard's
-- QuestTimerFrame is hidden while this is on; with the switch off it comes back as it was. One row per running timer,
-- soonest first: an MM:SS readout in the mana regen module's LED (the same segment atlas, Media/Textures/led_segments.tga)
-- in a well on the left, and on the right the quest name over a twenty segment gauge and a small "quest timer" label.
-- Cyan above a minute, amber under it, pink under fifteen seconds.
--
-- Data: GetQuestTimers() gives the seconds left on each timer, GetQuestIndexForTimer(i) the quest's log index. The
-- seconds are read on quest log events and turned into a deadline, so the readout counts down on its own between events.
-- The game does not say a quest's full limit, so the gauge is the time left out of the most seen for that quest.
--
-- Plain frames only, no secure templates, so building, painting and hiding Blizzard's timer are legal in combat. Every
-- size is a whole count of physical pixels; the name is a single line clipped to its room with an ellipsis, so nothing
-- spills past the drawer.

local _, FS = ...

local QT = {}
FS.QuestTimer = QT

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local KEY = "questTimer.shown"
QT.KEY = KEY
QT.SETTING = {
    label = "Quest timer under the minimap",
    key = KEY,
    tip = "Shows quest timers in a strip under the minimap, in place of the game's own timer window.",
}
if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(KEY, true) end

-- Design px (the Layout scale turns them into UI units, then into whole physical pixels).
local D = {
    ROW_H = 26, TOP = 5, BOTTOM = 3, SIDE = 4,
    WELL_W = 58, WELL_H = 16,              -- the LED well, from the row's top left at (SIDE, 0)
    LED_X = 4, LED_Y = 2,                  -- the readout inside the well, in texels
    TEXT_X = 66,                           -- name, gauge and label start here
    NAME_PX = 10, LABEL_PX = 8,
    GAUGE_Y = 12, GAUGE_H = 4, GAUGE_N = 20,
}
local CELL_W, CELL_H, ATLAS, GLOW_PAD, GLOW_W, GLOW_H = 10, 12, 64, 2, 14, 16
local AMBER_AT, PINK_AT = 60, 15
local MAX_ROWS = 4

local SEGMENT_ORDER = { "a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m" }
local GLYPH_TEXT = {
    ["0"] = "a b c d e f", ["1"] = "b c", ["2"] = "a b g1 g2 e d", ["3"] = "a b c d g1 g2", ["4"] = "f b g1 g2 c",
    ["5"] = "a f g1 g2 c d", ["6"] = "a f e d c g1 g2", ["7"] = "a b c", ["8"] = "a b c d e f g1 g2",
    ["9"] = "a b c d f g1 g2",
}
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

local function IsSecret(v)
    return FS.IsSecret and FS.IsSecret(v) or false
end

local function Enabled()
    if not (FS.Config and FS.Config.Get) then return true end
    local ok, v = pcall(FS.Config.Get, KEY)
    return not ok or v ~= false
end

-------------------------------------------------------------------------------
-- Model
-------------------------------------------------------------------------------

local timers = {}      -- { key, name, deadline, most }, soonest first
local most = {}        -- quest key -> the most seconds seen, for the gauge

-- "MM", "SS" for a count of seconds, clamped to 0..99:59.
function QT.Digits(secs)
    secs = math.max(0, math.min(99 * 60 + 59, math.ceil(secs)))
    return ("%02d"):format(math.floor(secs / 60)), ("%02d"):format(secs % 60)
end

function QT.Color(secs)
    local T = FS.Theme
    if secs < PINK_AT then return T.COLOR_HEALTH end
    if secs < AMBER_AT then return T.COLOR_AMBER end
    return T.COLOR_POWER
end

local function QuestName(i)
    local idxOf = _G.GetQuestIndexForTimer
    if type(idxOf) ~= "function" then return nil end
    local ok, index = pcall(idxOf, i)
    if not ok or type(index) ~= "number" or IsSecret(index) then return nil end
    local log = _G.C_QuestLog
    if log and type(log.GetTitleForLogIndex) == "function" then
        local okT, title = pcall(log.GetTitleForLogIndex, index)
        if okT and type(title) == "string" and not IsSecret(title) then return title end
    end
    if type(_G.GetQuestLogTitle) == "function" then
        local okT, title = pcall(_G.GetQuestLogTitle, index)
        if okT and type(title) == "string" and not IsSecret(title) then return title end
    end
end

-- Reads the game's timers into deadlines from `now`. Returns the list.
function QT.Read(now)
    local list = {}
    local get = _G.GetQuestTimers
    if type(get) == "function" then
        local ok, values = pcall(function() return { get() } end)
        if ok then
            for i, secs in ipairs(values) do
                if type(secs) == "number" and not IsSecret(secs) and secs >= 0 then
                    local name = QuestName(i)
                    local key = name or ("#" .. i)
                    most[key] = math.max(most[key] or 0, secs)
                    list[#list + 1] = { key = key, name = name or "Quest timer", deadline = now + secs, most = most[key] }
                elseif IsSecret(secs) and FS.LogDegradeOnce then
                    FS.LogDegradeOnce("questtimer-secret", "Quest timer: GetQuestTimers gave an unreadable value")
                end
            end
        end
    end
    table.sort(list, function(a, b) return a.deadline < b.deadline end)
    timers = list
    return list
end

-------------------------------------------------------------------------------
-- Pixels
-------------------------------------------------------------------------------

local G = {}           -- px (UI units a physical pixel), k (physical pixels a design px), n (pixels a LED texel)

local function Seat(host)
    local s = (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
    local factor
    local pu = _G.PixelUtil
    if type(pu) == "table" and type(pu.GetPixelToUIUnitFactor) == "function" then
        local ok, v = pcall(pu.GetPixelToUIUnitFactor)
        if ok and type(v) == "number" and v > 0 then factor = v end
    end
    local scale = 1
    local ok, v = pcall(host.GetEffectiveScale, host)
    if ok and type(v) == "number" and v > 0 then scale = v end
    G.px = factor and factor / scale or s
    G.k = s / G.px
    G.n = math.max(1, math.floor(G.k + 0.5))
end

local function P(d) return math.floor(d * G.k + 0.5) end

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
    return tex
end

local function Flat(parent, layer, sub)
    local t = Crisp(parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0))
    t:SetColorTexture(1, 1, 1, 1)
    return t
end

-- Seats `region` at x, y physical pixels from `anchor`'s top left, w x h pixels.
local function At(region, anchor, x, y, w, h)
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", anchor, "TOPLEFT", x * G.px, -y * G.px)
    if w then region:SetSize(w * G.px, h * G.px) end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local drawer

local function NewCell(parent)
    local cell = { seg = {}, gl = {} }
    for n = 1, #SEGMENT_ORDER do
        local l, t = ((n - 1) % 4) * 0.25, math.floor((n - 1) / 4) * 0.25
        local gl = Crisp(parent:CreateTexture(nil, "ARTWORK", nil, 1))
        gl:SetTexture(MEDIA .. "led_segment_glow.tga")
        gl:SetBlendMode("ADD")
        gl:SetTexCoord(l, l + GLOW_W / ATLAS, t, t + GLOW_H / ATLAS)
        cell.gl[n] = gl
        local tex = Crisp(parent:CreateTexture(nil, "ARTWORK", nil, 2))
        tex:SetTexture(MEDIA .. "led_segments.tga")
        tex:SetTexCoord(l, l + CELL_W / ATLAS, t, t + CELL_H / ATLAS)
        cell.seg[n] = tex
    end
    return cell
end

local function NewRow(parent)
    local T = FS.Theme
    local row = { frame = CreateFrame("Frame", nil, parent) }
    row.frame:EnableMouse(false)
    local well = CreateFrame("Frame", nil, row.frame)
    well:EnableMouse(false)
    row.well = well
    row.wellFill = T.AddCut2Texture(well, T.SLICE_CUT2_FILL_TEXTURE, T.COLOR_BAR_TRACK, "BACKGROUND", 1)
    row.wellRing = T.AddCut2Texture(well, T.SLICE_CUT2_OUTLINE_TEXTURE, T.COLOR_POWER, "BORDER", 1)
    Crisp(row.wellFill); Crisp(row.wellRing)
    row.cells = { NewCell(well), NewCell(well), NewCell(well), NewCell(well) }
    row.colon = { Flat(well, "ARTWORK", 2), Flat(well, "ARTWORK", 2) }
    row.name = row.frame:CreateFontString(nil, "OVERLAY")
    T.ApplyMono(row.name, D.NAME_PX, T.COLOR_TEXT_WHITE)
    row.name:SetJustifyH("LEFT")
    if row.name.SetWordWrap then row.name:SetWordWrap(false) end
    if row.name.SetMaxLines then row.name:SetMaxLines(1) end
    row.label = row.frame:CreateFontString(nil, "OVERLAY")
    T.ApplyMono(row.label, D.LABEL_PX, T.COLOR_MUTED)
    row.label:SetJustifyH("LEFT")
    if row.label.SetWordWrap then row.label:SetWordWrap(false) end
    row.label:SetText("quest timer")
    row.gaugeWell = Flat(row.frame, "BACKGROUND", 2)
    row.gaugeRing = { Flat(row.frame, "BORDER", 2), Flat(row.frame, "BORDER", 2), Flat(row.frame, "BORDER", 2),
        Flat(row.frame, "BORDER", 2) }
    row.gauge = {}
    for i = 1, D.GAUGE_N do row.gauge[i] = Flat(row.frame, "ARTWORK", 3) end
    row.rule = Flat(row.frame, "BORDER", 3)
    return row
end

-- The frame the drawer hangs from: the bottom of the minimap's chassis. Minimap.lua builds the coords and clock row under the
-- bezel, so that row is the bottom; with no row the bezel is.
local function ChassisBottom()
    local map = _G.Minimap
    return map and (map.fsReadoutRow or map.fsBezel)
end

local function Build()
    if drawer then return drawer end
    local chassis = ChassisBottom()
    if not chassis then return nil end
    local T = FS.Theme
    local f = CreateFrame("Frame", "ForeverSTUwaveQuestTimer", chassis)
    f:SetFrameLevel(chassis:GetFrameLevel())
    f:SetPoint("TOPLEFT", chassis, "BOTTOMLEFT", 0, 0)
    f:SetPoint("TOPRIGHT", chassis, "BOTTOMRIGHT", 0, 0)
    f:SetHeight(1)
    f:Hide()
    f.fill, f.glow, f.border = T.AddPanelChrome(f, { fillColor = T.COLOR_BG, accent = T.COLOR_POWER })
    f.rows = {}
    f:EnableMouse(true)
    f:SetScript("OnEnter", function(self)
        if not GameTooltip then return end
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
        local now = GetTime()
        for _, t in ipairs(timers) do
            local mm, ss = QT.Digits(t.deadline - now)
            GameTooltip:AddDoubleLine(t.name, mm .. ":" .. ss, 1, 1, 1, 1, 1, 1)
        end
        GameTooltip:Show()
    end)
    f:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    drawer = f
    return f
end

-------------------------------------------------------------------------------
-- Layout and paint
-------------------------------------------------------------------------------

local function LayoutRow(row, i, widthPx)
    local n = G.n
    local rowPx, top = P(D.ROW_H), P(D.TOP)
    local y = top + (i - 1) * rowPx
    At(row.frame, drawer, 0, y, widthPx, rowPx)
    local side = P(D.SIDE)
    -- the well holds the readout exactly: four cells, three 2 texel gaps, a 4 texel colon column, the LED inset on both sides
    local ledW = (4 * CELL_W + 3 * 2 + 4) * n
    local wellW = math.max(P(D.WELL_W), ledW + 2 * D.LED_X * n)
    local wellH = math.max(P(D.WELL_H), CELL_H * n + 2 * D.LED_Y * n)
    At(row.well, row.frame, side, 0, wellW, wellH)
    local lx, ly = math.floor((wellW - ledW) / 2), math.floor((wellH - CELL_H * n) / 2)
    local x = lx
    for c = 1, 4 do
        local cell = row.cells[c]
        for s = 1, #SEGMENT_ORDER do
            At(cell.seg[s], row.well, x, ly, CELL_W * n, CELL_H * n)
            At(cell.gl[s], row.well, x - GLOW_PAD * n, ly - GLOW_PAD * n, GLOW_W * n, GLOW_H * n)
        end
        x = x + (CELL_W + 2) * n
        if c == 2 then
            At(row.colon[1], row.well, x, ly + 3 * n, 2 * n, 2 * n)
            At(row.colon[2], row.well, x, ly + 7 * n, 2 * n, 2 * n)
            x = x + 4 * n
        end
    end
    -- the text column: from just right of the well to the drawer's inner edge
    local tx = math.max(P(D.TEXT_X), side + wellW + P(4))
    local room = widthPx - tx - side
    row.name:ClearAllPoints()
    row.name:SetPoint("TOPLEFT", row.frame, "TOPLEFT", tx * G.px, -P(1) * G.px)
    row.name:SetWidth(math.max(1, room) * G.px)
    local gy, gh = P(D.GAUGE_Y), math.max(2, P(D.GAUGE_H))
    At(row.gaugeWell, row.frame, tx, gy, room, gh)
    At(row.gaugeRing[1], row.frame, tx, gy, room, 1)
    At(row.gaugeRing[2], row.frame, tx, gy + gh - 1, room, 1)
    At(row.gaugeRing[3], row.frame, tx, gy, 1, gh)
    At(row.gaugeRing[4], row.frame, tx + room - 1, gy, 1, gh)
    local inner = room - 2
    local pitch = inner / D.GAUGE_N
    for g = 1, D.GAUGE_N do
        local l = tx + 1 + math.floor((g - 1) * pitch + 0.5)
        local r = tx + 1 + math.floor(g * pitch + 0.5) - 1
        At(row.gauge[g], row.frame, l, gy + 1, math.max(1, r - l), math.max(1, gh - 2))
    end
    row.label:ClearAllPoints()
    row.label:SetPoint("TOPLEFT", row.frame, "TOPLEFT", tx * G.px, -(gy + gh + P(1)) * G.px)
    row.label:SetWidth(math.max(1, room) * G.px)
    At(row.rule, row.frame, side, -P(2) - 1, widthPx - 2 * side, 1)
    row.rule:SetShown(i > 1)
    row.ch = nil
end

local function Tint(t, c, a) t:SetVertexColor(c[1], c[2], c[3], a or 1) end

local function PaintRow(row, t, now)
    local T = FS.Theme
    local left = t.deadline - now
    local col = QT.Color(left)
    local mm, ss = QT.Digits(left)
    local str = mm .. ss
    if row.ch ~= str or row.col ~= col then
        row.ch, row.col = str, col
        for c = 1, 4 do
            local lit = GLYPH[str:sub(c, c)] or {}
            local cell = row.cells[c]
            for s = 1, #SEGMENT_ORDER do
                if lit[s] then
                    Tint(cell.seg[s], col, 1); Tint(cell.gl[s], col, 0.5)
                else
                    Tint(cell.seg[s], col, 0.08); Tint(cell.gl[s], col, 0)
                end
            end
        end
        Tint(row.colon[1], col); Tint(row.colon[2], col)
        Tint(row.wellRing, col, 0.75)
    end
    row.name:SetText(t.name)
    row.name:SetTextColor(left < AMBER_AT and col[1] or 1, left < AMBER_AT and col[2] or 1, left < AMBER_AT and col[3] or 1)
    Tint(row.gaugeWell, T.COLOR_BAR_TRACK, 0.95)
    for k = 1, 4 do Tint(row.gaugeRing[k], T.COLOR_BORDER, 0.4) end
    local frac = t.most > 0 and math.max(0, math.min(1, left / t.most)) or 0
    local lit = math.ceil(frac * D.GAUGE_N - 1e-9)
    for g = 1, D.GAUGE_N do
        if g <= lit then Tint(row.gauge[g], col, g == lit and 0.7 or 1) else Tint(row.gauge[g], T.COLOR_BORDER, 0.22) end
    end
    Tint(row.rule, T.COLOR_BORDER, 0.3)
end

local ticker
local laidOutFor

local function Paint()
    if not drawer then return end
    local now = GetTime()
    local worst
    for i, row in ipairs(drawer.rows) do
        local t = timers[i]
        if t then
            PaintRow(row, t, now)
            local left = t.deadline - now
            worst = worst and math.min(worst, left) or left
        end
    end
    if worst then
        local c = QT.Color(worst)
        Tint(drawer.border, c, 1)
        Tint(drawer.glow, c, worst < AMBER_AT and 0.55 or 0.3)
    end
end

local function StopTicker()
    if ticker then ticker:Cancel(); ticker = nil end
end

-- Blizzard's timer is hidden only while the drawer is up. When the drawer has nothing to show (no timer yet, or the
-- game's numbers could not be read) the stock timer stays, so a running timer is never left without a readout
-- (player, Mulgore 2026-11-06: a ten minute quest showed in neither). Its showing is also a cue to read again: a timer
-- can arrive without a quest log event.
local function HookBlizzard()
    local stock = _G.QuestTimerFrame
    if not stock or stock.fsQuestTimerHidden or not stock.HookScript then return end
    stock.fsQuestTimerHidden = true
    stock:HookScript("OnShow", function()
        if not Enabled() then return end
        local ok, err = pcall(QT.Refresh)
        if not ok and FS.LogDegradeOnce then FS.LogDegradeOnce("questtimer", "Quest timer: " .. tostring(err)) end
    end)
end

local function HideBlizzard()
    local stock = _G.QuestTimerFrame
    if stock and stock.IsShown and stock:IsShown() then stock:Hide() end
end

function QT.Refresh()
    local f = Build()
    if not f then return end
    if not Enabled() then
        f:Hide(); StopTicker()
        return
    end
    HookBlizzard()
    QT.Read(GetTime())
    local count = math.min(#timers, MAX_ROWS)
    if count == 0 then
        f:Hide(); StopTicker()
        return
    end
    Seat(f)
    local widthPx = math.floor((f:GetWidth() or 0) / G.px + 0.5)
    if widthPx <= 0 then
        local chassis = ChassisBottom()
        widthPx = math.floor(((chassis and chassis:GetWidth()) or 0) / G.px + 0.5)
    end
    local sig = count .. ":" .. widthPx .. ":" .. G.px
    if laidOutFor ~= sig then
        laidOutFor = sig
        for i = 1, count do
            drawer.rows[i] = drawer.rows[i] or NewRow(f)
            LayoutRow(drawer.rows[i], i, widthPx)
        end
        f:SetHeight((P(D.TOP) + count * P(D.ROW_H) + P(D.BOTTOM)) * G.px)
    end
    for i, row in ipairs(drawer.rows) do row.frame:SetShown(i <= count) end
    f:Show()
    HideBlizzard()
    Paint()
    if not ticker and C_Timer and C_Timer.NewTicker then ticker = C_Timer.NewTicker(0.25, Paint) end
end

local events = CreateFrame("Frame")
for _, e in ipairs({ "PLAYER_ENTERING_WORLD", "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED", "UPDATE_QUEST_TIMERS",
    "UI_SCALE_CHANGED", "DISPLAY_SIZE_CHANGED" }) do
    pcall(events.RegisterEvent, events, e)
end
events:SetScript("OnEvent", function(_, event)
    if event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then laidOutFor = nil end
    local ok, err = pcall(QT.Refresh)
    if not ok and FS.LogDegradeOnce then FS.LogDegradeOnce("questtimer", "Quest timer: " .. tostring(err)) end
end)

if FS.Config and FS.Config.OnChange then
    FS.Config.OnChange(KEY, function()
        QT.Refresh()
        local stock = _G.QuestTimerFrame
        if not Enabled() and stock and type(_G.GetQuestTimers) == "function" and select("#", _G.GetQuestTimers()) > 0 then
            stock:Show()
        end
    end)
end
