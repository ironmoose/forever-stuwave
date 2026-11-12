-- Forever STUwave: Currency
-- The currency page of the character window (TokenFrame) from the approved CURRENCY mockup
-- (mockups/character-spells-2026-11-12.html, section 4): every currency with a cap is a row of TEN CAPACITY CELLS that fill as you
-- earn, like the totem poles on the HUD. At the cap the cells go amber and blink, so you see "spend this" without reading
-- numbers; a currency with a weekly cap carries a gold notch where this week's ceiling falls; the count reads "quantity / cap".
-- The window chrome, header band and the six mode tabs belong to Skins/Character.lua.
--
-- Skin only, and every behaviour stays the stock one: the same rows, collapse, selection, the options popup (unused, show on
-- backpack, transfer), tooltips and scroll list. Stock row art is held at alpha 0 (FS.HeldArt); the stock count is held and its
-- text mirrored beside our cells with the cap added, and the name is restyled in place. Nothing is moved, resized, reparented or
-- attributed.
--
-- Structure: the retail 12.1.0 Blizzard_TokenUI (an entry has Content.CurrencyIcon, Count, Name, BackgroundHighlight; its element
-- data carries quantity, maxQuantity, canEarnPerWeek, maxWeeklyQuantity, quantityEarnedThisWeek; a header has a title region; a
-- sub header has Text; the popup is TokenFramePopup). The 16001 dump names TokenFrame at login and nothing finer, so every field
-- is feature-detected. A number that is secret or not a plain number draws no cells for that row (the stock count text stays
-- mirrored as is).

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit
if not (Theme and HeldArt and Kit and PanelSkins and PanelSkins.RequireExport(
    Theme.AddPanelChrome and Theme.ApplyMono, "Currency.lua disabled: FS.Theme chrome helpers, FS.HeldArt or FS.ControlKit missing")) then return end

local Cur = {}
FS.CurrencySkin = Cur

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 }, cell = Theme.COLOR_CTRL_CELL or { 0.145, 0.082, 0.29 },
    gold = Theme.COLOR_GOLD or { 1, 0.82, 0.2 }, panel = { 0.071, 0.039, 0.133, 0.96 },
}

local G = { CELLS = 10, CELL_W = 8, CELL_H = 12, GAP = 2, TEXT_W = 96, SIDE = 12, NOTCH_W = 2, NOTCH_OVER = 3, PULSE = 0.9 }
Cur.GEOM = G

local S = { done = false, rows = setmetatable({}, { __mode = "k" }), hooked = setmetatable({}, { __mode = "k" }) }
Cur.state = S

local function Plain(v) return Kit.Plain(v) end
local function Try(fn, ...) return Kit.Try(fn, ...) end

local function Group(n)
    local s = tostring(math.floor(n))
    local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
    return (out:gsub("^,", ""))
end
Cur.Group = Group

-- Cells lit for `quantity` of `cap`: 0 for none, at least one for any, all ten at the cap.
function Cur.CellsLit(quantity, cap)
    if quantity <= 0 then return 0 end
    if quantity >= cap then return G.CELLS end
    return math.max(1, math.min(G.CELLS - 1, math.floor(quantity / cap * G.CELLS + 0.5)))
end

local function Number(v)
    v = Plain(v)
    return type(v) == "number" and v or nil
end

-- { quantity, cap, weeklyLeft } of a row's currency, nil fields when unreadable.
local function Reading(row)
    local d = row.elementData
    if type(d) ~= "table" and type(row.GetElementData) == "function" then d = Try(row.GetElementData, row) end
    if type(d) ~= "table" then return nil end
    local quantity, cap = Number(d.quantity), Number(d.maxQuantity)
    local weeklyMax, earned = Number(d.maxWeeklyQuantity), Number(d.quantityEarnedThisWeek)
    local weeklyLeft
    if Plain(d.canEarnPerWeek) == true and weeklyMax and weeklyMax > 0 and earned then weeklyLeft = math.max(0, weeklyMax - earned) end
    return { quantity = quantity, cap = cap and cap > 0 and cap or nil, weeklyLeft = weeklyLeft }
end

local function Parts(row)
    local p = S.rows[row]
    if p and p.cells then return p end
    p = p or {}
    S.rows[row] = p
    p.cells = {}
    for i = 1, G.CELLS do p.cells[i] = Kit.Rect(row, 0, 0, G.CELL_W, G.CELL_H, C.cell, 1, "OVERLAY", 2) end
    p.notch = Kit.Rect(row, 0, 0, G.NOTCH_W, G.CELL_H + 2 * G.NOTCH_OVER, C.gold, 1, "OVERLAY", 4)
    p.notch:Hide()
    p.label = Kit.Label(row, "", 11, C.text, "OVERLAY")
    Kit.Place(p.label, row, -G.SIDE, 0, nil, nil, "RIGHT", "RIGHT")
    p.label:SetJustifyH("RIGHT")
    return p
end

local function Mirror(p)
    local text = p.source and Plain(Try(p.source.GetText, p.source))
    if type(text) ~= "string" then return end
    p.count = text
    p.label:SetText(p.cap and (text .. " / " .. Group(p.cap)) or text)
end

-- Paints one entry row: cells for quantity against the cap, amber and blinking at the cap, the weekly notch, the count text.
function Cur.PaintRow(row)
    local p = S.rows[row]
    if not p then return end
    local r = Reading(row)
    p.cap = r and r.cap
    Mirror(p)
    Kit.StopAnimate(row, "cap")
    local rw, rh = Kit.SizePx(row)
    if not (r and r.quantity and r.cap and rw) then
        for _, cell in ipairs(p.cells) do cell:Hide() end
        p.notch:Hide()
        return
    end
    local stripW = G.CELLS * G.CELL_W + (G.CELLS - 1) * G.GAP
    local x0 = rw - G.SIDE - G.TEXT_W - 8 - stripW
    local y = math.floor((rh - G.CELL_H) / 2)
    local lit = Cur.CellsLit(r.quantity, r.cap)
    local capped = lit >= G.CELLS
    p.lit, p.capped = lit, capped
    local on = capped and C.amber or C.cyan
    for i, cell in ipairs(p.cells) do
        Kit.Move(cell, x0 + (i - 1) * (G.CELL_W + G.GAP), y, G.CELL_W, G.CELL_H)
        if i <= lit then cell:SetColorTexture(on[1], on[2], on[3], 1) else cell:SetColorTexture(C.cell[1], C.cell[2], C.cell[3], 1) end
        cell:Show()
    end
    if capped then
        Kit.Animate(row, "cap", function(_, elapsed)
            local a = Kit.Pulse(elapsed, G.PULSE, 0.35)
            for _, cell in ipairs(p.cells) do cell:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], a) end
        end)
    end
    if r.weeklyLeft then
        local ceiling = math.min(r.cap, r.quantity + r.weeklyLeft)
        local nx = x0 + math.floor(stripW * ceiling / r.cap + 0.5) - 1
        Kit.Move(p.notch, nx, y - G.NOTCH_OVER, G.NOTCH_W, G.CELL_H + 2 * G.NOTCH_OVER)
        p.notch:Show()
    else
        p.notch:Hide()
    end
end

local function Restyle(fs, host, px, color)
    if type(fs) ~= "table" or type(fs.SetFont) ~= "function" then return end
    Kit.RestyleLabel(fs, host, px, color)
    if type(fs.SetTextColor) == "function" then fs:SetTextColor(color[1], color[2], color[3], 1) end
end

local function SkinEntry(row)
    local content = row.Content
    if type(content) ~= "table" or type(content.Count) ~= "table" then return false end
    local p = Parts(row)
    p.source = content.Count
    Kit.HoldFrame(content.Count)
    if not p.mirrored then
        p.mirrored = true
        Kit.HookFunc(content.Count, "SetText", function() Mirror(p) end)
    end
    Restyle(content.Name, row, 12, C.text)
    local hl = content.BackgroundHighlight
    if type(hl) == "table" and type(hl.GetRegions) == "function" then
        for _, region in ipairs({ hl:GetRegions() }) do HeldArt.Hold(region) end
    end
    return true
end

local function SkinHeader(row)
    local Char = FS.CharacterSkin
    if Char and Char.HoldStock then
        -- the 16001 header rows have unnamed collapse art and a StateIcon (the plus or minus): hold the art, tint the glyph
        Char.HoldStock(row, 3)
        local icon = row.StateIcon
        if type(icon) == "table" and icon.SetVertexColor then pcall(icon.SetVertexColor, icon, C.cyan[1], C.cyan[2], C.cyan[3], 1) end
    end
    for _, key in ipairs({ "Left", "Middle", "Right", "HighlightLeft", "HighlightMiddle", "HighlightRight" }) do HeldArt.Hold(row[key]) end
    local title = type(row.GetTitleRegion) == "function" and Try(row.GetTitleRegion, row) or row.Text or row.Name
    if title then
        Restyle(title, row, 13, C.cyan)
        if PanelSkins.HookInlineColorRewrite and title == row.Text then pcall(PanelSkins.HookInlineColorRewrite, title, C.cyan) end
    end
end

local function RefreshRow(row)
    if SkinEntry(row) then Cur.PaintRow(row) else SkinHeader(row) end
end

local function HookRow(row)
    if S.hooked[row] then return end
    S.hooked[row] = true
    Kit.HookFunc(row, "Initialize", function() RefreshRow(row) end)
    Kit.HookScript(row, "OnSizeChanged", function() RefreshRow(row) end)
end

local function EachRow(fn)
    local frame = _G.TokenFrame
    local box = frame and frame.ScrollBox
    if not box then return end
    if type(box.ForEachFrame) == "function" then
        pcall(box.ForEachFrame, box, fn)
    elseif type(box.GetFrames) == "function" then
        local frames = Try(box.GetFrames, box)
        if type(frames) == "table" then for _, row in ipairs(frames) do fn(row) end end
    end
end

local function SkinPopup()
    local frame = _G.TokenFrame
    local popup = frame and (frame.Popup or _G.TokenFramePopup)
    if type(popup) == "table" and not popup.fsCurrencySkin then
        popup.fsCurrencySkin = true
        if popup.Border then Kit.HoldFrame(popup.Border) end
        Theme.AddPanelChrome(popup, { fillColor = C.panel, accent = C.violet, glowAlpha = 0.3 })
        Restyle(popup.Title, popup, 14, C.cyan)
        if PanelSkins.SweepControls then pcall(PanelSkins.SweepControls, popup) end
    end
    if frame and PanelSkins.SweepControls then pcall(PanelSkins.SweepControls, frame) end
end

function Cur.Refresh()
    if not S.done then return end
    EachRow(function(row)
        HookRow(row)
        RefreshRow(row)
    end)
end

local function Build()
    local frame = _G.TokenFrame
    if not frame or S.done then return end
    S.done = true
    frame.fsCurrencySkin = true
    pcall(SkinPopup)
    Kit.HookScript(frame, "OnShow", function() Kit.Later(function() Cur.Refresh() end) end)
    Kit.HookFunc(frame, "Update", function() Kit.Later(function() Cur.Refresh() end) end)
    Kit.OnReseat(Cur.Refresh)
    Cur.Refresh()
end

PanelSkins.RegisterInspect("Currency", { { name = "TokenFrame", guard = "fsCurrencySkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
