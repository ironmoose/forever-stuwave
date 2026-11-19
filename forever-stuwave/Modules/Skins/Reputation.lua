-- Forever STUwave: Reputation
-- The reputation page of the character window (ReputationFrame) from the approved REPUTATION mockup
-- (mockups/character-spells-2026-11-12.html, section 3): each faction is a STANDING LADDER, eight segments in a spectrum from
-- hated pink through amber, white, cyan and blue to exalted gold. Every standing you have passed is lit, the one you are in fills
-- by your progress, the rest are dim, and the leading edge breathes. The window chrome, header band and the character /
-- reputation / currency switch belong to Skins/Character.lua.
--
-- Skin only, and every behaviour stays the stock one: the same rows, the same clicks (select, collapse, the detail pane with its
-- at war, inactive and watch checkboxes), the same tooltips and the same scroll list. The stock bar keeps its value, its text and
-- its scripts; only its art is held at alpha 0 (FS.HeldArt) and our segments draw over its rect. Names and standing text are
-- restyled in place (mono, muted and light). Nothing is moved, resized, reparented or attributed.
--
-- Structure: the retail 12.1.0 Blizzard_UIPanels_Game ReputationFrame (ScrollBox rows; an entry has Content.ReputationBar with
-- Background, LeftTexture, RightTexture, BarText, and Content.Name; a header has Left, Middle, Right and Name; the detail pane is
-- ReputationDetailFrame). The 16001 dump names ReputationFrame at login and nothing finer, so every field is feature-detected and
-- a row whose parts are missing keeps its stock look. A row's standing comes from its element data (`reaction`), its progress from
-- the stock bar's own min, max and value; either one secret or missing draws no ladder and leaves the stock bar visible.
--
-- Row states (a stripe down the row's left edge and a wash behind it, repainted by the stock repaint and by hover): watched on
-- the bar is a cyan stripe; selected is a violet stripe and wash; at war is a pink stripe, a pink wash and a pink name; hover is
-- a light violet wash. The stock highlight regions are held; the state is read from the element data (atWarWith, isWatched) and
-- the row's IsSelected and IsMouseOver, each through FS.IsSecret first.
--
-- Left out on purpose (the mockup draws them, but they are computed, animated or invented, not a skin of a stock part): the eye
-- glyph on a watched row, the "+n" gain chips and the ladder's gain pulse (no per-session reputation gain is tracked), a standing
-- chip next to the bar (the stock bar text alternates progress and standing and is kept as it is), and the inactive row state.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit
if not (Theme and HeldArt and Kit and PanelSkins and PanelSkins.RequireExport(
    Theme.AddPanelChrome and Theme.ApplyMono, "Reputation.lua disabled: FS.Theme chrome helpers, FS.HeldArt or FS.ControlKit missing")) then return end

local Rep = {}
FS.ReputationSkin = Rep

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 }, ink = Theme.COLOR_CTRL_INK,
    cell = Theme.COLOR_CTRL_CELL or { 0.145, 0.082, 0.29 }, gold = Theme.COLOR_GOLD or { 1, 0.82, 0.2 },
    panel = { 0.071, 0.039, 0.133, 0.96 },
}

-- Hated .. exalted (reaction 1..8): the mockup's spectrum.
local LADDER = {
    { 1.00, 0.18, 0.59 }, { 1.00, 0.42, 0.36 }, { 1.00, 0.69, 0.18 }, { 0.93, 0.93, 0.96 },
    { 0.13, 0.88, 1.00 }, { 0.30, 0.55, 1.00 }, { 0.66, 0.42, 1.00 }, { 1.00, 0.82, 0.20 },
}
Rep.LADDER = LADDER

local G = { SEGMENTS = 8, GAP = 4, SEG_H = 8, EDGE = 2, INSET = 8, STRIPE = 3 }
Rep.GEOM = G

local S = { done = false, rows = setmetatable({}, { __mode = "k" }), hooked = setmetatable({}, { __mode = "k" }), marks = setmetatable({}, { __mode = "k" }) }
Rep.state = S

local function Plain(v) return Kit.Plain(v) end
local function Try(fn, ...) return Kit.Try(fn, ...) end

-------------------------------------------------------------------------------
-- The ladder
-------------------------------------------------------------------------------

-- Segment widths for a bar `w` physical pixels wide: eight, a 4 px gap, the rounding remainder spread over the first ones.
function Rep.SegmentWidths(w)
    local n, gap = G.SEGMENTS, G.GAP
    local usable = w - 2 * G.INSET - (n - 1) * gap
    if usable < n then return nil end
    local base, rem = math.floor(usable / n), usable % n
    local out = {}
    for i = 1, n do out[i] = base + (i <= rem and 1 or 0) end
    return out
end

-- The progress through the current standing from the stock bar's own numbers: 0..1, nil when it cannot be read plainly. The 16001
-- bar is a plain Frame (no min, max or value): its Fill is sized by the stock code to the progress across its FillArea, so the
-- fraction is read from those two widths (FS.CharacterSkin.BarFraction does both).
local function Progress(bar)
    local Char = FS.CharacterSkin
    if Char and Char.BarFraction then return Char.BarFraction(bar) end
    local lo, hi = Try(bar.GetMinMaxValues, bar)
    local v = Try(bar.GetValue, bar)
    lo, hi, v = Plain(lo), Plain(hi), Plain(v)
    if type(lo) ~= "number" or type(hi) ~= "number" or type(v) ~= "number" or hi <= lo then return nil end
    return math.max(0, math.min(1, (v - lo) / (hi - lo)))
end

local function ElementData(row)
    local data = row.elementData
    if type(data) ~= "table" and type(row.GetElementData) == "function" then data = Try(row.GetElementData, row) end
    if type(data) ~= "table" or Plain(data) == nil then return nil end
    return data
end

local function Reaction(row)
    local data = ElementData(row)
    if not data then return nil end
    local r = Plain(data.reaction)
    if type(r) ~= "number" or r < 1 then return nil end
    return math.min(G.SEGMENTS, math.floor(r))
end

local function Parts(row, bar)
    local p = S.rows[row]
    if p and p.segs then return p end
    p = p or {}
    S.rows[row] = p
    p.segs, p.fills = {}, {}
    for i = 1, G.SEGMENTS do
        p.segs[i] = Kit.Rect(bar, 0, 0, 1, G.SEG_H, C.cell, 1, "OVERLAY", 2)
        p.fills[i] = Kit.Rect(bar, 0, 0, 1, G.SEG_H, LADDER[i], 1, "OVERLAY", 3)
    end
    p.bar = bar
    -- the stock standing / progress text sits on the bar, where the ladder is: it is held and mirrored in small muted mono just left
    -- of the ladder, level with it (a label over the row's top right ran into the segments on the 30 unit 16001 rows)
    p.label = Kit.Label(row, "", 11, C.muted, "OVERLAY")
    Kit.Place(p.label, bar, -4, 0, nil, nil, "RIGHT", "LEFT", row)
    p.label:SetJustifyH("RIGHT")
    return p
end

local function Mirror(p)
    local text = p.source and Plain(Try(p.source.GetText, p.source))
    if type(text) == "string" then p.label:SetText(text:lower()) end
end

local function Lay(p)
    local bw, bh = Kit.SizePx(p.bar)
    if not bw then return false end
    local widths = Rep.SegmentWidths(bw)
    if not widths then return false end
    local y = math.floor((bh - G.SEG_H) / 2)
    local x = G.INSET
    p.x = {}
    for i = 1, G.SEGMENTS do
        Kit.Move(p.segs[i], x, y, widths[i], G.SEG_H)
        p.x[i] = { x = x, w = widths[i], y = y }
        x = x + widths[i] + G.GAP
    end
    return true
end

local function ShowLadder(p, on)
    for i = 1, G.SEGMENTS do
        p.segs[i]:SetShown(on)
        p.fills[i]:SetShown(on)
    end
end

-- Paints one entry row from its reaction and progress. The leading segment breathes while the row is shown.
function Rep.PaintRow(row)
    local p = S.rows[row]
    if not (p and p.bar) then return end
    local reaction, progress = Reaction(row), Progress(p.bar)
    if not reaction or not progress or not Lay(p) then
        ShowLadder(p, false)
        Kit.StopAnimate(p.bar, "lead")
        p.drawn = false
        return
    end
    p.drawn = true
    p.reaction, p.progress = reaction, progress
    ShowLadder(p, true)
    local capped = reaction >= G.SEGMENTS
    for i = 1, G.SEGMENTS do
        local seg, fill, pos = p.segs[i], p.fills[i], p.x[i]
        local lit = i < reaction or (i == reaction and capped)
        local frac = lit and 1 or (i == reaction and progress or 0)
        local w = frac >= 1 and pos.w or math.floor(pos.w * frac + 0.5)
        local dim = Kit.Mix(C.cell, LADDER[i], 0.18)
        seg:SetColorTexture(dim[1], dim[2], dim[3], 1)
        if w > 0 then
            Kit.Move(fill, pos.x, pos.y, w, G.SEG_H)
            fill:SetColorTexture(LADDER[i][1], LADDER[i][2], LADDER[i][3], 1)
            fill:Show()
        else
            fill:Hide()
        end
    end
    -- the leading edge: the standing in progress breathes, an exalted row rests lit
    Kit.StopAnimate(p.bar, "lead")
    if not capped then
        local lead = p.fills[reaction]
        local color = LADDER[reaction]
        Kit.Animate(p.bar, "lead", function(_, elapsed)
            lead:SetColorTexture(color[1], color[2], color[3], Kit.Pulse(elapsed, 1.6, 0.55))
        end)
    end
end

-------------------------------------------------------------------------------
-- Row states
-------------------------------------------------------------------------------

-- The stock row showed three states through its BackgroundHighlight (selected, hovered, and a standing red wash for a faction you
-- are at war with); that art is held (SkinEntry), so the states are drawn here from our own rects: a wash over the row and a
-- stripe STRIPE px wide at its left edge. A watched faction wears a cyan stripe, a selected row a violet one (and wash), a row at
-- war a pink name, stripe and wash, a hovered row a light wash. The flags are the stock row's own: elementData.atWarWith and
-- isWatched, and the row's IsSelected and IsMouseOver; a secret or missing one reads as false.
local function Marks(row)
    local m = S.marks[row]
    if m then return m end
    m = {}
    S.marks[row] = m
    m.wash = row:CreateTexture(nil, "BACKGROUND", nil, -6)
    m.wash:SetAllPoints(row)
    m.wash:Hide()
    m.stripe = row:CreateTexture(nil, "BORDER", nil, 3)
    m.stripe:SetPoint("TOPLEFT", row, "TOPLEFT", 0, 0)
    m.stripe:SetPoint("BOTTOMLEFT", row, "BOTTOMLEFT", 0, 0)
    m.stripe:Hide()
    return m
end

local function Flag(v) return Plain(v) == true end

function Rep.PaintMarks(row)
    local content = row.Content
    if type(content) ~= "table" or type(content.ReputationBar) ~= "table" or type(row.CreateTexture) ~= "function" then return end
    local data = ElementData(row) or {}
    local atWar, watched = Flag(data.atWarWith), Flag(data.isWatched)
    local selected = type(row.IsSelected) == "function" and Flag(Try(row.IsSelected, row))
    local hover = type(row.IsMouseOver) == "function" and Flag(Try(row.IsMouseOver, row))
    local m = Marks(row)
    local wash, washAlpha
    if atWar then wash, washAlpha = C.pink, selected and 0.26 or (hover and 0.2 or 0.12)
    elseif selected then wash, washAlpha = C.violet, 0.22
    elseif hover then wash, washAlpha = C.violet, 0.10 end
    if wash then
        m.wash:SetColorTexture(wash[1], wash[2], wash[3], washAlpha)
        m.wash:Show()
    else
        m.wash:Hide()
    end
    local stripe = selected and C.violet or (atWar and C.pink or (watched and C.cyan))
    if stripe then
        m.stripe:SetColorTexture(stripe[1], stripe[2], stripe[3], 1)
        m.stripe:SetWidth(Kit.U(row, G.STRIPE))
        m.stripe:Show()
    else
        m.stripe:Hide()
    end
    if type(content.Name) == "table" then Kit.Recolor(content.Name, atWar and C.pink or C.text) end
end

-------------------------------------------------------------------------------
-- Rows
-------------------------------------------------------------------------------

local function Restyle(fs, row, px, color)
    if type(fs) ~= "table" or type(fs.SetFont) ~= "function" then return end
    Kit.RestyleLabel(fs, row, px, color)
    if type(fs.SetTextColor) == "function" then fs:SetTextColor(color[1], color[2], color[3], 1) end
end

local function SkinEntry(row)
    local content = row.Content
    local bar = content and content.ReputationBar
    if type(bar) ~= "table" then return false end
    for _, key in ipairs({ "Background", "LeftTexture", "RightTexture" }) do HeldArt.Hold(bar[key]) end
    -- the 16001 bar: an unkeyed common-stat-bar-BG plate, a keyed Fill, a keyed Text
    local Char = FS.CharacterSkin
    if Char and Char.HoldStock then Char.HoldStock(bar, 0) end
    local texture = Try(bar.GetStatusBarTexture, bar)
    if type(texture) ~= "table" then texture = bar.Fill end
    local p = Parts(row, bar)
    p.texture = texture
    local text = bar.BarText or bar.Text
    if type(text) == "table" then
        p.source = text
        Kit.HoldFrame(text)
        if not p.mirrored then
            p.mirrored = true
            Kit.HookFunc(text, "SetText", function() Mirror(p) end)
            if type(bar.Fill) == "table" then Kit.HookFunc(bar.Fill, "SetWidth", function() Rep.PaintRow(row) end) end
        end
        Mirror(p)
    end
    Restyle(content.Name, row, 12, C.text)
    local hl = content.BackgroundHighlight
    if type(hl) == "table" and type(hl.GetRegions) == "function" then
        for _, region in ipairs({ hl:GetRegions() }) do HeldArt.Hold(region) end
    end
    return true
end

local function SkinHeader(row)
    -- the 16001 header rows carry unnamed collapse art and a StateIcon: the shared page row holds the art and tints the glyph
    local Char = FS.CharacterSkin
    if Char and Char.HoldStock then
        Char.HoldStock(row, 3)
        if Char.TintStateIcon then Char.TintStateIcon(row.StateIcon) end
    end
    for _, key in ipairs({ "Left", "Middle", "Right", "HighlightLeft", "HighlightMiddle", "HighlightRight" }) do
        HeldArt.Hold(row[key])
    end
    if type(row.Name) ~= "table" then return false end
    Restyle(row.Name, row, 13, C.cyan)
    return true
end

local function RefreshRow(row)
    if SkinEntry(row) then
        local p = S.rows[row]
        -- the stock fill is held only while our ladder stands in for it
        Rep.PaintRow(row)
        Rep.PaintMarks(row)
        if p.texture and p.drawn then HeldArt.Hold(p.texture) end
    else
        SkinHeader(row)
    end
end

local function HookRow(row)
    if S.hooked[row] then return end
    S.hooked[row] = true
    Kit.HookFunc(row, "Initialize", function() RefreshRow(row) end)
    -- the stock repaint of the highlight (selection, hover): the states drawn here follow it
    Kit.HookFunc(row, "RefreshBackgroundHighlight", function() Rep.PaintMarks(row) end)
    Kit.HookScript(row, "OnEnter", function() Rep.PaintMarks(row) end)
    Kit.HookScript(row, "OnLeave", function() Rep.PaintMarks(row) end)
    local content = row.Content
    local bar = content and content.ReputationBar
    if bar then
        Kit.HookFunc(bar, "UpdateBarValues", function() RefreshRow(row) end)
        Kit.HookScript(bar, "OnSizeChanged", function() RefreshRow(row) end)
    end
end

local function EachRow(fn)
    local frame = _G.ReputationFrame
    local box = frame and frame.ScrollBox
    if not box then return end
    if type(box.ForEachFrame) == "function" then
        pcall(box.ForEachFrame, box, fn)
    elseif type(box.GetFrames) == "function" then
        local frames = Try(box.GetFrames, box)
        if type(frames) == "table" then for _, row in ipairs(frames) do fn(row) end end
    end
end

local function SkinPane()
    local frame = _G.ReputationFrame
    if not frame then return end
    local detail = frame.ReputationDetailFrame
    if type(detail) == "table" and not detail.fsRepSkin then
        detail.fsRepSkin = true
        if detail.Border then Kit.HoldFrame(detail.Border) end
        HeldArt.Hold(detail.Divider)
        Theme.AddPanelChrome(detail, { fillColor = C.panel, accent = C.violet, glowAlpha = 0.3 })
        Restyle(detail.Title, detail, 14, C.cyan)
        if FS.CharacterSkin and FS.CharacterSkin.SkinDetail then pcall(FS.CharacterSkin.SkinDetail, detail) end
        if PanelSkins.SweepControls then pcall(PanelSkins.SweepControls, detail) end
    end
    if PanelSkins.SweepControls then pcall(PanelSkins.SweepControls, frame) end
end

function Rep.Refresh()
    if not S.done then return end
    EachRow(function(row)
        HookRow(row)
        RefreshRow(row)
    end)
end

local function Build()
    local frame = _G.ReputationFrame
    if not frame or S.done then return end
    S.done = true
    frame.fsReputationSkin = true
    pcall(SkinPane)
    Kit.HookScript(frame, "OnShow", function() Kit.Later(function() Rep.Refresh() end) end)
    Kit.HookFunc(frame, "Update", function() Kit.Later(function() Rep.Refresh() end) end)
    Kit.OnReseat(Rep.Refresh)
    Rep.Refresh()
end

PanelSkins.RegisterInspect("Reputation", { { name = "ReputationFrame", guard = "fsReputationSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
