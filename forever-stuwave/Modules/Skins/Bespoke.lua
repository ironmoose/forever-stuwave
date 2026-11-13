-- Forever STUwave: The bespoke windows (calendar, achievements, dressing room, tabard, gem sockets, barber shop)
-- The windows the generic panel skin (Panels.lua) deliberately skips, restyled in place from sections 3 to 8 of the MAPS + BESPOKE
-- mockup (mockups/maps-bespoke-2026-11-12.html). Each one is parchment and gold art that is not a NineSlice the generic strip can
-- find: CalendarFrame draws ad hoc corner and edge textures, AchievementFrame is a BackdropTemplate with metal and wood borders,
-- DressUpFrame keeps its model backdrop as a direct Texture region, TabardFrame's emblem is four alpha ADD textures Blizzard only
-- ever fades, ItemSocketingFrame layers parchment under the filigree, and BarberShopFrame is the whole screen. So here every one of
-- them gets the shared panel chrome (Theme.SkinPanel with its own strip off: the Blizzard art is held, never hidden, and the parts
-- that carry meaning are left alone), its close key, the controls sweep, and then the window's own parts.
--
-- Skin only, as in Commerce.lua, Character.lua and Maps.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a
-- Blizzard frame, post-hooks and alpha holds (FS.HeldArt) only, so every click, tooltip, calendar day, achievement, socket and
-- customization stays stock. Names are the real 12.1 tree (Blizzard_Calendar, Blizzard_AchievementUI, Blizzard_UIPanels_Game
-- DressUpFrames.xml and TabardFrame.xml, Blizzard_ItemSocketingUI, Blizzard_BarbershopUI); each is feature-detected and a missing
-- frame is skipped silently. A window's art is held BEFORE our own regions exist (HeldArt.Hold zeroes the regions it finds now).
--
--   Calendar     the grid is kept as it is: 42 day cells become ink cells with a dim edge (cyan on hover, a violet 2 px edge and
--                lock-on brackets on the selected day, a cyan 2 px edge, tint and date chip on today), a day of another month is
--                dimmed, the weekday and month labels are mono, the month arrows are chevron keys, the day popups (view event,
--                view holiday, view raid, create event, picker) wear the panel chrome. Event rows keep their own colours.
--   Achievements the metal, wood and parchment frame is held; the category list, the achievement rows (an ink card, amber edge
--                when earned, pink when selected, the stock shield, icon and tracked check kept), the summary and statistics
--                rows, the header and the search results are plated and dark parchment text is lightened.
--   Dressing room the class backdrop of the model is held and the model sits in a violet box; the stock close, maximize and
--                appearance list keys are cut keys; the details panel's side frame is held.
--   Tabard       the outer frame art and the label bars are held (the four emblem textures are NOT: Blizzard only fades them),
--                the five pickers are plates with chevron keys, the rotate buttons are chevron keys, the cost box is a plate.
--   Gem sockets  the parchment, gold border and socket filigree are held; the gems, their colour brackets and the shine stay.
--   Barber shop  the vignettes are tinted, Cancel, Reset and Accept are the shared text buttons.
--
-- Left out on purpose, because the mockup shows a computed display and the rule for this pass is "keep the functionality the same
-- as vanilla": the calendar's today beam, the next up countdown with its ticking colon and the per day load pips; the achievement
-- medals that fill from the bottom, the glint on a finished one and the thin fill line under a category; the dressing room's
-- turntable ring, degree ticks, slot hotspots with leader lines and the scan sweep; the tabard's loom wires, swatch strips and
-- the lock-on on the model part a picker edits; the sockets' circuit trace between the gems and the staged ghosts; the barber
-- shop's notched dials (the options live in CharCustomizeFrame, shared with character creation, and are masked icon buttons the
-- skin cannot redraw in place), the ghost mark and delta tag, the mirror frame with its scanline, the receipt and the cost meter.

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, Maps = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.MapsSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and Maps and Maps.kit and Maps.colors and Char.Box and Char.PaintBox
    and PanelSkins.RequireExport(Theme.SkinPanel, "Bespoke.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.MapsSkin missing")) then
    return
end

local B = {}
FS.BespokeSkin = B

local C = Maps.colors
local K = FS.Layout and FS.Layout.Controls or {}
local KEY = K.KEY or 20
local MK = Maps.kit
local Region, HoldKeys, HoldRegions, Mono, MonoKeep, ShownRegion, WatchShown, Key =
    MK.Region, MK.HoldKeys, MK.HoldRegions, MK.Mono, MK.MonoKeep, MK.ShownRegion, MK.WatchShown, MK.Key
local ChevronGlyph, CenteredGlyph, GLYPH_BOX, GLYPH_BAR = MK.ChevronGlyph, MK.CenteredGlyph, MK.GLYPH_BOX, MK.GLYPH_BAR

local Plain, Try, List = Kit.Plain, Kit.Try, Char.List

local function Weak() return setmetatable({}, { __mode = "k" }) end
local S = { shells = Weak(), days = Weak(), rows = Weak(), cards = Weak(), slabs = Weak(), watched = Weak(), done = {} }
B.state = S

local logged = {}
local function Step(name, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok and not logged[name] then
        logged[name] = true
        FS.LogDegradeOnce("bespoke:" .. name, ("|cffff4488Forever STUwave|r: window skin step '%s' failed: %s"):format(name, tostring(err)))
    end
    return ok
end

local function Global(name)
    local v = _G[name]
    return type(v) == "table" and v or nil
end

local function Hold(obj)
    if type(obj) ~= "table" then return end
    if Kit.TypeOf(obj) == "Texture" then HeldArt.Hold(obj) else Kit.HoldFrame(obj) end
end

local function HoldNamed(names)
    for _, name in ipairs(names or {}) do Hold(_G[name]) end
end

-- Every FontString that `frame` owns (down to `depth` frames) in mono, at the size and colour it has; dark parchment ink is
-- lightened first, and the hook of PanelSkins.RetintDarkText keeps it light when the stock code writes it again.
local function MonoAsIs(fs)
    if type(fs) ~= "table" or type(fs.GetFont) ~= "function" then return end
    local _, size = Try(fs.GetFont, fs)
    size = Plain(size)
    if type(size) ~= "number" or size <= 0 then size = 12 end
    local r, g, b = Try(fs.GetTextColor, fs)
    r, g, b = Plain(r), Plain(g), Plain(b)
    Theme.ApplyMono(fs, size, (type(r) == "number" and type(g) == "number" and type(b) == "number") and { r, g, b } or C.text)
end

local function LightenText(frame, depth)
    if type(frame) ~= "table" then return end
    for _, region in ipairs(List(frame, "GetRegions")) do
        if Kit.TypeOf(region) == "FontString" then
            PanelSkins.RetintDarkText(region, C.text)
            MonoAsIs(region)
        end
    end
    if depth and depth > 0 then
        for _, child in ipairs(List(frame, "GetChildren")) do LightenText(child, depth - 1) end
    end
end

-- A cut plate of ours (TL and BR chamfer) behind `host`'s own content that follows the size of `ref` (default `host`): the plate
-- is regions of `host`, seated to the rect of `ref` in physical pixels now and again whenever `ref` changes size (a card that
-- expands) or the pixel scale does. With `lockOn` it also carries the four lock-on brackets of the selected card.
local SLAB_RETICLE = 8

local function SeatSlab(rec)
    local ref, host, p = rec.ref, rec.host, rec.plate
    local w, h = Kit.SizePx(ref)
    if not w then return end
    local x = rec.inset or 0
    w = w - 2 * x
    p.w, p.h = w, h
    Kit.Place(p.fill, ref, x, 0, w, h, "TOPLEFT", "TOPLEFT", host)
    Kit.Place(p.ring, ref, x, 0, w, h, "TOPLEFT", "TOPLEFT", host)
    if p.ring2 then Kit.Place(p.ring2, ref, x + 1, 1, w - 2, h - 2, "TOPLEFT", "TOPLEFT", host) end
    if rec.reticle then Kit.SeatReticle(rec.reticle, x, 0, w, h, 0, SLAB_RETICLE) end
end

-- `inset` (physical pixels) keeps the plate clear of the left and right ends of `ref` (a row whose arrows sit at its ends).
local function Slab(host, cut, ref, lockOn, inset)
    ref = ref or host
    local rec = { host = host, ref = ref, inset = inset }
    local w, h = Kit.SizePx(ref)
    rec.plate = Kit.Plate(host, cut or 4, w or 100, h or 20)
    if lockOn and ref == host then
        rec.reticle = Kit.Reticle(host, "OVERLAY", 7)
        Kit.ShowReticle(rec.reticle, false)
    end
    SeatSlab(rec)
    S.slabs[rec] = true
    for _, script in ipairs({ "OnSizeChanged", "OnShow" }) do Kit.HookScript(ref, script, function() SeatSlab(rec) end) end
    return rec
end

-- edge colour and width, face colour and alpha; `lockOn` (a colour) shows the brackets in it, nil hides them
local function PaintSlab(rec, edge, px, fill, fillAlpha, lockOn)
    Kit.PaintPlate(rec.plate, fill or C.row, fillAlpha or 0.92, edge or C.dim, 1, px or 1)
    if rec.reticle then
        Kit.ShowReticle(rec.reticle, lockOn ~= nil)
        if lockOn then Kit.PaintReticle(rec.reticle, lockOn) end
    end
end

-- Runs `perRow(row)` over the rows a ScrollBox holds now and again whenever it repaints (a scroll, a new category): rows are
-- pooled and recycled, so each is met through the box.
local function WatchRows(box, perRow)
    if type(box) ~= "table" then return end
    local function sweep()
        if type(box.ForEachFrame) == "function" then
            pcall(box.ForEachFrame, box, function(row) Step("row", perRow, row) end)
        end
    end
    sweep()
    if S.watched[box] then return end
    S.watched[box] = true
    for _, m in ipairs({ "Update", "FullUpdate", "SetDataProvider" }) do Kit.HookFunc(box, m, sweep) end
end

-------------------------------------------------------------------------------
-- The window: panel chrome over held art
-------------------------------------------------------------------------------

-- opts: title (the stuwave://<title> band), keep (a set of direct regions to leave alone), hold (keys of art frames and
-- textures), names (globals to hold), close (globals of X keys that are not found by name), inset (hold the stock title text).
local function Shell(win, opts)
    if type(win) ~= "table" or S.shells[win] then return false end
    S.shells[win] = true
    win.fsBespokeSkin = true
    opts = opts or {}
    HoldRegions(win, opts.keep)
    HoldKeys(win, opts.hold or {})
    HoldNamed(opts.names)
    local title = Region(win, "TitleContainer")
    if title then Kit.HoldFrame(title.TitleText) end
    Hold(win.TitleText)
    Theme.SkinPanel(win, { strip = false, title = opts.title, fillColor = Theme.COLOR_BG, borderColor = Theme.COLOR_BORDER })
    if Theme.SkinCloseButton then Theme.SkinCloseButton(win) end
    local skins = FS.ButtonSkins
    if skins and skins.SkinCloseButton then
        for _, name in ipairs(opts.close or {}) do
            local btn = Global(name)
            if btn then pcall(skins.SkinCloseButton, btn, { anchor = win }) end
        end
    end
    PanelSkins.SweepOnShow(win)
    return true
end

-- The art of a ButtonFrameTemplate window, held; the window's own band names it.
local FRAME_ART = { "NineSlice", "Bg", "TopTileStreaks", "PortraitContainer", "Inset" }

-- A maximize and minimize pair (MaximizeMinimizeButtonFrameTemplate), as in the map window.
local function MaxMinKeys(frame)
    local mm = Region(frame, "MaximizeMinimizeFrame")
    if not mm then return end
    if mm.MaximizeButton then Key(mm.MaximizeButton, { glyph = CenteredGlyph(GLYPH_BOX, 10, 10) }) end
    if mm.MinimizeButton then Key(mm.MinimizeButton, { glyph = CenteredGlyph(GLYPH_BAR, 10, 10) }) end
end

-- A square frame that only carries art (a dialog border, an inset) held; a box of ours in its place.
local function Panelize(frame, edge)
    if type(frame) ~= "table" or S.cards[frame] then return end
    HoldRegions(frame)
    HoldKeys(frame, { "NineSlice", "Border", "Bg", "BG", "Background" })
    local slab = Slab(frame, 6)
    PaintSlab(slab, edge or C.violet, 1, C.ink, 0.96)
    S.cards[frame] = slab
end

-------------------------------------------------------------------------------
-- Calendar
-------------------------------------------------------------------------------

local DAY = { PAD = 1, CUT = 4, RETICLE = 8, TODAY_FILL = { 0.04, 0.13, 0.17 } }
local DAY_COUNT = 42
local EVENT_LINES = 4

local function IsToday(btn)
    local t = Global("CalendarTodayFrame")
    if not t or not ShownRegion(t) then return false end
    return Plain(Try(t.GetParent, t)) == btn
end

local function PaintDay(btn)
    local rec = S.days[btn]
    if not rec then return end
    local dark = rec.dark ~= nil and ShownRegion(rec.dark)
    local today = IsToday(btn)
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    local edge, alpha, px, fill = C.dim, dark and 0.4 or 0.9, 1, dark and C.ink or C.row
    if today then edge, alpha, px, fill = C.cyan, 1, 2, DAY.TODAY_FILL
    elseif rec.locked then edge, alpha, px = C.violet, 1, 2
    elseif hover then edge, alpha = C.cyan, 1 end
    Kit.PaintPlate(rec.plate, fill, 1, edge, alpha, px)
    Kit.ShowReticle(rec.reticle, rec.locked and not dark)
    if rec.chip then rec.chip:SetShown(today) end
    if rec.date then Kit.Recolor(rec.date, today and C.ink or (dark and C.muted or C.text)) end
end

local function RefreshDays()
    for btn in pairs(S.days) do PaintDay(btn) end
end

local function StyleEventLines(btn, name)
    for i = 1, EVENT_LINES do
        local line = Global(name .. "EventButton" .. i)
        if line then
            HeldArt.Hold(Global(name .. "EventButton" .. i .. "Black"))
            MonoKeep(Global(name .. "EventButton" .. i .. "Text1"), btn, 10)
            MonoKeep(Global(name .. "EventButton" .. i .. "Text2"), btn, 10)
        end
    end
end

local function SkinDay(btn)
    if type(btn) ~= "table" or S.days[btn] or type(btn.CreateTexture) ~= "function" then return end
    local name = Plain(Try(btn.GetName, btn))
    if type(name) ~= "string" then return end
    -- the holiday picture and the invite glow are information; the cell's own parchment and highlight are not
    local keep = {}
    for _, suffix in ipairs({ "EventTexture", "PendingInviteTexture" }) do
        local part = Global(name .. suffix)
        if part then keep[part] = true end
    end
    HeldArt.HoldButton(btn, keep)
    HeldArt.Hold(Global(name .. "EventBackgroundTexture"))
    local bw, bh = Kit.SizePx(btn)
    bw, bh = bw or 91, bh or 91
    local w, h = bw - 2 * DAY.PAD, bh - 2 * DAY.PAD
    local rec = { dark = Global(name .. "DarkFrame"), date = Global(name .. "DateFrameDate") }
    S.days[btn] = rec
    rec.plate = Kit.Plate(btn, DAY.CUT, w, h)
    Kit.Place(rec.plate.fill, btn, DAY.PAD, DAY.PAD, w, h)
    Kit.Place(rec.plate.ring, btn, DAY.PAD, DAY.PAD, w, h)
    if rec.plate.ring2 then Kit.Place(rec.plate.ring2, btn, DAY.PAD + 1, DAY.PAD + 1, w - 2, h - 2) end
    rec.reticle = Kit.Reticle(btn, "OVERLAY", 7)
    Kit.SeatReticle(rec.reticle, DAY.PAD, DAY.PAD, w, h, 0, DAY.RETICLE)
    Kit.PaintReticle(rec.reticle, C.violet)
    Kit.ShowReticle(rec.reticle, false)
    local df = Global(name .. "DateFrame")
    if df then
        HeldArt.Hold(Global(name .. "DateFrameBackground"))
        local dw, dh = Kit.SizePx(df)
        rec.chip = Kit.Rect(df, 0, 0, dw or 28, dh or 22, C.cyan, 1, "BORDER", 7)
        rec.chip:Hide()
    end
    Mono(rec.date, btn, 14, C.text)
    StyleEventLines(btn, name)
    rec.state = Kit.Track(btn, PaintDay)
    Kit.HookFunc(btn, "LockHighlight", function() rec.locked = true; PaintDay(btn) end)
    Kit.HookFunc(btn, "UnlockHighlight", function() rec.locked = false; PaintDay(btn) end)
    if rec.dark then WatchShown(rec.dark, function() PaintDay(btn) end) end
    PaintDay(btn)
end

local function SkinMonthArrows(win)
    local prev, nxt = Global("CalendarPrevMonthButton"), Global("CalendarNextMonthButton")
    if prev then Key(prev, { size = 24, glyph = ChevronGlyph("left") }) end
    if nxt then Key(nxt, { size = 24, glyph = ChevronGlyph("right") }) end
end

local POPUPS = {
    { "CalendarViewHolidayFrame", "day", "CalendarViewHolidayCloseButton" },
    { "CalendarViewRaidFrame", "day", "CalendarViewRaidCloseButton" },
    { "CalendarViewEventFrame", "day", "CalendarViewEventCloseButton" },
    { "CalendarCreateEventFrame", "create", "CalendarCreateEventCloseButton" },
    { "CalendarEventPickerFrame", "picker", nil },
}

local function BuildCalendar()
    local win = Global("CalendarFrame")
    if not win or S.done.calendar then return end
    S.done.calendar = true
    -- every direct region of the frame is the corner and edge art, the month and weekday backgrounds, or a shadow
    Shell(win, { title = "calendar", close = { "CalendarCloseButton" } })
    local todayFrame = Global("CalendarTodayFrame")
    if todayFrame then HoldRegions(todayFrame) end
    Mono(Global("CalendarMonthName"), win, 18, C.text)
    Mono(Global("CalendarYearName"), win, 14, C.cyan)
    for i = 1, 7 do Mono(Global("CalendarWeekday" .. i .. "Name"), win, 14, C.muted) end
    SkinMonthArrows(win)
    for i = 1, DAY_COUNT do Step("day", SkinDay, Global("CalendarDayButton" .. i)) end
    local today = Global("CalendarTodayFrame")
    if today then
        for _, m in ipairs({ "Show", "Hide", "SetParent" }) do Kit.HookFunc(today, m, RefreshDays) end
    end
    if type(_G.CalendarFrame_Update) == "function" then
        Kit.HookFunc(_G, "CalendarFrame_Update", function()
            for i = 1, DAY_COUNT do
                local btn = Global("CalendarDayButton" .. i)
                if btn and S.days[btn] then StyleEventLines(btn, "CalendarDayButton" .. i) end
            end
            RefreshDays()
        end)
    end
    for _, spec in ipairs(POPUPS) do
        local frame = Global(spec[1])
        if frame then
            Step("popup", function()
                HoldKeys(frame, { "Border" })
                local header = Region(frame, "Header")
                if header then HoldRegions(header) end
                Shell(frame, { title = spec[2], close = { spec[3] } })
            end)
        end
    end
    RefreshDays()
end

-------------------------------------------------------------------------------
-- Achievements
-------------------------------------------------------------------------------

-- The stock art of an achievement card; the shield, the icon picture, the tracked check and the plus and minus are information.
local ACH_ART = { "Background", "BottomLeftTsunami", "BottomRightTsunami", "TopLeftTsunami", "TopRightTsunami",
    "BottomTsunami1", "TopTsunami1", "TitleBar", "Glow", "RewardBackground", "GuildCornerL", "GuildCornerR" }

local function PaintAchievement(row)
    local rec = S.rows[row]
    if not rec then return end
    local done = Plain(row.completed) == true
    local selected = Plain(Try(row.IsSelected, row)) == true
    local hover = rec.state and rec.state.hover
    local edge, px, fill = C.violet, 1, C.row
    if selected then edge, px, fill = C.cyan, 2, DAY.TODAY_FILL
    elseif hover then edge = C.cyan
    elseif done then edge = C.amber end
    PaintSlab(rec.slab, edge, px, fill, 0.94, selected and C.cyan or nil)
    if rec.iconSlab then PaintSlab(rec.iconSlab, done and C.amber or C.dim, 1, C.ink, 0) end
end

local function SkinAchievement(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    local rec = {}
    S.rows[row] = rec
    for _, key in ipairs(ACH_ART) do HeldArt.Hold(row[key]) end
    HoldKeys(row, { "NineSlice", "Highlight" })
    local icon = Region(row, "Icon")
    if icon then
        HeldArt.Hold(icon.bling)
        HeldArt.Hold(icon.frame)
        if icon.texture then
            rec.iconSlab = Slab(icon, 3, icon.texture)
        end
    end
    rec.slab = Slab(row, 4, row, true)
    MonoKeep(row.Label, row, 14)
    PanelSkins.RetintDarkText(row.Description, C.text)
    MonoAsIs(row.Description)
    PanelSkins.RetintDarkText(row.HiddenDescription, C.text)
    MonoAsIs(row.HiddenDescription)
    MonoAsIs(row.Reward)
    local shield = Region(row, "Shield")
    if shield then
        MonoAsIs(shield.Points)
        MonoAsIs(shield.DateCompleted)
    end
    rec.state = Kit.Track(row, PaintAchievement)
    for _, m in ipairs({ "Saturate", "Desaturate", "SetSelected", "Init", "Expand", "Collapse" }) do
        Kit.HookFunc(row, m, function() PaintAchievement(row) end)
    end
    PaintAchievement(row)
end

local function PaintCategory(row)
    local rec = S.rows[row]
    if not rec then return end
    local hover = rec.state and rec.state.hover
    if rec.selected then PaintSlab(rec.slab, C.cyan, 1, C.band, 1)
    elseif hover then PaintSlab(rec.slab, C.cyan, 1, C.row, 1)
    else PaintSlab(rec.slab, C.dim, 1, C.ink, 0) end
    if rec.label then Kit.Recolor(rec.label, (rec.selected or hover) and C.cyan or C.text) end
end

local function SkinCategory(row)
    if type(row) ~= "table" or S.rows[row] then return end
    local button = Region(row, "Button")
    if not button or type(button.CreateTexture) ~= "function" then return end
    local rec = {}
    S.rows[row] = rec
    HeldArt.HoldButton(button)
    rec.slab = Slab(button, 4)
    rec.label = button.Label
    Mono(rec.label, button, 14, C.text)
    rec.state = Kit.Track(button, function() PaintCategory(row) end)
    Kit.HookFunc(row, "UpdateSelectionState", function(_, selected)
        rec.selected = Plain(selected) == true
        PaintCategory(row)
    end)
    PaintCategory(row)
end

-- A stat or summary card of the achievement window: its own art held, its text lightened, one box.
local function SkinPlainRow(row)
    if type(row) ~= "table" or S.rows[row] or type(row.CreateTexture) ~= "function" then return end
    local rec = {}
    S.rows[row] = rec
    HoldRegions(row)
    HoldKeys(row, { "NineSlice" })
    rec.slab = Slab(row, 4)
    PaintSlab(rec.slab, C.dim, 1, C.row, 0.94)
    LightenText(row, 0)
end

local function SweepObjectives()
    LightenText(Global("AchievementFrameAchievementsObjectives"), 2)
    LightenText(Global("AchievementFrameAchievementsObjectivesOffScreen"), 2)
end

local ACH_PAGES = { "AchievementFrameAchievements", "AchievementFrameStats", "AchievementFrameSummary", "AchievementFrameComparison" }

local function BuildAchievements()
    local win = Global("AchievementFrame")
    if not win or S.done.achievements then return end
    S.done.achievements = true
    -- the metal and wood borders, the parchment of the category list, the watermark and the guild emblems are direct regions
    Shell(win, { title = "achievements", close = { "AchievementFrameCloseButton" } })
    local header = Region(win, "Header")
    if header then
        HoldRegions(header)
        Mono(header.Title, header, 14, C.text)
        Mono(header.Points, header, 20, C.amber)
    end
    local details = Region(win, "HeaderDetails")
    if details then HoldKeys(details, { "TopTileStreaks" }) end
    for _, name in ipairs(ACH_PAGES) do
        local page = Global(name)
        if page then HoldRegions(page) end
    end
    HoldNamed({ "AchievementFrameStatsBG" })
    local cats = Region(win, "Categories")
    if cats then
        HoldRegions(cats)
        HoldKeys(cats, { "NineSlice" })
        local slab = Slab(cats, 6)
        PaintSlab(slab, C.violet, 1, C.ink, 0)
        S.cards[cats] = slab
        WatchRows(cats.ScrollBox, SkinCategory)
    end
    local ach = Global("AchievementFrameAchievements")
    if ach then WatchRows(ach.ScrollBox, SkinAchievement) end
    local stats = Global("AchievementFrameStats")
    if stats then WatchRows(stats.ScrollBox, SkinPlainRow) end
    for i = 1, 4 do SkinPlainRow(Global("AchievementFrameSummaryAchievement" .. i)) end
    local filters = details and Region(details, "Filters")
    local search = filters and Region(filters, "SearchBox")
    if search then Panelize(Region(search, "SearchPreviewContainer")) end
    Panelize(Region(win, "SearchResults"))
    for _, fn in ipairs({ "AchievementObjectives_DisplayCriteria", "AchievementObjectives_DisplayProgressiveAchievement" }) do
        if type(_G[fn]) == "function" then Kit.HookFunc(_G, fn, SweepObjectives) end
    end
    SweepObjectives()
end

-------------------------------------------------------------------------------
-- Dressing room
-------------------------------------------------------------------------------

local GLYPH_LIST = { { 0, 0, 10, 2 }, { 0, 4, 10, 2 }, { 0, 8, 10, 2 } }

local function BuildDressingRoom()
    local win = Global("DressUpFrame")
    if not win or S.done.dress then return end
    S.done.dress = true
    -- ModelBackground (the class backdrop of the scene) is the one direct region
    Shell(win, { title = "dressing", hold = FRAME_ART, close = { "DressUpFrameCloseButton" } })
    local scene = Region(win, "ModelScene")
    if scene then
        local slab = Slab(win, 6, scene)
        PaintSlab(slab, C.violet, 1, C.ink, 0.85)
        S.cards[scene] = slab
    end
    MaxMinKeys(win)
    local list = Region(win, "ToggleCustomSetDetailsButton")
    if list then Key(list, { size = KEY, glyph = CenteredGlyph(GLYPH_LIST, 10, 10) }) end
    local details = Region(win, "CustomSetDetailsPanel")
    if details then
        local keep = {}
        if details.BlackBackground then keep[details.BlackBackground] = true end
        HoldRegions(details, keep)
        local slab = Slab(details, 6)
        PaintSlab(slab, C.violet, 1, C.ink, 0)
        S.cards[details] = slab
    end
end

-------------------------------------------------------------------------------
-- Tabard
-------------------------------------------------------------------------------

local TABARD_ROWS = 5
local PICKER_INSET = 30

local function SkinPicker(i)
    local row = Global("TabardFrameCustomization" .. i)
    if not row then return end
    local name = "TabardFrameCustomization" .. i
    for _, suffix in ipairs({ "Left", "Middle", "Right" }) do HeldArt.Hold(Global(name .. suffix)) end
    local slab = Slab(row, 4, row, false, PICKER_INSET)
    PaintSlab(slab, C.dim, 1, C.row, 0.95)
    S.cards[row] = slab
    Mono(Global(name .. "Text"), row, 11, C.text)
    local left, right = Global(name .. "LeftButton"), Global(name .. "RightButton")
    if left then Key(left, { size = KEY, glyph = ChevronGlyph("left") }) end
    if right then Key(right, { size = KEY, glyph = ChevronGlyph("right") }) end
end

local function BuildTabard()
    local win = Global("TabardFrame")
    if not win or S.done.tabard then return end
    S.done.tabard = true
    -- the emblem is four alpha ADD textures Blizzard only fades and never re-shows: they are kept, never held or hidden
    local keep = {}
    for _, n in ipairs({ "TabardFrameEmblemTopLeft", "TabardFrameEmblemTopRight", "TabardFrameEmblemBottomLeft", "TabardFrameEmblemBottomRight" }) do
        local t = Global(n)
        if t then keep[t] = true end
    end
    Shell(win, { title = "tabard", hold = FRAME_ART, keep = keep, close = { "TabardFrameCloseButton" } })
    Mono(Global("TabardFrameNameText"), win, 14, C.text)
    Mono(Global("TabardFrameGreetingText"), win, 12, C.muted)
    HoldNamed({ "TabardFrameCustomizationBorder", "TabardFrameMoneyInset", "TabardFrameMoneyBg" })
    for i = 1, TABARD_ROWS do Step("picker", SkinPicker, i) end
    local left, right = Global("TabardCharacterModelRotateLeftButton"), Global("TabardCharacterModelRotateRightButton")
    if left then Key(left, { size = 24, glyph = ChevronGlyph("left") }) end
    if right then Key(right, { size = 24, glyph = ChevronGlyph("right") }) end
    local cost = Global("TabardFrameCostFrame")
    if cost then
        HoldKeys(cost, { "NineSlice" })
        local slab = Slab(cost, 6)
        PaintSlab(slab, C.violet, 1, C.ink, 0.96)
        S.cards[cost] = slab
        Mono(Global("TabardFrameCostLabel"), cost, 12, C.muted)
    end
    if PanelSkins.TryStyleMoney then
        PanelSkins.TryStyleMoney(Global("TabardFrameCostMoneyFrame"))
        PanelSkins.TryStyleMoney(Global("TabardFrameMoneyFrame"))
    end
end

-------------------------------------------------------------------------------
-- Gem sockets
-------------------------------------------------------------------------------

local function BuildSockets()
    local win = Global("ItemSocketingFrame")
    if not win or S.done.sockets then return end
    S.done.sockets = true
    -- ParchmentFrame-*, SocketFrame-*, ButtonFrame-*, GoldBorder-*, BorderShadow-* and the nubs are all direct regions
    Shell(win, { title = "sockets", hold = FRAME_ART, close = { "ItemSocketingFrameCloseButton" } })
    local container = Region(win, "SocketingContainer")
    local sockets = container and container.SocketFrames
    if type(sockets) == "table" then
        for _, socket in ipairs(sockets) do
            if type(socket) == "table" and not S.cards[socket] then
                -- the gem and the colour of its socket (Background, the brackets, the shine) carry the meaning
                local keep = {}
                if socket.Icon then keep[socket.Icon] = true end
                if socket.Background then keep[socket.Background] = true end
                HoldRegions(socket, keep)
                local slab = Slab(socket, 4)
                PaintSlab(slab, C.violet, 1, C.ink, 0.9)
                S.cards[socket] = slab
            end
        end
    end
end

-------------------------------------------------------------------------------
-- Barber shop
-------------------------------------------------------------------------------

local VIGNETTE = { 0.35, 0.18, 0.62 }
local BARBER_BUTTONS = { CancelButton = "pink", ResetButton = "muted", AcceptButton = "cyan" }

local function BuildBarber()
    local win = Global("BarberShopFrame")
    if not win or S.done.barber then return end
    S.done.barber = true
    win.fsBespokeSkin = true
    for _, key in ipairs({ "TopBackgroundOverlay", "LeftBackgroundOverlay", "RightBackgroundOverlay" }) do
        local v = win[key]
        if type(v) == "table" and type(v.SetVertexColor) == "function" then pcall(v.SetVertexColor, v, VIGNETTE[1], VIGNETTE[2], VIGNETTE[3], 1) end
    end
    local skins = FS.ButtonSkins
    if skins and skins.SkinTextButton then
        for key, accent in pairs(BARBER_BUTTONS) do
            local btn = Region(win, key)
            if btn and not (skins.Parts and skins.Parts(btn)) then pcall(skins.SkinTextButton, btn, { accent = C[accent] }) end
        end
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local BUILDERS = {
    { "CalendarFrame", BuildCalendar }, { "AchievementFrame", BuildAchievements }, { "DressUpFrame", BuildDressingRoom },
    { "TabardFrame", BuildTabard }, { "ItemSocketingFrame", BuildSockets }, { "BarberShopFrame", BuildBarber },
}

local function Build()
    if not S.done.reseat then
        S.done.reseat = true
        Kit.OnReseat(function()
            for rec in pairs(S.slabs) do pcall(SeatSlab, rec) end
        end)
    end
    for _, spec in ipairs(BUILDERS) do
        if Global(spec[1]) then Step("build." .. spec[1], spec[2]) end
    end
end
B.Build = Build

local entries = {}
for _, spec in ipairs(BUILDERS) do entries[#entries + 1] = { name = spec[1], guard = "fsBespokeSkin" } end
PanelSkins.RegisterInspect("Bespoke", entries)

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
