-- Forever STUwave: TabSkins
-- The tabs of the shared controls kit (mockups/shared-controls-2026-11-12.html, section 1): the slanted strip tab, skinned in
-- place on a stock tab button, and the switch, a reusable widget for the two or three tab form that nothing mounts yet.
--
-- The strip tab is the cast bar's shape: a parallelogram 28 tall whose sides lean 8 across the full height.
--
--   idle      ink face, 1 px dim edge, muted text           hover     cyan edge, violet cell face, light text
--   selected  pink on a #2a0f2e face with one more row of fill under it, no edge but a 4 tall chevron strip along the top
--             (the cast bar's chevrons, marching one pitch every 0.6 s) and a 1 px pink diagonal on each side, pink text
--   disabled  darkest ink, dim edge and text, no hover      news     a 4 square amber LED near the right end, breathing
--
-- Skin only. A stock tab keeps its rect, its scripts and its attributes: its Left, Middle, Right, Active and Highlight art is held
-- at alpha 0 (FS.HeldArt; the shown state stays as Blizzard wrote it and stays readable), our plate is regions of the tab
-- itself (under the label), and we follow it by post-hooks (OnEnter, OnLeave, OnMouseDown, OnMouseUp, OnShow, OnSizeChanged,
-- OnEnable, OnDisable, Enable, Disable, SetEnabled, and on a TabSystem button SetTabSelected, SetTabEnabled and
-- SetTabNotification) and by hooksecurefunc on PanelTemplates_SelectTab, DeselectTab and SetDisabledTabState, the three
-- functions that write a PanelTab's state. Those functions (and the engine, on every font object change) rewrite the label
-- too, so the label's mono font, colour and seat are put back after each. The plate is as wide as the stock rect (nothing is
-- resized) and 28 tall, from the top of the rect, or from the bottom of it on a top tab (isTopTab, isTabOnTop). A tab met in
-- combat is skinned when combat ends; a protected tab's label is not moved in combat.
--
-- Told by shape: a Button with the art of PanelTabButtonTemplate and TabSystemButtonTemplate (Left, Middle, Right, LeftActive,
-- MiddleActive and RightActive textures) and a label (`Text`). A UIPanelButton shares Left, Middle and Right but has no Active
-- art; a tab whose art another skin holds (the Mail header's) is left to it. Both are XML templates, never globals, so the
-- 16001 globals dump cannot confirm them; the shapes are read from the 12.1.0 Blizzard_SharedXML source and detected at
-- runtime. News is a TabSystem tab's notificationFrame (a frame from a pool other windows share, so it is left alone and our
-- LED shows beside it) or TabSkins.SetNews(tab, shown) for a window that keeps its own.
--
-- The switch (TabSkins.Switch) is its own frames: a body, an item per label, and the pink slug that slides to a newly chosen
-- item. See the function for its API.

local _, FS = ...

local Theme, HeldArt, Kit = FS.Theme, FS.HeldArt, FS.ControlKit
if not (Theme and HeldArt and Kit and FS.Layout and FS.Layout.Controls and FS.Layout.Controls.TAB_H and Theme.COLOR_CTRL_SEL) then return end

local TabSkins = {}
FS.TabSkins = TabSkins

local K = FS.Layout.Controls
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FILL, EDGE, DIAG = MEDIA .. "ctl_tab_fill.tga", MEDIA .. "ctl_tab_edge.tga", MEDIA .. "ctl_tab_diag.tga"
local CHEV4, CHEV3 = MEDIA .. "ctl_chevron_h4.tga", MEDIA .. "ctl_chevron_h3.tga"

local C = {
    ink = Theme.COLOR_CTRL_INK, dim = Theme.COLOR_CTRL_DIM, sel = Theme.COLOR_CTRL_SEL, cell = Theme.COLOR_CTRL_CELL,
    dis = Theme.COLOR_CTRL_DIS, disFill = Theme.COLOR_CTRL_DISFILL, disEdge = Theme.COLOR_CTRL_DISEDGE,
    text = Theme.COLOR_CTRL_TEXT, pink = Theme.COLOR_HEALTH, cyan = Theme.COLOR_POWER, muted = Theme.COLOR_MUTED,
    amber = Theme.COLOR_AMBER,
}

-- A bottom tab is a folder tab (live review 2026-11-12, AH mockup A): it hangs from the window's bottom border and wears
-- the window's own fill, fill alpha and border colour, square at the top, the panel's cut at its bottom right. The selected
-- one opens into the window (its border row is painted over) with a pink edge and rule. A top tab keeps the slanted strip.
local FOLDER = { H = 24, CUT = 6, GAP_MAX = 16, FILL_ALPHA = 0.92 }
C.bg, C.border = Theme.COLOR_BG, Theme.COLOR_BORDER

local function Weak() return setmetatable({}, { __mode = "k" }) end

local parts = Weak()    -- stock tab -> what we drew on it

local function IsTable(v) return type(v) == "table" end
local function Round(v) return math.floor(v + 0.5) end

local function InCombat() return type(InCombatLockdown) == "function" and InCombatLockdown() end

-------------------------------------------------------------------------------
-- The strip tab
-------------------------------------------------------------------------------

local ART = { "Left", "Middle", "Right", "LeftActive", "MiddleActive", "RightActive" }
local HELD = { "Left", "Middle", "Right", "LeftActive", "MiddleActive", "RightActive", "LeftHighlight", "MiddleHighlight",
    "RightHighlight" }

local function Held(region)
    if not IsTable(region) then return false end
    return Kit.Plain(Kit.Try(region.GetAlpha, region)) == 0
end

-- "tab" or nil.
function TabSkins.Kind(widget)
    if Kit.TypeOf(widget) ~= "Button" then return nil end
    for _, key in ipairs(ART) do
        if Kit.TypeOf(widget[key]) ~= "Texture" then return nil end
    end
    local label = widget.Text
    if not (IsTable(label) and type(label.SetFont) == "function") then return nil end
    if not parts[widget] and Held(widget.Left) then return nil end
    return "tab"
end

function TabSkins.Parts(widget) return parts[widget] end

local function IsSelected(widget)
    local flag = widget.isSelected -- TabSystem's own flag; a PanelTab shows its LeftActive art instead
    if flag ~= nil then return Kit.Plain(flag) == true end
    local active = widget.LeftActive
    return Kit.Plain(Kit.Try(active.IsShown, active)) == true
end

local function OnTop(widget)
    return widget.isTopTab == true or widget.isTabOnTop == true
end

local function ApplyMarch(p)
    local phase = p.phase or 0
    p.chev:SetTexCoord(-phase, -phase + (p.w - K.TAB_SLANT) / K.CHEV_PITCH, 0, 1)
end

local function SeatLabel(widget, p)
    local label = widget.Text
    if not (IsTable(label) and type(label.ClearAllPoints) == "function" and type(label.SetPoint) == "function") then return end
    if InCombat() and Kit.Plain(Kit.Try(widget.IsProtected, widget)) == true then
        if not p.labelWaits then
            p.labelWaits = true
            Kit.Defer(function()
                p.labelWaits = nil
                SeatLabel(widget, p)
            end)
        end
        return
    end
    local ppu = Kit.Ppu(widget)
    label:ClearAllPoints()
    local x = p.folder and (p.w - 2) / 2 or p.w / 2
    label:SetPoint("CENTER", widget, "TOPLEFT", x / ppu, -(p.top + (p.textY or K.TAB_TEXT_Y)) / ppu)
end

-- An icon tab (the spellbook's category tabs: a 36 x 35 Icon over a 44 x 32 button) is a key, not a strip tab: a square
-- cut-corner plate KEY.SIZE across centred on the stock rect, the icon KEY.INSET in from its edge, square, cropped past the
-- art's own frame and unmasked. Idle ink with the dim edge, hover cell and cyan, selected the selected fill with a 2 px pink
-- edge.
local KEY = { SIZE = 44, CUT = 6, INSET = 4, CROP = 0.08 }
local function LayoutKey(widget, p, w, h)
    local size = KEY.SIZE
    local x, y = Round((w - size) / 2), Round((h - size) / 2)
    p.w, p.h, p.top, p.fits = w, h, y, true
    local plate = p.key
    Kit.Place(plate.fill, widget, x, y, size, size)
    Kit.Place(plate.ring, widget, x, y, size, size)
    if plate.ring2 then Kit.Place(plate.ring2, widget, x + 1, y + 1, size - 2, size - 2) end
    Kit.Move(p.led, x + size - K.TAB_LED - 4, y + 4, K.TAB_LED, K.TAB_LED)
    local icon = widget.Icon
    if InCombat() and Kit.Plain(Kit.Try(widget.IsProtected, widget)) == true then return end
    if not p.iconCut then
        p.iconCut = true
        if IsTable(widget.IconMask) then Kit.Try(icon.RemoveMaskTexture, icon, widget.IconMask) end
        icon:SetTexCoord(KEY.CROP, 1 - KEY.CROP, KEY.CROP, 1 - KEY.CROP)
    end
    Kit.Place(icon, widget, x + KEY.INSET, y + KEY.INSET, size - 2 * KEY.INSET, size - 2 * KEY.INSET)
end

-- Physical pixels from the tab's top up to the bottom of the window it hangs from (the first ancestor whose bottom is within
-- reach), negative when the tab starts inside the window. nil when the tab hangs from no window (a strip inside a page),
-- and that tab keeps the slanted strip.
local function WindowGap(widget)
    local top = Kit.Plain(Kit.Try(widget.GetTop, widget))
    if type(top) ~= "number" then return nil end
    local ppu = Kit.Ppu(widget)
    local node = Kit.Try(widget.GetParent, widget)
    for _ = 1, 4 do
        if not IsTable(node) then return nil end
        local b = Kit.Plain(Kit.Try(node.GetBottom, node))
        if type(b) == "number" then
            local gap = Round((b - top) * ppu)
            if gap >= -8 and gap <= FOLDER.GAP_MAX then return gap end
        end
        node = Kit.Try(node.GetParent, node)
    end
    return nil
end

local function LayoutFolder(widget, p, w, gap)
    local y0 = -gap
    local H, cut = FOLDER.H - y0, FOLDER.CUT -- the bottom stays FOLDER.H under the tab's top; the top meets the window
    p.top, p.textY = y0, math.floor(H / 2)
    local f = p.fold
    Kit.Move(f.fill, 0, y0, w, H - cut)
    for r = 1, cut do
        Kit.Move(f.rows[r], 0, y0 + H - cut + r - 1, math.max(0, w - r), 1)
        Kit.Move(f.diag[r], w - 1 - r, y0 + H - cut + r - 1, 1, 1)
    end
    Kit.Move(f.left, 0, y0 - 1, 1, H + 1)
    Kit.Move(f.right, w - 1, y0 - 1, 1, H - cut + 1)
    Kit.Move(f.bottom, 0, y0 + H - 1, math.max(0, w - cut), 1)
    Kit.Move(f.rule, 3, y0 + H - 3, math.max(0, w - cut - 5), 1)
    Kit.Move(f.open, 1, y0 - 1, math.max(0, w - 2), 1)
    Kit.Move(p.led, w - K.TAB_LED_X, y0 + K.TAB_LED_Y, K.TAB_LED, K.TAB_LED)
    SeatLabel(widget, p)
end

local function Layout(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local w, h = Kit.SizePx(widget)
    if not w then return end
    if p.key then return LayoutKey(widget, p, w, h) end
    local gap = p.fold ~= nil and not OnTop(widget) and WindowGap(widget) or nil
    p.folder = gap ~= nil
    if p.folder then
        p.w, p.h = w, h
        p.fits = w > 2 * FOLDER.CUT
        return LayoutFolder(widget, p, w, gap)
    end
    p.textY = nil
    local s, th = K.TAB_SLANT, K.TAB_H
    local top = OnTop(widget) and math.max(0, h - th) or 0
    p.w, p.h, p.top = w, h, top
    p.fits = w > 2 * s -- a stock tab not yet sized (10 wide) has no room for two caps
    local mid = math.max(0, w - 2 * s)
    Kit.Move(p.fillL, 0, top, s, th)
    Kit.Move(p.fillM, s, top, mid, th)
    Kit.Move(p.fillR, w - s, top, s, th)
    Kit.Move(p.extra, 0, top + th, math.max(0, w - s), K.TAB_EXTRA)
    Kit.Move(p.edgeL, 0, top, s, th)
    Kit.Move(p.edgeR, w - s, top, s, th)
    Kit.Move(p.edgeTop, s, top, mid, 1)
    Kit.Move(p.edgeBottom, s, top + th - 1, mid, 1)
    Kit.Move(p.diagL, 0, top, s, th)
    Kit.Move(p.diagR, w - s, top, s, th)
    Kit.Move(p.chev, s, top, math.max(0, w - s), K.TAB_CHEV_H)
    Kit.Move(p.led, w - K.TAB_LED_X, top + K.TAB_LED_Y, K.TAB_LED, K.TAB_LED)
    ApplyMarch(p)
    SeatLabel(widget, p)
end

Kit.OnReseat(function()
    for widget in pairs(parts) do Layout(widget) end
end)

local function PaintFolder(widget, p, selected, disabled)
    local f = p.fold
    local fill, fa, edge, text = C.bg, FOLDER.FILL_ALPHA, C.border, C.muted
    if selected then
        edge, text = C.pink, C.pink
    elseif disabled then
        fill, fa, edge, text = C.disFill, 1, C.disEdge, C.dis
    elseif p.state.hover or p.state.pressed then
        fill, edge, text = C.cell, C.cyan, C.text
    end
    local on = p.fits
    f.fill:SetColorTexture(fill[1], fill[2], fill[3], fa)
    for r = 1, FOLDER.CUT do
        f.rows[r]:SetColorTexture(fill[1], fill[2], fill[3], fa)
        f.diag[r]:SetColorTexture(edge[1], edge[2], edge[3], 1)
    end
    for _, t in ipairs({ f.left, f.right, f.bottom }) do t:SetColorTexture(edge[1], edge[2], edge[3], 1) end
    for _, t in ipairs(f.all) do t:SetShown(on) end
    f.rule:SetShown(on and selected)
    f.open:SetShown(on and selected)
    for _, t in ipairs({ p.fillL, p.fillM, p.fillR, p.extra, p.edgeL, p.edgeR, p.edgeTop, p.edgeBottom, p.diagL, p.diagR,
        p.chev }) do t:Hide() end
    Kit.StopAnimate(widget, "march")
    return text
end

local function Paint(widget)
    local p = parts[widget]
    if not (p and p.built) then return end
    local selected = IsSelected(widget)
    local disabled = not selected and not Kit.IsEnabled(widget)
    if p.key then
        local fill, edge, px = C.ink, C.dim, 1
        if selected then
            fill, edge, px = C.sel, C.pink, 2
        elseif disabled then
            fill, edge = C.disFill, C.disEdge
        elseif p.state.hover or p.state.pressed then
            fill, edge = C.cell, C.cyan
        end
        Kit.PaintPlate(p.key, fill, 1, edge, 1, px)
        local news = p.news or IsTable(widget.notificationFrame)
        p.led:SetShown(news and true or false)
        if news then p.led:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], 1) end
        return
    end
    if p.folder then
        local text = PaintFolder(widget, p, selected, disabled)
        local news = p.news or IsTable(widget.notificationFrame)
        p.led:SetShown(p.fits and news and true or false)
        if p.fits and news then p.led:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], 1) end
        Kit.RestyleLabel(widget.Text, widget, K.TAB_TEXT, text)
        return
    end
    if p.fold then for _, t in ipairs(p.fold.all) do t:Hide() end end
    local fill, edge, text = C.ink, C.dim, C.muted
    if selected then
        fill, text = C.sel, C.pink
    elseif disabled then
        fill, edge, text = C.disFill, C.disEdge, C.dis
    elseif p.state.hover or p.state.pressed then
        fill, edge, text = C.cell, C.cyan, C.text
    end
    local on = p.fits
    for _, t in ipairs({ p.fillL, p.fillR }) do
        t:SetVertexColor(fill[1], fill[2], fill[3], 1)
        t:SetShown(on)
    end
    p.fillM:SetColorTexture(fill[1], fill[2], fill[3], 1)
    p.fillM:SetShown(on)
    p.extra:SetColorTexture(fill[1], fill[2], fill[3], 1)
    p.extra:SetShown(on and selected)
    for _, t in ipairs({ p.edgeL, p.edgeR }) do
        t:SetVertexColor(edge[1], edge[2], edge[3], 1)
        t:SetShown(on and not selected)
    end
    for _, t in ipairs({ p.edgeTop, p.edgeBottom }) do
        t:SetColorTexture(edge[1], edge[2], edge[3], 1)
        t:SetShown(on and not selected)
    end
    p.diagL:SetShown(on and selected)
    p.diagR:SetShown(on and selected)
    p.chev:SetShown(on and selected)
    if on and selected then
        if not Kit.IsAnimating(widget, "march") then
            p.phase = 0
            ApplyMarch(p)
            Kit.Animate(widget, "march", function(_, elapsed)
                p.phase = (elapsed % K.MARCH_PERIOD) / K.MARCH_PERIOD
                ApplyMarch(p)
            end)
        end
    else
        Kit.StopAnimate(widget, "march")
    end

    local news = p.news or IsTable(widget.notificationFrame)
    p.led:SetShown(on and news and true or false)
    if on and news then
        p.led:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], 1)
        if not Kit.IsAnimating(widget, "led") then
            Kit.Animate(widget, "led", function(_, elapsed)
                p.led:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
            end)
        end
    else
        Kit.StopAnimate(widget, "led")
    end

    -- Blizzard writes the label's font object (and so its colour) on every state change; ours is painted after it
    Kit.RestyleLabel(widget.Text, widget, K.TAB_TEXT, text)
end

local function Refresh(widget)
    local ok, err = pcall(function()
        Layout(widget)
        Paint(widget)
    end)
    if not ok then Kit.Fail("tab", err) end
end

-- Sets whether a window that keeps its own news shows the LED on this tab (a TabSystem tab's notification frame shows it by
-- itself).
function TabSkins.SetNews(widget, shown)
    local p = parts[widget]
    if not p then return end
    p.news = shown and true or false
    Paint(widget)
end

local function Build(widget)
    local p = { kind = "tab", w = 0, h = 0, top = 0, fits = false } -- nothing shows until the first layout has the tab's size
    parts[widget] = p -- marked first, so a failure part way is not retried into a second set of layers

    for _, key in ipairs(HELD) do HeldArt.Hold(widget[key]) end
    if IsTable(widget.TabTextures) then
        for _, region in ipairs(widget.TabTextures) do HeldArt.Hold(region) end
    end
    HeldArt.Hold(Kit.Try(widget.GetHighlightTexture, widget))

    local s, th = K.TAB_SLANT, K.TAB_H
    local capU, capV = s / K.TAB_ART, th / K.TAB_ART
    local function cap(path, layer, sub, color, flip)
        local t = Kit.Glyph(widget, path, 0, 0, s, th, color, 1, layer, sub)
        if flip then t:SetTexCoord(capU, 0, capV, 0) else t:SetTexCoord(0, capU, 0, capV) end
        return t
    end
    p.fillL, p.fillR = cap(FILL, "BACKGROUND", -6, C.ink, false), cap(FILL, "BACKGROUND", -6, C.ink, true)
    p.fillM = Kit.Rect(widget, s, 0, 1, th, C.ink, 1, "BACKGROUND", -6)
    p.extra = Kit.Rect(widget, 0, th, 1, K.TAB_EXTRA, C.sel, 1, "BACKGROUND", -6)
    p.edgeL, p.edgeR = cap(EDGE, "BORDER", 1, C.dim, false), cap(EDGE, "BORDER", 1, C.dim, true)
    p.edgeTop = Kit.Rect(widget, s, 0, 1, 1, C.dim, 1, "BORDER", 1)
    p.edgeBottom = Kit.Rect(widget, s, th - 1, 1, 1, C.dim, 1, "BORDER", 1)
    p.diagL, p.diagR = cap(DIAG, "BORDER", 2, C.pink, false), cap(DIAG, "BORDER", 2, C.pink, true)
    p.chev = Kit.Glyph(widget, CHEV4, s, 0, 1, K.TAB_CHEV_H, C.pink, K.TAB_CHEV_ALPHA, "BORDER", 3)
    p.chev:SetTexture(CHEV4, "REPEAT", "REPEAT")
    p.led = Kit.Rect(widget, 0, K.TAB_LED_Y, K.TAB_LED, K.TAB_LED, C.amber, 1, "BORDER", 4)
    for _, t in ipairs({ p.extra, p.diagL, p.diagR, p.chev, p.led }) do t:Hide() end
    local f = { rows = {}, diag = {}, all = {} }
    local function R(color, layer, sub)
        local t = Kit.Rect(widget, 0, 0, 1, 1, color, 1, layer, sub)
        t:Hide()
        f.all[#f.all + 1] = t
        return t
    end
    f.fill = R(C.bg, "BACKGROUND", -6)
    for r = 1, FOLDER.CUT do f.rows[r] = R(C.bg, "BACKGROUND", -6) end
    f.open = R(C.bg, "BACKGROUND", -5)
    f.left, f.right, f.bottom = R(C.border, "BORDER", 1), R(C.border, "BORDER", 1), R(C.border, "BORDER", 1)
    for r = 1, FOLDER.CUT do f.diag[r] = R(C.border, "BORDER", 1) end
    f.rule = R(C.pink, "BORDER", 2)
    p.fold = f
    if IsTable(widget.Icon) and type(widget.Icon.SetTexCoord) == "function" then
        p.key = Kit.Plate(widget, KEY.CUT, KEY.SIZE, KEY.SIZE)
        for _, t in ipairs({ p.fillL, p.fillM, p.fillR, p.extra, p.edgeL, p.edgeR, p.edgeTop, p.edgeBottom, p.diagL, p.diagR,
            p.chev }) do t:Hide(); t:SetAlpha(0) end
    end
    p.built = true

    p.state = Kit.Track(widget, Paint)
    for _, method in ipairs({ "SetTabSelected", "SetTabEnabled", "SetTabNotification" }) do
        Kit.HookFunc(widget, method, function() Refresh(widget) end)
    end
    Kit.HookScript(widget, "OnSizeChanged", function() Refresh(widget) end)
    Kit.HookScript(widget, "OnShow", function() Refresh(widget) end)
    Refresh(widget)
    Kit.Later(function() Refresh(widget) end)
end

-- Skins one stock tab button. Idempotent; returns true when it skinned now. A tab met in combat is skinned when combat ends.
function TabSkins.Skin(widget)
    if type(widget) ~= "table" or parts[widget] or not TabSkins.Kind(widget) then return false end
    if InCombat() then
        Kit.Defer(function() TabSkins.Skin(widget) end)
        return false
    end
    local ok, err = pcall(Build, widget)
    if not ok then Kit.Fail("tab", err) end
    return ok and parts[widget] ~= nil
end

Kit.Register("tab", {
    match = function(widget) return parts[widget] ~= nil or TabSkins.Kind(widget) ~= nil end,
    skin = TabSkins.Skin, parts = TabSkins.Parts,
})

-- PanelTab state is written by three plain functions, not by methods of the tab: PanelTemplates_SelectTab, DeselectTab and
-- SetDisabledTabState. They set the label's point and font as well, so the hook lays the tab out again after each.
if type(hooksecurefunc) == "function" then
    for _, name in ipairs({ "PanelTemplates_SelectTab", "PanelTemplates_DeselectTab", "PanelTemplates_SetDisabledTabState" }) do
        if type(_G[name]) == "function" then
            pcall(hooksecurefunc, name, function(tab)
                if IsTable(tab) and parts[tab] then Refresh(tab) end
            end)
        end
    end
end

-------------------------------------------------------------------------------
-- The switch
-------------------------------------------------------------------------------

local function ItemWidth(text)
    local len = type(_G.strlenutf8) == "function" and _G.strlenutf8(text) or #text
    return math.ceil((len * K.TAG_CHAR + K.SWITCH_ITEM_PAD) / K.SWITCH_STEP - 1e-9) * K.SWITCH_STEP
end

-- Seats a plate's three layers on `host` (a frame w x h physical pixels).
local function SeatPlate(plate, host, w, h)
    Kit.Place(plate.fill, host, 0, 0, w, h)
    Kit.Place(plate.ring, host, 0, 0, w, h)
    if plate.ring2 then Kit.Place(plate.ring2, host, 1, 1, w - 2, h - 2) end
end

local function ApplyUnder(sw)
    local width = sw.slugW - 2 * K.SWITCH_UNDER_INSET
    local phase = sw.phase or 0
    sw.under:SetTexCoord(-phase, -phase + width / K.CHEV_PITCH, 0, K.SWITCH_UNDER_H / K.SWITCH_UNDER_TILE)
end

local function SeatSlug(sw, x, w)
    sw.slugX, sw.slugW = x, w
    Kit.Move(sw.slug, x, K.SWITCH_ITEM_Y, w, K.SWITCH_ITEM_H)
    SeatPlate(sw.slugPlate, sw.slug, w, K.SWITCH_ITEM_H)
    Kit.Move(sw.under, K.SWITCH_UNDER_INSET, K.SWITCH_UNDER_Y, w - 2 * K.SWITCH_UNDER_INSET, K.SWITCH_UNDER_H)
    ApplyUnder(sw)
end

local function PaintItem(sw, i)
    local item = sw.items[i]
    local selected, disabled = sw.selected == i, sw.disabled[i] == true
    local color = C.muted
    if selected then
        color = C.pink
    elseif disabled then
        color = C.dis
    elseif item.hover then
        color = C.text
    end
    Kit.Recolor(item.label, color)
    local box = item.hover and not selected and not disabled
    item.plate.fill:SetShown(box)
    item.plate.ring:SetShown(box)
end

local function Slide(sw, x1, w1)
    local x0, w0 = sw.slugX, sw.slugW
    Kit.Animate(sw.slug, "slide", function(_, elapsed)
        local progress = math.min(1, elapsed / K.SWITCH_SLIDE)
        local e = Kit.Ease.outQuad(progress)
        SeatSlug(sw, Round(x0 + (x1 - x0) * e), Round(w0 + (w1 - w0) * e))
        if progress >= 1 then Kit.StopAnimate(sw.slug, "slide") end
    end)
end

-- A header switch for two or three tabs: a 28 tall body of items whose selected one is a pink slug that slides to a newly chosen
-- item. `parent` is any frame; opts.x and opts.y seat the body that many physical pixels from the parent's top left, opts.selected
-- is the starting item (1), opts.disabled and opts.badges are { [index] = true } sets, opts.onSelect(index, text, switch) is
-- called when the player picks an item. Returns the switch:
--
--   switch:SetSelected(index, instant)   picks an item (quietly: no callback); a disabled item cannot be picked
--   switch:GetSelected()                 the picked index
--   switch:SetDisabled(index, bool)      an item that cannot be picked and wears the dim text
--   switch:SetBadge(index, bool)         a pink LED on an item that has news
--   switch.frame, switch.width, switch.items[i].button
--
-- It is not registered with the sweep and no window mounts it yet.
function TabSkins.Switch(parent, items, opts)
    opts = opts or {}
    local sw = { items = {}, selected = 1, disabled = {}, phase = 0 }
    local widths, total = {}, 2 * K.SWITCH_PAD
    for i, text in ipairs(items) do
        widths[i] = ItemWidth(text)
        total = total + widths[i]
    end
    sw.width = total

    local frame = CreateFrame("Frame", nil, parent)
    Kit.Place(frame, parent, opts.x or 0, opts.y or 0, total, K.SWITCH_H)
    sw.frame = frame
    sw.plate = Kit.Plate(frame, K.SWITCH_CUT, total, K.SWITCH_H)
    SeatPlate(sw.plate, frame, total, K.SWITCH_H)
    Kit.PaintPlate(sw.plate, C.ink, 1, C.dim, 1, 1)

    local level = frame:GetFrameLevel()
    local slug = CreateFrame("Frame", nil, frame)
    slug:SetFrameLevel(level + 1)
    sw.slug = slug
    sw.slugPlate = Kit.Plate(slug, K.SWITCH_ITEM_CUT, 1, K.SWITCH_ITEM_H)
    Kit.PaintPlate(sw.slugPlate, C.sel, 1, C.pink, 1, 1)
    sw.under = Kit.Glyph(slug, CHEV3, K.SWITCH_UNDER_INSET, K.SWITCH_UNDER_Y, 1, K.SWITCH_UNDER_H, C.pink,
        K.SWITCH_UNDER_ALPHA, "OVERLAY", 1)
    sw.under:SetTexture(CHEV3, "REPEAT", "REPEAT")

    local x = K.SWITCH_PAD
    for i, text in ipairs(items) do
        local w = widths[i]
        local button = CreateFrame("Button", nil, frame)
        button:SetFrameLevel(level + 2)
        Kit.Place(button, frame, x, K.SWITCH_ITEM_Y, w, K.SWITCH_ITEM_H)
        local item = { button = button, width = w, x = x }
        item.plate = Kit.Plate(button, K.SWITCH_ITEM_CUT, w, K.SWITCH_ITEM_H)
        SeatPlate(item.plate, button, w, K.SWITCH_ITEM_H)
        Kit.PaintPlate(item.plate, C.cell, 1, C.cyan, 1, 1)
        item.label = Kit.Label(button, text, K.TAB_TEXT, C.muted, "OVERLAY")
        Kit.Place(item.label, button, w / 2, K.SWITCH_TEXT_Y, nil, nil, "CENTER", "TOPLEFT")
        item.badge = Kit.Rect(button, w - K.SWITCH_BADGE_X, K.SWITCH_BADGE_Y, K.SWITCH_BADGE, K.SWITCH_BADGE, C.pink, 1,
            "OVERLAY", 2)
        item.badge:Hide()
        sw.items[i] = item

        button:SetScript("OnEnter", function()
            item.hover = true
            PaintItem(sw, i)
        end)
        button:SetScript("OnLeave", function()
            item.hover = false
            PaintItem(sw, i)
        end)
        button:SetScript("OnClick", function()
            if sw.disabled[i] or sw.selected == i then return end
            sw:SetSelected(i)
            if opts.onSelect then opts.onSelect(i, text, sw) end
        end)
        x = x + w
    end

    for i in pairs(opts.disabled or {}) do sw.disabled[i] = true end
    local start = sw.items[opts.selected or 1] and (opts.selected or 1) or 1
    sw.selected = start
    local first = sw.items[start]
    Kit.Place(slug, frame, first.x, K.SWITCH_ITEM_Y, first.width, K.SWITCH_ITEM_H)
    SeatSlug(sw, first.x, first.width)
    for i in ipairs(sw.items) do PaintItem(sw, i) end
    Kit.Animate(slug, "march", function(_, elapsed)
        sw.phase = (elapsed % K.MARCH_PERIOD) / K.MARCH_PERIOD
        ApplyUnder(sw)
    end)

    function sw:GetSelected() return self.selected end

    function sw:SetSelected(index, instant)
        local item = self.items[index]
        if not item or self.disabled[index] or index == self.selected then return end
        local old = self.selected
        self.selected = index
        PaintItem(self, old)
        PaintItem(self, index)
        if instant or not (type(self.frame.IsVisible) == "function" and self.frame:IsVisible()) then
            Kit.StopAnimate(self.slug, "slide")
            SeatSlug(self, item.x, item.width)
        else
            Slide(self, item.x, item.width)
        end
    end

    function sw:SetDisabled(index, disabled)
        if not self.items[index] then return end
        self.disabled[index] = disabled and true or nil
        PaintItem(self, index)
    end

    function sw:SetBadge(index, shown)
        local item = self.items[index]
        if not item then return end
        item.badge:SetShown(shown and true or false)
        if shown then
            item.badge:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], 1)
            if not Kit.IsAnimating(item.button, "badge") then
                Kit.Animate(item.button, "badge", function(_, elapsed)
                    item.badge:SetColorTexture(C.pink[1], C.pink[2], C.pink[3], Kit.Pulse(elapsed, K.LED_PULSE, K.LED_FLOOR))
                end)
            end
        else
            Kit.StopAnimate(item.button, "badge")
        end
    end

    for i in pairs(opts.badges or {}) do sw:SetBadge(i, true) end
    return sw
end
