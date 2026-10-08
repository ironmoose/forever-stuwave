-- Forever STUwave: Gunsight Class Module for Warlock (soul shards), Rogue and Druid (combo points).
--
-- Registers the module "class" with FS.GunsightAreas, which hosts it in the upper or lower area and calls seat(rect)
-- again on every rescale. Offsets are image px from the area rect's corner (mockups/gunsight-modules-concepts-v7-2026-10-08.html,
-- shardsSlot and comboModule); gunsightclass-harness.py parses them back out of the mockup.

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.G) then return end
if not (Areas and Areas.RegisterModule) then return end

local ui, Point, G = Gunsight.ui, Gunsight.Point, Gunsight.G

local M = {
    LABEL_PX = 10, LABEL_ALPHA = 0.85, LABEL_DX = 7, LABEL_BASE = 14,     -- the violet caption
    GLYPH_DX = 11, GLYPH_DY = 22, GLYPH_W = 16, GLYPH_H = 30,             -- shard glyph box
    NUM_DX = 39, NUM_BASE = 49, NUM_PX = 32,                              -- shard count, left edge and baseline
    PIP_DX = 17, PIP_STEP = 20, PIP_DY = 38, PIP_R = 8,                   -- combo pip centres and half diagonal
    COMBO_NUM_DX = 125,                                                   -- combo count, left edge (same baseline and size)
    TEXT_MID = 0.35,                                                      -- a line's centre sits this fraction of its size above the baseline
    MAX_PIPS = 5,
    CANVAS_W = 16, CANVAS_H = 32, GLOW_CANVAS = 40,                       -- the baked shard files' canvases for a G.SH_W x G.SH_H cell (CombatHud TUNE)
    FILL = { lit = 0.28, off = 0.06 }, LINE = { lit = 1, off = 0.4 }, FACET = { lit = 1, off = 0.2 },
    FACET_MIX = 0.45,                                                     -- facet lines: the violet mixed this far toward white
    PIP_FILL = { lit = 0.9, off = 0.06 }, PIP_RING = { lit = 1, off = 0.4 },
    YELLOW = { 1, 244 / 255, 104 / 255 },                                 -- #fff468
}

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local SHARD_TEX = {
    glow = MEDIA .. "hud_shard_glow.tga", line = MEDIA .. "hud_shard_line.tga",
    fill = MEDIA .. "hud_shard_fill.tga", facet = MEDIA .. "hud_shard_facet.tga",
}
local PIP_FILL_TEX, PIP_RING_TEX = MEDIA .. "hud_diamond.tga", MEDIA .. "glyph_hud_diamond.tga"
local COMBO_EVENTS = { "PLAYER_COMBO_POINTS", "PLAYER_TARGET_CHANGED" }
local DRUID_EVENTS = { "UPDATE_SHAPESHIFT_FORM" }

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightclass_" .. key, "|cffff4488Forever STUwave|r: gunsight class module: " .. tostring(msg))
    end
end

local function IsSecret(v) return FS.IsSecret and FS.IsSecret(v) or false end

local function PlayerClass()
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) or type(token) ~= "string" then return nil end
    return token
end

-- A whole count of at least 0, or nil for anything else (a secret, a string, a NaN).
local function PlainCount(v)
    if IsSecret(v) or type(v) ~= "number" or v ~= v or v < 0 then return nil end
    return math.floor(v)
end

local function Lighten(c, f)
    return { c[1] + (1 - c[1]) * f, c[2] + (1 - c[2]) * f, c[3] + (1 - c[3]) * f }
end

local mode, class, caption    -- what the player's class draws here ("shards", "combo" or nil), its token, the caption text (set at build)
local shown, built, subscribed = false, false, false
local rect                    -- the corner of the area's image px rect, copied from the last seat() (the host reuses its table)
local frame, box, label, number
local glyph, pips = {}, {}
local lastKey                 -- what is painted now: a count, "secret" or "off"; nil forces a repaint

local function Theme() return FS.Theme end

-- A caption or count: its font is set at creation (SetText on a FontString with none throws), its centre
-- sits TEXT_MID of its size above the mockup's baseline.
local function NewText(parent)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs:SetJustifyH("LEFT")
    return fs
end

local function SeatText(fs, px, color, dx, base)
    Theme().ApplyMono(fs, ui(px), color)
    if rect then Point(fs, "LEFT", rect.x + dx, rect.y + base - M.TEXT_MID * px) end
end

local function SeatAll()
    if not built then return end
    local T = Theme()
    SeatText(label, M.LABEL_PX, { T.COLOR_BORDER[1], T.COLOR_BORDER[2], T.COLOR_BORDER[3], M.LABEL_ALPHA },
        M.LABEL_DX, M.LABEL_BASE)
    if mode == "shards" then
        SeatText(number, M.NUM_PX, number.fsColor, M.NUM_DX, M.NUM_BASE)
        if rect then
            local gw, gh = ui(M.GLYPH_W), ui(M.GLYPH_H)
            for name, tex in pairs(glyph) do
                local cw, ch = M.CANVAS_W, M.CANVAS_H
                if name == "glow" then cw, ch = M.GLOW_CANVAS, M.GLOW_CANVAS end
                tex:SetSize(gw * cw / G.SH_W, gh * ch / G.SH_H)
                Point(tex, "CENTER", rect.x + M.GLYPH_DX + M.GLYPH_W / 2, rect.y + M.GLYPH_DY + M.GLYPH_H / 2)
            end
        end
    else
        SeatText(number, M.NUM_PX, number.fsColor, M.COMBO_NUM_DX, M.NUM_BASE)
        if rect then
            for i, pip in ipairs(pips) do
                for _, tex in pairs(pip) do
                    tex:SetSize(ui(2 * M.PIP_R), ui(2 * M.PIP_R))
                    Point(tex, "CENTER", rect.x + M.PIP_DX + (i - 1) * M.PIP_STEP, rect.y + M.PIP_DY)
                end
            end
        end
    end
end

-- The count's colour: white while something is held, muted at 0. SeatText re-applies it after a rescale.
local function SetNumberColor(lit)
    local c = lit and Theme().COLOR_TEXT_WHITE or Theme().COLOR_MUTED
    number.fsColor = c
    number:SetTextColor(c[1], c[2], c[3], c[4] or 1)
end

-- The count goes to the string through SetFormattedText, which accepts a secret.
local function SetNumber(value)
    local ok = pcall(number.SetFormattedText, number, "%d", value)
    if not ok then LogOnce("number", "SetFormattedText refused the count") end
end

local function Paint(key)
    if key == lastKey and key ~= "secret" then return end
    lastKey = key
    box:SetShown(key ~= "off")
end

-------------------------------------------------------------------------------
-- Shards
-------------------------------------------------------------------------------

local function BuildShards()
    local violet = Theme().COLOR_BORDER
    local facet = Lighten(violet, M.FACET_MIX)
    local specs = {
        { "glow", "BACKGROUND", 0, violet }, { "line", "ARTWORK", 0, violet },
        { "fill", "ARTWORK", 1, violet }, { "facet", "ARTWORK", 2, facet },
    }
    for _, s in ipairs(specs) do
        local tex = box:CreateTexture(nil, s[2], nil, s[3])
        tex:SetTexture(SHARD_TEX[s[1]])
        tex:SetVertexColor(s[4][1], s[4][2], s[4][3], 1)
        glyph[s[1]] = tex
    end
    caption = "SOUL SHARDS"
end

local function PaintShards(n)
    local lit = n > 0
    local state = lit and "lit" or "off"
    local violet, facet = Theme().COLOR_BORDER, Lighten(Theme().COLOR_BORDER, M.FACET_MIX)
    glyph.glow:SetShown(lit)
    glyph.line:SetVertexColor(violet[1], violet[2], violet[3], M.LINE[state])
    glyph.fill:SetVertexColor(violet[1], violet[2], violet[3], M.FILL[state])
    glyph.facet:SetVertexColor(facet[1], facet[2], facet[3], M.FACET[state])
    SetNumberColor(lit)
    SetNumber(n)
end

local function OnHudState(state)
    if not built or mode ~= "shards" then return end
    local n = type(state) == "table" and PlainCount(state.shards) or nil
    if n == nil then
        Paint("off")
    else
        if n ~= lastKey then PaintShards(n) end
        Paint(n)
    end
end

-------------------------------------------------------------------------------
-- Combo points
-------------------------------------------------------------------------------

local function BuildCombo()
    local y = M.YELLOW
    for i = 1, M.MAX_PIPS do
        local fill = box:CreateTexture(nil, "ARTWORK", nil, 0)
        fill:SetTexture(PIP_FILL_TEX)
        fill:SetVertexColor(y[1], y[2], y[3], M.PIP_FILL.off)
        local ring = box:CreateTexture(nil, "ARTWORK", nil, 1)
        ring:SetTexture(PIP_RING_TEX)
        ring:SetVertexColor(y[1], y[2], y[3], M.PIP_RING.off)
        pips[i] = { fill = fill, ring = ring }
    end
    caption = "COMBO POINTS"
end

local function SetPips(n)
    local y = M.YELLOW
    for i, pip in ipairs(pips) do
        local state = i <= n and "lit" or "off"
        pip.fill:SetVertexColor(y[1], y[2], y[3], M.PIP_FILL[state])
        pip.ring:SetVertexColor(y[1], y[2], y[3], M.PIP_RING[state])
        pip.fill:Show()
        pip.ring:Show()
    end
end

local function HidePips()
    for _, pip in ipairs(pips) do
        pip.fill:Hide()
        pip.ring:Hide()
    end
end

-- Whether the Druid is in cat form: energy is its power type there (mana, rage and the other forms differ).
-- nil when the API is missing or the answer is secret, which draws nothing.
local function InCatForm()
    if type(UnitPowerType) ~= "function" then return nil end
    local ok, powerType, token = pcall(UnitPowerType, "player")
    if not ok or IsSecret(powerType) or IsSecret(token) then return nil end
    return token == "ENERGY" or powerType == 3
end

-- Combo points belong to a live hostile target; the shared FS.TargetTakesDots rule answers true when it cannot tell.
local function TargetTakesPoints()
    if type(FS.TargetTakesDots) ~= "function" then return true end
    local ok, takes = pcall(FS.TargetTakesDots)
    return not ok or takes ~= false
end

local function ComboActive()
    if class == "DRUID" and InCatForm() ~= true then return false end
    return TargetTakesPoints()
end

local function RefreshCombo()
    if not built or mode ~= "combo" or not shown then return end
    if type(GetComboPoints) ~= "function" or not ComboActive() then
        Paint("off")
        return
    end
    local ok, value = pcall(GetComboPoints, "player", "target")
    if not ok then
        Paint("off")
        return
    end
    if IsSecret(value) then
        HidePips()
        SetNumberColor(true)
        SetNumber(value)
        lastKey = nil
        Paint("secret")
        return
    end
    local n = PlainCount(value)
    if n == nil then
        Paint("off")
        return
    end
    n = math.min(n, M.MAX_PIPS)
    if n ~= lastKey then
        SetPips(n)
        SetNumberColor(n > 0)
        SetNumber(n)
    end
    Paint(n)
end

local function OnComboEvent(_, event, unit, token)
    if event == "UNIT_POWER_UPDATE" and not IsSecret(token) and token ~= nil and token ~= "COMBO_POINTS" then return end
    RefreshCombo()
end

local function SetComboEvents(on)
    local function reg(event, unitOnly)
        if on then
            local ok, err
            if unitOnly then
                ok, err = pcall(frame.RegisterUnitEvent, frame, event, "player")
            else
                ok, err = pcall(frame.RegisterEvent, frame, event)
            end
            if not ok then LogOnce("event_" .. event, event .. " cannot be registered on this client (" .. tostring(err) .. ")") end
        else
            pcall(frame.UnregisterEvent, frame, event)
        end
    end
    for _, e in ipairs(COMBO_EVENTS) do reg(e) end
    reg("UNIT_POWER_UPDATE", true)
    if class == "DRUID" then
        for _, e in ipairs(DRUID_EVENTS) do reg(e) end
        reg("UNIT_DISPLAYPOWER", true)
    end
    frame:SetScript("OnEvent", on and OnComboEvent or nil)
end

-------------------------------------------------------------------------------
-- The module
-------------------------------------------------------------------------------

local function Build(host)
    frame = CreateFrame("Frame", nil, host)
    frame:SetAllPoints(host)
    built = false
    class = PlayerClass()
    mode = (class == "WARLOCK" and "shards") or ((class == "ROGUE" or class == "DRUID") and "combo") or nil
    if not mode then return frame end
    box = CreateFrame("Frame", nil, frame)
    box:SetAllPoints(frame)
    box:Hide()
    label = NewText(box)
    number = NewText(box)
    number.fsColor = Theme().COLOR_MUTED
    if mode == "shards" then BuildShards() else BuildCombo() end
    built = true
    SeatAll()
    label:SetText(caption)
    return frame
end

local function Seat(r)
    if type(r) ~= "table" or type(r.x) ~= "number" or type(r.y) ~= "number" then return end
    rect = { x = r.x, y = r.y }
    local ok, err = pcall(SeatAll)
    if not ok then LogOnce("seat", err) end
end

local function OnShow()
    shown = true
    lastKey = nil
    if not built then return end
    if mode == "shards" then
        local Hud = FS.Hud
        if not (Hud and Hud.Subscribe) then
            LogOnce("nohud", "FS.Hud is missing, the shard count has no data")
            return
        end
        if not subscribed then
            subscribed = true
            Hud.Subscribe(OnHudState)
        end
    else
        SetComboEvents(true)
        RefreshCombo()
    end
end

local function OnHide()
    shown = false
    if not built then return end
    if mode == "shards" then
        if subscribed and FS.Hud and FS.Hud.Unsubscribe then FS.Hud.Unsubscribe(OnHudState) end
        subscribed = false
    else
        SetComboEvents(false)
    end
    lastKey = nil
end

local ok, result = pcall(Areas.RegisterModule, "class", {
    classes = { "WARLOCK", "ROGUE", "DRUID" },
    build = Build, seat = Seat, onShow = OnShow, onHide = OnHide,
})
if not ok or not result then LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")") end

-------------------------------------------------------------------------------
-- Coming soon: the fallback for a class with no class module
-------------------------------------------------------------------------------
-- Registered as "classSoon", which GunsightAreas shows in an area set to the Class Module whenever no spec above
-- lists the player's class. A class that gains a module stops showing it with no change here. A small dim plate in
-- the empty slot's language (violet wash, violet edge, muted text; mockup emptySlot) with the class caption's
-- header style; a plain frame, so a refresh in combat is never blocked.

local SOON = {
    DX = 0, DY = 2, W = 118, H = 46,               -- the plate, image px from the area rect's corner
    EDGE = 1, EDGE_ALPHA = 0.4, WASH_ALPHA = 0.04, -- 1 image px edge, the emptySlot violet wash
    HDR_PX = 10, HDR_ALPHA = 0.9, HDR_DX = 7, HDR_BASE = 14,   -- the TARGET DEBUFFS header style
    MAIN_PX = 13, MAIN_ALPHA = 0.8, MAIN_DX = 7, MAIN_BASE = 31,
    NAME_PX = 10, NAME_ALPHA = 0.6, NAME_DX = 7, NAME_BASE = 43,
    HEADER = "CLASS MODULE", MAIN = "COMING SOON",
}

local soonRect, soonFrame, soonBuilt           -- the corner of the last seat() rect, the plate frame
local soonWash, soonEdge, soonHdr, soonMain, soonName, soonNamed = nil, {}, nil, nil, nil, false

-- The localized class name, or nil when it cannot be read as a plain string.
local function ClassName()
    if type(UnitClass) ~= "function" then return nil end
    local ok, name = pcall(UnitClass, "player")
    if not ok or IsSecret(name) or type(name) ~= "string" or name == "" then return nil end
    return name
end

local function SoonText(fs, px, color, alpha, dx, base)
    Theme().ApplyMono(fs, ui(px), { color[1], color[2], color[3], alpha })
    if soonRect then Point(fs, "LEFT", soonRect.x + dx, soonRect.y + base - M.TEXT_MID * px) end
end

local function SoonSeatAll()
    if not soonBuilt then return end
    local T = Theme()
    if soonRect then
        local x, y, w, h, e = soonRect.x + SOON.DX, soonRect.y + SOON.DY, SOON.W, SOON.H, SOON.EDGE
        local function place(tex, tx, ty, tw, th)
            Point(tex, "TOPLEFT", tx, ty)
            tex:SetSize(ui(tw), ui(th))
        end
        place(soonWash, x, y, w, h)
        place(soonEdge.top, x, y, w, e)
        place(soonEdge.bottom, x, y + h - e, w, e)
        place(soonEdge.left, x, y, e, h)
        place(soonEdge.right, x + w - e, y, e, h)
    end
    SoonText(soonHdr, SOON.HDR_PX, T.COLOR_BORDER, SOON.HDR_ALPHA, SOON.HDR_DX, SOON.HDR_BASE)
    SoonText(soonMain, SOON.MAIN_PX, T.COLOR_MUTED, SOON.MAIN_ALPHA, SOON.MAIN_DX, SOON.MAIN_BASE)
    if soonNamed then SoonText(soonName, SOON.NAME_PX, T.COLOR_MUTED, SOON.NAME_ALPHA, SOON.NAME_DX, SOON.NAME_BASE) end
end

local function SoonBuild(host)
    soonFrame = CreateFrame("Frame", nil, host)
    soonFrame:SetAllPoints(host)
    soonBuilt = false
    local violet = Theme().COLOR_BORDER
    soonWash = soonFrame:CreateTexture(nil, "BACKGROUND")
    soonWash:SetColorTexture(violet[1], violet[2], violet[3], SOON.WASH_ALPHA)
    for _, side in ipairs({ "top", "bottom", "left", "right" }) do
        local tex = soonFrame:CreateTexture(nil, "BORDER")
        tex:SetColorTexture(violet[1], violet[2], violet[3], SOON.EDGE_ALPHA)
        soonEdge[side] = tex
    end
    soonHdr, soonMain, soonName = NewText(soonFrame), NewText(soonFrame), NewText(soonFrame)
    local name = ClassName()
    soonNamed = name ~= nil
    soonBuilt = true
    SoonSeatAll()          -- sets each font; SetText on a FontString with none throws
    soonHdr:SetText(SOON.HEADER)
    soonMain:SetText(SOON.MAIN)
    if soonNamed then soonName:SetText(name) else soonName:Hide() end
    return soonFrame
end

local function SoonSeat(r)
    if type(r) ~= "table" or type(r.x) ~= "number" or type(r.y) ~= "number" then return end
    soonRect = { x = r.x, y = r.y }
    local ok, err = pcall(SoonSeatAll)
    if not ok then LogOnce("soon_seat", err) end
end

local okSoon, resultSoon = pcall(Areas.RegisterModule, "classSoon", { build = SoonBuild, seat = SoonSeat })
if not okSoon or not resultSoon then
    LogOnce("register_soon", "FS.GunsightAreas.RegisterModule refused the coming soon plate (" .. tostring(resultSoon) .. ")")
end
