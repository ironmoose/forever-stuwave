-- Forever STUwave: Config page, Nameplates
-- Four tabs (Size, Text, Parts, Friendly), each with the same pinned preview band on top: four plates (a neutral one with a
-- quest marker, the target with auras, a power bar, a cast bar and combo points, one with a raid marker, a friendly one)
-- drawn from the measures and colours Nameplates.lua exports (FS.Nameplates.GEOMETRY and PALETTE) and from the settings as
-- they are now, so the band follows every change at once. Hovering a row shows the part that row changes, switched on for the
-- moment and pulsing, and puts everything back when the pointer leaves.
-- Out of the page when the client has no nameplate API, where Nameplates.lua exports nothing.

local _, FS = ...

local CW = FS.ConfigWindow
local UI, I, C, S, D = CW.UI, CW.I, CW.C, CW.Spec, CW.D
local Theme = FS.Theme

-- The preview's own layout (screen units, before the fit scale): the stage the plates stand on and what the plate module does
-- not export. The prototype's measures (mockups/proto-src-2026-11-25/plates.js).
local TITLE_H = 20          -- the PREVIEW tag row
local TITLE_GAP = 4         -- tag row to stage
local STAGE_H = 104         -- the stage, border included
local BAND_H = TITLE_H + TITLE_GAP + STAGE_H
local STAGE_PAD_X = 10      -- stage edge to the first and last plate
local STAGE_PAD_Y = 4       -- stage edge to the tallest plate, top and bottom
local PLATE_GAP = 26        -- between plates
local PIP_W, PIP_H, PIP_GAP, PIP_TOP = 8, 4, 3, 3   -- combo points: one pip, between pips, below the cast bar slot
local ICON_FILL = { 0.23, 0.11, 0.37, 1 }           -- an aura icon's body
local PIP_REST = { 0.165, 0.094, 0.251, 1 }
local STAGE_FILL = { 0.075, 0.035, 0.14, 1 }
local PULSE_PERIOD, PULSE_LOW = 0.8, 0.4            -- a pulsing part swings between full and this share of its alpha
local SKULL = { 0.75, 1, 0.25, 0.5 }                -- the raid marker's texcoords in UI-RaidTargetingIcons
local RAID_ICONS = "Interface\\TargetingFrame\\UI-RaidTargetingIcons"

-- The four plates, left to right. `fill` and `name` pick a palette colour; hp is the fill share; `power`, `cast`, `combo`,
-- `tmark` ride only the target.
local PLATES = {
    { name = "Gizmo", level = "20", fill = "neutral", hp = 100, quest = true, dim = true },
    { name = "Biff Tannen", level = "22", fill = "hostile", hp = 64, target = true, auras = { "own", "own", "other" },
        power = 72, cast = "Hadouken" },
    { name = "Gruber", level = "21+", fill = "hostile", hp = 88, mark = true, auras = { "other" }, dim = true },
    { name = "Marty", fill = "friend", hp = 93, friendly = true, dim = true },
}

-- Hover: values forced on for the moment (what shows) and the parts that pulse (what the row changes).
local PEEK_ON = {
    ["plates.quest"] = "quest", ["plates.auras"] = "auras", ["plates.raidMark"] = "raidMark", ["plates.level"] = "level",
    ["nameplates.comboPips"] = "combo", ["nameplates.targetMark"] = "targetMark",
}
local PEEK_FROM_ZERO = { ["plates.castH"] = "castH", ["plates.mpH"] = "mpH" }
local PULSES = {
    ["plates.quest"] = { "quest" }, ["plates.auras"] = { "aura" }, ["plates.raidMark"] = { "mark" },
    ["plates.level"] = { "name" }, ["plates.nameSize"] = { "name" }, ["plates.hpText"] = { "hptext" },
    ["plates.castH"] = { "cast" }, ["plates.mpH"] = { "power" }, ["nameplates.comboPips"] = { "combo" },
    ["nameplates.targetMark"] = { "tmark" }, ["plates.friendly"] = { "plate", plate = 4 },
}

local Pv = { tabs = {} }   -- tab key -> its band record

-- A stored value as the plates read it: the module's rules (range, step, options), the default for anything else.
local function Clean(def, value)
    if type(def.default) == "number" then
        if type(value) ~= "number" or value ~= value then value = def.default end
        value = math.max(def.min, math.min(def.max, value))
        return math.min(def.max, def.min + math.floor((value - def.min) / def.step + 0.5) * def.step)
    elseif type(def.default) == "boolean" then
        if type(value) ~= "boolean" then return def.default end
        return value
    end
    for _, option in ipairs(def.options or {}) do
        if option.value == value then return value end
    end
    return def.default
end

-- Every setting the preview draws from, with the hovered row's peek laid over it.
local function Values(peek)
    local N, v = FS.Nameplates, {}
    for field, def in pairs(N.SETTINGS) do v[field] = Clean(def, FS.Config.Get(def.key)) end
    local mark = N.TARGET_MARK_SETTING
    v.targetMark = (mark and FS.Config.Get(mark.key) == true) or false
    local combo = FS.NameplateCombo and FS.NameplateCombo.SETTING
    v.combo = (combo and FS.Config.Get(combo.key) ~= false) or false
    if peek then
        local field = PEEK_ON[peek]
        if field == "combo" and not combo then field = nil end
        if field then v[field] = true end
        field = PEEK_FROM_ZERO[peek]
        if field and v[field] == 0 then v[field] = N.SETTINGS[field].default end
        if peek == "plates.hpText" and v.hpText == "none" then v.hpText = "percent" end
        if peek == "plates.friendly" and v.friendly == "off" then v.friendly = "same" end
    end
    return v
end

local function HealthText(mode, hp)
    local cur = math.floor(hp * 31 + 0.5)
    if mode == "percent" then return hp .. "%" end
    if mode == "number" then return cur .. " / 3100" end
    if mode == "both" then return cur .. "  " .. hp .. "%" end
    return ""
end

local function Tag(rec, object, part, plate, base)
    object.fsPart, object.fsPlate, object.fsBase = part, plate, base or 1
    rec.parts[#rec.parts + 1] = object
    return object
end

local function Fill(frame, color, layer)
    local t = frame:CreateTexture(nil, layer or "BACKGROUND")
    t:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
    return t
end

local function Text(frame, size, color, outline)
    local fs = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyFontGeneric(fs, Theme.FONT_MONO, size, color, outline and "OUTLINE" or "")
    fs:SetText("")
    return fs
end

local function At(object, point, rel, relPoint, x, y)
    object:ClearAllPoints()
    object:SetPoint(point, rel, relPoint, x or 0, y or 0)
end

-- One plate's frames, built once; Render sizes, seats and shows them.
local function BuildPlate(rec, stage, index, spec)
    local P = { spec = spec }
    local pf = Tag(rec, CreateFrame("Frame", nil, stage), "plate", index, spec.dim and 0.75 or 1)
    pf:SetFrameLevel(stage:GetFrameLevel() + 1)
    P.pf = pf
    P.glow = Fill(pf, C.violet, "BACKGROUND")
    local box = Tag(rec, CreateFrame("Frame", nil, pf), "box", index)
    P.box = box
    P.chrome = Fill(box, Theme.COLOR_BG, "BACKGROUND")
    P.chrome:SetAllPoints(box)
    P.edges = I.Outline(box, Theme.COLOR_BORDER, 1)
    local bar = Tag(rec, CreateFrame("Frame", nil, box), "bar", index)
    P.bar = bar
    local track = Fill(bar, Theme.COLOR_BAR_TRACK, "BACKGROUND")
    track:SetAllPoints(bar)
    P.fill = Fill(bar, C.pink, "ARTWORK")
    P.caret = Fill(bar, Theme.COLOR_CARET_HEALTH, "OVERLAY")
    P.hptext = Tag(rec, Text(bar, rec.G.HP_TEXT_SIZE, FS.Nameplates.PALETTE.text, true), "hptext", index)
    -- the parts that stand above the bar draw over the chrome
    local over = CreateFrame("Frame", nil, pf)
    over:SetFrameLevel(box:GetFrameLevel() + 4)
    P.over = over
    P.name = Tag(rec, Text(over, 10, FS.Nameplates.PALETTE.text, true), "name", index)
    if spec.quest then P.quest = Tag(rec, Text(over, rec.G.QUEST_SIZE, FS.Nameplates.PALETTE.quest, true), "quest", index) end
    if spec.mark then
        P.mark = Tag(rec, over:CreateTexture(nil, "OVERLAY"), "mark", index)
        P.mark:SetTexture(RAID_ICONS)
        P.mark:SetTexCoord(SKULL[1], SKULL[2], SKULL[3], SKULL[4])
        P.mark:SetSize(rec.G.RAID_SIZE, rec.G.RAID_SIZE)
    end
    P.auras = {}
    for k, kind in ipairs(spec.auras or {}) do
        local icon = Tag(rec, CreateFrame("Frame", nil, over), "aura", index)
        icon:SetSize(rec.G.AURA_SIZE, rec.G.AURA_SIZE)
        Fill(icon, ICON_FILL, "BACKGROUND"):SetAllPoints(icon)
        I.Outline(icon, kind == "own" and Theme.COLOR_HEALTH or Theme.COLOR_BORDER, 1)
        P.auras[k] = icon
    end
    if spec.power then
        local power = Tag(rec, CreateFrame("Frame", nil, box), "power", index)
        Fill(power, Theme.COLOR_BAR_TRACK, "BACKGROUND"):SetAllPoints(power)
        P.power = power
        P.powerFill = Fill(power, Theme.COLOR_POWER, "ARTWORK")
    end
    if spec.cast then
        local cast = Tag(rec, CreateFrame("Frame", nil, pf), "cast", index)
        Fill(cast, Theme.COLOR_BAR_TRACK, "BACKGROUND"):SetAllPoints(cast)
        I.Outline(cast, Theme.COLOR_BAR_BORDER, 1)
        P.cast = cast
        P.castFill = Fill(cast, Theme.COLOR_CAST_INTERRUPTIBLE or Theme.COLOR_POWER, "ARTWORK")
        P.castName = Text(cast, rec.G.CAST_NAME_SIZE, FS.Nameplates.PALETTE.text, true)
        P.castName:SetText(spec.cast)
    end
    if spec.target then
        local combo = Tag(rec, CreateFrame("Frame", nil, pf), "combo", index)
        combo:SetSize(5 * PIP_W + 4 * PIP_GAP, PIP_H)
        P.combo, P.pips = combo, {}
        for k = 1, 5 do P.pips[k] = Fill(combo, k <= 3 and Theme.COLOR_HEALTH or PIP_REST, "ARTWORK") end
        local tmark = Tag(rec, CreateFrame("Frame", nil, over), "tmark", index)
        tmark:SetSize(3 * rec.G.MARK_W, rec.G.MARK_H)
        P.tmark, P.blocks = tmark, {}
        for k, rgb in ipairs(FS.Nameplates.PALETTE.targetMark or {}) do
            local block = Fill(tmark, { rgb[1], rgb[2], rgb[3], 1 }, "ARTWORK")
            block:SetSize(rec.G.MARK_W, rec.G.MARK_H)
            block:SetPoint("LEFT", tmark, "LEFT", (k - 1) * rec.G.MARK_W, 0)
            P.blocks[k] = block
        end
    end
    return P
end

local function Show(object, on)
    if object then object:SetShown(on and true or false) end
end

local function FillColor(spec)
    local palette = FS.Nameplates.PALETTE
    if spec.fill == "neutral" then return palette.fillNeutral end
    if spec.fill == "friend" then return palette.fillFriend end
    return Theme.COLOR_HEALTH
end

local function NameColor(spec)
    local palette = FS.Nameplates.PALETTE
    if spec.fill == "neutral" then return palette.nameNeutral or palette.text end
    if spec.fill == "friend" then return palette.nameFriendly or palette.text end
    return palette.nameHostile or palette.text
end

-- Sizes, seats and shows everything for the settings as they are (with the peek laid over them).
local function Render(rec)
    local N = FS.Nameplates
    local G = rec.G
    local v = Values(rec.peek)
    local castGap = math.max(G.CAST_GAP, (Theme.SLICE_GLOW_PAD or 0))
    local markY = G.MARK_Y[v.nameSize] or G.MARK_Y[10] or 46
    local aboveH = markY + G.MARK_H - G.PAD
    local boxW = v.w + 2 * G.PAD
    local boxHNatural = v.hpH + 2 * G.PAD + (v.mpH > 0 and (G.POWER_GAP + v.mpH) or 0)
    local belowNatural = castGap + v.castH + PIP_TOP + PIP_H
    local natW = #PLATES * boxW + (#PLATES - 1) * PLATE_GAP
    local natH = aboveH + boxHNatural + belowNatural
    local innerW = D.CONTENT_W - 2 - 2 * STAGE_PAD_X
    local innerH = STAGE_H - 2 - 2 * STAGE_PAD_Y
    local fit = math.min(1, innerW / natW, innerH / natH)
    rec.fit = fit

    local pulse, pulsePlate = {}, nil
    local group = rec.peek and PULSES[rec.peek]
    if group then
        for _, name in ipairs(group) do pulse[name] = true end
        pulsePlate = group.plate
    end

    -- which plates are up, and the row's width, so it stands centred
    local scales, total, count = {}, 0, 0
    for i, spec in ipairs(PLATES) do
        local scale = fit
        if spec.friendly and v.friendly == "smaller" then scale = fit * G.SMALL_SCALE end
        scales[i] = scale
        if not (spec.friendly and v.friendly == "off") then
            total = total + boxW * scale
            count = count + 1
        end
    end
    total = total + math.max(0, count - 1) * PLATE_GAP * fit
    local x = 1 + (innerW + 2 * STAGE_PAD_X - 2 - total) / 2
    local boxTop = 1 + STAGE_PAD_Y + (innerH - natH * fit) / 2 + aboveH * fit

    for _, object in ipairs(rec.parts) do
        object.fsPulse = false
        object:SetAlpha(object.fsBase)
    end

    for i, P in ipairs(rec.plates) do
        local spec, scale = P.spec, scales[i]
        local up = not (spec.friendly and v.friendly == "off")
        local power = spec.power and v.mpH > 0
        local boxH = v.hpH + 2 * G.PAD + (power and (G.POWER_GAP + v.mpH) or 0)
        local hostile = spec.fill == "hostile"
        local pf = P.pf
        pf.fsScale = scale
        pf:SetScale(scale)
        pf:SetShown(up)
        pf:SetSize(boxW, aboveH + boxH + belowNatural)
        pf:ClearAllPoints()
        pf:SetPoint("TOPLEFT", rec.stage, "TOPLEFT", x / scale, -(boxTop - aboveH * scale) / scale)
        if up then x = x + boxW * scale + PLATE_GAP * fit end

        At(P.box, "TOPLEFT", pf, "TOPLEFT", 0, -aboveH)
        P.box:SetSize(boxW, boxH)
        local glowAlpha = spec.target and (hostile and G.GLOW_TARGET_HOSTILE or G.GLOW_TARGET)
            or (hostile and G.GLOW_HOSTILE or G.GLOW_REST)
        local reach = spec.target and 4 or 3
        local glow = hostile and Theme.COLOR_HEALTH or Theme.COLOR_BORDER
        P.glow:SetColorTexture(glow[1], glow[2], glow[3], glowAlpha * 0.45)
        P.glow:ClearAllPoints()
        P.glow:SetPoint("TOPLEFT", P.box, "TOPLEFT", -reach, reach)
        P.glow:SetPoint("BOTTOMRIGHT", P.box, "BOTTOMRIGHT", reach, -reach)

        At(P.bar, "TOPLEFT", P.box, "TOPLEFT", G.PAD, -G.PAD)
        P.bar:SetSize(v.w, v.hpH)
        local fillW = math.max(1, math.floor(v.w * spec.hp / 100 + 0.5))
        local color = FillColor(spec)
        P.fill:SetColorTexture(color[1], color[2], color[3], 1)
        P.fill:ClearAllPoints()
        P.fill:SetPoint("TOPLEFT", P.bar, "TOPLEFT", 0, 0)
        P.fill:SetSize(fillW, v.hpH)
        P.caret:ClearAllPoints()
        P.caret:SetPoint("TOPLEFT", P.bar, "TOPLEFT", fillW - 1, 0)
        P.caret:SetSize(1, v.hpH)
        At(P.hptext, "CENTER", P.bar, "CENTER", 0, 0)
        P.hptext:SetText(HealthText(v.hpText == "none" and "" or v.hpText, spec.hp))
        Show(P.hptext, v.hpText ~= "none")

        local nameColor = NameColor(spec)
        Theme.ApplyFontGeneric(P.name, Theme.FONT_MONO, v.nameSize, nameColor, "OUTLINE")
        P.name:SetText((v.level and spec.level and (spec.level .. " ") or "") .. spec.name)
        At(P.name, "BOTTOMLEFT", P.bar, "TOPLEFT", 0, G.NAME_Y)
        if P.quest then
            At(P.quest, "RIGHT", P.name, "LEFT", -G.QUEST_GAP, 0)
            P.quest:SetText("!")
            Show(P.quest, v.quest)
        end
        if P.mark then
            At(P.mark, "BOTTOM", P.name, "TOP", 0, G.RAID_GAP)
            Show(P.mark, v.raidMark)
        end
        for k, icon in ipairs(P.auras) do
            At(icon, "BOTTOMRIGHT", P.bar, "TOPRIGHT", -(k - 1) * (G.AURA_SIZE + G.AURA_GAP), G.AURA_Y)
            Show(icon, v.auras)
        end
        if P.power then
            At(P.power, "TOPLEFT", P.bar, "BOTTOMLEFT", 0, -G.POWER_GAP)
            P.power:SetSize(v.w, math.max(1, v.mpH))
            P.powerFill:ClearAllPoints()
            P.powerFill:SetPoint("TOPLEFT", P.power, "TOPLEFT", 0, 0)
            P.powerFill:SetSize(math.max(1, math.floor(v.w * spec.power / 100 + 0.5)), math.max(1, v.mpH))
            Show(P.power, power)
        end
        if P.cast then
            local width = v.w + 2
            At(P.cast, "TOPLEFT", P.box, "BOTTOMLEFT", G.PAD - 1, -castGap)
            P.cast:SetSize(width, math.max(1, v.castH))
            P.castFill:ClearAllPoints()
            P.castFill:SetPoint("TOPLEFT", P.cast, "TOPLEFT", 1, -1)
            P.castFill:SetSize(math.max(1, math.floor((width - 2) * 0.55)), math.max(1, v.castH - 2))
            At(P.castName, "LEFT", P.cast, "LEFT", 2, 0)
            Show(P.cast, v.castH > 0)
        end
        if P.combo then
            At(P.combo, "TOP", P.box, "BOTTOM", 0, -(castGap + v.castH + PIP_TOP))
            for k, pip in ipairs(P.pips) do
                pip:ClearAllPoints()
                pip:SetPoint("LEFT", P.combo, "LEFT", (k - 1) * (PIP_W + PIP_GAP), 0)
                pip:SetSize(PIP_W, PIP_H)
            end
            Show(P.combo, v.combo)
            At(P.tmark, "BOTTOM", P.bar, "TOP", 0, markY)
            Show(P.tmark, v.targetMark)
        end
        At(P.over, "TOPLEFT", pf, "TOPLEFT", 0, 0)
        P.over:SetSize(boxW, aboveH + boxH)
    end

    for _, object in ipairs(rec.parts) do
        if pulse[object.fsPart] and (pulsePlate == nil or object.fsPlate == pulsePlate) then object.fsPulse = true end
    end
end

-- The pulse: every flagged part swings between full alpha and PULSE_LOW of it, while a row is hovered.
local function Pulse(rec, elapsed)
    rec.clock = (rec.clock or 0) + (elapsed or 0)
    local wave = 0.5 + 0.5 * math.cos(rec.clock * 2 * math.pi / PULSE_PERIOD)
    local k = PULSE_LOW + (1 - PULSE_LOW) * wave
    for _, object in ipairs(rec.parts) do
        if object.fsPulse then object:SetAlpha(object.fsBase * k) end
    end
end

local function Peek(rec, key)
    if rec.peek == key then return end
    rec.peek = key
    rec.band.fsPeek = key
    Render(rec)
    if key and PULSES[key] then
        rec.clock = 0
        rec.band:SetScript("OnUpdate", function(_, elapsed) Pulse(rec, elapsed) end)
    else
        rec.band:SetScript("OnUpdate", nil)
    end
end

local function Redraw()
    for _, rec in pairs(Pv.tabs) do Render(rec) end
end

-- The settings the band follows: the page's own, the target mark and the combo points.
local function Listen()
    if Pv.listening or not (FS.Config and FS.Config.OnChange) then return end
    Pv.listening = true
    local N = FS.Nameplates
    for _, def in pairs(N.SETTINGS) do FS.Config.OnChange(def.key, Redraw) end
    if N.TARGET_MARK_SETTING then FS.Config.OnChange(N.TARGET_MARK_SETTING.key, Redraw) end
    local combo = FS.NameplateCombo and FS.NameplateCombo.SETTING
    if combo then FS.Config.OnChange(combo.key, Redraw) end
    CW.On("rowEnter", function(entry)
        if entry.page ~= "plates" then return end
        local rec = Pv.tabs[entry.tab]
        if rec then Peek(rec, entry.key) end
    end)
    CW.On("rowLeave", function(entry)
        for _, rec in pairs(Pv.tabs) do
            if rec.peek == entry.key then Peek(rec, nil) end
        end
    end)
    CW.On("hide", function()
        for _, rec in pairs(Pv.tabs) do Peek(rec, nil) end
    end)
    CW.On("select", function()
        for _, rec in pairs(Pv.tabs) do Peek(rec, nil) end
    end)
end

-- The band on top of one tab. Nothing is drawn when the plate module offers no measures to draw from.
local function Preview(content, tab)
    local N = FS.Nameplates
    if not (N and N.SETTINGS and N.GEOMETRY and N.PALETTE) then return end
    local band = UI.Band(content, BAND_H)
    if not band then return end
    band.fsPlatesTab = tab
    local rec = { tab = tab, band = band, parts = {}, plates = {}, G = N.GEOMETRY }
    local title = I.Label(band, "PREVIEW", S.SMALL, C.muted)
    title:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -4)
    local icon = UI.HelpIcon(band, "The plates as your settings draw them. Point at a setting to see the part it changes, "
        .. "shown for a moment and pulsing.")
    icon:SetPoint("LEFT", title, "RIGHT", S.Q_GAP, 0)
    local stage = CreateFrame("Frame", nil, band)
    stage:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -(TITLE_H + TITLE_GAP))
    stage:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, -(TITLE_H + TITLE_GAP))
    stage:SetHeight(STAGE_H)
    if stage.SetClipsChildren then stage:SetClipsChildren(true) end
    Fill(stage, STAGE_FILL, "BACKGROUND"):SetAllPoints(stage)
    I.Outline(stage, C.line, 1)
    rec.stage = stage
    for index, spec in ipairs(PLATES) do rec.plates[index] = BuildPlate(rec, stage, index, spec) end
    Pv.tabs[tab] = rec
    band:SetScript("OnSizeChanged", function() Render(rec) end)
    Listen()
    Render(rec)
    return rec
end

local function SliderRow(content, field, label, unit, tip)
    local def = FS.Nameplates.SETTINGS[field]
    if not def then return end
    UI.Slider(content, {
        label = label, key = def.key, min = def.min, max = def.max, step = def.step, fmt = "%d " .. unit, tip = tip,
    })
end

local function ToggleRow(content, field, label, tip)
    local def = FS.Nameplates.SETTINGS[field]
    if not def then return end
    UI.Toggle(content, { label = label, key = def.key, tip = tip })
end

local function SegmentedRow(content, field, label, tip)
    local def = FS.Nameplates.SETTINGS[field]
    if not def then return end
    UI.Segmented(content, { label = label, key = def.key, options = def.options, tip = tip })
end

local function Ready()
    local N = FS.Nameplates
    return N and N.SETTINGS and true or false
end

CW.RegisterCategory({
    key = "plates", label = "Nameplates", group = "FRAMES", order = 6,
    tabs = {
        { key = "size", label = "Size", build = function(content)
            if not Ready() then return end
            Preview(content, "size")
            UI.Section(content, { title = "Enemy plates" })
            SliderRow(content, "w", "Plate width", "px")
            SliderRow(content, "hpH", "Health bar height", "px")
            SliderRow(content, "mpH", "Power bar height", "px", "0 hides the power bar.")
            SliderRow(content, "castH", "Cast bar height", "px", "0 hides the cast bar.")
        end },
        { key = "text", label = "Text", build = function(content)
            if not Ready() then return end
            Preview(content, "text")
            UI.Section(content, { title = "Text" })
            SliderRow(content, "nameSize", "Name size", "pt")
            ToggleRow(content, "level", "Level")
            SegmentedRow(content, "hpText", "Health text")
        end },
        { key = "parts", label = "Parts", build = function(content)
            local N = FS.Nameplates
            local setting = N and N.SETTING
            if not (setting and setting.key) then return end
            Preview(content, "parts")
            UI.Section(content, { title = "What shows" })
            UI.Toggle(content, { label = setting.label, key = setting.key, tip = setting.tip })
            if Ready() then
                ToggleRow(content, "quest", "Quest marker")
                ToggleRow(content, "auras", "Auras row")
                ToggleRow(content, "raidMark", "Raid marker")
            end
            local combo = FS.NameplateCombo and FS.NameplateCombo.SETTING
            if combo and combo.key then
                UI.Toggle(content, { label = combo.label, key = combo.key, tip = combo.tip })
            end
            local mark = N.TARGET_MARK_SETTING
            if mark and mark.key then
                UI.Toggle(content, { label = mark.label, key = mark.key, tip = mark.tip })
            end
        end },
        { key = "friendly", label = "Friendly", build = function(content)
            if not Ready() then return end
            Preview(content, "friendly")
            UI.Section(content, { title = "Friendly plates" })
            SegmentedRow(content, "friendly", "Friendly plates")
        end },
    },
})
