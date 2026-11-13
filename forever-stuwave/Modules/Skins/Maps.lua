-- Forever STUwave: World map chrome and the map quest log
-- The window around the world map (its border frame, the title, the tutorial and maximize keys), the breadcrumb, the keys on the
-- canvas (tracking filter, pin, side panel toggle) and the quest log beside the map (side tabs, settings key, headers, quest rows,
-- the campaign banner, the zone story), restyled in place from the SURVEY TABLE and QUEST RAIL sections of the MAPS + BESPOKE
-- mockup (mockups/maps-bespoke-2026-11-12.html, sections 1 and 2). WorldMapFrame and QuestMapFrame already wear the shared panel
-- skin (Panels.lua: chrome, fill, close key, the controls sweep for the floor dropdown, the search box and the text buttons); this
-- file adds the parts that were still stock. The map canvas and its pins stay the game's own.
--
-- Skin only, as in Commerce.lua and Character.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard
-- frame, post-hooks and alpha holds (FS.HeldArt) only, so every click, tooltip, zoom, quest pick and track toggle stays stock. Names
-- are the real 12.1 tree (Blizzard_WorldMap, Blizzard_UIPanels_Game QuestMapFrame.xml and WarCampaignTemplates.xml,
-- Blizzard_FrameXML NavigationBar.xml, Blizzard_SharedXML list and side tab templates); each is feature-detected and a missing
-- frame is skipped silently. The border frame of the map is a nested child the generic strip never reaches: it is held here, and
-- WorldMapFrame's own panel chrome (and its stuwave://map title band) shows through where the stock gold frame used to be.
--
-- A pooled row (a quest title, an objective line, a header, the campaign banner) is skinned once, guarded by a weak table, whenever
-- the stock list is rebuilt (post-hooks on QuestLogQuests_Update and QuestMapFrame_UpdateAll), and every row is painted again after
-- each rebuild and each change of the selected quest. The quest colour (its difficulty) is the stock code's and is never pinned.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the header switch between the full map and the quest log (it would call a Blizzard button from our code), the
-- surveyor rulers and the cursor tick on the canvas edges, the cursor and player read-outs moved onto the header (the stock
-- coordinates keep their place and only change type), the rail line and the quest level, count and daily chips of a row, the pip
-- chain of the campaign banner, the charge pips of an objective, the label tabs above the search box (the stock side tabs are
-- keys in place), and the Events and Map Legend pages. Map pins stay stock.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Char.Box and Char.PaintBox and Char.PinColor and Char.List
    and PanelSkins.RequireExport(Theme.ApplyMono, "Maps.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit or FS.CharacterSkin missing")) then
    return
end

local M = {}
FS.MapsSkin = M

local C = {
    violet = Theme.COLOR_BORDER, cyan = Theme.COLOR_POWER, pink = Theme.COLOR_HEALTH, amber = Theme.COLOR_AMBER,
    muted = Theme.COLOR_MUTED, ink = Theme.COLOR_CTRL_INK, text = Theme.COLOR_CTRL_TEXT or { 0.914, 0.886, 1 },
    dim = Theme.COLOR_CTRL_DIM or { 0.294, 0.165, 0.525 }, band = Theme.COLOR_CTRL_BAND or { 0.102, 0.051, 0.173 },
    row = { 0.059, 0.031, 0.125 }, amberInk = { 0.118, 0.071, 0.039 },
}
M.colors = C

local K = FS.Layout and FS.Layout.Controls or {}
local KEY, KEY_CUT = K.KEY or 20, K.KEY_CUT or 4

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { keys = Weak(), nav = Weak(), titles = Weak(), headers = Weak(), banners = Weak(), objectives = Weak(), done = {}, rules = {} }
M.state = S

local Plain, Try, List = Kit.Plain, Kit.Try, Char.List

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("maps:" .. name, ("|cffff4488Forever STUwave|r: map skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function Region(frame, key)
    return type(frame) == "table" and type(frame[key]) == "table" and frame[key] or nil
end

local function HoldKeys(frame, keys)
    if type(frame) ~= "table" then return end
    for _, key in ipairs(keys) do
        local part = frame[key]
        if type(part) == "table" then
            if Kit.TypeOf(part) == "Texture" then HeldArt.Hold(part) else Kit.HoldFrame(part) end
        end
    end
end

local function HoldRegions(frame, keep)
    for _, region in ipairs(List(frame, "GetRegions")) do
        if not (keep and keep[region]) then HeldArt.Hold(region) end
    end
end

-- A stock label in mono at `px`, in `color`.
local function Mono(fs, host, px, color)
    if type(fs) == "table" then Kit.RestyleLabel(fs, host, px, color or C.text) end
end

-- A stock label in mono that keeps the colour the stock code has given it (a quest difficulty, a state colour).
local function MonoKeep(fs, host, px)
    if type(fs) ~= "table" or type(fs.GetTextColor) ~= "function" then return end
    local r, g, b = Try(fs.GetTextColor, fs)
    r, g, b = Plain(r), Plain(g), Plain(b)
    Mono(fs, host, px, (type(r) == "number" and type(g) == "number" and type(b) == "number") and { r, g, b } or C.text)
end

local function ShownRegion(region)
    return type(region) == "table" and Plain(Try(region.IsShown, region)) == true
end

local function WatchShown(region, fn)
    for _, m in ipairs({ "Show", "Hide", "SetShown" }) do Kit.HookFunc(region, m, fn) end
end

-- A solid rectangle seated by its own anchors (not the kit's top left origin): `point` of the rect at `relPoint` of `ref`, offset
-- (x, y) physical pixels (y down), w x h pixels. Recorded, so a change of pixel scale seats it again.
local function Seat(obj, ref, point, relPoint, x, y, w, h, host)
    Kit.Place(obj, ref, x, y, w, h, point, relPoint, host or ref)
    return obj
end

-------------------------------------------------------------------------------
-- A cut key on a stock button
-------------------------------------------------------------------------------

local function PaintKey(btn)
    local k = S.keys[btn]
    if not k then return end
    local on = Kit.IsEnabled(btn)
    local st = k.state
    local hover = on and st and (st.hover or st.pressed)
    local selected = k.selected and k.selected() or false
    local glow = k.glowing and k.glowing() or false
    local edge, fill, px = k.idle or C.violet, C.ink, 1
    if not on then edge = C.dim
    elseif selected then edge, fill, px = C.pink, C.band, 2
    elseif glow then edge, px = C.amber, 2
    elseif hover then edge, px = C.cyan, 2 end
    Kit.PaintPlate(k.plate, fill, 1, edge, on and 1 or 0.6, px)
    local g = (hover or selected) and C.text or (k.tint or C.cyan)
    for _, t in ipairs(k.glyph) do
        t:SetColorTexture(g[1], g[2], g[3], 1)
        t:SetAlpha(on and 1 or 0.35)
    end
    if k.label then Kit.Recolor(k.label, g) end
    local icon = k.icon
    if type(icon) == "table" and type(icon.SetVertexColor) == "function" then
        local t = k.tint
        if t then
            local v = on and 1 or 0.45
            pcall(icon.SetVertexColor, icon, t[1] * v, t[2] * v, t[3] * v, 1)
        else
            local v = (hover or selected) and 1 or (on and 0.72 or 0.4)
            pcall(icon.SetVertexColor, icon, v, v, v, 1)
        end
    end
end

-- Cut-corner key `size` px across centred on the stock button. The stock art is held FIRST (HeldArt.HoldButton holds every region
-- the button has at that moment, so a plate made before it would be held invisible too), except `opts.keep` (the icon that is the
-- picture). opts: size, cut, keep (a set), icon (tinted with the state), tint, idle (edge colour), selected() and glowing() (state
-- the stock widget holds), glyph (a function(key) that draws cells on the button and returns them), label (text drawn centred).
local function Key(btn, opts)
    if type(btn) ~= "table" or type(btn.CreateTexture) ~= "function" then return nil end
    if S.keys[btn] then return S.keys[btn] end
    opts = opts or {}
    HeldArt.HoldButton(btn, opts.keep)
    local size, cut = opts.size or KEY, opts.cut or KEY_CUT
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or size, bh or size
    local x, y = math.floor((bw - size) / 2), math.floor((bh - size) / 2)
    local k = { plate = Kit.Plate(btn, cut, size, size), glyph = {}, x = x, y = y, size = size, icon = opts.icon, tint = opts.tint,
        idle = opts.idle, selected = opts.selected, glowing = opts.glowing }
    Kit.Place(k.plate.fill, btn, x, y, size, size)
    Kit.Place(k.plate.ring, btn, x, y, size, size)
    if k.plate.ring2 then Kit.Place(k.plate.ring2, btn, x + 1, y + 1, size - 2, size - 2) end
    if opts.glyph then k.glyph = opts.glyph(btn, x, y, size) or {} end
    if opts.label then
        k.label = Kit.Label(btn, opts.label, opts.labelPx or 14, C.cyan, "OVERLAY")
        k.label:ClearAllPoints()
        k.label:SetPoint("CENTER", btn, "CENTER", 0, 0)
    end
    S.keys[btn] = k
    -- a gold stock icon is tinted from grey, or a cyan tint would come out green
    if opts.tint and type(opts.icon) == "table" and type(opts.icon.SetDesaturated) == "function" then pcall(opts.icon.SetDesaturated, opts.icon, true) end
    k.state = Kit.Track(btn, PaintKey)
    for _, script in ipairs({ "OnEnable", "OnDisable", "OnShow" }) do Kit.HookScript(btn, script, PaintKey) end
    for _, m in ipairs({ "Enable", "Disable", "SetEnabled" }) do Kit.HookFunc(btn, m, function() PaintKey(btn) end) end
    PaintKey(btn)
    return k
end

-- Cells of a glyph, {x, y, w, h} each, at (gx, gy) px of `btn`.
local function Cells(btn, gx, gy, cells)
    local out = {}
    for _, c in ipairs(cells) do out[#out + 1] = Kit.Rect(btn, gx + c[1], gy + c[2], c[3], c[4], C.cyan, 1, "OVERLAY", 7) end
    return out
end

local GLYPH_BOX = { { 0, 0, 10, 2 }, { 0, 8, 10, 2 }, { 0, 2, 2, 6 }, { 8, 2, 2, 6 } }
local GLYPH_BAR = { { 0, 8, 10, 2 } }

local function CenteredGlyph(cells, gw, gh)
    return function(btn, x, y, size) return Cells(btn, x + math.floor((size - gw) / 2), y + math.floor((size - gh) / 2), cells) end
end

-- The five cells of a chevron, 2 px each: right pointing (6 wide, 10 tall) or down (10 wide, 6 tall) or left pointing.
local function ChevronCells(dir)
    local out = {}
    for i = 0, 4 do
        local d = math.abs(i - 2)
        if dir == "right" then out[#out + 1] = { (2 - d) * 2, i * 2, 2, 2 }
        elseif dir == "left" then out[#out + 1] = { d * 2, i * 2, 2, 2 }
        else out[#out + 1] = { i * 2, (2 - d) * 2, 2, 2 } end
    end
    return out
end

local function ChevronGlyph(dir)
    local wide = dir == "down"
    return CenteredGlyph(ChevronCells(dir), wide and 10 or 6, wide and 6 or 10)
end

-------------------------------------------------------------------------------
-- The map window
-------------------------------------------------------------------------------

-- The panel's own title (stuwave://map, a label of ours) starts clear of the tutorial key, which sits where the stock portrait
-- ring was and straddles the top edge: right of it while it is shown, at the band's own inset when it is not (maximised).
function M.SeatTitle(win)
    local label = win.fsPanelTitle
    local border = Region(win, "BorderFrame")
    local tut = border and border.Tutorial
    if type(label) ~= "table" or type(label.SetPoint) ~= "function" then return end
    local x = 10
    if type(tut) == "table" and ShownRegion(tut) then
        local w = Plain(Try(tut.GetWidth, tut))
        x = 43 + (type(w) == "number" and w or 46) + 4
    end
    local inset = Theme.PanelBandInset and Theme.PanelBandInset() or 2
    label:ClearAllPoints()
    label:SetPoint("LEFT", win, "TOPLEFT", x, -(inset + (Theme.PANEL_HEADER_H or 18) / 2))
end

local function SkinBorder(win)
    local b = Region(win, "BorderFrame")
    if not b then return end
    HoldKeys(b, { "NineSlice", "PortraitContainer", "Bg", "TopTileStreaks", "InsetBorderTop", "Underlay" })
    -- the stock title: the panel's own stuwave://map band names the window
    local title = Region(b, "TitleContainer")
    if title then Kit.HoldFrame(title.TitleText) end
    local tut = Region(b, "Tutorial")
    if tut then
        Key(tut, { size = KEY, cut = KEY_CUT, label = "?", labelPx = 14 })
        if not S.done.tutHook then
            S.done.tutHook = true
            for _, script in ipairs({ "OnShow", "OnHide" }) do Kit.HookScript(tut, script, function() M.SeatTitle(win) end) end
        end
    end
    local mm = Region(b, "MaximizeMinimizeFrame")
    if mm then
        if mm.MaximizeButton then Key(mm.MaximizeButton, { glyph = CenteredGlyph(GLYPH_BOX, 10, 10) }) end
        if mm.MinimizeButton then Key(mm.MinimizeButton, { glyph = CenteredGlyph(GLYPH_BAR, 10, 10) }) end
    end
    -- the cyan ring round the canvas, on a frame of ours above the held border art
    local canvas = Region(win, "ScrollContainer")
    if canvas and not S.ring then
        local host = CreateFrame("Frame", nil, b)
        host:SetAllPoints(b)
        if host.EnableMouse then host:EnableMouse(false) end
        S.ringHost = host
        S.ring = Char.Box(host, "OVERLAY", canvas)
        Char.PaintBox(S.ring, { 0, 0, 0 }, 0, C.cyan, 1, 1)
    end
    M.SeatTitle(win)
end

-------------------------------------------------------------------------------
-- The breadcrumb: a route of nodes
-------------------------------------------------------------------------------

local NAV = { NODE = 8, CURRENT = 12, GAP = 6, LINE_FROM = 4, LINE_TO = 18, PULSE = 3, PERIOD = 1.6 }

local function IsCurrent(b) return not Kit.IsEnabled(b) end

local function PaintNav(b)
    local rec = S.nav[b]
    if not rec then return end
    local current = IsCurrent(b)
    local hover = rec.state and rec.state.hover
    local color = current and C.cyan or (hover and C.cyan or C.text)
    local size = current and NAV.CURRENT or NAV.NODE
    if rec.node then
        Kit.Move(rec.node, -NAV.GAP, 0, size, size)
        rec.node:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], current and 1 or 0.7)
    end
    if rec.under then rec.under:SetShown(hover and not current and true or false) end
    if rec.label then Kit.Recolor(rec.label, color) end
    if b.text then
        Kit.RestyleLabel(b.text, b, 12, color)
    end
    if rec.line then rec.line:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.55) end
end

-- The anchors of a line run from the right end of `from` to the left end of `to` (both stock labels), so it follows the text
-- width the stock bar chose and needs no measuring.
local function SeatLine(line, from, to, host)
    line:ClearAllPoints()
    line:SetPoint("LEFT", from, "RIGHT", Kit.U(host, NAV.LINE_FROM), 0)
    line:SetPoint("RIGHT", to, "LEFT", -Kit.U(host, NAV.LINE_TO), 0)
    line:SetHeight(Kit.U(host, 1))
end

local function SkinNavButton(b)
    if type(b) ~= "table" or S.nav[b] or type(b.text) ~= "table" or type(b.CreateTexture) ~= "function" then return end
    local rec = {}
    S.nav[b] = rec
    HeldArt.HoldButton(b)
    HeldArt.Hold(b.arrowUp); HeldArt.Hold(b.arrowDown); HeldArt.Hold(b.selected); HeldArt.Hold(b.Left)
    local menu = Region(b, "MenuArrowButton")
    if menu then
        HeldArt.HoldButton(menu, menu.Art and { [menu.Art] = true } or nil)
        if menu.Art and menu.Art.SetVertexColor then pcall(menu.Art.SetVertexColor, menu.Art, C.cyan[1], C.cyan[2], C.cyan[3], 1) end
    end
    rec.node = Kit.Rect(b, 0, 0, NAV.NODE, NAV.NODE, C.cyan, 1, "OVERLAY", 7)
    Seat(rec.node, b.text, "RIGHT", "LEFT", -NAV.GAP, 0, NAV.NODE, NAV.NODE, b)
    rec.line = b:CreateTexture(nil, "OVERLAY", nil, 7)
    rec.line:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.55)
    Kit.Snap(rec.line)
    rec.line:Hide()
    rec.under = b:CreateTexture(nil, "OVERLAY", nil, 7)
    rec.under:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    Kit.Snap(rec.under)
    rec.under:ClearAllPoints()
    rec.under:SetPoint("TOPLEFT", b.text, "BOTTOMLEFT", 0, -Kit.U(b, 2))
    rec.under:SetPoint("TOPRIGHT", b.text, "BOTTOMRIGHT", 0, -Kit.U(b, 2))
    rec.under:SetHeight(Kit.U(b, 2))
    rec.under:Hide()
    S.rules[#S.rules + 1] = function()
        rec.under:ClearAllPoints()
        rec.under:SetPoint("TOPLEFT", b.text, "BOTTOMLEFT", 0, -Kit.U(b, 2))
        rec.under:SetPoint("TOPRIGHT", b.text, "BOTTOMRIGHT", 0, -Kit.U(b, 2))
        rec.under:SetHeight(Kit.U(b, 2))
    end
    rec.state = Kit.Track(b, PaintNav)
    for _, script in ipairs({ "OnEnable", "OnDisable", "OnShow" }) do Kit.HookScript(b, script, PaintNav) end
    PaintNav(b)
end

-- The overflow button (the stock "..." stop when the route is too long): a label of dots in place of the stock art.
local function SkinOverflow(b)
    if type(b) ~= "table" or S.nav[b] or type(b.CreateTexture) ~= "function" then return end
    local rec = { overflow = true }
    S.nav[b] = rec
    HeldArt.HoldButton(b)
    rec.label = Kit.Label(b, "...", 12, C.muted, "OVERLAY")
    rec.label:ClearAllPoints()
    rec.label:SetPoint("CENTER", b, "CENTER", 0, 0)
    rec.state = Kit.Track(b, function() Kit.Recolor(rec.label, (rec.state and rec.state.hover) and C.cyan or C.muted) end)
end

local function LayoutNav(bar)
    local list = Region(bar, "navList")
    if not list then return end
    for _, b in ipairs(list) do SkinNavButton(b) end
    local over = Region(bar, "overflowButton") or Region(bar, "overflow")
    if over then SkinOverflow(over) end
    local last
    for i, b in ipairs(list) do
        local rec = S.nav[b]
        if rec then
            local nxt = list[i + 1]
            local nrec = nxt and S.nav[nxt]
            local shown = nrec and ShownRegion(b) and ShownRegion(nxt)
            if shown then
                SeatLine(rec.line, b.text, nxt.text, b)
                rec.line:Show()
                last = rec.line
            else
                rec.line:Hide()
            end
            PaintNav(b)
        end
    end
    S.routeLine = last
end

local function StartRoute(bar)
    if S.pulse or type(bar.CreateTexture) ~= "function" then return end
    local pulse = bar:CreateTexture(nil, "OVERLAY", nil, 7)
    pulse:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    Kit.Snap(pulse)
    pulse:Hide()
    S.pulse = pulse
    Kit.Animate(bar, "route", function(_, elapsed)
        local line = S.routeLine
        if not (line and ShownRegion(line)) then pulse:Hide(); return end
        local w = Plain(Try(line.GetWidth, line))
        if type(w) ~= "number" or w <= 0 then pulse:Hide(); return end
        local p = (elapsed % NAV.PERIOD) / NAV.PERIOD
        local px = math.floor(p * math.max(0, w * Kit.Ppu(bar) - NAV.PULSE))
        Seat(pulse, line, "LEFT", "LEFT", px, 0, NAV.PULSE, NAV.PULSE, bar)
        pulse:Show()
    end)
end

local function SkinNavBar(win)
    local bar = Region(win, "NavBar")
    if not bar then return end
    HoldRegions(bar)
    HoldRegions(Region(bar, "overlay") or {})
    for _, key in ipairs({ "InsetBorderBottomLeft", "InsetBorderBottomRight", "InsetBorderBottom", "InsetBorderLeft", "InsetBorderRight" }) do
        HeldArt.Hold(bar[key])
    end
    LayoutNav(bar)
    StartRoute(bar)
    if not S.done.navHook then
        local installed = false
        for _, name in ipairs({ "NavBar_CheckLength", "NavBar_AddButton", "NavBar_Reset" }) do
            if type(_G[name]) == "function" then
                Kit.HookFunc(_G, name, function(self)
                    if self == bar then Step("nav", LayoutNav, bar) end
                end)
                installed = true
            end
        end
        S.done.navHook = installed
    end
end

-------------------------------------------------------------------------------
-- The keys on the canvas, the coordinates
-------------------------------------------------------------------------------

local MAP_KEY = 32

local function SkinOverlays(win)
    for _, f in ipairs(Region(win, "overlayFrames") or {}) do
        if type(f) == "table" then
            if f.FilterCounter then
                -- the tracking filter: a plate over its own icon (cyan), the count beside it
                Key(f, { size = MAP_KEY, keep = { [f.Icon] = true }, icon = f.Icon, tint = C.cyan })
                local counter = Region(f, "FilterCounter")
                if counter then Mono(counter.Count, counter, 11, C.pink); Char.PinColor(counter.Count, C.pink) end
            elseif f.IconOverlay and f.Icon then
                Key(f, { size = MAP_KEY, keep = { [f.Icon] = true }, icon = f.Icon, tint = C.amber })
            elseif f.CursorCoords and f.PlayerCoords then
                for _, spec in ipairs({ { f.CursorCoords, C.cyan }, { f.PlayerCoords, C.pink } }) do
                    local label = Region(spec[1], "Label")
                    if label then Mono(label, spec[1], 11, spec[2]); Char.PinColor(label, spec[2]) end
                end
            elseif f.OpenButton and f.CloseButton then
                Key(f.OpenButton, { size = MAP_KEY - 8, glyph = ChevronGlyph("left") })
                Key(f.CloseButton, { size = MAP_KEY - 8, glyph = ChevronGlyph("right") })
            end
        end
    end
end

-------------------------------------------------------------------------------
-- The quest log: side tabs, settings key, texts
-------------------------------------------------------------------------------

local TAB_KEY = 34

local function SkinTab(tab)
    if type(tab) ~= "table" or S.keys[tab] then return end
    local k = Key(tab, { size = TAB_KEY, cut = KEY_CUT, keep = tab.Icon and { [tab.Icon] = true } or nil, icon = tab.Icon, idle = C.dim,
        selected = function() return ShownRegion(tab.SelectedTexture) end,
        glowing = function() return type(tab.IsTabGlowAnimationPlaying) == "function" and Plain(Try(tab.IsTabGlowAnimationPlaying, tab)) == true end })
    if not k then return end
    HoldKeys(tab, { "Background", "SelectedTexture", "TabGlow", "HighlightTexture" })
    if tab.SelectedTexture then WatchShown(tab.SelectedTexture, function() PaintKey(tab) end) end
    for _, m in ipairs({ "SetChecked", "SetTabGlowAnimationPlaying" }) do Kit.HookFunc(tab, m, function() PaintKey(tab) end) end
    PaintKey(tab)
end

local function SkinSettings(btn)
    if type(btn) ~= "table" or S.keys[btn] then return end
    Key(btn, { size = KEY, keep = btn.Icon and { [btn.Icon] = true } or nil, icon = btn.Icon, tint = C.violet })
end

local function SkinLogFrame(qm)
    for _, key in ipairs({ "QuestsTab", "EventsTab", "MapLegendTab" }) do SkinTab(qm[key]) end
    local sf = _G.QuestScrollFrame
    if type(sf) == "table" then
        SkinSettings(sf.SettingsDropdown)
        Mono(sf.NoSearchResultsText, sf, 13, C.muted); Char.PinColor(sf.NoSearchResultsText, C.muted)
        Mono(sf.EmptyText, sf, 14, C.muted); Char.PinColor(sf.EmptyText, C.muted)
        local contents = sf.Contents
        if type(contents) == "table" then
            HoldKeys(contents.Separator, { "Divider" })
        end
        HoldKeys(sf, { "Edge" })
    end
    local sess = Region(qm, "QuestSessionManagement")
    if sess then
        HoldKeys(sess, { "BG" })
        Mono(sess.CommandText, sess, 12, C.text)
        Mono(sess.HelpText, sess, 11, C.muted)
        if not S.done.sess then
            S.done.sess = true
            Char.PaintBox(Char.Box(sess, "BORDER"), C.row, 1, C.dim, 1, 1)
        end
    end
end

-------------------------------------------------------------------------------
-- Headers, the campaign banner, the zone story
-------------------------------------------------------------------------------

local function PaintChevron(rec)
    local cb = rec.host
    local down = cb.collapsed ~= true
    rec.down = down
    local w, h = Kit.SizePx(cb)
    w, h = w or 24, h or 24
    local cells = ChevronCells(down and "down" or "right")
    local gw, gh = down and 10 or 6, down and 6 or 10
    local gx, gy = math.floor((w - gw) / 2), math.floor((h - gh) / 2)
    for i, c in ipairs(cells) do
        Kit.Move(rec.cells[i], gx + c[1], gy + c[2], c[3], c[4])
        rec.cells[i]:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    end
end

-- The chevron of a collapse button, its state kept on `rec` (rec.cells, rec.down, rec.host).
local function SkinChevron(cb, rec)
    if type(cb) ~= "table" or type(cb.CreateTexture) ~= "function" then return nil end
    HeldArt.HoldButton(cb)
    rec.host, rec.cells = cb, {}
    for i = 1, 5 do rec.cells[i] = Kit.Rect(cb, 0, 0, 2, 2, C.cyan, 1, "OVERLAY", 7) end
    Kit.HookFunc(cb, "UpdateCollapsedState", function() PaintChevron(rec) end)
    Kit.HookScript(cb, "OnShow", function() PaintChevron(rec) end)
    PaintChevron(rec)
    return rec
end

local function PaintHeaderText(h, over)
    local rec = S.headers[h]
    if not rec then return end
    local label = h.ButtonText or h.Text or h.text
    if type(label) ~= "table" then return end
    local hover = over
    if type(hover) ~= "boolean" then hover = rec.state and rec.state.hover or false end
    Kit.Recolor(label, hover and C.cyan or C.violet)
end

-- A list header (a zone, the covenant callings, a minimal campaign): the stock plate and plus held, a chevron on the collapse
-- button, a mono title in violet that lights cyan under the hand.
local function SkinHeader(h)
    if type(h) ~= "table" or S.headers[h] then return end
    local rec = {}
    S.headers[h] = rec
    HeldArt.HoldButton(h)
    SkinChevron(h.CollapseButton, rec)
    HoldKeys(h, { "Background", "SelectedHighlight", "HighlightTexture", "Highlight", "Divider" })
    local label = h.ButtonText or h.Text or h.text
    Mono(label, h, 12, C.violet)
    rec.state = Kit.Track(h, function() PaintHeaderText(h) end)
    Kit.HookFunc(h, "CheckHighlightTitle", function(_, over) PaintHeaderText(h, over) end)
    Kit.HookFunc(h, "SetText", function() PaintHeaderText(h) end)
    PaintHeaderText(h)
end

local function PaintBanner(f)
    local rec = S.banners[f]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    Char.PaintBox(rec.box, rec.fill or C.amberInk, 1, hover and rec.hot or rec.edge, 1, hover and 2 or 1)
end

-- The campaign banner and the zone story: the stock art held, an ink plate with an amber (campaign) or violet (story) edge, mono
-- title and progress.
local function SkinBanner(f, edge, hot, fill)
    if type(f) ~= "table" or S.banners[f] or type(f.CreateTexture) ~= "function" then return end
    HoldKeys(f, { "Background", "TopFiligree", "Divider", "SelectedHighlight", "HighlightTexture" })
    local rec = { edge = edge, hot = hot, fill = fill }
    S.banners[f] = rec
    rec.box = Char.Box(f, "BORDER")
    rec.state = Kit.Track(f, PaintBanner)
    Mono(f.Text, f, 12, C.text); Char.PinColor(f.Text, C.text)
    Mono(f.Progress, f, 11, edge); Char.PinColor(f.Progress, edge)
    local nxt = Region(f, "NextObjective")
    if nxt then MonoKeep(nxt.Text, nxt, 11) end
    if f.CollapseButton then SkinChevron(f.CollapseButton, rec) end
    PaintBanner(f)
end

-------------------------------------------------------------------------------
-- Quest rows
-------------------------------------------------------------------------------

local NODE_RING, NODE_CORE = 10, 6

local function QuestOf(btn)
    local id = Plain(btn.questID)
    return type(id) == "number" and id or nil
end

local function IsSuper(id)
    local st = _G.C_SuperTrack
    if not (id and type(st) == "table" and type(st.GetSuperTrackedQuestID) == "function") then return false end
    return Plain(Try(st.GetSuperTrackedQuestID)) == id
end

local function IsReady(id)
    local ql = _G.C_QuestLog
    if not (id and type(ql) == "table" and type(ql.IsComplete) == "function") then return false end
    return Plain(Try(ql.IsComplete, id)) == true
end

local function SeatReticle(rec, btn)
    local w, h = Kit.SizePx(btn)
    if w then Kit.SeatReticle(rec.reticle, 0, 0, w, h, 1, 6) end
end

local function PaintTitle(btn)
    local rec = S.titles[btn]
    if not (rec and rec.node) then return end
    local id = QuestOf(btn)
    local tracked = ShownRegion(btn.Checkbox and btn.Checkbox.CheckMark)
    local ready = IsReady(id)
    local selected = IsSuper(id)
    local hover = rec.state and rec.state.hover
    local lit = ready and C.amber or C.cyan
    Char.PaintBox(rec.node, C.ink, 1, (ready and C.amber) or ((tracked or hover) and C.cyan) or C.dim, 1, 1)
    rec.core:SetColorTexture(lit[1], lit[2], lit[3], 1)
    rec.core:SetShown(tracked or ready)
    if ready then
        if not Kit.IsAnimating(rec.core, "ready") then
            Kit.Animate(rec.core, "ready", function(_, elapsed)
                rec.core:SetColorTexture(C.amber[1], C.amber[2], C.amber[3], Kit.Pulse(elapsed, 1.6, 0.35))
            end)
        end
    else
        Kit.StopAnimate(rec.core, "ready")
    end
    if selected then rec.wash:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 0.10); rec.wash:Show()
    elseif hover then rec.wash:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.18); rec.wash:Show()
    else rec.wash:Hide() end
    SeatReticle(rec, btn)
    Kit.PaintReticle(rec.reticle, C.cyan, 1)
    Kit.ShowReticle(rec.reticle, selected)
end

local function SkinTitle(btn)
    if type(btn) ~= "table" or S.titles[btn] or type(btn.CreateTexture) ~= "function" then return end
    local rec = {}
    S.titles[btn] = rec
    local cb = Region(btn, "Checkbox")
    HeldArt.Hold(btn.HighlightTexture)
    if cb then
        HoldRegions(cb)
        local ref = cb:CreateTexture(nil, "BACKGROUND", nil, -8)
        Kit.Place(ref, cb, 0, 0, NODE_RING, NODE_RING, "CENTER", "CENTER", cb)
        rec.node = Char.Box(cb, "OVERLAY", ref)
        rec.core = Kit.Rect(cb, 0, 0, NODE_CORE, NODE_CORE, C.cyan, 1, "OVERLAY", 7)
        Seat(rec.core, cb, "CENTER", "CENTER", 0, 0, NODE_CORE, NODE_CORE)
        if cb.CheckMark then WatchShown(cb.CheckMark, function() PaintTitle(btn) end) end
    end
    rec.wash = btn:CreateTexture(nil, "BACKGROUND", nil, -7)
    rec.wash:SetAllPoints(btn)
    rec.wash:SetColorTexture(C.violet[1], C.violet[2], C.violet[3], 0.18)
    rec.wash:Hide()
    rec.reticle = Kit.Reticle(btn, "OVERLAY", 6)
    Kit.ShowReticle(rec.reticle, false)
    Kit.HookScript(btn, "OnSizeChanged", function() SeatReticle(rec, btn) end)
    MonoKeep(btn.Text, btn, 12)
    rec.state = Kit.Track(btn, PaintTitle)
    PaintTitle(btn)
end

local function SkinObjective(o)
    if type(o) ~= "table" or S.objectives[o] then return end
    S.objectives[o] = true
    MonoKeep(o.Dash, o, 11)
    MonoKeep(o.Text, o, 11)
end

local function EachActive(pool, fn)
    if type(pool) ~= "table" or type(pool.EnumerateActive) ~= "function" then return end
    pcall(function() for f in pool:EnumerateActive() do fn(f) end end)
end

function M.RefreshLog()
    local sf = _G.QuestScrollFrame
    if type(sf) ~= "table" then return end
    EachActive(sf.titleFramePool, function(f) Step("title", SkinTitle, f); Step("title.paint", PaintTitle, f) end)
    EachActive(sf.objectiveFramePool, function(f) Step("objective", SkinObjective, f) end)
    for _, pool in ipairs({ sf.headerFramePool, sf.campaignHeaderMinimalFramePool, sf.covenantCallingsHeaderFramePool }) do
        EachActive(pool, function(f) Step("header", SkinHeader, f) end)
    end
    EachActive(sf.campaignHeaderFramePool, function(f) Step("campaign", SkinBanner, f, C.amber, C.amber, C.amberInk) end)
    local contents = sf.Contents
    if type(contents) == "table" then Step("story", SkinBanner, contents.StoryHeader, C.violet, C.cyan, C.band) end
end

local function RepaintTitles()
    local sf = _G.QuestScrollFrame
    if type(sf) == "table" then EachActive(sf.titleFramePool, function(f) PaintTitle(f) end) end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

function M.Refresh()
    local win = _G.WorldMapFrame
    if type(win) ~= "table" then return end
    Step("border", SkinBorder, win)
    Step("nav", SkinNavBar, win)
    Step("overlays", SkinOverlays, win)
    local qm = _G.QuestMapFrame
    if type(qm) == "table" then
        Step("log", SkinLogFrame, qm)
        Step("rows", M.RefreshLog)
    end
end

local function BuildMap()
    local win = _G.WorldMapFrame
    if type(win) ~= "table" or S.done.map then return end
    S.done.map = true
    win.fsMapsSkin = true
    Kit.HookScript(win, "OnShow", function() Kit.Later(M.Refresh) end)
    for _, name in ipairs({ "HandleUserActionMaximizeSelf", "HandleUserActionMinimizeSelf", "Maximize", "Minimize" }) do
        Kit.HookFunc(win, name, function() Kit.Later(M.Refresh) end)
    end
    M.Refresh()
end

local function BuildLog()
    local qm = _G.QuestMapFrame
    if type(qm) ~= "table" or S.done.log then return end
    S.done.log = true
    qm.fsMapsSkin = true
    Kit.HookScript(qm, "OnShow", function() Kit.Later(M.Refresh) end)
    M.Refresh()
end

local function HookList()
    if S.done.listHook then return end
    local installed = false
    for _, name in ipairs({ "QuestLogQuests_Update", "QuestMapFrame_UpdateAll" }) do
        if type(_G[name]) == "function" then
            Kit.HookFunc(_G, name, function() M.RefreshLog() end)
            installed = true
        end
    end
    local sf = _G.QuestScrollFrame
    local contents = type(sf) == "table" and sf.Contents or nil
    if type(contents) == "table" then
        for _, m in ipairs({ "SelectButton", "ClearSelection" }) do Kit.HookFunc(contents, m, RepaintTitles) end
    end
    S.done.listHook = installed
end

local function Build()
    Step("build.map", BuildMap)
    Step("build.log", BuildLog)
    Step("build.hooks", HookList)
    if not S.done.reseat then
        S.done.reseat = true
        Kit.OnReseat(function()
            for _, rule in ipairs(S.rules) do pcall(rule) end
        end)
    end
end

-- The small kit this file built, for Bespoke.lua (the windows the mockup names after the map): the cut key on a stock button, the
-- glyph cells, and the hold and mono helpers. Nothing here is a Blizzard write.
M.kit = {
    Region = Region, HoldKeys = HoldKeys, HoldRegions = HoldRegions, Mono = Mono, MonoKeep = MonoKeep, ShownRegion = ShownRegion,
    WatchShown = WatchShown, Key = Key, Cells = Cells, CenteredGlyph = CenteredGlyph, ChevronGlyph = ChevronGlyph,
    GLYPH_BOX = GLYPH_BOX, GLYPH_BAR = GLYPH_BAR,
}

PanelSkins.RegisterInspect("Maps", { { name = "WorldMapFrame", guard = "fsMapsSkin" }, { name = "QuestMapFrame", guard = "fsMapsSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
