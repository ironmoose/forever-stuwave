-- Forever STUwave: DropdownSkins
-- The closed dropdown button of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 5) and the
-- additions it puts on the open list.
--
-- The closed button is the edit box's body (an ink face with a dim violet 1 px edge and the cut corner at the top left and
-- bottom right) with a small square swatch of the current choice, the label, a hairline and a chevron:
--
--   idle     ink face, dim edge, violet swatch, muted chevron        hover     the edge and chevron go cyan
--   open     cyan edge, 3 px glow, LED underline breathing, the chevron flips upright
--   disabled darkest ink, dim edge, dim label, swatch, hairline and chevron
--
-- The list keeps the stock rows and Modules/Skins/Menus.lua's chrome. On top of them: a row under the hand is caught in lock-on
-- brackets over a violet wash, the current value carries a pink LED that breathes, and the whole list is scanned open (a
-- cyan front edge runs down it in 0.2 s and each row appears as the edge passes it). The additions go on every modern menu
-- (a dropdown's list, a context menu, a submenu) and on the legacy UIDropDownMenu lists, which are the same list to the eye.
--
-- Skin only. A stock dropdown keeps its rect, its scripts and its menu: its Background and Arrow art is held at alpha 0
-- (FS.HeldArt), our face, glow and edge are regions of the button itself (under the label), the swatch, hairline, chevron and
-- LED live on a child frame, and we follow the button by post-hooks (OnEnter, OnLeave, OnMouseDown, OnMouseUp, OnShow,
-- OnEnable, OnDisable, OnButtonStateChanged, OnMenuOpened, OnMenuClosed, Enable, Disable). The label is restyled to the kit's
-- mono and moved to the swatch's right; Blizzard's own state colours are painted over after every state change.
--
-- The list's rows are Blizzard frames pooled and reused: nothing is written on them but alpha during the wipe (their own alpha
-- is saved and put back when the wipe ends, when the menu hides, and before the next wipe on the same frame), and our own
-- child frames carry the wash, the brackets and the LED. Nothing is hidden, resized, reparented or given an attribute, and
-- nothing is done to a list opened in combat (a context menu can hold protected actions); the closed button is skinned
-- when combat ends, like every other control. The modern menu frame is compositor managed: nothing is written on it as a
-- field, our state is in weak tables.
--
-- Told by shape: a Button that is a DropdownButton (the intrinsic) with a label (`Text`), between DD_MIN_W wide by
-- FIELD_MIN_H and FIELD_MAX_H tall in pixels, whose Background art nothing else holds. WowStyle1DropdownTemplate,
-- WowStyle1FilterDropdownTemplate and WowStyle2DropdownTemplate are XML templates, never globals, so the 16001 globals dump
-- cannot confirm them; their shapes are read from the 12.1.0 Blizzard_Menu source and detected at runtime. An arrow dropdown
-- (WowStyle1ArrowDropdownTemplate) has no label: it wears a small square key with the kit's chevron, no swatch or LED. A
-- legacy UIDropDownMenu frame (a Frame, not a button) is left alone.
--
-- The swatch has no source of its own: DropdownSkins.SetSwatch(button, color) sets the colour of the current choice, and a
-- button nothing has told wears the violet default.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and Theme.COLOR_CTRL_HAIR) then return end

local DropdownSkins = {}
FS.DropdownSkins = DropdownSkins

local K = FS.Layout.Controls
local CHEV = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\ctl_chev.tga"

local C = {
    ink = Theme.COLOR_CTRL_INK, dim = Theme.COLOR_CTRL_DIM, dis = Theme.COLOR_CTRL_DIS, disFill = Theme.COLOR_CTRL_DISFILL,
    disEdge = Theme.COLOR_CTRL_DISEDGE, text = Theme.COLOR_CTRL_TEXT, hair = Theme.COLOR_CTRL_HAIR,
    pink = Theme.COLOR_HEALTH, cyan = Theme.COLOR_POWER, muted = Theme.COLOR_MUTED, violet = Theme.COLOR_BORDER,
}

local function Weak() return setmetatable({}, { __mode = "k" }) end

local parts = Weak()       -- dropdown button -> what we drew on it
local rowParts = Weak()    -- menu row -> what we drew on it
local menuParts = Weak()   -- menu frame -> its scan frame and front edge
local legacyHooked = Weak()

local function Round(v) return math.floor(v + 0.5) end
local function IsTable(v) return type(v) == "table" end

-------------------------------------------------------------------------------
-- The closed button
-------------------------------------------------------------------------------

local ArrowArt

local function Held(region)
    if not IsTable(region) then return false end
    return Kit.Plain(Kit.Try(region.GetAlpha, region)) == 0
end

-- The stock gold arrow of a labelless arrow dropdown (WowStyle1ArrowDropdownTemplate's Arrow; the spellbook's settings
-- button keeps the same atlas as its Icon), or nil.
local ARROW_ATLAS = "common-dropdown-a-button"
function ArrowArt(widget)
    for _, key in ipairs({ "Arrow", "Icon" }) do
        local region = widget[key]
        if IsTable(region) and Kit.Plain(Kit.Try(region.GetAtlas, region)) == ARROW_ATLAS then return region end
    end
    return nil
end

-- "dropdown", "arrow" (a labelless arrow button: a small cut-corner key with the kit's chevron) or nil.
function DropdownSkins.Kind(widget)
    if Kit.TypeOf(widget) ~= "Button" then return nil end
    if not (widget.intrinsic == "DropdownButton" or type(widget.IsMenuOpen) == "function") then return nil end
    local label = widget.Text
    if not (IsTable(label) and type(label.SetFont) == "function") then
        return ArrowArt(widget) and "arrow" or nil
    end
    local w, h = Kit.SizePx(widget)
    if w and (w < K.DD_MIN_W or h < K.FIELD_MIN_H or h > K.FIELD_MAX_H) then return nil end
    if not parts[widget] and Held(widget.Background) then return nil end
    return "dropdown"
end

function DropdownSkins.Parts(widget) return parts[widget] end

local function IsOpen(widget)
    return Kit.Plain(Kit.Try(widget.IsMenuOpen, widget)) == true
end

local function PaintArrow(widget, p)
    local enabled = Kit.IsEnabled(widget)
    local open = enabled and IsOpen(widget)
    local fill, edge, glyph = C.ink, C.dim, C.muted
    if not enabled then
        fill, edge, glyph = C.disFill, C.disEdge, C.dis
    elseif open or p.state.hover or p.state.pressed then
        edge, glyph = C.cyan, C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, 1)
    p.chev:SetVertexColor(glyph[1], glyph[2], glyph[3], 1)
    if open then p.chev:SetTexCoord(0, 1, 1, 0) else p.chev:SetTexCoord(0, 1, 0, 1) end
end

local function Paint(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    if p.arrow then return PaintArrow(widget, p) end
    local enabled = Kit.IsEnabled(widget)
    local open = enabled and IsOpen(widget)
    local fill, edge, glyph, text, rule, swatch = C.ink, C.dim, C.muted, C.text, C.hair, p.swatchColor or C.violet
    if not enabled then
        fill, edge, glyph, text, rule, swatch = C.disFill, C.disEdge, C.dis, C.dis, C.disEdge, C.disEdge
    elseif open or p.state.hover or p.state.pressed then
        edge, glyph = C.cyan, C.cyan
    end
    Kit.PaintPlate(p.plate, fill, 1, edge, 1, 1)
    p.swatch:SetColorTexture(swatch[1], swatch[2], swatch[3], 1)
    p.hair:SetColorTexture(rule[1], rule[2], rule[3], 1)
    p.chev:SetVertexColor(glyph[1], glyph[2], glyph[3], 1)
    if open then p.chev:SetTexCoord(0, 1, 1, 0) else p.chev:SetTexCoord(0, 1, 0, 1) end
    -- Blizzard writes the label's font (filter dropdowns) and colour on every state change; ours is painted after it
    Kit.RestyleLabel(widget.Text, widget, K.FIELD_TEXT, text)
    Kit.Recolor(widget.Text, text)

    p.glow:SetShown(open)
    if open then
        p.led:Show()
        if not Kit.IsAnimating(p.over, "led") then
            Kit.Animate(p.over, "led", function(_, elapsed)
                p.led:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
            end)
        end
    else
        p.led:Hide()
        Kit.StopAnimate(p.over, "led")
    end
end

local function Layout(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(widget)
    if not w then return end
    p.w, p.h = w, h
    if p.arrow then
        -- a square key at least ARROW_MIN across, centred on the stock rect (the spellbook's is 15 x 16)
        local size = math.max(K.DD_ARROW_MIN, math.min(w, h))
        local x, y = Round((w - size) / 2), Round((h - size) / 2)
        Kit.Place(p.plate.fill, widget, x, y, size, size)
        Kit.Place(p.plate.ring, widget, x, y, size, size)
        if p.plate.ring2 then Kit.Place(p.plate.ring2, widget, x + 1, y + 1, size - 2, size - 2) end
        local g = K.FIELD_GLYPH
        Kit.Move(p.chev, x + Round((size - g) / 2), y + Round((size - g) / 2), g, g)
        return
    end
    Kit.Place(p.plate.fill, widget, 0, 0, w, h)
    Kit.Place(p.plate.ring, widget, 0, 0, w, h)
    if p.plate.ring2 then Kit.Place(p.plate.ring2, widget, 1, 1, w - 2, h - 2) end
    Kit.Move(p.glow, -K.FIELD_GLOW, -K.FIELD_GLOW, w + 2 * K.FIELD_GLOW, h + 2 * K.FIELD_GLOW)
    Kit.Move(p.swatch, K.DD_SWATCH_X, math.floor((h - K.DD_SWATCH) / 2), K.DD_SWATCH, K.DD_SWATCH)
    Kit.Move(p.hair, w - K.DD_ZONE, K.DD_RULE_PAD, 1, h - 2 * K.DD_RULE_PAD)
    Kit.Move(p.chev, w - K.DD_CHEV_X, math.floor((h - K.FIELD_GLYPH) / 2), K.FIELD_GLYPH, K.FIELD_GLYPH)
    Kit.Move(p.led, 1, h - K.FIELD_LED_UP, w - 2, K.FIELD_LED_H)
    local label = widget.Text
    if IsTable(label) and type(label.ClearAllPoints) == "function" and type(label.SetPoint) == "function" then
        local ppu = Kit.Ppu(widget)
        label:ClearAllPoints()
        label:SetPoint("LEFT", widget, "LEFT", K.DD_LABEL_X / ppu, 0)
        label:SetPoint("RIGHT", widget, "RIGHT", -K.DD_TEXT_RIGHT / ppu, 0)
        if type(label.SetJustifyH) == "function" then label:SetJustifyH("LEFT") end
    end
end

Kit.OnReseat(function()
    for widget in pairs(parts) do Layout(widget) end
end)

-- Sets the colour of the current choice's swatch (nil for the violet default). A secret colour is ignored.
function DropdownSkins.SetSwatch(widget, color)
    local p = parts[widget]
    if not p then return end
    if IsTable(color) and not (FS.IsSecret and FS.IsSecret(color)) and type(color[1]) == "number" then
        p.swatchColor = color
    else
        p.swatchColor = nil
    end
    Paint(widget)
end

local function BuildArrow(widget, p)
    p.arrow = true
    HeldArt.Hold(ArrowArt(widget))
    HeldArt.Hold(widget.Arrow)
    HeldArt.Hold(Kit.Try(widget.GetHighlightTexture, widget))
    p.plate = Kit.Plate(widget, K.DD_ARROW_CUT, K.DD_ARROW_MIN, K.DD_ARROW_MIN)
    local over = CreateFrame("Frame", nil, widget)
    over:SetAllPoints(widget)
    p.over = over
    p.chev = Kit.Glyph(over, CHEV, 0, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.muted, 1, "ARTWORK", 2)
    p.built = true
    p.state = Kit.Track(widget, Paint)
    for _, method in ipairs({ "OnButtonStateChanged", "OnMenuOpened", "OnMenuClosed", "CloseMenu" }) do
        Kit.HookFunc(widget, method, function() Paint(widget) end)
    end
    local function relayout()
        Layout(widget)
        Paint(widget)
    end
    Kit.HookScript(widget, "OnSizeChanged", relayout)
    Kit.HookScript(widget, "OnShow", relayout)
    relayout()
    Kit.Later(relayout)
end

local function Build(widget)
    local p = { w = 0, h = 0 }
    parts[widget] = p -- marked first, so a failure part way is not retried into a second set of layers
    if DropdownSkins.Kind(widget) == "arrow" then return BuildArrow(widget, p) end

    HeldArt.Hold(widget.Background)
    HeldArt.Hold(widget.Arrow)
    Kit.RestyleLabel(widget.Text, widget, K.FIELD_TEXT, C.text)

    p.plate = Kit.Plate(widget, K.FIELD_CUT, K.FIELD_GLYPH, K.FIELD_GLYPH)
    p.glow = Kit.Rect(widget, -K.FIELD_GLOW, -K.FIELD_GLOW, 1, 1, C.cyan, K.FIELD_GLOW_ALPHA, "BACKGROUND", -8)
    p.glow:Hide()

    local over = CreateFrame("Frame", nil, widget)
    over:SetAllPoints(widget)
    p.over = over
    p.swatch = Kit.Rect(over, K.DD_SWATCH_X, 0, K.DD_SWATCH, K.DD_SWATCH, C.violet, 1, "ARTWORK", 1)
    p.hair = Kit.Rect(over, 0, K.DD_RULE_PAD, 1, 1, C.hair, 1, "ARTWORK", 0)
    p.chev = Kit.Glyph(over, CHEV, 0, 0, K.FIELD_GLYPH, K.FIELD_GLYPH, C.muted, 1, "ARTWORK", 2)
    p.led = Kit.Rect(over, 1, 0, 1, K.FIELD_LED_H, C.cyan, 1, "ARTWORK", 3)
    p.led:Hide()
    p.built = true

    p.state = Kit.Track(widget, Paint)
    for _, method in ipairs({ "OnButtonStateChanged", "OnMenuOpened", "OnMenuClosed", "CloseMenu" }) do
        Kit.HookFunc(widget, method, function() Paint(widget) end)
    end
    local function relayout()
        Layout(widget)
        Paint(widget)
    end
    Kit.HookScript(widget, "OnSizeChanged", relayout)
    Kit.HookScript(widget, "OnShow", relayout)
    Layout(widget)
    Paint(widget)
    Kit.Later(relayout)
end

-- Skins one stock dropdown button. Idempotent; returns true when it skinned now. A button met in combat is skinned when
-- combat ends.
function DropdownSkins.Skin(widget)
    if type(widget) ~= "table" or parts[widget] or not DropdownSkins.Kind(widget) then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        Kit.Defer(function() DropdownSkins.Skin(widget) end)
        return false
    end
    local ok, err = pcall(Build, widget)
    if not ok then Kit.Fail("dropdown", err) end
    return ok and parts[widget] ~= nil
end

Kit.Register("dropdown", {
    match = function(widget) return parts[widget] ~= nil or DropdownSkins.Kind(widget) ~= nil end,
    skin = DropdownSkins.Skin, parts = DropdownSkins.Parts,
})

-------------------------------------------------------------------------------
-- The open list: rows
-------------------------------------------------------------------------------

-- The rows of a menu frame: a modern row answers GetElementDescription (Blizzard_Menu's compositor sets it on every element
-- frame); a legacy row is a button of DropDownListN named DropDownListNButtonM.
local function IsRow(menu, child)
    if not IsTable(child) or Kit.TypeOf(child) ~= "Button" then return false end
    if type(child.GetElementDescription) == "function" then return true end
    local list = Kit.Try(menu.GetName, menu)
    local name = Kit.Try(child.GetName, child)
    return type(list) == "string" and type(name) == "string" and name:find("^" .. list .. "Button%d+$") ~= nil
end

local function RowsOf(menu)
    local rows = {}
    if type(menu.GetChildren) ~= "function" then return rows end
    local ok, list = pcall(function() return { menu:GetChildren() } end)
    if not ok then return rows end
    for _, child in ipairs(list) do
        if IsRow(menu, child) then rows[#rows + 1] = child end
    end
    return rows
end

-- True when the row is the current value: a modern row's description says so, a legacy row shows its Check.
local function IsSelected(row)
    if type(row.GetElementDescription) == "function" then
        local ok, description = pcall(row.GetElementDescription, row)
        if not (ok and IsTable(description) and type(description.IsSelected) == "function") then return false end
        local okSelected, selected = pcall(description.IsSelected, description)
        return okSelected and Kit.Plain(selected) == true
    end
    local name = Kit.Try(row.GetName, row)
    local check = type(name) == "string" and _G[name .. "Check"] or nil
    return IsTable(check) and Kit.Plain(Kit.Try(check.IsShown, check)) == true
end

function DropdownSkins.RowParts(row) return rowParts[row] end

local function SyncRow(row, d)
    local selected = IsSelected(row)
    d.led:SetShown(selected)
    if selected then
        if not Kit.IsAnimating(d.over, "led") then
            Kit.Animate(d.over, "led", function(_, elapsed)
                d.led:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
            end)
        end
    else
        Kit.StopAnimate(d.over, "led")
    end
    local hover = d.hover == true
    d.wash:SetShown(hover)
    Kit.ShowReticle(d.reticle, hover)
end

local function LayoutRow(row, d)
    local w, h = Kit.SizePx(row)
    if not w then return end
    Kit.Move(d.wash, 0, 0, w, h)
    Kit.SeatReticle(d.reticle, K.ROW_PAD, K.ROW_PAD, w - 2 * K.ROW_PAD, h - 2 * K.ROW_PAD, 0, K.RETICLE_LEN)
    Kit.Move(d.led, K.ROW_LED_X, math.floor((h - K.ROW_LED_H) / 2), K.ROW_LED_W, K.ROW_LED_H)
end

Kit.OnReseat(function()
    for row, d in pairs(rowParts) do LayoutRow(row, d) end
end)

-- The wash sits under the row's own text and the brackets and LED over it: two child frames a level either side of the row.
local function BuildRow(row)
    local d = {}
    rowParts[row] = d
    local level = Kit.Plain(Kit.Try(row.GetFrameLevel, row)) or 1

    local under = CreateFrame("Frame", nil, row)
    under:SetAllPoints(row)
    under:SetFrameLevel(math.max(0, level - 1))
    d.under = under
    d.wash = Kit.Rect(under, 0, 0, 1, 1, C.violet, K.ROW_WASH_ALPHA, "BACKGROUND", 0)
    d.wash:Hide()

    local over = CreateFrame("Frame", nil, row)
    over:SetAllPoints(row)
    over:SetFrameLevel(level + 1)
    d.over = over
    d.reticle = Kit.Reticle(over, "OVERLAY", 4)
    Kit.PaintReticle(d.reticle, C.cyan, 1)
    Kit.ShowReticle(d.reticle, false)
    d.led = Kit.Rect(over, K.ROW_LED_X, 0, K.ROW_LED_W, K.ROW_LED_H, C.pink, 1, "OVERLAY", 3)
    d.led:Hide()

    Kit.HookScript(row, "OnEnter", function() d.hover = true; SyncRow(row, d) end)
    Kit.HookScript(row, "OnLeave", function() d.hover = false; SyncRow(row, d) end)
    Kit.HookScript(row, "OnShow", function() d.hover = false; SyncRow(row, d) end)
    Kit.HookScript(row, "OnSizeChanged", function() LayoutRow(row, d) end)
    LayoutRow(row, d)
    return d
end

local function DecorateRow(row)
    local d = rowParts[row] or BuildRow(row)
    LayoutRow(row, d)
    SyncRow(row, d)
end

-------------------------------------------------------------------------------
-- The open list: the scan wipe
-------------------------------------------------------------------------------

local driver -- one always-visible frame that owns every wipe, so a menu that hides mid-wipe is still seen to end it

local function Driver()
    if not driver then
        driver = CreateFrame("Frame", nil, UIParent)
        driver:Show()
    end
    return driver
end

local function MenuHost(menu)
    local m = menuParts[menu]
    if m then return m end
    m = { driver = Driver() }
    menuParts[menu] = m
    local host = CreateFrame("Frame", nil, menu)
    host:SetAllPoints(menu)
    host:SetFrameLevel((Kit.Plain(Kit.Try(menu.GetFrameLevel, menu)) or 1) + 30)
    m.host = host
    m.front = Kit.Rect(host, 0, 0, 1, K.WIPE_FRONT, C.cyan, 1, "OVERLAY", 7)
    m.front:Hide()
    return m
end

function DropdownSkins.MenuParts(menu) return menuParts[menu] end

-- Puts every row's own alpha back, hides the front edge and ends the wipe.
local function FinishWipe(menu)
    local m = menuParts[menu]
    if not m then return end
    if m.saved then
        for row, alpha in pairs(m.saved) do pcall(row.SetAlpha, row, alpha) end
        m.saved = nil
    end
    m.front:Hide()
    Kit.StopAnimate(m.driver, menu)
end

local function MenuShown(menu)
    return Kit.Plain(Kit.Try(menu.IsShown, menu)) == true
end

-- Distance of each row's vertical middle below the top of the menu, in pixels (nil when the client will not say).
local function RowMiddles(menu, rows)
    local ppu = Kit.Ppu(menu)
    local top = Kit.Plain(Kit.Try(menu.GetTop, menu))
    local middles = {}
    for i, row in ipairs(rows) do
        local rowTop, height = Kit.Plain(Kit.Try(row.GetTop, row)), Kit.Plain(Kit.Try(row.GetHeight, row))
        if type(top) == "number" and type(rowTop) == "number" and type(height) == "number" then
            middles[i] = (top - rowTop + height / 2) * ppu
        end
    end
    return middles
end

local function StartWipe(menu, rows)
    local m = MenuHost(menu)
    FinishWipe(menu) -- puts back what an earlier wipe on this frame took, so the alphas saved below are the real ones
    local mw, mh = Kit.SizePx(menu)
    if not mw or #rows == 0 then return end
    local middles = RowMiddles(menu, rows)
    m.saved = {}
    for i, row in ipairs(rows) do
        local alpha = Kit.Plain(Kit.Try(row.GetAlpha, row))
        m.saved[row] = type(alpha) == "number" and alpha or 1
        -- a client that gives no positions reveals the rows in order, evenly
        middles[i] = middles[i] or (i - 0.5) / #rows * mh
        pcall(row.SetAlpha, row, 0)
    end
    m.front:Show()
    Kit.Move(m.front, 0, 0, mw, K.WIPE_FRONT)
    Kit.Animate(m.driver, menu, function(_, elapsed)
        if not MenuShown(menu) then
            FinishWipe(menu)
            return
        end
        local progress = math.min(1, elapsed / K.WIPE_TIME)
        local front = Round(progress * mh)
        for i, row in ipairs(rows) do
            local saved = m.saved and m.saved[row]
            if saved and middles[i] <= front then
                pcall(row.SetAlpha, row, saved)
                m.saved[row] = nil
            end
        end
        Kit.Move(m.front, 0, math.max(0, front - K.WIPE_FRONT), mw, K.WIPE_FRONT)
        if progress >= 1 then FinishWipe(menu) end
    end)
end

-------------------------------------------------------------------------------
-- The open list: entry points
-------------------------------------------------------------------------------

local function SkinMenu(menu)
    if type(menu) ~= "table" then return end
    -- a context menu can hold protected actions: nothing is built on, or done to, a list opened in combat
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return end
    local rows = RowsOf(menu)
    for _, row in ipairs(rows) do DecorateRow(row) end
    StartWipe(menu, rows)
end

local function Run(menu)
    local ok, err = pcall(SkinMenu, menu)
    if not ok then Kit.Fail("menu", err) end
end

local menuHooked = false

-- Hooks the modern menu manager's two entry points (the way Menus.lua does) and the callback it gives a submenu. Returns true
-- once hooked.
function DropdownSkins.HookMenus()
    if menuHooked then return true end
    if type(Menu) ~= "table" or type(Menu.GetManager) ~= "function" then return false end
    local ok, manager = pcall(Menu.GetManager)
    if not (ok and IsTable(manager) and type(manager.GetOpenMenu) == "function" and type(manager.OpenMenu) == "function") then
        return false
    end
    local function current()
        local okMenu, frame = pcall(manager.GetOpenMenu, manager)
        return okMenu and frame or nil
    end
    local acquiredHooked = Weak()  -- a description reopened later keeps its one callback
    local function onAcquired() Run(current()) end
    local function opened(_, _, description)
        if IsTable(description) and not acquiredHooked[description]
            and type(description.AddMenuAcquiredCallback) == "function" then
            acquiredHooked[description] = true
            pcall(description.AddMenuAcquiredCallback, description, onAcquired)
        end
        Run(current())
    end
    Kit.HookFunc(manager, "OpenMenu", opened)
    Kit.HookFunc(manager, "OpenContextMenu", opened)
    menuHooked = true
    return true
end

-- Hooks the OnShow of each legacy DropDownListN that exists (they are real frames, built before any addon loads). Idempotent.
function DropdownSkins.HookLegacy()
    for i = 1, 3 do
        local list = _G["DropDownList" .. i]
        if IsTable(list) and not legacyHooked[list] then
            legacyHooked[list] = true
            Kit.HookScript(list, "OnShow", function(self) Run(self) end)
        end
    end
end

DropdownSkins.HookMenus()
DropdownSkins.HookLegacy()
Kit.Later(function()
    DropdownSkins.HookMenus()
    DropdownSkins.HookLegacy()
end)
